# -*- coding: utf-8 -*-
"""เทสต์ ห้องจ่ายเบอร์ → ชีตจ่ายเบอร์ + รายงานแบน (checkout/leadsheet.py · ย้ายมาจาก n8n 13 ต.ค.69)

    python scripts/test_leadsheet.py

ฐานข้อมูลทดสอบแยก · ปลอมที่ `requests` (= Google Sheets API) + ใบรับรอง Google · ข้อความสมมติ ไม่ใช่ข้อมูลลูกค้าจริง
ตรวจว่า: ใบในกลุ่ม/ใบที่ระบบส่ง → แถวเดียวต่อเลขลีด · รายงานผลไม่แตะ ว/ด/ป · เจ้าของเท่านั้น ·
แบนจากคนที่ถูกแท็กจริง · ขอปลดแบนไม่นับ · ชีตล่มไม่เสียข้อความ · ซ่อม ว/ด/ป เฉพาะแถวที่โดนทับ · ไม่มี LINE id ลงชีต
"""
import io
import os
import re
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone as dtz

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

from checkout import leadsheet as LS  # noqa: E402
from checkout import people  # noqa: E402
from checkout.models import Employee, GroupChat, LeadTask, LineProfile  # noqa: E402
from dashboard.services import google_sheets as G  # noqa: E402

people.BG = False
FAILS = []


def ok(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else " — " + str(extra)))
    if not cond:
        FAILS.append(name)


# ── Google Sheets ปลอม (2 ไฟล์: ชีตลีด + Sheet Master) ─────────────────────
class R:
    def __init__(self, code=200, js=None):
        self.status_code, self._js = code, js or {}
        self.text = str(self._js)

    def json(self):
        return self._js


def _ci(col):
    n = 0
    for ch in col:
        n = n * 26 + ord(ch) - 64
    return n - 1


_RNG = re.compile(r"'(.+)'!([A-Z]+)([0-9]+)(?::([A-Z]+)([0-9]*))?$")
LEAD_SID = G.SHEET_CONFIG["leads"]["spreadsheet_id"]
BAN_SID = G.SHEET_CONFIG["ban_report"]["spreadsheet_id"]
BAN_TAB = G.SHEET_CONFIG["ban_report"]["sheet_name"]
HDR = ["ว/ด/ป", "เบอร์โทร", "เวลา", "Code", "เซลล์", "ทีมไลฟ์", "Admin", "ช่องทาง", "สาขา", "type", "ADS",
       "รถลูกค้าถาม", "CAR / สูตร", "แจ้งหลักฐาน\nการโทร", "FOCUS", "วัน เวลา ที่ติดต่อ", "จำนวนอัพเดท",
       "วัน เวลา อัพเดทล่าสุด", "มากรอกชีตกันเถอะ", "PROFILE ลูกค้า จาก ADMIN", "อาชีพ", "รายได้", "อายุงาน",
       "ประวัติการผ่อน", "ประเภทลูกค้า", "สถานะลูกค้า", "Admin survey", "Status แอดมิน", "อัพเดทเคส"]
BAN_HDR = ["banDate", "time", "seller", "sellerDisplay", "banType", "reason", "bannedBy", "unbanDate", "status",
           "rawText", "groupId"]


def lrow(**kw):
    r = [""] * len(HDR)
    for k, v in kw.items():
        r[HDR.index(k)] = v
    return r


class Fake:
    def __init__(self):
        self.files = {LEAD_SID: {}, BAN_SID: {BAN_TAB: [BAN_HDR, ["1/10/2026", "10:00", "บิว"]]}}
        self.grid = {}
        self.calls, self.fail = [], 0

    def _file(self, url):
        for sid in self.files:
            if "/spreadsheets/" + sid in url:
                return sid
        return None

    def _rows(self, sid, tab, n):
        rows = self.files[sid][tab]
        while len(rows) < n:
            rows.append([])
        return rows[n - 1]

    def get(self, url, params=None, headers=None, timeout=None):
        u = urllib.parse.unquote(url)
        sid = self._file(u)
        self.calls.append(("GET", u))
        if sid is None:
            return R(404, {"error": "ไม่มีไฟล์นี้ในชุดปลอม"})
        if "/values/" not in u:
            return R(200, {"sheets": [{"properties": {"title": t, "sheetId": i, "gridProperties": {
                "rowCount": self.grid.get((sid, t), 4000)}}} for i, t in enumerate(self.files[sid])]})
        m = _RNG.match(u.split("/values/", 1)[1])
        tab = m.group(1)
        if tab not in self.files[sid]:
            return R(400, {"error": "Unable to parse range"})
        c0, r0 = _ci(m.group(2)), int(m.group(3))
        c1 = _ci(m.group(4)) if m.group(4) else c0
        out = [list(r[c0:c1 + 1]) for r in self.files[sid][tab][r0 - 1:]]
        while out and not any(str(v).strip() for v in out[-1]):
            out.pop()
        return R(200, {"values": out})

    def post(self, url, params=None, json=None, headers=None, timeout=None):
        u = urllib.parse.unquote(url)
        sid = self._file(u)
        self.calls.append(("POST", u, json))
        if self.fail:
            self.fail -= 1
            return R(500, {"error": "boom"})
        if u.endswith("values:batchUpdate"):
            for d in json["data"]:
                m = _RNG.match(d["range"])
                tab, n, c = m.group(1), int(m.group(3)), _ci(m.group(2))
                if n > self.grid.get((sid, tab), 4000):
                    return R(400, {"error": "exceeds grid limits"})
                row = self._rows(sid, tab, n)
                while len(row) <= c:
                    row.append("")
                v = d["values"][0][0]
                row[c] = v[1:] if isinstance(v, str) and v.startswith("'") else v     # USER_ENTERED: ' = ข้อความ
            return R(200, {"totalUpdatedCells": len(json["data"])})
        if u.endswith(":batchUpdate"):
            for rq in json["requests"]:
                ad = rq["appendDimension"]
                tab = list(self.files[sid])[ad["sheetId"]]
                self.grid[(sid, tab)] = self.grid.get((sid, tab), 4000) + ad["length"]
            return R(200, {})
        return R(400, {})

    def writes(self):
        return [c for c in self.calls if c[0] == "POST"]

    def cells(self):
        out = {}
        for c in self.writes():
            for d in (c[2] or {}).get("data") or []:
                out[d["range"]] = d["values"][0][0]
        return out


class Creds:
    token = "t"
    valid = True

    def refresh(self, _):
        pass


FAKE = Fake()
P = [mock.patch("requests.get", FAKE.get), mock.patch("requests.post", FAKE.post),
     mock.patch.object(G, "_get_credentials", lambda: Creds()),
     mock.patch.object(G, "fetch_sheet", lambda key: [])]
for p in P:
    p.start()

TAB_OCT, TAB_SEP, TAB_NOV = "ตุลาคม 69", "กันยายน 69", "พฤศจิกายน 69"
FAKE.files[LEAD_SID][TAB_SEP] = [HDR, lrow(**{"ว/ด/ป": "28/9/26", "Code": "TLD9-7700", "เซลล์": "มัท",
                                              "เบอร์โทร": "0811111111"})]
FAKE.files[LEAD_SID][TAB_OCT] = [
    HDR,
    lrow(**{"ว/ด/ป": "28/9/26", "Code": "TLD9-7700", "เซลล์": "มัท", "เบอร์โทร": "0811111111"}),   # เคสค้างก๊อปมา
    lrow(**{"ว/ด/ป": "12/10/26", "Code": "NLD10-9100", "เซลล์": "เฟิร์ส", "เบอร์โทร": "0822222222",
            "วัน เวลา ที่ติดต่อ": "12/10/26 9:00", "จำนวนอัพเดท": "1", "วัน เวลา อัพเดทล่าสุด": "12/10/26 9:00"}),
]

# ── คน + ห้อง ─────────────────────────────────────────────────
U = lambda c: "U" + c * 32                                       # noqa: E731
mat = Employee.objects.create(nickname="มัท", display_name="เซลมัท OxletAuto", position="ทีม A")
first = Employee.objects.create(nickname="เฟิร์ส", display_name="First", position="ทีม A")
kwang = Employee.objects.create(nickname="กวาง", display_name="Kwang", position="ออฟฟิศ บ้านเก่า")
for uid, e in ((U("a"), mat), (U("b"), first), (U("c"), kwang)):
    LineProfile.objects.create(user_id=uid, employee=e, is_employee=True, nickname=e.nickname,
                               display_name=e.display_name)
ROOM = "C" + "1" * 32
OTHER = "C" + "9" * 32
_N = {"i": 0}


def msg(text, uid="", at=None, out=False, extra=None, room=ROOM, name="ห้องจ่ายเบอร์ บ้านเก่า"):
    _N["i"] += 1
    return GroupChat.objects.create(
        chat_type=GroupChat.GROUP, group_id=room, group_name=name, message_id="m%d" % _N["i"],
        sender_id=uid, sender_name="", msg_type="text", text=text, extra=extra if extra is not None else {},
        direction=GroupChat.OUT if out else GroupChat.IN, sent_by_name="กวาง" if out else "",
        sent_at=at or datetime(2026, 10, 13, 3, 0, tzinfo=dtz.utc))           # 10:00 เวลาไทย


SLIP = ("Ac Lead No.   TLD10-9221\nAds  : ทดสอบโฆษณา\nชื่อ Account: ทดสอบ\nID LINE : -\n"
        "เบอร์โทร : 089-123-4567\nช่องทาง  : Live tiktok ช่องขายบอส\nรถ : สนใจ civic fe ปี22\n"
        "ไลฟ์ :   live sale\nเพิ่มเติม : ลูกค้าทำงานโรงงาน ติดต่อได้เลยนะครับ  @เซลมัท OxletAuto")

# ── 1) ปิดอยู่ = ไม่ทำอะไร ─────────────────────────────────────────
msg(SLIP, U("c"), extra={"mention": [U("a")]})
ok("ปิดโดยปริยาย", LS.get_config()["enabled"] is False)
ok("ปิดอยู่ = ไม่ประมวลผล", LS.process_pending() == {"skipped": "ปิดอยู่"} and not FAKE.calls)

LS.set_config(enabled=True)
LS.set_since(datetime(2026, 10, 13, 0, 0, tzinfo=dtz.utc))       # ไล่จากเช้าวันที่ 13

# ── 2) ใบในกลุ่ม → เพิ่มแถว ──────────────────────────────────────
r = LS.process_pending()
oct_ = FAKE.files[LEAD_SID][TAB_OCT]
ok("เพิ่ม 1 แถว", r.get("added") == ["TLD10-9221"], r)
row = oct_[3] if len(oct_) > 3 else []
col = lambda name: row[HDR.index(name)] if row and len(row) > HDR.index(name) else ""    # noqa: E731
ok("ลงแถวต่อจากแถวสุดท้าย (แถว 4)", col("Code") == "TLD10-9221", oct_)
ok("ว/ด/ป = วันที่ใบถึงกลุ่ม (ปี ค.ศ. 4 หลัก)", col("ว/ด/ป") == "13/10/2026", col("ว/ด/ป"))
ok("เวลา = เวลาใบถึงกลุ่ม", col("เวลา") == "10:00", col("เวลา"))
ok("เบอร์ไม่เสียเลข 0", col("เบอร์โทร") == "0891234567", col("เบอร์โทร"))
ok("เซลล์จากคนที่ถูกแท็กจริง", col("เซลล์") == "มัท", col("เซลล์"))
ok("Admin = คนโพสต์", col("Admin") == "กวาง", col("Admin"))
ok("ช่องทางตรงตัวเลือกชีต", col("ช่องทาง") == "LIVE Tiktok / ช่องขายบอส", col("ช่องทาง"))
ok("ทีมไลฟ์ตรงตัวเลือก", col("ทีมไลฟ์") == "Live Sale", col("ทีมไลฟ์"))
ok("type ตามตัวหน้าเลข", col("type") == "TLD", col("type"))
ok("ADS", col("ADS") == "ทดสอบโฆษณา", col("ADS"))
ok("รถลูกค้าถาม + CAR/สูตร", (col("รถลูกค้าถาม"), col("CAR / สูตร")) == ("สนใจ civic fe ปี22", "Civic FE"),
   (col("รถลูกค้าถาม"), col("CAR / สูตร")))
ok("PROFILE ตัดคำ 'ติดต่อได้เลย'", col("PROFILE ลูกค้า จาก ADMIN") == "ลูกค้าทำงานโรงงาน",
   col("PROFILE ลูกค้า จาก ADMIN"))
ok("สาขา", col("สาขา") == "ชลบุรี", col("สาขา"))
ok("ไม่เขียนช่องที่คนกรอกทีหลัง (ติดต่อ/อัพเดท/สถานะ)",
   not any(col(h) for h in ("วัน เวลา ที่ติดต่อ", "จำนวนอัพเดท", "สถานะลูกค้า", "แจ้งหลักฐาน\nการโทร")))

# ── 3) โพสต์ซ้ำ = ไม่เพิ่มแถว · จ่ายใหม่ = เปลี่ยนเซลล์ ───────────────
n_before = len(FAKE.writes())
msg(SLIP, U("c"), extra={"mention": [U("a")]})
r = LS.process_pending()
ok("โพสต์ใบเดิมซ้ำ = ไม่เพิ่มแถว", r.get("dup") == ["TLD10-9221"] and len(FAKE.writes()) == n_before, r)
msg(SLIP.replace("@เซลมัท OxletAuto", "@First"), U("c"), extra={"mention": [U("b")]})
r = LS.process_pending()
ok("จ่ายใหม่ (เลขเดิม คนใหม่) = เปลี่ยนเซลล์ในแถวเดิม", r.get("updated") == ["TLD10-9221"] and col("เซลล์") == "เฟิร์ส",
   (r, col("เซลล์")))
ok("ไม่มีแถวใหม่", len([x for x in oct_ if len(x) > 3 and x[3] == "TLD10-9221"]) == 1)
w0 = len(FAKE.writes())
msg(SLIP.replace("@เซลมัท OxletAuto", "@POOH"), U("c"), extra={})                       # ข้อความเก่า: ไม่มีข้อมูลแท็กจริง
r = LS.process_pending()
ok("★ แท็กที่หาในทะเบียนไม่เจอ ไม่ทับเซลล์เดิม (บั๊กที่เจอจากพรีวิว prod)",
   r.get("dup") == ["TLD10-9221"] and col("เซลล์") == "เฟิร์ส" and len(FAKE.writes()) == w0, (r, col("เซลล์")))

# ── 4) ใบที่ระบบส่งเอง (Connect) → ทางเดียวกัน ───────────────────
LeadTask.objects.create(code="NLD10-9222", run="9222", seller=mat, seller_name="มัท")
SYS = ("Ac Lead No. NLD10-9222\nAds : -\nชื่อ Account: -\nชื่อลูกค้า : ทดสอบสอง\nID LINE : abc_test\n"
       "ชื่อไลน์ : -\nเบอร์โทร : -\nช่องทาง : LINE@\nรถ : -\nไลฟ์ : -\nเพิ่มเติม : -\n@มัท")
msg(SYS, out=True, extra={"source": "connect", "code": "NLD10-9222", "tagged": True})
msg("Ac Lead No. NLD10-9999\n@มัท", out=True, extra={"source": "web"})               # ขาออกที่ไม่ใช่ใบของระบบ
r = LS.process_pending()
ok("ใบระบบ → เพิ่มแถว (ไม่สนใบขาออกอื่น)", r.get("added") == ["NLD10-9222"], r)
row = oct_[4]
ok("ใบระบบ: เซลล์จากงานจ่ายเบอร์ · Admin = คนกดจ่าย", (col("เซลล์"), col("Admin")) == ("มัท", "กวาง"),
   (col("เซลล์"), col("Admin")))
ok("ใบไม่มีเบอร์ = ID LINE", col("เบอร์โทร") == "ID LINE : abc_test", col("เบอร์โทร"))
ok("type NLD = Moderate", col("type") == "Moderate", col("type"))
msg(SYS.replace("NLD10-9222", "NLD10-9222"), U("c"), extra={"mention": [U("a")]})   # แอดมินโพสต์ซ้ำในกลุ่ม
r = LS.process_pending()
ok("2 ฝั่ง เลขเดียวกัน = แถวเดียว", r.get("dup") == ["NLD10-9222"], r)

# ── 5) รายงานผล ─────────────────────────────────────────────────
row = oct_[3]                                                    # TLD10-9221 ตอนนี้เป็นของเฟิร์ส
w0 = len(FAKE.writes())
msg("9221 รอตอบครับ", U("a"), at=datetime(2026, 10, 14, 7, 30, tzinfo=dtz.utc))   # มัทรายงาน แต่ไม่ใช่เจ้าของแล้ว
r = LS.process_pending()
ok("คนรายงานไม่ใช่เจ้าของ = ไม่เขียน", r.get("notOwner") and len(FAKE.writes()) == w0, r)
msg("9221 รอตอบครับ", U("b"), at=datetime(2026, 10, 14, 7, 31, tzinfo=dtz.utc))   # เฟิร์ส (เจ้าของ)
r = LS.process_pending()
ok("เจ้าของรายงาน → ลงชีต", r.get("reports") == 1, r)
ok("จำนวนอัพเดท +1", col("จำนวนอัพเดท") == "1", col("จำนวนอัพเดท"))
ok("อัพเดทล่าสุด = เวลารายงาน", col("วัน เวลา อัพเดทล่าสุด") == "14/10/2026 14:31", col("วัน เวลา อัพเดทล่าสุด"))
ok("ที่ติดต่อ (ว่าง) = เวลารายงาน", col("วัน เวลา ที่ติดต่อ") == "14/10/2026 14:31", col("วัน เวลา ที่ติดต่อ"))
ok("แจ้งหลักฐาน = ส่งแล้ว", col("แจ้งหลักฐาน\nการโทร") == "ส่งแล้ว")
ok("★ ว/ด/ป ไม่ถูกแตะ (บั๊กของ n8n)", col("ว/ด/ป") == "13/10/2026", col("ว/ด/ป"))
a_cells = [k for k in FAKE.cells() if re.search(r"!A\d+$", k)]
ok("ไม่มีการเขียนคอลัมน์ A จากรายงานผลเลย", all(k.endswith(("!A4", "!A5")) for k in a_cells), a_cells)
msg("TLD10-9221 โทรแล้วไม่รับสาย", U("b"), at=datetime(2026, 10, 14, 9, 0, tzinfo=dtz.utc))
msg("10-9221 นัดดูรถพรุ่งนี้", U("b"), at=datetime(2026, 10, 14, 10, 0, tzinfo=dtz.utc))
r = LS.process_pending()
ok("รูปแบบเลขเต็ม + เดือน-เลข ก็นับ", r.get("reports") == 2 and col("จำนวนอัพเดท") == "3", (r, col("จำนวนอัพเดท")))
ok("ที่ติดต่อเดิมไม่ถูกทับ", col("วัน เวลา ที่ติดต่อ") == "14/10/2026 14:31", col("วัน เวลา ที่ติดต่อ"))
w0 = len(FAKE.writes())
msg("9221 @First ตามด้วยครับ", U("c"))
msg("9221", U("b"))
r = LS.process_pending()
ok("แอดมินทวง (@) / เลขเปล่า ไม่ใช่รายงาน", len(FAKE.writes()) == w0 and not r.get("reports"), r)
msg("7700 ลูกค้ายังไม่สะดวก", U("a"))
r = LS.process_pending()
sep_row = FAKE.files[LEAD_SID][TAB_SEP][1]
ok("เคสค้างที่ก๊อปมาเดือนใหม่ → อัปเดตแถวในแท็บเดือนล่าสุด",
   oct_[1][HDR.index("จำนวนอัพเดท")] == "1" and (len(sep_row) <= 16 or not sep_row[16]), (oct_[1], sep_row))

# ── 6) แบน ──────────────────────────────────────────────────────
msg("แบน @First ไม่กรอกชีต ปลดพรุ่งนี้", U("c"), extra={"mention": [U("b")]})
msg("@เซลมัท จองมาแล้ว ขอปลดแบนด้วยค่ะ", U("a"), extra={"mention": [U("c")]})
msg("13/10/69 แบน @เซลมัท ไม่รับเคส", U("c"), extra={"mention": [U("a")]})
r = LS.process_pending()
ban = FAKE.files[BAN_SID][BAN_TAB]
ok("แบน 2 แถว (ขอปลดแบนไม่นับ)", r.get("bans") == 2 and len(ban) == 4, (r, ban))
b1 = dict(zip(BAN_HDR, ban[2] + [""] * 11))
ok("แบน: เซลล์/ประเภท/คนสั่ง/วันปลด", (b1["seller"], b1["banType"], b1["bannedBy"], b1["unbanDate"]) ==
   ("เฟิร์ส", "ไม่กรอกชีต", "กวาง", "14/10/2026"), b1)
b2 = dict(zip(BAN_HDR, ban[3] + [""] * 11))
ok("ปี พ.ศ. 2 หลัก (69) = 2026 ไม่ใช่ 1969", b2["banDate"] == "13/10/2026", b2["banDate"])
LS.set_config(ban=False)
msg("แบน @First ไม่รับเคส", U("c"), extra={"mention": [U("b")]})
LS.process_pending()
ok("ปิดรายงานแบนได้", len(ban) == 4)
LS.set_config(ban=True)

# ── 7) ห้องอื่นไม่นับ · ชีตล่มไม่เสียข้อความ · แท็บยังไม่มี ───────────────
msg(SLIP.replace("TLD10-9221", "TLD10-9300"), U("c"), extra={"mention": [U("a")]}, room=OTHER, name="ทีมAdmin")
r = LS.process_pending()
ok("ห้องที่ไม่ใช่ห้องจ่ายเบอร์ = ไม่อ่าน", r.get("pending") == 0, r)
before = LS._kv(LS.KV_STATE)["last_id"]
FAKE.fail = 1
msg(SLIP.replace("TLD10-9221", "TLD10-9301"), U("c"), extra={"mention": [U("a")]})
r = LS.process_pending()
ok("เขียนล้ม = ไม่ขยับตัวชี้", r.get("error") and LS._kv(LS.KV_STATE)["last_id"] == before, r)
r = LS.process_pending()
ok("รอบถัดไปเขียนได้", r.get("added") == ["TLD10-9301"], r)
msg(SLIP.replace("TLD10-9221", "TLD11-9400"), U("c"), at=datetime(2026, 11, 1, 3, 0, tzinfo=dtz.utc),
    extra={"mention": [U("a")]})
r = LS.process_pending()
ok("ยังไม่มีแท็บเดือนใหม่ = ค้างไว้ บอกเหตุผล", "ยังไม่มีแท็บ" in (r.get("error") or ""), r)
FAKE.files[LEAD_SID][TAB_NOV] = [HDR]
FAKE.grid[(LEAD_SID, TAB_NOV)] = 1
r = LS.process_pending()
nov = FAKE.files[LEAD_SID][TAB_NOV]
ok("สร้างแท็บแล้ว → ลงแถว 2 (ขยายตารางให้เอง)", r.get("added") == ["TLD11-9400"] and nov[1][3] == "TLD11-9400",
   (r, nov))

# ── 8) ซ่อม ว/ด/ป ที่ n8n เขียนทับ ─────────────────────────────────
FAKE.files[LEAD_SID][TAB_OCT].append(lrow(**{"ว/ด/ป": "13/10/26", "Code": "NLD10-9050", "เซลล์": "มัท",
                                             "วัน เวลา ที่ติดต่อ": "7/10/26 11:43",
                                             "วัน เวลา อัพเดทล่าสุด": "13/10/26 15:46"}))
FAKE.files[LEAD_SID][TAB_OCT].append(lrow(**{"ว/ด/ป": "13/10/26", "Code": "NLD10-9051", "เซลล์": "มัท",
                                             "วัน เวลา ที่ติดต่อ": "8/10/26 10:00",
                                             "วัน เวลา อัพเดทล่าสุด": "13/10/26 15:50"}))   # ไม่มีใบในคลัง
FAKE.files[LEAD_SID][TAB_OCT].append(lrow(**{"ว/ด/ป": "13/10/26", "Code": "NLD10-9052", "เซลล์": "มัท",
                                             "วัน เวลา อัพเดทล่าสุด": "14/10/26 9:00"}))    # ไม่ใช่ลายเซ็นบั๊ก
msg("Ac Lead No. NLD10-9050\nเบอร์โทร : 0833333333\n@เซลมัท", U("c"), at=datetime(2026, 10, 7, 4, 40, tzinfo=dtz.utc))
msg("Ac Lead No. NLD10-9052\nเบอร์โทร : 0844444444\n@เซลมัท", U("c"), at=datetime(2026, 10, 7, 4, 41, tzinfo=dtz.utc))
LS.set_since()                                                   # ใบเก่าพวกนี้ไม่ต้องลงชีตซ้ำ
rep = LS.repair_dates([TAB_OCT], apply=False)
ok("หาแถวที่โดนทับเจอ (มีใบในคลัง)", [f["code"] for f in rep["fix"]] == ["NLD10-9050"], rep["fix"])
ok("แถวที่หาใบไม่เจอ = รายงาน ไม่แก้", [f["code"] for f in rep["unknown"]] == ["NLD10-9051"], rep["unknown"])
w0 = len(FAKE.writes())
ok("ดูเฉยๆ = ไม่เขียน", len(FAKE.writes()) == w0)
rep = LS.repair_dates([TAB_OCT], apply=True)
fixed = [x for x in FAKE.files[LEAD_SID][TAB_OCT] if len(x) > 3 and x[3] == "NLD10-9050"][0]
ok("apply = คืนวันที่จริง", rep["applied"] == 1 and fixed[0] == "7/10/2026", fixed[0])
last = FAKE.writes()[-1][2]["data"]
ok("ซ่อมเขียนเฉพาะคอลัมน์ A", all(re.search(r"!A\d+$", d["range"]) for d in last), last)
untouched = [x for x in FAKE.files[LEAD_SID][TAB_OCT] if len(x) > 3 and x[3] == "NLD10-9052"][0]
ok("ว/ด/ป ≠ วันอัพเดทล่าสุด = ไม่แตะ", untouched[0] == "13/10/26", untouched[0])

# ── 9) ตัวช่วย ──────────────────────────────────────────────────
ok("type: RHLD = Hot RJ · RNLD = RJ · RB = Hot RB · HLD = Very Hot · WLD = Hot · BLD",
   [LS.lead_type(c) for c in ("RHLD10-1/1", "RNLD10-2/1", "RB-3", "HLD10-4", "WLD10-5", "BLD10-6")] ==
   ["Hot RJ", "RJ", "Hot RB", "Very Hot", "Hot", "BLD"])
ok("TikTokAds = TLD เสมอ", LS.lead_type("NLD10-1", "TikTokAds") == "TLD")
ok("ช่องทางว่าง = LINE@", LS.match_channel("") == "LINE@")
ok("TikTok แซน → Tiktok ช่องแซน", LS.match_channel("TikTok แซน") == "Tiktok ช่องแซน", LS.match_channel("TikTok แซน"))
ok("TT รถเข้าใหม่ → ตัวเลือกที่ขึ้นต้นเหมือนกัน", LS.match_channel("TT รถเข้าใหม่") == "TIKTOK รถเข้าใหม่อ๊อกเล็ตธ์",
   LS.match_channel("TT รถเข้าใหม่"))
ok("ไม่ตรงกติกาไหน = คำเดิม (ไม่เดา)", LS.match_channel("ช่องลึกลับ xyz") == "ช่องลึกลับ xyz")
ok("รายงาน 9075/1", LS.parse_report("9075/1 ได้รถแล้วครับ")["slash"] == 1)
ok("ใบจ่ายลีดไม่ใช่รายงาน", LS.parse_report(SLIP) is None)

# ── 10) ไม่มี LINE user id ลงชีต + store_chat เก็บคนที่ถูกแท็ก ─────────────
leak = [v for v in FAKE.cells().values() if re.search(r"U[0-9a-f]{32}", str(v))]
ok("ไม่มี LINE user id ในค่าที่เขียนลงชีต", not leak, leak)
from checkout import views as CV  # noqa: E402

with mock.patch.object(CV, "line_cfg", lambda: {"store_chat": True}), \
        mock.patch.object(people, "touch_profile", lambda *a, **k: {"name": "กวาง"}):
    CV.store_chat({"events": [{"type": "message", "timestamp": int(datetime.now(dtz.utc).timestamp() * 1000),
                               "source": {"type": "group", "groupId": ROOM, "userId": U("c")},
                               "message": {"id": "real-1", "type": "text", "text": "แบน @First",
                                           "mention": {"mentionees": [{"type": "user", "userId": U("b")},
                                                                      {"type": "all"}]}}}]})
g = GroupChat.objects.filter(message_id="real-1").first()
ok("store_chat เก็บ user id ของคนที่ถูกแท็กจริง (ไม่เอา @All)", g and g.extra.get("mention") == [U("b")],
   g and g.extra)

for p in P:
    p.stop()
_runner.teardown_databases(_old)
print()
print("ผ่านทั้งหมด" if not FAILS else "ไม่ผ่าน %d ข้อ: %s" % (len(FAILS), ", ".join(FAILS)))
sys.exit(1 if FAILS else 0)
