# -*- coding: utf-8 -*-
"""เทสต์หน้า "ระบบอัตโนมัติ" ใน CRM — กฎแท็กลูกค้าจากคำในแชท (★ 20 ต.ค.69 · checkout/autotag.py)

    python scripts/test_autotag.py

ฐานข้อมูลทดสอบแยก · เรียก API ผ่าน test client จริง (signed-cookie session + CSRF จริง)
ข้อมูลลูกค้าเป็นค่าสมมติทั้งหมด — ห้ามใส่ข้อมูลลูกค้าจริงในไฟล์นี้
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
if "testserver" not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]

from django.contrib.sessions.backends.signed_cookies import SessionStore  # noqa: E402
from django.test import Client  # noqa: E402
from django.utils import timezone  # noqa: E402

from checkout import autotag as AT  # noqa: E402
from checkout import connect as C  # noqa: E402
from checkout.models import ChatLead, ChatOwner, FbChat, FbProfile, GroupChat, LineProfile  # noqa: E402
from dashboard.services import constants as CONST  # noqa: E402

AT.BG = False
CONST.refresh_from_sheet = lambda *a, **k: True
CONST.ALL_SELLERS[:] = ["มัท"]

PASS = FAIL = 0
LEAK = re.compile(r"U[0-9a-f]{32}")


def ok(cond, label, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓", label)
    else:
        FAIL += 1
        print("  ✗", label, ("· " + str(extra)[:400]) if extra != "" else "")


def client(user=None, csrf=False):
    c = Client(enforce_csrf_checks=csrf)
    if user:
        st = SessionStore()
        st["oxlet_user"] = user
        st.save()
        c.cookies[settings.SESSION_COOKIE_NAME] = st.session_key
    return c


U_ADMIN = {"user_id": "admin", "nickname": "แอดมินทดสอบ", "position": "admin"}
U_SELLER = {"user_id": "U" + "1" * 32, "nickname": "มัท", "position": "seller", "seller_name": "มัท"}
NOW = timezone.now()
_N = {"i": 0}


def line_chat(name, msgs):
    """ลูกค้า LINE + ข้อความ [(dir, text, ชั่วโมงที่แล้ว)]"""
    _N["i"] += 1
    uid = "U%032x" % (0xabc000 + _N["i"])
    p = LineProfile.objects.create(user_id=uid, display_name=name)
    o = ChatOwner.objects.create(profile=p, last_in_at=NOW, last_at=NOW)
    for j, (d, t, hrs) in enumerate(msgs):
        GroupChat.objects.create(chat_type=GroupChat.USER, message_id="m%d-%d" % (_N["i"], j), sender_id=uid,
                                 msg_type="text", text=t, direction=d, sent_at=NOW - timedelta(hours=hrs))
    return o


def fb_chat(name, msgs):
    _N["i"] += 1
    tid = "t_%d" % (900 + _N["i"])
    p = FbProfile.objects.create(user_id="psid%d" % _N["i"], display_name=name, channel="2302089596486628",
                                 thread_id=tid)
    o = ChatOwner.objects.create(fb_profile=p, profile=None, last_in_at=NOW, last_at=NOW)
    for j, (d, t, hrs) in enumerate(msgs):
        FbChat.objects.create(thread_id=tid, message_id="f%d-%d" % (_N["i"], j), msg_type="text", text=t,
                              direction=d, sent_at=NOW - timedelta(hours=hrs), channel="2302089596486628")
    return o


def tags(o):
    ld = ChatLead.objects.filter(chat=o).first()
    return list(ld.tags or []) if ld else None


def post(c, body):
    r = c.post("/crm/api/auto", json.dumps(body), content_type="application/json", secure=True)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {}


# ═════════════════════════════════════════════════════════════════════
print("\n[1] ตรวจกฎก่อนบันทึก")
ok(AT.clean_rule({"tag": "", "words": "ดาวน์"}, [])[1] == "ใส่ชื่อแท็กก่อน", "ไม่มีชื่อแท็ก = ปฏิเสธ")
ok("อย่างน้อย 1 คำ" in AT.clean_rule({"tag": "ถามดาวน์", "words": " , \n"}, [])[1], "ไม่มีคำ = ปฏิเสธ")
ok("สั้นเกินไป" in AT.clean_rule({"tag": "x", "words": "ก"}, [])[1], "คำ 1 ตัวอักษร = ปฏิเสธ (จะจับกลางคำอื่นทั้งแชท)")
ok("มีกฎที่ติดแท็ก" in AT.clean_rule({"tag": "ถามดาวน์", "words": "ดาวน์"}, [{"id": "a1", "tag": "ถามดาวน์"}])[1],
   "แท็กซ้ำกับกฎอื่น = ปฏิเสธ")
r, e = AT.clean_rule({"tag": "  ถาม   ดาวน์ ", "words": "ดาวน์เท่าไหร่, ดาวน์กี่บาท\nดาวน์เท่าไหร่", "scope": "all"}, [])
ok(not e and r["tag"] == "ถาม ดาวน์" and r["words"] == ["ดาวน์เท่าไหร่", "ดาวน์กี่บาท"] and r["scope"] == "all",
   "ตัดช่องว่าง · แยกคำด้วย , และขึ้นบรรทัด · คำซ้ำเหลืออันเดียว", r)
ok("เลือกว่าดูข้อความของใคร" in AT.clean_rule({"tag": "x", "words": "ดาวน์", "scope": "bad"}, [])[1], "scope มั่ว = ปฏิเสธ")

print("\n[2] จับคำ")
R = {"id": "r1", "tag": "ถามดาวน์", "words": ["ดาวน์", "Down"], "not_words": ["สมัครงาน"], "scope": "in", "on": True}
ok(AT.hit(R, "ดาวน์เท่าไหร่ครับ") == "ดาวน์", "เจอคำ = คืนคำที่จับได้")
ok(AT.hit(R, "DOWN payment") == "Down", "อังกฤษไม่สนตัวพิมพ์เล็ก/ใหญ่")
ok(AT.hit(R, "สมัครงานค่ะ เงินดาวน์ไม่มี") == "", "มีคำยกเว้นในข้อความเดียวกัน = ไม่นับ")
ok(AT.hit(R, "สวัสดีครับ") == "", "ไม่มีคำ = ไม่เข้า")
ok(AT.hit({"words": ["แลกรถ"], "not_words": []}, "เเลกรถได้ไหม") == "แลกรถ", "สระพิมพ์ซ้อน (เเ = แ) ก็จับได้")
msgs = [{"dir": "out", "text": "ดาวน์เท่าไหร่ดีคะ"}, {"dir": "in", "text": "สวัสดีครับ"}]
ok(AT.tags_for([R], msgs) == {}, "scope = ข้อความลูกค้า: ข้อความของเราไม่นับ")
ok(AT.tags_for([dict(R, scope="all")], msgs) == {"ถามดาวน์": ("r1", "ดาวน์")}, "scope = ทั้งสองฝั่ง: ข้อความของเรานับด้วย")
ok(AT.tags_for([dict(R, on=False)], [{"dir": "in", "text": "ดาวน์"}]) == {}, "กฎที่ปิด = ไม่ทำงาน")
ok(AT.tags_for([R], [{"dir": "in", "text": "[รูป] ดาวน์"}]) == {}, "ข้อความแทนไฟล์ ([รูป]) ไม่นับ")


class FakeLead:
    def __init__(self, tags=None):
        self.tags = list(tags or [])


print("\n[3] ติด/เอาแท็กออก (ตัวกลาง)")
fl, a = FakeLead(["ลูกค้าVIP"]), {}
ok(AT.apply_lead(fl, a, {"ถามดาวน์": ("r1", "ดาวน์")}, [R]) and fl.tags == ["ลูกค้าVIP", "ถามดาวน์"]
   and a[AT.ATAG_KEY]["ถามดาวน์"]["rule"] == "r1", "ติดแท็กต่อท้าย · แท็กที่คนใส่เดิมอยู่ครบ · จดว่ามาจากกฎไหน", (fl.tags, a))
ok(not AT.apply_lead(fl, a, {"ถามดาวน์": ("r1", "ดาวน์")}, [R]), "ติดซ้ำ = ไม่เปลี่ยนอะไร")
ok(AT.apply_lead(fl, a, {}, [dict(R, tag="สนใจดาวน์")]) and fl.tags == ["ลูกค้าVIP", "สนใจดาวน์"]
   and "สนใจดาวน์" in a[AT.ATAG_KEY], "กฎเปลี่ยนชื่อแท็ก = แท็กของลูกค้าเปลี่ยนตาม (ตำแหน่งเดิม)", (fl.tags, a))
ok(AT.apply_lead(fl, a, {}, [dict(R, tag="สนใจดาวน์", on=False)]) and fl.tags == ["ลูกค้าVIP"] and AT.ATAG_KEY not in a,
   "ปิดกฎ = เอาแท็กของระบบออก · แท็กที่คนใส่ไม่โดน", (fl.tags, a))
fl, a = FakeLead(["ถามดาวน์"]), {}
ok(not AT.apply_lead(fl, a, {"ถามดาวน์": ("r1", "ดาวน์")}, [R]) and AT.ATAG_KEY not in a,
   "คนใส่แท็กเดียวกันไว้เองก่อน = เป็นของคน ระบบไม่ยึด (ลบกฎทีหลังแท็กไม่หาย)")
fl, a = FakeLead([]), {AT.TAGNO_KEY: ["ถามดาวน์"]}
ok(not AT.apply_lead(fl, a, {"ถามดาวน์": ("r1", "ดาวน์")}, [R]) and fl.tags == [], "คนเคยเอาแท็กนี้ออก = ไม่ติดกลับ")
fl, a = FakeLead(["t%d" % i for i in range(AT.TAGS_MAX)]), {}
ok(not AT.apply_lead(fl, a, {"ถามดาวน์": ("r1", "ดาวน์")}, [R]) and len(fl.tags) == AT.TAGS_MAX,
   "แท็กเต็ม %d อันแล้ว = ไม่ติดเพิ่ม" % AT.TAGS_MAX)
fl, a = FakeLead([]), {}
AT.apply_lead(fl, a, {"ถามดาวน์": ("r1", "ดาวน์")}, [R])
ok(not AT.apply_lead(fl, a, {}, [R]) and fl.tags == ["ถามดาวน์"], "ตอนข้อความเข้า (ไม่ prune) ไม่เจอคำ = แท็กเดิมยังอยู่")
ok(AT.apply_lead(fl, a, {}, [R], prune=True) and fl.tags == [], "อ่านย้อนหลังครบแล้วไม่เจอคำอีก (prune) = เอาออก")
fl, a = FakeLead([]), {}
AT.apply_lead(fl, a, {"ถามดาวน์": ("r1", "ดาวน์")}, [R])
AT.human_edit(fl, a, [])
ok(a.get(AT.TAGNO_KEY) == ["ถามดาวน์"] and AT.ATAG_KEY not in a, "คนเอาแท็กของระบบออกในหน้า Connect = จำไว้ไม่ติดกลับ", a)
AT.human_edit(FakeLead([]), a, ["ถามดาวน์"])
ok(AT.TAGNO_KEY not in a, "คนใส่กลับเอง = ล้างที่จำไว้", a)

# ═════════════════════════════════════════════════════════════════════
print("\n[4] สิทธิ์ของ API")
s, d = post(client(), {"action": "save", "rule": {"tag": "x", "words": "ดาวน์"}})
ok(s == 401, "ไม่ login = 401", s)
r = client(U_SELLER).get("/crm/api/auto", secure=True)
ok(r.status_code == 403, "เซลล์ = 403 (หน้านี้สำหรับแอดมิน)", r.status_code)
s, d = post(client(U_SELLER), {"action": "save", "rule": {"tag": "x", "words": "ดาวน์"}})
ok(s == 403 and not AT.rules(cache=False), "เซลล์บันทึกกฎไม่ได้", (s, d))
s, d = post(client(U_ADMIN, csrf=True), {"action": "save", "rule": {"tag": "x", "words": "ดาวน์"}})
ok(s == 403 and not AT.rules(cache=False), "POST ไม่มี CSRF = ถูกปฏิเสธ", s)
r = client(U_ADMIN).get("/crm/", secure=True)
boot = json.loads(re.search(r'id="crm-boot" type="application/json">(.*?)</script>', r.content.decode(), re.S).group(1))
ok(r.status_code == 200 and "roster" not in boot and "ดูของเซลล์" not in r.content.decode(),
   "หน้า CRM ไม่มีตัวเลือก \"ดูของเซลล์\" แล้ว", boot)
ok("ระบบอัตโนมัติ" in r.content.decode() and "pageAuto" in r.content.decode(), "หน้า CRM มีเมนู \"ระบบอัตโนมัติ\"")

# ═════════════════════════════════════════════════════════════════════
print("\n[5] เพิ่มกฎ → ติดแท็กแชทย้อนหลัง (LINE + Facebook)")
A = client(U_ADMIN)
c1 = line_chat("ลูกค้าถามดาวน์", [("in", "สวัสดีครับ", 30), ("in", "ดาวน์เท่าไหร่ครับรุ่นนี้", 29)])
c2 = fb_chat("ลูกค้าเพจ", [("in", "ขอทราบดาวน์กี่บาทคะ", 5)])
c3 = line_chat("ลูกค้าเฉยๆ", [("in", "มีรถกระบะไหม", 3)])
c4 = line_chat("คนสมัครงาน", [("in", "สมัครงานค่ะ ไม่ต้องดาวน์ใช่ไหม", 2)])
c5 = line_chat("เราพูดคำนี้เอง", [("out", "ดาวน์เริ่มต้น 0 บาทค่ะ", 2), ("in", "โอเค", 1)])
c6 = line_chat("ลูกค้าเก่ามาก", [("in", "ดาวน์เท่าไหร่", 24 * (AT.SCAN_DAYS + 5))])
RULE = {"tag": "ถามดาวน์", "words": "ดาวน์เท่าไหร่\nดาวน์กี่บาท\nดาวน์", "not_words": "สมัครงาน", "scope": "in"}
s, d = post(A, {"action": "preview", "rule": RULE})
ok(s == 200 and d["matched"] == 2 and {x["id"] for x in d["samples"]} == {c1.id, c2.id},
   "ทดสอบกฎ: เจอ 2 ราย (LINE + FB) · ไม่นับคนสมัครงาน/ข้อความของเรา/แชทเก่าเกิน %d วัน" % AT.SCAN_DAYS, d)
ok(all(tags(o) is None for o in (c1, c2, c3)), "ทดสอบกฎ = ยังไม่ติดแท็กใคร ไม่สร้างแถวข้อมูลลูกค้า")
ok(not LEAK.search(json.dumps(d, ensure_ascii=False)), "ผลทดสอบไม่มี LINE user id หลุด")
ok(any("<" not in x["text"] and "ดาวน์" in x["text"] for x in d["samples"]), "ตัวอย่างมีข้อความรอบคำที่จับได้")
s, d = post(A, {"action": "save", "rule": RULE})
ok(s == 200 and d["ok"] and d["rule"]["id"], "บันทึกกฎ", d)
RID = d["rule"]["id"]
ok(tags(c1) == ["ถามดาวน์"] and tags(c2) == ["ถามดาวน์"], "★ ติดแท็กให้แชทย้อนหลังทันที (LINE + Facebook)", (tags(c1), tags(c2)))
ok(tags(c3) is None and tags(c4) is None and tags(c5) is None and tags(c6) is None,
   "แชทที่ไม่เข้ากฎ = ไม่แตะ ไม่สร้างแถวเปล่า", (tags(c3), tags(c4), tags(c5), tags(c6)))
r = A.get("/crm/api/auto", secure=True)
g = r.json()
ok(r.status_code == 200 and g["rules"][0]["count"] == 2 and g["last"].get("changed") == 2,
   "GET: กฎ + ติดอยู่ 2 ราย + ผลอ่านย้อนหลังล่าสุด", g.get("rules"))
ok(len(g.get("builtin") or []) == 8 and all("how" in b and "count" in b for b in g["builtin"]),
   "GET: ระบบจับในตัว 8 เรื่อง (ดูอย่างเดียว)")
ok(not LEAK.search(r.content.decode()), "GET ไม่มี LINE user id หลุด")

print("\n[6] ข้อความใหม่เข้า → ติดแท็กเอง")
c7 = line_chat("ลูกค้าใหม่", [("in", "สวัสดี", 1)])
GroupChat.objects.create(chat_type=GroupChat.USER, message_id="m-new", sender_id=c7.profile.user_id, msg_type="text",
                         text="ขอถามหน่อย ดาวน์กี่บาทครับ", direction="in", sent_at=NOW)
C.capture_profile(ChatOwner.objects.get(pk=c7.pk))
ok(tags(c7) == ["ถามดาวน์"], "★ capture_profile (ตอนข้อความเข้า) ติดแท็กให้", tags(c7))

print("\n[7] คนแก้แท็กเอง · แก้กฎ · ปิด · ลบ")
C.save_lead_field(ChatOwner.objects.get(pk=c1.pk), "tags", [], by="เฟิร์น")
s, d = post(A, {"action": "save", "rule": dict(RULE, id=RID, tag="ถามดาวน์")})
ok(tags(c1) == [], "คนเอาแท็กออกในหน้า Connect → อ่านย้อนหลังรอบใหม่ไม่ติดกลับ", tags(c1))
C.save_lead_field(ChatOwner.objects.get(pk=c2.pk), "tags", ["ถามดาวน์", "ลูกค้าดี"], by="เฟิร์น")
s, d = post(A, {"action": "save", "rule": dict(RULE, id=RID, tag="สนใจเรื่องดาวน์")})
ok(s == 200 and tags(c2) == ["สนใจเรื่องดาวน์", "ลูกค้าดี"] and tags(c7) == ["สนใจเรื่องดาวน์"],
   "★ แก้ชื่อแท็กในกฎ → แท็กของลูกค้าเปลี่ยนตาม (แท็กที่คนเพิ่มอยู่ครบ)", (tags(c2), tags(c7)))
s, d = post(A, {"action": "save", "rule": dict(RULE, id=RID, tag="สนใจเรื่องดาวน์", words="ดาวน์กี่บาท")})
ok(tags(c2) == ["สนใจเรื่องดาวน์", "ลูกค้าดี"] and tags(c7) == ["สนใจเรื่องดาวน์"], "แก้คำแล้วยังเข้ากฎ = แท็กอยู่")
s, d = post(A, {"action": "save", "rule": dict(RULE, id=RID, tag="สนใจเรื่องดาวน์", words="ผ่อนเดือนละ")})
ok(tags(c2) == ["ลูกค้าดี"] and tags(c7) == [], "แก้คำแล้วไม่เข้ากฎอีก = แท็กของระบบออก · แท็กที่คนใส่อยู่", (tags(c2), tags(c7)))
s, d = post(A, {"action": "save", "rule": dict(RULE, id=RID, tag="สนใจเรื่องดาวน์")})
ok(tags(c7) == ["สนใจเรื่องดาวน์"], "แก้กลับ = ติดกลับ")
s, d = post(A, {"action": "toggle", "id": RID, "on": False})
ok(s == 200 and tags(c7) == [] and tags(c2) == ["ลูกค้าดี"], "★ ปิดกฎ = แท็กของระบบออก", (tags(c7), tags(c2)))
s, d = post(A, {"action": "toggle", "id": RID, "on": True})
ok(tags(c7) == ["สนใจเรื่องดาวน์"], "เปิดกฎ = ติดกลับ")
s, d = post(A, {"action": "save", "rule": {"tag": "สนใจเรื่องดาวน์", "words": "ดาวน์"}})
ok(s == 400 and "มีกฎที่ติดแท็ก" in d.get("error", ""), "เพิ่มกฎแท็กซ้ำ = 400 บอกเหตุผล", d)
s, d = post(A, {"action": "delete", "id": RID})
ok(s == 200 and tags(c7) == [] and tags(c2) == ["ลูกค้าดี"] and not AT.rules(cache=False),
   "★ ลบกฎ = แท็กของระบบออกทุกราย · แท็กที่คนใส่ไม่โดน", (tags(c7), tags(c2)))
s, d = post(A, {"action": "delete", "id": RID})
ok(s == 400 and "ไม่พบกฎ" in d.get("error", ""), "ลบซ้ำ = 400 ไม่พัง")
s, d = post(A, {"action": "boom"})
ok(s == 400, "คำสั่งมั่ว = 400")

print("\nผ่าน %d · ไม่ผ่าน %d" % (PASS, FAIL))
_runner.teardown_databases(_old)
sys.exit(1 if FAIL else 0)
