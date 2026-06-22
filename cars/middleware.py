"""
ผูก session ของ sales (oxlet_user) → Django auth ให้แอป cars/ (tracking) อัตโนมัติ
เพื่อให้แอดมินที่ login sales อยู่แล้ว เข้าแท็บ "สถานะรถ" (/track/) ได้โดยไม่ต้อง login ซ้ำ.

- ทำเฉพาะ path /track/ (ยกเว้น /track/login, /track/logout) — ไม่แตะหน้า sales เลย
  → กัน DB tracking ล่ม/ไม่ตั้งค่า ไม่ให้กระทบ sales (sales ไม่พึ่ง DB)
- ต้องวางหลัง AuthenticationMiddleware ใน MIDDLEWARE (ต้องมี request.user ก่อน)
- sales-admin (position=admin) → ตั้งเป็น Executive ของ tracking ครั้งแรก (จาก _bridge_line_to_django_user)
- ถ้า bridge ไม่สำเร็จ (DB ยังไม่ต่อ/ล่ม) ทั้งที่ login sales อยู่ → คืนหน้า "ยังไม่พร้อม"
  แทนที่จะปล่อยให้ login_required เด้งไป /login/ แล้ววนกลับ /track/ (redirect loop)
"""
from django.http import HttpResponse

_UNAVAILABLE_HTML = """<!doctype html><html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ระบบติดตามรถยังไม่พร้อม</title>
<style>body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
font-family:'Segoe UI',Tahoma,sans-serif;background:#0f1220;color:#e8ebf5}
.box{max-width:460px;text-align:center;padding:32px}
h1{font-size:20px;margin:0 0 10px}p{color:#8b93a7;font-size:14px;line-height:1.7;margin:6px 0}
code{background:#1a1f33;padding:2px 7px;border-radius:6px;font-size:12px;color:#c9d2ec}</style></head>
<body><div class="box">
<div style="font-size:42px;margin-bottom:8px">🚗🔌</div>
<h1>ระบบติดตามรถยังไม่พร้อมใช้งาน</h1>
<p>ยังไม่ได้เชื่อมต่อฐานข้อมูล (Supabase Postgres) บนเซิร์ฟเวอร์</p>
<p>ผู้ดูแลระบบต้องตั้งค่า <code>DATABASE_URL</code> + รัน migrate ก่อน<br>
ระบบยอดขาย (sales) ใช้งานได้ตามปกติ — กลับไปแท็บอื่นได้เลย</p>
</div></body></html>"""


class TrackSessionBridgeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path or ""
        if path.startswith("/track/") and "/login" not in path and "/logout" not in path:
            user = getattr(request, "user", None)
            if user is None or not user.is_authenticated:
                sess = request.session.get("oxlet_user") or {}
                uid = (sess.get("user_id") or "").strip()
                if uid:
                    try:
                        from dashboard.views import _bridge_line_to_django_user
                        _bridge_line_to_django_user(
                            request, uid,
                            sess.get("display_name") or sess.get("nickname") or "",
                            make_exec=(sess.get("position") == "admin"),
                        )
                    except Exception:
                        pass
                    # ผูกไม่สำเร็จ (DB ยังไม่ต่อ/ล่ม) แต่ login sales อยู่ → ตัด redirect loop
                    u2 = getattr(request, "user", None)
                    if u2 is None or not u2.is_authenticated:
                        return HttpResponse(_UNAVAILABLE_HTML, status=200,
                                            content_type="text/html; charset=utf-8")
        return self.get_response(request)
