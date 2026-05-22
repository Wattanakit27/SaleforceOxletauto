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
    LEADS_COL as L, SALES_COL as S,
    LIVE_COL as LV, FOLLOWUP_COL as FU, EMPLOYEE_COL as EM,
)
from .constants import (
    normalize_seller, TEAMS, TARGETS, ALL_SELLERS, TEAM_ID, RJ_TYPES,
    STATUS_ORDER,
)

BKK = ZoneInfo("Asia/Bangkok")

# ── Follow status keywords ──
FOLLOW_KEYWORDS = ["ติดตาม", "รอตอบ", "รอลูกค้า", "โทรไม่รับ", "ผิดนัด"]
# คำที่ทำให้เคส "จบแล้ว" — ใช้กรองเฉพาะ "ต้องโทร/ติดตามต่อ" (เคสยังอยู่ใน list ปกติ + นับ stat ปกติ)
# sync กับ line_notify.SKIP_STATUS — admin ใส่คำเหล่านี้เพื่อบอกว่าไม่ต้องตามต่อ
SKIP_STATUS = ["จบ", "ส่งมอบ", "คืนเคส", "คืน", "ยกเลิก", "ไม่สนใจ", "dead", "จ่ายใหม่"]


def is_skipped(status: str) -> bool:
    """เคสที่ถือว่า 'จบแล้ว' — ใช้สำหรับ exclude จากการแจ้งเตือนติดตาม
    (เคสยังนับใน stat รวม + แสดงใน list ปกติ — แค่ไม่ remind)"""
    if not status:
        return False
    low = status.lower()
    return any(s.lower() in low for s in SKIP_STATUS)


def is_follow(status: str) -> bool:
    """ตรวจว่า status เข้าข่าย 'ต้องตามต่อ' — ใช้สำหรับสร้าง follow_cases / KPI 'ต้องโทรต่อ'
    เคส skipped (จบ/คืน/ยกเลิก/จ่ายใหม่) → ไม่นับเป็น follow แม้มีคำว่า 'ติดตาม'"""
    if not status:
        return False
    if is_skipped(status):
        return False
    lower = status.lower()
    return any(kw in lower for kw in FOLLOW_KEYWORDS)


def is_vacant(status: str) -> bool:
    """ตรวจว่า admin_status ยังว่าง — ใช้สำหรับ KPI 'ว่าง' (เคสที่ admin ยังไม่ assign สถานะ)"""
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
    # bookings sheet ไม่ใช้แล้ว — เปลี่ยนมานับ "จอง" จาก leads sheet (admin/sales_status มี "จอง")
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

    # Jongs — นับจาก leads sheet (admin_status / sales_status มีคำว่า "จอง")
    # status อื่นๆ (รอเซ็นต์/รอผล/รอปล่อย/ปล่อย/รีเจ็ก) จะนับจาก sales_reports (booking_cases ด้านล่าง)
    # exclude เคส skipped (จบ/คืน/ยกเลิก/จ่ายใหม่)
    def has_booking_status(row) -> bool:
        admin_st = cell(row, L.admin_status)
        sales_st = cell(row, L.sales_status)
        if is_skipped(admin_st) or is_skipped(sales_st):
            return False
        return "จอง" in (admin_st or "") or "จอง" in (sales_st or "")

    year_jongs = []
    for r in year_leads:
        if not has_booking_status(r):
            continue
        seller = normalize_seller(cell(r, L.sales_rep))
        year_jongs.append({
            "seller": seller or "",  # อาจว่างได้ → orphan
            "date": cell(r, L.received_date),
            "code": cell(r, L.lead_code),
        })

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
        # วันที่ปล่อยรถ: ใช้ W (car_release_date) เป็นหลัก, ถ้าว่าง/parse ไม่ได้ ลอง V (legacy)
        new_release = cell(r, S.car_release_date)
        legacy_release = cell(r, S.legacy_car_release_date)
        chosen_release = new_release if (new_release and parse_date(new_release)) else (
            legacy_release if parse_date(legacy_release) else new_release
        )
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
            "releaseDate": chosen_release,
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
    done_cases = [b for b in booking_cases if b["status"] == "ปล่อย"]
    total_done = len(done_cases)
    total_target = sum(TARGETS.values())
    total_follow = len([r for r in year_leads if is_follow(cell(r, L.admin_status))])
    total_vacant = len([r for r in year_leads if is_vacant(cell(r, L.admin_status))])
    # Deal Value — ยอดปล่อยรถ (sum of sale_price for status=ปล่อย)
    total_deal_value = sum(b["price"] for b in done_cases)
    # Pipeline value — มูลค่าดีลที่ยังอยู่ใน pipeline (จอง/รอเซ็นต์/รอผล/รอปล่อย — ไม่รวมรีเจ็ก/ปล่อย)
    pipeline_value = sum(
        b["price"] for b in booking_cases
        if b["status"] in ("จอง", "รอเซ็นต์", "รอผล", "รอปล่อย")
    )

    summary = {
        "totalLeads": len(year_leads),
        "leadNormal": lead_normal,
        "leadRJ": lead_rj,
        "totalFollow": total_follow,
        "totalVacant": total_vacant,
        "totalDone": total_done,
        "totalTarget": total_target,
        "totalBookings": len(year_jongs),
        "totalDealValue": total_deal_value,
        "pipelineValue": pipeline_value,
        "avgDealValue": (total_deal_value / total_done) if total_done else 0,
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
        sb_done = [b for b in sb if b["status"] == "ปล่อย"]
        follow = len([r for r in sl if is_follow(cell(r, L.admin_status))])
        vacant = len([r for r in sl if is_vacant(cell(r, L.admin_status))])
        done = len(sb_done)
        deal_value = sum(b["price"] for b in sb_done)
        pipeline_val = sum(
            b["price"] for b in sb if b["status"] in ("จอง", "รอเซ็นต์", "รอผล", "รอปล่อย")
        )
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
            "dealValue": deal_value,
            "pipelineValue": pipeline_val,
            "avgDealValue": (deal_value / done) if done else 0,
        }
        if s_data["lead"] > 0 or s_data["done"] > 0 or s_data["booking"] > 0:
            sellers.append(s_data)

    # ── 🚫 Unknown/Orphan seller — เคสที่ seller ไม่อยู่ใน ALL_SELLERS หรือ ADMIN
    # เกิดเมื่อ: เซลล์ลาออก / สะกดแปลก / normalize_seller ไม่ map / seller_cell ว่าง /
    # ใช้คำเช่น "หน้าร้าน" "ออนไลน์" ฯลฯ → เคสตกหายไม่ขึ้นในรายบุคคล
    # → รวมเข้า virtual seller "❓ ไม่ระบุ" + เก็บรายชื่อต้นฉบับใน unknownSellerNames (สำหรับ admin debug)
    known_names = set(ALL_SELLERS) | {"ADMIN"}
    # ไม่ใช้ short-circuit "and" — รวมเคส seller ว่าง ("") ด้วย เพราะถือว่า orphan เหมือนกัน
    orphan_bookings = [b for b in booking_cases if b["seller"] not in known_names]
    orphan_leads_rows = [
        r for r in year_leads
        if normalize_seller(cell(r, L.sales_rep)) not in known_names
    ]
    if orphan_bookings or orphan_leads_rows:
        orphan_done_b = [b for b in orphan_bookings if b["status"] == "ปล่อย"]
        orphan_done = len(orphan_done_b)
        orphan_deal_value = sum(b["price"] for b in orphan_done_b)
        orphan_booking = len([j for j in year_jongs if j["seller"] not in known_names])
        orphan_pipeline_val = sum(
            b["price"] for b in orphan_bookings
            if b["status"] in ("จอง", "รอเซ็นต์", "รอผล", "รอปล่อย")
        )
        # ชื่อต้นฉบับ — แทนค่าว่างด้วย "(ว่าง)" ให้ admin เห็น
        orphan_names = sorted({
            (b["seller"] or "(ว่าง)") for b in orphan_bookings
        } | {
            (normalize_seller(cell(r, L.sales_rep)) or "(ว่าง)") for r in orphan_leads_rows
        })
        sellers.append({
            "name": "❓ ไม่ระบุ", "team": "?",
            "lead": len(orphan_leads_rows),
            "follow": len([r for r in orphan_leads_rows if is_follow(cell(r, L.admin_status))]),
            "vacant": len([r for r in orphan_leads_rows if is_vacant(cell(r, L.admin_status))]),
            "done": orphan_done,
            "target": 0, "booking": orphan_booking,
            "live": 0, "clip": 0, "clipTarget": 0,
            "liveInbox": 0, "liveLead": 0,
            "leadTypes": {},
            "dealValue": orphan_deal_value,
            "pipelineValue": orphan_pipeline_val,
            "avgDealValue": (orphan_deal_value / orphan_done) if orphan_done else 0,
            "unknownSellerNames": orphan_names,  # รายชื่อต้นฉบับสำหรับ admin debug
        })

    # ADMIN seller
    admin_leads = [r for r in year_leads if normalize_seller(cell(r, L.sales_rep)) == "ADMIN"]
    if admin_leads:
        admin_follow = len([r for r in admin_leads if is_follow(cell(r, L.admin_status))])
        admin_vacant = len([r for r in admin_leads if is_vacant(cell(r, L.admin_status))])
        admin_sb = [b for b in booking_cases if b["seller"] == "ADMIN"]
        admin_done_b = [b for b in admin_sb if b["status"] == "ปล่อย"]
        admin_done = len(admin_done_b)
        admin_deal_value = sum(b["price"] for b in admin_done_b)
        admin_pipeline_val = sum(
            b["price"] for b in admin_sb if b["status"] in ("จอง", "รอเซ็นต์", "รอผล", "รอปล่อย")
        )
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
            "dealValue": admin_deal_value,
            "pipelineValue": admin_pipeline_val,
            "avgDealValue": (admin_deal_value / admin_done) if admin_done else 0,
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
            "dealValue": sum(s.get("dealValue", 0) for s in ms),
            "pipelineValue": sum(s.get("pipelineValue", 0) for s in ms),
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

        # Pipeline value ของเดือนนี้ — รวมจาก m_bookings (ใช้วันที่จอง = b["date"])
        m_pipeline_value = sum(
            b["price"] for b in m_bookings
            if b["status"] in ("จอง", "รอเซ็นต์", "รอผล", "รอปล่อย")
        )
        m_deal_value = sum(b["price"] for b in m_done)

        m_sellers = {}
        for name in ALL_SELLERS:
            sl2 = [r for r in m_leads if normalize_seller(cell(r, L.sales_rep)) == name]
            sb_done2 = [b for b in m_done if b["seller"] == name]
            sb_pipe2 = [b for b in m_bookings if b["seller"] == name and b["status"] in ("จอง", "รอเซ็นต์", "รอผล", "รอปล่อย")]
            n_done2 = len(sb_done2)
            dv2 = sum(b["price"] for b in sb_done2)
            # Lead types breakdown ของเดือน — สำหรับการ์ด "🏷️ ประเภท Lead" ใน seller view
            m_lead_types: dict[str, int] = {}
            for r in sl2:
                t = cell(r, L.type)
                if t:
                    m_lead_types[t] = m_lead_types.get(t, 0) + 1
            m_sellers[name] = {
                "lead": len(sl2),
                "leadNormal": len([r for r in sl2 if cell(r, L.type) not in RJ_TYPES]),
                "leadRJ": len([r for r in sl2 if cell(r, L.type) in RJ_TYPES]),
                "follow": len([r for r in sl2 if is_follow(cell(r, L.admin_status))]),
                "vacant": len([r for r in sl2 if is_vacant(cell(r, L.admin_status))]),
                "done": n_done2,
                "booking": m_jong_by_seller.get(name, 0),
                "dealValue": dv2,
                "pipelineValue": sum(b["price"] for b in sb_pipe2),
                "avgDealValue": (dv2 / n_done2) if n_done2 else 0,
                "leadTypes": m_lead_types,
            }

        m_teams = {}
        for tid, members in TEAMS.items():
            ts = {"lead": 0, "follow": 0, "vacant": 0, "done": 0, "booking": 0,
                  "dealValue": 0, "pipelineValue": 0}
            for n in members:
                s2 = m_sellers.get(n, {})
                for k in ts:
                    ts[k] += s2.get(k, 0)
            m_teams[tid] = ts

        monthly_summary[m] = {
            "totalLeads": len(m_leads),
            "leadNormal": m_ln,
            "leadRJ": m_lr,
            "totalFollow": m_follow,
            "totalVacant": m_vacant,
            "totalDone": len(m_done),
            "totalBookings": len(m_jongs),
            "totalDealValue": m_deal_value,
            "pipelineValue": m_pipeline_value,
            "avgDealValue": (m_deal_value / len(m_done)) if m_done else 0,
            "pipeline": m_pipeline,
            "sellers": m_sellers,
            "teams": m_teams,
        }

    # ── Lead รถรุ่นไหน (อันดับ) — แยกตามเดือน + รวมปี ──
    # ใช้ "CAR / สูตร" (column M, car_formula) เท่านั้น — สะอาดและ normalize แล้ว
    # โครงสร้าง: {0: {car: count}, 1: {...}, ..., 12: {...}}  (0 = ทั้งปี)
    def _normalize_car(s: str) -> str:
        v = (s or "").strip()
        if not v or v == "-":
            return "ไม่ระบุ"
        # รวม "ไม่ระบุ" / "ไม่ระบุรถ" / "ไม่ระบุรุ่นรถ" → "ไม่ระบุ"
        if "ไม่ระบุ" in v:
            return "ไม่ระบุ"
        return v

    lead_cars_by_month: dict[int, dict[str, int]] = {m: {} for m in range(0, 13)}
    # Lead breakdown per car ต่อเซลล์ (สำหรับ modal เมื่อกดที่รถใน table)
    # โครงสร้าง: {car: {seller: {"total": N, "byMonth": [0]*13}}}
    lead_car_seller_month: dict[str, dict[str, dict]] = {}
    for r in year_leads:
        car = _normalize_car(cell(r, L.car_formula))
        m = get_month(cell(r, L.received_date))
        lead_cars_by_month[0][car] = lead_cars_by_month[0].get(car, 0) + 1
        if 1 <= m <= 12:
            lead_cars_by_month[m][car] = lead_cars_by_month[m].get(car, 0) + 1

        seller = normalize_seller(cell(r, L.sales_rep))
        if not seller or seller == "ADMIN":
            continue
        if car not in lead_car_seller_month:
            lead_car_seller_month[car] = {}
        if seller not in lead_car_seller_month[car]:
            lead_car_seller_month[car][seller] = {"total": 0, "byMonth": [0] * 13}
        lead_car_seller_month[car][seller]["total"] += 1
        if 1 <= m <= 12:
            lead_car_seller_month[car][seller]["byMonth"][m] += 1

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
            "dealValue": [0] * 32,
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
        daily_by_month[mm]["dealValue"][dd] += b["price"] or 0

    # Daily-by-month แยกตามเซลล์ — ใช้ตอน admin impersonate เซลล์คนใดคนหนึ่ง
    daily_by_seller = {
        name: {
            m: {
                "leads": [0] * 32,
                "leadRJ": [0] * 32,
                "bookings": [0] * 32,
                "dones": [0] * 32,
                "dealValue": [0] * 32,
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
        daily_by_seller[b["seller"]][mm]["dealValue"][dd] += b["price"] or 0

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
        "leadCarsByMonth": lead_cars_by_month,
        "leadCarSellerMonth": lead_car_seller_month,
    }
