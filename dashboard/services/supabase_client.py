"""Supabase client — REST (PostgREST) ผ่าน requests (ไม่ลง SDK เพิ่ม)

ใช้ secret key (สิทธิ์เต็ม ข้าม RLS) ฝั่ง server เท่านั้น.
- sheet_cache: mirror ข้อมูลจาก Google Sheets (dashboard อ่านจากนี่แทน)
- loan_applications / finance_checks: เก็บฟอร์มจากหน้าเซลล์
"""
import threading
from datetime import datetime, timezone

import requests
from django.conf import settings

# ── Lazy background sync ──
# เวลา dashboard อ่าน Supabase แล้วเจอข้อมูลเก่า > TTL → ยิง sync เบื้องหลัง (ไม่ block)
# ทำให้ local สดเองโดยไม่ต้องมี external cron (บน Vercel ใช้ n8n คู่กัน)
_STALE_TTL = 120  # วินาที
_bg_lock = threading.Lock()
_bg_syncing = False


def _trigger_bg_sync():
    global _bg_syncing
    with _bg_lock:
        if _bg_syncing:
            return
        _bg_syncing = True

    def _run():
        global _bg_syncing
        try:
            sync_all_sheets_to_supabase()
        except Exception:
            pass
        finally:
            _bg_syncing = False

    threading.Thread(target=_run, daemon=True).start()


def is_configured() -> bool:
    # ปิด Supabase ทั้งระบบเมื่อ USE_SUPABASE=False → ทุก read/write short-circuit (ไม่ยิงเน็ต/ไม่ค้าง)
    # (มิ.ย.69) ลบ Supabase project ทิ้งชั่วคราว → อ่าน Google ตรง · เปิดกลับด้วย USE_SUPABASE=True + ตั้ง URL/SECRET ใหม่
    if not getattr(settings, "USE_SUPABASE", False):
        return False
    return bool(getattr(settings, "SUPABASE_URL", "") and getattr(settings, "SUPABASE_SECRET_KEY", ""))


def _base() -> tuple[str, str]:
    url = (getattr(settings, "SUPABASE_URL", "") or "").rstrip("/")
    key = (getattr(settings, "SUPABASE_SECRET_KEY", "") or "").strip()
    if not url or not key:
        raise ValueError("ยังไม่ได้ตั้ง SUPABASE_URL / SUPABASE_SECRET_KEY ใน .env")
    return url, key


def _headers(key: str, extra: dict | None = None) -> dict:
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if extra:
        h.update(extra)
    return h


def insert_row(table: str, row: dict) -> list:
    """INSERT 1 แถว → คืน row ที่สร้าง (พร้อม id)."""
    url, key = _base()
    r = requests.post(
        f"{url}/rest/v1/{table}",
        headers=_headers(key, {"Prefer": "return=representation"}),
        json=row, timeout=20,
    )
    if r.status_code not in (200, 201):
        raise Exception(f"Supabase insert {table} {r.status_code}: {r.text[:300]}")
    return r.json()


def select_rows(table: str, query: str = "select=*", limit: int | None = None) -> list:
    """SELECT แบบ generic — query เป็น PostgREST query string (เช่น 'email=eq.x&select=*').
    คืน list ของ row (dict). raise ถ้า request ล้มเหลว."""
    url, key = _base()
    q = query
    if limit is not None:
        q = f"{q}&limit={limit}"
    r = requests.get(f"{url}/rest/v1/{table}?{q}", headers=_headers(key), timeout=20)
    if r.status_code != 200:
        raise Exception(f"Supabase select {table} {r.status_code}: {r.text[:300]}")
    return r.json()


def update_rows(table: str, match: str, patch: dict) -> list:
    """PATCH (UPDATE) แถวที่ตรงกับ match (PostgREST filter เช่น 'id=eq.123').
    คืน row ที่อัปเดต. raise ถ้าล้มเหลว."""
    url, key = _base()
    r = requests.patch(
        f"{url}/rest/v1/{table}?{match}",
        headers=_headers(key, {"Prefer": "return=representation"}),
        json=patch, timeout=20,
    )
    if r.status_code not in (200, 204):
        raise Exception(f"Supabase update {table} {r.status_code}: {r.text[:300]}")
    try:
        return r.json()
    except Exception:
        return []


def _trim_row(row: list) -> list:
    """ตัด cell ว่างท้ายแถวทิ้ง — ลดขนาด jsonb (เขียนเร็วขึ้น, กัน statement timeout).
    ปลอดภัย: aggregator อ่านด้วย cell(r, idx) ซึ่งคืน '' ถ้า idx เกินความยาวแถวอยู่แล้ว."""
    i = len(row)
    while i > 0 and (row[i - 1] is None or str(row[i - 1]).strip() == ""):
        i -= 1
    return row[:i] if i < len(row) else row


def upsert_sheet(sheet_key: str, rows: list) -> None:
    """upsert ข้อมูล 1 sheet ลง sheet_cache (sheet_key เป็น primary key)."""
    url, key = _base()
    rows = [_trim_row(r) for r in rows]   # ลดขนาดก้อน → เขียนเร็วขึ้น (leads 15k แถวเคย timeout)
    payload = {
        "sheet_key": sheet_key,
        "rows": rows,
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }
    r = requests.post(
        f"{url}/rest/v1/sheet_cache?on_conflict=sheet_key",
        headers=_headers(key, {"Prefer": "resolution=merge-duplicates,return=minimal"}),
        json=payload, timeout=60,
    )
    if r.status_code not in (200, 201, 204):
        raise Exception(f"Supabase upsert sheet_cache({sheet_key}) {r.status_code}: {r.text[:300]}")


def get_sheet(sheet_key: str) -> list | None:
    """อ่าน rows ของ 1 sheet จาก sheet_cache. คืน None ถ้าไม่มี."""
    url, key = _base()
    r = requests.get(
        f"{url}/rest/v1/sheet_cache?sheet_key=eq.{sheet_key}&select=rows",
        headers=_headers(key), timeout=30,
    )
    if r.status_code != 200:
        raise Exception(f"Supabase get sheet_cache({sheet_key}) {r.status_code}: {r.text[:300]}")
    data = r.json()
    if not data:
        return None
    return data[0].get("rows", [])


def sync_all_sheets_to_supabase() -> dict:
    """(Phase 2 มิ.ย.69) เลิก mirror leads ดิบเข้า sheet_cache — Supabase เก็บแค่ผลสรุป (dashboard_cache) → no-op.
    รีเฟรช dashboard ใช้ precompute_dashboard() อ่าน Google ตรงแทน (กัน CPU เต็มจากการยัด 15k แถว)."""
    return {"skipped": "raw mirror disabled (Phase 2 — เก็บแค่ dashboard_cache)"}
    from .google_sheets import (
        fetch_sheet, fetch_leads_by_month_tabs, fetch_sales_by_month_tabs,
        fetch_bookings_by_month_tabs, fetch_live_by_month_tabs,
    )
    results: dict = {}

    # leads + sales ใช้ month tabs (ตรงกับที่ dashboard ใช้)
    try:
        rows = fetch_leads_by_month_tabs()
        upsert_sheet("leads", rows)
        results["leads"] = len(rows)
    except Exception as e:
        results["leads"] = f"error: {e}"

    try:
        rows = fetch_sales_by_month_tabs()
        upsert_sheet("sales_reports", rows)
        results["sales_reports"] = len(rows)
    except Exception as e:
        results["sales_reports"] = f"error: {e}"

    try:
        rows = fetch_bookings_by_month_tabs()
        upsert_sheet("bookings", rows)
        results["bookings"] = len(rows)
    except Exception as e:
        results["bookings"] = f"error: {e}"

    try:
        rows = fetch_live_by_month_tabs()
        upsert_sheet("live_sessions", rows)
        results["live_sessions"] = len(rows)
    except Exception as e:
        results["live_sessions"] = f"error: {e}"

    for k in ("live_followups", "employees"):
        try:
            rows = fetch_sheet(k)
            upsert_sheet(k, rows)
            results[k] = len(rows)
        except Exception as e:
            results[k] = f"error: {e}"

    return results


def fetch_all_from_supabase() -> dict:
    """อ่าน 6 sheets จาก sheet_cache ใน query เดียว (เร็วกว่าอ่านทีละ sheet)."""
    url, key = _base()
    keys = ["leads", "sales_reports", "bookings", "live_sessions", "live_followups", "employees"]
    r = requests.get(
        f"{url}/rest/v1/sheet_cache?select=sheet_key,rows,synced_at", headers=_headers(key), timeout=60,
    )
    if r.status_code != 200:
        raise Exception(f"Supabase get_all sheet_cache {r.status_code}: {r.text[:300]}")
    data = r.json()
    cache = {row["sheet_key"]: row.get("rows", []) for row in data}
    out = {}
    for k in keys:
        if k not in cache:
            raise Exception(f"sheet_cache ยังไม่มี '{k}' (ต้อง sync ก่อน)")
        out[k] = cache[k]

    # ข้อมูลเก่าเกิน TTL → ยิง sync เบื้องหลัง (คืนข้อมูลปัจจุบันทันที ไม่รอ)
    try:
        stamps = [row["synced_at"] for row in data if row.get("synced_at")]
        if stamps:
            oldest = min(stamps).replace("Z", "+00:00")
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(oldest)).total_seconds()
            if age > _STALE_TTL:
                _trigger_bg_sync()
    except Exception:
        pass
    return out


def save_dashboard_cache(data: dict) -> None:
    """เก็บผล dashboard ที่คำนวณไว้แล้ว (pre-compute) ลง Supabase — 1 แถว (key='main')."""
    url, key = _base()
    payload = {
        "key": "main",
        "data": data,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    r = requests.post(
        f"{url}/rest/v1/dashboard_cache?on_conflict=key",
        headers=_headers(key, {"Prefer": "resolution=merge-duplicates,return=minimal"}),
        json=payload, timeout=90,
    )
    if r.status_code not in (200, 201, 204):
        raise Exception(f"Supabase save dashboard_cache {r.status_code}: {r.text[:200]}")


def get_dashboard_cache() -> dict | None:
    """อ่านผล dashboard ที่ pre-compute ไว้. คืน {'data':..., 'updated_at':...} หรือ None."""
    if not is_configured():
        return None
    url, key = _base()
    try:
        r = requests.get(
            f"{url}/rest/v1/dashboard_cache?key=eq.main&select=data,updated_at",
            headers=_headers(key), timeout=30,
        )
        if r.status_code != 200:
            return None
        rows = r.json()
        return rows[0] if rows else None
    except Exception:
        return None


def set_kv(k: str, data: dict) -> None:
    """เก็บ status เล็กๆ ลง dashboard_cache (key เฉพาะ) — ใช้ log cron heartbeat / followup. ไม่ throw."""
    if not is_configured():
        return
    try:
        url, key = _base()
        requests.post(
            f"{url}/rest/v1/dashboard_cache?on_conflict=key",
            headers=_headers(key, {"Prefer": "resolution=merge-duplicates,return=minimal"}),
            json={"key": k, "data": data, "updated_at": datetime.now(timezone.utc).isoformat()},
            timeout=15,
        )
    except Exception:
        pass


def get_kv(k: str) -> dict | None:
    """อ่าน status ที่เก็บด้วย set_kv. คืน {'data':..., 'updated_at':...} หรือ None."""
    if not is_configured():
        return None
    try:
        url, key = _base()
        r = requests.get(
            f"{url}/rest/v1/dashboard_cache?key=eq.{k}&select=data,updated_at",
            headers=_headers(key), timeout=15,
        )
        if r.status_code != 200:
            return None
        rows = r.json()
        return rows[0] if rows else None
    except Exception:
        return None


def get_dashboard_cache_age() -> float | None:
    """อายุ (วินาที) ของผล pre-compute ล่าสุด — อ่านแค่ updated_at (เบา). None ถ้าไม่มี."""
    if not is_configured():
        return None
    url, key = _base()
    try:
        r = requests.get(
            f"{url}/rest/v1/dashboard_cache?key=eq.main&select=updated_at",
            headers=_headers(key), timeout=15,
        )
        if r.status_code != 200 or not r.json():
            return None
        ts = r.json()[0]["updated_at"].replace("Z", "+00:00")
        return (datetime.now(timezone.utc) - datetime.fromisoformat(ts)).total_seconds()
    except Exception:
        return None


def get_sheet_config() -> dict:
    """อ่าน override ของ SHEET_CONFIG จาก Supabase → {key: {spreadsheet_id, sheet_name}}.
    คืน {} ถ้าไม่ได้ตั้งค่า/ตารางไม่มี (→ ใช้ default hardcode)."""
    if not is_configured():
        return {}
    url, key = _base()
    try:
        r = requests.get(
            f"{url}/rest/v1/sheet_config?select=key,spreadsheet_id,sheet_name",
            headers=_headers(key), timeout=15,
        )
        if r.status_code != 200:
            return {}
        out = {}
        for row in r.json():
            out[row["key"]] = {
                "spreadsheet_id": (row.get("spreadsheet_id") or "").strip(),
                "sheet_name": (row.get("sheet_name") or "").strip(),
            }
        return out
    except Exception:
        return {}


def save_sheet_config(items: list) -> None:
    """upsert override config — items = [{key, spreadsheet_id, sheet_name}, ...]."""
    url, key = _base()
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = [{
        "key": i["key"],
        "spreadsheet_id": (i.get("spreadsheet_id") or "").strip(),
        "sheet_name": (i.get("sheet_name") or "").strip(),
        "updated_at": now_iso,
    } for i in items if i.get("key")]
    r = requests.post(
        f"{url}/rest/v1/sheet_config?on_conflict=key",
        headers=_headers(key, {"Prefer": "resolution=merge-duplicates,return=minimal"}),
        json=payload, timeout=30,
    )
    if r.status_code not in (200, 201, 204):
        raise Exception(f"Supabase save sheet_config {r.status_code}: {r.text[:200]}")


def ping() -> dict:
    """ทดสอบการเชื่อมต่อ + เช็คว่าตารางมีอยู่. คืน dict สถานะ."""
    url, key = _base()
    out = {"url": url, "tables": {}}
    for t in ("sheet_cache", "loan_applications", "finance_checks"):
        try:
            r = requests.get(f"{url}/rest/v1/{t}?select=*&limit=1", headers=_headers(key), timeout=15)
            out["tables"][t] = "ok" if r.status_code == 200 else f"{r.status_code}: {r.text[:120]}"
        except Exception as e:
            out["tables"][t] = f"error: {e}"
    return out
