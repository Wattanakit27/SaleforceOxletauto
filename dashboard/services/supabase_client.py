"""Supabase client — REST (PostgREST) ผ่าน requests (ไม่ลง SDK เพิ่ม)

ใช้ secret key (สิทธิ์เต็ม ข้าม RLS) ฝั่ง server เท่านั้น.
- sheet_cache: mirror ข้อมูลจาก Google Sheets (dashboard อ่านจากนี่แทน)
- loan_applications / finance_checks: เก็บฟอร์มจากหน้าเซลล์
"""
from datetime import datetime, timezone

import requests
from django.conf import settings


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


def sync_all_sheets_to_supabase() -> dict:
    """(Phase 2 มิ.ย.69) เลิก mirror leads ดิบเข้า sheet_cache — Supabase เก็บแค่ผลสรุป (dashboard_cache) → no-op.
    รีเฟรช dashboard ใช้ precompute_dashboard() อ่าน Google ตรงแทน (กัน CPU เต็มจากการยัด 15k แถว).
    ยังถูกเรียกจาก cron_tick — คงไว้เป็น no-op (upsert_sheet/get_sheet/fetch_all_from_supabase ถูกลบออกแล้ว)."""
    return {"skipped": "raw mirror disabled (Phase 2 — เก็บแค่ dashboard_cache)"}


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
