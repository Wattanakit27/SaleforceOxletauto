# -*- coding: utf-8 -*-
"""จ่ายลีดขายจากแชทอัตโนมัติ (★ 18 ต.ค.69) — ดูสถานะ / ตั้งโหมด / ทดลองย้อนหลัง / รายงานผลโหมดจดอย่างเดียว

  manage.py autochat                          สถานะ + การตัดสินล่าสุด
  manage.py autochat --backtest --days 7      ถ้าเปิดตอนนี้ ระบบจะทำอะไรกับแชทที่ยังไม่มีเลข (ไม่เขียนอะไรเลย)
  manage.py autochat --mode observe           ตั้งโหมด off | observe | on
  manage.py autochat --run                    ทำ 1 รอบเดี๋ยวนี้ (ตามโหมดที่ตั้ง)
  manage.py autochat --report --days 7        เทียบสิ่งที่ระบบตัดสิน กับที่แอดมินทำจริง
ทุกแบบรับ --out ไฟล์ (console ไทยบน Windows เพี้ยน) · ไม่มีชื่อ/เบอร์ลูกค้าในผล (อ้างเลขแชท)
"""
import io

from django.core.management.base import BaseCommand

D_NAME = {"would": "จะจ่าย", "assigned": "จ่ายแล้ว", "failed": "จ่ายไม่สำเร็จ", "skip": "ข้าม", "human": "แอดมินจ่ายแล้ว"}


class Command(BaseCommand):
    help = "จ่ายลีดขายจากแชทอัตโนมัติ — สถานะ / โหมด / ทดลองย้อนหลัง / รายงาน"

    def add_arguments(self, p):
        p.add_argument("--mode", choices=["off", "observe", "on"])
        p.add_argument("--run", action="store_true")
        p.add_argument("--backtest", action="store_true")
        p.add_argument("--report", action="store_true")
        p.add_argument("--days", type=int, default=7)
        p.add_argument("--out", default="")

    def handle(self, *a, **o):
        from checkout import autochat as AC
        from checkout import leadflow as LF
        out = []
        if o["mode"]:
            new, errs = LF.clean_cfg({"auto_chat": o["mode"]})
            if errs:
                out.append("ตั้งโหมดไม่สำเร็จ: " + " · ".join(errs))
            elif not LF.save_cfg(new):
                out.append("บันทึกไม่สำเร็จ (ฐานข้อมูลไม่ตอบ)")
            else:
                out.append("ตั้งโหมดเป็น: %s%s" % (AC.MODE_NAME[o["mode"]],
                                                   (" · นับลูกค้าที่ให้เบอร์/ID LINE ตั้งแต่ " + new["auto_chat_since"])
                                                   if new.get("auto_chat_since") else ""))
        if o["run"]:
            r = AC.run()
            out.append("รอบนี้: %s" % r)
        if o["backtest"]:
            r = AC.backtest(o["days"])
            sm = r["summary"]
            out += ["ทดลองย้อนหลัง %d วัน (ไม่เขียนอะไร) — แชทลีดขายที่ให้เบอร์/ID LINE แล้ว ยังไม่มีเลขในระบบ: %d ราย" % (r["days"], sm["total"]),
                    "  แอดมินจ่ายแล้ว (ตอนนี้จับได้ด้วยเบอร์/ID LINE): %d" % sm.get("human", 0),
                    "  ระบบจะจ่าย: %d" % sm.get("would", 0),
                    "  ข้ามให้แอดมินตัดสิน: %d" % sm.get("skip", 0)]
            out += ["    · %s: %d" % (k, n) for k, n in r["reasons"]]
            out.append("")
            out += [self._line(x) for x in r["rows"]]
        if o["report"]:
            r = AC.report(o["days"])
            sm = r["summary"]
            out += ["รายงานโหมดจดอย่างเดียว %d วัน" % r["days"],
                    "  ระบบจะจ่าย %d → แอดมินจ่ายเซลล์เดียวกัน %d · คนละเซลล์ %d · ยังไม่มีใครจ่าย %d" % (
                        sm["would"], sm["would_paid_same"], sm["would_paid_other"], sm["would_open"]),
                    "  ระบบข้าม %d → แอดมินจ่ายแล้ว %d · ยังไม่จ่าย %d" % (sm["skip"], sm["skip_paid"], sm["skip_open"]),
                    "  ระบบจ่ายจริง %d · ไม่สำเร็จ %d" % (sm["assigned"], sm["failed"])]
            out += ["    · %s: %d" % (k, n) for k, n in r["reasons"]]
            out.append("")
            out += ["  #%-5s %-4s %s · %s" % (x["chat"], x.get("ch") or "", x.get("verdict") or "", x.get("why") or "")
                    for x in r["rows"]]
        if not (o["mode"] or o["run"] or o["backtest"] or o["report"]):
            st = AC.status_json()
            L = st.get("last") or {}
            out += ["โหมด: %s%s" % (st["modeName"], (" · ตั้งแต่ " + st["since"]) if st.get("since") else ""),
                    "รอบล่าสุด: %s" % (L or "-"), ""]
            out += [self._line(x) for x in st.get("recent") or []]
        text = "\n".join(out) + "\n"
        if o["out"]:
            io.open(o["out"], "w", encoding="utf-8").write(text)
            self.stdout.write("เขียนผลลง %s แล้ว" % o["out"])
        else:
            self.stdout.write(text)

    @staticmethod
    def _line(x):
        return "  %s #%-5s %-4s %-12s %s%s" % (
            (x.get("at") or "")[5:16].replace("T", " "), x.get("chat"), x.get("ch") or "", D_NAME.get(x.get("d"), x.get("d")),
            ("→ @%s (%s) · " % (x["to"], x.get("pfx") or "")) if x.get("to") else "", x.get("why") or "")
