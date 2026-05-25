"""Per-seller secret tokens for personal dashboard URLs.

แต่ละเซลล์มี token แบบสุ่ม 6-10 หลัก ใช้เป็น URL ส่วนตัวที่
/s/<token>/ — เซลล์เห็นเฉพาะข้อมูลของตัวเอง และเดา URL ของคนอื่นไม่ได้.

Source of truth:
1. **Sheet "ตั้งค่าเซลล์" column D** — primary (admin แก้ผ่าน UI ได้)
2. **`_FALLBACK_TOKENS` ด้านล่าง** — ใช้เมื่อ sheet ว่าง/error (เซลล์เก่าก่อนเปลี่ยนระบบ)

ถ้าเซลล์ใหม่ยังไม่มี token ใน sheet → `admin_seller_config` จะ auto-gen ตอน save
และเขียนกลับลง sheet ทันที (idempotent — ครั้งต่อไปจะอ่านได้)
"""
import secrets


# ── Fallback tokens — ใช้ถ้า sheet โหลดไม่ได้ ──
# เก็บ tokens เดิมไว้กัน URL ของเซลล์เก่าพัง (ลิงก์ที่ส่งไปแล้วยังใช้ได้)
_FALLBACK_TOKENS: dict[str, str] = {
    "โอ๊ต":   "84173629",
    "เฟิร์ส": "9264817",
    "เจ":     "53716294",
    "บอย":    "642893",
    "นั่ม":   "71649382",
    "กอล์ฟ":  "9283716405",
    "นวล":    "5273849",
    "เก้า":   "83649275",
    "มด":     "4716923",
    "มัท":    "82947163",
    "อุ้ม":   "6157394",
    "แซน":    "38472916",
    "ใบตอง":  "728649385",
}


# ── Mutable runtime state (populated by refresh_from_sheet) ──
# อย่า reassign — ใช้ .clear() + .update() เท่านั้น (กัน import binding หาย)
SELLER_TOKENS: dict[str, str] = dict(_FALLBACK_TOKENS)
TOKEN_TO_SELLER: dict[str, str] = {token: name for name, token in SELLER_TOKENS.items()}


def update_tokens(mapping: dict[str, str]) -> None:
    """Replace runtime tokens in-place. เรียกจาก refresh_from_sheet().
    Merge with fallback — ถ้า sheet ไม่มีเซลล์เก่าบางคน ก็ยังใช้ token เดิมได้
    """
    merged = dict(_FALLBACK_TOKENS)   # base = fallback
    merged.update(mapping)             # sheet ทับ fallback
    SELLER_TOKENS.clear()
    SELLER_TOKENS.update(merged)
    TOKEN_TO_SELLER.clear()
    for name, token in merged.items():
        if token:
            TOKEN_TO_SELLER[token] = name


def seller_from_token(token: str) -> str | None:
    """คืนชื่อเซลล์จาก token. ตรวจ 2 source ตามลำดับ:
    1. SELLER_TOKENS (hardcode + sheet — legacy 13 คน เก่า)
    2. LINE user_id ใน employees sheet (เซลล์ใหม่ใช้ user_id เป็น URL ตรงๆ)

    คืน None ถ้าไม่พบ → seller_dashboard จะแสดง "ลิงก์ไม่ถูกต้อง"
    """
    # 1. legacy tokens (เร็ว, ไม่ต้องเรียก API)
    if token in TOKEN_TO_SELLER:
        return TOKEN_TO_SELLER[token]

    # 2. LINE user_id lookup จาก employees sheet
    try:
        from .google_sheets import fetch_sheet, cell, EMPLOYEE_COL as EM
        from .constants import normalize_seller, ALL_SELLERS
        for r in fetch_sheet("employees"):
            if cell(r, EM.user_id) == token:
                nickname = cell(r, EM.nickname).strip()
                normalized = normalize_seller(nickname) or nickname
                # ตรวจว่าเซลล์อยู่ใน TEAMS จริง (กัน user_id อื่นๆ ที่ไม่ใช่เซลล์)
                if normalized in ALL_SELLERS:
                    return normalized
                break
    except Exception:
        pass

    return None


def generate_token(length: int = 8) -> str:
    """สุ่ม token (digit only, default 8 หลัก) — ใช้แค่ tools ภายในกรณีพิเศษ
    (ระบบจริงใช้ LINE user_id เป็น URL แทน)"""
    return "".join(secrets.choice("0123456789") for _ in range(length))
