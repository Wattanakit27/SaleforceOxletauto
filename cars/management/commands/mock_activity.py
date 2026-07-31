"""
mock_activity — สร้าง "ข้อมูลจำลองความเคลื่อนไหว" ให้รถที่มีอยู่แล้วในระบบ (ไม่เพิ่มจำนวนรถ)

ทำอะไร (ต่อรถ 1 คัน · คงสเตปปัจจุบันไว้ ไม่เปลี่ยน distribution):
  - สุ่ม date_in (วันรับเข้า) ย้อนหลัง + stage_since (เข้าสเตปปัจจุบันเมื่อไหร่) → flag เขียว/เหลือง/แดง คละกัน
  - frontline_at (ขึ้นหน้าร้าน) ให้รถที่ถึงสเตป show ขึ้นไป → T2L คำนวณได้จริง
  - สถานะ (sold สำหรับสเตป sold · สุ่ม hold เล็กน้อย) + tax_due_date บางคัน (โชว์ป้ายภาษีใกล้หมด/หมด)
  - ScanLog ไทม์ไลน์การเปลี่ยนสเตป (intake → ... → สเตปปัจจุบัน) worker_id='mock'

ใช้:
  python manage.py mock_activity            # จำลองให้ทุกคัน (ลบ log จำลองเก่า worker_id='mock' ก่อน)
  python manage.py mock_activity --keep-logs  # ไม่ลบ log จำลองเดิม (เติมทับ)

idempotent: รันซ้ำได้ — ลบ ScanLog ที่ worker_id='mock' ทิ้งก่อนสร้างใหม่ (log จริงไม่โดนแตะ)
* รันบน DB ไหนก็จำลองให้รถใน DB นั้น (local sqlite หรือ prod เมื่อต่อ DB แล้ว) *
"""
import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from cars import constants as C
from cars.models import Car, ScanLog

WORKERS = ["ช่างเอก", "ช่างบี", "เซลล์โอ๊ต", "เซลล์เฟิร์ส", "ฝ่ายทะเบียนแนน", "QC มด", "อู่สมชาย", "ดีเทลโจ"]
_SHOW_IDX = C.STAGE_ORDER[C.FRONTLINE_STAGE]   # index ของสเตป "show" (จุดจบ T2L)


def _stage_path(stage):
    """เส้นทางสเตปจำลอง intake → ... → สเตปปัจจุบัน (3-6 ก้าว) สำหรับสร้างไทม์ไลน์"""
    idx = C.STAGE_ORDER.get(stage, 0)
    if idx == 0:
        return [stage]
    before = [k for k in C.STAGE_KEYS if 0 < C.STAGE_ORDER[k] < idx]
    pick = random.sample(before, k=min(len(before), random.randint(1, 3))) if before else []
    path = ["intake"] + sorted(pick, key=lambda k: C.STAGE_ORDER[k]) + [stage]
    # dedup คงลำดับ
    seen, out = set(), []
    for k in path:
        if k not in seen:
            seen.add(k); out.append(k)
    return out


class Command(BaseCommand):
    help = "สร้างข้อมูลจำลองความเคลื่อนไหว (วันที่/สเตป/ประวัติสแกน) ให้รถที่มีอยู่"

    def add_arguments(self, parser):
        parser.add_argument("--keep-logs", action="store_true", help="ไม่ลบ ScanLog จำลองเดิม")

    @transaction.atomic
    def handle(self, *args, **opts):
        now = timezone.now()
        cars = list(Car.objects.filter(deleted_at__isnull=True))
        if not cars:
            self.stdout.write(self.style.WARNING("ไม่มีรถใน DB — import รถก่อน (import_cars / seed_demo)"))
            return

        if not opts["keep_logs"]:
            n_del = ScanLog.objects.filter(worker_id="mock").delete()[0]
            self.stdout.write(f"ลบ ScanLog จำลองเก่า {n_del} รายการ")

        flags = {"ok": 0, "amber": 0, "red": 0}
        n_logs = 0
        for car in cars:
            # อายุค้างสเตป → flag คละกัน (50% ok / 30% amber / 20% red)
            roll = random.random()
            if roll < 0.50:
                days_in = random.randint(0, 1)
            elif roll < 0.80:
                days_in = random.randint(C.STUCK_AMBER_DAYS, C.STUCK_RED_DAYS)   # 2-3
            else:
                days_in = random.randint(C.STUCK_RED_DAYS + 1, 22)               # 4-22 (แดง)
            stage_since = now - timedelta(days=days_in, hours=random.randint(0, 23))
            total_age = days_in + random.randint(2, 90)
            date_in = now - timedelta(days=total_age, hours=random.randint(0, 23))

            car.date_in = date_in
            car.stage_since = stage_since
            # frontline_at เฉพาะรถที่ถึง show ขึ้นไป (T2L = 2-9 วันหลังรับเข้า)
            if C.STAGE_ORDER.get(car.stage, 0) >= _SHOW_IDX:
                t2l = random.randint(2, max(2, min(9, total_age - 1)))
                car.frontline_at = date_in + timedelta(days=t2l)
            else:
                car.frontline_at = None
            # สถานะ
            if car.stage == "release":       # ปล่อยรถ = จบ
                car.status = "sold"
            elif random.random() < 0.05:
                car.status = "hold"
            else:
                car.status = "active"
            # ภาษี — 25% มีวันครบกำหนด (บางคันใกล้หมด/หมดแล้ว → โชว์ป้าย)
            if random.random() < 0.25:
                car.tax_due_date = (now + timedelta(days=random.randint(-40, 150))).date()
            car.save(update_fields=["date_in", "stage_since", "frontline_at", "status", "tax_due_date"])
            flags[car.flag] = flags.get(car.flag, 0) + 1

            # ไทม์ไลน์ ScanLog (intake → ... → สเตปปัจจุบัน)
            path = _stage_path(car.stage)
            span = (stage_since - date_in).total_seconds()
            for i, st in enumerate(path):
                ts = stage_since if i == len(path) - 1 else date_in + timedelta(seconds=span * i / max(1, len(path) - 1))
                log = ScanLog.objects.create(
                    car=car, stage=st, worker_name=random.choice(WORKERS),
                    worker_id="mock", note=random.choice(["", "", "ตามคิว", "เร่งด่วน", "รอของ"]),
                )
                ScanLog.objects.filter(pk=log.pk).update(created_at=ts)   # bypass auto_now_add
                n_logs += 1

        t2ls = [c.t2l for c in Car.objects.filter(deleted_at__isnull=True) if c.t2l is not None]
        avg = round(sum(t2ls) / len(t2ls), 1) if t2ls else None
        self.stdout.write(self.style.SUCCESS(
            f"จำลองเสร็จ: {len(cars)} คัน | ScanLog {n_logs} รายการ | "
            f"flag เขียว {flags['ok']} / เหลือง {flags['amber']} / แดง {flags['red']} | "
            f"T2L เฉลี่ย {avg} วัน (จากรถที่ขึ้นหน้าร้านแล้ว)"
        ))
