"""Gemini OCR — อ่านเอกสาร → ดึงข้อมูลใส่ฟอร์ม (server-side เท่านั้น)

รองรับ 2 ฟอร์ม:
- finance : "เช็คเคสไฟแนนซ์ก่อนเซ็น" (ใบสรุปหลังอนุมัติ)
- loan    : "ข้อมูลผู้ยื่นขอสินเชื่อรถยนต์มือสอง" (ใบยื่นสินเชื่อ — ละเอียด)

ใช้ REST API ผ่าน requests (ไม่ลง SDK เพิ่ม → lambda เล็ก)
"""
import base64
import json

import requests
from django.conf import settings

_DEFAULT_MODEL = "gemini-2.5-pro"
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _str_schema(keys: list[str]) -> dict:
    return {"type": "object", "properties": {k: {"type": "string"} for k in keys}}


# ── ฟอร์ม "เช็คไฟแนนซ์ก่อนเซ็น" ──
_FINANCE_KEYS = [
    "customer", "leadCode", "branch", "car", "plate", "price",
    "finco", "status", "approved", "down", "monthly", "terms", "cond",
    "signDate", "signTime", "extra",
]
_FINANCE_SCHEMA = _str_schema(_FINANCE_KEYS)
_FINANCE_PROMPT = """คุณคือผู้ช่วยกรอกฟอร์ม "เช็คเคสไฟแนนซ์ก่อนเซ็น" ของเต็นท์รถมือสอง
อ่านข้อมูลจากรูปเอกสาร (อาจปริ้นหรือเขียนมือ) แล้วดึงข้อมูลใส่แต่ละ field ตาม schema

กติกาสำคัญ:
- ถ้าไม่พบข้อมูลของ field ไหน ใส่ค่าว่าง "" ห้ามเดา
- ตัวเลขเงิน (price, approved, down, monthly) ใส่เฉพาะตัวเลขและ comma เช่น "550,000" ไม่ต้องมี "บาท"
- terms = จำนวนงวด ใส่เฉพาะตัวเลข เช่น "72"
- signDate แปลงเป็น YYYY-MM-DD
- finco = ชื่อบริษัทไฟแนนซ์, status = สถานะอนุมัติ
- รักษาข้อความภาษาไทยตามเอกสารเดิม"""


# ── ฟอร์ม "ยื่นสินเชื่อ" (ตามใบกระดาษ) ──
_LOAN_KEYS = [
    # ผู้เช่าซื้อ (ลูกค้า)
    "customer", "age", "phone", "province", "sex", "residence", "rent", "liveYears", "marital", "children",
    # อาชีพ & รายได้
    "occupation", "incomeSource", "company", "companyAbout", "companyLoc",
    "position", "workYears", "salary", "ot", "avgIncome",
    "bizName", "bizType", "bizLoc", "bizYears", "socialSecurity", "socialAmount", "otherJob",
    # ประวัติผ่อน / เครดิต
    "loanHistoryType", "credit", "payBank", "payInstallment", "payDuration",
    "payStatus", "payClosed", "blacklist", "tracking", "creditRequests",
    # การเลือกไฟแนนซ์
    "carModel", "finance", "reason", "note",
    # ผู้ค้ำ / ผู้กู้ร่วม
    "gCustomer", "gRelation", "gAge", "gPhone", "gProvince", "gOccupation", "gAvgIncome",
    # ลงชื่อ
    "referrer", "referrerPhone", "sales", "date",
]
_LOAN_SCHEMA = _str_schema(_LOAN_KEYS)
_LOAN_PROMPT = """คุณคือผู้ช่วยกรอกฟอร์ม "ข้อมูลผู้ยื่นขอสินเชื่อรถยนต์มือสอง" ของเต็นท์รถมือสอง
อ่านข้อมูลจากรูปเอกสาร (ส่วนใหญ่เขียนด้วยมือ มี checkbox/วงกลม) แล้วดึงข้อมูลใส่แต่ละ field ตาม schema

โครงสร้างเอกสารมี 2 ฝั่ง: ซ้าย = ผู้เช่าซื้อ (ลูกค้า), ขวา = ผู้ค้ำ/ผู้กู้ร่วม
- field ที่ขึ้นต้นด้วย g... = ของผู้ค้ำ (ฝั่งขวา) ถ้าฝั่งขวาว่างให้ใส่ ""

กติกาสำคัญ:
- ถ้าไม่พบข้อมูลของ field ไหน ใส่ค่าว่าง "" ห้ามเดา ห้ามมั่ว
- ตัวเลขเงิน (rent, salary, ot, avgIncome, socialAmount, payInstallment) ใส่เฉพาะตัวเลขและ comma
- ช่องที่เป็นตัวเลือก (มี checkbox/วงกลม) ให้ดูว่าติ๊กอันไหน แล้วใส่ข้อความของตัวเลือกนั้น:
  - sex: "ชาย" หรือ "หญิง"
  - residence: "บ้านตัวเอง"/"บ้านเช่า"/"ห้องเช่า"/"บ้านพักสวัสดิการ"
  - marital: "โสด"/"สมรส"/"จดทะเบียน"/"ไม่จดทะเบียน"
  - occupation: "พนักงานบริษัท"/"เจ้าของกิจการ"/"ค้าขาย"/"เกษตรกร"/"รับเหมา"/"อื่นๆ"
  - incomeSource: "เงินเข้าบัญชีอัตโนมัติ"/"รับเงินสด"/"นายจ้างโอนเข้าบัญชี"
  - loanHistoryType: "บ้าน"/"รถยนต์"/"รถมอเตอร์ไซค์"
  - credit: "บัตรเครดิต"/"ไม่มีประวัติ"/"อื่นๆ"
  - payStatus: "ผ่อนดีผ่อนตรง"/"เคยล่าช้าไม่เกิน 30 วัน"/"ล่าช้าเกิน 30 วัน"
  - socialSecurity: "มี"/"ไม่มี"
- finance = ไฟแนนซ์ที่เลือกจัด (เช่น TTB, AY, KK), reason = เหตุผลที่เลือกไฟแนนซ์นั้น
- date แปลงเป็น YYYY-MM-DD ถ้าทำได้
- รักษาข้อความภาษาไทยตามเอกสารเดิม"""


def _call_gemini(image_bytes: bytes, mime_type: str, schema: dict, prompt: str) -> dict:
    key = (getattr(settings, "GEMINI_API_KEY", "") or "").strip()
    if not key:
        raise ValueError("ยังไม่ได้ตั้ง GEMINI_API_KEY ใน .env")

    b64 = base64.b64encode(image_bytes).decode("ascii")
    body = {
        "contents": [{"parts": [
            {"text": prompt},
            {"inline_data": {"mime_type": mime_type, "data": b64}},
        ]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": schema,
            "temperature": 0,
        },
    }
    model = (getattr(settings, "GEMINI_MODEL", "") or _DEFAULT_MODEL).strip()
    url = _GEMINI_URL.format(model=model) + f"?key={key}"
    r = requests.post(url, json=body, timeout=60)
    if r.status_code != 200:
        raise Exception(f"Gemini API {r.status_code}: {r.text[:300]}")

    data = r.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise Exception("Gemini ไม่คืนข้อมูล (อาจถูก safety block หรือรูปอ่านไม่ออก)")

    try:
        fields = json.loads(text)
    except json.JSONDecodeError:
        raise Exception("Gemini คืนรูปแบบไม่ถูกต้อง")

    return {k: (str(v).strip() if v is not None else "") for k, v in fields.items()}


def extract_finance_fields(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    return _call_gemini(image_bytes, mime_type, _FINANCE_SCHEMA, _FINANCE_PROMPT)


def extract_loan_fields(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    return _call_gemini(image_bytes, mime_type, _LOAN_SCHEMA, _LOAN_PROMPT)
