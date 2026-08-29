"""ส่งสรุป "เบิก/คืนรถ" เข้ากลุ่ม LINE (แบบ C — คนกดในเว็บ แต่หัวหน้ายังเห็นในกลุ่มเหมือนเดิม)

ทำไมต้องมี: จาก log จริง การอนุมัติเกิดในกลุ่ม LINE (หัวหน้าตอบสติกเกอร์/รับทราบ)
ถ้าย้ายไปเว็บล้วน หัวหน้าจะไม่เห็นความเคลื่อนไหว → ระบบจะถูกเมิน
ตั้งกลุ่มปลายทางที่ KVStore 'checkout_line_config' · ไม่ตั้ง = ไม่ส่ง (ระบบยังทำงานปกติ)
"""
from django.conf import settings


def _cfg():
    try:
        from dashboard.services import cache_store
        return (cache_store.get_kv("checkout_line_config") or {}).get("data") or {}
    except Exception:
        return {}


def is_configured() -> bool:
    return bool(_cfg().get("group_id") and getattr(settings, "LINE_CHANNEL_ACCESS_TOKEN", ""))


def _push(text: str) -> bool:
    cfg = _cfg()
    gid = (cfg.get("group_id") or "").strip()
    token = getattr(settings, "LINE_CHANNEL_ACCESS_TOKEN", "")
    if not (gid and token) or not cfg.get("enabled", True):
        return False
    try:
        from dashboard.services.line_notify import push_line_message
        code, _ = push_line_message(gid, [{"type": "text", "text": text}], token)
        return code == 200
    except Exception:
        return False


def notify_out(m, missing=None) -> bool:
    """สรุปตอนเบิก — รูปแบบใกล้เคียงที่คนพิมพ์กันอยู่ในกลุ่ม จะได้อ่านแล้วคุ้นทันที"""
    from . import constants as C
    plate = m.plate_text or (m.car.plate if m.car_id and m.car else "") or (m.car_id or "-")
    lines = [f"🚗 เบิกรถ {plate}"]
    if m.car_id and m.car and (m.car.brand or m.car.model):
        lines.append(f"   {m.car.brand} {m.car.model}".rstrip())
    lines.append(f"ผู้เบิก: {m.borrower_name or '-'}")
    job = C.PURPOSE_NAME.get(m.purpose_key, m.purpose or "-")
    lines.append(f"งาน: {job}" + (f" · {m.destination}" if m.destination else ""))
    if m.odo_out:
        lines.append(f"ไมล์ออก: {m.odo_out:,}")
    if m.fuel_requested:
        lines.append("⛽ ขอเบิกน้ำมันด้วย")
    n = m.photos.filter(phase="out").count()
    lines.append(f"รูป: {n} ไฟล์" + (" ✅ ครบ" if not missing else f" ⚠️ ขาด {', '.join(missing)}"))
    if m.note:
        lines.append(f"หมายเหตุ: {m.note}")
    return _push("\n".join(lines))


def notify_return(m) -> bool:
    from . import constants as C
    plate = m.plate_text or (m.car.plate if m.car_id and m.car else "") or (m.car_id or "-")
    lines = [f"✅ คืนรถ {plate}", f"ผู้คืน: {m.borrower_name or '-'}"]
    if m.checked_out_at and m.returned_at:
        mins = int((m.returned_at - m.checked_out_at).total_seconds() // 60)
        lines.append(f"ใช้เวลา: {mins // 60} ชม. {mins % 60} นาที" if mins >= 60 else f"ใช้เวลา: {mins} นาที")
    if m.odo_in:
        run = (m.odo_in - m.odo_out) if (m.odo_out and m.odo_in >= m.odo_out) else None
        lines.append(f"ไมล์คืน: {m.odo_in:,}" + (f" (วิ่ง {run:,} กม.)" if run else ""))
    if m.damage_reported:
        lines.append("⚠️ แจ้งความเสียหาย — ให้หัวหน้าตรวจ")
    if m.note:
        lines.append(f"หมายเหตุ: {m.note}")
    return _push("\n".join(lines))
