# -*- coding: utf-8 -*-
"""ตอบแชท **Facebook Messenger** จากหน้า Connect (4 ต.ค.69 · เจ้าของเลือก "รวมคิวเดียวกับ LINE")

ส่งผ่าน Send API ของเพจที่ลูกค้าคุยอยู่ (`POST /<page_id>/messages` ด้วย page token — ผ่านด่าน `meta.post`
ที่กันเพจบริษัทอื่น) · กติกาเดียวกับฝั่ง LINE (`chat.send_reply`):
  - **ส่งไม่สำเร็จ = ไม่บันทึกลงบทสนทนา** (ไม่งั้นมีข้อความที่ลูกค้าไม่เคยได้รับปนอยู่)
  - สำเร็จ = เก็บลง `FbChat` ทันที (ขาออก + ชื่อคนตอบ) แล้วปิดรอบรอคำตอบใน Connect
    รอบซิงก์ถัดไปเจอข้อความเดิม = ไม่เก็บซ้ำ (message id ตรงกัน / `fb_sync._sent_from_connect`)

★ สวิตช์ `connect_config.fb_reply` (off / **test** / on) — เริ่มที่ test: ตอบได้เฉพาะ "แชททดสอบ" ที่แอดมินกำหนด
  (เจ้าของสั่ง "ทดสอบกับบัญชี FB ของเจ้าของก่อน ไม่ส่งหาลูกค้าจริง")

⚠️ กติกาของ Facebook: ตอบได้ภายใน **24 ชม.** นับจากข้อความล่าสุดของลูกค้า (`messaging_type=RESPONSE`)
   เกินนั้น Meta ปฏิเสธ → บอกให้ตอบใน Business Suite แทน (ระบบไม่ใส่ message tag เลี่ยงกติกา)
"""
from __future__ import annotations

from django.utils import timezone

from .chat import ReplyError

MAX_LEN = 2000            # Send API รับข้อความไม่เกิน 2000 ตัวอักษร


def _explain(e) -> str:
    """แปล error ของ Meta เป็นภาษาคน — โยน error ดิบให้แอดมินดูแล้วไม่มีใครรู้ว่าต้องทำอะไรต่อ"""
    code, sub = getattr(e, "code", None), getattr(e, "subcode", None)
    msg = str(e)
    if sub == 2018278 or (code == 10 and "window" in msg.lower()):
        return "เกิน 24 ชม. นับจากข้อความล่าสุดของลูกค้า — Facebook ไม่ให้ส่งแล้ว ตอบใน Facebook (Business Suite) แทน"
    if code == 551 or sub == 1545041:
        return "ลูกค้าคนนี้รับข้อความไม่ได้ (บล็อกเพจ/ปิดบัญชี)"
    if code in (200, 10, 230):
        return "แอป Meta ยังไม่มีสิทธิ์ส่งข้อความหาลูกค้าคนนี้ (%s) — ตอบใน Business Suite ไปก่อน" % msg[:120]
    if code in (4, 17, 32, 613):
        return "ส่งถี่เกินโควต้าของ Facebook — รอสักครู่แล้วลองใหม่"
    return "Facebook ไม่รับข้อความ: %s" % msg[:160]


def send_reply(o, text: str, user: dict | None = None):
    """ตอบลูกค้า FB ของแถว Connect `o` → แถว FbChat ที่บันทึก · ส่งไม่ได้ = ReplyError (ข้อความภาษาคน)"""
    from dashboard.services import meta

    from . import connect as C
    from .models import FbChat

    if not C.is_fb(o):
        raise ReplyError("ลูกค้าคนนี้ไม่ใช่ลูกค้า Facebook")
    ok, why = C.fb_reply_state(o)
    if not ok:
        raise ReplyError(why)
    text = (text or "").strip()
    if not text:
        raise ReplyError("พิมพ์ข้อความก่อนส่ง")
    if len(text) > MAX_LEN:
        raise ReplyError("ข้อความยาวเกินไป (ไม่เกิน %d ตัวอักษร)" % MAX_LEN)
    fp = o.fb_profile
    if not fp.user_id or not fp.channel:
        raise ReplyError("ไม่รู้ว่าลูกค้าคนนี้คุยกับเพจไหน — เปิดใน Business Suite แทน")
    try:
        pt = meta.page_token(fp.channel)
        res = meta.post("/%s/messages" % fp.channel, _token=pt, payload={
            "recipient": {"id": fp.user_id}, "messaging_type": "RESPONSE", "message": {"text": text}})
    except meta.MetaError as e:
        _log(fp, False, str(e))
        raise ReplyError(_explain(e))
    except Exception as e:                        # เน็ต/อื่นๆ — ไม่บันทึกลงบทสนทนา
        _log(fp, False, str(e))
        raise ReplyError("ส่งไม่สำเร็จ: %s" % str(e)[:120])

    emp = None
    try:
        emp = C.employee_of(user or {})
    except Exception:
        emp = None
    name = (emp.nickname if emp else "") or (user or {}).get("nickname") or (user or {}).get("display_name") or "แอดมิน"
    now = timezone.now()
    mid = str((res or {}).get("message_id") or "connect:%s:%s" % (fp.pk, now.timestamp()))
    row = FbChat.objects.create(
        thread_id=fp.thread_id or "", message_id=mid[:160], sender_id=fp.channel, sender_name="",
        msg_type="text", text=text, extra={"source": "connect"}, channel=fp.channel,
        direction=FbChat.OUT, sent_by=emp, sent_by_name=name[:80], sent_at=now)
    C._reply_done(o, now, text, emp=emp, by=name)
    _log(fp, True, "")
    return row


def _log(fp, ok: bool, err: str):
    """จดลง dash_event_log แบบเดียวกับการส่ง LINE (ตรวจย้อนหลังได้ว่าส่งถึงไหม) — จดไม่ได้ไม่เป็นไร"""
    try:
        from dashboard.services import eventlog
        eventlog.log("fb_send", name="ตอบแชท Facebook (Connect)", target=fp.channel, ok=ok,
                     error=(err or "")[:200])
    except Exception:
        pass
