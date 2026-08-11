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
    ("repair_done", "ซ่อมเสร็จรอตรวจ",     "clipboard-check"),
    ("parts",      "สั่งของ/รออะไหล่",     "package"),
    ("upholstery", "งานเบาะ",              "armchair"),
    ("paint_in",   "อู่สีใน",              "paintbrush"),
    ("paint_out",  "อู่สีนอก",             "paintbrush"),
    ("paint_check", "รอตรวจสี",            "clipboard-check"),   # ★ ส.ค.69 — ฝ่ายทะเบียนตรวจงานสีหลังอู่
    ("film",       "ติดฟิล์ม",             "scan-line"),
    ("wash",       "ชงล้าง",               "sparkles"),
    # เฟส 4 — ตรวจก่อนขึ้นโชว์ (QC) · ชื่อบอกชัดว่าเป็น "คิวของ QC" ไม่ใช่ของเซลล์
    ("qc_show",    "รอ QC ตรวจ",           "clipboard-check"),
    # เฟส 5 — ขาย (เซลล์) · QC ตรวจผ่านแล้วติ๊กส่งต่อให้เซลล์มาตรวจรับก่อนขึ้นหน้าร้านจริง
    ("sales_check", "รอเซลล์ตรวจรถขึ้นโชว์", "user-check"),
    ("show",       "รถพร้อมขาย (ตรวจรถขึ้นโชว์)", "store"),
    ("reserve",    "จอง",                  "handshake"),
    ("finance",    "จัดไฟแนนซ์",           "landmark"),
    ("transport_check", "ตรวจขนส่ง",       "truck"),             # ★ ส.ค.69 — เซลล์พารถตรวจขนส่ง (แทนรอปิดการขายของเซลล์)
    ("closing",    "รอปิดการขาย",          "file-signature"),    # เหลือฝ่ายทะเบียนเท่านั้น (ส.ค.69)
    # เฟส 6 — ปล่อยรถ (บังคับแนบรูป/วิดีโอ) · ★ ส.ค.69: ปล่อยรถไม่จบแล้ว (เซลล์เก็บรูปต่อได้)
    # กด "ขายแล้ว" ถึงจบจริง → status=sold หลุดบอร์ดไปหน้ารถขายแล้ว
    ("qc_release", "ตรวจรถรอปล่อย",        "clipboard-check"),
    ("release",    "ปล่อยรถ (ส่งรูปปล่อยรถ)", "banknote"),
    ("sold",       "ขายแล้ว",              "badge-check"),
]

# เฟส (key, ชื่อไทย, [stage keys]) — จัดกลุ่มแสดงผล
PHASES = [
    ("intake_phase", "รับเข้า",  ["intake", "photo_wait"]),
    ("recon_phase",  "ทำสภาพ",   ["repair", "repair_done", "parts", "upholstery", "paint_in", "paint_out", "paint_check", "film", "wash", "qc_show"]),
    ("sale_phase",   "ขาย",      ["sales_check", "show", "reserve", "finance", "transport_check", "closing"]),
    ("release_phase","ปล่อยรถ",  ["qc_release", "release", "sold"]),
]

STAGE_KEYS = [s[0] for s in STAGES]
STAGE_CHOICES = [(s[0], s[1]) for s in STAGES]
STAGE_NAME = {s[0]: s[1] for s in STAGES}
STAGE_ICON = {s[0]: s[2] for s in STAGES}
STAGE_ORDER = {key: i for i, key in enumerate(STAGE_KEYS)}

# สเตปที่ push LINE เมื่อเปลี่ยนเข้า (จุดส่งต่อ/ตัดสินใจ — ไม่สแปมทุกขั้น)
STAGE_NOTIFY = {
    "intake", "photo_wait", "repair", "repair_done", "paint_in", "paint_out", "paint_check", "wash",
    "qc_show", "sales_check", "show", "reserve", "finance", "transport_check", "closing",
    "qc_release", "release", "sold",
}

# สเตปที่ถือว่า "ขึ้นหน้าร้าน" -> ตั้ง frontline_at (จุดจบ T2L)
FRONTLINE_STAGE = "show"
# สีการ์ดตอนถึงหน้าร้านแล้ว — เขียว = จบสายทำสภาพ พร้อมขาย (ทับสีความด่วน)
FRONTLINE_COLOR = "#16a34a"

# สเตปช่วงปลาย (ขาย/ปล่อย)
OK_STAGES = {"show", "reserve", "finance", "transport_check", "closing", "qc_release", "release", "sold"}

# ===== ความด่วน (priority) — สีการ์ดมาจากนี่ (เลือกมือ · แทนวันค้างอัตโนมัติ) =====
# ★ ส.ค.69 — เอา "ยังไม่ได้ถ่ายรูป" ออกจากที่นี่ ไปเป็น "ธงงานค้าง" (CAR_FLAGS) แทน
#   เพราะเป็นคนละเรื่องกับความด่วน · ช่องเดียวเลือกได้ค่าเดียว → ติดธงแล้วบอกด่วนไม่ได้
PRIORITY_CHOICES = [
    ("urgent_high", "ด่วนมาก"),
    ("urgent",      "ด่วน"),
    ("normal",      "ปกติ"),
    ("low",         "ไม่เร่ง"),
]
PRIORITY_KEYS = [p[0] for p in PRIORITY_CHOICES]
PRIORITY_NAME = {p[0]: p[1] for p in PRIORITY_CHOICES}
PRIORITY_COLOR = {
    "urgent_high": "#dc2626", "urgent": "#ea580c", "normal": "#eab308", "low": "#d1d5db",
}
DEFAULT_PRIORITY = "normal"

# ===== ธงงานค้าง (flags) — ติ๊กได้หลายอันพร้อมกัน + ใช้ร่วมกับความด่วนได้ =====
# (field, ชื่อไทย, ไอคอน Lucide, สี) · รถติดธงแล้วยังย้ายไปสเตปอื่นได้ตามปกติ ธงติดตามรถไป
CAR_FLAGS = [
    ("need_photo",   "ยังไม่ได้ถ่ายรูป",      "camera", "#2563eb"),
    ("need_content", "ยังไม่ได้ถ่ายคอนเทนต์", "video",  "#7c3aed"),
]
FLAG_KEYS = [f[0] for f in CAR_FLAGS]
FLAG_NAME = {f[0]: f[1] for f in CAR_FLAGS}
FLAG_ICON = {f[0]: f[2] for f in CAR_FLAGS}
FLAG_COLOR = {f[0]: f[3] for f in CAR_FLAGS}

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
