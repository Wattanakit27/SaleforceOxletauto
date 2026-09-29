# -*- coding: utf-8 -*-
"""รวมบันทึกห้องโค้ช (เก่า+ใหม่) ลงตาราง `checkout_coachlog`

    python manage.py coach_db                      # ดูว่ามีอะไรอยู่แล้ว
    python manage.py coach_db --sync               # ดึงของใหม่จากแชทที่บอทเก็บ (prod ทำได้)
    python manage.py coach_db --import-sheet       # นำเข้าของเก่าจากแท็บ "บันทึกโค้ช"
    python manage.py coach_db --sync --import-sheet --out ผล.txt

⚠️ `--import-sheet` ต้องรันจากเครื่องที่ service account อ่านไฟล์โค้ชได้ (prod ยัง 403)
⚠️ console ไทยบน Windows เพี้ยน (cp874) → ใช้ --out
"""
from django.core.management.base import BaseCommand

from checkout import coach_db


class Command(BaseCommand):
    help = "รวมบันทึกห้องโค้ชลงฐานข้อมูล (ของเก่าจากชีต + ของใหม่จากแชท)"

    def add_arguments(self, p):
        p.add_argument("--sync", action="store_true",
                       help="ดึงจากแชทที่บอทเก็บไว้ → ตาราง (ไม่แตะชีต)")
        p.add_argument("--import-sheet", action="store_true",
                       help="นำเข้าแท็บ 'บันทึกโค้ช' ทั้งแท็บ (รันซ้ำได้)")
        p.add_argument("--days", type=int, default=120, help="ย้อนหลังกี่วันตอน --sync")
        p.add_argument("--seniors", default="", help='ทับรายชื่อซีเนียร์ เช่น "อุ้ม,เฟิร์ส"')
        p.add_argument("--out", default="", help="เขียนผลลงไฟล์ UTF-8")

    def handle(self, *a, **o):
        seniors = [s.strip() for s in (o["seniors"] or "").split(",") if s.strip()] or None
        L = []

        if o["import_sheet"]:
            r = coach_db.import_sheet()
            if r.get("error"):
                L.append("นำเข้าจากชีต : ล้มเหลว — %s" % r["error"])
            else:
                L.append("นำเข้าจากชีต : อ่าน %d แถว · เพิ่มใหม่ %d · มีอยู่แล้ว %d"
                         % (r["read"], r["added"], r["skipped"]))

        if o["sync"]:
            r = coach_db.sync_chat(days=o["days"], seniors=seniors)
            L.append("จากแชทบอท   : อ่าน %d ข้อความ · เพิ่มใหม่ %d · มีอยู่แล้ว %d"
                     % (r["read"], r["added"], r["skipped"]))

        s = coach_db.stats()
        L += [
            "",
            "ตาราง checkout_coachlog",
            "  รวม        : %d แถว" % s["total"],
            "  ช่วงวันที่  : %s → %s" % (s["from"] or "-", s["to"] or "-"),
            "  แยกบทบาท  : %s" % (" · ".join("%s %d" % (k or "(ว่าง)", v)
                                             for k, v in sorted(s["byRole"].items(),
                                                                key=lambda x: -x[1])) or "-"),
            "  แยกที่มา   : %s" % (" · ".join("%s %d" % (k or "(ว่าง)", v)
                                             for k, v in sorted(s["bySource"].items(),
                                                                key=lambda x: -x[1])) or "-"),
        ]
        if not (o["sync"] or o["import_sheet"]):
            L += ["", "ยังไม่ได้สั่งอะไร — ใส่ --sync (ของใหม่) หรือ --import-sheet (ของเก่า)"]

        txt = "\n".join(L)
        if o["out"]:
            with open(o["out"], "w", encoding="utf-8") as f:
                f.write(txt + "\n")
            self.stdout.write("wrote %s" % o["out"])
        else:
            self.stdout.write(txt)
