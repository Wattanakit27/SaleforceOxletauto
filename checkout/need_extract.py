# -*- coding: utf-8 -*-
"""อ่านบทสนทนาลูกค้า → สรุปเป็น "ความต้องการ" (`CustomerNeed`) ด้วย Gemini — ก.ย.69

*"เก็บทุกอย่างที่คิดว่าเป็นข้อมูล ทั้งลูกค้าหารถราคาเท่านี้ แท็กลูกค้าคนนี้เป็น lead
แล้วตามต่อว่าเป็น rj เพราะอะไร ถ้าเพราะราคาไม่ถึงก็เก็บไว้รอรถที่ราคาพอดีตามงบ"*

**ทำไมใช้ AI ไม่ใช่ regex** — ลูกค้าพิมพ์กันคนละแบบสุดๆ: "งบ 4 แสน" · "ไม่เกินสี่แสน" ·
"ผ่อนไหวเดือนละแปดพัน" · "เอาแบบ 3 แสนกว่าๆ" · "ยาริสปี19มีมั้ยครับ" · "อยากได้กระบะตอนเดียว"
เขียน regex ไล่จับ = ได้ไม่ถึงครึ่งแล้วต้องมานั่งปะทุกสัปดาห์ (บทเรียนจาก workflow เทิร์นรถ
ที่ต้องเขียน Scavenger/MANUAL_MAPPING มาปะกันไม่จบเพราะเทียบด้วยข้อความดิบ)

⚠️ **โมดูลนี้ไม่ส่งอะไรออกไปหาลูกค้าเด็ดขาด** — อ่านอย่างเดียว เขียนลงฐานข้อมูลเราเอง
⚠️ ไม่วิเคราะห์แชทพนักงาน (`is_employee`) — เปลืองเงินเปล่าและไม่ใช่ลูกค้า
"""
from __future__ import annotations

import hashlib
import json
import logging

import requests
from django.conf import settings
from django.utils import timezone

from .models import CustomerNeed, GroupChat, LineProfile

log = logging.getLogger(__name__)

_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# ใช้ flash: งานนี้เป็นการ "อ่านแล้วสรุป" ไม่ต้องใช้โมเดลใหญ่ และต้องรันกับลูกค้าหลายร้อยคน
_MODEL = "gemini-2.5-flash"
MAX_MSGS = 60          # เอาเท่าที่พอเห็นบริบท — ยาวกว่านี้เปลืองโดยไม่ได้ข้อมูลเพิ่ม

_SCHEMA = {
    "type": "object",
    "properties": {
        "has_need": {"type": "boolean"},
        "car_text": {"type": "string"},
        "car_model": {"type": "string"},
        "car_year_min": {"type": "integer"},
        "car_year_max": {"type": "integer"},
        "budget_max": {"type": "integer"},
        "budget_min": {"type": "integer"},
        "monthly_max": {"type": "integer"},
        "down_max": {"type": "integer"},
        "status": {"type": "string", "enum": ["new", "lead", "booked", "won", "rj"]},
        "reject_kind": {"type": "string",
                        "enum": ["", "price", "nocar", "credit", "lost", "silent", "other"]},
        "reject_note": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "evidence": {"type": "string"},
    },
    "required": ["has_need", "status", "confidence"],
}

_PROMPT = """คุณคือผู้ช่วยของเต็นท์รถมือสองในไทย อ่านบทสนทนาระหว่างลูกค้ากับแอดมินข้างล่าง
แล้วสรุปว่า "ลูกค้าคนนี้กำลังหารถอะไร งบเท่าไหร่"

กติกา:
- has_need = false ถ้าลูกค้าไม่ได้ถามหารถเลย (ทักมาเฉยๆ / ถามเรื่องอื่น / เป็นสแปม)
- car_model = ชื่อรุ่นสั้นๆ ที่ใช้เทียบกับสต็อกได้ เช่น "Yaris" "Fortuner" "D-Max"
  ไม่ต้องใส่ยี่ห้อถ้าไม่จำเป็น · ถ้าลูกค้าบอกแค่ประเภท ("กระบะ" "รถครอบครัว") ให้ใส่ตามนั้น
- car_text = คำที่ลูกค้าพิมพ์จริงเกี่ยวกับรถที่ต้องการ (ไม่ต้องเรียบเรียงใหม่)
- ตัวเลขทุกช่องเป็น "บาท" เป็นจำนวนเต็ม ไม่มีลูกน้ำ · ไม่รู้ให้ใส่ 0
  "4 แสน"/"สี่แสน" = 400000 · "ผ่อนเดือนละ 8 พัน" = monthly_max 8000
  · "ดาวน์ 5 หมื่น" = down_max 50000
- status: new = เพิ่งถาม ยังไม่คุยจบ · lead = คุยต่อเนื่อง มีนัด/ขอข้อมูลเพิ่ม
  · booked = จองแล้ว · won = ได้รถแล้วจากเรา · rj = ไม่ได้ไปต่อ
- reject_kind (ใส่เมื่อ status=rj เท่านั้น):
  price = ราคา/งบไม่ลงตัว · nocar = เราไม่มีรถรุ่นที่เขาต้องการ
  · credit = เครดิต/ไฟแนนซ์ไม่ผ่าน · lost = ไปซื้อที่อื่น/ได้รถแล้ว
  · silent = ติดต่อไม่ได้/เงียบไป · other = อื่นๆ
- evidence = ยกข้อความของลูกค้าที่ใช้สรุป มาไม่เกิน 2 ประโยค
- confidence = low ถ้าเดาเยอะ/ข้อมูลน้อย

ตอบเป็น JSON ตาม schema เท่านั้น

บทสนทนา:
"""


def _key() -> str:
    return (getattr(settings, "GEMINI_API_KEY", "") or "").strip()


def transcript(user_id: str, limit: int = MAX_MSGS) -> tuple[str, str]:
    """คืน (บทสนทนาเป็นข้อความ, ลายนิ้วมือ) — ลายนิ้วมือไว้เช็คว่ามีอะไรใหม่ตั้งแต่รอบก่อนไหม"""
    rows = list(GroupChat.objects
                .filter(sender_id=user_id)
                .exclude(chat_type=GroupChat.GROUP)
                .order_by("-sent_at", "-id")[:limit])
    rows.reverse()
    lines, ids = [], []
    for g in rows:
        who = "แอดมิน" if g.direction == GroupChat.OUT else "ลูกค้า"
        body = (g.text or "").strip() or ("[%s]" % (g.msg_type or "ไฟล์"))
        lines.append("%s: %s" % (who, body))
        ids.append(g.message_id)
    fp = hashlib.sha1("|".join(ids).encode("utf-8")).hexdigest()[:16]
    return "\n".join(lines), fp


def _ask(text: str) -> dict:
    key = _key()
    if not key:
        raise ValueError("ยังไม่ได้ตั้ง GEMINI_API_KEY")
    body = {
        "contents": [{"parts": [{"text": _PROMPT + text}]}],
        "generationConfig": {"responseMimeType": "application/json",
                             "responseSchema": _SCHEMA, "temperature": 0},
    }
    r = requests.post(_URL.format(model=_MODEL) + "?key=" + key, json=body, timeout=60)
    if r.status_code != 200:
        raise Exception("Gemini %s: %s" % (r.status_code, r.text[:200]))
    try:
        return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
    except (KeyError, IndexError, ValueError) as e:
        raise Exception("Gemini ตอบมาแบบอ่านไม่ได้: %s" % e)


def _num(v):
    """0/ว่าง = "ไม่รู้" → None (อย่าเก็บ 0 เป็นงบ ไม่งั้นตอนจับคู่จะกลายเป็น 'งบ 0 บาท')"""
    try:
        n = int(v or 0)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def analyze(profile: LineProfile, force: bool = False) -> CustomerNeed | None:
    """วิเคราะห์ลูกค้า 1 คน → สร้าง/อัปเดต `CustomerNeed` · คืน None ถ้าไม่มีความต้องการ

    **อัปเดตแถวเดิมถ้ายังคุยเรื่องเดิมอยู่** ไม่สร้างใหม่ทุกครั้งที่รัน — ไม่งั้นรันวันละครั้ง
    ก็ได้ความต้องการซ้ำวันละแถว จนหน้ารายการอ่านไม่ได้
    """
    if profile.is_employee:
        return None
    text, fp = transcript(profile.user_id)
    if not text.strip():
        return None

    # เคยวิเคราะห์บทสนทนาชุดนี้ไปแล้ว = ไม่มีอะไรใหม่ → ไม่ต้องจ่ายเงินซ้ำ
    latest = profile.needs.order_by("-updated_at").first()
    if latest and not force and (latest.note or "").endswith(fp):
        return latest

    d = _ask(text)
    if not d.get("has_need"):
        return None

    status = d.get("status") or CustomerNeed.NEW
    rk = (d.get("reject_kind") or "").strip()
    if status != CustomerNeed.RJ:
        rk = ""                                  # reject_kind มีความหมายเฉพาะตอน rj

    # แถวเดิมที่ยัง "มีชีวิต" = อัปเดตต่อ · ปิดไปแล้ว (rj/won) = เรื่องใหม่ ให้เปิดแถวใหม่
    row = profile.needs.exclude(status__in=[CustomerNeed.RJ, CustomerNeed.WON]) \
                       .order_by("-updated_at").first()
    if row is None:
        row = CustomerNeed(profile=profile, source=CustomerNeed.CHAT)

    row.car_text = (d.get("car_text") or "")[:300]
    row.car_model = (d.get("car_model") or "")[:80]
    row.car_year_min = _num(d.get("car_year_min"))
    row.car_year_max = _num(d.get("car_year_max"))
    row.budget_max = _num(d.get("budget_max"))
    row.budget_min = _num(d.get("budget_min"))
    row.monthly_max = _num(d.get("monthly_max"))
    row.down_max = _num(d.get("down_max"))
    row.status = status
    row.evidence = (d.get("evidence") or "")[:1000]
    row.confidence = (d.get("confidence") or "")[:8]
    if status == CustomerNeed.RJ:
        row.mark_reject(rk or CustomerNeed.RJ_OTHER, d.get("reject_note") or "")
    # ผนวกลายนิ้วมือท้าย note — รอบหน้าจะได้รู้ว่าบทสนทนาเปลี่ยนหรือยัง
    row.note = "วิเคราะห์อัตโนมัติ %s #%s" % (
        timezone.localtime().strftime("%d/%m/%y %H:%M"), fp)
    row.save()
    return row


def run(limit: int = 50, force: bool = False, days: int = 14) -> dict:
    """ไล่วิเคราะห์ลูกค้าที่คุยมาช่วงหลัง — คืนสรุปผล

    เรียงจาก **คนที่คุยล่าสุด** ก่อน: ลูกค้าที่เพิ่งทักคือคนที่ยังตามได้ทัน
    """
    since = timezone.now() - timezone.timedelta(days=days)
    qs = (LineProfile.objects
          .filter(is_employee=False, last_seen__gte=since)
          .order_by("-last_seen")[:limit])
    out = {"ดู": 0, "มีความต้องการ": 0, "ไม่มี": 0, "พลาด": 0, "รอรถ": 0, "errors": []}
    for p in qs:
        out["ดู"] += 1
        try:
            n = analyze(p, force=force)
        except Exception as e:                    # คนเดียวพังต้องไม่ล้มทั้งรอบ
            out["พลาด"] += 1
            out["errors"].append("%s: %s" % (p.show_name, e))
            log.warning("วิเคราะห์ความต้องการไม่สำเร็จ %s: %s", p.user_id, e)
            continue
        if n:
            out["มีความต้องการ"] += 1
            if n.waiting:
                out["รอรถ"] += 1
        else:
            out["ไม่มี"] += 1
    return out
