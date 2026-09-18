# -*- coding: utf-8 -*-
"""ความต้องการลูกค้า: วิเคราะห์จากแชท + จับคู่กับรถในสต็อก

    python manage.py customer_needs                      # ดูสรุปที่มีอยู่
    python manage.py customer_needs --analyze            # อ่านแชทแล้วสรุปความต้องการ (ใช้ Gemini)
    python manage.py customer_needs --analyze --limit 5 --dry-run
    python manage.py customer_needs --match              # ใครรอรถอยู่ แล้วตอนนี้มีรถตรงสเปกไหม
    python manage.py customer_needs --group              # อ่านกลุ่มจ่ายเบอร์เข้าระบบ
    python manage.py customer_needs --match --out d:\\ผล.txt

⚠️ **ไม่มีคำสั่งไหนส่งข้อความหาลูกค้า** — อ่าน + เขียนฐานข้อมูลเราเองล้วนๆ
⚠️ console ไทยเพี้ยน (cp874) → ใช้ `--out` เขียนไฟล์ UTF-8 แทน
"""
import io

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "วิเคราะห์ความต้องการลูกค้าจากแชท + จับคู่กับสต็อก (ไม่ส่งข้อความหาลูกค้า)"

    def add_arguments(self, p):
        p.add_argument("--analyze", action="store_true", help="อ่านแชทแล้วสรุปความต้องการ")
        p.add_argument("--match", action="store_true", help="จับคู่คนที่รอรถกับสต็อก")
        p.add_argument("--group", action="store_true",
                       help="อ่านกลุ่มจ่ายเบอร์ (ใบจ่ายลีด + เคส 'ไม่มีรถ')")
        p.add_argument("--limit", type=int, default=50, help="วิเคราะห์กี่คน (default 50)")
        p.add_argument("--days", type=int, default=14, help="ย้อนหลังกี่วัน (default 14)")
        p.add_argument("--force", action="store_true", help="วิเคราะห์ใหม่แม้บทสนทนาไม่เปลี่ยน")
        p.add_argument("--dry-run", action="store_true", help="วิเคราะห์ให้ดู ไม่เขียนฐานข้อมูล")
        p.add_argument("--out", help="เขียนผลลงไฟล์ (UTF-8)")

    def handle(self, *a, **o):
        from checkout.models import CustomerNeed

        lines = []
        w = lines.append

        if o["analyze"]:
            from checkout import need_extract
            if o["dry_run"]:
                w("== วิเคราะห์แบบไม่เขียนฐานข้อมูล ==")
                from checkout.models import LineProfile
                from django.utils import timezone
                since = timezone.now() - timezone.timedelta(days=o["days"])
                qs = (LineProfile.objects.filter(is_employee=False, last_seen__gte=since)
                      .order_by("-last_seen")[:o["limit"]])
                for p in qs:
                    text, _fp = need_extract.transcript(p.user_id)
                    if not text.strip():
                        continue
                    try:
                        d = need_extract._ask(text)
                    except Exception as e:
                        w("  %-18s พลาด: %s" % (p.show_name, e))
                        continue
                    if not d.get("has_need"):
                        w("  %-18s (ไม่ได้ถามหารถ)" % p.show_name)
                        continue
                    w("  %-18s %s | งบ %s | %s (%s)" % (
                        p.show_name, d.get("car_model") or d.get("car_text") or "?",
                        d.get("budget_max") or "-", d.get("status"), d.get("confidence")))
            else:
                res = need_extract.run(limit=o["limit"], force=o["force"], days=o["days"])
                w("== วิเคราะห์ความต้องการจากแชท ==")
                for k in ("ดู", "มีความต้องการ", "ไม่มี", "รอรถ", "พลาด"):
                    w("  %-14s %s" % (k, res[k]))
                for e in res["errors"][:5]:
                    w("    ! " + e)

        if o["group"]:
            from checkout import leadgroup
            st = leadgroup.ingest()
            w("== อ่านกลุ่มจ่ายเบอร์ ==")
            for k, v in st.items():
                w("  %-20s %s" % (k, v))
            w("  (\"ไม่มีรถ\" = ลูกค้าหารถที่เรายังไม่มี → เก็บรอไว้ พอรถเข้าจะขึ้นในพาเนล)")

        if o["match"]:
            from checkout import need_match
            rows = need_match.scan()
            w("")
            w("== ลูกค้าที่รอรถ แล้วตอนนี้มีรถตรงสเปก: %d ราย ==" % len(rows))
            w("   (รายการนี้ไว้ให้คนของเราตัดสินใจเอง — ระบบไม่ได้ทักลูกค้า)")
            for r in rows:
                w("")
                w("  ลูกค้า : %s%s" % (
                    r["customer"],
                    "  [ลีด %s]" % r["leadCode"] if r.get("leadCode") else ""))
                if not r["user_id"] and r.get("contact"):
                    w("  ติดต่อ : %s  (ไม่ได้ทักผ่าน LINE OA — ต้องโทร)" % r["contact"])
                w("  อยากได้: %s%s%s" % (r["want"],
                                        " · งบ %s" % f"{r['budget']:,}" if r["budget"] else "",
                                        " · เคยปิดเพราะ %s" % r["why"] if r["why"] else ""))
                for c in r["cars"]:
                    w("     → %s %s %s %s  %s" % (
                        c["code"], c["brand"], c["model"], c["year"] or "",
                        ("%s บ." % f"{c['price']:,}") if c["price"] else "(ยังไม่ใส่ราคา)"))

        if not o["analyze"] and not o["match"] and not o["group"]:
            w("== ความต้องการลูกค้าที่เก็บไว้ ==")
            total = CustomerNeed.objects.count()
            w("  ทั้งหมด        %d" % total)
            w("  รอรถอยู่       %d" % CustomerNeed.objects.filter(waiting=True).count())
            for k, label in CustomerNeed.STATUS_CHOICES:
                n = CustomerNeed.objects.filter(status=k).count()
                if n:
                    w("  %-14s %d" % (label, n))
            w("")
            w("  RJ แยกตามเหตุผล:")
            for k, label in CustomerNeed.REJECT_CHOICES:
                n = CustomerNeed.objects.filter(reject_kind=k).count()
                if n:
                    tag = " ← รอรถได้" if k in CustomerNeed.WAITABLE else ""
                    w("    %-22s %d%s" % (label, n, tag))
            if not total:
                w("  (ยังไม่มี — ลองสั่ง --analyze)")

        text = "\n".join(lines)
        if o["out"]:
            io.open(o["out"], "w", encoding="utf-8").write(text + "\n")
            self.stdout.write("เขียนผลลง %s แล้ว (%d บรรทัด)" % (o["out"], len(lines)))
        else:
            self.stdout.write(text)
