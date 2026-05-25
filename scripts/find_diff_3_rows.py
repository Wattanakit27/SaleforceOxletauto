"""หา 3 แถวที่ทำให้ API คืน 2,585 แต่ user นับใน sheet ได้ 2,582
เช็ค edge cases: วันที่แปลก, แถวว่าง, code ซ้ำใน tab, etc.
"""
import os, sys, django, urllib.parse, requests
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
django.setup()

from dashboard.services.google_sheets import (
    SHEET_CONFIG, _get_credentials, cell, LEADS_COL as L,
)
from google.auth.transport.requests import Request as AuthRequest
from dashboard.services.fetch_dashboard import parse_date, bangkok_now

SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
now = bangkok_now()

creds = _get_credentials(); creds.refresh(AuthRequest())
headers = {"Authorization": f"Bearer {creds.token}"}
sid = SHEET_CONFIG["leads"]["spreadsheet_id"]

# ดึง tab พ.ค. ทั้งหมด
encoded = urllib.parse.quote(f"'พฤษภาคม 69'")
r = requests.get(
    f"{SHEETS_API}/{sid}/values/{encoded}?valueRenderOption=FORMATTED_VALUE",
    headers=headers, timeout=30,
)
all_data = r.json().get("values", [])
header = all_data[0] if all_data else []
rows = all_data[1:]
print(f"\n=== tab 'พฤษภาคม 69' — {len(rows)} แถว (ไม่นับ header) ===\n")

# Count rows that pass our filter (date.month == 5)
keep = []
skip_no_date = []
skip_wrong_month = []
skip_bad_date = []
for idx, row in enumerate(rows):
    date_str = cell(row, L.received_date)
    if not date_str:
        skip_no_date.append((idx + 2, row))  # +2 = 1-indexed + header
        continue
    d = parse_date(date_str)
    if not d:
        skip_bad_date.append((idx + 2, date_str, row))
        continue
    if d.month != 5 or d.year != 2026:
        skip_wrong_month.append((idx + 2, date_str, d.month, row))
        continue
    keep.append((idx + 2, date_str, row))

print(f"keep (date=พ.ค. 2026): {len(keep)}")
print(f"skip (no date)       : {len(skip_no_date)}")
print(f"skip (bad date)      : {len(skip_bad_date)}")
print(f"skip (wrong month)   : {len(skip_wrong_month)}")

# 1) แถวว่าง / no date
print(f"\n📋 แถวที่ no date (อยู่ใน tab พ.ค. แต่ไม่มีวันที่):")
print(f"   จำนวน: {len(skip_no_date)} แถว")
for sheet_row, row in skip_no_date[:5]:
    code = cell(row, L.lead_code)
    phone = cell(row, L.phone)
    print(f"   row#{sheet_row}: code={code!r}, phone={phone!r}, row_len={len(row)}")
# ถ้า user "นับด้วยตา" แถวว่างจะไม่นับ — แต่ API count keep ไม่รวมพวกนี้อยู่แล้ว

# 2) bad date examples
print(f"\n⚠️ แถวที่ parse_date ไม่ได้:")
for sheet_row, date_str, row in skip_bad_date[:5]:
    print(f"   row#{sheet_row}: date={date_str!r}, code={cell(row, L.lead_code)!r}")

# 3) Code ซ้ำใน "keep" (= 3 รอบเดียวกัน เกินจากที่ user คาด?)
print(f"\n🔁 Code ซ้ำใน keep (เดือน 5 ใน tab พ.ค.):")
code_count = Counter()
for _, _, row in keep:
    code = cell(row, L.lead_code).strip().upper()
    if code:
        code_count[code] += 1
dups = [(c, n) for c, n in code_count.items() if n > 1]
print(f"   จำนวน code ที่ซ้ำ: {len(dups)}")
print(f"   จำนวน 'แถวซ้ำเกินมา' (= count - 1): {sum(n-1 for _, n in dups)}")
for c, n in sorted(dups, key=lambda x: -x[1])[:15]:
    # หาแถวที่ใช้ code นี้
    matches = [(sr, ds) for sr, ds, row in keep if cell(row, L.lead_code).strip().upper() == c]
    print(f"   {c!r:15} ซ้ำ {n} ครั้ง (rows: {[sr for sr, _ in matches[:5]]})")

# 4) วันที่ boundary (1/5, 31/5) — น่าจะถูก
print(f"\n📅 วันที่ boundary (1/5 หรือ 31/5):")
boundary = [(sr, ds) for sr, ds, _ in keep if ds in ('1/5/26', '31/5/26', '1/05/26', '31/05/26')]
print(f"   จำนวน: {len(boundary)}")
for sr, ds in boundary[:10]:
    print(f"   row#{sr}: {ds}")

# 5) Excel serial date หรือ format แปลก
print(f"\n🔢 วันที่ format ไม่ใช่ d/m/yy ปกติ:")
import re
weird_format = [(sr, ds) for sr, ds, _ in keep if not re.match(r'^\d{1,2}/\d{1,2}/\d{2,4}$', ds)]
print(f"   จำนวน: {len(weird_format)}")
for sr, ds in weird_format[:10]:
    print(f"   row#{sr}: {ds!r}")

# 6) แถวที่ keep แต่ "ดูเป็นแถวว่าง" (มีแค่วันที่ ไม่มีข้อมูลอื่น)
print(f"\n👻 แถวที่ keep แต่ดูเปล่าๆ (มีแค่วันที่ ไม่มีเบอร์/code/รถ):")
ghost = []
for sr, ds, row in keep:
    code = cell(row, L.lead_code).strip()
    phone = cell(row, L.phone).strip()
    car = (cell(row, L.car_inquiry) or cell(row, L.car_formula)).strip()
    if not code and not phone and not car:
        ghost.append((sr, ds, row))
print(f"   จำนวน: {len(ghost)}")
for sr, ds, row in ghost[:5]:
    print(f"   row#{sr}: date={ds}, row content: {[c[:20] if isinstance(c,str) else c for c in row[:8]]}")
