# -*- coding: utf-8 -*-
"""ลีดจากฟอร์ม "ขอราคาพิเศษ / นัดดูรถ" ของเว็บโชว์รูม → ห้องพัก Lead (13 ต.ค.69 · เจ้าของสั่ง
"เมื่อมีการกรอกข้อมูลส่วนนี้ให้ส่งไปที่กลุ่มพักหลีด")

เดิมฟอร์มบนเว็บโชว์รูมเก็บลงฐานข้อมูลของเว็บโชว์รูมเฉยๆ ไม่มีใครได้รับแจ้ง (เปิดดูได้แค่หน้า admin ของเว็บนั้น)
→ ลูกค้าที่กรอกมาหลุดหายเงียบ ทั้งที่หน้าเว็บบอกว่า "ทีมขายจะติดต่อกลับ"

ทางเดิน:  เว็บโชว์รูม POST /api/showroom/lead (X-Stock-Secret ตัวเดียวกับ webhook สต็อก)
          → โพสต์ **ใบจ่ายลีดฉบับร่าง** (ยังไม่มีเลขรัน · ช่องทาง "web oxlet") เข้ากลุ่ม "ADMIN เก็บ Lead" ด้วยบอทตัวส่ง
          → เก็บลง `GroupChat` ของกลุ่มนั้นเอง (LINE ไม่ส่งข้อความของบอทกลับมาทาง webhook)
          → `leadpark.board()` เห็นเป็นลีดรอจ่ายเบอร์ในห้องพัก Lead ของ Connect ทันที (จ่ายเบอร์/ส่งใบเข้ากลุ่ม ตามขั้นตอนเดิม)

★ ส่ง LINE ไม่สำเร็จ = ยังเก็บลงห้องพัก Lead (ลีดต้องไม่หาย) + จดเหตุผลใน dash_event_log + ตอบเว็บโชว์รูมว่าไม่ได้โพสต์
★ เว็บโชว์รูมส่งซ้ำ (ลองใหม่) = ไม่โพสต์ซ้ำ — กันด้วย message_id `web-lead-<รหัสลีดฝั่งโชว์รูม>`
"""
from __future__ import annotations

import hmac
import json

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

WHAT = "ลีดจากเว็บโชว์รูม (ห้องพัก Lead)"     # ชื่อเรื่องใน dash_event_log — หน้าสถานะระบบเฝ้าให้เองถ้าล้มติดกัน
CHANNEL = "web oxlet"                          # ตัวเลือกในช่อง "ช่องทาง" ของชีตลีด (dropdown) — ตรงตัว
_MAX = 300


def _s(v, n=_MAX) -> str:
    return str(v or "").strip()[:n]


def park_room() -> dict:
    """กลุ่ม "ADMIN เก็บ Lead" ที่ **บอทตัวส่งอยู่** → `{id, name}` · ตั้งเองได้ที่ `connect_config.web_lead_group`
    · ไม่ได้ตั้ง = หาจากชื่อกลุ่ม (`leadpark.PARK_HINTS`) — group id ออกต่อ provider เลือกของบอทเดิมไปก็ส่งไม่ได้"""
    from dashboard.services.line_channels import group_visible_to_push
    from .leadpark import PARK_HINTS
    from .slippost import _kv_groups
    groups = _kv_groups()
    try:
        # อ่านค่าดิบจาก KV (connect.cfg() ตัดคีย์ที่ไม่อยู่ในค่าตั้งต้นทิ้ง)
        from dashboard.services import cache_store
        gid = _s(((cache_store.get_kv("connect_config") or {}).get("data") or {}).get("web_lead_group"), 64)
    except Exception:
        gid = ""
    if gid:
        return {"id": gid, "name": (groups.get(gid) or {}).get("name") or ""}
    hits = []
    for g_id, g in groups.items():
        g = g or {}
        name = g.get("name") or ""
        if any(h in name.lower() for h in PARK_HINTS) and group_visible_to_push(g):
            hits.append((g.get("lastSeen") or "", g_id, name))
    if not hits:
        return {"id": "", "name": ""}
    hits.sort(reverse=True)
    return {"id": hits[0][1], "name": hits[0][2]}


def draft_fields(d: dict) -> dict:
    """ข้อมูลฟอร์ม → ช่องของใบจ่ายลีด (ตัวหน้า NLD + เดือนนี้ · ยังไม่มีเลขรัน = ใบร่างที่ห้องพัก Lead อ่าน)"""
    car = d.get("car") if isinstance(d.get("car"), dict) else {}
    car_bits = [_s(car.get("title"), 120)]
    if _s(car.get("plate"), 30):
        car_bits.append("ทะเบียน " + _s(car.get("plate"), 30))
    if _s(car.get("code"), 20):
        car_bits.append("รหัส " + _s(car.get("code"), 20))
    try:
        price = int(float(str(car.get("price") or 0).replace(",", "")))
    except (TypeError, ValueError):
        price = 0
    if price > 0:
        car_bits.append("ราคา {:,} บาท".format(price))
    more = ["ขอราคาพิเศษ / นัดดูรถ จากเว็บ Oxlet"]
    if _s(d.get("message"), 500):
        more.append("ข้อความ: " + _s(d.get("message"), 500))
    if _s(d.get("email"), 120):
        more.append("อีเมล " + _s(d.get("email"), 120))
    if _s(car.get("url"), 300):
        more.append(_s(car.get("url"), 300))
    return {
        "code": "NLD%d-" % timezone.localtime().month,
        "name": _s(d.get("name"), 80),
        "phone": _s(d.get("phone"), 40),
        "channel": CHANNEL,
        "car": " · ".join(b for b in car_bits if b),
        "more": " · ".join(more),
    }


def receive(d: dict) -> dict:
    """ข้อมูลลีดจากเว็บโชว์รูม → โพสต์ใบร่างเข้ากลุ่มพักลีด + เก็บลงห้องพัก Lead · คืน `{ok, pushed, room, error, duplicate?}`"""
    from dashboard.services import eventlog
    from dashboard.services.line_channels import key_of_token, push_token
    from dashboard.services.line_notify import push_line_message
    from .models import GroupChat
    from .slippost import _sent_id, body, explain, with_tag

    if not (_s(d.get("phone")) or _s(d.get("name"))):
        return {"ok": False, "status": 422, "error": "ไม่มีชื่อและเบอร์โทร"}
    lid = _s(d.get("lead_id"), 40)
    mid = ("web-lead-%s" % lid)[:64] if lid else ""
    if mid and GroupChat.objects.filter(message_id=mid).exists():
        return {"ok": True, "duplicate": True, "pushed": True}

    room = park_room()
    if not room["id"]:
        eventlog.log("line_send", name=WHAT, ok=False, error="ไม่พบกลุ่ม ADMIN เก็บ Lead ที่บอทตัวส่งอยู่")
        return {"ok": False, "status": 503, "error": "ยังไม่พบกลุ่ม ADMIN เก็บ Lead ที่บอทตัวส่งอยู่ — ตั้งได้ที่ connect_config.web_lead_group"}

    text = with_tag(body(draft_fields(d)))       # ★ 20 ต.ค.69 แบบใบใหม่ — บรรทัด "@" ว่างไว้ให้แอดมินแท็กเซลล์
    token = push_token()
    pushed, err, line_mid = False, "", ""
    if not token:
        err = "ยังไม่ได้ตั้ง LINE token ของบอทตัวส่ง"
    else:
        try:
            sc, resp = push_line_message(room["id"], [{"type": "text", "text": text}], token, what=WHAT)
            pushed = sc == 200
            err = "" if pushed else explain(sc, resp)
            line_mid = _sent_id(resp) if pushed else ""
        except Exception as e:                      # เน็ตล่ม — ลีดยังต้องเข้าห้องพัก Lead
            err = "ต่อ LINE ไม่ได้: %s" % str(e)[:120]

    # เก็บลงคลังแชทกลุ่มเสมอ (ส่งไม่สำเร็จก็เก็บ) — ห้องพัก Lead อ่านจากตรงนี้ ลีดต้องไม่หายเพราะ LINE ล่ม
    GroupChat.objects.create(
        chat_type=GroupChat.GROUP, group_id=room["id"], group_name=(room.get("name") or "")[:120],
        message_id=mid or ("web-lead-" + timezone.now().strftime("%Y%m%d%H%M%S%f")),
        sender_id="", sender_name="เว็บ Oxlet", msg_type="text", text=text,
        extra={"source": "web", "pushed": pushed, "error": err, "line_mid": line_mid,
               "lead_id": lid, "page": _s(d.get("source_page"), 60)},
        channel=(key_of_token(token) if token else "")[:24], direction=GroupChat.OUT,
        sent_by_name="เว็บ Oxlet", sent_at=timezone.now())
    try:
        from . import leadpark
        leadpark.forget()                            # ให้ห้องพัก Lead เห็นทันที ไม่ต้องรอแคช 30 วิ
    except Exception:
        pass
    return {"ok": True, "pushed": pushed, "room": room.get("name") or room["id"], "error": err}


@csrf_exempt
@require_POST
def api_web_lead(request):
    """POST จากเว็บโชว์รูม (ฟอร์มขอราคา/นัดดูรถ) · auth = X-Stock-Secret (ตัวเดียวกับ webhook สต็อก)
    ไม่ตั้ง secret = 503 ไม่รับ (ใครรู้ URL ก็ยิงลีดปลอมเข้ากลุ่มได้)"""
    secret = getattr(settings, "STOCK_SYNC_SECRET", "") or ""
    if not secret:
        return JsonResponse({"ok": False, "error": "ยังไม่ได้ตั้ง STOCK_SYNC_SECRET"}, status=503)
    got = request.headers.get("X-Stock-Secret") or ""
    if not hmac.compare_digest(got.encode(), secret.encode()):
        return JsonResponse({"ok": False, "error": "unauthorized"}, status=401)
    try:
        d = json.loads(request.body or "{}")
    except (ValueError, TypeError):
        d = None
    if not isinstance(d, dict):
        return JsonResponse({"ok": False, "error": "body ต้องเป็น JSON object"}, status=400)
    res = receive(d)
    return JsonResponse(res, status=200 if res.get("ok") else res.pop("status", 400), json_dumps_params={"ensure_ascii": False})
