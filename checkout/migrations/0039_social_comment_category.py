from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('checkout', '0038_social_comment'),
    ]

    operations = [
        migrations.AddField(
            model_name='socialcomment',
            name='category',
            field=models.CharField(blank=True, choices=[('greet', 'ทักทาย/พูดคุยเล่น'), ('interest', 'สนใจ/ถามราคา'), ('attack', 'โจมตีแบรนด์'), ('complaint', 'คอมเพลน')], db_index=True, max_length=12, verbose_name='ประเภทลูกค้า'),
        ),
        migrations.AddField(
            model_name='socialcomment',
            name='category_why',
            field=models.CharField(blank=True, max_length=60, verbose_name='จัดจากคำว่า'),
        ),
        migrations.AddField(
            model_name='socialcomment',
            name='category_by',
            field=models.CharField(blank=True, max_length=80, verbose_name='คนจัดประเภท (ว่าง = ระบบจัดเอง)'),
        ),
        migrations.AddField(
            model_name='socialcomment',
            name='category_v',
            field=models.PositiveSmallIntegerField(default=0, verbose_name='รุ่นตัวจัดประเภท'),
        ),
    ]
