# -*- coding: utf-8 -*-
"""เก็บลีดอัตโนมัติ → จองเลขรัน → ส่งใบลงกลุ่ม ADMIN เก็บ Lead (checkout/autolead.py · ไม่จ่ายเซลล์)

    manage.py autolead                       สถานะ + รอบล่าสุด
    manage.py autolead --off / --on          ปิด / เปิดทั้งหมด (เปิด = เริ่มนับจากตอนนี้ ไม่ส่งย้อนหลัง)
    manage.py autolead --drafts on|off       บอทรันเลขใบร่างที่แอดมินพักในกลุ่ม ADMIN เก็บ Lead
    manage.py autolead --warn on|off         บอทเตือนในห้องจ่ายเบอร์ (เลขชน / ออกเลขใหม่ให้ลูกค้าที่มีเลขแล้ว)
    manage.py autolead --preview             แชทไหนจะได้เลขอะไร (ไม่จองเลข ไม่ส่ง LINE)
    manage.py autolead --run                 ทำรอบเดียวเดี๋ยวนี้ (แชท + ข้อความกลุ่มที่ค้าง)
"""
import io
import json

from django.core.management.base import BaseCommand, CommandError

from checkout import autolead as AL


def _onoff(v):
    v = (v or "").strip().lower()
    if v not in ("on", "off"):
        raise CommandError("ใส่ on หรือ off")
    return v == "on"


class Command(BaseCommand):
    help = "เก็บลีดอัตโนมัติ (ส่งใบลงกลุ่ม ADMIN เก็บ Lead · ไม่จ่ายเซลล์)"

    def add_arguments(self, p):
        p.add_argument("--on", action="store_true")
        p.add_argument("--off", action="store_true")
        p.add_argument("--drafts", default="")
        p.add_argument("--warn", default="")
        p.add_argument("--preview", action="store_true")
        p.add_argument("--run", action="store_true")
        p.add_argument("--out", default="")

    def handle(self, *a, **o):
        lines = []
        if o["on"] or o["off"]:
            AL.set_enabled(bool(o["on"]))
        if o["drafts"]:
            AL.set_switch("drafts", _onoff(o["drafts"]))
        if o["warn"]:
            AL.set_switch("warn", _onoff(o["warn"]))
        c = AL.cfg()
        lines.append("เก็บลีดอัตโนมัติ: %s · เริ่มนับ %s · รอหลังให้เบอร์ %d นาที"
                     % ("เปิด" if c["enabled"] else "ปิด", c["since"] or "-", c["after_min"]))
        lines.append("  บอทรันเลขใบร่างในกลุ่ม ADMIN เก็บ Lead: %s · เตือนในห้องจ่ายเบอร์: %s"
                     % ("เปิด" if c["drafts"] else "ปิด", "เปิด" if c["warn"] else "ปิด"))
        ptr = AL._kv(AL.PTR_KEY)
        lines.append("  อ่านข้อความกลุ่มถึง: %s" % (("#%s (%s)" % (ptr.get("last_id"), ptr.get("at") or "-"))
                                                 if ptr else "ยังไม่เริ่ม (เริ่มจากข้อความล่าสุดตอนรอบแรก)"))
        if o["preview"]:
            r = AL.run(dry=True)
            lines.append("ดูก่อน (ไม่จองเลข ไม่ส่ง): %s" % json.dumps(r, ensure_ascii=False))
        elif o["run"]:
            r = AL.run()
            lines.append("รอบนี้: %s" % json.dumps(r, ensure_ascii=False))
        for key, title in (("autolead_last", "รอบล่าสุด (แชท)"), (AL.LAST_GROUP_KEY, "รอบล่าสุด (ข้อความกลุ่ม)")):
            last = AL._kv(key)
            if last:
                lines.append("%s: %s" % (title, json.dumps(last, ensure_ascii=False)[:1500]))
        text = "\n".join(lines)
        if o["out"]:
            io.open(o["out"], "w", encoding="utf-8").write(text + "\n")
            self.stdout.write("เขียนลง %s แล้ว" % o["out"])
        else:
            self.stdout.write(text)
