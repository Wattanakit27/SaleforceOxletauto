"""
วิวระบบติดตามรถ: dashboard / kanban / รายการรถ / เพิ่ม-แก้-ลบ / สแกนเปลี่ยนสเตป / QR
"""
import io
import json

import qrcode
import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

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
    all_cars = list(Car.objects.filter(deleted_at__isnull=True))
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


def _media_urls(lst, photo_name=None):
    """สร้าง public URL ของไฟล์แนบ (รูป/วิดีโอ) จาก path ที่เก็บไว้ใน Supabase"""
    base = (getattr(settings, "SUPABASE_URL", "") or "").rstrip("/")
    bucket = getattr(settings, "SUPABASE_STORAGE_BUCKET", "") or "car-photos"
    out = []
    if photo_name:  # back-compat: รูปเดี่ยวแบบเดิม
        out.append({"url": f"{base}/storage/v1/object/public/{bucket}/{photo_name}", "video": False})
    for m in (lst or []):
        p = m.get("path") if isinstance(m, dict) else m
        if p:
            out.append({"url": f"{base}/storage/v1/object/public/{bucket}/{p}",
                        "video": bool(isinstance(m, dict) and m.get("video"))})
    return out


def _fetch_logs(car, limit):
    """คืน (list ของ log objects, has_media) — fallback ถ้าคอลัมน์ media ยังไม่ถูก migrate (ช่วง deploy)"""
    try:
        return list(car.logs.all()[:limit]), True
    except Exception:
        return list(car.logs.all()[:limit].defer("media")), False


@login_required
def car_json(request, code):
    """รายละเอียดรถ (สำหรับ popup ในหน้าเดียว) — ฟิลด์ + ประวัติสแกน + สเตปที่เปลี่ยนได้."""
    car = get_object_or_404(Car, code=code)
    _log_objs, _hm = _fetch_logs(car, 50)
    logs = [{
        "stage": l.stage_name, "worker": l.worker_name,
        "note": l.note, "at": timezone.localtime(l.created_at).strftime("%d/%m/%y %H:%M"),
        "media": _media_urls(l.media if _hm else None, l.photo.name if l.photo else None),
    } for l in _log_objs]
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
        "canDelete": roles.can_manage_users(request.user),  # ลบ = แอดมินเท่านั้น (Exec/Admin)
        # ข้อมูลนำเข้า (ราคา/เจ้าของ/รายละเอียดเครื่องยนต์ ฯลฯ) — เก็บครบใน extra
        "price": (car.extra or {}).get("price"),
        "owner": (car.extra or {}).get("owner") or {},
        "detail": (car.extra or {}).get("detail") or {},
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
        car.deleted_at = timezone.now()   # soft delete → ถังขยะ (เก็บข้อมูลไว้)
        car.save(update_fields=["deleted_at"])
        messages.success(request, f"ย้ายรถ {car.code} เข้าถังขยะแล้ว")
        return redirect("track_dashboard")
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
    _log_objs, _hm = _fetch_logs(car, 20)
    logs = [{
        "stageKey": l.stage, "stageName": l.stage_name, "stageIcon": l.stage_icon,
        "at": timezone.localtime(l.created_at).strftime("%d/%m %H:%M"),
        "worker": l.worker_name, "note": l.note,
        "media": _media_urls(l.media if _hm else None, l.photo.name if l.photo else None),
    } for l in _log_objs]
    return render(request, "scan.html", {
        "car": car, "stages": stages, "logs": logs, "actor": _actor(request.user),
        "supabaseUrl": (getattr(settings, "SUPABASE_URL", "") or "").rstrip("/"),
        "storageBucket": getattr(settings, "SUPABASE_STORAGE_BUCKET", "") or "car-photos",
    })


@login_required
@require_POST
def api_sign_upload(request):
    """ขอ signed upload URL จาก Supabase (เซิร์ฟเวอร์เซ็นด้วย service_role) → เบราว์เซอร์อัปไฟล์ตรง
    (ข้ามลิมิต body 4.5MB ของ Vercel · รองรับวิดีโอ/รูปใหญ่)."""
    key = (getattr(settings, "SUPABASE_SECRET_KEY", "") or "").strip()
    base = (getattr(settings, "SUPABASE_URL", "") or "").rstrip("/")
    bucket = getattr(settings, "SUPABASE_STORAGE_BUCKET", "") or "car-photos"
    if not (key and base):
        return JsonResponse({"ok": False, "error": "ยังไม่ได้ตั้งค่า storage บนเซิร์ฟเวอร์"}, status=400)
    import re as _re
    import uuid as _uuid
    d = json.loads(request.body or "{}")
    fn = (d.get("filename") or "file")
    safe = _re.sub(r"[^A-Za-z0-9._-]", "_", fn)[-50:]
    path = f"scans/{timezone.now():%Y/%m}/{_uuid.uuid4().hex[:8]}-{safe}"
    try:
        r = requests.post(f"{base}/storage/v1/object/upload/sign/{bucket}/{path}",
                          headers={"apikey": key, "Authorization": f"Bearer {key}"}, timeout=15)
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)[:120]}, status=502)
    if r.status_code not in (200, 201):
        return JsonResponse({"ok": False, "error": f"sign fail {r.status_code}: {r.text[:120]}"}, status=400)
    signed = (r.json() or {}).get("url", "")
    upload_url = base + ("/storage/v1" + signed if signed.startswith("/object") else signed)
    return JsonResponse({"ok": True, "uploadUrl": upload_url, "path": path,
                         "isVideo": bool((d.get("contentType") or "").startswith("video"))})


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
    # ไฟล์แนบถูกอัปตรงเข้า Supabase แล้ว — รับมาเป็น path list (JSON)
    try:
        media = json.loads(request.POST.get("media") or "[]")
    except (ValueError, TypeError):
        media = []
    log, should_notify = car.change_stage(new_stage=stage, worker_name=actor, note=note)
    if media:
        try:  # กันช่วง deploy ที่คอลัมน์ media ยังไม่ migrate — เปลี่ยนสเตปต้องไม่ 500
            log.media = media
            log.save(update_fields=["media"])
        except Exception:
            pass
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


# =========================================================
#  JSON API — สำหรับเรนเดอร์ "สถานะรถ" ในหน้า sales (native, ไม่ใช้ iframe)
# =========================================================
def _to_int(s):
    if s in (None, ""):
        return None
    try:
        import re as _re
        return int(_re.sub(r"[^\d]", "", str(s)) or 0) or None
    except (ValueError, TypeError):
        return None


def _parse_dateonly(s):
    """'YYYY-MM-DD' (จาก <input type=date>) -> date | None"""
    from datetime import datetime as _dt
    try:
        return _dt.strptime((s or "").strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


@login_required
def cars_api(request):
    """ข้อมูล dashboard ติดตามรถ (counts + รายการรถ) เป็น JSON → sales เรนเดอร์เองด้วยธีมเดียวกัน."""
    all_cars = list(Car.objects.filter(deleted_at__isnull=True))
    flags = {"red": 0, "amber": 0, "ok": 0}
    counts = {k: 0 for k in C.STAGE_KEYS}
    for c in all_cars:
        flags[c.flag] += 1
        counts[c.stage] = counts.get(c.stage, 0) + 1
    phase_rows = [
        {"name": pn, "stages": [
            {"key": k, "name": C.STAGE_NAME[k], "icon": C.STAGE_ICON[k], "n": counts.get(k, 0)}
            for k in keys
        ]} for _, pn, keys in C.PHASES
    ]
    t2ls = [c.t2l for c in all_cars if c.t2l is not None]
    avg = round(sum(t2ls) / len(t2ls), 1) if t2ls else None
    # build public photo URL ตรงจาก Supabase (ไม่ต้องพึ่ง storage backend config บน prod)
    _base = (getattr(settings, "SUPABASE_URL", "") or "").rstrip("/")
    _bucket = getattr(settings, "SUPABASE_STORAGE_BUCKET", "") or "car-photos"
    cars = []
    for c in all_cars:
        ex = c.extra or {}
        det = ex.get("detail") or {}
        photo = f"{_base}/storage/v1/object/public/{_bucket}/{c.photo.name}" if (c.photo and _base) else ""
        cars.append({
            "code": c.code, "title": c.title, "name": ex.get("name") or c.title,
            "plate": c.plate, "branch": c.branch_name, "brand": c.brand, "model": c.model,
            "stage": c.stage, "stageName": c.stage_name, "stageIcon": c.stage_icon,
            "flag": c.flag, "days": c.days_in_stage, "price": ex.get("price"),
            "note": c.note, "photo": photo,
            "taxNote": det.get("วันที่ต่อภาษีรถยนต์", ""),
            "province": (ex.get("owner") or {}).get("จังหวัด", ""),
            # สำหรับเรียง: ราคา/ปี/ไมล์/วันรับเข้า/วันแก้ไขล่าสุด
            "priceNum": ex.get("price_num") or 0,
            "year": c.year or 0, "km": c.km or 0,
            "dateInTs": c.date_in.timestamp() if c.date_in else 0,
            "updatedTs": c.updated_at.timestamp() if c.updated_at else 0,
        })
    return JsonResponse({
        "total": len(all_cars), "flags": flags, "phaseRows": phase_rows,
        "avgT2l": avg, "t2lTarget": C.T2L_TARGET_DAYS,
        "branches": branch_pairs(), "stages": [[k, n] for k, n, _ in C.STAGES], "cars": cars,
        "statusChoices": list(C.STATUS_CHOICES), "bookChoices": list(C.BOOK_STATUS_CHOICES),
        # สเตปที่ user คนนี้ "เปลี่ยนได้" (Sales = qc/show/reserve/finance/closing/sold) → seller.html โชว์ปุ่มตามนี้
        "myStages": [[k, C.STAGE_NAME[k]] for k in roles.allowed_stages(request.user)],
        "canAdd": roles.can_add_car(request.user),
        "canManageUsers": roles.can_manage_users(request.user),
        "canViewAdmin": roles.can_view_admin(request.user),
        "canDelete": roles.can_manage_users(request.user),
    }, json_dumps_params={"ensure_ascii": False})


@login_required
@require_POST
def api_set_stage(request):
    """เปลี่ยนสเตปจากหน้า sales (POST JSON {code, stage}) — Exec/Purchasing เท่านั้น (direct)."""
    data = json.loads(request.body or "{}")
    car = get_object_or_404(Car, code=data.get("code"))
    stage = data.get("stage", "")
    if not roles.can_set_stage_direct(request.user, stage):
        return JsonResponse({"ok": False, "error": "ไม่มีสิทธิ์เปลี่ยนเป็นสเตปนี้ (บทบาททำงานต้องสแกน QR)"}, status=403)
    actor = _actor(request.user)
    _, should_notify = car.change_stage(new_stage=stage, worker_name=actor)
    if should_notify:
        notify_stage_change(car, worker_name=actor)
    return JsonResponse({"ok": True, "stageName": car.stage_name, "stageIcon": car.stage_icon,
                         "flag": car.flag, "days": car.days_in_stage})


@csrf_exempt
@login_required
@require_POST
def api_seller_set_stage(request):
    """เซลล์เปลี่ยนสเตปรถจากหน้าเซลล์ (seller.html · โหมด "สถานะรถ") — POST JSON {code, stage}.
    ★ ผ่อนกฎ scan-only ให้เซลล์ (ตามที่ตกลง): ใช้ can_set_stage (Sales เปลี่ยนสเตปที่ตัวเองมีสิทธิ์
    ได้ตรงๆ ไม่ต้องสแกน QR) ต่างจาก api_set_stage ที่ใช้ can_set_stage_direct (กัน scan-only).
    csrf_exempt + login_required (เหมือน endpoint ฝั่งเซลล์ตัวอื่น · seller.html ไม่มี CSRF token)."""
    data = json.loads(request.body or "{}")
    car = get_object_or_404(Car, code=data.get("code"))
    stage = data.get("stage", "")
    if not roles.can_set_stage(request.user, stage):
        return JsonResponse({"ok": False, "error": "ไม่มีสิทธิ์เปลี่ยนเป็นสเตปนี้"}, status=403)
    actor = _actor(request.user)
    _, should_notify = car.change_stage(new_stage=stage, worker_name=actor)
    if should_notify:
        notify_stage_change(car, worker_name=actor)
    return JsonResponse({"ok": True, "stageName": car.stage_name, "stageIcon": car.stage_icon,
                         "flag": car.flag, "days": car.days_in_stage})


@login_required
@require_POST
def api_add_car(request):
    """เพิ่มรถจากหน้า sales (POST JSON) — gen code อัตโนมัติ.
    รับฟิลด์ครบตาม DB: ทะเบียน/ยี่ห้อ/รุ่น/ปี/สี/ไมล์ + สเตปเริ่มต้น/สถานะ/สถานะเล่ม/
    วันรับเข้า/ครบกำหนดภาษี/หมายเหตุ + รูป 1 รูป (photo_path = path ที่อัปเข้า Supabase ผ่าน sign_upload)."""
    if not roles.can_add_car(request.user):
        return JsonResponse({"ok": False, "error": "ไม่มีสิทธิ์เพิ่มรถ"}, status=403)
    d = json.loads(request.body or "{}")

    # ฟิลด์ตัวเลือก — ค่านอกลิสต์ = ใช้ default (กันค่ามั่ว)
    status = d.get("status") if d.get("status") in dict(C.STATUS_CHOICES) else "active"
    book = d.get("book_status") if d.get("book_status") in dict(C.BOOK_STATUS_CHOICES) else ""
    stage = d.get("stage") if d.get("stage") in C.STAGE_KEYS else C.STAGE_KEYS[0]

    car = Car(
        branch=(d.get("branch") or C.DEFAULT_BRANCH),
        plate=(d.get("plate") or "")[:20], brand=(d.get("brand") or "")[:40],
        model=(d.get("model") or "")[:60], color=(d.get("color") or "")[:30],
        year=_to_int(d.get("year")), km=_to_int(d.get("km")),
        status=status, book_status=book, stage=stage,
        tax_due_date=_parse_dateonly(d.get("tax_due_date")),
        note=(d.get("note") or "")[:5000],
    )
    # วันรับเข้า (ระบุเองได้ · ว่าง = วันนี้ตาม default ของโมเดล)
    di = _parse_dateonly(d.get("date_in"))
    if di:
        from datetime import datetime as _dt, time as _time
        car.date_in = timezone.make_aware(_dt.combine(di, _time(12, 0)))
    # สเตปเริ่มต้น: ตั้งนาฬิกาค้างสเตป + จัดการ frontline/sold ให้เหมือน change_stage
    car.stage_since = timezone.now()
    if stage == C.FRONTLINE_STAGE:
        car.frontline_at = timezone.now()
    if stage == "sold":
        car.status = "sold"
    # รูปรถ — เก็บ path ที่อัปเข้า Supabase แล้ว (แสดงผลผ่าน car.photo.url / cars_api)
    photo_path = (d.get("photo_path") or "").strip()
    if photo_path:
        car.photo.name = photo_path
    car.save()
    return JsonResponse({"ok": True, "code": car.code})


@login_required
def api_users(request):
    """จัดการผู้ใช้/บทบาทระบบรถ จากเมนูจัดการของ sales (GET=list, POST=action) — Exec/Admin."""
    if not roles.can_manage_users(request.user):
        return JsonResponse({"ok": False, "error": "ต้องเป็น Executive/Admin"}, status=403)

    if request.method == "POST":
        d = json.loads(request.body or "{}")
        action = d.get("action", "")
        if action == "create":
            username = (d.get("username") or "").strip()
            password = d.get("password") or ""
            if not username or not password:
                return JsonResponse({"ok": False, "error": "ต้องกรอกชื่อผู้ใช้+รหัสผ่าน"}, status=400)
            if User.objects.filter(username__iexact=username).exists():
                return JsonResponse({"ok": False, "error": f"มีผู้ใช้ '{username}' แล้ว"}, status=400)
            u = User.objects.create_user(username=username, password=password)
            if d.get("full_name"):
                u.first_name = d["full_name"][:150]
                u.save(update_fields=["first_name"])
            if d.get("role"):
                roles.set_user_role(u, d["role"])
            return JsonResponse({"ok": True})
        if action == "set_role_line":
            # ตั้งบทบาทให้พนักงานจาก LINE id (ที่เก็บไว้แล้วในชีต) — สร้าง/ผูก Django user line_<id>
            lid = (d.get("line_id") or "").strip()
            if not lid:
                return JsonResponse({"ok": False, "error": "ไม่มี LINE id"}, status=400)
            lu, _ = User.objects.get_or_create(username=f"line_{lid}")
            if d.get("name") and not lu.first_name:
                lu.first_name = d["name"][:150]
                lu.save(update_fields=["first_name"])
            roles.set_user_role(lu, d.get("role") or "")
            return JsonResponse({"ok": True})
        u = User.objects.filter(pk=d.get("user_id")).first()
        if not u:
            return JsonResponse({"ok": False, "error": "ไม่พบผู้ใช้"}, status=404)
        if u.is_superuser:
            return JsonResponse({"ok": False, "error": "แก้ superuser ไม่ได้ (เป็นผู้บริหารเสมอ)"}, status=400)
        if action == "set_role":
            roles.set_user_role(u, d.get("role") or "")
        elif action == "toggle_active":
            u.is_active = not u.is_active
            u.save(update_fields=["is_active"])
        elif action == "reset_password":
            if not d.get("password"):
                return JsonResponse({"ok": False, "error": "ต้องระบุรหัสใหม่"}, status=400)
            u.set_password(d["password"])
            u.save(update_fields=["password"])
        return JsonResponse({"ok": True})

    # พนักงานจาก LINE (ใช้ LINE id ที่เก็บไว้แล้วในชีต employees → ตั้งบทบาท tracking ได้เลย)
    line_users = []
    try:
        from dashboard.services.google_sheets import fetch_sheet, cell, EMPLOYEE_COL as EM
        seen = set()
        for r in fetch_sheet("employees"):
            uid = (cell(r, EM.user_id) or "").strip()
            if not uid or uid in seen:
                continue
            seen.add(uid)
            du = User.objects.filter(username=f"line_{uid}").first()
            line_users.append({
                "lineId": uid,
                "name": (cell(r, EM.display_name) or cell(r, EM.nickname) or "").strip(),
                "nick": (cell(r, EM.nickname) or "").strip(),
                "role": roles.get_role(du) if du else None,
                "roleLabel": roles.role_label(du) if du else "ไม่มีบทบาท",
            })
    except Exception:
        line_users = []
    # บัญชีรหัสผ่าน (ช่าง/ฝ่ายทะเบียน/break-glass) — ไม่ใช่ line_*
    users = [{
        "id": u.pk, "username": u.username, "name": u.get_full_name(),
        "role": roles.get_role(u), "roleLabel": roles.role_label(u),
        "active": u.is_active, "isSuper": u.is_superuser,
    } for u in User.objects.exclude(username__startswith="line_").order_by("-is_active", "username")]
    # คำอธิบายบทบาท (สร้างจาก roles.py ให้ตรงเสมอ) — แต่ละบทบาทเปลี่ยนสเตปไหนได้ + ทำอะไรได้
    role_stages = {k: [] for k, _ in roles.ROLES}
    for st, rset in roles.STAGE_ROLES.items():
        for rk in rset:
            if rk in role_stages:
                role_stages[rk].append(C.STAGE_NAME.get(st, st))
    _caps = {
        roles.EXEC: "ทุกอย่าง — เปลี่ยนทุกสเตป + เพิ่ม/แก้/ลบรถ + จัดการบทบาท",
        roles.PURCHASING: "เพิ่ม/แก้รถ + เปลี่ยนสเตปตรงผ่านจอ (ไม่ต้องสแกน)",
        roles.ADMIN: "แก้ข้อมูลรถ + ลบรถ + จัดการบทบาท (ไม่เปลี่ยนสเตปงานช่าง)",
        roles.SALES: "สแกน QR เปลี่ยนสเตป (งานตรวจ/ขาย)",
        roles.TECH: "สแกน QR เปลี่ยนสเตป (งานช่าง)",
        roles.VENDOR: "สแกน QR เปลี่ยนสเตป (งานอู่นอก)",
        roles.REGIST: "ทำได้ทุกอย่าง (เท่าผู้บริหาร) — งานทะเบียน + ทุกสเตป + เพิ่ม/แก้/ลบรถ + จัดการบทบาท",
    }
    role_help = [{"label": lbl, "cap": _caps.get(k, ""),
                  "stages": [] if k in roles.FULL_ROLES else role_stages.get(k, []),
                  "scanOnly": k in roles.SCAN_ONLY_ROLES} for k, lbl in roles.ROLES]
    return JsonResponse({"ok": True, "lineUsers": line_users, "users": users,
                         "roles": [[k, v] for k, v in roles.ROLES], "roleHelp": role_help},
                        json_dumps_params={"ensure_ascii": False})


TRASH_DAYS = 30  # ถังขยะเก็บโชว์กี่วัน (พ้นแล้วซ่อน แต่ไม่ลบจริง — ข้อมูลยังอยู่)


@login_required
@require_POST
def api_delete_car(request):
    """ลบรถ = ย้ายเข้าถังขยะ (soft delete) — เก็บข้อมูลไว้ กู้คืนได้ใน 30 วัน · แอดมินเท่านั้น."""
    if not roles.can_manage_users(request.user):
        return JsonResponse({"ok": False, "error": "ลบรถได้เฉพาะแอดมิน"}, status=403)
    car = get_object_or_404(Car, code=json.loads(request.body or "{}").get("code"))
    car.deleted_at = timezone.now()
    car.save(update_fields=["deleted_at"])
    return JsonResponse({"ok": True})


@login_required
@require_POST
def api_restore_car(request):
    """กู้รถจากถังขยะกลับมาใช้งาน · แอดมินเท่านั้น."""
    if not roles.can_manage_users(request.user):
        return JsonResponse({"ok": False, "error": "กู้คืนได้เฉพาะแอดมิน"}, status=403)
    car = get_object_or_404(Car, code=json.loads(request.body or "{}").get("code"))
    car.deleted_at = None
    car.save(update_fields=["deleted_at"])
    return JsonResponse({"ok": True})


@login_required
def api_trash(request):
    """ถังขยะ — รถที่ลบภายใน 30 วัน (พ้น 30 วันซ่อน แต่ข้อมูลยังอยู่ใน DB)."""
    if not roles.can_view_admin(request.user):
        return JsonResponse({"ok": False, "error": "ไม่มีสิทธิ์"}, status=403)
    cutoff = timezone.now() - timezone.timedelta(days=TRASH_DAYS)
    qs = Car.objects.filter(deleted_at__isnull=False, deleted_at__gte=cutoff).order_by("-deleted_at")
    cars = []
    for c in qs:
        days_in = (timezone.now() - c.deleted_at).days
        cars.append({
            "code": c.code, "title": c.title, "plate": c.plate, "branch": c.branch_name,
            "stageName": c.stage_name, "deletedAt": timezone.localtime(c.deleted_at).strftime("%d/%m/%y %H:%M"),
            "daysLeft": max(0, TRASH_DAYS - days_in),
        })
    return JsonResponse({"ok": True, "cars": cars, "canRestore": roles.can_manage_users(request.user),
                         "trashDays": TRASH_DAYS}, json_dumps_params={"ensure_ascii": False})
