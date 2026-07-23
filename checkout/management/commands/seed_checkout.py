"""สร้างกติกา checklist มาตรฐาน 7 ข้อ (ตามประกาศบริษัท 12 ก.ค. 2569) — idempotent
รัน: python manage.py seed_checkout [--group <LINE group id>] [--name "ชื่อห้อง"]
"""
from django.core.management.base import BaseCommand

from checkout.models import ChecklistConfig, ChecklistItem

# 7 หลักฐานบังคับก่อนนำรถออกทุกครั้ง (สเปกข้อ 2)
STANDARD_ITEMS = [
    dict(key="engine_bay", label="ห้องเครื่อง", media_type="photo"),
    dict(key="oil", label="ระดับน้ำมันเครื่อง", media_type="photo"),
    dict(key="coolant", label="ระดับน้ำยาหม้อน้ำ", media_type="photo"),
    dict(key="battery", label="แบตเตอรี่", media_type="photo"),
    dict(key="around", label="รถรอบคัน (หน้า/หลัง/ซ้าย/ขวา)", media_type="photo", min_count=4),
    dict(key="odometer", label="เลขไมล์ + หน้าปัด", media_type="photo",
         special_rule="ต้องชัดระดับ OCR อ่านเลขไมล์ได้"),
    dict(key="dashcam", label="วิดีโอกล้องหน้ารถกำลังบันทึก", media_type="video",
         allow_from_group_shot=False,
         special_rule="เห็นตัวรถ/ทะเบียน + หน้าจอกล้อง + REC + วันเวลา · ยาว 5-10 วิ"),
]


class Command(BaseCommand):
    help = "สร้างกติกา checklist มาตรฐาน 7 ข้อ (เบิก-คืนรถส่วนกลาง)"

    def add_arguments(self, parser):
        parser.add_argument("--group", default="", help="LINE group id ของห้องรับ-ส่ง")
        parser.add_argument("--name", default="รับ-ส่งระหว่างสาขา", help="ชื่อห้อง/สาขา")

    def handle(self, *args, **opts):
        cfg, created = ChecklistConfig.objects.get_or_create(
            name=opts["name"],
            defaults={"room_line_group_id": opts["group"] or f"__placeholder__{opts['name']}"},
        )
        if opts["group"] and cfg.room_line_group_id != opts["group"]:
            cfg.room_line_group_id = opts["group"]
            cfg.save(update_fields=["room_line_group_id"])

        for i, it in enumerate(STANDARD_ITEMS):
            ChecklistItem.objects.update_or_create(
                config=cfg, key=it["key"],
                defaults={
                    "order": i,
                    "label": it["label"],
                    "media_type": it["media_type"],
                    "required": True,
                    "min_count": it.get("min_count", 1),
                    "allow_from_group_shot": it.get("allow_from_group_shot", True),
                    "special_rule": it.get("special_rule", ""),
                },
            )
        n = cfg.items.count()
        verb = "สร้างใหม่" if created else "อัปเดต"
        self.stdout.write(self.style.SUCCESS(
            f"{verb} '{cfg.name}' (group={cfg.room_line_group_id}) - checklist {n} ข้อ"
        ))
