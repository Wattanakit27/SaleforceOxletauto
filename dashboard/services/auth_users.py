"""ระบบบัญชีผู้ใช้ (สมัคร / อนุมัติ / login) — เก็บใน Supabase table `app_users`.

ไม่มี Django models (โปรเจกต์ไม่มี local DB) → ใช้ Supabase REST ผ่าน supabase_client.
รหัสผ่านเก็บเป็น hash ด้วย Django password hasher (PBKDF2) — ไม่เก็บ plaintext.

สถานะบัญชี (status):
  - pending  : สมัครแล้ว รอ admin กด approve ในเมล
  - active   : อนุมัติแล้ว login ได้
  - rejected : ถูกปฏิเสธ

SQL สร้างตาราง (รันใน Supabase SQL editor ครั้งเดียว):
  create table if not exists app_users (
    id uuid primary key default gen_random_uuid(),
    email text unique not null,
    password_hash text not null,
    full_name text,
    nickname text,
    role text not null default 'seller',      -- 'seller' | 'executive' | 'admin'
    seller_name text,                          -- เซลล์: ชื่อในระบบ (map ข้อมูล dashboard)
    status text not null default 'pending',    -- 'pending' | 'active' | 'rejected'
    created_at timestamptz default now(),
    approved_at timestamptz
  );
"""
import urllib.parse
from datetime import datetime, timezone

from django.contrib.auth.hashers import make_password, check_password
from django.core import signing

from . import supabase_client as sb

TABLE = "app_users"

# ── Role mapping: ป้ายภาษาไทย (จากฟอร์มสมัคร) ↔ role key (เก็บใน DB = position ใน session) ──
# role key ตรงกับ position เดิม: admin = แอดมินสูงสุด (มีเครื่องมือ admin ครบ),
# executive = ผู้บริหาร (เห็นทุกอย่างแต่ไม่มีเครื่องมือ), seller = เซลล์ (เห็นเฉพาะตัวเอง)
ROLE_LABELS = {
    "seller": "เซลล์",
    "executive": "ผู้บริหาร",
    "admin": "แอดมินสูงสุด",
}
VALID_ROLES = set(ROLE_LABELS.keys())

# salt สำหรับ signed token ในลิงก์ approve/reject (ป้องกันการปลอม + หมดอายุได้)
_APPROVAL_SALT = "oxlet-account-approval-v1"
APPROVAL_MAX_AGE = 14 * 24 * 3600  # ลิงก์ในเมลใช้ได้ 14 วัน


def is_enabled() -> bool:
    """ระบบบัญชีใช้ได้เมื่อ Supabase ถูกตั้งค่าแล้ว."""
    return sb.is_configured()


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def role_label(role: str) -> str:
    return ROLE_LABELS.get((role or "").strip().lower(), role or "")


def _q(value: str) -> str:
    """encode ค่าเป็น query string ปลอดภัย (กัน + . @ ในอีเมลทำ query เพี้ยน)."""
    return urllib.parse.quote(value, safe="")


def get_user_by_email(email: str) -> dict | None:
    email = normalize_email(email)
    if not email:
        return None
    rows = sb.select_rows(TABLE, f"email=eq.{_q(email)}&select=*", limit=1)
    return rows[0] if rows else None


def get_user_by_id(uid: str) -> dict | None:
    if not uid:
        return None
    rows = sb.select_rows(TABLE, f"id=eq.{_q(str(uid))}&select=*", limit=1)
    return rows[0] if rows else None


def create_pending_user(*, email: str, password: str, full_name: str,
                        nickname: str, role: str, seller_name: str = "") -> dict:
    """สร้างบัญชีสถานะ pending. raise ValueError ถ้าอีเมลซ้ำ/role ไม่ถูกต้อง."""
    email = normalize_email(email)
    role = (role or "").strip().lower()
    if role not in VALID_ROLES:
        raise ValueError("บทบาทไม่ถูกต้อง")
    if get_user_by_email(email):
        raise ValueError("อีเมลนี้ถูกใช้สมัครแล้ว")

    row = {
        "email": email,
        "password_hash": make_password(password),
        "full_name": (full_name or "").strip(),
        "nickname": (nickname or "").strip(),
        "role": role,
        "seller_name": (seller_name or "").strip(),
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    saved = sb.insert_row(TABLE, row)
    if not saved or not isinstance(saved, list):
        raise Exception("สร้างบัญชีไม่สำเร็จ (Supabase ไม่คืนข้อมูล)")
    return saved[0]


def set_status(uid: str, status: str) -> dict | None:
    """เปลี่ยนสถานะบัญชี (active/rejected). คืน row ที่อัปเดต."""
    patch = {"status": status}
    if status == "active":
        patch["approved_at"] = datetime.now(timezone.utc).isoformat()
    rows = sb.update_rows(TABLE, f"id=eq.{_q(str(uid))}", patch)
    return rows[0] if rows else None


def verify_login(email: str, password: str) -> tuple[dict | None, str]:
    """ตรวจ email+password. คืน (user, "") ถ้าผ่าน, (None, error_th) ถ้าไม่ผ่าน."""
    user = get_user_by_email(email)
    if not user or not check_password(password, user.get("password_hash") or ""):
        return None, "อีเมลหรือรหัสผ่านไม่ถูกต้อง"
    status = (user.get("status") or "").lower()
    if status == "pending":
        return None, "บัญชีนี้รอผู้ดูแลอนุมัติ — โปรดรอเมลตอบกลับ"
    if status == "rejected":
        return None, "บัญชีนี้ถูกปฏิเสธ — กรุณาติดต่อผู้ดูแลระบบ"
    if status != "active":
        return None, "บัญชีนี้ยังใช้งานไม่ได้"
    return user, ""


def session_payload(user: dict) -> dict:
    """แปลง user row → dict สำหรับเก็บใน session (รูปแบบเดียวกับ _session_user)."""
    role = (user.get("role") or "seller").strip().lower()
    nickname = user.get("nickname") or user.get("full_name") or user.get("email")
    return {
        "user_id": f"acct:{user.get('id')}",
        "nickname": nickname,
        "display_name": user.get("full_name") or nickname,
        "position": role,
        # เซลล์: ชื่อในระบบ (ใช้ดึงข้อมูลส่วนตัวที่ /me/)
        "seller_name": (user.get("seller_name") or nickname or "").strip(),
        "email": user.get("email"),
    }


# ── signed token สำหรับลิงก์ approve/reject ในเมล ──
def make_action_token(uid: str, action: str) -> str:
    """สร้าง signed token (tamper-proof + หมดอายุได้) ใส่ใน URL ของเมล."""
    return signing.dumps({"uid": str(uid), "act": action}, salt=_APPROVAL_SALT)


def load_action_token(token: str) -> tuple[str, str]:
    """ตรวจ token → (uid, action). raise signing.BadSignature/SignatureExpired ถ้าไม่ผ่าน."""
    data = signing.loads(token, salt=_APPROVAL_SALT, max_age=APPROVAL_MAX_AGE)
    return data["uid"], data["act"]
