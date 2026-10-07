# -*- coding: utf-8 -*-
"""เทสต์: คนออกจากกลุ่มเช็คชื่อ → เอาออกจากระบบเช็คชื่อเอง · กลับเข้า = คืนให้ (checkout/membership.py · 7 ต.ค.69)

    python scripts/test_member_left.py

ใช้ฐานข้อมูลทดสอบแยก · body ของ event เป็นรูปแบบจริงของ LINE (memberLeft / memberJoined)
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
settings.CRON_SECRET = "s3cret"

import threading  # noqa: E402

from django.contrib.sessions.backends.signed_cookies import SessionStore  # noqa: E402
from django.db import connection  # noqa: E402
from django.test import Client  # noqa: E402

from checkout import membership as M  # noqa: E402
from checkout.models import Employee, LineProfile  # noqa: E402
from dashboard.models import EventLog  # noqa: E402
from dashboard.services import cache_store  # noqa: E402

OK, BAD = [], []


def ck(name, cond, got=""):
    (OK if cond else BAD).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else "   ได้: %r" % (got,)))


G = "C" + "a" * 32          # กลุ่มเช็คชื่อ
OTHER = "C" + "b" * 32      # กลุ่มอื่น


def ev(kind, uid, gid=G):
    key = "joined" if kind == "memberJoined" else "left"
    return {"type": kind, "source": {"type": "group", "groupId": gid},
            key: {"members": [{"type": "user", "userId": uid}]}, "timestamp": 1}


def emp(nick):
    return Employee.objects.get(nickname=nick)


try:
    cache_store.set_kv("checkin_notify_config", {"enabled": True, "mode": "group", "group_id": G})
    A = Employee.objects.create(nickname="เอ", position="ทีม A", work_start="9:00")
    B = Employee.objects.create(nickname="บอส", track_checkin=False)            # ผู้บริหาร (แอดมินปิดเอง)
    UA, UB, UX = "U" + "1" * 32, "U" + "2" * 32, "U" + "9" * 32
    LineProfile.objects.create(user_id=UA, display_name="A", is_employee=True, employee=A)
    LineProfile.objects.create(user_id=UB, display_name="B", is_employee=True, employee=B)

    print("[1] ออกจากกลุ่มเช็คชื่อ")
    r = M.handle_member_events({"events": [ev("memberLeft", UA)]})
    ck("★ ออกจากกลุ่ม → ปิดเช็คชื่อ (ไม่ขึ้นตาราง ไม่ถูกแท็ก)", emp("เอ").track_checkin is False and r.get("left") == ["เอ"], r)
    ck("ไม่ลบออกจากทะเบียนพนักงาน (ประวัติยังอยู่)", Employee.objects.filter(nickname="เอ").exists())
    ck("จดว่าระบบเป็นคนปิด (คืนให้ได้ตอนกลับเข้า)", str(A.id) in M.left_members(), M.left_members())
    ck("แคช \"อยู่ในกลุ่มไหม\" ของตารางเช็คชื่อ = ไม่อยู่แล้ว",
       ((cache_store.get_kv("checkin_group_member") or {}).get("data") or {}).get(G, {}).get(UA, {}).get("in") is False)
    ck("จดลงล็อกเหตุการณ์", EventLog.objects.filter(kind="line_member", target="เอ").exists())
    M.handle_member_events({"events": [ev("memberLeft", UA)]})
    ck("event ซ้ำ (LINE ยิงซ้ำ) = ไม่พัง ไม่ทำซ้ำ", emp("เอ").track_checkin is False)

    print("[2] คนที่แอดมินปิดเช็คชื่อเอง / คนนอกทะเบียน / กลุ่มอื่น")
    M.handle_member_events({"events": [ev("memberLeft", UB)]})
    ck("ผู้บริหารที่ปิดเช็คชื่ออยู่แล้ว = ไม่จดว่าระบบปิด", str(B.id) not in M.left_members())
    M.handle_member_events({"events": [ev("memberJoined", UB)]})
    ck("★ ผู้บริหารเข้ากลุ่ม = ไม่เปิดเช็คชื่อให้ (แอดมินปิดเอง)", emp("บอส").track_checkin is False)
    r = M.handle_member_events({"events": [ev("memberLeft", UX)]})
    ck("คนไม่อยู่ในทะเบียน = จดอย่างเดียว ไม่พัง", r.get("unknown") == 1, r)
    C2 = Employee.objects.create(nickname="ซี", work_start="8:30")
    LineProfile.objects.create(user_id="U" + "3" * 32, display_name="C", is_employee=True, employee=C2)
    M.handle_member_events({"events": [ev("memberLeft", "U" + "3" * 32, gid=OTHER)]})
    ck("★ ออกจากกลุ่มอื่น (ไม่ใช่กลุ่มเช็คชื่อ) = ไม่แตะ", emp("ซี").track_checkin is True)

    print("[3] กลับเข้ากลุ่ม")
    r = M.handle_member_events({"events": [ev("memberJoined", UA)]})
    ck("★ กลับเข้ากลุ่ม → คืนเข้าระบบเช็คชื่อเอง", emp("เอ").track_checkin is True and r.get("back") == ["เอ"], r)
    ck("ไม่ค้างในรายการคนที่ระบบปิด", str(A.id) not in M.left_members())

    print("[4] ทางจริง: n8n → /api/line/group_ingest → thread")
    _start0, _close0 = threading.Thread.start, connection.close
    threading.Thread.start = lambda self: self.run()          # ทำในเธรดเดียวกัน (ฐานข้อมูลทดสอบอยู่ในหน่วยความจำ)
    connection.close = lambda *a, **k: None
    try:
        cl = Client()
        body = {"destination": "Uxxx", "events": [ev("memberLeft", UA)]}
        r = cl.post("/api/line/group_ingest?secret=s3cret", data=json.dumps(body),
                    content_type="application/json", secure=True)
        ck("★ event คนออกจากกลุ่มที่ n8n ส่งมา → ปิดเช็คชื่อ", r.status_code == 200 and emp("เอ").track_checkin is False,
           (r.status_code, emp("เอ").track_checkin))
        last = (cache_store.get_kv("line_member_last") or {}).get("data") or {}
        ck("จด line_member_last ไว้ดูว่า n8n ส่ง event นี้มาจริง", last.get("events") == 1 and last.get("left") == ["เอ"], last)
    finally:
        threading.Thread.start, connection.close = _start0, _close0

    print("[5] หน้าพนักงาน")
    adm = Client()
    st = SessionStore(); st["oxlet_user"] = {"user_id": "admin", "nickname": "admin", "position": "admin"}; st.save()
    adm.cookies[settings.SESSION_COOKIE_NAME] = st.session_key
    d = adm.get("/checkout/api/employees", secure=True).json()
    row = next((e for e in d.get("employees", []) if e["nickname"] == "เอ"), {})
    ck("API บอกวันที่ออกจากกลุ่ม (leftGroupAt)", bool(row.get("leftGroupAt")) and row.get("trackCheckin") is False, row)
    body = dict(id=A.id, nickname="เอ", position="ทีม A", workStart="9:00", trackCheckin=True, active=True)
    r = adm.post("/checkout/api/employees", data=json.dumps(dict(body, action="save")), content_type="application/json",
                 secure=True)
    ck("★ แอดมินติ๊กเช็คชื่อคืนเอง → ล้างป้าย \"ออกจากกลุ่ม\"", r.status_code == 200 and emp("เอ").track_checkin is True
       and str(A.id) not in M.left_members(), (r.status_code, r.content[:200]))
finally:
    _runner.teardown_databases(_old)

print("\nผ่าน %d / %d" % (len(OK), len(OK) + len(BAD)))
if BAD:
    print("ไม่ผ่าน:\n  - " + "\n  - ".join(BAD))
    sys.exit(1)
