import base64, hmac, json, os, re, secrets, tempfile, threading, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
import test_3d as core
ROOT=Path(__file__).resolve().parent
TOKEN_FILE=ROOT/'PRIVATE_BRIDGE_TOKEN.txt'
if not TOKEN_FILE.exists(): TOKEN_FILE.write_text(secrets.token_hex(32),encoding='ascii')
TOKEN=TOKEN_FILE.read_text(encoding='ascii').strip()
if not re.fullmatch(r'[0-9a-f]{64}',TOKEN): raise RuntimeError('Invalid bridge token; remove PRIVATE_BRIDGE_TOKEN.txt and restart.')
LOCK=threading.Lock(); JOBS={}; STARTS=0
MAX_STARTS_FILE=ROOT/'MAX_3D_JOBS.txt'
MAX_STARTS=10

def session_limit():
    # Called under LOCK by requests. Invalid edits retain the last valid limit.
    global MAX_STARTS
    try:
        value=int(MAX_STARTS_FILE.read_text(encoding='utf-8-sig').strip())
        if 1<=value<=1000: MAX_STARTS=value
    except (OSError, ValueError): pass
    return MAX_STARTS
BASE=None

def work(job,image,ext,engine,quality):
    try:
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/('reference'+ext);path.write_bytes(image)
            target=core.run(BASE,path,engine,quality=quality)
        if target.stat().st_size>80*1024**2: raise RuntimeError('GLB exceeds 80 MB')
        with LOCK: JOBS[job].update(state='done',file=target,seconds=round(time.monotonic()-JOBS[job]['start'],1),bytes=target.stat().st_size)
        print('DONE:',quality,round(target.stat().st_size/1024**2,1),'MiB',JOBS[job]['seconds'],'s',flush=True)
    except Exception as e:
        print('JOB FAILED:',job,str(e),flush=True)
        with LOCK: JOBS[job].update(state='error')


# Local FLUX.2 Klein image jobs; 3D routes below are unchanged.
IMAGE_LIMIT=10*1024*1024
IMAGE_WORKFLOWS={'text':'flux2_text_to_image.json','edit':'flux2_image_edit.json'}

def run_image(job,prompt,image=None,ext=None):
    import copy
    filename=IMAGE_WORKFLOWS['edit' if image else 'text']
    workflow=json.loads((ROOT/filename).read_text(encoding='utf-8-sig'))
    workflow['75:74']['inputs']['text']=prompt
    workflow['75:73']['inputs']['noise_seed']=secrets.randbelow(2**53)
    workflow['9']['inputs']['filename_prefix']='caratzon_2d_'+job
    if image:
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/('reference'+ext)
            path.write_bytes(image)
            uploadname=core.upload(BASE,path,job)
        workflow['76']['inputs']['image']=uploadname
    submit=core.req(BASE,'/prompt',json.dumps({'prompt':workflow,'client_id':uuid.uuid4().hex}).encode(),{'Content-Type':'application/json'},timeout=60)
    pid=submit.get('prompt_id')
    if not pid: raise RuntimeError('ComfyUI did not accept image job')
    end=time.monotonic()+900
    while time.monotonic()<end:
        history=core.req(BASE,'/history/'+pid,timeout=30)
        if pid in history:
            entry=history[pid]
            status=entry.get('status',{})
            if status.get('status_str')=='error':raise RuntimeError('ComfyUI image execution failed: '+str(status.get('messages',[]))[-1000:])
            if status.get('completed') or status.get('status_str')=='success':
                files=entry.get('outputs',{}).get('9',{}).get('images',[])
                for f in files:
                    if f.get('type')!='output' or not str(f.get('filename','')).lower().endswith('.png'):continue
                    from urllib.parse import urlencode
                    url='/view?'+urlencode({'filename':f['filename'],'subfolder':f.get('subfolder',''),'type':'output'})
                    # Local ComfyUI: read only returned PNG output (max 10 MiB).
                    imagebytes=core.req(BASE,url,timeout=120,binary=True)
                    if not imagebytes.startswith(b'\x89PNG\r\n\x1a\n') or len(imagebytes)>IMAGE_LIMIT:raise RuntimeError('Invalid image output')
                    folder=ROOT/'RESULTS';folder.mkdir(exist_ok=True)
                    path=folder/('caratzon_2d_'+job+'.png');path.write_bytes(imagebytes)
                    return path
                raise RuntimeError('No PNG image returned by SaveImage')
        time.sleep(1)
    raise RuntimeError('Image generation timeout')

def work_image(job,prompt,image,ext):
    try:
        target=run_image(job,prompt,image,ext)
        with LOCK:JOBS[job].update(state='done',file=target,seconds=round(time.monotonic()-JOBS[job]['start'],1),bytes=target.stat().st_size,kind='image')
        print('IMAGE DONE:',job,flush=True)
    except Exception as e:
        print('IMAGE FAILED:',job,str(e),flush=True)
        with LOCK:JOBS[job].update(state='error',error='IMAGE_FAILED')

def check_comfy_queue():
    q=core.req(BASE,'/queue',timeout=3)
    return bool(q.get('queue_running') or q.get('queue_pending'))

class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup();self.connection.settimeout(25)
    def log_message(self,*args): pass
    def send_json(self,status,data):
        b=json.dumps(data).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
    def allowed(self):
        if not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+TOKEN):
            self.send_json(401,{'error':'UNAUTHORIZED'});return False
        return True
    def do_GET(self):
        if not self.allowed():return
        u=urlsplit(self.path)
        if u.path=='/health':
            try:
                q=core.req(BASE,'/queue',timeout=3)
                with LOCK: busy=any(j['state']=='running' for j in JOBS.values()); limit=session_limit(); remaining=max(0,limit-STARTS)
                self.send_json(200,{'build':'4.1','qualities':['fast','hd','ultra'],'online':True,'busy':bool(busy or q.get('queue_running') or q.get('queue_pending')),'remaining':remaining,'limit':limit,'used':STARTS,'image_ready':all((ROOT/n).exists() for n in IMAGE_WORKFLOWS.values())})
            except Exception:self.send_json(503,{'error':'COMFY_OFFLINE'})
            return
        m=re.fullmatch(r'/(job|file|image-job|image-file)/([a-f0-9]{32})',u.path)
        if not m:self.send_json(404,{'error':'NOT_FOUND'});return
        with LOCK: j=dict(JOBS.get(m[2],{}))
        if not j:self.send_json(404,{'error':'JOB_NOT_FOUND'});return
        if m[1] in ('job','image-job') and (m[1]=='image-job')!=(j.get('kind')=='image'):self.send_json(404,{'error':'JOB_NOT_FOUND'});return
        if m[1] in ('file','image-file') and (m[1]=='image-file')!=(j.get('kind')=='image'):self.send_json(404,{'error':'JOB_NOT_FOUND'});return
        if m[1] in ('job','image-job'):self.send_json(200,{'state':j['state'],'elapsed':int(time.monotonic()-j['start']),'seconds':j.get('seconds'),'bytes':j.get('bytes')});return
        if j['state']!='done':self.send_json(409,{'error':'NOT_READY'});return
        p=j['file']
        try:
            with p.open('rb') as f:
                self.send_response(200);self.send_header('Content-Type','image/png' if j.get('kind')=='image' else 'model/gltf-binary');self.send_header('Content-Length',str(p.stat().st_size));self.send_header('Cache-Control','no-store');self.end_headers()
                while chunk:=f.read(65536):self.wfile.write(chunk)
        except (OSError,ConnectionError):pass
    def do_POST(self):
        global STARTS
        if not self.allowed():return
        if self.path=='/image-submit':
            try:
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<=12*1024**2:raise ValueError()
                d=json.loads(self.rfile.read(n))
                mode=d.get('mode');prompt=d.get('prompt','')
                if mode not in ('text','edit') or not isinstance(prompt,str) or not 3<=len(prompt)<=3000:raise ValueError()
                image=None;ext=None
                if mode=='edit':
                    m=re.fullmatch(r'data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)',d.get('image',''))
                    if not m:raise ValueError()
                    image=base64.b64decode(m[2],validate=True)
                    ext={'png':'.png','jpeg':'.jpg','webp':'.webp'}[m[1]]
                    if not 0<len(image)<=core.MAX_IMAGE:raise ValueError()
                    if not ((ext=='.png' and image.startswith(b'\x89PNG\r\n\x1a\n')) or (ext=='.jpg' and image.startswith(b'\xff\xd8\xff')) or (ext=='.webp' and image[:4]==b'RIFF' and image[8:12]==b'WEBP')):raise ValueError()
            except Exception:self.send_json(400,{'error':'BAD_IMAGE_REQUEST'});return
            with LOCK:
                if STARTS>=session_limit():self.send_json(429,{'error':'SESSION_LIMIT'});return
                if any(j['state']=='running' for j in JOBS.values()):self.send_json(409,{'error':'BUSY'});return
                try:
                    if check_comfy_queue():self.send_json(409,{'error':'BUSY'});return
                except Exception:self.send_json(503,{'error':'COMFY_OFFLINE'});return
                if not (ROOT/IMAGE_WORKFLOWS[mode]).exists():self.send_json(503,{'error':'IMAGE_WORKFLOW_MISSING'});return
                job=uuid.uuid4().hex
                JOBS[job]={'state':'running','kind':'image','start':time.monotonic()}
                STARTS+=1
                threading.Thread(target=work_image,args=(job,prompt,image,ext),daemon=True).start()
            self.send_json(202,{'job':job});return
        if self.path!='/submit':self.send_json(404,{'error':'NOT_FOUND'});return
        try:
            n=int(self.headers.get('Content-Length','0'))
            if not 0<n<=12*1024**2:raise ValueError()
            d=json.loads(self.rfile.read(n));engine=d['engine'];quality=d.get('quality','ultra');m=re.fullmatch(r'data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)',d['image'])
            if not m or engine not in ('pixal','trellis') or quality not in core.PRESETS:raise ValueError()
            image=base64.b64decode(m[2],validate=True);ext={'png':'.png','jpeg':'.jpg','webp':'.webp'}[m[1]]
            if not 0<len(image)<=core.MAX_IMAGE:raise ValueError()
            if not ((ext=='.png' and image.startswith(b'\x89PNG\r\n\x1a\n')) or (ext=='.jpg' and image.startswith(b'\xff\xd8\xff')) or (ext=='.webp' and image[:4]==b'RIFF' and image[8:12]==b'WEBP')):raise ValueError()
        except Exception:self.send_json(400,{'error':'BAD_IMAGE'});return
        with LOCK:
            if STARTS>=session_limit():self.send_json(429,{'error':'SESSION_LIMIT'});return
            if any(j['state']=='running' for j in JOBS.values()):self.send_json(409,{'error':'BUSY'});return
            try:
                q=core.req(BASE,'/queue',timeout=3)
                if q.get('queue_running') or q.get('queue_pending'):self.send_json(409,{'error':'BUSY'});return
            except Exception:self.send_json(503,{'error':'COMFY_OFFLINE'});return
            job=uuid.uuid4().hex;JOBS[job]={'state':'running','start':time.monotonic()};STARTS+=1
            threading.Thread(target=work,args=(job,image,ext,engine,quality),daemon=True).start()
        self.send_json(202,{'job':job})

if __name__=='__main__':
    BASE,s=core.find_server()
    if not any('4090' in str(d.get('name','')) for d in s.get('devices',[]) if isinstance(d,dict)):raise RuntimeError('RTX 4090 not detected')
    print('CARATZON V4.1 PRIVATE BRIDGE\nComfyUI:',BASE,'\nBridge: http://127.0.0.1:8765\nPrivate token file:',TOKEN_FILE,'\n',session_limit(),'jobs per session; edit MAX_3D_JOBS.txt to change. One at a time. Keep this window open.\nDo NOT share the token or tunnel URL publicly.',flush=True)
    ThreadingHTTPServer(('127.0.0.1',8765),Handler).serve_forever()
