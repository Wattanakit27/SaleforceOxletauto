"""สร้างตาราง "ยอดโซเชียลรายวัน" (`dash_social_daily`) ใหม่จาก snapshot

รันซ้ำได้ตลอด ไม่เบิ้ล (ลบของแพลตฟอร์มนั้นแล้วใส่ใหม่ในธุรกรรมเดียว)
    python manage.py social_rebuild [--days 120]
"""
from django.core.management.base import BaseCommand

from dashboard.services import social_daily


class Command(BaseCommand):
    help = "สร้างตารางยอดโซเชียลรายวันใหม่จากตาราง snapshot"

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=social_daily.DEFAULT_DAYS,
                            help="ย้อนหลังกี่วัน (ค่าเริ่มต้น %d)" % social_daily.DEFAULT_DAYS)

    def handle(self, *a, **o):
        res = social_daily.rebuild(o["days"])
        self.stdout.write("Facebook  %6d แถว" % res.get("meta", 0))
        self.stdout.write("TikTok    %6d แถว" % res.get("tiktok", 0))
        for e in res.get("errors") or []:
            self.stderr.write("ผิดพลาด: %s" % e)
