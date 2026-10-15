# -*- coding: utf-8 -*-
"""เทสต์ "แจ้งผู้พัฒนา" (15 ต.ค.69)

    python scripts/test_dev_requests.py

ฐานข้อมูลทดสอบแยก · ปลอมแค่ `requests.post` (= LINE push) · ทุกอย่างอื่นวิ่งของจริงผ่าน test client
(อัปไฟล์ผ่าน /track/api/upload · สร้าง/ดู/เปลี่ยนสถานะผ่าน /api/admin/dev_requests · เปิดไฟล์ผ่าน …/file)
"""
import io
import json
import os
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
os.environ["DB_HOST"] = ""
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

from datetime import timedelta  # noqa: E402
from unittest import mock  # noqa: E402

from django.contrib.auth.models import User  # noqa: E402
from django.contrib.sessions.backends.signed_cookies import SessionStore  # noqa: E402
from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402
from django.test import Client  # noqa: E402
from django.utils import timezone  # noqa: E402

from checkout.models import Employee, LineProfile  # noqa: E402
from dashboard.models import DevRequest  # noqa: E402
from dashboard.services import devreq  # noqa: E402

FAILS = []


def ok(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else " — " + str(extra)))
    if not cond:
        FAILS.append(name)


PRIV = tempfile.mkdtemp(prefix="devreq_priv_")
MEDIA = tempfile.mkdtemp(prefix="devreq_media_")
settings.DEV_REQUEST_ROOT = PRIV
settings.MEDIA_ROOT = MEDIA
settings.SITE_URL = "https://example.test"
settings.LINE_PUSH_CHANNEL_ACCESS_TOKEN = "PUSH_TOKEN"
settings.LINE_CHANNEL_ACCESS_TOKEN = "CRM_TOKEN"
OWNER_UID = "U" + "a" * 32

owner = Employee.objects.create(nickname="Wattanakit", display_name="วัฒนกิจ", position="")
LineProfile.objects.create(user_id=OWNER_UID, employee=owner, is_employee=True, nickname="Wattanakit", channel="push")

SENT = []
LINE_STATUS = {"code": 200}


class R:
    def __init__(self, code, js=None):
        self.status_code, self._js, self.text = code, js or {}, json.dumps(js or {})

    def json(self):
        return self._js


def fake_post(url, *a, **kw):
    if "api.line.me" in url:
        SENT.append(kw.get("json") or json.loads(kw.get("data") or "{}"))
        c = LINE_STATUS["code"]
        return R(c, {} if c == 200 else {"message": "Failed to send messages"})
    return R(404)


def client(user):
    c = Client()
    if user:
        s = SessionStore()
        s["oxlet_user"] = user
        s.save()
        c.cookies[settings.SESSION_COOKIE_NAME] = s.session_key
    return c


BOSS = {"user_id": "admin", "position": "admin", "nickname": "admin"}
ADM = {"user_id": "U" + "b" * 32, "position": "admin", "nickname": "กวาง", "display_name": "Kwang"}
SELLER = {"user_id": "U" + "c" * 32, "position": "seller", "nickname": "มัท"}

P = [mock.patch("requests.post", fake_post)]
for p in P:
    p.start()
try:
    # ── 1) อัปไฟล์แนบ ─────────────────────────────────────────────────
    print("\n[1] อัปไฟล์แนบ (/track/api/upload · target=devreq)")
    u = User.objects.create_user("kwang", password="x")
    up = Client()
    up.force_login(u)
    PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 3000

    def upload(name, data, ctype):
        r = up.post("/track/api/upload", {"file": SimpleUploadedFile(name, data, content_type=ctype),
                                          "target": "devreq"}, secure=True)
        return r.json()

    f1 = upload("หน้าจอ บั๊ก.png", PNG, "image/png")
    f2 = upload("clip.mp4", b"\x00\x00\x00\x18ftypmp42" + b"v" * 5000, "video/mp4")
    f3 = upload("evil.html", b"<script>alert(1)</script>", "text/html")
    ok("อัปรูป/คลิป/ไฟล์ได้ · บอกชนิดไฟล์", f1.get("ok") and f1["kind"] == "image" and f2["kind"] == "video"
       and f3["kind"] == "file", (f1, f2, f3))
    p1 = os.path.join(PRIV, f1["id"])
    ok("ไฟล์อยู่ในที่ปิด (ไม่ใช่ /media/)", os.path.isfile(p1) and not any(os.scandir(MEDIA)), p1)
    ok("ชื่อไฟล์ในเครื่องสุ่มใหม่ ไม่ใช้ชื่อที่อัปมา", "หน้าจอ" not in f1["id"] and f1["id"].endswith(".png"), f1["id"])
    anon = Client().post("/track/api/upload", {"file": SimpleUploadedFile("a.png", PNG, "image/png"),
                                               "target": "devreq"}, secure=True)
    ok("ไม่ login อัปไม่ได้", anon.status_code in (302, 401, 403), anon.status_code)

    # ── 2) ส่งเรื่อง → บันทึก + เด้ง LINE เจ้าของ ─────────────────────
    print("\n[2] ส่งเรื่อง")
    adm = client(ADM)

    def create(body, c=adm):
        r = c.post("/api/admin/dev_requests", json.dumps(dict({"action": "create"}, **body)),
                   content_type="application/json", secure=True)
        return r.status_code, r.json()

    code, d = create({"kind": "bug", "urgent": True, "title": "กดบันทึกสถานะลูกค้าแล้วไม่ติด",
                      "detail": "หน้าเซลล์ · กดบันทึก Z แล้วขึ้นหมุนค้าง", "page": "หน้าเซลล์",
                      "files": [{"id": f1["id"], "name": f1["name"]}, {"id": f2["id"], "name": f2["name"]}]})
    ok("ส่งได้ · บันทึกลงตาราง", code == 200 and d["ok"] and DevRequest.objects.count() == 1, d)
    r1 = DevRequest.objects.first()
    ok("จดว่าใครแจ้ง (ชื่อเล่น) + ประเภท + ด่วน", r1.requester == "กวาง" and r1.kind == "bug" and r1.urgent)
    ok("เด้ง LINE เจ้าของ 1 ข้อความ ด้วยบอทตัวส่ง", len(SENT) == 1 and SENT[0].get("to") == OWNER_UID, SENT)
    txt = SENT[0]["messages"][0]["text"] if SENT else ""
    ok("ข้อความ LINE: ประเภท/ด่วน/ผู้แจ้ง/หัวข้อ/ไฟล์แนบ/ลิงก์เข้าระบบ",
       "เจอบั๊ก" in txt and "ด่วน" in txt and "กวาง" in txt and "กดบันทึกสถานะลูกค้า" in txt
       and "รูป 1 · คลิป 1" in txt and "https://example.test/dashboard/?panel=devrequests" in txt, txt)
    ok("ไม่ส่งไฟล์เข้า LINE (ข้อความอย่างเดียว)", all(m.get("type") == "text" for m in SENT[0]["messages"]))
    ok("ผลการเด้ง LINE จดในแถว", r1.line_ok is True and d["item"]["lineOk"] is True)

    ok("ไม่มีหัวข้อ = ไม่บันทึก", create({"kind": "bug", "title": "  "})[0] == 400)
    ok("ประเภทมั่ว = ไม่บันทึก", create({"kind": "xx", "title": "a"})[0] == 400)
    ok("ไฟล์ปลอม/../ = ไม่บันทึก", create({"title": "a", "files": [{"id": "../../etc/passwd"}]})[0] == 400
       and create({"title": "a", "files": [{"id": "2026-10/" + "0" * 32 + ".png"}]})[0] == 400)
    ok("เกิน 10 ไฟล์ = ไม่บันทึก", create({"title": "a", "files": [{"id": f1["id"]}] * 11})[0] == 400)
    ok("เซลล์ส่งไม่ได้ (เฉพาะแอดมิน)", create({"title": "a"}, client(SELLER))[0] == 401)
    ok("ไม่ login ส่งไม่ได้", create({"title": "a"}, Client())[0] == 401)

    # LINE ส่งไม่ถึง → ยังบันทึก + บอกเหตุผล
    LINE_STATUS["code"] = 400
    code, d = create({"kind": "feature", "title": "อยากได้ปุ่มส่งออก Excel", "files": [{"id": f3["id"], "name": f3["name"]}]})
    LINE_STATUS["code"] = 200
    ok("LINE ไม่ถึง = ยังบันทึก · บอกว่าไม่ถึง", code == 200 and d["item"]["lineOk"] is False and d["item"]["lineError"], d)

    # ── 3) ดูรายการ ───────────────────────────────────────────────────
    print("\n[3] รายการ")
    g = adm.get("/api/admin/dev_requests?days=30", secure=True).json()
    ok("เห็นทุกเรื่อง ใหม่สุดก่อน · นับตามสถานะ", g["ok"] and [i["title"] for i in g["items"]][0] == "อยากได้ปุ่มส่งออก Excel"
       and g["counts"].get("new") == 2, g.get("counts"))
    it = [i for i in g["items"] if i["title"].startswith("กดบันทึก")][0]
    ok("รายการมีผู้แจ้ง/เวลา/วันที่/ไฟล์ (ลิงก์ผ่าน API)", it["requester"] == "กวาง" and it["date"] and it["time"]
       and it["files"][0]["url"].startswith("/api/admin/dev_requests/file?id="), it)
    body = json.dumps(g, ensure_ascii=False)
    ok("ไม่มี LINE user id / ที่อยู่ไฟล์จริงหลุด", ADM["user_id"] not in body and OWNER_UID not in body and PRIV not in body)
    ok("แอดมินทั่วไปจัดการสถานะไม่ได้ (canManage false)", g["canManage"] is False)
    ok("เซลล์ดูไม่ได้", client(SELLER).get("/api/admin/dev_requests", secure=True).status_code == 401)

    # ── 4) เปลี่ยนสถานะ (แอดมินสูงสุด) ─────────────────────────────────
    print("\n[4] สถานะ")
    boss = client(BOSS)

    def st(c, body):
        r = c.post("/api/admin/dev_requests", json.dumps(dict({"action": "status"}, **body)),
                   content_type="application/json", secure=True)
        return r.status_code, r.json()
    ok("แอดมินทั่วไปเปลี่ยนสถานะไม่ได้", st(adm, {"id": r1.pk, "status": "done"})[0] == 403)
    code, d = st(boss, {"id": r1.pk, "status": "doing", "note": "กำลังแก้ · คาดว่าเสร็จพรุ่งนี้"})
    ok("แอดมินสูงสุดเปลี่ยนสถานะ + หมายเหตุได้", code == 200 and d["item"]["status"] == "doing"
       and DevRequest.objects.get(pk=r1.pk).note.startswith("กำลังแก้"), d)
    ok("สถานะมั่ว = ไม่บันทึก", st(boss, {"id": r1.pk, "status": "zzz"})[0] == 400)
    ok("ไม่มีเรื่องนี้ = บอก", st(boss, {"id": 99999, "status": "done"})[0] == 400)
    ok("กรองตามสถานะ", [i["id"] for i in boss.get("/api/admin/dev_requests?status=doing", secure=True).json()["items"]] == [r1.pk])
    ok("แอดมินสูงสุด canManage true", boss.get("/api/admin/dev_requests", secure=True).json()["canManage"] is True)

    # ── 5) เปิดไฟล์แนบ ─────────────────────────────────────────────────
    print("\n[5] เปิดไฟล์แนบ")
    r = adm.get("/api/admin/dev_requests/file?id=%d&i=0" % r1.pk, secure=True)
    ok("รูป: เปิดในเบราว์เซอร์ได้ · nosniff · sandbox", r.status_code == 200 and r["Content-Type"] == "image/png"
       and r["X-Content-Type-Options"] == "nosniff" and "sandbox" in r.get("Content-Security-Policy", "")
       and b"".join(r.streaming_content) == PNG, dict(r.items()))
    rid2 = DevRequest.objects.get(title="อยากได้ปุ่มส่งออก Excel").pk
    r = adm.get("/api/admin/dev_requests/file?id=%d&i=0" % rid2, secure=True)
    ok("ไฟล์ HTML: บังคับดาวน์โหลด (ไม่รันในโดเมนเรา)", r.status_code == 200 and r["Content-Type"] == "application/octet-stream"
       and "attachment" in r.get("Content-Disposition", ""), dict(r.items()))
    ok("ลำดับไฟล์มั่ว = 404", adm.get("/api/admin/dev_requests/file?id=%d&i=9" % r1.pk, secure=True).status_code == 404)
    ok("เซลล์เปิดไฟล์ไม่ได้", client(SELLER).get("/api/admin/dev_requests/file?id=%d&i=0" % r1.pk, secure=True).status_code == 401)

    # ── 6) เพดานเด้ง LINE ต่อชั่วโมง ────────────────────────────────────
    print("\n[6] เพดาน LINE")
    old_cap, devreq.LINE_PER_HOUR = devreq.LINE_PER_HOUR, 1
    n0 = len(SENT)
    code, d = create({"kind": "question", "title": "สอบถามวิธีใช้"})
    devreq.LINE_PER_HOUR = old_cap
    ok("เกินเพดาน = บันทึกแต่ไม่เด้ง LINE", code == 200 and len(SENT) == n0 and d["item"]["lineOk"] is False
       and "เกิน" in d["item"]["lineError"], d)

    # ── 7) ลบไฟล์เก่า ───────────────────────────────────────────────────
    print("\n[7] ลบไฟล์เก่า")
    DevRequest.objects.filter(pk=r1.pk).update(created_at=timezone.now() - timedelta(days=200))
    orphan_old = upload("old.png", PNG, "image/png")
    orphan_new = upload("new.png", PNG, "image/png")
    po = os.path.join(PRIV, orphan_old["id"])
    t = timezone.now().timestamp() - 3 * 86400
    os.utime(po, (t, t))
    n = devreq.cleanup_files()
    r1 = DevRequest.objects.get(pk=r1.pk)
    ok("เรื่องเก่าเกิน 180 วัน: ลบไฟล์ · เรื่องยังอยู่ · ไฟล์ขึ้นว่าลบแล้ว", not os.path.exists(p1)
       and all(f.get("gone") for f in r1.files), (n, r1.files))
    ok("ไฟล์ที่อัปแล้วไม่ได้ส่ง ค้างเกิน 2 วัน = ลบ · เพิ่งอัป = เก็บไว้", not os.path.exists(po)
       and os.path.exists(os.path.join(PRIV, orphan_new["id"])))
    ok("เรื่องใหม่ไฟล์ไม่ถูกลบ", os.path.exists(os.path.join(PRIV, f3["id"])))
    g = adm.get("/api/admin/dev_requests?days=365", secure=True).json()
    it = [i for i in g["items"] if i["id"] == r1.pk][0]
    ok("รายการบอกว่าไฟล์ถูกลบ ไม่มีลิงก์", all(f["gone"] and not f["url"] for f in it["files"]), it["files"])
finally:
    for p in P:
        p.stop()
    _runner.teardown_databases(_old)

print()
print("ผ่านทั้งหมด" if not FAILS else "ไม่ผ่าน %d ข้อ: %s" % (len(FAILS), ", ".join(FAILS)))
sys.exit(1 if FAILS else 0)
