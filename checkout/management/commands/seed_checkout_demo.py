"""สร้างข้อมูลตัวอย่าง "เบิก-คืนรถ" ให้ดูหน้าตาระบบ — จำลองจาก log กลุ่ม LINE จริง (ส.ค.69)

    python manage.py seed_checkout_demo          # สร้าง (ล้างของเดิมก่อน)
    python manage.py seed_checkout_demo --keep   # ไม่ล้างของเดิม

ตั้งใจให้ครบทุกสถานะที่เกิดจริง: คืนแล้ว · ยังไม่คืน · ค้างข้ามคืน · มีความเสียหาย · ขอเบิกน้ำมัน
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from cars.models import Car
from checkout.models import CarMovement, MovementPhoto

# (ชื่อคนเบิก, ประเภทงาน, ปลายทาง, ชม.ที่ผ่านมาตอนเบิก, ใช้เวลากี่นาที (None=ยังไม่คืน),
#  ไมล์ออก, ขอน้ำมัน, เสียหาย, หมายเหตุ)  — อิงข้อความจริงในกลุ่ม
DEMO = [
    ("อาร์ท",   "service",  "ศูนย์ฮอนด้าแสงหงษ์",     30, 45,   88120, False, False, "นำรถไปตั้งศูนย์"),
    ("ก้าว",    "transport", "ขนส่งชลบุรี",           27, 92,   45260, True,  False, "เอารถไปตรวจขนส่ง แล้วเลยไปศูนย์"),
    ("ปุ๊กมิน", "move",     "สาขาชลบุรี",             25, 70,   12040, False, False, "เบิกรถรอซ่อมกลับสาขาชลบุรี"),
    ("ใหม่",    "transport", "ขนส่ง",                  8,  55,   61330, False, False, ""),
    ("บิลลี่",  "customer", "แปลงยาว",                6,  None, 77410, False, False, "ไปส่งลูกค้าที่แปลงยาว"),
    ("มิว",     "customer", "พัทยา",                  5,  None, 30880, True,  False, "ไปส่งลูกค้า และนำรถเทิร์นกลับ"),
    ("อุ้ม",    "finance",  "ไฟแนนซ์ กรุงเทพฯ",       28, None, 55120, False, False, "เบิกไปจัดไฟแนนซ์ — ยังไม่คืนข้ามคืน"),
    ("โสภา",    "errand",   "ฮาร์ดแวร์เฮ้าส์",         3,  40,   9870,  False, True,  "ไปซื้ออุปกรณ์ไฟ · กลับมามีรอยขีดข้างซ้าย"),
]


class Command(BaseCommand):
    help = "สร้างข้อมูลตัวอย่างเบิก-คืนรถ (จำลองจาก log กลุ่ม LINE จริง)"

    def add_arguments(self, parser):
        parser.add_argument("--keep", action="store_true", help="ไม่ล้างข้อมูลเดิม")

    def handle(self, *args, **opts):
        if not opts.get("keep"):
            n = CarMovement.objects.count()
            CarMovement.objects.all().delete()
            self.stdout.write(f"ล้างของเดิม {n} รายการ")

        cars = list(Car.objects.all()[:len(DEMO)])
        if not cars:
            self.stdout.write(self.style.ERROR("ไม่มีรถในระบบ — รัน seed_demo ก่อน"))
            return

        now = timezone.now()
        made = 0
        for i, (who, pkey, dest, hrs_ago, used_min, odo, fuel, dmg, note) in enumerate(DEMO):
            car = cars[i % len(cars)]
            if CarMovement.objects.filter(car=car, returned_at__isnull=True).exists():
                continue          # คันนี้มีรอบค้างอยู่แล้ว ข้าม (กันชนกฎ "เบิกซ้ำไม่ได้")
            from checkout import constants as C
            out_at = now - timedelta(hours=hrs_ago)
            m = CarMovement(
                car=car, plate_text=car.plate or "",
                borrower_name=who, purpose_key=pkey, purpose=C.PURPOSE_NAME[pkey],
                destination=dest, checked_out_at=out_at, odo_out=odo,
                fuel_requested=fuel, note=note,
                status=CarMovement.PENDING_HUMAN,
            )
            if used_min is not None:
                m.returned_at = out_at + timedelta(minutes=used_min)
                m.odo_in = odo + 20 + i * 37
                m.damage_reported = dmg
                m.status = CarMovement.PENDING_HUMAN if dmg else CarMovement.APPROVED_HUMAN
                m.approved_by = "" if dmg else "หัวหน้า (รับทราบในกลุ่ม)"
            m.save()
            # ไฟล์หลักฐาน — ใส่ path ตัวอย่างพอให้ตัวนับรูปมีค่า (ไฟล์จริงอาจไม่มีในเครื่อง)
            for k in range(3):
                p = MovementPhoto(movement=m, phase=MovementPhoto.OUT)
                p.file.name = f"cars/{car.code}/demo_out_{k+1}.jpg"
                p.save()
            if m.returned_at:
                for k in range(2):
                    p = MovementPhoto(movement=m, phase=MovementPhoto.IN)
                    p.file.name = f"cars/{car.code}/demo_in_{k+1}.jpg"
                    p.save()
            made += 1
        self.stdout.write(self.style.SUCCESS(
            f"สร้างตัวอย่าง {made} รอบ · ยังไม่คืน {CarMovement.objects.filter(returned_at__isnull=True).count()} คัน"))
