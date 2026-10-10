# -*- coding: utf-8 -*-
"""ข้อมูลของ **ศูนย์ควบคุมลีด** (หน้า Connect แบบใหม่ · 10 ต.ค.69) — ฐานข้อมูล Lead · ไปป์ไลน์ · แดชบอร์ดทีม

เจ้าของสั่งเอาแบบหน้าจอ "ศูนย์ควบคุมลีด" มาแทน Connect เดิม (ของเดิมยังเปิดได้ที่ `?classic=1`)
ไฟล์นี้ทำแค่ "อ่าน + รวมตัวเลข" จากของที่ระบบมีอยู่แล้ว — ไม่มีตารางใหม่ ไม่ส่งอะไรออก:

  - **ฐานข้อมูล Lead** = แถวในชีตลีด (ทุกแท็บรายเดือน · `fetch_leads_by_month_tabs`) + ชื่อลูกค้า
    จากใบจ่ายลีด/แชท (ชีตลีดไม่มีช่องชื่อลูกค้า) + เบอร์ซ้ำ (`LeadPhone`) + ประวัติงานจ่ายเบอร์ (`LeadTask`)
  - **ไปป์ไลน์** = เคสจองจากชีตยอดขาย (`bookingCases` ในผลสรุปแดชบอร์ด · สถานะชุดเดียวกับรายงานฝ่ายขาย)
  - **แดชบอร์ดทีม** = งานจ่ายเบอร์วันนี้ (`LeadTask`) + เวลาตอบแชท (`ChatOwnerLog`) + จอง/ปล่อยเดือนนี้
    (ผลสรุปแดชบอร์ด) — **ไม่ใช้ตัวนับ "แชทเลยเวลา"** เพราะทีมตอบในแอป LINE OA Manager ซึ่ง LINE ไม่ส่งกลับมา
    (ตัวเลขนั้นไม่มีความหมาย — เจ้าของสั่งถอดแท็บเลยเวลาไปแล้ว 7 ต.ค.69)
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timedelta

from django.db.models import Count, Q
from django.utils import timezone

_ROWS = {"at": 0.0, "val": None}
ROWS_TTL = 600                      # ชีตลีดหลายหมื่นแถว — อ่านใหม่ทุก 10 นาที (อ่านครั้งแรก ~8 วิ)
RETURN_WORDS = ("คืนเคส",)


def _cell(r, i):
    return (r[i] if i < len(r) else "") or ""


def _date(s):
    try:
        from dashboard.services.fetch_dashboard import parse_date
        d = parse_date(s)
        return d.date() if hasattr(d, "date") else d
    except Exception:
        return None


def _names() -> dict:
    """เลขลีด → ชื่อลูกค้า (ชีตลีดไม่มีช่องชื่อ) — จากงานจ่ายเบอร์ · แชท · ลีดภายนอก · ใบจ่ายลีดในกลุ่ม"""
    from .models import ChatLead, CustomerNeed, ExtLead, LeadTask
    out = {}
    for code, name in CustomerNeed.objects.exclude(lead_code="").exclude(customer_name="") \
            .values_list("lead_code", "customer_name")[:60000]:
        out.setdefault(code.upper(), name)
    for M, f in ((ExtLead, "customer_name"), (ExtLead, "account"), (ChatLead, "customer_name"),
                 (ChatLead, "account"), (LeadTask, "customer")):
        for code, name in M.objects.exclude(code="").exclude(**{f: ""}).values_list("code", f)[:60000]:
            out[code.upper()] = out.get(code.upper()) or name
    return out


def rows(force: bool = False) -> list:
    """ชีตลีดทุกแท็บ → แถวที่หน้าเว็บใช้ (จำ 10 นาทีต่อ process) · ใหม่สุดก่อน"""
    if not force and _ROWS["val"] is not None and time.time() - _ROWS["at"] < ROWS_TTL:
        return _ROWS["val"]
    from dashboard.services.constants import normalize_seller
    from dashboard.services.google_sheets import LEADS_COL as L
    from dashboard.services.google_sheets import fetch_leads_by_month_tabs
    from . import phonebook
    raw = fetch_leads_by_month_tabs() or []
    names = _names()
    out, by_phone = [], {}
    for r in raw:
        code = _cell(r, L.lead_code).strip().upper()
        phone = (phonebook.phones_in(_cell(r, L.phone)) or [""])[0]
        d = _date(_cell(r, L.received_date))
        z = _cell(r, L.customer_status).strip()
        ad = _cell(r, L.admin_status).strip()
        row = {"date": d.isoformat() if d else "", "code": code, "phone": phone,
               "seller": normalize_seller(_cell(r, L.sales_rep)) or _cell(r, L.sales_rep).strip(),
               "channel": _cell(r, L.channel).strip(), "type": _cell(r, L.type).strip(),
               "car": (_cell(r, L.car_formula) or _cell(r, L.car_inquiry)).strip()[:80],
               "carAsk": _cell(r, L.car_inquiry).strip()[:120], "z": z, "admin": ad,
               "sales": _cell(r, L.sales_status).strip()[:120], "note": _cell(r, L.fill_sheet_note).strip()[:300],
               "updates": _cell(r, L.update_count).strip(), "name": names.get(code, "")}
        row["returned"] = any(w in (z + " " + ad) for w in RETURN_WORDS)
        out.append(row)
        if phone:
            by_phone.setdefault(phone, set()).add(code or "?")
    for row in out:
        row["dup"] = max(0, len(by_phone.get(row["phone"], ())) - 1) if row["phone"] else 0
    out.sort(key=lambda x: (x["date"], x["code"]), reverse=True)
    _ROWS.update(at=time.time(), val=out)
    return out


def _forwarded(codes) -> set:
    """เลขที่ส่งต่อไม้ 2 ไปแล้ว (มีเลข R…/n ของเลขนั้นในระบบ)"""
    from .models import ChatLead, ExtLead, LeadTask
    done = set()
    for M in (LeadTask, ChatLead, ExtLead):
        for c in M.objects.filter(code__contains="/").values_list("code", flat=True)[:5000]:
            base = re.sub(r"/\d+$", "", c.upper())
            done.add(base[1:] if base.startswith("R") else base)
    return {c for c in codes if c in done}


def search(q: str = "", mode: str = "all", status: str = "", seller: str = "", limit: int = 100) -> dict:
    """ค้นฐานข้อมูล Lead — เบอร์ (เต็มหรือ 4 ตัวท้าย) · ชื่อ · ID LINE/รุ่นรถ · เลขลีด"""
    all_rows = rows()
    q = (q or "").strip().lower()
    digits = re.sub(r"\D", "", q)
    res = all_rows
    if mode == "returned":
        res = [r for r in res if r["returned"]]
        fw = _forwarded({r["code"] for r in res})
        res = [dict(r, forwarded=r["code"] in fw) for r in res if r["code"] not in fw]
    if seller:
        res = [r for r in res if r["seller"] == seller]
    if status:
        res = [r for r in res if status in (r["z"] or "")]
    if q:
        def hit(r):
            if digits and len(digits) >= 4 and (digits in r["phone"] or digits in re.sub(r"\D", "", r["code"])):
                return True
            hay = " ".join((r["code"], r["name"], r["car"], r["carAsk"], r["channel"], r["seller"], r["note"])).lower()
            return q in hay
        res = [r for r in res if hit(r)]
    stats = {"rows": len(all_rows), "phones": len({r["phone"] for r in all_rows if r["phone"]}),
             "returned": sum(1 for r in all_rows if r["returned"])}
    return {"rows": res[:limit], "total": len(res), "stats": stats,
            "sellers": sorted({r["seller"] for r in all_rows if r["seller"]})[:60]}


def detail(code: str) -> dict:
    """ลีด 1 เลข: แถวในชีต + เลขอื่นของเบอร์เดียวกัน + งานจ่ายเบอร์ + รายงานผล"""
    from .models import LeadReport, LeadTask
    from . import leadflow, phonebook
    code = (code or "").strip().upper()
    row = next((r for r in rows() if r["code"] == code), None)
    if not row:
        return {"error": "ไม่พบเลข %s ในชีตลีด" % code}
    # เลขอื่นของเบอร์เดียวกัน: แถวในชีตลีด (ทั้งปี) + สมุดเบอร์ (ใบในห้อง/ปุ่มจ่ายเบอร์ที่ยังไม่ลงชีต)
    others, seen = [], {code}
    if row["phone"]:
        for r in rows():
            if r["phone"] == row["phone"] and r["code"] not in seen:
                seen.add(r["code"])
                others.append({"code": r["code"], "seller": r["seller"], "date": r["date"], "channel": r["channel"],
                               "car": r["car"], "source": "sheet"})
        for x in phonebook.lookup(row["phone"], exclude_code=code):
            if (x.get("code") or "").upper() not in seen:
                seen.add((x.get("code") or "").upper())
                others.append(x)
    tasks = []
    base = re.sub(r"/\d+$", "", code)
    core = base[1:] if base.startswith("R") else base
    for t in LeadTask.objects.filter(Q(code__iexact=code) | Q(code__istartswith="R" + core)).order_by("-id")[:10]:
        tasks.append(dict(leadflow.task_state(t), code=t.code, seller=t.seller_name, by=t.by,
                          postedAt=leadflow._iso(t.posted_at), reports=t.reports, lastReport=t.last_report,
                          history=[h.get("seller") for h in (t.history or [])]))
    reps = [{"at": leadflow._iso(r.sent_at), "seller": r.seller_name, "text": r.text[:300], "state": r.state}
            for r in LeadReport.objects.filter(code__iexact=code).order_by("-sent_at")[:20]]
    done = leadflow.forwarded_as(code)
    return {"row": row, "others": others[:20], "tasks": tasks, "reports": reps,
            "fwd": "" if done else leadflow.fwd_code(code), "fwdDone": done}


# ─────────────────────────────────────────────────────────────
#  ไปป์ไลน์
# ─────────────────────────────────────────────────────────────
PIPE_COLS = ["จอง", "รอเซ็นต์", "รอผล", "รอปล่อย", "ปล่อย"]
STUCK = {"จอง": 3, "รอเซ็นต์": 3, "รอผล": 5, "รอปล่อย": 3}


def _days_since(s, today):
    d = _date(s)
    return (today - d).days if d else None


def pipeline(limit: int = 60) -> dict:
    """เคสจองเดือนนี้ (ที่ยังเดินอยู่) + ปล่อยเดือนนี้ — จากชีตยอดขาย · ค้างนานเกินกำหนด = ติดป้าย"""
    from dashboard.services.fetch_dashboard import fetch_dashboard_data, parse_month_day
    data = fetch_dashboard_data() or {}
    today = timezone.localdate()
    cols = {c: [] for c in PIPE_COLS}
    for b in data.get("bookingCases") or []:
        st = (b.get("status") or "").strip()
        if st not in cols:
            continue
        if st == "ปล่อย":
            md = parse_month_day(b.get("releaseDate") or "")
            if not md or md[0] != today.month:
                continue
            ref, days = b.get("releaseDate"), None
        else:
            ref = {"จอง": b.get("date"), "รอเซ็นต์": b.get("date"),
                   "รอผล": b.get("signDate") or b.get("date"),
                   "รอปล่อย": b.get("resultDate") or b.get("signDate") or b.get("date")}[st]
            days = _days_since(ref, today)
            if days is not None and (days > 120 or days < 0):
                continue                                    # วันที่ปีผิด/เคสเก่ามาก — ไม่ใช่งานที่กำลังเดิน
        cols[st].append({"customer": b.get("customer") or "-", "car": b.get("car") or "", "seller": b.get("seller") or "",
                         "price": b.get("price") or 0, "code": b.get("leadCode") or "", "date": b.get("date") or "",
                         "days": days, "stuck": bool(days is not None and st in STUCK and days > STUCK[st])})
    out = []
    for c in PIPE_COLS:
        items = sorted(cols[c], key=lambda x: (-(x["days"] or 0) if c != "ปล่อย" else 0))
        out.append({"status": c, "count": len(items), "value": sum(x["price"] for x in items),
                    "stuck": sum(1 for x in items if x["stuck"]), "items": items[:limit]})
    return {"cols": out, "stuckRule": STUCK, "at": data.get("generatedAt") or ""}


# ─────────────────────────────────────────────────────────────
#  แดชบอร์ดทีม
# ─────────────────────────────────────────────────────────────
def _month_summary(data, m):
    ms = data.get("monthlySummary") or {}
    return ms.get(m) or ms.get(str(m)) or {}


def team(now=None) -> dict:
    from dashboard.services.fetch_dashboard import fetch_dashboard_data
    from . import connect as C
    from .checkin_report import THAI_DAYS
    from .models import ChatLead, ChatOwner, ChatOwnerLog, LeadTask
    now = now or timezone.now()
    today = timezone.localdate()
    t0 = timezone.make_aware(datetime.combine(today, datetime.min.time()))
    m0 = timezone.make_aware(datetime.combine(today.replace(day=1), datetime.min.time()))
    data = fetch_dashboard_data() or {}
    ms = _month_summary(data, today.month)
    msel = ms.get("sellers") or {}

    # ใบทดลอง (บัญชีทดสอบ/ลูกค้าจำลอง) ไม่นับ — กรองใน Python (exclude บนคีย์ JSON ตัดแถวทิ้งหมดบน SQLite)
    tasks_today = [t for t in LeadTask.objects.filter(created_at__gte=t0)
                   .values("seller_id", "posted_at", "due_at", "first_report_at", "passed_at", "card")
                   if not (t["card"] or {}).get("demo")]
    reps = ChatOwnerLog.objects.filter(action=ChatOwnerLog.REPLY, at__gte=t0)
    rep_all = reps.count()
    rep_ok = reps.filter(on_time=True).count()

    def overdue(t):
        return bool(t["posted_at"] and t["due_at"] and not t["passed_at"]
                    and ((t["first_report_at"] and t["first_report_at"] > t["due_at"])
                         or (not t["first_report_at"] and now > t["due_at"])))

    chats_m = ChatOwner.objects.filter(created_at__gte=m0).count()
    contact_m = (ChatLead.objects.filter(chat__created_at__gte=m0)
                 .filter(~Q(phone="") | ~Q(line_id="")).count())
    funnel = [{"k": "แชทใหม่เข้า Connect", "v": chats_m, "src": "Connect"},
              {"k": "ได้เบอร์/ID LINE", "v": contact_m, "src": "Connect"},
              {"k": "ลีดในชีตเดือนนี้", "v": int(ms.get("lead") or 0), "src": "ชีตลีด"},
              {"k": "จองเดือนนี้", "v": int(ms.get("booking") or 0), "src": "ชีตลีด"},
              {"k": "ปล่อยเดือนนี้", "v": int(ms.get("done") or 0), "src": "ชีตยอดขาย"}]

    c = C.cfg()
    duty = C.duty_team(today, c)
    dname = THAI_DAYS[today.weekday()]
    by_emp = {}
    for t in tasks_today:
        by_emp.setdefault(t["seller_id"], []).append(t)
    six = [today - timedelta(days=i) for i in range(5, -1, -1)]
    s0 = timezone.make_aware(datetime.combine(six[0], datetime.min.time()))
    spark = {}
    for sid, d in (LeadTask.objects.filter(created_at__gte=s0, seller__isnull=False)
                   .values_list("seller_id", "created_at")):
        spark.setdefault(sid, {}).setdefault(timezone.localtime(d).date(), 0)
        spark[sid][timezone.localtime(d).date()] += 1
    rep_by = {r["employee_id"]: r for r in reps.values("employee_id")
              .annotate(n=Count("id"), ok=Count("id", filter=Q(on_time=True)))}
    sellers = []
    from .models import Employee
    emps = {e.id: e for e in Employee.objects.filter(active=True)}
    for s in C.seller_list():
        if s.get("test"):
            continue
        e = emps.get(s["id"])
        mine = by_emp.get(s["id"], [])
        rp = rep_by.get(s["id"]) or {}
        stat = "หยุดวันนี้" if (e and e.day_off and dname in e.day_off) else \
               ("เวรรับแชทวันนี้" if s["team"] == duty else "รับลีดอยู่")
        mm = msel.get(s["name"]) or {}
        sellers.append({"id": s["id"], "name": s["name"], "team": s["team"], "leadsToday": len(mine),
                        "reported": sum(1 for t in mine if t["first_report_at"]),
                        "late": sum(1 for t in mine if overdue(t)),
                        "replies": rp.get("n", 0), "repliesOk": rp.get("ok", 0),
                        "booking": int(mm.get("booking") or 0), "done": int(mm.get("done") or 0),
                        "spark": [spark.get(s["id"], {}).get(d, 0) for d in six], "status": stat})
    sellers.sort(key=lambda x: (x["team"], x["name"]))
    return {"date": today.isoformat(), "dayName": dname, "duty": duty,
            "tiles": {"tasksToday": len(tasks_today),
                      "lateToday": sum(1 for t in tasks_today if overdue(t)),
                      "reportedToday": sum(1 for t in tasks_today if t["first_report_at"]),
                      "repAll": rep_all, "repOk": rep_ok,
                      "doneMonth": int(ms.get("done") or 0), "bookingMonth": int(ms.get("booking") or 0)},
            "funnel": funnel, "sellers": sellers, "sixDays": [d.isoformat() for d in six]}
