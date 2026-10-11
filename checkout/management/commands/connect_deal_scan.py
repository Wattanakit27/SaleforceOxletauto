"""จัดประเภทลีดย้อนหลัง: ลีดรับซื้อรถ (ลูกค้าอยากขายรถให้เรา) / มีรถเทิร์น — ★ 11 ต.ค.69

    python manage.py connect_deal_scan                    # ดูเฉยๆ (ไม่เขียนอะไร)
    python manage.py connect_deal_scan --apply            # บันทึกจริง
    python manage.py connect_deal_scan --days 60 --out ผล.txt

ทำไมต้องมี: ตัวจับ (`lead_keywords.deal_kind`) ทำงานตอนข้อความใหม่เข้า/ตอนเปิดแชท → แชทที่คุยกันไปแล้ว
ก่อน deploy (เช่น ลูกค้าส่งรูปรถมาแล้วแอดมินตอบว่า "จะประสานงานให้ฝ่ายจัดซื้อติดต่อกลับ") ยังค้างอยู่ในคิวลีดขาย
จนกว่าจะมีคนเปิดแชท → รันครั้งเดียวหลัง deploy

ไม่แตะแชทที่คนตั้งประเภทไว้แล้ว / มีเลขลีดขาย / ติ๊กรับ lead / ส่งจัดซื้อแล้ว · รายงานอ้างแถวด้วย ChatOwner.id
**ไม่พิมพ์ LINE user id / เบอร์ลงรายงาน**
"""
import re

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "จัดประเภทลีดย้อนหลัง: ลีดรับซื้อรถ / มีรถเทิร์น (ไม่ใส่ --apply = ดูเฉยๆ)"

    def add_arguments(self, p):
        p.add_argument("--apply", action="store_true", help="บันทึกจริง (ไม่ใส่ = ดูเฉยๆ)")
        p.add_argument("--days", type=int, default=30, help="แชทที่ลูกค้าทักภายในกี่วัน (ค่าตั้งต้น 30)")
        p.add_argument("--out", help="เขียนผลลงไฟล์ UTF-8")

    def handle(self, *a, **o):
        from checkout import connect as C

        L = []
        add = L.append
        add("โหมด: %s · แชทที่ลูกค้าทักภายใน %d วัน" % ("บันทึกจริง" if o["apply"] else "ดูเฉยๆ (ใส่ --apply เพื่อบันทึก)",
                                                        o["days"]))
        r = C.scan_deals(days=o["days"], apply=o["apply"])
        add("ตรวจ %d แชท · เป็นลีดรับซื้ออยู่แล้ว %d · %s ลีดรับซื้อเพิ่ม %d · มีรถเทิร์น (ยังเป็นลีดขาย) %d"
            % (r["checked"], r["already"], "จัดเป็น" if o["apply"] else "จะจัดเป็น", r["buy"], r["trade"]))
        for x in r["rows"]:
            why = re.sub(r"\d[\d\s-]{7,}\d", "#เบอร์#", x["why"] or "")     # คำที่จับได้อาจมีเบอร์ลูกค้าติดมา
            add("  #%d %s %s — %s" % (x["id"], "รับซื้อ" if x["kind"] == "buy" else "เทิร์น ",
                                     "FB  " if x["src"] == "fb" else "LINE", why))
        report = "\n".join(L)
        if o.get("out"):
            with open(o["out"], "w", encoding="utf-8") as f:
                f.write(report)
            self.stdout.write("wrote -> %s" % o["out"])
        else:
            self.stdout.write(report)
