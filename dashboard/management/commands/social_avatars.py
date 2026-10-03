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
        got, asked, failed, why = 0, 0, 0, ""
        for a in rows:
            url = (a.profile or {}).get("avatar_url_100") or ""
            ok = bool(url) and avatars.save("tiktok", a.open_id, url)
            if not ok:
                #  ★ ไม่มีลิงก์ **หรือลิงก์หมดอายุแล้ว** → ขอ TikTok ใหม่เดี๋ยวนี้
                #    (ลิงก์รูปเป็น signed URL — ของเดิมเช็คแค่ "ไม่มีลิงก์" จึงไม่เคยลองใหม่
                #     เลยได้ 0 แบบเงียบๆ ถ้ารันหลังรอบ sync ไปไม่กี่ชั่วโมง)
                #    ขอแค่ข้อมูลช่อง **ไม่ดึงคลิปใหม่ทั้ง 600+ คลิป** ซึ่งกินโควต้าเปล่า
                fresh, err = _tiktok_avatar(a)
                asked += 1
                if fresh and avatars.save("tiktok", a.open_id, fresh):
                    ok = True
                else:
                    failed += 1
                    if err and not why:
                        why = err          # บอกสาเหตุแรกที่เจอ ดีกว่านับเฉยๆ แล้วให้เดาเอง
            if ok:
                got += 1
        note = ""
        if asked:
            note = " (ขอลิงก์ใหม่จาก TikTok %d ช่อง%s)" % (
                asked, (" · ไม่สำเร็จ %d — %s" % (failed, why)) if failed else "")
        return got, len(rows), note

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


def _tiktok_avatar(acc):
    """ขอลิงก์รูปโปรไฟล์ของช่องนั้นจาก TikTok โดยตรง + จำไว้ในทะเบียน → `(ลิงก์, เหตุที่ไม่ได้)`

    ใช้ตอนทะเบียนยังไม่มีลิงก์ หรือลิงก์ที่เก็บไว้หมดอายุแล้ว
    · ขอเฉพาะข้อมูลช่อง — **ไม่แตะรายการคลิป** จึงเบากว่าสั่ง sync ใหม่ทั้งช่องมาก

    ★★ ขอ field ได้เท่าที่ **สิทธิ์ของช่องนั้น** ครอบคลุม — TikTok **ปฏิเสธทั้งคำขอ**
       ถ้าขอเกินสิทธิ์ (กติกาเดียวกับ `tiktok_oauth._fetch_user` ที่ gate ไว้แล้ว)
       · `username` อยู่ใต้ `user.info.profile` ซึ่ง **ไม่ได้อยู่ในค่าตั้งต้น**
         (`user.info.basic,video.list`) → ขอพ่วงไปด้วยทีเดียว = ได้ศูนย์ทุกช่อง
         ซึ่งคือเคส "TikTok 0/10" ที่ฟังก์ชันนี้ตั้งใจมาแก้พอดี
    """
    import requests

    from dashboard.services import tiktok_oauth, tiktok_sync

    try:
        token = tiktok_oauth.access_token_for(acc.open_id)
    except Exception as e:                       # token ถอดรหัสไม่ได้ (เปลี่ยน SECRET_KEY ฯลฯ)
        return "", "อ่าน token ไม่ได้ (%s)" % str(e)[:60]
    if not token:
        return "", "ไม่มี token ที่ใช้ได้ — ให้เจ้าของช่องกดอนุญาตใหม่"

    fields = ["open_id", "avatar_url_100", "display_name"]
    if "user.info.profile" in set((acc.scope or "").split(",")):
        fields.append("username")

    try:
        r = requests.get(tiktok_sync.USER_URL, params={"fields": ",".join(fields)},
                         headers={"Authorization": "Bearer " + token}, timeout=15)
        j = r.json() if r.content else {}
    except (requests.RequestException, ValueError) as e:
        return "", "ต่อ TikTok ไม่ได้ (%s)" % str(e)[:60]
    if not isinstance(j, dict):
        j = {}

    #  ★ เช็คคำตอบจริง — ของเดิม `except Exception: return ""` ครอบทั้งฟังก์ชัน
    #    ทำให้ "ขอเกินสิทธิ์" / "token ถูกเพิกถอน" / "เน็ตล่ม" หน้าตาเหมือนกันหมด
    err = j.get("error") or {}
    code = str(err.get("code") or "")
    if r.status_code != 200 or (code and code != "ok"):
        return "", "TikTok ตอบ %s %s %s" % (r.status_code, code, str(err.get("message") or "")[:70])

    u = (j.get("data") or {}).get("user") or {}
    url = u.get("avatar_url_100") or ""
    if url:
        prof = dict(acc.profile or {})
        prof["avatar_url_100"] = url
        upd = ["profile"]
        for k in ("display_name", "username"):
            if u.get(k):
                prof[k] = u[k]
        acc.profile = prof
        if u.get("username"):
            acc.username = str(u["username"])[:120]
            upd.append("username")
        acc.save(update_fields=upd)
    return url, "" if url else "TikTok ไม่ได้ส่งลิงก์รูปมา"

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
