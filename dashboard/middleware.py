"""แอปมือถือส่ง `Authorization: Bearer <token>` แทนคุกกี้ — ★ 9 ต.ค.69

ทำให้คำขอนั้น "เหมือนคนที่ login เว็บอยู่" → API เดิมทั้งหมด (Connect · ระบบติดตามรถ · เบิก-คืนรถ)
ใช้กับแอปได้เลย ไม่ต้องเขียน API ชุดใหม่ เพราะทุกตัวเช็คสิทธิ์จาก `request.session["oxlet_user"]`

- ใส่ `oxlet_user` ลง session ชั่วคราวของคำขอนั้น (**ไม่บันทึก ไม่ส่งคุกกี้กลับ**) — token คือตัวยืนยันทุกครั้ง
- ไม่ต้องใช้ CSRF token: CSRF คือการโจมตีที่อาศัย "เบราว์เซอร์แนบคุกกี้ให้เอง" · header Authorization
  เว็บอื่นแนบมาให้ไม่ได้ (ไม่ได้เปิด CORS) → ปลอดภัยที่จะข้าม · คำขอที่ใช้คุกกี้ยังโดนตรวจ CSRF ตามเดิม
- `/track/` ใช้ระบบ login ของ Django → `TrackSessionBridgeMiddleware` (อยู่ถัดไป) ผูกให้เองจาก oxlet_user ชุดนี้
- token ผิด/หมดอายุ/ถูกยกเลิก → 401 JSON ทันที (แอปเด้งไปหน้า login) · ไม่ตกไปใช้คุกกี้แทน

ต้องอยู่หลัง AuthenticationMiddleware และก่อน TrackSessionBridgeMiddleware ใน MIDDLEWARE
"""
from importlib import import_module

from django.conf import settings
from django.http import JsonResponse


class MobileTokenMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self._store = import_module(settings.SESSION_ENGINE).SessionStore

    def __call__(self, request):
        auth = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth.startswith("Bearer "):
            return self.get_response(request)
        from .services import mobile_auth
        tok = mobile_auth.lookup(auth[7:])
        if not tok:
            return JsonResponse({"ok": False, "error": "หมดเวลาใช้งาน กรุณาเข้าสู่ระบบใหม่", "relogin": True},
                                status=401, json_dumps_params={"ensure_ascii": False})
        sess = self._store()
        sess["oxlet_user"] = dict(tok.user)
        request.session = sess
        # บัญชีคนงาน (ช่าง/ฝ่ายทะเบียน · login ด้วยชื่อผู้ใช้+รหัส) = Django user ที่มีอยู่แล้วพร้อมบทบาท
        # → ผูกตรงตัว ไม่งั้น TrackSessionBridgeMiddleware จะสร้าง `line_django_<ชื่อ>` บัญชีใหม่ที่ไม่มีบทบาท
        #   แล้วคนงานเปลี่ยนสเตปรถจากแอปไม่ได้ · ถูกปิดใช้งานที่ /track/users/ = token ใช้ไม่ได้ทันที
        uid = (tok.user or {}).get("user_id") or ""
        if uid.startswith("django_"):
            from django.contrib.auth.models import User
            duser = User.objects.filter(username=uid[len("django_"):], is_active=True).first()
            if not duser:
                return JsonResponse({"ok": False, "error": "บัญชีนี้ถูกปิดใช้งานแล้ว", "relogin": True},
                                    status=401, json_dumps_params={"ensure_ascii": False})
            request.user = duser
        request.mobile_token = tok
        request._dont_enforce_csrf_checks = True
        response = self.get_response(request)
        # ไม่ให้ SessionMiddleware เขียนคุกกี้กลับไปให้แอป (ตัวตนของแอปอยู่ที่ token อย่างเดียว)
        try:
            request.session.modified = False
        except Exception:
            pass
        return response


# ─────────────────────────────────────────────────────────────────────────────
# ★ 23 ต.ค.69 ไม่ให้ `?next=` โผล่ในแถบที่อยู่ (เจ้าของ: "next= นี่คืออะไร เจอบ่อยมาก ไม่อยากให้มี")
#
# `next` = หน้าที่จะพากลับไปหลัง login (เปิด /dashboard/ ตอนยังไม่ login → เด้งไป /login/?next=/dashboard/)
# ทุกจุดที่เด้งไปหน้า login (views หลายตัว · @login_required ของระบบรถ · /track/login/ · JS ใน Connect)
# ยังเขียน `?next=` เหมือนเดิม — ตัวนี้ดักที่จุดเดียว: ย้ายค่าไปเก็บใน session แล้วพาไป /login/ เปล่าๆ
#   - คำตอบที่เด้งไป /login/?next=X  → เก็บ X · เปลี่ยนที่อยู่เป็น /login/ (พารามิเตอร์อื่นอย่าง bg/pw คงไว้)
#   - เปิด /login/?next=X ตรงๆ (ลิงก์เก่า/JS) → เก็บ X แล้วพาไป /login/ อีกครั้ง
#   - หน้า login อ่านค่าคืนด้วย `login_next(request)` · login แล้ว (มี oxlet_user) เปิดหน้าอื่น = ล้างทิ้ง
# ไม่แตะ: แอปมือถือ (`/m/…` — อยู่ในเบราว์เซอร์ของแอป ใช้ next ในลิงก์ตามเดิม) · คำขอที่ใช้ token
# next ที่ไม่ใช่ path ในเว็บเรา (https://… · //… ) = ทิ้ง ไม่เก็บ (กันพาไปเว็บอื่น)
# ─────────────────────────────────────────────────────────────────────────────
import time as _time
from urllib.parse import parse_qsl, urlencode, urlsplit

from django.http import HttpResponseRedirect

LOGIN_PATH = "/login/"
NEXT_KEY = "login_next"
NEXT_TTL = 30 * 60          # เก็บไว้ 30 นาที (ลืมทิ้งไว้แล้วกลับมา login ทีหลัง = ไปหน้าแรกตามปกติ)
_SKIP_PREFIX = ("/m/",)     # ทางของแอปมือถือ — ไม่ย้าย


def safe_next(url) -> str:
    """path ในเว็บเราเท่านั้น · ไม่ใช่ = ''"""
    u = str(url or "").strip()
    if not u or len(u) > 500 or not u.startswith("/") or u.startswith("//") or u.startswith("/\\"):
        return ""
    if any(c in u for c in "\r\n\t"):
        return ""
    return u


def _skip(nxt: str) -> bool:
    return nxt.startswith(_SKIP_PREFIX)


def _store(request, nxt: str) -> None:
    try:
        request.session[NEXT_KEY] = {"u": nxt, "t": int(_time.time())}
    except Exception:
        pass


def login_next(request) -> str:
    """หน้าที่จะพากลับหลัง login ที่เก็บไว้ (หมดอายุ/ไม่มี = '')"""
    try:
        rec = request.session.get(NEXT_KEY) or {}
    except Exception:
        return ""
    if not isinstance(rec, dict) or int(_time.time()) - int(rec.get("t") or 0) > NEXT_TTL:
        return ""
    return safe_next(rec.get("u"))


def _without_next(pairs) -> str:
    rest = [(k, v) for k, v in pairs if k != "next"]
    return LOGIN_PATH + ("?" + urlencode(rest) if rest else "")


class LoginNextMiddleware:
    """ต้องอยู่หลัง SessionMiddleware (ใช้ request.session) — ดูคำอธิบายด้านบน"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(request, "session", None) is None or request.META.get("HTTP_AUTHORIZATION", "").startswith("Bearer "):
            return self.get_response(request)
        # เปิด /login/?next=… ตรงๆ → เก็บค่าแล้วพาไป /login/ ที่ไม่มี next
        if request.method == "GET" and request.path == LOGIN_PATH and "next" in request.GET:
            nxt = request.GET.get("next") or ""
            if not _skip(nxt):
                s = safe_next(nxt)
                if s:
                    _store(request, s)
                return HttpResponseRedirect(_without_next(parse_qsl(request.META.get("QUERY_STRING", ""),
                                                                    keep_blank_values=True)))
        response = self.get_response(request)
        if getattr(request, "mobile_token", None):
            return response
        try:
            self._after(request, response)
        except Exception:
            pass
        return response

    def _after(self, request, response):
        loc = response.get("Location") if response.status_code in (301, 302, 303, 307, 308) else None
        if loc:
            parts = urlsplit(loc)
            same = not parts.netloc or parts.netloc == request.get_host()
            if same and parts.path == LOGIN_PATH and parts.query:
                pairs = parse_qsl(parts.query, keep_blank_values=True)
                nxt = dict(pairs).get("next")
                if nxt is not None and not _skip(nxt):
                    s = safe_next(nxt)
                    if s:
                        _store(request, s)
                    response["Location"] = _without_next(pairs)
                    return
        # login แล้วเปิดหน้าอื่น = ใช้ค่าไปแล้ว (หรือไม่ใช้แล้ว) → ล้าง
        p = request.path
        if p.startswith(LOGIN_PATH) or p.startswith("/auth/") or p.startswith("/static/"):
            return
        sess = request.session
        if NEXT_KEY in sess and sess.get("oxlet_user"):
            sess.pop(NEXT_KEY, None)
