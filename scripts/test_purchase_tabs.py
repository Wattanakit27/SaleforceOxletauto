"""เทสต์ เตรียมแท็บเดือนใหม่ของชีตจัดซื้อ (dashboard/services/purchase_tabs.py)

    python scripts/test_purchase_tabs.py

ปลอมที่ขอบระบบ (requests + credentials) — ฟังก์ชันของเราได้รันจริงทุกบรรทัด
สิ่งที่ต้องไม่เกิดเด็ดขาด: คำสั่งเขียนใดๆ อ้างถึงแท็บต้นฉบับ
"""
import os
import sys
import urllib.parse
from datetime import datetime
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
os.environ["DB_HOST"] = ""
os.environ.setdefault("DEBUG", "True")
import django  # noqa: E402

django.setup()

from dashboard.services import purchase_followup as PF  # noqa: E402
from dashboard.services import purchase_tabs as PT  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + ((" — " + str(extra)) if (extra and not cond) else ""))
    if not cond:
        FAILS.append(name)


# ── 1) ชื่อแท็บ / ข้ามปี ──────────────────────────────────────────
check("ชื่อแท็บ ต.ค.69", PF.tab_name(2026, 10) == "ขายรถจบออนไลน์ ตุลาคม69")
check("ชื่อแท็บ ม.ค.70", PF.tab_name(2027, 1) == "ขายรถจบออนไลน์ มกราคม70")
check("เดือนก่อน ม.ค. = ธ.ค. ปีก่อน", PF.prev_month(2027, 1) == (2026, 12))
check("ม.ค. อ่าน ธ.ค. ปีก่อนด้วย (บั๊กเดิม: ข้ามทิ้ง)",
      PF._months_to_read(datetime(2027, 1, 5)) == ["ขายรถจบออนไลน์ มกราคม70", "ขายรถจบออนไลน์ ธันวาคม69"],
      PF._months_to_read(datetime(2027, 1, 5)))
check("ต.ค. อ่าน ต.ค.+ก.ย.",
      PF._months_to_read(datetime(2026, 10, 8)) == ["ขายรถจบออนไลน์ ตุลาคม69", "ขายรถจบออนไลน์ กันยายน69"])

# ── 2) แก้ชื่อเดือนแถว 1 ─────────────────────────────────────────
check("retitle ตุลาคม69→พฤศจิกายน69", PT.retitle("ตุลาคม69", (2026, 10), (2026, 11)) == "พฤศจิกายน69")
check("retitle บล็อกรับซื้อรถ", PT.retitle("รับซื้อรถ ตุลาคม69", (2026, 10), (2026, 11)) == "รับซื้อรถ พฤศจิกายน69")
check("retitle แบบ ค.ศ. 'กันยายน 2026'", PT.retitle("กันยายน 2026", (2026, 9), (2026, 10)) == "ตุลาคม 2026")
check("retitle ข้ามปี ธ.ค.69→ม.ค.70", PT.retitle("ธันวาคม69", (2026, 12), (2027, 1)) == "มกราคม70")
check("retitle ข้ามปี ค.ศ.", PT.retitle("ธันวาคม 2026", (2026, 12), (2027, 1)) == "มกราคม 2027")
check("retitle ไม่แตะสูตร", PT.retitle("=A2&\"ตุลาคม\"", (2026, 10), (2026, 11)) == "=A2&\"ตุลาคม\"")
check("retitle ไม่แตะข้อความอื่น", PT.retitle("จัดซื้อรับเข้า ออนไลน์และออฟไลน์", (2026, 10), (2026, 11))
      == "จัดซื้อรับเข้า ออนไลน์และออฟไลน์")
check("col_ranges รวมช่วงติดกัน", PT.col_ranges([0, 1, 2, 5, 6, 9]) == [(0, 2), (5, 6), (9, 9)])


# ── 3) ทางเขียนชีตจริง (ปลอม requests) ───────────────────────────
SRC = "ขายรถจบออนไลน์ ตุลาคม69"
DST = "ขายรถจบออนไลน์ พฤศจิกายน69"


class Resp:
    def __init__(self, data, status=200):
        self._d, self.status_code, self.text = data, status, str(data)

    def json(self):
        return self._d


class FakeSheets:
    """จำลอง Sheets API พอให้ ensure_tab เดินครบ · จดทุกคำขอไว้ตรวจ"""

    def __init__(self, tabs, formula_rows, row1, leftover_after_clear=False, clear_status=200):
        self.tabs = dict(tabs)
        self.formula_rows = formula_rows
        self.row1 = row1
        self.leftover = leftover_after_clear
        self.clear_status = clear_status
        self.calls = []          # (method, url-decoded, json)

    def _rng(self, url):
        return urllib.parse.unquote(url.split("/values/", 1)[1]) if "/values/" in url else ""

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(("GET", urllib.parse.unquote(url), params))
        if "/values/" not in url:
            return Resp({"sheets": [{"properties": p} for p in self.tabs.values()]})
        rng = self._rng(url)
        if rng.endswith("1") and "!A1:" in rng:
            return Resp({"values": [self.row1]})
        if (params or {}).get("valueRenderOption") == "FORMULA":
            return Resp({"values": self.formula_rows})
        # ตรวจคอลัมน์ C หลังล้าง
        return Resp({"values": [["OC-1"]] if self.leftover else []})

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append(("POST", urllib.parse.unquote(url), json))
        if url.endswith(":batchUpdate") and "/values" not in url:
            req = json["requests"][0]
            if "duplicateSheet" in req:
                name = req["duplicateSheet"]["newSheetName"]
                self.tabs[name] = {"sheetId": 999, "title": name, "index": 20}
                return Resp({"replies": [{"duplicateSheet": {"properties": {"sheetId": 999}}}]})
            if "deleteSheet" in req:
                self.tabs = {k: v for k, v in self.tabs.items() if v["sheetId"] != req["deleteSheet"]["sheetId"]}
                return Resp({"replies": [{}]})
        if url.endswith("values:batchClear"):
            return Resp({}, status=self.clear_status)
        if url.endswith("values:batchUpdate"):
            return Resp({})
        return Resp({"error": "unexpected"}, status=400)

    def put(self, url, params=None, json=None, headers=None, timeout=None):
        self.calls.append(("PUT", urllib.parse.unquote(url), json))
        return Resp({})

    def writes(self):
        return [c for c in self.calls if c[0] != "GET"]


class Creds:
    token = "x"

    def refresh(self, _):
        pass


def run(fake, year=2026, month=11, apply=True):
    with mock.patch("dashboard.services.google_sheets._get_credentials", return_value=Creds()), \
            mock.patch.object(PT.requests, "get", fake.get), \
            mock.patch.object(PT.requests, "post", fake.post), \
            mock.patch.object(PT.requests, "put", fake.put):
        return PT.ensure_tab(year, month, apply=apply)


TABS = {SRC: {"sheetId": 726090496, "title": SRC, "index": 19},
        "TestBot": {"sheetId": 1036416854, "title": "TestBot", "index": 20}}
# แถวข้อมูล (FORMULA): B มีสูตรเซลล์เดียวท่ามกลางตัวเลข (ต้องยังล้าง) · F เป็นสูตรทุกเซลล์ (ต้องเก็บ)
ROWS = []
for i in range(5):
    r = [""] * 48
    r[0], r[1], r[2], r[5] = "1/10/2026", ("=ROW()-2" if i == 0 else str(i + 1)), "OC-%d" % i, "=C%d" % (i + 3)
    r[35] = "=COUNTIF(I:I,AI3)"          # AJ สรุป — ไม่อยู่ในชุดล้างอยู่แล้ว
    ROWS.append(r)
ROW1 = ["ตุลาคม69"] + [""] * 22 + ["รับซื้อรถ ตุลาคม69"] + [""] * 17 + ["จัดซื้อรับเข้า ออนไลน์และออฟไลน์"]

# 3.1 ดูเฉยๆ = ไม่มีคำขอเขียนเลย
f = FakeSheets(TABS, ROWS, ROW1)
r = run(f, apply=False)
check("ดูแผน: ไม่มีคำขอเขียนเลย", not f.writes(), f.writes())
check("ดูแผน: ต้นแบบ = ตุลาคม69", r.get("source") == SRC, r)

# 3.2 สร้างจริง
f = FakeSheets(TABS, ROWS, ROW1)
r = run(f)
w = f.writes()
check("สร้างสำเร็จ", r.get("ok") is True, r)
dup = [c for c in w if c[2] and "requests" in c[2] and "duplicateSheet" in c[2]["requests"][0]]
check("ทำสำเนาจาก sheetId ต้นแบบ", dup and dup[0][2]["requests"][0]["duplicateSheet"]["sourceSheetId"] == 726090496)
check("แท็บใหม่วางต่อจากต้นแบบ", dup and dup[0][2]["requests"][0]["duplicateSheet"]["insertSheetIndex"] == 20)
clr = [c for c in w if c[1].endswith("values:batchClear")]
rngs = clr[0][2]["ranges"] if clr else []
check("ล้างเฉพาะในแท็บใหม่", rngs and all(x.startswith("'%s'!" % DST) for x in rngs), rngs)
check("คอลัมน์สูตรล้วน (F) ไม่ถูกล้าง", "'%s'!G3:W3000" % DST in rngs and "'%s'!A3:E3000" % DST in rngs, rngs)
check("B มีสูตรเซลล์เดียว = ยังล้าง (ไม่งั้นข้อมูลเก่าค้าง)", any(x.startswith("'%s'!A3:" % DST) for x in rngs), rngs)
check("ไม่ล้าง X / AP (เลขคันที่) / AI–AM (สูตร)",
      not any(("!X3" in x) or ("!AP3" in x) or ("!AI3" in x) for x in rngs), rngs)
t1 = [c for c in w if c[1].endswith("values:batchUpdate")]
data = t1[0][2]["data"] if t1 else []
check("แถว 1: แก้เฉพาะเซลล์ที่เปลี่ยน + RAW",
      t1 and t1[0][2]["valueInputOption"] == "RAW"
      and sorted(d["range"] for d in data) == sorted(["'%s'!A1" % DST, "'%s'!X1" % DST]), data)
check("แถว 1: ชื่อเดือนใหม่", sorted(d["values"][0][0] for d in data) == ["พฤศจิกายน69", "รับซื้อรถ พฤศจิกายน69"], data)
check("★ ไม่มีคำขอเขียนใดอ้างแท็บต้นฉบับ", not any(SRC in str(c[1]) + str(c[2]) for c in w
                                                  if "duplicateSheet" not in str(c[2])), w)

# 3.3 ล้างแล้วยังเหลือข้อมูล = ลบแท็บใหม่ทิ้ง
f = FakeSheets(TABS, ROWS, ROW1, leftover_after_clear=True)
r = run(f)
dele = [c for c in f.writes() if c[2] and "requests" in c[2] and "deleteSheet" in c[2]["requests"][0]]
check("ล้างไม่หมด → ลบแท็บใหม่ (sheetId ใหม่เท่านั้น)",
      dele and dele[0][2]["requests"][0]["deleteSheet"]["sheetId"] == 999 and r.get("rolledBack") is True, r)
check("ล้างไม่หมด → รายงาน error", bool(r.get("error")) and not r.get("ok"), r)
check("ล้างไม่หมด → แท็บต้นแบบยังอยู่", SRC in f.tabs and DST not in f.tabs, list(f.tabs))

# 3.4 API ล้างล้ม = ลบแท็บใหม่เหมือนกัน
f = FakeSheets(TABS, ROWS, ROW1, clear_status=500)
r = run(f)
check("ล้างล้ม (500) → ลบแท็บใหม่", r.get("rolledBack") is True and DST not in f.tabs, r)

# 3.5 มีแท็บอยู่แล้ว = ไม่ทำอะไร
f = FakeSheets(dict(TABS, **{DST: {"sheetId": 5, "title": DST, "index": 21}}), ROWS, ROW1)
r = run(f)
check("มีแท็บแล้ว → ไม่เขียนอะไรเลย", r.get("exists") is True and not f.writes(), f.writes())

# 3.6 ไม่มีต้นแบบย้อนหลัง 3 เดือน
f = FakeSheets({"TestBot": TABS["TestBot"]}, ROWS, ROW1)
r = run(f)
check("ไม่มีต้นแบบ → error ไม่เขียน", bool(r.get("error")) and not f.writes(), r)

# 3.7 ข้ามปี: ม.ค.70 ใช้ ธ.ค.69 เป็นต้นแบบ
DEC = "ขายรถจบออนไลน์ ธันวาคม69"
f = FakeSheets({DEC: {"sheetId": 77, "title": DEC, "index": 22}}, ROWS, ["ธันวาคม69"])
r = run(f, 2027, 1)
check("ข้ามปี: สร้าง มกราคม70 จาก ธันวาคม69", r.get("target") == "ขายรถจบออนไลน์ มกราคม70"
      and r.get("source") == DEC and r.get("ok"), r)

# ── 4) cron: วันที่ 25 = เตรียมเดือนหน้า · วันอื่น = เช็คแค่เดือนนี้ ─────────
seen = []


def fake_ensure(y, m, apply=False, api=None):
    seen.append((y, m, apply))
    return {"target": PF.tab_name(y, m), "exists": True, "action": "มีอยู่แล้ว"}


store = {}
with mock.patch.object(PT, "_Api", lambda: object()), \
        mock.patch.object(PT, "ensure_tab", fake_ensure), \
        mock.patch("dashboard.services.cache_store.get_kv", lambda k: store.get(k)), \
        mock.patch("dashboard.services.cache_store.set_kv", lambda k, v: store.__setitem__(k, {"data": v})):
    PT.maybe_prepare(datetime(2026, 10, 8, 10, 7))
    check("วันที่ 8: เช็คแค่เดือนนี้", seen == [(2026, 10, True)], seen)
    seen.clear()
    store.clear()
    PT.maybe_prepare(datetime(2026, 12, 26, 10, 7))
    check("26 ธ.ค.: เช็ค ธ.ค. + ม.ค. ปีหน้า", seen == [(2026, 12, True), (2027, 1, True)], seen)
    seen.clear()
    out = PT.maybe_prepare(datetime(2026, 12, 26, 11, 7))
    check("ทำแล้ววันนี้ → ไม่ทำซ้ำ", out == "" and not seen, (out, seen))

print("\n%d FAIL" % len(FAILS) if FAILS else "\nALL PASS")
sys.exit(1 if FAILS else 0)
