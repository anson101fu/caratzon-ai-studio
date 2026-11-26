"""Run a real local GPU batch test, then optionally enable the proven limit.
Does not start/stop any service, change Cloudflare, or send anything online.
"""
import hashlib,json,socket,subprocess,threading,time,uuid
from pathlib import Path
import batch456
import test_3d as core
ROOT=Path(__file__).resolve().parent
PROMPTS=[
 'Studio product photo of one simple yellow gold wedding band, no gems, white background.',
 'Studio product photo of a pair of silver dangling earrings, turquoise beads, white background.',
 'Studio product photo of a rose gold heart pendant with red gemstone, white background.',
 'Studio product photo of a blue sapphire and white platinum brooch, white background.',
 'Studio product photo of a black onyx signet ring in silver, white background.'
]
def bridge_running():
    try:
        with socket.create_connection(('127.0.0.1',8765),timeout=1):return True
    except OSError:return False

def main():
    if bridge_running():raise RuntimeError('Bridge 8765 is still running. Finish jobs and stop only Bridge before testing.')
    base,stats=core.find_server()
    if not any('4090' in str(d.get('name','')) for d in stats.get('devices',[]) if isinstance(d,dict)):raise RuntimeError('Expected RTX 4090 backend not found')
    q=core.req(base,'/queue',timeout=5)
    if q.get('queue_running') or q.get('queue_pending'):raise RuntimeError('ComfyUI is busy; do not run a second workload')
    if not batch456.available(core.req,base):raise RuntimeError('Batch custom node missing. Install it and restart ComfyUI once.')
    n=int(input('Test simultaneous text images (2, 3, 4 or 5; start at 2): ').strip())
    if n not in (2,3,4,5):raise ValueError('Choose 2–5')
    # Avoid surprising the operator with a previous enabled configuration after a failed new test.
    stamp=ROOT/'BATCH_456_TESTED.json'
    if stamp.exists():stamp.replace(ROOT/('BATCH_456_TESTED.backup-'+str(int(time.time()))+'.json'))
    workflow_file=ROOT/'flux2_text_to_image.json';workflow=json.loads(workflow_file.read_text(encoding='utf-8-sig'))
    folder=ROOT/'BATCH456_TEST_RESULTS'/time.strftime('%Y%m%d-%H%M%S');entries=[(uuid.uuid4().hex,p) for p in PROMPTS[:n]]
    stop=threading.Event();samples=[]
    def monitor():
        while not stop.is_set():
            try:
                raw=subprocess.check_output(['nvidia-smi','--query-gpu=name,memory.used,memory.total','--format=csv,noheader,nounits'],text=True,timeout=5)
                for line in raw.splitlines():
                    name,used,total=line.rsplit(',',2)
                    if '4090' in name:samples.append((int(used),int(total)))
            except Exception:pass
            stop.wait(.7)
    t=threading.Thread(target=monitor,daemon=True);t.start();started=time.monotonic()
    try:results=batch456.run_batch(core.req,base,workflow,entries,folder)
    finally:stop.set();t.join(timeout=6)
    print('Elapsed:',round(time.monotonic()-started,1),'seconds')
    if samples:print('Observed peak VRAM:',max(x[0] for x in samples),'/',samples[-1][1],'MiB (sampled, not a hard peak guarantee)')
    else:print('VRAM telemetry unavailable; not eligible for automatic enable.')
    if any(results.get(j) is None for j,p in entries):raise RuntimeError('One or more batch images failed. No limit enabled.')
    for i,(j,p) in enumerate(entries,1):print(i,p,'\n  ',results[j].name)
    print('Open results and check that each image matches its own prompt:',folder)
    if not samples:raise RuntimeError('No VRAM telemetry. Limit remains 1.')
    peak=max(x[0] for x in samples);total=samples[-1][1]
    if total-peak<1024:raise RuntimeError('Less than 1 GiB observed headroom. Test a smaller batch. Limit remains 1.')
    if input('After checking the separate images, enable this tested text batch limit? Type YES: ').strip()!='YES':print('Not enabled; default limit 1.');return
    data={'enabled':True,'tested_max':n,'workflow_sha256':hashlib.sha256(workflow_file.read_bytes()).hexdigest(),'test_date':time.strftime('%Y-%m-%dT%H:%M:%S'),'observed_peak_mib':peak,'total_mib':total}
    tmp=stamp.with_suffix('.tmp');tmp.write_text(json.dumps(data,indent=2),encoding='utf-8');tmp.replace(stamp)
    print('Enabled tested limit:',n,'Restart Bridge to apply. A two-second collection window precedes one simultaneous sampling batch.')
if __name__=='__main__':
    try:main()
    except Exception as e:print('TEST NOT ENABLED:',e);raise SystemExit(1)
