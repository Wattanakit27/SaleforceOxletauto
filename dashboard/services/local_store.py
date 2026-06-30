"""
Local Postgres store — เก็บ cache/kv/config/forms ใน DB ในเครื่อง (Django ORM)
แทน Supabase บน VPS. ฟังก์ชันชื่อ/รูปแบบคืนค่า ตรงกับ supabase_client เพื่อสลับ backend ง่าย
(ผ่าน cache_store facade). best-effort: DB ล่ม/ยังไม่ migrate = คืน None/{} ไม่ throw
(ยกเว้น save_dashboard_cache/save_sheet_config ที่ปล่อย exception ให้ caller รู้ผล)
"""
from django.utils import timezone


def available() -> bool:
    """มี DB ให้ใช้ไหม (มี ENGINE จริง — postgres/sqlite). DB ล่มจริงจะถูกจับใน try ของแต่ละ fn"""
    try:
        from django.conf import settings
        return bool(settings.DATABASES.get("default", {}).get("ENGINE"))
    except Exception:
        return False


def _iso(dt):
    return timezone.localtime(dt).isoformat() if dt else None


# ── dashboard pre-compute cache (key='main') ──
def save_dashboard_cache(data: dict) -> None:
    from dashboard.models import KVStore
    KVStore.objects.update_or_create(key="main", defaults={"data": data})


def get_dashboard_cache() -> dict | None:
    try:
        from dashboard.models import KVStore
        o = KVStore.objects.filter(key="main").first()
        return {"data": o.data, "updated_at": _iso(o.updated_at)} if o else None
    except Exception:
        return None


def get_dashboard_cache_age() -> float | None:
    try:
        from dashboard.models import KVStore
        o = KVStore.objects.filter(key="main").only("updated_at").first()
        return (timezone.now() - o.updated_at).total_seconds() if o else None
    except Exception:
        return None


# ── kv (heartbeat / followup log) ──
def set_kv(k: str, data: dict) -> None:
    try:
        from dashboard.models import KVStore
        KVStore.objects.update_or_create(key=k, defaults={"data": data})
    except Exception:
        pass


def get_kv(k: str) -> dict | None:
    try:
        from dashboard.models import KVStore
        o = KVStore.objects.filter(key=k).first()
        return {"data": o.data, "updated_at": _iso(o.updated_at)} if o else None
    except Exception:
        return None


# ── sheet_config override (เก็บเป็น blob ก้อนเดียว key='sheet_config') ──
def get_sheet_config() -> dict:
    try:
        from dashboard.models import KVStore
        o = KVStore.objects.filter(key="sheet_config").first()
        return (o.data if o else {}) or {}
    except Exception:
        return {}


def save_sheet_config(items: list) -> None:
    from dashboard.models import KVStore
    cfg = {}
    for i in items:
        if i.get("key"):
            cfg[i["key"]] = {
                "spreadsheet_id": (i.get("spreadsheet_id") or "").strip(),
                "sheet_name": (i.get("sheet_name") or "").strip(),
            }
    KVStore.objects.update_or_create(key="sheet_config", defaults={"data": cfg})


# ── ฟอร์ม finance/loan ──
def insert_form(kind: str, row: dict):
    """คืน id ของ record ที่สร้าง (best-effort — ล้มเหลวคืน None)"""
    try:
        from dashboard.models import FormSubmission
        return FormSubmission.objects.create(kind=kind, data=row).pk
    except Exception:
        return None
