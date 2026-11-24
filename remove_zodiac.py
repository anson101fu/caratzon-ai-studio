from pathlib import Path
import re, shutil, datetime
root=Path(__file__).resolve().parent
# script is designed to be copied into project root
html=root/'public'/'index.html'
if not html.exists():
    raise SystemExit('找不到 public/index.html，請將此檔放在 caratzon-ai-studio 主資料夾再執行。')
s=html.read_text(encoding='utf-8')
pattern=r'<div class="field"><label id="zodiacLabel" for="zodiac">[^<]*</label><select id="zodiac"></select></div>'
replacement='<select id="zodiac" hidden aria-hidden="true" tabindex="-1"><option value="auto" selected>自动 / 不限</option></select>'
new,n=re.subn(pattern,replacement,s,count=1)
if n==0:
    if 'id="zodiac" hidden' in s:
        print('生肖欄位已隱藏，無需重複修改。')
    else:
        raise SystemExit('找不到預期生肖欄位，為免損壞網站，沒有修改。')
else:
    backup=root / 'zodiac_backup_index.html'
    shutil.copy2(html,backup)
    html.write_text(new,encoding='utf-8')
    print('已更新 public/index.html；備份：zodiac_backup_index.html')
print('只需要 Commit / Push public/index.html；請勿上傳 PRIVATE_BRIDGE_TOKEN.txt。')
