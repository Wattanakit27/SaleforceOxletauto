# -*- coding: utf-8 -*-
"""ตรวจการรวมบันทึกห้องโค้ชลงฐานข้อมูล (30 ก.ย.69)

    python scripts/test_coach_db.py

**ทำไมต้องมี** — ตารางนี้เป็น "ที่รวมถาวร" ของข้อมูลที่ต้นทางถูกลบทิ้งเมื่อครบ 90 วัน
ถ้ากันซ้ำพลาด = ข้อมูลเบิ้ลทุกรอบ cron · ถ้าแปลงวันที่พลาด = เรียงตามเวลาไม่ได้
และ **ซ่อมย้อนหลังยาก** เพราะของเก่าในชีตอาจถูกลบไปแล้วตอนที่รู้ตัว
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
os.environ.setdefault("DB_HOST", "")
os.environ.setdefault("DEBUG", "True")

import django

django.setup()

from django.test.utils import setup_test_environment
from django.test.runner import DiscoverRunner

setup_test_environment()
runner = DiscoverRunner(verbosity=0, interactive=False)
old_cfg = runner.setup_databases()

from django.utils import timezone

from checkout import coach_db as CD
from checkout import coaching as C
from checkout.models import CoachLog, GroupChat

OK = [0, 0]


def ck(name, cond, got=""):
    OK[0] += 1
    if cond:
        OK[1] += 1
        print("  ok   %s" % name)
    else:
        print("  FAIL %s   ได้: %r" % (name, got))


def row(**kw):
    """สร้างแถวรูปแบบเดียวกับ coaching._row()"""
    return C._row(**kw)


print("[1] แปลงแถวชีต → ฟิลด์ฐานข้อมูล")
f = CD._to_fields(row(date="2026-04-17", time_="09:05", code="8029", who="เฟิร์ส",
                      role=C.SENIOR, team="ทีม A", text="ลองถามเรื่องอาชีพก่อน",
                      kind="คำแนะนำ", src=C.SRC_OLD, ref="old:12:5"))
ck("ครบทุกช่อง", set(CD.COL) <= set(f), sorted(f))
ck("รหัสอ้างอิงตรง", f["ref"] == "old:12:5", f["ref"])
ck("★ แปลงวันที่+เวลาเป็น datetime ได้", f["sent_at"] is not None, f["sent_at"])
ck("เวลาเป็นโซนไทย (09:05)",
   timezone.localtime(f["sent_at"]).strftime("%H:%M") == "09:05",
   timezone.localtime(f["sent_at"]).strftime("%H:%M") if f["sent_at"] else None)

# ★ _esc() ใส่ ' นำหน้าไว้กันชีตตีเป็นสูตร — ในฐานข้อมูลต้องถอดออก
f2 = CD._to_fields(row(date="2026-05-01", time_="10:00", who="อุ้ม", role=C.SENIOR,
                       text="-ครับ", ref="old:13:5"))
ck("★ ถอด ' ที่ใส่กันชีตตีเป็นสูตรออก", f2["text"] == "-ครับ", f2["text"])

f3 = CD._to_fields(row(date="ไม่ใช่วันที่", time_="", who="x", ref="old:14:5"))
ck("★ วันที่แปลงไม่ได้ = sent_at ว่าง แต่ไม่ทิ้งแถว",
   f3["sent_at"] is None and f3["date_text"] == "ไม่ใช่วันที่", f3)

print("\n[2] เขียนลงตาราง + กันซ้ำ")
rows = [row(date="2026-04-01", time_="13:03", who="บิว", role=C.JUNIOR,
            text="เคส 8029", code="8029", ref="old:1:5"),
        row(date="2026-04-02", time_="09:00", who="เฟิร์ส", role=C.SENIOR,
            text="ลองเสนอ KK", ref="old:2:5")]
r1 = CD.save_rows(rows)
ck("เขียนครั้งแรกได้ 2 แถว", r1["added"] == 2, r1)

r2 = CD.save_rows(rows)
ck("★ รันซ้ำ = ไม่เพิ่ม (กันด้วย ref)", (r2["added"], r2["skipped"]) == (0, 2), r2)
ck("ยอดรวมไม่บวม", CoachLog.objects.count() == 2, CoachLog.objects.count())

# ref ที่ยังไม่มีใน DB แต่ซ้ำกันเองในชุดเดียวกัน (ชีตมีแถวซ้ำได้)
dup = [row(date="2026-04-03", time_="08:00", who="ก", ref="old:99:5"),
       row(date="2026-04-03", time_="08:01", who="ข", ref="old:99:5")]
r3 = CD.save_rows(dup)
ck("★ ref ซ้ำภายในชุดเดียวกันก็กันได้",
   (r3["added"], r3["dupInBatch"]) == (1, 1), r3)

r4 = CD.save_rows([row(date="2026-04-04", time_="08:00", who="ข", text="ไม่มี ref")])
ck("★ แถวไม่มี ref = ข้าม (ไม่งั้นรันซ้ำจะเบิ้ล)",
   (r4["added"], r4["noRef"]) == (0, 1), r4)

print("\n[3] เรียงตามเวลา")
# Meta.ordering = sent_at, id — ดูเฉพาะ 2 แถวที่รู้เวลาแน่ๆ (แถวทดสอบอื่นปนได้)
got = [c.who for c in CoachLog.objects.filter(ref__in=["old:1:5", "old:2:5"])]
ck("เรียงเก่า→ใหม่ตาม sent_at", got == ["บิว", "เฟิร์ส"], got)

print("\n[4] ดึงจากแชทที่บอทเก็บ (sync_chat)")
gid = "Ctest_coach"
C.save_cfg(group_id=gid, seniors=["เฟิร์ส"])
now = timezone.now()
for i, (who, txt) in enumerate([("บิว", "รายงานเคสวันที่ 30/9\n8801 ลูกค้าเงียบ"),
                                ("เฟิร์ส", "ลองโทรตอนเย็น")]):
    GroupChat.objects.create(
        message_id="m%d" % i, group_id=gid, group_name="ห้องโค้ช", chat_type="group",
        sender_name=who, msg_type="text", text=txt,
        sent_at=now - timezone.timedelta(minutes=10 - i))
r5 = CD.sync_chat(days=30)
ck("อ่านครบ 2 ข้อความ", r5["read"] == 2, r5)
ck("เพิ่มเข้าตาราง 2 แถว", r5["added"] == 2, r5)
r6 = CD.sync_chat(days=30)
ck("★ ซิงก์ซ้ำ = ไม่เบิ้ล (cron รันทุกวันได้)", r6["added"] == 0, r6)

by_role = {c.who: c.role
           for c in CoachLog.objects.filter(ref__in=["line:m0", "line:m1"])}
ck("★ แยกบทบาทซีเนียร์/จูเนียร์ถูก",
   by_role == {"บิว": C.JUNIOR, "เฟิร์ส": C.SENIOR}, by_role)
# อ้างด้วย ref ของข้อความนั้นตรงๆ — filter ด้วยชื่อ/ที่มาไม่พอ เพราะชื่อซ้ำกับแถวในข้อ [2]
code = CoachLog.objects.filter(ref="line:m0").first()
ck("★ ดึงรหัสเคสจากต้นบรรทัดในรายงานประจำวัน",
   code and code.case_code == "8801", code.case_code if code else None)

print("\n[5] ★ ห้ามมี LINE user id หลุดเข้าตาราง")
GroupChat.objects.create(message_id="m9", group_id=gid, group_name="ห้องโค้ช",
                         chat_type="group", sender_id="U1234567890abcdef",
                         sender_name="", msg_type="text", text="ไม่มีชื่อผู้ส่ง",
                         sent_at=now)
CD.sync_chat(days=30)
allrows = list(CoachLog.objects.values_list("who", "text", "note", "team"))
ck("ไม่มีไอดีขึ้นต้น U ในช่องไหนเลย",
   not any(str(v).startswith("U1234") for r in allrows for v in r), allrows[-1])
ck("คนไม่มีชื่อ = ติดป้าย (ไม่เอา sender_id มาแทน)",
   CoachLog.objects.filter(who="(ไม่ทราบชื่อ)").exists())

print("\n[6] สรุปผล (stats)")
s = CD.stats()
ck("นับรวมถูก", s["total"] == CoachLog.objects.count(), s["total"])
ck("บอกช่วงวันที่", s["from"] and s["to"], (s["from"], s["to"]))
ck("แยกบทบาทได้", C.SENIOR in s["byRole"], s["byRole"])

print("\n[7] import_sheet เมื่อชีตมีปัญหา (ไม่ยิงเน็ตจริง)")
C._read = lambda tab, rng="": []
ck("อ่านชีตไม่ได้ = บอก error ไม่ใช่เงียบ", "error" in CD.import_sheet())
C._read = lambda tab, rng="": [["ผิดหัวตาราง", "ก", "ข"], ["1", "2", "3"]]
r7 = CD.import_sheet()
ck("★ หัวตารางไม่ตรง = ปฏิเสธ ไม่เขียนมั่ว",
   "error" in r7 and r7["added"] == 0, r7)

print("\n%s (%d/%d)" % ("ผ่านทั้งหมด" if OK[0] == OK[1] else "มีข้อที่ไม่ผ่าน",
                        OK[1], OK[0]))
runner.teardown_databases(old_cfg)
sys.exit(0 if OK[0] == OK[1] else 1)
