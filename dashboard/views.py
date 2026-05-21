"""Dashboard views — ported from Next.js API routes + pages."""
import json
import urllib.parse

from django.conf import settings
from django.http import JsonResponse, HttpResponseRedirect
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods

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


def _session_user(request):
    """ดึง user จาก signed-cookie session, คืน None ถ้าไม่ login.

    Format: {"position": "admin"|"executive"|..., "nickname": str, "user_id": str, "display_name": str}
    """
    u = request.session.get("oxlet_user")
    if u and isinstance(u, dict) and u.get("position"):
        return u
    return None


DEFAULT_EXECUTIVE_USER = {
    "user_id": "guest",
    "nickname": "ผู้บริหาร",
    "display_name": "ผู้บริหาร",
    "position": "executive",
}


@ensure_csrf_cookie
@require_GET
def dashboard_page(request):
    """Main dashboard — เปิดให้ทุกคนเข้าได้ default เป็นมุมมอง 'ผู้บริหาร'.
    Admin ต้องกดปุ่ม ADMIN แล้ว login จึงจะได้สิทธิ์ admin (session).
    ใช้ @ensure_csrf_cookie เพื่อให้ csrftoken cookie ถูก set ตั้งแต่หน้าแรก
    (ปุ่ม ADMIN ใช้ค่านี้ส่ง AJAX login).
    """
    user = _session_user(request) or DEFAULT_EXECUTIVE_USER

    try:
        data = fetch_dashboard_data()
    except Exception as e:
        return render(request, "dashboard/index.html", {
            "error": str(e),
            "data_json": "null",
            "constants_json": "{}",
            "session_user_json": json.dumps(user),
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
        "session_user_json": json.dumps(user),
        "error": None,
    })


@require_GET
def api_dashboard(request):
    """GET /api/dashboard — JSON data (executive level, ไม่ต้อง login)."""
    try:
        data = fetch_dashboard_data()
        return JsonResponse(data, json_dumps_params={"ensure_ascii": False, "default": str})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@require_http_methods(["GET", "POST"])
def login_view(request):
    """ADMIN login — รับ username + password.
    GET → แสดงหน้า login. POST → ตรวจสอบ, รองรับทั้ง form submit และ AJAX (JSON).
    """
    next_url = request.GET.get("next", "/dashboard/")
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest" \
        or "application/json" in request.headers.get("Accept", "")

    if request.method == "GET":
        if _session_user(request) and _session_user(request).get("position") == "admin":
            return HttpResponseRedirect(next_url)
        return render(request, "dashboard/login.html", {"next": next_url, "error": None})

    # POST
    next_url = request.POST.get("next", "/dashboard/")
    username = (request.POST.get("username") or "").strip()
    password = (request.POST.get("password") or "").strip()

    admin_user = (getattr(settings, "OXLET_ADMIN_USER", "admin") or "admin").strip()
    admin_pw = (getattr(settings, "OXLET_ADMIN_PASSWORD", "") or "").strip()

    if username == admin_user and password and password == admin_pw:
        request.session["oxlet_user"] = {
            "user_id": "admin",
            "nickname": "admin",
            "display_name": "Admin",
            "position": "admin",
        }
        request.session.set_expiry(60 * 60 * 24 * 30)
        if is_ajax:
            return JsonResponse({"ok": True, "next": next_url})
        return HttpResponseRedirect(next_url)

    error = "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง" if (username or password) else "กรุณากรอกชื่อผู้ใช้และรหัสผ่าน"
    if is_ajax:
        return JsonResponse({"ok": False, "error": error}, status=401)
    return render(request, "dashboard/login.html", {"next": next_url, "error": error})


@require_GET
def logout_view(request):
    """ออกจากระบบ admin — กลับสู่มุมมอง 'ผู้บริหาร' (default)."""
    request.session.flush()
    resp = HttpResponseRedirect("/dashboard/")
    resp.delete_cookie("oxlet_employee")
    return resp


@require_http_methods(["GET", "POST"])
def admin_send_line(request):
    """Admin-only — ดู preview pipeline + ส่ง LINE Flex แจ้งเตือน

    GET  → คืน pipeline ทุกเซลล์พร้อม map nickname→user_id (preview)
    POST → ส่งจริง. body JSON: {test: bool, target_user_id?: str, sellers?: [name,...]}
    """
    user = _session_user(request)
    if not user or user.get("position") != "admin":
        return JsonResponse({"error": "ต้อง login เป็น admin ก่อน"}, status=401)

    # Import here to keep top-level lighter and isolate Sheets fetch errors
    from .services.line_notify import (
        build_seller_pipelines, build_seller_flex,
        push_line_message, get_nickname_to_user_id,
    )

    if request.method == "GET":
        # Debug info ของ token (ไม่เผยค่าจริง — แสดงแค่ length + prefix/suffix)
        raw_token = getattr(settings, "LINE_CHANNEL_ACCESS_TOKEN", "") or ""
        stripped = raw_token.strip()
        token_info = {
            "raw_length": len(raw_token),
            "stripped_length": len(stripped),
            "has_trailing_whitespace": raw_token != stripped,
            "starts_with": stripped[:6] if stripped else "",
            "ends_with": stripped[-6:] if stripped else "",
            "has_token": bool(stripped),
        }
        # ทดสอบ token กับ LINE API
        if stripped:
            try:
                import requests as _rq
                r = _rq.get(
                    "https://api.line.me/v2/bot/info",
                    headers={"Authorization": f"Bearer {stripped}"},
                    timeout=5,
                )
                token_info["line_api_status"] = r.status_code
                if r.status_code != 200:
                    token_info["line_api_error"] = r.text[:200]
                else:
                    import json as _j
                    token_info["bot_name"] = _j.loads(r.text).get("displayName", "?")
            except Exception as e:
                token_info["line_api_error"] = str(e)

        try:
            pipelines = build_seller_pipelines()
            uid_map = get_nickname_to_user_id()
        except Exception as e:
            return JsonResponse({"error": f"ดึงข้อมูลล้มเหลว: {e}"}, status=500)
        result = []
        for p in pipelines:
            result.append({
                "seller": p["seller"],
                "called": len(p["called"]),
                "notCalled": len(p["notCalled"]),
                "followUp": len(p["followUp"]),
                "noStatus": len(p["noStatus"]),
                "user_id": uid_map.get(p["seller"], ""),
                "has_user_id": bool(uid_map.get(p["seller"])),
            })
        return JsonResponse({
            "ok": True,
            "has_token": token_info["has_token"],
            "token_debug": token_info,
            "sellers": result,
            "total_sellers": len(result),
        })

    # POST
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        body = {}

    channel_token = (getattr(settings, "LINE_CHANNEL_ACCESS_TOKEN", "") or "").strip()
    if not channel_token:
        return JsonResponse({"error": "ยังไม่ได้ตั้ง LINE_CHANNEL_ACCESS_TOKEN ใน .env"}, status=500)

    test_mode = bool(body.get("test"))
    target_user_id = (body.get("target_user_id") or "").strip()
    only_sellers = body.get("sellers") or None

    if test_mode and not target_user_id:
        return JsonResponse({"error": "Test mode ต้องระบุ target_user_id"}, status=400)

    try:
        pipelines = build_seller_pipelines()
        uid_map = get_nickname_to_user_id()
    except Exception as e:
        return JsonResponse({"error": f"ดึงข้อมูลล้มเหลว: {e}"}, status=500)

    if only_sellers:
        wanted = set(only_sellers)
        pipelines = [p for p in pipelines if p["seller"] in wanted]

    base_url = request.build_absolute_uri("/").rstrip("/")
    results = []
    for p in pipelines:
        seller = p["seller"]
        target = target_user_id if test_mode else uid_map.get(seller, "")
        if not target:
            results.append({"seller": seller, "user_id": None, "sent": False,
                            "error": "ไม่พบ LINE user_id ของเซลล์ใน employees sheet"})
            continue
        try:
            flex = build_seller_flex(p, base_url=base_url)
            code, text = push_line_message(target, [flex], channel_token)
            if code == 200:
                results.append({"seller": seller, "user_id": target, "sent": True})
            else:
                results.append({"seller": seller, "user_id": target, "sent": False,
                                "error": f"LINE API {code}: {text[:200]}"})
        except Exception as e:
            results.append({"seller": seller, "user_id": target, "sent": False, "error": str(e)})

    return JsonResponse({
        "ok": True,
        "test_mode": test_mode,
        "count": len(results),
        "sent": sum(1 for r in results if r["sent"]),
        "results": results,
    })


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
