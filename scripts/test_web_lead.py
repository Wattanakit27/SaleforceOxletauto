# -*- coding: utf-8 -*-
"""ตรวจลีดจากฟอร์มเว็บโชว์รูม → กลุ่ม ADMIN เก็บ Lead + ห้องพัก Lead (13 ต.ค.69)

    python scripts/test_web_lead.py

SQLite ชั่วคราว + test client จริง · ปลอมแค่ LINE ที่ขอบระบบ (requests.post) · ตรวจว่า:
  - ไม่ตั้ง secret = 503 · secret ผิด = 401 · ไม่มีชื่อ/เบอร์ = 422 · ไม่พบกลุ่มพักลีด = 503
  - โพสต์ "ใบร่าง" (ยังไม่มีเลขรัน · ช่องทาง web oxlet) เข้ากลุ่ม ADMIN เก็บ Lead ด้วยบอทตัวส่ง
  - ใบร่างขึ้นในห้องพัก Lead (leadpark.board) พร้อมชื่อ/เบอร์/รถ — จ่ายเบอร์ต่อได้ตามขั้นตอนเดิม
  - เว็บโชว์รูมส่งซ้ำ = ไม่โพสต์ซ้ำ · LINE ล่ม = ลีดยังเข้าห้องพัก Lead (บอกว่าโพสต์ไม่สำเร็จ)
  - ห้องจ่ายเบอร์/ห้องของบอทเดิม ไม่ถูกเลือกเป็นปลายทาง
"""
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
from django.test import Client
from django.utils import timezone

from checkout import leadpark
from checkout.leadgroup import parse_leadsheet
from checkout.models import GroupChat
from dashboard.services import cache_store

settings.LINE_CHANNEL_ACCESS_TOKEN = "tok-crm"
settings.LINE_PUSH_CHANNEL_ACCESS_TOKEN = "tok-push"

fail = []


def eq(got, want, what):
    if got == want:
        print("  ok   %s" % what)
    else:
        fail.append(what)
        print("  FAIL %s → ได้ %r ควรได้ %r" % (what, got, want))


# ── LINE ปลอม (ขอบระบบ) ─────────────────────────────────────────────
SENT = []
MODE = {"code": 200}


class _R:
    def __init__(self, code, body):
        self.status_code, self.text = code, json.dumps(body)

    def json(self):
        return json.loads(self.text)


def fake_post(url, *a, **kw):
    body = kw.get("json") or json.loads(kw.get("data") or "{}")
    SENT.append({"url": url, "to": body.get("to"), "auth": (kw.get("headers") or {}).get("Authorization"),
                 "text": ((body.get("messages") or [{}])[0]).get("text", "")})
    if MODE["code"] == 200:
        return _R(200, {"sentMessages": [{"id": "LMID%d" % len(SENT)}]})
    return _R(MODE["code"], {"message": "The bot is not in the group"})


requests.post = fake_post
c = Client()
URL = "/api/showroom/lead"
LEAD = {"lead_id": 7, "name": "สมชาย ใจดี", "phone": "081-234-5678", "email": "a@b.co",
        "message": "ขอผ่อนเดือนละ 8 พัน", "source_page": "car_detail",
        "car": {"title": "TOYOTA Hilux Revo 2018", "code": "CS03560", "plate": "5กน1573", "price": 429000,
                "url": "http://76.13.214.140:8080/listings/toyota-hilux-revo-2018/"}}


def post(d, secret="s3cret"):
    h = {"HTTP_X_STOCK_SECRET": secret} if secret is not None else {}
    r = c.post(URL, data=json.dumps(d), content_type="application/json", secure=True, **h)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {}


print("[1] ด่านรหัสลับ")
settings.STOCK_SYNC_SECRET = ""
eq(post(LEAD)[0], 503, "ยังไม่ตั้ง secret = 503")
settings.STOCK_SYNC_SECRET = "s3cret"
eq(post(LEAD, secret="ผิด")[0], 401, "secret ผิด = 401")
eq(post(LEAD, secret=None)[0], 401, "ไม่ส่ง secret = 401")
eq(post({"lead_id": 1, "email": "x@y.z"})[0], 422, "ไม่มีชื่อ/เบอร์ = 422")
eq(len(SENT), 0, "ยังไม่ยิง LINE เลย")

print("[2] ไม่มีกลุ่มพักลีดที่บอทตัวส่งอยู่")
cache_store.set_kv("line_groups", {
    "Cold": {"name": "ADMIN เก็บ Lead", "channels": ["crm"], "lastSeen": "2026-10-01T00:00:00"},   # บอทเดิม
    "Cpay": {"name": "ห้องจ่ายเบอร์ บ้านเก่า", "channels": ["push"], "lastSeen": "2026-10-13T00:00:00"},
})
st, j = post(LEAD)
eq(st, 503, "ไม่พบกลุ่ม = 503")
eq(len(SENT), 0, "ไม่ยิงเข้าห้องจ่ายเบอร์/ห้องของบอทเดิม")

print("[3] ส่งเข้ากลุ่ม ADMIN เก็บ Lead")
groups = cache_store.get_kv("line_groups")["data"]
groups["Cpark"] = {"name": "ADMIN เก็บ Lead", "channels": ["push"], "lastSeen": "2026-10-13T08:00:00"}
cache_store.set_kv("line_groups", groups)
st, j = post(LEAD)
eq((st, j.get("ok"), j.get("pushed")), (200, True, True), "ตอบ ok + โพสต์ LINE แล้ว")
eq(len(SENT), 1, "ยิง LINE 1 ครั้ง")
m = SENT[-1]
eq((m["to"], m["auth"]), ("Cpark", "Bearer tok-push"), "ปลายทาง = กลุ่มพักลีด ด้วยบอทตัวส่ง")
t = m["text"]
mon = timezone.localtime().month
eq(t.splitlines()[0], "Ac Lead No. NLD%d-" % mon, "บรรทัดแรก = ใบร่าง (ไม่มีเลขรัน)")
for part, what in [("ชื่อลูกค้า : สมชาย ใจดี", "ชื่อ"), ("เบอร์โทร : 081-234-5678", "เบอร์"),
                   ("ช่องทาง : web oxlet", "ช่องทางตรงตัวเลือกชีต"),
                   ("รถ : TOYOTA Hilux Revo 2018 · ทะเบียน 5กน1573 · รหัส CS03560 · ราคา 429,000 บาท", "รถ"),
                   ("ขอผ่อนเดือนละ 8 พัน", "ข้อความลูกค้า"), ("a@b.co", "อีเมล"), ("toyota-hilux-revo-2018", "ลิงก์รถ")]:
    eq(part in t, True, "ใบมี%s" % what)
eq(parse_leadsheet(t), None, "ไม่ถูกอ่านเป็นใบจ่ายจริง (ยังไม่มีเลข)")
g = GroupChat.objects.filter(message_id="web-lead-7").first()
eq(bool(g), True, "เก็บลงคลังแชทกลุ่ม")
eq((g.group_id, g.group_name, g.direction, g.extra.get("pushed")), ("Cpark", "ADMIN เก็บ Lead", "out", True),
   "แถวคลังแชทถูกกลุ่ม/ขาออก")

print("[4] ขึ้นในห้องพัก Lead ของ Connect")
b = leadpark.board(cache_sec=0)
w = [i for i in b["waiting"] if i["id"] == "web-lead-7"]
eq(len(w), 1, "อยู่ในรายการรอจ่ายเบอร์")
if w:
    i = w[0]
    eq((i["name"], i["phone"], i["channel"], i["base"]), ("สมชาย ใจดี", "0812345678", "web oxlet", "NLD"),
       "ชื่อ/เบอร์/ช่องทาง/ตัวหน้า")
    eq("Hilux Revo" in i["car"], True, "รถ")

print("[5] ส่งซ้ำ = ไม่โพสต์ซ้ำ")
st, j = post(LEAD)
eq((st, j.get("duplicate")), (200, True), "ตอบว่าซ้ำ")
eq(len(SENT), 1, "ไม่ยิง LINE เพิ่ม")
eq(GroupChat.objects.filter(message_id="web-lead-7").count(), 1, "ไม่มีแถวซ้ำ")

print("[6] LINE ล่ม → ลีดยังเข้าห้องพัก Lead")
MODE["code"] = 400
d2 = dict(LEAD, lead_id=8, name="สมหญิง", phone="0899999999", car={})
st, j = post(d2)
eq((st, j.get("ok"), j.get("pushed")), (200, True, False), "ok แต่ไม่ได้โพสต์")
eq("บอทตัวส่งอาจไม่ได้อยู่ในกลุ่ม" in (j.get("error") or ""), True, "บอกเหตุผลเป็นภาษาคน")
g2 = GroupChat.objects.filter(message_id="web-lead-8").first()
eq(bool(g2 and g2.extra.get("pushed") is False), True, "เก็บไว้พร้อมธงว่ายังไม่ได้โพสต์")
eq(any(i["id"] == "web-lead-8" for i in leadpark.board(cache_sec=0)["waiting"]), True, "ขึ้นห้องพัก Lead")
MODE["code"] = 200

print("[7] ตั้งกลุ่มเองได้ (connect_config.web_lead_group)")
from checkout import connect
cfg = connect.cfg()
cfg["web_lead_group"] = "Cmanual"
cache_store.set_kv("connect_config", cfg)
from checkout import weblead
eq(weblead.park_room()["id"], "Cmanual", "ค่าที่ตั้งเองชนะ")

runner.teardown_databases(old_cfg)
print()
print("ผ่านทั้งหมด" if not fail else "ไม่ผ่าน %d ข้อ: %s" % (len(fail), ", ".join(fail)))
sys.exit(1 if fail else 0)
