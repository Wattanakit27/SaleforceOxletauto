"""หน้า **Oxlet CRM** (`/crm/`) — ข้อมูลจริงก้อนเดียวต่อเซลล์ (★ 13 ต.ค.69 · แบบ "Oxlet CRM.html")

แบบที่ได้มามี 5 หน้า (แดชบอร์ด · ไปป์ไลน์ลีด · ลูกค้า · รายงาน · แชท) ใช้ข้อมูลสมมติ
ไฟล์นี้ประกอบข้อมูลจริงจาก **ของที่มีอยู่แล้ว** — ไม่มีสูตรนับใหม่ ตัวเลขจึงตรงกับหน้าเซลล์ / ข้อความ LINE:

  ยอดเดือน/ไตรมาส · รายวัน = fetch_seller_stats (ชุดเดียวกับหน้าเซลล์ "สถิติของฉัน" · ปล่อยนับตามแท็บ)
  ตามด่วน · ดีลค้าง      = fu_* ใน fetch_dashboard (สูตรเดียวกับข้อความ "ตามด่วน" ทุกเช้า)
  ใบจ่ายลีด · นาฬิกาโทร  = leadflow.seller_tasks (ตัวเดียวกับ /api/seller/today)
  ขั้น/ความร้อนของลูกค้าแชท = crm.stage_of / crm.heat_of (ตัวเดียวกับ Connect)
  อันดับ · เป้าทีม        = dailyBySeller / monthlySummary ที่ cron อุ่นไว้ (ส่งแค่ชื่อ+ตัวเลข เหมือนตารางคะแนน)

ไปป์ไลน์ลีด (เจ้าของเลือก "แชท + ลีดจากชีต"):
  · ลูกค้าแชท (LINE/FB) วางตามขั้นใน Connect — ลากเปลี่ยนขั้นได้ (POST /connect/api/crm ตัวเดิม)
  · ลีดจากชีต วางตามสถานะลูกค้า (คอลัมน์ Z) — ลากไม่ได้ · กดแล้วเลือกสถานะ (เขียนช่อง Z ช่องเดียวเหมือนหน้าเซลล์)
  · เคสจองที่ยังไม่ปล่อย (ชีตยอดขาย) อยู่คอลัมน์ "จอง / ปิดการขาย"

ทุกส่วนห่อ try แยก (ส่วนเดียวพังไม่ลากทั้งหน้า) · ไม่ส่ง LINE user id ออก (อ้างลูกค้าแชทด้วย ChatOwner.id)
"""
import logging
import re
import time
from datetime import date, datetime, timedelta

from django.utils import timezone

log = logging.getLogger(__name__)

PIPE_DAYS = 60            # ลีดจากชีตที่อยู่บนกระดาน = รับมาไม่เกินกี่วัน (เก่ากว่านี้ดูในหน้าลูกค้า/หน้าเซลล์)
CUST_DAYS = 90            # ลีดจากชีตที่ส่งให้หน้าลูกค้า (ทั้งปีหนักเกิน ~600 KB · หน้าเซลล์เดิมยังเห็นทั้งปี)
DEAD_DAYS = 14            # เคสเสีย/คืนเคส/ยกเลิก ส่งให้หน้าลูกค้าเฉพาะที่รับมาไม่เกินกี่วัน (เก่ากว่านี้บอกเป็นจำนวน · ~90% ของลีดเป็นแบบนี้)
DEAL_DAYS = 90            # เคสจองที่ยังไม่ปล่อย นับเฉพาะที่จองไม่เกินกี่วัน (เก่ากว่านี้ = เคสค้าง ไม่ใช่ดีลที่กำลังเดิน)
CACHE_TTL = 20            # จำผลต่อเซลล์ (วินาที) — กดรีเฟรชถี่ไม่ต้องคำนวณใหม่ · เขียนสถานะแล้วล้าง

COLS = [("new", "ลีดใหม่"), ("contacted", "ติดต่อแล้ว"), ("viewing", "นัดดูรถ"),
        ("finance", "ยื่นไฟแนนซ์"), ("booked", "จอง / ปิดการขาย")]
COL_ORDER = {k: i for i, (k, _) in enumerate(COLS)}
# ขั้นของลูกค้าแชท (crm.STAGES) → คอลัมน์บนกระดาน · lost ไม่อยู่บนกระดาน
CHAT_COL = {"new": "new", "pool": "new", "waiting": "new", "contacted": "contacted",
            "viewing": "viewing", "finance": "finance", "won": "booked"}
# ลากเข้าคอลัมน์ไหน → ตั้งขั้นอะไร ("ลีดใหม่" ระบบคิดเอง ตั้งเองไม่ได้ → ใช้ "รอติดต่อ")
COL_STAGE = {"new": "waiting", "contacted": "contacted", "viewing": "viewing", "finance": "finance", "booked": "won"}

# คอลัมน์ Z → คอลัมน์บนกระดาน (นอกจากจอง/เคสเสีย ซึ่งใช้ fu_booked / fu_skip ตัวเดียวกับตามด่วน)
Z_VIEWING = ("รอมาดูรถ",)
Z_FINANCE = ("รอเช็คเครดิต",)
DEAL_OPEN = ("จอง", "รอเซ็น", "รอผล", "รอปล่อย")     # สถานะเคสจองที่ยังไม่ปล่อย (ไม่นับ ปล่อย/รีเจ็ก)

_CAR_JUNK = re.compile(r"^\s*(?:\*[^*]{0,20}\*\s*[:：]?\s*)+")


def _clean_car(inq: str, formula: str = "") -> str:
    """รุ่นรถที่ลูกค้าถาม — ตัดหัวข้อแม่แบบใบจ่ายลีดที่ติดมา ("*เพิ่มเติม* :") · ว่าง = ใช้ CAR/สูตร"""
    s = _CAR_JUNK.sub("", inq or "").strip(" :：-*\t")
    return s or (formula or "").strip()


def _clean_code(c: str) -> str:
    """เลขลีดจากชีตยอดขาย บางแถวมี ":" / "-" ติดหน้า (":TLD10-8832") หรือเป็น "-" เฉยๆ"""
    c = (c or "").strip().lstrip(":：- ").strip()
    return "" if c in ("", "-") else c


TH_MON = ["", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
TH_DAY = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
TH_DAY_SHORT = ["จ", "อ", "พ", "พฤ", "ศ", "ส", "อา"]

_cache: dict = {}


def invalidate(seller: str = "") -> None:
    if seller:
        _cache.pop(seller, None)
    else:
        _cache.clear()


def _part(out: dict, key: str, fn) -> None:
    try:
        out[key] = fn()
    except Exception as e:                       # ส่วนเดียวพัง ไม่ลากทั้งหน้า
        log.warning("crm page %s: %s", key, e, exc_info=True)
        out.setdefault("errors", {})[key] = "โหลดส่วนนี้ไม่ได้: %s" % str(e)[:120]


def _mget(d, k):
    """dict ที่คีย์เป็นเดือน — คำนวณสดได้ int · อ่านจากที่เก็บ (JSON) ได้ str"""
    if not isinstance(d, dict):
        return {}
    v = d.get(k)
    if v is None:
        v = d.get(str(k))
    return v or {}


def _iso(dt):
    if not dt:
        return ""
    try:
        return timezone.localtime(dt).isoformat(timespec="seconds")
    except Exception:
        return ""


def _today() -> date:
    from .fetch_dashboard import bangkok_now
    return bangkok_now().date()


def _pdate(s):
    from .fetch_dashboard import parse_date
    try:
        return parse_date(str(s or "").split(" ")[0].strip())
    except Exception:
        return None


def _pdate_loose(s, year):
    """วันที่ที่อาจไม่มีปี ("10/2" จาก FORMATTED_VALUE ของชีตยอดขาย = 10 ก.พ.) → date ของปีที่ให้
    ⚠️ ห้ามเรียก parse_date กับ "d/m" ก่อน — ทางสำรอง dateutil อ่านเป็นเดือนขึ้นก่อน (10/2 → 2 ต.ค.)"""
    from .fetch_dashboard import parse_month_day
    txt = str(s or "").split(" ")[0].strip()
    if not re.fullmatch(r"\d{1,2}/\d{1,2}", txt):
        d = _pdate(txt)
        if d:
            return d
    try:
        md = parse_month_day(txt)
    except Exception:
        md = None
    if md:
        try:
            return date(year, md[0], md[1])
        except Exception:
            return None
    return None


# ─────────────────────────────────────────────────────────────
#  เซลล์ ↔ ทะเบียนพนักงาน
# ─────────────────────────────────────────────────────────────
def roster() -> list:
    """เซลล์ในทีม (ตั้งค่าเซลล์ + ทะเบียน) + เทเลเซลล์ — ตัวเลือก "ดูของใคร" ของแอดมิน"""
    from .constants import TEAM_ID, TEAMS, refresh_from_sheet
    refresh_from_sheet()
    out = []
    for team in sorted(TEAMS):
        for n in sorted(TEAMS[team]):
            out.append({"name": n, "team": TEAM_ID.get(n, team), "label": "เทเลเซลล์" if n == "ADMIN" else n})
    if not any(r["name"] == "ADMIN" for r in out):
        out.append({"name": "ADMIN", "team": "ADMIN", "label": "เทเลเซลล์"})
    return out


def seller_emp(seller: str):
    """แถวพนักงานของเซลล์ (ใช้หาลูกค้าแชทที่เขาดูแล) — เทียบชื่อเล่นแบบ normalize · ไม่เจอ = None"""
    if not seller or seller == "ADMIN":
        return None
    from checkout.models import Employee
    from .constants import normalize_seller
    e = Employee.objects.filter(nickname=seller, active=True).first()
    if e:
        return e
    for e in Employee.objects.filter(active=True).only("id", "nickname", "position"):
        if normalize_seller(e.nickname) == seller:
            return e
    return None


# ─────────────────────────────────────────────────────────────
#  ลีดจากชีต (ของเซลล์คนเดียว · ทั้งปี) → กระดาน / หน้าลูกค้า / ช่องทางในรายงาน
# ─────────────────────────────────────────────────────────────
def sheet_stage(l: dict) -> str:
    """คอลัมน์บนกระดานของลีดจากชีต · '' = ไม่อยู่บนกระดาน (เคสเสีย/คืนเคส/ยกเลิก — กติกาเดียวกับตามด่วน)"""
    from .fetch_dashboard import fu_booked, fu_skip
    if fu_booked(l):                              # ต้องเช็คก่อน: "ส่งมอบ" อยู่ในคำ "ไม่ต้องตาม" ด้วย
        return "booked"
    if fu_skip(l):
        return ""
    z = l.get("customerStatus") or ""
    if any(w in z for w in Z_FINANCE):
        return "finance"
    if any(w in z for w in Z_VIEWING):
        return "viewing"
    if not z.strip() and not (l.get("updateCount") or 0):
        return "new"
    return "contacted"


def _sheet_leads_impl(seller: str) -> list:
    from .constants import RJ_TYPES, normalize_seller
    from .fetch_dashboard import (compute_lead_score, customer_status_priority, fu_idle, fu_reason,
                                  fu_urgency, is_this_year, prepare_lead_score_context)
    from .google_sheets import LEADS_COL as L, cell, cell_num, fetch_all_sheets
    raw = fetch_all_sheets()
    raw_leads = raw.get("leads") or []
    ctx = prepare_lead_score_context(raw_leads, raw.get("sales_reports") or [])
    today = _today()
    by_code, out = {}, []
    for r in raw_leads:
        if normalize_seller(cell(r, L.sales_rep)) != seller:
            continue
        din = cell(r, L.received_date)
        if not is_this_year(din):
            continue
        try:
            ls = compute_lead_score(r, ctx["cfg"])
        except Exception:
            ls = {"score": 0, "tier": "cold"}
        d = _pdate(din)
        typ = cell(r, L.type)
        l = {
            "code": cell(r, L.lead_code), "phone": cell(r, L.phone), "channel": cell(r, L.channel),
            "type": typ, "rj": typ in RJ_TYPES,
            "car": _clean_car(cell(r, L.car_inquiry), cell(r, L.car_formula)),
            "dateIn": din, "timeIn": cell(r, L.time), "date": d.isoformat() if d else "",
            "month": d.month if d else None,
            "updateCount": int(cell_num(r, L.update_count)), "callProof": cell(r, L.call_proof),
            "customerStatus": cell(r, L.customer_status),
            "followPriority": customer_status_priority(cell(r, L.customer_status)),
            "adminStatus": cell(r, L.admin_status), "salesStatus": cell(r, L.sales_status),
            "lastUpdate": cell(r, L.last_updated_at),
            "occupation": cell(r, L.occupation), "income": cell(r, L.income),
            "customerType": cell(r, L.customer_type),
            "leadScore": ls["score"], "leadTier": ls["tier"],
        }
        l["stage"] = sheet_stage(l)
        l["idle"] = fu_idle(l, today)
        l["reason"] = fu_reason(l, today) if l["stage"] not in ("", "booked") else ""
        l["urgency"] = round(fu_urgency(l, today), 1) if l["stage"] not in ("", "booked") else 0
        code = (l["code"] or "").strip().upper()
        if code and code in by_code:             # เลขซ้ำในชีต — เก็บแถวที่รับล่าสุด
            prev = by_code[code]
            if (l["date"] or "") >= (prev["date"] or ""):
                out[out.index(prev)] = l
                by_code[code] = l
            continue
        if code:
            by_code[code] = l
        out.append(l)
    return out


def sheet_leads(seller: str) -> list:
    hit = _cache.get(("leads", seller))
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    rows = _sheet_leads_impl(seller)
    _cache[("leads", seller)] = (time.time(), rows)
    return rows


# ส่งให้หน้าเว็บเฉพาะที่ใช้จริง (สถานะแอดมิน/เซลล์ใช้คิดคอลัมน์ฝั่งเซิร์ฟเวอร์แล้ว ไม่ต้องส่ง)
_LEAD_KEYS = ("code", "phone", "channel", "type", "car", "dateIn", "timeIn", "date", "updateCount",
              "callProof", "customerStatus", "lastUpdate", "occupation", "income",
              "leadScore", "leadTier", "stage", "idle", "reason", "urgency")


def _slim(l: dict) -> dict:
    return {k: l.get(k) for k in _LEAD_KEYS}


# ─────────────────────────────────────────────────────────────
#  ลูกค้าแชท (Connect) ที่เซลล์คนนี้ดูแล
# ─────────────────────────────────────────────────────────────
def chat_cards(emp) -> list:
    if not emp:
        return []
    from checkout import connect as C
    from checkout import crm
    from checkout.models import ChatOwner
    now = timezone.now()
    objs = list(ChatOwner.objects.select_related("profile", "fb_profile", "owner", "lead")
                .filter(owner=emp).order_by("-last_at")[:400])
    amap = crm.next_appt_map([o.id for o in objs])
    mm = crm.match_map()
    out = []
    for o in objs:
        ld = C.lead_of(o, create=False)
        st = crm.stage_of(o, ld)
        ht = crm.heat_of(o, ld, now)
        sd = crm.silent_days(o, now)
        ap = amap.get(o.id)
        code = ((ld.code if ld else "") or "").strip()
        p = C.cust(o)
        out.append({
            "id": o.id, "name": (ld.customer_name if ld and ld.customer_name else p.show_name),
            "pic": o.picture_url or "", "src": "fb" if C.is_fb(o) else "line",
            "code": code, "phone": (ld.phone if ld else "") or "",
            "lineId": "" if (ld and (ld.auto or {}).get("line_id") == C.QR_SRC) else ((ld.line_id if ld else "") or ""),
            "car": ((ld.car_model or ld.car_text) if ld else "") or "",
            "channel": ((ld.channel if ld else "") or "") or ("Facebook" if C.is_fb(o) else "LINE@"),
            "z": (ld.customer_status if ld else "") or "", "type": (ld.lead_type if ld else "") or "",
            "occupation": (ld.occupation if ld else "") or "", "income": (ld.income if ld else "") or "",
            "stage": st, "stageLabel": crm.STAGE_NAME.get(st, st), "col": CHAT_COL.get(st, ""),
            "heat": ht["key"], "score": ht["score"], "heatWhy": ht["why"],
            "silent": sd if sd is not None else -1,
            "awaiting": bool(o.awaiting_since), "overdue": bool(o.awaiting_since and o.due_at and o.due_at <= now),
            "unread": C.is_unread(o), "trade": bool(ld and C.TRADE_KEY in (ld.auto or {})),
            "deal": C.deal_of(ld),
            "appt": ({"kind": ap[0], "due": _iso(ap[1]), "late": ap[1] < now} if ap else None),
            "carMatch": len(mm.get(code.upper()) or []) if code else 0,
            "lastAt": _iso(o.last_at), "lastIn": _iso(o.last_in_at), "preview": (o.last_preview or "")[:80],
            "lostReason": (ld.lost_reason if ld else "") or "", "stageAt": _iso(ld.stage_at) if ld else "",
        })
    return out


# ─────────────────────────────────────────────────────────────
#  ยอด · เป้า · สัปดาห์นี้ (fetch_seller_stats — ชุดเดียวกับหน้าเซลล์)
# ─────────────────────────────────────────────────────────────
def _month_sum(monthly, months, key):
    return sum((_mget(monthly, m).get(key) or 0) for m in months)


def kpi(stats: dict, seller: str) -> dict:
    from .constants import TARGETS
    today = _today()
    mo = stats.get("monthly") or {}
    q = (today.month - 1) // 3
    qm = [q * 3 + 1, q * 3 + 2, q * 3 + 3]
    pm = [m - 3 for m in qm] if q else []
    done = _month_sum(mo, qm, "done")
    dv = _month_sum(mo, qm, "dealValue")
    ln = _month_sum(mo, qm, "leadNormal")
    prev_dv = _month_sum(mo, pm, "dealValue") if pm else None
    tgt_m = TARGETS.get(seller, 0) or 0
    cur = _mget(mo, today.month)
    return {
        "quarter": q + 1, "months": [TH_MON[m] for m in qm],
        "dealValue": dv, "done": done, "avg": (dv / done) if done else 0,
        "conv": round(100.0 * done / ln, 1) if ln else 0, "leadNormal": ln,
        "prevDealValue": prev_dv, "target": tgt_m * 3, "targetMonth": tgt_m,
        "pct": round(100.0 * (dv - prev_dv) / prev_dv, 1) if prev_dv else None,
        "month": {"name": TH_MON[today.month], "done": cur.get("done") or 0, "dealValue": cur.get("dealValue") or 0,
                  "lead": cur.get("lead") or 0, "booking": cur.get("booking") or 0},
    }


def _day_val(daily, d: date, key: str) -> float:
    arr = _mget(daily, d.month).get(key) or []
    return arr[d.day] if len(arr) > d.day else 0


def week_leads(stats: dict) -> dict:
    """ลีดเข้าสัปดาห์นี้ (จ–อา · รวม RJ) · วันที่ยังไม่ถึง = คาดการณ์จากค่าเฉลี่ยวันเดียวกันใน 4 สัปดาห์ก่อน (ปีนี้เท่านั้น)"""
    today = _today()
    daily = stats.get("daily") or {}
    monday = today - timedelta(days=today.weekday())
    days, got, fc_total = [], 0, 0
    for i in range(7):
        d = monday + timedelta(days=i)
        hist = [monday + timedelta(days=i - 7 * k) for k in range(1, 5)]
        hist = [x for x in hist if x.year == today.year]
        avg = (sum(_day_val(daily, x, "leads") + _day_val(daily, x, "leadRJ") for x in hist) / len(hist)) if hist else 0
        if d > today:
            days.append({"label": TH_DAY_SHORT[i], "n": None, "fc": round(avg), "today": False})
            fc_total += round(avg)
        else:
            n = (_day_val(daily, d, "leads") + _day_val(daily, d, "leadRJ")) if d.year == today.year else 0
            got += n
            days.append({"label": TH_DAY_SHORT[i], "n": n, "fc": round(avg), "today": d == today})
    return {"days": days, "got": got, "forecast": got + fc_total}


def team_targets(seller: str, data: dict) -> dict:
    """เป้าเดือนนี้ของคนในทีมเดียวกัน — ชื่อ + ปล่อย/เป้า (ข้อยกเว้นเดียวกับตารางคะแนนในหน้าเซลล์)"""
    from .constants import TARGETS, TEAM_ID, TEAMS
    today = _today()
    team = TEAM_ID.get(seller, "")
    ms = _mget(data.get("monthlySummary") or {}, today.month).get("sellers") or {}
    names = list(TEAMS.get(team, [])) if team else [seller]
    rows = []
    for n in names:
        s = ms.get(n) or {}
        rows.append({"name": n, "label": "เทเลเซลล์" if n == "ADMIN" else n, "done": s.get("done") or 0,
                     "target": TARGETS.get(n, 0) or 0, "dealValue": s.get("dealValue") or 0, "me": n == seller})
    rows.sort(key=lambda r: (-(r["done"] / r["target"] if r["target"] else r["done"]), r["name"]))
    return {"team": team, "month": TH_MON[today.month], "rows": rows,
            "pipelineValue": (ms.get(seller) or {}).get("pipelineValue") or 0}


# ─────────────────────────────────────────────────────────────
#  นัดถัดไป — นัดในแชท (Connect) + นัดที่เซลล์รายงานในห้องจ่ายเบอร์ (LeadReport.appt_at)
# ─────────────────────────────────────────────────────────────
def appts(emp, seller: str, chats: list) -> list:
    from checkout.models import ChatFollowup, LeadReport
    now = timezone.now()
    start = now - timedelta(hours=3)
    by_id = {c["id"]: c for c in chats}
    out = []
    if emp:
        for f in (ChatFollowup.objects.filter(chat__owner=emp, done_at__isnull=True, due_at__gte=start)
                  .select_related("chat").order_by("due_at")[:8]):
            c = by_id.get(f.chat_id) or {}
            out.append({"src": "chat", "id": f.chat_id, "fid": f.id, "kind": f.kind, "kindLabel": f.get_kind_display(),
                        "due": _iso(f.due_at), "late": f.due_at < now, "note": f.note,
                        "name": c.get("name") or "", "car": c.get("car") or "", "phone": c.get("phone") or "",
                        "code": c.get("code") or ""})
    if seller:
        for r in (LeadReport.objects.filter(seller_name=seller, appt_at__gte=start).order_by("appt_at")[:8]):
            out.append({"src": "report", "id": None, "kind": "viewing", "kindLabel": "นัด (จากรายงานผล)",
                        "due": _iso(r.appt_at), "late": r.appt_at < now, "note": (r.text or "")[:120],
                        "name": "", "car": (r.fields or {}).get("car", "") if isinstance(r.fields, dict) else "",
                        "phone": "", "code": r.code})
    out.sort(key=lambda a: a["due"])
    return out[:8]


# ─────────────────────────────────────────────────────────────
#  เคสจองที่ยังไม่ปล่อย (คอลัมน์ "จอง / ปิดการขาย")
# ─────────────────────────────────────────────────────────────
def deal_cards(stats: dict) -> list:
    today = _today()
    out = []
    for i, b in enumerate(stats.get("bookingCases") or []):
        st = b.get("status") or ""
        if not st or not any(w in st for w in DEAL_OPEN):
            continue
        d = _pdate(b.get("date"))
        if not d or (today - d).days > DEAL_DAYS or d > today + timedelta(days=1):
            continue
        out.append({"id": "d%d" % i, "code": _clean_code(b.get("leadCode")), "name": (b.get("customer") or "").strip(),
                    "car": _clean_car(b.get("car") or ""), "price": b.get("price") or 0, "status": st,
                    "date": b.get("date") or "", "days": (today - d).days, "phone": b.get("phone") or "",
                    "channel": b.get("channel") or "", "signDate": b.get("signDate") or "",
                    "resultDate": b.get("resultDate") or "", "plate": b.get("plate") or "",
                    "finance": b.get("finance") or "", "isCash": bool(b.get("isCash"))})
    out.sort(key=lambda x: x["days"])
    return out


# ─────────────────────────────────────────────────────────────
#  รายงาน (30 วัน · 90 วัน · ปีนี้) — คำนวณฝั่งเซิร์ฟเวอร์ ส่งไปแค่ผลรวม
# ─────────────────────────────────────────────────────────────
def _span(today: date, key: str):
    """(เริ่ม, จบ, เริ่มช่วงก่อน, จบช่วงก่อน, ตัดที่ต้นปีไหม) · ปีนี้ = ไม่มีช่วงก่อน (แดชบอร์ดเก็บปีเดียว)"""
    jan1 = date(today.year, 1, 1)
    if key == "year":
        return jan1, today, None, None, False
    n = 30 if key == "r30" else 90
    s = today - timedelta(days=n - 1)
    ps, pe = s - timedelta(days=n), s - timedelta(days=1)
    clipped = s < jan1
    s = max(s, jan1)
    if pe < jan1:
        ps = pe = None
    elif ps < jan1:
        ps = jan1
    return s, today, ps, pe, clipped


def _sum_daily(daily, s: date, e: date, keys) -> float:
    if not s or not e:
        return 0
    tot, d = 0, s
    while d <= e:
        for k in keys:
            tot += _day_val(daily, d, k)
        d += timedelta(days=1)
    return tot


def _book_to_release(cases, s, e, year) -> float | None:
    vals = []
    for b in cases:
        if (b.get("status") or "") != "ปล่อย":
            continue
        rd = _pdate_loose(b.get("releaseDate"), year)
        bd = _pdate(b.get("date"))
        if not rd or not bd or not (s <= rd <= e):
            continue
        dd = (rd - bd).days
        if 0 <= dd <= 365:
            vals.append(dd)
    return round(sum(vals) / len(vals), 1) if vals else None


def _range_numbers(daily, cases, s, e, year) -> dict:
    dv = _sum_daily(daily, s, e, ("dealValue",))
    done = _sum_daily(daily, s, e, ("dones",))
    ln = _sum_daily(daily, s, e, ("leads",))
    return {"dealValue": dv, "done": done, "lead": ln, "leadAll": ln + _sum_daily(daily, s, e, ("leadRJ",)),
            "booking": _sum_daily(daily, s, e, ("bookings",)),
            "conv": round(100.0 * done / ln, 1) if ln else 0,
            "b2r": _book_to_release(cases, s, e, year)}


def _done_channels(cases: list) -> list:
    """เคสที่ปล่อยแล้ว + ช่องทางที่ล้างชื่อแล้ว (`channelClean`) — ตัวเทียบชุดเดียวกับตาราง "Lead → จอง → จบ"
    (รหัสลีด → ช่องทางในชีตลีดก่อน · ไม่เจอค่อยล้างข้อความที่เซลล์พิมพ์แล้วเทียบกับชื่อฝั่งลีด)"""
    from . import fetch_dashboard as FD
    from .google_sheets import LEADS_COL as L, cell, fetch_all_sheets
    done = [dict(b) for b in cases if (b.get("status") or "") == "ปล่อย"]
    if not done:
        return []
    code_ch, names = {}, []
    seen = set()
    for r in fetch_all_sheets().get("leads") or []:
        if not FD.is_this_year(cell(r, L.received_date)):
            continue
        ch = cell(r, L.channel).strip()
        if not ch:
            continue
        if ch not in seen:
            seen.add(ch)
            names.append(ch)
        code = cell(r, L.lead_code).strip()
        if code:
            code_ch.setdefault(code, ch)
    FD._attach_clean_channel(done, code_ch, sorted(names))
    return done


def _done_day(b, year):
    """วันที่นับเคสปล่อย — วันปล่อย (อ่านได้แม้ไม่มีปี) · อ่านไม่ได้ = วันที่ 1 ของเดือนแท็บ (กติกาเดียวกับแดชบอร์ด)"""
    d = _pdate_loose(b.get("releaseDate"), year)
    if d:
        return d
    from .fetch_dashboard import MONTHS_FULL_TH
    tab = str(b.get("sheetTab") or "").strip()
    tm = next((i + 1 for i, mn in enumerate(MONTHS_FULL_TH) if tab.startswith(mn)), 0)
    return date(year, tm, 1) if tm else None


def report(stats: dict, seller: str, leads: list, chats: list, data: dict) -> dict:
    from .constants import ALL_SELLERS, TEAM_ID
    today = _today()
    daily = stats.get("daily") or {}
    cases = stats.get("bookingCases") or []
    mo = stats.get("monthly") or {}
    try:
        all_cases = _done_channels(cases)
    except Exception:
        all_cases = [b for b in cases if (b.get("status") or "") == "ปล่อย"]
    dbs = data.get("dailyBySeller") or {}
    names = [n for n in list(ALL_SELLERS) + ["ADMIN"] if n in dbs]
    out = {"monthly": [], "ranges": {}, "seller": seller}
    for m in range(1, 13):
        r = _mget(mo, m)
        out["monthly"].append({"m": TH_MON[m], "dealValue": r.get("dealValue") or 0, "done": r.get("done") or 0,
                               "future": m > today.month})
    for key in ("r30", "r90", "year"):
        s, e, ps, pe, clipped = _span(today, key)
        cur = _range_numbers(daily, cases, s, e, today.year)
        prev = _range_numbers(daily, cases, ps, pe, today.year) if ps else None
        # กรวย = กลุ่มลีดที่รับในช่วงนี้ (ไม่รวม RJ) ไปถึงขั้นไหนแล้ว · ขั้นนัดดูรถ/ไฟแนนซ์ อ่านจากสถานะลูกค้า (Z) ที่เซลล์กรอก
        coh = [l for l in leads if not l.get("rj") and l.get("date") and s.isoformat() <= l["date"] <= e.isoformat()]

        def reach(l, col):
            st = l.get("stage") or ""
            if col == "contacted":
                return bool((l.get("updateCount") or 0) or (l.get("customerStatus") or "").strip() or st == "booked")
            return COL_ORDER.get(st, -1) >= COL_ORDER[col] if st else False
        funnel = [{"label": "ลีดเข้า", "n": len(coh)},
                  {"label": "ติดต่อแล้ว", "n": sum(1 for l in coh if reach(l, "contacted"))},
                  {"label": "นัดดูรถ", "n": sum(1 for l in coh if reach(l, "viewing"))},
                  {"label": "ยื่นไฟแนนซ์", "n": sum(1 for l in coh if reach(l, "finance"))},
                  {"label": "จอง / ปิดการขาย", "n": sum(1 for l in coh if reach(l, "booked"))}]
        ch = {}
        for b in all_cases:
            rd = _done_day(b, today.year)
            if rd and s <= rd <= e:
                k = (b.get("channelClean") or "").strip() or "ไม่ระบุ"
                ch[k] = ch.get(k, 0) + 1
        chans = sorted(({"name": k, "n": v} for k, v in ch.items()), key=lambda x: -x["n"])
        rank = []
        for n in names:
            dn = dbs.get(n) or {}
            rank.append({"name": n, "label": "เทเลเซลล์" if n == "ADMIN" else n, "team": TEAM_ID.get(n, ""),
                         "dealValue": _sum_daily(dn, s, e, ("dealValue",)), "done": _sum_daily(dn, s, e, ("dones",)),
                         "me": n == seller})
        rank = [r for r in rank if r["dealValue"] or r["done"] or r["me"]]
        rank.sort(key=lambda r: (-r["dealValue"], -r["done"], r["name"]))
        out["ranges"][key] = {"from": s.isoformat(), "to": e.isoformat(), "clipped": clipped,
                              "cur": cur, "prev": prev, "funnel": funnel, "channels": chans[:8],
                              "channelTotal": sum(ch.values()), "rank": rank}
    return out


# ─────────────────────────────────────────────────────────────
def _period_label(today: date) -> str:
    q = (today.month - 1) // 3 + 1
    q_start = date(today.year, (q - 1) * 3 + 1, 1)
    wk = (today - (q_start - timedelta(days=q_start.weekday()))).days // 7 + 1
    return "ไตรมาส %d · สัปดาห์ที่ %d · %s %d %s" % (q, wk, TH_DAY[today.weekday()], today.day, TH_MON[today.month])


def build(seller: str, emp=None, admin: bool = False) -> dict:
    """ข้อมูลหน้า /crm/ ของเซลล์ 1 คน — แอดมินดูของใครก็ได้ (เลือกจาก roster) · เซลล์เห็นของตัวเอง"""
    hit = _cache.get(seller)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    from .constants import TARGETS, TEAM_ID, TEAM_NAMES, refresh_from_sheet
    from .fetch_dashboard import fetch_dashboard_data, fetch_seller_stats
    refresh_from_sheet()
    today = _today()
    out = {"ok": True, "seller": seller, "label": "เทเลเซลล์" if seller == "ADMIN" else seller,
           "team": TEAM_ID.get(seller, ""), "teamName": TEAM_NAMES.get(TEAM_ID.get(seller, ""), ""),
           "target": TARGETS.get(seller, 0) or 0, "period": _period_label(today),
           "now": timezone.localtime().isoformat(timespec="seconds"), "cols": [{"key": k, "label": v} for k, v in COLS],
           "colStage": COL_STAGE, "pipeDays": PIPE_DAYS, "custDays": CUST_DAYS, "hasEmp": bool(emp)}
    stats, data, leads, chats = {}, {}, [], []
    try:
        stats = fetch_seller_stats(seller)
    except Exception as e:
        out.setdefault("errors", {})["stats"] = "อ่านยอดของเซลล์ไม่ได้: %s" % str(e)[:120]
    try:
        data = fetch_dashboard_data() or {}
    except Exception as e:
        out.setdefault("errors", {})["dashboard"] = "อ่านผลรวมแดชบอร์ดไม่ได้: %s" % str(e)[:120]
    try:
        leads = sheet_leads(seller)
    except Exception as e:
        out.setdefault("errors", {})["leads"] = "อ่านลีดจากชีตไม่ได้: %s" % str(e)[:120]
    try:
        chats = chat_cards(emp)
    except Exception as e:
        out.setdefault("errors", {})["chats"] = "อ่านลูกค้าแชทไม่ได้: %s" % str(e)[:120]

    cut_pipe = (today - timedelta(days=PIPE_DAYS)).isoformat()
    cut_cust = (today - timedelta(days=CUST_DAYS)).isoformat()
    cut_dead = (today - timedelta(days=DEAD_DAYS)).isoformat()
    keep = [l for l in leads if (l.get("date") or "") >= cut_cust and (l.get("stage") or (l.get("date") or "") >= cut_dead)]
    out["leads"] = [_slim(l) for l in keep]
    out["leadsYear"] = len(leads)
    out["deadHidden"] = sum(1 for l in leads if (l.get("date") or "") >= cut_cust and not l.get("stage")
                            and (l.get("date") or "") < cut_dead)
    out["deadDays"] = DEAD_DAYS
    out["chats"] = chats
    try:
        from checkout import crm
        mm = crm.match_map()
        for l in out["leads"]:
            c = mm.get((l.get("code") or "").strip().upper()) or []
            l["carMatch"] = len(c)
            if c:
                l["cars"] = c[:3]                 # รถพร้อมขายที่ตรงสเปก (ผล leadflow.refresh_needs ทุก 30 นาที)
    except Exception:
        pass
    out["pipeCut"] = cut_pipe
    _part(out, "deals", lambda: deal_cards(stats))
    _part(out, "kpi", lambda: kpi(stats, seller))
    _part(out, "week", lambda: week_leads(stats))
    _part(out, "teamTargets", lambda: team_targets(seller, data))
    _part(out, "appts", lambda: appts(emp, seller, chats))
    _part(out, "report", lambda: report(stats, seller, leads, chats, data))
    _part(out, "zOptions", _z_options)
    try:
        from . import mobile_home as MH
        _part(out, "tasks", lambda: MH._tasks(seller))
        _part(out, "follow", lambda: MH._follow(seller, emp))
    except Exception:
        pass
    _cache[seller] = (time.time(), out)
    return out


def _z_options() -> list:
    """ตัวเลือกสถานะลูกค้า (คอลัมน์ Z) = ชุดเดียวกับ dropdown ในชีตลีด (Connect อ่านไว้ทุกชั่วโมง)"""
    try:
        from checkout import connect as C
        return list((C.dropdowns().get("fields") or {}).get("customer_status") or [])
    except Exception:
        return []


def lead_by_code(seller: str, code: str):
    code = (code or "").strip().upper()
    if not code:
        return None
    for l in sheet_leads(seller):
        if (l.get("code") or "").strip().upper() == code:
            return l
    return None


_SAFE = re.compile(r"[\x00-\x1f]")


def clean_z(value: str) -> str:
    return _SAFE.sub("", str(value or "")).strip()[:40]
