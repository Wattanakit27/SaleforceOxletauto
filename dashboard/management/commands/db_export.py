"""ดึงข้อมูลในฐานข้อมูลออกมาเป็นไฟล์ จาก SSH — ★ ก.ย.69

    python manage.py db_export --list                          # มีตารางอะไรให้ดึง กี่แถว
    python manage.py db_export --all --out /tmp/oxlet.zip      # ทุกตาราง (zip · CSV ไฟล์ละตาราง)
    python manage.py db_export --table checkout_groupchat --out /tmp/chat.csv
    python manage.py db_export --all --out /tmp/ข้อมูล/        # แตกเป็นไฟล์ในโฟลเดอร์ (ไม่ zip)

ทำไมต้องมีทั้งทางเว็บและทาง SSH:
  - ทางเว็บ (เมนู "ฐานข้อมูล" → ปุ่มดาวน์โหลด) = เจ้าของกดเอาเองได้ ไม่ต้องเรียกใคร
  - ทาง SSH = เอาไป **ตั้ง cron สำรองข้อมูลรายวัน** ได้ และไฟล์ใหญ่ไม่ต้องวิ่งผ่านเบราว์เซอร์

⚠️ console ไทยเพี้ยน (cp874) → คำสั่งนี้เขียน**ไฟล์** เสมอ ที่พิมพ์ลงจอเป็นแค่สรุปสั้นๆ
⚠️ ไฟล์ที่ได้มีชื่อ-ข้อความของคนจริง (PDPA) — LINE user id ของพนักงานถูกปิดให้แล้ว
   แต่ที่เหลือเป็นข้อมูลจริง **เก็บให้ดี อย่าทิ้งไว้ใน /tmp ของเครื่องที่คนอื่นเข้าได้**
"""
import os

from django.core.management.base import BaseCommand

from dashboard.services import db_export


class Command(BaseCommand):
    help = "ดึงข้อมูลในฐานข้อมูลออกมาเป็น CSV / zip"

    def add_arguments(self, p):
        p.add_argument("--list", action="store_true", help="ดูว่ามีตารางอะไรให้ดึง กี่แถว")
        p.add_argument("--table", help="ชื่อตาราง (เช่น checkout_groupchat)")
        p.add_argument("--all", action="store_true", help="ทุกตาราง")
        p.add_argument("--out", help="ไฟล์ปลายทาง (ลงท้าย / = โฟลเดอร์ → แตกเป็นไฟล์ๆ)")

    def handle(self, *a, **o):
        w = self.stdout.write

        if o.get("list") or (not o.get("table") and not o.get("all")):
            rows = db_export.datasets()
            w("ตารางที่ดึงได้ %d ตาราง:" % len(rows))
            for r in rows:
                w("  %-34s %10s แถว %s" % (r["table"],
                                           "?" if r["rows"] is None else f"{r['rows']:,}",
                                           "[PDPA]" if r["pii"] else ""))
            w("")
            w("  ดึงทั้งหมด : manage.py db_export --all --out /tmp/oxlet.zip")
            w("  ดึงตารางเดียว: manage.py db_export --table <ชื่อตาราง> --out /tmp/x.csv")
            return

        out = o.get("out") or ""

        # ── ตารางเดียว ──
        if o.get("table"):
            try:
                data, n, cut = db_export.table_csv(o["table"])
            except ValueError as e:
                w("❌ %s" % e)
                return
            path = out or ("%s.csv" % o["table"])
            if path.endswith(("/", "\\")) or os.path.isdir(path):
                path = os.path.join(path, "%s.csv" % o["table"])
            self._write(path, data)
            w("wrote -> %s  (%s แถว%s)" % (path, f"{n:,}", " · ตัดที่เพดาน" if cut else ""))
            return

        # ── ทุกตาราง: โฟลเดอร์ (แตกไฟล์) หรือ zip ──
        if out and (out.endswith(("/", "\\")) or os.path.isdir(out)):
            os.makedirs(out, exist_ok=True)
            summary = []
            for d in db_export.datasets():
                t = d["table"]
                try:
                    data, n, cut = db_export.table_csv(t)
                    self._write(os.path.join(out, "%s.csv" % t), data)
                    summary.append({"table": t, "name": d["name"], "rows": n, "cut": cut, "error": ""})
                except Exception as e:
                    summary.append({"table": t, "name": d["name"], "rows": 0, "cut": False,
                                    "error": str(e)[:160]})
            self._write(os.path.join(out, "อ่านก่อน.txt"),
                        db_export.readme(summary).encode("utf-8"))
            w("wrote -> %s  (%d ไฟล์ · %s แถว)"
              % (out, len(summary) + 1, f"{sum(s['rows'] for s in summary):,}"))
        else:
            data, summary = db_export.all_zip()
            path = out or "oxlet_export.zip"
            self._write(path, data)
            w("wrote -> %s  (%d ตาราง · %s แถว · %.1f MB)"
              % (path, len(summary), f"{sum(s['rows'] for s in summary):,}",
                 len(data) / 1048576.0))

        for s in summary:
            if s["error"]:
                w("  ⚠️ %s อ่านไม่ได้: %s" % (s["table"], s["error"]))

    def _write(self, path, data: bytes):
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
