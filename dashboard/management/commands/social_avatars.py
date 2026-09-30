# -*- coding: utf-8 -*-
"""รูปโปรไฟล์ช่อง/เพจ — ดูสถานะ / ดึงมาเก็บเดี๋ยวนี้ (30 ก.ย.69)

    python manage.py social_avatars                  # มีรูปโปรไฟล์กี่ช่องแล้ว
    python manage.py social_avatars --fetch          # ดึงเดี๋ยวนี้ (ไม่ต้องรอ sync เที่ยงคืน)
    python manage.py social_avatars --fetch --side tiktok
    python manage.py social_avatars --out av.txt     # console ไทยเพี้ยน (cp874) ให้เขียนไฟล์แทน

**ทำไมต้องโหลดไฟล์มาเก็บ** — ลิงก์รูปโปรไฟล์ของ TikTok/Facebook เป็น signed URL
หมดอายุ เก็บลิงก์ลงฐานข้อมูลแล้วอีกไม่กี่ชั่วโมงก็เปิดไม่ขึ้น (แบบเดียวกับรูปปกคลิป)

**⚠️ รันด้วย root ไม่ได้บนเซิร์ฟเวอร์** — `media/` เป็นของ user `oxlet` (ตัวที่รันเว็บ+cron)
รันด้วย root แล้วโฟลเดอร์จะเกิดมาเป็นของ root → **รอบ sync เที่ยงคืนเขียนรูปไม่ได้อีกเลย
แบบเงียบๆ** · คำสั่งนี้เตือนให้ถ้าเจ้าของโฟลเดอร์ไม่ตรง
"""
import io
import os

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "ดูสถานะ/ดึงรูปโปรไฟล์ช่อง TikTok + เพจ Facebook + ช่อง YouTube"

    def add_arguments(self, p):
        p.add_argument("--fetch", action="store_true", help="ดึงรูปเดี๋ยวนี้")
        p.add_argument("--side", default="", help="tiktok | meta | youtube (ไม่ใส่ = ทุกฝั่ง)")
        p.add_argument("--out", default="", help="เขียนผลลงไฟล์ (เลี่ยง console ไทยเพี้ยน)")

    def handle(self, *a, **o):
        lines = []

        def say(s=""):
            lines.append(s)
            if not o["out"]:
                try:
                    self.stdout.write(s)
                except UnicodeEncodeError:
                    self.stdout.write(s.encode("ascii", "replace").decode())

        from dashboard.services import avatars

        w = _owner_warning()
        if w:
            say(w)
            say()

        sides = [o["side"]] if o["side"] in avatars.SIDES else list(avatars.SIDES)

        if o["fetch"]:
            say("กำลังดึงรูปโปรไฟล์…")
            for side in sides:
                try:
                    n, total, note = _fetch(side)
                    say("  %-8s ได้ %d จาก %d ช่อง%s" % (side, n, total, note))
                except Exception as e:
                    say("  %-8s ล้มเหลว: %s" % (side, str(e)[:160]))
            say()

        st = avatars.stats()
        say("มีรูปโปรไฟล์เก็บไว้แล้ว")
        for side in avatars.SIDES:
            say("  %-8s %d ช่อง" % (side, st.get(side, 0)))
        if not o["fetch"]:
            say()
            say("ยังไม่มีรูป = การ์ดใช้อักษรย่อบนวงกลมสีแทน (ไม่พัง) · ใส่ --fetch เพื่อดึงเดี๋ยวนี้")

        if o["out"]:
            with io.open(o["out"], "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            self.stdout.write("wrote %s" % o["out"])


def _fetch(side: str):
    """ดึงรูปของฝั่งนั้น → `(สำเร็จ, ทั้งหมด, หมายเหตุ)`"""
    from dashboard.services import avatars

    if side == "tiktok":
        from dashboard.models import TikTokAccount
        rows = list(TikTokAccount.objects.filter(status=TikTokAccount.ACTIVE))
        if not rows:
            return 0, 0, " — ยังไม่มีช่องที่เชื่อมไว้"
        pairs, missing = [], 0
        for a in rows:
            url = (a.profile or {}).get("avatar_url_100") or ""
            if url:
                pairs.append((a.open_id, url))
            else:
                missing += 1
        note = ""
        if missing:
            #  ลิงก์รูปมากับรอบ sync — ช่องที่ยังไม่เคย sync หลังอัปเดตนี้จะยังไม่มี
            note = " — %d ช่องยังไม่มีลิงก์รูป (รอรอบ sync เที่ยงคืน หรือ manage.py tiktok_accounts --sync)" % missing
        return avatars.save_many("tiktok", pairs), len(rows), note

    if side == "meta":
        from dashboard.services import meta
        pairs = []
        for pid in sorted(meta.pages()):
            try:
                info = meta.get("/%s" % pid, _token=meta.page_token(pid),
                                fields="picture.width(200)") or {}
                url = ((info.get("picture") or {}).get("data") or {}).get("url")
                if url:
                    pairs.append((str(pid), url))
            except Exception:
                continue
        return avatars.save_many("meta", pairs), len(meta.pages()), ""

    if side == "youtube":
        from django.conf import settings

        from dashboard.services import youtube_sync
        #  รายชื่อช่องมาจาก .env (YOUTUBE_CHANNELS) — ไม่มีฟังก์ชัน channels() ให้เรียก
        refs = list(getattr(settings, "YOUTUBE_CHANNELS", []) or [])
        pairs = []
        for ref in refs:
            try:
                ch = youtube_sync.resolve_channel(ref)
                if ch.get("avatar"):
                    pairs.append((ch["channel_id"], ch["avatar"]))
            except Exception:
                continue
        return avatars.save_many("youtube", pairs), len(refs), ""

    return 0, 0, " — ไม่รู้จักฝั่งนี้"


def _owner_warning() -> str:
    """เตือนถ้าเจ้าของโฟลเดอร์ media ไม่ใช่ user ที่รันคำสั่งนี้ (บทเรียนจาก social_covers)"""
    try:
        from django.conf import settings
        root = str(settings.MEDIA_ROOT)
        if not os.path.isdir(root) or not hasattr(os, "geteuid"):
            return ""
        owner, me = os.stat(root).st_uid, os.geteuid()
        if owner == me:
            return ""
        import pwd
        nm = lambda u: (pwd.getpwuid(u).pw_name if u is not None else "?")
        return ("⚠️ media/ เป็นของ %s แต่คำสั่งนี้รันด้วย %s\n"
                "   รันแบบนี้แทน:  sudo -u %s .venv/bin/python manage.py social_avatars --fetch"
                % (nm(owner), nm(me), nm(owner)))
    except Exception:
        return ""
