"""ค่าคงที่ระบบเบิก-คืนรถ — อิงจากพฤติกรรมจริงในกลุ่ม LINE (วิเคราะห์ log ส.ค.69)"""

# วัตถุประสงค์การเบิก — จัดกลุ่มจากที่คนพิมพ์จริงในกลุ่ม 5 วัน
# (ตรวจขนส่ง 6 ครั้ง · เข้าศูนย์/ซ่อม 8 · ส่งลูกค้า/ให้ลูกค้าดู 5 · ย้ายสาขา 6 · ไฟแนนซ์ 3 · งานทั่วไป 4)
# เป็นปุ่มให้กด ไม่ต้องพิมพ์ → ได้ข้อมูลที่เอาไปนับได้ (ของเดิมพิมพ์อิสระ นับไม่ได้เลย)
PURPOSES = [
    ("transport", "ตรวจขนส่ง", "clipboard-check"),
    ("service", "เข้าศูนย์ / ซ่อม / ตั้งศูนย์", "wrench"),
    ("customer", "ส่งลูกค้า / ให้ลูกค้าดูรถ", "user"),
    ("finance", "จัดไฟแนนซ์ / เซ็นสัญญา", "credit-card"),
    ("move", "ย้ายสาขา / ไปจอด", "map-pin"),
    ("errand", "งานทั่วไป (ซื้อของ/ไปรษณีย์/รับส่ง)", "package"),
]
PURPOSE_NAME = {k: n for k, n, _ in PURPOSES}
PURPOSE_KEYS = [k for k, _, _ in PURPOSES]

# ★ เช็คลิสต์รูปตอนเบิก — "บังคับน้อย ใช้ได้จริง" มากกว่า "บังคับเยอะ ไม่มีใครทำ"
#   จาก log: คนส่ง 1-3 รูปเป็นส่วนใหญ่ · ที่ออฟฟิศไล่ทวงคือ "รูปไม่ครบ" ซึ่งไม่เคยนิยามว่าครบคืออะไร
#   → บังคับ 2 อย่างที่จำเป็นต่อการพิสูจน์สภาพ/ระยะ ที่เหลือเป็นตัวเลือก (ถ่ายได้ก็ดี)
#   แก้ได้ภายหลังผ่าน ChecklistConfig/ChecklistItem ในฐานข้อมูล (โครงรองรับอยู่แล้ว)
DEFAULT_CHECKLIST = [
    dict(key="around",   label="รถรอบคัน (อย่างน้อย 2 มุม)", media_type="photo", required=True,  min_count=2),
    dict(key="odometer", label="เลขไมล์ + หน้าปัด",          media_type="photo", required=True,  min_count=1,
         special_rule="ต้องอ่านเลขไมล์ออก"),
    dict(key="engine_bay", label="ห้องเครื่อง",              media_type="photo", required=False, min_count=1),
    dict(key="fuel",     label="เกจน้ำมัน",                  media_type="photo", required=False, min_count=1),
    dict(key="damage",   label="รอย/ตำหนิที่พบ",              media_type="photo", required=False, min_count=1),
]
# ตอนคืน — เบากว่าตอนเบิก (คนกลับมาเหนื่อยแล้ว บังคับเยอะจะไม่ถ่าย)
RETURN_CHECKLIST = [
    dict(key="around",   label="รถรอบคัน (อย่างน้อย 1 มุม)", media_type="photo", required=True, min_count=1),
    dict(key="odometer", label="เลขไมล์ตอนคืน",              media_type="photo", required=True, min_count=1),
]

# คีย์ config ใน ChecklistConfig สำหรับ "เบิกผ่านเว็บ" (ไม่ผูกกับกลุ่ม LINE ห้องไหน)
WEB_CONFIG_KEY = "__web__"

# เกินกี่ชั่วโมงถือว่า "ค้างคืน / ควรตาม"
OVERDUE_HOURS = 12
