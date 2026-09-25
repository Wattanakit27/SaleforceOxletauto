# -*- coding: utf-8 -*-
"""ส่งรายงานเคสรับซื้อเข้าห้อง LINE ของแต่ละคน — 25 ก.ย.69 (เจ้าของสั่ง)

    python manage.py purchase_report --dry-run          # ดูข้อความ ไม่ส่ง
    python manage.py purchase_report --days 7           # ส่งจริงเข้าห้องตามที่ตั้งไว้
    python manage.py purchase_report --to Cxxxx         # ส่งทดสอบเข้าห้องเดียว
    python manage.py purchase_report --gap              # ดูเฉพาะตาราง "รถขาดตลาด"

⚠️ console ของ Windows เป็น cp874 ภาษาไทยอาจเพี้ยน → ใช้ `--out ไฟล์`
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "รายงานเคสรับซื้อ + รถที่ขาดตลาด เข้าห้อง LINE รายคน"

    def add_arguments(self, p):
        p.add_argument("--days", type=int, default=7, help="ย้อนหลังกี่วัน (ค่าเริ่มต้น 7)")
        p.add_argument("--max", type=int, default=0, help="สูงสุดกี่คันต่อข้อความ")
        p.add_argument("--to", default="", help="ส่งเข้าห้องเดียว (ทดสอบ)")
        p.add_argument("--dry-run", action="store_true", help="โชว์ข้อความ ไม่ส่ง")
        p.add_argument("--gap", action="store_true", help="โชว์เฉพาะตารางรถที่ขาดตลาด")
        p.add_argument("--out", default="", help="เขียนผลลงไฟล์ (กันภาษาไทยเพี้ยนใน console)")

    def handle(self, *a, **o):
        from dashboard.services import purchase_report as R

        lines = []
        say = lines.append

        gap = R.market_gap()
        if not gap:
            say("⚠️ ยังคำนวณ 'รถขาดตลาด' ไม่ได้ — อ่านผลสรุปแดชบอร์ด (dash_kv 'main') ไม่ได้")

        if o["gap"]:
            say("รถที่ตลาดหา แต่เราไม่มีของ (%d เดือนล่าสุด)" % R.DEMAND_MONTHS)
            say("  %-14s %8s %9s %9s %11s %8s"
                % ("รุ่น", "ถามหา", "พร้อมขาย", "มีทั้งหมด", "เพิ่งรับเข้า", "คะแนน"))
            for g in gap[:20]:
                say("  %-14s %8d %9d %9d %11d %8.0f"
                    % (g["name"][:14], g["demand"], g["show"], g["total"],
                       g.get("recent", 0), g["score"]))
            return self._done(lines, o)

        rep = R.build_room_reports(days=o["days"], gap=gap,
                                   max_cars=o["max"] or R.MAX_CARS)
        rooms = rep["rooms"]
        if not rooms:
            say("ไม่มีเคสค้างในช่วง %d วัน — ไม่ส่งอะไร" % o["days"])
            return self._done(lines, o)

        for gid, person, text in rooms:
            say("=" * 46)
            say("ห้อง %s  (%s)" % (person, gid[:12] + "…"))
            say("=" * 46)
            say(text)
            say("")
        if rep["admin"]:
            say("=" * 46)
            say("สรุปให้แอดมิน")
            say("=" * 46)
            say(rep["admin"])
            say("")

        if o["dry_run"]:
            say("(--dry-run: ไม่ส่ง)")
            return self._done(lines, o)

        # ── ส่งจริง ──
        from dashboard.services.line_channels import token_for
        from dashboard.services.line_notify import push_line_message

        targets = [(o["to"], "ทดสอบ", rooms[0][2])] if o["to"] else rooms
        for gid, person, text in targets:
            code, resp = push_line_message(
                gid, [{"type": "text", "text": text}], token_for(gid),
                what="รายงานเคสรับซื้อ (%s)" % person)
            say("ส่ง %-8s → %s" % (person, "สำเร็จ" if code == 200 else "ล้มเหลว %s %s" % (code, resp[:80])))
        return self._done(lines, o)

    def _done(self, lines, o):
        text = "\n".join(lines)
        if o["out"]:
            with open(o["out"], "w", encoding="utf-8") as f:
                f.write(text + "\n")
            self.stdout.write("เขียนผลลงไฟล์: %s" % o["out"])
        else:
            self.stdout.write(text)
