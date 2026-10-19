from django.db import migrations, models


class Migration(migrations.Migration):
    """★ 19 ต.ค.69 เก็บลีดอัตโนมัติ: เลขที่ระบบจองไว้ให้ลีดภายนอก (ใบร่างในกลุ่ม ADMIN เก็บ Lead / ฟอร์มในเว็บ)"""

    dependencies = [("checkout", "0042_employee_department")]

    operations = [
        migrations.AddField(
            model_name="extlead",
            name="auto",
            field=models.JSONField(blank=True, default=dict, verbose_name="ข้อมูลระบบ (เลขที่จองไว้)"),
        ),
    ]
