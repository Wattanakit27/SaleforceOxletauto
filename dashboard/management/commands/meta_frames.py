# -*- coding: utf-8 -*-
"""กราฟคนดูหลุด + ภาพทีละวินาทีของคลิป Facebook — ดูสถานะ / สั่งทำเดี๋ยวนี้ (15 ต.ค.69)

    python manage.py meta_frames                    # คลิปที่ได้ภาพ (คลิปใหม่ 7 วัน + ยิงแอดวิวสูง 25 อันดับ) + มีภาพหรือยัง
    python manage.py meta_frames --watch            # ทำรอบ "คลิปใหม่" เดี๋ยวนี้: ดึงกราฟ 7 วัน → วิเคราะห์ → ทำภาพ
    python manage.py meta_frames --analyze          # คิดผลวิเคราะห์ให้แถวที่ยังไม่มี (ไม่ยิง Facebook)
    python manage.py meta_frames --fetch [--limit 3]  # ทำภาพให้คลิปที่ยังไม่มี (ทีละคลิป รอจนเสร็จ)
    python manage.py meta_frames --purge            # ลบภาพทีละวินาทีทั้งหมด (ปิดฟีเจอร์แล้ว · 15 ต.ค.69 ใช้รูปปก+ลิงก์แทน)
    python manage.py meta_frames --out f.txt        # console ไทยเพี้ยน (cp874) ให้เขียนไฟล์แทน

★ ภาพทีละวินาทีปิดอยู่ (`video_frames.ENABLED = False`) — เจ้าของสั่ง "ไม่ต้องดาวน์โหลดวิดีโอ แค่ลิงก์ + รูปปก"
  `--watch` ยังดึงกราฟคลิปใหม่ + วิเคราะห์ตามปกติ แค่ไม่ทำภาพ

ปกติไม่ต้องรัน — cron_tick ทำรอบคลิปใหม่ทุกชั่วโมง + รอบเที่ยงคืนทำทุกคลิป
⚠️ บนเซิร์ฟเวอร์ต้องรันในนาม `oxlet` (เจ้าของ media/) ไม่งั้นโฟลเดอร์ภาพเป็นของ root แล้วเว็บเขียนไม่ได้
"""
import io

from django.core.management.base import BaseCommand

REASON = {"ads": "ยิงแอด", "new": "คลิปใหม่"}


class Command(BaseCommand):
    help = "กราฟคนดูหลุด + ภาพทีละวินาทีของคลิป Facebook — ดูสถานะ / ทำเดี๋ยวนี้"

    def add_arguments(self, p):
        p.add_argument("--watch", action="store_true", help="ทำรอบคลิปใหม่เดี๋ยวนี้ (ดึงกราฟ+วิเคราะห์+ภาพ)")
        p.add_argument("--analyze", action="store_true", help="คิดผลวิเคราะห์ให้แถวที่ยังไม่มี")
        p.add_argument("--fetch", action="store_true", help="ทำภาพให้คลิปที่ยังไม่มีเดี๋ยวนี้ (เฉพาะตอนเปิดฟีเจอร์)")
        p.add_argument("--purge", action="store_true", help="ลบภาพทีละวินาทีทั้งหมด")
        p.add_argument("--top", type=int, default=0, help="ยิงแอดกี่อันดับ (ไม่ใส่ = ค่าตั้งต้นของระบบ)")
        p.add_argument("--limit", type=int, default=None, help="ทำภาพอย่างมากกี่คลิปในรอบนี้")
        p.add_argument("--out", default="", help="เขียนผลลงไฟล์")

    def handle(self, *a, **o):
        from dashboard.management.commands.social_covers import _owner_warning
        from dashboard.services import video_frames as VF

        lines = []

        def say(s=""):
            lines.append(s)
            if not o["out"]:
                try:
                    self.stdout.write(s)
                except UnicodeEncodeError:
                    self.stdout.write(s.encode("ascii", "replace").decode())

        top = o["top"] or VF.TOP_N
        w = _owner_warning().replace("social_covers --fetch", "meta_frames --watch")
        if w:
            say(w)
            say("")

        if o["purge"]:
            r = VF.purge()
            say("ลบภาพทีละวินาทีแล้ว %d คลิป · คืนพื้นที่ %.1f MB" % (r["clips"], r["mb"]))
            say("")
        if not VF.ENABLED:
            say("ภาพทีละวินาทีปิดอยู่ (ไม่โหลดวิดีโอ · หน้าเว็บใช้รูปหน้าปก + ลิงก์ไป Facebook)")
            say("")
        if o["watch"]:
            from dashboard.services import meta_sync
            say("รอบคลิปใหม่: ดึงกราฟคลิป %d วันล่าสุด → วิเคราะห์ → ทำภาพ …" % meta_sync.WATCH_DAYS)
            r = meta_sync.watch_videos("manual")
            say("  กราฟ %s คลิป (เพิ่งเจอครั้งแรก %s) · วิเคราะห์เพิ่ม %s · ข้อมูลดิบ %s ก้อน"
                % (r.get("videos", 0), r.get("new", 0), r.get("analyzed", 0), r.get("raw", 0)))
            say("  ภาพ: %s" % r.get("frames"))
            for e in (r.get("errors") or [])[:10]:
                say("    - " + e)
            say("")
        if o["analyze"]:
            from dashboard.services import social_stats
            say("คิดผลวิเคราะห์ให้แถวที่ยังไม่มี: %d คลิป" % social_stats.analyze_missing())
            say("")
        if o["fetch"]:
            say("กำลังทำภาพทีละวินาที (ทีละคลิป · คลิปละ ~10-30 วินาที) …")
            r = VF.prefetch(top, limit=o["limit"])
            say("  เข้าเกณฑ์ %d · มีอยู่แล้ว %d · ทำใหม่ %d · ไม่สำเร็จ %d · มีคนทำอยู่ %d · ลบของที่หลุดเกณฑ์ %d"
                % (r["total"], r["ready"], r["made"], r["failed"], r["busy"], r["pruned"]))
            for e in r["errors"][:10]:
                say("    - " + e)
            say("")

        if not VF.ENABLED:
            try:
                from dashboard.models import MetaVideoRetention
                tot = MetaVideoRetention.objects.count()
                done = MetaVideoRetention.objects.filter(analyzed_at__isnull=False).count()
                say("กราฟคนดูหลุดในฐานข้อมูล %d คลิป · วิเคราะห์แล้ว %d" % (tot, done))
            except Exception:
                pass
            if o["out"]:
                io.open(o["out"], "w", encoding="utf-8").write("\n".join(lines))
                self.stdout.write("เขียนผลลง %s แล้ว" % o["out"])
            return
        rows = VF.eligible(top, fresh=True)
        n_new = sum(1 for r in rows if r["reason"] == "new")
        say("คลิปที่ได้ภาพทีละวินาที %d คลิป = ยิงแอดวิวสูงสุด %d อันดับ (%d) + คลิปใหม่ %d วัน (%d)"
            % (len(rows), top, len(rows) - n_new, VF.NEW_DAYS, n_new))
        have = 0
        for i, r in enumerate(rows, 1):
            st = VF.status(r["post_id"])
            mark = {"ready": "มีภาพ %d ภาพ" % len(st.get("urls") or []),
                    "running": "กำลังทำ", "error": "พลาด: " + (st.get("error") or "")[:60],
                    "none": "ยังไม่มี"}.get(st["state"], st["state"])
            have += st["state"] == "ready"
            views = ("  วิว %s (แอด %s)" % (format(r["views"], ","), format(r["paid"], ","))
                     if r["reason"] == "ads" else "")
            say("  %2d. [%s] %s%s  %s" % (i, REASON.get(r["reason"], r["reason"]), r["post_id"], views, mark))
        say("")
        say("มีภาพแล้ว %d จาก %d คลิป" % (have, len(rows)))
        try:
            from dashboard.models import MetaVideoRetention
            tot = MetaVideoRetention.objects.count()
            done = MetaVideoRetention.objects.filter(analyzed_at__isnull=False).count()
            say("กราฟคนดูหลุดในฐานข้อมูล %d คลิป · วิเคราะห์แล้ว %d" % (tot, done))
        except Exception:
            pass

        if o["out"]:
            io.open(o["out"], "w", encoding="utf-8").write("\n".join(lines))
            self.stdout.write("เขียนผลลง %s แล้ว" % o["out"])
