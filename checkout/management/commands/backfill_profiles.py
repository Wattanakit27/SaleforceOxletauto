"""เติมโปรไฟล์ LINE ให้คนที่มีแชทอยู่ในคลังแต่ยังไม่มีแถวใน LineProfile — ★ ก.ย.69

    python manage.py backfill_profiles --dry-run      # ดูว่าจะเติมกี่คน ไม่เขียนอะไร
    python manage.py backfill_profiles                # เติมจริง
    python manage.py backfill_profiles --limit 20     # ลองทีละนิดก่อน

ทำไมต้องมี: บั๊กใน `people.fetch_profile` (12-16 ก.ย.69) ทำให้คนที่ทักเข้ามาใหม่
**ไม่ถูกสร้างโปรไฟล์เลย** ทั้งที่ข้อความถูกเก็บครบ · แก้บั๊กแล้วจะมีโปรไฟล์ก็ต่อเมื่อเขาทักมาอีกครั้ง
→ คนที่ทักมาแล้วเงียบไปจะหายจากตารางโปรไฟล์ถาวร · คำสั่งนี้เติมย้อนหลังจากคลังแชทที่มีอยู่

**ไม่ใช้ `touch_profile()` ตรงๆ** เพราะมันถูกออกแบบให้เรียก "ทีละข้อความ":
จะตั้ง `first_seen` = ตอนนี้ และนับ `msg_count` = 1 ซึ่งผิดสำหรับการเติมย้อนหลัง
→ ที่นี่คำนวณจากคลังแชทจริง (ทักครั้งแรก/ล่าสุด/จำนวนข้อความ/บัญชีที่เคยเห็น)

⚠️ ต้องรันบนเซิร์ฟเวอร์ (ใช้ LINE token ใน .env + เขียนฐานข้อมูล)
⚠️ ดึงโปรไฟล์ได้เฉพาะคนที่ยังเป็นเพื่อนกับบอท/ยังอยู่ในกลุ่ม · คนที่บล็อกไปแล้วได้แถวที่ไม่มีชื่อ
"""
import time

from django.core.management.base import BaseCommand
from django.db.models import Count, Max, Min
from django.utils import timezone


class Command(BaseCommand):
    help = "เติม LineProfile ย้อนหลังให้คนที่มีแชทแต่ยังไม่มีโปรไฟล์"

    def add_arguments(self, p):
        p.add_argument("--dry-run", action="store_true", help="ดูเฉยๆ ไม่เขียน ไม่ยิง LINE")
        p.add_argument("--limit", type=int, default=0, help="ทำแค่ N คนแรก (0 = ทั้งหมด)")
        p.add_argument("--out", help="เขียนสรุปลงไฟล์ (กัน console ไทยเพี้ยน)")

    def handle(self, *a, **o):
        from checkout import people
        from checkout.models import GroupChat, LineProfile

        L = []
        add = L.append
        have = set(LineProfile.objects.values_list("user_id", flat=True))
        rows = (GroupChat.objects.exclude(sender_id="")
                .values("sender_id")
                .annotate(n=Count("id"), first=Min("sent_at"), last=Max("sent_at"))
                .order_by("-last"))
        todo = [r for r in rows if r["sender_id"] not in have]
        if o["limit"]:
            todo = todo[:o["limit"]]

        add("คนที่มีแชทแต่ไม่มีโปรไฟล์: %d คน" % len(todo))
        if o["dry_run"]:
            add("(--dry-run · ยังไม่เขียน/ไม่ยิง LINE)")
            self._emit(L, o)
            return

        made = named = emp = failed = 0
        now = timezone.now()
        for r in todo:
            uid = r["sender_id"]
            # ข้อความแรกของคนนี้ = ที่มา (1:1 หรือกลุ่ม) + บัญชีที่เจอครั้งแรก
            first_msg = (GroupChat.objects.filter(sender_id=uid)
                         .order_by("sent_at", "id").values("chat_type", "group_id", "channel").first()) or {}
            chans = [c for c in GroupChat.objects.filter(sender_id=uid).exclude(channel="")
                     .values_list("channel", flat=True).distinct() if c]
            last_gid = (GroupChat.objects.filter(sender_id=uid).exclude(group_id="")
                        .order_by("-sent_at").values_list("group_id", flat=True).first()) or ""
            try:
                n = people.nickname_for(user_id=uid)
                nick = "" if n == "ไม่ทราบชื่อ" else n
            except Exception:
                nick = ""
            prof = {}
            if not nick:
                try:
                    prof = people.fetch_profile(uid, group_id=last_gid,
                                                channel=first_msg.get("channel") or "")
                except Exception as e:
                    add("  ⚠️ ดึงโปรไฟล์ %s… ไม่ได้: %s" % (uid[:8], e))
                time.sleep(0.05)          # ไม่ยิง LINE รัวเกินไป
            ctype = first_msg.get("chat_type") or "user"
            try:
                LineProfile.objects.create(
                    user_id=uid,
                    display_name=(prof.get("displayName") or "")[:120],
                    status_message=prof.get("statusMessage") or "",
                    language=(prof.get("language") or "")[:16],
                    nickname=nick,
                    is_employee=bool(nick),
                    source=ctype if ctype in ("user", "group", "room") else "user",
                    group_id=first_msg.get("group_id") or "",
                    channel=first_msg.get("channel") or "",
                    channels=chans,
                    msg_count=r["n"],
                    first_seen=r["first"] or now,
                    last_seen=r["last"] or now,
                    fetched_at=now if prof else None,
                    raw={k: v for k, v in prof.items() if k != "pictureUrl"},
                )
                made += 1
                emp += 1 if nick else 0
                name = nick or prof.get("displayName") or ""
                if name:
                    named += 1
                    # ข้อความเก่าที่ชื่อผู้ส่งว่าง → เติมให้ (หน้าสถานะ/แชทจะอ่านรู้เรื่อง)
                    GroupChat.objects.filter(sender_id=uid, sender_name="").update(sender_name=name[:80])
            except Exception as e:
                failed += 1
                add("  ❌ สร้างโปรไฟล์ %s… ไม่ได้: %s: %s" % (uid[:8], type(e).__name__, str(e)[:120]))

        add("")
        add("✅ สร้างโปรไฟล์ %d คน (พนักงาน %d · ลูกค้า %d) · ได้ชื่อ %d คน · พลาด %d"
            % (made, emp, made - emp, named, failed))
        if made - named:
            add("   ไม่ได้ชื่อ %d คน = บล็อกบอท/ออกจากกลุ่มไปแล้ว LINE ไม่ให้ดึงโปรไฟล์ (ปกติ)" % (made - named))
        self._emit(L, o)

    def _emit(self, L, o):
        report = "\n".join(L)
        if o.get("out"):
            with open(o["out"], "w", encoding="utf-8") as f:
                f.write(report)
            self.stdout.write("wrote -> %s" % o["out"])
        else:
            self.stdout.write(report)
