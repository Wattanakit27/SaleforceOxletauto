"""โปรไฟล์พนักงานในแอปมือถือ — ★ 21 ต.ค.69 เจ้าของสั่ง
*"ข้อมูลส่วนตัว ทั้งชื่อแล้วก็รูปดึงมาจาก Line ได้เลย ส่วนตำแหน่งหรืออื่นๆ เดี๋ยวให้ Admin มากรอก"*

- **ชื่อ + รูป = จาก LINE**
  · ตอน LINE Login ได้โปรไฟล์ที่ LINE ยืนยันแล้ว → `save_from_login()` เก็บรูปทันที
  · คนที่ login ไว้ก่อนแล้ว / บัญชีชื่อผู้ใช้+รหัส (คนงาน) → `refresh()` ถาม LINE ด้วยบัญชี LINE
    ที่ผูกกับคนนั้นในทะเบียน (Messaging API ตัวเดียวกับที่ดึงโปรไฟล์ลูกค้า) · ทุก 7 วัน · พลาด = เว้น 24 ชม.
- **แผนก / ตำแหน่ง / เวลาเข้างาน / วันหยุด = แอดมินกรอก** ในหน้า "พนักงาน" ของเว็บ — แอปแสดงอย่างเดียว
  ช่องที่ยังว่างส่งรายชื่อไปใน `missing` ให้แอปขึ้น "รอแอดมินกรอก"

★ ข้อยกเว้นของกติกา "ไม่เก็บรูปโปรไฟล์" (ก.ย.69 · ใช้กับ LineProfile ที่มีลูกค้าปน) —
  เก็บเฉพาะของ **พนักงาน** ที่ `Employee.picture_url` · เก็บแค่ลิงก์ ไม่โหลดไฟล์
⚠️ ห้ามส่ง LINE user id ออกไปกับโปรไฟล์ (กติกาเดิมทั้งโปรเจกต์)
"""
import threading
from datetime import timedelta

from django.utils import timezone

PIC_REFRESH_DAYS = 7      # ลิงก์รูปตายเมื่อเจ้าตัวเปลี่ยนรูป → ถามใหม่ทุกสัปดาห์
PIC_RETRY_HOURS = 24      # ถามไม่ได้ (ไม่ได้เพิ่มบอท/ไม่อยู่กลุ่มเดียวกับบอท) = เว้นวันนึงค่อยลองใหม่
BG = True                 # เทสต์ตั้ง False (ทำในที่ ไม่แตก thread)
_BUSY = set()
_LOCK = threading.Lock()

# ช่องที่แอดมินต้องกรอก (คีย์ในโปรไฟล์ → ชื่อที่คนอ่าน)
ADMIN_FIELDS = [("department", "แผนก"), ("position", "ตำแหน่ง"),
                ("workStart", "เวลาเข้างาน"), ("dayOff", "วันหยุด")]


def clean_url(u) -> str:
    """รับเฉพาะลิงก์ https (รูปโปรไฟล์ LINE อยู่บน profile.line-scdn.net) · ยาวเกิน = ทิ้ง"""
    u = str(u or "").strip()
    return u if u.startswith("https://") and len(u) <= 500 else ""


def due(emp, now=None) -> bool:
    """ถึงเวลาถาม LINE ใหม่หรือยัง — มีรูปแล้ว 7 วัน · ยังไม่มีรูป (ถามแล้วไม่ได้) 24 ชม."""
    if not emp.picture_at:
        return True
    age = (now or timezone.now()) - emp.picture_at
    return age > (timedelta(days=PIC_REFRESH_DAYS) if emp.picture_url else timedelta(hours=PIC_RETRY_HOURS))


def save_from_login(emp, display_name: str = "", picture: str = "") -> None:
    """LINE Login ส่งโปรไฟล์ที่ยืนยันแล้ว — เก็บรูปทันที (ไม่มีรูป = ล้างของเก่า)
    ชื่อ LINE เติมเฉพาะตอนทะเบียนยังว่าง — ช่องนี้ใช้เทียบชื่อคนในกลุ่ม แอดมินอาจแก้ไว้เอง ห้ามทับ"""
    if not emp:
        return
    from .models import Employee
    fields = {"picture_url": clean_url(picture), "picture_at": timezone.now()}
    name = str(display_name or "").strip()
    if name and not (emp.display_name or "").strip():
        fields["display_name"] = name[:120]
    Employee.objects.filter(pk=emp.pk).update(**fields)
    for k, v in fields.items():
        setattr(emp, k, v)


def refresh(emp) -> bool:
    """ถามรูปจาก LINE ด้วยบัญชี LINE ที่ผูกกับคนนี้ — ได้ = True
    คนในกลุ่มที่ไม่ได้เพิ่มบอทเป็นเพื่อน ต้องถามผ่านกลุ่ม → หากลุ่มล่าสุดที่เขาพิมพ์จากคลังแชท"""
    from . import people
    from .models import Employee, GroupChat, LineProfile
    now = timezone.now()
    data, got = {}, False
    for uid, ch in LineProfile.objects.filter(employee=emp).values_list("user_id", "channel")[:6]:
        gid = (GroupChat.objects.filter(sender_id=uid, chat_type=GroupChat.GROUP)
               .order_by("-sent_at").values_list("group_id", flat=True).first() or "")
        d = people.fetch_profile(user_id=uid, group_id=gid, channel=ch or "") or {}
        if d.get("displayName"):
            data, got = d, True
            if d.get("pictureUrl"):
                break
    if got:
        fields = {"picture_url": clean_url(data.get("pictureUrl")), "picture_at": now}
        name = str(data.get("displayName") or "").strip()
        if name and not (emp.display_name or "").strip():
            fields["display_name"] = name[:120]
    elif emp.picture_url:
        # ถามไม่ได้แต่มีรูปเดิม → ใช้ต่อ แล้วลองใหม่ในอีก 24 ชม. (ไม่ถามทุกครั้งที่เปิดแอป)
        fields = {"picture_at": now - timedelta(days=PIC_REFRESH_DAYS) + timedelta(hours=PIC_RETRY_HOURS)}
    else:
        fields = {"picture_at": now}
    Employee.objects.filter(pk=emp.pk).update(**fields)
    for k, v in fields.items():
        setattr(emp, k, v)
    return got


def refresh_bg(emp) -> None:
    """ถาม LINE ในเบื้องหลัง — แอปไม่ต้องรอ (ได้รูปรอบที่เปิดหน้าถัดไป) · คนเดียวกันไม่ถามซ้อน"""
    if not BG:
        try:
            refresh(emp)
        except Exception:
            pass
        return
    with _LOCK:
        if emp.pk in _BUSY:
            return
        _BUSY.add(emp.pk)

    def run():
        try:
            refresh(emp)
        except Exception:
            pass
        finally:
            with _LOCK:
                _BUSY.discard(emp.pk)
            try:
                from django.db import connection
                connection.close()
            except Exception:
                pass

    threading.Thread(target=run, daemon=True).start()


def employee_of(user: dict):
    try:
        from . import departments
        return departments.employee_of_user(user or {})
    except Exception:
        return None


def profile(user: dict, fetch: bool = True) -> dict:
    """โปรไฟล์ของคนที่ login (ของตัวเองเท่านั้น) — ชื่อ/รูปจาก LINE · ที่เหลือจากทะเบียนพนักงาน"""
    user = user or {}
    emp = employee_of(user)
    if emp and fetch and due(emp):
        refresh_bg(emp)
    nick = (user.get("nickname") or user.get("seller_name") or "").strip()
    out = {
        "registered": bool(emp),
        "nickname": (emp.nickname if emp else nick) or "",
        # ชื่อที่ตั้งใน LINE — จาก LINE Login ครั้งล่าสุดก่อน (สดสุด) แล้วค่อยทะเบียน
        "lineName": (user.get("line_name") or (emp.display_name if emp else "")
                     or user.get("display_name") or "").strip(),
        "picture": (emp.picture_url if emp and emp.picture_url else clean_url(user.get("picture"))),
        "department": "", "departmentName": "", "departmentAuto": False,
        "position": "", "workStart": "", "dayOff": "",
    }
    if emp:
        try:
            from .departments import LABEL
        except Exception:
            LABEL = {}
        out.update({
            "department": emp.department or "",
            "departmentName": LABEL.get(emp.department or "", "") if emp.department else "",
            "departmentAuto": bool(emp.department_auto and emp.department),
            "position": (emp.position or "").strip(),
            "workStart": (emp.work_start or "").strip(),
            "dayOff": (emp.day_off or "").strip(),
        })
    out["missing"] = [label for key, label in ADMIN_FIELDS if not out.get(key)]
    return out
