"""Dashboard views — ported from Next.js API routes + pages."""
import json
import urllib.parse

from django.conf import settings
from django.http import JsonResponse, HttpResponseRedirect
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from .services.fetch_dashboard import fetch_dashboard_data
from .services.google_sheets import fetch_sheet, cell, EMPLOYEE_COL as EM
from .services.constants import (
    UPD_TGT, PAGE_SIZE, STATUS_COLOR, STATUS_ORDER,
    TEAM_COLORS, TEAM_NAMES, LT_COLORS, MONTHS_SHORT, MONTHS_FULL,
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


# position ที่เห็นข้อมูลรวมทั้งหมด (admin + ผู้บริหาร) — เซลล์ทั่วไปไม่อยู่ในนี้
EXEC_POSITIONS = {"executive", "ผู้บริหาร", "manager", "exec", "admin"}


def _can_view_all(user) -> bool:
    """True ถ้าเป็น admin/ผู้บริหาร (เห็น dashboard รวม). เซลล์ = False."""
    return bool(user) and (user.get("position") or "").strip().lower() in EXEC_POSITIONS


def _is_admin(user) -> bool:
    return bool(user) and (user.get("position") or "").strip().lower() == "admin"


def _save_to_supabase(table, row):
    """เก็บ row ลง Supabase (best-effort). คืน id ถ้าสำเร็จ, None ถ้าล่ม/ยังไม่ตั้งค่า."""
    try:
        from .services.supabase_client import is_configured, insert_row
        if not is_configured():
            return None
        saved = insert_row(table, row)
        if saved and isinstance(saved, list):
            return saved[0].get("id")
    except Exception:
        pass
    return None


@ensure_csrf_cookie
@require_GET
def dashboard_page(request):
    """Main dashboard — ต้อง login (admin/ผู้บริหารเท่านั้น).
    เซลล์ทั่วไป → redirect ไปหน้าส่วนตัว /me/ (กันเห็น data รวมของทุกคนผ่าน DevTools).
    """
    user = _session_user(request)
    if not user:
        return HttpResponseRedirect("/login/?next=/dashboard/")
    if not _can_view_all(user):
        return HttpResponseRedirect("/me/")

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
    """GET /api/dashboard — JSON data รวมทุกเซลล์ → ต้อง login admin/ผู้บริหาร."""
    if not _can_view_all(_session_user(request)):
        return JsonResponse({"error": "ต้อง login ผู้บริหาร/admin ก่อน"}, status=401)
    try:
        data = fetch_dashboard_data()
        return JsonResponse(data, json_dumps_params={"ensure_ascii": False, "default": str})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@ensure_csrf_cookie
@require_GET
def admin_page(request):
    """/admin/ — alias ของ /dashboard/ ใช้ template เดียวกัน (index.html)
    ต้อง login เป็น admin (แอดมินสูงสุด) เท่านั้น.
    """
    user = _session_user(request)
    if not user or not _is_admin(user):
        return HttpResponseRedirect("/login/?next=/admin/")

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
        "UPD_TGT": UPD_TGT, "PAGE_SIZE": PAGE_SIZE,
        "STATUS_COLOR": STATUS_COLOR, "STATUS_ORDER": STATUS_ORDER,
        "TEAM_COLORS": TEAM_COLORS, "TEAM_NAMES": TEAM_NAMES,
        "LT_COLORS": LT_COLORS, "MONTHS_SHORT": MONTHS_SHORT, "MONTHS_FULL": MONTHS_FULL,
    }

    return render(request, "dashboard/index.html", {
        "data_json": json.dumps(data, ensure_ascii=False, default=str),
        "constants_json": json.dumps(constants, ensure_ascii=False),
        "session_user_json": json.dumps(user),
        "error": None,
        "is_admin_page": True,  # frontend ใช้ flag นี้ตัดสินใจ UI
    })


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
    line_token = (request.POST.get("token") or "").strip()
    email = (request.POST.get("email") or "").strip()

    # ทาง 0: สมาชิก (email + password) ผ่าน Supabase — เส้นทางหลักของระบบใหม่
    if email:
        from .services.auth_users import is_enabled, verify_login, session_payload
        if not is_enabled():
            err = "ระบบสมาชิกยังไม่พร้อม (ยังไม่ได้ตั้งค่า Supabase)"
            if is_ajax:
                return JsonResponse({"ok": False, "error": err}, status=503)
            return render(request, "dashboard/login.html", {"next": next_url, "error": err})
        try:
            user, err = verify_login(email, password)
        except Exception as e:
            user, err = None, f"ตรวจสอบบัญชีล้มเหลว: {e}"
        if user:
            payload = session_payload(user)
            request.session["oxlet_user"] = payload
            request.session.set_expiry(60 * 60 * 24 * 30)
            if payload["position"] in EXEC_POSITIONS:
                target = next_url if next_url and next_url not in ("/me/",) else "/dashboard/"
            else:
                target = "/me/"
            if is_ajax:
                return JsonResponse({"ok": True, "next": target})
            return HttpResponseRedirect(target)
        if is_ajax:
            return JsonResponse({"ok": False, "error": err}, status=401)
        return render(request, "dashboard/login.html", {"next": next_url, "error": err})

    # ทาง 1: Admin login (ชื่อ + รหัสผ่าน)
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

    # ทาง 2: LINE user_id (ผู้บริหาร/เซลล์) → ตรวจ employees sheet + set session
    if line_token:
        try:
            employees = fetch_sheet("employees")
            for r in employees:
                if cell(r, EM.user_id) == line_token:
                    position = (cell(r, EM.position) or "").strip().lower()
                    nickname = cell(r, EM.nickname)
                    display = cell(r, EM.display_name)
                    # ได้สิทธิ์ admin จาก 2 ทาง (ยังนับเป็นเซลล์ปกติในสถิติ):
                    #  1) LINE user_id อยู่ในชีต "ตั้งค่าแอดมิน" (เทเลเซลล์/ออฟฟิศ ที่ไม่ใช่เซลล์)
                    #  2) เป็นเซลล์ใน TEAMS ที่ถูกติ๊ก "แอดมิน" ในชีตตั้งค่าเซลล์
                    from .services.constants import (
                        normalize_seller, ADMIN_SELLERS, ADMIN_USER_IDS,
                        refresh_from_sheet, load_admin_user_ids,
                    )
                    refresh_from_sheet()
                    load_admin_user_ids()
                    if line_token in ADMIN_USER_IDS or normalize_seller((nickname or "").strip()) in ADMIN_SELLERS:
                        position = "admin"
                    request.session["oxlet_user"] = {
                        "user_id": line_token,
                        "nickname": nickname,
                        "display_name": display,
                        "position": position or "seller",
                        "seller_name": (nickname or "").strip(),
                    }
                    request.session.set_expiry(60 * 60 * 24 * 30)
                    # เซลล์ทั่วไป → /s/<user_id>/, ผู้บริหาร → /dashboard/
                    if position in ("executive", "ผู้บริหาร", "manager", "exec", "admin"):
                        target = next_url if next_url != "/dashboard/" else "/dashboard/"
                    else:
                        target = f"/s/{line_token}/"
                    if is_ajax:
                        return JsonResponse({"ok": True, "next": target})
                    return HttpResponseRedirect(target)
        except Exception as e:
            err = f"ตรวจ user_id ล้มเหลว: {e}"
            if is_ajax:
                return JsonResponse({"ok": False, "error": err}, status=500)
            return render(request, "dashboard/login.html", {"next": next_url, "error": err})

    error = "ข้อมูลไม่ถูกต้อง" if (username or password or line_token) else "กรุณากรอกข้อมูล"
    if is_ajax:
        return JsonResponse({"ok": False, "error": error}, status=401)
    return render(request, "dashboard/login.html", {"next": next_url, "error": error})


@require_GET
def logout_view(request):
    """ออกจากระบบ — กลับไปหน้า login (dashboard ต้อง login แล้ว)"""
    request.session.flush()
    resp = HttpResponseRedirect("/login/")
    resp.delete_cookie("oxlet_employee")
    return resp


@ensure_csrf_cookie
@require_http_methods(["GET", "POST"])
def register_view(request):
    """หน้าสมัครสมาชิก — /register/
    GET → ฟอร์มสมัคร. POST → สร้างบัญชี pending ใน Supabase + ส่งเมล approve ไปผู้ดูแล.
    บัญชีใช้งานได้หลังผู้ดูแลกดลิงก์ approve ในเมล oxletauto@gmail.com.
    """
    from .services.auth_users import is_enabled, create_pending_user, ROLE_LABELS, VALID_ROLES, make_action_token

    ctx_roles = ROLE_LABELS  # {"seller":"เซลล์", "executive":"ผู้บริหาร", "admin":"แอดมินสูงสุด"}

    if request.method == "GET":
        return render(request, "dashboard/register.html", {
            "roles": ctx_roles, "error": None, "done": False, "form": {},
        })

    # POST
    form = {
        "full_name": (request.POST.get("full_name") or "").strip(),
        "nickname": (request.POST.get("nickname") or "").strip(),
        "email": (request.POST.get("email") or "").strip().lower(),
        "role": (request.POST.get("role") or "").strip().lower(),
        "seller_name": (request.POST.get("seller_name") or "").strip(),
    }
    password = request.POST.get("password") or ""
    password2 = request.POST.get("password2") or ""

    def _err(msg):
        return render(request, "dashboard/register.html", {
            "roles": ctx_roles, "error": msg, "done": False, "form": form,
        })

    if not is_enabled():
        return _err("ระบบสมัครสมาชิกยังไม่พร้อม (ยังไม่ได้ตั้งค่า Supabase)")
    if not form["full_name"] or not form["email"] or not password or not form["role"]:
        return _err("กรุณากรอกข้อมูลให้ครบ (ชื่อ / อีเมล / รหัสผ่าน / บทบาท)")
    if "@" not in form["email"] or "." not in form["email"].split("@")[-1]:
        return _err("รูปแบบอีเมลไม่ถูกต้อง")
    if len(password) < 6:
        return _err("รหัสผ่านต้องยาวอย่างน้อย 6 ตัวอักษร")
    if password != password2:
        return _err("รหัสผ่านทั้งสองช่องไม่ตรงกัน")
    if form["role"] not in VALID_ROLES:
        return _err("กรุณาเลือกบทบาทให้ถูกต้อง")

    nickname = form["nickname"] or form["full_name"]
    seller_name = form["seller_name"] or nickname if form["role"] == "seller" else form["seller_name"]

    try:
        user = create_pending_user(
            email=form["email"], password=password, full_name=form["full_name"],
            nickname=nickname, role=form["role"], seller_name=seller_name,
        )
    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        return _err(f"สร้างบัญชีไม่สำเร็จ: {e}")

    # สร้างลิงก์ approve/reject (signed token) → ส่งเข้าเมลผู้ดูแล
    base = (getattr(settings, "SITE_URL", "") or "").rstrip("/") or request.build_absolute_uri("/").rstrip("/")
    approve_url = f"{base}/account/review/?t={make_action_token(user['id'], 'approve')}"
    reject_url = f"{base}/account/review/?t={make_action_token(user['id'], 'reject')}"

    email_ok, email_err = True, ""
    try:
        from .services.email_send import send_approval_request
        send_approval_request(user, approve_url, reject_url)
    except Exception as e:
        email_ok, email_err = False, str(e)

    return render(request, "dashboard/register.html", {
        "roles": ctx_roles, "error": None, "done": True, "form": {},
        "email_ok": email_ok, "email_err": email_err,
        "notify_email": getattr(settings, "APPROVAL_NOTIFY_EMAIL", ""),
    })


@ensure_csrf_cookie
@require_http_methods(["GET", "POST"])
def account_review(request):
    """หน้า approve/reject บัญชี — /account/review/?t=<signed_token> (ลิงก์จากเมล).
    GET = แสดงหน้ายืนยัน (ไม่เปลี่ยนสถานะ — กันลิงก์ถูก prefetch แล้ว approve เอง).
    POST = ทำรายการจริง (อนุมัติ → active, ปฏิเสธ → rejected).
    """
    from django.core.signing import BadSignature, SignatureExpired
    from .services.auth_users import load_action_token, get_user_by_id, set_status, role_label

    token = (request.GET.get("t") or request.POST.get("t") or "").strip()

    def _page(state, **extra):
        return render(request, "dashboard/account_review.html",
                      {"state": state, "token": token, **extra})

    if not token:
        return _page("invalid")
    try:
        uid, action = load_action_token(token)
    except SignatureExpired:
        return _page("expired")
    except (BadSignature, Exception):
        return _page("invalid")

    if action not in ("approve", "reject"):
        return _page("invalid")

    try:
        user = get_user_by_id(uid)
    except Exception as e:
        return _page("error", error=str(e))
    if not user:
        return _page("invalid")

    status = (user.get("status") or "").lower()
    view_ctx = {"user": user, "action": action, "role_label": role_label(user.get("role"))}

    # ทำรายการแล้ว (active/rejected) → ไม่ให้ทำซ้ำ
    if status != "pending":
        return _page("already", **view_ctx)

    if request.method == "GET":
        return _page("confirm", **view_ctx)

    # POST → ดำเนินการ
    new_status = "active" if action == "approve" else "rejected"
    try:
        set_status(uid, new_status)
    except Exception as e:
        return _page("error", error=str(e), **view_ctx)
    return _page("done", **view_ctx)


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

    from .services.constants import refresh_from_sheet, TEAMS, TARGETS, ADMIN_SELLERS
    from .services.google_sheets import SHEET_CONFIG, write_sheet
    from .services.line_notify import get_nickname_to_user_id

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
            is_admin = bool(s.get("is_admin"))
            cleaned.append([name, team, target, is_admin])

        if not cleaned:
            return JsonResponse({"error": "ต้องมีอย่างน้อย 1 เซลล์"}, status=400)

        # เรียง by team, name แล้วใส่ header (คอลัมน์ D = "แอดมิน": TRUE/ว่าง)
        cleaned.sort(key=lambda r: (r[1], r[0]))
        values = [["ชื่อเล่น", "ทีม", "เป้า", "แอดมิน"]] + [
            [name, team, target, ("TRUE" if is_admin else "")]
            for name, team, target, is_admin in cleaned
        ]

        try:
            write_sheet("sellers_config", values)
        except Exception as e:
            return JsonResponse({"error": f"เขียน sheet ล้มเหลว: {e}"}, status=500)

        # โหลด config ใหม่ทันทีให้ dashboard เห็นค่าใหม่
        refresh_from_sheet()
        return JsonResponse({"ok": True, "saved": len(cleaned)})

    # GET — ส่ง user_id (จาก employees sheet) แทน token เพื่อให้ admin เห็น URL ส่วนตัวของเซลล์ใน UI
    loaded_from_sheet = refresh_from_sheet()
    cfg = SHEET_CONFIG.get("sellers_config", {})
    sheet_url = f"https://docs.google.com/spreadsheets/d/{cfg.get('spreadsheet_id','')}/edit"

    try:
        uid_map = get_nickname_to_user_id()
    except Exception:
        uid_map = {}

    sellers = []
    for tid, members in sorted(TEAMS.items()):
        for name in members:
            sellers.append({
                "name": name,
                "team": tid,
                "target": TARGETS.get(name, 0),
                "user_id": uid_map.get(name, ""),  # LINE user_id = URL /s/<user_id>/
                "is_admin": name in ADMIN_SELLERS,  # ติ๊กแล้ว → login เป็นแอดมิน
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
def admin_admin_config(request):
    """Admin endpoint — จัดการ "ไอดีแอดมิน" (เทเลเซลล์/ออฟฟิศ ที่ไม่ใช่เซลล์ใน TEAMS)
    GET  → รายชื่อแอดมินปัจจุบัน + รายชื่อ employees (ไว้เลือกใน UI)
    POST body: {"admins":[{"user_id":"U...","name":"เฟิร์น","note":""},...]} → เขียนชีต "ตั้งค่าแอดมิน"
    """
    user = _session_user(request)
    if not user or user.get("position") != "admin":
        return JsonResponse({"error": "ต้อง login admin ก่อน"}, status=401)

    from .services.google_sheets import (
        SHEET_CONFIG, write_sheet, fetch_sheet, cell,
        ADMIN_CONFIG_COL as AC, EMPLOYEE_COL as EM,
    )
    from .services.constants import load_admin_user_ids

    if request.method == "POST":
        try:
            body = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "JSON ไม่ถูกต้อง"}, status=400)

        incoming = body.get("admins") or []
        if not isinstance(incoming, list):
            return JsonResponse({"error": "admins ต้องเป็น list"}, status=400)

        cleaned = []
        seen = set()
        for idx, a in enumerate(incoming):
            uid = str(a.get("user_id", "") or "").strip()
            if not uid:
                continue
            if not uid.startswith("U") or len(uid) < 20:
                return JsonResponse({"error": f"แถวที่ {idx+1}: LINE user_id ไม่ถูกต้อง (ต้องขึ้นต้น U)"}, status=400)
            if uid in seen:
                continue
            seen.add(uid)
            cleaned.append([uid, str(a.get("name", "") or "").strip(), str(a.get("note", "") or "").strip()])

        values = [["LINE user_id", "ชื่อ", "หมายเหตุ"]] + cleaned
        try:
            write_sheet("admin_config", values)
        except Exception as e:
            return JsonResponse({"error": f"เขียน sheet ล้มเหลว: {e}"}, status=500)

        load_admin_user_ids()  # โหลดใหม่ทันที
        return JsonResponse({"ok": True, "saved": len(cleaned)})

    # GET
    cfg = SHEET_CONFIG.get("admin_config", {})
    try:
        rows = fetch_sheet("admin_config")
    except Exception:
        rows = []
    admins = []
    for r in rows:
        uid = cell(r, AC.user_id).strip()
        if not uid.startswith("U") or len(uid) < 20:
            continue
        admins.append({
            "user_id": uid,
            "name": cell(r, AC.name).strip(),
            "note": cell(r, AC.note).strip(),
        })

    # employees list — ไว้ให้ UI เลือกคนแทนการพิมพ์ user_id เอง
    employees = []
    try:
        for r in fetch_sheet("employees"):
            uid = cell(r, EM.user_id).strip()
            if not uid.startswith("U") or len(uid) < 20:
                continue
            employees.append({
                "user_id": uid,
                "nickname": cell(r, EM.nickname).strip(),
                "display": cell(r, EM.display_name).strip(),
                "dept": cell(r, EM.position).strip(),
            })
    except Exception:
        pass

    return JsonResponse({
        "ok": True,
        "admins": admins,
        "employees": employees,
        "sheet_url": f"https://docs.google.com/spreadsheets/d/{cfg.get('spreadsheet_id','')}/edit",
        "sheet_name": cfg.get("sheet_name", "ตั้งค่าแอดมิน"),
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
        # ไม่มี LINE ต้องส่งนาทีนี้ → ใช้จังหวะนี้รีเฟรช dashboard (sync + pre-compute) แบบ throttle ~5 นาที
        # → cron tick (1 นาที) ตัวเดียวดูแลทั้ง LINE + ความเร็ว dashboard ไม่ต้องสร้าง cron แยก
        refreshed = False
        if getattr(settings, "USE_SUPABASE", False):
            try:
                from .services.supabase_client import (
                    is_configured, get_dashboard_cache_age, sync_all_sheets_to_supabase,
                )
                if is_configured():
                    age = get_dashboard_cache_age()
                    if age is None or age > 270:   # > ~4.5 นาที → รีเฟรช
                        sync_all_sheets_to_supabase()
                        from .services.fetch_dashboard import precompute_dashboard, _dash_cache
                        _dash_cache["data"] = None
                        precompute_dashboard()
                        refreshed = True
            except Exception:
                pass   # best-effort
        return JsonResponse({
            "ok": True, "fired": 0,
            "now": f"{now.hour:02d}:{now.minute:02d}",
            "total_schedules": len(schedules),
            "dashboard_refreshed": refreshed,
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
def cron_sync(request):
    """Public (?secret=xxx) — sync Google Sheets → Supabase (sheet_cache).
    ให้ external cron ยิงทุก 1 นาที = realtime (วิธี A). Auth เหมือน cron_tick.
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

    from .services.supabase_client import is_configured, sync_all_sheets_to_supabase
    if not is_configured():
        return JsonResponse({"error": "ยังไม่ได้ตั้ง SUPABASE_URL / SUPABASE_SECRET_KEY"}, status=500)
    try:
        result = sync_all_sheets_to_supabase()
    except Exception as e:
        return JsonResponse({"error": f"sync ล้มเหลว: {e}"}, status=500)

    # หลัง sync mirror เสร็จ → คำนวณ dashboard ใหม่ + เก็บผล (pre-compute)
    # ทำให้คนเข้าเว็บอ่านผลสำเร็จรูป ไม่ต้องคำนวณ 15k lead สดเอง
    precomputed = False
    try:
        from .services.fetch_dashboard import _dash_cache, precompute_dashboard
        _dash_cache["data"] = None   # บังคับคำนวณจาก mirror ที่เพิ่ง sync
        precompute_dashboard()
        precomputed = True
    except Exception as e:
        result["precompute_error"] = str(e)[:200]
    return JsonResponse({"ok": True, "synced": result, "precomputed": precomputed})


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


@require_http_methods(["POST"])
def admin_export_leadscore(request):
    """Admin endpoint — เขียน Diligence Score รายเซลล์ลง sheet 'leadscore'
    POST body (optional): {"month": 5, "year": 2026}
    ถ้าไม่ระบุ ใช้เดือนปัจจุบัน
    """
    user = _session_user(request)
    if not user or user.get("position") != "admin":
        return JsonResponse({"error": "ต้อง login admin ก่อน"}, status=401)

    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        body = {}

    month = body.get("month")
    year = body.get("year")
    try:
        month = int(month) if month else None
        year = int(year) if year else None
    except (ValueError, TypeError):
        return JsonResponse({"error": "month/year ต้องเป็นจำนวนเต็ม"}, status=400)

    try:
        from .services.fetch_dashboard import export_leadscore_to_sheet
        result = export_leadscore_to_sheet(month, year)
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({"error": f"export ล้มเหลว: {e}"}, status=500)


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


@csrf_exempt
@require_http_methods(["POST"])
def insights_seller(request):
    """AI วิเคราะห์เซลล์ — body {seller, stats}. คืน narrative จาก Gemini (cache 30 นาที)."""
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON ไม่ถูกต้อง"}, status=400)
    seller = (body.get("seller") or "").strip()
    stats = (body.get("stats") or "").strip()
    if not seller or not stats:
        return JsonResponse({"error": "ต้องมี seller + stats"}, status=400)
    from .services.gemini_insights import analyze_seller
    try:
        text = analyze_seller(seller, stats)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=502)
    return JsonResponse({"ok": True, "analysis": text})


@csrf_exempt
@require_http_methods(["POST"])
def insights_forecast(request):
    """AI อธิบายแนวโน้มยอดขาย — body {summary}. คืน narrative จาก Gemini."""
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON ไม่ถูกต้อง"}, status=400)
    summary = (body.get("summary") or "").strip()
    if not summary:
        return JsonResponse({"error": "ต้องมี summary"}, status=400)
    from .services.gemini_insights import forecast_narrative
    try:
        text = forecast_narrative(summary)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=502)
    return JsonResponse({"ok": True, "narrative": text})


@require_GET
def admin_sheets_status(request):
    """Admin — แสดงแหล่งข้อมูล (Google Sheets) ที่ระบบใช้ + สถานะเชื่อมต่อ + tab รายเดือน (สด)."""
    user = _session_user(request)
    if not user or user.get("position") != "admin":
        return JsonResponse({"error": "ต้อง login admin ก่อน"}, status=401)

    import concurrent.futures
    import requests as _rq
    from google.auth.transport.requests import Request as AuthRequest
    from .services.google_sheets import (
        SHEET_CONFIG, fetch_sheet, _get_credentials, SHEETS_API, _THAI_MONTHS,
        load_sheet_config_overrides,
    )

    from .services.supabase_client import is_configured as _sb_configured

    # ดึง override ล่าสุดจาก Supabase ก่อน (ถ้า admin เคยย้ายไฟล์ชีต)
    load_sheet_config_overrides(force=True)

    # 6 แหล่งข้อมูลหลัก (ตรงกับ node ใน n8n)
    sources_def = [
        ("leads", "📋 Lead", "รายการ Lead ทั้งหมด (รวม sheet + tab รายเดือน)"),
        ("sales_reports", "💰 รายงานฝ่ายขาย", "ยอดขาย / สถานะจอง-ปล่อย"),
        ("bookings", "📝 จอง", "รายการจอง"),
        ("live_sessions", "📡 ไลฟ์สด", "เซสชั่นไลฟ์"),
        ("live_followups", "🎬 ติดตามไลฟ์สด", "คลิป follow-up"),
        ("employees", "👤 พนักงาน (USRID)", "พนักงาน + LINE user_id"),
    ]

    def _check(item_def):
        key, name, desc = item_def
        cfg = SHEET_CONFIG.get(key, {})
        d = {
            "key": key, "name": name, "desc": desc,
            "tab": cfg.get("sheet_name", ""),
            "spreadsheetId": cfg.get("spreadsheet_id", ""),
            "url": f"https://docs.google.com/spreadsheets/d/{cfg.get('spreadsheet_id','')}/edit",
        }
        try:
            d["rows"] = len(fetch_sheet(key))
            d["status"] = "ok"
        except Exception as e:
            d["status"] = "error"
            d["error"] = str(e)[:140]
            d["rows"] = 0
        return d

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        sources = list(ex.map(_check, sources_def))

    # leads: รายชื่อ tab รายเดือนที่เจอ (สด)
    monthly_tabs = []
    try:
        creds = _get_credentials()
        creds.refresh(AuthRequest())
        sid = SHEET_CONFIG["leads"]["spreadsheet_id"]
        meta = _rq.get(
            f"{SHEETS_API}/{sid}?fields=sheets.properties.title",
            headers={"Authorization": f"Bearer {creds.token}"}, timeout=15,
        ).json()
        for s in meta.get("sheets", []):
            title = s["properties"]["title"]
            for m in _THAI_MONTHS:
                if title.startswith(m + " "):
                    monthly_tabs.append(title)
                    break
    except Exception:
        pass

    # sheet ตั้งค่า (ไม่ใช่ data feed)
    config_sources = []
    for key, name in [("sellers_config", "🎯 ตั้งค่าเซลล์"),
                      ("schedule_config", "⏰ ตั้งเวลาส่ง LINE"),
                      ("lead_score_config", "📊 เกณฑ์คะแนน Lead")]:
        cfg = SHEET_CONFIG.get(key, {})
        config_sources.append({
            "key": key, "name": name, "tab": cfg.get("sheet_name", ""),
            "spreadsheetId": cfg.get("spreadsheet_id", ""),
            "url": f"https://docs.google.com/spreadsheets/d/{cfg.get('spreadsheet_id','')}/edit",
        })

    return JsonResponse({
        "ok": True,
        "sources": sources,
        "monthlyTabs": monthly_tabs,
        "configSources": config_sources,
        "useSupabase": bool(getattr(settings, "USE_SUPABASE", False)),
        "canEdit": _sb_configured(),
    }, json_dumps_params={"ensure_ascii": False})


@csrf_exempt
@require_http_methods(["POST"])
def admin_sheet_config(request):
    """Admin — บันทึก override ของแหล่งข้อมูล (ย้าย spreadsheet/tab) ลง Supabase.

    body JSON: {"items": [{"key": "leads", "spreadsheetId": "...", "sheetName": "..."}, ...]}
    เก็บใน Supabase table sheet_config → load_sheet_config_overrides() จะ apply ทุก process.
    """
    user = _session_user(request)
    if not user or user.get("position") != "admin":
        return JsonResponse({"error": "ต้อง login admin ก่อน"}, status=401)

    from .services.supabase_client import is_configured as sb_ok, save_sheet_config
    if not sb_ok():
        return JsonResponse({"error": "ต้องตั้ง Supabase ก่อน (SUPABASE_URL/SUPABASE_SECRET_KEY) ถึงจะบันทึก override ได้"}, status=400)

    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON ไม่ถูกต้อง"}, status=400)

    items_in = body.get("items") or []
    if not isinstance(items_in, list) or not items_in:
        return JsonResponse({"error": "ต้องมี items"}, status=400)

    from .services.google_sheets import SHEET_CONFIG, load_sheet_config_overrides
    items = []
    for it in items_in:
        key = (it.get("key") or "").strip()
        if key not in SHEET_CONFIG:
            continue
        items.append({
            "key": key,
            "spreadsheet_id": (it.get("spreadsheetId") or "").strip(),
            "sheet_name": (it.get("sheetName") or "").strip(),
        })
    if not items:
        return JsonResponse({"error": "ไม่มี key ที่ถูกต้อง"}, status=400)

    try:
        save_sheet_config(items)
    except Exception as e:
        return JsonResponse({"error": str(e)[:300]}, status=502)

    # apply ทันที + ล้าง cache ทั้งหมด (sheet cache + dashboard) ให้ดึงไฟล์ใหม่
    load_sheet_config_overrides(force=True)
    from .services.google_sheets import invalidate_cache
    invalidate_cache()
    try:
        from .services.fetch_dashboard import _dash_cache
        _dash_cache["data"] = None  # force คำนวณใหม่จากไฟล์ใหม่ (ไม่ใช้ .clear() เพราะต้องคง key "ts")
    except Exception:
        pass

    # ถ้าอ่านผ่าน Supabase mirror → ต้อง re-sync จากไฟล์ใหม่ ไม่งั้น dashboard เห็นข้อมูลเก่า
    synced = None
    if getattr(settings, "USE_SUPABASE", False):
        try:
            from .services.supabase_client import sync_all_sheets_to_supabase
            synced = sync_all_sheets_to_supabase()
        except Exception as e:
            synced = {"error": str(e)[:200]}

    return JsonResponse({"ok": True, "saved": len(items), "synced": synced},
                        json_dumps_params={"ensure_ascii": False})


@csrf_exempt
@require_http_methods(["POST"])
def update_lead_note(request):
    """หน้า LEAD — เซลล์กรอกคอลัม S ('มากรอกชีตกันเถอะ') → เขียนกลับ Google Sheet จริง.

    body JSON: {token, code, note, month?}
    note = ข้อความอัพเดทแต่ละครั้งคั่นด้วย ' / ' (ตามจำนวนอัพเดทในคอลัม Q)
    """
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON ไม่ถูกต้อง"}, status=400)

    token = (body.get("token") or "").strip()
    code = (body.get("code") or "").strip()
    field = (body.get("field") or "fill_sheet_note").strip()   # S=fill_sheet_note (default) / Z=customer_status / N=call_proof
    value = body.get("value", body.get("note", ""))            # back-compat: เดิมส่ง 'note'
    if not isinstance(value, str):
        value = str(value)

    seller_name = seller_from_token(token)   # คืนชื่อ normalize แล้ว
    if not seller_name:
        return JsonResponse({"error": "token ไม่ถูกต้อง"}, status=401)
    if not code:
        return JsonResponse({"error": "ไม่มี code"}, status=400)

    try:
        mi = int(body.get("month")) if body.get("month") else None
    except (ValueError, TypeError):
        mi = None

    from .services.google_sheets import update_lead_field
    res = update_lead_field(code, field, value, mi, expected_seller=seller_name)
    if res.get("error"):
        return JsonResponse(res, status=502)

    # mirror Supabase → re-sync เบื้องหลัง ให้ dashboard เห็นค่าใหม่ (ไม่ block)
    if getattr(settings, "USE_SUPABASE", False):
        try:
            from .services.supabase_client import _trigger_bg_sync
            _trigger_bg_sync()
        except Exception:
            pass
    return JsonResponse(res, json_dumps_params={"ensure_ascii": False})


@csrf_exempt
@require_http_methods(["POST"])
def finance_check_submit(request):
    """รับฟอร์ม 'เช็คเคสไฟแนนซ์ก่อนเซ็น' จากหน้าเซลล์ → สร้าง Flex → push เข้า LINE

    ช่วงทดสอบ: ส่งเข้า FINANCE_TEST_LINE_ID (หรือ EXECUTIVE_USER_IDS[0]) แทนกลุ่ม
    body JSON: {"token": "<seller token>", "data": {...form fields...}}
    """
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON ไม่ถูกต้อง"}, status=400)

    token = (body.get("token") or "").strip()
    data = body.get("data") or {}
    if not isinstance(data, dict):
        return JsonResponse({"error": "data ต้องเป็น object"}, status=400)

    seller_name = seller_from_token(token) or "-"
    data.setdefault("seller", seller_name)

    channel_token = (getattr(settings, "LINE_CHANNEL_ACCESS_TOKEN", "") or "").strip()
    if not channel_token:
        return JsonResponse({"error": "ยังไม่ได้ตั้ง LINE_CHANNEL_ACCESS_TOKEN ใน .env"}, status=500)

    # ปลายทาง: ส่งเข้า FINANCE_TEST_LINE_ID เท่านั้น — ไม่ fallback ไป id อื่นเด็ดขาด (กันส่งผิดคน)
    target = (getattr(settings, "FINANCE_TEST_LINE_ID", "") or "").strip()
    if not target:
        return JsonResponse({"error": "ยังไม่ได้ตั้ง FINANCE_TEST_LINE_ID ใน .env — ปฏิเสธการส่ง (กันส่งผิดคน)"}, status=500)

    # เก็บลง Supabase (best-effort — ไม่ block การส่ง LINE)
    record_id = _save_to_supabase("finance_checks", {
        "seller": data.get("seller") or seller_name,
        "lead_code": data.get("leadCode", ""),
        "customer": data.get("customer", ""),
        "finco": data.get("finco", ""),
        "status": "pending",
        "data": data,
    })

    from .services.line_notify import build_finance_check_flex, push_line_message
    base_url = request.build_absolute_uri("/").rstrip("/")
    try:
        flex = build_finance_check_flex(data, base_url=base_url)
        code, text = push_line_message(target, [flex], channel_token)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

    if code == 200:
        return JsonResponse({"ok": True, "target": target[:10] + "...", "saved": bool(record_id), "id": record_id})
    return JsonResponse({"error": f"LINE {code}: {text[:200]}"}, status=502)


@csrf_exempt
@require_http_methods(["POST"])
def scan_doc(request):
    """รับรูปเอกสารไฟแนนซ์ → Gemini OCR → คืน field สำหรับเติมฟอร์ม (ร่าง ให้คนตรวจก่อน).

    body JSON: {"image": "data:image/jpeg;base64,...."}  (หรือ base64 ล้วน)
    """
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON ไม่ถูกต้อง"}, status=400)

    img = (body.get("image") or "").strip()
    if not img:
        return JsonResponse({"error": "ไม่มีรูป"}, status=400)

    mime = "image/jpeg"
    if img.startswith("data:"):
        try:
            header, b64 = img.split(",", 1)
            mime = header.split(";")[0].replace("data:", "").strip() or mime
        except ValueError:
            return JsonResponse({"error": "รูปไม่ถูกต้อง"}, status=400)
    else:
        b64 = img

    import base64 as _b64
    try:
        img_bytes = _b64.b64decode(b64)
    except Exception:
        return JsonResponse({"error": "decode รูปไม่ได้"}, status=400)
    if len(img_bytes) > 8 * 1024 * 1024:
        return JsonResponse({"error": "รูปใหญ่เกิน 8MB — ถ่ายใหม่หรือย่อก่อน"}, status=400)

    form = (body.get("form") or "finance").strip()
    from .services.gemini_ocr import extract_finance_fields, extract_loan_fields
    try:
        if form == "loan":
            fields = extract_loan_fields(img_bytes, mime)
        else:
            fields = extract_finance_fields(img_bytes, mime)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=502)
    return JsonResponse({"ok": True, "fields": fields})


@csrf_exempt
@require_http_methods(["POST"])
def loan_submit(request):
    """รับฟอร์ม 'ยื่นสินเชื่อ' จากหน้าเซลล์ → สร้าง Flex → push เข้า LINE (ทดสอบส่ง id แอดมิน)."""
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON ไม่ถูกต้อง"}, status=400)

    token = (body.get("token") or "").strip()
    data = body.get("data") or {}
    if not isinstance(data, dict):
        return JsonResponse({"error": "data ต้องเป็น object"}, status=400)

    seller_name = seller_from_token(token) or "-"
    data.setdefault("sales", seller_name)

    channel_token = (getattr(settings, "LINE_CHANNEL_ACCESS_TOKEN", "") or "").strip()
    if not channel_token:
        return JsonResponse({"error": "ยังไม่ได้ตั้ง LINE_CHANNEL_ACCESS_TOKEN ใน .env"}, status=500)

    target = (getattr(settings, "FINANCE_TEST_LINE_ID", "") or "").strip()
    if not target:
        return JsonResponse({"error": "ยังไม่ได้ตั้ง FINANCE_TEST_LINE_ID ใน .env — ปฏิเสธการส่ง (กันส่งผิดคน)"}, status=500)

    # เก็บลง Supabase (best-effort)
    record_id = _save_to_supabase("loan_applications", {
        "seller": data.get("sales") or seller_name,
        "customer": data.get("customer", ""),
        "phone": data.get("phone", ""),
        "finance": data.get("finance", ""),
        "status": "pending",
        "data": data,
    })

    from .services.line_notify import build_loan_flex, push_line_message
    base_url = request.build_absolute_uri("/").rstrip("/")
    try:
        flex = build_loan_flex(data, base_url=base_url)
        code, text = push_line_message(target, [flex], channel_token)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

    if code == 200:
        return JsonResponse({"ok": True, "target": target[:10] + "...", "saved": bool(record_id), "id": record_id})
    return JsonResponse({"error": f"LINE {code}: {text[:200]}"}, status=502)


@require_GET
def seller_dashboard(request, token):
    """หน้าส่วนตัวของเซลล์ — /s/<token>/

    Token: รับ 2 แบบ
      1. SELLER_TOKENS legacy (เซลล์เก่า 13 คน)
      2. LINE user_id จาก employees sheet (เซลล์ใหม่)

    Data isolation: ใช้ fetch_seller_stats() ที่ส่งเฉพาะข้อมูลของเซลล์คนนี้
    → ไม่ใส่ data ของเซลล์อื่นใน JSON (กันแอบเปิด DevTools ดู)
    """
    seller_name = seller_from_token(token)
    if not seller_name:
        return render(request, "dashboard/seller.html", {
            "error": "ลิงก์ไม่ถูกต้องหรือหมดอายุ — กรุณาติดต่อผู้ดูแลระบบ",
            "seller": None,
            "data_json": "null",
            "constants_json": "{}",
        }, status=404)
    return _render_seller_page(request, seller_name)


@ensure_csrf_cookie
@require_GET
def me_dashboard(request):
    """/me/ — หน้าส่วนตัวของเซลล์ที่ login (email+password) — ดึง seller_name จาก session.
    admin/ผู้บริหาร → redirect ไป /dashboard/ (ไม่มีข้อมูลรายเซลล์ของตัวเอง)."""
    user = _session_user(request)
    if not user:
        return HttpResponseRedirect("/login/?next=/me/")
    if _can_view_all(user):
        return HttpResponseRedirect("/dashboard/")
    from .services.constants import normalize_seller
    raw_name = (user.get("seller_name") or user.get("nickname") or "").strip()
    seller_name = normalize_seller(raw_name) or raw_name
    if not seller_name:
        return render(request, "dashboard/seller.html", {
            "error": "บัญชีนี้ยังไม่ได้ผูกกับชื่อเซลล์ — กรุณาติดต่อผู้ดูแลระบบ",
            "seller": None, "data_json": "null", "constants_json": "{}",
        }, status=404)
    return _render_seller_page(request, seller_name)


def _render_seller_page(request, seller_name):
    """render หน้า seller.html ของเซลล์ 1 คน (ใช้ร่วม /s/<token>/ และ /me/).
    ส่งเฉพาะข้อมูลของเซลล์คนนี้ (fetch_seller_stats) — ไม่มี data ของคนอื่นใน JSON."""
    from .services.fetch_dashboard import fetch_seller_stats

    try:
        # ดึงเฉพาะข้อมูลของเซลล์คนนี้ — ไม่มีของเซลล์อื่นใน response
        data = fetch_seller_stats(seller_name)
    except Exception as e:
        return render(request, "dashboard/seller.html", {
            "error": str(e),
            "seller": seller_name,
            "data_json": "null",
            "constants_json": "{}",
        })

    # ── จัดอันดับ "ต้องโทร" โดยความเร่งด่วน ──
    def call_priority(c):
        u = c.get("updateCount", 0)
        score = 100 if u == 0 else 0
        score += max(0, UPD_TGT - u) * 10
        return score

    my_follows = data.get("followCases", [])
    for c in my_follows:
        u = c.get("updateCount", 0)
        c["mustCall"] = u == 0 or u < UPD_TGT
        c["callScore"] = call_priority(c)
    my_follows.sort(key=lambda c: c["callScore"], reverse=True)
    must_call_count = sum(1 for c in my_follows if c["mustCall"])

    # ── ดึง lead list (รวม junk) — ใช้ fetch_leads_by_month_tabs (cached)
    # เลขตรงกับการนับ raw rows ใน Google Sheet
    from .services.google_sheets import fetch_leads_by_month_tabs, cell, cell_num, LEADS_COL as L
    from .services.constants import normalize_seller
    from .services.fetch_dashboard import is_this_year, customer_status_priority
    import re as _re

    raw_leads = fetch_leads_by_month_tabs()

    # ── Lead Score context: โหลด config + maps ครั้งเดียวสำหรับ batch ──
    from .services.fetch_dashboard import prepare_lead_score_context, compute_lead_score
    from .services.google_sheets import fetch_sheet
    try:
        sales_rows = fetch_sheet("sales_reports")
    except Exception:
        sales_rows = []
    score_ctx = prepare_lead_score_context(raw_leads, sales_rows)

    my_leads = []
    for r in raw_leads:
        if normalize_seller(cell(r, L.sales_rep)) != seller_name:
            continue
        date_str = cell(r, L.received_date)
        if not is_this_year(date_str):
            continue
        note_raw = cell(r, L.fill_sheet_note) or ""
        note = _re.sub(r"^\d{4,5}\s*", "", note_raw)
        # คำนวณ Lead Score ต่อเคส
        try:
            ls = compute_lead_score(
                r, score_ctx["cfg"],
                score_ctx["cancelled"], score_ctx["done"],
                score_ctx["top_cars"],
            )
        except Exception:
            ls = {"score": 0, "tier": "❄cold", "breakdown": []}
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
            "customerStatus": cell(r, L.customer_status),   # คอลัม Z (layout ใหม่)
            "followPriority": customer_status_priority(cell(r, L.customer_status)),
            "lastUpdate": cell(r, L.last_updated_at),
            "note": note,
            "fillNote": note,                                # คอลัม S ดิบ (ไว้กรอก/แก้)
            "profile": cell(r, L.customer_profile),          # T PROFILE ลูกค้า
            "occupation": cell(r, L.occupation),             # U อาชีพ
            "income": cell(r, L.income),                     # V รายได้
            "jobTenure": cell(r, L.job_tenure),              # W อายุงาน
            "paymentHistory": cell(r, L.payment_history),    # X ประวัติการผ่อน
            "customerType": cell(r, L.customer_type),        # Y ประเภทลูกค้า
            "leadScore": ls["score"],
            "leadTier": ls["tier"],
            "scoreBreakdown": ls["breakdown"],
        })

    filtered = {
        "meta": data["meta"],
        "seller": data["seller"],
        "today": data["today"],
        "leads": my_leads,
        "followCases": my_follows,
        "bookingCases": data["bookingCases"],
        "mustCallCount": must_call_count,
        "daily": data["daily"],
        "monthly": data["monthly"],
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
