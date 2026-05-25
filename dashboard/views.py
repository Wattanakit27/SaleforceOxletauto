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
def admin_seller_config(request):
    """Admin endpoint — ตั้งเป้า/ทีม
    GET  → คืน config ปัจจุบัน
    POST body: {"sellers":[{"name":"โอ๊ต","team":"A","target":8},...]}
         → เขียนกลับ Google Sheet (tab "ตั้งค่าเซลล์", สร้าง tab ใหม่ถ้าไม่มี)
    """
    user = _session_user(request)
    if not user or user.get("position") != "admin":
        return JsonResponse({"error": "ต้อง login admin ก่อน"}, status=401)

    from .services.constants import refresh_from_sheet, TEAMS, TARGETS
    from .services.google_sheets import SHEET_CONFIG, write_sheet

    if request.method == "POST":
        try:
            body = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "JSON ไม่ถูกต้อง"}, status=400)

        incoming = body.get("sellers") or []
        if not isinstance(incoming, list):
            return JsonResponse({"error": "sellers ต้องเป็น list"}, status=400)

        # Validate + normalize
        cleaned = []
        seen_names = set()
        for idx, s in enumerate(incoming):
            name = str(s.get("name", "") or "").strip()
            team = str(s.get("team", "") or "").strip().upper()
            try:
                target = int(s.get("target", 0) or 0)
            except (ValueError, TypeError):
                return JsonResponse({"error": f"แถวที่ {idx+1}: target ต้องเป็นจำนวนเต็ม"}, status=400)
            if not name:
                return JsonResponse({"error": f"แถวที่ {idx+1}: ชื่อเล่นว่าง"}, status=400)
            if not team:
                return JsonResponse({"error": f"แถวที่ {idx+1} ({name}): ทีมว่าง"}, status=400)
            if target < 0:
                return JsonResponse({"error": f"แถวที่ {idx+1} ({name}): เป้าต้อง ≥ 0"}, status=400)
            if name in seen_names:
                return JsonResponse({"error": f"ชื่อเล่นซ้ำ: {name}"}, status=400)
            seen_names.add(name)
            cleaned.append([name, team, target])

        if not cleaned:
            return JsonResponse({"error": "ต้องมีอย่างน้อย 1 เซลล์"}, status=400)

        # เรียง by team, name แล้วใส่ header
        cleaned.sort(key=lambda r: (r[1], r[0]))
        values = [["ชื่อเล่น", "ทีม", "เป้า"]] + cleaned

        try:
            write_sheet("sellers_config", values)
        except Exception as e:
            return JsonResponse({"error": f"เขียน sheet ล้มเหลว: {e}"}, status=500)

        # โหลด config ใหม่ทันทีให้ dashboard เห็นค่าใหม่
        refresh_from_sheet()
        return JsonResponse({"ok": True, "saved": len(cleaned)})

    # GET
    loaded_from_sheet = refresh_from_sheet()
    cfg = SHEET_CONFIG.get("sellers_config", {})
    sheet_url = f"https://docs.google.com/spreadsheets/d/{cfg.get('spreadsheet_id','')}/edit"

    sellers = []
    for tid, members in sorted(TEAMS.items()):
        for name in members:
            sellers.append({
                "name": name,
                "team": tid,
                "target": TARGETS.get(name, 0),
            })
    sellers.sort(key=lambda s: (s["team"], s["name"]))

    return JsonResponse({
        "ok": True,
        "loaded_from_sheet": loaded_from_sheet,
        "sheet_url": sheet_url,
        "sheet_name": cfg.get("sheet_name", "ตั้งค่าเซลล์"),
        "sellers": sellers,
        "total_target": sum(s["target"] for s in sellers),
        "team_count": len({s["team"] for s in sellers}),
    })


@require_http_methods(["GET", "POST"])
def admin_schedule_config(request):
    """Admin endpoint — ตารางเวลาส่ง LINE Flex อัตโนมัติ
    GET  → คืนรายการ schedule
    POST body: {"schedules":[{"time":"09:00","days":"*","sellers":["*"],"test_target":"","enabled":true,"label":"เช้า"},...]}
    """
    user = _session_user(request)
    if not user or user.get("position") != "admin":
        return JsonResponse({"error": "ต้อง login admin ก่อน"}, status=401)

    from .services.google_sheets import SHEET_CONFIG, write_sheet
    from .services.line_notify import load_schedules

    if request.method == "POST":
        try:
            body = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "JSON ไม่ถูกต้อง"}, status=400)
        incoming = body.get("schedules") or []
        if not isinstance(incoming, list):
            return JsonResponse({"error": "schedules ต้องเป็น list"}, status=400)

        cleaned = []
        for idx, s in enumerate(incoming):
            time_str = str(s.get("time", "") or "").strip()
            if not time_str or ":" not in time_str:
                return JsonResponse({"error": f"แถวที่ {idx+1}: เวลาต้องเป็น HH:MM"}, status=400)
            try:
                hh, mm = time_str.split(":", 1)
                hh, mm = int(hh), int(mm)
                if not (0 <= hh < 24 and 0 <= mm < 60):
                    raise ValueError
                time_str = f"{hh:02d}:{mm:02d}"
            except Exception:
                return JsonResponse({"error": f"แถวที่ {idx+1}: เวลา {time_str} ไม่ถูกต้อง"}, status=400)
            days = str(s.get("days", "*") or "*").strip() or "*"
            sellers_in = s.get("sellers") or ["*"]
            if isinstance(sellers_in, list):
                sellers_str = "*" if sellers_in == ["*"] else ",".join(str(x).strip() for x in sellers_in if str(x).strip())
            else:
                sellers_str = str(sellers_in).strip() or "*"
            test_target = str(s.get("test_target", "") or "").strip()
            enabled = "TRUE" if s.get("enabled") else "FALSE"
            label = str(s.get("label", "") or "").strip()
            include_exec = "TRUE" if s.get("include_executive") else "FALSE"
            # sellers อาจว่างได้ ถ้าส่งเฉพาะผู้บริหาร
            cleaned.append([time_str, days, sellers_str, test_target, enabled, label, include_exec])

        cleaned.sort(key=lambda r: r[0])
        values = [["เวลา", "วัน", "เซลล์", "test_target", "เปิดใช้", "ป้ายชื่อ", "ผู้บริหาร"]] + cleaned
        try:
            write_sheet("schedule_config", values)
        except Exception as e:
            return JsonResponse({"error": f"เขียน sheet ล้มเหลว: {e}"}, status=500)
        return JsonResponse({"ok": True, "saved": len(cleaned)})

    # GET
    schedules = load_schedules()
    cfg = SHEET_CONFIG.get("schedule_config", {})
    sheet_url = f"https://docs.google.com/spreadsheets/d/{cfg.get('spreadsheet_id','')}/edit"
    return JsonResponse({
        "ok": True,
        "schedules": schedules,
        "count": len(schedules),
        "enabled_count": sum(1 for s in schedules if s.get("enabled")),
        "sheet_url": sheet_url,
        "sheet_name": cfg.get("sheet_name", "ตั้งเวลาส่ง"),
    })


@require_http_methods(["GET", "POST"])
def cron_tick(request):
    """Public endpoint สำหรับ external cron ยิงเข้ามาทุกนาที (* * * * *)
    อ่าน schedule sheet → ส่ง LINE Flex ตาม schedule ที่ match เวลาปัจจุบัน (BKK)
    Auth: เหมือน cron_send_line (?secret=xxx, Authorization Bearer, X-Cron-Secret)
    """
    secret_setting = (getattr(settings, "CRON_SECRET", "") or "").strip()
    if not secret_setting:
        return JsonResponse({"error": "CRON_SECRET ยังไม่ได้ตั้งใน env"}, status=500)

    auth_header = request.headers.get("Authorization", "")
    bearer = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else ""
    submitted = (
        bearer
        or request.GET.get("secret", "").strip()
        or request.headers.get("X-Cron-Secret", "").strip()
    )
    if submitted != secret_setting:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    channel_token = (getattr(settings, "LINE_CHANNEL_ACCESS_TOKEN", "") or "").strip()
    if not channel_token:
        return JsonResponse({"error": "LINE_CHANNEL_ACCESS_TOKEN ไม่ได้ตั้ง"}, status=500)

    from .services.line_notify import (
        load_schedules, schedule_matches_now,
        build_seller_pipelines, build_seller_flex, build_overview_flex,
        push_line_message, get_nickname_to_user_id,
    )
    from .services.fetch_dashboard import bangkok_now, fetch_dashboard_data
    from .services.constants import EXECUTIVE_USER_IDS

    now = bangkok_now()
    schedules = load_schedules()
    fired_schedules = [s for s in schedules if schedule_matches_now(s, now)]

    if not fired_schedules:
        return JsonResponse({
            "ok": True, "fired": 0,
            "now": f"{now.hour:02d}:{now.minute:02d}",
            "total_schedules": len(schedules),
        })

    try:
        pipelines = build_seller_pipelines()
        uid_map = get_nickname_to_user_id()
    except Exception as e:
        return JsonResponse({"error": f"ดึงข้อมูลล้มเหลว: {e}"}, status=500)

    # ถ้ามี schedule ใดต้อง include_executive → โหลด full_data (สำหรับ overview)
    needs_overview = any(s.get("include_executive") for s in fired_schedules)
    full_data = None
    if needs_overview:
        try:
            full_data = fetch_dashboard_data()
        except Exception as e:
            full_data = None  # fail soft — ส่ง seller flex ได้ แต่ overview ไม่ได้

    base_url = request.build_absolute_uri("/").rstrip("/")
    all_results = []
    for sched in fired_schedules:
        seller_filter = set(sched["sellers"]) if sched["sellers"] not in (["*"], ["*"]) else None
        if sched["sellers"] == ["*"]:
            seller_filter = None
        if not sched["sellers"]:
            seller_filter = set()  # empty list → skip all sellers (ส่งแค่ exec)
        test_target = sched.get("test_target", "")
        sched_results = []

        # 1) ส่ง per-seller Flex
        for p in pipelines:
            if seller_filter is not None and p["seller"] not in seller_filter:
                continue
            target = test_target if test_target else uid_map.get(p["seller"], "")
            if not target:
                sched_results.append({"recipient": p["seller"], "sent": False, "error": "no user_id"})
                continue
            try:
                flex = build_seller_flex(p, base_url=base_url)
                code, text = push_line_message(target, [flex], channel_token)
                sched_results.append({
                    "recipient": p["seller"],
                    "sent": code == 200,
                    "error": None if code == 200 else f"LINE {code}: {text[:120]}",
                })
            except Exception as e:
                sched_results.append({"recipient": p["seller"], "sent": False, "error": str(e)})

        # 2) ส่ง Overview Flex ให้ผู้บริหาร (ถ้าเปิด include_executive)
        if sched.get("include_executive") and full_data:
            try:
                overview = build_overview_flex(pipelines, full_data, base_url=base_url)
                for exec_uid in EXECUTIVE_USER_IDS:
                    target = test_target if test_target else exec_uid
                    if not target:
                        continue
                    code, text = push_line_message(target, [overview], channel_token)
                    sched_results.append({
                        "recipient": f"🎩 ผู้บริหาร ({exec_uid[:10]}...)",
                        "sent": code == 200,
                        "error": None if code == 200 else f"LINE {code}: {text[:120]}",
                    })
            except Exception as e:
                sched_results.append({"recipient": "🎩 ผู้บริหาร", "sent": False, "error": str(e)})

        all_results.append({
            "schedule": {"time": sched["time"], "label": sched["label"]},
            "sent": sum(1 for r in sched_results if r["sent"]),
            "failed": sum(1 for r in sched_results if not r["sent"]),
            "results": sched_results,
        })

    return JsonResponse({
        "ok": True,
        "now": f"{now.hour:02d}:{now.minute:02d}",
        "fired": len(fired_schedules),
        "results": all_results,
    })


@require_http_methods(["GET", "POST"])
def cron_send_line(request):
    """Public endpoint สำหรับ external cron (cron-job.org / Vercel cron) ยิงเข้ามา

    ป้องกันด้วย CRON_SECRET — ใครไม่มี secret ถูกต้องจะได้ 401
    URL pattern: /api/cron/send_line?secret=xxx[&test=1&target=Uxxx&sellers=A,B]

    Params:
        secret    (required) — ตรงกับ env CRON_SECRET
        test      (optional) — "1" = test mode (ใช้ target แทน user_id จริง)
        target    (optional) — Test target user_id (ต้องมีถ้า test=1)
        sellers   (optional) — comma-separated, default ทุกเซลล์
    """
    secret_setting = (getattr(settings, "CRON_SECRET", "") or "").strip()
    if not secret_setting:
        return JsonResponse({"error": "CRON_SECRET ยังไม่ได้ตั้งใน env"}, status=500)

    # รองรับทั้ง 3 รูปแบบ:
    # 1) Vercel cron auto: Authorization: Bearer <CRON_SECRET>
    # 2) External cron (cron-job.org): ?secret=xxx
    # 3) Custom header: X-Cron-Secret: xxx
    auth_header = request.headers.get("Authorization", "")
    bearer = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else ""
    submitted = (
        bearer
        or request.GET.get("secret", "").strip()
        or request.headers.get("X-Cron-Secret", "").strip()
    )
    if submitted != secret_setting:
        return JsonResponse({"error": "Unauthorized — secret ไม่ถูกต้อง"}, status=401)

    channel_token = (getattr(settings, "LINE_CHANNEL_ACCESS_TOKEN", "") or "").strip()
    if not channel_token:
        return JsonResponse({"error": "LINE_CHANNEL_ACCESS_TOKEN ไม่ได้ตั้ง"}, status=500)

    from .services.line_notify import (
        build_seller_pipelines, build_seller_flex,
        push_line_message, get_nickname_to_user_id,
    )

    test_mode = request.GET.get("test") in ("1", "true", "yes")
    target_user_id = (request.GET.get("target") or "").strip()
    only_sellers_raw = (request.GET.get("sellers") or "").strip()
    only_sellers = [s.strip() for s in only_sellers_raw.split(",") if s.strip()] if only_sellers_raw else None

    if test_mode and not target_user_id:
        return JsonResponse({"error": "test=1 ต้องระบุ target ด้วย"}, status=400)

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
            results.append({"seller": seller, "sent": False, "error": "ไม่มี user_id"})
            continue
        try:
            flex = build_seller_flex(p, base_url=base_url)
            code, text = push_line_message(target, [flex], channel_token)
            if code == 200:
                results.append({"seller": seller, "sent": True})
            else:
                results.append({"seller": seller, "sent": False, "error": f"LINE {code}: {text[:120]}"})
        except Exception as e:
            results.append({"seller": seller, "sent": False, "error": str(e)})

    sent_count = sum(1 for r in results if r["sent"])
    return JsonResponse({
        "ok": True,
        "test_mode": test_mode,
        "count": len(results),
        "sent": sent_count,
        "failed": len(results) - sent_count,
        "results": results,
    })


@require_GET
def admin_diagnostics(request):
    """Admin-only — สรุปการกรองข้อมูล + เคสที่หลุดจาก dashboard

    Returns:
        leads: total / thisYear / prevYear / noDate / badDate (+ examples)
        sales: total / kept / dropNoSeq / dropNoStatus / statusBreakdown (+ examples)
    """
    user = _session_user(request)
    if not user or user.get("position") != "admin":
        return JsonResponse({"error": "ต้อง login admin ก่อน"}, status=401)

    from .services.google_sheets import (
        fetch_sheet, fetch_leads_dedup, get_leads_dedup_stats, cell,
        LEADS_COL as L, SALES_COL as S,
    )
    from .services.fetch_dashboard import parse_date, bangkok_now

    try:
        leads = fetch_leads_dedup()  # union monthly tabs + dedupe (latest wins)
        dedup_stats = get_leads_dedup_stats()
        sales = fetch_sheet("sales_reports")
    except Exception as e:
        return JsonResponse({"error": f"fetch sheet ล้มเหลว: {e}"}, status=500)

    cur_year = bangkok_now().year

    # ── Leads diagnostic ──
    lead_total = len(leads)
    lead_this_year = 0
    lead_prev_year = 0
    lead_no_date = 0
    lead_bad_date = 0
    bad_date_examples = []
    no_date_with_data = []  # leads ที่ไม่มีวันที่ แต่มีข้อมูลอื่น (อาจเป็นเคสที่ user ลืมกรอกวันที่)

    for r in leads:
        date_str = cell(r, L.received_date)
        if not date_str:
            # ดูว่ามีข้อมูลอื่นมั้ย
            has_other = bool(cell(r, L.phone) or cell(r, L.lead_code)
                             or cell(r, L.sales_rep) or cell(r, L.car_inquiry)
                             or cell(r, L.car_formula))
            if has_other:
                if len(no_date_with_data) < 10:
                    no_date_with_data.append({
                        "code": cell(r, L.lead_code) or "-",
                        "seller": cell(r, L.sales_rep) or "-",
                        "phone": cell(r, L.phone) or "-",
                        "car": cell(r, L.car_inquiry) or cell(r, L.car_formula) or "-",
                    })
            lead_no_date += 1
            continue
        d = parse_date(date_str)
        if not d:
            lead_bad_date += 1
            if len(bad_date_examples) < 10:
                bad_date_examples.append({
                    "code": cell(r, L.lead_code) or "-",
                    "seller": cell(r, L.sales_rep) or "-",
                    "phone": cell(r, L.phone) or "-",
                    "rawDate": date_str,
                })
            continue
        if d.year == cur_year:
            lead_this_year += 1
        else:
            lead_prev_year += 1

    # ── Sales reports diagnostic ──
    sales_total = len(sales)
    sales_kept = 0
    sales_drop_no_seq = 0
    sales_drop_invalid_seq = 0
    sales_drop_no_status = 0
    no_status_examples = []
    invalid_seq_examples = []
    from collections import Counter
    status_breakdown = Counter()

    for r in sales:
        seq = cell(r, S.order_num)
        if not seq or seq == "ลำดับ":
            sales_drop_no_seq += 1
            continue
        try:
            int(seq)
        except ValueError:
            sales_drop_invalid_seq += 1
            if len(invalid_seq_examples) < 5:
                invalid_seq_examples.append({
                    "seq": seq,
                    "seller": cell(r, S.sales_rep) or "-",
                    "customer": cell(r, S.customer_name) or "-",
                })
            continue
        status = cell(r, S.status)
        if not status:
            sales_drop_no_status += 1
            if len(no_status_examples) < 10:
                no_status_examples.append({
                    "seq": seq,
                    "seller": cell(r, S.sales_rep) or "-",
                    "customer": cell(r, S.customer_name) or "-",
                    "date": cell(r, S.date) or "-",
                    "car": cell(r, S.car_detail) or "-",
                })
            continue
        # Clean status (strip (ซื้อสด))
        clean = status.replace(" (ซื้อสด)", "").strip()
        status_breakdown[clean] += 1
        sales_kept += 1

    # ── 🔍 Released breakdown — แจกแจง "ปล่อย" ทุกเคสตามเซลล์ (debug ว่าเคสหายอยู่ตรงไหน) ──
    from .services.constants import normalize_seller, ALL_SELLERS
    released_by_seller_raw = {}     # ชื่อ raw จาก sheet (ก่อน normalize)
    released_by_seller_norm = {}    # ชื่อหลัง normalize_seller()
    released_total = 0
    known_set = set(ALL_SELLERS) | {"ADMIN"}
    for r in sales:
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
        clean = status.replace(" (ซื้อสด)", "").strip()
        if clean != "ปล่อย":
            continue
        released_total += 1
        seller_raw = cell(r, S.sales_rep).strip()
        seller_clean = seller_raw.replace("ชื่อเซลล์ ", "").replace("ชื่อเซลล์", "").strip()
        seller_norm = normalize_seller(seller_clean) or "(ว่าง)"
        released_by_seller_raw[seller_raw or "(ว่าง)"] = released_by_seller_raw.get(seller_raw or "(ว่าง)", 0) + 1
        released_by_seller_norm[seller_norm] = released_by_seller_norm.get(seller_norm, 0) + 1
    # แยก: เซลล์ที่อยู่ใน ALL_SELLERS vs เซลล์ที่ไม่อยู่ (orphan)
    released_known = {k: v for k, v in released_by_seller_norm.items() if k in known_set}
    released_orphan = {k: v for k, v in released_by_seller_norm.items() if k not in known_set}
    released_known_sum = sum(released_known.values())
    released_orphan_sum = sum(released_orphan.values())

    # ── เคส "รอปล่อย" detail (admin อาจสับสนกับ "ปล่อย") ──
    waiting_release_cases = []
    for r in sales:
        seq = cell(r, S.order_num)
        if not seq or seq == "ลำดับ":
            continue
        try:
            int(seq)
        except ValueError:
            continue
        status = cell(r, S.status)
        clean = status.replace(" (ซื้อสด)", "").strip()
        if clean == "รอปล่อย":
            waiting_release_cases.append({
                "seller": cell(r, S.sales_rep) or "-",
                "customer": cell(r, S.customer_name) or "-",
                "car": cell(r, S.car_detail) or "-",
                "date": cell(r, S.date) or "-",
                "price": cell(r, S.sale_price) or "-",
            })
            if len(waiting_release_cases) >= 50:
                break

    return JsonResponse({
        "ok": True,
        "generatedAt": bangkok_now().isoformat(),
        "leads": {
            "total": lead_total,
            "thisYear": lead_this_year,
            "prevYear": lead_prev_year,
            "noDate": lead_no_date,
            "badDate": lead_bad_date,
            "badDateExamples": bad_date_examples,
            "noDateWithData": no_date_with_data,
            "dedup": dedup_stats,
        },
        "sales": {
            "total": sales_total,
            "kept": sales_kept,
            "dropNoSeq": sales_drop_no_seq,
            "dropInvalidSeq": sales_drop_invalid_seq,
            "dropNoStatus": sales_drop_no_status,
            "noStatusExamples": no_status_examples,
            "invalidSeqExamples": invalid_seq_examples,
            "statusBreakdown": dict(status_breakdown),
            "waitingReleaseCases": waiting_release_cases,
            "waitingReleaseTotal": status_breakdown.get("รอปล่อย", 0),
        },
        "released": {
            "total": released_total,
            "knownSum": released_known_sum,        # sum ของเซลล์ที่อยู่ใน ALL_SELLERS
            "orphanSum": released_orphan_sum,      # sum ของเซลล์ที่ไม่อยู่ (เป็น orphan)
            "gap": released_total - released_known_sum - released_orphan_sum,
            "bySellerNormalized": dict(sorted(released_by_seller_norm.items(), key=lambda x: -x[1])),
            "bySellerRaw": dict(sorted(released_by_seller_raw.items(), key=lambda x: -x[1])),
            "knownSellers": dict(sorted(released_known.items(), key=lambda x: -x[1])),
            "orphanSellers": dict(sorted(released_orphan.items(), key=lambda x: -x[1])),
        },
        "currentYear": cur_year,
    }, json_dumps_params={"ensure_ascii": False})


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

    # ── ดึง lead ของเซลล์คนนี้ — แสดงทุกเคส (รวม คืนเคส/ยกเลิก/จ่ายใหม่) ──
    # เคส junk ยังโผล่ใน lead list + นับใน KPI "หลีดที่รับ"/"โทรแล้ว"/"อัพเดท..."
    # (frontend seller.html ตัด junk ออกจากแค่ KPI "ยังไม่โทร" + "ต้องโทรต่อ" + banner)
    #
    # ใช้ fetch_leads_by_month_tabs — อ่านจาก monthly tab โดยตรง + filter ให้แต่ละ row
    # อยู่ใน tab ของเดือนตัวเองจริง. เลขจะตรงกับการนับใน Google Sheet (~2,585 เคส พ.ค. 2026)
    # ที่ admin คาดหวัง — ตรงข้ามกับ fetch_sheet("leads")/fetch_leads_dedup ที่มี dup + orphan
    from .services.google_sheets import fetch_leads_by_month_tabs, cell, cell_num, LEADS_COL as L
    from .services.constants import normalize_seller
    from .services.fetch_dashboard import is_this_year
    import re as _re

    raw_leads = fetch_leads_by_month_tabs()  # monthly tabs only, filter date matches tab month
    my_leads = []
    for r in raw_leads:
        if normalize_seller(cell(r, L.sales_rep)) != seller_name:
            continue
        date_str = cell(r, L.received_date)
        if not is_this_year(date_str):
            continue
        note_raw = cell(r, L.fill_sheet_note) or ""
        note = _re.sub(r"^\d{4,5}\s*", "", note_raw)
        my_leads.append({
            "code": cell(r, L.lead_code),
            "phone": cell(r, L.phone),
            "channel": cell(r, L.channel),
            "leadType": cell(r, L.type),
            "car": cell(r, L.car_inquiry) or cell(r, L.car_formula),
            "dateIn": date_str,
            "timeIn": cell(r, L.time),
            "callProof": cell(r, L.call_proof),
            "updateCount": int(cell_num(r, L.update_count)),
            "adminStatus": cell(r, L.admin_status),
            "salesStatus": cell(r, L.sales_status),
            "lastUpdate": cell(r, L.last_updated_at),
            "note": note,
            "profile": cell(r, L.customer_profile),
        })

    # ── daily + monthly ของเซลล์คนนี้ (ใช้ตัวจาก aggregator ตรงๆ — รวม junk) ──
    my_daily = data.get("dailyBySeller", {}).get(seller_name, {})
    my_monthly = {}
    for m_str, m_data in (data.get("monthlySummary") or {}).items():
        ss = (m_data.get("sellers") or {}).get(seller_name) or {}
        my_monthly[m_str] = {
            "lead": ss.get("lead", 0),
            "leadNormal": ss.get("leadNormal", 0),
            "leadRJ": ss.get("leadRJ", 0),
            "follow": ss.get("follow", 0),
            "vacant": ss.get("vacant", 0),
            "done": ss.get("done", 0),
            "booking": ss.get("booking", 0),
            "dealValue": ss.get("dealValue", 0),
        }

    filtered = {
        "meta": data.get("meta", {}),
        "seller": my_seller,
        "today": today_my,
        "leads": my_leads,
        "followCases": my_follows,
        "bookingCases": my_bookings,
        "mustCallCount": must_call_count,
        "daily": my_daily,
        "monthly": my_monthly,
    }

    constants = {
        "UPD_TGT": UPD_TGT,
        "STATUS_COLOR": STATUS_COLOR,
        "STATUS_ORDER": STATUS_ORDER,
        "TEAM_COLORS": TEAM_COLORS,
        "TEAM_NAMES": TEAM_NAMES,
        "LT_COLORS": LT_COLORS,
        "MONTHS_SHORT": MONTHS_SHORT,
        "MONTHS_FULL": MONTHS_FULL,
    }

    return render(request, "dashboard/seller.html", {
        "error": None,
        "seller": seller_name,
        "data_json": json.dumps(filtered, ensure_ascii=False, default=str),
        "constants_json": json.dumps(constants, ensure_ascii=False),
    })
