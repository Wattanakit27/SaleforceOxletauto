"""context processor — ใส่ข้อมูลร่วม (บทบาท + ชื่อระบบ) ให้ทุกเทมเพลต"""
from . import roles


def nav(request):
    # context processor นี้ run ทุกหน้า (รวม sales) → ต้องทน DB ล่ม/ไม่ตั้งค่า ไม่งั้น sales พังตาม
    base = {"SITE_NAME": "Oxlet Auto · ระบบติดตามรถ", "my_role": "",
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
