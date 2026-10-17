# -*- coding: utf-8 -*-
"""เทสต์ส่วนเสริมแชทสำหรับแอป (★ 16 ต.ค.69 · checkout/chatplus.py)

    python scripts/test_chatplus.py

  - ส่งซ้ำด้วย client_id เดิม = ไม่ยิง LINE ซ้ำ คืนข้อความเดิม · ส่งล้มแล้วลองใหม่ได้ · กำลังส่ง = 409
  - ส่งรูป: ย่อ/ตัด EXIF · ลิงก์ https สาธารณะให้ LINE · ส่งล้ม = ไม่บันทึก + ไม่ทิ้งไฟล์ · สิทธิ์ · ลูกค้าจำลองไม่ออกเน็ต
  - ข้อความสำเร็จรูป: ทุกคนเห็น · แก้ได้เฉพาะแอดมิน · ค่าว่าง/ยาวเกิน ฟ้อง
  - ตัวเลขยังไม่อ่านในรายชื่อ · รายชื่อโอน/เหตุผลรับไม่ได้ในหน้าแชท

ฐานข้อมูลทดสอบแยก · **ปลอมที่ขอบระบบเท่านั้น** (`requests` = LINE) — ไม่ปลอมฟังก์ชันของเราเอง
"""
import io
import json
import os
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
settings.LINE_CHANNEL_ACCESS_TOKEN = "tok-crm"
settings.LINE_PUSH_CHANNEL_ACCESS_TOKEN = "tok-push"
settings.SITE_URL = "https://oxlet.example"
MEDIA_TMP = tempfile.mkdtemp(prefix="chatplus-media-")
settings.MEDIA_ROOT = MEDIA_TMP

import requests  # noqa: E402
from django.contrib.sessions.backends.signed_cookies import SessionStore  # noqa: E402
from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402
from django.test import Client  # noqa: E402
from django.utils import timezone  # noqa: E402
from PIL import Image  # noqa: E402

from checkout import connect as C  # noqa: E402
C.BG_FILL = False
import checkout.people as _people  # noqa: E402
_people.BG = False
from checkout import leadflow as _LF  # noqa: E402
_LF.BG_SLOW = False
from checkout import chatmedia as _CM  # noqa: E402
_CM.BG = False
from checkout import chatplus as X  # noqa: E402
from checkout.models import ChatOwner, Employee, GroupChat, LineProfile  # noqa: E402
from dashboard.models import KVStore  # noqa: E402

CALLS = []
POST_CODE = [200]


class _R:
    def __init__(self, code=200, js=None):
        self.status_code, self._js = code, (js or {})
        self.text = json.dumps(self._js)
        self.headers = {}

    def json(self):
        return self._js


def _post(url, *a, **k):
    CALLS.append((url, k.get("json")))
    return _R(POST_CODE[0], {} if POST_CODE[0] == 200 else {"message": "Invalid to"})


def _get(url, *a, **k):
    return _R(404, {"message": "Not found"})


requests.post, requests.get = _post, _get
import dashboard.services.google_sheets as _GS  # noqa: E402


def _no_sheet(*a, **k):
    raise RuntimeError("ไม่ต่อ Google Sheets ในเทสต์")


_GS.fetch_sheet = _no_sheet
_GS.fetch_lead_dropdowns = _no_sheet

OK, BAD = [], []


def ck(name, cond, got=""):
    (OK if cond else BAD).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else "   ได้: %r" % (got,)))


def pushes():
    return [c for c in CALLS if "/message/push" in c[0]]


def client(user):
    cl = Client()
    if user:
        st = SessionStore()
        st["oxlet_user"] = user
        st.save()
        cl.cookies[settings.SESSION_COOKIE_NAME] = st.session_key
    return cl


def J(cl, path, body=None):
    r = cl.post(path, json.dumps(body), content_type="application/json", secure=True) if body is not None \
        else cl.get(path, secure=True)
    try:
        return r.status_code, json.loads(r.content.decode("utf-8"))
    except Exception:
        return r.status_code, {}


def jpeg(w=3000, h=2000, exif_gps=True):
    im = Image.new("RGB", (w, h), (120, 60, 200))
    b = io.BytesIO()
    if exif_gps:
        ex = Image.Exif()
        ex[0x010F] = "PhoneMaker"                  # Make
        ex[0x8825] = {2: (13.0, 45.0, 0.0)}        # GPS IFD (ละติจูด) — ต้องไม่หลุดถึงลูกค้า
        im.save(b, "JPEG", exif=ex)
    else:
        im.save(b, "JPEG")
    return b.getvalue()


def UP(cl, rid, data, cid="", name="car.jpg"):
    f = SimpleUploadedFile(name, data, content_type="image/jpeg")
    body = {"id": str(rid), "file": f}
    if cid:
        body["client_id"] = cid
    r = cl.post("/connect/api/reply_image", body, secure=True)
    try:
        return r.status_code, json.loads(r.content.decode("utf-8"))
    except Exception:
        return r.status_code, {}


try:
    from checkout.views import _save_cfg, line_cfg
    TODAY = timezone.localdate()
    C.save_cfg(dict(C.DEFAULTS, anchor_date=TODAY.isoformat(), anchor_team="A", open="00:00", close="00:00"))
    _save_cfg(dict(line_cfg(), reply_customer=True))

    A1 = Employee.objects.create(nickname="เอหนึ่ง", position="ทีม A")
    A2 = Employee.objects.create(nickname="เอสอง", position="ทีม A")
    P1 = LineProfile.objects.create(user_id="U%032x" % 1, display_name="ลูกค้าหนึ่ง", channel="crm")
    P2 = LineProfile.objects.create(user_id="U%032x" % 2, display_name="ลูกค้าสอง", channel="crm")
    t0 = timezone.now() - timedelta(minutes=3)
    o1 = C.note_customer_message(P1.user_id, t0, "สนใจ Civic")
    o2 = C.note_customer_message(P2.user_id, t0, "มีรถเก๋งไหม")
    C.claim(o1.id, A1)
    GroupChat.objects.create(chat_type="user", message_id="in-1", sender_id=P1.user_id, direction="in",
                             msg_type="text", text="สนใจ Civic", sent_at=t0)

    SA1 = client({"user_id": "Ux1", "nickname": "เอหนึ่ง", "position": "seller"})
    SA2 = client({"user_id": "Ux2", "nickname": "เอสอง", "position": "seller"})
    ADM = client({"user_id": "admin", "nickname": "admin", "position": "admin"})
    NOB = client(None)

    # ═════════════════════════════════════════════════════════════════════
    print("[1] ส่งข้อความ — client_id เดิม = ไม่ส่งหาลูกค้าซ้ำ")
    CALLS.clear()
    s_, d = J(SA1, "/connect/api/reply", {"id": o1.id, "text": "สวัสดีครับ", "client_id": "abc123"})
    ck("ส่งได้", s_ == 200 and d.get("ok"), (s_, d))
    m1 = d.get("message") or {}
    ck("ข้อความที่คืนมีรหัส l<pk> (แอปใช้เป็นคีย์ · ไม่ใช่ LINE id)", str(m1.get("id", "")).startswith("l"), m1)
    ck("ยิง LINE 1 ครั้ง", len(pushes()) == 1, len(pushes()))
    s_, d = J(SA1, "/connect/api/reply", {"id": o1.id, "text": "สวัสดีครับ", "client_id": "abc123"})
    ck("★ ส่งซ้ำ client_id เดิม = ได้ข้อความเดิม ไม่ยิง LINE อีก", s_ == 200 and d.get("dup")
       and (d.get("message") or {}).get("id") == m1.get("id") and len(pushes()) == 1, (s_, d, len(pushes())))
    ck("บทสนทนามีข้อความนี้แถวเดียว", GroupChat.objects.filter(sender_id=P1.user_id, direction="out",
                                                               text="สวัสดีครับ").count() == 1)
    s_, d = J(SA1, "/connect/api/reply", {"id": o1.id, "text": "สวัสดีครับ", "client_id": "other"})
    ck("client_id ใหม่ = ส่งใหม่ได้ (ตั้งใจส่งซ้ำ)", s_ == 200 and len(pushes()) == 2, (s_, len(pushes())))
    s_, d = J(SA1, "/connect/api/reply", {"id": o1.id, "text": "ไม่มี client_id"})
    ck("ไม่ส่ง client_id (หน้าเว็บเดิม) = ทำงานเหมือนเดิม", s_ == 200 and len(pushes()) == 3, (s_, len(pushes())))

    POST_CODE[0] = 400
    s_, d = J(SA1, "/connect/api/reply", {"id": o1.id, "text": "รอบนี้ล้ม", "client_id": "fail1"})
    ck("LINE ปฏิเสธ = ฟ้องเป็นภาษาคน", s_ == 400 and "บล็อก" in (d.get("error") or ""), (s_, d))
    ck("ส่งล้ม = ไม่บันทึกลงบทสนทนา", not GroupChat.objects.filter(text="รอบนี้ล้ม").exists())
    ck("ส่งล้ม = ปลดล็อก (ไม่มีแถวล็อกค้าง)", not KVStore.objects.filter(key__endswith=":fail1").exists())
    POST_CODE[0] = 200
    s_, d = J(SA1, "/connect/api/reply", {"id": o1.id, "text": "รอบนี้ล้ม", "client_id": "fail1"})
    ck("★ กด \"ส่งอีกครั้ง\" หลังล้ม = ส่งได้", s_ == 200 and d.get("ok") and not d.get("dup"), (s_, d))

    KVStore.objects.create(key="%s%d:busy1" % (X.LOCK_PREFIX, o1.id), data={"at": timezone.now().isoformat()})
    n0 = len(pushes())
    s_, d = J(SA1, "/connect/api/reply", {"id": o1.id, "text": "ซ้อน", "client_id": "busy1"})
    ck("รอบก่อนกำลังส่งอยู่ = 409 ไม่ยิงซ้อน", s_ == 409 and len(pushes()) == n0, (s_, d))
    KVStore.objects.filter(key__endswith=":busy1").update(updated_at=timezone.now() - timedelta(seconds=X.LOCK_STALE_SEC + 5))
    s_, d = J(SA1, "/connect/api/reply", {"id": o1.id, "text": "ซ้อน", "client_id": "busy1"})
    ck("ล็อกค้างเกิน 90 วิ (รอบก่อนตาย) = รับช่วงส่งต่อได้", s_ == 200 and d.get("ok"), (s_, d))
    s_, d = J(SA1, "/connect/api/reply", {"id": o1.id, "text": "x", "client_id": "<script>"})
    ck("client_id แปลกๆ ถูกล้างอักขระก่อนใช้", s_ == 200 and not KVStore.objects.filter(key__contains="<").exists(), s_)

    s_, d = J(SA2, "/connect/api/reply", {"id": o1.id, "text": "แย่งตอบ", "client_id": "zz"})
    ck("เซลล์อื่นตอบลูกค้าคนอื่นไม่ได้ (403) และไม่จองล็อก", s_ == 403
       and not KVStore.objects.filter(key__endswith=":zz").exists(), (s_, d))

    # ═════════════════════════════════════════════════════════════════════
    print("[2] ส่งรูปหาลูกค้า")
    CALLS.clear()
    s_, d = UP(SA1, o1.id, jpeg(), cid="img1")
    ck("ส่งรูปได้", s_ == 200 and d.get("ok"), (s_, d))
    p = pushes()
    msg = (p[-1][1] or {}).get("messages", [{}])[0] if p else {}
    ck("LINE ได้ข้อความชนิด image", msg.get("type") == "image", msg)
    ck("ลิงก์รูปเป็น https สาธารณะ (SITE_URL/media/chat_out/…)", str(msg.get("originalContentUrl", "")).startswith(
        "https://oxlet.example/media/chat_out/") and str(msg.get("previewImageUrl", "")).endswith("_p.jpg"), msg)
    row = GroupChat.objects.filter(sender_id=P1.user_id, direction="out", msg_type="image").first()
    ck("บันทึกลงบทสนทนาเป็นรูป", row is not None and row.has_media and row.text == "[รูป]", row)
    rel = (row.extra or {}).get("out_file", "") if row else ""
    full = os.path.join(MEDIA_TMP, rel)
    ck("ไฟล์อยู่บนดิสก์จริง", rel and os.path.isfile(full), rel)
    if rel and os.path.isfile(full):
        im = Image.open(full)
        ck("ย่อด้านยาวไม่เกิน 2048", max(im.size) <= X.MAX_SIDE, im.size)
        ck("★ ตัด EXIF/พิกัดทิ้ง (ไม่ส่งตำแหน่งที่ถ่ายถึงลูกค้า)", not im.getexif().get(0x8825) and not im.getexif().get(0x010F),
           dict(im.getexif()))
        ck("รูปตัวอย่างไม่เกิน 1MB (กติกา LINE)", os.path.getsize(full.replace(".jpg", "_p.jpg")) < 1024 * 1024)
    m = d.get("message") or {}
    ck("ข้อความที่คืนมีไฟล์ (ลิงก์ /media/ · พร้อมดู)", (m.get("files") or [{}])[0].get("url", "").startswith("/media/chat_out/")
       and (m.get("files") or [{}])[0].get("state") == "ready", m)
    s_, d = J(SA1, "/connect/api/chat?id=%d" % o1.id)
    last = (d.get("messages") or [{}])[-1]
    ck("หน้าแชทเห็นรูปที่ส่ง (ไม่ผ่าน /connect/api/media)", last.get("dir") == "out" and (last.get("files") or [{}])[0].get("kind") == "image",
       last)
    s_, d2 = UP(SA1, o1.id, jpeg(), cid="img1")
    ck("★ ส่งรูปซ้ำ client_id เดิม = ไม่ยิง LINE ซ้ำ", d2.get("dup") and len(pushes()) == 1, (d2, len(pushes())))

    POST_CODE[0] = 400
    before = set(os.listdir(os.path.join(MEDIA_TMP, "chat_out")))
    s_, d = UP(SA1, o1.id, jpeg(800, 600), cid="img2")
    ck("LINE ปฏิเสธรูป = ฟ้อง + ไม่บันทึก", s_ == 400 and GroupChat.objects.filter(msg_type="image").count() == 1, (s_, d))
    ck("ส่งล้ม = ไม่ทิ้งไฟล์ค้างบนดิสก์", set(os.listdir(os.path.join(MEDIA_TMP, "chat_out"))) == before)
    POST_CODE[0] = 200

    s_, d = UP(SA1, o1.id, b"%PDF-1.4 not an image", cid="pdf1", name="x.jpg")
    ck("ไม่ใช่รูป = ฟ้องเป็นภาษาคน", s_ == 400 and "JPG" in (d.get("error") or ""), (s_, d))
    s_, d = UP(SA2, o1.id, jpeg(400, 300))
    ck("เซลล์อื่นส่งรูปหาลูกค้าคนอื่นไม่ได้", s_ == 403, s_)
    s_, d = UP(NOB, o1.id, jpeg(400, 300))
    ck("ไม่ login = 401", s_ == 401, s_)

    _save_cfg(dict(line_cfg(), reply_customer=False))
    s_, d = UP(SA1, o1.id, jpeg(400, 300))
    ck("ล็อกการส่งอยู่ = ส่งรูปไม่ได้", s_ == 400 and "ปิดการส่ง" in (d.get("error") or ""), (s_, d))
    _save_cfg(dict(line_cfg(), reply_customer=True))

    old = settings.SITE_URL
    settings.SITE_URL = "http://127.0.0.1:8000"
    s_, d = UP(SA1, o1.id, jpeg(400, 300))
    ck("ไม่ใช่ https = บอกว่าส่งรูปได้เฉพาะเซิร์ฟเวอร์จริง", s_ == 400 and "https" in (d.get("error") or ""), (s_, d))
    settings.SITE_URL = old

    simp = LineProfile.objects.create(user_id="TEST-sim1", display_name="ลูกค้าจำลอง")
    so = C.note_customer_message(simp.user_id, timezone.now(), "ทดสอบ")
    C.claim(so.id, A1)
    CALLS.clear()
    s_, d = UP(SA1, so.id, jpeg(400, 300))
    ck("ลูกค้าจำลอง = บันทึกได้ ไม่ออกเน็ต", s_ == 200 and not pushes(), (s_, d, len(pushes())))

    # ไฟล์เก่าเกินอายุแชท = ถูกกวาด
    stale = os.path.join(MEDIA_TMP, "chat_out", "old.jpg")
    open(stale, "wb").write(b"x")
    os.utime(stale, (0, 0))
    ck("กวาดสำเนาที่เกินอายุแชทลูกค้า", X.cleanup_out() >= 1 and not os.path.exists(stale))

    # ═════════════════════════════════════════════════════════════════════
    print("[3] ข้อความสำเร็จรูป")
    s_, d = J(SA1, "/connect/api/canned")
    ck("เซลล์เห็นรายการ (ว่าง) แต่แก้ไม่ได้", s_ == 200 and d.get("items") == [] and d.get("canEdit") is False, d)
    s_, d = J(SA1, "/connect/api/canned", {"action": "save", "title": "ขอเบอร์", "text": "รบกวนขอเบอร์ครับ"})
    ck("เซลล์เพิ่มไม่ได้ (403)", s_ == 403, s_)
    s_, d = J(ADM, "/connect/api/canned", {"action": "save", "title": "ขอเบอร์", "text": "รบกวนขอเบอร์ติดต่อกลับครับ"})
    ck("แอดมินเพิ่มได้", s_ == 200 and len(d.get("items") or []) == 1, (s_, d))
    cid0 = (d.get("items") or [{}])[0].get("id")
    s_, d = J(ADM, "/connect/api/canned", {"action": "save", "id": cid0, "title": "ขอเบอร์", "text": "แก้แล้ว"})
    ck("แก้ข้อความเดิม (ไม่เพิ่มแถว)", s_ == 200 and len(d["items"]) == 1 and d["items"][0]["text"] == "แก้แล้ว", d)
    s_, d = J(ADM, "/connect/api/canned", {"action": "save", "text": "   "})
    ck("ข้อความว่าง = ฟ้อง", s_ == 400, (s_, d))
    s_, d = J(ADM, "/connect/api/canned", {"action": "save", "text": "ก" * 1001})
    ck("ยาวเกิน 1000 = ฟ้อง", s_ == 400, (s_, d))
    s_, d = J(SA1, "/connect/api/canned")
    ck("เซลล์เห็นข้อความที่แอดมินเพิ่ม", [x["text"] for x in d.get("items") or []] == ["แก้แล้ว"], d)
    s_, d = J(ADM, "/connect/api/canned", {"action": "delete", "id": cid0})
    ck("แอดมินลบได้", s_ == 200 and d.get("items") == [], d)
    s_, d = J(ADM, "/connect/api/canned", {"action": "delete", "id": "nope"})
    ck("ลบของที่ไม่มี = ฟ้อง", s_ == 400, s_)
    s_, d = J(NOB, "/connect/api/canned")
    ck("ไม่ login = 401", s_ == 401, s_)

    # ═════════════════════════════════════════════════════════════════════
    print("[4] ตัวเลขยังไม่อ่าน · รายชื่อโอน · เหตุผลรับไม่ได้")
    for i in range(3):
        GroupChat.objects.create(chat_type="user", message_id="u2-%d" % i, sender_id=P2.user_id, direction="in",
                                 msg_type="text", text="ข้อความ %d" % i, sent_at=timezone.now() - timedelta(minutes=2 - i))
        C.note_customer_message(P2.user_id, timezone.now() - timedelta(minutes=2 - i), "ข้อความ %d" % i)
    s_, d = J(ADM, "/connect/api/inbox?view=all")
    r2 = next((r for r in d.get("rows") or [] if r["id"] == o2.id), {})
    ck("แถวที่ยังไม่อ่านมี unreadCount ≥ 3", r2.get("unread") and (r2.get("unreadCount") or 0) >= 3, r2)
    J(ADM, "/connect/api/chat?id=%d" % o2.id)                 # แอดมินเปิดอ่าน
    s_, d = J(ADM, "/connect/api/inbox?view=all")
    r2 = next((r for r in d.get("rows") or [] if r["id"] == o2.id), {})
    ck("เปิดอ่านแล้ว = unreadCount 0", r2.get("unreadCount") == 0 and not r2.get("unread"), r2)
    ck("ทุกแถวมี unreadCount (แอปไม่ต้องเดา)", all("unreadCount" in r for r in d.get("rows") or []))

    s_, d = J(ADM, "/connect/api/chat?id=%d" % o1.id)
    ck("แอดมิน: หน้าแชทมีรายชื่อโอน", {s["name"] for s in d.get("sellers") or []} >= {"เอหนึ่ง", "เอสอง"}, d.get("sellers"))
    s_, d = J(SA1, "/connect/api/chat?id=%d" % o1.id)
    ck("เซลล์: ไม่ได้รายชื่อโอน", "sellers" not in d, list(d))
    GHOST = client({"user_id": "Ux9", "nickname": "ไม่มีในทะเบียน", "position": "seller"})
    P3 = LineProfile.objects.create(user_id="U%032x" % 3, display_name="ลูกค้าสาม")
    o3 = C.note_customer_message(P3.user_id, timezone.now(), "สวัสดี")
    s_, d = J(GHOST, "/connect/api/chat?id=%d" % o3.id)
    ck("บัญชีไม่ผูกทะเบียน: บอกเหตุผลที่รับไม่ได้", s_ in (401, 403) or "ทะเบียน" in (d.get("claimWhy") or ""), (s_, d))

    # ไม่มี LINE user id ของลูกค้าหลุดใน API ที่เพิ่ม
    _, a = J(ADM, "/connect/api/inbox?view=all")
    _, b = J(SA1, "/connect/api/canned")
    blob = json.dumps([a, b], ensure_ascii=False)
    ck("ไม่มี LINE user id หลุดในรายชื่อ/ข้อความสำเร็จรูป", P1.user_id not in blob and P2.user_id not in blob)

finally:
    _runner.teardown_databases(_old)
    shutil.rmtree(MEDIA_TMP, ignore_errors=True)

print("\nผ่าน %d / %d" % (len(OK), len(OK) + len(BAD)))
if BAD:
    print("ไม่ผ่าน:\n  - " + "\n  - ".join(BAD))
    sys.exit(1)
