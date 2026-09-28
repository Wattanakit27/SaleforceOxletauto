# -*- coding: utf-8 -*-
"""ตรวจการแปลงไอดีผู้รับให้ตรงบัญชีบอทที่ส่ง (27 ก.ย.69)

    python scripts/test_dm_channel.py

**ทำไมต้องมีเทสต์นี้** — ตามด่วนหยุดส่งทั้งทีม 3 วัน (25-27 ก.ย.) เพราะส่งไปไอดี
ฝั่งบอทเดิม ด้วย token ของบอทตัวส่ง → LINE ไม่รู้จักผู้รับ ตอบ 400 ทุกคน
โดยไม่มีอะไรฟ้องนอกจาก `dash_event_log`

ปลอมที่ **`requests.post`** (ขอบระบบ) ไม่ปลอมฟังก์ชันของเราเอง — ตามบทเรียนเดิม
ที่เคยปลอม `fetch_profile` ทั้งฟังก์ชันแล้วบั๊กจริงหลุดไป 3 วัน
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

from django.test import override_settings

from checkout.models import Employee, LineProfile
from checkout.people import id_for_channel
from dashboard.services import line_channels as LC
from dashboard.services import line_notify as LN

fail = []


def ck(name, got, want):
    ok = got == want
    print(("  ok   " if ok else "  FAIL ") + name)
    if not ok:
        print("        ได้ %r · ต้องได้ %r" % (got, want))
        fail.append(name)


CRM_TOK, PUSH_TOK = "tok-crm-xxx", "tok-push-yyy"

# ---- ข้อมูลจำลองแบบเดียวกับ prod --------------------------------
# พนักงานที่มีไอดี 2 ฝั่ง: ตัวที่นำเข้าจากชีต (channel='') + ตัวที่บอทใหม่ได้ยิน (push)
e1 = Employee.objects.create(nickname="เจ", display_name="เจ Oxlet")
LineProfile.objects.create(user_id="Usheet_je", employee=e1, channel="",
                           nickname="เจ", is_employee=True)
LineProfile.objects.create(user_id="Upush_je", employee=e1, channel="push",
                           nickname="เจ", is_employee=True)

# พนักงานที่ยังมีแต่ไอดีจากชีต (บอทใหม่ไม่เคยได้ยิน) — ห้ามเดา
e2 = Employee.objects.create(nickname="เบียร์", display_name="Wattanakit")
LineProfile.objects.create(user_id="Usheet_beer", employee=e2, channel="",
                           nickname="เบียร์", is_employee=True)

# ลูกค้า — ไม่ผูกทะเบียนพนักงาน · ห้ามแปลงเด็ดขาด
LineProfile.objects.create(user_id="Ucust_1", channel="crm", display_name="ลูกค้า ก")

print("people.id_for_channel()")
ck("ไอดีจากชีต + จะส่งด้วยบอทตัวส่ง → ได้ไอดีฝั่ง push",
   id_for_channel("Usheet_je", "push"), "Upush_je")
ck("ส่งด้วยบอทตัวส่ง + ไอดีถูกฝั่งอยู่แล้ว → คืนตัวเดิม",
   id_for_channel("Upush_je", "push"), "Upush_je")
ck("คนที่ยังไม่มีไอดีฝั่ง push → ค่าว่าง (ไม่เดา)",
   id_for_channel("Usheet_beer", "push"), "")
ck("ลูกค้า (ไม่ผูกทะเบียน) → ค่าว่าง ไม่แปลงให้",
   id_for_channel("Ucust_1", "push"), "")
ck("ไอดีที่ไม่รู้จัก → ค่าว่าง", id_for_channel("Uไม่มีจริง", "push"), "")
ck("ไม่บอกว่าจะส่งจากบัญชีไหน → ค่าว่าง", id_for_channel("Usheet_je", ""), "")

with override_settings(LINE_CHANNEL_ACCESS_TOKEN=CRM_TOK,
                       LINE_PUSH_CHANNEL_ACCESS_TOKEN=PUSH_TOK):
    print("line_channels.key_of_token()")
    ck("token ตัวรับ", LC.key_of_token(CRM_TOK), "crm")
    ck("token ตัวส่ง", LC.key_of_token(PUSH_TOK), "push")
    ck("token ที่ไม่รู้จัก → ค่าว่าง", LC.key_of_token("tok-มั่ว"), "")
    ck("token ว่าง → ค่าว่าง", LC.key_of_token(""), "")

    print("line_notify._dm_target()")
    ck("แชท 1:1 ไอดีผิดฝั่ง → แปลงให้ + จดว่า remap",
       LN._dm_target("Usheet_je", PUSH_TOK), ("Upush_je", {"remap": "push"}))
    # ★ 29 ก.ย.69 — เดิมข้อนี้คาดว่า "แปลงไม่ได้ = ส่งด้วยไอดีเดิม (แล้วก็ 400)"
    #   ตอนนี้เปลี่ยนเจตนา: บัญชีที่ควรใช้ไม่มีไอดีของคนนี้เลย = ยังไงก็ส่งไม่ถึง
    #   → ให้ **สลับไปใช้บัญชีที่ไอดีนี้เป็นของมัน** แทน (ดู dm_route)
    to, extra = LN._dm_target("Usheet_beer", PUSH_TOK)
    ck("คนที่ยังไม่มีไอดีฝั่งใหม่ → ไอดีไม่เปลี่ยน", to, "Usheet_beer")
    ck("★ แต่สลับไปส่งด้วยบัญชีตัวรับ + จดเหตุผลไว้", extra.get("viaChannel"), "crm")
    ck("กลุ่ม C… → ไม่แตะเลย",
       LN._dm_target("C40b836d0390ba32994b17c2c0286643d", PUSH_TOK),
       ("C40b836d0390ba32994b17c2c0286643d", {}))
    ck("ห้อง R… → ไม่แตะเลย", LN._dm_target("Rabc", PUSH_TOK), ("Rabc", {}))
    ck("ลูกค้า → ไม่แตะ (การตอบแชทเลือกบัญชีเองอยู่แล้ว)",
       LN._dm_target("Ucust_1", PUSH_TOK), ("Ucust_1", {}))

    # ---- ส่งจริงผ่าน push_line_message: ปลอมที่ requests.post ----
    print("push_line_message() ยิงไปที่ไอดีที่แปลงแล้วจริงไหม")
    sent = []

    class Res:
        status_code, text = 200, "{}"

    def fake_post(url, headers=None, json=None, timeout=None):
        # เก็บ token ที่ใช้ด้วย — ข้อสำคัญคือ "ส่งด้วยบัญชีไหน" ไม่ใช่แค่ "ส่งไปไอดีไหน"
        sent.append((json.get("to"),
                     (headers or {}).get("Authorization", "").replace("Bearer ", "")))
        return Res()

    real = LN.requests.post
    LN.requests.post = fake_post
    try:
        LN.push_line_message("Usheet_je", [{"type": "text", "text": "ตามด่วน"}],
                             PUSH_TOK, what="ตามด่วน (เทสต์)")
        LN.push_line_message("C40b836d0390ba32994b17c2c0286643d",
                             [{"type": "text", "text": "การ์ด"}], PUSH_TOK, what="การ์ด (เทสต์)")
        LN.push_line_message("Ucust_1", [{"type": "text", "text": "ตอบลูกค้า"}],
                             CRM_TOK, what="ตอบแชทลูกค้า (เทสต์)")
        LN.push_line_message("Usheet_beer", [{"type": "text", "text": "ตามด่วน"}],
                             PUSH_TOK, what="ตามด่วน (เทสต์ คนที่ยังไม่มีไอดีใหม่)")
    finally:
        LN.requests.post = real
    ck("ตามด่วน → ยิงไปไอดีฝั่ง push ด้วย token ตัวส่ง", sent[0], ("Upush_je", PUSH_TOK))
    ck("การ์ดเข้ากลุ่ม → ไอดีกลุ่มเดิม ด้วย token ตัวส่ง",
       sent[1], ("C40b836d0390ba32994b17c2c0286643d", PUSH_TOK))
    ck("ตอบแชทลูกค้าด้วยบัญชีตัวรับ → ไอดีเดิม token ตัวรับ", sent[2], ("Ucust_1", CRM_TOK))
    ck("★ คนที่ยังไม่มีไอดีฝั่งใหม่ → ยิงด้วย **token ตัวรับ** ไอดีเดิม (ส่งถึงจริง)",
       sent[3], ("Usheet_beer", CRM_TOK))

print()
if fail:
    print("ไม่ผ่าน %d ข้อ: %s" % (len(fail), " · ".join(fail)))
else:
    print("ผ่านทั้งหมด")
runner.teardown_databases(old_cfg)
sys.exit(1 if fail else 0)
