# -*- coding: utf-8 -*-
"""เชื่อมช่อง TikTok หลายช่องเข้าระบบ (Login Kit / OAuth v2) — ก.ย.69

ขั้นตอนที่เจ้าของทำ: ลงทะเบียน Redirect URI `https://<โดเมน>/api/tiktok/webhook` ในแท็บ Web
ของแอป OXLETAUTO แล้ว → ต่อจากนั้นเป็นงานของไฟล์นี้:

  1. `make_link(label)`  สร้างลิงก์ขออนุญาต "รายช่อง" → ส่งให้เจ้าของช่องแต่ละช่องเปิด
  2. เจ้าของช่องกดอนุญาต → TikTok พากลับมาที่ `/api/tiktok/webhook?code=…&state=…`
  3. `callback()`         ตรวจ state → แลก code เป็น access/refresh token → ดึงชื่อช่อง → เก็บ
  4. `refresh_due()`      cron เรียกทุกนาที · ต่ออายุ access token ก่อนหมด 2 ชม.
  5. `access_token_for()` ให้โค้ดที่จะดึงยอดวิว/ไลก์ของคลิปในอนาคตเอา token ไปใช้

**state เป็นเลขสุ่ม ไม่ใช่ชื่อช่อง** (เอกสารที่เจ้าของได้มาให้ใส่ state=CHANNEL_ID) —
state ที่เดาได้ = ใครก็สร้างลิงก์ปลอมพาช่องของตัวเองมาผูกกับชื่อช่องของเราได้ · เราเก็บ
"state → ชื่อช่องที่ตั้ง" ไว้ฝั่งเซิร์ฟเวอร์ ใช้ได้ครั้งเดียว หมดอายุ 7 วัน

**token เข้ารหัสก่อนเก็บ** (Fernet · กุญแจจาก SECRET_KEY) — หน้า SQL/ไฟล์ export ที่ผู้บริหาร
เปิดดูได้จะเห็นแต่ค่าที่เข้ารหัส · ถือ token = อ่านข้อมูลช่องนั้นได้แทนเรา
"""
from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.utils import timezone

AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
USER_URL = "https://open.tiktokapis.com/v2/user/info/"
TIMEOUT = 20
STATE_TTL_DAYS = 7            # ส่งลิงก์ให้เจ้าของช่องหลายคน แต่ละคนเปิดไม่พร้อมกัน
REFRESH_BEFORE = timedelta(hours=2)
REFRESH_PER_TICK = 3          # cron ยิงทุกนาที — ต่ออายุทีละไม่กี่ช่อง ไม่ให้ cron_tick ช้า
_STATE_PREFIX = "tiktok_oauth:"


class TikTokError(RuntimeError):
    pass


# ── ค่าตั้ง ──────────────────────────────────────────────────────
def client_key() -> str:
    return (getattr(settings, "TIKTOK_CLIENT_KEY", "") or "").strip()


def client_secret() -> str:
    return (getattr(settings, "TIKTOK_CLIENT_SECRET", "") or "").strip()


def redirect_uri() -> str:
    v = (getattr(settings, "TIKTOK_REDIRECT_URI", "") or "").strip()
    return v or (getattr(settings, "SITE_URL", "") or "").rstrip("/") + "/api/tiktok/webhook"


def scopes() -> str:
    return (getattr(settings, "TIKTOK_SCOPES", "") or "user.info.basic,video.list").replace(" ", "")


def is_configured() -> bool:
    return bool(client_key() and client_secret())


# ── เข้ารหัส token ─────────────────────────────────────────────────
def _fernet():
    from cryptography.fernet import Fernet
    raw = hashlib.sha256(b"oxlet-tiktok-token:" + settings.SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(raw))


def enc(v: str) -> str:
    return _fernet().encrypt(v.encode("utf-8")).decode("ascii") if v else ""


def dec(v: str) -> str:
    if not v:
        return ""
    try:
        return _fernet().decrypt(v.encode("ascii")).decode("utf-8")
    except Exception:
        raise TikTokError("ถอดรหัส token ไม่ได้ (SECRET_KEY อาจถูกเปลี่ยน) — ให้เจ้าของช่องกดอนุญาตใหม่")


# ── 1) ลิงก์ขออนุญาต ─────────────────────────────────────────────
def make_link(label: str, by: str = "") -> str:
    """ลิงก์ให้เจ้าของช่องเปิดแล้วกดอนุญาต — 1 ลิงก์ต่อ 1 ช่อง ใช้ได้ครั้งเดียว"""
    from . import cache_store
    if not client_key():
        raise TikTokError("ยังไม่ได้ตั้ง TIKTOK_CLIENT_KEY")
    state = secrets.token_urlsafe(24)
    cache_store.set_kv(_STATE_PREFIX + state, {
        "label": (label or "").strip()[:120], "by": (by or "")[:80],
        "created": timezone.now().isoformat()})
    return AUTHORIZE_URL + "?" + urlencode({
        "client_key": client_key(), "response_type": "code", "scope": scopes(),
        "redirect_uri": redirect_uri(), "state": state})


def _take_state(state: str) -> dict | None:
    """ดึง state แล้วลบทิ้ง (ใช้ได้ครั้งเดียว) · หมดอายุ = None"""
    from datetime import datetime
    from . import cache_store
    if not state or len(state) > 100:
        return None
    key = _STATE_PREFIX + state
    d = (cache_store.get_kv(key) or {}).get("data") or {}
    if not d:
        return None
    cache_store.set_kv(key, {})                      # ใช้แล้วทิ้ง — เปิดลิงก์ซ้ำ/ส่งต่อไม่ได้
    try:
        if timezone.now() - datetime.fromisoformat(d["created"]) > timedelta(days=STATE_TTL_DAYS):
            return None
    except (KeyError, ValueError):
        return None
    return d


# ── 2-3) รับ code → แลก token → เก็บ ──────────────────────────────
def _post_token(data: dict) -> dict:
    try:
        r = requests.post(TOKEN_URL, data=dict(data, client_key=client_key(),
                                               client_secret=client_secret()),
                          headers={"Content-Type": "application/x-www-form-urlencoded",
                                   "Cache-Control": "no-cache"}, timeout=TIMEOUT)
        j = r.json()
    except requests.RequestException as e:
        raise TikTokError("ต่อ TikTok ไม่ได้: %s" % str(e)[:120])
    except ValueError:
        raise TikTokError("TikTok ตอบไม่ใช่ JSON (HTTP %s)" % r.status_code)
    if j.get("error") or not j.get("access_token"):
        raise TikTokError("TikTok ปฏิเสธ: %s %s" % (j.get("error") or "",
                                                   (j.get("error_description") or "")[:160]))
    return j


def _fetch_user(token: str, scope: str) -> dict:
    """ข้อมูลช่อง — ขอเฉพาะช่องที่สิทธิ์ครอบคลุม (ขอเกินสิทธิ์ TikTok ปฏิเสธทั้งคำขอ) · ไม่เอารูปโปรไฟล์"""
    fields = ["open_id", "union_id", "display_name"]
    sc = set((scope or "").split(","))
    if "user.info.profile" in sc:
        fields += ["username", "is_verified"]
    if "user.info.stats" in sc:
        fields += ["follower_count", "following_count", "likes_count", "video_count"]
    try:
        r = requests.get(USER_URL, params={"fields": ",".join(fields)},
                         headers={"Authorization": "Bearer " + token}, timeout=TIMEOUT)
        j = r.json()
    except (requests.RequestException, ValueError):
        return {}
    return ((j.get("data") or {}).get("user") or {}) if isinstance(j, dict) else {}


def _apply_token(acc, j: dict):
    now = timezone.now()
    acc.access_token = enc(j["access_token"])
    acc.access_expires_at = now + timedelta(seconds=int(j.get("expires_in") or 86400))
    if j.get("refresh_token"):
        acc.refresh_token = enc(j["refresh_token"])
        acc.refresh_expires_at = now + timedelta(seconds=int(j.get("refresh_expires_in") or 31536000))
    if j.get("scope"):
        acc.scope = str(j["scope"])[:300]
    acc.status = acc.ACTIVE
    acc.last_error = ""


def callback(params) -> tuple:
    """TikTok พาเจ้าของช่องกลับมา → คืน (http status, ข้อความหน้าเว็บ, ชื่อช่อง)"""
    from dashboard.models import TikTokAccount
    from . import eventlog

    if params.get("error"):
        why = (params.get("error_description") or params.get("error") or "")[:200]
        eventlog.log("tiktok_oauth", name="ปฏิเสธ/ยกเลิก", ok=False, reason=why)
        return 400, "ไม่ได้เชื่อมช่อง — TikTok แจ้งว่า: %s" % why, ""
    if not is_configured():
        return 503, "ระบบยังไม่ได้ตั้งค่า TikTok (client key / secret) — แจ้งผู้ดูแลระบบ", ""
    st = _take_state(params.get("state", ""))
    if st is None:
        eventlog.log("tiktok_oauth", name="state ไม่ถูกต้อง", ok=False)
        return 400, ("ลิงก์นี้ใช้ไม่ได้แล้ว (ใช้ไปแล้ว / หมดอายุ 7 วัน / ไม่ได้สร้างจากระบบเรา) — "
                     "ขอลิงก์ใหม่จากผู้ดูแลระบบ"), ""
    code = params.get("code", "")
    if not code:
        return 400, "TikTok ไม่ได้ส่งรหัสอนุญาตมา — ลองเปิดลิงก์ใหม่อีกครั้ง", ""
    try:
        j = _post_token({"code": code, "grant_type": "authorization_code",
                         "redirect_uri": redirect_uri()})
    except TikTokError as e:
        eventlog.log("tiktok_oauth", name="แลก token ไม่ได้", ok=False, reason=str(e)[:200],
                     label=st.get("label"))
        return 502, "เชื่อมช่องไม่สำเร็จ: %s" % e, st.get("label", "")

    oid = str(j.get("open_id") or "")[:120]
    acc = TikTokAccount.objects.filter(open_id=oid).first() or TikTokAccount(open_id=oid)
    _apply_token(acc, j)
    u = _fetch_user(j["access_token"], j.get("scope") or "")
    acc.label = st.get("label") or acc.label
    acc.display_name = (u.get("display_name") or acc.display_name or "")[:200]
    acc.username = (u.get("username") or acc.username or "")[:120]
    acc.profile = u
    acc.connected_by = st.get("by") or acc.connected_by
    acc.refreshed_at = timezone.now()
    acc.save()
    eventlog.log("tiktok_oauth", name="เชื่อมช่องแล้ว", ok=True, label=acc.label,
                 channel=acc.display_name, scope=acc.scope)
    return 200, "เชื่อมช่องเรียบร้อย", (acc.display_name or acc.label)


# ── 4) ต่ออายุ ──────────────────────────────────────────────────────
def refresh(acc) -> bool:
    try:
        rt = dec(acc.refresh_token)
        if not rt:
            raise TikTokError("ไม่มี refresh token")
        j = _post_token({"grant_type": "refresh_token", "refresh_token": rt})
    except TikTokError as e:
        acc.status = acc.ERROR
        acc.last_error = str(e)[:300]
        acc.save(update_fields=["status", "last_error"])
        return False
    _apply_token(acc, j)
    acc.refreshed_at = timezone.now()
    acc.save()
    return True


def refresh_due(limit: int = REFRESH_PER_TICK) -> dict:
    """เรียกจาก cron_tick — ต่ออายุช่องที่ access token ใกล้หมด (ทีละไม่กี่ช่อง)"""
    from dashboard.models import TikTokAccount
    if not is_configured():
        return {}
    soon = timezone.now() + REFRESH_BEFORE
    qs = (TikTokAccount.objects.exclude(status=TikTokAccount.REVOKED)
          .filter(access_expires_at__lt=soon).order_by("access_expires_at")[:limit])
    done = {"ok": 0, "fail": 0}
    for acc in qs:
        done["ok" if refresh(acc) else "fail"] += 1
    return done if (done["ok"] or done["fail"]) else {}


# ── 5) ให้โค้ดอื่นเอา token ไปใช้ ─────────────────────────────────────
def access_token_for(open_id: str) -> str:
    """access token (ถอดรหัสแล้ว) ของช่องนี้ · ใกล้หมดก็ต่ออายุให้ก่อน"""
    from dashboard.models import TikTokAccount
    acc = TikTokAccount.objects.get(open_id=open_id)
    if acc.status == acc.REVOKED:
        raise TikTokError("เจ้าของช่องยกเลิกสิทธิ์แล้ว")
    if not acc.access_expires_at or acc.access_expires_at < timezone.now() + timedelta(minutes=5):
        if not refresh(acc):
            raise TikTokError("ต่ออายุ token ไม่สำเร็จ: %s" % acc.last_error)
    return dec(acc.access_token)


def mark_revoked(open_id: str) -> int:
    """webhook `authorization.removed` = เจ้าของช่องกดยกเลิกสิทธิ์จากฝั่ง TikTok"""
    from dashboard.models import TikTokAccount
    return TikTokAccount.objects.filter(open_id=open_id).update(
        status=TikTokAccount.REVOKED, access_token="", refresh_token="",
        last_error="เจ้าของช่องยกเลิกสิทธิ์ (authorization.removed)")
