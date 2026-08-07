# เพิ่มสเตป "ซ่อมเสร็จรอตรวจ" (repair_done) ต่อจาก "เช็คซ่อม" + เปลี่ยนป้ายความด่วน photo_wait เป็น "ยังไม่ได้ถ่ายรูป" (ส.ค.69)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cars', '0010_restage_v2_priority'),
    ]

    operations = [
        migrations.AlterField(
            model_name='car',
            name='priority',
            field=models.CharField(choices=[('urgent_high', 'ด่วนมาก'), ('urgent', 'ด่วน'), ('normal', 'ปกติ'), ('low', 'ไม่เร่ง'), ('photo_wait', 'ยังไม่ได้ถ่ายรูป')], default='normal', max_length=16, verbose_name='ความด่วน'),
        ),
        migrations.AlterField(
            model_name='car',
            name='stage',
            field=models.CharField(choices=[('intake', 'รับเข้า'), ('photo_wait', 'รถรอถ่ายรูป'), ('repair', 'เช็คซ่อม'), ('repair_done', 'ซ่อมเสร็จรอตรวจ'), ('parts', 'สั่งของ/รออะไหล่'), ('upholstery', 'งานเบาะ'), ('paint_in', 'อู่สีใน'), ('paint_out', 'อู่สีนอก'), ('film', 'ติดฟิล์ม'), ('wash', 'ชงล้าง'), ('qc_show', 'รอตรวจรถขึ้นโชว์'), ('show', 'รถพร้อมขาย/หน้าร้าน'), ('reserve', 'จอง'), ('finance', 'จัดไฟแนนซ์'), ('closing', 'รอปิดการขาย'), ('qc_release', 'ตรวจรถรอปล่อย'), ('release', 'ปล่อยรถ')], default='intake', max_length=20, verbose_name='สเตป'),
        ),
        migrations.AlterField(
            model_name='scanlog',
            name='stage',
            field=models.CharField(choices=[('intake', 'รับเข้า'), ('photo_wait', 'รถรอถ่ายรูป'), ('repair', 'เช็คซ่อม'), ('repair_done', 'ซ่อมเสร็จรอตรวจ'), ('parts', 'สั่งของ/รออะไหล่'), ('upholstery', 'งานเบาะ'), ('paint_in', 'อู่สีใน'), ('paint_out', 'อู่สีนอก'), ('film', 'ติดฟิล์ม'), ('wash', 'ชงล้าง'), ('qc_show', 'รอตรวจรถขึ้นโชว์'), ('show', 'รถพร้อมขาย/หน้าร้าน'), ('reserve', 'จอง'), ('finance', 'จัดไฟแนนซ์'), ('closing', 'รอปิดการขาย'), ('qc_release', 'ตรวจรถรอปล่อย'), ('release', 'ปล่อยรถ')], max_length=20, verbose_name='สเตป'),
        ),
    ]
