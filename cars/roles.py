"""
ระบบสิทธิ์ 7 บทบาท (1 user = 1 บทบาท ผ่าน Django Group)
  Executive    ผู้บริหาร   - ทำได้ทุกอย่าง (superuser = Executive เสมอ)
  Purchasing   จัดซื้อ     - เพิ่ม/แก้รถ, เลื่อนสเตปช่วงรับเข้า (ไม่ต้องสแกน)
  Admin        แอดมิน      - แก้ข้อมูลรถ + จัดการ user (เพิ่มรถ/เปลี่ยนสเตปไม่ได้)
  Sales        เซลล์       - งานตรวจ/ขาย ผ่านการสแกน
  Technician   ช่าง        - งานซ่อม/ดีเทล ผ่านการสแกน
  Vendor       อู่นอก      - ทำสี/เบาะ ผ่านการสแกน
  Registration ฝ่ายทะเบียน - โอน/ภาษี/พ.ร.บ./ป้าย ผ่านการสแกน

แนวคิด: บทบาททำงาน (Sales/Tech/Vendor/Registration) เปลี่ยนสเตปได้ทาง "การสแกน" เท่านั้น
        Executive/Purchasing เปลี่ยนตรงผ่าน UI ได้
"""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

# ===== คีย์บทบาท (ชื่อ Group) =====
EXEC = "Executive"
PURCHASING = "Purchasing"
ADMIN = "Admin"
SALES = "Sales"
TECH = "Technician"
VENDOR = "Vendor"
REGIST = "Registration"

ROLES = [
    (EXEC, "ผู้บริหาร"),
    (PURCHASING, "จัดซื้อ"),
    (ADMIN, "แอดมิน"),
    (SALES, "เซลล์"),
    (TECH, "ช่าง"),
    (VENDOR, "อู่นอก"),
    (REGIST, "ฝ่ายทะเบียน"),
]
ROLE_LABEL = dict(ROLES)

# สเตป -> เซตบทบาทที่ "กดเปลี่ยนเข้าสเตปนั้น" ได้ (Executive ได้ทุกสเตปเสมอ)
STAGE_ROLES = {
    "intake":       {PURCHASING},
    "appraise":     {PURCHASING},
    "repair":       {TECH},
    "wait_paint":   {TECH, VENDOR},
    "paint":        {VENDOR},
    "parts":        {TECH},
    "upholstery":   {VENDOR, TECH},
    "film":         {TECH},
    "detail":       {TECH},
    "qc":           {SALES},
    "rework":       {TECH},
    "registration": {REGIST},
    "show":         {SALES},
    "reserve":      {SALES},
    "finance":      {SALES, REGIST},
    "closing":      {SALES},
    "sold":         {SALES},
}

# บทบาทที่ต้อง "สแกนก่อน" ถึงจะเปลี่ยนสเตปได้ (เปลี่ยนตรงผ่าน UI ไม่ได้)
SCAN_ONLY_ROLES = {SALES, TECH, VENDOR, REGIST}


def set_user_role(user, role_key):
    """ตั้งบทบาทให้ user (1 คน 1 บทบาท) — ล้างของเดิมแล้วใส่ group ใหม่"""
    from django.contrib.auth.models import Group
    user.groups.clear()
    if role_key:
        group, _ = Group.objects.get_or_create(name=role_key)
        user.groups.add(group)


def get_role(user):
    """คืนคีย์บทบาทของ user (superuser = Executive) หรือ None"""
    if not getattr(user, "is_authenticated", False):
        return None
    if user.is_superuser:
        return EXEC
    names = set(user.groups.values_list("name", flat=True))
    for key, _ in ROLES:
        if key in names:
            return key
    return None


def role_label(user):
    return ROLE_LABEL.get(get_role(user), "ไม่มีบทบาท")


# ===== ความสามารถ =====
def is_exec(user):        return get_role(user) == EXEC
def can_manage_users(user): return get_role(user) in {EXEC, ADMIN}
def can_add_car(user):    return get_role(user) in {EXEC, PURCHASING}
def can_edit_car(user):   return get_role(user) in {EXEC, PURCHASING, ADMIN}
def can_delete_car(user): return get_role(user) == EXEC
def can_view_admin(user): return get_role(user) in {EXEC, PURCHASING, ADMIN}
def is_worker(user):      return get_role(user) in SCAN_ONLY_ROLES


def allowed_stages(user):
    """รายชื่อคีย์สเตปที่ user เปลี่ยนได้"""
    role = get_role(user)
    if role == EXEC:
        return list(STAGE_ROLES.keys())
    return [s for s, rs in STAGE_ROLES.items() if role in rs]


def can_set_stage(user, stage):
    return is_exec(user) or (get_role(user) in STAGE_ROLES.get(stage, set()))


def can_set_stage_direct(user, stage):
    """เปลี่ยนสเตปผ่าน UI โดยตรง (ไม่สแกน) — เฉพาะ Exec/Purchasing"""
    if get_role(user) in SCAN_ONLY_ROLES:
        return False
    return can_set_stage(user, stage)


# ===== decorator =====
def role_required(check):
    """ครอบ view: ต้องล็อกอิน + ผ่าน check(user) ไม่งั้น 403"""
    def deco(view):
        @wraps(view)
        @login_required
        def _wrapped(request, *args, **kwargs):
            if not check(request.user):
                raise PermissionDenied("คุณไม่มีสิทธิ์เข้าถึงส่วนนี้")
            return view(request, *args, **kwargs)
        return _wrapped
    return deco
