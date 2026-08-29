"""
ระบบเบิก-คืนรถส่วนกลาง (checkout/) — เฟส 1: โครงข้อมูล
ดูสเปกเต็ม: docs/checkout_plan.md (+ ต้นฉบับ OXLET_CAR_CHECKOUT_SPEC.md)

- แยกเป็น app ระดับบน (ไม่ยัดใน cars/) เพราะเฟส 4 จะขยายไปตรวจ "ห้อง" ที่ไม่เกี่ยวกับรถ
  (เช็คชื่อเข้างาน / งานซ่อม-อู่นอก / ส่งมอบรถลูกค้า) ด้วยเครื่องตรวจตัวเดียว แค่เพิ่ม config
- ใช้ DB จริง (Postgres บน VPS · SQLite ตอน dev) เหมือน cars/ — ต้อง migrate
- หลักการ AI (เฟส 2): AI เป็นด่านแรก ไม่ใช่คนตัดสินสุดท้าย · คนแย้ง/override ได้เสมอ (มีชื่อกำกับ)
"""
from django.db import models
from django.utils import timezone


class ChecklistConfig(models.Model):
    """กติการายห้อง (ผูก LINE group id) — หัวใจของการขยายห้อง: เพิ่มห้อง = เพิ่ม config ไม่แก้โค้ด"""
    room_line_group_id = models.CharField("LINE group id", max_length=64, unique=True)
    name = models.CharField("ชื่อห้อง/สาขา", max_length=80)
    active = models.BooleanField("เปิดใช้", default=True)
    # หน้าต่างเวลา (ปรับตามหน้างานได้ ไม่ต้องแก้โค้ด — สเปกข้อ 6)
    group_window_min = models.PositiveIntegerField("หน้าต่างจับกลุ่มไฟล์ (นาที)", default=5)
    settle_seconds = models.PositiveIntegerField("รอไฟล์หยุดไหลก่อนตรวจ (วินาที)", default=90)
    remind_after_min = models.PositiveIntegerField("ทวงหลังไม่ครบ (นาที)", default=5)
    escalate_after_min = models.PositiveIntegerField("แจ้งหัวหน้าเมื่อเงียบเกิน (นาที)", default=15)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "กติกาห้อง (checklist)"
        verbose_name_plural = "กติกาห้อง (checklist)"

    def __str__(self):
        return self.name


class ChecklistItem(models.Model):
    """1 ข้อในกติกา (เช่น "น้ำยาหม้อน้ำ") — checklist = สิ่งที่ต้องพิสูจน์ได้ ไม่ใช่จำนวนรูปที่ต้องถ่าย"""
    PHOTO, VIDEO = "photo", "video"
    MEDIA_CHOICES = [(PHOTO, "รูป"), (VIDEO, "วิดีโอ")]

    config = models.ForeignKey(ChecklistConfig, on_delete=models.CASCADE, related_name="items")
    order = models.PositiveIntegerField("ลำดับ", default=0)
    key = models.CharField("คีย์", max_length=40)      # engine_bay/oil/coolant/battery/around/odometer/dashcam
    label = models.CharField("ชื่อ", max_length=80)     # "ระดับน้ำยาหม้อน้ำ"
    media_type = models.CharField("ชนิด", max_length=10, choices=MEDIA_CHOICES, default=PHOTO)
    required = models.BooleanField("บังคับ", default=True)
    min_count = models.PositiveIntegerField("จำนวนขั้นต่ำ", default=1)
    # ยอมรับหลักฐานจาก "รูปรวม" ได้ไหม (เช่น ห้องเครื่องมุมกว้าง = ห้องเครื่อง+แบต) · วิดีโอ REC = False เสมอ
    allow_from_group_shot = models.BooleanField("ยอมรับจากรูปรวมได้", default=True)
    special_rule = models.CharField("เงื่อนไขพิเศษ", max_length=160, blank=True)  # "ต้องเห็น REC + วันเวลา"

    class Meta:
        ordering = ["config", "order"]
        verbose_name = "ข้อ checklist"
        verbose_name_plural = "ข้อ checklist"

    def __str__(self):
        return f"{self.config.name} · {self.label}"


class CarMovement(models.Model):
    """1 รอบเบิก-คืนรถ (รถออก → ใช้ → คืน)"""
    OUT_WAITING = "waiting_files"
    CHECKING = "checking"
    APPROVED = "approved"
    INCOMPLETE = "incomplete"
    PENDING_HUMAN = "pending_human"
    SYSTEM_ERROR = "system_error"
    APPROVED_HUMAN = "approved_by_human"
    EQUIPMENT_HOLD = "equipment_hold"
    CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (OUT_WAITING, "รอไฟล์"),
        (CHECKING, "กำลังตรวจ"),
        (APPROVED, "ผ่าน (AI)"),
        (INCOMPLETE, "ไม่ครบ — ทวง"),
        (PENDING_HUMAN, "รอคนยืนยัน"),
        (SYSTEM_ERROR, "ระบบขัดข้อง — คนตรวจ"),
        (APPROVED_HUMAN, "ผ่านโดยคน"),
        (EQUIPMENT_HOLD, "ระงับ — อุปกรณ์เสีย"),
        (CANCELLED, "ยกเลิก"),
    ]
    # สถานะที่ถือว่า "ปล่อยรถได้" (เขียว)
    GREEN = {APPROVED, APPROVED_HUMAN}

    # รถ: FK ไป cars.Car (อาจ match ไม่ได้ตอนแรก → เก็บ plate_text ไว้ด้วย)
    car = models.ForeignKey("cars.Car", on_delete=models.SET_NULL, null=True, blank=True, related_name="movements")
    plate_text = models.CharField("ทะเบียนที่พิมพ์", max_length=30, blank=True)
    config = models.ForeignKey(ChecklistConfig, on_delete=models.SET_NULL, null=True, blank=True)

    borrower_name = models.CharField("ผู้เบิก/ผู้ขับ", max_length=80, blank=True)
    borrower_line_id = models.CharField("LINE id ผู้เบิก", max_length=64, blank=True)
    purpose = models.CharField("วัตถุประสงค์", max_length=120, blank=True)
    destination = models.CharField("ปลายทาง/สาขา", max_length=120, blank=True)

    checked_out_at = models.DateTimeField("เวลาเบิก", null=True, blank=True)
    returned_at = models.DateTimeField("เวลาคืน", null=True, blank=True)
    odo_out = models.PositiveIntegerField("ไมล์ออก (OCR)", null=True, blank=True)
    odo_in = models.PositiveIntegerField("ไมล์เข้า (OCR)", null=True, blank=True)

    status = models.CharField("สถานะ", max_length=20, choices=STATUS_CHOICES, default=OUT_WAITING)
    approved_by = models.CharField("อนุมัติ/ผ่านโดย", max_length=80, blank=True)  # มีชื่อคนกำกับเสมอถ้า override
    damage_reported = models.BooleanField("แจ้งความเสียหายตอนคืน", default=False)
    # ★ ส.ค.69 — จาก log จริง "เบิกน้ำมัน" มักพ่วงมากับการเบิกรถ (และมียกเลิกกลางคันด้วย)
    fuel_requested = models.BooleanField("ขอเบิกน้ำมันด้วย", default=False)
    purpose_key = models.CharField("ประเภทงาน", max_length=20, blank=True)   # ดู constants.PURPOSES
    note = models.TextField("หมายเหตุ", blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "รอบเบิก-คืนรถ"
        verbose_name_plural = "รอบเบิก-คืนรถ"

    def __str__(self):
        who = self.plate_text or (self.car_id or "?")
        return f"{who} · {self.get_status_display()}"

    @property
    def is_open(self):
        """ยังไม่คืน = รถยังอยู่กับผู้เบิก"""
        return self.returned_at is None and self.status != self.CANCELLED


class MovementPhoto(models.Model):
    """ไฟล์หลักฐาน (หลายชิ้นต่อรอบ · phase out=เบิก / in=คืน)"""
    OUT, IN = "out", "in"
    PHASE_CHOICES = [(OUT, "เบิก"), (IN, "คืน")]
    PHOTO, VIDEO = "photo", "video"
    MEDIA_CHOICES = [(PHOTO, "รูป"), (VIDEO, "วิดีโอ")]

    movement = models.ForeignKey(CarMovement, on_delete=models.CASCADE, related_name="photos")
    phase = models.CharField("รอบ", max_length=4, choices=PHASE_CHOICES, default=OUT)
    file = models.FileField("ไฟล์", upload_to="checkout/%Y/%m/", null=True, blank=True)
    media_type = models.CharField("ชนิด", max_length=10, choices=MEDIA_CHOICES, default=PHOTO)

    # จำแนก checklist ข้อไหน (null จนกว่า AI/คนจะจำแนก — เฟส 2)
    checklist_item = models.ForeignKey(ChecklistItem, on_delete=models.SET_NULL, null=True, blank=True)
    ai_label = models.CharField("AI จำแนก", max_length=60, blank=True)
    ai_confidence = models.FloatField("ความมั่นใจ AI", null=True, blank=True)
    phash = models.CharField("perceptual hash (กันรูปซ้ำ)", max_length=32, blank=True, db_index=True)

    line_message_id = models.CharField("LINE message id", max_length=64, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "ไฟล์หลักฐาน"
        verbose_name_plural = "ไฟล์หลักฐาน"


class ViolationLog(models.Model):
    """บันทึกการฝ่าฝืน (หลักฐานฝ่ายบุคคล — ระบบไม่ลงโทษเอง แต่เป็นพยาน)"""
    NO_EVIDENCE = "no_evidence"
    IGNORED = "ignored_reminder"
    REUSED = "reused_photo"
    TYPE_CHOICES = [
        (NO_EVIDENCE, "ออกรถหลักฐานไม่ครบ"),
        (IGNORED, "เมินการทวง (เงียบเกินกำหนด)"),
        (REUSED, "ใช้รูปซ้ำ/ของคนก่อน"),
    ]
    movement = models.ForeignKey(CarMovement, on_delete=models.CASCADE, null=True, blank=True, related_name="violations")
    person = models.CharField("ผู้ฝ่าฝืน", max_length=80, blank=True)
    person_line_id = models.CharField("LINE id", max_length=64, blank=True)
    type = models.CharField("ประเภท", max_length=20, choices=TYPE_CHOICES)
    detail = models.CharField("รายละเอียด", max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "บันทึกฝ่าฝืน"
        verbose_name_plural = "บันทึกฝ่าฝืน"


class EquipmentIssue(models.Model):
    """แจ้งกล้อง/อุปกรณ์เสีย + การอนุมัติให้ออก (log ว่าใครอนุมัติ — หลักฐานตอนเคลมประกัน)"""
    OPEN, APPROVED, RESOLVED = "open", "approved", "resolved"
    STATUS_CHOICES = [(OPEN, "รอจัดการ"), (APPROVED, "อนุมัติให้ออก"), (RESOLVED, "แก้แล้ว")]
    car = models.ForeignKey("cars.Car", on_delete=models.SET_NULL, null=True, blank=True, related_name="equipment_issues")
    reporter = models.CharField("ผู้แจ้ง", max_length=80, blank=True)
    issue = models.CharField("อาการ", max_length=200)
    status = models.CharField("สถานะ", max_length=10, choices=STATUS_CHOICES, default=OPEN)
    approved_by = models.CharField("อนุมัติโดย", max_length=80, blank=True)
    approved_at = models.DateTimeField("อนุมัติเมื่อ", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "แจ้งอุปกรณ์เสีย"
        verbose_name_plural = "แจ้งอุปกรณ์เสีย"


class LineEventLog(models.Model):
    """จด webhook event ดิบ "ก่อนเป็นอย่างแรก" (สเปกข้อ 11.5) — worker ค่อยไล่โหลดไฟล์จากคิวนี้
    เพราะ LINE content API หมดอายุเร็ว ไฟล์หายถาวรถ้า thread ตายกลางทาง · restart แล้วทำต่อได้
    dedupe ด้วย line_message_id (LINE retry webhook ได้)"""
    PENDING, DONE, FAILED, SKIPPED = "pending", "done", "failed", "skipped"
    STATUS_CHOICES = [(PENDING, "รอโหลด"), (DONE, "โหลดแล้ว"), (FAILED, "ล้มเหลว"), (SKIPPED, "ข้าม")]
    line_message_id = models.CharField("LINE message id", max_length=64, unique=True)
    group_id = models.CharField("group id", max_length=64, blank=True, db_index=True)
    sender_line_id = models.CharField("ผู้ส่ง", max_length=64, blank=True)
    event_type = models.CharField("ชนิด event", max_length=20, blank=True)  # text/image/video/sticker
    text = models.TextField("ข้อความ", blank=True)
    raw = models.JSONField("event ดิบ", default=dict, blank=True)
    status = models.CharField("สถานะ", max_length=10, choices=STATUS_CHOICES, default=PENDING)
    attempts = models.PositiveIntegerField("ครั้งที่พยายามโหลด", default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "LINE event (คิวโหลดไฟล์)"
        verbose_name_plural = "LINE event (คิวโหลดไฟล์)"
