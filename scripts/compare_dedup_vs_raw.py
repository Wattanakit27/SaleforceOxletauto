"""เทียบ fetch_sheet vs fetch_leads_dedup — ดู lead count ของแต่ละเซลล์เดือนนี้"""
import os, sys, django
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
django.setup()

from dashboard.services.google_sheets import fetch_sheet, fetch_leads_dedup, cell, LEADS_COL as L
from dashboard.services.fetch_dashboard import parse_date, bangkok_now
from dashboard.services.constants import normalize_seller

now = bangkok_now()
print(f"\n=== เทียบ raw vs dedup เดือน {now.month}/{now.year} ===\n")

raw = fetch_sheet("leads")
ded = fetch_leads_dedup()
print(f"fetch_sheet('leads')   = {len(raw):>6} แถว ('รวม sheet' ตรงๆ)")
print(f"fetch_leads_dedup()    = {len(ded):>6} แถว (union+dedup)")
print(f"ต่างกัน                = {len(ded)-len(raw):+d} แถว\n")

def count_by_seller(rows, label):
    by_seller = Counter()
    total = 0
    for r in rows:
        d = parse_date(cell(r, L.received_date))
        if not d or d.year != now.year or d.month != now.month:
            continue
        seller = normalize_seller(cell(r, L.sales_rep)) or "(ไม่ระบุ)"
        by_seller[seller] += 1
        total += 1
    print(f"--- {label}: เดือน {now.month} = {total} เคส ---")
    return by_seller

raw_by_seller = count_by_seller(raw, "fetch_sheet (รวม sheet ตรงๆ)")
ded_by_seller = count_by_seller(ded, "fetch_leads_dedup")

print(f"\n{'seller':<14} {'raw':>6} {'dedup':>6} {'diff':>6}")
print("-" * 36)
all_sellers = set(raw_by_seller) | set(ded_by_seller)
rows_out = []
for s in all_sellers:
    r = raw_by_seller.get(s, 0)
    d = ded_by_seller.get(s, 0)
    rows_out.append((s, r, d, r - d))
rows_out.sort(key=lambda x: -x[1])
for s, r, d, diff in rows_out:
    marker = " ← มี diff" if diff != 0 else ""
    print(f"{s:<14} {r:>6} {d:>6} {diff:>+6}{marker}")
print("-" * 36)
tot_r = sum(raw_by_seller.values())
tot_d = sum(ded_by_seller.values())
print(f"{'รวม':<14} {tot_r:>6} {tot_d:>6} {tot_r-tot_d:>+6}")
