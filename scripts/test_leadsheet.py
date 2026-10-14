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
from dashboard.services import line_channels  # noqa: E402

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
        self.cols = {}                   # แท็บที่สร้างผ่าน addSheet: จำนวนคอลัมน์ (ค่าตั้งต้นของ Google = 26)
        self.calls, self.fail = [], 0
        # แท็บเดือนจริงตั้งรูปแบบคอลัมน์ ว/ด/ป เป็น d/m/yy — เขียน 13/10/2026 แล้วอ่านกลับได้ 13/10/26 (เหมือน prod)
        self.date_yy = False
        self.line = []                   # ข้อความที่ยิงไป LINE push (แจ้งเตือนเจ้าของ) — ไม่นับเป็นการเขียนชีต

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
        if "api.line.me" in u:
            self.line.append(json)
            return R(200, {})
        sid = self._file(u)
        self.calls.append(("POST", u, json))
        if self.fail:
            self.fail -= 1
            return R(500, {"error": "boom"})
        if u.endswith("values:batchUpdate"):
            for d in json["data"]:
                m = _RNG.match(d["range"])
                tab, n, c = m.group(1), int(m.group(3)), _ci(m.group(2))
                if n > self.grid.get((sid, tab), 4000) or c >= self.cols.get((sid, tab), 99):
                    return R(400, {"error": "exceeds grid limits"})
                row = self._rows(sid, tab, n)
                while len(row) <= c:
                    row.append("")
                v = d["values"][0][0]
                row[c] = v[1:] if isinstance(v, str) and v.startswith("'") else v     # USER_ENTERED: ' = ข้อความ
                if self.date_yy and c == 0 and isinstance(row[c], str):
                    row[c] = re.sub(r"^(\d{1,2}/\d{1,2}/)\d{2}(\d{2})$", r"\1\2", row[c])
            return R(200, {"totalUpdatedCells": len(json["data"])})
        if u.endswith(":batchUpdate"):
            for rq in json["requests"]:
                if "addSheet" in rq:
                    pr = rq["addSheet"]["properties"]
                    self.files[sid][pr["title"]] = []
                    self.cols[(sid, pr["title"])] = (pr.get("gridProperties") or {}).get("columnCount", 26)
                    continue
                if "deleteSheet" in rq:
                    del self.files[sid][list(self.files[sid])[rq["deleteSheet"]["sheetId"]]]
                    continue
                if "cutPaste" in rq:                             # ย้ายช่วงเซลล์ (ค่าไปครบ · ต้นทางว่าง)
                    cp = rq["cutPaste"]
                    src, dst = cp["source"], cp["destination"]
                    tabs = list(self.files[sid])
                    st, dt = tabs[src["sheetId"]], tabs[dst["sheetId"]]
                    if dst["rowIndex"] + 1 > self.grid.get((sid, dt), 4000):
                        return R(400, {"error": "exceeds grid limits"})
                    srow = self._rows(sid, st, src["startRowIndex"] + 1)
                    vals = list(srow[src["startColumnIndex"]:src["endColumnIndex"]])
                    drow = self._rows(sid, dt, dst["rowIndex"] + 1)
                    while len(drow) < dst["columnIndex"] + len(vals):
                        drow.append("")
                    drow[dst["columnIndex"]:dst["columnIndex"] + len(vals)] = vals
                    for i in range(src["startColumnIndex"], min(src["endColumnIndex"], len(srow))):
                        srow[i] = ""
                    continue
                if "deleteDimension" in rq:                      # ลบแถว (ทีละคำขอ ตามลำดับที่ส่งมา)
                    rg = rq["deleteDimension"]["range"]
                    tab = list(self.files[sid])[rg["sheetId"]]
                    del self.files[sid][tab][rg["startIndex"]:rg["endIndex"]]
                    continue
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
     mock.patch.object(G, "fetch_sheet", lambda key: []),
     mock.patch.object(line_channels, "dm_token", lambda: "TEST_DM_TOKEN")]
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
owner = Employee.objects.create(nickname="Wattanakit", display_name="วัฒนกิจ", position="")
for uid, e in ((U("a"), mat), (U("b"), first), (U("c"), kwang), (U("e"), owner)):
    LineProfile.objects.create(user_id=uid, employee=e, is_employee=True, nickname=e.nickname,
                               display_name=e.display_name)


def line_texts(since=0):
    return [m["text"] for b in FAKE.line[since:] for m in b.get("messages", [])]
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
ok("แจ้ง LINE เจ้าของ: รายงานผลไม่ลงชีต (ไม่ใช่เจ้าของ)",
   any("รายงานผลไม่ลงชีต" in t and "มัท" in t and "เฟิร์ส" in t for t in line_texts()), line_texts())
ok("แจ้งไปที่ LINE ของ Wattanakit", FAKE.line and FAKE.line[-1]["to"] == U("e"), FAKE.line[-1:])
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
# ★ 13 ต.ค.69 เจ้าของสั่ง: ยังไม่มีแท็บเดือนใหม่ = ลงแท็บเดิมไปก่อน · แท็บใหม่มาเมื่อไหร่ค่อยลงแท็บใหม่
other_before = [list(x) for x in oct_]
n_line = len(FAKE.line)
msg(SLIP.replace("TLD10-9221", "TLD11-9400"), U("c"), at=datetime(2026, 11, 1, 3, 0, tzinfo=dtz.utc),
    extra={"mention": [U("a")]})
r = LS.process_pending()
in_oct = [x for x in oct_ if len(x) > 3 and x[3] == "TLD11-9400"]
ok("ยังไม่มีแท็บเดือนใหม่ = ลงแท็บเดิม (ตุลาคม) ไปก่อน ไม่ค้าง", r.get("added") == ["TLD11-9400"] and len(in_oct) == 1
   and not r.get("error"), r)
ok("ว/ด/ป ของใบ = วันที่ใบถึงกลุ่ม (1 พ.ย.)", in_oct and in_oct[0][0] == "1/11/2026", in_oct)
ok("จดไว้รอย้าย", [(x["want"], x["tab"], x["code"]) for x in LS._kv(LS.KV_FALLBACK).get("rows") or []]
   == [(TAB_NOV, TAB_OCT, "TLD11-9400")], LS._kv(LS.KV_FALLBACK))
ok("แจ้ง LINE: ยังไม่มีแท็บใหม่ ลงแท็บเดิมไปก่อน", any("ยังไม่มีแท็บ" in t and TAB_OCT in t for t in line_texts(n_line)),
   line_texts(n_line))
msg("9400 รอตอบครับ", U("a"), at=datetime(2026, 11, 1, 4, 0, tzinfo=dtz.utc))
r = LS.process_pending()
ok("รายงานผลของใบที่ลงแท็บเดิม → ลงได้", r.get("reports") == 1 and in_oct[0][HDR.index("จำนวนอัพเดท")] == "1", r)
FAKE.files[LEAD_SID][TAB_NOV] = []                               # แอดมินสร้างแท็บไว้เปล่าๆ (ยังไม่มีหัวตาราง)
FAKE.grid[(LEAD_SID, TAB_NOV)] = 1
msg(SLIP.replace("TLD10-9221", "TLD11-9401").replace("089-123-4567", "089-555-0001"), U("c"),
    at=datetime(2026, 11, 1, 5, 0, tzinfo=dtz.utc), extra={"mention": [U("a")]})
LS._set_kv(LS.KV_FALLBACK, dict(LS._kv(LS.KV_FALLBACK), checkedAt=""))
r = LS.process_pending()
ok("แท็บใหม่ยังเปล่า (ไม่มีหัวตาราง) = ลงแท็บเดิมต่อ ไม่ค้างทั้งคิว", r.get("added") == ["TLD11-9401"]
   and not r.get("error"), r)
ok("แท็บใหม่ยังไม่พร้อม = ยังไม่ย้าย", len(LS._kv(LS.KV_FALLBACK).get("rows") or []) == 2)
w_calls = len(FAKE.calls)
r = LS.process_pending()
ok("ไม่มีข้อความใหม่ + เพิ่งเช็ค = ไม่ยิง Google", r == {"pending": 0} and len(FAKE.calls) == w_calls, r)
FAKE.files[LEAD_SID][TAB_NOV].append(list(HDR))                 # แอดมินวางหัวตาราง
LS._set_kv(LS.KV_FALLBACK, dict(LS._kv(LS.KV_FALLBACK), checkedAt=""))
n_line = len(FAKE.line)
r = LS.process_pending()
nov = FAKE.files[LEAD_SID][TAB_NOV]
moved = [x[3] for x in nov[1:] if len(x) > 3 and x[3]]
ok("แท็บใหม่มา → ย้าย 2 ใบไปต่อท้ายแท็บใหม่ ตามลำดับเดิม (ขยายตารางให้เอง)", moved == ["TLD11-9400", "TLD11-9401"],
   nov)
ok("ย้ายทั้งแถว (รวมจำนวนอัพเดทจากรายงานผล + ว/ด/ป)", len(nov) > 1 and nov[1][HDR.index("จำนวนอัพเดท")] == "1"
   and nov[1][0] == "1/11/2026", nov[1:2])
ok("แถวที่ย้ายถูกลบจากแท็บเดิม", not [x for x in oct_ if len(x) > 3 and x[3] in ("TLD11-9400", "TLD11-9401")])
ok("แถวอื่นในแท็บเดิมไม่ถูกแตะ", oct_ == other_before, (len(oct_), len(other_before)))
ok("ล้างรายการรอย้าย", not LS._kv(LS.KV_FALLBACK).get("rows"))
ok("แจ้ง LINE: ย้ายให้แล้ว", any("ย้ายใบ" in t and "TLD11-9400" in t for t in line_texts(n_line)), line_texts(n_line))
msg(SLIP.replace("TLD10-9221", "TLD11-9402").replace("089-123-4567", "089-555-0002"), U("c"),
    at=datetime(2026, 11, 1, 6, 0, tzinfo=dtz.utc), extra={"mention": [U("a")]})
r = LS.process_pending()
ok("ใบหลังแท็บใหม่มา → ลงแท็บใหม่ตรงๆ", r.get("added") == ["TLD11-9402"] and nov[-1][3] == "TLD11-9402"
   and not LS._kv(LS.KV_FALLBACK).get("rows"), (r, nov[-1]))

# ── 7b) แจ้ง LINE เมื่อบันทึกชีตไม่ได้ — ครั้งเดียวต่อชั่วโมง · กลับมาได้แจ้งว่าหายแล้ว ──────────────
n_line = len(FAKE.line)
FAKE.fail = 1
msg(SLIP.replace("TLD10-9221", "TLD11-9403").replace("089-123-4567", "089-555-0003"), U("c"),
    at=datetime(2026, 11, 1, 7, 0, tzinfo=dtz.utc), extra={"mention": [U("a")]})
r = LS.process_pending()
ok("บันทึกชีตไม่ได้ → แจ้ง LINE (บอกว่าข้อความไม่หาย)", r.get("error")
   and any("บันทึกชีตไม่ได้" in t and "ไม่หาย" in t for t in line_texts(n_line)), line_texts(n_line))
n_line = len(FAKE.line)
FAKE.fail = 1
r = LS.process_pending()
ok("ล้มซ้ำภายในชั่วโมง = ไม่แจ้งซ้ำ", r.get("error") and len(FAKE.line) == n_line, line_texts(n_line))
r = LS.process_pending()
ok("กลับมาบันทึกได้ → ลงครบ + แจ้งว่าหายแล้ว", r.get("added") == ["TLD11-9403"]
   and any("กลับมาบันทึกชีตได้แล้ว" in t for t in line_texts(n_line)), (r, line_texts(n_line)))
n_line = len(FAKE.line)
msg("9999 ลูกค้าไม่รับสาย", U("a"), at=datetime(2026, 11, 1, 8, 0, tzinfo=dtz.utc))
r = LS.process_pending()
ok("หาเลขที่รายงานไม่เจอ → แจ้ง LINE", any("หาเลข" in t and "9999" in t for t in line_texts(n_line)), line_texts(n_line))
n_line = len(FAKE.line)
msg("9400 รอตอบ", "U" + "f" * 32, at=datetime(2026, 11, 1, 8, 5, tzinfo=dtz.utc))   # คนนอกทะเบียน
r = LS.process_pending()
ok("คนรายงานไม่อยู่ในทะเบียน → แจ้ง LINE (เดิมข้ามเงียบ)",
   any("ไม่อยู่ในทะเบียน" in t for t in line_texts(n_line)), (r, line_texts(n_line)))
ok("ทุกแจ้งเตือนไปที่ Wattanakit · ไม่มี LINE id ในข้อความ",
   all(b["to"] == U("e") for b in FAKE.line) and not any(re.search(r"U[0-9a-f]{32}", t) for t in line_texts()),
   line_texts())
LS.set_config(alert=False)
n_line = len(FAKE.line)
msg("9998 ลูกค้าไม่รับสาย", U("a"), at=datetime(2026, 11, 1, 8, 10, tzinfo=dtz.utc))
LS.process_pending()
ok("ปิดแจ้งเตือนได้", len(FAKE.line) == n_line)
LS.set_config(alert=True)

# ── 7c) หัวคอลัมน์ขยับ / เปลี่ยนชื่อ / ถูกลบ → ปรับเองได้ก็ปรับ + แจ้งเจ้าของทุกกรณี (14 ต.ค.69) ─────────────
ok("จำตำแหน่งคอลัมน์ล่าสุดของแท็บไว้", str(G.LEADS_COL.lead_code) in (LS._kv(LS.KV_COLS).get(TAB_NOV) or {}),
   LS._kv(LS.KV_COLS))


def nslip(code, minute):
    return msg(SLIP.replace("TLD10-9221", code).replace("089-123-4567", "089-556-%04d" % minute), U("c"),
               at=datetime(2026, 11, 1, 9, minute, tzinfo=dtz.utc), extra={"mention": [U("a")]})


def nrow(code, hdr):
    ci = hdr.index("Code")
    got = [x for x in nov if len(x) > ci and x[ci] == code]
    return got[0] if got else []


def at(row_, name, hdr):
    i = hdr.index(name)
    return row_[i] if len(row_) > i else ""


# a) แทรกคอลัมน์ใหม่ที่ B — ทุกคอลัมน์ขยับไป 1 ช่อง
for r_ in nov:
    r_.insert(1, "")
nov[0][1] = "หมายเหตุแอดมิน"
H1 = list(nov[0])
n_line = len(FAKE.line)
nslip("TLD11-9410", 1)
r = LS.process_pending()
x = nrow("TLD11-9410", H1)
ok("คอลัมน์ขยับ → ลงช่องถูกทุกช่อง (จับด้วยชื่อหัวคอลัมน์)", r.get("added") == ["TLD11-9410"] and x
   and (at(x, "เซลล์", H1), at(x, "ADS", H1), at(x, "หมายเหตุแอดมิน", H1)) == ("มัท", "ทดสอบโฆษณา", ""), (r, x))
ok("แจ้ง LINE: คอลัมน์ขยับ ปรับให้แล้ว", any("คอลัมน์ขยับ" in t and TAB_NOV in t for t in line_texts(n_line)),
   line_texts(n_line))
n_line = len(FAKE.line)
nslip("TLD11-9414", 2)
LS.process_pending()
ok("ขยับแล้วรอบถัดไปไม่แจ้งซ้ำ", not any("คอลัมน์ขยับ" in t for t in line_texts(n_line)), line_texts(n_line))

# b) เปลี่ยนชื่อหัวคอลัมน์ในที่เดิม "เซลล์" → "คนดูแลเคส" (ระบบไม่รู้จักชื่อนี้)
i_sel = H1.index("เซลล์")
nov[0][i_sel] = "คนดูแลเคส"
n_line = len(FAKE.line)
nslip("TLD11-9411", 3)
r = LS.process_pending()
x = nrow("TLD11-9411", H1)
ok("หัวคอลัมน์ถูกเปลี่ยนชื่อ → บันทึกลงคอลัมน์เดิมต่อ", r.get("added") == ["TLD11-9411"] and x and x[i_sel] == "มัท",
   (r, x))
ok("แจ้ง LINE: เปลี่ยนชื่อ + ใช้คอลัมน์เดิมต่อ",
   any("เปลี่ยนชื่อเป็น" in t and "คนดูแลเคส" in t for t in line_texts(n_line)), line_texts(n_line))
msg("9411 รอตอบครับ", U("a"), at=datetime(2026, 11, 1, 9, 30, tzinfo=dtz.utc))
r = LS.process_pending()
ok("รายงานผลยังหาเจ้าของเคสเจอ (อ่านช่องเซลล์จากคอลัมน์เดิม)", r.get("reports") == 1, r)
nov[0][i_sel] = "เซลล์"

# c) ลบคอลัมน์ ADS — ทุกคอลัมน์หลังจากนั้นเลื่อนซ้าย → ไม่เดาตำแหน่ง · แจ้งว่าหาไม่เจอ · ช่องอื่นยังลงถูก
i_ads = H1.index("ADS")
for r_ in nov:
    if len(r_) > i_ads:
        del r_[i_ads]
H2 = list(nov[0])
n_line = len(FAKE.line)
nslip("TLD11-9412", 4)
r = LS.process_pending()
x = nrow("TLD11-9412", H2)
ok("คอลัมน์ถูกลบ → ช่องอื่นยังลงถูก", r.get("added") == ["TLD11-9412"] and x
   and (at(x, "เซลล์", H2), at(x, "รถลูกค้าถาม", H2)) == ("มัท", "สนใจ civic fe ปี22"), (r, x))
ok("ไม่เดาตำแหน่ง (ค่า ADS ไม่ไปโผล่ช่องอื่น)", x and "ทดสอบโฆษณา" not in x, x)
ok("แจ้ง LINE: หาหัวคอลัมน์ ADS ไม่เจอ ช่องนี้ไม่ได้บันทึก",
   any('"ADS"' in t and "ไม่เจอ" in t and "ไม่ได้บันทึก" in t for t in line_texts(n_line)), line_texts(n_line))
ok("สถานะรอบล่าสุดบอกเรื่องคอลัมน์", any("ADS" in c for c in (r.get("columns") or [])), r.get("columns"))

# d) หัว "Code" ถูกเปลี่ยนชื่อในที่เดิม → ใช้คอลัมน์เดิมต่อ (ไม่ทำให้ทั้งแท็บใช้ไม่ได้)
i_code = H2.index("Code")
nov[0][i_code] = "เลขลีด"
n_line = len(FAKE.line)
nslip("TLD11-9413", 5)
r = LS.process_pending()
ok("หัว Code ถูกเปลี่ยนชื่อ → ยังลงแท็บเดิมของเดือน (ไม่ไปลงแท็บเดือนก่อน)",
   r.get("added") == ["TLD11-9413"] and nrow("TLD11-9413", nov[0][:i_code] + ["Code"] + nov[0][i_code + 1:])
   and not LS._kv(LS.KV_FALLBACK).get("rows"), r)
ok("แจ้ง LINE: หัว Code ถูกเปลี่ยนชื่อ", any("เลขลีด" in t and "Code" in t for t in line_texts(n_line)),
   line_texts(n_line))
nov[0][i_code] = "Code"

# e) หัว Code หายและเดาไม่ได้ (ไม่มีตำแหน่งที่จำไว้) → ลงแท็บเดือนก่อนไปก่อน + แจ้ง · แก้หัวแล้วย้ายกลับให้เอง
cols = LS._kv(LS.KV_COLS)
cols.pop(TAB_NOV, None)
LS._set_kv(LS.KV_COLS, cols)
nov[0][i_code] = "รหัสใหม่"
n_line = len(FAKE.line)
nslip("TLD11-9415", 6)
r = LS.process_pending()
ok("หัว Code หาย เดาไม่ได้ → ลงแท็บเดือนก่อนไปก่อน ไม่ค้าง", r.get("added") == ["TLD11-9415"]
   and [x["code"] for x in LS._kv(LS.KV_FALLBACK).get("rows") or []] == ["TLD11-9415"], (r, LS._kv(LS.KV_FALLBACK)))
ok("แจ้ง LINE: หาหัวคอลัมน์ Code ไม่เจอ + หัวตารางตอนนี้",
   any("Code" in t and "ไม่เจอ" in t and "รหัสใหม่" in t for t in line_texts(n_line)), line_texts(n_line))
nov[0][i_code] = "Code"
LS._set_kv(LS.KV_FALLBACK, dict(LS._kv(LS.KV_FALLBACK), checkedAt=""))
n_line = len(FAKE.line)
LS.process_pending()
x = nrow("TLD11-9415", H2)
ok("แก้หัวกลับแล้ว → ย้ายใบกลับแท็บของเดือนให้เอง", x and not LS._kv(LS.KV_FALLBACK).get("rows")
   and not [y for y in oct_ if len(y) > 3 and y[3] == "TLD11-9415"], x)
ok("★ แท็บใหม่จัดคอลัมน์ต่างจากแท็บเดิม → ย้ายตามชื่อหัวคอลัมน์ ลงช่องถูก (ไม่ตัดแปะทั้งแถว)",
   x and (at(x, "เซลล์", H2), at(x, "เบอร์โทร", H2), at(x, "ว/ด/ป", H2), at(x, "หมายเหตุแอดมิน", H2))
   == ("มัท", "0895560006", "1/11/2026", ""), x)
ok("แจ้ง LINE: ย้ายตามชื่อหัวคอลัมน์ + บอกคอลัมน์ที่แท็บใหม่ไม่มี (ADS)",
   any("ย้ายตามชื่อหัวคอลัมน์" in t and "ADS" in t for t in line_texts(n_line)), line_texts(n_line))

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

# ── 9b) จำลองแอดมินจ่ายเบอร์ (manage.py leadsheet --simulate) ─────────────
with mock.patch.object(LS.timezone, "localdate", lambda: datetime(2026, 10, 13).date()):
    before_oct = [list(x) for x in FAKE.files[LEAD_SID][TAB_OCT]]
    rep = LS.simulate("มัท", "กวาง", "เฟิร์ส")
    sim = FAKE.files[LEAD_SID].get(LS.SIM_TAB) or []
text = "\n".join(rep)
ok("จำลอง: สร้างแท็บทดสอบ + หัวตารางก๊อปจากเดือนนี้", sim and sim[0][:4] == HDR[:4], sim[:1])
ok("จำลอง: ลงแถวเดียว (โพสต์ซ้ำไม่เพิ่ม)", len([x for x in sim[1:] if len(x) > 3 and x[3]]) == 1, sim)
ok("จำลอง: เซลล์จากแท็กจริง + รายงานผลลง + คนอื่นรายงานไม่ลง",
   "add" in text and "dup" in text and "report" in text and "not-owner" in text, text)
ok("จำลอง: ว/ด/ป ไม่ถูกทับ", "ไม่ถูกทับ ✓" in text, text)
ok("จำลอง: แท็บเดือนจริงไม่ถูกแตะ", FAKE.files[LEAD_SID][TAB_OCT] == before_oct)
ok("จำลอง: ไม่มี LINE id ในรายงาน", not re.search(r"U[0-9a-f]{32}", text))
ok("ลบแท็บทดสอบได้", LS.delete_sim_tab() and LS.SIM_TAB not in FAKE.files[LEAD_SID])

# ── 9c) จำลองต่อท้ายแท็บเดือนจริง (--in-month-tab) + ลบเฉพาะแถวที่จำลองสร้าง ─────
oct_now = FAKE.files[LEAD_SID][TAB_OCT]
last_before = max(i for i, x in enumerate(oct_now) if any(str(v).strip() for v in x[:5]))
snapshot = [list(x) for x in oct_now]
FAKE.date_yy = True                                              # แท็บเดือนจริงโชว์ปี 2 หลัก (เหมือน prod)
with mock.patch.object(LS.timezone, "localdate", lambda: datetime(2026, 10, 13).date()):
    rep = LS.simulate("มัท", "กวาง", "เฟิร์ส", real_tab=True)
FAKE.date_yy = False
text = "\n".join(rep)
ok("แท็บจริงโชว์ ว/ด/ป ปี 2 หลัก (ชุดปลอมจำลองได้)", re.search(r"หลังรายงาน = \d{1,2}/\d{1,2}/\d{2} ", text), text)
sim_code = re.search(r"Ac Lead No\.\s+(\S+)", text).group(1)
added_at = [i for i, x in enumerate(oct_now) if len(x) > 3 and x[3] == sim_code]
ok("ต่อท้ายแถวสุดท้ายของแท็บเดือนจริง", added_at == [last_before + 1], (added_at, last_before))
ok("รายงานผล + ว/ด/ป ไม่ถูกทับ (แท็บจริง)", "report" in text and "ไม่ถูกทับ ✓" in text, text)
ok("จดเลขแถวจำลองไว้ให้ลบ", LS._kv(LS.KV_SIM).get("rows") == [{"tab": TAB_OCT, "code": sim_code}])
decoy = lrow(**{"ว/ด/ป": "13/10/26", "Code": sim_code, "เซลล์": "นวล", "ADS": "โฆษณาจริง"})
oct_now.append(decoy)                                            # แถวจริงที่บังเอิญเลขเดียวกัน (ADS ไม่ใช่ป้ายจำลอง)
gone = LS.delete_sim_rows()
ok("ลบแถวจำลองแถวเดียว", gone == ["%s แถว %d" % (TAB_OCT, last_before + 2)], gone)
ok("แถวอื่นไม่ถูกแตะ (เทียบก่อนจำลอง)", oct_now[:len(snapshot)] == snapshot)
ok("แถวเลขเดียวกันแต่ไม่ใช่ของจำลอง ไม่ถูกลบ", oct_now[-1] == decoy)
oct_now.pop()
ok("ลบซ้ำ = ไม่มีอะไรให้ลบ", LS.delete_sim_rows() == [])

# ── 9d) ทดสอบย้ายข้ามแท็บกับชีต (manage.py leadsheet --test-month-move) ─────────────
oct_snapshot = [list(x) for x in FAKE.files[LEAD_SID][TAB_OCT]]
with mock.patch.object(LS.timezone, "localdate", lambda: datetime(2026, 10, 13).date()):
    rep = LS.move_selftest()
ok("คำสั่งทดสอบย้ายข้ามแท็บ: ผ่านทุกข้อ", rep[0].startswith("ผลรวม: ใช้ได้") and not any(x.startswith("ไม่ผ่าน") for x in rep),
   rep)
ok("คำสั่งทดสอบย้าย: ลบแท็บชั่วคราวทิ้ง · แท็บเดือนจริงไม่ถูกแตะ",
   not any(t in FAKE.files[LEAD_SID] for t in LS.MOVE_TEST_TABS) and FAKE.files[LEAD_SID][TAB_OCT] == oct_snapshot)
cut = [rq for c in FAKE.writes() for rq in ((c[2] or {}).get("requests") or []) if "cutPaste" in rq]
ok("ย้ายด้วย cutPaste (ค่า+รูปแบบไปครบ ไม่อ่านแล้วเขียนใหม่)", cut, len(cut))

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

# ── 11) log ทุกเรื่อง + แจ้งเตือนเมื่อพังกะทันหัน + ตัวเฝ้าระบบ (14 ต.ค.69 เจ้าของสั่ง) ─────────────
from dashboard.models import EventLog  # noqa: E402
from dashboard.services import sheet_mirror as SM  # noqa: E402
from dashboard.services.cache_store import set_kv as _setkv  # noqa: E402
from django.utils import timezone as djtz  # noqa: E402

LS.process_pending()                                              # เคลียร์ของค้างก่อนเริ่มส่วนนี้
ev = EventLog.objects.filter(kind="leadsheet")


def ev_has(text, **kw):                                           # SQLite ไม่รองรับค้นใน JSON → กรองใน Python
    return any(text in str((e.detail or {}).get("text", "")) for e in ev.filter(**kw))


ok("ทุกเรื่องที่แจ้ง = 1 แถวใน dash_event_log (kind=leadsheet)", ev.count() > 0, ev.count())
ok("log: บันทึกชีตไม่ได้ = ok False", ev_has("บันทึกชีตไม่ได้", ok=False, target="fail"))
ok("log: กลับมาบันทึกได้ = ok True", ev.filter(ok=True, target="recovered").exists())
ok("log: ไม่มี LINE user id ในข้อความ", not [e for e in ev.all() if re.search(r"U[0-9a-f]{32}", str(e.detail))])

# ปิดแจ้งเตือน LINE = ยังจด log
LS.set_config(alert=False)
n_line, n_ev = len(FAKE.line), ev.count()
LS.alert([("t:1", "ทดสอบจด log ตอนปิดแจ้งเตือน", 0)])
ok("ปิดแจ้งเตือน LINE = ไม่ส่ง แต่ยังจด log", len(FAKE.line) == n_line and ev.count() == n_ev + 1
   and ev_has("ตอนปิดแจ้งเตือน"), (len(FAKE.line) - n_line, ev.count() - n_ev))
LS.set_config(alert=True)

# failing=None (ตัวเฝ้าระบบ/สำเนาชีตเรียก) ห้ามแตะสถานะ "บันทึกไม่ได้"
LS._set_kv(LS.KV_ALERT, dict(LS._kv(LS.KV_ALERT), failing="boom"))
n_line = len(FAKE.line)
LS.alert([("t:2", "เรื่องอื่น", 0)])
ok("alert(items) ไม่ล้างสถานะบันทึกไม่ได้ · ไม่แจ้งว่าหายแล้ว", LS._kv(LS.KV_ALERT).get("failing") == "boom"
   and not any("กลับมาบันทึก" in t for t in line_texts(n_line)), line_texts(n_line))
LS.alert([], failing="")
ok("ผลบันทึกรอบใหม่สำเร็จ (failing='') = แจ้งหายแล้ว", not LS._kv(LS.KV_ALERT).get("failing")
   and any("กลับมาบันทึก" in t for t in line_texts(n_line)), line_texts(n_line))

# พังกะทันหันในงานเบื้องหลัง = จด log + แจ้ง (เดิม except: pass เงียบ)
n_line = len(FAKE.line)
with mock.patch.object(LS, "process_pending", side_effect=RuntimeError("db gone")):
    r = LS.safe_process("cron")
ok("safe_process: ล้ม → คืน error ไม่โยนต่อ", "db gone" in r.get("error", ""), r)
ok("safe_process: แจ้ง LINE ว่าล้มกะทันหัน (บอกที่มา)", any("ล้มกะทันหัน" in t and "cron" in t and "db gone" in t
                                                           for t in line_texts(n_line)), line_texts(n_line))
ok("safe_process: จด log ok False", ev.filter(ok=False, target__startswith="crash:").exists())
n_line = len(FAKE.line)
with mock.patch.object(LS, "process_pending", side_effect=RuntimeError("db gone")):
    LS.safe_process("cron")
ok("ล้มซ้ำภายในชั่วโมง = ไม่แจ้งซ้ำ", len(FAKE.line) == n_line, line_texts(n_line))


class _SyncThread:
    def __init__(self, target=None, **k):
        self.t = target

    def start(self):
        self.t()


n_line = len(FAKE.line)
with mock.patch.object(LS, "process_pending", side_effect=ValueError("kick พัง")), \
        mock.patch.object(LS.threading, "Thread", _SyncThread):
    LS.kick()
ok("kick (ระบบส่งใบ) ล้ม = แจ้ง ไม่เงียบ", any("kick พัง" in t for t in line_texts(n_line)), line_texts(n_line))
n_line = len(FAKE.line)
with mock.patch.object(LS, "process_pending", side_effect=ValueError("webhook พัง")):
    LS.maybe_process({"events": [{"source": {"groupId": ROOM}}]})
ok("maybe_process (ข้อความ LINE เข้า) ล้ม = แจ้ง ไม่เงียบ", any("webhook พัง" in t for t in line_texts(n_line)),
   line_texts(n_line))
VSRC = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard", "views.py"),
            encoding="utf-8").read()
ok("cron ใช้ safe_process (ไม่กลืน error เงียบ)", '_ls_safe("cron")' in VSRC and "_ls_pending()" not in VSRC)

# สำเนาชีตลง Postgres ล้ม = แจ้งด้วย
n_line = len(FAKE.line)
with mock.patch.object(SM, "_auth", side_effect=RuntimeError("ไม่มีสิทธิ์อ่านชีต")):
    r = SM.run()
ok("สำเนาชีตล้ม → แจ้ง LINE + log", r.get("error") and any("สำเนาชีต" in t for t in line_texts(n_line))
   and ev.filter(target__startswith="mirror:").exists(), (r, line_texts(n_line)))

# ตัวเฝ้าระบบ
LS._set_kv(LS.KV_ALERT, dict(LS._kv(LS.KV_ALERT), failing="", sent={}))
_setkv("cron_tick", {"ok": True})
now = djtz.now()
keys = lambda items: [k for k, _t, _e in items]  # noqa: E731
ok("ตัวเฝ้าระบบ: cron เพิ่งทำงาน = ไม่แจ้ง", "wd:cron" not in keys(LS.watchdog_check(now)))
ok("ตัวเฝ้าระบบ: cron หยุดเกิน 10 นาที = แจ้ง", "wd:cron" in keys(LS.watchdog_check(now + timedelta(minutes=30))))
day = djtz.make_aware(datetime(2026, 11, 10, 12, 0))               # หลังข้อความทดสอบทั้งหมด (ล่าสุด 1 พ.ย.)
ok("ตัวเฝ้าระบบ: ช่วงทำงานไม่มีข้อความจากห้องจ่ายเบอร์เกิน 90 นาที = แจ้ง",
   "wd:quiet" in keys(LS.watchdog_check(day.replace(hour=15, minute=0))))
ok("ตัวเฝ้าระบบ: 10:30 เช้า (ข้อความล่าสุดเมื่อคืน) = ยังไม่แจ้ง (นับจาก 10:00 ไม่ใช่จากเมื่อคืน)",
   "wd:quiet" not in keys(LS.watchdog_check(day.replace(hour=10, minute=30))))
ok("ตัวเฝ้าระบบ: นอกเวลาทำงาน = ไม่แจ้งเรื่องเงียบ",
   "wd:quiet" not in keys(LS.watchdog_check(day.replace(hour=22, minute=0))))
# ข้อความค้างเกิน 15 นาที (งานปกติไม่ได้ทำงาน) → ลงให้เอง + แจ้ง
_setkv("cron_tick", {"ok": True})
LS.process_pending()
old = djtz.now() - timedelta(minutes=20)
msg(SLIP.replace("TLD10-9221", "TLD10-9501").replace("089-123-4567", "089-777-0001"), U("c"), at=old,
    extra={"mention": [U("a")]})
ok("มีข้อความค้างเกิน 15 นาที", LS.pending_count(LS.STUCK_MIN) == 1, LS.pending_count(LS.STUCK_MIN))
items = LS.watchdog_check()
ok("ตัวเฝ้าระบบลงให้เอง → ไม่ค้าง + แจ้งว่าลงให้แล้ว", LS.pending_count() == 0
   and any(k.startswith("wd:healed") for k in keys(items)), items)
msg(SLIP.replace("TLD10-9221", "TLD10-9502").replace("089-123-4567", "089-777-0002"), U("c"), at=old,
    extra={"mention": [U("a")]})
FAKE.fail = 1
items = LS.watchdog_check()
ok("ลงเองแล้วยังไม่ได้ = แจ้งว่ายังค้าง + เหตุผล", "wd:stuck" in keys(items)
   and any("ยังไม่ได้" in t for _k, t, _e in items), items)
LS.process_pending()                                              # รอบถัดไปลงได้
ok("รอบถัดไปลงได้", LS.pending_count() == 0)
LS.set_config(enabled=False)
ok("ปิดระบบลงชีต = ตัวเฝ้าไม่ตรวจ", LS.watchdog_check(now + timedelta(minutes=60)) == [])
LS.set_config(enabled=True)
ok("ตัวเฝ้าไม่เริ่มเองตอนรันเทสต์/manage.py (เฉพาะ gunicorn)", LS._WD["pid"] == 0, LS._WD)
ok("ผู้นำตัวเฝ้า (SQLite) = ทำได้", LS._wd_leader() is True)

# ดู log ย้อนหลัง
rows = LS.recent_log(days=3)
ok("recent_log: มีเรื่องที่แจ้ง + ผลส่ง LINE", any("บันทึกชีตไม่ได้" in r_["text"] for r_ in rows)
   and any(r_["kind"] == "line_send" for r_ in rows), rows[:5])
ok("recent_log: ไม่มี LINE user id", not [r_ for r_ in rows if re.search(r"U[0-9a-f]{32}", r_["text"])])
import tempfile  # noqa: E402

from django.core.management import call_command  # noqa: E402

_tmp = os.path.join(tempfile.mkdtemp(), "log.txt")
call_command("leadsheet", "--log", "--days", "3", "--out", _tmp)
_out = open(_tmp, encoding="utf-8").read()
ok("manage.py leadsheet --log", "log ระบบลงชีตจ่ายเบอร์" in _out and "ล้มกะทันหัน" in _out, _out[:400])
call_command("leadsheet", "--out", _tmp)
_out = open(_tmp, encoding="utf-8").read()
ok("manage.py leadsheet (สถานะ) บอกเรื่องตัวเฝ้าระบบ", "ตัวเฝ้าระบบ" in _out, _out[-300:])

for p in P:
    p.stop()
_runner.teardown_databases(_old)
print()
print("ผ่านทั้งหมด" if not FAILS else "ไม่ผ่าน %d ข้อ: %s" % (len(FAILS), ", ".join(FAILS)))
sys.exit(1 if FAILS else 0)
