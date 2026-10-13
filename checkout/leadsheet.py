# -*- coding: utf-8 -*-
"""ห้องจ่ายเบอร์ → "ชีทจ่ายเบอร์ ปี69" (แท็บรายเดือน) + "รายงานแบน" — **ย้ายมาจาก n8n** (13 ต.ค.69)

เจ้าของสั่ง *"ทำไมมันกรอกชีทมั่ว อยากให้เอา n8n อันนี้ลง saleforce"* แล้วเคาะกติกา:
*"ถ้าจ่ายจาก Salesforce ก็ลง sheet ใน Salesforce เลย ไม่ต้องทำระบบซ้ำ · ถ้าจ่ายใน Line ก็ลงเหมือนกัน
แบ่งเป็นสองฝั่ง แต่โดยรวมแล้วผลลัพธ์ต้องได้แค่หนึ่ง"*

ทางเดียวสำหรับทั้ง 2 ฝั่ง = **คลังแชทกลุ่ม (`GroupChat`) ของห้องจ่ายเบอร์**
  · ใบที่แอดมินโพสต์เองใน LINE → webhook เก็บเป็นแถวขาเข้า (IN)
  · ใบที่ระบบส่ง (ปุ่มจ่ายเบอร์ใน Connect/ห้องพัก Lead · จ่ายใหม่ · ไม้ 2) → `slippost._store` เก็บเป็นแถวขาออก
    (`extra.source = "connect"`) เพราะ LINE ไม่ส่งข้อความของบอทเองกลับมา
  → ตัวชี้ `GroupChat.id` ตัวเดียวไล่ตามลำดับ · **Code เดิมมีแถวในชีตแล้ว = ไม่เพิ่มแถว** (เปลี่ยนเซลล์ถ้าจ่ายใหม่)

งาน 3 อย่าง (ตรงกับ workflow n8n "LINE → Sheet" เดิม):
  1. **ใบจ่ายลีด** → เพิ่มแถวในแท็บเดือน (ว/ด/ป · เบอร์ · เวลา · Code · เซลล์ · ทีมไลฟ์ · Admin · ช่องทาง · สาขา ·
     type · ADS · รถลูกค้าถาม · CAR/สูตร · PROFILE)
  2. **รายงานผล "เลข + ผล"** ("9075 รอตอบ") → จำนวนอัพเดท +1 · อัพเดทล่าสุด · ที่ติดต่อ (ถ้ายังว่าง) · แจ้งหลักฐาน = ส่งแล้ว
     **ไม่แตะ ว/ด/ป เด็ดขาด** — n8n เขียนวันที่รายงานทับช่องนี้ทุกครั้ง (ต้นเหตุ "วันที่ 13 โผล่กลางวันที่ 12")
  3. **ข้อความแบน** (แท็กคน + คำว่าแบน/ปรับ/รีเจ) → ต่อท้ายแท็บ "รายงานแบน" (คะแนนเซลล์ด้าน "โดนแบน" อ่านตรงนี้)

ต่างจาก n8n โดยตั้งใจ:
  · ว/ด/ป + เวลา = เวลาที่ใบถึงกลุ่ม (n8n เดาจากวันที่ตัวแรกในข้อความ — ใบที่มีวันที่ในหมายเหตุได้วันผิด)
  · โพสต์ใบเลขเดิมซ้ำ = ไม่เพิ่มแถว (n8n เพิ่มซ้ำ) · จ่ายใหม่ = เปลี่ยนช่องเซลล์ของแถวเดิม
  · ช่องทาง/ไลฟ์ ไม่ใช้ fuzzy (Levenshtein) — ไม่ตรงกติกาไหนเลย = เขียนคำเดิม ให้คนเห็นว่าไม่อยู่ในตัวเลือก
  · อ่านเฉพาะห้องจ่ายเบอร์ (n8n ส่งทุกกลุ่มที่ "ยังไม่ลงทะเบียน" เข้ามาด้วย)
  · "ขอปลดแบน" ไม่นับเป็นการแบน (n8n นับ) · ปี พ.ศ. 2 หลักในข้อความแบนแปลงถูก (n8n ได้ปี 1969)
  · ไม่เขียน LINE user id ลงชีต (n8n เขียน userId แทนชื่อตอนหาชื่อไม่เจอ)

สวิตช์ KV `leadsheet_config.enabled` — **ปิดโดยปริยาย** · เปิดแล้วต้องปิด workflow n8n วันเดียวกัน (ไม่งั้นเขียน 2 ที่)
ตัวชี้ครั้งแรก = ข้อความล่าสุดตอนเปิด (ไม่ไล่ย้อน) · `--since` ไล่ย้อนได้ (ใบซ้ำกันด้วย Code · แต่รายงานจะถูกนับซ้ำ
ถ้า n8n นับไปแล้ว — ใส่ --since เป็นเวลาที่ปิด n8n)
"""
from __future__ import annotations

import logging
import re
import threading
import urllib.parse
from datetime import date, datetime, timedelta

import requests
from django.utils import timezone

log = logging.getLogger(__name__)

KV_CONFIG = "leadsheet_config"     # {"enabled": bool, "ban": bool}
KV_STATE = "leadsheet_state"       # {"last_id": int, "at": iso}
KV_LAST = "leadsheet_last"         # ผลรอบล่าสุด (หน้าสถานะระบบ + คำสั่ง manage.py leadsheet อ่าน)
WHAT = "ชีตจ่ายเบอร์ (แทน n8n)"     # ชื่องานใน dash_event_log
_LOCK_KEY = 7_406_064              # Postgres advisory lock (leadflow ใช้ 7_406_062 · Connect 7_406_063)
MAX_ROW = 6000
_ROW_COLS = 5                      # หาแถวสุดท้ายจาก ว/ด/ป · เบอร์ · เวลา · Code · เซลล์ (คอลัมน์อื่นคนกรอกทีหลัง)


# ════════════════════════════════════════════════════════════════════
# ค่าตั้ง / KV
# ════════════════════════════════════════════════════════════════════
def _kv(key) -> dict:
    from dashboard.services.cache_store import get_kv
    try:
        raw = get_kv(key) or {}
        d = raw.get("data", raw) if isinstance(raw, dict) else {}
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _set_kv(key, val):
    from dashboard.services.cache_store import set_kv
    try:
        set_kv(key, val)
    except Exception:
        pass


def get_config() -> dict:
    c = {"enabled": False, "ban": True}
    d = _kv(KV_CONFIG)
    c.update({k: bool(d[k]) for k in ("enabled", "ban") if k in d})
    return c


def set_config(**kw) -> dict:
    c = get_config()
    c.update({k: bool(v) for k, v in kw.items() if v is not None})
    _set_kv(KV_CONFIG, c)
    return get_config()


# ════════════════════════════════════════════════════════════════════
# Google Sheets (ขอบระบบ = requests — เทสต์ปลอมที่ requests ไม่ใช่ที่คลาสนี้)
# ════════════════════════════════════════════════════════════════════
class _Api:
    def __init__(self, sid):
        from google.auth.transport.requests import Request as AuthRequest

        from dashboard.services.google_sheets import SHEETS_API, _get_credentials
        creds = _get_credentials()
        creds.refresh(AuthRequest())
        self.h = {"Authorization": "Bearer %s" % creds.token}
        self.base = "%s/%s" % (SHEETS_API, sid)

    @staticmethod
    def _ok(r, what):
        if r.status_code != 200:
            raise SheetError("%s: HTTP %s %s" % (what, r.status_code, r.text[:200]), r.status_code)
        return r.json()

    def props(self) -> dict:
        """{ชื่อแท็บ: {"id": sheetId, "rows": จำนวนแถวของตาราง}}"""
        j = self._ok(requests.get(self.base, params={"fields": "sheets.properties(sheetId,title,gridProperties)"},
                                  headers=self.h, timeout=30), "อ่านรายชื่อแท็บ")
        return {s["properties"]["title"]: {"id": s["properties"].get("sheetId"),
                                           "rows": (s["properties"].get("gridProperties") or {}).get("rowCount") or 0}
                for s in j.get("sheets", [])}

    def expand(self, sheet_id, add: int):
        """เพิ่มแถวท้ายตาราง — เขียนเลยขอบตาราง Sheets ตอบ 400 (values:append ของ n8n ขยายให้เอง เราต้องทำเอง)"""
        return self._ok(requests.post(self.base + ":batchUpdate", json={"requests": [{"appendDimension": {
            "sheetId": sheet_id, "dimension": "ROWS", "length": int(add)}}]}, headers=self.h, timeout=60),
            "เพิ่มแถวท้ายตาราง")

    def get(self, rng, render="FORMATTED_VALUE") -> list:
        url = "%s/values/%s" % (self.base, urllib.parse.quote(rng))
        return self._ok(requests.get(url, params={"valueRenderOption": render}, headers=self.h, timeout=60),
                        "อ่าน " + rng).get("values", [])

    def batch(self, reqs: list, what: str):
        return self._ok(requests.post(self.base + ":batchUpdate", json={"requests": reqs}, headers=self.h,
                                      timeout=60), what)

    def write(self, cells: dict, what: str):
        """เขียนเฉพาะเซลล์ที่ระบุ ({"'แท็บ'!A12": ค่า}) — ไม่แตะเซลล์อื่นในแถว (ไม่ทับสูตร/dropdown ของคนอื่น)"""
        data = [{"range": rng, "values": [[val]]} for rng, val in cells.items()]
        return self._ok(requests.post(self.base + "/values:batchUpdate",
                                      json={"valueInputOption": "USER_ENTERED", "data": data},
                                      headers=self.h, timeout=60), what)


class SheetError(RuntimeError):
    def __init__(self, msg, code=0):
        super().__init__(msg)
        self.code = code


def _col(i: int) -> str:
    s, i = "", i + 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _q(tab) -> str:
    return "'%s'" % tab


def tab_name(d) -> str:
    """แท็บรายเดือนของชีตลีด — "ตุลาคม 69" (ปี พ.ศ. 2 หลัก · เว้นวรรค · ต่างจากชีตจัดซื้อที่ไม่เว้น)"""
    from dashboard.services.google_sheets import _THAI_MONTHS
    return "%s %02d" % (_THAI_MONTHS[d.month - 1], (d.year + 543) % 100)


def _prev(d, n=1):
    y, m = d.year, d.month - n
    while m < 1:
        y, m = y - 1, m + 12
    return date(y, m, 1)


def _code_key(s) -> str:
    return re.sub(r"\s+", "", str(s or "")).upper()


_RUN = re.compile(r"-(\d{3,6})(?:/(\d{1,2}))?$")
_CODE_MONTH = re.compile(r"^[A-Z]*?(\d{1,2})-")


class LeadTab:
    """แท็บรายเดือน 1 แท็บ + ดัชนี Code → แถว · อ่านครั้งเดียวต่อรอบแล้วแก้ในหน่วยความจำตามที่เขียนไป"""

    def __init__(self, api, title):
        from dashboard.services.google_sheets import LEADS_COL, _resolve_lead_colmap
        self.api, self.title = api, title
        vals = api.get("%s!A1:AH%d" % (_q(title), MAX_ROW))
        self.header = vals[0] if vals else []
        self.rows = vals[1:] if len(vals) > 1 else []            # แถวชีต = index + 2
        self.cm = _resolve_lead_colmap(self.header, self.rows[:20]) if self.header else {}
        self.L = LEADS_COL
        if self.cm.get(LEADS_COL.lead_code) is None:
            raise SheetError("แท็บ %s ไม่มีหัวคอลัมน์ Code" % title)
        self.last = 1
        for i, r in enumerate(self.rows):
            if any(str(v).strip() for v in r[:_ROW_COLS]):
                self.last = i + 2

    def src(self, field):
        return self.cm.get(field)

    def val(self, row: list, field) -> str:
        i = self.cm.get(field)
        return str(row[i]).strip() if i is not None and i < len(row) else ""

    def find(self, code) -> list:
        k = _code_key(code)
        ci = self.cm[self.L.lead_code]
        return [(i + 2, r) for i, r in enumerate(self.rows) if ci < len(r) and _code_key(r[ci]) == k]

    def by_run(self, run: str, slash: int | None = None, month: int | None = None) -> list:
        ci = self.cm[self.L.lead_code]
        out = []
        for i, r in enumerate(self.rows):
            k = _code_key(r[ci]) if ci < len(r) else ""
            m = _RUN.search(k)
            if not m or m.group(1) != run:
                continue
            if slash is not None and int(m.group(2) or 0) != slash:
                continue
            if month:
                mm = _CODE_MONTH.match(k)
                if mm and int(mm.group(1)) != month:
                    continue
            out.append((i + 2, r))
        return out

    def cells(self, n: int, values: dict) -> dict:
        """{ช่อง canonical: ค่า} → {"'แท็บ'!X<n>": ค่า} เฉพาะช่องที่แท็บนี้มีหัวคอลัมน์"""
        out = {}
        for f, v in values.items():
            i = self.cm.get(f)
            if i is not None:
                out["%s!%s%d" % (_q(self.title), _col(i), n)] = v
        return out

    def remember(self, n: int, values: dict):
        """จำค่าที่เพิ่งเขียน (รอบเดียวกันอ่านเจอโดยไม่ต้องอ่านชีตใหม่)"""
        while len(self.rows) < n - 1:
            self.rows.append([])
        row = self.rows[n - 2]
        for f, v in values.items():
            i = self.cm.get(f)
            if i is None:
                continue
            while len(row) <= i:
                row.append("")
            row[i] = str(v).lstrip("'")
        self.last = max(self.last, n)


# ════════════════════════════════════════════════════════════════════
# ใบจ่ายลีด → ช่องของแถว (พอร์ตจาก n8n "Build Sheet Row3" v2.3)
# ════════════════════════════════════════════════════════════════════
def _clean(v) -> str:
    return re.sub(r"\s+", " ", str(v or "").replace(" ", " ")).strip()


def _t(v) -> str:
    """ข้อความที่ต้องเป็นข้อความเสมอ — เบอร์ขึ้นต้น 0 / ขึ้นต้น = + - @ (ไม่งั้น Sheets ตัดเลข 0 / ตีเป็นสูตร)"""
    s = str(v or "")
    if s and (s[0] in "=+-@" or re.fullmatch(r"0\d+", s)):
        return "'" + s
    return s


def _dstr(d) -> str:
    return "%d/%d/%d" % (d.day, d.month, d.year)            # ปี ค.ศ. 4 หลัก — กัน Sheets ตีปี 2 หลักผิด (69 → 1969)


def _dtstr(dt) -> str:
    dt = timezone.localtime(dt)
    return "%s %02d:%02d" % (_dstr(dt), dt.hour, dt.minute)


def _pick(field: str, v) -> str:
    """ค่าใน dropdown ของชีต (ชื่อช่องแบบ Connect: channel/live_team/admin_name/lead_type/car_model/call_proof)
    ตรงตัว (ไม่สนช่องว่าง/ตัวพิมพ์) ก่อน · ไม่ตรง = ตัวเลือกเดียวที่ขึ้นต้นเหมือนกัน ("TIKTOK รถเข้าใหม่" →
    "TIKTOK รถเข้าใหม่อ๊อกเล็ตธ์") · หลายตัว/ไม่เจอ = "" (ไม่เดา)"""
    from . import connect as C
    hit = C.dd_pick(field, v)
    if hit or not str(v or "").strip():
        return hit
    k = re.sub(r"\s+", "", str(v)).lower()
    opts = [o for o in C.dd_options(field) if re.sub(r"\s+", "", o).lower().startswith(k)]
    return opts[0] if len(opts) == 1 else ""


# ช่องทาง — คำย่อ/สะกดที่แอดมินพิมพ์ในใบ → ตัวเลือกในชีต (จาก n8n · ผลลัพธ์ผ่าน dd_pick อีกชั้นให้ตรงตัวเลือกจริง)
CHANNEL_ALIASES = {
    "ไลฟ์ช่อง888": "LIVE Tiktok / ช่อง888", "liveช่อง888": "LIVE Tiktok / ช่อง888",
    "ไลฟ์ทิกต๊อกช่อง888": "LIVE Tiktok / ช่อง888", "live ช่อง888": "LIVE Tiktok / ช่อง888",
    "tiktokช่อง888": "TIKTOK ช่อง888", "ทิกต๊อกช่อง888": "TIKTOK ช่อง888", "ช่อง888": "TIKTOK ช่อง888",
    "888": "TIKTOK ช่อง888",
    "ไล": "LINE@", "ไลน": "LINE@", "ไลน์": "LINE@", "line": "LINE@", "ลาย": "LINE@", "ล้าย": "LINE@",
    "ไลน์@": "LINE@", "line@": "LINE@",
    "ติ": "Tiktok  ช่องหลัก", "ติก": "Tiktok  ช่องหลัก", "ทิก": "Tiktok  ช่องหลัก", "ทิกต": "Tiktok  ช่องหลัก",
    "ทิกต๊อก": "Tiktok  ช่องหลัก", "tiktok": "Tiktok  ช่องหลัก", "tik": "Tiktok  ช่องหลัก",
    "ติ๊ก": "Tiktok  ช่องหลัก", "ทิกต๊อกช่องหลัก": "Tiktok  ช่องหลัก",
    "เพ": "เพจบ้านเก่า", "เพจ": "เพจบ้านเก่า", "page": "เพจบ้านเก่า", "fb": "เพจบ้านเก่า",
    "เพจบ้านเก่า": "เพจบ้านเก่า", "บ้านเก่า": "เพจบ้านเก่า", "เพจอ่อนนุช": "เพจอ่อนนุช", "อ่อนนุช": "เพจอ่อนนุช",
    "เพจguru": "เพจ Guru", "guru": "เพจ Guru", "กูรู": "เพจ Guru",
    "ไลฟ์ช่องขายบอส": "LIVE Tiktok / ช่องขายบอส", "liveช่องขายบอส": "LIVE Tiktok / ช่องขายบอส",
    "ไลฟ์ขายบอส": "LIVE Tiktok / ช่องขายบอส", "ไลฟ์ทิกต๊อกช่องขายบอส": "LIVE Tiktok / ช่องขายบอส",
    "ไลฟ์ช่องหลัก": "LIVE Tiktok / ช่องหลัก", "liveช่องหลัก": "LIVE Tiktok / ช่องหลัก",
    "ไลฟ์ทิกต๊อกช่องหลัก": "LIVE Tiktok / ช่องหลัก",
    "ไลฟ์guru": "LIVE Tiktok / ช่อง Guru", "liveguru": "LIVE Tiktok / ช่อง Guru",
    "ไลฟ์facebook": "LIVE Facebook", "ไลฟ์fb": "LIVE Facebook", "livefacebook": "LIVE Facebook",
    "livefb": "LIVE Facebook",
    "เบอร์กลาง/เพจ": "เบอร์กลาง / เพจ", "เบอร์กลาง / เพจ": "เบอร์กลาง / เพจ", "เบอร์กลางเพจ": "เบอร์กลาง / เพจ",
    "เบอร์กลาง/tiktok": "เบอร์กลาง / Tiktok", "เบอร์กลาง / tiktok": "เบอร์กลาง / Tiktok",
    "เบอร์กลาง/ทิกต๊อก": "เบอร์กลาง / Tiktok", "เบอร์กลางtiktok": "เบอร์กลาง / Tiktok",
    "tiktokโอ๊ต": "TIKTOK โอ๊ต", "ทิกต๊อกโอ๊ต": "TIKTOK โอ๊ต", "tiktokนวล": "Tiktok นวล",
    "ทิกต๊อกนวล": "Tiktok นวล", "tiktokมัท": "Tiktok มัท", "ทิกต๊อกมัท": "Tiktok มัท",
    "tiktokอุ้ม": "TIKTOK อุ้ม", "ทิกต๊อกอุ้ม": "TIKTOK อุ้ม", "tiktokเฟิร์ส": "TIKTOK เฟิร์ส",
    "ทิกต๊อกเฟิร์ส": "TIKTOK เฟิร์ส", "tiktokหนึ่ง": "TIKTOK หนึ่ง", "ทิกต๊อกหนึ่ง": "TIKTOK หนึ่ง",
    "tiktokguru": "Tiktok Guru", "ทิกต๊อกguru": "Tiktok Guru",
    "เว็บ": "web oxlet", "web": "web oxlet", "เว็บoxlet": "web oxlet",
    "ยู": "Youtube", "youtube": "Youtube", "ยูทูป": "Youtube", "12": "12car", "12car": "12car",
    "line@/tiktok": "Line@ / TIKTOK", "line@ / tiktok": "Line@ / TIKTOK", "ไลน์@/tiktok": "Line@ / TIKTOK",
    "ไลน์@/ทิกต๊อก": "Line@ / TIKTOK", "marketplace": "Market Place", "มาร์เก็ตเพลส": "Market Place",
    "ส่วนตัว": "ส่วนตัวแอดมิน", "แอดมิน": "ส่วนตัวแอดมิน", "broker": "Broker oxlet", "โบรกเกอร์": "Broker oxlet",
    "roddonjai": "Roddonjai", "รดน้ำใจ": "Roddonjai",
    "ช่องบอสเจมส์": "TIKTOK ช่องบอสเจมส์ทะเบียนเทพ", "บอสเจมส์": "TIKTOK ช่องบอสเจมส์ทะเบียนเทพ",
    "ทะเบียนเทพ": "TIKTOK ช่องบอสเจมส์ทะเบียนเทพ",
    "แซน": "Tiktok ช่องแซน", "ช่องแซน": "Tiktok ช่องแซน", "tiktokแซน": "Tiktok ช่องแซน",
    "tiktokช่องแซน": "Tiktok ช่องแซน", "ทิกต๊อกแซน": "Tiktok ช่องแซน", "ทิกต๊อกช่องแซน": "Tiktok ช่องแซน",
    "ติ๊กต๊อกแซน": "Tiktok ช่องแซน", "tt แซน": "Tiktok ช่องแซน",
    "รถเข้าใหม่": "TIKTOK รถเข้าใหม่", "เข้าใหม่": "TIKTOK รถเข้าใหม่", "tiktokรถเข้าใหม่": "TIKTOK รถเข้าใหม่",
    "tiktok รถเข้าใหม่": "TIKTOK รถเข้าใหม่", "ทิกต๊อกรถเข้าใหม่": "TIKTOK รถเข้าใหม่",
    "ช่องรถเข้าใหม่": "TIKTOK รถเข้าใหม่", "tt รถเข้าใหม่": "TIKTOK รถเข้าใหม่",
}


def match_channel(raw) -> str:
    """ช่องทางในใบ → ตัวเลือกในชีต · ว่าง = LINE@ (ตามเดิมของ n8n) · ไม่ตรงกติกาไหน = คำเดิม (ไม่เดาแบบ fuzzy)"""
    from . import connect as C
    inp = _clean(raw).lower()
    if not inp:
        return _pick("channel", "LINE@") or "LINE@"
    hit = _pick("channel", raw)
    if hit:
        return hit
    v = CHANNEL_ALIASES.get(inp)
    if not v:
        live = "ไลฟ์" in inp or "live" in inp
        tt = "tiktok" in inp or "ทิกต๊อก" in inp
        if live:
            v = ("LIVE Facebook" if ("facebook" in inp or "fb" in inp) else
                 "LIVE Tiktok / ช่องขายบอส" if "ขายบอส" in inp else
                 "LIVE Tiktok / ช่อง Guru" if "guru" in inp else
                 "LIVE Tiktok / ช่อง888" if "888" in inp else "LIVE Tiktok / ช่องหลัก")
        elif tt and any(k in inp for k in ("แซน", "เข้าใหม่", "ช่องหลัก", "guru", "888")):
            v = ("Tiktok ช่องแซน" if "แซน" in inp else "TIKTOK รถเข้าใหม่" if "เข้าใหม่" in inp else
                 "Tiktok  ช่องหลัก" if "ช่องหลัก" in inp else "Tiktok Guru" if "guru" in inp else "TIKTOK ช่อง888")
        elif "แซน" in inp:
            v = "Tiktok ช่องแซน"
        elif "เข้าใหม่" in inp:
            v = "TIKTOK รถเข้าใหม่"
        elif "line" in inp or "ไลน" in inp:
            v = "Line@ / TIKTOK" if tt else "LINE@"
        elif "เพจ" in inp or "บ้านเก่า" in inp or "อ่อนนุช" in inp:
            v = ("เพจบ้านเก่า" if "บ้านเก่า" in inp else "เพจอ่อนนุช" if "อ่อนนุช" in inp else
                 "เพจ Guru" if "guru" in inp else "เพจบ้านเก่า")
    if not v:
        opts = C.dd_options("channel")
        part = [o for o in opts if o.lower() in inp or inp in o.lower()]
        v = part[0] if len(part) == 1 else ""
    return (_pick("channel", v) or v) if v else _clean(raw)


LIVE_ALIASES = {"infu": "Live Infu", "อินฟลู": "Live Infu", "อินฟู": "Live Infu",
                "productions": "Live Productions", "production": "Live Productions", "โปรดักชั่น": "Live Productions",
                "โปรดัก": "Live Productions", "pro": "Live Productions", "prod": "Live Productions",
                "โปร": "Live Productions", "sale": "Live Sale", "เซล": "Live Sale", "เซลล์": "Live Sale"}


def match_live(raw) -> str:
    """ช่อง "ไลฟ์" ในใบ → ตัวเลือก "ทีมไลฟ์" ของชีต (คำผิดยอดฮิตจาก n8n) · ไม่ตรง = ว่าง"""
    from . import connect as C
    inp = _clean(raw).lower()
    if not inp:
        return ""
    hit = _pick("live_team", raw)
    if hit:
        return hit
    v = LIVE_ALIASES.get(inp.replace("live", "").replace("ไลฟ์", "").strip()) or ""
    if not v:
        if any(k in inp for k in ("infu", "infl", "info", "อินฟ", "imfu", "nifu", "infy")):
            v = "Live Infu"
        elif any(k in inp for k in ("prod", "ptod", "pordu", "โปร")):
            v = "Live Productions"
        elif any(k in inp for k in ("sale", "sal", "sle", "เซล", "เซ็ล", "เซ้ล", "sael", "slae", "asle", "sake", "dale")):
            v = "Live Sale"
    return (_pick("live_team", v) or v) if v else ""


def lead_type(code: str, channel: str = "") -> str:
    """type จากตัวหน้าเลขลีด (กติกา n8n) — R นำหน้า = รีเจค · TikTokAds = TLD เสมอ"""
    from . import connect as C
    k = _code_key(code)
    letters = (re.match(r"[A-Z]+", k.split("-")[0]) or [""])[0] if k else ""
    t = ""
    if letters.startswith("R"):
        t = ("Hot RB" if letters == "RB" or (letters.endswith("RB") and "LD" not in letters) else
             "Hot RJ" if letters.endswith("HLD") else "RJ")
    elif letters:
        t = ("Very Hot" if letters.endswith("HLD") else "Hot" if letters.endswith("WLD") else
             "TLD" if letters.endswith("TLD") else "BLD" if letters.endswith("BLD") else
             "Moderate" if letters.endswith("LD") else "")
    if channel == "TikTokAds":
        t = "TLD"
    return (_pick("lead_type", t) or t) if t else ""


_STOP_PROFILE = ("ติดต่อได้เลย", "เวลาจ่าย", "ส่งหลักฐาน", "แจ้งโอน", "ติดต่อ")
_CAMPAIGN = re.compile(r"กองทัพ|แคมเปญ|โปรโมชั่น|ชื่อแคม")


def _profile(text: str) -> str:
    m = (re.search(r"\*เพิ่มเติม\*\s*:?\s*([^@]+?)(?:@|$)", text or "", re.S)
         or re.search(r"เพิ่มเติม\s*:?\s*([^@]+?)(?:@|$)", text or "", re.S))
    s = _clean(m.group(1)) if m else ""
    if not s:
        return ""
    low = s.lower()
    cut = min([low.find(k) for k in _STOP_PROFILE if low.find(k) >= 0] or [len(s)])
    return re.sub(r"[|•\-–—:：]+$", "", s[:cut]).strip()


def _contact(text: str, d: dict) -> str:
    p = re.sub(r"[-\s]", "", d.get("phone") or "")
    m = re.search(r"0\d{8,9}", p)
    if m:
        return m.group(0)
    lid = re.search(r"ID\s*LINE\s*:?[ \t]*([^\n]+)", text or "", re.I)
    v = re.sub(r"^line:\s*", "", lid.group(1).strip(), flags=re.I).strip() if lid else ""
    v = "" if not v.strip("-–— ") else v
    return "ID LINE : " + (v or "QR code")


def _nick_of_uid(uid: str) -> str:
    from .models import LineProfile
    if not uid:
        return ""
    p = LineProfile.objects.filter(user_id=uid).select_related("employee").first()
    if not p:
        return ""
    return ((p.employee.nickname if p.employee_id else "") or (p.nickname if p.is_employee else "") or "").strip()


SURE_SELLER = ("แท็ก LINE", "งานจ่ายเบอร์ในระบบ", "ข้อความ @")   # รู้แน่ว่าเป็นใครในทะเบียน


def _seller_of(g, d: dict) -> tuple:
    """เซลล์ที่ได้ใบ → (ชื่อในชีต, มาจากไหน) — แท็กจริงของ LINE ก่อน · แล้วงานจ่ายเบอร์ของระบบ · แล้วข้อความ @"""
    from dashboard.services.constants import normalize_seller

    from . import connect as C
    from .models import GroupChat, LeadTask
    nick, how = "", ""
    mention = (g.extra or {}).get("mention") or []
    if mention:
        nick, how = _nick_of_uid(mention[-1]), "แท็ก LINE"
    if not nick and g.direction == GroupChat.OUT:
        t = LeadTask.objects.filter(code=_code_key(d.get("lead_code"))).first()
        nick, how = ((t.seller_name or "") if t else ""), "งานจ่ายเบอร์ในระบบ"
    if not nick and d.get("assigned"):
        nick = C._tag_match(d["assigned"])
        how = "ข้อความ @" if nick else ""
        if not nick:
            nick, how = d["assigned"].lstrip("@").strip(), "ข้อความ @ (ไม่พบในทะเบียน)"
    return (normalize_seller(nick) if nick else ""), how


def slip_row(g, d: dict) -> dict:
    """ใบจ่ายลีด 1 ใบ → {ช่อง canonical: ค่าที่จะเขียน} + "_why" (ที่มาของบางช่อง ไว้ดูตอน preview)"""
    from dashboard.services.google_sheets import LEADS_COL as L

    from . import connect as C
    from .models import ChatLead, ExtLead, GroupChat
    text = g.text or ""
    at = timezone.localtime(g.sent_at or timezone.now())
    code = _code_key(d.get("lead_code"))
    channel = match_channel(d.get("channel") or "")
    live = match_live(d.get("live") or "")
    seller, how = _seller_of(g, d)
    if g.direction == GroupChat.OUT:
        admin = g.sent_by_name or g.sender_name or ""
    else:
        admin = C._poster(g)
    admin = _pick("admin_name", admin) or admin
    car_ask = car_model = ""
    raw_car = _clean(d.get("car") or "")
    if raw_car and not _CAMPAIGN.search(raw_car):
        car_ask = raw_car
        try:
            hit = C.car_in(raw_car)
            car_model = (hit[0] if hit else "") or ""
        except Exception:
            car_model = ""
    ltype = lead_type(code, channel)
    # ใบที่ระบบส่งเอง: ข้อมูลลีดใน Connect ละเอียดกว่าข้อความในใบ (type/รุ่น/Admin ที่คนเลือกจาก dropdown)
    rich = None
    try:
        rich = ChatLead.objects.filter(code__iexact=code).first() or ExtLead.objects.filter(code__iexact=code).first()
    except Exception:
        rich = None
    if rich is not None:
        ltype = getattr(rich, "lead_type", "") or ltype
        car_model = getattr(rich, "car_model", "") or car_model
        if getattr(rich, "admin_name", ""):
            admin = rich.admin_name
    branch = ""
    try:
        dd = C.dropdowns()
        branch = (dd.get("branchBySeller") or {}).get(seller) or dd.get("branchTop") or ""
    except Exception:
        branch = ""
    row = {
        L.received_date: _dstr(at), L.phone: _t(_contact(text, d)), L.time: "'%02d:%02d" % (at.hour, at.minute),
        L.lead_code: code, L.sales_rep: seller, L.live_team: live, L.admin: _t(admin), L.channel: channel,
        L.branch: branch or "ชลบุรี", L.type: ltype, L.ads: _t(_clean(d.get("ads"))),
        L.car_inquiry: _t(car_ask), L.car_formula: car_model, L.customer_profile: _t(_profile(text)),
    }
    row = {k: v for k, v in row.items() if str(v).strip()}
    row["_why"] = {"seller": how}
    return row


# ════════════════════════════════════════════════════════════════════
# รายงานผล "เลข + ผล"
# ════════════════════════════════════════════════════════════════════
_REP_FULL = re.compile(r"^\s*([A-Za-z]{1,6})(\d{0,2})\s*-\s*(\d{3,6})(?:\s*/\s*(\d{1,2}))?(?![\d/])\s*(.*)$", re.S)
_REP_MONTH = re.compile(r"^\s*(\d{1,2})-(\d{3,6})(?:/(\d{1,2}))?(?![\d/])\s*(.*)$", re.S)


def parse_report(text: str):
    """"9075 รอตอบ" · "TLD10-9075 รอตอบ" · "10-9075 รอตอบ" · "9075/1 ได้รถแล้ว" → dict · ไม่ใช่รายงาน = None

    ไม่นับ: ใบจ่ายลีด · ข้อความที่มี @ (แอดมินทวง "9075 @มัท ตามด้วย") · ไม่มีข้อความต่อท้ายเลข
    """
    from .leadflow import parse_report as short
    t = (text or "").strip()
    if not t or "@" in t or re.search(r"lead\s*no", t, re.I):
        return None
    m = _REP_FULL.match(t)
    if m and len(_clean(m.group(5))) >= 2:
        return {"code": _code_key("%s%s-%s%s" % (m.group(1), m.group(2), m.group(3),
                                                  "/" + m.group(4) if m.group(4) else "")),
                "run": m.group(3), "slash": int(m.group(4) or 0), "month": 0, "body": _clean(m.group(5))}
    m = _REP_MONTH.match(t)
    if m and len(_clean(m.group(4))) >= 2 and 1 <= int(m.group(1)) <= 12:
        return {"code": "", "run": m.group(2), "slash": int(m.group(3) or 0), "month": int(m.group(1)),
                "body": _clean(m.group(4))}
    p = short(t)
    if p:
        return {"code": "", "run": p[0], "slash": p[1], "month": 0, "body": p[2]}
    return None


def _owner_rows(tab: LeadTab, rows: list, nick: str) -> list:
    from dashboard.services.constants import normalize_seller
    me = normalize_seller(nick)
    return [(n, r) for n, r in rows if normalize_seller(tab.val(r, tab.L.sales_rep)) == me]


def _num(s) -> int:
    d = re.sub(r"\D", "", str(s or ""))
    return int(d) if d else 0


# ════════════════════════════════════════════════════════════════════
# ข้อความแบน (พอร์ตจาก n8n "Parse Ban v2")
# ════════════════════════════════════════════════════════════════════
_BAN_WORD = re.compile(r"แบน|ปรับ|รีเจ")


def is_ban(g) -> bool:
    """แท็กคน + คำว่า แบน/ปรับ/รีเจ · ไม่ใช่ใบจ่ายลีด · "ขอปลดแบน" อย่างเดียวไม่นับ (n8n นับ — แถวขยะในรายงานแบน)"""
    text = g.text or ""
    if not text or re.search(r"lead\s*no", text, re.I) or "ไม่นับ" in text:
        return False
    ex = g.extra or {}
    mention = ex.get("mention") or []
    if not mention and not ("mention" not in ex and "@" in text):
        return False
    words = re.sub(r"(?:ขอ)?ปลด\s*แบน", "", text)
    if not _BAN_WORD.search(words):
        return False
    if re.search(r"ปรับ\s*\d{2,}", text) and not mention:
        return False                                     # ปรับเงินล้วน
    return True


def _ban_targets(g) -> list:
    from . import connect as C
    from .models import LineProfile
    out = []
    for uid in (g.extra or {}).get("mention") or []:
        nick = _nick_of_uid(uid)
        if not nick:
            p = LineProfile.objects.filter(user_id=uid).first()
            nick = (p.display_name or "").strip() if p else ""
        if nick and nick not in out:
            out.append(nick)
    if not out and "mention" not in (g.extra or {}):
        for tag in re.findall(r"@([^\s@]+)", g.text or ""):
            nick = C._tag_match(tag) or tag
            if nick and nick not in out:
                out.append(nick)
    return out


def _thai_date(d: int, m: int, y: int):
    if y < 100:
        y = (2500 + y - 543) if y >= 60 else 2000 + y     # "69" = พ.ศ. 2569 · "26" = ค.ศ. 2026
    elif y > 2400:
        y -= 543
    try:
        return date(y, m, d)
    except ValueError:
        return None


def ban_rows(g) -> list:
    """ข้อความแบน → แถวของแท็บ "รายงานแบน" (1 คน 1 แถว) ตามหัวคอลัมน์ banDate|time|seller|…"""
    from dashboard.services.constants import normalize_seller
    text = g.text or ""
    at = timezone.localtime(g.sent_at or timezone.now())
    has_sheet = re.search(r"ไม่กรอกชี|กรอกชี|ติ๊กรุ่น|ติ๊กรถ|ติ๊ก|รีเจ|กรอกเสร็จ", text)
    has_case = re.search(r"ไม่รับเคส|ไม่รับงาน|ไม่รับ(?!เงิน)", text)
    has_proof = re.search(r"ไม่ส่งหลักฐาน|หลักฐานการติดต่อ|ไม่ส่งหลัก", text)
    ban_type = ("ไม่รับเคส + ไม่กรอกชีต" if has_case and has_sheet else "ไม่รับเคส" if has_case else
                "ไม่กรอกชีต" if has_sheet else "ไม่ส่งหลักฐานการติดต่อ" if has_proof else "อื่นๆ")
    rm = re.search(r"เนื่องจาก([^@\n]*)", text)
    reason = _clean(rm.group(1)) if rm else ""
    rng = re.search(r"(\d{1,2})-(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})", text)
    dm = re.match(r"\s*(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})", text)
    ban_d = None
    if rng:
        ban_d = _thai_date(int(rng.group(2)), int(rng.group(3)), int(rng.group(4)))   # ช่วงวัน = ใช้วันหลัง
    elif dm:
        ban_d = _thai_date(int(dm.group(1)), int(dm.group(2)), int(dm.group(3)))
    ban_d = ban_d or at.date()
    unban = ""
    if re.search(r"ปลดแบน|ปลด\s*พน|ปลด\s*พรุ่งนี้|พรุ่งนี้|ปลด\s*พ\.?น\.?", text):
        unban = _dstr(ban_d + timedelta(days=1))
    elif re.search(r"จนกว่าจะกรอกเสร็จ|กรอกเสร็จปลดแบน|กรอกเสร็จ", text):
        unban = "จนกว่ากรอกเสร็จ"
    by = _nick_of_uid(g.sender_id or "") or ""
    rows = []
    for nick in _ban_targets(g):
        rows.append({"banDate": _dstr(ban_d), "time": "%02d:%02d" % (at.hour, at.minute),
                     "seller": _t(normalize_seller(nick) or nick), "sellerDisplay": "", "banType": ban_type,
                     "reason": _t(reason or ban_type), "bannedBy": _t(by), "unbanDate": unban, "status": "แบน",
                     "rawText": _t(text[:1000]), "groupId": g.group_id or ""})
    return rows


# ════════════════════════════════════════════════════════════════════
# จัดการข้อความ 1 แถว
# ════════════════════════════════════════════════════════════════════
class Ctx:
    """ของที่ใช้ร่วมกันใน 1 รอบ — ตัวต่อ Sheets + แท็บที่อ่านแล้ว (อ่านแท็บละครั้ง)"""

    def __init__(self, lead_api=None, ban_api=None, write=True, redirect=""):
        self._lead, self._ban, self.write = lead_api, ban_api, write
        self.tabs, self.titles, self.ban_tab, self._ban_props = {}, None, None, None
        self.redirect = redirect          # จำลอง: ทุกแท็บเดือน → แท็บทดสอบแท็บเดียว (ไม่แตะแท็บจริง)

    def lead_api(self):
        if self._lead is None:
            from dashboard.services.google_sheets import SHEET_CONFIG, load_sheet_config_overrides
            load_sheet_config_overrides()
            self._lead = _Api(SHEET_CONFIG["leads"]["spreadsheet_id"])
        return self._lead

    def ban_api(self):
        if self._ban is None:
            from dashboard.services.google_sheets import SHEET_CONFIG
            self._ban = _Api(SHEET_CONFIG["ban_report"]["spreadsheet_id"])
        return self._ban

    def tab(self, title) -> LeadTab | None:
        if self.redirect:
            title = self.redirect
        if self.titles is None:
            self.titles = self.lead_api().props()
        if title not in self.titles:
            return None
        if title not in self.tabs:
            self.tabs[title] = LeadTab(self.lead_api(), title)
        return self.tabs[title]

    @staticmethod
    def _room(api, props: dict, title: str, n: int):
        p = props.get(title) or {}
        if p.get("rows") and n > p["rows"]:
            add = max(200, n - p["rows"])
            api.expand(p["id"], add)
            p["rows"] += add

    def room(self, title: str, n: int):
        """ให้แน่ใจว่าแท็บมีแถวถึง n (ตารางเต็ม = เพิ่มแถวก่อนเขียน)"""
        self._room(self.lead_api(), self.titles or {}, title, n)

    def ban_room(self, title: str, n: int):
        if self._ban_props is None:
            self._ban_props = self.ban_api().props()
        self._room(self.ban_api(), self._ban_props, title, n)


def _contact_keys(s: str) -> set:
    s = str(s or "")
    out = {"p:" + p for p in re.findall(r"0\d{8,9}", re.sub(r"[-\s]", "", s))}
    m = re.search(r"ID\s*LINE\s*:?\s*(\S+)", s, re.I)
    if m and m.group(1).lower() not in ("qr", "-", "line@"):
        out.add("l:" + m.group(1).lower())
    return out


def handle_slip(g, d: dict, ctx: Ctx) -> dict:
    from dashboard.services.constants import normalize_seller
    from dashboard.services.google_sheets import LEADS_COL as L
    row = slip_row(g, d)
    why = row.pop("_why", {})
    code = row[L.lead_code]
    at = timezone.localtime(g.sent_at or timezone.now()).date()
    target = ctx.tab(tab_name(at))
    if target is None:
        raise SheetError("ยังไม่มีแท็บ %s ในชีตจ่ายเบอร์ (แอดมินต้องสร้างก่อน)" % tab_name(at))
    # มีเลขนี้อยู่แล้ว (แท็บเดือนนี้ / เดือนก่อน / เดือนตามเลข) = ลีดเดิม → ไม่เพิ่มแถว
    seen, hits = set(), []
    cm = _CODE_MONTH.match(code)
    cands = [target.title, tab_name(_prev(at))]
    if cm and 1 <= int(cm.group(1)) <= 12:
        y = at.year - (1 if int(cm.group(1)) > at.month else 0)
        cands.append(tab_name(date(y, int(cm.group(1)), 1)))
    for title in cands:
        t = ctx.tab(title)
        if t is None or t.title in seen:
            continue
        seen.add(t.title)
        hits += [(t, n, r) for n, r in t.find(code)]
    new_keys = _contact_keys(row.get(L.phone, ""))
    same = [(t, n, r) for t, n, r in hits
            if not new_keys or not _contact_keys(t.val(r, L.phone)) or new_keys & _contact_keys(t.val(r, L.phone))]
    if same:
        t, n, r = same[-1]                                       # แถวล่างสุดของแท็บล่าสุด
        upd = {}
        # จ่ายใหม่ (เลขเดิม คนใหม่) — เปลี่ยนเฉพาะตอนรู้แน่ว่าเป็นใครในทะเบียน
        # ★ เจอจากพรีวิวบน prod 13 ต.ค.69: ข้อความเก่าไม่มีข้อมูลแท็กจริง แท็ก "@POOH" หาในทะเบียนไม่เจอ
        #   → เกือบเอา "POOH" ไปทับ "ภู" ที่ถูกต้องอยู่แล้ว · หาไม่เจอ = ไม่แตะช่องเซลล์ของแถวเดิม
        if (row.get(L.sales_rep) and why.get("seller") in SURE_SELLER
                and normalize_seller(row[L.sales_rep]) != normalize_seller(t.val(r, L.sales_rep))):
            upd[L.sales_rep] = row[L.sales_rep]
        for f in (L.phone, L.live_team, L.admin, L.channel, L.type, L.ads, L.car_inquiry, L.car_formula,
                  L.customer_profile):
            if row.get(f) and not t.val(r, f):
                upd[f] = row[f]                                  # เติมเฉพาะช่องที่ยังว่าง — ไม่ทับที่คนแก้
        diff = {}
        if not ctx.write:                                        # preview: เทียบกับแถวที่มีอยู่ (เช่นที่ n8n เขียนไว้)
            for f, v in row.items():
                old, new = t.val(r, f), str(v).lstrip("'")
                if f == L.received_date and _parse_dmy(old) == _parse_dmy(new):
                    continue                                     # 13/10/26 = 13/10/2026 (แค่รูปแบบ)
                if old and new and _clean(old).lower() != _clean(new).lower():
                    diff[_field_name(f)] = [old, new]
        if not upd:
            return {"action": "dup", "code": code, "tab": t.title, "sheetRow": n, "diff": diff}
        if ctx.write:
            ctx.lead_api().write(t.cells(n, upd), "อัปเดตลีด %s" % code)
            t.remember(n, upd)
        return {"action": "update", "code": code, "tab": t.title, "sheetRow": n,
                "fields": sorted(_field_name(f) for f in upd), "diff": diff}
    n = max(target.last + 1, 2)
    if n > MAX_ROW:
        raise SheetError("แท็บ %s เกิน %d แถว" % (target.title, MAX_ROW))
    res = {"action": "add", "code": code, "tab": target.title, "sheetRow": n, "seller": row.get(L.sales_rep, ""),
           "sellerFrom": why.get("seller", "")}
    if hits:
        res["conflict"] = "เลข %s มีอยู่แล้ว (แถว %s) แต่เบอร์/ไลน์คนละคน — เพิ่มเป็นแถวใหม่" % (
            code, ", ".join("%s!%d" % (t.title, nn) for t, nn, _ in hits))
    if ctx.write:
        ctx.room(target.title, n)
        ctx.lead_api().write(target.cells(n, row), "เพิ่มลีด %s" % code)
        target.remember(n, row)
    else:
        res["row"] = {_field_name(f): str(v) for f, v in row.items()}
    return res


def handle_report(g, p: dict, ctx: Ctx) -> dict:
    from dashboard.services.google_sheets import LEADS_COL as L

    from . import connect as C
    from .models import LineProfile
    prof = LineProfile.objects.filter(user_id=g.sender_id or "").select_related("employee").first()
    nick = (prof.employee.nickname if prof and prof.employee_id and prof.employee.active else "") if prof else ""
    if not nick:
        return {"action": "skip", "why": "คนรายงานไม่อยู่ในทะเบียนพนักงาน"}
    at = timezone.localtime(g.sent_at or timezone.now())
    label = p["code"] or ("%s%s" % (p["run"], "/%d" % p["slash"] if p["slash"] else ""))
    for k in range(3):                                           # แท็บเดือนนี้ก่อน (เคสค้างถูกก๊อปมาเดือนใหม่)
        t = ctx.tab(tab_name(_prev(at.date(), k)))
        if t is None:
            continue
        if p["code"]:
            rows = t.find(p["code"]) or t.by_run(p["run"], p["slash"] if p["slash"] else None)
        else:
            rows = t.by_run(p["run"], p["slash"] if p["slash"] else None, p["month"] or None)
            if not p["slash"]:
                plain = [(n, r) for n, r in rows if "/" not in t.val(r, L.lead_code)]
                rows = plain or rows
        if not rows:
            continue
        mine = _owner_rows(t, rows, nick)
        empty = [(n, r) for n, r in rows if not t.val(r, L.sales_rep)]
        pick = (mine or (empty if len(rows) == 1 else []))
        if not pick:
            return {"action": "not-owner", "code": label, "tab": t.title, "reporter": nick,
                    "owner": ", ".join(sorted({t.val(r, L.sales_rep) or "-" for _, r in rows}))}
        n, r = pick[-1]
        upd = {L.update_count: str(_num(t.val(r, L.update_count)) + 1), L.last_updated_at: _dtstr(at),
               L.call_proof: C.dd_pick("call_proof", "ส่งแล้ว") or "ส่งแล้ว"}
        if not t.val(r, L.contact_datetime):
            upd[L.contact_datetime] = _dtstr(at)
        code = t.val(r, L.lead_code)
        if ctx.write:
            ctx.lead_api().write(t.cells(n, upd), "รายงานผล %s" % code)
            t.remember(n, upd)
        return {"action": "report", "code": code, "tab": t.title, "sheetRow": n, "reporter": nick,
                "count": int(upd[L.update_count])}
    return {"action": "report-miss", "code": label, "reporter": nick}


def handle_ban(g, ctx: Ctx) -> dict:
    rows = ban_rows(g)
    if not rows:
        return {"action": "skip", "why": "ข้อความแบนแต่หาชื่อคนโดนแบนไม่ได้"}
    if not ctx.write:
        return {"action": "ban", "rows": rows}
    from dashboard.services.google_sheets import SHEET_CONFIG
    api, tab = ctx.ban_api(), SHEET_CONFIG["ban_report"]["sheet_name"]
    if ctx.ban_tab is None:
        vals = api.get("%s!A1:K%d" % (_q(tab), MAX_ROW))
        hdr = [str(h).strip() for h in (vals[0] if vals else [])]
        last = max([i + 1 for i, r in enumerate(vals) if any(str(v).strip() for v in r)] or [1])
        ctx.ban_tab = {"hdr": hdr, "last": last}
    hdr = ctx.ban_tab["hdr"]
    if "seller" not in hdr or "banDate" not in hdr:
        raise SheetError("แท็บ %s ไม่มีหัวคอลัมน์ banDate/seller" % tab, 400)
    cells, n0 = {}, ctx.ban_tab["last"] + 1
    for i, r in enumerate(rows):
        for k, v in r.items():
            if k in hdr and str(v).strip():
                cells["%s!%s%d" % (_q(tab), _col(hdr.index(k)), n0 + i)] = v
    ctx.ban_room(tab, n0 + len(rows) - 1)
    api.write(cells, "บันทึกแบน")
    ctx.ban_tab["last"] = n0 + len(rows) - 1
    return {"action": "ban", "sellers": [r["seller"].lstrip("'") for r in rows], "sheetRow": n0}


def _field_name(f) -> str:
    from dashboard.services.google_sheets import LEADS_COL as L
    for k, v in vars(L).items():
        if not k.startswith("_") and v == f:
            return k
    return str(f)


def handle(g, ctx: Ctx) -> dict:
    """GroupChat 1 แถว → ผล · โยน SheetError เมื่อเขียนชีตล้ม (รอบหน้าลองใหม่)"""
    from .leadgroup import parse_leadsheet
    from .models import GroupChat
    if g.direction == GroupChat.OUT and (g.extra or {}).get("source") != "connect":
        return {"action": "skip"}
    try:
        d = parse_leadsheet(g.text or "")
    except Exception as e:
        return {"action": "parse-error", "error": ("%s: %s" % (type(e).__name__, e))[:200]}
    if d:
        return handle_slip(g, d, ctx)
    if g.direction == GroupChat.OUT:
        return {"action": "skip"}
    if get_config()["ban"] and is_ban(g):
        try:
            return handle_ban(g, ctx)
        except SheetError as e:
            if e.code in (400, 403, 404):                        # ไม่มีสิทธิ์/หาแท็บไม่เจอ = ถาวร — ข้าม ไม่ขวางคิว
                return {"action": "ban-error", "error": str(e)[:300]}
            raise
    p = parse_report(g.text or "")
    if p:
        return handle_report(g, p, ctx)
    return {"action": "skip"}


# ════════════════════════════════════════════════════════════════════
# วนประมวลผล (ตัวชี้ GroupChat.id · webhook + ระบบส่งใบ + cron เก็บตก)
# ════════════════════════════════════════════════════════════════════
class _Lock:
    def __init__(self):
        self.got = False

    def __enter__(self):
        from django.db import connection
        if connection.vendor != "postgresql":
            self.got = True
            return self
        with connection.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", [_LOCK_KEY])
            self.got = bool(cur.fetchone()[0])
        return self

    def __exit__(self, *a):
        from django.db import connection
        if self.got and connection.vendor == "postgresql":
            try:
                with connection.cursor() as cur:
                    cur.execute("SELECT pg_advisory_unlock(%s)", [_LOCK_KEY])
            except Exception:
                pass
        return False


_ROOMS = {"at": 0.0, "ids": []}


def _rooms() -> list:
    """ห้องจ่ายเบอร์ (ทะเบียนกลุ่ม + ชื่อมี "จ่ายเบอร์") · จำ 5 นาที — webhook เรียกทุกข้อความ ไม่ต้องค้นชื่อกลุ่มทุกครั้ง"""
    import time
    from . import connect as C
    if not _ROOMS["ids"] or time.time() - _ROOMS["at"] > 300:
        _ROOMS.update(at=time.time(), ids=sorted(C._lead_group_ids()))
    return _ROOMS["ids"]


def _qs(after_id):
    from .models import GroupChat
    return (GroupChat.objects.filter(id__gt=after_id, chat_type=GroupChat.GROUP, group_id__in=_rooms(),
                                     msg_type="text").order_by("id"))


def _max_id() -> int:
    from django.db.models import Max

    from .models import GroupChat
    return GroupChat.objects.aggregate(m=Max("id"))["m"] or 0


def set_since(at=None) -> int:
    """ตั้งตัวชี้ = ข้อความก่อนเวลา `at` (ไม่ใส่ = ข้อความล่าสุดตอนนี้ — ไม่ไล่ย้อน)"""
    from django.db.models import Max

    from .models import GroupChat
    if at is None:
        last = _max_id()
    else:
        last = GroupChat.objects.filter(sent_at__lt=at).aggregate(m=Max("id"))["m"] or 0
    _set_kv(KV_STATE, {"last_id": last, "at": timezone.localtime().isoformat(timespec="seconds")})
    return last


def _cursor() -> int:
    st = _kv(KV_STATE)
    if isinstance(st.get("last_id"), int):
        return st["last_id"]
    return set_since()                       # เปิดครั้งแรก = เริ่มจากตอนนี้ (ของเก่า n8n เขียนไปแล้ว)


def pending_count(older_than_min: int = 0) -> int:
    st = _kv(KV_STATE)
    if not isinstance(st.get("last_id"), int):
        return 0
    qs = _qs(st["last_id"])
    if older_than_min:
        qs = qs.filter(sent_at__lt=timezone.now() - timedelta(minutes=older_than_min))
    return qs.count()


def process_pending(limit: int = 150, ctx: Ctx | None = None) -> dict:
    """เขียนข้อความที่ยังไม่ได้จัดการลงชีต · เรียกได้ถี่ (ไม่มีงาน = query เดียวจบ)"""
    if not get_config()["enabled"]:
        return {"skipped": "ปิดอยู่"}
    with _Lock() as lk:
        if not lk.got:
            return {"skipped": "อีกตัวกำลังทำอยู่"}
        last_id = _cursor()
        msgs = list(_qs(last_id)[:limit])
        if not msgs:
            return {"pending": 0}
        ctx = ctx or Ctx()
        try:
            ctx.lead_api()                                       # ต่อ Google ไม่ได้ = ไม่แตะตัวชี้เลย
        except Exception as e:
            err = ("%s: %s" % (type(e).__name__, e))[:300]
            _set_kv(KV_LAST, {"at": timezone.localtime().isoformat(timespec="seconds"), "error": err,
                              "processed": 0, "lastId": last_id})
            _log(False, error=err)
            return {"error": err}
        res = {"at": timezone.localtime().isoformat(timespec="seconds"), "processed": 0, "added": [],
               "updated": [], "dup": [], "reports": 0, "notOwner": [], "reportMiss": [], "bans": 0,
               "conflicts": [], "unknownSeller": [], "error": ""}
        for g in msgs:
            try:
                r = handle(g, ctx)
            except (SheetError, requests.RequestException) as e:  # ชีตล้ม/เน็ต = หยุดตรงนี้ รอบหน้าเริ่มข้อความเดิม
                res["error"] = ("%s: %s" % (type(e).__name__, e))[:300]
                _log(False, error=res["error"], messageId=g.id)
                break
            except Exception as e:                               # ข้อความนี้อ่านพัง (บั๊ก) = ข้าม ไม่ให้ขวางคิวทั้งหมด
                r = {"action": "parse-error", "error": ("%s: %s" % (type(e).__name__, e))[:200]}
                log.exception("leadsheet: ข้อความ %s", g.id)
            a = r.get("action")
            if a == "add":
                res["added"].append(r["code"])
                if r.get("conflict"):
                    res["conflicts"].append(r["conflict"])
                if "ไม่พบ" in (r.get("sellerFrom") or "") or not r.get("seller"):
                    res["unknownSeller"].append(r["code"])
            elif a == "update":
                res["updated"].append(r["code"])
            elif a == "dup":
                res["dup"].append(r["code"])
            elif a == "report":
                res["reports"] += 1
            elif a == "not-owner":
                res["notOwner"].append("%s (%s รายงาน · ในชีตเป็นของ %s)" % (r["code"], r["reporter"], r["owner"]))
            elif a == "report-miss":
                res["reportMiss"].append(r["code"])
            elif a == "ban":
                res["bans"] += len(r.get("sellers") or [])
            elif a in ("ban-error", "parse-error"):
                res.setdefault("errors", []).append(r.get("error", ""))
            last_id = g.id
            res["processed"] += 1
            _set_kv(KV_STATE, {"last_id": last_id, "at": timezone.localtime().isoformat(timespec="seconds")})
        res["lastId"] = last_id
        for k in ("notOwner", "reportMiss", "conflicts", "unknownSeller", "dup"):
            res[k] = res[k][-30:]
        _set_kv(KV_LAST, res)
        return res


def _log(ok: bool, **kw):
    try:
        from dashboard.services import eventlog
        eventlog.log(eventlog.CRON, name=WHAT, ok=ok, **kw)
    except Exception:
        pass


_BG = {"busy": False}


def kick():
    """ทำในเธรดแยก (เรียกจาก webhook/ตอนระบบส่งใบ) — ห้ามหน่วงคำขอหน้าเว็บ/ข้อความตอบ LINE"""
    if _BG["busy"] or not get_config()["enabled"]:
        return False
    _BG["busy"] = True

    def run():
        try:
            process_pending()
        except Exception:
            pass
        finally:
            _BG["busy"] = False
            try:
                from django.db import connection
                connection.close()
            except Exception:
                pass
    threading.Thread(target=run, daemon=True).start()
    return True


def maybe_process(data):
    """เรียกจาก `_checkout_ingest` (thread อยู่แล้ว) หลังเก็บแชท — ทำเฉพาะเมื่อมีข้อความจากห้องจ่ายเบอร์"""
    if not get_config()["enabled"]:
        return None
    s = str(data)
    if any(gid in s for gid in _rooms()):
        return process_pending()
    return None


# ════════════════════════════════════════════════════════════════════
# ซ่อม ว/ด/ป ที่ n8n เขียนทับด้วยวันที่รายงาน
# ════════════════════════════════════════════════════════════════════
def _parse_dmy(s):
    m = re.match(r"\s*(\d{1,2})/(\d{1,2})/(\d{2,4})", str(s or ""))
    return _thai_date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def slip_dates(days: int = 120) -> dict:
    """Code → วันที่ใบจ่ายลีดถึงกลุ่มครั้งแรก (ใบในคลังแชทห้องจ่ายเบอร์ + งานจ่ายเบอร์ของระบบ)"""
    from .leadgroup import parse_leadsheet
    from .models import GroupChat, LeadTask
    out = {}
    since = timezone.now() - timedelta(days=days)
    for text, at in (GroupChat.objects.filter(chat_type=GroupChat.GROUP, group_id__in=_rooms(), sent_at__gte=since,
                                              text__icontains="lead no").values_list("text", "sent_at")):
        d = parse_leadsheet(text or "")
        if not d or not at:
            continue
        k, day = _code_key(d.get("lead_code")), timezone.localtime(at).date()
        if k and (k not in out or day < out[k]):
            out[k] = day
    for code, at in LeadTask.objects.filter(posted_at__isnull=False).values_list("code", "posted_at"):
        k, day = _code_key(code), timezone.localtime(at).date()
        if k and (k not in out or day < out[k]):
            out[k] = day
    return out


def repair_dates(tabs: list | None = None, apply: bool = False, ctx: Ctx | None = None) -> dict:
    """หาแถวที่ ว/ด/ป ถูกเขียนทับด้วยวันที่รายงาน แล้วคืนวันที่จริง (วันที่ใบถึงกลุ่ม)

    นับว่าโดนทับเมื่อ: **ว/ด/ป = วันของ "อัพเดทล่าสุด"** (n8n เขียน 2 ช่องนี้พร้อมกันเสมอ) **และ**
    วันที่ใบถึงกลุ่มจริง (จากคลังแชท) เป็นวันก่อนหน้า · เขียนเฉพาะช่อง ว/ด/ป ไม่แตะช่องอื่น
    หาใบไม่เจอ (เก่ากว่าคลังแชท) แต่ "วันที่ติดต่อ" มาก่อน ว/ด/ป (เป็นไปไม่ได้ถ้าไม่โดนทับ) = ไม่แก้ แค่บอกในรายงาน
    """
    from dashboard.services.google_sheets import LEADS_COL as L
    ctx = ctx or Ctx(write=apply)
    today = timezone.localdate()
    tabs = tabs or [tab_name(today), tab_name(_prev(today))]
    truth = slip_dates()
    out = {"tabs": [], "fix": [], "unknown": [], "applied": 0}
    for title in tabs:
        t = ctx.tab(title)
        if t is None:
            out["tabs"].append({"tab": title, "error": "ไม่มีแท็บนี้"})
            continue
        fixes, unknown = {}, 0
        for i, r in enumerate(t.rows):
            n = i + 2
            code = _code_key(t.val(r, L.lead_code))
            a = _parse_dmy(t.val(r, L.received_date))
            lu = _parse_dmy(t.val(r, L.last_updated_at))
            if not code or not a or not lu or a != lu:
                continue
            real = truth.get(code)
            if real is None:
                ct = _parse_dmy(t.val(r, L.contact_datetime))
                if not ct or ct >= a:                        # ไม่มีหลักฐานว่าโดนทับ (รายงานวันเดียวกับที่ลีดเข้า = ปกติ)
                    continue
                unknown += 1
                out["unknown"].append({"tab": title, "row": n, "code": code, "a": t.val(r, L.received_date)})
                continue
            if real < a:
                fixes[n] = real
                out["fix"].append({"tab": title, "row": n, "code": code, "from": t.val(r, L.received_date),
                                   "to": _dstr(real)})
        out["tabs"].append({"tab": title, "fix": len(fixes), "unknown": unknown})
        if apply and fixes:
            cells = {}
            for n, real in fixes.items():
                cells.update(t.cells(n, {L.received_date: _dstr(real)}))
            ctx.lead_api().write(cells, "ซ่อม ว/ด/ป แท็บ %s" % title)
            out["applied"] += len(fixes)
    if apply:
        _log(True, repaired=out["applied"], tabs=tabs)
    return out


def status() -> dict:
    st, last = _kv(KV_STATE), _kv(KV_LAST)
    return {"config": get_config(), "cursor": st.get("last_id"), "cursorAt": st.get("at"),
            "rooms": len(_rooms()), "pending": pending_count(), "last": last}


# ════════════════════════════════════════════════════════════════════
# จำลอง: แอดมินพิมพ์ใบในกลุ่ม + เซลล์รายงานผล — ไม่ส่งอะไรเข้า LINE · เขียนแท็บทดสอบแยก
# ════════════════════════════════════════════════════════════════════
SIM_TAB = "ทดสอบลงชีต (ลบได้)"


def _uid_of(nick: str) -> str:
    """LINE id ของพนักงาน (ใช้ภายในเท่านั้น — ไม่พิมพ์ออก) · ไม่มี = ค่าว่าง"""
    from .models import LineProfile
    p = (LineProfile.objects.filter(employee__nickname=nick, employee__active=True)
         .order_by("-last_seen").first())
    return p.user_id if p else ""


def _sim_msg(text: str, uid: str = "", name: str = "", mention=None, at=None):
    """ข้อความในกลุ่มแบบไม่บันทึกลงฐานข้อมูล (หน้าตาเหมือนแถว GroupChat ที่ webhook เก็บ)"""
    from .models import GroupChat
    rooms = _rooms()
    return GroupChat(chat_type=GroupChat.GROUP, group_id=rooms[0] if rooms else "", group_name="จำลอง",
                     message_id="sim", sender_id=uid, sender_name=name, msg_type="text", text=text,
                     extra={"mention": list(mention or [])}, direction=GroupChat.IN,
                     sent_at=at or timezone.now())


def _ensure_sim_tab(ctx: Ctx) -> str:
    """สร้างแท็บทดสอบ (หัวตารางก๊อปจากแท็บเดือนนี้) ถ้ายังไม่มี"""
    api = ctx.lead_api()
    props = api.props()
    if SIM_TAB not in props:
        src = tab_name(timezone.localdate())
        if src not in props:
            raise SheetError("ไม่มีแท็บ %s ให้ก๊อปหัวตาราง" % src)
        hdr = (api.get("%s!A1:AH1" % _q(src)) or [[]])[0]
        # แท็บใหม่มี 26 คอลัมน์ (A–Z) — หัวตารางจริงมี 29+ คอลัมน์ เขียนเลยขอบ = Sheets ตอบ 400
        api.batch([{"addSheet": {"properties": {"title": SIM_TAB, "gridProperties": {
            "rowCount": 200, "columnCount": max(40, len(hdr) + 5)}}}}], "สร้างแท็บทดสอบ")
        api.write({"%s!%s1" % (_q(SIM_TAB), _col(i)): h for i, h in enumerate(hdr) if str(h).strip()},
                  "หัวตารางแท็บทดสอบ")
    ctx.titles = None
    ctx.tabs = {}
    return SIM_TAB


SIM_ADS = "ทดสอบระบบลงชีต"         # ป้ายในช่อง ADS ของแถวจำลอง — ลบแถวได้เฉพาะแถวที่มีป้ายนี้ + เลขที่จดไว้
KV_SIM = "leadsheet_sim"           # {"rows": [{"tab", "code"}]} แถวจำลองที่ลงแท็บเดือนจริง (รอลบ)


def delete_sim_tab() -> bool:
    ctx = Ctx()
    props = ctx.lead_api().props()
    if SIM_TAB not in props:
        return False
    ctx.lead_api().batch([{"deleteSheet": {"sheetId": props[SIM_TAB]["id"]}}], "ลบแท็บทดสอบ")
    return True


def delete_sim_rows() -> list:
    """ลบแถวจำลองที่ลงแท็บเดือนจริง — **เฉพาะเลขที่จดไว้ตอนจำลอง และช่อง ADS เป็นป้ายจำลอง** (อ่านสดก่อนลบ ·
    ลบจากล่างขึ้นบน) · แถวที่ไม่ตรงทั้ง 2 อย่างไม่แตะ · คืนรายการที่ลบ"""
    from dashboard.services.google_sheets import LEADS_COL as L
    want = _kv(KV_SIM).get("rows") or []
    if not want:
        return []
    ctx = Ctx()
    api, props, done = ctx.lead_api(), ctx.lead_api().props(), []
    for title in sorted({w["tab"] for w in want}):
        if title not in props:
            continue
        t = LeadTab(api, title)
        codes = {_code_key(w["code"]) for w in want if w["tab"] == title}
        rows = sorted((n for c in codes for n, r in t.find(c) if t.val(r, L.ads) == SIM_ADS), reverse=True)
        if rows:
            api.batch([{"deleteDimension": {"range": {"sheetId": props[title]["id"], "dimension": "ROWS",
                                                      "startIndex": n - 1, "endIndex": n}}} for n in rows],
                      "ลบแถวจำลอง")
            done += ["%s แถว %d" % (title, n) for n in rows]
    _set_kv(KV_SIM, {"rows": []})
    return done


def simulate(seller: str, admin: str, other: str = "", channel: str = "Live tiktok ช่องขายบอส",
             real_tab: bool = False) -> list:
    """จำลองแอดมินจ่ายเบอร์ในกลุ่ม → ลงชีตด้วยโค้ดตัวจริงทุกขั้น · คืนบรรทัดรายงานผล

    ไม่ส่ง LINE · ไม่บันทึกข้อความลงฐานข้อมูล · ไม่แตะตัวชี้ / ชีตรายงานแบน
    `real_tab=False` = แท็บทดสอบแยก · `True` = **ต่อท้ายแท็บเดือนจริง** (แดชบอร์ดนับระหว่างที่แถวยังอยู่ →
    จดเลขไว้ใน KV ให้ `delete_sim_rows()` ลบทีหลัง)
    """
    from dashboard.services.google_sheets import LEADS_COL as L

    from .leadgroup import parse_leadsheet
    from .models import Employee
    out = []
    emp = Employee.objects.filter(nickname=seller, active=True).first()
    if not emp:
        raise SheetError("ไม่พบเซลล์ชื่อเล่น %s ในทะเบียนพนักงาน" % seller)
    s_uid, a_uid = _uid_of(seller), _uid_of(admin)
    if real_tab:
        ctx = Ctx()
    else:
        ctx = Ctx(redirect=SIM_TAB)
        _ensure_sim_tab(ctx)
    now = timezone.localtime()
    code = "TLD%d-9%s" % (now.month, now.strftime("%d%H%M")[-5:])     # เลขรัน 6 หลักขึ้นต้น 9 — ไม่ชนเลขจริง (4 หลัก)
    run = code.split("-")[1]
    lines = [
        "Ac Lead No.   %s" % code,
        "Ads  : %s" % SIM_ADS,
        "ชื่อ Account: ลูกค้าทดสอบ",
        "ID LINE : -",
        "เบอร์โทร : 080-000-0000",
        "ช่องทาง  : %s" % channel,
        "รถ : สนใจ civic fe ปี22",
        "ไลฟ์ :   live sale",
        "เพิ่มเติม : ลูกค้าทดสอบ ทำงานโรงงาน ติดต่อได้เลยนะครับ  @%s" % (emp.display_name or seller),
    ]
    slip = "\n".join(lines)
    out.append("ข้อความที่จำลองว่าแอดมิน %s พิมพ์ในกลุ่ม (ไม่ได้ส่งเข้า LINE):" % admin)
    out += ["    " + x for x in lines]
    out.append("แท็กจริงของ LINE: %s" % (("มี (ชี้ไปที่ %s)" % seller) if s_uid else "ไม่มี — ใช้ชื่อหลัง @ แทน"))

    g = _sim_msg(slip, a_uid, admin, [s_uid] if s_uid else [])
    d = parse_leadsheet(slip)
    r = handle_slip(g, d, ctx)
    tab = r.get("tab") or SIM_TAB
    if real_tab and r.get("action") == "add":
        st = _kv(KV_SIM)
        _set_kv(KV_SIM, {"rows": (st.get("rows") or []) + [{"tab": tab, "code": r["code"]}]})
    out.append("1) แอดมินโพสต์ใบ → %s %s แถว %s · เซลล์ = %s (%s)" % (
        r["action"], r["code"], r["sheetRow"], r.get("seller", ""), r.get("sellerFrom", "")))
    r2 = handle_slip(g, d, ctx)
    out.append("2) แอดมินโพสต์ใบเดิมซ้ำ → %s (ต้องเป็น dup = ไม่เพิ่มแถว)" % r2["action"])
    n = r["sheetRow"]
    t = ctx.tab(tab)
    a_before = t.val(t.rows[n - 2], L.received_date) if len(t.rows) >= n - 1 else ""
    if s_uid:
        rep = _sim_msg("%s รอตอบครับ" % run, s_uid, seller, at=timezone.now() + timedelta(minutes=5))
        r3 = handle(rep, ctx)
        out.append('3) %s รายงาน "%s รอตอบครับ" → %s · จำนวนอัพเดท = %s' % (
            seller, run, r3["action"], r3.get("count", "-")))
    else:
        out.append("3) ข้ามการรายงานผล — %s ยังไม่มีบัญชี LINE ผูกในทะเบียน" % seller)
    o_uid = _uid_of(other) if other else ""
    if o_uid:
        r4 = handle(_sim_msg("%s ลูกค้าไม่รับสาย" % run, o_uid, other), ctx)
        out.append("4) %s (ไม่ใช่เจ้าของ) รายงานเลขเดียวกัน → %s (ต้องเป็น not-owner = ไม่ลง)" % (other, r4["action"]))
    fresh = LeadTab(ctx.lead_api(), tab)                          # อ่านแถวกลับจากชีตจริง
    row = next((rr for _, rr in fresh.find(code)), [])
    out.append('แถวในชีตตอนนี้ (แท็บ "%s" แถว %d · มี %d แถวของเลขนี้):' % (tab, n, len(fresh.find(code))))
    for i, h in enumerate(fresh.header):
        v = str(row[i]).strip() if i < len(row) else ""
        if v:
            out.append("    %-28s %s" % (re.sub(r"\s+", " ", str(h)).strip()[:28], v))
    after = fresh.val(row, L.received_date)
    out.append("ว/ด/ป ก่อนรายงาน = %s · หลังรายงาน = %s → %s" % (
        a_before, after, "ไม่ถูกทับ ✓" if after == a_before else "ถูกทับ ✗"))
    return out
