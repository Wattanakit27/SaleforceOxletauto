"""
ระบบสิทธิ์ 10 บทบาท (1 user = 1 บทบาท ผ่าน Django Group)
  Executive    ผู้บริหาร   - ทำได้ทุกอย่าง (superuser = Executive เสมอ)
  Purchasing   จัดซื้อ     - เพิ่ม/แก้รถ, รับเข้า (ไม่ต้องสแกน)
  Admin        แอดมิน      - แก้ข้อมูลรถ + จัดการ user (เพิ่มรถ/เปลี่ยนสเตปไม่ได้)
  Sales        เซลล์       - งานขาย + ส่งกลับ QC + ตรวจรถรอปล่อย + ปล่อยรถ ผ่านการสแกน
  Technician   ช่าง        - ซ่อมเสร็จรอตรวจ/อะไหล่/เบาะ/ฟิล์ม ผ่านการสแกน (เช็คซ่อม = โปรดักชันเป็นคนใส่)
  (อู่นอก ยุบเข้า Registration แล้ว — งานอู่สีนอก/เบาะ ฝ่ายทะเบียนดูแล · เจ้าของเดิม Tech/Production ยังทำได้)
  Registration ฝ่ายทะเบียน - FULL_ROLES (ทำได้ทุกสเตป + จัดการรถ/ผู้ใช้)
  CarWash      ฝ่ายล้างรถ  - ล้างเสร็จ → "รอ QC ตรวจ" + ติ๊ก "รอเซลล์ตรวจ" แทน QC ไปก่อน (ยังไม่มีคน QC)
  Production   โปรดักชัน   - รถรอถ่ายรูป + ส่งต่อไป ซ่อม/ล้าง + ขึ้นหน้าร้าน + ถ่ายคอนเทนต์ (แทรกทุกสเตป)
  QC           QC          - 4 ปุ่มตรวจ: ตีกลับฝ่ายทะเบียน/รอตรวจเซลล์/แก้ไขรอตรวจขึ้นโชว์/แก้ไขรอตรวจรอปล่อย
  PaintIn      อู่สีใน     - อู่สีใน · FULL_ROLES (ตามที่ตั้ง)

แนวคิด: บทบาททำงาน (Sales/Tech/CarWash/Production) เปลี่ยนสเตปได้ทาง "การสแกน" เท่านั้น
        Executive/Purchasing/Registration/PaintIn เปลี่ยนตรงผ่าน UI ได้ (FULL_ROLES · QC ก็เปลี่ยนตรงได้แต่มีแค่ 4 ปุ่ม)
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
VENDOR = "Vendor"          # ยุบเข้า Registration แล้ว (คงค่าคงที่กัน ref เก่า · ไม่อยู่ใน ROLES)
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
    (REGIST, "ฝ่ายทะเบียน"),
    (CARWASH, "ฝ่ายล้างรถ"),
    (PRODUCTION, "โปรดักชัน"),
    (QC, "QC"),
    (PAINTIN, "อู่สีใน"),
]
ROLE_LABEL = dict(ROLES)

# สเตป -> เซตบทบาทที่ "กดเปลี่ยนเข้าสเตปนั้น" ได้ (STAGE_FULL_ROLES = Exec/PaintIn ได้ทุกสเตป · ยกเว้น intake)
# ★ ปรับใหญ่ ส.ค.69 (ตามเจ้าของสั่ง):
#   - "รับเข้า" เอาออกทุกบทบาท (รถถูกสร้างที่สเตปรับเข้าอยู่แล้ว ไม่มีใครต้องกดเข้า)
#   - โปรดักชัน: เอา "ชงล้าง" ออก · ช่าง: เอา "ติดฟิล์ม" ออก
#   - ฝ่ายทะเบียน: ไม่ full สเตปแล้ว — ได้ทุกสเตปยกเว้น งานเบาะ/อะไหล่ (ดู REGIST_EXCLUDE)
#   - "รอปิดการขาย" เหลือฝ่ายทะเบียน (+สิทธิ์เต็ม) เท่านั้น
#   - เซลล์: ตัดรอปิดการขาย → ได้ "ตรวจขนส่ง" แทน + "ขายแล้ว" (จบจริง) + ปุ่ม qc_show ใช้ป้าย "ตีกลับ QC"
STAGE_ROLES = {
    "intake":      set(),                # ★ ไม่มีใครกดเข้า "รับเข้า" ได้ (ทุกบทบาทรวมสิทธิ์เต็ม — ดู NO_ONE_STAGES)
    "photo_wait":  {PRODUCTION},
    "repair":      {PRODUCTION},         # เช็คซ่อม = โปรดักชันเป็นคนใส่ (ส่งรถเข้าสายซ่อม)
    "repair_done": {TECH},               # ช่างซ่อมเสร็จ → กดส่ง "ซ่อมเสร็จรอตรวจ"
    "parts":       {TECH},
    "upholstery":  {TECH},
    "paint_in":    set(),                # อู่สีใน = PAINTIN (FULL) เท่านั้น
    "paint_out":   set(),                # อู่สีนอก = สถานะ (อู่ภายนอก) · ฝ่ายทะเบียนเป็นคนปล่อย/รับกลับ
    "paint_check": {QC},                 # ★ QC "ตีกลับฝ่ายทะเบียน" (งานสี/สภาพยังไม่เรียบร้อย)
    "film":        set(),                # ★ เอาออกจากช่างแล้ว — เหลือฝ่ายทะเบียน/สิทธิ์เต็ม
    "wash":        set(),                # ★ เอาออกจากโปรดักชันแล้ว — เหลือฝ่ายทะเบียน/สิทธิ์เต็ม
    "wash_release": {SALES},             # ★ ส.ค.69 — เซลล์สั่ง "ล้างรถรอปล่อย" (ล้างรอบสองก่อนส่งมอบ/รอขาย)
    "qc_show":     {CARWASH, SALES, QC}, # ล้างเสร็จ → ฝ่ายล้างส่ง QC · เซลล์ "ตีกลับ QC" · QC "แก้ไขรอตรวจขึ้นโชว์"
    "sales_check": {QC},                 # QC ตรวจผ่านแล้ว "ติ๊ก" ส่งต่อให้เซลล์มาตรวจรับ ("รอตรวจเซลล์")
                                         # ★ ส.ค.69 เอา CARWASH ออก — มีคน QC จริงแล้ว ฝ่ายล้างไม่ต้องติ๊กแทน
    "show":        {SALES, PRODUCTION},  # เซลล์ตรวจรับแล้วดันขึ้นหน้าร้าน (โปรดักชันถ่ายรูปเสร็จก็ดันได้)
    "reserve":     {SALES},
    "finance":     {SALES},
    "transport_check": {SALES},          # ★ เซลล์พารถตรวจขนส่ง (แทนรอปิดการขายของเซลล์)
    "closing":     set(),                # ★ รอปิดการขาย = ฝ่ายทะเบียน (+สิทธิ์เต็ม) เท่านั้น
    "qc_release":  {SALES, CARWASH, QC}, # บังคับแนบรูป · ฝ่ายล้าง "ล้างเสร็จรถรอปล่อย" · QC "แก้ไขรอตรวจรอปล่อย"
    "release":     {SALES},              # ปล่อยรถ = เซลล์เก็บรูปส่งมอบ (ไม่จบ · รถยังอยู่บนบอร์ด) · บังคับแนบรูป
    "sold":        set(),                # ★ ขายแล้ว = จบจริง → ฝ่ายทะเบียน (+สิทธิ์เต็ม) เป็นคนกด
                                         #   (ส.ค.69 เอาออกจากเซลล์ตามที่เจ้าของสั่ง)
}

# สเตปที่ "ไม่มีใครกดเข้าได้" แม้สิทธิ์เต็ม (รับเข้า = จุดเกิดของรถตอนสร้าง ไม่ใช่ปุ่ม)
NO_ONE_STAGES = {"intake"}
# ฝ่ายทะเบียน: ทุกสเตปยกเว้นชุดนี้ (เจ้าของสั่งเอา เบาะ/อะไหล่ ออก · intake โดน NO_ONE_STAGES อยู่แล้ว)
REGIST_EXCLUDE = {"upholstery", "parts"}
# (เลิกใช้ QC_EXCLUDE แล้ว ส.ค.69 — QC ระบุปุ่มตรงๆ ใน STAGE_ROLES แทนการ "ให้หมดแล้วตัดออก")

# ป้ายปุ่มพิเศษต่อบทบาท — key สเตปเดิม แต่คำบนปุ่มเปลี่ยนตามบริบทผู้กด
# (สเตปเดียวกันแต่ "ความหมายของการกด" ต่างกันตามคนกด → เขียนคำให้ตรงกับงานที่เขาทำจริง)
STAGE_BUTTON_LABELS = {
    SALES: {
        "qc_show": "ตีกลับ QC",          # เซลล์เจอปัญหา → ตีรถกลับเข้าคิว "รอ QC ตรวจ"
        "wash_release": "ล้างรถรอปล่อย",  # ★ ส.ค.69 เซลล์สั่งล้างรอบสองก่อนส่งมอบ
    },
    CARWASH: {
        "qc_show": "รอตรวจ QC",           # ล้างเสร็จ (รอบแรก) → ส่ง QC ตรวจ
        "qc_release": "ล้างเสร็จรถรอปล่อย",  # ★ ล้างรอบสองเสร็จ → เด้งไปหน้าเซลล์ให้ทำงานต่อ
    },
    QC: {                                 # ★ ส.ค.69 — คำบนปุ่มของ QC (เพิ่มจากปุ่มเดิม ไม่ได้ตัดของเดิมออก)
        "paint_check": "ตีกลับฝ่ายทะเบียน",   # งานสี/สภาพยังไม่เรียบร้อย → ส่งกลับให้ฝ่ายทะเบียนทำต่อ
        "sales_check": "รอตรวจเซลล์",
        "qc_show":     "แก้ไขรอตรวจขึ้นโชว์",
        "qc_release":  "แก้ไขรอตรวจรอปล่อย",
    },
}

# ★ ส.ค.69 — ความด่วน: ฝ่ายล้างรถเห็นสถานะแต่ตั้งเองไม่ได้ (บทบาทอื่นตั้งได้ตามเดิม)
READONLY_PRIORITY_ROLES = {CARWASH}

# ★ ส.ค.69 รอบ 5 (เจ้าของสั่ง) — ธงงานค้าง "แยกสิทธิ์รายช่อง" ไม่ใช่สิทธิ์เดียวคุมทั้ง 3
#   ใครไม่อยู่ในลิสต์ของช่องนั้น = เห็นสถานะได้ แต่ติ๊กไม่ได้
#   เหตุผล: คนที่ "รู้จริง" ว่างานนั้นค้างอยู่ไหม คือคนที่ทำงานนั้นเอง (กันคนอื่นติ๊กมั่ว)
FLAG_EDIT_ROLES = {
    "need_photo":   {PRODUCTION},          # ทีมคอนเทนต์ (โปรดักชัน — เจ้าของสเตป "รถรอถ่ายรูป")
    "need_content": {PRODUCTION},          # ทีมคอนเทนต์
    "need_tire":    {TECH, REGIST},        # ช่าง + ฝ่ายทะเบียน
}
# ผู้บริหาร/แอดมินระบบ (superuser → get_role คืน EXEC) ติ๊กได้ทุกช่องเสมอ — กันล็อกตัวเองออก
FLAG_ALWAYS_ROLES = {EXEC}


def can_set_priority(user, stage=None) -> bool:
    """ตั้ง "ความด่วน" ได้ไหม
    - บทบาท: ทุกบทบาท ยกเว้น READONLY_PRIORITY_ROLES (ฝ่ายล้างรถ = ดูอย่างเดียว)
    - สเตป: ★ ส.ค.69 โชว์เฉพาะช่วงที่ "มีคิวให้แย่ง" (รับเข้า+ทำสภาพ) · ช่วงขาย/ปล่อยซ่อน
      (ส่ง stage=None = เช็คเฉพาะบทบาท เช่นตอนทำ UI รวมที่ยังไม่รู้ว่ารถคันไหน)"""
    from . import constants as _C
    if stage is not None and stage not in _C.PRIORITY_STAGES:
        return False
    return get_role(user) not in READONLY_PRIORITY_ROLES


def can_set_flag(user, flag_key) -> bool:
    """ติ๊ก "ธงงานค้าง" ช่องนั้นได้ไหม — ดูตาม FLAG_EDIT_ROLES รายช่อง"""
    role = get_role(user)
    return role in FLAG_ALWAYS_ROLES or role in FLAG_EDIT_ROLES.get(flag_key, set())


def flag_perms(user) -> dict:
    """{flag_key: ติ๊กได้ไหม} — ส่งให้หน้าเว็บไปปิด/เปิด checkbox รายช่อง"""
    from . import constants as _C
    return {k: can_set_flag(user, k) for k in _C.FLAG_KEYS}


def stage_button_label(role, stage_key, default_name):
    """ชื่อปุ่มสเตปตามบทบาทผู้กด — ไม่มี override = ชื่อสเตปปกติ"""
    return STAGE_BUTTON_LABELS.get(role, {}).get(stage_key, default_name)

# บทบาทที่ต้อง "สแกนก่อน" ถึงจะเปลี่ยนสเตปได้ (เปลี่ยนตรงผ่าน UI ไม่ได้)
SCAN_ONLY_ROLES = {SALES, TECH, CARWASH, PRODUCTION}

# สิทธิ์เต็ม "การจัดการ" (จัดการรถ/ผู้ใช้ ฯลฯ) — ฝ่ายทะเบียนยังจัดการได้เต็ม
FULL_ROLES = {EXEC, REGIST, QC, PAINTIN}
# สิทธิ์เต็ม "สเตป" (กดได้ทุกสเตป ยกเว้น NO_ONE_STAGES) — ★ ส.ค.69 ฝ่ายทะเบียนไม่ full สเตปแล้ว (ดู REGIST_EXCLUDE)
# ★ ส.ค.69 รอบ 7 (เจ้าของสั่ง) — QC ออกจากกลุ่มสิทธิ์เต็มสเตปแล้ว
#   เดิม QC ได้ทุกสเตปแล้วค่อยตัดฝั่งขายออก (QC_EXCLUDE) → ยังเหลือ 13 ปุ่ม รกเกินงานจริง
#   ตอนนี้ระบุตรงๆ ว่า QC มี 4 ปุ่ม (ดู STAGE_ROLES) = งานตรวจของ QC ล้วน
STAGE_FULL_ROLES = {EXEC, PAINTIN}


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
def can_add_car(user):    return get_role(user) in {EXEC, ADMIN, PURCHASING}   # ★ ส.ค.69 เจ้าของสั่ง: เพิ่มรถ = แอดมิน+จัดซื้อ (+ผู้บริหาร/superuser) เท่านั้น
def can_edit_car(user):   return get_role(user) in (FULL_ROLES | {PURCHASING, ADMIN})


# ★ ส.ค.69 — เซลล์แก้ข้อมูลรถได้เฉพาะ "รถพร้อมขาย" กับ "รถที่ปล่อย/ขายแล้ว" (เจ้าของสั่ง)
SALES_EDIT_STAGES = {"show", "release", "sold"}


def can_edit_this_car(user, car):
    """สิทธิ์แก้ข้อมูลรถ "รายคัน" — ใช้แทน can_edit_car ตรงที่รู้ว่ารถคันไหน"""
    if can_edit_car(user):
        return True
    return get_role(user) == SALES and car.stage in SALES_EDIT_STAGES
def can_delete_car(user): return get_role(user) in FULL_ROLES
def can_view_admin(user): return get_role(user) in (FULL_ROLES | {PURCHASING, ADMIN})
def is_worker(user):      return get_role(user) in SCAN_ONLY_ROLES


def _stage_exclude(role):
    """สเตปที่บทบาทนี้ถูกตัดออก แม้จะอยู่ในกลุ่มสิทธิ์เต็ม — คืน set() ถ้าไม่มีข้อยกเว้น"""
    if role == REGIST:
        return REGIST_EXCLUDE          # ฝ่ายทะเบียน: เว้น เบาะ/อะไหล่
    return set()


def allowed_stages(user):
    """รายชื่อคีย์สเตปที่ user เปลี่ยนได้ (intake ไม่มีใครกดได้ · ทะเบียนเว้นเบาะ/อะไหล่ · QC ระบุ 4 ปุ่มตรงๆ ใน STAGE_ROLES)"""
    role = get_role(user)
    skip = _stage_exclude(role)
    if role in STAGE_FULL_ROLES or role == REGIST:
        return [s for s in STAGE_ROLES if s not in NO_ONE_STAGES and s not in skip]
    return [s for s, rs in STAGE_ROLES.items() if role in rs]


def can_set_stage(user, stage):
    if stage in NO_ONE_STAGES:
        return False
    role = get_role(user)
    if role in STAGE_FULL_ROLES or role == REGIST:
        return stage not in _stage_exclude(role)
    return role in STAGE_ROLES.get(stage, set())


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
