# -*- coding: utf-8 -*-
"""
ปรับโฟลว์สเตปใหม่ (ก.ค.69): 17→15 สเตป, 4 เฟส
- เพิ่มจุดตรวจแยก 3 จุด (qc_repair/qc_paint/qc_wash) + สเตป wash (ชงล้าง)
- ตัด appraise/wait_paint/detail/qc(เดี่ยว)/rework/registration
- ย้ายรถเดิมที่อยู่สเตปเก่าเข้าสเตปใหม่อัตโนมัติ (STAGE_MAP)
ScanLog เป็น log ประวัติ → เปลี่ยนแค่ choices ไม่ remap ค่าเดิม (คงข้อเท็จจริงที่เคยสแกน)
"""
from django.db import migrations, models

NEW_CHOICES = [
    ("intake", "รับเข้า"),
    ("repair", "เช็คซ่อม"),
    ("qc_repair", "ซ่อมเสร็จ รอตรวจ"),
    ("parts", "สั่งของ/รออะไหล่"),
    ("upholstery", "งานเบาะ"),
    ("paint", "ทำสี/อู่สี"),
    ("qc_paint", "สีเสร็จ รอตรวจ"),
    ("film", "ติดฟิล์ม"),
    ("wash", "ชงล้าง"),
    ("qc_wash", "ล้างเสร็จ รอตรวจ"),
    ("show", "รถพร้อมขาย/หน้าร้าน"),
    ("reserve", "จอง"),
    ("finance", "จัดไฟแนนซ์"),
    ("closing", "ปิดการขาย"),
    ("sold", "ขายแล้ว"),
]

# สเตปเก่า -> สเตปใหม่ (สำหรับรถที่มีอยู่แล้ว) · สเตปที่ชื่อคงเดิมไม่ต้อง map
STAGE_MAP = {
    "appraise": "repair",       # ประเมินซ่อม → เข้าสายซ่อม
    "wait_paint": "paint",      # รอเข้าอู่สี → ทำสี
    "detail": "wash",           # ชง/ล้าง(ดีเทล) → ชงล้าง
    "qc": "qc_wash",            # รอตรวจ(เดิม = ตรวจสุดท้ายก่อนพร้อมขาย) → ล้างเสร็จรอตรวจ
    "rework": "repair",         # รอแก้ไข(ไม่ผ่าน) → เช็คซ่อมใหม่
    "registration": "show",     # ทะเบียน(ตัดออก) → รถพร้อมขาย
}


def remap_forward(apps, schema_editor):
    Car = apps.get_model("cars", "Car")
    for old, new in STAGE_MAP.items():
        Car.objects.filter(stage=old).update(stage=new)


def remap_backward(apps, schema_editor):
    # ไม่ย้อนกลับ (สเตปใหม่ควบหลายสเตปเก่า แยกกลับไม่ได้แน่นอน) — no-op
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("cars", "0007_car_drive_folder_id_car_plate_original"),
    ]

    operations = [
        migrations.AlterField(
            model_name="car",
            name="stage",
            field=models.CharField(
                choices=NEW_CHOICES, default="intake", max_length=20, verbose_name="สเตป"
            ),
        ),
        migrations.AlterField(
            model_name="scanlog",
            name="stage",
            field=models.CharField(choices=NEW_CHOICES, max_length=20, verbose_name="สเตป"),
        ),
        migrations.RunPython(remap_forward, remap_backward),
    ]
