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

_DEFAULT_CFG = {"enabled": False, "time": "17:30", "mode": "test", "test_id": "", "group_id": "",
                # ช่วงวันที่ของข้อมูลในรูปที่ส่ง: month=เดือนปัจจุบัน · today=วันปัจจุบัน · range=ระบุเอง
                "date_mode": "month", "date_from": "", "date_to": ""}


def _apply_date_mode(page, cfg) -> None:
    """ตั้งตัวกรองวันที่ของแดชบอร์ดก่อนแคป ตาม config ของการ์ด (เรียกหลัง login/สลับแท็บ · best-effort)"""
    mode = (cfg or {}).get("date_mode") or "month"
    try:
        page.wait_for_function("typeof setDfRange === 'function' && typeof dfThisMonth === 'function'", timeout=30000)
        if mode == "today":
            page.evaluate("setDf(-1)")
        elif mode == "range":
            f = str((cfg or {}).get("date_from") or "").strip()
            t = str((cfg or {}).get("date_to") or "").strip()
            if f and t:
                page.evaluate("(a) => setDfRange(a[0], a[1])", [f, t])
            else:
                page.evaluate("dfThisMonth()")
        else:
            page.evaluate("dfThisMonth()")
        page.wait_for_timeout(1800)   # รอ render ใหม่ตามช่วงที่ตั้ง
    except Exception:
        pass


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


# แต่ละรูปที่จะแคป: (element id, wrapper id ที่ซ่อนอยู่ height:0 ต้องเปิดก่อน)
_SHOT_TARGETS = [
    ("rpt-shot", "rpt-shot-wrap"),            # ตารางรายงาน จอง/อนุมัติ/ปล่อย (เวอร์ชันอ่านง่าย)
    ("rpt-shot-teams", "rpt-shot-teams-wrap"),  # กราฟแท่งการแข่งขันรายทีม (ปล่อย)
]


def capture_report_images(cfg: dict | None = None) -> list[str]:
    """login แดชบอร์ด → แคป #rpt-shot + #rpt-shot-teams → เซฟ PNG · คืน list ของ path (ว่าง = พัง/ไม่มี playwright)
    ทำใน browser session เดียว (login ครั้งเดียว แคปหลายรูป)"""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return []
    # ยิงที่ SITE_URL (dev=http://127.0.0.1:8000 · prod=https://โดเมนจริง ผ่าน nginx)
    # → CSRF referer scheme ตรง (อย่าใส่ X-Forwarded-Proto เอง จะทำ CSRF เพี้ยนตอน POST login)
    base = (getattr(settings, "REPORT_SHOT_BASE", "") or getattr(settings, "SITE_URL", "") or "http://127.0.0.1:8000").rstrip("/")
    user = getattr(settings, "OXLET_ADMIN_USER", "admin")
    pw = getattr(settings, "OXLET_ADMIN_PASSWORD", "")
    ts = time.strftime("%Y%m%d_%H%M%S")
    outs: list[str] = []
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
            # รอ render เสร็จก่อนตั้งช่วงวันที่ (ไม่งั้นโดน init ทับ)
            try:
                page.wait_for_selector(".ntab", state="visible", timeout=45000)
                page.wait_for_timeout(600)
            except Exception:
                pass
            _apply_date_mode(page, cfg)   # ช่วงวันที่ตามที่ตั้งไว้ (None = เดือนปัจจุบัน)
            # #rpt-shot / #rpt-shot-teams ซ่อนใน wrapper height:0 → เปิดให้เห็นก่อนแคป
            # timeout สูง (35s) กัน cold start: /api/dashboard คำนวณสด ~8-20s ตอน cache เย็น
            try:
                page.wait_for_selector("#rpt-shot", state="attached", timeout=35000)
                page.wait_for_timeout(2200)   # ให้ตาราง + ฟอนต์ render ครบ
            except Exception:
                pass
            for el_id, wrap_id in _SHOT_TARGETS:
                try:
                    # ต้องเป็น arrow function ถึงจะรับ arg ได้ (Playwright ไม่ให้ arguments[0] ใน expression ธรรมดา)
                    page.evaluate(
                        "(id) => { var w=document.getElementById(id); if(w){w.style.height='auto'; w.style.overflow='visible';} }",
                        wrap_id,
                    )
                    page.wait_for_timeout(350)
                    el = page.query_selector("#" + el_id)
                    if not el:
                        continue
                    pth = os.path.join(_report_dir(), f"report_{ts}_{el_id}.png")
                    el.screenshot(path=pth)
                    if os.path.exists(pth):
                        outs.append(pth)
                except Exception:
                    continue
            # fallback: ถ้าแคป #rpt-shot ไม่ได้เลย → ลอง #rpt-card (ตารางเว็บตัวเต็ม)
            if not outs:
                try:
                    page.wait_for_selector("#rpt-card", state="visible", timeout=15000)
                    page.wait_for_timeout(2000)
                    pth = os.path.join(_report_dir(), f"report_{ts}_rpt-card.png")
                    page.query_selector("#rpt-card").screenshot(path=pth)
                    if os.path.exists(pth):
                        outs.append(pth)
                except Exception:
                    pass
            browser.close()
    except Exception:
        return outs
    return outs


# back-compat: เดิมชื่อ capture_report_image (คืน path เดียว)
def capture_report_image() -> str | None:
    imgs = capture_report_images()
    return imgs[0] if imgs else None


def _report_caption() -> str:
    """ข้อความก่อนรูป: 'ผลงานทีม ตั้งแต่วันที่ 1-<วันนี้>/<เดือน>/<ปี พ.ศ.> ค่ะ' (โซนไทย)"""
    try:
        from .fetch_dashboard import bangkok_now
        now = bangkok_now()
        return f"ผลงานทีม ตั้งแต่วันที่ 1-{now.day}/{now.month}/{now.year + 543} ค่ะ"
    except Exception:
        return "ผลงานทีม (อัปเดตอัตโนมัติ) ค่ะ"


def _public_url(path: str) -> str:
    site = getattr(settings, "SITE_URL", "").rstrip("/")
    rel = os.path.relpath(path, settings.MEDIA_ROOT).replace("\\", "/")
    media = (getattr(settings, "MEDIA_URL", "/media/") or "/media/")
    return f"{site}{media}{rel}"


# ── send ──
def _caption_message(caption: str, mention_all: bool) -> dict:
    """สร้าง message ข้อความนำหน้ารูป · mention_all=True → textV2 แท็ก @All (เฉพาะกลุ่ม)"""
    if mention_all:
        # LINE textV2: {all} = placeholder → substitution mention type=all (แท็กทุกคนในกลุ่ม)
        return {
            "type": "textV2",
            "text": caption + " {all}",
            "substitution": {"all": {"type": "mention", "mentionee": {"type": "all"}}},
        }
    return {"type": "text", "text": caption}


def send_report_to_line(target_id: str, caption: str = "", mention_all: bool = False) -> tuple[bool, str]:
    """แคป + ส่ง caption + รูปรายงาน (2 รูป: ตาราง + กราฟทีม) เข้า LINE target · คืน (ok, ข้อความสถานะ/URL)
    - caption ว่าง = ใช้ _report_caption() (ผลงานทีม ตั้งแต่ 1-<วันนี้>...)
    - mention_all=True = แท็ก @All (ใช้เฉพาะส่งเข้ากลุ่ม · 1:1 แท็กไม่ได้)"""
    if not target_id:
        return False, "ไม่มีปลายทาง (target_id)"
    paths = capture_report_images()
    if not paths:
        return False, "แคปรูปไม่สำเร็จ — เช็ค playwright/chromium ติดตั้งไหม (playwright install chromium --with-deps)"
    urls = [_public_url(p) for p in paths]
    bad = [u for u in urls if not u.lower().startswith("https://")]
    if bad:
        return False, f"รูปยังไม่มี URL https สาธารณะ (SITE_URL={getattr(settings,'SITE_URL','')}) — ต้องรันบน prod ที่มี /media/ เสิร์ฟผ่าน https · url={bad[0]}"
    try:
        from .line_notify import push_line_message
        token = getattr(settings, "LINE_CHANNEL_ACCESS_TOKEN", "")
        if not token:
            return False, "ไม่มี LINE_CHANNEL_ACCESS_TOKEN"
        cap = caption or _report_caption()
        msgs = [_caption_message(cap, mention_all)]
        for u in urls:
            msgs.append({"type": "image", "originalContentUrl": u, "previewImageUrl": u})
        sc, resp = push_line_message(target_id, msgs, token)
        _cleanup_old()
        return (sc == 200), ("  ".join(urls) if sc == 200 else f"LINE {sc}: {(resp or '')[:250]}")
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
    is_group = cfg["mode"] == "group"
    target = cfg["group_id"] if is_group else cfg["test_id"]
    if not target:
        return False
    # ส่งเข้ากลุ่ม = แท็ก @All · ส่งทดสอบเข้า 1:1 = ข้อความธรรมดา (แท็กไม่ได้)
    ok, info = send_report_to_line(target, mention_all=is_group)
    try:
        from . import cache_store
        cache_store.set_kv("report_line_last", {"date": today_iso, "time": now_hhmm, "ok": ok, "info": info[:200]})
    except Exception:
        pass
    return ok


# ══════════════════════════════════════════════════════════════════════════════
# ยอด LEAD (สรุปย่อ) → LINE  — แคปการ์ด #leadsummary-card ส่งเข้ากลุ่ม (config แยกจากรายงานรายวัน)
# ══════════════════════════════════════════════════════════════════════════════
_LEAD_CFG_KEY = "leadsummary_line_config"


def get_lead_config() -> dict:
    try:
        from . import cache_store
        raw = (cache_store.get_kv(_LEAD_CFG_KEY) or {}).get("data") or {}
    except Exception:
        raw = {}
    cfg = dict(_DEFAULT_CFG)
    cfg.update({k: raw[k] for k in _DEFAULT_CFG if k in raw})
    cfg["enabled"] = bool(cfg["enabled"])
    return cfg


def save_lead_config(cfg: dict) -> None:
    from . import cache_store
    clean = dict(_DEFAULT_CFG)
    clean.update({k: cfg[k] for k in _DEFAULT_CFG if k in cfg})
    clean["enabled"] = bool(clean["enabled"])
    cache_store.set_kv(_LEAD_CFG_KEY, clean)


def capture_leadsummary() -> str | None:
    """login แดชบอร์ด → แคปการ์ด #leadsummary-card (มองเห็นบนหน้า ไม่ต้องเปิด wrapper) → คืน path"""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None
    base = (getattr(settings, "REPORT_SHOT_BASE", "") or getattr(settings, "SITE_URL", "") or "http://127.0.0.1:8000").rstrip("/")
    user = getattr(settings, "OXLET_ADMIN_USER", "admin")
    pw = getattr(settings, "OXLET_ADMIN_PASSWORD", "")
    out = os.path.join(_report_dir(), f"leadsummary_{time.strftime('%Y%m%d_%H%M%S')}.png")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            page = browser.new_page(device_scale_factor=3, viewport={"width": 1680, "height": 1200})
            page.goto(base + "/login/?bg=1", wait_until="domcontentloaded", timeout=30000)
            page.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
            page.wait_for_selector("input[name=username]", state="visible", timeout=10000)
            page.fill("input[name=username]", user)
            page.fill("input[name=password]", pw)
            page.click("button[type=submit]")
            page.wait_for_url("**/dashboard/**", timeout=30000)
            page.wait_for_selector("#leadsummary-card", state="visible", timeout=35000)   # cold start เผื่อ ~8-20s
            page.wait_for_timeout(1800)
            el = page.query_selector("#leadsummary-card")
            if el:
                el.screenshot(path=out)
            browser.close()
        return out if os.path.exists(out) else None
    except Exception:
        return None


def _lead_caption() -> str:
    try:
        from .fetch_dashboard import bangkok_now
        now = bangkok_now()
        return f"ยอด LEAD ประจำวันที่ {now.day}/{now.month}/{now.year + 543} ค่ะ"
    except Exception:
        return "ยอด LEAD (อัปเดตอัตโนมัติ) ค่ะ"


def send_leadsummary_to_line(target_id: str, caption: str = "", mention_all: bool = False) -> tuple[bool, str]:
    """แคป #leadsummary-card → ส่ง caption + รูปเข้า LINE · คืน (ok, สถานะ/URL)"""
    if not target_id:
        return False, "ไม่มีปลายทาง (target_id)"
    path = capture_leadsummary()
    if not path:
        return False, "แคปรูปไม่สำเร็จ — เช็ค playwright/chromium (playwright install chromium --with-deps)"
    url = _public_url(path)
    if not url.lower().startswith("https://"):
        return False, f"รูปยังไม่มี URL https สาธารณะ (SITE_URL={getattr(settings,'SITE_URL','')}) — ต้องรันบน prod · url={url}"
    try:
        from .line_notify import push_line_message
        token = getattr(settings, "LINE_CHANNEL_ACCESS_TOKEN", "")
        if not token:
            return False, "ไม่มี LINE_CHANNEL_ACCESS_TOKEN"
        cap = caption or _lead_caption()
        msgs = [_caption_message(cap, mention_all), {"type": "image", "originalContentUrl": url, "previewImageUrl": url}]
        sc, resp = push_line_message(target_id, msgs, token)
        _cleanup_old()
        return (sc == 200), (url if sc == 200 else f"LINE {sc}: {(resp or '')[:250]}")
    except Exception as e:
        return False, f"ส่ง LINE ล้มเหลว: {str(e)[:200]}"


def maybe_send_leadsummary(now_hhmm: str, today_iso: str) -> bool:
    """เรียกจาก cron_tick · ส่ง #leadsummary-card ถ้า enabled + เวลาตรง + ยังไม่ส่งวันนี้"""
    cfg = get_lead_config()
    if not cfg["enabled"] or cfg["time"] != now_hhmm:
        return False
    try:
        from . import cache_store
        last = (cache_store.get_kv("leadsummary_line_last") or {}).get("data") or {}
        if last.get("date") == today_iso and last.get("time") == now_hhmm:
            return False
    except Exception:
        pass
    is_group = cfg["mode"] == "group"
    target = cfg["group_id"] if is_group else cfg["test_id"]
    if not target:
        return False
    ok, info = send_leadsummary_to_line(target, mention_all=is_group)
    try:
        from . import cache_store
        cache_store.set_kv("leadsummary_line_last", {"date": today_iso, "time": now_hhmm, "ok": ok, "info": info[:200]})
    except Exception:
        pass
    return ok


# ══════════════════════════════════════════════════════════════════════════════
# ระบบส่งการ์ดเข้าไลน์ (generic ต่อการ์ด) — แต่ละตารางมีปุ่ม+ตั้งค่าของตัวเอง
# config: KVStore "cardline_<id>" · rpt-card ใช้เวอร์ชันสวย (#rpt-shot + กราฟทีม) · การ์ดอื่นแคป element ตรงๆ
# ══════════════════════════════════════════════════════════════════════════════
_LINE_CARDS = {
    "rpt-card": "รายงาน จอง/อนุมัติ/ปล่อย",
    "leadrecv-card": "จำนวนที่รับ Lead ต่อวัน",
    "purchase-card": "ฝั่งจัดซื้อ (รับซื้อรถ)",
    "bought-card": "รถซื้อเข้า รายคน",
    "leadreport-card": "รายงาน lead (แยกช่องทาง)",
    "leadsummary-card": "ยอด LEAD (สรุปย่อ)",
    "mega-card": "สรุปเต็มรายเซลล์",
    "alloc-card": "จัดสรร Lead ตามคะแนน",
    "scorecard-card": "ตารางคะแนนเซลล์",
    "clipweek-card": "ติดตามคอนเทนต์ (คลิป) รายสัปดาห์",
    "yodrot-card": "ยอดรถเข้า รายรุ่น (จัดซื้อ)",
}

# การ์ดที่ไม่ได้อยู่แท็บ "ภาพรวม" → ต้องสลับแท็บก่อนแคป (ปุ่มแท็บชื่อไทยตรงกับ nav)
_CARD_TAB = {
    "clipweek-card": "ไลฟ์",
    "yodrot-card": "จัดซื้อ",
}


def get_card_config(card_id: str) -> dict:
    try:
        from . import cache_store
        raw = (cache_store.get_kv("cardline_" + card_id) or {}).get("data") or {}
    except Exception:
        raw = {}
    cfg = dict(_DEFAULT_CFG)
    cfg.update({k: raw[k] for k in _DEFAULT_CFG if k in raw})
    cfg["enabled"] = bool(cfg["enabled"])
    return cfg


def save_card_config(card_id: str, cfg: dict) -> None:
    from . import cache_store
    clean = dict(_DEFAULT_CFG)
    clean.update({k: cfg[k] for k in _DEFAULT_CFG if k in cfg})
    clean["enabled"] = bool(clean["enabled"])
    cache_store.set_kv("cardline_" + card_id, clean)


def _capture_element(card_id: str, cfg: dict | None = None) -> str | None:
    """login แดชบอร์ด → แคป element #<card_id> (การ์ดที่มองเห็นบนหน้า) → คืน path
    cfg = อ่านมาก่อนแล้ว (กัน DB read พังหลัง Playwright รันนาน) · None = อ่านเอง"""
    if cfg is None:
        cfg = get_card_config(card_id)
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None
    base = (getattr(settings, "REPORT_SHOT_BASE", "") or getattr(settings, "SITE_URL", "") or "http://127.0.0.1:8000").rstrip("/")
    user = getattr(settings, "OXLET_ADMIN_USER", "admin")
    pw = getattr(settings, "OXLET_ADMIN_PASSWORD", "")
    out = os.path.join(_report_dir(), f"card_{card_id}_{time.strftime('%Y%m%d_%H%M%S')}.png")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            page = browser.new_page(device_scale_factor=3, viewport={"width": 1780, "height": 1400})
            page.goto(base + "/login/?bg=1", wait_until="domcontentloaded", timeout=30000)
            page.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
            page.wait_for_selector("input[name=username]", state="visible", timeout=10000)
            page.fill("input[name=username]", user)
            page.fill("input[name=password]", pw)
            page.click("button[type=submit]")
            page.wait_for_url("**/dashboard/**", timeout=30000)
            # ต้องรอให้โหลดข้อมูล+เรนเดอร์เสร็จก่อน ค่อยตั้งช่วงวันที่ (ไม่งั้นโดน init ตั้งค่าเริ่มต้นทับ)
            try:
                page.wait_for_selector(".ntab", state="visible", timeout=45000)
                page.wait_for_timeout(600)
            except Exception:
                pass
            _apply_date_mode(page, cfg)   # ช่วงวันที่ตามที่ตั้งไว้ต่อการ์ด (อ่านมาก่อน launch browser)
            _tab = _CARD_TAB.get(card_id)
            if _tab:   # การ์ดอยู่คนละแท็บ → กดแท็บก่อน (ไม่งั้นหา element ไม่เจอ)
                try:
                    page.wait_for_selector(".ntab", state="visible", timeout=45000)
                    page.wait_for_timeout(600)
                    page.click(f"button.ntab:has-text('{_tab}')")
                    page.wait_for_timeout(1200)
                except Exception:
                    pass
            page.wait_for_selector("#" + card_id, state="attached", timeout=35000)
            page.wait_for_timeout(1800)
            # ซ่อนปุ่ม "ส่งไลน์" + ไอคอน "?" (ตัวช่วย UI · ไม่ใช่ข้อมูล) ก่อนแคป — รูปสะอาดขึ้น
            try:
                page.evaluate("document.querySelectorAll('.linesend-btn,.info-tip,.no-capture').forEach(function(e){e.style.display='none'})")
            except Exception:
                pass
            # 1) เวอร์ชันอ่านง่าย #<id>-shot (ซ่อนใน wrapper height:0 · เปิดก่อนแคป) — ถ้ามี
            try:
                page.evaluate(
                    "(id)=>{var w=document.getElementById(id); if(w){w.style.height='auto';w.style.overflow='visible';}}",
                    card_id + "-shot-wrap",
                )
                page.wait_for_timeout(400)
                shot = page.query_selector("#" + card_id + "-shot")
                if shot:
                    shot.screenshot(path=out)
                    browser.close()
                    return out if os.path.exists(out) else None
            except Exception:
                pass
            # 2) fallback: แคปการ์ดจริง — ขยาย overflow ให้เห็นครบทุกคอลัมน์ + หดการ์ดพอดีเนื้อหา (กันที่ว่างขวา/คอลัมน์ถูกตัด)
            try:
                page.evaluate(
                    "(id)=>{var c=document.getElementById(id); if(!c)return;"
                    "c.querySelectorAll('*').forEach(function(e){var o=getComputedStyle(e).overflowX; if(o==='auto'||o==='scroll'){e.style.overflow='visible';e.style.maxWidth='none';}});"
                    "c.style.display='inline-block'; c.style.width='fit-content'; c.style.maxWidth='none';}",
                    card_id,
                )
                page.wait_for_timeout(400)
            except Exception:
                pass
            el = page.query_selector("#" + card_id)
            if el:
                el.screenshot(path=out)
            browser.close()
        return out if os.path.exists(out) else None
    except Exception:
        return None


def capture_card(card_id: str) -> list[str]:
    """คืน list ของ path รูปของการ์ด · rpt-card = เวอร์ชันสวย (ตาราง+กราฟทีม) · การ์ดอื่น = element ตรงๆ"""
    cfg = get_card_config(card_id)   # อ่าน config ครั้งเดียว "ก่อน" launch browser (กัน DB read พังหลัง Playwright รันนาน → ตกไป default)
    if card_id == "rpt-card":
        return capture_report_images(cfg)
    p = _capture_element(card_id, cfg)
    return [p] if p else []


def _card_caption(card_id: str) -> str:
    name = _LINE_CARDS.get(card_id, "รายงาน")
    try:
        from .fetch_dashboard import bangkok_now
        now = bangkok_now()
        return f"{name} ประจำวันที่ {now.day}/{now.month}/{now.year + 543} ค่ะ"
    except Exception:
        return f"{name} (อัปเดตอัตโนมัติ) ค่ะ"


def send_card_to_line(card_id: str, target_id: str, caption: str = "", mention_all: bool = False) -> tuple[bool, str]:
    """แคปการ์ด #<card_id> → ส่ง caption + รูปเข้า LINE · คืน (ok, สถานะ/URL)"""
    if card_id not in _LINE_CARDS:
        return False, "การ์ดไม่รองรับการส่งไลน์"
    if not target_id:
        return False, "ไม่มีปลายทาง (target_id)"
    paths = capture_card(card_id)
    if not paths:
        return False, "แคปรูปไม่สำเร็จ — เช็ค playwright/chromium (playwright install chromium --with-deps)"
    urls = [_public_url(p) for p in paths]
    bad = [u for u in urls if not u.lower().startswith("https://")]
    if bad:
        return False, f"รูปยังไม่มี URL https สาธารณะ (SITE_URL={getattr(settings,'SITE_URL','')}) — ต้องรันบน prod · url={bad[0]}"
    try:
        from .line_notify import push_line_message
        token = getattr(settings, "LINE_CHANNEL_ACCESS_TOKEN", "")
        if not token:
            return False, "ไม่มี LINE_CHANNEL_ACCESS_TOKEN"
        cap = caption or _card_caption(card_id)
        msgs = [_caption_message(cap, mention_all)]
        for u in urls:
            msgs.append({"type": "image", "originalContentUrl": u, "previewImageUrl": u})
        sc, resp = push_line_message(target_id, msgs, token)
        _cleanup_old()
        return (sc == 200), ("  ".join(urls) if sc == 200 else f"LINE {sc}: {(resp or '')[:250]}")
    except Exception as e:
        return False, f"ส่ง LINE ล้มเหลว: {str(e)[:200]}"


def maybe_send_cards(now_hhmm: str, today_iso: str) -> None:
    """เรียกจาก cron_tick · ส่งทุกการ์ดที่ enabled + เวลาตรง + ยังไม่ส่งวันนี้
    ⚠️ อ่าน config ทุกการ์ด "ก่อน" รัน Playwright — เพราะ Playwright แคปใบละ ~30-60วิ ทำ DB connection ค้าง
       ถ้าอ่าน config กลางลูป (หลังใบแรกแคป) get_card_config จะพัง → คืน default (enabled=False) → การ์ดที่เหลือถูกข้าม (bug 'ส่งมาอันเดียว')"""
    from . import cache_store
    from django.db import close_old_connections
    # เฟส 1: หาการ์ดที่ต้องส่ง (DB reads ล้วน · connection ยังสด)
    todo = []
    for card_id in _LINE_CARDS:
        try:
            cfg = get_card_config(card_id)
            if not cfg["enabled"] or cfg["time"] != now_hhmm:
                continue
            last = (cache_store.get_kv("cardline_last_" + card_id) or {}).get("data") or {}
            if last.get("date") == today_iso and last.get("time") == now_hhmm:
                continue
            is_group = cfg["mode"] == "group"
            target = cfg["group_id"] if is_group else cfg["test_id"]
            if not target:
                continue
            todo.append((card_id, target, is_group))
        except Exception:
            continue
    # เฟส 2: ส่งทีละใบ (Playwright) · รีเซ็ต connection ก่อนแตะ DB ทุกครั้ง (กันค้างหลังแคป)
    for card_id, target, is_group in todo:
        try:
            close_old_connections()
        except Exception:
            pass
        try:
            ok, info = send_card_to_line(card_id, target, mention_all=is_group)
        except Exception as e:
            ok, info = False, str(e)[:200]
        try:
            close_old_connections()
            cache_store.set_kv("cardline_last_" + card_id,
                               {"date": today_iso, "time": now_hhmm, "ok": ok, "info": info[:200]})
        except Exception:
            pass
