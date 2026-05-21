import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-change-me")
DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "django.contrib.sessions",
    "dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
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

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Google Sheets config
GOOGLE_SERVICE_ACCOUNT_EMAIL = os.getenv("GOOGLE_SERVICE_ACCOUNT_EMAIL", "")
GOOGLE_PRIVATE_KEY = os.getenv("GOOGLE_PRIVATE_KEY", "").replace("\\n", "\n")
# Strip surrounding quotes
if GOOGLE_PRIVATE_KEY.startswith('"') and GOOGLE_PRIVATE_KEY.endswith('"'):
    GOOGLE_PRIVATE_KEY = GOOGLE_PRIVATE_KEY[1:-1]
if GOOGLE_PRIVATE_KEY.startswith("'") and GOOGLE_PRIVATE_KEY.endswith("'"):
    GOOGLE_PRIVATE_KEY = GOOGLE_PRIVATE_KEY[1:-1]
