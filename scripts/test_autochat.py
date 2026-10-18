# -*- coding: utf-8 -*-
"""เทสต์จ่ายลีดขายจากแชทอัตโนมัติ + ตัวจับคู่ "จ่ายแล้วหรือยัง" (★ 18 ต.ค.69)

    python scripts/test_autochat.py

  [1] leadmatch: ID LINE / ชื่อ → ตัวเทียบ (QR code ไม่ใช่ไอดี · อีโมจิ/Oxlet Auto ถูกตัด)
  [2] autofill: ใบจ่ายลีดที่ตรง ID LINE (ไม่มีเบอร์) → ได้เลข · ชีตลีด "ID LINE : xxx" → ได้เลข · เลขที่คนอื่นถืออยู่ไม่ก๊อป
  [3] ตรงแค่ชื่อ = "_maybe" (ไม่ได้เลข) · ช่องทางขัดกัน (ใบ LINE@ แต่ลูกค้าทักเพจ) = ไม่นับ
  [4] เวลาให้ช่องทางติดต่อ (`_contact_at`) = เวลาข้อความลูกค้า · ไม่ทับ · ลีดที่มีเบอร์อยู่แล้วไม่จด
  [5] ตั้งค่าโหมด off/observe/on — เปลี่ยนโหมด = เริ่มนับใหม่ · ค่าผิดฟ้อง
  [6] ตัดสินทีละแชท: จะจ่าย · ลูกค้าเก่า (เบอร์/ID LINE) · ลูกค้าคนเดียวหลายแชท · มีใบร่าง · มีเจ้าของ · จำลอง/รับซื้อ
  [7] รอบ observe: จดอย่างเดียว ไม่ออกเลข ไม่ส่ง LINE · รอบซ้ำไม่จดซ้ำ · ให้เบอร์ก่อนเปิด/ยังไม่ครบเวลารอ = ไม่ดู
  [8] รอบ on: จ่ายจริงผ่าน assign_lead (เลข + ใบเข้ากลุ่ม) · ไม่เกิน 3 ใบ/รอบ · นอกเวลาทำการ = ไม่จ่าย
  [9] รายงานเทียบกับที่แอดมินทำ · ทดลองย้อนหลังไม่เขียนอะไร
  [10] จ่ายวนใบร่าง: ID LINE เคยได้เลข / ชื่อตรงแชทที่ระบบเพิ่งจ่าย = ข้าม

ฐานข้อมูลทดสอบแยก · ปลอมที่ขอบระบบเท่านั้น (`requests` = LINE/Google)
"""
import io
import json
import os
import re
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
settings.LINE_CHANNEL_ACCESS_TOKEN = "tok-crm"
settings.LINE_PUSH_CHANNEL_ACCESS_TOKEN = "tok-push"
settings.SITE_URL = "https://oxlet.test"

import requests  # noqa: E402
from django.utils import timezone  # noqa: E402

import dashboard.services.google_sheets as GS  # noqa: E402
from checkout import autochat as AC  # noqa: E402
from checkout import connect as C  # noqa: E402
from checkout import leadflow as LF  # noqa: E402
from checkout import leadmatch as LM  # noqa: E402
from checkout import leadpark as LP  # noqa: E402
from checkout.models import ChatLead, ChatOwner, Employee, ExtLead, GroupChat, LeadPhone, LineProfile, FbProfile  # noqa: E402
from dashboard.models import LeadSheetRow  # noqa: E402
from dashboard.services import cache_store  # noqa: E402

C.BG_FILL = False
LF.BG_SLOW = False
AC.BG = False
import checkout.people as _people  # noqa: E402
_people.BG = False
try:
    import checkout.chatmedia as _cm  # noqa: E402
    _cm.BG = False
except Exception:
    pass

MEMBERS = set()
PUSHES = []


class _R:
    def __init__(self, code=200, js=None):
        self.status_code, self._js = code, (js or {})
        self.text = json.dumps(self._js)
        self.headers = {}

    def json(self):
        return self._js


def _post(url, *a, **k):
    if "/message/push" in url:
        PUSHES.append((k.get("json") or {}).get("to"))
        return _R(200, {"sentMessages": [{"id": "sm-%d" % len(PUSHES)}]})
    return _R(200, {})


def _get(url, *a, **k):
    mm = re.search(r"/v2/bot/group/([^/]+)/member/([^/?]+)", url)
    if mm:
        return _R(200, {"displayName": "x"}) if mm.group(2) in MEMBERS else _R(404, {"message": "Not found"})
    return _R(404, {"message": "Not found"})


requests.post, requests.get = _post, _get
GS.load_sheet_config_overrides = lambda *a, **k: None


def _no_sheet(*a, **k):
    raise RuntimeError("ไม่ต่อ Google Sheets ในเทสต์")


GS.fetch_lead_dropdowns = _no_sheet

OK, BAD = [], []


def ck(name, cond, got=""):
    (OK if cond else BAD).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else "   ได้: %r" % (got,)))


PARK = "C" + "3" * 32
ROOM = "C" + "4" * 32
MID = [0]
UID = [0]


def gmsg(gid, gname, text, ago_min, sender="หมิว"):
    MID[0] += 1
    return GroupChat.objects.create(chat_type="group", group_id=gid, group_name=gname, message_id="m-%d" % MID[0],
                                    sender_id="U" + "f" * 32, sender_name=sender, msg_type="text", direction="in",
                                    text=text, sent_at=timezone.now() - timedelta(minutes=ago_min))


def slip(code, name, ago_min, phone="-", lid="-", ch="เพจบ้านเก่า"):
    return gmsg(ROOM, "ห้องจ่ายเบอร์ บ้านเก่า",
                "Ac Lead No. %s\nAds : -\nชื่อ Account: %s\nชื่อลูกค้า : -\nID LINE : %s\nเบอร์โทร : %s\n"
                "ช่องทาง : %s\nรถ : -\nไลฟ์ : -\nเพิ่มเติม : -\n@มัท" % (code, name, lid, phone, ch), ago_min)


def draft(name, ago_min, phone="-", lid="-", ch="เพจบ้านเก่า"):
    return gmsg(PARK, "ADMIN เก็บ Lead",
                "Ac Lead No. NLD10-\nAds : -\nชื่อ Account: %s\nชื่อลูกค้า : -\nID LINE : %s\nเบอร์โทร : %s\n"
                "ช่องทาง : %s\nรถ : -\nไลฟ์ : -\nเพิ่มเติม : -" % (name, lid, phone, ch), ago_min)


def chat(name, phone="", lid="", ago_min=20, contact_ago=None, fb=False, owner=None):
    """ลูกค้าแชทที่คุยในระบบแล้ว (รอคำตอบ) · ให้เบอร์/ID LINE เมื่อ contact_ago นาทีก่อน"""
    UID[0] += 1
    at = timezone.now() - timedelta(minutes=ago_min)
    if fb:
        fp = FbProfile.objects.create(user_id="psid-%d" % UID[0], display_name=name, channel="page1",
                                      thread_id="t_%d" % UID[0])
        o = ChatOwner.objects.create(fb_profile=fp, awaiting_since=at, last_in_at=at, last_at=at, owner=owner)
    else:
        p = LineProfile.objects.create(user_id="U%031dz" % UID[0], display_name=name)
        o = ChatOwner.objects.create(profile=p, awaiting_since=at, last_in_at=at, last_at=at, owner=owner)
    lead = C.lead_of(o)
    lead.phone, lead.line_id = phone, lid
    auto = {}
    if phone:
        auto["phone"] = "แชท"
    if lid:
        auto["line_id"] = "แชท"
    if contact_ago is not None and (phone or lid):
        auto["_contact_at"] = LF._iso(timezone.now() - timedelta(minutes=contact_ago))
    lead.auto = auto
    lead.save()
    return ChatOwner.objects.select_related("profile", "fb_profile", "owner", "lead").get(pk=o.pk)


def fresh(o):
    return ChatOwner.objects.select_related("profile", "fb_profile", "owner", "lead").get(pk=o.pk)


try:
    cache_store.set_kv("line_groups", {PARK: {"name": "ADMIN เก็บ Lead", "channels": ["push"]},
                                       ROOM: {"name": "ห้องจ่ายเบอร์ บ้านเก่า", "channels": ["push"]}})
    team = []
    for i, nick in enumerate(("มัท", "เฟิร์ส")):
        e = Employee.objects.create(nickname=nick, position="ทีม A", work_start="9:00")
        uid = "U" + ("%032x" % (0xabc100 + i))
        LineProfile.objects.create(user_id=uid, display_name=nick, is_employee=True, employee=e, nickname=nick,
                                   channel="push")
        MEMBERS.add(uid)
        team.append(e)
    slip("NLD10-9400", "ตั้งต้น", 3000, phone="0899999999")       # ใบตั้งต้นให้เลขรันเริ่มที่ 9401

    # ═════════════════════════════════════════════════════════════════════
    print("[1] leadmatch — ตัวเทียบ ID LINE / ชื่อ")
    for v, want in (("@Abc.Def99", "abcdef99"), ("abc_def-99", "abcdef99"), ("QR code", ""), ("Line@", ""),
                    ("line.me/ti/p/~myid99", "myid99"), ("0812345678", ""), ("ab", ""), ("Qr code / yingat9015", "yingat9015")):
        ck("lid_core(%r) = %r" % (v, want), LM.lid_core(v) == want, LM.lid_core(v))
    ck("ชื่อ: อีโมจิ/ช่องว่างถูกตัด", LM.name_key("Somchai 😊 Na") == "somchaina", LM.name_key("Somchai 😊 Na"))
    ck("ชื่อ: ตัด Oxlet Auto ท้ายชื่อ", LM.name_key("Mod🐜 Oxlet Auto") == "mod", LM.name_key("Mod🐜 Oxlet Auto"))
    ck("ชื่อสั้นเกิน = ไม่ใช้", LM.name_key("Ab") == "", LM.name_key("Ab"))
    ck("สระ ำ ไม่แตก (NFC)", LM.name_key("ดำ ดำ") == "ดำดำ", LM.name_key("ดำ ดำ"))

    # ═════════════════════════════════════════════════════════════════════
    print("[2] autofill — จับคู่ด้วย ID LINE (ใบในกลุ่ม · ชีตลีด)")
    slip("NLD10-9410", "ลูกค้าไอดี", 10, lid="abc.def99")
    LM.forget()
    o1 = chat("ลูกค้าไอดี เพจ", lid="@ABC.def99", contact_ago=15)
    l1 = C.autofill(o1, slip_min=1)
    ck("★ ใบที่ตรง ID LINE (ไม่มีเบอร์) → ได้เลข NLD10-9410", l1.code == "NLD10-9410", l1.code)
    ck("ที่มา = ใบจ่ายลีด + จดว่าจ่ายให้ใคร", (l1.auto or {}).get("code") == "ใบจ่ายลีด"
       and ((l1.auto or {}).get("_slip") or {}).get("tag") == "มัท", l1.auto)
    today = timezone.localdate()
    LeadSheetRow.objects.create(tab="ตุลาคม 69", row_no=10, tab_month=today.replace(day=1), code="NLD10-9420",
                                phone="ID LINE : zxcv.1234", seller="เฟิร์ส", received_date=today, synced_at=timezone.now())
    o2 = chat("ลูกค้าชีต", lid="ZXCV1234", contact_ago=15)
    l2 = C.autofill(o2, slip_min=1)
    ck("★ ชีตลีด 'ID LINE : zxcv.1234' → ได้เลข NLD10-9420 (จ่ายนอกระบบ)", l2.code == "NLD10-9420", l2.code)
    ck("ที่มา = ชีตลีด", (l2.auto or {}).get("code") == "ชีตลีด", (l2.auto or {}).get("code"))
    LeadSheetRow.objects.create(tab="ตุลาคม 69", row_no=11, tab_month=today.replace(day=1), code="NLD10-9421",
                                phone="ID LINE : held.9999", seller="มัท", received_date=today, synced_at=timezone.now())
    oh = chat("ถือเลขอยู่", lid="held9999")
    lh = C.lead_of(oh)
    lh.code = "NLD10-9421"
    lh.save()
    o3 = chat("ลูกค้าไอดีเดียวกัน", lid="held.9999", contact_ago=15)
    l3 = C.autofill(o3, slip_min=1)
    ck("เลขในชีตที่แชทอื่นถืออยู่แล้ว → ไม่ก๊อปมาซ้ำ", not l3.code, l3.code)

    # ═════════════════════════════════════════════════════════════════════
    print("[3] ตรงแค่ชื่อ = อาจจ่ายแล้ว (ไม่ตัดสินเอง)")
    slip("NLD10-9430", "คุณชื่อซ้ำ", 30, phone="0811111111", ch="LINE@")
    LM.forget()
    o4 = chat("คุณ ชื่อซ้ำ", phone="0822222222", contact_ago=15)
    l4 = C.autofill(o4, slip_min=1)
    mb = (l4.auto or {}).get(C.MAYBE_KEY) or {}
    ck("★ ชื่อตรง เบอร์ไม่ตรง → ไม่ได้เลข แต่ติด _maybe NLD10-9430", not l4.code and mb.get("code") == "NLD10-9430", (l4.code, mb))
    o5 = chat("คุณชื่อซ้ำ", phone="0833333333", contact_ago=15, fb=True)
    l5 = C.autofill(o5, slip_min=1)
    ck("ใบเขียน LINE@ แต่ลูกค้าทักเพจ = ไม่ใช่คนเดียวกัน (ไม่ติด _maybe)",
       C.MAYBE_KEY not in (l5.auto or {}), (l5.auto or {}).get(C.MAYBE_KEY))

    # ═════════════════════════════════════════════════════════════════════
    print("[4] เวลาที่ลูกค้าให้ช่องทางติดต่อ")
    o6 = chat("ลูกค้าใหม่", ago_min=7)
    ok6 = C.capture_contact(o6, extra=[{"dir": "in", "text": "เบอร์ผม 0844444444 ครับ"}])
    a6 = C.lead_of(o6).auto or {}
    ck("capture_contact ได้เบอร์", ok6 and C.lead_of(o6).phone == "0844444444", C.lead_of(o6).phone)
    ck("★ จดเวลา = ข้อความล่าสุดของลูกค้า (ไม่ใช่ตอนนี้)", a6.get("_contact_at") == LF._iso(o6.last_in_at), a6.get("_contact_at"))
    first_at = a6.get("_contact_at")
    o6b = fresh(o6)
    o6b.last_in_at = timezone.now()
    o6b.save()
    C.capture_contact(o6b, extra=[{"dir": "in", "text": "ไลน์ไอดี: newid777"}])
    ck("ให้ ID LINE เพิ่มทีหลัง → เวลาเดิม (ไม่ทับ)", (C.lead_of(o6b).auto or {}).get("_contact_at") == first_at,
       (C.lead_of(o6b).auto or {}).get("_contact_at"))
    o7 = chat("มีเบอร์อยู่แล้ว", phone="0855555555")
    C.capture_contact(o7, extra=[{"dir": "in", "text": "ไลน์ไอดี: haveph99"}])
    ck("ลีดที่มีเบอร์ก่อนแล้ว (ก่อนมีระบบนี้) → ไม่จด", "_contact_at" not in (C.lead_of(o7).auto or {}), C.lead_of(o7).auto)
    o8 = chat("ส่ง QR", ago_min=4)
    C.capture_qr(o8, "line.me/ti/p/AbCdEf", ref="l99")
    ck("รูป QR → จดเวลาด้วย", (C.lead_of(o8).auto or {}).get("_contact_at") == LF._iso(o8.last_in_at),
       (C.lead_of(o8).auto or {}).get("_contact_at"))

    # ═════════════════════════════════════════════════════════════════════
    print("[5] ตั้งค่าโหมด")
    ck("ค่าตั้งต้น = ปิด", LF.cfg()["auto_chat"] == "off", LF.cfg()["auto_chat"])
    _c, errs = LF.clean_cfg({"auto_chat": "yes"})
    ck("ค่าผิด → ฟ้อง", bool(errs), errs)
    c, errs = LF.clean_cfg({"auto_chat": "observe"})
    ck("observe → จดเวลาเริ่ม", not errs and c["auto_chat"] == "observe" and c["auto_chat_since"], c)
    LF.save_cfg(c)
    s1 = LF.cfg()["auto_chat_since"]
    c2, _e = LF.clean_cfg({"auto_chat": "observe", "cap_day": 20})
    ck("บันทึกซ้ำโหมดเดิม → เวลาเดิม", c2["auto_chat_since"] == s1, c2["auto_chat_since"])
    c3, _e = LF.clean_cfg({"auto_chat": "off"})
    ck("ปิด → ล้างเวลา", c3["auto_chat"] == "off" and c3["auto_chat_since"] == "", c3)
    raw = dict(LF.cfg())
    raw["auto_chat"] = "weird"
    cache_store.set_kv(LF.CFG_KEY, raw)
    ck("ค่าเพี้ยนในฐานข้อมูล → อ่านเป็นปิด", LF.cfg()["auto_chat"] == "off", LF.cfg()["auto_chat"])

    # ═════════════════════════════════════════════════════════════════════
    print("[6] ตัดสินทีละแชท")
    c = dict(LF.cfg(), auto_chat="observe", auto_after_min=10)
    o9 = chat("ลูกค้าสด", phone="0866000001", contact_ago=15)
    r9 = AC.decide(o9, c)
    ck("★ ลูกค้าใหม่ไม่ตรงอะไรเลย → จะจ่าย (คิวจ่ายวน)", r9["d"] == "would" and r9["emp"] in team, r9)
    ck("มีตัวหน้าเลขลีด", bool(r9.get("pfx")), r9.get("pfx"))
    LeadPhone.objects.create(phone="0866000002", code="NLD8-7000", seller="เฟิร์ส", seen_on=today - timedelta(days=60))
    r10 = AC.decide(chat("ลูกค้าเก่าเบอร์", phone="0866000002", contact_ago=15), c)
    ck("★ เบอร์เคยเป็นลีด (สมุดเบอร์) → ข้าม ลูกค้าเก่า", r10["d"] == "skip" and "ลูกค้าเก่า" in r10["why"], r10)
    oo = chat("เคยได้เลขไอดี", lid="old.id55")
    lo = C.lead_of(oo)
    lo.code = "NLD7-6000"
    lo.save()
    ChatLead.objects.filter(pk=lo.pk).update(updated_at=timezone.now() - timedelta(days=90))
    r11 = AC.decide(chat("ไอดีเก่า", lid="old_id55", contact_ago=15), c)
    ck("★ ID LINE เคยได้เลข (90 วันก่อน) → ข้าม ลูกค้าเก่า", r11["d"] == "skip" and "ID LINE" in r11["why"], r11)
    first = chat("ทัก LINE ก่อน", phone="0866000003", contact_ago=30)
    second = chat("ทักเพจทีหลัง", phone="086-600-0003", contact_ago=15, fb=True)
    r12 = AC.decide(second, c)
    ck("★ ลูกค้าคนเดียวทัก 2 ช่องทาง → แชทหลังข้าม", r12["d"] == "skip" and "#%d" % first.id in r12["why"], r12)
    ck("แชทแรกยังจ่ายได้", AC.decide(first, c)["d"] == "would", AC.decide(first, c))
    draft("มีใบร่าง", 25, phone="0866000004")
    LM.forget()
    r13 = AC.decide(chat("ลูกค้ามีใบร่าง", phone="0866000004", contact_ago=15), c)
    ck("★ แอดมินโพสต์ใบร่างแล้ว → ข้าม (จ่ายทางห้องพัก)", r13["d"] == "skip" and "ใบร่าง" in r13["why"], r13)
    r14 = AC.decide(chat("มีเจ้าของ", phone="0866000005", contact_ago=15, owner=team[1]), c)
    ck("มีเซลล์ดูแลอยู่ → จ่ายให้คนเดิม", r14["d"] == "would" and r14["emp"] == team[1] and r14["why"] == "ดูแลแชทนี้อยู่", r14)
    ob = chat("อยากขายรถ", phone="0866000006", contact_ago=15)
    lb = C.lead_of(ob)
    lb.auto = dict(lb.auto, _buylead={"by": "ระบบ", "at": LF._iso(timezone.now())})
    lb.save()
    ck("ลีดรับซื้อ → ข้าม", AC.decide(fresh(ob), c)["d"] == "skip", AC.decide(fresh(ob), c))
    ck("ลีดรับซื้อไม่อยู่ในรายการให้ดู", ob.id not in [x.id for x in AC.candidates(dict(c, auto_chat_since=LF._iso(timezone.now() - timedelta(hours=1))))], "")
    ck("ตรงแค่ชื่อ (_maybe) → ข้าม", AC.decide(fresh(o4), c)["d"] == "skip" and "ชื่อตรง" in AC.decide(fresh(o4), c)["why"], AC.decide(fresh(o4), c))
    ck("ได้เลขจากใบ ID LINE แล้ว → แอดมินจ่ายแล้ว", AC.decide(fresh(o1), c)["d"] == "human", AC.decide(fresh(o1), c))

    # ═════════════════════════════════════════════════════════════════════
    print("[7] รอบ observe — จดอย่างเดียว")
    ChatOwner.objects.all().update(awaiting_since=None)   # ล้างแชทข้างบน (ไม่ให้ปนรอบนี้) — ยังคุยในระบบผ่าน owner/log ไม่ได้
    ChatLead.objects.update(phone="", line_id="")
    since = timezone.now() - timedelta(minutes=60)
    LF.save_cfg(dict(LF.cfg(), auto_chat="observe", auto_chat_since=LF._iso(since), auto_after_min=10))
    cache_store.set_kv(AC.KV_STATE, {})
    cache_store.set_kv(AC.KV_LOG, [])
    before = chat("ให้เบอร์ก่อนเปิด", phone="0877000001", contact_ago=90, ago_min=5)
    early = chat("เพิ่งให้เบอร์", phone="0877000002", contact_ago=3, ago_min=3)
    a = chat("รอบนี้ เอ", phone="0877000003", contact_ago=20, ago_min=20)
    b = chat("รอบนี้ บี", lid="robeebee", contact_ago=25, ago_min=25)
    ids = [x.id for x in AC.candidates(LF.cfg())]
    ck("ให้เบอร์ก่อนเปิดสวิตช์ → ไม่ดู", before.id not in ids, ids)
    ck("ให้เบอร์ยังไม่ครบ 10 นาที → ยังไม่ดู", early.id not in ids, ids)
    ck("ให้เบอร์หลังเปิด + เกิน 10 นาที → ดู", a.id in ids and b.id in ids, ids)
    np = len(PUSHES)
    r = AC.run()
    ck("★ observe: ตัดสิน 'จะจ่าย' 2 ราย", r.get("would") == 2, r)
    ck("★ observe: ไม่ออกเลขให้ใคร", not C.lead_of(fresh(a)).code and not C.lead_of(fresh(b)).code,
       (C.lead_of(fresh(a)).code, C.lead_of(fresh(b)).code))
    ck("★ observe: ไม่ส่ง LINE", len(PUSHES) == np, PUSHES[np:])
    log = cache_store.get_kv(AC.KV_LOG)["data"]
    ck("จดลง log 2 แถว (มีเซลล์ที่จะได้)", len(log) == 2 and all(x.get("to") for x in log), log)
    ck("log ไม่มีเบอร์/ชื่อลูกค้า", not any("0877" in json.dumps(x, ensure_ascii=False) or "รอบนี้" in json.dumps(x, ensure_ascii=False)
                                         for x in log), log)
    r2 = AC.run()
    ck("รอบถัดไปภายใน 10 นาที → ไม่ตรวจซ้ำ ไม่จดซ้ำ", r2.get("checked") == 0 and len(cache_store.get_kv(AC.KV_LOG)["data"]) == 2, r2)
    tos = {x["chat"]: x["to"] for x in log}
    ck("2 รายกระจายคนละเซลล์ (คนได้ใบน้อยสุดก่อน)", len(set(tos.values())) == 2, tos)

    # ═════════════════════════════════════════════════════════════════════
    print("[9a] รายงาน — เทียบกับที่แอดมินทำ")
    la = C.lead_of(fresh(a))
    la.code = "NLD10-9450"
    la.auto = dict(la.auto, code="ใบจ่ายลีด", _slip={"seller": tos[a.id], "at": LF._iso(timezone.now())})
    la.save()
    rep = AC.report(7)
    sm = rep["summary"]
    ck("แอดมินจ่ายรายเอให้เซลล์เดียวกับที่ระบบเลือก → paid_same 1", sm["would_paid_same"] == 1, sm)
    ck("รายบียังไม่มีใครจ่าย → open 1", sm["would_open"] == 1, sm)

    # ═════════════════════════════════════════════════════════════════════
    print("[8] รอบ on — จ่ายจริง")
    LF.save_cfg(dict(LF.cfg(), auto_chat="on", auto_chat_since=LF._iso(since)))
    cache_store.set_kv(AC.KV_STATE, {})
    AC._in_hours = lambda now: False
    r3 = AC.run()
    ck("นอกเวลาทำการ → ไม่จ่าย", r3.get("assigned") == 0 and not C.lead_of(fresh(b)).code, r3)
    import importlib
    cache_store.set_kv(AC.KV_STATE, {})
    AC._in_hours = lambda now: True
    extra = [chat("on %d" % i, phone="08780000%02d" % i, contact_ago=15 + i, ago_min=15 + i) for i in range(4)]
    np = len(PUSHES)
    r4 = AC.run()
    ck("★ on: จ่ายไม่เกิน 3 ใบต่อรอบ", r4.get("assigned") == 3, r4)
    got = [fresh(x) for x in [b] + extra if C.lead_of(fresh(x)).code]
    ck("★ on: ได้เลขจริง + จดว่าระบบจ่าย", len(got) == 3 and all(C.lead_of(x).assigned_by.startswith("จ่ายวนอัตโนมัติ") for x in got),
       [(C.lead_of(x).code, C.lead_of(x).assigned_by) for x in got])
    ck("★ on: ส่งใบเข้าห้องจ่ายเบอร์", PUSHES[np:].count(ROOM) == 3, PUSHES[np:])
    codes = [C.lead_of(x).code for x in got]
    ck("เลขไม่ซ้ำกัน", len(set(codes)) == 3, codes)
    ck("แชทที่ได้เลขแล้ว ไม่อยู่ในรายการรอบหน้า", not ({x.id for x in got} & {x.id for x in AC.candidates(LF.cfg())}), "")
    r5 = AC.run()
    ck("รอบหน้าจ่ายที่เหลือ", r5.get("assigned") == 2, r5)
    ck("ครบทุกแชท (5 ใบ) เลขไม่ซ้ำ", len({C.lead_of(fresh(x)).code for x in [b] + extra}) == 5,
       [C.lead_of(fresh(x)).code for x in [b] + extra])

    # ═════════════════════════════════════════════════════════════════════
    print("[9b] ทดลองย้อนหลัง — ไม่เขียนอะไร")
    LF.save_cfg(dict(LF.cfg(), auto_chat="off", auto_chat_since=""))
    tb = chat("ย้อนหลัง", phone="0879000001", contact_ago=60, ago_min=60)
    slip("NLD10-9460", "ย้อนหลังจ่ายแล้ว", 30, lid="bt.paid1")
    LM.forget()
    tp = chat("ย้อนหลังจ่ายแล้ว", lid="bt_paid1", contact_ago=60, ago_min=60)
    n_codes = ChatLead.objects.exclude(code="").count()
    bt = AC.backtest(7)
    ck("ทดลองย้อนหลัง: เจอแชทที่แอดมินจ่ายแล้ว (ID LINE)", any(x["chat"] == tp.id and x["d"] == "human" for x in bt["rows"]), bt["rows"])
    ck("ทดลองย้อนหลัง: แชทที่ยังไม่จ่าย = จะจ่าย", any(x["chat"] == tb.id and x["d"] == "would" for x in bt["rows"]), bt["rows"])
    ck("★ ทดลองย้อนหลังไม่เขียนเลขลงฐานข้อมูล", ChatLead.objects.exclude(code="").count() == n_codes
       and not C.lead_of(fresh(tp)).code, (n_codes, ChatLead.objects.exclude(code="").count()))

    # ═════════════════════════════════════════════════════════════════════
    print("[10] จ่ายวนใบร่าง — กันซ้ำด้วย ID LINE / ชื่อ")
    GroupChat.objects.filter(group_id=PARK).delete()
    LF.save_cfg(dict(LF.cfg(), auto_assign=True, auto_after_min=10, auto_since=LF._iso(timezone.now() - timedelta(hours=1))))
    od = chat("ไอดีเคยได้เลข", lid="dup_id77")
    ld = C.lead_of(od)
    ld.code = "NLD9-7777"
    ld.save()
    dl = draft("ไอดีซ้ำ", 20, lid="Dup.Id77")
    dn = draft("on 0", 20, ch="LINE@")
    dk = draft("ร่างปกติ", 20, phone="0870000999")
    LP.forget()
    LM.forget()
    LF._auto_assign(LF.cfg(), timezone.now())
    last = cache_store.get_kv("leadflow_auto_last")["data"]
    sk = {x["id"]: x["why"] for x in last.get("skipped") or []}
    ck("★ ใบร่างที่ ID LINE เคยได้เลข → ข้าม", "ID LINE" in sk.get(dl.message_id, ""), sk)
    ck("★ ใบร่างที่ชื่อตรงแชทที่ระบบเพิ่งจ่าย → ข้าม", "แชท #" in sk.get(dn.message_id, ""), sk)
    ck("ใบร่างปกติ → จ่าย", ExtLead.objects.filter(message_id=dk.message_id).exclude(code="").exists(), last)

    # ═════════════════════════════════════════════════════════════════════
    print("[11] หน้าตั้งค่า (API) ส่งสถานะ")
    from checkout.connect_views import _autochat_status
    st = _autochat_status()
    ck("สถานะมีโหมด + การตัดสินล่าสุด", st.get("mode") in AC.MODES and isinstance(st.get("recent"), list), st)
finally:
    _runner.teardown_databases(_old)

print("\nผ่าน %d · ไม่ผ่าน %d" % (len(OK), len(BAD)))
if BAD:
    print("ไม่ผ่าน:", *BAD, sep="\n  ")
    sys.exit(1)
