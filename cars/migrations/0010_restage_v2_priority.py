# -*- coding: utf-8 -*-
"""restructure สเตปใหม่ (ก.ค.69) — 16 สเตป + ฟิลด์ priority (ความด่วน)
- เพิ่ม: photo_wait, paint_in, paint_out, qc_show, qc_release, release
- ตัด: qc_repair, qc_paint, qc_wash, paint, sold (→ remap)
- เพิ่มฟิลด์ Car.priority (default normal) · สีการ์ดมาจาก priority แทนวันค้าง
ScanLog = log ประวัติ → เปลี่ยนแค่ choices ไม่ remap ค่าเดิม
"""
from django.db import migrations, models

NEW_CHOICES = [
    ("intake", "รับเข้า"),
    ("photo_wait", "รถรอถ่ายรูป"),
    ("repair", "เช็คซ่อม"),
    ("parts", "สั่งของ/รออะไหล่"),
    ("upholstery", "งานเบาะ"),
    ("paint_in", "อู่สีใน"),
    ("paint_out", "อู่สีนอก"),
    ("film", "ติดฟิล์ม"),
    ("wash", "ชงล้าง"),
    ("qc_show", "รอตรวจรถขึ้นโชว์"),
    ("show", "รถพร้อมขาย/หน้าร้าน"),
    ("reserve", "จอง"),
    ("finance", "จัดไฟแนนซ์"),
    ("closing", "รอปิดการขาย"),
    ("qc_release", "ตรวจรถรอปล่อย"),
    ("release", "ปล่อยรถ"),
]

PRIORITY_CHOICES = [
    ("urgent_high", "ด่วนมาก"),
    ("urgent", "ด่วน"),
    ("normal", "ปกติ"),
    ("low", "ไม่เร่ง"),
    ("photo_wait", "รอถ่ายรูปยังไม่เสร็จ"),
]

# สเตปเก่า -> ใหม่ (รถที่มีอยู่)
STAGE_MAP = {
    "qc_repair": "repair",       # จุดตรวจกลางเดิม → กลับสายซ่อม
    "qc_paint": "paint_out",     # ตรวจสีเดิม → อู่สีนอก
    "qc_wash": "wash",           # ตรวจล้างเดิม → ล้าง
    "paint": "paint_out",        # ทำสีเดิม → อู่สีนอก
    "sold": "release",           # ขายแล้วเดิม → ปล่อยรถ (จบ)
}


def remap_forward(apps, schema_editor):
    Car = apps.get_model("cars", "Car")
    for old, new in STAGE_MAP.items():
        Car.objects.filter(stage=old).update(stage=new)


def remap_backward(apps, schema_editor):
    pass  # ไม่ย้อนกลับ (ควบหลายสเตป)


class Migration(migrations.Migration):

    dependencies = [
        ("cars", "0009_alter_car_stage_alter_scanlog_stage"),
    ]

    operations = [
        migrations.AddField(
            model_name="car",
            name="priority",
            field=models.CharField(
                choices=PRIORITY_CHOICES, default="normal", max_length=16, verbose_name="ความด่วน"
            ),
        ),
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
