# -*- coding: utf-8 -*-
"""เก็บลีดอัตโนมัติ → จองเลขรัน → ส่งใบลงกลุ่ม ADMIN เก็บ Lead (checkout/autolead.py · ไม่จ่ายเซลล์)

    manage.py autolead                 สถานะ + รอบล่าสุด
    manage.py autolead --off / --on    ปิด / เปิด (เปิด = เริ่มนับจากตอนนี้ ไม่ส่งย้อนหลัง)
    manage.py autolead --preview       จะส่งแชทไหน เลขอะไร (ไม่จองเลข ไม่ส่ง LINE)
    manage.py autolead --run           ทำรอบเดียวเดี๋ยวนี้
"""
import io
import json

from django.core.management.base import BaseCommand

from checkout import autolead as AL


class Command(BaseCommand):
    help = "เก็บลีดอัตโนมัติ (ส่งใบลงกลุ่ม ADMIN เก็บ Lead · ไม่จ่ายเซลล์)"

    def add_arguments(self, p):
        p.add_argument("--on", action="store_true")
        p.add_argument("--off", action="store_true")
        p.add_argument("--preview", action="store_true")
        p.add_argument("--run", action="store_true")
        p.add_argument("--out", default="")

    def handle(self, *a, **o):
        lines = []
        if o["on"] or o["off"]:
            AL.set_enabled(bool(o["on"]))
        c = AL.cfg()
        lines.append("เก็บลีดอัตโนมัติ: %s · เริ่มนับ %s · รอหลังให้เบอร์ %d นาที"
                     % ("เปิด" if c["enabled"] else "ปิด", c["since"] or "-", c["after_min"]))
        if o["preview"]:
            r = AL.run(dry=True)
            lines.append("ดูก่อน (ไม่จองเลข ไม่ส่ง): %s" % json.dumps(r, ensure_ascii=False))
        elif o["run"]:
            r = AL.run()
            lines.append("รอบนี้: %s" % json.dumps(r, ensure_ascii=False))
        try:
            from dashboard.services import cache_store
            last = (cache_store.get_kv("autolead_last") or {}).get("data") or {}
            if last:
                lines.append("รอบล่าสุดที่มีงาน: %s" % json.dumps(last, ensure_ascii=False)[:1500])
        except Exception:
            pass
        text = "\n".join(lines)
        if o["out"]:
            io.open(o["out"], "w", encoding="utf-8").write(text + "\n")
            self.stdout.write("เขียนลง %s แล้ว" % o["out"])
        else:
            self.stdout.write(text)
