"""Google Sheets API — ported from lib/google-sheets.ts"""
import asyncio
import concurrent.futures
from typing import Any

import requests
from google.auth.transport.requests import Request as AuthRequest
from google.oauth2.service_account import Credentials
from django.conf import settings

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
}

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

class SALES_COL:
    sales_rep = 0; order_num = 1; date = 2; channel = 3; lead_code = 4
    booking_no = 5; customer_name = 6; phone = 7; car_detail = 8
    car_year = 9; license_plate = 10; sale_price = 11; deposit_amount = 12
    status = 13; sign_date = 14; finance_main = 15; finance_backup = 16
    grade = 17; doc_complete_date = 18; result_date = 19; note = 20
    car_release_date = 21

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
    # Row format: ชื่อเล่น | ทีม (A/B/C) | เป้าต่อเดือน
    nickname = 0
    team = 1
    target = 2

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


def fetch_sheet(config_key: str) -> list[list[str]]:
    """Fetch a single sheet → list of row arrays (skip header)."""
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
    return rows[1:]  # skip header


def fetch_all_sheets() -> dict[str, list[list[str]]]:
    """Fetch all 6 sheets in parallel using threads."""
    keys = ["leads", "sales_reports", "bookings", "live_sessions", "live_followups", "employees"]
    results = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(fetch_sheet, k): k for k in keys}
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
