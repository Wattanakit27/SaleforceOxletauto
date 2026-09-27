# -*- coding: utf-8 -*-
"""ตรวจว่าหน้าสถานะระบบ "ร้อง" จริงเมื่องานส่งเข้าไลน์ล้ม (27 ก.ย.69)

    python scripts/test_health_send.py

**ทำไมต้องทดสอบให้ถึงตัว view** — บล็อกเช็คห่อด้วย `try/except` กว้าง ตามบทเรียนเดิม
("`except` ที่ครอบทั้งฟังก์ชันทำให้ 'ไม่มีข้อมูล' กับ 'โค้ดพัง' หน้าตาเหมือนกัน")
ถ้าไม่เรียก view จริงจะไม่รู้ว่าโค้ดได้รันหรือโดนกลืนไปเงียบๆ
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
os.environ.setdefault("DB_HOST", "")
os.environ.setdefault("DEBUG", "True")

import django

django.setup()

from django.test.utils import setup_test_environment
from django.test.runner import DiscoverRunner

setup_test_environment()
runner = DiscoverRunner(verbosity=0, interactive=False)
old_cfg = runner.setup_databases()

import json

from django.test import Client
from django.utils import timezone

from dashboard.models import EventLog
from dashboard.services import fetch_dashboard as FD
from dashboard.services.eventlog import SEND

fail = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        if extra:
            print("        " + extra)
        fail.append(name)


FD.fetch_dashboard_data = lambda *a, **k: {}      # ไม่ต้องยิง Google ตอนทดสอบ

now = timezone.now()
# ตามด่วน: ล้มหมด ไม่มีสำเร็จเลย → ต้องขึ้น err
for i in range(14):
    EventLog.objects.create(kind=SEND, name="ตามด่วน (cron ตามตารางส่ง)",
                            target="Ux%d" % i, ok=False, at=now)
# ตารางเช็คชื่อ: สำเร็จบ้าง ไม่ถึงบ้าง → ต้องขึ้น warn
EventLog.objects.create(kind=SEND, name="ตารางเช็คชื่อเข้างาน", target="Cg", ok=True, at=now)
EventLog.objects.create(kind=SEND, name="ตารางเช็คชื่อเข้างาน", target="Uz", ok=False, at=now)
# งานที่สำเร็จล้วน → ต้องไม่ถูกเอ่ยถึง
EventLog.objects.create(kind=SEND, name="การ์ดสรุปลีด", target="Cok", ok=True, at=now)

c = Client()
# โปรเจกต์ใช้ session แบบ signed-cookie → ต้องยัดคุกกี้เอง
# (`client.session.save()` ไม่เขียนคุกกี้ให้ เพราะข้อมูลอยู่ใน key ของคุกกี้เอง)
from importlib import import_module

from django.conf import settings as _S

_store = import_module(_S.SESSION_ENGINE).SessionStore()
_store["oxlet_user"] = {"user_id": "admin", "nickname": "admin", "position": "admin"}
_store.save()
c.cookies[_S.SESSION_COOKIE_NAME] = _store.session_key
# secure=True เพราะโปรเจกต์บังคับ https (ไม่งั้นได้ 301 redirect)
r = c.get("/api/admin/system_health", secure=True)
ck("view ตอบ 200", r.status_code == 200, "ได้ %s" % r.status_code)
body = json.loads(r.content.decode())
msgs = [i["msg"] for i in body.get("issues", [])]
errs = [i["msg"] for i in body.get("issues", []) if i["level"] == "err"]
warns = [i["msg"] for i in body.get("issues", []) if i["level"] == "warn"]

ck("ร้องว่าตามด่วนล้มทั้งงาน (err)",
   any("ล้มทั้งงาน" in m and "ตามด่วน" in m for m in errs),
   "issues=%s" % msgs)
ck("บอกจำนวนที่ล้มมาด้วย", any("ล้ม 14" in m for m in errs), "errs=%s" % errs)
ck("บอกวิธีไล่ต่อ (ตารางล็อก)", any("dash_event_log" in m for m in errs))
ck("งานที่สำเร็จบางส่วน = warn ไม่ใช่ err",
   any("ไม่ถึง 1 จาก 2" in m for m in warns), "warns=%s" % warns)
ck("งานที่สำเร็จล้วนไม่ถูกเอ่ยถึง", not any("การ์ดสรุปลีด" in m for m in msgs))

# ไม่มีล็อกเลย = ต้องเงียบ (ไม่ใช่ร้องหลอก)
EventLog.objects.all().delete()
body2 = json.loads(c.get("/api/admin/system_health", secure=True).content.decode())
ck("ไม่มีล็อกส่งเลย → ไม่ร้องเรื่องนี้",
   not any("ส่งเข้าไลน์" in i["msg"] for i in body2.get("issues", [])),
   "issues=%s" % [i["msg"] for i in body2.get("issues", [])])

print()
if fail:
    print("ไม่ผ่าน %d ข้อ: %s" % (len(fail), " · ".join(fail)))
else:
    print("ผ่านทั้งหมด")
runner.teardown_databases(old_cfg)
sys.exit(1 if fail else 0)
