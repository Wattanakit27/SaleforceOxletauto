"""
import_cars — นำเข้าเคสรถจริงจากไฟล์ export (zip ที่มี cars.json + images/)

ใช้:
  python manage.py import_cars "D:\\oxlet_cars_2026-06-23.zip"
  python manage.py import_cars <zip> --images        # อัปรูปขึ้น storage ด้วย (ต้องตั้ง storage ให้ใช้ได้ก่อน)
  python manage.py import_cars <zip> --limit 5        # ทดสอบ 5 คันแรก

- โค้ดรถ = "รหัสรถ" จริง (เช่น CS03776) → idempotent (รันซ้ำ = อัปเดต ไม่ซ้ำ)
- status → สเตป · สาขา → Branch (บ้านเก่า=BK, อ่อนนุช=ON)
- detail/owner/price/image_files เก็บครบใน Car.extra (เป๊ะ ไม่ตกหล่น)
"""
import json
import re
import zipfile
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from cars.models import Branch, Car

STATUS_TO_STAGE = {
    "อยู่ระหว่างการซ่อม": "repair",
    "พร้อมขาย": "show",
    "จองแล้ว": "reserve",
    "จัดไฟแนนซ์": "finance",
    "รอปิดการขาย": "closing",
}

# ชื่อสาขา (จาก export) → (code prefix, ชื่อ)
BRANCH_MAP = {
    "สาขา บ้านเก่า": ("BK", "สาขา บ้านเก่า"),
    "สาขา อ่อนนุช": ("ON", "สาขา อ่อนนุช"),
}

_DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")


def _parse_date(s):
    """ดึงวันที่ d/m/Y จากสตริง (มีข้อความปนได้) → date หรือ None"""
    if not s:
        return None
    m = _DATE_RE.search(str(s))
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y > 2400:  # เผื่อ พ.ศ.
        y -= 543
    try:
        return datetime(y, mo, d).date()
    except ValueError:
        return None


def _int(s):
    if s in (None, ""):
        return None
    try:
        return int(re.sub(r"[^\d]", "", str(s)) or 0) or None
    except ValueError:
        return None


def _plate(car):
    o = car.get("owner") or {}
    p = (o.get("หมายเลขทะเบียน") or "").strip()
    if p:
        return p[:20]
    raw = (car.get("plate") or "").split(" (")[0].strip()
    return raw[:20]


def _model(car):
    d = car.get("detail") or {}
    main = (d.get("รุ่นรถ") or "").strip()
    sub = (d.get("รุ่นย่อย") or "").strip()
    out = (main + (" " + sub if sub else "")).strip()
    if not out:  # fallback จาก top-level model "ISUZU > D-MAX >"
        out = (car.get("model") or "").replace(">", " ").strip()
    return out[:60]


class Command(BaseCommand):
    help = "นำเข้าเคสรถจริงจากไฟล์ zip (cars.json + images/)"

    def add_arguments(self, parser):
        parser.add_argument("zip_path")
        parser.add_argument("--images", action="store_true", help="อัปรูปขึ้น storage ด้วย")
        parser.add_argument("--limit", type=int, default=0, help="จำกัดจำนวน (ทดสอบ)")

    def handle(self, *args, **opts):
        zip_path = opts["zip_path"]
        try:
            z = zipfile.ZipFile(zip_path)
        except Exception as e:
            raise CommandError(f"เปิด zip ไม่ได้: {e}")

        cars = json.loads(z.read("cars.json").decode("utf-8")).get("cars", [])
        if opts["limit"]:
            cars = cars[: opts["limit"]]
        self.stdout.write(f"พบ {len(cars)} เคสใน cars.json")

        # map ชื่อไฟล์รูป (hash) → path เต็มใน zip (สำหรับ --images)
        img_index = {}
        for n in z.namelist():
            if n.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                img_index[n.rsplit("/", 1)[-1]] = n

        # สร้างสาขา
        for code, name in BRANCH_MAP.values():
            Branch.objects.get_or_create(code=code, defaults={"name": name})

        now = timezone.now()
        created = updated = skipped = errors = 0
        by_stage = {}
        for car in cars:
            d = car.get("detail") or {}
            code = (d.get("รหัสรถ") or car.get("key") or "").strip()[:12]
            if not code:
                skipped += 1
                continue
            try:
                stage = STATUS_TO_STAGE.get(car.get("status", ""), "intake")
                br_code = BRANCH_MAP.get(car.get("branch", ""), ("BK", ""))[0]
                date_in = _parse_date(d.get("วันที่ซื้อรถเข้า"))
                date_in_dt = (timezone.make_aware(datetime(date_in.year, date_in.month, date_in.day))
                              if date_in else now)
                defaults = dict(
                    branch=br_code,
                    plate=_plate(car),
                    brand=(car.get("brand") or "").strip()[:40],
                    model=_model(car),
                    year=_int(d.get("รถปี ค.ศ.")),
                    color=(d.get("สี") or "").strip()[:30],
                    km=_int(d.get("เลขไมล์ปัจจุบัน")),
                    stage=stage,
                    stage_since=now,
                    date_in=date_in_dt,
                    status="active",
                    tax_due_date=_parse_date(d.get("วันที่ต่อภาษีรถยนต์")),
                    note=(car.get("note") or "")[:5000],
                    extra={
                        "import_status": car.get("status"),
                        "price": car.get("price"),
                        "price_num": car.get("price_num"),
                        "name": car.get("name"),
                        "source_key": car.get("key"),
                        "detail": d,
                        "owner": car.get("owner") or {},
                        "image_files": car.get("image_files") or [],
                        "image_count": car.get("image_count") or 0,
                    },
                )
                obj, is_new = Car.objects.update_or_create(code=code, defaults=defaults)
                created += int(is_new)
                updated += int(not is_new)
                by_stage[stage] = by_stage.get(stage, 0) + 1

                if opts["images"]:
                    self._upload_images(z, img_index, obj, car)
            except Exception as e:
                errors += 1
                self.stderr.write(f"  ! {code}: {e}")

        self.stdout.write(self.style.SUCCESS(
            f"เสร็จ — สร้างใหม่ {created} · อัปเดต {updated} · ข้าม {skipped} · error {errors}"))
        self.stdout.write("ตามสเตป: " + ", ".join(f"{k}={v}" for k, v in by_stage.items()))

    def _upload_images(self, z, img_index, car_obj, car):
        """อัปรูปคันนี้ขึ้น storage (รูปแรก = car.photo) — ใช้เมื่อ --images และ storage พร้อม"""
        from django.core.files.base import ContentFile
        files = car.get("image_files") or []
        first = True
        for fn in files:
            path = img_index.get(fn)
            if not path:
                continue
            data = z.read(path)
            if first:
                car_obj.photo.save(fn, ContentFile(data), save=True)
                first = False
        # (รูปที่เหลือ: ปัจจุบันเก็บแค่รายการใน extra.image_files — ขยายเป็นแกลเลอรีภายหลังได้)
