# ★ 6 ต.ค.69 — ปุ่ม "จ่ายเบอร์" ส่งใบจ่ายลีดเข้ากลุ่มจ่ายเบอร์จริง + แท็กเซลล์ (checkout/slippost.py)
#   เก็บผลการส่ง (สำเร็จไหม · กลุ่มไหน · แท็กได้ไหม · ล้มเพราะอะไร) ไว้ให้หน้าเว็บโชว์ปุ่ม "ส่งอีกครั้ง"

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('checkout', '0030_connect_facebook'),
    ]

    operations = [
        migrations.AddField(
            model_name='chatlead',
            name='post_info',
            field=models.JSONField(blank=True, default=dict, verbose_name='ส่งใบจ่ายลีดเข้ากลุ่ม'),
        ),
        migrations.AddField(
            model_name='extlead',
            name='post_info',
            field=models.JSONField(blank=True, default=dict, verbose_name='ส่งใบจ่ายลีดเข้ากลุ่ม'),
        ),
    ]
