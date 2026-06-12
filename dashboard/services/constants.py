"""Constants — ported from lib/constants.ts"""

UPD_TGT = 4
LIVE_TGT = 4
PAGE_SIZE = 15

# Seller name normalization
# - alias ของเซลล์ปัจจุบัน (ชื่อสะกดต่างใน sheet → ชื่อมาตรฐานใน config)
# - alias ของเซลล์เก่า (รวม Ice→ไอซ์, ตาต้า→ต้า เพื่อไม่ให้ตัวเลขกระจาย)
SELLER_MAP = {
    "เจเจ": "เจ",
    "กลอฟ": "กอล์ฟ",
    "แซนด์": "แซน",
    "Ice": "ไอซ์",
    "ICE": "ไอซ์",
    "ice": "ไอซ์",
    "ตาต้า": "ต้า",
    "นั้ม": "นั่ม",   # ไม้โท→ไม้เอก — ชีต sales ม.ค.-มี.ค. สะกดผิด ทำให้ปล่อยของนั่มหาย
}


def normalize_seller(name: str) -> str:
    return SELLER_MAP.get(name, name)


# Teams & Targets
# Default values (fallback ถ้าโหลด sheet "ตั้งค่าเซลล์" ไม่ได้)
TEAMS = {
    "A": ["โอ๊ต", "เฟิร์ส", "เจ", "บอย", "นั่ม", "กอล์ฟ"],
    "B": ["นวล", "เก้า", "มด", "มัท", "อุ้ม", "แซน"],
    "C": ["ใบตอง"],
}

TARGETS = {
    "โอ๊ต": 8, "เฟิร์ส": 12, "เจ": 7, "บอย": 8, "นั่ม": 6, "กอล์ฟ": 2,
    "นวล": 10, "เก้า": 8, "มด": 6, "มัท": 8, "อุ้ม": 8, "แซน": 2,
    "ใบตอง": 2,
}

ALL_SELLERS = [s for members in TEAMS.values() for s in members]

TEAM_ID = {}
for tid, members in TEAMS.items():
    for name in members:
        TEAM_ID[name] = tid

# เซลล์ที่ได้สิทธิ์ "แอดมินด้วย" (ติ๊กคอลัมน์ "แอดมิน" ในชีตตั้งค่าเซลล์)
# → login ด้วย LINE user_id แล้วได้ position=admin แต่ยังนับเป็นเซลล์ปกติ
# mutate in-place เท่านั้น (.clear()/.update()) — กัน import binding หาย
ADMIN_SELLERS: set[str] = set()

# รายชื่อ LINE user_id ที่เป็นแอดมิน "โดยตรง" (เทเลเซลล์/ออฟฟิศ ที่ไม่ใช่เซลล์ใน TEAMS)
# อ่านจากชีต "ตั้งค่าแอดมิน" — แก้ผ่านปุ่ม 👑 จัดการแอดมิน หรือแก้ในชีตตรงๆ
ADMIN_USER_IDS: set[str] = set()


def _is_truthy_flag(v: str) -> bool:
    return (v or "").strip().lower() in ("true", "1", "yes", "y", "✓", "✔", "admin", "ใช่")


def load_admin_user_ids() -> set[str]:
    """อ่านชีต 'ตั้งค่าแอดมิน' → set ของ LINE user_id ที่เป็นแอดมิน. mutate ADMIN_USER_IDS in-place.
    ถ้าชีตยังไม่มี/error → คงค่าเดิม (ไม่ล้าง) เพื่อกันแอดมินหลุดสิทธิ์ชั่วคราว."""
    try:
        from .google_sheets import fetch_sheet, cell, ADMIN_CONFIG_COL as AC
        rows = fetch_sheet("admin_config")
    except Exception:
        return ADMIN_USER_IDS
    new_ids = set()
    for r in rows:
        uid = cell(r, AC.user_id).strip()
        # LINE user_id ขึ้นต้น U ยาว 33 ตัว — กรอง header/ขยะออก
        if uid.startswith("U") and len(uid) >= 20:
            new_ids.add(uid)
    ADMIN_USER_IDS.clear()
    ADMIN_USER_IDS.update(new_ids)
    return ADMIN_USER_IDS


def refresh_from_sheet() -> bool:
    """อ่าน sheet "ตั้งค่าเซลล์" แล้ว mutate TEAMS/TARGETS/ALL_SELLERS/TEAM_ID in-place.

    คืน True ถ้าโหลดสำเร็จ, False ถ้า sheet ไม่มีหรือ error (จะ fallback default).
    Import google_sheets ใน function เพื่อกัน circular import.

    หมายเหตุ: ไม่ load tokens จาก sheet แล้ว — seller URL ใช้ LINE user_id จาก employees sheet
    (ดู seller_tokens.seller_from_token() ที่ fall back ไปอ่าน employees)
    """
    try:
        from .google_sheets import fetch_sheet, cell, cell_num, SELLER_CONFIG_COL as SC
    except Exception:
        return False
    try:
        rows = fetch_sheet("sellers_config")
    except Exception:
        return False

    new_teams: dict[str, list[str]] = {}
    new_targets: dict[str, int] = {}
    new_admins: set[str] = set()
    for r in rows:
        name = SELLER_MAP.get(cell(r, SC.nickname).strip(), cell(r, SC.nickname).strip())
        if not name or name in ("ชื่อเล่น", "nickname", "Nickname"):
            continue
        team = cell(r, SC.team).strip().upper()
        target = int(cell_num(r, SC.target) or 0)
        if not team:
            continue
        new_teams.setdefault(team, []).append(name)
        new_targets[name] = target
        if _is_truthy_flag(cell(r, SC.is_admin)):
            new_admins.add(name)

    if not new_targets:
        return False  # sheet ว่าง → fallback

    # mutate in-place — โมดูลอื่นที่ import TEAMS/TARGETS แล้ว reference dict ตัวเดียวกัน เห็นค่าใหม่
    TEAMS.clear()
    TEAMS.update(new_teams)
    TARGETS.clear()
    TARGETS.update(new_targets)

    ALL_SELLERS.clear()
    ALL_SELLERS.extend(s for ms in TEAMS.values() for s in ms)

    TEAM_ID.clear()
    TEAM_ID.update({n: tid for tid, ms in TEAMS.items() for n in ms})

    ADMIN_SELLERS.clear()
    ADMIN_SELLERS.update(new_admins)
    return True

RJ_TYPES = ["RJ", "Hot RJ", "Hot RB"]

# Executive LINE user_ids — รับ Overview Flex (สรุปยอดรวมทีม)
# เปลี่ยนได้ผ่าน env var EXECUTIVE_USER_IDS (comma-separated)
import os as _os
EXECUTIVE_USER_IDS = [
    uid.strip() for uid in (
        _os.getenv("EXECUTIVE_USER_IDS", "U1cb2b916b062d2ef42c6800d21165083") or ""
    ).split(",") if uid.strip()
]

# แอดมินสูงสุด (hardcode/break-glass) — LINE user_id ที่เป็น "แอดมินใหญ่" เสมอ ไม่ขึ้นกับชีต
# ใช้กันแอดมินหลักล็อกตัวเองออก หรือยังไม่มีใน employees → login ผ่าน LINE ได้ทันทีในฐานะ admin
# เพิ่ม/แก้ได้ผ่าน env SUPER_ADMIN_IDS (comma-separated) — รวมกับ default ด้านล่าง
SUPER_ADMIN_IDS: set[str] = {
    "U6bf1d72cf1d7e237c3a5c9848dde9bf4",
    "Ueac80f8644c5d1cfdbec61b1d91caee2",
    "U481c3a42fd2f32cadea175131492d958",
    "U1cb2b916b062d2ef42c6800d21165083",
} | {
    uid.strip() for uid in (_os.getenv("SUPER_ADMIN_IDS", "") or "").split(",") if uid.strip()
}

STATUS_COLOR = {
    "จอง": "#f59e0b",
    "รอเซ็นต์": "#3b82f6",
    "รอผล": "#f97316",
    "รอปล่อย": "#8b5cf6",
    "ปล่อย": "#10b981",
    "รีเจ็ก": "#ef4444",
}

STATUS_ORDER = ["จอง", "รอเซ็นต์", "รอผล", "รอปล่อย", "ปล่อย", "รีเจ็ก"]

TEAM_COLORS = {
    "A": "var(--tA)",
    "B": "var(--tB)",
    "C": "var(--tC)",
    "ADMIN": "var(--amber-mid)",
}

TEAM_NAMES = {
    "A": "ทีม A",
    "B": "ทีม B",
    "C": "ทีม C",
    "ADMIN": "ADMIN",
}

MONTHS_SHORT = [
    "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
    "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
]

MONTHS_FULL = [
    "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
    "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
]

LT_COLORS = {
    "NLD": "var(--blue)",
    "BLD": "var(--green)",
    "TLD": "var(--purple-mid)",
    "WLD": "var(--amber-mid)",
    "HLD": "var(--green-mid)",
    "RJ": "var(--red)",
    "Hot RJ": "var(--red)",
    "Hot RB": "var(--red-mid)",
}
