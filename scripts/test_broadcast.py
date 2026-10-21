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
PUSH_FAIL = set()


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
    if url.endswith("/push") and (k.get("json") or {}).get("to") in PUSH_FAIL:
        return _R(400, {"message": "Invalid to"})
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
ok(s == 400 and "ยังไม่มี LINE" in d.get("error", "") and "แอดบัญชี LINE OA" in d.get("error", ""),
   "ไม่มี LINE ของแอดมินในระบบ = บอกวิธีแก้", d)

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
msgs, infos, store, clinks = B.build({"text": "", "images": [], "cars": ["CS9901", "CS9902"]})
fl = msgs[0] if msgs else {}
ok(len(msgs) == 1 and fl.get("type") == "flex" and len(infos) == 1, "รถที่ขายแล้วไม่ส่ง · การ์ดรถ 1 ใบ", [m.get("type") for m in msgs])
bub = fl.get("contents", {})
ok(bub.get("hero", {}).get("url", "").startswith("https://example.test/media/chat_out/"), "รูปรถเป็นสำเนา https ของเรา", bub.get("hero"))
ok(bub.get("footer", {}).get("contents", [{}])[0].get("action", {}).get("uri") == B.PH % 0
   and clinks and clinks[0]["url"] == "https://web.example.test/stock/CS9901/",
   "ปุ่มลิงก์หน้ารถบนเว็บโชว์รูม (รถที่ขึ้นเว็บอยู่ · เป็นลิงก์ติดตาม)", (bub.get("footer"), clinks))
ok("฿259,000" in json.dumps(bub, ensure_ascii=False) and "Honda City" in fl.get("altText", ""), "ราคา + ชื่อรุ่นในการ์ด")
Car.objects.filter(pk="CS9901").update(web_listed=False)
msgs2, _, _, _ = B.build({"text": "x", "images": [], "cars": ["CS9901"]})
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

print("\n[12] ค้นหาเงื่อนไข — อาชีพ · รายได้ · ยี่ห้อ · ไม่เอา")
ok(B.income_range("22,000") == (22000, 22000) and B.income_range("2หมื่น") == (20000, 20000)
   and B.income_range("20000-25000") == (20000, 25000) and B.income_range("15k") == (15000, 15000)
   and B.income_range("ไม่ทราบ") is None, "อ่านช่องรายได้ที่พิมพ์อิสระได้ (22,000 · 2หมื่น · ช่วง · 15k)")
for o, occ, inc in [(L1, "พนักงานบริษัท", "22,000"), (L4, "พนักงานโรงงาน", "15000-18000"), (L5, "ค้าขาย", "3หมื่น"),
                    (F1, "พนักงานบริษัท", "")]:
    ChatLead.objects.filter(chat=o).update(occupation=occ, income=inc)
ALL = {"days": 0}


def ids_of(**kw):
    return {r["id"] for r in B.audience(B.clean_filters(dict(ALL, **kw)))["rows"]}


ok(ids_of(conds=[{"f": "occupation", "v": "พนักงาน"}]) == {L1.id, L4.id, F1.id}, "อาชีพ \"มีคำว่า พนักงาน\" = ทุกแบบพนักงาน")
ok(ids_of(conds=[{"f": "occupation", "v": "พนักงานบริษัท"}, {"f": "occupation", "v": "ค้าขาย"}]) == {L1.id, F1.id, L5.id},
   "หัวข้อเดียวกันหลายค่า = อย่างใดอย่างหนึ่ง")
ok(ids_of(conds=[{"f": "occupation", "v": "พนักงาน"}, {"f": "brand", "v": "Honda"}]) == set(),
   "ต่างหัวข้อ = ต้องตรงทุกข้อ (พนักงาน + Honda ไม่มีใครตรง)")
ok(ids_of(conds=[{"f": "brand", "v": "Honda"}]) == {L5.id}, "ยี่ห้อจากแท็ก (เทียบทั้งคำ)")
ok(ids_of(conds=[{"f": "occupation", "v": "พนักงาน", "neg": True}]) == {L5.id}, "ไม่เอา = ตัดคนที่ตรงออก",
   ids_of(conds=[{"f": "occupation", "v": "พนักงาน", "neg": True}]))
ok(ids_of(conds=[{"f": "text", "v": "โรงงาน"}]) == {L4.id}, "คำค้นค้นในข้อมูลลูกค้าด้วย (อาชีพ)")
ok(ids_of(imin=20000) == {L1.id, L5.id}, "รายได้ตั้งแต่ 20,000 (ช่วง 15-18k ไม่นับ · 3หมื่นนับ)")
ok(ids_of(imin=16000, imax=21000) == {L4.id}, "ช่วงรายได้ซ้อนกัน = นับ (15,000-18,000 อยู่ในช่วง 16,000-21,000)")
a12 = B.audience(B.clean_filters(dict(ALL, imin=20000)))
ok(a12["noinc"] == 1, "ลูกค้าที่ไม่รู้รายได้ไม่ถูกนับ และนับแยกให้หน้าเว็บบอก", a12["noinc"])
ok("อาชีพ พนักงาน" in B.describe(B.clean_filters({"conds": [{"f": "occupation", "v": "พนักงาน"}], "imin": 20000}))
   and "รายได้ 20,000" in B.describe(B.clean_filters({"imin": 20000})), "สรุปเงื่อนไขในประวัติอ่านออก")
bad = B.clean_filters({"conds": [{"f": "boom", "v": "x"}, {"f": "occupation", "v": ""}, "x"], "imin": "abc"})
ok(bad["conds"] == [] and bad["imin"] == 0, "เงื่อนไขมั่ว = ไม่ใช้")
s, d = post(A, {"action": "preview", "filters": dict(ALL, conds=[{"f": "occupation", "v": "พนักงาน"}])})
fac = {g["f"]: [x["v"] for x in g["items"]] for g in d.get("facets", [])}
ok(s == 200 and d.get("total") == 3 and "พนักงานบริษัท" in fac.get("occupation", []) and "Honda" in fac.get("brand", [])
   and "Honda" not in fac.get("tag", []), "ตัวเลือกแยกหัวข้อ (อาชีพ · ยี่ห้อไม่ปนกับแท็กทั่วไป)", fac)
ok(any(r["occupation"] == "พนักงานบริษัท" and r["income"] == "22,000" for r in d.get("rows", [])), "ตารางผลลัพธ์มีอาชีพ/รายได้")
r = A.get("/crm/api/broadcast", {"export": "csv", "f": json.dumps(dict(ALL, imin=20000))}, secure=True)
body = r.content.decode("utf-8")
ok("อาชีพ" in body.splitlines()[0] and "ค้าขาย" in body and "พนักงานโรงงาน" not in body, "CSV มีคอลัมน์อาชีพ/รายได้ และกรองตามรายได้")

print("\n[13] ลิงก์ติดตาม + ส่งทดสอบหาทีม (แบบ MAAC)")
B.BG = False
from checkout.models import BroadcastClick  # noqa: E402
UA_PHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari Line/13.18.0"
UA_BOT = "facebookexternalhit/1.1;line-poker/1.0"
LK = [{"label": "ดูโปรเดือนนี้", "url": "https://shop.example.test/promo?a=1", "mode": "button", "tag": "สนใจโปร"},
      {"label": "เว็บร้าน", "url": "https://shop.example.test/", "mode": "text", "tagOn": False}]
for bad, why in [({"links": [{"label": "x", "url": "javascript:alert(1)"}]}, "ไม่ถูกต้อง"),
                 ({"links": [{"label": "", "url": "https://a.test/"}]}, "ยังไม่มีชื่อปุ่ม"),
                 ({"links": [{"label": "ก" * 21, "url": "https://a.test/"}]}, "ยาวเกินไป"),
                 ({"links": [{"label": "a", "url": "https://a.test/x y"}]}, "ไม่ถูกต้อง"),
                 ({"links": [{"label": "a%d" % i, "url": "https://a.test/%d" % i} for i in range(4)]}, "ไม่เกิน 3")]:
    try:
        B.clean_content(bad)
        ok(False, "ปฏิเสธลิงก์: " + why)
    except B.BError as e:
        ok(why in str(e), "ปฏิเสธลิงก์: " + why, str(e))
cc = B.clean_content({"links": [{"label": "ดูรถ", "url": "https://a.test/"}, {"label": "", "url": ""}]})
ok(len(cc["links"]) == 1 and cc["links"][0]["tag"] == "กดลิงก์ ดูรถ" and cc["links"][0]["mode"] == "button",
   "แถวว่างข้าม · แท็กตั้งต้น = \"กดลิงก์ <ชื่อปุ่ม>\" · ลิงก์อย่างเดียวส่งได้", cc["links"])
cc = B.clean_content({"text": "x", "links": LK, "link_title": "  โปรพิเศษ  "})
ok(cc["links"][1]["tag"] == "" and cc["link_title"] == "โปรพิเศษ", "ปิดติดแท็ก = ไม่ติด · หัวการ์ดตัดช่องว่าง")
ok(B.content_hash(cc) != B.content_hash(dict(cc, links=cc["links"][:1])), "แก้ลิงก์ = เนื้อหาเปลี่ยน (ต้องทดสอบใหม่)")
msgs, infos, store, links = B.build(cc)
ok([m["type"] for m in msgs] == ["text", "flex"] and len(links) == 2, "ข้อความ (+ลิงก์แนบ) + การ์ดปุ่มลิงก์", [m["type"] for m in msgs])
ok("เว็บร้าน: __OXBCL01__" in msgs[0]["text"] and "shop.example.test" not in json.dumps(msgs),
   "ลิงก์ในข้อความที่ส่ง = ตัวแทน (แทนเป็นลิงก์ของแต่ละคนตอนส่ง)", msgs[0]["text"])
btn = msgs[1]["contents"]["footer"]["contents"]
ok(len(btn) == 1 and btn[0]["action"] == {"type": "uri", "label": "ดูโปรเดือนนี้", "uri": "__OXBCL00__"}
   and msgs[1]["contents"]["body"]["contents"][0]["text"] == "โปรพิเศษ", "ซ่อนลิงก์หลังปุ่ม (Flex) + หัวการ์ด", btn)
ok("https://shop.example.test/" in store[0]["text"] and "[ปุ่มลิงก์] โปรพิเศษ" in store[1]["text"],
   "ที่เก็บลงแชทของลูกค้า = ลิงก์จริง (เซลล์อ่านออก)", store)
UPS = [B.upload(SimpleUploadedFile("p%d.png" % i, png((40 * i, 10, 10)), "image/png")) for i in range(3)]
try:
    B.build(B.clean_content({"text": "x", "images": [{"full": u["full"]} for u in UPS], "cars": ["CS9901"], "links": LK[:1]}))
    six = False
except B.BError as e:
    six = "ไม่เกิน 5 ชิ้น" in str(e)
Car.objects.filter(pk="CS9901").update(web_listed=True)
m5, _i5, _s5, l5 = B.build(B.clean_content({"text": "x", "cars": ["CS9901"], "links": LK[:1]}))
car_link = [x for x in l5 if x["mode"] == "car"]
ok(six, "ข้อความ+รูป 3+การ์ดรถ+การ์ดลิงก์ = 6 ชิ้น เกิน LINE = บอกวิธีแก้")
ok(len(car_link) == 1 and car_link[0]["url"] == "https://web.example.test/stock/CS9901/"
   and car_link[0]["tag"] == "กดดูรถ Honda City"
   and m5[1]["contents"]["footer"]["contents"][0]["action"]["uri"] == "__OXBCL01__",
   "ปุ่ม \"ดูรายละเอียดรถ\" ก็เป็นลิงก์ติดตาม (แท็ก กดดูรถ <รุ่น>)", car_link)
m5b, _i, _s, l5b = B.build(B.clean_content({"text": "x", "cars": ["CS9901"], "car_tag": False}))
ok(l5b and l5b[0]["tag"] == "", "ปิดติดแท็กคนกดดูรถได้")

print("\n[14] รายชื่อคนในทีมที่ส่งทดสอบได้")
emp2 = Employee.objects.create(nickname="นวลทดสอบ")
NUAN = "U" + "a" * 32
LineProfile.objects.create(user_id=NUAN, display_name="Nuan", employee=emp2, is_employee=True, channel="crm")
emp3 = Employee.objects.create(nickname="ไม่มีไลน์")
s, d = post(A, {"action": "testers"})
names = [x["name"] for x in d.get("testers", [])]
ok(s == 200 and names[:1] == ["แอดมินบี"] and "นวลทดสอบ" in names and "ไม่มีไลน์" not in names,
   "ตัวเองขึ้นก่อน · เฉพาะคนที่มี LINE กับบัญชีของร้าน", names)
ok(not re.search(r"U[0-9a-f]{32}", json.dumps(d)), "รายชื่อคนทดสอบไม่มี LINE userId")
s, d = post(client(U_SELLER), {"action": "testers"})
ok(s == 403, "เซลล์ดูรายชื่อไม่ได้")

print("\n[15] ส่งทดสอบหาทีม + ลิงก์ทดสอบ")
CONT = {"text": "โปรเดือนนี้ ดาวน์ 0 บาท", "links": LK, "link_title": "โปรพิเศษ"}
CALLS.clear()
s, d = post(A, {"action": "test", "content": CONT, "account": "crm", "testers": [emp.pk, emp2.pk, emp3.pk]})
push = [c for c in CALLS if c["url"].endswith("/push")]
ok(s == 200 and d.get("ok") and {c["json"]["to"] for c in push} == {ME, NUAN}, "ส่งทดสอบถึงคนที่เลือก (2 คนที่มี LINE)", d)
ok("ส่งไม่ถึง: ไม่มีไลน์" in d.get("message", "") and [r["ok"] for r in d.get("results", [])] == [True, True, False],
   "บอกรายคนว่าใครส่งไม่ถึง", d.get("message"))
u1 = re.findall(r"https://example\.test/b/(t-[0-9a-z-]+)", json.dumps(push[0]["json"]))
u2 = re.findall(r"https://example\.test/b/(t-[0-9a-z-]+)", json.dumps(push[1]["json"]))
ok(len(u1) == 2 and len(u2) == 2 and set(u1).isdisjoint(u2), "ลิงก์ทดสอบของแต่ละคนไม่ซ้ำกัน", (u1, u2))
ok(cache_store.get_kv("bcast_testers")["data"] == [emp.pk, emp2.pk, emp3.pk], "จำรายชื่อคนทดสอบไว้ครั้งหน้า")
tok_nuan_btn = [t for t in u2 if t.endswith("-0-" + t.split("-")[-1])][0]
r = client().get("/b/" + tok_nuan_btn, secure=True, HTTP_USER_AGENT=UA_PHONE)
ok(r.status_code == 302 and r["Location"] == "https://shop.example.test/promo?a=1" and r["Cache-Control"] == "no-store",
   "กดลิงก์ทดสอบ = พาไปหน้าจริง", (r.status_code, r.get("Location")))
s, d = post(A, {"action": "teststate", "hash": B.content_hash(B.clean_content(CONT))})
ok(s == 200 and [x["name"] for x in d.get("clicks", [])] == ["นวลทดสอบ"] and d["clicks"][0]["links"][0]["label"] == "ดูโปรเดือนนี้",
   "หน้าเว็บรู้ว่าใครในทีมกดลิงก์ทดสอบแล้ว", d)
ok(not BroadcastClick.objects.exists() and "สนใจโปร" not in (ChatLead.objects.get(chat=L1).tags or []),
   "ลิงก์ทดสอบไม่นับเป็นลูกค้ากด · ไม่ติดแท็กใคร")
r = client().get("/b/" + u1[0], secure=True, HTTP_USER_AGENT=UA_BOT)
s, d = post(A, {"action": "teststate", "hash": B.content_hash(B.clean_content(CONT))})
ok(r.status_code == 302 and len(d.get("clicks", [])) == 1, "ตัวดึงลิงก์ทำตัวอย่าง (LINE preview) ไม่นับว่ากด")

print("\n[16] ส่งจริงแบบมีลิงก์ = ส่งทีละคน (ลิงก์ของแต่ละคนไม่ซ้ำ)")
CALLS.clear()
s, d = post(A, {"action": "send", "content": CONT, "filters": BASE, "confirm": 3, "client_id": "cid-link-0001"})
push = [c for c in CALLS if c["url"].endswith("/push")]
mc = [c for c in CALLS if "multicast" in c["url"]]
bl = Broadcast.objects.get(client_id="cid-link-0001")
ok(s == 200 and d.get("ok") and bl.mode == "push" and bl.status == "done" and bl.sent == 3 and not mc,
   "ไม่ใช้ multicast · ส่งครบ 3 ราย", (d, bl.status, bl.sent))
ok({c["json"]["to"] for c in push} == {L1.profile.user_id, L4.profile.user_id, L5.profile.user_id}
   and {c["headers"]["Authorization"] for c in push if c["json"]["to"] == L5.profile.user_id} == {"Bearer tok-push"},
   "ส่งหาลูกค้าแต่ละคนด้วยบัญชีที่เขาคุยอยู่")
urls = {}
for c in push:
    urls[c["json"]["to"]] = re.findall(r"https://example\.test/b/([0-9a-z]+-[0-9a-z]+-\d-[0-9a-f]+)", json.dumps(c["json"]))
ok(all(len(v) == 2 for v in urls.values()) and len({x for v in urls.values() for x in v}) == 6,
   "ลูกค้า 3 คน × 2 ลิงก์ = ลิงก์ไม่ซ้ำกัน 6 อัน", urls)
ok(len({c["headers"].get("X-Line-Retry-Key") for c in push}) == 3, "Retry-Key ต่อคน (ส่งซ้ำคนเดิม LINE ไม่ส่งซ้ำ)")
ok(GroupChat.objects.filter(message_id__startswith="bc:%d:" % bl.pk, text__contains="เว็บร้าน: https://shop.example.test/").count() == 3,
   "เก็บลงแชทของลูกค้าแต่ละคน (ลิงก์จริง ไม่ใช่ลิงก์ติดตาม)")
ok(len(bl.links) == 2 and bl.links[0]["tag"] == "สนใจโปร", "บันทึกลิงก์ + แท็กไว้กับบรอดแคสต์")

print("\n[17] ลูกค้ากดลิงก์ → จดว่าใครกด + ติดแท็ก")
tok1 = [t for t in urls[L1.profile.user_id] if "-0-" in t][0]
r = client().get("/b/" + tok1, secure=True, HTTP_USER_AGENT=UA_PHONE)
ok(r.status_code == 302 and r["Location"] == "https://shop.example.test/promo?a=1" and r["Referrer-Policy"] == "no-referrer",
   "กดแล้วพาไปปลายทาง (ไม่ส่ง referrer)", (r.status_code, r.get("Location")))
ck = BroadcastClick.objects.get(broadcast=bl, chat=L1, link=0)
ld1 = ChatLead.objects.get(chat=L1)
ok(ck.count == 1 and ck.tagged == "สนใจโปร" and "สนใจโปร" in ld1.tags and (ld1.auto or {}).get("_btags", {}).get("สนใจโปร", {}).get("b") == bl.pk,
   "จดคนกด + ติดแท็กของลิงก์ (จดว่าติดจากบรอดแคสต์ไหน)", (ck.count, ck.tagged, ld1.tags))
ok(ChatOwnerLog.objects.filter(chat_id=L1.pk, action=ChatOwnerLog.BCAST, note__contains="ลูกค้ากด").exists(), "ประวัติลูกค้า: กดลิงก์")
client().get("/b/" + tok1, secure=True, HTTP_USER_AGENT=UA_PHONE)
ck.refresh_from_db()
ok(ck.count == 2 and ChatLead.objects.get(chat=L1).tags.count("สนใจโปร") == 1, "กดซ้ำ = นับเพิ่ม · แท็กไม่ซ้ำ")
client().get("/b/" + tok1, secure=True, HTTP_USER_AGENT=UA_BOT)
client().head("/b/" + tok1, secure=True, HTTP_USER_AGENT=UA_PHONE)
ck.refresh_from_db()
ok(ck.count == 2, "ตัวดึงลิงก์ทำตัวอย่าง / HEAD ไม่นับ")
tok_txt = [t for t in urls[L4.profile.user_id] if "-1-" in t][0]
r = client().get("/b/" + tok_txt, secure=True, HTTP_USER_AGENT=UA_PHONE)
ok(r.status_code == 302 and r["Location"] == "https://shop.example.test/" and BroadcastClick.objects.get(chat=L4, link=1).tagged == ""
   and "กดลิงก์ เว็บร้าน" not in (ChatLead.objects.get(chat=L4).tags or []), "ลิงก์ที่ปิดติดแท็ก = จดคนกดอย่างเดียว")
ld5 = ChatLead.objects.get(chat=L5)
ld5.auto = {"_tag_no": ["สนใจโปร"]}
ld5.save()
tok5 = [t for t in urls[L5.profile.user_id] if "-0-" in t][0]
client().get("/b/" + tok5, secure=True, HTTP_USER_AGENT=UA_PHONE)
ok(BroadcastClick.objects.get(chat=L5, link=0).tagged == "" and "สนใจโปร" not in ChatLead.objects.get(chat=L5).tags,
   "แท็กที่คนเคยเอาออกเอง = ไม่ติดกลับ")
bad = tok1[:-1] + ("0" if tok1[-1] != "0" else "1")
r = client().get("/b/" + bad, secure=True, HTTP_USER_AGENT=UA_PHONE)
ok(r.status_code == 404 and "Location" not in r, "ลายเซ็นผิด = ไม่พาไปไหน (กันปลอมลิงก์คนอื่น)")
fake = tok1.replace("-0-", "-7-")
r = client().get("/b/" + fake, secure=True, HTTP_USER_AGENT=UA_PHONE)
ok(r.status_code == 404, "ลิงก์ลำดับที่ไม่มีจริง = 404")
r = client().get("/b/../../etc", secure=True)
ok(r.status_code == 404, "ค่ามั่ว = 404")

print("\n[18] ประวัติ + ดาวน์โหลดคนกด")
r = A.get("/crm/api/broadcast", secure=True)
hb = [x for x in r.json().get("history", []) if x["id"] == bl.pk][0]
ok(hb["mode"] == "push" and hb["clickPeople"] == 3 and hb["clickTagged"] == 1 and hb["links"][0]["people"] == 2
   and hb["links"][0]["clicks"] == 3 and hb["links"][1]["people"] == 1, "ประวัติบอกคนกด (รวม/รายลิงก์/ติดแท็ก)", hb)
r = A.get("/crm/api/broadcast", {"export": "clicks", "id": bl.pk}, secure=True)
body = r.content.decode("utf-8")
ok(r.status_code == 200 and body.startswith("﻿") and "ลูกค้าหนึ่ง" in body and "สนใจโปร" in body and "'0812345678" in body
   and len(body.strip().splitlines()) == 4, "CSV คนกด 3 คน (ชื่อ · เบอร์ · ลิงก์ที่กด · แท็กที่ติด)", body[:300])
ok(client(U_SELLER).get("/crm/api/broadcast", {"export": "clicks", "id": bl.pk}, secure=True).status_code == 403,
   "เซลล์ดาวน์โหลดคนกดไม่ได้")
ok(A.get("/crm/api/broadcast", {"export": "clicks", "id": 99999}, secure=True).status_code == 404, "บรอดแคสต์ไม่มีจริง = 404")

print("\n[19] ส่งไม่ถึงบางคน + งานค้างทำต่อ")
PUSH_FAIL.add(L4.profile.user_id)
post(A, {"action": "test", "content": dict(CONT, text="รอบสอง"), "account": "crm"})
s, d = post(A, {"action": "send", "content": dict(CONT, text="รอบสอง"), "filters": BASE, "confirm": 3, "client_id": "cid-link-0002"})
b2 = Broadcast.objects.get(client_id="cid-link-0002")
ok(b2.status == "partial" and b2.sent == 2 and b2.failed == 1 and "บล็อก" in b2.error, "บางคนส่งไม่ถึง = ส่งได้บางส่วน + เหตุผล", b2.error)
ok(not GroupChat.objects.filter(message_id="bc:%d:%d:0" % (b2.pk, L4.pk)).exists(), "คนที่ส่งไม่ถึงไม่ถูกเก็บลงแชท")
PUSH_FAIL.clear()
b3 = Broadcast.objects.create(client_id="cid-link-0003", text="ค้าง", links=bl.links, mode="push", status="sending",
                              total=3, sent=1, recipients=[L1.pk],
                              accounts={"crm": {"name": "x", "n": 2, "ok": 1, "fail": 0, "error": ""},
                                        "push": {"name": "y", "n": 1, "ok": 0, "fail": 0, "error": ""}})
tpl = json.dumps([{"type": "text", "text": "ค้าง " + B.PH % 0}])
cache_store.set_kv(B.JOB_KEY % b3.pk, {"tpl": tpl, "n": 1, "store": [{"type": "text", "text": "ค้าง"}],
                                       "plan": [[L1.pk, L1.profile.user_id, "crm"], [L4.pk, L4.profile.user_id, "crm"],
                                                [L5.pk, L5.profile.user_id, "push"]], "cid": "cid-link-0003", "who": "แอดมินบี"})
cache_store.set_kv(B.JOBST_KEY % b3.pk, {"at": (timezone.now() - timedelta(minutes=10)).isoformat(), "failed": {}})
CALLS.clear()
res = B.resume_stale()
b3.refresh_from_db()
tos = [c["json"]["to"] for c in CALLS if c["url"].endswith("/push")]
ok(res == [b3.pk] and b3.status == "done" and b3.sent == 3 and sorted(tos) == sorted([L4.profile.user_id, L5.profile.user_id]),
   "เซิร์ฟเวอร์รีสตาร์ทกลางทาง = ทำต่อเฉพาะคนที่ยังไม่ได้ (ไม่ส่งซ้ำคนเดิม)", (res, b3.status, tos))
cache_store.set_kv(B.JOBST_KEY % b3.pk, {"at": timezone.now().isoformat(), "failed": {}})
Broadcast.objects.filter(pk=b3.pk).update(status="sending")
ok(B.resume_stale() == [], "งานที่ยังขยับอยู่ = ไม่แตะ")
Broadcast.objects.filter(pk=b3.pk).update(created_at=timezone.now() - timedelta(hours=21))
B.resume_stale()
ok(Broadcast.objects.get(pk=b3.pk).status == "partial", "ค้างเกิน 20 ชม. = ปิดงาน ไม่ส่งต่อ (retry key หมดอายุ)")
B.BG = True

requests.post, requests.get = _real_post, _real_get
shutil.rmtree(TMP, ignore_errors=True)
print("\nผ่าน %d · ไม่ผ่าน %d" % (PASS, FAIL))
_runner.teardown_databases(_old)
sys.exit(1 if FAIL else 0)
