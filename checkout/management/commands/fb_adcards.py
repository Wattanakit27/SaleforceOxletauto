# -*- coding: utf-8 -*-
"""การ์ดโฆษณาในแชท Facebook → ช่อง ADS + ad id ของลีด (checkout/fb_ads.py · ★ 19 ต.ค.69)

    manage.py fb_adcards                     ดูเฉยๆ: แชท FB 7 วันที่มีการ์ดโฆษณาแล้ว / จับคู่ ad id ได้แล้ว
    manage.py fb_adcards --apply             ครั้งเดียวหลัง deploy: ถาม Facebook การ์ดโฆษณาของแชทที่เก็บไว้ก่อนมีฟีเจอร์
                                             (ข้อความ 25 อันล่าสุดต่อห้อง) แล้วเติมช่อง ADS + ad id (ช่องที่คนแก้แล้วไม่แตะ)
    manage.py fb_adcards --apply --days 14   ย้อนกี่วัน (ค่าตั้งต้น 7)
    manage.py fb_adcards --apply --rematch   จับคู่ชื่อโฆษณาใหม่ให้แชทที่จับคู่ไปแล้วด้วย (หลังแก้วิธีจับคู่)
"""
import io
import json

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "เติมการ์ดโฆษณา/ad id ให้แชท Facebook ที่ลูกค้ามาจากโฆษณา"

    def add_arguments(self, p):
        p.add_argument("--apply", action="store_true")
        p.add_argument("--days", type=int, default=7)
        p.add_argument("--limit", type=int, default=300)
        p.add_argument("--rematch", action="store_true")
        p.add_argument("--out", default="")

    def handle(self, *a, **o):
        from datetime import timedelta

        from django.utils import timezone

        from checkout import fb_ads
        from checkout.models import ChatLead
        lines = []
        if o["apply"]:
            r = fb_ads.backfill(days=o["days"], limit=o["limit"], rematch=o["rematch"])
            lines.append("เติมแล้ว: %s" % json.dumps(r, ensure_ascii=False))
        since = timezone.now() - timedelta(days=o["days"])
        qs = ChatLead.objects.filter(chat__fb_profile__isnull=False, chat__last_in_at__gte=since)
        n_all = qs.count()
        n_card = qs.filter(auto__has_key=fb_ads.CARD_KEY).count()
        n_id = qs.exclude(ad_id="").count()
        lines.append("แชท FB %d วัน: %d · มีการ์ดโฆษณา %d · จับคู่ ad id ได้ %d" % (o["days"], n_all, n_card, n_id))
        hows = {}
        for a in qs.filter(auto__has_key=fb_ads.CARD_KEY).values_list("auto", flat=True)[:500]:
            h = ((a or {}).get(fb_ads.CARD_KEY) or {}).get("how") or "-"
            hows[h] = hows.get(h, 0) + 1
        lines.append("  วิธีจับคู่: %s (exact = webhook บอก ad id · unique = ชื่อตรงตัวเดียว · spend = ชื่อซ้ำหลายตัว เลือกตัวที่ใช้เงินมากสุด · none = ยังหาไม่เจอ)"
                     % json.dumps(hows, ensure_ascii=False))
        for l in qs.exclude(ad_id="").order_by("-updated_at")[:15]:
            ad = (l.auto or {}).get(fb_ads.CARD_KEY) or {}
            lines.append("  แชท #%s · ADS \"%s\" → %s (%s)" % (l.chat_id, l.ads, l.ad_name, ad.get("how") or ""))
        text = "\n".join(lines)
        if o["out"]:
            io.open(o["out"], "w", encoding="utf-8").write(text + "\n")
            self.stdout.write("เขียนลง %s แล้ว" % o["out"])
        else:
            self.stdout.write(text)
