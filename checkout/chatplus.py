# -*- coding: utf-8 -*-
"""ส่วนเสริมห้องแชทลูกค้า (Connect) สำหรับแอปมือถือ — ★ 16 ต.ค.69 (เจ้าของสั่ง "ทำตามที่แนะนำทั้งหมด")

  1. **กันส่งซ้ำ** (`client_id`) — แอปส่งแบบขึ้นข้อความทันที แล้วลองส่งซ้ำได้เมื่อเน็ตหลุด
     ถ้ารอบแรกถึง LINE แล้วแต่คำตอบหายระหว่างทาง รอบสองต้อง "ไม่ส่งซ้ำ" แต่คืนข้อความเดิมให้
     → ล็อกด้วยแถวใน `dash_kv` (key = `reply_cid:<แชท>:<client_id>`) ซึ่งใช้ร่วมทุก gunicorn worker
  2. **ส่งรูปหาลูกค้า** — LINE/Facebook ดึงรูปจากลิงก์ https สาธารณะ → เก็บสำเนาที่ `MEDIA_ROOT/chat_out/<สุ่ม>.jpg`
     (ชื่อสุ่มเดาไม่ได้ · ลบเองเมื่อเกินอายุแชทลูกค้า 60 วัน) · บันทึกลงบทสนทนาเฉพาะตอนส่งสำเร็จ (กติกาเดียวกับข้อความ)
  3. **ข้อความสำเร็จรูป** — KV `connect_canned` · ทุกคนเห็น · แอดมินเพิ่ม/แก้/ลบ
  4. **ตัวเลขยังไม่อ่าน** ต่อแถวในรายชื่อ (นับเฉพาะแถวที่ยังไม่อ่าน · เพดาน 99)
"""
from __future__ import annotations

import io
import os
import re
import time
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from . import connect as C
from .models import ChatOwner, FbChat, GroupChat

# ─────────────────────────────────────────────────────────────
#  1. กันส่งซ้ำ
# ─────────────────────────────────────────────────────────────
LOCK_PREFIX = "reply_cid:"
LOCK_STALE_SEC = 90          # ล็อกที่ค้างนานกว่านี้โดยไม่มีผล = รอบนั้นตายกลางทาง (worker ถูกรีสตาร์ท) → ให้ลองใหม่ได้
LOCK_KEEP_DAYS = 2


def clean_cid(v) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "", str(v or ""))[:36]


def msg_json(src: str, row) -> dict:
    """ข้อความขาออก 1 แถว รูปแบบเดียวกับ connect.messages() (แอปเอาไปต่อท้ายรายการได้ทันที)"""
    return {
        "id": "%s%d" % (src, row.pk), "at": C._iso(row.sent_at), "text": row.text or "", "dir": "out",
        "by": row.sent_by_name or "", "type": row.msg_type or "text", "media": bool(row.has_media),
        "files": out_files(row),
    }


def _kv():
    from dashboard.models import KVStore
    return KVStore


def lock_take(o_id: int, cid: str):
    """→ ("go", key) ส่งได้ · ("done", {"src","pk"}) เคยส่งสำเร็จแล้ว · ("busy", None) รอบก่อนกำลังส่งอยู่"""
    KV = _kv()
    key = "%s%d:%s" % (LOCK_PREFIX, int(o_id), cid)
    now = timezone.now()
    try:
        with transaction.atomic():
            KV.objects.create(key=key, data={"at": now.isoformat()})
        return "go", key
    except IntegrityError:
        pass
    kv = KV.objects.filter(pk=key).first()
    if not kv:                                   # เพิ่งถูกลบระหว่างทาง (รอบก่อนล้ม) — ลองจองใหม่ครั้งเดียว
        try:
            with transaction.atomic():
                KV.objects.create(key=key, data={"at": now.isoformat()})
            return "go", key
        except IntegrityError:
            return "busy", None
    d = kv.data or {}
    if d.get("pk"):
        return "done", d
    if (now - kv.updated_at).total_seconds() < LOCK_STALE_SEC:
        return "busy", None
    KV.objects.filter(pk=key).update(data={"at": now.isoformat()}, updated_at=now)   # ค้างจากรอบที่ตาย → รับช่วงต่อ
    return "go", key


def lock_done(key: str, src: str, pk: int) -> None:
    if not key:
        return
    KV = _kv()
    now = timezone.now()
    KV.objects.filter(pk=key).update(data={"src": src, "pk": pk, "at": now.isoformat()}, updated_at=now)
    # กวาดล็อกเก่า (เล็กมาก · ทำตอนส่งสำเร็จพอ)
    try:
        KV.objects.filter(key__startswith=LOCK_PREFIX, updated_at__lt=now - timedelta(days=LOCK_KEEP_DAYS)).delete()
    except Exception:
        pass


def lock_fail(key: str) -> None:
    """ส่งไม่สำเร็จ = ปลดล็อก ให้กด "ส่งอีกครั้ง" ได้ทันที"""
    if key:
        _kv().objects.filter(pk=key).delete()


def done_message(d: dict) -> dict | None:
    src, pk = d.get("src"), d.get("pk")
    model = FbChat if src == "f" else GroupChat
    row = model.objects.filter(pk=pk).first()
    return msg_json(src, row) if row else None


# ─────────────────────────────────────────────────────────────
#  2. ส่งรูปหาลูกค้า
# ─────────────────────────────────────────────────────────────
OUT_DIR = "chat_out"
MAX_IN_MB = 15               # ไฟล์ที่รับจากแอป
MAX_SIDE = 2048              # ย่อให้ด้านยาวไม่เกินนี้ (LINE รับรูปเต็มได้ไม่เกิน 10MB)
PREVIEW_SIDE = 640           # รูปตัวอย่าง (LINE บังคับไม่เกิน 1MB)


class ImageError(Exception):
    pass


def _out_root():
    return os.path.join(str(settings.MEDIA_ROOT), OUT_DIR)


def _public_base() -> str:
    return (getattr(settings, "SITE_URL", "") or "").rstrip("/")


def _media_url(rel: str) -> str:
    """path ใต้ MEDIA_ROOT → ลิงก์เต็ม (ให้ LINE/Facebook ดึงรูป)"""
    return "%s/%s/%s" % (_public_base(), settings.MEDIA_URL.strip("/"), rel)


def _encode(raw: bytes) -> tuple[bytes, bytes]:
    """รูปที่แอปส่งมา → (รูปเต็ม JPEG, รูปตัวอย่าง JPEG) · หมุนตาม EXIF · ตัด EXIF ทิ้ง (พิกัด GPS ในรูปห้ามหลุดถึงลูกค้า)"""
    from PIL import Image, ImageOps
    try:
        im = Image.open(io.BytesIO(raw))
        im = ImageOps.exif_transpose(im)
    except Exception:
        raise ImageError("เปิดไฟล์รูปนี้ไม่ได้ — ส่งได้เฉพาะรูป JPG / PNG")
    if im.mode not in ("RGB", "L"):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        try:
            bg.paste(im, mask=im.convert("RGBA").split()[-1])
        except Exception:
            bg.paste(im.convert("RGB"))
        im = bg
    elif im.mode == "L":
        im = im.convert("RGB")

    def jpg(img, side, q):
        x = img.copy()
        x.thumbnail((side, side))
        b = io.BytesIO()
        x.save(b, "JPEG", quality=q, optimize=True)
        return b.getvalue()

    full = jpg(im, MAX_SIDE, 85)
    prev = jpg(im, PREVIEW_SIDE, 75)
    return full, prev


def _save_out(full: bytes, prev: bytes) -> tuple[str, str]:
    """เก็บสำเนาสาธารณะ → (path ใต้ MEDIA_ROOT ของรูปเต็ม, ของรูปตัวอย่าง)"""
    root = _out_root()
    os.makedirs(root, exist_ok=True)
    name = uuid.uuid4().hex
    rel_full = "%s/%s.jpg" % (OUT_DIR, name)
    rel_prev = "%s/%s_p.jpg" % (OUT_DIR, name)
    for rel, data in ((rel_full, full), (rel_prev, prev)):
        p = os.path.join(str(settings.MEDIA_ROOT), rel)
        tmp = p + ".part"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, p)
    return rel_full, rel_prev


def _drop(*rels):
    for rel in rels:
        try:
            os.remove(os.path.join(str(settings.MEDIA_ROOT), rel))
        except OSError:
            pass


def out_files(row) -> list:
    """ไฟล์ของข้อความขาออกที่ส่งจากระบบ (รูปที่เราส่งหาลูกค้า) — ลิงก์ /media/ ตรง (เป็นสำเนาสาธารณะอยู่แล้ว)"""
    f = (row.extra or {}).get("out_file") if row.has_media else ""
    if not f:
        return []
    return [{"url": "/%s/%s" % (settings.MEDIA_URL.strip("/"), f), "kind": "image", "ext": "jpg", "state": "ready",
             "name": "", "size": int((row.extra or {}).get("out_size") or 0)}]


def _actor(user: dict | None):
    who = ((user or {}).get("nickname") or (user or {}).get("display_name") or "").strip()
    emp = None
    try:
        emp = C.employee_of(user or {})
    except Exception:
        emp = None
    if emp:
        who = emp.nickname
    return who or "แอดมิน", emp


def send_image(o: ChatOwner, upload, user: dict | None) -> tuple[str, object]:
    """ส่งรูป 1 รูปหาลูกค้าของแถว `o` → (src "l"/"f", แถวแชทที่บันทึก) · ส่งไม่ได้ = ImageError (ภาษาคน)

    กติกาเดียวกับส่งข้อความ: สวิตช์ล็อกการส่ง · ลูกค้าจำลองไม่ออกนอกระบบ · บันทึกเฉพาะตอนส่งสำเร็จ
    """
    from dashboard.services import line_channels as LC
    from dashboard.services.line_notify import push_line_message
    from .chat import _channel_for, _explain, reply_on

    if not upload:
        raise ImageError("ยังไม่ได้เลือกรูป")
    if upload.size > MAX_IN_MB * 1024 * 1024:
        raise ImageError("รูปใหญ่เกินไป (ไม่เกิน %d MB)" % MAX_IN_MB)
    raw = upload.read()
    full, prev = _encode(raw)
    sim = C.is_sim_row(o)
    fb = C.is_fb(o)
    base = _public_base()
    if not sim and not base.startswith("https://"):
        raise ImageError("ส่งรูปได้เฉพาะบนเซิร์ฟเวอร์จริง — LINE/Facebook ต้องดึงรูปจากลิงก์ https")

    rel_full, rel_prev = _save_out(full, prev)
    url_full, url_prev = _media_url(rel_full), _media_url(rel_prev)
    who, emp = _actor(user)
    now = timezone.now()
    extra = {"source": "connect", "out_file": rel_full, "out_preview": rel_prev, "out_size": len(full)}
    try:
        if fb:
            from dashboard.services import meta
            from .fb_send import _explain as fb_explain, _log as fb_log
            ok, why = C.fb_reply_state(o)
            if not ok:
                raise ImageError(why)
            fp = o.fb_profile
            if not fp.user_id or not fp.channel:
                raise ImageError("ไม่รู้ว่าลูกค้าคนนี้คุยกับเพจไหน — เปิดใน Business Suite แทน")
            try:
                res = meta.post("/%s/messages" % fp.channel, _token=meta.page_token(fp.channel), payload={
                    "recipient": {"id": fp.user_id}, "messaging_type": "RESPONSE",
                    "message": {"attachment": {"type": "image", "payload": {"url": url_full, "is_reusable": False}}}})
            except meta.MetaError as e:
                fb_log(fp, False, str(e))
                raise ImageError(fb_explain(e))
            except ImageError:
                raise
            except Exception as e:
                fb_log(fp, False, str(e))
                raise ImageError("ส่งไม่สำเร็จ: %s" % str(e)[:120])
            mid = str((res or {}).get("message_id") or "connect:%s:%s" % (fp.pk, now.timestamp()))
            row = FbChat.objects.create(
                thread_id=fp.thread_id or "", message_id=mid[:160], sender_id=fp.channel, sender_name="",
                msg_type="image", text="[รูป]", extra=extra, channel=fp.channel, has_media=True,
                direction=FbChat.OUT, sent_by=emp, sent_by_name=who[:80], sent_at=now)
            C._reply_done(o, now, "[รูป]", emp=emp, by=who)
            fb_log(fp, True, "")
            return "f", row

        prof = o.profile
        if sim:
            channel = "test"
        else:
            if not reply_on():
                raise ImageError("ยังปิดการส่งหาลูกค้าอยู่ (ตั้งใจล็อกไว้) — เปิดด้วย `manage.py checkout_config --reply on`")
            channel = _channel_for(prof)
            token = LC.token_of(channel) if channel else LC.dm_token()
            if not token:
                raise ImageError("ยังไม่ได้ตั้ง LINE token ของบัญชีที่คุยกับลูกค้าคนนี้")
            code, body = push_line_message(prof.user_id, [{"type": "image", "originalContentUrl": url_full,
                                                           "previewImageUrl": url_prev}], token, what="ส่งรูปหาลูกค้า")
            if code != 200:
                raise ImageError(_explain(code, body))
        row = GroupChat.objects.create(
            chat_type=GroupChat.USER, message_id="out:%s" % uuid.uuid4().hex, sender_id=prof.user_id,
            sender_name=prof.show_name or "", direction=GroupChat.OUT, msg_type=GroupChat.IMAGE, text="[รูป]",
            channel=channel, has_media=True, extra=extra, sent_by=emp, sent_by_name=who, sent_at=now)
        try:
            C.note_reply(prof.user_id, emp, now, "[รูป]", by=who)
        except Exception:
            pass
        return "l", row
    except Exception:
        _drop(rel_full, rel_prev)                # ส่งไม่ออก = ไม่ทิ้งรูปค้างบนดิสก์
        raise


def cleanup_out(days: int | None = None) -> int:
    """ลบสำเนารูปที่เราส่งหาลูกค้าเมื่อเกินอายุแชทลูกค้า (60 วัน) — วันละครั้งจาก connect.tick"""
    from .constants import CUSTOMER_CHAT_KEEP_DAYS
    days = days or CUSTOMER_CHAT_KEEP_DAYS
    root = _out_root()
    if not os.path.isdir(root):
        return 0
    cut = time.time() - days * 86400
    n = 0
    for name in os.listdir(root):
        p = os.path.join(root, name)
        try:
            if os.path.isfile(p) and os.path.getmtime(p) < cut:
                os.remove(p)
                n += 1
        except OSError:
            pass
    return n


# ─────────────────────────────────────────────────────────────
#  3. ข้อความสำเร็จรูป
# ─────────────────────────────────────────────────────────────
CANNED_KEY = "connect_canned"
CANNED_MAX = 60
TITLE_MAX, TEXT_MAX = 40, 1000


def canned_list() -> list:
    kv = _kv().objects.filter(pk=CANNED_KEY).first()
    items = (kv.data or {}).get("items") if kv else None
    return [x for x in (items or []) if isinstance(x, dict) and x.get("id") and x.get("text")]


def canned_save(item_id: str, title: str, text: str) -> tuple[bool, str]:
    title = (title or "").strip()[:TITLE_MAX]
    text = (text or "").strip()
    if not text:
        return False, "ยังไม่มีข้อความ"
    if len(text) > TEXT_MAX:
        return False, "ข้อความยาวเกินไป (ไม่เกิน %d ตัวอักษร)" % TEXT_MAX
    KV = _kv()
    with transaction.atomic():
        kv, _ = KV.objects.select_for_update().get_or_create(pk=CANNED_KEY, defaults={"data": {"items": []}})
        items = [x for x in ((kv.data or {}).get("items") or []) if isinstance(x, dict)]
        if item_id:
            hit = next((x for x in items if x.get("id") == item_id), None)
            if not hit:
                return False, "ไม่พบข้อความนี้ (อาจถูกลบไปแล้ว)"
            hit.update(title=title, text=text)
        else:
            if len(items) >= CANNED_MAX:
                return False, "มีข้อความสำเร็จรูปครบ %d ข้อความแล้ว — ลบอันที่ไม่ใช้ก่อน" % CANNED_MAX
            items.append({"id": uuid.uuid4().hex[:10], "title": title, "text": text})
        kv.data = {"items": items}
        kv.save(update_fields=["data", "updated_at"])
    return True, "บันทึกแล้ว"


def canned_delete(item_id: str) -> tuple[bool, str]:
    KV = _kv()
    with transaction.atomic():
        kv = KV.objects.select_for_update().filter(pk=CANNED_KEY).first()
        items = [x for x in ((kv.data or {}).get("items") or []) if isinstance(x, dict)] if kv else []
        left = [x for x in items if x.get("id") != item_id]
        if len(left) == len(items):
            return False, "ไม่พบข้อความนี้"
        kv.data = {"items": left}
        kv.save(update_fields=["data", "updated_at"])
    return True, "ลบแล้ว"


# ─────────────────────────────────────────────────────────────
#  4. ตัวเลขยังไม่อ่าน
# ─────────────────────────────────────────────────────────────
UNREAD_CAP = 99


def unread_counts(rows: list) -> None:
    """เติม `unreadCount` ให้แถวในรายชื่อ — นับเฉพาะแถวที่ยังไม่อ่าน (ปกติไม่กี่แถวต่อหน้า) · เพดาน 99"""
    ids = [r["id"] for r in rows if r.get("unread")]
    objs = ChatOwner.objects.select_related("profile", "fb_profile").in_bulk(ids) if ids else {}
    for r in rows:
        o = objs.get(r["id"]) if r.get("unread") else None
        if not o:
            r["unreadCount"] = 0
            continue
        if C.is_fb(o):
            fp = o.fb_profile
            qs = (FbChat.objects.filter(thread_id=fp.thread_id, direction=FbChat.IN)
                  if fp and fp.thread_id else FbChat.objects.none())
        else:
            qs = GroupChat.objects.filter(sender_id=o.profile.user_id, direction=GroupChat.IN) \
                .exclude(chat_type=GroupChat.GROUP)
        if o.read_at:
            qs = qs.filter(sent_at__gt=o.read_at)
        n = qs.order_by()[:UNREAD_CAP].count()
        r["unreadCount"] = max(1, n)             # ยังไม่อ่าน = อย่างน้อย 1 เสมอ (เวลาเครื่องคลาดนิดหน่อยต้องไม่กลายเป็น 0)


_CLEAN = {"day": ""}


def cleanup_daily() -> int | None:
    """เรียกจาก connect.tick ทุกนาที — ทำจริงวันละครั้งต่อ worker (listdir โฟลเดอร์เดียว เบามาก)"""
    today = timezone.localdate().isoformat()
    if _CLEAN["day"] == today:
        return None
    _CLEAN["day"] = today
    return cleanup_out()
