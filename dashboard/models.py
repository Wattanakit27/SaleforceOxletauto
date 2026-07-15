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
