import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# ──────────────────────────────────────────────────────────────────────
# กลยุทธ์ ENV (Vercel จำกัด ~15 ตัว):
#   • SECRET (ต้องตั้งบน Vercel เท่านั้น ห้าม inline ลงโค้ด) — 8 ตัว:
#       GOOGLE_PRIVATE_KEY, DJANGO_SECRET_KEY, OXLET_ADMIN_PASSWORD,
#       LINE_CHANNEL_ACCESS_TOKEN, CRON_SECRET, GEMINI_API_KEY, SUPABASE_SECRET_KEY,
#       OXLET_SELLER_PASSWORD (รหัสรวม login — env-only กันหลุด git)
#   • NON-SECRET (inline เป็น default ด้านล่าง — Vercel ไม่ต้องตั้ง):
#       url/model/flag/username/hostname ฯลฯ
#   • local dev: .env (gitignored) override ได้ทุกตัว
# ──────────────────────────────────────────────────────────────────────

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-change-me")
# DEBUG default = False (ปลอดภัยสำหรับ prod ที่ไม่ได้ตั้ง env). local dev ตั้ง DEBUG=True ใน .env
DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")

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
    # auth/admin/contenttypes/messages — ต้องมีเพราะแอป cars/ (tracking) ใช้ Django auth + admin
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sessions",
    "dashboard",
    "cars",  # ระบบติดตามรถ (tracking) — DB จริง, แยกจาก sales ที่อ่าน Sheets
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise ต้องอยู่ทันทีหลัง SecurityMiddleware — serve static บน production
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    # เพิ่มสำหรับ cars/ (tracking) — auth + messages + clickjacking
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # ผูก session sales → Django auth ให้ /track/ (เข้าแท็บ "สถานะรถ" ไม่ต้อง login ซ้ำ) · ต้องอยู่หลัง AuthenticationMiddleware
    "cars.middleware.TrackSessionBridgeMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# sales ฝัง seller.html เป็น iframe (same-origin) → SAMEORIGIN ไม่งั้น admin tab "เซลล์" พัง
X_FRAME_OPTIONS = "SAMEORIGIN"

# Session ใช้ signed-cookie backend — ไม่ต้องมี DB, ปลอดภัยเพราะ sign ด้วย SECRET_KEY
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
SESSION_COOKIE_NAME = "oxlet_sess"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30  # 30 วัน
# Production (ไม่ DEBUG) บังคับ HTTPS — cookie ส่งเฉพาะ HTTPS + redirect http→https
# (Vercel ส่ง X-Forwarded-Proto=https → Django รู้ว่า secure ผ่าน SECURE_PROXY_SSL_HEADER ด้านบน)
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG

# Admin credentials — override ใน .env ได้: OXLET_ADMIN_USER, OXLET_ADMIN_PASSWORD
# Default: admin / 1234 (ควรเปลี่ยนใน production)
OXLET_ADMIN_USER = os.getenv("OXLET_ADMIN_USER", "admin")
OXLET_ADMIN_PASSWORD = os.getenv("OXLET_ADMIN_PASSWORD", "1234")

# (เลิกใช้แล้ว — มิ.ย.69) รหัสรวม login ด้วย LINE user_id — ถอด path ออกจาก login_view กันคนนอก
# เหลือ login ผ่าน LINE Login (OAuth) อย่างเดียว · ตัวแปรนี้ไม่ถูกอ้างถึงในโค้ดแล้ว (เก็บไว้กัน import พัง/อ้างอิงเก่า)
OXLET_SELLER_PASSWORD = os.getenv("OXLET_SELLER_PASSWORD", "")

# LINE Messaging API — Channel Access Token (ตั้งใน .env เท่านั้น ไม่ commit)
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")

# LINE Login (OAuth) — ให้เซลล์เข้าด้วยบัญชี LINE (ยืนยันตัวตน · PDPA). ตั้งจาก LINE Login channel
LINE_LOGIN_CHANNEL_ID = os.getenv("LINE_LOGIN_CHANNEL_ID", "")
LINE_LOGIN_CHANNEL_SECRET = os.getenv("LINE_LOGIN_CHANNEL_SECRET", "")
# Callback URL ต้องตรงกับที่ลงทะเบียนใน LINE Login channel (ใช้ canonical URL)
LINE_LOGIN_CALLBACK = os.getenv("LINE_LOGIN_CALLBACK", "https://saleforce-oxletauto.vercel.app/auth/line/callback")

# ปลายทางทดสอบ Flex "เช็คไฟแนนซ์ก่อนเซ็น" — LINE user_id แอดมิน (ไม่ลับ: เป็นปลายทาง ไม่ใช่ credential)
FINANCE_TEST_LINE_ID = os.getenv("FINANCE_TEST_LINE_ID", "U6bf1d72cf1d7e237c3a5c9848dde9bf4")

# Gemini API key — สแกนเอกสาร OCR (server-side เท่านั้น) — SECRET ต้องตั้งบน Vercel
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# โมเดล OCR (ไม่ลับ — ชื่อโมเดล): pro = แม่นสุด (ลายมือ), flash = เร็ว/ถูกกว่า
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-pro-preview")

# Supabase — mirror Sheet + เก็บฟอร์ม (server-side)
# URL = ไม่ลับ (public REST endpoint, ป้องกันด้วย key+RLS) → inline ได้
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://qtavqquhjstrgrzauvsd.supabase.co").rstrip("/")
# SECRET key (ข้าม RLS) — env-only เท่านั้น (อย่า hardcode/commit) · ต้องตั้งบน Vercel
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY", "")
# (Phase 2 มิ.ย.69) default True — Supabase เก็บแค่ "ผลสรุป" (dashboard_cache) ไม่ mirror leads ดิบ
# active เมื่อ is_configured() = True (มี URL + SECRET_KEY) · ถ้า SECRET_KEY ว่าง → fallback อ่าน Google ตรง (ไม่พัง)
USE_SUPABASE = os.getenv("USE_SUPABASE", "True").lower() in ("true", "1", "yes")

# Cron endpoint secret — ใช้ป้องกัน /api/cron/send_line ไม่ให้ใครยิงก็ได้
# external cron service (n8n, Vercel cron) ต้องส่ง ?secret=xxx มาด้วย
CRON_SECRET = os.getenv("CRON_SECRET", "")

ROOT_URLCONF = "oxlet.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # templates/ ระดับ root = เทมเพลตของแอป cars/ (tracking) · dashboard ใช้ app dirs
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.static",
                # cars/ (tracking) ต้องการ auth + messages + nav
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "cars.context.nav",
            ],
        },
    },
]

WSGI_APPLICATION = "oxlet.wsgi.application"

# ──────────────────────────────────────────────────────────────────────
# ฐานข้อมูล — sales เดิมไม่ใช้ DB (อ่าน Google Sheets). เพิ่ม Postgres ให้แอป cars/ (tracking)
#   • DATABASE_URL = Supabase pooled (port 6543, transaction mode) → ใช้ตอน runtime
#   • DB_HOST/DB_NAME/... แยกตัว → ก็ได้
#   • ไม่ตั้งอะไรเลย → SQLite (local dev เท่านั้น)
# ⚠️ Vercel serverless ต้องต่อผ่าน pooler + CONN_MAX_AGE=0 + DISABLE_SERVER_SIDE_CURSORS=True
#    (pgbouncer transaction mode ใช้ server-side cursor ไม่ได้) · migrate ใช้ direct conn (5432)
# ──────────────────────────────────────────────────────────────────────
_DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if _DATABASE_URL:
    from urllib.parse import urlparse, unquote
    _u = urlparse(_DATABASE_URL)
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": (_u.path or "/postgres").lstrip("/") or "postgres",
        "USER": unquote(_u.username or ""),
        "PASSWORD": unquote(_u.password or ""),
        "HOST": _u.hostname or "",
        "PORT": str(_u.port or 5432),
        "CONN_MAX_AGE": 0,
        "DISABLE_SERVER_SIDE_CURSORS": True,
        "OPTIONS": {"sslmode": os.getenv("DB_SSLMODE", "require")},
    }}
elif os.getenv("DB_HOST"):
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "postgres"),
        "USER": os.getenv("DB_USER", "postgres"),
        "PASSWORD": os.getenv("DB_PASSWORD", ""),
        "HOST": os.getenv("DB_HOST"),
        "PORT": os.getenv("DB_PORT", "5432"),
        "CONN_MAX_AGE": 0,
        "DISABLE_SERVER_SIDE_CURSORS": True,
        "OPTIONS": {"sslmode": os.getenv("DB_SSLMODE", "require")},
    }}
else:
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }}

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
# service account email = ไม่ลับ (เป็น identity ไม่ใช่ credential) → inline ได้
GOOGLE_SERVICE_ACCOUNT_EMAIL = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_EMAIL",
    "n8n-sheets@sylvan-road-477705-q4.iam.gserviceaccount.com",
)
# GOOGLE_PRIVATE_KEY = SECRET (RSA private key) — ต้องตั้งบน Vercel เท่านั้น ห้าม inline
GOOGLE_PRIVATE_KEY = os.getenv("GOOGLE_PRIVATE_KEY", "").replace("\\n", "\n")
# Strip surrounding quotes
if GOOGLE_PRIVATE_KEY.startswith('"') and GOOGLE_PRIVATE_KEY.endswith('"'):
    GOOGLE_PRIVATE_KEY = GOOGLE_PRIVATE_KEY[1:-1]
if GOOGLE_PRIVATE_KEY.startswith("'") and GOOGLE_PRIVATE_KEY.endswith("'"):
    GOOGLE_PRIVATE_KEY = GOOGLE_PRIVATE_KEY[1:-1]

# ──────────────────────────────────────────────────────────────────────
# ระบบติดตามรถ (cars/) — auth / QR / LINE / media
# ──────────────────────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

# โดเมนที่ QR ชี้ไป (หน้า /track/scan/<code>/) — ต้องตรง prod ก่อนปริ้น QR
SITE_URL = os.getenv("SITE_URL", "https://saleforce-oxletauto.vercel.app").rstrip("/")

# LINE push ของ tracking (แยกจาก sales LINE_CHANNEL_ACCESS_TOKEN) — ไม่ตั้ง = ไม่ push เงียบ ๆ
LINE_CHANNEL_TOKEN = os.getenv("LINE_CHANNEL_TOKEN", "")
LINE_GROUP_ID = os.getenv("LINE_GROUP_ID", "")

# ยุบเหลือ login เดียว — tracking ใช้หน้า login หลักของ sales (/login/)
# login_required ของ cars/ → เด้งไป /login/?next=... · sales bridge session → Django auth ให้เอง
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/track/"
LOGOUT_REDIRECT_URL = "/login/"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# รูป/ไฟล์ของ cars/ → Supabase Storage (Vercel serverless เก็บไฟล์ถาวรไม่ได้)
# เปิดใช้เมื่อ: ตั้ง SUPABASE_STORAGE_BUCKET (env) + มี SUPABASE_URL + SUPABASE_SECRET_KEY
# ไม่ตั้ง → fallback FileSystemStorage (local dev เท่านั้น · บน prod รูปจะไม่ persist)
SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "")
if SUPABASE_URL and SUPABASE_SECRET_KEY and SUPABASE_STORAGE_BUCKET:
    STORAGES["default"]["BACKEND"] = "cars.storage.SupabaseStorage"
