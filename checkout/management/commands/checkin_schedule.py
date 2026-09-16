# -*- coding: utf-8 -*-
"""ตั้งเวลาส่งตารางเช็คชื่อ + ตามคนที่ยังไม่เช็ค — ★ 16 ก.ย.69

แทน **Schedule Trigger** 2 ตัวใน n8n (9:30 ส่งตาราง · 10:00 ตามคน + แท็กผู้บริหาร)
`cron_tick` ที่ยิงอยู่ทุกนาทีเป็นคนเรียกให้เอง

    python manage.py checkin_schedule                               # ดูค่าปัจจุบัน
    python manage.py checkin_schedule --group Cxxxx --mode group --on
    python manage.py checkin_schedule --table-time 09:30 --escalate-time 10:00
    python manage.py checkin_schedule --test-id Uxxxx --mode test   # ลองยิงเข้าตัวเองก่อน
    python manage.py checkin_schedule --off                         # ปิด

**โหมด test = ส่งเข้าแชทส่วนตัว** (แท็กไม่ได้ ระบบจะเปลี่ยนเป็นรายชื่อให้เอง)
**โหมด group = ส่งเข้ากลุ่ม** ถึงจะแท็กคนได้จริง
"""
import re

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "ดู/ตั้งเวลาส่งตารางเช็คชื่อและข้อความตามคนที่ยังไม่เช็คชื่อ"

    def add_arguments(self, p):
        p.add_argument("--on", action="store_true", help="เปิดส่งอัตโนมัติ")
        p.add_argument("--off", action="store_true", help="ปิดส่งอัตโนมัติ")
        p.add_argument("--table-time", default="", help="เวลาส่งรูปตาราง (HH:MM)")
        p.add_argument("--escalate-time", default="", help="เวลาตามคนที่ยังไม่เช็ค (HH:MM · ว่าง = ไม่ส่งรอบนี้)")
        p.add_argument("--group", default="", help="LINE group id ปลายทางจริง")
        p.add_argument("--test-id", default="", help="LINE user id สำหรับทดสอบ")
        p.add_argument("--mode", choices=["test", "group"], help="ส่งเข้าที่ไหน")

    def handle(self, *a, **o):
        from checkout import checkin_report as R

        cfg, changed = R.config(), []

        def _time(v, key, label):
            v = (v or "").strip()
            if not v:
                return
            if v.lower() in ("none", "-", "off"):
                cfg[key] = ""
                changed.append("%s = ไม่ส่ง" % label)
                return
            if not re.match(r"^\d{1,2}:\d{2}$", v):
                self.stderr.write("เวลาต้องเป็น HH:MM (ได้รับ '%s')" % v)
                return
            h, m = v.split(":")
            cfg[key] = "%02d:%s" % (int(h), m)
            changed.append("%s = %s" % (label, cfg[key]))

        _time(o["table_time"], "table_time", "เวลาส่งรูปตาราง")
        _time(o["escalate_time"], "escalate_time", "เวลาตามคนที่ยังไม่เช็ค")
        if o["group"]:
            cfg["group_id"] = o["group"].strip()
            changed.append("กลุ่มปลายทาง = " + cfg["group_id"])
        if o["test_id"]:
            cfg["test_id"] = o["test_id"].strip()
            changed.append("ไอดีทดสอบ = " + cfg["test_id"])
        if o["mode"]:
            cfg["mode"] = o["mode"]
            changed.append("ส่งเข้า = " + ("กลุ่ม" if o["mode"] == "group" else "แชททดสอบ"))
        if o["on"]:
            cfg["enabled"] = True
            changed.append("เปิดส่งอัตโนมัติ")
        if o["off"]:
            cfg["enabled"] = False
            changed.append("ปิดส่งอัตโนมัติ")

        if changed:
            cfg = R.save_config(cfg)     # อ่านกลับจาก DB จริง — ยืนยันว่าเขียนติด
            cfg = R.config()
            self.stdout.write("บันทึกแล้ว:")
            for c in changed:
                self.stdout.write("   - " + c)
            self.stdout.write("")

        target = cfg["test_id"] if cfg["mode"] == "test" else cfg["group_id"]
        self.stdout.write("ค่าที่เซิร์ฟเวอร์ถืออยู่ตอนนี้")
        self.stdout.write("-" * 46)
        self.stdout.write("  ส่งอัตโนมัติ        : %s" % ("เปิด" if cfg["enabled"] else "ปิด"))
        self.stdout.write("  เวลาส่งรูปตาราง     : %s" % (cfg["table_time"] or "(ไม่ส่ง)"))
        self.stdout.write("  เวลาตามคนยังไม่เช็ค : %s" % (cfg["escalate_time"] or "(ไม่ส่ง)"))
        self.stdout.write("  ส่งเข้า              : %s" % ("กลุ่ม" if cfg["mode"] == "group" else "แชททดสอบ"))
        self.stdout.write("  ปลายทางที่จะใช้จริง  : %s" % (target or "(ยังไม่ได้ตั้ง)"))

        mgr = R.managers()
        self.stdout.write("  คนที่จะถูกแท็กตอนมีคนไม่เช็คชื่อ: %s"
                          % (", ".join(m["name"] for m in mgr) or "(ยังไม่ได้ติ๊กใคร)"))
        self.stdout.write('     ติ๊กได้ที่ เมนู → ทีม & สิทธิ์ → พนักงาน → ช่อง "แจ้งเตือน"')

        if cfg["enabled"] and not target:
            self.stdout.write(self.style.WARNING("  ⚠️ เปิดไว้แต่ยังไม่ได้ตั้งปลายทาง → จะไม่ส่งอะไรเลย"))
        if cfg["enabled"] and cfg["mode"] == "test":
            self.stdout.write(self.style.WARNING(
                "  ⚠️ โหมดทดสอบ = ส่งเข้าแชทส่วนตัว ซึ่ง LINE แท็กคนไม่ได้ "
                "(ระบบจะเปลี่ยนเป็นรายชื่อให้) · ใช้จริงต้อง --mode group"))
