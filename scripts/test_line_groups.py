# -*- coding: utf-8 -*-
"""ตรวจทะเบียนกลุ่ม LINE (28 ก.ย.69)

    python scripts/test_line_groups.py

ชื่อกลุ่มที่ใช้ทดสอบเป็น **ชื่อจริงบนเซิร์ฟเวอร์** (วัด 28/09) ไม่ใช่ชื่อสมมติ —
การจัดประเภทที่ผ่านแต่กับชื่อที่เราคิดเอง แปลว่ายังไม่ได้ทดสอบอะไรเลย
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

from django.test.runner import DiscoverRunner
from django.test.utils import setup_test_environment

setup_test_environment()
runner = DiscoverRunner(verbosity=0, interactive=False)
old_cfg = runner.setup_databases()

from django.core.management import call_command
from django.utils import timezone

from checkout.management.commands.line_groups_sync import guess_kind
from checkout.models import GroupChat, LineGroup

fail = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        if extra:
            print("        " + str(extra)[:300])
        fail.append(name)


# ── ชื่อกลุ่มจริงบน prod → ประเภทที่ควรได้ ──
REAL = [
    ("Sale Coaching Room Oxlet auto", "coaching"),
    ("ห้องจ่ายเบอร์ บ้านเก่า", "lead"),
    ("ห้องจ่ายเบอร์ REJECT", "lead"),
    ("เคสHOT (พี่ต๊าด) ซื้อ-ขายรถช่องทางออนไลน์", "tradein"),
    ("เคสHOT (พี่หมี) ซื้อ-ขายรถช่องทางออนไลน์", "tradein"),
    ("จัดซื้อ [รายงานรถ]", "purchase"),
    ("จัดไฟแนนซ์", "finance"),
    ("จองรถ", "booking"),
    ("รับ-ส่ง ระหว่างสาขา", "transfer"),
    ("รับสมัครพนักงาน", "hr"),
    ("Branding and Content Maketing Team", "content"),
    ("ทีมAdmin อ๊อกเล็ตธ์ออโต้", "admin"),
    ("อ๊อกเล็ตธ์ ออโต้", "other"),          # กลุ่มรวมบริษัท — ไม่ควรถูกยัดหมวดมั่ว
]

print("\n[1] จัดประเภทจากชื่อกลุ่มจริงบน prod")
bad = []
for name, want in REAL:
    got = guess_kind(name)
    if got != want:
        bad.append("%s → %s (ควรเป็น %s)" % (name, got, want))
ck("จัดถูกครบ %d กลุ่ม" % len(REAL), not bad, " · ".join(bad))

print("\n[2] เคสที่ชื่อใกล้กัน ต้องไม่สับ")
ck("'รับสมัครพนักงาน' ไม่กลายเป็น transfer", guess_kind("รับสมัครพนักงาน") == "hr")
ck("'จัดซื้อ' ไม่กลายเป็น finance", guess_kind("จัดซื้อ [รายงานรถ]") == "purchase")
ck("ชื่อว่าง = other ไม่ใช่พัง", guess_kind("") == "other")
ck("ชื่อที่ไม่เข้าหมวดไหน = other", guess_kind("กลุ่มเพื่อนสนิท") == "other")

print("\n[3] ย้ายจากทะเบียน KV + จากแชท เข้าเป็นตาราง")
from dashboard.services import cache_store

cache_store.set_kv("line_groups", {
    "C001": {"name": "Sale Coaching Room Oxlet auto", "channels": ["push"], "source": "webhook"},
    "C002": {"name": "จองรถ", "channels": ["crm"], "source": "manual"},
})
now = timezone.now()
# กลุ่มที่ไม่มีในทะเบียน KV แต่มีข้อความจริง → ต้องถูกเก็บด้วย
for i in range(3):
    GroupChat.objects.create(group_id="C003", group_name="จัดไฟแนนซ์", message_id="x%d" % i,
                             chat_type=GroupChat.GROUP, msg_type="text", text="hi", sent_at=now)
GroupChat.objects.create(group_id="C001", group_name="Sale Coaching Room Oxlet auto",
                         message_id="y1", chat_type=GroupChat.GROUP, msg_type="text",
                         text="ถามเคสครับ", sent_at=now)
# แชท 1:1 กับลูกค้า ต้องไม่ถูกนับเป็นกลุ่ม
GroupChat.objects.create(group_id="", chat_type=GroupChat.USER, message_id="z1",
                         msg_type="text", text="สนใจรถ", sent_at=now)

call_command("line_groups_sync", apply=True, out=os.devnull)
ck("สร้างครบ 3 กลุ่ม (KV 2 + จากแชทอีก 1)", LineGroup.objects.count() == 3,
   list(LineGroup.objects.values_list("group_id", "name", "kind")))
ck("แชท 1:1 ไม่ถูกนับเป็นกลุ่ม", not LineGroup.objects.filter(group_id="").exists())
g1 = LineGroup.objects.get(group_id="C001")
ck("ห้องโค้ชได้ประเภท coaching", g1.kind == "coaching", g1.kind)
ck("ติดป้ายว่าระบบเดาให้", g1.kind_auto)
ck("เก็บบัญชีบอทที่อยู่ในกลุ่ม", g1.channels == ["push"], g1.channels)
ck("กลุ่มที่มีแต่ในแชท ได้ชื่อจากแชท",
   LineGroup.objects.get(group_id="C003").name == "จัดไฟแนนซ์")

print("\n[4] รันซ้ำไม่สร้างซ้ำ · คนตั้งประเภทเองแล้วห้ามเดาทับ")
call_command("line_groups_sync", apply=True, out=os.devnull)
ck("รันซ้ำยังมี 3 กลุ่ม", LineGroup.objects.count() == 3)

call_command("line_groups_sync", apply=True, set=["C002=coaching"], out=os.devnull)
g2 = LineGroup.objects.get(group_id="C002")
ck("ตั้งประเภทเองแล้วเปลี่ยนตาม", g2.kind == "coaching", g2.kind)
ck("ตั้งเองแล้วเลิกติดป้าย 'ระบบเดาให้'", not g2.kind_auto)

call_command("line_groups_sync", apply=True, out=os.devnull)
g2 = LineGroup.objects.get(group_id="C002")
ck("★ รันรอบถัดไปต้องไม่เดาทับค่าที่คนตั้งเอง", g2.kind == "coaching", g2.kind)

print("\n[5] ประเภทที่ไม่รู้จัก / คำสั่งผิดรูป ต้องไม่ทำอะไรพัง")
before = LineGroup.objects.get(group_id="C001").kind
call_command("line_groups_sync", apply=True, set=["C001=ไม่มีหมวดนี้"], out=os.devnull)
ck("ประเภทมั่ว = ไม่แตะของเดิม",
   LineGroup.objects.get(group_id="C001").kind == before)
call_command("line_groups_sync", apply=True, set=["ไม่มีเครื่องหมายเท่ากับ"], out=os.devnull)
ck("คำสั่งผิดรูป = ไม่ล้ม", LineGroup.objects.count() == 3)

print("\n[6] ไม่ใส่ --apply = ต้องไม่เขียนอะไร")
LineGroup.objects.all().delete()
call_command("line_groups_sync", out=os.devnull)
ck("ดูเฉยๆ ไม่สร้างแถว", LineGroup.objects.count() == 0)

print()
if fail:
    print("ไม่ผ่าน %d ข้อ: %s" % (len(fail), " · ".join(fail)))
else:
    print("ผ่านทั้งหมด")
runner.teardown_databases(old_cfg)
sys.exit(1 if fail else 0)
