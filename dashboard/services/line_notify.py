"""LINE Flex notification — port จาก n8n workflow.

Pipeline:
1. ดึง leads จากชีต → filter เดือนปัจจุบัน
2. กรอง row ที่ admin_status ตรงกับ SKIP_STATUS (จบ/ยกเลิก/ฯลฯ)
3. Group ตามเซลล์ (normalize ชื่อ) → แยก called / notCalled / followUp / noStatus
4. สร้าง LINE Flex Message ต่อเซลล์
5. POST ไป LINE Messaging API push endpoint
"""
from __future__ import annotations

import requests

from .constants import normalize_seller
from .fetch_dashboard import bangkok_now, parse_date
from .google_sheets import (
    cell, cell_num, fetch_sheet,
    EMPLOYEE_COL as EM, LEADS_COL as L,
)
from .seller_tokens import SELLER_TOKENS

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"

# คำที่อยู่ใน admin_status แล้วต้องข้ามเคสนั้นไป
SKIP_STATUS = ["จบ", "ส่งมอบ", "คืนเคส", "คืน", "ยกเลิก", "ไม่สนใจ", "dead", "จ่ายใหม่"]

# คำที่อยู่ใน sales_status ถือว่า "ต้องตามต่อ"
FOLLOW_STATUS = ["ติดตาม", "รอตอบ", "รอลูกค้า", "รอ", "ผิดนัด", "โทรไม่รับ", "นัดหมาย"]

DAYS_TH = ["อาทิตย์", "จันทร์", "อังคาร", "พุธ", "พฤหัส", "ศุกร์", "เสาร์"]


def _strip_leading_digits(s: str) -> str:
    """ตัดเลข 4-5 ตัวหน้า (timestamp ที่ติดมากับโน้ตจาก sheet)."""
    if not s:
        return ""
    import re
    return re.sub(r"^\d{4,5}\s*", "", s).strip()


def build_seller_pipelines(target_month: int | None = None, target_year: int | None = None) -> list[dict]:
    """อ่าน leads sheet, filter เดือนเป้าหมาย, group ตามเซลล์, คืนรายการ pipeline ต่อเซลล์."""
    now = bangkok_now()
    if target_month is None:
        target_month = now.month
    if target_year is None:
        target_year = now.year

    raw_leads = fetch_sheet("leads")
    grouped: dict[str, dict] = {}

    for row in raw_leads:
        d = parse_date(cell(row, L.received_date))
        if not d or d.month != target_month or d.year != target_year:
            continue

        admin_status = cell(row, L.admin_status).lower()
        if admin_status and any(s.lower() in admin_status for s in SKIP_STATUS):
            continue

        seller_raw = cell(row, L.sales_rep).strip()
        seller = normalize_seller(seller_raw)
        if not seller or seller == "ADMIN":
            continue

        if seller not in grouped:
            grouped[seller] = {
                "seller": seller,
                "called": [],
                "notCalled": [],
                "followUp": [],
                "noStatus": [],
            }

        proof = cell(row, L.call_proof).strip()
        sales_status = cell(row, L.sales_status).strip()
        note = _strip_leading_digits(cell(row, L.fill_sheet_note))[:35]

        entry = {
            "code": cell(row, L.lead_code).strip(),
            "phone": cell(row, L.phone).strip(),
            "car": cell(row, L.car_formula).strip(),
            "upd": int(cell_num(row, L.update_count)),
            "note": note,
        }

        if proof == "ส่งแล้ว":
            grouped[seller]["called"].append(entry)
        else:
            grouped[seller]["notCalled"].append(entry)

        ss_low = sales_status.lower()
        if ss_low and any(f.lower() in ss_low for f in FOLLOW_STATUS):
            grouped[seller]["followUp"].append(entry)
        elif not sales_status or sales_status == "-":
            grouped[seller]["noStatus"].append(entry)

    return list(grouped.values())


def build_seller_flex(data: dict, base_url: str = "") -> dict:
    """สร้าง LINE Flex Message ของเซลล์ 1 คน — port จาก n8n '✉️ สร้าง Flex' node."""
    seller = data["seller"]
    called = data.get("called", [])
    not_called = data.get("notCalled", [])
    follow_up = data.get("followUp", [])

    now = bangkok_now()
    # weekday(): จันทร์=0, อาทิตย์=6 → แมปกลับเป็น อาทิตย์=0..เสาร์=6
    dow = (now.weekday() + 1) % 7
    date_label = f"{DAYS_TH[dow]} {now.day}/{now.month}/{str(now.year + 543)[-2:]}"

    total = len(called) + len(not_called)
    call_pct = round(len(called) / total * 100) if total > 0 else 0

    def progress_bar(fill: int, empty: int) -> dict:
        contents = []
        if fill > 0:
            contents.append({"type": "box", "layout": "vertical", "flex": fill, "height": "6px",
                             "backgroundColor": "#10b981", "cornerRadius": "4px", "contents": []})
        if empty > 0:
            contents.append({"type": "box", "layout": "vertical", "flex": empty, "height": "6px",
                             "backgroundColor": "#e5e7eb", "cornerRadius": "4px", "contents": []})
        return {"type": "box", "layout": "horizontal", "margin": "sm", "spacing": "none", "contents": contents}

    not_called_rows = []
    for c in not_called[:5]:
        car_part = f" · {c['car']}" if c["car"] else ""
        not_called_rows.append({
            "type": "box", "layout": "horizontal", "margin": "xs",
            "contents": [
                {"type": "box", "layout": "vertical", "width": "6px", "height": "6px",
                 "backgroundColor": "#ef4444", "cornerRadius": "3px", "margin": "none",
                 "offsetTop": "5px", "contents": []},
                {"type": "box", "layout": "vertical", "flex": 1, "margin": "sm", "contents": [
                    {"type": "text", "text": c["code"] or "-", "size": "xs", "color": "#1f2937", "weight": "bold"},
                    {"type": "text", "text": f"{c['phone'] or '-'}{car_part}",
                     "size": "xxs", "color": "#9ca3af", "wrap": True},
                ]},
            ],
        })
    if len(not_called) > 5:
        not_called_rows.append({"type": "text", "text": f"+ อีก {len(not_called) - 5} เคส",
                                "size": "xxs", "color": "#9ca3af", "align": "center", "margin": "xs"})

    follow_rows = []
    for c in follow_up[:4]:
        follow_rows.append({
            "type": "box", "layout": "horizontal", "margin": "xs",
            "contents": [
                {"type": "box", "layout": "vertical", "width": "6px", "height": "6px",
                 "backgroundColor": "#f59e0b", "cornerRadius": "3px", "margin": "none",
                 "offsetTop": "5px", "contents": []},
                {"type": "box", "layout": "vertical", "flex": 1, "margin": "sm", "contents": [
                    {"type": "text", "text": c["code"] or "-", "size": "xs", "color": "#1f2937", "weight": "bold"},
                    {"type": "text", "text": c["note"] or c["phone"] or "-",
                     "size": "xxs", "color": "#9ca3af", "wrap": True},
                ]},
            ],
        })
    if len(follow_up) > 4:
        follow_rows.append({"type": "text", "text": f"+ อีก {len(follow_up) - 4} เคส",
                            "size": "xxs", "color": "#9ca3af", "align": "center", "margin": "xs"})

    body = [
        {
            "type": "box", "layout": "horizontal", "spacing": "sm",
            "contents": [
                {"type": "box", "layout": "vertical", "flex": 1, "backgroundColor": "#f0fdf4",
                 "cornerRadius": "8px", "paddingAll": "10px", "contents": [
                    {"type": "text", "text": str(len(called)), "size": "xxl", "color": "#10b981",
                     "weight": "bold", "align": "center"},
                    {"type": "text", "text": "✅ โทรแล้ว", "size": "xxs", "color": "#6b7280", "align": "center"},
                 ]},
                {"type": "box", "layout": "vertical", "flex": 1, "backgroundColor": "#fef2f2",
                 "cornerRadius": "8px", "paddingAll": "10px", "contents": [
                    {"type": "text", "text": str(len(not_called)), "size": "xxl", "color": "#ef4444",
                     "weight": "bold", "align": "center"},
                    {"type": "text", "text": "📵 ยังไม่โทร", "size": "xxs", "color": "#6b7280", "align": "center"},
                 ]},
                {"type": "box", "layout": "vertical", "flex": 1, "backgroundColor": "#fffbeb",
                 "cornerRadius": "8px", "paddingAll": "10px", "contents": [
                    {"type": "text", "text": str(len(follow_up)), "size": "xxl", "color": "#f59e0b",
                     "weight": "bold", "align": "center"},
                    {"type": "text", "text": "🔔 ต้องตาม", "size": "xxs", "color": "#6b7280", "align": "center"},
                 ]},
            ],
        },
        {"type": "box", "layout": "horizontal", "margin": "md", "contents": [
            {"type": "text", "text": "อัตราโทร", "size": "xxs", "color": "#9ca3af", "flex": 1},
            {"type": "text", "text": f"{call_pct}%", "size": "xxs", "color": "#374151", "weight": "bold", "flex": 0},
        ]},
        progress_bar(call_pct, 100 - call_pct),
    ]

    if not_called:
        body.append({"type": "separator", "margin": "lg"})
        body.append({"type": "box", "layout": "horizontal", "margin": "md", "contents": [
            {"type": "box", "layout": "vertical", "width": "3px", "backgroundColor": "#ef4444",
             "cornerRadius": "2px", "margin": "none", "contents": []},
            {"type": "text", "text": " ยังไม่โทร", "size": "xs", "color": "#374151", "weight": "bold", "margin": "sm"},
        ]})
        body.extend(not_called_rows)

    if follow_up:
        body.append({"type": "separator", "margin": "md"})
        body.append({"type": "box", "layout": "horizontal", "margin": "sm", "contents": [
            {"type": "box", "layout": "vertical", "width": "3px", "backgroundColor": "#f59e0b",
             "cornerRadius": "2px", "margin": "none", "contents": []},
            {"type": "text", "text": " ต้องตามอีก", "size": "xs", "color": "#374151", "weight": "bold", "margin": "sm"},
        ]})
        body.extend(follow_rows)

    # ปุ่ม footer ลิงก์ไปหน้าส่วนตัวของเซลล์ (/s/<token>/)
    token = SELLER_TOKENS.get(seller)
    seller_url = f"{base_url}/s/{token}/" if token else f"{base_url}/dashboard/"

    return {
        "type": "flex",
        "altText": f"📊 Pipeline วันนี้ — {seller} | โทรแล้ว {len(called)} · ยังไม่โทร {len(not_called)} · ต้องตาม {len(follow_up)}",
        "contents": {
            "type": "bubble", "size": "mega",
            "header": {
                "type": "box", "layout": "vertical", "backgroundColor": "#0055aa", "paddingAll": "16px",
                "contents": [
                    {"type": "text", "text": "Pipeline วันนี้", "size": "xs", "color": "#93c5fd"},
                    {"type": "text", "text": seller, "size": "xl", "color": "#ffffff", "weight": "bold"},
                    {"type": "text", "text": date_label, "size": "xs", "color": "#bfdbfe", "margin": "xs"},
                ],
            },
            "body": {"type": "box", "layout": "vertical", "paddingAll": "14px", "contents": body},
            "footer": {
                "type": "box", "layout": "vertical", "paddingAll": "10px",
                "contents": [{
                    "type": "button",
                    "action": {"type": "uri", "label": "ดูเคสติดตาม", "uri": seller_url},
                    "style": "primary", "color": "#0055aa", "height": "sm",
                }],
            },
        },
    }


def push_line_message(user_id: str, messages: list[dict], channel_token: str, timeout: int = 10) -> tuple[int, str]:
    """ยิง message ไป LINE push endpoint. คืน (status_code, response_text)."""
    res = requests.post(
        LINE_PUSH_URL,
        headers={
            "Authorization": f"Bearer {channel_token}",
            "Content-Type": "application/json",
        },
        json={"to": user_id, "messages": messages},
        timeout=timeout,
    )
    return res.status_code, res.text


def get_nickname_to_user_id() -> dict[str, str]:
    """อ่าน employees sheet → คืน dict {nickname: line_user_id}."""
    employees = fetch_sheet("employees")
    out: dict[str, str] = {}
    for r in employees:
        uid = cell(r, EM.user_id)
        nick = cell(r, EM.nickname)
        if uid and nick:
            out[nick] = uid
    return out


def _cell_truthy(v: str) -> bool:
    """แปลง cell string เป็น bool — TRUE/yes/1/ใช่/ขึ้น เป็น True"""
    return (v or "").strip().lower() in ("true", "yes", "1", "ใช่", "เปิด", "on")


def load_schedules() -> list[dict]:
    """อ่าน schedule_config sheet → list of dict
    Fields: time(HH:MM), days(str), sellers(list or '*'), test_target, enabled(bool), label
    """
    from .google_sheets import fetch_sheet, cell, SCHEDULE_COL as SC
    try:
        rows = fetch_sheet("schedule_config")
    except Exception:
        return []

    schedules = []
    for r in rows:
        time_str = cell(r, SC.time).strip()
        if not time_str or ":" not in time_str:
            continue
        # validate + normalize HH:MM (sheet อาจเก็บ "9:00" ไม่มี leading zero)
        try:
            hh, mm = time_str.split(":", 1)
            time_str = f"{int(hh):02d}:{int(mm):02d}"
        except Exception:
            continue
        days = cell(r, SC.days).strip() or "*"
        sellers_str = cell(r, SC.sellers).strip() or "*"
        sellers_list = ["*"] if sellers_str == "*" else [s.strip() for s in sellers_str.split(",") if s.strip()]
        schedules.append({
            "time": time_str,
            "days": days,
            "sellers": sellers_list,
            "test_target": cell(r, SC.test_target).strip(),
            "enabled": _cell_truthy(cell(r, SC.enabled)),
            "label": cell(r, SC.label).strip(),
        })
    return schedules


def schedule_matches_now(sched: dict, now=None) -> bool:
    """ตรวจว่า schedule ตรงกับเวลาปัจจุบัน (BKK) หรือเปล่า — match by HH:MM นาทีต่อนาที"""
    from .fetch_dashboard import bangkok_now
    n = now or bangkok_now()
    if not sched.get("enabled"):
        return False
    # day match
    days = sched.get("days") or "*"
    if days != "*":
        # Sunday=0 .. Saturday=6 (matches cron convention)
        weekday = (n.weekday() + 1) % 7  # python: Mon=0 → ours: Mon=1, Sun=0
        ok = False
        for part in days.split(","):
            part = part.strip()
            if "-" in part:
                a, b = part.split("-", 1)
                try:
                    if int(a) <= weekday <= int(b):
                        ok = True; break
                except ValueError:
                    pass
            else:
                try:
                    if int(part) == weekday:
                        ok = True; break
                except ValueError:
                    pass
        if not ok:
            return False
    # time match (HH:MM exact)
    target = sched["time"]
    current = f"{n.hour:02d}:{n.minute:02d}"
    return target == current
