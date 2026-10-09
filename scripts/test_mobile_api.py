# -*- coding: utf-8 -*-
"""เทสต์ login แอปมือถือ + ตัวกลาง Bearer token (9 ต.ค.69)

    python scripts/test_mobile_api.py

ฐานข้อมูลทดสอบแยก (สร้างใหม่ทุกครั้ง) · เรียกผ่าน test client จริง (middleware ครบทั้งสาย)
· ปลอมแค่ชีตพนักงาน (ขอบระบบ Google) — ไม่ปลอมฟังก์ชันของเราเอง
"""
import base64
import hashlib
import io
import json
import os
import re
import sys
from datetime import timedelta

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

from django.contrib.sessions.backends.signed_cookies import SessionStore  # noqa: E402
from django.test import Client  # noqa: E402
from django.utils import timezone  # noqa: E402

from checkout.models import Employee  # noqa: E402
from dashboard.models import MobileLogin, MobileToken  # noqa: E402
from dashboard.services import google_sheets  # noqa: E402
from dashboard.services import mobile_auth as MA  # noqa: E402

PASS = FAIL = 0


def ok(cond, label):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓", label)
    else:
        FAIL += 1
        print("  ✗", label)


SELLER = {"user_id": "U" + "a" * 32, "nickname": "มัท", "display_name": "เซลมัท",
          "position": "seller", "seller_name": "มัท"}
ADMIN = {"user_id": "admin", "nickname": "admin", "display_name": "admin", "position": "admin"}
DEV = "exp://192.168.1.20:8081/--/auth"


def browser(user=None, csrf=False):
    """เบราว์เซอร์ของระบบในมือถือ (ตอน login) — มีคุกกี้ session ของเว็บถ้า login แล้ว"""
    c = Client(enforce_csrf_checks=csrf)
    if user:
        st = SessionStore()
        st["oxlet_user"] = user
        st.save()
        c.cookies[settings.SESSION_COOKIE_NAME] = st.session_key
    return c


def pkce():
    v = base64.urlsafe_b64encode(os.urandom(40)).decode().rstrip("=")
    ch = base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).decode().rstrip("=")
    return v, ch


def full_login(user, redirect=DEV):
    """ทางเดินเต็ม: /m/login → (login เว็บแล้ว) → /m/handoff → รหัส → token"""
    v, ch = pkce()
    b = browser(user)
    r = b.get("/m/login", {"r": redirect, "c": ch}, secure=True)
    r2 = b.get(r["Location"], secure=True)
    code = re.search(r"code=([^&]+)", r2["Location"]).group(1)
    app = Client()
    r3 = app.post("/api/m/token", json.dumps({"code": code, "verifier": v, "device": "iPhone ทดสอบ"}),
                  content_type="application/json", secure=True)
    return r3.json().get("token")


# ─────────────────────────────────────────────────────────────────────
print("\n[1] ที่อยู่กลับเข้าแอป — รับเฉพาะที่อนุญาต")
ok(MA.redirect_ok(DEV), "exp://<IP วงใน>/--/ (Expo Go ในวง Wi-Fi เดียวกัน) ผ่าน")
ok(MA.redirect_ok("oxletauto://auth"), "oxletauto:// (แอปจริง) ผ่าน")
for bad in ["https://evil.example/cb", "exp://evil.example:8081/--/auth", "exp://8.8.8.8:8081/--/auth",
            "exps://abc.exp.direct/--/auth", "exp://127.0.0.1:8081/--/auth", "exp://192.168.1.20:8081/auth",
            "javascript:alert(1)", "exp://192.168.1.20:8081/--/auth\nSet-Cookie: x", ""]:
    ok(not MA.redirect_ok(bad), "ปฏิเสธ %r" % bad[:40])
settings.MOBILE_DEV_REDIRECTS = False
ok(not MA.redirect_ok(DEV), "ปิด MOBILE_DEV_REDIRECTS แล้ว exp:// ใช้ไม่ได้ (oxletauto:// ยังได้)")
ok(MA.redirect_ok("oxletauto://auth"), "  …แต่ oxletauto:// ยังผ่าน")
settings.MOBILE_DEV_REDIRECTS = True

print("\n[2] เริ่ม login")
v, ch = pkce()
r = browser().get("/m/login", {"r": DEV, "c": ch}, secure=True)
ok(r.status_code == 302 and r["Location"].startswith("/auth/line/start?next=/m/handoff/"),
   "ยังไม่ login เว็บ → พาไป LINE Login ตัวเดิม แล้วกลับมา /m/handoff/<pid>")
r = browser().get("/m/login", {"r": "https://evil.example/cb", "c": ch}, secure=True)
ok(r.status_code == 400 and MobileLogin.objects.filter(redirect__contains="evil").count() == 0,
   "ที่อยู่ไม่ผ่าน → 400 และไม่สร้างใบผ่านทาง")
r = browser().get("/m/login", {"r": DEV, "c": "short"}, secure=True)
ok(r.status_code == 400, "challenge สั้นผิดรูป → 400")
r = browser(SELLER).get("/m/login", {"r": DEV, "c": ch}, secure=True)
ok(r.status_code == 302 and r["Location"].startswith("/m/handoff/"),
   "เบราว์เซอร์ login เว็บไว้แล้ว → ข้าม LINE ไป handoff เลย")

print("\n[3] handoff → รหัส → token")
b = browser(SELLER)
r = b.get("/m/login", {"r": DEV, "c": ch}, secure=True)
pid = r["Location"].rsplit("/", 1)[1]
r2 = b.get("/m/handoff/" + pid, secure=True)
ok(r2.status_code == 302 and r2["Location"].startswith(DEV + "?code="),
   "ส่งกลับเข้าแอปพร้อมรหัสใช้ครั้งเดียว" + ("" if r2.status_code == 302 else " [%s %s]" % (r2.status_code, r2.content[:200])))
code = r2["Location"].split("code=")[1]
rec = MobileLogin.objects.get(pid=pid)
ok(code not in json.dumps(list(MobileLogin.objects.values()), default=str), "ฐานข้อมูลเก็บแค่แฮช ไม่มีรหัสตัวจริง")
r3 = b.get("/m/handoff/" + pid, secure=True)
ok(r3.status_code == 400, "เปิด handoff ซ้ำ (ใบเดิม) → ใช้ไม่ได้")
app = Client()
bad = app.post("/api/m/token", json.dumps({"code": code, "verifier": "x" * 50}),
               content_type="application/json", secure=True)
ok(bad.status_code == 400, "รหัสลับ PKCE ผิด → แลก token ไม่ได้ (แอปอื่นที่ดักรหัสไปใช้ไม่ได้)")
good = app.post("/api/m/token", json.dumps({"code": code, "verifier": v, "device": "iPhone"}),
                content_type="application/json", secure=True)
gj = good.json()
ok(good.status_code == 200 and gj.get("token") and gj["me"]["nickname"] == "มัท", "แลก token สำเร็จ")
ok("U" + "a" * 32 not in good.content.decode(), "คำตอบไม่มี LINE user id ของพนักงาน")
again = app.post("/api/m/token", json.dumps({"code": code, "verifier": v}),
                 content_type="application/json", secure=True)
ok(again.status_code == 400, "รหัสเดิมแลกซ้ำไม่ได้ (ใช้ครั้งเดียว)")
TOK = gj["token"]
ok(not MobileToken.objects.filter(key_hash=TOK).exists() and MobileToken.objects.count() == 1,
   "เก็บ token เป็นแฮชเท่านั้น")

print("\n[4] หมดอายุ")
v2, ch2 = pkce()
b = browser(SELLER)
pid2 = b.get("/m/login", {"r": DEV, "c": ch2}, secure=True)["Location"].rsplit("/", 1)[1]
MobileLogin.objects.filter(pid=pid2).update(created_at=timezone.now() - timedelta(minutes=11))
ok(b.get("/m/handoff/" + pid2, secure=True).status_code == 400, "ใบผ่านทางเกิน 10 นาที → ใช้ไม่ได้")
v3, ch3 = pkce()
pid3 = b.get("/m/login", {"r": DEV, "c": ch3}, secure=True)["Location"].rsplit("/", 1)[1]
code3 = b.get("/m/handoff/" + pid3, secure=True)["Location"].split("code=")[1]
MobileLogin.objects.filter(pid=pid3).update(handed_at=timezone.now() - timedelta(minutes=3))
r = app.post("/api/m/token", json.dumps({"code": code3, "verifier": v3}),
             content_type="application/json", secure=True)
ok(r.status_code == 400, "รหัสที่ส่งเข้าแอปเกิน 2 นาที → แลกไม่ได้")

print("\n[5] เรียก API ด้วย Bearer")
H = {"HTTP_AUTHORIZATION": "Bearer " + TOK}
r = Client().get("/api/m/me", secure=True, **H)
ok(r.status_code == 200 and r.json()["me"]["position"] == "seller", "/api/m/me ได้ข้อมูลคนที่ login")
ok(settings.SESSION_COOKIE_NAME not in r.cookies, "ไม่ส่งคุกกี้ session กลับให้แอป")
ok(Client().get("/api/m/me", secure=True).status_code == 401, "ไม่มี token → 401")
r = Client().get("/api/m/me", secure=True, HTTP_AUTHORIZATION="Bearer มั่ว")
ok(r.status_code == 401 and r.json().get("relogin"), "token มั่ว → 401 + บอกให้ login ใหม่")

Employee.objects.create(nickname="มัท", position="ทีม A", active=True)
r = Client().get("/connect/api/inbox", secure=True, **H)
ok(r.status_code == 200 and r.json().get("ok"), "API เดิมของ Connect ใช้ token ได้เลย (ไม่ต้องเขียนใหม่)")
ok(settings.SESSION_COOKIE_NAME not in r.cookies, "  …และไม่ได้คุกกี้ session กลับไป")

# POST ด้วย token ไม่ต้องมี CSRF · POST ด้วยคุกกี้ยังต้องมีเหมือนเดิม
c = Client(enforce_csrf_checks=True)
r = c.post("/connect/api/claim", json.dumps({"id": 999999}), content_type="application/json", secure=True, **H)
ok(r.status_code != 403 or "CSRF" not in r.content.decode(), "POST ด้วย token ไม่โดนตรวจ CSRF (ไม่ได้ใช้คุกกี้)")
ok(r.status_code == 404, "  …และถึงตัว API จริง (ไม่พบลูกค้า = 404)")
r = browser(SELLER, csrf=True).post("/connect/api/claim", json.dumps({"id": 999999}),
                                    content_type="application/json", secure=True)
ok(r.status_code == 403, "POST ด้วยคุกกี้ไม่มี CSRF → ยังโดนบล็อกเหมือนเดิม")

print("\n[6] ระบบติดตามรถ (/track/) ผ่าน token")
from cars.models import Car  # noqa: E402
Car.objects.create(code="CSDEMO1", plate="1กก1234", brand="Toyota", model="Yaris")
ADM_TOK = full_login(ADMIN)
ok(bool(ADM_TOK), "แอดมินระบบ login จากแอปได้")
r = Client().get("/track/api/m/car/CSDEMO1", secure=True, HTTP_AUTHORIZATION="Bearer " + ADM_TOK)
d = r.json() if r.status_code == 200 else {}
ok(r.status_code == 200 and d.get("code") == "CSDEMO1", "เปิดรถด้วย token ได้ (ผูก login ระบบรถให้เอง)")
ok(d.get("direct") and isinstance(d.get("rules", {}).get("forceMedia"), list),
   "ได้ปุ่มเปลี่ยนสเตป + กติกาแนบรูป/หมายเหตุ")
r = Client().get("/track/api/m/car/NOPE", secure=True, HTTP_AUTHORIZATION="Bearer " + ADM_TOK)
ok(r.status_code == 404 and not r.json()["ok"], "รหัสรถไม่มีในระบบ → 404 JSON (ไม่ใช่หน้า HTML)")
ok(Client().get("/track/api/m/car/CSDEMO1", secure=True).status_code in (302, 401),
   "ไม่มี token → เข้าไม่ได้")
stage = d["direct"][0]["key"]
r = Client().post("/track/api/set_stage", json.dumps({"code": "CSDEMO1", "stage": stage}),
                  content_type="application/json", secure=True, HTTP_AUTHORIZATION="Bearer " + ADM_TOK)
ok(r.status_code in (200, 400), "เปลี่ยนสเตปผ่าน API เดิมได้ (400 = ติดกติกาแนบรูป/หมายเหตุ ซึ่งถูกต้อง)")
if r.status_code == 400:
    ok("แนบรูป" in r.json().get("error", "") or "หมายเหตุ" in r.json().get("error", ""),
       "  …ข้อความบอกว่าต้องแนบรูป/หมายเหตุ")

print("\n[7] ออกจากระบบ · พนักงานลาออก")
r = Client().post("/api/m/logout", secure=True, **H)
ok(r.status_code == 200, "ออกจากระบบ")
ok(Client().get("/api/m/me", secure=True, **H).status_code == 401, "token ที่ออกจากระบบแล้วใช้ไม่ได้")
T2 = full_login(SELLER)
ok(Client().get("/api/m/me", secure=True, HTTP_AUTHORIZATION="Bearer " + T2).status_code == 200,
   "login ใหม่ได้ token ใหม่")
Employee.objects.filter(nickname="มัท").update(active=False)
ok(Client().get("/api/m/me", secure=True, HTTP_AUTHORIZATION="Bearer " + T2).status_code == 401,
   "ปิดใช้งานพนักงานในทะเบียน → token ใช้ไม่ได้ทันที")
MobileToken.objects.filter(nickname="admin").update(expires_at=timezone.now() - timedelta(seconds=1))
ok(Client().get("/api/m/me", secure=True, HTTP_AUTHORIZATION="Bearer " + ADM_TOK).status_code == 401,
   "token หมดอายุ → ใช้ไม่ได้")

print("\n[8] LINE Login ตัวเดิมพาเซลล์กลับมาที่ /m/ ได้")
_orig = google_sheets.fetch_sheet


def _fake_sheet(key, *a, **k):
    if key == "employees":
        row = [""] * 8
        row[0], row[1], row[5], row[6] = "U" + "b" * 32, "เซลบิว", "บิว", "seller"
        return [["header"] * 8, row]
    return []


google_sheets.fetch_sheet = _fake_sheet
import dashboard.views as V  # noqa: E402
_vorig = V.fetch_sheet
V.fetch_sheet = _fake_sheet
try:
    from django.test import RequestFactory  # noqa: E402
    rq = RequestFactory().get("/")
    rq.session = SessionStore()
    target, err = V._login_with_line_user_id(rq, "U" + "b" * 32, "/m/handoff/abc")
    ok(err is None and target == "/m/handoff/abc", "เซลล์ login ผ่าน LINE แล้วกลับไป /m/handoff (ไม่โดนพาไป /me/)")
    target, err = V._login_with_line_user_id(rq, "U" + "b" * 32, "/dashboard/")
    ok(target == "/me/", "  …ทางอื่นของเซลล์ยังไป /me/ เหมือนเดิม")
finally:
    google_sheets.fetch_sheet = _orig
    V.fetch_sheet = _vorig

print("\n[9] คนงาน (ช่าง/ฝ่ายทะเบียน) login ด้วยชื่อผู้ใช้+รหัส → สแกน QR จากแอป")
from django.contrib.auth.models import User  # noqa: E402
from cars import roles as R  # noqa: E402
w = User.objects.create_user("chang1", password="pass-1234", first_name="ช่างหนึ่ง")
R.set_user_role(w, R.TECH)
v, ch = pkce()
b = browser()
r = b.get("/m/login", {"r": DEV, "c": ch, "via": "pw"}, secure=True)
ok(r.status_code == 302 and r["Location"].startswith("/login/?next=/m/handoff/"),
   "via=pw → หน้า login ของเว็บ (มีช่องชื่อผู้ใช้+รหัส) แล้วกลับมา /m/handoff")
nxt = r["Location"].split("next=")[1]
r = b.post("/login/", {"username": "chang1", "password": "pass-1234", "next": nxt}, secure=True)
ok(r.status_code == 302 and r["Location"] == nxt, "login รหัสผ่านสำเร็จ → กลับไป /m/handoff (ไม่โดนพาไป /dashboard/)")
r = b.get(nxt, secure=True)
code = re.search(r"code=([^&]+)", r.get("Location", "")).group(1)
WT = Client().post("/api/m/token", json.dumps({"code": code, "verifier": v}),
                   content_type="application/json", secure=True).json().get("token")
ok(bool(WT), "คนงานได้ token")
WH = {"HTTP_AUTHORIZATION": "Bearer " + WT}
r = Client().get("/track/api/m/car/CSDEMO1", secure=True, **WH)
ok(r.status_code == 200 and r.json().get("role") == R.TECH,
   "เปิดรถด้วยบัญชีเดิมของช่าง (ได้บทบาทช่าง)" + ("" if r.status_code == 200 else " [%s]" % r.status_code))
ok(not User.objects.filter(username="line_django_chang1").exists(),
   "  …ไม่สร้างบัญชีใหม่ที่ไม่มีบทบาท (line_django_chang1)")
r = Client().get("/connect/api/inbox", secure=True, **WH)
ok(r.status_code == 403, "คนงานเปิด Connect ไม่ได้ (แชทลูกค้าเฉพาะเซลล์/แอดมิน)")
wd = Client().get("/track/api/m/car/CSDEMO1", secure=True, **WH).json()
import tempfile  # noqa: E402
from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402
from django.test import override_settings  # noqa: E402
from cars import gdrive as _gd  # noqa: E402
_gd_orig = _gd.is_configured
_gd.is_configured = lambda: False      # เครื่องทดสอบไม่ยิง Google Drive จริง → เก็บดิสก์ (ทางเดียวกับตอนยังไม่ตั้ง Drive)
with tempfile.TemporaryDirectory() as tmp, override_settings(
        MEDIA_ROOT=tmp, STORAGES={**settings.STORAGES,
                                  "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}}):
    up = Client().post("/track/api/upload", {"code": "CSDEMO1",
                                             "file": SimpleUploadedFile("a.jpg", b"\xff\xd8\xff" + b"0" * 64, "image/jpeg")},
                       secure=True, **WH)
    uj = up.json() if up.status_code == 200 else {}
    ok(up.status_code == 200 and uj.get("id"), "อัปรูปจากแอป (multipart + token) ได้" + ("" if up.status_code == 200 else " [%s %s]" % (up.status_code, up.content[:200])))
    st = wd["direct"][0]["key"] if wd.get("direct") else ""
    r = Client().post("/track/api/seller_set_stage",
                      json.dumps({"code": "CSDEMO1", "stage": st, "note": "ทดสอบจากแอป",
                                  "media": [{"id": uj.get("id"), "video": False}]}),
                      content_type="application/json", secure=True, **WH)
    ok(bool(st) and r.status_code == 200 and r.json().get("ok"),
       "ช่างเปลี่ยนสเตปจากแอป (แนบรูป+หมายเหตุ) สำเร็จ" + ("" if r.status_code == 200 else " [%s %s]" % (r.status_code, r.content[:120])))
    car = Car.objects.get(code="CSDEMO1")
    lg = car.logs.first()
    ok(car.stage == st and lg and lg.worker_name and lg.media, "  …บันทึกสเตป + ชื่อคนทำ + รูปลงประวัติรถ")
_gd.is_configured = _gd_orig
r = b.post("/login/", {"username": "chang1", "password": "pass-1234", "next": "https://evil.example/"}, secure=True)
ok(r.status_code == 302 and r["Location"] == "/dashboard/", "next ที่ไม่อนุญาต → ยังไป /dashboard/ เหมือนเดิม")
User.objects.filter(pk=w.pk).update(is_active=False)
ok(Client().get("/track/api/m/car/CSDEMO1", secure=True, **WH).status_code == 401,
   "ปิดบัญชีที่ /track/users/ → token ของคนงานใช้ไม่ได้ทันที")

_runner.teardown_databases(_old)
print("\nผล: ผ่าน %d · ไม่ผ่าน %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
