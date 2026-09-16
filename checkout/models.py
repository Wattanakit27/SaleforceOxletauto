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

    # ★ ก.ย.69 — มุมที่คนงาน "ติ๊กเอง" ว่าถ่ายครบ (คีย์ตาม constants.SHOT_ANGLES_*)
    #   เก็บเป็นลิสต์คีย์ เช่น ["left","right","front","rear","engine","odometer"]
    #   ไม่ครบก็บันทึกได้ — ระบบแค่จดไว้ว่าขาดมุมไหน ให้หัวหน้าเห็น (ไม่บล็อกรถไม่ให้ออก)
    shots_out = models.JSONField("มุมที่ถ่ายตอนเบิก", default=list, blank=True)
    shots_in = models.JSONField("มุมที่ถ่ายตอนคืน", default=list, blank=True)

    # ★ ก.ย.69 — เคสนี้เกิดจากไหน (ใช้แยก "ของจริงจากหน้าเว็บ" ออกจาก "ที่ระบบเดาจากกลุ่ม LINE")
    #   line = บอทอ่านข้อความในกลุ่มแล้วตีความเอง (ยังไม่ยืนยัน — ต้องมีคนตรวจ)
    SRC_WEB, SRC_LINE, SRC_IMPORT = "web", "line", "import"
    SOURCE_CHOICES = [(SRC_WEB, "กดในเว็บ"), (SRC_LINE, "บอทอ่านจากกลุ่ม LINE"),
                      (SRC_IMPORT, "นำเข้าจาก log")]
    source = models.CharField("ที่มา", max_length=10, choices=SOURCE_CHOICES,
                              default=SRC_WEB, db_index=True)

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


class GroupChat(models.Model):
    """แชท LINE ที่วิ่งเข้ามาหาบอท — **ทั้งแชทกลุ่ม และแชท 1:1 กับลูกค้า**
    (★ ก.ย.69 — เจ้าของสั่งให้เก็บลง Postgres · ชื่อคลาสคงเดิมไว้ ไม่ rename ตาราง)

    ต่างจาก `GroupMessage` เดิมที่ยุบทิ้งไปยังไง:
      - **แยกตามกลุ่มชัดเจน** (`group_id` + ชื่อกลุ่ม) → ใช้เป็นคลังแชทของแต่ละกลุ่มได้จริง
      - เก็บ **สติกเกอร์ / LINE emoji / ตำแหน่งรูป** ด้วย ไม่ใช่แค่ข้อความล้วน
      - มี **อายุข้อมูล** (`CHAT_KEEP_DAYS`) ลบของเก่าอัตโนมัติ — คลังแชทที่ไม่มีวันหมดอายุ
        = กองข้อมูลส่วนบุคคลที่โตไม่หยุด (PDPA)

    ⚠️ `sender_id` (LINE userId) เก็บไว้เพื่อ **เทียบชื่อเล่น + แท็กในกลุ่ม** เท่านั้น
       เวลาโชว์บนหน้าเว็บให้ใช้ `sender_name` (ชื่อเล่น) เสมอ — ดู [people.py](people.py)
    ⚠️ รูปภาพ: LINE ไม่ได้ส่งไฟล์มากับ webhook — ส่งมาแค่ `message.id` แล้วต้องไปโหลดจาก
       content API ภายในเวลาจำกัด · ตอนนี้เก็บ `has_media` + `message_id` ไว้ก่อน
       (`media_token` จะถูกเติมตอนทำเฟสโหลดไฟล์เข้า Drive)
    """
    # ★ ก.ย.69 — แยกว่าเป็นแชทกลุ่ม หรือแชทเดี่ยวกับลูกค้า (อายุข้อมูลคนละเกณฑ์)
    GROUP, USER, ROOM = "group", "user", "room"
    TYPE_CHOICES = [(GROUP, "แชทกลุ่ม"), (USER, "ลูกค้าทักเข้า OA"), (ROOM, "ห้องคุย")]
    chat_type = models.CharField("ประเภทแชท", max_length=8, choices=TYPE_CHOICES,
                                 default=GROUP, db_index=True)
    # แชทเดี่ยวไม่มี group id → ว่างได้ (คู่สนทนาดูจาก sender_id แทน)
    group_id = models.CharField("LINE group id", max_length=64, blank=True, db_index=True)
    group_name = models.CharField("ชื่อกลุ่ม", max_length=120, blank=True)
    message_id = models.CharField("LINE message id", max_length=64, unique=True)

    sender_id = models.CharField("LINE user id ผู้ส่ง", max_length=64, blank=True)
    sender_name = models.CharField("ชื่อเล่นผู้ส่ง", max_length=80, blank=True)

    TEXT, IMAGE, VIDEO, AUDIO, FILE, STICKER, LOCATION = (
        "text", "image", "video", "audio", "file", "sticker", "location")
    msg_type = models.CharField("ชนิด", max_length=12, blank=True, db_index=True)
    text = models.TextField("ข้อความ", blank=True)

    # สติกเกอร์ + LINE emoji (อิโมจิยูนิโค้ดปกติอยู่ใน text อยู่แล้ว)
    sticker_id = models.CharField("sticker id", max_length=32, blank=True)
    sticker_package = models.CharField("sticker package", max_length=32, blank=True)
    emojis = models.JSONField("LINE emoji ในข้อความ", default=list, blank=True)
    extra = models.JSONField("ข้อมูลอื่นของ event", default=dict, blank=True)

    has_media = models.BooleanField("มีไฟล์แนบ", default=False, db_index=True)
    media_token = models.CharField("ไฟล์ที่โหลดเก็บแล้ว", max_length=200, blank=True)

    # ★ ก.ย.69 — มี 2 บัญชีแล้ว: ต้องรู้ว่าข้อความนี้ "บอทตัวไหนเป็นคนได้ยิน"
    #   ไม่งั้นพอบัญชีใหม่เริ่มรับด้วย จะแยกไม่ออกว่าใครคุยกับตัวไหน (มาจาก webhook `destination`)
    channel = models.CharField("บัญชีที่รับข้อความ", max_length=24, blank=True, db_index=True)

    sent_at = models.DateTimeField("เวลาในกลุ่ม", null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sent_at", "-id"]
        indexes = [models.Index(fields=["group_id", "-sent_at"])]
        verbose_name = "แชทในกลุ่ม LINE"
        verbose_name_plural = "แชทในกลุ่ม LINE"

    def __str__(self):
        return "%s · %s: %s" % (self.group_name or self.group_id[:10],
                                self.sender_name or "-", (self.text or self.msg_type)[:40])


class LineProfile(models.Model):
    """คนที่เคยคุยกับบอท — **1 แถวต่อคน** (ไม่ใช่ต่อข้อความ)

    ★ ก.ย.69 — เจ้าของสั่ง: *"อย่าลืมเก็บ User ID ของลูกค้าด้วย แล้วก็ Profile"*

    ทำไมต้องแยกตาราง ไม่ยัดลง `GroupChat`:
      - โปรไฟล์เป็นของ "คน" ไม่ใช่ของ "ข้อความ" — ถ้ายัดรวมจะซ้ำทุกแถวและตกยุคคนละเวลา
      - ตอบคำถามที่ตารางแชทตอบไม่ได้: **ลูกค้าที่ทักเข้ามามีกี่คน · ใครทักบ่อย · ทักครั้งแรกเมื่อไหร่**
      - ได้ `user_id` ไว้ **ทักกลับหาลูกค้าได้ตรง** (push ต้องใช้ id ไม่ใช่ชื่อ)

    ⚠️ นี่คือ **ข้อมูลส่วนบุคคล** (PDPA) — มีอายุข้อมูลเท่าแชท (`_cleanup_chat` ลบให้)
       และ `is_employee` แยกไว้ชัดเพื่อไม่ให้เอาโปรไฟล์พนักงานไปปนกับลูกค้า
    ⚠️ `status_message` / `language` **ได้เฉพาะคนที่เพิ่มบอทเป็นเพื่อน (แชท 1:1)**
       — คนในกลุ่มที่ไม่ได้เพิ่มเพื่อน ดึงได้แค่ชื่อ + รูป ผ่าน group member API
    """
    USER, GROUP, ROOM = "user", "group", "room"
    SRC_CHOICES = [(USER, "ทักเข้า OA"), (GROUP, "เจอในกลุ่ม"), (ROOM, "ห้องคุย")]

    user_id = models.CharField("LINE user id", max_length=64, unique=True)
    display_name = models.CharField("ชื่อที่ตั้งใน LINE", max_length=120, blank=True)
    # ★ ก.ย.69 — **ไม่เก็บรูปโปรไฟล์** (เจ้าของสั่ง) · เก็บน้อยที่สุดเท่าที่ใช้จริงพอ (PDPA)
    #   ที่เคยเก็บคือ "ลิงก์" ไม่ใช่ไฟล์ จึงไม่ได้กินที่ แต่ก็ไม่มีใครใช้ → ตัดออก
    status_message = models.TextField("สเตตัส", blank=True)
    language = models.CharField("ภาษา", max_length=16, blank=True)

    # ถ้าเทียบกับชีตพนักงานได้ = คนใน ไม่ใช่ลูกค้า
    nickname = models.CharField("ชื่อเล่น (จากชีตพนักงาน)", max_length=80, blank=True)
    is_employee = models.BooleanField("เป็นพนักงาน", default=False, db_index=True)

    source = models.CharField("เจอครั้งแรกจาก", max_length=8, choices=SRC_CHOICES,
                              default=USER, db_index=True)
    group_id = models.CharField("กลุ่มที่เจอ", max_length=64, blank=True)

    # ★ ก.ย.69 — **LINE user id ไม่ใช่ค่าสากล** มันผูกกับ "ผู้ให้บริการ (provider)" ของ channel
    #   คนเดียวกันที่คุยกับบอท 2 ตัว:
    #     - บอทอยู่ provider เดียวกัน → ได้ userId **ตัวเดียวกัน** → แถวนี้แถวเดียว (channels มี 2 ค่า)
    #     - คนละ provider           → ได้ userId **คนละตัว** → กลายเป็น 2 แถว และ
    #       **ระบบไม่มีทางรู้เองว่าเป็นคนเดียวกัน** (ต้องมีคนยืนยัน)
    #   จึงต้องจดไว้ว่าเห็นคนนี้จากบัญชีไหนบ้าง ไม่งั้นตอนทำ CRM จะนับลูกค้าซ้ำโดยไม่รู้ตัว
    channel = models.CharField("เจอครั้งแรกจากบัญชี", max_length=24, blank=True, db_index=True)
    channels = models.JSONField("เคยเห็นจากบัญชีไหนบ้าง", default=list, blank=True)

    # ★ ก.ย.69 — ผูกกับ "ตัวคน" (Employee) · คนเดียวมี LINE id ได้หลายตัว (บอทละ provider)
    employee = models.ForeignKey("Employee", verbose_name="เป็นพนักงานคนนี้", null=True, blank=True,
                                 on_delete=models.SET_NULL, related_name="line_accounts")

    msg_count = models.PositiveIntegerField("จำนวนข้อความที่เคยส่ง", default=0)
    first_seen = models.DateTimeField("ทักครั้งแรก", default=timezone.now)
    last_seen = models.DateTimeField("ล่าสุด", default=timezone.now, db_index=True)
    fetched_at = models.DateTimeField("ดึงโปรไฟล์ล่าสุด", null=True, blank=True)
    raw = models.JSONField("คำตอบดิบจาก LINE", default=dict, blank=True)

    class Meta:
        verbose_name = "โปรไฟล์คน LINE"
        verbose_name_plural = "โปรไฟล์คน LINE"
        indexes = [models.Index(fields=["is_employee", "-last_seen"])]

    @property
    def show_name(self):
        """ชื่อที่เอาไปโชว์ได้ — พนักงานใช้ชื่อเล่น · ลูกค้าใช้ชื่อที่เขาตั้งใน LINE"""
        return self.nickname or self.display_name or "ไม่ทราบชื่อ"

    def __str__(self):
        return "%s (%s)" % (self.show_name, "พนักงาน" if self.is_employee else "ลูกค้า")


class Employee(models.Model):
    """ทะเบียนพนักงาน — **ย้ายมาเป็นของระบบเรา** (เจ้าของสั่ง 16 ก.ย.69)

    เดิมรายชื่อพนักงานอยู่ในชีตอย่างเดียว แล้วทุกอย่างจับคู่คนด้วย **LINE user id** ของชีต
    → พอเปลี่ยนมาใช้บอทใหม่ (คนละ provider) id ที่วิ่งเข้ามาเป็นคนละชุด **จับคู่ไม่ได้เลยสักคน**
    (วัดจริง 16/09: บอทใหม่ได้ยิน 45 คน จับคู่ชีตได้ 0)

    ตารางนี้จึงเก็บ "ตัวคน" ไว้ที่เดียว แล้วให้ **LINE id กี่ตัวก็ได้ผูกเข้ามา**
    (`LineProfile.employee`) — บอทเดิม 1 ตัว บอทใหม่ 1 ตัว ก็ยังเป็นคนเดียวกัน
    เพิ่ม/แก้คนได้ในระบบเราเอง ไม่ต้องไปแก้ชีต (`import_employees` ใช้ครั้งแรกตอนย้ายข้อมูลเข้า)

    ⚠️ **ห้ามโชว์ LINE id ของพนักงานบนหน้าเว็บ** (กติกาเดิม) — หน้าจัดการโชว์แค่ว่าผูกไว้กี่บัญชี
    """
    SHEET, MANUAL = "sheet", "manual"
    SRC_CHOICES = [(SHEET, "นำเข้าจากชีต"), (MANUAL, "เพิ่มในระบบ")]

    nickname = models.CharField("ชื่อเล่น", max_length=80, unique=True)
    display_name = models.CharField("ชื่อที่ตั้งใน LINE", max_length=120, blank=True, db_index=True)
    position = models.CharField("ตำแหน่ง/ทีม", max_length=80, blank=True)
    work_start = models.CharField("เวลาเข้างาน", max_length=16, blank=True)
    day_off = models.CharField("วันหยุด", max_length=40, blank=True)
    group_id = models.CharField("กลุ่ม LINE ที่ผูกไว้", max_length=64, blank=True)
    active = models.BooleanField("ยังทำงานอยู่", default=True, db_index=True)
    # ★ 16 ก.ย.69 (เจ้าของสั่ง) — ผู้บริหารไม่ต้องเช็คชื่อเข้างาน
    #   ติ๊กออก = ไม่ขึ้นในพาเนล "เช็คชื่อเข้างาน" เลย (ไม่นับเป็นคนที่ต้องมา · ไม่ขึ้น "ยังไม่เช็คชื่อ")
    #   **ไม่เดาจาก "ไม่ได้กรอกตำแหน่ง/เวลา"** เพราะพนักงานใหม่ที่ยังกรอกไม่ครบจะหายไปด้วย
    track_checkin = models.BooleanField("ต้องเช็คชื่อเข้างาน", default=True, db_index=True)
    note = models.CharField("หมายเหตุ", max_length=200, blank=True)
    source = models.CharField("ที่มา", max_length=8, choices=SRC_CHOICES, default=MANUAL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "พนักงาน"
        verbose_name_plural = "พนักงาน"
        ordering = ["position", "nickname"]

    def __str__(self):
        return "%s (%s)" % (self.nickname, self.position or "-")


class CheckIn(models.Model):
    """เช็คชื่อเข้างาน — 1 แถวต่อ "คน 1 วัน" (ย้ายมาจากชีต "เช็คชื่อ" · เจ้าของสั่ง 16 ก.ย.69)

    ทำไมย้ายมา: ชีตต้องคอยลบแถวเก่าเอง · จับคู่คนด้วย LINE id ชุดเดียว (พอเปลี่ยนบอทก็เพี้ยน) ·
    เอาไปทำสถิติไม่ได้ · ตารางนี้ผูกกับ `Employee` ตรงๆ → รู้ทันทีว่าใครยังไม่เช็คชื่อวันนี้

    **สาย/ตรงเวลา ตัดสินจาก "เวลาเข้างานของคนนั้น"** (`work_start` เก็บสำเนาไว้ในแถวด้วย —
    ถ้าวันหลังเปลี่ยนเวลาเข้างาน ประวัติเก่าต้องไม่เปลี่ยนตาม)

    ⚠️ ที่มาของเวลาคือ **ตัวหนังสือบนรูป** (คนงานถ่ายรูปเช็คอินที่มีเวลาแปะอยู่) อ่านด้วย AI
      อ่านไม่ออกค่อยตกไปใช้เวลาที่ข้อความวิ่งเข้า LINE — `time_source` บอกว่าได้จากทางไหน
    """
    ONTIME, LATE, ABNORMAL = "ontime", "late", "abnormal"
    STATUS_CHOICES = [(ONTIME, "ตรงเวลา"), (LATE, "สาย"), (ABNORMAL, "ผิดปกติ/อ่านไม่ออก")]

    employee = models.ForeignKey("Employee", verbose_name="พนักงาน", null=True, blank=True,
                                 on_delete=models.SET_NULL, related_name="checkins")
    user_id = models.CharField("LINE user id ที่ส่งมา", max_length=64, db_index=True)
    display_name = models.CharField("ชื่อที่โชว์", max_length=120, blank=True)

    date_iso = models.DateField("วันที่ (โซนไทย)", db_index=True)
    checkin_at = models.DateTimeField("เวลาเช็คชื่อ", null=True, blank=True)
    time_hm = models.CharField("เวลาที่อ่านได้", max_length=8, blank=True)
    work_start = models.CharField("เวลาเข้างานที่ใช้ตัดสิน", max_length=16, blank=True)

    status = models.CharField("สถานะ", max_length=10, choices=STATUS_CHOICES, default=ABNORMAL, db_index=True)
    reason = models.CharField("เหตุผล", max_length=200, blank=True)
    time_source = models.CharField("เวลามาจาก", max_length=16, blank=True)   # image | message

    full_address = models.CharField("สถานที่", max_length=300, blank=True)
    province = models.CharField("จังหวัด", max_length=80, blank=True)
    note = models.CharField("หมายเหตุ", max_length=200, blank=True)
    raw = models.JSONField("ข้อมูลดิบที่ AI อ่านได้", default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "เช็คชื่อเข้างาน"
        verbose_name_plural = "เช็คชื่อเข้างาน"
        # คนหนึ่งเช็คชื่อได้วันละครั้ง — n8n ใช้คู่นี้ทำ upsert (ON CONFLICT) กันบันทึกซ้ำ
        constraints = [models.UniqueConstraint(fields=["user_id", "date_iso"], name="uniq_checkin_user_day")]
        indexes = [models.Index(fields=["-date_iso", "status"])]
        ordering = ["-date_iso", "time_hm"]

    def __str__(self):
        who = self.employee.nickname if self.employee_id and self.employee else (self.display_name or self.user_id[:8])
        return "%s %s %s" % (self.date_iso, who, self.get_status_display())
