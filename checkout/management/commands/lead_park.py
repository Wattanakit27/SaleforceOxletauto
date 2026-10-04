# -*- coding: utf-8 -*-
"""ดูห้องพัก Lead ("ADMIN เก็บ Lead") — ข้อความในห้องถูกอ่านเป็นอะไร + ลีดไหนยังรอเลข

    python manage.py lead_park                 # 7 วันล่าสุด
    python manage.py lead_park --days 30 --out lead_park.txt

ไว้ตรวจแพทเทิร์นเมื่อห้องมีข้อความมากขึ้น — ข้อความที่ "อ่านไม่ออก" จะถูกยกตัวอย่างให้ดู
(ถ้าแอดมินเริ่มพิมพ์แบบใหม่ในห้องนี้ จะเห็นตรงนั้นก่อน) · อ่านอย่างเดียว ไม่แก้อะไร ไม่ส่งอะไร
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from checkout import leadpark as LP
from checkout.leadgroup import parse_leadsheet
from checkout.models import GroupChat


class Command(BaseCommand):
    help = "ห้องพัก Lead: แพทเทิร์นข้อความ + ลีดที่ยังรอเลข"

    def add_arguments(self, p):
        p.add_argument("--days", type=int, default=LP.DAYS)
        p.add_argument("--out", default="", help="เขียนผลลงไฟล์ UTF-8 (console ไทยบน Windows เพี้ยน)")

    def handle(self, *a, **o):
        days = max(1, o["days"])
        lines = []
        w = lines.append
        since = timezone.now() - timedelta(days=days)
        msgs = list(GroupChat.objects.filter(chat_type=GroupChat.GROUP, sent_at__gte=since)
                    .filter(LP._rooms(LP.PARK_HINTS)).order_by("sent_at", "id"))
        rooms = sorted({m.group_name for m in msgs})
        w("ห้องพัก Lead ย้อนหลัง %d วัน: %s" % (days, ", ".join(rooms) or "(ยังไม่มีข้อความจากห้องที่ชื่อมี %s)"
                                              % " / ".join(LP.PARK_HINTS)))
        kinds = {"ใบร่าง (ยังไม่มีเลข)": 0, "ใบจริง (มีเลขแล้ว)": 0, "รูป/ไฟล์": 0, "อื่นๆ": 0}
        other = []
        for m in msgs:
            if LP.parse_draft(m.text):
                kinds["ใบร่าง (ยังไม่มีเลข)"] += 1
            elif parse_leadsheet(m.text):
                kinds["ใบจริง (มีเลขแล้ว)"] += 1
            elif m.has_media or not (m.text or "").strip():
                kinds["รูป/ไฟล์"] += 1
            else:
                kinds["อื่นๆ"] += 1
                other.append(m)
        w("ข้อความ %d: %s" % (len(msgs), " · ".join("%s %d" % kv for kv in kinds.items())))
        for m in other[:15]:
            w("  [อ่านไม่ออก] %s %s: %s" % (timezone.localtime(m.sent_at).strftime("%d/%m %H:%M"), m.sender_name,
                                           (m.text or "").replace("\n", " ⏎ ")[:140]))

        b = LP.board(days=days, cache_sec=0)
        st = b["stats"]
        w("")
        w("ยังรอเลข %d ราย (เกิน %d นาที %d ราย) · วันนี้ได้เลขแล้ว %d ราย%s" % (
            st["waiting"], b["warnMin"], st["late"], st["assignedToday"],
            (" · พักเฉลี่ย %d นาที" % st["avgWaitMinToday"]) if st["avgWaitMinToday"] is not None else ""))
        for i in b["waiting"]:
            w("  รอ   %s  %-8s %s · %s · %s · พักโดย %s · รอ %d นาที%s" % (
                i["at"][5:16].replace("T", " "), i["prefix"], i["account"] or i["lineId"] or i["phone"] or "-",
                i["channel"] or "-", i["car"] or "-", i["by"] or "-", i["waitMin"],
                (" · โพสต์ซ้ำ %d" % i["reposts"]) if i["reposts"] else ""))
        for i in b["assigned"][:20]:
            w("  ได้เลข %s  %s → %s @%s (โดย %s ใน %s) · พัก %d นาที" % (
                i["at"][5:16].replace("T", " "), i["prefix"], i["code"], i["seller"] or "-",
                i["assignedBy"] or "-", i["assignedRoom"] or "-", i["waitMin"]))
        text = "\n".join(lines)
        if o["out"]:
            with open(o["out"], "w", encoding="utf-8") as f:
                f.write(text + "\n")
            self.stdout.write("เขียนลง %s แล้ว" % o["out"])
        else:
            self.stdout.write(text)
