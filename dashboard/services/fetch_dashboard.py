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


def activity_stats(rows: list) -> dict:
    """คำนวณ stats สำหรับตารางคะแนน 100 แต้ม จาก lead rows ของเซลล์คนหนึ่ง:
    - updateSum: รวมจำนวนอัพเดททุกเคส (ปริมาณติดตาม)
    - proofCount: จำนวนเคสที่มีหลักฐานการโทร (call_proof = 'ส่งแล้ว')
    - returnCount: จำนวนเคสคืน (admin/sales_status มี 'คืน')
    - cancelCount: จำนวนเคสลูกค้ายกเลิก (มี 'ยกเลิก')
    """
    upd_sum = proof = ret = cancel = dist = 0
    for r in rows:
        upd_sum += int(cell_num(r, L.update_count))
        if cell(r, L.call_proof) == "ส่งแล้ว":
            proof += 1
        combined = f"{cell(r, L.admin_status)} {cell(r, L.sales_status)}"
        if "คืน" in combined:
            ret += 1
        if "ยกเลิก" in combined:
            cancel += 1
        # distributable = lead ที่แจกจ่ายได้ (ไม่ใช่ไลฟ์สด + ไม่ใช่ RJ)
        # ใช้เฉพาะ "จัดสรร Lead อนาคต" — ไม่กระทบ KPI/เคส/RJ ที่นับเต็ม
        _ch = cell(r, L.channel).strip().upper()
        _ty = cell(r, L.type).strip().upper().replace(" ", "")
        if not _ch.startswith("LIVE") and _ty not in ("RJ", "HOTRJ", "HOTRB"):
            dist += 1
    return {"updateSum": upd_sum, "proofCount": proof,
            "returnCount": ret, "cancelCount": cancel, "leadDist": dist}


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
    raw_bookings = raw["bookings"]   # ← นับ "จอง" จาก sheet นี้ (source of truth)
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

    # Jongs — นับจาก bookings sheet (source of truth)
    # ผู้ใช้ต้องการให้ตัวเลขตรงกับ bookings spreadsheet ที่ admin บันทึก
    # status อื่น (รอเซ็น/รอผล/รอปล่อย/ปล่อย/รีเจ็ก) ยังนับจาก sales_reports (booking_cases ด้านล่าง)
    year_jongs = []
    for r in raw_bookings:
        date_str = cell(r, B.date)
        if not is_this_year(date_str):
            continue
        # skip header / non-data rows
        no_val = cell(r, B.no)
        if not no_val or no_val in ("ลำดับ", "no", "No"):
            continue
        seller_raw = cell(r, B.sales_rep).replace("ชื่อเซลล์ ", "").replace("ชื่อเซลล์", "").strip()
        seller = normalize_seller(seller_raw)
        year_jongs.append({
            "seller": seller or "",  # อาจว่าง → orphan
            "date": date_str,
            "code": cell(r, B.code),
        })

    # BookingCases from sales_reports
    # สร้าง map leadCode → received_date (ล่าสุด) เพื่อใช้คำนวณ Velocity Phase 1
    # ถ้า code ซ้ำ (admin เปิดเคสใหม่ใช้ code เดิม) → เลือกวันที่ล่าสุด
    # ไม่งั้นจะคำนวณ velocity ผิด (lead จาก ก.พ. แต่จองจริง พ.ค. = 94 วัน)
    lead_received_map = {}
    for r in year_leads:
        code = cell(r, L.lead_code).strip()
        if not code:
            continue
        new_date_str = cell(r, L.received_date)
        new_d = parse_date(new_date_str)
        if not new_d:
            continue
        existing = lead_received_map.get(code)
        if not existing:
            lead_received_map[code] = new_date_str
        else:
            existing_d = parse_date(existing)
            if not existing_d or new_d > existing_d:
                lead_received_map[code] = new_date_str

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
        lead_code = cell(r, S.lead_code).strip()
        channel_val = cell(r, S.channel)
        booking_cases.append({
            "seller": seller,
            "status": status.replace(" (ซื้อสด)", "").strip(),
            "isCash": is_cash,
            "channel": channel_val,
            "customer": cell(r, S.customer_name),
            "phone": cell(r, S.phone),
            "car": cell(r, S.car_detail),
            "year": cell(r, S.car_year),
            "plate": cell(r, S.license_plate),
            "price": cell_num(r, S.sale_price),
            "deposit": cell_num(r, S.deposit_amount),
            "leadCode": lead_code,
            "leadDate": lead_received_map.get(lead_code, ""),  # วันรับหลีดเดิม (Velocity Phase 1)
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
        # ยังไม่อัพเดท = update_count == 0 และไม่ใช่ junk
        not_called = 0
        for r in sl:
            if int(cell_num(r, L.update_count)) > 0:
                continue
            if is_skipped(cell(r, L.admin_status)) or is_skipped(cell(r, L.sales_status)):
                continue
            not_called += 1
        done = len(sb_done)
        deal_value = sum(b["price"] for b in sb_done)
        pipeline_val = sum(
            b["price"] for b in sb if b["status"] in ("จอง", "รอเซ็นต์", "รอผล", "รอปล่อย")
        )
        lead_types = {}
        for r in sl:
            t = cell(r, L.type) or "ไม่ระบุ"
            lead_types[t] = lead_types.get(t, 0) + 1
        astats = activity_stats(sl)   # updateSum / proofCount / returnCount / cancelCount
        s_data = {
            "name": name,
            "team": TEAM_ID.get(name, "?"),
            "lead": len(sl),
            "follow": follow,
            "vacant": vacant,
            "notCalled": not_called,
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
            # สำหรับตารางคะแนน 100 แต้ม
            "updateSum": astats["updateSum"],
            "proofCount": astats["proofCount"],
            "returnCount": astats["returnCount"],
            "cancelCount": astats["cancelCount"],
            "leadDist": astats["leadDist"],
        }
        if s_data["lead"] > 0 or s_data["done"] > 0 or s_data["booking"] > 0:
            sellers.append(s_data)

    # ── 🚫 Orphan sellers — เซลล์ที่ไม่อยู่ใน config ปัจจุบัน (ส่วนใหญ่คือเซลล์เก่าที่ลาออก)
    # เกิดเมื่อ: เซลล์ลาออก / สะกดแปลก / normalize_seller ไม่ map / seller_cell ว่าง /
    # ใช้คำเช่น "หน้าร้าน" "ออนไลน์" ฯลฯ → เคสตกหายไม่ขึ้นในรายบุคคล
    # → สร้าง row ต่อชื่อ (ไม่รวม) เพื่อให้ admin เห็น breakdown ของเซลล์เก่า
    known_names = set(ALL_SELLERS) | {"ADMIN"}
    # Group orphan rows by normalized seller name
    orphan_groups: dict[str, dict] = {}
    for r in year_leads:
        s = normalize_seller(cell(r, L.sales_rep)) or "(ว่าง)"
        if s in known_names:
            continue
        g = orphan_groups.setdefault(s, {"leads": [], "bookings": [], "dones": [], "jongs": []})
        g["leads"].append(r)
    for b in booking_cases:
        s = b["seller"] or "(ว่าง)"
        if s in known_names:
            continue
        g = orphan_groups.setdefault(s, {"leads": [], "bookings": [], "dones": [], "jongs": []})
        g["bookings"].append(b)
        if b["status"] == "ปล่อย":
            g["dones"].append(b)
    for j in year_jongs:
        s = j["seller"] or "(ว่าง)"
        if s in known_names:
            continue
        g = orphan_groups.setdefault(s, {"leads": [], "bookings": [], "dones": [], "jongs": []})
        g["jongs"].append(j)

    # เพิ่ม row ต่อชื่อเซลล์เก่า (sort by lead count desc)
    for name, g in sorted(orphan_groups.items(), key=lambda x: -len(x[1]["leads"])):
        n_done = len(g["dones"])
        deal_value = sum(b["price"] for b in g["dones"])
        pipeline_val = sum(
            b["price"] for b in g["bookings"]
            if b["status"] in ("จอง", "รอเซ็นต์", "รอผล", "รอปล่อย")
        )
        sellers.append({
            "name": name, "team": "INACTIVE",  # team = INACTIVE → frontend แสดงเป็น "เซลล์เก่า"
            "lead": len(g["leads"]),
            "follow": len([r for r in g["leads"] if is_follow(cell(r, L.admin_status))]),
            "vacant": len([r for r in g["leads"] if is_vacant(cell(r, L.admin_status))]),
            "done": n_done,
            "target": 0, "booking": len(g["jongs"]),
            "live": 0, "clip": 0, "clipTarget": 0,
            "liveInbox": 0, "liveLead": 0,
            "leadTypes": {},
            "dealValue": deal_value,
            "pipelineValue": pipeline_val,
            "avgDealValue": (deal_value / n_done) if n_done else 0,
            "inactive": True,  # ใช้สำหรับ frontend แยก style
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
        # ADMIN booking: bookings sheet ไม่มี ADMIN → นับจอง จาก leads sheet (admin/sales_status มี "จอง")
        admin_booking = len([j for j in year_jongs if j["seller"] == "ADMIN"])
        if admin_booking == 0:
            admin_booking = len([
                r for r in admin_leads
                if not (is_skipped(cell(r, L.admin_status)) or is_skipped(cell(r, L.sales_status)))
                and ("จอง" in (cell(r, L.admin_status) or "") or "จอง" in (cell(r, L.sales_status) or ""))
            ])
        admin_types = {}
        for r in admin_leads:
            t = cell(r, L.type) or "ไม่ระบุ"
            admin_types[t] = admin_types.get(t, 0) + 1
        admin_astats = activity_stats(admin_leads)
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
            "updateSum": admin_astats["updateSum"],
            "proofCount": admin_astats["proofCount"],
            "returnCount": admin_astats["returnCount"],
            "cancelCount": admin_astats["cancelCount"],
            "leadDist": admin_astats["leadDist"],
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

    # ── Not Called Cases — เคสที่ updateCount=0 และไม่ใช่ junk (ใช้ใน 🔴 modal) ──
    not_called_cases = []
    for r in year_leads:
        if int(cell_num(r, L.update_count)) > 0:
            continue
        admin_st = cell(r, L.admin_status)
        sales_st = cell(r, L.sales_status)
        if is_skipped(admin_st) or is_skipped(sales_st):
            continue
        seller = normalize_seller(cell(r, L.sales_rep)) or "-"
        if seller == "-":
            continue
        not_called_cases.append({
            "code": cell(r, L.lead_code) or "-",
            "seller": seller,
            "phone": cell(r, L.phone) or "-",
            "leadType": cell(r, L.type),
            "car": cell(r, L.car_inquiry) or cell(r, L.car_formula) or "-",
            "channel": cell(r, L.channel) or "-",
            "dateIn": cell(r, L.received_date) or "-",
            "adminStatus": admin_st or "-",
        })

    # ── Booking (จอง) cases — จาก bookings sheet สำหรับ 🏆 modal ──
    jong_cases = []
    for r in raw_bookings:
        date_str = cell(r, B.date)
        if not is_this_year(date_str):
            continue
        no_val = cell(r, B.no)
        if not no_val or no_val in ("ลำดับ", "no", "No"):
            continue
        seller_raw = cell(r, B.sales_rep).replace("ชื่อเซลล์ ", "").replace("ชื่อเซลล์", "").strip()
        seller = normalize_seller(seller_raw) or "-"
        if seller == "-":
            continue
        jong_cases.append({
            "code": cell(r, B.code) or "-",
            "seller": seller,
            "date": date_str,
            "channel": cell(r, B.channel) or "-",
            "car": cell(r, B.car) or cell(r, B.car_formula) or "-",
            "customer": cell(r, B.customer_name) or "-",
            "plate": cell(r, B.plate) or "-",
            "amount": cell_num(r, B.booking_amount),
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
            # ยังไม่อัพเดท = update_count == 0 และไม่ใช่เคส junk (จบ/คืน/ยกเลิก/จ่ายใหม่)
            m_not_called = 0
            for r in sl2:
                if int(cell_num(r, L.update_count)) > 0:
                    continue
                if is_skipped(cell(r, L.admin_status)) or is_skipped(cell(r, L.sales_status)):
                    continue
                m_not_called += 1
            m_astats = activity_stats(sl2)
            m_sellers[name] = {
                "lead": len(sl2),
                "leadNormal": len([r for r in sl2 if cell(r, L.type) not in RJ_TYPES]),
                "leadRJ": len([r for r in sl2 if cell(r, L.type) in RJ_TYPES]),
                "follow": len([r for r in sl2 if is_follow(cell(r, L.admin_status))]),
                "vacant": len([r for r in sl2 if is_vacant(cell(r, L.admin_status))]),
                "notCalled": m_not_called,
                "done": n_done2,
                "booking": m_jong_by_seller.get(name, 0),
                "dealValue": dv2,
                "pipelineValue": sum(b["price"] for b in sb_pipe2),
                "avgDealValue": (dv2 / n_done2) if n_done2 else 0,
                "leadTypes": m_lead_types,
                # ตารางคะแนน 100 แต้ม
                "updateSum": m_astats["updateSum"],
                "proofCount": m_astats["proofCount"],
                "returnCount": m_astats["returnCount"],
                "cancelCount": m_astats["cancelCount"],
                "leadDist": m_astats["leadDist"],
            }

        # ── เพิ่ม orphan sellers ต่อเดือน — split per name (เซลล์เก่าแต่ละคน) ──
        m_orphan_groups: dict[str, dict] = {}
        for r in m_leads:
            s = normalize_seller(cell(r, L.sales_rep)) or "(ว่าง)"
            if s in known_names:
                continue
            g = m_orphan_groups.setdefault(s, {"leads": [], "bookings": [], "dones": [], "jongs": 0})
            g["leads"].append(r)
        for b in m_bookings:
            s = b["seller"] or "(ว่าง)"
            if s in known_names:
                continue
            g = m_orphan_groups.setdefault(s, {"leads": [], "bookings": [], "dones": [], "jongs": 0})
            g["bookings"].append(b)
        for b in m_done:
            s = b["seller"] or "(ว่าง)"
            if s in known_names:
                continue
            g = m_orphan_groups.setdefault(s, {"leads": [], "bookings": [], "dones": [], "jongs": 0})
            g["dones"].append(b)
        for j in m_jongs:
            s = j["seller"] or "(ว่าง)"
            if s in known_names:
                continue
            g = m_orphan_groups.setdefault(s, {"leads": [], "bookings": [], "dones": [], "jongs": 0})
            g["jongs"] += 1

        for orphan_name, g in m_orphan_groups.items():
            n_done = len(g["dones"])
            dv = sum(b["price"] for b in g["dones"])
            pipe_b = [b for b in g["bookings"]
                      if b["status"] in ("จอง", "รอเซ็นต์", "รอผล", "รอปล่อย")]
            o_astats = activity_stats(g["leads"])
            # จอง: bookings sheet (g["jongs"]) — ถ้า 0 (เช่น ADMIN) นับจาก leads status
            o_booking = g["jongs"]
            if o_booking == 0:
                o_booking = len([
                    r for r in g["leads"]
                    if not (is_skipped(cell(r, L.admin_status)) or is_skipped(cell(r, L.sales_status)))
                    and ("จอง" in (cell(r, L.admin_status) or "") or "จอง" in (cell(r, L.sales_status) or ""))
                ])
            m_sellers[orphan_name] = {
                "lead": len(g["leads"]),
                "leadNormal": len([r for r in g["leads"] if cell(r, L.type) not in RJ_TYPES]),
                "leadRJ": len([r for r in g["leads"] if cell(r, L.type) in RJ_TYPES]),
                "follow": len([r for r in g["leads"] if is_follow(cell(r, L.admin_status))]),
                "vacant": len([r for r in g["leads"] if is_vacant(cell(r, L.admin_status))]),
                "done": n_done,
                "booking": o_booking,
                "dealValue": dv,
                "pipelineValue": sum(b["price"] for b in pipe_b),
                "avgDealValue": (dv / n_done) if n_done else 0,
                "leadTypes": {},
                "inactive": True,
                "updateSum": o_astats["updateSum"],
                "proofCount": o_astats["proofCount"],
                "returnCount": o_astats["returnCount"],
                "cancelCount": o_astats["cancelCount"],
                "leadDist": o_astats["leadDist"],
            }

        # ── ADMIN (monthly) — orphan handling ข้าม ADMIN ผ่าน known_names จึงต้องเพิ่มเอง ──
        m_admin_leads = [r for r in m_leads if normalize_seller(cell(r, L.sales_rep)) == "ADMIN"]
        if m_admin_leads:
            m_admin_done = [b for b in m_done if b["seller"] == "ADMIN"]
            m_admin_dv = sum(b["price"] for b in m_admin_done)
            # จอง: bookings sheet → ถ้า 0 นับจาก leads status
            m_admin_booking = m_jong_by_seller.get("ADMIN", 0)
            if m_admin_booking == 0:
                m_admin_booking = len([
                    r for r in m_admin_leads
                    if not (is_skipped(cell(r, L.admin_status)) or is_skipped(cell(r, L.sales_status)))
                    and ("จอง" in (cell(r, L.admin_status) or "") or "จอง" in (cell(r, L.sales_status) or ""))
                ])
            m_admin_astats = activity_stats(m_admin_leads)
            m_sellers["ADMIN"] = {
                "lead": len(m_admin_leads),
                "leadNormal": len([r for r in m_admin_leads if cell(r, L.type) not in RJ_TYPES]),
                "leadRJ": len([r for r in m_admin_leads if cell(r, L.type) in RJ_TYPES]),
                "follow": len([r for r in m_admin_leads if is_follow(cell(r, L.admin_status))]),
                "vacant": len([r for r in m_admin_leads if is_vacant(cell(r, L.admin_status))]),
                "done": len(m_admin_done),
                "booking": m_admin_booking,
                "dealValue": m_admin_dv,
                "pipelineValue": 0,
                "avgDealValue": (m_admin_dv / len(m_admin_done)) if m_admin_done else 0,
                "leadTypes": {},
                "updateSum": m_admin_astats["updateSum"],
                "proofCount": m_admin_astats["proofCount"],
                "returnCount": m_admin_astats["returnCount"],
                "cancelCount": m_admin_astats["cancelCount"],
                "leadDist": m_admin_astats["leadDist"],
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
        "notCalledCases": not_called_cases,   # 🔴 ยังไม่อัพเดท modal
        "jongCases": jong_cases,              # 🏆 Top จอง modal
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


# ── Diligence Score ── port จาก JS (index.html buildDilMap + diligenceScore)
SCORE_JONG = 50
SCORE_DONE = 100
RJ_WEIGHT = 0.5
JONG_STATUSES = ("จอง", "รอเซ็นต์", "รอผล", "รอปล่อย")


def diligence_score_for_calls(update_count: int, is_rj: bool) -> int:
    """คะแนนความขยันจากการโทร — ปกติ: 1=10, 2=15, 3+=5/ครั้ง; RJ: × 0.5"""
    u = max(0, int(update_count or 0))
    if u == 0:
        return 0
    if u == 1:
        base = 10
    elif u == 2:
        base = 25                      # 10 + 15
    else:
        base = 25 + (u - 2) * 5         # 10 + 15 + (u-2)*5
    return round(base * RJ_WEIGHT) if is_rj else base


def compute_diligence_scores(target_month: int | None = None,
                             target_year: int | None = None) -> list[dict]:
    """คำนวณ Diligence Score รายเซลล์ของเดือนที่เลือก
    คืน list ของ dict — 1 entry ต่อเซลล์ พร้อม breakdown ครบ

    Args:
        target_month: เดือน 1-12, None = เดือนปัจจุบัน
        target_year: ปี ค.ศ., None = ปีปัจจุบัน

    Returns: [{name, team, score, cnt, cntNormal, cntRJ, totUpdates, jongs, dones,
              scoreCall, scoreCallNormal, scoreCallRJ, scoreJong, scoreDone,
              avg, high, target}, ...]
    """
    from .constants import refresh_from_sheet, TEAMS, TEAM_ID, TARGETS, ALL_SELLERS, RJ_TYPES
    refresh_from_sheet()

    now = bangkok_now()
    m = target_month if target_month else now.month
    y = target_year if target_year else now.year

    # ดึง raw data
    data = fetch_dashboard_data()
    follow_cases = data.get("followCases", [])
    booking_cases = data.get("bookingCases", [])
    monthly = data.get("monthlySummary", {})

    rj_set = set(RJ_TYPES)
    score_map: dict[str, dict] = {}

    def _ensure(name: str) -> dict:
        if name not in score_map:
            score_map[name] = {
                "name": name,
                "team": TEAM_ID.get(name, ""),
                "target": TARGETS.get(name, 0),
                "score": 0, "cnt": 0, "cntNormal": 0, "cntRJ": 0,
                "totUpdates": 0, "totNormal": 0, "totRJ": 0,
                "jongs": 0, "dones": 0,
                "scoreCall": 0, "scoreCallNormal": 0, "scoreCallRJ": 0,
                "scoreJong": 0, "scoreDone": 0,
                "high": 0,
            }
        return score_map[name]

    # ── ส่วน 1: คะแนนจากการโทร (followCases ใน month) ──
    for l in follow_cases:
        d = parse_date(l.get("dateIn", ""))
        if not d or d.year != y or d.month != m:
            continue
        e = _ensure(l["seller"])
        upd = int(l.get("updateCount", 0))
        is_rj = l.get("leadType") in rj_set
        e["totUpdates"] += upd
        if is_rj:
            e["cntRJ"] += 1
            e["totRJ"] += upd
        else:
            e["cntNormal"] += 1
            e["totNormal"] += upd
        e["cnt"] += 1
        if upd >= 3:
            e["high"] += 1
        sc = diligence_score_for_calls(upd, is_rj)
        if is_rj:
            e["scoreCallRJ"] += sc
        else:
            e["scoreCallNormal"] += sc
        e["scoreCall"] += sc
        e["score"] += sc

    # ── ส่วน 2: คะแนนจอง/ปล่อย จาก monthlySummary[m].sellers[name] ──
    m_sellers = (monthly.get(m) or monthly.get(str(m)) or {}).get("sellers", {})
    for name, sd in m_sellers.items():
        if name not in ALL_SELLERS and name != "ADMIN":
            continue  # skip orphan/inactive
        jongs = int(sd.get("booking", 0))
        dones = int(sd.get("done", 0))
        if jongs > 0 or dones > 0:
            e = _ensure(name)
            e["jongs"] = jongs
            e["dones"] = dones
            e["scoreJong"] = jongs * SCORE_JONG
            e["scoreDone"] = dones * SCORE_DONE
            e["score"] += e["scoreJong"] + e["scoreDone"]

    # avg per case
    for e in score_map.values():
        e["avg"] = round(e["totUpdates"] / e["cnt"], 2) if e["cnt"] else 0

    # เซลล์ที่ active แต่ไม่มี data ในเดือนนั้น → ใส่ entry ว่างไว้
    for name in ALL_SELLERS:
        if name not in score_map:
            _ensure(name)

    # Sort by score desc
    out = sorted(score_map.values(), key=lambda x: -x["score"])
    return out


def export_leadscore_to_sheet(target_month: int | None = None,
                              target_year: int | None = None) -> dict:
    """เขียน Diligence Score ลง sheet 'leadscore' (clear + write)
    คืน dict {ok, rows_written, month, year}
    """
    from .google_sheets import write_sheet

    now = bangkok_now()
    m = target_month if target_month else now.month
    y = target_year if target_year else now.year
    scores = compute_diligence_scores(m, y)

    month_name = MONTHS_FULL_TH[m - 1] if 1 <= m <= 12 else f"เดือน {m}"
    generated_at = now.isoformat(timespec="seconds")

    header = [
        "เซลล์", "ทีม", "Score รวม",
        "เคสรับ", "ปกติ", "RJ",
        "จำนวนโทรรวม", "เฉลี่ย/เคส", "🔥 3+",
        "จอง", "ปล่อย",
        "คะแนนโทร (Normal)", "คะแนนโทร (RJ)", "คะแนนจอง", "คะแนนปล่อย",
        "เป้า/เดือน", "เดือน", "ปี", "อัพเดทเมื่อ",
    ]
    rows = [header]
    for e in scores:
        rows.append([
            e["name"], e["team"], e["score"],
            e["cnt"], e["cntNormal"], e["cntRJ"],
            e["totUpdates"], e["avg"], e["high"],
            e["jongs"], e["dones"],
            e["scoreCallNormal"], e["scoreCallRJ"], e["scoreJong"], e["scoreDone"],
            e["target"], month_name, y, generated_at,
        ])

    write_sheet("leadscore", rows)
    return {"ok": True, "rows_written": len(scores), "month": m, "year": y, "month_name": month_name}


# Thai months — ใช้ใน export_leadscore_to_sheet
MONTHS_FULL_TH = [
    "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
    "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
]


# Alias สำหรับ /admin/ และ /dashboard/ — same data
fetch_global_stats = fetch_dashboard_data


def fetch_seller_stats(seller_name: str) -> dict:
    """ดึง data เฉพาะของเซลล์คนเดียว — ใช้ใน /s/<token>/

    Goals:
    - Performance: ไม่ aggregate ทุกเซลล์ (skip teams/leadCarsByMonth/dailyBySeller)
    - Data isolation: JSON ส่งไป frontend มีเฉพาะข้อมูลของเซลล์คนนี้
      (กันเซลล์เปิด DevTools แล้วเห็นข้อมูลเพื่อน)
    - Quota: ใช้ fetch_all_sheets() ที่มี cache 60s → ครั้งแรกใช้ quota
      เท่ากับ global, ครั้งต่อมาภายใน 60s ใช้ 0 API calls

    Returns: dict shape เหมือนที่ seller.html ใช้ — meta/seller/today/leads/
    followCases/bookingCases/mustCallCount/daily/monthly
    """
    from .constants import refresh_from_sheet, TEAM_ID, TARGETS

    refresh_from_sheet()
    raw = fetch_all_sheets()
    raw_leads = raw["leads"]
    sales_reports = raw["sales_reports"]
    raw_bookings = raw["bookings"]   # ← นับ "จอง" จาก bookings sheet (source of truth)

    now = bangkok_now()
    year_full = now.year

    # ── 1) Filter ก่อนทุกอย่าง — ลด work ทันที ──
    my_year_leads = [
        r for r in raw_leads
        if is_this_year(cell(r, L.received_date))
        and normalize_seller(cell(r, L.sales_rep)) == seller_name
    ]
    my_today_leads = [
        r for r in my_year_leads
        if is_today(cell(r, L.received_date))
    ]

    # ── 2) Booking cases ของเซลล์ (จาก sales_reports) ──
    # map leadCode → received_date (ล่าสุด) สำหรับ Velocity Phase 1
    # ถ้า code ซ้ำ → เลือกวันรับล่าสุด (ไม่งั้น velocity เพี้ยน)
    my_lead_received_map = {}
    for r in my_year_leads:
        code = cell(r, L.lead_code).strip()
        if not code:
            continue
        new_date_str = cell(r, L.received_date)
        new_d = parse_date(new_date_str)
        if not new_d:
            continue
        existing = my_lead_received_map.get(code)
        if not existing:
            my_lead_received_map[code] = new_date_str
        else:
            existing_d = parse_date(existing)
            if not existing_d or new_d > existing_d:
                my_lead_received_map[code] = new_date_str

    my_booking_cases = []
    for r in sales_reports:
        seller_raw = cell(r, S.sales_rep).replace("ชื่อเซลล์ ", "").replace("ชื่อเซลล์", "").strip()
        if normalize_seller(seller_raw) != seller_name:
            continue
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
        new_release = cell(r, S.car_release_date)
        legacy_release = cell(r, S.legacy_car_release_date)
        chosen_release = new_release if (new_release and parse_date(new_release)) else (
            legacy_release if parse_date(legacy_release) else new_release
        )
        lead_code = cell(r, S.lead_code).strip()
        channel_val = cell(r, S.channel)
        my_booking_cases.append({
            "seller": seller_name,
            "status": status.replace(" (ซื้อสด)", "").strip(),
            "isCash": is_cash,
            "channel": channel_val,
            "customer": cell(r, S.customer_name),
            "phone": cell(r, S.phone),
            "car": cell(r, S.car_detail),
            "year": cell(r, S.car_year),
            "plate": cell(r, S.license_plate),
            "price": cell_num(r, S.sale_price),
            "deposit": cell_num(r, S.deposit_amount),
            "leadCode": lead_code,
            "leadDate": my_lead_received_map.get(lead_code, ""),  # วันรับหลีดเดิม (Velocity Phase 1)
            "date": cell(r, S.date),
            "signDate": cell(r, S.sign_date),
            "resultDate": cell(r, S.result_date),
            "docsDate": cell(r, S.doc_complete_date),
            "releaseDate": chosen_release,
            "finance": cell(r, S.finance_main),
            "grade": cell(r, S.grade),
            "note": cell(r, S.note),
        })

    # ── 3) Year jongs ของเซลล์ (จาก bookings sheet — source of truth) ──
    my_year_jongs = []
    for r in raw_bookings:
        date_str = cell(r, B.date)
        if not is_this_year(date_str):
            continue
        no_val = cell(r, B.no)
        if not no_val or no_val in ("ลำดับ", "no", "No"):
            continue
        seller_raw = cell(r, B.sales_rep).replace("ชื่อเซลล์ ", "").replace("ชื่อเซลล์", "").strip()
        if normalize_seller(seller_raw) != seller_name:
            continue
        my_year_jongs.append({
            "date": date_str,
            "code": cell(r, B.code),
        })

    # ── 4) Follow cases ของเซลล์ ──
    my_follow_cases = []
    for r in my_year_leads:
        if not is_follow(cell(r, L.admin_status)):
            continue
        note_raw = cell(r, L.fill_sheet_note) or "-"
        note = re.sub(r"^\d{4,5}\s*", "", note_raw) or "-"
        my_follow_cases.append({
            "code": cell(r, L.lead_code) or "-",
            "seller": seller_name,
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

    # ── 4.5) Lead Score — เติมคะแนนคุณภาพ lead ต่อเคส (priority "โทรเคสไหนก่อน") ──
    try:
        attach_lead_scores(my_follow_cases, my_year_leads, sales_reports)
    except Exception:
        for c in my_follow_cases:
            c.setdefault("leadScore", 0)
            c.setdefault("leadTier", "❄cold")
            c.setdefault("scoreBreakdown", [])

    # ── 5) Today summary (เฉพาะเซลล์) ──
    my_today = {
        "lead": len(my_today_leads),
        "follow": len([r for r in my_today_leads if is_follow(cell(r, L.admin_status))]),
        "vacant": len([r for r in my_today_leads if is_vacant(cell(r, L.admin_status))]),
    }

    # ── 6) Monthly summary (เฉพาะเซลล์, 12 เดือน) ──
    def get_done_month(b: dict) -> int:
        rd = b.get("releaseDate")
        if rd:
            d = parse_date(rd)
            if d:
                return d.month
        return get_month(b["date"])

    my_monthly = {}
    for m in range(1, 13):
        m_leads = [r for r in my_year_leads if get_month(cell(r, L.received_date)) == m]
        m_jongs = [j for j in my_year_jongs if get_month(j["date"]) == m]
        m_done = [b for b in my_booking_cases if b["status"] == "ปล่อย" and get_done_month(b) == m]
        n_done = len(m_done)
        dv = sum(b["price"] for b in m_done)
        my_monthly[m] = {
            "lead": len(m_leads),
            "leadNormal": len([r for r in m_leads if cell(r, L.type) not in RJ_TYPES]),
            "leadRJ": len([r for r in m_leads if cell(r, L.type) in RJ_TYPES]),
            "follow": len([r for r in m_leads if is_follow(cell(r, L.admin_status))]),
            "vacant": len([r for r in m_leads if is_vacant(cell(r, L.admin_status))]),
            "done": n_done,
            "booking": len(m_jongs),
            "dealValue": dv,
        }

    # ── 7) Daily breakdown (เฉพาะเซลล์, 12 เดือน × 32 วัน) ──
    def _parse_day(date_str: str):
        d = parse_date(date_str)
        return (d.month, d.day) if d else None

    my_daily = {
        m: {"leads": [0]*32, "leadRJ": [0]*32, "bookings": [0]*32, "dones": [0]*32, "dealValue": [0]*32}
        for m in range(1, 13)
    }
    for r in my_year_leads:
        md = _parse_day(cell(r, L.received_date))
        if not md:
            continue
        mm, dd = md
        bucket = "leadRJ" if cell(r, L.type) in RJ_TYPES else "leads"
        my_daily[mm][bucket][dd] += 1
    for j in my_year_jongs:
        md = _parse_day(j["date"])
        if not md:
            continue
        mm, dd = md
        my_daily[mm]["bookings"][dd] += 1
    for b in my_booking_cases:
        if b["status"] != "ปล่อย":
            continue
        rd = b.get("releaseDate") or b.get("date")
        md = _parse_day(rd)
        if not md:
            continue
        mm, dd = md
        my_daily[mm]["dones"][dd] += 1
        my_daily[mm]["dealValue"][dd] += b["price"] or 0

    # ── 8) Year-level seller card (lead/follow/vacant/done/booking/dealValue) ──
    n_done_year = sum(1 for b in my_booking_cases if b["status"] == "ปล่อย")
    dv_year = sum(b["price"] for b in my_booking_cases if b["status"] == "ปล่อย")
    my_seller = {
        "name": seller_name,
        "team": TEAM_ID.get(seller_name, "?"),
        "target": TARGETS.get(seller_name, 0),
        "lead": len(my_year_leads),
        "follow": len([r for r in my_year_leads if is_follow(cell(r, L.admin_status))]),
        "vacant": len([r for r in my_year_leads if is_vacant(cell(r, L.admin_status))]),
        "done": n_done_year,
        "booking": len(my_year_jongs),
        "dealValue": dv_year,
        "live": 0, "clip": 0, "clipTarget": 0,
        "liveInbox": 0, "liveLead": 0,
        "leadTypes": {},
    }

    return {
        "meta": {
            "generatedAt": now.isoformat(),
            "month": now.month,
            "year": year_full,
        },
        "seller": my_seller,
        "today": my_today,
        "bookingCases": my_booking_cases,
        "followCases": my_follow_cases,
        "daily": my_daily,
        "monthly": my_monthly,
        "leadScoreEnabled": True,
        # NOTE: ไม่ส่ง sellers[]/teams/leadCarsByMonth/userIdMap/employees ไป
        # → frontend ไม่มีข้อมูลเซลล์อื่นๆ ให้แอบดูใน DevTools
    }


# ════════════════════════════════════════════════════════════════
# Lead Score — คำนวณคะแนนคุณภาพของแต่ละ lead
# ════════════════════════════════════════════════════════════════
# อ่านเกณฑ์จาก sheet "เกณฑ์คะแนน lead" (tab ใน employees spreadsheet)
# Admin แก้คะแนนใน sheet ได้ตลอด — ระบบ pickup ทุก 60s (cache TTL)
#
# คะแนนสะท้อน "ลูกค้าคนนี้น่าปิดแค่ไหน" — ไม่เกี่ยวกับเซลล์
# เซลล์ใช้คะแนนนี้ priority "วันนี้โทรเคสไหนก่อน"
# ════════════════════════════════════════════════════════════════

# Default config — ใช้ตอน sheet ว่างหรืออ่านไม่ได้
_LEAD_SCORE_DEFAULTS: dict[str, int] = {
    "Lead ใหม่ (≤3 วัน)": 20,
    "Lead ปานกลาง (4-7 วัน)": 10,
    "Lead เก่า (8-14 วัน)": 0,
    "Lead เย็น (>14 วัน)": -5,
    "ประเภท: Normal": 50,
    "ประเภท: Hot RB": 30,
    "ประเภท: Hot RJ": 25,
    "ประเภท: RJ": 15,
    "รุ่นรถยอดนิยม (top 20)": 20,
    "ราคารถสูง (≥500,000)": 10,
    "ราคารถปานกลาง (200-500k)": 5,
    "เคยจองแล้วยกเลิก": -5,
    "เคยจอง+ปล่อยสำเร็จ": -10,
    "มาจาก Facebook Ads": 5,
    "มาจาก TikTok / ไลฟ์สด": 10,
    "มาจาก Walk-in / โทรมา": 15,
    "ลูกค้าตอบไลน์/โทรกลับ": 25,
    "ลูกค้าทักก่อน (inbox)": 15,
    "โทรไม่รับเกิน 3 ครั้ง": -10,
}


def load_lead_score_config() -> dict[str, int]:
    """อ่าน config จาก sheet → dict {name: score} เฉพาะที่ enabled=TRUE.
    ถ้าอ่านไม่ได้/ว่าง → fallback _LEAD_SCORE_DEFAULTS.
    """
    try:
        from .google_sheets import fetch_sheet
        rows = fetch_sheet("lead_score_config")
    except Exception:
        return dict(_LEAD_SCORE_DEFAULTS)

    cfg: dict[str, int] = {}
    for r in rows:
        if len(r) < 4:
            continue
        name = (r[0] or "").strip()
        if not name or name == "ชื่อเกณฑ์":
            continue
        enabled = (r[3] or "").strip().upper()
        if enabled not in ("TRUE", "T", "YES", "1", "ใช่"):
            continue
        try:
            score = int(float((r[2] or "0").strip()))
        except (ValueError, TypeError):
            continue
        cfg[name] = score

    return cfg if cfg else dict(_LEAD_SCORE_DEFAULTS)


def _build_lead_history_maps(sales_reports: list) -> tuple[set, set]:
    """สร้าง set ของ lead_code ที่เคยยกเลิก / เคยปล่อยสำเร็จ.
    ใช้สำหรับ Lead Score history component.
    """
    cancelled = set()
    done = set()
    for r in sales_reports:
        code = cell(r, S.lead_code).strip()
        if not code:
            continue
        status = cell(r, S.status).lower()
        if any(k in status for k in ("ยกเลิก", "คืน", "รีเจ็ก")):
            cancelled.add(code)
        elif "ปล่อย" in status:
            done.add(code)
    return cancelled, done


def _build_top_cars_set(raw_leads: list, top_n: int = 20) -> set:
    """หา top N รุ่นรถยอดนิยม (จาก car_formula column M)."""
    counts: dict[str, int] = {}
    for r in raw_leads:
        car = cell(r, L.car_formula).strip()
        if not car or car == "ไม่ระบุ":
            continue
        counts[car] = counts.get(car, 0) + 1
    return set([c for c, _ in sorted(counts.items(), key=lambda x: -x[1])[:top_n]])


def compute_lead_score(lead_row: list,
                       cfg: dict[str, int],
                       cancelled_codes: set,
                       done_codes: set,
                       top_cars: set,
                       price_lookup: dict[str, float] | None = None) -> dict:
    """คำนวณ Lead Score ของ lead 1 ราย.

    Returns:
        {
          "score": int,
          "tier": "🔥hot" | "🌡warm" | "❄cold",
          "breakdown": [(name, points), ...]
        }
    """
    breakdown: list[tuple[str, int]] = []

    def _apply(name: str):
        if name in cfg and cfg[name] != 0:
            breakdown.append((name, cfg[name]))

    # 1) Freshness — จากวันที่รับ
    received = cell(lead_row, L.received_date)
    d = parse_date(received)
    if d:
        days_old = (bangkok_now().date() - d).days
        if days_old <= 3:
            _apply("Lead ใหม่ (≤3 วัน)")
        elif days_old <= 7:
            _apply("Lead ปานกลาง (4-7 วัน)")
        elif days_old <= 14:
            _apply("Lead เก่า (8-14 วัน)")
        else:
            _apply("Lead เย็น (>14 วัน)")

    # 2) Type
    lead_type = cell(lead_row, L.type).strip()
    if lead_type == "Hot RB":
        _apply("ประเภท: Hot RB")
    elif lead_type == "Hot RJ":
        _apply("ประเภท: Hot RJ")
    elif lead_type == "RJ":
        _apply("ประเภท: RJ")
    else:
        _apply("ประเภท: Normal")

    # 3) Car popularity + price
    car = cell(lead_row, L.car_formula).strip()
    if car and car in top_cars:
        _apply("รุ่นรถยอดนิยม (top 20)")
    if price_lookup and car in price_lookup:
        p = price_lookup[car]
        if p >= 500_000:
            _apply("ราคารถสูง (≥500,000)")
        elif p >= 200_000:
            _apply("ราคารถปานกลาง (200-500k)")

    # 4) History — code เคยอยู่ใน sales_reports หรือไม่
    code = cell(lead_row, L.lead_code).strip()
    if code:
        if code in done_codes:
            _apply("เคยจอง+ปล่อยสำเร็จ")
        elif code in cancelled_codes:
            _apply("เคยจองแล้วยกเลิก")

    # 5) Channel
    channel = cell(lead_row, L.channel).lower()
    if "facebook" in channel or "fb" in channel:
        _apply("มาจาก Facebook Ads")
    elif "tiktok" in channel or "ไลฟ์" in channel or "live" in channel:
        _apply("มาจาก TikTok / ไลฟ์สด")
    elif "walk" in channel or "โทร" in channel or "inbox" in channel:
        _apply("มาจาก Walk-in / โทรมา")

    # 6) Engagement — based on call_proof + admin_status + update_count
    update_count = int(cell_num(lead_row, L.update_count))
    admin_st = cell(lead_row, L.admin_status).lower()
    sales_st = cell(lead_row, L.sales_status).lower()
    call_proof = cell(lead_row, L.call_proof)
    combined_st = f"{admin_st} {sales_st}"

    # ลูกค้าตอบ — มี keyword positive
    if any(k in combined_st for k in ("ตอบกลับ", "นัด", "สนใจ", "รอลูกค้า")) and call_proof == "ส่งแล้ว":
        _apply("ลูกค้าตอบไลน์/โทรกลับ")
    elif "inbox" in channel and update_count >= 1:
        _apply("ลูกค้าทักก่อน (inbox)")

    # โทรไม่รับเกิน 3 ครั้ง
    if update_count >= 3 and ("ไม่รับ" in combined_st or "ผิดนัด" in combined_st):
        _apply("โทรไม่รับเกิน 3 ครั้ง")

    # ── สรุป ──
    total = sum(pts for _, pts in breakdown)
    if total >= 80:
        tier = "🔥hot"
    elif total >= 50:
        tier = "🌡warm"
    else:
        tier = "❄cold"

    return {"score": total, "tier": tier, "breakdown": breakdown}


def prepare_lead_score_context(raw_leads: list, sales_reports: list) -> dict:
    """โหลด config + สร้าง lookup maps สำหรับการคำนวณ Lead Score แบบ batch.
    เรียก 1 ครั้งต่อ request → ใช้ซ้ำได้กับหลาย rows.
    """
    cfg = load_lead_score_config()
    cancelled, done = _build_lead_history_maps(sales_reports)
    top_cars = _build_top_cars_set(raw_leads, top_n=20)
    return {
        "cfg": cfg,
        "cancelled": cancelled,
        "done": done,
        "top_cars": top_cars,
    }


def attach_lead_scores(follow_cases: list[dict],
                       my_year_leads: list,
                       sales_reports: list) -> list[dict]:
    """เติม field 'leadScore' + 'leadTier' + 'scoreBreakdown' ในแต่ละ follow_case.

    Args:
        follow_cases: list ของ dict ที่มี field 'code'
        my_year_leads: raw lead rows ของเซลล์ (ใช้หา row ตาม code)
        sales_reports: raw sales rows (ใช้สร้าง history maps)

    Returns:
        follow_cases เดิม + field ใหม่
    """
    cfg = load_lead_score_config()
    cancelled, done = _build_lead_history_maps(sales_reports)
    top_cars = _build_top_cars_set(my_year_leads, top_n=20)

    # Index leads by code สำหรับ lookup เร็ว
    leads_by_code: dict[str, list] = {}
    for r in my_year_leads:
        code = cell(r, L.lead_code).strip()
        if code:
            leads_by_code[code] = r

    for case in follow_cases:
        code = case.get("code", "").strip()
        row = leads_by_code.get(code)
        if not row:
            case["leadScore"] = 0
            case["leadTier"] = "❄cold"
            case["scoreBreakdown"] = []
            continue
        result = compute_lead_score(row, cfg, cancelled, done, top_cars)
        case["leadScore"] = result["score"]
        case["leadTier"] = result["tier"]
        case["scoreBreakdown"] = result["breakdown"]

    return follow_cases
