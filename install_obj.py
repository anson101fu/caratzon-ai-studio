"""Add OBJ+MTL ZIP export to an *installed* Caratzon Tennis Bracelet V1.
Run install.py once first if V1 is not already installed.
Backups are placed in .caratzon_backups; secrets are never read or shipped.
"""
from pathlib import Path
import datetime,shutil
R=Path(__file__).resolve().parent
files=[R/'local/bridge.py',R/'functions/api/local3d.js',R/'public/tennis-bracelet.js',R/'public/tennis-bracelet.html',R/'local/tennis_obj.py']
for p in files:
    if not p.exists():raise SystemExit('Missing '+str(p)+'; install original V1 first.')
changes={}
def replace(p,old,new):
    s=changes.get(p,p.read_text(encoding='utf8'))
    if new in s:return
    if s.count(old)!=1:raise SystemExit(f'Version mismatch at {p.relative_to(R)}; nothing changed. Check installed V1.')
    changes[p]=s.replace(old,new,1)

p=R/'local/bridge.py'
replace(p,'import tennis_geometry\n','import tennis_geometry\nimport tennis_obj\n')
replace(p,"        stats=tennis_geometry.generate(params,target)\n", "        stats=tennis_geometry.generate(params,target)\n        package=tennis_obj.export_package(target,target.with_suffix('.zip'))\n")
replace(p,"JOBS[job].update(state='done',file=target,seconds=round(time.monotonic()-JOBS[job]['start'],1),bytes=stats['bytes'])", "JOBS[job].update(state='done',file=target,package=package,seconds=round(time.monotonic()-JOBS[job]['start'],1),bytes=stats['bytes'])")
replace(p,"m=re.fullmatch(r'/(job|file|image-job|image-file)/([a-f0-9]{32})',u.path)", "m=re.fullmatch(r'/(job|file|image-job|image-file|tennis-package)/([a-f0-9]{32})',u.path)")
replace(p,"        if m[1] in ('file','image-file') and (m[1]=='image-file')!=(j.get('kind')=='image'):self.send_json(404,{'error':'JOB_NOT_FOUND'});return", "        if m[1] in ('file','image-file') and (m[1]=='image-file')!=(j.get('kind')=='image'):self.send_json(404,{'error':'JOB_NOT_FOUND'});return\n        if m[1]=='tennis-package' and 'package' not in j and j['state']=='done':self.send_json(404,{'error':'NOT_TENNIS_JOB'});return")
replace(p,"        p=j['file']\n", "        p=j.get('package') if m[1]=='tennis-package' else j['file']\n")
replace(p,"self.send_header('Content-Type','image/png' if j.get('kind')=='image' else 'model/gltf-binary')", "self.send_header('Content-Type','application/zip' if m[1]=='tennis-package' else ('image/png' if j.get('kind')=='image' else 'model/gltf-binary'))")

p=R/'functions/api/local3d.js'
replace(p,"['job','file','image-job','image-file'].includes(action)", "['job','file','image-job','image-file','tennis-package'].includes(action)")
replace(p,"if(path.startsWith('/file/')||path.startsWith('/image-file/'))opts.signal", "if(path.startsWith('/file/')||path.startsWith('/image-file/')||path.startsWith('/tennis-package/'))opts.signal")
replace(p,"if((path.startsWith('/file/')||path.startsWith('/image-file/'))&&r.ok)", "if((path.startsWith('/file/')||path.startsWith('/image-file/')||path.startsWith('/tennis-package/'))&&r.ok)")
replace(p,"'Content-Type':path.startsWith('/image-file/')?'image/png':'model/gltf-binary'", "'Content-Type':path.startsWith('/tennis-package/')?'application/zip':path.startsWith('/image-file/')?'image/png':'model/gltf-binary'")

p=R/'public/tennis-bracelet.js'
replace(p,"if(action==='file'&&r.ok)return r.blob();", "if((action==='file'||action==='tennis-package')&&r.ok)return r.blob();")
replace(p,"let modelUrl = null, currentJob = null;", "let modelUrl = null, currentJob = null, completedJob = null;")
replace(p,"$('generate').disabled=true;$('download').disabled=true;", "$('generate').disabled=true;$('download').disabled=true;$('downloadObj').disabled=true;completedJob=null;")
replace(p,"  modelUrl=URL.createObjectURL(b);$('viewer').src=modelUrl;$('download').disabled=false;", "  modelUrl=URL.createObjectURL(b);$('viewer').src=modelUrl;$('download').disabled=false;completedJob=currentJob;$('downloadObj').disabled=false;")
p=R/'public/tennis-bracelet.js'
new=changes[p]+'''\n$('downloadObj').addEventListener('click',async()=>{\n if(!completedJob)return;\n const btn=$('downloadObj');btn.disabled=true;\n try{\n  status('正在取得 OBJ + MTL ZIP…');\n  const blob=await api('tennis-package','GET',null,completedJob);\n  if(blob.type && !['application/zip','application/octet-stream'].includes(blob.type))throw Error('INVALID_PACKAGE');\n  const url=URL.createObjectURL(blob),a=document.createElement('a');\n  a.href=url;a.download='caratzon_tennis_bracelet_OBJ_MTL.zip';document.body.append(a);a.click();a.remove();\n  setTimeout(()=>URL.revokeObjectURL(url),10000);status('✅ OBJ + MTL 下载完成，请解压到同一个文件夹。');\n }catch(e){status('❌ OBJ 下载失败：'+e.message)}finally{btn.disabled=false}\n});\n'''
changes[p]=new
p=R/'public/tennis-bracelet.html'
replace(p,'<button class="linkbtn" id="download" disabled>下载 GLB</button>', '<button class="linkbtn" id="download" disabled>下载 GLB</button><button class="linkbtn" id="downloadObj" disabled>下载 OBJ + MTL</button>')
replace(p,'<span class="badge">GLB</span>', '<span class="badge">GLB / OBJ + MTL</span>')

root=R/'.caratzon_backups'/('obj_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
for p,s in changes.items():
    dest=root/p.relative_to(R);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
for p,s in changes.items():p.write_text(s,encoding='utf8');print('[UPDATED]',p.relative_to(R))
print('OBJ/MTL patch complete. Backup at',root)
