# -*- coding: utf-8 -*-
"""หน้า **Connect** (`/connect/`) + API — ห้องแชทลูกค้ารวม (3 ต.ค.69 · เจ้าของสั่ง)

ตรรกะทั้งหมดอยู่ใน [connect.py](connect.py) — ไฟล์นี้ทำแค่ 2 อย่าง: **เช็คสิทธิ์** แล้วแปลงเป็น JSON

สิทธิ์ (เช็คที่เซิร์ฟเวอร์ทุก endpoint — ไม่ใช่แค่ซ่อนปุ่ม เพราะยิง API ตรงได้):
  - **แอดมิน/ผู้บริหาร** — เห็นทุกแชท · ตอบได้ทุกคน · โอน/ปล่อยคืนคิว · ตั้งค่าเวร/เส้นตาย
  - **เซลล์** — เห็นเต็มเฉพาะลูกค้าที่ตัวเองรับ · คิวรอรับเห็นแค่ข้อความที่ลูกค้าเพิ่งส่ง
    และเห็นเฉพาะวันเวรของทีมตัวเอง · ตอบได้เฉพาะลูกค้าของตัวเอง
  - **คนงาน (worker)** — เข้าไม่ได้

⚠️ ไม่ส่ง LINE user id ของลูกค้าออกจากไฟล์นี้เลย — อ้างอิงด้วย `ChatOwner.id`
"""
import json

from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET

from . import connect as C
from .models import ChatOwner, Employee

_ADMIN_POS = {"admin", "executive", "ผู้บริหาร", "manager", "exec"}


def _j(data, status=200):
    return JsonResponse(data, status=status, json_dumps_params={"ensure_ascii": False})


def _body(request) -> dict:
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return {}


def _ctx(request):
    """คนที่เปิดหน้านี้ — None = ยังไม่ login"""
    u = request.session.get("oxlet_user")
    if not (isinstance(u, dict) and u.get("position")):
        return None
    pos = (u.get("position") or "").strip().lower()
    try:
        emp = C.employee_of(u)
    except Exception:
        emp = None
    return {
        "user": u,
        "admin": pos in _ADMIN_POS,
        "worker": pos == "worker",
        "emp": emp,
        "team": C.team_of(emp),
        "name": (emp.nickname if emp else (u.get("nickname") or u.get("display_name") or "")),
    }


def _deny(ctx):
    """เหตุผลที่ใช้หน้านี้ไม่ได้ ('' = ใช้ได้)"""
    if not ctx:
        return "ต้องเข้าสู่ระบบก่อน"
    if ctx["worker"]:
        return "หน้านี้สำหรับเซลล์และแอดมินเท่านั้น"
    if not ctx["admin"] and not ctx["emp"]:
        return "บัญชีนี้ยังไม่ได้ผูกกับทะเบียนพนักงาน — แจ้งแอดมินให้เพิ่มชื่อเล่นในหน้า \"พนักงาน\""
    return ""


def _access(ctx, o) -> str:
    """'full' = เห็นบทสนทนาทั้งหมด · 'preview' = คิวรอรับ (เห็นแค่ที่ลูกค้าเพิ่งส่ง) · '' = ไม่มีสิทธิ์"""
    if ctx["admin"]:
        return "full"
    emp = ctx["emp"]
    if emp and o.owner_id == emp.id:
        return "full"
    if (not o.owner_id and o.awaiting_since and ctx["team"]
            and ctx["team"] == C.today_team()):
        return "preview"
    return ""


def _row(request, ctx, rid):
    try:
        rid = int(rid)
    except Exception:
        return None
    return ChatOwner.objects.select_related("profile", "owner").filter(pk=rid).first()


def _status(ctx) -> list:
    """ป้ายเตือนบนหัวหน้า — บอกตรงๆ ว่าทำไมบางอย่างยังใช้ไม่ได้"""
    out = []
    try:
        from .chat import reply_on
        from .views import line_cfg
        lc = line_cfg()
        if not lc.get("store_customer_chat"):
            out.append({"level": "err", "text": "ยังไม่ได้เปิด \"เก็บแชทลูกค้า\" — ลูกค้าที่ทักเข้ามาจะไม่เข้า Connect",
                        "fix": "manage.py checkout_config --customer-chat on" if ctx["admin"] else ""})
        if not reply_on():
            out.append({"level": "warn",
                        "text": "ยังล็อกการส่งข้อความหาลูกค้าอยู่ (ช่วงทดสอบ) — ดู/รับ/โอนลูกค้าได้ แต่กดส่งไม่ได้",
                        "fix": "manage.py checkout_config --reply on" if ctx["admin"] else ""})
    except Exception:
        pass
    return out


def _duty(c=None) -> dict:
    c = c or C.cfg()
    d = timezone.localdate()
    return {"today": C.duty_team(d, c), "tomorrow": C.duty_team(d + timezone.timedelta(days=1), c),
            "teams": c["teams"], "slaMin": c["sla_min"], "open": c["open"], "close": c["close"]}


# ─────────────────────────────────────────────────────────────
#  หน้าเว็บ
# ─────────────────────────────────────────────────────────────
@ensure_csrf_cookie
@require_GET
def page(request):
    ctx = _ctx(request)
    if not ctx:
        nxt = "/connect/" + (("?id=%s" % request.GET.get("id")) if request.GET.get("id") else "")
        from urllib.parse import quote
        return HttpResponseRedirect("/login/?next=" + quote(nxt))
    err = _deny(ctx)
    boot = {
        "me": {"name": ctx["name"], "team": ctx["team"], "admin": ctx["admin"],
               "empId": ctx["emp"].id if ctx["emp"] else 0},
        "openId": request.GET.get("id") or "",
        "embed": request.GET.get("embed") == "1",
    }
    # json_script (ไม่ใช่ |safe) — ชื่อเล่นเป็นข้อความที่คนพิมพ์เอง ห้ามให้ปิด <script> ได้
    return render(request, "checkout/connect.html", {"error": err, "boot": boot},
                  status=403 if err else 200)


# ─────────────────────────────────────────────────────────────
#  API
# ─────────────────────────────────────────────────────────────
@require_GET
def api_summary(request):
    """ตัวเลขเล็กๆ สำหรับป้ายบนเมนู (แดชบอร์ดแอดมิน + หน้าเซลล์) — เบา เรียกถี่ได้"""
    ctx = _ctx(request)
    if _deny(ctx):
        return _j({"ok": False}, 401)
    duty = _duty()
    cnt = C.counts(ctx["emp"], ctx["admin"])
    on_duty = bool(ctx["team"]) and ctx["team"] == duty["today"]
    if not ctx["admin"] and not on_duty:
        cnt["queue"] = 0                        # ไม่ใช่วันเวร = ไม่ต้องเห็นคิว
    return _j({"ok": True, "counts": cnt, "duty": duty, "onDuty": on_duty,
               "admin": ctx["admin"]})


@require_GET
def api_inbox(request):
    ctx = _ctx(request)
    why = _deny(ctx)
    if why:
        return _j({"ok": False, "error": why}, 401 if not ctx else 403)
    c = C.cfg()
    duty = _duty(c)
    admin, emp = ctx["admin"], ctx["emp"]
    on_duty = bool(ctx["team"]) and ctx["team"] == duty["today"]

    view = (request.GET.get("view") or "").strip()
    allowed = C.VIEWS if admin else ("queue", "mine")
    if view not in allowed:
        view = "overdue" if admin else ("queue" if on_duty else "mine")
    try:
        seller = int(request.GET.get("seller") or 0)
    except Exception:
        seller = 0

    note = ""
    if admin:
        try:
            C.sync_rows()                        # ลูกค้าเก่าที่ทักมาก่อนมี Connect (ทุก 2 นาทีพอ)
        except Exception:
            pass
    if view == "queue" and not admin and not on_duty:
        rows = []
        note = C.off_duty_reason(ctx["team"], c)
    else:
        rows = C.inbox(view, me=emp, admin=admin, q=request.GET.get("q", ""), seller_id=seller)

    cnt = C.counts(emp, admin)
    if not admin and not on_duty:
        cnt["queue"] = 0
    out = {"ok": True, "view": view, "rows": rows, "counts": cnt, "duty": duty,
           "onDuty": on_duty, "note": note, "status": _status(ctx),
           "now": timezone.localtime().isoformat(timespec="seconds")}
    if admin:
        out["sellers"] = C.seller_list()
    return _j(out)


@require_GET
def api_chat(request):
    ctx = _ctx(request)
    why = _deny(ctx)
    if why:
        return _j({"ok": False, "error": why}, 401 if not ctx else 403)
    o = _row(request, ctx, request.GET.get("id"))
    if not o:
        return _j({"ok": False, "error": "ไม่พบลูกค้ารายนี้"}, 404)
    acc = _access(ctx, o)
    if not acc:
        return _j({"ok": False, "error": "ลูกค้าคนนี้ไม่ใช่ของคุณ — เห็นได้เฉพาะลูกค้าที่คุณรับไว้"}, 403)
    from .chat import reply_on
    admin, emp = ctx["admin"], ctx["emp"]
    mine = bool(emp and o.owner_id == emp.id)
    if acc == "preview":
        msgs = C.messages(o, limit=10, since=o.awaiting_since)
    else:
        msgs = C.messages(o)
    out = {
        "ok": True,
        "row": C.row_json(o, emp),
        "access": acc,
        "messages": msgs,
        "canClaim": not o.owner_id and bool(emp) and (admin or acc == "preview"),
        "canReply": acc == "full" and (admin or mine),
        "canDismiss": acc == "full" and bool(o.awaiting_since) and (admin or mine),
        "canAssign": admin,
        "replyOn": reply_on(),
        "now": timezone.localtime().isoformat(timespec="seconds"),
    }
    if admin:
        out["history"] = C.history(o)
        out["status"] = o.profile.status_message or ""
        out["firstSeen"] = C._iso(o.profile.first_seen)
    return _j(out)


def _post_guard(request):
    if request.method != "POST":
        return None, None, _j({"ok": False, "error": "ต้องเป็น POST"}, 405)
    ctx = _ctx(request)
    why = _deny(ctx)
    if why:
        return None, None, _j({"ok": False, "error": why}, 401 if not ctx else 403)
    return ctx, _body(request), None


def api_claim(request):
    ctx, body, bad = _post_guard(request)
    if bad:
        return bad
    o = _row(request, ctx, body.get("id"))
    if not o:
        return _j({"ok": False, "error": "ไม่พบลูกค้ารายนี้"}, 404)
    # กติกาวันเวร/คิว/ใครกดก่อน อยู่ใน claim() ทั้งหมด (และอธิบายเหตุผลเป็นภาษาคนเอง)
    ok, msg = C.claim(o.id, ctx["emp"], admin=ctx["admin"])
    return _j({"ok": ok, "message" if ok else "error": msg}, 200 if ok else 409)


def api_reply(request):
    ctx, body, bad = _post_guard(request)
    if bad:
        return bad
    o = _row(request, ctx, body.get("id"))
    if not o:
        return _j({"ok": False, "error": "ไม่พบลูกค้ารายนี้"}, 404)
    emp = ctx["emp"]
    if not (ctx["admin"] or (emp and o.owner_id == emp.id)):
        return _j({"ok": False, "error": "ตอบได้เฉพาะลูกค้าของคุณ — กด \"รับลูกค้า\" ก่อน"}, 403)
    from .chat import ReplyError, send_reply
    try:
        row = send_reply(o.profile.user_id, body.get("text") or "", ctx["user"])
    except ReplyError as e:
        return _j({"ok": False, "error": str(e)}, 400)
    except Exception as e:                       # เน็ตล่ม/LINE ไม่ตอบ — อย่าคืน 500 เปล่าๆ
        return _j({"ok": False, "error": "ส่งไม่สำเร็จ: %s" % e}, 502)
    return _j({"ok": True, "message": {"at": C._iso(row.sent_at), "text": row.text, "dir": "out",
                                       "by": row.sent_by_name or "", "type": "text", "media": False}})


def api_assign(request):
    ctx, body, bad = _post_guard(request)
    if bad:
        return bad
    if not ctx["admin"]:
        return _j({"ok": False, "error": "โอนลูกค้าได้เฉพาะแอดมิน"}, 403)
    o = _row(request, ctx, body.get("id"))
    if not o:
        return _j({"ok": False, "error": "ไม่พบลูกค้ารายนี้"}, 404)
    try:
        eid = int(body.get("emp") or 0)
    except Exception:
        eid = 0
    emp = Employee.objects.filter(pk=eid).first() if eid else None
    if eid and not emp:
        return _j({"ok": False, "error": "ไม่พบพนักงานคนนี้ในทะเบียน"}, 404)
    ok, msg = C.assign(o.id, emp, by=ctx["name"] or "แอดมิน")
    return _j({"ok": ok, "message" if ok else "error": msg}, 200 if ok else 400)


def api_dismiss(request):
    ctx, body, bad = _post_guard(request)
    if bad:
        return bad
    o = _row(request, ctx, body.get("id"))
    if not o:
        return _j({"ok": False, "error": "ไม่พบลูกค้ารายนี้"}, 404)
    emp = ctx["emp"]
    if not (ctx["admin"] or (emp and o.owner_id == emp.id)):
        return _j({"ok": False, "error": "ทำได้เฉพาะลูกค้าของคุณ"}, 403)
    ok, msg = C.dismiss(o.id, by=ctx["name"], emp=emp)
    return _j({"ok": ok, "message" if ok else "error": msg}, 200 if ok else 400)


def _alert_groups() -> list:
    """กลุ่ม LINE ที่บอทตัวส่งอยู่ — ตัวเลือก "ส่งแจ้งเตือนเข้ากลุ่มไหน" (ซ่อน id ของบอทตัวรับ)"""
    try:
        from dashboard.services import cache_store
        from dashboard.services.line_channels import group_visible_to_push
        groups = (cache_store.get_kv("line_groups") or {}).get("data") or {}
        rows = [{"id": gid, "name": g.get("name", "")} for gid, g in groups.items()
                if group_visible_to_push(g)]
        rows.sort(key=lambda r: r["name"] or r["id"])
        return rows
    except Exception:
        return []


def api_config(request):
    ctx = _ctx(request)
    if not ctx or not ctx["admin"]:
        return _j({"ok": False, "error": "ตั้งค่าได้เฉพาะแอดมิน/ผู้บริหาร"}, 403)
    if request.method == "POST":
        body = _body(request)
        new, errs = C.clean_cfg(body)
        if not errs and new.get("alert_on") and new.get("alert_group") \
                and new["alert_group"] != C.cfg().get("alert_group"):
            try:
                from dashboard.services.line_channels import push_group_error
                e = push_group_error(new["alert_group"])
                if e:
                    errs.append(e)
            except Exception:
                pass
        if errs:
            return _j({"ok": False, "error": " · ".join(errs), "errors": errs}, 400)
        if not C.save_cfg(new):
            return _j({"ok": False, "error": "บันทึกไม่สำเร็จ (ฐานข้อมูลไม่ตอบ)"}, 500)
    c = C.cfg()
    teams = sorted({s["team"] for s in C.seller_list()} | set(c["teams"]))
    return _j({"ok": True, "cfg": c, "roster": C.roster(14, c), "duty": _duty(c),
               "teamsAvail": teams, "groups": _alert_groups(), "status": _status(ctx),
               "sellers": C.seller_list()})


@require_GET
def api_stats(request):
    ctx = _ctx(request)
    if not ctx or not ctx["admin"]:
        return _j({"ok": False, "error": "เฉพาะแอดมิน/ผู้บริหาร"}, 403)
    try:
        days = max(1, min(90, int(request.GET.get("days") or 7)))
    except Exception:
        days = 7
    out = C.stats(days)
    out["ok"] = True
    out["slaMin"] = C.cfg()["sla_min"]
    return _j(out)
