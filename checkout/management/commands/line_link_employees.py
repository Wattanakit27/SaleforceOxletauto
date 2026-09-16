"""จับคู่ "คนที่พิมพ์ผ่านบอทใหม่" กับพนักงาน โดยใช้ชื่อโปรไฟล์ LINE — ★ ก.ย.69

    python manage.py line_link_employees                 # ดูเฉยๆ (ไม่เขียนอะไร)
    python manage.py line_link_employees --apply         # บันทึกลงฐานข้อมูลเรา
    python manage.py line_link_employees --out ผล.txt    # console ไทยเพี้ยน → เขียนไฟล์
    python manage.py line_link_employees --include-dm    # รวมคนที่ทักเข้า 1:1 ด้วย (ปกติไม่รวม)

ทำไมต้องมี: **LINE ออก userId ต่อ provider** — ชีตพนักงานเก็บ id ของบอทเดิม พอกลุ่มเปลี่ยนมา
ใช้บอทใหม่ ทุก id ที่วิ่งเข้ามาเป็นคนละชุด (วัดจริง 16/09: บอทเดิมได้ยิน 48 คน จับคู่ชีตได้ 46 ·
บอทใหม่ได้ยิน 45 คน จับคู่ได้ **0**) → พนักงานถูกนับเป็นคนนอก และหน้าเว็บโชว์ชื่อ LINE แทนชื่อเล่น

วิธีจับคู่: **ชื่อโปรไฟล์ LINE เป็นของคนนั้น ไม่เปลี่ยนตามบอท** → เอาชื่อที่เก็บไว้ในตาราง
`LineProfile` มาเทียบกับชีตพนักงาน (อ่านอย่างเดียว ไม่เขียนกลับชีต) แล้ว **เก็บผลไว้ในฐานข้อมูลเรา**
(`nickname` + `is_employee`) · ตั้งแต่นั้นระบบจำ id ใหม่ของคนนั้นได้เอง ไม่ต้องเทียบชื่อซ้ำ

**ไม่เดา** — ชื่อต้องตรงกับชีต (ตัดอิโมจิ/ช่องว่าง/ตัวพิมพ์ใหญ่เล็กก่อนเทียบ) ไม่ตรง = ไม่แตะ
แล้วลิสต์ให้ดูว่าเหลือใครบ้าง จะได้ไปเติมชื่อในชีตหรือปล่อยไว้ก็ได้

⚠️ ค่าเริ่มต้นดูเฉพาะ **คนที่พิมพ์ในกลุ่มบริษัท** — ไม่แตะคนที่ทักเข้า 1:1 (นั่นคือลูกค้า
ถ้าบังเอิญตั้งชื่อ LINE ซ้ำกับพนักงานจะกลายเป็นจับคู่ผิด) · จำเป็นจริงค่อยใส่ `--include-dm`
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "จับคู่คนที่มาจากบอทใหม่กับพนักงาน ด้วยชื่อโปรไฟล์ LINE (เก็บผลในฐานข้อมูลเรา)"

    def add_arguments(self, p):
        p.add_argument("--apply", action="store_true", help="บันทึกจริง (ไม่ใส่ = ดูเฉยๆ)")
        p.add_argument("--include-dm", action="store_true", help="รวมคนที่ทักเข้าแชท 1:1 ด้วย")
        p.add_argument("--out", help="เขียนผลลงไฟล์ UTF-8")

    def handle(self, *a, **o):
        from checkout import people
        from checkout.models import GroupChat, LineProfile

        L = []
        add = L.append
        apply = o["apply"]
        add("โหมด: %s" % ("บันทึกจริง" if apply else "ดูเฉยๆ (ใส่ --apply เพื่อบันทึก)"))

        rows = LineProfile.objects.filter(is_employee=False).exclude(display_name="")
        if not o["include_dm"]:
            rows = rows.filter(source__in=("group", "room"))
        rows = list(rows.order_by("-msg_count"))
        add("คนที่ยังไม่ถูกนับเป็นพนักงาน: %d คน%s"
            % (len(rows), "" if o["include_dm"] else " (เฉพาะคนที่พิมพ์ในกลุ่ม)"))

        try:
            people._load(force=True)          # โหลดชีตสดก่อนเทียบ (cache 10 นาทีอาจเก่า)
        except Exception as e:
            add("⛔ อ่านชีตพนักงานไม่ได้: %s" % str(e)[:150])
            return self._emit(L, o)
        if not people._CACHE["by_name"]:
            add("⛔ ชีตพนักงานว่าง/อ่านไม่ได้ — ยังเทียบชื่อไม่ได้")
            return self._emit(L, o)

        hit, miss, renamed = [], [], 0
        for p in rows:
            nick = ""
            try:
                nick = people.employee_nick_by_name(p.display_name)
            except Exception:
                nick = ""
            if nick:
                hit.append((p, nick))
            else:
                miss.append(p)

        add("")
        add("✅ เทียบชื่อกับชีตได้ %d คน" % len(hit))
        for p, nick in hit:
            add("   %-28s → %s   (%d ข้อความ)" % (p.display_name[:28], nick, p.msg_count or 0))
            if apply:
                p.nickname, p.is_employee = nick, True
                p.save(update_fields=["nickname", "is_employee"])
                # ข้อความเก่าที่จดชื่อ LINE ไว้ → เปลี่ยนเป็นชื่อเล่น (หน้าเว็บอ่านรู้เรื่องย้อนหลัง)
                renamed += GroupChat.objects.filter(sender_id=p.user_id).exclude(
                    sender_name=nick).update(sender_name=nick[:80])

        add("")
        add("❔ เทียบไม่ได้ %d คน — ไม่แตะ (อาจเป็นคนนอก หรือชื่อใน LINE ไม่ตรงกับชีต)" % len(miss))
        for p in miss[:40]:
            add("   %-28s (%d ข้อความ · ล่าสุด %s)"
                % (p.display_name[:28], p.msg_count or 0,
                   p.last_seen.strftime("%d/%m") if p.last_seen else "-"))
        if len(miss) > 40:
            add("   … อีก %d คน" % (len(miss) - 40))

        add("")
        if apply:
            add("บันทึกแล้ว: ตั้งเป็นพนักงาน %d คน · แก้ชื่อในข้อความเก่า %d ข้อความ" % (len(hit), renamed))
            add("ต่อจากนี้ระบบจำ id ฝั่งบอทใหม่ของคนพวกนี้ได้เอง ไม่ต้องรันซ้ำ")
        else:
            add("ยังไม่เขียนอะไร — ใส่ --apply เมื่อตรวจรายชื่อข้างบนแล้วว่าถูกต้อง")
        self._emit(L, o)

    def _emit(self, L, o):
        report = "\n".join(L)
        if o.get("out"):
            with open(o["out"], "w", encoding="utf-8") as f:
                f.write(report)
            self.stdout.write("wrote -> %s" % o["out"])
        else:
            self.stdout.write(report)
