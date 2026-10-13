"""สำเนา "ชีทจ่ายเบอร์ ปี69" + "รายงานแบน" ลง Postgres (ดู dashboard/services/sheet_mirror.py)

    python manage.py sheet_mirror                       # สถานะ: แต่ละแท็บมีกี่แถว · รอบล่าสุดเมื่อไหร่
    python manage.py sheet_mirror --run                 # ดึงทั้งชีตเดี๋ยวนี้ (ปกติระบบทำเองทุก 10 นาที)
    python manage.py sheet_mirror --run --tab "ตุลาคม 69"   # ดึงแท็บเดียว

ใส่ --out ไฟล์ เพื่อเลี่ยงภาษาไทยเพี้ยนบน console Windows
"""
import json

from django.core.management.base import BaseCommand

from dashboard.services import sheet_mirror as SM


class Command(BaseCommand):
    help = "สำเนาชีตจ่ายเบอร์ + รายงานแบน ลง Postgres"

    def add_arguments(self, p):
        p.add_argument("--run", action="store_true")
        p.add_argument("--tab", action="append", help='แท็บที่จะดึง เช่น "ตุลาคม 69" (ใส่ซ้ำได้)')
        p.add_argument("--out", help="เขียนผลลงไฟล์ (UTF-8)")

    def handle(self, *args, **o):
        lines = []
        if o["run"]:
            lines.append(json.dumps(SM.run(o.get("tab")), ensure_ascii=False, indent=1))
        st = SM.status()
        lines.append("แถวชีตจ่ายเบอร์ในฐานข้อมูล: %d แถว · รายงานแบน %d แถว" % (st["rows"], st["bans"]))
        for tab, n in st["tabs"]:
            lines.append("  %s: %d" % (tab, n))
        last = st["last"]
        lines.append("รอบล่าสุด: %s · %s · %s ms%s" % (
            last.get("at", "-"), "สำเร็จ" if last.get("ok") else "ล้ม", last.get("ms", "-"),
            (" · " + last["error"]) if last.get("error") else ""))
        text = "\n".join(lines)
        if o.get("out"):
            with open(o["out"], "w", encoding="utf-8") as f:
                f.write(text + "\n")
            self.stdout.write("เขียนผลลง %s แล้ว" % o["out"])
        else:
            self.stdout.write(text)
