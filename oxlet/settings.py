import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-change-me")
DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")

# ALLOWED_HOSTS — รับจาก env var ถ้ามี (comma-separated), fallback "*" สำหรับ dev
_hosts_env = os.getenv("ALLOWED_HOSTS", "").strip()
if _hosts_env:
    ALLOWED_HOSTS = [h.strip() for h in _hosts_env.split(",") if h.strip()]
else:
    ALLOWED_HOSTS = ["*"] if DEBUG else [".vercel.app", "localhost", "127.0.0.1"]

# Vercel/proxy ส่ง HTTPS มาเป็น header X-Forwarded-Proto
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.getenv(
    "CSRF_TRUSTED_ORIGINS", "https://*.vercel.app"
).split(",") if o.strip()]

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "django.contrib.sessions",
    "dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise ต้องอยู่ทันทีหลัง SecurityMiddleware — serve static บน production
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
]

# Session ใช้ signed-cookie backend — ไม่ต้องมี DB, ปลอดภัยเพราะ sign ด้วย SECRET_KEY
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
SESSION_COOKIE_NAME = "oxlet_sess"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30  # 30 วัน

# Admin credentials — override ใน .env ได้: OXLET_ADMIN_USER, OXLET_ADMIN_PASSWORD
# Default: admin / 1234 (ควรเปลี่ยนใน production)
OXLET_ADMIN_USER = os.getenv("OXLET_ADMIN_USER", "admin")
OXLET_ADMIN_PASSWORD = os.getenv("OXLET_ADMIN_PASSWORD", "1234")

# LINE Messaging API — Channel Access Token (ตั้งใน .env เท่านั้น ไม่ commit)
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")

# ปลายทางทดสอบ Flex "เช็คไฟแนนซ์ก่อนเซ็น" — ใส่ LINE user_id แอดมิน
# ช่วงทดสอบส่งเข้า id นี้แทนกลุ่ม. ถ้าว่าง → ปฏิเสธการส่ง (ไม่ fallback)
FINANCE_TEST_LINE_ID = os.getenv("FINANCE_TEST_LINE_ID", "")

# Gemini API key — สแกนเอกสาร OCR (server-side เท่านั้น)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# โมเดล OCR — pro = แม่นสุด (ลายมือ), flash = เร็ว/ถูกกว่า
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")

# Supabase — mirror Sheet + เก็บฟอร์ม (server-side, ใช้ secret key)
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY", "")
SUPABASE_PUBLISHABLE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
# เปิด = dashboard อ่านจาก Supabase (sheet_cache), ปิด = อ่าน Google Sheets ตรง (เดิม)
USE_SUPABASE = os.getenv("USE_SUPABASE", "False").lower() in ("true", "1", "yes")

# Cron endpoint secret — ใช้ป้องกัน /api/cron/send_line ไม่ให้ใครยิงก็ได้
# external cron service (cron-job.org, Vercel cron) ต้องส่ง ?secret=xxx มาด้วย
CRON_SECRET = os.getenv("CRON_SECRET", "")

ROOT_URLCONF = "oxlet.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.static",
            ],
        },
    },
]

WSGI_APPLICATION = "oxlet.wsgi.application"

DATABASES = {}

LANGUAGE_CODE = "th"
TIME_ZONE = "Asia/Bangkok"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = []
STATIC_ROOT = BASE_DIR / "staticfiles"
# WhiteNoise: หา static จาก app/static โดยตรง — ไม่ต้องรัน collectstatic บน Vercel
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = DEBUG
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Google Sheets config
GOOGLE_SERVICE_ACCOUNT_EMAIL = os.getenv("GOOGLE_SERVICE_ACCOUNT_EMAIL", "")
GOOGLE_PRIVATE_KEY = os.getenv("GOOGLE_PRIVATE_KEY", "").replace("\\n", "\n")
# Strip surrounding quotes
if GOOGLE_PRIVATE_KEY.startswith('"') and GOOGLE_PRIVATE_KEY.endswith('"'):
    GOOGLE_PRIVATE_KEY = GOOGLE_PRIVATE_KEY[1:-1]
if GOOGLE_PRIVATE_KEY.startswith("'") and GOOGLE_PRIVATE_KEY.endswith("'"):
    GOOGLE_PRIVATE_KEY = GOOGLE_PRIVATE_KEY[1:-1]
