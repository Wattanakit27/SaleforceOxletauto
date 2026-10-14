"""หน้า "วันนี้" ของแอปมือถือ — ข้อมูลจริงก้อนเดียวต่อบทบาท (★ 11 ต.ค.69)

ต้นแบบแอป (oxlet-mobile-demo) ใช้ข้อมูลสมมติ · ตัวนี้ประกอบข้อมูลจริงฝั่งเซิร์ฟเวอร์จาก **ของที่มีอยู่แล้ว**
ไม่มีสูตรใหม่สักตัว — แยกสูตรเมื่อไหร่ ตัวเลขในแอปกับบนเว็บ/ในข้อความ LINE จะไม่ตรงกันแล้วไม่มีใครรู้ว่าอันไหนถูก:

  ตามด่วน/ดีลค้าง = fetch_dashboard.seller_followups (สูตรเดียวกับข้อความ "ตามด่วน" ทุกเช้า)
  ยอดเดือนนี้      = monthlySummary ที่ cron อุ่นไว้ (ชุดเดียวกับตารางในแดชบอร์ด)
  คะแนนเซลล์      = compute_diligence_scores (ตารางคะแนนเดียวกับหน้าเซลล์)
  ใบจ่ายลีด        = leadflow.seller_tasks (ตัวเดียวกับ /api/seller/today)
  งานจัดซื้อ        = purchase_page.summary (ตัวเดียวกับ /buy/ และข้อความ LINE ห้องเคสHOT)

ทุกส่วนห่อ try แยก — ส่วนหนึ่งพังต้องไม่ทำให้ทั้งหน้าขาว (ส่วนนั้นขึ้นใน `errors` แทน) · ไม่ส่ง LINE user id ออก
"""
import logging
import re
import time

from django.utils import timezone

log = logging.getLogger(__name__)

TH_MON = ["", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
THAI_DAYS = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
EXEC_POSITIONS = {"admin", "executive", "ผู้บริหาร", "manager", "exec"}

MAX_URGENT = 8          # ตามด่วนในหน้าแรก (ข้อความ LINE ส่ง 5)
MAX_DEALS = 5
MAX_TASKS = 6
MAX_QUEUE = 40          # รถในคิวของทีม (คนงาน)
MAX_BUY_CASES = 40      # เคสจัดซื้อที่ส่งให้แอป (ที่เหลือบอกเป็นตัวเลข)
SLOW_TTL = 60           # จำผลส่วนที่คำนวณหนัก (ตามด่วน ~1 วิ · ตารางคะแนน) ต่อ process

_slow: dict = {}


def _cached(key, fn, ttl=SLOW_TTL):
    hit = _slow.get(key)
    now = time.time()
    if hit and now - hit[0] < ttl:
        return hit[1]
    val = fn()
    _slow[key] = (now, val)
    return val


def _mget(d, k):
    """dict ที่คีย์เป็นเดือน — คำนวณสดได้ int · อ่านจากที่เก็บ (JSON) ได้ str"""
    if not isinstance(d, dict):
        return {}
    v = d.get(k)
    if v is None:
        v = d.get(str(k))
    return v or {}


def role_of(user: dict) -> str:
    """admin · worker (ช่าง/ฝ่ายทะเบียน/ล้างรถ) · buyer (จัดซื้อ) · seller — แอปใช้จัดแท็บ"""
    pos = (user.get("position") or "").strip().lower()
    if pos in EXEC_POSITIONS:
        return "admin"
    if pos == "worker":
        return "worker"
    try:
        from . import purchase_page
        nick = (user.get("nickname") or user.get("seller_name") or "").strip()
        if purchase_page.is_purchaser(nick, user.get("position")):
            return "buyer"
    except Exception:
        pass
    return "seller"


def _hm(s):
    """"8:30" / "08.30" / "9.00" → นาทีตั้งแต่เที่ยงคืน · อ่านไม่ออก = None"""
    m = re.search(r"(\d{1,2})\s*[.:]\s*(\d{2})", str(s or ""))
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    return h * 60 + mi if h < 24 and mi < 60 else None


# ─────────────────────────────────────────────────────────────
#  ส่วนที่ใช้ทุกบทบาท
# ─────────────────────────────────────────────────────────────
def my_checkin(emp, day=None) -> dict | None:
    """เช็คชื่อเข้างานวันนี้ของตัวเอง — ข้อมูลที่ n8n เขียนลง checkout_checkin (ไม่มีพนักงานในทะเบียน = None)"""
    if not emp:
        return None
    from checkout.models import CheckIn
    day = day or timezone.localdate()
    dname = THAI_DAYS[day.weekday()]
    out = {"workStart": emp.work_start or "", "dayName": dname, "track": bool(emp.track_checkin)}
    from checkout.checkin_app import SOURCE, first_per_employee
    rows = first_per_employee(CheckIn.objects.filter(employee=emp, date_iso=day))
    c = rows[0] if rows else None
    out["anywhere"] = bool(getattr(emp, "checkin_anywhere", False))   # ★ 14 ต.ค.69 เช็คชื่อในแอป
    if c:
        late = None
        a, b = _hm(c.time_hm), _hm(c.work_start or emp.work_start)
        if c.status == "late" and a is not None and b is not None and a > b:
            late = a - b
        out.update(status=c.status or "abnormal", time=c.time_hm or "", lateMin=late,
                   source="app" if c.time_source == SOURCE else "line")
    elif emp.day_off and dname in emp.day_off:
        out["status"] = "dayoff"
    else:
        out["status"] = "none"
    return out


def my_out(request, limit: int = 10) -> list:
    """รถที่ฉันเบิกออกไปแล้วยังไม่คืน (ชื่อผู้เบิก = ชื่อเล่นของคนที่ login — ตัวเดียวกับตอนกดเบิก)"""
    from checkout.models import CarMovement
    from checkout.views import _actor_name
    me = (_actor_name(request) or "").strip()
    if not me:
        return []
    now = timezone.now()
    out = []
    for m in (CarMovement.objects.filter(returned_at__isnull=True, borrower_name=me)
              .exclude(status=CarMovement.CANCELLED).select_related("car")
              .order_by("-checked_out_at")[:limit]):
        car = m.car
        hours = (now - m.checked_out_at).total_seconds() / 3600 if m.checked_out_at else 0
        out.append({"code": car.code if car else "", "plate": (car.plate if car else "") or m.plate_text or "",
                    "title": car.title if car else "", "purpose": m.purpose or "",
                    "destination": m.destination or "",
                    "since": timezone.localtime(m.checked_out_at).isoformat(timespec="seconds")
                    if m.checked_out_at else "", "hours": round(hours, 1)})
    return out


def _car_row(c) -> dict:
    return {"code": c.code, "plate": c.plate or "", "label": c.card_label, "title": c.title,
            "stage": c.stage, "stageName": c.stage_name, "days": c.days_in_stage, "flag": c.flag,
            "priority": c.priority, "priorityName": c.priority_name, "priorityColor": c.priority_color,
            "flags": [{"key": f["key"], "name": f["name"], "color": f["color"]} for f in c.flags]}


def _active_cars():
    from cars.models import Car
    return [c for c in Car.objects.filter(deleted_at__isnull=True)
            if not (c.status == "sold" or c.stage == "sold")]


# ─────────────────────────────────────────────────────────────
#  เซลล์
# ─────────────────────────────────────────────────────────────
def _seller_kpi(name: str) -> dict:
    from .constants import TARGETS, refresh_from_sheet
    from .fetch_dashboard import bangkok_now, fetch_dashboard_data
    refresh_from_sheet()
    m = bangkok_now().month
    s = _mget(_mget(fetch_dashboard_data().get("monthlySummary") or {}, m).get("sellers") or {}, name)
    return {"month": TH_MON[m], "lead": s.get("lead", 0), "booking": s.get("booking", 0),
            "done": s.get("done", 0), "dealValue": s.get("dealValue", 0),
            "notCalled": s.get("notCalled", 0), "target": TARGETS.get(name, 0)}


SCORE_PARTS = [("sDone", "จบ (ปล่อย)", 30), ("sJong", "จอง", 10), ("sConv", "Conv", 20),
               ("sVel", "สถานะ", 10), ("sFollow", "ติดตาม", 20), ("sBan", "โดนแบน", 10)]


def _score(name: str) -> dict | None:
    from .fetch_dashboard import compute_diligence_scores
    rows = _cached("scorecard", compute_diligence_scores, 120)
    rows = sorted(rows or [], key=lambda e: -(e.get("score") or 0))
    for i, e in enumerate(rows):
        if e.get("name") == name:
            return {"total": round(e.get("score") or 0, 1), "rank": i + 1, "of": len(rows),
                    "parts": [{"label": lb, "val": round(e.get(k) or 0, 1), "max": mx} for k, lb, mx in SCORE_PARTS]}
    return None


def _chats(emp) -> dict:
    from checkout import connect as C
    cnt = C.counts(emp, False)
    from datetime import timedelta
    duty_today, duty_tomorrow = C.today_team(), C.duty_team(timezone.localdate() + timedelta(days=1))
    team = C.team_of(emp) if emp else ""
    on_duty = bool(team) and team == duty_today
    if not on_duty:
        cnt["queue"] = 0                        # ไม่ใช่วันเวร = ไม่ต้องเห็นคิว (กติกาเดียวกับ /connect/api/summary)
    return {"mineWaiting": cnt.get("mineWaiting", 0), "mineOverdue": cnt.get("mineOverdue", 0),
            "mine": cnt.get("mine", 0), "queue": cnt.get("queue", 0), "team": team,
            "dutyToday": duty_today, "dutyTomorrow": duty_tomorrow, "onDuty": on_duty}


def _tasks(name: str) -> dict:
    from checkout import leadflow as LF
    rows = LF.seller_tasks(name)
    todo = [r for r in rows if r["kind"] in ("overdue", "waiting", "unsent")]
    todo.sort(key=lambda r: (r["kind"] != "overdue", r.get("leftMin") if r.get("leftMin") is not None else 9999))
    keep = ("code", "customer", "car", "phone", "dueAt", "kind", "leftMin", "chatId", "lastReport")
    return {"total": len(rows), "open": len(todo), "late": sum(1 for r in todo if r["kind"] == "overdue"),
            "rows": [{k: r.get(k) for k in keep} for r in todo[:MAX_TASKS]], "callMin": LF.cfg()["call_min"]}


def _follow(name: str, emp) -> dict:
    from .fetch_dashboard import fu_idle, fu_reason, seller_followups
    fu = _cached("fu:" + name, lambda: seller_followups(name))
    today = fu["today"]
    urgent = fu["urgent"][:MAX_URGENT]
    chat_by_code = {}
    if emp and urgent:                           # ลีดนี้คุยอยู่ใน Connect ไหม → ปุ่มเปิดแชท (เฉพาะลูกค้าของตัวเอง)
        try:
            from checkout.models import ChatLead
            for x in ChatLead.objects.filter(code__in=[u["code"] for u in urgent if u["code"]],
                                             chat__owner=emp).values("code", "chat_id"):
                chat_by_code[x["code"]] = x["chat_id"]
        except Exception:
            pass
    z_opts = []
    if name != "ADMIN":                          # ★ 13 ต.ค.69 เลือกสถานะลูกค้า (Z) จากแอป → /crm/api/lead_status
        try:                                     #   ลีดของเทเลเซลล์แก้ในชีตโดยตรง (API ตอบ 400) → ไม่ส่งตัวเลือก
            from .crm_page import _z_options
            z_opts = _z_options()
        except Exception:
            z_opts = []
    return {
        "follow": len(fu["urgent"]), "notCalled": fu["notCalled"], "noStatus": fu["noStatus"],
        "stale": fu["stale"], "windowDays": 14, "zOptions": z_opts,
        "urgent": [{"code": u["code"], "car": u.get("car") or "", "phone": u.get("phone") or "",
                    "type": u.get("leadType") or "", "status": u["customerStatus"] or "",
                    "hot": "hot" in (u["leadTier"] or ""), "updates": u["updateCount"] or 0,
                    "idle": fu_idle(u, today), "reason": fu_reason(u, today),
                    "chatId": chat_by_code.get(u["code"])} for u in urgent],
        "deals": [{"customer": b.get("customer") or "", "plate": b.get("plate") or "", "car": b.get("car") or "",
                   "status": b.get("status") or "", "reason": rs, "days": d, "code": b.get("leadCode") or ""}
                  for b, rs, d in fu["deals"][:MAX_DEALS]],
    }


def _car_match(name: str) -> dict:
    from checkout import leadflow as LF
    rows = LF.seller_matches(name).get("rows") or []
    return {"customers": len(rows), "rows": rows[:5]}


def _seller_name(user) -> str:
    from .constants import normalize_seller
    raw = (user.get("seller_name") or user.get("nickname") or "").strip()
    return normalize_seller(raw) or raw


def seller_home(request, user, emp, out, lazy=False):
    name = _seller_name(user)
    out["seller"] = name
    _part(out, "kpi", lambda: _seller_kpi(name))
    _part(out, "score", lambda: _score(name))
    _part(out, "chats", lambda: _chats(emp))
    _part(out, "tasks", lambda: _tasks(name))
    if lazy:
        # ตามด่วนต้องอ่านชีตลีดทั้งก้อน (ครั้งแรกของ worker ~8 วิ) → แอปขอแยกด้วย ?part=follow
        # หน้าจอขึ้นส่วนอื่นได้ทันที ไม่ต้องรอ
        out["followLazy"] = True
    else:
        _part(out, "follow", lambda: _follow(name, emp))
    _part(out, "carMatch", lambda: _car_match(name))


def follow_part(request, user: dict) -> dict:
    """เฉพาะ "ตามด่วน" ของเซลล์ (GET /api/m/home?part=follow) — บทบาทอื่นได้ {} """
    from checkout import connect as C
    out = {"ok": True}
    if role_of(user) != "seller":
        return out
    emp = None
    try:
        emp = C.employee_of(user)
    except Exception:
        pass
    _part(out, "follow", lambda: _follow(_seller_name(user), emp))
    return out


# ─────────────────────────────────────────────────────────────
#  แอดมิน / ผู้บริหาร
# ─────────────────────────────────────────────────────────────
def _admin_numbers() -> dict:
    from .fetch_dashboard import bangkok_now, fetch_dashboard_data
    data = fetch_dashboard_data()
    now = bangkok_now()
    dm = _mget(data.get("dailyByMonth") or {}, now.month)

    def _day(k):
        arr = dm.get(k) or []
        return arr[now.day] if len(arr) > now.day else 0
    ms = _mget(data.get("monthlySummary") or {}, now.month)
    return {"month": TH_MON[now.month],
            "today": {"lead": _day("leads"), "leadRJ": _day("leadRJ"), "booking": _day("bookings"),
                      "done": _day("dones"), "dealValue": _day("dealValue")},
            "monthTotal": {"lead": ms.get("totalLeads", 0), "booking": ms.get("totalBookings", 0),
                           "done": ms.get("totalDone", 0), "dealValue": ms.get("totalDealValue", 0)}}


def _admin_chats() -> dict:
    from checkout import connect as C
    from checkout import leadflow as LF
    cnt = C.counts(None, True)
    out = {"queue": cnt.get("queue", 0), "tocode": cnt.get("tocode", 0),
           "pending": cnt.get("pending", 0),          # ให้เบอร์แล้ว รอแอดมินกดรับ lead (กลุ่มบนสุดของห้องพัก)
           "buyroom": cnt.get("buyroom", 0),          # ★ 11 ต.ค.69 ลีดรับซื้อรถ รอส่งใบเคสรับซื้อให้จัดซื้อ
           "dutyToday": C.today_team()}
    try:
        from checkout.leadpark import board
        out["parked"] = board()["stats"]["waiting"]
    except Exception:
        out["parked"] = 0
    try:
        sm = LF.summary()
        out["slipsToday"] = sm["total"]
        out["callLate"] = sm["counts"].get("overdue", 0)
    except Exception:
        pass
    return out


def checkin_summary(day=None) -> dict:
    """เช็คชื่อวันนี้ทั้งบริษัท — กติกาเดียวกับพาเนลเช็คชื่อ (ตัดคนวันหยุด · ตัดคนที่ไม่ต้องเช็คชื่อ)
    "ยังไม่มา" นับเฉพาะคนที่ **เลยเวลาเข้างานของตัวเองแล้ว** (ดูวันนี้) — ยังไม่ถึงเวลาไม่ใช่ขาด"""
    from checkout.models import CheckIn, Employee
    today = timezone.localdate()
    day = day or today
    dname = THAI_DAYS[day.weekday()]
    seen, n = set(), {"ontime": 0, "late": 0, "abnormal": 0}
    late_rows = []
    from checkout.checkin_app import first_per_employee   # คนเดียววันละแถว (แอป + กลุ่ม LINE)
    for c in sorted(first_per_employee(CheckIn.objects.filter(date_iso=day).select_related("employee")),
                    key=lambda x: (x.time_hm or "", x.id)):
        if c.employee_id:
            seen.add(c.employee_id)
        st = c.status if c.status in n else "abnormal"
        n[st] += 1
        if st == "late":
            late_rows.append({"name": (c.employee.nickname if c.employee_id and c.employee else "")
                              or c.display_name or "ไม่ทราบชื่อ", "time": c.time_hm or ""})
    now_min = (timezone.localtime().hour * 60 + timezone.localtime().minute) if day == today else 24 * 60
    missing, not_yet, dayoff, no_time = [], 0, 0, 0
    for e in Employee.objects.filter(active=True, track_checkin=True).order_by("nickname"):
        if e.id in seen:
            continue
        if e.day_off and dname in e.day_off:
            dayoff += 1
            continue
        ws = _hm(e.work_start)
        if ws is None:
            no_time += 1
        elif now_min >= ws:
            missing.append({"name": e.nickname, "workStart": e.work_start})
        else:
            not_yet += 1
    return {"came": sum(n.values()), **n, "lateRows": late_rows[:12], "missing": missing,
            "notYet": not_yet, "dayoff": dayoff, "noTime": no_time,
            "employees": Employee.objects.filter(active=True, track_checkin=True).count()}


def _cars_summary() -> dict:
    from cars.views import out_now_codes
    cars = _active_cars()
    fl = {"red": 0, "amber": 0, "ok": 0, "wait": 0}
    for c in cars:
        fl[c.flag] = fl.get(c.flag, 0) + 1
    stuck = sorted([c for c in cars if c.flag in ("red", "amber")], key=lambda c: -c.days_in_stage)[:6]
    ready = sum(1 for c in cars if c.stage == "show")
    return {"total": len(cars), "ready": ready, "flags": fl, "outNow": len(out_now_codes()),
            "stuck": [_car_row(c) for c in stuck]}


def admin_home(request, user, emp, out):
    _part(out, "numbers", _admin_numbers)
    _part(out, "chats", _admin_chats)
    _part(out, "staff", checkin_summary)          # ทั้งบริษัท (ของตัวเองอยู่ที่ "checkin")
    _part(out, "cars", _cars_summary)


# ─────────────────────────────────────────────────────────────
#  คนงาน (ช่าง/ฝ่ายทะเบียน/ล้างรถ/โปรดักชัน/QC/อู่สี)
# ─────────────────────────────────────────────────────────────
def _team_queue(request) -> dict:
    """รถที่อยู่ในสเตปที่ทีมของฉันเป็นเจ้าของงาน (STAGE_OWNER — ตารางเดียวกับป้าย "→ ฝ่าย" บนปุ่มสเตป)
    เรียงเหมือนบอร์ด: ติดธงงานค้างก่อน → ความด่วน → ค้างนานสุดก่อน"""
    from cars import constants as CC
    from cars import roles
    u = getattr(request, "user", None)
    role = roles.get_role(u) if (u and u.is_authenticated) else ""
    label = roles.ROLE_LABEL.get(role, "") if role else ""
    if not label:
        return {"role": "", "roleLabel": "", "rows": [], "total": 0,
                "note": "บัญชีนี้ยังไม่มีบทบาทในระบบติดตามรถ — ให้แอดมินตั้งที่ /track/users/"}
    mine = {k for k, own in CC.STAGE_OWNER.items() if label in own}
    pr = {k: i for i, k in enumerate(CC.PRIORITY_KEYS)}
    cars = [c for c in _active_cars() if c.stage in mine]
    cars.sort(key=lambda c: (not c.flags, pr.get(c.priority, 9), c.stage_since))
    return {"role": role, "roleLabel": label, "total": len(cars), "rows": [_car_row(c) for c in cars[:MAX_QUEUE]],
            "stages": [CC.STAGE_NAME[k] for k in CC.STAGE_KEYS if k in mine]}


def worker_home(request, user, emp, out):
    _part(out, "queue", lambda: _team_queue(request))


# ─────────────────────────────────────────────────────────────
#  จัดซื้อ
# ─────────────────────────────────────────────────────────────
def _purchase(user) -> dict:
    from . import purchase_page
    nick = (user.get("nickname") or user.get("seller_name") or "").strip()
    d = purchase_page.summary(nick)
    cases = d.get("cases") or []
    d["cases"] = [{"code": c.get("code") or "", "name": c.get("name") or "", "car": c.get("car") or "",
                   "phone": c.get("phone") or "", "owner": c.get("owner") or "", "age": c.get("age", 0),
                   "talked": bool(c.get("talked")), "model": c.get("model") or "",
                   "gapDemand": (c.get("gap") or {}).get("demand", 0) if c.get("gap") else 0}
                  for c in cases[:MAX_BUY_CASES]]
    d["moreCases"] = max(0, len(cases) - MAX_BUY_CASES)
    d["gap"] = (d.get("gap") or [])[:10]
    return d


def buyer_home(request, user, emp, out):
    _part(out, "purchase", lambda: _purchase(user))


# ─────────────────────────────────────────────────────────────
def _part(out: dict, key: str, fn) -> None:
    try:
        out[key] = fn()
    except Exception as e:                       # ส่วนเดียวพัง ไม่ลากทั้งหน้า
        log.warning("mobile home %s: %s", key, e, exc_info=True)
        out.setdefault("errors", {})[key] = "โหลดส่วนนี้ไม่ได้ — ลองดึงลงเพื่อโหลดใหม่"


def build(request, user: dict, lazy: bool = False) -> dict:
    from checkout import connect as C
    role = role_of(user)
    emp = None
    try:
        emp = C.employee_of(user)
    except Exception:
        pass
    out = {"ok": True, "role": role, "now": timezone.localtime().isoformat(timespec="seconds"),
           "dayName": THAI_DAYS[timezone.localdate().weekday()],
           "me": {"nickname": user.get("nickname") or user.get("display_name") or "",
                  "position": (emp.position if emp else "") or ""}}
    _part(out, "checkin", lambda: my_checkin(emp))
    _part(out, "myOut", lambda: my_out(request))
    if role == "seller":
        seller_home(request, user, emp, out, lazy=lazy)
    else:
        {"admin": admin_home, "worker": worker_home, "buyer": buyer_home}[role](request, user, emp, out)
    return out
