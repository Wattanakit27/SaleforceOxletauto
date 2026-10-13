"""ห้องจ่ายเบอร์ → "ชีทจ่ายเบอร์ ปี69" + "รายงานแบน" (แทน workflow n8n · ดู checkout/leadsheet.py)

    python manage.py leadsheet                       # สถานะ: เปิดไหม · ค้างกี่ข้อความ · ผลรอบล่าสุด
    python manage.py leadsheet --preview --last 80   # ข้อความล่าสุด 80 ข้อความในห้องจ่ายเบอร์จะเขียนอะไร
                                                     #   (อ่านชีตอย่างเดียว · ใบที่ n8n ลงไว้แล้วขึ้น "มีแล้ว" + ช่องที่ต่างกัน)
    python manage.py leadsheet --on                  # เปิด (เริ่มจากข้อความล่าสุดตอนนี้ · ต้องปิด n8n วันเดียวกัน)
    python manage.py leadsheet --on --since "2026-10-13 18:00"   # เปิด + ไล่ย้อนจากเวลาที่ปิด n8n
    python manage.py leadsheet --off
    python manage.py leadsheet --ban off             # ไม่เขียนรายงานแบน (ใบ/รายงานผลยังเขียน)
    python manage.py leadsheet --run                 # เขียนข้อความที่ค้างเดี๋ยวนี้
    python manage.py leadsheet --repair-dates        # หาแถวที่ ว/ด/ป ถูก n8n เขียนทับ (ดูเฉยๆ)
    python manage.py leadsheet --repair-dates --apply [--tab "ตุลาคม 69"]   # คืนวันที่จริง

ใส่ --out ไฟล์ เพื่อเลี่ยงภาษาไทยเพี้ยนบน console Windows
"""
import json
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from checkout import leadsheet as LS


def _short(row: dict) -> str:
    return " · ".join("%s=%s" % (k, v) for k, v in row.items() if k != "phone")


class Command(BaseCommand):
    help = "ลงชีตจ่ายเบอร์จากห้องจ่ายเบอร์ (แทน n8n)"

    def add_arguments(self, p):
        p.add_argument("--on", action="store_true")
        p.add_argument("--off", action="store_true")
        p.add_argument("--ban", choices=["on", "off"])
        p.add_argument("--since", help='ตั้งจุดเริ่ม เช่น "2026-10-13 18:00" (เวลาไทย) — ข้อความหลังเวลานี้จะถูกเขียน')
        p.add_argument("--run", action="store_true", help="เขียนข้อความที่ค้างเดี๋ยวนี้")
        p.add_argument("--preview", action="store_true", help="ดูว่าจะเขียนอะไร (ไม่เขียน)")
        p.add_argument("--last", type=int, default=0, help="ใช้กับ --preview: ข้อความล่าสุด N ข้อความ (ไม่สนตัวชี้)")
        p.add_argument("--repair-dates", action="store_true", help="หา/ซ่อม ว/ด/ป ที่ถูกเขียนทับด้วยวันที่รายงาน")
        p.add_argument("--tab", action="append", help='แท็บที่ซ่อม เช่น "ตุลาคม 69" (ใส่ซ้ำได้ · ไม่ใส่ = เดือนนี้+เดือนก่อน)')
        p.add_argument("--apply", action="store_true", help="ใช้คู่กับ --repair-dates")
        p.add_argument("--out", help="เขียนผลลงไฟล์ (UTF-8)")

    def handle(self, *args, **o):
        lines = []
        if o["on"] and o["off"]:
            raise CommandError("เลือก --on หรือ --off อย่างเดียว")
        since = None
        if o.get("since"):
            try:
                since = timezone.make_aware(datetime.strptime(o["since"], "%Y-%m-%d %H:%M"))
            except ValueError:
                raise CommandError('--since ต้องเป็น "YYYY-MM-DD HH:MM" (เวลาไทย)')
        if o["on"] or o["off"] or o.get("ban"):
            was = LS.get_config()["enabled"]
            cfg = LS.set_config(enabled=(True if o["on"] else (False if o["off"] else None)),
                                ban={"on": True, "off": False}.get(o.get("ban")))
            lines.append("ตั้งค่าแล้ว: %s" % json.dumps(cfg, ensure_ascii=False))
            if o["on"] and not was and not since:
                last = LS.set_since()
                lines.append("เริ่มจากข้อความล่าสุดตอนนี้ (id > %d) — ข้อความก่อนหน้านี้ถือว่า n8n ลงไปแล้ว" % last)
        if since:
            last = LS.set_since(since)
            lines.append("ตั้งจุดเริ่ม: ข้อความหลัง %s (id > %d)" % (o["since"], last))

        if o["repair_dates"]:
            self._repair(o, lines)
        elif o["run"]:
            lines.append(json.dumps(LS.process_pending(), ensure_ascii=False, indent=1))
        elif o["preview"]:
            self._preview(o, lines)
        else:
            st = LS.status()
            lines.append("สถานะ: %s · รายงานแบน %s · ห้องจ่ายเบอร์ %d ห้อง" % (
                "เปิด" if st["config"]["enabled"] else "ปิด", "เขียน" if st["config"]["ban"] else "ไม่เขียน",
                st["rooms"]))
            lines.append("ตัวชี้: %s (%s) · ค้าง %d · เกิน 10 นาที %d" % (
                st["cursor"], st["cursorAt"] or "-", st["pending"], LS.pending_count(10)))
            lines.append("ผลรอบล่าสุด: %s" % json.dumps(st["last"], ensure_ascii=False))

        text = "\n".join(lines)
        if o.get("out"):
            with open(o["out"], "w", encoding="utf-8") as f:
                f.write(text + "\n")
            self.stdout.write("เขียนผลลง %s แล้ว" % o["out"])
        else:
            self.stdout.write(text)

    def _repair(self, o, lines):
        r = LS.repair_dates(o.get("tab"), apply=o["apply"])
        lines.append("แท็บ: %s" % json.dumps(r["tabs"], ensure_ascii=False))
        lines.append("แถวที่ ว/ด/ป ถูกเขียนทับ (หาวันที่จริงเจอ) %d แถว:" % len(r["fix"]))
        for f in r["fix"]:
            lines.append("  %s แถว %d  %s  %s → %s" % (f["tab"], f["row"], f["code"], f["from"], f["to"]))
        if r["unknown"]:
            lines.append("ว/ด/ป = วันอัพเดทล่าสุด แต่หาใบในคลังแชทไม่เจอ %d แถว (ไม่แก้ · ส่วนใหญ่วันที่ถูกอยู่แล้ว):"
                         % len(r["unknown"]))
            for f in r["unknown"][:200]:
                lines.append("  %s แถว %d  %s  ว/ด/ป=%s" % (f["tab"], f["row"], f["code"], f["a"]))
        if o["apply"]:
            lines.append("แก้แล้ว %d แถว (เขียนเฉพาะช่อง ว/ด/ป)" % r["applied"])
        elif r["fix"]:
            lines.append("(ยังไม่ได้แก้ — ใส่ --apply เพื่อเขียนวันที่จริงลงช่อง ว/ด/ป)")

    def _preview(self, o, lines):
        from checkout.models import GroupChat
        ctx = LS.Ctx(write=False)
        if o["last"]:
            ids = list(GroupChat.objects.filter(chat_type=GroupChat.GROUP, group_id__in=LS._rooms(), msg_type="text")
                       .order_by("-id").values_list("id", flat=True)[:o["last"]])
            msgs = list(GroupChat.objects.filter(id__in=ids).order_by("id"))
        else:
            st = LS._kv(LS.KV_STATE)
            msgs = list(LS._qs(st.get("last_id") or LS._max_id())[:100])
        lines.append("ข้อความ %d รายการ (ยังไม่เขียน):" % len(msgs))
        for m in msgs:
            when = timezone.localtime(m.sent_at).strftime("%d/%m %H:%M") if m.sent_at else "-"
            try:
                r = LS.handle(m, ctx)
            except Exception as e:
                lines.append("  %s ล้ม: %s" % (when, e))
                continue
            a = r.get("action")
            if a == "skip":
                continue
            if a == "add":
                lines.append("  %s เพิ่มแถว %s → %s แถว %s · %s" % (when, r["code"], r["tab"], r["sheetRow"],
                                                                   _short(r.get("row") or {})))
                if r.get("conflict"):
                    lines.append("      ⚠ " + r["conflict"])
            elif a in ("dup", "update"):
                what = "มีแล้ว" if a == "dup" else "เติม " + ",".join(r.get("fields") or [])
                diff = {k: v for k, v in (r.get("diff") or {}).items() if k != "phone"}
                lines.append("  %s %s %s (%s แถว %s)%s" % (
                    when, what, r["code"], r["tab"], r["sheetRow"],
                    (" · ต่างจากในชีต: " + json.dumps(diff, ensure_ascii=False)) if diff else ""))
            elif a == "report":
                lines.append("  %s รายงานผล %s (%s แถว %s) โดย %s → ครั้งที่ %s" % (
                    when, r["code"], r["tab"], r["sheetRow"], r["reporter"], r["count"]))
            elif a == "ban":
                lines.append("  %s แบน: %s" % (when, json.dumps(
                    [{k: x[k] for k in ("banDate", "seller", "banType", "unbanDate")} for x in r["rows"]],
                    ensure_ascii=False)))
            else:
                lines.append("  %s %s %s" % (when, a, json.dumps({k: v for k, v in r.items() if k != "action"},
                                                                 ensure_ascii=False)))
