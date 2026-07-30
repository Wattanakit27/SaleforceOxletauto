"""
seed_demo — สร้างข้อมูลตัวอย่าง: สาขา, กลุ่มบทบาท 7 บทบาท, รถตัวอย่างหลายสเตป
รัน: python manage.py seed_demo
"""
from datetime import timedelta

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.utils import timezone

from cars import constants as C
from cars import roles
from cars.models import Branch, Car, ScanLog

DEMO = [
    # (branch, brand, model, year, color, plate, stage, days_ago_in)
    ("CB", "Toyota", "Altis", 2019, "ขาว", "1กก1234", "repair", 6),
    ("CB", "Honda", "Civic", 2020, "ดำ", "2ขข5678", "paint", 9),
    ("CB", "Mazda", "Mazda3", 2018, "แดง", "3คค9012", "wash", 3),
    ("SP", "Toyota", "Revo", 2021, "เทา", "4งง3456", "qc_paint", 12),
    ("SP", "Mitsubishi", "Xpander", 2022, "เงิน", "5จจ7890", "show", 5),
    ("SP", "Nissan", "Almera", 2021, "น้ำเงิน", "6ฉฉ2345", "reserve", 8),
    ("CB", "Honda", "City", 2020, "ขาว", "7ชช6789", "qc_wash", 2),
    ("CB", "Toyota", "Fortuner", 2019, "ดำ", "8ซซ1122", "sold", 20),
]


class Command(BaseCommand):
    help = "สร้างข้อมูลตัวอย่าง (สาขา + บทบาท + รถ)"

    def handle(self, *args, **opts):
        # สาขา
        for code, name in C.BRANCH_CHOICES:
            Branch.objects.get_or_create(code=code, defaults={"name": name})
        # กลุ่มบทบาท 7 บทบาท
        for key, _ in roles.ROLES:
            Group.objects.get_or_create(name=key)
        self.stdout.write(self.style.SUCCESS(f"สร้างสาขา {len(C.BRANCH_CHOICES)} + บทบาท {len(roles.ROLES)} แล้ว"))

        if Car.objects.exists():
            self.stdout.write(self.style.WARNING("มีรถอยู่แล้ว — ข้ามการ seed รถ"))
            return

        now = timezone.now()
        for br, brand, model, year, color, plate, stage, days in DEMO:
            car = Car(branch=br, brand=brand, model=model, year=year,
                      color=color, plate=plate)
            car.date_in = now - timedelta(days=days)
            car.save()
            # เดินสเตปจาก intake -> stage เป้าหมาย (log ครบ)
            target = C.STAGE_ORDER[stage]
            for i, key in enumerate(C.STAGE_KEYS):
                if i > target:
                    break
                car.stage = key
                car.stage_since = now - timedelta(days=max(0, days - i))
                if key == C.FRONTLINE_STAGE and not car.frontline_at:
                    car.frontline_at = car.stage_since
                if key == "sold":
                    car.status = "sold"
                car.save()
                ScanLog.objects.create(car=car, stage=key, worker_name="ตัวอย่าง")
            self.stdout.write(f"  + {car.code} {brand} {model} -> {car.stage_name}")

        self.stdout.write(self.style.SUCCESS(f"สร้างรถตัวอย่าง {len(DEMO)} คันแล้ว"))
