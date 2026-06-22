"""
ผูก session ของ sales (oxlet_user) → Django auth ให้แอป cars/ (tracking) อัตโนมัติ
เพื่อให้แอดมินที่ login sales อยู่แล้ว เข้าแท็บ "สถานะรถ" (/track/) ได้โดยไม่ต้อง login ซ้ำ.

- ทำเฉพาะ path /track/ (ยกเว้น /track/login, /track/logout) — ไม่แตะหน้า sales เลย
  → กัน DB tracking ล่ม/ไม่ตั้งค่า ไม่ให้กระทบ sales (sales ไม่พึ่ง DB)
- ต้องวางหลัง AuthenticationMiddleware ใน MIDDLEWARE (ต้องมี request.user ก่อน)
- sales-admin (position=admin) → ตั้งเป็น Executive ของ tracking ครั้งแรก (จาก _bridge_line_to_django_user)
"""


class TrackSessionBridgeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path or ""
        if path.startswith("/track/") and "/login" not in path and "/logout" not in path:
            try:
                user = getattr(request, "user", None)
                if user is None or not user.is_authenticated:
                    sess = request.session.get("oxlet_user") or {}
                    uid = (sess.get("user_id") or "").strip()
                    if uid:
                        from dashboard.views import _bridge_line_to_django_user
                        _bridge_line_to_django_user(
                            request, uid,
                            sess.get("display_name") or sess.get("nickname") or "",
                            make_exec=(sess.get("position") == "admin"),
                        )
            except Exception:
                # DB ล่ม/ไม่ตั้งค่า → ปล่อยให้ login_required เด้งไป /track/login/ ตามปกติ (ไม่ throw)
                pass
        return self.get_response(request)
