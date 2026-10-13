# -*- coding: utf-8 -*-
"""เทสต์ สำเนาชีตจ่ายเบอร์ + รายงานแบน ลง Postgres (dashboard/services/sheet_mirror.py · 13 ต.ค.69)

    python scripts/test_sheet_mirror.py

ฐานข้อมูลทดสอบแยก · ปลอมที่ `requests` (Google Sheets API) + ใบรับรอง Google · ข้อมูลสมมติ
"""
import io
import os
import sys
import urllib.parse
from datetime import date, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
os.environ["DB_HOST"] = ""
os.environ.setdefault("DEBUG", "True")

import django  # noqa: E402

django.setup()

from django.test.runner import DiscoverRunner  # noqa: E402
from django.test.utils import setup_test_environment  # noqa: E402

setup_test_environment()
_runner = DiscoverRunner(verbosity=0, interactive=False)
_old = _runner.setup_databases()

from unittest import mock  # noqa: E402

from django.utils import timezone  # noqa: E402

from dashboard.models import BanSheetRow, LeadSheetRow  # noqa: E402
from dashboard.services import db_inventory, google_sheets as G  # noqa: E402
from dashboard.services import sheet_mirror as SM  # noqa: E402

FAILS = []


def ok(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else " — " + str(extra)))
    if not cond:
        FAILS.append(name)


HDR = ["ว/ด/ป", "เบอร์โทร", "เวลา", "Code", "เซลล์", "ทีมไลฟ์", "Admin", "ช่องทาง", "สาขา", "type", "ADS",
       "รถลูกค้าถาม", "CAR / สูตร", "แจ้งหลักฐาน\nการโทร", "FOCUS", "วัน เวลา ที่ติดต่อ", "จำนวนอัพเดท",
       "วัน เวลา อัพเดทล่าสุด", "มากรอกชีตกันเถอะ", "PROFILE ลูกค้า จาก ADMIN", "อาชีพ", "รายได้", "อายุงาน",
       "ประวัติการผ่อน", "ประเภทลูกค้า", "สถานะลูกค้า", "Admin survey", "Status แอดมิน", "อัพเดทเคส", "อัพเดทเคส"]


def lrow(**kw):
    r = [""] * len(HDR)
    for k, v in kw.items():
        r[HDR.index(k)] = v
    return r


LEAD_SID = G.SHEET_CONFIG["leads"]["spreadsheet_id"]
BAN_SID = G.SHEET_CONFIG["ban_report"]["spreadsheet_id"]
BAN_TAB = G.SHEET_CONFIG["ban_report"]["sheet_name"]
SHEET = {
    LEAD_SID: {
        "ตุลาคม 69": [HDR,
                      lrow(**{"ว/ด/ป": "12/10/26", "เบอร์โทร": "0812345678", "เวลา": "22:03", "Code": "TLD10-9221 ",
                              "เซลล์": "นิด", "ช่องทาง": "LINE@", "วัน เวลา ที่ติดต่อ": "12/10/26 22:54",
                              "จำนวนอัพเดท": "2", "วัน เวลา อัพเดทล่าสุด": "13/10/2026 9:05",
                              "สถานะลูกค้า": "รอตอบ", "อัพเดทเคส": "a"}),
                      [],
                      lrow(**{"ว/ด/ป": "46308", "เบอร์โทร": "ID LINE : abc", "Code": "nld10-9222"})],
        "กันยายน 69": [HDR, lrow(**{"ว/ด/ป": "28/9/69", "Code": "TLD9-7700", "เซลล์": "มัท"})],
        "รวม sheet": [HDR, lrow(**{"Code": "ไม่ควรถูกดึง"})],
        "Bot": [["x"], ["y"]],
    },
    BAN_SID: {BAN_TAB: [["banDate", "time", "seller", "sellerDisplay", "banType", "reason", "bannedBy",
                         "unbanDate", "status", "rawText", "groupId"],
                        ["13/10/26", "13:31", "บิว", "", "ไม่กรอกชีต", "ไม่กรอกชีต", "กวาง", "", "แบน", "แบน @billy", "C1"],
                        ["46307", "15:00", "นิด", "", "ไม่รับเคส", "ไม่รับเคส", "กวาง", "14/10/2026", "แบน", "", "C1"]]},
}
STATE = {"fail": False, "calls": 0}


class R:
    def __init__(self, code, js):
        self.status_code, self._js, self.text = code, js, str(js)

    def json(self):
        return self._js


def fake_get(url, params=None, headers=None, timeout=None):
    STATE["calls"] += 1
    sid = next((s for s in SHEET if "/spreadsheets/" + s in url), None)
    if STATE["fail"] or sid is None:
        return R(500, {"error": "boom"})
    if url.endswith("/values:batchGet"):
        out = []
        for k, v in params:
            if k != "ranges":
                continue
            tab = urllib.parse.unquote(v).split("!")[0].strip("'")
            out.append({"range": v, "values": SHEET[sid].get(tab, [])})
        return R(200, {"valueRanges": out})
    return R(200, {"sheets": [{"properties": {"title": t}} for t in SHEET[sid]]})


class Creds:
    token = "t"
    valid = True

    def refresh(self, _):
        pass


P = [mock.patch("requests.get", fake_get), mock.patch.object(G, "_get_credentials", lambda: Creds())]
for p in P:
    p.start()

# ── 1) ดึงครั้งแรก ─────────────────────────────────────────────
ok("ถึงรอบตั้งแต่ยังไม่เคยทำ", SM.due())
r = SM.run()
ok("สำเร็จ", r.get("ok") and not r.get("error"), r)
ok("ดึงเฉพาะแท็บรายเดือน (ไม่เอารวม sheet / Bot)", set(r["tabs"]) == {"ตุลาคม 69", "กันยายน 69"}, r["tabs"])
ok("ข้ามแถวว่าง", r["tabs"]["ตุลาคม 69"] == 2 and LeadSheetRow.objects.count() == 3, r["tabs"])
a = LeadSheetRow.objects.get(code="TLD10-9221")
ok("Code ตัดช่องว่าง", a.code == "TLD10-9221")
ok("แถวในชีต + เดือนของแท็บ", (a.row_no, a.tab_month) == (2, date(2026, 10, 1)), (a.row_no, a.tab_month))
ok("ว/ด/ป ปี 2 หลัก = ค.ศ.", a.received_date == date(2026, 10, 12), a.received_date)
ok("ช่องหลักแตกเป็นคอลัมน์", (a.phone, a.seller, a.channel, a.customer_status, a.update_count) ==
   ("0812345678", "นิด", "LINE@", "รอตอบ", 2), (a.phone, a.seller, a.channel, a.customer_status, a.update_count))
lt = timezone.localtime(a.contact_at) if a.contact_at else None
ok("วันเวลาที่ติดต่อ = เวลาไทย", lt and (lt.date(), lt.hour, lt.minute) == (date(2026, 10, 12), 22, 54), lt)
lu = timezone.localtime(a.last_updated_at) if a.last_updated_at else None
ok("ปี 4 หลักก็อ่านได้", lu and (lu.day, lu.hour, lu.minute) == (13, 9, 5), lu)
ok("ทุกช่องดิบอยู่ใน raw (หัวซ้ำ = เติม (2))", a.raw.get("แจ้งหลักฐาน การโทร") is None and a.raw.get("อัพเดทเคส") == "a"
   and a.raw.get("เวลา") == "22:03", a.raw)
b = LeadSheetRow.objects.get(code="NLD10-9222")
ok("Code ตัวเล็ก → ตัวใหญ่ · วันที่แบบเลข serial", (b.row_no, b.received_date) == (4, date(2026, 10, 13)),
   (b.row_no, b.received_date))
c = LeadSheetRow.objects.get(code="TLD9-7700")
ok("ปี พ.ศ. 2 หลัก (69) = 2026", c.received_date == date(2026, 9, 28), c.received_date)
ok("รายงานแบน 2 แถว", r["bans"] == 2 and BanSheetRow.objects.count() == 2, r["bans"])
bn = BanSheetRow.objects.order_by("row_no")
ok("แบน: วันที่ + คน + ประเภท", (bn[0].ban_date, bn[0].seller, bn[0].ban_type, bn[0].banned_by) ==
   (date(2026, 10, 13), "บิว", "ไม่กรอกชีต", "กวาง"))
ok("แบน: วันที่แบบ serial", bn[1].ban_date == date(2026, 10, 12), bn[1].ban_date)
ok("ไม่ถึงรอบอีก 10 นาที", not SM.due())
ok("ครบ 10 นาที = ถึงรอบ", SM.due(timezone.now() + timedelta(minutes=10)))

# ── 2) แก้/ลบในชีต → ตามมาครบ ───────────────────────────────────
SHEET[LEAD_SID]["ตุลาคม 69"].pop(1)                    # ลบแถว TLD10-9221 (แถวล่างเลื่อนขึ้น)
SHEET[LEAD_SID]["ตุลาคม 69"][2][HDR.index("เซลล์")] = "ภู"
del SHEET[LEAD_SID]["กันยายน 69"]                      # แท็บถูกลบ/เปลี่ยนชื่อ
r = SM.run()
ok("แถวที่ลบในชีต หายจากตาราง", not LeadSheetRow.objects.filter(code="TLD10-9221").exists())
b = LeadSheetRow.objects.get(code="NLD10-9222")
ok("แถวที่เลื่อน = เลขแถวใหม่ + ค่าที่แก้", (b.row_no, b.seller) == (3, "ภู"), (b.row_no, b.seller))
ok("แท็บที่หายไปจากชีต = ลบสำเนาด้วย", not LeadSheetRow.objects.filter(tab="กันยายน 69").exists())
ok("ไม่มีแถวซ้ำ", LeadSheetRow.objects.count() == 1, LeadSheetRow.objects.count())

# ── 3) ชีตล่ม = ของเดิมอยู่ครบ ───────────────────────────────────
STATE["fail"] = True
r = SM.run()
ok("ชีตล่ม = บอกเหตุผล", not r.get("ok") and "HTTP 500" in r.get("error", ""), r)
ok("ชีตล่ม = สำเนาเดิมไม่หาย", LeadSheetRow.objects.count() == 1 and BanSheetRow.objects.count() == 2)
ok("ผลรอบล่าสุดจดไว้ (หน้าสถานะระบบอ่าน)", SM._kv(SM.KV_LAST).get("error"))
STATE["fail"] = False

# ── 4) ตัวช่วย ────────────────────────────────────────────────
ok("ข้อความยาวเกินช่อง = ตัด ไม่ล้ม", len(SM._fit(LeadSheetRow, "seller", "ก" * 500)) == 80)
ok("วันที่ผิด = None", SM.parse_date("31/2/26") is None and SM.parse_date("xyz") is None)
ok("\"15/1\" ไม่มีปี = ปีของแท็บ", SM.parse_date("15/1", date(2026, 1, 1)) == date(2026, 1, 15))
ok("แท็บ ธ.ค. มี \"3/1\" = มกราคมปีหน้า", SM.parse_date("3/1", date(2026, 12, 1)) == date(2027, 1, 3))
_x = SM.parse_dt("15/1 10:30", date(2026, 1, 1))
ok("\"15/1 10:30\" มีเวลา", _x and timezone.localtime(_x).hour == 10, _x)
ok("ไม่มีเดือนของแท็บ = ไม่เดาปี", SM.parse_date("15/1") is None)
_h = ["DATE", "เบอร์โทร", "เวลา", "Code"] + [""] * 14 + ["ว/ด/ป"]
ok("หัว A = DATE ใช้คอลัมน์ A (แท็บ มี.ค.69) ไม่ใช่ ว/ด/ป ที่คอลัมน์ S",
   G._resolve_lead_colmap(_h).get(G.LEADS_COL.received_date) == 0)
ok("แท็บรายเดือนอ่านเดือนถูก", SM.tab_month("มกราคม 70") == date(2027, 1, 1) and SM.tab_month("รวม sheet") is None)
ok("ดึงแท็บเดียวได้", SM.run(["ตุลาคม 69"]).get("tabs") == {"ตุลาคม 69": 1})
ok("มีคำอธิบายในสารบัญฐานข้อมูล + ป้ายข้อมูลส่วนบุคคล",
   all(db_inventory.TABLES.get(t, {}).get("pii") for t in ("dash_lead_sheet_row", "dash_ban_sheet_row")))

for p in P:
    p.stop()
_runner.teardown_databases(_old)
print()
print("ผ่านทั้งหมด" if not FAILS else "ไม่ผ่าน %d ข้อ: %s" % (len(FAILS), ", ".join(FAILS)))
sys.exit(1 if FAILS else 0)
