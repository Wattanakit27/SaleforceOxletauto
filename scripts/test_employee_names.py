# -*- coding: utf-8 -*-
"""แก้ชื่อเล่นในทะเบียนแล้ว ทุกที่ต้องขึ้นชื่อใหม่ — ★ 6 ต.ค.69

    python scripts/test_employee_names.py

**ทำไมต้องมีเทสต์นี้** — เจ้าของแจ้ง *"นิดตั้งค่าชื่อเล่นแล้ว แต่มันยังขึ้นเป็นชื่อ account อยู่"*
ต้นเหตุ: ตัวแปลง LINE id → ชื่อ (`people._load`) อ่าน **สำเนา** `LineProfile.nickname`
แล้ว `touch_profile` เขียนค่าที่อ่านได้กลับลงสำเนาเดิมทุกข้อความ = ชื่อใหม่ไม่มีวันเข้า
(วัดจริง: แก้ชื่อ 5/10 → ข้อความหลังแก้ 49 ข้อความยังเป็น "Nid")

ปลอมแค่ **ชีตพนักงาน (Google)** ซึ่งเป็นขอบระบบ — ฟังก์ชันของเราเองรันตัวจริงทั้งหมด
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
os.environ.setdefault("DB_HOST", "")
os.environ.setdefault("DEBUG", "True")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.test.utils import setup_test_environment  # noqa: E402
from django.test.runner import DiscoverRunner  # noqa: E402

setup_test_environment()
runner = DiscoverRunner(verbosity=0, interactive=False)
old_cfg = runner.setup_databases()
if "testserver" not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]

import json  # noqa: E402
from datetime import timedelta  # noqa: E402

from django.contrib.sessions.backends.signed_cookies import SessionStore  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.test import Client  # noqa: E402
from django.utils import timezone  # noqa: E402

from checkout import connect, people  # noqa: E402
from checkout.models import CheckIn, Employee, GroupChat, LineProfile  # noqa: E402
from dashboard.services import google_sheets  # noqa: E402

fail = []


def ck(name, got, want):
    ok = got == want
    print(("  ok   " if ok else "  FAIL ") + name)
    if not ok:
        print("        ได้ %r · ต้องได้ %r" % (got, want))
        fail.append(name)


# ชีตพนักงาน = ขอบระบบ (Google) · ปลอมให้อ่านไม่ได้ → ระบบต้องทำงานจากทะเบียนในฐานข้อมูลเรา
def _no_sheet(*a, **k):
    raise RuntimeError("ไม่ต่อ Google ในเทสต์")


google_sheets.fetch_sheet = _no_sheet

try:
    # ── ข้อมูลแบบเดียวกับ prod (5/10): นิดเพิ่งแก้ชื่อเล่น แต่สำเนายังเป็น "Nid" ──
    nid = Employee.objects.create(nickname="Nid", display_name="Nid", position="ทีม B",
                                  work_start="9:00", track_checkin=False)
    mat = Employee.objects.create(nickname="มัท", display_name="เซลมัท", position="ทีม A",
                                  work_start="9:00", track_checkin=True)
    LineProfile.objects.create(user_id="Uold_nid", employee=nid, channel="",
                               nickname="Nid", display_name="", is_employee=True)
    LineProfile.objects.create(user_id="Upush_nid", employee=nid, channel="push",
                               nickname="Nid", display_name="Nid", is_employee=True)
    LineProfile.objects.create(user_id="Ucust_nid", channel="crm", nickname="",
                               display_name="Nid", is_employee=False)   # ลูกค้าที่บังเอิญชื่อ Nid
    now = timezone.now()
    for i in range(3):
        GroupChat.objects.create(chat_type="group", group_id="Cgrp", message_id="m%d" % i,
                                 sender_id="Upush_nid", sender_name="Nid", msg_type="text",
                                 text="สวัสดี", sent_at=now)
    GroupChat.objects.create(chat_type="user", message_id="cust1", sender_id="Ucust_nid",
                             sender_name="Nid", msg_type="text", text="สนใจรถ", sent_at=now)
    GroupChat.objects.create(chat_type="user", message_id="out1", sender_id="Ucust_nid",
                             direction=GroupChat.OUT, sent_by=nid, sent_by_name="Nid",
                             msg_type="text", text="ได้ค่ะ", sent_at=now)
    CheckIn.objects.create(employee=nid, user_id="Upush_nid", date_iso=timezone.localdate(),
                           time_hm="08:59", status="ontime")

    # ── 1. แก้ชื่อในทะเบียนตรงๆ (ทางที่ไม่ผ่านหน้าเว็บ) → ตัวแปลงชื่อต้องอ่านจากทะเบียน ──
    print("── 1. ตัวแปลง LINE id → ชื่อ อ่านจากทะเบียน ไม่ใช่สำเนา")
    Employee.objects.filter(pk=nid.pk).update(nickname="นิด")
    people.invalidate()
    ck("id ฝั่งบอทใหม่ → นิด (เดิมได้ 'Nid' จากสำเนา)", people.nickname_for("Upush_nid"), "นิด")
    ck("id ฝั่งบอทเดิม → นิด", people.nickname_for("Uold_nid"), "นิด")
    ck("ลูกค้าที่ชื่อ Nid ไม่ถูกเหมาเป็นพนักงาน (ไม่มี id ในทะเบียน)",
       people.nickname_for("Ucust_nid") != "", True)

    # ── 2. touch_profile (ทุกข้อความที่เข้ามา) ต้องเขียนชื่อใหม่ ไม่เขียนชื่อเก่ากลับ ──
    print("── 2. ข้อความใหม่จากนิด → บันทึกเป็นชื่อใหม่ + สำเนาถูกแก้")
    Employee.objects.filter(pk=nid.pk).update(nickname="นิดดา")   # แก้อีกรอบ · แคชยังจำ "นิด"
    tp = people.touch_profile("Upush_nid", group_id="Cgrp", chat_type="group", channel="push")
    ck("ชื่อที่คืนให้ตอนเก็บแชท = ชื่อในทะเบียนทันที (ไม่รอแคชหมดอายุ)", tp.get("name"), "นิดดา")
    ck("สำเนาในโปรไฟล์ LINE ถูกแก้ตาม",
       LineProfile.objects.get(user_id="Upush_nid").nickname, "นิดดา")
    Employee.objects.filter(pk=nid.pk).update(nickname="Nid")
    LineProfile.objects.filter(employee=nid).update(nickname="Nid")
    people.invalidate()

    # ── 3. แก้ชื่อผ่านหน้า "พนักงาน" → ตามแก้ทุกสำเนา ──
    print("── 3. แก้ชื่อเล่นในหน้าพนักงาน")
    c = Client()
    st = SessionStore()
    st["oxlet_user"] = {"user_id": "admin", "nickname": "", "position": "admin"}
    st.save()
    c.cookies[settings.SESSION_COOKIE_NAME] = st.session_key
    nid.refresh_from_db()
    connect._TAGNICK["at"] = 0.0
    ck("ก่อนแก้: แท็ก @Nid หาเจอ", connect._tag_match("Nid"), "Nid")
    body = {"action": "save", "id": nid.pk, "nickname": "นิด", "displayName": "Nid",
            "position": "ทีม B", "workStart": "9:00", "dayOff": "ศุกร์", "active": True,
            "trackCheckin": False}
    r = c.post("/checkout/api/employees", json.dumps(body), content_type="application/json",
               secure=True)
    ck("บันทึกผ่าน", r.status_code, 200)
    ck("โปรไฟล์ LINE ทั้ง 2 บัญชีเป็นชื่อใหม่",
       sorted(LineProfile.objects.filter(employee=nid).values_list("nickname", flat=True)),
       ["นิด", "นิด"])
    ck("ข้อความเก่าที่นิดพิมพ์ในกลุ่ม → ชื่อใหม่",
       sorted(set(GroupChat.objects.filter(sender_id="Upush_nid").values_list("sender_name", flat=True))),
       ["นิด"])
    ck("ชื่อคนตอบลูกค้า (sent_by_name) → ชื่อใหม่",
       GroupChat.objects.get(message_id="out1").sent_by_name, "นิด")
    ck("ข้อความของลูกค้าที่บังเอิญชื่อ Nid ไม่ถูกแตะ",
       GroupChat.objects.get(message_id="cust1").sender_name, "Nid")
    ck("โปรไฟล์ลูกค้าไม่ถูกแตะ", LineProfile.objects.get(user_id="Ucust_nid").nickname, "")
    ck("แท็ก @Nid ในใบจ่ายลีด → นิด (เดิมกำกวม 2 ชื่อ คืนค่าว่าง)", connect._tag_match("Nid"), "นิด")
    ck("แท็ก @นิด → นิด", connect._tag_match("นิด"), "นิด")
    ck("ชื่อซ้ำกับคนอื่น = ปฏิเสธ (ของเดิม)",
       c.post("/checkout/api/employees", json.dumps(dict(body, nickname="มัท")),
              content_type="application/json", secure=True).status_code, 400)

    # ── 4. ปิด "เช็คชื่อ" แต่เช็คชื่อเข้ามาจริง → หน้าพนักงานต้องบอก ──
    print("── 4. ปิดเช็คชื่อไว้ แต่เช็คชื่อเข้ามาจริง")
    rows = {e["nickname"]: e for e in json.loads(r.content)["employees"]}
    ck("นิด: checkinsWhileOff = 1", rows["นิด"].get("checkinsWhileOff"), 1)
    ck("มัท (ติ๊กเช็คชื่อปกติ) = 0", rows["มัท"].get("checkinsWhileOff"), 0)
    CheckIn.objects.create(employee=nid, user_id="Upush_nid",
                           date_iso=timezone.localdate() - timedelta(days=30),
                           time_hm="09:00", status="ontime")
    rows = {e["nickname"]: e for e in json.loads(
        c.get("/checkout/api/employees", secure=True).content)["employees"]}
    ck("นับเฉพาะ 14 วันล่าสุด (เช็คชื่อเมื่อ 30 วันก่อนไม่นับ)", rows["นิด"]["checkinsWhileOff"], 1)

    # ── 5. คำสั่งซ่อมของที่ค้างบน prod ──
    print("── 5. manage.py sync_employee_names")
    LineProfile.objects.filter(employee=nid).update(nickname="Nid")       # จำลองของค้างก่อนแก้
    GroupChat.objects.filter(sender_id="Upush_nid").update(sender_name="Nid")
    out = io.StringIO()
    call_command("sync_employee_names", stdout=out)
    ck("ดูเฉยๆ: เจอ 1 คน", "ชื่อไม่ตรงทะเบียน 1 คน" in out.getvalue(), True)
    ck("ดูเฉยๆ: ไม่แก้อะไร", LineProfile.objects.filter(employee=nid, nickname="Nid").count(), 2)
    call_command("sync_employee_names", "--apply", stdout=io.StringIO())
    ck("--apply: แก้ครบ", LineProfile.objects.filter(employee=nid, nickname="นิด").count(), 2)
    ck("--apply: ข้อความแก้ครบ",
       GroupChat.objects.filter(sender_id="Upush_nid", sender_name="นิด").count(), 3)
    out = io.StringIO()
    call_command("sync_employee_names", stdout=out)
    ck("รันซ้ำ = ไม่มีอะไรต้องแก้", "ทุกคนตรงกับทะเบียนแล้ว" in out.getvalue(), True)
    ck("ลูกค้าชื่อ Nid ยังไม่ถูกแตะหลังรันคำสั่ง",
       GroupChat.objects.get(message_id="cust1").sender_name, "Nid")
finally:
    runner.teardown_databases(old_cfg)

print("\nผ่านทั้งหมด" if not fail else "\nไม่ผ่าน %d ข้อ" % len(fail))
sys.exit(1 if fail else 0)
