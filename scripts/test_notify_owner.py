# -*- coding: utf-8 -*-
"""เทสต์ /api/notify/owner (★ 14 ต.ค.69 · hook เครื่อง dev → LINE หาเจ้าของ)

    python scripts/test_notify_owner.py

ฐานข้อมูลทดสอบแยก · ปลอมแค่ requests.post (LINE push) · ไม่ส่งอะไรออกจริง
"""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
os.environ.setdefault("DB_HOST", "")
os.environ.setdefault("DEBUG", "True")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.test.runner import DiscoverRunner  # noqa: E402
from django.test.utils import setup_test_environment  # noqa: E402

setup_test_environment()
_runner = DiscoverRunner(verbosity=0, interactive=False)
_old = _runner.setup_databases()
if "testserver" not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]

import requests  # noqa: E402
from django.test import Client  # noqa: E402

from checkout.models import Employee, LineProfile  # noqa: E402
from dashboard import views as V  # noqa: E402
from dashboard.services import google_sheets  # noqa: E402

google_sheets.fetch_sheet = lambda *a, **k: []

PASS = FAIL = 0


def ok(cond, label):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓", label)
    else:
        FAIL += 1
        print("  ✗", label)


SENT = []


class _Resp:
    status_code = 200
    text = "{}"

    def json(self):
        return {}


_orig_post = requests.post


def fake_post(url, *a, **k):
    if "api.line.me" in str(url):
        SENT.append({"url": url, "json": k.get("json")})
        return _Resp()
    return _orig_post(url, *a, **k)


requests.post = fake_post
settings.CRON_SECRET = "s3cret-test"
settings.LINE_PUSH_CHANNEL_ACCESS_TOKEN = "push-token-test"
settings.LINE_CHANNEL_ACCESS_TOKEN = "crm-token-test"

try:
    e = Employee.objects.create(nickname="Wattanakit", position="", track_checkin=False)
    LineProfile.objects.create(user_id="U" + "9" * 32, display_name="Wattanakit", employee=e,
                               is_employee=True, channel="push")
    c = Client()

    def post(body, secret="s3cret-test"):
        h = {"HTTP_X_CRON_SECRET": secret} if secret is not None else {}
        return c.post("/api/notify/owner", json.dumps(body), content_type="application/json", secure=True, **h)

    print("\n[1] สิทธิ์")
    ok(post({"text": "x"}, secret=None).status_code == 401 and not SENT, "ไม่มีรหัสลับ → 401 ไม่ส่ง")
    ok(post({"text": "x"}, secret="ผิด").status_code == 401 and not SENT, "รหัสลับผิด → 401 ไม่ส่ง")
    ok(c.get("/api/notify/owner", secure=True).status_code == 405, "GET → 405")

    print("\n[2] ส่ง")
    r = post({"text": "งานเสร็จแล้ว ใช้เวลา 12 นาที"})
    ok(r.status_code == 200 and r.json().get("ok"), "ส่งสำเร็จ")
    ok(len(SENT) == 1 and SENT[0]["json"]["to"] == "U" + "9" * 32, "ส่งถึงไอดีของเจ้าของ (Wattanakit)")
    ok("12 นาที" in SENT[0]["json"]["messages"][0]["text"], "ข้อความตรงที่ส่งมา")
    ok(post({"text": ""}).status_code == 400, "ไม่มีข้อความ → 400")
    long = "ก" * 3000
    post({"text": long})
    ok(len(SENT[-1]["json"]["messages"][0]["text"]) <= 1000, "ข้อความยาวถูกตัดที่ 1000 ตัว")

    print("\n[3] จำกัดจำนวน/ชม.")
    n0 = len(SENT)
    codes = [post({"text": "รอบ %d" % i}).status_code for i in range(V.NOTIFY_OWNER_PER_HOUR)]
    ok(codes[-1] == 429 and len(SENT) - n0 == V.NOTIFY_OWNER_PER_HOUR - 2,
       "ครบ %d ข้อความใน 1 ชม. → 429 ไม่ส่งเพิ่ม" % V.NOTIFY_OWNER_PER_HOUR)
finally:
    requests.post = _orig_post
    _runner.teardown_databases(_old)

print("\nผ่าน %d · ไม่ผ่าน %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
