"""
ค่าคงที่ระบบติดตามรถ — สเตป 16 ขั้น (5 เฟส), สาขา, สถานะ, เกณฑ์ flag
อิงสถานะงานจริงจากรายงานซ่อม (เช็คซ่อม/ชงล้าง/อู่สี/รอแก้ไข/รอปิดการขาย ฯลฯ)
"""

# ===== สเตป 16 ขั้น แบ่ง 5 เฟส (key, ชื่อไทย, ไอคอน Lucide) =====
STAGES = [
    # เฟส 1 — รับเข้า (จัดซื้อ)
    ("intake",       "รับเข้า",                      "log-in"),
    ("appraise",     "ประเมินซ่อม",                  "clipboard-list"),
    # เฟส 2 — ทำสภาพ (ช่าง/อู่นอก)
    ("repair",       "เช็คซ่อม",                     "wrench"),
    ("wait_paint",   "รอเข้าอู่สี",                  "clock"),
    ("paint",        "ทำสี/อู่สี",                   "paintbrush"),
    ("parts",        "สั่งของ/รออะไหล่",             "package"),
    ("upholstery",   "งานเบาะ",                      "armchair"),
    ("film",         "ติดฟิล์ม",                     "scan-line"),
    ("detail",       "ชง/ล้าง (ดีเทล)",              "sparkles"),
    # เฟส 3 — ตรวจ (เซลล์/ช่าง)
    ("qc",           "รอตรวจ (QC)",                  "clipboard-check"),
    ("rework",       "รอแก้ไข (ไม่ผ่าน)",            "triangle-alert"),
    # เฟส 4 — ทะเบียน (ฝ่ายทะเบียน)
    ("registration", "ทะเบียน (โอน/ภาษี/พ.ร.บ./ป้าย)", "file-text"),
    # เฟส 5 — ขาย (เซลล์)
    ("show",         "รถพร้อมขาย/หน้าร้าน",          "store"),
    ("reserve",      "จอง",                          "handshake"),
    ("finance",      "จัดไฟแนนซ์",                   "landmark"),
    ("closing",      "รอปิดการขาย",                  "file-signature"),
    ("sold",         "ขายแล้ว",                      "banknote"),
]

# เฟส (key, ชื่อไทย, [stage keys]) — ใช้จัดกลุ่มแสดงผล
PHASES = [
    ("intake_phase", "รับเข้า",  ["intake", "appraise"]),
    ("recon_phase",  "ทำสภาพ",   ["repair", "wait_paint", "paint", "parts", "upholstery", "film", "detail"]),
    ("qc_phase",     "ตรวจ",     ["qc", "rework"]),
    ("reg_phase",    "ทะเบียน",  ["registration"]),
    ("sale_phase",   "ขาย",      ["show", "reserve", "finance", "closing", "sold"]),
]

STAGE_KEYS = [s[0] for s in STAGES]
STAGE_CHOICES = [(s[0], s[1]) for s in STAGES]
STAGE_NAME = {s[0]: s[1] for s in STAGES}
STAGE_ICON = {s[0]: s[2] for s in STAGES}
STAGE_ORDER = {key: i for i, key in enumerate(STAGE_KEYS)}

# สเตปที่ push LINE เมื่อเปลี่ยนเข้า (จุดส่งต่อ/ตัดสินใจ — ไม่สแปมทุกขั้น)
STAGE_NOTIFY = {
    "intake", "repair", "paint", "qc", "rework", "registration",
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
