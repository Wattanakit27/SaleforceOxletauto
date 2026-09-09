"""อ่านข้อความในกลุ่ม LINE แล้วเดาว่าเป็นการ "เบิก/คืนรถ" ไหม — ใช้ในโหมดเฝ้าดู (ยังไม่ทำอะไร)

ที่มาของกติกา: วิเคราะห์ข้อความจริงในกลุ่ม
  รอบแรก (ส.ค.69) 5 วัน · รอบสอง (ก.ย.69) 10 วัน 403 ข้อความ — ดู
  [checkout/samples/group_log_sep69.txt](samples/group_log_sep69.txt)
  ป้อนซ้ำได้ด้วย `manage.py seed_group_log --dry-run` (พิมพ์รายงานความแม่นออกมาเลย)
เป้าหมายเฟสนี้คือ "วัดความแม่น" ไม่ใช่ "ทำงานแทนคน" → เดาผิดได้ ไม่มีผลอะไร

★ ก.ย.69 — บทเรียนจาก log จริง 10 วัน (แก้แล้วในไฟล์นี้):
  1. "ขอเบิกน้ำมัน..." ไม่ใช่ "เบิกรถ" — เดิมคำว่า "เบิก" ทำให้ 12 ข้อความกลายเป็นรถออกนอกลาน
     (คนขอเบิกน้ำมันตอนรถอยู่ในลานก็มี เช่น "เบิกน้ำมันเติมขยับรถครับ") → แยกเป็น kind="fuel"
  2. "หลังเติมครับ" = รูปหลังเติมน้ำมัน เป็นหลักฐานคนละใบกับการเบิก → kind="fuel_done"
  3. คนพิมพ์ย่อมาก "เอา 3414 กลับชลบุรี" / "นำ3413กลับชลบุรี" — ไม่มีคำว่า "รถ" เลย
  4. พิมพ์ผิดเป็นเรื่องปกติ ("คีน3414" = คืน)
"""
import re

from . import constants as C

# ป้ายชื่อของแต่ละชนิด (หน้า observe ใช้ตัวนี้ — อย่า hardcode ซ้ำที่อื่น)
KIND_LABEL = {"out": "เบิก", "in": "คืน", "fuel": "ขอน้ำมัน", "fuel_done": "เติมแล้ว",
              "plate_only": "อ้างถึงรถ"}

# --- คำที่บอกว่า "รถออก" --- (เรียงจากเจาะจงไปกว้าง)
_OUT_WORDS = ["ขอเบิกรถ", "เบิกรถ", "ยืมรถ", "นำรถไป", "เอารถไป", "รับรถ",
              "เบิก", "เอารถ", "นำรถ", "พารถ", "ขับรถ"]
# คำที่ "มั่นใจว่ารถออกจริง" (ไม่ใช่แค่เดาจากคำกว้างๆ)
_OUT_STRONG = {"ขอเบิกรถ", "เบิกรถ", "ยืมรถ", "นำรถไป", "เอารถไป"}
# --- คำที่บอกว่า "รถกลับ" --- ("คีน" = พิมพ์ผิดของ "คืน" เจอในกลุ่มจริง)
_IN_WORDS = ["คืนรถ", "คีนรถ", "คืน", "คีน", "รถกลับแล้ว", "กลับถึงแล้ว", "เอารถกลับ"]
# --- น้ำมัน ---
_FUEL_WORDS = ["เบิกน้ำมัน", "ขอเบิกน้ำมัน", "เติมน้ำมัน", "น้ำมัน"]
_FUEL_DONE_WORDS = ["หลังเติม", "เติมเสร็จ"]
# --- ยกเลิก / เปลี่ยนคัน ---
_CANCEL_WORDS = ["ยกเลิก", "เปลี่ยนเป็นคันนี้", "เปลี่ยนคัน"]

# คำ -> ประเภทงาน (ตรงกับ constants.PURPOSES)
_PURPOSE_HINTS = [
    ("transport", ["ตรวจขนส่ง", "ขนส่ง", "ตรวจสภาพ", "ตรอ"]),
    ("service",   ["ศูนย์", "ตั้งศูนย์", "ซ่อม", "อู่", "ฟิล์ม", "เบาะ", "ยาง", "ล้อแม็ก",
                   "จี้กระจก", "ถ่วงล้อ", "แอร์"]),
    # ⚠️ "จัดซื้อ" ต้องมาก่อน "customer" — ไม่งั้น "ไปดูรถ" โดนคำว่า "ดูรถ" ของ customer กินไปก่อน
    ("buying",    ["ไปดูรถ", "ดูรถที่", "เข้าใหม่", "รับรถเข้า", "ประเมินรถ", "ตีราคา"]),
    ("customer",  ["ลูกค้า", "ส่งรถ", "ให้ดูรถ", "ดูรถ", "เทิร์น", "ส่งมอบ",
                   "ทดลองขับ", "เทสไดรฟ์", "ลค"]),
    ("finance",   ["ไฟแนนซ์", "เซ็นสัญญา", "เซ็น", "จัดไฟ"]),
    ("move",      ["กลับชลบุรี", "กลับสาขา", "ไปจอด", "จอดที่", "ฝากจอด", "สาขา",
                   "อ่อนนุช", "สลับป้าย"]),
    ("errand",    ["ซื้อของ", "ไปรษณีย์", "ไปรับ", "รับของ", "ส่งพี่", "ธนาคาร",
                   "เอกสาร", "ป้ายทะเบียน", "คุมประพฤติ"]),
    # ⚠️ อย่าใส่คำสั้นอย่าง "รับ" — ไปโดน "ครับ" ที่ต่อท้ายเกือบทุกประโยค
]

_PLATE_RE = re.compile(r"(?<!\d)(\d{3,4})(?!\d)")      # เลขทะเบียน 3-4 ตัวที่คนพิมพ์ในกลุ่ม
_NOISE = re.compile(r"https?://\S+")
# "เบิก1314" · "เอา 3414 กลับชลบุรี" · "นำ3413กลับชลบุรี" — ย่อจนไม่มีคำว่า "รถ"
_SHORT_TAKE_RE = re.compile(r"^\s*(?:ขอ)?(เบิก|นำ|เอา|พา)\s*\d{3,4}")
# "พาคุณปุ้ยไปเซ็นไฟแนนซ์" · "พาพี่มิวไปเอารถ"
_TAKE_SOMEONE_RE = re.compile(r"พา.{0,20}ไป")
# ประโยคคำถาม/สั่งงานล่วงหน้า — ไม่ใช่การเบิกที่เกิดขึ้นตอนนี้
_QUESTION = ["ไหม", "มั้ย", "หรอ", "หรือ", "ใคร", "?", "รบกวน"]
_FUTURE = ["พรุ่งนี้", "มะรืน", "สัปดาห์หน้า", "เดี๋ยว"]
# ★ ก.ย.69 — ข้อความย่อสุดๆ ที่ "สื่อความจากรูปที่ส่งคู่กัน" (จาก log จริง)
#   "ขนส่งค่ะ" · "ไปขนส่ง" · "กลับชลบุรี" · "ไปรับพี่โอ๊ดครับ" — ไม่มีคำว่าเบิก/รถ เลย
#   เดาให้เป็น "เบิก" แต่ตั้ง confidence=low เสมอ ให้คนตรวจในโหมดเฝ้าดู
_MENTION = re.compile(r"@\S+")
_POLITE = re.compile(r"(?:ค่ะ|คะ|ครับ|คับ|จ้า|จ้ะ|นะ|น่ะ|ๆ|\s)+$")
_SHORT_TASK = ["ขนส่ง", "ตั้งศูนย์", "ตรอ", "กลับชลบุรี", "กลับสาขา", "ไปรับ", "ไปส่ง", "ขึ้นโชว์"]
_SHORT_TASK_MAX = 24        # ยาวกว่านี้ = มีเนื้อความอื่นปน อย่าเดา
# ขอให้คนอื่นทำ ≠ ตัวเองเบิก ("ไปส่งหน่อยครับ") — ใช้เฉพาะทางเดาย่อ ไม่ใช้กับประโยคเต็ม
_REQUEST = ["หน่อย", "รบกวน", "ฝากด้วย"]
# พิมพ์แต่เลขทะเบียนเปล่าๆ ("1061" · "595" · "HRV6149") — รู้ว่าคันไหน แต่ไม่รู้ว่าเบิกหรือคืน
_PLATE_ONLY_RE = re.compile(r"^[A-Za-z฀-๿]{0,8}\s*\d{3,4}$")


def _clean(text):
    return _NOISE.sub(" ", (text or "").strip())


def _has_any(t, words):
    return next((w for w in words if w in t), "")


def parse(text: str) -> dict:
    """คืน {kind, plate, purpose, fuel, cancel, confidence, why}
    kind: 'out' (เบิกรถออก) | 'in' (คืนรถ) | 'fuel' (ขอเบิกน้ำมัน — รถไม่จำเป็นต้องออก)
          | 'fuel_done' (ส่งรูปหลังเติม) | 'plate_only' (พิมพ์แต่เลขทะเบียน — รู้ว่าคันไหน
            แต่ไม่รู้ว่าเบิกหรือคืน) | '' (ไม่เกี่ยว)
    confidence: 'high' = มั่นใจ · 'low' = เดา (ควรให้คนดู) · '' = ไม่เกี่ยว
    """
    t = _clean(text)
    res = {"kind": "", "plate": "", "purpose": "", "fuel": False,
           "cancel": False, "confidence": "", "why": ""}
    if not t:
        return res

    res["fuel"] = bool(_has_any(t, _FUEL_WORDS))
    res["cancel"] = bool(_has_any(t, _CANCEL_WORDS))
    ask = any(w in t for w in _QUESTION)
    later = any(w in t for w in _FUTURE)

    hit_in = _has_any(t, _IN_WORDS)
    hit_out = _has_any(t, _OUT_WORDS)
    short_take = bool(_SHORT_TAKE_RE.search(t))
    take_someone = bool(_TAKE_SOMEONE_RE.search(t))

    # 1) รูปหลังเติมน้ำมัน — หลักฐานคนละใบ ไม่ใช่การเบิก
    if _has_any(t, _FUEL_DONE_WORDS):
        res["kind"] = "fuel_done"
        res["confidence"] = "high"
        res["why"] = 'ส่งรูป "หลังเติม"'
        m = _PLATE_RE.search(t)
        if m:
            res["plate"] = m.group(1)
        return res

    # 2) คืนรถ — ข้อความสั้นและชัด (เช็คก่อน "เบิก" เพราะ "คืนรถ" ไม่มีคำเบิกปน)
    if hit_in and not (hit_out or short_take):
        res["kind"] = "in"
        # "คืน" / "คืนครับ" / "คืนรถ" สั้นๆ = ชัดเจนพอ ไม่ต้องให้คนมานั่งตรวจ
        res["confidence"] = "high" if (hit_in in ("คืนรถ", "คีนรถ", "เอารถกลับ")
                                       or len(t) <= 16) else "low"
        res["why"] = 'เจอคำว่า "%s"' % hit_in
    # 3) ขอเบิกน้ำมัน (ไม่มีคำว่าเอารถออก) — แยกจากการเบิกรถเด็ดขาด
    elif res["fuel"] and not (hit_out in _OUT_STRONG or short_take):
        res["kind"] = "fuel"
        res["confidence"] = "high" if "เบิกน้ำมัน" in t else "low"
        res["why"] = "ขอเบิกน้ำมัน (ไม่ได้บอกว่าเอารถออก)"
    # 4) เบิกรถออก
    elif hit_out or short_take or (take_someone and not ask):
        if later or ask:                     # สั่งงานพรุ่งนี้ / ถามคำถาม = ยังไม่ใช่การเบิกตอนนี้
            return res
        res["kind"] = "out"
        res["confidence"] = "high" if hit_out in _OUT_STRONG else "low"
        res["why"] = ('เจอคำว่า "%s"' % hit_out) if hit_out else "เขียนย่อ (คำเบิก + เลขทะเบียน)"
    else:
        # --- ทางเดาสุดท้าย: ข้อความย่อที่สื่อความจากรูปที่ส่งคู่กัน ---
        core = _POLITE.sub("", _MENTION.sub(" ", t).strip()).strip()
        if _PLATE_ONLY_RE.match(core):
            res["kind"] = "plate_only"
            res["confidence"] = "low"
            res["why"] = "พิมพ์แต่เลขทะเบียน — ต้องดูรูป/ข้อความก่อนหน้าว่าเบิกหรือคืน"
            mm = _PLATE_RE.search(core)
            if mm:
                res["plate"] = mm.group(1)
            return res
        task = _has_any(core, _SHORT_TASK) if len(core) <= _SHORT_TASK_MAX else ""
        if not task or ask or later or any(w in t for w in _REQUEST):
            return res
        res["kind"] = "out"
        res["confidence"] = "low"
        res["why"] = 'เขียนย่อ บอกแต่ปลายทาง/งาน ("%s")' % task

    m = _PLATE_RE.search(t)
    if m:
        res["plate"] = m.group(1)

    if res["kind"] == "out":       # ตอนคืนไม่ต้องเดางาน (ข้อความคืนสั้นมาก เดาไปก็มั่ว)
        for key, words in _PURPOSE_HINTS:
            if any(w in t for w in words):
                res["purpose"] = key
                break
        if not res["purpose"]:
            res["confidence"] = "low"
            res["why"] += " · แต่เดาประเภทงานไม่ได้"
    return res


def purpose_name(key):
    return C.PURPOSE_NAME.get(key, "")


def kind_name(key):
    return KIND_LABEL.get(key, "")
