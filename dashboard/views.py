"""Dashboard views — ported from Next.js API routes + pages."""
import json
import urllib.parse

from django.http import JsonResponse, HttpResponseRedirect
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .services.fetch_dashboard import fetch_dashboard_data
from .services.google_sheets import fetch_sheet, cell, EMPLOYEE_COL as EM
from .services.constants import (
    UPD_TGT, PAGE_SIZE, STATUS_COLOR, STATUS_ORDER,
    TEAM_COLORS, TEAM_NAMES, LT_COLORS, MONTHS_SHORT, MONTHS_FULL,
    TEAM_ID, TARGETS,
)
from .services.helpers import pct, nc, urg, nocar, empty, dots_html, urg_badge_html
from .services.seller_tokens import seller_from_token


@require_GET
def index(request):
    """Redirect / → /dashboard"""
    return HttpResponseRedirect("/dashboard/")


@require_GET
def dashboard_page(request):
    """Main dashboard page — renders template with all data as JSON for JS."""
    try:
        data = fetch_dashboard_data()
    except Exception as e:
        return render(request, "dashboard/index.html", {
            "error": str(e),
            "data_json": "null",
            "constants_json": "{}",
        })

    constants = {
        "UPD_TGT": UPD_TGT,
        "PAGE_SIZE": PAGE_SIZE,
        "STATUS_COLOR": STATUS_COLOR,
        "STATUS_ORDER": STATUS_ORDER,
        "TEAM_COLORS": TEAM_COLORS,
        "TEAM_NAMES": TEAM_NAMES,
        "LT_COLORS": LT_COLORS,
        "MONTHS_SHORT": MONTHS_SHORT,
        "MONTHS_FULL": MONTHS_FULL,
    }

    return render(request, "dashboard/index.html", {
        "data_json": json.dumps(data, ensure_ascii=False, default=str),
        "constants_json": json.dumps(constants, ensure_ascii=False),
        "error": None,
    })


@require_GET
def api_dashboard(request):
    """GET /api/dashboard — JSON API endpoint."""
    try:
        data = fetch_dashboard_data()
        return JsonResponse(data, json_dumps_params={"ensure_ascii": False, "default": str})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@require_GET
def api_auth(request):
    """GET /api/auth?token=... — verify magic link token."""
    token = request.GET.get("token")
    if not token:
        return JsonResponse({"error": "Missing token"}, status=400)

    try:
        employees = fetch_sheet("employees")
        row = None
        for r in employees:
            if cell(r, EM.user_id) == token:
                row = r
                break

        if not row:
            return JsonResponse({"error": "Invalid token"}, status=404)

        return JsonResponse({
            "id": cell(row, EM.user_id),
            "user_id": cell(row, EM.user_id),
            "display_name": cell(row, EM.display_name),
            "nickname": cell(row, EM.nickname),
            "position": cell(row, EM.position),
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@require_GET
def magic_link(request, token):
    """Magic link auth entry — /u/<token>/"""
    return render(request, "dashboard/magic_link.html", {"token": token})


@require_GET
def seller_dashboard(request, token):
    """หน้าส่วนตัวของเซลล์ — /s/<token>/

    Token เป็นเลข 6-10 หลักสุ่ม (ดู services/seller_tokens.py).
    เซลล์เห็นเฉพาะข้อมูลของตัวเอง พร้อมรายการลูกค้าที่ "ต้องโทร".
    """
    seller_name = seller_from_token(token)
    if not seller_name:
        return render(request, "dashboard/seller.html", {
            "error": "ลิงก์ไม่ถูกต้องหรือหมดอายุ — กรุณาติดต่อผู้ดูแลระบบ",
            "seller": None,
            "data_json": "null",
            "constants_json": "{}",
        }, status=404)

    try:
        data = fetch_dashboard_data()
    except Exception as e:
        return render(request, "dashboard/seller.html", {
            "error": str(e),
            "seller": seller_name,
            "data_json": "null",
            "constants_json": "{}",
        })

    # ── กรองข้อมูลเฉพาะของเซลล์คนนี้ ──
    my_seller = next(
        (s for s in data.get("sellers", []) if s["name"] == seller_name),
        {
            "name": seller_name,
            "team": TEAM_ID.get(seller_name, "?"),
            "lead": 0, "follow": 0, "vacant": 0, "done": 0,
            "target": TARGETS.get(seller_name, 0),
            "booking": 0, "live": 0, "clip": 0, "clipTarget": 0,
            "liveInbox": 0, "liveLead": 0, "leadTypes": {},
        },
    )
    my_follows = [c for c in data.get("followCases", []) if c["seller"] == seller_name]
    my_bookings = [b for b in data.get("bookingCases", []) if b["seller"] == seller_name]
    today_my = data.get("today", {}).get("bySeller", {}).get(seller_name, {
        "lead": 0, "follow": 0, "vacant": 0,
    })

    # ── จัดอันดับ "ต้องโทร" โดยความเร่งด่วน ──
    # urgency: lead ที่ยังไม่ได้โทรเลย (updateCount=0) = สูงสุด
    # ตามด้วยจำนวนครั้งที่ยังขาดให้ครบ UPD_TGT
    def call_priority(c):
        u = c.get("updateCount", 0)
        score = 100 if u == 0 else 0
        score += max(0, UPD_TGT - u) * 10
        return score

    for c in my_follows:
        u = c.get("updateCount", 0)
        c["mustCall"] = u == 0 or u < UPD_TGT
        c["callScore"] = call_priority(c)
    my_follows.sort(key=lambda c: c["callScore"], reverse=True)

    must_call_count = sum(1 for c in my_follows if c["mustCall"])

    filtered = {
        "meta": data.get("meta", {}),
        "seller": my_seller,
        "today": today_my,
        "followCases": my_follows,
        "bookingCases": my_bookings,
        "mustCallCount": must_call_count,
    }

    constants = {
        "UPD_TGT": UPD_TGT,
        "STATUS_COLOR": STATUS_COLOR,
        "STATUS_ORDER": STATUS_ORDER,
        "TEAM_COLORS": TEAM_COLORS,
        "TEAM_NAMES": TEAM_NAMES,
        "LT_COLORS": LT_COLORS,
        "MONTHS_SHORT": MONTHS_SHORT,
    }

    return render(request, "dashboard/seller.html", {
        "error": None,
        "seller": seller_name,
        "data_json": json.dumps(filtered, ensure_ascii=False, default=str),
        "constants_json": json.dumps(constants, ensure_ascii=False),
    })
