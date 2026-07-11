"""แจ้งเว็บโชว์รูม (oxlet_web) เมื่อรถเปลี่ยนสถานะ — realtime sync ผ่าน webhook (best-effort).

- ยิงเฉพาะสเตปที่โชว์รูมสนใจ (พร้อมขาย/จอง/ขายแล้ว) · สเตปอื่นข้าม (ประหยัด)
- ยิงใน daemon thread → ไม่บล็อกการเปลี่ยนสเตป · ล้มเหลว = เงียบ (pull สำรองจะ reconcile ทีหลัง)
- ปิดอัตโนมัติถ้ายังไม่ตั้ง env: SHOWROOM_WEBHOOK_URL + STOCK_SYNC_SECRET
"""
import threading

import requests
from django.conf import settings

# สเตปฝั่ง tracking ที่ map ไปสถานะโชว์รูม (ตรงกับ api_stock_update ฝั่ง oxlet_web)
#   show → available · reserve → reserved · sold → sold(ซ่อน)
_STAGES = {"show", "reserve", "sold"}


def _post(url, secret, payload):
    try:
        requests.post(url, json=payload, headers={"X-Stock-Secret": secret}, timeout=5)
    except Exception:
        pass  # best-effort — โชว์รูมล่ม/เน็ตหลุด = ข้าม (pull สำรองจะตามเก็บ)


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


def notify_showroom(car):
    """ยิง webhook แจ้งโชว์รูมถ้ารถอยู่สเตปที่เกี่ยว — non-blocking, best-effort."""
    url = getattr(settings, "SHOWROOM_WEBHOOK_URL", "")
    secret = getattr(settings, "STOCK_SYNC_SECRET", "")
    if not url or not secret:
        return
    if (getattr(car, "stage", "") or "") not in _STAGES:
        return
    payload = {
        "code": car.code,
        "stage": car.stage,
        "status": car.status,
        "brand": car.brand or "",
        "model": car.model or "",
        "year": car.year or None,
        "color": car.color or "",
        "km": car.km or None,
        "plate": car.plate or "",
        "photos": _photo_urls(car),
    }
    threading.Thread(target=_post, args=(url, secret, payload), daemon=True).start()
