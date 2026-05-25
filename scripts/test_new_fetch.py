"""ทดสอบ fetch_leads_by_month_tabs() — ควรได้ ~2,585 สำหรับเดือน 5"""
import os, sys, django
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
django.setup()

from dashboard.services.google_sheets import fetch_leads_by_month_tabs, cell, LEADS_COL as L
from dashboard.services.fetch_dashboard import parse_date, bangkok_now
from dashboard.services.constants import normalize_seller

now = bangkok_now()
print(f"\n=== fetch_leads_by_month_tabs() เดือน {now.month}/{now.year} ===\n")

rows = fetch_leads_by_month_tabs()
print(f"รวมทุกเดือน: {len(rows)} แถว")

# Per-month breakdown
mo = Counter()
for r in rows:
    d = parse_date(cell(r, L.received_date))
    if d:
        mo[d.month] += 1
print(f"\nกระจายตามเดือน:")
for m in sorted(mo):
    print(f"  เดือน {m}: {mo[m]}")

# Per-seller for current month
print(f"\nเดือน {now.month} per-seller:")
c = Counter()
for r in rows:
    d = parse_date(cell(r, L.received_date))
    if not d or d.month != now.month or d.year != now.year:
        continue
    s = normalize_seller(cell(r, L.sales_rep)) or "(ว่าง)"
    c[s] += 1
for s, n in c.most_common():
    print(f"  {s:<14} {n}")
print(f"  รวม          = {sum(c.values())}  ← target ~2,582")
