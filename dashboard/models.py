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


class MetaVideoRetention(models.Model):
    """กราฟ "คนยังดูอยู่กี่ %" ของวิดีโอในเพจ — 1 แถวต่อโพสต์ (ค่าล่าสุด · อัปเดตทุกเที่ยงคืน) · 15 ต.ค.69

    Facebook ให้มา **41 จุด แบ่งตามความยาวคลิปทุก 2.5%** (จุด 0 = เริ่มคลิป · จุด 40 = จบคลิป) ค่าเป็นสัดส่วน 0–1
    ไม่ได้ให้เป็นวินาที → แปลงด้วย `length_sec` · 3 เส้น: รวมทุกคน · วิดีโอเล่นเอง (autoplay) · คนกดเล่นเอง
    เก็บค่าล่าสุดค่าเดียว (ไม่เก็บรายวัน) — กราฟแทบไม่ขยับหลังคลิปออกไม่กี่วัน เก็บทุกคืนจะบวมเปล่า
    """
    page_id = models.CharField("เพจ", max_length=32, db_index=True)
    post_id = models.CharField("โพสต์", max_length=64, unique=True)
    video_id = models.CharField("วิดีโอ", max_length=64, blank=True)
    created_time = models.DateTimeField("โพสต์เมื่อ", null=True, blank=True)
    length_sec = models.FloatField("ความยาวคลิป (วินาที)", null=True, blank=True)
    curve = models.JSONField("คนยังดูอยู่ (รวม) 41 จุด", default=list, blank=True)
    curve_auto = models.JSONField("คนยังดูอยู่ (เล่นเอง/autoplay)", default=list, blank=True)
    curve_click = models.JSONField("คนยังดูอยู่ (กดเล่นเอง)", default=list, blank=True)
    updated_at = models.DateTimeField("อัปเดตล่าสุด", auto_now=True)
    first_seen = models.DateTimeField("ระบบเจอคลิปนี้ครั้งแรก", null=True, blank=True)

    # ── ผลวิเคราะห์ (คิดด้วย social_stats._kpi ตัวเดียวกับหน้าเว็บ · คิดใหม่ทุกครั้งที่กราฟอัปเดต) ──
    # เก็บเป็นคอลัมน์ให้เขียน SQL ได้ตรงๆ เช่น "คลิปไหน Hook ต่ำกว่า 60%" (15 ต.ค.69 · เจ้าของสั่ง)
    hook_pct = models.FloatField("Hook · เหลือกี่ % ที่วิที่ 3", null=True, blank=True)
    hold_pct = models.FloatField("Hold · ของคนที่ดูถึง 3 วิ ดูต่อถึงวิ 15/จบ กี่ %", null=True, blank=True)
    hold_to = models.CharField("Hold วัดถึง (15 / end)", max_length=8, blank=True)
    half_sec = models.IntegerField("คนที่ดูถึง 3 วิ หายครึ่งที่วินาทีที่", null=True, blank=True)
    drop_sec = models.IntegerField("หลุดหนักสุดที่วินาทีที่", null=True, blank=True)
    drop_pct = models.FloatField("หลุดหนักสุดกี่ %", null=True, blank=True)
    end_pct = models.FloatField("ดูจบกี่ %", null=True, blank=True)
    persec = models.JSONField("คนยังดูอยู่ทีละวินาที (%)", default=list, blank=True)
    analyzed_at = models.DateTimeField("วิเคราะห์ล่าสุด", null=True, blank=True)

    # ── ภาพทีละวินาที (ไฟล์อยู่ media/frames/meta/<post id>/ · ตารางจดว่ามีกี่ภาพ ทำเมื่อไหร่ เพราะอะไร) ──
    frames_n = models.IntegerField("ภาพทีละวินาที (จำนวน)", default=0)
    frames_at = models.DateTimeField("ทำภาพเมื่อ", null=True, blank=True)
    frames_reason = models.CharField("ได้ภาพเพราะ (new = คลิปใหม่ · ads = ยิงแอดวิวสูง)", max_length=8, blank=True)
    frames_error = models.CharField("ทำภาพไม่สำเร็จเพราะ", max_length=200, blank=True)

    class Meta:
        db_table = "dash_meta_video_retention"
        verbose_name = "กราฟคนดูค้างของวิดีโอ Facebook"
        verbose_name_plural = "กราฟคนดูค้างของวิดีโอ Facebook"

    def __str__(self):
        return "%s (%s วิ)" % (self.post_id, self.length_sec)


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
    # ★ 23 ก.ย.69 — แตกตัวเลขสำคัญออกจาก `actions` JSON มาเป็นคอลัมน์ (ดู ads_stats.ACTION_MAP)
    #   เดิมมีแต่ JSON ดิบ → จะรู้ "ต้นทุนต่อแชท" ต้องงัด jsonb ทุกครั้ง เขียน SQL เองแทบไม่ได้
    link_clicks = models.IntegerField("คลิกลิงก์", default=0)
    video_views = models.IntegerField("วิววิดีโอ", default=0)
    engagement = models.IntegerField("การมีส่วนร่วมกับโพสต์", default=0)
    chats = models.IntegerField("เริ่มแชท (7 วัน)", default=0)
    chats_replied = models.IntegerField("แชทที่ตอบกลับ (7 วัน)", default=0)
    leads = models.IntegerField("ลีด", default=0)
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


class MetaPageDaily(models.Model):
    """ยอด **ระดับเพจ** รายวันที่ Facebook สรุปให้เอง — 1 แถว/เพจ/วัน (upsert)

    ★ 21 ก.ย.69 — ทำขึ้นเพื่อตอบคำถามเดียว: **"ที่เรารวมจากโพสต์ เก็บครบไหม"**
    `dash_meta_post_snapshot` คือยอดที่เรา *รวมเอง* จากโพสต์ในฟีด (วิดีโอเท่านั้นที่มีวิว)
    ตารางนี้คือยอดที่ **Facebook รายงานเอง** ของทั้งเพจ → เอามาวางเทียบกันแล้วเห็นช่องว่างทันที
    · ต่างจาก snapshot ตรงที่ **ไม่ต้องรอสะสม** — Meta ให้ย้อนหลังมาเลย (~30 วัน)
    """
    page_id = models.CharField("เพจ", max_length=32, db_index=True)
    date = models.DateField("วันที่", db_index=True)
    video_views = models.BigIntegerField("วิววิดีโอ (ทั้งเพจ)", default=0)
    engagements = models.BigIntegerField("การมีส่วนร่วมกับโพสต์", default=0)
    page_views = models.BigIntegerField("คนเปิดดูเพจ", default=0)
    follows = models.BigIntegerField("ผู้ติดตามใหม่", default=0)
    likes = models.BigIntegerField("กดถูกใจโพสต์", default=0)
    updated_at = models.DateTimeField("ดึงล่าสุด", auto_now=True)

    class Meta:
        db_table = "dash_meta_page_daily"
        verbose_name = "ยอดเพจ Facebook (รายวัน)"
        verbose_name_plural = "ยอดเพจ Facebook (รายวัน)"
        ordering = ["-date"]
        constraints = [models.UniqueConstraint(fields=["page_id", "date"],
                                               name="uniq_meta_page_day")]

    def __str__(self):
        return "%s %s วิว %s" % (self.date, self.page_id, self.video_views)


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


class SocialDaily(models.Model):
    """ยอดโซเชียล **รายวันจริง** — 1 แถว = โพสต์/คลิป 1 ชิ้น × 1 วัน

    ★ 23 ก.ย.69 (เจ้าของสั่ง "แยกตาราง Daily กับภาพรวม จะได้กรองวันได้")
    ตารางเดิม (`dash_meta_post_snapshot` / `dash_tiktok_video_snapshot`) เก็บ **ยอดสะสม**
    ณ ตอนดึง → ถ้าอยากรู้ "วันนี้ได้กี่วิว" ต้องเอา 2 วันมาลบกันเองทุกครั้ง
    · ตารางนี้คือผลลัพธ์ที่ลบไว้แล้ว → `WHERE date BETWEEN … ` ได้ตรงๆ ทั้งในหน้า SQL และโค้ด

    **เป็นข้อมูลที่คำนวณมา (derived) ไม่ใช่ต้นฉบับ** — ลบทิ้งแล้วสร้างใหม่ได้เสมอด้วย
    `manage.py social_rebuild` (ต้นฉบับคือตาราง snapshot) · สูตรใช้ตัวเดียวกับที่หน้าเว็บใช้
    (`social_stats._daily_one`) จะได้ไม่มีเลข 2 ชุดที่ไม่ตรงกัน
    """
    META, TIKTOK, YOUTUBE = "meta", "tiktok", "youtube"

    date = models.DateField("วันที่ของยอด", db_index=True)
    platform = models.CharField("แพลตฟอร์ม", max_length=8, db_index=True)
    object_id = models.CharField("โพสต์/คลิป", max_length=64, db_index=True)
    owner_id = models.CharField("เพจ/ช่อง", max_length=120, blank=True, db_index=True)
    title = models.CharField("ข้อความ/ชื่อคลิป (ย่อ)", max_length=200, blank=True)

    # ยอดที่ "เพิ่มขึ้นในวันนั้น" (ติดลบไม่นับ — โพสต์ถูกลบ/ตัวเลขถูกแก้ย้อนหลัง)
    views = models.BigIntegerField("วิว (วันนั้น)", default=0)
    likes = models.BigIntegerField("ไลก์ (วันนั้น)", default=0)
    comments = models.BigIntegerField("คอมเมนต์ (วันนั้น)", default=0)
    shares = models.BigIntegerField("แชร์ (วันนั้น)", default=0)

    # ยอดสะสม ณ สิ้นวันนั้น (ไว้เทียบ/ตรวจว่าตัวเลขเพี้ยนไหม)
    cum_views = models.BigIntegerField("วิวสะสม", default=0)
    cum_likes = models.BigIntegerField("ไลก์สะสม", default=0)
    cum_comments = models.BigIntegerField("คอมเมนต์สะสม", default=0)
    cum_shares = models.BigIntegerField("แชร์สะสม", default=0)

    updated_at = models.DateTimeField("คำนวณล่าสุด", auto_now=True)

    class Meta:
        db_table = "dash_social_daily"
        verbose_name = "ยอดโซเชียลรายวัน"
        verbose_name_plural = "ยอดโซเชียลรายวัน"
        ordering = ["-date"]
        constraints = [models.UniqueConstraint(fields=["platform", "object_id", "date"],
                                               name="uniq_social_daily")]
        indexes = [models.Index(fields=["platform", "date"])]

    def __str__(self):
        return "%s %s %s วิว+%s" % (self.date, self.platform, self.object_id, self.views)


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


class YouTubeChannelSnapshot(models.Model):
    """ยอดรวมของช่อง YouTube ณ สิ้นวัน (ผู้ติดตาม/วิวรวม/จำนวนคลิป)

    ★ ต่างจาก TikTok/Meta ตรงที่ **ไม่ต้องให้เจ้าของช่องกดอนุญาต** — ยอดพวกนี้เป็นข้อมูลสาธารณะ
      ขอด้วย API key ใบเดียวได้ทุกช่อง (`YOUTUBE_API_KEY` ใน .env)
    ⚠️ `subscriber_count` เป็น null ได้ ถ้าเจ้าของช่องตั้งซ่อนจำนวนผู้ติดตามไว้
    """
    taken_at = models.DateTimeField("ดึงเมื่อ", db_index=True)
    snap_date = models.DateField("ยอด ณ สิ้นวัน", db_index=True)
    trigger = models.CharField("ดึงเพราะ", max_length=8, default="cron")
    channel_id = models.CharField("ช่อง (UC...)", max_length=64, db_index=True)
    handle = models.CharField("@handle ที่ตั้งไว้ใน .env", max_length=120, blank=True)
    title = models.CharField("ชื่อช่อง", max_length=200, blank=True)

    subscriber_count = models.BigIntegerField("ผู้ติดตาม", null=True, blank=True)
    view_count = models.BigIntegerField("วิวรวมทั้งช่อง", null=True, blank=True)
    video_count = models.IntegerField("จำนวนคลิป", null=True, blank=True)

    class Meta:
        db_table = "dash_youtube_channel_snapshot"
        verbose_name = "ยอดช่อง YouTube (รายวัน)"
        verbose_name_plural = "ยอดช่อง YouTube (รายวัน)"
        ordering = ["-taken_at"]
        indexes = [models.Index(fields=["channel_id", "trigger", "snap_date"])]

    def __str__(self):
        return "%s %s ผู้ติดตาม %s" % (self.snap_date, self.title, self.subscriber_count)


class YouTubeVideoSnapshot(models.Model):
    """ยอดสะสมของคลิป YouTube 1 คลิป ณ เวลาที่ดึง — คู่ขนานกับ `TikTokVideoSnapshot`

    ยอดรายวัน = แถว `trigger='cron'` วัน D ลบวัน D-1 (กติกาเดียวกับ Meta/TikTok)
    · `snap_date` ของรอบเที่ยงคืน = วันที่เพิ่งจบไป
    ★ รอบ cron ของวันเดียวกันรันซ้ำได้ ไม่เบิ้ล — ลบชุด cron ของวันนั้นของช่องนั้นก่อนเขียนใหม่

    ⚠️ **YouTube ไม่ให้ยอดแชร์และยอดดิสไลก์** (ปิดดิสไลก์ตั้งแต่ปี 2021 · แชร์ไม่เคยมีใน API)
      → คอลัมน์ `shares` ใน `dash_social_daily` ของฝั่ง YouTube จะเป็น 0 เสมอ **ไม่ใช่บั๊ก**
    ⚠️ `like_count` เป็น null ได้ ถ้าเจ้าของคลิปซ่อนยอดไลก์
    """
    CRON, MANUAL = "cron", "manual"

    taken_at = models.DateTimeField("ดึงเมื่อ", db_index=True)
    snap_date = models.DateField("ยอดสะสม ณ สิ้นวัน", db_index=True)
    trigger = models.CharField("ดึงเพราะ", max_length=8, default=CRON)
    channel_id = models.CharField("ช่อง (UC...)", max_length=64, db_index=True)
    video_id = models.CharField("คลิป", max_length=64, db_index=True)
    published_at = models.DateTimeField("โพสต์เมื่อ", null=True, blank=True)
    title = models.CharField("ชื่อคลิป (ตัดสั้น)", max_length=300, blank=True)
    duration = models.IntegerField("ยาว (วินาที)", default=0)
    is_short = models.BooleanField("เป็น Shorts (ยาว <= 3 นาที)", default=False)

    view_count = models.BigIntegerField("วิว", default=0)
    like_count = models.BigIntegerField("ไลก์", default=0)
    comment_count = models.BigIntegerField("คอมเมนต์", default=0)

    class Meta:
        db_table = "dash_youtube_video_snapshot"
        verbose_name = "ยอดคลิป YouTube (รายวัน)"
        verbose_name_plural = "ยอดคลิป YouTube (รายวัน)"
        ordering = ["-taken_at"]
        indexes = [models.Index(fields=["video_id", "snap_date"]),
                   models.Index(fields=["channel_id", "trigger", "snap_date"])]

    def __str__(self):
        return "%s %s %s วิว" % (self.snap_date, self.video_id, self.view_count)


class YouTubeRaw(models.Model):
    """คำตอบดิบจาก YouTube API ทั้งก้อน — ไว้คิดตัวเลขใหม่ย้อนหลัง · มีวันหมดอายุ (`KEEP_DAYS`)"""
    KEEP_DAYS = 90

    fetched_at = models.DateTimeField("ดึงเมื่อ", auto_now_add=True, db_index=True)
    kind = models.CharField("ชนิด", max_length=16, db_index=True)       # channels / videos
    channel_id = models.CharField("ช่อง", max_length=64, blank=True, db_index=True)
    trigger = models.CharField("ดึงเพราะ", max_length=8, default="cron")
    data = models.JSONField("คำตอบดิบ", default=dict, blank=True)

    class Meta:
        db_table = "dash_youtube_raw"
        verbose_name = "ข้อมูลดิบจาก YouTube"
        verbose_name_plural = "ข้อมูลดิบจาก YouTube"
        ordering = ["-fetched_at"]


class AdsDaily(models.Model):
    """ยอดโฆษณา **รายวัน (รวมทั้งบัญชี)** — 1 แถว = บัญชีโฆษณา 1 บัญชี × 1 วัน

    ★ 23 ก.ย.69 (เจ้าของสั่ง "เก็บข้อมูลของ Ads เป็น Daily Day กับภาพรวม เก็บพวกค่าต่างๆ
      ด้วย พวก cost per chat") — คู่ขนานกับ `dash_social_daily` ของฝั่งโซเชียล

    `dash_meta_ad_daily` เป็นรายวัน**ต่อโฆษณาแต่ละชิ้น** (147 ชิ้น × ทุกวัน) ซึ่งละเอียดเกิน
    สำหรับคำถามแบบ "เดือนนี้ยิงไปเท่าไหร่ ได้แชทกี่ครั้ง" → ตารางนี้คือผลรวมรายวันที่พร้อมใช้

    **⚠️ ไม่เก็บ "ต้นทุนต่อแชท" เป็นคอลัมน์โดยตั้งใจ** — ต้นทุนของช่วงหลายวันต้องคิดจาก
    **ผลรวมเงิน ÷ ผลรวมแชท** ถ้าเก็บรายวันไว้แล้วมีคนเอาไปเฉลี่ยจะได้เลขผิด
    (วัดจริง 23 ก.ย.69: ค่าที่ Meta เฉลี่ยมาให้ = ฿61.31 แต่ผลรวมจริง = ฿62.49)
    · ให้คิดตอนแสดงผลเสมอ (ดู `ads_stats.stats`)

    **เป็นข้อมูล derived** — ลบทิ้งแล้วสร้างใหม่ได้ด้วย `manage.py ads_rebuild`
    """
    date = models.DateField("วันที่", db_index=True)
    account_id = models.CharField("บัญชีโฆษณา", max_length=32, db_index=True)

    spend = models.DecimalField("ใช้เงิน (บาท)", max_digits=14, decimal_places=2, default=0)
    impressions = models.BigIntegerField("แสดงผล", default=0)
    reach = models.BigIntegerField("เข้าถึง (คน)", default=0)
    clicks = models.BigIntegerField("คลิกทั้งหมด", default=0)
    link_clicks = models.BigIntegerField("คลิกลิงก์", default=0)
    video_views = models.BigIntegerField("วิววิดีโอ", default=0)
    engagement = models.BigIntegerField("การมีส่วนร่วมกับโพสต์", default=0)
    chats = models.BigIntegerField("เริ่มแชท", default=0)
    chats_replied = models.BigIntegerField("แชทที่ตอบกลับ", default=0)
    leads = models.BigIntegerField("ลีด", default=0)

    ads = models.IntegerField("จำนวนโฆษณาที่ยิงวันนั้น", default=0)
    campaigns = models.IntegerField("จำนวนแคมเปญ", default=0)
    updated_at = models.DateTimeField("คำนวณล่าสุด", auto_now=True)

    class Meta:
        db_table = "dash_ads_daily"
        verbose_name = "ยอดโฆษณารายวัน"
        verbose_name_plural = "ยอดโฆษณารายวัน"
        ordering = ["-date"]
        constraints = [models.UniqueConstraint(fields=["account_id", "date"],
                                               name="uniq_ads_daily")]
        indexes = [models.Index(fields=["date"])]

    def __str__(self):
        return "%s %s ใช้ %s บาท" % (self.date, self.account_id, self.spend)


# ─────────────────────────────────────────────────────────────────────
# แอปมือถือ — ★ 9 ต.ค.69 (demo บน iPhone ผ่าน Expo Go · เจ้าของประเมินก่อนจ่ายค่า Apple)
#
# แอปไม่ได้ถือคุกกี้ของเว็บ → login ผ่าน LINE Login ตัวเดิมของเว็บในเบราว์เซอร์ของระบบ
# แล้วเว็บส่ง "รหัสใช้ครั้งเดียว" กลับเข้าแอป (MobileLogin) → แอปแลกเป็น token (MobileToken)
# → ส่ง `Authorization: Bearer` มากับทุกคำขอ · ตัวกลาง dashboard/middleware.py ทำให้คำขอนั้น
#   เหมือนคนที่ login อยู่ → API เดิมของเว็บ (Connect / ระบบติดตามรถ) ใช้ได้เลยโดยไม่ต้องแก้
# ─────────────────────────────────────────────────────────────────────
class MobileLogin(models.Model):
    """ใบผ่านทางตอน login จากแอป — 1 แถวต่อการกด "เข้าสู่ระบบ" 1 ครั้ง · อายุ 10 นาที · ใช้ได้ครั้งเดียว

    แอปส่ง `challenge` (= sha256 ของรหัสลับที่แอปถือไว้ · PKCE) มาตอนเริ่ม → ตอนแลก token
    ต้องส่งรหัสลับตัวจริงมาด้วย → แอปอื่นที่ดักรหัสครั้งเดียวไปได้ ก็แลกเป็น token ไม่ได้
    """
    pid = models.CharField("รหัสรายการ", max_length=48, unique=True)
    redirect = models.CharField("ส่งกลับเข้าแอปที่", max_length=300)
    challenge = models.CharField("PKCE challenge", max_length=128)
    code_hash = models.CharField("แฮชรหัสใช้ครั้งเดียว", max_length=64, blank=True, db_index=True)
    user = models.JSONField("คนที่ login", default=dict, blank=True)
    created_at = models.DateTimeField("เริ่ม", auto_now_add=True, db_index=True)
    handed_at = models.DateTimeField("ส่งรหัสกลับเข้าแอป", null=True, blank=True)
    used_at = models.DateTimeField("แลก token แล้ว", null=True, blank=True)

    class Meta:
        db_table = "dash_mobile_login"
        verbose_name = "ใบผ่านทาง login แอปมือถือ"
        verbose_name_plural = "ใบผ่านทาง login แอปมือถือ"


class MobileToken(models.Model):
    """รหัสเข้าระบบของแอปมือถือ — เก็บแค่ **แฮช** (token ตัวจริงอยู่ในเครื่องผู้ใช้เท่านั้น)

    `user` = สำเนา `oxlet_user` ตอน login (ชุดเดียวกับที่ session ของเว็บเก็บ) · หมดอายุ 30 วัน
    · กดออกจากระบบ = `revoked_at` · พนักงานถูกปิดในทะเบียน = ใช้ไม่ได้ทันที (เช็คทุกคำขอ)
    """
    key_hash = models.CharField("แฮช token", max_length=64, unique=True)
    user = models.JSONField("คนที่ login", default=dict, blank=True)
    nickname = models.CharField("ชื่อเล่น", max_length=120, blank=True, db_index=True)
    device = models.CharField("เครื่อง", max_length=160, blank=True)
    created_at = models.DateTimeField("ออกเมื่อ", auto_now_add=True)
    last_used_at = models.DateTimeField("ใช้ล่าสุด", null=True, blank=True)
    expires_at = models.DateTimeField("หมดอายุ")
    revoked_at = models.DateTimeField("ยกเลิกเมื่อ", null=True, blank=True)

    class Meta:
        db_table = "dash_mobile_token"
        verbose_name = "รหัสเข้าระบบแอปมือถือ"
        verbose_name_plural = "รหัสเข้าระบบแอปมือถือ"
        ordering = ["-created_at"]

    def __str__(self):
        return "%s (%s)" % (self.nickname, self.device or "-")


class LeadSheetRow(models.Model):
    """สำเนาแถวของ "ชีทจ่ายเบอร์ ปี69" (แท็บรายเดือน) ใน Postgres — ★ 13 ต.ค.69 เจ้าของสั่ง
    *"อย่าลืมเก็บลง postgres ด้วยนะ เก็บไว้เผื่อทำอย่างอื่นต่อ"*

    **ชีตยังเป็นต้นฉบับ** (แอดมิน/เซลล์กรอกในชีต) · ตารางนี้ดึงซ้ำทุก 10 นาที (`sheet_mirror.py`)
    แทนที่ทั้งแท็บในธุรกรรมเดียว → แถวที่ถูกลบ/แก้ในชีตตามมาด้วย · ช่องหลักแตกเป็นคอลัมน์
    (จับคู่ตามหัวตารางชุดเดียวกับแดชบอร์ด — แต่ละเดือนคอลัมน์ไม่ตรงกัน) · **ทุกช่องดิบอยู่ใน `raw`**
    """
    tab = models.CharField("แท็บ", max_length=40, db_index=True)
    row_no = models.PositiveIntegerField("แถวในชีต")
    tab_month = models.DateField("เดือนของแท็บ", db_index=True)
    code = models.CharField("Code", max_length=40, blank=True, db_index=True)
    received_date = models.DateField("ว/ด/ป", null=True, blank=True, db_index=True)
    time = models.CharField("เวลา", max_length=16, blank=True)
    phone = models.CharField("เบอร์โทร / ID LINE", max_length=160, blank=True, db_index=True)
    seller = models.CharField("เซลล์", max_length=80, blank=True, db_index=True)
    live_team = models.CharField("ทีมไลฟ์", max_length=80, blank=True)
    admin = models.CharField("Admin", max_length=80, blank=True)
    channel = models.CharField("ช่องทาง", max_length=160, blank=True, db_index=True)
    branch = models.CharField("สาขา", max_length=80, blank=True)
    lead_type = models.CharField("type", max_length=80, blank=True)
    ads = models.TextField("ADS", blank=True)
    car_inquiry = models.TextField("รถลูกค้าถาม", blank=True)
    car_formula = models.CharField("CAR / สูตร", max_length=120, blank=True, db_index=True)
    call_proof = models.CharField("แจ้งหลักฐานการโทร", max_length=60, blank=True)
    focus = models.CharField("FOCUS", max_length=60, blank=True)
    contact_at = models.DateTimeField("วัน เวลา ที่ติดต่อ", null=True, blank=True)
    update_count = models.IntegerField("จำนวนอัพเดท", null=True, blank=True)
    last_updated_at = models.DateTimeField("วัน เวลา อัพเดทล่าสุด", null=True, blank=True)
    fill_note = models.TextField("มากรอกชีตกันเถอะ", blank=True)
    profile = models.TextField("PROFILE ลูกค้า จาก ADMIN", blank=True)
    occupation = models.TextField("อาชีพ", blank=True)
    income = models.TextField("รายได้", blank=True)
    job_tenure = models.TextField("อายุงาน", blank=True)
    payment_history = models.TextField("ประวัติการผ่อน", blank=True)
    customer_type = models.CharField("ประเภทลูกค้า", max_length=120, blank=True)
    customer_status = models.CharField("สถานะลูกค้า", max_length=120, blank=True, db_index=True)
    admin_status = models.TextField("Status แอดมิน", blank=True)
    sales_status = models.TextField("Status เซลล์", blank=True)
    raw = models.JSONField("ทุกช่องดิบ {หัวคอลัมน์: ค่า}", default=dict, blank=True)
    synced_at = models.DateTimeField("ดึงจากชีตเมื่อ")

    class Meta:
        db_table = "dash_lead_sheet_row"
        verbose_name = "แถวชีตจ่ายเบอร์ (สำเนา)"
        verbose_name_plural = "แถวชีตจ่ายเบอร์ (สำเนา)"
        ordering = ["tab_month", "row_no"]
        constraints = [models.UniqueConstraint(fields=["tab", "row_no"], name="uniq_lead_sheet_row")]
        indexes = [models.Index(fields=["seller", "received_date"])]

    def __str__(self):
        return "%s แถว %s %s" % (self.tab, self.row_no, self.code)


class BanSheetRow(models.Model):
    """สำเนาแท็บ "รายงานแบน" (Sheet Master) ใน Postgres — ★ 13 ต.ค.69 · ดึงพร้อมชีตจ่ายเบอร์ทุก 10 นาที (แทนที่ทั้งแท็บ)"""
    row_no = models.PositiveIntegerField("แถวในชีต", unique=True)
    ban_date = models.DateField("วันที่แบน", null=True, blank=True, db_index=True)
    time = models.CharField("เวลา", max_length=16, blank=True)
    seller = models.CharField("คนที่โดนแบน", max_length=80, blank=True, db_index=True)
    seller_display = models.CharField("ชื่อที่แสดง", max_length=120, blank=True)
    ban_type = models.CharField("ประเภท", max_length=80, blank=True)
    reason = models.TextField("เหตุผล", blank=True)
    banned_by = models.CharField("คนสั่งแบน", max_length=80, blank=True)
    unban_date = models.CharField("ปลดแบน", max_length=40, blank=True)
    status = models.CharField("สถานะ", max_length=40, blank=True)
    raw_text = models.TextField("ข้อความเดิม", blank=True)
    group_id = models.CharField("กลุ่ม", max_length=64, blank=True)
    raw = models.JSONField("ทุกช่องดิบ", default=dict, blank=True)
    synced_at = models.DateTimeField("ดึงจากชีตเมื่อ")

    class Meta:
        db_table = "dash_ban_sheet_row"
        verbose_name = "แถวรายงานแบน (สำเนา)"
        verbose_name_plural = "แถวรายงานแบน (สำเนา)"
        ordering = ["row_no"]

    def __str__(self):
        return "%s %s %s" % (self.ban_date, self.seller, self.ban_type)


class DevRequest(models.Model):
    """แจ้งผู้พัฒนา — บั๊ก / ขอฟีเจอร์ / สอบถาม จากคนใช้ระบบ · 1 แถวต่อเรื่อง (15 ต.ค.69 · เจ้าของสั่ง)

    ส่งแล้วเด้งข้อความเข้า LINE ส่วนตัวเจ้าของ (dashboard/services/devreq.py) · ไฟล์แนบเก็บนอก /media/
    (`files` = [{id: token, name, size, kind}] · ลบไฟล์เองเกิน 180 วัน แล้วติด "gone")
    """
    KINDS = [("bug", "เจอบั๊ก / ใช้งานไม่ได้"), ("feature", "ขอฟีเจอร์ / ขอแก้"), ("question", "สอบถาม"), ("other", "อื่นๆ")]
    STATUSES = [("new", "ใหม่"), ("doing", "กำลังทำ"), ("done", "เสร็จแล้ว"), ("rejected", "ไม่ทำ")]

    created_at = models.DateTimeField("แจ้งเมื่อ", auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField("แก้ล่าสุด", auto_now=True)
    kind = models.CharField("ประเภท", max_length=12, choices=KINDS, default="bug")
    urgent = models.BooleanField("ด่วน", default=False)
    title = models.CharField("หัวข้อ", max_length=200)
    detail = models.TextField("รายละเอียด", blank=True)
    page = models.CharField("เจอที่หน้าไหน", max_length=300, blank=True)
    requester = models.CharField("ผู้แจ้ง", max_length=80, blank=True)
    requester_role = models.CharField("บทบาทผู้แจ้ง", max_length=20, blank=True)
    requester_uid = models.CharField("บัญชีผู้แจ้ง (ไม่โชว์บนเว็บ)", max_length=80, blank=True)
    files = models.JSONField("ไฟล์แนบ", default=list, blank=True)
    status = models.CharField("สถานะ", max_length=10, choices=STATUSES, default="new", db_index=True)
    note = models.TextField("หมายเหตุจากผู้พัฒนา", blank=True)
    line_ok = models.BooleanField("แจ้ง LINE สำเร็จ", null=True, blank=True)
    line_error = models.CharField("แจ้ง LINE ไม่สำเร็จเพราะ", max_length=300, blank=True)
    user_agent = models.CharField("อุปกรณ์ที่แจ้ง", max_length=300, blank=True)

    class Meta:
        db_table = "dash_dev_request"
        verbose_name = "แจ้งผู้พัฒนา"
        verbose_name_plural = "แจ้งผู้พัฒนา"
        ordering = ["-created_at"]

    def __str__(self):
        return "%s %s" % (self.created_at, self.title)


class LeaveRequest(models.Model):
    """คำขอลา — ★ 21 ต.ค.69 (เจ้าของสั่ง · แอปมือถือ หมวดหน้าหลัก → ลา) · 1 แถวต่อคำขอ

    พนักงานยื่นในแอป → แอดมิน/ผู้บริหารอนุมัติ/ไม่อนุมัติในแอป (dashboard/services/leave.py)
    · `days` = จำนวนวันลาจริง (ตัดวันหยุดประจำสัปดาห์ของคนนั้น + วันหยุดบริษัท · ครึ่งวัน = 0.5)
    · ปฏิทินในแอปแสดงวันลาแทน "ขาด" · ⚠️ ตารางเช็คชื่อที่ส่งเข้า LINE ยังไม่อ่านตารางนี้
    · เก็บชื่อเล่นไว้ในแถว — ลบพนักงานแล้วประวัติการลายังอ่านได้
    """
    PENDING, APPROVED, REJECTED, CANCELLED = "pending", "approved", "rejected", "cancelled"
    STATUSES = [(PENDING, "รออนุมัติ"), (APPROVED, "อนุมัติ"), (REJECTED, "ไม่อนุมัติ"), (CANCELLED, "ยกเลิก")]
    KINDS = [("sick", "ลาป่วย"), ("personal", "ลากิจ"), ("vacation", "ลาพักร้อน"), ("other", "ลาอื่นๆ")]
    HALVES = [("", "เต็มวัน"), ("am", "ครึ่งวันเช้า"), ("pm", "ครึ่งวันบ่าย")]

    employee = models.ForeignKey("checkout.Employee", null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="leave_requests", verbose_name="พนักงาน")
    nickname = models.CharField("ชื่อเล่น", max_length=80, db_index=True)
    kind = models.CharField("ประเภทการลา", max_length=12, choices=KINDS)
    start_date = models.DateField("ลาตั้งแต่", db_index=True)
    end_date = models.DateField("ลาถึง", db_index=True)
    half = models.CharField("ครึ่งวัน", max_length=2, choices=HALVES, blank=True)
    days = models.DecimalField("จำนวนวันลา", max_digits=5, decimal_places=1, default=0)
    reason = models.TextField("เหตุผล", blank=True)
    status = models.CharField("สถานะ", max_length=10, choices=STATUSES, default=PENDING, db_index=True)
    decided_by = models.CharField("อนุมัติ/ไม่อนุมัติโดย", max_length=80, blank=True)
    decided_at = models.DateTimeField("ตัดสินเมื่อ", null=True, blank=True)
    decide_note = models.CharField("หมายเหตุจากผู้อนุมัติ", max_length=300, blank=True)
    created_by = models.CharField("ยื่นโดย", max_length=80, blank=True)
    created_at = models.DateTimeField("ยื่นเมื่อ", auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField("แก้ล่าสุด", auto_now=True)

    class Meta:
        db_table = "dash_leave_request"
        verbose_name = "คำขอลา"
        verbose_name_plural = "คำขอลา"
        ordering = ["-start_date", "-id"]

    def __str__(self):
        return "%s %s %s–%s" % (self.nickname, self.kind, self.start_date, self.end_date)
