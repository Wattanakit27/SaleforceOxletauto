"""หน้า **Oxlet CRM** (`/crm/`) + API ของหน้านี้ (★ 13 ต.ค.69 · แบบ "Oxlet CRM.html" · เจ้าของเลือก "ทำเป็นหน้าใหม่แยก")

ไม่แตะหน้าเดิม (/me/ · /connect/ · /dashboard/) — ทีมลองใช้ก่อน แล้วค่อยตัดสินว่าจะสลับเป็นหน้าหลักไหม
ตรรกะข้อมูลอยู่ที่ [services/crm_page.py](services/crm_page.py) · ไฟล์นี้เช็คสิทธิ์แล้วแปลงเป็น JSON

สิทธิ์ (เช็คที่เซิร์ฟเวอร์ทุก endpoint):
  - **เซลล์** — เห็นเฉพาะของตัวเอง (ส่ง `seller` ของคนอื่นมาก็ไม่มีผล)
  - **แอดมิน/ผู้บริหาร** — เลือกดูของเซลล์คนไหนก็ได้ (`?seller=`)
  - **คนงาน** → /track/ · **จัดซื้อ** → /buy/ (หน้านี้ไม่มีข้อมูลของเขา)
  - ไม่ login → /login/?next=/crm/
ลูกค้าแชท: ใช้ API ของ Connect ตัวเดิม (ขั้น/นัด/บันทึกการโทร) — สิทธิ์ของ Connect คุมอยู่แล้ว
"""
import json

from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods

from .views import _can_view_all, _session_user


def _j(data, status=200):
    return JsonResponse(data, status=status, json_dumps_params={"ensure_ascii": False})


def _own_seller(user) -> str:
    """ชื่อเซลล์ของคนที่ login — ชื่อเล่น (normalize) · เทเลเซลล์ = "ADMIN" (ศูนย์รวมเคสที่ลงชื่อ ADMIN)"""
    from .services.constants import ALL_SELLERS, TELE_USER_IDS, load_tele_user_ids, normalize_seller
    raw = (user.get("seller_name") or user.get("nickname") or "").strip()
    name = normalize_seller(raw) or raw
    if name in ALL_SELLERS:
        return name
    try:
        load_tele_user_ids()
        if (user.get("user_id") or "").strip() in TELE_USER_IDS:
            return "ADMIN"
    except Exception:
        pass
    return name


def _who(request, want: str = ""):
    """(user, seller ที่จะดู, admin?, เหตุผลที่ใช้ไม่ได้)"""
    user = _session_user(request)
    if not user:
        return None, "", False, "login"
    pos = (user.get("position") or "").strip().lower()
    if pos == "worker":
        return user, "", False, "worker"
    admin = _can_view_all(user)
    from .services.constants import ALL_SELLERS, normalize_seller, refresh_from_sheet
    refresh_from_sheet()
    if admin:
        want = normalize_seller((want or "").strip()) or (want or "").strip()
        if want and (want in ALL_SELLERS or want == "ADMIN"):
            return user, want, True, ""
        own = _own_seller(user)
        if own in ALL_SELLERS:
            return user, own, True, ""
        from .services import crm_page
        r = crm_page.roster()
        return user, (r[0]["name"] if r else ""), True, ""
    try:
        from .services import mobile_home
        if mobile_home.role_of(user) == "buyer":
            return user, "", False, "buyer"
    except Exception:
        pass
    seller = _own_seller(user)
    if not seller:
        return user, "", False, "noname"
    return user, seller, False, ""


@ensure_csrf_cookie
@require_GET
def page(request):
    user, seller, admin, why = _who(request, request.GET.get("seller", ""))
    if why == "login":
        from urllib.parse import quote
        return HttpResponseRedirect("/login/?next=" + quote(request.get_full_path() or "/crm/"))
    if why == "worker":
        return HttpResponseRedirect("/track/")
    if why == "buyer":
        return HttpResponseRedirect("/buy/")
    boot = {"seller": seller, "admin": admin, "page": (request.GET.get("p") or "").strip()[:12],
            "me": {"nickname": user.get("nickname") or user.get("display_name") or "",
                   "own": _own_seller(user) if user else ""},
            "selfView": bool(seller) and seller == _own_seller(user),
            "error": "บัญชีนี้ยังไม่ได้ผูกกับชื่อเซลล์ — แจ้งผู้ดูแลระบบให้ตั้งชื่อเล่นในหน้าพนักงาน" if why == "noname" else ""}
    # ★ 20 ต.ค.69 เจ้าของสั่งเอาตัวเลือก "ดูของเซลล์" ออก — ไม่ส่งรายชื่อเซลล์ให้หน้าเว็บแล้ว (`?seller=` ยังใช้ได้ทางลิงก์)
    return render(request, "dashboard/crm.html", {"boot": boot}, status=404 if why == "noname" else 200)


@require_GET
def api_data(request):
    user, seller, admin, why = _who(request, request.GET.get("seller", ""))
    if why:
        return _j({"ok": False, "error": {"login": "ต้องเข้าสู่ระบบก่อน", "worker": "หน้านี้สำหรับเซลล์และแอดมิน",
                                           "buyer": "หน้านี้สำหรับเซลล์และแอดมิน",
                                           "noname": "บัญชีนี้ยังไม่ได้ผูกกับชื่อเซลล์"}.get(why, why)},
                  401 if why == "login" else 403)
    from .services import crm_page
    if request.GET.get("fresh") == "1":
        crm_page.invalidate(seller)
    emp = crm_page.seller_emp(seller)
    data = crm_page.build(seller, emp=emp, admin=admin)
    out = dict(data)
    out["admin"] = admin
    out["selfView"] = seller == _own_seller(user)
    return _j(out)


@require_GET
def api_customer(request):
    """รายละเอียดลูกค้าแชท 1 คน (แผงขวาของหน้าลูกค้า) — **ไม่นับว่าอ่านแชทแล้ว** (ต่างจากเปิดแชทใน Connect)

    สิทธิ์ = เจ้าของลูกค้า หรือแอดมิน (กติกาเดียวกับ Connect · คิวรอรับดูที่นี่ไม่ได้)
    """
    from checkout import connect as C
    from checkout import crm
    from checkout.connect_views import _ctx, _deny, _row
    from checkout.models import ChatOwnerLog
    ctx = _ctx(request)
    why = _deny(ctx)
    if why:
        return _j({"ok": False, "error": why}, 401 if not ctx else 403)
    o = _row(request, ctx, request.GET.get("id"))
    if not o:
        return _j({"ok": False, "error": "ไม่พบลูกค้ารายนี้"}, 404)
    emp = ctx["emp"]
    mine = bool(emp and o.owner_id == emp.id)
    if not (ctx["admin"] or mine):
        return _j({"ok": False, "error": "ลูกค้าคนนี้ไม่ใช่ของคุณ"}, 403)
    ld = C.lead_of(o, create=False)
    noisy = (ChatOwnerLog.REPLY, ChatOwnerLog.DISMISS, ChatOwnerLog.ESCALATE)
    timeline = [{"at": crm._iso(l.at), "action": l.action, "label": l.get_action_display(),
                 "emp": l.emp_name, "by": l.by_name, "note": l.note}
                for l in o.logs.exclude(action__in=noisy).order_by("-at", "-id")[:30]]
    return _j({"ok": True, "row": C.row_json(o, emp), "lead": C.lead_json(o, ld) if ld else None,
               "crm": crm.detail_json(o, ld), "profile": C.profile_json(o, "full", []),
               "timeline": timeline, "canEdit": bool(ctx["admin"] or mine)})


@require_http_methods(["POST"])
def api_lead_status(request):
    """เลือกสถานะลูกค้า (คอลัมน์ Z) ให้ลีดจากชีต — POST `{code, value, seller?}`

    เขียนช่อง Z ช่องเดียว (update_lead_field ตัวเดียวกับหน้าเซลล์) · เขียนเฉพาะแถวที่ชื่อเซลล์ตรง (expected_seller)
    เซลล์: ของตัวเองเท่านั้น · แอดมิน: ของเซลล์ที่เลือกดูอยู่ (`seller`)
    คืนคอลัมน์ใหม่บนกระดาน (sheet_stage ฝั่งเซิร์ฟเวอร์ — หน้าเว็บไม่ต้องมีสูตรของตัวเอง)
    """
    try:
        body = json.loads(request.body or b"{}")
    except Exception:
        body = {}
    user, seller, admin, why = _who(request, str(body.get("seller") or ""))
    if why:
        return _j({"ok": False, "error": "ทำได้เฉพาะเซลล์และแอดมิน"}, 401 if why == "login" else 403)
    if seller == "ADMIN":
        return _j({"ok": False, "error": "ลีดของเทเลเซลล์แก้ในชีตโดยตรง"}, 400)
    from .services import crm_page
    code = str(body.get("code") or "").strip()
    value = crm_page.clean_z(body.get("value"))
    opts = crm_page._z_options()
    if value and opts and value not in opts:
        return _j({"ok": False, "error": "สถานะนี้ไม่อยู่ในตัวเลือกของชีตลีด"}, 400)
    lead = crm_page.lead_by_code(seller, code)
    if not lead:
        return _j({"ok": False, "error": "ไม่พบลีด %s ของ %s ในปีนี้" % (code, seller)}, 404)
    from .services.google_sheets import update_lead_field
    res = update_lead_field(code, "customer_status", value, lead.get("month"), expected_seller=seller)
    if res.get("error"):
        return _j({"ok": False, "error": res["error"]}, 502)
    lead2 = dict(lead, customerStatus=value)
    stage = crm_page.sheet_stage(lead2)
    lead["customerStatus"] = value                 # แคชในเครื่องเห็นค่าใหม่ทันที (ชีตจริงตามมารอบอ่านถัดไป)
    lead["stage"] = stage
    crm_page.invalidate(seller)
    try:
        from .services import eventlog
        eventlog.log("crm", name="เลือกสถานะลูกค้า (หน้า CRM)", target=seller, ok=True, code=code, value=value)
    except Exception:
        pass
    return _j({"ok": True, "stage": stage, "value": value, "tab": res.get("tab", ""), "cell": res.get("cell", "")})


@require_http_methods(["GET", "POST"])
def api_auto(request):
    """หน้า **ระบบอัตโนมัติ** (★ 20 ต.ค.69 · แอดมินเท่านั้น) — คำที่ระบบจับจากแชท + แท็กลูกค้าอัตโนมัติ

    ★ 21 ต.ค.69 คำทั้งหมดย้ายจากโค้ดมาอยู่ในตาราง `checkout_keywordrule` (`checkout/kwdb.py`) แก้ได้ในหน้านี้
    GET = หมวด + ทุกแถว (+ ลูกค้าที่ติดแท็กจากแถวนั้น) · จำนวนที่ระบบเติมให้ต่อหมวด · ผลอ่านย้อนหลังล่าสุด
    POST `{action: "save", row}` เพิ่ม/แก้แถว · `{action: "toggle", key, field: active|tag, on}` · `{action: "delete", key}` ·
    `{action: "reset", key}` คืนค่าเดิมของระบบ · `{action: "preview", row}` ทดสอบกับแชทย้อนหลัง · `{action: "test", text}` ลองพิมพ์ ·
    `{action: "rescan"}` อ่านแชทย้อนหลังติดแท็กใหม่เดี๋ยวนี้
    (รูปแบบเดิมของกฎแท็กของเรา `{action: save|preview, rule}` · `{action: toggle|delete, id}` ยังใช้ได้)
    """
    user, _seller, admin, why = _who(request)
    if why == "login":
        return _j({"ok": False, "error": "ต้องเข้าสู่ระบบก่อน"}, 401)
    if why or not admin:
        return _j({"ok": False, "error": "หน้านี้สำหรับแอดมินเท่านั้น"}, 403)
    from checkout import autotag as AT
    from checkout import kwdb as KW
    by = (user.get("nickname") or user.get("display_name") or "แอดมิน")[:80]
    if request.method == "GET":
        KW._load(force=True)
        cnt = AT.rule_counts()
        rows = [dict(KW.row_json(r), count=cnt.get(r["key"], 0)) for r in KW.all_rows()]
        rs = [dict(r, count=cnt.get(r["id"], 0)) for r in AT.rules()]
        return _j({"ok": True, "groups": KW.GROUPS, "rows": rows, "rules": rs, "fill": AT.fill_stats(),
                   "source": KW.source(), "scopes": AT.SCOPES, "scanDays": AT.SCAN_DAYS, "last": AT.last_run(),
                   "busy": bool(AT._RUN.get("busy")),
                   "limits": {"rules": AT.RULE_MAX, "words": KW.WORDS_MAX, "tag": AT.TAG_LEN, "name": KW.NAME_LEN,
                              "wordMin": KW.WORD_MIN}})
    try:
        body = json.loads(request.body or b"{}")
    except Exception:
        return _j({"ok": False, "error": "ข้อมูลไม่ถูกต้อง"}, 400)
    act = str(body.get("action") or "")
    out = {}
    if act == "test":
        return _j(AT.test_text(body.get("text") or ""))
    if act == "preview":
        res = AT.preview(body.get("rule") or {}) if "rule" in body else AT.preview_row(body.get("row") or {})
        return _j(res, 200 if res.get("ok") else 400)
    if act == "rescan":
        AT.rescan_bg(by)
        ok, msg = True, "กำลังอ่านแชทย้อนหลัง %d วันและติดแท็กใหม่ตามคำปัจจุบัน" % AT.SCAN_DAYS
    elif act == "save" and "rule" in body:
        ok, msg, rule = AT.save_rule(body.get("rule") or {}, by=by)
        out["rule"] = rule
    elif act == "save":
        ok, msg, row = KW.save(body.get("row") or {}, by=by)
        out["row"] = KW.row_json(row) if row else None
        if ok and row and row["group"] in KW.TAG_GROUPS + ("occupation",):
            AT.rescan_bg(by)
            msg += " — กำลังติดแท็กให้แชทย้อนหลัง %d วัน" % AT.SCAN_DAYS
    elif act == "toggle" and body.get("id") and not body.get("key"):
        ok, msg = AT.toggle(body.get("id"), bool(body.get("on")), by=by)
    elif act == "toggle":
        ok, msg, row = KW.toggle(body.get("key"), str(body.get("field") or "active"), bool(body.get("on")), by=by)
        if ok and row and row["group"] in KW.TAG_GROUPS:
            AT.rescan_bg(by)
    elif act == "delete" and body.get("id") and not body.get("key"):
        ok, msg = AT.delete_rule(body.get("id"), by=by)
    elif act == "delete":
        grp = next((r["group"] for r in KW.all_rows() if r["key"] == str(body.get("key") or "")), "")
        ok, msg = KW.delete(body.get("key"), by=by)
        if ok and grp in KW.TAG_GROUPS:
            AT.rescan_bg(by)
    elif act == "reset":
        ok, msg = KW.reset(body.get("key"), by=by)
        if ok:
            AT.rescan_bg(by)
    else:
        return _j({"ok": False, "error": "ไม่รู้จักคำสั่งนี้"}, 400)
    if ok:
        try:
            from .services import eventlog
            eventlog.log("crm", name="ระบบอัตโนมัติ: " + act, target=by, ok=True,
                         key=body.get("key") or body.get("id") or ((body.get("row") or {}).get("name"))
                         or ((body.get("rule") or {}).get("tag")))
        except Exception:
            pass
    return _j(dict(out, ok=ok, message=msg if ok else "", error="" if ok else msg), 200 if ok else 400)
