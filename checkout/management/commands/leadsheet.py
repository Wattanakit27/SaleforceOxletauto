"""ห้องจ่ายเบอร์ → "ชีทจ่ายเบอร์ ปี69" + "รายงานแบน" (แทน workflow n8n · ดู checkout/leadsheet.py)

    python manage.py leadsheet                       # สถานะ: เปิดไหม · ค้างกี่ข้อความ · ผลรอบล่าสุด
    python manage.py leadsheet --preview --last 80   # ข้อความล่าสุด 80 ข้อความในห้องจ่ายเบอร์จะเขียนอะไร
                                                     #   (อ่านชีตอย่างเดียว · ใบที่ n8n ลงไว้แล้วขึ้น "มีแล้ว" + ช่องที่ต่างกัน)
    python manage.py leadsheet --on                  # เปิด (เริ่มจากข้อความล่าสุดตอนนี้ · ต้องปิด n8n วันเดียวกัน)
    python manage.py leadsheet --on --since "2026-10-13 18:00"   # เปิด + ไล่ย้อนจากเวลาที่ปิด n8n
    python manage.py leadsheet --off
    python manage.py leadsheet --ban off             # ไม่เขียนรายงานแบน (ใบ/รายงานผลยังเขียน)
    python manage.py leadsheet --alert-test          # ส่ง LINE ทดสอบหาผู้รับแจ้งเตือน (ค่าตั้งต้น: Wattanakit/วัฒนกิจ)
    python manage.py leadsheet --test-month-move     # ลองย้ายแถวข้ามแท็บกับ Google จริง (แท็บชั่วคราว ลบทิ้งเอง)
    python manage.py leadsheet --alert-to ชื่อเล่น      # เปลี่ยนผู้รับแจ้งเตือน · --alert off = ปิดแจ้งเตือน
    python manage.py leadsheet --run                 # เขียนข้อความที่ค้างเดี๋ยวนี้
    python manage.py leadsheet --repair-dates        # หาแถวที่ ว/ด/ป ถูก n8n เขียนทับ (ดูเฉยๆ)
    python manage.py leadsheet --repair-dates --apply [--tab "ตุลาคม 69"]   # คืนวันที่จริง
    python manage.py leadsheet --simulate --seller มัท --admin กวาง [--other เฟิร์ส]
        # จำลองแอดมินโพสต์ใบในกลุ่ม + เซลล์รายงานผล → ลงแท็บ "ทดสอบลงชีต (ลบได้)" (ไม่ส่ง LINE · ไม่แตะแท็บจริง)
    python manage.py leadsheet --simulate --seller มัท --admin กวาง --in-month-tab
        # เหมือนข้างบน แต่ต่อท้ายแท็บเดือนจริง (แดชบอร์ดนับระหว่างที่แถวยังอยู่ — ลบด้วย --simulate-cleanup)
    python manage.py leadsheet --simulate-cleanup    # ลบแท็บทดสอบ + แถวจำลองในแท็บเดือนจริง (เฉพาะที่คำสั่งนี้สร้าง)

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
        p.add_argument("--alert", choices=["on", "off"], help="แจ้งเตือน LINE ส่วนตัวเมื่อบันทึกชีตไม่ได้")
        p.add_argument("--alert-to", help="ชื่อเล่น (หรือชื่อ LINE) ผู้รับแจ้งเตือน")
        p.add_argument("--alert-test", action="store_true", help="ส่งข้อความทดสอบหาผู้รับแจ้งเตือน")
        p.add_argument("--test-month-move", action="store_true",
                       help="ลองย้ายแถวข้ามแท็บกับ Google จริง (สร้างแท็บชั่วคราว 2 แท็บแล้วลบทิ้ง)")
        p.add_argument("--since", help='ตั้งจุดเริ่ม เช่น "2026-10-13 18:00" (เวลาไทย) — ข้อความหลังเวลานี้จะถูกเขียน')
        p.add_argument("--run", action="store_true", help="เขียนข้อความที่ค้างเดี๋ยวนี้")
        p.add_argument("--preview", action="store_true", help="ดูว่าจะเขียนอะไร (ไม่เขียน)")
        p.add_argument("--last", type=int, default=0, help="ใช้กับ --preview: ข้อความล่าสุด N ข้อความ (ไม่สนตัวชี้)")
        p.add_argument("--repair-dates", action="store_true", help="หา/ซ่อม ว/ด/ป ที่ถูกเขียนทับด้วยวันที่รายงาน")
        p.add_argument("--tab", action="append", help='แท็บที่ซ่อม เช่น "ตุลาคม 69" (ใส่ซ้ำได้ · ไม่ใส่ = เดือนนี้+เดือนก่อน)')
        p.add_argument("--apply", action="store_true", help="ใช้คู่กับ --repair-dates")
        p.add_argument("--simulate", action="store_true", help="จำลองแอดมินจ่ายเบอร์ → ลงแท็บทดสอบ")
        p.add_argument("--seller", help="ชื่อเล่นเซลล์ที่ได้ใบ (ใช้กับ --simulate)")
        p.add_argument("--admin", default="", help="ชื่อเล่นแอดมินที่โพสต์ใบ (ใช้กับ --simulate)")
        p.add_argument("--other", default="", help="เซลล์อีกคน ลองรายงานแทน (ต้องไม่ลง)")
        p.add_argument("--in-month-tab", action="store_true", help="ใช้กับ --simulate: ต่อท้ายแท็บเดือนจริง")
        p.add_argument("--simulate-cleanup", action="store_true", help="ลบแท็บทดสอบ + แถวจำลองในแท็บเดือนจริง")
        p.add_argument("--log", action="store_true", help="ดู log ย้อนหลัง: เรื่องที่แจ้งเตือน · ล้ม · ผลส่ง LINE")
        p.add_argument("--days", type=int, default=3, help="ใช้กับ --log (ค่าเริ่มต้น 3 วัน)")
        p.add_argument("--watchdog", action="store_true", help="ตรวจระบบแบบตัวเฝ้าระบบเดี๋ยวนี้ (ไม่ส่ง LINE)")
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
        if o["on"] or o["off"] or o.get("ban") or o.get("alert") or o.get("alert_to") is not None:
            was = LS.get_config()["enabled"]
            cfg = LS.set_config(enabled=(True if o["on"] else (False if o["off"] else None)),
                                ban={"on": True, "off": False}.get(o.get("ban")),
                                alert={"on": True, "off": False}.get(o.get("alert")),
                                alert_to=o.get("alert_to"))
            lines.append("ตั้งค่าแล้ว: %s" % json.dumps(cfg, ensure_ascii=False))
            if o["on"] and not was and not since:
                last = LS.set_since()
                lines.append("เริ่มจากข้อความล่าสุดตอนนี้ (id > %d) — ข้อความก่อนหน้านี้ถือว่า n8n ลงไปแล้ว" % last)
        if since:
            last = LS.set_since(since)
            lines.append("ตั้งจุดเริ่ม: ข้อความหลัง %s (id > %d)" % (o["since"], last))

        if o["log"]:
            rows = LS.recent_log(days=o["days"], limit=300)
            lines.append("log ระบบลงชีตจ่ายเบอร์ %d วันล่าสุด (%d รายการ · ใหม่ก่อน):" % (o["days"], len(rows)))
            for r in rows:
                lines.append("  %s %s %s" % (r["at"], "ok " if r["ok"] else "ERR", r["text"]))
            if not rows:
                lines.append("  (ไม่มี — ไม่มีเรื่องผิดปกติ)")
        elif o["watchdog"]:
            items = LS.watchdog_check()
            lines.append("ตัวเฝ้าระบบ: %s" % ("ปกติ" if not items else "%d เรื่อง" % len(items)))
            lines += ["  - " + t for _k, t, _e in items]
        elif o["test_month_move"]:
            lines += LS.move_selftest()
        elif o["alert_test"]:
            r = LS.alert_test()
            lines.append(("ส่งแล้ว → %s" % r["to"]) if r["ok"] else ("ส่งไม่ถึง: %s" % r["error"]))
        elif o["simulate"]:
            if not o.get("seller"):
                raise CommandError("ใส่ --seller ชื่อเล่นเซลล์ (เช่น --seller มัท)")
            lines += LS.simulate(o["seller"], o.get("admin") or "", o.get("other") or "",
                                 real_tab=o["in_month_tab"])
            lines.append("ลบด้วย --simulate-cleanup (ลบเฉพาะแถว/แท็บที่คำสั่งจำลองสร้าง)")
        elif o["simulate_cleanup"]:
            rows = LS.delete_sim_rows()
            lines.append(("ลบแถวจำลอง: " + ", ".join(rows)) if rows else "ไม่มีแถวจำลองในแท็บเดือนจริง")
            lines.append("ลบแท็บทดสอบแล้ว" if LS.delete_sim_tab() else "ไม่มีแท็บทดสอบ")
        elif o["repair_dates"]:
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
            cfg = st["config"]
            lines.append("แจ้งเตือน LINE: %s · ผู้รับ %s%s" % (
                "เปิด" if cfg.get("alert", True) else "ปิด", st["alertTo"] or "หาไม่เจอ (ตั้งด้วย --alert-to)",
                (" · ส่งล่าสุด %s %s" % (st["alertLast"].get("at", ""), "ถึง" if st["alertLast"].get("ok")
                                         else "ไม่ถึง: %s" % st["alertLast"].get("error", ""))) if st["alertLast"] else ""))
            if st["failing"]:
                lines.append("กำลังบันทึกไม่ได้: %s" % st["failing"])
            wd = st.get("watchdog") or {}
            lines.append("ตัวเฝ้าระบบ: %s" % (("ตรวจล่าสุด %s · %s" % (wd.get("at"), "; ".join(wd.get("issues") or [])
                                                                       or "ปกติ")) if wd.get("at")
                                               else "ยังไม่เคยทำงาน (เริ่มเองเมื่อเว็บรันใต้ gunicorn)"))
            lines.append("ดู log ย้อนหลัง: manage.py leadsheet --log [--days 7]")
            if st["fallback"]:
                lines.append("ใบที่ลงแท็บเดิมรอย้ายไปแท็บใหม่ %d ใบ: %s" % (len(st["fallback"]), ", ".join(
                    "%s→%s" % (x["code"], x["want"]) for x in st["fallback"][-10:])))

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
