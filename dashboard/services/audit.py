"""audit — บันทึกเหตุการณ์เข้าสู่ระบบ (login log) ลง tracking DB (cars.LoginEvent)

best-effort: ถ้า DB ล่ม / ยังไม่ migrate / ไม่ได้ต่อ DB → ข้ามเงียบ ไม่ทำให้ login พัง
(sales เป็น Sheets-based ไม่มี local DB · เขียน log ลง Postgres ของระบบ tracking)
"""


def _client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR") or ""
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or ""


def log_login(request, *, identity="", name="", method="", success=True, role="", reason=""):
    """สร้าง 1 แถวใน LoginEvent — เรียกจากทุกจุด login (สำเร็จ/ล้มเหลว)."""
    try:
        from cars.models import LoginEvent
        LoginEvent.objects.create(
            identity=(identity or "")[:200],
            name=(name or "")[:200],
            method=(method or "")[:20],
            success=bool(success),
            role=(role or "")[:40],
            ip=_client_ip(request)[:64],
            user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:300],
            reason=(reason or "")[:200],
        )
    except Exception:
        pass  # DB ล่ม/ยังไม่ migrate = ไม่ทำให้ login พัง
