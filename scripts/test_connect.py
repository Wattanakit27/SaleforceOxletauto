# -*- coding: utf-8 -*-
"""เทสต์ Connect — ห้องแชทลูกค้ารวม (3 ต.ค.69)

    python scripts/test_connect.py

ใช้ฐานข้อมูลทดสอบแยก (สร้างใหม่ทุกครั้ง) · **ปลอมที่ขอบระบบ** (`requests` = LINE/Google)
ไม่ปลอมฟังก์ชันของเราเอง — บทเรียนเดิม: ปลอมทั้งฟังก์ชัน = ไม่ได้ทดสอบฟังก์ชันนั้นเลย
"""
import io
import json
import os
import re
import sys
from datetime import date, datetime, timedelta

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

import requests  # noqa: E402
from django.contrib.sessions.backends.signed_cookies import SessionStore  # noqa: E402
from django.test import Client  # noqa: E402
from django.utils import timezone  # noqa: E402

from checkout import connect as C  # noqa: E402
C.BG_FILL = False            # ไม่ให้ thread เติมรูปวิ่งชนฐานข้อมูลทดสอบ (เรียก fill_pictures ตรงๆ แทน)
from checkout.models import ChatOwner, ChatOwnerLog, Employee, GroupChat, LineProfile  # noqa: E402
from dashboard.services import cache_store  # noqa: E402

# ── ขอบระบบ: LINE + Google (ห้ามออกเน็ตจริงในเทสต์) ──────────────────────
CALLS = []


class _R:
    def __init__(self, code=200, js=None):
        self.status_code, self._js = code, (js or {})
        self.text = json.dumps(self._js)
        self.headers = {}

    def json(self):
        return self._js

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError("HTTP %s" % self.status_code)


POST_CODE = [200]


def _post(url, *a, **k):
    CALLS.append(("post", url, k.get("json")))
    return _R(POST_CODE[0], {} if POST_CODE[0] == 200 else {"message": "Invalid to"})


PROFILE_OK = [False]          # True = LINE ตอบโปรไฟล์ลูกค้า (มีรูป) · False = 404 (เช่นลูกค้าบล็อกบอท)
FAKE_PIC = "https://profile.line-scdn.net/0hFAKEPICTURE"


SHEET_ROUTE = [None]          # ฟังก์ชันตอบ Google Sheets API ปลอม (ตั้งเฉพาะช่วงที่ทดสอบอ่าน dropdown ของชีตลีด)


def _get(url, *a, **k):
    CALLS.append(("get", url, None))
    if SHEET_ROUTE[0] and "sheets.googleapis.com" in url:
        return SHEET_ROUTE[0](url)
    if PROFILE_OK[0] and "/v2/bot/profile/" in url:
        return _R(200, {"displayName": "ชื่อใหม่ใน LINE", "pictureUrl": FAKE_PIC,
                        "statusMessage": "หารถให้ครอบครัว", "language": "th"})
    return _R(404, {"message": "Not found"})


requests.post, requests.get = _post, _get
import dashboard.services.google_sheets as _GS  # noqa: E402


def _no_sheet(*a, **k):
    raise RuntimeError("ไม่ต่อ Google Sheets ในเทสต์")


_GS.fetch_sheet = _no_sheet
# dropdown ของชีตลีด: ปกติ "อ่านไม่ได้" (ฟอร์มใช้ชุดที่จำไว้ DD_FALLBACK) · ส่วน [19] ใช้ตัวจริงกับ Sheets API ปลอม
_REAL_FLD = _GS.fetch_lead_dropdowns
_GS.fetch_lead_dropdowns = _no_sheet

OK, BAD = [], []


def ck(name, cond, got=""):
    (OK if cond else BAD).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else "   ได้: %r" % (got,)))


TZ = timezone.get_current_timezone()


def at(y, mo, d, hh, mm=0):
    return timezone.make_aware(datetime(y, mo, d, hh, mm), TZ)


def pushes():
    return [c for c in CALLS if c[0] == "post" and "/message/push" in c[1]]


try:
    # ═════════════════════════════════════════════════════════════════════
    print("[1] เวรวันเว้นวัน")
    c = dict(C.DEFAULTS, anchor_date="2026-10-01", anchor_team="A", overrides={})
    ck("1 ต.ค. = A (วันตั้งต้น)", C.duty_team(date(2026, 10, 1), c) == "A")
    ck("2 ต.ค. = B", C.duty_team(date(2026, 10, 2), c) == "B")
    ck("3 ต.ค. = A", C.duty_team(date(2026, 10, 3), c) == "A")
    ck("30 ก.ย. (ก่อนวันตั้งต้น) = B", C.duty_team(date(2026, 9, 30), c) == "B")
    ck("ข้ามเดือน 1 พ.ย. (31 วันถัดมา) = B", C.duty_team(date(2026, 11, 1), c) == "B")
    c2 = dict(c, overrides={"2026-10-04": "A"})
    ck("สลับเวรเฉพาะวัน 4 ต.ค. → A", C.duty_team(date(2026, 10, 4), c2) == "A")
    ck("สลับเวรไม่ลามไปวันถัดไป (5 ต.ค. = A ตามสูตร)", C.duty_team(date(2026, 10, 5), c2) == "A")
    ck("วันถัดจากวันสลับยังเดินตามสูตร (6 ต.ค. = B)", C.duty_team(date(2026, 10, 6), c2) == "B")
    c3 = dict(c, teams=["A", "B", "C"])
    ck("3 ทีมหมุนเวียน", [C.duty_team(date(2026, 10, d), c3) for d in (1, 2, 3, 4)] == ["A", "B", "C", "A"])

    # ═════════════════════════════════════════════════════════════════════
    print("[2] เส้นตาย 5 นาที (นับเฉพาะเวลาทำการ)")
    c = dict(C.DEFAULTS, sla_min=5, open="08:30", close="20:00")
    ck("10:00 → 10:05", C.due_for(at(2026, 10, 3, 10), c) == at(2026, 10, 3, 10, 5))
    ck("ทักก่อนเปิด 07:00 → 08:35", C.due_for(at(2026, 10, 3, 7), c) == at(2026, 10, 3, 8, 35))
    ck("ทักหลังปิด 21:00 → พรุ่งนี้ 08:35", C.due_for(at(2026, 10, 3, 21), c) == at(2026, 10, 4, 8, 35))
    ck("ตี 2 → 08:35 วันเดียวกัน", C.due_for(at(2026, 10, 4, 2), c) == at(2026, 10, 4, 8, 35))
    ck("19:58 → 20:03 (เลยเวลาปิดได้ ไม่ตัดทิ้ง)", C.due_for(at(2026, 10, 3, 19, 58), c) == at(2026, 10, 3, 20, 3))
    c24 = dict(c, open="00:00", close="00:00")
    ck("ตั้งเปิด=ปิด = นับ 24 ชม. (ตี 3 → 03:05)", C.due_for(at(2026, 10, 3, 3), c24) == at(2026, 10, 3, 3, 5))

    # ═════════════════════════════════════════════════════════════════════
    print("[3] ตรวจค่าตั้ง — ผิดต้องฟ้อง ไม่เงียบ")
    _, e = C.clean_cfg({"teams": ["A", "ทีมโปรดักชัน"]})
    ck("รหัสทีมยาว/ไทย = ฟ้อง", bool(e), e)
    _, e = C.clean_cfg({"teams": ["A", "B"], "anchor_team": "C"})
    ck("ทีมของวันตั้งต้นไม่อยู่ในรายการ = ฟ้อง", bool(e), e)
    _, e = C.clean_cfg({"sla_min": 0})
    ck("เส้นตาย 0 นาที = ฟ้อง", bool(e), e)
    _, e = C.clean_cfg({"open": "25:00"})
    ck("เวลา 25:00 = ฟ้อง", bool(e), e)
    _, e = C.clean_cfg({"alert_on": True, "alert_group": ""})
    ck("เปิดแจ้งเตือนแต่ไม่เลือกกลุ่ม = ฟ้อง", bool(e), e)
    _, e = C.clean_cfg({"alert_group": "U" + "a" * 32})
    ck("กลุ่มแจ้งเตือนเป็นไอดีคน (U…) = ฟ้อง", bool(e), e)
    good, e = C.clean_cfg({"teams": ["a", "b"], "anchor_team": "b", "sla_min": "7", "open": "9:00"})
    ck("ค่าถูก = ผ่าน + ทำให้เป็นรูปแบบเดียวกัน",
       not e and good["teams"] == ["A", "B"] and good["anchor_team"] == "B"
       and good["sla_min"] == 7 and good["open"] == "09:00", (e, good))
    old_day = (timezone.localdate() - timedelta(days=60)).isoformat()
    good, e = C.clean_cfg({"overrides": {old_day: "A", "2099-01-01": "B"}})
    ck("สลับเวรที่ผ่านมานานแล้วถูกทิ้งตอนบันทึก", not e and old_day not in good["overrides"]
       and "2099-01-01" in good["overrides"], good["overrides"])

    # ── ข้อมูลตั้งต้น: วันนี้ = เวรทีม A · นับ 24 ชม. (เทสต์ไม่ขึ้นกับเวลาที่รัน) ──
    TODAY = timezone.localdate()
    ck("บันทึกค่าตั้งได้", C.save_cfg(dict(C.DEFAULTS, anchor_date=TODAY.isoformat(), anchor_team="A",
                                            open="00:00", close="00:00")))
    ck("วันนี้เวรทีม A ตามที่ตั้ง", C.today_team() == "A", C.today_team())

    A1 = Employee.objects.create(nickname="เอหนึ่ง", position="ทีม A")
    A2 = Employee.objects.create(nickname="เอสอง", position="ทีม A")
    B1 = Employee.objects.create(nickname="บีหนึ่ง", position="ทีม B")
    OFFICE = Employee.objects.create(nickname="ออฟฟิศ", position="ออฟฟิศ บ้านเก่า")
    ck("ทีมจากทะเบียน: ทีม A → A", C.team_of(A1) == "A")
    ck("ตำแหน่งที่ไม่ใช่ทีมขาย = ไม่มีทีม", C.team_of(OFFICE) == "", C.team_of(OFFICE))
    ck("รายชื่อโอนได้มีแต่ทีมขาย", {s["name"] for s in C.seller_list()} == {"เอหนึ่ง", "เอสอง", "บีหนึ่ง"},
       C.seller_list())

    def cust(n, name):
        return LineProfile.objects.create(user_id="U%032x" % n, display_name=name)

    P1, P2, P3 = cust(1, "ลูกค้าหนึ่ง"), cust(2, "ลูกค้าสอง"), cust(3, "ลูกค้าสาม")
    STAFF = LineProfile.objects.create(user_id="U%032x" % 99, display_name="พนักงาน",
                                       is_employee=True, nickname="เอหนึ่ง", employee=A1)

    # ═════════════════════════════════════════════════════════════════════
    print("[4] ลูกค้าทักเข้ามา → เข้าคิว + เริ่มนับ")
    t0 = timezone.now() - timedelta(minutes=2)
    o1 = C.note_customer_message(P1.user_id, t0, "สนใจ Civic ปี 20")
    ck("สร้างแถวให้ลูกค้า", o1 is not None and ChatOwner.objects.count() == 1)
    ck("ยังไม่มีเจ้าของ", o1.owner_id is None)
    ck("เริ่มรอบรอ + เส้นตาย = +5 นาที", o1.awaiting_since == t0 and o1.due_at == t0 + timedelta(minutes=5),
       (o1.awaiting_since, o1.due_at))
    #  ทีม = เวรของ "วันที่ของเส้นตาย" — รันเทสต์ตอน 23:58 เส้นตายข้ามเที่ยงคืนไปเป็นเวรวันรุ่งขึ้น (ถูกต้อง)
    ck("ทีมของรอบนี้ = เวรของวันที่ครบเส้นตาย",
       o1.team == C.duty_team(timezone.localtime(o1.due_at).date()), (o1.team, o1.due_at))
    o1b = C.note_customer_message(P1.user_id, t0 + timedelta(minutes=1), "ผ่อนเดือนละเท่าไหร่")
    ck("ส่งรัวๆ = รอบเดิม เส้นตายไม่เลื่อน", o1b.due_at == t0 + timedelta(minutes=5))
    ck("ข้อความล่าสุดอัปเดต", o1b.last_preview == "ผ่อนเดือนละเท่าไหร่" and o1b.last_dir == "in")
    ck("พนักงานทักบอทแจ้งเตือน (push) = ไม่เข้าคิว", C.note_customer_message(STAFF.user_id, t0, "x", channel="push") is None)
    ck("ไม่รู้จักคนนี้ = ไม่พัง", C.note_customer_message("U" + "f" * 32, t0, "x") is None)

    # ═════════════════════════════════════════════════════════════════════
    print("[5] รับลูกค้า — ใครกดก่อนได้ไป · เฉพาะวันเวร")
    ok, msg = C.claim(o1.id, B1)
    ck("ทีม B (ไม่ใช่วันเวร) รับไม่ได้", not ok and "เวรทีม A" in msg, msg)
    ck("ทีม B: บอกวันเวรถัดไปจริง (พรุ่งนี้)", "พรุ่งนี้" in msg, msg)
    C1 = Employee.objects.create(nickname="ซีหนึ่ง", position="ทีม C")
    ok, msg = C.claim(o1.id, C1)
    ck("★ ทีมที่ไม่อยู่ในเวร (C) = บอกว่าไม่อยู่ในเวร ไม่ใช่ให้รอวันเวรที่ไม่มีวันมา",
       not ok and "ไม่ได้อยู่ในเวร" in msg, msg)
    ok, msg = C.claim(o1.id, OFFICE)
    ck("ไม่มีทีมในทะเบียน = บอกให้ไปตั้งทีม", not ok and "ยังไม่ได้ตั้งทีม" in msg, msg)
    ck("ทีมที่เวรวันนี้ = ไม่มีเหตุผลห้าม", C.off_duty_reason("A") == "")
    ok, msg = C.claim(o1.id, A1)
    ck("ทีม A (วันเวร) รับได้", ok, msg)
    ok, msg = C.claim(o1.id, A2)
    ck("คนที่สองกดทีหลัง = ไม่ได้ + บอกว่าใครได้ไป", not ok and "เอหนึ่ง" in msg, msg)
    ck("เจ้าของคือคนแรก", ChatOwner.objects.get(pk=o1.id).owner_id == A1.id)
    ok, msg = C.claim(o1.id, A1)
    ck("กดซ้ำ (ของตัวเองอยู่แล้ว) = ไม่ error", ok, msg)
    ck("ประวัติจด 'รับลูกค้า' ครั้งเดียว", ChatOwnerLog.objects.filter(chat_id=o1.id, action="claim").count() == 1)
    ok, msg = C.claim(o1.id, None)
    ck("บัญชีไม่ผูกทะเบียน = บอกเหตุผล", not ok and "ทะเบียนพนักงาน" in msg, msg)
    # ลูกค้าที่ไม่ได้รออยู่ในคิว — เซลล์รับเองไม่ได้ (ต้องให้แอดมินโอน) · แอดมินรับได้
    o3 = C._row_for(P3)
    ok, msg = C.claim(o3.id, A2)
    ck("ลูกค้าที่ไม่ได้รอในคิว = เซลล์รับเองไม่ได้", not ok, msg)
    ok, msg = C.claim(o3.id, B1, admin=True)
    ck("แอดมินรับได้ทุกวัน (ไม่ติดเวร)", ok, msg)
    C.assign(o3.id, None, by="เทสต์")

    # ═════════════════════════════════════════════════════════════════════
    print("[6] ลูกค้าของเราตลอด — ไม่ขึ้นกับวันเวร")
    C.save_cfg(dict(C.cfg(), anchor_team="B"))              # พรุ่งนี้สมมติ: วันนี้กลายเป็นเวร B
    o1c = C.note_customer_message(P1.user_id, timezone.now(), "ยังอยู่ไหมครับ")
    ck("วันที่ไม่ใช่เวรทีม A ลูกค้าก็ยังเป็นของ เอหนึ่ง", o1c.owner_id == A1.id)
    C.save_cfg(dict(C.cfg(), anchor_team="A"))

    # ═════════════════════════════════════════════════════════════════════
    print("[7] ตอบแล้ว = จบรอบรอ + จดเวลาเป็นสถิติ")
    r = C.note_reply(P1.user_id, A1, timezone.now(), "สวัสดีครับ")
    ck("ตอบแล้วไม่รอแล้ว", r.awaiting_since is None and r.due_at is None)
    ck("จดตอบครั้งแรกของเจ้าของ", r.first_reply_at is not None)
    lg = ChatOwnerLog.objects.filter(chat_id=o1.id, action="reply").first()
    ck("ประวัติตอบมีเวลาที่ลูกค้ารอ", lg is not None and lg.wait_sec is not None and lg.wait_sec >= 100,
       lg and lg.wait_sec)
    ck("ตอบทันเวลา = on_time จริง", lg is not None and lg.on_time is True)
    C.note_reply(P1.user_id, A1, timezone.now(), "ตามมาอีกข้อความ")
    ck("ตอบเพิ่มตอนไม่มีรอบรอ = ไม่นับซ้ำในสถิติ",
       ChatOwnerLog.objects.filter(chat_id=o1.id, action="reply").count() == 1)

    # ═════════════════════════════════════════════════════════════════════
    print("[8] เลยเวลา → แจ้งแอดมินครั้งเดียวต่อรอบ")
    CALLS.clear()
    o2 = C.note_customer_message(P2.user_id, timezone.now() - timedelta(minutes=9), "มีรถเก๋งไหม")
    res = C.tick()
    ck("ติดธงเลยเวลา 1 คน", res.get("escalated") == 1, res)
    ck("ไม่ได้เปิดแจ้ง LINE = ไม่ยิง LINE", not pushes(), pushes())
    ck("เรียกซ้ำ = ไม่แจ้งซ้ำ", C.tick() == {})
    ck("ประวัติเลยเวลา (ยังไม่มีเจ้าของ)", ChatOwnerLog.objects.filter(
        chat_id=o2.id, action="escalate", note__contains="ยังไม่มีเซลล์").count() == 1)
    C.note_reply(P2.user_id, None, timezone.now(), "มีครับ", by="admin")
    o2r = ChatOwner.objects.get(pk=o2.id)
    ck("ตอบแล้วล้างธงเลยเวลา", o2r.escalated_at is None and o2r.awaiting_since is None)
    lg2 = ChatOwnerLog.objects.filter(chat_id=o2.id, action="reply").first()
    ck("ตอบหลังเส้นตาย = on_time เป็นเท็จ", lg2 is not None and lg2.on_time is False)
    # เปิดแจ้งเตือน LINE เข้ากลุ่ม
    C.save_cfg(dict(C.cfg(), alert_on=True, alert_group="C" + "1" * 32))
    CALLS.clear()
    C.note_customer_message(P2.user_id, timezone.now() - timedelta(minutes=8), "ยังไม่มีใครตอบเลย")
    res = C.tick()
    p = pushes()
    ck("เปิดแจ้ง LINE = ส่ง 1 ข้อความ", res.get("alert") == "ok" and len(p) == 1, (res, p))
    body = json.dumps(p[0][2] if p else {}, ensure_ascii=False)
    ck("ส่งเข้ากลุ่มที่ตั้งไว้", ('"to": "C' + "1" * 32) in body, body[:120])
    ck("ข้อความมีชื่อลูกค้า + ลิงก์ Connect", "ลูกค้าสอง" in body and "/connect/" in body, body[:300])
    C.save_cfg(dict(C.cfg(), alert_on=False, alert_group=""))
    C.note_reply(P2.user_id, None, timezone.now(), "ขอโทษครับ", by="admin")

    # ═════════════════════════════════════════════════════════════════════
    print("[9] โอน / ปล่อยคืนคิว / ไม่ต้องตอบ / เซลล์ลาออก")
    ok, msg = C.assign(o2.id, B1, by="แอดมิน")
    ck("แอดมินโอนให้ทีม B ได้ (ไม่ติดเวร)", ok and ChatOwner.objects.get(pk=o2.id).owner_id == B1.id, msg)
    ck("ทีมของแถวเปลี่ยนตามเจ้าของ", ChatOwner.objects.get(pk=o2.id).team == "B")
    ok, msg = C.assign(o2.id, None, by="แอดมิน")
    ck("ปล่อยคืนคิว", ok and ChatOwner.objects.get(pk=o2.id).owner_id is None, msg)
    ck("ประวัติมีทั้งโอนและปล่อย", set(ChatOwnerLog.objects.filter(chat_id=o2.id)
                                     .values_list("action", flat=True)) >= {"assign", "release"})
    C.note_customer_message(P2.user_id, timezone.now(), "ขอบคุณครับ")
    ok, msg = C.dismiss(o2.id, by="แอดมิน")
    ck("ไม่ต้องตอบ = ปิดรอบรอ", ok and ChatOwner.objects.get(pk=o2.id).awaiting_since is None, msg)
    C.assign(o2.id, A2, by="แอดมิน")
    A2.active = False
    A2.save()
    o2x = C.note_customer_message(P2.user_id, timezone.now(), "สวัสดี")
    ck("เจ้าของถูกปิดใช้งาน → ลูกค้ากลับเข้าคิวเอง", o2x.owner_id is None)
    ck("ปิดใช้งานแล้วถูกโอนให้ไม่ได้", not C.assign(o2.id, A2, by="แอดมิน")[0])
    A2.active = True
    A2.save()

    # ═════════════════════════════════════════════════════════════════════
    print("[10] เก็บแชทจาก webhook → เข้า Connect เอง")
    from checkout.views import store_chat, line_cfg, _save_cfg
    cfg0 = line_cfg()
    _save_cfg(dict(cfg0, store_customer_chat=True))
    n = store_chat({"events": [{
        "type": "message", "timestamp": int(timezone.now().timestamp() * 1000),
        "source": {"type": "user", "userId": "U%032x" % 4},
        "message": {"id": "m-new-1", "type": "text", "text": "มี Yaris ไหมครับ"}}]})
    ck("เก็บข้อความ 1 ข้อความ", n == 1, n)
    o4 = ChatOwner.objects.filter(profile__user_id="U%032x" % 4).first()
    ck("ลูกค้าใหม่โผล่ในคิว Connect พร้อมนาฬิกา", o4 is not None and o4.awaiting_since is not None
       and o4.owner_id is None, o4)
    ck("ข้อความล่าสุดถูกต้อง", o4 is not None and o4.last_preview == "มี Yaris ไหมครับ")
    store_chat({"events": [{
        "type": "message", "source": {"type": "user", "userId": "U%032x" % 4},
        "message": {"id": "m-new-2", "type": "sticker", "stickerId": "1", "packageId": "2"}}]})
    ck("สติกเกอร์ = ป้ายอ่านออก", ChatOwner.objects.get(pk=o4.id).last_preview == "[สติกเกอร์]")
    store_chat({"events": [{
        "type": "message", "source": {"type": "group", "groupId": "C" + "2" * 32, "userId": "U%032x" % 5},
        "message": {"id": "m-grp-1", "type": "text", "text": "แชทกลุ่มงาน"}}]})
    ck("แชทกลุ่มงาน = ไม่เข้า Connect", not ChatOwner.objects.filter(profile__user_id="U%032x" % 5).exists())

    # ═════════════════════════════════════════════════════════════════════
    print("[11] สิทธิ์หน้าเว็บ — เซลล์เห็นเฉพาะลูกค้าของตัวเอง")
    for i, g in enumerate(((P1, "in", "สนใจ Civic ปี 20"), (P1, "out", "สวัสดีครับ"), (P2, "in", "มีรถเก๋งไหม"))):
        GroupChat.objects.create(chat_type="user", message_id="seed-%d" % i,
                                 sender_id=g[0].user_id, direction=g[1], msg_type="text", text=g[2],
                                 sent_at=timezone.now() - timedelta(minutes=30))
    # ลูกค้า 2 กลับมาอยู่กับ เอสอง (ทีม A) — ใช้ทดสอบว่า เอหนึ่ง เห็นไม่ได้
    C.assign(o2.id, A2, by="แอดมิน")

    def client(user):
        cl = Client()
        if user:
            st = SessionStore()
            st["oxlet_user"] = user
            st.save()
            cl.cookies[settings.SESSION_COOKIE_NAME] = st.session_key
        return cl

    SA1 = client({"user_id": "Ux1", "nickname": "เอหนึ่ง", "position": "seller"})
    SB1 = client({"user_id": "Ux2", "nickname": "บีหนึ่ง", "position": "seller"})
    ADM = client({"user_id": "admin", "nickname": "admin", "position": "admin"})
    WRK = client({"user_id": "django_w", "nickname": "ช่าง", "position": "worker"})
    NOB = client(None)
    GHOST = client({"user_id": "Ux9", "nickname": "ไม่มีในทะเบียน", "position": "seller"})

    def J(cl, path, body=None):
        r = cl.post(path, json.dumps(body), content_type="application/json", secure=True) if body is not None \
            else cl.get(path, secure=True)
        try:
            return r.status_code, json.loads(r.content.decode("utf-8"))
        except Exception:
            return r.status_code, {}

    r = NOB.get("/connect/", secure=True)
    ck("ไม่ login → ไปหน้า login พร้อม next", r.status_code == 302 and "/login/?next=" in r["Location"],
       r.status_code)
    r = WRK.get("/connect/", secure=True)
    ck("คนงาน (worker) เข้าไม่ได้", r.status_code == 403, r.status_code)
    r = GHOST.get("/connect/", secure=True)
    ck("เซลล์ที่ไม่มีในทะเบียน = บอกเหตุผล", r.status_code == 403 and "ทะเบียนพนักงาน" in r.content.decode(),
       r.status_code)
    r = SA1.get("/connect/", secure=True)
    ck("เซลล์เปิดหน้าได้", r.status_code == 200, r.status_code)
    r = ADM.get("/connect/", secure=True)
    ck("แอดมินเปิดหน้าได้", r.status_code == 200, r.status_code)

    s, d = J(SA1, "/connect/api/inbox?view=all")
    ck("เซลล์ขอดู 'ทั้งหมด' → ถูกบังคับเป็นมุมมองของตัวเอง", s == 200 and d.get("view") in ("queue", "mine"),
       (s, d.get("view")))
    s, d = J(SA1, "/connect/api/inbox?view=mine")
    names = {x["name"] for x in d.get("rows", [])}
    ck("ลูกค้าของฉัน = เฉพาะของตัวเอง", names == {"ลูกค้าหนึ่ง"}, names)
    s, d = J(SA1, "/connect/api/inbox?view=queue")
    ck("วันเวร: เห็นคิวรอรับ", "ลูกค้า" in json.dumps(d, ensure_ascii=False) and d.get("onDuty") is True,
       (d.get("onDuty"), [x["name"] for x in d.get("rows", [])]))
    s, d = J(SB1, "/connect/api/inbox?view=queue")
    ck("ไม่ใช่วันเวร: คิวว่าง + บอกว่าเวรทีมไหน", d.get("rows") == [] and "เวรทีม A" in (d.get("note") or ""),
       d.get("note"))
    s, d = J(SA1, "/connect/api/chat?id=%d" % o2.id)
    ck("เปิดแชทลูกค้าของคนอื่น = 403", s == 403, s)
    s, d = J(SA1, "/connect/api/chat?id=%d" % o1.id)
    ck("เปิดแชทลูกค้าของตัวเอง = เห็นเต็ม", s == 200 and d.get("access") == "full"
       and len(d.get("messages", [])) >= 2, (s, d.get("access")))
    ck("ลูกค้าของตัวเอง = ตอบได้", d.get("canReply") is True)
    s, d = J(SA1, "/connect/api/chat?id=%d" % o4.id)
    ck("คิวรอรับ = เห็นแค่ข้อความที่เพิ่งส่ง (preview)", s == 200 and d.get("access") == "preview"
       and all(m["dir"] == "in" for m in d.get("messages", [])), (s, d.get("access")))
    ck("คิวรอรับ = ยังตอบไม่ได้ แต่กดรับได้", d.get("canReply") is False and d.get("canClaim") is True)
    s, d = J(SB1, "/connect/api/chat?id=%d" % o4.id)
    ck("คิวรอรับ วันไม่ใช่เวร = เปิดไม่ได้", s == 403, s)
    s, d = J(SA1, "/connect/api/reply", {"id": o4.id, "text": "สวัสดีครับ"})
    ck("ตอบลูกค้าที่ยังไม่ได้รับ = 403", s == 403, s)
    s, d = J(SA1, "/connect/api/assign", {"id": o4.id, "emp": A1.id})
    ck("เซลล์โอนลูกค้าเองไม่ได้", s == 403, s)
    s, d = J(SA1, "/connect/api/config")
    ck("เซลล์เปิดตั้งค่าไม่ได้", s == 403, s)
    s, d = J(SA1, "/connect/api/stats")
    ck("เซลล์ดูสถิติไม่ได้", s == 403, s)
    s, d = J(SB1, "/connect/api/claim", {"id": o4.id})
    ck("รับลูกค้าตอนไม่ใช่วันเวร (ยิง API ตรง) = ปฏิเสธ", s == 409 and "เวร" in d.get("error", ""), (s, d))
    s, d = J(SA1, "/connect/api/claim", {"id": o4.id})
    ck("รับลูกค้าในวันเวรผ่าน API ได้", s == 200 and d.get("ok"), (s, d))
    s, d = J(SA1, "/connect/api/chat?id=%d" % o4.id)
    ck("รับแล้ว = เห็นเต็ม", d.get("access") == "full", d.get("access"))

    print("[12] ตอบผ่าน Connect")
    s, d = J(SA1, "/connect/api/reply", {"id": o4.id, "text": "มีครับ"})
    ck("ยังล็อกการส่ง = ส่งไม่ได้ + บอกวิธีเปิด", s == 400 and "--reply on" in d.get("error", ""), (s, d))
    _save_cfg(dict(line_cfg(), reply_customer=True))
    CALLS.clear()
    s, d = J(SA1, "/connect/api/reply", {"id": o4.id, "text": "มี Yaris 2 คันครับ"})
    ck("เจ้าของตอบได้", s == 200 and d.get("ok"), (s, d))
    ck("ยิง LINE ไปหาลูกค้าคนนั้นจริง", any(("U%032x" % 4) in json.dumps(c[2] or {}) for c in pushes()), pushes())
    out = GroupChat.objects.filter(sender_id="U%032x" % 4, direction="out").first()
    ck("เก็บข้อความขาออก + ชื่อคนตอบ", out is not None and out.sent_by_id == A1.id and out.sent_by_name == "เอหนึ่ง",
       out and (out.sent_by_id, out.sent_by_name))
    ck("ตอบแล้วรอบรอจบ", ChatOwner.objects.get(pk=o4.id).awaiting_since is None)
    POST_CODE[0] = 400
    s, d = J(SA1, "/connect/api/reply", {"id": o4.id, "text": "ส่งไม่ถึง"})
    ck("LINE ปฏิเสธ = แจ้งเป็นภาษาคน", s == 400 and "บล็อก" in d.get("error", ""), (s, d))
    ck("ส่งไม่สำเร็จ = ไม่บันทึกลงบทสนทนา", not GroupChat.objects.filter(text="ส่งไม่ถึง").exists())
    POST_CODE[0] = 200
    s, d = J(ADM, "/connect/api/reply", {"id": o2.id, "text": "แอดมินตอบแทนครับ"})
    ck("แอดมินตอบลูกค้าของใครก็ได้", s == 200 and d.get("ok"), (s, d))

    print("[13] แอดมิน")
    s, d = J(ADM, "/connect/api/inbox?view=all")
    ck("แอดมินเห็นทุกคน", s == 200 and len(d.get("rows", [])) >= 4, len(d.get("rows", [])))
    ck("แอดมินได้รายชื่อเซลล์ไว้โอน (ทีม A/B/C — ไม่รวมออฟฟิศ)", len(d.get("sellers", [])) == 4,
       [x["name"] for x in d.get("sellers", [])])
    s, d = J(ADM, "/connect/api/chat?id=%d" % o2.id)
    ck("แอดมินเห็นประวัติ", s == 200 and len(d.get("history", [])) >= 2, (s, len(d.get("history", []))))
    s, d = J(ADM, "/connect/api/assign", {"id": o4.id, "emp": B1.id})
    ck("แอดมินโอนผ่าน API", s == 200 and ChatOwner.objects.get(pk=o4.id).owner_id == B1.id, (s, d))
    s, d = J(SA1, "/connect/api/chat?id=%d" % o4.id)
    ck("โอนออกไปแล้ว เจ้าของเดิมเปิดไม่ได้", s == 403, s)
    s, d = J(ADM, "/connect/api/config", {"sla_min": 0})
    ck("ตั้งค่าผิด = 400 + บอกช่อง", s == 400 and "1–120" in d.get("error", ""), (s, d))
    s, d = J(ADM, "/connect/api/config", {"sla_min": 7})
    ck("ตั้งค่าถูก = บันทึก", s == 200 and C.cfg()["sla_min"] == 7, (s, C.cfg()["sla_min"]))
    ck("ตั้งค่าคืนตารางเวร 14 วัน", len(d.get("roster", [])) == 14)
    s, d = J(ADM, "/connect/api/stats?days=7")
    names = {r["name"] for r in d.get("rows", [])}
    ck("สถิติมีคนที่ตอบ/รับลูกค้า", s == 200 and "เอหนึ่ง" in names, names)
    s, d = J(SA1, "/connect/api/summary")
    ck("ป้ายตัวเลขของเซลล์", s == 200 and d.get("ok") and "mineWaiting" in d.get("counts", {}), d)

    print("[14] ไม่มี LINE user id หลุดออกหน้า Connect")
    leak = re.compile(r"U[0-9a-f]{32}")
    dumps = []
    for cl, paths in ((SA1, ["/connect/api/inbox?view=mine", "/connect/api/inbox?view=queue",
                             "/connect/api/chat?id=%d" % o1.id, "/connect/api/summary", "/connect/"]),
                      (ADM, ["/connect/api/inbox?view=all", "/connect/api/chat?id=%d" % o1.id,
                             "/connect/api/config", "/connect/api/stats", "/connect/"])):
        for pth in paths:
            dumps.append((pth, cl.get(pth, secure=True).content.decode("utf-8")))
    bad = [p for p, txt in dumps if leak.search(txt)]
    ck("ทุก endpoint ไม่มี LINE user id", not bad, bad)

    print("[15] โปรไฟล์ลูกค้า — รูป LINE + เบอร์ที่พิมพ์มา + รถที่หา")
    ck("เบอร์มือถือติดกัน", C.phones_in(["โทรมา 0902483727 นะครับ"]) == ["0902483727"])
    ck("เบอร์มีขีด/เว้นวรรค", C.phones_in(["090-248-3727", "081 234 5678"]) == ["0902483727", "0812345678"])
    ck("เบอร์ +66", C.phones_in(["+66 90 248 3727"]) == ["0902483727"])
    ck("เบอร์บ้าน 02", C.phones_in(["02-123-4567"]) == ["021234567"])
    ck("ไม่จับราคา/ปี/รหัสลีด", C.phones_in(["งบ 450000 ปี 2021 รหัส TLD9-7376 ผ่อน 9000"]) == [])
    ck("เบอร์ซ้ำนับครั้งเดียว", C.phones_in(["0902483727", "090-248-3727"]) == ["0902483727"])
    ck("ไม่จับเลขยาวเกิน (เลขบัญชี 12 หลัก)", C.phones_in(["012345678901"]) == [])

    # touch_profile ส่งรูปที่เพิ่งดึงมาต่อ — แต่ไม่เก็บลง LineProfile (กติกาเดิม)
    from checkout import people
    PROFILE_OK[0] = True
    tp = people.touch_profile("U%032x" % 6, chat_type="user")
    ck("ลูกค้าใหม่: touch_profile คืนรูปมาด้วย", tp.get("picture") == FAKE_PIC, tp)
    lp6 = LineProfile.objects.get(user_id="U%032x" % 6)
    ck("★ ไม่เก็บรูปลง LineProfile (ไม่มีช่องนี้แล้ว)", not hasattr(lp6, "picture_url"))
    ck("★ raw ของ LineProfile ไม่มี pictureUrl", "pictureUrl" not in (lp6.raw or {}), lp6.raw)
    o6 = C.note_customer_message("U%032x" % 6, timezone.now(), "สวัสดี", picture=tp.get("picture"))
    ck("รูปที่ส่งต่อมา เก็บที่แถว Connect", o6.picture_url == FAKE_PIC and o6.picture_at is not None)
    n_get = len([c for c in CALLS if c[0] == "get"])
    C.note_customer_message("U%032x" % 6, timezone.now(), "อีกข้อความ")
    ck("รูปยังใหม่ = ไม่ยิง LINE ซ้ำ", len([c for c in CALLS if c[0] == "get"]) == n_get)
    tp_emp = people.touch_profile(STAFF.user_id, chat_type="user")
    ck("★ พนักงาน = ไม่ส่งรูปออกมา", not tp_emp.get("picture"), tp_emp)

    # ลูกค้าเก่าที่ยังไม่มีรูป → เติมเอง (จองแถวก่อน กันหลาย worker ดึงซ้ำ)
    ChatOwner.objects.update(picture_url="", picture_at=None)
    n = C.fill_pictures(limit=50)
    ck("เติมรูปให้ลูกค้าเก่าทุกคนที่ดึงได้", n == ChatOwner.objects.count() and n >= 4,
       (n, ChatOwner.objects.count()))
    ck("ทุกแถวได้รูป", not ChatOwner.objects.filter(picture_url="").exists())
    lp1 = LineProfile.objects.get(pk=P1.pk)
    ck("ดึงโปรไฟล์แล้วอัปเดตชื่อ/สเตตัส/ภาษาใน LineProfile", lp1.display_name == "ชื่อใหม่ใน LINE"
       and lp1.status_message == "หารถให้ครอบครัว" and lp1.language == "th", (lp1.display_name, lp1.status_message))
    ck("เรียกซ้ำทันที = ไม่มีอะไรต้องเติม", C.fill_pictures(limit=50) == 0)
    PROFILE_OK[0] = False
    ChatOwner.objects.filter(pk=o1.id).update(picture_url="", picture_at=None)
    ck("ดึงไม่ได้ (ลูกค้าบล็อกบอท) = ไม่ล้ม", C.fill_pictures(limit=50) == 0)
    o1p = ChatOwner.objects.get(pk=o1.id)
    left = (o1p.picture_at + timedelta(days=C.PIC_REFRESH_DAYS)) - timezone.now()
    ck("ดึงไม่ได้ = เว้นราว 1 วันค่อยลองใหม่ (ไม่ยิงทุกครั้งที่เปิดหน้า)",
       timedelta(hours=23) < left <= timedelta(hours=24), left)
    ck("ดึงไม่ได้ = ไม่ถือว่าได้รูป", o1p.picture_url == "")
    ChatOwner.objects.filter(pk=o1.id).update(picture_url=FAKE_PIC)

    # การ์ดโปรไฟล์ในหน้าแชท
    from checkout.models import CustomerNeed
    GroupChat.objects.create(chat_type="user", message_id="seed-phone", sender_id=P1.user_id, direction="in",
                             msg_type="text", text="เบอร์ผม 090-248-3727 ครับ", sent_at=timezone.now())
    CustomerNeed.objects.create(profile=P1, car_model="Civic", budget_max=450000, monthly_max=9000,
                                status="lead", waiting=True)
    C.assign(o1.id, A1, by="แอดมิน")
    s_, d = J(SA1, "/connect/api/chat?id=%d" % o1.id)
    pf = d.get("profile") or {}
    ck("เจ้าของเห็นการ์ดโปรไฟล์เต็ม", s_ == 200 and pf.get("full") is True, (s_, pf.get("full")))
    ck("การ์ดมีรูป", pf.get("pic") == FAKE_PIC, pf.get("pic"))
    ck("การ์ดมีเบอร์ที่ลูกค้าพิมพ์", pf.get("phones") == ["0902483727"], pf.get("phones"))
    ck("การ์ดมีรถที่ลูกค้าหา + งบ", pf.get("needs") and pf["needs"][0]["car"] == "Civic"
       and "450,000" in pf["needs"][0]["detail"] and pf["needs"][0]["waiting"] is True, pf.get("needs"))
    ck("การ์ดมีสเตตัส LINE", pf.get("status") == "หารถให้ครอบครัว", pf.get("status"))
    ck("แถวในลิสต์มีรูป", any(r.get("pic") == FAKE_PIC for r in J(SA1, "/connect/api/inbox?view=mine")[1].get("rows", [])))
    # คิวรอรับ (preview) — เห็นแค่รูป+ชื่อ ไม่เห็นเบอร์/รถที่หา
    C.assign(o4.id, None, by="แอดมิน")
    C.note_customer_message("U%032x" % 4, timezone.now(), "โทรหาผม 0811111111")
    GroupChat.objects.create(chat_type="user", message_id="seed-phone-4", sender_id="U%032x" % 4, direction="in",
                             msg_type="text", text="โทรหาผม 0811111111", sent_at=timezone.now())
    s_, d = J(SA1, "/connect/api/chat?id=%d" % o4.id)
    pf = d.get("profile") or {}
    ck("คิวรอรับ: การ์ดแบบย่อ", s_ == 200 and pf.get("full") is False, (s_, pf))
    ck("★ คิวรอรับ: ไม่ส่งเบอร์/รถที่หา/สเตตัส ออกไป", "phones" not in pf and "needs" not in pf and "status" not in pf, pf)

    leak2 = [pth for pth in ("/connect/api/chat?id=%d" % o1.id, "/connect/api/inbox?view=mine")
             if leak.search(SA1.get(pth, secure=True).content.decode("utf-8"))]
    ck("หลังเพิ่มโปรไฟล์ ยังไม่มี LINE user id หลุด", not leak2, leak2)

    print("[16] โหมดทดสอบ — บัญชีเซลล์จำลอง + ลูกค้าจำลอง")
    ck("ลูกค้าจำลองนับ 5 นาทีทันทีแม้ตอนกลางคืน",
       C.due_for(at(2026, 10, 3, 23), dict(C.DEFAULTS), ignore_hours=True) == at(2026, 10, 3, 23, 5))
    s_, d = J(SA1, "/connect/api/test")
    ck("เซลล์ใช้โหมดทดสอบไม่ได้", s_ == 403, s_)
    s_, d = J(SA1, "/connect/api/test", {"action": "as", "team": "A"})
    ck("เซลล์สลับตัวตนไม่ได้", s_ == 403, s_)
    s_, d = J(ADM, "/connect/api/test")
    ck("แอดมินเห็นสถานะโหมดทดสอบ", s_ == 200 and d.get("as") is False and "counts" in d, d)
    _save_cfg(dict(line_cfg(), reply_customer=False))       # ล็อกการส่งไว้ — ลูกค้าจำลองต้องยังตอบได้

    TST = client({"user_id": "admin", "nickname": "admin", "position": "admin"})
    s_, d = J(TST, "/connect/api/test", {"action": "as", "team": "B"})
    ck("แอดมินสลับเป็น ทดสอบเซลล์ B", s_ == 200 and d.get("ok"), d)
    tB = Employee.objects.filter(nickname="ทดสอบเซลล์ B").first()
    ck("สร้างบัญชีจำลองให้ (ทีม B · ไม่ต้องเช็คชื่อ)", tB is not None and C.team_of(tB) == "B"
       and tB.track_checkin is False, tB and (tB.position, tB.track_checkin))
    r = TST.get("/connect/", secure=True).content.decode("utf-8")
    #  json_script หนีอักษรไทยเป็น \uXXXX — ต้องแกะ JSON ก่อนเทียบ (ค้นข้อความตรงๆ จะไม่เจอ)
    mm = re.search(r'<script id="cn-boot" type="application/json">(.*?)</script>', r, re.S)
    boot = json.loads(mm.group(1)) if mm else {}
    ck("หน้าเว็บบอกว่ากำลังใช้บัญชีจำลอง", (boot.get("test") or {}).get("as") is True
       and (boot.get("me") or {}).get("name") == "ทดสอบเซลล์ B" and (boot.get("me") or {}).get("admin") is False, boot)
    s_, d = J(TST, "/connect/api/inbox?view=all")
    ck("โหมดทดสอบ = ได้สิทธิ์แบบเซลล์ (ขอดูทั้งหมดไม่ได้)", d.get("view") in ("queue", "mine")
       and "overdue" not in d.get("counts", {}), (d.get("view"), list(d.get("counts", {}))))
    s_, d = J(TST, "/connect/api/config")
    ck("โหมดทดสอบ = เปิดตั้งค่าไม่ได้ (เหมือนเซลล์)", s_ == 403, s_)
    s_, d = J(TST, "/connect/api/test", {"action": "customer", "text": "มีกระบะไหมครับ"})
    ck("สร้างลูกค้าจำลองได้", s_ == 200 and d.get("id"), d)
    sim_id = d.get("id")
    so = ChatOwner.objects.select_related("profile").get(pk=sim_id)
    ck("ลูกค้าจำลอง id ไม่ใช่ LINE id", so.profile.user_id.startswith("TEST-")
       and not leak.search(so.profile.user_id), so.profile.user_id)
    ck("ลูกค้าจำลองเข้าคิว + เริ่มนับทันที", so.awaiting_since is not None and so.owner_id is None
       and (so.due_at - so.awaiting_since) == timedelta(minutes=C.cfg()["sla_min"]))
    s_, d = J(TST, "/connect/api/claim", {"id": sim_id})
    ck("ทดสอบเซลล์ B วันนี้ไม่ใช่เวร = รับไม่ได้ (เหมือนเซลล์จริง)", s_ == 409, (s_, d))
    s_, d = J(TST, "/connect/api/test", {"action": "as", "team": "A"})
    s_, d = J(TST, "/connect/api/claim", {"id": sim_id})
    ck("สลับเป็นทีม A แล้วรับได้", s_ == 200 and d.get("ok"), (s_, d))
    s_, d = J(TST, "/connect/api/chat?id=%d" % sim_id)
    ck("★ ลูกค้าจำลอง: ช่องตอบเปิดแม้ล็อกการส่งอยู่ (ตรงกับฝั่งส่ง)", d.get("replyOn") is True
       and d.get("canReply") is True, (d.get("replyOn"), d.get("canReply")))
    CALLS.clear()
    s_, d = J(TST, "/connect/api/reply", {"id": sim_id, "text": "มีครับ Revo ปี 20"})
    ck("ตอบลูกค้าจำลองได้แม้ล็อกการส่งอยู่", s_ == 200 and d.get("ok"), (s_, d))
    ck("★ ตอบลูกค้าจำลอง = ไม่ยิง LINE เลย", not pushes(), pushes())
    out = GroupChat.objects.filter(sender_id=so.profile.user_id, direction="out").first()
    ck("บันทึกคำตอบในนามบัญชีจำลอง", out is not None and out.sent_by_name == "ทดสอบเซลล์ A", out and out.sent_by_name)
    ck("ตอบแล้วรอบรอจบ", ChatOwner.objects.get(pk=sim_id).awaiting_since is None)
    s_, d = J(TST, "/connect/api/test", {"action": "say", "id": sim_id, "text": "ราคาเท่าไหร่ครับ"})
    ck("พิมพ์แทนลูกค้าจำลองได้ → เริ่มรอบรอใหม่", s_ == 200 and ChatOwner.objects.get(pk=sim_id).awaiting_since,
       (s_, d))
    s_, d = J(TST, "/connect/api/test", {"action": "say", "id": o1.id, "text": "แอบพิมพ์แทนลูกค้าจริง"})
    ck("★ พิมพ์แทนลูกค้าจริงไม่ได้", s_ == 400, (s_, d))
    # ลูกค้าจำลองเลยเวลา — ติดธงในระบบได้ แต่ห้ามส่ง LINE ไปปลุกกลุ่มแอดมิน
    C.save_cfg(dict(C.cfg(), alert_on=True, alert_group="C" + "1" * 32))
    ChatOwner.objects.filter(pk=sim_id).update(due_at=timezone.now() - timedelta(minutes=1), escalated_at=None)
    ChatOwner.objects.exclude(pk=sim_id).update(awaiting_since=None, due_at=None)
    CALLS.clear()
    res = C.tick()
    ck("ลูกค้าจำลองเลยเวลา = ติดธง", res.get("escalated") == 1, res)
    ck("★ ลูกค้าจำลองเลยเวลา = ไม่ส่ง LINE เข้ากลุ่มแอดมิน", not pushes() and "alert" not in res, (res, pushes()))
    C.save_cfg(dict(C.cfg(), alert_on=False, alert_group=""))
    # บัญชีจำลองเผลอรับลูกค้าจริง → ล้างแล้วต้องคืนเข้าคิว
    C.assign(o2.id, None, by="เทสต์")
    C.note_customer_message(P2.user_id, timezone.now(), "ลูกค้าจริงทักมา")
    s_, d = J(TST, "/connect/api/claim", {"id": o2.id})
    ck("บัญชีจำลองรับลูกค้าจริงได้ (ระบบเตือนก่อนส่งที่หน้าเว็บ)", s_ == 200, (s_, d))
    s_, d = J(TST, "/connect/api/test", {"action": "exit"})
    s_, d = J(TST, "/connect/api/inbox?view=all")
    ck("กลับเป็นแอดมินแล้วเห็นทั้งหมด", d.get("view") == "all", d.get("view"))
    s_, d = J(TST, "/connect/api/test")
    ck("นับว่าบัญชีจำลองถือลูกค้าจริงอยู่", (d.get("counts") or {}).get("realHeld") == 1, d.get("counts"))
    # ★ แอดมินตั้ง connect_as ชี้ไปเซลล์จริง (ปลอม session) = ต้องไม่ได้เป็นเซลล์คนนั้น
    HACK = client({"user_id": "admin", "nickname": "admin", "position": "admin"})
    st = SessionStore(); st["oxlet_user"] = {"user_id": "admin", "nickname": "admin", "position": "admin"}
    st["connect_as"] = A1.id; st.save()
    HACK.cookies[settings.SESSION_COOKIE_NAME] = st.session_key
    s_, d = J(HACK, "/connect/api/inbox?view=all")
    ck("★ สลับเป็นเซลล์จริงไม่ได้ (เฉพาะบัญชีจำลอง)", d.get("view") == "all", d.get("view"))
    SELLER_AS = client(None)
    st = SessionStore(); st["oxlet_user"] = {"user_id": "Ux1", "nickname": "เอหนึ่ง", "position": "seller"}
    st["connect_as"] = tB.id; st.save()
    SELLER_AS.cookies[settings.SESSION_COOKIE_NAME] = st.session_key
    s_, d = J(SELLER_AS, "/connect/api/test")
    ck("★ เซลล์ที่มี connect_as ใน session ก็ยังเป็นตัวเอง", s_ == 403, s_)
    s_, d = J(TST, "/connect/api/test", {"action": "clear"})
    ck("ล้างข้อมูลทดสอบ", s_ == 200 and d.get("ok"), d)
    rr = d.get("result") or {}
    ck("ลบลูกค้าจำลอง + บัญชีจำลอง", rr.get("customers", 0) >= 1 and rr.get("sellers") == 2, rr)
    ck("★ ลูกค้าจริงที่บัญชีจำลองถือไว้ กลับเข้าคิว", rr.get("released") == 1
       and ChatOwner.objects.get(pk=o2.id).owner_id is None, rr)
    ck("ไม่เหลือลูกค้าจำลองในระบบ", not LineProfile.objects.filter(user_id__startswith="TEST-").exists()
       and not GroupChat.objects.filter(sender_id__startswith="TEST-").exists())
    ck("ไม่เหลือบัญชีจำลองในทะเบียน", not Employee.objects.filter(nickname__startswith="ทดสอบเซลล์").exists())
    ck("สถิติไม่เหลือชื่อบัญชีจำลอง", "ทดสอบเซลล์ A" not in {r["name"] for r in C.stats(30)["rows"]})
    ck("ลูกค้าจริงยังอยู่ครบ", ChatOwner.objects.filter(pk__in=[o1.id, o2.id]).count() == 2)

    print("[17] ข้อมูลลีดของลูกค้า — ช่องเดียวกับชีตลีด + เติมอัตโนมัติ + ใบจ่ายลีด")
    from checkout.models import ChatLead
    from checkout.leadgroup import parse_leadsheet
    o1 = ChatOwner.objects.select_related("profile", "owner").get(pk=o1.id)
    ChatLead.objects.filter(chat=o1).delete()
    C.assign(o1.id, A2, by="เฟิร์น")                     # โอนจริง (มีประวัติ) แล้วโอนกลับ
    C.assign(o1.id, A1, by="เฟิร์น")
    o1 = ChatOwner.objects.select_related("profile", "owner").get(pk=o1.id)
    GroupChat.objects.create(chat_type="user", message_id="seed-car", sender_id=P1.user_id, direction="in",
                             msg_type="text", text="สนใจแคมรี่ปี 20 ครับ", sent_at=timezone.now())
    ld = C.autofill(o1)
    ck("เติมเบอร์จากแชท", ld.phone == "0902483727" and ld.auto.get("phone") == "แชท", (ld.phone, ld.auto))
    ck("เติมรุ่นรถจากแชท (ชื่อไทย → ชื่อแบบชีต)", ld.car_model == "Camry" and "แคมรี่" in ld.car_text,
       (ld.car_model, ld.car_text))
    ck("ช่องทาง = LINE@ ตาม dropdown ของชีต (ค่าตั้งต้นของระบบ)", ld.channel == "LINE@" and ld.auto.get("channel") == "ระบบ",
       ld.channel)
    ck("สาขา = สาขาที่ลีดไปจริง (ชลบุรี)", ld.branch == "ชลบุรี" and ld.auto.get("branch") == "ระบบ", ld.branch)
    ck("Admin = คนที่โอนลูกค้าให้ (ชื่ออยู่ในตัวเลือกของชีต)", ld.admin_name == "เฟิร์น", ld.admin_name)
    # คนโอนที่ไม่ใช่ Admin ในตัวเลือกของชีต (เช่นเจ้าของบริษัท) → ไม่เติม ไม่เดา
    o3x = ChatOwner.objects.select_related("profile", "owner").get(pk=o3.id)
    ChatLead.objects.filter(chat=o3x).delete()
    C.assign(o3x.id, A2, by="Wattanakit")
    ld3 = C.autofill(ChatOwner.objects.select_related("profile", "owner").get(pk=o3x.id))
    ck("★ คนโอนไม่อยู่ในตัวเลือก Admin ของชีต = ไม่เติม", ld3.admin_name == "", ld3.admin_name)
    # บัญชีแอดมินระบบ (ชื่อเล่น "admin") ≠ ตัวเลือก "ADMIN" ของชีต — ต่างแค่ตัวพิมพ์ แต่คนละความหมาย
    ChatLead.objects.filter(chat=o3x).delete()
    C.assign(o3x.id, None, by="admin")              # ปล่อยก่อน — โอนให้คนเดิมซ้ำ = ไม่จดประวัติ (เทสต์จะผ่านหลอก)
    C.assign(o3x.id, A2, by="admin")
    last_by = (ChatOwnerLog.objects.filter(chat_id=o3x.id, action=ChatOwnerLog.ASSIGN)
               .order_by("-at", "-id").values_list("by_name", flat=True).first())
    ld3 = C.autofill(ChatOwner.objects.select_related("profile", "owner").get(pk=o3x.id))
    ck("★ แอดมินระบบ (admin) ไม่ถูกเติมเป็น ADMIN ของชีต", last_by == "admin" and "ADMIN" in C.dd_options("admin_name")
       and ld3.admin_name == "", (last_by, ld3.admin_name))
    # ใบจ่ายลีดในกลุ่มจ่ายเบอร์ — โพสต์หลังจากเติมรอบแรกแล้ว
    slip = ("Ac Lead No. TLD9-7376\nAds : รถครอบครัว 7 ที่นั่ง\nชื่อ Account: Oxlet ช่องหลัก\n"
            "ชื่อลูกค้า : คุณสมชาย\nID LINE : somchai99\nชื่อไลน์ : อะไรก็ได้\nเบอร์โทร : 090-248-3727\n"
            "ช่องทาง : TikTok\nรถ : Fortuner\nไลฟ์ : -\nเพิ่มเติม : ผ่อนไม่เกิน 12000\n@เอหนึ่ง")
    GroupChat.objects.create(chat_type="group", group_id="C" + "9" * 32, group_name="ห้องจ่ายเบอร์ ทดสอบ",
                             message_id="slip-1", sender_id="U%032x" % 77, direction="in", msg_type="text",
                             text=slip, sent_at=timezone.now())
    ld = C.autofill(o1)
    ck("หาใบจ่ายลีดซ้ำไม่ถี่ (เว้น 30 นาที)", ld.code == "", ld.code)
    a = dict(ld.auto); a.pop("_slip_at", None); ChatLead.objects.filter(pk=ld.pk).update(auto=a)
    o1 = ChatOwner.objects.select_related("profile", "owner").get(pk=o1.id)
    ld = C.autofill(o1)
    ck("★ เบอร์ตรงใบจ่ายลีด → ได้ Code", ld.code == "TLD9-7376", ld.code)
    ck("ได้ ADS / Account / ชื่อลูกค้า / ID LINE จากใบ", ld.ads == "รถครอบครัว 7 ที่นั่ง" and ld.account == "Oxlet ช่องหลัก"
       and ld.customer_name == "คุณสมชาย" and ld.line_id == "somchai99", (ld.ads, ld.account, ld.customer_name, ld.line_id))
    ck("★ ช่องทางจากใบแทนค่าตั้งต้นของระบบได้", ld.channel == "TikTok" and ld.auto.get("channel") == "ใบจ่ายลีด", ld.channel)
    ck("★ รถที่จับได้จากแชทไม่ถูกใบทับ", ld.car_model == "Camry" and "แคมรี่" in ld.car_text, ld.car_text)
    ck("จดว่ามาจากใบจ่ายลีดกลุ่มไหน", (ld.auto.get("_slip") or {}).get("group") == "ห้องจ่ายเบอร์ ทดสอบ", ld.auto)
    # คนแก้แล้ว ระบบไม่ทับ
    ok, msg = C.save_lead_field(o1, "phone", "081-111-2222", by="เอหนึ่ง")
    ck("แก้เบอร์ → ปรับรูปแบบให้", ok and ChatLead.objects.get(pk=ld.pk).phone == "0811112222", (ok, msg))
    ok, msg = C.save_lead_field(o1, "phone", "ไม่ใช่เบอร์")
    ck("เบอร์ผิดรูปแบบ = ปฏิเสธ", not ok and "เบอร์" in msg, msg)
    ok, msg = C.save_lead_field(o1, "sql_injection", "x")
    ck("ช่องที่ไม่รู้จัก = ปฏิเสธ", not ok, msg)
    ok, msg = C.save_lead_field(o1, "code", "X" * 40)
    ck("ยาวเกิน = ปฏิเสธ", not ok and "ยาวเกิน" in msg, msg)
    C.save_lead_field(o1, "channel", "", by="เอหนึ่ง")                  # คนลบช่องทางทิ้งเอง
    o1 = ChatOwner.objects.select_related("profile", "owner").get(pk=o1.id)
    ld = C.autofill(o1)
    ck("★ คนลบช่องไหนทิ้ง ระบบไม่เติมกลับ", ld.channel == "" and ld.auto.get("channel") == "คน", ld.channel)
    ck("★ คนแก้เบอร์แล้ว ระบบไม่ทับด้วยเบอร์จากแชท", ld.phone == "0811112222", ld.phone)
    ok, _ = C.save_lead_field(o1, "tags", ["ผ่อนได้", "ผ่อนได้", " ด่วน ", ""])
    ck("แท็ก: ตัดซ้ำ/ช่องว่าง", ok and ChatLead.objects.get(pk=ld.pk).tags == ["ผ่อนได้", "ด่วน"],
       ChatLead.objects.get(pk=ld.pk).tags)
    # ใบจ่ายลีดแบบย่อ — ระบบกลุ่มจ่ายเบอร์อ่านกลับได้
    st = C.slip_text(o1)
    back = parse_leadsheet(st) or {}
    ck("ใบจ่ายลีดย่อ: อ่านกลับด้วยตัวแกะของกลุ่มจ่ายเบอร์ได้", back.get("lead_code") == "TLD9-7376"
       and back.get("phone") == "0811112222" and back.get("assigned") == "เอหนึ่ง", back)
    ck("ใบจ่ายลีดย่อ: ไลฟ์ว่าง = ขีด", "ไลฟ์ : -" in st, st)
    # ผ่านหน้าเว็บ
    s_, d = J(SA1, "/connect/api/chat?id=%d" % o1.id)
    ck("เจ้าของเปิดแชท = ได้ข้อมูลลีด + แก้ได้", s_ == 200 and d.get("lead", {}).get("code") == "TLD9-7376"
       and d.get("leadEditable") is True, (s_, d.get("leadEditable")))
    lj = d.get("lead") or {}
    ck("ช่องอัตโนมัติมีครบ (ว/ด/ป · เซลล์ · ติดต่อ · จำนวนอัพเดท · อัพเดทล่าสุด)",
       lj.get("leadAt") and lj.get("seller") == "เอหนึ่ง" and "updates" in lj and "lastUpdate" in lj, lj)
    ddo = ((d.get("leadOptions") or {}).get("dropdowns") or {})
    ck("ตัวเลือก dropdown ชุดเดียวกับชีต (type / ประเภทลูกค้า / แจ้งหลักฐาน 3 ค่า)",
       "Very Hot" in ddo.get("lead_type", []) and "พนักงานบริษัท" in ddo.get("customer_type", [])
       and ddo.get("call_proof") == ["ส่งแล้ว", "ยังไม่ส่ง", "รอหลักฐาน"], ddo.get("call_proof"))
    ck("ยังอ่านชีตไม่ได้ = บอกว่าเป็นชุดที่จำไว้", ((d.get("leadOptions") or {}).get("source") or {}).get("fallback") is True)
    s_, d = J(SA1, "/connect/api/lead", {"id": o1.id, "field": "occupation", "value": "พนักงานบริษัท"})
    ck("เจ้าของบันทึกช่องได้", s_ == 200 and d.get("lead", {}).get("occupation") == "พนักงานบริษัท", (s_, d.get("error")))
    s_, d = J(SB1, "/connect/api/lead", {"id": o1.id, "field": "occupation", "value": "แอบแก้"})
    ck("★ คนที่ไม่ใช่เจ้าของแก้ไม่ได้", s_ == 403, s_)
    s_, d = J(ADM, "/connect/api/lead", {"id": o1.id, "field": "customer_name", "value": "คุณสมชาย ใจดี"})
    ck("แอดมินแก้ได้", s_ == 200, (s_, d.get("error")))
    s_, d = J(ADM, "/connect/api/inbox?view=all")
    ck("รายชื่อใช้ชื่อลูกค้าที่กรอก (แทนชื่อ LINE)", any(r["name"] == "คุณสมชาย ใจดี" for r in d.get("rows", [])))
    s_, d = J(ADM, "/connect/api/inbox?view=all&q=0811112222")
    ck("ค้นด้วยเบอร์ได้", [r["id"] for r in d.get("rows", [])] == [o1.id], [r["name"] for r in d.get("rows", [])])
    s_, d = J(ADM, "/connect/api/inbox?view=all&q=TLD9-7376")
    ck("ค้นด้วยเลขลีดได้", [r["id"] for r in d.get("rows", [])] == [o1.id], [r["name"] for r in d.get("rows", [])])
    C.assign(o4.id, None, by="แอดมิน")
    C.note_customer_message("U%032x" % 4, timezone.now(), "สวัสดีครับ")
    s_, d = J(SA1, "/connect/api/chat?id=%d" % o4.id)
    ck("★ คิวรอรับ (preview) ไม่ได้ข้อมูลลีด", s_ == 200 and "lead" not in d, list(d))
    s_, d = J(SA1, "/connect/api/lead", {"id": o4.id, "field": "phone", "value": "0812345678"})
    ck("★ คิวรอรับ แก้ข้อมูลลีดไม่ได้", s_ == 403, s_)
    leak3 = [pth for pth in ("/connect/api/chat?id=%d" % o1.id,) if leak.search(SA1.get(pth, secure=True).content.decode())]
    ck("ข้อมูลลีดไม่มี LINE user id หลุด", not leak3, leak3)
    # ลูกค้าจำลอง: เติมจากแชทของตัวเอง + ค่าตั้งต้นได้ (เจ้าของทดสอบระบบเติมอัตโนมัติด้วยลูกค้าจำลอง)
    #   แต่ "ไม่ค้นใบจ่ายลีด" — เบอร์ทดสอบอาจไปตรงใบของลูกค้าจริงแล้วดึงข้อมูลจริงมาปน
    GroupChat.objects.create(chat_type="group", group_id="C" + "9" * 32, group_name="ห้องจ่ายเบอร์ ทดสอบ",
                             message_id="slip-real-9999", sender_id="U%032x" % 77, direction="in", msg_type="text",
                             text="Ac Lead No. NLD10-9001\nชื่อลูกค้า : ลูกค้าจริงคนหนึ่ง\nเบอร์โทร : 0899999999\n@เอหนึ่ง",
                             sent_at=timezone.now())
    so = C.sim_customer("โทร 0899999999 สนใจแคมรี่")
    sl = C.autofill(ChatOwner.objects.select_related("profile").get(pk=so.id))
    ck("★ ลูกค้าจำลอง = เติมจากแชทของตัวเอง (เบอร์ · รุ่นรถ · ช่องทาง · สาขา)",
       sl.phone == "0899999999" and sl.car_model == "Camry" and sl.channel == "LINE@" and sl.branch == "ชลบุรี",
       (sl.phone, sl.car_model, sl.channel, sl.branch))
    ck("★ ลูกค้าจำลอง = ไม่ดึงใบจ่ายลีดของลูกค้าจริงมาปน", sl.code == "" and sl.customer_name == "",
       (sl.code, sl.customer_name))
    GroupChat.objects.filter(message_id="slip-real-9999").delete()   # ไม่ให้เลข 9001 ไปปนเทสต์เลขรันข้างล่าง
    C.sim_clear()
    ck("ล้างข้อมูลทดสอบ = ข้อมูลลีดของลูกค้าจำลองหายตาม", not ChatLead.objects.filter(pk=sl.pk).exists())

    print("[18] เลขลีด + ปุ่มจ่ายเบอร์ (ทดลอง — เก็บใน Postgres อย่างเดียว)")
    # ★ 6 ต.ค.69 ค่าตั้งต้นเปลี่ยนเป็น "ส่งเข้ากลุ่มจริง" — ส่วนนี้ (ถึง [29]) ทดสอบโหมดทดลองเดิม (สวิตช์ปิด)
    #   ส่วนส่งจริงอยู่ที่ [30]
    ck("ค่าตั้งต้น = ส่งใบเข้ากลุ่มจริง", C.DEFAULTS["slip_post"] is True and C.slip_post_on())
    C.save_cfg(dict(C.cfg(), slip_post=False))
    ck("ปิดสวิตช์ส่งเข้ากลุ่มได้", C.slip_post_on() is False)
    ck("★ อ่านเลขลีดเดือน 2 หลักได้ (ต.ค.-ธ.ค.)", (parse_leadsheet("Ac Lead No.   NLD10-8409") or {}).get("lead_code") == "NLD10-8409")
    ck("ยังอ่านเลขแบบเดิมได้", (parse_leadsheet("Ac Lead No. TLD9-7376") or {}).get("lead_code") == "TLD9-7376"
       and (parse_leadsheet("Ac Lead No. TLD-10187") or {}).get("lead_code") == "TLD-10187")

    class _L:                                                     # ข้อมูลลีดจำลองสำหรับเดาตัวหน้า
        def __init__(self, t="", ch=""):
            self.lead_type, self.channel = t, ch
    sp = lambda t="", ch="", team="": C.suggest_prefix(_L(t, ch), team)
    ck("Moderate → NLD", sp("Moderate")["base"] == "NLD")
    ck("Hot → WLD", sp("Hot")["base"] == "WLD")
    ck("Very Hot → HLD", sp("Very Hot")["base"] == "HLD")
    ck("BLD → BLD", sp("BLD")["base"] == "BLD")
    ck("ไม่มี type + ช่องทาง TikTok → TLD", sp("", "LIVE Tiktok / ช่องขายบอส")["base"] == "TLD")
    ck("TikTokAds → TALD", sp("", "TikTokAds")["base"] == "TALD")
    ck("ไม่มีอะไรเลย → NLD", sp()["base"] == "NLD")
    ck("type RJ → แนะนำ R", sp("RJ")["reject"] is True)
    ck("จ่ายให้เทเลเซลล์ → แนะนำ A", sp("Moderate", team="ADMIN")["admin"] is True)
    ck("ประกอบตัวหน้า R+A+ฐาน", C.build_prefix("NLD", True, True) == "RANLD" and C.build_prefix("xx") == "NLD")

    GID = "C" + "8" * 32
    for i, code in enumerate(("NLD10-8409", "TLD10-8410", "RNLD10-9999")):     # R = เคสเก่าส่งต่อ ไม่นับ
        GroupChat.objects.create(chat_type="group", group_id=GID, group_name="ห้องจ่ายเบอร์ บ้านเก่า",
                                 message_id="code-%d" % i, sender_id="U%032x" % 78, direction="in",
                                 msg_type="text", text="Ac Lead No.   %s\nเบอร์โทร : 08%08d" % (code, i),
                                 sent_at=timezone.now() - timedelta(minutes=5 - i))
    ck("เลขรันล่าสุด = มากสุดของใบจ่ายลีด (ไม่นับ R)", C.last_running() == 8410, C.last_running())
    MON = timezone.localdate().month
    ck("เลขถัดไป = ตัวหน้า+เดือน+เลขรัน", C.next_code("NLD") == "NLD%d-8411" % MON, C.next_code("NLD"))

    CALLS.clear()
    C.assign(o4.id, None, by="เทสต์")
    ChatLead.objects.filter(chat_id=o4.id).delete()
    s_, d = J(ADM, "/connect/api/chat?id=%d" % o4.id)
    ch = d.get("codeHelp") or {}
    ck("แอดมินได้ตัวช่วยออกเลข", ch.get("next") == 8411 and ch.get("month") == MON, ch)
    s_, d = J(SA1, "/connect/api/chat?id=%d" % o1.id)
    ck("เซลล์ไม่ได้ปุ่มจ่ายเบอร์", "codeHelp" not in d)
    s_, d = J(SA1, "/connect/api/assign_lead", {"id": o4.id, "emp": A1.id, "base": "NLD"})
    ck("★ เซลล์จ่ายเบอร์ไม่ได้", s_ == 403, s_)
    s_, d = J(ADM, "/connect/api/assign_lead", {"id": o4.id, "emp": 0, "base": "NLD"})
    ck("ไม่เลือกเซลล์ = ปฏิเสธ", s_ == 400 and "เลือกเซลล์" in d.get("error", ""), d)
    s_, d = J(ADM, "/connect/api/assign_lead", {"id": o4.id, "emp": A1.id, "base": "WLD"})
    ld4 = ChatLead.objects.get(chat_id=o4.id)
    ck("จ่ายเบอร์ได้ + ออกเลขตามกติกา", s_ == 200 and ld4.code == "WLD%d-8411" % MON, (s_, d, ld4.code))
    ck("type ว่าง → เติมตามตัวหน้า (WLD = Hot)", ld4.lead_type == "Hot", ld4.lead_type)
    ck("ติดป้ายทดลอง + จดคน/เวลาจ่าย", ld4.code_demo is True and ld4.assigned_at and ld4.assigned_by == "admin",
       (ld4.code_demo, ld4.assigned_by))
    ck("โอนลูกค้าให้เซลล์ที่เลือก", ChatOwner.objects.get(pk=o4.id).owner_id == A1.id)
    ck("ประวัติบอกว่าจ่ายเบอร์อะไร", ChatOwnerLog.objects.filter(chat_id=o4.id, action="assign",
                                                             note__contains="จ่ายเบอร์ WLD").exists())
    ck("★ ไม่ลงชีต/ไม่โพสต์กลุ่ม (ไม่มีคำขอออกนอกระบบ)", not [c for c in CALLS if c[0] == "post"], CALLS)
    st4 = C.slip_text(ChatOwner.objects.select_related("profile", "owner").get(pk=o4.id))
    ck("ใบย่อขึ้นป้ายทดลองบรรทัดแรก", st4.startswith("⚠️ ทดลอง"), st4[:40])
    ck("ใบย่อยังอ่านเลขกลับได้", (parse_leadsheet(st4) or {}).get("lead_code") == "WLD%d-8411" % MON)
    # คนถัดไปได้เลขต่อ (นับเลขที่โหมดทดลองออกไปแล้วด้วย)
    C.assign(o2.id, None, by="เทสต์"); ChatLead.objects.filter(chat_id=o2.id).update(code="", assigned_at=None)
    s_, d = J(ADM, "/connect/api/assign_lead", {"id": o2.id, "emp": A2.id, "base": "NLD", "admin": True})
    ck("คนถัดไปได้เลขต่อ + ตัวหน้า A", ChatLead.objects.get(chat_id=o2.id).code == "ANLD%d-8412" % MON,
       ChatLead.objects.get(chat_id=o2.id).code)
    ChatLead.objects.filter(chat_id=o2.id).update(code="", assigned_at=None)
    s_, d = J(ADM, "/connect/api/assign_lead", {"id": o2.id, "emp": A2.id, "base": "NLD", "code": "WLD%d-8411" % MON})
    ck("★ เลขซ้ำกับลูกค้าคนอื่น = ปฏิเสธ", s_ == 400 and "ถูกใช้" in d.get("error", ""), d)
    s_, d = J(ADM, "/connect/api/assign_lead", {"id": o2.id, "emp": A2.id, "base": "NLD", "code": "abc"})
    ck("เลขผิดรูปแบบ = ปฏิเสธ", s_ == 400 and "รูปแบบ" in d.get("error", ""), d)
    s_, d = J(ADM, "/connect/api/chat?id=%d" % o4.id)
    ck("จ่ายแล้วหน้าเว็บได้ข้อมูลการจ่าย", (d.get("lead") or {}).get("assignedAt") and (d.get("lead") or {}).get("codeDemo") is True)
    # ★ มีเลขอยู่แล้ว (เลขจริงจากใบจ่ายลีด/คนกรอก) = ห้ามออกเลขทดลองทับ — หน้าเว็บค้างของเก่าก็โดนกันที่เซิร์ฟเวอร์
    ChatLead.objects.filter(chat_id=o2.id).update(code="NLD10-8000", code_demo=False, assigned_at=None)
    s_, d = J(ADM, "/connect/api/assign_lead", {"id": o2.id, "emp": A2.id, "base": "NLD"})
    ck("★ มีเลขลีดอยู่แล้ว = ไม่ออกเลขทับ", s_ == 400 and "มีเลขลีด" in d.get("error", "")
       and ChatLead.objects.get(chat_id=o2.id).code == "NLD10-8000", (s_, d))
    # เลขที่กรอกเอง → type ตามตัวหน้าของ "เลขนั้น" ไม่ใช่ตัวหน้าที่เลือกในกล่อง
    ChatLead.objects.filter(chat_id=o2.id).update(code="", lead_type="", assigned_at=None)
    s_, d = J(ADM, "/connect/api/assign_lead", {"id": o2.id, "emp": A2.id, "base": "NLD", "code": "rahld%d-8500" % MON})
    ld2 = ChatLead.objects.get(chat_id=o2.id)
    ck("เลขที่กรอกเอง: type ตามตัวหน้าของเลข (RAHLD → Very Hot)",
       s_ == 200 and ld2.code == "RAHLD%d-8500" % MON and ld2.lead_type == "Very Hot", (s_, d, ld2.code, ld2.lead_type))
    # ★ โอนไม่สำเร็จ = เลขต้องไม่ค้างอยู่กับลูกค้าที่ไม่มีเซลล์ (ย้อนทั้งธุรกรรม)
    ChatLead.objects.filter(chat_id=o2.id).update(code="", assigned_at=None)
    C.assign(o2.id, None, by="เทสต์")
    _real_assign = C.assign
    C.assign = lambda *a, **k: (False, "โอนไม่ได้ (ทดสอบ)")
    try:
        ok_, msg_ = C.assign_lead(ChatOwner.objects.get(pk=o2.id), A2, "NLD", by="เทสต์")
    finally:
        C.assign = _real_assign
    ld2 = ChatLead.objects.get(chat_id=o2.id)
    ck("★ โอนไม่สำเร็จ = ไม่เก็บเลขค้าง", ok_ is False and ld2.code == "" and ld2.assigned_at is None,
       (ok_, msg_, ld2.code))

    # ═════════════════════════════════════════════════════════════════════
    print("[19] dropdown ของฟอร์มลีด = ชุดเดียวกับชีตลีด (อ่านแท็บเดือนล่าสุด ทุกชั่วโมง)")
    from urllib.parse import unquote
    from dashboard.services.fetch_dashboard import bangkok_now
    from dashboard.services.google_sheets import LEADS_COL, _THAI_MONTHS
    nb = bangkok_now()
    be2 = (nb.year + 543) % 100
    CUR = "%s %d" % (_THAI_MONTHS[nb.month - 1], be2)
    nm = nb.month % 12 + 1
    NXT = "%s %d" % (_THAI_MONTHS[nm - 1], be2 + (1 if nm == 1 else 0))          # เดือนหน้า = อนาคต ห้ามเลือก
    pm = (nb.month - 2) % 12 + 1
    PRV = "%s %d" % (_THAI_MONTHS[pm - 1], be2 - (1 if pm == 12 else 0))
    # หัวตาราง "สลับตำแหน่ง" จากของจริง (สาขาอยู่คอลัมน์ F) — ต้องจับด้วยชื่อหัวตาราง ไม่ใช่ตำแหน่ง
    HDR = ["ว/ด/ป", "เบอร์โทร", "เวลา", "Code", "เซลล์", "สาขา", "Admin", "ช่องทาง", "ทีมไลฟ์", "type", "ADS",
           "รถลูกค้าถาม", "CAR / สูตร", "แจ้งหลักฐาน\nการโทร", "FOCUS"]
    LISTS = {4: ["เอหนึ่ง", "เอสอง"], 5: ["ชลบุรี", "เทพารักษ์ "], 6: ["เฟิร์น", "หมิว", "แอดมินใหม่"],
             7: ["เพจบ้านเก่า", "LINE@", "Line@ / TIKTOK"], 8: ["Live Sale"], 9: ["Very Hot", "Hot", "Moderate"],
             12: ["Camry", "City 5 ประตู", "Civic FE", "Civic FC", "ลูกค้าไม่ตอบ", "Benz"],
             13: ["ส่งแล้ว", "ยังไม่ส่ง", "รอหลักฐาน"]}
    SELL = ["เอหนึ่ง"] * 12 + ["เอสอง"] * 10 + ["บี"] * 200
    BRAN = ["เทพารักษ์"] * 12 + ["ชลบุรี", "เทพารักษ์"] * 5 + ["ชลบุรี"] * 200
    SEEN = []

    def _route(url):
        u = unquote(url)
        SEEN.append(u)
        if "fields=sheets.properties.title" in u:
            return _R(200, {"sheets": [{"properties": {"title": t}} for t in ("รวม sheet", PRV, " " + CUR, NXT)]})
        if "values:batchGet" in u:
            return _R(200, {"valueRanges": [{"values": [[s] for s in SELL]}, {"values": [[b] for b in BRAN]}]})
        if "includeGridData=true" in u:
            vals = []
            for ci in range(len(HDR)):
                if ci in LISTS:
                    vals.append({"dataValidation": {"condition": {"type": "ONE_OF_LIST", "values": [
                        {"userEnteredValue": v} for v in LISTS[ci]]}, "showCustomUi": True}})
                elif ci == 14:                                    # FOCUS = dropdown ที่อ้างช่วงเซลล์
                    vals.append({"dataValidation": {"condition": {"type": "ONE_OF_RANGE", "values": [
                        {"userEnteredValue": "='ตั้งค่า'!A1:A2"}]}}})
                else:
                    vals.append({})
            return _R(200, {"sheets": [{"data": [{"rowData": [{"values": vals}]}]}]})
        if "/values/" in u and u.endswith("!1:1"):
            return _R(200, {"values": [HDR]})
        if "/values/'ตั้งค่า'!A1:A2" in u:
            return _R(200, {"values": [["FOCUS"], ["Concentrate "]]})
        return _R(404, {"error": "unknown " + u[-60:]})

    _real_creds = _GS._get_credentials
    _GS._get_credentials = lambda: type("Cr", (), {"token": "fake-token"})()
    SHEET_ROUTE[0] = _route
    try:
        got = _REAL_FLD()
        cols = got.get("columns") or {}
        ck("เลือกแท็บเดือนล่าสุด (ข้ามเดือนหน้า/เดือนก่อน · ตัดช่องว่างชื่อแท็บ)", got.get("tab") == CUR, got.get("tab"))
        ck("★ จับคอลัมน์ด้วยชื่อหัวตาราง (สาขาอยู่ F ก็ยังได้) + ตัดช่องว่างท้ายตัวเลือก",
           cols.get(str(LEADS_COL.branch)) == ["ชลบุรี", "เทพารักษ์"], cols.get(str(LEADS_COL.branch)))
        ck("dropdown แบบอ้างช่วงเซลล์ (FOCUS) ก็อ่านได้", cols.get(str(LEADS_COL.focus)) == ["FOCUS", "Concentrate"],
           cols.get(str(LEADS_COL.focus)))
        ck("สาขาต่อเซลล์: ชัด (≥90%) เท่านั้น · ครึ่งๆ ไม่เดา",
           got.get("branchBySeller") == {"เอหนึ่ง": "เทพารักษ์", "บี": "ชลบุรี"}, got.get("branchBySeller"))
        ck("สาขาภาพรวม = สาขาที่ลีดเกือบทั้งหมดไป", got.get("branchTop") == "ชลบุรี", got.get("branchTop"))
        grid = [u for u in SEEN if "includeGridData" in u]
        bget = [u for u in SEEN if "values:batchGet" in u]
        ck("★ ไม่ดึงข้อมูลลูกค้า: ขอแค่กฎ dropdown + หัวตาราง + คอลัมน์ เซลล์/สาขา",
           grid and all("fields=sheets(data(rowData(values(dataValidation))))" in u for u in grid)
           and bget and all(("!E2:E" in u and "!F2:F" in u) for u in bget)
           and not any("formattedValue" in u for u in SEEN), SEEN[-3:])

        # เก็บลง KV → ฟอร์มใช้ชุดใหม่
        _GS.fetch_lead_dropdowns = _REAL_FLD
        res = C.refresh_dropdowns(force=True)
        ck("อ่านชีตแล้วเก็บไว้", res.get("dropdowns") == CUR, res)
        dd = C.dropdowns()
        ck("ฟอร์มใช้ตัวเลือกชุดใหม่จากชีต", dd["fields"].get("admin_name") == ["เฟิร์น", "หมิว", "แอดมินใหม่"]
           and dd.get("fallback") is False, dd["fields"].get("admin_name"))
        ck("คอลัมน์ที่ฟอร์มไม่มีช่อง (เซลล์) ไม่ถูกเอามาเป็นตัวเลือก", "sales_rep" not in dd["fields"]
           and all(f in C.LEAD_FIELDS for f in dd["fields"]), list(dd["fields"]))
        ck("เทียบค่าแบบไม่สนช่องว่าง/ตัวพิมพ์", C.dd_pick("admin_name", " แอดมินใหม่ ") == "แอดมินใหม่"
           and C.dd_pick("admin_name", "ไม่มีคนนี้") == "")
        ck("รุ่นรถตรงตัวเลือก → ได้ชื่อตามชีต", (C.car_in("มี civic fe ไหมครับ") or ("",))[0] == "Civic FE",
           C.car_in("มี civic fe ไหมครับ"))
        ck("★ รุ่นกำกวม (city เฉยๆ) → ได้แค่ข้อความ ไม่เดาว่า 4/5 ประตู",
           (C.car_in("honda city ปี 20 ครับ") or ("x",))[0] == "", C.car_in("honda city ปี 20 ครับ"))
        ck("ตัวเลือกที่ไม่ใช่ชื่อรุ่น (ลูกค้าไม่ตอบ) ไม่ถูกใช้จับรถ", "ลูกค้าไม่ตอบ" not in C._vocab()["names"].values())

        # สาขาตามเซลล์เจ้าของ แทนค่าตั้งต้นของระบบ — แต่ไม่แทนที่คนเลือก
        o1 = ChatOwner.objects.select_related("profile", "owner").get(pk=o1.id)
        ck("(ก่อนหน้า) สาขาเป็นค่าตั้งต้นของระบบ", C.lead_of(o1).auto.get("branch") == "ระบบ", C.lead_of(o1).auto)
        ldb = C.autofill(o1)
        ck("★ สาขา = สาขาของเซลล์ที่รับลูกค้า (แทนค่าตั้งต้นได้)", ldb.branch == "เทพารักษ์", ldb.branch)
        C.save_lead_field(o1, "branch", "ชลบุรี", by="เอหนึ่ง")
        ldb = C.autofill(ChatOwner.objects.select_related("profile", "owner").get(pk=o1.id))
        ck("★ คนเลือกสาขาเองแล้ว ระบบไม่ทับ", ldb.branch == "ชลบุรี" and ldb.auto.get("branch") == "คน", ldb.branch)

        s_, d = J(ADM, "/connect/api/chat?id=%d" % o1.id)
        lo = d.get("leadOptions") or {}
        ck("หน้าเว็บได้ตัวเลือกชุดใหม่ + บอกแท็บที่อ่าน", "แอดมินใหม่" in (lo.get("dropdowns") or {}).get("admin_name", [])
           and (lo.get("source") or {}).get("tab") == CUR and (lo.get("source") or {}).get("fallback") is False, lo.get("source"))

        # ค่าที่ระบบเคยใส่ไว้ก่อนมี dropdown ("LINE OA") → แก้ให้ตรงตัวเลือกของชีต · ค่าจากคน/ใบจ่ายลีด ไม่แตะ
        def _set_ch(src):
            l_ = C.lead_of(o1)
            l_.channel = "LINE OA"
            l_.auto = dict(l_.auto or {}, channel=src)
            l_.save()
            return C.autofill(ChatOwner.objects.select_related("profile", "owner").get(pk=o1.id))
        ldb = _set_ch("ระบบ")
        ck("★ ค่าเก่าของระบบที่ไม่อยู่ในตัวเลือกชีต (LINE OA) → แก้เป็น LINE@",
           ldb.channel == "LINE@" and ldb.auto.get("channel") == "ระบบ", (ldb.channel, ldb.auto.get("channel")))
        for src_ in ("คน", "ใบจ่ายลีด"):
            ldb = _set_ch(src_)
            ck("ค่าที่มาจาก%s ไม่ถูกแก้ แม้ไม่อยู่ในตัวเลือกชีต" % src_, ldb.channel == "LINE OA", ldb.channel)

        # ชีตอ่านไม่ได้ = ไม่ทับของเดิม + เว้น 15 นาที
        _GS.fetch_lead_dropdowns = _no_sheet
        res = C.refresh_dropdowns(force=True)
        ck("อ่านไม่ได้ = แจ้งว่าล้ม", res.get("dropdowns") == "fail", res)
        ck("★ อ่านไม่ได้ = ตัวเลือกเดิมยังอยู่ (ไม่กลายเป็นช่องพิมพ์เปล่า)",
           C.dropdowns()["fields"].get("admin_name") == ["เฟิร์น", "หมิว", "แอดมินใหม่"])
        ck("เพิ่งล้ม = ยังไม่ลองใหม่ (เว้น 15 นาที)", C._dd_due() is False)
        st_ = C._dd_state()
        old = (timezone.now() - timedelta(hours=2)).isoformat()
        cache_store.set_kv(C.DD_KEY, dict(st_, at=old, failAt=(timezone.now() - timedelta(minutes=20)).isoformat()))
        ck("อ่านครั้งล่าสุดเกิน 1 ชม. + ล้มเกิน 15 นาที = ถึงเวลาอ่านใหม่", C._dd_due() is True)
        cache_store.set_kv(C.DD_KEY, dict(st_, at=old, failAt=(timezone.now() - timedelta(minutes=5)).isoformat()))
        ck("ล้มไปไม่ถึง 15 นาที = ยังไม่อ่าน", C._dd_due() is False)
        cache_store.set_kv(C.DD_KEY, dict(st_, at=old, failAt=""))
        _GS.fetch_lead_dropdowns = _REAL_FLD
        res = C.tick()
        ck("cron tick อ่าน dropdown ใหม่เมื่อถึงเวลา", res.get("dropdowns") == CUR, res)
        ck("tick รอบถัดไปไม่อ่านซ้ำ (ยังไม่ครบชั่วโมง)", "dropdowns" not in C.tick())
    finally:
        SHEET_ROUTE[0] = None
        _GS._get_credentials = _real_creds
        _GS.fetch_lead_dropdowns = _no_sheet

    # ═════════════════════════════════════════════════════════════════════
    print("[20] รถที่ลูกค้าถาม — ยี่ห้อ + ปีที่พิมพ์แยกข้อความ (4 ต.ค.69 · เจ้าของแจ้ง \"ลูกค้าก็บอกอยู่นะ อีซูซุ\")")
    cache_store.set_kv(C.DD_KEY, {})                  # กลับไปใช้ชุดที่จำไว้ (มี D Max · MuX · Benz · Yaris Cross …)
    C._DD.update(at=0.0, val=None)
    ck("บอกแค่ยี่ห้อ = รู้ว่าถามรถ แต่ไม่เดารุ่น", C.car_in("อีซูซุ") == ("", "อีซูซุ"), C.car_in("อีซูซุ"))
    ck("ยี่ห้อที่ชีตมีตัวเลือกระดับยี่ห้อ = ได้ CAR/สูตร", (C.car_in("สนใจเบนซ์ครับ") or ("",))[0] == "Benz",
       C.car_in("สนใจเบนซ์ครับ"))
    ck("ยี่ห้ออังกฤษก็จับได้", C.car_in("Isuzu มีไหม") == ("", "Isuzu มีไหม"), C.car_in("Isuzu มีไหม"))
    ck("★ เกียร์ออโต้ ≠ Kia", C.car_in("เกียร์ออโต้ไหมครับ") is None, C.car_in("เกียร์ออโต้ไหมครับ"))
    ck("ดีแม็ค (สะกดอีกแบบ) → D Max", (C.car_in("ดีแม็ค ปี 15") or ("",))[0] == "D Max", C.car_in("ดีแม็ค ปี 15"))
    ck("★ ชื่อไทยยาวก่อน: ยาริสครอส → Yaris Cross (ไม่ใช่ยาริสเฉยๆ)",
       (C.car_in("หายาริสครอสครับ") or ("",))[0] == "Yaris Cross", C.car_in("หายาริสครอสครับ"))
    ck("มาสด้า 2 → Mazda2 (ไม่ใช่แค่ยี่ห้อ)", (C.car_in("มาสด้า 2 ปี 18") or ("",))[0] == "Mazda2",
       C.car_in("มาสด้า 2 ปี 18"))
    ck("ข้อความทั่วไปไม่นับเป็นรถ", C.car_in("มีคันไหนบ้าง") is None and C.car_in("โทรมา 0902483727") is None)
    ck("ปีแบบไม่มีคำว่าปีก็นับ · เลขกลางเบอร์โทรไม่นับ", C._has_spec("2015-2017") and not C._has_spec("0902483727"))

    o5id = o3.id

    def _car(msgs, fresh=True):
        if fresh:
            ChatLead.objects.filter(chat_id=o5id).delete()
        return C.autofill(ChatOwner.objects.select_related("profile", "owner").get(pk=o5id), msgs)

    ld = _car(["สวัสดีครับ", "อีซูซุ", "ปี2015-2017", "มีคันไหนบ้าง"])
    ck("★ เคสจริง: อีซูซุ + ปี2015-2017 (คนละข้อความ) → รถลูกค้าถามครบทั้งคู่",
       ld.car_text == "อีซูซุ ปี2015-2017" and ld.auto.get("car_text") == "แชท", (ld.car_text, ld.auto))
    ck("ไม่เดารุ่นให้ (อีซูซุ มีหลายรุ่นในชีต)", ld.car_model == "", ld.car_model)
    ck("ใบจ่ายลีดขึ้นรถแล้ว (เดิม \"รถ : -\")",
       "รถ : อีซูซุ ปี2015-2017" in C.slip_text(ChatOwner.objects.get(pk=o5id)), C.slip_text(ChatOwner.objects.get(pk=o5id)))
    ld = _car(["อีซูซุ"])
    ld = _car(["อีซูซุ", "ปี2015-2017"], fresh=False)
    ck("★ ลูกค้าพิมพ์ปีตามมาทีหลัง → เติมต่อจากของเดิมที่ระบบใส่ไว้", ld.car_text == "อีซูซุ ปี2015-2017", ld.car_text)
    C.save_lead_field(ChatOwner.objects.get(pk=o5id), "car_text", "หากระบะ", by="เอหนึ่ง")
    ld = _car(["อีซูซุ", "ปี2015-2017", "งบ 4 แสน"], fresh=False)
    ck("★ คนแก้แล้ว ระบบไม่เติมต่อทับ", ld.car_text == "หากระบะ" and ld.auto.get("car_text") == "คน", ld.car_text)
    ld = _car(["อีซูซุ", "ดีแม็กซ์ ปี 2016", "ดาวน์ 0 ได้ไหม"])
    ck("ยี่ห้อ + รุ่นชัดข้อความถัดไป → CAR/สูตร D Max + ข้อความรวมยี่ห้อ",
       ld.car_model == "D Max" and ld.car_text == "อีซูซุ ดีแม็กซ์ ปี 2016", (ld.car_model, ld.car_text))
    ld = _car(["แคมรี่ ปี 20", "หรือ civic fe ก็ได้"])
    ck("รุ่นชัดคันอื่นในข้อความถัดไป = คนละคัน ไม่เอามาต่อ",
       ld.car_model == "Camry" and ld.car_text == "แคมรี่ ปี 20", (ld.car_model, ld.car_text))
    ld = _car(["งบ 3 แสน", "ฮอนด้า"])
    ck("งบที่บอกก่อนชื่อรถ ก็ต่อเข้ามา", ld.car_text == "งบ 3 แสน ฮอนด้า", ld.car_text)
    ld = _car(["อีซูซุ", "ปี 2015 " + "ก" * 100])
    ck("ข้อความยาว (ไม่ใช่สเปกสั้นๆ) ไม่เอามาต่อ", ld.car_text == "อีซูซุ", ld.car_text)

    # ═════════════════════════════════════════════════════════════════════
    print("[21] แท็บ \"จ่ายเบอร์\" ของแอดมิน (4 ต.ค.69 · เจ้าของถาม \"ขาดหน้าแอดมินจ่ายเบอร์มั้ย\")")
    NEW = C.note_customer_message(cust(201, "ลูกค้าใหม่ทักมา").user_id, timezone.now(), "มี civic ไหม 0833330001")
    # ลูกค้าเก่าที่ทักมาก่อนเปิด Connect (มีแชทเก่า ไม่ได้ทักกลับมา) → แถวจาก sync_rows ไม่มีรอบรอ/ประวัติ
    OLDP = cust(202, "ลูกค้าเก่าก่อนมี Connect")
    GroupChat.objects.create(chat_type="user", message_id="old-202", sender_id=OLDP.user_id, direction="in",
                             msg_type="text", text="สวัสดีครับ", sent_at=timezone.now() - timedelta(days=20))
    C.sync_rows(force=True)
    OLD = ChatOwner.objects.get(profile=OLDP)
    # แอดมินตอบไปแล้ว (ไม่มีรอบรอ ไม่มีเจ้าของ) แต่ยังไม่ได้จ่ายเบอร์ → ต้องยังอยู่ในแท็บ
    REP = C.note_customer_message(cust(203, "แอดมินตอบแล้ว").user_id, timezone.now(), "ผ่อนเท่าไหร่ ไอดีไลน์ rep_line1")
    C.note_reply(REP.profile.user_id, None, timezone.now(), "เดือนละ 8 พันครับ", by="admin")
    REP.refresh_from_db()
    COD = C.note_customer_message(cust(204, "มีเลขแล้ว").user_id, timezone.now(), "สนใจครับ")
    ChatLead.objects.create(chat=COD, code="NLD10-8001")

    def tocode_ids():
        return [r["id"] for r in C.inbox("tocode", admin=True)]

    ids = tocode_ids()
    ck("ลูกค้าใหม่ที่ยังไม่มีเลข = อยู่ในแท็บ", NEW.id in ids, ids)
    ck("★ แอดมินตอบแล้วแต่ยังไม่จ่ายเบอร์ = ยังอยู่", REP.awaiting_since is None and REP.id in ids, ids)
    ck("★ ลูกค้าเก่าก่อนเปิด Connect (ไม่ได้ทักกลับ) = ไม่นับ", OLD.id not in ids, ids)
    ck("มีเลขลีดแล้ว = ไม่อยู่", COD.id not in ids, ids)
    ck("ตัวเลขบนแท็บตรงกับรายการ", C.counts(admin=True).get("tocode") == len(ids), (C.counts(admin=True), len(ids)))
    ck("ลูกค้าที่รอคำตอบขึ้นก่อนคนที่ตอบไปแล้ว", ids.index(NEW.id) < ids.index(REP.id), ids)
    rowc = next((r for r in C.inbox("all", admin=True) if r["id"] == COD.id), {})
    ck("รายชื่อมีเลขลีดให้โชว์เป็นป้าย", rowc.get("code") == "NLD10-8001", rowc.get("code"))

    s_, d = J(ADM, "/connect/api/inbox?view=tocode")
    ck("API: แอดมินเปิดแท็บจ่ายเบอร์ได้", s_ == 200 and d.get("view") == "tocode"
       and NEW.id in [r["id"] for r in d.get("rows", [])] and "tocode" in d.get("counts", {}), (s_, d.get("view")))
    s_, d = J(SA1, "/connect/api/inbox?view=tocode")
    ck("★ เซลล์ขอแท็บจ่ายเบอร์ = ได้แท็บของตัวเองแทน (ไม่เห็นลูกค้าคนอื่น)",
       s_ == 200 and d.get("view") != "tocode" and "tocode" not in d.get("counts", {}), (s_, d.get("view")))

    # ไม่ใช่ลีดขาย → "ไม่ต้องจ่ายเบอร์"
    s_, d = J(SA1, "/connect/api/assign_lead", {"id": NEW.id, "skip": True})
    ck("★ เซลล์กด \"ไม่ต้องจ่ายเบอร์\" ไม่ได้", s_ == 403, s_)
    s_, d = J(ADM, "/connect/api/assign_lead", {"id": NEW.id, "skip": True})
    ck("แอดมินกด \"ไม่ต้องจ่ายเบอร์\" ได้", s_ == 200 and d.get("ok"), (s_, d))
    ck("★ ออกจากแท็บจ่ายเบอร์", NEW.id not in tocode_ids())
    s_, d = J(ADM, "/connect/api/chat?id=%d" % NEW.id)
    nc = (d.get("lead") or {}).get("noCode") or {}
    ck("หน้าเว็บรู้ว่ากดไม่ต้องจ่ายเบอร์ไว้ + ใครกด", nc.get("by") == "admin" and nc.get("at"), nc)
    ck("ป้ายนี้ไม่โผล่เป็นช่องที่ระบบเติมให้", "_nocode" not in ((d.get("lead") or {}).get("auto") or {}))
    s_, d = J(ADM, "/connect/api/assign_lead", {"id": NEW.id, "skip": False})
    ck("เอากลับมาจ่ายเบอร์ได้", s_ == 200 and NEW.id in tocode_ids(), (s_, d))
    s_, d = J(ADM, "/connect/api/assign_lead", {"id": COD.id, "skip": True})
    ck("มีเลขลีดแล้ว กดไม่ต้องจ่ายเบอร์ = ปฏิเสธ", s_ == 400 and "มีเลขลีด" in d.get("error", ""), (s_, d))
    # กดไม่ต้องจ่ายไว้ แล้วเปลี่ยนใจจ่ายเบอร์ → ป้ายเดิมต้องไม่ค้าง
    C.mark_no_code(ChatOwner.objects.get(pk=NEW.id), True, by="admin")
    n0 = len(CALLS)
    s_, d = J(ADM, "/connect/api/assign_lead", {"id": NEW.id, "emp": A1.id, "base": "NLD"})
    ldn = ChatLead.objects.get(chat_id=NEW.id)
    ck("จ่ายเบอร์หลังกดไม่ต้องจ่าย = ได้เลข + ล้างป้าย", s_ == 200 and ldn.code and "_nocode" not in (ldn.auto or {}),
       (s_, d, ldn.code, ldn.auto))
    ck("จ่ายแล้วออกจากแท็บ", NEW.id not in tocode_ids())
    ck("★ จ่ายเบอร์ไม่มีคำขอออกนอกระบบ (ไม่ลงชีต/ไม่โพสต์กลุ่ม)", not [c for c in CALLS[n0:] if c[0] == "post"], CALLS[n0:])
    # ลูกค้าเก่าทักกลับมาใหม่ = เป็นลีดอีกรอบ → เข้าแท็บ
    C.note_customer_message(OLDP.user_id, timezone.now(), "ยังมีรถไหมครับ โทร 0833330002")
    ck("ลูกค้าเก่าทักกลับมา = เข้าแท็บจ่ายเบอร์", OLD.id in tocode_ids())

    # ═════════════════════════════════════════════════════════════════════
    print("[22] ห้องพัก Lead (\"ADMIN เก็บ Lead\") — ใบร่างยังไม่มีเลข → ใบจริงในห้องจ่ายเบอร์")
    from checkout import leadpark as LP

    def slip(code, acc="", line="", phone="", ch="Live tiktok ช่องขายบอส", car="Yaris ativ", tag=""):
        return ("Ac Lead No.   %s\nAds  :   \nชื่อ Account : %s\nชื่อลูกค้า :      \nID LINE : %s\nชื่อไลน์ :   \n"
                "เบอร์โทร : %s\nช่องทาง  :    %s\nรถ : %s\nไลฟ์ :   live sale\nเพิ่มเติม  :  \n\nติดต่อได้เลยนะครับ\n%s"
                % (code, acc, line, phone, ch, car, ("@" + tag) if tag else ""))

    d = LP.parse_draft(slip("TLD10-", acc="บัญชีทดสอบ", line="abc0812345678"))
    ck("ใบร่าง: ตัวหน้า+เดือน ไม่มีเลขรัน", d and d["prefix"] == "TLD10-" and d["month"] == 10 and d["type"] == "TLD", d)
    ck("★ เบอร์ที่ฝังอยู่ใน ID LINE ก็จับได้", d and d["phones"] == ["0812345678"], d and d["phones"])
    ck("ใบจริง (มีเลข) ไม่ใช่ใบร่าง", LP.parse_draft(slip("TLD10-8500", tag="เอหนึ่ง")) is None)
    ck("ใบร่างตัวหน้า R/A แยกได้", (LP.parse_draft(slip("RATLD9-")) or {}).get("reject") is True
       and (LP.parse_draft(slip("ATLD9-")) or {}).get("admin") is True)
    ck("ข้อความทั่วไปไม่ใช่ใบร่าง", LP.parse_draft("รับทราบครับ") is None and LP.parse_draft("7364 รอตอบ") is None)
    ck("★ ใบจริงเว้นวรรคหลังขีด (RTLD9- 6456/1) อ่านได้ + เลขไม่มีช่องว่าง",
       (parse_leadsheet(slip("RTLD9- 6456/1")) or {}).get("lead_code") == "RTLD9-6456",
       parse_leadsheet(slip("RTLD9- 6456/1")))
    ck("★ ใบร่างที่บรรทัดถัดไปขึ้นต้นด้วยเบอร์ ไม่กลายเป็นเลขลีดปลอม",
       parse_leadsheet("Ac Lead No.   TLD10-\n0812345678\nช่องทาง : TikTok") is None
       and LP.parse_draft("Ac Lead No.   TLD10-\n0812345678\nช่องทาง : TikTok") is not None)
    ck("ช่อง *เพิ่มเติม* (ตัวหนาแบบ LINE) ก็อ่าน", (LP.parse_draft("Ac Lead No. NLD9-\n*เพิ่มเติม*  : ซื้อสด\nเบอร์โทร : 0899998888")
                                                    or {}).get("more") == "ซื้อสด")

    PARK, ASG, REJ, OTHER = "C" + "a" * 32, "C" + "b" * 32, "C" + "c" * 32, "C" + "d" * 32
    ROOMS = {PARK: "ADMIN เก็บ Lead", ASG: "ห้องจ่ายเบอร์ บ้านเก่า", REJ: "ห้องจ่ายเบอร์ REJECT",
             OTHER: "ทีมAdmin อ๊อกเล็ตธ์ออโต้"}
    T0 = timezone.now() - timedelta(hours=2)
    _n = [0]

    def post(gid, mins, text, who="หมิว"):
        _n[0] += 1
        GroupChat.objects.create(chat_type="group", group_id=gid, group_name=ROOMS[gid], message_id="pk-%d" % _n[0],
                                 sender_id="U%032x" % 500, sender_name=who, direction="in", msg_type="text",
                                 text=text, sent_at=T0 + timedelta(minutes=mins))

    post(PARK, 0, slip("TLD10-", acc="คนเอ", phone="0811111111"))                  # A — เบอร์
    post(PARK, 1, slip("TLD10-", acc="คนบี", line="beeline99"))                     # B — ID LINE อย่างเดียว
    post(PARK, 2, slip("TLD10-", acc="คนซี"))                                       # C — มีแต่ชื่อ Account
    post(PARK, 3, slip("TLD10-", acc="คนเอ", phone="081-111-1111"))                 # A โพสต์ซ้ำ (เขียนเบอร์มีขีด)
    post(OTHER, 4, slip("TLD10-", acc="คนดี", phone="0822222222"))                  # ห้องอื่น ไม่ใช่ห้องพัก
    post(ASG, 10, slip("TLD10-9001", acc="คนเอ", phone="0811111111", tag="เอหนึ่ง"), who="เฟิร์น")
    post(REJ, 11, slip("RTLD10-9002/1", acc="คนบี", line="beeline99", tag="บีหนึ่ง"), who="กวาง")   # ส่งต่อเคสรีเจ็ค ≠ ได้เลข
    post(ASG, 12, slip("TLD10-9003", acc="คนซี", ch="TikTok ช่องอื่น", tag="เอสอง"))                   # ชื่อซ้ำ แต่คนละช่องทาง
    post(ASG, 13, slip("TLD10-9004", acc="คนซี", tag="เอสอง"), who="เฟิร์น")
    b = LP.board(cache_sec=0)
    W = {i["account"]: i for i in b["waiting"]}
    A = {i["account"]: i for i in b["assigned"]}
    ck("หาห้องพักเจอจากชื่อกลุ่ม", b["room"] == "ADMIN เก็บ Lead", b["room"])
    ck("★ ยังรอเลข = เฉพาะคนที่ยังไม่มีใบจริง (บี)", list(W) == ["คนบี"], list(W))
    ck("★ ส่งต่อเคสรีเจ็ค (R…) ไม่นับว่าได้เลข", "คนบี" in W)
    ck("ได้เลข: จับคู่ด้วยเบอร์ + ได้เลข/เซลล์/คนจ่าย/เวลารอ",
       A.get("คนเอ", {}).get("code") == "TLD10-9001" and A["คนเอ"]["seller"] == "เอหนึ่ง"
       and A["คนเอ"]["assignedBy"] == "เฟิร์น" and A["คนเอ"]["waitMin"] == 10, A.get("คนเอ"))
    ck("★ โพสต์ใบร่างซ้ำ = ลีดเดิม (ไม่นับเป็นลีดใหม่)", A.get("คนเอ", {}).get("reposts") == 1
       and sum(1 for i in b["waiting"] + b["assigned"] if i["account"] == "คนเอ") == 1)
    ck("★ ไม่มีเบอร์/ID LINE → จับด้วยชื่อ Account + ช่องทาง (ชื่อซ้ำคนละช่องทางไม่นับ)",
       A.get("คนซี", {}).get("code") == "TLD10-9004", A.get("คนซี"))
    ck("ใบร่างในห้องอื่น (ทีมAdmin) ไม่นับ", "คนดี" not in W and "คนดี" not in A)
    ck("สถิติวันนี้", b["stats"]["waiting"] == 1 and b["stats"]["assignedToday"] in (2, 0), b["stats"])

    LP._CACHE["val"] = None
    s_, d = J(ADM, "/connect/api/inbox?view=tocode")
    pk = d.get("parked") or {}
    ck("API แท็บจ่ายเบอร์: ได้ห้องพัก Lead + ตัวเลข", s_ == 200 and len(pk.get("waiting", [])) == 1
       and d.get("counts", {}).get("parked") == 1, (s_, d.get("counts")))
    s_, d = J(ADM, "/connect/api/inbox?view=overdue")
    ck("แท็บอื่นได้แค่ตัวเลข (ไม่ส่งรายการทั้งก้อนทุก 8 วิ)", "parked" not in d and d.get("counts", {}).get("parked") == 1)
    s_, d = J(SA1, "/connect/api/inbox?view=tocode")
    ck("★ เซลล์ไม่เห็นห้องพัก Lead", "parked" not in d and "parked" not in d.get("counts", {}))
    ck("ห้องพักไม่มี LINE user id หลุด", not leak.search(json.dumps(pk, ensure_ascii=False)))

    # ═════════════════════════════════════════════════════════════════════
    print("[23] จ่ายเบอร์ลีดภายนอก (TikTok/FB) จากห้องพัก Lead — เลขรันชุดเดียวกับลูกค้า LINE OA")
    from checkout.models import ExtLead
    ck("ช่องทาง → ป้าย", [LP.source_of(x) for x in ("Live tiktok ช่องขายบอส", "TT ช่อง888", "เพจบ้านเก่า",
                                                     "fb ads", "Line@", "เบอร์กลาง", "button")]
       == ["tiktok", "tiktok", "facebook", "facebook", "line", "other", "other"])
    ck("board มีป้ายช่องทาง + id ใบร่าง (ไม่ใช่ LINE user id)", W["คนบี"]["source"] == "tiktok"
       and W["คนบี"]["id"].startswith("pk-"), W["คนบี"].get("id"))
    bid = W["คนบี"]["id"]
    CALLS.clear()
    s_, d = J(SA1, "/connect/api/park_assign", {"mid": bid, "emp": A1.id, "base": "TLD"})
    ck("★ เซลล์จ่ายเบอร์ลีดภายนอกไม่ได้", s_ == 403, s_)
    s_, d = J(ADM, "/connect/api/park_assign", {"mid": bid, "emp": 0, "base": "TLD"})
    ck("ไม่เลือกเซลล์ = ปฏิเสธ", s_ == 400 and "เลือกเซลล์" in d.get("error", ""), d)
    s_, d = J(ADM, "/connect/api/park_assign", {"mid": "ไม่มีจริง", "emp": A1.id, "base": "TLD"})
    ck("ใบร่างไม่มีจริง = ปฏิเสธ", s_ == 400 and "ไม่พบใบร่าง" in d.get("error", ""), d)
    nxt = C.last_running() + 1
    s_, d = J(ADM, "/connect/api/park_assign", {"mid": bid, "emp": A1.id, "base": "TLD"})
    eb = ExtLead.objects.filter(message_id=bid).first()
    ck("★ จ่ายเบอร์ได้ + เลขต่อจากเลขรันล่าสุด (ชุดเดียวกับลูกค้า LINE OA)",
       s_ == 200 and eb and eb.code == "TLD%d-%d" % (MON, nxt), (s_, d, eb and eb.code, nxt))
    ck("เก็บสำเนาลีด + เซลล์/คนจ่าย + ติดป้ายทดลอง", eb and eb.line_id == "beeline99" and eb.account == "คนบี"
       and eb.seller_id == A1.id and eb.seller_name == "เอหนึ่ง" and eb.assigned_by == "admin" and eb.code_demo
       and eb.source == "tiktok", eb and (eb.line_id, eb.seller_name, eb.assigned_by))
    ck("★ ไม่ลงชีต/ไม่โพสต์กลุ่ม (ไม่มีคำขอออกนอกระบบ)", not [c for c in CALLS if c[0] == "post"], CALLS)
    ps = parse_leadsheet(d.get("slip", "")) or {}
    ck("ใบจ่ายลีดที่ได้: อ่านกลับได้ (เลข + @เซลล์) + ป้ายทดลองบรรทัดแรก",
       ps.get("lead_code") == eb.code and ps.get("assigned") == "เอหนึ่ง" and d.get("slip", "").startswith("⚠️ ทดลอง"), ps)
    b = LP.board(cache_sec=0)
    ck("★ จ่ายแล้วหายจากรายการรอเลขทันที", "คนบี" not in [i["account"] for i in b["waiting"]])
    ab = next((i for i in b["assigned"] if i["account"] == "คนบี"), {})
    ck("อยู่ใน \"จ่ายแล้ว\" พร้อมเลขที่ระบบออก", (ab.get("sys") or {}).get("code") == eb.code and not ab.get("code"), ab)
    s_, d = J(ADM, "/connect/api/park_assign", {"mid": bid, "emp": A2.id, "base": "TLD"})
    ck("★ จ่ายซ้ำ = ไม่ออกเลขทับ", s_ == 400 and "ไปแล้ว" in d.get("error", "")
       and ExtLead.objects.get(message_id=bid).code == eb.code, d)
    aid = next(i["id"] for i in b["assigned"] if i["account"] == "คนเอ")
    s_, d = J(ADM, "/connect/api/park_assign", {"mid": aid, "emp": A1.id, "base": "TLD"})
    ck("★ ได้เลขในห้องจ่ายเบอร์แล้ว (แอดมินโพสต์เอง) = ไม่ออกเลขซ้อน", s_ == 400 and "TLD10-9001" in d.get("error", ""), d)
    # ลูกค้า LINE OA คนถัดไปต้องได้เลขต่อจากลีดภายนอก (ไม่ชนกัน)
    ck("เลขถัดไปนับเลขของลีดภายนอกด้วย", C.last_running() == nxt, C.last_running())
    post(PARK, 30, slip("TLD10-", acc="คนอี", phone="0855555555"))
    eid_ = [i["id"] for i in LP.board(cache_sec=0)["waiting"] if i["account"] == "คนอี"][0]
    s_, d = J(ADM, "/connect/api/park_assign", {"mid": eid_, "emp": A1.id, "base": "TLD", "code": eb.code})
    ck("★ ใส่เลขที่ถูกใช้แล้ว = ปฏิเสธ", s_ == 400 and "ถูกใช้" in d.get("error", ""), d)
    s_, d = J(ADM, "/connect/api/park_assign", {"mid": eid_, "skip": True})
    b = LP.board(cache_sec=0)
    ck("ไม่ต้องจ่ายเบอร์ = ออกจากรายการรอ + อยู่ใน \"ซ่อนไว้\"", s_ == 200 and "คนอี" not in [i["account"] for i in b["waiting"]]
       and [i["account"] for i in b["skipped"]] == ["คนอี"] and b["stats"]["skipped"] == 1, (s_, b["stats"]))
    s_, d = J(ADM, "/connect/api/park_assign", {"mid": eid_, "skip": False})
    ck("เอากลับมาจ่ายเบอร์ได้", s_ == 200 and "คนอี" in [i["account"] for i in LP.board(cache_sec=0)["waiting"]])
    s_, d = J(ADM, "/connect/api/park_assign", {"mid": bid, "skip": True})
    ck("จ่ายเบอร์แล้ว กดซ่อนไม่ได้", s_ == 400, d)
    LP._CACHE["val"] = None
    s_, d = J(ADM, "/connect/api/inbox?view=tocode")
    chp = (d.get("parked") or {}).get("codeHelp") or {}
    ck("หน้าเว็บได้ตัวช่วยประกอบเลขตัวอย่าง", chp.get("next") == C.last_running() + 1 and chp.get("month") == MON
       and any(x["key"] == "TLD" for x in chp.get("bases", [])), chp)
    ExtLead.objects.filter(message_id=bid).update(parked_at=timezone.now() - timedelta(days=100))
    C.tick()
    ck("★ ลีดภายนอกเกิน 90 วันถูกลบ (มีเบอร์/ID LINE ลูกค้า)", not ExtLead.objects.filter(message_id=bid).exists())

    # ═════════════════════════════════════════════════════════════════════
    print("[24] Facebook Messenger ในคิวเดียวกับ LINE (ซิงก์ทุกนาที · ตอบจาก Connect ช่วงทดสอบ)")
    from checkout import fb_sync as FS
    from checkout.models import FbChat, FbProfile
    from dashboard.services import meta as M
    settings.META_ACCESS_TOKEN, settings.META_PAGE_IDS, settings.META_AD_ACCOUNTS = "user-tok", ["111"], []
    PSID = "990011223344556677"                      # PSID ลูกค้า — ห้ามหลุดออกหน้าเว็บ
    FB = {"convs": [], "msgs": {}, "send": None, "sent": [], "gets": []}
    nowu = timezone.now()

    def fbt(dt):
        return dt.astimezone(TZ).strftime("%Y-%m-%dT%H:%M:%S%z")

    def conv(cid, psid, name, upd):
        return {"id": cid, "updated_time": fbt(upd), "message_count": len(FB["msgs"].get(cid, [])),
                "link": "/111/inbox/%s" % cid,
                "participants": {"data": [{"id": "111", "name": "เพจเรา"}, {"id": psid, "name": name}]}}

    def fmsg(mid, frm, text, at_):
        return {"id": mid, "created_time": fbt(at_), "from": {"id": frm, "name": "x"}, "message": text}

    _old_get, _old_post = requests.get, requests.post

    def _fb_get(url, *a, **k):
        if "graph.facebook.com" not in url:
            return _old_get(url, *a, **k)
        path = url.split("graph.facebook.com/")[1].split("/", 1)[1]
        FB["gets"].append(path)
        if path == "111":
            return _R(200, {"id": "111", "access_token": "page-tok"})
        if path == "111/conversations":
            return _R(200, {"data": FB["convs"]})
        if path.endswith("/messages"):
            return _R(200, {"data": FB["msgs"].get(path.split("/")[0], [])})
        return _R(404, {"error": {"message": "unknown " + path, "code": 100}})

    def _fb_post(url, *a, **k):
        if "graph.facebook.com" not in url:
            return _old_post(url, *a, **k)
        FB["sent"].append((url.split("graph.facebook.com/")[1], k.get("json")))
        if FB["send"]:
            return _R(400, {"error": FB["send"]})
        return _R(200, {"recipient_id": PSID, "message_id": "m_sent_%d" % len(FB["sent"])})

    requests.get, requests.post = _fb_get, _fb_post
    try:
        n0 = len(FB["sent"])
        try:
            M.post("/999/messages", payload={})
            blocked = False
        except M.ForeignAsset:
            blocked = True
        ck("★ ด่าน Meta: ส่งข้อความเข้าเพจบริษัทอื่นไม่ได้ + ไม่ยิงเน็ต", blocked and len(FB["sent"]) == n0)

        t1 = nowu - timedelta(minutes=1)
        FB["msgs"]["t_1"] = [fmsg("m_in1", PSID, "สนใจ civic fe ครับ 0812223333", t1)]
        FB["convs"] = [conv("t_1", PSID, "ลูกค้าเฟซบุ๊ก", t1)]
        r = FS.sync_live()
        fp = FbProfile.objects.filter(user_id=PSID).first()
        fo = ChatOwner.objects.filter(fb_profile=fp).first() if fp else None
        ck("ซิงก์ทุกนาที: เก็บแชท + สร้างลูกค้าใน Connect", r.get("newMsgs") == 1 and fo is not None, (r, fo))
        ck("★ ลูกค้า FB เข้าคิวรอรับ + เริ่มนับ 5 นาที + ทีมตามเวร", fo and fo.awaiting_since and not fo.owner_id
           and fo.team == "A", fo and (fo.awaiting_since, fo.team))
        g0 = len(FB["gets"])
        FS.sync_live()
        ck("ห้องไม่ขยับ = ไม่ยิงขอข้อความซ้ำ", not [x for x in FB["gets"][g0:] if x.endswith("/messages")], FB["gets"][g0:])

        s_, d = J(ADM, "/connect/api/inbox?view=queue")
        row = next((x for x in d.get("rows", []) if x["id"] == fo.id), {})
        ck("รายชื่อมีป้าย Facebook + ชื่อ + ข้อความล่าสุด", row.get("src") == "fb" and row.get("name") == "ลูกค้าเฟซบุ๊ก"
           and "civic" in row.get("preview", ""), row)
        s_, d = J(ADM, "/connect/api/inbox?view=all&src=fb")
        ck("ตัวกรองช่องทาง Facebook = เฉพาะลูกค้า FB", d.get("rows") and all(x["src"] == "fb" for x in d["rows"]))
        s_, d = J(ADM, "/connect/api/inbox?view=all&src=line")
        ck("ตัวกรอง LINE = ไม่มีลูกค้า FB", fo.id not in [x["id"] for x in d.get("rows", [])])
        s_, d = J(SA1, "/connect/api/claim", {"id": fo.id})
        ck("เซลล์ทีมเวรรับลูกค้า FB ได้ (กติกาเดียวกับ LINE)", s_ == 200 and ChatOwner.objects.get(pk=fo.id).owner_id == A1.id, d)
        s_, d = J(SA1, "/connect/api/chat?id=%d" % fo.id)
        ck("เปิดแชท FB: เห็นข้อความ + โปรไฟล์บอกเพจ", s_ == 200 and d["messages"][0]["text"].startswith("สนใจ civic")
           and d["profile"]["src"] == "fb" and d["profile"].get("inbox", "").startswith("https://www.facebook.com/"), d.get("profile"))
        ck("ข้อมูลลีด FB: เบอร์จากแชท + ชื่อ Account = ชื่อใน Facebook + ไม่เดาช่องทาง",
           d["lead"]["phone"] == "0812223333" and d["lead"]["account"] == "ลูกค้าเฟซบุ๊ก" and d["lead"]["channel"] == "",
           (d["lead"]["phone"], d["lead"]["account"], d["lead"]["channel"]))
        # ★ 6 ต.ค.69 เจ้าของสั่ง: ลูกค้าที่ไม่ใช่ LINE (Facebook) = เซลล์ได้สิทธิ์ในระบบ "เพื่อเก็บข้อมูลเท่านั้น"
        #   → เซลล์เปิดแชท/กรอกข้อมูลลีดได้ แต่ตอบ/ปิดรอบไม่ได้ (แอดมินยังตอบได้ตามโหมด fb_reply)
        ck("★ เซลล์ + ลูกค้า FB = สิทธิ์เก็บข้อมูลเท่านั้น (ตอบไม่ได้ · บอกเหตุผล)",
           d.get("replyOn") is False and "เก็บข้อมูลเท่านั้น" in d.get("replyWhy", "") and d.get("canDismiss") is False,
           (d.get("replyOn"), d.get("replyWhy"), d.get("canDismiss")))
        s_, d = J(ADM, "/connect/api/chat?id=%d" % fo.id)
        ck("★ ช่วงทดสอบ: แอดมินยังตอบแชท FB ที่ไม่ใช่แชททดสอบไม่ได้", d.get("replyOn") is False and "ทดสอบ" in d.get("replyWhy", ""))
        leakfb = [pth for pth in ("/connect/api/inbox?view=all", "/connect/api/chat?id=%d" % fo.id)
                  if PSID in ADM.get(pth, secure=True).content.decode()]
        ck("★ ไม่ส่ง PSID ลูกค้าออกหน้าเว็บ", not leakfb, leakfb)

        n0 = len(FB["sent"])
        s_, d = J(ADM, "/connect/api/reply", {"id": fo.id, "text": "สวัสดีครับ"})
        ck("★ ตอบแชท FB ที่ไม่ใช่แชททดสอบ = ปฏิเสธ + ไม่ยิง Facebook", s_ == 400 and len(FB["sent"]) == n0, (s_, d))
        s_, d = J(SA1, "/connect/api/fb_test", {"id": fo.id, "on": True})
        ck("เซลล์ตั้งแชททดสอบไม่ได้", s_ == 403, s_)
        s_, d = J(ADM, "/connect/api/fb_test", {"id": fo.id, "on": True})
        ck("แอดมินตั้งเป็นแชททดสอบ", s_ == 200 and fo.id in C.cfg()["fb_test_rows"], d)
        s_, d = J(SA1, "/connect/api/reply", {"id": fo.id, "text": "สวัสดีครับ"})
        ck("★ เซลล์ตอบลูกค้า FB ไม่ได้แม้เป็นแชททดสอบ (เก็บข้อมูลเท่านั้น) + ไม่ยิง Facebook",
           s_ == 403 and "เก็บข้อมูลเท่านั้น" in d.get("error", "") and len(FB["sent"]) == n0, (s_, d))
        s_, d = J(SA1, "/connect/api/dismiss", {"id": fo.id})
        ck("★ เซลล์ปิดรอบรอของลูกค้า FB ไม่ได้", s_ == 403, (s_, d))
        ck("★ ลูกค้า FB ไม่นับเป็น \"รอตอบ\" ของเซลล์ (ป้ายตัวเลขไม่เตือนเรื่องที่ทำไม่ได้)",
           C.counts(A1)["mineWaiting"] == ChatOwner.objects.filter(owner=A1, awaiting_since__isnull=False,
                                                                   fb_profile__isnull=True).count()
           and C.counts(A1, admin=True)["mineWaiting"] > C.counts(A1)["mineWaiting"], (C.counts(A1), C.counts(A1, admin=True)))
        s_, d = J(ADM, "/connect/api/reply", {"id": fo.id, "text": "มีครับ ปี 23 ครับ"})
        sent = FB["sent"][-1] if FB["sent"] else ("", {})
        ck("★ ตอบจาก Connect → Send API ของเพจ (ตอบกลับภายใน 24 ชม.)", s_ == 200 and sent[0].endswith("/111/messages")
           and sent[1] == {"recipient": {"id": PSID}, "messaging_type": "RESPONSE", "message": {"text": "มีครับ ปี 23 ครับ"}}, (s_, d, sent))
        out = FbChat.objects.filter(thread_id="t_1", direction="out").first()
        fo.refresh_from_db()
        ck("บันทึกข้อความขาออก + ชื่อคนตอบ + ปิดรอบรอ", out and out.sent_by_name == "admin" and out.message_id == "m_sent_%d" % len(FB["sent"])
           and fo.awaiting_since is None and ChatOwnerLog.objects.filter(chat=fo, action="reply").exists(),
           out and (out.sent_by_name, fo.awaiting_since))

        # ซิงก์รอบถัดไป: ข้อความที่ส่งจาก Connect (id เดิม) ไม่เก็บซ้ำ · ลูกค้าตอบกลับ = รอบรอใหม่
        t2 = timezone.now()
        FB["msgs"]["t_1"] = [fmsg("m_in2", PSID, "ราคาเท่าไหร่ครับ", t2), fmsg(out.message_id, "111", "มีครับ ปี 23 ครับ", out.sent_at)] \
            + FB["msgs"]["t_1"]
        FB["convs"] = [conv("t_1", PSID, "ลูกค้าเฟซบุ๊ก", t2)]
        FS.sync_live()
        fo.refresh_from_db()
        ck("★ ข้อความที่ส่งจาก Connect ไม่ถูกเก็บซ้ำตอนซิงก์", FbChat.objects.filter(thread_id="t_1", direction="out").count() == 1)
        ck("ลูกค้าตอบกลับ = เริ่มรอบรอใหม่ (ของเจ้าของเดิม)", fo.awaiting_since and fo.owner_id == A1.id, fo.awaiting_since)
        # ★ ข้อความตอบอัตโนมัติของเพจ (ออกวินาทีเดียวกับลูกค้า / ภายใน 15 วิ) = ไม่ใช่คนตอบ → นาฬิกายังเดิน
        #   (เจอจริง 4 ต.ค.69: Business Suite ส่งฟอร์มขอเบอร์ทันทีที่ลูกค้าทัก แล้วระบบเคยนับว่า "ตอบแล้ว")
        FB["msgs"]["t_1"] = [fmsg("m_auto1", "111", "รับโปรขับฟรี โปรดแจ้ง ชื่อ เบอร์ ไลน์", t2),
                             fmsg("m_auto2", "111", "สวัสดีค่ะ", t2 + timedelta(seconds=3))] + FB["msgs"]["t_1"]
        FB["convs"] = [conv("t_1", PSID, "ลูกค้าเฟซบุ๊ก", t2 + timedelta(seconds=3))]
        FS.sync_live()
        fo.refresh_from_db()
        ck("★ ตอบอัตโนมัติของเพจ = ยังไม่นับว่าตอบ (รอบรอไม่ถูกปิด)", fo.awaiting_since is not None
           and not ChatOwnerLog.objects.filter(chat=fo, action="reply", at__gte=t2 - timedelta(seconds=1), by_name="ตอบใน Facebook").exists(),
           fo.awaiting_since)
        # เพจตอบเองใน Business Suite → ปิดรอบให้ (Facebook ส่งขาออกมาด้วย)
        t3 = timezone.now() + timedelta(seconds=30)
        FB["msgs"]["t_1"] = [fmsg("m_bs1", "111", "ทักไลน์มาได้เลยครับ", t3)] + FB["msgs"]["t_1"]
        FB["convs"] = [conv("t_1", PSID, "ลูกค้าเฟซบุ๊ก", t3)]
        FS.sync_live()
        fo.refresh_from_db()
        lg = ChatOwnerLog.objects.filter(chat=fo, action="reply").order_by("-at").first()
        ck("★ ตอบใน Facebook (Business Suite) = หยุดนาฬิกาให้ + จดว่าตอบที่ไหน", fo.awaiting_since is None
           and lg and lg.by_name == "ตอบใน Facebook", lg and lg.by_name)
        s_, d = J(SA1, "/connect/api/chat?id=%d" % fo.id)
        # เทียบแบบไม่สนลำดับ — เวลาข้อความทดสอบปัดเป็นวินาที อาจมาก่อนข้อความที่ส่งจาก Connect ในวินาทีเดียวกัน
        ck("บับเบิลขาออกบอกว่าใครตอบ / ตอบอัตโนมัติ / ตอบใน Facebook", sorted(m["by"] for m in d["messages"] if m["dir"] == "out")
           == sorted(["admin", "ตอบอัตโนมัติ (เพจ)", "ตอบอัตโนมัติ (เพจ)", "ตอบใน Facebook"]),
           [m["by"] for m in d["messages"] if m["dir"] == "out"])

        # เกิน 24 ชม. → Facebook ปฏิเสธ → บอกเป็นภาษาคน + ไม่บันทึก
        FB["send"] = {"message": "(#10) This message is sent outside of allowed window.", "code": 10, "error_subcode": 2018278}
        n_out = FbChat.objects.filter(direction="out").count()
        s_, d = J(ADM, "/connect/api/reply", {"id": fo.id, "text": "ยังสนใจไหมครับ"})
        ck("★ เกิน 24 ชม.: บอกให้ตอบใน Business Suite + ไม่บันทึกข้อความที่ส่งไม่ถึง",
           s_ == 400 and "24 ชม." in d.get("error", "") and FbChat.objects.filter(direction="out").count() == n_out, d)
        FB["send"] = None

        # ห้องเก่า (ข้อความ 2 ชม. ก่อน) ที่เพิ่งดึงมา = มีแถว แต่ไม่เริ่มนับ 5 นาที
        PS2 = "880011223344556677"
        t_old = timezone.now() - timedelta(hours=2)
        FB["msgs"]["t_2"] = [fmsg("m_old1", PS2, "สวัสดีค่ะ", t_old)]
        FB["convs"] = [conv("t_2", PS2, "ลูกค้าเก่า FB", t_old), conv("t_1", PSID, "ลูกค้าเฟซบุ๊ก", t3)]
        FS.sync_live()
        o2 = ChatOwner.objects.filter(fb_profile__user_id=PS2).first()
        ck("★ ข้อความเก่าที่เพิ่งดึงมา = มีแถวแต่ไม่ขึ้นเลยเวลา", o2 and o2.awaiting_since is None, o2 and o2.awaiting_since)
        # ลูกค้า FB ที่คุยภายใน 7 วันแต่ยังไม่มีแถว (ก่อนเปิดใช้) → sync_rows สร้างให้
        fp3 = FbProfile.objects.create(user_id="770011223344556677", display_name="คุยเมื่อวาน", channel="111",
                                       thread_id="t_3", last_seen=timezone.now() - timedelta(days=1))
        FbChat.objects.create(thread_id="t_3", message_id="m_y1", sender_id=fp3.user_id, msg_type="text",
                              text="มีรถไหม", channel="111", direction="in", sent_at=timezone.now() - timedelta(days=1))
        C.sync_rows(force=True)
        o3 = ChatOwner.objects.filter(fb_profile=fp3).first()
        ck("ลูกค้า FB เมื่อวาน (ก่อนเปิดใช้) มีแถวใน \"ทั้งหมด\" ไม่เริ่มรอบรอ", o3 and o3.awaiting_since is None
           and o3.last_preview == "มีรถไหม", o3 and o3.last_preview)

        # ปิดสวิตช์ = ไม่ขึ้นคิว
        cc = C.cfg(); cc["fb_on"] = False; C.save_cfg(cc)
        PS4 = "660011223344556677"
        FB["msgs"]["t_4"] = [fmsg("m_n1", PS4, "สนใจครับ", timezone.now())]
        FB["convs"] = [conv("t_4", PS4, "ลูกค้าตอนปิด", timezone.now())]
        FS.sync_live()
        ck("ปิด \"ดึงแชท Facebook เข้า Connect\" = แชทยังเก็บ แต่ไม่ขึ้นคิว", FbChat.objects.filter(message_id="m_n1").exists()
           and not ChatOwner.objects.filter(fb_profile__user_id=PS4).exists())
        cc["fb_on"] = True; C.save_cfg(cc)
        s_, d = J(ADM, "/connect/api/config", {"fb_reply": "เปิด"})
        ck("ค่าตั้งการตอบ FB ผิด = ปฏิเสธ", s_ == 400, d)
        s_, d = J(ADM, "/connect/api/config", {"fb_reply": "on"})
        ck("เปิดตอบ FB ทุกแชทได้ + การ์ดตั้งค่าได้ชื่อเพจ", s_ == 200 and d["cfg"]["fb_reply"] == "on"
           and (d.get("fb") or {}).get("pages") == [{"id": "111", "name": "111"}], d.get("fb"))
        ck("เปิดแล้ว ตอบแชท FB ไหนก็ได้", C.fb_reply_state(ChatOwner.objects.get(pk=o2.id))[0] is True)
        ck("tick ไม่พังเมื่อมีลูกค้า FB เลยเวลา", isinstance(C.tick(), dict))
    finally:
        requests.get, requests.post = _old_get, _old_post

    # ═════════════════════════════════════════════════════════════════════
    print("[25] พนักงานทักบัญชีลูกค้า = ขึ้น Connect (ป้าย \"พนักงาน\") · เจ้าของทักทดสอบจาก LINE ส่วนตัวแล้วไม่เห็น")
    EMP2 = LineProfile.objects.create(user_id="U%032x" % 98, display_name="เจ้าของทดสอบ", is_employee=True,
                                      nickname="บอส", employee=OFFICE)
    ck("ทักบอทแจ้งเตือน (push) = ไม่ขึ้น", C.note_customer_message(EMP2.user_id, timezone.now(), "hi", channel="push") is None
       and not ChatOwner.objects.filter(profile=EMP2).exists())
    # ผ่านเส้นทางจริง: webhook → store_chat → Connect (บัญชีลูกค้า crm)
    from checkout.views import store_chat
    from checkout import views as CV
    _cfg0 = CV.line_cfg()
    _real_cfg = CV.line_cfg
    CV.line_cfg = lambda: dict(_cfg0, store_chat=True, store_customer_chat=True)
    try:
        store_chat({"destination": "", "events": [{"type": "message", "timestamp": int(timezone.now().timestamp() * 1000),
                    "source": {"type": "user", "userId": EMP2.user_id},
                    "message": {"id": "emp-test-1", "type": "text", "text": "ทดสอบจาก LINE ส่วนตัว"}}]})
    finally:
        CV.line_cfg = _real_cfg
    oe = ChatOwner.objects.filter(profile=EMP2).first()
    ck("★ พนักงานทักบัญชีลูกค้า = ขึ้น Connect + เริ่มรอบรอ", oe is not None and oe.awaiting_since is not None, oe)
    s_, d = J(ADM, "/connect/api/inbox?view=all")
    re_ = next((x for x in d.get("rows", []) if oe and x["id"] == oe.id), {})
    # ★ 6 ต.ค.69 — ชื่อพนักงานมาจาก **ทะเบียนที่ผูกอยู่** (OFFICE = "ออฟฟิศ") ไม่ใช่สำเนาในโปรไฟล์ LINE ("บอส")
    #   สำเนาที่ไม่ตรงทะเบียนคือบั๊ก "นิดแก้ชื่อเล่นแล้วยังขึ้นชื่อเดิม" — ดู scripts/test_employee_names.py
    ck("แถวมีป้ายพนักงาน + ชื่อ (ชื่อในทะเบียนชนะสำเนา)",
       re_.get("staff") is True and re_.get("name") == OFFICE.nickname, re_)
    C.note_reply(EMP2.user_id, None, timezone.now(), "ได้รับแล้วครับ", by="admin")   # = สิ่งที่ send_reply เรียกหลังส่งสำเร็จ
    oe.refresh_from_db()
    ck("ตอบแล้วปิดรอบได้ (พนักงานก็เหมือนลูกค้า)", oe.awaiting_since is None, oe.awaiting_since)
    EMP3 = LineProfile.objects.create(user_id="U%032x" % 97, display_name="คุยกับบอทแจ้งเตือน", is_employee=True)
    ck("พนักงานที่ไม่มีแถว (คุยกับบอทแจ้งเตือน) ตอบแล้วไม่สร้างแถวใหม่",
       C.note_reply(EMP3.user_id, None, timezone.now(), "x") is None and not ChatOwner.objects.filter(profile=EMP3).exists())

    # ═════════════════════════════════════════════════════════════════════
    print("[26] ห้องพัก Lead = เฉพาะลูกค้าที่ให้เบอร์/ไอดีไลน์แล้ว (เจ้าของสั่ง 4 ต.ค.69)")
    m_ = lambda d, t: {"dir": d, "text": t}
    ck("เบอร์ในแชท = ช่องทางติดต่อ", C.contacts_in([m_("in", "โทร 081-234-5678 ครับ")]) == (["0812345678"], []))
    ck("ไอดีไลน์แบบมีป้าย", C.contacts_in([m_("in", "ไอดีไลน์ tus_123 ครับ")])[1] == ["tus_123"])
    ck("★ ไอดีคำเดียวหลังเราขอ (ขอเบอร์ หรือไอดี LINE)", C.contacts_in(
        [m_("out", "ขอเบอร์ หรือไอดี LINE หน่อยครับ"), m_("in", "tus.neem")])[1] == ["tus.neem"])
    ck("★ คำอังกฤษลอยๆ ที่เราไม่ได้ขอ ≠ ไอดี", C.contacts_in([m_("in", "civic"), m_("in", "ok55")]) == ([], []))
    ck("online shop ≠ ไอดี (line ในคำอังกฤษ)", C.contacts_in([m_("in", "online shop ไหมครับ")]) == ([], []))
    ck("ข้อความของเราไม่นับเป็นเบอร์ลูกค้า", C.contacts_in([m_("out", "โทร 0899999999 ได้เลยครับ")]) == ([], []))
    NC = C.note_customer_message(cust(301, "แค่ถามรถ").user_id, timezone.now(), "มี civic fe ไหมครับ")
    ck("★ ลูกค้าที่ยังแค่ถามรถ = อยู่คิวรอรับ แต่ไม่เข้าห้องพัก", NC.awaiting_since and NC.id not in tocode_ids())
    C.note_customer_message(cust(301, "แค่ถามรถ").user_id if False else NC.profile.user_id, timezone.now(), "เบอร์ 0844440001 ครับ")
    ck("★ ให้เบอร์แล้ว = เข้าห้องพักทันที (ไม่ต้องรอแอดมินเปิดแชท)", NC.id in tocode_ids()
       and ChatLead.objects.get(chat=NC).phone == "0844440001")
    C.save_lead_field(ChatOwner.objects.get(pk=NC.id), "phone", "", by="admin")
    C.note_customer_message(NC.profile.user_id, timezone.now(), "อีกเบอร์ 0844440002")
    ck("คนลบเบอร์เองแล้ว ระบบไม่เติมกลับ", ChatLead.objects.get(chat=NC).phone == "" and NC.id not in tocode_ids())
    # แถวเดิมที่คุยไปแล้ว (ก่อนมีกติกานี้) — เก็บตกจากแชทที่เก็บไว้
    OLDC = cust(302, "คุยไว้ก่อน")
    GroupChat.objects.create(chat_type="user", message_id="oc-1", sender_id=OLDC.user_id, direction="in",
                             msg_type="text", text="ไลน์ไอดี oldc_99 นะครับ", sent_at=timezone.now())
    oc = C._row_for(OLDC)
    ChatOwner.objects.filter(pk=oc.id).update(awaiting_since=timezone.now(), due_at=timezone.now())
    ck("(ก่อนเก็บตก) ยังไม่อยู่ห้องพัก", oc.id not in tocode_ids())
    C.scan_contacts()
    ck("★ เก็บตกแชทเดิม: เจอไอดีไลน์ → เข้าห้องพัก", oc.id in tocode_ids()
       and ChatLead.objects.get(chat=oc).line_id == "oldc_99")
    ck("ตัวเลขแท็บตรงกับรายการ (หลังกติกาใหม่)", C.counts(admin=True)["tocode"] == len(tocode_ids()))

    # ═════════════════════════════════════════════════════════════════════
    print("[27] Messenger webhook — Facebook ส่งแชทมาเอง (แทนการถาม API ทุกนาที · เจ้าของห่วงติด token)")
    import hashlib as _hl
    import hmac as _hm
    from checkout import fb_webhook as FW
    settings.META_WEBHOOK_VERIFY_TOKEN, settings.META_APP_SECRET = "vtok-123", "app-secret-xyz"
    FW.INLINE = True
    W = {"gets": [], "posts": [], "conv": {}}
    _g0, _p0 = requests.get, requests.post

    def _wg(url, *a, **k):
        if "graph.facebook.com" not in url:
            return _g0(url, *a, **k)
        path = url.split("graph.facebook.com/")[1].split("/", 1)[1]
        prm = k.get("params") or {}
        W["gets"].append((path, dict(prm)))
        if path == "111":
            return _R(200, {"id": "111", "access_token": "page-tok"})
        if path == "111/conversations":
            c = W["conv"].get(prm.get("user_id"))
            return _R(200, {"data": [c] if c else []})
        if path == "111/subscribed_apps":
            return _R(200, {"data": [{"id": "app", "subscribed_fields": ["messages", "message_echoes"]}]})
        return _R(404, {"error": {"message": "unknown", "code": 100}})

    def _wp(url, *a, **k):
        if "graph.facebook.com" not in url:
            return _p0(url, *a, **k)
        W["posts"].append((url.split("graph.facebook.com/")[1], k.get("json")))
        return _R(200, {"success": True})

    requests.get, requests.post = _wg, _wp

    def hook(body, secret="app-secret-xyz", sig=None):
        raw = json.dumps(body).encode()
        if sig is None:
            sig = "sha256=" + _hm.new(secret.encode(), raw, _hl.sha256).hexdigest()
        r = NOB.post("/api/meta/webhook", data=raw, content_type="application/json",
                     HTTP_X_HUB_SIGNATURE_256=sig, secure=True)
        js = {}
        if r.status_code == 200 and r["Content-Type"].startswith("application/json"):
            js = r.json()
        return r.status_code, js

    def ev(psid, mid, text, echo=False, ts=None, page="111"):
        ts = ts or int(timezone.now().timestamp() * 1000)
        msg = {"mid": mid, "text": text}
        if echo:
            msg.update(is_echo=True, app_id=1)
        return {"object": "page", "entry": [{"id": page, "time": ts, "messaging": [{
            "sender": {"id": page if echo else psid}, "recipient": {"id": psid if echo else page},
            "timestamp": ts, "message": msg}]}]}

    try:
        r = NOB.get("/api/meta/webhook?hub.mode=subscribe&hub.verify_token=vtok-123&hub.challenge=987654", secure=True)
        ck("ทักทายตอนลงทะเบียน URL: verify token ตรง = ตอบ challenge", r.status_code == 200 and r.content == b"987654", r.content)
        r = NOB.get("/api/meta/webhook?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=1", secure=True)
        ck("verify token ผิด = 403", r.status_code == 403)
        settings.META_APP_SECRET = ""
        st_, _ = hook(ev("990000000000000001", "m_w0", "x"), secret="x")
        ck("★ ยังไม่ตั้ง App Secret = ไม่รับ (กันแชทปลอม)", st_ == 503 and not FbChat.objects.filter(message_id="m_w0").exists())
        settings.META_APP_SECRET = "app-secret-xyz"
        st_, _ = hook(ev("990000000000000001", "m_w0", "x"), sig="sha256=deadbeef")
        ck("★ ลายเซ็นไม่ตรง = 403 ไม่เก็บ", st_ == 403 and not FbChat.objects.filter(message_id="m_w0").exists())
        ck("หน้าตั้งค่าเห็นว่าโดนปฏิเสธเพราะอะไร", "ลายเซ็น" in (FW.last().get("rejected") or ""), FW.last())

        PW = "990000000000000001"
        W["conv"][PW] = {"id": "t_w1", "updated_time": fbt(timezone.now()), "message_count": 1, "link": "/111/inbox/t_w1",
                         "participants": {"data": [{"id": "111", "name": "เพจ"}, {"id": PW, "name": "ลูกค้าเว็บฮุก"}]}}
        n_get = len(W["gets"])
        st_, d = hook(ev(PW, "m_w1", "สนใจ yaris ครับ 0855551234"))
        fpw = FbProfile.objects.filter(user_id=PW).first()
        ow = ChatOwner.objects.filter(fb_profile=fpw).first()
        ck("★ ข้อความลูกค้า → เก็บ + เข้าคิว Connect ทันที (ไม่ต้องรอรอบดึง)", st_ == 200 and d.get("saved") == 1
           and ow is not None and ow.awaiting_since is not None, (st_, d))
        convq = [g for g in W["gets"][n_get:] if g[0] == "111/conversations"]
        ck("ลูกค้าใหม่: ถามห้องสนทนา+ชื่อ 1 ครั้ง", fpw.thread_id == "t_w1" and fpw.display_name == "ลูกค้าเว็บฮุก"
           and len(convq) == 1 and convq[0][1].get("user_id") == PW, convq)
        ck("ให้เบอร์มาในข้อความ = เข้าห้องพัก Lead", ow.id in tocode_ids())
        n_get = len(W["gets"])
        hook(ev(PW, "m_w2", "ยังว่างไหม"))
        ck("★ ลูกค้าเดิม = ไม่ยิง Graph API เลย", not W["gets"][n_get:], W["gets"][n_get:])
        st_, d = hook(ev(PW, "m_w2", "ยังว่างไหม"))
        ck("Facebook ส่งซ้ำ = ไม่เก็บซ้ำ", d.get("dup") == 1 and FbChat.objects.filter(message_id="m_w2").count() == 1)
        hook(ev(PW, "m_w2b", "ขอบคุณที่ทักมาค่ะ", echo=True, ts=int(timezone.now().timestamp() * 1000) + 2000))
        ow.refresh_from_db()
        ck("★ echo ภายใน 15 วิ = ตอบอัตโนมัติ ไม่หยุดนาฬิกา", ow.awaiting_since is not None)
        hook(ev(PW, "m_w3", "ว่างครับ ทักไลน์ได้เลย", echo=True, ts=int(timezone.now().timestamp() * 1000) + 60000))
        ow.refresh_from_db()
        ck("★ เพจตอบ (echo) = หยุดนาฬิกา", ow.awaiting_since is None
           and ChatOwnerLog.objects.filter(chat=ow, action="reply", by_name="ตอบใน Facebook").exists())
        st_, d = hook(ev("990000000000000009", "m_x9", "หวัดดี", page="999"))
        ck("★ เพจบริษัทอื่น = ไม่เก็บ", d.get("foreign") == 1 and not FbChat.objects.filter(message_id="m_x9").exists(), d)
        st_, d = hook({"object": "page", "entry": [{"id": "111", "messaging": [{"sender": {"id": PW}, "read": {"watermark": 1}}]}]})
        ck("อ่านแล้ว/ส่งถึง (ไม่ใช่ข้อความ) = ข้าม", d.get("skipped") == 1 and d.get("saved") == 0, d)
        # หาห้องสนทนาไม่เจอ → ห้องชั่วคราว → รอบดึงสำรองเจอห้องจริง ย้ายข้อความเข้าห้องจริง
        PX = "990000000000000002"
        hook(ev(PX, "m_x1", "สนใจครับ"))
        fpx = FbProfile.objects.get(user_id=PX)
        ck("หาห้องไม่เจอ = ห้องชั่วคราว (ข้อความไม่หาย)", fpx.thread_id == "psid:" + PX
           and FbChat.objects.get(message_id="m_x1").thread_id == "psid:" + PX)
        FS._upsert_profile({"id": "t_x1", "updated_time": fbt(timezone.now()), "message_count": 1,
                            "participants": {"data": [{"id": "111"}, {"id": PX, "name": "ลูกค้าเอ็กซ์"}]}},
                           "111", timezone.now()).save()
        ck("★ เจอห้องจริงแล้ว ย้ายข้อความเข้าห้องจริง", FbChat.objects.get(message_id="m_x1").thread_id == "t_x1"
           and FbProfile.objects.get(user_id=PX).thread_id == "t_x1")
        # ดึงสำรอง: ความถี่ตามค่าตั้ง · เช็คข้าม worker ผ่าน KV
        C._FB_RUN["at"] = 0.0
        cache_store.set_kv("fb_live_last", {"at": timezone.now().isoformat()})
        ck("★ worker อื่นเพิ่งดึง (KV) = ยังไม่ถึงรอบ", C.fb_poll_due() is False)
        cache_store.set_kv("fb_live_last", {"at": (timezone.now() - timedelta(minutes=1)).isoformat()})
        ck("ค่าตั้งต้น 2 นาที: ผ่านไป 1 นาที = ยังไม่ถึงรอบ", C.fb_poll_due() is False and C.cfg()["fb_poll_min"] == 2)
        cache_store.set_kv("fb_live_last", {"at": (timezone.now() - timedelta(minutes=3)).isoformat()})
        ck("เกิน 2 นาที = ถึงรอบ", C.fb_poll_due() is True)
        s_, d = J(ADM, "/connect/api/config", {"fb_poll_min": 1})
        ck("ดึงสำรองถี่กว่า 2 นาที = ปฏิเสธ", s_ == 400, d)
        s_, d = J(ADM, "/connect/api/config", {"fb_poll_min": 30})
        ck("ตั้งดึงสำรองทุก 30 นาทีได้ + การ์ดได้สถานะ webhook", s_ == 200 and d["cfg"]["fb_poll_min"] == 30
           and d["fb"]["webhook"]["url"].endswith("/api/meta/webhook") and d["fb"]["webhook"]["secretSet"] is True, d.get("fb"))
        s_, d = J(SA1, "/connect/api/fb_webhook", {})
        ck("เซลล์กดผูกเพจไม่ได้", s_ == 403)
        s_, d = J(ADM, "/connect/api/fb_webhook", {})
        sub = [x for x in W["posts"] if x[0].endswith("/111/subscribed_apps")]
        ck("ปุ่มผูกเพจ: ขอรับ messages + message_echoes", s_ == 200 and sub
           and sub[-1][1] == {"subscribed_fields": "messages,message_echoes"}, (s_, d, sub))
        s_, d = J(ADM, "/connect/api/fb_webhook")
        ck("ตรวจการผูกเพจได้", s_ == 200 and d["pages"][0]["subscribed"] is True, d)
    finally:
        requests.get, requests.post = _g0, _p0
        FW.INLINE = False

    # ═════════════════════════════════════════════════════════════════════
    print("[28] ห้องพัก Lead: จ่ายให้ใคร — จับใบจ่ายลีดในกลุ่มเอง (เจ้าของ: \"อยากรู้ว่าจ่ายให้ใครบ้าง\")")
    PG = "C" + "9" * 32

    def post_slip(mid, code, phone, tag, by_name="หมิว Oxlet"):
        return GroupChat.objects.create(
            chat_type="group", group_id=PG, group_name="ห้องจ่ายเบอร์ ทดสอบ", message_id=mid,
            sender_id="U%032x" % 78, sender_name=by_name, direction="in", msg_type="text",
            text="Ac Lead No. %s\nชื่อ Account: ลูกค้าห้องพัก\nเบอร์โทร : %s\nช่องทาง : TikTok\n@%s" % (code, phone, tag),
            sent_at=timezone.now())

    MAT = Employee.objects.create(nickname="มัททดสอบ", position="ทีม A", display_name="เซลมัท OxletAuto")
    Employee.objects.create(nickname="ไหมหนึ่ง", position="ทีม B", display_name="Mai OxletAuto")
    Employee.objects.create(nickname="ไหมสอง", position="ทีม B", display_name="Mai🐶 Oxlet")
    C._TAGNICK["at"] = 0.0
    ck("แท็กชื่อเล่นตรง → ชื่อเล่น", C.tag_nick("@เอหนึ่ง") == "เอหนึ่ง", C.tag_nick("@เอหนึ่ง"))
    ck("★ แท็กชื่อ LINE คำแรก (@เซลมัท) → ชื่อเล่นในทะเบียน", C.tag_nick("@เซลมัท") == "มัททดสอบ", C.tag_nick("@เซลมัท"))
    ck("★ แท็กที่ตรงหลายคน (@Mai) = คืนแท็กเดิม ไม่เดา", C.tag_nick("@Mai") == "Mai", C.tag_nick("@Mai"))
    ck("แท็กที่ไม่มีในทะเบียน = คืนแท็กเดิม", C.tag_nick("@คนนอก") == "คนนอก")
    ck("ว่าง = ว่าง", C.tag_nick("") == "" and C.tag_nick(None) == "")

    R1 = C.note_customer_message(cust(401, "ห้องพักหนึ่ง").user_id, timezone.now(), "สนใจ civic เบอร์ 0855550001 ครับ")
    R2 = C.note_customer_message(cust(402, "ห้องพักสอง").user_id, timezone.now(), "เบอร์ 0855550002")
    R3 = C.note_customer_message(cust(403, "ห้องพักสาม").user_id, timezone.now(), "เบอร์ 0855550003")
    ck("(ก่อนจ่าย) ลีดที่ให้เบอร์แล้วอยู่ในห้องพัก", {R1.id, R2.id, R3.id} <= set(tocode_ids()), tocode_ids())
    post_slip("park-slip-1", "TLD10-9101", "085-555-0001", "เซลมัท")
    # เพิ่งหาไปไม่ถึง 3 นาที → รอบกวาดข้ามคนนี้ (ไม่โหลดแชทซ้ำทุกนาที)
    l1 = C.lead_of(ChatOwner.objects.get(pk=R1.id))
    ChatLead.objects.filter(pk=l1.pk).update(auto=dict(l1.auto or {}, _slip_at=timezone.now().isoformat()))
    C.slip_sweep(force=True)
    ck("เพิ่งหาไป (< 3 นาที) = ยังไม่หาซ้ำ", ChatLead.objects.get(pk=l1.pk).code == "", ChatLead.objects.get(pk=l1.pk).code)
    old = (timezone.now() - timedelta(minutes=C.SLIP_SWEEP_MIN + 1)).isoformat()
    ChatLead.objects.filter(pk=l1.pk).update(auto=dict(ChatLead.objects.get(pk=l1.pk).auto or {}, _slip_at=old))
    out = C.slip_sweep(force=True)
    l1 = ChatLead.objects.get(pk=l1.pk)
    sl = (l1.auto or {}).get("_slip") or {}
    ck("★ ใบจ่ายลีดในกลุ่ม → ลีดได้เลขเอง ไม่ต้องรอใครเปิดแชท", l1.code == "TLD10-9101" and out.get("matched", 0) >= 1,
       (l1.code, out))
    ck("★ ได้เลขแล้วออกจากห้องพัก", R1.id not in tocode_ids(), tocode_ids())
    ck("★ จ่ายให้ใคร = แท็กท้ายใบ → ชื่อเล่น", sl.get("seller") == "มัททดสอบ" and sl.get("tag") == "เซลมัท", sl)
    ck("ใครจ่าย = คนโพสต์ใบ (ชื่อ ไม่ใช่ LINE id)", sl.get("by") == "หมิว Oxlet" and not leak.search(sl.get("by", "")), sl)
    ck("ลีดที่ยังไม่มีใบ = ยังอยู่ในห้องพัก", {R2.id, R3.id} <= set(tocode_ids()))
    # รอบกวาดถี่ไม่ได้ (กันทุก worker ทำงานซ้ำทุกคำขอ)
    ck("รอบกวาดเว้น ≥ 55 วิ (ไม่ force = ข้าม)", C.slip_sweep() == {})

    # จ่ายผ่านปุ่มในระบบ → อยู่ในรายการ "จ่ายแล้ว" ด้วย (ผู้รับ = เจ้าของที่โอนให้)
    ok_, msg_ = C.assign_lead(ChatOwner.objects.get(pk=R2.id), A2, "NLD", by="กวางทดสอบ")
    ck("(จ่ายเบอร์ในระบบ R2)", ok_, msg_)
    # ลีดที่ได้เลขจากใบก่อนมีช่อง "จ่ายให้ใคร" → รอบกวาดเติมให้จากเลข
    post_slip("park-slip-3", "TLD10-9103", "085-555-0003", "เอหนึ่ง", by_name="กวาง")
    l3 = C.lead_of(ChatOwner.objects.get(pk=R3.id))
    ChatLead.objects.filter(pk=l3.pk).update(code="TLD10-9103",
                                             auto={"_slip": {"at": timezone.now().isoformat(), "group": "ห้องจ่ายเบอร์ ทดสอบ"}})
    C.slip_sweep(force=True)
    sl3 = (ChatLead.objects.get(pk=l3.pk).auto or {}).get("_slip") or {}
    ck("★ ใบเก่าที่ยังไม่รู้ผู้รับ → เติมจากเลขลีด", sl3.get("seller") == "เอหนึ่ง" and sl3.get("by") == "กวาง", sl3)

    al = {r["id"]: r for r in C.assigned_list()}
    a1, a2, a3 = al.get(R1.id) or {}, al.get(R2.id) or {}, al.get(R3.id) or {}
    ck("รายการจ่ายแล้ว: ใบในกลุ่ม → ผู้รับ + ใครจ่าย + ทางไหน",
       a1.get("seller") == "มัททดสอบ" and a1.get("by") == "หมิว Oxlet" and a1.get("how") == "ใบในห้องจ่ายเบอร์"
       and a1.get("code") == "TLD10-9101", a1)
    ck("รายการจ่ายแล้ว: ปุ่มในระบบ → ผู้รับ = เจ้าของ · ป้ายทดลอง",
       a2.get("seller") == "เอสอง" and a2.get("by") == "กวางทดสอบ" and a2.get("how") == "ระบบ (ทดลอง)", a2)
    ck("รายการจ่ายแล้ว: ใบเก่าที่เติมผู้รับแล้ว", a3.get("seller") == "เอหนึ่ง", a3)
    ats = [r["at"] for r in C.assigned_list()]
    ck("เรียงล่าสุดก่อน", ats == sorted(ats, reverse=True), ats[:5])
    # ใบเก่าเกิน 7 วัน ไม่อยู่ในรายการ
    l1 = ChatLead.objects.get(code="TLD10-9101")
    ChatLead.objects.filter(pk=l1.pk).update(auto=dict(l1.auto, _slip=dict(l1.auto["_slip"],
                                             at=(timezone.now() - timedelta(days=8)).isoformat())))
    ck("ใบเก่าเกิน 7 วัน = ไม่อยู่ในรายการจ่ายแล้ว", R1.id not in {r["id"] for r in C.assigned_list()})
    ChatLead.objects.filter(pk=l1.pk).update(auto=l1.auto)

    # ลูกค้าจำลองไม่ไปดึงใบของลูกค้าจริงมา (กติกาเดิมของ autofill — รอบกวาดต้องไม่เลี่ยง)
    post_slip("park-slip-sim", "TLD10-9109", "085-555-0009", "เอหนึ่ง")
    so = C.sim_customer("เบอร์ 0855550009 ครับ")
    C.slip_sweep(force=True)
    ck("★ ลูกค้าจำลอง = รอบกวาดไม่ดึงใบจ่ายลีดจริงมาปน", C.lead_of(ChatOwner.objects.get(pk=so.id)).code == "",
       C.lead_of(ChatOwner.objects.get(pk=so.id)).code)
    C.sim_clear()
    # cron (tick ทุกนาที) เป็นคนกวาดจริง — ไม่ต้องรอใครเปิดหน้า
    R4 = C.note_customer_message(cust(404, "ห้องพักสี่").user_id, timezone.now(), "เบอร์ 0855550004")
    post_slip("park-slip-4", "TLD10-9104", "0855550004", "เอหนึ่ง")
    C._SWEEP["at"] = 0.0
    tk = C.tick()
    ck("★ cron tick กวาดห้องพักให้เอง", C.lead_of(ChatOwner.objects.get(pk=R4.id)).code == "TLD10-9104"
       and (tk.get("slipSweep") or {}).get("matched", 0) >= 1, tk)
    C._SWEEP["at"] = 0.0
    ld4 = C.lead_of(ChatOwner.objects.get(pk=R4.id))
    ChatLead.objects.filter(pk=ld4.pk).update(code="", auto={})
    s_, d = J(ADM, "/connect/api/inbox?view=tocode")
    ck("★ แอดมินเปิดห้องพัก = กวาดให้ทันที (ไม่ต้องรอ cron)", R4.id not in [r["id"] for r in d.get("rows", [])]
       and C.lead_of(ChatOwner.objects.get(pk=R4.id)).code == "TLD10-9104", [r["id"] for r in d.get("rows", [])])

    # ผ่านหน้าเว็บ — แอดมินได้ "จ่ายแล้ว" · เซลล์ไม่ได้ · ไม่มี LINE id หลุด
    r_ = ADM.get("/connect/api/inbox?view=tocode", secure=True)
    d = json.loads(r_.content.decode("utf-8"))
    got = {x["id"]: x for x in d.get("assigned") or []}
    ck("API ห้องพัก (แอดมิน) มีรายการจ่ายแล้ว + ผู้รับ", got.get(R1.id, {}).get("seller") == "มัททดสอบ"
       and got.get(R2.id, {}).get("seller") == "เอสอง", list(got))
    ck("★ API ห้องพัก: ไม่มี LINE user id หลุด", not leak.search(r_.content.decode()))
    s_, d = J(SA1, "/connect/api/inbox?view=tocode")
    ck("เซลล์ไม่ได้รายการจ่ายแล้ว", "assigned" not in d, list(d))

    # ═════════════════════════════════════════════════════════════════════
    print("[29] ลูกค้าอยากขายรถให้เรา — แอดมินส่งเข้ากลุ่มเคสHOT ของจัดซื้อ (ใบ \"โค้ด : OC-…\" · เจ้าของให้สังเกตกลุ่ม)")
    from checkout.leadgroup import parse_buycase
    BUY_HOT_MEE, BUY_HOT_TARD = "C" + "7" * 32, "C" + "6" * 32

    def buy_slip(gid, gname, mid, code, phone, name, chan, tag=""):
        txt = ("โค้ด : %s\nADS  : -\nรุ่น : MAZDA 2 ปี20 เทา\nเลขไมล์ : 56464 กม\nทะเบียน : 1 ขน 691 กทม\n"
               "เบอร์ติดต่อ  : %s\nชื่อลูกค้า : %s / %s \nเพิ่มเติม :  \nขายเพราะ :  \nราคากลางรับซื้อจากตาราง : \n%s"
               % (code, phone, name, chan, ("@" + tag + "  ") if tag else ""))
        return GroupChat.objects.create(chat_type="group", group_id=gid, group_name=gname, message_id=mid,
                                        sender_id="U%032x" % 79, sender_name="โดนัท", direction="in",
                                        msg_type="text", text=txt, sent_at=timezone.now())

    pb = parse_buycase("โค้ด : OC-7436\nADS  : -\nรุ่น : MAZDA 2\nเบอร์ติดต่อ  : 087-532-6156\n"
                       "ชื่อลูกค้า : New_matter / LINE@ \nเพิ่มเติม :  \n@หมีน้อย  \n") or {}
    ck("แกะใบเคสรับซื้อ: โค้ด/เบอร์/ชื่อ/ช่องทาง/แท็ก", pb.get("case_code") == "OC-7436" and pb.get("phone") == "087-532-6156"
       and pb.get("name") == "New_matter" and pb.get("channel") == "LINE@" and pb.get("assigned") == "หมีน้อย", pb)
    ck("รถในใบเคสรับซื้อ = รถของลูกค้า (เก็บแยกช่อง ไม่ใช่รถที่จะซื้อ)", pb.get("car") == "MAZDA 2")
    ck("ข้อความตามงาน (ไม่ได้ขึ้นต้นด้วยโค้ด) ≠ ใบ",
       parse_buycase("OC-7436 ลูกค้าทักมาในLine@ ค่ะ ติดต่อหาลูกค้าหน่อยค่ะ @หมีน้อย") is None)
    ck("ใบจ่ายลีดขาย ≠ ใบเคสรับซื้อ", parse_buycase("Ac Lead No. NLD10-8401\nเบอร์โทร : 0811111111") is None)
    ck("โค้ด SC (เคสVERY HOT) ก็อ่านได้", (parse_buycase("โค้ด : SC-  7562\nเบอร์ติดต่อ : 0811111111") or {})
       .get("case_code") == "SC-7562")
    ck("ช่องทางขัดกับที่ลูกค้าทักมา = ไม่ใช่คนเดียวกัน (จับด้วยชื่อ)",
       C._channel_fits("LINE@", fb=False) and not C._channel_fits("เพจguru", fb=False)
       and C._channel_fits("เพจguru", fb=True) and not C._channel_fits("Line@ guru เจมส์", fb=True)
       and C._channel_fits("", fb=True))

    Employee.objects.create(nickname="พี่หมี", position="จัดซื้อ", display_name="หมีน้อย")
    Employee.objects.create(nickname="ต๊าด", position="จัดซื้อ", display_name="•Tard'ANUPonG•")
    C._TAGNICK["at"] = 0.0
    B1 = C.note_customer_message(cust(501, "New_matter").user_id, timezone.now(), "อยากขายมาสด้า 2 ปี 2020 เบอร์ 0866660001")
    B2 = C.note_customer_message(cust(502, "ขายรถไม่แท็ก").user_id, timezone.now(), "เบอร์ 0866660002 ครับ")
    B3 = C.note_customer_message(cust(503, "Supamard").user_id, timezone.now(), "ไอดีไลน์ supa_m ค่ะ")
    B4 = C.note_customer_message(cust(504, "ชื่อซ้ำเพจ").user_id, timezone.now(), "ไอดีไลน์ dup_pg ค่ะ")
    B5 = C.note_customer_message(cust(505, "ทั้งขายทั้งซื้อ").user_id, timezone.now(), "เบอร์ 0866660005")
    ck("(ก่อนส่ง) ทั้ง 5 คนอยู่ในห้องพัก", {B1.id, B2.id, B3.id, B4.id, B5.id} <= set(tocode_ids()), tocode_ids())
    buy_slip(BUY_HOT_MEE, "เคสHOT (พี่หมี) ซื้อ-ขายรถช่องทางออนไลน์", "buy-1", "OC-7436", "0866660001",
             "New_matter", "LINE@", tag="หมีน้อย")
    buy_slip(BUY_HOT_TARD, "เคสHOT (พี่ต๊าด) ซื้อ-ขายรถช่องทางออนไลน์", "buy-2", "OC-7440", "086-666-0002",
             "คนอื่นชื่อไม่ตรง", "เพจguru")
    buy_slip(BUY_HOT_MEE, "เคสHOT (พี่หมี) ซื้อ-ขายรถช่องทางออนไลน์", "buy-3", "OC-7441", "-",
             "Supamard", "Line@ guru เจมส์", tag="หมีน้อย")
    buy_slip(BUY_HOT_MEE, "เคสHOT (พี่หมี) ซื้อ-ขายรถช่องทางออนไลน์", "buy-4", "OC-7442", "-",
             "ชื่อซ้ำเพจ", "เพจguru", tag="หมีน้อย")
    buy_slip(BUY_HOT_TARD, "เคสHOT (พี่ต๊าด) ซื้อ-ขายรถช่องทางออนไลน์", "buy-5", "OC-7443", "0866660005",
             "ทั้งขายทั้งซื้อ", "LINE@", tag="•Tard'ANUPonG•")
    post_slip("buy-5-sale", "NLD10-9150", "0866660005", "เอหนึ่ง")            # มีใบลีดขายด้วย → ใบขายชนะ
    C.slip_sweep(force=True)

    def buy_of(o):
        return (C.lead_of(ChatOwner.objects.get(pk=o.id)).auto or {}).get(C.BUY_KEY) or {}

    l1 = C.lead_of(ChatOwner.objects.get(pk=B1.id))
    b1 = buy_of(B1)
    ck("★ ใบเคสรับซื้อ (เบอร์ตรง) → ออกจากห้องพัก", B1.id not in tocode_ids(), tocode_ids())
    ck("★ จดเลขเคส + ส่งให้ใคร (แท็ก @หมีน้อย → พี่หมี) + ใครส่ง", b1.get("code") == "OC-7436"
       and b1.get("seller") == "พี่หมี" and b1.get("by") == "โดนัท" and "พี่หมี" in b1.get("group", ""), b1)
    ck("★ เลขเคสรับซื้อไม่ใส่ช่อง Code ของลีดขาย", l1.code == "", l1.code)
    ck("★ ไม่แท็ก → ผู้รับจากชื่อกลุ่ม (พี่ต๊าด → ต๊าด ในทะเบียน)", buy_of(B2).get("seller") == "ต๊าด", buy_of(B2))
    ck("★ ไม่มีเบอร์ → จับด้วยชื่อตรงทั้งชื่อ (LINE@ ตรงกับลูกค้า LINE)", buy_of(B3).get("code") == "OC-7441", buy_of(B3))
    ck("★ ชื่อตรงแต่ใบเขียนว่ามาจากเพจ ลูกค้าทัก LINE = ไม่จับคู่ (ไม่เดา)", buy_of(B4) == {} and B4.id in tocode_ids(),
       buy_of(B4))
    l5 = C.lead_of(ChatOwner.objects.get(pk=B5.id))
    ck("มีทั้งใบขายและใบรับซื้อ → ใบลีดขายชนะ (ได้เลขลีด)", l5.code == "NLD10-9150" and buy_of(B5) == {},
       (l5.code, buy_of(B5)))
    al = {r["id"]: r for r in C.assigned_list()}
    r1 = al.get(B1.id) or {}
    ck("รายการจ่ายแล้ว: เคสรับซื้อ → ส่งให้ใคร · ทางไหน · ป้ายรับซื้อ", r1.get("kind") == "buy" and r1.get("code") == "OC-7436"
       and r1.get("seller") == "พี่หมี" and r1.get("how") == "ส่งจัดซื้อ · เคสHOT (พี่หมี)", r1)
    ck("รายการจ่ายแล้ว: ใบขายยังเป็น kind=sale", (al.get(B5.id) or {}).get("kind") == "sale", al.get(B5.id))
    rj = C.row_json(ChatOwner.objects.get(pk=B1.id))
    ck("รายชื่อมีป้ายเลขเคสรับซื้อ (แยกจากเลขลีด)", rj.get("buyCode") == "OC-7436" and rj.get("code") == "", rj)
    s_, d = J(ADM, "/connect/api/chat?id=%d" % B1.id)
    ck("แผงข้อมูลลูกค้าบอกว่าส่งจัดซื้อแล้ว", s_ == 200 and ((d.get("lead") or {}).get("buy") or {}).get("code") == "OC-7436",
       (s_, (d.get("lead") or {}).get("buy")))
    r_ = ADM.get("/connect/api/inbox?view=tocode", secure=True)
    ck("★ API ห้องพัก (มีเคสรับซื้อ) ไม่มี LINE user id หลุด", r_.status_code == 200 and not leak.search(r_.content.decode()))

    # ═════════════════════════════════════════════════════════════════════
    print("[30] ปุ่มจ่ายเบอร์ส่งเข้ากลุ่มจ่ายเบอร์จริง + แท็กเซลล์ (6 ต.ค.69 · เจ้าของ: \"ต่อจริงๆ ส่งจริงๆ\")")
    from checkout import slippost as SP
    from checkout.models import FbProfile
    MEMBERS, SEND_MODE, SENT, SENT_H, SMID = set(), ["ok"], [], [], [0]

    def _p30(url, *a, **k):                       # ขอบระบบ: LINE push
        CALLS.append(("post", url, k.get("json")))
        if "/message/push" in url:
            body = k.get("json") or {}
            SENT.append(body)
            SENT_H.append(k.get("headers") or {})
            if SEND_MODE[0] == "fail":
                return _R(400, {"message": "Failed to send messages"})
            if SEND_MODE[0] == "mention" and any(m.get("type") == "textV2" for m in body.get("messages", [])):
                return _R(400, {"message": "The request body has 1 error(s)", "details": [
                    {"message": "The mentioned user is not found in the group", "property": "messages[0].substitution"}]})
            SMID[0] += 1                          # LINE ออก message id ไม่ซ้ำกันเลย — ของปลอมต้องไม่ซ้ำด้วย
            return _R(200, {"sentMessages": [{"id": "sm-%d" % SMID[0], "quoteToken": "q"}]})
        return _R(200, {})

    def _g30(url, *a, **k):                       # ขอบระบบ: LINE ถามว่าคนนี้อยู่ในกลุ่มไหม
        CALLS.append(("get", url, None))
        mm = re.search(r"/v2/bot/group/([^/]+)/member/([^/?]+)", url)
        if mm:
            return _R(200, {"displayName": "x"}) if mm.group(2) in MEMBERS else _R(404, {"message": "Not found"})
        return _R(404, {"message": "Not found"})

    def assigned(cid):
        return ChatLead.objects.get(chat_id=cid)

    _g0, _p0, _site0 = requests.get, requests.post, settings.SITE_URL
    requests.get, requests.post = _g30, _p30
    settings.SITE_URL = "https://oxlet.test"
    try:
        C.save_cfg(dict(C.cfg(), slip_post=True, slip_group="", slip_group_reject=""))
        CRMONLY = "C" + "e" * 32
        nowi = timezone.now().isoformat()
        cache_store.set_kv("line_groups", {
            ASG: {"name": "ห้องจ่ายเบอร์ บ้านเก่า", "channels": ["push"], "lastSeen": nowi},
            REJ: {"name": "ห้องจ่ายเบอร์ REJECT", "channels": ["push"], "lastSeen": nowi},
            CRMONLY: {"name": "ห้องจ่ายเบอร์ (บอทเดิม)", "channels": ["crm"], "lastSeen": nowi},
            PARK: {"name": "ADMIN เก็บ Lead", "channels": ["push"], "lastSeen": nowi}})
        rr = SP.rooms()
        ck("หาห้องเอง: เลขปกติ → บ้านเก่า · เลข R → REJECT", rr["main"]["id"] == ASG and rr["reject"]["id"] == REJ, rr)
        ck("★ ห้องที่มีแต่บอทเดิมได้ยิน ไม่ถูกเลือก (บอทตัวส่งส่งไม่ได้)", CRMONLY not in [r["id"] for r in SP.lead_rooms()])
        ck("ห้องพัก Lead ไม่ถูกนับเป็นห้องจ่ายเบอร์", PARK not in [r["id"] for r in SP.lead_rooms()])
        ck("เลข R… → ห้อง REJECT · เลขปกติ → บ้านเก่า",
           SP.room_for("RNLD10-1")["id"] == REJ and SP.room_for("NLD10-1")["id"] == ASG)
        _c30, errs = C.clean_cfg({"slip_group": "U123"})
        ck("ตั้งกลุ่มจ่ายเบอร์ผิดรูปแบบ = ฟ้อง ไม่เงียบ", errs and "group id" in errs[0], errs)
        C.save_cfg(dict(C.cfg(), slip_group=REJ))
        ck("ตั้งห้องเองได้ (ชนะการหาจากชื่อ)", SP.rooms()["main"]["id"] == REJ and SP.rooms()["main"]["auto"] is False)
        C.save_cfg(dict(C.cfg(), slip_group=""))

        A1_PUSH = "U" + "7" * 32
        LineProfile.objects.create(user_id=A1_PUSH, display_name="เอหนึ่ง LINE", is_employee=True, employee=A1,
                                   channel="push")
        MEMBERS.add(A1_PUSH)
        cache_store.set_kv("checkin_group_member", {})

        # ── ลูกค้า LINE: โอนแชท (ตอบผ่าน Connect) + ส่งใบเข้ากลุ่ม + แท็ก ──
        L1 = C.note_customer_message(cust(601, "ลูกค้าส่งจริง").user_id, timezone.now(), "สนใจ civic เบอร์ 0866000601 ครับ")
        nxt = C.last_running() + 1
        s_, d = J(ADM, "/connect/api/chat?id=%d" % L1.id)
        ph = ((d.get("codeHelp") or {}).get("post") or {})
        ck("กล่องจ่ายเบอร์บอกล่วงหน้าว่าจะส่งเข้าห้องไหน", ph.get("on") is True and ph.get("room") == "ห้องจ่ายเบอร์ บ้านเก่า"
           and ph.get("rejectRoom") == "ห้องจ่ายเบอร์ REJECT" and ph.get("fb") is False, ph)
        SENT.clear(); SENT_H.clear()
        s_, d = J(ADM, "/connect/api/assign_lead", {"id": L1.id, "emp": A1.id, "base": "NLD"})
        ld = assigned(L1.id)
        ck("จ่ายเบอร์ลูกค้า LINE + เลขต่อจากเลขรัน", s_ == 200 and ld.code == "NLD%d-%d" % (MON, nxt), (s_, d, ld.code))
        ck("★ เลขจริง (ไม่ติดป้ายทดลอง)", ld.code_demo is False and (ld.auto or {}).get("code") == "จ่ายเบอร์")
        ck("★ ส่งเข้าห้องบ้านเก่า 1 ครั้ง ด้วย token บอทตัวส่ง", len(SENT) == 1 and SENT[0]["to"] == ASG
           and SENT_H[0].get("Authorization") == "Bearer tok-push", (SENT, SENT_H))
        m0 = (SENT[0]["messages"] if SENT else [{}])[0]
        ck("★ แท็กเซลล์ด้วยไอดีฝั่งบอทตัวส่ง (textV2 · กดแล้วเด้งหาคน)", m0.get("type") == "textV2"
           and m0["substitution"]["seller"]["mentionee"]["userId"] == A1_PUSH and m0["text"].endswith("{seller}"), m0)
        tx = m0.get("text", "")
        # ★ 6 ต.ค.69 เจ้าของกำหนด pattern จากรูป: 11 บรรทัด · ช่องว่าง = "-" · แท็กบรรทัดสุดท้าย · ไม่มีบรรทัดอื่นแทรก
        want = ["Ac Lead No. " + ld.code, "Ads : -", "ชื่อ Account: -", "ชื่อลูกค้า : -", "ID LINE : -",
                "ชื่อไลน์ : ลูกค้าส่งจริง", "เบอร์โทร : 0866000601", "ช่องทาง : LINE@", "รถ : -",
                "ไลฟ์ : -", "เพิ่มเติม : -", "{seller}"]
        ck("★ ใบที่ส่งตรง pattern ที่เจ้าของกำหนดทุกบรรทัด", tx.split("\n") == want, tx.split("\n"))
        pi = ld.post_info or {}
        ck("จด post_info: สำเร็จ + ห้อง + แท็กได้", pi.get("ok") and pi.get("group") == ASG and pi.get("tagged") is True
           and pi.get("groupName") == "ห้องจ่ายเบอร์ บ้านเก่า" and not pi.get("sending"), pi)
        ck("ข้อความบอกแอดมินว่าส่งเข้าห้องไหน + แท็กใคร", "ส่งเข้า \"ห้องจ่ายเบอร์ บ้านเก่า\"" in d.get("message", "")
           and "@เอหนึ่ง" in d.get("message", "") and (d.get("post") or {}).get("ok"), d)
        ck("★ LINE: โอนแชทให้เซลล์", ChatOwner.objects.get(pk=L1.id).owner_id == A1.id)
        s_, d = J(SA1, "/connect/api/chat?id=%d" % L1.id)
        ck("★ LINE: เซลล์ตอบลูกค้าผ่าน Connect ได้ (ไม่ใช่สิทธิ์เก็บข้อมูลอย่างเดียว)", s_ == 200 and d.get("canReply") is True
           and "เก็บข้อมูลเท่านั้น" not in (d.get("replyWhy") or ""), (d.get("canReply"), d.get("replyWhy")))
        ck("หน้าเว็บได้สถานะการส่ง", ((d.get("lead") or {}).get("post") or {}).get("ok") is True
           and "mid" not in ((d.get("lead") or {}).get("post") or {}), (d.get("lead") or {}).get("post"))
        g = GroupChat.objects.filter(group_id=ASG, direction="out").order_by("-id").first()
        ps = parse_leadsheet(g.text if g else "") or {}
        ck("★ ใบที่ระบบส่ง เก็บในคลังแชทกลุ่มด้วย (อ่านกลับได้: เลข + @เซลล์)", g and g.message_id == "sm-1"
           and ps.get("lead_code") == ld.code and ps.get("assigned") == "เอหนึ่ง" and g.sender_name == "admin",
           (g and g.text[-60:], ps))
        ck("เลขรันถัดไปต่อจากใบที่ระบบส่ง", C.last_running() == nxt, C.last_running())
        ck("ลูกค้าที่จ่ายแล้วออกจากห้องพัก", L1.id not in tocode_ids())
        r1 = {r["id"]: r for r in C.assigned_list()}.get(L1.id) or {}
        ck("รายการจ่ายแล้ว: บอกว่าส่งเข้ากลุ่มแล้ว + ให้ใคร", r1.get("how") == "ระบบ → ส่งเข้ากลุ่มแล้ว"
           and r1.get("seller") == "เอหนึ่ง", r1)
        s_, d = J(ADM, "/connect/api/assign_lead", {"id": L1.id, "resend": True})
        ck("★ ส่งสำเร็จแล้ว กดส่งซ้ำ = ปฏิเสธ (ใบไม่เบิ้ลในกลุ่ม)", s_ == 400 and "ไปแล้ว" in d.get("error", "") and len(SENT) == 1,
           (s_, d))
        s_, d = J(SA1, "/connect/api/assign_lead", {"id": L1.id, "resend": True})
        ck("เซลล์กดส่งซ้ำไม่ได้", s_ == 403, s_)

        # ── เซลล์ไม่อยู่ในกลุ่ม → ไม่แท็ก (พิมพ์ @ชื่อเล่น) แต่ใบยังถึงกลุ่ม ──
        MEMBERS.discard(A1_PUSH); cache_store.set_kv("checkin_group_member", {})
        L2 = C.note_customer_message(cust(602, "ลูกค้าเซลล์นอกกลุ่ม").user_id, timezone.now(), "เบอร์ 0866000602")
        SENT.clear()
        s_, d = J(ADM, "/connect/api/assign_lead", {"id": L2.id, "emp": A1.id, "base": "NLD"})
        m0 = (SENT[0]["messages"] if SENT else [{}])[0]
        pi = assigned(L2.id).post_info or {}
        ck("★ เซลล์ไม่อยู่ในกลุ่ม = ไม่แท็ก (พิมพ์ @ชื่อเล่น) ใบยังถึงกลุ่ม", len(SENT) == 1 and m0.get("type") == "text"
           and m0.get("text", "").endswith("@เอหนึ่ง") and pi.get("ok") and pi.get("tagged") is False
           and "ไม่ได้อยู่ในกลุ่ม" in pi.get("tagWhy", ""), (m0.get("type"), pi))

        # ── LINE ไม่รับการแท็ก → ส่งซ้ำแบบพิมพ์ชื่อ (ใบไม่หาย) ──
        MEMBERS.add(A1_PUSH); cache_store.set_kv("checkin_group_member", {})
        SEND_MODE[0] = "mention"
        L3 = C.note_customer_message(cust(603, "ลูกค้าแท็กพลาด").user_id, timezone.now(), "เบอร์ 0866000603 {ทดสอบปีกกา}")
        C.save_lead_field(ChatOwner.objects.get(pk=L3.id), "more", "งบ {3 แสน}")
        SENT.clear()
        s_, d = J(ADM, "/connect/api/assign_lead", {"id": L3.id, "emp": A1.id, "base": "NLD"})
        pi = assigned(L3.id).post_info or {}
        ck("★ LINE ปฏิเสธการแท็ก = ส่งซ้ำแบบพิมพ์ชื่อ ใบถึงกลุ่ม", len(SENT) == 2 and SENT[0]["messages"][0]["type"] == "textV2"
           and SENT[1]["messages"][0]["type"] == "text" and pi.get("ok") and pi.get("tagged") is False, (len(SENT), pi))
        ck("ข้อความลูกค้าที่มีวงเล็บปีกกา ไม่ถูกตีเป็นตัวแทนที่ของ textV2",
           "{3" not in SENT[0]["messages"][0]["text"] and "(3 แสน)" in SENT[0]["messages"][0]["text"]
           and "{3 แสน}" in SENT[1]["messages"][0]["text"], SENT[0]["messages"][0]["text"][-80:])
        SEND_MODE[0] = "ok"

        # ── ส่งไม่สำเร็จ → การจ่ายในระบบยังอยู่ + กดส่งอีกครั้งได้ ──
        SEND_MODE[0] = "fail"
        L4 = C.note_customer_message(cust(604, "ลูกค้าส่งไม่ออก").user_id, timezone.now(), "เบอร์ 0866000604")
        SENT.clear()
        s_, d = J(ADM, "/connect/api/assign_lead", {"id": L4.id, "emp": A1.id, "base": "NLD"})
        ld4 = assigned(L4.id)
        ck("★ ส่งเข้ากลุ่มไม่สำเร็จ = ยังจ่ายเบอร์ในระบบ (เลข + เซลล์อยู่) + บอกเหตุผลภาษาคน",
           s_ == 200 and ld4.code and ChatOwner.objects.get(pk=L4.id).owner_id == A1.id
           and (ld4.post_info or {}).get("ok") is False and "บอทตัวส่ง" in (ld4.post_info or {}).get("error", "")
           and (ld4.post_info or {}).get("tagged") is False
           and "ส่งเข้ากลุ่มอีกครั้ง" in d.get("message", ""), (d, ld4.post_info))
        ck("ไม่เก็บใบที่ส่งไม่ถึงลงคลังแชทกลุ่ม",
           not GroupChat.objects.filter(group_id=ASG, direction="out", text__contains=ld4.code).exists())
        ck("★ เลขที่ส่งไม่สำเร็จยังนับในเลขรัน (คนถัดไปไม่ได้เลขซ้ำ)",
           C.last_running() >= int(ld4.code.split("-")[1]), (C.last_running(), ld4.code))
        r4 = {r["id"]: r for r in C.assigned_list()}.get(L4.id) or {}
        ck("รายการจ่ายแล้ว: บอกว่ายังส่งไม่สำเร็จ", r4.get("how") == "ระบบ (ยังส่งเข้ากลุ่มไม่สำเร็จ)", r4)
        SEND_MODE[0] = "ok"; SENT.clear()
        s_, d = J(ADM, "/connect/api/assign_lead", {"id": L4.id, "resend": True})
        ck("★ กด \"ส่งเข้ากลุ่มอีกครั้ง\" → สำเร็จ", s_ == 200 and (d.get("post") or {}).get("ok") and len(SENT) == 1
           and (assigned(L4.id).post_info or {}).get("ok"), (s_, d))
        ChatLead.objects.filter(chat_id=L4.id).update(post_info={"ok": False, "error": "x",
                                                                  "sending": timezone.now().isoformat()})
        SENT.clear()
        s_, d = J(ADM, "/connect/api/assign_lead", {"id": L4.id, "resend": True})
        ck("กดส่งซ้ำระหว่างที่อีกคำขอกำลังส่ง = ปฏิเสธ (กันใบเบิ้ล)", s_ == 400 and "กำลังส่ง" in d.get("error", "") and not SENT,
           (s_, d))

        # ── เลขขึ้นต้น R → ห้อง REJECT ──
        L5 = C.note_customer_message(cust(605, "ลูกค้ารีเจ็ค").user_id, timezone.now(), "เบอร์ 0866000605")
        SENT.clear()
        s_, d = J(ADM, "/connect/api/assign_lead", {"id": L5.id, "emp": A1.id, "base": "NLD", "reject": True})
        ck("★ เลขขึ้นต้น R → ส่งเข้าห้องจ่ายเบอร์ REJECT", s_ == 200 and SENT and SENT[0]["to"] == REJ
           and assigned(L5.id).code.startswith("RNLD"), (s_, d, SENT and SENT[0]["to"]))

        # ── ลูกค้า Facebook: ส่งเข้ากลุ่ม + เซลล์ได้สิทธิ์เก็บข้อมูลเท่านั้น ──
        fpx = FbProfile.objects.create(channel="111", user_id="PSIDX9", thread_id="t_x9", display_name="ลูกค้าเฟซส่งจริง")
        F1 = ChatOwner.objects.create(fb_profile=fpx, last_at=timezone.now())
        C.save_lead_field(F1, "phone", "0866000609")
        s_, d = J(ADM, "/connect/api/chat?id=%d" % F1.id)
        ck("กล่องจ่ายเบอร์ของลูกค้า FB บอกล่วงหน้าว่าเซลล์ได้สิทธิ์เก็บข้อมูลเท่านั้น",
           ((d.get("codeHelp") or {}).get("post") or {}).get("fb") is True
           and "เก็บข้อมูลเท่านั้น" in ((d.get("codeHelp") or {}).get("post") or {}).get("fbNote", ""), d.get("codeHelp"))
        SENT.clear()
        s_, d = J(ADM, "/connect/api/assign_lead", {"id": F1.id, "emp": A1.id, "base": "NLD"})
        txt = SENT[0]["messages"][0]["text"] if SENT else ""
        ck("★ ลูกค้า Facebook: ส่งเข้ากลุ่ม + แท็ก + บอกว่าเซลล์ได้สิทธิ์เก็บข้อมูลเท่านั้น", s_ == 200 and len(SENT) == 1
           and SENT[0]["messages"][0]["type"] == "textV2" and "เก็บข้อมูลเท่านั้น" in d.get("message", "")
           and "ชื่อไลน์ : -" in txt and "เบอร์โทร : 0866000609" in txt and txt.endswith("{seller}"), (d, txt))
        ck("ลูกค้า Facebook: เป็นลูกค้าของเซลล์ในระบบ", ChatOwner.objects.get(pk=F1.id).owner_id == A1.id)
        s_, d = J(SA1, "/connect/api/chat?id=%d" % F1.id)
        ck("★ ลูกค้า Facebook: เซลล์เปิดดู+กรอกข้อมูลลีดได้ แต่ตอบไม่ได้", s_ == 200 and d.get("leadEditable") is True
           and d.get("replyOn") is False and "เก็บข้อมูลเท่านั้น" in d.get("replyWhy", ""), (s_, d.get("replyWhy")))
        s_, d = J(SA1, "/connect/api/lead", {"id": F1.id, "field": "occupation", "value": "พนักงานบริษัท"})
        ck("เซลล์กรอกข้อมูลลีดของลูกค้า Facebook ได้", s_ == 200, (s_, d))
        s_, d = J(SA1, "/connect/api/reply", {"id": F1.id, "text": "สวัสดีครับ"})
        ck("★ เซลล์ตอบลูกค้า Facebook ไม่ได้", s_ == 403, (s_, d))

        # ── ลูกค้าจำลอง / บัญชีทดสอบ = ไม่ส่งเข้ากลุ่มจริง ──
        TS = C.test_seller("A")
        L6 = C.note_customer_message(cust(606, "ลูกค้าให้บัญชีทดสอบ").user_id, timezone.now(), "เบอร์ 0866000606")
        SENT.clear()
        s_, d = J(ADM, "/connect/api/assign_lead", {"id": L6.id, "emp": TS.id, "base": "NLD"})
        ck("★ จ่ายให้บัญชีทดสอบ = ไม่ส่งเข้ากลุ่มจริง (เลขทดลอง)", s_ == 200 and not SENT and assigned(L6.id).code_demo is True
           and "ไม่ส่งเข้ากลุ่มจริง" in d.get("message", ""), (s_, d, len(SENT)))
        C.sim_customer("สนใจรถ เบอร์ 0866000607")
        SIM = ChatOwner.objects.filter(profile__user_id__startswith=C.SIM_PREFIX).order_by("-id").first()
        s_, d = J(ADM, "/connect/api/chat?id=%d" % SIM.id)
        ck("ลูกค้าจำลอง: กล่องจ่ายเบอร์บอกว่าไม่ส่งเข้ากลุ่ม",
           ((d.get("codeHelp") or {}).get("post") or {}).get("on") is False, (d.get("codeHelp") or {}).get("post"))
        SENT.clear()
        s_, d = J(ADM, "/connect/api/assign_lead", {"id": SIM.id, "emp": A1.id, "base": "NLD"})
        ck("★ ลูกค้าจำลอง = ไม่ส่งเข้ากลุ่มจริง", s_ == 200 and not SENT and assigned(SIM.id).code_demo is True, (s_, d))
        s_, d = J(ADM, "/connect/api/assign_lead", {"id": SIM.id, "resend": True})
        ck("ลูกค้าจำลอง: กดส่งเข้ากลุ่มไม่ได้", s_ == 400 and not SENT, (s_, d))
        C.sim_clear()

        # ── ลีดภายนอกในห้องพัก (TikTok ฯลฯ) — แท็กในกลุ่ม + จดว่าจ่ายให้ใคร ──
        post(PARK, 110, slip("TLD10-", acc="คนส่งจริง", phone="0866000620"))
        LP._CACHE["val"] = None
        pid = [i["id"] for i in LP.board(cache_sec=0)["waiting"] if i["account"] == "คนส่งจริง"][0]
        SENT.clear()
        s_, d = J(ADM, "/connect/api/park_assign", {"mid": pid, "emp": A1.id, "base": "TLD"})
        ex = ExtLead.objects.get(message_id=pid)
        m0 = SENT[0]["messages"][0] if SENT else {}
        ck("★ ลีดภายนอก: ส่งเข้ากลุ่ม + แท็ก + เลขจริง", s_ == 200 and len(SENT) == 1 and SENT[0]["to"] == ASG
           and m0.get("type") == "textV2" and ex.code_demo is False and (ex.post_info or {}).get("ok")
           and (d.get("post") or {}).get("ok"), (s_, d))
        ck("★ ใบของลีดภายนอก: ข้อมูลจากใบร่าง + ช่องทาง/ไลฟ์เป็นคำตาม dropdown ของชีต",
           m0.get("text", "").split("\n") == ["Ac Lead No. " + ex.code, "Ads : -", "ชื่อ Account: คนส่งจริง",
                                               "ชื่อลูกค้า : -", "ID LINE : -", "ชื่อไลน์ : -", "เบอร์โทร : 0866000620",
                                               "ช่องทาง : LIVE Tiktok / ช่องขายบอส", "รถ : Yaris ativ", "ไลฟ์ : Live Sale",
                                               "เพิ่มเติม : -", "{seller}"], m0.get("text", "").split("\n"))
        sx = LP.slip_text(ExtLead.objects.get(pk=ex.pk))
        ck("ปุ่มคัดลอกของลีดภายนอก = pattern เดียวกัน + @เซลล์", sx.split("\n")[:-1] == m0.get("text", "").split("\n")[:-1]
           and sx.endswith("\n@เอหนึ่ง"), sx)
        b = LP.board(cache_sec=0)
        ab = next((i for i in b["assigned"] if i["account"] == "คนส่งจริง"), {})
        ck("★ ห้องพักเห็นใบที่ระบบส่ง (จับคู่ใบจริงในห้องจ่ายเบอร์) + สถานะการส่ง",
           ab.get("code") == ex.code and ((ab.get("sys") or {}).get("post") or {}).get("ok"), ab)
        s_, d = J(ADM, "/connect/api/park_assign", {"mid": pid, "resend": True})
        ck("ลีดภายนอกส่งแล้ว กดส่งซ้ำ = ปฏิเสธ", s_ == 400 and len(SENT) == 1, (s_, d))

        # ── ไม่มี LINE user id หลุดออกหน้าเว็บ ──
        bad = [p_ for p_ in ("/connect/api/chat?id=%d" % L1.id, "/connect/api/inbox?view=tocode", "/connect/api/config",
                             "/connect/api/chat?id=%d" % F1.id)
               if leak.search(ADM.get(p_, secure=True).content.decode())]
        ck("★ API ของการจ่ายเบอร์ ไม่มี LINE user id หลุด (รวมไอดีที่ใช้แท็ก)", not bad, bad)
        s_, d = J(ADM, "/connect/api/config")
        ck("หน้าตั้งค่าเห็นห้องจ่ายเบอร์ที่จะส่ง", ((d.get("slip") or {}).get("rooms") or {}).get("main", {}).get("id") == ASG
           and d.get("cfg", {}).get("slip_post") is True, d.get("slip"))

        # ── pattern ตามรูปที่เจ้าของส่งมา + คำตาม dropdown ของชีตจ่ายเบอร์ ──
        BJ = C.note_customer_message(cust(611, "Ben Jao LINE").user_id, timezone.now(), "สวัสดีครับ")
        bj = C.lead_of(ChatOwner.objects.get(pk=BJ.id))
        ChatLead.objects.filter(pk=bj.pk).update(account="Ben Jao", line_id="hannork", channel="", branch="")
        bjo = ChatOwner.objects.select_related("profile").get(pk=BJ.id)
        bjo.profile.display_name = ""
        st = C.slip_text(bjo, ChatLead.objects.get(pk=bj.pk))
        ck("★ ใบจ่ายลีด = pattern ในรูปเป๊ะ (ลูกค้า Ben Jao)", st.split("\n") == [
            "Ac Lead No. -", "Ads : -", "ชื่อ Account: Ben Jao", "ชื่อลูกค้า : -", "ID LINE : hannork", "ชื่อไลน์ : -",
            "เบอร์โทร : -", "ช่องทาง : -", "รถ : -", "ไลฟ์ : -", "เพิ่มเติม : -"], st.split("\n"))
        ps = parse_leadsheet("Ac Lead No. NLD10-1234\n" + "\n".join(st.split("\n")[1:]) + "\n@เอหนึ่ง") or {}
        ck("อ่านใบกลับ: \"-\" = ช่องว่าง (ไม่เอา \"-\" ไปเติมข้อมูล)", ps.get("account") == "Ben Jao"
           and ps.get("line_id") == "hannork" and "channel" not in ps and "car" not in ps and ps.get("assigned") == "เอหนึ่ง", ps)
        CH = {"Live tiktok ช่องขายบอส": "LIVE Tiktok / ช่องขายบอส", "TikTok แซน": "Tiktok ช่องแซน",
              "TikTok ช่องแซน": "Tiktok ช่องแซน", "Line@": "LINE@", "เพจguru": "เพจ Guru", "เบอร์กลาง/เพจ": "เบอร์กลาง / เพจ",
              "TikTok ช่องหลัก": "Tiktok  ช่องหลัก", "Live TIKTOK ช่องหลัก": "LIVE Tiktok / ช่องหลัก",
              "TikTok ช่อง888": "TIKTOK ช่อง888", "Live tiktok ช่องguru": "LIVE Tiktok / ช่อง Guru",
              "TIKTOK รถเข้าใหม่ อ๊อกเล็ตธ์": "TIKTOK รถเข้าใหม่อ๊อกเล็ตธ์", "TikTok guru": "Tiktok Guru"}
        bad_ch = {k: C.dd_pick("channel", k) for k, v in CH.items() if C.dd_pick("channel", k) != v}
        ck("★ ช่องทางที่คนพิมพ์ในกลุ่ม (วัดจริง 30 วัน) → คำตาม dropdown ของชีต", not bad_ch, bad_ch)
        ck("ช่องทางที่ไม่มีในชีต = ไม่เดา (คงคำเดิม)", C.dd_pick("channel", "tiktok ช่องปรึกษา") == ""
           and C.dd_pick("channel", "Live  sale tiktok ช่องขายบอส") == "")
        keys = [C._ch_key(o) for o in C.dd_options("channel")]
        ck("คีย์เทียบช่องทางของตัวเลือกในชีตไม่ชนกันเอง (ทุกตัวแยกกันได้)", len(keys) == len(set(keys)), keys)
        ck("ไลฟ์: \"live sale\" → ทีมไลฟ์ \"Live Sale\"", C.dd_pick("live_team", "live sale") == "Live Sale"
           and C.dd_pick("live_team", "Live  Productions") == "Live Productions")
        ChatLead.objects.filter(pk=bj.pk).update(live="live infu", live_team="", channel="TikTok แซน")
        st = C.slip_text(bjo, ChatLead.objects.get(pk=bj.pk))
        ck("ใบ: ช่องทาง/ไลฟ์ เป็นคำตาม dropdown", "ช่องทาง : Tiktok ช่องแซน" in st and "ไลฟ์ : Live Infu" in st, st)
        ChatLead.objects.filter(pk=bj.pk).update(live_team="Live boss")
        st = C.slip_text(bjo, ChatLead.objects.get(pk=bj.pk))
        ck("ใบ: ไลฟ์ = ช่องทีมไลฟ์ก่อน (คอลัมน์เดียวกันในชีต)", "ไลฟ์ : Live boss" in st, st)

        # ── ปิดสวิตช์ = โหมดทดลองเดิม ──
        C.save_cfg(dict(C.cfg(), slip_post=False))
        L7 = C.note_customer_message(cust(607, "ลูกค้าปิดสวิตช์").user_id, timezone.now(), "เบอร์ 0866000607")
        SENT.clear()
        s_, d = J(ADM, "/connect/api/assign_lead", {"id": L7.id, "emp": A1.id, "base": "NLD"})
        ck("ปิดสวิตช์ = ไม่ส่งเข้ากลุ่ม (ทดลองเดิม)", s_ == 200 and not SENT and assigned(L7.id).code_demo is True, (s_, d))
    finally:
        requests.get, requests.post, settings.SITE_URL = _g0, _p0, _site0

    # ═════════════════════════════════════════════════════════════════════
    print("[31] จับ keyword จากแชท → ช่องโปรไฟล์ลีด (7 ต.ค.69 · เจ้าของ: \"จับ keyword แล้วลงตาม dropdown\")")
    from checkout.models import ChatLead
    _dd_saved = cache_store.get_kv(C.DD_KEY)
    K1 = C.note_customer_message(cust(701, "ลูกค้าคีย์เวิร์ด").user_id, timezone.now(),
                                 "เป็นพนักงานโรงงานครับ เงินเดือน 18,000 อายุงาน 2 ปี มีผ่อนมอไซค์อยู่ ผ่อนตรง")
    kl = ChatLead.objects.filter(chat_id=K1.id).first()
    ck("★ ข้อความเข้า = เติมโปรไฟล์ทันที (ไม่ต้องรอใครเปิดแชท)", kl is not None and kl.occupation == "พนักงานโรงงาน"
       and kl.income == "18000" and kl.job_tenure == "2 ปี", kl and (kl.occupation, kl.income, kl.job_tenure))
    ck("ประวัติผ่อนสรุปเป็นคำสั้นๆ", kl is not None and "ผ่อนมอเตอร์ไซค์" in kl.pay_history and "ผ่อนตรง" in kl.pay_history,
       kl and kl.pay_history)
    ck("ประเภทลูกค้า = ตัวเลือกของชีต (dropdown)", kl is not None and kl.customer_type == "พนักงานบริษัท"
       and kl.customer_type in C.dd_options("customer_type"), kl and kl.customer_type)
    ck("จดว่ามาจากแชท + จับจากคำไหน", kl is not None and kl.auto.get("occupation") == "แชท"
       and "18,000" in (kl.auto.get("_kw") or {}).get("income", ""), kl and kl.auto)
    K1 = ChatOwner.objects.select_related("profile", "owner").get(pk=K1.id)
    lj = C.lead_json(K1)
    ck("หน้าเว็บได้ \"จับจากคำไหน\" (autoWhy) แต่ไม่เห็นคีย์ภายใน", "income" in (lj.get("autoWhy") or {})
       and "_kw" not in (lj.get("auto") or {}), (lj.get("autoWhy"), lj.get("auto")))
    K2 = C.note_customer_message(cust(702, "ลูกค้าเงียบ").user_id, timezone.now(), "สวัสดีครับ ขอดูรูปรถหน่อย")
    ck("ไม่เจอ keyword = ไม่สร้างแถวข้อมูลลีดเปล่า", not ChatLead.objects.filter(chat_id=K2.id).exists())
    # คนแก้แล้ว ระบบไม่ทับ
    C.save_lead_field(K1, "occupation", "ช่างเชื่อม", by="เอหนึ่ง")
    C.note_customer_message(K1.profile.user_id, timezone.now(), "จริงๆ ทำงานบริษัทครับ")
    ck("★ คนแก้อาชีพแล้ว ข้อความใหม่ไม่ทับ", ChatLead.objects.get(chat_id=K1.id).occupation == "ช่างเชื่อม")
    # สถานะลูกค้า: ข้อความล่าสุดชนะ · คนตั้งเองแล้วล็อก
    C.note_customer_message(K1.profile.user_id, timezone.now(), "สนใจมากครับ อยากออกเลย")
    s1 = ChatLead.objects.get(chat_id=K1.id).customer_status
    C.note_customer_message(K1.profile.user_id, timezone.now(), "ขอคิดดูก่อนนะครับ ขอปรึกษาแฟนก่อน")
    s2 = ChatLead.objects.get(chat_id=K1.id).customer_status
    ck("★ สถานะเปลี่ยนตามข้อความล่าสุด (สนใจมาก → ลังเล)", s1 == "สนใจมาก" and s2 == "ลังเล", (s1, s2))
    C.save_lead_field(K1, "customer_status", "จอง", by="เอหนึ่ง")
    C.note_customer_message(K1.profile.user_id, timezone.now(), "ได้รถแล้วครับ ขอบคุณ")
    ck("★ คนตั้งสถานะเองแล้ว ข้อความใหม่ไม่ทับ", ChatLead.objects.get(chat_id=K1.id).customer_status == "จอง")
    # dropdown ของชีต: ไม่มีตัวเลือก = ไม่เติม · ชุดที่อ่านไว้ก่อนมีช่องสถานะ = ใช้ชุดที่จำไว้เฉพาะช่องที่ขาด
    cache_store.set_kv(C.DD_KEY, {"fields": {"customer_type": ["พนักงานบริษัท", "ไม่แจ้งอาชีพ"]},
                                  "tab": "ตุลาคม 69", "at": timezone.now().isoformat()})
    C._DD.update(at=0.0, val=None)
    K3 = C.note_customer_message(cust(703, "แม่ค้าออนไลน์").user_id, timezone.now(),
                                 "ขายของออนไลน์ค่ะ ยังไม่แน่ใจเลยค่ะ")
    k3 = ChatLead.objects.get(chat_id=K3.id)
    ck("★ ชีตไม่มีตัวเลือก \"ค้าขาย\" = ไม่เติมประเภทลูกค้า (แต่อาชีพเติม)", k3.customer_type == ""
       and k3.occupation == "ขายของออนไลน์", (k3.customer_type, k3.occupation))
    ck("★ ชุด dropdown ที่อ่านไว้ก่อนมีช่องสถานะ → ใช้ชุดที่จำไว้ (สถานะยังเติมได้)", k3.customer_status == "ลังเล",
       k3.customer_status)
    ck("ช่องที่อ่านจากชีตได้ ชีตชนะ (ไม่เอาชุดที่จำไว้มาปน)", C.dd_options("customer_type") == ["พนักงานบริษัท", "ไม่แจ้งอาชีพ"])
    # type ตามตัวหน้าของเลขลีด
    K3 = ChatOwner.objects.select_related("profile", "owner").get(pk=K3.id)
    ChatLead.objects.filter(chat_id=K3.id).update(code="RWLD10-8500/1")
    ck("type ว่าง + มีเลขลีด → เติมตามตัวหน้า (RWLD → Hot)", C.autofill(K3).lead_type == "Hot",
       ChatLead.objects.get(chat_id=K3.id).lead_type)
    if _dd_saved is None:
        cache_store.set_kv(C.DD_KEY, {})
    else:
        cache_store.set_kv(C.DD_KEY, _dd_saved.get("data", _dd_saved) if isinstance(_dd_saved, dict) else _dd_saved)
    C._DD.update(at=0.0, val=None)

finally:
    _runner.teardown_databases(_old)

print("\nผ่าน %d / %d" % (len(OK), len(OK) + len(BAD)))
if BAD:
    print("ไม่ผ่าน:\n  - " + "\n  - ".join(BAD))
    sys.exit(1)
