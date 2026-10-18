# -*- coding: utf-8 -*-
"""★ 18 ต.ค.69 — แผนก + ตำแหน่ง ในทะเบียนพนักงาน (เจ้าของสั่ง · checkout/departments.py)

เติม "แผนก" ให้คนที่มีอยู่แล้วแบบ **เดา** (`department_auto=True`) — ไม่ไปเปลี่ยนสิทธิ์ระบบรถของใคร
จนกว่าจะมีคนกดยืนยันในหน้าพนักงาน:
  1) บัญชี LINE ที่ผูกไว้มีบทบาทระบบรถอยู่แล้ว → แผนกตามบทบาทนั้น (แม่นสุด — แอดมินตั้งไว้เอง)
  2) ไม่มี → เดาจากตำแหน่ง (ทีม A → เซลล์ · จัดซื้อ · โปรดักชัน/เด็กฝึกงาน · ช่าง …)
  3) เดาไม่ได้ (เช่น "ออฟฟิศ บ้านเก่า" ที่ไม่มีบทบาทระบบรถ — มีหลายแผนกปนกัน) → ว่างไว้

ตรรกะเดาเขียนแช่ไว้ในไฟล์นี้ (ไม่ import departments.py) — migration ต้องให้ผลเดิมเสมอแม้โค้ดหลักเปลี่ยน
"""
import re

from django.db import migrations, models

GROUP_DEPT = {"Executive": "exec", "Admin": "admin", "Sales": "sales", "Purchasing": "purchasing",
              "Registration": "registration", "QC": "qc", "Technician": "technician", "CarWash": "carwash",
              "PaintIn": "paint", "Production": "production"}
GROUP_ORDER = ["Executive", "Purchasing", "Admin", "Sales", "Technician", "Registration",
               "CarWash", "Production", "QC", "PaintIn"]
_TEAM = re.compile(r"^(?:เซลล์\s*|เซล\s*|sales?\s*)?(?:ทีม|team)\s*([A-Za-z0-9]{1,2})$", re.I)


def _tele(pos):
    low = (pos or "").strip().lower()
    return low == "admin" or "เทเลเซล" in low or "telesale" in low


def _guess(pos, groups):
    pos = (pos or "").strip()
    low = pos.lower()
    for g in GROUP_ORDER:
        if g in groups:
            d = GROUP_DEPT[g]
            return "telesale" if d == "sales" and _tele(pos) else d
    if not pos:
        return ""
    if _tele(pos):
        return "telesale"
    if _TEAM.match(pos) or "เซลล์" in pos:
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


def fill(apps, schema_editor):
    Employee = apps.get_model("checkout", "Employee")
    LineProfile = apps.get_model("checkout", "LineProfile")
    User = apps.get_model("auth", "User")
    by_emp = {}
    for eid, uid in LineProfile.objects.exclude(employee=None).exclude(user_id="").values_list("employee_id", "user_id"):
        by_emp.setdefault(eid, []).append("line_" + uid)
    names = [n for lst in by_emp.values() for n in lst]
    groups_of = {}
    if names:
        for u in User.objects.filter(username__in=names).prefetch_related("groups"):
            gs = {"Executive"} if u.is_superuser else {g.name for g in u.groups.all()}
            groups_of[u.username] = gs
    for e in Employee.objects.all():
        if e.department:
            continue
        gs = set()
        for n in by_emp.get(e.pk, []):
            gs |= groups_of.get(n, set())
        d = _guess(e.position, gs)
        if d:
            Employee.objects.filter(pk=e.pk).update(department=d, department_auto=True)


class Migration(migrations.Migration):

    dependencies = [
        ("checkout", "0041_room_chat_auto_on"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.AddField(
            model_name="employee",
            name="department",
            field=models.CharField(blank=True, db_index=True, max_length=20, verbose_name="แผนก"),
        ),
        migrations.AddField(
            model_name="employee",
            name="department_auto",
            field=models.BooleanField(default=False, verbose_name="แผนกที่ระบบเดาให้ (ยังไม่มีคนยืนยัน)"),
        ),
        migrations.AlterField(
            model_name="employee",
            name="position",
            field=models.CharField(blank=True, max_length=80, verbose_name="ตำแหน่ง (ใต้แผนก · เช่น ทีม A)"),
        ),
        migrations.RunPython(fill, migrations.RunPython.noop),
    ]
