# -*- coding: utf-8 -*-
"""รายงานโซเชียล — ดูได้ทุกช่วงเวลา (23 ก.ย.69 · เจ้าของขอ)

    python manage.py social_report                          # ภาพรวมทุกช่วงเวลาในหน้าเดียว
    python manage.py social_report --period 7d               # ลงรายละเอียดช่วงเดียว
    python manage.py social_report --from 2026-09-01 --to 2026-09-23
    python manage.py social_report --out รายงาน.txt          # เขียนไฟล์ (console ไทยเพี้ยน cp874)
    python manage.py social_report --period month --csv out.csv

ช่วงที่รองรับ: `today` วันนี้ · `7d` 7 วันย้อนหลัง · `week` สัปดาห์นี้ (จันทร์→วันนี้) ·
`month` เดือนนี้ · `year` ปีนี้ · `all` ทั้งหมดเท่าที่เก็บมา · `range` กำหนดเอง (--from/--to)

★ **หัวใจของรายงานนี้คือบอกว่า "ตัวเลขนี้มาจากข้อมูลกี่วัน"** — ระบบเพิ่งเริ่มเก็บ 19 ก.ย.69
  ถ้าโชว์ตัวเลขเฉยๆ คนอ่านจะนึกว่า "ทั้งปีได้เท่านี้เอง?" ทั้งที่จริงคือยังไม่มีข้อมูล
  (บทเรียนเดิม: เจ้าของเคยทักว่า "เมื่อวาน วันก่อน วันนี้ เท่ากันหมดเลย" ซึ่งไม่ใช่บั๊ก
   แต่เพราะมีข้อมูลวันเดียว — ต้องเขียนกำกับเสมอ)

★ **ยอดย้อนหลังสร้างใหม่ไม่ได้** — snapshot คือการจดยอด ณ วันนั้น ย้อนไปจดไม่ได้
  ยกเว้น 2 อย่างที่ Facebook ให้ย้อนหลังเอง: ยอดระดับเพจ (~30 วัน) และค่าโฆษณา
"""
import csv
import io
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count, Max, Min, Sum

PERIODS = ["today", "7d", "week", "month", "year", "all"]
PERIOD_NAME = {"today": "วันนี้", "7d": "7 วันย้อนหลัง", "week": "สัปดาห์นี้",
               "month": "เดือนนี้", "year": "ปีนี้", "all": "ทั้งหมดเท่าที่เก็บมา",
               "range": "กำหนดเอง"}
PLAT_NAME = {"meta": "Facebook", "tiktok": "TikTok", "youtube": "YouTube"}


def _n(v) -> str:
    return "{:,}".format(int(v or 0))


class Command(BaseCommand):
    help = "รายงานยอดโซเชียลตามช่วงเวลา (วันนี้ / 7 วัน / สัปดาห์ / เดือน / ปี / กำหนดเอง)"

    def add_arguments(self, p):
        p.add_argument("--period", choices=PERIODS + ["range"], default="",
                       help="ไม่ใส่ = โชว์ทุกช่วงเปรียบเทียบกัน")
        p.add_argument("--from", dest="dfrom", default="", help="YYYY-MM-DD")
        p.add_argument("--to", dest="dto", default="", help="YYYY-MM-DD")
        p.add_argument("--top", type=int, default=10, help="โชว์โพสต์/คลิปยอดนิยมกี่อัน")
        p.add_argument("--out", default="", help="เขียนผลลงไฟล์")
        p.add_argument("--csv", default="", help="เขียนยอดรายวันเป็น CSV")

    # ── ช่วงเวลา ────────────────────────────────────────────────
    def _range(self, key, today, first, last):
        """คืน (วันเริ่ม, วันจบ) ของแต่ละช่วง · first/last = วันแรก-วันสุดท้ายที่มีข้อมูลจริง"""
        if key == "today":
            return today, today
        if key == "7d":
            return today - timedelta(days=6), today
        if key == "week":
            return today - timedelta(days=today.weekday()), today      # จันทร์ → วันนี้
        if key == "month":
            return today.replace(day=1), today
        if key == "year":
            return today.replace(month=1, day=1), today
        return (first or today), (last or today)                        # all

    def handle(self, *a, **o):
        from dashboard.models import MetaAdDaily, MetaPageDaily, SocialDaily
        from dashboard.services.meta_sync import _bkk_now

        self.lines = []
        say = self.lines.append
        today = _bkk_now().date()

        agg = SocialDaily.objects.aggregate(a=Min("date"), b=Max("date"))
        first, last = agg["a"], agg["b"]

        say("=" * 78)
        say("  รายงานโซเชียล  ·  ข้อมูล ณ %s (เวลาไทย)" % _bkk_now().strftime("%d/%m/%Y %H:%M"))
        say("=" * 78)
        if not first:
            say("")
            say("  ** ยังไม่มียอดรายวันเลยสักแถว **")
            say("  ยอดรายวัน = ยอดสะสมวันนี้ ลบ เมื่อวาน → ต้องเก็บ snapshot อย่างน้อย 2 คืน")
            say("  ลองสั่ง:  python manage.py social_rebuild")
            return self._flush(o)
        say("  ยอดรายวันที่คำนวณได้: %s ถึง %s" % (first.strftime("%d/%m/%Y"), last.strftime("%d/%m/%Y")))

        # ── ตารางเปรียบเทียบทุกช่วง ───────────────────────────
        want = [o["period"]] if o["period"] else PERIODS
        if o["dfrom"] or o["dto"]:
            want = ["range"]

        say("")
        say("[1] ภาพรวมแต่ละช่วงเวลา (ทุกแพลตฟอร์มรวมกัน)")
        say("-" * 78)
        say("  %-16s %-19s %-11s %10s %9s" % ("ช่วง", "วันที่", "มีข้อมูล", "วิว", "ไลก์"))
        rows_for_detail = {}
        for key in want:
            if key == "range":
                s = date.fromisoformat(o["dfrom"]) if o["dfrom"] else first
                e = date.fromisoformat(o["dto"]) if o["dto"] else today
            else:
                s, e = self._range(key, today, first, last)
            qs = SocialDaily.objects.filter(date__gte=s, date__lte=e)
            t = qs.aggregate(v=Sum("views"), l=Sum("likes"), c=Sum("comments"),
                             sh=Sum("shares"), d=Count("date", distinct=True))
            span = (e - s).days + 1
            rows_for_detail[key] = (s, e, t)
            say("  %-16s %-19s %-11s %10s %9s" % (
                PERIOD_NAME[key],
                "%s - %s" % (s.strftime("%d/%m"), e.strftime("%d/%m")),
                "%d/%d วัน" % (t["d"] or 0, span),
                _n(t["v"]), _n(t["l"])))
        say("")
        say("  * \"มีข้อมูล x/y วัน\" — y คือจำนวนวันในช่วง, x คือวันที่คำนวณยอดรายวันได้จริง")
        say("    ระบบเริ่มเก็บ 19 ก.ย.69 → ช่วงที่ยาวกว่านั้นจะมีข้อมูลแค่บางส่วน เป็นเรื่องปกติ")

        # ── รายละเอียดช่วงที่เลือก (ไม่เลือก = 7 วัน) ──────────
        key = o["period"] or ("range" if (o["dfrom"] or o["dto"]) else "7d")
        s, e, tot = rows_for_detail.get(key, (None, None, None))
        if s is None:
            s, e = self._range(key, today, first, last)
        say("")
        say("=" * 78)
        say("  ลงรายละเอียด: %s (%s - %s)" % (PERIOD_NAME[key], s.strftime("%d/%m/%Y"), e.strftime("%d/%m/%Y")))
        say("=" * 78)

        qs = SocialDaily.objects.filter(date__gte=s, date__lte=e)

        say("")
        say("[2] แยกตามแพลตฟอร์ม")
        say("-" * 78)
        say("  %-10s %10s %9s %9s %8s %8s %8s" % ("", "วิว", "ไลก์", "คอมเมนต์", "แชร์", "ชิ้นงาน", "วัน"))
        any_row = False
        for p in ("meta", "tiktok", "youtube"):
            r = qs.filter(platform=p).aggregate(
                v=Sum("views"), l=Sum("likes"), c=Sum("comments"), sh=Sum("shares"),
                n=Count("object_id", distinct=True), d=Count("date", distinct=True))
            if not r["d"]:
                say("  %-10s  (ยังไม่มีข้อมูลในช่วงนี้)" % PLAT_NAME[p])
                continue
            any_row = True
            say("  %-10s %10s %9s %9s %8s %8s %8s" % (
                PLAT_NAME[p], _n(r["v"]), _n(r["l"]), _n(r["c"]), _n(r["sh"]), _n(r["n"]), r["d"]))
        if not any_row:
            say("  (ไม่มีข้อมูลในช่วงนี้เลย)")
        say("")
        say("  * YouTube ไม่มีคอลัมน์ \"แชร์\" (API ไม่ให้) → ขึ้น 0 เสมอ ไม่ใช่ตัวเลขผิด")

        # ── ยอดรายวัน ────────────────────────────────────────
        say("")
        say("[3] ยอดรายวัน")
        say("-" * 78)
        day_rows = (qs.values("date").annotate(v=Sum("views"), l=Sum("likes"),
                                               c=Sum("comments"), sh=Sum("shares"))
                    .order_by("date"))
        if not day_rows:
            say("  (ไม่มี)")
        else:
            say("  %-12s %12s %10s %10s %9s" % ("วันที่", "วิว", "ไลก์", "คอมเมนต์", "แชร์"))
            for r in day_rows:
                say("  %-12s %12s %10s %10s %9s" % (
                    r["date"].strftime("%d/%m/%Y"), _n(r["v"]), _n(r["l"]), _n(r["c"]), _n(r["sh"])))

        # ── Facebook ระดับเพจ (ย้อนหลังได้จริง) ────────────────
        pg = MetaPageDaily.objects.filter(date__gte=s, date__lte=e).aggregate(
            v=Sum("video_views"), e_=Sum("engagements"), f=Sum("follows"),
            pv=Sum("page_views"), d=Count("date", distinct=True))
        say("")
        say("[4] Facebook รายงานเองระดับเพจ  (ตัวเทียบ - Facebook ให้ย้อนหลัง ~30 วัน)")
        say("-" * 78)
        if not pg["d"]:
            say("  (ไม่มีข้อมูลในช่วงนี้)")
        else:
            say("  วิววิดีโอทั้งเพจ : %s" % _n(pg["v"]))
            say("  การมีส่วนร่วม    : %s" % _n(pg["e_"]))
            say("  ผู้ติดตามใหม่    : %s" % _n(pg["f"]))
            say("  คนเปิดดูเพจ      : %s" % _n(pg["pv"]))
            say("  มีข้อมูล %d วัน" % pg["d"])
            mine = qs.filter(platform="meta").aggregate(v=Sum("views"))["v"] or 0
            if pg["v"]:
                pct = mine * 100.0 / float(pg["v"])
                say("")
                say("  ที่เรารวมได้จากรายโพสต์ = %s (%.0f%% ของยอดเพจ)" % (_n(mine), pct))
                if pct < 80:
                    say("  ** ต่ำกว่า 80%% — น่าจะมีรีลส์/โพสต์ที่ไม่อยู่ในฟีดที่เราดึงไม่ถึง **")

        # ── ค่าโฆษณา ─────────────────────────────────────────
        ad = MetaAdDaily.objects.filter(date__gte=s, date__lte=e).aggregate(
            sp=Sum("spend"), im=Sum("impressions"), cl=Sum("clicks"), d=Count("date", distinct=True))
        say("")
        say("[5] ค่าโฆษณา Meta")
        say("-" * 78)
        if not ad["d"]:
            say("  (ไม่มีข้อมูลในช่วงนี้)")
        else:
            say("  ใช้เงิน %s บาท · แสดงผล %s · คลิก %s · มีข้อมูล %d วัน"
                % (_n(ad["sp"]), _n(ad["im"]), _n(ad["cl"]), ad["d"]))

        # ── โพสต์/คลิปที่ปังสุด ────────────────────────────────
        say("")
        say("[6] โพสต์/คลิปที่คนดูมากสุดในช่วงนี้ (เรียงตามวิวที่เกิดขึ้นในช่วง)")
        say("-" * 78)
        top = (qs.values("platform", "object_id", "title")
               .annotate(v=Sum("views"), l=Sum("likes"), c=Sum("comments"))
               .order_by("-v")[:o["top"]])
        if not top:
            say("  (ไม่มี)")
        for i, r in enumerate(top, 1):
            say("  %2d. [%-8s] วิว %-10s ไลก์ %-7s | %s"
                % (i, PLAT_NAME.get(r["platform"], r["platform"]), _n(r["v"]), _n(r["l"]),
                   (r["title"] or r["object_id"])[:44]))

        # ── อะไรยังขาด ───────────────────────────────────────
        say("")
        say("[7] อะไรที่ยังไม่มีในรายงานนี้")
        say("-" * 78)
        for p in ("meta", "tiktok", "youtube"):
            n = SocialDaily.objects.filter(platform=p).count()
            if not n:
                why = {"meta": "ยังไม่ได้ดึง Facebook",
                       "tiktok": "snapshot รอบ cron ยังไม่ครบ 2 คืน (แถว manual ไม่นับ)",
                       "youtube": "ยังไม่ได้ deploy / ยังไม่ได้ดึงครบ 2 คืน"}[p]
                say("  - %s: ยังไม่มียอดรายวันเลย — %s" % (PLAT_NAME[p], why))
        say("  - Instagram: ยังไม่ได้ผูก IG เข้ากับเพจ Facebook (instagram_business_account ว่าง)")
        say("  - เกรดคลิป A/B/C/D: ยังไม่มีเกณฑ์ในระบบ ต้องกำหนดสูตรก่อน")

        if o["csv"] and day_rows:
            with io.open(o["csv"], "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(["วันที่", "วิว", "ไลก์", "คอมเมนต์", "แชร์"])
                for r in day_rows:
                    w.writerow([r["date"].isoformat(), r["v"] or 0, r["l"] or 0,
                                r["c"] or 0, r["sh"] or 0])
            say("")
            say("เขียน CSV แล้ว: %s" % o["csv"])

        return self._flush(o)

    def _flush(self, o):
        text = "\n".join(self.lines)
        if o["out"]:
            with io.open(o["out"], "w", encoding="utf-8") as f:
                f.write(text + "\n")
            self.stdout.write("wrote %s (%d lines)" % (o["out"], len(self.lines)))
        else:
            for ln in self.lines:
                try:
                    self.stdout.write(ln)
                except UnicodeEncodeError:      # console ไทยเพี้ยน (cp874)
                    self.stdout.write(ln.encode("ascii", "replace").decode("ascii"))
