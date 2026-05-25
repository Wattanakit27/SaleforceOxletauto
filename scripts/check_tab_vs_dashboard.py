"""เทียบ row count ต่อ monthly tab vs ตัวเลขที่ dashboard ใช้
ถ้า user ดูจาก tab "พฤษภาคม 69" ตรงๆ มีกี่แถว vs dashboard แสดงเท่าไหร่
"""
import os, sys, urllib.parse, requests, django
from pathlib import Path
from collections import Counter

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
django.setup()

from dashboard.services.google_sheets import (
    SHEET_CONFIG, fetch_sheet, fetch_leads_dedup, cell, LEADS_COL as L,
    _get_credentials, _THAI_MONTHS,
)
from google.auth.transport.requests import Request as AuthRequest
from dashboard.services.fetch_dashboard import (
    parse_date, is_this_year, is_skipped, bangkok_now,
)
from dashboard.services.constants import normalize_seller

SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"

now = bangkok_now()
print(f"\n=== Cross-check: tab vs dashboard ({now.date()}) ===\n")

# 1) ลิสต์ทุก tab + นับ row ต่อ tab
creds = _get_credentials()
creds.refresh(AuthRequest())
headers = {"Authorization": f"Bearer {creds.token}"}
sid = SHEET_CONFIG["leads"]["spreadsheet_id"]

meta = requests.get(
    f"{SHEETS_API}/{sid}?fields=sheets.properties.title",
    headers=headers, timeout=15,
).json()
all_tabs = [s["properties"]["title"] for s in meta.get("sheets", [])]
print(f"Tab ทั้งหมดใน leads spreadsheet ({len(all_tabs)} tabs):")
for t in all_tabs:
    print(f"  • {t!r}")

print(f"\n--- นับ row ต่อ tab (raw, รวม header) ---")
tab_raw_counts = {}
for tab in all_tabs:
    encoded = urllib.parse.quote(f"'{tab}'")
    url = f"{SHEETS_API}/{sid}/values/{encoded}?valueRenderOption=FORMATTED_VALUE"
    r = requests.get(url, headers=headers, timeout=30)
    if r.status_code != 200:
        print(f"  {tab!r}: ERROR {r.status_code}")
        continue
    rows = r.json().get("values", [])
    tab_raw_counts[tab] = len(rows)
    # ดูว่ามีกี่แถวที่มีข้อมูลจริง (มีโค้ดหรือเบอร์)
    has_data = sum(1 for row in rows[1:] if any(c.strip() for c in row[:5] if c))
    print(f"  {tab!r:30}: raw={len(rows):>6}, มีข้อมูล (skip header)={has_data}")

# 2) เจาะ tab "พฤษภาคม 69" — ดูทุกเดือนใน column วันที่
print(f"\n--- เจาะ tab 'พฤษภาคม 69' (ถ้ามี) ---")
may_tab = None
for t in all_tabs:
    if "พฤษภาคม" in t:
        may_tab = t
        break
if not may_tab:
    print("  ไม่พบ tab 'พฤษภาคม ...'")
else:
    encoded = urllib.parse.quote(f"'{may_tab}'")
    url = f"{SHEETS_API}/{sid}/values/{encoded}?valueRenderOption=FORMATTED_VALUE"
    rows = requests.get(url, headers=headers, timeout=30).json().get("values", [])[1:]
    print(f"  {may_tab!r}: {len(rows)} แถว (ไม่นับ header)")

    # นับว่าวันที่ตกเดือนไหน
    month_dist = Counter()
    year_dist = Counter()
    no_date = 0
    bad_date_examples = []
    skipped_in_may = 0
    active_in_may = 0
    sellers_in_may = Counter()
    for r in rows:
        date_str = cell(r, L.received_date)
        if not date_str:
            no_date += 1
            continue
        d = parse_date(date_str)
        if not d:
            if len(bad_date_examples) < 5:
                bad_date_examples.append((date_str, cell(r, L.lead_code)))
            continue
        month_dist[d.month] += 1
        year_dist[d.year] += 1
        if d.year == now.year and d.month == 5:
            admin_st = cell(r, L.admin_status)
            sales_st = cell(r, L.sales_status)
            if is_skipped(admin_st) or is_skipped(sales_st):
                skipped_in_may += 1
            else:
                active_in_may += 1
            seller = normalize_seller(cell(r, L.sales_rep)) or "(ไม่ระบุ)"
            sellers_in_may[seller] += 1

    print(f"  - no date: {no_date}")
    print(f"  - bad date: {len(bad_date_examples)} {bad_date_examples[:3]}")
    print(f"  - distribution ตามเดือน: {dict(sorted(month_dist.items()))}")
    print(f"  - distribution ตามปี: {dict(sorted(year_dist.items()))}")
    print(f"\n  ✦ เฉพาะเดือน 5/{now.year} ใน tab นี้:")
    print(f"    active: {active_in_may}, junk: {skipped_in_may}, รวม: {active_in_may+skipped_in_may}")
    print(f"    by seller:")
    for s, n in sellers_in_may.most_common(20):
        print(f"      {s:<14} {n}")

# 3) เทียบกับ dedup (สิ่งที่ dashboard ใช้)
print(f"\n--- After fetch_leads_dedup() — ใช้ตัวนี้ใน dashboard ---")
deduped = fetch_leads_dedup()
month5 = []
junk5 = []
for r in deduped:
    d = parse_date(cell(r, L.received_date))
    if not d or d.year != now.year or d.month != 5:
        continue
    admin_st = cell(r, L.admin_status)
    sales_st = cell(r, L.sales_status)
    if is_skipped(admin_st) or is_skipped(sales_st):
        junk5.append(r)
    else:
        month5.append(r)
print(f"  Dashboard เห็น (active เดือน 5): {len(month5)}")
print(f"  Dashboard ตัด junk (ไม่แสดงให้เซลล์): {len(junk5)}")
print(f"  รวม dedup เดือน 5: {len(month5) + len(junk5)}")

# 4) เทียบกับ tab "รวม sheet" ตรงๆ (ไม่ผ่าน dedup)
print(f"\n--- 'รวม sheet' (base, ก่อน dedup) — เฉพาะเดือน 5/{now.year} ---")
base_rows = fetch_sheet("leads")
ba, bj = 0, 0
for r in base_rows:
    d = parse_date(cell(r, L.received_date))
    if not d or d.year != now.year or d.month != 5:
        continue
    admin_st = cell(r, L.admin_status)
    sales_st = cell(r, L.sales_status)
    if is_skipped(admin_st) or is_skipped(sales_st):
        bj += 1
    else:
        ba += 1
print(f"  'รวม sheet' เดือน 5: active={ba}, junk={bj}, รวม={ba+bj}")
print(f"  (เลขนี้ไม่ผ่าน dedup — ถ้า dedup น้อยกว่า แสดงว่ามี code ซ้ำกัน base vs monthly)")
