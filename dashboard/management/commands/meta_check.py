# -*- coding: utf-8 -*-
"""ตรวจว่า Meta token ของเรา "เอื้อมถึงบริษัทอื่น" หรือไม่ — ก.ย.69

เจ้าของทำงาน 2 บริษัท (อ๊อกเล็ตธ์ออโต้ + OSUKA) และสั่งว่า **ต้องแยกกัน ไม่ปนกัน**
แต่ token ของ Meta ออกในนามโปรไฟล์คน ไม่ใช่ในนามบริษัท → เอื้อมถึงทั้ง 2 บริษัทเสมอ
คำสั่งนี้ตอบว่า "แล้วตอนนี้แอปเราปนหรือยัง"

    python manage.py meta_check                 # ดูสถานะ
    python manage.py meta_check --suggest       # ช่วยร่างค่า META_* ให้ก๊อปลง .env
    python manage.py meta_check --out ไฟล์.txt  # เขียนไฟล์ (console ไทยเพี้ยน cp874)

⚠️ อ่านอย่างเดียว ไม่แก้อะไรทั้งฝั่ง Meta และฝั่งเรา
"""
from __future__ import annotations

import io

import requests
from django.core.management.base import BaseCommand

from dashboard.services import meta

LINE = "=" * 72


class Command(BaseCommand):
    help = "ตรวจว่า Meta token เอื้อมถึง asset ของบริษัทอื่นหรือไม่ (อ่านอย่างเดียว)"

    def add_arguments(self, parser):
        parser.add_argument("--suggest", action="store_true",
                            help="ร่างค่า META_AD_ACCOUNTS / META_PAGE_IDS ให้")
        parser.add_argument("--out", default="", help="เขียนผลลงไฟล์ (UTF-8)")

    def handle(self, *a, **o):
        buf = []
        p = buf.append

        p(LINE)
        p("ตรวจการแยกบริษัทของ Meta API")
        p(LINE)

        # ── 1. ตัว token ──────────────────────────────────────────
        try:
            t = meta.token()
        except meta.NotConfigured as e:
            p("โทเคน : ✗ %s" % e)
            p("")
            p("ยังไม่ได้ตั้ง META_ACCESS_TOKEN → ตอนนี้แอปแตะ Meta ไม่ได้เลย")
            p("ในแง่การแยกบริษัทถือว่า **ปลอดภัยที่สุด** (ไม่มีอะไรปนได้)")
            return self._out(buf, o)

        try:
            d = requests.get("https://graph.facebook.com/v21.0/debug_token",
                             params={"input_token": t, "access_token": t},
                             timeout=30).json().get("data") or {}
        except Exception as e:
            d = {"_err": str(e)}
        p("โทเคน : %s | แอป %s | เจ้าของ user %s"
          % ("ใช้ได้" if d.get("is_valid") else "✗ ใช้ไม่ได้ (%s)" % d.get("_err", "")[:40],
             d.get("application"), d.get("user_id")))
        p("        สิทธิ์ %d รายการ" % len(d.get("scopes") or []))

        # ── 2. allowlist ─────────────────────────────────────────
        r = meta.audit()
        p("")
        p("บริษัทนี้ระบุ asset ไว้:")
        p("   บัญชีโฆษณา : %s" % (", ".join("act_" + x for x in r["allowAdAccounts"]) or "— ยังไม่ระบุ —"))
        p("   เพจ         : %s" % (", ".join(r["allowPages"]) or "— ยังไม่ระบุ —"))
        if not r["configured"]:
            p("")
            p("★ ยังไม่ระบุ asset → `meta.get()` จะปฏิเสธทุกคำขอ (ปิดสนิทโดยเจตนา)")
            p("  ตั้ง META_AD_ACCOUNTS / META_PAGE_IDS ใน .env ก่อนถึงจะใช้งานได้")

        # ── 3. ของบริษัทอื่นที่ token เอื้อมถึง ───────────────────
        fa, fp = r["foreignAdAccounts"], r["foreignPages"]
        p("")
        p(LINE)
        if fa or fp:
            p("⚠️  token นี้เอื้อมถึง asset ที่ **ไม่ใช่ของบริษัทนี้**")
            p(LINE)
            for k, v in sorted(fa.items()):
                p("   บัญชีโฆษณา act_%-18s %s" % (k, v[:40]))
            for k, v in sorted(fp.items()):
                p("   เพจ        %-22s %s" % (k, v[:40]))
            p("")
            p("   นี่เป็น **เรื่องปกติของ Meta** — สิทธิ์ผูกกับโปรไฟล์คน ไม่ใช่ตัว token")
            p("   ออก token ใหม่กี่รอบก็เห็นเหมือนเดิม · แก้ได้ 2 ทางเท่านั้น:")
            p("     (ก) ถอนโปรไฟล์ตัวเองออกจาก asset ของบริษัทอื่น (ทำที่ business.facebook.com)")
            p("     (ข) ปล่อยไว้ แต่ให้โค้ดแตะไม่ได้ ← ที่ไฟล์ meta.py ทำอยู่")
            p("")
            p("   สำคัญ: ตราบใดที่ใช้ `meta.get()` ของที่ลิสต์ข้างบน **แตะไม่ได้**")
            p("          แต่ถ้าใครเขียน requests ยิง Graph API ตรง ๆ ด่านนี้ไม่ช่วยอะไรเลย")
        else:
            p("✅ token เอื้อมถึงเฉพาะ asset ของบริษัทนี้ ไม่มีของบริษัทอื่นปน")
            p(LINE)

        # ── 4. ตั้งไว้แต่เอื้อมไม่ถึง ─────────────────────────────
        if r["missingAdAccounts"] or r["missingPages"]:
            p("")
            p("⚠️  ระบุไว้ใน allowlist แต่ token เอื้อมไม่ถึง (พิมพ์ผิด / ถูกถอดสิทธิ์?)")
            for x in r["missingAdAccounts"]:
                p("   act_%s" % x)
            for x in r["missingPages"]:
                p("   เพจ %s" % x)

        for e in r["errors"]:
            p("   (ขอข้อมูลบางส่วนไม่ได้: %s)" % e[:80])

        # ── 5. ช่วยร่างค่า ───────────────────────────────────────
        if o["suggest"]:
            p("")
            p(LINE)
            p("ร่างค่าให้ — ★ ต้องตรวจเองก่อนใช้ ว่าทุกตัวเป็นของบริษัทนี้จริง")
            p(LINE)
            mine_a = sorted(set(r["reachAdAccounts"]) - set(fa))
            mine_p = sorted(set(r["reachPages"]) - set(fp))
            if not (mine_a or mine_p):     # ยังไม่เคยตั้ง → เสนอทุกตัวที่เอื้อมถึง
                p("(ยังไม่ได้ระบุ asset เลย — ด้านล่างคือ *ทุก* ตัวที่ token เอื้อมถึง")
                p(" ให้ลบบรรทัดของบริษัทอื่นออกก่อนก๊อปลง .env)")
                p("")
                for k, v in sorted(r["reachAdAccounts"].items()):
                    p("#   act_%-18s %s" % (k, v[:44]))
                for k, v in sorted(r["reachPages"].items()):
                    p("#   เพจ %-22s %s" % (k, v[:44]))
                mine_a = sorted(r["reachAdAccounts"])
                mine_p = sorted(r["reachPages"])
            p("")
            p("META_AD_ACCOUNTS=%s" % ",".join(mine_a))
            p("META_PAGE_IDS=%s" % ",".join(mine_p))

        return self._out(buf, o)

    def _out(self, buf, o):
        text = "\n".join(buf)
        if o.get("out"):
            io.open(o["out"], "w", encoding="utf-8").write(text + "\n")
            self.stdout.write("เขียนผลลง %s แล้ว" % o["out"])
        else:
            self.stdout.write(text)
