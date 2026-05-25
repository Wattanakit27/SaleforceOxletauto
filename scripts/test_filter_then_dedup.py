"""ลอง 3 วิธี:
  1. raw (ไม่ dedup เลย) = 2,667
  2. dedup ทั้งหมดก่อน → filter เดือน = 2,552
  3. filter เดือนก่อน → dedup ภายในเดือน = ???  ← user คาด 2,582
"""
import os, sys, django
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
django.setup()

from dashboard.services.google_sheets import fetch_sheet, cell, LEADS_COL as L
from dashboard.services.fetch_dashboard import parse_date, bangkok_now
from dashboard.services.constants import normalize_seller

now = bangkok_now()
print(f"\n=== ทดสอบ 3 วิธี dedup เดือน 5/2026 ===\n")

base = fetch_sheet("leads")

# Method 1: ไม่ dedup เลย
m1 = [r for r in base if (d := parse_date(cell(r, L.received_date))) and d.year == 2026 and d.month == 5]
print(f"1. ไม่ dedup เลย                    = {len(m1)}")

# Method 2: dedup ทั้งหมดก่อน → filter
from dashboard.services.google_sheets import _dedupe_leads_by_code
deduped = _dedupe_leads_by_code(base)
m2 = [r for r in deduped if (d := parse_date(cell(r, L.received_date))) and d.year == 2026 and d.month == 5]
print(f"2. dedup ทั้ง sheet → filter เดือน  = {len(m2)}  (-{len(m1)-len(m2)})")

# Method 3: filter เดือนก่อน → dedup ภายใน month subset
filtered = [r for r in base if (d := parse_date(cell(r, L.received_date))) and d.year == 2026 and d.month == 5]
m3 = _dedupe_leads_by_code(filtered)
print(f"3. filter เดือน → dedup ภายใน      = {len(m3)}  (-{len(m1)-len(m3)})  ← user คาด ~2582")

# per-seller method 3
print(f"\nMethod 3 per-seller:")
c = Counter()
for r in m3:
    s = normalize_seller(cell(r, L.sales_rep)) or "(ว่าง)"
    c[s] += 1
for s, n in c.most_common():
    print(f"  {s:<14} {n}")
print(f"  รวม          = {sum(c.values())}")
