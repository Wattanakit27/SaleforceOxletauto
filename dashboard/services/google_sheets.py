"""Google Sheets API — ported from lib/google-sheets.ts"""
import concurrent.futures
import time
from typing import Any

import requests
from google.auth.transport.requests import Request as AuthRequest
from google.oauth2.service_account import Credentials
from django.conf import settings


# ── In-memory cache สำหรับ Sheet reads ──
# ลด API quota hits — TTL 60s ก็พอดี (data ไม่ได้ update วินาทีต่อวินาที)
# Module-level dict → persist ใน warm Vercel instance (cold start จะ reset)
# Invalidate ด้วย invalidate_cache(key) ตอน write_sheet (ดู write_sheet ด้านล่าง)
_CACHE_TTL = 60  # seconds
_CACHE: dict[str, tuple[float, Any]] = {}  # key → (timestamp, data)


def _cache_get(key: str):
    entry = _CACHE.get(key)
    if not entry:
        return None
    ts, data = entry
    if time.time() - ts > _CACHE_TTL:
        _CACHE.pop(key, None)
        return None
    return data


def _cache_set(key: str, data):
    _CACHE[key] = (time.time(), data)


def invalidate_cache(key: str | None = None):
    """ล้าง cache — ถ้าใส่ key = ล้างแค่ key นั้น, None = ล้างทั้งหมด"""
    if key is None:
        _CACHE.clear()
    else:
        _CACHE.pop(key, None)

# ── Config: Sheet IDs & tab names ──
SHEET_CONFIG = {
    "leads": {
        "spreadsheet_id": "1s9FFPRV53U7pQTnBGSlkSFL8ygmRGRGYOAG1HakzgA0",
        "sheet_name": "รวม sheet",
    },
    "sales_reports": {
        "spreadsheet_id": "13_vFkHEZWRAzxZiJ1Uj-NPlzlZtptyXuIjdxkGqlg8Y",
        "sheet_name": "รวม sheet",
    },
    "bookings": {
        "spreadsheet_id": "13jiQTOvcCvlKLGvjrb348_iRWoiMpumqqeEgOTkTgB0",
        "sheet_name": "รวม sheet",
    },
    "live_sessions": {
        "spreadsheet_id": "18Djos3lUJnoZ00gYEBuCCExwm1YknfIQrP-TIuUgjWU",
        "sheet_name": "รวม sheet",
    },
    "live_followups": {
        "spreadsheet_id": "18Djos3lUJnoZ00gYEBuCCExwm1YknfIQrP-TIuUgjWU",
        "sheet_name": "ติดตามไลฟ์สด",
    },
    "employees": {
        "spreadsheet_id": "1HOhrPSIFTxfOpc4UWvKb-LfMuXGYW2vYkR5vbGzPd_A",
        "sheet_name": "เก็บข้อมูลพนักงาน กลุ่ม หลัก",
    },
    "sellers_config": {
        "spreadsheet_id": "1HOhrPSIFTxfOpc4UWvKb-LfMuXGYW2vYkR5vbGzPd_A",
        "sheet_name": "ตั้งค่าเซลล์",
    },
    "schedule_config": {
        "spreadsheet_id": "1HOhrPSIFTxfOpc4UWvKb-LfMuXGYW2vYkR5vbGzPd_A",
        "sheet_name": "ตั้งเวลาส่ง",
    },
    "admin_config": {   # รายชื่อ LINE user_id ที่เป็นแอดมิน (ออฟฟิศ/คนที่ไม่ใช่เซลล์ใน TEAMS) — มีสิทธิ์แอดมิน
        "spreadsheet_id": "1HOhrPSIFTxfOpc4UWvKb-LfMuXGYW2vYkR5vbGzPd_A",
        "sheet_name": "ตั้งค่าแอดมิน",
    },
    "tele_config": {   # รายชื่อ LINE user_id ของเทเลเซลล์ (ทีมโทร) — เคสรวมเป็น seller "ADMIN" · ไม่ใช่สิทธิ์แอดมิน
        "spreadsheet_id": "1HOhrPSIFTxfOpc4UWvKb-LfMuXGYW2vYkR5vbGzPd_A",
        "sheet_name": "ตั้งค่าเทเลเซลล์",
    },
    "onhand_config": {   # ONHAND รายสัปดาห์ (แอดมินพิมพ์เอง) — ต่อเซลล์: onhand/onhand หน้า/เป้าจองหน้า/เคสติดตาม
        "spreadsheet_id": "1HOhrPSIFTxfOpc4UWvKb-LfMuXGYW2vYkR5vbGzPd_A",
        "sheet_name": "ONHAND รายสัปดาห์",
    },
    "seller_flags": {   # สีโฟกัสแถวเซลล์ (แอดมินตั้งเอง) — เซลล์ | สี (y=เหลือง, r=แดง)
        "spreadsheet_id": "1HOhrPSIFTxfOpc4UWvKb-LfMuXGYW2vYkR5vbGzPd_A",
        "sheet_name": "โฟกัสเซลล์",
    },
    "leadscore": {
        "spreadsheet_id": "1HOhrPSIFTxfOpc4UWvKb-LfMuXGYW2vYkR5vbGzPd_A",
        "sheet_name": "leadscore",
    },
    "lead_score_config": {
        "spreadsheet_id": "1HOhrPSIFTxfOpc4UWvKb-LfMuXGYW2vYkR5vbGzPd_A",
        "sheet_name": "เกณฑ์คะแนน lead",
    },
    "ban_report": {   # log การโดนแบน (1 แถว = 1 ครั้ง) — ใช้ในคะแนนเซลล์ส่วน "โดนแบน"
        "spreadsheet_id": "18Djos3lUJnoZ00gYEBuCCExwm1YknfIQrP-TIuUgjWU",
        "sheet_name": "รายงานแบน",
    },
}

# คอลัมน์ tab "รายงานแบน": banDate|time|seller|sellerDisplay|banType|reason|bannedBy|unbanDate|status|...
class BAN_COL:
    ban_date = 0; time = 1; seller = 2; seller_display = 3
    ban_type = 4; reason = 5; banned_by = 6; unban_date = 7; status = 8

# ── Column index maps (0-based) ──
class LEADS_COL:
    received_date = 0; phone = 1; time = 2; lead_code = 3; sales_rep = 4
    live_team = 5; admin = 6; channel = 7; branch = 8; type = 9; ads = 10
    car_inquiry = 11; car_formula = 12; call_proof = 13; focus = 14
    contact_datetime = 15; update_count = 16; last_updated_at = 17
    fill_sheet_note = 18; customer_profile = 19; customer_profile_1 = 20
    customer_profile_2 = 21; customer_profile_3 = 22; date2 = 23
    status = 24; admin_survey = 25; admin_status = 26; _skip = 27
    sales_status = 28; case_update_1 = 29; case_update_2 = 30
    case_update_3 = 31; final_status = 32
    # คอลัม Z "สถานะลูกค้า" (layout ใหม่ มิ.ย.69+) — canonical slot ใหม่
    # ไม่ทับ index เดิม. normalize ยัดค่ามาที่นี่ผ่าน header matching
    customer_status = 33
    # คอลัม U–Y (layout ใหม่) — profile ที่เซลล์กรอกได้ (canonical slot ใหม่ map ตามหัวตาราง)
    occupation = 34        # U อาชีพ
    income = 35            # V รายได้
    job_tenure = 36        # W อายุงาน
    payment_history = 37   # X ประวัติการผ่อน
    customer_type = 38     # Y ประเภทลูกค้า

# ── Header-based column mapping (กันคอลัมน์ย้าย) ──
# ชีต lead เรียงคอลัมน์ไม่เหมือนกันในแต่ละเดือน (เช่น มิ.ย.69 ย้ายสถานะมาคอลัม Z)
# เลยไม่ fix ตำแหน่งตายตัว แต่จับคู่ field กับ "ชื่อหัวตาราง" แทน → เดือนไหน layout ไหนก็อ่านถูก
# alias เขียนเป็นภาษาคนได้เลย (เว้นวรรค/ขึ้นบรรทัด/พิมพ์เล็กใหญ่ ไม่สำคัญ — _norm_header ตัดทิ้ง)
_LEAD_FIELD_ALIASES = [
    (LEADS_COL.received_date, ["ว/ด/ป", "วันที่", "วดป"]),
    (LEADS_COL.phone, ["เบอร์โทร", "เบอร์"]),
    (LEADS_COL.time, ["เวลา"]),
    (LEADS_COL.lead_code, ["Code"]),
    (LEADS_COL.sales_rep, ["เซลล์"]),
    (LEADS_COL.live_team, ["ทีมไลฟ์"]),
    (LEADS_COL.admin, ["Admin"]),
    (LEADS_COL.channel, ["ช่องทาง"]),
    (LEADS_COL.branch, ["สาขา"]),
    (LEADS_COL.type, ["type"]),
    (LEADS_COL.ads, ["ADS"]),
    (LEADS_COL.car_inquiry, ["รถลูกค้าถาม"]),
    (LEADS_COL.car_formula, ["CAR / สูตร", "CAR/สูตร"]),
    (LEADS_COL.call_proof, ["แจ้งหลักฐานการโทร", "แจ้งหลักฐาน การโทร"]),
    (LEADS_COL.focus, ["FOCUS"]),
    (LEADS_COL.contact_datetime, ["วัน เวลา ที่ติดต่อ"]),
    (LEADS_COL.update_count, ["จำนวนอัพเดท"]),
    (LEADS_COL.last_updated_at, ["วัน เวลา อัพเดทล่าสุด"]),
    (LEADS_COL.fill_sheet_note, ["มากรอกชีตกันเถอะ"]),
    (LEADS_COL.customer_profile, ["PROFILE ลูกค้า จาก ADMIN", "PROFILE ลูกค้า"]),
    (LEADS_COL.occupation, ["อาชีพ"]),                     # คอลัม U
    (LEADS_COL.income, ["รายได้"]),                        # คอลัม V
    (LEADS_COL.job_tenure, ["อายุงาน"]),                   # คอลัม W
    (LEADS_COL.payment_history, ["ประวัติการผ่อน"]),        # คอลัม X
    (LEADS_COL.customer_type, ["ประเภทลูกค้า"]),            # คอลัม Y
    (LEADS_COL.customer_status, ["สถานะลูกค้า"]),          # คอลัม Z (layout ใหม่)
    (LEADS_COL.admin_status, ["Status แอดมิน", "สถานะแอดมิน"]),
    (LEADS_COL.sales_status, ["Status เซลล์", "สถานะเซลล์"]),
]
# canonical index ที่ "จัดการ" (ต้อง map จาก header — หาไม่เจอ = เคลียร์ว่าง กันอ่านผิดคอลัม)
_LEAD_MANAGED_IDX = [idx for idx, _ in _LEAD_FIELD_ALIASES]
_LEAD_CANON_WIDTH = 39  # max canonical index (customer_type=38) + 1


def _norm_header(s: str) -> str:
    """normalize ชื่อหัวคอลัมน์ — ตัดช่องว่าง/ขึ้นบรรทัดทิ้ง + พิมพ์เล็ก (จับคู่ง่าย ทนการพิมพ์)."""
    return "".join((s or "").split()).lower()


def _resolve_lead_colmap(header: list, sample_rows: list | None = None) -> dict:
    """header row → {canonical_index: source_index} จับคู่ตามชื่อหัวตาราง (เจอตัวแรกชนะ).

    ★ ส.ค.69 — เพิ่ม sample_rows: ถ้าหา "ช่องวันที่" จากหัวตารางไม่เจอ ให้ดูจากเนื้อข้อมูลแทน
      เหตุ: แท็บ "กันยายน 69" มีคนพิมพ์ทับหัวตาราง A1 จาก "ว/ด/ป" เป็นตัวเลข (46234 = วันที่ในรูป serial)
      → จับคู่ช่องวันที่ไม่ได้ → ทุกแถวถูกล้างวันที่ → **ทั้งเดือนหายไปจากระบบเงียบๆ** (48 ลีดจริงกลายเป็น 0)
      ช่องวันที่เป็นหัวใจ (ใช้กรองว่าแถวอยู่เดือนไหน) พังช่องเดียว = เดือนนั้นสูญทั้งเดือน จึงต้องมีทางสำรอง
    """
    norm = [_norm_header(c) for c in header]
    colmap: dict[int, int] = {}
    for canon_idx, aliases in _LEAD_FIELD_ALIASES:
        targets = {_norm_header(a) for a in aliases}
        for src_idx, hv in enumerate(norm):
            if hv and hv in targets:
                colmap[canon_idx] = src_idx
                break
    # เตือนเมื่อ match ไม่เจอ "เกินครึ่ง" ของ field → header เปลี่ยนชื่อ/ผิด tab → _normalize_lead_row จะล้างคอลัมน์เงียบๆ
    # (ไม่เตือนตอนขาดไม่กี่ field เพราะเดือนเก่าไม่มีคอลัมน์ใหม่ Z/U-Y เป็นปกติ)
    # ── ทางสำรองของ "ช่องวันที่": หาคอลัมน์ที่เนื้อข้อมูลเป็นวันที่จริง ──
    if LEADS_COL.received_date not in colmap and sample_rows:
        from .fetch_dashboard import parse_month_day
        best, best_hits = None, 0
        for src_idx in range(0, min(4, max((len(r) for r in sample_rows), default=0))):
            hits = sum(1 for r in sample_rows
                       if src_idx < len(r) and parse_month_day(str(r[src_idx] or "").strip()))
            if hits > best_hits:
                best, best_hits = src_idx, hits
        # ต้องดูเป็นวันที่จริงเกินครึ่งของตัวอย่าง ถึงจะเชื่อ (กันไปหยิบคอลัมน์เบอร์โทร/เวลา)
        if best is not None and best_hits >= max(3, len(sample_rows) // 2):
            colmap[LEADS_COL.received_date] = best
            import logging
            logging.getLogger("oxlet.sheets").warning(
                "lead colmap: หัวตารางช่องวันที่ผิด/หาย — เดาจากเนื้อข้อมูลได้คอลัมน์ %d "
                "(%d/%d แถวตัวอย่างเป็นวันที่) · ควรแก้หัวตารางในชีตให้เป็น 'ว/ด/ป'",
                best, best_hits, len(sample_rows))

    _missing = len(_LEAD_FIELD_ALIASES) - len(colmap)
    if _missing > len(_LEAD_FIELD_ALIASES) // 2:
        import logging
        logging.getLogger("oxlet.sheets").warning(
            "lead colmap: header match ไม่เจอ %d/%d field — คอลัมน์ถูกเคลียร์ว่างเยอะผิดปกติ "
            "(header เปลี่ยนชื่อ/ผิด tab?) เช็คหัวตาราง หรือเพิ่ม alias ใน _LEAD_FIELD_ALIASES",
            _missing, len(_LEAD_FIELD_ALIASES),
        )
    return colmap


def _normalize_lead_row(raw: list, colmap: dict) -> list:
    """จัดแถวให้อยู่ใน canonical layout: field ที่ map ได้ → ย้ายมาช่อง canonical,
    field ที่หา header ไม่เจอ → เคลียร์ว่าง (กันค่าคอลัมอื่นมาปนแล้วอ่านผิด เช่น 'ดึงคืน').
    คอลัมที่ไม่ได้จัดการ (ไม่มีใน alias) ปล่อยตามตำแหน่งเดิม."""
    width = max(len(raw), _LEAD_CANON_WIDTH)
    new_row = list(raw) + [""] * (width - len(raw))
    for canon_idx in _LEAD_MANAGED_IDX:
        src_idx = colmap.get(canon_idx)
        new_row[canon_idx] = raw[src_idx] if (src_idx is not None and src_idx < len(raw)) else ""
    return new_row


class SALES_COL:
    sales_rep = 0; order_num = 1; date = 2; channel = 3; lead_code = 4
    booking_no = 5; customer_name = 6; phone = 7; car_detail = 8
    car_year = 9; license_plate = 10; sale_price = 11; deposit_amount = 12
    status = 13; sign_date = 14; finance_main = 15; finance_backup = 16
    grade = 17; doc_complete_date = 18; result_date = 19; note = 20
    # วันที่ปล่อยรถ = V(21) (ตำแหน่งปัจจุบัน) — W(22) ตอนนี้เป็น "คืนเงิน/ค่าใช้จ่าย"
    # ค่ามักปนข้อความ (เช่น "รับรถ 20/3/69") → ใช้ extract_release_date() ดึงวันที่ออกมา
    car_release_date = 21
    legacy_car_release_date = 22

class BOOKINGS_COL:
    no = 0; date = 1; sales_rep = 2; channel = 3; seller_input = 4
    booking_amount = 5; code = 6; ads = 7; type = 8; car = 9
    plate = 10; customer_name = 11; province = 12; car_formula = 13

class LIVE_COL:
    date = 0; time = 1; team = 2; host_1 = 3; host_2 = 4
    host_3 = 5; host_4 = 6; host_5 = 7; topic = 8; inbox = 9
    lead_count = 10
    # ต่อท้ายตอนอ่าน (ไม่ใช่คอลัมน์จริงในชีต · แท็บกว้าง 44 คอล → ใช้ 50/51 กันชน) — ให้ inline edit รู้ว่าเขียนกลับแถวไหน
    sheet_tab = 50; sheet_row = 51

class FOLLOWUP_COL:
    name = 0; clip_date = 1

class EMPLOYEE_COL:
    user_id = 0; display_name = 1; picture_url = 2; group_id = 3
    reply_token = 4; nickname = 5; position = 6

class SELLER_CONFIG_COL:
    # ตั้งค่าเซลล์ tab — admin แก้ใน Google Sheets ตรงๆ ได้
    # Row format: ชื่อเล่น | ทีม (A/B/C) | เป้าต่อเดือน | แอดมิน (TRUE/ว่าง)
    # หมายเหตุ: ไม่มี column token แล้ว — URL ส่วนตัวเซลล์ใช้ LINE user_id (จาก employees sheet)
    nickname = 0
    team = 1
    target = 2
    is_admin = 3   # คอลัมน์ D — TRUE = เซลล์คนนี้ได้สิทธิ์แอดมินด้วย (login แล้วเป็น admin)

class ADMIN_CONFIG_COL:
    # tab "ตั้งค่าแอดมิน" — รายชื่อ LINE user_id ที่เป็นแอดมิน (คนที่ไม่ใช่เซลล์ใน TEAMS)
    # Row: LINE user_id | ชื่อ | หมายเหตุ
    user_id = 0
    name = 1
    note = 2

class SCHEDULE_COL:
    # ตั้งเวลาส่ง tab — ตารางเวลา trigger LINE Flex
    # Row: เวลา | วัน | เซลล์ | test_target | enabled | label | include_executive
    time = 0      # HH:MM (Bangkok time, 24-hour)
    days = 1      # "*" ทุกวัน | "1-5" จันทร์-ศุกร์ | "0,6" เสาร์-อาทิตย์ | "1,3,5" เลือกเฉพาะ (0=อาทิตย์)
    sellers = 2   # "*" ทุกเซลล์ | "โอ๊ต,เก้า,เจ" รายชื่อ | "" ไม่ส่งให้เซลล์
    test_target = 3  # ว่าง = ส่งจริง, ใส่ user_id = test mode
    enabled = 4   # TRUE/FALSE
    label = 5     # ชื่อตาราง (สำหรับมนุษย์อ่าน)
    include_executive = 6  # TRUE/FALSE — ส่ง Overview Flex ให้ผู้บริหารด้วยไหม


# ── Auth ──
SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
_credentials = None


def _get_credentials() -> Credentials:
    global _credentials
    email = settings.GOOGLE_SERVICE_ACCOUNT_EMAIL
    key = settings.GOOGLE_PRIVATE_KEY
    if not email or not key:
        raise ValueError("Missing GOOGLE_SERVICE_ACCOUNT_EMAIL or GOOGLE_PRIVATE_KEY")
    if _credentials is None or not _credentials.valid:
        _credentials = Credentials.from_service_account_info(
            {"client_email": email, "private_key": key, "token_uri": "https://oauth2.googleapis.com/token"},
            # Full read+write scope — admin ตั้งเป้า/ทีมในระบบจะเขียนกลับ sheet ผ่าน scope นี้
            # + drive.metadata.readonly — อ่านรายชื่อไฟล์ Google Sheets (ทำ dropdown เลือกไฟล์แบบ n8n)
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive.metadata.readonly",
            ],
        )
    if not _credentials.valid:
        _credentials.refresh(AuthRequest())
    return _credentials


def ensure_sheet_tab(spreadsheet_id: str, tab_name: str) -> bool:
    """ตรวจ tab ใน spreadsheet — ถ้าไม่มีให้สร้าง (ใช้ batchUpdate).
    คืน True ถ้ามีอยู่/สร้างสำเร็จ.
    """
    creds = _get_credentials()
    creds.refresh(AuthRequest())
    headers = {"Authorization": f"Bearer {creds.token}"}

    # อ่าน metadata ดูว่า tab มีอยู่ไหม
    r = requests.get(
        f"{SHEETS_API}/{spreadsheet_id}?fields=sheets.properties.title",
        headers=headers, timeout=15,
    )
    if r.status_code != 200:
        raise Exception(f"Sheets meta fetch failed: {r.status_code} {r.text}")
    existing = [s["properties"]["title"] for s in r.json().get("sheets", [])]
    if tab_name in existing:
        return True

    # สร้าง tab ใหม่
    r = requests.post(
        f"{SHEETS_API}/{spreadsheet_id}:batchUpdate",
        headers={**headers, "Content-Type": "application/json"},
        json={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
        timeout=15,
    )
    if r.status_code != 200:
        raise Exception(f"Cannot create tab '{tab_name}': {r.status_code} {r.text}")
    return True


def write_sheet(config_key: str, values: list[list]) -> None:
    """เขียนทับ tab ทั้งหมดด้วย values (clear+write).
    values = [[header_row], [row1], [row2], ...]
    """
    cfg = SHEET_CONFIG[config_key]
    sid = cfg["spreadsheet_id"]
    tab = cfg["sheet_name"]

    ensure_sheet_tab(sid, tab)

    creds = _get_credentials()
    creds.refresh(AuthRequest())
    headers = {"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"}

    import urllib.parse
    # A:ZZ (ไม่ใช่ A:Z) — กันข้อมูลคอลัมน์เกิน Z ค้างไม่ถูกล้าง (write_sheet = เขียนทับทั้ง tab)
    encoded = urllib.parse.quote(f"'{tab}'!A:ZZ")

    # Clear ก่อน
    r = requests.post(
        f"{SHEETS_API}/{sid}/values/{encoded}:clear",
        headers=headers, timeout=15,
    )
    if r.status_code != 200:
        raise Exception(f"Clear failed: {r.status_code} {r.text}")

    # Write ใหม่
    encoded_a1 = urllib.parse.quote(f"'{tab}'!A1")
    r = requests.put(
        f"{SHEETS_API}/{sid}/values/{encoded_a1}?valueInputOption=USER_ENTERED",
        headers=headers,
        json={"values": values},
        timeout=15,
    )
    if r.status_code != 200:
        raise Exception(f"Write failed: {r.status_code} {r.text}")

    # Invalidate cache สำหรับ key ที่เพิ่งเขียน (กัน user เห็นค่าเก่า)
    invalidate_cache(f"sheet:{config_key}")


# ── Config store: ย้าย config บางตัวเข้า DB (KVStore) — อ่าน/เขียนเร็ว ไม่ต้องรอ Sheets API ──
# อ่าน: DB ก่อน · ว่าง → fallback ชีต (แล้ว seed DB ให้ครั้งต่อไปเร็ว · auto-migrate) · เขียน: DB อย่างเดียว (ชีตไม่ใช่ source แล้ว)
_DB_CONFIG_KEYS = {"sellers_config", "schedule_config"}


def read_config_rows(config_key: str) -> list[list]:
    """อ่าน config rows — DB ก่อน (เร็ว) · DB ว่าง → อ่านชีตแล้ว seed DB · error → ชีต (rows รวม header เหมือน fetch_sheet)"""
    if config_key not in _DB_CONFIG_KEYS:
        return fetch_sheet(config_key)
    try:
        from . import cache_store
        rows = ((cache_store.get_kv("cfg_" + config_key) or {}).get("data") or {}).get("rows")
        if rows:
            return rows
    except Exception:
        pass
    rows = fetch_sheet(config_key)   # fallback ชีต + seed DB
    if rows:
        try:
            from . import cache_store
            cache_store.set_kv("cfg_" + config_key, {"rows": rows})
        except Exception:
            pass
    return rows


def write_config_rows(config_key: str, values: list[list]) -> None:
    """เขียน config เข้า DB (เร็ว · DB เป็น source) — ไม่แตะชีต
    แปลงทุกช่องเป็น string (ให้ตรงฟอร์แมตที่ fetch_sheet คืน · cell()/cell_num() คาด string)"""
    from . import cache_store
    rows = [["" if c is None else str(c) for c in row] for row in values]
    cache_store.set_kv("cfg_" + config_key, {"rows": rows})


def _col_letter(i: int) -> str:
    """0 → A, 25 → Z, 26 → AA ..."""
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


# ช่องที่อนุญาตให้เซลล์เขียนกลับจากหน้า LEAD (canonical field → LEADS_COL index)
_WRITABLE_LEAD_FIELDS = {
    "fill_sheet_note": LEADS_COL.fill_sheet_note,   # คอลัม S "มากรอกชีตกันเถอะ"
    "customer_status": LEADS_COL.customer_status,   # คอลัม Z "สถานะลูกค้า"
    "customer_profile": LEADS_COL.customer_profile, # คอลัม T PROFILE ลูกค้า
    "occupation": LEADS_COL.occupation,             # คอลัม U อาชีพ
    "income": LEADS_COL.income,                     # คอลัม V รายได้
    "job_tenure": LEADS_COL.job_tenure,             # คอลัม W อายุงาน
    "payment_history": LEADS_COL.payment_history,   # คอลัม X ประวัติการผ่อน
    "customer_type": LEADS_COL.customer_type,       # คอลัม Y ประเภทลูกค้า
}


def update_lead_field(code: str, field: str, value: str, month: int | None = None,
                      expected_seller: str = "") -> dict:
    """เขียนค่ากลับ 1 ช่องของ lead ตาม Code — รองรับหลาย field (S/Z/N).

    หา source column ของ field + lead_code จาก header (รองรับทุก layout)
    แล้ว PATCH เฉพาะ cell เดียว. คืน {ok, tab, cell} หรือ {error}.
    expected_seller (normalized) — ถ้าใส่ จะเขียนเฉพาะแถวที่เซลล์ตรงกัน (กันแก้เคสคนอื่น).
    """
    import urllib.parse
    from .constants import normalize_seller   # late import กัน circular
    canon = _WRITABLE_LEAD_FIELDS.get(field)
    if canon is None:
        return {"error": f"ไม่อนุญาตให้แก้ field '{field}'"}
    load_sheet_config_overrides()
    code = (code or "").strip()
    if not code:
        return {"error": "ไม่มี Code"}

    sid = SHEET_CONFIG["leads"]["spreadsheet_id"]
    creds = _get_credentials()
    creds.refresh(AuthRequest())
    auth = {"Authorization": f"Bearer {creds.token}"}

    # รายชื่อ tab รายเดือนทั้งหมด (สด)
    try:
        meta = requests.get(
            f"{SHEETS_API}/{sid}?fields=sheets.properties.title",
            headers=auth, timeout=15,
        ).json()
        titles = [s["properties"]["title"] for s in meta.get("sheets", [])]
    except Exception as e:
        return {"error": f"อ่านรายชื่อ tab ไม่ได้: {e}"}

    # จัดลำดับ tab ที่จะค้น — เดือนเป้าหมายก่อน แล้วค่อยที่เหลือ + "รวม sheet"
    monthly = [t for t in titles if any(t.startswith(m + " ") for m in _THAI_MONTHS)]
    ordered = []
    if month and 1 <= month <= 12:
        mname = _THAI_MONTHS[month - 1]
        ordered += [t for t in monthly if t.startswith(mname + " ")]
    ordered += [t for t in monthly if t not in ordered]
    if "รวม sheet" in titles:
        ordered.append("รวม sheet")

    for tab in ordered:
        encoded = urllib.parse.quote(f"'{tab}'")
        r = requests.get(
            f"{SHEETS_API}/{sid}/values/{encoded}?valueRenderOption=FORMATTED_VALUE",
            headers=auth, timeout=30,
        )
        if r.status_code != 200:
            continue
        vals = r.json().get("values", [])
        if not vals:
            continue
        colmap = _resolve_lead_colmap(vals[0], vals[1:21])
        code_src = colmap.get(LEADS_COL.lead_code)
        field_src = colmap.get(canon)
        rep_src = colmap.get(LEADS_COL.sales_rep)
        if code_src is None or field_src is None:
            continue
        for i, raw in enumerate(vals[1:], start=2):   # sheet row = index+2 (1 header)
            if code_src < len(raw) and (raw[code_src] or "").strip() == code:
                # กันเซลล์แก้เคสคนอื่น (ถ้ามี code ซ้ำข้ามเซลล์ → ข้ามแถวที่ไม่ใช่ของเขา)
                if expected_seller and rep_src is not None:
                    rs = normalize_seller(raw[rep_src]) if rep_src < len(raw) else ""
                    if rs != expected_seller:
                        continue
                a1 = urllib.parse.quote(f"'{tab}'!{_col_letter(field_src)}{i}")
                up = requests.put(
                    f"{SHEETS_API}/{sid}/values/{a1}?valueInputOption=USER_ENTERED",
                    headers={**auth, "Content-Type": "application/json"},
                    json={"values": [[value]]}, timeout=15,
                )
                if up.status_code != 200:
                    return {"error": f"เขียนไม่สำเร็จ {up.status_code}: {up.text[:160]}"}
                invalidate_cache()   # leads cache → ดึงใหม่
                return {"ok": True, "tab": tab, "cell": f"{_col_letter(field_src)}{i}"}

    return {"error": f"ไม่พบเคส Code '{code}' ในชีต"}


def update_lead_fill_note(code: str, value: str, month: int | None = None,
                          expected_seller: str = "") -> dict:
    """back-compat — เขียนคอลัม S ('มากรอกชีตกันเถอะ'). ใช้ update_lead_field ข้างใน."""
    return update_lead_field(code, "fill_sheet_note", value, month, expected_seller)


def update_release_date(tab: str, sheet_row: int, col_idx: int, value: str) -> dict:
    """เขียน 'วันปล่อย' กลับชีตยอดขาย ตรงตำแหน่ง (tab + แถว + คอลัมน์) ที่ booking_case จำไว้ (inline edit แอดมิน).
    col_idx 0-based (23=X พ.ค.+ · 21=V เดือนก่อน) · caller ต้องเช็คสิทธิ์ admin + validate มาแล้ว.
    """
    import urllib.parse
    load_sheet_config_overrides()
    sid = SHEET_CONFIG["sales_reports"]["spreadsheet_id"]
    a1 = f"'{tab}'!{_col_letter(col_idx)}{int(sheet_row)}"
    creds = _get_credentials()
    creds.refresh(AuthRequest())
    headers = {"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"}
    enc = urllib.parse.quote(a1)
    r = requests.put(
        f"{SHEETS_API}/{sid}/values/{enc}?valueInputOption=USER_ENTERED",
        headers=headers, json={"values": [[value]]}, timeout=15,
    )
    if r.status_code != 200:
        raise Exception(f"write failed: {r.status_code} {r.text[:140]}")
    invalidate_cache()   # ล้าง cache ทั้งหมด → ดึงค่าใหม่รอบหน้า
    return {"a1": a1, "value": value}


# ── CRUD ไลฟ์รายครั้ง (ชีต live_sessions แท็บ "สรุปไลฟ์สด <เดือน>") ──
def _live_sid_headers():
    load_sheet_config_overrides()
    sid = SHEET_CONFIG["live_sessions"]["spreadsheet_id"]
    creds = _get_credentials()
    creds.refresh(AuthRequest())
    return sid, {"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"}


def update_live_session(tab: str, sheet_row: int, team: str, hosts: list, topic: str) -> dict:
    """แก้ไลฟ์ 1 ครั้ง — เขียนช่วง C:I ของแถวนั้น (ทีม | ผู้ไลฟ์1-5 | หัวข้อ) · caller ต้องเช็คสิทธิ์ admin มาแล้ว"""
    import urllib.parse
    sid, headers = _live_sid_headers()
    hs = [(hosts[i] if i < len(hosts) else "") for i in range(5)]
    a1 = f"'{tab}'!C{int(sheet_row)}:I{int(sheet_row)}"
    # RAW: เก็บเป็นข้อความตรงตัว (ตรงกับที่ชีตนี้ใช้อยู่) + กันข้อความขึ้นต้น '=' กลายเป็นสูตร
    r = requests.put(
        f"{SHEETS_API}/{sid}/values/{urllib.parse.quote(a1)}?valueInputOption=RAW",
        headers=headers, json={"values": [[team] + hs + [topic]]}, timeout=15,
    )
    if r.status_code != 200:
        raise Exception(f"write failed: {r.status_code} {r.text[:140]}")
    invalidate_cache()
    return {"a1": a1}


def append_live_session(tab: str, date: str, time_: str, team: str, hosts: list,
                        topic: str, inbox, lead) -> dict:
    """เพิ่มไลฟ์ 1 ครั้ง — ต่อท้ายแท็บเดือนนั้น (A:K)"""
    import urllib.parse
    sid, headers = _live_sid_headers()
    ensure_sheet_tab(sid, tab)
    hs = [(hosts[i] if i < len(hosts) else "") for i in range(5)]
    row = [date, time_, team] + hs + [topic, inbox, lead]
    a1 = f"'{tab}'!A:K"
    # RAW: วันที่เก็บเป็นข้อความ '23/07/26' เหมือนแถวเดิมในชีต (USER_ENTERED จะกลายเป็น serial 46226)
    r = requests.post(
        f"{SHEETS_API}/{sid}/values/{urllib.parse.quote(a1)}:append"
        f"?valueInputOption=RAW&insertDataOption=INSERT_ROWS",
        headers=headers, json={"values": [row]}, timeout=15,
    )
    if r.status_code != 200:
        raise Exception(f"append failed: {r.status_code} {r.text[:140]}")
    invalidate_cache()
    return {"tab": tab, "row": row}


def delete_live_session(tab: str, sheet_row: int) -> dict:
    """ลบไลฟ์ 1 ครั้ง — ล้างค่าทั้งแถว (A:K) · ใช้ clear ไม่ใช่ deleteRow เพื่อไม่ให้เลขแถวของรายการอื่นเลื่อน"""
    import urllib.parse
    sid, headers = _live_sid_headers()
    a1 = f"'{tab}'!A{int(sheet_row)}:K{int(sheet_row)}"
    r = requests.post(
        f"{SHEETS_API}/{sid}/values/{urllib.parse.quote(a1)}:clear",
        headers=headers, json={}, timeout=15,
    )
    if r.status_code != 200:
        raise Exception(f"clear failed: {r.status_code} {r.text[:140]}")
    invalidate_cache()
    return {"a1": a1}


# ── Fetch helpers ──
def cell(row: list[str], index: int) -> str:
    if index < len(row):
        v = row[index]
        return (str(v) if v is not None else "").strip()   # กันค่าที่ไม่ใช่ string (เช่น int จาก config DB)
    return ""


def cell_num(row: list[str], index: int) -> float:
    v = cell(row, index).replace(",", "").replace(" ", "")
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0


def cell_bool(row: list[str], index: int) -> bool:
    v = cell(row, index).lower()
    return v in ("ส่งแล้ว", "true", "yes", "1")


# ── Override SHEET_CONFIG จาก Supabase (เปลี่ยน spreadsheet/tab ได้จากแอดมิน) ──
# โหลดครั้งเดียวต่อ process (flag) — admin กดบันทึกจะ reload ด้วย force=True
_sheet_config_loaded = False


def load_sheet_config_overrides(force: bool = False) -> None:
    """อ่าน override จาก Supabase แล้ว mutate SHEET_CONFIG in-place (spreadsheet_id/sheet_name).
    ใช้สำหรับย้ายไฟล์ชีต (เช่น ปีใหม่) โดยไม่ต้องแก้โค้ด. error/ไม่มี Supabase → ใช้ default.
    """
    global _sheet_config_loaded
    if _sheet_config_loaded and not force:
        return
    _sheet_config_loaded = True
    try:
        from .cache_store import get_sheet_config
        for k, v in (get_sheet_config() or {}).items():
            if k in SHEET_CONFIG:
                if v.get("spreadsheet_id"):
                    SHEET_CONFIG[k]["spreadsheet_id"] = v["spreadsheet_id"]
                if v.get("sheet_name"):
                    SHEET_CONFIG[k]["sheet_name"] = v["sheet_name"]
    except Exception:
        pass


def fetch_sheet(config_key: str) -> list[list[str]]:
    """Fetch a single sheet → list of row arrays (skip header).
    Cache TTL 60s — ลด API quota hits (Vercel warm instance memory)
    """
    load_sheet_config_overrides()
    cache_key = f"sheet:{config_key}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    creds = _get_credentials()
    creds.refresh(AuthRequest())
    token = creds.token

    cfg = SHEET_CONFIG[config_key]
    sid = cfg["spreadsheet_id"]
    sheet_name = cfg["sheet_name"]
    import urllib.parse
    encoded_range = urllib.parse.quote(f"'{sheet_name}'")
    url = f"{SHEETS_API}/{sid}/values/{encoded_range}?valueRenderOption=FORMATTED_VALUE"

    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if resp.status_code != 200:
        raise Exception(f"Sheets API error ({config_key}): {resp.status_code} {resp.text}")

    data = resp.json()
    rows = data.get("values", [])
    result = rows[1:]  # skip header
    _cache_set(cache_key, result)
    return result


# Thai month name → 1-based index (ใช้สำหรับเรียง tab รายเดือนใน leads spreadsheet)
_THAI_MONTHS = [
    "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
    "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
]


_last_dedup_stats: dict = {"input_rows": 0, "output_rows": 0, "duplicates_removed": 0, "no_code": 0}


def get_leads_dedup_stats() -> dict:
    """คืน stats ของการ dedup ครั้งล่าสุด (สำหรับ admin diagnostics)."""
    return dict(_last_dedup_stats)


def _dedupe_leads_by_code(rows: list[list[str]]) -> list[list[str]]:
    """Dedup lead rows by Code (col D=3), case-insensitive + trimmed.
    แถวที่ปรากฏหลังสุดใน list ชนะ (overwrite earlier) — "ตัวล่าสุด" = แถวล่างใน sheet,
    หรือเดือนใหม่กว่าถ้า rows มาจากการต่อ tab เดือนเก่า → ใหม่
    Code ว่าง = ไม่ dedup (ถือเป็นเคสแยก).
    """
    code_to_row: dict[str, list[str]] = {}
    rows_no_code: list[list[str]] = []
    duplicates_removed = 0
    for row in rows:
        raw_code = row[3] if len(row) > 3 else ""
        code = (raw_code or "").strip().upper()
        if code:
            if code in code_to_row:
                duplicates_removed += 1
            code_to_row[code] = row  # overwrite — later row wins
        else:
            rows_no_code.append(row)
    result = list(code_to_row.values()) + rows_no_code
    _last_dedup_stats.update({
        "input_rows": len(rows),
        "output_rows": len(result),
        "duplicates_removed": duplicates_removed,
        "no_code": len(rows_no_code),
    })
    return result


def fetch_leads_dedup() -> list[list[str]]:
    """รวมข้อมูล leads จาก "รวม sheet" + monthly tabs (เช่น "มกราคม 69", "พฤษภาคม 69")
    แล้ว dedup by Code (column D=3, case-insensitive + trimmed).

    ลำดับ overwrite (แถวหลังสุดชนะ):
      1. "รวม sheet" (base) — มีข้อมูลทั้งหมดสำรอง
      2. Monthly tabs ม.ค. → ธ.ค. — ทับด้วย row ที่อาจ update ใหม่กว่า
      3. ภายใน tab เดียวกัน — แถวล่างสุดชนะ

    Failsafe: ถ้า monthly tabs fetch ไม่ได้/ว่าง → ยังมีข้อมูลจาก "รวม sheet" เป็น fallback
    """
    import urllib.parse

    # 1) Base: "รวม sheet" — ข้อมูล primary ที่ระบบใช้มาก่อน
    try:
        base_rows = fetch_sheet("leads")
    except Exception:
        base_rows = []

    # 2) ดึง monthly tabs (best-effort — ถ้าไม่ได้ก็ skip)
    monthly_rows: list[list[str]] = []
    try:
        creds = _get_credentials()
        creds.refresh(AuthRequest())
        headers_auth = {"Authorization": f"Bearer {creds.token}"}
        sid = SHEET_CONFIG["leads"]["spreadsheet_id"]

        meta = requests.get(
            f"{SHEETS_API}/{sid}?fields=sheets.properties.title",
            headers=headers_auth, timeout=15,
        ).json()
        all_tabs = [s["properties"]["title"] for s in meta.get("sheets", [])]

        monthly_tabs: list[tuple[int, str]] = []
        for tab in all_tabs:
            for idx, m in enumerate(_THAI_MONTHS):
                if tab.startswith(m + " "):
                    monthly_tabs.append((idx, tab))
                    break
        monthly_tabs.sort()  # ม.ค. (idx=0) → ธ.ค. (idx=11)

        def _fetch_tab(tab: str) -> list[list[str]]:
            encoded = urllib.parse.quote(f"'{tab}'")
            url = f"{SHEETS_API}/{sid}/values/{encoded}?valueRenderOption=FORMATTED_VALUE"
            r = requests.get(url, headers=headers_auth, timeout=30)
            if r.status_code != 200:
                return []
            return r.json().get("values", [])[1:]  # skip header

        tab_rows: dict[str, list[list[str]]] = {}
        if monthly_tabs:
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
                futs = {ex.submit(_fetch_tab, tab): tab for _, tab in monthly_tabs}
                for fut in concurrent.futures.as_completed(futs):
                    tab = futs[fut]
                    try:
                        tab_rows[tab] = fut.result()
                    except Exception:
                        tab_rows[tab] = []

        for _, tab in monthly_tabs:
            monthly_rows.extend(tab_rows.get(tab, []))
    except Exception:
        monthly_rows = []  # graceful — ใช้แค่ base_rows

    # 3) Merge — base + monthly (monthly ทับ base ถ้า code ซ้ำ)
    #    Failsafe: ถ้า monthly_rows ว่าง → base_rows ยังครบ → ระบบไม่พัง
    ordered_rows = base_rows + monthly_rows
    return _dedupe_leads_by_code(ordered_rows)


def fetch_leads_by_month_tabs() -> list[list[str]]:
    """อ่าน leads จาก monthly tabs (มกราคม-ธันวาคม 69) แต่ละแถวเก็บเฉพาะ
    ที่ "วันที่ใน column ตรงกับเดือนของ tab" — ตัดเคสที่ admin เอามาใส่ผิด tab ออก.

    Cache TTL 60s — ลด API hits (1 meta + 5 tabs = 6 reads/call, แพงสุด)

    ใช้แทน fetch_leads_dedup ใน seller_dashboard เพื่อให้ตัวเลขตรงกับการนับ
    raw rows ในแต่ละ monthly tab (= ที่ admin คาดหวัง).

    Failsafe: ถ้า monthly tabs fetch ไม่ได้/ว่าง → fall back ไป fetch_sheet("leads")
    """
    cache_key = "leads_month_tabs"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    import urllib.parse

    try:
        creds = _get_credentials()
        creds.refresh(AuthRequest())
        headers_auth = {"Authorization": f"Bearer {creds.token}"}
        sid = SHEET_CONFIG["leads"]["spreadsheet_id"]

        meta = requests.get(
            f"{SHEETS_API}/{sid}?fields=sheets.properties.title",
            headers=headers_auth, timeout=15,
        ).json()
        all_tabs = [s["properties"]["title"] for s in meta.get("sheets", [])]

        # Parse tab names + skip future months (กรณีมีการสร้าง tab ไว้ล่วงหน้าหลายปี)
        # Format: "{ชื่อเดือน} {ปีพ.ศ.2digit}" เช่น "พฤษภาคม 69"
        from datetime import datetime
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Asia/Bangkok"))
        cur_year_2digit = (now.year + 543) % 100  # 2026 → 69
        cur_month = now.month

        monthly_tabs: list[tuple[int, str]] = []  # (month 1-12, tab name)
        future_skipped = 0
        for tab in all_tabs:
            for idx, m in enumerate(_THAI_MONTHS):
                if tab.startswith(m + " "):
                    # ดึง year part หลังชื่อเดือน
                    year_str = tab[len(m) + 1:].strip()
                    try:
                        tab_year = int(year_str)
                    except ValueError:
                        # ปีไม่ใช่ตัวเลข — เก็บไว้ก่อน (backward compat)
                        monthly_tabs.append((idx + 1, tab))
                        break
                    tab_month = idx + 1
                    # Skip tab ที่อยู่ในอนาคต (ลด API calls + เร็วขึ้น)
                    if tab_year > cur_year_2digit or (tab_year == cur_year_2digit and tab_month > cur_month):
                        future_skipped += 1
                        break
                    monthly_tabs.append((tab_month, tab))
                    break

        if not monthly_tabs:
            # ไม่มี monthly tab → fall back
            return fetch_sheet("leads")

        def _fetch_tab(tab: str) -> list[list[str]]:
            """★ ส.ค.69 — ลองซ้ำ 1 ครั้งถ้าพลาด
            เดิมพลาดครั้งเดียว = คืนลิสต์ว่าง → "เดือนนั้นหายทั้งเดือน" แบบเงียบๆ
            (เจอจริงตอนตรวจ: ก.พ. หาย 2,787 ลีดจากการดึงพลาดชั่วคราวรอบเดียว)"""
            encoded = urllib.parse.quote(f"'{tab}'")
            url = f"{SHEETS_API}/{sid}/values/{encoded}?valueRenderOption=FORMATTED_VALUE"
            import time as _t
            last = ""
            for _attempt in range(3):
                try:
                    r = requests.get(url, headers=headers_auth, timeout=30)
                    if r.status_code == 200:
                        return r.json().get("values", [])
                    last = "HTTP %s" % r.status_code
                except Exception as _e:
                    last = str(_e)[:60]
                # 429 = Google จำกัดจำนวนครั้ง (เราอ่าน 9 แท็บพร้อมกัน แต่ละแท็บหลายพันแถว)
                # ต้องรอแล้วค่อยลองใหม่ ยิงซ้ำทันทีจะโดนปฏิเสธซ้ำ
                _t.sleep(1.0 + _attempt * 2.0)
            import logging
            logging.getLogger("oxlet.sheets").warning("อ่านแท็บ '%s' ไม่สำเร็จ (%s)", tab, last)
            return []

        # Fetch all tabs in parallel
        tab_rows: dict[str, tuple[int, list[list[str]]]] = {}
        failed_tabs: list[str] = []      # ★ แท็บที่อ่านไม่ได้ — ต้องรู้ ไม่ใช่เงียบ
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
            futs = {ex.submit(_fetch_tab, tab): (m_int, tab) for m_int, tab in monthly_tabs}
            for fut in concurrent.futures.as_completed(futs):
                m_int, tab = futs[fut]
                try:
                    vals_ = fut.result()
                except Exception:
                    vals_ = []
                if not vals_:
                    failed_tabs.append(tab)
                tab_rows[tab] = (m_int, vals_)

        # ดึง parse_date จาก fetch_dashboard (avoid circular import — late import)
        from .fetch_dashboard import parse_date

        # ── overlay สถานะล่าสุดจากทุกแท็บ: Z (customer_status) + AB (admin_status) + เซลล์ (sales_status) ──
        # เคสเก่า (วันที่เดือนก่อน) ถูกเอามาทำต่อในแท็บปัจจุบัน (admin อัปเดต Z/AB) แต่ date-filter เก็บ copy เดือนเก่า
        # (สถานะในสำเนาเดือนเก่ายังเป็นค่าเดิม) → สถานะที่อัปเดต (จ่ายใหม่/คืนเคส/จอง) หาย → ตามผิด/นับผิด.
        # รวบ "ค่าล่าสุด (เดือนสูงสุดที่กรอก)" ต่อ lead_code มา overlay ทับ (การนับเดือนยังอิงวันที่เดิม — overlay แค่สถานะ).
        # เคส TLD-10187: received 28/5 → row ใช้สำเนา พ.ค. (admin=ติดตาม) แต่ admin ใส่ "จ่ายใหม่" ในแท็บ มิ.ย. → overlay มาให้
        _OVERLAY_FIELDS = (LEADS_COL.customer_status, LEADS_COL.admin_status, LEADS_COL.sales_status)
        latest: dict[int, dict[str, str]] = {f: {} for f in _OVERLAY_FIELDS}
        latest_m: dict[int, dict[str, int]] = {f: {} for f in _OVERLAY_FIELDS}
        for m_int, tab in monthly_tabs:
            _, vals = tab_rows.get(tab, (m_int, []))
            if not vals:
                continue
            cmz = _resolve_lead_colmap(vals[0], vals[1:21])
            csrc = cmz.get(LEADS_COL.lead_code)
            if csrc is None:
                continue
            srcs = {f: cmz[f] for f in _OVERLAY_FIELDS if cmz.get(f) is not None}
            if not srcs:
                continue
            for raw in vals[1:]:
                code = (raw[csrc] if csrc < len(raw) else "").strip()
                if not code:
                    continue
                for f, fsrc in srcs.items():
                    val = (raw[fsrc] if fsrc < len(raw) else "").strip()
                    if val and m_int >= latest_m[f].get(code, 0):
                        latest[f][code] = val
                        latest_m[f][code] = m_int

        all_rows: list[list[str]] = []
        for m_int, tab in monthly_tabs:
            _, vals = tab_rows.get(tab, (m_int, []))
            if not vals:
                continue
            # map คอลัมน์ตามชื่อหัวตารางของ tab นี้ (แต่ละเดือน layout อาจต่างกัน)
            colmap = _resolve_lead_colmap(vals[0], vals[1:21])
            for raw in vals[1:]:
                row = _normalize_lead_row(raw, colmap)
                d = parse_date(cell(row, LEADS_COL.received_date))
                if d and d.month == m_int:
                    _code = cell(row, LEADS_COL.lead_code).strip()
                    for f in _OVERLAY_FIELDS:    # สถานะล่าสุดจากทุกแท็บ (Z/AB/เซลล์)
                        if _code in latest[f]:
                            row[f] = latest[f][_code]
                    all_rows.append(row)
        # ★ ส.ค.69 — อ่านแท็บไหนไม่ได้ = ผลลัพธ์ "ขาดทั้งเดือน"
        #   ห้าม cache ผลที่ขาด (ไม่งั้นตัวเลขผิดค้าง 60 วิ + ถูกเขียนลง precompute ต่อ)
        #   และต้องบันทึกไว้ให้หน้าสถานะระบบเห็น — เดิมเงียบสนิท
        if failed_tabs:
            try:
                from . import cache_store
                cache_store.set_kv("sheets_fetch_last",
                                   {"ok": False, "source": "leads", "failed": failed_tabs[:6]})
            except Exception:
                pass
            import logging
            logging.getLogger("oxlet.sheets").warning(
                "อ่านแท็บ leads ไม่สำเร็จ %d แท็บ: %s — ตัวเลขเดือนนั้นจะขาด (ไม่ cache ผลนี้)",
                len(failed_tabs), ", ".join(failed_tabs[:6]))
            return all_rows          # คืนของเท่าที่ได้ แต่ไม่ cache → รอบหน้าลองใหม่
        try:
            from . import cache_store
            cache_store.set_kv("sheets_fetch_last", {"ok": True, "source": "leads"})
        except Exception:
            pass
        _cache_set(cache_key, all_rows)
        return all_rows
    except Exception as e:
        # graceful fallback — อย่างน้อยมีข้อมูลจาก "รวม sheet"
        # ★ ส.ค.69 — เดิมกลืนเงียบ: พอ fallback ตัวเลขเปลี่ยนไปคนละชุด (รวม sheet ไม่ครบเดือนใหม่)
        #   แต่ไม่มีใครรู้ว่าเกิดอะไร → ต้อง log + บันทึกให้หน้าสถานะระบบเห็น
        import logging, traceback
        logging.getLogger("oxlet.sheets").error(
            "fetch_leads_by_month_tabs ล้มเหลว → ตกไปใช้ 'รวม sheet' (ตัวเลขจะไม่ตรงกับแท็บรายเดือน): %s%s",
            e, chr(10) + traceback.format_exc()[-800:])
        try:
            from . import cache_store
            cache_store.set_kv("sheets_fetch_last",
                               {"ok": False, "source": "leads", "fallback": True, "error": str(e)[:200]})
        except Exception:
            pass
        return fetch_sheet("leads")


# ===== แผนที่คอลัมน์ของชีตยอดขาย (header-based · ส.ค.69) =====
# ★ ทำไมต้องมี: แท็บรายเดือนของชีตยอดขาย "ขยับคอลัมน์" เรื่อยๆ เมื่อแอดมินแทรกช่องใหม่
#   วัดจริง ส.ค.69: เม.ย.69 แทรก 5 ช่อง (อาชีพ/รายได้/อายุงาน/ประวัติผ่อน/อายุ) ก่อนช่อง "สถานะ"
#   → สถานะเลื่อน 13→18 · นัดเซ็น 14→19 · ปล่อยรถ 21/22→27/28
#   ผลตอนนั้น: เม.ย.+พ.ค. หายทั้งเดือน (ตัวกรอง "สถานะไม่ว่าง" ไปอ่านช่องอาชีพที่ว่าง)
#             มิ.ย.-ส.ค. อ่าน "พนักงานบริษัท/ค้าขาย" มาเป็นสถานะ
#   → เลิก fix ตำแหน่งตายตัว อ่านจาก "ชื่อหัวตาราง" ของแต่ละแท็บแทน (แบบเดียวกับชีตลีด)
#   เพิ่ม/เปลี่ยนชื่อหัวคอลัมน์ในชีต = เติม alias ตรงนี้ที่เดียว
_SALES_HDR_RULES = [
    # (ฟิลด์, ตรวจแบบ, คำ) — เรียงจาก "เจาะจงสุด" ลงมา · คอลัมน์แรกที่เข้าเงื่อนไขได้ฟิลด์นั้น
    ("sign_date",         "in", "นัดเซ็น"),
    ("result_date",       "in", "ผลออกจริง"),
    ("_result_est",       "in", "ผลน่าจะออก"),      # ไม่ใช้ (กันไปชนกับวันผลจริง)
    ("doc_complete_date", "in", "เอกสารครบ"),
    ("car_release_date",  "in", "ปล่อยรถ"),
    ("deposit_amount",    "in", "เงินจอง"),
    ("sale_price",        "in", "ราคาขาย"),
    ("license_plate",     "in", "ทะเบียน"),
    ("car_detail",        "in", "รายละเอียดรถ"),
    ("car_year",          "in", "ปีรถ"),
    ("phone",             "in", "เบอร์โทร"),
    ("customer_name",     "in", "ชื่อ-นามสกุล"),
    ("booking_no",        "in", "เลขที่จอง"),
    ("lead_code",         "in", "โค้ด"),
    ("channel",           "in", "ช่องทาง"),
    ("order_num",         "in", "ลำดับ"),
    ("finance_main",      "in", "ไฟแนนซ์หลัก"),
    ("finance_backup",    "in", "ไฟแนนซ์สำรอง"),
    ("grade",             "in", "เกรด"),
    ("occupation",        "in", "อาชีพ"),
    ("income",            "in", "รายได้"),
    ("job_tenure",        "in", "อายุงาน"),
    ("payment_history",   "in", "ประวัติผ่อน"),
    ("status",            "eq", "สถานะ"),
    ("date",              "eq", "วันที่"),
    ("note",              "eq", "หมายเหตุ"),
    ("age",               "eq", "อายุ"),
]
# ตำแหน่ง canonical ที่โค้ดทั้งระบบใช้ (ต้องตรงกับ class SALES_COL) — normalize แล้วทุกแท็บหน้าตาเหมือนกัน
_SALES_CANON = {
    "order_num": 1, "date": 2, "channel": 3, "lead_code": 4, "booking_no": 5,
    "customer_name": 6, "phone": 7, "car_detail": 8, "car_year": 9, "license_plate": 10,
    "sale_price": 11, "deposit_amount": 12, "status": 13, "sign_date": 14,
    "finance_main": 15, "finance_backup": 16, "grade": 17, "doc_complete_date": 18,
    "result_date": 19, "note": 20, "car_release_date": 21,
    # ช่องใหม่ที่แอดมินแทรกเข้ามา — เก็บไว้ท้ายแถว (ยังไม่มีใครใช้ แต่ไม่ทิ้งข้อมูล)
    "occupation": 23, "income": 24, "job_tenure": 25, "payment_history": 26, "age": 27,
}
SALES_ROW_WIDTH = 28          # 0..27 (0 = ชื่อเซลล์)
SALES_IDX_TAB = 28            # ชื่อแท็บ
SALES_IDX_ROW = 29            # เลขแถวในชีต (1-based)
SALES_IDX_RESULT_COL = 30     # คอลัมน์จริงของ "วันผลออกจริง" ในชีต (ไว้เขียนกลับ)
SALES_IDX_RELEASE_COL = 31    # คอลัมน์จริงของ "วันที่ปล่อยรถ" ในชีต (ไว้เขียนกลับ)
SALES_IDX_STATUS_COL = 32     # คอลัมน์จริงของ "สถานะ" (เลื่อน 13->18 ตั้งแต่ เม.ย.69)
SALES_IDX_SIGN_COL = 33       # คอลัมน์จริงของ "วันที่นัดเซ็น" (เลื่อน 14->19)


def _resolve_sales_colmap(header_row) -> dict:
    """อ่านหัวตารางของแท็บ → {ฟิลด์: index จริงในชีต} · ฟิลด์ที่ไม่เจอ = ไม่มีในแผนที่"""
    import re as _re
    out = {}
    for j, raw in enumerate(header_row or []):
        txt = _re.sub(r"\s+", "", str(raw or ""))
        if not txt:
            continue
        for field, how, word in _SALES_HDR_RULES:
            if field in out or field.startswith("_"):
                continue
            if (word in txt) if how == "in" else (txt == word):
                out[field] = j
                break
    return out


def fetch_sales_by_month_tabs() -> list[list[str]]:
    """อ่านยอดขายจากแท็บรายเดือน '<เดือน>69' ตรงๆ (แทน 'รวม sheet' ที่ใช้สูตร REDUCE).

    แต่ละแท็บจัดกลุ่มตามเซลล์ด้วย marker 'ชื่อเซลล์ X' ใน column B:
    - ดึงบล็อกของแต่ละเซลล์ (ตั้งแต่ใต้ marker ถึง marker ถัดไป)
    - เอาเฉพาะแถวที่ลำดับ(B) เป็นตัวเลข + สถานะ(N) ไม่ว่าง (ตรงกับ filter ในสูตร)
    - prepend ชื่อเซลล์เป็น column 0 → ได้รูปแบบเดียวกับ flattened 'รวม sheet' เดิม (ตรง SALES_COL)

    ★ ชื่อเซลล์ match กับ ALL_SELLERS (รายชื่อจริง dynamic) → เซลล์ใหม่เพิ่มเองอัตโนมัติ,
      marker ขยะ ('A' / ว่าง / ชื่อไม่อยู่ในรายชื่อ) ถูกตัดทิ้ง — แก้ปัญหาสูตร hardcode 13 ชื่อ
    Failsafe: แท็บไม่มี/ว่าง → fall back ไป fetch_sheet('sales_reports')
    """
    import urllib.parse
    load_sheet_config_overrides()
    cache_key = "sales_month_tabs"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        from .constants import normalize_seller, ALL_SELLERS, refresh_from_sheet
        from .fetch_dashboard import bangkok_now
        refresh_from_sheet()   # ให้ ALL_SELLERS เป็นรายชื่อล่าสุด

        sid = SHEET_CONFIG["sales_reports"]["spreadsheet_id"]
        creds = _get_credentials()
        creds.refresh(AuthRequest())
        auth = {"Authorization": f"Bearer {creds.token}"}

        now = bangkok_now()
        be_year2 = (now.year + 543) % 100               # 2026 -> 2569 -> 69
        want = {f"{_THAI_MONTHS[m - 1]}{be_year2:02d}": m for m in range(1, now.month + 1)}

        meta = requests.get(f"{SHEETS_API}/{sid}?fields=sheets.properties.title",
                            headers=auth, timeout=20).json()
        titles = {s["properties"]["title"] for s in meta.get("sheets", [])}
        tabs = [(t, m) for t, m in want.items() if t in titles]
        if not tabs:
            return fetch_sheet("sales_reports")

        known = {normalize_seller(s) for s in ALL_SELLERS} | {"ADMIN"}   # อ่านบล็อก "ชื่อเซลล์ ADMIN" ด้วย

        def _fetch(tab):
            enc = urllib.parse.quote(f"'{tab}'")
            r = requests.get(f"{SHEETS_API}/{sid}/values/{enc}?valueRenderOption=FORMATTED_VALUE",
                             headers=auth, timeout=40)
            return r.json().get("values", []) if r.status_code == 200 else []

        tab_vals = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
            futs = {ex.submit(_fetch, t): t for t, _ in tabs}
            for f in concurrent.futures.as_completed(futs):
                tab_vals[futs[f]] = f.result()

        all_rows: list[list[str]] = []
        for tab, _m in tabs:
            vals = tab_vals.get(tab, [])
            # หา marker 'ชื่อเซลล์ X' ใน column B (index 1)
            markers = []
            for i, row in enumerate(vals):
                b = (row[1] if len(row) > 1 else "") or ""
                if isinstance(b, str) and b.strip().startswith("ชื่อเซลล์"):
                    markers.append((i, b.strip()[len("ชื่อเซลล์"):].strip()))
            # ★ ส.ค.69 — อ่าน "หัวตาราง" ของแท็บนี้ (แถวถัดจาก marker แรก) แล้วทำแผนที่คอลัมน์
            #   แต่ละเดือนคอลัมน์ไม่ตรงกัน (แอดมินแทรกช่องใหม่) → fix ตำแหน่งตายตัวไม่ได้อีกแล้ว
            cmap = _resolve_sales_colmap(vals[markers[0][0] + 1]) if markers and markers[0][0] + 1 < len(vals) else {}
            if "status" not in cmap:      # หาหัวตารางไม่เจอ → กลับไปใช้ตำแหน่งเดิม (กันแท็บรูปแบบแปลก)
                cmap = {k: v for k, v in _SALES_CANON.items()}
            c_status = cmap.get("status", 13)
            c_seq = cmap.get("order_num", 1)
            for k, (mi, raw_name) in enumerate(markers):
                name = normalize_seller(raw_name)
                end = markers[k + 1][0] if k + 1 < len(markers) else len(vals)
                # อ่านบล็อก: (1) ชื่ออยู่ในรายชื่อจริง (ALL_SELLERS/ADMIN) หรือ
                #   (2) ชื่อเซลล์จริงที่ไม่อยู่ใน config — เซลล์ลาออก/เทเลเซลล์ (เช่น "ใบตอง") ยังนับเคส
                #   (ผู้ใช้: เซลล์ออกไปแล้วเคสยังนับ · แค่เดือนต่อมาไม่มีชื่อ/สิทธิ์เข้าระบบ)
                # ตัดเฉพาะ marker ขยะ: "A"/ว่าง/สั้นเกิน หรือบล็อกไม่มีเคสจริง (seq เลข + สถานะ)
                if name not in known:
                    rn = raw_name.strip()
                    if len(rn) < 2 or rn.upper() == "A":
                        continue
                    if not any(
                        str(vals[j][c_seq] if len(vals[j]) > c_seq else "").strip().isdigit()
                        and str(vals[j][c_status] if len(vals[j]) > c_status else "").strip()
                        for j in range(mi + 1, end)
                    ):
                        continue   # บล็อกว่าง (ไม่มีเคส)
                for j in range(mi + 1, end):
                    row = vals[j]
                    seq = str(row[c_seq] if len(row) > c_seq else "").strip()
                    status = str(row[c_status] if len(row) > c_status else "").strip()
                    if not seq.isdigit() or not status:
                        continue   # ข้าม sub-header / แถวว่าง (ตรง filter N<>"" ในสูตร)
                    # col 0=ชื่อเซลล์, col 1-27=ตรง tab · col 28=tab name, col 29=แถวในชีต (1-based) — ใช้ inline edit เขียนกลับ
                    # เคสที่มาร์ค "ADMIN" ในคอลัมน์ AB (idx 24-29) = "เทเลเซลล์ทำเอง" (หาลีด+ปิดเอง) แม้อยู่ใต้บล็อกเซลล์อื่น
                    #   → ย้ายเป็น ADMIN ทุกสถานะ รวม "ปล่อย" ด้วย (เทเลเซลล์ได้เครดิตปล่อยเมื่อปิดเอง)
                    # ★ (มิ.ย.69→ก.ค.69) เอากฎยกเว้น "ปล่อย" ออกแล้ว: เดิมบังคับเทปล่อยให้เซลล์เจ้าของบล็อกเสมอ
                    #   ตอนนี้ผู้ใช้เลือก "มาร์คต่างคำ" — เคสที่เทเลเซลล์แค่หาลีดให้แล้ว "เซลล์เป็นคนปิด"
                    #   = ไม่ต้องมาร์ค ADMIN (ลบมาร์คทิ้ง) → ปล่อยเป็นของเซลล์เจ้าของบล็อกตามปกติ
                    # มาร์ค ADMIN อยู่ช่องโน้ตท้ายแถว — ตำแหน่งขยับตามเดือน จึงกวาดตั้งแต่ช่องสถานะไปจนจบแถว
                    # (เทียบแบบ "ทั้งช่องเท่ากับ ADMIN" เท่านั้น จึงไม่ไปชนข้อความอื่น)
                    admin_flag = any(str(c).strip().upper() == "ADMIN" for c in row[c_status:])
                    seller_out = "ADMIN" if admin_flag else name
                    # ★ normalize เข้าตำแหน่ง canonical → โค้ดที่อ่าน (SALES_COL) ใช้ได้เหมือนเดิมทุกเดือน
                    out_row = [""] * SALES_ROW_WIDTH
                    out_row[0] = seller_out
                    for field, dst in _SALES_CANON.items():
                        src = cmap.get(field)
                        if src is not None and src < len(row):
                            out_row[dst] = row[src] or ""
                    all_rows.append(out_row + [tab, str(j + 1),
                                               str(cmap.get("result_date", "")),
                                               str(cmap.get("car_release_date", "")),
                                               str(cmap.get("status", "")),
                                               str(cmap.get("sign_date", ""))])
        _cache_set(cache_key, all_rows)
        return all_rows
    except Exception:
        return fetch_sheet("sales_reports")


def fetch_bookings_by_month_tabs() -> list[list[str]]:
    """อ่าน 'จอง' จากแท็บรายเดือน 'จอง/จบ <เดือน> 69' (ไฟล์ bookings) แทน 'รวม sheet' (เก่า).

    แท็บวางจอง(ซ้าย A-K)+จบ(ขวา) แยกกัน — อ่านแค่ A-K (ฝั่งจอง) ซึ่งตรง BOOKINGS_COL เป๊ะ
    (NO|DATE|เซลล์|ช่องทาง|พิมพ์|ยอดจอง|CODE|ADS|TYPE|CAR|ทะเบียน). year_jongs กรอง date เอง.
    ชื่อแท็บมี '/' → ใช้ values:batchGet (range เป็น query param). Failsafe → fetch_sheet('bookings').
    """
    import urllib.parse
    load_sheet_config_overrides()
    cache_key = "bookings_month_tabs"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        from .fetch_dashboard import bangkok_now
        sid = SHEET_CONFIG["bookings"]["spreadsheet_id"]
        creds = _get_credentials()
        creds.refresh(AuthRequest())
        auth = {"Authorization": f"Bearer {creds.token}"}

        now = bangkok_now()
        be2 = (now.year + 543) % 100
        want = {f"จอง/จบ {_THAI_MONTHS[m - 1]} {be2:02d}": m for m in range(1, now.month + 1)}

        meta = requests.get(f"{SHEETS_API}/{sid}?fields=sheets.properties.title",
                            headers=auth, timeout=20).json()
        titles = [s["properties"]["title"] for s in meta.get("sheets", [])]

        def _norm(t):
            return "".join(t.split())
        want_norm = {_norm(k) for k in want}
        tabs = [t for t in titles if _norm(t) in want_norm]
        if not tabs:
            return fetch_sheet("bookings")

        # batchGet หลาย range พร้อมกัน (ชื่อแท็บมี '/' → encode safe='')
        qs = "&".join(
            "ranges=" + urllib.parse.quote(f"'{t}'!A1:K400", safe="") for t in tabs
        )
        url = f"{SHEETS_API}/{sid}/values:batchGet?{qs}&valueRenderOption=FORMATTED_VALUE"
        r = requests.get(url, headers=auth, timeout=60)
        if r.status_code != 200:
            return fetch_sheet("bookings")

        all_rows: list[list[str]] = []
        for vr in r.json().get("valueRanges", []):
            all_rows.extend(vr.get("values", []))
        _cache_set(cache_key, all_rows)
        return all_rows
    except Exception:
        return fetch_sheet("bookings")


def fetch_finance_by_month_tabs() -> dict:
    """★ ส.ค.69 — นับ "เคสจบ" แยกตามไฟแนนซ์ จากฝั่ง "จบ" (บล็อกขวา) ของแท็บ 'จอง/จบ <เดือน> 69'
    (ไฟล์นับลีด/bookings — ฝั่งที่ระบบไม่เคยอ่าน · ฝั่งจองอ่านแค่ A-K ใน fetch_bookings_by_month_tabs).

    ผู้ใช้เพิ่มคอลัมน์ "ชำระแบบ" (dropdown: KK/KL/TTB/AY/NISSAN/เงินสด/...) ในฝั่งจบ → อยาก
    เห็นสรุป "เดือนไหนจบด้วยไฟแนนซ์ไหนกี่คัน" ในแดชบอร์ด (แท็บสถานะจองปล่อย + รูปรายงาน LINE).

    วิธีอ่าน (header-based — ตำแหน่งคอลัมน์ต่างกันได้ต่อแท็บ ห้าม fix index):
    - สแกน 5 แถวแรกหา header "ชำระแบบ" → ได้คอลัมน์ไฟแนนซ์ของแท็บนั้น
    - หา header สถานะปิดใกล้ๆ (คำว่า "ปิด" หรือ "สถานะ" ทางขวาของชำระแบบ) — เจอ = นับเฉพาะแถว
      ที่สถานะมีคำว่า "ปิด" · ไม่เจอ = นับทุกแถวที่ชำระแบบไม่ว่าง (ฝั่งจบ = เคสจบอยู่แล้ว)
    - เดือน = เดือนของแท็บ (แบบ _tab_month) · คืน {เดือน(int): {ชื่อไฟแนนซ์: จำนวน}} · error = {}
    """
    import urllib.parse
    load_sheet_config_overrides()
    cache_key = "finance_month_tabs"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        from .fetch_dashboard import bangkok_now
        sid = SHEET_CONFIG["bookings"]["spreadsheet_id"]
        creds = _get_credentials()
        creds.refresh(AuthRequest())
        auth = {"Authorization": f"Bearer {creds.token}"}

        now = bangkok_now()
        be2 = (now.year + 543) % 100
        want = {f"จอง/จบ {_THAI_MONTHS[m - 1]} {be2:02d}": m for m in range(1, now.month + 1)}

        meta = requests.get(f"{SHEETS_API}/{sid}?fields=sheets.properties.title",
                            headers=auth, timeout=20).json()
        titles = [s["properties"]["title"] for s in meta.get("sheets", [])]

        def _norm(t):
            return "".join(t.split())
        month_of = {_norm(k): m for k, m in want.items()}
        tabs = [t for t in titles if _norm(t) in month_of]
        if not tabs:
            return {}

        qs = "&".join(
            "ranges=" + urllib.parse.quote(f"'{t}'!A1:BZ500", safe="") for t in tabs
        )
        url = f"{SHEETS_API}/{sid}/values:batchGet?{qs}&valueRenderOption=FORMATTED_VALUE"
        r = requests.get(url, headers=auth, timeout=60)
        if r.status_code != 200:
            return {}

        out: dict[int, dict[str, int]] = {}
        for tab, vr in zip(tabs, r.json().get("valueRanges", [])):
            rows = vr.get("values", [])
            month = month_of[_norm(tab)]
            pay_col = status_col = header_row = None
            for ri, row in enumerate(rows[:5]):
                for ci, cell in enumerate(row):
                    if _norm(str(cell)) == "ชำระแบบ":
                        pay_col, header_row = ci, ri
                        break
                if pay_col is not None:
                    break
            if pay_col is None:
                continue
            # หา col สถานะปิดทางขวาของชำระแบบ (ห่างไม่เกิน 8 ช่อง — อยู่บล็อกจบเดียวกัน)
            hdr = rows[header_row]
            for ci in range(pay_col + 1, min(pay_col + 9, len(hdr))):
                head = _norm(str(hdr[ci]))
                if "ปิด" in head or "สถานะ" in head:
                    status_col = ci
                    break
            bucket = out.setdefault(month, {})
            for row in rows[header_row + 1:]:
                fin = str(row[pay_col]).strip() if pay_col < len(row) else ""
                if not fin:
                    continue
                if status_col is not None:
                    st = str(row[status_col]).strip() if status_col < len(row) else ""
                    # นับเฉพาะ "ปิด..." จริง — กัน "ยังไม่ปิด"/"ไม่ปิด" หลุดมานับ (substring "ปิด" ตรงเฉยๆ ไม่พอ)
                    if ("ปิด" not in st) or ("ไม่ปิด" in st) or ("ยังไม่" in st):
                        continue
                bucket[fin] = bucket.get(fin, 0) + 1
        _cache_set(cache_key, out)
        return out
    except Exception:
        return {}


def fetch_channel_stats_by_month_tabs() -> dict:
    """★ ส.ค.69 — "จอง/จบ แยกช่องทาง" จากแท็บ 'จอง/จบ <เดือน> 69' (ไฟล์นับลีด) ตามที่เจ้าของชี้

    ทำไมต้องอ่านจากที่นี่ (ไม่ใช่ sales_reports):
      แท็บนี้มี "คอลัมน์ช่องทางที่ล้างแล้ว" ไว้ให้สูตรใช้อยู่แล้ว = dropdown สะอาด ~27 ค่า
      ตรงกับช่องทางฝั่งลีดเป๊ะ · ต่างจาก sales_reports ที่เป็นข้อความเซลล์พิมพ์เอง (198 แบบ)
        ฝั่งจอง (บล็อกซ้าย)  D = "ช่องทางที่ใช้ใส่สูตร"  (E = ที่เซลล์พิมพ์มา — ห้ามใช้ มั่ว)
        ฝั่งจบ  (บล็อกขวา)   Y = "ที่มาสูตร"             (Z = เซลล์ใส่ — ห้ามใช้ มั่ว)

    อ่านแบบ header-based (ตำแหน่งคอลัมน์ย้ายได้ต่อแท็บ ห้าม fix index)
    คืน {"jong": {เดือน: {วัน: {ช่องทาง: n}}}, "done": {...}} — รูปเดียวกับ leadChannelByMonth
    เพื่อให้ frontend กรองตามช่วงวันที่ได้เหมือนกัน · error = {"jong": {}, "done": {}}
    """
    import urllib.parse
    load_sheet_config_overrides()
    cache_key = "channel_stats_month_tabs"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    empty = {"jong": {}, "done": {}}
    try:
        from .fetch_dashboard import bangkok_now, parse_month_day
        sid = SHEET_CONFIG["bookings"]["spreadsheet_id"]
        creds = _get_credentials()
        creds.refresh(AuthRequest())
        auth = {"Authorization": f"Bearer {creds.token}"}

        now = bangkok_now()
        be2 = (now.year + 543) % 100
        want = {f"จอง/จบ {_THAI_MONTHS[m - 1]} {be2:02d}": m for m in range(1, now.month + 1)}
        meta = requests.get(f"{SHEETS_API}/{sid}?fields=sheets.properties.title",
                            headers=auth, timeout=20).json()
        titles = [s["properties"]["title"] for s in meta.get("sheets", [])]

        def _norm(t):
            return "".join(str(t).split())

        month_of = {_norm(k): m for k, m in want.items()}
        tabs = [t for t in titles if _norm(t) in month_of]
        if not tabs:
            return empty

        qs = "&".join("ranges=" + urllib.parse.quote(f"'{t}'!A1:BZ500", safe="") for t in tabs)
        url = f"{SHEETS_API}/{sid}/values:batchGet?{qs}&valueRenderOption=FORMATTED_VALUE"
        r = requests.get(url, headers=auth, timeout=60)
        if r.status_code != 200:
            return empty

        jong: dict = {}
        done: dict = {}

        def _add(bucket, m, d, ch):
            bucket.setdefault(m, {}).setdefault(d, {})
            bucket[m][d][ch] = bucket[m][d].get(ch, 0) + 1

        for tab, vr in zip(tabs, r.json().get("valueRanges", [])):
            rows = vr.get("values", [])
            month = month_of[_norm(tab)]
            # หาแถวหัวตาราง + คอลัมน์ที่ต้องใช้ (ชื่อหัวตรงตามที่ผู้ใช้ตั้งไว้ในชีต)
            hrow = jd = jch = dd = dch = None
            for ri, row in enumerate(rows[:5]):
                for ci, cv in enumerate(row):
                    h = _norm(cv)
                    if h == "DATE" and jd is None:
                        jd, hrow = ci, ri
                    elif "ช่องทางที่ใช้ใส่สูตร" in h and jch is None:
                        jch = ci
                    elif "วันที่ปล่อย" in h and dd is None:
                        dd = ci
                    elif "ที่มาสูตร" in h and dch is None:
                        dch = ci
                if hrow is not None and jch is not None and dch is not None:
                    break
            if hrow is None:
                continue
            for row in rows[hrow + 1:]:
                def _g(i):
                    return str(row[i]).strip() if (i is not None and i < len(row)) else ""
                # ฝั่งจอง — นับตามวันจอง (B)
                ch = _g(jch)
                md = parse_month_day(_g(jd))
                if ch and md:
                    _add(jong, md[0], md[1], ch)
                # ฝั่งจบ — นับตามวันที่ปล่อย (AD)
                ch2 = _g(dch)
                md2 = parse_month_day(_g(dd))
                if ch2 and md2:
                    _add(done, md2[0], md2[1], ch2)

        out = {"jong": jong, "done": done}
        _cache_set(cache_key, out)
        return out
    except Exception:
        return empty


def fetch_live_by_month_tabs() -> list[list[str]]:
    """อ่าน live sessions จากแท็บรายเดือน 'สรุปไลฟ์สด <เดือน>' (สดกว่า 'รวม sheet' ที่ใช้สูตร — เดือนล่าสุดมัก lag)
    โครงสร้างแต่ละแท็บเหมือน 'รวม sheet' เป๊ะ (วันที่|เวลา|ทีม|ผู้ไลฟ์1-5|หัวข้อ|... → ตรง LIVE_COL).
    รวมทุกแท็บ 'สรุปไลฟ์สด *' (Mar/Apr/May/Jun...) · Failsafe → fetch_sheet('live_sessions').
    """
    import urllib.parse
    try:
        creds = _get_credentials()
        creds.refresh(AuthRequest())
        token = creds.token
        sid = SHEET_CONFIG["live_sessions"]["spreadsheet_id"]
        meta = requests.get(
            f"{SHEETS_API}/{sid}?fields=sheets.properties.title",
            headers={"Authorization": f"Bearer {token}"}, timeout=30,
        ).json()
        live_tabs = [
            s["properties"]["title"] for s in meta.get("sheets", [])
            if s["properties"]["title"].startswith("สรุปไลฟ์สด")
        ]
        all_rows: list[list[str]] = []
        for tab in live_tabs:
            enc = urllib.parse.quote(f"'{tab}'")
            r = requests.get(
                f"{SHEETS_API}/{sid}/values/{enc}?valueRenderOption=FORMATTED_VALUE",
                headers={"Authorization": f"Bearer {token}"}, timeout=30,
            )
            if r.status_code == 200:
                # แนบ tab + เลขแถวจริง (1-based · +2 เพราะตัด header แถวแรก) → ใช้ตอนแก้/ลบเขียนกลับชีต
                for i, row in enumerate(r.json().get("values", [])[1:]):
                    row = list(row)
                    while len(row) < LIVE_COL.sheet_tab:
                        row.append("")
                    row.append(tab)          # index 50
                    row.append(str(i + 2))   # index 51 — แถวจริงในชีต
                    all_rows.append(row)
        return all_rows if all_rows else fetch_sheet("live_sessions")
    except Exception:
        return fetch_sheet("live_sessions")


def list_drive_spreadsheets() -> list[dict]:
    """รายชื่อไฟล์ Google Sheets ที่ service account เข้าถึงได้ (ถูกแชร์ให้) — ทำ dropdown เลือกไฟล์แบบ n8n.
    คืน [{id, name}] เรียงตามชื่อ · error → []
    """
    import urllib.parse
    creds = _get_credentials()
    creds.refresh(AuthRequest())
    token = creds.token
    q = urllib.parse.quote("mimeType='application/vnd.google-apps.spreadsheet' and trashed=false")
    out: list[dict] = []
    page_token = None
    for _ in range(15):   # กันลูป (สูงสุด ~1500 ไฟล์)
        url = (f"https://www.googleapis.com/drive/v3/files?q={q}"
               "&fields=nextPageToken,files(id,name)&pageSize=100&orderBy=name")
        if page_token:
            url += f"&pageToken={urllib.parse.quote(page_token)}"
        r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
        if r.status_code != 200:
            break
        data = r.json()
        out.extend({"id": f.get("id"), "name": f.get("name", "")} for f in data.get("files", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return out


def list_spreadsheet_tabs(sid: str) -> list[str]:
    """รายชื่อ tab ของ spreadsheet (dropdown เลือก tab) · error → []"""
    if not sid:
        return []
    creds = _get_credentials()
    creds.refresh(AuthRequest())
    token = creds.token
    r = requests.get(
        f"{SHEETS_API}/{sid}?fields=sheets.properties.title",
        headers={"Authorization": f"Bearer {token}"}, timeout=30,
    )
    if r.status_code != 200:
        return []
    return [s["properties"]["title"] for s in r.json().get("sheets", [])]


def fetch_all_sheets() -> dict[str, list[list[str]]]:
    """Fetch all 6 sheets in parallel using threads.

    Leads ใช้ fetch_leads_by_month_tabs (อ่าน monthly tab + filter date ตรง tab month)
    เพื่อให้ตัวเลขตรงกับการนับ raw rows ใน Google Sheet ที่ admin คาดหวัง.
    """
    # in-memory cache (60s) — กัน seller page / request ซ้ำ อ่าน mirror ใหญ่ (14k leads) ใหม่ทุกครั้ง
    # (เดิม USE_SUPABASE bypass cache → ทุก /s/ load อ่าน Supabase สด ~2s) · invalidate ตอน write/sync
    cached = _cache_get("all_sheets")
    if cached is not None:
        return cached

    # (Phase 2 มิ.ย.69) อ่าน Google ตรงเสมอ — เลิก mirror sheet_cache แล้ว (Supabase เก็บแค่ผลสรุป dashboard_cache)
    # sales_reports + bookings อ่านจากแท็บรายเดือนตรง — เลิกพึ่ง 'รวม sheet' (เก่า/สูตร)
    other_keys = ["live_followups", "employees"]
    results: dict[str, list[list[str]]] = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(fetch_sheet, k): k for k in other_keys}
        futures[executor.submit(fetch_leads_by_month_tabs)] = "leads"
        futures[executor.submit(fetch_sales_by_month_tabs)] = "sales_reports"
        futures[executor.submit(fetch_bookings_by_month_tabs)] = "bookings"
        futures[executor.submit(fetch_live_by_month_tabs)] = "live_sessions"
        for future in concurrent.futures.as_completed(futures):
            key = futures[future]
            results[key] = future.result()

    result = {
        "leads": results["leads"],
        "sales_reports": results["sales_reports"],
        "bookings": results["bookings"],
        "live_sessions": results["live_sessions"],
        "live_followups": results["live_followups"],
        "employees": results["employees"],
    }
    _cache_set("all_sheets", result)
    return result
