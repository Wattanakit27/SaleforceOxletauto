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
