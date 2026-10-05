"""ตามแก้ชื่อเล่นที่คัดลอกไปเก็บไว้ที่อื่น ให้ตรงกับทะเบียนพนักงาน — ★ 6 ต.ค.69

เจ้าของแจ้ง: *"นิดตั้งค่าชื่อเล่นแล้ว แต่มันยังขึ้นเป็นชื่อ account อยู่"*
ต้นเหตุ: ชื่อเล่นถูกคัดลอกไปเก็บใน `LineProfile.nickname` / `GroupChat.sender_name` ตอนผูก
แล้วการแก้ชื่อในหน้า "พนักงาน" ไม่เคยตามไปแก้ (ตอนนี้แก้แล้ว — `people.propagate_nickname`)
คำสั่งนี้ไว้ซ่อมของที่ค้างอยู่ก่อนแก้ · รันซ้ำได้ ไม่มีอะไรเปลี่ยน = ไม่แตะ

    python manage.py sync_employee_names            # ดูเฉยๆ ว่าจะแก้ใครบ้าง
    python manage.py sync_employee_names --apply    # แก้จริง
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "แก้ชื่อเล่นในโปรไฟล์ LINE / ชื่อผู้ส่งในแชท ให้ตรงกับทะเบียนพนักงาน"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="แก้จริง (ไม่ใส่ = ดูเฉยๆ)")
        parser.add_argument("--out", default="", help="เขียนผลลงไฟล์ (console ไทยบน Windows เพี้ยน)")

    def handle(self, *args, **o):
        from checkout import people
        from checkout.models import Employee, GroupChat, LineProfile

        lines = []
        add = lines.append
        todo = 0
        for e in Employee.objects.all().order_by("id"):
            nick = (e.nickname or "").strip()
            if not nick:
                continue
            profs = LineProfile.objects.filter(employee=e)
            uids = list(profs.values_list("user_id", flat=True))
            p_old = sorted(set(profs.exclude(nickname=nick).values_list("nickname", flat=True)))
            m_old = (GroupChat.objects.filter(sender_id__in=uids).exclude(direction=GroupChat.OUT)
                     .exclude(sender_name=nick).count()) if uids else 0
            r_old = GroupChat.objects.filter(sent_by=e).exclude(sent_by_name=nick).count()
            if not (p_old or m_old or r_old):
                continue
            todo += 1
            add("- %s: โปรไฟล์ LINE %s · ข้อความที่เขาพิมพ์ %d · ข้อความที่เขาตอบลูกค้า %d"
                % (nick, ("ชื่อเดิม " + ", ".join('"%s"' % x for x in p_old)) if p_old else "ตรงแล้ว",
                   m_old, r_old))
            if o["apply"]:
                res = people.propagate_nickname(e)
                add("    แก้แล้ว: %s" % res)

        head = ("ชื่อไม่ตรงทะเบียน %d คน" % todo) if todo else "ทุกคนตรงกับทะเบียนแล้ว"
        if todo and not o["apply"]:
            head += " — ยังไม่ได้แก้ (ใส่ --apply เพื่อแก้จริง)"
        text = "\n".join([head] + lines) + "\n"
        if o["out"]:
            with open(o["out"], "w", encoding="utf-8") as f:
                f.write(text)
            self.stdout.write("เขียนผลลง %s" % o["out"])
        else:
            self.stdout.write(text)
