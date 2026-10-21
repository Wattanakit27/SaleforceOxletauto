# -*- coding: utf-8 -*-
"""เทสต์โปรไฟล์พนักงานในแอป (★ 21 ต.ค.69 · checkout/staff_profile.py · /api/m/me)
ชื่อ + รูปจาก LINE · แผนก/ตำแหน่ง/เวลาเข้างาน/วันหยุดจากทะเบียน (แอดมินกรอก)

    python scripts/test_staff_profile.py

ฐานข้อมูลทดสอบแยก · test client จริงทั้งสาย (LINE Login callback → /m/handoff → /api/m/token → /api/m/me)
· ปลอมแค่ขอบระบบ: `requests` (LINE) + ฟังก์ชันหาพนักงานจากชีตตอน login
"""
import base64
import hashlib
import io
import json
import os
import re
import sys
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

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
settings.LINE_LOGIN_CHANNEL_ID = "1234567890"
settings.LINE_LOGIN_CHANNEL_SECRET = "x"
settings.LINE_LOGIN_CALLBACK = "https://testserver/auth/line/callback"
settings.LINE_CHANNEL_ACCESS_TOKEN = "tok-crm"
settings.LINE_PUSH_CHANNEL_ACCESS_TOKEN = "tok-push"

import requests  # noqa: E402
from django.contrib.sessions.backends.signed_cookies import SessionStore  # noqa: E402
from django.test import Client  # noqa: E402
from django.utils import timezone  # noqa: E402

from checkout import staff_profile as SP  # noqa: E402
from checkout.models import Employee, GroupChat, LineProfile  # noqa: E402
from dashboard import views as DV  # noqa: E402
from dashboard.services import google_sheets  # noqa: E402

google_sheets.fetch_sheet = lambda *a, **k: []
SP.BG = False

PASS = FAIL = 0


def ok(cond, label):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓", label)
    else:
        FAIL += 1
        print("  ✗", label)


class R:
    def __init__(self, status, data):
        self.status_code, self._d = status, data

    def json(self):
        return self._d


CALLS = []
LINE_PROFILE = {}          # โปรไฟล์ที่ LINE Login ตอบ
BOT_PROFILES = {}          # url ของ Messaging API → โปรไฟล์ (ไม่มี = 404)
_real_get, _real_post = requests.get, requests.post


def fake_get(url, *a, **k):
    CALLS.append(url)
    if url == "https://api.line.me/v2/profile":
        return R(200, dict(LINE_PROFILE))
    if url in BOT_PROFILES:
        return R(200, dict(BOT_PROFILES[url]))
    return R(404, {"message": "Not found"})


def fake_post(url, *a, **k):
    CALLS.append(url)
    if "oauth2/v2.1/token" in url:
        return R(200, {"access_token": "AT"})
    return R(404, {})


requests.get, requests.post = fake_get, fake_post

LOGIN_USER = {}


def fake_login(request, line_user_id, next_url="/dashboard/"):
    """แทนการอ่านชีตพนักงานตอน login (ไม่ใช่ส่วนที่ทดสอบ)"""
    if not LOGIN_USER:
        return None, "ไม่พบบัญชี LINE นี้ในรายชื่อพนักงาน"
    request.session["oxlet_user"] = dict(LOGIN_USER, user_id=line_user_id)
    return next_url, None


DV._login_with_line_user_id = fake_login
LINE_ID = re.compile(r"U[0-9a-f]{32}")


def line_login_token():
    """เปิดแอป → LINE Login → กลับเข้าแอป → แลก token (เส้นทางเดียวกับของจริง)"""
    v = base64.urlsafe_b64encode(os.urandom(40)).decode().rstrip("=")
    ch = base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).decode().rstrip("=")
    c = Client()
    r = c.get("/m/login", {"r": "exp://192.168.1.20:8081/--/auth", "c": ch}, secure=True)
    r = c.get(r["Location"], secure=True)                       # /auth/line/start → access.line.me
    state = parse_qs(urlparse(r["Location"]).query)["state"][0]
    r = c.get("/auth/line/callback", {"code": "abc", "state": state}, secure=True)
    hand = r["Location"]
    r = c.get(hand, secure=True)
    code = re.search(r"code=([^&]+)", r["Location"]).group(1)
    r3 = Client().post("/api/m/token", json.dumps({"code": code, "verifier": v}),
                       content_type="application/json", secure=True)
    return r3.json()


def token_for(user):
    v = base64.urlsafe_b64encode(os.urandom(40)).decode().rstrip("=")
    ch = base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).decode().rstrip("=")
    c = Client()
    st = SessionStore()
    st["oxlet_user"] = user
    st.save()
    c.cookies[settings.SESSION_COOKIE_NAME] = st.session_key
    r = c.get("/m/login", {"r": "exp://192.168.1.20:8081/--/auth", "c": ch}, secure=True)
    r2 = c.get(r["Location"], secure=True)
    code = re.search(r"code=([^&]+)", r2["Location"]).group(1)
    r3 = Client().post("/api/m/token", json.dumps({"code": code, "verifier": v}),
                       content_type="application/json", secure=True)
    return r3.json()["token"]


def me(tok):
    r = Client().get("/api/m/me", HTTP_AUTHORIZATION="Bearer " + tok, secure=True)
    return r


try:
    print("\n[1] กติกาพื้นฐาน")
    ok(SP.clean_url("https://profile.line-scdn.net/abc") == "https://profile.line-scdn.net/abc", "ลิงก์ https ผ่าน")
    ok(SP.clean_url("http://x/a.jpg") == "" and SP.clean_url("javascript:alert(1)") == "", "ไม่ใช่ https = ทิ้ง")
    ok(SP.clean_url("https://x/" + "a" * 600) == "", "ยาวเกิน 500 = ทิ้ง")
    now = timezone.now()
    e = Employee(nickname="t", picture_url="https://p/1", picture_at=now - timedelta(days=3))
    ok(not SP.due(e, now), "มีรูปแล้ว 3 วัน = ยังไม่ถามใหม่")
    e.picture_at = now - timedelta(days=8)
    ok(SP.due(e, now), "มีรูปแล้ว 8 วัน = ถามใหม่")
    e.picture_url, e.picture_at = "", now - timedelta(hours=5)
    ok(not SP.due(e, now), "ถามแล้วไม่ได้รูป 5 ชม. = ยังไม่ถาม")
    e.picture_at = now - timedelta(hours=25)
    ok(SP.due(e, now), "ถามแล้วไม่ได้รูป 25 ชม. = ลองใหม่")

    print("\n[2] LINE Login → แอปได้ชื่อ + รูปจาก LINE")
    mat = Employee.objects.create(nickname="มัท", display_name="", department="sales", position="ทีม A",
                                  work_start="9:00", day_off="อาทิตย์")
    UID = "U" + "a" * 32
    LineProfile.objects.create(user_id=UID, nickname="มัท", is_employee=True, employee=mat)
    LOGIN_USER.update({"nickname": "มัท", "display_name": "", "position": "seller", "seller_name": "มัท"})
    LINE_PROFILE.update({"userId": UID, "displayName": "Mat ⚡", "pictureUrl": "https://profile.line-scdn.net/mat1"})
    j = line_login_token()
    ok(j.get("ok") and j.get("token"), "login ผ่าน LINE แล้วได้ token")
    m = j.get("me") or {}
    ok(m.get("name") == "Mat ⚡", "ชื่อในแอป = ชื่อที่ตั้งใน LINE (%s)" % m.get("name"))
    ok(m.get("picture") == "https://profile.line-scdn.net/mat1", "รูปในแอป = รูปโปรไฟล์ LINE")
    mat.refresh_from_db()
    ok(mat.picture_url == "https://profile.line-scdn.net/mat1" and mat.picture_at, "เก็บรูปไว้ที่ทะเบียนพนักงาน")
    ok(mat.display_name == "Mat ⚡", "ทะเบียนยังไม่มีชื่อ LINE → เติมให้")
    ok(not LINE_ID.search(json.dumps(j, ensure_ascii=False)), "คำตอบตอนแลก token ไม่มี LINE user id")

    tok = j["token"]
    r = me(tok)
    p = r.json()["me"].get("profile") or {}
    ok(r.status_code == 200 and p.get("registered"), "/api/m/me มีโปรไฟล์ของคนในทะเบียน")
    ok(p.get("nickname") == "มัท" and p.get("lineName") == "Mat ⚡", "ชื่อเล่นจากทะเบียน · ชื่อจาก LINE")
    ok(p.get("departmentName") == "เซลล์" and p.get("position") == "ทีม A", "แผนก/ตำแหน่งจากทะเบียน (%s · %s)"
       % (p.get("departmentName"), p.get("position")))
    ok(p.get("workStart") == "9:00" and p.get("dayOff") == "อาทิตย์", "เวลาเข้างาน/วันหยุดจากทะเบียน")
    ok(p.get("missing") == [], "กรอกครบ = ไม่มีช่องค้าง")
    ok(not LINE_ID.search(r.content.decode()), "/api/m/me ไม่มี LINE user id")

    print("\n[3] ชื่อ LINE ที่แอดมินแก้ไว้ในทะเบียน ไม่ถูกทับ · ไม่มีรูป = ล้างของเก่า")
    Employee.objects.filter(pk=mat.pk).update(display_name="เซลมัท OxletAuto")
    LINE_PROFILE.update({"displayName": "Mat new", "pictureUrl": ""})
    j2 = line_login_token()
    mat.refresh_from_db()
    ok(mat.display_name == "เซลมัท OxletAuto", "ชื่อในทะเบียนเดิมยังอยู่")
    ok(mat.picture_url == "", "LINE ไม่มีรูปแล้ว = ล้างรูปเก่า")
    ok((j2.get("me") or {}).get("name") == "Mat new", "แอปโชว์ชื่อ LINE ล่าสุดจากการ login")

    print("\n[4] คนที่ login ไว้ก่อนแล้ว → ถามรูปจาก LINE ด้วยบัญชีที่ผูกไว้ (ทุก 7 วัน)")
    nuan = Employee.objects.create(nickname="นวล", display_name="Nuan", department="sales", position="ทีม B")
    UID2 = "U" + "b" * 32
    LineProfile.objects.create(user_id=UID2, nickname="นวล", is_employee=True, employee=nuan, channel="push")
    GroupChat.objects.create(message_id="m1", chat_type=GroupChat.GROUP, group_id="C" + "1" * 32,
                             sender_id=UID2, text="รายงาน", sent_at=timezone.now())
    member_url = "https://api.line.me/v2/bot/group/%s/member/%s" % ("C" + "1" * 32, UID2)
    BOT_PROFILES[member_url] = {"displayName": "Nuan", "pictureUrl": "https://profile.line-scdn.net/nuan"}
    CALLS.clear()
    tok2 = token_for({"user_id": "U" + "9" * 32, "nickname": "นวล", "display_name": "Nuan",
                      "position": "seller", "seller_name": "นวล"})
    r = me(tok2)
    p = r.json()["me"]["profile"]
    ok(member_url in CALLS, "ถาม LINE ผ่านกลุ่มที่เขาพิมพ์ล่าสุด")
    ok(r.json()["me"].get("picture") == "https://profile.line-scdn.net/nuan", "ได้รูปจาก LINE")
    ok(p.get("missing") == ["เวลาเข้างาน", "วันหยุด"], "ช่องที่แอดมินยังไม่กรอก: %s" % p.get("missing"))
    CALLS.clear()
    me(tok2)
    ok(not CALLS, "เปิดซ้ำภายใน 7 วัน = ไม่ถาม LINE อีก")

    print("\n[5] ถาม LINE ไม่ได้ = ไม่ถามทุกครั้งที่เปิดแอป · มีรูปเดิมใช้ต่อ")
    Employee.objects.filter(pk=nuan.pk).update(picture_at=timezone.now() - timedelta(days=9))
    BOT_PROFILES.pop(member_url)
    CALLS.clear()
    r = me(tok2)
    ok(CALLS, "ครบ 7 วัน = ลองถามใหม่")
    ok(r.json()["me"].get("picture") == "https://profile.line-scdn.net/nuan", "ถามไม่ได้ = ใช้รูปเดิม")
    CALLS.clear()
    me(tok2)
    ok(not CALLS, "พลาดแล้วไม่ลองซ้ำทันที (รอ 24 ชม.)")
    nuan.refresh_from_db()
    ok(not SP.due(nuan, timezone.now() + timedelta(hours=23)) and SP.due(nuan, timezone.now() + timedelta(hours=25)),
       "ลองใหม่หลัง 24 ชม.")

    print("\n[6] ไม่มีในทะเบียน / บัญชีคนงาน (ไม่มี LINE)")
    tok3 = token_for({"user_id": "U" + "d" * 32, "nickname": "ใครก็ไม่รู้", "display_name": "x",
                      "position": "seller", "seller_name": "ใครก็ไม่รู้"})
    p = me(tok3).json()["me"]["profile"]
    ok(p["registered"] is False and len(p["missing"]) == 4, "ไม่มีในทะเบียน = แจ้งว่ายังไม่ลงทะเบียน")
    from django.contrib.auth.models import User
    User.objects.create_user("chang1", password="x")
    tong = Employee.objects.create(nickname="ช่างต้อง", department="technician", position="ช่างและคนงาน",
                                   work_start="8:00", day_off="อาทิตย์")
    tok4 = token_for({"user_id": "django_chang1", "nickname": "ช่างต้อง", "display_name": "ช่างต้อง",
                      "position": "worker"})
    CALLS.clear()
    r = me(tok4)
    p = r.json()["me"]["profile"]
    ok(r.status_code == 200 and p["registered"] and p["departmentName"], "คนงานได้ข้อมูลจากทะเบียน (%s)"
       % p.get("departmentName"))
    ok(not CALLS and not r.json()["me"].get("picture"), "ไม่มีบัญชี LINE ผูก = ไม่ถาม LINE · ไม่มีรูป")
    tong.refresh_from_db()
    ok(tong.picture_at is not None, "จดว่าถามแล้ว (ไม่ถามซ้ำทุกครั้ง)")

    print("\n[7] login ไม่ผ่าน (ไม่ใช่พนักงาน) = ไม่เก็บอะไร")
    LOGIN_USER.clear()
    n0 = Employee.objects.exclude(picture_url="").count()
    c = Client()
    r = c.get("/auth/line/start", {"next": "/dashboard/"}, secure=True)
    state = parse_qs(urlparse(r["Location"]).query)["state"][0]
    LINE_PROFILE.update({"userId": "U" + "e" * 32, "displayName": "คนนอก", "pictureUrl": "https://p/x"})
    r = c.get("/auth/line/callback", {"code": "abc", "state": state}, secure=True)
    ok(r.status_code == 200 and Employee.objects.exclude(picture_url="").count() == n0, "คนนอกไม่ถูกเก็บรูป")
finally:
    requests.get, requests.post = _real_get, _real_post
    _runner.teardown_databases(_old)

print("\nผ่าน %d · ไม่ผ่าน %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
