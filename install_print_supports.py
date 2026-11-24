from pathlib import Path
import shutil,datetime
root=Path(__file__).resolve().parent
public=root/'public'
if not (public/'free.js').exists() or not (public/'index.html').exists() or not (public/'3d-export.js').exists():
    raise SystemExit('ERROR: Run installer in caratzon-ai-studio root, with public/free.js, public/index.html, public/3d-export.js present.')
backup=root/'.caratzon_backups'/('supports_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
backup.mkdir(parents=True,exist_ok=True)
def patch(path,fn):
    src=path.read_text('utf-8');dst=fn(src)
    if dst!=src:
        shutil.copy2(path,backup/path.name)
        path.write_text(dst,'utf-8')
        print('[UPDATED]',path.relative_to(root))
    else:print('[UNCHANGED]',path.relative_to(root))
def include(html):
    tag='<script src="3d-print-supports.js?v=1.0" defer></script>'
    if '3d-print-supports.js' not in html:
        assert '</body>' in html, 'Missing HTML body'
        html=html.replace('</body>',tag+'</body>')
    return html
for name in ('index.html','free-studio.html','tennis-bracelet.html'):
    path=public/name
    if path.exists():patch(path,include)
src=(root/'3d-print-supports.js').read_bytes()
(public/'3d-print-supports.js').write_bytes(src)
print('[INSTALLED] public/3d-print-supports.js')
def expose(js):
    if 'CaratzonFreeGetGLB' in js:return js
    needle="$('saveGLB').onclick="
    assert needle in js,'Cannot find free.js GLB handler; no change made'
    return js.replace(needle,"window.CaratzonFreeGetGLB=()=>mesh ? new Blob([glbBytes||exportGLB(mesh)],{type:'model/gltf-binary'}) : null;\n"+needle,1)
patch(public/'free.js',expose)
print('Done. Check Git changes before committing. No Bridge restart required.')
