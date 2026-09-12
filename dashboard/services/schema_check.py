"""เช็คว่า "โครงฐานข้อมูลตามโค้ดทัน" หรือยัง — ★ ก.ย.69 (เจ้าของสั่ง)

ที่มา: deploy แล้ว `git pull` แต่ **ลืม `migrate`** → โค้ดใหม่เขียนคอลัมน์ที่ยังไม่มีในตาราง
→ ทุกข้อความที่วิ่งเข้ามาถูกทิ้งหมด **แบบเงียบ** (งานเก็บอยู่ใน background thread
   ผู้เรียกเลยไม่เห็น error · ร่องรอยอยู่แค่ใน KV ที่ไม่มีใครเปิดดู)

เจ้าของสั่ง: *"ถ้าไม่เข้าฐานข้อมูล ก็ช่วยแจ้งมาด้วย"* → ตัวนี้ทำให้มันร้องเองใน 3 ที่:
  - response ที่ตอบกลับ n8n (เห็นทันทีใน execution ตอนยิงทดสอบ)
  - `manage.py checkout_status` (บรรทัดแรกสุด)
  - หน้าสถานะระบบของแอดมิน

**เบา**: ถามฐานข้อมูลจริงแค่ทุก 60 วินาที (cache) — เรียกทุก webhook ได้ไม่หนัก
"""
import time

_TTL = 60
_cache = {"at": 0.0, "pending": []}


def pending_migrations(force: bool = False) -> list:
    """คืนรายชื่อ migration ที่ยังไม่ได้รัน เช่น `["checkout.0011_groupchat_channel…"]`

    ว่าง = โครงฐานข้อมูลทันโค้ดแล้ว · อ่านไม่ได้ (DB ล่ม) = คืนว่างเหมือนกัน
    (ไม่ใช่หน้าที่ของตัวนี้ที่จะไปเตือนเรื่อง DB ล่ม — มีตัวอื่นดูอยู่แล้ว)
    """
    now = time.time()
    if not force and _cache["at"] and (now - _cache["at"]) < _TTL:
        return _cache["pending"]
    out = []
    try:
        from django.db import connections, DEFAULT_DB_ALIAS
        from django.db.migrations.executor import MigrationExecutor
        ex = MigrationExecutor(connections[DEFAULT_DB_ALIAS])
        targets = ex.loader.graph.leaf_nodes()
        # ⚠️ migration_plan คืน (Migration, ถอยหลังไหม) — ไม่ใช่ (app, name)
        #   เผลอ unpack เป็น 2 ตัวแล้วต่อสตริงจะได้ชื่อห้อย ".False" ติดมา
        out = ["%s.%s" % (m.app_label, m.name) for m, _backwards in ex.migration_plan(targets)]
    except Exception:
        out = []
    _cache.update({"at": now, "pending": out})
    return out


def warn_line() -> str:
    """ข้อความเตือนสั้นๆ พร้อมวิธีแก้ · ไม่มีปัญหา = คืนค่าว่าง"""
    p = pending_migrations()
    if not p:
        return ""
    return ("⚠️ ยังไม่ได้รัน migrate %d ตัว (%s) → **ข้อมูลใหม่จะเขียนลงฐานข้อมูลไม่ได้** "
            "· แก้: cd /opt/oxlet && .venv/bin/python manage.py migrate && systemctl restart oxlet"
            % (len(p), ", ".join(p[:3]) + ("…" if len(p) > 3 else "")))
