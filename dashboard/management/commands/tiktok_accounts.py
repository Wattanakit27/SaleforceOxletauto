# -*- coding: utf-8 -*-
"""จัดการช่อง TikTok ที่เชื่อมกับระบบ — ก.ย.69

    python manage.py tiktok_accounts                          # ดูช่องที่เชื่อมแล้ว + สถานะ
    python manage.py tiktok_accounts --link "ช่องA" --link "ช่องB" ...
                                                              # สร้างลิงก์ขออนุญาต 1 ลิงก์ต่อช่อง
    python manage.py tiktok_accounts --links-file ช่อง.txt     # ชื่อช่องบรรทัดละ 1 ชื่อ
    python manage.py tiktok_accounts --sync                   # ดึงยอดคลิปทุกช่องเดี๋ยวนี้ (รอจนเสร็จ)
    python manage.py tiktok_accounts --out ผล.txt             # เขียนไฟล์ (console ไทยเพี้ยน cp874)

ลิงก์ใช้ได้ **ครั้งเดียว** และหมดอายุใน 7 วัน · ส่งให้เจ้าของช่องแต่ละช่องเปิดแล้วกดอนุญาต
→ TikTok พากลับมาที่ /api/tiktok/webhook แล้วระบบเก็บ token ให้เอง
⚠️ ลิงก์ใช้ได้เฉพาะบนเซิร์ฟเวอร์จริง (Redirect URI ลงทะเบียนเป็นโดเมนจริง)
"""
from __future__ import annotations

import io

from django.core.management.base import BaseCommand

LINE = "=" * 76


class Command(BaseCommand):
    help = "ดู/เชื่อมช่อง TikTok · สร้างลิงก์ขออนุญาตรายช่อง · ดึงยอดคลิปเดี๋ยวนี้"

    def add_arguments(self, p):
        p.add_argument("--link", action="append", default=[], help="ชื่อช่อง (ใส่ซ้ำได้หลายช่อง)")
        p.add_argument("--links-file", default="", help="ไฟล์ชื่อช่อง บรรทัดละ 1 ชื่อ")
        p.add_argument("--sync", action="store_true", help="ดึงยอดคลิปทุกช่องเดี๋ยวนี้")
        p.add_argument("--out", default="", help="เขียนผลลงไฟล์ (UTF-8)")

    def handle(self, *a, **o):
        from dashboard.models import TikTokAccount
        from dashboard.services import tiktok_oauth, tiktok_sync

        buf = []
        p = buf.append
        p(LINE)
        p("TikTok — client key %s · secret %s" % (
            "ตั้งแล้ว" if tiktok_oauth.client_key() else "✗ ยังไม่ตั้ง",
            "ตั้งแล้ว" if tiktok_oauth.client_secret() else "✗ ยังไม่ตั้ง"))
        p("redirect URI : %s" % tiktok_oauth.redirect_uri())
        p("สิทธิ์ที่ขอ   : %s" % tiktok_oauth.scopes())
        if "user.info.stats" not in tiktok_oauth.scopes():
            p("               (ไม่มี user.info.stats = ไม่ได้ยอดผู้ติดตาม/ไลก์รวมของช่อง ได้แค่ยอดรายคลิป)")
        p(LINE)

        labels = [x.strip() for x in o["link"] if x.strip()]
        if o["links_file"]:
            labels += [l.strip() for l in io.open(o["links_file"], encoding="utf-8") if l.strip()]
        if labels:
            p("ลิงก์ขออนุญาต (ใช้ได้ครั้งเดียว · หมดอายุ %d วัน) — ส่งให้เจ้าของแต่ละช่อง"
              % tiktok_oauth.STATE_TTL_DAYS)
            p("")
            for lb in labels:
                try:
                    p("■ %s" % lb)
                    p("  %s" % tiktok_oauth.make_link(lb, "manage.py"))
                except tiktok_oauth.TikTokError as e:
                    p("  ✗ %s" % e)
                    break
                p("")
            p(LINE)

        if o["sync"]:
            p("ดึงยอดคลิปทุกช่อง...")
            r = tiktok_sync.run("manual", "manage.py")
            p("  %s · %s คลิป · %s วิ" % ("สำเร็จ" if r.get("ok") else "มีปัญหา",
                                         r.get("videos", 0), int(r.get("ms", 0) / 1000)))
            for name, n in (r.get("accounts") or {}).items():
                p("    %-30s %s คลิป" % (name[:30], n))
            for e in (r.get("errors") or []) + ([r["error"]] if r.get("error") else []):
                p("  ✗ %s" % e)
            p(LINE)

        accs = list(TikTokAccount.objects.all())
        p("ช่องที่เชื่อมแล้ว %d ช่อง" % len(accs))
        for a in accs:
            p("  %-24s %-22s %-18s สิทธิ์: %s" % ((a.label or "-")[:24], (a.display_name or "-")[:22],
                                               a.get_status_display(), a.scope or "-"))
            if a.last_error:
                p("      ✗ %s" % a.last_error[:120])
        text = "\n".join(buf)
        if o["out"]:
            io.open(o["out"], "w", encoding="utf-8").write(text + "\n")
            self.stdout.write("เขียนผลลง %s แล้ว" % o["out"])
        else:
            self.stdout.write(text)
