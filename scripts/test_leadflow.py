# -*- coding: utf-8 -*-
"""เทสต์งานจ่ายเบอร์ (10 ต.ค.69) — สมุดเบอร์ · ไม้ 2 · คิวจ่ายวน · นาฬิกาโทร · การ์ดปุ่ม · อ่านรายงานผล

    python scripts/test_leadflow.py

ฐานข้อมูลทดสอบแยก (สร้างใหม่ทุกครั้ง) · **ปลอมที่ขอบระบบ** (`requests` = LINE/Google · ใบรับรอง Google)
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
settings.SITE_URL = "https://oxlet.test"

import requests  # noqa: E402
from django.contrib.sessions.backends.signed_cookies import SessionStore  # noqa: E402
from django.test import Client  # noqa: E402
from django.utils import timezone  # noqa: E402

import dashboard.services.google_sheets as GS  # noqa: E402
from checkout import connect as C  # noqa: E402
from checkout import leadflow as LF  # noqa: E402
from checkout import phonebook as PB  # noqa: E402
from checkout.models import (ChatLead, ChatOwner, Employee, ExtLead, GroupChat, LeadPhone,  # noqa: E402
                             LeadReport, LeadTask, LineProfile)
from dashboard.services import cache_store  # noqa: E402

C.BG_FILL = False
LF.BG_SLOW = False           # ไม่ให้ thread งานช้าวิ่งชนฐานข้อมูลทดสอบ

# ── ขอบระบบ ─────────────────────────────────────────────────────────
CALLS, SENT, MEMBERS = [], [], set()
SHEET = {"rows": [], "writes": []}    # ชีตลีดปลอม (แท็บเดียว) สำหรับ update_lead_fields


class _R:
    def __init__(self, code=200, js=None):
        self.status_code, self._js = code, (js or {})
        self.text = json.dumps(self._js)
        self.headers = {}

    def json(self):
        return self._js


SMID = [0]


def _post(url, *a, **k):
    body = k.get("json") or {}
    CALLS.append(("post", url, body, (k.get("headers") or {}).get("Authorization", "")))
    if "/message/push" in url:
        SENT.append(body)
        SMID[0] += 1
        return _R(200, {"sentMessages": [{"id": "sm-%d" % SMID[0]}]})
    if "/message/reply" in url:
        return _R(200, {})
    if "values:batchUpdate" in url:
        SHEET["writes"].append(body)
        return _R(200, {"totalUpdatedCells": len(body.get("data") or [])})
    return _R(200, {})


HEADER = ["ว/ด/ป", "เบอร์โทร", "ชื่อ", "Code", "เซลล์", "สถานะลูกค้า", "อาชีพ", "รายได้", "อายุงาน",
          "ประวัติการผ่อน", "ประเภทลูกค้า"]


def _get(url, *a, **k):
    CALLS.append(("get", url, None, ""))
    mm = re.search(r"/v2/bot/group/([^/]+)/member/([^/?]+)", url)
    if mm:
        return _R(200, {"displayName": "x"}) if mm.group(2) in MEMBERS else _R(404, {"message": "Not found"})
    if "sheets.googleapis.com" in url and "fields=sheets.properties.title" in url:
        return _R(200, {"sheets": [{"properties": {"title": "ตุลาคม 69"}}]})
    if "sheets.googleapis.com" in url and "/values/" in url:
        return _R(200, {"values": [HEADER] + SHEET["rows"]})
    return _R(404, {"message": "Not found"})


requests.post, requests.get = _post, _get


class _Cred:
    token = "fake"

    def refresh(self, *_a):
        pass


GS._get_credentials = lambda: _Cred()
GS.load_sheet_config_overrides = lambda *a, **k: None


def _no_sheet(*a, **k):
    raise RuntimeError("ไม่ต่อ Google Sheets ในเทสต์")


GS.fetch_lead_dropdowns = _no_sheet

OK, BAD = [], []


def ck(name, cond, got=""):
    (OK if cond else BAD).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else "   ได้: %r" % (got,)))


TZ = timezone.get_current_timezone()


def at(y, mo, d, hh, mm=0):
    return timezone.make_aware(datetime(y, mo, d, hh, mm), TZ)


def pushes(to=None):
    return [c for c in CALLS if c[0] == "post" and "/message/push" in c[1] and (to is None or c[2].get("to") == to)]


def replies():
    return [c for c in CALLS if c[0] == "post" and "/message/reply" in c[1]]


leak = re.compile(r"U[0-9a-f]{32}")

try:
    # ═════════════════════════════════════════════════════════════════════
    print("[1] สมุดเบอร์: แปลงเบอร์")
    ck("081-234-5678 → 0812345678", PB.norm("081-234-5678") == "0812345678")
    ck("+66 81 234 5678 → 0812345678", PB.norm("+66 81 234 5678") == "0812345678")
    ck("812345678 (ขาด 0) → 0812345678", PB.norm("812345678") == "0812345678")
    ck("เบอร์บ้าน 038-123456 → 038123456", PB.norm("038-123456") == "038123456")
    ck("ไม่ใช่เบอร์ (เลขลีด 9075) = ''", PB.norm("9075") == "")
    ck("ช่องมี 2 เบอร์ → ได้ทั้งคู่", PB.phones_in("081-111-2222 / 089-333-4444") == ["0811112222", "0893334444"])

    # ── พนักงาน ──
    def emp(nick, pos, day_off=""):
        return Employee.objects.create(nickname=nick, position=pos, day_off=day_off, work_start="9:00")

    MAT = emp("มัททดสอบ", "ทีม A")
    FIRST = emp("เฟิร์สทดสอบ", "ทีม A")
    BIW = emp("บิวทดสอบ", "ทีม B")
    OFF = emp("หยุดทดสอบ", "ทีม B", day_off="จันทร์ อังคาร พุธ พฤหัส ศุกร์ เสาร์ อาทิตย์")
    MIW = emp("หมิวทดสอบ", "ออฟฟิศ บ้านเก่า")
    TST = emp("ทดสอบเซลล์ A", "ทีม A")
    UID = {e.id: "U" + ("%032x" % (0xabc000 + e.id)) for e in (MAT, FIRST, BIW, OFF, MIW)}
    for e in (MAT, FIRST, BIW, OFF, MIW):
        LineProfile.objects.create(user_id=UID[e.id], display_name=e.nickname + " LINE", is_employee=True,
                                   employee=e, nickname=e.nickname, channel="push")
        MEMBERS.add(UID[e.id])

    # ═════════════════════════════════════════════════════════════════════
    print("[2] สมุดเบอร์: สร้างจากชีต + เช็คเบอร์ซ้ำ")
    from dashboard.services.google_sheets import LEADS_COL as L

    def row(**kv):
        r = [""] * 40
        for k, v in kv.items():
            r[getattr(L, k)] = v
        return r

    out = PB.rebuild_from_sheet([row(received_date="5/10/2026", phone="081-555-0001", lead_code="NLD10-9001",
                                     sales_rep="มัททดสอบ", channel="LINE@", car_formula="Civic FE"),
                                 row(received_date="1/9/2026", phone="0815550002", lead_code="TLD9-8001",
                                     sales_rep="บิวทดสอบ")])
    ck("สร้างจากชีต 2 เบอร์", out["phones"] == 2 and LeadPhone.objects.filter(source="sheet").count() == 2, out)
    PB.rebuild_from_sheet([row(received_date="5/10/2026", phone="081-555-0001", lead_code="NLD10-9001",
                               sales_rep="มัททดสอบ"), row(received_date="1/9/2026", phone="0815550002",
                                                         lead_code="TLD9-8001", sales_rep="บิวทดสอบ")])
    ck("สร้างซ้ำไม่เบิ้ล", LeadPhone.objects.filter(source="sheet").count() == 2)
    r = PB.check_for_seller("081 555 0001", "บิวทดสอบ")
    ck("เบอร์ของคนอื่น → บอกชื่อเซลล์ + เดือน", r.get("found") and r["seller"] == "มัททดสอบ" and r["month"] == "ต.ค. 69", r)
    ck("★ เบอร์ของคนอื่น → ไม่ส่งเลขลีดออก", "code" not in r, r)
    r = PB.check_for_seller("0815550002", "บิวทดสอบ")
    ck("เบอร์ของตัวเอง → บอกเลขลีด", r.get("mine") and r.get("code") == "TLD9-8001", r)
    ck("เบอร์ไม่เคยเป็นลีด → found=False", PB.check_for_seller("0899999999", "บิวทดสอบ") == {"ok": True, "found": False})
    ck("พิมพ์ 4 ตัวท้าย = ไม่รับ", PB.check_for_seller("0001", "บิวทดสอบ").get("ok") is False)
    d = LF.dup_info("0815550001")
    ck("dup_info สำหรับแอดมิน: เลข + เซลล์ + id", d and d["code"] == "NLD10-9001" and d["sellerId"] == MAT.id, d)
    ck("dup_info ไม่นับเลขของลูกค้าคนเดียวกัน (exclude_code)", LF.dup_info("0815550001", "NLD10-9001") is None)

    # ═════════════════════════════════════════════════════════════════════
    print("[3] ส่งต่อไม้ 2 — R + เลขเดิม + /1")
    ck("TLD9-8129 → RTLD9-8129/1", LF.fwd_code("TLD9-8129") == "RTLD9-8129/1", LF.fwd_code("TLD9-8129"))
    ck("RTLD9-8129/1 → RTLD9-8129/2", LF.fwd_code("RTLD9-8129/1") == "RTLD9-8129/2")
    ck("ANLD10-9010 → RANLD10-9010/1", LF.fwd_code("ANLD10-9010") == "RANLD10-9010/1")
    ck("รูปแบบไม่ใช่เลขลีด = ''", LF.fwd_code("OC-7436") == "" and LF.fwd_code("") == "")
    ck("_CODE_RE รับเลข /1", bool(C._CODE_RE.match("RTLD9-8129/1")))
    ck("run_of ตัด /1", LF.run_of("RTLD9-8129/1") == "8129")

    # ═════════════════════════════════════════════════════════════════════
    print("[4] อ่านรายงาน \"เลข + ผล\"")
    ck("\"9075 รอตอบครับ\"", LF.parse_report("9075 รอตอบครับ") == ("9075", 0, "รอตอบครับ"))
    ck("ไม่เว้นวรรค \"9064ลูกค้าไม่ตอบ\"", LF.parse_report("9064ลูกค้าไม่ตอบ") == ("9064", 0, "ลูกค้าไม่ตอบ"))
    ck("ห้อง REJECT \"8129/1 ได้รถแล้ว\"", LF.parse_report("8129/1 ได้รถแล้ว") == ("8129", 1, "ได้รถแล้ว"))
    ck("★ แอดมินทวง \"9075 @มัท ตามด้วย\" ไม่นับ", LF.parse_report("9075 @มัท ตามด้วย") is None)
    ck("ใบจ่ายลีดไม่นับ", LF.parse_report("Ac Lead No. NLD10-9075\nเบอร์โทร : 0812345678") is None)
    ck("เบอร์โทรนำหน้าไม่นับ", LF.parse_report("0812345678 โทรกลับด้วย") is None)
    ck("ตัวเลขล้วนไม่นับ", LF.parse_report("9075 25,000") is None)
    st = LF.read_report("ไม่รับสายครับ")
    ck("ไม่รับสาย → สถานะ ไม่รับสาย · ไม่ส่งการ์ด", st["fields"].get("customer_status") == "ไม่รับสาย" and not st["rich"], st)
    st = LF.read_report("ลูกค้าจองแล้วครับ โอนจองเรียบร้อย")
    ck("จองแล้ว → จอง · ส่งการ์ด", st["fields"].get("customer_status") == "จอง" and st["rich"], st)
    now0 = at(2026, 10, 9, 10, 0)     # ศุกร์
    st = LF.read_report("อาชีพ พนักงานโรงงาน เงินเดือน 18,000 นัดมาดูรถเสาร์ 10 โมง", now0)
    ck("อาชีพ + รายได้ + นัด → การ์ดยืนยัน", st["rich"] and st["fields"].get("income") == "18,000"
       and "โรงงาน" in (st["fields"].get("occupation") or "") and st["appt"].startswith("2026-10-10T10:00"), st)

    print("[5] วันนัด")
    ck("เสาร์ 10 โมง (วันนี้ศุกร์) → 10 ต.ค. 10:00", LF.parse_appt("นัดมาดูรถเสาร์ 10 โมง", now0) == at(2026, 10, 10, 10))
    ck("พรุ่งนี้บ่ายสอง → 10 ต.ค. 14:00", LF.parse_appt("พรุ่งนี้บ่ายสอง จะเข้ามาดูรถ", now0) == at(2026, 10, 10, 14))
    ck("12/10 4 โมงเย็น → 12 ต.ค. 16:00", LF.parse_appt("นัด 12/10 4 โมงเย็น", now0) == at(2026, 10, 12, 16))
    ck("นัดเที่ยง (วันนี้)", LF.parse_appt("นัดเข้ามาเที่ยง", now0) == at(2026, 10, 9, 12))
    ck("3 ทุ่ม → 21:00", LF.parse_appt("โทรกลับ 3 ทุ่ม", now0) == at(2026, 10, 9, 21))
    ck("14:30 → 14:30", LF.parse_appt("นัด 14:30 ครับ", now0) == at(2026, 10, 9, 14, 30))
    ck("ไม่มีคำว่านัด/มาดู = ไม่เดา", LF.parse_appt("ราคา 10 โมง", now0) is None)
    ck("เวลาที่ผ่านไปแล้ว = ไม่เดา", LF.parse_appt("นัด 08:00", now0) is None)
    ck("วันเสาร์หน้า → 17 ต.ค.", LF.parse_appt("นัดมาดูรถเสาร์หน้า", now0) == at(2026, 10, 17, 10))

    # ═════════════════════════════════════════════════════════════════════
    print("[6] คิวจ่ายวน")
    LF.save_cfg(dict(LF.cfg(), rr_teams=["A", "B"], cap_day=2))
    names = [r["name"] for r in LF.rr_candidates()]
    ck("อยู่ในคิว: เซลล์ทีม A/B", set(names) == {"มัททดสอบ", "เฟิร์สทดสอบ", "บิวทดสอบ"}, names)
    ck("ตัดคนวันหยุด · ออฟฟิศ · บัญชีทดสอบ", "หยุดทดสอบ" not in names and "หมิวทดสอบ" not in names
       and "ทดสอบเซลล์ A" not in names, names)
    LeadTask.objects.create(code="NLD10-1", run="1", seller=BIW, seller_name=BIW.nickname)
    LeadTask.objects.create(code="NLD10-2", run="2", seller=MAT, seller_name=MAT.nickname)
    LeadTask.objects.create(code="NLD10-3", run="3", seller=MAT, seller_name=MAT.nickname)
    cand = LF.rr_candidates()
    ck("คนได้ใบน้อยสุดก่อน (เฟิร์ส 0 ใบ)", cand[0]["name"] == "เฟิร์สทดสอบ", [(r["name"], r["today"]) for r in cand])
    ck("เต็มเพดาน (มัท 2/2) = หลุดคิว", "มัททดสอบ" not in [r["name"] for r in cand])
    ck("exclude คนที่เคยได้เคสนี้", LF.rr_pick(exclude={FIRST.id}).nickname == "บิวทดสอบ")
    LeadTask.objects.filter(code__in=["NLD10-1", "NLD10-2", "NLD10-3"]).delete()
    LF.save_cfg(dict(LF.cfg(), cap_day=12))
    _c, errs = LF.clean_cfg({"call_min": 2, "rr_teams": ["A", "ทีมขาย"]})
    ck("ตั้งค่าผิด = ฟ้องพร้อมบอกช่อง", len(errs) == 2 and "5–240" in errs[0], errs)
    ck("ส่งออกทุกอย่างปิดโดยปริยาย", not any(LF.DEFAULTS[k] for k in
                                            ("card_on", "report_on", "remind_on", "auto_assign", "auto_pull")))

    # ═════════════════════════════════════════════════════════════════════
    print("[7] จ่ายเบอร์ผ่านระบบ → งาน + การ์ดใน push เดียวกัน")
    ASG, REJ = "C" + "1" * 32, "C" + "2" * 32
    nowi = timezone.now().isoformat()
    cache_store.set_kv("line_groups", {
        ASG: {"name": "ห้องจ่ายเบอร์ บ้านเก่า", "channels": ["push"], "lastSeen": nowi},
        REJ: {"name": "ห้องจ่ายเบอร์ REJECT", "channels": ["push"], "lastSeen": nowi}})
    C.save_cfg(dict(C.cfg(), slip_post=True, slip_group="", slip_group_reject="", open="00:00", close="00:00"))
    LF.save_cfg(dict(LF.cfg(), card_on=True, call_min=15))

    def cust(n, name, phone):
        p = LineProfile.objects.create(user_id="U" + ("%032x" % (0xc00000 + n)), display_name=name)
        o = ChatOwner.objects.create(profile=p)
        ChatLead.objects.create(chat=o, phone=phone, customer_name=name, car_text="Civic FE")
        return ChatOwner.objects.select_related("owner", "profile", "fb_profile").get(pk=o.pk)

    # เลขรันล่าสุดในห้อง (ของจริงหลักพัน — ฐานข้อมูลว่างจะได้เลขรัน 1 ซึ่งไม่ใช่รูปแบบเลขลีด)
    GroupChat.objects.create(chat_type="group", group_id=ASG, group_name="ห้องจ่ายเบอร์ บ้านเก่า", message_id="seed-slip",
                             text="Ac Lead No. NLD10-9000\n@ใครสักคน", msg_type="text", direction="in",
                             sent_at=timezone.now() - timedelta(hours=5))
    def LD(o):                                     # อ่านสดจากฐานข้อมูล (o.lead ที่แคชไว้บน instance อาจเก่า)
        return ChatLead.objects.get(chat_id=o.pk)

    O1 = cust(1, "ลูกค้าหนึ่ง", "0866000001")
    n0 = len(pushes(ASG))
    ok, msg = C.assign_lead(O1, MAT, "NLD", by="หมิว")
    code1 = LD(O1).code
    t1 = LeadTask.objects.get(code=code1)
    ck("จ่ายเบอร์สำเร็จ + มีงาน", ok and t1.seller_id == MAT.id and t1.source == "system", (ok, msg))
    ck("นาฬิกาเริ่มเมื่อใบถึงกลุ่ม (posted_at + due 15 นาที)",
       t1.posted_at and abs((t1.due_at - t1.posted_at).total_seconds() - 900) < 5, (t1.posted_at, t1.due_at))
    p = pushes(ASG)[n0:]
    msgs = p[0][2].get("messages") if p else []
    ck("★ ส่งครั้งเดียว: ใบ + การ์ดใน push เดียวกัน", len(p) == 1 and len(msgs) == 2 and msgs[1]["type"] == "flex",
       [(m.get("type")) for m in msgs])
    flex = json.dumps(msgs[1]) if len(msgs) > 1 else ""
    ck("การ์ดมีปุ่มรับเคส/ขอผ่าน/โทร", "lf=ack&t=%d" % t1.id in flex and "lf=pass" in flex and "tel:0866000001" in flex)
    ck("การ์ดจดว่าส่งแล้ว", (t1.card or {}).get("sent") is True, t1.card)
    ck("สมุดเบอร์จดเบอร์จากปุ่มจ่ายเบอร์", LeadPhone.objects.filter(phone="0866000001", source="system",
                                                                    code=code1, seller=MAT.nickname).exists())
    O2 = cust(2, "ลูกค้าสอง", "086-600-0001")
    d2 = LF.dup_info(LD(O2).phone)
    ck("★ ลูกค้าอีกรายเบอร์เดียวกัน → เห็นว่าเป็นของมัทแล้ว", d2 and d2["code"] == code1 and d2["sellerId"] == MAT.id, d2)

    # ═════════════════════════════════════════════════════════════════════
    print("[8] ปุ่มในการ์ด (postback)")

    def pb(data, uid, gid=ASG):
        return {"type": "postback", "replyToken": "rt-%d" % len(CALLS), "postback": {"data": data},
                "source": {"type": "group", "groupId": gid, "userId": uid}}

    r0 = len(replies())
    m = LF.handle_postback(pb(LF._pb("ack", t1.id), UID[BIW.id]), "tok-push")
    ck("คนอื่นกดรับ = ไม่ได้ บอกว่าเป็นของใคร", "มัททดสอบ" in m and not LeadTask.objects.get(pk=t1.id).acked_at, m)
    m = LF.handle_postback(pb("lf=ack&t=%d&s=bad" % t1.id, UID[MAT.id]), "tok-push")
    ck("ลายเซ็นผิด = ใช้ไม่ได้", "ใช้ไม่ได้" in m and not LeadTask.objects.get(pk=t1.id).acked_at, m)
    m = LF.handle_postback(pb(LF._pb("ack", t1.id), UID[MAT.id]), "tok-push")
    ck("เจ้าของกดรับ = acked", LeadTask.objects.get(pk=t1.id).acked_at is not None and "รับเคส" in m, m)
    rr_ = replies()[r0:]
    ck("★ ตอบด้วย reply token (ไม่ใช่ push)", len(rr_) == 3 and all("tok-push" in c[3] for c in rr_), len(rr_))
    ck("ปุ่มที่ไม่ใช่ของเรา = เงียบ", LF.handle_postback(pb("action=other", UID[MAT.id]), "tok-push") == "")

    # ═════════════════════════════════════════════════════════════════════
    print("[9] รายงานผลในห้องจ่ายเบอร์ → นาฬิกาหยุด")
    GroupChat.objects.create(chat_type="group", group_id=ASG, group_name="ห้องจ่ายเบอร์ บ้านเก่า", message_id="old",
                             text="เก่า", sent_at=timezone.now() - timedelta(hours=3))
    cache_store.set_kv(LF.KV_STATE, {})
    run1 = t1.run

    def gmsg(mid, uid, text, gid=ASG):
        return GroupChat.objects.create(chat_type="group", group_id=gid, group_name="ห้องจ่ายเบอร์ บ้านเก่า",
                                        message_id=mid, sender_id=uid, text=text, msg_type="text",
                                        direction="in", sent_at=timezone.now())

    gmsg("m-nudge", UID[MIW.id], "%s @มัท ตามด้วยค่ะ" % run1)
    gmsg("m-admin", UID[MIW.id], "%s รอตอบ" % run1)
    r = LF.process_pending()
    ck("แอดมินทวง / คนที่ไม่ใช่ทีมขาย ไม่นับเป็นรายงาน", r.get("reports") == 0 and LeadReport.objects.count() == 0, r)
    gmsg("m-r1", UID[MAT.id], "%sไม่รับสายครับ" % run1)
    r = LF.process_pending()
    t1.refresh_from_db()
    ck("รายงานของเซลล์ → งานมีรายงาน", r.get("reports") == 1 and t1.first_report_at and t1.reports == 1, r)
    ck("รายงานเฉยๆ ไม่ส่งการ์ดยืนยัน (ปิด report_on อยู่ด้วย)",
       LeadReport.objects.get(message_id="m-r1").state == LeadReport.NOTED)
    r = LF.process_pending()
    ck("รันซ้ำไม่เบิ้ล", r.get("reports", 0) == 0 and LeadReport.objects.count() == 1, r)

    # ═════════════════════════════════════════════════════════════════════
    print("[10] ใบที่แอดมินโพสต์เองในห้อง → งาน (source=group) + สมุดเบอร์")
    gmsg("m-slip", UID[MIW.id], "Ac Lead No. TLD10-9555\nAds : -\nชื่อ Account: บีลูกค้า\nเบอร์โทร : 089-777-0001\n"
         "ช่องทาง : TIKTOK ช่อง888\nรถ : Yaris Ativ\n@บิวทดสอบ")
    LF.process_pending()
    tg = LeadTask.objects.filter(code="TLD10-9555").first()
    ck("สร้างงานจากใบในกลุ่ม · ผู้รับจากแท็ก", tg and tg.source == "group" and tg.seller_id == BIW.id and tg.due_at, tg)
    ck("สมุดเบอร์จดจากใบ", LeadPhone.objects.filter(phone="0897770001", code="TLD10-9555", source="slip").exists())
    gmsg("m-old", UID[BIW.id], "7777 ลูกค้าบอกยังไม่สะดวกคุย")
    GroupChat.objects.create(chat_type="group", group_id=ASG, group_name="ห้องจ่ายเบอร์ บ้านเก่า", message_id="m-oldslip",
                             sender_id=UID[MIW.id], text="Ac Lead No. NLD9-7777\nเบอร์โทร : 0812223333\n@บิวทดสอบ",
                             msg_type="text", direction="in", sent_at=timezone.now() - timedelta(days=20))
    LeadReport.objects.filter(message_id="m-old").delete()
    LF.handle_report(GroupChat.objects.get(message_id="m-old"))
    ck("รายงานของใบเก่า (ก่อนเปิดระบบ) → สร้างงานย้อนหลังจากใบในห้อง",
       LeadReport.objects.get(message_id="m-old").code == "NLD9-7777", LeadReport.objects.get(message_id="m-old").code)

    # ═════════════════════════════════════════════════════════════════════
    print("[11] การ์ดยืนยันแชทส่วนตัว → ลงชีต")
    LF.save_cfg(dict(LF.cfg(), report_on=True))
    SHEET["rows"] = [["10/10/2026", "0866000001", "ลูกค้าหนึ่ง", code1, "มัททดสอบ"] + [""] * 6]
    n0 = len(pushes())
    gmsg("m-rich", UID[MAT.id], "%s ลูกค้าทำงานโรงงาน เงินเดือน 18,000 นัดมาดูรถพรุ่งนี้บ่ายสอง" % run1)
    LF.process_pending()
    rep = LeadReport.objects.get(message_id="m-rich")
    dm = [c for c in pushes()[n0:] if c[2].get("to") == UID[MAT.id]]
    ck("รายงานมีข้อมูลจริง → ส่งการ์ดเข้าแชทส่วนตัวเซลล์", rep.state == LeadReport.ASKED and len(dm) == 1, (rep.state, len(dm)))
    ck("การ์ดยืนยันมีปุ่ม ถูกต้อง/ไม่บันทึก", "lf=ok&r=%d" % rep.id in json.dumps(dm[0][2]) if dm else False)
    m = LF.handle_postback({"type": "postback", "replyToken": "rt-x", "postback": {"data": LF._pb("ok", rep.id, "r")},
                            "source": {"type": "user", "userId": UID[BIW.id]}}, "tok-push")
    ck("คนอื่นกด = ไม่ได้", "การ์ดนี้เป็นของ" in m and LeadReport.objects.get(pk=rep.id).state == LeadReport.ASKED, m)
    m = LF.handle_postback({"type": "postback", "replyToken": "rt-y", "postback": {"data": LF._pb("ok", rep.id, "r")},
                            "source": {"type": "user", "userId": UID[MAT.id]}}, "tok-push")
    rep.refresh_from_db()
    w = SHEET["writes"][-1] if SHEET["writes"] else {}
    cells = {x["range"].split("!")[1]: x["values"][0][0] for x in w.get("data", [])}
    ck("กดถูกต้อง → ลงชีต (แถวของเคสนี้)", rep.state == LeadReport.SAVED and cells.get("H2") == "18,000"
       and "โรงงาน" in cells.get("G2", ""), (rep.state, cells, m))
    SHEET["rows"] = [["10/10/2026", "0866000001", "ลูกค้าหนึ่ง", code1, "บิวทดสอบ"] + [""] * 6]
    res = GS.update_lead_fields(code1, {"occupation": "ค้าขาย"}, 10, expected_seller="มัททดสอบ")
    ck("★ ชีตเป็นของเซลล์อื่น = ไม่เขียนทับ", "error" in res and "บิวทดสอบ" in res["error"], res)
    gmsg("m-rich2", UID[MAT.id], "%s ลูกค้าจองแล้วครับ" % run1)
    LF.process_pending()
    rep2 = LeadReport.objects.get(message_id="m-rich2")
    LF.handle_postback({"type": "postback", "replyToken": "rt-z", "postback": {"data": LF._pb("no", rep2.id, "r")},
                        "source": {"type": "user", "userId": UID[MAT.id]}}, "tok-push")
    ck("กดไม่บันทึก = ข้าม ไม่เขียนชีต", LeadReport.objects.get(pk=rep2.id).state == LeadReport.SKIPPED)

    # ═════════════════════════════════════════════════════════════════════
    print("[12] เตือนนัด")
    LF.save_cfg(dict(LF.cfg(), remind_on=True, remind_min=60))
    LeadReport.objects.filter(pk=rep.id).update(appt_at=timezone.now() + timedelta(minutes=30))
    n0 = len(pushes(UID[MAT.id]))
    LF._remind(LF.cfg(), timezone.now())
    LF._remind(LF.cfg(), timezone.now())
    ck("เตือนนัดครั้งเดียว", len(pushes(UID[MAT.id])) - n0 == 1, len(pushes(UID[MAT.id])) - n0)

    # ═════════════════════════════════════════════════════════════════════
    print("[13] เลยเวลา / ขอผ่าน → จ่ายใหม่ (เลขเดิม)")
    O3 = cust(3, "ลูกค้าสาม", "0866000003")
    C.assign_lead(O3, BIW, "NLD", by="หมิว")
    code3 = LD(O3).code
    t3 = LeadTask.objects.get(code=code3)
    LeadTask.objects.filter(pk=t3.pk).update(due_at=timezone.now() - timedelta(minutes=1))
    LF.tick()
    ck("tick ติดธงเลยเวลา", LeadTask.objects.get(pk=t3.pk).overdue_at is not None)
    LF.save_cfg(dict(LF.cfg(), auto_pull=True, pull_max=1))
    n0 = len(pushes(ASG))
    LF.tick()
    t3.refresh_from_db()
    ck("★ auto_pull: จ่ายใหม่ให้คนถัดไป (เลขเดิม · ใบเดิม แท็กคนใหม่)",
       t3.seller_id != BIW.id and t3.history and t3.history[-1]["seller"] == "บิวทดสอบ"
       and len(pushes(ASG)) - n0 == 1 and LD(O3).code == code3, (t3.seller_name, t3.history))
    ck("โอนแชทตามไปด้วย", ChatOwner.objects.get(pk=O3.pk).owner_id == t3.seller_id)
    LeadTask.objects.filter(pk=t3.pk).update(due_at=timezone.now() - timedelta(minutes=1), overdue_at=timezone.now())
    n0 = len(pushes(ASG))
    LF.tick()
    ck("ครบ pull_max แล้วไม่จ่ายวนซ้ำ", len(pushes(ASG)) == n0)
    LF.save_cfg(dict(LF.cfg(), auto_pull=False))
    O4 = cust(4, "ลูกค้าสี่", "0866000004")
    C.assign_lead(O4, FIRST, "NLD", by="หมิว")
    t4 = LeadTask.objects.get(code=LD(O4).code)
    m = LF.handle_postback(pb(LF._pb("pass", t4.id), UID[FIRST.id]), "tok-push")
    ck("ขอผ่าน → จด passed + บอกให้แอดมินจ่ายใหม่", LeadTask.objects.get(pk=t4.pk).passed_at and "แอดมิน" in m, m)
    ok, msg = LF.reassign(LeadTask.objects.get(pk=t4.pk), BIW, by="หมิว")
    ck("แอดมินจ่ายใหม่ให้คนที่เลือก", ok and LeadTask.objects.get(pk=t4.pk).seller_id == BIW.id, msg)
    ok, msg = LF.reassign(tg, MAT)
    ck("ใบที่แอดมินโพสต์เอง จ่ายใหม่จากระบบไม่ได้ (บอกวิธี)", not ok and "ไม้ 2" in msg, msg)

    # ═════════════════════════════════════════════════════════════════════
    print("[14] ส่งต่อไม้ 2")
    n0 = len(pushes(REJ))
    ok, msg = LF.forward_chat(ChatOwner.objects.select_related("owner", "profile").get(pk=O1.pk), BIW, by="หมิว")
    ld = LD(O1)
    ck("เลขใหม่ R + เลขเดิม + /1", ok and ld.code == "R" + code1 + "/1", (ok, msg, ld.code))
    ck("ใบเข้าห้อง REJECT", len(pushes(REJ)) - n0 == 1)
    ck("โอนลูกค้าให้คนไม้ 2 + จำเลขเดิม", ChatOwner.objects.get(pk=O1.pk).owner_id == BIW.id
       and (ld.auto.get("_prev_codes") or [{}])[-1].get("code") == code1, ld.auto.get("_prev_codes"))
    tf = LeadTask.objects.filter(code=ld.code).first()
    ck("งานใหม่ของเลข /1 (เลขรันเดิม)", tf and tf.run == run1 and tf.seller_id == BIW.id, tf)
    gmsg("m-rj", UID[BIW.id], "%s/1 ได้รถแล้วครับ" % run1, gid=REJ)
    LF.process_pending()
    ck("รายงาน \"เลข/1\" → ผูกกับงานไม้ 2", LeadReport.objects.get(message_id="m-rj").task_id == tf.id)
    ok, msg = LF.forward_chat(ChatOwner.objects.get(pk=O2.pk), MAT)
    ck("ยังไม่มีเลข = ส่งต่อไม่ได้ (บอกให้จ่ายเบอร์ปกติ)", not ok and "จ่ายเบอร์ปกติ" in msg, msg)

    # ═════════════════════════════════════════════════════════════════════
    print("[15] ตอบลูกค้าผ่าน Connect = นาฬิกาหยุด")
    O5 = cust(5, "ลูกค้าห้า", "0866000005")
    C.assign_lead(O5, MAT, "NLD", by="หมิว")
    t5 = LeadTask.objects.get(code=LD(O5).code)
    o5 = ChatOwner.objects.get(pk=O5.pk)
    o5.awaiting_since = timezone.now() - timedelta(minutes=1)
    o5.save()
    C._reply_done(o5, timezone.now(), "สวัสดีครับ", emp=MAT)
    ck("ตอบผ่าน Connect → งานแชทนี้หยุดนับ", LeadTask.objects.get(pk=t5.pk).first_report_at is not None)

    # ═════════════════════════════════════════════════════════════════════
    print("[16] จ่ายวนอัตโนมัติ (ใบร่างในห้องพัก Lead)")
    PARK = "C" + "3" * 32
    gl = (cache_store.get_kv("line_groups") or {}).get("data") or {}
    gl[PARK] = {"name": "ADMIN เก็บ Lead", "channels": ["push"], "lastSeen": nowi}
    cache_store.set_kv("line_groups", gl)
    for i, (ph, nm) in enumerate((("0877000001", "ร่างใหม่"), ("0815550001", "ร่างเบอร์ซ้ำ"))):
        GroupChat.objects.create(chat_type="group", group_id=PARK, group_name="ADMIN เก็บ Lead", message_id="draft-%d" % i,
                                 sender_id=UID[MIW.id], sender_name="หมิว", msg_type="text", direction="in",
                                 text="Ac Lead No. TLD10-\nAds : -\nชื่อ Account: %s\nเบอร์โทร : %s\nช่องทาง : TIKTOK ช่อง888" % (nm, ph),
                                 sent_at=timezone.now() - timedelta(minutes=10))
    from checkout import leadpark
    leadpark.forget()
    LF.save_cfg(dict(LF.cfg(), auto_assign=True, auto_after_min=3))
    got = LF._auto_assign(LF.cfg(), timezone.now())
    leadpark.forget()
    e0 = ExtLead.objects.filter(message_id="draft-0").first()
    ck("ใบร่างที่รอเกินเวลา → จ่ายวนให้คนในคิว", e0 and e0.code and e0.seller_id, got)
    ck("★ เบอร์ซ้ำ = ไม่จ่ายเอง (ให้แอดมินตัดสิน)", not ExtLead.objects.filter(message_id="draft-1", code__gt="").exists()
       and any(x["why"] == "เบอร์ซ้ำ" for x in (LF._kv("leadflow_auto_last").get("skipped") or [])),
       LF._kv("leadflow_auto_last"))
    te = LeadTask.objects.filter(ext=e0).first()
    ck("ใบร่างที่จ่ายแล้ว → มีงาน + การ์ด", te and (te.card or {}).get("sent"), te and te.card)
    LF.save_cfg(dict(LF.cfg(), auto_assign=False))
    ok, msg = LF.forward_ext("draft-0", MAT, by="หมิว")
    e0.refresh_from_db()
    ck("ส่งต่อไม้ 2 ของลีดภายนอก", ok and e0.code.startswith("R") and e0.code.endswith("/1") and e0.seller_id == MAT.id,
       (ok, msg, e0.code))

    # ═════════════════════════════════════════════════════════════════════
    print("[17] API + สิทธิ์")

    def client(user):
        cl = Client()
        if user:
            s_ = SessionStore()
            s_["oxlet_user"] = user
            s_.save()
            cl.cookies[settings.SESSION_COOKIE_NAME] = s_.session_key
        return cl

    def J(cl, path, body=None):
        r_ = cl.post(path, json.dumps(body), content_type="application/json", secure=True) if body is not None \
            else cl.get(path, secure=True)
        try:
            return r_.status_code, json.loads(r_.content.decode("utf-8")), r_.content.decode("utf-8")
        except Exception:
            return r_.status_code, {}, ""

    ADM = client({"user_id": "admin", "nickname": "admin", "position": "admin"})
    SEL = client({"user_id": UID[MAT.id], "nickname": "มัททดสอบ", "seller_name": "มัททดสอบ", "position": "seller"})
    NOB = client(None)
    s_, d, raw = J(ADM, "/connect/api/leadflow")
    ck("แอดมินเปิดค่าตั้ง/งานวันนี้ได้", s_ == 200 and d.get("ok") and d.get("tasks"), s_)
    ck("★ ไม่มี LINE user id หลุดใน API งานจ่ายเบอร์", not leak.search(raw))
    s_, d, _ = J(SEL, "/connect/api/leadflow")
    ck("เซลล์เปิดไม่ได้", s_ == 403)
    s_, d, _ = J(ADM, "/connect/api/leadflow", {"action": "config", "call_min": 1})
    ck("ตั้งค่าผิดผ่าน API = 400", s_ == 400 and "5–240" in d.get("error", ""), d)
    s_, d, raw = J(ADM, "/connect/api/chat?id=%d" % O2.id)
    ch = d.get("codeHelp") or {}
    # เบอร์นี้ถูกส่งต่อไม้ 2 ให้บิวแล้ว ([14]) → เจ้าของล่าสุด = บิว (เลข R…/1)
    ck("แผงจ่ายเบอร์: เบอร์ซ้ำ (เจ้าของล่าสุด) + คิวจ่ายวน", (ch.get("dup") or {}).get("sellerId") == BIW.id
       and (ch.get("dup") or {}).get("code", "").endswith("/1") and ch.get("rr"), ch.get("dup"))
    ck("★ ไม่มี LINE user id หลุดในแผงแชท", not leak.search(raw))
    s_, d, raw = J(ADM, "/connect/api/inbox?view=tocode")
    ck("ห้องพัก Lead มีนาฬิกาโทร", s_ == 200 and (d.get("leadflow") or {}).get("tasks") is not None, s_)
    ck("★ ไม่มี LINE user id หลุดในห้องพัก Lead", not leak.search(raw))
    s_, d, _ = J(NOB, "/api/seller/check_phone", {"phone": "0815550001"})
    ck("เช็คเบอร์: ไม่ login = 401", s_ == 401)
    s_, d, _ = J(SEL, "/api/seller/check_phone", {"phone": "0815550002"})
    ck("เช็คเบอร์: เซลล์ login → ได้คำตอบ (ของบิว)", s_ == 200 and d.get("found") and d.get("seller") == "บิวทดสอบ"
       and "code" not in d, d)
    s_, d, _ = J(SEL, "/api/seller/car_matches")
    ck("รถตรงกับลูกค้า: เซลล์เปิดได้", s_ == 200 and d.get("ok"), d)

    # ═════════════════════════════════════════════════════════════════════
    print("[19] ศูนย์ควบคุมลีด (หน้า Connect แบบใหม่) + งานวันนี้ของเซลล์")
    from checkout import console_data as CD
    import dashboard.services.fetch_dashboard as FD
    LC = GS.LEADS_COL
    tday = timezone.localdate()
    ds = tday.strftime("%d/%m/%Y")

    def lrow(code, phone, seller, z="", admin=""):
        r = [""] * 40
        r[LC.received_date], r[LC.lead_code], r[LC.phone], r[LC.sales_rep] = ds, code, phone, seller
        r[LC.customer_status], r[LC.admin_status], r[LC.car_formula], r[LC.channel] = z, admin, "Civic FE", "LINE@"
        return r

    _orig_ft, _orig_fd = GS.fetch_leads_by_month_tabs, FD.fetch_dashboard_data
    GS.fetch_leads_by_month_tabs = lambda *a, **k: [lrow("NLD10-7001", "0877123401", "มัททดสอบ", z="คืนเคส"),
                                                    lrow("NLD10-7002", "087-712-3401", "บิวทดสอบ"),
                                                    lrow("TLD10-7003", "0877000003", "บิวทดสอบ", z="จอง")]

    def _dago(n):
        return (tday - timedelta(days=n)).strftime("%d/%m/%Y")

    FD.fetch_dashboard_data = lambda *a, **k: {
        "bookingCases": [{"status": "จอง", "date": _dago(5), "customer": "ค้าง", "seller": "มัททดสอบ", "price": 500000},
                         {"status": "รอผล", "date": _dago(9), "signDate": _dago(2), "customer": "ปกติ", "seller": "บิวทดสอบ"},
                         {"status": "ปล่อย", "date": _dago(9), "releaseDate": ds, "customer": "ปล่อยแล้ว", "seller": "บิวทดสอบ"},
                         {"status": "จอง", "date": _dago(400), "customer": "เก่ามาก", "seller": "บิวทดสอบ"}],
        "monthlySummary": {str(tday.month): {"lead": 3, "booking": 1, "done": 1,
                                             "sellers": {"บิวทดสอบ": {"booking": 1, "done": 1}}}}}
    try:
        CD.rows(force=True)
        s_, d, raw = J(ADM, "/connect/api/leaddb")
        ck("ฐานข้อมูล Lead: อ่านแถวชีต + นับคืนเคส/เบอร์ไม่ซ้ำ", s_ == 200 and d.get("total") == 3
           and (d.get("stats") or {}).get("returned") == 1 and (d.get("stats") or {}).get("phones") == 2, d.get("stats"))
        dd = {r["code"]: r for r in d.get("rows") or []}
        ck("ฐานข้อมูล Lead: เบอร์เดียวกันคนละรูปแบบ = ซ้ำ", (dd.get("NLD10-7002") or {}).get("dup") == 1, dd.get("NLD10-7002"))
        ck("★ ไม่มี LINE user id หลุดในฐานข้อมูล Lead", not leak.search(raw))
        s_, d, _ = J(ADM, "/connect/api/leaddb?q=3401")
        ck("ค้นด้วย 4 ตัวท้ายของเบอร์", s_ == 200 and d.get("total") == 2, d.get("total"))
        s_, d, _ = J(ADM, "/connect/api/leaddb?mode=returned")
        ck("โหมดคืนเคส = เฉพาะคืนเคส", [r["code"] for r in d.get("rows") or []] == ["NLD10-7001"], d.get("rows"))
        s_, d, _ = J(ADM, "/connect/api/leaddb?status=%E0%B8%88%E0%B8%AD%E0%B8%87")
        ck("กรองสถานะลูกค้า (จอง)", [r["code"] for r in d.get("rows") or []] == ["TLD10-7003"], d.get("rows"))
        s_, d, _ = J(ADM, "/connect/api/leaddb?code=NLD10-7001")
        ck("รายละเอียดเลข: เลขอื่นของเบอร์เดียวกัน + เลขไม้ 2", s_ == 200 and d.get("fwd") == "RNLD10-7001/1"
           and [o["code"] for o in d.get("others") or []] == ["NLD10-7002"], (d.get("fwd"), d.get("others")))
        s_, d, _ = J(ADM, "/connect/api/leaddb?code=XLD1-1")
        ck("เลขที่ไม่มีในชีต = 404", s_ == 404, s_)
        for path in ("/connect/api/leaddb", "/connect/api/pipeline", "/connect/api/team"):
            s_, d, _ = J(SEL, path)
            ck("เซลล์เปิด %s ไม่ได้" % path.rsplit("/", 1)[1], s_ == 403, s_)
        s_, d, _ = J(ADM, "/connect/api/leadflow", {"action": "forward", "code": "NLD10-7001", "emp": BIW.id})
        ef = ExtLead.objects.filter(code="RNLD10-7001/1").first()
        ck("ส่งต่อไม้ 2 จากฐานข้อมูล (เลขมีแต่ในชีต) → ลีดภายนอกเลข R…/1 ของบิว",
           ef is not None and ef.seller_id == BIW.id and ef.phone == "0877123401", (s_, d, ef and ef.code))
        s_, d, _ = J(ADM, "/connect/api/leadflow", {"action": "forward", "code": "NLD10-7001", "emp": MAT.id})
        ck("ส่งต่อซ้ำ = ไม่ออกเลขซ้อน + บอกว่าส่งไปแล้ว", ExtLead.objects.filter(code__startswith="RNLD10-7001").count() == 1
           and not d.get("ok") and "RNLD10-7001/1" in (d.get("error") or d.get("message") or ""), d)
        s_, d, _ = J(ADM, "/connect/api/leaddb?code=NLD10-7001")
        ck("รายละเอียดเลขที่ส่งต่อแล้ว: บอกเลขที่ส่งต่อ ไม่เสนอเลขใหม่", not d.get("fwd")
           and (d.get("fwdDone") or {}).get("code") == "RNLD10-7001/1", (d.get("fwd"), d.get("fwdDone")))
        s_, d, _ = J(ADM, "/connect/api/pipeline")
        cols = {c["status"]: c for c in d.get("cols") or []}
        ck("ไปป์ไลน์: จองเกิน 3 วัน = ค้าง · เคสปีเก่ามากไม่ขึ้น", s_ == 200 and cols["จอง"]["count"] == 1
           and cols["จอง"]["stuck"] == 1, cols.get("จอง"))
        ck("ไปป์ไลน์: รอผล 2 วัน ไม่ค้าง · ปล่อยเดือนนี้ 1", cols["รอผล"]["stuck"] == 0 and cols["ปล่อย"]["count"] == 1,
           (cols.get("รอผล"), cols.get("ปล่อย")))
        s_, d, raw = J(ADM, "/connect/api/team")
        n_today = sum(1 for t in LeadTask.objects.filter(
            created_at__gte=timezone.make_aware(datetime.combine(tday, datetime.min.time())))
            if not (t.card or {}).get("demo"))
        ck("แดชบอร์ดทีม: ใบวันนี้ตรงกับฐานข้อมูล (ไม่นับใบทดลอง)", s_ == 200 and d["tiles"]["tasksToday"] == n_today,
           (d.get("tiles"), n_today))
        ck("แดชบอร์ดทีม: จอง/ปล่อยเดือนนี้จากผลสรุป", d["tiles"]["doneMonth"] == 1 and d["tiles"]["bookingMonth"] == 1,
           d.get("tiles"))
        ck("★ ไม่มี LINE user id หลุดในแดชบอร์ดทีม", not leak.search(raw))
        s_, d, raw = J(ADM, "/connect/api/inbox?view=queue")
        ck("กล่องแชทรวม (แอดมิน): มือเซลล์วันนี้ + แถบขั้นตอน", s_ == 200 and isinstance(d.get("rrBoard"), list)
           and d.get("rrBoard") and "today" in (d.get("lfStrip") or {}), (d.get("lfStrip"), (d.get("rrBoard") or [])[:1]))
        ck("มือเซลล์วันนี้: ทุกคนมี id/ชื่อ/ทีม/ได้กี่ใบ", all({"id", "name", "team", "today", "ok"} <= set(x) for x in d["rrBoard"]))
        s_, d, raw = J(SEL, "/api/seller/today")
        mine_n = sum(1 for t in LeadTask.objects.filter(seller_name="มัททดสอบ",
                                                        created_at__gte=timezone.now() - timedelta(days=2))
                     if not (t.card or {}).get("demo"))
        ck("งานวันนี้ของเซลล์: เห็นเฉพาะใบของตัวเอง", s_ == 200 and len(d.get("tasks") or []) == mine_n
           and all(t.get("kind") for t in d["tasks"]), (len(d.get("tasks") or []), mine_n))
        ck("★ ไม่มี LINE user id หลุดในงานวันนี้ของเซลล์", not leak.search(raw))
        s_, d, _ = J(NOB, "/api/seller/today")
        ck("งานวันนี้: ไม่ login = 401", s_ == 401, s_)
        r_ = ADM.get("/connect/?classic=1", secure=True)
        ck("หน้า Connect แบบเดิมยังเปิดได้ (?classic=1)", r_.status_code == 200 and b'class="cn-top"' in r_.content
           and b'lc-rail' not in r_.content, r_.status_code)
        r_ = ADM.get("/connect/?p=db", secure=True)
        ck("หน้า Connect แบบใหม่ + เปิดหน้าฐานข้อมูลตรง", r_.status_code == 200 and b'id="lc-rail"' in r_.content
           and b'"panel": "db"' in r_.content, r_.status_code)
    finally:
        GS.fetch_leads_by_month_tabs, FD.fetch_dashboard_data = _orig_ft, _orig_fd
        CD._ROWS.update(at=0.0, val=None)

    # ═════════════════════════════════════════════════════════════════════
    print("[18] ลบของเก่า")
    old = LeadTask.objects.create(code="NLD1-1", run="1")
    LeadTask.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=LF.KEEP_DAYS + 1))
    LF.cleanup()
    ck("งานเกิน 90 วันถูกลบ", not LeadTask.objects.filter(pk=old.pk).exists())

finally:
    _runner.teardown_databases(_old)

print("\nผ่าน %d / %d" % (len(OK), len(OK) + len(BAD)))
if BAD:
    print("ไม่ผ่าน:\n  - " + "\n  - ".join(BAD))
    sys.exit(1)
