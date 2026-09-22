# -*- coding: utf-8 -*-
"""สั่งดึงยอด YouTube เดี๋ยวนี้ — ไม่ต้องรอรอบเที่ยงคืน

    python manage.py youtube_sync --check          # แค่เช็คว่าคีย์/ช่องใช้ได้ไหม ไม่เขียน DB
    python manage.py youtube_sync                  # ดึงจริง (trigger=manual)
    python manage.py youtube_sync --cron           # ดึงแบบรอบเที่ยงคืน (snap_date = เมื่อวาน)
    python manage.py youtube_sync --out ผล.txt     # เขียนผลลงไฟล์ (console ไทยเพี้ยน cp874)

⚠️ **ยอดรายวันต้องมี snapshot อย่างน้อย 2 คืนถึงจะคำนวณได้** (วันแรกไม่มีวันก่อนหน้าให้ลบ)
   → รันวันนี้ครั้งเดียวจะเห็นแต่ "ยอดสะสม" ยังไม่มีเลขรายวัน เป็นเรื่องปกติ
⚠️ คีย์ถูกล็อก IP ไว้ที่ VPS → **ต้องรันบนเซิร์ฟเวอร์** รันในเครื่องจะได้ 403
"""
import io

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "ดึงยอดช่อง/คลิป YouTube เข้าฐานข้อมูลเดี๋ยวนี้"

    def add_arguments(self, parser):
        parser.add_argument("--cron", action="store_true",
                            help="ทำเป็นรอบเที่ยงคืน (snap_date = เมื่อวาน · ใช้คำนวณยอดรายวัน)")
        parser.add_argument("--check", action="store_true",
                            help="เช็คคีย์/ช่องอย่างเดียว ไม่เขียนฐานข้อมูล")
        parser.add_argument("--out", default="", help="เขียนผลลงไฟล์แทนการพิมพ์ลงจอ")

    def handle(self, *a, **o):
        from dashboard.services import youtube_sync as Y

        lines = []
        def say(s=""):
            lines.append(str(s))

        if not Y.is_configured():
            say("ยังไม่ได้ตั้ง YOUTUBE_API_KEY / YOUTUBE_CHANNELS ใน .env — ไม่ทำอะไร")
            return self._flush(lines, o["out"])

        from django.conf import settings
        refs = list(settings.YOUTUBE_CHANNELS)
        say("ช่องที่ตั้งไว้ %d ช่อง: %s" % (len(refs), ", ".join(refs)))

        if o["check"]:
            say("\n--- เช็คอย่างเดียว (ไม่เขียนฐานข้อมูล) ---")
            for ref in refs:
                try:
                    c = Y.resolve_channel(ref)
                    say("  OK %s -> %s | ผู้ติดตาม %s | วิวรวม %s | คลิป %s | %s"
                        % (ref, c["title"], c["subscribers"], c["views"], c["videos"],
                           c["channel_id"]))
                except Y.SyncError as e:
                    say("  ล้มเหลว %s -> %s" % (ref, e))
            return self._flush(lines, o["out"])

        trigger = "cron" if o["cron"] else "manual"
        say("\nกำลังดึง (trigger=%s) ..." % trigger)
        r = Y.run(trigger, by="manage.py")
        if r.get("error"):
            say("ไม่ได้เริ่ม: %s" % r["error"])
            return self._flush(lines, o["out"])

        say("  วันที่ของยอด : %s" % r.get("snapDate"))
        say("  ใช้เวลา      : %.1f วินาที" % (r.get("ms", 0) / 1000.0))
        say("  คลิปที่เก็บ   : %d" % r.get("videos", 0))
        for name, n in (r.get("channels") or {}).items():
            say("     - %s : %d คลิป" % (name, n))
        say("  แถวรายวันที่คำนวณได้ : %s" % r.get("daily", 0))
        if r.get("trimmed"):
            say("  ลบข้อมูลดิบเกิน 90 วัน : %d แถว" % r["trimmed"])
        for e in (r.get("errors") or []):
            say("  ผิดพลาด: %s" % e)
        say("\nสรุป: %s" % ("สำเร็จ" if r.get("ok") else "มีบางช่องไม่สำเร็จ (ดูข้างบน)"))
        if not r.get("daily"):
            say("หมายเหตุ: ยังไม่มีเลข 'รายวัน' เพราะต้องมี snapshot อย่างน้อย 2 คืนถึงจะลบกันได้")
        return self._flush(lines, o["out"])

    def _flush(self, lines, out):
        text = "\n".join(lines)
        if out:
            with io.open(out, "w", encoding="utf-8") as f:
                f.write(text + "\n")
            self.stdout.write("wrote %s (%d lines)" % (out, len(lines)))
        else:
            for ln in lines:
                try:
                    self.stdout.write(ln)
                except UnicodeEncodeError:      # console ไทยเพี้ยน (cp874)
                    self.stdout.write(ln.encode("ascii", "replace").decode("ascii"))
