"""CARATZON Tennis Bracelet V1 additive installation.
Run from project root after extracting this ZIP into that root.
Makes timestamped backups of edited files; keeps all existing AI/3D routes.
"""
import datetime, os, shutil, subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent
PATCHES={}

def patch(filepath,old,new):
    text=PATCHES.get(filepath)
    if text is None:text=filepath.read_text(encoding='utf-8')
    if new in text:
        print('[SKIP] already patched:',filepath.relative_to(ROOT));return
    if text.count(old)!=1:
        raise RuntimeError('Expected exact patch anchor not found in '+str(filepath)+'; original files unchanged. Do not force. Update installer for your current version.')
    PATCHES[filepath]=text.replace(old,new,1)

bridge=ROOT/'local'/'bridge.py'
proxy=ROOT/'functions'/'api'/'local3d.js'
index=ROOT/'public'/'index.html'
for p in [bridge,proxy,index,ROOT/'local'/'tennis_geometry.py',ROOT/'public'/'tennis-bracelet.html',ROOT/'public'/'tennis-bracelet.js']:
    if not p.exists():raise SystemExit('Missing required file: '+str(p))

patch(index,'<nav id="tools"></nav>', '<nav id="tools"></nav><a href="tennis-bracelet.html" class="nav" style="display:flex;gap:12px;text-decoration:none;color:#e4ca93;border:1px solid #6a5938;margin:8px 0 18px;padding:12px;border-radius:8px"><span>◇</span><span>网球手链专用 3D / Tennis Bracelet</span></a>')

patch(proxy,"  if(u.searchParams.get('action')==='image-submit'){", """  if(u.searchParams.get('action')==='tennis-submit'){
   if(d?.consent!==true||typeof d?.length_mm!=='number'||d.length_mm<130||d.length_mm>230||typeof d?.stone_mm!=='number'||d.stone_mm<1.5||d.stone_mm>5||!['round','square'].includes(d.shape)||!['silver','gold','rose'].includes(d.metal)||!['box','lobster'].includes(d.clasp))return json({error:'BAD_BRACELET_PARAMS'},400);
   path='/tennis-submit';opts.headers['Content-Type']='application/json';opts.body=JSON.stringify({length_mm:d.length_mm,stone_mm:d.stone_mm,shape:d.shape,metal:d.metal,clasp:d.clasp});
  }else if(u.searchParams.get('action')==='image-submit'){""")

patch(bridge,'import test_3d as core\n','import test_3d as core\nimport tennis_geometry\n')
patch(bridge,'class Handler(BaseHTTPRequestHandler):', '''def work_tennis(job,params):
    try:
        target=ROOT/'RESULTS'/('caratzon_tennis_'+job+'.glb')
        stats=tennis_geometry.generate(params,target)
        if target.stat().st_size>80*1024**2:raise RuntimeError('GLB exceeds 80 MB')
        with LOCK:
            JOBS[job].update(state='done',file=target,seconds=round(time.monotonic()-JOBS[job]['start'],1),bytes=stats['bytes'])
        print('TENNIS DONE:',job,'stones:',stats['stone_count'],flush=True)
    except Exception as e:
        print('TENNIS FAILED:',job,str(e),flush=True)
        with LOCK:JOBS[job].update(state='error',error='MODEL_FAILED')

class Handler(BaseHTTPRequestHandler):''')
patch(bridge,"        if self.path=='/image-submit':", '''        if self.path=='/tennis-submit':
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
                if any(j['state']=='running' for j in JOBS.values()):self.send_json(409,{'error':'BUSY'});return
                job=uuid.uuid4().hex
                JOBS[job]={'state':'running','start':time.monotonic()}
                STARTS+=1
                threading.Thread(target=work_tennis,args=(job,params),daemon=True).start()
            self.send_json(202,{'job':job});return
        if self.path=='/image-submit':''')

gitignore=ROOT/'.gitignore'; gi=gitignore.read_text(encoding='utf-8') if gitignore.exists() else ''
lines=['local/PRIVATE_BRIDGE_TOKEN.txt','local/RESULTS/','local/MAX_3D_JOBS.txt','.caratzon_backups/','local/test_bracelet.glb']
new_gi=gi+('' if not gi or gi.endswith('\n') else '\n')+''.join(v+'\n' for v in lines if v not in gi.splitlines())
if new_gi!=gi:PATCHES[gitignore]=new_gi

backup_root=ROOT/'.caratzon_backups'/datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
backup_root.mkdir(parents=True,exist_ok=True)
for p,new in PATCHES.items():
    if p.exists():
        dst=backup_root/p.relative_to(ROOT);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst)
for p,new in PATCHES.items():
    p.write_text(new,encoding='utf-8')
    print('[OK]',p.relative_to(ROOT))
print('\nInstallation complete. Backups:',backup_root)
print('IMPORTANT: .gitignore does not untrack previously committed secrets.')
try:
    r=subprocess.run(['git','ls-files','--error-unmatch','local/PRIVATE_BRIDGE_TOKEN.txt'],cwd=ROOT,capture_output=True,text=True)
    if r.returncode==0:print('SECURITY WARNING: Git already tracks PRIVATE_BRIDGE_TOKEN.txt. STOP pushing; untrack and rotate the secret.')
except OSError:pass
print('Restart bridge.py. Commit only safe front-end/API/geometry files. Do not commit private credentials.')
