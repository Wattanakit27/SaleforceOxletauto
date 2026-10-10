# -*- coding: utf-8 -*-
"""**งานจ่ายเบอร์** — นาฬิกาโทร · ปุ่มรับเคส/ขอผ่าน · จ่ายวน · ส่งต่อไม้ 2 · อ่านรายงานผล (10 ต.ค.69)

เจ้าของส่งตัวอย่างหน้าจอ 3 ชุด ("ศูนย์ควบคุมลีด" · มือถือเซลล์ · หน้าเซลล์) แล้วสั่ง
*"ปรับให้เข้ากับระบบเรา ไม่ใช่ปรับไฟล์ของเขา"* — เลือกทำ 7 อย่าง:

  แอดมิน  ① เช็คเบอร์ซ้ำตอนจ่ายเบอร์ (`phonebook.py`)  ② ส่งต่อไม้ 2 (R+เลขเดิม+/1 → ห้อง REJECT)
          ③ จ่ายวนอัตโนมัติ + นาฬิกาโทร 15 นาที
  เซลล์   ④ รถใหม่ตรงกับลูกค้าของฉัน  ⑤ เช็คเบอร์ซ้ำเอง (`phonebook.check_for_seller`)
          ⑥ การ์ดปุ่ม รับเคส/ขอผ่าน ในห้องจ่ายเบอร์  ⑦ อ่านรายงาน "เลข 4 หลัก + ผล" → การ์ดยืนยันแชทส่วนตัว → ลงชีต

ข้อเท็จจริงจากห้องจริง (วัดก่อนทำ · อ่านอย่างเดียว):
  - เซลล์รายงานผลในห้องจ่ายเบอร์ด้วย **เลขรัน + ผล** ("9075 รอตอบครับ" · "9064ลูกค้าไม่ตอบ" ไม่เว้นวรรคก็มี)
    ~1,189 ข้อความ/สัปดาห์ · ห้อง REJECT พิมพ์ "8129/1 …"
  - แอดมินพิมพ์ทวง "9075 @มัท ตามด้วย" ในรูปแบบเดียวกัน → **ข้อความที่มี @ ไม่นับเป็นรายงาน**
  - ส่งต่อไม้ 2 ในห้อง REJECT = **R + เลขเดิม + /1** (prod: 1,075 จาก 1,077 ใบ · ไม่เคยเห็น /2)

**ระบบรู้ไม่ได้ว่าเซลล์โทรจริงไหม** (มือถือเซลล์ไม่ได้ต่อระบบ) → นาฬิกาหยุดเมื่อ "รายงานผล" ในห้อง
หรือตอบลูกค้าผ่าน Connect · กดรับเคส = รับทราบ ไม่ได้หยุดนาฬิกา

กติกาที่ต้องรักษา:
  - **ทุกอย่างที่ส่งออก (การ์ดปุ่ม · การ์ดยืนยัน · เตือนนัด · จ่ายวน/จ่ายใหม่อัตโนมัติ) ปิดโดยปริยาย**
    เปิดที่ Connect → ตั้งค่า → "งานจ่ายเบอร์" · นาฬิกาเองไม่ส่งอะไรออก (โชว์ในหน้า Connect อย่างเดียว)
  - **การ์ดปุ่มต่อท้ายใบจ่ายลีดใน push เดียวกัน** — LINE นับโควต้าต่อผู้รับต่อครั้งที่ยิง
    ส่งแยกครั้ง = กลุ่ม 30 คนเสีย 30 ข้อความเพิ่มทุกใบ · ตอบปุ่มด้วย **reply token (ฟรี)**
  - **การ์ดยืนยันส่งเฉพาะรายงานที่มีข้อมูลจริง** (อาชีพ/รายได้/นัด/สถานะสำคัญ) — "รอตอบ" เฉยๆ ไม่ส่ง
    (1,189 ข้อความ/สัปดาห์ ถ้าส่งทุกอันคือสแปม)
  - **เขียนชีตเฉพาะเมื่อเซลล์กด "ถูกต้อง"** + เฉพาะแถวที่ชื่อเซลล์ในชีตตรงกับคนกด (กันแก้เคสคนอื่น)
  - postback ลงชื่อ HMAC (`SECRET_KEY`) — ใครปลอมข้อมูลปุ่มมาก็กดแทนคนอื่นไม่ได้
  - ไม่ส่ง LINE user id ของพนักงานออกหน้าเว็บ
"""
from __future__ import annotations

import hashlib
import hmac
import re
import threading
import time
from datetime import date, datetime, timedelta

from django.db.models import Count, Max, Q
from django.utils import timezone

from .models import Employee, ExtLead, GroupChat, LeadReport, LeadTask, LineProfile

CFG_KEY = "leadflow_config"
WHAT_CARD = "งานจ่ายเบอร์: การ์ดยืนยันรายงาน"
WHAT_REMIND = "งานจ่ายเบอร์: เตือนนัดลูกค้า"
KEEP_DAYS = 90                      # มีเบอร์/ชื่อลูกค้า — อายุเท่าแชทกลุ่มที่เป็นต้นทาง

DEFAULTS = {
    # ── นาฬิกาโทร (ไม่ส่งอะไรออก) ──
    "clock_on": True,
    "call_min": 15,                 # ต้องรายงานผลภายในกี่นาทีหลังใบถึงกลุ่ม (นับเฉพาะเวลาทำการของ Connect)
    # ── ส่งออก: ปิดโดยปริยายทั้งหมด ──
    "card_on": False,               # แนบการ์ดปุ่ม รับเคส/ขอผ่าน/โทร ต่อท้ายใบจ่ายลีด (push เดียวกัน)
    "report_on": False,             # รายงานที่มีข้อมูลจริง → การ์ดยืนยันเข้าแชทส่วนตัวเซลล์ → กดแล้วลงชีต
    "remind_on": False,             # เตือนนัดลูกค้า (จากรายงานที่ยืนยันแล้ว) ก่อนถึงเวลา
    "remind_min": 60,
    "auto_assign": False,           # จ่ายวนอัตโนมัติ — ใบร่างในห้องพัก Lead ที่รอเกิน auto_after_min
    "auto_after_min": 3,
    "auto_pull": False,             # เลยเวลา/กดขอผ่าน → จ่ายใหม่ให้คนถัดไปในคิวเอง (เลขเดิม)
    "pull_max": 2,                  # จ่ายใหม่อัตโนมัติได้กี่ครั้งต่อใบ (กันวน)
    # ── คิวจ่ายวน ──
    "rr_teams": ["A", "B", "C"],
    "cap_day": 12,                  # วันละไม่เกินกี่ใบต่อคน (0 = ไม่จำกัด)
    "need_checkin": False,          # ต้องเช็คชื่อเข้างานวันนี้แล้วถึงจะได้ใบ
}
_BOOL = ("clock_on", "card_on", "report_on", "remind_on", "auto_assign", "auto_pull", "need_checkin")
_INT = {"call_min": (5, 240), "remind_min": (10, 240), "auto_after_min": (1, 120),
        "pull_max": (0, 5), "cap_day": (0, 100)}


def _kv(key):
    try:
        from dashboard.services import cache_store
        return (cache_store.get_kv(key) or {}).get("data") or {}
    except Exception:
        return {}


def _set_kv(key, val):
    try:
        from dashboard.services import cache_store
        cache_store.set_kv(key, val)
    except Exception:
        pass


def cfg() -> dict:
    raw = _kv(CFG_KEY)
    c = dict(DEFAULTS)
    c.update({k: v for k, v in (raw or {}).items() if k in DEFAULTS})
    for k in _BOOL:
        c[k] = bool(c.get(k))
    for k, (lo, hi) in _INT.items():
        try:
            c[k] = max(lo, min(hi, int(c.get(k))))
        except Exception:
            c[k] = DEFAULTS[k]
    teams = [str(t).strip().upper() for t in (c.get("rr_teams") or []) if str(t).strip()]
    c["rr_teams"] = [t for t in teams if re.fullmatch(r"[A-Z0-9]{1,2}|ADMIN", t)] or list(DEFAULTS["rr_teams"])
    return c


def clean_cfg(body: dict) -> tuple[dict, list]:
    """ค่าจากหน้าตั้งค่า → (ค่าที่จะบันทึก, ปัญหา) · ค่าผิด = ฟ้องพร้อมบอกช่อง ไม่เงียบ"""
    c, errs = cfg(), []
    names = {"call_min": "เวลาที่ต้องรายงานผล", "remind_min": "เตือนนัดก่อนกี่นาที",
             "auto_after_min": "จ่ายวนเมื่อรอเกินกี่นาที", "pull_max": "จ่ายใหม่อัตโนมัติสูงสุด",
             "cap_day": "เพดานใบต่อคนต่อวัน"}
    for k in _BOOL:
        if k in body:
            c[k] = bool(body[k])
    for k, (lo, hi) in _INT.items():
        if k in body:
            try:
                v = int(body[k])
                if not lo <= v <= hi:
                    raise ValueError
                c[k] = v
            except Exception:
                errs.append("%s ต้องเป็นตัวเลข %d–%d" % (names[k], lo, hi))
    if "rr_teams" in body:
        teams = [str(t).strip().upper() for t in (body.get("rr_teams") or []) if str(t).strip()]
        bad = [t for t in teams if not re.fullmatch(r"[A-Z0-9]{1,2}|ADMIN", t)]
        if bad or not teams:
            errs.append("ทีมในคิวจ่ายวนไม่ถูกต้อง: %s" % (", ".join(bad) or "(ว่าง)"))
        else:
            c["rr_teams"] = list(dict.fromkeys(teams))
    return c, errs


def save_cfg(c: dict) -> bool:
    try:
        from dashboard.services import cache_store
        cache_store.set_kv(CFG_KEY, {k: c[k] for k in DEFAULTS})
        return True
    except Exception:
        return False


def _iso(dt):
    return timezone.localtime(dt).isoformat(timespec="seconds") if dt else ""


def _note_error(where: str, e, **kw):
    """จดข้อผิดพลาดล่าสุดใน KV `leadflow_error` + dash_event_log — งานนี้ห่อ try ไว้หลายชั้น (ห้ามทำให้ใบส่งไม่ออก)
    ถ้าไม่จด = พังเงียบ ไม่มีใครรู้ว่านาฬิกาไม่เดิน"""
    msg = ("%s: %s" % (type(e).__name__, e))[:300]
    _set_kv("leadflow_error", dict(kw, at=_iso(timezone.now()), where=where, error=msg))
    try:
        from dashboard.services import eventlog
        eventlog.log("leadflow", name=where, ok=False, error=msg, **kw)
    except Exception:
        pass


def _hm(dt) -> str:
    return timezone.localtime(dt).strftime("%H:%M") if dt else ""


# ─────────────────────────────────────────────────────────────
#  เลขลีด: ส่งต่อไม้ 2
# ─────────────────────────────────────────────────────────────
_FWD = re.compile(r"^(R?A?(?:NLD|WLD|HLD|BLD|TLD|TALD|LD)\d{1,2}-\d{3,6})(?:/(\d{1,2}))?$")


def run_of(code: str) -> str:
    """เลขรันที่เซลล์พิมพ์รายงาน — "RTLD9-8129/1" → "8129" """
    m = re.search(r"-\s*(\d{3,6})", code or "")
    return m.group(1) if m else ""


def fwd_code(old: str) -> str:
    """เลขของ "ส่งต่อไม้ 2" — แบบที่ทีมใช้ในห้อง REJECT: **R + เลขเดิม + /1**
    เลขเดิมมี /n อยู่แล้ว = /n+1 · เลขนั้นถูกใช้แล้ว = ขยับต่อ · รูปแบบไม่ถูก = ""
    """
    from . import connect as C
    m = _FWD.match((old or "").strip().upper())
    if not m:
        return ""
    core, n = m.group(1), int(m.group(2) or 0)
    if not core.startswith("R"):
        core = "R" + core
    for i in range(n + 1, n + 10):
        code = "%s/%d" % (core, i)
        if not C.code_taken(code) and not LeadTask.objects.filter(code__iexact=code).exists():
            return code
    return ""


# ─────────────────────────────────────────────────────────────
#  คิวจ่ายวน (round-robin)
# ─────────────────────────────────────────────────────────────
def _today_counts(day=None) -> dict:
    day = day or timezone.localdate()
    start = timezone.make_aware(datetime.combine(day, datetime.min.time()))
    rows = (LeadTask.objects.filter(created_at__gte=start, seller__isnull=False)
            .values("seller_id").annotate(n=Count("id"), last=Max("created_at")))
    return {r["seller_id"]: (r["n"], r["last"]) for r in rows}


def rr_candidates(c=None, exclude=(), day=None) -> list:
    """เซลล์ที่รับใบได้ตอนนี้ เรียงคนได้น้อยสุดก่อน (เท่ากัน = คนที่ได้ใบล่าสุดนานกว่าก่อน)

    ตัด: ไม่ได้อยู่ทีมในคิว · บัญชีทดสอบ · วันหยุดของคนนั้น · ยังไม่เช็คชื่อ (ถ้าตั้งไว้) · เต็มเพดานวันนี้
    คืน `[{id, name, team, today, emp}]` · ทุกคนถูกตัด = ลิสต์ว่าง (ผู้เรียกต้องบอกเหตุผล)
    """
    from . import connect as C
    from .checkin_report import THAI_DAYS
    c = c or cfg()
    day = day or timezone.localdate()
    dname = THAI_DAYS[day.weekday()]
    checked = set()
    if c["need_checkin"]:
        try:
            from .models import CheckIn
            checked = set(CheckIn.objects.filter(date_iso=day, employee__isnull=False)
                          .values_list("employee_id", flat=True))
        except Exception:
            checked = set()
    counts = _today_counts(day)
    ex = {int(x) for x in exclude if x}
    epoch = timezone.make_aware(datetime(2000, 1, 1))
    out = []
    for e in Employee.objects.filter(active=True):
        t = C.team_of(e)
        if t not in c["rr_teams"] or e.id in ex or C.is_test_seller(e):
            continue
        if e.day_off and dname in e.day_off:
            continue
        if c["need_checkin"] and e.id not in checked:
            continue
        n, last = counts.get(e.id, (0, None))
        if c["cap_day"] and n >= c["cap_day"]:
            continue
        out.append({"id": e.id, "name": e.nickname, "team": t, "today": n, "_last": last or epoch, "emp": e})
    out.sort(key=lambda r: (r["today"], r["_last"], r["name"]))
    return out


def rr_pick(exclude=(), c=None):
    cand = rr_candidates(c, exclude=exclude)
    return cand[0]["emp"] if cand else None


def rr_json(c=None, n: int = 4) -> list:
    """คิวถัดไปให้หน้าเว็บ — ไม่มี emp/LINE id"""
    return [{"id": r["id"], "name": r["name"], "team": r["team"], "today": r["today"]}
            for r in rr_candidates(c)[:n]]


# ─────────────────────────────────────────────────────────────
#  เช็คเบอร์ซ้ำ (แอดมินก่อนจ่าย)
# ─────────────────────────────────────────────────────────────
def dup_info(phone, exclude_code: str = "") -> dict | None:
    """เบอร์นี้เคยเป็นลีดของใคร → `{seller, code, date, channel, more}` · ไม่ซ้ำ/ไม่มีเบอร์ = None"""
    from . import phonebook
    try:
        hits = phonebook.lookup(phone, exclude_code)
    except Exception:
        return None
    if not hits:
        return None
    top = next((h for h in hits if h["seller"]), hits[0])
    seller = "เทเลเซลล์" if top["seller"] == "ADMIN" else top["seller"]
    return {"seller": seller, "code": top["code"], "date": top["date"], "channel": top["channel"],
            "car": top["car"], "more": max(0, len(hits) - 1),
            "sellerId": _emp_id(top["seller"])}


def _emp_id(nick: str):
    if not nick:
        return None
    e = Employee.objects.filter(nickname=nick, active=True).only("id").first()
    return e.id if e else None


# ─────────────────────────────────────────────────────────────
#  การ์ดปุ่ม (postback ลงชื่อ HMAC)
# ─────────────────────────────────────────────────────────────
def _sig(action: str, oid) -> str:
    from django.conf import settings
    raw = ("%s:%s" % (action, oid)).encode()
    return hmac.new((settings.SECRET_KEY or "x").encode(), raw, hashlib.sha256).hexdigest()[:12]


def _pb(action: str, oid, key: str = "t") -> str:
    return "lf=%s&%s=%s&s=%s" % (action, key, oid, _sig(action, oid))


def _tel(phone: str) -> str:
    from . import phonebook
    p = phonebook.norm(phone)
    return ("tel:" + p) if p else ""


def card_message(task: LeadTask) -> dict:
    """การ์ดต่อท้ายใบจ่ายลีด: ต้องรายงานผลภายใน HH:MM · ปุ่ม รับเคส / ขอผ่าน / โทร

    การ์ดใน LINE แก้ย้อนหลังไม่ได้ → บอก "ภายในกี่โมง" ไม่ใช่นับถอยหลัง
    """
    due = _hm(task.due_at) or "-"
    btns = [{"type": "button", "style": "primary", "color": "#7c3aed", "height": "sm",
             "action": {"type": "postback", "label": "รับเคส", "data": _pb("ack", task.id)}},
            {"type": "button", "style": "secondary", "height": "sm",
             "action": {"type": "postback", "label": "ขอผ่าน", "data": _pb("pass", task.id)}}]
    tel = _tel(task.phone)
    if tel:
        btns.append({"type": "button", "style": "link", "height": "sm",
                     "action": {"type": "uri", "label": "โทรหาลูกค้า", "uri": tel}})
    return {"type": "flex", "altText": "รับเคส %s · รายงานผลภายใน %s น." % (task.code, due),
            "contents": {"type": "bubble", "size": "kilo",
                         "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                             {"type": "text", "text": task.code, "weight": "bold", "size": "md", "color": "#4c1d95"},
                             {"type": "text", "text": "@%s รายงานผลภายใน %s น." % (task.seller_name or "-", due),
                              "size": "sm", "wrap": True, "color": "#374151"},
                             {"type": "text", "text": "พิมพ์ \"%s + ผล\" ในห้องนี้ = นาฬิกาหยุด" % (task.run or "เลข"),
                              "size": "xs", "wrap": True, "color": "#6b7280"}]},
                         "footer": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": btns}}}


# ─────────────────────────────────────────────────────────────
#  สร้าง/อัปเดตงาน (เรียกจากปุ่มจ่ายเบอร์ · ใบในกลุ่ม)
# ─────────────────────────────────────────────────────────────
def _due(at, c=None):
    from . import connect as C
    c = c or cfg()
    cc = dict(C.cfg())
    cc["sla_min"] = c["call_min"]
    return C.due_for(at, cc)


def before_post(code: str, emp, by: str = "", chat=None, ext=None, phone: str = "", customer: str = "",
                car: str = "", demo: bool = False) -> tuple:
    """ก่อนส่งใบเข้ากลุ่ม (ปุ่มจ่ายเบอร์ในระบบ) → `(task, ข้อความเสริมที่ต่อท้ายใบ)`

    สร้างงานก่อนยิง เพราะการ์ดต้องมีเลขงานในปุ่ม · ส่งไม่สำเร็จ = งานยังไม่เริ่มนับ (`after_post`)
    ไม่โยน exception — พังแล้วใบยังต้องส่งได้ตามเดิม
    """
    from . import phonebook
    c = cfg()
    try:
        code = (code or "").strip().upper()
        if not code:
            return None, []
        t, _ = LeadTask.objects.get_or_create(code=code, defaults={"run": run_of(code), "source": LeadTask.SYSTEM})
        old = t.seller_id
        if old and emp and old != emp.id:
            hist = list(t.history or [])
            hist.append({"seller": t.seller_name, "at": _iso(timezone.now()),
                         "why": "จ่ายใหม่", "passed": bool(t.passed_at), "reports": t.reports})
            t.history = hist[-10:]
        t.seller, t.seller_name = emp, (emp.nickname if emp else "")[:80]
        t.by = (by or "")[:80]
        t.chat, t.ext = chat, ext
        t.customer, t.phone, t.car = (customer or "")[:120], (phonebook.norm(phone) or "")[:10], (car or "")[:120]
        t.run = run_of(code)
        t.source = LeadTask.SYSTEM
        t.acked_at = t.passed_at = t.first_report_at = t.overdue_at = None
        t.reports, t.last_report = 0, ""
        now = timezone.now()
        t.posted_at = now if demo else None
        t.due_at = _due(now, c) if demo else None
        t.card = {"demo": True} if demo else {}
        t.save()
        try:
            phonebook.note(phone, code, emp.nickname if emp else "", phonebook.LeadPhone.SYSTEM, car=car)
        except Exception:
            pass
        if demo or not c["card_on"]:
            return t, []
        t.due_at = _due(now, c)                  # ตัวเลขบนการ์ด = เวลาที่จะใช้จริงถ้าส่งสำเร็จตอนนี้
        return t, [card_message(t)]
    except Exception as e:                       # ใบยังต้องส่งได้ — แต่จดไว้ (พังเงียบ = ไม่มีใครรู้ว่านาฬิกาไม่เดิน)
        _note_error("before_post", e, code=code)
        return None, []


def after_post(task, info: dict, card: bool = False):
    """ส่งใบแล้ว → เริ่มนาฬิกาเมื่อถึงกลุ่มจริง · จดว่าการ์ดไปด้วยไหม"""
    if not task:
        return
    try:
        now = timezone.now()
        upd = {"card": {"sent": bool(card and info.get("ok")), "at": _iso(now), "ok": bool(info.get("ok"))}}
        if info.get("ok"):
            upd.update(posted_at=now, due_at=_due(now), group_id=(info.get("group") or "")[:64])
        LeadTask.objects.filter(pk=task.pk).update(**upd)
    except Exception:
        pass


def note_group_slip(g, d: dict) -> LeadTask | None:
    """ใบจ่ายลีดที่แอดมินโพสต์เองในห้องจ่ายเบอร์ → งาน (source=group) + สมุดเบอร์ — นาฬิกาครอบทุกใบ"""
    from . import connect as C
    from . import phonebook
    code = (d.get("lead_code") or "").strip().upper()
    if not code or not run_of(code):
        return None
    nick = C.tag_nick(d.get("assigned") or "") if d.get("assigned") else ""
    emp = Employee.objects.filter(nickname=nick, active=True).first() if nick else None
    try:
        phonebook.note(d.get("phone") or "", code, nick, phonebook.LeadPhone.SLIP,
                       seen_on=timezone.localtime(g.sent_at).date() if g.sent_at else None,
                       channel=d.get("channel") or "", car=d.get("car") or d.get("ads") or "")
    except Exception:
        pass
    if LeadTask.objects.filter(code=code).exists():
        return None                              # ระบบออกเลขนี้เอง (มีงานแล้ว) หรือเคยเห็นใบนี้แล้ว
    at = g.sent_at or timezone.now()
    try:
        return LeadTask.objects.create(
            code=code, run=run_of(code), source=LeadTask.GROUP, seller=emp, seller_name=(nick or "")[:80],
            by=(C._poster(g) or "")[:80], customer=(d.get("name") or d.get("account") or "")[:120],
            phone=(phonebook.norm(d.get("phone") or "") or "")[:10],
            car=(d.get("car") or d.get("ads") or "")[:120], group_id=(g.group_id or "")[:64],
            posted_at=at, due_at=_due(at))
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────
#  อ่านรายงานผล "เลข + ผล"
# ─────────────────────────────────────────────────────────────
_REPORT = re.compile(r"^\s*(\d{3,6})(?:\s*/\s*(\d{1,2}))?\s*(?=[^\d\s/])(.{2,})$", re.S)
_REPORT_STATUS = [
    (r"ได้รถ(?:ไป)?แล้ว|ซื้อ(?:ที่|คัน)อื่น(?:ไป)?แล้ว", "ได้รถแล้ว"),
    (r"จอง(?:แล้ว|เรียบร้อย)|โอนจอง|วางจอง|วางมัดจำ|มัดจำแล้ว", "จอง"),
    (r"ไม่มีรถ|รถไม่มี|หารถไม่ได้|ไม่มีรุ่น", "ไม่มีรถที่ลูกค้าสนใจ"),
    (r"รถ(?:คันนี้)?ขาย(?:ไป)?แล้ว|คันนี้ขายแล้ว", "รถขายไปแล้ว"),
    (r"ไม่สนใจแล้ว|ไม่เอาแล้ว|ไม่ซื้อแล้ว|เปลี่ยนใจ", "ลูกค้าไม่สนใจแล้ว"),
    (r"ติดต่อไม่ได้|เบอร์ผิด|ปิดเครื่อง|ไม่มีสัญญาณ|โทรไม่ติด|ไม่มีผู้ใช้", "ติดต่อไม่ได้"),
    (r"ไม่รับสาย|โทรไม่รับ|ยังไม่รับ(?!ซื้อ)|สายไม่ว่าง|ตัดสาย", "ไม่รับสาย"),
    (r"ลูกค้าไม่ตอบ|ไม่ตอบ(?:แชท|ไลน์|ข้อความ)?|อ่านไม่ตอบ|ทักแล้วเงียบ", "ลูกค้าไม่ตอบ"),
    (r"รอตอบ|รอลูกค้าตอบ|ทักไลน์ไป|แอดไลน์|ส่งไลน์", "รอตอบ"),
]
_REPORT_STATUS_RX = [(re.compile(p), k) for p, k in _REPORT_STATUS]
# สถานะที่ "มีความหมายพอจะถามยืนยัน" (ส่งการ์ดเข้าแชทส่วนตัว) — รอตอบ/ไม่รับสาย เฉยๆ ไม่ส่ง
RICH_STATUS = {"จอง", "ได้รถแล้ว", "ลูกค้าไม่สนใจแล้ว", "รอมาดูรถ", "ติดแบล็คลิส", "ไม่มีรถที่ลูกค้าสนใจ",
               "รถขายไปแล้ว", "หาคนออกให้", "รอเช็คเครดิต", "สนใจมาก", "ดาวน์ไม่พอ", "เงินสดเงินไม่พอ", "มีรถเทริน"}
FIELD_LABEL = {"customer_status": "สถานะลูกค้า", "occupation": "อาชีพ", "income": "รายได้",
               "job_tenure": "อายุงาน", "payment_history": "ประวัติผ่อน", "customer_type": "ประเภทลูกค้า"}


def parse_report(text: str):
    """"9075 รอตอบครับ" → ("9075", 0, "รอตอบครับ") · ไม่ใช่รายงาน = None

    ไม่นับ: ใบจ่ายลีด · ข้อความที่มี @ (แอดมินทวง "9075 @มัท ตามด้วย") · เลขที่เป็นเบอร์/ราคา (≥7 หลัก)
    """
    t = (text or "").strip()
    if not t or "@" in t or re.search(r"lead\s*no", t, re.I):
        return None
    m = _REPORT.match(t)
    if not m:
        return None
    body = m.group(3).strip()
    if len(body) < 2 or re.match(r"^[\d,.\s]+$", body):
        return None
    return m.group(1), int(m.group(2) or 0), body


def _status_of(body: str) -> tuple:
    from . import connect as C
    from . import lead_keywords as K
    opts = C.dd_options("customer_status")
    for rx, key in _REPORT_STATUS_RX:
        m = rx.search(body)
        if m:
            v = K.pick(opts, [key]) or (key if not opts else "")
            if v:
                return v, m.group(0)
    st = K.status_in(K.norm(body))
    if st:
        v = K.pick(opts, K.STATUS_SPELL.get(st[0], [st[0]]))
        if v:
            return v, st[1]
    return "", ""


def read_report(body: str, now=None) -> dict:
    """ข้อความรายงาน → `{fields: {ช่องชีต: ค่า}, why: {ช่อง: คำที่จับได้}, appt: iso, rich}`"""
    from . import connect as C
    from . import lead_keywords as K
    out, why = {}, {}
    st, w = _status_of(body)
    if st:
        out["customer_status"], why["customer_status"] = st, w
    got = K.extract([body])
    for src, dst in (("occupation", "occupation"), ("job_tenure", "job_tenure"), ("pay_history", "payment_history")):
        if src in got:
            out[dst], why[dst] = str(got[src][0])[:80], str(got[src][1])[:60]
    if "income" in got:
        try:
            out["income"] = "{:,}".format(int(got["income"][0]))
            why["income"] = str(got["income"][1])[:60]
        except Exception:
            pass
    if "customer_type" in got:
        v = K.pick(C.dd_options("customer_type"), K.TYPE_SPELL.get(got["customer_type"][0], []))
        if v:
            out["customer_type"], why["customer_type"] = v, str(got["customer_type"][1])[:60]
    appt = parse_appt(body, now)
    if appt and "customer_status" not in out:
        v = K.pick(C.dd_options("customer_status"), ["รอมาดูรถ"])
        if v and re.search(r"มาดู|เข้ามา|เข้าเต็นท์|มาที่ร้าน|มาเต็นท์", body):
            out["customer_status"], why["customer_status"] = v, "นัดมาดูรถ"
    rich = bool(appt) or any(k in out for k in ("occupation", "income", "job_tenure", "payment_history",
                                                "customer_type")) or out.get("customer_status") in RICH_STATUS
    return {"fields": out, "why": why, "appt": _iso(appt) if appt else "", "rich": rich}


# ── วันนัด ──
_TH_N = {"หนึ่ง": 1, "สอง": 2, "สาม": 3, "สี่": 4, "ห้า": 5, "หก": 6, "เจ็ด": 7, "แปด": 8, "เก้า": 9, "สิบ": 10,
         "สิบเอ็ด": 11, "เอ็ด": 1}
_N = r"(\d{1,2}|สิบเอ็ด|หนึ่ง|สอง|สาม|สี่|ห้า|หก|เจ็ด|แปด|เก้า|สิบ)"
_APPT_KW = re.compile(r"นัด|เข้ามา|มาดู|เข้าเต็นท์|มาเต็นท์|มาที่ร้าน|โทรกลับ|ติดต่อกลับ|จะมา|แวะมา|เข้าไปดู|ขอดูรถ")
_WD = [("จันทร์", 0), ("อังคาร", 1), ("พุธ", 2), ("พฤหัส", 3), ("ศุกร์", 4), ("เสาร์", 5), ("อาทิตย์", 6)]


def _num(s) -> int:
    s = (s or "").strip()
    return int(s) if s.isdigit() else _TH_N.get(s, 0)


def _appt_time(t: str):
    m = re.search(r"(?<![\d/])([01]?\d|2[0-3])\s*[:.]\s*([0-5]\d)(?!\d)", t)
    if m:
        return int(m.group(1)), int(m.group(2))
    if re.search(r"เที่ยง(?!คืน)", t):
        return 12, 0
    m = re.search(r"บ่าย\s*" + _N + r"?\s*(?:โมง)?", t)
    if m and (m.group(1) or "โมง" in m.group(0)):
        n = _num(m.group(1)) if m.group(1) else 1
        if 1 <= n <= 5:
            return 12 + n, 0
    m = re.search(_N + r"\s*ทุ่ม", t)
    if m and 1 <= _num(m.group(1)) <= 5:
        return 18 + _num(m.group(1)), 0
    m = re.search(_N + r"\s*โมง\s*(เย็น|เช้า|ครึ่ง)?", t)
    if m:
        n, part = _num(m.group(1)), m.group(2) or ""
        if part == "เย็น" and 1 <= n <= 6:
            return 12 + n, 0
        if 7 <= n <= 11:
            return n, (30 if part == "ครึ่ง" else 0)
        if 1 <= n <= 6 and part != "เช้า":
            return 12 + n, (30 if part == "ครึ่ง" else 0)
    return None


def parse_appt(text: str, now=None):
    """วัน-เวลานัดในรายงาน ("นัดมาดูรถเสาร์ 10 โมง" · "พรุ่งนี้บ่ายสอง") → datetime โซนไทย · ไม่ชัด = None

    ต้องมีคำว่านัด/เข้ามา/มาดู… ก่อน (กันเลขเวลาลอยๆ เช่นราคา) · บอกแต่วัน = 10:00 · บอกแต่เวลา = วันนี้
    """
    t = text or ""
    if not _APPT_KW.search(t):
        return None
    now = timezone.localtime(now or timezone.now())
    today = now.date()
    day = None
    if re.search(r"มะรืน", t):
        day = today + timedelta(days=2)
    elif re.search(r"พรุ่งนี้|พรุ่งนี้", t):
        day = today + timedelta(days=1)
    elif re.search(r"วันนี้|เย็นนี้|บ่ายนี้|คืนนี้", t):
        day = today
    if day is None:
        for name, wd in _WD:
            m = re.search(r"(?:วัน)?" + name + r"(?:บดี)?\s*(หน้า)?", t)
            if m:
                ahead = (wd - today.weekday()) % 7
                day = today + timedelta(days=ahead + (7 if m.group(1) else 0))
                break
    if day is None:
        m = re.search(r"(?<!\d)(\d{1,2})\s*/\s*(\d{1,2})(?:\s*/\s*(\d{2,4}))?(?!\d)", t)
        if m:
            d, mo = int(m.group(1)), int(m.group(2))
            y = today.year
            if m.group(3):
                y = int(m.group(3))
                y = y + 2500 if y < 100 else y
                y = y - 543 if y > 2400 else y
            try:
                day = date(y, mo, d)
                if not m.group(3) and day < today - timedelta(days=7):
                    day = date(y + 1, mo, d)
            except ValueError:
                day = None
    hm = _appt_time(t)
    if day is None and hm is None:
        return None
    if day is None:
        day = today
    if hm is None:
        hm = (10, 0)
    dt = timezone.make_aware(datetime(day.year, day.month, day.day, hm[0], hm[1]))
    if dt < now - timedelta(minutes=30):
        return None                              # เวลาที่ผ่านไปแล้ว — น่าจะอ่านผิด ไม่เดา
    return dt


# ─────────────────────────────────────────────────────────────
#  จับคู่รายงานกับงาน
# ─────────────────────────────────────────────────────────────
def _emp_of_uid(uid: str):
    if not uid:
        return None
    p = (LineProfile.objects.filter(user_id=uid, employee__isnull=False)
         .select_related("employee").first())
    return p.employee if p and p.employee.active else None


def _task_for(run: str, slash: int, emp=None):
    """งานของเลขรันนี้ · /n = เคสส่งต่อ (ขึ้นต้น R) · หลายงานเลขเดียวกัน = ของคนรายงานก่อน แล้วค่อยงานจริงล่าสุด"""
    qs = LeadTask.objects.filter(run=run).order_by("-posted_at", "-id")
    rows = list(qs[:10])
    if not rows:
        return None
    if slash:
        rows = [t for t in rows if t.code.upper().startswith("R")] or rows
    rows.sort(key=lambda t: (not (emp and t.seller_id == emp.id), bool((t.card or {}).get("demo")),
                             -(t.posted_at.timestamp() if t.posted_at else 0)))
    return rows[0]


def _lazy_task(run: str, slash: int):
    """ไม่มีงานของเลขนี้ (ใบเก่าก่อนเปิดระบบ) → หาใบในห้องจ่ายเบอร์ย้อน 60 วัน แล้วสร้างงานย้อนหลัง"""
    from . import connect as C
    from .leadgroup import parse_leadsheet
    gids = C._lead_group_ids()
    if not gids:
        return None
    since = timezone.now() - timedelta(days=60)
    for g in (GroupChat.objects.filter(chat_type=GroupChat.GROUP, group_id__in=gids, sent_at__gte=since,
                                       text__icontains="-" + run).order_by("-sent_at")[:8]):
        d = parse_leadsheet(g.text or "")
        if not d or run_of(d.get("lead_code") or "") != run:
            continue
        if slash and not d["lead_code"].startswith("R"):
            continue
        t = note_group_slip(g, d)
        return t or LeadTask.objects.filter(code=d["lead_code"]).first()
    return None


def handle_report(g) -> LeadReport | None:
    """ข้อความในห้องจ่ายเบอร์ 1 แถว → รายงานผล (ถ้าใช่) · ซ้ำ message id = ข้าม"""
    from . import connect as C
    p = parse_report(g.text or "")
    if not p:
        return None
    run, slash, body = p
    emp = _emp_of_uid(g.sender_id or "")
    if not emp or not C.team_of(emp):            # คนที่ไม่ใช่ทีมขาย (แอดมิน/ออฟฟิศ) ไม่ใช่รายงานผล
        return None
    if LeadReport.objects.filter(message_id=g.message_id).exists():
        return None
    task = _task_for(run, slash, emp) or _lazy_task(run, slash)
    at = g.sent_at or timezone.now()
    info = read_report(body, at)
    appt = None
    if info["appt"]:
        try:
            appt = datetime.fromisoformat(info["appt"])
        except Exception:
            appt = None
    try:
        r = LeadReport.objects.create(
            message_id=g.message_id, task=task, code=task.code if task else "", seller=emp,
            seller_name=emp.nickname[:80], text=(g.text or "")[:2000], sent_at=at,
            fields={"fields": info["fields"], "why": info["why"], "rich": info["rich"]}, appt_at=appt)
    except Exception:
        return None                              # ซ้ำ (อีก worker ทำไปแล้ว)
    if task:
        upd = {"reports": task.reports + 1, "last_report_at": at, "last_report": body[:300]}
        if not task.first_report_at:
            upd["first_report_at"] = at
        LeadTask.objects.filter(pk=task.pk).update(**upd)
    return r


def note_chat_reply(o, at=None):
    """เซลล์ตอบลูกค้าผ่าน Connect = ติดต่อแล้ว → นาฬิกาของงานแชทนี้หยุด (ไม่นับเป็นรายงาน)"""
    try:
        at = at or timezone.now()
        (LeadTask.objects.filter(chat=o, first_report_at__isnull=True, posted_at__isnull=False)
         .update(first_report_at=at, last_report_at=at, last_report="ตอบลูกค้าผ่าน Connect"))
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
#  ประมวลผลข้อความในห้องจ่ายเบอร์ (ตัวชี้ GroupChat.id — webhook + cron เก็บตก)
# ─────────────────────────────────────────────────────────────
KV_STATE = "leadflow_state"
_LOCK_KEY = 7_406_062


class _Lock:
    def __init__(self):
        self.got = False

    def __enter__(self):
        from django.db import connection
        if connection.vendor != "postgresql":
            self.got = True
            return self
        with connection.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", [_LOCK_KEY])
            self.got = bool(cur.fetchone()[0])
        return self

    def __exit__(self, *a):
        from django.db import connection
        if self.got and connection.vendor == "postgresql":
            try:
                with connection.cursor() as cur:
                    cur.execute("SELECT pg_advisory_unlock(%s)", [_LOCK_KEY])
            except Exception:
                pass
        return False


def _cursor() -> int:
    st = _kv(KV_STATE)
    if isinstance(st.get("last_id"), int):
        return st["last_id"]
    # ครั้งแรก = เริ่มจากข้อความ 1 ชม.ล่าสุด (ไม่ไล่ประวัติทั้งหมด — ของเก่าถูกสร้างงานย้อนหลังเมื่อมีรายงานเข้ามา)
    since = timezone.now() - timedelta(hours=1)
    return GroupChat.objects.filter(sent_at__lt=since).aggregate(m=Max("id"))["m"] or 0


def process_pending(limit: int = 200) -> dict:
    """ข้อความใหม่ในห้องจ่ายเบอร์ → ใบจ่ายลีด (งาน+สมุดเบอร์) / รายงานผล (+การ์ดยืนยัน)"""
    from . import connect as C
    from .leadgroup import parse_leadsheet
    out = {"slips": 0, "reports": 0, "asked": 0}
    with _Lock() as lk:
        if not lk.got:
            return {"skipped": "อีกตัวกำลังทำอยู่"}
        last = _cursor()
        gids = C._lead_group_ids()
        rows = list(GroupChat.objects.filter(id__gt=last).order_by("id").values_list("id", flat=True)[:limit])
        if not rows:
            return out
        msgs = list(GroupChat.objects.filter(id__in=rows, chat_type=GroupChat.GROUP, group_id__in=gids,
                                             direction=GroupChat.IN, msg_type="text").order_by("id"))
        c = cfg()
        for g in msgs:
            try:
                d = parse_leadsheet(g.text or "")
                if d:
                    if note_group_slip(g, d):
                        out["slips"] += 1
                    continue
                r = handle_report(g)
                if r:
                    out["reports"] += 1
                    if c["report_on"] and (r.fields or {}).get("rich") and r.task_id:
                        if ask_confirm(r):
                            out["asked"] += 1
            except Exception:
                continue
        _set_kv(KV_STATE, {"last_id": rows[-1], "at": _iso(timezone.now()), **out})
    return out


_BG = {"busy": False, "at": 0.0}


def _bg(fn, *a):
    if _BG["busy"]:
        return False
    _BG["busy"] = True

    def run():
        try:
            fn(*a)
        except Exception:
            pass
        finally:
            _BG["busy"] = False
            try:
                from django.db import connection
                connection.close()
            except Exception:
                pass
    threading.Thread(target=run, daemon=True).start()
    return True


# ─────────────────────────────────────────────────────────────
#  การ์ดยืนยันรายงาน (แชทส่วนตัวเซลล์) → ลงชีต
# ─────────────────────────────────────────────────────────────
def _dm_uid(emp) -> str:
    """ไอดีของเซลล์ฝั่งบัญชีที่ส่งแชทส่วนตัว (`push_line_message` แปลงให้ตรงฝั่งอีกชั้น)"""
    from .checkin_report import _pick_id, push_channel
    profs = list(LineProfile.objects.filter(employee=emp).order_by("-last_seen"))
    return _pick_id(profs, push_channel()) or (profs[0].user_id if profs else "")


def confirm_message(r: LeadReport) -> dict:
    f = (r.fields or {}).get("fields") or {}
    rows = [{"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
        {"type": "text", "text": FIELD_LABEL.get(k, k), "size": "xs", "color": "#6b7280", "flex": 3},
        {"type": "text", "text": str(v), "size": "sm", "wrap": True, "flex": 5, "color": "#111827"}]}
        for k, v in f.items()]
    if r.appt_at:
        lt = timezone.localtime(r.appt_at)
        rows.append({"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
            {"type": "text", "text": "นัด", "size": "xs", "color": "#6b7280", "flex": 3},
            {"type": "text", "text": "%d/%d %s น. (เตือนก่อนถึงเวลา)" % (lt.day, lt.month, lt.strftime("%H:%M")),
             "size": "sm", "wrap": True, "flex": 5}]})
    return {"type": "flex", "altText": "บันทึกรายงาน %s ลงชีต?" % r.code,
            "contents": {"type": "bubble", "size": "kilo",
                         "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": [
                             {"type": "text", "text": "บันทึกลงชีตลีด?", "weight": "bold", "color": "#4c1d95"},
                             {"type": "text", "text": "%s · \"%s\"" % (r.code, (r.text or "")[:80]),
                              "size": "xs", "wrap": True, "color": "#6b7280"},
                             {"type": "separator", "margin": "sm"}] + rows},
                         "footer": {"type": "box", "layout": "horizontal", "spacing": "sm", "contents": [
                             {"type": "button", "style": "primary", "color": "#7c3aed", "height": "sm",
                              "action": {"type": "postback", "label": "ถูกต้อง บันทึก", "data": _pb("ok", r.id, "r")}},
                             {"type": "button", "style": "secondary", "height": "sm",
                              "action": {"type": "postback", "label": "ไม่บันทึก", "data": _pb("no", r.id, "r")}}]}}}


def ask_confirm(r: LeadReport) -> bool:
    """ส่งการ์ดยืนยันเข้าแชทส่วนตัวเซลล์ (เฉพาะรายงานที่มีข้อมูลจริง)"""
    from dashboard.services.line_channels import dm_token
    from dashboard.services.line_notify import push_line_message
    if not r.seller_id or not r.code:
        return False
    uid = _dm_uid(r.seller)
    if not uid:
        LeadReport.objects.filter(pk=r.pk).update(state=LeadReport.FAILED,
                                                  saved={"error": "ยังไม่มีไอดี LINE ของเซลล์"})
        return False
    sc, body = push_line_message(uid, [confirm_message(r)], dm_token(), what=WHAT_CARD)
    if sc == 200:
        LeadReport.objects.filter(pk=r.pk).update(state=LeadReport.ASKED, asked_at=timezone.now())
        return True
    LeadReport.objects.filter(pk=r.pk).update(state=LeadReport.FAILED,
                                              saved={"error": "LINE %s %s" % (sc, (body or "")[:120])})
    return False


def save_report(r: LeadReport) -> dict:
    """เซลล์กด "ถูกต้อง" → เขียนช่องที่อ่านได้ลงชีตลีด (แถวที่เซลล์ในชีต = คนกด เท่านั้น)"""
    from dashboard.services.constants import normalize_seller
    from dashboard.services.google_sheets import update_lead_fields
    f = dict((r.fields or {}).get("fields") or {})
    if not f:
        return {"error": "ไม่มีข้อมูลให้บันทึก"}
    month = timezone.localtime(r.sent_at).month if r.sent_at else None
    res = update_lead_fields(r.code, f, month, expected_seller=normalize_seller(r.seller_name))
    _mirror_chat_lead(r, f)
    return res


def _mirror_chat_lead(r: LeadReport, f: dict):
    """ลูกค้าแชทของงานนี้ — เติมช่องเดียวกันในข้อมูลลีดของ Connect (เฉพาะช่องที่คนยังไม่แก้)"""
    try:
        from . import connect as C
        t = r.task
        if not t or not t.chat_id:
            return
        lead = C.lead_of(t.chat)
        auto = dict(lead.auto or {})
        m = {"customer_status": "customer_status", "occupation": "occupation", "income": "income",
             "job_tenure": "job_tenure", "payment_history": "pay_history", "customer_type": "customer_type"}
        ch = []
        for k, attr in m.items():
            if k in f and hasattr(lead, attr) and auto.get(attr) != C.HUMAN:
                setattr(lead, attr, str(f[k])[:120])
                auto[attr] = "รายงานเซลล์"
                ch.append(attr)
        if ch:
            lead.auto = auto
            lead.save()
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
#  postback (ปุ่มในการ์ด) — มาทาง webhook เดียวกับข้อความ
# ─────────────────────────────────────────────────────────────
def _reply(token: str, reply_token: str, text: str):
    """ตอบผ่าน reply token (ฟรี ไม่นับโควต้า) · ต้องใช้ token ของบอทที่ได้รับ event"""
    import requests
    if not (token and reply_token and text):
        return
    try:
        requests.post("https://api.line.me/v2/bot/message/reply",
                      headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
                      json={"replyToken": reply_token, "messages": [{"type": "text", "text": text[:1000]}]},
                      timeout=8)
    except Exception:
        pass


def _parse_pb(data: str) -> dict:
    out = {}
    for part in (data or "").split("&"):
        k, _, v = part.partition("=")
        if k:
            out[k] = v
    return out


def handle_postback(ev: dict, token: str = "") -> str:
    """กดปุ่มในการ์ด → ข้อความที่ตอบกลับ ("" = ไม่ใช่ปุ่มของเรา) · ตอบผ่าน reply token"""
    p = _parse_pb(((ev.get("postback") or {}).get("data")) or "")
    act = p.get("lf") or ""
    if act not in ("ack", "pass", "ok", "no"):
        return ""
    oid = p.get("t") or p.get("r") or ""
    if not oid.isdigit() or not hmac.compare_digest(p.get("s") or "", _sig(act, oid)):
        msg = "ปุ่มนี้ใช้ไม่ได้แล้ว"
    else:
        uid = ((ev.get("source") or {}).get("userId")) or ""
        emp = _emp_of_uid(uid)
        msg = _act_task(act, int(oid), emp) if act in ("ack", "pass") else _act_report(act, int(oid), emp)
    _reply(token, ev.get("replyToken") or "", msg)
    _set_kv("leadflow_postback_last", {"at": _iso(timezone.now()), "act": act, "msg": msg[:120]})
    return msg


def _act_task(act: str, tid: int, emp) -> str:
    t = LeadTask.objects.filter(pk=tid).select_related("seller").first()
    if not t:
        return "ไม่พบงานนี้แล้ว"
    if not emp:
        return "ยังไม่รู้ว่าบัญชี LINE นี้เป็นใคร — แจ้งแอดมินให้ผูกชื่อในหน้าพนักงาน"
    if t.seller_id != emp.id:
        return "เคส %s เป็นของ %s — ปุ่มนี้กดได้เฉพาะคนที่ได้รับเคส" % (t.code, t.seller_name or "-")
    now = timezone.now()
    if act == "ack":
        if t.passed_at:
            return "เคส %s กดขอผ่านไปแล้ว" % t.code
        if t.acked_at:
            return "รับเคส %s ไปแล้ว · พิมพ์ \"%s + ผล\" เมื่อติดต่อแล้ว" % (t.code, t.run)
        LeadTask.objects.filter(pk=t.pk).update(acked_at=now)
        return "✓ %s รับเคส %s แล้ว · รายงานผลภายใน %s น." % (emp.nickname, t.code, _hm(t.due_at) or "-")
    if t.passed_at:
        return "กดขอผ่านเคส %s ไปแล้ว" % t.code
    if t.first_report_at:
        return "เคส %s รายงานผลไปแล้ว — ถ้าจะคืนเคสให้แจ้งแอดมิน" % t.code
    LeadTask.objects.filter(pk=t.pk).update(passed_at=now)
    c = cfg()
    if c["auto_pull"] and t.source == LeadTask.SYSTEM and (t.chat_id or t.ext_id):
        t.refresh_from_db()
        ok, m = reassign(t, None, by="จ่ายใหม่อัตโนมัติ (ขอผ่าน)")
        if ok:
            return "%s ขอผ่านเคส %s · %s" % (emp.nickname, t.code, m)
    return "%s ขอผ่านเคส %s — แอดมินจ่ายใหม่ได้ที่หน้า Connect" % (emp.nickname, t.code)


def _act_report(act: str, rid: int, emp) -> str:
    r = LeadReport.objects.filter(pk=rid).select_related("task", "seller").first()
    if not r:
        return "ไม่พบรายงานนี้แล้ว"
    if not emp or r.seller_id != emp.id:
        return "การ์ดนี้เป็นของ %s" % (r.seller_name or "-")
    if r.state in (LeadReport.SAVED, LeadReport.SKIPPED):
        return "รายงานนี้ %s ไปแล้ว" % ("บันทึก" if r.state == LeadReport.SAVED else "ข้าม")
    now = timezone.now()
    if act == "no":
        LeadReport.objects.filter(pk=r.pk).update(state=LeadReport.SKIPPED, done_at=now, appt_at=None)
        return "ไม่บันทึก %s — ถ้าจะแก้เองให้กรอกในหน้าเซลล์" % r.code
    res = save_report(r)
    if res.get("error"):
        LeadReport.objects.filter(pk=r.pk).update(state=LeadReport.FAILED, done_at=now, saved=res)
        return "ลงชีตไม่สำเร็จ: %s" % res["error"][:200]
    LeadReport.objects.filter(pk=r.pk).update(state=LeadReport.SAVED, done_at=now, saved=res)
    tail = ""
    if r.appt_at:
        tail = " · จะเตือนนัดก่อนถึงเวลา" if cfg()["remind_on"] else ""
    return "✓ บันทึก %s ลงชีตแล้ว (%s)%s" % (r.code, res.get("tab") or "-", tail)


def handle_events(data) -> dict:
    """เรียกจาก webhook (`_checkout_ingest` · thread) — ปุ่มในการ์ด + ข้อความใหม่ในห้องจ่ายเบอร์"""
    from dashboard.services import line_channels as LC
    out = {}
    evs = (data or {}).get("events") or [] if isinstance(data, dict) else []
    pbs = [e for e in evs if isinstance(e, dict) and e.get("type") == "postback"]
    if pbs:
        key = LC.channel_of((data or {}).get("destination") or "")
        token = LC.token_of(key) if key else LC.push_token()
        out["postbacks"] = [handle_postback(e, token) for e in pbs]
    if any(isinstance(e, dict) and e.get("type") == "message" for e in evs):
        out["pending"] = process_pending()
    return out


# ─────────────────────────────────────────────────────────────
#  จ่ายใหม่ (เลขเดิม) · ส่งต่อไม้ 2 (เลขใหม่ R…/1)
# ─────────────────────────────────────────────────────────────
def _exclude_ids(t: LeadTask) -> set:
    ids = {t.seller_id} if t.seller_id else set()
    for h in t.history or []:
        e = Employee.objects.filter(nickname=h.get("seller") or "").only("id").first()
        if e:
            ids.add(e.id)
    return ids


def reassign(t: LeadTask, emp=None, by: str = "") -> tuple:
    """จ่ายใหม่ให้คนอื่น **เลขเดิม** (เลยเวลา/ขอผ่าน) — ใบเดิมทุกช่อง แท็กคนใหม่ · emp=None = คนถัดไปในคิว"""
    from . import connect as C
    if t.source != LeadTask.SYSTEM or not (t.chat_id or t.ext_id):
        return False, "เคสนี้แอดมินโพสต์ใบเองในกลุ่ม — จ่ายใหม่ด้วยการโพสต์ใบในกลุ่ม หรือใช้ \"ส่งต่อไม้ 2\""
    emp = emp or rr_pick(exclude=_exclude_ids(t))
    if not emp:
        return False, "ไม่มีเซลล์ว่างในคิวจ่ายวน (ทุกคนหยุด/เต็มเพดาน/เคยได้เคสนี้แล้ว)"
    if t.seller_id == emp.id:
        return False, "เคสนี้เป็นของ %s อยู่แล้ว" % emp.nickname
    if t.chat_id:
        o = t.chat
        ok, msg = C.assign(o.id, emp, by=by, note="จ่ายใหม่ %s" % t.code)
        if not ok:
            return False, msg
        lead = C.lead_of(o)
        o.refresh_from_db()
        info = C._post_slip(o, lead, emp, by)
    else:
        e = t.ext
        e.seller, e.seller_name = emp, emp.nickname[:80]
        e.save(update_fields=["seller", "seller_name", "updated_at"])
        from .leadpark import _post
        info = _post(e, emp, by)
    from . import slippost
    return bool(info.get("ok")), slippost.summary(t.code, emp.nickname, info)


def forward_chat(o, emp, by: str = "") -> tuple:
    """ส่งต่อไม้ 2 ของลูกค้าแชท — เลข R+เดิม+/1 · โอนแชท · ใบเข้าห้อง REJECT"""
    from . import connect as C
    from . import slippost
    lead = C.lead_of(o)
    old = (lead.code or "").strip().upper()
    if not old:
        return False, "ลูกค้ารายนี้ยังไม่มีเลขลีด — ใช้ปุ่มจ่ายเบอร์ปกติ"
    if not emp or not emp.active:
        return False, "เลือกเซลล์ที่จะส่งต่อให้ก่อน"
    new = fwd_code(old)
    if not new:
        return False, "เลข %s ส่งต่อไม่ได้ (รูปแบบไม่ใช่เลขลีด)" % old
    real = C.slip_post_on() and not C.is_sim_row(o) and not C.is_test_seller(emp)
    try:
        with C.code_lock():
            lead = type(lead).objects.get(pk=lead.pk)
            if C.code_taken(new, chat_lead_pk=lead.pk):
                raise C._Undo("เลข %s ถูกใช้แล้ว" % new)
            auto = dict(lead.auto or {})
            prev = list(auto.get("_prev_codes") or [])
            prev.append({"code": old, "seller": o.owner.nickname if o.owner_id else "", "at": _iso(timezone.now())})
            auto["_prev_codes"] = prev[-5:]
            auto["code"] = "ส่งต่อไม้ 2" if real else "ส่งต่อไม้ 2(ทดลอง)"
            lead.auto, lead.code, lead.code_demo = auto, new, not real
            lead.assigned_at, lead.assigned_by = timezone.now(), (by or "")[:80]
            lead.post_info = {"sending": timezone.now().isoformat()} if real else {}
            lead.save()
            if o.owner_id != emp.id:
                ok, msg = C.assign(o.id, emp, by=by, note="ส่งต่อไม้ 2 %s → %s" % (old, new))
                if not ok:
                    raise C._Undo(msg)
    except C._Undo as e:
        return False, str(e)
    o.refresh_from_db()
    if not real:
        before_post(new, emp, by, chat=o, phone=lead.phone, customer=lead.customer_name or lead.account,
                    car=lead.car_model or lead.car_text, demo=True)
        return True, "ส่งต่อไม้ 2: %s → %s ให้ %s แล้ว (ไม่ส่งเข้ากลุ่มจริง)" % (old, new, emp.nickname)
    info = C._post_slip(o, lead, emp, by)
    return bool(info.get("ok")), "ส่งต่อไม้ 2 %s → " % old + slippost.summary(new, emp.nickname, info)


def forward_ext(mid: str, emp, by: str = "") -> tuple:
    """ส่งต่อไม้ 2 ของลีดในห้องพัก (จ่ายไปแล้ว) — ExtLead เดิมเปลี่ยนเป็นเลขใหม่ + เซลล์ใหม่"""
    from . import connect as C
    from .leadpark import _post, forget
    e = ExtLead.objects.select_related("seller").filter(message_id=str(mid or "")).first()
    if not e or not e.code:
        return False, "ลีดนี้ยังไม่ได้จ่ายเบอร์ — ใช้ปุ่มจ่ายเบอร์ปกติ"
    if not emp or not emp.active:
        return False, "เลือกเซลล์ที่จะส่งต่อให้ก่อน"
    old = e.code.upper()
    new = fwd_code(old)
    if not new:
        return False, "เลข %s ส่งต่อไม่ได้" % old
    with C.code_lock():
        e = ExtLead.objects.get(pk=e.pk)
        if C.code_taken(new, ext_pk=e.pk):
            return False, "เลข %s ถูกใช้แล้ว" % new
        e.code, e.seller, e.seller_name = new, emp, emp.nickname[:80]
        e.assigned_at, e.assigned_by = timezone.now(), (by or "")[:80]
        e.code_demo = C.is_test_seller(emp) or not C.slip_post_on()
        e.post_info = {} if e.code_demo else {"sending": timezone.now().isoformat()}
        e.more = ("%s · ไม้ 2 จาก %s" % (e.more or "", old)).strip(" ·")[:1000]
        e.save()
    forget()
    if e.code_demo:
        before_post(new, emp, by, ext=e, phone=e.phone, customer=e.customer_name or e.account,
                    car=e.car_text, demo=True)
        return True, "ส่งต่อไม้ 2: %s → %s ให้ %s แล้ว (ไม่ส่งเข้ากลุ่มจริง)" % (old, new, emp.nickname)
    info = _post(e, emp, by)
    from . import slippost
    return bool(info.get("ok")), "ส่งต่อไม้ 2 %s → " % old + slippost.summary(new, emp.nickname, info)


# ─────────────────────────────────────────────────────────────
#  cron (ทุกนาที · ผ่าน connect.tick)
# ─────────────────────────────────────────────────────────────
def tick(now=None) -> dict:
    """เลยเวลา (จด) · จ่ายใหม่อัตโนมัติ · จ่ายวน · เตือนนัด · เก็บตกข้อความ · สมุดเบอร์จากชีต · ลบของเก่า"""
    now = now or timezone.now()
    c = cfg()
    out = {}
    try:
        n = (LeadTask.objects.filter(posted_at__isnull=False, due_at__lte=now, first_report_at__isnull=True,
                                     passed_at__isnull=True, overdue_at__isnull=True).update(overdue_at=now))
        if n:
            out["overdue"] = n
    except Exception as e:
        out["overdueError"] = str(e)[:120]
    if c["auto_pull"]:
        try:
            out["pulled"] = _auto_pull(c, now)
        except Exception as e:
            out["pullError"] = str(e)[:120]
    if c["auto_assign"]:
        try:
            out["autoAssign"] = _auto_assign(c, now)
        except Exception as e:
            out["autoError"] = str(e)[:120]
    if c["remind_on"]:
        try:
            out["reminded"] = _remind(c, now)
        except Exception as e:
            out["remindError"] = str(e)[:120]
    try:
        r = process_pending()
        if r.get("slips") or r.get("reports"):
            out["pending"] = r
    except Exception as e:
        out["pendingError"] = str(e)[:120]
    try:
        _slow_bg(now)
    except Exception:
        pass
    return out


def _auto_pull(c, now) -> list:
    """เลยเวลาไม่รายงาน / กดขอผ่าน → จ่ายใหม่คนถัดไป (เลขเดิม) · ทีละ 2 ใบต่อนาที · ใบละไม่เกิน pull_max ครั้ง"""
    done = []
    qs = (LeadTask.objects.filter(source=LeadTask.SYSTEM, first_report_at__isnull=True)
          .filter(Q(overdue_at__isnull=False) | Q(passed_at__isnull=False))
          .filter(Q(chat__isnull=False) | Q(ext__isnull=False))
          .order_by("due_at")[:20])
    for t in qs:
        # ใบทดลอง (ไม่ได้ส่งเข้ากลุ่ม) ไม่จ่ายวน — กรองใน Python: exclude() บนคีย์ JSON ที่ไม่มีอยู่
        #   ตัดแถวทิ้งหมดบน SQLite (NULL) → เทสต์จับได้ว่าไม่มีใบไหนถูกจ่ายใหม่เลย
        if (t.card or {}).get("demo") or len(t.history or []) >= c["pull_max"]:
            continue
        ok, msg = reassign(t, None, by="จ่ายใหม่อัตโนมัติ")
        done.append({"code": t.code, "ok": ok, "msg": msg[:120]})
        if len(done) >= 2:
            break
    return done


def _auto_assign(c, now) -> list:
    """ใบร่างในห้องพัก Lead ที่รอเกิน auto_after_min → จ่ายวนให้คนถัดไป · **เบอร์ซ้ำ = ข้าม (ให้แอดมินตัดสิน)**

    ลูกค้าแชทใน Connect ไม่จ่ายอัตโนมัติ (ยังต้องดูว่าเป็นลีดขายจริงไหม) — หน้าเว็บแค่เลือกคนถัดไปในคิวไว้ให้
    """
    from . import leadpark
    done, skipped = [], []
    b = leadpark.board(cache_sec=0)
    for it in b.get("waiting") or []:
        if it.get("code") or (it.get("waitMin") or 0) < c["auto_after_min"]:
            continue
        phone = it.get("phone") or ""
        if phone and dup_info(phone):
            skipped.append({"id": it["id"], "why": "เบอร์ซ้ำ"})
            continue
        emp = rr_pick(c=c)
        if not emp:
            skipped.append({"id": it["id"], "why": "ไม่มีเซลล์ว่างในคิว"})
            break
        ok, msg, _e = leadpark.assign(it["id"], emp, it.get("base") or "NLD", admin=bool(it.get("admin")),
                                      reject=bool(it.get("reject")), by="จ่ายวนอัตโนมัติ")
        done.append({"id": it["id"], "ok": ok, "seller": emp.nickname, "msg": msg[:120]})
        if len(done) >= 3:
            break
    _set_kv("leadflow_auto_last", {"at": _iso(now), "done": done, "skipped": skipped[:20]})
    return done


def _remind(c, now) -> int:
    """นัดลูกค้าที่เซลล์ยืนยันแล้ว → เตือนเข้าแชทส่วนตัวก่อนถึงเวลา remind_min นาที (ครั้งเดียว)"""
    from dashboard.services.line_channels import dm_token
    from dashboard.services.line_notify import push_line_message
    n = 0
    soon = now + timedelta(minutes=c["remind_min"])
    for r in (LeadReport.objects.filter(state=LeadReport.SAVED, appt_at__isnull=False, appt_at__lte=soon,
                                        appt_at__gte=now - timedelta(minutes=5), reminded_at__isnull=True)
              .select_related("seller", "task")[:10]):
        if not LeadReport.objects.filter(pk=r.pk, reminded_at__isnull=True).update(reminded_at=now):
            continue
        uid = _dm_uid(r.seller) if r.seller_id else ""
        if not uid:
            continue
        t = r.task
        lt = timezone.localtime(r.appt_at)
        text = "⏰ นัดลูกค้า %s %s น.\n%s%s\nรายงานไว้: %s" % (
            r.code, lt.strftime("%H:%M"), (t.customer + " · ") if t and t.customer else "",
            ("โทร " + t.phone) if t and t.phone else "", (r.text or "")[:160])
        sc, _b = push_line_message(uid, [{"type": "text", "text": text}], dm_token(), what=WHAT_REMIND)
        n += 1 if sc == 200 else 0
    return n


_SLOW = {"at": 0.0}
BG_SLOW = True                      # เทสต์ปิดไว้ (thread วิ่งชนฐานข้อมูลทดสอบ SQLite) — เรียก _slow_work() ตรงแทน


def _slow_bg(now):
    """งานช้า (thread แยก): สมุดเบอร์จากชีตทุก 6 ชม. · ความต้องการลูกค้าจากห้องจ่ายเบอร์ทุก 30 นาที · ลบของเก่า"""
    if not BG_SLOW or time.time() - _SLOW["at"] < 600:
        return
    _SLOW["at"] = time.time()
    _bg(_slow_work)


def _slow_work():
    from . import phonebook
    if phonebook.due_rebuild():
        try:
            phonebook.rebuild_from_sheet()
        except Exception as e:
            _set_kv(phonebook.KV_LAST, {"at": _iso(timezone.now()), "error": str(e)[:200]})
    try:
        refresh_needs()
    except Exception as e:
        _note_error("refresh_needs", e)
    cleanup()


def cleanup(now=None) -> int:
    now = now or timezone.now()
    cut = now - timedelta(days=KEEP_DAYS)
    n1, _ = LeadReport.objects.filter(created_at__lt=cut).delete()
    n2, _ = LeadTask.objects.filter(created_at__lt=cut).delete()
    return n1 + n2


# ─────────────────────────────────────────────────────────────
#  ④ รถใหม่ตรงกับลูกค้าของฉัน
# ─────────────────────────────────────────────────────────────
KV_NEEDS = "leadflow_needs"
NEEDS_EVERY_MIN = 30


def refresh_needs(force: bool = False) -> dict:
    """อ่านห้องจ่ายเบอร์ต่อจากที่ค้าง → ความต้องการลูกค้า → จับคู่สต็อก → เก็บผลรายเซลล์ใน KV"""
    from . import connect as C
    from . import leadgroup, need_match
    st = _kv(KV_NEEDS)
    try:
        last = datetime.fromisoformat(st.get("at") or "")
        if not force and (timezone.now() - last).total_seconds() < NEEDS_EVERY_MIN * 60:
            return st
    except Exception:
        pass
    since = st.get("lastId")
    try:
        r = leadgroup.ingest(limit=3000, since_id=since if isinstance(since, int) else None)
        since = r.get("_last_id", since)
    except Exception as e:
        st["ingestError"] = str(e)[:160]
    by = {}
    try:
        for m in need_match.scan(mark=True):
            need = m["need"]
            nick = C.tag_nick(need.seller) if need.seller else ""
            if not nick:
                continue
            by.setdefault(nick, []).append({
                "code": m["leadCode"], "customer": m["customer"], "want": m["want"], "budget": m["budget"],
                "why": m["why"], "cars": [{"code": x.get("code"), "name": x.get("name"), "price": x.get("price"),
                                            "year": x.get("year")} for x in m["cars"][:3]]})
    except Exception as e:
        st["scanError"] = str(e)[:160]
    st.update(at=_iso(timezone.now()), lastId=since, bySeller=by)
    _set_kv(KV_NEEDS, st)
    return st


def seller_matches(nick: str) -> dict:
    from dashboard.services.constants import normalize_seller
    st = _kv(KV_NEEDS)
    rows = (st.get("bySeller") or {}).get(nick) or (st.get("bySeller") or {}).get(normalize_seller(nick)) or []
    return {"at": st.get("at") or "", "rows": rows[:30]}


# ─────────────────────────────────────────────────────────────
#  หน้าเว็บ (Connect → ห้องพัก Lead → แท็บ "นาฬิกาโทร")
# ─────────────────────────────────────────────────────────────
def task_state(t: LeadTask, now=None) -> dict:
    now = now or timezone.now()
    if (t.card or {}).get("demo"):
        kind = "demo"
    elif t.passed_at:
        kind = "passed"
    elif t.first_report_at:
        kind = "reported"
    elif not t.posted_at:
        kind = "unsent"
    elif t.due_at and now > t.due_at:
        kind = "overdue"
    else:
        kind = "waiting"
    left = int((t.due_at - now).total_seconds() // 60) if t.due_at else None
    return {"kind": kind, "leftMin": left}


def tasks_json(days: int = 1, now=None) -> list:
    now = now or timezone.now()
    since = timezone.make_aware(datetime.combine(timezone.localdate() - timedelta(days=days - 1),
                                                 datetime.min.time()))
    out = []
    for t in (LeadTask.objects.filter(created_at__gte=since).select_related("chat", "ext")
              .order_by("-posted_at", "-id")[:300]):
        s = task_state(t, now)
        out.append({"id": t.id, "code": t.code, "run": t.run, "source": t.source, "seller": t.seller_name,
                    "sellerId": t.seller_id, "by": t.by, "customer": t.customer, "car": t.car,
                    "postedAt": _iso(t.posted_at), "dueAt": _iso(t.due_at), "ackedAt": _iso(t.acked_at),
                    "passedAt": _iso(t.passed_at), "reportAt": _iso(t.first_report_at), "reports": t.reports,
                    "lastReport": t.last_report, "history": [h.get("seller") for h in (t.history or [])],
                    "chatId": t.chat_id, "extId": t.ext.message_id if t.ext_id else "",
                    "canReassign": t.source == LeadTask.SYSTEM and bool(t.chat_id or t.ext_id),
                    "card": bool((t.card or {}).get("sent")), **s})
    return out


def summary(now=None) -> dict:
    rows = tasks_json(1, now)
    cnt = {}
    for r in rows:
        cnt[r["kind"]] = cnt.get(r["kind"], 0) + 1
    return {"total": len(rows), "counts": cnt}
