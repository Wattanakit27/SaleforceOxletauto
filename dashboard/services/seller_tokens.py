"""Per-seller secret tokens for personal dashboard URLs.

แต่ละเซลล์มี token แบบสุ่ม 6-10 หลัก ใช้เป็น URL ส่วนตัวที่
/s/<token>/ — เซลล์เห็นเฉพาะข้อมูลของตัวเอง และเดา URL ของคนอื่นไม่ได้.

ถ้าต้องการ rotate token ของเซลล์คนใด ให้แก้ค่าตรงนี้ได้เลย.
"""

# ── nickname → secret token (สุ่ม 6-10 หลัก) ──
SELLER_TOKENS: dict[str, str] = {
    "โอ๊ต":   "84173629",      # 8 หลัก
    "เฟิร์ส": "9264817",        # 7 หลัก
    "เจ":     "53716294",       # 8 หลัก
    "บอย":    "642893",         # 6 หลัก
    "นั่ม":   "71649382",       # 8 หลัก
    "กอล์ฟ":  "9283716405",     # 10 หลัก
    "นวล":    "5273849",        # 7 หลัก
    "เก้า":   "83649275",       # 8 หลัก
    "มด":     "4716923",        # 7 หลัก
    "มัท":    "82947163",       # 8 หลัก
    "อุ้ม":   "6157394",        # 7 หลัก
    "แซน":    "38472916",       # 8 หลัก
    "ใบตอง":  "728649385",      # 9 หลัก
}

# ── token → nickname (lookup ฝั่ง view ใช้ตัวนี้) ──
TOKEN_TO_SELLER: dict[str, str] = {token: name for name, token in SELLER_TOKENS.items()}


def seller_from_token(token: str) -> str | None:
    """คืนชื่อเซลล์จาก token, ถ้าไม่พบคืน None."""
    return TOKEN_TO_SELLER.get(token)
