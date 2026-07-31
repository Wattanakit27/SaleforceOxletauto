# -*- coding: utf-8 -*-
"""สร้างบัญชีทดสอบ 1 บัญชี/บทบาท (11 บทบาท) — ไว้ทดสอบบอร์ดสถานะรถเฉพาะสเตปของแต่ละคน.

รัน: python manage.py seed_role_accounts
  --password xxx  ตั้งรหัสเอง (default = 1234)
idempotent — รันซ้ำได้ (get_or_create + ตั้งรหัส/บทบาทใหม่ทุกครั้ง)
บัญชีเหล่านี้ login ที่ /login/?bg=1 (ช่อง username/password · login_view ลอง authenticate())
⚠️ รหัส default เป็นรหัสทดสอบ — บน prod ควรเปลี่ยนรหัสที่ /track/users/
"""
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from cars import roles

# (role_key, username, ชื่อที่แสดง)
ACCOUNTS = [
    (roles.EXEC,       "exec",      "ผู้บริหาร (ทดสอบ)"),
    (roles.PURCHASING, "purchase",  "จัดซื้อ (ทดสอบ)"),
    (roles.ADMIN,      "admintrk",  "แอดมิน (ทดสอบ)"),
    (roles.SALES,      "sales",     "เซลล์ (ทดสอบ)"),
    (roles.TECH,       "tech",      "ช่าง (ทดสอบ)"),
    (roles.VENDOR,     "vendor",    "อู่นอก (ทดสอบ)"),
    (roles.REGIST,     "regist",    "ฝ่ายทะเบียน (ทดสอบ)"),
    (roles.CARWASH,    "wash",      "ฝ่ายล้างรถ (ทดสอบ)"),
    (roles.PRODUCTION, "prod",      "โปรดักชัน (ทดสอบ)"),
    (roles.QC,         "qc",        "QC (ทดสอบ)"),
    (roles.PAINTIN,    "paintin",   "อู่สีใน (ทดสอบ)"),
]


class Command(BaseCommand):
    help = "สร้างบัญชีทดสอบ 1 บัญชีต่อบทบาท (11 บทบาท)"

    def add_arguments(self, parser):
        parser.add_argument("--password", default="1234", help="รหัสผ่าน (ใช้ร่วมทุกบัญชี · default 1234)")

    def handle(self, *args, **opts):
        pw = opts["password"]
        self.stdout.write("บัญชีทดสอบ (login ที่ /login/?bg=1):")
        self.stdout.write("-" * 52)
        for role_key, username, display in ACCOUNTS:
            u, created = User.objects.get_or_create(username=username)
            first, _, last = display.partition(" ")
            u.first_name = first[:30]
            u.last_name = last[:150]
            u.is_active = True
            u.is_staff = False
            u.set_password(pw)
            u.save()
            roles.set_user_role(u, role_key)   # ล้าง group เดิม + ใส่ group บทบาทใหม่
            tag = "สร้างใหม่" if created else "อัปเดต"
            self.stdout.write(f"  {username:<10} | {roles.ROLE_LABEL[role_key]:<12} | {tag}")
        self.stdout.write("-" * 52)
        self.stdout.write(f"รหัสผ่านทุกบัญชี: {pw}")
        self.stdout.write("(รหัสทดสอบ - บน prod เปลี่ยนที่ /track/users/)")
