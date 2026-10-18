# -*- coding: utf-8 -*-
"""เทสต์ห้องพัก Lead: "QR code" ไม่ใช่ไอดี · จ่ายวนเฉพาะใบร่างหลังเปิดสวิตช์ · เลขรันอ่านสำเนาชีตด้วย (★ 18 ต.ค.69)

    python scripts/test_park_qr.py

  [1] clean_line_id — คำแทนรูป QR / Line@ / ชื่อไทย = ไม่ใช่ไอดี · "Qr code / yingat9015" → yingat9015
  [2] ห้องพัก: ใบร่าง QR ของลูกค้าคนละคน ต้องไม่ถูกรวมเป็น "โพสต์ซ้ำ" และไม่จับคู่กับใบจริงของลูกค้าคนอื่น
  [3] ตั้งค่า: เปิดจ่ายวน = จดเวลาเปิด · ปิด = ล้าง · บันทึกซ้ำตอนเปิดอยู่ = เวลาเดิม
  [4] จ่ายวน: ใบร่างที่โพสต์ก่อนเปิดสวิตช์ไม่จ่ายเอง · หลังเปิด = จ่าย · ค่าตั้งต้นรอ 10 นาที
  [5] เลขรัน: เลขในสำเนาชีตลีด (แท็บเดือนนี้ · นำหน้าไม่เกิน 30) นับด้วย · พิมพ์ผิด/R/เดือนก่อน ไม่นับ

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
from checkout import connect as C  # noqa: E402
from checkout import leadflow as LF  # noqa: E402
from checkout import leadpark as LP  # noqa: E402
from checkout.models import Employee, ExtLead, GroupChat, LineProfile  # noqa: E402
from dashboard.models import LeadSheetRow  # noqa: E402
from dashboard.services import cache_store  # noqa: E402

C.BG_FILL = False
LF.BG_SLOW = False
import checkout.people as _people  # noqa: E402
_people.BG = False

MEMBERS = set()


class _R:
    def __init__(self, code=200, js=None):
        self.status_code, self._js = code, (js or {})
        self.text = json.dumps(self._js)
        self.headers = {}

    def json(self):
        return self._js


SMID = [0]


def _post(url, *a, **k):
    if "/message/push" in url:
        SMID[0] += 1
        return _R(200, {"sentMessages": [{"id": "sm-%d" % SMID[0]}]})
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


def gmsg(gid, gname, text, ago_min, sender="หมิว"):
    MID[0] += 1
    return GroupChat.objects.create(chat_type="group", group_id=gid, group_name=gname, message_id="m-%d" % MID[0],
                                    sender_id="U" + "f" * 32, sender_name=sender, msg_type="text", direction="in",
                                    text=text, sent_at=timezone.now() - timedelta(minutes=ago_min))


def draft(name, ago_min, phone="-", lid="QR code", ch="เพจบ้านเก่า"):
    return gmsg(PARK, "ADMIN เก็บ Lead",
                "Ac Lead No. NLD10-\nAds : -\nชื่อ Account: %s\nชื่อลูกค้า : -\nID LINE : %s\nเบอร์โทร : %s\n"
                "ช่องทาง : %s\nรถ : -\nไลฟ์ : -\nเพิ่มเติม : -" % (name, lid, phone, ch), ago_min)


def slip(code, name, ago_min, phone="-", lid="QR code", ch="เพจบ้านเก่า"):
    return gmsg(ROOM, "ห้องจ่ายเบอร์ บ้านเก่า",
                "Ac Lead No. %s\nAds : -\nชื่อ Account: %s\nชื่อลูกค้า : -\nID LINE : %s\nเบอร์โทร : %s\n"
                "ช่องทาง : %s\nรถ : -\nไลฟ์ : -\nเพิ่มเติม : -\n@มัท" % (code, name, lid, phone, ch), ago_min)


try:
    # ═════════════════════════════════════════════════════════════════════
    print("[1] clean_line_id — คำแทนรูป QR ไม่ใช่ไอดี")
    for v in ("QR code", "Qr code", "qr code", "QR CODE", "QR codde", "QR", "Line@", "line @", "-", "",
              "id line", "คิวอาร์โค้ด", "ส่งรูป", "แนบรูปภาพ", "สมชาย"):
        ck("%r → ไม่ใช่ไอดี" % v, LP.clean_line_id(v) == "", LP.clean_line_id(v))
    ck("'Qr code  /  yingat9015' → yingat9015", LP.clean_line_id("Qr code  /  yingat9015") == "yingat9015",
       LP.clean_line_id("Qr code  /  yingat9015"))
    ck("ไอดีจริง port0955759309 คงเดิม", LP.clean_line_id("port0955759309") == "port0955759309")
    ck("ไอดีจริง a.b_c-9 คงเดิม", LP.clean_line_id("a.b_c-9") == "a.b_c-9")
    s, w = LP.keys({"phones": [], "line_id": "QR code", "account": "Somchai", "channel": "เพจบ้านเก่า"})
    ck("keys: QR code ไม่ได้คีย์แข็ง → ใช้ชื่อ Account+ช่องทาง", not s and w == "a:somchai|เพจบ้านเก่า", (s, w))
    s, _w = LP.keys({"phones": [], "line_id": "qr code / yingat9015", "account": "", "channel": ""})
    ck("keys: ไอดีที่ต่อท้าย QR ยังได้คีย์แข็ง", s == {"l:yingat9015"}, s)

    # ═════════════════════════════════════════════════════════════════════
    print("[2] ห้องพัก: ใบร่าง QR คนละคนไม่ถูกรวม · ไม่จับคู่ใบจริงของคนอื่น")
    gl = {PARK: {"name": "ADMIN เก็บ Lead", "channels": ["push"]},
          ROOM: {"name": "ห้องจ่ายเบอร์ บ้านเก่า", "channels": ["push"]}}
    cache_store.set_kv("line_groups", gl)
    d1 = draft("ลูกค้าเอ", 120)
    d2 = draft("ลูกค้าบี", 100)
    slip("NLD10-9501", "ลูกค้าซี", 90)                  # ใบจริงของลูกค้าคนอื่น เขียน QR code เหมือนกัน
    d3 = draft("ลูกค้าดี", 80)
    slip("NLD10-9502", "ลูกค้าดี", 70)                  # ใบจริงของลูกค้าดี (ชื่อ Account+ช่องทางตรงกัน)
    LP.forget()
    b = LP.board(cache_sec=0)
    wait_ids = {i["id"] for i in b["waiting"]}
    asg = {i["id"]: i for i in b["assigned"]}
    ck("ใบร่าง QR ลูกค้าเอ ยังรอจ่าย", d1.message_id in wait_ids, wait_ids)
    ck("★ ใบร่าง QR ลูกค้าบี ไม่ถูกรวมเป็นโพสต์ซ้ำของลูกค้าเอ", d2.message_id in wait_ids, wait_ids)
    ck("★ ไม่จับคู่กับใบจริงของลูกค้าซี (QR code เหมือนกัน)",
       d1.message_id not in asg and d2.message_id not in asg, list(asg))
    ck("ลูกค้าดี จับคู่ใบจริงด้วยชื่อ Account+ช่องทาง → จ่ายแล้ว NLD10-9502",
       asg.get(d3.message_id, {}).get("code") == "NLD10-9502", asg.get(d3.message_id))

    # ═════════════════════════════════════════════════════════════════════
    print("[3] ตั้งค่าจ่ายวน: จดเวลาเปิด")
    ck("ค่าตั้งต้นรอ 10 นาที", LF.DEFAULTS["auto_after_min"] == 10, LF.DEFAULTS["auto_after_min"])
    LF.save_cfg(dict(LF.cfg(), auto_assign=False, auto_since=""))
    c, errs = LF.clean_cfg({"auto_assign": True, "auto_after_min": 10})
    ck("เปิดสวิตช์ → จดเวลาเปิด", not errs and c["auto_since"], c.get("auto_since"))
    LF.save_cfg(c)
    first_since = LF.cfg()["auto_since"]
    ck("บันทึกแล้วอ่านกลับได้", first_since == c["auto_since"], first_since)
    c2, _e = LF.clean_cfg({"auto_assign": True, "cap_day": 15})
    ck("บันทึกซ้ำตอนเปิดอยู่ → เวลาเปิดเดิม", c2["auto_since"] == first_since, c2["auto_since"])
    c3, _e = LF.clean_cfg({"auto_assign": False})
    ck("ปิดสวิตช์ → ล้างเวลาเปิด", c3["auto_since"] == "", c3["auto_since"])

    # ═════════════════════════════════════════════════════════════════════
    print("[4] จ่ายวน: เฉพาะใบร่างที่โพสต์หลังเปิดสวิตช์")
    team = []
    for i, nick in enumerate(("มัททดสอบ", "เฟิร์สทดสอบ")):
        e = Employee.objects.create(nickname=nick, position="ทีม A", work_start="9:00")
        uid = "U" + ("%032x" % (0xabc100 + i))
        LineProfile.objects.create(user_id=uid, display_name=nick, is_employee=True, employee=e, nickname=nick,
                                   channel="push")
        MEMBERS.add(uid)
        team.append(e)
    GroupChat.objects.filter(group_id=PARK).delete()
    old = draft("ร่างเก่า", 60, phone="0877100001", lid="-")
    since = timezone.now() - timedelta(minutes=30)
    new = draft("ร่างใหม่", 15, phone="0877100002", lid="-")
    fresh = draft("ร่างเพิ่งโพสต์", 2, phone="0877100003", lid="-")
    LF.save_cfg(dict(LF.cfg(), auto_assign=True, auto_after_min=10, auto_since=LF._iso(since)))
    LP.forget()
    got = LF._auto_assign(LF.cfg(), timezone.now())
    LP.forget()
    eo = ExtLead.objects.filter(message_id=old.message_id, code__gt="").first()
    en = ExtLead.objects.filter(message_id=new.message_id, code__gt="").first()
    ef = ExtLead.objects.filter(message_id=fresh.message_id, code__gt="").first()
    ck("★ ใบร่างก่อนเปิดสวิตช์ (รอ 60 นาที) → ไม่จ่ายเอง", eo is None, got)
    ck("ใบร่างหลังเปิดสวิตช์ รอเกิน 10 นาที → จ่ายวน", en is not None and en.seller_id in {e.id for e in team}, got)
    ck("ใบร่างหลังเปิดสวิตช์ แต่รอแค่ 2 นาที → ยังไม่จ่าย", ef is None, got)
    LF.save_cfg(dict(LF.cfg(), auto_since=""))
    LP.forget()
    LF._auto_assign(LF.cfg(), timezone.now())
    LP.forget()
    ck("ไม่มีเวลาเปิด (ตั้งผ่านทางเก่า) → พฤติกรรมเดิม จ่ายทุกใบที่รอเกิน",
       ExtLead.objects.filter(message_id=old.message_id, code__gt="").exists())
    LF.save_cfg(dict(LF.cfg(), auto_assign=False, auto_since=""))

    # ═════════════════════════════════════════════════════════════════════
    print("[5] เลขรัน: นับเลขในสำเนาชีตลีดด้วย")
    GroupChat.objects.filter(group_id=ROOM).delete()
    ExtLead.objects.all().delete()
    slip("NLD10-9522", "x", 30)
    base = C.last_running()
    ck("จากใบในห้องจ่ายเบอร์ = 9522", base == 9522, base)
    today = timezone.localdate()
    first = today.replace(day=1)
    prev = (first - timedelta(days=1)).replace(day=1)
    now = timezone.now()

    def srow(n, code, month):
        LeadSheetRow.objects.create(tab="t%s" % month.isoformat(), row_no=n, tab_month=month, code=code, synced_at=now)

    srow(1, "NLD10-9525", first)                         # แอดมินลงในชีตตรงๆ ไม่ได้โพสต์ใบ
    ck("★ เลขในชีตนำหน้าใบในกลุ่ม → นับ (ถัดไป 9526)", C.last_running() == 9525, C.last_running())
    srow(2, "NLD10-95250", first)                        # พิมพ์เกินหลัก
    ck("พิมพ์เกินหลัก (95250) → ไม่นับ", C.last_running() == 9525, C.last_running())
    srow(3, "TLD10-9665", first)                         # แบบที่เจอจริงในแท็บ ก.ย. (7665 → 9665)
    ck("★ นำหน้าใบในกลุ่มเกิน 30 เลข (พิมพ์หลักแรกผิด) → ไม่นับ", C.last_running() == 9525, C.last_running())
    srow(4, "RNLD10-9530/1", first)
    ck("เลข R ในชีต → ไม่นับ", C.last_running() == 9525, C.last_running())
    srow(5, "NLD9-9540", prev)
    ck("แท็บเดือนก่อน → ไม่นับ", C.last_running() == 9525, C.last_running())
    srow(6, "TLD 10-9530", first)
    ck("แท็บเดือนนี้ + มีช่องว่างในเลข → นับ", C.last_running() == 9530, C.last_running())
    ck("next_code ต่อจากเลขสูงสุด", C.next_code("NLD").endswith("-9531"), C.next_code("NLD"))
    GroupChat.objects.filter(group_id=ROOM).delete()
    ck("ไม่มีใบในกลุ่มเลย → ไม่เดาจากชีต", C._sheet_running(0) == [], C._sheet_running(0))
finally:
    _runner.teardown_databases(_old)

print("\nผ่าน %d · ไม่ผ่าน %d" % (len(OK), len(BAD)))
if BAD:
    print("ไม่ผ่าน:", *BAD, sep="\n  ")
    sys.exit(1)
