"""แจ้งเว็บโชว์รูม (oxlet_web) เมื่อรถเปลี่ยนสถานะ / กดปุ่ม Active — webhook /api/stock-update/

★ ปุ่ม Active (13 ต.ค.69 เจ้าของสั่ง): รถขึ้นเว็บเมื่อ "กด Active" + ถึงสเตปพร้อมขาย/จอง เท่านั้น
  - payload มี `active` = Car.web_active · เว็บโชว์รูมเป็นคนตัดสินว่าจะสร้าง/ซ่อน/เปิดคืน
  - เว็บตอบ `listed` (ลูกค้าเห็นอยู่ไหม) กลับมา → เก็บที่ Car.web_listed · พลาด = Car.web_sync_error
    (เดิมยิงแล้วเงียบ ส่งไม่ออกก็ไม่มีใครรู้ — บทเรียน "หยุดส่งเงียบๆ" ของทั้งระบบ)

2 ทาง:
  - notify_showroom(car)  ← post_save ทุกครั้งที่รถอยู่สเตปพร้อมขาย/จอง/ขายแล้ว · ยิงใน thread ไม่บล็อกงาน
  - push_showroom(car)    ← ปุ่ม Active / คำสั่ง showroom_push · รอผลแล้วคืนให้หน้าเว็บบอกผู้ใช้ทันที
ปิดอัตโนมัติถ้ายังไม่ตั้ง env: SHOWROOM_WEBHOOK_URL + STOCK_SYNC_SECRET
"""
import threading
import time
from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.utils import timezone

# สเตปที่เว็บสนใจตอนรถเปลี่ยนสถานะเอง (ตรงกับ api_stock_update ฝั่ง oxlet_web)
#   show → available · reserve → reserved · sold → sold(ซ่อน) · สเตปอื่นไม่ยิง (ประหยัด)
#   ปุ่ม Active ยิงได้ทุกสเตป (เว็บตอบ "waiting" ถ้ายังไม่ถึงพร้อมขาย)
_STAGES = {"show", "reserve", "sold"}
TIMEOUT = 8
BG = True        # เทสต์ปิดไว้ (ยิงตรงในคำขอ ไม่แตก thread ชนฐานข้อมูลทดสอบ)
LOG_KIND = "showroom"


def is_configured():
    return bool(getattr(settings, "SHOWROOM_WEBHOOK_URL", "") and getattr(settings, "STOCK_SYNC_SECRET", ""))


def public_base():
    """โดเมนหน้าเว็บโชว์รูมที่ลูกค้าเปิด — ทำลิงก์ "ดูบนเว็บ"
    SHOWROOM_PUBLIC_URL ก่อน · ไม่ตั้ง = เดาจาก SHOWROOM_WEBHOOK_URL
    (ถ้า webhook ยิงทาง 127.0.0.1/localhost ในเครื่องเดียวกัน เดาไม่ได้ → ไม่มีลิงก์ ดีกว่าลิงก์เสีย)"""
    base = (getattr(settings, "SHOWROOM_PUBLIC_URL", "") or "").strip().rstrip("/")
    if base:
        return base
    u = urlsplit(getattr(settings, "SHOWROOM_WEBHOOK_URL", "") or "")
    if not u.scheme or not u.hostname or u.hostname in ("127.0.0.1", "localhost", "::1", "0.0.0.0"):
        return ""
    return "%s://%s" % (u.scheme, u.netloc)


def web_url(car):
    """ลิงก์หน้ารถบนเว็บโชว์รูม (ผ่าน /stock/<รหัส>/ ที่เด้งไปหน้ารถ) · ไม่มีโดเมน = ''"""
    base = public_base()
    return "%s/stock/%s/" % (base, car.code) if base else ""


def _photo_urls(car):
    """รูปขาย (id/path ใน car.extra['sale_photos']) → URL เต็มที่โชว์รูมโหลดได้
    Drive id (ไม่มี '/') → thumbnail link · disk path (มี '/') → SITE_URL + /media/ + path"""
    ids = (car.extra or {}).get("sale_photos") if isinstance(car.extra, dict) else None
    if not isinstance(ids, list):
        return []
    base = getattr(settings, "SITE_URL", "").rstrip("/")
    media = getattr(settings, "MEDIA_URL", "/media/")
    out = []
    for pid in ids:
        pid = str(pid or "").strip()
        if not pid:
            continue
        if "/" in pid:   # disk path
            url = base + "/" + media.strip("/") + "/" + pid.lstrip("/")
        else:            # Drive id
            try:
                from . import gdrive
                url = gdrive.photo_url(pid)
            except Exception:
                continue
        # key = id/path ต้นทาง (คงที่) → โชว์รูมผูกรูปกับต้นทางไว้ (reconcile ปก/ลบได้ถูกตัว)
        out.append({"url": url, "key": pid})
    return out


def sale_price(car):
    """ราคาขาย (บาท) ที่ส่งไปเว็บ — ช่อง "ราคาขาย" ที่กรอกในระบบ (Car.price) ชนะ ·
    ไม่มี = ราคานำเข้าจาก Car Spend (extra.price_num) · ไม่มีทั้งคู่ = None (เว็บคงราคาเดิมของมัน)
    ลำดับเดียวกับ cars_api `priceNum` / need_match — ราคาบนบอร์ดกับบนเว็บต้องเป็นตัวเดียวกัน"""
    ex = car.extra if isinstance(getattr(car, "extra", None), dict) else {}
    for v in (getattr(car, "price", None), ex.get("price_num")):
        try:
            n = int(float(str(v).replace(",", "").strip()))
        except (TypeError, ValueError):
            continue
        if n > 0:
            return n
    return None


def _payload(car):
    return {
        "code": car.code,
        "stage": car.stage,
        "status": car.status,
        "active": bool(getattr(car, "web_active", False)),
        "price": sale_price(car),
        "brand": car.brand or "",
        "model": car.model or "",
        "year": car.year or None,
        "color": car.color or "",
        "km": car.km or None,
        "plate": car.plate or "",
        "photos": _photo_urls(car),
    }


def _send(payload):
    """ยิง webhook แล้วแปลผล → {ok, listed(True/False/None), action, created, path, error}
    listed=None = เว็บไม่ได้บอก (โชว์รูมรุ่นก่อนมีปุ่ม Active) → ไม่แตะสถานะที่เก็บไว้"""
    url = getattr(settings, "SHOWROOM_WEBHOOK_URL", "")
    secret = getattr(settings, "STOCK_SYNC_SECRET", "")
    if not url or not secret:
        return {"ok": False, "error": "ยังไม่ได้ตั้งค่าการเชื่อมเว็บโชว์รูม (SHOWROOM_WEBHOOK_URL / STOCK_SYNC_SECRET)",
                "unconfigured": True}
    try:
        r = requests.post(url, json=payload, headers={"X-Stock-Secret": secret}, timeout=TIMEOUT)
    except requests.Timeout:
        return {"ok": False, "error": "เว็บโชว์รูมไม่ตอบภายใน %d วินาที" % TIMEOUT}
    except requests.RequestException as e:
        return {"ok": False, "error": "ติดต่อเว็บโชว์รูมไม่ได้ (%s)" % type(e).__name__}
    if r.status_code == 401:
        return {"ok": False, "error": "รหัสลับไม่ตรงกับเว็บโชว์รูม (STOCK_SYNC_SECRET สองฝั่งต้องเหมือนกัน)"}
    try:
        j = r.json()
    except ValueError:
        j = None
    if r.status_code >= 400 or not isinstance(j, dict) or not j.get("ok"):
        why = (j or {}).get("error") if isinstance(j, dict) else ""
        return {"ok": False, "error": "เว็บโชว์รูมตอบ HTTP %d%s" % (r.status_code, (" · " + str(why)) if why else "")}
    action = str(j.get("action") or "")
    if "listed" in j:
        listed = bool(j.get("listed"))
    elif action in ("available", "reserved"):
        listed = True
    elif action == "sold":
        listed = False
    else:
        listed = None
    return {"ok": True, "listed": listed, "action": action, "created": bool(j.get("created")),
            "path": str(j.get("path") or "")}


def _record(code, res):
    """เก็บผลล่าสุดลงรถ — ใช้ .update() (ไม่ยิง post_save ซ้ำ = ไม่วนส่ง webhook)"""
    if res.get("unconfigured"):
        return
    try:
        from .models import Car
        fields = {"web_synced_at": timezone.now(),
                  "web_sync_error": "" if res.get("ok") else (res.get("error") or "ไม่ทราบสาเหตุ")[:200]}
        if res.get("ok") and res.get("listed") is not None:
            fields["web_listed"] = res["listed"]
        Car.objects.filter(pk=code).update(**fields)
    except Exception:
        pass


def _log(code, payload, res, ms, why):
    try:
        from dashboard.services import eventlog
        eventlog.log(LOG_KIND, name=why, target=code, ok=bool(res.get("ok")), ms=ms,
                     stage=payload.get("stage"), active=payload.get("active"),
                     action=res.get("action", ""), listed=res.get("listed"), error=res.get("error", ""))
    except Exception:
        pass


def _run(payload, why, log_ok):
    t0 = time.time()
    res = _send(payload)
    ms = int((time.time() - t0) * 1000)
    _record(payload["code"], res)
    if (log_ok or not res.get("ok")) and not res.get("unconfigured"):
        _log(payload["code"], payload, res, ms, why)
    return res


def _bg(payload, why):
    try:
        _run(payload, why, log_ok=False)
    finally:
        try:
            from django.db import connection
            connection.close()       # thread ของเราเอง — คืน connection ไม่ให้ค้าง
        except Exception:
            pass


def notify_showroom(car):
    """post_save — ยิงเมื่อรถอยู่สเตปที่เว็บสนใจ · ไม่บล็อกการเปลี่ยนสเตป · ผลบันทึกลงรถ"""
    if not is_configured():
        return
    if (getattr(car, "stage", "") or "") not in _STAGES:
        return
    payload = _payload(car)
    if BG:
        threading.Thread(target=_bg, args=(payload, "รถเปลี่ยนสถานะ (อัตโนมัติ)"), daemon=True).start()
    else:
        _run(payload, "รถเปลี่ยนสถานะ (อัตโนมัติ)", log_ok=False)


def push_showroom(car, why="กดปุ่ม Active"):
    """ยิงทันทีแล้วรอผล (ปุ่ม Active / คำสั่ง showroom_push) — ยิงได้ทุกสเตป
    คืน {ok, listed, action, created, path, error, unconfigured?}"""
    return _run(_payload(car), why, log_ok=True)
