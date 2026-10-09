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
