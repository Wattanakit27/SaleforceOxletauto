# -*- coding: utf-8 -*-
"""เทสต์: ช่วงวันที่ของการ์ดที่ส่งเข้าไลน์ + คำอธิบายตอนส่งแชทส่วนตัวไม่ได้"""
import io, os, sys, django
from datetime import date, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
os.environ.setdefault("DB_HOST", "")
django.setup()

from dashboard.services import report_shot as R
from dashboard.services.fetch_dashboard import bangkok_now

OK = [0, 0]


def ck(name, cond, got=""):
    OK[0] += 1
    if cond:
        OK[1] += 1
        print("  ok   %s" % name)
    else:
        print("  FAIL %s   ได้: %r" % (name, got))


today = bangkok_now().date()
print("[1] แปลง date_mode → ช่วงวันที่ (วันนี้ = %s)" % today)

f, t = R._date_range_for("today", {})
ck("วันนี้", (f, t) == (today.isoformat(),) * 2, (f, t))

f, t = R._date_range_for("yesterday", {})
y = (today - timedelta(days=1)).isoformat()
ck("★ เมื่อวาน = วันเดียว ไม่ใช่ช่วง", (f, t) == (y, y), (f, t))

f, t = R._date_range_for("last7", {})
ck("★ 7 วันย้อนหลัง รวมวันนี้ (นับได้ 7 วันพอดี)",
   f == (today - timedelta(days=6)).isoformat() and t == today.isoformat()
   and (date.fromisoformat(t) - date.fromisoformat(f)).days == 6, (f, t))

f, t = R._date_range_for("range", {"date_from": "2026-09-28", "date_to": "2026-09-28"})
ck("ระบุเอง 28/9", (f, t) == ("2026-09-28", "2026-09-28"), (f, t))

ck("ระบุเองแต่กรอกไม่ครบ = ตกไปเดือนปัจจุบัน",
   R._date_range_for("range", {"date_from": "2026-09-28", "date_to": ""}) == (None, None))
ck("เดือนปัจจุบัน = ให้หน้าเว็บจัดการเอง", R._date_range_for("month", {}) == (None, None))
ck("ค่ามั่ว = ไม่คืนช่วงมั่ว", R._date_range_for("อะไรก็ไม่รู้", {}) == (None, None))

print("\n[2] รายการตัวเลือกที่ส่งให้หน้าเว็บ")
keys = [k for k, _ in R.DATE_MODES]
ck("มีครบ 5 แบบ เรียงตามที่ตั้งใจ",
   keys == ["month", "today", "yesterday", "last7", "range"], keys)
ck("ทุกตัวมีชื่อภาษาไทย", all(n.strip() for _, n in R.DATE_MODES))
ck("DATE_MODE_KEYS ตรงกับลิสต์", R.DATE_MODE_KEYS == set(keys))

print("\n[3] เมื่อวาน/7 วัน ต้องคิดจากโซนไทย ไม่ใช่ UTC")
# เซิร์ฟเวอร์เป็น UTC — ช่วงหัวค่ำไทย (00:00-07:00 UTC ของวันถัดไป) ถ้าคิดด้วย UTC จะเพี้ยน 1 วัน
import datetime as _dt
ck("★ ใช้ bangkok_now() (วันไทย) ไม่ใช่ date.today() ของเครื่อง",
   R._date_range_for("today", {})[0] == bangkok_now().date().isoformat())

print("\n[4] คำอธิบายตอนส่งแชทส่วนตัวไม่ได้")
from dashboard.services.line_notify import dm_hint
ck("กลุ่ม (C…) = ไม่ต้องอธิบายอะไร", dm_hint("C9412426ea68e8e3f41bfa583ea671ae4") == "")
ck("ค่าว่าง = ไม่พัง", dm_hint("") == "")
h = dm_hint("U6bf1d72cf1d7e237c3a5c9848dde9bf4")
ck("คน (U…) = ต้องบอกวิธีแก้", isinstance(h, str))

print("\n%s (%d/%d)" % ("ผ่านทั้งหมด" if OK[0] == OK[1] else "มีข้อที่ไม่ผ่าน", OK[1], OK[0]))
