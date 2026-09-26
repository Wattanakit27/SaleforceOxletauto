# -*- coding: utf-8 -*-
"""รูปปกคลิป/โพสต์ — ดูสถานะ / ดึงมาเก็บเดี๋ยวนี้ (26 ก.ย.69)

    python manage.py social_covers                 # ดูว่ามีรูปปกกี่ใบแล้ว
    python manage.py social_covers --fetch         # ดึงรูปปกเดี๋ยวนี้ (ไม่ต้องรอ sync เที่ยงคืน)
    python manage.py social_covers --fetch --side tiktok
    python manage.py social_covers --out cover.txt # console ไทยเพี้ยน (cp874) ให้เขียนไฟล์แทน

**ทำไมต้องมีคำสั่งนี้** — ลิงก์รูปปกที่ TikTok/Facebook ให้มา **หมดอายุใน ~6 ชม.**
จึงเก็บลงฐานข้อมูลไม่ได้ ต้องโหลดตัวไฟล์มาเก็บเอง · รอบ sync เที่ยงคืนโหลดให้อยู่แล้ว
คำสั่งนี้ไว้ "เอาเดี๋ยวนี้" ตอนเพิ่งเปิดฟีเจอร์ หรือตอนไฟล์หาย

⚠️ ดึงได้เฉพาะคลิป/โพสต์ที่ยังอยู่ในหน้าต่างที่ API คืนมา (TikTok ~90 วันล่าสุด)
   ของเก่ากว่านั้นจะไม่มีรูปปก — การ์ดจะใช้แถบสีประจำแพลตฟอร์มแทน ไม่พัง
"""
import io

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "ดูสถานะ/ดึงรูปปกคลิปของ TikTok + Facebook"

    def add_arguments(self, p):
        p.add_argument("--fetch", action="store_true", help="ดึงรูปปกเดี๋ยวนี้")
        p.add_argument("--side", default="", help="tiktok | meta (ไม่ใส่ = ทั้งคู่)")
        p.add_argument("--out", default="", help="เขียนผลลงไฟล์ (เลี่ยง console ไทยเพี้ยน)")

    def handle(self, *a, **o):
        lines = []

        def say(s=""):
            lines.append(s)
            if not o["out"]:
                try:
                    self.stdout.write(s)
                except UnicodeEncodeError:      # console ไทยเพี้ยน — ไม่ให้ล้มทั้งคำสั่ง
                    self.stdout.write(s.encode("ascii", "replace").decode())

        from dashboard.services import covers
        want = [s for s in covers.SIDES if not o["side"] or s == o["side"]]

        w = _owner_warning()
        if w:
            say(w)
            say("")

        if o["fetch"]:
            for side in want:
                say("ดึงรูปปกฝั่ง %s …" % side)
                try:
                    n = _fetch(side, say)
                    say("  โหลดมาใหม่ %d ใบ" % n)
                except Exception as e:
                    say("  ดึงไม่สำเร็จ: %s" % str(e)[:200])
            say("")

        say("รูปปกที่เก็บไว้ตอนนี้")
        st = covers.stats()
        for side in covers.SIDES:
            have = st.get(side, {})
            total = _item_count(side)
            say("  %-8s %5d ใบ · %5.1f MB%s"
                % (side, have.get("files", 0), have.get("mb", 0.0),
                   ("  (จากชิ้นงานทั้งหมด %d)" % total) if total else ""))
        say("  youtube  — ไม่ต้องเก็บ (ประกอบลิงก์จาก video id ได้ฟรี ไม่หมดอายุ)")

        if o["out"]:
            io.open(o["out"], "w", encoding="utf-8").write("\n".join(lines))
            self.stdout.write("เขียนผลลง %s แล้ว" % o["out"])


def _owner_warning() -> str:
    """เตือนเมื่อจะสร้างไฟล์ด้วย user ที่ไม่ใช่เจ้าของ media/

    ★ กับดักตอน deploy: บนเซิร์ฟเวอร์ `media/` เป็นของ user `oxlet` (ตัวที่รันเว็บ+cron)
      ถ้ารันคำสั่งนี้ด้วย **root** โฟลเดอร์ `media/covers/` จะเกิดมาเป็นของ root
      → รอบ sync เที่ยงคืนที่รันในนาม `oxlet` **เขียนรูปปกไม่ได้อีกเลย แบบเงียบๆ**
    """
    import os
    if not hasattr(os, "geteuid"):          # Windows — ไม่มีเรื่องเจ้าของไฟล์แบบนี้
        return ""
    try:
        from django.conf import settings
        root = str(settings.MEDIA_ROOT)
        owner = os.stat(root).st_uid
        me = os.geteuid()
        if owner == me:
            return ""
        import pwd
        nm = pwd.getpwuid(owner).pw_name
        return ("⚠️ กำลังรันในนาม uid %d แต่ %s เป็นของ '%s'\n"
                "   ถ้าสร้างไฟล์ตอนนี้ โฟลเดอร์รูปปกจะเป็นของ uid %d แล้ว sync เที่ยงคืน\n"
                "   (รันในนาม '%s') จะเขียนรูปใหม่ไม่ได้อีกเลยแบบเงียบๆ\n"
                "   → ให้รันแบบนี้แทน:  sudo -u %s .venv/bin/python manage.py social_covers --fetch"
                % (me, root, nm, me, nm, nm))
    except Exception:
        return ""


def _item_count(side: str) -> int:
    from dashboard.models import MetaPostSnapshot, TikTokVideoSnapshot
    try:
        if side == "tiktok":
            return TikTokVideoSnapshot.objects.values("video_id").distinct().count()
        return MetaPostSnapshot.objects.values("post_id").distinct().count()
    except Exception:
        return 0


def _fetch(side: str, say) -> int:
    """ดึงเฉพาะลิงก์รูปปกแล้วโหลดไฟล์ — ไม่แตะตารางตัวเลขเลย"""
    from dashboard.services import covers
    if side == "tiktok":
        from dashboard.models import TikTokAccount
        from dashboard.services import tiktok_oauth, tiktok_sync
        n = 0
        # ★ ใช้ค่าคงที่ของโมเดล ไม่ใช่สตริงที่พิมพ์เอง
        #   เคยเขียน status="ok" ซึ่งไม่มีอยู่จริง (ของจริงคือ "active") → กรองได้ 0 ช่อง
        #   แล้วคำสั่งรายงาน "โหลดใหม่ 0" เงียบๆ เหมือนทำงานปกติ หาสาเหตุไม่เจอ
        accs = list(TikTokAccount.objects.filter(status=TikTokAccount.ACTIVE))
        if not accs:
            say("  ไม่มีช่อง TikTok ที่ใช้งานได้เลย — ยังไม่ได้เชื่อมช่อง หรือ token ถูกยกเลิก")
        for acc in accs:
            try:
                token = tiktok_oauth.access_token_for(acc.open_id)
            except Exception as e:
                say("  ช่อง %s: ขอ token ไม่ได้ (%s)" % (acc.label, str(e)[:60]))
                continue
            cursor, todo = None, []
            for _ in range(tiktok_sync.MAX_PAGES):
                j = tiktok_sync._videos_page(token, cursor)
                d = j.get("data") or {}
                for v in (d.get("videos") or []):
                    todo.append((str(v.get("id") or ""), v.get("cover_image_url") or ""))
                if not d.get("has_more") or not d.get("cursor"):
                    break
                cursor = d["cursor"]
            got = covers.save_many("tiktok", todo)
            say("  ช่อง %s: เจอ %d คลิป · โหลดใหม่ %d" % (acc.label, len(todo), got))
            n += got
        return n

    from dashboard.services import meta
    n = 0
    for pid in sorted(meta.pages()):
        pt = meta.page_token(pid)
        todo = []
        for chunk in meta.paged("/%s/posts" % pid, _token=pt,
                                fields="id,full_picture", limit=50, max_pages=20):
            for p in (chunk.get("data") or []):
                todo.append((str(p.get("id") or ""), p.get("full_picture") or ""))
        got = covers.save_many("meta", todo)
        say("  เพจ %s: เจอ %d โพสต์ · โหลดใหม่ %d" % (pid, len(todo), got))
        n += got
    return n
