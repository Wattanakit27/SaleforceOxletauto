# ปุ่ม Active (13 ต.ค.69) — รถขึ้นเว็บโชว์รูม Oxlet เมื่อกด Active + ถึงสเตปพร้อมขาย/จอง
#
# ข้อมูลเดิม (เจ้าของเลือก "รถที่ขึ้นเว็บอยู่แล้วให้โชว์ต่อ นับเป็น Active"):
#   ก่อนมีปุ่มนี้ รถขึ้นเว็บเองทันทีที่ถึง "พร้อมขาย/จอง" แล้วค้างอยู่บนเว็บจนกว่าจะขายแล้ว
#   → นับเป็น Active ให้ทุกคันที่ "อยู่พร้อมขาย/จอง ตอนนี้" หรือ "เคยถึงพร้อมขายแล้ว (frontline_at)"
#     และยังไม่ขาย · รถที่ยังทำสภาพอยู่ = ไม่ Active (รอกดเอง)
#   web_listed ยังเป็น False — ไม่รู้ว่าเว็บมีประกาศจริงไหม (ขึ้นกับว่าเคยตั้ง webhook ไว้)
#   ให้รัน `manage.py showroom_push --apply` หลัง deploy เพื่อถามเว็บแล้วบันทึกสถานะจริง

from django.db import migrations, models
from django.db.models import Q
from django.utils import timezone

BY = "ระบบ (ขึ้นเว็บอยู่แล้วก่อนมีปุ่ม Active)"


def mark_existing(apps, schema_editor):
    Car = apps.get_model("cars", "Car")
    (Car.objects
     .filter(Q(stage__in=["show", "reserve"]) | Q(frontline_at__isnull=False),
             status="active", deleted_at__isnull=True)
     .exclude(stage="sold")
     .update(web_active=True, web_active_at=timezone.now(), web_active_by=BY))


def unmark(apps, schema_editor):
    Car = apps.get_model("cars", "Car")
    Car.objects.filter(web_active_by=BY).update(web_active=False, web_active_at=None, web_active_by="")


class Migration(migrations.Migration):

    dependencies = [
        ('cars', '0018_car_price'),
    ]

    operations = [
        migrations.AddField(
            model_name='car',
            name='web_active',
            field=models.BooleanField(default=False, verbose_name='Active (ขึ้นเว็บ Oxlet)'),
        ),
        migrations.AddField(
            model_name='car',
            name='web_active_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='กด Active เมื่อ'),
        ),
        migrations.AddField(
            model_name='car',
            name='web_active_by',
            field=models.CharField(blank=True, max_length=80, verbose_name='กด Active โดย'),
        ),
        migrations.AddField(
            model_name='car',
            name='web_listed',
            field=models.BooleanField(default=False, verbose_name='แสดงบนเว็บอยู่ (เว็บยืนยัน)'),
        ),
        migrations.AddField(
            model_name='car',
            name='web_synced_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='ส่งไปเว็บล่าสุด'),
        ),
        migrations.AddField(
            model_name='car',
            name='web_sync_error',
            field=models.CharField(blank=True, max_length=200, verbose_name='ส่งไปเว็บไม่สำเร็จ'),
        ),
        migrations.RunPython(mark_existing, unmark),
    ]
