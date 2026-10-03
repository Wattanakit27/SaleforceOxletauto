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
    ck("พนักงานทักเข้า OA = ไม่เข้าคิว", C.note_customer_message(STAFF.user_id, t0, "x") is None)
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

finally:
    _runner.teardown_databases(_old)

print("\nผ่าน %d / %d" % (len(OK), len(OK) + len(BAD)))
if BAD:
    print("ไม่ผ่าน:\n  - " + "\n  - ".join(BAD))
    sys.exit(1)
