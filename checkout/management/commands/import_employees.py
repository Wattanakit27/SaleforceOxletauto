"""ย้ายทะเบียนพนักงานจากชีต → ฐานข้อมูลของเรา แล้วผูก LINE id ทุกบัญชีเข้ากับคน — ★ 16 ก.ย.69

    python manage.py import_employees                 # ดูเฉยๆ (ไม่เขียนอะไร)
    python manage.py import_employees --apply         # เขียนจริง
    python manage.py import_employees --out ผล.txt    # console ไทยเพี้ยน → เขียนไฟล์

เอาอะไรมาบ้าง: ชื่อเล่น · ชื่อที่ตั้งใน LINE · **ตำแหน่ง** · **เวลาเข้างาน** · วันหยุด · group id

ผูก LINE id เข้ากับคน 2 ทาง (เจ้าของสั่ง "แมทจาก display name เอา"):
  1. **LINE id ที่ตรงกับชีต** → ผูกได้เลย (นี่คือ id ฝั่งบอทเดิม)
  2. **ชื่อโปรไฟล์ LINE ตรงกัน** → ผูกได้ (ครอบ id ฝั่งบอทใหม่ ซึ่งชีตไม่มี)
     ตัดอิโมจิ/ช่องว่าง/ตัวพิมพ์ ก่อนเทียบ · **ชื่อซ้ำกันหลายคน = ไม่ผูก** (ไม่เดา)

หลังย้ายเสร็จ **แก้/เพิ่มพนักงานในระบบเราได้เลย ไม่ต้องกลับไปแก้ชีต** — ระบบอ่านทะเบียนในฐานข้อมูลก่อน
แล้วค่อยเติมจากชีตเฉพาะคนที่ยังไม่ได้ย้ายเข้ามา · รันซ้ำได้ (อัปเดตทับของเดิม ไม่สร้างซ้ำ)
"""
from django.core.management.base import BaseCommand

WORK_START, DAY_OFF = 7, 8      # คอลัมน์ในชีตพนักงาน (ต่อจาก position=6)


class Command(BaseCommand):
    help = "ย้ายทะเบียนพนักงาน (ชื่อ/ตำแหน่ง/เวลาเข้างาน) จากชีตเข้าฐานข้อมูล + ผูก LINE id"

    def add_arguments(self, p):
        p.add_argument("--apply", action="store_true", help="เขียนจริง (ไม่ใส่ = ดูเฉยๆ)")
        p.add_argument("--out", help="เขียนผลลงไฟล์ UTF-8")

    def handle(self, *a, **o):
        from collections import Counter
        from checkout import people
        from checkout.models import Employee, GroupChat, LineProfile
        from dashboard.services.google_sheets import fetch_sheet, EMPLOYEE_COL as EM

        L, add, apply = [], None, o["apply"]
        add = L.append
        add("โหมด: %s" % ("เขียนจริง" if apply else "ดูเฉยๆ (ใส่ --apply เพื่อเขียน)"))
        try:
            rows = fetch_sheet("employees")
        except Exception as e:
            add("⛔ อ่านชีตพนักงานไม่ได้: %s" % str(e)[:150])
            return self._emit(L, o)

        def cell(r, i):
            return (str(r[i]).strip() if i < len(r) and r[i] else "")

        # ── 1. อ่านชีต → รายคน ──
        staff, skipped = [], 0
        for r in rows:
            nick = cell(r, EM.nickname)
            dn = cell(r, EM.display_name)
            if not (nick or dn):
                skipped += 1
                continue
            staff.append({
                "nickname": (nick or dn)[:80],
                "display_name": dn[:120],
                "position": cell(r, EM.position)[:80],
                "work_start": cell(r, WORK_START)[:16],
                "day_off": cell(r, DAY_OFF)[:40],
                "group_id": cell(r, EM.group_id)[:64],
                "user_id": cell(r, EM.user_id),
            })
        add("ชีตมีพนักงาน %d คน%s" % (len(staff), (" (ข้ามแถวว่าง %d)" % skipped) if skipped else ""))

        dup_nick = [n for n, c in Counter(s["nickname"] for s in staff).items() if c > 1]
        if dup_nick:
            add("⚠️ ชื่อเล่นซ้ำในชีต: %s — จะเก็บแถวหลังสุดทับ" % ", ".join(dup_nick))

        # ── 2. เตรียมการจับคู่ชื่อโปรไฟล์ (ชื่อซ้ำ = ไม่ผูก) ──
        name_owner, name_dup = {}, set()
        for s in staff:
            key = people._norm(s["display_name"])
            if not key:
                continue
            if key in name_owner and name_owner[key] != s["nickname"]:
                name_dup.add(key)
            name_owner[key] = s["nickname"]
        for key in name_dup:
            name_owner.pop(key, None)
        uid_owner = {s["user_id"]: s["nickname"] for s in staff if s["user_id"]}

        # ── 3. เขียนทะเบียน ──
        created = updated = 0
        emp_of = {}
        for s in staff:
            fields = {k: s[k] for k in
                      ("display_name", "position", "work_start", "day_off", "group_id")}
            fields["source"] = Employee.SHEET
            if not apply:
                exists = Employee.objects.filter(nickname=s["nickname"]).exists()
                created += 0 if exists else 1
                updated += 1 if exists else 0
                continue
            obj, new = Employee.objects.update_or_create(nickname=s["nickname"], defaults=fields)
            emp_of[s["nickname"]] = obj
            created, updated = created + (1 if new else 0), updated + (0 if new else 1)
        add("ทะเบียนพนักงาน: %s %d คน · อัปเดต %d คน"
            % ("สร้าง" if apply else "จะสร้าง", created, updated))

        # ── 4. ผูก LINE id ของทุกบัญชีเข้ากับคน ──
        by_uid = by_name = 0
        unlinked = []
        for p in LineProfile.objects.all().only("user_id", "display_name", "nickname", "is_employee"):
            nick = uid_owner.get(p.user_id) or ""
            how = "uid"
            if not nick and p.display_name:
                nick = name_owner.get(people._norm(p.display_name), "")
                how = "name"
            if not nick:
                if p.source in ("group", "room") and not p.is_employee:
                    unlinked.append(p.display_name or p.user_id[:8])
                continue
            by_uid, by_name = (by_uid + 1, by_name) if how == "uid" else (by_uid, by_name + 1)
            if not apply:
                continue
            p.employee = emp_of.get(nick)
            p.nickname, p.is_employee = nick, True
            p.save(update_fields=["employee", "nickname", "is_employee"])
            GroupChat.objects.filter(sender_id=p.user_id).exclude(
                sender_name=nick).update(sender_name=nick[:80])
        add("ผูก LINE id: จาก id ในชีต %d บัญชี · จากชื่อโปรไฟล์ %d บัญชี (คนเดียวมีได้หลายบัญชี)"
            % (by_uid, by_name))

        if unlinked:
            add("")
            add("❔ คนในกลุ่มที่ยังผูกกับพนักงานไม่ได้ %d คน (ชื่อใน LINE ไม่ตรงกับชีต):" % len(unlinked))
            for n in unlinked[:30]:
                add("   %s" % n)
            if len(unlinked) > 30:
                add("   … อีก %d คน" % (len(unlinked) - 30))
            add("   → ถ้าเป็นพนักงานจริง เพิ่ม/แก้ชื่อในหน้า \"พนักงาน\" ของระบบ แล้วรันคำสั่งนี้ซ้ำ")

        add("")
        add("รวมในฐานข้อมูลตอนนี้: พนักงาน %d คน · ผูก LINE แล้ว %d บัญชี"
            % (Employee.objects.count(),
               LineProfile.objects.filter(employee__isnull=False).count()))
        if not apply:
            add("ยังไม่เขียนอะไร — ใส่ --apply เมื่อตรวจแล้วว่าถูกต้อง")
        self._emit(L, o)

    def _emit(self, L, o):
        report = "\n".join(L)
        if o.get("out"):
            with open(o["out"], "w", encoding="utf-8") as f:
                f.write(report)
            self.stdout.write("wrote -> %s" % o["out"])
        else:
            self.stdout.write(report)
