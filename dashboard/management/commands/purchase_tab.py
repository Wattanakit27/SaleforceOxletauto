"""เตรียมแท็บรายเดือนของชีตจัดซื้อ "ซื้อขายเทิร์นรถ" (ดู dashboard/services/purchase_tabs.py)

    python manage.py purchase_tab                       # สถานะ: แท็บเดือนนี้/เดือนหน้ามีหรือยัง + ผลรอบล่าสุด
    python manage.py purchase_tab --month 2026-11       # ดูแผนเฉยๆ (อ่านอย่างเดียว ไม่เขียนชีต)
    python manage.py purchase_tab --month 2026-11 --apply   # สร้างจริง
    python manage.py purchase_tab --auto off            # ปิดการเตรียมแท็บอัตโนมัติใน cron (on = เปิด)

ไม่ใส่ --month = เดือนหน้า · ใส่ --out ไฟล์ เพื่อเลี่ยงภาษาไทยเพี้ยนบน console Windows
"""
import json

from django.core.management.base import BaseCommand, CommandError

from dashboard.services import purchase_tabs as PT
from dashboard.services.purchase_followup import tab_name


class Command(BaseCommand):
    help = "เตรียมแท็บเดือนใหม่ของชีตจัดซื้อ (ค่าเริ่มต้น = ดูเฉยๆ)"

    def add_arguments(self, p):
        p.add_argument("--month", help="YYYY-MM (ค.ศ.) · ไม่ใส่ = เดือนหน้า")
        p.add_argument("--apply", action="store_true", help="สร้างแท็บจริง (ไม่ใส่ = ดูแผนเฉยๆ)")
        p.add_argument("--auto", choices=["on", "off"], help="เปิด/ปิดการเตรียมแท็บอัตโนมัติใน cron")
        p.add_argument("--out", help="เขียนผลลงไฟล์ (UTF-8)")

    def handle(self, *args, **o):
        from dashboard.services.cache_store import get_kv, set_kv
        from dashboard.services.fetch_dashboard import bangkok_now

        lines = []
        if o.get("auto"):
            set_kv(PT.KV_AUTO, {"on": o["auto"] == "on"})
            lines.append("ตั้งค่าเตรียมแท็บอัตโนมัติ = %s" % ("เปิด" if PT.auto_on() else "ปิด"))

        now = bangkok_now()
        if o.get("month"):
            try:
                y, m = [int(x) for x in o["month"].split("-")]
                assert 1 <= m <= 12
            except Exception:
                raise CommandError("--month ต้องเป็น YYYY-MM เช่น 2026-11")
            r = PT.ensure_tab(y, m, apply=o["apply"])
            lines.append(json.dumps(r, ensure_ascii=False, indent=2))
        elif o["apply"]:
            raise CommandError("--apply ต้องใส่ --month ด้วย (กันสร้างผิดเดือน)")
        elif not o.get("auto"):
            ny, nm = (now.year + 1, 1) if now.month == 12 else (now.year, now.month + 1)
            titles = PT._Api().tabs()
            for label, (y, m) in (("เดือนนี้", (now.year, now.month)), ("เดือนหน้า", (ny, nm))):
                t = tab_name(y, m)
                lines.append("%s: %s — %s" % (label, t, "มีแล้ว" if t in titles else "ยังไม่มี"))
            lines.append("เตรียมแท็บอัตโนมัติ: %s (เริ่มเตรียมเดือนหน้าตั้งแต่วันที่ %d)"
                         % ("เปิด" if PT.auto_on() else "ปิด", PT.PREPARE_FROM_DAY))
            raw = get_kv(PT.KV_LAST) or {}
            last = raw.get("data", raw) if isinstance(raw, dict) else raw
            lines.append("ผลรอบล่าสุด: %s" % json.dumps(last, ensure_ascii=False))

        text = "\n".join(lines)
        if o.get("out"):
            with open(o["out"], "w", encoding="utf-8") as f:
                f.write(text + "\n")
            self.stdout.write("เขียนผลลง %s แล้ว" % o["out"])
        else:
            self.stdout.write(text)
