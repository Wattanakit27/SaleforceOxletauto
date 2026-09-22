# -*- coding: utf-8 -*-
"""แตกตัวเลขจาก actions JSON + สร้างตารางยอดโฆษณารายวัน (`dash_ads_daily`) ใหม่

    python manage.py ads_rebuild                 # แตกคอลัมน์ + สร้างตารางรายวันใหม่
    python manage.py ads_rebuild --days 365
    python manage.py ads_rebuild --show          # โชว์ยอดรวม + ต้นทุนหลังสร้างเสร็จ

ใช้ตอน: deploy ครั้งแรก (แถวเก่ามีแต่ JSON ยังไม่มีคอลัมน์) หรือเวลาสงสัยว่าตัวเลขเพี้ยน
— ตารางนี้เป็นข้อมูล derived ลบทิ้งแล้วสร้างใหม่ได้เสมอ (ต้นฉบับคือ `dash_meta_ad_daily`)
"""
import io

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "สร้างตารางยอดโฆษณารายวันใหม่จากข้อมูลดิบ"

    def add_arguments(self, p):
        p.add_argument("--days", type=int, default=0, help="ย้อนหลังกี่วัน (ไม่ใส่ = ค่าปกติ 120)")
        p.add_argument("--show", action="store_true", help="โชว์ยอดรวม + ต้นทุนหลังสร้างเสร็จ")
        p.add_argument("--out", default="", help="เขียนผลลงไฟล์")

    def handle(self, *a, **o):
        from dashboard.services import ads_stats as A

        lines = []
        say = lines.append

        r1 = A.backfill()
        say("แตกตัวเลขจาก actions JSON: ตรวจ %s แถว" % r1.get("scanned", 0))

        days = o["days"] or A.DEFAULT_DAYS
        r2 = A.rebuild_daily(days)
        say("สร้างตารางรายวัน (ย้อนหลัง %d วัน): %s แถว" % (days, r2.get("rows", 0)))

        if o["show"]:
            from dashboard.models import AdsDaily
            from django.db.models import Max, Min
            g = AdsDaily.objects.aggregate(a=Min("date"), b=Max("date"))
            if not g["a"]:
                say("")
                say("ยังไม่มีข้อมูลโฆษณาเลย")
            else:
                d = A.stats(g["a"].isoformat(), g["b"].isoformat())
                t, c = d["total"], d["cost"]
                say("")
                say("ช่วงที่มีข้อมูล : %s ถึง %s (%d วัน)"
                    % (g["a"].strftime("%d/%m/%Y"), g["b"].strftime("%d/%m/%Y"),
                       d["coverage"]["haveDays"]))
                say("ใช้เงิน        : %s บาท" % "{:,.2f}".format(t["spend"]))
                say("เริ่มแชท       : %s  (ตอบกลับ %s)" % ("{:,}".format(t["chats"]),
                                                            "{:,}".format(t["chats_replied"])))
                say("ต้นทุนต่อแชท   : %s บาท   <- เงินทั้งหมด หาร แชททั้งหมด" % c["perChat"])
                say("ลีด            : %s  (ต้นทุน %s บาท/ลีด)" % ("{:,}".format(t["leads"]), c["perLead"]))
                say("คลิกลิงก์      : %s" % "{:,}".format(t["link_clicks"]))
                say("CPM / CTR      : %s บาท / %s%%" % (c["cpm"], c["ctr"]))

        text = "\n".join(lines)
        if o["out"]:
            with io.open(o["out"], "w", encoding="utf-8") as f:
                f.write(text + "\n")
            self.stdout.write("wrote %s" % o["out"])
        else:
            for ln in lines:
                try:
                    self.stdout.write(ln)
                except UnicodeEncodeError:      # console ไทยเพี้ยน (cp874)
                    self.stdout.write(ln.encode("ascii", "replace").decode("ascii"))
