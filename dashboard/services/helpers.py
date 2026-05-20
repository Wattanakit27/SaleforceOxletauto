"""Helpers — ported from lib/helpers.ts"""
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from .constants import UPD_TGT

BKK = ZoneInfo("Asia/Bangkok")


def pct(a: int, b: int) -> int:
    return round((a / b) * 100) if b > 0 else 0


def nc(u: int) -> int:
    return max(0, UPD_TGT - u)


def urg(update_count: int) -> int:
    s = 100 if update_count == 0 else 0
    s += nc(update_count) * 10
    return s


def nocar(c: str | None) -> bool:
    return not c or c in ("ลูกค้าไม่ตอบ", "รถที่ไม่ได้ทำการตลาด", "-", "")


def empty(v: str | None) -> bool:
    return not v or v in ("-", "")


def bangkok_now() -> datetime:
    return datetime.now(BKK)


def today_day() -> int:
    return bangkok_now().day


def today_month() -> int:
    return bangkok_now().month


def pass_month(date_str: str | None, df_month: int) -> bool:
    """df_month: 0=ทั้งหมด, -1=วันนี้, 1-12=เดือนนั้น"""
    if df_month == 0:
        return True
    if not date_str:
        return True
    parts = date_str.split("/")
    if len(parts) < 2:
        return True
    try:
        day = int(parts[0])
        month = int(parts[1])
    except (ValueError, IndexError):
        return True
    if df_month == -1:
        return day == today_day() and month == today_month()
    return month == df_month


def parse_note_history(note: str) -> list[str]:
    if not note or note == "-":
        return []
    cleaned = re.sub(r"^\d{4,5}\s*", "", note)
    parts = [s.strip() for s in cleaned.split("/")]
    return [s for s in parts if s and s != "-"]


def dots_html(u: int) -> str:
    html = ""
    for i in range(UPD_TGT):
        filled = i < u
        if filled:
            if u >= UPD_TGT:
                c = "#3B6D11"
            elif u >= 3:
                c = "#1D9E75"
            elif u >= 2:
                c = "#EF9F27"
            else:
                c = "#E24B4A"
        else:
            c = "#ccc"
        html += f'<span class="dot" style="background:{c}"></span>'
    return (
        f'<span style="display:flex;align-items:center">{html}'
        f'<span style="font-size:10px;color:var(--t3);margin-left:2px">{u}/{UPD_TGT}</span></span>'
    )


def urg_badge_html(update_count: int) -> str:
    n = nc(update_count)
    if update_count == 0:
        return '<span class="bdg" style="background:var(--red-bg);color:var(--red)">ยังไม่โทร</span>'
    if n >= 3:
        return f'<span class="bdg" style="background:var(--red-bg);color:var(--red)">+{n}</span>'
    if n >= 1:
        return f'<span class="bdg" style="background:var(--amber-bg);color:var(--amber)">+{n}</span>'
    return '<span class="bdg" style="background:var(--green-bg);color:var(--green)">✓</span>'
