"""เทียบทุก source ของ "lead เดือนนี้" เพื่อหาว่ายอดไม่ตรงตรงไหน
เซลล์/แอดมินอาจดูจากที่ต่างกัน 3-4 ที่ — script นี้จะแสดง gap ทั้งหมด
"""
import os, sys, django, urllib.parse, requests
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
django.setup()

from dashboard.services.google_sheets import (
    SHEET_CONFIG, fetch_sheet, cell, LEADS_COL as L, _get_credentials,
)
from google.auth.transport.requests import Request as AuthRequest
from dashboard.services.fetch_dashboard import parse_date, bangkok_now
from dashboard.services.constants import normalize_seller

SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
now = bangkok_now()
print(f"\n=== หาว่า 'lead เดือน {now.month}/{now.year}' หายไปไหน ===\n")

# 1) ดึง tab "พฤษภาคม 69" ตรงๆ
creds = _get_credentials()
creds.refresh(AuthRequest())
headers = {"Authorization": f"Bearer {creds.token}"}
sid = SHEET_CONFIG["leads"]["spreadsheet_id"]

# หาชื่อ tab ของเดือนนี้
months_th = ["มกราคม","กุมภาพันธ์","มีนาคม","เมษายน","พฤษภาคม","มิถุนายน",
             "กรกฎาคม","สิงหาคม","กันยายน","ตุลาคม","พฤศจิกายน","ธันวาคม"]
cur_month_name = months_th[now.month - 1]

meta = requests.get(
    f"{SHEETS_API}/{sid}?fields=sheets.properties.title",
    headers=headers, timeout=15,
).json()
all_tabs = [s["properties"]["title"] for s in meta.get("sheets", [])]
month_tab = None
for t in all_tabs:
    if cur_month_name in t:
        month_tab = t
        break

print(f"Tab เดือนนี้: {month_tab!r}\n")

def fetch_tab_rows(tab_name):
    encoded = urllib.parse.quote(f"'{tab_name}'")
    url = f"{SHEETS_API}/{sid}/values/{encoded}?valueRenderOption=FORMATTED_VALUE"
    r = requests.get(url, headers=headers, timeout=30)
    return r.json().get("values", [])[1:] if r.status_code == 200 else []

tab_rows = fetch_tab_rows(month_tab) if month_tab else []
base_rows = fetch_sheet("leads")

# 2) Source A: tab "พฤษภาคม 69" ทุกแถว (ไม่ filter วันที่)
def by_seller(rows, filter_fn=None):
    c = Counter()
    for r in rows:
        if filter_fn and not filter_fn(r):
            continue
        s = normalize_seller(cell(r, L.sales_rep)) or "(ไม่ระบุ)"
        c[s] += 1
    return c

def in_cur_month(r):
    d = parse_date(cell(r, L.received_date))
    return bool(d and d.year == now.year and d.month == now.month)

src_A = by_seller(tab_rows)                              # tab raw (ไม่ filter)
src_B = by_seller(tab_rows, in_cur_month)                # tab filter วันที่
src_C = by_seller(base_rows, in_cur_month)               # รวม sheet filter วันที่ (dashboard ตอนนี้ใช้)

print(f"3 sources ของ 'lead เดือน {now.month}':")
print(f"  A. Tab {month_tab!r} ทุกแถว           = {sum(src_A.values()):>6}")
print(f"  B. Tab {month_tab!r} filter วัน=เดือน{now.month} = {sum(src_B.values()):>6}")
print(f"  C. 'รวม sheet' filter วัน=เดือน{now.month}      = {sum(src_C.values()):>6}  (← dashboard เซลล์ใช้)")

# Per-seller diff
print(f"\n{'seller':<14}{'A: tab':>8}{'B: tab+date':>13}{'C: รวม+date':>13}{'A-C':>6}{'B-C':>6}")
print("-" * 60)
all_sellers = set(src_A) | set(src_B) | set(src_C)
rows_out = []
for s in all_sellers:
    a = src_A.get(s, 0); b = src_B.get(s, 0); c = src_C.get(s, 0)
    rows_out.append((s, a, b, c, a-c, b-c))
rows_out.sort(key=lambda x: -x[1])
for s, a, b, c, ac, bc in rows_out:
    print(f"{s:<14}{a:>8}{b:>13}{c:>13}{ac:>+6}{bc:>+6}")
print("-" * 60)
ta = sum(src_A.values()); tb = sum(src_B.values()); tc = sum(src_C.values())
print(f"{'รวม':<14}{ta:>8}{tb:>13}{tc:>13}{ta-tc:>+6}{tb-tc:>+6}")

# 3) วิเคราะห์ "tab เดือนนี้ แต่วันที่ไม่ใช่เดือนนี้" (= ปริมาณที่หลุดจาก dashboard)
print(f"\n📋 แถวใน tab {month_tab!r} ที่ filter วัน≠เดือน{now.month} (= dashboard ไม่นับเดือนนี้):")
month_dist = Counter()
year_dist = Counter()
no_date_in_tab = 0
for r in tab_rows:
    date_str = cell(r, L.received_date)
    if not date_str:
        no_date_in_tab += 1
        continue
    d = parse_date(date_str)
    if not d:
        continue
    if d.month == now.month and d.year == now.year:
        continue
    month_dist[f"{d.month}/{d.year}"] += 1

print(f"  no_date: {no_date_in_tab}")
for k, n in sorted(month_dist.items(), key=lambda x: -x[1]):
    print(f"  วันที่ตกเดือน {k}: {n} แถว")

# 4) "รวม sheet" filter เดือนนี้ แต่ไม่อยู่ใน tab "พฤษภาคม 69" (= มีใน C แต่ไม่อยู่ใน B)
print(f"\n📋 แถวที่ 'รวม sheet' บอกว่าเป็นเดือน {now.month} แต่ไม่อยู่ใน tab {month_tab!r}:")
tab_codes = set()
for r in tab_rows:
    code = cell(r, L.lead_code).strip().upper()
    if code:
        tab_codes.add(code)

orphans = []
for r in base_rows:
    if not in_cur_month(r):
        continue
    code = cell(r, L.lead_code).strip().upper()
    if code and code not in tab_codes:
        orphans.append({
            "code": cell(r, L.lead_code),
            "date": cell(r, L.received_date),
            "seller": normalize_seller(cell(r, L.sales_rep)) or "(ว่าง)",
            "phone": cell(r, L.phone),
            "admin": cell(r, L.admin_status),
            "sales": cell(r, L.sales_status),
        })
print(f"  จำนวน: {len(orphans)} แถว")
print(f"  ตัวอย่าง 5 แถวแรก:")
for o in orphans[:5]:
    print(f"    {o['date']:>10} | {o['code']:<15} | {o['seller']:<10} | admin={o['admin']!r:<20} sales={o['sales']!r}")

# 5) แถวใน tab "พฤษภาคม 69" filter date=พ.ค. แต่ไม่อยู่ใน "รวม sheet"
print(f"\n📋 แถวที่อยู่ใน tab {month_tab!r} (date=พ.ค.) แต่ไม่อยู่ใน 'รวม sheet':")
base_codes = set()
for r in base_rows:
    code = cell(r, L.lead_code).strip().upper()
    if code:
        base_codes.add(code)

missing = []
for r in tab_rows:
    if not in_cur_month(r):
        continue
    code = cell(r, L.lead_code).strip().upper()
    if code and code not in base_codes:
        missing.append({
            "code": cell(r, L.lead_code),
            "date": cell(r, L.received_date),
            "seller": normalize_seller(cell(r, L.sales_rep)) or "(ว่าง)",
        })
print(f"  จำนวน: {len(missing)} แถว")
for m in missing[:5]:
    print(f"    {m['date']:>10} | {m['code']:<15} | {m['seller']}")
