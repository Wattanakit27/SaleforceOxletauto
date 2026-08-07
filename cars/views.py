"""
วิวระบบติดตามรถ: dashboard / kanban / รายการรถ / เพิ่ม-แก้-ลบ / สแกนเปลี่ยนสเตป / QR
"""
import io
import json
import os
import re

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
from .models import Car, ScanLog, LoginEvent, branch_pairs

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
    # ★ แยก "ขายแล้ว" ออกจากตารางหลัก (เหมือนแท็บสถานะรถในแดชบอร์ดขาย) — default โชว์รถในระบบ
    #   ปล่อยรถ (release) = จบ → status=sold → หลุดจากบอร์ด/ตารางรถในระบบ
    def _is_sold(c):
        return c.status == "sold" or c.stage == "release"
    active_n = sum(1 for c in all_cars if not _is_sold(c))
    sold_n = len(all_cars) - active_n
    view = "sold" if request.GET.get("view", "active") == "sold" else "active"
    cars = [c for c in all_cars if (_is_sold(c) if view == "sold" else not _is_sold(c))]
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

    # ── บอร์ดสถานะรถ (คัมบัง) — คอลัมน์ตามสเตป · มาร์ค "สเตปของฉัน" ตามบทบาท ──
    #   ทุกบัญชี (ยกเว้นคนนอก = ไม่ login) เห็นบอร์ด · default โฟกัสสเตปตัวเอง สลับดูทั้งหมดได้
    #   full roles (ผู้บริหาร/ทะเบียน) = เห็นทุกสเตปปกติ ไม่มาร์ค/ไม่มีปุ่มสลับ (allowed = ทุกสเตปอยู่แล้ว)
    is_full = roles.is_exec(request.user)
    my_stages = set() if is_full else set(roles.allowed_stages(request.user))
    _board_by = {}
    for c in all_cars:
        if _is_sold(c):
            continue
        _board_by.setdefault(c.stage, []).append(c)
    board_cols = []
    for k, n, i in C.STAGES:
        if k == "release":       # ปล่อยรถ = จบ (status sold) → ไม่ต้องมีคอลัมน์บนบอร์ด
            continue
        lst = sorted(_board_by.get(k, []), key=lambda c: c.stage_since)  # ค้างนานสุดขึ้นก่อน
        board_cols.append({"key": k, "name": n, "icon": i, "mine": k in my_stages, "cars": lst})
    has_my = bool(my_stages)                        # มีสเตปตัวเอง → default โฟกัสงานตัวเอง + ปุ่มสลับ

    return render(request, "dashboard.html", {
        "total": len(all_cars), "flags": flags, "phase_rows": phase_rows,
        "avg_t2l": avg_t2l, "t2l_target": C.T2L_TARGET_DAYS,
        "cars": cars, "branch_choices": branch_pairs(), "stage_choices": C.STAGES,
        "cur_branch": branch, "cur_stage": stage, "cur_sort": sort,
        "cur_view": view, "active_n": active_n, "sold_n": sold_n,
        "board_cols": board_cols, "has_my": has_my, "is_full": is_full,
        # ปุ่ม "แดชบอร์ดขาย" โชว์เฉพาะแอดมินขาย (มาจาก /track/ ตรง) — คนงาน (position=worker) ซ่อน (อยู่ /dashboard/ แล้ว)
        "show_sales_link": (request.session.get("oxlet_user") or {}).get("position") == "admin",
        "add_form": CarForm(), "can_add": roles.can_add_car(request.user),
        # build public photo URL ตรงจาก Supabase (ไม่พึ่ง storage backend บน prod เหมือน cars_api)
        "supabaseUrl": (getattr(settings, "SUPABASE_URL", "") or "").rstrip("/"),
        "storageBucket": getattr(settings, "SUPABASE_STORAGE_BUCKET", "") or "car-photos",
    })


@roles.role_required(roles.can_manage_users)
def login_log(request):
    """หน้าดู log การเข้าสู่ระบบ (Executive/Admin) — ใครเข้า/พยายามเข้า เมื่อไหร่ สำเร็จไหม.
    ดึงจาก cars.LoginEvent (เขียนจากทุกจุด login ฝั่ง sales/tracking · best-effort)."""
    show = request.GET.get("show", "")          # ''=ทั้งหมด · 'ok'=สำเร็จ · 'fail'=ล้มเหลว
    qs = LoginEvent.objects.all()
    if show == "fail":
        qs = qs.filter(success=False)
    elif show == "ok":
        qs = qs.filter(success=True)
    events = list(qs[:300])
    now = timezone.localtime(timezone.now())
    start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today = LoginEvent.objects.filter(created_at__gte=start_today)
    rows = [{
        "at": timezone.localtime(e.created_at).strftime("%d/%m/%y %H:%M:%S"),
        "identity": e.identity, "name": e.name,
        "method": e.get_method_display() if e.method else "—",
        "success": e.success, "role": e.role, "ip": e.ip, "reason": e.reason,
        "ua": e.user_agent,
    } for e in events]
    return render(request, "login_log.html", {
        "rows": rows, "show": show,
        "today_ok": today.filter(success=True).count(),
        "today_fail": today.filter(success=False).count(),
        "uniq_today": today.filter(success=True).values("identity").distinct().count(),
        "total": LoginEvent.objects.count(),
    })


@roles.role_required(roles.can_manage_users)
def login_log_api(request):
    """JSON ของ log การเข้าสู่ระบบ — ให้หน้าแดชบอร์ด sales (index.html) เรนเดอร์เป็น modal เอง.
    (เข้าจาก /track/ → middleware bridge session sales → Django user · เหมือน api_users)."""
    show = request.GET.get("show", "")
    qs = LoginEvent.objects.all()
    if show == "fail":
        qs = qs.filter(success=False)
    elif show == "ok":
        qs = qs.filter(success=True)
    now = timezone.localtime(timezone.now())
    start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today = LoginEvent.objects.filter(created_at__gte=start_today)
    rows = [{
        "at": timezone.localtime(e.created_at).strftime("%d/%m %H:%M:%S"),
        "identity": e.identity, "name": e.name,
        "method": e.get_method_display() if e.method else "—",
        "success": e.success, "ip": e.ip, "reason": e.reason,
    } for e in list(qs[:200])]
    return JsonResponse({
        "ok": True, "rows": rows, "total": LoginEvent.objects.count(),
        "todayOk": today.filter(success=True).count(),
        "todayFail": today.filter(success=False).count(),
        "uniqToday": today.filter(success=True).values("identity").distinct().count(),
    }, json_dumps_params={"ensure_ascii": False})


def _media_urls(lst, photo_name=None):
    """สร้าง URL แสดงผลของไฟล์แนบ (รูป/วิดีโอ) จาก token ที่เก็บไว้:
    - Drive file id (ไม่มี "/") → Google Drive
    - path มี "/" → ดิสก์ VPS (/media/...) · หรือ Supabase (ถ้ายังตั้ง bucket — legacy)"""
    from . import gdrive

    def _u(token, video):
        if not token:
            return None
        if "/" in token:  # ไฟล์ที่เก็บเป็น path
            if getattr(settings, "SUPABASE_STORAGE_BUCKET", "") and getattr(settings, "SUPABASE_URL", ""):
                base = settings.SUPABASE_URL.rstrip("/")
                bucket = settings.SUPABASE_STORAGE_BUCKET
                return {"url": f"{base}/storage/v1/object/public/{bucket}/{token}", "video": video}
            # ดิสก์ VPS — nginx เสิร์ฟ /media/
            url = getattr(settings, "MEDIA_URL", "/media/").rstrip("/") + "/" + token.lstrip("/")
            return {"url": url, "video": video}
        url = gdrive.video_view_url(token) if video else gdrive.photo_url(token)
        return {"url": url, "video": video}

    out = []
    if photo_name:  # back-compat: รูปเดี่ยว (ImageField)
        u = _u(photo_name, False)
        if u:
            out.append(u)
    for m in (lst or []):
        if isinstance(m, dict):
            u = _u(m.get("id") or m.get("path"), bool(m.get("video")))
        else:
            u = _u(m, False)
        if u:
            out.append(u)
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
        "stage": l.stage_name, "stageKey": l.stage, "worker": l.worker_name,
        "note": l.note, "at": timezone.localtime(l.created_at).strftime("%d/%m/%y %H:%M"),
        "media": _media_urls(l.media if _hm else None, l.photo.name if l.photo else None),
    } for l in _log_objs]
    # สเตปที่ user เปลี่ยนได้ตามบทบาท — ผ่อนกฎ scan-only: กดเปลี่ยนจากบอร์ด/โมดัลได้เลย
    # (คนงานที่ไม่มีสเตป/ไม่มีบทบาท = [] → โชว์ลิงก์สแกน QR แทน)
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
        "priority": car.priority, "priorityColor": car.priority_color, "priorityName": car.priority_name,
        "needPhoto": car.need_photo, "needContent": car.need_content, "flags": car.flags,
        "qrUrl": f"/track/qr/{car.code}.png",
        "lastWorker": (logs[0]["worker"] if logs else ""),
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
    return render(request, "car_form.html", {"form": form, "mode": "edit", "car": car,
                                             "sale_photos": _sale_photos_ctx(car)})


def _resolve_sale_photo_url(pid):
    """id/path ของรูปขาย → URL แสดงผล (Drive id→thumbnail · disk path→/media/)"""
    pid = str(pid or "").strip()
    if not pid:
        return ""
    if "/" in pid:
        return settings.MEDIA_URL.rstrip("/") + "/" + pid.lstrip("/")
    try:
        from . import gdrive
        return gdrive.photo_url(pid)
    except Exception:
        return ""


def _sale_photos_ctx(car):
    """list ของ {id, url, cover} จาก car.extra['sale_photos'] (รูปแรก=ปก)
    ยังไม่มีแกลเลอรี แต่มีรูปเดิม (Car.photo) → เอามาโชว์เป็นรูปแรก (กันแกลเลอรีว่าง)"""
    ids = (car.extra or {}).get("sale_photos") if isinstance(car.extra, dict) else None
    ids = list(ids) if isinstance(ids, list) else []
    if not ids and car.photo and car.photo.name:
        ids = [car.photo.name]
    return [{"id": p, "url": _resolve_sale_photo_url(p), "cover": (i == 0)}
            for i, p in enumerate(ids) if p]


@csrf_exempt
@login_required
@require_POST
def api_car_photos(request, code):
    """จัดการรูปขายของรถ (extra['sale_photos']) — action: add / remove / cover · คืน list ใหม่ + sync โชว์รูม"""
    if not roles.can_edit_car(request.user):
        return JsonResponse({"ok": False, "error": "ไม่มีสิทธิ์"}, status=403)
    car = get_object_or_404(Car, code=code)
    d = json.loads(request.body or "{}")
    action = d.get("action")
    pid = str(d.get("id") or "").strip()
    extra = car.extra if isinstance(car.extra, dict) else {}
    photos = [str(p) for p in (extra.get("sale_photos") or []) if p]
    if not photos and car.photo and car.photo.name:   # seed จากรูปเดิม → action ต่อยอดได้
        photos = [car.photo.name]
    if action == "add" and pid:
        if pid not in photos:
            photos.append(pid)
    elif action == "remove" and pid:
        photos = [p for p in photos if p != pid]
    elif action == "cover" and pid and pid in photos:
        photos = [pid] + [p for p in photos if p != pid]
    else:
        return JsonResponse({"ok": False, "error": "action ไม่ถูกต้อง"}, status=400)
    extra["sale_photos"] = photos
    car.extra = extra
    if photos:
        car.photo.name = photos[0]
        car.save(update_fields=["extra", "photo"])
    else:
        car.save(update_fields=["extra"])
    return JsonResponse({"ok": True, "photos": _sale_photos_ctx(car)})


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


@csrf_exempt
@login_required
@require_POST
def api_sign_upload(request):
    """ขอ signed upload URL จาก Supabase (เซิร์ฟเวอร์เซ็นด้วย service_role) → เบราว์เซอร์อัปไฟล์ตรง
    (ข้ามลิมิต body 4.5MB ของ Vercel · รองรับวิดีโอ/รูปใหญ่).
    csrf_exempt: หน้าเซลล์ (seller.html · โหมดสถานะรถ) เรียกอัปรูปก่อน/หลังตอนเปลี่ยนสเตป
    ซึ่งไม่มี CSRF token — เหมือน endpoint ฝั่งเซลล์ตัวอื่น (login_required กันคนนอกอยู่แล้ว)."""
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


def _car_folder_name(car):
    """ชื่อโฟลเดอร์ Drive ของรถ: '<โค้ด> <ทะเบียน>(<ทะเบียนเดิม>)' เช่น 'CS0011 กก1414(4525)'"""
    name = f"{car.code} {car.plate}".strip()
    if car.plate_original:
        name += f"({car.plate_original})"
    return name


def _ensure_car_folder(car):
    """หา/สร้างโฟลเดอร์ Drive ของรถคันนี้ → คืน folder id (เก็บที่ car.drive_folder_id)
    มีอยู่แล้ว = rename ให้ตรงชื่อปัจจุบัน (กรณีแก้ทะเบียน) · คืน '' ถ้า Drive ยังไม่ตั้งค่า"""
    from . import gdrive
    if not gdrive.is_configured():
        return ""
    fid = gdrive.ensure_folder(
        _car_folder_name(car),
        parent_id=getattr(settings, "GDRIVE_ROOT_FOLDER_ID", ""),
        existing_id=car.drive_folder_id or "",
    )
    if fid and fid != car.drive_folder_id:
        car.drive_folder_id = fid
        car.save(update_fields=["drive_folder_id"])
    return fid


_THAI_MON = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
             "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]


def _safe_filename(s):
    """ตัดอักขระที่ทำชื่อไฟล์พังตอนโหลดลง Windows/มือถือ (\\ / : * ? \" < > | ขึ้นบรรทัดใหม่)"""
    s = re.sub(r'[\\/:*?"<>|\r\n\t]', "", s or "")
    return re.sub(r"\s+", " ", s).strip()


def _label_stage_media(log, car):
    """ตั้งชื่อไฟล์รูป/วิดีโอใน Drive ตาม 'สถานะ(ผู้เปลี่ยน) วันเวลา ลำดับ.นามสกุล'
    เช่น 'รับเข้า(หมี) 8ก.ค.69 14-30 1.jpg' — เฉพาะไฟล์บน Drive (id ไม่มี '/') · ไฟล์ดิสก์ข้าม.
    best-effort: ล้มเหลว = ไม่ทำให้การเปลี่ยนสเตปพัง (ชื่อไฟล์เป็นแค่ป้าย ไม่กระทบลิงก์แสดงผลที่อิง id)."""
    from . import gdrive
    if not gdrive.is_configured():
        return
    media = log.media if isinstance(log.media, list) else []
    if not media:
        return
    now = timezone.localtime(log.created_at) if log.created_at else timezone.localtime()
    stage = _safe_filename(car.stage_name) or "อัพเดท"
    worker = _safe_filename(log.worker_name) or "-"
    datestr = f"{now.day}{_THAI_MON[now.month - 1]}{(now.year + 543) % 100:02d} {now.hour:02d}-{now.minute:02d}"
    n = 0
    for m in media:
        if not isinstance(m, dict):
            continue
        fid = m.get("id") or ""
        if not fid or "/" in fid:   # "/" = path บนดิสก์ VPS → ข้าม (ฟีเจอร์นี้สำหรับ Drive)
            continue
        n += 1
        ext = os.path.splitext(gdrive.get_name(fid))[1]
        if not ext:
            ext = ".mp4" if m.get("video") else ".jpg"
        gdrive.rename(fid, f"{stage}({worker}) {datestr} {n}{ext}")


def _save_local_media(f, code=""):
    """เก็บไฟล์ลงดิสก์ VPS (MEDIA_ROOT) จัดโฟลเดอร์ media/cars/<code>/ → คืน relative name (มี "/")"""
    import re as _re
    import uuid as _uuid
    from django.core.files.storage import default_storage
    safe = _re.sub(r"[^A-Za-z0-9._-]", "_", f.name or "file")[-50:]
    sub = f"cars/{code}" if code else f"cars/_misc/{timezone.now():%Y/%m}"
    return default_storage.save(f"{sub}/{_uuid.uuid4().hex[:8]}-{safe}", f)


@csrf_exempt
@login_required
@require_POST
def api_upload(request):
    """อัปรูป/วิดีโอ (ฝั่งเซิร์ฟเวอร์) → คืน {ok, id, video, url}
    multipart: file=<ไฟล์> + code=<โค้ดรถ> (ออปชั่น) + target=<'disk'|''>.
    แยกที่เก็บตามประเภท:
    - **รูปหน้าปกรถ** (เพิ่มรถ · target='disk') → ดิสก์ VPS เสมอ (ไฟล์เล็ก ไม่ต้องพึ่งบริการนอก)
    - **รูปรายงาน/วิดีโอ** (สแกน/หน้าเซลล์ · ไม่ส่ง target) → Google Drive ถ้าตั้งไว้ (โชว์ลิงก์) · ยังไม่ตั้ง = ดิสก์ VPS (fallback)
    บน VPS ไม่มีลิมิต body 4.5MB แบบ Vercel (จำกัดด้วย GDRIVE_MAX_UPLOAD_MB · nginx 220M).
    csrf_exempt + login_required (เหมือน endpoint ฝั่งเซลล์ตัวอื่น · seller.html ไม่มี CSRF token)."""
    f = request.FILES.get("file")
    if not f:
        return JsonResponse({"ok": False, "error": "ไม่มีไฟล์"}, status=400)
    max_mb = getattr(settings, "GDRIVE_MAX_UPLOAD_MB", 200)
    if f.size and f.size > max_mb * 1024 * 1024:
        return JsonResponse({"ok": False, "error": f"ไฟล์ใหญ่เกิน {max_mb}MB"}, status=400)
    code = (request.POST.get("code") or "").strip()
    target = (request.POST.get("target") or "").strip()   # 'disk' = บังคับเก็บดิสก์ (รูปหน้าปก)
    is_video = (f.content_type or "").startswith("video")

    from . import gdrive
    if target != "disk" and gdrive.is_configured():
        # ── Google Drive (รูปรายงาน/วิดีโอ · โฟลเดอร์ต่อรถ) ──
        parent = ""
        if code:
            car = Car.objects.filter(code=code).first()
            if car:
                try:
                    parent = _ensure_car_folder(car)
                except Exception:
                    parent = ""  # สร้างโฟลเดอร์ไม่ได้ → อัปลง root แทน (ไม่ให้พังทั้งงาน)
        try:
            fid = gdrive.upload(f, f.name, content_type=f.content_type, size=f.size, parent_id=parent)
        except Exception as e:
            return JsonResponse({"ok": False, "error": str(e)[:160]}, status=502)
        url = gdrive.video_view_url(fid) if is_video else gdrive.photo_url(fid)
        return JsonResponse({"ok": True, "id": fid, "video": is_video, "url": url})

    # ── เก็บลงดิสก์ VPS (รูปหน้าปก target=disk · หรือ Drive ยังไม่ตั้ง = fallback) ──
    try:
        name = _save_local_media(f, code)
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)[:160]}, status=502)
    url = getattr(settings, "MEDIA_URL", "/media/").rstrip("/") + "/" + name.lstrip("/")
    return JsonResponse({"ok": True, "id": name, "video": is_video, "url": url})


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
        try:  # ตั้งชื่อไฟล์ตามสถานะ+ผู้เปลี่ยน+เวลา (best-effort · ไม่พังงานถ้า Drive ล่ม)
            _label_stage_media(log, car)
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

    # map LINE user_id → (ชื่อเล่น, displayname) จากชีต employees → โชว์ชื่อแทน line_<id> ดิบ
    emp_map = {}
    try:
        from dashboard.services.google_sheets import fetch_sheet, cell, EMPLOYEE_COL as EM
        for e in fetch_sheet("employees"):
            uid = (cell(e, EM.user_id) or "").strip()
            if uid:
                emp_map[uid] = ((cell(e, EM.nickname) or "").strip(), (cell(e, EM.display_name) or "").strip())
    except Exception:
        emp_map = {}

    def _label(u):
        if u.username.startswith("line_"):
            nick, disp = emp_map.get(u.username[5:], ("", ""))
            return nick or disp or (u.get_full_name() or "").strip() or u.username
        return (u.get_full_name() or "").strip() or u.username

    rows = [
        {"u": u, "role": roles.get_role(u), "role_label": roles.role_label(u),
         "label": _label(u), "is_line": u.username.startswith("line_")}
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
    cars = []
    for c in all_cars:
        ex = c.extra or {}
        det = ex.get("detail") or {}
        # ผ่าน _media_urls → รองรับทั้ง Drive id และ Supabase path (legacy) ตามชนิดที่เก็บ
        _pu = _media_urls(None, c.photo.name) if c.photo else []
        photo = _pu[0]["url"] if _pu else ""
        cars.append({
            "code": c.code, "title": c.title, "name": ex.get("name") or c.title,
            "plate": c.plate, "branch": c.branch_name, "brand": c.brand, "model": c.model,
            "stage": c.stage, "stageName": c.stage_name, "stageIcon": c.stage_icon,
            "status": c.status, "sold": (c.status == "sold" or c.stage == "release"),
            "flag": c.flag, "days": c.days_in_stage, "price": ex.get("price"),
            "priority": c.priority, "priorityColor": c.priority_color, "priorityName": c.priority_name,
            "needPhoto": c.need_photo, "needContent": c.need_content, "flags": c.flags,
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
        "me": _actor(request.user),
        "canAdd": roles.can_add_car(request.user),
        "canManageUsers": roles.can_manage_users(request.user),
        "canViewAdmin": roles.can_view_admin(request.user),
        "canDelete": roles.can_manage_users(request.user),
    }, json_dumps_params={"ensure_ascii": False})


@login_required
@require_POST
def api_set_stage(request):
    """เปลี่ยนสเตปจากบอร์ด/โมดัล (POST JSON {code, stage, note?}).
    ★ ผ่อนกฎ scan-only: ใช้ can_set_stage (บทบาทที่ "มีสิทธิ์สเตปนั้น" กดเปลี่ยนได้ตรงๆ จากบอร์ด
    ไม่ต้องสแกน QR) — คนงาน (ช่าง/ล้างรถ/โปรดักชัน/เซลล์) กดเปลี่ยนสเตปตัวเองจากบอร์ดได้เลย.
    สแกน QR หน้ารถ (scan_submit) ยังใช้ได้ตามเดิม."""
    data = json.loads(request.body or "{}")
    car = get_object_or_404(Car, code=data.get("code"))
    stage = data.get("stage", "")
    if not roles.can_set_stage(request.user, stage):
        return JsonResponse({"ok": False, "error": "ไม่มีสิทธิ์เปลี่ยนเป็นสเตปนี้ (บทบาทของคุณไม่ครอบสเตปนี้)"}, status=403)
    media = data.get("media")
    if not isinstance(media, list):
        media = []
    if stage in C.STAGE_FORCE_MEDIA and not media:   # ตรวจปล่อย/ปล่อยรถ = บังคับแนบรูป/วิดีโอ
        return JsonResponse({"ok": False, "error": "สเตปนี้ต้องแนบรูป/วิดีโอก่อนยืนยัน"}, status=400)
    note = (data.get("note") or "").strip()
    pr = data.get("priority")
    if pr in C.PRIORITY_NAME:                          # ปรับความด่วนพร้อมกัน (ถ้าส่งมา)
        car.priority = pr
        car.save(update_fields=["priority"])
    actor = _actor(request.user)
    log, should_notify = car.change_stage(new_stage=stage, worker_name=actor, note=note)
    if media:
        try:
            log.media = media
            log.save(update_fields=["media"])
        except Exception:
            pass
    if should_notify:
        notify_stage_change(car, worker_name=actor)
    return JsonResponse({"ok": True, "stageName": car.stage_name, "stageIcon": car.stage_icon,
                         "flag": car.flag, "days": car.days_in_stage,
                         "priority": car.priority, "priorityColor": car.priority_color})


@csrf_exempt
@login_required
@require_POST
def api_seller_set_stage(request):
    """เซลล์เปลี่ยนสเตปรถจากหน้าเซลล์ (seller.html · โหมด "สถานะรถ") — POST JSON {code, stage, note?, media?}.
    ★ ผ่อนกฎ scan-only ให้เซลล์ (ตามที่ตกลง): ใช้ can_set_stage (Sales เปลี่ยนสเตปที่ตัวเองมีสิทธิ์
    ได้ตรงๆ ไม่ต้องสแกน QR) ต่างจาก api_set_stage ที่ใช้ can_set_stage_direct (กัน scan-only).
    note = หมายเหตุ · media = list ของ path รูป/วิดีโอ (อัปตรงเข้า Supabase ผ่าน api_sign_upload แล้ว
    ส่ง path กลับมา — แนบเข้า ScanLog เหมือนหน้าสแกน) → เก็บรูป "ก่อน/หลัง" ตอนเปลี่ยนสเตป.
    csrf_exempt + login_required (เหมือน endpoint ฝั่งเซลล์ตัวอื่น · seller.html ไม่มี CSRF token)."""
    data = json.loads(request.body or "{}")
    car = get_object_or_404(Car, code=data.get("code"))
    stage = data.get("stage", "")
    if not roles.can_set_stage(request.user, stage):
        return JsonResponse({"ok": False, "error": "ไม่มีสิทธิ์เปลี่ยนเป็นสเตปนี้"}, status=403)
    note = (data.get("note") or "").strip()
    media = data.get("media")
    if not isinstance(media, list):
        media = []
    actor = _actor(request.user)
    log, should_notify = car.change_stage(new_stage=stage, worker_name=actor, note=note)
    if media:
        try:  # กันช่วง deploy ที่คอลัมน์ media ยังไม่ migrate — เปลี่ยนสเตปต้องไม่ 500
            log.media = media
            log.save(update_fields=["media"])
        except Exception:
            pass
        try:  # ตั้งชื่อไฟล์ตามสถานะ+ผู้เปลี่ยน+เวลา (best-effort · ไม่พังงานถ้า Drive ล่ม)
            _label_stage_media(log, car)
        except Exception:
            pass
    if should_notify:
        notify_stage_change(car, worker_name=actor)
    return JsonResponse({"ok": True, "stageName": car.stage_name, "stageIcon": car.stage_icon,
                         "flag": car.flag, "days": car.days_in_stage})


@csrf_exempt
@csrf_exempt
@login_required
@require_POST
def api_set_priority(request):
    """ตั้ง "ความด่วน" ของรถ (สีการ์ด) — POST JSON {code, priority}.
    ความด่วนเป็นการ "โฟกัส/จัดคิว" ไม่ใช่การเปลี่ยนสเตป → คนที่ล็อกอินติดตามรถทุกคนตั้งได้
    (บอร์ดถูก scope ตามบทบาทอยู่แล้ว) · csrf_exempt (บอร์ดในหน้า sales/seller ไม่มี CSRF token)."""
    data = json.loads(request.body or "{}")
    car = get_object_or_404(Car, code=data.get("code"))
    pr = data.get("priority")
    if pr not in C.PRIORITY_NAME:
        return JsonResponse({"ok": False, "error": "ความด่วนไม่ถูกต้อง"}, status=400)
    car.priority = pr
    car.save(update_fields=["priority"])
    return JsonResponse({"ok": True, "priority": car.priority,
                         "priorityColor": car.priority_color, "priorityName": car.priority_name})


@csrf_exempt
@login_required
@require_POST
def api_set_flags(request):
    """ติ๊ก/ปลด "ธงงานค้าง" ของรถ — POST JSON {code, need_photo?, need_content?} (ส่งมาเฉพาะตัวที่จะเปลี่ยน).
    ธงเป็นการ "หมายเหตุงานที่ยังค้าง" ไม่ใช่การเปลี่ยนสเตป → คนที่ล็อกอินติดตามรถทุกคนติ๊กได้
    (เหมือนความด่วน) · แยกจาก priority → ติดธงพร้อมบอกด่วน/ไม่ด่วนได้ · csrf_exempt (บอร์ดฝัง iframe)."""
    data = json.loads(request.body or "{}")
    car = get_object_or_404(Car, code=data.get("code"))
    changed = []
    for key in C.FLAG_KEYS:
        if key in data:
            setattr(car, key, bool(data[key]))
            changed.append(key)
    if changed:
        car.save(update_fields=changed)
    return JsonResponse({"ok": True, "needPhoto": car.need_photo,
                         "needContent": car.need_content, "flags": car.flags})


@csrf_exempt
@login_required
@require_POST
def api_content_shoot(request):
    """บันทึก "ถ่ายคอนเทนต์" ที่สเตปปัจจุบัน — POST JSON {code, note?, media?}.
    เป็น action แทรกได้ทุกสเตป (ไม่เปลี่ยนสเตป) → สร้าง ScanLog ที่สเตปเดิม + แนบรูป/วิดีโอ + โน้ต
    เก็บลงไทม์ไลน์รถ (โปรดักชันถ่ายคอนเทนต์ระหว่างทำสภาพ/ขาย). ไม่ push LINE."""
    data = json.loads(request.body or "{}")
    car = get_object_or_404(Car, code=data.get("code"))
    media = data.get("media")
    if not isinstance(media, list):
        media = []
    note = (data.get("note") or "").strip()
    note = ("ถ่ายคอนเทนต์ · " + note) if note else "ถ่ายคอนเทนต์"
    actor = _actor(request.user)
    log = ScanLog.objects.create(car=car, stage=car.stage, worker_name=actor, note=note)
    if car.need_content:          # ถ่ายคอนเทนต์แล้ว → ปลดธงให้เอง ไม่ต้องมากดออกซ้ำ
        car.need_content = False
        car.save(update_fields=["need_content"])
    if media:
        try:
            log.media = media
            log.save(update_fields=["media"])
        except Exception:
            pass
        try:
            _label_stage_media(log, car)
        except Exception:
            pass
    return JsonResponse({"ok": True, "stage": car.stage, "stageName": car.stage_name})


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
    if stage == "release":       # ปล่อยรถ = จบ → มาร์ค sold
        car.status = "sold"

    # รูปขาย — รับหลายรูป (id/path จาก api_upload) · รูปแรก = ปก · เก็บ list ใน extra['sale_photos']
    # ตั้งก่อน save → post_save ยิง webhook ครั้งเดียวพร้อมรูป → sync ไปโชว์รูม (ไม่ยิงซ้ำ/ไม่ race)
    photos = [str(p).strip() for p in (d.get("photos") or []) if p]
    single = (d.get("photo_id") or d.get("photo_path") or "").strip()
    if single and single not in photos:
        photos.insert(0, single)
    if photos:
        car.photo.name = photos[0]
        extra = car.extra if isinstance(car.extra, dict) else {}
        extra["sale_photos"] = photos
        car.extra = extra

    car.save()   # gen code + post_save → notify_showroom (พร้อม photos)

    # ย้ายรูป Drive เข้าโฟลเดอร์รถ (best-effort · หลังมี code แล้ว · disk ข้าม)
    drive_ids = [p for p in photos if p and "/" not in p]
    if drive_ids:
        try:
            from . import gdrive
            folder = _ensure_car_folder(car)
            if folder:
                for pid in drive_ids:
                    gdrive.move_to_folder(pid, folder)
        except Exception:
            pass
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
        roles.SALES: "สแกน QR เปลี่ยนสเตป (คนตรวจ qc + งานขาย + เด้งกลับตอนตรวจไม่ผ่าน)",
        roles.TECH: "สแกน QR เปลี่ยนสเตป (อะไหล่/เบาะ/ฟิล์ม) — เช็คซ่อมให้โปรดักชันเป็นคนใส่ (ช่างแค่ตรวจดู)",
        roles.REGIST: "ทำได้ทุกอย่าง (เท่าผู้บริหาร) — คนประเมิน/ตรวจ ชี้ทางแยกได้ทุกสเตป + เพิ่ม/แก้/ลบรถ + จัดการบทบาท",
        roles.CARWASH: "ล้างรถเสร็จ → กดส่ง 'รอตรวจรถขึ้นโชว์' (ชงล้าง = โปรดักชันเป็นคนใส่ · ฝ่ายล้างแค่ล้าง/ดู)",
        roles.PRODUCTION: "รถรอถ่ายรูป + ส่งต่อไปซ่อม/ล้าง + ถ่ายคอนเทนต์ (แทรกได้ทุกสเตป) — อู่สีนอกเป็นของฝ่ายทะเบียน",
        roles.QC: "ทำได้ทุกอย่าง (เท่าผู้บริหาร) — ตรวจรถขึ้นโชว์ + ตรวจรถรอปล่อย",
        roles.PAINTIN: "ทำได้ทุกอย่าง (เท่าผู้บริหาร) — งานอู่สีใน",
    }
    role_help = [{"label": lbl, "cap": _caps.get(k, ""),
                  "stages": [] if k in roles.FULL_ROLES else role_stages.get(k, []),
                  "scanOnly": k in roles.SCAN_ONLY_ROLES} for k, lbl in roles.ROLES]
    return JsonResponse({"ok": True, "lineUsers": line_users, "users": users,
                         "roles": [[k, v] for k, v in roles.ROLES], "roleHelp": role_help},
                        json_dumps_params={"ensure_ascii": False})


@login_required
def api_branches(request):
    """จัดการสาขา จากเมนู "สถานะรถ" ของ sales (GET=list, POST action=create/rename/toggle_active/delete) — Exec/Admin.
    code = prefix รหัสรถ (CB→CB-0011) → แก้ไม่ได้หลังสร้าง (จะทำให้รหัสรถเดิมกำพร้า) · แก้ได้แค่ชื่อ+เปิด/ปิด · ลบได้เมื่อไม่มีรถ"""
    from .models import Branch, _branch_name_cache
    if not roles.can_manage_users(request.user):
        return JsonResponse({"ok": False, "error": "ต้องเป็น Executive/Admin"}, status=403)
    if request.method == "POST":
        d = json.loads(request.body or "{}")
        action = d.get("action", "")
        if action == "create":
            code = (d.get("code") or "").strip().upper()
            name = (d.get("name") or "").strip()
            if not code or not name:
                return JsonResponse({"ok": False, "error": "ต้องกรอกรหัส + ชื่อสาขา"}, status=400)
            if len(code) > 4:
                return JsonResponse({"ok": False, "error": "รหัสสาขายาวได้ไม่เกิน 4 ตัว"}, status=400)
            if Branch.objects.filter(code__iexact=code).exists():
                return JsonResponse({"ok": False, "error": f"มีรหัส '{code}' อยู่แล้ว"}, status=400)
            Branch.objects.create(code=code, name=name, active=True)
        elif action == "rename":
            b = Branch.objects.filter(pk=d.get("id")).first()
            if not b:
                return JsonResponse({"ok": False, "error": "ไม่พบสาขา"}, status=404)
            name = (d.get("name") or "").strip()
            if not name:
                return JsonResponse({"ok": False, "error": "ชื่อสาขาห้ามว่าง"}, status=400)
            b.name = name
            b.save(update_fields=["name"])
        elif action == "toggle_active":
            b = Branch.objects.filter(pk=d.get("id")).first()
            if not b:
                return JsonResponse({"ok": False, "error": "ไม่พบสาขา"}, status=404)
            b.active = not b.active
            b.save(update_fields=["active"])
        elif action == "delete":
            b = Branch.objects.filter(pk=d.get("id")).first()
            if not b:
                return JsonResponse({"ok": False, "error": "ไม่พบสาขา"}, status=404)
            n = Car.objects.filter(branch=b.code, deleted_at__isnull=True).count()
            if n:
                return JsonResponse({"ok": False, "error": f"มีรถ {n} คันในสาขานี้ — ปิดใช้งานแทน หรือย้ายรถออกก่อน"}, status=400)
            b.delete()
        else:
            return JsonResponse({"ok": False, "error": "action ไม่ถูกต้อง"}, status=400)
        try:
            _branch_name_cache.clear()   # ล้าง cache ชื่อสาขา — rename เห็นผลทันที
        except Exception:
            pass
        return JsonResponse({"ok": True})
    # GET: ทุกสาขา (รวมปิดใช้งาน) + จำนวนรถต่อสาขา
    # bootstrap: ตารางยังว่าง → seed จาก constant (สาขาที่โชว์อยู่จาก fallback) เข้า DB ก่อน
    # กัน "เพิ่มสาขาใหม่ 1 อันแล้วสาขาเดิมหาย" (branch_pairs ใช้ DB rows แทน constant ทันทีที่มีแถวแรก)
    if not Branch.objects.exists():
        for _code, _name in C.BRANCH_CHOICES:
            Branch.objects.get_or_create(code=_code, defaults={"name": _name, "active": True})
        _branch_name_cache.clear()
    rows = [{"id": b.pk, "code": b.code, "name": b.name, "active": b.active,
             "cars": Car.objects.filter(branch=b.code, deleted_at__isnull=True).count()}
            for b in Branch.objects.all().order_by("code")]
    return JsonResponse({"ok": True, "branches": rows}, json_dumps_params={"ensure_ascii": False})


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
