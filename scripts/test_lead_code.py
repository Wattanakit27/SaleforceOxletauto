# -*- coding: utf-8 -*-
"""เทสต์ตัวหน้าเลขลีดอัตโนมัติ (★ 17 ต.ค.69 · checkout/lead_code.py)

    python scripts/test_lead_code.py

  [1] เกณฑ์ของเจ้าของทีละข้อ (decide — ฟังก์ชันล้วน) + กับดักคำไทย
  [2] ใช้งานจริงผ่านหน้าเว็บ: เปิดแชท → กล่องจ่ายเบอร์แนะนำตัวหน้า + เหตุผล · ติ๊กเอกสารรายได้ → คิดใหม่ ·
      กดชื่อเซลล์ (ไม่ส่ง base) → ออกเลขตามตัวหน้าที่แนะนำ · ห้องพัก Lead / Run Auto โชว์ตัวหน้า · LD ออกเลขได้ ·
      ไม่ติ๊ก R ให้ลีดใหม่ · type ที่คนตั้งชนะ · TikTok คงเดิม

ฐานข้อมูลทดสอบแยก · ปลอมที่ขอบระบบเท่านั้น (`requests` = LINE/Google)
"""
import io
import json
import os
import sys
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

import requests  # noqa: E402
from django.contrib.sessions.backends.signed_cookies import SessionStore  # noqa: E402
from django.test import Client  # noqa: E402
from django.utils import timezone  # noqa: E402

from checkout import connect as C  # noqa: E402
C.BG_FILL = False
import checkout.people as _people  # noqa: E402
_people.BG = False
from checkout import leadflow as _LF  # noqa: E402
_LF.BG_SLOW = False
from checkout import chatmedia as _CMD  # noqa: E402
_CMD.BG = False
from checkout import comments as _CMT  # noqa: E402
_CMT.BG = False
from checkout import lead_code as L  # noqa: E402
from checkout.models import ChatFollowup, ChatLead, Employee, GroupChat, LineProfile  # noqa: E402
import dashboard.services.google_sheets as _GS  # noqa: E402


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


requests.post = lambda *a, **k: _R(200, {})
requests.get = lambda *a, **k: _R(404, {"message": "Not found"})


def _no_sheet(*a, **k):
    raise RuntimeError("ไม่ต่อ Google Sheets ในเทสต์")


_GS.fetch_sheet = _no_sheet
_GS.fetch_lead_dropdowns = _no_sheet

OK, BAD = [], []


def ck(name, cond, got=""):
    (OK if cond else BAD).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else "   ได้: %r" % (got,)))


class Ld:
    """ข้อมูลลีดจำลองสำหรับ decide()"""
    def __init__(self, **k):
        for f in ("phone", "line_id", "occupation", "income", "job_tenure", "pay_history", "customer_type",
                  "customer_status", "fill_note", "admin_profile", "more"):
            setattr(self, f, k.get(f, ""))
        self.auto = k.get("auto", {})


def D(ld, tin=(), tout=(), **kw):
    return L.decide(ld, list(tin), list(tout), **kw)


try:
    print("[1] เกณฑ์ของเจ้าของ")
    ck("months: 2 ปี / 1 ปี 6 เดือน / 8 เดือน / 1 ปีกว่า / ไม่ถึง 1 ปี / หลายปี",
       [L.months(x) for x in ("2 ปี", "1 ปี 6 เดือน", "8 เดือน", "1 ปีกว่า", "ไม่ถึง 1 ปี", "หลายปี", "", "นาน")]
       == [24, 18, 8, 13, 11, 36, None, None])
    ck("money: 22,000 / 1.5 หมื่น / 15k / ไม่มีตัวเลข",
       [L.money(x) for x in ("22,000", "1.5 หมื่น", "15k", "ไม่บอก")] == [22000, 15000, 15000, None])
    P = "0812345678"
    CASES = [
        ("NLD: ให้เบอร์ ไม่ให้ข้อมูล", Ld(phone=P), [P], {}, "NLD"),
        ("BLD: ไม่ให้ข้อมูล + รถในสต็อกไม่เกิน 3 แสน", Ld(phone=P), ["สนใจ vios"], {"prices": [219000, 259000]}, "BLD"),
        ("BLD: ไม่ให้ข้อมูล + งบ 2.5 แสน", Ld(phone=P), ["งบ 2.5 แสน"], {}, "BLD"),
        ("ไม่ใช่ BLD: รถในสต็อกบางคันเกิน 3 แสน", Ld(phone=P), ["สนใจ city"], {"prices": [259000, 459000]}, "NLD"),
        ("LD: เงินเดือนน้อย (12,000)", Ld(phone=P, occupation="พนักงานโรงงาน", income="12000"), [], {}, "LD"),
        ("LD: อายุงานไม่ถึงปี", Ld(phone=P, occupation="พนักงาน", job_tenure="8 เดือน"), [], {}, "LD"),
        ("LD: ไม่มีผ่อน (ไม่มีเครดิต)", Ld(phone=P, occupation="ค้าขาย", pay_history="ไม่มีเครดิต"), [], {}, "LD"),
        ("LD: เครดิตอ่อน (ติดบูโร)", Ld(phone=P, occupation="ค้าขาย", pay_history="ติดบูโร"), [], {}, "LD"),
        ("NLD: ให้ข้อมูลบางส่วน ไม่อ่อนไม่ดี", Ld(phone=P, occupation="ขับรถ", income="25000"), [], {}, "NLD"),
        ("WLD: อายุงานเกิน 1 ปี", Ld(phone=P, occupation="พนักงาน", job_tenure="3 ปี"), [], {}, "WLD"),
        ("WLD: ประวัติผ่อนเกิน 1 ปี (จากแชท)", Ld(phone=P, occupation="ขับรถ"), ["ผ่อนรถมา 2 ปีแล้ว ตรงทุกงวด"], {}, "WLD"),
        ("WLD: เงินเดือนน้อยแต่อายุงาน 2 ปี (ระดับสูงสุดชนะ)", Ld(phone=P, income="12000", job_tenure="2 ปี"), [], {}, "WLD"),
        ("HLD: อายุงาน 3 ปี + สลิปเงินเดือน + เบอร์", Ld(phone=P, job_tenure="3 ปี"), ["มีสลิปเงินเดือนครับ"], {}, "HLD"),
        ("WLD: โปรไฟล์ดี + เอกสาร แต่ให้แค่ไอดีไลน์", Ld(line_id="somchai", job_tenure="3 ปี"), ["มีสลิปเงินเดือนครับ"], {}, "WLD"),
        ("HLD: ซื้อสด + เราแจ้งราคาแล้ว", Ld(phone=P), ["ซื้อสดครับ"], {"tout": ["คันนี้ราคา 459,000 บาทครับ"]}, "HLD"),
        ("HLD: ซื้อสด + งบพอกับรถ", Ld(phone=P), ["ซื้อสด งบ 5 แสน"], {"prices": [450000]}, "HLD"),
        ("ไม่ใช่ HLD: ซื้อสด แต่งบไม่พอกับรถ", Ld(phone=P), ["ซื้อสด งบ 3 แสน"], {"prices": [450000]}, "NLD"),
        ("HLD: ไปเซ็นที่อื่นมา ไฟแนนซ์ผ่านแล้ว", Ld(phone=P), ["ไปเซ็นที่อื่นมา ไฟแนนซ์ผ่านแล้ว แต่ยังไม่ได้รถ"], {}, "HLD"),
        ("HLD: อนุมัติแล้ว", Ld(phone=P), ["ทางแบงค์อนุมัติแล้วครับ กำลังเลือกรถ"], {}, "HLD"),
        ("WLD: นัดเข้ามาดูรถ มีวันชัด", Ld(phone=P), ["พรุ่งนี้บ่ายสองเข้าไปดูรถ"], {"visit_date": "18/10 14:00"}, "WLD"),
        ("NLD: จะเข้ามาดูรถ ไม่บอกวัน", Ld(phone=P), ["ไว้จะเข้าไปดูรถครับ"], {}, "NLD"),
        ("WLD: มีรถมาเทิร์น + โปรไฟล์ดี", Ld(phone=P, job_tenure="5 ปี"), ["มีรถเก่ามาเทิร์นครับ"], {}, "WLD"),
        ("NLD: มีรถมาเทิร์น ไม่รู้โปรไฟล์", Ld(phone=P), ["มีรถเก่ามาเทิร์นครับ"], {}, "NLD"),
        ("NLD: ให้เช็คราคารถเทิร์นก่อน", Ld(phone=P), ["ช่วยประเมินราคารถเก่าก่อนได้ไหม"], {}, "NLD"),
        ("HLD: แอดมินติ๊กเอกสาร + อายุงาน 2 ปี", Ld(phone=P, job_tenure="2 ปี"), [], {"doc_flag": True}, "HLD"),
        ("แอดมินเอาติ๊กเอกสารออก ชนะคำในแชท", Ld(phone=P, job_tenure="2 ปี"), ["มีสลิปเงินเดือน"], {"doc_flag": False}, "WLD"),
    ]
    for name, ld, tin, kw, want in CASES:
        kw = dict(kw)
        tout = kw.pop("tout", [])
        r = D(ld, tin, tout, **kw)
        ck(name + " → " + want, r["base"] == want and r["why"], (r["base"], r["why"]))
    TRAPS = [
        ("กับดัก: อยากผ่อน 4 ปี ≠ ประวัติผ่อน", Ld(phone=P, occupation="ขับรถ"), ["อยากผ่อน 4 ปี"], "WLD"),
        ("กับดัก: ไม่มีสลิป ≠ มีเอกสาร", Ld(phone=P, job_tenure="3 ปี"), ["ไม่มีสลิปครับ"], "HLD"),
        ("กับดัก: ไฟแนนซ์ไม่ผ่าน ≠ ผ่านแล้ว", Ld(phone=P), ["ยื่นไฟแนนซ์ไม่ผ่าน"], "HLD"),
        ("กับดัก: รออนุมัติ ≠ อนุมัติแล้ว", Ld(phone=P), ["ยื่นไฟแนนซ์รออนุมัติอยู่"], "HLD"),
        ("กับดัก: ผ่านไหม (คำถาม) ≠ ผ่านแล้ว", Ld(phone=P), ["เงินเดือน 15000 ยื่นไฟแนนซ์ผ่านไหม"], "HLD"),
        ("กับดัก: เงินสดไม่พอ ≠ ซื้อสด", Ld(phone=P), ["เงินสดไม่พอ"], "HLD"),
        ("กับดัก: แฟนผ่อนรถมา 3 ปี (ของญาติ)", Ld(phone=P, occupation="แม่บ้าน"), ["แฟนผ่อนรถมา 3 ปี"], "WLD"),
        ("กับดัก: สลิปโอนเงินจอง ≠ สลิปเงินเดือน", Ld(phone=P, job_tenure="3 ปี"), ["ส่งสลิปโอนจองแล้วครับ"], "HLD"),
    ]
    for name, ld, tin, bad in TRAPS:
        r = D(ld, tin)
        ck(name, r["base"] != bad, (r["base"], r["why"]))
    r = D(Ld(phone=P, job_tenure="3 ปี"), ["มีสลิปเงินเดือน", "ซื้อสด"], ["ราคา 399,000"])
    ck("เหตุผลครบทุกเกณฑ์ที่เข้า (เรียงสูง → ต่ำ)", len(r["reasons"]) >= 2 and r["reasons"][0][0] == "HLD", r["reasons"])

    # ═════════════════════════════════════════════════════════════════════
    print("[2] ใช้งานจริงผ่านหน้าเว็บ")
    C.save_cfg(dict(C.cfg(), slip_post=False, room_chat_auto=False))     # โหมดทดลอง — ไม่ส่งเข้ากลุ่ม
    A1 = Employee.objects.create(nickname="เอหนึ่ง", position="ทีม A")
    TELE = Employee.objects.create(nickname="เทเล", position="เทเลเซลล์")
    MON = timezone.localdate().month
    GroupChat.objects.create(chat_type="group", group_id="C" + "8" * 32, group_name="ห้องจ่ายเบอร์ บ้านเก่า",   # ใบตั้งต้น (เลขรัน 4 หลัก)
                             message_id="seed-slip", sender_id="U%032x" % 77, direction="in", msg_type="text",
                             text="Ac Lead No.   NLD%d-8400\nเบอร์โทร : 0800000000" % MON,
                             sent_at=timezone.now() - timedelta(hours=1))
    t0 = timezone.now() - timedelta(minutes=20)

    def chat(n, lines):
        p = LineProfile.objects.create(user_id="U%032x" % n, display_name="ลูกค้า%d" % n)
        o = None
        for i, (d, txt) in enumerate(lines):
            at = t0 + timedelta(minutes=i)
            GroupChat.objects.create(chat_type="user", message_id="m%d-%d" % (n, i), sender_id=p.user_id,
                                     direction=d, msg_type="text", text=txt, sent_at=at)
            if d == "in":
                o = C.note_customer_message(p.user_id, at, txt)
        return o

    def client(user):
        cl = Client()
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

    ADM = client({"user_id": "admin", "nickname": "admin", "position": "admin"})
    o1 = chat(1, [("in", "สนใจ civic ครับ"), ("out", "ขอเบอร์ติดต่อหน่อยครับ"), ("in", "0812345678"),
                  ("in", "เป็นพนักงานบริษัท อายุงาน 3 ปีครับ")])
    s_, d = J(ADM, "/connect/api/chat?id=%d" % o1.id)
    sg = ((d.get("codeHelp") or {}).get("suggest") or {})
    ck("เปิดแชท → แนะนำ WLD (อายุงาน 3 ปี จากแชท)", s_ == 200 and sg.get("base") == "WLD" and "3 ปี" in sg.get("why", ""),
       (s_, sg, (d.get("lead") or {}).get("job_tenure")))
    ck("บอกว่าเป็นตัวหน้าอัตโนมัติ + มีช่องเอกสาร", sg.get("auto") is True and sg.get("doc") is False, sg)
    ck("ลีดใหม่ไม่ติ๊ก R ให้", sg.get("reject") is False)
    ck("ตัวเลือกตัวหน้ามี LD (Moderate)", {"key": "LD", "type": "Moderate"} in (d.get("codeHelp") or {}).get("bases", []))
    s_, r = J(ADM, "/connect/api/assign_lead", {"id": o1.id, "doc": True})
    ck("ติ๊ก มีเอกสารยืนยันรายได้", s_ == 200 and r.get("ok"), (s_, r))
    s_, d = J(ADM, "/connect/api/chat?id=%d" % o1.id)
    sg = d["codeHelp"]["suggest"]
    ck("ติ๊กแล้วคิดใหม่ → HLD (อายุงาน + เอกสาร + เบอร์)", sg["base"] == "HLD" and sg["doc"] and not sg["docAuto"], sg)
    s_, r = J(ADM, "/connect/api/assign_lead", {"id": o1.id, "doc": None})
    s_, d = J(ADM, "/connect/api/chat?id=%d" % o1.id)
    ck("คืนให้ระบบดูจากแชท → กลับเป็น WLD", d["codeHelp"]["suggest"]["base"] == "WLD", d["codeHelp"]["suggest"])
    J(ADM, "/connect/api/assign_lead", {"id": o1.id, "doc": True})
    s_, r = J(ADM, "/connect/api/assign_lead", {"id": o1.id, "emp": A1.id})
    ld = ChatLead.objects.get(chat=o1)                  # อ่านใหม่จากฐาน (o1.lead ที่จำไว้เป็นของเก่า)
    ck("กดชื่อเซลล์ (ไม่ส่งตัวหน้า) → ออกเลข HLD + type Very Hot", s_ == 200 and ld.code.startswith("HLD") and ld.lead_type == "Very Hot",
       (s_, r, ld.code, ld.lead_type))

    o2 = chat(2, [("in", "สนใจกระบะ"), ("in", "เบอร์ 0898765432"), ("in", "เป็นพนักงานโรงงาน เงินเดือน 12000 ครับ")])
    C.mark_park(o2, True, by="admin")
    s_, ib = J(ADM, "/connect/api/inbox?view=tocode")
    row = next((x for x in ib.get("rows") or [] if x["id"] == o2.id), {})
    ck("ห้องพัก Lead: การ์ดแชทบอกตัวหน้า LD + เหตุผล", row.get("pfx") == "LD" and "12,000" in row.get("pfxWhy", ""), row)
    s_, plan = J(ADM, "/connect/api/crm", {"action": "auto_plan"})
    pi = next((p for p in plan.get("plan") or [] if p.get("kind") == "chat" and p.get("id") == o2.id), {})
    ck("Run Auto: แผนบอกตัวหน้าเดียวกัน (LD)", pi.get("pfx") == "LD", (plan.get("plan"), plan.get("skipped")))
    s_, r = J(ADM, "/connect/api/assign_lead", {"id": o2.id, "emp": A1.id})
    ld2 = ChatLead.objects.get(chat=o2)
    ck("ออกเลข LD ได้ + type Moderate", ld2.code.startswith("LD") and ld2.lead_type == "Moderate", (r, ld2.code, ld2.lead_type))

    o3 = chat(3, [("in", "สนใจ vios"), ("in", "0861112222")])
    ld3 = C.lead_of(o3)
    ld3.lead_type, ld3.auto = "Hot", dict(ld3.auto or {}, lead_type="คน")
    ld3.save()
    s_, d = J(ADM, "/connect/api/chat?id=%d" % o3.id)
    ck("type ที่คนตั้งไว้ชนะเกณฑ์อัตโนมัติ (Hot → WLD)", d["codeHelp"]["suggest"]["base"] == "WLD"
       and "type" in d["codeHelp"]["suggest"]["why"], d["codeHelp"]["suggest"])

    o4 = chat(4, [("in", "มีรถเก่ามาเทิร์นครับ"), ("in", "0863334444")])
    ChatFollowup.objects.create(chat=o4, kind=ChatFollowup.VIEWING, due_at=timezone.now() + timedelta(days=1), note="ดูรถ")
    L.forget(o4.id)
    s_, d = J(ADM, "/connect/api/chat?id=%d" % o4.id)
    ck("มีนัดดูรถ (มีวัน) → WLD", d["codeHelp"]["suggest"]["base"] == "WLD" and "นัด" in d["codeHelp"]["suggest"]["why"],
       d["codeHelp"]["suggest"])
    sg = C.suggest_prefix(C.lead_of(o4), C.team_of(TELE), o=o4)
    ck("จ่ายให้เทเลเซลล์ → ติ๊ก A ให้ (ตัวหน้าเดิม)", sg["admin"] is True and sg["base"] == "WLD", sg)
    ld4 = C.lead_of(o4)
    ld4.channel = "TikTok ช่องแซน"
    ld4.save()
    L.forget(o4.id)
    ck("ช่องทาง TikTok คงเป็น TLD", C.suggest_prefix(C.lead_of(o4), "", o=o4)["base"] == "TLD")

    SEL = client({"user_id": "Usel", "nickname": "เอหนึ่ง", "position": "seller"})
    s_, r = J(SEL, "/connect/api/assign_lead", {"id": o4.id, "doc": True})
    ck("เซลล์ติ๊กเอกสารไม่ได้ (แอดมินเท่านั้น)", s_ == 403, (s_, r))

finally:
    _runner.teardown_databases(_old)

print("\nผ่าน %d / %d" % (len(OK), len(OK) + len(BAD)))
if BAD:
    print("ไม่ผ่าน:\n  - " + "\n  - ".join(BAD))
    sys.exit(1)
