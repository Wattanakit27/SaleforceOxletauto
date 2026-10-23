# -*- coding: utf-8 -*-
"""เทสต์ชื่อเว็บใหม่ portal.oxletauto.co.th (★ 23 ต.ค.69)

    python scripts/test_portal_domain.py

  - ค่าตั้งต้นรับทั้งชื่อใหม่และชื่อเดิม (ALLOWED_HOSTS / CSRF_TRUSTED_ORIGINS / LINE Login callback)
  - LINE Login: เข้าทางชื่อไหน = callback กลับชื่อนั้น (ทั้งตอนพาไป LINE และตอนแลก code) · ไม่ตรง = ตัวแรก
  - .env ตั้ง LINE_LOGIN_CALLBACK ตัวเดียว (แบบเดิม) = ใช้ตัวนั้นเสมอ ไม่พัง

ไม่ยิง LINE จริง — ปลอมที่ `requests.post` (แลก code) เท่านั้น
"""
import io
import json
import os
import sys
from urllib.parse import parse_qs, urlparse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DJANGO_SETTINGS_MODULE"] = "oxlet.settings"
os.environ["DB_HOST"] = ""
os.environ["DEBUG"] = "False"
for k in ("ALLOWED_HOSTS", "CSRF_TRUSTED_ORIGINS", "LINE_LOGIN_CALLBACK"):
    os.environ[k] = ""

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.test.runner import DiscoverRunner  # noqa: E402
from django.test.utils import setup_test_environment  # noqa: E402

setup_test_environment()
_runner = DiscoverRunner(verbosity=0, interactive=False)
_old = _runner.setup_databases()

import requests  # noqa: E402
from django.test import Client, override_settings  # noqa: E402

OK, BAD = [], []


def ck(name, cond, got=""):
    (OK if cond else BAD).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else "   ได้: %r" % (got,)))


SENT = []


class _R:
    status_code = 200
    headers = {}

    def json(self):
        return {"error": "invalid_grant", "error_description": "test"}


def _post(url, data=None, **k):
    SENT.append((url, dict(data or {})))
    return _R()


requests.post = _post
NEW, OLD = "portal.oxletauto.co.th", "srv1793506.hstgr.cloud"

try:
    print("[1] ค่าตั้งต้น")
    ck("ALLOWED_HOSTS มีชื่อใหม่ + ชื่อเดิม", NEW in settings.ALLOWED_HOSTS and OLD in settings.ALLOWED_HOSTS, settings.ALLOWED_HOSTS)
    ck("CSRF_TRUSTED_ORIGINS มีทั้ง 2 ชื่อ", "https://" + NEW in settings.CSRF_TRUSTED_ORIGINS
       and "https://" + OLD in settings.CSRF_TRUSTED_ORIGINS, settings.CSRF_TRUSTED_ORIGINS)
    ck("LINE Login callback 2 ตัว (ตัวแรก = ชื่อเดิม เพื่อไม่ให้ของเดิมเปลี่ยน)",
       settings.LINE_LOGIN_CALLBACKS == ["https://%s/auth/line/callback" % OLD, "https://%s/auth/line/callback" % NEW]
       and settings.LINE_LOGIN_CALLBACK.startswith("https://" + OLD), settings.LINE_LOGIN_CALLBACKS)

    print("[2] LINE Login เลือก callback ตามชื่อเว็บที่เปิด")
    with override_settings(LINE_LOGIN_CHANNEL_ID="123", LINE_LOGIN_CHANNEL_SECRET="s"):
        for host in (NEW, OLD):
            cl = Client()
            r = cl.get("/auth/line/start", HTTP_HOST=host, secure=True)
            q = parse_qs(urlparse(r.get("Location", "")).query)
            ck("เข้าทาง %s → redirect_uri = %s" % (host, host), r.status_code == 302
               and q.get("redirect_uri") == ["https://%s/auth/line/callback" % host], (r.status_code, q.get("redirect_uri")))
            st = (q.get("state") or [""])[0]
            SENT.clear()
            cl.get("/auth/line/callback", {"code": "c1", "state": st}, HTTP_HOST=host, secure=True)
            ck("callback ที่ %s แลก code ด้วย redirect_uri เดียวกัน" % host,
               SENT and SENT[0][1].get("redirect_uri") == "https://%s/auth/line/callback" % host, SENT[:1])
        cl = Client()
        r = cl.get("/auth/line/start", HTTP_HOST="localhost", secure=True)
        q = parse_qs(urlparse(r.get("Location", "")).query)
        ck("ชื่อที่ไม่มี callback ของตัวเอง = ใช้ตัวแรก", q.get("redirect_uri") == ["https://%s/auth/line/callback" % OLD], q.get("redirect_uri"))

    print("[3] .env ตั้ง callback ตัวเดียวแบบเดิม")
    with override_settings(LINE_LOGIN_CHANNEL_ID="123", LINE_LOGIN_CALLBACKS=["https://%s/auth/line/callback" % OLD],
                           LINE_LOGIN_CALLBACK="https://%s/auth/line/callback" % OLD):
        r = Client().get("/auth/line/start", HTTP_HOST=NEW, secure=True)
        q = parse_qs(urlparse(r.get("Location", "")).query)
        ck("เข้าทางชื่อใหม่แต่ลงทะเบียนไว้ตัวเดียว = กลับชื่อเดิม (ไม่พัง)", q.get("redirect_uri") == ["https://%s/auth/line/callback" % OLD], q.get("redirect_uri"))

    print("[4] หน้าเว็บตอบชื่อใหม่ได้ (ALLOWED_HOSTS)")
    r = Client().get("/login/", HTTP_HOST=NEW, secure=True)
    ck("GET /login/ ทางชื่อใหม่ = 200", r.status_code == 200, r.status_code)
    r = Client().get("/login/", HTTP_HOST="evil.example.com", secure=True)
    ck("ชื่อแปลกปลอม = 400", r.status_code == 400, r.status_code)
finally:
    _runner.teardown_databases(_old)

print("\nผ่าน %d / %d" % (len(OK), len(OK) + len(BAD)))
if BAD:
    print("ไม่ผ่าน:\n  - " + "\n  - ".join(BAD))
    sys.exit(1)
