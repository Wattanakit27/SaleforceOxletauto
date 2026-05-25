"""นับ emoji ที่ใช้ในแต่ละไฟล์ template"""
import re
import sys
from collections import Counter
from pathlib import Path

# Range emoji ที่ใช้กันบ่อย
EMOJI_RE = re.compile(
    r'[\U0001F300-\U0001F9FF'    # symbols & pictographs
    r'\U0001FA70-\U0001FAFF'     # extended symbols
    r'☀-➿'             # misc + dingbats
    r'✀-➿]'            # dingbats
)

files = [
    'dashboard/templates/dashboard/seller.html',
    'dashboard/templates/dashboard/index.html',
    'dashboard/templates/dashboard/login.html',
    'dashboard/templates/dashboard/magic_link.html',
]

for f in files:
    p = Path(f)
    if not p.exists():
        continue
    text = p.read_text(encoding='utf-8')
    matches = EMOJI_RE.findall(text)
    cnt = Counter(matches)
    print(f"\n=== {f} ({len(matches)} total, {len(cnt)} unique) ===")
    for emo, n in cnt.most_common(30):
        print(f"  {emo} × {n}")
