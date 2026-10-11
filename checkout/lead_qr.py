# -*- coding: utf-8 -*-
"""ลูกค้าให้ LINE เป็น "QR / ลิงก์เพิ่มเพื่อน" แทนการพิมพ์ ID → นับเป็นช่องทางติดต่อ (เข้าห้องพัก Lead) · 11 ต.ค.69

ที่มา (ถามจากหน้าจอจริง): *"ถ้าลูกค้าส่งรูปมา … เราไม่มีตัวที่ดูข้อมูลว่ามันเป็น Lead จริงไหม?"*
  กติกาเดิม: ลีดเข้าห้องพักเมื่อมี **เบอร์หรือ ID LINE ที่พิมพ์เป็นตัวอักษร** (`connect.contacts_in`)
  → ลูกค้าที่ส่ง **รูป QR ของ LINE** หรือแปะ **ลิงก์ line.me/ti/p/…** หลุดทั้งคู่
  (วัด prod 30 วัน: แชทที่ยังไม่มีช่องทางติดต่อ 66 ราย · ส่งรูปมา 16 ราย · มีอย่างน้อย 2 รายพิมพ์ตามว่า "ไลน์ผม")

★ อ่าน QR **ในเครื่องเรา** (zxing-cpp) — ไม่ส่งรูปลูกค้าออกไปที่ไหน
  รูปที่ลูกค้าส่งมีทั้งบัตรประชาชน/เล่มทะเบียน/สลิป → ส่งให้บริการภายนอกอ่าน = ข้อมูลส่วนบุคคลออกนอกบริษัท
  · ไลบรารีไม่มี (ยังไม่ได้ pip install) = ข้ามเงียบ ระบบเดิมทำงานตามปกติ

★ นับเฉพาะ **LINE ส่วนตัว** — QR ของบัญชีทางการ (`@xxx`) / ลิงก์กลุ่ม / QR พร้อมเพย์ในสลิป ไม่นับ
"""
from __future__ import annotations

import re

# ลิงก์เพิ่มเพื่อนของ LINE ส่วนตัว
#   https://line.me/ti/p/~myid      ← แชร์ด้วย ID (ได้ ID จริง)
#   https://line.me/ti/p/AbC12xYz   ← QR / ลิงก์ส่วนตัว (โทเคน — ไม่ใช่ ID แต่กดแล้วเพิ่มเพื่อนได้)
#   https://line.me/R/ti/p/@oa      ← บัญชีทางการ → ไม่นับ (ลูกค้าแปะลิงก์ร้าน/ส่งลิงก์ OA ของเรากลับมา)
_LINK = re.compile(r"(?:https?://)?(?:www\.)?line\.me/(?:R/)?ti/p/([~%@A-Za-z0-9._-]{3,64})", re.I)

STATE = {"lib": None}          # None = ยังไม่ได้ลอง import · True/False = มี/ไม่มีไลบรารี


def line_contact(text: str) -> str:
    """ข้อความ/ค่าที่อ่านจาก QR → ช่องทาง LINE ที่ใช้เพิ่มเพื่อนได้ ("" = ไม่ใช่ LINE ส่วนตัว)

    `~id` → คืน id เปล่า (ตรงกับที่แอดมินพิมพ์ในชีต) · โทเคน → คืน `line.me/ti/p/<โทเคน>` (เอาไปกด/สแกนต่อได้)
    """
    for m in _LINK.finditer(text or ""):
        v = m.group(1)
        if v.startswith("@") or v.lower().startswith("%40"):
            continue                                   # บัญชีทางการ ไม่ใช่ลูกค้า
        if v.startswith("~"):
            from .connect import _id_ok
            vid = _id_ok(v[1:])
            if vid:
                return vid
            continue
        if re.fullmatch(r"[A-Za-z0-9_-]{4,64}", v):
            return "line.me/ti/p/" + v
    return ""


def _lib():
    if STATE["lib"] is None:
        try:
            import zxingcpp  # noqa: F401
            STATE["lib"] = True
        except Exception:
            STATE["lib"] = False
    return STATE["lib"]


def decode(path) -> list:
    """ข้อความใน QR ทุกตัวของรูปนี้ ([] = ไม่มี/อ่านไม่ได้/ไม่มีไลบรารี) — ไม่โยน error"""
    if not _lib():
        return []
    try:
        import zxingcpp
        from PIL import Image
        with Image.open(path) as im:
            im.load()
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            if max(im.size) > 2400:                    # ภาพหน้าจอมือถือชัดพออยู่แล้ว · รูปกล้องใหญ่ย่อลงให้อ่านเร็ว
                im.thumbnail((2400, 2400))
            res = zxingcpp.read_barcodes(im, formats=zxingcpp.BarcodeFormat.QRCode)
        return [r.text for r in res if getattr(r, "text", "")]
    except Exception:
        return []


def contact_in_image(path) -> str:
    for t in decode(path):
        v = line_contact(t)
        if v:
            return v
    return ""


def owner_of(src: str, row):
    """แถวแชท (ข้อความขาเข้า 1:1) → ChatOwner ของลูกค้าคนนั้น (None = ไม่มี/ไม่ใช่แชทลูกค้า)"""
    from .models import ChatOwner, FbChat, FbProfile, GroupChat, LineProfile
    if src == "l":
        if row.chat_type == GroupChat.GROUP or row.direction != GroupChat.IN or not row.sender_id:
            return None
        prof = LineProfile.objects.filter(user_id=row.sender_id).first()
        return ChatOwner.objects.filter(profile=prof).first() if prof else None
    if row.direction == FbChat.OUT or not row.thread_id:
        return None
    fp = FbProfile.objects.filter(thread_id=row.thread_id).first()
    return ChatOwner.objects.filter(fb_profile=fp).first() if fp else None


def _images(src: str, row) -> list:
    from . import chatmedia as CM
    _, exts, _ = CM.parse(row.media_token)
    out = []
    for i, ext in enumerate(exts):
        if ext in CM.IMAGE_EXT:
            p = CM.stored(src, row, i)
            if p:
                out.append(p)
    return out


def scan_row(src: str, row, stats: dict | None = None) -> str:
    """รูปที่โหลดแล้วของข้อความนี้มี QR LINE ไหม → เติม ID LINE ให้ลีด (ช่องว่าง + คนยังไม่เคยแก้) · คืนค่าที่เติม

    เช็คลูกค้าก่อนอ่านรูป — มี ID LINE อยู่แล้ว/คนแก้ช่องนี้แล้ว = ไม่ต้องเสียเวลาอ่าน QR
    """
    from . import connect as C
    imgs = _images(src, row)
    if not imgs or not _lib():
        return ""
    o = owner_of(src, row)
    if not o or C.is_sim_row(o):
        return ""
    ld = C.lead_of(o, create=False)
    if ld and (ld.line_id or (ld.auto or {}).get("line_id") == C.HUMAN):
        if stats is not None:
            stats["had"] = stats.get("had", 0) + 1
        return ""
    for p in imgs:
        if stats is not None:
            stats["images"] = stats.get("images", 0) + 1
        v = contact_in_image(p)
        if v:
            return v if C.capture_qr(o, v, "%s%d" % (src, row.pk)) else ""
    return ""


def scan_existing(days: int = 60, limit: int = 0) -> dict:
    """ย้อนอ่าน QR ในรูปที่โหลดไว้ก่อนมีตัวนี้ (ครั้งเดียวตอน deploy · `chat_media --qr`)
    รูปใหม่ไม่ต้องใช้ตัวนี้ — อ่านให้ทันทีตอนโหลดรูป (chatmedia.ensure)"""
    from datetime import timedelta

    from django.utils import timezone

    from . import chatmedia as CM
    from .models import FbChat, GroupChat
    out = {"lib": bool(_lib()), "rows": 0, "images": 0, "had": 0, "filled": 0, "values": []}
    if not out["lib"]:
        return out
    since = timezone.now() - timedelta(days=max(1, days))
    lq = (GroupChat.objects.filter(has_media=True, direction=GroupChat.IN, sent_at__gte=since)
          .exclude(chat_type=GroupChat.GROUP).exclude(media_token="").order_by("-sent_at"))
    fq = (FbChat.objects.filter(has_media=True, direction=FbChat.IN, sent_at__gte=since)
          .exclude(media_token="").order_by("-sent_at"))
    rows = [(CM.LINE, r) for r in lq] + [(CM.FB, r) for r in fq]
    if limit:
        rows = rows[:limit]
    for src, row in rows:
        out["rows"] += 1
        try:
            v = scan_row(src, row, out)
        except Exception:
            v = ""
        if v:
            out["filled"] += 1
            out["values"].append("%s%d" % (src, row.pk))     # อ้างแถวแชท ไม่ใส่ค่า ID LINE ลงรายงาน
    return out
