"""Helper — แสดงค่า env vars จาก .env ให้ copy ไปกรอก Vercel dashboard.

วิธีรัน:
    python show_env.py

หรือถ้ามีหลาย Python:
    py -3.14 show_env.py

หมายเหตุ: ไฟล์นี้ไม่ต้องอัปขึ้น git (อยู่ใน .gitignore ได้)
"""
from dotenv import dotenv_values

v = dotenv_values(".env")
keys = [
    "GOOGLE_SERVICE_ACCOUNT_EMAIL",
    "GOOGLE_PRIVATE_KEY",
    "DJANGO_SECRET_KEY",
    "DEBUG",
    "OXLET_ADMIN_USER",
    "OXLET_ADMIN_PASSWORD",
    "LINE_CHANNEL_ACCESS_TOKEN",
]

print("=" * 60)
print("📋 Env vars สำหรับ Vercel dashboard")
print("=" * 60)
for k in keys:
    val = v.get(k, "(MISSING)")
    print()
    print(f"### {k}")
    print("-" * 50)
    print(val)
print()
print("=" * 60)
print("ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS ใส่ตามนี้ (เปลี่ยน xxx เป็นชื่อ project):")
print("=" * 60)
print("ALLOWED_HOSTS=xxx.vercel.app")
print("CSRF_TRUSTED_ORIGINS=https://xxx.vercel.app")
