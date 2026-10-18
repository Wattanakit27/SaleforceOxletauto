# -*- coding: utf-8 -*-
"""แผนก + ตำแหน่ง ในทะเบียนพนักงาน — ★ 18 ต.ค.69 (เจ้าของสั่ง)

*"ยังมีสถานะในระบบอีกอยู่ไม่ใช่หรอ QC อะไรต่างๆ ที่เป็นสถานะรถ เราจะใช้เป็นสถานะในโปรไฟล์นั้นเลย
ซึ่งต้องแก้ภายในเว็บด้วย เราจะมีแผนก แล้วก็ตำแหน่ง แผนกจะเป็นเซลล์ ตำแหน่งจะเป็นเซลล์ทีม A, เซลล์ทีม B"*

เจ้าของเคาะ (AskUserQuestion 18 ต.ค.69): ใช้ 11 แผนกตามตาราง · **สิทธิ์กดสเตปรถตามแผนกอัตโนมัติ**

  แผนก (`Employee.department`) = ตัวกำหนด **บทบาทในแอป** + **สิทธิ์ระบบรถ** (Django Group ของบัญชี LINE ที่ผูกไว้)
  ตำแหน่ง (`Employee.position`) = รายละเอียดใต้แผนก (ทีม A / แอดมิน บ้านเก่า / เด็กฝึกงาน) — **ค่าเดิมไม่ถูกเขียนทับ**
    (ตำแหน่งยังเป็นตัวกำหนดทีมขาย `team_id_of` · กลุ่มในตารางเช็คชื่อ · เวร Connect เหมือนเดิม)

กติกาความปลอดภัยที่ต้องรักษา:
- **แผนกที่ระบบเดาให้ (`department_auto=True`) ไม่ไปเปลี่ยนสิทธิ์ระบบรถของใคร** — migration เดาจาก
  บทบาทระบบรถเดิม/ตำแหน่ง ถ้าเอาค่าเดาไปตั้งสิทธิ์ทันที = แจกสิทธิ์กดสเตปรถให้คนที่ไม่เคยมีโดยไม่มีใครอนุมัติ
  (ช่องโหว่เดียวกับที่ปิดไป ส.ค.69 — เคยแจก Sales ให้ทุกคนที่ login ครั้งแรก) → ต้องมีคนกดยืนยัน/เลือกแผนกเองก่อน
- **แผนกไม่ยกสิทธิ์ "แอดมินฝั่งขาย"** (ดูข้อมูลลูกค้า/ยอดขายทั้งหมด) — ยังตั้งที่ "จัดการแอดมิน" ที่เดิม
  แผนกผู้บริหาร/แอดมินได้แท็บแอดมินในแอปเฉพาะคนที่ login มาเป็นแอดมินอยู่แล้ว · คนอื่นในแผนกนี้ได้แท็บคนงาน
  (ดูรถ/แก้ข้อมูลรถตามสิทธิ์ระบบรถ) — ไม่งั้นแอปโชว์แท็บแอดมินแต่เซิร์ฟเวอร์ปฏิเสธทุกคำขอ
- **superuser ไม่ถูกแตะ** (ผู้บริหารเสมอ · กันแอดมินระบบล็อกตัวเองออก)
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# (คีย์, ชื่อแผนก) — เรียงตามที่เจ้าของเคาะ · คีย์อังกฤษเก็บใน DB (ชื่อไทยแก้ได้โดยไม่ต้อง migrate)
DEPARTMENTS = [
    ("exec", "ผู้บริหาร"),
    ("admin", "แอดมิน"),
    ("telesale", "เทเลเซลล์"),
    ("sales", "เซลล์"),
    ("purchasing", "จัดซื้อ"),
    ("registration", "ฝ่ายทะเบียน"),
    ("qc", "QC"),
    ("technician", "ช่าง"),
    ("carwash", "ล้างรถ"),
    ("paint", "อู่สี"),
    ("production", "โปรดักชัน"),
]
LABEL = dict(DEPARTMENTS)
KEYS = [k for k, _ in DEPARTMENTS]

# แผนก → บทบาทระบบรถ (ชื่อ Group ใน cars/roles.py — เขียนเป็นสตริงตรงๆ ไม่ import cars ตอนโหลดโมดูล)
TRACK_ROLE = {
    "exec": "Executive",
    "admin": "Admin",
    "telesale": "Sales",
    "sales": "Sales",
    "purchasing": "Purchasing",
    "registration": "Registration",
    "qc": "QC",
    "technician": "Technician",
    "carwash": "CarWash",
    "paint": "PaintIn",
    "production": "Production",
}

# แผนก → บทบาทในแอป (admin · seller · buyer · worker) — admin เฉพาะคนที่ login เป็นแอดมินอยู่แล้ว (ดูหัวไฟล์)
APP_ROLE = {
    "exec": "admin", "admin": "admin",
    "telesale": "seller", "sales": "seller",
    "purchasing": "buyer",
    "registration": "worker", "qc": "worker", "technician": "worker",
    "carwash": "worker", "paint": "worker", "production": "worker",
}
APP_LABEL = {"admin": "แอดมิน", "seller": "เซลล์", "buyer": "จัดซื้อ", "worker": "คนงาน"}

# ตัวอย่างตำแหน่งใต้แผนก (หน้าพนักงานใช้เป็นตัวเลือกแนะนำ — พิมพ์อย่างอื่นได้)
#   เซลล์ใช้ "ทีม A" (ไม่ใช่ "เซลล์ทีม A") ให้ตรงกับกลุ่มในตารางเช็คชื่อที่มีอยู่ · "เซลล์ทีม A" ก็ใช้ได้ (team_id_of รับ)
POSITION_HINTS = {
    "exec": ["ผู้บริหาร"],
    "admin": ["ออฟฟิศ บ้านเก่า", "ออฟฟิศ อ่อนนุช"],
    "telesale": ["เทเลเซลล์"],
    "sales": ["ทีม A", "ทีม B", "ทีม C"],
    "purchasing": ["จัดซื้อ"],
    "registration": ["ออฟฟิศ บ้านเก่า", "ฝ่ายทะเบียน"],
    "qc": ["ช่างและคนงาน", "QC"],
    "technician": ["ช่างและคนงาน"],
    "carwash": ["ช่างและคนงาน"],
    "paint": ["อู่สีใน"],
    "production": ["ทีมโปรดักชัน", "เด็กฝึกงาน"],
}


# ─────────────────────────────────────────────────────────────
#  เดาแผนก (ใช้ใน migration ครั้งแรก + ปุ่ม "เดาให้") — บทบาทระบบรถเดิมชนะตำแหน่ง
# ─────────────────────────────────────────────────────────────
GROUP_DEPT = {v: k for k, v in TRACK_ROLE.items() if k not in ("telesale",)}   # Sales → sales
GROUP_ORDER = ["Executive", "Purchasing", "Admin", "Sales", "Technician", "Registration",
               "CarWash", "Production", "QC", "PaintIn"]     # ลำดับเดียวกับ cars.roles.ROLES


def _is_tele(pos: str) -> bool:
    low = (pos or "").strip().lower()
    return low == "admin" or any(k in low for k in ("เทเลเซล", "telesale"))


def _team_like(pos: str) -> bool:
    try:
        from dashboard.services.constants import team_id_of
        t = team_id_of(pos)
    except Exception:
        t = ""
    return bool(t) and t != "ADMIN"


def guess(position: str = "", groups=()) -> str:
    """แผนกที่น่าจะใช่ — "" = เดาไม่ได้ (ออฟฟิศที่ไม่มีบทบาทระบบรถ มีหลายแผนกปนกัน ไม่เดา)"""
    pos = (position or "").strip()
    low = pos.lower()
    gs = set(groups or ())
    for g in GROUP_ORDER:
        if g in gs:
            d = GROUP_DEPT.get(g, "")
            if d == "sales" and _is_tele(pos):
                return "telesale"
            return d
    if not pos:
        return ""
    if _is_tele(pos):
        return "telesale"
    if _team_like(pos) or "เซลล์" in pos:
        return "sales"
    if "จัดซื้อ" in pos:
        return "purchasing"
    if "โปรดักชัน" in pos or "production" in low or "ฝึกงาน" in pos:
        return "production"
    if "qc" in low:
        return "qc"
    if "ล้างรถ" in pos:
        return "carwash"
    if "อู่สี" in pos or "พ่นสี" in pos:
        return "paint"
    if "ทะเบียน" in pos:
        return "registration"
    if "ช่าง" in pos:
        return "technician"
    if "ผู้บริหาร" in pos or low in ("executive", "manager", "exec"):
        return "exec"
    if "แอดมิน" in pos:
        return "admin"
    return ""


# ─────────────────────────────────────────────────────────────
#  บัญชี Django ของพนักงาน (ผ่าน LINE ที่ผูกไว้ · ชื่อบัญชี line_<userId> จาก bridge)
# ─────────────────────────────────────────────────────────────
def _usernames(emp) -> list:
    try:
        ids = list(emp.line_accounts.values_list("user_id", flat=True))
    except Exception:
        return []
    return ["line_" + u for u in ids if u]


def linked_users(emp):
    from django.contrib.auth.models import User
    names = _usernames(emp)
    return list(User.objects.filter(username__in=names)) if names else []


def track_roles_map(emps) -> dict:
    """{employee.pk: [ชื่อบทบาทระบบรถของบัญชีที่ผูก (ไม่ซ้ำ)]} — ใช้โชว์ในหน้าพนักงาน (query ไม่กี่ครั้ง)"""
    from django.contrib.auth.models import User
    from checkout.models import LineProfile
    out: dict = {}
    pairs = list(LineProfile.objects.filter(employee__in=emps).exclude(user_id="")
                 .values_list("employee_id", "user_id"))
    names = {"line_" + u: eid for eid, u in pairs}
    if not names:
        return out
    for u in User.objects.filter(username__in=list(names)).prefetch_related("groups"):
        eid = names.get(u.username)
        gs = ["Executive"] if u.is_superuser else [g.name for g in u.groups.all()]
        lst = out.setdefault(eid, [])
        for g in gs:
            if g not in lst:
                lst.append(g)
    return out


def sync_track_role(emp) -> list:
    """ตั้งบทบาทระบบรถของบัญชีที่ผูกกับคนนี้ตามแผนก — **เฉพาะแผนกที่คนยืนยันแล้ว**
    คืน [(ชื่อบัญชี, บทบาทเดิม, บทบาทใหม่)] ที่เปลี่ยนจริง · superuser ไม่แตะ"""
    dept = (getattr(emp, "department", "") or "").strip()
    if not dept or getattr(emp, "department_auto", False):
        return []
    want = TRACK_ROLE.get(dept)
    if not want:
        return []
    from cars import roles as R
    changed = []
    for u in linked_users(emp):
        if u.is_superuser:
            continue
        cur = R.get_role(u)
        if cur != want:
            R.set_user_role(u, want)
            changed.append((u.username, cur or "", want))
    if changed:
        try:
            from dashboard.services import eventlog
            eventlog.log("dept", name="sync_track_role", target=emp.nickname, ok=True,
                         department=dept, changes=[[a, b, c] for a, b, c in changed])
        except Exception:
            pass
    return changed


def employee_of_line(line_user_id: str):
    if not line_user_id:
        return None
    try:
        from checkout.models import LineProfile
        p = LineProfile.objects.select_related("employee").filter(user_id=line_user_id).first()
        return p.employee if p and p.employee_id else None
    except Exception:
        return None


def track_role_for_line(line_user_id: str) -> str:
    """บทบาทระบบรถที่บัญชี LINE นี้ "ต้องเป็น" ตามแผนกที่ยืนยันแล้ว — "" = ไม่บังคับ (ใช้บทบาทที่ตั้งไว้เดิม)"""
    e = employee_of_line(line_user_id)
    if not e or not e.active or e.department_auto:
        return ""
    return TRACK_ROLE.get(e.department or "", "")


def dept_for_username(username: str):
    """(แผนก, ชื่อเล่น) ของบัญชี Django line_<id> ที่ "ล็อกสิทธิ์ตามแผนก" อยู่ — ไม่มี = None"""
    if not str(username or "").startswith("line_"):
        return None
    e = employee_of_line(username[5:])
    if not e or e.department_auto or not e.department:
        return None
    return e.department, e.nickname


# ─────────────────────────────────────────────────────────────
#  แผนกของคนที่ login อยู่ (แอป/หน้าเว็บ) → บทบาทในแอป
# ─────────────────────────────────────────────────────────────
def employee_of_user(user: dict):
    """พนักงานในทะเบียนของ session ที่ login (LINE id ก่อน แล้วค่อยชื่อเล่น)"""
    if not isinstance(user, dict):
        return None
    e = employee_of_line(str(user.get("user_id") or ""))
    if e:
        return e
    nick = str(user.get("nickname") or user.get("seller_name") or "").strip()
    if not nick:
        return None
    try:
        from checkout.models import Employee
        return Employee.objects.filter(nickname=nick).first()
    except Exception:
        return None


def app_role_of(user: dict, session_admin: bool = False) -> str:
    """บทบาทในแอปตามแผนก — "" = ยังไม่ระบุแผนก (ให้ตัวเรียกใช้กติกาเดิม)
    แผนกผู้บริหาร/แอดมินแต่ไม่ได้ login เป็นแอดมินฝั่งขาย = คนงาน (ดูรถตามสิทธิ์ระบบรถ)"""
    e = employee_of_user(user)
    if not e or not e.department:
        return ""
    r = APP_ROLE.get(e.department, "")
    if r == "admin" and not session_admin:
        return "worker"
    return r


def options() -> list:
    """ตัวเลือกแผนกสำหรับหน้าเว็บ — ชื่อ · บทบาทในแอป · สิทธิ์ระบบรถ · ตำแหน่งแนะนำ"""
    try:
        from cars.roles import ROLE_LABEL
    except Exception:
        ROLE_LABEL = {}
    return [{"key": k, "label": lb, "app": APP_LABEL.get(APP_ROLE.get(k, ""), ""),
             "track": ROLE_LABEL.get(TRACK_ROLE.get(k, ""), TRACK_ROLE.get(k, "")),
             "hints": POSITION_HINTS.get(k, [])} for k, lb in DEPARTMENTS]
