"""
ทดสอบ Google Drive + สร้างโฟลเดอร์หลัก (ที่เก็บโฟลเดอร์รถทุกคัน)

ใช้หลังตั้ง GDRIVE_CLIENT_ID/SECRET/REFRESH_TOKEN ใน .env แล้ว:
  python manage.py gdrive_setup
→ เช็คว่า token ใช้ได้ + สร้างโฟลเดอร์ "Oxlet Car Media" → พิมพ์ GDRIVE_ROOT_FOLDER_ID ให้เอาไปใส่ .env
(ถ้าไม่ตั้ง GDRIVE_ROOT_FOLDER_ID ไฟล์จะไปอยู่ root ของไดรฟ์ — ใช้งานได้แต่รก)
"""
from django.core.management.base import BaseCommand, CommandError

from cars import gdrive


class Command(BaseCommand):
    help = "ทดสอบ Google Drive token + สร้างโฟลเดอร์หลักสำหรับเก็บโฟลเดอร์รถ"

    def add_arguments(self, parser):
        parser.add_argument("--name", default="Oxlet Car Media", help="ชื่อโฟลเดอร์หลัก")

    def handle(self, *args, **opts):
        if not gdrive.is_configured():
            raise CommandError("ยังไม่ได้ตั้ง GDRIVE_CLIENT_ID / GDRIVE_CLIENT_SECRET / GDRIVE_REFRESH_TOKEN ใน .env")
        try:
            gdrive._access_token()
        except Exception as e:
            raise CommandError(f"ใช้ token ไม่ได้: {e}")
        self.stdout.write(self.style.SUCCESS("✓ token ใช้งานได้"))

        try:
            fid = gdrive.ensure_folder(opts["name"], parent_id="")
        except Exception as e:
            raise CommandError(f"สร้างโฟลเดอร์ไม่สำเร็จ: {e}")

        self.stdout.write(self.style.SUCCESS(f"✓ โฟลเดอร์ '{opts['name']}' พร้อมแล้ว\n"))
        self.stdout.write("ใส่ค่านี้ใน .env (ออปชั่น แต่แนะนำ):")
        self.stdout.write(f"GDRIVE_ROOT_FOLDER_ID={fid}")
