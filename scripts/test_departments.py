# -*- coding: utf-8 -*-
"""เทสต์ "แผนก + ตำแหน่ง" ในทะเบียนพนักงาน (★ 18 ต.ค.69 · checkout/departments.py · migration 0042)

    python scripts/test_departments.py

ฐานข้อมูลทดสอบแยก · เรียก API ผ่าน test client จริง (session แอดมินแบบ signed-cookie)
· ปลอมแค่ชีตพนักงาน Google (ขอบระบบ) — ไม่ปลอมฟังก์ชันแผนก/สิทธิ์ของเราเอง
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

import importlib  # noqa: E402

from django.apps import apps as _apps  # noqa: E402
from django.contrib.auth.models import User  # noqa: E402
from django.contrib.sessions.backends.signed_cookies import SessionStore  # noqa: E402
from django.test import Client, RequestFactory  # noqa: E402

from cars import roles as R  # noqa: E402
from checkout import departments as D  # noqa: E402
from checkout.models import Employee, LineProfile  # noqa: E402
from dashboard.services import google_sheets  # noqa: E402
from dashboard.services.constants import team_id_of  # noqa: E402

PASS = FAIL = 0


def ok(cond, label, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓", label)
    else:
        FAIL += 1
        print("  ✗", label, extra)


def _no_sheet(*a, **k):
    raise RuntimeError("ไม่ต่อ Google ในเทสต์")


google_sheets.fetch_sheet = _no_sheet

LINE_A = "U" + "a" * 32
LINE_B = "U" + "b" * 32
LINE_C = "U" + "c" * 32
LINE_D = "U" + "d" * 32


def user_with(uid, role=None, superuser=False):
    u = User.objects.create(username="line_" + uid, is_superuser=superuser, is_staff=superuser)
    if role:
        R.set_user_role(u, role)
    return u


def emp(nick, position="", line=None, **kw):
    e = Employee.objects.create(nickname=nick, position=position, **kw)
    if line:
        LineProfile.objects.create(user_id=line, employee=e, nickname=nick, is_employee=True, channel="push")
    return e


print("[1] เดาแผนก — บทบาทระบบรถเดิมชนะตำแหน่ง · ออฟฟิศที่ไม่มีบทบาท = ไม่เดา")
ok(D.guess("ทีมโปรดักชัน", {"Sales"}) == "sales", "แซน: ตำแหน่งทีมโปรดักชัน แต่บทบาทระบบรถ = เซลล์ → เซลล์")
ok(D.guess("ออฟฟิศ บ้านเก่า", {"Registration"}) == "registration", "ออฟฟิศ + ฝ่ายทะเบียน → ฝ่ายทะเบียน")
ok(D.guess("ช่างและคนงาน", {"QC"}) == "qc", "ช่างและคนงาน + QC → QC")
ok(D.guess("ออฟฟิศ บ้านเก่า", set()) == "", "ออฟฟิศที่ไม่มีบทบาท = ไม่เดา (มีหลายแผนกปนกัน)")
ok(D.guess("ทีม B", set()) == "sales" and D.guess("เซลล์ทีม A", set()) == "sales", "ทีม B / เซลล์ทีม A → เซลล์")
ok(D.guess("เทเลเซลล์", {"Sales"}) == "telesale" and D.guess("เทเลเซลล์", set()) == "telesale", "เทเลเซลล์ (มี/ไม่มีบทบาท)")
ok(D.guess("จัดซื้อ", set()) == "purchasing" and D.guess("เด็กฝึกงาน", set()) == "production", "จัดซื้อ · เด็กฝึกงาน → โปรดักชัน")
ok(D.guess("ช่างและคนงาน", set()) == "technician", "ช่างและคนงาน (ไม่มีบทบาท) → ช่าง")
ok(D.guess("", set()) == "", "ไม่มีอะไรเลย = ว่าง")
ok(D.guess("ทีม B", {"Executive", "Sales"}) == "exec", "หลายบทบาท = เอาตามลำดับ ROLES (ผู้บริหารก่อน)")
mig = importlib.import_module("checkout.migrations.0042_employee_department")
same = all(mig._guess(p, g) == D.guess(p, g) for p, g in [
    ("ทีมโปรดักชัน", {"Sales"}), ("ออฟฟิศ บ้านเก่า", set()), ("ทีม C", set()), ("เซลล์ทีม A", set()),
    ("เทเลเซลล์", {"Sales"}), ("ช่างและคนงาน", {"CarWash"}), ("เด็กฝึกงาน", set()), ("อู่สีใน", set())])
ok(same, "ตรรกะเดาใน migration (แช่ไว้) ให้ผลเดียวกับ departments.guess")

print("[2] ตำแหน่ง \"เซลล์ทีม A\" ใช้กับทีมขายได้ (team_id_of)")
ok(team_id_of("เซลล์ทีม A") == "A" and team_id_of("เซลล์ ทีม B") == "B" and team_id_of("ทีม C") == "C", "เซลล์ทีม A/B · ทีม C")
ok(team_id_of("เซลล์") == "" and team_id_of("ทีมโปรดักชัน") == "" and team_id_of("เซลล์ทีมโปรดักชัน") == "", "เซลล์เฉยๆ / ทีมโปรดักชัน = ไม่ใช่ทีมขาย")
ok(team_id_of("เทเลเซลล์") == "ADMIN", "เทเลเซลล์ = ทีม ADMIN เหมือนเดิม")

print("[3] migration เติมแผนกแบบ \"ระบบเดา\" — ไม่แตะสิทธิ์ระบบรถของใคร")
san = emp("แซน", "ทีมโปรดักชัน", LINE_A)
user_with(LINE_A, R.SALES)
ofc = emp("เฟิร์น", "ออฟฟิศ บ้านเก่า", LINE_B)
user_with(LINE_B, R.REGIST)
nob = emp("บิว", "ทีม B", LINE_C)            # ยังไม่เคยเข้าระบบรถ (ไม่มีบัญชี Django)
mystery = emp("ใหม่", "ออฟฟิศ บ้านเก่า")      # เดาไม่ได้
done = emp("กวาง", "ออฟฟิศ บ้านเก่า", department="admin")   # มีแผนกแล้ว ไม่แตะ
mig.fill(_apps, None)
for e in (san, ofc, nob, mystery, done):
    e.refresh_from_db()
ok(san.department == "sales" and san.department_auto, "แซน = เซลล์ (เดา)")
ok(ofc.department == "registration" and ofc.department_auto, "เฟิร์น = ฝ่ายทะเบียน (จากบทบาทระบบรถ)")
ok(nob.department == "sales" and nob.department_auto, "บิว = เซลล์ (จากตำแหน่ง)")
ok(mystery.department == "" and not mystery.department_auto, "ออฟฟิศที่ไม่มีบทบาท = ว่างไว้")
ok(done.department == "admin" and not done.department_auto, "แถวที่มีแผนกอยู่แล้วไม่ถูกเดาทับ")
ok(D.sync_track_role(ofc) == [], "แผนกที่ระบบเดา = ไม่ตั้งสิทธิ์ระบบรถให้ใคร")
ok(D.track_role_for_line(LINE_C) == "", "บิว (เดา) — bridge ไม่บังคับบทบาท")

print("[4] หน้าพนักงาน (API) — เลือกแผนก/ยืนยัน = สิทธิ์ระบบรถเปลี่ยนตาม · แก้ช่องอื่นไม่ยืนยันแผนก")
c = Client()
st = SessionStore()
st["oxlet_user"] = {"user_id": "admin", "nickname": "", "position": "admin"}
st.save()
c.cookies[settings.SESSION_COOKIE_NAME] = st.session_key


def save(e, **kw):
    body = {"action": "save", "id": e.pk, "nickname": e.nickname, "displayName": e.display_name,
            "position": e.position, "workStart": e.work_start, "dayOff": e.day_off, "active": True,
            "trackCheckin": True}
    body.update(kw)
    r = c.post("/checkout/api/employees", json.dumps(body), content_type="application/json", secure=True)
    return r.status_code, json.loads(r.content)


g = json.loads(c.get("/checkout/api/employees", secure=True).content)
opts = {o["key"]: o for o in g.get("departments", [])}
ok(len(opts) == 11 and opts["sales"]["track"] == "เซลล์" and opts["purchasing"]["app"] == "จัดซื้อ",
   "ตัวเลือก 11 แผนก + บทบาทแอป/สิทธิ์ระบบรถของแต่ละแผนก")
row = next(x for x in g["employees"] if x["nickname"] == "เฟิร์น")
ok(row["department"] == "registration" and row["departmentAuto"] and row["trackRoles"] == ["ฝ่ายทะเบียน"],
   "แถวบอกแผนก · ระบบเดา · สิทธิ์ระบบรถตอนนี้", row)
ok(LINE_B not in c.get("/checkout/api/employees", secure=True).content.decode(), "ไม่มี LINE user id ในคำตอบ")
code, js = save(ofc, department="registration", note="ลาป่วย")
ofc.refresh_from_db()
ok(code == 200 and ofc.department_auto, "แก้หมายเหตุเฉยๆ = แผนกที่เดายังไม่ถูกยืนยัน")
code, js = save(ofc, department="qc")
ofc.refresh_from_db()
fern_u = User.objects.get(username="line_" + LINE_B)
ok(code == 200 and ofc.department == "qc" and not ofc.department_auto, "เลือกแผนกใหม่ = ยืนยันแล้ว")
ok(R.get_role(fern_u) == R.QC, "บัญชี LINE ที่ผูกได้สิทธิ์ระบบรถ = QC ทันที")
ok(js.get("synced") == [{"from": "ฝ่ายทะเบียน", "to": "QC"}], "บอกว่าสิทธิ์เปลี่ยนจากอะไรเป็นอะไร", js.get("synced"))
ok(LINE_B not in json.dumps(js, ensure_ascii=False), "คำตอบตอนบันทึกไม่มี LINE id (ไม่ส่งชื่อบัญชี)")
code, js = save(san, department="sales", confirmDept=True)
san.refresh_from_db()
ok(code == 200 and not san.department_auto and js.get("synced") == [], "กดยืนยันค่าที่เดาไว้ = ยืนยัน · สิทธิ์ตรงอยู่แล้วไม่เปลี่ยน")
code, js = save(san, department="ไม่มีแผนกนี้")
ok(code == 400 and "ไม่รู้จักแผนก" in js.get("error", ""), "แผนกมั่ว = 400 บอกเหตุผล")
boss = emp("บอส", "", LINE_D)
user_with(LINE_D, None, superuser=True)
code, js = save(boss, department="sales")
ok(code == 200 and User.objects.get(username="line_" + LINE_D).is_superuser and js.get("synced") == [],
   "superuser ไม่ถูกเปลี่ยนสิทธิ์ (ผู้บริหารเสมอ)")
r = c.post("/checkout/api/employees", json.dumps({"action": "save", "nickname": "น้องใหม่", "department": "carwash",
                                                  "active": True}), content_type="application/json", secure=True)
nn = Employee.objects.get(nickname="น้องใหม่")
ok(r.status_code == 200 and nn.department == "carwash" and not nn.department_auto, "เพิ่มคนใหม่พร้อมแผนก")
c2 = Client()
ok(c2.get("/checkout/api/employees", secure=True).status_code == 401, "ไม่ login = 401")

print("[5] login ครั้งแรก/ครั้งถัดไป (bridge) — บทบาทระบบรถตามแผนกที่ยืนยันแล้ว")
from dashboard.views import _bridge_line_to_django_user  # noqa: E402

rf = RequestFactory()


def bridge(uid, **kw):
    req = rf.get("/track/")
    req.session = SessionStore()
    return _bridge_line_to_django_user(req, uid, **kw)


NEW = "U" + "e" * 32
newbie = emp("หน่อง", "ช่างและคนงาน", NEW, department="technician")
u_new = bridge(NEW)
ok(R.get_role(u_new) == R.TECH, "คนใหม่ login ครั้งแรก = ได้บทบาทตามแผนก (ช่าง)")
R.set_user_role(u_new, R.SALES)               # มีคนไปแก้ที่ /track/users/ ตรงๆ
ok(R.get_role(bridge(NEW)) == R.TECH, "แก้บทบาทตรงๆ แล้ว login ใหม่ = กลับมาตามแผนก")
GUESS = "U" + "f" * 32
emp("เดา", "ทีม A", GUESS, department="sales", department_auto=True)
ok(R.get_role(bridge(GUESS)) is None, "แผนกที่ระบบเดา = ไม่แจกบทบาท (กันช่องโหว่แจก Sales ทุกคน)")
ADM = "U" + "9" * 32
emp("แอดมินเซล", "ทีม A", ADM, department="sales")
ok(R.get_role(bridge(ADM, make_exec=True)) == R.SALES, "แผนกที่ยืนยันแล้วชนะกติกา 'แอดมินฝั่งขายได้ผู้บริหาร'")
ok(bridge("Uzzzz", make_exec=True) and R.get_role(User.objects.get(username="line_Uzzzz")) == R.EXEC,
   "ไม่มีในทะเบียน = กติกาเดิม (แอดมินครั้งแรก = ผู้บริหาร)")

print("[6] บทบาทในแอป (role_of) ตามแผนก")
from dashboard.services.mobile_home import role_of  # noqa: E402

ok(role_of({"user_id": NEW, "nickname": "หน่อง", "position": "ช่างและคนงาน"}) == "worker", "ช่าง → คนงาน")
ok(role_of({"user_id": LINE_B, "nickname": "เฟิร์น", "position": "ออฟฟิศ บ้านเก่า"}) == "worker",
   "ฝ่ายทะเบียน/QC ที่เคยตกเป็น 'เซลล์' → คนงาน")
emp("หมี", "จัดซื้อ", department="purchasing")
ok(role_of({"user_id": "x", "nickname": "หมี", "position": ""}) == "buyer", "จัดซื้อ → จัดซื้อ")
ok(role_of({"user_id": LINE_A, "nickname": "แซน", "position": "ทีมโปรดักชัน"}) == "seller", "เซลล์ → เซลล์")
emp("ผบ", "", department="exec")
ok(role_of({"user_id": "y", "nickname": "ผบ", "position": "ออฟฟิศ"}) == "worker",
   "แผนกผู้บริหารแต่ไม่ได้ login เป็นแอดมิน = คนงาน (แผนกไม่ยกสิทธิ์ดูข้อมูลขาย)")
ok(role_of({"user_id": "y", "nickname": "ผบ", "position": "admin"}) == "admin", "login เป็นแอดมิน = แอดมินเสมอ")
ok(role_of({"user_id": "z", "nickname": "ไม่มีในทะเบียน", "position": "ทีม A"}) == "seller", "ไม่มีแผนก = กติกาเดิม")

print("[7] จัดซื้อ (is_purchaser) — แผนกที่ยืนยันแล้วชนะรายชื่อเดิม")
from dashboard.services import purchase_page  # noqa: E402

ok(purchase_page.is_purchaser("หมี", ""), "แผนกจัดซื้อ = จัดซื้อ")
Employee.objects.filter(nickname="หมี").update(department="sales")
ok(not purchase_page.is_purchaser("หมี", ""), "ยืนยันแผนกอื่นแล้ว = ไม่ใช่จัดซื้อ (แม้ชื่ออยู่ในรายชื่อเดิม)")
Employee.objects.filter(nickname="หมี").update(department="sales", department_auto=True)
ok(purchase_page.is_purchaser("หมี", ""), "แผนกที่ระบบเดา = ไม่ทับรายชื่อเดิม")
ok(purchase_page.is_purchaser("ต๊าด", ""), "ไม่มีในทะเบียน = รายชื่อเดิม")

print("[8] หน้าผู้ใช้ระบบรถ (/track/users/) — ล็อกบัญชีที่ตั้งตามแผนก")
mgr = User.objects.create(username="mgr", is_superuser=True, is_staff=True)
c3 = Client()
c3.force_login(mgr)
r = c3.get("/track/users/", secure=True)
ok(r.status_code == 200 and "ตามแผนก: QC (เฟิร์น)" in r.content.decode(), "บอกว่าบัญชีนี้ตั้งตามแผนก")
r = c3.post("/track/users/", {"action": "set_role", "user_id": fern_u.pk, "role": R.SALES}, secure=True, follow=True)
fern_u.refresh_from_db()
ok(R.get_role(fern_u) == R.QC and "เปลี่ยนแผนกที่หน้า" in r.content.decode(), "เปลี่ยนตรงๆ ไม่ได้ + บอกให้ไปแก้ที่แผนก")

print("[9] คิวรถของคนงานในแอป — คนที่เข้าด้วย LINE อ่านบทบาทจากบัญชีของเขาเอง")
from dashboard.services import mobile_home  # noqa: E402

req = rf.get("/api/m/home")
from django.contrib.auth.models import AnonymousUser  # noqa: E402

req.user = AnonymousUser()
q = mobile_home._team_queue(req, {"user_id": LINE_B})
ok(q.get("role") == R.QC, "เฟิร์น (LINE) = คิวของ QC", q.get("role"))
q2 = mobile_home._team_queue(req, {"user_id": "U" + "7" * 32})
ok(q2.get("role") == "" and "แผนก" in q2.get("note", ""), "ไม่มีบทบาท = บอกให้ตั้งแผนก")

_runner.teardown_databases(_old)
print()
print("ผ่าน %d · ไม่ผ่าน %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
