from django.db import migrations, models


class Migration(migrations.Migration):
    """★ 23 ต.ค.69 ตอบคอมเมนต์ Facebook จากหน้า "คอมเมนต์" ใน Connect — จดว่าใครตอบ + คำตอบที่ส่งจากระบบ"""

    dependencies = [
        ("checkout", "0048_broadcast_links"),
    ]

    operations = [
        migrations.AddField(
            model_name="socialcomment",
            name="replied_by",
            field=models.CharField(blank=True, max_length=80, verbose_name="ตอบในระบบล่าสุดโดย"),
        ),
        migrations.AddField(
            model_name="socialcomment",
            name="reply_log",
            field=models.JSONField(blank=True, default=list, verbose_name="คำตอบที่ส่งจากระบบ"),
        ),
    ]
