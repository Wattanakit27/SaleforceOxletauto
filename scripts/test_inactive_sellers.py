"""ทดสอบว่า orphan sellers ถูกแยกเป็น per-name rows + inactive flag"""
import os, sys, django
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
django.setup()

from dashboard.services.google_sheets import invalidate_cache
from dashboard.services.fetch_dashboard import fetch_dashboard_data, bangkok_now

invalidate_cache()  # clear cache เพื่อให้ refresh จาก sheet

data = fetch_dashboard_data()
now = bangkok_now()

print(f"\n=== Year sellers list ({len(data['sellers'])} entries) ===\n")
print(f"{'ชื่อ':<20} {'team':<10} {'lead':>6} {'inactive':>8}")
print("-" * 50)
for s in data["sellers"]:
    inactive_flag = "✓" if s.get("inactive") else ""
    print(f"  {s['name']:<18} {s['team']:<10} {s['lead']:>6} {inactive_flag:>8}")

# Monthly for current month
m = data.get("monthlySummary", {}).get(now.month) or data.get("monthlySummary", {}).get(str(now.month)) or {}
m_sellers = m.get("sellers", {})

print(f"\n=== Monthly sellers (เดือน {now.month}) — {len(m_sellers)} entries ===\n")
print(f"{'ชื่อ':<20} {'lead':>6} {'inactive':>8}")
print("-" * 38)
for name, s in sorted(m_sellers.items(), key=lambda x: -x[1].get("lead", 0)):
    inactive_flag = "✓" if s.get("inactive") else ""
    print(f"  {name:<18} {s.get('lead', 0):>6} {inactive_flag:>8}")
