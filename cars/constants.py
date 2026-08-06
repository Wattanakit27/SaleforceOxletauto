"""
ค่าคงที่ระบบติดตามรถ — สเตป 16 ขั้น (4 เฟส), สาขา, สถานะ, ความด่วน (priority)
โฟลว์: รับเข้า → ถ่ายรูป(โปรดักชัน) → ทำสภาพ(ซ่อม/สี/เบาะ/ฟิล์ม/ล้าง) → ตรวจขึ้นโชว์(QC) → ขาย → ตรวจ+ปล่อยรถ(QC)
★ สีการ์ด = ความด่วน (priority) ที่เลือกมือ · ไม่ใช่วันค้างอัตโนมัติ · ปล่อยรถ = จบ (ไม่มี "ขายแล้ว")
"""

# ===== สเตป 16 ขั้น (key, ชื่อไทย, ไอคอน Lucide) =====
STAGES = [
    # เฟส 1 — รับเข้า (จัดซื้อ)
    ("intake",     "รับเข้า",              "log-in"),
    # เฟส 2 — ถ่ายรูป (โปรดักชัน · ส่งต่อไปซ่อม/สี/ล้าง แล้วแต่)
    ("photo_wait", "รถรอถ่ายรูป",          "camera"),
    # เฟส 3 — ทำสภาพ (ช่าง/อู่สีใน-นอก/ล้าง · อู่นอกยุบเข้าฝ่ายทะเบียน)
    ("repair",     "เช็คซ่อม",             "wrench"),
    ("parts",      "สั่งของ/รออะไหล่",     "package"),
    ("upholstery", "งานเบาะ",              "armchair"),
    ("paint_in",   "อู่สีใน",              "paintbrush"),
    ("paint_out",  "อู่สีนอก",             "paintbrush"),
    ("film",       "ติดฟิล์ม",             "scan-line"),
    ("wash",       "ชงล้าง",               "sparkles"),
    # เฟส 4 — ตรวจก่อนขึ้นโชว์ (QC)
    ("qc_show",    "รอตรวจรถขึ้นโชว์",     "clipboard-check"),
    # เฟส 5 — ขาย (เซลล์)
    ("show",       "รถพร้อมขาย/หน้าร้าน",  "store"),
    ("reserve",    "จอง",                  "handshake"),
    ("finance",    "จัดไฟแนนซ์",           "landmark"),
    ("closing",    "รอปิดการขาย",          "file-signature"),
    # เฟส 6 — ปล่อยรถ (QC · บังคับแนบรูป/วิดีโอ) · ปล่อยรถ = จบ
    ("qc_release", "ตรวจรถรอปล่อย",        "clipboard-check"),
    ("release",    "ปล่อยรถ",              "banknote"),
]

# เฟส (key, ชื่อไทย, [stage keys]) — จัดกลุ่มแสดงผล
PHASES = [
    ("intake_phase", "รับเข้า",  ["intake", "photo_wait"]),
    ("recon_phase",  "ทำสภาพ",   ["repair", "parts", "upholstery", "paint_in", "paint_out", "film", "wash", "qc_show"]),
    ("sale_phase",   "ขาย",      ["show", "reserve", "finance", "closing"]),
    ("release_phase","ปล่อยรถ",  ["qc_release", "release"]),
]

STAGE_KEYS = [s[0] for s in STAGES]
STAGE_CHOICES = [(s[0], s[1]) for s in STAGES]
STAGE_NAME = {s[0]: s[1] for s in STAGES}
STAGE_ICON = {s[0]: s[2] for s in STAGES}
STAGE_ORDER = {key: i for i, key in enumerate(STAGE_KEYS)}

# สเตปที่ push LINE เมื่อเปลี่ยนเข้า (จุดส่งต่อ/ตัดสินใจ — ไม่สแปมทุกขั้น)
STAGE_NOTIFY = {
    "intake", "photo_wait", "repair", "paint_in", "paint_out", "wash",
    "qc_show", "show", "reserve", "finance", "closing", "qc_release", "release",
}

# สเตปที่ถือว่า "ขึ้นหน้าร้าน" -> ตั้ง frontline_at (จุดจบ T2L)
FRONTLINE_STAGE = "show"

# สเตปช่วงปลาย (ขาย/ปล่อย)
OK_STAGES = {"show", "reserve", "finance", "closing", "qc_release", "release"}

# ===== ความด่วน (priority) — สีการ์ดมาจากนี่ (เลือกมือ · แทนวันค้างอัตโนมัติ) =====
PRIORITY_CHOICES = [
    ("urgent_high", "ด่วนมาก"),
    ("urgent",      "ด่วน"),
    ("normal",      "ปกติ"),
    ("low",         "ไม่เร่ง"),
    ("photo_wait",  "รอถ่ายรูปยังไม่เสร็จ"),
]
PRIORITY_KEYS = [p[0] for p in PRIORITY_CHOICES]
PRIORITY_NAME = {p[0]: p[1] for p in PRIORITY_CHOICES}
PRIORITY_COLOR = {
    "urgent_high": "#dc2626", "urgent": "#ea580c", "normal": "#eab308",
    "low": "#d1d5db", "photo_wait": "#2563eb",
}
DEFAULT_PRIORITY = "normal"

# สเตปที่ "บังคับแนบรูป/วิดีโอ" ก่อนเปลี่ยนเข้า (ตรวจปล่อย/ปล่อยรถ)
STAGE_FORCE_MEDIA = {"qc_release", "release"}

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
