"""ส่ง/ดูตัวอย่าง ข้อความเตือนงานจัดซื้อ (รับซื้อรถ)

    python manage.py notify_purchase --dry-run              # ดูข้อความเฉยๆ ไม่ส่ง
    python manage.py notify_purchase --to <LINE user id>    # ส่งทุกข้อความเข้าไอดีเดียว (ทดสอบ)

ยังไม่ผูกกับ cron — ใช้ทดสอบ/ดูหน้าตาก่อนเปิดใช้จริง
"""
from django.conf import settings
from django.core.management.base import BaseCommand

from dashboard.services import purchase_followup as PF


class Command(BaseCommand):
    help = "ส่งข้อความเตือนงานจัดซื้อเข้า LINE (หรือ --dry-run เพื่อดูเฉยๆ)"

    def add_arguments(self, p):
        p.add_argument("--to", help="LINE user id ปลายทาง (ทดสอบ — ส่งทุกข้อความเข้าไอดีนี้)")
        p.add_argument("--dry-run", action="store_true", help="ไม่ส่ง แค่พิมพ์ข้อความ")
        p.add_argument("--days", type=int, default=PF.LOOKBACK_DAYS,
                       help="ย้อนหลังกี่วัน (default %d)" % PF.LOOKBACK_DAYS)
        p.add_argument("--max", type=int, default=PF.MAX_CARS,
                       help="สูงสุดกี่คันต่อคน (default %d)" % PF.MAX_CARS)

    def handle(self, *args, **o):
        cases = PF.fetch_open_cases(days=o["days"])
        if not cases:
            self.stdout.write("ไม่มีเคสค้างในช่วง %d วัน (หรืออ่านชีตไม่ได้)" % o["days"])
            return
        msgs = PF.build_messages(cases, max_cars=o["max"])
        parts = list(msgs["owner"])
        if msgs["admin"]:
            parts.append(("แอดมิน (สรุป)", msgs["admin"]))

        self.stdout.write("เคสค้างทั้งหมด %d · จะส่ง %d ข้อความ" % (len(cases), len(parts)))
        for who, txt in parts:
            self.stdout.write("")
            self.stdout.write("===== %s =====" % who)
            self.stdout.write(txt)

        if o["dry_run"]:
            self.stdout.write(self.style.WARNING("(dry-run — ไม่ได้ส่งจริง)"))
            return
        target = (o.get("to") or "").strip()
        if not target:
            self.stdout.write(self.style.ERROR("ต้องใส่ --to <LINE user id> หรือ --dry-run"))
            return
        token = (getattr(settings, "LINE_CHANNEL_ACCESS_TOKEN", "") or "").strip()
        if not token:
            self.stdout.write(self.style.ERROR("ยังไม่ได้ตั้ง LINE_CHANNEL_ACCESS_TOKEN"))
            return
        from dashboard.services.line_notify import push_line_message
        ok = 0
        for who, txt in parts:
            code, resp = push_line_message(target, [{"type": "text", "text": txt}], token)
            if code == 200:
                ok += 1
            else:
                self.stdout.write(self.style.ERROR(
                    "ส่ง '%s' ไม่สำเร็จ: HTTP %s %s" % (who, code, str(resp)[:150])))
        self.stdout.write(self.style.SUCCESS("ส่งสำเร็จ %d/%d ข้อความ" % (ok, len(parts))))
