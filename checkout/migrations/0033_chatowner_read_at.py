# 9 ต.ค.69 — Connect: สถานะ "ยังไม่อ่าน" ในรายชื่อลูกค้า

from django.db import migrations, models
from django.db.models import F


def mark_existing(apps, schema_editor):
    """แชทเดิมทั้งหมด = อ่านแล้ว · ยกเว้นลูกค้าที่ยังรอคำตอบอยู่ (นับเป็นยังไม่อ่าน)
    ไม่งั้นวันแรกรายชื่อทั้ง 2,000 แถวเป็นตัวหนาหมด แยกไม่ออกว่าใครใหม่"""
    ChatOwner = apps.get_model("checkout", "ChatOwner")
    ChatOwner.objects.filter(awaiting_since__isnull=True).update(read_at=F("last_in_at"))


class Migration(migrations.Migration):

    dependencies = [
        ('checkout', '0032_chatlead_customer_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='chatowner',
            name='read_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='อ่านถึงข้อความลูกค้าเมื่อ'),
        ),
        migrations.RunPython(mark_existing, migrations.RunPython.noop),
    ]
