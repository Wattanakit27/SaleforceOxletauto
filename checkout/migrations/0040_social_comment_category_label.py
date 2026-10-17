from django.db import migrations, models


class Migration(migrations.Migration):
    """เปลี่ยนชื่อที่โชว์ "สนใจ/ถามราคา" → "สนใจ/สอบถาม" (17 ต.ค.69 · ค่าในฐานข้อมูลยังเป็น interest เหมือนเดิม)"""

    dependencies = [
        ('checkout', '0039_social_comment_category'),
    ]

    operations = [
        migrations.AlterField(
            model_name='socialcomment',
            name='category',
            field=models.CharField(blank=True, choices=[('greet', 'ทักทาย/พูดคุยเล่น'), ('interest', 'สนใจ/สอบถาม'), ('attack', 'โจมตีแบรนด์'), ('complaint', 'คอมเพลน')], db_index=True, max_length=12, verbose_name='ประเภทลูกค้า'),
        ),
    ]
