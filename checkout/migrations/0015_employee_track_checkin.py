# -*- coding: utf-8 -*-
"""ช่อง "ต้องเช็คชื่อเข้างาน" + เติมค่าย้อนหลังให้แถวที่ยังไม่ได้กรอกอะไรเลย

★ 16 ก.ย.69 เจ้าของแจ้ง: *"คนที่ไม่มีชื่อเล่นหรืออะไรเลย จะนับว่าเป็นผู้บริหาร
  ซึ่งเราจะไม่ใช้เก็บข้อมูลกัน"* — คนกลุ่มนี้เคยค้างอยู่ในพาเนลเช็คชื่อทุกวัน
  ในกลุ่ม "ยังไม่ได้ตั้งเวลาเข้างาน" ทั้งที่ไม่ได้ตั้งใจให้เช็คชื่อตั้งแต่แรก

การเติมย้อนหลังนี้ **ทำครั้งเดียวกับแถวที่มีอยู่ตอน migrate** เท่านั้น —
คนที่เพิ่มเข้ามาทีหลังได้ค่า default = ต้องเช็คชื่อ (ไม่งั้นพนักงานใหม่ที่ยังกรอกไม่ครบ
จะหายไปจากพาเนลแบบเงียบๆ) · ติ๊กกลับเองได้ที่เมนู "พนักงาน"
"""
from django.db import migrations, models


def _mark_exec(apps, schema_editor):
    """แถวที่ ตำแหน่ง + เวลาเข้างาน + วันหยุด ว่างทั้งหมด = ผู้บริหาร ไม่ต้องเช็คชื่อ"""
    Employee = apps.get_model("checkout", "Employee")
    Employee.objects.filter(position="", work_start="", day_off="").update(track_checkin=False)


class Migration(migrations.Migration):

    dependencies = [
        ('checkout', '0014_checkin_checkin_uniq_checkin_user_day'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='track_checkin',
            field=models.BooleanField(db_index=True, default=True, verbose_name='ต้องเช็คชื่อเข้างาน'),
        ),
        # ย้อนกลับ = ไม่ทำอะไร (ค่าที่ตั้งไว้เป็นการตัดสินใจของผู้ใช้ ไม่ควรรีเซ็ตให้)
        migrations.RunPython(_mark_exec, migrations.RunPython.noop),
    ]
