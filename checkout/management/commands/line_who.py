"""หา LINE user id ของคน จากชื่อ (หรือหาชื่อ จาก user id) — ★ ก.ย.69

    python manage.py line_who วัฒนกิจ
    python manage.py line_who U1cb2b9...        # ใส่ id มา = บอกว่าเป็นใคร
    python manage.py line_who --all             # ลิสต์คนที่เคยคุยกับบอททั้งหมด

ทำไมต้องมี: เวลาจะ **ทักกลับหาลูกค้า** ต้องใช้ user id ไม่ใช่ชื่อ
แต่ id ไม่ได้โผล่ในหน้าเว็บทุกที่ (พนักงานตั้งใจซ่อน) → ต้องมีทางค้นจากบรรทัดคำสั่ง

ค้น 3 แหล่งพร้อมกัน เพราะคนละแหล่งรู้คนละกลุ่ม:
  1. `LineProfile`  — คนที่เคยคุยกับบอท (ลูกค้า + พนักงานที่พิมพ์ในกลุ่ม)
  2. `GroupChat`    — เผื่อมีแถวแชทแต่ยังไม่มีโปรไฟล์ (ข้อความเก่าก่อนทำตารางโปรไฟล์)
  3. ชีตพนักงาน     — พนักงานที่ยังไม่เคยพิมพ์ผ่านบอทเลย
"""
from django.core.management.base import BaseCommand


def _norm(s):
    return (s or "").strip().lower()


class Command(BaseCommand):
    help = "หา LINE user id จากชื่อ (หรือหาชื่อจาก user id)"

    def add_arguments(self, p):
        p.add_argument("q", nargs="?", default="", help="ชื่อ / ชื่อเล่น / LINE user id")
        p.add_argument("--all", action="store_true", help="ลิสต์ทุกคนที่เคยคุยกับบอท")
        p.add_argument("--out", help="เขียนผลลงไฟล์ (UTF-8) — กัน console ไทยเพี้ยน")

    def handle(self, *a, **o):
        L = []
        add = L.append
        q = _norm(o.get("q"))
        show_all = o.get("all")
        if not q and not show_all:
            add("ใส่ชื่อที่จะค้นด้วย เช่น:  manage.py line_who วัฒนกิจ")
            self.stdout.write("\n".join(L))
            return

        hit = lambda *vals: show_all or any(q in _norm(v) for v in vals)

        # --- 1) โปรไฟล์คนที่เคยคุยกับบอท ---
        add("=" * 64)
        add("คนที่เคยคุยกับบอท (ตาราง LineProfile)")
        add("=" * 64)
        n = 0
        try:
            from checkout.models import LineProfile
            for p in LineProfile.objects.order_by("-last_seen")[:2000]:
                if not hit(p.display_name, p.nickname, p.user_id):
                    continue
                n += 1
                add("  %s" % p.user_id)
                add("     ชื่อ      : %s%s" % (p.show_name,
                                               "  (พนักงาน)" if p.is_employee else "  (ลูกค้า)"))
                if p.status_message:
                    add("     สเตตัส    : %s" % p.status_message[:60])
                add("     คุยมาแล้ว : %d ข้อความ · ล่าสุด %s"
                    % (p.msg_count, p.last_seen.strftime("%d/%m/%y %H:%M") if p.last_seen else "-"))
        except Exception as e:
            add("  ⚠️ อ่านตารางไม่ได้ (%s) — migrate ครบหรือยัง?" % e)
        if not n:
            add("  (ไม่เจอ)")

        # --- 2) เผื่อมีแถวแชทแต่ยังไม่มีโปรไฟล์ (ข้อความก่อนทำตารางโปรไฟล์) ---
        try:
            from checkout.models import GroupChat, LineProfile
            known = set(LineProfile.objects.values_list("user_id", flat=True))
            rows = {}
            for c in GroupChat.objects.exclude(sender_id="").order_by("-sent_at")[:3000]:
                if c.sender_id in known or c.sender_id in rows:
                    continue
                if not hit(c.sender_name, c.sender_id):
                    continue
                rows[c.sender_id] = c
            if rows:
                add("")
                add("มีแถวแชทแต่ยังไม่มีโปรไฟล์ (ข้อความเก่ากว่าตอนเริ่มเก็บโปรไฟล์)")
                add("-" * 64)
                for uid, c in rows.items():
                    add("  %s" % uid)
                    add("     ชื่อ      : %s · ล่าสุด %s"
                        % (c.sender_name or "(ไม่รู้ชื่อ)",
                           c.sent_at.strftime("%d/%m/%y %H:%M") if c.sent_at else "-"))
        except Exception:
            pass

        # --- 3) ชีตพนักงาน (คนที่ยังไม่เคยพิมพ์ผ่านบอท) ---
        if q:
            try:
                from dashboard.services.google_sheets import fetch_sheet, EMPLOYEE_COL as EM
                out = []
                for r in fetch_sheet("employees"):
                    cell = lambda i: (str(r[i]).strip() if i < len(r) and r[i] else "")
                    uid, dn, nick = cell(EM.user_id), cell(EM.display_name), cell(EM.nickname)
                    if uid and (q in _norm(dn) or q in _norm(nick) or q in _norm(uid)):
                        out.append("  %s   %s / %s" % (uid, nick or "-", dn or "-"))
                if out:
                    add("")
                    add("จากชีตพนักงาน")
                    add("-" * 64)
                    L.extend(out)
            except Exception as e:
                add("")
                add("  (อ่านชีตพนักงานไม่ได้: %s)" % e)

        report = "\n".join(L)
        if o.get("out"):
            with open(o["out"], "w", encoding="utf-8") as f:
                f.write(report)
            self.stdout.write("wrote -> %s" % o["out"])
        else:
            self.stdout.write(report)
