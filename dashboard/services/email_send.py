"""ส่งเมลผ่าน Gmail SMTP (Django core mail).

ใช้ส่งเมล "ขออนุมัติบัญชีใหม่" ไปที่ APPROVAL_NOTIFY_EMAIL (oxletauto@gmail.com)
พร้อมปุ่ม ✅ อนุมัติ / ❌ ปฏิเสธ ที่ลิงก์ไปหน้า /account/review/ (ลิงก์เป็น signed token).

ต้องตั้ง env: GMAIL_APP_PASSWORD (App Password 16 หลักของ EMAIL_HOST_USER) + เปิด 2FA บนบัญชี Gmail.
ถ้าส่งล้มเหลว → raise (view จะแจ้งผู้สมัครว่าส่งเมลไม่ได้ แต่บัญชี pending ถูกบันทึกแล้ว).
"""
import html

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

from .auth_users import role_label


def _esc(v) -> str:
    return html.escape(str(v or "—"))


def send_approval_request(user: dict, approve_url: str, reject_url: str) -> None:
    """ส่งเมลขออนุมัติบัญชีใหม่ไปยังผู้ดูแล. raise ถ้า SMTP ล้มเหลว."""
    to_addr = getattr(settings, "APPROVAL_NOTIFY_EMAIL", "") or settings.EMAIL_HOST_USER
    role = role_label(user.get("role"))
    name = _esc(user.get("full_name") or user.get("nickname"))
    email = _esc(user.get("email"))
    nickname = _esc(user.get("nickname"))
    seller = _esc(user.get("seller_name")) if (user.get("role") == "seller") else "—"

    subject = f"🔔 ขออนุมัติบัญชีใหม่: {user.get('full_name') or user.get('nickname')} ({role})"

    text = (
        f"มีคำขอสมัครบัญชีใหม่เข้าระบบ Oxlet Dashboard\n\n"
        f"ชื่อ: {user.get('full_name') or '—'}\n"
        f"ชื่อเล่น: {user.get('nickname') or '—'}\n"
        f"อีเมล: {user.get('email')}\n"
        f"บทบาทที่ขอ: {role}\n"
        f"ชื่อเซลล์ในระบบ: {user.get('seller_name') or '—'}\n\n"
        f"อนุมัติ: {approve_url}\n"
        f"ปฏิเสธ: {reject_url}\n"
    )

    body = f"""\
<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:520px;margin:0 auto;
            background:#fff;border:1px solid #e5e7eb;border-radius:14px;overflow:hidden">
  <div style="background:#0f172a;color:#fff;padding:18px 22px;font-size:16px;font-weight:700">
    🔔 ขออนุมัติบัญชีใหม่ — Oxlet Dashboard
  </div>
  <div style="padding:22px">
    <p style="margin:0 0 16px;color:#334155;font-size:14px">
      มีผู้สมัครใช้งานระบบ กรุณาตรวจสอบและเลือกอนุมัติหรือปฏิเสธ
    </p>
    <table style="width:100%;border-collapse:collapse;font-size:14px;color:#0f172a">
      <tr><td style="padding:6px 0;color:#64748b;width:130px">ชื่อ</td><td style="padding:6px 0;font-weight:600">{name}</td></tr>
      <tr><td style="padding:6px 0;color:#64748b">ชื่อเล่น</td><td style="padding:6px 0">{nickname}</td></tr>
      <tr><td style="padding:6px 0;color:#64748b">อีเมล (ใช้ login)</td><td style="padding:6px 0">{email}</td></tr>
      <tr><td style="padding:6px 0;color:#64748b">บทบาทที่ขอ</td><td style="padding:6px 0;font-weight:600">{_esc(role)}</td></tr>
      <tr><td style="padding:6px 0;color:#64748b">ชื่อเซลล์ในระบบ</td><td style="padding:6px 0">{seller}</td></tr>
    </table>
    <div style="margin-top:24px;text-align:center">
      <a href="{html.escape(approve_url)}"
         style="display:inline-block;background:#16a34a;color:#fff;text-decoration:none;
                padding:12px 28px;border-radius:10px;font-weight:700;font-size:14px;margin:4px">
        ✅ อนุมัติ
      </a>
      <a href="{html.escape(reject_url)}"
         style="display:inline-block;background:#dc2626;color:#fff;text-decoration:none;
                padding:12px 28px;border-radius:10px;font-weight:700;font-size:14px;margin:4px">
        ❌ ปฏิเสธ
      </a>
    </div>
    <p style="margin:22px 0 0;color:#94a3b8;font-size:12px;text-align:center">
      ลิงก์นี้จะพาไปหน้ายืนยันก่อนทำรายการ และหมดอายุใน 14 วัน
    </p>
  </div>
</div>"""

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[to_addr],
    )
    msg.attach_alternative(body, "text/html")
    msg.send(fail_silently=False)
