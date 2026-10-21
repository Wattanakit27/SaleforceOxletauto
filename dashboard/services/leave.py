"""ลา + ปฏิทินเข้างาน — ★ 21 ต.ค.69 (เจ้าของสั่ง · แอปมือถือ หมวดหน้าหลัก: ลงเวลา · ปฏิทิน · ลา · แบบแอป HumanOS)

*"แยกหน้า dashboard ออกจากหน้าเช็กชื่อด้วย จะแทนที่ด้วยปฏิทิน และวันลา"*

- **ลา** (`dashboard.LeaveRequest`): พนักงานยื่นในแอป → แอดมิน/ผู้บริหาร (position admin) อนุมัติ/ไม่อนุมัติในแอป
  · ยื่นได้ย้อนหลังไม่เกิน `BACK_DAYS` (ลาป่วยมาแจ้งทีหลัง) · ล่วงหน้าไม่เกิน `AHEAD_DAYS` · ช่วงเดียวยาวไม่เกิน `MAX_SPAN`
  · ครึ่งวันได้เฉพาะลาวันเดียว · ช่วงที่ทับคำขอเดิม (รออนุมัติ/อนุมัติแล้ว) = ปฏิเสธ
  · `days` ตัดวันหยุดประจำสัปดาห์ของคนนั้น (ช่อง "วันหยุด" ในทะเบียน) + วันหยุดบริษัท (KV `checkin_notify_config.holidays`)
  · คนยื่นยกเลิกได้เฉพาะที่ยังรออนุมัติ · แอดมินยกเลิกที่อนุมัติไปแล้วได้
  · **ไม่ส่งอะไรเข้า LINE** · จด `dash_event_log` kind=`leave`
- **ปฏิทิน** (`month_view`): รายวันของเดือน — เข้างาน/ออกงาน/สาย (ตาราง `checkout_checkin` · แถวแรกของวันตาม
  `checkin_app.first_per_employee`) · ลา · วันหยุด · ขาด (วันทำงานที่ผ่านไปแล้วไม่มีเช็คชื่อและไม่ได้ลา)
  · แอดมินเห็น "ใครลาวันไหน" ของทั้งบริษัทด้วย (`team`)
- ⚠️ ตารางเช็คชื่อที่ส่งเข้า LINE (checkout/checkin_report) ยังไม่อ่านวันลาจากตารางนี้
"""
import datetime as dt
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

BACK_DAYS = 30
AHEAD_DAYS = 180
MAX_SPAN = 60
REASON_MAX = 500
KIND_NAME = {"sick": "ลาป่วย", "personal": "ลากิจ", "vacation": "ลาพักร้อน", "other": "ลาอื่นๆ"}
HALF_NAME = {"": "เต็มวัน", "am": "ครึ่งวันเช้า", "pm": "ครึ่งวันบ่าย"}
STATUS_NAME = {"pending": "รออนุมัติ", "approved": "อนุมัติแล้ว", "rejected": "ไม่อนุมัติ", "cancelled": "ยกเลิกแล้ว"}
TH_DOW = ["จันทร์", "อังคาร", "พุธ", "พฤหัส", "ศุกร์", "เสาร์", "อาทิตย์"]   # date.weekday() 0 = จันทร์
# คำในช่อง "วันหยุด" — คำย่อที่อยู่ในชื่อเต็มเสมอ (เขียนย่อ/เต็มก็ตรงทั้งคู่ · "พฤหัส" ⊂ "พฤหัสบดี")
_DOW_KEYS = ["จันทร์", "อังคาร", "พุธ", "พฤหัส", "ศุกร์", "เสาร์", "อาทิตย์"]


def _M():
    from dashboard.models import LeaveRequest
    return LeaveRequest


def is_day_off(day_off: str, day: dt.date) -> bool:
    """วันนี้เป็นวันหยุดประจำสัปดาห์ของคนนี้ไหม (ช่อง "วันหยุด" ในทะเบียน · เขียนได้หลายวันในช่องเดียว)"""
    txt = day_off or ""
    if not txt.strip():
        return False
    return _DOW_KEYS[day.weekday()] in txt


def holidays() -> set:
    """วันหยุดบริษัท (YYYY-MM-DD) — ชุดเดียวกับที่ตารางเช็คชื่อใช้งดส่ง"""
    from dashboard.services import cache_store
    try:
        v = cache_store.get_kv("checkin_notify_config") or {}
        v = v.get("data", v) if isinstance(v, dict) else {}
        return {str(x) for x in (v.get("holidays") or [])}
    except Exception:
        return set()


def _days(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        yield d
        d += dt.timedelta(days=1)


def count_days(emp, start: dt.date, end: dt.date, half: str = "", hol=None) -> Decimal:
    """จำนวนวันลาจริง — ตัดวันหยุดประจำสัปดาห์ + วันหยุดบริษัท · ครึ่งวัน = 0.5"""
    hol = holidays() if hol is None else hol
    n = 0
    for d in _days(start, end):
        if is_day_off(getattr(emp, "day_off", ""), d) or d.isoformat() in hol:
            continue
        n += 1
    if half and n:
        return Decimal("0.5")
    return Decimal(n)


def _parse_date(v):
    try:
        return dt.date.fromisoformat(str(v or "").strip()[:10])
    except ValueError:
        return None


def row_json(r) -> dict:
    return {
        "id": r.pk, "nickname": r.nickname, "kind": r.kind, "kindName": KIND_NAME.get(r.kind, r.kind),
        "start": r.start_date.isoformat(), "end": r.end_date.isoformat(), "half": r.half,
        "halfName": HALF_NAME.get(r.half, ""), "days": float(r.days), "reason": r.reason,
        "status": r.status, "statusName": STATUS_NAME.get(r.status, r.status),
        "decidedBy": r.decided_by, "decidedAt": timezone.localtime(r.decided_at).isoformat(timespec="minutes") if r.decided_at else "",
        "decideNote": r.decide_note, "createdAt": timezone.localtime(r.created_at).isoformat(timespec="minutes"),
    }


def _log(name, target, ok=True, **detail):
    try:
        from dashboard.services import eventlog
        eventlog.log("leave", name=name, target=(target or "")[:64], ok=ok, **detail)
    except Exception:
        pass


# ─────────────────────────── ยื่น / อนุมัติ / ยกเลิก ───────────────────────────

def create(emp, by: str, data: dict) -> tuple:
    """ยื่นลา → (http_status, payload) · ผิดช่องไหนบอกช่องนั้น"""
    LR = _M()
    if not emp:
        return 403, {"ok": False, "error": "บัญชีนี้ยังไม่ผูกกับทะเบียนพนักงาน — แจ้งแอดมินให้เพิ่มชื่อเล่นในหน้าพนักงาน"}
    kind = str(data.get("kind") or "").strip()
    if kind not in KIND_NAME:
        return 400, {"ok": False, "error": "เลือกประเภทการลา"}
    start, end = _parse_date(data.get("start")), _parse_date(data.get("end") or data.get("start"))
    if not start or not end:
        return 400, {"ok": False, "error": "วันที่ไม่ถูกต้อง"}
    if end < start:
        return 400, {"ok": False, "error": "วันสุดท้ายต้องไม่ก่อนวันแรก"}
    today = timezone.localdate()
    if start < today - dt.timedelta(days=BACK_DAYS):
        return 400, {"ok": False, "error": "ยื่นลาย้อนหลังได้ไม่เกิน %d วัน" % BACK_DAYS}
    if end > today + dt.timedelta(days=AHEAD_DAYS):
        return 400, {"ok": False, "error": "ยื่นลาล่วงหน้าได้ไม่เกิน %d วัน" % AHEAD_DAYS}
    if (end - start).days + 1 > MAX_SPAN:
        return 400, {"ok": False, "error": "ลาครั้งเดียวได้ไม่เกิน %d วัน — แยกเป็นหลายคำขอ" % MAX_SPAN}
    half = str(data.get("half") or "").strip()
    if half not in HALF_NAME:
        return 400, {"ok": False, "error": "ช่วงเวลาไม่ถูกต้อง"}
    if half and start != end:
        return 400, {"ok": False, "error": "ลาครึ่งวันได้เฉพาะลาวันเดียว"}
    reason = str(data.get("reason") or "").strip()
    if len(reason) > REASON_MAX:
        return 400, {"ok": False, "error": "เหตุผลยาวเกิน %d ตัวอักษร" % REASON_MAX}
    days = count_days(emp, start, end, half)
    if days <= 0:
        return 400, {"ok": False, "error": "ช่วงที่เลือกเป็นวันหยุดทั้งหมด — ไม่ต้องยื่นลา"}
    with transaction.atomic():
        clash = (LR.objects.select_for_update()
                 .filter(employee=emp, status__in=[LR.PENDING, LR.APPROVED], start_date__lte=end, end_date__gte=start)
                 .order_by("start_date").first())
        if clash:
            return 400, {"ok": False, "error": "ช่วงนี้มี%s%sอยู่แล้ว (%s)" % (
                KIND_NAME.get(clash.kind, "คำขอลา"), STATUS_NAME.get(clash.status, ""),
                _range_text(clash.start_date, clash.end_date))}
        r = LR.objects.create(employee=emp, nickname=emp.nickname, kind=kind, start_date=start, end_date=end,
                              half=half, days=days, reason=reason, created_by=(by or emp.nickname)[:80])
    _log("ยื่นลา", emp.nickname, kind=kind, start=start.isoformat(), end=end.isoformat(), days=float(days))
    return 200, {"ok": True, "row": row_json(r),
                 "message": "ยื่น%s %s (%s วัน) แล้ว — รอแอดมินอนุมัติ" % (KIND_NAME[kind], _range_text(start, end), _num(days))}


def cancel(emp, by: str, rid, admin: bool) -> tuple:
    LR = _M()
    r = LR.objects.filter(pk=_int(rid)).first()
    if not r:
        return 404, {"ok": False, "error": "ไม่พบคำขอลานี้"}
    mine = emp is not None and r.employee_id == emp.pk
    if not (mine or admin):
        return 403, {"ok": False, "error": "ยกเลิกได้เฉพาะคำขอของตัวเอง"}
    if r.status == LR.PENDING or (admin and r.status == LR.APPROVED):
        r.status = LR.CANCELLED
        r.decided_by, r.decided_at = (by or "")[:80], timezone.now()
        r.save(update_fields=["status", "decided_by", "decided_at", "updated_at"])
        _log("ยกเลิกลา", r.nickname, by=by)
        return 200, {"ok": True, "row": row_json(r), "message": "ยกเลิกคำขอลาแล้ว"}
    if r.status == LR.APPROVED:
        return 400, {"ok": False, "error": "คำขอนี้อนุมัติแล้ว — แจ้งแอดมินให้ยกเลิกให้"}
    return 400, {"ok": False, "error": "คำขอนี้%sไปแล้ว" % STATUS_NAME.get(r.status, "")}


def decide(by: str, rid, approve: bool, note: str = "") -> tuple:
    """แอดมินอนุมัติ/ไม่อนุมัติ (เฉพาะที่ยังรออนุมัติ) — ผู้เรียกต้องเช็คสิทธิ์แอดมินก่อน"""
    LR = _M()
    with transaction.atomic():
        r = LR.objects.select_for_update().filter(pk=_int(rid)).first()
        if not r:
            return 404, {"ok": False, "error": "ไม่พบคำขอลานี้"}
        if r.status != LR.PENDING:
            return 400, {"ok": False, "error": "คำขอนี้%sไปแล้ว" % STATUS_NAME.get(r.status, "")}
        r.status = LR.APPROVED if approve else LR.REJECTED
        r.decided_by, r.decided_at = (by or "แอดมิน")[:80], timezone.now()
        r.decide_note = str(note or "").strip()[:300]
        r.save(update_fields=["status", "decided_by", "decided_at", "decide_note", "updated_at"])
    _log("อนุมัติลา" if approve else "ไม่อนุมัติลา", r.nickname, by=by)
    return 200, {"ok": True, "row": row_json(r),
                 "message": "%s %s ของ%s แล้ว" % ("อนุมัติ" if approve else "ไม่อนุมัติ", KIND_NAME.get(r.kind, "การลา"), r.nickname)}


def overview(emp, admin: bool, year: int = None) -> dict:
    """หน้า "ลา" ในแอป — คำขอของฉัน + สรุปวันลาปีนี้ (แยกประเภท · นับเฉพาะที่อนุมัติ) + แอดมิน: รออนุมัติ/ลาวันนี้"""
    LR = _M()
    today = timezone.localdate()
    year = year or today.year
    out = {"ok": True, "linked": bool(emp), "admin": admin, "year": year,
           "kinds": [{"key": k, "name": v} for k, v in KIND_NAME.items()],
           "halves": [{"key": k, "name": v} for k, v in HALF_NAME.items()],
           "limits": {"backDays": BACK_DAYS, "aheadDays": AHEAD_DAYS, "maxSpan": MAX_SPAN}}
    if emp:
        mine = list(LR.objects.filter(employee=emp).order_by("-start_date", "-id")[:60])
        out["mine"] = [row_json(r) for r in mine]
        used = {k: 0.0 for k in KIND_NAME}
        for r in LR.objects.filter(employee=emp, status=LR.APPROVED, start_date__year=year):
            used[r.kind] = used.get(r.kind, 0.0) + float(r.days)
        out["used"] = used
        out["dayOff"] = getattr(emp, "day_off", "") or ""
    if admin:
        out["pending"] = [row_json(r) for r in LR.objects.filter(status=LR.PENDING).order_by("start_date", "id")[:100]]
        out["today"] = [row_json(r) for r in LR.objects.filter(status=LR.APPROVED, start_date__lte=today,
                                                               end_date__gte=today).order_by("nickname")]
        out["recent"] = [row_json(r) for r in LR.objects.exclude(status=LR.PENDING)
                         .filter(updated_at__gte=timezone.now() - dt.timedelta(days=30)).order_by("-updated_at")[:40]]
    return out


# ─────────────────────────── ปฏิทิน ───────────────────────────

def month_view(emp, ym: str, admin: bool = False) -> dict:
    """ปฏิทินเดือน YYYY-MM ของคนนี้ → {days: [...], summary, team?}"""
    from checkout.checkin_app import OUT_KEY, first_per_employee, status_for
    from checkout.models import CheckIn
    LR = _M()
    today = timezone.localdate()
    try:
        y, m = (int(x) for x in (ym or "").split("-")[:2])
        first = dt.date(y, m, 1)
    except (TypeError, ValueError):
        first = today.replace(day=1)
    last = (first.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
    hol = holidays()
    out = {"ok": True, "linked": bool(emp), "month": first.strftime("%Y-%m"), "today": today.isoformat(),
           "first": first.isoformat(), "last": last.isoformat(), "days": []}

    ci_by_day, leaves = {}, []
    if emp:
        rows = list(CheckIn.objects.filter(employee=emp, date_iso__gte=first, date_iso__lte=last))
        by = {}
        for c in rows:
            by.setdefault(c.date_iso, []).append(c)
        for d, cs in by.items():
            ci_by_day[d] = first_per_employee(cs)[0]
        leaves = list(LR.objects.filter(employee=emp, status__in=[LR.PENDING, LR.APPROVED],
                                        start_date__lte=last, end_date__gte=first))
    started = timezone.localtime(emp.created_at).date() if emp and getattr(emp, "created_at", None) else first
    summ = {"ontime": 0, "late": 0, "absent": 0, "leave": 0.0, "work": 0, "pending": 0}
    for d in _days(first, last):
        item = {"date": d.isoformat(), "dow": d.weekday(), "state": "none"}
        off = bool(emp) and is_day_off(emp.day_off, d)
        holiday = d.isoformat() in hol
        if off:
            item["dayoff"] = True
        if holiday:
            item["holiday"] = True
        c = ci_by_day.get(d)
        if c:
            st, late = status_for(c.time_hm, c.work_start or emp.work_start)
            st = c.status or st
            o = (c.raw or {}).get(OUT_KEY) or {}
            item["checkin"] = {"time": c.time_hm, "status": st, "lateMin": late if st == "late" else 0,
                               "out": o.get("hm", "") if isinstance(o, dict) else ""}
        lv = next((r for r in leaves if r.start_date <= d <= r.end_date), None)
        if lv:
            item["leave"] = {"id": lv.pk, "kind": lv.kind, "kindName": KIND_NAME.get(lv.kind, lv.kind),
                             "status": lv.status, "half": lv.half}
        # สถานะรวมของวัน (สีในปฏิทิน) — มาทำงาน > ลา > วันหยุด > ขาด
        if c:
            item["state"] = "late" if item["checkin"]["status"] == "late" else "ontime"
            summ["late" if item["state"] == "late" else "ontime"] += 1
            summ["work"] += 1
        elif lv and lv.status == LR.APPROVED and not off and not holiday:
            item["state"] = "leave"
            summ["leave"] += 0.5 if lv.half else 1.0
        elif lv and lv.status == LR.PENDING and not off and not holiday:
            item["state"] = "leavePending"
            summ["pending"] += 1
        elif holiday:
            item["state"] = "holiday"
        elif off:
            item["state"] = "dayoff"
        elif d > today:
            item["state"] = "future"
        elif emp and emp.track_checkin and started <= d < today:
            item["state"] = "absent"
            summ["absent"] += 1
        out["days"].append(item)
    out["summary"] = summ
    if emp:
        out["workStart"] = emp.work_start or ""
        out["dayOff"] = emp.day_off or ""
        out["track"] = bool(emp.track_checkin)
    if admin:
        team = {}
        for r in LR.objects.filter(status__in=[LR.PENDING, LR.APPROVED], start_date__lte=last, end_date__gte=first):
            for d in _days(max(r.start_date, first), min(r.end_date, last)):
                team.setdefault(d.isoformat(), []).append({"nickname": r.nickname, "kindName": KIND_NAME.get(r.kind, ""),
                                                           "status": r.status, "half": r.half})
        out["team"] = team
    return out


# ─────────────────────────── ตัวช่วย ───────────────────────────

def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _num(d) -> str:
    f = float(d)
    return str(int(f)) if f == int(f) else ("%.1f" % f)


_TH_MON = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]


def _d(d: dt.date) -> str:
    return "%d %s" % (d.day, _TH_MON[d.month - 1])


def _range_text(a: dt.date, b: dt.date) -> str:
    return _d(a) if a == b else "%s – %s" % (_d(a), _d(b))
