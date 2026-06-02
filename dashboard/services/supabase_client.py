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
# ทำให้ local สดเองโดยไม่ต้องมี external cron (บน Vercel ใช้ cron-job.org คู่กัน)
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


def upsert_sheet(sheet_key: str, rows: list) -> None:
    """upsert ข้อมูล 1 sheet ลง sheet_cache (sheet_key เป็น primary key)."""
    url, key = _base()
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
    """อ่าน Google Sheets ทั้งหมด → upsert ลง sheet_cache. คืนสรุปจำนวนแถวต่อ sheet."""
    from .google_sheets import (
        fetch_sheet, fetch_leads_by_month_tabs, fetch_sales_by_month_tabs,
        fetch_bookings_by_month_tabs,
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

    for k in ("live_sessions", "live_followups", "employees"):
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
