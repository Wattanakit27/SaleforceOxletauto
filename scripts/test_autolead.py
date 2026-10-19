# -*- coding: utf-8 -*-
"""เทสต์เก็บลีดอัตโนมัติ → จองเลขรัน → ส่งใบลงกลุ่ม "ADMIN เก็บ Lead" (★ 19 ต.ค.69)

    python scripts/test_autolead.py

  [1] ค่าตั้ง: เปิดโดยปริยาย · รอบแรกเริ่มนับจากตอนนี้ (ไม่ส่งย้อนหลัง)
  [2] ลูกค้าให้เบอร์ → จองเลขต่อจากเลขรันล่าสุด → ใบเลขเต็ม (ไม่แท็กเซลล์) ลงกลุ่ม ADMIN เก็บ Lead · แชทยังอยู่ในห้องพัก
  [3] ไม่ส่ง: ให้เบอร์ก่อนเปิด · ยังไม่ครบเวลารอ · ลูกค้าจำลอง · แอดมินพักใบร่างเองแล้ว · ลีดรับซื้อ · รอบซ้ำ
  [4] เลขรันต่อกัน (ตัวนับรวมเลขที่จองไว้) · ใบของระบบไม่ขึ้นซ้ำในห้องพัก/ไม่ใช้จับคู่
  [5] แอดมินจ่ายเซลล์ → ใช้เลขที่จองไว้ · เลขถูกใช้มือในห้องจ่ายเบอร์ไปแล้ว = ออกเลขใหม่ + บอก
  [6] ส่ง LINE ไม่สำเร็จ = เลขยังจองอยู่ · ส่งใหม่รอบหลัง · ปิดสวิตช์ = ไม่ทำอะไร · ไม่จ่ายเซลล์เองเด็ดขาด
  [7] ใบร่างที่แอดมินพักในกลุ่ม → บอทจองเลข + ตอบใบเลขเต็ม (อ้างใบร่าง) · โพสต์ซ้ำ = บอกเลขเดิม · R/เก่า/ปิดสวิตช์ = ไม่ทำ
      · ลูกค้าเดิม (จองไว้แล้ว/เพิ่งได้เลข) = ซ่อน + บอกเลขเดิม · ข้อความซ้ำ 2 แถว = ทำครั้งเดียว
  [8] จ่ายเซลล์ใบร่างที่จองไว้ = เลขเดิม · แอดมินคัดลอกใบไปแท็กเองแล้ว = ไม่จ่ายซ้ำ (ทั้งใบร่างและแชท)
  [9] เตือนในห้องจ่ายเบอร์: เลขชน · ออกเลขใหม่ให้ลูกค้าที่จองไว้ · ออกเลขใหม่ให้ลูกค้าที่เพิ่งได้เลข · ใช้ถูก/R/ปิด = ไม่เตือน
  [10] ฟอร์มเพิ่มลีดเอง (API): แอดมินเท่านั้น · ตรวจข้อมูล · ลูกค้าเดิม = 409 แล้วยืนยันได้ · ใบร่าง + เลข + ใบลงกลุ่ม · ขึ้นห้องพัก

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
from django.contrib.sessions.backends.signed_cookies import SessionStore  # noqa: E402
from django.test import Client  # noqa: E402
from django.test.runner import DiscoverRunner  # noqa: E402
from django.test.utils import setup_test_environment  # noqa: E402

setup_test_environment()
_runner = DiscoverRunner(verbosity=0, interactive=False)
_old = _runner.setup_databases()
settings.LINE_CHANNEL_ACCESS_TOKEN = "tok-crm"
settings.LINE_PUSH_CHANNEL_ACCESS_TOKEN = "tok-push"
settings.SITE_URL = "https://oxlet.test"
if "testserver" not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]

import requests  # noqa: E402
from django.utils import timezone  # noqa: E402

import dashboard.services.google_sheets as GS  # noqa: E402
from checkout import autochat as AC  # noqa: E402
from checkout import autolead as AL  # noqa: E402
from checkout import connect as C  # noqa: E402
from checkout import leadflow as LF  # noqa: E402
from checkout import leadmatch as LM  # noqa: E402
from checkout import leadpark as LP  # noqa: E402
from checkout.models import ChatLead, ChatOwner, Employee, ExtLead, GroupChat, LineProfile  # noqa: E402
from dashboard.services import cache_store  # noqa: E402

C.BG_FILL = False
LF.BG_SLOW = False
AC.BG = False
AL.BG = False
import checkout.people as _people  # noqa: E402
_people.BG = False
try:
    import checkout.chatmedia as _cm  # noqa: E402
    _cm.BG = False
except Exception:
    pass

MEMBERS = set()
PUSHES = []          # (to, text)
QUOTES = []          # quoteToken ของข้อความที่ส่ง (ตอบแบบอ้างใบร่าง)
FAIL_TO = set()


class _R:
    def __init__(self, code=200, js=None):
        self.status_code, self._js = code, (js or {})
        self.text = json.dumps(self._js)
        self.headers = {}

    def json(self):
        return self._js


def _post(url, *a, **k):
    if "/message/push" in url:
        js = k.get("json") or {}
        to = js.get("to")
        if to in FAIL_TO:
            return _R(500, {"message": "boom"})
        m0 = (js.get("messages") or [{}])[0]
        if m0.get("quoteToken") == "bad-quote":
            return _R(400, {"message": "Invalid quote token"})
        PUSHES.append((to, m0.get("text") or ""))
        QUOTES.append(m0.get("quoteToken") or "")
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


def slip(code, name, ago_min, phone="-", tag="@มัท"):
    return gmsg(ROOM, "ห้องจ่ายเบอร์ บ้านเก่า",
                "Ac Lead No. %s\nAds : -\nชื่อ Account: %s\nชื่อลูกค้า : -\nID LINE : -\nเบอร์โทร : %s\n"
                "ช่องทาง : LINE@\nรถ : -\nไลฟ์ : -\nเพิ่มเติม : -\n%s" % (code, name, phone, tag), ago_min)


def draft(name, ago_min, phone="-", lid="-", channel="LINE@", prefix="NLD10-", quote=""):
    g = gmsg(PARK, "ADMIN เก็บ Lead",
             "Ac Lead No. %s\nAds : -\nชื่อ Account: %s\nชื่อลูกค้า : -\nID LINE : %s\nเบอร์โทร : %s\n"
             "ช่องทาง : %s\nรถ : -\nไลฟ์ : -\nเพิ่มเติม : -" % (prefix, name, lid, phone, channel), ago_min)
    if quote:
        GroupChat.objects.filter(pk=g.pk).update(extra={"quote": quote}, channel="push")
        g.refresh_from_db()
    return g


def ext_res(mid):
    e = ExtLead.objects.filter(message_id=mid).first()
    return ((e.auto or {}).get(AL.KEY) or {}) if e else {}


def room_pushes():
    return [t for to, t in PUSHES if to == ROOM]


def chat(name, phone="", lid="", contact_ago=10, ago_min=None, uid=None):
    UID[0] += 1
    at = timezone.now() - timedelta(minutes=ago_min if ago_min is not None else contact_ago)
    p = LineProfile.objects.create(user_id=uid or ("U%031dz" % UID[0]), display_name=name)
    o = ChatOwner.objects.create(profile=p, awaiting_since=at, last_in_at=at, last_at=at)
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
    return fresh(o)


def fresh(o):
    return ChatOwner.objects.select_related("profile", "fb_profile", "owner", "lead").get(pk=o.pk)


def res_of(o):
    return (ChatLead.objects.get(chat=o).auto or {}).get(AL.KEY) or {}


def park_pushes():
    return [t for to, t in PUSHES if to == PARK]


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
    slip("NLD10-9400", "ตั้งต้น", 3000, phone="0899999999")      # เลขรันล่าสุด = 9400
    mon = timezone.localdate().month

    # ═════════════════════════════════════════════════════════════════════
    print("[1] ค่าตั้ง")
    ck("เปิดโดยปริยาย", AL.cfg()["enabled"] is True, AL.cfg())
    o_old = chat("ลูกค้าก่อนเปิด", phone="0810000001", contact_ago=30)
    r1 = AL.run()
    ck("★ รอบแรก = จดเวลาเริ่ม ไม่ส่งอะไร", "started" in r1 and not PUSHES, (r1, PUSHES))
    ck("ลูกค้าที่ให้เบอร์ก่อนเปิด → ไม่ถูกจองเลข", not res_of(o_old), res_of(o_old))
    # ย้อนเวลาเริ่มเป็น 15 นาทีก่อน เพื่อทดสอบลูกค้าที่ให้เบอร์หลังเปิด
    c = AL.cfg()
    c["since"] = (timezone.now() - timedelta(minutes=15)).isoformat(timespec="seconds")
    AL.save_cfg(c)

    # ═════════════════════════════════════════════════════════════════════
    print("[2] จองเลข + ส่งใบลงกลุ่ม ADMIN เก็บ Lead")
    o1 = chat("คุณเอ ซื้อรถ", phone="0811111111", contact_ago=5)
    r2 = AL.run()
    rv = res_of(o1)
    ck("★ จองเลขต่อจากเลขล่าสุด = 9401", rv.get("num") == 9401, rv)
    ck("เลขเต็มตามตัวหน้าที่แนะนำ + เดือนนี้", re.match(r"^[A-Z]+%d-9401$" % mon, rv.get("code") or ""), rv.get("code"))
    ck("★ ส่งลงกลุ่ม ADMIN เก็บ Lead สำเร็จ", rv.get("ok") is True and len(park_pushes()) == 1, (rv, PUSHES))
    txt = park_pushes()[0] if park_pushes() else ""
    ck("ใบมีเลขเต็ม + เบอร์ลูกค้า", rv.get("code", "?") in txt and "0811111111" in txt, txt)
    ck("★ ใบไม่แท็กเซลล์ (ไม่มี @)", "@" not in txt.replace("LINE@", ""), txt)
    ck("ไม่ได้ส่งอะไรเข้าห้องจ่ายเบอร์", not [t for to, t in PUSHES if to == ROOM], PUSHES)
    l1 = ChatLead.objects.get(chat=o1)
    ck("★ ช่องเลขลีดยังว่าง (ยังไม่จ่ายเซลล์)", not l1.code and not l1.assigned_at, (l1.code, l1.assigned_at))
    ck("★ แชทยังอยู่ในห้องพัก Lead", C.to_code(ChatOwner.objects.filter(pk=o1.pk)).exists())
    ck("ไม่มีเจ้าของ (ไม่ได้โอนให้เซลล์)", fresh(o1).owner_id is None, fresh(o1).owner_id)
    g = GroupChat.objects.filter(message_id__startswith=AL.MSG_PREFIX).first()
    ck("เก็บใบลงคลังแชทกลุ่ม ADMIN เก็บ Lead", g and g.group_id == PARK and (g.extra or {}).get("chat") == o1.id, g)
    ck("รายชื่อแชทมีป้ายเลขที่จองไว้ (autoCode)", C.row_json(fresh(o1)).get("autoCode") == rv.get("code"),
       C.row_json(fresh(o1)).get("autoCode"))
    ch = C.code_help(fresh(o1), ChatLead.objects.get(chat=o1))
    ck("กล่องจ่ายเบอร์: เลขที่จะได้ = เลขที่จองไว้", ch.get("next") == 9401 and (ch.get("reserved") or {}).get("code") == rv.get("code"), ch)

    # ═════════════════════════════════════════════════════════════════════
    print("[3] กรณีที่ไม่ส่ง")
    n0 = len(PUSHES)
    AL._RUN["at"] = 0
    AL.run()
    ck("รอบซ้ำ → ไม่ส่งใบเดิมซ้ำ", len(PUSHES) == n0, PUSHES[n0:])
    o_new = chat("เพิ่งให้เบอร์", phone="0812222222", contact_ago=0)
    AL.run()
    ck("ยังไม่ครบเวลารอ (2 นาที) → ยังไม่ส่ง", not res_of(o_new), res_of(o_new))
    o_sim = chat("ลูกค้าจำลอง", phone="0813333333", contact_ago=5, uid="TEST-x1")
    draft("คุณบี มีใบร่าง", 3, phone="0814444444")
    LM.forget()
    o_dr = chat("คุณบี มีใบร่าง", phone="0814444444", contact_ago=5)
    o_buy = chat("อยากขายรถ", phone="0815555555", contact_ago=5)
    lb = ChatLead.objects.get(chat=o_buy)
    lb.auto = dict(lb.auto, _buylead={"by": "ระบบ", "at": LF._iso(timezone.now())})
    lb.save()
    n0 = len(PUSHES)
    AL.run()
    ck("ลูกค้าจำลอง → ไม่ส่ง", not res_of(o_sim), res_of(o_sim))
    ck("★ แอดมินพักใบร่างเองแล้ว → แชทไม่ได้เลขซ้ำ (จดเหตุผล)", "skip" in res_of(o_dr), res_of(o_dr))
    dr = PUSHES[n0:]
    ck("★ ใบร่างของแอดมินได้เลข 9402 จากบอท (ใบเดียว ไม่ซ้ำกับแชท)",
       len(dr) == 1 and dr[0][0] == PARK and "9402" in dr[0][1], dr)
    ck("ลีดรับซื้อ → ไม่ส่ง", not res_of(o_buy), res_of(o_buy))

    # ═════════════════════════════════════════════════════════════════════
    print("[4] เลขรันต่อกัน · ใบของระบบไม่ขึ้นซ้ำ")
    o2 = chat("คุณซี", phone="0816666666", contact_ago=5)
    AL.run()
    ck("★ ลีดถัดไปได้ 9403 (นับเลขที่จองไว้ ทั้งแชทและใบร่าง)", res_of(o2).get("num") == 9403, res_of(o2))
    ck("ปุ่มจ่ายเบอร์ลีดอื่นจะได้ 9404", C.last_running() + 1 == 9404, C.last_running())
    LP.forget()
    b = LP.board(cache_sec=0)
    ck("★ ใบของระบบไม่ขึ้นเป็นใบร่างซ้ำในห้องพัก", not any("คุณซี" in (i.get("account") or "") or "คุณเอ" in (i.get("account") or "")
                                                        for i in b["waiting"]), [i.get("account") for i in b["waiting"]])
    LM.forget()
    ck("ใบของระบบไม่ใช้จับคู่ (leadmatch)", not LM.find(phones={"0816666666"}), LM.find(phones={"0816666666"}))
    ck("★ ไม่มีใครถูกจ่ายเซลล์อัตโนมัติ", not ChatLead.objects.filter(assigned_at__isnull=False).exists())

    # ═════════════════════════════════════════════════════════════════════
    print("[5] แอดมินจ่ายเซลล์ → ใช้เลขที่จองไว้")
    rv1 = res_of(o1)
    ok, msg = C.assign_lead(fresh(o1), team[0], rv1["base"], rv1["admin"], False, "", by="กวาง")
    l1 = ChatLead.objects.get(chat=o1)
    ck("★ จ่ายแล้วได้เลขที่จองไว้", ok and l1.code == rv1["code"], (ok, msg, l1.code))
    ck("ใบ + แท็กเซลล์เข้าห้องจ่ายเบอร์", any(to == ROOM and rv1["code"] in t for to, t in PUSHES), PUSHES[-2:])
    ck("โอนแชทให้เซลล์", fresh(o1).owner_id == team[0].id, fresh(o1).owner_id)
    # เลขที่จองไว้ถูกแอดมินใช้มือในห้องจ่ายเบอร์ไปแล้ว
    rv2 = res_of(o2)
    slip("NLD%d-%d" % (mon, rv2["num"]), "คนอื่น", 1, phone="0897777777")
    ok, msg = C.assign_lead(fresh(o2), team[1], rv2["base"], rv2["admin"], False, "", by="กวาง")
    l2 = ChatLead.objects.get(chat=o2)
    ck("★ เลขชน → ออกเลขใหม่ ไม่ใช้เลขซ้ำ", ok and l2.code and l2.code != rv2["code"], (ok, l2.code))
    ck("บอกแอดมินว่าเลขที่จองไว้ถูกใช้ไปแล้ว", "ถูกใช้ไปแล้ว" in msg, msg)

    # ═════════════════════════════════════════════════════════════════════
    print("[6] ส่งไม่สำเร็จ · ส่งใหม่ · ปิดสวิตช์")
    FAIL_TO.add(PARK)
    o3 = chat("คุณดี", phone="0818888888", contact_ago=5)
    AL.run()
    r3 = res_of(o3)
    ck("★ ส่งไม่สำเร็จ = เลขยังจองอยู่ + จดเหตุผล", r3.get("num") and r3.get("ok") is False and r3.get("error"), r3)
    FAIL_TO.discard(PARK)
    AL.run()
    ck("ยังไม่ครบ 5 นาที → ยังไม่ส่งใหม่", res_of(o3).get("ok") is False, res_of(o3))
    r3b = dict(res_of(o3), tried=(timezone.now() - timedelta(minutes=6)).isoformat(timespec="seconds"))
    l3 = ChatLead.objects.get(chat=o3)
    l3.auto = dict(l3.auto, **{AL.KEY: r3b})
    l3.save()
    AL.run()
    r3c = res_of(o3)
    ck("★ ครบเวลา → ส่งใหม่ด้วยเลขเดิม", r3c.get("ok") is True and r3c.get("num") == r3.get("num"), r3c)
    AL.set_enabled(False)
    o4 = chat("คุณอี", phone="0819999999", contact_ago=5)
    n0 = len(PUSHES)
    ck("ปิดสวิตช์ → run ไม่ทำอะไร", AL.run().get("off") and not res_of(o4) and len(PUSHES) == n0)
    AL.set_enabled(True)
    ck("เปิดใหม่ = เริ่มนับจากตอนนี้ (ไม่ส่งลูกค้าที่ให้เบอร์ระหว่างปิด)", (AL.run() or {}).get("posted", 0) == 0 and not res_of(o4),
       res_of(o4))
    ck("★ ทั้งเทสต์ไม่มีลีดถูกจ่ายเซลล์เองโดยระบบ (assigned_by = แอดมินเท่านั้น)",
       set(ChatLead.objects.filter(assigned_at__isnull=False).values_list("assigned_by", flat=True)) <= {"กวาง"})


    # ═════════════════════════════════════════════════════════════════════
    print("[7] ใบร่างที่แอดมินพักในกลุ่ม → บอทรันเลข")
    c = AL.cfg()
    c["since"] = (timezone.now() - timedelta(minutes=30)).isoformat(timespec="seconds")
    AL.save_cfg(c)
    LM.forget()
    LP.forget()
    base_n = C.last_running()
    n0 = len(PUSHES)
    d1 = draft("TT คุณจี", 1, phone="0820000001", channel="Live tiktok ช่องขายบอส", prefix="TLD10-", quote="q-1")
    r7 = AL.process_groups()
    rv = ext_res(d1.message_id)
    ck("★ ใบร่างได้เลขถัดไป (จองไว้ที่ลีดภายนอก)", rv.get("num") == base_n + 1 and rv.get("ok") is True, (rv, r7))
    ck("ตัวหน้าตามใบร่าง (TLD) + เดือนนี้", rv.get("code") == "TLD%d-%d" % (mon, base_n + 1), rv.get("code"))
    new = PUSHES[n0:]
    ck("★ บอทตอบใบเลขเต็มในกลุ่ม ADMIN เก็บ Lead (อ้างใบร่าง)",
       len(new) == 1 and new[0][0] == PARK and rv.get("code", "?") in new[0][1] and QUOTES[-1] == "q-1", (new, QUOTES[-1:]))
    ck("ใบที่ตอบ = ใบจ่ายลีด (เบอร์ลูกค้าครบ · ไม่แท็กเซลล์)",
       bool(new) and "0820000001" in new[0][1] and "@" not in new[0][1].replace("LINE@", ""), new)
    ck("ใบที่ตอบเก็บลงคลังแชท", GroupChat.objects.filter(message_id__startswith=AL.MSG_PREFIX + "x").exists())
    b = LP.board(cache_sec=0)
    it = next((i for i in b["waiting"] if i["id"] == d1.message_id), None)
    ck("★ ห้องพัก Lead: ลีดยังรอจ่ายเซลล์ + ป้ายเลขที่จองไว้", it and (it.get("reserved") or {}).get("code") == rv.get("code"), it)
    ck("ใบของบอทไม่ขึ้นเป็นลีดใหม่ในห้องพัก", sum(1 for i in b["waiting"] if "TT คุณจี" in (i.get("account") or "")) == 1,
       [i.get("account") for i in b["waiting"]])
    n0 = len(PUSHES)
    d1b = draft("TT คุณจี", 0, phone="0820000001", channel="Live tiktok ช่องขายบอส", prefix="TLD10-")
    AL.process_groups()
    new = PUSHES[n0:]
    ck("★ โพสต์ใบร่างเดิมซ้ำ = บอกเลขเดิม ไม่ออกเลขใหม่",
       len(new) == 1 and rv.get("code", "?") in new[0][1] and "ลูกค้าเดิม" in new[0][1] and not ext_res(d1b.message_id),
       (new, ext_res(d1b.message_id)))
    ck("เลขรันไม่ขยับ", C.last_running() == base_n + 1, C.last_running())
    n0 = len(PUSHES)
    draft("TT คุณจี", 0, phone="0820000001", channel="Live tiktok ช่องขายบอส", prefix="TLD10-")
    AL.process_groups()
    ck("โพสต์ซ้ำอีกภายใน 30 นาที = เงียบ (ไม่พูดซ้ำในกลุ่ม)", len(PUSHES) == n0, PUSHES[n0:])
    n0 = len(PUSHES)
    dr_r = draft("ไม้สอง", 0, phone="0820000002", prefix="RNLD10-")
    dr_old = draft("ใบเก่ามาก", 200, phone="0820000003")
    AL.process_groups()
    ck("ใบ R (ไม้ 2) → ไม่ออกเลขใหม่", not ext_res(dr_r.message_id) and len(PUSHES) == n0,
       (ext_res(dr_r.message_id), PUSHES[n0:]))
    ck("ใบร่างเก่ากว่า 3 ชม. (ระบบตามหลัง) → ไม่ตอบ", not ext_res(dr_old.message_id))
    o_h = chat("คุณเอช", phone="0821111111", contact_ago=5)
    AL.run()
    rh = res_of(o_h)
    ck("(เตรียม) แชทได้เลขจากระบบ", rh.get("num"), rh)
    n0 = len(PUSHES)
    d_h = draft("คุณเอช TT", 0, phone="0821111111")
    AL.process_groups()
    eh = ExtLead.objects.filter(message_id=d_h.message_id).first()
    new = PUSHES[n0:]
    ck("★ ใบร่างของลูกค้าที่จองเลขทางแชทแล้ว → ไม่ออกเลขใหม่ + ซ่อน",
       eh and eh.no_code and not ext_res(d_h.message_id), eh and (eh.no_code, eh.no_code_by))
    ck("บอกเลขเดิมในกลุ่ม", len(new) == 1 and rh.get("code", "?") in new[0][1], new)
    LP.forget()
    ck("ห้องพัก Lead: ใบร่างนั้นอยู่ \"ซ่อนไว้\"", any(i["id"] == d_h.message_id for i in LP.board(cache_sec=0)["skipped"]))
    slip("NLD%d-9300" % mon, "ลูกค้าเก่าเมื่อวาน", 600, phone="0822222222")
    n0 = len(PUSHES)
    d_s = draft("ลูกค้าเก่าเมื่อวาน", 0, phone="0822222222")
    AL.process_groups()
    new = PUSHES[n0:]
    ck("★ ลูกค้าที่ได้เลขในห้องจ่ายเบอร์ภายใน 2 วัน → ซ่อน + บอกเลขเดิม",
       not ext_res(d_s.message_id) and len(new) == 1 and "9300" in new[0][1], new)
    n0 = len(PUSHES)
    dd = draft("คุณสอง แถว", 0, phone="0823333333")
    MID[0] += 1
    GroupChat.objects.create(chat_type="group", group_id=PARK, group_name="ADMIN เก็บ Lead", message_id="m-%d" % MID[0],
                             sender_id="U" + "f" * 32, sender_name="หมิว", msg_type="text", direction="in",
                             text=dd.text, sent_at=dd.sent_at)
    AL.process_groups()
    ck("ข้อความเดียวกันถูกเก็บ 2 แถว → บอทตอบครั้งเดียว", len(PUSHES) - n0 == 1, PUSHES[n0:])
    n0 = len(PUSHES)
    dq = draft("คุณอ้าง ผิด", 0, phone="0824444444", quote="bad-quote")
    AL.process_groups()
    ck("อ้างใบร่างไม่ได้ (quoteToken เสีย) → ส่งแบบไม่อ้าง ใบต้องถึงกลุ่ม",
       ext_res(dq.message_id).get("ok") is True and len(PUSHES) - n0 == 1, (ext_res(dq.message_id), PUSHES[n0:]))
    FAIL_TO.add(PARK)
    df = draft("คุณส่งพลาด", 0, phone="0824444555")
    AL.process_groups()
    rf = ext_res(df.message_id)
    ck("ส่งลงกลุ่มไม่สำเร็จ = เลขยังจองไว้ + จดเหตุผล", rf.get("num") and rf.get("ok") is False and rf.get("error"), rf)
    FAIL_TO.discard(PARK)
    e_f = ExtLead.objects.get(message_id=df.message_id)
    e_f.auto = dict(e_f.auto, **{AL.KEY: dict(rf, tried=(timezone.now() - timedelta(minutes=6)).isoformat(timespec="seconds"))})
    e_f.save()
    AL.run()
    ck("★ ครบ 5 นาที → ส่งใหม่ด้วยเลขเดิม", ext_res(df.message_id).get("ok") is True
       and ext_res(df.message_id).get("num") == rf.get("num"), ext_res(df.message_id))
    AL.set_switch("drafts", False)
    n0 = len(PUSHES)
    d_off = draft("ปิดสวิตช์", 0, phone="0825555555")
    AL.process_groups()
    ck("ปิดสวิตช์ drafts → ไม่รันเลข", not ext_res(d_off.message_id) and len(PUSHES) == n0)
    AL.set_switch("drafts", True)

    # ═════════════════════════════════════════════════════════════════════
    print("[8] จ่ายเซลล์ลีดที่จองเลขไว้")
    rv = ext_res(d1.message_id)
    ok, msg, e = LP.assign(d1.message_id, team[1], rv["base"], rv["admin"], False, "", by="กวาง")
    ck("★ ใบร่าง: จ่ายเซลล์ = เลขที่จองไว้", ok and e and e.code == rv["code"], (ok, msg, e and e.code))
    ck("ใบ + แท็กเข้าห้องจ่ายเบอร์", any(rv["code"] in t for t in room_pushes()), room_pushes()[-1:])
    d8 = draft("คุณแปด", 0, phone="0826666666")
    AL.process_groups()
    r8 = ext_res(d8.message_id)
    slip(r8["code"], "คุณแปด", 0, phone="0826666666", tag="@เฟิร์ส")
    LP.forget()
    ok, msg, e = LP.assign(d8.message_id, team[0], r8["base"], r8["admin"], False, "", by="กวาง")
    ck("★ ใบร่าง: แอดมินคัดลอกใบไปแท็กเองแล้ว → ไม่จ่ายซ้ำ", not ok and "ได้เลข" in msg, (ok, msg))
    o8 = chat("คุณแปดแชท", phone="0827777777", contact_ago=5)
    AL.run()
    r8c = res_of(o8)
    slip(r8c["code"], "คุณแปดแชท", 0, phone="0827777777", tag="@เฟิร์ส")
    ok, msg = C.assign_lead(fresh(o8), team[0], r8c["base"], r8c["admin"], False, "", by="กวาง")
    ck("★ แชท: แอดมินคัดลอกใบไปแท็กเองแล้ว → ไม่จ่ายซ้ำ", not ok and "ไม่ต้องจ่ายซ้ำ" in msg
       and not ChatLead.objects.get(chat=o8).code, (ok, msg))

    # ═════════════════════════════════════════════════════════════════════
    print("[9] เตือนในห้องจ่ายเบอร์")
    d9 = draft("คุณเก้า", 0, phone="0830000001")
    AL.process_groups()
    r9 = ext_res(d9.message_id)
    n0 = len(PUSHES)
    slip("NLD%d-%d" % (mon, r9["num"]), "คนละคน", 0, phone="0839999999")
    AL.process_groups()
    new = [t for to, t in PUSHES[n0:] if to == ROOM]
    ck("★ (ก) ใช้เลขที่จองไว้ให้ลูกค้าอีกราย → เตือนเลขชน", len(new) == 1 and "ลูกค้าอีกราย" in new[0], new)
    o9 = chat("คุณเก้าแชท", phone="0831111111", contact_ago=5)
    AL.run()
    r9c = res_of(o9)
    n0 = len(PUSHES)
    newnum = C.last_running() + 1
    slip("NLD%d-%d" % (mon, newnum), "คุณเก้าแชท", 0, phone="0831111111")
    AL.process_groups()
    new = [t for to, t in PUSHES[n0:] if to == ROOM]
    ck("★ (ข) ออกเลขใหม่ให้ลูกค้าที่ระบบจองเลขไว้ → เตือนให้ใช้เลขเดิม",
       len(new) == 1 and r9c.get("code", "?") in new[0] and "ใช้เลขเดิม" in new[0], new)
    n0 = len(PUSHES)
    slip("NLD%d-9600" % mon, "คุณสิบ", 10, phone="0832222222")
    slip("NLD%d-9601" % mon, "คุณสิบ", 0, phone="0832222222", tag="@เฟิร์ส")
    AL.process_groups()
    new = [t for to, t in PUSHES[n0:] if to == ROOM]
    ck("★ (ค) ลูกค้าเพิ่งได้เลข แล้วออกเลขใหม่ → เตือนให้ใช้เลขเดิม", len(new) == 1 and "9600" in new[0] and "9601" in new[0], new)
    d9b = draft("คุณถูก", 0, phone="0833333333")
    AL.process_groups()
    r9b = ext_res(d9b.message_id)
    n0 = len(PUSHES)
    slip(r9b["code"], "คุณถูก", 0, phone="0833333333")
    slip("RNLD%d-9600/1" % mon, "คุณสิบ", 0, phone="0832222222")
    MID[0] += 1
    GroupChat.objects.create(chat_type="group", group_id=ROOM, group_name="ห้องจ่ายเบอร์ บ้านเก่า", message_id="m-%d" % MID[0],
                             sender_id="", sender_name="ระบบ", msg_type="text", direction="out",
                             text="Ac Lead No. NLD%d-%d\nชื่อ Account: คุณเก้าแชท\nเบอร์โทร : 0831111111\n@มัท"
                             % (mon, newnum + 5), sent_at=timezone.now())
    AL.process_groups()
    ck("ใช้เลขที่จองไว้ถูกคน / ใบ R / ใบที่ระบบส่งเอง → ไม่เตือน", not [t for to, t in PUSHES[n0:] if to == ROOM],
       PUSHES[n0:])
    AL.set_switch("warn", False)
    n0 = len(PUSHES)
    slip("NLD%d-%d" % (mon, newnum + 9), "คุณเก้าแชท", 0, phone="0831111111")
    AL.process_groups()
    ck("ปิดสวิตช์ warn → ไม่เตือน", len(PUSHES) == n0, PUSHES[n0:])
    AL.set_switch("warn", True)

    # ═════════════════════════════════════════════════════════════════════
    print("[10] ฟอร์มเพิ่มลีดเอง (API)")

    def client(user):
        cl = Client()
        st_ = SessionStore()
        st_["oxlet_user"] = user
        st_.save()
        cl.cookies[settings.SESSION_COOKIE_NAME] = st_.session_key
        return cl

    ADM = client({"user_id": "admin", "nickname": "กวาง", "position": "admin"})
    SEL = client({"user_id": "Ux1", "nickname": "มัท", "position": "seller"})

    def J(cl, body):
        r = cl.post("/connect/api/park_add", json.dumps(body), content_type="application/json", secure=True)
        try:
            return r.status_code, json.loads(r.content.decode("utf-8"))
        except Exception:
            return r.status_code, {}

    st, js = J(SEL, {"phone": "0840000001"})
    ck("เซลล์เพิ่มลีดไม่ได้ (403)", st == 403, (st, js))
    st, js = J(ADM, {"channel": "TIKTOK ช่องขายบอส"})
    ck("ไม่มีเบอร์/ID LINE/ชื่อ Account → 400", st == 400 and js.get("error"), (st, js))
    st, js = J(ADM, {"phone": "12345"})
    ck("เบอร์ผิดรูปแบบ → 400", st == 400 and "เบอร์" in (js.get("error") or ""), (st, js))
    n0 = len(PUSHES)
    base_n = C.last_running()
    st, js = J(ADM, {"channel": "TIKTOK ช่องขายบอส", "live": "Live Sale", "account": "ฟอร์มเว็บหนึ่ง",
                     "phone": "084-000-0001", "car": "Yaris Ativ"})
    ck("★ เพิ่มลีดในเว็บ = จองเลขต่อจากเดิม + ส่งใบลงกลุ่ม",
       st == 200 and js.get("posted") and js.get("code") == "TLD%d-%d" % (mon, base_n + 1), (st, js))
    new = PUSHES[n0:]
    ck("ใบเลขเต็มลงกลุ่ม ADMIN เก็บ Lead ใบเดียว (มีเบอร์ + ช่องทางตาม dropdown)",
       len(new) == 1 and new[0][0] == PARK and js.get("code", "?") in new[0][1] and "0840000001" in new[0][1]
       and "Yaris Ativ" in new[0][1], new)
    LP.forget()
    b = LP.board(cache_sec=0)
    it = next((i for i in b["waiting"] if i["id"] == js.get("mid")), None)
    ck("★ ลีดขึ้นในห้องพัก Lead (เพิ่มในเว็บ · จองเลขแล้ว · โดยใคร)",
       it and it.get("webForm") and (it.get("reserved") or {}).get("code") == js.get("code") and it.get("by") == "กวาง", it)
    st, js2 = J(ADM, {"channel": "LINE@", "phone": "0840000001"})
    ck("★ ลูกค้าเดิม → 409 + เลขเดิม (ยังไม่ออกเลขใหม่)",
       st == 409 and (js2.get("dup") or {}).get("code") == js.get("code"), (st, js2))
    st, js3 = J(ADM, {"phone": "0831111111"})
    ck("ลูกค้าที่จองเลขทางแชทแล้ว → 409", st == 409 and (js3.get("dup") or {}).get("code") == r9c.get("code"), (st, js3))
    st, js4 = J(ADM, {"phone": "0822222222", "account": "ลูกค้าเก่าเมื่อวาน"})
    ck("ลูกค้าที่เพิ่งได้เลขในห้องจ่ายเบอร์ → 409", st == 409 and "9300" in (js4.get("error") or ""), (st, js4))
    n0 = len(PUSHES)
    st, js5 = J(ADM, {"phone": "0822222222", "account": "ลูกค้าเก่าเมื่อวาน", "force": True})
    ck("★ แอดมินยืนยัน (force) → ออกเลขใหม่ + ส่งใบ", st == 200 and js5.get("posted") and js5.get("code")
       and len(PUSHES) - n0 == 1, (st, js5))
    r = ADM.get("/connect/api/inbox?view=tocode", secure=True)
    pk = (json.loads(r.content.decode("utf-8")).get("parked") or {}) if r.status_code == 200 else {}
    ck("หน้าเว็บได้ตัวเลือกฟอร์ม (ช่องทาง/ทีมไลฟ์ตาม dropdown ชีต)",
       (pk.get("form") or {}).get("channels") and (pk.get("form") or {}).get("lives"), (r.status_code, pk.get("form")))
    ck("★ ทั้งหมดนี้ไม่มีลีดภายนอกถูกจ่ายเซลล์เองโดยระบบ",
       set(ExtLead.objects.exclude(code="").values_list("assigned_by", flat=True)) <= {"กวาง"},
       list(ExtLead.objects.exclude(code="").values_list("assigned_by", flat=True)))

finally:
    _runner.teardown_databases(_old)

print("\nผ่าน %d · ไม่ผ่าน %d" % (len(OK), len(BAD)))
sys.exit(1 if BAD else 0)
