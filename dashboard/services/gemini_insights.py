"""AI insights ด้วย Gemini — วิเคราะห์เซลล์ (โค้ช) + อธิบายแนวโน้มยอดขาย

ใช้ Gemini text generation (server-side, ใช้ key + model จาก settings)
cache ผล 30 นาที (Gemini ช้า + มีค่าใช้จ่าย — ไม่ต้องเรียกซ้ำทุกครั้ง)
"""
import hashlib
import time

import requests
from django.conf import settings

_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

_cache: dict = {}      # key → (ts, text)
_TTL = 1800            # 30 นาที


def _hk(s: str) -> str:
    """cache key ที่ stable ข้าม process — hash() builtin สุ่มตาม PYTHONHASHSEED ทุก process
    → บน serverless (process ใหม่ทุก request) cache แทบไม่ hit. ใช้ sha1 แทน."""
    return hashlib.sha1((s or "").encode("utf-8")).hexdigest()[:16]


def _gemini_text(prompt: str, max_tokens: int = 2048) -> str:
    key = (getattr(settings, "GEMINI_API_KEY", "") or "").strip()
    if not key:
        raise ValueError("ยังไม่ได้ตั้ง GEMINI_API_KEY ใน .env")
    # ใช้ flash + ปิด thinking สำหรับงาน narrative — เร็ว + ไม่กิน token ไปกับ thinking
    # (pro model จะใช้ thinking จน token หมดก่อนตอบ ทำให้คำตอบสั้น/ขาด)
    model = (getattr(settings, "GEMINI_INSIGHTS_MODEL", "") or "gemini-2.5-flash").strip()
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": max_tokens,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    url = _GEMINI_URL.format(model=model) + f"?key={key}"
    r = requests.post(url, json=body, timeout=60)
    if r.status_code != 200:
        raise Exception(f"Gemini {r.status_code}: {r.text[:200]}")
    data = r.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError):
        raise Exception("Gemini ไม่คืนข้อความ (อาจถูก safety block)")


def _cached(key: str, build_prompt, max_tokens: int = 900) -> str:
    e = _cache.get(key)
    if e and (time.time() - e[0]) < _TTL:
        return e[1]
    text = _gemini_text(build_prompt(), max_tokens)
    _cache[key] = (time.time(), text)
    return text


def analyze_seller(name: str, stats_text: str) -> str:
    """โค้ชวิเคราะห์ผลงานเซลล์ 1 คน จากสรุปตัวเลข."""
    def _p():
        return f"""คุณคือหัวหน้าทีมขายรถมือสองที่เป็นโค้ชเก่ง วิเคราะห์ผลงานเซลล์ชื่อ "{name}" จากตัวเลข:

{stats_text}

เขียนวิเคราะห์ภาษาไทย กันเอง ให้กำลังใจแต่ตรงไปตรงมา อิงตัวเลขจริง:
**💪 จุดแข็ง** — 1-2 ข้อ
**⚠️ ต้องพัฒนา** — 1-2 ข้อ (ชี้ตัวเลขที่อ่อน)
**🎯 ทำสัปดาห์นี้** — 2-3 ข้อ รูปธรรม ทำได้จริง
สั้น กระชับ ไม่เกิน 12 บรรทัด ใช้ bullet"""
    return _cached(f"seller:{name}:{_hk(stats_text)}", _p, 2048)


def forecast_narrative(summary_text: str) -> str:
    """วิเคราะห์ยอดขาย + แนวโน้มตลาดเชิงลึก (รวมปัจจัยภายนอก) สำหรับเต็นท์รถมือสองน้ำมัน."""
    def _p():
        return f"""คุณคือนักวิเคราะห์ตลาดรถยนต์มือสองในไทยที่เก่งมาก ลูกค้าคือ **เจ้าของเต็นท์รถมือสองที่ขายรถใช้น้ำมันเป็นหลัก**

ข้อมูลยอดขายรายเดือนของเต็นท์:
{summary_text}

วิเคราะห์เชิงลึกเป็นภาษาไทย ตรงประเด็น อิงข้อมูลจริง + ความรู้ตลาดที่คุณมี:

**📈 แนวโน้มจากตัวเลข** — ขึ้น/ทรง/ลง, จังหวะ/ฤดูกาล, สัญญาณที่เห็น

**🌍 ปัจจัยตลาดที่ต้องจับตา** (เลือกเฉพาะที่เกี่ยวกับรถมือสองน้ำมันในไทยช่วงนี้):
- ราคาน้ำมัน → กระทบความต้องการรถน้ำมัน
- กระแส **รถ EV** ที่เข้ามาแทนรถน้ำมัน → ความเสี่ยงระยะยาวต่อเต็นท์
- เศรษฐกิจ / กำลังซื้อ / ดอกเบี้ย / ความเข้มงวดการปล่อยสินเชื่อ
- ปัจจัยโลก (สงคราม/ราคาพลังงาน) ถ้าเกี่ยวข้อง

**🔮 มุมมองข้างหน้า** — ทิศทางเดือน-ไตรมาสหน้า (เชิงทิศทาง ไม่ต้องฟันธงเป็นตัวเลขเป๊ะ)

**🎯 กลยุทธ์สำหรับเต็นท์** — 2-3 ข้อรูปธรรม (เช่น ควรสต๊อกรถประเภท/รุ่นไหน, รับมือกระแส EV, จังหวะรับซื้อ/ปล่อย)

กระชับ ใช้ bullet ภายใต้แต่ละหัวข้อ — เป็นที่ปรึกษาที่ตรงไปตรงมา ไม่เยิ่นเย้อ
หมายเหตุ: คุณไม่มีข้อมูล real-time ราคาน้ำมัน/สงครามล่าสุด ให้วิเคราะห์เชิงกลยุทธ์/ทิศทางจากความรู้ตลาดที่มี"""
    return _cached(f"forecast:{_hk(summary_text)}", _p, 2048)
