# -*- coding: utf-8 -*-
"""ตรวจตัวเก็บบันทึกห้องโค้ชเซลล์ (27 ก.ย.69)

    python scripts/test_coaching.py

**ปลอมที่ขอบระบบ (requests + การขอ token) ไม่ปลอมฟังก์ชันของเราเอง** — บทเรียน ก.ย.69:
เทสต์เดิมปลอม `fetch_profile` ทั้งฟังก์ชัน ทำให้บั๊กจริงซ่อนอยู่ 3 วันโดยไม่มีเทสต์ไหนจับได้
ที่นี่ `_api`/`_read`/`_append`/`_ensure_header` จึงถูกรันจริงทุกบรรทัด
"""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
os.environ.setdefault("DB_HOST", "")
os.environ.setdefault("DEBUG", "True")

import django

django.setup()

from django.test.runner import DiscoverRunner
from django.test.utils import setup_test_environment

setup_test_environment()
runner = DiscoverRunner(verbosity=0, interactive=False)
old_cfg = runner.setup_databases()

import requests
from django.utils import timezone

from checkout import coaching as CO
from checkout.models import Employee, GroupChat

fail = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        if extra:
            print("        " + str(extra)[:400])
        fail.append(name)


# ────────────────────────── ขอบระบบปลอม: auth + HTTP ──────────────────────────
class _Creds:
    token = "fake-token"

    def refresh(self, _req):
        pass


import dashboard.services.google_sheets as GS

GS._get_credentials = lambda: _Creds()

SHEETS = {}          # {tab: [[...]]}  — ชีตจำลองในหน่วยความจำ
CALLS = {"clear": 0, "put": 0, "append": 0}


class _Resp:
    def __init__(self, data, code=200):
        self.status_code, self._d = code, data
        self.text = json.dumps(data)

    def json(self):
        return self._d


def _tab_of(url):
    import urllib.parse
    raw = urllib.parse.unquote(url)
    if "/values/" not in raw:
        return ""
    return raw.split("/values/")[1].split("!")[0].strip("'")


def _range_of(url):
    import urllib.parse
    raw = urllib.parse.unquote(url)
    part = raw.split("/values/")[1].split("?")[0].split(":append")[0]
    return part.split("!")[1] if "!" in part else ""


def fake_get(url, **kw):
    """เลียนพฤติกรรม Sheets API จริง — **ต้องตัดตามช่วงที่ขอ** ไม่ใช่คืนทั้งตาราง
    ไม่งั้นเทสต์จะไม่จับบั๊ก "อ่านช่วงแคบเกินแล้วกันเขียนซ้ำไม่เห็นแถวเก่า" """
    if "fields=sheets.properties" in url:
        return _Resp({"sheets": [{"properties": {"title": t}} for t in SHEETS]})
    if "/values/" not in url:
        return _Resp({}, 404)
    rows = SHEETS.get(_tab_of(url), [])
    rng = _range_of(url)
    m = __import__("re").match(r"^([A-Z]+)(\d+):([A-Z]+)(\d+)$", rng)
    if not m:
        return _Resp({"values": rows})
    def n(c):                                   # A→0 · L→11
        v = 0
        for ch in c:
            v = v * 26 + (ord(ch) - 64)
        return v - 1
    c1, r1, c2, r2 = n(m.group(1)), int(m.group(2)), n(m.group(3)), int(m.group(4))
    out = []
    for r in rows[r1 - 1:r2]:
        out.append([(r[i] if i < len(r) else "") for i in range(c1, c2 + 1)])
    while out and not any(str(c).strip() for c in out[-1]):
        out.pop()
    return _Resp({"values": out})


def fake_post(url, **kw):
    if ":batchUpdate" in url:                      # addSheet
        title = kw["json"]["requests"][0]["addSheet"]["properties"]["title"]
        SHEETS.setdefault(title, [])
        return _Resp({})
    if ":clear" in url:
        CALLS["clear"] += 1                        # ★ ต้องไม่เกิดขึ้นเลย (append-only)
        return _Resp({})
    if ":append" in url:
        CALLS["append"] += 1
        SHEETS.setdefault(_tab_of(url), []).extend(kw["json"]["values"])
        return _Resp({})
    return _Resp({}, 404)


def fake_put(url, **kw):
    CALLS["put"] += 1                              # ★ เขียนทับ = ผิดกติกา
    return _Resp({})


requests.get, requests.post, requests.put = fake_get, fake_post, fake_put

# ────────────────────────── ข้อมูลตั้งต้น ──────────────────────────
GID = "Ccoach0000000000000000000000000001"
CO.save_cfg(group_id=GID, seniors=["อุ้ม", "เฟิร์ส", "โอ๊ต", "นวล"], enabled=True)

Employee.objects.create(nickname="เฟิร์ส", display_name="First", position="ทีม A")
Employee.objects.create(nickname="อุ้ม", display_name="Oumoxlet", position="ทีม B")
Employee.objects.create(nickname="เก้า", display_name="Kao", position="ทีม A")

from checkout import people

people._CACHE["at"] = 0.0                          # ให้โหลดทะเบียนใหม่จาก DB ที่เพิ่งสร้าง

# ═══════════════════ 1. ดึงรหัสเคส ═══════════════════
print("\n[1] ดึงรหัสเคสจากข้อความ")
ck("จับ NLD-4095", CO.case_code("เคส NLD-4095 ลูกค้าสนใจ") == "NLD-4095")
ck("จับ RBLD-30627/1", CO.case_code("RBLD-30627/1 คืนครับ") == "RBLD-30627/1")
ck("จับ TLD-31620 (5 หลัก)", CO.case_code("อัปเดต TLD-31620") == "TLD-31620")
ck("จับตัวพิมพ์เล็ก → คืนพิมพ์ใหญ่", CO.case_code("nld-4095 ครับ") == "NLD-4095")
ck("เลขเปล่าต้นข้อความ = รหัสเคส", CO.case_code("4120 บอกเค้าเลยครับ") == "4120")
ck("★ เลขกลางข้อความไม่ใช่รหัสเคส (กันจับค่าผ่อน)",
   CO.case_code("ลูกค้าผ่อนไหว 13000 ต่อเดือน") == "",
   CO.case_code("ลูกค้าผ่อนไหว 13000 ต่อเดือน"))
ck("ไม่มีรหัส = ค่าว่าง", CO.case_code("ตามแล้วอัพเดทด้วยครับ") == "")

# ── ★ รูปแบบ "รายงานเคสประจำวัน" ของจริงในห้องโค้ช (วัด 28 ก.ย.69) ──
#    ทุกข้อความขึ้นต้น "รายงานเคสวันที่ …" แล้วรหัสเคสอยู่ต้นบรรทัดถัดไป
#    เวอร์ชันแรกยึด "ต้นข้อความ" → จับไม่ได้เลยสักเคส (6/7 ข้อความมีรหัสแต่ช่องว่าง)
_R1 = "รายงานเคสวันที่ 28 / 9\nA\n\nB\n8029 ยังไม่ทราบโปรไฟล์ลูกค้า\n\n8074 เงินเดือนประมาณ 20,000 อยากได้"
ck("★ รหัสต้นบรรทัดในรายงานประจำวัน (ไม่ใช่ต้นข้อความ)",
   CO.case_code(_R1) == "8029 8074", CO.case_code(_R1))
ck("★ รหัสมีทับ /1 ต้นบรรทัด",
   CO.case_code("รายงานเคสวันที่ 28/9/69\n\n6239/1  ลูกค้าสนใจ camry") == "6239/1",
   CO.case_code("รายงานเคสวันที่ 28/9/69\n\n6239/1  ลูกค้าสนใจ camry"))
ck("★ วันที่ต้นบรรทัดไม่ใช่รหัส (28/9 สั้นกว่า 4 หลัก)",
   CO.case_code("รายงานเคส\n28/9/69 ครับ") == "", CO.case_code("รายงานเคส\n28/9/69 ครับ"))
ck("★ ตัวเลขกลางบรรทัดยังไม่ถูกจับ แม้อยู่บรรทัดหลัง",
   CO.case_code("รายงานเคส\nลูกค้าอายุ 32 ปี ผ่อนไหว 13000") == "",
   CO.case_code("รายงานเคส\nลูกค้าอายุ 32 ปี ผ่อนไหว 13000"))
ck("★ รหัสซ้ำในข้อความเดียว นับครั้งเดียว",
   CO.case_code("8029 ทักแล้ว\n8029 อัปเดตอีก") == "8029",
   CO.case_code("8029 ทักแล้ว\n8029 อัปเดตอีก"))

# ═══════════════════ 2. กันข้อความกลายเป็นสูตร ═══════════════════
print("\n[2] กัน Google Sheets ตีข้อความเป็นสูตร")
ck("ขึ้นต้น = ต้องใส่ ' นำหน้า", CO._esc("=1+1") == "'=1+1")
ck("ขึ้นต้น - ต้องใส่ ' นำหน้า", CO._esc("-ครับ") == "'-ครับ")
ck("ขึ้นต้น @ ต้องใส่ ' นำหน้า", CO._esc("@Jay ช่วยดู") == "'@Jay ช่วยดู")
ck("ข้อความปกติไม่แตะ", CO._esc("ตามด้วยครับ") == "ตามด้วยครับ")

# ═══════════════════ 3. วันที่ของชีตเก่า (ปนกัน 4 แบบ) ═══════════════════
print("\n[3] แปลงวันที่ชีตเก่า")
ck("พ.ศ. 17/04/2569 → 2026-04-17", CO._old_date("17/04/2569") == "2026-04-17",
   CO._old_date("17/04/2569"))
ck("ค.ศ. 10/4/2026 → 2026-04-10", CO._old_date("10/4/2026") == "2026-04-10")
ck("ISO 2026-04-03 คงเดิม", CO._old_date("2026-04-03") == "2026-04-03")
ck("2 หลัก 01/04/26 → 2026-04-01", CO._old_date("01/04/26") == "2026-04-01",
   CO._old_date("01/04/26"))
ck("แปลงไม่ได้ = คืนค่าเดิม ไม่ทิ้ง", CO._old_date("เมื่อวาน") == "เมื่อวาน")
ck("เวลา 8:20 → 08:20", CO._old_time("8:20") == "08:20")
ck("ล้าง '9057 (no code)' → '9057'", CO._clean_old_code("9057 (no code)") == "9057",
   CO._clean_old_code("9057 (no code)"))
ck("ล้างขีดนำหน้า '-4093' → '4093'", CO._clean_old_code("-4093") == "4093")
ck("ป้ายจริงไม่ถูกแตะ", CO._clean_old_code("หน้าร้าน_Jay_0407") == "หน้าร้าน_Jay_0407")
ck("รหัสปกติไม่ถูกแตะ", CO._clean_old_code("RBLD-30627/1") == "RBLD-30627/1")

# ═══════════════════ 4. แยกซีเนียร์/จูเนียร์ ═══════════════════
print("\n[4] แยกบทบาท")
ck("อุ้ม = ซีเนียร์", CO.is_senior("อุ้ม"))
ck("เก้า = ไม่ใช่ซีเนียร์", not CO.is_senior("เก้า"))
ck("เฟิร์น ≠ เฟิร์ส (ชื่อใกล้กันต้องไม่สับ)", not CO.is_senior("เฟิร์น"))

# ═══════════════════ 5. แชทจากบอท → แถวในชีต ═══════════════════
print("\n[5] แปลงแชทที่บอทเก็บไว้")
now = timezone.now()
UID_J = "U1111111111111111111111111111aaaa"
UID_S = "U2222222222222222222222222222bbbb"
GroupChat.objects.create(group_id=GID, message_id="m1", sender_id=UID_J, sender_name="เก้า",
                         msg_type="text", text="NLD-4095 ลูกค้าขอดูรถพรุ่งนี้", sent_at=now)
GroupChat.objects.create(group_id=GID, message_id="m2", sender_id=UID_S, sender_name="เฟิร์ส",
                         msg_type="text", text="ตามแล้วอัพเดทด้วยครับ", sent_at=now)
GroupChat.objects.create(group_id=GID, message_id="m3", sender_id=UID_J, sender_name="",
                         msg_type="image", text="", has_media=True, sent_at=now)
GroupChat.objects.create(group_id="Cother", message_id="m9", sender_id=UID_J,
                         sender_name="เก้า", msg_type="text", text="ห้องอื่น", sent_at=now)

rows, st = CO.rows_from_chat(days=30)
by_ref = {r[11]: r for r in rows}
ck("อ่านเฉพาะห้องโค้ช ไม่เอาห้องอื่น", len(rows) == 3, "%d แถว" % len(rows))
ck("นับซีเนียร์ 1 · จูเนียร์ 2", st["senior"] == 1 and st["junior"] == 2, st)
ck("จับรหัสเคสได้ 1", st["withCode"] == 1, st)
ck("ทีมมาจากทะเบียน", by_ref["line:m2"][5] == "ทีม A", by_ref["line:m2"])
ck("ลำดับนิ่ง (เวลาเท่ากันต้องเรียงตาม id ไม่สลับ)",
   [r[11] for r in rows] == ["line:m1", "line:m2", "line:m3"], [r[11] for r in rows])
ck("รูปที่ไม่มีข้อความ = เขียนกำกับว่าไฟล์อยู่ใน LINE",
   "ไฟล์อยู่ใน LINE" in by_ref["line:m3"][6], by_ref["line:m3"])
ck("ไม่มีชื่อ = '(ไม่ทราบชื่อ)' ไม่เอา user id มาใส่",
   by_ref["line:m3"][3] == "(ไม่ทราบชื่อ)", by_ref["line:m3"])
blob = json.dumps(rows, ensure_ascii=False)
ck("★ ไม่มี LINE user id หลุดลงชีตเลย", UID_J not in blob and UID_S not in blob)

# ═══════════════════ 6. นำเข้าชีตเก่า ═══════════════════
print("\n[6] นำเข้าแท็บเดิม (1 แถวเก่า → หลายแถวใหม่)")
SHEETS[CO.OLD_TAB] = [
    ["วันที่", "เวลา", "รหัสเคส", "userid", "displyname", "เซลล์", "ระดับ", "ข้อความ",
     "คำตอบบอท", "First", "โอ๊ต", "Nual", "อุ้ม", "ประเภทเหตุการณ์", "Auto-Log?",
     "อัปเดตกี่ครั้ง", "อัปเดตล่าสุด", "สถานะ"],
    # แถวยุค AI: มีข้อความจูเนียร์ + ซีเนียร์ 2 คน + คำตอบบอท + ระดับ
    ["17/04/2569", "13:03", "NLD-4095", "Uold111", "Kao", "Kao", "B",
     "ลูกค้าอาชีพค้าขาย ขอเช็คเครดิต", "━━━ เคสครบ ━━━ สรุป...", "ไปกสิกรครับ", "",
     "", "โทรคอนเฟิร์มนัดแล้ว", "อัปเดตเคส", "TRUE", "3", "18/04/2569", "จอง"],
    # แถวยุค log ดิบ: ชื่อที่จับคู่ทะเบียนไม่ได้ + ช่องประเภทถูกยัดข้อความ
    ["10/4/2026", "8:20", "4120", "Uold222", "GoLF⛳️", "", "", "อัพเดทเคสนี้ครับ", "",
     "", "", "", "", "เค้าซื้อสดหรือจัดเคสนี้", "", "", "", "ไม่ตอบ"],
    ["", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],   # แถวว่าง
]
old, ost = CO.rows_from_old_sheet()
ck("ข้ามแถวว่าง (อ่านได้ 2 แถว)", ost["oldRows"] == 2, ost)
ck("แตกแถวที่ 1 เป็น: จูเนียร์+ซีเนียร์2+บอท = 4 แถว จากแถวแรก",
   len([r for r in old if r[11].startswith("old:2:")]) == 4,
   [r[11] for r in old])
ck("ความเห็นซีเนียร์แยกเป็นแถวของตัวเอง (เฟิร์ส)",
   any(r[3] == "เฟิร์ส" and r[4] == CO.SENIOR and "กสิกร" in r[6] for r in old), old)
ck("ความเห็นซีเนียร์ (อุ้ม) ก็แยกแถว",
   any(r[3] == "อุ้ม" and "โทรคอนเฟิร์ม" in r[6] for r in old))
ck("คำตอบบอท AI ระบุที่มาว่าไม่ใช่คนพูด",
   any(r[9] == CO.SRC_OLD_AI and r[4] == CO.BOT for r in old))
ck("ช่องที่ใช้ผิด = เก็บไว้ แต่ไม่เดาว่าใครพูด",
   any(r[9] == CO.SRC_OLD_MISPLACED and r[3] == "(ไม่ระบุ)"
       and r[4] == CO.UNKNOWN and "ซื้อสด" in r[6] for r in old), old)
ck("ค่าประเภทมาตรฐานไม่ถูกนับว่าใช้ผิด", ost["misplaced"] == 1, ost)
ck("จับคู่ชื่อได้ (Kao → เก้า)", any(r[3] == "เก้า" for r in old), [r[3] for r in old])
ck("จับคู่ไม่ได้ = ใช้ชื่อ LINE ที่ล้างอิโมจิแล้ว",
   any(r[3] == "GoLF" for r in old), [r[3] for r in old])
ck("รายงานชื่อที่จับคู่ไม่ได้ให้คนไปแก้ทะเบียน",
   "GoLF⛳️" in ost["unmatchedNames"], ost["unmatchedNames"])
ck("★ ไม่เอา userid ในชีตเก่ามาใส่ (เป็นไอดีของบอทที่ปิดแล้ว)",
   "Uold111" not in json.dumps(old, ensure_ascii=False))
ck("เก็บ 'ระดับ B' ไว้ในหมายเหตุ ไม่สร้างคอลัมน์ว่างทั้งตาราง",
   any("ระดับ B" in r[10] for r in old), [r[10] for r in old])
ck("สถานะเคสติดมาด้วย", any(r[7] == "จอง" for r in old))

# ═══════════════════ 7. เขียนชีต: ต่อท้ายเท่านั้น + รันซ้ำไม่เบิ้ล ═══════════════════
print("\n[7] เขียนชีต")
r1 = CO.sync(days=30, include_old=True)
tab = CO.cfg()["tab"]
ck("สร้างแท็บใหม่ให้เอง", tab in SHEETS)
ck("แถวแรกเป็นหัวตาราง", SHEETS[tab][0] == CO.COLUMNS, SHEETS[tab][:1])
ck("เขียนครบทุกแถว", r1["written"] == r1["new"] and r1["new"] > 0, r1)
ck("★ ไม่เคยสั่ง clear ชีต", CALLS["clear"] == 0)
ck("★ ไม่เคยเขียนทับ (ไม่ใช้ PUT)", CALLS["put"] == 0)

before = len(SHEETS[tab])
r2 = CO.sync(days=30, include_old=True)
ck("รันซ้ำ = ไม่เพิ่มแถว", len(SHEETS[tab]) == before and r2["new"] == 0, r2)
ck("รันซ้ำรายงานว่าข้ามไปกี่แถว", r2["skipped"] == r1["new"], r2)

GroupChat.objects.create(group_id=GID, message_id="m4", sender_id=UID_S, sender_name="อุ้ม",
                         msg_type="text", text="ดีครับ ปิดให้เลย", sent_at=timezone.now())
r3 = CO.sync(days=30)
ck("ข้อความใหม่ถูกเพิ่มต่อท้าย", r3["new"] == 1 and len(SHEETS[tab]) == before + 1, r3)

# ★ แท็บโตเกินช่วงที่เคยอ่าน (5,000 แถว) แล้วต้องยังกันเขียนซ้ำได้
#   ถ้าอ่านช่วงแคบ ตัวกันซ้ำจะมองไม่เห็นแถวเก่า → เขียนซ้ำแบบเงียบๆ
pad = [["", "", "", "", "", "", "", "", "", "", "", "pad:%d" % i] for i in range(6000)]
SHEETS[tab].extend(pad)
grew = len(SHEETS[tab])
r4 = CO.sync(days=30, include_old=True)
ck("★ แท็บโตเกิน 6,000 แถวแล้วยังไม่เขียนซ้ำ",
   r4["new"] == 0 and len(SHEETS[tab]) == grew, r4)
del SHEETS[tab][-6000:]

# ═══════════════════ 8. dry-run + สวิตช์ปิด ═══════════════════
print("\n[8] ทดลอง (dry-run) และสวิตช์")
n_before = len(SHEETS[tab])
rd = CO.sync(days=30, dry_run=True)
ck("dry-run ไม่เขียนชีต", len(SHEETS[tab]) == n_before and "written" not in rd, rd)
ck("dry-run มีตัวอย่างให้ดู", bool(rd.get("preview")))

CO.save_cfg(enabled=False)
ck("ปิดสวิตช์ = maybe_sync ไม่ทำอะไร", CO.maybe_sync() == "")
CO.save_cfg(enabled=True)
out = CO.maybe_sync()
ck("เปิดสวิตช์ = ทำงาน", out.startswith("written="), out)
ck("วันเดียวกันไม่ทำซ้ำ", CO.maybe_sync() == "")

print()
if fail:
    print("ไม่ผ่าน %d ข้อ: %s" % (len(fail), " · ".join(fail)))
else:
    print("ผ่านทั้งหมด")
runner.teardown_databases(old_cfg)
sys.exit(1 if fail else 0)
