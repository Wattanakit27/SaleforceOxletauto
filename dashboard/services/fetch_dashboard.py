"""
Main dashboard data fetching & transformation — ported from lib/fetch-dashboard.ts
"""
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, date
from zoneinfo import ZoneInfo

from django.conf import settings

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

# ── คำที่ "ไม่ใช่ชื่อเซลล์" — กันคำสถานะหลุดเข้ามาเป็น orphan seller ในตารางรายเซลล์ ──
# (บางแถวกรอกคำสถานะลงคอลัมน์ชื่อเซลล์ → ระบบนึกว่าเป็นเซลล์เก่า) เช็คแบบ exact หลัง normalize
NON_SELLER_NAMES = {
    "(ว่าง)", "จอง", "ส่งมอบ", "คืนเคส", "คืน", "จ่ายใหม่", "ยกเลิก", "ไม่สนใจ",
    "รอปล่อย", "รอผล", "รอเซ็นต์", "รอเซ็น", "รีเจ็ก", "ปล่อย", "ติดตาม", "จบ",
    "dead", "-", "",
}

# ── คอลัม Z "สถานะลูกค้า" (layout ใหม่ มิ.ย.69+) — ใช้คัดลำดับว่าตามเคสไหนก่อน ──
# ลำดับความสำคัญ (สูง = ตามก่อน) ตามที่ผู้ใช้กำหนด:
#   active chase (priority ≥3): สนใจมาก > ลังเล > ไม่รับสาย > รอเงิน > รอเช็คเครดิต > ดาวน์ไม่พอ
#   booked/done (priority 1-2): จอง, ส่งมอบ — ไม่ใช่เคสเสีย แต่ไม่ต้อง remind ให้โทร
CUSTOMER_STATUS_PRIORITY = {
    "สนใจมาก": 8,
    "ลังเล": 7,
    "ไม่รับสาย": 6,
    "ลูกค้าไม่ตอบ": 6,   # มิ.ย.69 เพิ่ม — ยังตามต่อ (เหมือนไม่รับสาย)
    "รอเงิน": 5,
    "รอเช็คเครดิต": 4,
    "ดาวน์ไม่พอ": 3,
    "เงินสดเงินไม่พอ": 3,  # มิ.ย.69 เพิ่ม — ยังตามต่อ (เหมือนดาวน์ไม่พอ)
    "จอง": 2,
    "ส่งมอบ": 1,
    "ได้รถแล้ว": 1,       # มิ.ย.69 เพิ่ม — เคสจบ (ได้รถ) ไม่ remind เหมือนส่งมอบ
}
# Z ที่ "เคสเสีย" (ในวงเล็บ) — ไม่ต้องตาม + ไม่ remind (คืนเคส = เพิ่มใหม่)
CUSTOMER_STATUS_DEAD = [
    "ยังไม่ออก", "แบล็คลิส", "แบล็คลิสต์", "เครดิตไม่ผ่าน", "ไม่สนใจ", "คืนเคส",
]


def customer_status_priority(z: str) -> int:
    """คอลัม Z → คะแนนลำดับการตาม (8=สนใจมากสุด ... 1=ส่งมอบ, 0=เคสเสีย/ไม่รู้จัก)."""
    if not z:
        return 0
    for k, v in CUSTOMER_STATUS_PRIORITY.items():
        if k in z:
            return v
    return 0


def is_nofollow_z(z: str) -> bool:
    """คอลัม Z เป็น 'เคสเสีย' (ในวงเล็บ) ไหม — ไม่ต้องตาม."""
    return bool(z) and any(k in z for k in CUSTOMER_STATUS_DEAD)


def effective_status(r) -> str:
    """สถานะที่ใช้ตัดสิน follow/skip ของ lead 1 แถว —
    ใช้คอลัม Z (สถานะลูกค้า) ก่อนถ้ามีค่า, ไม่งั้น fallback admin_status (layout เก่า/ยังไม่กรอก Z)."""
    z = cell(r, L.customer_status).strip()
    return z if z else cell(r, L.admin_status)


def should_follow(r) -> bool:
    """lead นี้ 'ต้องตามต่อ' ไหม (row-level, Z-aware).
    - มีคอลัม Z (layout ใหม่): ตามต่อถ้าไม่ใช่ '(ไม่ต้องตาม)'
    - ไม่มี Z (layout เก่า/ยังไม่กรอก): ใช้ is_follow(admin_status) เดิม → ผลเท่าเดิมเป๊ะ"""
    z = cell(r, L.customer_status).strip()
    if z:
        if is_nofollow_z(z):
            return False                          # เคสเสีย (ในวงเล็บ)
        if "จอง" in z or "ส่งมอบ" in z or "ได้รถแล้ว" in z:
            return False                          # booked/done (รวม "ได้รถแล้ว") — ไม่ remind ให้โทร
        return True                               # active chase (หรือ status ที่ไม่รู้จัก)
    return is_follow(cell(r, L.admin_status))


def is_lead_vacant(r) -> bool:
    """lead ยัง 'ว่าง' (ยังไม่ตีสถานะ) ไหม — มี Z = ไม่ว่าง, ไม่งั้นใช้ is_vacant(admin) เดิม."""
    if cell(r, L.customer_status).strip():
        return False
    return is_vacant(cell(r, L.admin_status))


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
        # LIVE = ไม่นับเป็น lead ที่แจกจ่ายได้ — ใช้ "LIVE" in (contains) ให้ตรงกับ leadLive
        # (เดิม startswith → "FB LIVE" หลุดเป็น distributable ทั้งที่นับเป็น leadLive)
        if "LIVE" not in _ch and _ty not in ("RJ", "HOTRJ", "HOTRB"):
            dist += 1
    return {"updateSum": upd_sum, "proofCount": proof,
            "returnCount": ret, "cancelCount": cancel, "leadDist": dist}


# ── Date helpers ──
def bangkok_now() -> datetime:
    return datetime.now(BKK)


def parse_date(date_str: str) -> date | None:
    if not date_str or date_str == "-":
        return None
    s = date_str.strip()
    # Excel serial date — จำกัดช่วงสมเหตุสมผล (~2009-2036) กันเลขมั่ว
    # (เช่น "25235" = ปี 1969) ถูกตีเป็นวันที่ → ถ้านอกช่วงคืน None ให้ caller fallback ไปวันจอง
    if re.match(r"^\d{4,5}$", s):
        serial = int(s)
        if 40000 < serial < 50000:
            from datetime import timedelta
            return date(1899, 12, 30) + timedelta(days=serial)
        return None
    # d/m/yy format — รองรับทั้ง ค.ศ. ("26") และ พ.ศ. ("69") ปนกันในชีต
    parts = s.split("/")
    if len(parts) == 3:
        try:
            day = int(parts[0])
            month = int(parts[1])
            year = int(parts[2])
            if year < 100:
                # 2 หลัก: >50 = พ.ศ. (69→2569→2026), ≤50 = ค.ศ. (26→2026)
                year += 2500 if year > 50 else 2000
            if year > 2500:
                year -= 543
            return date(year, month, day)
        except (ValueError, TypeError):
            pass
    # Fallback
    try:
        from dateutil.parser import parse as dateutil_parse
        return dateutil_parse(s).date()
    except Exception:
        pass
    return None


_EMBED_DATE_RE = re.compile(r"\d{1,2}/\d{1,2}/\d{2,4}")


def extract_release_date(r) -> str:
    """วันที่ปล่อยรถ — convention การกรอก: เดือน พ.ค.+ อยู่ X(23), เดือนก่อนหน้าอยู่ V(21)
    (เผื่อ scan W/X/U ถ้าตัวหลักว่าง). ค่ามักปนข้อความ ('รับรถ 20/3/69') → ดึงวันที่ออกมา
    กรองปี 2020-2035 กัน data เสีย (เช่น 1/2/1969). คืน '' ถ้าไม่เจอ → caller fallback วันจอง
    """
    def _ok(d):
        return d is not None and 2020 <= d.year <= 2035

    def _clean(val):
        # ทั้งช่องเป็นวันที่ล้วน (หรือ excel serial) — เชื่อถือได้สุด
        if val and _ok(parse_date(val)):
            return val
        return None

    def _embed(val):
        # วันที่ที่ฝังอยู่ในข้อความโน้ต (เช่น 'รับรถ 20/3/69') — ใช้ต่อเมื่อไม่มีวันที่สะอาดเลย
        if not val:
            return None
        m = _EMBED_DATE_RE.search(val)
        if m and _ok(parse_date(m.group())):
            return m.group()
        return None

    bd = parse_date(cell(r, S.date))          # วันจอง (เชื่อถือได้) ใช้ดูว่าเป็นเดือน พ.ค.+ ไหม
    is_may = bool(bd and bd.month >= 5)
    # X=23, W=22, V=21, U=20 ; พ.ค.+ release อยู่ X(23) · เดือนก่อน release อยู่ V(21) (ตรงกับ _release_col + CLAUDE.md)
    # ★ เดือนก่อนต้องอ่าน V(21) "ก่อน" W(22) ไม่งั้นค่าที่ inline edit เขียนลง V ถูก W (โน้ต) บังตอนอ่าน → "บันทึกแล้วไม่ติด"
    #   (V ว่าง → fall through ไป W/X/U เหมือนเดิม ไม่ regression)
    order = (23, 22, 21, 20) if is_may else (21, 22, 23, 20)
    # รอบ 1: หาวันที่ "สะอาด" (ทั้งช่องเป็นวันที่) ก่อน — กันไปคว้าวันที่ฝังในโน้ต
    # (เช่น W = 'นัดเซ็น 29/04/69' ทั้งที่ X มีวันปล่อยจริง '19/5/2026' สะอาดอยู่)
    for col in order:
        got = _clean(cell(r, col))
        if got:
            return got
    # รอบ 2: ไม่มีวันที่สะอาดเลย → fallback ดึงวันที่ที่ฝังในข้อความโน้ต
    for col in order:
        got = _embed(cell(r, col))
        if got:
            return got
    return ""


def release_date_primary(r) -> str:
    """วันปล่อยจาก 'คอลัมน์หลัก' เท่านั้น (X(23) สำหรับ พ.ค.+, W(22) สำหรับเดือนก่อนหน้า) — ไม่ fallback คอลัมน์อื่น.
    ใช้ในกระดิ่งแจ้งเตือน: ถ้าว่าง = admin ยังไม่กรอกวันปล่อยในช่องที่ถูก (แม้ extract_release_date จะไปเจอ
    วันที่ใน V/U/โน้ตมาแทน — เคสปล่อยแต่ "ช่องวันปล่อยจริงว่าง" เช่น กรอก V ไว้แต่ X ว่าง)."""
    bd = parse_date(cell(r, S.date))
    if bd and bd.month >= 5:
        # พ.ค.+ : วันปล่อยจริงอยู่ X(23) — ถือว่า "กรอกแล้ว" ถ้ามี pattern วันที่ใน X (มี/ไม่มีปีก็ได้ เช่น 24/05)
        # ว่าง/ข้อความล้วน ('ติดตาม','รอรับ') = ยังไม่กรอกวันปล่อย → flag (แม้ extract เจอวันที่ใน V)
        val = (cell(r, 23) or "").strip()
        return val if re.search(r"\d{1,2}/\d{1,2}", val) else ""
    # เดือนก่อน พ.ค. : layout เก่า (วันปล่อยอยู่ V) — ใช้ extract เดิม (ไม่ strict กัน false positive)
    return extract_release_date(r)


def _release_col(r) -> int:
    """คอลัมน์ 'วันปล่อยจริง' (0-based) สำหรับ inline edit เขียนกลับ: พ.ค.+ = 23(X) · เดือนก่อน = 21(V)."""
    d = parse_date(cell(r, S.date))
    return 23 if (d and d.month >= 5) else 21


def result_date_for(r) -> str:
    """วันผล (อนุมัติเครดิต) — layout ย้ายตามเดือนเหมือนวันปล่อย: พ.ค.+ = U(20) · เดือนก่อน = T(19).
    ★ เดิม fix ที่ T(19) เสมอ → เดือนปัจจุบัน (พ.ค.+) ได้ค่าว่างทุกเคส เพราะผลย้ายไป U(20)
      → velocity ช่วง 2-3 (เซ็น→ผล, ผล→ปล่อย) = 0 → ตัน 3.3. อ่านคอลัมน์ตามเดือนให้ตรง layout จริง."""
    d = parse_date(cell(r, S.date))
    return cell(r, 20) if (d and d.month >= 5) else cell(r, 19)


def result_col_for(r) -> int:
    """คอลัมน์ 'วันผล' (0-based) สำหรับ inline edit เขียนกลับ: พ.ค.+ = 20(U) · เดือนก่อน = 19(T)
    (ต้องตรงกับ result_date_for ที่อ่าน ไม่งั้นเขียนแล้วถูกอ่านคนละช่อง = 'บันทึกแล้วไม่ติด')."""
    d = parse_date(cell(r, S.date))
    return 20 if (d and d.month >= 5) else 19


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


def parse_month_day(date_str: str):
    """คืน (month, day) จากสตริงวันที่ — รองรับทั้งวันเต็ม (d/m/yy, Excel serial) และ **แบบไม่มีปี** (d/m เช่น "10/06").
    เหตุผล: daily bucket (กราฟ + KPI "ปิดได้") เคยใช้ parse_date() ตรงๆ ซึ่งบังคับต้องมีปี (3 ส่วน) →
    วันปล่อยที่แอดมินกรอกแบบ "10/06" (ไม่ใส่ปี) จะ parse ไม่ได้ → เคสตกไปนับตามวันจอง (คนละเดือน) หรือถูกทิ้ง
    ทำให้ KPI ปิดได้ (รายวัน) ไม่ตรงกับ monthlySummary/ตารางละเอียด (ที่ใช้ get_month ซึ่งดึงเดือนได้แม้ไม่มีปี).
    helper นี้ทำให้ทั้งสองทางนับเดือนเดียวกัน. ปีไม่จำเป็น — bucket อยู่ในปีของ dashboard อยู่แล้ว."""
    d = parse_date(date_str)
    if d and 1 <= d.day <= 31:
        return (d.month, d.day)
    s = (date_str or "").strip()
    if s and s != "-":
        parts = s.split("/")
        if len(parts) == 2:   # "d/m" ไม่มีปี — get_month ดึงเดือนได้ ก็ต้อง bucket เดือนเดียวกัน
            try:
                day, mo = int(parts[0]), int(parts[1])
                if 1 <= day <= 31 and 1 <= mo <= 12:
                    return (mo, day)
            except ValueError:
                pass
    return None


# ── Main fetch function ──
_dash_cache: dict = {"ts": 0.0, "data": None}
_DASH_TTL = 30          # in-memory cache (warm lambda) — กันคำนวณซ้ำทุก request
_PRECOMPUTE_TTL = 300   # ผล pre-compute ใน Supabase ถือว่า "สด" ภายใน 5 นาที
_LOCAL_TTL = 180        # โหมดไม่มี Supabase (มิ.ย.69) — อ่าน Google + cache memory 3 นาที (คำนวณ ~8.5s ตอนหมดอายุ)


def precompute_dashboard() -> dict:
    """คำนวณ dashboard 1 ครั้ง → เก็บผลลง Supabase (เรียกจาก cron/sync).
    ทำให้คนเข้าเว็บอ่าน "ผลสำเร็จรูป" ไม่ต้องคำนวณ 15k lead สดทุกโหลด."""
    import time
    data = _compute_dashboard_data()
    try:
        from .cache_store import save_dashboard_cache, available
        if available():
            save_dashboard_cache(data)
    except Exception:
        pass
    _dash_cache["ts"] = time.time()
    _dash_cache["data"] = data
    return data


def fetch_dashboard_data() -> dict:
    """อ่านผล dashboard — เร็วสุด→ช้าสุด:
    1) in-memory cache (warm process) — มี store 30 วิ · ไม่มี store 180 วิ
    2) ที่เก็บผล (Supabase หรือ Postgres ในเครื่อง): precompute fresh/stale ก็ใช้ — กันลูกโซ่ recompute
    3) ไม่มี store (หรือ cold + store ล่ม) → คำนวณสดจาก Google (~8.5 วิ) แล้ว cache ในหน่วยความจำ

    ⚠️ โหมด VPS (มิ.ย.69): store = PostgreSQL ในเครื่อง (cache_store → local_store). cron อุ่น cache ทุกนาที
    → ทุก worker อ่าน store ที่อุ่นแล้ว (เร็ว ~50ms ไม่ recompute สด). dashboard อุ่นตลอดเหมือนยุค Supabase
    แต่ local เร็วกว่า (ไม่วิ่งเน็ต ไม่เจอ NANO timeout). เปิด Supabase กลับได้ด้วย USE_SUPABASE=True (facade เลือกให้)

    ⚠️ บทเรียน NANO ล่ม: ห้ามให้ user request trigger recompute ถ้ามีของเก่าให้เสิร์ฟ (กันลูกโซ่ล่ม) —
    recompute เป็นงานของ cron เท่านั้น. user-load อ่าน store (cron อุ่นไว้) · cold start เท่านั้นที่คำนวณสด
    """
    import time
    from datetime import datetime as _dt, timezone as _tz
    from .cache_store import available, get_dashboard_cache
    c = _dash_cache
    now = time.time()
    store = available()   # Supabase หรือ Postgres ในเครื่อง (VPS) — cron อุ่นไว้ให้
    ttl = _DASH_TTL if store else _LOCAL_TTL
    # 1) in-memory cache สด → ใช้เลย
    if c["data"] is not None and (now - c["ts"]) < ttl:
        return c["data"]

    # 2) มีที่เก็บผล → อ่าน precompute (fresh/stale ก็ใช้ · ไม่ปล่อยให้ user-load ไป recompute รุม DB)
    if store:
        try:
            cached = get_dashboard_cache()
            if cached and cached.get("data"):
                ts = (cached.get("updated_at") or "").replace("Z", "+00:00")
                age = (_dt.now(_tz.utc) - _dt.fromisoformat(ts)).total_seconds() if ts else 1e9
                c["data"] = cached["data"]
                # fresh → cache เต็ม 30 วิ · stale → cache สั้น (เช็ค store ใหม่เร็วขึ้น เผื่อ cron อัปแล้ว)
                c["ts"] = now if age < _PRECOMPUTE_TTL else (now - _DASH_TTL + 5)
                return cached["data"]
        except Exception:
            pass
        # อ่าน store ไม่ได้ (timeout/ล่ม) → ใช้ของเก่าใน memory ถ้ามี (กันลูกโซ่ recompute ที่ไปรุม DB ซ้ำ)
        if c["data"] is not None:
            c["ts"] = now - _DASH_TTL + 5   # เสิร์ฟของเก่าต่อ แต่ลองเช็ค store ใหม่อีกใน ~5 วิ
            return c["data"]

    # 3) ไม่มี store (หรือ cold + store ล่ม) → คำนวณสดจาก Google แล้ว cache ในหน่วยความจำ
    return precompute_dashboard()


_ban_cache: dict = {"ts": 0.0, "year": None, "data": None}
_BAN_TTL = 600  # 10 นาที — แบนเปลี่ยนน้อยมาก ไม่ต้องอ่าน Google ทุก cold load (เดิม +1.5s/load)


def fetch_ban_counts_by_month(year: int) -> dict:
    """อ่าน tab 'รายงานแบน' → {month: {seller_normalized: จำนวนครั้งโดนแบน}} ของปีนั้น.
    1 แถว = 1 ครั้งที่โดนแบน (นับตาม banDate). cache 10 นาที. error/ไม่มี sheet → {}."""
    import time
    c = _ban_cache
    if c["data"] is not None and c["year"] == year and (time.time() - c["ts"]) < _BAN_TTL:
        return c["data"]

    from .google_sheets import fetch_sheet, BAN_COL
    out: dict[int, dict] = {}
    try:
        rows = fetch_sheet("ban_report")
    except Exception:
        return out
    for r in rows:
        d = parse_date(cell(r, BAN_COL.ban_date))
        if not d or d.year != year:
            continue
        seller = normalize_seller(cell(r, BAN_COL.seller))
        if not seller:
            continue
        out.setdefault(d.month, {})
        out[d.month][seller] = out[d.month].get(seller, 0) + 1
    c["ts"] = time.time(); c["year"] = year; c["data"] = out
    return out


def _mask_phone(p) -> str:
    """ปิดบังเบอร์โทร (PDPA) — โชว์ 3 ตัวหน้า + 2 ตัวท้าย กลางเป็น x · ใช้ในข้อมูลรวม (admin/exec).
    หน้าเซลล์ใช้ fetch_seller_stats (คนละ path) เบอร์เต็มไว้โทรลูกค้าตัวเอง. idempotent (mask ซ้ำได้)."""
    s = str(p or "").strip()
    d = re.sub(r"\D", "", s)
    if len(d) < 6:
        return s  # ไม่ใช่เบอร์ (เช่น "-"/ว่าง/ที่ mask แล้ว) → คงเดิม
    return d[:3] + "-xxx-" + d[-2:]


def _dedup_booking_cases(cases: list[dict]) -> list[dict]:
    """เคสจองที่ค้าง (ไม่จบใน 1 เดือน) ถูกก๊อปไปแท็บเดือนถัดไปเรื่อยๆ โดยวันจองยังเป็นเดือนเดิม
    → เคสเดียวโผล่หลายแท็บ ทำให้ตัวนับสถานะ (จอง/รอเซ็น/รอผล/รอปล่อย/รีเจ็ก) ซ้ำ 2-2.6 เท่า
    (ปล่อย แทบไม่กระทบ เพราะแท็บเก่าเคสยังไม่ปล่อย)

    dedup: เก็บสำเนาจาก 'แท็บเดือนล่าสุด' ของแต่ละเคส = สถานะปัจจุบันจริง + วันปล่อยถูก
    (สำเนาเก่าในแท็บก่อนหน้า = สถานะที่ตายแล้ว ไม่ใช่ปัจจุบัน) · วันจองยังเป็นเดือนเดิม (ก๊อปมาพร้อมกัน)
    → จอง ยังนับเดือนถูก · ปล่อย นับตามวันปล่อย · inline edit เขียนกลับแท็บ active (ล่าสุด)

    คีย์ระบุเคสเดียวกัน: leadCode (ถ้ามีเลข) · เคสไม่มีรหัส "-" ใช้ ชื่อลูกค้า+รถ+วันจอง แทน
    """
    def _tab_order(tab: str) -> int:
        t = (tab or "").strip()
        for i, m in enumerate(MONTHS_FULL_TH):
            if t.startswith(m):
                return i + 1
        return 0

    def _key(b: dict):
        c = (b.get("leadCode") or "").strip().lstrip(":").strip().upper()
        if any(ch.isdigit() for ch in c):
            return ("code", c)
        return ("cust", str(b.get("customer", "")).strip()[:14],
                str(b.get("car", "")).strip()[:14], str(b.get("date", "")).strip())

    # หาสำเนา 'แท็บล่าสุด' ต่อ key (ถ้าเสมอ เอาแถวหลังสุดในลิสต์)
    best: dict = {}
    for b in cases:
        k = _key(b)
        prev = best.get(k)
        if prev is None or _tab_order(b.get("sheetTab", "")) >= _tab_order(prev.get("sheetTab", "")):
            best[k] = b
    # คงลำดับตามที่เจอ key ครั้งแรก (ไม่สลับ output)
    seen, out = set(), []
    for b in cases:
        k = _key(b)
        if k in seen:
            continue
        seen.add(k)
        out.append(best[k])
    return out


def _compute_dashboard_data() -> dict:
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
    # sellerTokens: normalize(ชื่อเล่น) → LINE user_id — ใช้ iframe หน้าเซลล์จริง /s/<token>/
    user_id_map = {}
    seller_tokens = {}
    employee_list = []
    for row in employees:
        uid = cell(row, EM.user_id)
        nickname = cell(row, EM.nickname)
        if uid and nickname:
            user_id_map[uid] = nickname
            seller_tokens[normalize_seller(nickname)] = uid
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

    # "ADMIN" = ศูนย์รวมเทเลเซลล์ (เคสที่ลงชื่อ "ADMIN" ในชีต = ทีมโทรรวมกัน)
    # ตั้ง token ของ "ADMIN" = LINE user_id ของเทเลเซลล์คนแรก → dropdown หน้าเซลล์เปิด /s/ ได้
    # (seller_from_token map ทุกไอดีเทเลเซลล์ → "ADMIN" อยู่แล้ว)
    try:
        from .constants import load_tele_user_ids, TELE_USER_IDS
        load_tele_user_ids()
        if TELE_USER_IDS:
            seller_tokens["ADMIN"] = sorted(TELE_USER_IDS)[0]
    except Exception:
        pass

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
        chosen_release = extract_release_date(r)
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
            "resultDate": result_date_for(r),
            "docsDate": cell(r, S.doc_complete_date),
            "releaseDate": chosen_release,
            "releaseDatePrimary": release_date_primary(r),
            "sheetTab": cell(r, 28), "sheetRow": cell(r, 29), "resultCol": result_col_for(r), "releaseCol": _release_col(r),   # ตำแหน่งในชีต (inline edit วันผล/ปล่อย — คอลัมน์ตามเดือน)
            "finance": cell(r, S.finance_main),
            "grade": cell(r, S.grade),
            "note": cell(r, S.note),
        })

    # เคสค้างข้ามเดือนถูกก๊อปหลายแท็บ → dedup เก็บสำเนาแท็บล่าสุด (สถานะปัจจุบัน)
    # booking_cases (dedup) = ใช้กับ summary รวม + ส่งให้ frontend (กัน date-range นับซ้ำ)
    # booking_cases_raw (ไม่ dedup) = ใช้นับ "รายเดือนตามแท็บ" ให้ตรงสูตรชีต (เคสข้ามเดือนนับในทุกแท็บที่มันอยู่)
    booking_cases_raw = booking_cases
    booking_cases = _dedup_booking_cases(booking_cases)

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
    total_follow = len([r for r in year_leads if should_follow(r)])
    total_vacant = len([r for r in year_leads if is_lead_vacant(r)])
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
        follow = len([r for r in sl if should_follow(r)])
        vacant = len([r for r in sl if is_lead_vacant(r)])
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
        if s in known_names or s in NON_SELLER_NAMES:
            continue
        g = orphan_groups.setdefault(s, {"leads": [], "bookings": [], "dones": [], "jongs": []})
        g["leads"].append(r)
    for b in booking_cases:
        s = b["seller"] or "(ว่าง)"
        if s in known_names or s in NON_SELLER_NAMES:
            continue
        g = orphan_groups.setdefault(s, {"leads": [], "bookings": [], "dones": [], "jongs": []})
        g["bookings"].append(b)
        if b["status"] == "ปล่อย":
            g["dones"].append(b)
    for j in year_jongs:
        s = j["seller"] or "(ว่าง)"
        if s in known_names or s in NON_SELLER_NAMES:
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
            "follow": len([r for r in g["leads"] if should_follow(r)]),
            "vacant": len([r for r in g["leads"] if is_lead_vacant(r)]),
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
        admin_follow = len([r for r in admin_leads if should_follow(r)])
        admin_vacant = len([r for r in admin_leads if is_lead_vacant(r)])
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
        if not should_follow(r):
            continue
        seller = normalize_seller(cell(r, L.sales_rep)) or "-"
        if seller == "-":
            continue
        note_raw = cell(r, L.fill_sheet_note) or "-"
        note = re.sub(r"^\d{4,5}\s*", "", note_raw) or "-"
        # ⚡ เก็บเฉพาะ field ที่ frontend (index.html) + compute_diligence_scores ใช้จริง (8 ตัว)
        # — ตัด phone/channel/adminStatus/customerStatus/followPriority/callProof/profile/timeIn ออก
        #   (ไม่มีใครอ่านจาก followCases · seller.html ใช้ D.leads แทน) → ลดก้อน precompute ~0.7 MB
        #   เขียน Supabase NANO ได้ไม่ timeout + อ่านเร็วขึ้น. **อย่าเพิ่ม field ที่ไม่ได้ใช้กลับมา**
        follow_cases.append({
            "code": cell(r, L.lead_code) or "-",
            "seller": seller,
            "leadType": cell(r, L.type),
            "car": cell(r, L.car_inquiry) or cell(r, L.car_formula) or "-",
            "dateIn": cell(r, L.received_date) or "-",
            "note": note[:120],   # frontend โชว์แค่ 80 ตัวอักษร → เก็บ 120 พอ (ลดขนาด)
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
        "totalFollow": len([r for r in today_leads if should_follow(r)]),
        "totalVacant": len([r for r in today_leads if is_lead_vacant(r)]),
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
        "clips": year_clips,   # [{name, date}] — ให้ frontend กรองตามช่วงวันที่ได้ (เกณฑ์ อาทิตย์ละ 2)
    }

    # Monthly Summary
    def _tab_month(b):
        t = str(b.get("sheetTab", "") or "").strip()
        for i, mn in enumerate(MONTHS_FULL_TH):
            if t.startswith(mn):
                return i + 1
        return 0

    def get_done_month(b):
        # ★ (ก.ค.69) นับ "ตามแท็บ" ที่เคสอยู่ = เดือนที่ทีมบันทึกในชีต (ตรงสูตรสรุป)
        #   เดิมใช้ "วันปล่อย" → แท็บเดือนเก่าคอลัมน์วันปล่อยย้าย/ฟอร์แมตต่าง/ว่าง → parse ไม่ได้
        #   → เดือนต้นปีนับปล่อยขาดเยอะ (ม.ค. ได้ 18 แทน 44) · ตอนนี้ยึดแท็บเป็นหลัก
        tm = _tab_month(b)
        if tm:
            return tm
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
        m_follow = len([r for r in m_leads if should_follow(r)])
        m_vacant = len([r for r in m_leads if is_lead_vacant(r)])

        # ★ นับ "ตามแท็บ" จาก raw (ก่อน dedup) → เคสข้ามเดือนนับในทุกแท็บที่มันอยู่ (ตรงสูตรชีต)
        m_bookings = [b for b in booking_cases_raw if _tab_month(b) == m]
        m_done = [b for b in booking_cases_raw if b["status"] == "ปล่อย" and _tab_month(b) == m]

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
                "leadLive": len([r for r in sl2 if "LIVE" in cell(r, L.channel).upper()]),   # lead จากไลฟ์ (channel มี LIVE)
                "follow": len([r for r in sl2 if should_follow(r)]),
                "vacant": len([r for r in sl2 if is_lead_vacant(r)]),
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
                "leadLive": len([r for r in g["leads"] if "LIVE" in cell(r, L.channel).upper()]),
                "follow": len([r for r in g["leads"] if should_follow(r)]),
                "vacant": len([r for r in g["leads"] if is_lead_vacant(r)]),
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
            # ยอดเงินจอง (pipeline) ของ ADMIN รายเดือน — จาก booking_cases เดือนนั้น (จอง/รอเซ็น/รอผล/รอปล่อย)
            m_admin_pipeline = sum(
                b["price"] for b in m_bookings
                if b["seller"] == "ADMIN" and b["status"] in ("จอง", "รอเซ็นต์", "รอผล", "รอปล่อย")
            )
            m_sellers["ADMIN"] = {
                "lead": len(m_admin_leads),
                "leadNormal": len([r for r in m_admin_leads if cell(r, L.type) not in RJ_TYPES]),
                "leadRJ": len([r for r in m_admin_leads if cell(r, L.type) in RJ_TYPES]),
                "leadLive": len([r for r in m_admin_leads if "LIVE" in cell(r, L.channel).upper()]),
                "follow": len([r for r in m_admin_leads if should_follow(r)]),
                "vacant": len([r for r in m_admin_leads if is_lead_vacant(r)]),
                "done": len(m_admin_done),
                "booking": m_admin_booking,
                "dealValue": m_admin_dv,
                "pipelineValue": m_admin_pipeline,
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

        # per-seller pipeline (รอผล/รอปล่อย) นับ "ตามแท็บ" จาก m_bookings — รวมทุกเซลล์ (ADMIN/ลาออก/ใบตอง)
        #   → report table (frontend) ดึงอันนี้ไปโชว์แทนการนับเองด้วย leadDate → ตรงสูตรชีต (เหมือน จอง/ปล่อย)
        m_pipe_by_seller: dict[str, dict] = {}
        for b in m_bookings:
            nm = b["seller"]
            if not nm:
                continue
            e = m_pipe_by_seller.setdefault(nm, {"wr": 0, "wp": 0})
            if b["status"] == "รอผล":
                e["wr"] += 1
            elif b["status"] == "รอปล่อย":
                e["wp"] += 1

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
            "pipeBySeller": m_pipe_by_seller,
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
        if cell(r, L.type) in RJ_TYPES:   # ★ Lead-by-Car ไม่นับ RJ ทุกประเภท (RJ/Hot RJ/Hot RB)
            continue
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
        return parse_month_day(date_str)   # รองรับ "d/m" ไม่มีปี → daily ตรงกับ monthlySummary

    def _parse_done_day(b):
        # ★ (ก.ค.69) เดือน = เดือนของแท็บ (ตรงสูตรชีต · เหมือน get_done_month) · วัน = วันปล่อยถ้า parse ได้ ไม่งั้นวันจอง ไม่งั้น 1
        tm = _tab_month(b)
        rd = b.get("releaseDate", "")
        _d = _parse_day(rd) if (rd and rd != "-" and rd != "") else None
        if not _d:
            _d = _parse_day(b.get("date", ""))
        if tm:
            return (tm, _d[1] if _d else 1)
        return _d   # ไม่มีแท็บ → วิธีเดิม (วันปล่อย/วันจอง)

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

    for b in booking_cases_raw:   # raw (นับตามแท็บ ให้ตรงสูตรชีต · เคสข้ามเดือนนับทุกแท็บ)
        if b["status"] != "ปล่อย":
            continue
        md = _parse_done_day(b)
        if not md:
            continue
        mm, dd = md
        daily_by_month[mm]["dones"][dd] += 1
        daily_by_month[mm]["dealValue"][dd] += b["price"] or 0

    # Daily-by-month แยกตามเซลล์ — ใช้ตอน admin impersonate เซลล์คนใดคนหนึ่ง
    # รวม orphan/inactive sellers + ทุกเซลล์ที่มีเคสในชีต (ADMIN/เซลล์ลาออก/ใบตอง) → ตารางรายเซลล์ครบ ไม่ขาด
    _daily_names = (set(ALL_SELLERS)
                    | {s["name"] for s in sellers if s.get("inactive")}
                    | {b["seller"] for b in booking_cases_raw if b.get("seller")})
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
        for name in _daily_names
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

    for b in booking_cases_raw:   # raw (นับตามแท็บ ให้ตรงสูตรชีต)
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

    # ── โดนแบน (คะแนนเซลล์ส่วน "โดนแบน") — inject ต่อเซลล์ทั้งรายเดือน + รายปี ──
    ban_by_month = fetch_ban_counts_by_month(year_full)
    for s in sellers:
        s["bans"] = sum(ban_by_month.get(mm, {}).get(s["name"], 0) for mm in range(1, 13))
    for mm, msum in monthly_summary.items():
        mm_int = int(mm)
        for nm, sd in (msum.get("sellers") or {}).items():
            sd["bans"] = ban_by_month.get(mm_int, {}).get(nm, 0)

    # ── PDPA: ปิดบังเบอร์โทรในข้อมูลรวม (admin/exec เห็น masked) — หน้าเซลล์เบอร์เต็ม (fetch_seller_stats คนละ path) ──
    for _lst in (booking_cases, follow_cases, not_called_cases, jong_cases):
        for _row in _lst:
            if isinstance(_row, dict) and _row.get("phone"):
                _row["phone"] = _mask_phone(_row["phone"])

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
        "sellerTokens": seller_tokens,
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
                # สูตรใหม่ (100 คะแนน)
                "capUpd": 0, "leads": 0, "bans": 0, "conv": 0, "completion": 0,
                "velPct": 0, "velN": 0,
                "sDone": 0, "sJong": 0, "sConv": 0, "sVel": 0, "sFollow": 0, "sBan": 0,
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
        e["capUpd"] += min(upd, 4)   # ติดตาม: cap 4/เคส
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
        e["scoreCall"] += sc   # เก็บไว้ดู (ไม่รวมใน score ใหม่)

    # ── ส่วน 2: จอง/ปล่อย/lead/แบน จาก monthlySummary[m].sellers[name] ──
    m_sellers = (monthly.get(m) or monthly.get(str(m)) or {}).get("sellers", {})
    for name, sd in m_sellers.items():
        if name not in ALL_SELLERS and name != "ADMIN":
            continue  # skip orphan/inactive
        jongs = int(sd.get("booking", 0))
        dones = int(sd.get("done", 0))
        leads = int(sd.get("lead", 0))
        leads_normal = int(sd.get("leadNormal", leads))   # Lead ปกติ (ไม่รวม RJ) — ใช้คิด Conv
        bans = int(sd.get("bans", 0))
        if jongs > 0 or dones > 0 or leads > 0 or name in score_map:
            e = _ensure(name)
            e["jongs"] = jongs
            e["dones"] = dones
            e["leads"] = leads
            e["leadsNormal"] = leads_normal
            e["bans"] = bans
            e["scoreJong"] = jongs * SCORE_JONG
            e["scoreDone"] = dones * SCORE_DONE

    # avg per case
    for e in score_map.values():
        e["avg"] = round(e["totUpdates"] / e["cnt"], 2) if e["cnt"] else 0

    # เซลล์ที่ active แต่ไม่มี data ในเดือนนั้น → ใส่ entry ว่างไว้
    for name in ALL_SELLERS:
        if name not in score_map:
            _ensure(name)

    # ── ส่วน 3: ความเร็ว (จอง→เซ็น→ผล→ปล่อย) ของเคสปล่อยในเดือน ──
    # 3 ช่วง: จอง→เซ็น ≤3วัน · เซ็น→ผล ≤3วัน · ผล→ปล่อย ≤1วัน
    # แต่ละช่วง: ทันกำหนด=1.0, เกินค่อยลดเชิงเส้นถึง 0 ที่ 3× กำหนด, วันว่าง/parse ไม่ได้=0
    def _stage_score(d_from: str, d_to: str, deadline: int) -> float:
        a, b = parse_date(d_from or ""), parse_date(d_to or "")
        if not a or not b:
            return 0.0
        days = (b - a).days
        if days < 0:
            return 0.0   # วันกลับหัว (กรอกสลับ เช่น ผล<เซ็น) — ไม่ให้คะแนน ไม่งั้น days<=deadline เป็นจริงได้เต็ม
        if days <= deadline:
            return 1.0
        return max(0.0, 1 - (days - deadline) / (2 * deadline))

    def _case_velocity(bc: dict) -> float:
        s1 = _stage_score(bc.get("date"), bc.get("signDate"), 3)
        s2 = _stage_score(bc.get("signDate"), bc.get("resultDate"), 3)
        s3 = _stage_score(bc.get("resultDate"), bc.get("releaseDate"), 1)
        return (s1 + s2 + s3) / 3.0   # [0,1]

    vel_acc: dict[str, list] = {}
    for bc in booking_cases:
        if bc.get("status") != "ปล่อย":
            continue
        rd = bc.get("releaseDate") or ""
        dm = get_month(rd) if rd and rd != "-" else 0
        if dm == 0:
            dm = get_month(bc.get("date", ""))
        if dm != m:
            continue
        name = bc.get("seller")
        if name not in score_map:
            if name in ALL_SELLERS or name == "ADMIN":
                _ensure(name)
            else:
                continue
        vel_acc.setdefault(name, []).append(_case_velocity(bc))

    # ── สูตรคะแนนใหม่ (100): จบ30 จอง10 Conv20 ความเร็ว10 ติดตาม20 แบน10 ──
    for e in score_map.values():
        e["sDone"] = round(min(e["dones"] / 15, 1) * 30, 1)
        e["sJong"] = round(min(e["jongs"] / 30, 1) * 10, 1)
        conv = (e["dones"] / e["leadsNormal"] * 100) if e.get("leadsNormal") else 0   # Conv = ปล่อย ÷ Lead ปกติ (ไม่รวม RJ)
        e["conv"] = round(conv, 1)
        e["sConv"] = round(min(conv / 5, 1) * 20, 1)
        fr = vel_acc.get(e["name"], [])
        e["velN"] = len(fr)
        vel = (sum(fr) / len(fr)) if fr else 0          # ความเร็วเฉลี่ยจริง — ใช้โชว์ velPct (% ปิดทันกำหนด)
        # คะแนน sVel ถ่วงตามจำนวนเคส (Bayesian shrink k=1 เข้าหากลาง 0.5): ปล่อยน้อย=ถ่วงเข้ากลาง · ปล่อยเยอะ=เชื่อค่าจริง
        # กันคนปล่อย 1 เคสเร็วได้ 10 เท่าคนปล่อย 4 (ปล่อย 1=7.5 · 4=9.0 · 8=9.4) · sync กับ JS buildDilMap
        adj = ((sum(fr) + 0.5) / (len(fr) + 1)) if fr else 0
        e["velPct"] = round(vel * 100)
        e["sVel"] = round(adj * 10, 1)
        completion = (e["capUpd"] / (4 * e["cnt"])) if e["cnt"] else 0
        e["completion"] = round(completion * 100)
        e["sFollow"] = round(completion * 20, 1)
        e["sBan"] = max(0, 10 - e["bans"])
        e["score"] = round(e["sDone"] + e["sJong"] + e["sConv"] + e["sVel"] + e["sFollow"] + e["sBan"], 1)

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
        "เซลล์", "ทีม", "Score รวม (100)",
        "Lead", "ปล่อย", "จอง", "เคสติดตาม",
        "Conv %", "ติดตาม %", "สถานะ %", "โดนแบน",
        "จบ /30", "จอง /10", "Conv /20", "สถานะ /10", "ติดตาม /20", "แบน /10",
        "เดือน", "ปี", "อัพเดทเมื่อ",
    ]
    rows = [header]
    for e in scores:
        rows.append([
            e["name"], e["team"], e["score"],
            e["leads"], e["dones"], e["jongs"], e["cnt"],
            e["conv"], e["completion"], e["velPct"], e["bans"],
            e["sDone"], e["sJong"], e["sConv"], e["sVel"], e["sFollow"], e["sBan"],
            month_name, y, generated_at,
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


_seller_stats_cache: dict = {}   # {seller_name: (ts, data)}
_SELLER_STATS_TTL = 45           # วิ — cache หน้าเซลล์ (sync ~1นาทีอยู่แล้ว ข้อมูลไม่เก่ากว่านั้น)


def fetch_seller_stats(seller_name: str) -> dict:
    """cache ผลต่อเซลล์ ~45 วิ → โหลดซ้ำไม่ต้องคำนวณ 14k ลีดใหม่ (เดิม ~2.4s → ~0s)
    (ความสดของข้อมูลคุมโดย mirror sync ~1 นาทีอยู่แล้ว · 45 วิ จึงไม่ทำให้เก่าขึ้น)
    """
    import time
    _now = time.time()
    _hit = _seller_stats_cache.get(seller_name)
    if _hit and _now - _hit[0] < _SELLER_STATS_TTL:
        return _hit[1]
    _data = _fetch_seller_stats_impl(seller_name)
    _seller_stats_cache[seller_name] = (_now, _data)
    return _data


def _fetch_seller_stats_impl(seller_name: str) -> dict:
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
        chosen_release = extract_release_date(r)
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
            "resultDate": result_date_for(r),
            "docsDate": cell(r, S.doc_complete_date),
            "releaseDate": chosen_release,
            "releaseDatePrimary": release_date_primary(r),
            "sheetTab": cell(r, 28), "sheetRow": cell(r, 29), "resultCol": result_col_for(r), "releaseCol": _release_col(r),   # ตำแหน่งในชีต (inline edit วันผล/ปล่อย — คอลัมน์ตามเดือน)
            "finance": cell(r, S.finance_main),
            "grade": cell(r, S.grade),
            "note": cell(r, S.note),
        })

    # เคสค้างข้ามเดือนถูกก๊อปหลายแท็บ → dedup เก็บสำเนาแท็บล่าสุด (สถานะปัจจุบัน) · ส่งให้ frontend
    # my_booking_cases_raw (ไม่ dedup) = นับ done รายเดือน "ตามแท็บ" ให้ตรงสูตรชีต (เหมือนหน้ารวม)
    my_booking_cases_raw = my_booking_cases
    my_booking_cases = _dedup_booking_cases(my_booking_cases)

    # ── 3) Year jongs ของเซลล์ (จาก bookings sheet — source of truth สำหรับเซลล์ทั่วไป) ──
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
    # ★ ADMIN (เทเลเซลล์): bookings sheet ไม่มี ADMIN → derive "จอง" จาก leads (admin/sales_status มี "จอง" + ไม่ skip)
    #   mirror logic หน้ารวม (admin_booking fallback ~บรรทัด 763) → กราฟจอง/รายเดือนของ ADMIN ไม่แบน 0 (ตรงกับกล่อง KPI จอง)
    if seller_name == "ADMIN" and not my_year_jongs:
        for r in my_year_leads:
            a, s = cell(r, L.admin_status) or "", cell(r, L.sales_status) or ""
            if is_skipped(a) or is_skipped(s):
                continue
            if "จอง" in a or "จอง" in s:
                my_year_jongs.append({
                    "date": cell(r, L.received_date),
                    "code": cell(r, L.lead_code),
                })

    # ── 4) Follow cases ของเซลล์ ──
    my_follow_cases = []
    for r in my_year_leads:
        if not should_follow(r):
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
            "customerStatus": cell(r, L.customer_status),
            "followPriority": customer_status_priority(cell(r, L.customer_status)),
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
        "follow": len([r for r in my_today_leads if should_follow(r)]),
        "vacant": len([r for r in my_today_leads if is_lead_vacant(r)]),
    }

    # ── 6) Monthly summary (เฉพาะเซลล์, 12 เดือน) ──
    def _tab_month(b: dict) -> int:
        t = str(b.get("sheetTab", "") or "").strip()
        for i, mn in enumerate(MONTHS_FULL_TH):
            if t.startswith(mn):
                return i + 1
        return 0

    def get_done_month(b: dict) -> int:
        # ★ (ก.ค.69) นับ "ตามแท็บ" ที่เคสอยู่ (ตรงสูตรชีต · เหมือนหน้ารวม) — เดิมใช้วันปล่อย parse ไม่ได้แท็บเก่า
        tm = _tab_month(b)
        if tm:
            return tm
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
        m_done = [b for b in my_booking_cases_raw if b["status"] == "ปล่อย" and _tab_month(b) == m]
        n_done = len(m_done)
        dv = sum(b["price"] for b in m_done)
        my_monthly[m] = {
            "lead": len(m_leads),
            "leadNormal": len([r for r in m_leads if cell(r, L.type) not in RJ_TYPES]),
            "leadRJ": len([r for r in m_leads if cell(r, L.type) in RJ_TYPES]),
            "follow": len([r for r in m_leads if should_follow(r)]),
            "vacant": len([r for r in m_leads if is_lead_vacant(r)]),
            "done": n_done,
            "booking": len(m_jongs),
            "dealValue": dv,
        }

    # ── 7) Daily breakdown (เฉพาะเซลล์, 12 เดือน × 32 วัน) ──
    def _parse_day(date_str: str):
        return parse_month_day(date_str)   # รองรับ "d/m" ไม่มีปี → กราฟ/นับหน้าเซลล์ไม่ทิ้งเคสวันปล่อยไม่มีปี

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
    for b in my_booking_cases_raw:   # raw (นับ done ตามแท็บ ให้ตรงสูตรชีต · วัน = วันปล่อยถ้าได้ ไม่งั้น 1)
        if b["status"] != "ปล่อย":
            continue
        tm = _tab_month(b)
        _d = _parse_day(b.get("releaseDate") or b.get("date"))
        if tm:
            mm, dd = tm, (_d[1] if _d else 1)
        elif _d:
            mm, dd = _d
        else:
            continue
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
        "follow": len([r for r in my_year_leads if should_follow(r)]),
        "vacant": len([r for r in my_year_leads if is_lead_vacant(r)]),
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
    # ── ความใหม่ (Freshness) ──
    "Lead ใหม่ (≤3 วัน)": 20,
    "Lead ปานกลาง (4-7 วัน)": 10,
    "Lead เก่า (8-14 วัน)": 0,
    "Lead เย็น (>14 วัน)": -5,
    # ── ประเภท (Type) — ทเยอร์ตามค่าในชีต (match ตรงๆ "ประเภท: <ค่า>") · มิ.ย.69 ──
    "ประเภท: Very Hot": 60,
    "ประเภท: Hot": 50,
    "ประเภท: TLD / Hot": 50,   # type แยกจาก TLD (มีในชีตจริง x45)
    "ประเภท: MerHot": 38,
    "ประเภท: TLD": 35,
    "ประเภท: Moderate": 35,
    "ประเภท: BLD": 30,
    "ประเภท: Hot RB": 28,       # รีเจค
    "ประเภท: Hot RJ": 22,       # รีเจค
    "ประเภท: RJ": 15,           # รีเจค
    # ── ช่องทาง (Channel) ──
    "มาจาก Facebook Ads": 5,
    "มาจาก TikTok / ไลฟ์สด": 10,
    "มาจาก Walk-in / โทรมา": 15,
    # ── Engagement ──
    "ลูกค้าตอบไลน์/โทรกลับ": 25,
    "ลูกค้าทักก่อน (inbox)": 15,
    "โทรไม่รับเกิน 3 ครั้ง": -10,
    # (ตัด "รถ/ราคา" + "ประวัติ" ออกแล้ว — มิ.ย.69 ตามเกณฑ์ใหม่)
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


def compute_lead_score(lead_row: list, cfg: dict[str, int]) -> dict:
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

    # 2) Type — match ค่าในชีตตรงๆ ("ประเภท: <value>") → config
    #    รองรับทุก type (Very Hot/Hot/TLD / Hot/MerHot/TLD/Moderate/BLD/Hot RB/Hot RJ/RJ)
    #    เพิ่ม type ใหม่ได้โดยเพิ่มแถวในชีต "เกณฑ์คะแนน lead" — ไม่ต้องแก้โค้ด
    #    (เดิม else=Normal+50 ทำให้ Moderate/TLD/BLD = 65% ของลีด ได้ +50 เท่า Very Hot → ดูฮอทมั่ว)
    lead_type = cell(lead_row, L.type).strip()
    if lead_type:
        _apply("ประเภท: " + lead_type)

    # (ตัด "รถ/ราคา" + "ประวัติ" ออกแล้ว — มิ.ย.69 ตามเกณฑ์ใหม่)

    # 5) Channel
    channel = cell(lead_row, L.channel).lower()
    if "facebook" in channel or "fb" in channel.split():   # "fb" แบบ token (กัน substring เช่นคำที่บังเอิญมี fb)
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
    # threshold: hot≥55 (Very Hot/Hot/TLD-Hot แม้ลีดเก่า) · warm≥35 (TLD/Moderate/MerHot) · cold = ที่เหลือ
    total = sum(pts for _, pts in breakdown)
    if total >= 55:
        tier = "🔥hot"
    elif total >= 35:
        tier = "🌡warm"
    else:
        tier = "❄cold"

    return {"score": total, "tier": tier, "breakdown": breakdown}


_lsc_cache: dict = {"key": None, "ts": 0.0, "val": None}


def prepare_lead_score_context(raw_leads: list, sales_reports: list) -> dict:
    """โหลด config + สร้าง lookup maps สำหรับการคำนวณ Lead Score แบบ batch.
    เรียก 1 ครั้งต่อ request → ใช้ซ้ำได้กับหลาย rows.

    Cache 60s (in-process): ผลขึ้นกับ raw_leads+sales_reports ซึ่งเป็น sheet ที่ cache อยู่แล้ว
    → ไม่ต้องวน 14k leads สร้าง top_cars ใหม่ทุกหน้าเซลล์. key = (len, len) กัน data คนละชุด.
    """
    import time as _t
    key = (len(raw_leads), len(sales_reports))
    now = _t.time()
    if _lsc_cache["val"] is not None and _lsc_cache["key"] == key and (now - _lsc_cache["ts"]) < 60:
        return _lsc_cache["val"]

    cfg = load_lead_score_config()
    val = {"cfg": cfg}
    _lsc_cache.update(key=key, ts=now, val=val)
    return val


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
        result = compute_lead_score(row, cfg)
        case["leadScore"] = result["score"]
        case["leadTier"] = result["tier"]
        case["scoreBreakdown"] = result["breakdown"]

    return follow_cases


# ════════════════════════════════════════════════════════════════
# 🔔 แจ้งเตือน "ตามด่วน" รายเซลล์ (เฟส 2) — mirror followUrgency จาก seller.html เป็น Python
# cron_tick ยิงเช้า/บ่าย → ส่ง LINE ข้อความธรรมดา top N ให้เซลล์แต่ละคน · pass เดียว (group ตาม seller)
# ════════════════════════════════════════════════════════════════
# ลิงก์ในข้อความ followup → ดึงจาก SITE_URL (.env) เพื่อให้ตรงโดเมนที่ใช้จริง (VPS)
_FU_BASE = (getattr(settings, "SITE_URL", "") or "https://srv1793506.hstgr.cloud").rstrip("/")
_FU_CADENCE = {"สนใจมาก": 1, "ลังเล": 2, "ไม่รับสาย": 1, "ลูกค้าไม่ตอบ": 1, "รอเงิน": 3, "รอเช็คเครดิต": 2, "ดาวน์ไม่พอ": 3, "เงินสดเงินไม่พอ": 3}
# อ้าง CUSTOMER_STATUS_DEAD (นิยาม "เคสเสีย" ของ dashboard) ตัวเดียวกัน — กัน followup ดันเคสที่ dashboard ถือว่าตายแล้ว (เดิมลิสต์แยกกันคำไม่ตรง)
_FU_DEAD = CUSTOMER_STATUS_DEAD
_FU_SKIP = ["จบ", "ส่งมอบ", "คืนเคส", "คืน", "ยกเลิก", "ไม่สนใจ", "dead", "จ่ายใหม่"]
_FU_NOANS_CAP = 5
_FU_TH_MON = ["", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]


def build_followup_messages(max_leads: int = 5, max_deals: int = 5) -> list[dict]:
    """ข้อความ "ตามด่วน" รายเซลล์ (ข้อความธรรมดา) — สมองเดียวกับ seller.html (followUrgency + cadence + ดีลค้าง)
    คืน [{"seller", "user_id", "text"}] เฉพาะเซลล์ที่มีเคส + มี user_id · กรองเฉพาะเคสใหม่ (เดือนนี้ + 1 สัปดาห์ท้ายเดือนก่อน)
    """
    from collections import defaultdict
    from datetime import timedelta
    from .google_sheets import fetch_all_sheets, cell, cell_num, LEADS_COL as L, SALES_COL as S
    from .constants import (normalize_seller, ALL_SELLERS, refresh_from_sheet,
                            ADMIN_SELLERS, ADMIN_USER_IDS, load_admin_user_ids,
                            TELE_USER_IDS, load_tele_user_ids)
    from .line_notify import get_nickname_to_user_id

    refresh_from_sheet()
    load_admin_user_ids()
    load_tele_user_ids()
    raw = fetch_all_sheets()
    raw_leads = raw.get("leads") or []
    sales_reports = raw.get("sales_reports") or []
    ctx = prepare_lead_score_context(raw_leads, sales_reports)
    nick2uid = get_nickname_to_user_id()
    today = bangkok_now().date()
    win_start = today.replace(day=1) - timedelta(days=7)
    date_str = f"{today.day} {_FU_TH_MON[today.month]} {(today.year + 543) % 100:02d}"  # เช่น "13 มิ.ย. 69"

    def _ds(s):
        d = parse_date(str(s or "").split(" ")[0].strip())
        return (today - d).days if d else None

    def _inwin(s):
        d = parse_date(str(s or "").split(" ")[0].strip())
        return bool(d) and d >= win_start

    def _idle(l):
        d = _ds(l["lastUpdate"])
        if d is None:
            d = _ds(l["dateIn"])
        return max(0, d) if d is not None else 0

    def _cad(l):
        z = l["customerStatus"] or ""
        for k, v in _FU_CADENCE.items():
            if k in z:
                return v
        return 2

    # ── "ไม่ต้องตาม" = ดูคอลัม Z (สถานะลูกค้า) ร่วมกับ AB (Status แอดมิน) + เซลล์ — อันใดอันหนึ่งเข้าเงื่อนไข = ตัด ──
    # (เดิม _booked ดูแค่ Z ถ้า Z มีค่า → เคส Z=ติดตาม แต่ AB=จอง/ปล่อย หลุดมาโดนตามผิด)
    # ตัวอย่าง: Z ว่าง·AB=ยกเลิก → ตัด · Z=คืนเคส·AB=ติดตาม → ตัด (คำเสียใน Z ชนะ) · Z=ติดตาม·AB=จอง → ตัด (booked จาก AB)
    def _skip(l):
        z = l["customerStatus"] or ""
        if any(k in z for k in _FU_DEAD):            # คำ "เคสเสีย" ของ Z (controlled vocab)
            return True
        # ยกเลิก/คืนเคส/จ่ายใหม่/จบ/ส่งมอบ... ที่ไหนก็ตาม (Z หรือ AB หรือเซลล์)
        st = (z + " " + (l["adminStatus"] or "") + " " + (l["salesStatus"] or "")).lower()
        return any(k.lower() in st for k in _FU_SKIP)

    def _booked(l):
        # จอง/ปล่อย/ส่งมอบ/ได้รถแล้ว ที่คอลัมไหนก็ตาม (Z + AB + เซลล์) = ไม่ตามเป็นลีดใหม่
        blob = (l["customerStatus"] or "") + " " + (l["adminStatus"] or "") + " " + (l["salesStatus"] or "")
        return any(k in blob for k in ("จอง", "ส่งมอบ", "ได้รถแล้ว", "ปล่อย"))

    def _urg(l):
        score = l["leadScore"] or 0
        updates = l["updateCount"] or 0
        cp = l["followPriority"] or 0
        idle = min(_idle(l), 21)
        z = l["customerStatus"] or ""
        if "ไม่รับสาย" in z and updates >= _FU_NOANS_CAP:
            return -1
        if updates == 0:
            return 120 + (score / 100) * idle * 9 + cp * 6 + idle * 2
        over = idle - _cad(l)
        u = cp * 6
        if over >= 0:
            u += 40 + (score / 100) * over * 9 + over * 2
        else:
            u *= 0.35
        return u

    def _reason(l):
        updates = l["updateCount"] or 0
        idle = _idle(l)
        hot = "hot" in (l["leadTier"] or "")
        over = idle - _cad(l)
        z = l["customerStatus"] or ""
        if updates == 0:
            return "ยังไม่โทรเลย"
        if "ไม่รับสาย" in z:
            return f"ไม่รับสาย ลองครั้งที่ {updates + 1}"
        if hot and over >= 0:
            return f"ฮอท ค้าง {idle} วัน"
        if over >= 2:
            return f"เลยรอบตาม {over} วัน"
        if over >= 0:
            return "ถึงรอบตาม"
        if (l["followPriority"] or 0) >= 7:
            return "ลูกค้าสนใจมาก"
        return "ตามต่อ"

    leads_by_seller = defaultdict(list)
    for r in raw_leads:
        name = normalize_seller(cell(r, L.sales_rep))
        if not name or (name not in ALL_SELLERS and name != "ADMIN"):
            continue
        if not _inwin(cell(r, L.received_date)):
            continue
        try:
            ls = compute_lead_score(r, ctx["cfg"])
        except Exception:
            ls = {"score": 0, "tier": "❄cold"}
        leads_by_seller[name].append({
            "code": cell(r, L.lead_code), "leadScore": ls["score"], "leadTier": ls["tier"],
            "updateCount": int(cell_num(r, L.update_count)),
            "customerStatus": cell(r, L.customer_status),
            "followPriority": customer_status_priority(cell(r, L.customer_status)),
            "lastUpdate": cell(r, L.last_updated_at), "dateIn": cell(r, L.received_date),
            "adminStatus": cell(r, L.admin_status), "salesStatus": cell(r, L.sales_status),
        })

    bookings_by_seller = defaultdict(list)
    for r in sales_reports:
        seller = normalize_seller(cell(r, S.sales_rep).replace("ชื่อเซลล์ ", "").replace("ชื่อเซลล์", "").strip())
        if not seller or (seller not in ALL_SELLERS and seller != "ADMIN"):
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
        bookings_by_seller[seller].append({
            "status": status.replace(" (ซื้อสด)", "").strip(),
            "customer": cell(r, S.customer_name), "plate": cell(r, S.license_plate),
            "date": cell(r, S.date), "signDate": cell(r, S.sign_date), "resultDate": result_date_for(r),
        })

    def _stuck(bcs):
        out = []; seen = set()
        for b in bcs:
            st = b.get("status", "") or ""
            if not _inwin(b.get("date")):
                continue
            key = (b.get("customer", ""), b.get("plate", ""), st, b.get("date", ""))
            if key in seen:
                continue
            seen.add(key)
            sd = b.get("signDate"); sd = sd if sd and sd != "-" else None
            if "รอเซ็น" in st or ("จอง" in st and not sd):
                d = _ds(b.get("date")); rs, lo = "ค้างเซ็น", 3
            elif "รอผล" in st:
                d = _ds(sd or b.get("date")); rs, lo = "รอผลไฟแนนซ์นาน", 5
            elif "รอปล่อย" in st:
                d = _ds(b.get("resultDate") or sd or b.get("date")); rs, lo = "รอปล่อยค้าง", 3
            else:
                continue
            if d is None or d <= lo:
                continue
            out.append((b, rs, d))
        out.sort(key=lambda x: -x[2])
        return out

    out = []
    # summary: (name, n_follow, n_stuck, n_notcalled, n_stale7, n_nostatus) — กลุ่มที่มีงานค้าง (รวม ADMIN)
    summary = []
    admin_recip = sorted(r for r in TELE_USER_IDS if r)  # ไอดีเทเลเซลล์ (ชีต "ตั้งค่าเทเลเซลล์") — ผู้รับ followup กลุ่ม ADMIN
    for name in sorted(ALL_SELLERS) + ["ADMIN"]:
        leads = leads_by_seller.get(name, [])
        _active = [l for l in leads if not _skip(l) and not _booked(l)]
        n_nc = sum(1 for l in _active if (l["updateCount"] or 0) == 0)            # ยังไม่โทร
        n_st = sum(1 for l in _active if _idle(l) > 7)                            # ค้างเกิน 7 วัน
        n_ns = sum(1 for l in _active if not (l["customerStatus"] or "").strip()
                   and not (l["adminStatus"] or "").strip()
                   and not (l["salesStatus"] or "").strip())  # ไม่มีสถานะเลย (Z + คอลัมเก่าว่างหมด)
        urgent_all = [l for l in _active if _urg(l) > 0]
        urgent_all.sort(key=_urg, reverse=True)
        sd_all = _stuck(bookings_by_seller.get(name, []))
        if urgent_all or sd_all:
            summary.append((name, len(urgent_all), len(sd_all), n_nc, n_st, n_ns))
        # ผู้รับ: เซลล์ปกติ = uid ตัวเอง · "ADMIN" (เทเลเซลล์) = 5 ไอดีในชีต "ตั้งค่าแอดมิน"
        if name == "ADMIN":
            recips, link_uid = admin_recip, (admin_recip[0] if admin_recip else "")
        else:
            _uid = nick2uid.get(name)
            recips, link_uid = ([_uid] if _uid else []), (_uid or "")
        if not recips:
            continue
        urgent = urgent_all[:max_leads]
        sd = sd_all[:max_deals]
        if not urgent and not sd:
            continue
        if name == "ADMIN":
            lines = [f"ตามด่วนวันนี้ (กลุ่มเทเลเซลล์) - {date_str}", ""]
        else:
            lines = [f"ตามด่วนวันนี้ - {date_str}", ""]
        if urgent:
            lines.append("ลีดต้องตาม")
            for l in urgent:
                lines.append(f"- {l['code'] or '(ไม่มีโค้ด)'} — {_reason(l)}")
            lines.append("")
        if sd:
            lines.append("ดีลค้าง")
            for b, rs, d in sd:
                lines.append(f"- {b.get('customer') or '-'} · ทะเบียน {b.get('plate') or '-'} — {rs} {d} วัน")
            lines.append("")
        lines.append("เปิดหน้ากลุ่มเทเลเซลล์:" if name == "ADMIN" else "เปิดหน้าตัวเอง:")
        lines.append(f"{_FU_BASE}/s/{link_uid}/")
        out.append({"seller": name, "user_id": link_uid, "recipients": recips, "text": "\n".join(lines)})

    # ── สรุปรวมทีม สำหรับแอดมิน (entry พิเศษ admin=True · cron ส่งเข้า ADMIN_USER_IDS) ──
    if summary:
        summary.sort(key=lambda x: -(x[1] + x[2]))
        tot_f = sum(x[1] for x in summary)
        tot_s = sum(x[2] for x in summary)
        tot_nc = sum(x[3] for x in summary)
        tot_st = sum(x[4] for x in summary)
        tot_ns = sum(x[5] for x in summary)
        olines = [f"สรุปตามด่วนวันนี้ (ทีม) - {date_str}", "",
                  f"ต้องตามรวม {tot_f} เคส - ดีลค้าง {tot_s} ดีล",
                  f"- ยังไม่โทร {tot_nc} เคส",
                  f"- ค้างเกิน 7 วัน {tot_st} เคส",
                  f"- ยังไม่ใส่สถานะ {tot_ns} เคส", ""]
        for nm, nf, ns, nc, nd, nx in summary:
            parts = []
            if ns:
                parts.append(f"{ns} ดีลค้าง")
            if nc:
                parts.append(f"ยังไม่โทร ({nc} เคส)")
            if nx:
                parts.append(f"ไม่มีสถานะ ({nx} เคส)")
            if not parts:
                continue
            _lbl = "เทเลเซลล์" if nm == "ADMIN" else nm
            olines.append(f"- {_lbl}: {' - '.join(parts)}")
        olines.append("")
        olines.append(f"ดูภาพรวม: {_FU_BASE}/dashboard/")
        # ผู้รับสรุป = แอดมินเทเลเซลล์ (ADMIN_USER_IDS) + เซลล์ที่ติ๊กแอดมิน 👑 (ADMIN_SELLERS → uid)
        admin_recipients = set(ADMIN_USER_IDS) | {nick2uid[n] for n in ADMIN_SELLERS if nick2uid.get(n)}
        out.append({"seller": "", "user_id": "", "admin": True,
                    "recipients": sorted(r for r in admin_recipients if r),
                    "text": "\n".join(olines)})
    return out
