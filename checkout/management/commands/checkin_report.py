# -*- coding: utf-8 -*-
"""สร้างตารางเช็คชื่อเป็นรูป แล้วส่งเข้า LINE — ★ 16 ก.ย.69 (เจ้าของขอ)

    python manage.py checkin_report --to วัฒนกิจ            # ส่งเข้าแชทส่วนตัวคนนั้น (ทดสอบ)
    python manage.py checkin_report --to Uxxxxxxxx          # ใส่ LINE id ตรงๆ ก็ได้
    python manage.py checkin_report --to Cxxxxxxxx          # ส่งเข้ากลุ่ม
    python manage.py checkin_report --dry-run               # ดูว่าตารางจะออกมายังไง ไม่ส่ง
    python manage.py checkin_report --out /tmp/x.png        # สร้างรูปเก็บไว้ดูเฉยๆ
    python manage.py checkin_report --date 2026-09-15       # ย้อนวัน

⚠️ **ส่งรูปได้จริงเฉพาะบนเซิร์ฟเวอร์จริง** — LINE ต้องไปดึงรูปจาก URL https สาธารณะ
⚠️ console ของ Windows เป็น cp874 ภาษาไทยอาจเพี้ยน → ใช้ `--out` เขียนไฟล์แทน
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "สร้างตารางเช็คชื่อเป็นรูป + ส่งเข้า LINE (ไม่ใช้บริการแปลงรูปภายนอก)"

    def add_arguments(self, p):
        p.add_argument("--to", default="", help="ชื่อเล่นพนักงาน หรือ LINE id (U…/C…)")
        p.add_argument("--date", default="", help="YYYY-MM-DD (ไม่ใส่ = วันนี้)")
        p.add_argument("--out", default="", help="เซฟรูปไว้ที่ไฟล์นี้ (ไม่ส่ง LINE)")
        p.add_argument("--dry-run", action="store_true", help="ดูสรุป ไม่สร้างรูป ไม่ส่ง")
        p.add_argument("--no-tag", action="store_true", help="ไม่ต้องแท็กคนที่ยังไม่เช็คชื่อ")
        p.add_argument("--escalate", action="store_true",
                       help='ส่ง "ข้อความรอบสาย" แทนรูปตาราง (ตามคนที่ยังไม่เช็ค + แท็กผู้บริหาร)')

    # ── ชื่อเล่น → LINE id (ไม่ต้องให้คนไปหา id เอง) ──
    def _resolve(self, who):
        who = (who or "").strip()
        if not who or who[0] in "UCR" and len(who) > 20:
            return who, ""
        from checkout.models import Employee, LineProfile
        e = (Employee.objects.filter(nickname__iexact=who).first()
             or Employee.objects.filter(nickname__icontains=who).first()
             or Employee.objects.filter(display_name__icontains=who).first())
        if not e:
            return "", "หาพนักงานชื่อ '%s' ไม่เจอในทะเบียน" % who
        # แชทส่วนตัวส่งได้เฉพาะบัญชีที่เขาเพิ่มเป็นเพื่อนไว้ → เอาไอดีฝั่ง dm_token ก่อน
        from dashboard.services.line_channels import dm_token
        want = ""
        try:
            from dashboard.services.line_channels import accounts
            for a in accounts():
                if a.get("token") == dm_token():
                    want = a.get("key") or ""
                    break
        except Exception:
            want = ""
        profs = list(LineProfile.objects.filter(employee_id=e.id))
        if not profs:
            return "", "'%s' ยังไม่ได้ผูกบัญชี LINE — ให้เขาพิมพ์ในกลุ่มสัก 1 ครั้งก่อน" % e.nickname
        pick = next((p for p in profs if p.channel == want), None)
        if not pick:
            # ★ ไอดีออกต่อ provider — เอาไอดีของบอทอีกตัวไปส่ง LINE จะตอบ 400 แบบไม่บอกสาเหตุ
            #   เตือนตรงนี้ดีกว่าปล่อยให้ไปงงที่ข้อความ error ของ LINE
            have = ", ".join(sorted({p.channel or "?" for p in profs}))
            self.stdout.write(self.style.WARNING(
                "  ⚠️ '%s' มีไอดีของบัญชี [%s] แต่แชทส่วนตัวส่งออกจากบัญชี '%s' — "
                "ถ้าส่งไม่ผ่าน ให้เขาแอดบอทตัวนั้นเป็นเพื่อนแล้วทักมาสัก 1 ครั้ง"
                % (e.nickname, have, want or "(ยังไม่ตั้ง)")))
            pick = profs[0]
        return pick.user_id, ""

    def handle(self, *a, **o):
        from datetime import date
        from checkout import checkin_report as R

        day = None
        if o["date"]:
            try:
                day = date.fromisoformat(o["date"])
            except ValueError:
                self.stderr.write("รูปแบบวันที่ผิด ต้องเป็น YYYY-MM-DD")
                return

        data = R.collect(day)
        c = data["counts"]
        self.stdout.write("วัน%s %s" % (data["dayName"], data["date"]))
        self.stdout.write("  ในตาราง %d คน · ตรงเวลา %d · สาย %d · ยังไม่เช็คชื่อ %d · วันหยุด %d"
                          % (c["total"], c["ontime"], c["late"], c["missing"], c["off"]))
        for team, rows in data["groups"]:
            self.stdout.write("  [%s] %d คน" % (team, len(rows)))
        if data["missing"]:
            self.stdout.write("  ต้องแท็ก: " + ", ".join(m["name"] for m in data["missing"]))

        if o["escalate"]:
            ch = R.push_channel()
            mgr = R.managers(ch)
            named = ", ".join("%s%s" % (m["name"], "" if m["userId"] else " (แท็กไม่ได้)")
                              for m in mgr)
            self.stdout.write("  จะแท็กผู้บริหาร: %s"
                              % (named or "(ยังไม่ได้ติ๊กใครในหน้าพนักงาน)"))
            # ★ บอกล่วงหน้าว่าถ้าส่งเข้ากลุ่มจริงจะแท็กได้กี่คน — ไม่งั้นไปรู้เอาตอนส่งจริง
            ok_n, all_n, no_tag = R.tag_coverage(data["missing"], ch)
            self.stdout.write("  ถ้าส่งเข้ากลุ่ม (บัญชี '%s') จะแท็กได้ %d/%d คน"
                              % (ch or "?", ok_n, all_n))
            if no_tag:
                self.stdout.write("    แท็กไม่ได้ (จะพิมพ์ชื่อแทน): " + ", ".join(no_tag))

        if o["dry_run"]:
            if o["escalate"]:
                for m in R.escalation_messages(data, "", mention=False):
                    self.stdout.write("\n--- ข้อความที่จะส่ง (โหมดอ่านง่าย ไม่ใส่แท็ก) ---\n" + m["text"])
            self.stdout.write("\n(--dry-run: ไม่ส่ง)")
            return

        if o["escalate"]:
            if not o["to"]:
                self.stderr.write("ต้องใส่ --to ด้วย")
                return
            target, err = self._resolve(o["to"])
            if err:
                self.stderr.write(err)
                return
            ok, msg = R.send_escalation(target, day)
            self.stdout.write(("\nส่งแล้ว: " if ok else "\nส่งไม่สำเร็จ: ") + str(msg))
            return

        if o["out"] or not o["to"]:
            path = R.render_png(data, o["out"])
            self.stdout.write("\nรูป: %s" % path)
            if not o["to"]:
                self.stdout.write("ยังไม่ได้ใส่ --to จึงไม่ส่ง")
            return

        target, err = self._resolve(o["to"])
        if err:
            self.stderr.write(err)
            return
        ok, msg = R.send(target, day, tag=not o["no_tag"])
        self.stdout.write(("\nส่งแล้ว: " if ok else "\nส่งไม่สำเร็จ: ") + str(msg))
