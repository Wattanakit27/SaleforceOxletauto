"""ทดสอบ fetch_seller_stats() — ตรวจว่าข้อมูลเฉพาะเซลล์ + ไม่มี leak ของคนอื่น"""
import os, sys, time, json, django
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
django.setup()

from dashboard.services.google_sheets import invalidate_cache
from dashboard.services.fetch_dashboard import fetch_seller_stats, fetch_dashboard_data

invalidate_cache()

# Test 1: เปรียบเทียบความเร็ว fetch_seller_stats vs fetch_dashboard_data
print(f"\n=== Performance comparison ===\n")

t0 = time.time()
seller_data = fetch_seller_stats("บอย")
t1 = time.time() - t0
print(f"fetch_seller_stats('บอย')      : {t1:.2f}s")

t0 = time.time()
global_data = fetch_dashboard_data()
t2 = time.time() - t0
print(f"fetch_dashboard_data() (global): {t2:.2f}s")
print(f"Speedup เซลล์view = {t2/max(t1,0.001):.1f}x")

# Test 2: Data isolation — ดูว่า fetch_seller_stats ไม่ส่งข้อมูลเซลล์อื่น
print(f"\n=== Data isolation ===\n")
keys = sorted(seller_data.keys())
print(f"Keys ใน fetch_seller_stats: {keys}")
print(f"\nKeys ที่ HASN'T leaked:")
for forbidden in ["sellers", "teams", "leadCarsByMonth", "leadCarSellerMonth",
                  "userIdMap", "employees", "dailyBySeller", "summary"]:
    if forbidden not in seller_data:
        print(f"  ✓ '{forbidden}' ไม่อยู่ใน response")
    else:
        print(f"  ✗ LEAK: '{forbidden}' ยังอยู่!")

# Test 3: ตรวจตัวเลขตรงกับ global
print(f"\n=== Numbers consistency (compare บอย) ===\n")
boy_global = next((s for s in global_data["sellers"] if s["name"] == "บอย"), None)
boy_seller = seller_data["seller"]
print(f"{'metric':<14} {'global':>10} {'seller_stats':>15} {'match':>7}")
print("-" * 50)
for k in ["lead", "follow", "vacant", "done", "booking", "dealValue", "target"]:
    g = boy_global.get(k, 0) if boy_global else 0
    s = boy_seller.get(k, 0)
    match = "✓" if g == s else "✗"
    print(f"  {k:<12} {g:>10} {s:>15} {match:>7}")

# Test 4: Monthly summary ตรงกัน?
print(f"\n=== Monthly summary เดือนปัจจุบัน (เดือน 5) ===\n")
m_global = global_data.get("monthlySummary", {}).get(5, {}).get("sellers", {}).get("บอย", {})
m_seller = seller_data["monthly"].get(5, {})
print(f"{'metric':<14} {'global':>10} {'seller':>10} {'match':>7}")
print("-" * 45)
for k in ["lead", "follow", "vacant", "done", "booking", "dealValue"]:
    g = m_global.get(k, 0)
    s = m_seller.get(k, 0)
    match = "✓" if g == s else "✗"
    print(f"  {k:<12} {g:>10} {s:>10} {match:>7}")

# Test 5: Response size (JSON bytes)
print(f"\n=== JSON size comparison ===\n")
seller_json = json.dumps(seller_data, ensure_ascii=False, default=str)
global_json = json.dumps(global_data, ensure_ascii=False, default=str)
print(f"fetch_seller_stats JSON size:  {len(seller_json):>10,} bytes")
print(f"fetch_dashboard_data JSON size:{len(global_json):>10,} bytes")
print(f"Reduction: {(1 - len(seller_json)/len(global_json))*100:.1f}%")
