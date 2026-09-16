# -*- coding: utf-8 -*-
"""จดล็อกเหตุการณ์ลงตาราง `dash_event_log` — ★ 16 ก.ย.69 (เจ้าของสั่ง)

*"ล็อกอะไรต่างๆ ก็ควรเก็บไว้ในนี้นะ"* — เดิมร่องรอยการทำงานอยู่ใน `dash_kv`
แบบเก็บ **ค่าล่าสุดค่าเดียว** (ทับทุกครั้ง) และ **ขาส่งออก LINE ไม่มีล็อกเลย**
→ ย้อนดูไม่ได้ว่า "เมื่อวานส่งออกจริงไหม ล้มตั้งแต่เมื่อไหร่"

**กฎเหล็ก: ล็อกต้องไม่ทำให้งานหลักพัง** — ทุกอย่างที่นี่ห่อ try/except
เขียนไม่ได้ (ยังไม่ migrate / DB ล่ม) = ข้ามเงียบ ไม่โยน exception กลับไปให้ผู้เรียก
"""

# จดเฉพาะเหตุการณ์ที่ "ต้องตรวจย้อนหลังได้" ไม่ใช่ทุกอย่างที่เกิดขึ้น
SEND = "line_send"      # ส่งออก LINE (รายงาน/การ์ด/ตามด่วน/สรุปเบิก-คืน)
WEBHOOK = "webhook"     # ขาเข้าที่ผิดปกติ (ไม่มี event / ลายเซ็นไม่ผ่าน)
CRON = "cron"           # งานอัตโนมัติที่ล้ม หรือที่ส่งของออกไปจริง
SHEETS = "sheets"       # อ่านชีตพลาด / ตกไปใช้ทางสำรอง

_TRIM_KEY = "eventlog_trim_last"


def log(kind, name="", target="", ok=True, ms=0, **detail):
    """จด 1 เหตุการณ์ — คืน `True` ถ้าเขียนติด (ผู้เรียกไม่ต้องเช็คก็ได้)"""
    try:
        from dashboard.models import EventLog
        EventLog.objects.create(
            kind=(kind or "")[:24], name=str(name or "")[:120],
            target=str(target or "")[:64], ok=bool(ok), ms=int(ms or 0),
            detail={k: v for k, v in detail.items() if v is not None})
        return True
    except Exception:
        return False


def trim(days=None) -> int:
    """ลบล็อกที่เก่ากว่ากำหนด — คืนจำนวนแถวที่ลบ

    ล็อกที่ไม่มีวันหมดอายุ = ตารางโตไม่หยุด แล้ววันหนึ่งจะไปกินดิสก์เซิร์ฟเวอร์
    (เคยโดนมาแล้วกับรูปรายงาน 1.3 GB ที่ไม่มีใครกวาด)
    """
    try:
        from datetime import timedelta
        from django.utils import timezone
        from dashboard.models import EventLog
        cut = timezone.now() - timedelta(days=int(days or EventLog.KEEP_DAYS))
        n, _ = EventLog.objects.filter(at__lt=cut).delete()
        return n
    except Exception:
        return 0


def trim_daily() -> int:
    """เรียกถี่แค่ไหนก็ได้ — ลบจริงวันละครั้ง (ใช้ KV กันรันซ้ำ เหมือน `_cleanup_chat`)"""
    try:
        from django.utils import timezone
        from . import cache_store
        today = timezone.localdate().isoformat()
        last = (cache_store.get_kv(_TRIM_KEY) or {}).get("data") or {}
        if last.get("day") == today:
            return 0
        n = trim()
        cache_store.set_kv(_TRIM_KEY, {"day": today, "deleted": n})
        return n
    except Exception:
        return 0
