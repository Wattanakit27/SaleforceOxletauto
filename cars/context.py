"""context processor — ใส่ข้อมูลร่วม (บทบาท + ชื่อระบบ + เวอร์ชัน) ให้ทุกเทมเพลต"""
import subprocess

from django.conf import settings

from . import roles

_app_version: str | None = None   # cache ต่อ process — git rev-list รันครั้งเดียว


def app_version() -> str:
    """เวอร์ชันแอปจากจำนวน git commit ÷ 10 (100 commits = v10.0) — สูตรที่เจ้าของกำหนด (ส.ค.69).
    รันครั้งเดียวต่อ process · ไม่มี git/.git (เช่น deploy แบบ copy) → '' (ป้ายซ่อนตัวเอง)"""
    global _app_version
    if _app_version is None:
        try:
            n = int(subprocess.run(
                ["git", "rev-list", "--count", "HEAD"],
                capture_output=True, text=True, timeout=5, cwd=settings.BASE_DIR,
            ).stdout.strip())
            _app_version = f"v{n / 10:.1f}"
        except Exception:
            _app_version = ""
    return _app_version


def nav(request):
    # context processor นี้ run ทุกหน้า (รวม sales) → ต้องทน DB ล่ม/ไม่ตั้งค่า ไม่งั้น sales พังตาม
    base = {"SITE_NAME": "Oxlet Auto · ระบบติดตามรถ", "my_role": "",
            "APP_VERSION": app_version(),
            "can_add_car": False, "can_view_admin": False, "can_manage_users": False}
    # context processor นี้ run ทุกหน้า — แต่ทำ DB query เฉพาะหน้า /track/ เท่านั้น
    # (กันหน้า sales เสีย latency จาก query ข้ามภูมิภาคไป Supabase Sydney โดยไม่จำเป็น)
    if not (getattr(request, "path", "") or "").startswith("/track/"):
        return base
    try:
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated):
            return base
        base.update({
            "my_role": roles.role_label(user),
            "can_add_car": roles.can_add_car(user),
            "can_view_admin": roles.can_view_admin(user),
            "can_manage_users": roles.can_manage_users(user),
        })
    except Exception:
        pass
    return base
