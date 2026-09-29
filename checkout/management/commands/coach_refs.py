# -*- coding: utf-8 -*-
"""เขียนแท็บอ้างอิง "พนักงาน" + "กลุ่มไลน์" ในไฟล์โค้ช

    python manage.py coach_refs                 # ดูเฉยๆ ไม่แตะชีต
    python manage.py coach_refs --apply
    python manage.py coach_refs --apply --out ผล.txt

⚠️ console ไทยบน Windows เพี้ยน (cp874) → ใช้ --out
⚠️ ต้องรันจากเครื่องที่ service account มีสิทธิ์ writer บนไฟล์โค้ช
   (ตอนนี้ prod ยังเป็น 403 — ดู CLAUDE.md หัวข้อห้องโค้ช)
"""
from django.core.management.base import BaseCommand

from checkout import coach_refs


class Command(BaseCommand):
    help = "เขียนแท็บ 'พนักงาน' + 'กลุ่มไลน์' ในไฟล์โค้ช (สำหรับผู้วิเคราะห์ภายนอก)"

    def add_arguments(self, p):
        p.add_argument("--apply", action="store_true", help="เขียนจริง (ไม่ใส่ = ดูเฉยๆ)")
        p.add_argument("--seniors", default="", help='ทับรายชื่อซีเนียร์ เช่น "อุ้ม,เฟิร์ส"')
        p.add_argument("--out", default="", help="เขียนผลลงไฟล์ UTF-8")

    def handle(self, *a, **o):
        seniors = [s.strip() for s in (o["seniors"] or "").split(",") if s.strip()] or None
        r = coach_refs.push(apply=o["apply"], seniors=seniors)

        L = [
            "ไฟล์โค้ช     : %s" % coach_refs.SHEET_ID,
            "แท็บที่เขียน  : %s · %s" % (coach_refs.EMP_TAB, coach_refs.GRP_TAB),
            "พนักงาน      : %d คน" % r["employees"],
            "กลุ่มไลน์     : %d กลุ่ม" % r["groups"],
            "ซีเนียร์      : %s" % (" · ".join(r["seniors"]) or "(ไม่พบใครตรงรายชื่อ)"),
        ]
        if r["noIds"]:
            L.append("ยังไม่ผูก LINE: %d คน (%s)"
                     % (len(r["noIds"]), " · ".join(r["noIds"][:8])))
        L.append("")
        L.append("เขียนชีตแล้ว" if r["applied"] else "ยังไม่เขียน — ใส่ --apply เพื่อเขียนจริง")

        txt = "\n".join(L)
        if o["out"]:
            with open(o["out"], "w", encoding="utf-8") as f:
                f.write(txt + "\n")
            self.stdout.write("wrote %s" % o["out"])
        else:
            self.stdout.write(txt)
