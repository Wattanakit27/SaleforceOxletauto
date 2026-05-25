"""Debug: junk เยอะเพราะ keyword ตัวไหน + status text จริงเป็นอะไร"""
import os, sys, django
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
django.setup()

from dashboard.services.google_sheets import fetch_leads_dedup, cell, LEADS_COL as L
from dashboard.services.fetch_dashboard import (
    parse_date, is_skipped, SKIP_STATUS, bangkok_now,
)

now = bangkok_now()
print(f"\n=== วิเคราะห์ junk เดือน {now.month}/{now.year} ===\n")
print(f"SKIP_STATUS keywords ปัจจุบัน: {SKIP_STATUS}\n")

raw = fetch_leads_dedup()

# นับ status text จริงของเคสที่ถูก mark เป็น junk เดือนนี้
admin_status_hit = Counter()
sales_status_hit = Counter()
keyword_hit_admin = Counter()
keyword_hit_sales = Counter()

for r in raw:
    d = parse_date(cell(r, L.received_date))
    if not d or d.year != now.year or d.month != now.month:
        continue
    admin_st = cell(r, L.admin_status)
    sales_st = cell(r, L.sales_status)
    admin_skip = is_skipped(admin_st)
    sales_skip = is_skipped(sales_st)
    if not (admin_skip or sales_skip):
        continue
    if admin_skip:
        admin_status_hit[admin_st] += 1
        for kw in SKIP_STATUS:
            if kw.lower() in admin_st.lower():
                keyword_hit_admin[kw] += 1
    if sales_skip:
        sales_status_hit[sales_st] += 1
        for kw in SKIP_STATUS:
            if kw.lower() in sales_st.lower():
                keyword_hit_sales[kw] += 1

print(f"📋 admin_status ของเคสที่ถูก mark = junk (top 30):")
print(f"{'count':>6}  status")
print(f"{'-'*6}  {'-'*40}")
for status, n in admin_status_hit.most_common(30):
    print(f"{n:>6}  {status!r}")

print(f"\n📋 sales_status ของเคสที่ถูก mark = junk (top 30):")
print(f"{'count':>6}  status")
print(f"{'-'*6}  {'-'*40}")
for status, n in sales_status_hit.most_common(30):
    print(f"{n:>6}  {status!r}")

print(f"\n🔑 Keyword hit count (admin_status):")
for kw, n in keyword_hit_admin.most_common():
    print(f"  {kw!r:18} → {n} เคส")
print(f"\n🔑 Keyword hit count (sales_status):")
for kw, n in keyword_hit_sales.most_common():
    print(f"  {kw!r:18} → {n} เคส")

# ตรวจ "คืน" ดูว่ามี false-positive ไหม
print(f"\n⚠️ เช็คคำว่า 'คืน' ใน admin_status (อาจ false-positive):")
khun_hit = [s for s in admin_status_hit if 'คืน' in s.lower()]
for s in khun_hit[:20]:
    print(f"  {admin_status_hit[s]:>4}x  {s!r}")

print(f"\n⚠️ เช็คคำว่า 'จบ' ใน admin_status:")
job_hit = [s for s in admin_status_hit if 'จบ' in s.lower()]
for s in job_hit[:20]:
    print(f"  {admin_status_hit[s]:>4}x  {s!r}")
