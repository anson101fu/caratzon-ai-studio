import base64, copy, json, os, re, struct, subprocess, sys, time, uuid
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler
from urllib.parse import urlencode
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parent
OPENER = build_opener(ProxyHandler({})) # local only; never use VPN HTTP proxy
MAX_IMAGE = 8 * 1024**2
MAX_GLB = 100 * 1024**2

def req(base, path, data=None, headers=None, timeout=20, binary=False):
    request = Request(base+path, data=data, headers=headers or {})
    try:
        with OPENER.open(request, timeout=timeout) as r:
            if binary:
                b = r.read(MAX_GLB+1)
                if len(b)>MAX_GLB: raise RuntimeError('GLB exceeds 100 MB')
                return b
            return json.load(r)
    except HTTPError as e:
        detail=e.read(4096).decode('utf-8','replace')
        raise RuntimeError(f'HTTP {e.code}: {detail}') from e

def detect_ports():
    ports=[8000,8188,8001,8189]
    if os.name=='nt':
        try:
            listing=subprocess.check_output(['netstat','-ano','-p','tcp'],text=True,errors='replace',timeout=10)
            for line in listing.splitlines():
                fields=line.split()
                if len(fields)>=5 and fields[0]=='TCP' and fields[3]=='LISTENING':
                    match=re.match(r'^(?:127\.0\.0\.1|0\.0\.0\.0|\[::\]|\[::1\]):(\d+)$',fields[1])
                    if match and int(match[1])>=1024: ports.append(int(match[1]))
        except Exception: pass
    return list(dict.fromkeys(ports))

def find_server():
    for port in detect_ports():
        base=f'http://127.0.0.1:{port}'
        try:
            s=req(base,'/system_stats',timeout=1)
            if not isinstance(s,dict) or not ('system' in s and 'devices' in s): continue
            n=req(base,'/object_info/Save3DAdvanced',timeout=3)
            if 'Save3DAdvanced' in n: return base,s
        except Exception: pass
    raise RuntimeError('ComfyUI API not found. Keep Caratzon-3D open, and check it is running locally.')

def upload(base, path, job):
    image=path.read_bytes()
    if not 0<len(image)<=MAX_IMAGE: raise RuntimeError('Image must be 8 MB or smaller.')
    ext=path.suffix.lower(); types={'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp'}
    if ext not in types: raise RuntimeError('Select PNG, JPG or WEBP.')
    name='caratzon_'+job+ext
    boundary='----Caratzon'+uuid.uuid4().hex
    chunks=[f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\nContent-Type: {types[ext]}\r\n\r\n'.encode(),image,b'\r\n',f'--{boundary}\r\nContent-Disposition: form-data; name="type"\r\n\r\ninput\r\n--{boundary}--\r\n'.encode()]
    result=req(base,'/upload/image',b''.join(chunks),{'Content-Type':'multipart/form-data; boundary='+boundary},timeout=60)
    filename=result.get('name'); sub=result.get('subfolder','')
    if not filename or result.get('type','input')!='input': raise RuntimeError('Unexpected upload response')
    return (sub+'/' if sub else '')+filename

PRESETS={"fast": (1024,1024,150000), "hd": (1024,2048,300000), "ultra": (1536,4096,700000)}

def build_workflow(filename,engine,job,quality="ultra"):
    w=json.loads((ROOT/'workflow.json').read_text(encoding='utf-8-sig'))
    assert w['122']['class_type']=='LoadImage' and w['316']['class_type']=='PrimitiveBoolean' and w['322']['class_type']=='Save3DAdvanced'
    w['122']['inputs']['image']=filename
    w['316']['inputs']['value']=engine=='trellis'
    w['322']['inputs']['filename_prefix']='3d/caratzon_'+job
    if quality not in PRESETS: raise ValueError('Invalid quality')
    if quality != 'ultra':
        resolution,texture,faces=PRESETS[quality]
        w['94']['inputs']['target_resolution']=resolution
        w['288']['inputs']['value']=texture
        w['186']['inputs']['target_face_count']=faces
        w['224']['inputs']['resolution']=min(2048,texture)
        # Remove independent preview outputs only; keep all connected processing nodes.
        for node in ('246','323','262'):
            if not any(isinstance(v,list) and len(v)==2 and v[0]==node for n in w.values() for v in n.get('inputs',{}).values()):
                w.pop(node,None)
    # Ultra retains the original workflow settings.
    return w

def get_glb(base, entry):
    out=entry.get('outputs',{}).get('322',{})
    files=out.get('3d',[])
    if not isinstance(files,list): raise RuntimeError('Unexpected 3D result')
    for f in files:
        if not isinstance(f,dict) or not str(f.get('filename','')).lower().endswith('.glb') or f.get('type')!='output': continue
        q=urlencode({'filename':f['filename'],'subfolder':f.get('subfolder',''),'type':'output'})
        b=req(base,'/view?'+q,timeout=120,binary=True)
        if len(b)<20 or struct.unpack('<4sII',b[:12])!=(b'glTF',2,len(b)): raise RuntimeError('Invalid GLB file')
        return b
    raise RuntimeError('Node 322 did not return a saved GLB. Output keys: '+str(list(out)))

def run(base,path,engine,deadline=1800,quality="ultra"):
    job=uuid.uuid4().hex[:16]
    name=upload(base,path,job)
    workflow=build_workflow(name,engine,job,quality)
    result=req(base,'/prompt',json.dumps({'prompt':workflow,'client_id':uuid.uuid4().hex}).encode(),{'Content-Type':'application/json'},timeout=60)
    pid=result.get('prompt_id')
    if not pid: raise RuntimeError('Prompt not accepted: '+str(result)[:3000])
    print('PROMPT ID:',pid,flush=True)
    t=time.monotonic(); last=-1
    while time.monotonic()-t<deadline:
        h=req(base,'/history/'+pid,timeout=30)
        if pid in h:
            entry=h[pid]; status=entry.get('status',{})
            if status.get('status_str')=='error': raise RuntimeError('ComfyUI execution error: '+str(status.get('messages',[]))[-3000:])
            if status.get('completed') or status.get('status_str')=='success':
                b=get_glb(base,entry); output=ROOT/'RESULTS';output.mkdir(exist_ok=True)
                target=output/f'caratzon_{engine}_{job}.glb';target.write_bytes(b)
                return target
        elapsed=int(time.monotonic()-t)
        if elapsed//10!=last:
            print(f'Waiting for job ... {elapsed}s',flush=True);last=elapsed//10
        time.sleep(1)
    raise RuntimeError('Polling timed out. ComfyUI may still be running; check its queue before retrying.')

def main():
    print('CARATZON V4 - LOCAL 3D API TEST (no paid API)\nKeep ComfyUI Caratzon-3D running. No public network listener.\n')
    base,s=find_server();print('COMFY API:',base);print('GPU:',s.get('devices'))
    if not any('4090' in str(d.get('name','')) for d in s.get('devices',[]) if isinstance(d,dict)):
        raise RuntimeError('RTX 4090 not reported by ComfyUI. Check the instance.')
    q=req(base,'/queue');
    if q.get('queue_running') or q.get('queue_pending'): raise RuntimeError('ComfyUI already has jobs. Finish them before running this test.')
    print('1 = Pixal3D (your current workflow)\n2 = TRELLIS.2')
    answer=input('Engine [1/2, Enter = 1]: ').strip() or '1'
    if answer not in ('1','2'): raise RuntimeError('Choose 1 or 2.')
    import tkinter as tk
    from tkinter import filedialog
    root=tk.Tk();root.withdraw();root.attributes('-topmost',True)
    path=filedialog.askopenfilename(title='Select a jewellery image',filetypes=[('Images','*.png *.jpg *.jpeg *.webp')]);root.destroy()
    if not path: print('Cancelled.');return
    print('Selected:',Path(path).name)
    if input('Generate one REAL model on your own 4090? [y/N] ').strip().lower()!='y':return
    target=run(base,Path(path),'trellis' if answer=='2' else 'pixal')
    print('\nSUCCESS: valid GLB downloaded:',target,flush=True)
    if os.name=='nt': os.startfile(str(target.parent))

if __name__=='__main__':
    try: main()
    except Exception as e:
        print('\nTEST FAILED:',str(e),flush=True);sys.exit(1)
