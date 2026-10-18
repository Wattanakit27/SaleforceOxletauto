"""★ 18 ต.ค.69 แชทที่ให้เบอร์/ID LINE เข้าห้องพัก Lead เอง (เลิกให้แอดมินกด "รับ lead")

เจ้าของ "ต่อไปนี้ไม่มีแล้วการให้แอดมินมากดรับหลีดไปพัก เราส่งไปเองเลยดีกว่า"
ค่าตั้งต้นในโค้ดเปลี่ยนเป็นเปิดแล้ว แต่บนเซิร์ฟเวอร์บันทึก `room_chat_auto: false` ไว้ใน KV `connect_config`
(ค่าที่บันทึกชนะค่าตั้งต้น) → เปลี่ยนเป็น true ครั้งเดียวตอน migrate · ไม่มีค่าที่บันทึกไว้ = ไม่ต้องทำอะไร
"""
from django.db import migrations


def forward(apps, schema_editor):
    KV = apps.get_model("dashboard", "KVStore")
    row = KV.objects.filter(key="connect_config").first()
    if not row or not isinstance(row.data, dict) or row.data.get("room_chat_auto") is True:
        return
    data = dict(row.data)
    data["room_chat_auto"] = True
    row.data = data
    row.save(update_fields=["data", "updated_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("checkout", "0040_social_comment_category_label"),
        ("dashboard", "0019_dev_request"),
    ]

    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
