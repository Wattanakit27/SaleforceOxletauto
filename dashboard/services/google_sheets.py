"""Google Sheets API — ported from lib/google-sheets.ts"""
import asyncio
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


def _resolve_lead_colmap(header: list) -> dict:
    """header row → {canonical_index: source_index} จับคู่ตามชื่อหัวตาราง (เจอตัวแรกชนะ)."""
    norm = [_norm_header(c) for c in header]
    colmap: dict[int, int] = {}
    for canon_idx, aliases in _LEAD_FIELD_ALIASES:
        targets = {_norm_header(a) for a in aliases}
        for src_idx, hv in enumerate(norm):
            if hv and hv in targets:
                colmap[canon_idx] = src_idx
                break
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
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
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
    encoded = urllib.parse.quote(f"'{tab}'!A:Z")

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
        colmap = _resolve_lead_colmap(vals[0])
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


# ── Fetch helpers ──
def cell(row: list[str], index: int) -> str:
    if index < len(row):
        return (row[index] or "").strip()
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
        from .supabase_client import get_sheet_config
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
            # เก็บ header (แถวแรก) ไว้ด้วย เพื่อ map คอลัมน์ตามชื่อหัวตาราง
            encoded = urllib.parse.quote(f"'{tab}'")
            url = f"{SHEETS_API}/{sid}/values/{encoded}?valueRenderOption=FORMATTED_VALUE"
            r = requests.get(url, headers=headers_auth, timeout=30)
            return r.json().get("values", []) if r.status_code == 200 else []

        # Fetch all tabs in parallel
        tab_rows: dict[str, tuple[int, list[list[str]]]] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
            futs = {ex.submit(_fetch_tab, tab): (m_int, tab) for m_int, tab in monthly_tabs}
            for fut in concurrent.futures.as_completed(futs):
                m_int, tab = futs[fut]
                try:
                    tab_rows[tab] = (m_int, fut.result())
                except Exception:
                    tab_rows[tab] = (m_int, [])

        # ดึง parse_date จาก fetch_dashboard (avoid circular import — late import)
        from .fetch_dashboard import parse_date

        all_rows: list[list[str]] = []
        for m_int, tab in monthly_tabs:
            _, vals = tab_rows.get(tab, (m_int, []))
            if not vals:
                continue
            # map คอลัมน์ตามชื่อหัวตารางของ tab นี้ (แต่ละเดือน layout อาจต่างกัน)
            colmap = _resolve_lead_colmap(vals[0])
            for raw in vals[1:]:
                row = _normalize_lead_row(raw, colmap)
                d = parse_date(cell(row, LEADS_COL.received_date))
                if d and d.month == m_int:
                    all_rows.append(row)
        _cache_set(cache_key, all_rows)
        return all_rows
    except Exception:
        # graceful fallback — อย่างน้อยมีข้อมูลจาก "รวม sheet"
        return fetch_sheet("leads")


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

        known = {normalize_seller(s) for s in ALL_SELLERS}

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
            for k, (mi, raw_name) in enumerate(markers):
                name = normalize_seller(raw_name)
                if name not in known:
                    continue   # ตัด marker ขยะ / เซลล์ไม่อยู่ในรายชื่อจริง
                end = markers[k + 1][0] if k + 1 < len(markers) else len(vals)
                for j in range(mi + 1, end):
                    row = vals[j]
                    seq = str(row[1] if len(row) > 1 else "").strip()
                    status = str(row[13] if len(row) > 13 else "").strip()
                    if not seq.isdigit() or not status:
                        continue   # ข้าม sub-header / แถวว่าง (ตรง filter N<>"" ในสูตร)
                    all_rows.append([name] + [(row[i] if i < len(row) else "") for i in range(1, 28)])
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


def fetch_all_sheets() -> dict[str, list[list[str]]]:
    """Fetch all 6 sheets in parallel using threads.

    Leads ใช้ fetch_leads_by_month_tabs (อ่าน monthly tab + filter date ตรง tab month)
    เพื่อให้ตัวเลขตรงกับการนับ raw rows ใน Google Sheet ที่ admin คาดหวัง.
    """
    # ถ้าเปิด USE_SUPABASE → อ่านจาก sheet_cache (mirror) แทน Google
    # ถ้า cache ขาด/error → fallback ไปอ่าน Google ตรง (ปลอดภัย)
    if getattr(settings, "USE_SUPABASE", False):
        try:
            from .supabase_client import fetch_all_from_supabase
            return fetch_all_from_supabase()
        except Exception:
            pass

    # sales_reports + bookings อ่านจากแท็บรายเดือนตรง — เลิกพึ่ง 'รวม sheet' (เก่า/สูตร)
    other_keys = ["live_sessions", "live_followups", "employees"]
    results: dict[str, list[list[str]]] = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(fetch_sheet, k): k for k in other_keys}
        futures[executor.submit(fetch_leads_by_month_tabs)] = "leads"
        futures[executor.submit(fetch_sales_by_month_tabs)] = "sales_reports"
        futures[executor.submit(fetch_bookings_by_month_tabs)] = "bookings"
        for future in concurrent.futures.as_completed(futures):
            key = futures[future]
            results[key] = future.result()

    return {
        "leads": results["leads"],
        "sales_reports": results["sales_reports"],
        "bookings": results["bookings"],
        "live_sessions": results["live_sessions"],
        "live_followups": results["live_followups"],
        "employees": results["employees"],
    }
