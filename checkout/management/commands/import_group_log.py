"""อ่าน log กลุ่ม LINE → **จับ pattern แล้วสร้างเป็นเคสเบิก-คืนรถจริง** (`CarMovement`)

    python manage.py import_group_log --dry-run     # ดูว่าจะได้เคสอะไรบ้าง ไม่เขียน DB
    python manage.py import_group_log --clear       # ล้างเคสที่นำเข้ารอบก่อนแล้วใส่ใหม่
    python manage.py import_group_log --out rep.txt # เขียนรายงานเป็นไฟล์ (กัน console ไทยเพี้ยน)

เคสที่ได้ไปโผล่ที่ **แท็บ "เบิก-คืนรถ" ในแดชบอร์ด** (`/dashboard/?tab=ck`) เหมือนเคสจริงทุกอย่าง

⚠️ กติกาที่ต้องรักษา (เจ้าของสั่ง ก.ย.69):
  - **ไม่เก็บข้อความดิบทั้งกลุ่มลงระบบ** — เอาเฉพาะที่จับ pattern ได้ว่าเป็นการเบิก/คืน
  - **ห้ามโชว์ LINE user id** — ชื่อผู้เบิกใช้ "ชื่อเล่น" ที่เทียบจากชีตพนักงาน ([people.py](../../people.py))
    userId เก็บไว้ที่ `borrower_line_id` สำหรับ "แท็กในกลุ่ม LINE" เท่านั้น (API ไม่ส่งออก)
"""
import os
import re
from datetime import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from checkout import parser as P
from checkout import people
from checkout.models import CarMovement, MovementPhoto
from checkout import constants as C

DEFAULT_FILE = os.path.join("checkout", "samples", "group_log_sep69.txt")
# เครื่องหมายว่าเคสนี้มาจากการนำเข้า log (ไม่ใช่คนกดในเว็บ) — ใช้ตอน --clear และดูย้อนหลัง
SAMPLE_MARK = "[นำเข้าจากกลุ่ม LINE]"
# จับรูป/วิดีโอที่ส่งใกล้ๆ ข้อความนั้น (คนส่งรูปก่อนแล้วค่อยพิมพ์) — กี่นาทีถือว่าชุดเดียวกัน
PHOTO_WINDOW_MIN = 6

MULTIWORD_SENDERS = [
    "🪷Jay. OxletAuto📜👑",
    "เมตตา สัตย์ธรรม🚘🚔🚖",
    "เซลมัท OxletAuto",
]
_SYSTEM_TEXTS = ["เขียนโน้ตใหม่", "ยกเลิกข้อความ", "ออกจากกลุ่ม", "เพิ่มประกาศ", "เพิ่ม<u>ประกาศ</u>"]
_TYPE_MAP = {"รูป": "image", "วิดีโอ": "video", "สติกเกอร์": "sticker"}
_DATE_RE = re.compile(r"^(\d{4})\.(\d{2})\.(\d{2})")
_MSG_RE = re.compile(r"^(\d{1,2}):(\d{2})\s+(.*)$")
# ปลายทางที่คนพิมพ์ท้ายประโยค — เอาไปลงคอลัมน์ "ปลายทาง" ให้หัวหน้าอ่านง่าย
_DEST_HINTS = ["ชลบุรี", "อ่อนนุช", "ศรีราชา", "พัทยา", "นครปฐม", "กรุงเทพ", "พานทอง",
               "แปลงยาว", "ขนส่ง", "ศูนย์", "อู่", "ตรอ"]


def _split_sender(rest):
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
            rows.append({"at": day.replace(hour=int(m.group(1)), minute=int(m.group(2))),
                         "sender": sender, "text": text, "type": _msg_type(text)})
    return rows


def _dest(text):
    for w in _DEST_HINTS:
        if w in text:
            return w
    return ""


def _photos_near(rows, i):
    """นับรูป/วิดีโอที่คนเดียวกันส่งรอบๆ ข้อความนี้ (ก่อนหรือหลังไม่เกิน PHOTO_WINDOW_MIN นาที)"""
    me, at = rows[i]["sender"], rows[i]["at"]
    out = []
    for r in rows:
        if r["sender"] != me or r["type"] not in ("image", "video"):
            continue
        if abs((r["at"] - at).total_seconds()) <= PHOTO_WINDOW_MIN * 60:
            out.append(r["type"])
    return out


def build_cases(rows):
    """จับ pattern จาก log → รายการเคสเบิก-คืน (ยังไม่เขียน DB)

    กติกาการจับคู่: ไล่ตามเวลา · "เบิก" เปิดรอบของคนนั้น · "คืน" ปิดรอบที่ค้างอยู่ของคนเดียวกัน
      · เบิกซ้อนโดยยังไม่คืน = รอบเก่าค้างไว้ (ตรงกับของจริง: คนเดียวเบิกหลายคันได้)
      · "ขอเบิกน้ำมัน" ระหว่างรอบที่เปิดอยู่ = ติดธง ⛽ ให้รอบนั้น (ไม่ใช่รอบใหม่)
      · "พิมพ์แต่เลขทะเบียน" = เติมทะเบียนให้รอบที่เปิดอยู่ถ้ายังไม่รู้ว่าคันไหน
    """
    open_by, cases = {}, []
    for i, r in enumerate(rows):
        if r["type"] != "text":
            continue
        p = P.parse(r["text"])
        k, who = p["kind"], r["sender"]
        cur = open_by.get(who)
        if k == "out":
            c = {"who": who, "out_at": r["at"], "out_text": r["text"],
                 "plate": p["plate"], "purpose": p["purpose"], "fuel": p["fuel"],
                 "dest": _dest(r["text"]), "conf": p["confidence"],
                 "out_media": _photos_near(rows, i), "in_at": None, "in_text": "",
                 "in_media": []}
            open_by[who] = c
            cases.append(c)
        elif k == "in" and cur:
            cur["in_at"] = r["at"]
            cur["in_text"] = r["text"]
            cur["in_media"] = _photos_near(rows, i)
            if not cur["plate"] and p["plate"]:
                cur["plate"] = p["plate"]
            open_by.pop(who, None)
        elif k == "fuel" and cur:
            cur["fuel"] = True
        elif k == "plate_only" and cur and not cur["plate"]:
            cur["plate"] = p["plate"]
    return cases


class Command(BaseCommand):
    help = "อ่าน log กลุ่ม LINE แล้วสร้างเป็นเคสเบิก-คืนรถ (โผล่ในแท็บ เบิก-คืนรถ)"

    def add_arguments(self, p):
        p.add_argument("--file", default=DEFAULT_FILE)
        p.add_argument("--dry-run", action="store_true", help="ไม่เขียน DB แค่รายงาน")
        p.add_argument("--clear", action="store_true", help="ลบเคสที่นำเข้ารอบก่อนก่อนใส่ใหม่")
        p.add_argument("--out", help="เขียนรายงานลงไฟล์ (UTF-8)")

    def handle(self, *a, **o):
        rows = read_log(o["file"])
        if not rows:
            self.stderr.write("อ่านไฟล์ไม่ได้ / ไม่มีข้อความ: %s" % o["file"])
            return
        cases = build_cases(rows)
        report = self._report(rows, cases)
        if o["out"]:
            with open(o["out"], "w", encoding="utf-8") as f:
                f.write(report)
            self.stdout.write("wrote report -> %s" % o["out"])
        else:
            self.stdout.write(report)
        if o["dry_run"]:
            self.stdout.write("(dry-run - DB untouched)")
            return
        self._save(cases, o["clear"])

    # ---------- เขียนลง DB ----------
    def _save(self, cases, clear):
        from cars.models import Car
        if clear:
            n = CarMovement.objects.filter(note__startswith=SAMPLE_MARK).delete()[0]
            self.stdout.write("cleared %d old imported rows" % n)
        made = 0
        for c in cases:
            car = None
            if c["plate"]:
                try:
                    car = Car.objects.filter(plate__endswith=c["plate"]).first()
                except Exception:
                    car = None
            note = "%s %s" % (SAMPLE_MARK, c["out_text"])
            if c["in_text"]:
                note += "\nคืน: " + c["in_text"]
            returned = bool(c["in_at"])
            m = CarMovement.objects.create(
                car=car, plate_text=c["plate"] or "",
                # ★ ชื่อเล่นเท่านั้น — ห้ามโชว์ LINE user id (ดู people.py)
                borrower_name=people.nickname_for(display_name=c["who"]),
                borrower_line_id=people.line_id_for(c["who"]),
                purpose_key=c["purpose"], purpose=C.PURPOSE_NAME.get(c["purpose"], ""),
                destination=c["dest"],
                checked_out_at=_aware(c["out_at"]),
                returned_at=_aware(c["in_at"]) if returned else None,
                fuel_requested=bool(c["fuel"]),
                note=note,
                # คืนแล้ว = จบ (หัวหน้าเห็นในกลุ่มแล้ว) · ยังไม่คืน = ค้าง รอคนยืนยัน
                status=CarMovement.APPROVED_HUMAN if returned else CarMovement.PENDING_HUMAN,
                source=CarMovement.SRC_IMPORT,
            )
            # รูปที่ส่งในกลุ่มจริง — เก็บเป็นหลักฐานว่า "ส่งกี่ไฟล์" (ไม่มีตัวไฟล์ เพราะอยู่ใน LINE)
            for t in c["out_media"]:
                MovementPhoto.objects.create(movement=m, phase=MovementPhoto.OUT,
                                             media_type=t if t == "video" else "photo")
            for t in c["in_media"]:
                MovementPhoto.objects.create(movement=m, phase=MovementPhoto.IN,
                                             media_type=t if t == "video" else "photo")
            made += 1
        self.stdout.write("saved %d movements" % made)

    # ---------- รายงาน ----------
    def _report(self, rows, cases):
        L = []
        add = L.append
        texts = [r for r in rows if r["type"] == "text"]
        closed = [c for c in cases if c["in_at"]]
        add("=" * 62)
        add("จับ pattern จาก log กลุ่ม (%d ข้อความ · %s → %s)"
            % (len(rows), rows[0]["at"].strftime("%d/%m"), rows[-1]["at"].strftime("%d/%m")))
        add("=" * 62)
        add("ข้อความที่คนพิมพ์ %d → **สร้างเป็นเคสเบิก-คืนได้ %d เคส**" % (len(texts), len(cases)))
        add("   คืนแล้ว %d · ยังไม่คืน %d · ขอน้ำมันด้วย %d"
            % (len(closed), len(cases) - len(closed), sum(1 for c in cases if c["fuel"])))
        add("   รู้ว่าคันไหน (มีทะเบียน) %d / %d" % (sum(1 for c in cases if c["plate"]), len(cases)))
        if closed:
            hrs = [(c["in_at"] - c["out_at"]).total_seconds() / 3600 for c in closed]
            add("   เวลาใช้รถเฉลี่ย %.1f ชม. (นานสุด %.1f)" % (sum(hrs) / len(hrs), max(hrs)))
        add("")
        pur = {}
        for c in cases:
            key = C.PURPOSE_NAME.get(c["purpose"], "(เดาไม่ได้)")
            pur[key] = pur.get(key, 0) + 1
        add("ประเภทงาน:")
        for k, v in sorted(pur.items(), key=lambda x: -x[1]):
            add("   %-38s %d" % (k, v))
        add("")
        who = {}
        for c in cases:
            who[c["who"]] = who.get(c["who"], 0) + 1
        add("คนเบิก (ชื่อเล่นจะถูกเทียบจากชีตพนักงานตอนบันทึก):")
        for k, v in sorted(who.items(), key=lambda x: -x[1]):
            add("   %-22s %d ครั้ง" % (k[:22], v))
        add("")
        add("-" * 62)
        add("เคสที่ยังไม่เจอการคืน (%d) — ของจริงที่ตกหล่นในกลุ่ม" % (len(cases) - len(closed)))
        add("-" * 62)
        for c in cases:
            if not c["in_at"]:
                add("  %s %-14s | %s" % (c["out_at"].strftime("%d/%m %H:%M"),
                                         c["who"][:14], c["out_text"][:52]))
        return "\n".join(L)


def _aware(dt):
    return timezone.make_aware(dt) if (dt and timezone.is_naive(dt)) else dt
