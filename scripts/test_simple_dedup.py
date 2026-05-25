"""ทดสอบ: dedup 'รวม sheet' อย่างเดียว (ไม่ union monthly tabs)
ควรได้ ~2,582 ตามที่ user คำนวณ
"""
import os, sys, django
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
django.setup()

from dashboard.services.google_sheets import (
    fetch_sheet, _dedupe_leads_by_code, cell, LEADS_COL as L,
)
from dashboard.services.fetch_dashboard import parse_date, bangkok_now
from dashboard.services.constants import normalize_seller

now = bangkok_now()
print(f"\n=== ทดสอบ simple dedup เดือน {now.month}/{now.year} ===\n")

base = fetch_sheet("leads")
print(f"'รวม sheet' raw      = {len(base):>6} แถว")

deduped = _dedupe_leads_by_code(base)
print(f"หลัง dedup by code   = {len(deduped):>6} แถว (-{len(base)-len(deduped)} dup)")

def filter_month(rows, m, y):
    out = []
    for r in rows:
        d = parse_date(cell(r, L.received_date))
        if d and d.month == m and d.year == y:
            out.append(r)
    return out

raw_may = filter_month(base, 5, 2026)
ded_may = filter_month(deduped, 5, 2026)

print(f"\nเฉพาะเดือน 5/{now.year}:")
print(f"  raw 'รวม sheet'   = {len(raw_may)}")
print(f"  หลัง dedup        = {len(ded_may)}  ← ต้องเท่ากับ ~2582 ที่ user คาด")
print(f"  ลดลง              = {len(raw_may) - len(ded_may)} แถว (= code duplicates)")

# Per-seller breakdown หลัง dedup
print(f"\nหลัง dedup — per-seller เดือน 5:")
by_seller = Counter()
for r in ded_may:
    s = normalize_seller(cell(r, L.sales_rep)) or "(ว่าง)"
    by_seller[s] += 1
for s, n in by_seller.most_common():
    print(f"  {s:<14} {n}")
print(f"  รวม          = {sum(by_seller.values())}")
