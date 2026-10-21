# -*- coding: utf-8 -*-
"""เทสต์ช่อง "วันหยุด" ของพนักงาน (★ 15 ต.ค.69 · checkin_report.is_day_off)

    python scripts/test_day_off.py

ที่มา: วันพฤหัส คนที่ช่องวันหยุดเขียน "พฤหัส" (ย่อ) ไม่ถูกตัด เพราะโค้ดเดิมเทียบ "พฤหัสบดี" in "พฤหัส"
→ ถูกจ่ายลีด (คิวจ่ายวน) + ถูกนับ/แท็กว่าขาดเช็คชื่อ · เทสต์เดิมล้มเฉพาะวันพฤหัส (ขึ้นกับวันที่รัน)

ทุกข้อในไฟล์นี้ **ตรึงวันเอง** (จ. 12 – อา. 18 ต.ค.69) ผลต้องเหมือนกันไม่ว่ารันวันไหน
· ฐานข้อมูลทดสอบแยก · ปลอมแค่ชีต Google / ผลแดชบอร์ด (ขอบระบบ) · ไม่ส่ง LINE
"""
import io
import os
import sys
from datetime import date, datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
os.environ.setdefault("DB_HOST", "")
os.environ.setdefault("DEBUG", "True")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.test.runner import DiscoverRunner  # noqa: E402
from django.test.utils import setup_test_environment  # noqa: E402

setup_test_environment()
_runner = DiscoverRunner(verbosity=0, interactive=False)
_old = _runner.setup_databases()
if "testserver" not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]

from django.contrib.sessions.backends.signed_cookies import SessionStore  # noqa: E402
from django.test import Client  # noqa: E402
from django.utils import timezone  # noqa: E402

import dashboard.services.fetch_dashboard as FD  # noqa: E402
from checkout import checkin_report as R  # noqa: E402
from checkout import console_data as CD  # noqa: E402
from checkout.models import Employee  # noqa: E402
from dashboard.services import google_sheets  # noqa: E402
from dashboard.services import mobile_home as MH  # noqa: E402

google_sheets.fetch_sheet = lambda *a, **k: []      # ชีตพนักงาน — ไม่ออกเน็ต
FD.fetch_dashboard_data = lambda *a, **k: {}        # แดชบอร์ดทีม — ไม่อ่านชีตลีด

PASS = FAIL = 0


def ok(cond, label, got=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓", label)
    else:
        FAIL += 1
        print("  ✗", label, ("   ได้: %r" % (got,)) if got != "" else "")


WEEK = [date(2026, 10, 12 + i) for i in range(7)]       # index = weekday (0 = จันทร์ … 6 = อาทิตย์)
WED, THU, FRI = WEEK[2], WEEK[3], WEEK[4]

try:
    # ═════════════════════════════════════════════════════════════════════
    print("[1] is_day_off — ชื่อเต็ม/ย่อ ครบ 7 วัน")
    ok([d.weekday() for d in WEEK] == list(range(7)), "ตรึงสัปดาห์: 12 ต.ค.69 = จันทร์ … 18 = อาทิตย์")
    for wd in range(7):
        full, key = R.THAI_DAYS[wd], R.DAY_OFF_KEYS[wd]
        hits = [d.weekday() for d in WEEK if R.is_day_off(full, d)]
        ok(hits == [wd], "\"%s\" ตรงวันเดียว (ของมันเอง)" % full, hits)
        hits = [d.weekday() for d in WEEK if R.is_day_off(key, d)]
        ok(hits == [wd], "\"%s\" ตรงวันเดียว (ของมันเอง)" % key, hits)
    ok(R.is_day_off("พฤหัส", THU), "★ พฤหัส: \"พฤหัส\" (ย่อ) = หยุด")
    ok(R.is_day_off("พฤหัสบดี", THU), "พฤหัส: \"พฤหัสบดี\" (เต็ม) = หยุด")
    ok(R.is_day_off("วันพฤหัส", THU) and R.is_day_off("พฤหัสฯ", THU), "พฤหัส: \"วันพฤหัส\" / \"พฤหัสฯ\" = หยุด")
    ok(R.is_day_off("จันทร์ อังคาร พุธ พฤหัส ศุกร์ เสาร์ อาทิตย์", THU), "★ หยุดทุกวัน (เขียนพฤหัสย่อ) = หยุดพฤหัสด้วย")
    ok(not R.is_day_off("พฤหัส", WED) and not R.is_day_off("พฤหัส", FRI), "\"พฤหัส\" ไม่ตรงพุธ/ศุกร์")
    multi = [d.weekday() for d in WEEK if R.is_day_off("ศุกร์ เสาร์ อาทิตย์", d)]
    ok(multi == [4, 5, 6], "หลายวันในช่องเดียว \"ศุกร์ เสาร์ อาทิตย์\" = ศ./ส./อา. เท่านั้น", multi)
    ok(not R.is_day_off("", THU) and not R.is_day_off(None, THU), "ช่องว่าง/None = ไม่หยุด")
    ok(R.is_day_off("พฤหัส", 3) and not R.is_day_off("พฤหัส", 4), "รับเลข weekday ได้ (3 = พฤหัส)")

    # ── พนักงาน (ทีมขาย · เวลาเข้างาน 00:00 = เลยเวลาแล้วเสมอ ไม่ขึ้นกับนาฬิกาตอนรัน) ──
    def emp(nick, pos, day_off=""):
        return Employee.objects.create(nickname=nick, position=pos, day_off=day_off, work_start="00:00",
                                       active=True, track_checkin=True)

    SHORT = emp("ทูพฤหัสย่อ", "ทีม A", "พฤหัส")
    FULL = emp("ภูพฤหัสเต็ม", "ทีม A", "พฤหัสบดี")
    FRIOFF = emp("นิดหยุดศุกร์", "ทีม B", "ศุกร์")
    WORK = emp("มัทมาทำงาน", "ทีม B")
    THU_OFF = {"ทูพฤหัสย่อ", "ภูพฤหัสเต็ม"}

    # ═════════════════════════════════════════════════════════════════════
    print("[2] ตารางเช็คชื่อ (checkin_report.collect) + รอบตามตัว 10:00")
    d = R.collect(THU)
    rows = {r["name"]: r for _, rs in d["groups"] for r in rs}
    miss = {m["name"] for m in d["missing"]}
    ok(d["dayName"] == "พฤหัสบดี", "หัวตารางยังโชว์ชื่อเต็ม \"พฤหัสบดี\"", d["dayName"])
    ok(rows["ทูพฤหัสย่อ"]["off"] and rows["ภูพฤหัสเต็ม"]["off"], "★ พฤหัส: หยุดพฤหัส (ย่อ/เต็ม) = ติดป้ายวันหยุด",
       {k: rows[k]["off"] for k in THU_OFF})
    ok(not (miss & THU_OFF), "★ พฤหัส: คนหยุดพฤหัสไม่อยู่ในรายชื่อ \"ยังไม่เช็คชื่อ\"", miss)
    ok({"นิดหยุดศุกร์", "มัทมาทำงาน"} <= miss, "พฤหัส: คนหยุดศุกร์/คนทำงาน ยังถูกนับว่ายังไม่เช็คชื่อ", miss)
    ok(d["counts"]["off"] == 2 and d["counts"]["missing"] == 2, "ยอด: หยุด 2 · ยังไม่เช็คชื่อ 2", d["counts"])
    ok(rows["ทูพฤหัสย่อ"]["note_show"] == "วันหยุด (พฤหัสบดี)", "ช่องหมายเหตุ: \"วันหยุด (พฤหัสบดี)\"",
       rows["ทูพฤหัสย่อ"]["note_show"])
    msgs = R.escalation_messages(d, mention=False)
    txt = msgs[0]["text"] if msgs else ""
    ok(txt and not any(n in txt for n in THU_OFF), "★ รอบตามตัว (พฤหัส): ไม่ตามคนหยุดพฤหัส", txt)
    ok("นิดหยุดศุกร์" in txt and "มัทมาทำงาน" in txt, "รอบตามตัว (พฤหัส): ตามคนที่ไม่ได้หยุด", txt)
    d = R.collect(FRI)
    miss = {m["name"] for m in d["missing"]}
    ok(THU_OFF <= miss and "นิดหยุดศุกร์" not in miss, "ศุกร์: คนหยุดพฤหัสกลับมาถูกนับ · คนหยุดศุกร์ไม่ถูกนับ", miss)

    # ═════════════════════════════════════════════════════════════════════
    print("[3] พาเนลเช็คชื่อบนเว็บ (/checkout/api/checkins?date=)")
    adm = Client()
    st = SessionStore()
    st["oxlet_user"] = {"user_id": "admin", "nickname": "", "display_name": "admin", "position": "admin"}
    st.save()
    adm.cookies[settings.SESSION_COOKIE_NAME] = st.session_key
    r = adm.get("/checkout/api/checkins", {"date": THU.isoformat()}, secure=True)
    js = r.json() if r.status_code == 200 else {}
    off = {x["name"] for x in js.get("dayoff") or []}
    miss = {x["name"] for x in js.get("missing") or []}
    ok(r.status_code == 200 and js.get("dayName") == "พฤหัสบดี", "เปิดได้ · dayName = พฤหัสบดี", r.status_code)
    ok(off == THU_OFF, "★ พฤหัส: กลุ่ม \"วันหยุดวันนี้\" = คนหยุดพฤหัส (ย่อ+เต็ม)", off)
    ok(not (miss & THU_OFF) and {"นิดหยุดศุกร์", "มัทมาทำงาน"} <= miss, "พฤหัส: \"ยังไม่เช็คชื่อ\" ไม่มีคนหยุดพฤหัส", miss)
    js = adm.get("/checkout/api/checkins", {"date": FRI.isoformat()}, secure=True).json()
    ok({x["name"] for x in js.get("dayoff") or []} == {"นิดหยุดศุกร์"}, "ศุกร์: กลุ่มวันหยุด = คนหยุดศุกร์",
       js.get("dayoff"))

    # ═════════════════════════════════════════════════════════════════════
    print("[4] แอปมือถือ (mobile_home)")
    ok(MH.my_checkin(SHORT, THU)["status"] == "dayoff", "★ เช็คชื่อของฉัน (พฤหัส · หยุด \"พฤหัส\") = วันหยุด")
    ok(MH.my_checkin(SHORT, FRI)["status"] == "none", "เช็คชื่อของฉัน (ศุกร์) = ยังไม่เช็คชื่อ")
    summ = MH.checkin_summary(THU)
    names = {m["name"] for m in summ["missing"]}
    ok(summ["dayoff"] == 2 and not (names & THU_OFF), "★ สรุปทั้งบริษัท (พฤหัส): หยุด 2 · คนหยุดพฤหัสไม่ใช่คนขาด",
       (summ["dayoff"], names))

    # ═════════════════════════════════════════════════════════════════════
    print("[5] แดชบอร์ดทีม (console_data.team) — ตรึงวันด้วย now=")
    noon = timezone.make_aware(datetime(2026, 10, 15, 12, 0))
    t = CD.team(now=noon)
    st_ = {s["name"]: s["status"] for s in t["sellers"]}
    ok(t["date"] == "2026-10-15" and t["dayName"] == "พฤหัสบดี", "ใช้วันจาก now= (15 ต.ค.69 พฤหัส)", t["date"])
    ok(st_.get("ทูพฤหัสย่อ") == "หยุดวันนี้" and st_.get("ภูพฤหัสเต็ม") == "หยุดวันนี้",
       "★ พฤหัส: หยุดพฤหัส (ย่อ/เต็ม) = หยุดวันนี้", st_)
    ok(st_.get("นิดหยุดศุกร์") != "หยุดวันนี้", "พฤหัส: คนหยุดศุกร์ไม่ขึ้นหยุดวันนี้", st_)
    t = CD.team(now=timezone.make_aware(datetime(2026, 10, 16, 12, 0)))
    st_ = {s["name"]: s["status"] for s in t["sellers"]}
    ok(st_.get("ทูพฤหัสย่อ") != "หยุดวันนี้" and st_.get("นิดหยุดศุกร์") == "หยุดวันนี้",
       "ศุกร์: กลับกัน", st_)
finally:
    _runner.teardown_databases(_old)

print("\nผ่าน %d · ไม่ผ่าน %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
