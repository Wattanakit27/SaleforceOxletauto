"""
Cache store facade — เลือก backend อัตโนมัติ:
  • Supabase (REST) ถ้า USE_SUPABASE=True + ตั้งค่าครบ
  • ไม่งั้น PostgreSQL ในเครื่อง (local_store · ORM) — โหมดหลักบน VPS

ให้ฟังก์ชันชื่อเดียวกับ supabase_client → call site เรียกผ่านนี่ตัวเดียว ไม่ต้องรู้ว่าใช้ backend ไหน
ทุกฟังก์ชัน best-effort (DB/Supabase ล่ม = None/{}); save_* ปล่อย exception ให้ caller จับ
"""
from . import supabase_client as _sb
from . import local_store as _ls


def _on_sb() -> bool:
    try:
        return _sb.is_configured()
    except Exception:
        return False


def available() -> bool:
    """มีที่เก็บผล (Supabase หรือ local DB) ให้ใช้ไหม — ใช้ตัดสินว่า cron ควรอุ่น cache / แสดงสถานะ"""
    return _on_sb() or _ls.available()


def backend() -> str:
    return "supabase" if _on_sb() else ("local" if _ls.available() else "none")


def save_dashboard_cache(data):
    return (_sb if _on_sb() else _ls).save_dashboard_cache(data)


def get_dashboard_cache():
    return (_sb if _on_sb() else _ls).get_dashboard_cache()


def get_dashboard_cache_age():
    return (_sb if _on_sb() else _ls).get_dashboard_cache_age()


def set_kv(k, data):
    return (_sb if _on_sb() else _ls).set_kv(k, data)


def get_kv(k):
    return (_sb if _on_sb() else _ls).get_kv(k)


def get_sheet_config():
    return (_sb if _on_sb() else _ls).get_sheet_config()


def save_sheet_config(items):
    return (_sb if _on_sb() else _ls).save_sheet_config(items)


def insert_form(kind: str, row: dict):
    """kind = 'finance' | 'loan'"""
    if _on_sb():
        table = "finance_checks" if kind == "finance" else "loan_applications"
        saved = _sb.insert_row(table, row)
        if saved and isinstance(saved, list):
            return saved[0].get("id")
        return None
    return _ls.insert_form(kind, row)
