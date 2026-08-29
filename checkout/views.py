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
        # ★ ส.ค.69 — งานที่ไปทำ + "ค้างนานแค่ไหน" (จาก log จริง เบิกแล้วไม่คืนคือปัญหาที่มองไม่เห็นเลย)
        "fuel": m.fuel_requested,
        "outHours": (round((timezone.now() - m.checked_out_at).total_seconds() / 3600, 1)
                     if (m.checked_out_at and not m.returned_at) else None),
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


# =========================================================
#  เบิก-คืนรถ จากหน้าสแกน QR (แบบ C · ส.ค.69)
#  คนงานสแกน QR ที่รถอยู่แล้วทุกวัน → เพิ่มปุ่มเบิก/คืนในหน้าเดิม = เปลี่ยนพฤติกรรมน้อยที่สุด
#  แล้วบอทโพสต์สรุปเข้ากลุ่ม LINE ให้หัวหน้าเห็นเหมือนเดิม (ดู lineout.py)
# =========================================================
from django.contrib.auth.decorators import login_required   # noqa: E402
from django.views.decorators.http import require_POST        # noqa: E402

from . import constants as C                                 # noqa: E402
from . import lineout                                        # noqa: E402
from .models import ChecklistConfig, ChecklistItem, MovementPhoto   # noqa: E402


def open_movement_for(car_code):
    """รอบเบิกที่ "ยังไม่คืน" ของรถคันนี้ (ถ้ามี) — ใช้ตัดสินว่าจะโชว์ปุ่มเบิกหรือปุ่มคืน"""
    return (CarMovement.objects
            .filter(car_id=car_code, returned_at__isnull=True)
            .exclude(status=CarMovement.CANCELLED)
            .order_by("-checked_out_at", "-created_at").first())


def web_checklist(phase="out"):
    """เช็คลิสต์รูปที่ใช้กับการเบิกผ่านเว็บ — เอาจาก DB ถ้าแอดมินตั้งไว้ ไม่งั้นใช้ค่าเริ่มต้นในโค้ด"""
    cfg = ChecklistConfig.objects.filter(room_line_group_id=C.WEB_CONFIG_KEY, active=True).first()
    if cfg:
        items = list(cfg.items.all().order_by("order"))
        if items:
            return [dict(key=i.key, label=i.label, media_type=i.media_type,
                         required=i.required, min_count=i.min_count) for i in items]
    return list(C.DEFAULT_CHECKLIST if phase == "out" else C.RETURN_CHECKLIST)


def _actor_name(request):
    """ชื่อคนทำ — เอาจาก session ฝั่งขายก่อน (ชื่อเล่นที่ทุกคนรู้จัก) ไม่งั้นใช้ username"""
    u = request.session.get("oxlet_user")
    if isinstance(u, dict):
        n = (u.get("nickname") or u.get("display_name") or "").strip()
        if n:
            return n
    user = request.user
    return (user.get_full_name() or user.username) if user.is_authenticated else "ไม่ทราบชื่อ"


def _save_photos(m, phase, media):
    """เก็บไฟล์แนบ — media = [{id, video}] จาก /track/api/upload (Drive id หรือ path บนดิสก์)
    เก็บ token ลง FileField.name ตรงๆ (วิธีเดียวกับ Car.photo ที่ใช้อยู่) → แสดงผลด้วยตัวเดิมได้"""
    n = 0
    for item in (media or []):
        token = (item.get("id") if isinstance(item, dict) else item) or ""
        if not token:
            continue
        p = MovementPhoto(movement=m, phase=phase,
                          media_type=MovementPhoto.VIDEO if (isinstance(item, dict) and item.get("video"))
                          else MovementPhoto.PHOTO)
        p.file.name = token
        p.save()
        n += 1
    return n


def _missing_required(checklist, count):
    """ชื่อข้อที่ยังขาด — เฟสนี้ยังไม่มี AI จำแนกว่ารูปไหนคือข้อไหน
    จึงเช็คแค่ "จำนวนรวมพอไหม" (ผลรวม min_count ของข้อบังคับ) แล้วบอกว่าต้องถ่ายอะไรบ้าง
    (จำแนกรายข้อด้วย AI = เฟสถัดไป · โครง MovementPhoto.checklist_item/ai_label รองรับไว้แล้ว)"""
    need = sum(i["min_count"] for i in checklist if i.get("required"))
    if count >= need:
        return []
    return [i["label"] for i in checklist if i.get("required")]


@csrf_exempt
@login_required
@require_POST
def api_car_out(request):
    """เบิกรถ — POST {code, purpose, destination?, odo_out?, fuel?, note?, media:[{id,video}]}"""
    try:
        b = json.loads(request.body or "{}")
    except Exception:
        b = {}
    from cars.models import Car
    car = Car.objects.filter(code=(b.get("code") or "").strip()).first()
    if not car:
        return JsonResponse({"ok": False, "error": "ไม่พบรถคันนี้"}, status=404)
    if open_movement_for(car.code):
        return JsonResponse({"ok": False, "error": "รถคันนี้ถูกเบิกอยู่แล้ว ยังไม่ได้คืน"}, status=400)

    purpose = (b.get("purpose") or "").strip()
    if purpose not in C.PURPOSE_NAME:
        return JsonResponse({"ok": False, "error": "เลือกประเภทงานก่อน"}, status=400)
    media = b.get("media") if isinstance(b.get("media"), list) else []
    checklist = web_checklist("out")
    missing = _missing_required(checklist, len(media))
    if missing:
        need = sum(i["min_count"] for i in checklist if i.get("required"))
        return JsonResponse({"ok": False, "error": "ต้องแนบรูปอย่างน้อย %d รูป (%s)"
                             % (need, " · ".join(missing))}, status=400)

    odo = b.get("odo_out")
    try:
        odo = int(str(odo).replace(",", "").strip()) if str(odo or "").strip() else None
    except (TypeError, ValueError):
        odo = None
    m = CarMovement.objects.create(
        car=car, plate_text=car.plate or "",
        borrower_name=_actor_name(request),
        purpose_key=purpose, purpose=C.PURPOSE_NAME[purpose],
        destination=(b.get("destination") or "").strip(),
        checked_out_at=timezone.now(), odo_out=odo,
        fuel_requested=bool(b.get("fuel")),
        note=(b.get("note") or "").strip(),
        status=CarMovement.PENDING_HUMAN,   # รอหัวหน้ารับทราบในกลุ่ม (เหมือนที่ทำกันอยู่)
    )
    _save_photos(m, MovementPhoto.OUT, media)
    sent = lineout.notify_out(m)
    return JsonResponse({"ok": True, "id": m.id, "lineSent": sent},
                        json_dumps_params={"ensure_ascii": False})


@csrf_exempt
@login_required
@require_POST
def api_car_return(request):
    """คืนรถ — POST {code, odo_in?, damage?, note?, media:[{id,video}]}"""
    try:
        b = json.loads(request.body or "{}")
    except Exception:
        b = {}
    m = open_movement_for((b.get("code") or "").strip())
    if not m:
        return JsonResponse({"ok": False, "error": "รถคันนี้ไม่มีรอบเบิกที่ค้างอยู่"}, status=404)
    media = b.get("media") if isinstance(b.get("media"), list) else []
    checklist = web_checklist("in")
    missing = _missing_required(checklist, len(media))
    if missing:
        need = sum(i["min_count"] for i in checklist if i.get("required"))
        return JsonResponse({"ok": False, "error": "ต้องแนบรูปอย่างน้อย %d รูป (%s)"
                             % (need, " · ".join(missing))}, status=400)
    odo = b.get("odo_in")
    try:
        odo = int(str(odo).replace(",", "").strip()) if str(odo or "").strip() else None
    except (TypeError, ValueError):
        odo = None
    m.returned_at = timezone.now()
    m.odo_in = odo
    m.damage_reported = bool(b.get("damage"))
    if b.get("note"):
        m.note = (m.note + "\n" if m.note else "") + "คืน: " + str(b.get("note")).strip()
    m.status = CarMovement.APPROVED_HUMAN if not m.damage_reported else CarMovement.PENDING_HUMAN
    m.save()
    _save_photos(m, MovementPhoto.IN, media)
    sent = lineout.notify_return(m)
    return JsonResponse({"ok": True, "id": m.id, "lineSent": sent},
                        json_dumps_params={"ensure_ascii": False})


# =========================================================
#  โหมดเฝ้าดู (observe) — เก็บข้อความในกลุ่ม LINE ไว้ "ดูเฉยๆ" ก่อนเปิดใช้จริง
#  เจ้าของขอ: เอาบอทเข้ากลุ่ม → นั่งดูว่าระบบตีความตรงไหม → ค่อยเปิดทำงาน
# =========================================================
def observe_enabled() -> bool:
    """เปิดเก็บ log ไหม — ตั้งที่ KVStore 'checkout_line_config' {observe: true}"""
    try:
        from dashboard.services import cache_store
        cfg = (cache_store.get_kv("checkout_line_config") or {}).get("data") or {}
        return bool(cfg.get("observe"))
    except Exception:
        return False


def record_group_events(data):
    """เก็บข้อความจาก payload ของ LINE webhook — best-effort ล้วน
    ★ อ่านอย่างเดียว ไม่สร้าง/แก้เคสเบิก-คืนใดๆ ทั้งสิ้น (นั่นคือประเด็นของโหมดนี้)"""
    if not observe_enabled():
        return 0
    from datetime import datetime, timezone as _dtz
    from .models import GroupMessage
    from . import parser as P
    from cars.models import Car

    events = data.get("events") if isinstance(data, dict) else (data if isinstance(data, list) else [])
    saved = 0
    for ev in (events or []):
        if not isinstance(ev, dict) or ev.get("type") != "message":
            continue
        src = ev.get("source") or {}
        gid = src.get("groupId") or ""
        if not gid:
            continue
        msg = ev.get("message") or {}
        mid = str(msg.get("id") or "")
        if mid and GroupMessage.objects.filter(message_id=mid).exists():
            continue          # กันซ้ำ (LINE ส่งซ้ำได้)
        text = msg.get("text") or ""
        r = P.parse(text)
        car = None
        if r.get("plate"):
            # คนพิมพ์เลขท้ายทะเบียน 3-4 ตัว → หารถที่ทะเบียนลงท้ายด้วยเลขนั้น
            car = Car.objects.filter(plate__endswith=r["plate"]).first()
        ts = ev.get("timestamp")
        sent = None
        if ts:
            try:
                sent = datetime.fromtimestamp(int(ts) / 1000, tz=_dtz.utc)
            except Exception:
                sent = None
        GroupMessage.objects.create(
            group_id=gid, message_id=mid,
            sender_id=(src.get("userId") or ""),
            msg_type=str(msg.get("type") or ""), text=text,
            parsed_kind=r["kind"], parsed_plate=r["plate"], parsed_purpose=r["purpose"],
            parsed_conf=r["confidence"], parsed_why=r["why"][:120],
            matched_car=car, sent_at=sent or timezone.now(),
        )
        saved += 1
    return saved


def observe_page(request):
    """หน้าเทียบ "ข้อความจริง vs ระบบตีความว่าอะไร" — กดบอกถูก/ผิด แล้ววัดความแม่น"""
    return render(request, "checkout/observe.html", {"is_admin": bool(_admin(request))})


@csrf_exempt
def api_observe(request):
    if not _admin(request):
        return JsonResponse({"ok": False, "error": "ต้อง login admin"}, status=401)
    from .models import GroupMessage
    from . import parser as P
    rows = []
    for m in GroupMessage.objects.select_related("matched_car")[:400]:
        rows.append({
            "id": m.id,
            "at": timezone.localtime(m.sent_at).strftime("%d/%m %H:%M") if m.sent_at else "",
            "who": m.sender_name or ((m.sender_id[:8] + "…") if m.sender_id else ""),
            "type": m.msg_type, "text": m.text,
            "kind": m.parsed_kind,
            "kindLabel": {"out": "เบิก", "in": "คืน"}.get(m.parsed_kind, "—"),
            "plate": m.parsed_plate, "purpose": P.purpose_name(m.parsed_purpose),
            "conf": m.parsed_conf, "why": m.parsed_why,
            "car": (m.matched_car.code + " · " + (m.matched_car.plate or "")) if m.matched_car_id else "",
            "verdict": m.human_verdict,
        })
    total = GroupMessage.objects.count()
    detected = GroupMessage.objects.exclude(parsed_kind="").count()
    judged = GroupMessage.objects.exclude(human_verdict="")
    nj = judged.count()
    ok = judged.filter(human_verdict="ok").count()
    return JsonResponse({
        "ok": True, "rows": rows, "enabled": observe_enabled(),
        "stats": {"messages": total, "detected": detected, "judged": nj, "correct": ok,
                  "accuracy": round(ok * 100.0 / nj, 1) if nj else None},
    }, json_dumps_params={"ensure_ascii": False})


@csrf_exempt
def api_observe_verdict(request):
    """คนตรวจกดบอกว่าระบบตีความถูก/ผิด — POST {id, verdict: ok|wrong|''}"""
    if not _admin(request):
        return JsonResponse({"ok": False, "error": "ต้อง login admin"}, status=401)
    try:
        b = json.loads(request.body or "{}")
    except Exception:
        b = {}
    from .models import GroupMessage
    m = GroupMessage.objects.filter(id=b.get("id")).first()
    if not m:
        return JsonResponse({"ok": False, "error": "ไม่พบข้อความ"}, status=404)
    v = (b.get("verdict") or "").strip()
    m.human_verdict = v if v in ("ok", "wrong") else ""
    m.save(update_fields=["human_verdict"])
    return JsonResponse({"ok": True, "verdict": m.human_verdict})


@csrf_exempt
def api_observe_toggle(request):
    """เปิด/ปิดโหมดเฝ้าดู + ตั้ง group id — POST {observe?, group_id?, enabled?}"""
    if not _admin(request):
        return JsonResponse({"ok": False, "error": "ต้อง login admin"}, status=401)
    try:
        b = json.loads(request.body or "{}")
    except Exception:
        b = {}
    from dashboard.services import cache_store
    cfg = (cache_store.get_kv("checkout_line_config") or {}).get("data") or {}
    for k in ("observe", "enabled"):
        if k in b:
            cfg[k] = bool(b[k])
    if "group_id" in b:
        cfg["group_id"] = (b.get("group_id") or "").strip()
    cache_store.set_kv("checkout_line_config", cfg)
    return JsonResponse({"ok": True, "config": cfg}, json_dumps_params={"ensure_ascii": False})
