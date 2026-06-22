"""context processor — ใส่ข้อมูลร่วม (บทบาท + ชื่อระบบ) ให้ทุกเทมเพลต"""
from . import roles


def nav(request):
    user = getattr(request, "user", None)
    return {
        "SITE_NAME": "Oxlet Auto · ระบบติดตามรถ",
        "my_role": roles.role_label(user) if user and user.is_authenticated else "",
        "can_add_car": user.is_authenticated and roles.can_add_car(user) if user else False,
        "can_view_admin": user.is_authenticated and roles.can_view_admin(user) if user else False,
        "can_manage_users": user.is_authenticated and roles.can_manage_users(user) if user else False,
    }
