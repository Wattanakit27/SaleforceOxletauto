"""
ค่าคงที่ระบบติดตามรถ — สเตป 15 ขั้น (4 เฟส), สาขา, สถานะ, เกณฑ์ flag
อิงสถานะงานจริง: รับเข้า → ซ่อม(+ตรวจ) → ทำสภาพ/สี(+ตรวจ) → ล้าง(+ตรวจ) → ขาย
"""

# ===== สเตป 15 ขั้น แบ่ง 4 เฟส (key, ชื่อไทย, ไอคอน Lucide) =====
# โฟลว์: รับเข้า → ซ่อม(+ตรวจ) → ทำสภาพ/สี(+ตรวจ) → ล้าง(+ตรวจ) → ขาย
# 3 จุดตรวจ (qc_repair/qc_paint/qc_wash) = ทางแยก: ผ่าน→ไปต่อ(ข้ามได้) · ไม่ผ่าน→เด้งกลับทำใหม่ที่เดิม
# กดครั้งเดียวย้ายสเตป (out ของคนก่อน = in ของคนถัดไป) · ไม่มีขั้นทะเบียน (โอน/ภาษี/ป้าย ทำนอกระบบ)
STAGES = [
    # เฟส 1 — รับเข้า (จัดซื้อ)
    ("intake",       "รับเข้า",                      "log-in"),
    # เฟส 2 — ทำสภาพ (ช่าง/อู่นอก) + จุดตรวจ
    ("repair",       "เช็คซ่อม",                     "wrench"),
    ("qc_repair",    "ซ่อมเสร็จ รอตรวจ",             "clipboard-check"),
    ("parts",        "สั่งของ/รออะไหล่",             "package"),
    ("upholstery",   "งานเบาะ",                      "armchair"),
    ("paint",        "ทำสี/อู่สี",                   "paintbrush"),
    ("qc_paint",     "สีเสร็จ รอตรวจ",               "clipboard-check"),
    ("film",         "ติดฟิล์ม",                     "scan-line"),
    # เฟส 3 — ล้าง (ฝ่ายล้างรถ) + จุดตรวจ
    ("wash",         "ชงล้าง",                       "sparkles"),
    ("qc_wash",      "ล้างเสร็จ รอตรวจ",             "clipboard-check"),
    # เฟส 4 — ขาย (เซลล์)
    ("show",         "รถพร้อมขาย/หน้าร้าน",          "store"),
    ("reserve",      "จอง",                          "handshake"),
    ("finance",      "จัดไฟแนนซ์",                   "landmark"),
    ("closing",      "รอปิดการขาย",                  "file-signature"),
    ("sold",         "ขายแล้ว",                      "banknote"),
]

# เฟส (key, ชื่อไทย, [stage keys]) — ใช้จัดกลุ่มแสดงผล
PHASES = [
    ("intake_phase", "รับเข้า", ["intake"]),
    ("recon_phase",  "ทำสภาพ",  ["repair", "qc_repair", "parts", "upholstery", "paint", "qc_paint", "film"]),
    ("wash_phase",   "ล้าง",    ["wash", "qc_wash"]),
    ("sale_phase",   "ขาย",     ["show", "reserve", "finance", "closing", "sold"]),
]

STAGE_KEYS = [s[0] for s in STAGES]
STAGE_CHOICES = [(s[0], s[1]) for s in STAGES]
STAGE_NAME = {s[0]: s[1] for s in STAGES}
STAGE_ICON = {s[0]: s[2] for s in STAGES}
STAGE_ORDER = {key: i for i, key in enumerate(STAGE_KEYS)}

# สเตปที่ push LINE เมื่อเปลี่ยนเข้า (จุดส่งต่อ/ตัดสินใจ — ไม่สแปมทุกขั้น)
STAGE_NOTIFY = {
    "intake", "repair", "qc_repair", "paint", "qc_paint", "wash", "qc_wash",
    "show", "reserve", "finance", "closing", "sold",
}

# สเตปที่ถือว่า "ขึ้นหน้าร้าน" -> ตั้ง frontline_at (จุดจบ T2L)
FRONTLINE_STAGE = "show"

# สเตปช่วงปลาย (ถือว่าเขียวเสมอ ไม่ต้องเตือนค้าง)
OK_STAGES = {"show", "reserve", "finance", "closing", "sold"}

# ===== สาขา (prefix รหัสรถ) =====
BRANCH_CHOICES = [
    ("CB", "สาขาชลบุรี"),
    ("SP", "สาขาสมุทรปราการ"),
]
BRANCH_PREFIX = dict(BRANCH_CHOICES)
DEFAULT_BRANCH = "CB"

# ===== สถานะรวม (ภาพรวม นอกเหนือสเตปไลน์) =====
STATUS_CHOICES = [
    ("active", "กำลังดำเนินการ"),
    ("sold", "ขายแล้ว"),
    ("hold", "พัก/ระงับ (รถบริษัท/CEO/ยืม)"),
]

# ===== สถานะเล่ม/ทะเบียน (ฝ่ายทะเบียนใช้) =====
BOOK_STATUS_CHOICES = [
    ("", "— เลือกสถานะเล่ม —"),
    ("ready", "พร้อมเล่ม"),
    ("waiting", "รอเล่ม"),
    ("transferring", "ระหว่างโอน"),
    ("copy", "ใช้สำเนา"),
    ("finance", "ติดไฟแนนซ์"),
]

# ===== เกณฑ์ T2L / flag (วัน) =====
T2L_TARGET_DAYS = 5     # KPI: T2L ≤ 5 วัน
STUCK_AMBER_DAYS = 2    # ค้างสเตป ≥ 2 วัน = เหลือง
STUCK_RED_DAYS = 3      # ค้างสเตป > 3 วัน = แดง
