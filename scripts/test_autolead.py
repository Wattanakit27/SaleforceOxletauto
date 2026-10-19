# -*- coding: utf-8 -*-
"""เทสต์เก็บลีดอัตโนมัติ → จองเลขรัน → ส่งใบลงกลุ่ม "ADMIN เก็บ Lead" (★ 19 ต.ค.69)

    python scripts/test_autolead.py

  [1] ค่าตั้ง: เปิดโดยปริยาย · รอบแรกเริ่มนับจากตอนนี้ (ไม่ส่งย้อนหลัง)
  [2] ลูกค้าให้เบอร์ → จองเลขต่อจากเลขรันล่าสุด → ใบเลขเต็ม (ไม่แท็กเซลล์) ลงกลุ่ม ADMIN เก็บ Lead · แชทยังอยู่ในห้องพัก
  [3] ไม่ส่ง: ให้เบอร์ก่อนเปิด · ยังไม่ครบเวลารอ · ลูกค้าจำลอง · แอดมินพักใบร่างเองแล้ว · ลีดรับซื้อ · รอบซ้ำ
  [4] เลขรันต่อกัน (ตัวนับรวมเลขที่จองไว้) · ใบของระบบไม่ขึ้นซ้ำในห้องพัก/ไม่ใช้จับคู่
  [5] แอดมินจ่ายเซลล์ → ใช้เลขที่จองไว้ · เลขถูกใช้มือในห้องจ่ายเบอร์ไปแล้ว = ออกเลขใหม่ + บอก
  [6] ส่ง LINE ไม่สำเร็จ = เลขยังจองอยู่ · ส่งใหม่รอบหลัง · ปิดสวิตช์ = ไม่ทำอะไร · ไม่จ่ายเซลล์เองเด็ดขาด

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
from checkout import autolead as AL  # noqa: E402
from checkout import connect as C  # noqa: E402
from checkout import leadflow as LF  # noqa: E402
from checkout import leadmatch as LM  # noqa: E402
from checkout import leadpark as LP  # noqa: E402
from checkout.models import ChatLead, ChatOwner, Employee, GroupChat, LineProfile  # noqa: E402
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
        PUSHES.append((to, ((js.get("messages") or [{}])[0]).get("text") or ""))
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


def draft(name, ago_min, phone="-"):
    return gmsg(PARK, "ADMIN เก็บ Lead",
                "Ac Lead No. NLD10-\nAds : -\nชื่อ Account: %s\nชื่อลูกค้า : -\nID LINE : -\nเบอร์โทร : %s\n"
                "ช่องทาง : LINE@\nรถ : -\nไลฟ์ : -\nเพิ่มเติม : -" % (name, phone), ago_min)


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
    ck("★ แอดมินพักใบร่างเองแล้ว → ไม่ส่งซ้ำ (จดเหตุผล)", "skip" in res_of(o_dr) and len(PUSHES) == n0, (res_of(o_dr), PUSHES[n0:]))
    ck("ลีดรับซื้อ → ไม่ส่ง", not res_of(o_buy), res_of(o_buy))

    # ═════════════════════════════════════════════════════════════════════
    print("[4] เลขรันต่อกัน · ใบของระบบไม่ขึ้นซ้ำ")
    o2 = chat("คุณซี", phone="0816666666", contact_ago=5)
    AL.run()
    ck("★ ลีดถัดไปได้ 9402 (นับเลขที่จองไว้)", res_of(o2).get("num") == 9402, res_of(o2))
    ck("ปุ่มจ่ายเบอร์ลีดอื่นจะได้ 9403", C.last_running() + 1 == 9403, C.last_running())
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

finally:
    _runner.teardown_databases(_old)

print("\nผ่าน %d · ไม่ผ่าน %d" % (len(OK), len(BAD)))
sys.exit(1 if BAD else 0)
