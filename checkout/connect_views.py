# -*- coding: utf-8 -*-
"""หน้า **Connect** (`/connect/`) + API — ห้องแชทลูกค้ารวม (3 ต.ค.69 · เจ้าของสั่ง)

ตรรกะทั้งหมดอยู่ใน [connect.py](connect.py) — ไฟล์นี้ทำแค่ 2 อย่าง: **เช็คสิทธิ์** แล้วแปลงเป็น JSON

สิทธิ์ (เช็คที่เซิร์ฟเวอร์ทุก endpoint — ไม่ใช่แค่ซ่อนปุ่ม เพราะยิง API ตรงได้):
  - **แอดมิน/ผู้บริหาร** — เห็นทุกแชท · ตอบได้ทุกคน · โอน/ปล่อยคืนคิว · ตั้งค่าเวร/เส้นตาย
  - **เซลล์** — เห็นเต็มเฉพาะลูกค้าที่ตัวเองรับ · คิวรอรับเห็นแค่ข้อความที่ลูกค้าเพิ่งส่ง
    และเห็นเฉพาะวันเวรของทีมตัวเอง · ตอบได้เฉพาะลูกค้าของตัวเอง
    · ★ 6 ต.ค.69 ลูกค้า **Facebook** = สิทธิ์เก็บข้อมูลเท่านั้น (ดูแชท/กรอกข้อมูลลีด · ตอบ/ปิดรอบไม่ได้)
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
from .slippost import FB_DATA_ONLY

_ADMIN_POS = {"admin", "executive", "ผู้บริหาร", "manager", "exec"}


def _j(data, status=200):
    return JsonResponse(data, status=status, json_dumps_params={"ensure_ascii": False})


def _body(request) -> dict:
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return {}


TEST_AS_KEY = "connect_as"        # session: แอดมินกำลังใช้หน้าจอแบบบัญชีเซลล์จำลองคนไหน (Employee.id)


def _ctx(request):
    """คนที่เปิดหน้านี้ — None = ยังไม่ login

    ★ โหมดทดสอบ: แอดมินสลับไปใช้หน้าจอแบบ **บัญชีเซลล์จำลอง** ได้ (`connect_as` ใน session)
      → สิทธิ์ทุกอย่างคิดแบบเซลล์คนนั้นเป๊ะ (เช็คซ้ำทุกคำขอว่าคนจริงยังเป็นแอดมิน
      และเป้าหมายเป็นบัญชีจำลองเท่านั้น — สลับเป็นเซลล์จริงไม่ได้)
    """
    u = request.session.get("oxlet_user")
    if not (isinstance(u, dict) and u.get("position")):
        return None
    pos = (u.get("position") or "").strip().lower()
    admin = pos in _ADMIN_POS
    real_name = u.get("nickname") or u.get("display_name") or ""
    as_id = request.session.get(TEST_AS_KEY) if admin else None
    if as_id:
        tester = Employee.objects.filter(pk=as_id, active=True).first()
        if tester and C.is_test_seller(tester):
            return {"user": {"nickname": tester.nickname, "position": "seller"},
                    "admin": False, "worker": False, "emp": tester, "team": C.team_of(tester),
                    "name": tester.nickname, "testAs": True, "realAdmin": True, "realName": real_name}
        request.session.pop(TEST_AS_KEY, None)          # บัญชีจำลองถูกลบไปแล้ว → กลับเป็นแอดมิน
    try:
        emp = C.employee_of(u)
    except Exception:
        emp = None
    return {
        "user": u,
        "admin": admin,
        "worker": pos == "worker",
        "emp": emp,
        "team": C.team_of(emp),
        "name": (emp.nickname if emp else real_name),
        "testAs": False, "realAdmin": admin, "realName": real_name,
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
    return ChatOwner.objects.select_related("profile", "fb_profile", "owner").filter(pk=rid).first()


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
        # โหมดทดสอบ — หน้าเว็บขึ้นแถบบอกตลอดว่ากำลังใช้บัญชีจำลอง + ปุ่มกลับเป็นแอดมิน
        "test": {"as": ctx["testAs"], "realName": ctx["realName"],
                 "teams": C.cfg()["teams"]} if ctx["realAdmin"] else None,
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
        if view == "tocode":
            try:
                C.slip_sweep_bg()                # ลีดที่จ่ายในกลุ่มแล้ว → ได้เลข + ออกจากห้องพัก (thread · เว้น ≥ 55 วิ ต่อ worker)
            except Exception:
                pass
    try:
        C.fill_pictures_bg()                     # ทยอยเติมรูปโปรไฟล์ลูกค้า (thread แยก · นาทีละครั้ง)
    except Exception:
        pass
    if view == "queue" and not admin and not on_duty:
        rows = []
        note = C.off_duty_reason(ctx["team"], c)
    else:
        rows = C.inbox(view, me=emp, admin=admin, q=request.GET.get("q", ""), seller_id=seller,
                       src=(request.GET.get("src") or "").strip())

    cnt = C.counts(emp, admin)
    if not admin and not on_duty:
        cnt["queue"] = 0
    out = {"ok": True, "view": view, "rows": rows, "counts": cnt, "duty": duty,
           "onDuty": on_duty, "note": note, "status": _status(ctx),
           "now": timezone.localtime().isoformat(timespec="seconds")}
    if admin:
        out["sellers"] = C.seller_list()
        # ห้องพัก Lead ("ADMIN เก็บ Lead") — ลีดที่แอดมินพักใบร่างไว้ ยังไม่ได้เลข/เซลล์ (leadpark.py · จำผล 30 วิ)
        #   อ่านไม่ได้ต้องไม่ทำให้รายชื่อลูกค้าโหลดไม่ขึ้น
        try:
            from .leadpark import board
            pk = board()
            cnt["parked"] = pk["stats"]["waiting"]
            if view == "tocode":
                # ตัวช่วยประกอบเลขตัวอย่างในกล่องจ่ายเบอร์ของลีดภายนอก (เลขรันชุดเดียวกับลูกค้า LINE OA)
                pk["codeHelp"] = {"bases": [{"key": b, "type": t} for b, t in C.CODE_BASES],
                                  "month": timezone.localdate().month, "next": C.last_running() + 1,
                                  "post": C.post_help()}     # กดจ่ายแล้วส่งเข้ากลุ่มไหน (บอกก่อนกด)
                for it in pk.get("assigned") or []:      # แท็กท้ายใบ (ชื่อ LINE คำแรก) → ชื่อเล่นในทะเบียน
                    it["sellerNick"] = C.tag_nick(it.get("seller") or "")
                out["parked"] = pk
        except Exception as e:
            out["parkedError"] = str(e)[:120]
        if view == "tocode":
            # "จ่ายแล้ว" — ลูกค้าแชทที่ได้เลขแล้ว 7 วันล่าสุด จ่ายให้ใคร/โดยใคร (เจ้าของ: "อยากรู้ว่าจ่ายให้ใครบ้าง")
            try:
                out["assigned"] = C.assigned_list(emp)
            except Exception as e:
                out["assignedError"] = str(e)[:120]
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
    fb_data_only = C.is_fb(o) and not admin
    if acc == "preview":
        msgs = C.messages(o, limit=10, since=o.awaiting_since)
    else:
        msgs = C.messages(o)
    out = {
        "ok": True,
        "row": C.row_json(o, emp),
        "access": acc,
        "messages": msgs,
        # โปรไฟล์ลูกค้า — เบอร์โทรดึงจากข้อความที่ลูกค้าพิมพ์ (เฉพาะคนที่เห็นแชทเต็ม)
        "profile": C.profile_json(o, acc, [m["text"] for m in msgs if m["dir"] == "in"]),
        "canClaim": not o.owner_id and bool(emp) and (admin or acc == "preview"),
        "canReply": acc == "full" and (admin or mine),
        # ★ 6 ต.ค.69 — ลูกค้า Facebook: เซลล์ได้สิทธิ์ "เก็บข้อมูลเท่านั้น" → ปิดรอบรอ/ตอบไม่ได้ (แอดมินยังทำได้)
        "canDismiss": acc == "full" and bool(o.awaiting_since) and (admin or (mine and not fb_data_only)),
        "canAssign": admin,
        # ลูกค้าจำลองไม่ติดสวิตช์ล็อก (ตอบไปไม่ออกนอกระบบ) — ต้องตรงกับ chat.send_reply
        #   ลูกค้า Facebook มีสวิตช์ของตัวเอง (connect_config.fb_reply: off/test/on) — ต้องตรงกับ fb_send.send_reply
        "replyOn": (False if fb_data_only else
                    C.fb_reply_state(o)[0] if C.is_fb(o) else (reply_on() or C.is_sim_row(o))),
        "replyWhy": (FB_DATA_ONLY if fb_data_only else C.fb_reply_state(o)[1] if C.is_fb(o) else ""),
        "now": timezone.localtime().isoformat(timespec="seconds"),
    }
    if admin:
        out["history"] = C.history(o)
        if C.is_fb(o):                               # ปุ่ม "ใช้แชทนี้ทดสอบการตอบ Facebook" (โหมด test)
            c = C.cfg()
            out["fbTest"] = {"mode": c["fb_reply"], "on": o.id in c["fb_test_rows"]}
    # ข้อมูลลีด (ช่องเดียวกับชีตลีด) — เฉพาะคนที่เห็นแชทเต็ม · เติมอัตโนมัติก่อนส่ง (ไม่ทับที่คนพิมพ์)
    if acc == "full":
        try:
            C.capture_contact(o, msgs)                # เบอร์/ID LINE ที่ลูกค้าให้ (รวมไอดีที่ส่งหลังเราขอ)
            lead = C.autofill(o, [m["text"] for m in msgs if m["dir"] == "in"])
            out["lead"] = C.lead_json(o, lead)
            out["leadEditable"] = bool(admin or mine)
            out["leadOptions"] = C.lead_options()
            if admin:                             # ปุ่ม "จ่ายเบอร์" (โหมดทดลอง) — เฉพาะแอดมิน
                out["codeHelp"] = C.code_help(o, lead)
        except Exception as e:                    # ส่วนลีดพัง ต้องไม่ทำให้เปิดแชทไม่ได้
            out["leadError"] = "โหลดข้อมูลลีดไม่ได้: %s" % str(e)[:120]
    return _j(out)


def api_assign_lead(request):
    """ปุ่ม **"จ่ายเบอร์"** (แอดมิน) — POST `{id, emp, base, admin, reject, code?}`
    · `{id, skip: true|false}` = ปุ่ม "ไม่ต้องจ่ายเบอร์" (ไม่ใช่ลีดขาย → ออกจากแท็บจ่ายเบอร์) / เอากลับเข้าแท็บ
    · `{id, resend: true}` = ปุ่ม "ส่งเข้ากลุ่มอีกครั้ง" (รอบแรกส่งไม่สำเร็จ)

    ออกเลขลีดตามกติกาจริง + โอนลูกค้าให้เซลล์ + จดว่าใครจ่ายเมื่อไหร่
    ★ 6 ต.ค.69 **ส่งใบเข้ากลุ่มจ่ายเบอร์จริง + แท็กเซลล์** (slippost.py · ไม่ลงชีต) — สวิตช์ `slip_post` ปิด = ทดลองเดิม
    """
    ctx, body, bad = _post_guard(request)
    if bad:
        return bad
    if not ctx["admin"]:
        return _j({"ok": False, "error": "จ่ายเบอร์ได้เฉพาะแอดมิน"}, 403)
    o = _row(request, ctx, body.get("id"))
    if not o:
        return _j({"ok": False, "error": "ไม่พบลูกค้ารายนี้"}, 404)
    if "skip" in body:                            # ปุ่ม "ไม่ต้องจ่ายเบอร์" (true) / "เอากลับเข้าแท็บจ่ายเบอร์" (false)
        ok, msg = C.mark_no_code(o, bool(body.get("skip")), by=ctx["name"] or "แอดมิน")
        return _j({"ok": ok, "message" if ok else "error": msg}, 200 if ok else 400)
    if body.get("resend"):
        ok, msg = C.repost_lead(o, by=ctx["name"] or "แอดมิน")
        return _j({"ok": ok, "message" if ok else "error": msg,
                   "post": _post_out(C.lead_of(_row(request, ctx, o.id)))}, 200 if ok else 400)
    try:
        eid = int(body.get("emp") or 0)
    except Exception:
        eid = 0
    emp = Employee.objects.filter(pk=eid).first() if eid else None
    ok, msg = C.assign_lead(o, emp, str(body.get("base") or ""), bool(body.get("admin")),
                            bool(body.get("reject")), str(body.get("code") or ""), by=ctx["name"] or "แอดมิน")
    if not ok:
        return _j({"ok": False, "error": msg}, 400)
    return _j({"ok": True, "message": msg, "post": _post_out(C.lead_of(_row(request, ctx, o.id)))})


def _post_out(rec) -> dict | None:
    """ผลส่งใบเข้ากลุ่มสำหรับหน้าเว็บ (ตัด message id ของ LINE ออก — ไม่จำเป็นต้องออกหน้าเว็บ)"""
    pi = getattr(rec, "post_info", None) or {}
    return {k: v for k, v in pi.items() if k != "mid"} or None


def api_park_assign(request):
    """จ่ายเบอร์ **ลีดภายนอก** จากห้องพัก Lead (TikTok/FB/เบอร์กลาง … · แอดมิน)
    POST `{mid, emp, base, admin, reject, code?}` · `{mid, skip: true|false}` = ไม่ต้องจ่ายเบอร์ / เอากลับ
    · `{mid, resend: true}` = ส่งเข้ากลุ่มอีกครั้ง

    `mid` = message id ของใบร่างในกลุ่ม (ไม่ใช่ข้อมูลส่วนบุคคล) · เก็บใน ExtLead + ★ 6 ต.ค.69 ส่งเข้ากลุ่มจ่ายเบอร์จริง
    (สิทธิ์ในระบบ = จดว่าจ่ายให้ใคร · ไม่ลงชีต)
    """
    ctx, body, bad = _post_guard(request)
    if bad:
        return bad
    if not ctx["admin"]:
        return _j({"ok": False, "error": "จ่ายเบอร์ได้เฉพาะแอดมิน"}, 403)
    from . import leadpark as LP
    mid = str(body.get("mid") or "")
    by = ctx["name"] or "แอดมิน"
    if "skip" in body:
        ok, msg = LP.skip(mid, bool(body.get("skip")), by=by)
        return _j({"ok": ok, "message" if ok else "error": msg}, 200 if ok else 400)
    if body.get("resend"):
        ok, msg = LP.repost(mid, by=by)
        from .models import ExtLead
        return _j({"ok": ok, "message" if ok else "error": msg,
                   "post": _post_out(ExtLead.objects.filter(message_id=mid).first())}, 200 if ok else 400)
    try:
        eid = int(body.get("emp") or 0)
    except Exception:
        eid = 0
    emp = Employee.objects.filter(pk=eid).first() if eid else None
    ok, msg, e = LP.assign(mid, emp, str(body.get("base") or ""), bool(body.get("admin")),
                           bool(body.get("reject")), str(body.get("code") or ""), by=by)
    if not ok:
        return _j({"ok": False, "error": msg}, 400)
    return _j({"ok": True, "message": msg, "code": e.code, "slip": LP.slip_text(e), "post": _post_out(e)})


def api_lead(request):
    """แก้ข้อมูลลีด 1 ช่อง — POST `{id, field, value}` · เจ้าของลูกค้าหรือแอดมินเท่านั้น

    ทีละช่อง (ไม่ใช่ทั้งฟอร์ม) — 2 คนแก้คนละช่องพร้อมกันจะไม่ทับกัน
    """
    ctx, body, bad = _post_guard(request)
    if bad:
        return bad
    o = _row(request, ctx, body.get("id"))
    if not o:
        return _j({"ok": False, "error": "ไม่พบลูกค้ารายนี้"}, 404)
    emp = ctx["emp"]
    if not (ctx["admin"] or (emp and o.owner_id == emp.id)):
        return _j({"ok": False, "error": "แก้ได้เฉพาะลูกค้าของคุณ — กด \"รับลูกค้า\" ก่อน"}, 403)
    ok, msg = C.save_lead_field(o, str(body.get("field") or ""), body.get("value"), by=ctx["name"])
    if not ok:
        return _j({"ok": False, "error": msg}, 400)
    o = _row(request, ctx, o.id)
    return _j({"ok": True, "message": msg, "lead": C.lead_json(o)})


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
    if C.is_fb(o) and not ctx["admin"]:          # ★ 6 ต.ค.69 เจ้าของสั่ง: ไม่ใช่ LINE = สิทธิ์เก็บข้อมูลเท่านั้น
        return _j({"ok": False, "error": FB_DATA_ONLY}, 403)
    from .chat import ReplyError, send_reply
    try:
        if C.is_fb(o):                               # ลูกค้า Facebook → Send API ของเพจ (fb_send.py)
            from .fb_send import send_reply as fb_send_reply
            row = fb_send_reply(o, body.get("text") or "", ctx["user"])
        else:
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
    if C.is_fb(o) and not ctx["admin"]:          # ลูกค้า Facebook ของเซลล์ = เก็บข้อมูลเท่านั้น (แอดมินดูแลแชท)
        return _j({"ok": False, "error": FB_DATA_ONLY}, 403)
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
        # กลุ่มจ่ายเบอร์ที่เลือกเอง — บอทตัวส่งต้องอยู่ในกลุ่มนั้นจริง (ไม่งั้นใบส่งไม่ออกทุกครั้งแบบเงียบๆ)
        cur = C.cfg()
        for key in ("slip_group", "slip_group_reject"):
            if not errs and new.get(key) and new[key] != cur.get(key):
                try:
                    from dashboard.services.line_channels import push_group_error
                    e = push_group_error(new[key])
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
    fb = {}
    try:                                             # สถานะดึงแชท Facebook รอบล่าสุด (การ์ดตั้งค่า)
        from dashboard.services import cache_store
        from dashboard.services import meta
        from django.conf import settings as _s
        from . import fb_webhook
        fb = {"last": (cache_store.get_kv("fb_live_last") or {}).get("data") or {},
              "configured": meta.is_configured(),
              "pages": [{"id": pid, "name": C.fb_page_name(pid)} for pid in sorted(meta.pages())],
              # Messenger webhook (Facebook ส่งมาเอง) — ตัวหลัก · การดึงด้านบนเป็นตัวสำรอง
              "webhook": {"url": (getattr(_s, "SITE_URL", "") or "").rstrip("/") + "/api/meta/webhook",
                          "verifySet": bool(getattr(_s, "META_WEBHOOK_VERIFY_TOKEN", "")),
                          "secretSet": bool(getattr(_s, "META_APP_SECRET", "")),
                          "last": fb_webhook.last()}}
    except Exception:
        pass
    slip = {}
    try:                                             # กลุ่มจ่ายเบอร์ที่ปุ่ม "จ่ายเบอร์" จะส่งเข้า (การ์ดตั้งค่า)
        from . import slippost
        slip = {"rooms": slippost.rooms(c), "candidates": slippost.lead_rooms()}
    except Exception:
        pass
    return _j({"ok": True, "cfg": c, "roster": C.roster(14, c), "duty": _duty(c),
               "teamsAvail": teams, "groups": _alert_groups(), "status": _status(ctx),
               "sellers": C.seller_list(), "fb": fb, "slip": slip})


def api_fb_test(request):
    """แอดมินกำหนด/ยกเลิก "แชททดสอบการตอบ Facebook" — POST `{id, on}` (ใช้ในโหมด fb_reply = test)

    ทดสอบกับแชทของคนในบริษัท (เจ้าของทักเพจจาก FB ตัวเอง) ก่อนเปิดให้ตอบลูกค้าจริงทุกคน
    """
    ctx, body, bad = _post_guard(request)
    if bad:
        return bad
    if not ctx["admin"]:
        return _j({"ok": False, "error": "เฉพาะแอดมิน"}, 403)
    o = _row(request, ctx, body.get("id"))
    if not o or not C.is_fb(o):
        return _j({"ok": False, "error": "ไม่พบแชท Facebook รายนี้"}, 404)
    c = C.cfg()
    rows = [r for r in c["fb_test_rows"] if r != o.id]
    if body.get("on"):
        rows = (rows + [o.id])[-20:]
    c["fb_test_rows"] = rows
    if not C.save_cfg(c):
        return _j({"ok": False, "error": "บันทึกไม่สำเร็จ"}, 500)
    return _j({"ok": True, "message": ("ตั้งเป็นแชททดสอบแล้ว — ตอบจาก Connect ได้" if body.get("on")
                                       else "ยกเลิกแชททดสอบแล้ว")})


def api_fb_webhook(request):
    """Messenger webhook (แอดมิน) — GET = เพจไหนผูกกับแอปแล้ว · POST = ผูกเพจของเรากับแอป (messages + message_echoes)

    ผูกแล้ว Facebook ส่งแชทของเพจมาที่ `/api/meta/webhook` เอง · ต้องลงทะเบียน Callback URL ในหน้าแอป Meta ก่อน
    """
    ctx = _ctx(request)
    if not ctx or not ctx["admin"]:
        return _j({"ok": False, "error": "เฉพาะแอดมิน"}, 403)
    from . import fb_webhook
    if request.method == "POST":
        res = fb_webhook.subscribe_pages()
        ok = bool(res) and all(v == "ok" for v in res.values())
        return _j({"ok": ok, "result": {C.fb_page_name(k): v for k, v in res.items()},
                   "error": "" if ok else "ผูกไม่สำเร็จบางเพจ — ดูรายละเอียดในผลลัพธ์"}, 200 if ok else 400)
    st = fb_webhook.subscription_status()
    return _j({"ok": True, "pages": [dict(v, id=k, name=C.fb_page_name(k)) for k, v in st.items()]})


def api_test(request):
    """โหมดทดสอบ (แอดมินเท่านั้น) — GET = สถานะ · POST `{action}`:
       `as` {team}  = ใช้หน้าจอแบบบัญชีเซลล์จำลองของทีมนั้น (สร้างให้ถ้ายังไม่มี)
       `exit`       = กลับเป็นแอดมิน
       `customer` {text?} = ลูกค้าจำลองทักเข้ามา 1 คน
       `say` {id, text}   = ลูกค้าจำลองพิมพ์ต่อ (ทดสอบรอบรอ/เลยเวลา)
       `clear`      = ล้างข้อมูลทดสอบทั้งหมด (ลูกค้าจริงที่บัญชีจำลองรับไว้ → คืนคิว)
    """
    ctx = _ctx(request)
    if not ctx or not ctx["realAdmin"]:
        return _j({"ok": False, "error": "โหมดทดสอบใช้ได้เฉพาะแอดมิน/ผู้บริหาร"}, 403)
    if request.method != "POST":
        return _j({"ok": True, "as": ctx["testAs"], "name": ctx["name"] if ctx["testAs"] else "",
                   "counts": C.sim_counts(), "teams": C.cfg()["teams"]})
    body = _body(request)
    act = (body.get("action") or "").strip()
    if act == "as":
        team = str(body.get("team") or "").strip().upper()
        if team not in C.cfg()["teams"]:
            return _j({"ok": False, "error": "ทีม %s ไม่อยู่ในเวร" % (team or "?")}, 400)
        emp = C.test_seller(team)
        request.session[TEST_AS_KEY] = emp.id
        return _j({"ok": True, "message": "ตอนนี้คุณใช้หน้าจอแบบ %s" % emp.nickname})
    if act == "exit":
        request.session.pop(TEST_AS_KEY, None)
        return _j({"ok": True, "message": "กลับเป็นแอดมินแล้ว"})
    if act == "customer":
        o = C.sim_customer(body.get("text") or "")
        return _j({"ok": True, "id": o.id if o else 0,
                   "message": "ลูกค้าจำลองทักเข้ามาแล้ว — อยู่ในแท็บ \"รอรับ\" ของทีม %s" % (o.team if o else "-")})
    if act == "say":
        text = (body.get("text") or "").strip()
        if not text:
            return _j({"ok": False, "error": "ยังไม่ได้พิมพ์ข้อความ"}, 400)
        o = C.sim_say(body.get("id"), text)
        if not o:
            return _j({"ok": False, "error": "พิมพ์แทนได้เฉพาะลูกค้าจำลอง"}, 400)
        return _j({"ok": True, "message": "ลูกค้าจำลองส่งข้อความแล้ว"})
    if act == "clear":
        request.session.pop(TEST_AS_KEY, None)
        r = C.sim_clear(by=ctx["realName"] or "แอดมิน")
        return _j({"ok": True, "result": r,
                   "message": "ล้างแล้ว — ลูกค้าจำลอง %d คน · บัญชีจำลอง %d บัญชี%s" % (
                       r["customers"], r["sellers"],
                       (" · คืนลูกค้าจริงเข้าคิว %d คน" % r["released"]) if r["released"] else "")})
    return _j({"ok": False, "error": "ไม่รู้จักคำสั่ง %s" % act}, 400)


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
