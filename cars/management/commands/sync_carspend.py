"""
sync_carspend — ดึงรถสดจากเว็บ Car Spend เข้าตาราง Car โดยตรง (ไม่ต้อง export zip)

ใช้:
  python manage.py sync_carspend --dry-run           # ดูก่อนว่าจะเกิดอะไร ไม่เขียน DB
  python manage.py sync_carspend                     # สต็อกปัจจุบัน (236 คัน · ~6 นาที)
  python manage.py sync_carspend --photos            # + โหลดรูปปกเข้า storage
  python manage.py sync_carspend --status sold       # รถขายแล้ว (~3,540 คัน · ~75 นาที)
  python manage.py sync_carspend --limit 5           # ทดสอบ

ต้องตั้ง env: CARSPEND_USER / CARSPEND_PASS

เป็นพี่น้องกับ import_cars (ตัวที่อ่าน zip) — ใช้ mapping/helper ชุดเดียวกันทั้งหมด
(STATUS_TO_STAGE, BRANCH_MAP, _parse_date, _int, _model) เพื่อไม่ให้กติกาแตกเป็นสองมาตรฐาน

พฤติกรรม (เหมือน import_cars):
- code = "รหัสรถ" จริง (เช่น CS03754) → รันซ้ำ = อัปเดต ไม่สร้างซ้ำ
- "สเตป/วันรับเข้า" ตั้งเฉพาะตอนสร้างใหม่ → re-sync ไม่รีเซ็ตสเตปที่หน้างานขยับไปแล้ว
- ข้อมูลดิบเก็บครบใน Car.extra

★ ระวัง: ต้นทางกรอกรหัสรถซ้ำได้ (เจอ 2 คู่ที่เป็นคนละคันจริงๆ) แต่ Car.code เป็น
  primary key → คันหลังจะได้ suffix "-2" พร้อม warning (ไม่ปล่อยให้ข้อมูลหายเงียบ)
"""
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from cars.models import Branch, Car
from cars.carspend import STATUS_FILTER, CarSpend, CarSpendError

# ใช้ mapping/helper ชุดเดียวกับตัวนำเข้าจาก zip — อย่า copy มาแก้แยก
from .import_cars import BRANCH_MAP, STATUS_TO_STAGE, _int, _model, _parse_date


class Command(BaseCommand):
    help = "ดึงรถสดจาก Car Spend (autosoftware.co.th) เข้าตาราง Car"

    def add_arguments(self, p):
        p.add_argument("--status", default="stock", choices=sorted(STATUS_FILTER),
                       help="stock = สต็อกปัจจุบัน (default) · sold = ขายแล้ว (ไม่รวมใน stock)")
        p.add_argument("--limit", type=int, default=0, help="จำกัดจำนวน (ทดสอบ)")
        p.add_argument("--delay", type=float, default=0.3, help="หน่วงระหว่าง request วินาที")
        p.add_argument("--photos", action="store_true",
                       help="โหลดรูปปกเข้า storage ด้วย (ข้ามคันที่มีรูปแล้ว)")
        p.add_argument("--dry-run", action="store_true", help="ไม่เขียน DB แค่รายงานว่าจะทำอะไร")

    def handle(self, *args, **o):
        user = os.getenv("CARSPEND_USER")
        pwd = os.getenv("CARSPEND_PASS")
        dry = o["dry_run"]

        try:
            client = CarSpend(user, pwd, delay=o["delay"])
        except CarSpendError as e:
            raise CommandError(str(e))

        if not dry:
            for code, name in BRANCH_MAP.values():
                Branch.objects.get_or_create(code=code, defaults={"name": name})

        now = timezone.now()
        created = updated = skipped = errors = renamed = 0
        by_stage, unknown_status, unknown_branch = {}, {}, {}

        self.stdout.write(f"ดึงสถานะ: {o['status']}" + ("  [DRY RUN — ไม่เขียน DB]" if dry else ""))

        for n, car in enumerate(client.iter_cars(STATUS_FILTER[o["status"]], o["limit"]), 1):
            d = car["detail"]
            code = (d.get("รหัสรถ") or "").strip()[:12]
            if not code:
                skipped += 1
                continue

            try:
                src_status = car.get("status") or ""
                stage = STATUS_TO_STAGE.get(src_status, "intake")
                if src_status and src_status not in STATUS_TO_STAGE:
                    unknown_status[src_status] = unknown_status.get(src_status, 0) + 1

                br_name = car.get("branch") or ""
                if br_name not in BRANCH_MAP:
                    unknown_branch[br_name] = unknown_branch.get(br_name, 0) + 1
                br_code = BRANCH_MAP.get(br_name, ("BK", ""))[0]

                date_in = _parse_date(d.get("วันที่ซื้อรถเข้า"))
                date_in_dt = (timezone.make_aware(
                    timezone.datetime(date_in.year, date_in.month, date_in.day))
                    if date_in else now)

                resolved = self._resolve_code(code, car["key"], dry)
                if resolved is None:
                    skipped += 1
                    continue
                renamed += int(resolved != code)
                code = resolved

                always = dict(
                    branch=br_code,
                    plate=(car.get("plate") or "")[:20],
                    brand=(car.get("brand") or "").strip()[:40],
                    model=_model(car),
                    year=_int(d.get("รถปี ค.ศ.")),
                    color=(d.get("สี") or "").strip()[:30],
                    km=_int(d.get("เลขไมล์ปัจจุบัน")),
                    tax_due_date=_parse_date(d.get("วันที่ต่อภาษีรถยนต์")),
                    note=(car.get("note") or "")[:5000],
                    extra={
                        "import_status": src_status,
                        "import_source": "carspend",
                        "price": car.get("price"),
                        "price_num": _int(car.get("price")),
                        "name": car.get("name"),
                        "source_key": car["key"],
                        "detail": d,
                        "owner": car.get("owner") or {},
                        "image_urls": car.get("image_urls") or [],
                        "image_count": len(car.get("image_urls") or []),
                    },
                )
                # "ขายแล้ว" ที่ต้นทาง = จบจริง → status=sold (หลุดบอร์ด) ตามกติกาของระบบ
                if stage == "sold":
                    always["status"] = "sold"

                if dry:
                    exists = Car.objects.filter(code=code).exists()
                    created += int(not exists)
                    updated += int(exists)
                else:
                    with transaction.atomic():
                        _obj, is_new = Car.objects.update_or_create(
                            code=code, defaults=always,
                            create_defaults={**always, "stage": stage,
                                             "stage_since": now, "date_in": date_in_dt},
                        )
                    created += int(is_new)
                    updated += int(not is_new)
                    if o["photos"]:
                        self._save_cover(client, _obj, car)

                by_stage[stage] = by_stage.get(stage, 0) + 1
                if n % 25 == 0:
                    self.stdout.write(f"  ... {n} คัน")
            except Exception as e:
                errors += 1
                self.stderr.write(f"  ! {code}: {e}")

        self.stdout.write(self.style.SUCCESS(
            f"เสร็จ — สร้างใหม่ {created} · อัปเดต {updated} · ข้าม {skipped} · error {errors}"))
        if renamed:
            self.stdout.write(self.style.WARNING(
                f"รหัสรถซ้ำที่ต้นทาง {renamed} คัน → เติม suffix ให้ (ดู warning ด้านบน)"))
        self.stdout.write("ตามสเตป: " + ", ".join(f"{k}={v}" for k, v in sorted(by_stage.items())))
        for label, d_ in (("สถานะที่ยังไม่ได้ map", unknown_status), ("สาขาที่ไม่รู้จัก", unknown_branch)):
            if d_:
                self.stdout.write(self.style.WARNING(
                    f"{label}: " + ", ".join(f"{k or '(ว่าง)'}={v}" for k, v in d_.items())))

    # ------------------------------------------------------------------

    def _resolve_code(self, code, src_key, dry):
        """
        Car.code เป็น primary key แต่ต้นทางกรอกรหัสซ้ำได้ (คนละคัน รหัสเดียวกัน)
        - แถวเดิมที่มาจาก key เดียวกัน → ใช้ code เดิม (อัปเดตทับ)
        - รหัสชนกับคันอื่น → เติม -2, -3, ... ให้ (ไม่ทับข้อมูลคันอื่น ไม่ทำให้รถหาย)
        """
        existing = Car.objects.filter(code=code).first()
        if existing is None or (existing.extra or {}).get("source_key") == src_key:
            return code
        base = code[:10]
        for i in range(2, 10):
            alt = f"{base}-{i}"
            other = Car.objects.filter(code=alt).first()
            if other is None or (other.extra or {}).get("source_key") == src_key:
                self.stderr.write(self.style.WARNING(
                    f"  รหัส {code} ซ้ำกับคันอื่นที่ต้นทาง → ใช้ {alt} แทน"))
                return alt
        self.stderr.write(self.style.ERROR(f"  รหัส {code} ซ้ำเกิน 8 คัน — ข้าม"))
        return None

    def _save_cover(self, client, car_obj, car):
        """
        โหลดรูปปก (รูปแรกของอัลบัม) ลง "ดิสก์ VPS" — ข้ามคันที่มีรูปแล้ว

        เขียนผ่าน FileSystemStorage ตรง ไม่ใช้ default_storage เพราะถ้าตั้ง GDRIVE_* ไว้
        default_storage จะเป็น Drive แต่กติกาของโปรเจกต์คือ "รูปหน้าปกรถ → ดิสก์เสมอ"
        (ไฟล์เล็ก ไม่ควรพึ่งบริการนอก) · ชื่อไฟล์มี "/" → GoogleDriveStorage.url()
        เสิร์ฟจาก MEDIA_URL ให้เอง เหมือนรูปที่อัปผ่าน api_upload target=disk
        """
        if car_obj.photo:
            return
        imgs = car.get("image_urls") or []
        if not imgs:
            return
        import re
        import uuid

        from django.conf import settings
        from django.core.files.base import ContentFile
        from django.core.files.storage import FileSystemStorage

        cover = imgs[0]
        try:
            data = client.download(cover["full"])
            fs = FileSystemStorage(location=settings.MEDIA_ROOT, base_url=settings.MEDIA_URL)
            safe = re.sub(r"[^A-Za-z0-9._-]", "_", cover["file"])[-50:]
            car_obj.photo.name = fs.save(
                f"cars/{car_obj.code}/{uuid.uuid4().hex[:8]}-{safe}", ContentFile(data))
            car_obj.save(update_fields=["photo"])
        except Exception as e:
            self.stderr.write(f"  ! รูป {car_obj.code}: {e}")
