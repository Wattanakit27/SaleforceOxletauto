"""เคสรับซื้อ/เทิร์นรถ → ชีต "ซื้อขายเทิร์นรถ" (แทน workflow n8n · ดู checkout/tradein.py)

    python manage.py tradein                     # สถานะ: เปิดไหม · เขียนแท็บไหน · ค้างกี่ข้อความ · ผลรอบล่าสุด
    python manage.py tradein --preview           # ดูว่าข้อความที่ค้างจะเขียนอะไร (ไม่เขียนชีต)
    python manage.py tradein --run               # เขียนข้อความที่ค้างเดี๋ยวนี้ (ปกติระบบทำเองตอนข้อความเข้า+ทุกนาที)
    python manage.py tradein --target month      # เขียนแท็บรายเดือนจริง (test = แท็บ TestBot)
    python manage.py tradein --off | --on        # ปิด/เปิด
    python manage.py tradein --since "2026-10-08 12:34"   # ตั้งจุดเริ่มใหม่ (ข้อความก่อนเวลานี้ถือว่าจัดการแล้ว)

ใส่ --out ไฟล์ เพื่อเลี่ยงภาษาไทยเพี้ยนบน console Windows
"""
import json
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Max
from django.utils import timezone

from checkout import tradein as T


class Command(BaseCommand):
    help = "บันทึกเคสรับซื้อ/เทิร์นรถจากห้องเคสHOT ลงชีต (แทน n8n)"

    def add_arguments(self, p):
        p.add_argument("--on", action="store_true")
        p.add_argument("--off", action="store_true")
        p.add_argument("--target", choices=["test", "month"])
        p.add_argument("--run", action="store_true", help="เขียนข้อความที่ค้างเดี๋ยวนี้")
        p.add_argument("--preview", action="store_true", help="ดูว่าจะเขียนอะไร (ไม่เขียน)")
        p.add_argument("--since", help='ตั้งจุดเริ่มใหม่ เช่น "2026-10-08 12:34" (เวลาไทย)')
        p.add_argument("--repair", action="store_true",
                       help="ล้างแถวที่ลงผิดคอลัมน์ (8 ต.ค.69) แล้วเขียนใหม่จากแชทเดิม · ไม่ใส่ --apply = ดูเฉยๆ")
        p.add_argument("--apply", action="store_true", help="ใช้คู่กับ --repair")
        p.add_argument("--out", help="เขียนผลลงไฟล์ (UTF-8)")

    def handle(self, *args, **o):
        from dashboard.services.cache_store import set_kv

        from checkout.models import GroupChat
        lines = []
        if o["on"] and o["off"]:
            raise CommandError("เลือก --on หรือ --off อย่างเดียว")
        if o["on"] or o["off"] or o.get("target"):
            cfg = T.set_config(enabled=(True if o["on"] else (False if o["off"] else None)), target=o.get("target"))
            lines.append("ตั้งค่าแล้ว: %s" % json.dumps(cfg, ensure_ascii=False))
        if o.get("since"):
            try:
                dt = timezone.make_aware(datetime.strptime(o["since"], "%Y-%m-%d %H:%M"))
            except ValueError:
                raise CommandError('--since ต้องเป็น "YYYY-MM-DD HH:MM" (เวลาไทย)')
            last = GroupChat.objects.filter(group_id__in=list(T.PURCHASE_GROUPS), sent_at__lt=dt).aggregate(
                m=Max("id"))["m"] or 0
            set_kv(T.KV_STATE, {"last_id": last})
            lines.append("ตั้งจุดเริ่มใหม่: ข้อความหลัง %s (id > %d)" % (o["since"], last))

        if o["repair"]:
            r = T.repair_shifted(apply=o["apply"])
            lines.append(json.dumps(r, ensure_ascii=False, indent=1))
            if r.get("rows") and not o["apply"]:
                lines.append("(ยังไม่ได้แก้ — ใส่ --apply เพื่อล้างแถวพวกนี้แล้วเขียนใหม่ให้ถูกที่)")
        elif o["run"]:
            lines.append(json.dumps(T.process_pending(), ensure_ascii=False, indent=1))
        elif o["preview"]:
            from dashboard.services.purchase_tabs import _Api
            api, cache, cfg = _Api(), {}, T.get_config()
            msgs = list(T.pending_qs(T._cursor())[:100])
            lines.append("ข้อความค้าง %d รายการ (ยังไม่เขียน):" % len(msgs))
            for m in msgs:
                r = T.handle(m, api, cache, cfg, write=False)
                when = timezone.localtime(m.sent_at).strftime("%d/%m %H:%M") if m.sent_at else "-"
                if r.get("action") == "add":
                    row = r["row"]
                    lines.append("  %s เพิ่มแถว %s → %s · จัดซื้อ=%s ผู้ส่ง=%s เคส=%s car=%s" % (
                        when, r["code"], r["tab"], row[12], row[13], row[14], row[18] or "-"))
                elif r.get("action") == "comment":
                    lines.append("  %s คอมเมนต์ %s → %s แถว %s (%s)" % (
                        when, r["code"], r["tab"], r["sheetRow"], ",".join(r["cols"])))
                else:
                    lines.append("  %s %s %s" % (when, r.get("action"), r.get("code", "")))
        else:
            cfg = T.get_config()
            lines.append("สถานะ: %s · เขียนลง %s" % (
                "เปิด" if cfg["enabled"] else "ปิด",
                "แท็บ TestBot" if cfg["target"] == "test" else "แท็บรายเดือน (ขายรถจบออนไลน์ <เดือน><ปี>)"))
            lines.append("ข้อความที่ยังไม่ได้จัดการ: %d (เกิน 10 นาที %d)" % (T.pending_count(), T.pending_count(10)))
            lines.append("ผลรอบล่าสุด: %s" % json.dumps(T._kv(T.KV_LAST), ensure_ascii=False))

        text = "\n".join(lines)
        if o.get("out"):
            with open(o["out"], "w", encoding="utf-8") as f:
                f.write(text + "\n")
            self.stdout.write("เขียนผลลง %s แล้ว" % o["out"])
        else:
            self.stdout.write(text)
