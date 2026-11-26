"""Experimental, one FLUX sampler with N separate conditioning rows.
Compatible text-only workflow. No hidden serial fallback. Requires custom node.
"""
import copy, json, re, secrets, struct, time, uuid, zlib
from pathlib import Path
from urllib.parse import urlencode
NODE='CZ456BatchConditioning'

def make_graph(workflow, entries):
    if not 2<=len(entries)<=5:raise ValueError('Batch size must be 2–5')
    if len({j for j,p in entries})!=len(entries):raise ValueError('Duplicate job ID')
    g=copy.deepcopy(workflow)
    checks={'9':'SaveImage','75:74':'CLIPTextEncode','75:66':'EmptyFlux2LatentImage','75:63':'CFGGuider','75:64':'SamplerCustomAdvanced','75:65':'VAEDecode','75:82':'ConditioningZeroOut','75:73':'RandomNoise','75:70':'UNETLoader'}
    if any(g.get(k,{}).get('class_type')!=v for k,v in checks.items()):raise ValueError('Unsupported local FLUX workflow; no serial fallback')
    if g['75:66']['inputs'].get('width')!=1024 or g['75:66']['inputs'].get('height')!=1024 or g['75:70']['inputs'].get('unet_name')!='flux-2-klein-4b-fp8.safetensors':raise ValueError('Batch only tested against the known 1K Klein 4B workflow')
    if g['75:63']['inputs'].get('cfg')!=1:raise ValueError('Unsupported CFG')
    original=g.pop('75:74');g.pop('9');links={};outputs={}
    for i,(job,prompt) in enumerate(entries):
        if not re.fullmatch('[a-f0-9]{32}',job) or not isinstance(prompt,str) or not 3<=len(prompt)<=3000:raise ValueError('Invalid job')
        node=f'cz456_text_{i}';g[node]=copy.deepcopy(original);g[node]['inputs']['text']=prompt;links[f'c{i+1}']=[node,0]
        split=f'cz456_split_{i}';save=f'cz456_save_{i}';prefix='cz456_'+job
        g[split]={'class_type':'ImageFromBatch','inputs':{'image':['75:65',0],'batch_index':i,'length':1}}
        g[save]={'class_type':'SaveImage','inputs':{'images':[split,0],'filename_prefix':prefix}}
        outputs[job]=(save,prefix)
    g['cz456_batch']={'class_type':NODE,'inputs':links}
    g['75:63']['inputs']['positive']=['cz456_batch',0]
    g['75:82']['inputs']['conditioning']=['cz456_batch',0]
    g['75:66']['inputs']['batch_size']=len(entries)
    g['75:73']['inputs']['noise_seed']=secrets.randbelow(2**53)
    return g,outputs

def clean_png(data):
    # Comfy SaveImage can embed the entire multi-client prompt graph. Never
    # deliver any ancillary metadata (including other customers' prompts).
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('Not PNG')
    out=bytearray(data[:8]);i=8;ended=False;has_data=False;first=True
    while i+12<=len(data):
        n=struct.unpack('>I',data[i:i+4])[0];kind=data[i+4:i+8];end=i+12+n
        if end>len(data):raise ValueError('Truncated PNG')
        if zlib.crc32(data[i+4:end-4])&0xffffffff!=struct.unpack('>I',data[end-4:end])[0]:raise ValueError('PNG CRC error')
        if first and (kind!=b'IHDR' or n!=13):raise ValueError('Invalid PNG header')
        first=False
        if kind in (b'IHDR',b'PLTE',b'IDAT',b'IEND',b'tRNS',b'sRGB',b'gAMA',b'cHRM'):out.extend(data[i:end])
        if kind==b'IDAT':has_data=True
        if kind==b'IEND':ended=True;break
        i=end
    if not ended or not has_data:raise ValueError('Incomplete PNG')
    return bytes(out)

def available(req,base):
    try:return NODE in req(base,'/object_info/'+NODE,timeout=8) and 'ImageFromBatch' in req(base,'/object_info/ImageFromBatch',timeout=8)
    except Exception:return False

def run_batch(req,base,workflow,entries,dest,timeout=900):
    g,outputs=make_graph(workflow,entries)
    submit=req(base,'/prompt',json.dumps({'prompt':g,'client_id':uuid.uuid4().hex}).encode(),{'Content-Type':'application/json'},timeout=60)
    pid=submit.get('prompt_id')
    if not pid:raise RuntimeError('Batch workflow was not accepted')
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        history=req(base,'/history/'+pid,timeout=30)
        entry=history.get(pid)
        if entry:
            status=entry.get('status',{})
            if status.get('status_str')=='error':raise RuntimeError('Batch GPU execution failed; check ComfyUI log (no serial fallback)')
            if status.get('completed') or status.get('status_str')=='success':
                dest=Path(dest);dest.mkdir(parents=True,exist_ok=True);result={}
                for job,(node,prefix) in outputs.items():
                    try:
                        files=entry.get('outputs',{}).get(node,{}).get('images',[])
                        if len(files)!=1:raise RuntimeError('Unexpected batch output count')
                        f=files[0];name=f.get('filename','')
                        if f.get('type')!='output' or not name.startswith(prefix+'_') or not name.lower().endswith('.png'):raise RuntimeError('Unexpected output identity')
                        data=req(base,'/view?'+urlencode({'filename':name,'subfolder':f.get('subfolder',''),'type':'output'}),timeout=120,binary=True)
                        if len(data)>10*1024**2:raise RuntimeError('PNG too large')
                        data=clean_png(data);path=dest/('caratzon_2d_'+job+'.png');path.write_bytes(data);result[job]=path
                    except Exception:result[job]=None
                return result
        time.sleep(1)
    raise RuntimeError('Batch timeout; check ComfyUI before retry')
