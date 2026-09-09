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

from . import people
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
    # prefetch_related("photos") ทำให้บรรทัดนี้ไม่ยิง query เพิ่ม (อย่าเปลี่ยนไปใช้ .count())
    photos = list(m.photos.all())

    def _t(dt):
        return timezone.localtime(dt).strftime("%d/%m %H:%M") if dt else ""
    return {
        "id": m.id,
        "plate": m.plate_text or (m.car_id or ""),
        # ★ ชื่อเล่นเท่านั้น — safe_name แปลง line_<userId> ที่อาจค้างจากข้อมูลเก่าให้ด้วย
        "borrower": people.safe_name(m.borrower_name),
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
        "photos": len(photos),
        # รูปแยกช่วง (เบิก/คืน) — หน้าเว็บโชว์ thumbnail กดดูเต็มได้
        "media": _photo_urls(photos),
        "approvedBy": m.approved_by,
        # ★ ส.ค.69 — งานที่ไปทำ + "ค้างนานแค่ไหน" (จาก log จริง เบิกแล้วไม่คืนคือปัญหาที่มองไม่เห็นเลย)
        "fuel": m.fuel_requested,
        "outHours": (round((timezone.now() - m.checked_out_at).total_seconds() / 3600, 1)
                     if (m.checked_out_at and not m.returned_at) else None),
    }


def _top_cars(limit=10):
    """รถที่ถูกเบิกบ่อยสุด — นับจาก **ทุกเคสในระบบ** ไม่ใช่แค่หน้าที่โหลดมา

    ★ ก.ย.69 (เจ้าของขอ): "อยากรู้ว่ารถคันไหนโดนเบิกบ่อยที่สุด"
      ใช้ตอบว่า รถคันไหนควรเป็น "รถส่วนกลาง" จริงๆ · คันไหนถูกหยิบไปใช้จนไม่ได้ขาย
    จัดกลุ่มด้วย car_id ถ้ารู้ว่าคันไหน ไม่งั้นใช้ทะเบียนที่พิมพ์ (เคสที่ยังจับคู่รถไม่ได้)
    """
    rows = CarMovement.objects.exclude(status=CarMovement.CANCELLED).values_list(
        "car_id", "plate_text", "checked_out_at", "returned_at")
    agg = {}
    for car_id, plate, out_at, back_at in rows:
        key = car_id or (("p:" + plate) if plate else "")
        if not key:
            continue                      # ไม่รู้ว่าคันไหนเลย — นับไม่ได้
        a = agg.setdefault(key, {"carId": car_id, "plate": plate, "n": 0,
                                 "last": None, "outNow": False})
        a["n"] += 1
        if not a["plate"] and plate:
            a["plate"] = plate
        if out_at and (a["last"] is None or out_at > a["last"]):
            a["last"] = out_at
        if out_at and not back_at:
            a["outNow"] = True
    top = sorted(agg.values(), key=lambda x: (-x["n"], x["plate"]))[:limit]

    names = {}
    ids = [t["carId"] for t in top if t["carId"]]
    if ids:
        try:
            from cars.models import Car
            for c in Car.objects.filter(code__in=ids):
                names[c.code] = {"plate": c.plate or "", "model": (c.brand + " " + c.model).strip()}
        except Exception:
            pass
    out = []
    for t in top:
        info = names.get(t["carId"] or "", {})
        out.append({
            "plate": t["plate"] or info.get("plate") or (t["carId"] or "-"),
            "model": info.get("model", ""),
            "count": t["n"],
            "last": timezone.localtime(t["last"]).strftime("%d/%m") if t["last"] else "",
            "outNow": t["outNow"],
        })
    return out


@csrf_exempt
def api_movements(request):
    if not _admin(request):
        return JsonResponse({"ok": False, "error": "ต้อง login admin"}, status=401)
    # โหลดกว้างขึ้นเพื่อให้ "ค้นหา" ฝั่งหน้าเว็บครอบคลุมของเก่าด้วย (เดิม 300)
    movements = list(CarMovement.objects.select_related("car").prefetch_related("photos")[:1000])
    rows = [_mv_json(m) for m in movements]
    counts = {
        "open": sum(1 for m in movements if m.is_open),
        "incomplete": sum(1 for m in movements if m.status == CarMovement.INCOMPLETE),
        "pending": sum(1 for m in movements if m.status == CarMovement.PENDING_HUMAN),
        "hold": sum(1 for m in movements if m.status == CarMovement.EQUIPMENT_HOLD),
        "violations": ViolationLog.objects.count(),
        "overdue": sum(1 for m in movements
                       if m.is_open and m.checked_out_at
                       and (timezone.now() - m.checked_out_at).total_seconds() / 3600 >= C.OVERDUE_HOURS),
    }
    # ★ ก.ย.69 — ส่งเกณฑ์ "ค้างกี่ชม." จาก constants ไม่ให้หน้าเว็บ hardcode ซ้ำ
    #   (เดิม template ฝัง 12/4 ไว้เอง → แก้ constants แล้วหน้าเว็บไม่เปลี่ยนตาม)
    #   ⚠️ ห้าม import C ในฟังก์ชันนี้ — จะกลายเป็นตัวแปร local แล้ว counts ข้างบนพัง (UnboundLocalError)
    return JsonResponse({"ok": True, "movements": rows, "counts": counts,
                         "topCars": _top_cars(),
                         "total": CarMovement.objects.count(),
                         "config": {"overdueHours": C.OVERDUE_HOURS, "warnHours": C.WARN_HOURS}},
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
    """ชื่อคนทำ — **ชื่อเล่นเท่านั้น ห้ามเป็น LINE user id**
    ★ ก.ย.69: เดิม fallback ไป `user.username` ซึ่งของคนที่เข้าผ่าน LINE คือ `line_<userId>`
      → LINE user id หลุดไปโชว์บนหน้าเว็บ (อ่านไม่ออก + เป็นข้อมูลส่วนบุคคล)
      ตอนนี้ส่งผ่าน `people.safe_name()` ซึ่งแปลงกลับเป็นชื่อเล่นจากชีตพนักงานให้"""
    from . import people
    u = request.session.get("oxlet_user")
    if isinstance(u, dict):
        n = (u.get("nickname") or "").strip()
        if n:
            return n
        n = people.nickname_for(user_id=(u.get("user_id") or ""),
                                display_name=(u.get("display_name") or ""))
        if n and n != "ไม่ทราบชื่อ":
            return n
    user = request.user
    if not user.is_authenticated:
        return "ไม่ทราบชื่อ"
    return people.safe_name(user.get_full_name() or user.username) or "ไม่ทราบชื่อ"


def _label_movement_media(m, phase):
    """ตั้งชื่อไฟล์รูป/วิดีโอใน Google Drive ให้ **เรียงลำดับและอ่านออก**

    ได้ชื่อแบบ `เบิกรถ(ใหม่) 9ก.ย.69 11-02 01.jpg` / `คืนรถ(ใหม่) 9ก.ย.69 12-52 01.jpg`
    → เปิดโฟลเดอร์ของรถคันนั้นใน Drive แล้วรู้ทันทีว่ารูปไหนตอนเบิก ตอนคืน ใครถ่าย เมื่อไหร่
    ★ ก.ย.69 (เจ้าของสั่ง "เก็บรูปทุกขั้นตอนเบิก/คืน ไว้ใน Drive เหมือนตัวอื่น")
      — ไฟล์ขึ้น Drive อยู่แล้ว (ผ่าน /track/api/upload พร้อม code → เข้าโฟลเดอร์รถ)
        แต่เดิม **ไม่ตั้งชื่อ** เลยเป็น IMG_1234.jpg กองรวมกัน แยกไม่ออก
    ใช้กติกาเดียวกับฝั่งสเตป (`cars.views._label_stage_media`) — เลขลำดับเติม 0 ให้เรียงถูกใน Drive
    best-effort: ล้มเหลว = ไม่ทำให้การเบิก/คืนพัง (ชื่อเป็นแค่ป้าย ลิงก์แสดงผลอิง id)
    """
    import os as _os
    from cars import gdrive
    from cars.views import _safe_filename, _THAI_MON
    if not gdrive.is_configured():
        return
    at = m.checked_out_at if phase == MovementPhoto.OUT else (m.returned_at or timezone.now())
    now = timezone.localtime(at or timezone.now())
    action = "เบิกรถ" if phase == MovementPhoto.OUT else "คืนรถ"
    who = _safe_filename(people.safe_name(m.borrower_name)) or "-"
    datestr = "%d%s%02d %02d-%02d" % (now.day, _THAI_MON[now.month - 1],
                                      (now.year + 543) % 100, now.hour, now.minute)
    n = 0
    for p in m.photos.filter(phase=phase).order_by("id"):
        fid = p.file.name or ""
        if not fid or "/" in fid:      # "/" = เก็บบนดิสก์ VPS → ข้าม (ฟีเจอร์นี้สำหรับ Drive)
            continue
        n += 1
        ext = _os.path.splitext(gdrive.get_name(fid))[1]
        if not ext:
            ext = ".mp4" if p.media_type == MovementPhoto.VIDEO else ".jpg"
        gdrive.rename(fid, "%s(%s) %s %02d%s" % (action, who, datestr, n, ext))


def _photo_urls(photos):
    """รูปของเคสนี้แยกตามช่วง (เบิก/คืน) สำหรับโชว์ในตาราง — ใช้ตัวสร้าง URL ตัวเดียวกับฝั่งสเตป
    ⚠️ รับ **list ที่ prefetch มาแล้ว** ไม่ใช่ queryset — ตารางมีได้ 1000 แถว ถ้ายิง query ต่อแถวจะพังทันที"""
    from cars.views import _media_urls
    out = {"out": [], "in": []}
    for p in photos:
        token = p.file.name or ""
        if not token:
            continue               # เคสที่นำเข้าจาก log — รู้ว่าส่งกี่ไฟล์ แต่ไฟล์อยู่ใน LINE
        u = _media_urls([{"id": token, "video": p.media_type == MovementPhoto.VIDEO}])
        if u:
            out["out" if p.phase == MovementPhoto.OUT else "in"].append(u[0])
    return out


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
    try:
        _label_movement_media(m, MovementPhoto.OUT)
    except Exception:
        pass
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
    try:
        _label_movement_media(m, MovementPhoto.IN)
    except Exception:
        pass
    sent = lineout.notify_return(m)
    return JsonResponse({"ok": True, "id": m.id, "lineSent": sent},
                        json_dumps_params={"ensure_ascii": False})
