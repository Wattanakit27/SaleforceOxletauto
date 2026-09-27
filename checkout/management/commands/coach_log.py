"""เก็บบทสนทนาห้องโค้ชเซลล์ (Senior ↔ Junior) ลงชีต — ดู [coaching.py](../../coaching.py)

    python manage.py coach_log                          # ดูสถานะ + นับว่ามีอะไรรอเขียน
    python manage.py coach_log --dry-run --import-old    # ลองดูของเก่าก่อน (ไม่เขียนชีต)
    python manage.py coach_log --import-old              # นำเข้าของเก่า + ของใหม่ (ครั้งเดียวพอ)
    python manage.py coach_log --sync                    # เก็บของใหม่เข้าชีต
    python manage.py coach_log --seniors "อุ้ม,เฟิร์ส,โอ๊ต,นวล"
    python manage.py coach_log --group Cxxxx --on|--off   # ตั้งกลุ่ม / เปิด-ปิดซิงก์อัตโนมัติ

⚠️ console ภาษาไทยบน Windows เพี้ยน (cp874) → ใส่ `--out ไฟล์.txt` อ่านจากไฟล์แทน
⚠️ **เขียนต่อท้ายเท่านั้น ไม่เคยลบ** · รันซ้ำไม่เบิ้ล (ข้ามแถวที่ `รหัสอ้างอิง` มีอยู่แล้ว)
"""
import io

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "เก็บบทสนทนาห้องโค้ชเซลล์ลงชีต (Senior/Junior) + นำเข้าข้อมูลเก่า"

    def add_arguments(self, p):
        p.add_argument("--sync", action="store_true", help="เก็บแชทใหม่เข้าชีตเดี๋ยวนี้")
        p.add_argument("--import-old", action="store_true",
                       help="นำเข้าข้อมูลเก่าจากแท็บ 'Sheet A — Log' ด้วย")
        p.add_argument("--dry-run", action="store_true", help="คำนวณให้ดู ไม่เขียนชีต")
        p.add_argument("--days", type=int, default=120, help="ย้อนหลังกี่วัน (default 120)")
        p.add_argument("--group", help="LINE group id ของห้องโค้ช")
        p.add_argument("--seniors", help='รายชื่อซีเนียร์ คั่นด้วย , (เช่น "อุ้ม,เฟิร์ส")')
        p.add_argument("--on", action="store_true", help="เปิดซิงก์อัตโนมัติรายวัน")
        p.add_argument("--off", action="store_true", help="ปิดซิงก์อัตโนมัติ")
        p.add_argument("--out", help="เขียนผลลงไฟล์ (UTF-8)")

    def handle(self, *a, **o):
        from checkout import coaching as CO
        lines = []

        def say(s=""):
            lines.append(s)

        # ── ตั้งค่า ──
        upd = {}
        if o.get("group"):
            upd["group_id"] = o["group"].strip()
        if o.get("seniors"):
            upd["seniors"] = [s.strip() for s in o["seniors"].split(",") if s.strip()]
        if o.get("on"):
            upd["enabled"] = True
        if o.get("off"):
            upd["enabled"] = False
        if upd:
            CO.save_cfg(**upd)
            say("บันทึกการตั้งค่าแล้ว: %s" % ", ".join(sorted(upd)))

        c = CO.cfg()
        say("ห้องโค้ช      : %s" % c["group_id"])
        say("แท็บปลายทาง   : %s  (ไฟล์ %s)" % (c["tab"], CO.SHEET_ID))
        say("ซีเนียร์      : %s" % " · ".join(c["seniors"]))
        say("ซิงก์อัตโนมัติ: %s (วันละครั้งจาก cron_tick)"
            % ("เปิด" if c["enabled"] else "ปิด"))

        # จำนวนแชทที่บอทเก็บไว้แล้วในห้องนี้
        try:
            from checkout.models import GroupChat
            n = GroupChat.objects.filter(group_id=c["group_id"]).count()
            say("แชทที่เก็บไว้ : %d ข้อความ%s"
                % (n, "" if n else "  ← ยังไม่มีใครพิมพ์หลังบอทเข้ากลุ่ม"))
        except Exception as e:
            say("แชทที่เก็บไว้ : อ่านไม่ได้ (%s)" % str(e)[:80])

        run = o.get("sync") or o.get("import_old") or o.get("dry_run")
        if not run:
            say()
            say("ยังไม่ได้สั่งอะไร — ใส่ --sync (เก็บของใหม่) หรือ --import-old (รวมของเก่า)")
            say("แนะนำครั้งแรก: --dry-run --import-old  เพื่อดูก่อนว่าจะได้อะไร")
            return self._out(lines, o)

        say()
        try:
            r = CO.sync(days=o["days"], include_old=bool(o.get("import_old")),
                        dry_run=bool(o.get("dry_run")))
        except Exception as e:
            say("ล้มเหลว: %s" % e)
            return self._out(lines, o, err=True)

        ch = r.get("chat") or {}
        say("จากบอท (ย้อน %d วัน): ซีเนียร์ %d · จูเนียร์ %d · มีรหัสเคส %d%s"
            % (o["days"], ch.get("senior", 0), ch.get("junior", 0), ch.get("withCode", 0),
               (" · ไม่รู้ชื่อ %d" % ch["unnamed"]) if ch.get("unnamed") else ""))

        if "old" in r:
            od = r["old"]
            say("จากชีตเดิม %d แถว → แตกเป็น: ข้อความจูเนียร์ %d · ความเห็นซีเนียร์ %d "
                "· คำตอบบอท AI %d · ช่องที่ใช้ผิด %d"
                % (od["oldRows"], od["junior"], od["senior"], od["bot"], od["misplaced"]))
            say("   จับคู่ชื่อกับทะเบียนพนักงานได้ %d แถว" % od["matched"])
            un = sorted(od["unmatchedNames"].items(), key=lambda x: -x[1])
            if un:
                say("   ⚠️ ชื่อที่จับคู่ไม่ได้ (ใช้ชื่อ LINE ตามเดิม — แก้ได้ที่เมนู 'พนักงาน'):")
                for nm, cnt in un[:12]:
                    say("      %-32s %4d แถว" % (nm, cnt))

        say()
        say("รวมที่เตรียมได้ %d แถว · มีในชีตแล้ว %d · ใหม่ %d"
            % (r["candidates"], r["skipped"], r["new"]))
        if r.get("dryRun"):
            say("(ทดลอง — ยังไม่เขียนชีต)")
            for row in r.get("preview") or []:
                say("   | " + " | ".join(str(x)[:26] for x in row[:8]))
        else:
            say("เขียนลงแท็บ '%s' แล้ว %d แถว" % (r["tab"], r.get("written", 0)))
        return self._out(lines, o)

    def _out(self, lines, o, err=False):
        text = "\n".join(lines)
        if o.get("out"):
            with io.open(o["out"], "w", encoding="utf-8") as f:
                f.write(text + "\n")
            self.stdout.write("wrote %s (%d lines)" % (o["out"], len(lines)))
        else:
            for ln in lines:
                try:
                    self.stdout.write(ln)
                except UnicodeEncodeError:       # console cp874 — บอกทางออกแทนที่จะพัง
                    self.stdout.write(ln.encode("ascii", "replace").decode())
        if err:
            raise SystemExit(1)
