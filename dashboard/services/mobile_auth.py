"""login ของแอปมือถือ — ★ 9 ต.ค.69 (demo บน iPhone ผ่าน Expo Go)

ทางเดิน (ไม่ต้องใช้ชุดเครื่องมือของ LINE · ไม่ต้องแก้อะไรใน LINE Developers):
  1. แอปเปิดเบราว์เซอร์ของระบบที่ `/m/login?r=<ที่อยู่กลับเข้าแอป>&c=<PKCE challenge>`
  2. เว็บพาไป LINE Login ตัวเดิม (ช่องเดิม → LINE user id ชุดเดียวกับเว็บ) → กลับมาที่ `/m/handoff/<pid>`
  3. เว็บส่ง "รหัสใช้ครั้งเดียว" กลับเข้าแอปทาง `r?code=…` (อายุ 2 นาที)
  4. แอปเอารหัส + รหัสลับ PKCE มาแลก token ที่ `/api/m/token` → ส่ง `Authorization: Bearer` ทุกคำขอ

กันอะไรไว้บ้าง:
  · ที่อยู่กลับเข้าแอป (`r`) รับเฉพาะรูปแบบที่อนุญาต — ไม่งั้นใครก็ทำลิงก์ให้รหัสวิ่งไปหาเครื่องตัวเองได้
  · PKCE — แอปอื่นในเครื่องที่แย่งรับลิงก์ไปได้ ก็แลกเป็น token ไม่ได้ (ไม่มีรหัสลับ)
  · เก็บแค่แฮชของรหัส/token ในฐานข้อมูล · ใช้ครั้งเดียว · มีวันหมดอายุ
  · พนักงานที่ถูกปิดใช้งานในทะเบียน → token ใช้ไม่ได้ทันที
"""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import secrets
from datetime import timedelta
from urllib.parse import urlparse

from django.conf import settings
from django.utils import timezone

LOGIN_TTL = timedelta(minutes=10)     # กด "เข้าสู่ระบบ" แล้วต้อง login LINE ให้เสร็จภายในนี้
CODE_TTL = timedelta(minutes=2)       # รหัสที่ส่งกลับเข้าแอป ต้องแลกภายในนี้
TOKEN_TTL = timedelta(days=30)
TOUCH_EVERY = timedelta(minutes=5)    # จด "ใช้ล่าสุด" ไม่ถี่กว่านี้ (ไม่เขียนฐานข้อมูลทุกคำขอ)

APP_SCHEME = "oxletauto"              # แอปตัวจริงในอนาคต (ติดตั้งจากสโตร์)


def _sha(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()


def _b64url_sha(s: str) -> str:
    d = hashlib.sha256((s or "").encode("ascii", "ignore")).digest()
    return base64.urlsafe_b64encode(d).decode("ascii").rstrip("=")


def norm_challenge(c: str) -> str:
    """รับได้ทั้ง base64 ธรรมดาและ base64url (แอปบางตัวคำนวณ sha256 ออกมาเป็น base64 ธรรมดา)"""
    return (c or "").strip().replace("+", "-").replace("/", "_").rstrip("=")


def redirect_ok(r: str) -> bool:
    """ที่อยู่กลับเข้าแอปที่ยอมส่งรหัสไปให้

    · `oxletauto://…` — แอปตัวจริงของเรา
    · `exp://<IP วงใน>:<พอร์ต>/--/…` — แอป Expo Go ตอนทดลอง (เครื่องคอมที่รันโค้ดแอปอยู่วง Wi-Fi เดียวกัน)
      ปิดได้ด้วย `MOBILE_DEV_REDIRECTS=False` ตอนเลิกใช้ Expo Go · **ไม่รับ exp ที่ชี้ออกเน็ต/ทางอุโมงค์**
      ไม่งั้นใครก็ตั้งเครื่องตัวเองแล้วส่งลิงก์ให้พนักงานกด รหัสจะวิ่งไปหาเขา
    """
    r = (r or "").strip()
    if not r or len(r) > 300 or any(ch in r for ch in "\r\n\t "):
        return False
    try:
        u = urlparse(r)
    except Exception:
        return False
    if u.scheme == APP_SCHEME:
        return True
    if u.scheme == "exp" and getattr(settings, "MOBILE_DEV_REDIRECTS", True):
        host = u.hostname or ""
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return False
        return ip.version == 4 and ip.is_private and not ip.is_loopback and (u.path or "").startswith("/--/")
    return False


def start(redirect: str, challenge: str):
    """เริ่มรายการ login → คืน (pid, error)"""
    from dashboard.models import MobileLogin
    if not redirect_ok(redirect):
        return None, "ที่อยู่กลับเข้าแอปไม่ถูกต้อง"
    ch = norm_challenge(challenge)
    if not (43 <= len(ch) <= 128):
        return None, "ข้อมูลยืนยันจากแอปไม่ครบ (challenge)"
    # กวาดของเก่าทิ้งไปด้วย (ใบผ่านทางอายุไม่กี่นาที ไม่ต้องเก็บเกินวัน)
    MobileLogin.objects.filter(created_at__lt=timezone.now() - timedelta(days=1)).delete()
    pid = secrets.token_urlsafe(24)
    MobileLogin.objects.create(pid=pid, redirect=redirect.strip(), challenge=ch)
    return pid, None


def pending(pid: str):
    """ใบผ่านทางที่ยังใช้ได้ (ยังไม่หมดอายุ ยังไม่ได้ส่งรหัส) — ไม่เจอ = None"""
    from dashboard.models import MobileLogin
    rec = MobileLogin.objects.filter(pid=pid or "", handed_at__isnull=True).first()
    if not rec or rec.created_at < timezone.now() - LOGIN_TTL:
        return None
    return rec


def hand_off(rec, user: dict) -> str:
    """login LINE ผ่านแล้ว → ออกรหัสใช้ครั้งเดียว · คืนที่อยู่ที่ต้องส่งกลับเข้าแอป"""
    code = secrets.token_urlsafe(32)
    rec.code_hash = _sha(code)
    rec.user = dict(user or {})
    rec.handed_at = timezone.now()
    rec.save(update_fields=["code_hash", "user", "handed_at"])
    sep = "&" if "?" in rec.redirect else "?"
    return "%s%scode=%s" % (rec.redirect, sep, code)


def exchange(code: str, verifier: str, device: str = ""):
    """แลกรหัสใช้ครั้งเดียว → token · คืน (token, record, error)"""
    from django.db import transaction
    from dashboard.models import MobileLogin, MobileToken
    code, verifier = (code or "").strip(), (verifier or "").strip()
    if not code or not verifier:
        return None, None, "ข้อมูลไม่ครบ"
    with transaction.atomic():
        rec = (MobileLogin.objects.select_for_update()
               .filter(code_hash=_sha(code), used_at__isnull=True, handed_at__isnull=False).first())
        if not rec or rec.handed_at < timezone.now() - CODE_TTL:
            return None, None, "รหัสหมดอายุหรือถูกใช้ไปแล้ว — กดเข้าสู่ระบบใหม่"
        if _b64url_sha(verifier) != rec.challenge:
            return None, None, "รหัสยืนยันไม่ตรง — กดเข้าสู่ระบบใหม่"
        rec.used_at = timezone.now()
        rec.save(update_fields=["used_at"])
        user = dict(rec.user or {})
    token = secrets.token_urlsafe(32)
    tok = MobileToken.objects.create(
        key_hash=_sha(token), user=user, nickname=(user.get("nickname") or "")[:120],
        device=(device or "")[:160], expires_at=timezone.now() + TOKEN_TTL)
    return token, tok, None


def _inactive(user: dict) -> bool:
    """พนักงานคนนี้ถูกปิดใช้งานในทะเบียนแล้ว (ลาออก) — อ่านไม่ได้ = ถือว่ายังใช้ได้ (เหมือนคุกกี้ของเว็บ)"""
    nick = (user or {}).get("nickname") or ""
    if not nick:
        return False
    try:
        from checkout.models import Employee
        e = Employee.objects.filter(nickname=nick).only("active").first()
        return bool(e) and not e.active
    except Exception:
        return False


def lookup(token: str):
    """token → แถว MobileToken ที่ยังใช้ได้ · ไม่ผ่าน = None"""
    from dashboard.models import MobileToken
    token = (token or "").strip()
    if not token or len(token) > 200:
        return None
    try:
        t = MobileToken.objects.filter(key_hash=_sha(token), revoked_at__isnull=True).first()
    except Exception:
        return None
    now = timezone.now()
    if not t or t.expires_at <= now or not (t.user or {}).get("position"):
        return None
    if _inactive(t.user):
        return None
    if not t.last_used_at or t.last_used_at < now - TOUCH_EVERY:
        MobileToken.objects.filter(pk=t.pk).update(last_used_at=now)
        t.last_used_at = now
    return t


def revoke(t) -> None:
    from dashboard.models import MobileToken
    MobileToken.objects.filter(pk=t.pk).update(revoked_at=timezone.now())
