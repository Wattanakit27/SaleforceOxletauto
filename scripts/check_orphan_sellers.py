"""หา "ไม่ระบุ" คืออะไร — leads ที่ชื่อเซลล์ไม่อยู่ใน ALL_SELLERS"""
import os, sys, django
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
django.setup()

from dashboard.services.google_sheets import fetch_leads_by_month_tabs, fetch_sheet, cell, LEADS_COL as L, EMPLOYEE_COL as EM
from dashboard.services.fetch_dashboard import parse_date, bangkok_now
from dashboard.services.constants import normalize_seller, ALL_SELLERS, refresh_from_sheet, TEAMS, SELLER_MAP

# Load config sheet first
refresh_from_sheet()
print(f"\n=== ALL_SELLERS ใน config ({len(ALL_SELLERS)} คน) ===")
print(", ".join(sorted(ALL_SELLERS)))

now = bangkok_now()
print(f"\n=== วิเคราะห์ orphan sellers ({now.year}) ===\n")

leads = fetch_leads_by_month_tabs()
print(f"Total leads ทั้งปี: {len(leads)}")

# Group leads by normalized seller name
raw_names = Counter()        # ชื่อ raw ใน sheet (ก่อน normalize)
normalized = Counter()       # ชื่อหลัง normalize
orphan_raw = Counter()       # raw ของเคสที่ orphan
orphan_normalized = Counter()  # normalized ของเคสที่ orphan

for r in leads:
    d = parse_date(cell(r, L.received_date))
    if not d or d.year != now.year:
        continue
    raw = cell(r, L.sales_rep).strip()
    if not raw:
        raw_names["(ว่าง)"] += 1
        continue
    raw_names[raw] += 1
    norm = normalize_seller(raw)
    normalized[norm] += 1
    if norm not in ALL_SELLERS:
        orphan_raw[raw] += 1
        orphan_normalized[norm] += 1

print(f"\n📊 จำนวน 'ไม่ระบุ' (orphan = ไม่อยู่ใน config) เดือนนี้:")
print(f"  รวมทั้งหมด: {sum(orphan_normalized.values())} เคส\n")

print(f"📋 ชื่อ orphan (หลัง normalize) — top 20:")
print(f"{'ชื่อ':<25} {'count':>6}")
print("-" * 33)
for name, n in orphan_normalized.most_common(20):
    print(f"  {name!r:<23} {n:>6}")

print(f"\n📋 ชื่อ raw (ก่อน normalize) ของเคส orphan — top 30:")
print(f"   ดูว่าใช่เซลล์ใหม่/พิมพ์ผิด/admin หรือไม่")
print(f"{'ชื่อ raw':<35} {'count':>6}")
print("-" * 43)
for raw, n in orphan_raw.most_common(30):
    print(f"  {raw!r:<33} {n:>6}")

# เปรียบเทียบกับ employees sheet — orphan ที่เป็น user_id จริงในระบบไหม
print(f"\n🔍 เช็คชื่อ orphan ใน employees sheet:")
try:
    employees = fetch_sheet("employees")
    employee_nicks = set()
    for r in employees:
        nick = cell(r, EM.nickname).strip()
        if nick:
            employee_nicks.add(nick)
            normalized_nick = normalize_seller(nick)
            if normalized_nick:
                employee_nicks.add(normalized_nick)

    in_employees = []
    not_in_employees = []
    for name, n in orphan_normalized.most_common():
        if name in employee_nicks:
            in_employees.append((name, n))
        else:
            not_in_employees.append((name, n))

    print(f"\n  ✓ Orphan ที่อยู่ใน employees sheet (= เซลล์ใหม่จริง, ต้องเพิ่ม config):")
    for name, n in in_employees[:15]:
        print(f"    {name!r:<25} {n:>6}")

    print(f"\n  ✗ Orphan ที่ไม่อยู่ใน employees sheet (= admin? พิมพ์ผิด?):")
    for name, n in not_in_employees[:15]:
        print(f"    {name!r:<25} {n:>6}")
except Exception as e:
    print(f"  Error: {e}")

# Sample raw_seller value ของเคส orphan
print(f"\n📋 SELLER_MAP ปัจจุบัน ({len(SELLER_MAP)} entries):")
for raw, norm in sorted(SELLER_MAP.items())[:20]:
    print(f"  {raw!r:<25} → {norm!r}")
if len(SELLER_MAP) > 20:
    print(f"  ... อีก {len(SELLER_MAP)-20} entries")
