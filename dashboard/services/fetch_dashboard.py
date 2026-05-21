"""
Main dashboard data fetching & transformation — ported from lib/fetch-dashboard.ts
"""
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, date
from zoneinfo import ZoneInfo

from .google_sheets import (
    fetch_all_sheets, cell, cell_num,
    LEADS_COL as L, SALES_COL as S, BOOKINGS_COL as B,
    LIVE_COL as LV, FOLLOWUP_COL as FU, EMPLOYEE_COL as EM,
)
from .constants import (
    normalize_seller, TEAMS, TARGETS, ALL_SELLERS, TEAM_ID, RJ_TYPES,
    STATUS_ORDER,
)

BKK = ZoneInfo("Asia/Bangkok")

# ── Follow status keywords ──
FOLLOW_KEYWORDS = ["ติดตาม", "รอตอบ", "รอลูกค้า", "โทรไม่รับ", "ผิดนัด"]


def is_follow(status: str) -> bool:
    if not status:
        return False
    lower = status.lower()
    return any(kw in lower for kw in FOLLOW_KEYWORDS)


def is_vacant(status: str) -> bool:
    return not status or status in ("-", "")


# ── Date helpers ──
def bangkok_now() -> datetime:
    return datetime.now(BKK)


def parse_date(date_str: str) -> date | None:
    if not date_str or date_str == "-":
        return None
    # Excel serial date
    if re.match(r"^\d{4,5}$", date_str.strip()):
        serial = int(date_str.strip())
        if 1000 < serial < 100000:
            from datetime import timedelta
            excel_epoch = date(1899, 12, 30)
            d = excel_epoch + timedelta(days=serial)
            return d
    # d/m/yy format
    parts = date_str.split("/")
    if len(parts) == 3:
        try:
            day = int(parts[0])
            month = int(parts[1]) - 1  # 0-based for compatibility
            year = int(parts[2])
            if year < 100:
                year += 2000
            if year > 2500:
                year -= 543
            return date(year, month + 1, day)
        except (ValueError, TypeError):
            pass
    # Fallback
    try:
        from dateutil.parser import parse as dateutil_parse
        return dateutil_parse(date_str).date()
    except Exception:
        pass
    return None


def is_this_year(date_str: str) -> bool:
    d = parse_date(date_str)
    if not d:
        return False
    return d.year == bangkok_now().year


def is_today(date_str: str) -> bool:
    d = parse_date(date_str)
    if not d:
        return False
    now = bangkok_now()
    return d.year == now.year and d.month == now.month and d.day == now.day


def get_month(date_str: str) -> int:
    if not date_str or date_str == "-":
        return 0
    if re.match(r"^\d{4,5}$", date_str.strip()):
        d = parse_date(date_str)
        return d.month if d else 0
    parts = date_str.split("/")
    if len(parts) >= 2:
        try:
            return int(parts[1])
        except ValueError:
            return 0
    return 0


# ── Main fetch function ──
def fetch_dashboard_data() -> dict:
    # โหลด config เซลล์ล่าสุดจาก sheet (mutate TEAMS/TARGETS in-place)
    # ถ้า sheet หายหรือ error → ใช้ default hardcode
    from .constants import refresh_from_sheet
    refresh_from_sheet()

    raw = fetch_all_sheets()
    raw_leads = raw["leads"]
    sales_reports = raw["sales_reports"]
    raw_bookings = raw["bookings"]
    live_sessions = raw["live_sessions"]
    live_followups = raw["live_followups"]
    employees = raw["employees"]

    now = bangkok_now()
    month = now.month
    year_full = now.year
    weeks_elapsed = math.ceil(now.day / 7)
    clip_month_target = weeks_elapsed * 2

    # userIdMap + employee list (สำหรับ admin panel)
    user_id_map = {}
    employee_list = []
    for row in employees:
        uid = cell(row, EM.user_id)
        nickname = cell(row, EM.nickname)
        if uid and nickname:
            user_id_map[uid] = nickname
        if not uid:
            continue
        # ไม่ส่ง reply_token ออกไปเพราะเป็น sensitive (ใช้ตอบ LINE webhook)
        employee_list.append({
            "user_id": uid,
            "display_name": cell(row, EM.display_name),
            "picture_url": cell(row, EM.picture_url),
            "group_id": cell(row, EM.group_id),
            "nickname": nickname,
            "position": cell(row, EM.position),
        })

    # Filter leads
    year_leads = [r for r in raw_leads if is_this_year(cell(r, L.received_date))]
    today_leads = [r for r in raw_leads if is_today(cell(r, L.received_date))]

    # Jongs from bookings sheet
    jongs = []
    for r in raw_bookings:
        date_str = cell(r, B.date)
        if not re.match(r"^\d+/\d+/\d{2,4}$", date_str):
            continue
        seller = normalize_seller(cell(r, B.sales_rep))
        if not seller or seller in ("เซลล์", "DATE"):
            continue
        if seller.startswith("รวม") or seller.startswith("**"):
            continue
        jongs.append({"seller": seller, "date": date_str, "code": cell(r, B.code)})
    year_jongs = [j for j in jongs if is_this_year(j["date"])]

    # BookingCases from sales_reports
    booking_cases = []
    for r in sales_reports:
        seller_cell = cell(r, S.sales_rep)
        seller = normalize_seller(
            seller_cell.replace("ชื่อเซลล์ ", "").replace("ชื่อเซลล์", "").strip()
        )
        seq = cell(r, S.order_num)
        if not seq or seq == "ลำดับ":
            continue
        try:
            int(seq)
        except ValueError:
            continue
        status = cell(r, S.status)
        if not status:
            continue
        is_cash = "(ซื้อสด)" in status
        booking_cases.append({
            "seller": seller,
            "status": status.replace(" (ซื้อสด)", "").strip(),
            "isCash": is_cash,
            "customer": cell(r, S.customer_name),
            "phone": cell(r, S.phone),
            "car": cell(r, S.car_detail),
            "year": cell(r, S.car_year),
            "plate": cell(r, S.license_plate),
            "price": cell_num(r, S.sale_price),
            "deposit": cell_num(r, S.deposit_amount),
            "leadCode": cell(r, S.lead_code),
            "date": cell(r, S.date),
            "signDate": cell(r, S.sign_date),
            "resultDate": cell(r, S.result_date),
            "docsDate": cell(r, S.doc_complete_date),
            "releaseDate": cell(r, S.car_release_date),
            "finance": cell(r, S.finance_main),
            "grade": cell(r, S.grade),
            "note": cell(r, S.note),
        })

    # Live sessions from this year
    year_live = [r for r in live_sessions if is_this_year(cell(r, LV.date))]

    # Clips from this year
    year_clips = []
    for row in live_followups:
        name = normalize_seller(cell(row, FU.name))
        clip_date = cell(row, FU.clip_date)
        if not name or not clip_date or name not in ALL_SELLERS:
            continue
        if is_this_year(clip_date):
            year_clips.append({"name": name, "date": clip_date})

    # Aggregate live/clip counts
    live_count_map = {}
    live_inbox_map = {}
    live_lead_map = {}
    clip_count_map = {}

    for r in year_live:
        for i in range(5):
            h = normalize_seller(cell(r, LV.host_1 + i))
            if h and h not in ("-", "nan"):
                live_count_map[h] = live_count_map.get(h, 0) + 1
                live_inbox_map[h] = live_inbox_map.get(h, 0) + cell_num(r, LV.inbox)
                live_lead_map[h] = live_lead_map.get(h, 0) + cell_num(r, LV.lead_count)

    for c in year_clips:
        clip_count_map[c["name"]] = clip_count_map.get(c["name"], 0) + 1

    # Jong per seller
    jong_by_seller = {}
    for j in year_jongs:
        jong_by_seller[j["seller"]] = jong_by_seller.get(j["seller"], 0) + 1

    # Summary
    lead_normal = len([r for r in year_leads if cell(r, L.type) not in RJ_TYPES])
    lead_rj = len([r for r in year_leads if cell(r, L.type) in RJ_TYPES])
    total_done = len([b for b in booking_cases if b["status"] == "ปล่อย"])
    total_target = sum(TARGETS.values())
    total_follow = len([r for r in year_leads if is_follow(cell(r, L.admin_status))])
    total_vacant = len([r for r in year_leads if is_vacant(cell(r, L.admin_status))])

    summary = {
        "totalLeads": len(year_leads),
        "leadNormal": lead_normal,
        "leadRJ": lead_rj,
        "totalFollow": total_follow,
        "totalVacant": total_vacant,
        "totalDone": total_done,
        "totalTarget": total_target,
        "totalBookings": len(year_jongs),
    }

    # Pipeline
    pipeline = {
        "จอง": len(year_jongs),
        "รอเซ็นต์": len([b for b in booking_cases if b["status"] == "รอเซ็นต์"]),
        "รอผล": len([b for b in booking_cases if b["status"] == "รอผล"]),
        "รอปล่อย": len([b for b in booking_cases if b["status"] == "รอปล่อย"]),
        "ปล่อย": len([b for b in booking_cases if b["status"] == "ปล่อย"]),
        "รีเจ็ก": len([b for b in booking_cases if b["status"] == "รีเจ็ก"]),
    }

    # Sellers
    sellers = []
    for name in ALL_SELLERS:
        sl = [r for r in year_leads if normalize_seller(cell(r, L.sales_rep)) == name]
        sb = [b for b in booking_cases if b["seller"] == name]
        follow = len([r for r in sl if is_follow(cell(r, L.admin_status))])
        vacant = len([r for r in sl if is_vacant(cell(r, L.admin_status))])
        done = len([b for b in sb if b["status"] == "ปล่อย"])
        lead_types = {}
        for r in sl:
            t = cell(r, L.type) or "ไม่ระบุ"
            lead_types[t] = lead_types.get(t, 0) + 1
        s_data = {
            "name": name,
            "team": TEAM_ID.get(name, "?"),
            "lead": len(sl),
            "follow": follow,
            "vacant": vacant,
            "done": done,
            "target": TARGETS.get(name, 0),
            "booking": jong_by_seller.get(name, 0),
            "live": live_count_map.get(name, 0),
            "clip": clip_count_map.get(name, 0),
            "clipTarget": clip_month_target,
            "liveInbox": live_inbox_map.get(name, 0),
            "liveLead": live_lead_map.get(name, 0),
            "leadTypes": lead_types,
        }
        if s_data["lead"] > 0 or s_data["done"] > 0 or s_data["booking"] > 0:
            sellers.append(s_data)

    # ADMIN seller
    admin_leads = [r for r in year_leads if normalize_seller(cell(r, L.sales_rep)) == "ADMIN"]
    if admin_leads:
        admin_follow = len([r for r in admin_leads if is_follow(cell(r, L.admin_status))])
        admin_vacant = len([r for r in admin_leads if is_vacant(cell(r, L.admin_status))])
        admin_done = len([b for b in booking_cases if b["seller"] == "ADMIN" and b["status"] == "ปล่อย"])
        admin_booking = len([j for j in year_jongs if j["seller"] == "ADMIN"])
        admin_types = {}
        for r in admin_leads:
            t = cell(r, L.type) or "ไม่ระบุ"
            admin_types[t] = admin_types.get(t, 0) + 1
        sellers.append({
            "name": "ADMIN", "team": "ADMIN",
            "lead": len(admin_leads), "follow": admin_follow,
            "vacant": admin_vacant, "done": admin_done,
            "target": 0, "booking": admin_booking,
            "live": 0, "clip": 0, "clipTarget": 0,
            "liveInbox": 0, "liveLead": 0,
            "leadTypes": admin_types,
        })

    # Teams
    teams = {}
    for tid, members in TEAMS.items():
        ms = [s for s in sellers if s["name"] in members]
        teams[tid] = {
            "members": members,
            "lead": sum(s["lead"] for s in ms),
            "follow": sum(s["follow"] for s in ms),
            "vacant": sum(s["vacant"] for s in ms),
            "done": sum(s["done"] for s in ms),
            "target": sum(s["target"] for s in ms),
            "booking": sum(s["booking"] for s in ms),
            "live": sum(s["live"] for s in ms),
            "clip": sum(s["clip"] for s in ms),
            "clipTarget": len(members) * clip_month_target,
        }

    # Follow Cases
    follow_cases = []
    for r in year_leads:
        if not is_follow(cell(r, L.admin_status)):
            continue
        seller = normalize_seller(cell(r, L.sales_rep)) or "-"
        if seller == "-":
            continue
        note_raw = cell(r, L.fill_sheet_note) or "-"
        note = re.sub(r"^\d{4,5}\s*", "", note_raw) or "-"
        follow_cases.append({
            "code": cell(r, L.lead_code) or "-",
            "seller": seller,
            "phone": cell(r, L.phone) or "-",
            "channel": cell(r, L.channel) or "-",
            "leadType": cell(r, L.type),
            "car": cell(r, L.car_inquiry) or cell(r, L.car_formula) or "-",
            "adminStatus": cell(r, L.admin_status) or "ติดตาม",
            "callProof": cell(r, L.call_proof) or "-",
            "profile": cell(r, L.customer_profile) or "",
            "dateIn": cell(r, L.received_date) or "-",
            "timeIn": cell(r, L.time),
            "note": note,
            "lastUpdate": cell(r, L.last_updated_at) or "-",
            "updateCount": int(cell_num(r, L.update_count)),
        })

    # Today summary
    today_by_seller = {}
    for r in today_leads:
        s = normalize_seller(cell(r, L.sales_rep))
        if not s:
            continue
        if s not in today_by_seller:
            today_by_seller[s] = {"lead": 0, "follow": 0, "vacant": 0}
        today_by_seller[s]["lead"] += 1
        st = cell(r, L.admin_status)
        if is_follow(st):
            today_by_seller[s]["follow"] += 1
        if is_vacant(st):
            today_by_seller[s]["vacant"] += 1

    today_summary = {
        "totalLeads": len(today_leads),
        "totalFollow": len([r for r in today_leads if is_follow(cell(r, L.admin_status))]),
        "totalVacant": len([r for r in today_leads if is_vacant(cell(r, L.admin_status))]),
        "bySeller": today_by_seller,
    }

    # Live Activity
    live_sessions_list = []
    for r in year_live:
        hosts = []
        for i in range(5):
            h = normalize_seller(cell(r, LV.host_1 + i))
            if h and h not in ("-", "nan"):
                hosts.append(h)
        live_sessions_list.append({
            "date": cell(r, LV.date),
            "time": cell(r, LV.time),
            "team": cell(r, LV.team),
            "hosts": hosts,
            "topic": cell(r, LV.topic),
            "inbox": int(cell_num(r, LV.inbox)),
            "lead": int(cell_num(r, LV.lead_count)),
        })

    by_host = {}
    for n in ALL_SELLERS:
        by_host[n] = {
            "sessions": live_count_map.get(n, 0),
            "inbox": int(live_inbox_map.get(n, 0)),
            "lead": int(live_lead_map.get(n, 0)),
            "clip": clip_count_map.get(n, 0),
        }

    live_activity = {
        "totalSessions": len(year_live),
        "totalInbox": int(sum(cell_num(r, LV.inbox) for r in year_live)),
        "totalLead": int(sum(cell_num(r, LV.lead_count) for r in year_live)),
        "byHost": by_host,
        "sessions": live_sessions_list,
    }

    # Monthly Summary
    def get_done_month(b):
        rd = b.get("releaseDate", "")
        if rd and rd != "-" and rd != "":
            m = get_month(rd)
            if m > 0:
                return m
        return get_month(b["date"])

    monthly_summary = {}
    for m in range(1, 13):
        m_leads = [r for r in year_leads if get_month(cell(r, L.received_date)) == m]
        m_jongs = [j for j in year_jongs if get_month(j["date"]) == m]
        m_ln = len([r for r in m_leads if cell(r, L.type) not in RJ_TYPES])
        m_lr = len([r for r in m_leads if cell(r, L.type) in RJ_TYPES])
        m_follow = len([r for r in m_leads if is_follow(cell(r, L.admin_status))])
        m_vacant = len([r for r in m_leads if is_vacant(cell(r, L.admin_status))])

        m_bookings = [b for b in booking_cases if get_month(b["date"]) == m]
        m_done = [b for b in booking_cases if b["status"] == "ปล่อย" and get_done_month(b) == m]

        m_pipeline = {
            "จอง": len(m_jongs),
            "รอเซ็นต์": len([b for b in m_bookings if b["status"] == "รอเซ็นต์"]),
            "รอผล": len([b for b in m_bookings if b["status"] == "รอผล"]),
            "รอปล่อย": len([b for b in m_bookings if b["status"] == "รอปล่อย"]),
            "ปล่อย": len(m_done),
            "รีเจ็ก": len([b for b in m_bookings if b["status"] == "รีเจ็ก"]),
        }

        m_jong_by_seller = {}
        for j in m_jongs:
            m_jong_by_seller[j["seller"]] = m_jong_by_seller.get(j["seller"], 0) + 1

        m_sellers = {}
        for name in ALL_SELLERS:
            sl2 = [r for r in m_leads if normalize_seller(cell(r, L.sales_rep)) == name]
            sb_done = [b for b in m_done if b["seller"] == name]
            m_sellers[name] = {
                "lead": len(sl2),
                "leadNormal": len([r for r in sl2 if cell(r, L.type) not in RJ_TYPES]),
                "leadRJ": len([r for r in sl2 if cell(r, L.type) in RJ_TYPES]),
                "follow": len([r for r in sl2 if is_follow(cell(r, L.admin_status))]),
                "vacant": len([r for r in sl2 if is_vacant(cell(r, L.admin_status))]),
                "done": len(sb_done),
                "booking": m_jong_by_seller.get(name, 0),
            }

        m_teams = {}
        for tid, members in TEAMS.items():
            ts = {"lead": 0, "follow": 0, "vacant": 0, "done": 0, "booking": 0}
            for n in members:
                s2 = m_sellers.get(n, {"lead": 0, "follow": 0, "vacant": 0, "done": 0, "booking": 0})
                for k in ts:
                    ts[k] += s2[k]
            m_teams[tid] = ts

        monthly_summary[m] = {
            "totalLeads": len(m_leads),
            "leadNormal": m_ln,
            "leadRJ": m_lr,
            "totalFollow": m_follow,
            "totalVacant": m_vacant,
            "totalDone": len(m_done),
            "totalBookings": len(m_jongs),
            "pipeline": m_pipeline,
            "sellers": m_sellers,
            "teams": m_teams,
        }

    # Daily breakdown ภายในแต่ละเดือน — ใช้ตอน user เลือกเดือนเฉพาะแล้วกราฟต้องสลับเป็นรายวัน
    def _parse_day(date_str):
        d = parse_date(date_str)
        if not d or not (1 <= d.day <= 31):
            return None
        return (d.month, d.day)

    def _parse_done_day(b):
        rd = b.get("releaseDate", "")
        if rd and rd != "-" and rd != "":
            md = _parse_day(rd)
            if md:
                return md
        return _parse_day(b["date"])

    daily_by_month = {
        m: {
            "leads": [0] * 32,
            "leadRJ": [0] * 32,
            "bookings": [0] * 32,
            "dones": [0] * 32,
        }
        for m in range(1, 13)
    }

    for r in year_leads:
        md = _parse_day(cell(r, L.received_date))
        if not md:
            continue
        mm, dd = md
        bucket = "leadRJ" if cell(r, L.type) in RJ_TYPES else "leads"
        daily_by_month[mm][bucket][dd] += 1

    for j in year_jongs:
        md = _parse_day(j["date"])
        if not md:
            continue
        mm, dd = md
        daily_by_month[mm]["bookings"][dd] += 1

    for b in booking_cases:
        if b["status"] != "ปล่อย":
            continue
        md = _parse_done_day(b)
        if not md:
            continue
        mm, dd = md
        daily_by_month[mm]["dones"][dd] += 1

    # Daily-by-month แยกตามเซลล์ — ใช้ตอน admin impersonate เซลล์คนใดคนหนึ่ง
    daily_by_seller = {
        name: {
            m: {
                "leads": [0] * 32,
                "leadRJ": [0] * 32,
                "bookings": [0] * 32,
                "dones": [0] * 32,
            }
            for m in range(1, 13)
        }
        for name in ALL_SELLERS
    }

    for r in year_leads:
        md = _parse_day(cell(r, L.received_date))
        if not md:
            continue
        mm, dd = md
        name = normalize_seller(cell(r, L.sales_rep))
        if name not in daily_by_seller:
            continue
        bucket = "leadRJ" if cell(r, L.type) in RJ_TYPES else "leads"
        daily_by_seller[name][mm][bucket][dd] += 1

    for j in year_jongs:
        md = _parse_day(j["date"])
        if not md:
            continue
        mm, dd = md
        if j["seller"] not in daily_by_seller:
            continue
        daily_by_seller[j["seller"]][mm]["bookings"][dd] += 1

    for b in booking_cases:
        if b["status"] != "ปล่อย":
            continue
        md = _parse_done_day(b)
        if not md:
            continue
        mm, dd = md
        if b["seller"] not in daily_by_seller:
            continue
        daily_by_seller[b["seller"]][mm]["dones"][dd] += 1

    return {
        "meta": {
            "generatedAt": now.isoformat(),
            "month": month,
            "year": year_full,
            "weeksElapsed": weeks_elapsed,
            "clipMonthTarget": clip_month_target,
        },
        "summary": summary,
        "today": today_summary,
        "pipeline": pipeline,
        "teams": teams,
        "sellers": sellers,
        "followCases": follow_cases,
        "bookingCases": booking_cases,
        "liveActivity": live_activity,
        "userIdMap": user_id_map,
        "employees": employee_list,
        "monthlySummary": monthly_summary,
        "dailyByMonth": daily_by_month,
        "dailyBySeller": daily_by_seller,
    }
