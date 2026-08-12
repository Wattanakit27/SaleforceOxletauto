"""แปลหมายเหตุข้ามภาษาอัตโนมัติ (พม่า/เขมร → ไทย) ด้วย Gemini — best-effort (ส.ค.69)

คนงานพิมพ์หมายเหตุภาษาตัวเองตอนเปลี่ยนสเตป → หลังบันทึกเสร็จระบบแปลใน thread เบื้องหลัง
แล้วเติม "(แปล: ...)" ต่อท้ายเฉพาะบรรทัดที่เป็นภาษาพม่า/เขมร (บรรทัดไทย/เช็คลิสต์ไม่แตะ)
→ ทุกคนเห็นคำแปลไทยใน timeline โดยคนพิมพ์ไม่ต้องทำอะไรเพิ่ม

ใช้ GEMINI_API_KEY เดิมของโปรเจกต์ (ตัวเดียวกับ insights/OCR) · โมเดล GEMINI_INSIGHTS_MODEL (flash — ถูก)
ไม่ตั้งคีย์/Gemini ล่ม/แปลไม่ได้ = เงียบ ข้อความเดิมอยู่ครบ ไม่กระทบการเปลี่ยนสเตป
"""
import re
import threading

import requests
from django.conf import settings

# อักษรพม่า (รวมบล็อกส่วนขยาย) + เขมร — เจอในบรรทัดไหน = บรรทัดนั้นต้องแปล
_FOREIGN = re.compile(r"[က-႟ꩠ-ꩿꧠ-꧿ក-៿]")


def needs_translation(line: str) -> bool:
    return bool(_FOREIGN.search(line)) and "(แปล:" not in line


def _gemini_translate(text: str) -> str:
    """แปลเป็นไทยผ่าน Gemini REST — คืน '' ถ้าแปลไม่ได้ (คีย์ไม่มี/HTTP พัง/รูปแบบตอบเพี้ยน)"""
    key = (getattr(settings, "GEMINI_API_KEY", "") or "").strip()
    if not key:
        return ""
    model = getattr(settings, "GEMINI_INSIGHTS_MODEL", "") or "gemini-2.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    body = {
        "contents": [{"parts": [{"text":
            "แปลข้อความนี้เป็นภาษาไทยแบบสั้นตรงตัว (บริบท: หมายเหตุงานซ่อม/เตรียมรถมือสองในเต็นท์รถ) "
            "ตอบเฉพาะคำแปลอย่างเดียว ห้ามอธิบายเพิ่ม:\n" + text}]}],
        "generationConfig": {"temperature": 0},
    }
    try:
        r = requests.post(url, json=body, timeout=30)
        if r.status_code != 200:
            return ""
        out = (r.json()["candidates"][0]["content"]["parts"][0]["text"] or "").strip()
        return out.splitlines()[0].strip() if out else ""
    except Exception:
        return ""


def translate_note_text(note: str, translate=None) -> str:
    """เติม '(แปล: ...)' ใต้บรรทัดที่เป็นพม่า/เขมร — คืน '' ถ้าไม่มีอะไรต้องแปล/แปลไม่สำเร็จ
    translate = ฟังก์ชันแปล (default Gemini · ส่งตัวอื่นได้ตอนเทสต์)"""
    translate = translate or _gemini_translate
    lines = (note or "").split("\n")
    out, changed = [], False
    for i, line in enumerate(lines):
        out.append(line)
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        # ข้ามถ้าบรรทัดถัดไปเป็นคำแปลอยู่แล้ว (กันแปลซ้ำตอน save ซ้ำ/เรียกซ้ำ)
        if line.strip() and needs_translation(line) and not nxt.startswith("(แปล:"):
            th = translate(line.strip())
            if th:
                out.append(f"(แปล: {th})")
                changed = True
    return "\n".join(out) if changed else ""


def translate_log_async(log_pk):
    """เรียกหลังสร้าง ScanLog — แปลใน daemon thread (ไม่บล็อกการเปลี่ยนสเตป · พังเงียบ)"""
    def _work():
        try:
            from .models import ScanLog
            log = ScanLog.objects.get(pk=log_pk)
            new = translate_note_text(log.note)
            if new:
                log.note = new
                log.save(update_fields=["note"])
        except Exception:
            pass
    threading.Thread(target=_work, daemon=True).start()
