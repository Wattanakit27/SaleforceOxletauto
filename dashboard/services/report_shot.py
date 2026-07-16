"""แคปตาราง "รายงาน จอง/อนุมัติ/ปล่อย" จากแดชบอร์ดเป็นรูป (Playwright headless Chromium) → ส่งเข้า LINE

- render ในเครื่อง/VPS เอง (ไม่ส่งข้อมูลออกนอกเหมือน hcti)
- ต้องมี playwright + chromium: `pip install playwright` + `playwright install chromium --with-deps`
- LINE image message ต้องมี URL แบบ public → เซฟรูปลง MEDIA_ROOT/reports/ (nginx เสิร์ฟ /media/) แล้วส่ง SITE_URL/media/...
- config เก็บใน KVStore (dash_kv key='report_line_config') · best-effort ทุกจุด (พังแล้วไม่ล้มระบบ)
"""
import os
import time
import glob
from django.conf import settings

_DEFAULT_CFG = {"enabled": False, "time": "17:30", "mode": "test", "test_id": "", "group_id": ""}


# ── config (KVStore) ──
def get_report_config() -> dict:
    try:
        from . import cache_store
        raw = (cache_store.get_kv("report_line_config") or {}).get("data") or {}
    except Exception:
        raw = {}
    cfg = dict(_DEFAULT_CFG)
    cfg.update({k: raw[k] for k in _DEFAULT_CFG if k in raw})
    cfg["enabled"] = bool(cfg["enabled"])
    return cfg


def save_report_config(cfg: dict) -> None:
    from . import cache_store
    clean = dict(_DEFAULT_CFG)
    clean.update({k: cfg[k] for k in _DEFAULT_CFG if k in cfg})
    clean["enabled"] = bool(clean["enabled"])
    cache_store.set_kv("report_line_config", clean)


# ── capture ──
def _report_dir() -> str:
    d = os.path.join(settings.MEDIA_ROOT, "reports")
    os.makedirs(d, exist_ok=True)
    return d


def _cleanup_old(days: int = 7) -> None:
    """ลบรูปรายงานเก่ากว่า N วัน (กันสะสม)"""
    try:
        cutoff = time.time() - days * 86400
        for f in glob.glob(os.path.join(_report_dir(), "report_*.png")):
            if os.path.getmtime(f) < cutoff:
                os.remove(f)
    except Exception:
        pass


def capture_report_image() -> str | None:
    """login แดชบอร์ด → แคปการ์ด #rpt-card → เซฟ PNG · คืน path (หรือ None ถ้าพัง/ไม่มี playwright)"""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None
    # ยิงที่ SITE_URL (dev=http://127.0.0.1:8000 · prod=https://โดเมนจริง ผ่าน nginx)
    # → CSRF referer scheme ตรง (อย่าใส่ X-Forwarded-Proto เอง จะทำ CSRF เพี้ยนตอน POST login)
    base = (getattr(settings, "REPORT_SHOT_BASE", "") or getattr(settings, "SITE_URL", "") or "http://127.0.0.1:8000").rstrip("/")
    user = getattr(settings, "OXLET_ADMIN_USER", "admin")
    pw = getattr(settings, "OXLET_ADMIN_PASSWORD", "")
    out = os.path.join(_report_dir(), f"report_{time.strftime('%Y%m%d_%H%M%S')}.png")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            page = browser.new_page(device_scale_factor=3, viewport={"width": 1680, "height": 1000})   # 3x = คมชัดขึ้น (แตะดูเต็มในไลน์แล้วคม)
            page.goto(base + "/login/?bg=1", wait_until="domcontentloaded", timeout=30000)
            page.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")  # เปิดฟอร์ม break-glass (อยู่ใน <details> พับไว้)
            page.wait_for_selector("input[name=username]", state="visible", timeout=10000)
            page.fill("input[name=username]", user)
            page.fill("input[name=password]", pw)
            page.click("button[type=submit]")
            page.wait_for_url("**/dashboard/**", timeout=30000)
            page.wait_for_selector("#rpt-card", state="visible", timeout=30000)
            page.wait_for_timeout(2200)   # ให้ตาราง + ฟอนต์ render ครบ
            page.query_selector("#rpt-card").screenshot(path=out)
            browser.close()
        return out if os.path.exists(out) else None
    except Exception:
        return None


def _public_url(path: str) -> str:
    site = getattr(settings, "SITE_URL", "").rstrip("/")
    rel = os.path.relpath(path, settings.MEDIA_ROOT).replace("\\", "/")
    media = (getattr(settings, "MEDIA_URL", "/media/") or "/media/")
    return f"{site}{media}{rel}"


# ── send ──
def send_report_to_line(target_id: str, caption: str = "") -> tuple[bool, str]:
    """แคป + ส่งรูปรายงานเข้า LINE target · คืน (ok, ข้อความสถานะ/URL)"""
    if not target_id:
        return False, "ไม่มีปลายทาง (target_id)"
    path = capture_report_image()
    if not path:
        return False, "แคปรูปไม่สำเร็จ — เช็ค playwright/chromium ติดตั้งไหม (playwright install chromium --with-deps)"
    url = _public_url(path)
    if not url.lower().startswith("https://"):
        return False, f"รูปยังไม่มี URL https สาธารณะ (SITE_URL={getattr(settings,'SITE_URL','')}) — ต้องรันบน prod ที่มี /media/ เสิร์ฟผ่าน https · path={path}"
    try:
        from .line_notify import push_line_message
        token = getattr(settings, "LINE_CHANNEL_ACCESS_TOKEN", "")
        if not token:
            return False, "ไม่มี LINE_CHANNEL_ACCESS_TOKEN"
        msgs = []
        if caption:
            msgs.append({"type": "text", "text": caption})
        msgs.append({"type": "image", "originalContentUrl": url, "previewImageUrl": url})
        sc, resp = push_line_message(target_id, msgs, token)
        _cleanup_old()
        return (sc == 200), (url if sc == 200 else f"LINE {sc}: {(resp or '')[:200]}")
    except Exception as e:
        return False, f"ส่ง LINE ล้มเหลว: {str(e)[:200]}"


# ── cron: ยิงเมื่อถึงเวลาที่ตั้ง (once/day · anti-dup ด้วย last_sent) ──
def maybe_send_daily_report(now_hhmm: str, today_iso: str) -> bool:
    """เรียกจาก cron_tick · ส่งถ้า enabled + เวลาตรง + ยังไม่ส่งวันนี้ · คืน True ถ้าส่ง"""
    cfg = get_report_config()
    if not cfg["enabled"] or cfg["time"] != now_hhmm:
        return False
    try:
        from . import cache_store
        last = (cache_store.get_kv("report_line_last") or {}).get("data") or {}
        if last.get("date") == today_iso and last.get("time") == now_hhmm:
            return False   # ส่งไปแล้วนาทีนี้ (กันซ้ำถ้า cron ยิงถี่)
    except Exception:
        pass
    target = cfg["test_id"] if cfg["mode"] == "test" else cfg["group_id"]
    if not target:
        return False
    ok, info = send_report_to_line(target, caption="📊 รายงานจอง/อนุมัติ/ปล่อย (อัปเดตอัตโนมัติ)")
    try:
        from . import cache_store
        cache_store.set_kv("report_line_last", {"date": today_iso, "time": now_hhmm, "ok": ok, "info": info[:200]})
    except Exception:
        pass
    return ok
