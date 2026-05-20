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
    "dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

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
