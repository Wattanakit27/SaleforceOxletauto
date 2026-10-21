# -*- coding: utf-8 -*-
"""เทสต์หน้า "บรอดแคสต์" ใน CRM (★ 21 ต.ค.69 · checkout/broadcast.py · API /crm/api/broadcast)

    python scripts/test_broadcast.py

ฐานข้อมูลทดสอบแยก · เรียก API ผ่าน test client จริง (signed-cookie session + CSRF จริง)
ปลอมแค่ขอบระบบ (`requests.post/get` = LINE) · รูปเขียนลงโฟลเดอร์ชั่วคราว (ไม่แตะ media/ ของโปรเจกต์)
ข้อมูลลูกค้าเป็นค่าสมมติทั้งหมด — ห้ามใส่ข้อมูลลูกค้าจริงในไฟล์นี้
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile
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
TMP = tempfile.mkdtemp(prefix="bc_test_")
settings.MEDIA_ROOT = TMP
settings.SITE_URL = "https://example.test"
settings.LINE_CHANNEL_ACCESS_TOKEN = "tok-crm"
settings.LINE_PUSH_CHANNEL_ACCESS_TOKEN = "tok-push"
settings.SHOWROOM_WEBHOOK_URL = ""
settings.STOCK_SYNC_SECRET = ""
settings.SHOWROOM_PUBLIC_URL = "https://web.example.test"

import requests  # noqa: E402
from django.contrib.sessions.backends.signed_cookies import SessionStore  # noqa: E402
from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402
from django.test import Client  # noqa: E402
from django.utils import timezone  # noqa: E402

from checkout import broadcast as B  # noqa: E402
from checkout import connect as C  # noqa: E402
from checkout.models import (Broadcast, ChatLead, ChatOwner, ChatOwnerLog, Employee, FbProfile,  # noqa: E402
                             GroupChat, LineProfile)
from dashboard.services import cache_store  # noqa: E402
from dashboard.services import constants as CONST  # noqa: E402

CONST.refresh_from_sheet = lambda *a, **k: True
CONST.ALL_SELLERS[:] = ["มัท"]

PASS = FAIL = 0


def ok(cond, label, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓", label)
    else:
        FAIL += 1
        print("  ✗", label, ("· " + str(extra)[:400]) if extra != "" else "")


# ── ปลอม LINE ──
CALLS = []
QUOTA = {"type": "none"}
USED = {"totalUsage": 0}
MC_STATUS = {"code": 200}


class _R:
    def __init__(self, code, body, ctype="application/json", raw=b""):
        self.status_code, self._b, self.headers, self._raw = code, body, {"Content-Type": ctype}, raw
        self.text = json.dumps(body) if isinstance(body, (dict, list)) else str(body)

    def json(self):
        return self._b

    def iter_content(self, n):
        yield self._raw


_real_post, _real_get = requests.post, requests.get


def fake_post(url, *a, **k):
    CALLS.append({"url": url, "json": k.get("json"), "headers": k.get("headers") or {}})
    if "multicast" in url:
        return _R(MC_STATUS["code"], {} if MC_STATUS["code"] == 200 else {"message": "Invalid to"})
    return _R(200, {})


def fake_get(url, *a, **k):
    if url.endswith("/quota"):
        return _R(200, QUOTA)
    if url.endswith("/consumption"):
        return _R(200, USED)
    return _R(404, {})


requests.post, requests.get = fake_post, fake_get


def client(user=None, csrf=False):
    c = Client(enforce_csrf_checks=csrf)
    if user:
        st = SessionStore()
        st["oxlet_user"] = user
        st.save()
        c.cookies[settings.SESSION_COOKIE_NAME] = st.session_key
    return c


U_ADMIN = {"user_id": "admin", "nickname": "แอดมินบี", "position": "admin"}
U_SELLER = {"user_id": "U" + "1" * 32, "nickname": "มัท", "position": "seller", "seller_name": "มัท"}
NOW = timezone.now()
_N = {"i": 0}
TAG = "สนใจรถปีเก่า"


def line_cust(name, tags=(), days=1, stage="", phone="", channel="", staff=False, uid=None):
    _N["i"] += 1
    uid = uid or "U%032x" % (0xbc0000 + _N["i"])
    p = LineProfile.objects.create(user_id=uid, display_name=name, is_employee=staff, channel="crm")
    o = ChatOwner.objects.create(profile=p, last_in_at=NOW - timedelta(days=days), last_at=NOW - timedelta(days=days))
    ChatLead.objects.create(chat=o, tags=list(tags), stage=stage, phone=phone)
    GroupChat.objects.create(chat_type=GroupChat.USER, message_id="in-%d" % _N["i"], sender_id=uid, msg_type="text",
                             text="สวัสดีครับ", direction=GroupChat.IN, sent_at=NOW - timedelta(days=days), channel=channel)
    return o


def fb_cust(name, tags=()):
    _N["i"] += 1
    p = FbProfile.objects.create(user_id="psid%d" % _N["i"], display_name=name, channel="2302089596486628",
                                 thread_id="t_%d" % _N["i"])
    o = ChatOwner.objects.create(fb_profile=p, profile=None, last_in_at=NOW, last_at=NOW)
    ChatLead.objects.create(chat=o, tags=list(tags))
    return o


def post(c, body):
    r = c.post("/crm/api/broadcast", json.dumps(body), content_type="application/json", secure=True)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {}


def png(color=(200, 30, 30)):
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (40, 30), color).save(b, "PNG")
    return b.getvalue()


# ═════════════════════════════════════════════════════════════════════
L1 = line_cust("ลูกค้าหนึ่ง", [TAG], phone="0812345678")
L2 = line_cust("ลูกค้าสอง", [TAG, "ไม่รับข่าวสาร"])
L3 = line_cust("ลูกค้าสาม", [TAG, "Honda"], stage="won")
L4 = line_cust("ลูกค้าสี่", [TAG], days=50)
L5 = line_cust("ลูกค้าห้า", [TAG, "Honda"], channel="push")
F1 = fb_cust("ลูกค้าเฟซ", [TAG])
S1 = line_cust("พนักงานเอง", [TAG], staff=True)
SIM = line_cust("ลูกค้าจำลอง", [TAG], uid="TEST-sim-1")
BASE = {"any": [TAG]}

print("\n[1] เงื่อนไข")
f = B.clean_filters({"days": "abc", "src": "x", "stages": ["won", "boom"], "deal": "?", "any": TAG})
ok(f["days"] == 0 and f["src"] == "" and f["stages"] == ["won"] and f["deal"] == "" and f["any"] == [TAG] and f["closed"] is True,
   "ค่ามั่ว = ค่าตั้งต้น · ปิดการขายไม่รวมโดยปริยาย", f)
a = B.audience(B.clean_filters(BASE))
ids = {r["id"] for r in a["rows"]}
ok(ids == {L1.id, L4.id, L5.id, F1.id}, "แท็กเดียว: ไม่รวมพนักงาน/ลูกค้าจำลอง/ไม่รับข่าวสาร/ปิดการขาย", ids)
ok(a["optout"] == 1 and a["closed"] == 1, "นับแยกว่าไม่ได้รับเพราะอะไร (ไม่รับข่าวสาร 1 · ปิดการขาย 1)", a)
ok({r["id"] for r in B.audience(B.clean_filters(dict(BASE, closed=False)))["rows"]} == ids | {L3.id}, "ติ๊กออก = รวมลูกค้าที่ปิดการขาย")
ok({r["id"] for r in B.audience(B.clean_filters({"all": [TAG, "Honda"]}))["rows"]} == {L5.id}, "ต้องมีครบทุกแท็ก")
ok({r["id"] for r in B.audience(B.clean_filters(dict(BASE, **{"not": ["Honda"]})))["rows"]} == {L1.id, L4.id, F1.id}, "ไม่เอาแท็ก")
ok({r["id"] for r in B.audience(B.clean_filters(dict(BASE, days=30)))["rows"]} == {L1.id, L5.id, F1.id}, "คุยภายใน 30 วัน")
ok({r["id"] for r in B.audience(B.clean_filters(dict(BASE, src="fb")))["rows"]} == {F1.id}, "เฉพาะ Facebook")
ok({r["id"] for r in B.audience(B.clean_filters(dict(BASE, q="081-234")))["rows"]} == {L1.id}, "ค้นเบอร์แบบมีขีด")
ok({r["id"] for r in B.audience(B.clean_filters(dict(BASE, contact=True)))["rows"]} == {L1.id}, "เฉพาะที่ให้เบอร์/ไลน์")
ok("แท็ก สนใจรถปีเก่า" in B.describe(B.clean_filters(BASE)), "สรุปเงื่อนไขอ่านออก", B.describe(B.clean_filters(BASE)))

print("\n[2] สิทธิ์ + ตัวอย่างกลุ่ม")
A = client(U_ADMIN, csrf=False)
s, d = post(client(), {"action": "preview", "filters": BASE})
ok(s == 401, "ไม่ login = 401", s)
s, d = post(client(U_SELLER), {"action": "preview", "filters": BASE})
ok(s == 403, "เซลล์ = 403", s)
s, d = post(client(U_ADMIN, csrf=True), {"action": "preview", "filters": BASE})
ok(s == 403, "ไม่มี CSRF = 403", s)
s, d = post(A, {"action": "preview", "filters": BASE, "quota": True})
ok(s == 200 and d.get("total") == 4 and d.get("line") == 3 and d.get("fb") == 1, "นับ LINE/Facebook ถูก", d.get("total"))
acc = {x["key"]: x["n"] for x in d.get("accounts", [])}
ok(acc == {"crm": 2, "push": 1}, "แยกบัญชี OA ตามที่ลูกค้าคุยอยู่ (ข้อความล่าสุดของลูกค้า)", acc)
ok(any(t["t"] == TAG for t in d.get("tags", [])), "ส่งรายการแท็กที่ใช้อยู่ + จำนวน")
ok(not re.search(r"U[0-9a-f]{32}", json.dumps(d.get("rows", []))), "รายชื่อบนหน้าเว็บไม่มี LINE userId")
ok((d.get("quota") or {}).get("crm", {}).get("limit") is None, "โควต้าไม่จำกัด = limit None", d.get("quota"))

print("\n[3] ดาวน์โหลดรายชื่อ")
r = A.get("/crm/api/broadcast", {"export": "csv", "f": json.dumps(BASE)}, secure=True)
body = r.content.decode("utf-8")
ok(r.status_code == 200 and body.startswith("﻿") and "attachment" in r["Content-Disposition"], "CSV ใส่ BOM + ดาวน์โหลดเป็นไฟล์")
ok("ลูกค้าหนึ่ง" in body and "ลูกค้าเฟซ" in body and "ลูกค้าสอง" not in body and "'0812345678" in body,
   "มีลูกค้า LINE+Facebook · ไม่มีคนไม่รับข่าวสาร · เบอร์ใส่ ' กันเลข 0 หาย")
r = A.get("/crm/api/broadcast", {"export": "ids", "account": "crm", "f": json.dumps(BASE)}, secure=True)
lines = r.content.decode().split()
ok(r.status_code == 200 and set(lines) == {L1.profile.user_id, L4.profile.user_id}, "ไฟล์ userId แยกบัญชี (ไม่มีของบัญชีอื่น/Facebook)", lines)
r = client(U_SELLER).get("/crm/api/broadcast", {"export": "csv", "f": "{}"}, secure=True)
ok(r.status_code == 403, "เซลล์ดาวน์โหลดไม่ได้")

print("\n[4] อัปรูป + ตรวจเนื้อหา")
r = A.post("/crm/api/broadcast", {"file": SimpleUploadedFile("a.png", png(), "image/png")}, secure=True)
up = r.json()
ok(r.status_code == 200 and up.get("ok") and os.path.exists(os.path.join(TMP, up["full"])) and os.path.exists(os.path.join(TMP, up["prev"])),
   "อัปรูป = สำเนา JPEG ใน media/chat_out (รูปเต็ม + ตัวอย่าง)", up)
r = A.post("/crm/api/broadcast", {"file": SimpleUploadedFile("a.txt", b"hello", "text/plain")}, secure=True)
ok(r.status_code == 400, "ไม่ใช่รูป = 400")
for bad, why in [({}, "ยังไม่มีเนื้อหา"), ({"text": "x" * 2001}, "ยาวเกินไป"),
                 ({"images": [{"full": "../../etc/passwd"}]}, "ไม่ถูกต้อง"),
                 ({"images": [{"full": "chat_out/" + "a" * 32 + ".jpg"}]}, "หารูป")]:
    try:
        B.clean_content(bad)
        ok(False, "ปฏิเสธ: " + why)
    except B.BError as e:
        ok(why in str(e), "ปฏิเสธ: " + why, str(e))

print("\n[5] ส่งทดสอบหาตัวเอง")
emp = Employee.objects.create(nickname="แอดมินบี")
ME = "U" + "e" * 32
LineProfile.objects.create(user_id=ME, display_name="บี", employee=emp, is_employee=True, channel="crm")
CONTENT = {"text": "รถเข้าใหม่ ปี 2014 ราคาพิเศษ", "images": [{"full": up["full"]}], "cars": []}
CALLS.clear()
s, d = post(A, {"action": "test", "content": CONTENT, "account": "crm"})
push = [c for c in CALLS if c["url"].endswith("/push")]
ok(s == 200 and d.get("ok") and len(push) == 1 and push[0]["json"]["to"] == ME, "ส่งหา LINE ของแอดมินเอง (ฝั่งบัญชีเดียวกับลูกค้า)", (s, d))
ok(push and [m["type"] for m in push[0]["json"]["messages"]] == ["text", "image"]
   and push[0]["json"]["messages"][1]["originalContentUrl"].startswith("https://example.test/media/chat_out/"),
   "เนื้อหา = ข้อความ + รูป (ลิงก์ https ของเรา)")
s, d = post(client({"user_id": "admin", "nickname": "ไม่มีไลน์", "position": "admin"}), {"action": "test", "content": CONTENT})
ok(s == 400 and "ไม่พบ LINE ของคุณ" in d.get("error", ""), "ไม่มี LINE ของแอดมินในระบบ = บอกวิธีแก้", d)

print("\n[6] ส่งจริง — ด่าน")
cache_store.set_kv("checkout_line_config", {"reply_customer": False})
s, d = post(A, {"action": "send", "content": CONTENT, "filters": BASE, "confirm": 3, "client_id": "cid-aaaa-0001"})
ok(s == 400 and "ปิดการส่ง" in d.get("error", ""), "สวิตช์ส่งหาลูกค้าปิด = ไม่ส่ง", d)
cache_store.set_kv("checkout_line_config", {"reply_customer": True})
s, d = post(A, {"action": "send", "content": dict(CONTENT, text="แก้ข้อความแล้ว"), "filters": BASE, "confirm": 3,
                "client_id": "cid-aaaa-0002"})
ok(s == 400 and "ส่งทดสอบ" in d.get("error", ""), "แก้เนื้อหาหลังทดสอบ = ต้องทดสอบใหม่", d)
s, d = post(A, {"action": "send", "content": CONTENT, "filters": BASE, "confirm": 99, "client_id": "cid-aaaa-0003"})
ok(s == 200 and d.get("needConfirm") and d.get("count") == 3 and not Broadcast.objects.exists(),
   "จำนวนที่ยืนยันไม่ตรง = ถามใหม่ ไม่ส่ง", d)
B._QUOTA.clear()
QUOTA.update({"type": "limited", "value": 500})
USED["totalUsage"] = 499
s, d = post(A, {"action": "send", "content": CONTENT, "filters": BASE, "confirm": 3, "client_id": "cid-aaaa-0004"})
ok(s == 400 and "โควต้า" in d.get("error", ""), "โควต้าเดือนนี้ไม่พอ = ไม่ส่ง", d)
B._QUOTA.clear()
QUOTA.clear()
QUOTA["type"] = "none"

print("\n[7] ส่งจริง")
before = {o.id: (o.awaiting_since, o.last_dir, o.last_out_at, o.read_at) for o in ChatOwner.objects.all()}
CALLS.clear()
s, d = post(A, {"action": "send", "content": CONTENT, "filters": BASE, "confirm": 3, "client_id": "cid-aaaa-0005"})
mc = [c for c in CALLS if "multicast" in c["url"]]
ok(s == 200 and d.get("ok") and d["item"]["sent"] == 3 and d["item"]["status"] == "done", "ส่งครบ 3 ราย", d)
tos = {(c["headers"].get("Authorization"), tuple(sorted(c["json"]["to"]))) for c in mc}
ok(tos == {("Bearer tok-crm", tuple(sorted([L1.profile.user_id, L4.profile.user_id]))),
           ("Bearer tok-push", (L5.profile.user_id,))}, "multicast แยกตามบัญชีที่ลูกค้าคุยอยู่ · ไม่ส่ง Facebook", tos)
ok(all(re.match(r"^[0-9a-f-]{36}$", c["headers"].get("X-Line-Retry-Key", "")) for c in mc), "ทุกชุดมี X-Line-Retry-Key")
b = Broadcast.objects.get()
ok(b.fb_skipped == 1 and set(b.recipients) == {L1.id, L4.id, L5.id} and b.created_by == "แอดมินบี" and b.tested_by == "แอดมินบี",
   "บันทึกประวัติ (ผู้รับ · Facebook ที่ข้าม · คนส่ง/คนทดสอบ)")
rows = GroupChat.objects.filter(message_id__startswith="bc:")
ok(rows.count() == 6 and set(rows.values_list("sender_id", flat=True)) == {L1.profile.user_id, L4.profile.user_id, L5.profile.user_id},
   "เก็บข้อความลงแชทของลูกค้าแต่ละคน (ข้อความ + รูป)", rows.count())
ok(ChatOwnerLog.objects.filter(action=ChatOwnerLog.BCAST).count() == 3, "ประวัติลูกค้า: ส่งบรอดแคสต์")
after = {o.id: (o.awaiting_since, o.last_dir, o.last_out_at, o.read_at) for o in ChatOwner.objects.all()}
ok(before == after, "ไม่แตะนาฬิกาตอบ/ข้อความล่าสุด/ยังไม่อ่าน")
o1 = ChatOwner.objects.get(pk=L1.pk)
ok(not any((m.get("text") or "").startswith("รถเข้าใหม่") for m in C.messages(o1)), "ตัวจับคำ (messages ปกติ) ไม่เห็นข้อความบรอดแคสต์")
bm = [m for m in C.messages(o1, bc=True) if m.get("bc")]
ok(len(bm) == 2 and bm[1]["files"] and bm[1]["files"][0]["url"].startswith("/media/chat_out/"), "หน้าแชทเห็นข้อความบรอดแคสต์ + รูป", bm)
CALLS.clear()
s, d = post(A, {"action": "send", "content": CONTENT, "filters": BASE, "confirm": 3, "client_id": "cid-aaaa-0005"})
ok(s == 200 and d.get("dup") and not CALLS and Broadcast.objects.count() == 1, "กดซ้ำ (รหัสเดิม) = ไม่ส่งซ้ำ")

print("\n[8] ลีดไม่เปลี่ยนเพราะข้อความบรอดแคสต์")
BUY = {"text": "เรามีฝ่ายจัดซื้อประเมินราคารับซื้อ ส่งรูปรถ ด้านนอก ด้านใน หน้าปัดเลขไมล์ มาได้เลย", "images": [], "cars": []}
post(A, {"action": "test", "content": BUY, "account": "crm"})
s, d = post(A, {"action": "send", "content": BUY, "filters": {"any": [TAG], "src": "line", "days": 30}, "confirm": 2,
                "client_id": "cid-aaaa-0006"})
ok(s == 200 and d.get("ok"), "ส่งข้อความที่มีคำของฝ่ายจัดซื้อ", d)
r = A.get("/connect/api/chat", {"id": L1.pk}, secure=True)
cj = r.json() if r.status_code == 200 else {}
ok(r.status_code == 200 and any(m.get("bc") for m in cj.get("messages", [])), "เปิดแชทใน Connect เห็นข้อความบรอดแคสต์", r.status_code)
ok(C.deal_of(ChatLead.objects.get(chat=L1)) == "sell", "ลีดยังเป็นลีดขาย (ไม่ถูกเปลี่ยนเป็นลีดรับซื้อ)")

print("\n[9] ส่งไม่สำเร็จ / แบ่งชุด")
B.BATCH = 1
MC_STATUS["code"] = 400
post(A, {"action": "test", "content": dict(CONTENT, text="ชุดที่สาม"), "account": "crm"})
n_rows = GroupChat.objects.filter(message_id__startswith="bc:").count()
CALLS.clear()
s, d = post(A, {"action": "send", "content": dict(CONTENT, text="ชุดที่สาม"), "filters": BASE, "confirm": 3, "client_id": "cid-aaaa-0007"})
ok(s == 502 and d["item"]["status"] == "failed" and "บล็อก" in d.get("error", ""), "LINE ปฏิเสธ = บันทึกว่าไม่สำเร็จ + เหตุผลภาษาคน", d)
ok(len([c for c in CALLS if "multicast" in c["url"]]) == 3, "แบ่งชุดตามเพดาน (ชุดละ 1 = 3 ครั้ง)")
ok(GroupChat.objects.filter(message_id__startswith="bc:").count() == n_rows, "ส่งไม่ถึง = ไม่เก็บลงแชท")
MC_STATUS["code"] = 200
B.BATCH = 500

print("\n[10] การ์ดรถจากสต็อก")
from cars.models import Car  # noqa: E402
os.makedirs(os.path.join(TMP, "cars"), exist_ok=True)
with open(os.path.join(TMP, "cars", "c1.png"), "wb") as fh:
    fh.write(png((10, 120, 10)))
car = Car.objects.create(code="CS9901", brand="Honda", model="City", year=2014, km=120000, price=259000, stage="show",
                         web_listed=True)
car.photo.name = "cars/c1.png"
Car.objects.filter(pk=car.pk).update(photo="cars/c1.png")
sold = Car.objects.create(code="CS9902", brand="Toyota", model="Vios", stage="sold", status="sold")
msgs, infos, store = B.build({"text": "", "images": [], "cars": ["CS9901", "CS9902"]})
fl = msgs[0] if msgs else {}
ok(len(msgs) == 1 and fl.get("type") == "flex" and len(infos) == 1, "รถที่ขายแล้วไม่ส่ง · การ์ดรถ 1 ใบ", [m.get("type") for m in msgs])
bub = fl.get("contents", {})
ok(bub.get("hero", {}).get("url", "").startswith("https://example.test/media/chat_out/"), "รูปรถเป็นสำเนา https ของเรา", bub.get("hero"))
ok(bub.get("footer", {}).get("contents", [{}])[0].get("action", {}).get("uri") == "https://web.example.test/stock/CS9901/",
   "ปุ่มลิงก์หน้ารถบนเว็บโชว์รูม (รถที่ขึ้นเว็บอยู่)", bub.get("footer"))
ok("฿259,000" in json.dumps(bub, ensure_ascii=False) and "Honda City" in fl.get("altText", ""), "ราคา + ชื่อรุ่นในการ์ด")
Car.objects.filter(pk="CS9901").update(web_listed=False)
msgs2, _, _ = B.build({"text": "x", "images": [], "cars": ["CS9901"]})
ok("footer" not in msgs2[1]["contents"], "รถยังไม่ขึ้นเว็บ = ไม่มีปุ่มลิงก์ (กันลิงก์เปิดแล้วไม่เจอ)")
settings.SITE_URL = "http://127.0.0.1:8000"
try:
    B.build({"text": "x", "images": [], "cars": ["CS9901"]})
    ok(False, "ไม่ใช่ https = ไม่ส่งรูป/การ์ด")
except B.BError as e:
    ok("https" in str(e), "ไม่ใช่ https = ไม่ส่งรูป/การ์ด")
settings.SITE_URL = "https://example.test"
s, d = post(A, {"action": "cars", "codes": ["CS9901", "CS9902"]})
ok(s == 200 and [c["code"] for c in d.get("cars", [])] == ["CS9901"], "รายละเอียดรถที่เลือก (ไม่รวมคันที่ขายแล้ว)", d)

print("\n[11] ประวัติ")
r = A.get("/crm/api/broadcast", secure=True)
h = r.json().get("history", [])
ok(r.status_code == 200 and len(h) == 3 and h[0]["status"] == "failed", "ประวัติการส่ง (ใหม่สุดก่อน)", [x["status"] for x in h])
ok(not re.search(r"U[0-9a-f]{32}", r.content.decode()), "ประวัติไม่มี LINE userId")

requests.post, requests.get = _real_post, _real_get
shutil.rmtree(TMP, ignore_errors=True)
print("\nผ่าน %d · ไม่ผ่าน %d" % (PASS, FAIL))
_runner.teardown_databases(_old)
sys.exit(1 if FAIL else 0)
