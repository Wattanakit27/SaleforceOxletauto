# -*- coding: utf-8 -*-
"""ดึงแชท Facebook Messenger ของเพจเรา → `FbChat` / `FbProfile` (raw data) — ก.ย.69

*"ส่วนระบบ CRM ก็เป็น raw data ตั้งชื่อ table ให้เหมือนกับ CRM ฝั่ง LINE"*
→ เจ้าของเลือก **ตารางแยก ชื่อคู่ขนาน** (checkout_fbchat ↔ checkout_groupchat ·
  checkout_fbprofile ↔ checkout_lineprofile)

**เรียกจาก `meta_sync.run()`** — รอบเที่ยงคืนต่อจากดึงโพสต์/โฆษณา และตอนกดปุ่ม sync เอง
**ทุกคำขอผ่าน `meta.py`** → เพจของบริษัทอื่นหลุดเข้ามาไม่ได้

**ทำไมไม่ดึงทุกห้องทุกคืน** — วัดจริง ก.ย.69 มี ≥8,200 ห้อง · ≥115,000 ข้อความ
ถ้ายิงขอข้อความทุกห้อง = หลายพันคำขอต่อคืน โควต้าเต็มแน่
→ จำ `updated_time` ของห้องไว้ใน `FbProfile.thread_updated` · ห้องที่ **เวลาเท่าเดิม = ไม่มีอะไรใหม่**
  ข้ามได้เลยโดยไม่ยิง API (การขอ "รายชื่อห้อง" ถูกมาก — 100 ห้องต่อ 1 คำขอ)
→ ห้องที่ขยับ: ดึงข้อความจากใหม่ไปเก่า **หยุดทันทีที่เจอข้อความที่มีอยู่แล้ว**

**รอบแรกจะไม่ครบในคืนเดียว (ตั้งใจ)** — มีเพดานจำนวนห้อง/เวลา/โควต้าต่อรอบ
ห้องที่ยังไม่ได้ดึงจะถูกหยิบต่อในคืนถัดไปเอง (เพราะ thread_updated ยังไม่ตรง)
คืนปกติมีห้องขยับแค่ ~100-150 ห้อง (วัดจาก "คนคุยรายวัน")

**อายุข้อมูล = ฝั่ง LINE** (`CUSTOMER_CHAT_KEEP_DAYS` 60 วัน) — บทสนทนากับคนนอกที่ไม่ได้
ยินยอมอะไรกับเรา เก็บเท่าที่ใช้พอ · ข้อความเก่ากว่านั้นไม่ดึง และที่มีอยู่จะถูกลบ
"""
from __future__ import annotations

import time
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from . import constants as C

KEEP_DAYS = C.CUSTOMER_CHAT_KEEP_DAYS
# เพดานต่อรอบ — กันรอบแรก (ย้อนหลังหลายพันห้อง) กินโควต้า/เวลาจนงานอื่นเสีย
MAX_THREADS = {"cron": 600, "manual": 150}
TIME_BUDGET_SEC = {"cron": 12 * 60, "manual": 4 * 60}
STOP_USAGE_PCT = 60          # โควต้าเกินนี้ = หยุดดึงแชท เก็บที่เหลือไว้ให้งานอื่น
MAX_MSG_PAGES = 20           # ห้องเดียวดึงข้อความได้สูงสุด 20 หน้า × 100 ต่อรอบ

_CONV_FIELDS = "id,updated_time,message_count,unread_count,can_reply,link,participants"
_MSG_FIELDS = ("id,created_time,from,to,message,tags,sticker,"
               "attachments{id,mime_type,name,size,image_data,video_data,file_url}")


def _clean(m: dict) -> dict:
    """ข้อความดิบที่จะเก็บ — ตัด paging (มี token) + email ปลอมของ Meta (`<id>@facebook.com`)"""
    from dashboard.services.meta_sync import _raw
    d = _raw(m)
    for k in ("from",):
        if isinstance(d.get(k), dict):
            d[k].pop("email", None)
    to = d.get("to")
    if isinstance(to, dict):
        for x in (to.get("data") or []):
            if isinstance(x, dict):
                x.pop("email", None)
    return d


def _msg_type(m: dict) -> str:
    if m.get("sticker"):
        return "sticker"
    att = ((m.get("attachments") or {}).get("data") or [])
    if att:
        mt = (att[0].get("mime_type") or "").lower()
        for k in ("image", "video", "audio"):
            if mt.startswith(k):
                return k
        return "file"
    return "text"


def _sync_thread(cid: str, pid: str, pt: str, floor) -> tuple:
    """ดึงข้อความใหม่ของห้องเดียว → คืน (จำนวนข้อความใหม่, เวลาข้อความเก่าสุดที่เห็น)"""
    from dashboard.services import meta
    from dashboard.services.meta_sync import _dt
    from .models import FbChat

    new, oldest = 0, None
    for chunk in meta.paged("/%s/messages" % cid, _token=pt, fields=_MSG_FIELDS,
                            limit=100, max_pages=MAX_MSG_PAGES):
        rows = chunk.get("data") or []
        ids = [str(m.get("id")) for m in rows if m.get("id")]
        have = set(FbChat.objects.filter(message_id__in=ids).values_list("message_id", flat=True))
        objs, stop = [], False
        for m in rows:
            mid = str(m.get("id") or "")
            if not mid:
                continue
            if mid in have:              # เรียงใหม่→เก่า เจอของที่มีแล้ว = ที่เหลือมีหมดแล้ว
                stop = True
                break
            ct = _dt(m.get("created_time"))
            if ct and ct < floor:        # เก่ากว่าอายุข้อมูล ไม่ต้องเก็บ
                stop = True
                break
            f = m.get("from") or {}
            out = str(f.get("id") or "") == pid
            att = ((m.get("attachments") or {}).get("data") or [])
            objs.append(FbChat(
                thread_id=cid, message_id=mid[:160],
                sender_id=str(f.get("id") or "")[:64], sender_name=(f.get("name") or "")[:120],
                msg_type=_msg_type(m), text=m.get("message") or "",
                sticker_id=str(m.get("sticker") or "")[:300],
                extra=_clean(m), has_media=bool(att), channel=pid,
                direction=FbChat.OUT if out else FbChat.IN,
                sent_at=ct))
            if ct and (oldest is None or ct < oldest):
                oldest = ct
        if objs:
            FbChat.objects.bulk_create(objs, ignore_conflicts=True)
            new += len(objs)
        if stop:
            break
    return new, oldest


def _upsert_profile(c: dict, pid: str, ut):
    from dashboard.services.meta_sync import _raw
    from .models import FbProfile

    parts = ((c.get("participants") or {}).get("data") or [])
    cust = next((p for p in parts if str(p.get("id")) != pid), None)
    if not cust or not cust.get("id"):
        return None
    link = c.get("link") or ""
    if link.startswith("/"):
        link = "https://www.facebook.com" + link
    raw = _raw(c)
    for p in ((raw.get("participants") or {}).get("data") or []):
        p.pop("email", None)                 # email ปลอมของ Meta ไม่มีประโยชน์
    prof, created = FbProfile.objects.get_or_create(
        channel=pid, user_id=str(cust["id"])[:64],
        defaults={"display_name": (cust.get("name") or "")[:120], "last_seen": ut or timezone.now()})
    prof.display_name = (cust.get("name") or prof.display_name)[:120]
    prof.thread_id = str(c.get("id") or "")[:64]
    prof.inbox_link = link[:300]
    prof.msg_count = int(c.get("message_count") or prof.msg_count or 0)
    if ut:
        prof.last_seen = ut
    prof.raw = raw
    return prof


def trim() -> dict:
    """ลบของเกินอายุ — กติกาเดียวกับแชทลูกค้าฝั่ง LINE (`_cleanup_chat`)"""
    from .models import FbChat, FbProfile
    cut = timezone.now() - timedelta(days=KEEP_DAYS)
    try:
        n = FbChat.objects.filter(sent_at__lt=cut).delete()[0]
        p = FbProfile.objects.filter(is_employee=False, last_seen__lt=cut).delete()[0]
        return {"msgs": n, "profiles": p}
    except Exception:
        return {"msgs": 0, "profiles": 0}


def sync(trigger: str = "cron", touch=None) -> dict:
    """ดึงแชททุกเพจของเรา 1 รอบ · `touch()` = ต่ออายุล็อกระหว่างทาง (รอบแรกอาจยาวหลายนาที)"""
    from dashboard.services import meta
    from dashboard.services.meta_sync import _dt

    t0 = time.time()
    floor = timezone.now() - timedelta(days=KEEP_DAYS)
    cap = MAX_THREADS.get(trigger, 150)
    budget = TIME_BUDGET_SEC.get(trigger, 240)
    out = {"threadsSeen": 0, "threadsSynced": 0, "unchanged": 0, "newMsgs": 0,
           "profiles": 0, "pages": {}, "stopped": "", "errors": []}

    def _halt() -> str:
        if out["threadsSynced"] >= cap:
            return "ครบเพดาน %d ห้องต่อรอบ — ที่เหลือดึงต่อรอบหน้า" % cap
        if time.time() - t0 > budget:
            return "ครบเวลา %d นาทีต่อรอบ — ที่เหลือดึงต่อรอบหน้า" % (budget // 60)
        if (meta.last_usage.get("pct") or 0) >= STOP_USAGE_PCT:
            return "โควต้า Meta เกิน %d%% — หยุดไว้ก่อน" % STOP_USAGE_PCT
        return ""

    for pid in sorted(meta.pages()):
        n_page = 0
        try:
            pt = meta.page_token(pid)
            done = False
            for chunk in meta.paged("/%s/conversations" % pid, _token=pt,
                                    fields=_CONV_FIELDS, limit=100, max_pages=200):
                for c in (chunk.get("data") or []):
                    ut = _dt(c.get("updated_time"))
                    if ut and ut < floor:            # เรียงใหม่→เก่า ถึงห้องที่เงียบเกินอายุข้อมูลแล้ว
                        done = True
                        break
                    out["threadsSeen"] += 1
                    prof = _upsert_profile(c, pid, ut)
                    if prof is None:
                        continue
                    if prof.pk and prof.thread_updated and ut and prof.thread_updated == ut:
                        out["unchanged"] += 1        # ไม่มีอะไรใหม่ — ไม่ต้องยิง API
                        continue
                    why = _halt()
                    if why:
                        out["stopped"] = why
                        done = True
                        break
                    new, oldest = _sync_thread(str(c["id"]), pid, pt, floor)
                    with transaction.atomic():
                        prof.thread_updated = ut
                        prof.fetched_at = timezone.now()
                        if oldest and (not prof.first_seen or oldest < prof.first_seen):
                            prof.first_seen = oldest
                        prof.save()
                    out["newMsgs"] += new
                    out["threadsSynced"] += 1
                    n_page += 1
                    if touch and out["threadsSynced"] % 20 == 0:
                        touch()
                if done:
                    break
        except meta.MetaError as e:
            out["errors"].append("แชทเพจ %s: %s" % (pid, str(e)[:120]))
        out["pages"][pid] = n_page
        if out["stopped"]:
            break

    from .models import FbProfile
    out["profiles"] = FbProfile.objects.count()
    out["trimmed"] = trim()
    out["sec"] = int(time.time() - t0)
    return out
