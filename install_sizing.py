from pathlib import Path
import shutil
from datetime import datetime
ROOT=Path(__file__).resolve().parent
PUB=ROOT/'public'
INDEX=PUB/'index.html'
APP=PUB/'app.js'
for p in (INDEX,APP):
    if not p.is_file(): raise SystemExit(f'Missing: {p}. Put this installer in caratzon-ai-studio project root.')
js=ROOT/'jewelry-sizing.js'
if not js.exists(): raise SystemExit('jewelry-sizing.js missing next to installer')
shutil.copy2(js,PUB/'jewelry-sizing.js')
backup=ROOT/'sizing_backups'/datetime.now().strftime('%Y%m%d_%H%M%S')
backup.mkdir(parents=True,exist_ok=True)
for p in (INDEX,APP):shutil.copy2(p,backup/p.name)
s=INDEX.read_text('utf-8')
if 'jewelry-sizing.js' not in s:
    marker='</body>'
    if marker not in s:raise SystemExit('Cannot find </body> in index.html')
    s=s.replace(marker,'<script src="jewelry-sizing.js?v=1.0" defer></script>\n'+marker,1)
    INDEX.write_text(s,'utf-8')
else: print('index.html already includes jewelry-sizing.js')
s=APP.read_text('utf-8')
needle="'Selected options: '+Object.values(design).join(', ')+'.'"
repl="'Selected options: '+Object.values(design).join(', ')+'.', 'Target dimensions: '+(window.CaratzonJewelrySizing?.getBrief()||'Not specified')+'.'"
if repl in s:print('Local prompt already includes sizing')
elif needle in s:s=s.replace(needle,repl,1)
else:raise SystemExit('app.js changed; cannot locate local prompt. Backups available.')
needle="prompt:$('prompt').value.trim()||'Jewellery design',settings:"
repl="prompt:($('prompt').value.trim()||'Jewellery design')+'\\nTarget dimensions: '+(window.CaratzonJewelrySizing?.getBrief()||'Not specified'),settings:"
if needle in s:s=s.replace(needle,repl,1)
elif repl in s:print('Cloud prompt already includes sizing')
else:raise SystemExit('app.js changed; cannot locate cloud prompt. Backups available.')
APP.write_text(s,'utf-8')
print('[INSTALLED] public/jewelry-sizing.js')
print('[UPDATED] public/index.html')
print('[UPDATED] public/app.js')
print('Backups:',backup)
print('NOTE: Dimensions are design targets only, not validated 3D CAD geometry.')
