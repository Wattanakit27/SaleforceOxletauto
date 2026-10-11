# -*- coding: utf-8 -*-
"""เทสต์รูป/ไฟล์ที่ลูกค้าส่งในแชท (★ 11 ต.ค.69) — checkout/chatmedia.py + /connect/api/media

    python scripts/test_chat_media.py

โหลดจาก LINE (token ตามบัญชีที่ได้ยิน · 404/400 = หมดอายุ · 401/5xx = ลองใหม่) · Facebook (เฉพาะโดเมน FB ·
ไม่ตาม redirect ออกนอก FB) · ใหญ่เกิน · ชนิดไฟล์ (รูปต้องดูไบต์จริง · svg/html ห้ามเปิดในเบราว์เซอร์) ·
สิทธิ์ผ่าน test client จริง (แอดมิน/เจ้าของ/คิวรอรับ/คนอื่น/ลูกค้าผิดคน) · รอบกวาด · ลบไฟล์ของแชทที่หมดอายุ ·
คำสั่ง chat_media · ไม่มี LINE user id หลุดในลิงก์

ฐานข้อมูลทดสอบแยก · ที่เก็บไฟล์เป็นโฟลเดอร์ชั่วคราว · **ปลอมที่ขอบระบบ** (`requests.get`) ไม่ปลอมฟังก์ชันของเราเอง
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
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
if "testserver" not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]
settings.LINE_CHANNEL_ACCESS_TOKEN = "tok-crm"
settings.LINE_PUSH_CHANNEL_ACCESS_TOKEN = "tok-push"
STORE = tempfile.mkdtemp(prefix="chat_media_")
settings.CHAT_MEDIA_ROOT = Path(STORE)
settings.CHAT_MEDIA_MAX_MB = 1

import requests  # noqa: E402
from django.contrib.sessions.backends.signed_cookies import SessionStore  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.test import Client  # noqa: E402
from django.utils import timezone  # noqa: E402

import dashboard.services.google_sheets as GS  # noqa: E402
from checkout import chatmedia as CM  # noqa: E402
from checkout import connect as C  # noqa: E402
from checkout import leadflow as LF  # noqa: E402
from checkout.models import ChatOwner, Employee, FbChat, FbProfile, GroupChat, LineProfile  # noqa: E402

C.BG_FILL = False
import checkout.people as _people  # noqa: E402
_people.BG = False             # แคชชื่อหมดอายุ = โหลดตรง (ไม่แตก thread ชนฐานข้อมูลทดสอบ)
LF.BG_SLOW = False
CM.BG = False

# ── ขอบระบบ: requests.get ───────────────────────────────────────────
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 300
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 300
PDF = b"%PDF-1.7\n" + b"x" * 300
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
HTML = b"<html><script>alert(1)</script></html>"
ROUTES = {}          # url → [(สถานะ, ไบต์, content-type, header เพิ่ม), …] ตามลำดับครั้งที่ยิง (ตัวท้ายใช้ซ้ำ)
CALLS = []           # (url, Authorization)


class _Resp:
    def __init__(self, code, body=b"", ctype="", extra=None, length=True):
        self.status_code = code
        self._body = body
        self.headers = {"Content-Type": ctype}
        if length and body:
            self.headers["Content-Length"] = str(len(body))
        self.headers.update(extra or {})
        self.text = body.decode("utf-8", "replace") if code != 200 else ""

    def iter_content(self, n):
        for i in range(0, len(self._body), n):
            yield self._body[i:i + n]

    def json(self):
        return {}

    def close(self):
        pass


def _get(url, *a, **k):
    CALLS.append((url, (k.get("headers") or {}).get("Authorization", "")))
    seq = ROUTES.get(url)
    if not seq:
        return _Resp(404, b'{"message":"Not found"}', "application/json")
    item = seq.pop(0) if len(seq) > 1 else seq[0]
    if isinstance(item, BaseException):
        raise item
    code, body, ctype, extra = (list(item) + [None] * 4)[:4]
    return _Resp(code, body or b"", ctype or "", extra, length=not (extra or {}).get("_nolen"))


def _post(url, *a, **k):
    CALLS.append((url, "post"))
    return _Resp(200, b"{}", "application/json")


requests.get, requests.post = _get, _post
GS.fetch_lead_dropdowns = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no sheets"))
GS.load_sheet_config_overrides = lambda *a, **k: None

OK, BAD = [], []


def ck(name, cond, got=""):
    (OK if cond else BAD).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else "   ได้: %r" % (got,)))


def line_url(mid):
    return CM.LINE_CONTENT % mid


NOW = timezone.now()
_N = [0]


def line_cust(name, owner=None, awaiting=False):
    _N[0] += 1
    p = LineProfile.objects.create(user_id="U" + ("%032x" % (0xd00000 + _N[0])), display_name=name, msg_count=3,
                                   first_seen=NOW - timedelta(days=9))
    o = ChatOwner.objects.create(profile=p, owner=owner, claimed_at=NOW - timedelta(hours=1) if owner else None,
                                 awaiting_since=(NOW - timedelta(minutes=5)) if awaiting else None,
                                 last_in_at=NOW, last_at=NOW, last_dir="in", team="A")
    return ChatOwner.objects.select_related("profile", "fb_profile", "owner").get(pk=o.pk)


def line_msg(o, mid, typ="image", when=None, channel="crm", direction="in", extra=None, chat_type="user"):
    return GroupChat.objects.create(chat_type=chat_type, group_id="" if chat_type == "user" else "Cgrp" + mid,
                                    message_id=mid, sender_id=o.profile.user_id, msg_type=typ,
                                    text="[รูป]" if typ == "image" else "", has_media=True, channel=channel,
                                    direction=direction, extra=extra or {}, sent_at=when or NOW - timedelta(minutes=1))


def client(user):
    cl = Client()
    if user:
        s_ = SessionStore()
        s_["oxlet_user"] = user
        s_.save()
        cl.cookies[settings.SESSION_COOKIE_NAME] = s_.session_key
    return cl


def body_of(r):
    if hasattr(r, "streaming_content"):
        return b"".join(r.streaming_content)
    return r.content


try:
    C.save_cfg(dict(C.cfg(), anchor_date=timezone.localdate().isoformat(), anchor_team="A", overrides={}))
    MAT = Employee.objects.create(nickname="มัทไฟล์", position="ทีม A", work_start="9:00")
    BIW = Employee.objects.create(nickname="บิวไฟล์", position="ทีม A", work_start="9:00")
    ADM = client({"user_id": "admin", "nickname": "admin", "position": "admin"})
    SM = client({"user_id": "U" + "1" * 32, "nickname": MAT.nickname, "seller_name": MAT.nickname, "position": "seller"})
    SB = client({"user_id": "U" + "2" * 32, "nickname": BIW.nickname, "seller_name": BIW.nickname, "position": "seller"})

    # ─────────────────────────────────────────────────────────
    print("[1] LINE — ใช้ token ของบัญชีที่ได้ยินข้อความ")
    o1 = line_cust("ลูกค้ารูป", owner=MAT)
    m1 = line_msg(o1, "9001", channel="crm")
    ROUTES[line_url("9001")] = [(200, JPG, "image/jpeg")]
    ck("ยังไม่โหลด = state pending", CM.files_json(o1.id, "l", m1)[0]["state"] == "pending")
    tok = CM.ensure("l", m1)
    ck("โหลดสำเร็จ = ok|jpg", tok.startswith("ok|jpg|"), tok)
    ck("ใช้ token บัญชีตัวรับ", CALLS[-1] == (line_url("9001"), "Bearer tok-crm"), CALLS[-1])
    p1 = CM.stored("l", m1, 0)
    ck("ไฟล์อยู่ใน CHAT_MEDIA_ROOT/line", bool(p1) and Path(STORE) / "line" in p1.parents, p1)
    ck("เนื้อไฟล์ครบ", p1 and p1.read_bytes() == JPG)
    ck("ไม่อยู่ใน MEDIA_ROOT (โฟลเดอร์สาธารณะ)", p1 and Path(settings.MEDIA_ROOT) not in p1.parents)
    ck("ไม่มีไฟล์ชั่วคราวค้าง", not list((Path(STORE) / "line").glob("tmp-*")))
    m1.refresh_from_db()
    ck("media_token ถูกบันทึกลงแถว", m1.media_token.startswith("ok|jpg|"), m1.media_token)
    n = len(CALLS)
    CM.ensure("l", m1)
    ck("โหลดแล้วไม่ยิงซ้ำ", len(CALLS) == n)
    fj = CM.files_json(o1.id, "l", m1)[0]
    ck("files_json = ready + image", fj["state"] == "ready" and fj["kind"] == "image" and fj["ext"] == "jpg", fj)
    ck("ลิงก์ผ่าน /connect/api/media", fj["url"] == "/connect/api/media?id=%d&m=l%d.0" % (o1.id, m1.pk), fj["url"])

    m2 = line_msg(o1, "9002", channel="push")
    ROUTES[line_url("9002")] = [(200, PNG, "image/png")]
    CM.ensure("l", m2)
    ck("บัญชีตัวส่ง = token ตัวส่ง", CALLS[-1][1] == "Bearer tok-push", CALLS[-1])
    ck("PNG = png", CM.parse(m2.media_token)[1] == ["png"], m2.media_token)

    m3 = line_msg(o1, "9003", channel="")
    ROUTES[line_url("9003")] = [(400, b'{"message":"bad"}', "application/json"), (200, JPG, "image/jpeg")]
    CM.ensure("l", m3)
    ck("ไม่รู้บัญชี = ลองทุก token จนได้", m3.media_token.startswith("ok|"), m3.media_token)
    ck("ลองตัวรับก่อนแล้วตัวส่ง", [c[1] for c in CALLS[-2:]] == ["Bearer tok-crm", "Bearer tok-push"], CALLS[-2:])

    print("[2] LINE — หมดอายุ/พลาดชั่วคราว/ใหญ่เกิน")
    m4 = line_msg(o1, "9004", channel="")
    ROUTES[line_url("9004")] = [(404, b"{}", "application/json")]
    CM.ensure("l", m4)
    ck("404 ทุก token = gone", m4.media_token.startswith("gone|"), m4.media_token)
    n = len(CALLS)
    CM.ensure("l", m4, refresh=True)
    ck("gone แล้วไม่ยิงซ้ำ", len(CALLS) == n)
    ck("files_json = gone", CM.files_json(o1.id, "l", m4)[0]["state"] == "gone")

    m5 = line_msg(o1, "9005")
    ROUTES[line_url("9005")] = [(401, b"{}", "application/json"), (200, JPG, "image/jpeg")]
    CM.ensure("l", m5)
    ck("401 = err (ลองใหม่ได้)", m5.media_token.startswith("err|"), m5.media_token)
    n = len(CALLS)
    CM.ensure("l", m5)
    ck("err ไม่ถึง 10 นาที = ไม่ยิงซ้ำ", len(CALLS) == n)
    CM.ensure("l", m5, now=time.time() + CM.RETRY_SEC + 5)
    ck("ครบ 10 นาที = ลองใหม่สำเร็จ", m5.media_token.startswith("ok|"), m5.media_token)
    ck("err ยังเป็น pending ในหน้าเว็บ", CM.files_json(o1.id, "l", line_msg(o1, "9005x", channel="crm"))[0]["state"] == "pending")

    m6 = line_msg(o1, "9006")
    ROUTES[line_url("9006")] = [requests.ConnectionError("เน็ตหลุด")]
    CM.ensure("l", m6)
    ck("เน็ตหลุด = err", m6.media_token.startswith("err|"), m6.media_token)

    m7 = line_msg(o1, "9007", typ="video")
    ROUTES[line_url("9007")] = [(200, b"x" * (1024 * 1024 + 10), "video/mp4")]
    CM.ensure("l", m7)
    ck("Content-Length เกินเพดาน = big", m7.media_token.startswith("big|"), m7.media_token)
    m8 = line_msg(o1, "9008", typ="video")
    ROUTES[line_url("9008")] = [(200, b"x" * (1024 * 1024 + 10), "video/mp4", {"_nolen": True})]
    CM.ensure("l", m8)
    ck("ไม่บอกขนาดแต่สตรีมเกิน = big", m8.media_token.startswith("big|"), m8.media_token)
    ck("ไฟล์เกินถูกลบทิ้ง ไม่มีของค้าง", not list((Path(STORE) / "line").glob("%d-*" % m8.pk))
       and not list((Path(STORE) / "line").glob("tmp-*")))
    ck("files_json = big", CM.files_json(o1.id, "l", m8)[0]["state"] == "big")

    m9 = line_msg(o1, "9009", typ="video")
    ROUTES[line_url("9009")] = [(202, b"", "")]
    CM.ensure("l", m9)
    ck("202 (วิดีโอยังไม่พร้อม) = err", m9.media_token.startswith("err|"), m9.media_token)

    print("[3] ชนิดไฟล์ — รูปต้องดูไบต์จริง · svg/html ห้ามเปิดในเบราว์เซอร์")
    ma = line_msg(o1, "9010")
    ROUTES[line_url("9010")] = [(200, HTML, "image/jpeg")]
    CM.ensure("l", ma)
    ck("บอกว่า jpeg แต่ไบต์เป็น HTML = bin", CM.parse(ma.media_token)[1] == ["bin"], ma.media_token)
    ck("ไม่นับเป็นรูปในหน้าเว็บ", CM.files_json(o1.id, "l", ma)[0]["kind"] == "file")
    mb = line_msg(o1, "9011", typ="file", extra={"fileName": "รูป.svg", "fileSize": len(SVG)})
    ROUTES[line_url("9011")] = [(200, SVG, "image/svg+xml")]
    CM.ensure("l", mb)
    ck("svg ไม่ได้นามสกุลที่เปิดในเบราว์เซอร์", CM.parse(mb.media_token)[1][0] not in CM.INLINE_TYPES, mb.media_token)
    mc = line_msg(o1, "9012", typ="file", extra={"fileName": "สัญญา.pdf", "fileSize": len(PDF)})
    ROUTES[line_url("9012")] = [(200, PDF, "application/octet-stream")]
    CM.ensure("l", mc)
    ck("pdf ดูจากไบต์ = pdf", CM.parse(mc.media_token)[1] == ["pdf"], mc.media_token)
    fj = CM.files_json(o1.id, "l", mc)[0]
    ck("ชื่อไฟล์/ขนาดมาจาก LINE", fj["name"] == "สัญญา.pdf" and fj["size"] == len(PDF), fj)
    md = line_msg(o1, "9013", typ="file", extra={"fileName": "ใบเสนอราคา.docx"})
    ROUTES[line_url("9013")] = [(200, b"PK\x03\x04" + b"x" * 50, "application/octet-stream")]
    CM.ensure("l", md)
    ck("docx เก็บตามชื่อไฟล์", CM.parse(md.media_token)[1] == ["docx"], md.media_token)
    me = line_msg(o1, "9014", typ="audio")
    ROUTES[line_url("9014")] = [(200, b"\x00\x00\x00\x18ftypM4A " + b"x" * 40, "audio/x-m4a")]
    CM.ensure("l", me)
    ck("เสียง = m4a", CM.parse(me.media_token)[1] == ["m4a"], me.media_token)

    print("[4] Facebook — เฉพาะโดเมน FB · redirect ออกนอก FB ไม่ตาม")
    fp = FbProfile.objects.create(user_id="psid-1", display_name="ลูกค้าเฟซ", channel="111", thread_id="t_1")
    of = ChatOwner.objects.create(fb_profile=fp, owner=MAT, claimed_at=NOW, last_at=NOW, last_in_at=NOW, team="A")
    of = ChatOwner.objects.select_related("profile", "fb_profile", "owner").get(pk=of.pk)
    A1, A2 = "https://scontent.xx.fbcdn.net/v/a.jpg?sig=1", "https://cdn.fbsbx.com/v/doc.pdf?sig=2"
    f1 = FbChat.objects.create(thread_id="t_1", message_id="m_f1", sender_id="psid-1", msg_type="image", text="",
                               has_media=True, channel="111", direction="in", sent_at=NOW - timedelta(minutes=2),
                               extra={"attachments": {"data": [{"image_data": {"url": A1}},
                                                               {"file_url": A2, "name": "ใบขับขี่.pdf",
                                                                "mime_type": "application/pdf"}]}})
    ROUTES[A1] = [(200, JPG, "image/jpeg")]
    ROUTES[A2] = [(200, PDF, "application/pdf")]
    ck("ไฟล์แนบ 2 ชิ้น", len(CM.attachments("f", f1)) == 2)
    CM.ensure("f", f1)
    ck("FB 2 ไฟล์ = ok|jpg,pdf", f1.media_token.startswith("ok|jpg,pdf|"), f1.media_token)
    ck("FB ไม่ส่ง token ไปด้วย", all(c[1] == "" for c in CALLS if c[0] in (A1, A2)))
    fjs = CM.files_json(of.id, "f", f1)
    ck("files_json FB 2 ชิ้น", [x["kind"] for x in fjs] == ["image", "file"] and fjs[1]["name"] == "ใบขับขี่.pdf", fjs)

    EVIL = "https://evil.example.com/a.jpg"
    f2 = FbChat.objects.create(thread_id="t_1", message_id="m_f2", sender_id="psid-1", msg_type="image",
                               has_media=True, channel="111", direction="in", sent_at=NOW - timedelta(minutes=1),
                               extra={"attachments": [{"type": "image", "url": EVIL}]})
    CM.ensure("f", f2)
    ck("ลิงก์นอกโดเมน FB = ไม่ยิง", not any(c[0] == EVIL for c in CALLS))
    ck("ลิงก์นอกโดเมน FB = none", f2.media_token.startswith("none|"), f2.media_token)

    R1 = "https://lookaside.fbsbx.com/r1"
    f3 = FbChat.objects.create(thread_id="t_1", message_id="m_f3", sender_id="psid-1", msg_type="image",
                               has_media=True, channel="111", direction="in", sent_at=NOW,
                               extra={"attachments": [{"type": "image", "url": R1}]})
    ROUTES[R1] = [(302, b"", "", {"Location": EVIL})]
    CM.ensure("f", f3)
    ck("redirect ออกนอก FB = ไม่ตาม", not any(c[0] == EVIL for c in CALLS))
    ck("redirect ออกนอก FB = gone", f3.media_token.startswith("gone|"), f3.media_token)
    R2, R2T = "https://lookaside.fbsbx.com/r2", "https://scontent.fbcdn.net/real.jpg"
    f4 = FbChat.objects.create(thread_id="t_1", message_id="m_f4", sender_id="psid-1", msg_type="image",
                               has_media=True, channel="111", direction="in", sent_at=NOW,
                               extra={"attachments": [{"type": "image", "url": R2}]})
    ROUTES[R2] = [(302, b"", "", {"Location": R2T})]
    ROUTES[R2T] = [(200, JPG, "image/jpeg")]
    CM.ensure("f", f4)
    ck("redirect ไปโดเมน FB = ตามไปโหลด", f4.media_token.startswith("ok|jpg"), f4.media_token)
    ck("http (ไม่ใช่ https) ไม่นับเป็นโดเมน FB", not CM._fb_url_ok("http://scontent.fbcdn.net/a.jpg"))
    ck("โดเมนปลอมที่ลงท้ายคล้าย ไม่ผ่าน", not CM._fb_url_ok("https://evilfbcdn.net/a.jpg"))
    f5 = FbChat.objects.create(thread_id="t_1", message_id="m_f5", sender_id="psid-1", msg_type="image",
                               has_media=True, channel="111", direction="in", sent_at=NOW,
                               extra={"attachments": [{"type": "image", "url": "https://scontent.fbcdn.net/old.jpg"}]})
    ROUTES["https://scontent.fbcdn.net/old.jpg"] = [(403, b"expired", "text/plain")]
    CM.ensure("f", f5, refresh=True)
    ck("ลิงก์หมดอายุ + ขอใหม่ไม่ได้ = gone (ไม่พัง)", f5.media_token.startswith("gone|"), f5.media_token)

    print("[5] เปิดไฟล์ผ่าน /connect/api/media — สิทธิ์ + header")
    u1 = "/connect/api/media?id=%d&m=l%d.0" % (o1.id, m1.pk)
    r = ADM.get(u1, secure=True)
    ck("แอดมินเปิดได้ 200", r.status_code == 200, r.status_code)
    ck("เนื้อไฟล์ถูก", body_of(r) == JPG)
    ck("ชนิด image/jpeg", r["Content-Type"] == "image/jpeg", r["Content-Type"])
    ck("nosniff", r.get("X-Content-Type-Options") == "nosniff")
    ck("cache แบบ private", "private" in (r.get("Cache-Control") or ""), r.get("Cache-Control"))
    ck("CSP sandbox", "sandbox" in (r.get("Content-Security-Policy") or ""))
    ck("เปิดในเบราว์เซอร์ (inline)", "attachment" not in (r.get("Content-Disposition") or ""), r.get("Content-Disposition"))
    r = SM.get(u1, secure=True)
    ck("เจ้าของลูกค้าเปิดได้", r.status_code == 200, r.status_code)
    r = SB.get(u1, secure=True)
    ck("เซลล์คนอื่นเปิดไม่ได้ 403", r.status_code == 403, r.status_code)
    r = client(None).get(u1, secure=True)
    ck("ไม่ login = 401", r.status_code == 401, r.status_code)
    r = ADM.get(u1 + "&dl=1", secure=True)
    ck("dl=1 = ดาวน์โหลด", "attachment" in (r.get("Content-Disposition") or ""), r.get("Content-Disposition"))
    r = ADM.get("/connect/api/media?id=%d&m=l%d.0" % (o1.id, mb.pk), secure=True)
    ck("svg = ดาวน์โหลดเสมอ + octet-stream", r.status_code == 200 and "attachment" in r.get("Content-Disposition", "")
       and r["Content-Type"] == "application/octet-stream", (r.status_code, r.get("Content-Type")))
    r = ADM.get("/connect/api/media?id=%d&m=l%d.0" % (o1.id, ma.pk), secure=True)
    ck("HTML ที่แอบอ้างเป็นรูป = ดาวน์โหลด", "attachment" in r.get("Content-Disposition", ""), r.get("Content-Disposition"))
    r = ADM.get("/connect/api/media?id=%d&m=l%d.0" % (o1.id, mc.pk), secure=True)
    ck("pdf เปิดในเบราว์เซอร์ได้", r["Content-Type"] == "application/pdf" and "attachment" not in r.get("Content-Disposition", ""),
       (r.get("Content-Type"), r.get("Content-Disposition")))
    ck("ชื่อไฟล์ไทยไม่พัง", "filename*=utf-8''" in r.get("Content-Disposition", "").lower(), r.get("Content-Disposition"))

    o2 = line_cust("ลูกค้าอีกคน", owner=MAT)
    r = ADM.get("/connect/api/media?id=%d&m=l%d.0" % (o2.id, m1.pk), secure=True)
    ck("ข้อความของลูกค้าคนอื่น = 404", r.status_code == 404, r.status_code)
    r = ADM.get("/connect/api/media?id=%d&m=f%d.0" % (o1.id, f1.pk), secure=True)
    ck("ไฟล์ FB ผ่านลูกค้า LINE = 404", r.status_code == 404, r.status_code)
    r = ADM.get("/connect/api/media?id=%d&m=l%d.5" % (o1.id, m1.pk), secure=True)
    ck("ลำดับไฟล์เกิน = 404", r.status_code == 404, r.status_code)
    for bad in ("x1.0", "l1", "l1.0.0", "../l1.0", "l-1.0"):
        r = ADM.get("/connect/api/media?id=%d&m=%s" % (o1.id, bad), secure=True)
        if r.status_code != 400:
            break
    ck("ระบุไฟล์ผิดรูปแบบ = 400", r.status_code == 400, (bad, r.status_code))
    grp = line_msg(o1, "9020", chat_type="group")
    ROUTES[line_url("9020")] = [(200, JPG, "image/jpeg")]
    r = ADM.get("/connect/api/media?id=%d&m=l%d.0" % (o1.id, grp.pk), secure=True)
    ck("ข้อความในกลุ่ม LINE ไม่เปิดผ่านแชทลูกค้า", r.status_code == 404, r.status_code)

    r = ADM.get("/connect/api/media?id=%d&m=l%d.0" % (o1.id, m4.pk), secure=True)
    js = json.loads(r.content)
    ck("หมดอายุ = 410 + บอกเหตุผล", r.status_code == 410 and js.get("state") == "gone" and "LINE" in js.get("error", ""), (r.status_code, js))

    mn = line_msg(o1, "9021")
    ROUTES[line_url("9021")] = [(200, JPG, "image/jpeg")]
    r = ADM.get("/connect/api/media?id=%d&m=l%d.0" % (o1.id, mn.pk), secure=True)
    ck("ยังไม่โหลด = โหลดตอนเปิดเลย", r.status_code == 200 and body_of(r) == JPG, r.status_code)

    r = SM.get("/connect/api/media?id=%d&m=f%d.1" % (of.id, f1.pk), secure=True)
    ck("FB ไฟล์ที่ 2 (pdf) เจ้าของเปิดได้", r.status_code == 200 and body_of(r) == PDF, r.status_code)

    print("[6] คิวรอรับ (preview) — เปิดได้เฉพาะไฟล์ที่ลูกค้าเพิ่งส่ง")
    oq = line_cust("ลูกค้ารอรับ", awaiting=True)
    old = line_msg(oq, "9030", when=NOW - timedelta(hours=3))
    new = line_msg(oq, "9031", when=NOW - timedelta(minutes=1))
    ROUTES[line_url("9030")] = [(200, JPG, "image/jpeg")]
    ROUTES[line_url("9031")] = [(200, JPG, "image/jpeg")]
    r = SB.get("/connect/api/media?id=%d&m=l%d.0" % (oq.id, new.pk), secure=True)
    ck("เซลล์เวรวันนี้เปิดรูปที่ลูกค้าเพิ่งส่งได้", r.status_code == 200, r.status_code)
    r = SB.get("/connect/api/media?id=%d&m=l%d.0" % (oq.id, old.pk), secure=True)
    ck("รูปเก่าก่อนเริ่มรอบ = 403 (ต้องรับลูกค้าก่อน)", r.status_code == 403, r.status_code)
    r = ADM.get("/connect/api/media?id=%d&m=l%d.0" % (oq.id, old.pk), secure=True)
    ck("แอดมินเปิดรูปเก่าได้", r.status_code == 200, r.status_code)
    C.save_cfg(dict(C.cfg(), anchor_team="B"))
    r = SB.get("/connect/api/media?id=%d&m=l%d.0" % (oq.id, new.pk), secure=True)
    ck("ไม่ใช่วันเวรทีม = 403", r.status_code == 403, r.status_code)
    C.save_cfg(dict(C.cfg(), anchor_team="A"))

    print("[7] ข้อความในหน้าแชทมีลิงก์ไฟล์ · ไม่มี LINE id หลุด")
    msgs = C.messages(o1)
    withf = [x for x in msgs if x.get("files")]
    ck("ข้อความมีรูปมีช่อง files", len(withf) >= 10, len(withf))
    ck("ข้อความไม่มีรูป = files ว่าง", all(not x.get("files") for x in msgs if not x.get("media")))
    leak = re.compile(r"U[0-9a-f]{32}")
    ck("ลิงก์ไม่มี LINE user id", not any(leak.search(f["url"]) for x in withf for f in x["files"]))
    r = ADM.get("/connect/api/chat?id=%d" % o1.id, secure=True)
    txt = r.content.decode("utf-8", "replace")
    ck("api_chat ส่ง files มาด้วย", r.status_code == 200 and '"files"' in txt and "/connect/api/media" in txt, r.status_code)
    fm = C.messages(of)
    ck("แชท FB ก็มี files", any(x.get("files") for x in fm))

    print("[8] รอบกวาด · ลบไฟล์ของแชทที่หมดอายุ")
    sw = line_cust("ลูกค้ากวาด", owner=BIW)
    s1 = line_msg(sw, "9040", when=NOW - timedelta(days=1))
    s2 = line_msg(sw, "9041", when=NOW - timedelta(days=20))        # เก่ากว่า 7 วัน = รอบอัตโนมัติไม่แตะ
    s3 = line_msg(sw, "9042", direction="out")                       # ขาออก = ไม่ใช่ไฟล์ลูกค้า
    s4 = line_msg(sw, "9043", chat_type="group")                    # แชทกลุ่ม = ไม่ใช่ลูกค้า
    for mid in ("9040", "9041", "9042", "9043"):
        ROUTES[line_url(mid)] = [(200, JPG, "image/jpeg")]
    pend = {(s, r.pk) for s, r in CM.pending(CM.PREFETCH_DAYS, 500)}
    ck("pending มีข้อความใหม่", ("l", s1.pk) in pend)
    ck("pending ไม่มีของเก่าเกิน 7 วัน", ("l", s2.pk) not in pend)
    ck("pending ไม่มีขาออก/แชทกลุ่ม", ("l", s3.pk) not in pend and ("l", s4.pk) not in pend)
    res = CM.sweep()
    s1.refresh_from_db()
    ck("รอบกวาดโหลดของใหม่", s1.media_token.startswith("ok|"), (s1.media_token, res))
    ck("รอบกวาดนับผล", res.get("ok", 0) >= 1 and "sec" in res, res)
    ck("ไม่มีเหลือในรอบถัดไป", ("l", s1.pk) not in {(s, r.pk) for s, r in CM.pending(CM.PREFETCH_DAYS, 500)})
    ck("sweep_bg ปิดในเทสต์ = ไม่ทำอะไร", CM.sweep_bg() == {})

    gone_pk = s1.pk
    p = CM.stored("l", s1, 0)
    orphan = Path(STORE) / "line" / "999999-0.jpg"
    orphan.write_bytes(JPG)
    tmp = Path(STORE) / "line" / "tmp-old"
    tmp.write_bytes(b"x")
    os.utime(tmp, (time.time() - 7200, time.time() - 7200))
    GroupChat.objects.filter(pk=gone_pk).delete()                   # แชทหมดอายุถูกลบ
    res = CM.cleanup_files()
    ck("ลบไฟล์ของแชทที่ถูกลบ", p is not None and not p.exists(), res)
    ck("ลบไฟล์กำพร้า", not orphan.exists())
    ck("ลบไฟล์ชั่วคราวเก่า", not tmp.exists())
    ck("ไฟล์ของแชทที่ยังอยู่ไม่โดนลบ", CM.stored("l", m1, 0) is not None)
    ck("นับผลลบ", res["deleted"] >= 3 and res["kept"] >= 1, res)

    print("[9] คำสั่ง chat_media")
    out = os.path.join(STORE, "report.txt")
    call_command("chat_media", fetch=True, days=60, out=out)
    rep = open(out, encoding="utf-8").read()
    s2.refresh_from_db()
    ck("--fetch โหลดของเก่าเกิน 7 วันด้วย", s2.media_token.startswith("ok|"), s2.media_token)
    ck("รายงานมีสรุปตามอายุข้อความ", "ผลตามอายุข้อความ" in rep and "LINE" in rep, rep[:300])
    ck("รายงานมีสถานะรวม", "สถานะไฟล์ในแชทลูกค้า" in rep and "โหลดแล้ว" in rep, rep[-400:])
    call_command("chat_media", out=out)
    ck("ไม่มีตัวเลือก = แค่ดูสถานะ", "สถานะไฟล์" in open(out, encoding="utf-8").read())

    print("[10] หน้าสถานะระบบร้องเมื่อโหลดไม่ได้ทั้งรอบ")
    from dashboard.services import cache_store
    from dashboard.services import fetch_dashboard as FD
    FD.fetch_dashboard_data = lambda *a, **k: {}          # ไม่ยิง Google

    def health_msgs():
        r_ = ADM.get("/api/admin/system_health", secure=True)
        return r_.status_code, [i["msg"] for i in json.loads(r_.content).get("issues", []) if "รูป/ไฟล์ที่ลูกค้าส่ง" in i["msg"]]

    cache_store.set_kv(CM.LAST_KEY, {"tried": 30, "ok": 0, "err": 30, "at": timezone.now().isoformat()})
    code, hm = health_msgs()
    ck("พลาดทั้งรอบ = ร้อง", code == 200 and len(hm) == 1 and "chat_media" in hm[0], (code, hm))
    cache_store.set_kv(CM.LAST_KEY, {"tried": 30, "ok": 25, "err": 5, "at": timezone.now().isoformat()})
    ck("สำเร็จบ้าง = ไม่ร้อง", health_msgs()[1] == [])
    cache_store.set_kv(CM.LAST_KEY, {"tried": 30, "ok": 0, "err": 30,
                                     "at": (timezone.now() - timedelta(hours=5)).isoformat()})
    ck("เก่าเกิน 2 ชม. = ไม่ร้อง (หายแล้วไม่ค้างเตือน)", health_msgs()[1] == [])

    print("[11] tick ไม่พังเมื่อมีรอบกวาด")
    try:
        res = C.tick()
        ck("connect.tick ทำงานได้", isinstance(res, dict), res)
    except Exception as e:
        ck("connect.tick ทำงานได้", False, e)

    print("[12] ลูกค้าส่ง QR / ลิงก์ LINE = ช่องทางติดต่อ → เข้าห้องพัก Lead (lead_qr · อ่านในเครื่อง)")
    import random

    import qrcode
    from PIL import Image

    from checkout import lead_qr as LQ

    def shot(payload=None, size=(1080, 1900), seed=1):
        """ภาพหน้าจอมือถือจำลอง: พื้นเทา + แถบ + QR กลางจอ (ไม่มี payload = รูปถ่ายธรรมดาไม่มี QR)"""
        rnd = random.Random(seed)
        im = Image.new("RGB", size, (236, 236, 236))
        px = im.load()
        for _ in range(6000):                                  # จุดรบกวนเล็กๆ ให้ไม่ใช่ภาพเรียบเกินจริง
            px[rnd.randrange(size[0]), rnd.randrange(size[1])] = (rnd.randrange(256),) * 3
        if payload:
            q = qrcode.make(payload).convert("RGB").resize((520, 520))
            im.paste(q, ((size[0] - 520) // 2, 600))
        b = io.BytesIO()
        im.save(b, "PNG")
        return b.getvalue()

    ck("มีไลบรารีอ่าน QR (zxing-cpp)", LQ._lib(), "pip install zxing-cpp==3.1.1")
    # ── อ่านลิงก์ ──
    ck("ลิงก์ ID (~) = ได้ ID", LQ.line_contact("https://line.me/ti/p/~somchai_99") == "somchai_99")
    ck("ลิงก์ QR (โทเคน) = ได้ลิงก์", LQ.line_contact("ส่งข้อความและโทรฟรีด้วย LINE กันเถอะ https://line.me/ti/p/AbCd3f9xYz")
       == "line.me/ti/p/AbCd3f9xYz")
    ck("ลิงก์บัญชีทางการ (@) ไม่นับ", LQ.line_contact("https://line.me/R/ti/p/@693tyhah") == "")
    ck("ลิงก์บัญชีทางการ (%40) ไม่นับ", LQ.line_contact("https://line.me/R/ti/p/%40693tyhah") == "")
    ck("ลิงก์กลุ่มไม่นับ", LQ.line_contact("https://line.me/R/ti/g/AbCdEfGh12") == "")
    ck("lin.ee (ลิงก์ย่อของร้าน) ไม่นับ", LQ.line_contact("https://lin.ee/AbCd123") == "")
    ck("ข้อความทั่วไปไม่นับ", LQ.line_contact("สนใจ civic ครับ line ผมเดี๋ยวส่งให้") == "")
    ph, ids = C.contacts_in([{"dir": "in", "text": "ติดต่อมาไลน์นี้เลยครับ https://line.me/ti/p/AbCd3f9xYz"}])
    ck("contacts_in: ลิงก์แชร์ LINE ที่ลูกค้าแปะ = ช่องทางติดต่อ", ids == ["line.me/ti/p/AbCd3f9xYz"], ids)
    ph, ids = C.contacts_in([{"dir": "out", "text": "แอดไลน์ร้านได้ที่ https://line.me/ti/p/AbCd3f9xYz"}])
    ck("contacts_in: ลิงก์ที่เราพิมพ์เองไม่นับ", ids == [], ids)
    # ── อ่าน QR ในรูป ──
    tmpq = Path(STORE) / "q_test.png"
    tmpq.write_bytes(shot("https://line.me/ti/p/AbCd3f9xYz"))
    ck("อ่าน QR LINE จากภาพหน้าจอได้", LQ.contact_in_image(tmpq) == "line.me/ti/p/AbCd3f9xYz", LQ.decode(tmpq))
    tmpq.write_bytes(shot("00020101021129370016A000000677010111011300668123456785802TH53037646304ABCD"))
    ck("QR พร้อมเพย์ (สลิป) ไม่นับ", LQ.decode(tmpq) and LQ.contact_in_image(tmpq) == "", LQ.decode(tmpq))
    tmpq.write_bytes(shot(None))
    ck("รูปถ่ายไม่มี QR = ไม่มีอะไร", LQ.decode(tmpq) == [])
    tmpq.write_bytes(b"not an image")
    ck("ไฟล์เสีย = ไม่พัง", LQ.decode(tmpq) == [])

    def qr_case(name, payload, prep=None, awaiting=True):
        o_ = line_cust(name, awaiting=awaiting)
        if prep:
            prep(o_)
        mid = "qr-" + name
        m_ = line_msg(o_, mid)
        ROUTES[line_url(mid)] = [(200, shot(payload), "image/png")]
        CM.ensure("l", m_)
        o_ = ChatOwner.objects.select_related("profile", "fb_profile", "owner", "lead").get(pk=o_.pk)
        return o_, C.lead_of(o_, create=False)

    def tocode_ids():
        return set(C.to_code(ChatOwner.objects.all()).values_list("id", flat=True))

    oq, lq = qr_case("ส่งQR", "https://line.me/ti/p/AbCd3f9xYz")
    ck("★ ส่งรูป QR LINE → ได้ ID LINE ในข้อมูลลีด", lq and lq.line_id == "line.me/ti/p/AbCd3f9xYz", lq and lq.line_id)
    ck("ป้ายที่มา = รูป QR", lq and (lq.auto or {}).get("line_id") == C.QR_SRC and (lq.auto or {}).get("_qr", {}).get("msg"),
       lq and lq.auto)
    ck("★ เข้าห้องพัก Lead ทันที (ไม่ต้องรอแอดมินเปิดแชท)", oq.id in tocode_ids())
    rj = C.row_json(oq)
    ck("รายชื่อ: contact = qr (ป้าย 'รอจ่ายเบอร์ · QR')", rj.get("contact") == "qr" and rj.get("nocode") is False, rj.get("contact"))
    oi, li = qr_case("ส่งQRไอดี", "https://line.me/ti/p/~somchai_99")
    ck("QR แบบมี ID = ได้ ID เปล่า", li and li.line_id == "somchai_99", li and li.line_id)
    oa, la = qr_case("ส่งQRร้าน", "https://line.me/R/ti/p/@693tyhah")
    ck("QR บัญชีทางการ (ลูกค้าส่ง QR ร้านกลับมา) = ไม่นับ", not (la and la.line_id) and oa.id not in tocode_ids(),
       la and la.line_id)
    op, lp = qr_case("ส่งรูปรถ", None)
    ck("รูปรถ/เล่มทะเบียน (ไม่มี QR) = ไม่ใช่ลีด ไม่สร้างข้อมูลลีดเปล่า", lp is None and op.id not in tocode_ids(), lp)

    def human_cleared(o_):
        ld = C.lead_of(o_)
        ld.auto = {"line_id": C.HUMAN}
        ld.save()
    oh, lh = qr_case("คนลบเอง", "https://line.me/ti/p/AbCd3f9xYz", prep=human_cleared)
    ck("คนลบช่อง ID LINE เองแล้ว = ระบบไม่เติมกลับ", lh and lh.line_id == "", lh and lh.line_id)

    def has_id(o_):
        ld = C.lead_of(o_)
        ld.line_id = "mine_typed"
        ld.save()
    ok_, lk = qr_case("มีไอดีแล้ว", "https://line.me/ti/p/AbCd3f9xYz", prep=has_id)
    ck("มี ID LINE อยู่แล้ว = ไม่ทับ", lk and lk.line_id == "mine_typed", lk and lk.line_id)

    print("     FB: ลูกค้าเพจส่ง QR LINE มา")
    fq = FbProfile.objects.create(user_id="psid-qr", display_name="เฟซส่งQR", channel="111", thread_id="t_qr")
    ofq = ChatOwner.objects.create(fb_profile=fq, last_at=NOW, last_in_at=NOW, team="A", awaiting_since=NOW)
    AQ = "https://scontent.xx.fbcdn.net/v/qr.png?sig=9"
    fm = FbChat.objects.create(thread_id="t_qr", message_id="m_fqr", sender_id="psid-qr", msg_type="image", text="",
                               has_media=True, channel="111", direction="in", sent_at=NOW,
                               extra={"attachments": [{"type": "image", "url": AQ}]})
    ROUTES[AQ] = [(200, shot("https://line.me/ti/p/~fbcust_1"), "image/png")]
    CM.ensure("f", fm)
    lfq = C.lead_of(ChatOwner.objects.get(pk=ofq.pk), create=False)
    ck("FB: QR ในรูป → ได้ ID LINE", lfq and lfq.line_id == "fbcust_1", lfq and lfq.line_id)

    print("     ไม่มีไลบรารี = ข้ามเงียบ ไม่ทำให้การโหลดรูปพัง · แล้วย้อนอ่านด้วย chat_media --qr")
    LQ.STATE["lib"] = False
    ob, lb = qr_case("ก่อนติดตั้ง", "https://line.me/ti/p/Back12fill")
    mb = GroupChat.objects.get(message_id="qr-ก่อนติดตั้ง")
    ck("ไม่มีไลบรารี: รูปยังโหลดได้ตามปกติ", mb.media_token.startswith("ok|png"), mb.media_token)
    ck("ไม่มีไลบรารี: ไม่เติมอะไร", not (lb and lb.line_id))
    LQ.STATE["lib"] = None
    out2 = os.path.join(STORE, "qr_rep.txt")
    call_command("chat_media", qr=True, days=7, out=out2)
    rep2 = open(out2, encoding="utf-8").read()
    lb = C.lead_of(ChatOwner.objects.get(pk=ob.pk), create=False)
    ck("★ chat_media --qr ย้อนอ่านรูปเก่าแล้วเติมให้", lb and lb.line_id == "line.me/ti/p/Back12fill", lb and lb.line_id)
    ck("รายงาน --qr บอกจำนวนที่เติม", "เติม ID LINE จากรูป QR: 1 ราย" in rep2, rep2[-300:])
    ck("รายงานไม่มีค่า ID LINE/ลิงก์ของลูกค้า", "Back12fill" not in rep2 and "line.me" not in rep2)
    call_command("chat_media", qr=True, days=7, out=out2)
    ck("รันซ้ำ = ไม่เติมซ้ำ", "เติม ID LINE จากรูป QR: 0 ราย" in open(out2, encoding="utf-8").read())

    r_ = ADM.get("/connect/api/inbox?view=all", secure=True)
    rows_ = {x["id"]: x for x in json.loads(r_.content).get("rows", [])}
    ck("API รายชื่อส่ง contact/nocode", oq.id in rows_ and rows_[oq.id].get("contact") == "qr"
       and rows_.get(op.id, {}).get("contact", "") == "", (rows_.get(oq.id, {}).get("contact"), rows_.get(op.id, {}).get("contact")))
    ck("หน้าเว็บมีป้าย 'รอจ่ายเบอร์'", "รอจ่ายเบอร์" in open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "checkout", "templates", "checkout", "connect.html"), encoding="utf-8").read())

finally:
    _runner.teardown_databases(_old)
    shutil.rmtree(STORE, ignore_errors=True)

print("\nผ่าน %d · ไม่ผ่าน %d" % (len(OK), len(BAD)))
if BAD:
    print("ไม่ผ่าน:", BAD)
    sys.exit(1)
