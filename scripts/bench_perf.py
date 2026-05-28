"""วัดเวลาที่ระบบใช้โหลด dashboard / seller / leadscore"""
import os, sys, time, django
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
django.setup()

from dashboard.services.google_sheets import invalidate_cache
from dashboard.services.fetch_dashboard import (
    fetch_dashboard_data, fetch_seller_stats,
    compute_diligence_scores, export_leadscore_to_sheet,
)

def t(label, fn):
    t0 = time.time()
    r = fn()
    dt = time.time() - t0
    print(f"  {label:<45} {dt:>7.2f}s")
    return r, dt

print(f"\n=== Cold start (cache ว่าง) ===\n")
invalidate_cache()
_, t1 = t("fetch_dashboard_data() — full /dashboard/", fetch_dashboard_data)

print(f"\n=== Warm cache (call ที่ 2 ภายใน 60s) ===\n")
_, t2 = t("fetch_dashboard_data() — cache hit", fetch_dashboard_data)
_, t3 = t("fetch_seller_stats('บอย') — cache hit", lambda: fetch_seller_stats("บอย"))
_, t4 = t("compute_diligence_scores() — cache hit", compute_diligence_scores)

print(f"\n=== Summary ===")
print(f"  Cold start /dashboard/        : ~{t1:.1f}s  (ครั้งแรกที่ Vercel cold)")
print(f"  Warm /dashboard/              : ~{t2:.2f}s  (ครั้งต่อมาภายใน 60s)")
print(f"  Warm /s/<token>/              : ~{t3:.2f}s  (data isolated)")
print(f"  Warm compute_diligence_scores : ~{t4:.2f}s")

print(f"\nสรุป: ครั้งแรกหลัง deploy/cold start ใช้ {t1:.0f}s")
print(f"      ครั้งต่อมา (cache อยู่)        ใช้ {t2:.2f}s")
