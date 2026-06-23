"""
วิวระบบติดตามรถ: dashboard / kanban / รายการรถ / เพิ่ม-แก้-ลบ / สแกนเปลี่ยนสเตป / QR
"""
import io

import qrcode
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from . import constants as C
from . import roles
from .forms import CarForm
from .line import notify_stage_change
from .models import Car, ScanLog, branch_pairs

SORT_MAP = {
    "updated": ("-updated_at",),
    "stuck": ("stage_since",),
    "newest": ("-date_in",),
    "code": ("code",),
}


def _actor(user):
    """ชื่อผู้ทำงานจาก user ที่ล็อกอิน"""
    return (user.get_full_name() or user.username) if user.is_authenticated else ""


def _stage_options(keys):
    """[(key, name, icon), ...] ตามลำดับสเตป — สำหรับปุ่มเปลี่ยนสเตป"""
    kset = set(keys)
    return [(k, n, i) for k, n, i in C.STAGES if k in kset]


# =========================================================
#  Dashboard / Kanban
# =========================================================
@login_required
def dashboard(request):
    """หน้าเดียวจบ: ตัวเลขสรุปต่อสเตป + ตารางรถทั้งหมด (มีตัวกรอง) · กดรถ = popup (car_json)."""
    all_cars = list(Car.objects.all())
    flags = {"red": 0, "amber": 0, "ok": 0}
    counts = {k: 0 for k in C.STAGE_KEYS}
    for c in all_cars:
        flags[c.flag] += 1
        counts[c.stage] = counts.get(c.stage, 0) + 1
    phase_rows = [
        {"name": pname, "stages": [
            {"key": k, "name": C.STAGE_NAME[k], "icon": C.STAGE_ICON[k], "n": counts.get(k, 0)}
            for k in keys
        ]}
        for _, pname, keys in C.PHASES
    ]
    t2ls = [c.t2l for c in all_cars if c.t2l is not None]
    avg_t2l = round(sum(t2ls) / len(t2ls), 1) if t2ls else None

    # ตารางรถ (รวม car_list เดิมมาไว้หน้าเดียว) — กรอง/เรียงใน Python จาก all_cars
    # (ดึง DB ครั้งเดียว ไม่ query ซ้ำ — ลด round-trip ข้ามภูมิภาคไป Supabase Sydney)
    branch = request.GET.get("branch", "")
    stage = request.GET.get("stage", "")
    sort = request.GET.get("sort", "updated")
    cars = all_cars
    if branch:
        cars = [c for c in cars if c.branch == branch]
    if stage:
        cars = [c for c in cars if c.stage == stage]
    if sort == "stuck":
        cars = sorted(cars, key=lambda c: c.stage_since)
    elif sort == "newest":
        cars = sorted(cars, key=lambda c: c.date_in, reverse=True)
    elif sort == "code":
        cars = sorted(cars, key=lambda c: c.code)
    else:  # updated (default)
        cars = sorted(cars, key=lambda c: c.updated_at, reverse=True)

    return render(request, "dashboard.html", {
        "total": len(all_cars), "flags": flags, "phase_rows": phase_rows,
        "avg_t2l": avg_t2l, "t2l_target": C.T2L_TARGET_DAYS,
        "cars": cars, "branch_choices": branch_pairs(), "stage_choices": C.STAGES,
        "cur_branch": branch, "cur_stage": stage, "cur_sort": sort,
        "add_form": CarForm(), "can_add": roles.can_add_car(request.user),
    })


@login_required
def car_json(request, code):
    """รายละเอียดรถ (สำหรับ popup ในหน้าเดียว) — ฟิลด์ + ประวัติสแกน + สเตปที่เปลี่ยนได้."""
    car = get_object_or_404(Car, code=code)
    logs = [{
        "stage": l.stage_name, "worker": l.worker_name,
        "note": l.note, "at": timezone.localtime(l.created_at).strftime("%d/%m/%y %H:%M"),
    } for l in car.logs.all()[:50]]
    # สเตปที่ "เปลี่ยนตรงผ่าน UI" ได้ (Exec/Purchasing) · บทบาททำงานเปลี่ยนผ่านสแกนเท่านั้น
    if roles.is_worker(request.user) or not roles.can_view_admin(request.user):
        direct = []
    else:
        direct = [{"key": k, "name": n} for k, n, _ in _stage_options(roles.allowed_stages(request.user))]
    return JsonResponse({
        "code": car.code, "title": car.title, "plate": car.plate,
        "brand": car.brand, "model": car.model, "year": car.year,
        "color": car.color, "km": car.km, "branch": car.branch_name,
        "stage": car.stage, "stageName": car.stage_name, "stageIcon": car.stage_icon,
        "status": car.get_status_display(),
        "bookStatus": car.get_book_status_display() if car.book_status else "",
        "taxDue": car.tax_due_date.strftime("%d/%m/%Y") if car.tax_due_date else "",
        "note": car.note,
        "dateIn": timezone.localtime(car.date_in).strftime("%d/%m/%Y") if car.date_in else "",
        "t2l": car.t2l, "daysInStage": car.days_in_stage, "flag": car.flag,
        "qrUrl": f"/track/qr/{car.code}.png",
        "photo": car.photo.url if car.photo else "",
        "scanUrl": f"/track/scan/{car.code}/",
        "editUrl": f"/track/cars/{car.code}/edit/",
        "logs": logs, "direct": direct, "canEdit": roles.can_edit_car(request.user),
    }, json_dumps_params={"ensure_ascii": False})


@login_required
def kanban(request):
    cars = list(Car.objects.exclude(status="sold"))
    columns = [
        {"key": k, "name": n, "icon": i, "cars": [c for c in cars if c.stage == k]}
        for k, n, i in C.STAGES
    ]
    return render(request, "kanban.html", {"columns": columns, "total": len(cars)})


# =========================================================
#  รายการรถ + CRUD
# =========================================================
@login_required
def car_list(request):
    branch = request.GET.get("branch", "")
    stage = request.GET.get("stage", "")
    sort = request.GET.get("sort", "updated")

    qs = Car.objects.all()
    if branch:
        qs = qs.filter(branch=branch)
    if stage:
        qs = qs.filter(stage=stage)
    qs = qs.order_by(*SORT_MAP.get(sort, ("-updated_at",)))

    cars = list(qs)
    return render(request, "car_list.html", {
        "cars": cars,
        "total": len(cars),
        "branch_choices": branch_pairs(),
        "stage_choices": C.STAGES,
        "cur_branch": branch,
        "cur_stage": stage,
        "cur_sort": sort,
    })


@login_required
def car_detail(request, code):
    car = get_object_or_404(Car, code=code)
    if roles.is_worker(request.user) or not roles.can_view_admin(request.user):
        # บทบาททำงาน: เปลี่ยนสเตปผ่านหน้าสแกนเท่านั้น
        direct_stages = []
    else:
        direct_stages = _stage_options(roles.allowed_stages(request.user))
    return render(request, "car_detail.html", {
        "car": car,
        "logs": car.logs.all()[:50],
        "direct_stages": direct_stages,
        "can_edit": roles.can_edit_car(request.user),
        "can_delete": roles.can_delete_car(request.user),
    })


@roles.role_required(roles.can_add_car)
def car_create(request):
    if request.method == "POST":
        form = CarForm(request.POST, request.FILES)
        if form.is_valid():
            car = form.save()
            messages.success(request, f"เพิ่มรถ {car.code} เรียบร้อย — อย่าลืมปริ้น QR แปะรถ")
            return redirect("track_dashboard")
    else:
        form = CarForm()
    return render(request, "car_form.html", {"form": form, "mode": "create"})


@roles.role_required(roles.can_edit_car)
def car_edit(request, code):
    car = get_object_or_404(Car, code=code)
    if request.method == "POST":
        form = CarForm(request.POST, request.FILES, instance=car)
        if form.is_valid():
            car = form.save()
            messages.success(request, f"บันทึกข้อมูลรถ {car.code} แล้ว")
            return redirect("track_dashboard")
    else:
        form = CarForm(instance=car)
    return render(request, "car_form.html", {"form": form, "mode": "edit", "car": car})


@roles.role_required(roles.can_delete_car)
def car_delete(request, code):
    car = get_object_or_404(Car, code=code)
    if request.method == "POST":
        deleted = car.code
        car.delete()
        messages.success(request, f"ลบรถ {deleted} แล้ว")
        return redirect("car_list")
    return render(request, "car_delete.html", {"car": car})


@login_required
def car_stage(request, code):
    """เปลี่ยนสเตปตรงจาก UI (Exec/Purchasing เท่านั้น) — POST"""
    car = get_object_or_404(Car, code=code)
    if request.method == "POST":
        new_stage = request.POST.get("stage", "")
        if not roles.can_set_stage_direct(request.user, new_stage):
            raise PermissionDenied("คุณไม่มีสิทธิ์เปลี่ยนเป็นสเตปนี้ (ลองผ่านหน้าสแกน)")
        actor = _actor(request.user)
        _, should_notify = car.change_stage(new_stage=new_stage, worker_name=actor)
        if should_notify:
            notify_stage_change(car, worker_name=actor)
        messages.success(request, f"{car.code} → {car.stage_name}")
    return redirect("track_dashboard")


# =========================================================
#  สแกน (มือถือ)
# =========================================================
@login_required
def scan_page(request, code):
    car = get_object_or_404(Car, code=code)
    stages = _stage_options(roles.allowed_stages(request.user))
    return render(request, "scan.html", {
        "car": car,
        "stages": stages,
        "logs": car.logs.all()[:20],
        "actor": _actor(request.user),
    })


@login_required
def scan_submit(request, code):
    car = get_object_or_404(Car, code=code)
    if request.method != "POST":
        return redirect("scan", code=code)
    stage = request.POST.get("stage", "")
    if not roles.can_set_stage(request.user, stage):
        raise PermissionDenied("บทบาทของคุณไม่มีสิทธิ์เปลี่ยนเป็นสเตปนี้")
    note = (request.POST.get("note") or "").strip()
    actor = _actor(request.user)
    photo = request.FILES.get("photo")
    _, should_notify = car.change_stage(new_stage=stage, worker_name=actor, note=note, photo=photo)
    if should_notify:
        notify_stage_change(car, worker_name=actor)
    messages.success(request, f"บันทึกงาน {car.code} แล้ว — สเตปปัจจุบัน: {car.stage_name}")
    return redirect("scan", code=code)


# =========================================================
#  QR
# =========================================================
@login_required
def qr_png(request, code):
    """รูป QR (PNG) ชี้ไปหน้า /scan/<code>/"""
    car = get_object_or_404(Car, code=code)
    img = qrcode.make(car.qr_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return HttpResponse(buf.getvalue(), content_type="image/png")


@roles.role_required(roles.can_view_admin)
def qr_print(request):
    """หน้าเลือกรถเพื่อพิมพ์ QR (ตัวกรองสาขา/สเตป)"""
    branch = request.GET.get("branch", "")
    stage = request.GET.get("stage", "")
    qs = Car.objects.all()
    if branch:
        qs = qs.filter(branch=branch)
    if stage:
        qs = qs.filter(stage=stage)
    return render(request, "qr_print.html", {
        "cars": list(qs.order_by("branch", "code")),
        "branch_choices": branch_pairs(),
        "stage_choices": C.STAGES,
        "cur_branch": branch, "cur_stage": stage,
    })


@roles.role_required(roles.can_view_admin)
def qr_print_sheet(request):
    """แผ่นพิมพ์ QR ของรถที่เลือก — รับ ?code=..&code=.."""
    codes = request.GET.getlist("code")
    cars = sorted(Car.objects.filter(code__in=codes), key=lambda c: c.code) if codes else []
    return render(request, "qr_sheet.html", {"cars": cars})


# =========================================================
#  จัดการผู้ใช้ / บทบาท (Executive + Admin)
# =========================================================
@roles.role_required(roles.can_manage_users)
def manage_users(request):
    """เพิ่ม/แก้ผู้ใช้ + กำหนด 1 ใน 7 บทบาท — แอดมินทำเองได้โดยไม่ต้องเข้า Django admin"""
    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "create":
            username = (request.POST.get("username") or "").strip()
            password = request.POST.get("password") or ""
            full_name = (request.POST.get("full_name") or "").strip()
            role_key = request.POST.get("role") or ""
            if not username or not password:
                messages.error(request, "ต้องกรอกชื่อผู้ใช้และรหัสผ่าน")
            elif User.objects.filter(username__iexact=username).exists():
                messages.error(request, f"มีผู้ใช้ '{username}' อยู่แล้ว")
            else:
                u = User.objects.create_user(username=username, password=password)
                if full_name:
                    u.first_name = full_name[:150]
                    u.save(update_fields=["first_name"])
                if role_key:
                    roles.set_user_role(u, role_key)
                messages.success(request, f"เพิ่มผู้ใช้ {username} ({roles.ROLE_LABEL.get(role_key, 'ไม่มีบทบาท')}) แล้ว")

        elif action == "set_role":
            u = User.objects.filter(pk=request.POST.get("user_id")).first()
            role_key = request.POST.get("role") or ""
            if not u:
                messages.error(request, "ไม่พบผู้ใช้")
            elif u.is_superuser:
                messages.error(request, "เปลี่ยนบทบาท superuser ไม่ได้ (เป็นผู้บริหารเสมอ)")
            else:
                roles.set_user_role(u, role_key)
                messages.success(request, f"ตั้ง {u.username} เป็น {roles.ROLE_LABEL.get(role_key, 'ไม่มีบทบาท')}")

        elif action == "toggle_active":
            u = User.objects.filter(pk=request.POST.get("user_id")).first()
            if u and u.is_superuser:
                messages.error(request, "ปิดใช้งาน superuser ไม่ได้")
            elif u:
                u.is_active = not u.is_active
                u.save(update_fields=["is_active"])
                messages.success(request, f"{'เปิด' if u.is_active else 'ปิด'}ใช้งาน {u.username} แล้ว")

        elif action == "reset_password":
            u = User.objects.filter(pk=request.POST.get("user_id")).first()
            password = request.POST.get("password") or ""
            if u and password:
                u.set_password(password)
                u.save(update_fields=["password"])
                messages.success(request, f"รีเซ็ตรหัสผ่าน {u.username} แล้ว")
            else:
                messages.error(request, "ต้องระบุรหัสผ่านใหม่")

        return redirect("manage_users")

    rows = [
        {"u": u, "role": roles.get_role(u), "role_label": roles.role_label(u)}
        for u in User.objects.order_by("-is_active", "username")
    ]
    return render(request, "manage_users.html", {"rows": rows, "roles": roles.ROLES})
