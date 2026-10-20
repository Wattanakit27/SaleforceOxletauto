# -*- coding: utf-8 -*-
"""เทสต์ "ลูกค้าอ้างรถในรูป → AI บอกยี่ห้อ/รุ่น" (★ 20 ต.ค.69 · checkout/carvision.py)

    python scripts/test_carvision.py

ฐานข้อมูลทดสอบแยก · ปลอมแค่ขอบระบบ: requests.get (โหลดรูปจาก Facebook) + requests.post (Gemini)
ข้อมูลลูกค้าเป็นค่าสมมติทั้งหมด
"""
import io
import json
import os
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

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

import requests  # noqa: E402
from django.utils import timezone  # noqa: E402
from PIL import Image  # noqa: E402

from checkout import autolead as AL  # noqa: E402
from checkout import carvision as CV  # noqa: E402
from checkout import chatmedia as CM  # noqa: E402
from checkout import connect as C  # noqa: E402
from checkout import lead_qr  # noqa: E402
from checkout.models import ChatLead, ChatOwner, FbChat, FbProfile, GroupChat, LineProfile  # noqa: E402

TMP = tempfile.mkdtemp(prefix="carvision-")
settings.CHAT_MEDIA_ROOT = os.path.join(TMP, "chat")
settings.MEDIA_ROOT = os.path.join(TMP, "media")
settings.GEMINI_API_KEY = "test-key"
CV.BG = False
CM.BG = False

PASS = FAIL = 0


def ok(cond, label, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓", label)
    else:
        FAIL += 1
        print("  ✗", label, ("· " + str(extra)[:500]) if extra != "" else "")


def jpeg(color) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (1600, 1200), color).save(b, "JPEG")
    return b.getvalue()


class _Resp:
    def __init__(self, data, ctype="image/jpeg", status=200):
        self.status_code, self._d = status, data
        self.headers = {"Content-Type": ctype, "Content-Length": str(len(data))}

    def iter_content(self, n):
        for i in range(0, len(self._d), n):
            yield self._d[i:i + n]

    def close(self):
        pass


GETS, POSTS = [], []
REPLY = {"brand": "Toyota", "model": "Yaris Ativ 1.2 Premium 2022", "image": 3, "confidence": 0.86, "reason": "รูปล่างสุด"}


def fake_get(url, *a, **k):
    GETS.append(url)
    return _Resp(jpeg((len(GETS) * 40 % 255, 80, 120)))


class _Post:
    def __init__(self, body):
        self.status_code = 200
        self._b = body
        self.text = json.dumps(body)

    def json(self):
        return self._b


def fake_post(url, json=None, **k):  # noqa: A002
    POSTS.append({"url": url, "body": json})
    import json as _j
    return _Post({"candidates": [{"content": {"parts": [{"text": _j.dumps(REPLY)}]}}]})


requests.get = fake_get
requests.post = fake_post
QR = {"n": 0}
lead_qr.scan_row = lambda *a, **k: QR.__setitem__("n", QR["n"] + 1) or ""

NOW = timezone.now()
_N = {"i": 0}


def fb_chat(name):
    _N["i"] += 1
    tid = "t_%d" % (700 + _N["i"])
    p = FbProfile.objects.create(user_id="psid%d" % _N["i"], display_name=name, channel="2302089596486628", thread_id=tid)
    return ChatOwner.objects.create(fb_profile=p, profile=None, last_in_at=NOW, last_at=NOW)


def fb_msg(o, d, text="", mins=0, image=False):
    _N["i"] += 1
    ex = {}
    if image:
        ex = {"attachments": {"data": [{"mime_type": "image/jpeg",
                                         "image_data": {"url": "https://scontent.xx.fbcdn.net/v/img%d.jpg" % _N["i"]}}]}}
    return FbChat.objects.create(thread_id=o.fb_profile.thread_id, message_id="fbm%d" % _N["i"],
                                 msg_type="image" if image else "text", text="" if image else text, has_media=image,
                                 extra=ex, direction=d, sent_at=NOW - timedelta(minutes=mins), channel="2302089596486628")


def lead(o):
    return ChatLead.objects.filter(chat=o).first()


def run(o):
    C.capture_profile(ChatOwner.objects.get(pk=o.pk))
    return lead(o)


# ═════════════════════════════════════════════════════════════════════
print("\n[1] จับข้อความที่อ้างรถในรูป")
for t in ("จัดไฟแนนซ์ครับสนใจคันล่างสุด", "คันนี้ราคาเท่าไหร่", "สนใจคันสีขาวครับ", "เอาตามรูปเลย", "รูปที่ 3 ยังอยู่ไหม",
          "ขอดูคันที่2", "คันบนสุดผ่อนเท่าไหร่", "แบบในรูปมีไหม"):
    ok(CV.is_ref(t), "จับ: %s" % t)
for t in ("สวัสดีครับ", "ต้องการรถกระบะ", "[รูป]", "ผ่อนเดือนละเท่าไหร่", "มีคันอื่นไหม"):
    ok(not CV.is_ref(t), "ไม่จับ: %s" % t)

print("\n[2] ชื่อรถจากผล AI")
ok(CV.car_name(REPLY) == "Toyota Yaris Ativ", "ตัดรุ่นย่อย/เครื่อง/ปีที่หลุดมา → ยี่ห้อ + รุ่น", CV.car_name(REPLY))
ok(CV.car_name({"brand": "Honda", "model": "Honda City", "confidence": 0.9}) == "Honda City", "รุ่นขึ้นต้นด้วยยี่ห้อซ้ำ = ตัดออก")
ok(CV.car_name({"brand": "Honda", "model": "City", "confidence": 0.3}) == "", "มั่นใจไม่ถึง %.1f = ไม่ใช้" % CV.MIN_CONF)
ok(CV.car_name({"brand": "", "model": "", "confidence": 0.9}) == "", "ดูไม่ออก = ไม่ใช้")

print("\n[3] เลือกรูป")
at = NOW.isoformat()
msgs = ([{"id": "f%d" % i, "dir": "out", "type": "image", "at": (NOW - timedelta(minutes=200 - i)).isoformat()} for i in range(3)]
        + [{"id": "f%d" % i, "dir": "out", "type": "image", "at": (NOW - timedelta(minutes=10)).isoformat()} for i in range(10, 22)]
        + [{"id": "c1", "dir": "in", "type": "image", "at": (NOW - timedelta(minutes=60)).isoformat()},
           {"id": "c2", "dir": "in", "type": "image", "at": (NOW + timedelta(minutes=2)).isoformat()},
           {"id": "r", "dir": "in", "text": "คันล่างสุด", "at": at}])
imgs = CV.images_for(msgs, msgs[-1])
ids = [m["id"] for m in imgs]
ok(len(imgs) == CV.MAX_IMAGES and ids[-1] == "c2" and "f0" not in ids and "c1" not in ids,
   "รูปร้านเกิน %d นาทีไม่เอา · รูปลูกค้าห่างเกิน %d นาทีไม่เอา · รูปลูกค้าส่งตามหลังเอา · ไม่เกิน %d รูป"
   % (CV.WINDOW_MIN, CV.CUST_IMG_MIN, CV.MAX_IMAGES), ids)
ok(CV.find_ref([{"id": "x", "dir": "in", "text": "คันนี้", "at": (NOW - timedelta(minutes=40)).isoformat()}]) is None,
   "ข้อความอ้างรูปเก่าเกิน %d นาที = ไม่ทำ" % CV.RECENT_MIN)
ok(CV.find_ref([{"id": "x", "dir": "in", "text": "คันนี้", "at": at}, {"id": "y", "dir": "in", "text": "ขอบคุณครับ", "at": at}]) is None,
   "ข้อความล่าสุดของลูกค้าไม่ได้อ้างรูป = ไม่ทำ")

# ═════════════════════════════════════════════════════════════════════
print("\n[4] เคสจริง: เพจส่งรูปรถ 3 รูป → ลูกค้า \"สนใจคันล่างสุด\"")
o = fb_chat("ลูกค้าทดสอบ วิชัย")
for i in range(3):
    fb_msg(o, "out", mins=8, image=True)
fb_msg(o, "out", "รุ่นที่มีตอนนี้ครับ", mins=7)
fb_msg(o, "in", "จัดไฟแนนซ์ครับ สนใจคันล่างสุด เบอร์ 0812345670", mins=1)
ld = run(o)
ok(len(POSTS) == 1, "เรียก AI 1 ครั้ง", len(POSTS))
body = json.dumps(POSTS[0]["body"], ensure_ascii=False) if POSTS else ""
parts = (POSTS[0]["body"]["contents"][0]["parts"] if POSTS else [])
ok(sum(1 for p in parts if "inline_data" in p) == 3, "ส่งรูป 3 รูป (ย่อแล้ว)", len(parts))
ok("รูปที่ 3 (ร้าน)" in body and "สนใจคันล่างสุด" in body and "รูปที่ 1 อยู่บนสุด" in body,
   "บอก AI ลำดับรูป + ใครส่ง + ข้อความลูกค้า")
ok("วิชัย" not in body, "ไม่ส่งชื่อลูกค้าให้ AI")
ok(all(len(__import__("base64").b64decode(p["inline_data"]["data"])) < 400_000 for p in parts if "inline_data" in p),
   "รูปถูกย่อก่อนส่ง (ไม่ส่งไฟล์เต็ม)")
ok(ld and ld.car_text == "Toyota Yaris Ativ" and (ld.auto or {}).get("car_text") == CV.SRC,
   "★ ช่อง \"รถลูกค้าถาม\" = Toyota Yaris Ativ (ที่มา: รูป)", (ld.car_text if ld else None, (ld.auto or {}) if ld else None))
v = (ld.auto or {}).get(CV.KEY) or {}
ok(v.get("car") == "Toyota Yaris Ativ" and v.get("image") == 3 and v.get("n") == 3, "เก็บผล AI ไว้ตรวจย้อนหลัง", v)
f = AL._fields(ChatOwner.objects.get(pk=o.pk), lead(o), "NLD10-")
ok(f.get("car") == "Toyota Yaris Ativ", "★ ใบเก็บลีดขึ้นรถคันนี้", f.get("car"))
ok(QR["n"] == 0, "รูปที่ร้านส่งไม่ถูกอ่าน QR (กันเอา QR แอดมินเป็นไอดีลูกค้า)", QR["n"])
n0 = len(POSTS)
run(o)
ok(len(POSTS) == n0, "ข้อความเดิม = ไม่เรียก AI ซ้ำ")

print("\n[5] ช่องที่คนแก้แล้วไม่แตะ · การ์ดโฆษณาแทนได้")
o2 = fb_chat("ลูกค้าคนที่สอง")
ChatLead.objects.create(chat=o2, car_text="Civic FE", car_model="Civic FE",
                        auto={"car_text": "โฆษณา", "car_model": "โฆษณา"})
fb_msg(o2, "out", mins=5, image=True)
fb_msg(o2, "in", "คันนี้ผ่อนเท่าไหร่", mins=0)
l2 = run(o2)
ok(l2.car_text == "Toyota Yaris Ativ", "รถจากการ์ดโฆษณา → แทนด้วยคันที่ลูกค้าชี้ในรูป")
ok(l2.car_model != "Civic FE" and (l2.auto or {}).get("car_model") == CV.SRC,
   "CAR/สูตร ของการ์ดโฆษณาไม่ค้างไว้ (ตรงตัวเลือกชีต หรือ \"ไม่ระบุรุ่นรถ\")", l2.car_model)
o3 = fb_chat("ลูกค้าคนที่สาม")
ChatLead.objects.create(chat=o3, car_text="Honda City", auto={"car_text": C.HUMAN})
fb_msg(o3, "out", mins=5, image=True)
fb_msg(o3, "in", "คันนี้ผ่อนเท่าไหร่", mins=0)
l3 = run(o3)
ok(l3.car_text == "Honda City" and (l3.auto or {}).get(CV.KEY, {}).get("car") == "Toyota Yaris Ativ",
   "ช่องที่คนแก้เอง = ไม่ทับ (ผลเก็บไว้ดูได้)", (l3.car_text, l3.auto))

print("\n[6] ไม่เรียก AI เมื่อไม่ควร")
n0 = len(POSTS)
o4 = fb_chat("ไม่มีรูป")
fb_msg(o4, "in", "คันนี้ราคาเท่าไหร่", mins=0)
run(o4)
ok(len(POSTS) == n0, "ไม่มีรูปในแชท = ไม่เรียก AI")
o5 = fb_chat("ไม่ได้อ้างรูป")
fb_msg(o5, "out", mins=5, image=True)
fb_msg(o5, "in", "ผ่อนเดือนละเท่าไหร่ครับ", mins=0)
run(o5)
ok(len(POSTS) == n0, "ข้อความไม่ได้อ้างรูป = ไม่เรียก AI")
settings.GEMINI_API_KEY = ""
o6 = fb_chat("ไม่มีคีย์")
fb_msg(o6, "out", mins=5, image=True)
fb_msg(o6, "in", "คันนี้", mins=0)
run(o6)
ok(len(POSTS) == n0, "ไม่ได้ตั้ง GEMINI_API_KEY = ปิดเงียบ")
settings.GEMINI_API_KEY = "test-key"
REPLY_LOW = dict(REPLY, confidence=0.2)
_r = REPLY.copy()
REPLY.clear()
REPLY.update(REPLY_LOW)
o7 = fb_chat("ไม่แน่ใจ")
fb_msg(o7, "out", mins=5, image=True)
fb_msg(o7, "in", "คันนี้", mins=0)
l7 = run(o7)
ok(len(POSTS) == n0 + 1 and not (l7.car_text or ""), "AI ไม่มั่นใจ = ไม่เติมช่องรถ", l7.car_text)
REPLY.clear()
REPLY.update(_r)

print("\n[7] LINE: รูปที่ส่งจาก Connect (สำเนาในเครื่อง)")
p = LineProfile.objects.create(user_id="U" + "c" * 32, display_name="ลูกค้า LINE")
ol = ChatOwner.objects.create(profile=p, last_in_at=NOW, last_at=NOW)
Path(settings.MEDIA_ROOT, "chat_out").mkdir(parents=True, exist_ok=True)
Path(settings.MEDIA_ROOT, "chat_out", "a.jpg").write_bytes(jpeg((10, 200, 10)))
GroupChat.objects.create(chat_type=GroupChat.USER, message_id="lo1", sender_id=p.user_id, msg_type="image", text="[รูป]",
                         has_media=True, extra={"out_file": "chat_out/a.jpg"}, direction="out",
                         sent_at=NOW - timedelta(minutes=3))
GroupChat.objects.create(chat_type=GroupChat.USER, message_id="li1", sender_id=p.user_id, msg_type="text",
                         text="สนใจคันในรูปครับ", direction="in", sent_at=NOW)
n0 = len(POSTS)
ll = run(ol)
ok(len(POSTS) == n0 + 1 and ll.car_text == "Toyota Yaris Ativ", "★ แชท LINE + รูปที่ส่งจาก Connect ก็ทำได้", (len(POSTS) - n0, ll.car_text))

print("\nผ่าน %d · ไม่ผ่าน %d" % (PASS, FAIL))
_runner.teardown_databases(_old)
sys.exit(1 if FAIL else 0)
