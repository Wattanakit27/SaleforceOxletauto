"""
โมเดลของแอป sales (dashboard) — เก็บ "ผลสรุป/สถานะ" ลง PostgreSQL ในเครื่อง (VPS)
แทน Supabase (มิ.ย.69 หลังขึ้น VPS). sales หลักยังอ่าน Google Sheets เหมือนเดิม —
ตารางพวกนี้แค่ cache ผลคำนวณ + heartbeat + override + ฟอร์ม (เทียบเท่า dashboard_cache/kv ของ Supabase)

ใช้ DB เดียวกับ cars/ (tracking). ไม่ตั้ง DB = SQLite (local dev) ก็ทำงานได้
"""
from django.db import models


class KVStore(models.Model):
    """key → JSON ทั่วไป — ใช้แทน Supabase dashboard_cache:
    - key='main'          : ผลคำนวณ dashboard (pre-compute · ~2-3MB)
    - key='cron_tick'     : heartbeat ของ cron
    - key='cron_followup' : log การส่ง followup ล่าสุด
    - key='sheet_config'  : override แหล่งข้อมูล {sheetKey: {spreadsheet_id, sheet_name}}
    """
    key = models.CharField(max_length=64, primary_key=True)
    data = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "dash_kv"

    def __str__(self):
        return self.key


class FormSubmission(models.Model):
    """ฟอร์มที่เซลล์ส่ง (เช็คไฟแนนซ์ / ขอสินเชื่อ) — แทน Supabase finance_checks/loan_applications"""
    kind = models.CharField(max_length=20, db_index=True)  # finance | loan
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dash_form"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.kind} #{self.pk}"


class FollowupLog(models.Model):
    """บันทึกสรุป "ตามด่วน" รายวันต่อเซลล์ (snapshot จาก build_followup_messages) — ดูความคืบหน้า/เทรนด์
    cron เขียนตอนส่ง followup · upsert ตาม (date, seller) = 1 แถว/วัน/เซลล์ (ส่งซ้ำในวันเดียวกันทับ)"""
    date = models.DateField("วันที่", db_index=True)
    seller = models.CharField("เซลล์", max_length=40)          # ชื่อเล่น · "ADMIN"=เทเลเซลล์
    team = models.CharField("ทีม", max_length=20, blank=True)
    follow_total = models.IntegerField("ต้องตาม", default=0)   # urgent count (state ล่าสุดของวัน)
    stuck_deals = models.IntegerField("ดีลค้าง", default=0)
    not_called = models.IntegerField("ยังไม่โทร", default=0)
    no_status = models.IntegerField("ไม่มีสถานะ", default=0)
    nags = models.IntegerField("โดนทวง (ครั้ง/วัน)", default=0)   # +1 ทุกรอบ followup ที่ส่งแล้วมีชื่อเซลล์นี้ (อย่างน้อย 1 เรื่อง)
    # แยก "โดนทวง" ตามเรื่องที่ค้าง — +1 ต่อรอบส่งที่เรื่องนั้นยังค้าง (เห็นว่าเซลล์พลาดเรื่องไหนบ่อย)
    nag_call = models.IntegerField("โดนทวง-โทร", default=0)       # รอบที่มี "ยังไม่โทร"
    nag_status = models.IntegerField("โดนทวง-สถานะ", default=0)   # รอบที่มี "ไม่มีสถานะ"
    nag_deal = models.IntegerField("โดนทวง-ดีล", default=0)       # รอบที่มี "ดีลค้าง"
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "dash_followup_log"
        unique_together = [("date", "seller")]
        ordering = ["-date", "seller"]
        indexes = [models.Index(fields=["-date"])]

    def __str__(self):
        return f"{self.date} {self.seller}"


class SellerWeekly(models.Model):
    """สรุปผลงานรายเซลล์ราย "สัปดาห์" (จอง/ปล่อย/Lead/RJ/ไลฟ์/คลิป/ยอด) — snapshot จากแดชบอร์ด
    ดูความคืบหน้ารายสัปดาห์. cron เขียน · upsert ตาม (week_start, seller) = 1 แถว/สัปดาห์/เซลล์
    week_start = วันจันทร์ของสัปดาห์ (โซนไทย) · ค่า = ผลรวมในสัปดาห์นั้น (flow)"""
    week_start = models.DateField("จันทร์ของสัปดาห์", db_index=True)
    seller = models.CharField("เซลล์", max_length=40)
    team = models.CharField("ทีม", max_length=20, blank=True)
    lead = models.IntegerField("Lead (ไม่รวม RJ)", default=0)
    rj = models.IntegerField("RJ", default=0)
    booking = models.IntegerField("จอง", default=0)
    done = models.IntegerField("ปล่อย", default=0)
    deal_value = models.BigIntegerField("฿ ปล่อย", default=0)
    live = models.IntegerField("ไลฟ์", default=0)
    clip = models.IntegerField("คลิป", default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "dash_seller_weekly"
        unique_together = [("week_start", "seller")]
        ordering = ["-week_start", "seller"]
        indexes = [models.Index(fields=["-week_start"])]

    def __str__(self):
        return f"{self.week_start} {self.seller}"


class EventLog(models.Model):
    """ล็อกเหตุการณ์ของระบบ — ★ 16 ก.ย.69 (เจ้าของสั่ง "ล็อกอะไรต่างๆ ก็ควรเก็บไว้ในนี้")

    **ทำไมต้องมี**: ที่ผ่านมาร่องรอยการทำงานถูกเก็บใน `dash_kv` แบบ **"ค่าล่าสุดค่าเดียว"**
    (`line_webhook_last`, `chat_store_last`, `precompute_last`, `cardline_last_*`) —
    ทับทุกครั้งที่ทำงาน จึง **ย้อนดูไม่ได้เลยว่าเมื่อวานเป็นยังไง**
    และ **ขาส่งออก LINE ไม่มีล็อกเลย** (`push_line_message` ยิงแล้วจบ)
    → เคยทำให้ **รายงานรายวันหยุดส่งเงียบ 2-3 วัน** และ **การ์ดตั้งเวลาส่งไม่ออกทุกใบ**
      โดยไม่มีใครเห็น กว่าจะรู้ก็ต่อเมื่อมีคนทักว่า "ทำไมไม่มีรายงาน"

    ตารางนี้เก็บเป็น **แถวต่อเหตุการณ์** → เปิดหน้า "ดูข้อมูลดิบ (SQL)" แล้วถามย้อนหลังได้ว่า
    *ส่งออกจริงไหม · ล้มเหลวตั้งแต่เมื่อไหร่ · ล้มเพราะอะไร*

    **ไม่ใช่ที่เก็บทุกอย่าง** — จดเฉพาะเหตุการณ์ที่ต้องตรวจย้อนหลังได้ (ส่งออก · ขาเข้าที่ผิดปกติ ·
    งานอัตโนมัติที่ล้ม) ไม่งั้นตารางจะโตเร็วโดยไม่มีใครใช้ · เก็บ `KEEP_DAYS` วันแล้วลบเอง
    """
    KEEP_DAYS = 90

    at = models.DateTimeField("เวลา", auto_now_add=True, db_index=True)
    kind = models.CharField("ประเภท", max_length=24, db_index=True)   # line_send / webhook / cron …
    name = models.CharField("เรื่อง", max_length=120, blank=True)
    target = models.CharField("ปลายทาง", max_length=64, blank=True)   # group id / user id
    ok = models.BooleanField("สำเร็จ", default=True, db_index=True)
    ms = models.IntegerField("ใช้เวลา (มิลลิวินาที)", default=0)
    detail = models.JSONField("รายละเอียด", default=dict, blank=True)

    class Meta:
        db_table = "dash_event_log"
        verbose_name = "ล็อกเหตุการณ์ระบบ"
        verbose_name_plural = "ล็อกเหตุการณ์ระบบ"
        ordering = ["-at"]
        indexes = [models.Index(fields=["kind", "-at"])]

    def __str__(self):
        return "%s %s %s" % (self.at, self.kind, "ok" if self.ok else "FAIL")


# ─────────────────────────────────────────────────────────────────────
# Meta (Facebook) — ก.ย.69 · เจ้าของสั่ง "ดึงทุกเที่ยงคืน เก็บเป็น raw data"
#
# ทำไมต้องจดเอง: Meta ให้ "ยอดสะสม" ของโพสต์เท่านั้น (วิว/ไลก์/แชร์) ไม่มีรายวัน
# และไม่มีเวลาที่แต่ละคนกด → ทางเดียวที่จะรู้ "วันนี้วิวเพิ่มกี่" คือจดยอดสะสม
# ทุกเที่ยงคืนแล้วเอามาลบกันเอง · **ย้อนหลังไม่ได้** เริ่มนับวันที่เปิดเก็บ
#
# ★ ทุกแถวมาจาก `dashboard/services/meta.py` ซึ่งกันไม่ให้ asset ของบริษัทอื่น
#   (OSUKA) หลุดเข้ามา — ห้ามเขียนตารางพวกนี้จากโค้ดที่ยิง Graph API ตรง
# ─────────────────────────────────────────────────────────────────────
class MetaPostSnapshot(models.Model):
    """ยอดสะสมของโพสต์ 1 โพสต์ ณ เวลาที่ดึง — 1 แถวต่อ "โพสต์ × รอบที่ดึง"

    **ใช้หายอดรายวัน**: เอาแถว `trigger='cron'` ของวัน D ลบกับวัน D-1
    (รอบ cron ดึงตอนเที่ยงคืน → `snap_date` = วันที่ **เพิ่งจบไป** ไม่ใช่วันที่ดึง)

    แถว `trigger='manual'` (กดปุ่ม sync เอง) เก็บไว้ดูยอดล่าสุดระหว่างวัน
    **อย่าเอาไปลบหายอดรายวัน** ไม่งั้นวันนั้นจะถูกหั่นเป็นสองท่อน

    ยอดติดลบได้ (Meta ลบไลก์/วิวปลอมย้อนหลัง) — เก็บตามจริง ไม่ปัดเป็น 0
    """
    CRON, MANUAL = "cron", "manual"

    taken_at = models.DateTimeField("ดึงเมื่อ", db_index=True)
    snap_date = models.DateField("ยอดสะสม ณ สิ้นวัน", db_index=True)
    trigger = models.CharField("ดึงเพราะ", max_length=8, default=CRON)   # cron / manual

    page_id = models.CharField("เพจ", max_length=32, db_index=True)
    post_id = models.CharField("โพสต์", max_length=64, db_index=True)
    post_type = models.CharField("ชนิด", max_length=32, blank=True)      # video / photo / album …
    created_time = models.DateTimeField("โพสต์เมื่อ", null=True, blank=True)
    permalink = models.URLField("ลิงก์", max_length=300, blank=True)
    message = models.CharField("ข้อความ (ตัดสั้น)", max_length=200, blank=True)

    reactions = models.IntegerField("รีแอ็กรวม", default=0)
    reactions_by_type = models.JSONField("รีแอ็กแยกชนิด", default=dict, blank=True)
    comments = models.IntegerField("คอมเมนต์", default=0)
    shares = models.IntegerField("แชร์", default=0)
    clicks = models.IntegerField("คลิก", default=0)

    video_views = models.IntegerField("วิว (3 วิ+)", default=0)
    video_views_organic = models.IntegerField("วิวออร์แกนิก", default=0)
    video_views_paid = models.IntegerField("วิวจากโฆษณา", default=0)
    video_avg_watch_ms = models.IntegerField("ดูเฉลี่ย (มิลลิวินาที)", default=0)
    video_complete_30s = models.IntegerField("ดูครบ 30 วิ", default=0)
    video_view_time_ms = models.BigIntegerField("เวลาดูรวม (มิลลิวินาที)", default=0)

    class Meta:
        db_table = "dash_meta_post_snapshot"
        verbose_name = "ยอดโพสต์ Facebook (รายวัน)"
        verbose_name_plural = "ยอดโพสต์ Facebook (รายวัน)"
        ordering = ["-taken_at"]
        indexes = [models.Index(fields=["post_id", "snap_date"]),
                   models.Index(fields=["trigger", "snap_date"])]

    def __str__(self):
        return "%s %s %s" % (self.snap_date, self.post_id, self.trigger)


class MetaAdDaily(models.Model):
    """ผลโฆษณา 1 ตัว × 1 วัน — ★ ต่างจากโพสต์: **Meta แยกรายวันให้เอง + ย้อนหลังได้**

    จึงเป็น "1 แถวต่อ ad ต่อวัน" (upsert) ไม่ใช่ snapshot · ทุกรอบดึงย้อน 3 วันมาทับ
    เพราะ Meta **แก้ตัวเลขโฆษณาย้อนหลัง** (attribution มาช้าได้ถึงหลายวัน)
    `actions` = ของดิบจาก Meta ทั้งก้อน (ลีด · แชท · คลิกลิงก์ ฯลฯ มีหลายสิบชนิด)
    """
    date = models.DateField("วันที่", db_index=True)
    account_id = models.CharField("บัญชีโฆษณา", max_length=32, db_index=True)
    campaign_id = models.CharField("แคมเปญ", max_length=32, blank=True, db_index=True)
    campaign_name = models.CharField("ชื่อแคมเปญ", max_length=300, blank=True)
    adset_id = models.CharField("ชุดโฆษณา", max_length=32, blank=True)
    adset_name = models.CharField("ชื่อชุดโฆษณา", max_length=300, blank=True)
    ad_id = models.CharField("โฆษณา", max_length=32, db_index=True)
    ad_name = models.CharField("ชื่อโฆษณา", max_length=300, blank=True)

    spend = models.DecimalField("ใช้เงิน (บาท)", max_digits=14, decimal_places=2, default=0)
    impressions = models.IntegerField("แสดงผล", default=0)
    reach = models.IntegerField("เข้าถึง (คน)", default=0)
    clicks = models.IntegerField("คลิก", default=0)
    actions = models.JSONField("actions ดิบ", default=list, blank=True)
    cost_per_action = models.JSONField("ต้นทุนต่อ action ดิบ", default=list, blank=True)
    updated_at = models.DateTimeField("ดึงล่าสุด", auto_now=True)

    class Meta:
        db_table = "dash_meta_ad_daily"
        verbose_name = "ผลโฆษณา Facebook (รายวัน)"
        verbose_name_plural = "ผลโฆษณา Facebook (รายวัน)"
        ordering = ["-date"]
        constraints = [models.UniqueConstraint(fields=["date", "ad_id"],
                                               name="uniq_meta_ad_day")]

    def __str__(self):
        return "%s %s %s" % (self.date, self.ad_id, self.spend)


class MetaRaw(models.Model):
    """คำตอบดิบจาก Meta ทั้งก้อน — ไว้คิดตัวเลขใหม่ย้อนหลังในวันที่อยากรู้อะไรที่ไม่ได้คิดไว้

    **มีวันหมดอายุ `KEEP_DAYS`** — วัดจริง ~6.5 KB/โพสต์ × ~1,800 โพสต์/วัน ≈ 12 MB/วัน
    ถ้าไม่ลบจะกิน ~4 GB/ปี (บทเรียนเดิม: รูปรายงานที่ไม่มีใครกวาดกินไป 1.3 GB)
    ตัวเลขที่ต้องใช้ระยะยาวถูกแตกไปเก็บใน 2 ตารางข้างบนแล้ว ตารางนี้เป็นของสำรอง
    """
    KEEP_DAYS = 90

    fetched_at = models.DateTimeField("ดึงเมื่อ", auto_now_add=True, db_index=True)
    kind = models.CharField("ชนิด", max_length=16, db_index=True)       # posts / ads / page
    ref_id = models.CharField("ของใคร", max_length=40, blank=True)       # page id / act id
    trigger = models.CharField("ดึงเพราะ", max_length=8, default="cron")
    data = models.JSONField("คำตอบดิบ", default=dict, blank=True)

    class Meta:
        db_table = "dash_meta_raw"
        verbose_name = "ข้อมูลดิบจาก Meta"
        verbose_name_plural = "ข้อมูลดิบจาก Meta"
        ordering = ["-fetched_at"]

    def __str__(self):
        return "%s %s %s" % (self.fetched_at, self.kind, self.ref_id)


class TikTokEvent(models.Model):
    """event ที่ TikTok ยิงเข้า webhook ของเรา — 1 แถวต่อ event · เก็บดิบทั้งก้อน (ก.ย.69)

    TikTok for Developers ส่งมาเป็น JSON: `client_key` · `event` (เช่น authorization.removed,
    video.publish.completed) · `create_time` (unix) · `user_openid` · `content` (JSON ที่เป็น *string* ซ้อนอีกชั้น)
    · ลายเซ็นอยู่ใน header `TikTok-Signature: t=<เวลา>,s=<hmac>`

    **กันซ้ำด้วย `body_hash`** — TikTok ไม่มี event id ให้ และลองส่งซ้ำเมื่อเราตอบช้า/ไม่ใช่ 200
    **มีอายุ `KEEP_DAYS`** — ล็อกที่ไม่มีวันหมดอายุ = ตารางโตไม่หยุด (บทเรียนเดิม)
    """
    KEEP_DAYS = 180

    received_at = models.DateTimeField("ได้รับเมื่อ", auto_now_add=True, db_index=True)
    event = models.CharField("ชนิด event", max_length=80, blank=True, db_index=True)
    client_key = models.CharField("แอป TikTok (client_key)", max_length=80, blank=True, db_index=True)
    user_openid = models.CharField("ผู้ใช้ (open_id)", max_length=120, blank=True, db_index=True)
    create_time = models.DateTimeField("TikTok สร้างเมื่อ", null=True, blank=True)
    # True = ลายเซ็นตรง · None = ยังไม่ได้ตั้ง secret จึงไม่ได้ตรวจ (ลายเซ็นไม่ตรงจะไม่ถูกเก็บเลย)
    signature_ok = models.BooleanField("ลายเซ็นถูกต้อง", null=True, blank=True)
    content = models.JSONField("content (แกะจาก string แล้ว)", default=dict, blank=True)
    raw = models.JSONField("body ดิบทั้งก้อน", default=dict, blank=True)
    body_hash = models.CharField("ลายนิ้วมือ body (กันซ้ำ)", max_length=64, unique=True)

    class Meta:
        db_table = "dash_tiktok_event"
        verbose_name = "event จาก TikTok (webhook)"
        verbose_name_plural = "event จาก TikTok (webhook)"
        ordering = ["-received_at"]

    def __str__(self):
        return "%s %s" % (self.received_at, self.event)


class TikTokAccount(models.Model):
    """ช่อง TikTok ที่เจ้าของกดอนุญาตให้ระบบเราอ่านข้อมูล — 1 แถวต่อช่อง (open_id) · ก.ย.69

    ได้มาจาก Login Kit: เจ้าของช่องเปิดลิงก์ขออนุญาต → TikTok ส่ง `code` กลับมาที่
    `/api/tiktok/webhook` → เราแลกเป็น access_token (อายุ ~24 ชม.) + refresh_token (~365 วัน)

    ★ **token เข้ารหัสก่อนเก็บ** (Fernet · กุญแจสร้างจาก SECRET_KEY) — ใครเปิดหน้า "ฐานข้อมูล (SQL)"
      หรือไฟล์ export จะเห็นแต่ค่าที่ถูกเข้ารหัส · ถือ token = ดึงข้อมูลช่องนั้นได้แทนเรา
      ⚠️ เปลี่ยน SECRET_KEY เมื่อไหร่ ถอดรหัสไม่ได้ ต้องให้เจ้าของช่องกดอนุญาตใหม่
    ★ access_token ต่ออายุเองจาก cron (`tiktok_oauth.refresh_due`) ก่อนหมด 2 ชม.
    """
    ACTIVE, ERROR, REVOKED = "active", "error", "revoked"
    STATUS_CHOICES = [(ACTIVE, "ใช้งานได้"), (ERROR, "ต่ออายุไม่สำเร็จ"), (REVOKED, "เจ้าของยกเลิกสิทธิ์")]

    open_id = models.CharField("open_id (id ช่องต่อแอป)", max_length=120, unique=True)
    label = models.CharField("ชื่อที่เราตั้ง (ตอนสร้างลิงก์)", max_length=120, blank=True)
    display_name = models.CharField("ชื่อช่อง", max_length=200, blank=True)
    username = models.CharField("@ชื่อผู้ใช้", max_length=120, blank=True)
    scope = models.CharField("สิทธิ์ที่ได้", max_length=300, blank=True)
    profile = models.JSONField("ข้อมูลช่องจาก TikTok (ไม่มีรูป)", default=dict, blank=True)

    access_token = models.TextField("access token (เข้ารหัส)", blank=True)
    access_expires_at = models.DateTimeField("access token หมดอายุ", null=True, blank=True)
    refresh_token = models.TextField("refresh token (เข้ารหัส)", blank=True)
    refresh_expires_at = models.DateTimeField("refresh token หมดอายุ", null=True, blank=True)

    status = models.CharField("สถานะ", max_length=10, choices=STATUS_CHOICES, default=ACTIVE, db_index=True)
    last_error = models.CharField("ผิดพลาดล่าสุด", max_length=300, blank=True)
    connected_by = models.CharField("ใครสร้างลิงก์", max_length=80, blank=True)
    connected_at = models.DateTimeField("เชื่อมเมื่อ", auto_now_add=True)
    refreshed_at = models.DateTimeField("ต่ออายุล่าสุด", null=True, blank=True)

    class Meta:
        db_table = "dash_tiktok_account"
        verbose_name = "ช่อง TikTok ที่เชื่อมแล้ว"
        verbose_name_plural = "ช่อง TikTok ที่เชื่อมแล้ว"
        ordering = ["label", "display_name"]

    def __str__(self):
        return "%s (%s)" % (self.label or self.display_name or self.open_id[:10], self.status)


class TikTokVideoSnapshot(models.Model):
    """ยอดสะสมของคลิป TikTok 1 คลิป ณ เวลาที่ดึง — คู่ขนานกับ `MetaPostSnapshot` ฝั่ง Facebook

    TikTok ให้ยอด (วิว/ไลก์/คอมเมนต์/แชร์) เป็น **ยอดสะสม** เท่านั้น ไม่มีรายวัน
    → ยอดรายวัน = แถว `trigger='cron'` วัน D ลบวัน D-1 · `snap_date` ของรอบเที่ยงคืน = วันที่เพิ่งจบไป
    ★ รอบ cron ของวันเดียวกันรันซ้ำได้ (เช่นระบบรีสตาร์ทกลางทาง) — ลบของวันนั้นของช่องนั้นก่อนแล้วค่อยใส่
      จึงมี 1 แถวต่อคลิปต่อวันเสมอ ไม่เบิ้ล
    """
    CRON, MANUAL = "cron", "manual"

    taken_at = models.DateTimeField("ดึงเมื่อ", db_index=True)
    snap_date = models.DateField("ยอดสะสม ณ สิ้นวัน", db_index=True)
    trigger = models.CharField("ดึงเพราะ", max_length=8, default=CRON)
    open_id = models.CharField("ช่อง (open_id)", max_length=120, db_index=True)
    video_id = models.CharField("คลิป", max_length=64, db_index=True)
    create_time = models.DateTimeField("โพสต์เมื่อ", null=True, blank=True)
    title = models.CharField("ชื่อ/คำบรรยาย (ตัดสั้น)", max_length=300, blank=True)
    share_url = models.URLField("ลิงก์คลิป", max_length=300, blank=True)
    duration = models.IntegerField("ยาว (วินาที)", default=0)

    view_count = models.BigIntegerField("วิว", default=0)
    like_count = models.BigIntegerField("ไลก์", default=0)
    comment_count = models.BigIntegerField("คอมเมนต์", default=0)
    share_count = models.BigIntegerField("แชร์", default=0)

    class Meta:
        db_table = "dash_tiktok_video_snapshot"
        verbose_name = "ยอดคลิป TikTok (รายวัน)"
        verbose_name_plural = "ยอดคลิป TikTok (รายวัน)"
        ordering = ["-taken_at"]
        indexes = [models.Index(fields=["video_id", "snap_date"]),
                   models.Index(fields=["open_id", "trigger", "snap_date"])]

    def __str__(self):
        return "%s %s %s" % (self.snap_date, self.video_id, self.view_count)


class TikTokAccountSnapshot(models.Model):
    """ยอดรวมของช่อง ณ สิ้นวัน (ผู้ติดตาม/ไลก์รวม/จำนวนคลิป) — ได้เฉพาะช่องที่ให้สิทธิ์ `user.info.stats`"""
    taken_at = models.DateTimeField("ดึงเมื่อ", db_index=True)
    snap_date = models.DateField("ยอด ณ สิ้นวัน", db_index=True)
    trigger = models.CharField("ดึงเพราะ", max_length=8, default="cron")
    open_id = models.CharField("ช่อง (open_id)", max_length=120, db_index=True)
    follower_count = models.BigIntegerField("ผู้ติดตาม", null=True, blank=True)
    following_count = models.BigIntegerField("กำลังติดตาม", null=True, blank=True)
    likes_count = models.BigIntegerField("ไลก์รวมทั้งช่อง", null=True, blank=True)
    video_count = models.IntegerField("จำนวนคลิป", null=True, blank=True)

    class Meta:
        db_table = "dash_tiktok_account_snapshot"
        verbose_name = "ยอดช่อง TikTok (รายวัน)"
        verbose_name_plural = "ยอดช่อง TikTok (รายวัน)"
        ordering = ["-taken_at"]
        indexes = [models.Index(fields=["open_id", "trigger", "snap_date"])]


class TikTokRaw(models.Model):
    """คำตอบดิบจาก TikTok API ทั้งก้อน — ไว้คิดตัวเลขใหม่ย้อนหลัง · มีวันหมดอายุ (`KEEP_DAYS`)"""
    KEEP_DAYS = 90

    fetched_at = models.DateTimeField("ดึงเมื่อ", auto_now_add=True, db_index=True)
    kind = models.CharField("ชนิด", max_length=16, db_index=True)       # videos / user
    open_id = models.CharField("ช่อง (open_id)", max_length=120, blank=True, db_index=True)
    trigger = models.CharField("ดึงเพราะ", max_length=8, default="cron")
    data = models.JSONField("คำตอบดิบ", default=dict, blank=True)

    class Meta:
        db_table = "dash_tiktok_raw"
        verbose_name = "ข้อมูลดิบจาก TikTok"
        verbose_name_plural = "ข้อมูลดิบจาก TikTok"
        ordering = ["-fetched_at"]
