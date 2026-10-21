# ★ 21 ต.ค.69 คำขอลา (แอปมือถือ) — dashboard/services/leave.py

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('checkout', '0013_employee_lineprofile_employee'),   # ★ ตารางพนักงานเกิดที่ 0013 — ไม่ผูกกับ migration ที่ยังไม่ได้ push ของงานอื่น
        ('dashboard', '0019_dev_request'),
    ]

    operations = [
        migrations.CreateModel(
            name='LeaveRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nickname', models.CharField(db_index=True, max_length=80, verbose_name='ชื่อเล่น')),
                ('kind', models.CharField(choices=[('sick', 'ลาป่วย'), ('personal', 'ลากิจ'), ('vacation', 'ลาพักร้อน'), ('other', 'ลาอื่นๆ')], max_length=12, verbose_name='ประเภทการลา')),
                ('start_date', models.DateField(db_index=True, verbose_name='ลาตั้งแต่')),
                ('end_date', models.DateField(db_index=True, verbose_name='ลาถึง')),
                ('half', models.CharField(blank=True, choices=[('', 'เต็มวัน'), ('am', 'ครึ่งวันเช้า'), ('pm', 'ครึ่งวันบ่าย')], max_length=2, verbose_name='ครึ่งวัน')),
                ('days', models.DecimalField(decimal_places=1, default=0, max_digits=5, verbose_name='จำนวนวันลา')),
                ('reason', models.TextField(blank=True, verbose_name='เหตุผล')),
                ('status', models.CharField(choices=[('pending', 'รออนุมัติ'), ('approved', 'อนุมัติ'), ('rejected', 'ไม่อนุมัติ'), ('cancelled', 'ยกเลิก')], db_index=True, default='pending', max_length=10, verbose_name='สถานะ')),
                ('decided_by', models.CharField(blank=True, max_length=80, verbose_name='อนุมัติ/ไม่อนุมัติโดย')),
                ('decided_at', models.DateTimeField(blank=True, null=True, verbose_name='ตัดสินเมื่อ')),
                ('decide_note', models.CharField(blank=True, max_length=300, verbose_name='หมายเหตุจากผู้อนุมัติ')),
                ('created_by', models.CharField(blank=True, max_length=80, verbose_name='ยื่นโดย')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='ยื่นเมื่อ')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='แก้ล่าสุด')),
                ('employee', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='leave_requests', to='checkout.employee', verbose_name='พนักงาน')),
            ],
            options={
                'verbose_name': 'คำขอลา',
                'verbose_name_plural': 'คำขอลา',
                'db_table': 'dash_leave_request',
                'ordering': ['-start_date', '-id'],
            },
        ),
    ]
