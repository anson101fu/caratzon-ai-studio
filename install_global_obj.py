"""Install global OBJ+MTL exporter to the existing Caratzon public pages.
   Safe by design: backs up changed files, asserts target anchors, idempotent.
   Run from GitHub repo root: python install_global_obj.py
"""
from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(__file__).resolve().parent
HERE = ROOT / '3d-export.js'
DEST = ROOT / 'public'
if not (DEST / 'index.html').is_file() or not (DEST / 'free-studio.html').is_file():
    raise SystemExit('ERROR: place installer in the caratzon-ai-studio repository root')
if not HERE.is_file():
    raise SystemExit('ERROR: 3d-export.js must be beside install_global_obj.py')
backup = ROOT / '.caratzon_backups' / ('global_obj_' + datetime.now().strftime('%Y%m%d_%H%M%S'))

def patch(name, transform):
    path = DEST / name
    original = path.read_text(encoding='utf-8-sig')
    result = transform(original)
    if result == original:
        print('[UNCHANGED]', path.relative_to(ROOT));return
    backup.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup / name)
    path.write_text(result, encoding='utf-8')
    print('[UPDATED]',path.relative_to(ROOT))

def index(s):
    if '3d-export.js?v=2.0' not in s:
        assert '</body>' in s
        s=s.replace('</body>','<script src="3d-export.js?v=2.0" defer></script></body>',1)
    return s

def free_html(s):
    if 'id="saveSTL"' not in s or 'id="saveGLB"' not in s:
        raise RuntimeError('Free Studio button anchors not found')
    if 'id="saveOBJ"' not in s:
        marker='<button class="outline" id="saveSTL" disabled data-l="downloadSTL">下载 STL</button>'
        assert marker in s, 'Unexpected Free Studio HTML layout'
        s=s.replace(marker, marker+'<button class="outline" id="saveOBJ" disabled data-l="downloadOBJ">下载 OBJ + MTL</button>',1)
    if '3d-export.js?v=2.0' not in s:
        anchor='<script src="free.js?v=3.6" defer></script>'
        assert anchor in s, 'Free Studio script anchor not found'
        s=s.replace(anchor,'<script src="3d-export.js?v=2.0" defer></script>'+anchor,1)
    return s

def free_js(s):
    if 'downloadOBJ:' not in s:
        marker="downloadSTL:['下载 STL','Download STL','Скачать STL'],"
        assert marker in s, 'Translation anchor missing'
        s=s.replace(marker,marker+"downloadOBJ:['下载 OBJ + MTL','Download OBJ + MTL','Скачать OBJ + MTL'],",1)
    if "$('saveOBJ').disabled=!mesh;" not in s:
        marker="$('saveSTL').disabled=!mesh;"
        assert marker in s, 'Button update anchor missing'
        s=s.replace(marker,marker+"$('saveOBJ').disabled=!mesh;",1)
    if "$('saveOBJ').onclick" not in s:
        marker="$('saveSTL').onclick=()=>{if(mesh)dl(new Blob([exportSTL(mesh)],{type:'application/octet-stream'}),mesh.name+'.stl')};"
        assert marker in s, 'STL export anchor missing'
        additional="\n$('saveOBJ').onclick=async()=>{if(!mesh)return;const button=$('saveOBJ');button.disabled=true;try{const bytes=glbBytes||exportGLB(mesh);const result=await window.Caratzon3DExport.exportBlob(new Blob([bytes],{type:'model/gltf-binary'}),mesh.name);say(['OBJ + MTL 已下载，坐标单位为毫米','OBJ + MTL downloaded, coordinates in millimetres','OBJ + MTL сохранены, единицы: мм']);}catch(e){say(['OBJ 导出失败：','OBJ export failed: ','Ошибка OBJ: '][['zh','en','ru'].indexOf(lang)]+e.message);}finally{button.disabled=false}};"
        s=s.replace(marker,marker+additional,1)
    return s

shutil.copy2(HERE, DEST / '3d-export.js')
print('[INSTALLED] public/3d-export.js')
patch('index.html',index)
patch('free-studio.html',free_html)
patch('free.js',free_js)
print('READY: GitHub Desktop review public/3d-export.js, public/index.html, public/free-studio.html, public/free.js')
print('Existing Tennis Bracelet GLB + OBJ/MTL backend remains unchanged.')
print('Remote embedded TRELLIS/Space results require downloading GLB and opening it in Free Studio V2.')
print('DO NOT commit PRIVATE_BRIDGE_TOKEN.txt, RESULTS, or .caratzon_backups.')
