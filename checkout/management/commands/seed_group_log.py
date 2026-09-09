"""นำเข้า log กลุ่ม LINE จริง → GroupMessage (โหมดเฝ้าดู) + รายงานว่าระบบตีความได้แค่ไหน

    python manage.py seed_group_log --dry-run            # แค่วัดผล ไม่เขียน DB
    python manage.py seed_group_log --clear              # ล้างของเดิมแล้วใส่ใหม่
    python manage.py seed_group_log --out report.txt     # เขียนรายงานเป็นไฟล์ (กัน console ไทยเพี้ยน)

เจตนา: เอาบทสนทนาจริงมาป้อนหน้า /checkout/observe/ เพื่อ "เห็นของจริง" ตั้งแต่วันแรก
       ไม่ต้องรอบอทเข้ากลุ่มแล้วเก็บข้อความเองเป็นสัปดาห์ · ไม่สร้างเคสเบิก-คืนใดๆ ทั้งสิ้น
"""
import os
import re
from datetime import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from checkout import parser as P
from checkout.models import GroupMessage

DEFAULT_FILE = os.path.join("checkout", "samples", "group_log_sep69.txt")
SAMPLE_GROUP_ID = "SAMPLE_LOG"      # group id ปลอมของชุดตัวอย่าง (แยกจากกลุ่มจริงชัดเจน)

# ชื่อผู้ส่งที่มีช่องว่างในตัวเอง — ต้องรู้ก่อนถึงตัดชื่อออกจากข้อความได้ถูก
MULTIWORD_SENDERS = [
    "🪷Jay. OxletAuto📜👑",
    "เมตตา สัตย์ธรรม🚘🚔🚖",
    "เซลมัท OxletAuto",
]

# ข้อความที่ LINE สร้างเอง ไม่ใช่คนพิมพ์ → ไม่เอามาวัดความแม่น
_SYSTEM_TEXTS = ["เขียนโน้ตใหม่", "ยกเลิกข้อความ", "ออกจากกลุ่ม", "เพิ่มประกาศ",
                 "เพิ่ม<u>ประกาศ</u>"]
_TYPE_MAP = {"รูป": "image", "วิดีโอ": "video", "สติกเกอร์": "sticker"}

_DATE_RE = re.compile(r"^(\d{4})\.(\d{2})\.(\d{2})")
_MSG_RE = re.compile(r"^(\d{1,2}):(\d{2})\s+(.*)$")


def _split_sender(rest):
    """แยก 'ชื่อผู้ส่ง' ออกจากข้อความ — เช็คชื่อที่มีช่องว่างก่อน แล้วค่อยตัดคำแรก"""
    for name in MULTIWORD_SENDERS:
        if rest.startswith(name + " "):
            return name, rest[len(name) + 1:]
        if rest == name:
            return name, ""
    parts = rest.split(" ", 1)
    return parts[0], (parts[1] if len(parts) > 1 else "")


def _msg_type(text):
    if text in _TYPE_MAP:
        return _TYPE_MAP[text]
    if any(s in text for s in _SYSTEM_TEXTS):
        return "system"
    if "maps.google.com/maps?q=" in text:
        return "location"
    return "text"


def read_log(path):
    """คืน list ของ dict {at, sender, text, type} เรียงตามเวลา"""
    rows, day = [], None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n").strip()
            if not line or line.startswith("#"):
                continue
            d = _DATE_RE.match(line)
            if d:
                day = datetime(int(d.group(1)), int(d.group(2)), int(d.group(3)))
                continue
            m = _MSG_RE.match(line)
            if not m or day is None:
                continue
            sender, text = _split_sender(m.group(3))
            at = day.replace(hour=int(m.group(1)), minute=int(m.group(2)))
            rows.append({"at": at, "sender": sender, "text": text, "type": _msg_type(text)})
    return rows


def analyse(rows):
    """ป้อนทุกข้อความเข้า parser แล้วสรุปว่าจับได้/พลาดอะไร"""
    out = []
    for r in rows:
        res = P.parse(r["text"]) if r["type"] == "text" else P.parse("")
        out.append(dict(r, **{"p": res}))
    return out


def pair_movements(items):
    """จับคู่ เบิก→คืน ต่อคน (เรียงเวลา) — ตอบว่า "ใครเบิกแล้วไม่คืน" ได้ไหม
    คืน (pairs, open_out, orphan_in)"""
    openv, pairs, orphan_in = {}, [], []
    for it in items:
        k = it["p"]["kind"]
        if k == "out":
            if it["sender"] in openv:          # เบิกซ้อนโดยยังไม่คืน = คู่เก่าค้าง
                pairs.append((openv.pop(it["sender"]), None))
            openv[it["sender"]] = it
        elif k == "in":
            prev = openv.pop(it["sender"], None)
            if prev:
                pairs.append((prev, it))
            else:
                orphan_in.append(it)
    return pairs, list(openv.values()), orphan_in


class Command(BaseCommand):
    help = "นำเข้า log กลุ่ม LINE ตัวอย่าง เข้าโหมดเฝ้าดู + รายงานความแม่นของ parser"

    def add_arguments(self, p):
        p.add_argument("--file", default=DEFAULT_FILE)
        p.add_argument("--group", default=SAMPLE_GROUP_ID, help="LINE group id ที่จะบันทึกไว้")
        p.add_argument("--dry-run", action="store_true", help="ไม่เขียน DB แค่รายงาน")
        p.add_argument("--clear", action="store_true", help="ลบข้อความชุดตัวอย่างเดิมก่อน")
        p.add_argument("--out", help="เขียนรายงานลงไฟล์ (UTF-8)")

    def handle(self, *a, **o):
        rows = read_log(o["file"])
        if not rows:
            self.stderr.write("อ่านไฟล์ไม่ได้ / ไม่มีข้อความ: %s" % o["file"])
            return
        items = analyse(rows)
        report = self._report(items)

        if o["out"]:
            with open(o["out"], "w", encoding="utf-8") as f:
                f.write(report)
            self.stdout.write("wrote report -> %s" % o["out"])
        else:
            self.stdout.write(report)

        if o["dry_run"]:
            self.stdout.write("(dry-run - DB untouched)")
            return
        self._save(items, o["group"], o["clear"])

    # ---------- บันทึกลง DB ----------
    def _save(self, items, gid, clear):
        from cars.models import Car
        if clear:
            n = GroupMessage.objects.filter(group_id=gid).delete()[0]
            self.stdout.write("cleared %d old rows" % n)
        made = 0
        for i, it in enumerate(items, 1):
            mid = "sample-%s-%04d" % (gid, i)
            if GroupMessage.objects.filter(message_id=mid).exists():
                continue
            p = it["p"]
            car = None
            if p["plate"]:
                try:
                    car = Car.objects.filter(plate__endswith=p["plate"]).first()
                except Exception:
                    car = None
            GroupMessage.objects.create(
                group_id=gid, message_id=mid, sender_name=it["sender"],
                msg_type=it["type"], text=it["text"],
                parsed_kind=p["kind"], parsed_plate=p["plate"], parsed_purpose=p["purpose"],
                parsed_conf=p["confidence"], parsed_why=p["why"][:120], matched_car=car,
                sent_at=timezone.make_aware(it["at"]) if timezone.is_naive(it["at"]) else it["at"],
            )
            made += 1
        self.stdout.write("saved %d messages into group '%s'" % (made, gid))

    # ---------- รายงาน ----------
    def _report(self, items):
        L = []
        add = L.append
        texts = [i for i in items if i["type"] == "text"]
        by_type = {}
        for i in items:
            by_type[i["type"]] = by_type.get(i["type"], 0) + 1

        add("=" * 66)
        add("สรุปการอ่าน log กลุ่มจริง  (%d ข้อความ · %s → %s)"
            % (len(items), items[0]["at"].strftime("%d/%m"), items[-1]["at"].strftime("%d/%m")))
        add("=" * 66)
        add("ชนิดข้อความ: " + " · ".join("%s %d" % (k, v) for k, v in sorted(by_type.items())))
        add("")

        hit = [i for i in texts if i["p"]["kind"]]
        miss = [i for i in texts if not i["p"]["kind"]]
        high = [i for i in hit if i["p"]["confidence"] == "high"]
        out_ = [i for i in hit if i["p"]["kind"] == "out"]
        in_ = [i for i in hit if i["p"]["kind"] == "in"]
        plate = [i for i in hit if i["p"]["plate"]]
        fuel = [i for i in texts if i["p"]["fuel"]]

        add("ข้อความที่คนพิมพ์จริง (ไม่นับรูป/สติกเกอร์/โน้ตระบบ) : %d" % len(texts))
        add("  ระบบจับว่าเป็นเบิก/คืน : %d  (%.0f%%)  → เบิก %d · คืน %d"
            % (len(hit), 100.0 * len(hit) / max(len(texts), 1), len(out_), len(in_)))
        add("  มั่นใจ (high)          : %d   · เดา (low) : %d" % (len(high), len(hit) - len(high)))
        add("  จับทะเบียนได้          : %d / %d ข้อความที่จับได้" % (len(plate), len(hit)))
        add("  พ่วงเบิกน้ำมัน         : %d" % len(fuel))
        add("")

        pur = {}
        for i in out_:
            k = i["p"]["purpose"] or "(เดาไม่ได้)"
            pur[k] = pur.get(k, 0) + 1
        add("ประเภทงานที่เดาได้จากข้อความ 'เบิก' %d ครั้ง:" % len(out_))
        for k, v in sorted(pur.items(), key=lambda x: -x[1]):
            add("   %-14s %d" % (P.purpose_name(k) or k, v))
        add("")

        pairs, still_out, orphan = pair_movements(items)
        closed = [p for p in pairs if p[1]]
        add("จับคู่ เบิก→คืน ต่อคน:")
        add("   ปิดรอบได้ (เบิกแล้วมีคืน) : %d" % len(closed))
        add("   เบิกแล้วไม่เจอคืน         : %d" % (len(pairs) - len(closed) + len(still_out)))
        add("   'คืน' ที่ไม่มี 'เบิก' นำหน้า: %d" % len(orphan))
        if closed:
            durs = [(b["at"] - a["at"]).total_seconds() / 3600 for a, b in closed]
            add("   เวลาใช้รถเฉลี่ย %.1f ชม. (สั้นสุด %.1f · นานสุด %.1f)"
                % (sum(durs) / len(durs), min(durs), max(durs)))
        add("")

        add("-" * 66)
        add("[A] ข้อความที่ระบบ 'จับไม่ได้เลย' — ต้องดูว่าควรจับไหม (%d)" % len(miss))
        add("-" * 66)
        for i in miss:
            add("  %s %-12s | %s" % (i["at"].strftime("%d/%m %H:%M"), i["sender"][:12], i["text"][:70]))
        add("")
        add("-" * 66)
        add("[B] ข้อความที่ 'เดา' (low) — เสี่ยงตีความผิด (%d)" % (len(hit) - len(high)))
        add("-" * 66)
        for i in hit:
            if i["p"]["confidence"] == "high":
                continue
            p = i["p"]
            add("  %s %-12s | %-3s %-5s %-10s | %s"
                % (i["at"].strftime("%d/%m %H:%M"), i["sender"][:12], p["kind"],
                   p["plate"] or "-", P.purpose_name(p["purpose"]) or "-", i["text"][:52]))
        add("")
        add("-" * 66)
        add("[C] 'คืน' ที่หาคู่เบิกไม่เจอ — แปลว่าตอนเบิกระบบพลาด (%d)" % len(orphan))
        add("-" * 66)
        for i in orphan:
            add("  %s %-12s | %s" % (i["at"].strftime("%d/%m %H:%M"), i["sender"][:12], i["text"][:60]))
        add("")
        add("-" * 66)
        add("[D] เบิกแล้วไม่เจอคืน (%d)" % (len(pairs) - len(closed) + len(still_out)))
        add("-" * 66)
        for a, b in pairs:
            if b is None:
                add("  %s %-12s | %s" % (a["at"].strftime("%d/%m %H:%M"), a["sender"][:12], a["text"][:60]))
        for a in still_out:
            add("  %s %-12s | %s" % (a["at"].strftime("%d/%m %H:%M"), a["sender"][:12], a["text"][:60]))
        return "\n".join(L)
