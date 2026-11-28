import hashlib, base64, hmac, json, os, re, secrets, tempfile, threading, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
import test_3d as core
import tennis_geometry
import tennis_obj
import quality_ai
import batch456
import ctb457
ROOT=Path(__file__).resolve().parent
TOKEN_FILE=ROOT/'PRIVATE_BRIDGE_TOKEN.txt'
if not TOKEN_FILE.exists(): TOKEN_FILE.write_text(secrets.token_hex(32),encoding='ascii')
TOKEN=TOKEN_FILE.read_text(encoding='ascii').strip()
if not re.fullmatch(r'[0-9a-f]{64}',TOKEN): raise RuntimeError('Invalid bridge token; remove PRIVATE_BRIDGE_TOKEN.txt and restart.')
LOCK=threading.Lock(); JOBS={}; STARTS=0
MAX_STARTS_FILE=ROOT/'MAX_3D_JOBS.txt'
MAX_STARTS=10
MAX_ACTIVE=5
# No waiting queue. Each explicitly provisioned ComfyUI backend has one slot.
# Default is the single existing RTX 4090 backend. Extra backends must be
# provisioned and stress-tested separately; never start extra GPU processes here.
BACKENDS=[]
RESERVED={}
BATCH_LIMIT=1
BATCH_OPEN=None
BATCH_WINDOW=2.0

def active_count():
    return len(RESERVED)

def reserve(kind):
    # Called with LOCK held. QA/3D/tennis are exclusive to avoid memory overlap.
    if len(RESERVED)>=MAX_ACTIVE:return None
    if any(k=='batch_text' for _,k in RESERVED.values()):return None
    if kind!='image' and RESERVED:return None
    if any(k!='image' for _,k in RESERVED.values()):return None
    candidates=BACKENDS if kind=='image' else [BASE]
    for url in candidates:
        if any(u==url for u,_ in RESERVED.values()):continue
        try:
            q=core.req(url,'/queue',timeout=3)
            if q.get('queue_running') or q.get('queue_pending'):continue
        except Exception:continue
        return url
    return None

def launch(fn,args,job,url,kind):
    RESERVED[job]=(url,kind)
    JOBS[job]['queued']=False
    def runner():
        try:
            fn(*args,backend=url) if kind=='image' else fn(*args)
        except Exception as e:
            with LOCK:
                JOBS[job].update(state='error',error='EXECUTION_FAILED')
                if manifest(job):record(job,{'state':'error','error':'EXECUTION_FAILED'})
            print('Job failed:',type(e).__name__,flush=True)
        finally:
            with LOCK:RESERVED.pop(job,None)
    threading.Thread(target=runner,daemon=True).start()

def batch_capacity():
    if BATCH_LIMIT<=1:return len(BACKENDS)
    if not RESERVED:return BATCH_LIMIT
    if BATCH_OPEN is not None and time.monotonic()<BATCH_OPEN['deadline']:
        return BATCH_LIMIT
    return 0

def batch_offer(job,prompt):
    # Caller holds LOCK. Collect briefly into one GPU execution, not a serial queue.
    global BATCH_OPEN
    if BATCH_LIMIT<=1:return False
    if BATCH_OPEN is None:
        if RESERVED or reserve('image')!=BASE:return False
        group={'deadline':time.monotonic()+BATCH_WINDOW,'entries':[], 'event':threading.Event()}
        BATCH_OPEN=group
        first=True
    else:
        group=BATCH_OPEN;first=False
        if time.monotonic()>=group['deadline'] or len(group['entries'])>=BATCH_LIMIT:return False
    group['entries'].append((job,prompt))
    RESERVED[job]=(BASE,'batch_text')
    JOBS[job]={'state':'running','kind':'image','start':time.monotonic(),'phase':'collecting','queued':False}
    if len(group['entries'])>=BATCH_LIMIT:group['event'].set()
    if first:threading.Thread(target=batch_runner,args=(group,),daemon=True).start()
    return True

def batch_runner(group):
    global BATCH_OPEN
    group['event'].wait(max(0,group['deadline']-time.monotonic()))
    with LOCK:
        if BATCH_OPEN is group:BATCH_OPEN=None
        entries=list(group['entries'])
        for job,_ in entries:JOBS[job].update(phase='running',start=time.monotonic())
    try:
        if len(entries)==1:
            job,prompt=entries[0];work_image(job,prompt,None,None,backend=BASE)
        else:
            print('BATCH456 sampling',len(entries),'independent text prompts',flush=True)
            workflow=json.loads((ROOT/IMAGE_WORKFLOWS['text']).read_text(encoding='utf-8-sig'))
            results=batch456.run_batch(core.req,BASE,workflow,entries,ROOT/'RESULTS')
            with LOCK:
                for job,_ in entries:
                    target=results.get(job)
                    if target is None:JOBS[job].update(state='error',phase='error',error='BATCH_OUTPUT_FAILED')
                    else:JOBS[job].update(state='done',phase='done',file=target,seconds=round(time.monotonic()-JOBS[job]['start'],1),bytes=target.stat().st_size)
            print('BATCH456 complete',len(entries),flush=True)
    except Exception as e:
        print('BATCH456 failed:',type(e).__name__,str(e)[:250],flush=True)
        with LOCK:
            for job,_ in entries:JOBS[job].update(state='error',phase='error',error='BATCH_GPU_FAILED')
    finally:
        with LOCK:
            for job,_ in entries:RESERVED.pop(job,None)


def load_batch_limit():
    path=ROOT/'BATCH_456_TESTED.json'
    if not path.exists() or len(BACKENDS)!=1:return 1
    try:
        data=json.loads(path.read_text(encoding='utf-8-sig'));n=data['tested_max']
        if type(n)!=int or not 2<=n<=5 or data.get('enabled') is not True:raise ValueError()
        fp=hashlib.sha256((ROOT/IMAGE_WORKFLOWS['text']).read_bytes()).hexdigest()
        if data.get('workflow_sha256')!=fp or not batch456.available(core.req,BASE):raise ValueError()
        return n
    except Exception:
        print('Batch disabled: run the actual GPU test and verify the custom node first.',flush=True);return 1

def load_backends():
    out=[BASE]
    cfg=ROOT/'IMAGE_BACKENDS_456.json'
    if cfg.exists():
        data=json.loads(cfg.read_text(encoding='utf-8-sig'))
        for url in data.get('additional_backends',[]):
            if not isinstance(url,str) or not re.fullmatch(r'http://127\.0\.0\.1:[0-9]{1,5}',url):raise ValueError('Only explicit loopback HTTP backends allowed')
            if not 1<=int(url.rsplit(':',1)[1])<=65535:raise ValueError('Invalid port')
            if url not in out:out.append(url)
        if len(out)>MAX_ACTIVE:raise ValueError('At most five backends')
    return out


def session_limit():
    # Called under LOCK by requests. Invalid edits retain the last valid limit.
    global MAX_STARTS
    try:
        value=int(MAX_STARTS_FILE.read_text(encoding='utf-8-sig').strip())
        if 1<=value<=1000: MAX_STARTS=value
    except (OSError, ValueError): pass
    return MAX_STARTS
BASE=None
TRANSFER=ROOT/'RESULTS'/'transfer444'
TRANSFER.mkdir(parents=True,exist_ok=True)
CHUNK=256*1024
MAX_BODY=12*1024**2

def atomic(path,data):
    tmp=path.with_name(path.name+'.tmp');tmp.write_bytes(data);os.replace(tmp,path)

def manifest(job):
    p=TRANSFER/job/'job.json'
    return json.loads(p.read_text()) if p.exists() else None

def record(job,data):
    atomic(TRANSFER/job/'job.json',json.dumps(data).encode())

def durable_work(job,image,ext,engine,quality):
    work(job,image,ext,engine,quality)
    with LOCK:
        j=JOBS[job]
        if j['state']=='done':
            try:
                target=TRANSFER/job/'result.glb'
                atomic(target,j['file'].read_bytes())
                record(job,{'state':'done','bytes':target.stat().st_size,'seconds':j['seconds'],'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
            except Exception:record(job,{'state':'error','error':'RESULT_SAVE_FAILED'})
        else:record(job,{'state':'error','error':'GENERATION_FAILED'})


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

def run_image(job,prompt,image=None,ext=None,backend=None):
    backend=backend or BASE
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
            uploadname=core.upload(backend,path,job)
        workflow['76']['inputs']['image']=uploadname
    submit=core.req(backend,'/prompt',json.dumps({'prompt':workflow,'client_id':uuid.uuid4().hex}).encode(),{'Content-Type':'application/json'},timeout=60)
    pid=submit.get('prompt_id')
    if not pid: raise RuntimeError('ComfyUI did not accept image job')
    end=time.monotonic()+900
    while time.monotonic()<end:
        history=core.req(backend,'/history/'+pid,timeout=30)
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
                    imagebytes=core.req(backend,url,timeout=120,binary=True)
                    if not imagebytes.startswith(b'\x89PNG\r\n\x1a\n') or len(imagebytes)>IMAGE_LIMIT:raise RuntimeError('Invalid image output')
                    folder=ROOT/'RESULTS';folder.mkdir(exist_ok=True)
                    path=folder/('caratzon_2d_'+job+'.png');path.write_bytes(imagebytes)
                    return path
                raise RuntimeError('No PNG image returned by SaveImage')
        time.sleep(1)
    raise RuntimeError('Image generation timeout')

def work_image(job,prompt,image,ext,backend=None):
    try:
        target=run_image(job,prompt,image,ext,backend)
        with LOCK:JOBS[job].update(state='done',file=target,seconds=round(time.monotonic()-JOBS[job]['start'],1),bytes=target.stat().st_size,kind='image')
        print('IMAGE DONE:',job,flush=True)
    except Exception as e:
        print('IMAGE FAILED:',job,str(e),flush=True)
        with LOCK:JOBS[job].update(state='error',error='IMAGE_FAILED')

def check_comfy_queue():
    q=core.req(BASE,'/queue',timeout=3)
    return bool(q.get('queue_running') or q.get('queue_pending'))

def work_tennis(job,params):
    try:
        target=ROOT/'RESULTS'/('caratzon_tennis_'+job+'.glb')
        stats=tennis_geometry.generate(params,target)
        package=tennis_obj.export_package(target,target.with_suffix('.zip'))
        if target.stat().st_size>80*1024**2:raise RuntimeError('GLB exceeds 80 MB')
        with LOCK:
            JOBS[job].update(state='done',file=target,package=package,seconds=round(time.monotonic()-JOBS[job]['start'],1),bytes=stats['bytes'])
        print('TENNIS DONE:',job,'stones:',stats['stone_count'],flush=True)
    except Exception as e:
        print('TENNIS FAILED:',job,str(e),flush=True)
        with LOCK:JOBS[job].update(state='error',error='MODEL_FAILED')

class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup();self.connection.settimeout(25)
    def log_message(self,*args): pass
    def send_json(self,status,data):
        try:
            b=json.dumps(data).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
        except (OSError,ConnectionError):pass
    def allowed(self):
        if not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+TOKEN):
            self.send_json(401,{'error':'UNAUTHORIZED'});return False
        return True
    def transfer_get(self,u):
        m=re.fullmatch(r'/transfer/(status|chunk)/([a-f0-9]{32})(?:/([0-9]{1,4}))?',u.path)
        if not m:return False
        action,job,index=m.groups()
        with LOCK:
            d=manifest(job)
            if d and d['state']=='running' and job not in JOBS:d={'state':'error','error':'BRIDGE_RESTARTED_NO_AUTO_REPLAY'}
            if action=='status':
                if d and d['state']=='running':d={**d,'elapsed':int(time.monotonic()-JOBS[job]['start']),'queued':JOBS[job].get('queued',False)}
                self.send_json(200,d or {'state':'uploading','received':[int(x.name[4:]) for x in (TRANSFER/job).glob('part*') if re.fullmatch(r'part[0-9]+',x.name)]});return True
            if not d or d['state']!='done' or index is None:self.send_json(409,{'error':'NOT_READY'});return True
            offset=int(index)*CHUNK
            if offset>=d['bytes']:self.send_json(416,{'error':'BAD_RANGE'});return True
            with (TRANSFER/job/'result.glb').open('rb') as f:f.seek(offset);b=f.read(CHUNK)
        self.send_json(200,{'data':base64.b64encode(b).decode(),'sha256':hashlib.sha256(b).hexdigest()});return True
    def transfer_post(self):
        global STARTS
        m=re.fullmatch(r'/transfer/(upload|commit)/([a-f0-9]{32})(?:/([0-9]{1,3}))?',self.path)
        if not m:return False
        action,job,index=m.groups()
        try:
            n=int(self.headers.get('Content-Length','0'))
            if not 0<n<=400000:raise ValueError()
            raw=self.rfile.read(n)
            if len(raw)!=n:raise ValueError()
            d=json.loads(raw)
            folder=TRANSFER/job
            with LOCK:
                existing=manifest(job)
                if existing:self.send_json(200,{'job':job,'state':existing['state']});return True
                if not folder.exists() and sum(1 for _ in TRANSFER.iterdir())>=1000:self.send_json(507,{'error':'TRANSFER_STORAGE_LIMIT'});return True
                folder.mkdir(exist_ok=True)
                if action=='upload':
                    if index is None or int(index)>=48:raise ValueError()
                    b=base64.b64decode(d['data'],validate=True)
                    if not 0<len(b)<=CHUNK or hashlib.sha256(b).hexdigest()!=d['sha256']:raise ValueError()
                    path=folder/('part'+str(int(index)))
                    if path.exists() and path.read_bytes()!=b:self.send_json(409,{'error':'CHUNK_CONFLICT'});return True
                    atomic(path,b);self.send_json(200,{'ok':True});return True
                count=d['count'];size=d['size']
                if type(count)!=int or type(size)!=int or not 0<size<=MAX_BODY or count!=(size+CHUNK-1)//CHUNK:raise ValueError()
                parts=[(folder/('part'+str(i))).read_bytes() for i in range(count)]
                raw=b''.join(parts)
                if len(raw)!=size or hashlib.sha256(raw).hexdigest()!=d['sha256']:raise ValueError()
                data=json.loads(raw);engine=data['engine'];quality=data['quality']
                match=re.fullmatch(r'data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)',data['image'])
                if not match or data.get('consent') is not True or engine not in ('pixal','trellis') or quality not in core.PRESETS:raise ValueError()
                image=base64.b64decode(match[2],validate=True);ext={'png':'.png','jpeg':'.jpg','webp':'.webp'}[match[1]]
                if not 0<len(image)<=core.MAX_IMAGE or not ((ext=='.png' and image.startswith(b'\x89PNG\r\n\x1a\n')) or (ext=='.jpg' and image.startswith(b'\xff\xd8\xff')) or (ext=='.webp' and image[:4]==b'RIFF' and image[8:12]==b'WEBP')):raise ValueError()
                if STARTS>=session_limit():self.send_json(429,{'error':'SESSION_LIMIT'});return True
                url=reserve('3d')
                if url is None:self.send_json(409,{'error':'BUSY'});return True
                try:
                    check_comfy_queue()
                except Exception:self.send_json(503,{'error':'COMFY_OFFLINE'});return True
                record(job,{'state':'running'});JOBS[job]={'state':'running','start':time.monotonic()};STARTS+=1
                for i in range(count):(folder/('part'+str(i))).unlink(missing_ok=True)
                launch(durable_work,(job,image,ext,engine,quality),job,url,'3d')
                self.send_json(202,{'job':job,'state':'running'});return True
        except (ValueError,KeyError,TypeError,OSError):self.send_json(400,{'error':'BAD_TRANSFER_OR_INCOMPLETE'});return True
    def do_GET(self):
        if not self.allowed():return
        u=urlsplit(self.path)
        if ctb457.get(self,u):return
        if self.transfer_get(u):return
        qa=re.fullmatch(r'/qa-job/([a-f0-9]{32})',u.path)
        if qa:
            with LOCK: j=dict(JOBS.get(qa[1],{}))
            if j.get('kind')!='qa':self.send_json(404,{'error':'QA_JOB_NOT_FOUND'});return
            self.send_json(200,{'state':j['state'],'queued':j.get('queued',False),'result':j.get('result')});return
        if u.path=='/health':
            try:
                q=core.req(BASE,'/queue',timeout=3)
                with LOCK:
                    active=active_count(); capacity=batch_capacity(); busy=active>=capacity or any(k not in ('image','batch_text') for _,k in RESERVED.values()); limit=session_limit(); remaining=max(0,limit-STARTS)
                self.send_json(200,{'build':'4.1','transfer444':True,'qualities':['fast','hd','ultra'],'online':True,'busy':busy,'active_jobs':active,'max_active_jobs':max(BATCH_LIMIT,len(BACKENDS)),'execution_mode':'text-batch-window' if BATCH_LIMIT>1 else 'independent-backends-no-queue','max_image_slots':max(BATCH_LIMIT,len(BACKENDS)),'batch_text_limit':BATCH_LIMIT,'batch_collecting':BATCH_OPEN is not None,'batch_window_seconds':BATCH_WINDOW if BATCH_LIMIT>1 else 0,'remaining':remaining,'limit':limit,'used':STARTS,'image_ready':all((ROOT/n).exists() for n in IMAGE_WORKFLOWS.values())})
            except Exception:self.send_json(503,{'error':'COMFY_OFFLINE'})
            return
        m=re.fullmatch(r'/(job|file|image-job|image-file|tennis-package)/([a-f0-9]{32})',u.path)
        if not m:self.send_json(404,{'error':'NOT_FOUND'});return
        with LOCK: j=dict(JOBS.get(m[2],{}))
        if not j or j.get('kind')=='qa':self.send_json(404,{'error':'JOB_NOT_FOUND'});return
        if m[1] in ('job','image-job') and (m[1]=='image-job')!=(j.get('kind')=='image'):self.send_json(404,{'error':'JOB_NOT_FOUND'});return
        if m[1] in ('file','image-file') and (m[1]=='image-file')!=(j.get('kind')=='image'):self.send_json(404,{'error':'JOB_NOT_FOUND'});return
        if m[1]=='tennis-package' and 'package' not in j and j['state']=='done':self.send_json(404,{'error':'NOT_TENNIS_JOB'});return
        if m[1] in ('job','image-job'):self.send_json(200,{'state':j['state'],'elapsed':int(time.monotonic()-j['start']),'queued':j.get('queued',False),'phase':j.get('phase'),'error':j.get('error'),'seconds':j.get('seconds'),'bytes':j.get('bytes')});return
        if j['state']!='done':self.send_json(409,{'error':'NOT_READY'});return
        p=j.get('package') if m[1]=='tennis-package' else j['file']
        try:
            with p.open('rb') as f:
                self.send_response(200);self.send_header('Content-Type','application/zip' if m[1]=='tennis-package' else ('image/png' if j.get('kind')=='image' else 'model/gltf-binary'));self.send_header('Content-Length',str(p.stat().st_size));self.send_header('Cache-Control','no-store');self.end_headers()
                while chunk:=f.read(65536):self.wfile.write(chunk)
        except (OSError,ConnectionError):pass
    def do_POST(self):
        global STARTS
        if not self.allowed():return
        if ctb457.post(self):return
        if self.transfer_post():return
        if self.path=='/qa-submit':
            try:
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<=6*1024**2:raise ValueError()
                d=json.loads(self.rfile.read(n))
            except Exception:self.send_json(400,{'error':'BAD_QA_INPUT'});return
            with LOCK:
                url=reserve('qa')
                if url is None:self.send_json(409,{'error':'BUSY'});return
                try:
                    check_comfy_queue()
                except Exception:self.send_json(503,{'error':'COMFY_OFFLINE'});return
                job=uuid.uuid4().hex;JOBS[job]={'state':'running','kind':'qa','start':time.monotonic()}
                def review():
                    try: result=quality_ai.evaluate(d)
                    except Exception as e:
                        print('Quality check unavailable:',type(e).__name__,flush=True)
                        result={'status':'review','issues':['Local vision check unavailable; verify Ollama, model and GPU memory.']}
                    with LOCK:JOBS[job].update(state='done',result=result)
                launch(review,(),job,url,'qa')
            self.send_json(202,{'job':job});return
        if self.path=='/tennis-submit':
            try:
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<=4096:raise ValueError()
                d=json.loads(self.rfile.read(n))
                params={k:d[k] for k in ('length_mm','stone_mm','shape','metal','clasp')}
                if not 130<=float(params['length_mm'])<=230 or not 1.5<=float(params['stone_mm'])<=5:raise ValueError()
                if params['shape'] not in ('round','square') or params['metal'] not in ('silver','gold','rose') or params['clasp'] not in ('box','lobster'):raise ValueError()
            except (ValueError,KeyError,TypeError,OverflowError):self.send_json(400,{'error':'BAD_BRACELET_PARAMS'});return
            with LOCK:
                if STARTS>=session_limit():self.send_json(429,{'error':'SESSION_LIMIT'});return
                url=reserve('tennis')
                if url is None:self.send_json(409,{'error':'BUSY'});return
                job=uuid.uuid4().hex
                JOBS[job]={'state':'running','start':time.monotonic()}
                STARTS+=1
                launch(work_tennis,(job,params),job,url,'tennis')
            self.send_json(202,{'job':job});return
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
                if not (ROOT/IMAGE_WORKFLOWS[mode]).exists():self.send_json(503,{'error':'IMAGE_WORKFLOW_MISSING'});return
                if mode=='text' and BATCH_LIMIT>1:
                    job=uuid.uuid4().hex
                    if not batch_offer(job,prompt):self.send_json(409,{'error':'BUSY'});return
                    STARTS+=1
                    self.send_json(202,{'job':job,'phase':'collecting'});return
                url=reserve('image')
                if url is None:self.send_json(409,{'error':'BUSY'});return
                job=uuid.uuid4().hex
                JOBS[job]={'state':'running','kind':'image','start':time.monotonic()}
                STARTS+=1
                launch(work_image,(job,prompt,image,ext),job,url,'image')
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
            url=reserve('3d')
            if url is None:self.send_json(409,{'error':'BUSY'});return
            try:
                q=core.req(BASE,'/queue',timeout=3)
                
            except Exception:self.send_json(503,{'error':'COMFY_OFFLINE'});return
            job=uuid.uuid4().hex;JOBS[job]={'state':'running','start':time.monotonic()};STARTS+=1
            launch(work,(job,image,ext,engine,quality),job,url,'3d')
        self.send_json(202,{'job':job})

if __name__=='__main__':
    BASE,s=core.find_server()
    if not any('4090' in str(d.get('name','')) for d in s.get('devices',[]) if isinstance(d,dict)):raise RuntimeError('RTX 4090 not detected')
    BACKENDS=load_backends()
    BATCH_LIMIT=load_batch_limit()
    print('CARATZON V4.5.7 PRIVATE BRIDGE\nComfyUI:',BASE,'\nBridge: http://127.0.0.1:8765\nPrivate token file:',TOKEN_FILE,'\n',session_limit(),'jobs per session; edit MAX_3D_JOBS.txt to change. No waiting queue; image slots: '+str(len(BACKENDS))+'. Keep this window open.\nDo NOT share the token or tunnel URL publicly.',flush=True)
    print('Batch text limit:',BATCH_LIMIT,'(brief collection only, no serial fallback)',flush=True)
    ThreadingHTTPServer(('127.0.0.1',8765),Handler).serve_forever()
