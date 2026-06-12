"""ดึงข้อมูลทุกชีต (leads 15k + sales/bookings/live/employees) → ไฟล์ JSON เดียว"""
import os, sys, json, time, django
from pathlib import Path
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
django.setup()

from dashboard.services.google_sheets import fetch_all_sheets, invalidate_cache
from dashboard.services.fetch_dashboard import bangkok_now

now = bangkok_now()
print(f"กำลังดึงข้อมูล... ({now:%Y-%m-%d %H:%M})")
t0 = time.time()
invalidate_cache()
raw = fetch_all_sheets()
print(f"  อ่านเสร็จใน {time.time()-t0:.1f}s")

out = {
    "_meta": {
        "exported_at": now.isoformat(),
        "rows": {k: len(v) for k, v in raw.items()},
    },
    **{k: v for k, v in raw.items()},
}

out_dir = BASE / "exports"
out_dir.mkdir(exist_ok=True)
out_path = out_dir / "sheets_data.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, default=str)

size_mb = out_path.stat().st_size / 1024 / 1024
print(f"\nเสร็จ → {out_path}")
print(f"  ขนาดไฟล์: {size_mb:.1f} MB")
print(f"  จำนวนแถวต่อชีต:")
for k, v in out["_meta"]["rows"].items():
    print(f"    {k:<18} {v:>6} แถว")
