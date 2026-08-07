# แยก "ธงงานค้าง" ออกจาก "ความด่วน" (ส.ค.69)
#   เดิม "ยังไม่ได้ถ่ายรูป" เป็นตัวเลือกหนึ่งใน priority → ติดธงแล้วบอกด่วน/ไม่ด่วนไม่ได้
#   ตอนนี้แยกเป็น need_photo/need_content (ติ๊กพร้อมกันได้ + ใช้ร่วมกับความด่วนได้)
#   ★ ย้ายข้อมูลเดิม: รถที่ priority="photo_wait" → need_photo=True + priority="normal"
from django.db import migrations, models


def move_photo_wait_to_flag(apps, schema_editor):
    Car = apps.get_model("cars", "Car")
    Car.objects.filter(priority="photo_wait").update(need_photo=True, priority="normal")


def back_to_photo_wait(apps, schema_editor):
    Car = apps.get_model("cars", "Car")
    Car.objects.filter(need_photo=True).update(priority="photo_wait")


class Migration(migrations.Migration):

    dependencies = [
        ('cars', '0012_stage_sales_check'),
    ]

    operations = [
        migrations.AddField(
            model_name='car',
            name='need_content',
            field=models.BooleanField(default=False, verbose_name='ยังไม่ได้ถ่ายคอนเทนต์'),
        ),
        migrations.AddField(
            model_name='car',
            name='need_photo',
            field=models.BooleanField(default=False, verbose_name='ยังไม่ได้ถ่ายรูป'),
        ),
        # ★ ย้ายข้อมูลก่อนเปลี่ยน choices — ไม่งั้นรถที่ priority="photo_wait" จะค้างค่าที่ไม่มีในลิสต์
        migrations.RunPython(move_photo_wait_to_flag, back_to_photo_wait),
        migrations.AlterField(
            model_name='car',
            name='priority',
            field=models.CharField(choices=[('urgent_high', 'ด่วนมาก'), ('urgent', 'ด่วน'), ('normal', 'ปกติ'), ('low', 'ไม่เร่ง')], default='normal', max_length=16, verbose_name='ความด่วน'),
        ),
    ]
