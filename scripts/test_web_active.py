# -*- coding: utf-8 -*-
"""ตรวจปุ่ม Active (13 ต.ค.69) — รถขึ้นเว็บโชว์รูม Oxlet เมื่อกด Active + ถึงสเตปพร้อมขาย/จอง

    python scripts/test_web_active.py

ฐานข้อมูลทดสอบ (SQLite ชั่วคราว) + test client จริงทั้งสาย middleware/สิทธิ์ ·
ปลอมแค่ "เว็บโชว์รูมฝั่งโน้น" ที่ขอบระบบ (requests.post) ตามบทเรียนเดิม — ตัวปลอมทำตามสัญญา
ของ api_stock_update (สร้าง/ซ่อน/รอ/ขายแล้ว + ตอบ listed) · ตรวจว่า:
  - กดได้เฉพาะผู้บริหาร/แอดมิน (เซลล์/ฝ่ายทะเบียน 403 · ไม่ login = ไปหน้า login)
  - กด Active ตอนยังไม่ถึงพร้อมขาย = รอ · ถึงพร้อมขายเมื่อไหร่ขึ้นเว็บเอง
  - รถที่ไม่ Active ถึงพร้อมขาย = ไม่ขึ้นเว็บ (พฤติกรรมเดิมที่ขึ้นเองถูกปิดแล้ว)
  - ปิด Active = ซ่อน · ขายแล้ว = หาย
  - ส่งไม่สำเร็จ = บอกเหตุผล + ป้ายแดง + ส่งซ้ำได้ (ไม่เงียบ)
  - migration นับรถที่ขึ้นเว็บอยู่แล้วเป็น Active (เจ้าของเลือก "โชว์ต่อ")
"""
import importlib
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
os.environ["DB_HOST"] = ""
os.environ.setdefault("DEBUG", "True")

import django

django.setup()

from django.conf import settings
from django.test.runner import DiscoverRunner
from django.test.utils import setup_test_environment

setup_test_environment()
runner = DiscoverRunner(verbosity=0, interactive=False)
old_cfg = runner.setup_databases()
if "testserver" not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]

import requests
from django.apps import apps as django_apps
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client
from django.utils import timezone

from cars import roles, showroom_sync
from cars.models import Car

showroom_sync.BG = False
settings.SHOWROOM_WEBHOOK_URL = "https://showroom.example/api/stock-update/"
settings.STOCK_SYNC_SECRET = "s3cret"
settings.SHOWROOM_PUBLIC_URL = ""

fail = []


def eq(got, want, what):
    if got == want:
        print("  ok   %s" % what)
    else:
        fail.append(what)
        print("  FAIL %s → ได้ %r ควรได้ %r" % (what, got, want))


# ── เว็บโชว์รูมปลอม (ทำตามสัญญา api_stock_update) ─────────────────────────────
SHOW = {}          # code → {"listed": bool, "status": str}
CALLS = []
MODE = {"fail": None}


class _Resp:
    def __init__(self, code, body):
        self.status_code = code
        self._b = body

    def json(self):
        if isinstance(self._b, Exception):
            raise self._b
        return self._b


def fake_post(url, json=None, headers=None, timeout=None):
    CALLS.append({"url": url, "json": json, "headers": headers})
    if MODE["fail"] == "conn":
        raise requests.ConnectionError("down")
    if MODE["fail"] == "401":
        return _Resp(401, {"ok": False, "error": "unauthorized"})
    if MODE["fail"] == "html":
        return _Resp(502, ValueError("not json"))
    p = json or {}
    code, stage, active = p["code"], p.get("stage"), p.get("active", True)
    v = SHOW.get(code)
    created = False
    if stage == "sold" or p.get("status") == "sold":
        if v:
            v["status"] = "sold"
        return _Resp(200, {"ok": True, "action": "sold", "listed": False, "created": False})
    if not active:
        if v and v["listed"]:
            v["listed"] = False
            action = "hidden"
        else:
            action = "inactive"
    elif stage in ("show", "reserve"):
        st = "available" if stage == "show" else "reserved"
        if not v:
            v = SHOW[code] = {"listed": True, "status": st}
            created = True
        v.update(listed=True, status=st)
        action = st
    else:
        if v:
            v["listed"] = True
            action = "shown"
        else:
            action = "waiting"
    listed = bool(v and v["listed"] and v["status"] != "sold")
    return _Resp(200, {"ok": True, "action": action, "created": created, "listed": listed,
                       "path": "/listings/x/" if listed else ""})


showroom_sync.requests.post = fake_post


def user(name, role=None, superuser=False):
    u = User.objects.create_user(name, password="x", is_superuser=superuser)
    if role:
        roles.set_user_role(u, role)
    c = Client()
    c.force_login(u)
    return c


ex = user("boss", superuser=True)
adm = user("admintrk", roles.ADMIN)
sales = user("sale1", roles.SALES)
regist = user("reg1", roles.REGIST)
anon = Client()


def toggle(c, code, on):
    r = c.post("/track/api/web_active", data=json.dumps({"code": code, "active": on}),
               content_type="application/json", secure=True)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {}


def new_car(**kw):
    c = Car(branch="CB", brand="Toyota", model="Yaris", year=2022, plate=kw.pop("plate", "1กก1234"), **kw)
    c.save()
    return c


def fresh(c):
    c.refresh_from_db()
    return c


print("[1] สิทธิ์ — ผู้บริหาร/แอดมินเท่านั้น")
car = new_car()
eq(toggle(sales, car.code, True)[0], 403, "เซลล์กดไม่ได้ (403)")
eq(toggle(regist, car.code, True)[0], 403, "ฝ่ายทะเบียนกดไม่ได้ (403)")
eq(toggle(anon, car.code, True)[0] in (302, 401, 403), True, "ไม่ login กดไม่ได้")
eq(fresh(car).web_active, False, "ยังไม่ Active")
eq(len(CALLS), 0, "ไม่มีคำขอไปเว็บเลย")
st, j = toggle(adm, car.code, True)
eq((st, j.get("ok")), (200, True), "แอดมินกดได้")
toggle(adm, car.code, False)
CALLS.clear()

print("[2] กด Active ตอนรถยังทำสภาพ → รอ · ถึงพร้อมขายแล้วขึ้นเอง")
st, j = toggle(ex, car.code, True)
eq((st, j.get("pushed"), j["web"]["state"]), (200, True, "wait"), "ตอบว่ารอ")
eq("ถึงสเตปพร้อมขาย" in j.get("message", ""), True, "บอกผู้ใช้ว่าจะขึ้นเมื่อถึงพร้อมขาย")
eq((CALLS[-1]["json"]["active"], CALLS[-1]["json"]["stage"]), (True, "intake"), "ส่ง active=true + สเตปจริง")
eq(CALLS[-1]["headers"].get("X-Stock-Secret"), "s3cret", "แนบรหัสลับ")
c2 = fresh(car)
eq((c2.web_active, c2.web_listed, c2.web_active_by), (True, False, "boss"), "บันทึกผู้กด · ยังไม่ขึ้นเว็บ")
eq(car.code in SHOW, False, "เว็บยังไม่มีประกาศ")
c2.change_stage("show", worker_name="test")
c2 = fresh(car)
eq((SHOW.get(car.code) or {}).get("listed"), True, "ถึงพร้อมขาย → เว็บสร้างประกาศ")
eq((c2.web_listed, c2.web_state["key"]), (True, "live"), "บันทึกว่าขึ้นเว็บอยู่ (ป้ายเขียว)")

print("[3] รถที่ไม่ Active ถึงพร้อมขาย → ไม่ขึ้นเว็บ")
car3 = new_car(plate="2ขข2222")
car3.change_stage("show", worker_name="test")
eq(CALLS[-1]["json"]["active"], False, "ส่ง active=false")
eq(car3.code in SHOW, False, "เว็บไม่สร้างประกาศ (เดิมขึ้นเองทันที)")
eq(fresh(car3).web_state, None, "ไม่มีป้ายบนการ์ด")
st, j = toggle(ex, car3.code, True)
eq((j["web"]["state"], (SHOW.get(car3.code) or {}).get("listed")), ("live", True), "กด Active ตอนพร้อมขาย → ขึ้นทันที")
eq("สร้างประกาศใหม่" in j.get("message", ""), True, "บอกว่าสร้างประกาศใหม่")
eq("ยังไม่มีราคาขาย" in j.get("message", ""), True, "รถไม่มีราคา → บอกให้ไปใส่ราคาที่หน้าแก้ไขรถ")

print("[4] ปิด Active → ซ่อน · เปิดกลับ → กลับมา")
st, j = toggle(ex, car3.code, False)
eq((j["web"]["active"], j["web"]["state"], SHOW[car3.code]["listed"]), (False, "", False), "ซ่อนจากเว็บ")
eq("ซ่อนจากเว็บ" in j.get("message", ""), True, "บอกว่าซ่อนแล้ว")
eq(fresh(car3).web_listed, False, "บันทึกว่าไม่อยู่บนเว็บ")
st, j = toggle(ex, car3.code, True)
eq(SHOW[car3.code]["listed"], True, "เปิดกลับมาได้")

print("[5] จอง → ขายแล้ว")
car3 = fresh(car3)
car3.change_stage("reserve", worker_name="test")
eq(SHOW[car3.code]["status"], "reserved", "จอง → จองแล้วบนเว็บ")
car3.change_stage("sold", worker_name="test")
c3 = fresh(car3)
eq((SHOW[car3.code]["status"], c3.web_listed, c3.web_state), ("sold", False, None), "ขายแล้ว → หายจากเว็บ ไม่มีป้าย")
st, j = toggle(ex, car3.code, True)
eq(st, 400, "กด Active รถที่ขายแล้วไม่ได้")

print("[6] ส่งไม่สำเร็จ ต้องไม่เงียบ")
car6 = new_car(plate="6ฉฉ6666")
car6.change_stage("show", worker_name="test")
MODE["fail"] = "conn"
st, j = toggle(ex, car6.code, True)
eq((st, j.get("ok"), j.get("pushed")), (200, True, False), "บันทึก Active ได้ แต่บอกว่าส่งไม่สำเร็จ")
eq("ส่งไปเว็บไม่สำเร็จ" in j.get("message", ""), True, "ข้อความบอกผู้ใช้")
c6 = fresh(car6)
eq((c6.web_active, c6.web_state["key"], bool(c6.web_sync_error)), (True, "error", True), "ป้ายแดง + เก็บสาเหตุ")
MODE["fail"] = "401"
st, j = toggle(ex, car6.code, True)
eq("รหัสลับไม่ตรง" in fresh(car6).web_sync_error, True, "401 → บอกว่ารหัสลับไม่ตรง")
MODE["fail"] = "html"
toggle(ex, car6.code, True)
eq("HTTP 502" in fresh(car6).web_sync_error, True, "เว็บล่ม (HTML) → บอก HTTP")
MODE["fail"] = None
st, j = toggle(ex, car6.code, True)
c6 = fresh(car6)
eq((c6.web_sync_error, c6.web_state["key"]), ("", "live"), "ส่งซ้ำสำเร็จ → ป้ายเขียว ล้างข้อผิดพลาด")

print("[7] ยังไม่ได้ตั้งค่าเชื่อมเว็บ")
settings.SHOWROOM_WEBHOOK_URL = ""
car7 = new_car(plate="7ชช7777")
n0 = len(CALLS)
st, j = toggle(ex, car7.code, True)
eq((st, fresh(car7).web_active, len(CALLS) == n0), (200, True, True), "บันทึกได้ ไม่ยิงอะไรออก")
eq("ยังไม่ได้เชื่อมเว็บโชว์รูม" in j.get("message", ""), True, "บอกว่ายังไม่ได้ตั้งค่า")
eq(fresh(car7).web_sync_error, "", "ไม่บันทึกเป็นข้อผิดพลาด (ไม่ใช่ปัญหาเครือข่าย)")
settings.SHOWROOM_WEBHOOK_URL = "https://showroom.example/api/stock-update/"

print("[8] ข้อมูลเพี้ยน")
r = ex.post("/track/api/web_active", data=json.dumps({"code": car7.code, "active": "yes"}),
            content_type="application/json", secure=True)
eq(r.status_code, 400, "active ไม่ใช่ true/false = 400")
r = ex.post("/track/api/web_active", data=json.dumps({"code": "NOPE", "active": True}),
            content_type="application/json", secure=True)
eq(r.status_code, 404, "ไม่มีรถคันนี้ = 404")

print("[9] ป๊อปอัปรถ + บอร์ด")
j = ex.get("/track/cars/%s/json" % car.code, secure=True).json()
eq((j["web"]["can"], j["web"]["state"], j["web"]["url"]), (True, "live", "https://showroom.example/stock/%s/" % car.code),
   "ผู้บริหาร: กดได้ · ขึ้นเว็บ · ลิงก์ดูบนเว็บ")
j = sales.get("/track/cars/%s/json" % car.code, secure=True).json()
eq((j["web"]["can"], j["web"]["state"]), (False, "live"), "เซลล์: เห็นสถานะ กดไม่ได้")
settings.SHOWROOM_PUBLIC_URL = "https://www.oxlet.example"
settings.SHOWROOM_WEBHOOK_URL = "http://127.0.0.1:8001/api/stock-update/"
eq(showroom_sync.web_url(fresh(car)), "https://www.oxlet.example/stock/%s/" % car.code, "ลิงก์ใช้ SHOWROOM_PUBLIC_URL")
settings.SHOWROOM_PUBLIC_URL = ""
eq(showroom_sync.web_url(fresh(car)), "", "webhook ทาง 127.0.0.1 + ไม่ตั้งโดเมน = ไม่มีลิงก์ (ดีกว่าลิงก์เสีย)")
settings.SHOWROOM_WEBHOOK_URL = "https://showroom.example/api/stock-update/"
html = ex.get("/track/", secure=True).content.decode()
eq('class="webb" data-code="%s"' % car.code in html, True, "การ์ดในบอร์ดมีช่องป้ายลูกโลก")
eq("แสดงบนเว็บ Oxlet อยู่" in html, True, "ป้ายบนการ์ดบอกว่าขึ้นเว็บ")

print("[10] migration — รถที่ขึ้นเว็บอยู่แล้วนับเป็น Active")
mig = importlib.import_module("cars.migrations.0019_car_web_active")
Car.objects.update(web_active=False, web_active_by="")
a = new_car(plate="1ก1"); a.change_stage("show", worker_name="t")
b = new_car(plate="1ก2"); b.change_stage("reserve", worker_name="t")
c = new_car(plate="1ก3"); Car.objects.filter(pk=c.pk).update(stage="finance", frontline_at=timezone.now())
d = new_car(plate="1ก4")
e = new_car(plate="1ก5"); e.change_stage("show", worker_name="t"); Car.objects.filter(pk=e.pk).update(status="hold")
f = new_car(plate="1ก6"); f.change_stage("sold", worker_name="t")
Car.objects.update(web_active=False, web_active_by="")
mig.mark_existing(django_apps, None)
got = {x.plate: x.web_active for x in Car.objects.filter(pk__in=[a.pk, b.pk, c.pk, d.pk, e.pk, f.pk])}
eq(got, {"1ก1": True, "1ก2": True, "1ก3": True, "1ก4": False, "1ก5": False, "1ก6": False},
   "พร้อมขาย/จอง/เคยถึงพร้อมขาย = Active · ยังทำสภาพ/พัก/ขายแล้ว = ไม่")
mig.unmark(django_apps, None)
eq(Car.objects.filter(web_active=True).exists(), False, "ย้อน migration ได้")

print("[11] คำสั่ง showroom_push")
SHOW.clear()
Car.objects.filter(pk__in=[a.pk, b.pk]).update(web_active=True, web_listed=False)
n0 = len(CALLS)
call_command("showroom_push", stdout=io.StringIO())
eq(len(CALLS), n0, "ไม่ใส่ --apply = ไม่ยิง")
out = io.StringIO()
call_command("showroom_push", "--apply", stdout=out)
eq((fresh(a).web_listed, fresh(b).web_listed), (True, True), "--apply → ส่ง + บันทึกว่าขึ้นเว็บ")
eq("ขึ้นเว็บอยู่ 2" in out.getvalue(), True, "สรุปจำนวน")

print("[12] ราคาขายส่งไปเว็บด้วย")
p = new_car(plate="9ญญ9999", price=459000)
eq(showroom_sync.sale_price(p), 459000, "ช่องราคาขายที่กรอกเอง")
p2 = new_car(plate="9ญญ9998", extra={"price_num": "389,000"})
eq(showroom_sync.sale_price(p2), 389000, "ไม่มีราคาที่กรอก → ใช้ราคานำเข้า Car Spend (ตัดจุลภาค)")
p3 = new_car(plate="9ญญ9997", price=525000, extra={"price_num": 1})
eq(showroom_sync.sale_price(p3), 525000, "ราคาที่กรอกเองชนะราคานำเข้า")
eq(showroom_sync.sale_price(new_car(plate="9ญญ9996")), None, "ไม่มีราคาเลย = None (เว็บคงราคาเดิม)")
eq(showroom_sync.sale_price(new_car(plate="9ญญ9995", extra={"price_num": "ติดต่อสอบถาม"})), None, "ราคาเพี้ยน = None")
p.change_stage("show", worker_name="t")
eq(CALLS[-1]["json"].get("price"), 459000, "เปลี่ยนสเตป → payload มีราคา")
st, j = toggle(ex, p.code, True)
eq(CALLS[-1]["json"].get("price"), 459000, "กด Active → payload มีราคา")
eq("ราคา 459,000 บาท" in j.get("message", ""), True, "ข้อความบอกราคาที่ขึ้นเว็บ")
p = fresh(p)
p.price = 445000
p.save()                                  # แก้ราคาในระบบ (เหมือนหน้าแก้ไขรถ) → post_save ส่งไปเว็บเอง
eq(CALLS[-1]["json"].get("price"), 445000, "แก้ราคาในระบบ → ส่งราคาใหม่ทันที")

print("[13] คอลัมน์ Active ในตารางรถ")
html = ex.get("/track/", secure=True).content.decode()
eq('<td class="wcell" data-code="%s"' % p.code in html, True, "ตารางมีคอลัมน์ Active")
_row = html.split('<td class="wcell" data-code="%s"' % p.code, 1)[1].split("</td>", 1)[0]
eq(("tblWebActive" in _row, "checked" in _row, "ขึ้นเว็บแล้ว" in _row), (True, True, True),
   "ผู้บริหาร: สวิตช์เปิดอยู่ + ป้ายขึ้นเว็บแล้ว")
_row2 = html.split('<td class="wcell" data-code="%s"' % d.code, 1)[1].split("</td>", 1)[0]
eq(("tblWebActive" in _row2, "checked" in _row2), (True, False), "รถไม่ Active: สวิตช์ปิด")
html_s = sales.get("/track/", secure=True).content.decode()
_rs = html_s.split('<td class="wcell" data-code="%s"' % p.code, 1)[1].split("</td>", 1)[0]
eq(("tblWebActive" in _rs, "ขึ้นเว็บแล้ว" in _rs), (False, True), "เซลล์: ไม่มีสวิตช์ เห็นแค่สถานะ")
html_sold = ex.get("/track/?view=sold", secure=True).content.decode()
if '<td class="wcell" data-code="%s"' % f.code in html_sold:
    _rf = html_sold.split('<td class="wcell" data-code="%s"' % f.code, 1)[1].split("</td>", 1)[0]
    eq(("disabled" in _rf, "checked" in _rf), (True, False), "รถขายแล้ว: สวิตช์กดไม่ได้")
else:
    eq(True, True, "รถขายแล้วไม่อยู่ในตารางหลัก (ข้าม)")

runner.teardown_databases(old_cfg)
print()
print("ผ่านทั้งหมด" if not fail else "ไม่ผ่าน %d ข้อ: %s" % (len(fail), ", ".join(fail)))
sys.exit(1 if fail else 0)
