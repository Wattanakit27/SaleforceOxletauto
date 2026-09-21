# -*- coding: utf-8 -*-
"""21 ก.ย.69 — แถวพนักงานที่ "ระบบเพิ่มให้เอง" ต้องไม่อยู่ในระบบเช็คชื่อจนกว่าคนจะยืนยัน

เจ้าของแจ้ง (เห็นตารางเช็คชื่อ 21/09): *"อะไรรรร บางคนไม่อยู่ในกลุ่มด้วยซ้ำ"*
- `Sirun` (พิมพ์ในกลุ่ม Branding) · `โด่ง` (กลุ่มรับ-ส่งระหว่างสาขา) ถูกระบบสร้างเป็นพนักงาน
  ตอนพิมพ์ใน **กลุ่มอื่น** แล้วไปโผล่ในตารางเช็คชื่อ + ถูกแท็กทั้ง 2 รอบทุกเช้า
- ทั้งคู่ไม่มีตำแหน่ง ไม่มีเวลาเข้างาน และ **ไม่เคยเช็คชื่อเลยสักครั้ง**

ปิด `track_checkin` ให้เฉพาะแถวแบบนั้น (auto + ไม่มีเวลาเข้างาน + ไม่เคยเช็คชื่อ)
— แถวที่คนกรอกเองหรือมาจากชีต **ไม่แตะ** · เติมครั้งเดียวตอน migrate เหมือน 0015
"""
from django.db import migrations


def close(apps, schema_editor):
    Employee = apps.get_model("checkout", "Employee")
    CheckIn = apps.get_model("checkout", "CheckIn")
    has_checkin = set(CheckIn.objects.values_list("employee_id", flat=True))
    ids = [e.id for e in Employee.objects.filter(source="auto", track_checkin=True)
           if not (e.work_start or "").strip() and e.id not in has_checkin]
    if ids:
        Employee.objects.filter(id__in=ids).update(track_checkin=False)


class Migration(migrations.Migration):
    dependencies = [("checkout", "0020_fbchat_fbprofile")]
    # ย้อนกลับ = ไม่ต้องทำอะไร (ติ๊กกลับเองได้ในหน้าพนักงาน)
    operations = [migrations.RunPython(close, migrations.RunPython.noop)]
