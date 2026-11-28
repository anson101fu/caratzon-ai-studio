"""Private CTB slicing worker. No printer settings accepted from clients."""
import json, math, struct, subprocess, tempfile, threading, time, uuid, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
CONFIG=ROOT/'CTB_PRIVATE.json'
LOCK=threading.Lock()
JOBS={}
LIMIT=50*1024*1024
def config():
    d=json.loads(CONFIG.read_text(encoding='utf-8-sig'))
    if d.get('enabled') is not True or not d.get('printer'): raise ValueError('CTB_NOT_CONFIGURED')
    for k in ('prusa','uvtools','profile'):
        p=Path(d[k])
        if not p.is_absolute() or not p.is_file():raise ValueError('CTB_NOT_CONFIGURED')
    profile=Path(d['profile']).read_text(encoding='utf-8-sig')
    settings=dict((k.strip(),v.strip()) for line in profile.splitlines() if '=' in line and not line.lstrip().startswith(('#',';')) for k,v in [line.split('=',1)])
    if settings.get('printer_technology','').upper()!='SLA' or settings.get('supports_enable')!='0' or settings.get('pad_enable')!='0' or float(settings.get('support_object_elevation','-1'))!=0:raise ValueError('CTB_PROFILE_REQUIRES_NO_EXTRA_SUPPORTS')
    if d['version'] not in (2,3,4):raise ValueError('CTB_NOT_CONFIGURED')
    return d
def validate(raw):
    if len(raw)<134 or len(raw)>LIMIT:raise ValueError('BAD_STL')
    n=struct.unpack_from('<I',raw,80)[0]
    if not n or 84+50*n!=len(raw):raise ValueError('BAD_STL')
    # Browser geometry is Y-up; rotate to Z-up without changing size.
    data=bytearray(raw)
    lo=[math.inf]*3;hi=[-math.inf]*3
    for i in range(n):
        for j in range(4):
            p=84+i*50+j*12
            x,y,z=struct.unpack_from('<fff',raw,p)
            if not all(math.isfinite(v) and abs(v)<=10000 for v in (x,y,z)):raise ValueError('BAD_STL')
            v=(x,-z,y)
            struct.pack_into('<fff',data,p,*v)
            if j:
                for k in range(3):lo[k]=min(lo[k],v[k]);hi[k]=max(hi[k],v[k])
    if max(hi[k]-lo[k] for k in range(3))>510:raise ValueError('BAD_STL_SIZE')
    return data
def run(job,raw,d):
    try:
        with tempfile.TemporaryDirectory(prefix='czctb-') as folder:
            p=Path(folder); stl=p/'model.stl';sl=p/'model.sl1';ct=p/'model.ctb'
            stl.write_bytes(validate(raw))
            def cmd(args):
                subprocess.run(args,cwd=p,check=True,timeout=240,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            cmd([d['prusa'],'--load',d['profile'],'--export-sla','--output',str(sl),str(stl)])
            if not sl.is_file() or not zipfile.is_zipfile(sl):raise ValueError('SLICER_NO_SL1')
            cmd([d['uvtools'],'convert',str(sl),'ctb',str(ct),'--version',str(d['version'])])
            if not ct.is_file() or not 16<ct.stat().st_size<=100*1024*1024:raise ValueError('CTB_OUTPUT_INVALID')
            with ct.open('rb') as f:
                if f.read(4)!=b'\x19\x00\xfd\x12':raise ValueError('CTB_MAGIC_INVALID')
            cmd([d['uvtools'],'print-properties',str(ct)])
            result=ct.read_bytes()
        with LOCK:JOBS[job].update(state='done',data=result,finished=time.monotonic())
    except Exception as e:
        print('CTB failed:',type(e).__name__,str(e)[:200],flush=True)
        with LOCK:JOBS[job].update(state='error',error='CTB_SLICE_FAILED',finished=time.monotonic())
def cleanup():
    for k in list(JOBS):
        if time.monotonic()-JOBS[k].get('finished',time.monotonic())>600:del JOBS[k]
def post(h):
    if h.path!='/ctb-submit':return False
    try:d=config()
    except Exception:h.send_json(503,{'error':'CTB_NOT_CONFIGURED'});return True
    with LOCK:
        cleanup()
        if any(j['state']=='running' for j in JOBS.values()) or len(JOBS)>=3:
            h.send_json(409,{'error':'CTB_BUSY'});return True
        job=uuid.uuid4().hex;JOBS[job]={'state':'running'}
    try:
        n=int(h.headers.get('Content-Length','0'))
        if not 134<=n<=LIMIT:raise ValueError()
        raw=h.rfile.read(n)
        if len(raw)!=n or 84+50*struct.unpack_from('<I',raw,80)[0]!=n:raise ValueError()
    except Exception:
        with LOCK:JOBS.pop(job,None)
        h.send_json(400,{'error':'BAD_STL'});return True
    threading.Thread(target=run,args=(job,raw,d),daemon=True).start()
    h.send_json(202,{'job':job});return True
def get(h,u):
    if u.path=='/ctb-health':
        try:d=config();h.send_json(200,{'ready':True,'printer':d['printer']})
        except Exception:h.send_json(200,{'ready':False})
        return True
    import re
    m=re.fullmatch(r'/ctb-(job|file)/([a-f0-9]{32})',u.path)
    if not m:return False
    with LOCK:
        cleanup();j=dict(JOBS.get(m[2],{}))
    if not j:h.send_json(404,{'error':'CTB_JOB_NOT_FOUND'});return True
    if m[1]=='job':h.send_json(200,{k:v for k,v in j.items() if k in ('state','error')});return True
    if j['state']!='done':h.send_json(409,{'error':'CTB_NOT_READY'});return True
    b=j['data'];h.send_response(200);h.send_header('Content-Type','application/octet-stream');h.send_header('Content-Length',str(len(b)));h.send_header('Cache-Control','no-store');h.end_headers();h.wfile.write(b)
    with LOCK:JOBS.pop(m[2],None)
    return True
