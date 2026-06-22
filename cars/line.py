"""
แจ้งเตือน LINE ตอนเปลี่ยนสเตป (ออปชั่น)
- ไม่ตั้ง LINE_CHANNEL_TOKEN/LINE_GROUP_ID -> ไม่ push (no-op) ระบบยังทำงานปกติ
"""
import json
import urllib.request

from django.conf import settings


def notify_stage_change(car, worker_name=""):
    token = getattr(settings, "LINE_CHANNEL_TOKEN", "")
    group = getattr(settings, "LINE_GROUP_ID", "")
    if not (token and group):
        return False  # ยังไม่ตั้งค่า — ข้ามเงียบ ๆ

    text = (
        f"🚗 {car.code} {car.title}\n"
        f"➡️ {car.stage_name}\n"
        f"สาขา: {car.branch_name}"
        + (f"\nโดย: {worker_name}" if worker_name else "")
    )
    payload = {"to": group, "messages": [{"type": "text", "text": text}]}
    req = urllib.request.Request(
        "https://api.line.me/v2/bot/message/push",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        urllib.request.urlopen(req, timeout=5)
        return True
    except Exception:
        return False  # อย่าให้การแจ้งเตือนล้มทำงานหลักพัง
