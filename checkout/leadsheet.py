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

# ★ 13 ต.ค.69 เจ้าของสั่ง: *"ขึ้นเดือนใหม่ต้องกรอกลงเดือนล่าสุด · ถ้ายังไม่เจอแท็บใหม่ให้บันทึกลงแท็บเดิมไปก่อน
#   จนกว่าจะมีแท็บใหม่ค่อยอัปเดตในแท็บใหม่ · มีข้อผิดพลาด/บันทึกไม่ได้ แจ้ง LINE ส่วนตัวฉัน (วัฒนกิจ)"*
KV_FALLBACK = "leadsheet_fallback"  # {"rows": [{"want","tab","code","at"}], "checkedAt"} ใบที่ลงแท็บเดิมเพราะยังไม่มีแท็บใหม่
FALLBACK_MONTHS = 3                # ลงแท็บเดิมได้ย้อนกี่เดือน
FALLBACK_CHECK_MIN = 5             # มีใบรอย้าย = เช็คทุก 5 นาทีว่าแอดมินสร้างแท็บใหม่หรือยัง (แม้ไม่มีข้อความใหม่)
KV_ALERT = "leadsheet_alert"       # {"sent": {คีย์: iso}, "failing": str, "lastSend": {...}} — กันแจ้งเตือนซ้ำ
ALERT_TO = ("Wattanakit", "วัฒนกิจ")  # ผู้รับแจ้งเตือนทาง LINE ส่วนตัว · เปลี่ยนได้ด้วย manage.py leadsheet --alert-to
ALERT_REPEAT_MIN = 60              # ปัญหาเดิมยังไม่หาย = เตือนซ้ำทุก 1 ชม. (cron ลองใหม่ทุกนาที แต่ไม่ต้องเตือนทุกนาที)
FALLBACK_REMIND_MIN = 360          # ยังไม่มีแท็บเดือนใหม่ = เตือนซ้ำทุก 6 ชม.
# ★ 14 ต.ค.69 เจ้าของแจ้ง *"เคสที่เจอบ่อยคือ column เปลี่ยนชื่อหรือขยับแล้วบันทึกไม่ได้ · ถ้าทำให้ refresh เองแล้วบันทึกได้
#   ก็ดี แต่แจ้งฉันด้วย"* — ระบบอ่านหัวตารางใหม่ทุกรอบอยู่แล้ว (ขยับ = ตามได้เอง) แต่หัวคอลัมน์ถูกเปลี่ยนชื่อ = ช่องนั้น
#   ถูกข้ามเงียบๆ → จำตำแหน่งคอลัมน์ล่าสุดที่ใช้ได้ไว้ เปลี่ยนชื่อในที่เดิมได้ใช้คอลัมน์เดิมต่อ + แจ้งทุกกรณี
KV_COLS = "leadsheet_cols"         # {แท็บ: {ช่อง: {"i": ลำดับคอลัมน์, "h": หัวคอลัมน์}}} ตำแหน่งที่ใช้ได้ล่าสุด
# ★ 14 ต.ค.69 เจ้าของสั่ง *"ถ้ามี error หรือข้อผิดพลาดอะไร บันทึก log ไว้ และแจ้งเตือนฉันด้วย"*
#   ทุกเรื่องที่แจ้ง = 1 แถวใน dash_event_log (kind=leadsheet) · ดูย้อนหลัง: manage.py leadsheet --log
#   + ตัวเฝ้าระบบ (watchdog) ในตัวเว็บเอง — จับกรณี "ไม่มีอะไรทำงานเลย" ที่ตัวแจ้งเตือนปกติมองไม่เห็น
#     (cron จาก n8n หยุด · ข้อความ LINE ไม่วิ่งเข้า · ข้อความค้างไม่มีใครลง)
KV_WD = "leadsheet_watchdog"       # รอบล่าสุดของตัวเฝ้าระบบ {at, pid, issues}
WD_LOCK_KEY = 7_406_066            # advisory lock — gunicorn 5 worker มีตัวเฝ้าทำงานจริงตัวเดียว
WD_EVERY_SEC = 300                 # ตรวจทุก 5 นาที
CRON_STALE_MIN = 10                # cron ไม่ทำงานเกินนี้ = แจ้ง
STUCK_MIN = 15                     # ข้อความค้างไม่ได้ลงชีตเกินนี้ = ลองลงเอง แล้วแจ้ง
QUIET_MIN = 90                     # ช่วงทำงานไม่มีข้อความจากห้องจ่ายเบอร์เข้าเลยเกินนี้ = แจ้ง
QUIET_HOURS = (10, 19)             # ช่วงทำงานที่ห้องจ่ายเบอร์ต้องมีข้อความ (วัดจริง ~15–20 ข้อความ/ชม.)
# ★ 15 ต.ค.69 เจ้าของแจ้ง *"เซลล์ชื่อ 'ใหม่' โผล่ในชีต ฉันตั้งค่าไว้ให้เป็น Admin"* — n8n แปลง "คน" เป็น "ชื่อในชีต"
#   ด้วยแท็บ "รายชื่อสมาชิกกลุ่ม Lead" (userId | displayName | Nickname) ทุกขั้น: เซลล์ของใบจ่ายลีด · เจ้าของตอนรายงานผล ·
#   คนโดนแบน/คนสั่งแบน · ตอนย้ายมาผมใช้ชื่อเล่นในทะเบียนพนักงานแทน → ขั้นนี้หลุด (Mai = ADMIN ในแท็บนั้น)
#   ตอนนี้แท็บนั้นชนะทะเบียน · เทียบด้วย LINE id แล้วชื่อที่ตั้งใน LINE แบบตรงตัวเท่านั้น (ไม่ fuzzy)
MEMBERS_TAB = "รายชื่อสมาชิกกลุ่ม Lead"
MEMBERS_TTL_SEC = 600
MEMBER_HOW = "แท็บรายชื่อสมาชิกกลุ่ม Lead"
_MEMBERS = {"at": 0.0, "base": None, "uid": {}, "disp": {}}


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
    """enabled/ban/alert = สวิตช์ · alert_to = ชื่อเล่น (หรือชื่อ LINE) ผู้รับแจ้งเตือน · ว่าง = ALERT_TO"""
    c = {"enabled": False, "ban": True, "alert": True, "alert_to": ""}
    d = _kv(KV_CONFIG)
    c.update({k: bool(d[k]) for k in ("enabled", "ban", "alert") if k in d})
    if isinstance(d.get("alert_to"), str):
        c["alert_to"] = d["alert_to"].strip()[:80]
    return c


def set_config(**kw) -> dict:
    c = get_config()
    for k, v in kw.items():
        if v is None:
            continue
        c[k] = str(v).strip()[:80] if k == "alert_to" else bool(v)
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


def _slash_of(code) -> int:
    """เลขไม้ (/n) ท้ายเลขลีด · ไม่มี = 0"""
    m = _RUN.search(_code_key(code))
    return int(m.group(2) or 0) if m else 0
_CODE_MONTH = re.compile(r"^[A-Z]*?(\d{1,2})-")


def _write_fields() -> tuple:
    """ช่องที่ระบบนี้เขียนลงชีต (ใบจ่ายลีด + รายงานผล)"""
    from dashboard.services.google_sheets import LEADS_COL as L
    return (L.received_date, L.phone, L.time, L.lead_code, L.sales_rep, L.live_team, L.admin, L.channel, L.branch,
            L.type, L.ads, L.car_inquiry, L.car_formula, L.customer_profile, L.update_count, L.last_updated_at,
            L.contact_datetime, L.call_proof)


def _col_label(f) -> str:
    """ชื่อหัวคอลัมน์มาตรฐานของช่อง (ชื่อแรกในรายการที่ระบบรู้จัก) — ไว้เขียนในแจ้งเตือน"""
    from dashboard.services.google_sheets import _LEAD_FIELD_ALIASES
    for idx, names in _LEAD_FIELD_ALIASES:
        if idx == f:
            return names[0]
    return str(f)


def _heal_columns(t, learn: bool):
    """เทียบการจับคู่คอลัมน์รอบนี้กับตำแหน่งที่ใช้ได้ล่าสุดของแท็บนี้ (KV_COLS)

    · คอลัมน์ขยับ (ชื่อเดิม ตำแหน่งใหม่) — จับคู่ด้วยชื่อตามได้เองอยู่แล้ว → แจ้งให้รู้ (รวมเป็นข้อความเดียวต่อแท็บ)
    · หัวคอลัมน์ถูกเปลี่ยนชื่อ "ในที่เดิม" → ใช้คอลัมน์เดิมต่อ + แจ้ง ถ้าเข้าเงื่อนไขทุกข้อ:
        ตำแหน่งเดิมมีหัวคอลัมน์ · หัวนั้นไม่ใช่ของช่องอื่นที่ระบบรู้จัก · คอลัมน์ข้างๆ (ที่รู้จัก) ยังอยู่ที่เดิม
      (ข้อหลังกันกรณี "ลบคอลัมน์" แล้วทุกอย่างเลื่อน — ถ้าเดาตำแหน่งตอนนั้นจะเขียนลงช่องผิด → ไม่เดา แจ้งว่าหาไม่เจอแทน)
    · learn = รอบเขียนจริง → จำตำแหน่งที่ใช้ได้ล่าสุดไว้ (preview/จำลองไม่จำ)
    """
    st = _kv(KV_COLS)
    known = st.get(t.title) or {}
    hdr = [str(h).strip() for h in t.header]
    claimed = set(t.cm.values())
    moved = []
    for f in _write_fields():
        k = known.get(str(f)) or {}
        cur = t.cm.get(f)
        if cur is not None:
            if k and k.get("i") is not None and k["i"] != cur:
                moved.append("%s %s→%s" % (_col_label(f), _col(k["i"]), _col(cur)))
            continue
        i = k.get("i")
        if i is None or i >= len(hdr) or not hdr[i] or i in claimed:
            continue
        neigh = [nf for nf, v in known.items() if v.get("i") in (i - 1, i + 1)]
        if not neigh or any(t.cm.get(int(nf)) != known[nf]["i"] for nf in neigh):
            continue
        t.cm[f] = i
        claimed.add(i)
        t.notes.append(("colheal:%s:%s:%s" % (t.title, f, hdr[i]),
                        'แท็บ "%s": หัวคอลัมน์ "%s" (คอลัมน์ %s) ถูกเปลี่ยนชื่อเป็น "%s" — ระบบบันทึกลงคอลัมน์เดิมต่อให้แล้ว '
                        '· ถ้าไม่ใช่ช่องเดียวกัน แก้หัวคอลัมน์กลับเป็น "%s"' % (t.title, k.get("h") or _col_label(f),
                                                                          _col(i), hdr[i], _col_label(f)), 0))
    if moved:
        sig = ",".join(sorted(moved))
        t.notes.append(("colmove:%s:%s" % (t.title, sig),
                        'แท็บ "%s": คอลัมน์ขยับ (%s) — ระบบปรับตามให้แล้ว บันทึกได้ปกติ' % (t.title, " · ".join(moved[:8])
                                                                                     + (" ฯลฯ" if len(moved) > 8 else "")),
                        0))
    if learn and t.cm.get(t.L.lead_code) is not None:
        new = {str(f): {"i": t.cm[f], "h": hdr[t.cm[f]] if t.cm[f] < len(hdr) else ""}
               for f in _write_fields() if t.cm.get(f) is not None}
        if new != known:
            st[t.title] = new
            keep = [k for k in st if k != t.title][-5:] + [t.title]      # จำแค่ ~6 แท็บล่าสุด
            _set_kv(KV_COLS, {k: st[k] for k in keep})


def _column_items(ctx) -> list:
    """รายการแจ้งเตือนเรื่องคอลัมน์ของรอบนี้ (ซ่อม/ขยับ/หาไม่เจอ)"""
    out = list(ctx.col_notes)
    for t in list(ctx.tabs.values()):
        if t is None:
            continue
        out += t.notes
        if t.missing:
            names = sorted(_col_label(f) for f in t.missing)
            hdr = [str(h).strip() for h in t.header if str(h).strip()]
            out.append(("colmiss:%s:%s" % (t.title, ",".join(names)),
                        'แท็บ "%s": หาหัวคอลัมน์ %s ไม่เจอ — ช่องนี้ไม่ได้บันทึก (ส่วนอื่นของแถวบันทึกแล้ว) · '
                        "แก้ชื่อหัวคอลัมน์ให้ตรงของเดิม · หัวตารางตอนนี้: %s"
                        % (t.title, ", ".join('"%s"' % n for n in names), " | ".join(hdr[:14])), ALERT_REPEAT_MIN))
    return out


class LeadTab:
    """แท็บรายเดือน 1 แท็บ + ดัชนี Code → แถว · อ่านครั้งเดียวต่อรอบแล้วแก้ในหน่วยความจำตามที่เขียนไป"""

    def __init__(self, api, title, learn: bool = False):
        from dashboard.services.google_sheets import LEADS_COL, _resolve_lead_colmap
        self.api, self.title = api, title
        vals = api.get("%s!A1:AH%d" % (_q(title), MAX_ROW))
        self.header = vals[0] if vals else []
        self.rows = vals[1:] if len(vals) > 1 else []            # แถวชีต = index + 2
        self.cm = _resolve_lead_colmap(self.header, self.rows[:20]) if self.header else {}
        self.L = LEADS_COL
        self.notes, self.missing = [], set()                     # แจ้งเตือนเรื่องคอลัมน์ · ช่องที่เขียนไม่ได้
        if self.header:
            _heal_columns(self, learn)                           # หัวคอลัมน์ถูกเปลี่ยนชื่อในที่เดิม = ใช้คอลัมน์เดิมต่อ
        if self.cm.get(LEADS_COL.lead_code) is None:
            e = SheetError("แท็บ %s ไม่มีหัวคอลัมน์ Code" % title)
            e.header = list(self.header)
            raise e
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

    def find_legacy(self, code) -> list:
        """แถวไม้ 2 ที่ลงไว้โดยไม่มี /n (บั๊ก 14–15 ต.ค.69: RNLD10-8286 แทน RNLD10-8286/1)
        — ใช้เมื่อหาเลขเต็มไม่เจอ · เฉพาะเลขขึ้นต้น R เท่านั้น (เลขปกติไม่มี /n อยู่แล้ว)"""
        k = _code_key(code)
        if "/" not in k or not k.startswith("R"):
            return []
        return self.find(k.split("/")[0])

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
            elif str(v).strip():
                self.missing.add(f)                              # หาคอลัมน์ไม่เจอ = ช่องนี้ไม่ได้บันทึก → แจ้งเจ้าของ
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


_EMOJI = re.compile("[%s-%s%s-%s%s-%s%s-%s%s%s]" % tuple(chr(c) for c in (   # อิโมจิ/สัญลักษณ์ในชื่อ LINE
    0x10000, 0x10FFFF, 0x2190, 0x21FF, 0x2300, 0x27BF, 0x2B00, 0x2BFF, 0xFE0F, 0x200D)))


def _dkey(s) -> str:
    """ชื่อที่ตั้งใน LINE → คีย์เทียบ: ตัวพิมพ์เล็ก · ตัดอิโมจิ · ช่องว่างเหลือช่องเดียว (เทียบตรงตัว ไม่ fuzzy)"""
    return re.sub(r"\s+", " ", _EMOJI.sub("", str(s or ""))).strip().lower()


def load_members(ctx) -> dict:
    """แท็บ "รายชื่อสมาชิกกลุ่ม Lead" → {"uid": {LINE id: Nickname}, "disp": {ชื่อ LINE: Nickname}} · จำ 10 นาที

    ไม่มีแท็บนี้ = ว่าง (ใช้ชื่อเล่นในทะเบียนตามเดิม) · อ่านพลาด = ใช้ของที่จำไว้ · ไม่เคยอ่านได้เลย = โยน SheetError
    (รอบหน้าลองใหม่ — ลงชีตด้วยชื่อผิดแล้วต้องตามแก้ทีหลัง แย่กว่ารอนาทีเดียว)
    ชื่อ LINE ซ้ำกันแต่ Nickname ต่างกัน = ไม่ใช้ชื่อนั้นเทียบ (ไม่เดาว่าใคร)
    """
    import time
    api = ctx.lead_api()
    base = getattr(api, "base", "")
    now = time.time()
    if _MEMBERS["base"] == base and now - _MEMBERS["at"] < MEMBERS_TTL_SEC:
        return _MEMBERS
    if ctx.titles is None:
        ctx.titles = api.props()
    if MEMBERS_TAB not in ctx.titles:
        _MEMBERS.update(at=now, base=base, uid={}, disp={})
        return _MEMBERS
    try:
        vals = api.get("%s!A1:Z2000" % _q(MEMBERS_TAB))
    except SheetError:
        if _MEMBERS["base"] == base and _MEMBERS["at"]:
            return _MEMBERS
        raise
    hdr = [str(h).strip().lower() for h in (vals[0] if vals else [])]
    iu, idn, inn = (hdr.index(k) if k in hdr else -1 for k in ("userid", "displayname", "nickname"))
    uid, disp, clash = {}, {}, set()
    for r in (vals[1:] if inn >= 0 else []):
        cell = [str(v).strip() for v in r]
        nick = cell[inn] if inn < len(cell) else ""
        if not nick:
            continue
        if 0 <= iu < len(cell) and cell[iu]:
            uid[cell[iu]] = nick
        k = _dkey(cell[idn]) if 0 <= idn < len(cell) else ""
        if k:
            if disp.get(k, nick) != nick:
                clash.add(k)
            disp[k] = nick
    for k in clash:
        disp.pop(k, None)
    _MEMBERS.update(at=now, base=base, uid=uid, disp=disp)
    return _MEMBERS


def member_name(ctx, uid: str = "", nick: str = "", disp: str = "") -> str:
    """ชื่อที่แท็บรายชื่อสมาชิกตั้งไว้ให้คนนี้ ("" = ไม่ได้ตั้ง) — เทียบ LINE id ก่อน → บัญชี LINE ของคนในทะเบียนชื่อเล่นนี้ →
    ชื่อที่ตั้งใน LINE (ตรงตัว) · ใช้กับใบที่ระบบส่งเองด้วย (มีแต่ชื่อเล่นจากงานจ่ายเบอร์ ไม่มี LINE id)"""
    if ctx is None:
        return ""
    m = load_members(ctx)
    if not m["uid"] and not m["disp"]:
        return ""
    if uid and m["uid"].get(uid):
        return _upper_admin(m["uid"][uid])
    names = [disp] if disp else []
    if nick:
        from django.db.models import Q

        from .models import Employee, LineProfile
        for u, dn in LineProfile.objects.filter(Q(employee__nickname=nick) | Q(nickname=nick, is_employee=True)
                                                ).values_list("user_id", "display_name"):
            if m["uid"].get(u):
                return _upper_admin(m["uid"][u])
            names.append(dn)
        names += list(Employee.objects.filter(nickname=nick).values_list("display_name", flat=True))
    for n in names:
        k = _dkey(n)
        if k and m["disp"].get(k):
            return _upper_admin(m["disp"][k])
    return ""


def _upper_admin(name: str) -> str:
    """เจ้าของสั่ง 15 ต.ค.69 "ใช้คำว่า ADMIN ตัวใหญ่หมด" — ตัวเลือกในชีตและคีย์ของแดชบอร์ดคือ ADMIN"""
    return "ADMIN" if str(name or "").strip().upper() == "ADMIN" else name


# รู้แน่ว่าเป็นใคร (แท็กจริง / งานในระบบ / เจอในทะเบียน / เจอในแท็บรายชื่อสมาชิก) — ใช้ตัดสินว่าเปลี่ยนเซลล์ของแถวเดิมได้ไหม
SURE_SELLER = ("แท็ก LINE", "งานจ่ายเบอร์ในระบบ", "ข้อความ @", MEMBER_HOW)


def _seller_of(g, d: dict, ctx=None) -> tuple:
    """เซลล์ที่ได้ใบ → (ชื่อในชีต, มาจากไหน) — แท็กจริงของ LINE ก่อน · แล้วงานจ่ายเบอร์ของระบบ · แล้วข้อความ @
    แล้วแปลงเป็นชื่อที่แท็บ "รายชื่อสมาชิกกลุ่ม Lead" ตั้งไว้ (ขั้นเดียวกับ n8n · เช่น ใหม่ → ADMIN)"""
    from dashboard.services.constants import normalize_seller

    from . import connect as C
    from .models import GroupChat, LeadTask
    nick, how, uid, tag = "", "", "", ""
    mention = (g.extra or {}).get("mention") or []
    if mention:
        uid = mention[-1]
        nick, how = _nick_of_uid(uid), "แท็ก LINE"
    if not nick and g.direction == GroupChat.OUT:
        t = (LeadTask.objects.filter(code=_code_key(d.get("lead_code_full") or d.get("lead_code"))).first()
             or LeadTask.objects.filter(code=_code_key(d.get("lead_code"))).first())
        nick, how = ((t.seller_name or "") if t else ""), "งานจ่ายเบอร์ในระบบ"
    if not nick and d.get("assigned"):
        tag = d["assigned"].lstrip("@").strip()
        nick = C._tag_match(d["assigned"])
        how = "ข้อความ @" if nick else ""
        if not nick:
            nick, how = tag, "ข้อความ @ (ไม่พบในทะเบียน)"
    sheet = member_name(ctx, uid=uid, nick=nick if how in SURE_SELLER else "", disp=tag)
    if sheet:
        if how not in SURE_SELLER:
            how = MEMBER_HOW
        nick = sheet
    return (normalize_seller(nick) if nick else ""), how


def slip_row(g, d: dict, ctx=None) -> dict:
    """ใบจ่ายลีด 1 ใบ → {ช่อง canonical: ค่าที่จะเขียน} + "_why" (ที่มาของบางช่อง ไว้ดูตอน preview)"""
    from dashboard.services.google_sheets import LEADS_COL as L

    from . import connect as C
    from .models import ChatLead, ExtLead, GroupChat
    text = g.text or ""
    at = timezone.localtime(g.sent_at or timezone.now())
    code = _code_key(d.get("lead_code_full") or d.get("lead_code"))     # เลขเต็ม (ไม้ 2 มี /1)
    channel = match_channel(d.get("channel") or "")
    live = match_live(d.get("live") or "")
    seller, how = _seller_of(g, d, ctx)
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
        if rich is None and code != _code_key(d.get("lead_code")):
            base = _code_key(d.get("lead_code"))
            rich = ChatLead.objects.filter(code__iexact=base).first() or ExtLead.objects.filter(code__iexact=base).first()
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


def _owner_rows(tab: LeadTab, rows: list, names) -> list:
    """แถวที่เจ้าของ = คนรายงาน · `names` = ชื่อเล่นในทะเบียน + ชื่อในแท็บรายชื่อสมาชิก (เช่น ใหม่ / ADMIN)"""
    from dashboard.services.constants import normalize_seller
    me = {normalize_seller(n) for n in ([names] if isinstance(names, str) else names) if n}
    return [(n, r) for n, r in rows if normalize_seller(tab.val(r, tab.L.sales_rep)) in me]


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


def _ban_targets(g, ctx=None) -> list:
    """คนโดนแบน → ชื่อในรายงานแบน · แท็บรายชื่อสมาชิกชนะทะเบียน (n8n ใช้ Nickname ในแท็บนั้น — ใหม่ = ADMIN)"""
    from . import connect as C
    from .models import LineProfile
    out = []
    for uid in (g.extra or {}).get("mention") or []:
        reg = _nick_of_uid(uid)
        nick = member_name(ctx, uid=uid, nick=reg) or reg
        if not nick:
            p = LineProfile.objects.filter(user_id=uid).first()
            nick = (p.display_name or "").strip() if p else ""
        if nick and nick not in out:
            out.append(nick)
    if not out and "mention" not in (g.extra or {}):
        for tag in re.findall(r"@([^\s@]+)", g.text or ""):
            reg = C._tag_match(tag)
            nick = member_name(ctx, nick=reg, disp=tag) or reg or tag
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


def ban_rows(g, ctx=None) -> list:
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
    reg = _nick_of_uid(g.sender_id or "")
    by = member_name(ctx, uid=g.sender_id or "", nick=reg) or reg or ""
    rows = []
    for nick in _ban_targets(g, ctx):
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
        self.notready = set()             # แท็บที่มีชื่อแล้วแต่ยังไม่มีหัวตาราง (แอดมินเพิ่งสร้างเปล่าๆ)
        self.col_notes = []               # แท็บที่หาคอลัมน์ Code ไม่เจอ (หัวตารางมี แต่ชื่อเปลี่ยน/ลบ)

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
            try:
                self.tabs[title] = LeadTab(self.lead_api(), title, learn=self.write and not self.redirect)
            except SheetError as e:
                # แอดมินสร้างแท็บเดือนใหม่ไว้เปล่าๆ (ยังไม่วางหัวตาราง) = ยังใช้ไม่ได้ เหมือนยังไม่มีแท็บ
                #   ถ้าโยนต่อ คิวทั้งหมด (รวมรายงานผลของเคสเดือนก่อน) จะค้างจนกว่าจะมีหัวตาราง
                if "ไม่มีหัวคอลัมน์ Code" not in str(e):
                    raise
                self.tabs[title] = None
                self.notready.add(title)
                hdr = [str(h).strip() for h in (getattr(e, "header", None) or []) if str(h).strip()]
                if hdr:                                          # มีหัวตาราง แต่หาคอลัมน์ Code ไม่เจอ = มีคนแก้หัวตาราง
                    self.col_notes.append(("colcode:" + title, 'แท็บ "%s": หาหัวคอลัมน์ "Code" ไม่เจอ — ระบบใช้แท็บนี้ไม่ได้ '
                                           "(ใบใหม่ลงแท็บเดือนก่อนไปก่อน · รายงานผลของเคสในแท็บนี้ลงไม่ได้) · แก้หัวคอลัมน์ "
                                           'กลับเป็น "Code" · หัวตารางตอนนี้: %s' % (title, " | ".join(hdr[:12])),
                                           ALERT_REPEAT_MIN))
        return self.tabs[title]

    def month_tab(self, at) -> tuple:
        """แท็บที่จะลงใบของวันที่ `at` → (LeadTab, ชื่อแท็บที่ควรเป็น ถ้าต้องลงแท็บเดิมแทน · ไม่งั้น "")

        ปกติ = แท็บของเดือนนั้น ("พฤศจิกายน 69") · ยังไม่มี/ยังเปล่า = แท็บเดือนล่าสุดที่มี (ย้อนได้ FALLBACK_MONTHS)
        """
        want = tab_name(at)
        t = self.tab(want)
        if t is not None or self.redirect:
            return t, ""
        for k in range(1, FALLBACK_MONTHS + 1):
            t = self.tab(tab_name(_prev(at, k)))
            if t is not None:
                return t, want
        return None, want

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
    row = slip_row(g, d, ctx)
    why = row.pop("_why", {})
    code = row[L.lead_code]
    at = timezone.localtime(g.sent_at or timezone.now()).date()
    # ขึ้นเดือนใหม่ = แท็บเดือนใหม่ · ยังไม่มีแท็บใหม่ = ลงแท็บเดิมไปก่อน แล้ว `settle_fallback` ย้ายให้เมื่อแท็บใหม่มา
    target, fallback = ctx.month_tab(at)
    if target is None:
        raise SheetError("ยังไม่มีแท็บ %s และไม่มีแท็บเดือนก่อนหน้าให้ลงแทน (แอดมินต้องสร้างแท็บ)" % tab_name(at))
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
        hits += [(t, n, r) for n, r in sorted(t.find(code) + t.find_legacy(code), key=lambda x: x[0])]   # ยึดแถวล่าสุด
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
        if _code_key(t.val(r, L.lead_code)) != code:              # แถวเก่าที่ลงไปโดยไม่มี /n → ซ่อมเลขให้เต็ม
            upd[L.lead_code] = code
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
    if fallback:
        res["fallback"] = fallback                              # แท็บที่ควรลง (ยังไม่มี) → process_pending จดไว้รอย้าย
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
    # ชื่อในชีตอาจไม่ใช่ชื่อเล่น (แท็บรายชื่อสมาชิกตั้ง "ใหม่" = ADMIN) — ถือว่าเป็นเจ้าของได้ทั้ง 2 ชื่อ
    sheet = member_name(ctx, uid=g.sender_id or "", nick=nick)
    names = [x for x in (nick, sheet) if x]
    nick = nick or sheet
    if not nick:
        # ข้อความหน้าตาเป็นรายงานผล แต่ไม่รู้ว่าใครส่ง = ลงชีตไม่ได้ → แจ้งเจ้าของ (เดิมข้ามเงียบ)
        return {"action": "report-noemp", "reporter": g.sender_name or "ไม่ทราบชื่อ",
                "label": p["code"] or p["run"], "why": "คนรายงานไม่อยู่ในทะเบียนพนักงาน"}
    at = timezone.localtime(g.sent_at or timezone.now())
    label = p["code"] or ("%s%s" % (p["run"], "/%d" % p["slash"] if p["slash"] else ""))
    for k in range(3):                                           # แท็บเดือนนี้ก่อน (เคสค้างถูกก๊อปมาเดือนใหม่)
        t = ctx.tab(tab_name(_prev(at.date(), k)))
        if t is None:
            continue
        rows = (t.find(p["code"]) + t.find_legacy(p["code"])) if p["code"] else []
        if not rows:
            rows = t.by_run(p["run"], None, p["month"] or None)
            if p["slash"]:
                # ระบุ /n มา = เลือกแถวที่ /n ตรงก่อน · ไม่มี (แถวไม้ 2 ที่ลงไว้โดยไม่มี /n 14–15 ต.ค.69) = ทุกแถวของเลขนี้
                exact = [(n, r) for n, r in rows if _slash_of(t.val(r, L.lead_code)) == p["slash"]]
                rows = exact or rows
        if not rows:
            continue
        # ★ เลขลีดซ้ำในชีตได้ (เลขเดิม → ไม้ 2 · จ่ายใหม่ · ก๊อปเคสค้างมาเดือนใหม่) → **ยึดแถวล่าสุด** (เจ้าของสั่ง 15 ต.ค.69)
        #   แถวล่างสุดของแท็บใหม่สุดที่เจอเลขนี้ = เคสตอนนี้เป็นของใคร · เดิมเลือก "แถวของคนรายงาน" แม้เป็นแถวเก่า
        rows.sort(key=lambda x: x[0])
        n, r = rows[-1]
        seller = t.val(r, L.sales_rep)
        if seller and not _owner_rows(t, [(n, r)], names):
            return {"action": "not-owner", "code": label, "tab": t.title, "reporter": nick, "owner": seller,
                    "sheetRow": n, "rowCode": t.val(r, L.lead_code)}
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
    rows = ban_rows(g, ctx)
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
        settle_due = _fallback_due()
        if not msgs and not settle_due:
            return {"pending": 0}
        ctx = ctx or Ctx()
        try:
            ctx.lead_api()                                       # ต่อ Google ไม่ได้ = ไม่แตะตัวชี้เลย
        except Exception as e:
            err = ("%s: %s" % (type(e).__name__, e))[:300]
            _set_kv(KV_LAST, {"at": timezone.localtime().isoformat(timespec="seconds"), "error": err,
                              "processed": 0, "lastId": last_id})
            _log(False, error=err)
            alert([], failing=err)
            return {"error": err}
        items = []                                               # [(คีย์กันซ้ำ, ข้อความ, เตือนซ้ำทุกกี่นาที · 0 = ครั้งเดียว)]
        if settle_due:
            try:
                items += settle_fallback(ctx)
            except (SheetError, requests.RequestException) as e:
                items.append(("move-fail", "ย้ายใบจากแท็บเดิมไปแท็บเดือนใหม่ไม่สำเร็จ: %s (ลองใหม่ทุก %d นาที)"
                              % (str(e)[:200], FALLBACK_CHECK_MIN), ALERT_REPEAT_MIN))
            if not msgs:
                alert(items, failing="")                         # ต่อชีตได้ + ไม่มีอะไรค้าง = หายแล้ว
                return {"pending": 0}
        res = {"at": timezone.localtime().isoformat(timespec="seconds"), "processed": 0, "added": [],
               "updated": [], "dup": [], "reports": 0, "notOwner": [], "reportMiss": [], "bans": 0,
               "conflicts": [], "unknownSeller": [], "error": ""}
        fb_new = {}                                              # แท็บที่ควรลง → [ใบที่ลงแท็บเดิมรอบนี้]
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
            items += _alert_items(g, r)
            if a == "add":
                res["added"].append(r["code"])
                if r.get("conflict"):
                    res["conflicts"].append(r["conflict"])
                if "ไม่พบ" in (r.get("sellerFrom") or "") or not r.get("seller"):
                    res["unknownSeller"].append(r["code"])
                if r.get("fallback"):
                    _remember_fallback(r["fallback"], r["tab"], r["code"])
                    fb_new.setdefault((r["fallback"], r["tab"]), []).append(r["code"])
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
            elif a == "report-noemp":
                res.setdefault("reportNoEmp", []).append("%s (%s)" % (r["label"], r["reporter"]))
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
        for (want, tab), codes in fb_new.items():
            total = sum(1 for x in (_kv(KV_FALLBACK).get("rows") or []) if x.get("want") == want)
            items.append(("fb:" + want, 'ยังไม่มีแท็บ "%s" (หรือยังไม่มีหัวตาราง) — ลงแท็บ "%s" ไปก่อน %d ใบ (ล่าสุด %s) · '
                          "สร้างแท็บ %s เมื่อไหร่ ระบบย้ายไปให้เอง" % (want, tab, total, ", ".join(codes[-5:]), want),
                          FALLBACK_REMIND_MIN))
        if res["error"]:
            res["fallbackRows"] = len(_kv(KV_FALLBACK).get("rows") or [])
        col = _column_items(ctx)
        if col:
            res["columns"] = [x[1] for x in col][-10:]
        items += col
        _set_kv(KV_LAST, res)
        alert(items, failing=res["error"], pending=(pending_count() if res["error"] else 0))
        return res


# ════════════════════════════════════════════════════════════════════
# ขึ้นเดือนใหม่: ลงแท็บเดิมไปก่อน → ย้ายไปแท็บใหม่เมื่อแอดมินสร้าง
# ════════════════════════════════════════════════════════════════════
def _remember_fallback(want: str, tab: str, code: str):
    st = _kv(KV_FALLBACK)
    rows = [x for x in (st.get("rows") or []) if not (x.get("want") == want and x.get("code") == code)]
    rows.append({"want": want, "tab": tab, "code": code, "at": timezone.localtime().isoformat(timespec="seconds")})
    _set_kv(KV_FALLBACK, dict(st, rows=rows[-500:]))


def _fallback_due(now=None) -> bool:
    """มีใบรอย้าย และไม่ได้เช็คมาเกิน FALLBACK_CHECK_MIN นาที"""
    from django.utils.dateparse import parse_datetime
    st = _kv(KV_FALLBACK)
    if not st.get("rows"):
        return False
    t = parse_datetime(st.get("checkedAt") or "")
    return not t or (now or timezone.now()) - t >= timedelta(minutes=FALLBACK_CHECK_MIN)


def _in_month(val, want: str) -> bool:
    d = _parse_dmy(val)
    return bool(d) and tab_name(d) == want


def settle_fallback(ctx: Ctx) -> list:
    """แท็บเดือนใหม่มาแล้ว → ย้ายใบที่ลงแท็บเดิมไว้ไปต่อท้ายแท็บใหม่ (ทั้งแถว รวมช่องที่คนกรอกเพิ่มแล้ว)

    ย้ายด้วย cutPaste ของ Google (ค่า+รูปแบบไปครบ ไม่ต้องอ่านแล้วเขียนใหม่ = เบอร์ไม่เสีย 0 · วันที่ไม่เพี้ยน)
    แล้วลบแถวที่ว่างในแท็บเดิม — ทั้งหมดในคำขอเดียว (Google ทำทั้งชุดหรือไม่ทำเลย)

    ไม่แตะแถวที่: เลขนั้นมีในแท็บใหม่แล้ว (แอดมินก๊อปไปเอง) · หาแถวเดิมไม่เจอ · ว/ด/ป ไม่ใช่เดือนของแท็บใหม่
    → แถวที่ ว/ด/ป เป็นเดือนใหม่แต่อยู่แท็บเดิม แดชบอร์ดไม่นับ (กรองแถวตามเดือนของแท็บ) จึงต้องย้าย
    คืนรายการแจ้งเตือน [(คีย์, ข้อความ, เตือนซ้ำ)]
    """
    from dashboard.services.google_sheets import LEADS_COL as L
    st = _kv(KV_FALLBACK)
    rows = st.get("rows") or []
    if not rows:
        return []
    api = ctx.lead_api()
    props = api.props()
    keep, notes = [], []
    wants = []
    for x in rows:
        if x.get("want") not in wants:
            wants.append(x["want"])
    for want in wants:
        items = [x for x in rows if x.get("want") == want]
        new = None
        if want in props:
            try:
                new = LeadTab(api, want)
            except SheetError:
                new = None                                       # มีแท็บแล้วแต่ยังไม่มีหัวตาราง
        if new is None:
            keep += items
            continue
        olds, moves, skipped = {}, [], []
        for x in items:
            if new.find(x["code"]):
                skipped.append("%s (มีในแท็บใหม่แล้ว)" % x["code"])
                continue
            ot = olds.get(x["tab"])
            if ot is None and x["tab"] in props:
                try:
                    ot = olds[x["tab"]] = LeadTab(api, x["tab"])
                except SheetError:
                    ot = None
            hits = [n for n, r in (ot.find(x["code"]) if ot else []) if _in_month(ot.val(r, L.received_date), want)]
            if not hits:
                skipped.append("%s (หาแถวในแท็บ %s ไม่เจอ)" % (x["code"], x["tab"]))
                continue
            moves.append((x["tab"], hits[-1], x["code"]))
        if moves:
            dropped = _move_rows(api, props, moves, olds, new, want)
            _log(True, moved=[m[2] for m in moves], to=want, dropped=dropped)
            notes.append(("moved:%s:%s" % (want, ",".join(m[2] for m in moves)), 'แท็บ "%s" มาแล้ว — ย้ายใบที่ลงแท็บเดิมไว้ไปให้ %d ใบ: %s%s'
                          % (want, len(moves), ", ".join(m[2] for m in moves[:10]),
                             (" · แท็บใหม่จัดคอลัมน์ต่างจากแท็บเดิม ย้ายตามชื่อหัวคอลัมน์ (คอลัมน์ที่แท็บใหม่ไม่มี "
                              "ค่าไม่ได้ย้าย: %s)" % ", ".join(dropped)) if dropped else ""), 0))
        if skipped:
            notes.append(("moveskip:%s:%s" % (want, ",".join(skipped)), 'แท็บ "%s" มาแล้ว — ไม่ได้ย้าย %d ใบ: %s'
                          % (want, len(skipped), ", ".join(skipped[:10])), 0))
    _set_kv(KV_FALLBACK, {"rows": keep, "checkedAt": timezone.now().isoformat()})
    ctx.titles, ctx.tabs = None, {}                              # แถวเลื่อนแล้ว — อ่านใหม่
    return notes


def _hnorm(h) -> str:
    from dashboard.services.google_sheets import _norm_header
    return _norm_header(str(h or ""))


def _same_layout(old: LeadTab, new: LeadTab) -> bool:
    """หัวตารางแท็บเดิมตรงกับแท็บใหม่ทุกคอลัมน์ (แท็บใหม่มีคอลัมน์เพิ่มท้ายได้) = ตัดแปะทั้งแถวได้"""
    ha = [_hnorm(h) for h in old.header]
    while ha and not ha[-1]:
        ha.pop()
    hb = [_hnorm(h) for h in new.header]
    return bool(ha) and ha == hb[:len(ha)]


def _col_map(old: LeadTab, new: LeadTab) -> dict:
    """ลำดับคอลัมน์แท็บเดิม → แท็บใหม่: ชื่อหัวคอลัมน์ตรงกันก่อน แล้วช่องที่ระบบรู้จัก (ชื่อเรียกต่างกันได้)"""
    hn = {}
    for j, h in enumerate(new.header):
        if _hnorm(h) and _hnorm(h) not in hn:
            hn[_hnorm(h)] = j
    out, used = {}, set()
    for i, h in enumerate(old.header):
        j = hn.get(_hnorm(h)) if _hnorm(h) else None
        if j is not None and j not in used:
            out[i] = j
            used.add(j)
    for f, i in old.cm.items():
        j = new.cm.get(f)
        if i not in out and j is not None and j not in used:
            out[i] = j
            used.add(j)
    return out


def _move_rows(api, props: dict, moves: list, olds: dict, new: LeadTab, want: str) -> list:
    """ย้ายแถว [(แท็บเดิม, แถว, Code)] ไปต่อท้ายแท็บ `want` แล้วลบแถวเดิม · คืนหัวคอลัมน์ที่แท็บใหม่ไม่มี (ค่าไม่ได้ย้าย)

    หัวตารางตรงกัน = cutPaste + ลบ ในคำขอเดียว (ค่า+รูปแบบไปครบ) ·
    ★ ไม่ตรงกัน (แท็บใหม่จัดคอลัมน์ใหม่) = ตัดแปะทั้งแถวจะลงผิดช่อง → เขียนค่าตามชื่อหัวคอลัมน์ แล้วค่อยลบแถวเดิม
    """
    dest, assign = new.last + 1, {}
    for m in sorted(moves, key=lambda m: (m[0], m[1])):         # เรียงตามเดิม (เก่าก่อน) → ต่อท้ายตามลำดับ
        assign[m] = dest
        dest += 1
    Ctx._room(api, props, want, dest - 1)
    if not all(_same_layout(olds[m[0]], new) for m in moves):
        cells, dropped = {}, set()
        for m in moves:
            ot = olds[m[0]]
            cmap = _col_map(ot, new)
            row = ot.rows[m[1] - 2] if 0 <= m[1] - 2 < len(ot.rows) else []
            for i, v in enumerate(row):
                if not str(v).strip():
                    continue
                j = cmap.get(i)
                if j is None:
                    dropped.add((str(ot.header[i]).strip() if i < len(ot.header) else "") or _col(i))
                    continue
                cells["%s!%s%d" % (_q(want), _col(j), assign[m])] = _t(v) if isinstance(v, str) else v
        if cells:
            api.write(cells, "ย้ายใบไป %s (ตามชื่อหัวคอลัมน์)" % want)
        api.batch([{"deleteDimension": {"range": {"sheetId": props[m[0]]["id"], "dimension": "ROWS",
                                                  "startIndex": m[1] - 1, "endIndex": m[1]}}}
                   for m in sorted(moves, key=lambda m: (m[0], -m[1]))], "ลบแถวที่ย้ายแล้วจากแท็บเดิม")
        return sorted(dropped) or ["(ไม่มี — แค่ลำดับคอลัมน์ต่างกัน)"]
    reqs = []
    for m in sorted(moves, key=lambda m: (m[0], -m[1])):        # ลบจากล่างขึ้นบน — แถวข้างบนไม่เลื่อน
        ncol = max(len(olds[m[0]].header), 1)
        reqs.append({"cutPaste": {
            "source": {"sheetId": props[m[0]]["id"], "startRowIndex": m[1] - 1, "endRowIndex": m[1],
                       "startColumnIndex": 0, "endColumnIndex": ncol},
            "destination": {"sheetId": props[want]["id"], "rowIndex": assign[m] - 1, "columnIndex": 0},
            "pasteType": "PASTE_NORMAL"}})
        reqs.append({"deleteDimension": {"range": {"sheetId": props[m[0]]["id"], "dimension": "ROWS",
                                                   "startIndex": m[1] - 1, "endIndex": m[1]}}})
    api.batch(reqs, "ย้ายใบจากแท็บเดิมไป %s" % want)
    return []


MOVE_TEST_TABS = ("ทดสอบย้ายแท็บ ต้นทาง (ลบได้)", "ทดสอบย้ายแท็บ ปลายทาง (ลบได้)")


def _del_tabs(props: dict, titles) -> list:
    """คำขอลบแท็บ — เรียงรหัสแท็บมากไปน้อย (ชุดปลอมในเทสต์ใช้ลำดับแท็บเป็นรหัส · ของจริงไม่สนลำดับ)"""
    ids = sorted((props[t]["id"] for t in titles if t in props), reverse=True)
    return [{"deleteSheet": {"sheetId": i}} for i in ids]


def move_selftest() -> list:
    """ลองย้ายแถวข้ามแท็บกับ **Google ของจริง** (manage.py leadsheet --test-month-move)

    สร้างแท็บชั่วคราว 2 แท็บ (หัวตารางก๊อปจากแท็บเดือนนี้) → ลงแถวตัวอย่าง 2 แถวที่ต้นทาง → ย้ายแถวที่ 2 ด้วยโค้ดตัวเดียวกับ
    ตอนขึ้นเดือนใหม่ (`_move_rows`) → อ่านกลับมาตรวจ → **ลบทั้ง 2 แท็บทิ้งเสมอ** · ไม่แตะแท็บเดือนจริง
    """
    from dashboard.services.google_sheets import LEADS_COL as L
    api = Ctx().lead_api()
    src, dst = MOVE_TEST_TABS
    out, ok_all = [], True

    def check(name, cond, extra=""):
        nonlocal ok_all
        ok_all = ok_all and bool(cond)
        out.append("%s %s%s" % ("ผ่าน" if cond else "ไม่ผ่าน", name, ("" if cond else " — %s" % extra)))

    props = api.props()
    old = _del_tabs(props, MOVE_TEST_TABS)
    if old:
        api.batch(old, "ลบแท็บทดสอบย้ายที่ค้าง")
        props = api.props()
    month = tab_name(timezone.localdate())
    if month not in props:
        raise SheetError("ไม่มีแท็บ %s ให้ก๊อปหัวตาราง" % month)
    hdr = (api.get("%s!A1:AH1" % _q(month)) or [[]])[0]
    api.batch([{"addSheet": {"properties": {"title": src, "gridProperties": {
                   "rowCount": 20, "columnCount": max(40, len(hdr) + 5)}}}},
               {"addSheet": {"properties": {"title": dst, "gridProperties": {      # ปลายทางมีแถวเดียว = ต้องขยายเอง
                   "rowCount": 1, "columnCount": max(40, len(hdr) + 5)}}}}], "สร้างแท็บทดสอบย้าย")
    try:
        for t in MOVE_TEST_TABS:
            api.write({"%s!%s1" % (_q(t), _col(i)): h for i, h in enumerate(hdr) if str(h).strip()},
                      "หัวตารางแท็บทดสอบย้าย")
        st = LeadTab(api, src)
        api.write(st.cells(2, {L.received_date: "31/10/2026", L.phone: _t("0811111111"), L.time: "'08:00",
                               L.lead_code: "TEST-KEEP-1", L.sales_rep: "ทดสอบ"}), "แถวตัวอย่าง (ต้องอยู่ที่เดิม)")
        api.write(st.cells(3, {L.received_date: "1/11/2026", L.phone: _t("0812345678"), L.time: "'09:05",
                               L.lead_code: "TEST-MOVE-1", L.sales_rep: "ทดสอบ", L.update_count: "2"}),
                  "แถวตัวอย่าง (ต้องถูกย้าย)")
        props = api.props()
        st, dt = LeadTab(api, src), LeadTab(api, dst)
        n = [k for k, _ in st.find("TEST-MOVE-1")]
        check("ลงแถวตัวอย่างที่แท็บต้นทาง", n == [3], n)
        _move_rows(api, props, [(src, 3, "TEST-MOVE-1")], {src: st}, dt, dst)
        st, dt = LeadTab(api, src), LeadTab(api, dst)
        moved = dt.find("TEST-MOVE-1")
        check("ย้ายไปแท็บปลายทางแถว 2 (ขยายตารางให้เอง)", [k for k, _ in moved] == [2], [k for k, _ in moved])
        r = moved[0][1] if moved else []
        check("เบอร์ไม่เสียเลข 0", dt.val(r, L.phone) == "0812345678", dt.val(r, L.phone))
        check("วันที่ไม่เพี้ยน (1 พ.ย. 2026)", _parse_dmy(dt.val(r, L.received_date)) == date(2026, 11, 1),
              dt.val(r, L.received_date))
        check("เวลา + ช่องอื่นไปครบ", (dt.val(r, L.time), dt.val(r, L.update_count)) == ("09:05", "2"),
              (dt.val(r, L.time), dt.val(r, L.update_count)))
        check("แถวที่ย้ายหายจากต้นทาง (ไม่เหลือแถวว่าง)", not st.find("TEST-MOVE-1") and st.last == 2, st.last)
        check("แถวอื่นในต้นทางอยู่ที่เดิม", [k for k, _ in st.find("TEST-KEEP-1")] == [2])
    finally:
        props = api.props()
        if _del_tabs(props, MOVE_TEST_TABS):
            api.batch(_del_tabs(props, MOVE_TEST_TABS), "ลบแท็บทดสอบย้าย")
        out.append("ลบแท็บทดสอบทั้ง 2 แท็บแล้ว")
    out.insert(0, "ผลรวม: %s" % ("ใช้ได้ — ขึ้นเดือนใหม่ย้ายใบจากแท็บเดิมได้จริง" if ok_all else "มีข้อที่ไม่ผ่าน — ส่งผลนี้ให้ Claude ดู"))
    return out


# ════════════════════════════════════════════════════════════════════
# แจ้งเตือนทาง LINE ส่วนตัวเจ้าของ — บันทึกชีตไม่ได้ / ข้อความที่ลงชีตไม่ได้ / ลงแท็บเดิม
# ════════════════════════════════════════════════════════════════════
def _alert_items(g, r: dict) -> list:
    """ผลของข้อความ 1 ข้อความ → รายการที่ต้องแจ้ง (คีย์ = เลขข้อความ → แจ้งครั้งเดียว)"""
    a, k = r.get("action"), "m%s" % g.id
    if a == "not-owner":
        return [(k, "รายงานผลไม่ลงชีต: %s — %s รายงาน แต่ในชีตเป็นเคสของ %s (พิมพ์เลขผิด?)"
                 % (r.get("code"), r.get("reporter"), r.get("owner")), 0)]
    if a == "report-miss":
        return [(k, "รายงานผลไม่ลงชีต: หาเลข %s ไม่เจอในแท็บ 3 เดือนล่าสุด (%s รายงาน)"
                 % (r.get("code"), r.get("reporter")), 0)]
    if a == "report-noemp":
        return [(k, "รายงานผลไม่ลงชีต: เลข %s — คนส่ง (%s) ไม่อยู่ในทะเบียนพนักงาน" % (r.get("label"), r.get("reporter")), 0)]
    if a == "parse-error":
        return [(k, "อ่านข้อความในห้องจ่ายเบอร์ไม่ได้ ข้ามไป: %s" % r.get("error", ""), 0)]
    if a == "ban-error":
        return [(k, "บันทึกรายงานแบนไม่ได้: %s" % r.get("error", ""), 0)]
    out = []
    if a == "add" and r.get("conflict"):
        out.append((k + "c", "ลงแถวใหม่แต่เลขซ้ำ: %s" % r["conflict"], 0))
    if a == "add" and ("ไม่พบ" in (r.get("sellerFrom") or "") or not r.get("seller")):
        out.append((k + "s", "ลงชีตแล้วแต่หาเซลล์ในทะเบียนไม่เจอ: %s (ช่องเซลล์ = %s)"
                    % (r.get("code"), r.get("seller") or "ว่าง"), 0))
    return out


def _alert_uid() -> str:
    """LINE id ของผู้รับแจ้งเตือน (ใช้ภายใน ไม่พิมพ์ออก) — ชื่อเล่นในทะเบียน → ชื่อที่ตั้งใน LINE"""
    from django.db.models import Q

    from .models import Employee, LineProfile
    names = [n for n in [get_config().get("alert_to")] + list(ALERT_TO) if n]
    for nm in names:
        e = (Employee.objects.filter(nickname__iexact=nm).first()
             or Employee.objects.filter(display_name__iexact=nm).first())
        if e is not None:
            p = LineProfile.objects.filter(employee=e).exclude(user_id="").order_by("-last_seen").first()
            if p:
                return p.user_id
        ps = list(LineProfile.objects.filter(Q(nickname__iexact=nm) | Q(display_name__iexact=nm), is_employee=True)
                  .exclude(user_id="").order_by("-last_seen")[:5])
        if ps and len({p.employee_id or p.user_id for p in ps}) == 1:
            return ps[0].user_id
    return ""


def alert_target() -> str:
    """ชื่อผู้รับที่ใช้อยู่ (ไว้โชว์ในสถานะ) — ไม่คืน LINE id"""
    from .models import LineProfile
    uid = _alert_uid()
    if not uid:
        return ""
    p = LineProfile.objects.filter(user_id=uid).select_related("employee").first()
    return (p.employee.nickname if p and p.employee_id else (p.display_name if p else "")) or "พบแล้ว"


def _send_alert(text: str, what: str = "แจ้งเตือนลงชีตจ่ายเบอร์") -> tuple:
    from dashboard.services import line_channels, line_notify
    uid = _alert_uid()
    if not uid:
        return False, "หา LINE ของผู้รับแจ้งเตือน (%s) ในทะเบียนไม่เจอ" % (get_config().get("alert_to") or ALERT_TO[0])
    tok = line_channels.dm_token()
    if not tok:
        return False, "ยังไม่ได้ตั้ง token ของบอทส่งข้อความ"
    st, body = line_notify.push_line_message(uid, [{"type": "text", "text": text[:4900]}], tok,
                                             what=what)
    return st == 200, ("" if st == 200 else "LINE %s: %s" % (st, str(body)[:200]))


def alert(items: list, failing: str | None = None, pending: int = 0, force: bool = False) -> dict:
    """จด log + ส่ง LINE ส่วนตัวเจ้าของ **รวมเป็นข้อความเดียวต่อรอบ** · กันซ้ำด้วยคีย์ใน KV_ALERT

    failing = ผลการบันทึกชีตรอบนี้ ("" = ได้ · ข้อความ = ไม่ได้ เตือนซ้ำทุก ALERT_REPEAT_MIN ·
              หายแล้วแจ้ง "กลับมาบันทึกได้แล้ว" ครั้งเดียว) · None = ไม่เกี่ยว (ตัวเฝ้าระบบ/สำเนาชีตเรียก)
    items = [(คีย์, ข้อความ, เตือนซ้ำทุกกี่นาที)] · 0 = ครั้งเดียวต่อคีย์
    **จด log ทุกครั้งที่มีเรื่อง แม้ปิดแจ้งเตือน LINE ไว้** (ปิดแค่การส่ง)
    """
    from django.utils.dateparse import parse_datetime
    st = _kv(KV_ALERT)
    sent = dict(st.get("sent") or {})
    now = timezone.now()

    def due(key, every):
        t = parse_datetime(sent.get(key) or "")
        return t is None or (every and now - t >= timedelta(minutes=every))

    lines, logs = [], []                                         # logs = [(สำเร็จ/ดี?, คีย์, ข้อความ)]
    if failing:
        if due("fail", ALERT_REPEAT_MIN):
            lines.append("บันทึกชีตไม่ได้: %s%s · ระบบลองใหม่ทุกนาที ข้อความไม่หาย"
                         % (failing[:200], (" — ค้าง %d ข้อความ" % pending) if pending else ""))
            logs.append((False, "fail", lines[-1]))
            sent["fail"] = now.isoformat()
        st["failing"] = failing[:300]
    elif failing is not None and st.get("failing"):
        lines.append("กลับมาบันทึกชีตได้แล้ว (ข้อความที่ค้างลงครบ)")
        logs.append((True, "recovered", lines[-1]))
        st["failing"] = ""
        sent.pop("fail", None)
    for key, text, every in items:
        if due(key, every):
            lines.append(text)
            logs.append((key.startswith(("moved:", "wd:healed")), key, text))
            sent[key] = now.isoformat()
    for good, key, text in logs:
        _log_event(good, key, text)
    keep_after = now - timedelta(days=7)
    sent = {k: v for k, v in sent.items() if (parse_datetime(v) or now) >= keep_after}
    st["sent"] = sent
    out = {}
    if lines and (get_config().get("alert", True) or force):
        head = "[ลงชีตจ่ายเบอร์] %s" % timezone.localtime(now).strftime("%d/%m %H:%M")
        ok, err = _send_alert(head + "\n" + "\n".join("- " + x for x in lines[:20])
                              + ("\n(และอีก %d เรื่อง)" % (len(lines) - 20) if len(lines) > 20 else ""))
        out = {"at": timezone.localtime(now).isoformat(timespec="seconds"), "ok": ok, "error": err, "n": len(lines)}
        st["lastSend"] = out
        if not ok:
            log.warning("leadsheet: แจ้งเตือนไม่ถึง — %s", err)
    _set_kv(KV_ALERT, st)
    return out


def alert_test() -> dict:
    """ส่งข้อความทดสอบหาผู้รับแจ้งเตือน (manage.py leadsheet --alert-test)"""
    ok, err = _send_alert("[ลงชีตจ่ายเบอร์] ทดสอบแจ้งเตือน — ถ้าบันทึกชีตไม่ได้หรือมีรายงานผลที่ลงชีตไม่ได้ "
                          "จะแจ้งมาที่แชทนี้")
    return {"ok": ok, "error": err, "to": alert_target()}


def _log_event(ok: bool, key: str, text: str):
    """1 เรื่อง = 1 แถวใน dash_event_log (kind=leadsheet) — ไม่ให้การจด log ทำงานหลักพัง"""
    try:
        from dashboard.services import eventlog
        eventlog.log(eventlog.LEADSHEET, name=WHAT, target=key[:64], ok=ok, text=text[:1000])
    except Exception:
        pass


def safe_process(source: str = "") -> dict:
    """เรียก process_pending แบบ **ห้ามพังเงียบ** — เดิมงานเบื้องหลัง (cron/webhook/kick) ห่อ `except: pass`
    ระบบลงชีตพังกะทันหัน (บั๊ก/ฐานข้อมูลล่ม) = ไม่มีใครรู้ → ตอนนี้จด log + แจ้งเจ้าของ (ข้อความไม่หาย ตัวชี้ไม่ขยับ)"""
    try:
        return process_pending()
    except Exception as e:
        err = ("%s: %s" % (type(e).__name__, e))[:300]
        log.exception("leadsheet: process_pending ล้ม (%s)", source)
        try:
            alert([("crash:" + err[:80], "ระบบลงชีตล้มกะทันหัน (%s): %s · ข้อความไม่หาย รอบหน้าลองใหม่"
                    % (source or "-", err), ALERT_REPEAT_MIN)])
        except Exception:
            log.exception("leadsheet: แจ้งเตือนล้ม")
            _log_event(False, "crash", err)
        return {"error": err}


def watchdog_check(now=None) -> list:
    """ตรวจว่าระบบลงชีต "ยังเดินอยู่" — คืนรายการแจ้งเตือน (ไม่ส่งเอง) · ตัวแจ้งเตือนปกติทำงานใน process_pending
    ถ้าไม่มีอะไรมาเรียก process_pending เลย (cron หยุด + ข้อความไม่เข้า) มันก็เงียบ — ตัวนี้จึงต้องอยู่นอกเส้นทางนั้น

    1. cron (ตัวปลุกงานทุกนาทีจาก n8n) หยุด
    2. ข้อความค้างไม่ได้ลงชีตเกิน STUCK_MIN → **ลองลงเองก่อน** (refresh เอง) แล้วแจ้งผล
    3. ช่วงทำงาน ไม่มีข้อความจากห้องจ่ายเบอร์เข้าเลยเกิน QUIET_MIN = ตัวส่งต่อ LINE (n8n) น่าจะหยุด
    """
    from django.utils.dateparse import parse_datetime

    from dashboard.services.cache_store import get_kv

    from .models import GroupChat
    if not get_config()["enabled"]:
        return []
    now = now or timezone.now()
    items = []
    ct = get_kv("cron_tick") or {}
    at = parse_datetime(str(ct.get("updated_at") or "").replace("Z", "+00:00"))
    if at and now - at > timedelta(minutes=CRON_STALE_MIN):
        items.append(("wd:cron", "ตัวปลุกงานทุกนาที (cron จาก n8n) ไม่ทำงานมา %d นาที — ชีตยังลงจากข้อความ LINE ที่เข้ามาได้ "
                      "แต่งานเก็บตก/แจ้งเตือนอื่นหยุด · ตรวจ n8n" % ((now - at).total_seconds() // 60), ALERT_REPEAT_MIN))
    stuck = pending_count(STUCK_MIN)
    if stuck and not _kv(KV_ALERT).get("failing"):                # กำลังบันทึกไม่ได้ = แจ้งไปแล้วทางนั้น
        res = safe_process("ตัวเฝ้าระบบ")
        left = pending_count(STUCK_MIN)
        if left:
            items.append(("wd:stuck", "มีข้อความค้างไม่ได้ลงชีต %d รายการเกิน %d นาที — ระบบลองลงเองแล้วยังไม่ได้ (%s)"
                          % (left, STUCK_MIN, res.get("error") or res.get("skipped") or "ไม่ทราบสาเหตุ"),
                          ALERT_REPEAT_MIN))
        elif not res.get("error"):
            items.append(("wd:healed:" + timezone.localtime(now).strftime("%Y%m%d%H%M"),
                          "มีข้อความค้างไม่ได้ลงชีต %d รายการ (งานปกติไม่ได้ทำงาน) — ระบบลงให้เองแล้ว" % stuck, 0))
    local = timezone.localtime(now)
    if QUIET_HOURS[0] <= local.hour < QUIET_HOURS[1]:
        last = (GroupChat.objects.filter(chat_type=GroupChat.GROUP, group_id__in=_rooms(), direction=GroupChat.IN)
                .order_by("-sent_at").values_list("sent_at", flat=True).first())
        # นับจากข้อความล่าสุด หรือ 10:00 ของวันนี้ (อันที่หลังกว่า) — ไม่งั้น 10:00 ทุกเช้าจะแจ้งเพราะข้อความล่าสุดคือเมื่อคืน
        start = local.replace(hour=QUIET_HOURS[0], minute=0, second=0, microsecond=0)
        ref = max(last, start) if last else None
        if ref and now - ref > timedelta(minutes=QUIET_MIN):
            items.append(("wd:quiet", "ไม่มีข้อความจากห้องจ่ายเบอร์เข้าระบบตั้งแต่ %s (%d นาที · ช่วงทำงาน) — ตัวส่งต่อข้อความ "
                          "LINE (n8n) อาจหยุด ชีตจะไม่ลงจนกว่าจะกลับมา"
                          % (timezone.localtime(ref).strftime("%H:%M"), (now - ref).total_seconds() // 60), 180))
    return items


_WD = {"pid": 0, "leader": False}


def _wd_leader() -> bool:
    """ตัวเฝ้าระบบทำงานจริงแค่ worker เดียว — ถือ advisory lock ไว้ตลอดอายุ connection ของเธรดนี้"""
    from django.db import connection
    if connection.vendor != "postgresql":
        return True
    with connection.cursor() as cur:
        if _WD["leader"]:
            cur.execute("SELECT 1")                              # connection หลุด = lock หลุด → โยน error ไปขอใหม่
            return True
        cur.execute("SELECT pg_try_advisory_lock(%s)", [WD_LOCK_KEY])
        _WD["leader"] = bool(cur.fetchone()[0])
    return _WD["leader"]


def start_watchdog():
    """เริ่มตัวเฝ้าระบบในเธรดแยก (เรียกจาก CheckoutConfig.ready เฉพาะใต้ gunicorn) — ไม่ขึ้นกับ n8n/cron"""
    import os
    if _WD["pid"] == os.getpid():                                # fork แล้วเธรดไม่ตามมา → เทียบ pid ไม่ใช่แค่ธง
        return False
    _WD["pid"], _WD["leader"] = os.getpid(), False

    def loop():
        import random
        import time
        time.sleep(60 + random.random() * 60)                    # ให้เว็บเปิดเสร็จก่อน · worker ไม่ชนกัน
        while True:
            try:
                if _wd_leader():
                    items = watchdog_check()
                    _set_kv(KV_WD, {"at": timezone.localtime().isoformat(timespec="seconds"), "pid": os.getpid(),
                                    "issues": [t for _k, t, _e in items]})
                    if items:
                        alert(items)
            except Exception:
                log.exception("leadsheet watchdog")
                _WD["leader"] = False
                try:
                    from django.db import connection
                    connection.close()
                except Exception:
                    pass
            time.sleep(WD_EVERY_SEC)

    threading.Thread(target=loop, daemon=True, name="leadsheet-watchdog").start()
    return True


def recent_log(days: int = 3, limit: int = 100) -> list:
    """log ของระบบลงชีตย้อนหลัง (ใหม่ก่อน) — เรื่องที่แจ้ง · ล้ม · ผลส่งแจ้งเตือน"""
    from django.db.models import Q

    from dashboard.models import EventLog
    since = timezone.now() - timedelta(days=days)
    q = (Q(kind="leadsheet") | Q(kind="cron", name=WHAT) | Q(kind="cron", name="สำเนาชีตจ่ายเบอร์ลง Postgres")
         | Q(kind="line_send", name="แจ้งเตือนลงชีตจ่ายเบอร์"))
    out = []
    for e in EventLog.objects.filter(q, at__gte=since).order_by("-at")[:limit]:
        d = e.detail or {}
        text = d.get("text") or d.get("error") or ", ".join("%s=%s" % (k, v) for k, v in d.items())
        if e.kind == "line_send":
            text = ("ส่งแจ้งเตือน LINE ถึงแล้ว" if e.ok else
                    "ส่งแจ้งเตือน LINE ไม่ถึง: %s" % (d.get("error") or d.get("status") or "-"))
        out.append({"at": timezone.localtime(e.at).strftime("%d/%m %H:%M"), "ok": e.ok, "kind": e.kind,
                    "text": str(text)[:500]})
    return out


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
            safe_process("ระบบส่งใบ")
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
        return safe_process("ข้อความ LINE เข้า")
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


def fix_member_names(tabs: list | None = None, apply: bool = False, ctx: Ctx | None = None) -> dict:
    """แถวที่ช่องเซลล์เป็นชื่อเล่นในทะเบียน แต่แท็บรายชื่อสมาชิกตั้งชื่อในชีตไว้อีกแบบ (เช่น "ใหม่" → ADMIN) → แก้ให้ตรง

    เขียนเฉพาะช่องเซลล์ · แก้เฉพาะชื่อที่เป็นชื่อเล่นในทะเบียนตรงตัว (ชื่ออื่นที่คนพิมพ์เองไม่แตะ) · ไม่ใส่ apply = ดูเฉยๆ
    """
    from dashboard.services.google_sheets import LEADS_COL as L

    from .models import Employee
    ctx = ctx or Ctx(write=apply)
    today = timezone.localdate()
    tabs = tabs or [tab_name(today), tab_name(_prev(today))]
    nicks = set(Employee.objects.values_list("nickname", flat=True))
    want = {}
    out = {"tabs": [], "fix": [], "applied": 0}
    for title in tabs:
        t = ctx.tab(title)
        if t is None:
            out["tabs"].append({"tab": title, "error": "ไม่มีแท็บนี้"})
            continue
        fixes = {}
        for i, r in enumerate(t.rows):
            s = t.val(r, L.sales_rep)
            if not s or s not in nicks:
                continue
            if s not in want:
                want[s] = member_name(ctx, nick=s)
            to = want[s]
            if to and to != s:
                fixes[i + 2] = to
                out["fix"].append({"tab": title, "row": i + 2, "code": t.val(r, L.lead_code), "from": s, "to": to})
        out["tabs"].append({"tab": title, "fix": len(fixes)})
        if apply and fixes:
            cells = {}
            for n, to in fixes.items():
                cells.update(t.cells(n, {L.sales_rep: to}))
            ctx.lead_api().write(cells, "แก้ชื่อเซลล์ตามแท็บรายชื่อสมาชิก แท็บ %s" % title)
            out["applied"] += len(fixes)
    if apply:
        _log(True, fixedNames=out["applied"], tabs=tabs)
    return out


BUG_SLASH_START = date(2026, 10, 14)     # วันที่ระบบนี้เริ่มลงชีตแทน n8n (แถวไม้ 2 ลงโดยไม่มี /n ตั้งแต่วันนี้)
_R_NO_SLASH = re.compile(r"^R[A-Z]*\d{1,2}-\d{3,6}$")


def fix_slash_codes(tabs: list | None = None, apply: bool = False, ctx: Ctx | None = None,
                    redo_reports: bool = True, days: int = 70) -> dict:
    """ซ่อมแถวไม้ 2 ที่ลงไว้โดยไม่มี "/n" (บั๊ก 14–15 ต.ค.69: `RNLD10-8286` แทน `RNLD10-8286/1`)

    1. หาแถวที่ Code ขึ้นต้น R ไม่มี "/" → หาใบจ่ายลีดต้นฉบับในคลังแชทห้องจ่ายเบอร์ (เลขฐานตรงกัน) →
       ใบมี /n = แก้ช่อง Code ให้เป็นเลขเต็ม · ไม่เจอใบ / ใบไม่มี /n / มีแถวเลขเต็มอยู่แล้ว = ไม่แตะ (รายงานให้ดู)
    2. (`redo_reports`) รายงานผล "8286/1 …" ที่ส่งตั้งแต่ BUG_SLASH_START แล้วหาแถวไม่เจอเพราะเลขขาด /n
       → ลงให้ใหม่ด้วยเวลาเดิมของข้อความ (ก่อนแก้หาแถวไม่เจอแน่นอน = ไม่นับซ้ำ)
    ไม่ใส่ apply = ดูเฉยๆ · ต้องรันบนเซิร์ฟเวอร์ (คลังแชทอยู่ที่นั่น)
    """
    from dashboard.services.google_sheets import LEADS_COL as L

    from .leadgroup import parse_leadsheet
    from .models import GroupChat
    ctx = ctx or Ctx(write=apply)
    today = timezone.localdate()
    tabs = tabs or [tab_name(today), tab_name(_prev(today))]
    out = {"tabs": [], "fix": [], "skip": [], "applied": 0, "reports": [], "reportsApplied": 0}

    # ใบจ่ายลีดที่มี /n ในห้องจ่ายเบอร์ → {เลขฐาน: {เลขเต็ม}}
    since = timezone.now() - timedelta(days=days)
    full_of: dict = {}                                           # เลขฐาน → [เลขเต็ม ตามลำดับเวลาใบ]
    qs = (GroupChat.objects.filter(chat_type=GroupChat.GROUP, group_id__in=_rooms(), sent_at__gte=since,
                                   text__icontains="lead")
          .only("text").order_by("sent_at", "id"))
    for g in qs.iterator():
        d = parse_leadsheet(g.text or "")
        if d and d.get("lead_slash"):
            lst = full_of.setdefault(_code_key(d["lead_code"]), [])
            full = _code_key(d["lead_code_full"])
            if full in lst:
                lst.remove(full)
            lst.append(full)

    fixed_runs = {}                                              # เลขรัน → [(แท็บ, แถว)] ที่แก้แล้ว
    for title in tabs:
        t = ctx.tab(title)
        if t is None:
            out["tabs"].append({"tab": title, "error": "ไม่มีแท็บนี้"})
            continue
        cells, nfix = {}, 0
        for i, r in enumerate(t.rows):
            code = _code_key(t.val(r, L.lead_code))
            if not _R_NO_SLASH.match(code):
                continue
            n = i + 2
            fulls = full_of.get(code) or []
            item = {"tab": title, "row": n, "code": code, "seller": t.val(r, L.sales_rep),
                    "date": t.val(r, L.received_date)}
            if not fulls:
                item["why"] = "ไม่พบใบจ่ายลีดที่มี /n"
                out["skip"].append(item)
                continue
            full = fulls[-1]                                     # ใบหลายเลข (/1 แล้ว /2) = ยึดใบล่าสุด
            if t.find(full):
                item["note"] = "มีแถว %s อยู่แล้ว — เลขซ้ำได้ ยึดแถวล่าสุด" % full
            item["to"] = full
            out["fix"].append(item)
            cells.update(t.cells(n, {L.lead_code: full}))
            t.remember(n, {L.lead_code: full})                  # รอบเดียวกัน (ลงรายงานใหม่) เห็นเลขเต็มแล้ว
            m = _RUN.search(full)
            fixed_runs.setdefault(m.group(1), []).append((title, n))
            nfix += 1
        out["tabs"].append({"tab": title, "fix": nfix})
        if apply and cells:
            ctx.lead_api().write(cells, "ซ่อมเลขไม้ 2 (เติม /n) แท็บ %s" % title)
            out["applied"] += nfix

    if redo_reports and fixed_runs:
        start = timezone.make_aware(datetime.combine(BUG_SLASH_START, datetime.min.time()))
        msgs = (GroupChat.objects.filter(chat_type=GroupChat.GROUP, group_id__in=_rooms(), msg_type="text",
                                         direction=GroupChat.IN, sent_at__gte=start)
                .order_by("sent_at", "id"))
        for g in msgs.iterator():
            p = parse_report(g.text or "")
            if not p or not p["slash"] or p["run"] not in fixed_runs:
                continue
            try:
                res = handle_report(g, p, ctx)
            except SheetError as e:
                res = {"action": "error", "error": str(e)[:160]}
            res["at"] = timezone.localtime(g.sent_at).strftime("%d/%m %H:%M") if g.sent_at else ""
            res["text"] = (g.text or "")[:60]
            out["reports"].append(res)
            if apply and res.get("action") == "report":
                out["reportsApplied"] += 1
    if apply:
        _log(True, fixedSlash=out["applied"], redoReports=out["reportsApplied"], tabs=tabs)
    return out


def status() -> dict:
    st, last = _kv(KV_STATE), _kv(KV_LAST)
    al = _kv(KV_ALERT)
    return {"config": get_config(), "cursor": st.get("last_id"), "cursorAt": st.get("at"),
            "rooms": len(_rooms()), "pending": pending_count(), "last": last,
            "fallback": _kv(KV_FALLBACK).get("rows") or [], "alertTo": alert_target(),
            "alertLast": al.get("lastSend") or {}, "failing": al.get("failing") or "", "watchdog": _kv(KV_WD)}


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
    # เทียบเป็น "วันที่" ไม่ใช่ตัวอักษร — เราเขียน 13/10/2026 แต่แท็บเดือนจริงตั้งรูปแบบคอลัมน์โชว์ 13/10/26
    #   (เทียบตัวอักษรเคยขึ้น "ถูกทับ ✗" หลอกตอนลองบน prod 13 ต.ค.69 ทั้งที่เป็นวันเดียวกัน)
    same = _parse_dmy(after) is not None and _parse_dmy(after) == _parse_dmy(a_before)
    out.append("ว/ด/ป ก่อนรายงาน = %s · หลังรายงาน = %s → %s" % (
        a_before, after, "ไม่ถูกทับ ✓ (วันเดียวกัน)" if same else "ถูกทับ ✗"))
    return out
