# -*- coding: utf-8 -*-
"""เทสต์แบบใบจ่ายลีดใหม่ (20 ต.ค.69 · เจ้าของสั่ง "เปลี่ยนรูปแบบเป็นแบบนี้")

    python scripts/test_slip_format.py

ค่าทั้งหมดเป็นค่าสมมติ — ห้ามใส่ข้อมูลลูกค้าจริงในไฟล์นี้
ไม่แตะฐานข้อมูล (ฟังก์ชันล้วน + ของปลอมเล็กๆ)
"""
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")      # console ไทยของ Windows (cp874)
except Exception:
    pass
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
os.environ["DB_HOST"] = ""
import django  # noqa: E402

django.setup()

from checkout import autolead as AL  # noqa: E402
from checkout import leadpark as LP  # noqa: E402
from checkout import leadsheet as LS  # noqa: E402
from checkout import slippost as SP  # noqa: E402
from checkout.leadgroup import parse_fields, parse_leadsheet  # noqa: E402

PASS = FAIL = 0


def ck(name, cond, got=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print("  FAIL", name, "  ได้:", repr(got)[:600])


F = {"code": "LD10-9401", "ads": "", "account": "somchai_k", "name": "", "line_id": "Ab2468", "line_name": "",
     "phone": "", "channel": "Line@", "car": "", "live": "", "more": "",
     "occupation": "พนักงานร้านกาแฟ", "income": "15000-18000", "job_tenure": "2 ปี 3 เดือน",
     "pay_history": "ผ่อนบ้านตั้งแต่ปีที่แล้ว มือถือ 6 เดือน"}

print("[1] หน้าตาใบตรงแบบของเจ้าของทีละบรรทัด")
body = SP.body(F)
want = [
    "Ac Lead No. LD10-9401",
    "Ads  :  ",
    "ชื่อ Account :    somchai_k",
    "ชื่อลูกค้า :     ",
    "ID LINE :    Ab2468",
    "ชื่อไลน์ :  ",
    "เบอร์โทร :    ",
    "ช่องทาง  :   Line@",
    "รถ :     ",
    "",
    "เพิ่มเติม  :  ",
    "อาชีพ :    พนักงานร้านกาแฟ",
    "รายได้ :    15,000-18,000",
    "อายุงาน :   2 ปี 3 เดือน",
    "ประวัติการผ่อน :  ผ่อนบ้านตั้งแต่ปีที่แล้ว มือถือ 6 เดือน",
    "",
    "เวลาจ่าย ",
    "ส่งหลักฐาน ",
    "ติดต่อได้เลยนะครับ",
]
got = body.split("\n")
ck("จำนวนบรรทัดเท่าแบบ", len(got) == len(want), got)
for i, (g, w) in enumerate(zip(got, want)):
    ck("บรรทัด %d = %r" % (i + 1, w), g == w, g)
ck("ไม่มีบรรทัดไลฟ์เมื่อไม่มีทีมไลฟ์", "ไลฟ์" not in body, body)
ck("ช่องว่าง = เว้นว่าง ไม่ใส่ \"-\"", ":  -" not in body and ": -" not in body, body)

print("[2] ไลฟ์ · ค่า \"-\" · ค่าหลายบรรทัด")
b2 = SP.body(dict(F, live="Live Sale", ads="-", more="ดาวน์ 3 หมื่น\nอยากออกเดือนหน้า"))
lines = b2.split("\n")
ck("มีทีมไลฟ์ = บรรทัดไลฟ์ต่อจากรถ", lines[9] == "ไลฟ์ :  Live Sale" and lines[8].startswith("รถ :"), lines[:11])
ck("\"-\" = ว่าง", "Ads  :  " in lines and "Ads  :  -" not in lines, lines[:3])
ck("เพิ่มเติมหลายบรรทัด = บรรทัดเดียว", "เพิ่มเติม  :  ดาวน์ 3 หมื่น · อยากออกเดือนหน้า" in lines, lines)

print("[3] รายได้ใส่จุลภาค")
for raw, want_ in [("16000-20000", "16,000-20,000"), ("25000", "25,000"), ("25,000", "25,000"), ("2 หมื่น", "2 หมื่น"),
                   ("15k", "15k"), ("1500000", "1,500,000"), ("", "")]:
    ck("money(%r) = %r" % (raw, want_), SP.money(raw) == want_, SP.money(raw))

print("[4] บรรทัดแท็กท้ายใบ")
ck("ยังไม่จ่าย = \"@\" เปล่า เว้นบรรทัดก่อน", SP.with_tag(body).endswith("ติดต่อได้เลยนะครับ\n\n@"), SP.with_tag(body)[-30:])
ck("จ่ายแล้ว = @ชื่อเล่น", SP.with_tag(body, "มัท").endswith("\n\n@มัท"))
m1 = SP.messages(body, "มัท", "", False)[0]
ck("ส่งแบบพิมพ์ชื่อ = ใบ + @มัท", m1["type"] == "text" and m1["text"] == body + "\n\n@มัท", m1["text"][-20:])
m2 = SP.messages(body, "มัท", "U" + "1" * 32, True)[0]
ck("ส่งแบบแท็กจริง = textV2 ต่อท้าย {seller}", m2["type"] == "textV2" and m2["text"].endswith("ติดต่อได้เลยนะครับ\n\n{seller}"),
   m2["text"][-30:])

print("[5] ตัวอ่านใบอ่านใบใหม่กลับได้")
d = parse_leadsheet(SP.with_tag(body, "มัท")) or {}
ck("เลขลีด", d.get("lead_code") == "LD10-9401", d)
for k in ("account", "line_id", "channel", "occupation", "job_tenure", "pay_history"):
    ck("ช่อง %s" % k, d.get(k) == F[k], (k, d.get(k)))
ck("รายได้ (มีจุลภาค)", d.get("income") == "15,000-18,000", d.get("income"))
ck("แท็ก = มัท", d.get("assigned") == "มัท", d.get("assigned"))
ck("ช่องว่างอ่านเป็นว่าง", not d.get("ads") and not d.get("phone") and not d.get("more"), d)
ck("ใบยังไม่จ่าย = ไม่มีแท็ก", parse_fields(SP.with_tag(body))["assigned"] == "")
draft = SP.with_tag(SP.body(dict(F, code="LD10-")))
ck("ใบไม่มีเลขรัน = ไม่ใช่ใบจ่ายจริง", parse_leadsheet(draft) is None)
dd = LP.parse_draft(draft) or {}
ck("ใบไม่มีเลขรัน = ใบร่างของห้องพัก Lead", dd.get("prefix") == "LD10-" and dd.get("occupation") == F["occupation"], dd)

print("[6] PROFILE ในชีตจ่ายเบอร์ = ตั้งแต่เพิ่มเติมถึงก่อน \"เวลาจ่าย\"")
pr = LS._profile(SP.with_tag(body, "มัท"))
ck("มีอาชีพ/รายได้", "พนักงานร้านกาแฟ" in pr and "15,000-18,000" in pr, pr)
ck("ไม่มีเวลาจ่าย/ส่งหลักฐาน/ติดต่อได้เลย", not any(w in pr for w in ("เวลาจ่าย", "ส่งหลักฐาน", "ติดต่อได้เลย")), pr)

print("[7] เพิ่มเติม ไม่ซ้ำกับ 4 บรรทัดข้อมูลลูกค้า")


def msg(t):
    return {"dir": "in", "text": t}


form = msg("อาชีพ : พนักงานร้านกาแฟ\nรายได้ : 15000-18000\nอายุงาน : 2ปี 3เดือน\nประวัติการผ่อน : ผ่อนบ้าน")
allk = ("occupation", "income", "job_tenure", "pay_history")
ck("แบบฟอร์มบอกแค่ 4 เรื่อง + ใบมีครบ = เพิ่มเติมว่าง", AL.customer_notes(None, [form], have=allk) == "",
   AL.customer_notes(None, [form], have=allk))
form2 = msg("อาชีพ : พนักงานร้านกาแฟ\nรายได้ : 15000\nจังหวัด : ชลบุรี\nแพลนออกรถ : เดือนหน้า")
n2 = AL.customer_notes(None, [form2], have=("occupation", "income"))
ck("แบบฟอร์มมีป้ายอื่น = เพิ่มเติมเก็บเฉพาะป้ายนั้น", "ชลบุรี" in n2 and "เดือนหน้า" in n2 and "กาแฟ" not in n2, n2)
plain = msg("ทำงานโรงงานค่ะ เงินเดือน 18000")
ck("ข้อความบอกแค่อาชีพ/รายได้ + ใบมีแล้ว = ไม่ซ้ำ", AL.customer_notes(None, [plain], have=("occupation", "income")) == "")
mixed = msg("เงินเดือน 18000 มีดาวน์ 30000 ค่ะ")
ck("ข้อความมีดาวน์ด้วย = เก็บทั้งข้อความ", "ดาวน์" in AL.customer_notes(None, [mixed], have=("income",)))
ck("ใบยังไม่มีข้อมูลลูกค้า = เก็บแบบเดิม (ข้อมูลไม่หาย)", "โรงงาน" in AL.customer_notes(None, [plain], have=()))
ck("ข้อความที่เราพิมพ์ไม่นับ", AL.customer_notes(None, [{"dir": "out", "text": "ดาวน์เท่าไหร่คะ"}]) == "")


print("[8] ลีดจากใบร่าง: ข้อมูลลูกค้าจากใบร่างไปถึงใบที่ส่งต่อ")


class FakeExt:
    message_id = ""
    auto = {"_prof": {"occupation": "ค้าขาย", "income": "20000"}}


p = LP._profile_of(FakeExt())
ck("อ่านจาก auto._prof", p == {"occupation": "ค้าขาย", "income": "20000", "job_tenure": "", "pay_history": ""}, p)
ck("_profile_from เก็บเฉพาะช่องที่มีค่า", LP._profile_from({"occupation": "ค้าขาย", "income": "", "x": 1}) == {"occupation": "ค้าขาย"})

print("[9] ใบอัปเดต: ใบที่ส่งก่อนมีช่องข้อมูลลูกค้าไม่เด้งพร้อมกันหลัง deploy")
old = {"car": "", "name": "", "phone": "0812345670", "line_id": "", "more": "", "ads": "", "live": ""}
ck("ใบเก่า + ตอนนี้มีอาชีพ = ไม่นับเป็นค่าใหม่", AL._changes(old, dict(old, occupation="ค้าขาย")) == [])
new = AL._snap(dict(old))
ck("ใบใหม่ + ลูกค้าบอกรายได้ทีหลัง = ใบอัปเดต \"รายได้\"", AL._changes(new, dict(old, income="20000")) == ["รายได้"],
   AL._changes(new, dict(old, income="20000")))

print("ผ่าน %d · ไม่ผ่าน %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
