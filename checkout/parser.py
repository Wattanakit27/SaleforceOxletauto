"""อ่านข้อความในกลุ่ม LINE แล้วเดาว่าเป็นการ "เบิก/คืนรถ" ไหม — ใช้ในโหมดเฝ้าดู (ยังไม่ทำอะไร)

ที่มาของกติกา: วิเคราะห์ข้อความจริงในกลุ่ม 5 วัน (ส.ค.69)
  "เบิกรถไปตรวจขนส่งครับ" · "เบิก5655 ไปส่งลูกค้าที่แปลงยาว" · "นำรถไปตั้งศูนย์ครับ"
  "เอารถ 1477 กลับชลบุรีครับ" · "คืนรถครับ" · "คืน" · "ขอเบิกน้ำมันรถไปตรวจขนส่ง"
เป้าหมายเฟสนี้คือ "วัดความแม่น" ไม่ใช่ "ทำงานแทนคน" → เดาผิดได้ ไม่มีผลอะไร
"""
import re

from . import constants as C

# --- คำที่บอกว่า "รถออก" --- (เรียงจากเจาะจงไปกว้าง)
_OUT_WORDS = ["เบิกรถ", "ขอเบิกรถ", "เบิก", "นำรถไป", "เอารถไป", "เอารถ", "นำรถ", "พารถ"]
# --- คำที่บอกว่า "รถกลับ" ---
_IN_WORDS = ["คืนรถ", "คืน", "รถกลับแล้ว", "กลับถึงแล้ว", "เอารถกลับ"]
# --- น้ำมัน ---
_FUEL_WORDS = ["เบิกน้ำมัน", "ขอเบิกน้ำมัน", "เติมน้ำมัน", "น้ำมัน"]
# --- ยกเลิก ---
_CANCEL_WORDS = ["ยกเลิก", "เปลี่ยนเป็นคันนี้"]

# คำ -> ประเภทงาน (ตรงกับ constants.PURPOSES)
_PURPOSE_HINTS = [
    ("transport", ["ตรวจขนส่ง", "ขนส่ง", "ตรวจสภาพ"]),
    ("service",   ["ศูนย์", "ตั้งศูนย์", "ซ่อม", "อู่", "ฟิล์ม", "เบาะ", "ยาง", "จี้กระจก", "ถ่วงล้อ", "แอร์"]),
    ("customer",  ["ลูกค้า", "ส่งรถ", "ให้ดูรถ", "ดูรถ", "เทิร์น", "ส่งมอบ"]),
    ("finance",   ["ไฟแนนซ์", "เซ็นสัญญา", "เซ็น", "จัดไฟ"]),
    ("move",      ["กลับชลบุรี", "กลับสาขา", "ไปจอด", "จอดที่", "สาขา", "อ่อนนุช", "สลับป้าย"]),
    ("errand",    ["ซื้อของ", "ไปรษณีย์", "ไปรับ", "รับของ", "ส่งพี่", "ธนาคาร", "เอกสาร"]),
    # ⚠️ อย่าใส่คำสั้นอย่าง "รับ" — ไปโดน "ครับ" ที่ต่อท้ายเกือบทุกประโยค
]

_PLATE_RE = re.compile(r"(?<!\d)(\d{3,4})(?!\d)")      # เลขทะเบียน 3-4 ตัวที่คนพิมพ์ในกลุ่ม
_NOISE = re.compile(r"https?://\S+")


def parse(text: str) -> dict:
    """คืน {kind, plate, purpose, fuel, cancel, confidence, why}
    kind: 'out' (เบิก) | 'in' (คืน) | '' (ไม่เกี่ยว)
    confidence: 'high' = มั่นใจ · 'low' = เดา (ควรให้คนดู) · '' = ไม่เกี่ยว
    """
    raw = (text or "").strip()
    t = _NOISE.sub(" ", raw)          # ตัดลิงก์แผนที่ออกก่อน (เลขในลิงก์ทำให้จับทะเบียนผิด)
    res = {"kind": "", "plate": "", "purpose": "", "fuel": False,
           "cancel": False, "confidence": "", "why": ""}
    if not t:
        return res

    res["fuel"] = any(w in t for w in _FUEL_WORDS)
    res["cancel"] = any(w in t for w in _CANCEL_WORDS)

    # คืนก่อน — "คืนรถครับ" สั้นและชัด · ระวังคำว่า "คืน" ใน "ข้ามคืน"
    hit_in = next((w for w in _IN_WORDS if w in t), "")
    hit_out = next((w for w in _OUT_WORDS if w in t), "")
    if hit_in and not hit_out:
        res["kind"] = "in"
        res["confidence"] = "high" if hit_in in ("คืนรถ", "เอารถกลับ") else "low"
        res["why"] = f'เจอคำว่า "{hit_in}"'
    elif hit_out:
        res["kind"] = "out"
        res["confidence"] = "high" if hit_out in ("เบิกรถ", "ขอเบิกรถ", "นำรถไป", "เอารถไป") else "low"
        res["why"] = f'เจอคำว่า "{hit_out}"'
    else:
        return res

    m = _PLATE_RE.search(t)
    if m:
        res["plate"] = m.group(1)

    if res["kind"] == "out":       # ตอนคืนไม่ต้องเดางาน (ข้อความคืนสั้นมาก เดาไปก็มั่ว)
        for key, words in _PURPOSE_HINTS:
            if any(w in t for w in words):
                res["purpose"] = key
                break
    if res["kind"] == "out" and not res["purpose"]:
        res["confidence"] = "low"
        res["why"] += " · แต่เดาประเภทงานไม่ได้"
    return res


def purpose_name(key):
    return C.PURPOSE_NAME.get(key, "")
