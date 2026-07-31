"""
ระบบสิทธิ์ 11 บทบาท (1 user = 1 บทบาท ผ่าน Django Group)
  Executive    ผู้บริหาร   - ทำได้ทุกอย่าง (superuser = Executive เสมอ)
  Purchasing   จัดซื้อ     - เพิ่ม/แก้รถ, รับเข้า (ไม่ต้องสแกน)
  Admin        แอดมิน      - แก้ข้อมูลรถ + จัดการ user (เพิ่มรถ/เปลี่ยนสเตปไม่ได้)
  Sales        เซลล์       - งานขาย (show/reserve/finance/closing/release) ผ่านการสแกน
  Technician   ช่าง        - ซ่อม/อะไหล่/ฟิล์ม ผ่านการสแกน
  Vendor       อู่นอก      - อู่สีนอก/เบาะ ผ่านการสแกน
  Registration ฝ่ายทะเบียน - FULL_ROLES (ทำได้ทุกสเตป + จัดการรถ/ผู้ใช้)
  CarWash      ฝ่ายล้างรถ  - ชงล้างรถ ผ่านการสแกน
  Production   โปรดักชัน   - รถรอถ่ายรูป + ส่งต่อไป ซ่อม/สี/ล้าง + ถ่ายคอนเทนต์ (แทรกทุกสเตป)
  QC           QC          - รอตรวจขึ้นโชว์ + ตรวจรอปล่อย · FULL_ROLES (สิทธิ์เยอะเท่าฝ่ายทะเบียน)
  PaintIn      อู่สีใน     - อู่สีใน · FULL_ROLES (ตามที่ตั้ง)

แนวคิด: บทบาททำงาน (Sales/Tech/Vendor/CarWash/Production) เปลี่ยนสเตปได้ทาง "การสแกน" เท่านั้น
        Executive/Purchasing/Registration/QC/PaintIn เปลี่ยนตรงผ่าน UI ได้ (FULL_ROLES)
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
CARWASH = "CarWash"
PRODUCTION = "Production"
QC = "QC"
PAINTIN = "PaintIn"

ROLES = [
    (EXEC, "ผู้บริหาร"),
    (PURCHASING, "จัดซื้อ"),
    (ADMIN, "แอดมิน"),
    (SALES, "เซลล์"),
    (TECH, "ช่าง"),
    (VENDOR, "อู่นอก"),
    (REGIST, "ฝ่ายทะเบียน"),
    (CARWASH, "ฝ่ายล้างรถ"),
    (PRODUCTION, "โปรดักชัน"),
    (QC, "QC"),
    (PAINTIN, "อู่สีใน"),
]
ROLE_LABEL = dict(ROLES)

# สเตป -> เซตบทบาทที่ "กดเปลี่ยนเข้าสเตปนั้น" ได้ (FULL_ROLES = Exec/Regist/QC/PaintIn ได้ทุกสเตปเสมอ)
# โปรดักชัน: photo_wait + route ไป repair/paint_out/wash · QC/อู่สีใน = full (ทำได้ทุกสเตป · qc_show/qc_release เป็นของ QC)
STAGE_ROLES = {
    "intake":     {PURCHASING},
    "photo_wait": {PRODUCTION},
    "repair":     {TECH, PRODUCTION},
    "parts":      {TECH},
    "upholstery": {VENDOR, TECH},
    "paint_in":   set(),                 # อู่สีใน = PAINTIN (FULL) เท่านั้น
    "paint_out":  {VENDOR, PRODUCTION},
    "film":       {TECH},
    "wash":       {CARWASH, PRODUCTION},
    "qc_show":    set(),                 # QC (FULL) เท่านั้น
    "show":       {SALES},
    "reserve":    {SALES},
    "finance":    {SALES},
    "closing":    {SALES},
    "qc_release": set(),                 # QC (FULL) · บังคับแนบรูป/วิดีโอ
    "release":    {SALES},               # เซลล์ปิด (QC/ผู้บริหาร ก็ทำได้)
}

# บทบาทที่ต้อง "สแกนก่อน" ถึงจะเปลี่ยนสเตปได้ (เปลี่ยนตรงผ่าน UI ไม่ได้)
SCAN_ONLY_ROLES = {SALES, TECH, VENDOR, CARWASH, PRODUCTION}

# สิทธิ์เต็ม (ทำได้ทุกอย่าง = ผู้บริหาร) — ฝ่ายทะเบียน + QC + อู่สีใน ยกระดับมาเท่าผู้บริหาร
FULL_ROLES = {EXEC, REGIST, QC, PAINTIN}


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


# ===== ความสามารถ ===== (FULL_ROLES = ผู้บริหาร+ฝ่ายทะเบียน ทำได้ทุกอย่าง)
def is_exec(user):        return get_role(user) in FULL_ROLES
def can_manage_users(user): return get_role(user) in (FULL_ROLES | {ADMIN})
def can_add_car(user):    return get_role(user) in (FULL_ROLES | {PURCHASING})
def can_edit_car(user):   return get_role(user) in (FULL_ROLES | {PURCHASING, ADMIN})
def can_delete_car(user): return get_role(user) in FULL_ROLES
def can_view_admin(user): return get_role(user) in (FULL_ROLES | {PURCHASING, ADMIN})
def is_worker(user):      return get_role(user) in SCAN_ONLY_ROLES


def allowed_stages(user):
    """รายชื่อคีย์สเตปที่ user เปลี่ยนได้"""
    role = get_role(user)
    if role in FULL_ROLES:
        return list(STAGE_ROLES.keys())
    return [s for s, rs in STAGE_ROLES.items() if role in rs]


def can_set_stage(user, stage):
    return get_role(user) in FULL_ROLES or (get_role(user) in STAGE_ROLES.get(stage, set()))


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
