# -*- coding: utf-8 -*-
"""รับ webhook จาก TikTok for Developers → `dash_tiktok_event` (raw data) — ก.ย.69

*"ช่วยเตรียมสภาพแวดล้อมอีกอันหนึ่งหน่อย ฉันจะเอาไว้เก็บ TikTok Dev อีกอันหนึ่ง
 ขอ callback ฉันจะเอาไปวางที่ webhook ของเว็บนั้น"*

callback URL = `SITE_URL/api/tiktok/webhook` (ต้องเป็น https สาธารณะ → ใช้ได้เฉพาะบนเซิร์ฟเวอร์จริง)

**รูปแบบที่ TikTok ส่งมา** (developers.tiktok.com → Webhooks)::

    POST  header  TikTok-Signature: t=1633174587,s=18494715036ac4416a1d0a67...
          body    {"client_key": "...", "event": "authorization.removed",
                   "create_time": 1615338610, "user_openid": "...",
                   "content": "{\\"reason\\": 1}"}          ← content เป็น JSON ที่ห่อเป็น string

**ลายเซ็น** = HMAC-SHA256(client_secret, "<t>.<body ดิบทุกไบต์>") เป็น hex เทียบกับ `s`
- ตั้ง `TIKTOK_CLIENT_SECRET` แล้ว → ไม่ตรง / ไม่มี header / เวลาเก่าเกิน `MAX_SKEW_SEC` = **401 ไม่เก็บ**
- ยังไม่ตั้ง → รับและเก็บ แต่ `signature_ok = NULL` (ตั้งใจ: ช่วงตั้งค่าครั้งแรก TikTok อาจยิง
  event ทดสอบมาก่อนที่เราจะใส่ secret · ถ้าปฏิเสธ หน้า TikTok จะบอกว่า URL ใช้ไม่ได้)
  ⚠️ **อย่าปล่อยไว้แบบไม่ตั้ง** — ใครรู้ URL ก็ยิงของปลอมเข้ามาได้ (บทเรียนเดียวกับ
  `LINE_CHANNEL_SECRET` ที่เคยไม่ถูกประกาศจนข้ามการตรวจมาตลอด)

**ต้องตอบ 200 ให้เร็ว** — ตอบช้า/ไม่ใช่ 2xx TikTok จะส่งซ้ำ · กันซ้ำด้วยลายนิ้วมือของ body
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone as dt_tz

from django.conf import settings
from django.utils import timezone

MAX_BODY = 1024 * 1024        # body ใหญ่เกิน 1 MB = ไม่ใช่ event ปกติของ TikTok
MAX_SKEW_SEC = 10 * 60        # เวลาในลายเซ็นเก่าได้ไม่เกิน 10 นาที (กันเอาของเก่ามายิงซ้ำ)
STATUS_KEY = "tiktok_webhook_last"
TRIM_KEY = "tiktok_trim_last"


def secret() -> str:
    return (getattr(settings, "TIKTOK_CLIENT_SECRET", "") or "").strip()


def check_signature(header: str, body: bytes, now: float | None = None) -> tuple:
    """คืน (ผ่านไหม, เหตุผล) — เรียกเฉพาะตอนตั้ง secret แล้ว"""
    sec = secret()
    if not header:
        return False, "ไม่มี header TikTok-Signature"
    parts = {}
    for kv in header.split(","):
        k, _, v = kv.strip().partition("=")
        parts[k.strip()] = v.strip()
    t, s = parts.get("t", ""), parts.get("s", "")
    if not t.isdigit() or not s:
        return False, "รูปแบบ TikTok-Signature ไม่ถูกต้อง"
    if abs((now or time.time()) - int(t)) > MAX_SKEW_SEC:
        return False, "เวลาในลายเซ็นเก่า/ล้ำเกิน %d นาที" % (MAX_SKEW_SEC // 60)
    want = hmac.new(sec.encode("utf-8"), t.encode("ascii") + b"." + body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(want, s.lower()):
        return False, "ลายเซ็นไม่ตรง (secret ผิด หรือ body ถูกแก้ระหว่างทาง)"
    return True, ""


def _beat(**d):
    """จดครั้งล่าสุดที่ TikTok ยิงเข้ามา — แยกได้ว่า "ไม่ถูกยิง" หรือ "ถูกยิงแต่ตรวจไม่ผ่าน" """
    try:
        from . import cache_store
        cache_store.set_kv(STATUS_KEY, dict(d, at=timezone.now().isoformat()))
    except Exception:
        pass


def _trim_daily():
    """ลบ event เก่ากว่า KEEP_DAYS — วันละครั้ง (เช็คผ่าน KV) ไม่ให้ถ่วงการตอบ webhook"""
    try:
        from dashboard.models import TikTokEvent
        from . import cache_store
        today = timezone.localdate().isoformat()
        if ((cache_store.get_kv(TRIM_KEY) or {}).get("data") or {}).get("day") == today:
            return
        cut = timezone.now() - timedelta(days=TikTokEvent.KEEP_DAYS)
        n = TikTokEvent.objects.filter(received_at__lt=cut).delete()[0]
        cache_store.set_kv(TRIM_KEY, {"day": today, "deleted": n})
    except Exception:
        pass


def handle(body: bytes, sig_header: str) -> tuple:
    """ตัวรับหลัก — คืน (http status, dict ที่ตอบกลับ)"""
    from dashboard.models import TikTokEvent

    if len(body) > MAX_BODY:
        _beat(ok=False, error="body ใหญ่เกิน")
        return 413, {"ok": False, "error": "body too large"}

    sig_ok = None
    if secret():
        ok, why = check_signature(sig_header, body)
        if not ok:
            _beat(ok=False, error=why)
            try:
                from . import eventlog
                eventlog.log("webhook", name="tiktok", ok=False, reason=why)
            except Exception:
                pass
            return 401, {"ok": False, "error": "invalid signature"}
        sig_ok = True

    try:
        data = json.loads(body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        _beat(ok=False, error="body ไม่ใช่ JSON")
        return 400, {"ok": False, "error": "body is not JSON"}
    if not isinstance(data, dict):
        data = {"_body": data}

    # content มาเป็น JSON ที่ห่อเป็น string อีกชั้น — แกะออกให้ query ได้ (แกะไม่ได้ก็เก็บเป็นข้อความ)
    content = data.get("content")
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except ValueError:
            content = {"_text": content}
    if not isinstance(content, dict):
        content = {"_value": content} if content is not None else {}

    ct = None
    try:
        if data.get("create_time"):
            ct = datetime.fromtimestamp(int(data["create_time"]), tz=dt_tz.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        ct = None

    h = hashlib.sha256(body).hexdigest()
    _, created = TikTokEvent.objects.get_or_create(
        body_hash=h,
        defaults=dict(event=str(data.get("event") or "")[:80],
                      client_key=str(data.get("client_key") or "")[:80],
                      user_openid=str(data.get("user_openid") or "")[:120],
                      create_time=ct, signature_ok=sig_ok, content=content, raw=data))
    # เจ้าของช่องกดยกเลิกสิทธิ์จากฝั่ง TikTok → ปิดช่องนั้น + ทิ้ง token (เก็บไว้ก็ใช้ไม่ได้แล้ว)
    #   ทำเฉพาะ event ที่ตรวจลายเซ็นผ่าน — ไม่งั้นใครก็ยิง event ปลอมมาตัดช่องเราทิ้งได้
    if created and sig_ok and data.get("event") == "authorization.removed" and data.get("user_openid"):
        try:
            from . import tiktok_oauth
            tiktok_oauth.mark_revoked(str(data["user_openid"]))
        except Exception:
            pass
    _beat(ok=True, event=str(data.get("event") or ""), duplicate=not created,
          signed=sig_ok is True)
    _trim_daily()
    return 200, {"ok": True, "duplicate": not created}
