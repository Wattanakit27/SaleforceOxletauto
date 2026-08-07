"""
โมเดลหลัก (tracking-only): Car, ScanLog, Branch
- Car.save() gen Car Code อัตโนมัติ (CB-0001 / SP-0001) ด้วย select_for_update กัน race
- Car.change_stage() -> ตั้ง stage/stage_since, frontline_at, status, สร้าง ScanLog
- T2L = frontline_at - date_in (คิดตอนเข้า show = รถพร้อมขาย)
"""
from django.db import models, transaction
from django.db.models import Max
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from . import constants as C


class Car(models.Model):
    code = models.CharField("รหัสรถ", max_length=12, primary_key=True, editable=False)
    branch = models.CharField("สาขา", max_length=4, default=C.DEFAULT_BRANCH)

    plate = models.CharField("ทะเบียน", max_length=20, blank=True)
    # ทะเบียนเดิม — ระบบจำให้อัตโนมัติเมื่อมีการแก้ทะเบียน (โชว์ในวงเล็บชื่อโฟลเดอร์ Drive)
    plate_original = models.CharField("ทะเบียนเดิม (ก่อนแก้)", max_length=20, blank=True)
    brand = models.CharField("ยี่ห้อ", max_length=40, blank=True)
    model = models.CharField("รุ่น", max_length=60, blank=True)
    year = models.PositiveIntegerField("ปี", null=True, blank=True)
    color = models.CharField("สี", max_length=30, blank=True)
    km = models.PositiveIntegerField("เลขไมล์", null=True, blank=True)

    stage = models.CharField("สเตป", max_length=20, choices=C.STAGE_CHOICES, default=C.STAGE_KEYS[0])
    stage_since = models.DateTimeField("เข้าสเตปเมื่อ", default=timezone.now)
    date_in = models.DateTimeField("วันรับเข้า", default=timezone.now)
    frontline_at = models.DateTimeField("ขึ้นหน้าร้านเมื่อ", null=True, blank=True)

    status = models.CharField("สถานะ", max_length=10, choices=C.STATUS_CHOICES, default="active")
    # ความด่วน — สีการ์ดมาจากนี่ (เลือกมือ · แทนวันค้างอัตโนมัติ)
    priority = models.CharField("ความด่วน", max_length=16, choices=C.PRIORITY_CHOICES, default=C.DEFAULT_PRIORITY)
    # ธงงานค้าง — แยกจากความด่วน (ติ๊กพร้อมกันได้ · รถด่วนมาก + ยังไม่ถ่ายคอนเทนต์ ได้พร้อมกัน)
    need_photo = models.BooleanField("ยังไม่ได้ถ่ายรูป", default=False)
    need_content = models.BooleanField("ยังไม่ได้ถ่ายคอนเทนต์", default=False)

    # ----- ฝ่ายทะเบียน -----
    book_status = models.CharField("สถานะเล่ม", max_length=14, choices=C.BOOK_STATUS_CHOICES, blank=True)
    tax_due_date = models.DateField("ครบกำหนดต่อภาษี", null=True, blank=True)
    doc_registration = models.FileField("เล่มทะเบียน", upload_to="docs/%Y/%m/", null=True, blank=True)

    photo = models.ImageField("รูปรถ", upload_to="cars/%Y/%m/", null=True, blank=True)
    # โฟลเดอร์ Google Drive ของรถคันนี้ (รูป/วิดีโอเข้าโฟลเดอร์เดียวกัน) — ตั้งครั้งแรกที่อัปไฟล์
    drive_folder_id = models.CharField("โฟลเดอร์ Drive", max_length=64, blank=True)
    note = models.TextField("หมายเหตุ", blank=True)

    # ข้อมูลดิบจากการนำเข้า (detail/owner/price/รูป ฯลฯ) — เก็บครบเป๊ะ ไม่ตกหล่น
    extra = models.JSONField("ข้อมูลเพิ่มเติม (นำเข้า)", default=dict, blank=True)

    # soft delete — ลบ = ย้ายถังขยะ (เก็บข้อมูลไว้) · ถังขยะโชว์ 30 วัน แล้วซ่อน (ไม่ลบจริง)
    deleted_at = models.DateTimeField("ลบเมื่อ (ถังขยะ)", null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "รถ"
        verbose_name_plural = "รถ"
        ordering = ["-date_in"]

    def __str__(self):
        return f"{self.code} {self.brand} {self.model}".strip()

    # ----- gen Car Code -----
    @staticmethod
    def _next_code(branch):
        """หาเลขลำดับถัดไปของสาขา -> CB-0001 (เรียกใน transaction + select_for_update)"""
        prefix = (branch or C.DEFAULT_BRANCH).strip().upper()
        last = (
            Car.objects.select_for_update()
            .filter(code__startswith=f"{prefix}-")
            .aggregate(m=Max("code"))["m"]
        )
        seq = int(last.split("-")[1]) + 1 if last else 1
        return f"{prefix}-{seq:04d}"

    @classmethod
    def from_db(cls, db, field_names, values):
        # จำทะเบียนตอนโหลด เพื่อตรวจจับ "การแก้ทะเบียน" ตอน save (ไม่ยิง query เพิ่ม)
        inst = super().from_db(db, field_names, values)
        inst._loaded_plate = inst.plate
        return inst

    def save(self, *args, **kwargs):
        if not self.code:
            with transaction.atomic():
                self.code = self._next_code(self.branch)
                super().save(*args, **kwargs)
            self._loaded_plate = self.plate
            return
        # จับ "ทะเบียนเดิม" อัตโนมัติ: ทะเบียนเปลี่ยน + ยังไม่เคยเก็บเดิม → เก็บอันก่อนหน้าไว้
        uf = kwargs.get("update_fields")
        plate_saving = uf is None or "plate" in uf
        prev = getattr(self, "_loaded_plate", None)
        if plate_saving and prev and prev != self.plate and not self.plate_original:
            self.plate_original = prev[:20]
            if uf is not None:
                kwargs["update_fields"] = list(uf) + ["plate_original"]
        super().save(*args, **kwargs)
        self._loaded_plate = self.plate

    # ----- เปลี่ยนสเตป -----
    def change_stage(self, new_stage, worker_name="", worker_id="", note="", photo=None):
        """เปลี่ยนสเตป + บันทึก ScanLog + ตั้ง frontline_at + คืน (log, should_notify)"""
        now = timezone.now()
        self.stage = new_stage
        self.stage_since = now
        if new_stage == C.FRONTLINE_STAGE and not self.frontline_at:
            self.frontline_at = now
        if new_stage == "release":       # ปล่อยรถ = จบ (ส่งมอบ) → มาร์ค sold หลุดจากบอร์ด
            self.status = "sold"
        self.save()

        log = ScanLog.objects.create(
            car=self, stage=new_stage, worker_name=worker_name,
            worker_id=worker_id, note=note, photo=photo,
        )
        return log, new_stage in C.STAGE_NOTIFY

    # ----- computed -----
    @property
    def days_in_stage(self):
        return (timezone.now() - self.stage_since).days

    @property
    def t2l(self):
        """Time-to-Line (วัน): date_in -> frontline_at ; None ถ้ายังไม่ขึ้นหน้าร้าน"""
        if not self.frontline_at:
            return None
        return round((self.frontline_at - self.date_in).total_seconds() / 86400, 1)

    @property
    def t2l_done(self):
        return self.frontline_at is not None

    @property
    def flag(self):
        """ok / amber / red ตามจำนวนวันค้างสเตป (ช่วงปลาย/ขายแล้ว/พัก = ok)
        ★ ติ๊กธง "ยังไม่ได้ถ่ายรูป" = "wait" — ไม่นับเป็นค้าง (รถรอทุกอย่างเสร็จก่อน ไม่ใช่งานดอง)
        วันยังเดินตามจริง แค่ไม่ขึ้นแดง/เหลือง · ปลดธงเมื่อไหร่กลับมานับตามวันจริงทันที"""
        if self.status in ("sold", "hold") or self.stage in C.OK_STAGES:
            return "ok"
        if self.need_photo:
            return "wait"
        d = self.days_in_stage
        if d > C.STUCK_RED_DAYS:
            return "red"
        if d >= C.STUCK_AMBER_DAYS:
            return "amber"
        return "ok"

    @property
    def stage_name(self):
        return C.STAGE_NAME.get(self.stage, self.stage)

    @property
    def stage_icon(self):
        return C.STAGE_ICON.get(self.stage, "circle")

    @property
    def priority_color(self):
        return C.PRIORITY_COLOR.get(self.priority, "#eab308")

    @property
    def priority_name(self):
        return C.PRIORITY_NAME.get(self.priority, self.priority)

    @property
    def card_color(self):
        """สีการ์ดในบอร์ด — ถึง "รถพร้อมขาย/หน้าร้าน" = เขียว (จบสายทำสภาพแล้ว)
        ไม่งั้นใช้สีความด่วนตามปกติ · ธงงานค้างโชว์แยกเป็นไอคอนบนการ์ด (ดู flags)"""
        return C.FRONTLINE_COLOR if self.stage == C.FRONTLINE_STAGE else self.priority_color

    @property
    def flags(self):
        """ธงงานค้างที่ติดอยู่ → [{key, name, icon, color}] สำหรับโชว์เป็นไอคอนบนการ์ด/ป๊อปอัป"""
        return [{"key": k, "name": C.FLAG_NAME[k], "icon": C.FLAG_ICON[k], "color": C.FLAG_COLOR[k]}
                for k in C.FLAG_KEYS if getattr(self, k, False)]

    @property
    def card_label(self):
        """ป้ายบนหัวการ์ด — ใช้ป้ายทะเบียนเป็นหลัก (คนหน้างานจำทะเบียนไม่ใช่รหัส)
        ไม่มีทะเบียน (รถเพิ่งเข้า/ยังไม่โอน) → fallback รหัสรถ."""
        return (self.plate or "").strip() or self.code

    @property
    def stage_index(self):
        return C.STAGE_ORDER.get(self.stage, 0)

    @property
    def branch_name(self):
        return branch_name(self.branch)

    @property
    def title(self):
        return " ".join(str(x) for x in [self.brand, self.model, self.year] if x).strip() or self.code

    @property
    def qr_url(self):
        """URL ปลายทางที่ QR ชี้ไป (หน้าสแกน)"""
        from django.conf import settings
        return f"{settings.SITE_URL}/track/scan/{self.code}/"


class ScanLog(models.Model):
    car = models.ForeignKey(Car, on_delete=models.CASCADE, related_name="logs", verbose_name="รถ")
    stage = models.CharField("สเตป", max_length=20, choices=C.STAGE_CHOICES)
    worker_name = models.CharField("ผู้สแกน", max_length=80, blank=True)
    worker_id = models.CharField("LINE userId", max_length=64, blank=True)
    photo = models.ImageField("รูป", upload_to="scans/%Y/%m/", null=True, blank=True)
    # ไฟล์แนบหลายไฟล์ (รูป/วิดีโอ) — อัปตรงเข้า Supabase Storage แล้วเก็บ path: [{"path":..,"video":bool}]
    media = models.JSONField("ไฟล์แนบ (รูป/วิดีโอ)", default=list, blank=True)
    note = models.TextField("หมายเหตุ", blank=True)
    created_at = models.DateTimeField("เวลา", auto_now_add=True)

    class Meta:
        verbose_name = "ประวัติการสแกน"
        verbose_name_plural = "ประวัติการสแกน"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.car_id} -> {self.stage} @ {self.created_at:%Y-%m-%d %H:%M}"

    @property
    def stage_name(self):
        return C.STAGE_NAME.get(self.stage, self.stage)

    @property
    def stage_icon(self):
        return C.STAGE_ICON.get(self.stage, "circle")


class Branch(models.Model):
    """สาขา (DB-driven) — code = prefix รหัสรถ (CB-/SP-/...)"""
    code = models.CharField("รหัสสาขา (prefix)", max_length=4, unique=True)
    name = models.CharField("ชื่อสาขา", max_length=120)
    active = models.BooleanField("เปิดใช้งาน", default=True)
    created_at = models.DateTimeField("เวลา", auto_now_add=True)

    class Meta:
        verbose_name = "สาขา"
        verbose_name_plural = "สาขา"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} · {self.name}"

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
        super().save(*args, **kwargs)


def branch_pairs(active_only=True):
    """[(code, name), ...] จาก DB — fallback เป็น constant ถ้ายังไม่มีข้อมูล"""
    qs = Branch.objects.filter(active=True) if active_only else Branch.objects.all()
    pairs = [(b.code, b.name) for b in qs.order_by("code")]
    return pairs or list(C.BRANCH_CHOICES)


_branch_name_cache = {}


def branch_name(code):
    """ชื่อสาขาจาก code — constant ก่อน (ไม่ยิง query) · DB-driven cache ต่อ process
    (กัน N+1 ตอนแสดงรถหลายร้อยคันในหน้าเดียว — branch code นอก constant เช่น BK/ON)"""
    if not code:
        return "—"
    if code in C.BRANCH_PREFIX:
        return C.BRANCH_PREFIX[code]
    if code in _branch_name_cache:
        return _branch_name_cache[code]
    b = Branch.objects.filter(code=code).first()
    name = b.name if b else code
    _branch_name_cache[code] = name
    return name


class LoginEvent(models.Model):
    """บันทึกการเข้าสู่ระบบ (audit) — ใครเข้า/พยายามเข้า เมื่อไหร่ ด้วยวิธีไหน สำเร็จไหม
    เก็บทั้ง sales (LINE/แอดมินรหัสผ่าน) และ tracking (worker). เขียนแบบ best-effort —
    DB ล่ม/ยังไม่ migrate = ข้ามเงียบ ไม่ทำให้ login พัง (ดู dashboard/services/audit.py)."""
    METHODS = [("line", "LINE"), ("admin", "แอดมินรหัสผ่าน"), ("worker", "บัญชีรหัสผ่าน")]
    created_at = models.DateTimeField("เวลา", auto_now_add=True, db_index=True)
    identity = models.CharField("บัญชี (user/LINE id)", max_length=200, blank=True)
    name = models.CharField("ชื่อ", max_length=200, blank=True)
    method = models.CharField("วิธี", max_length=20, choices=METHODS, blank=True)
    success = models.BooleanField("สำเร็จ", default=True)
    role = models.CharField("บทบาท", max_length=40, blank=True)
    ip = models.CharField("IP", max_length=64, blank=True)
    user_agent = models.CharField("อุปกรณ์", max_length=300, blank=True)
    reason = models.CharField("หมายเหตุ/สาเหตุ", max_length=200, blank=True)

    class Meta:
        verbose_name = "การเข้าสู่ระบบ"
        verbose_name_plural = "การเข้าสู่ระบบ"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["-created_at"]), models.Index(fields=["success"])]

    def __str__(self):
        return f"{'OK' if self.success else 'FAIL'} {self.identity} ({self.method})"


class Presence(models.Model):
    """ผู้ใช้ที่กำลังออนไลน์ (heartbeat) — นับ "คนเข้าเว็บตอนนี้" = แถวที่ last_seen ภายใน ~2.5 นาที.
    1 แถวต่อ identity (user_id ของ session · update_or_create อัปเดตในที่เดิม ไม่บวมตาราง).
    เขียนจาก dashboard.presence_ping (heartbeat ทุก ~45 วิ จาก index.html/seller.html) · best-effort."""
    identity = models.CharField(max_length=200, unique=True)
    name = models.CharField(max_length=200, blank=True)
    role = models.CharField(max_length=40, blank=True)
    page = models.CharField(max_length=20, blank=True)        # dashboard / seller
    last_seen = models.DateTimeField(db_index=True)

    class Meta:
        verbose_name = "ออนไลน์"
        verbose_name_plural = "ออนไลน์"
        ordering = ["-last_seen"]

    def __str__(self):
        return f"{self.identity} @ {self.last_seen:%H:%M}"


# ── แจ้งเว็บโชว์รูม (oxlet_web) sync สถานะรถ realtime ─────────────────────────
# post_save ครอบทุกทางที่ทำให้รถขยับ (เปลี่ยนสเตป/เพิ่มรถตรงที่สเตปพร้อมขาย/แก้ในแอดมิน)
# → notify_showroom (ยิงเฉพาะสเตป show/reserve/sold · เช็คภายใน) · best-effort · ข้าม fixture
@receiver(post_save, sender=Car)
def _notify_showroom_on_car_save(sender, instance, raw=False, **kwargs):
    if raw:
        return
    try:
        from .showroom_sync import notify_showroom
        notify_showroom(instance)
    except Exception:
        pass
