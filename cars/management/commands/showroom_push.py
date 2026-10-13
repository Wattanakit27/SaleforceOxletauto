"""ส่งสถานะ Active ของรถไปเว็บโชว์รูม Oxlet แล้วบันทึกผลจริง (ปุ่ม Active · 13 ต.ค.69)

    python manage.py showroom_push                 # ดูเฉยๆ ว่าจะส่งรถคันไหน (ไม่ยิงเน็ต)
    python manage.py showroom_push --apply         # ส่งจริง + บันทึกว่าขึ้นเว็บอยู่ไหม
    python manage.py showroom_push --apply --code CB-0012
    python manage.py showroom_push --apply --errors # ส่งซ้ำเฉพาะคันที่ส่งไม่สำเร็จรอบก่อน

ใช้ตอน:
  - หลัง deploy ครั้งแรก — migration นับรถที่เคยขึ้นเว็บเป็น Active ให้แล้ว แต่ยังไม่รู้ว่าเว็บมีประกาศจริงไหม
    รันคำสั่งนี้ครั้งเดียว → ป้ายลูกโลกในบอร์ดบอกสถานะจริง
  - webhook ล่ม/เว็บโชว์รูมปิดปรับปรุง แล้วอยากส่งซ้ำ
ส่งเฉพาะรถที่ Active และยังไม่ขาย · รถที่ไม่ Active ไม่ส่ง (ไม่สร้างประกาศอยู่แล้ว)
"""
from django.core.management.base import BaseCommand

from cars import showroom_sync
from cars.models import Car


class Command(BaseCommand):
    help = "ส่งสถานะ Active ของรถไปเว็บโชว์รูม Oxlet แล้วบันทึกผลจริง"

    def add_arguments(self, p):
        p.add_argument("--apply", action="store_true", help="ส่งจริง (ไม่ใส่ = ดูเฉยๆ)")
        p.add_argument("--code", help="ส่งคันเดียว (รหัสรถ)")
        p.add_argument("--errors", action="store_true", help="เฉพาะคันที่ส่งไม่สำเร็จรอบก่อน")
        p.add_argument("--out", help="เขียนผลลงไฟล์ (UTF-8) แทนพิมพ์ลงจอ")

    def handle(self, *a, **o):
        lines = []
        say = lines.append
        qs = Car.objects.filter(web_active=True, deleted_at__isnull=True).exclude(status="sold").order_by("code")
        if o.get("code"):
            qs = Car.objects.filter(code=o["code"].strip())
        if o.get("errors"):
            qs = qs.exclude(web_sync_error="")
        cars = list(qs)
        say("รถที่จะส่ง: %d คัน" % len(cars))
        if not showroom_sync.is_configured():
            say("⚠ ยังไม่ได้ตั้ง SHOWROOM_WEBHOOK_URL / STOCK_SYNC_SECRET — ส่งไม่ได้")
        if not o.get("apply"):
            for c in cars:
                say("  %-9s %-10s %-22s %s" % (c.code, c.plate or "-", c.stage_name[:22], "Active" if c.web_active else "ไม่ Active"))
            say("(ดูเฉยๆ — ใส่ --apply เพื่อส่งจริง)")
        else:
            n = {"live": 0, "wait": 0, "error": 0}
            for c in cars:
                res = showroom_sync.push_showroom(c, why="คำสั่ง showroom_push")
                if res.get("unconfigured"):
                    say("หยุด: ยังไม่ได้ตั้งค่าการเชื่อมเว็บโชว์รูม")
                    break
                if not res.get("ok"):
                    n["error"] += 1
                    say("  ✗ %s %s — %s" % (c.code, c.plate or "", res.get("error", "")))
                elif res.get("listed"):
                    n["live"] += 1
                    say("  ✓ %s %s ขึ้นเว็บอยู่%s" % (c.code, c.plate or "", " (สร้างประกาศใหม่)" if res.get("created") else ""))
                else:
                    n["wait"] += 1
                    say("  · %s %s ยังไม่ขึ้นเว็บ (%s)" % (c.code, c.plate or "", res.get("action") or "-"))
            say("สรุป: ขึ้นเว็บอยู่ %(live)d · ยังไม่ขึ้น %(wait)d · ส่งไม่สำเร็จ %(error)d" % n)
        text = "\n".join(lines)
        if o.get("out"):
            with open(o["out"], "w", encoding="utf-8") as f:
                f.write(text + "\n")
            self.stdout.write("เขียนผลลง %s แล้ว" % o["out"])
        else:
            self.stdout.write(text)
