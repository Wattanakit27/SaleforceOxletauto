"""หน้า supervisor เบิก-คืนรถ (ก้อน 2) — ดูเคส/อนุมัติ/เพิ่มมือ ในธีมเดียวกับแดชบอร์ด
- gate ด้วย session sales admin (position=="admin") เหมือนหน้ารวม /dashboard/
- ฝังเป็นแท็บ "เบิก-คืนรถ" ใน index.html (iframe /checkout/) หรือเปิดตรง /checkout/
- ยังไม่แตะ LINE (ก้อน 3) — เพิ่มเคสมือได้เพื่อทดสอบ flow ก่อน
"""
import json

from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import CarMovement, ViolationLog


# ผู้ที่เห็นหน้ารวม /dashboard/ ได้ (admin + ผู้บริหาร) = supervisor เบิก-คืนรถ
_SUPERVISOR_POSITIONS = {"admin", "executive", "ผู้บริหาร", "manager", "exec"}


def _admin(request):
    """คืน user ถ้าเป็น supervisor (admin/ผู้บริหาร · session sales) ไม่งั้น None"""
    u = request.session.get("oxlet_user")
    if u and isinstance(u, dict) and (u.get("position") or "").strip().lower() in _SUPERVISOR_POSITIONS:
        return u
    return None


def supervisor(request):
    """หน้า supervisor (HTML) — ถ้าไม่ใช่แอดมินโชว์ข้อความปฏิเสธ"""
    return render(request, "checkout/dashboard.html", {"is_admin": bool(_admin(request))})


def _mv_json(m):
    def _t(dt):
        return timezone.localtime(dt).strftime("%d/%m %H:%M") if dt else ""
    return {
        "id": m.id,
        "plate": m.plate_text or (m.car_id or ""),
        "borrower": m.borrower_name,
        "purpose": m.purpose,
        "destination": m.destination,
        "status": m.status,
        "statusLabel": m.get_status_display(),
        "isGreen": m.status in CarMovement.GREEN,
        "isOpen": m.is_open,
        "damage": m.damage_reported,
        "odoOut": m.odo_out,
        "odoIn": m.odo_in,
        "checkedOut": _t(m.checked_out_at),
        "returned": _t(m.returned_at),
        "photos": m.photos.count(),
        "approvedBy": m.approved_by,
    }


@csrf_exempt
def api_movements(request):
    if not _admin(request):
        return JsonResponse({"ok": False, "error": "ต้อง login admin"}, status=401)
    movements = list(CarMovement.objects.select_related("car")[:300])
    rows = [_mv_json(m) for m in movements]
    counts = {
        "open": sum(1 for m in movements if m.is_open),
        "incomplete": sum(1 for m in movements if m.status == CarMovement.INCOMPLETE),
        "pending": sum(1 for m in movements if m.status == CarMovement.PENDING_HUMAN),
        "hold": sum(1 for m in movements if m.status == CarMovement.EQUIPMENT_HOLD),
        "violations": ViolationLog.objects.count(),
    }
    return JsonResponse({"ok": True, "movements": rows, "counts": counts},
                        json_dumps_params={"ensure_ascii": False})


@csrf_exempt
def api_add(request):
    u = _admin(request)
    if not u:
        return JsonResponse({"ok": False, "error": "ต้อง login admin"}, status=401)
    try:
        b = json.loads(request.body or "{}")
    except Exception:
        b = {}
    plate = (b.get("plate") or "").strip()
    if not plate:
        return JsonResponse({"ok": False, "error": "ใส่ทะเบียน"}, status=400)
    m = CarMovement.objects.create(
        plate_text=plate,
        borrower_name=(b.get("borrower") or "").strip(),
        purpose=(b.get("purpose") or "").strip(),
        destination=(b.get("destination") or "").strip(),
        checked_out_at=timezone.now(),
        status=CarMovement.OUT_WAITING,
        note="เพิ่มมือ (supervisor)",
    )
    return JsonResponse({"ok": True, "id": m.id}, json_dumps_params={"ensure_ascii": False})


@csrf_exempt
def api_action(request):
    """POST {id, action: approve|return|cancel, odo_in?, damage?}"""
    u = _admin(request)
    if not u:
        return JsonResponse({"ok": False, "error": "ต้อง login admin"}, status=401)
    try:
        b = json.loads(request.body or "{}")
    except Exception:
        b = {}
    m = CarMovement.objects.filter(id=b.get("id")).first()
    if not m:
        return JsonResponse({"ok": False, "error": "ไม่พบเคส"}, status=404)
    action = b.get("action")
    who = u.get("nickname") or u.get("display_name") or "admin"
    if action == "approve":
        m.status = CarMovement.APPROVED_HUMAN
        m.approved_by = who
    elif action == "return":
        m.returned_at = timezone.now()
        odo = b.get("odo_in")
        if odo not in (None, ""):
            try:
                m.odo_in = int(odo)
            except (TypeError, ValueError):
                pass
        m.damage_reported = bool(b.get("damage"))
        if m.status in (CarMovement.OUT_WAITING, CarMovement.INCOMPLETE):
            m.status = CarMovement.CHECKING
    elif action == "cancel":
        m.status = CarMovement.CANCELLED
    else:
        return JsonResponse({"ok": False, "error": "action ไม่รู้จัก"}, status=400)
    m.save()
    return JsonResponse({"ok": True, "status": m.status, "statusLabel": m.get_status_display()},
                        json_dumps_params={"ensure_ascii": False})
