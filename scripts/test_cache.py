"""ทดสอบ cache ลด API calls จริง — เรียก fetch_sheet 3 ครั้งติด"""
import os, sys, time, django
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
django.setup()

from dashboard.services.google_sheets import fetch_sheet, fetch_leads_by_month_tabs, invalidate_cache, _CACHE

print(f"\n=== ทดสอบ cache (TTL 60s) ===\n")

# เริ่มต้น cache ว่าง
invalidate_cache()
print(f"Cache size after clear: {len(_CACHE)}")

# Call 1 — miss (fetch from API)
t0 = time.time()
r1 = fetch_sheet("employees")
t1 = time.time() - t0
print(f"\nCall 1 (cache miss): {t1:.2f}s, rows={len(r1)}, cache size={len(_CACHE)}")

# Call 2 — hit (จาก cache)
t0 = time.time()
r2 = fetch_sheet("employees")
t2 = time.time() - t0
print(f"Call 2 (cache hit):  {t2:.2f}s, rows={len(r2)}, cache size={len(_CACHE)}")

# Call 3 — leads (cache miss)
t0 = time.time()
r3 = fetch_leads_by_month_tabs()
t3 = time.time() - t0
print(f"\nCall 3 (leads miss):  {t3:.2f}s, rows={len(r3)}, cache size={len(_CACHE)}")

# Call 4 — leads (cache hit)
t0 = time.time()
r4 = fetch_leads_by_month_tabs()
t4 = time.time() - t0
print(f"Call 4 (leads hit):   {t4:.2f}s, rows={len(r4)}, cache size={len(_CACHE)}")

# Summary
print(f"\n=== Summary ===")
print(f"fetch_sheet:           miss={t1:.2f}s  hit={t2:.2f}s  speedup={t1/max(t2,0.001):.0f}x")
print(f"fetch_leads_by_month:  miss={t3:.2f}s  hit={t4:.2f}s  speedup={t3/max(t4,0.001):.0f}x")
