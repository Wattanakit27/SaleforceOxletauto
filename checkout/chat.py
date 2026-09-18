# -*- coding: utf-8 -*-
"""ตอบแชทลูกค้าจากหน้าเว็บ + เก็บบทสนทนาทั้ง 2 ฝั่ง — ก.ย.69 (เจ้าของสั่ง)

*"อยากให้พัฒนาระบบแชทขึ้นมา เอาไว้ตอบแชทของลูกค้าที่เราเก็บใน CRM ไว้ …
  การที่เราตอบแชทในนี้จะบอกได้ด้วยว่า admin ตอบลูกค้ายังไงบ้าง
  และเราสามารถพัฒนา chatbot เองได้ด้วยจากช่องทางของเราเอง"*

**ทำไมต้องเก็บขาออกด้วย** — ของเดิมเก็บแต่ขาเข้า อ่านย้อนหลังเลยเห็นแต่ฝั่งลูกค้าพูด
ไม่รู้ว่าแอดมินตอบอะไรกลับ = เอาไปสอน chatbot ไม่ได้ เพราะไม่มีคู่ "ถาม-ตอบ"
พอตอบผ่านหน้านี้ ทุกคำตอบถูกบันทึกเป็นข้อมูลสอนไปในตัว

⚠️ **ข้อความที่แอดมินตอบจากแอป LINE OA Manager เราไม่เห็น** — LINE ไม่ส่ง event
   ขาออกของตัวเองกลับมาทาง webhook · จะได้ข้อมูลครบก็ต่อเมื่อตอบผ่านหน้านี้เท่านั้น
"""
from __future__ import annotations

import uuid

from django.utils import timezone

from dashboard.services import line_channels as LC
from dashboard.services.line_notify import push_line_message

from .models import GroupChat, LineProfile

# LINE จำกัดข้อความละ 5,000 ตัวอักษร — ตัดฝั่งเราก่อนเพื่อให้ error อ่านรู้เรื่อง
# (ถ้าปล่อยไป LINE ตอบ 400 ซึ่งไม่บอกว่าเพราะยาวเกิน)
MAX_LEN = 4800


class ReplyError(Exception):
    """ส่งไม่ได้ — ข้อความในนี้เอาไปโชว์ผู้ใช้ได้เลย (ภาษาคน ไม่ใช่ error ดิบ)"""


def reply_on() -> bool:
    """เปิดให้ส่งข้อความหาลูกค้าจริงหรือยัง — **ปิดโดยปริยาย**

    ★ ก.ย.69 เจ้าของสั่ง: *"อย่าเพิ่งส่งข้อความอะไรหาลูกค้านะ"*

    **ทำไมต้องมีสวิตช์แยก ทั้งที่ปุ่มอยู่หลัง login แอดมินอยู่แล้ว** — ปุ่มที่ส่งของจริงออกไป
    หาคนนอกบริษัท กดพลาดแล้วเรียกคืนไม่ได้ · ระหว่างที่ยังทดสอบกันอยู่ ต้องล็อกไว้ที่
    ฝั่งเซิร์ฟเวอร์ ไม่ใช่แค่ซ่อนปุ่ม (ยิง API ตรงได้) · กติกาเดียวกับ `lineout.send_on()`
    ที่คุมการโพสต์เข้ากลุ่ม

    เปิดเมื่อพร้อม: `manage.py checkout_config --reply on`
    """
    try:
        from dashboard.services import cache_store
        cfg = (cache_store.get_kv("checkout_line_config") or {}).get("data") or {}
        return bool(cfg.get("reply_customer"))
    except Exception:
        return False                      # อ่านค่าไม่ได้ = ถือว่าปิด (fail-safe)


def _channel_for(prof: LineProfile) -> str:
    """ลูกค้าคนนี้คุยอยู่กับบัญชี OA ตัวไหน

    **สำคัญมาก** — ตอบผิดบัญชีคือ LINE ตอบ 400 หรือ (แย่กว่า) ส่งไปไม่ถึงเงียบๆ
    เพราะ push เข้าแชท 1:1 ได้เฉพาะคนที่ *เพิ่มบัญชีนั้นเป็นเพื่อน* แล้วเท่านั้น

    ลำดับ: บัญชีที่ได้ยินข้อความล่าสุดของคนนี้ → บัญชีที่เจอเขาครั้งแรก → ตัวรับ (ค่าเริ่มต้น)
    """
    last = (GroupChat.objects
            .filter(sender_id=prof.user_id, direction=GroupChat.IN)
            .exclude(channel="")
            .order_by("-sent_at", "-id")
            .values_list("channel", flat=True)
            .first())
    return last or prof.channel or ""


def conversation(user_id: str, limit: int = 200) -> list:
    """บทสนทนาของคนนี้ **ทั้ง 2 ฝั่ง** เรียงเก่า→ใหม่ (อ่านเป็นบทสนทนา)"""
    rows = list(GroupChat.objects
                .filter(sender_id=user_id)
                .exclude(chat_type=GroupChat.GROUP)
                .order_by("-sent_at", "-id")[:limit])
    rows.reverse()
    return rows


def send_reply(user_id: str, text: str, actor: dict | None = None) -> GroupChat:
    """ตอบลูกค้า 1 ข้อความ → คืนแถว `GroupChat` ที่บันทึกไว้

    `actor` = session `oxlet_user` ของแอดมินที่กดส่ง (ใช้บอกว่า "ใครเป็นคนตอบ")

    **บันทึกลงฐานข้อมูลเฉพาะตอนส่งสำเร็จ** — ถ้าจดตอนล้มด้วย บทสนทนาจะมีข้อความ
    ที่ลูกค้าไม่เคยได้รับปนอยู่ แล้วคนอ่านทีหลัง (หรือ chatbot ที่เอาไปเรียน)
    จะเข้าใจผิดว่าเราตอบไปแล้ว · ที่ล้มไปจดไว้ใน `dash_event_log` แทน
    """
    text = (text or "").strip()
    if not text:
        raise ReplyError("ยังไม่ได้พิมพ์ข้อความ")
    if len(text) > MAX_LEN:
        raise ReplyError("ข้อความยาวเกินไป (%d ตัว) — LINE รับได้ไม่เกิน %d"
                         % (len(text), MAX_LEN))

    prof = LineProfile.objects.filter(user_id=user_id).first()
    if not prof:
        raise ReplyError("ไม่รู้จักลูกค้าคนนี้ (ยังไม่เคยมีข้อความเข้ามา)")

    # ★ ด่านสุดท้ายก่อนออกไปหาคนนอกบริษัท — เช็คหลังตรวจ input ครบแล้ว
    #   เพื่อให้คนทดสอบเจอ error เรื่องข้อความผิดก่อน ไม่ใช่มาติดตรงนี้แล้วไม่รู้ว่าอย่างอื่นถูกไหม
    if not reply_on():
        raise ReplyError("ยังปิดการส่งหาลูกค้าอยู่ (ตั้งใจล็อกไว้) — "
                         "เปิดด้วยคำสั่ง `manage.py checkout_config --reply on` บนเซิร์ฟเวอร์")

    channel = _channel_for(prof)
    token = LC.token_of(channel) if channel else LC.dm_token()
    if not token:
        raise ReplyError("ยังไม่ได้ตั้ง LINE token ของบัญชีที่คุยกับลูกค้าคนนี้")

    code, body = push_line_message(user_id, [{"type": "text", "text": text}], token,
                                   what="ตอบแชทลูกค้า")
    if code != 200:
        raise ReplyError(_explain(code, body))

    who = ""
    emp = None
    if actor:
        who = (actor.get("nickname") or actor.get("display_name")
               or actor.get("seller_name") or "").strip()
        if who:
            from .models import Employee
            emp = Employee.objects.filter(nickname=who).first()

    now = timezone.now()
    row = GroupChat.objects.create(
        chat_type=GroupChat.USER,
        message_id="out:%s" % uuid.uuid4().hex,   # ขาออกไม่มี id จาก LINE → ออกเอง
        sender_id=user_id,                        # = "คู่สนทนา" ไม่ใช่คนพิมพ์ (ให้ query รวมง่าย)
        sender_name=prof.show_name or "",
        direction=GroupChat.OUT,
        msg_type=GroupChat.TEXT,
        text=text,
        channel=channel,
        sent_by=emp,
        sent_by_name=who,
        sent_at=now,
    )
    LineProfile.objects.filter(pk=prof.pk).update(last_seen=now)
    return row


def _explain(code: int, body: str) -> str:
    """แปลคำตอบของ LINE เป็นภาษาที่แอดมินอ่านแล้วรู้ว่าต้องทำอะไรต่อ

    เดิมโยน error ดิบให้ผู้ใช้ดู → เห็น `{"message":"Invalid to"}` แล้วก็ไม่รู้จะทำยังไงต่อ
    """
    b = (body or "")
    if code == 400 and "Invalid to" in b:
        return "ส่งไม่ได้ — ลูกค้าอาจบล็อก/ลบบัญชีนี้ออกจากเพื่อนแล้ว"
    if code == 403:
        return "บัญชี LINE นี้ไม่มีสิทธิ์ส่งข้อความ (เช็คว่าใช้ token ถูกบัญชีไหม)"
    if code == 429:
        return "ส่งถี่เกินไป หรือโควตาข้อความเดือนนี้หมดแล้ว — ลองใหม่อีกครั้ง"
    if code == 401:
        return "LINE token หมดอายุ/ไม่ถูกต้อง — ต้องตั้งค่าใหม่ใน .env"
    return "LINE ปฏิเสธ (สถานะ %s) %s" % (code, b[:160])
