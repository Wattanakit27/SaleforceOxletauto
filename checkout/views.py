"""หน้า supervisor เบิก-คืนรถ (ก้อน 2) — ดูเคส/อนุมัติ/เพิ่มมือ ในธีมเดียวกับแดชบอร์ด
- gate ด้วย session sales admin (position=="admin") เหมือนหน้ารวม /dashboard/
- ฝังเป็นแท็บ "เบิก-คืนรถ" ใน index.html (iframe /checkout/) หรือเปิดตรง /checkout/
- ยังไม่แตะ LINE (ก้อน 3) — เพิ่มเคสมือได้เพื่อทดสอบ flow ก่อน
"""
import json
import re

from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from . import people
from .models import CarMovement, GroupChat, ViolationLog


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
        "source": m.source,
        # มุมที่ยังไม่ได้ถ่าย (ชื่อไทย) — ว่าง = ครบ · หัวหน้าเห็นได้ทันทีในตาราง
        "missOut": C.missing_shots("out", m.shots_out),
        "missIn": C.missing_shots("in", m.shots_in) if m.returned_at else [],
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


def _clean_shots(raw, phase="out"):
    """คีย์มุมที่คนงานติ๊กมา — กรองให้เหลือเฉพาะคีย์ที่มีจริง (กันส่งอะไรมาก็ได้)"""
    ok = {k for k, _ in C.shot_angles(phase)}
    return [k for k in (raw or []) if isinstance(k, str) and k in ok]


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
        # ★ ก.ย.69 — มุมที่คนงานติ๊กว่าถ่ายแล้ว (ไม่ครบก็บันทึกได้ · แค่จดว่าขาดอะไร)
        shots_out=_clean_shots(b.get("shots"), "out"),
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
    m.shots_in = _clean_shots(b.get("shots"), "in")
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


# =========================================================
#  ตั้งค่ากลุ่ม LINE + "ดักเก็บข้อความจากกลุ่ม" (ก.ย.69 — เจ้าของสั่ง)
#  ★ โหมดตอนนี้ = อ่านอย่างเดียว: บอทอ่านข้อความในกลุ่มที่เลือก แล้วสร้างเคสให้ดู
#    **ไม่ตอบกลับ ไม่โพสต์อะไรเข้ากลุ่มทั้งสิ้น** (เจ้าของ: "อย่าเพิ่งส่งอะไร เก็บไว้ก่อน เดี๋ยวตามมาดู")
#  เปิดการส่งเมื่อไหร่ = ติ๊ก "ให้บอทส่งสรุปเข้ากลุ่ม" ในพาเนลตั้งค่า
# =========================================================
LINE_CFG_KEY = "checkout_line_config"
_SEEN_KEY = "checkout_seen_msgs"      # กัน LINE ส่ง webhook ซ้ำ (เก็บ message id ล่าสุด)
_SEEN_MAX = 300


def line_cfg() -> dict:
    try:
        from dashboard.services import cache_store
        return (cache_store.get_kv(LINE_CFG_KEY) or {}).get("data") or {}
    except Exception:
        return {}


def _save_cfg(cfg):
    from dashboard.services import cache_store
    cache_store.set_kv(LINE_CFG_KEY, cfg)


@csrf_exempt
def api_line_config(request):
    """GET = ค่าที่ตั้งไว้ + รายชื่อกลุ่มที่บอทรู้จัก · POST {group_id?, listen?, send?} = บันทึก"""
    if not _admin(request):
        return JsonResponse({"ok": False, "error": "ต้อง login admin"}, status=401)
    cfg = line_cfg()
    if request.method == "POST":
        try:
            b = json.loads(request.body or "{}")
        except Exception:
            b = {}
        if "group_id" in b:
            new_gid = (b.get("group_id") or "").strip()
            if new_gid and new_gid != (cfg.get("group_id") or "").strip():
                # ★ ก.ย.69 — กลุ่มนี้ใช้ทั้ง "ดักเก็บ" และ "โพสต์สรุป" → ต้องเป็น id ที่บอทตัวส่งเห็น
                from dashboard.services.line_channels import push_group_error
                err = push_group_error(new_gid)
                if err:
                    return JsonResponse({"ok": False, "error": err}, status=400,
                                        json_dumps_params={"ensure_ascii": False})
            cfg["group_id"] = new_gid
        for k in ("listen", "send", "store_chat", "store_customer_chat"):
            if k in b:
                cfg[k] = bool(b[k])
        _save_cfg(cfg)

    groups = []
    try:
        from dashboard.services import cache_store
        from dashboard.services.line_channels import group_visible_to_push
        for gid, v in ((cache_store.get_kv("line_groups") or {}).get("data") or {}).items():
            if group_visible_to_push(v or {}):      # ซ่อน id ของบอทตัวรับ (ตัวส่งใช้ไม่ได้)
                groups.append({"id": gid, "name": (v or {}).get("name", "")})
        groups.sort(key=lambda x: (x["name"] or x["id"]))
    except Exception:
        pass

    from django.conf import settings as _st

    from dashboard.services import line_channels as _ch
    n_line = CarMovement.objects.filter(source=CarMovement.SRC_LINE).count()
    return JsonResponse({
        "ok": True,
        "config": {"groupId": cfg.get("group_id", ""),
                   "listen": bool(cfg.get("listen")),
                   "send": bool(cfg.get("send")),
                   "storeChat": bool(cfg.get("store_chat")),
                   "storeCustomerChat": bool(cfg.get("store_customer_chat"))},
        "chat": chat_stats(),
        "groups": groups,
        # ★ ก.ย.69 — แยกบัญชี "ตัวรับ" (เก็บแชท) กับ "ตัวส่ง" (โพสต์เข้ากลุ่ม)
        #   พาเนลต้องบอกให้ชัดว่าอันไหนพร้อม ไม่งั้นติ๊ก "ให้บอทโพสต์" แล้วเงียบโดยไม่รู้สาเหตุ
        "lineToken": bool(_ch.crm_token()),
        "pushToken": bool(_ch.push_token()),
        "splitAccounts": _ch.has_push_channel(),
        "webhookUrl": (getattr(_st, "SITE_URL", "") or "").rstrip("/") + "/api/line/webhook",
        "fromLine": n_line,
    }, json_dumps_params={"ensure_ascii": False})


def _seen(mid) -> bool:
    """เคยประมวลผลข้อความนี้แล้วหรือยัง (LINE ยิง webhook ซ้ำได้)"""
    if not mid:
        return False
    try:
        from dashboard.services import cache_store
        ids = (cache_store.get_kv(_SEEN_KEY) or {}).get("data") or []
        if mid in ids:
            return True
        ids.append(mid)
        cache_store.set_kv(_SEEN_KEY, ids[-_SEEN_MAX:])
    except Exception:
        return False
    return False


def _open_of(uid, name):
    """รอบที่ยังไม่คืนของคนนี้ (ล่าสุดก่อน) — เทียบด้วย LINE id ก่อน ไม่มีค่อยเทียบชื่อ"""
    qs = CarMovement.objects.filter(returned_at__isnull=True).exclude(status=CarMovement.CANCELLED)
    m = qs.filter(borrower_line_id=uid).order_by("-checked_out_at").first() if uid else None
    if not m and name:
        m = qs.filter(borrower_name=name).order_by("-checked_out_at").first()
    return m


def ingest_group_events(data) -> int:
    """อ่าน event จากกลุ่ม LINE ที่เลือกไว้ → สร้าง/ปิดเคสเบิก-คืน ตาม pattern ที่ parser จับได้

    **อ่านอย่างเดียว — ไม่ส่งข้อความตอบกลับเข้ากลุ่มเด็ดขาด** (การส่งอยู่ที่ lineout ซึ่งปิดอยู่)
    เก็บเฉพาะข้อความที่ "จับ pattern ได้" เท่านั้น ไม่ได้ดูดทั้งกลุ่มลงฐานข้อมูล
    best-effort ทั้งก้อน: พังตรงไหน = เงียบ ไม่ทำให้ webhook เดิม (เก็บ group id) พัง
    """
    cfg = line_cfg()
    gid_want = (cfg.get("group_id") or "").strip()
    if not (cfg.get("listen") and gid_want):
        return 0
    from . import parser as P
    from cars.models import Car

    events = data.get("events") if isinstance(data, dict) else (data if isinstance(data, list) else [])
    made = 0
    for ev in (events or []):
        if not isinstance(ev, dict) or ev.get("type") != "message":
            continue
        src = ev.get("source") or {}
        if (src.get("groupId") or "") != gid_want:
            continue                      # กลุ่มอื่น = ไม่ยุ่ง
        msg = ev.get("message") or {}
        if msg.get("type") != "text":
            continue                      # รูป/สติกเกอร์ — ยังไม่ดึงไฟล์จาก LINE (เฟสถัดไป)
        if _seen(str(msg.get("id") or "")):
            continue
        r = P.parse(msg.get("text") or "")
        if not r["kind"]:
            continue                      # ไม่ใช่การเบิก/คืน = ไม่เก็บ

        uid = (src.get("userId") or "").strip()
        who = people.nickname_for(user_id=uid)
        cur = _open_of(uid, who)

        if r["kind"] == "out":
            car = None
            if r["plate"]:
                try:
                    car = Car.objects.filter(plate__endswith=r["plate"]).first()
                except Exception:
                    car = None
            CarMovement.objects.create(
                car=car, plate_text=r["plate"] or "",
                borrower_name=who, borrower_line_id=uid,
                purpose_key=r["purpose"], purpose=C.PURPOSE_NAME.get(r["purpose"], ""),
                checked_out_at=timezone.now(), fuel_requested=bool(r["fuel"]),
                note=(msg.get("text") or "").strip()[:500],
                status=CarMovement.PENDING_HUMAN,
                source=CarMovement.SRC_LINE,
            )
            made += 1
        elif r["kind"] == "in" and cur:
            cur.returned_at = timezone.now()
            cur.note = (cur.note + "\n" if cur.note else "") + "คืน: " + (msg.get("text") or "").strip()[:200]
            cur.save(update_fields=["returned_at", "note", "updated_at"])
            made += 1
        elif r["kind"] == "fuel" and cur and not cur.fuel_requested:
            cur.fuel_requested = True
            cur.save(update_fields=["fuel_requested", "updated_at"])
        elif r["kind"] == "plate_only" and cur and not cur.plate_text and r["plate"]:
            cur.plate_text = r["plate"]
            cur.save(update_fields=["plate_text", "updated_at"])
    return made


# =========================================================
#  เก็บแชทในกลุ่ม LINE ลง Postgres แยกตามกลุ่ม (ก.ย.69 — เจ้าของสั่ง)
#  n8n ยิง body ดิบของ LINE มาที่ /api/line/group_ingest → เก็บทุกกลุ่มที่บอทอยู่
#  ต่างจากการ "สร้างเคส" (ingest_group_events) ซึ่งดูเฉพาะกลุ่มที่ตั้งไว้กลุ่มเดียว
# =========================================================
_CHAT_CLEAN_KEY = "chat_cleanup_last"
_CHAT_LOG_KEY = "chat_store_last"      # ผลการเก็บแชทรอบล่าสุด (รวม error) — กันพังแบบเงียบ


def _chat_log(**kw):
    """จดผลรอบล่าสุดของ store_chat — ★ ก.ย.69

    `store_chat` ถูกเรียกใน daemon thread ที่ except กลืนทุกอย่าง → ถ้าเขียน DB ไม่ได้
    (คอลัมน์ไม่ตรง/สิทธิ์/ตารางหาย) จะได้ 0 ข้อความแบบ **ไม่มีร่องรอยเลย**
    เก็บไว้ให้ `checkout_config` โชว์ได้ว่าพยายามเก็บแล้วเกิดอะไรขึ้น
    """
    try:
        from dashboard.services import cache_store
        kw["at"] = timezone.localtime().isoformat(timespec="seconds")
        cache_store.set_kv(_CHAT_LOG_KEY, kw)
    except Exception:
        pass


def _event_time(ev):
    """เวลาในกลุ่มจาก event.timestamp (มิลลิวินาที) — ไม่มี = ใช้เวลาตอนนี้"""
    ts = ev.get("timestamp")
    try:
        if ts:
            from datetime import datetime, timezone as _dtz
            return datetime.fromtimestamp(int(ts) / 1000, tz=_dtz.utc)
    except Exception:
        pass
    return timezone.now()


def _cleanup_chat():
    """ลบแชทที่เกินอายุ — ทำมากสุดวันละครั้ง (เช็คผ่าน KV) ไม่ให้ถ่วง webhook"""
    try:
        from dashboard.services import cache_store
        today = timezone.localdate().isoformat()
        last = (cache_store.get_kv(_CHAT_CLEAN_KEY) or {}).get("data") or {}
        if last.get("day") == today:
            return
        now = timezone.now()
        # แชทกลุ่ม 90 วัน · แชทลูกค้า 60 วัน (บทสนทนากับคนนอก เก็บสั้นกว่าโดยตั้งใจ)
        n = GroupChat.objects.filter(
            chat_type=GroupChat.GROUP,
            sent_at__lt=now - timezone.timedelta(days=C.CHAT_KEEP_DAYS)).delete()[0]
        n += GroupChat.objects.exclude(chat_type=GroupChat.GROUP).filter(
            sent_at__lt=now - timezone.timedelta(days=C.CUSTOMER_CHAT_KEEP_DAYS)).delete()[0]
        # ★ โปรไฟล์ก็มีอายุเหมือนกัน — ข้อมูลส่วนบุคคลที่ไม่มีวันหมดอายุ = กองโตไม่หยุด (PDPA)
        #   ลบเฉพาะ "ลูกค้าที่หายไปนาน" · โปรไฟล์พนักงานเก็บไว้ (ใช้เทียบชื่อในงานประจำ)
        p = 0
        try:
            from .models import LineProfile
            p = LineProfile.objects.filter(
                is_employee=False,
                last_seen__lt=now - timezone.timedelta(days=C.CUSTOMER_CHAT_KEEP_DAYS)
            ).delete()[0]
        except Exception:
            pass
        cache_store.set_kv(_CHAT_CLEAN_KEY, {"day": today, "deleted": n, "profiles": p})
    except Exception:
        pass


def store_chat(data) -> int:
    """เก็บข้อความในกลุ่มลง `GroupChat` — คืนจำนวนที่เก็บใหม่

    เก็บ **ทุกกลุ่มที่บอทอยู่** (แยกด้วย group_id) ไม่ใช่แค่กลุ่มที่ตั้งดักเก็บเคส
    เปิด/ปิดที่ `checkout_line_config["store_chat"]` · ปิดอยู่ = ไม่เก็บอะไรเลย
    กันซ้ำด้วย `message_id` (unique) — LINE ยิง webhook ซ้ำได้
    """
    cfg = line_cfg()
    want_group = bool(cfg.get("store_chat"))            # แชทกลุ่ม
    want_user = bool(cfg.get("store_customer_chat"))    # แชท 1:1 กับลูกค้า
    # ★ 16 ก.ย.69 — คนใหม่ที่พิมพ์ในกลุ่มงาน = เพิ่มเข้าทะเบียนพนักงานให้เลย (เจ้าของขอ)
    #   **เปิดโดยปริยาย** · ปิดได้ที่ `checkout_line_config["auto_employee"]`
    #   (ถ้าวันหนึ่งมีกลุ่มที่มีลูกค้าปนอยู่ จะได้ไม่ดูดเข้าทะเบียน)
    auto_emp = bool(cfg.get("auto_employee", True))
    if not (want_group or want_user):
        return 0
    events = (data or {}).get("events") or []
    if not events:
        return 0

    # ★ ก.ย.69 — "บัญชีไหนเป็นคนได้ยินข้อความชุดนี้" (จาก `destination` ที่ LINE ใส่มาใน body)
    #   n8n forward ทั้ง 2 บัญชีมาที่ endpoint เดียวกัน → ไม่รู้ตรงนี้ = ดึงโปรไฟล์ด้วย token ผิดตัว
    chan = ""
    try:
        from dashboard.services.line_channels import channel_of
        chan = channel_of((data or {}).get("destination") or "")
    except Exception:
        chan = ""

    # ชื่อกลุ่มที่บอทจำไว้ (ไม่ต้องยิง LINE API ซ้ำทุกข้อความ)
    names = {}
    try:
        from dashboard.services import cache_store
        names = {g: (v or {}).get("name", "")
                 for g, v in ((cache_store.get_kv("line_groups") or {}).get("data") or {}).items()}
    except Exception:
        pass

    made, skipped, err = 0, 0, ""
    for ev in events:
        if not isinstance(ev, dict) or ev.get("type") != "message":
            continue
        src = ev.get("source") or {}
        gid = (src.get("groupId") or "").strip()
        # ★ ก.ย.69 — เดิมข้ามทุกอย่างที่ไม่มี groupId ทำให้ "ลูกค้าทักเข้า OA" หลุดหมด
        #   ทั้งที่ข้อมูลวิ่งมาถึงเซิร์ฟเวอร์แล้ว · ตอนนี้เก็บด้วย (เปิด/ปิดแยกกัน)
        ctype = GroupChat.GROUP if gid else (
            GroupChat.ROOM if src.get("roomId") else GroupChat.USER)
        if ctype == GroupChat.GROUP and not want_group:
            continue
        if ctype != GroupChat.GROUP and not want_user:
            continue
        msg = ev.get("message") or {}
        mid = str(msg.get("id") or "").strip()
        if not mid or GroupChat.objects.filter(message_id=mid).exists():
            continue
        mtype = (msg.get("type") or "").strip()
        uid = (src.get("userId") or "").strip()
        try:
            # ★ ก.ย.69 — เก็บ user id + โปรไฟล์ลงตาราง `LineProfile` ไปในตัว (เจ้าของสั่ง)
            #   รวมงาน "เทียบชีตพนักงาน → ไม่ใช่พนักงานค่อยถาม LINE → upsert โปรไฟล์"
            #   ไว้ที่เดียว · เดิมเรียก display_name_for() ซึ่งได้แค่ชื่อ ไม่ได้เก็บอะไรไว้เลย
            who = people.touch_profile(uid, group_id=gid, room_id=(src.get("roomId") or ""),
                                       chat_type=ctype, channel=chan,
                                       auto_employee=auto_emp).get("name") if uid else ""
        except Exception:
            who = ""
        try:
            GroupChat.objects.create(
                chat_type=ctype, channel=chan,
                group_id=gid, group_name=names.get(gid, ""), message_id=mid,
                sender_id=uid, sender_name=("" if who == "ไม่ทราบชื่อ" else who),
                msg_type=mtype, text=(msg.get("text") or "")[:5000],
                sticker_id=str(msg.get("stickerId") or "")[:32],
                sticker_package=str(msg.get("packageId") or "")[:32],
                emojis=msg.get("emojis") or [],
                extra={k: v for k, v in msg.items()
                       if k in ("keywords", "address", "latitude", "longitude",
                                "fileName", "fileSize", "duration", "title")},
                has_media=mtype in (GroupChat.IMAGE, GroupChat.VIDEO,
                                    GroupChat.AUDIO, GroupChat.FILE),
                sent_at=_event_time(ev),
            )
            made += 1
        except Exception as e:
            skipped += 1
            err = err or ("%s: %s" % (type(e).__name__, e))[:200]
            continue                     # ชนกันเพราะ webhook ซ้ำ = ข้าม ไม่ล้มทั้งก้อน
    _chat_log(saved=made, skipped=skipped, events=len(events), error=err)
    if made:
        _cleanup_chat()
    return made


def _profile_counts():
    """นับโปรไฟล์ที่เก็บไว้ — แยกลูกค้า/พนักงาน + **แยกตามบัญชีที่เจอ**

    ★ ก.ย.69 — ตัวเลข `byChannel` สำคัญตอนมี 2 บัญชี: ถ้าบอทคนละ provider
    คนเดียวกันจะได้ userId คนละตัว = นับเป็น 2 คน · ดูตรงนี้จะเห็นว่าเริ่มซ้ำหรือยัง
    """
    try:
        from django.db.models import Count
        from .models import LineProfile
        tot = LineProfile.objects.count()
        emp = LineProfile.objects.filter(is_employee=True).count()
        by = {(r["channel"] or "ไม่ทราบ"): r["n"]
              for r in LineProfile.objects.values("channel").annotate(n=Count("id"))}
        return {"total": tot, "employees": emp, "customers": tot - emp, "byChannel": by}
    except Exception:
        return {"total": 0, "employees": 0, "customers": 0, "byChannel": {}}


def _cust_row(r, prof=None):
    """1 แถวของ "ลูกค้าที่ทักเข้ามา" สำหรับพาเนล — ชื่อ/จำนวน/ช่วงเวลา + user id
    (ไม่มีรูปโปรไฟล์ — เจ้าของสั่งไม่เก็บ ก.ย.69)"""
    return {
        "name": (prof.show_name if prof else "") or r["sender_name"] or "(ไม่รู้ชื่อ)",
        "userId": r["sender_id"] or "",
        "status": (prof.status_message if prof else "") or "",
        "n": r["n"],
        "first": (timezone.localtime(prof.first_seen).strftime("%d/%m/%y")
                  if prof and prof.first_seen else ""),
        "last": timezone.localtime(r["last"]).strftime("%d/%m %H:%M") if r["last"] else "",
    }


# ─────────────────────────────────────────────────────────────
#  แชทลูกค้า (CRM) — ★ ก.ย.69
#  เจ้าของกดเมนู "ลูกค้า & แชท" แล้วเด้งไปโผล่หน้าเบิก-คืนรถ เพราะตอนแรกผมเอาข้อมูล
#  ลูกค้าไปฝังไว้ใน "พาเนลตั้งค่า" ของหน้านั้น → แยกออกมาเป็น endpoint ของตัวเอง
#  ให้แดชบอร์ดหลักเปิดเป็นพาเนลได้ตรงๆ ไม่ต้องข้ามหน้า
# ─────────────────────────────────────────────────────────────
CUST_LIST_MAX = 200      # รายชื่อลูกค้าต่อครั้ง
CUST_MSG_MAX = 100       # ข้อความย้อนหลังต่อคน


def _msg_preview(g) -> str:
    """ข้อความ 1 บรรทัดสำหรับโชว์ — ชนิดที่ไม่ใช่ตัวอักษรบอกเป็นคำอ่านออก"""
    if (g.text or "").strip():
        return g.text
    if g.msg_type == "sticker":
        return "[สติกเกอร์]"
    if g.has_media:
        return "[รูป/ไฟล์ — ตัวไฟล์อยู่ใน LINE ระบบยังไม่ได้โหลดมาเก็บ]"
    return "[%s]" % (g.msg_type or "ไม่ทราบชนิด")


@csrf_exempt
def api_employees(request):
    """ทะเบียนพนักงานในระบบเรา — GET ลิสต์ · POST `{action:"save"|"delete", …}` — ★ 16 ก.ย.69

    เจ้าของสั่งย้ายทะเบียนออกจากชีตมาไว้ที่ระบบ: *"เราจะให้เขาแก้ในระบบ SaleForce ของเรา"*
    เก็บ ชื่อเล่น · ชื่อที่ตั้งใน LINE · ตำแหน่ง · เวลาเข้างาน · วันหยุด · group id

    ★ **ไม่ส่ง LINE user id ของพนักงานออกมา** (กติกาเดิม · ใครถือ id ก็ทักหาพนักงานได้ตรง)
      บอกแค่ว่าผูกไว้กี่บัญชี — คนเดียวมีได้หลายบัญชีเพราะ id ออกต่อ provider ของบอท
    """
    if not _admin(request):
        return JsonResponse({"ok": False, "error": "ต้อง login admin"}, status=401)
    from .models import Employee

    if request.method == "POST":
        try:
            b = json.loads(request.body or "{}")
        except Exception:
            b = {}
        act = (b.get("action") or "save").strip()
        if act == "delete":
            n, _ = Employee.objects.filter(pk=b.get("id") or 0).delete()
            return JsonResponse({"ok": bool(n)}, json_dumps_params={"ensure_ascii": False})
        nick = (b.get("nickname") or "").strip()[:80]
        if not nick:
            return JsonResponse({"ok": False, "error": "ต้องมีชื่อเล่น"}, status=400,
                                json_dumps_params={"ensure_ascii": False})
        fields = {
            "display_name": (b.get("displayName") or "").strip()[:120],
            "position": (b.get("position") or "").strip()[:80],
            "work_start": (b.get("workStart") or "").strip()[:16],
            "day_off": (b.get("dayOff") or "").strip()[:40],
            "group_id": (b.get("groupId") or "").strip()[:64],
            "note": (b.get("note") or "").strip()[:200],
            "active": bool(b.get("active", True)),
            # ติ๊กออก = ผู้บริหาร/ไม่ต้องเช็คชื่อ → ไม่โผล่ในพาเนลเช็คชื่อเลย
            "track_checkin": bool(b.get("trackCheckin", True)),
            # ติ๊ก = ถูกแท็กในข้อความรอบสาย (แทน MANAGERS ที่ n8n ฝัง userId ไว้ในโค้ด)
            "notify_missing": bool(b.get("notifyMissing", False)),
        }
        row = Employee.objects.filter(pk=b.get("id") or 0).first()
        if row:
            if nick != row.nickname and Employee.objects.filter(nickname=nick).exists():
                return JsonResponse({"ok": False, "error": "ชื่อเล่นนี้มีอยู่แล้ว"}, status=400,
                                    json_dumps_params={"ensure_ascii": False})
            row.nickname = nick
            for k, v in fields.items():
                setattr(row, k, v)
            row.save()
        else:
            if Employee.objects.filter(nickname=nick).exists():
                return JsonResponse({"ok": False, "error": "ชื่อเล่นนี้มีอยู่แล้ว"}, status=400,
                                    json_dumps_params={"ensure_ascii": False})
            Employee.objects.create(nickname=nick, source=Employee.MANUAL, **fields)

    rows = []
    for e in Employee.objects.all().prefetch_related("line_accounts"):
        rows.append({
            "id": e.pk, "nickname": e.nickname, "displayName": e.display_name,
            "position": e.position, "workStart": e.work_start, "dayOff": e.day_off,
            "groupId": e.group_id, "note": e.note, "active": e.active,
            "trackCheckin": e.track_checkin, "notifyMissing": e.notify_missing,
            "fromSheet": e.source == Employee.SHEET,
            # ระบบเพิ่มให้เองตอนเจอในกลุ่ม + ยังไม่มีใครมากรอกตำแหน่ง/เวลา = ต้องมีคนตามเติม
            "needsInfo": e.source == Employee.AUTO and not (e.position and e.work_start),
            # จำนวนบัญชี LINE ที่ผูกไว้ — **ไม่ส่ง id ออกไป**
            "lineAccounts": len(list(e.line_accounts.all())),
        })
    return JsonResponse({"ok": True, "count": len(rows), "employees": rows},
                        json_dumps_params={"ensure_ascii": False})


def api_checkins(request):
    """เช็คชื่อเข้างานรายวัน — GET `?date=YYYY-MM-DD` (ไม่ใส่ = วันนี้ โซนไทย) — ★ 16 ก.ย.69

    เจ้าของสั่งย้ายจากชีต "เช็คชื่อ" มาเก็บใน Postgres: *"มันเป็นการเก็บทุกๆ วันอยู่แล้ว
    ไม่ต้องมานั่งลบข้อมูลแบบเดิม"* → n8n เขียนลง `checkout_checkin` หน้านี้อ่านมาโชว์

    `?from=&to=` = **โหมดสรุปช่วง** — รายคน: มากี่วัน · สายกี่ครั้ง · มาเฉลี่ยกี่โมง (เรียงคนสายบ่อยขึ้นก่อน)

    คืน 3 ก้อน: **มาแล้ว** (ตรงเวลา/สาย) · **ยังไม่เช็คชื่อ** · **วันหยุดของคนนั้น**
    — "ยังไม่เช็คชื่อ" ตัดคนที่วันนี้ตรงกับวันหยุดในทะเบียนออก ไม่งั้นจะขึ้นแดงทั้งที่เขาหยุดจริง

    ★ **คนที่ติ๊ก "ไม่ต้องเช็คชื่อ" (ผู้บริหาร) ไม่นับในหน้านี้เลย** — ไม่อยู่ในยอด "ต้องมา"
      และไม่ขึ้นค้างในกลุ่มยังไม่เช็คชื่อ/ยังไม่ได้ตั้งเวลา (เจ้าของสั่ง 16 ก.ย.69)
      แต่ถ้าเขาเช็คชื่อเข้ามาจริง **แถวนั้นยังโชว์** — ข้อมูลที่มีอยู่แล้วไม่ซ่อน
    """
    if not _admin(request):
        return JsonResponse({"ok": False, "error": "ต้อง login admin"}, status=401)
    from datetime import date as _date
    from .models import CheckIn, Employee

    today = timezone.localdate()

    # ── โหมดสรุปช่วง: ?from=&to= — "ใครมากี่วัน สายกี่ครั้ง มาเฉลี่ยกี่โมง" ──
    f_raw, t_raw = (request.GET.get("from") or "").strip(), (request.GET.get("to") or "").strip()
    if f_raw or t_raw:
        def _d(v, default):
            try:
                return _date.fromisoformat(v)
            except ValueError:
                return default
        d_to = _d(t_raw, today)
        d_from = _d(f_raw, d_to.replace(day=1))
        if d_from > d_to:
            d_from, d_to = d_to, d_from

        agg = {}
        for c in (CheckIn.objects.filter(date_iso__gte=d_from, date_iso__lte=d_to)
                  .select_related("employee").order_by("date_iso")):
            key = c.employee_id or ("uid:" + c.user_id)
            a = agg.setdefault(key, {
                "name": (c.employee.nickname if c.employee_id and c.employee else "") or c.display_name or "ไม่ทราบชื่อ",
                "position": (c.employee.position if c.employee_id and c.employee else ""),
                "linked": bool(c.employee_id),
                "days": 0, "ontime": 0, "late": 0, "abnormal": 0, "_mins": [], "last": ""})
            a["days"] += 1
            a[c.status if c.status in ("ontime", "late", "abnormal") else "abnormal"] += 1
            a["last"] = c.date_iso.isoformat()
            m = (c.time_hm or "").split(":")
            if len(m) == 2 and m[0].isdigit() and m[1].isdigit():
                a["_mins"].append(int(m[0]) * 60 + int(m[1]))

        rows = []
        for a in agg.values():
            mins = a.pop("_mins")
            if mins:
                avg = sum(mins) // len(mins)
                a["avgTime"] = "%02d:%02d" % (avg // 60, avg % 60)
            else:
                a["avgTime"] = ""
            rows.append(a)
        rows.sort(key=lambda r: (-r["late"], -r["days"], r["name"]))
        n_emp = Employee.objects.filter(active=True, track_checkin=True).count()
        return JsonResponse({"ok": True, "mode": "range", "from": d_from.isoformat(), "to": d_to.isoformat(),
                             "rows": rows, "employees": n_emp},
                            json_dumps_params={"ensure_ascii": False})

    raw = (request.GET.get("date") or "").strip()
    try:
        day = _date.fromisoformat(raw) if raw else today
    except ValueError:
        day = today

    # ชื่อวันภาษาไทย — ใช้เทียบกับช่อง "วันหยุด" ในทะเบียน (เก็บเป็นคำ เช่น "อาทิตย์")
    THAI_DAYS = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
    day_name = THAI_DAYS[day.weekday()]

    rows, seen_emp = [], set()
    for c in (CheckIn.objects.filter(date_iso=day).select_related("employee")
              .order_by("time_hm", "id")):
        if c.employee_id:
            seen_emp.add(c.employee_id)
        rows.append({
            "name": (c.employee.nickname if c.employee_id and c.employee else "") or c.display_name or "ไม่ทราบชื่อ",
            "position": (c.employee.position if c.employee_id and c.employee else ""),
            "timeHm": c.time_hm, "workStart": c.work_start,
            "status": c.status, "reason": c.reason,
            "timeSource": c.time_source, "address": c.full_address,
            "linked": bool(c.employee_id),   # ยังจับคู่กับทะเบียนไม่ได้ = ต้องไปผูกชื่อ
        })

    missing, dayoff = [], []
    for e in (Employee.objects.filter(active=True, track_checkin=True)
              .order_by("position", "nickname")):
        if e.id in seen_emp:
            continue
        item = {"name": e.nickname, "position": e.position, "workStart": e.work_start,
                "dayOff": e.day_off, "note": e.note}
        (dayoff if (e.day_off and day_name in e.day_off) else missing).append(item)

    n = {"ontime": sum(1 for r in rows if r["status"] == "ontime"),
         "late": sum(1 for r in rows if r["status"] == "late"),
         "abnormal": sum(1 for r in rows if r["status"] == "abnormal")}
    return JsonResponse({"ok": True, "date": day.isoformat(), "dayName": day_name,
                         "isToday": day == today, "counts": n,
                         "rows": rows, "missing": missing, "dayoff": dayoff,
                         "employees": Employee.objects.filter(active=True, track_checkin=True).count()},
                        json_dumps_params={"ensure_ascii": False})


def api_checkin_config(request):
    """ตั้งค่าส่งตารางเช็คชื่อเข้าไลน์ — ★ 17 ก.ย.69 (เจ้าของขอ "ขอหน้า URL ตั้งค่า ดิฉันตั้งเอง")

      GET  → ค่าปัจจุบัน + กลุ่มที่บอทตัวส่งอยู่ + ใครจะถูกแท็ก + แท็กได้กี่คน
      POST → บันทึก `{enabled, tableTime, escalateTime, mode, groupId, testId, maxTag, holidays}`
      POST `{action:"test", round:"table"|"escalate"}` → ส่งทดสอบเดี๋ยวนี้

    **ส่งด้วยบอทตัวส่ง (OxletautoGiveLead) เสมอ** — ดู `checkin_report.bot()`
    """
    if not _admin(request):
        return JsonResponse({"ok": False, "error": "ต้อง login admin/ผู้บริหาร"}, status=401,
                            json_dumps_params={"ensure_ascii": False})
    from . import checkin_report as R

    if request.method == "POST":
        try:
            b = json.loads(request.body or "{}")
        except Exception:
            b = {}

        if b.get("action") == "test":
            cfg = R.config()
            target = cfg["test_id"] if cfg.get("mode") == "test" else cfg["group_id"]
            if not target:
                return JsonResponse({"ok": False, "error": "ยังไม่ได้ตั้งปลายทาง"}, status=400,
                                    json_dumps_params={"ensure_ascii": False})
            try:
                if b.get("round") == "escalate":
                    ok, msg = R.send_escalation(target)
                else:
                    ok, msg = R.send(target)
            except Exception as e:
                ok, msg = False, str(e)[:300]
            return JsonResponse({"ok": ok, "message": msg},
                                json_dumps_params={"ensure_ascii": False})

        def _hhmm(v):
            v = (v or "").strip()
            if not v:
                return ""
            m = re.match(r"^(\d{1,2}):(\d{2})$", v)
            return "%02d:%s" % (int(m.group(1)), m.group(2)) if m else ""

        try:
            cap = max(0, int(b.get("maxTag") or 0))
        except (TypeError, ValueError):
            cap = 20
        hol = []
        for d in (b.get("holidays") or []):
            d = str(d or "").strip()
            try:
                from datetime import date as _d
                hol.append(_d.fromisoformat(d).isoformat())
            except ValueError:
                continue
        R.save_config({
            "enabled": bool(b.get("enabled")),
            "table_time": _hhmm(b.get("tableTime")),
            "escalate_time": _hhmm(b.get("escalateTime")),
            "mode": "group" if b.get("mode") == "group" else "test",
            "group_id": (b.get("groupId") or "").strip()[:64],
            "test_id": (b.get("testId") or "").strip()[:64],
            "max_tag": cap,
            "holidays": sorted(set(hol)),
        })

    cfg = R.config()
    bot = R.bot()
    data = R.collect()
    ok_n, all_n, no_tag = R.tag_coverage(data["missing"], bot["key"])
    mgrs = R.managers(bot["key"])

    # กลุ่มที่ "บอทตัวส่ง" อยู่จริงเท่านั้น — กันเลือกกลุ่มของบอทเก่าแล้วส่งไม่ออก
    groups = []
    try:
        from dashboard.services import cache_store
        from dashboard.services.line_channels import group_visible_to_push
        reg = (cache_store.get_kv("line_groups") or {}).get("data") or {}
        for gid, v in reg.items():
            v = v or {}
            if group_visible_to_push(v):
                groups.append({"id": gid, "name": v.get("name") or gid})
        groups.sort(key=lambda g: g["name"])
    except Exception:
        groups = []

    return JsonResponse({
        "ok": True,
        "config": {"enabled": cfg["enabled"], "tableTime": cfg["table_time"],
                   "escalateTime": cfg["escalate_time"], "mode": cfg["mode"],
                   "groupId": cfg["group_id"], "testId": cfg["test_id"],
                   "maxTag": cfg.get("max_tag", 20), "holidays": cfg.get("holidays") or []},
        "bot": {"name": bot["name"], "separate": bot["ok"]},
        "groups": groups,
        "today": {"date": data["date"].isoformat(), "dayName": data["dayName"],
                  "total": data["counts"]["total"], "missing": data["counts"]["missing"]},
        "tag": {"can": ok_n, "all": all_n, "cannot": no_tag[:20]},
        "managers": [{"name": m["name"], "canTag": bool(m["userId"])} for m in mgrs],
    }, json_dumps_params={"ensure_ascii": False})


def api_customers(request):
    """ลูกค้าที่ทักเข้า LINE OA — `?q=` ค้นหา · `?user_id=` ดูบทสนทนาของคนนั้น

    **ไม่ใช่หน้าตั้งค่า** — อ่านอย่างเดียว ไว้ดูว่าใครทักมา ทักว่าอะไร และคัดลอก id ไปทักกลับ

    ★ กติกา LINE user id: **ลูกค้าโชว์ได้** (เจ้าของขอไว้ทักกลับ · push ต้องใช้ id) แต่
      **พนักงานที่ทักเข้า OA ต้องไม่โชว์ id** — เช็คจาก `LineProfile.is_employee`
    """
    if not _admin(request):
        return JsonResponse({"ok": False, "error": "ต้อง login admin/ผู้บริหาร"}, status=401,
                            json_dumps_params={"ensure_ascii": False})
    from django.db.models import Count, Max
    from .models import LineProfile

    uid = (request.GET.get("user_id") or "").strip()
    base = GroupChat.objects.exclude(chat_type=GroupChat.GROUP)   # 1:1 + ห้องคุย = ไม่ใช่กลุ่มงาน

    # ── บทสนทนาของคนเดียว ──
    if uid:
        prof = LineProfile.objects.filter(user_id=uid).first()
        rows = list(base.filter(sender_id=uid).order_by("-sent_at", "-id")[:CUST_MSG_MAX])
        rows.reverse()                                            # เก่า → ใหม่ (อ่านเป็นบทสนทนา)
        emp = bool(prof and prof.is_employee)
        return JsonResponse({
            "ok": True,
            "person": {
                "name": (prof.show_name if prof else "") or (rows[-1].sender_name if rows else "") or "(ไม่รู้ชื่อ)",
                "userId": "" if emp else uid,                     # พนักงาน = ไม่ส่ง id ออก
                "isEmployee": emp,
                "status": (prof.status_message if prof else "") or "",
                "msgCount": prof.msg_count if prof else len(rows),
                "first": (timezone.localtime(prof.first_seen).strftime("%d/%m/%y %H:%M")
                          if prof and prof.first_seen else ""),
                "channel": (prof.channel if prof else "") or "",
                "channels": list(prof.channels or []) if prof else [],
            },
            "messages": [{
                "at": timezone.localtime(g.sent_at).strftime("%d/%m %H:%M") if g.sent_at else "",
                "text": _msg_preview(g),
                "type": g.msg_type or "",
                "media": bool(g.has_media),
                "channel": g.channel or "",
                # ★ ก.ย.69 — ฝั่งไหนพูด + ใครเป็นคนตอบ (หน้าเว็บวางซ้าย/ขวาจากตรงนี้)
                "dir": g.direction or "in",
                "by": g.sent_by_name or "",
            } for g in rows],
            "canReply": bool(uid) and not emp,
            # ★ สวิตช์ล็อกการส่งจริง — หน้าเว็บต้องรู้ เพื่อบอกผู้ใช้ว่าทำไมส่งไม่ได้
            "replyOn": __import__("checkout.chat", fromlist=["chat"]).reply_on(),
            "limit": CUST_MSG_MAX,
        }, json_dumps_params={"ensure_ascii": False})

    # ── รายชื่อลูกค้า ──
    q = (request.GET.get("q") or "").strip()
    agg = (base.values("sender_id", "sender_name")
           .annotate(n=Count("id"), last=Max("sent_at")).order_by("-last"))
    if q:
        agg = agg.filter(sender_name__icontains=q)
    rows = list(agg[:CUST_LIST_MAX])
    profs = {p.user_id: p for p in LineProfile.objects.filter(
        user_id__in=[r["sender_id"] for r in rows if r["sender_id"]])}
    out = []
    for r in rows:
        pr = profs.get(r["sender_id"])
        emp = bool(pr and pr.is_employee)
        d = _cust_row(r, pr)
        if emp:                       # พนักงานทักเข้า OA — เก็บไว้ดูได้ แต่ห้ามโชว์ id
            d["userId"] = ""
        d["isEmployee"] = emp
        d["channel"] = (pr.channel if pr else "") or ""
        out.append(d)

    totals = {
        "people": base.values("sender_id").distinct().count(),
        "messages": base.count(),
        "keepDays": C.CUSTOMER_CHAT_KEEP_DAYS,
        "storeOn": bool(line_cfg().get("store_customer_chat")),
    }
    # แยกตามบัญชี OA ที่ได้ยิน — เห็นทันทีว่าลูกค้าเข้ามาทางตัวไหนบ้าง (รองรับหลาย OA)
    by_channel = {(r["channel"] or "(ไม่ทราบ)"): r["n"] for r in
                  base.values("channel").annotate(n=Count("id")).order_by("-n")}
    return JsonResponse({"ok": True, "totals": totals, "byChannel": by_channel,
                         "customers": out, "shown": len(out), "max": CUST_LIST_MAX},
                        json_dumps_params={"ensure_ascii": False})


@csrf_exempt
def api_reply(request):
    """**ตอบแชทลูกค้า** — POST `{user_id, text}` · admin/ผู้บริหารเท่านั้น

    ★ ก.ย.69 เจ้าของสั่งทำหน้าตอบแชท · ดู [chat.py](chat.py) สำหรับกติกาการเลือกบัญชี OA
      และเหตุผลที่ต้องเก็บข้อความขาออกลงฐานข้อมูลด้วย (= ข้อมูลสอน chatbot)

    `csrf_exempt` เพราะพาเนลอยู่ในหน้าแดชบอร์ดที่โพสต์ JSON แบบเดียวกับ endpoint อื่นของไฟล์นี้
    — ตัวกันจริงคือ `_admin()` ที่เช็ค session ฝั่งขาย
    """
    actor = _admin(request)
    if not actor:
        return JsonResponse({"ok": False, "error": "ต้อง login admin/ผู้บริหาร"}, status=401,
                            json_dumps_params={"ensure_ascii": False})
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "ต้องเป็น POST"}, status=405,
                            json_dumps_params={"ensure_ascii": False})
    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        body = {}
    uid = (body.get("user_id") or "").strip()
    text = (body.get("text") or "").strip()

    from .chat import ReplyError, send_reply
    try:
        row = send_reply(uid, text, actor)
    except ReplyError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400,
                            json_dumps_params={"ensure_ascii": False})
    except Exception as e:                      # เน็ตล่ม/LINE ไม่ตอบ — อย่าคืน 500 เปล่าๆ
        return JsonResponse({"ok": False, "error": "ส่งไม่สำเร็จ: %s" % e}, status=502,
                            json_dumps_params={"ensure_ascii": False})

    return JsonResponse({"ok": True, "message": {
        "at": timezone.localtime(row.sent_at).strftime("%d/%m %H:%M"),
        "text": row.text, "dir": "out", "by": row.sent_by_name or "",
    }}, json_dumps_params={"ensure_ascii": False})


def api_needs(request):
    """**ความต้องการลูกค้า** — ใครหารถอะไร งบเท่าไหร่ ใครรอรถอยู่ (admin/ผู้บริหาร)

    `?waiting=1` = เฉพาะคนที่รอรถ · `?match=1` = แนบรถในสต็อกที่ตรงสเปกมาด้วย

    ★ ก.ย.69 — **อ่านอย่างเดียว ไม่มีการส่งข้อความหาลูกค้าจากหน้านี้**
      รายการนี้ไว้ให้คนของเราเห็นว่า "มีของให้เสนอแล้วนะ" แล้วตัดสินใจทักเอง
    """
    if not _admin(request):
        return JsonResponse({"ok": False, "error": "ต้อง login admin/ผู้บริหาร"}, status=401,
                            json_dumps_params={"ensure_ascii": False})
    from .models import CustomerNeed

    qs = CustomerNeed.objects.select_related("profile").order_by("-updated_at")
    if request.GET.get("waiting"):
        qs = qs.filter(waiting=True)
    rows = list(qs[:300])

    # จับคู่สต็อกทีเดียวสำหรับทุกแถว — อ่านรถครั้งเดียว ไม่ยิงต่อแถว
    hits = {}
    if request.GET.get("match"):
        try:
            from . import need_match
            stock = need_match._stock()
            for n in rows:
                m = need_match.matches_for(n, stock)
                if m:
                    hits[n.pk] = m[:3]
        except Exception:
            hits = {}                       # ระบบรถล่ม/ยังไม่ต่อ DB = ยังดูรายการได้ตามปกติ

    def one(n):
        p = n.profile                       # ว่างได้ — เคสจากกลุ่มจ่ายเบอร์ไม่มีโปรไฟล์ LINE
        return {
            "id": n.pk,
            "name": n.who,
            "userId": "" if (not p or p.is_employee) else p.user_id,
            "leadCode": n.lead_code or "",
            "source": n.source,
            "contact": n.contact or "",
            "channel": n.channel or "",
            "want": n.car_model or n.car_text or "",
            "carText": n.car_text or "",
            "budget": n.budget_max, "budgetMin": n.budget_min,
            "monthly": n.monthly_max, "down": n.down_max,
            "yearMin": n.car_year_min, "yearMax": n.car_year_max,
            "status": n.status, "statusName": n.get_status_display(),
            "rejectKind": n.reject_kind,
            "rejectName": n.get_reject_kind_display() if n.reject_kind else "",
            "waiting": n.waiting,
            "confidence": n.confidence or "",
            "evidence": n.evidence or "",
            "seller": n.seller or "",
            "at": timezone.localtime(n.updated_at).strftime("%d/%m/%y %H:%M"),
            "cars": [{"code": c["code"], "name": ("%s %s" % (c["brand"], c["model"])).strip(),
                      "year": c["year"], "price": c["price"]} for c in hits.get(n.pk, [])],
        }

    all_q = CustomerNeed.objects.all()
    return JsonResponse({
        "ok": True,
        "needs": [one(n) for n in rows],
        "totals": {
            "all": all_q.count(),
            "waiting": all_q.filter(waiting=True).count(),
            "matched": len(hits),
        },
        # นับ RJ แยกเหตุผล — เห็นทันทีว่าที่เสียไปเป็นเพราะ "ของขาด" หรือ "คนไม่เอา"
        "byReject": {lbl: all_q.filter(reject_kind=k).count()
                     for k, lbl in CustomerNeed.REJECT_CHOICES if k},
        "waitable": [lbl for k, lbl in CustomerNeed.REJECT_CHOICES
                     if k in CustomerNeed.WAITABLE],
    }, json_dumps_params={"ensure_ascii": False})


def chat_stats():
    """สรุปคลังแชทสำหรับพาเนลตั้งค่า — {total, groups:[{id,name,n,last}], media}"""
    from django.db.models import Count, Max
    rows = (GroupChat.objects.filter(chat_type=GroupChat.GROUP)
            .values("group_id", "group_name")
            .annotate(n=Count("id"), last=Max("sent_at")).order_by("-n")[:10])
    cust = GroupChat.objects.exclude(chat_type=GroupChat.GROUP)
    cust_rows = list(cust.values("sender_id", "sender_name")
                     .annotate(n=Count("id"), last=Max("sent_at")).order_by("-last")[:8])
    # ★ ก.ย.69 — ต่อโปรไฟล์เข้ามาด้วย (รูป + ทักครั้งแรกเมื่อไหร่) · ดึงทีเดียวไม่ยิงต่อแถว
    profs = {}
    try:
        from .models import LineProfile
        profs = {p.user_id: p for p in LineProfile.objects.filter(
            user_id__in=[r["sender_id"] for r in cust_rows if r["sender_id"]])}
    except Exception:
        profs = {}
    return {
        "total": GroupChat.objects.count(),
        "media": GroupChat.objects.filter(has_media=True).count(),
        "keepDays": C.CHAT_KEEP_DAYS,
        "custKeepDays": C.CUSTOMER_CHAT_KEEP_DAYS,
        "custTotal": cust.count(),
        "custPeople": cust.values("sender_id").distinct().count(),
        "profiles": _profile_counts(),
        # ★ กติกาเรื่อง LINE user id (ก.ย.69 · ปรับตามที่เจ้าของสั่งเพิ่ม):
        #   - **พนักงาน** = ห้ามโชว์ id เด็ดขาด (โชว์ชื่อเล่นอย่างเดียว) — ของเดิม
        #   - **ลูกค้า** = ส่ง id ออกได้ เพราะเจ้าของขอไว้ใช้ "ทักกลับหาลูกค้า" (push ต้องใช้ id)
        #     และคนที่เห็นหน้านี้มีแค่ admin/ผู้บริหารอยู่แล้ว
        "customers": [_cust_row(r, profs.get(r["sender_id"])) for r in cust_rows],
        "groups": [{"id": r["group_id"], "name": r["group_name"] or "",
                    "n": r["n"],
                    "last": timezone.localtime(r["last"]).strftime("%d/%m %H:%M") if r["last"] else ""}
                   for r in rows],
    }
