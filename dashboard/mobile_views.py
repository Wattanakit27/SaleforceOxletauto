"""หน้า/API สำหรับแอปมือถือ — ★ 9 ต.ค.69 (demo บน iPhone ผ่าน Expo Go)

ทางเดิน login อธิบายไว้ที่ services/mobile_auth.py · หลัง login แอปเรียก API เดิมของเว็บด้วย
`Authorization: Bearer` (dashboard/middleware.py) — ไฟล์นี้มีแค่ส่วนที่เว็บยังไม่มี
"""
import json

from django.http import Http404, HttpResponseRedirect, JsonResponse
from django.http.response import HttpResponseRedirectBase
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .services import eventlog
from .services import mobile_auth as MA


class _AppRedirect(HttpResponseRedirectBase):
    """ส่งกลับเข้าแอป — HttpResponseRedirect ของ Django ไม่ยอมให้ไปที่อยู่แบบ exp:// / oxletauto://"""
    status_code = 302          # คลาสฐานไม่ได้ตั้งไว้ (ไม่ใส่ = 200 เปล่าๆ แล้วเบราว์เซอร์ไม่พากลับเข้าแอป)
    allowed_schemes = ["exp", MA.APP_SCHEME]


def _j(data, status=200):
    return JsonResponse(data, status=status, json_dumps_params={"ensure_ascii": False})


def _page(msg, status=400):
    """หน้าข้อความสั้นๆ ในเบราว์เซอร์ตอน login (คนเห็นจริง ไม่ใช่แอป)"""
    from django.http import HttpResponse
    from django.utils.html import escape
    html = ("<!doctype html><html lang='th'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'><title>Oxlet</title>"
            "<style>body{font-family:'Noto Sans Thai',sans-serif;display:flex;min-height:100vh;align-items:center;"
            "justify-content:center;margin:0;background:#f5f3ff;color:#1f1147}div{max-width:420px;padding:28px;"
            "text-align:center;line-height:1.7}</style></head><body><div>%s<br><br>ปิดหน้านี้แล้วกลับไปที่แอป</div>"
            "</body></html>") % escape(msg)
    return HttpResponse(html, status=status)


def _session_user(request):
    u = request.session.get("oxlet_user")
    return u if isinstance(u, dict) and u.get("position") else None


@require_GET
def m_login(request):
    """แอปเปิดหน้านี้ในเบราว์เซอร์ของระบบ → พาไปหน้า login ตัวเดิมของเว็บ

    `via=line` (ค่าตั้งต้น) = LINE Login ตรงๆ (เซลล์/แอดมิน)
    `via=pw` = หน้า /login/ ที่มีช่องชื่อผู้ใช้+รหัส (คนงาน: ช่าง/ฝ่ายทะเบียน/ล้างรถ — คนที่สแกน QR หน้ารถจริง)
    """
    pid, err = MA.start(request.GET.get("r", ""), request.GET.get("c", ""))
    if err:
        return _page(err)
    nxt = "/m/handoff/%s" % pid
    if _session_user(request):                    # เบราว์เซอร์นี้ login เว็บไว้แล้ว → ไม่ต้องผ่าน LINE ซ้ำ
        return HttpResponseRedirect(nxt)
    if request.GET.get("via") == "pw":
        return HttpResponseRedirect("/login/?next=%s" % nxt)
    return HttpResponseRedirect("/auth/line/start?next=%s" % nxt)


@require_GET
def m_handoff(request, pid):
    """login LINE เสร็จแล้ว → ส่งรหัสใช้ครั้งเดียวกลับเข้าแอป"""
    rec = MA.pending(pid)
    if not rec:
        return _page("ลิงก์หมดอายุแล้ว — กลับไปกด \"เข้าสู่ระบบ\" ในแอปใหม่อีกครั้ง")
    user = _session_user(request)
    if not user:
        return HttpResponseRedirect("/auth/line/start?next=/m/handoff/%s" % pid)
    return _AppRedirect(MA.hand_off(rec, user))


def _me(user: dict) -> dict:
    """ข้อมูลคนที่ login ที่ส่งให้แอป — **ไม่ส่ง LINE user id ออก** (กติกาเดิมทั้งโปรเจกต์)"""
    pos = (user.get("position") or "").strip().lower()
    return {"nickname": user.get("nickname") or user.get("display_name") or "",
            "position": pos, "admin": pos in ("admin", "executive", "ผู้บริหาร", "manager", "exec")}


@csrf_exempt
@require_POST
def m_token(request):
    """แลกรหัสใช้ครั้งเดียว + รหัสลับ PKCE → token ของแอป"""
    try:
        body = json.loads(request.body or b"{}")
    except Exception:
        body = {}
    token, tok, err = MA.exchange(body.get("code"), body.get("verifier"), body.get("device") or "")
    if err:
        return _j({"ok": False, "error": err}, 400)
    eventlog.log("mobile", name="login แอปมือถือ", target=tok.nickname, ok=True, device=tok.device)
    return _j({"ok": True, "token": token, "expires": tok.expires_at.isoformat(), "me": _me(tok.user)})


def _need_token(request):
    tok = getattr(request, "mobile_token", None)
    return tok, (None if tok else _j({"ok": False, "error": "ต้องเข้าสู่ระบบจากแอป", "relogin": True}, 401))


@require_GET
def m_me(request):
    tok, bad = _need_token(request)
    if bad:
        return bad
    return _j({"ok": True, "me": _me(tok.user)})


@csrf_exempt
@require_POST
def m_logout(request):
    tok, bad = _need_token(request)
    if bad:
        return bad
    MA.revoke(tok)
    return _j({"ok": True})


@require_GET
def m_car(request, code):
    """รถ 1 คันสำหรับหน้าสแกน QR ของแอป = ข้อมูลชุดเดียวกับป๊อปอัปรถบนบอร์ด (`car_json`)
    + กติกาเปลี่ยนสเตป (ต้องแนบรูป/หมายเหตุสเตปไหน · เช็คลิสต์) — แอปจะได้ไม่ต้องจำกติกาเอง
    อยู่ใต้ /track/ เพื่อให้ตัวผูก login ของระบบรถ (TrackSessionBridgeMiddleware) ทำงาน
    """
    tok, bad = _need_token(request)
    if bad:
        return bad
    if not request.user.is_authenticated:
        return _j({"ok": False, "error": "บัญชีนี้ยังเข้าระบบติดตามรถไม่ได้ — ให้แอดมินตั้งบทบาทให้ก่อน"}, 403)
    from cars import constants as C
    from cars import roles
    from cars.views import car_json
    try:
        resp = car_json(request, code)
    except Http404:
        return _j({"ok": False, "error": "ไม่พบรถรหัส %s ในระบบ" % code}, 404)
    if resp.status_code != 200:
        return _j({"ok": False, "error": "เปิดข้อมูลรถไม่ได้ (%s)" % resp.status_code}, resp.status_code)
    data = json.loads(resp.content)
    data["ok"] = True
    data["role"] = roles.get_role(request.user) or ""
    data["rules"] = {
        "forceMedia": sorted(C.STAGE_FORCE_MEDIA), "forceNote": sorted(C.STAGE_FORCE_NOTE),
        "checklistStages": roles.checklist_stages_for(request.user), "checklistItems": C.CHECKLIST_ITEMS,
    }
    return _j(data)
