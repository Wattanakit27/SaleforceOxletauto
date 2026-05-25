"""ดูตัวเลขที่ main dashboard จะแสดง หลังเปลี่ยน fetch_all_sheets → by_month_tabs"""
import os, sys, django
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
django.setup()

from dashboard.services.fetch_dashboard import fetch_dashboard_data, bangkok_now

now = bangkok_now()
print(f"\n=== Main dashboard data (เดือนปัจจุบัน {now.month}/{now.year}) ===\n")

data = fetch_dashboard_data()
summary = data.get("summary", {})
month_data = (data.get("monthlySummary") or {}).get(now.month) or (data.get("monthlySummary") or {}).get(str(now.month)) or {}

print(f"summary (ทั้งปี):")
for k in ("totalLeads", "leadNormal", "leadRJ", "totalFollow", "totalBookings", "totalDone"):
    print(f"  {k:<16} = {summary.get(k, '?'):>6}")

print(f"\nเดือน {now.month} เฉพาะ:")
for k in ("totalLeads", "leadNormal", "leadRJ", "totalFollow", "totalBookings", "totalDone", "totalVacant"):
    print(f"  {k:<16} = {month_data.get(k, '?'):>6}")

print(f"\nเดือน 4 (เม.ย.):")
m4 = (data.get("monthlySummary") or {}).get(4) or (data.get("monthlySummary") or {}).get("4") or {}
for k in ("totalLeads", "leadNormal", "leadRJ"):
    print(f"  {k:<16} = {m4.get(k, '?'):>6}")
