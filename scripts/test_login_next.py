# -*- coding: utf-8 -*-
"""เทสต์ "ไม่ให้ ?next= โผล่ในแถบที่อยู่" (★ 23 ต.ค.69 · dashboard/middleware.py LoginNextMiddleware)

    python scripts/test_login_next.py

  - ทุกทางที่เด้งไปหน้า login (view · @login_required ของระบบรถ · /track/login/) → /login/ เปล่าๆ
  - หน้า login ยังรู้ว่าต้องพากลับหน้าไหน (ช่องซ่อน next + ลิงก์ LINE)
  - เปิด /login/?next=… ตรงๆ (ลิงก์เก่า/JS) → เก็บแล้วพาไป /login/ · พารามิเตอร์อื่น (bg) คงไว้
  - next ที่พาไปเว็บอื่น = ทิ้ง · ทางของแอปมือถือ (/m/…) ไม่แตะ
  - login แล้วพากลับถูกหน้า · ใช้แล้วล้างทิ้ง (เข้า /login/ ทีหลังไม่ถูกพาไปหน้าเก่า) · หมดอายุ 30 นาที
"""
import io
import os
import re
import sys
import time
from urllib.parse import parse_qs, unquote, urlparse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DJANGO_SETTINGS_MODULE"] = "oxlet.settings"
os.environ["DB_HOST"] = ""
os.environ["DEBUG"] = "False"

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.test.runner import DiscoverRunner  # noqa: E402
from django.test.utils import setup_test_environment  # noqa: E402

setup_test_environment()
_runner = DiscoverRunner(verbosity=0, interactive=False)
_old = _runner.setup_databases()

from django.test import Client, override_settings  # noqa: E402

from dashboard import middleware as MW  # noqa: E402

if "testserver" not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]

OK, BAD = [], []


def ck(name, cond, got=""):
    (OK if cond else BAD).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else "   ได้: %r" % (got,)))


def hidden_next(r) -> str:
    m = re.search(r'name="next" value="([^"]*)"', r.content.decode("utf-8"))
    return m.group(1) if m else None


def line_next(r) -> str:
    m = re.search(r'/auth/line/start\?next=([^"&]*)', r.content.decode("utf-8"))
    return unquote(m.group(1)) if m else None


def get(c, url, **kw):
    return c.get(url, secure=True, **kw)


try:
    print("[1] เด้งไปหน้า login = ไม่มี ?next= แต่ยังจำหน้าที่ต้องกลับ")
    c = Client()
    r = get(c, "/dashboard/")
    ck("ไม่ login เปิด /dashboard/ → /login/ เปล่าๆ", r.status_code == 302 and r["Location"] == "/login/", r.get("Location"))
    r = get(c, "/login/")
    ck("หน้า login: ช่องซ่อน next = /dashboard/", r.status_code == 200 and hidden_next(r) == "/dashboard/", hidden_next(r))
    ck("หน้า login: ลิงก์ LINE ส่ง next ต่อ", line_next(r) == "/dashboard/", line_next(r))

    c = Client()
    r = get(c, "/crm/")
    ck("/crm/ → /login/", r.status_code == 302 and r["Location"] == "/login/", r.get("Location"))
    ck("หน้า login จำ /crm/", hidden_next(get(c, "/login/")) == "/crm/")

    c = Client()
    r = get(c, "/track/")
    ck("/track/ (@login_required ของระบบรถ) → /login/", r.status_code == 302 and r["Location"] == "/login/", r.get("Location"))
    ck("หน้า login จำ /track/", hidden_next(get(c, "/login/")) == "/track/")

    c = Client()
    r = get(c, "/track/login/")
    ck("/track/login/ → /login/", r.status_code == 302 and r["Location"] == "/login/", r.get("Location"))

    print("[2] เปิด /login/?next=… ตรงๆ")
    c = Client()
    r = get(c, "/login/?next=/connect/%3Fid%3D5")
    ck("ลิงก์เก่า /login/?next= → /login/", r.status_code == 302 and r["Location"] == "/login/", r.get("Location"))
    ck("จำ next ที่มี query (/connect/?id=5)", hidden_next(get(c, "/login/")) == "/connect/?id=5")
    r = get(c, "/login/?bg=1&next=/admin/")
    ck("พารามิเตอร์อื่นคงไว้ (?bg=1)", r.status_code == 302 and r["Location"] == "/login/?bg=1", r.get("Location"))
    ck("…และจำ /admin/", hidden_next(get(c, "/login/?bg=1")) == "/admin/")

    print("[3] กันพาไปเว็บอื่น · ไม่แตะแอปมือถือ")
    for bad in ("https://evil.example/", "//evil.example/x", "/\\evil.example"):
        c = Client()
        r = get(c, "/login/", data={"next": bad})
        ck("next อันตราย %s → ตัดทิ้ง" % bad, r.status_code == 302 and r["Location"] == "/login/", r.get("Location"))
        ck("…ไม่ถูกเก็บ (กลับหน้าแรกตามปกติ)", hidden_next(get(c, "/login/")) == "/dashboard/")
    c = Client()
    r = get(c, "/login/?next=/m/handoff/abc123")
    ck("ทางของแอปมือถือ /m/… ไม่ถูกย้าย (200 · next อยู่ในหน้า)", r.status_code == 200 and hidden_next(r) == "/m/handoff/abc123",
       (r.status_code, hidden_next(r)))

    print("[4] login แล้วพากลับถูกหน้า + ใช้แล้วล้าง")
    with override_settings(OXLET_ADMIN_USER="admin", OXLET_ADMIN_PASSWORD="pw-test-123"):
        c = Client()
        get(c, "/crm/")
        nxt = hidden_next(get(c, "/login/"))
        r = c.post("/login/", {"username": "admin", "password": "pw-test-123", "next": nxt}, secure=True)
        ck("login แอดมิน → พากลับ /crm/", r.status_code == 302 and r["Location"] == "/crm/", (r.status_code, r.get("Location")))
        get(c, "/crm/")
        r = get(c, "/login/")
        ck("ใช้แล้วล้าง: เข้า /login/ ทีหลัง → /dashboard/ (ไม่ใช่ /crm/ ค้าง)",
           r.status_code == 302 and r["Location"] == "/dashboard/", r.get("Location"))

    print("[5] LINE Login ใช้ค่าที่เก็บไว้")
    with override_settings(LINE_LOGIN_CHANNEL_ID="123", LINE_LOGIN_CHANNEL_SECRET="s"):
        c = Client()
        get(c, "/connect/")
        r = get(c, "/auth/line/start")
        q = parse_qs(urlparse(r.get("Location", "")).query)
        ck("ไปหน้า LINE ได้", r.status_code == 302 and "access.line.me" in r.get("Location", ""), r.get("Location"))
        ck("จำ next=/connect/ ไว้พากลับหลัง LINE", c.session.get("line_login_next") == "/connect/", c.session.get("line_login_next"))
        ck("redirect_uri ไม่มี next", "next" not in (q.get("redirect_uri") or [""])[0])

    print("[6] หมดอายุ / ฟังก์ชันย่อย")

    class _Req:
        def __init__(self, sess):
            self.session = sess
    ck("เก็บไว้ไม่เกิน 30 นาที = ใช้ได้", MW.login_next(_Req({MW.NEXT_KEY: {"u": "/me/", "t": int(time.time()) - 60}})) == "/me/")
    ck("เกิน 30 นาที = ไม่ใช้", MW.login_next(_Req({MW.NEXT_KEY: {"u": "/me/", "t": int(time.time()) - 31 * 60}})) == "")
    ck("ค่าเสีย = ไม่ใช้", MW.login_next(_Req({MW.NEXT_KEY: "x"})) == "")
    ck("safe_next: path ปกติ", MW.safe_next("/s/abc/?uid=1") == "/s/abc/?uid=1")
    ck("safe_next: ขึ้นบรรทัดใหม่ = ทิ้ง", MW.safe_next("/a\r\nSet-Cookie: x") == "")
    ck("safe_next: javascript: = ทิ้ง", MW.safe_next("javascript:alert(1)") == "")

    print("[7] แอปมือถือ (token) ไม่โดนแตะ")
    r = Client().get("/connect/api/summary", secure=True, HTTP_AUTHORIZATION="Bearer nope")
    ck("token ผิด = 401 เหมือนเดิม", r.status_code == 401, r.status_code)
finally:
    _runner.teardown_databases(_old)

print("\nผ่าน %d / %d" % (len(OK), len(OK) + len(BAD)))
if BAD:
    print("ไม่ผ่าน:\n  - " + "\n  - ".join(BAD))
    sys.exit(1)
