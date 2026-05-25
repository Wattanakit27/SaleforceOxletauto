"""ตรวจ lead เดือนนี้ — แยกตาม seller + Code prefix
ใช้: python scripts/check_leads_this_month.py
"""
import os
import sys
import django
from collections import Counter, defaultdict
from pathlib import Path

# Bootstrap Django
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
django.setup()

from dashboard.services.google_sheets import fetch_leads_dedup, cell, LEADS_COL as L
from dashboard.services.fetch_dashboard import (
    parse_date, is_this_year, is_skipped, bangkok_now,
)
from dashboard.services.constants import normalize_seller, ALL_SELLERS

now = bangkok_now()
cur_year = now.year
cur_month = now.month
print(f"\n=== ตรวจ Lead เดือน {cur_month}/{cur_year} (วันนี้: {now.date()}) ===\n")

raw = fetch_leads_dedup()
print(f"raw_leads (dedup แล้ว): {len(raw)} แถว")

# Bucket leads
this_month = []
junk_this_month = []
bad_date = []
no_date = []
prev_months = Counter()

for r in raw:
    date_str = cell(r, L.received_date)
    if not date_str:
        no_date.append(r)
        continue
    d = parse_date(date_str)
    if not d:
        bad_date.append((date_str, cell(r, L.lead_code)))
        continue
    if d.year != cur_year:
        continue
    if d.month != cur_month:
        prev_months[d.month] += 1
        continue
    admin_st = cell(r, L.admin_status)
    sales_st = cell(r, L.sales_status)
    if is_skipped(admin_st) or is_skipped(sales_st):
        junk_this_month.append(r)
    else:
        this_month.append(r)

print(f"\n📅 เดือน {cur_month}/{cur_year}:")
print(f"  - active (ไม่ junk): {len(this_month)} เคส")
print(f"  - junk (คืน/ยกเลิก/จ่ายใหม่/ฯลฯ): {len(junk_this_month)} เคส")
print(f"  - รวมทั้งหมด: {len(this_month) + len(junk_this_month)} เคส")

print(f"\n📅 เดือนอื่นของปี {cur_year}:")
for m in sorted(prev_months):
    print(f"  - เดือน {m}: {prev_months[m]} เคส")

print(f"\n⚠️ ข้อมูลผิด:")
print(f"  - no date (ไม่มีวันที่): {len(no_date)} เคส")
print(f"  - bad date (parse ไม่ได้): {len(bad_date)} เคส")
if bad_date[:5]:
    for ds, code in bad_date[:5]:
        print(f"      ตัวอย่าง: date={ds!r}, code={code!r}")

# วิเคราะห์ Code prefix (เพื่อดูว่า reset ทุกเดือนจริงไหม)
print(f"\n🔑 Code prefix เดือนนี้ (เพื่อดูว่า reset ใหม่):")
prefixes_this_month = Counter()
sample_codes_this_month = []
for r in this_month + junk_this_month:
    code = cell(r, L.lead_code).strip()
    if code:
        # หา prefix = ตัวอักษร + ตัวเลข 2 ตัวแรก เช่น "L25-001" → "L25-"
        import re
        m = re.match(r'^([A-Z]+\d*[-/]?)', code, re.IGNORECASE)
        prefix = m.group(1).upper() if m else code[:5].upper()
        prefixes_this_month[prefix] += 1
        if len(sample_codes_this_month) < 8:
            sample_codes_this_month.append(code)
print(f"  Prefix breakdown:")
for p, n in prefixes_this_month.most_common(10):
    print(f"    {p!r:20} {n} เคส")
print(f"  ตัวอย่าง code: {sample_codes_this_month}")

# Breakdown by seller (เดือนนี้, active only)
print(f"\n👤 Active leads เดือน {cur_month} แยกตามเซลล์ (ไม่รวม junk):")
seller_counts = Counter()
seller_junk_counts = Counter()
for r in this_month:
    seller = normalize_seller(cell(r, L.sales_rep)) or "(ไม่ระบุ)"
    seller_counts[seller] += 1
for r in junk_this_month:
    seller = normalize_seller(cell(r, L.sales_rep)) or "(ไม่ระบุ)"
    seller_junk_counts[seller] += 1

# Sort by total leads
all_sellers = set(seller_counts) | set(seller_junk_counts)
rows = []
for s in all_sellers:
    a = seller_counts.get(s, 0)
    j = seller_junk_counts.get(s, 0)
    rows.append((s, a, j, a + j))
rows.sort(key=lambda x: -x[3])

print(f"{'เซลล์':<14} {'active':>8} {'junk':>8} {'รวม':>8}")
print(f"{'-'*14} {'-'*8} {'-'*8} {'-'*8}")
for s, a, j, tot in rows:
    in_config = "" if s in ALL_SELLERS else "  ⚠️ ไม่อยู่ใน config"
    print(f"{s:<14} {a:>8} {j:>8} {tot:>8}{in_config}")

# Sum
tot_active = sum(seller_counts.values())
tot_junk = sum(seller_junk_counts.values())
print(f"{'-'*14} {'-'*8} {'-'*8} {'-'*8}")
print(f"{'รวม':<14} {tot_active:>8} {tot_junk:>8} {tot_active+tot_junk:>8}")

# เช็คโค้ดซ้ำในเดือนนี้
print(f"\n🔁 Code ซ้ำในเดือนนี้ (ถ้ามี = bug):")
codes = [cell(r, L.lead_code).strip().upper() for r in this_month + junk_this_month if cell(r, L.lead_code).strip()]
dup = [c for c, n in Counter(codes).items() if n > 1]
if dup:
    for c in dup[:10]:
        print(f"  ⚠️ {c} ซ้ำ {Counter(codes)[c]} ครั้ง")
else:
    print(f"  ✓ ไม่มีโค้ดซ้ำ ({len(codes)} codes ทั้งหมดของเดือนนี้)")
