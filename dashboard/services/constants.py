"""Constants — ported from lib/constants.ts"""

UPD_TGT = 4
LIVE_TGT = 4
PAGE_SIZE = 15

# Seller name normalization
SELLER_MAP = {
    "เจเจ": "เจ",
    "กลอฟ": "กอล์ฟ",
    "แซนด์": "แซน",
}


def normalize_seller(name: str) -> str:
    return SELLER_MAP.get(name, name)


# Teams & Targets
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

RJ_TYPES = ["RJ", "Hot RJ", "Hot RB"]

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
