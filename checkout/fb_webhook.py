# -*- coding: utf-8 -*-
"""**Messenger webhook** — Facebook ส่งแชทของเพจมาเองทันทีที่มีข้อความ (4 ต.ค.69)

เจ้าของสั่ง *"ถ้าดึงจาก API รอบทุกๆ หนึ่งนาที มันจะติด Token ลองเปลี่ยนวิธีอื่นดู"*
→ เปลี่ยนจาก "เราไปถามทุกนาที" (fb_sync.sync_live) เป็น "Facebook ส่งมาเอง" · การถามเหลือเป็นตัวสำรองช้าๆ
  (ค่าตั้ง `connect_config.fb_poll_min` · ค่าตั้งต้น 10 นาที) เก็บตกกรณี webhook หลุด

Callback URL = `SITE_URL/api/meta/webhook` · ลงทะเบียนในหน้าแอป Meta + ผูกเพจกับแอป (ดู deploy/meta_webhook.md)
  - GET  = Meta ทักทายตอนลงทะเบียน (`hub.verify_token` ต้องตรง `META_WEBHOOK_VERIFY_TOKEN` → ตอบ `hub.challenge`)
  - POST = เหตุการณ์ข้อความ (`object=page`) · ตรวจลายเซ็น `X-Hub-Signature-256` ด้วย `META_APP_SECRET`

★ รับเฉพาะเพจใน `META_PAGE_IDS` — เพจบริษัทอื่น (เจ้าของทำงาน 2 บริษัท) ทิ้งเงียบ ไม่เก็บ
★ ข้อความลูกค้า (`message`) + ข้อความที่เพจตอบ (`is_echo` — ตอบใน Business Suite/แอปก็มา) → `FbChat` → Connect
  ข้อความที่ส่งจาก Connect เก็บไว้แล้วตอนส่ง (message id เดียวกัน) echo มาซ้ำ = ไม่เก็บซ้ำ
★ ลูกค้าใหม่ที่ยังไม่รู้ห้องสนทนา (t_…) → ถาม Graph API 1 ครั้งต่อคน (`/<page>/conversations?user_id=`)
  คนเดิม = ไม่ยิง API เลย
"""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone as dt_tz

from django.conf import settings
from django.utils import timezone

KV_LAST = "fb_webhook_last"


def verify_get(params) -> str | None:
    """การทักทายตอนลงทะเบียน URL → ค่า challenge ที่ต้องตอบกลับ · ไม่ผ่าน = None"""
    want = (getattr(settings, "META_WEBHOOK_VERIFY_TOKEN", "") or "").strip()
    if not want:
        return None
    if params.get("hub.mode") == "subscribe" and hmac.compare_digest(params.get("hub.verify_token") or "", want):
        return params.get("hub.challenge") or ""
    return None


def check_signature(raw: bytes, header: str) -> bool | None:
    """True = ลายเซ็นถูก · False = ผิด/ไม่มี · None = ยังไม่ได้ตั้ง META_APP_SECRET (ตรวจไม่ได้)"""
    secret = (getattr(settings, "META_APP_SECRET", "") or "").strip()
    if not secret:
        return None
    h = (header or "").strip()
    if not h.startswith("sha256="):
        return False
    want = hmac.new(secret.encode(), raw or b"", hashlib.sha256).hexdigest()
    return hmac.compare_digest(h[7:], want)


def _msg_type(m: dict) -> str:
    if m.get("sticker_id"):
        return "sticker"
    att = m.get("attachments") or []
    if att:
        t = (att[0].get("type") or "").lower()
        return t if t in ("image", "video", "audio", "file") else "file"
    return "text"


def _profile_for(pid: str, psid: str, at):
    """โปรไฟล์ลูกค้า (เพจ, PSID) — คนใหม่ถาม Graph API หาห้องสนทนา+ชื่อ 1 ครั้ง · ถามไม่ได้ = สร้างไว้ก่อน (ไม่มีชื่อ)"""
    from .models import FbProfile
    fp = FbProfile.objects.filter(channel=pid, user_id=psid).first()
    if fp and fp.thread_id:
        return fp
    try:
        from dashboard.services import meta
        from dashboard.services.meta_sync import _dt

        from .fb_sync import _CONV_FIELDS, _upsert_profile
        pt = meta.page_token(pid)
        data = meta.get("/%s/conversations" % pid, _token=pt, user_id=psid, fields=_CONV_FIELDS)
        c = next(iter(data.get("data") or []), None)
        if c:
            prof = _upsert_profile(c, pid, _dt(c.get("updated_time")))
            if prof is not None:
                prof.save()
                return prof
    except Exception:
        pass
    # หาห้องสนทนาไม่ได้ (เน็ต/โควต้า) → ห้องชั่วคราว "psid:<id>" ให้ข้อความไม่หลุดจากกัน
    #   รอบดึงสำรอง/เที่ยงคืนเจอห้องจริงเมื่อไหร่ fb_sync._upsert_profile ย้ายข้อความเข้าห้องจริงให้
    if not fp:
        fp, _ = FbProfile.objects.get_or_create(channel=pid, user_id=psid[:64],
                                               defaults={"last_seen": at or timezone.now()})
    if not fp.thread_id:
        fp.thread_id = ("psid:%s" % psid)[:64]
        fp.save(update_fields=["thread_id"])
    return fp


def handle_payload(data: dict) -> dict:
    """เหตุการณ์จาก Messenger webhook → เก็บ FbChat + แจ้ง Connect · คืนสถิติ (ไว้จด KV / ตอบกลับ)"""
    from dashboard.services import meta

    from .fb_sync import _sent_from_connect, _notify_connect
    from .models import FbChat

    ours = meta.pages()
    out = {"events": 0, "saved": 0, "dup": 0, "foreign": 0, "skipped": 0}
    if (data or {}).get("object") != "page":
        out["skipped"] += 1
        return out
    batches = {}                                       # FbProfile.pk → (fp, [FbChat ใหม่])
    for entry in (data.get("entry") or []):
        pid = str(entry.get("id") or "")
        if pid not in ours:
            out["foreign"] += len(entry.get("messaging") or []) or 1
            continue                                   # เพจบริษัทอื่น — ไม่เก็บอะไรเลย
        for ev in (entry.get("messaging") or []):
            m = ev.get("message")
            if not isinstance(m, dict) or not m.get("mid"):
                out["skipped"] += 1                    # read / delivery / postback — ไม่ใช่ข้อความ
                continue
            out["events"] += 1
            echo = bool(m.get("is_echo"))
            psid = str(((ev.get("recipient") if echo else ev.get("sender")) or {}).get("id") or "")
            if not psid or psid == pid:
                out["skipped"] += 1
                continue
            mid = str(m["mid"])[:160]
            if FbChat.objects.filter(message_id=mid).exists():
                out["dup"] += 1                        # ส่งจาก Connect ไปแล้ว / Meta ส่งซ้ำ
                continue
            ts = ev.get("timestamp")
            at = (datetime.fromtimestamp(ts / 1000, tz=dt_tz.utc) if isinstance(ts, (int, float))
                  else timezone.now())
            fp = _profile_for(pid, psid, at)
            att = m.get("attachments") or []
            row = FbChat(thread_id=fp.thread_id or "", message_id=mid,
                         sender_id=(pid if echo else psid)[:64],
                         sender_name="" if echo else (fp.display_name or "")[:120],
                         msg_type=_msg_type(m), text=m.get("text") or "",
                         sticker_id=str(m.get("sticker_id") or "")[:300],
                         extra={"webhook": True, "attachments": [{"type": a.get("type")} for a in att],
                                "app_id": m.get("app_id")},
                         has_media=bool(att), channel=pid,
                         direction=FbChat.OUT if echo else FbChat.IN, sent_at=at)
            if _sent_from_connect(row):
                out["dup"] += 1
                continue
            row.save()
            out["saved"] += 1
            if not echo:
                fp.last_seen = max(fp.last_seen or at, at)
                fp.msg_count = (fp.msg_count or 0) + 1
                fp.save(update_fields=["last_seen", "msg_count"])
            batches.setdefault(fp.pk, (fp, []))[1].append(row)
    for fp, rows in batches.values():
        _notify_connect(fp, rows)
    return out


def beat(stats: dict, sig) -> None:
    """จดครั้งล่าสุดที่ Facebook ยิงมา — หน้าตั้งค่า Connect โชว์ (แยกออกว่า "ยังไม่เคยยิงมา" กับ "ยิงมาแต่ลายเซ็นไม่ผ่าน")"""
    try:
        from dashboard.services import cache_store
        prev = (cache_store.get_kv(KV_LAST) or {}).get("data") or {}
        cache_store.set_kv(KV_LAST, dict(stats, at=timezone.now().isoformat(), sigOk=sig,
                                         hits=int(prev.get("hits") or 0) + 1))
    except Exception:
        pass


def last() -> dict:
    try:
        from dashboard.services import cache_store
        return (cache_store.get_kv(KV_LAST) or {}).get("data") or {}
    except Exception:
        return {}


def subscribe_pages(fields: str = "messages,message_echoes") -> dict:
    """ผูกเพจของเรากับแอป (ให้ Facebook ส่งเหตุการณ์ข้อความของเพจเข้า webhook) — ปุ่มในหน้าตั้งค่า Connect

    ต้องลงทะเบียน Callback URL ในหน้าแอป Meta ก่อน ไม่งั้นผูกแล้วก็ไม่มีอะไรส่งมา (ไม่พัง)
    """
    from dashboard.services import meta
    out = {}
    for pid in sorted(meta.pages()):
        try:
            pt = meta.page_token(pid)
            r = meta.post("/%s/subscribed_apps" % pid, _token=pt,
                          payload={"subscribed_fields": fields})
            out[pid] = "ok" if (r or {}).get("success") else json.dumps(r, ensure_ascii=False)[:120]
        except Exception as e:
            out[pid] = "ไม่สำเร็จ: %s" % str(e)[:120]
    return out


def subscription_status() -> dict:
    """เพจไหนผูกกับแอปแล้ว + รับเหตุการณ์อะไรบ้าง (อ่านอย่างเดียว)"""
    from dashboard.services import meta
    out = {}
    for pid in sorted(meta.pages()):
        try:
            pt = meta.page_token(pid)
            d = meta.get("/%s/subscribed_apps" % pid, _token=pt)
            apps = d.get("data") or []
            fields = sorted({f for a in apps for f in (a.get("subscribed_fields") or [])})
            out[pid] = {"subscribed": bool(apps), "fields": fields}
        except Exception as e:
            out[pid] = {"subscribed": None, "error": str(e)[:120]}
    return out


# ─────────────────────────────────────────────────────────────
#  หน้าเว็บ (public · csrf_exempt) — `/api/meta/webhook`
# ─────────────────────────────────────────────────────────────
INLINE = False            # เทสต์ตั้ง True = ประมวลผลในคำขอเลย (ปกติทำใน thread แยก ตอบ Facebook ทันที)
MAX_BODY = 1_000_000


def _work(data, sig):
    try:
        st = handle_payload(data)
    except Exception as e:
        st = {"error": str(e)[:200]}
    beat(st, sig)
    if not INLINE:
        try:
            from django.db import connection
            connection.close()
        except Exception:
            pass
    return st


def view(request):
    """GET = Meta ทักทายตอนลงทะเบียน URL · POST = เหตุการณ์ข้อความของเพจ"""
    from django.http import HttpResponse, JsonResponse
    if request.method == "GET":
        ch = verify_get(request.GET)
        if ch is None:
            return HttpResponse("verify token ไม่ตรง (META_WEBHOOK_VERIFY_TOKEN)", status=403)
        return HttpResponse(ch, content_type="text/plain")
    if request.method != "POST":
        return HttpResponse(status=405)
    raw = request.body or b""
    if len(raw) > MAX_BODY:
        return HttpResponse(status=413)
    sig = check_signature(raw, request.headers.get("X-Hub-Signature-256", ""))
    if sig is None:
        # ★ ไม่ตั้ง App Secret = ไม่รับ — ใครรู้ URL ก็ยิงแชทปลอมเข้า Connect ได้ (ต่างจาก TikTok ที่รับไว้ก่อน
        #   เพราะตรงนี้ข้อความกลายเป็นลูกค้าในคิวของเซลล์ทันที)
        beat({"rejected": "ยังไม่ได้ตั้ง META_APP_SECRET"}, None)
        return HttpResponse("META_APP_SECRET ยังไม่ได้ตั้ง", status=503)
    if sig is False:
        beat({"rejected": "ลายเซ็นไม่ตรง"}, False)
        return HttpResponse("bad signature", status=403)
    try:
        data = json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        return HttpResponse("not json", status=400)
    if INLINE:
        return JsonResponse(_work(data, sig))
    import threading
    threading.Thread(target=_work, args=(data, sig), daemon=True).start()
    return HttpResponse("EVENT_RECEIVED")          # Meta ต้องการ 200 เร็ว — ประมวลผลต่อใน thread
