from pathlib import Path
from datetime import datetime
import shutil, re, sys

ROOT=Path(__file__).resolve().parent
JS=ROOT/'public'/'app.js'
HTML=ROOT/'public'/'index.html'
if not (JS.is_file() and HTML.is_file()):
    sys.exit('ERROR: Put this installer in the caratzon-ai-studio project root, beside public/.')
js=JS.read_text(encoding='utf-8-sig'); html=HTML.read_text(encoding='utf-8-sig')
oldjs,oldhtml=js,html
# Remove the old zodiac option data, which would otherwise try to populate an absent select.
js,n=re.subn(r'^choices\.zodiac=.*?;\s*\n','',js,count=1,flags=re.M)
# Remove the old label updater, which throws TypeError when the label is absent.
js,nlabel=re.subn(r"set\('zodiacLabel',tr\(\['生肖主题（可选）','Chinese zodiac \(optional\)','Китайский зодиак \(необязательно\)'\]\)\);",'',js,count=1)
# Do not access deleted zodiac dropdown in generation validation.
js,nvalidation=re.subn(r"&&\(!\(active==='design'\|\|active==='relief'\)\|\|\$\('zodiac'\)\.value==='auto'\)","",js,count=1)
# Remove zodiac tag rendering to avoid stale selected options leaking into design brief.
js,ntag=re.subn(r",p\.zodiac&&p\.zodiac!=='Any'\?localChoice\('zodiac',p\.zodiac\):''",'',js,count=1)
# Update example text so it no longer suggests Zodiac designs as a mode.
js=js.replace('例如：海洋 自由 要中性D 唔洗要石；或 12生肖 925银。简单说，AI 自动补全。','例如：海洋主题中性风格戒指，925银，不镶宝石。简单说，AI 自动补全。')
# Remove invisible obsolete select; no hidden zodiac left behind.
html,h=re.subn(r'<select id="zodiac" hidden aria-hidden="true" tabindex="-1"><option value="auto" selected>自动 / 不限</option></select>','',html,count=1)
html,h2=re.subn(r'<div class="field"><label id="zodiacLabel" for="zodiac">.*?</label><select id="zodiac"></select></div>','',html,count=1)
# Cache-bust the JS so Cloudflare/browser can't reuse old broken script.
html,count=re.subn(r'app\.js\?v=[^"\s]+','app.js?v=4.3.1-zodiac-fix',html,count=1)
if not count: sys.exit('ERROR: Could not locate app.js script in index.html; no files changed.')
if "set('zodiacLabel'" in js or "$('zodiac')" in js or 'choices.zodiac=' in js:
    sys.exit('ERROR: Old zodiac references remain; no files changed. Send current public/app.js for review.')
if js==oldjs:sys.exit('ERROR: app.js was not updated; no files changed.')
backup=ROOT/'.caratzon_backups'/('zodiac_crash_fix_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
backup.mkdir(parents=True,exist_ok=True)
shutil.copy2(JS,backup/'app.js');shutil.copy2(HTML,backup/'index.html')
JS.write_text(js,encoding='utf-8'); HTML.write_text(html,encoding='utf-8')
print('[OK] public/app.js — removed obsolete zodiac references')
print('[OK] public/index.html — removed hidden zodiac field, cache-busted app.js')
print('[BACKUP]',backup)
print('Next: verify site, then commit only public/app.js and public/index.html.')
