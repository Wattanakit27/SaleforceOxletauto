"""สารบัญฐานข้อมูล — "ระบบเก็บอะไรไว้บ้าง" ในที่เดียว

ทำไมต้องมี (เจ้าของขอ ก.ย.69):
  ระบบโตขึ้นเรื่อยๆ (ขาย → ติดตามรถ → เบิก-คืนรถ → เก็บแชทกลุ่ม LINE) แล้ว
  **ไม่มีใครตอบได้ว่าตอนนี้เก็บข้อมูลอะไรไว้กี่ตาราง อันไหนมีข้อมูลส่วนบุคคล**
  ซึ่งเป็นคำถามแรกที่ต้องตอบได้เวลาคุยเรื่อง PDPA / เวลาจะลบข้อมูลทิ้ง

หลักคิด:
  - **นับแถว + อธิบายว่าเก็บอะไร** เท่านั้น — ไม่ดึงเนื้อข้อมูลออกมาโชว์
    (หน้านี้ตอบ "มีอะไร" ไม่ใช่ "ข้อมูลใครบ้าง" · อยากดูรายตัวมีหน้าเฉพาะของมันอยู่แล้ว)
  - ทุกอย่าง best-effort — ตารางไหนอ่านไม่ได้ (ยังไม่ migrate/DB ล่ม) บอกว่าอ่านไม่ได้
    แล้วไปต่อ ไม่ทำให้ทั้งหน้าพัง
  - `pii=True` = มีข้อมูลส่วนบุคคล (ชื่อ/LINE id/เบอร์/รูปคน) → หน้าเว็บติดป้ายเตือน
"""
from datetime import date, datetime

# ตารางที่ "ไม่ได้อยู่ในโมเดลของเราเอง" แต่อยากอธิบายด้วย (ตารางระบบของ Django)
_SYSTEM_LABEL = "ตารางระบบ Django"

# app_label → ชื่อกลุ่มที่คนอ่านออก
APP_LABEL = {
    "dashboard": "ยอดขาย / แดชบอร์ด (dashboard)",
    "cars": "ติดตามรถ (cars)",
    "checkout": "เบิก-คืนรถ (checkout)",
    "auth": _SYSTEM_LABEL,
    "admin": _SYSTEM_LABEL,
    "contenttypes": _SYSTEM_LABEL,
    "sessions": _SYSTEM_LABEL,
}

# ลำดับการโชว์ (ของเราก่อน ตารางระบบไว้ท้าย)
APP_ORDER = ["dashboard", "cars", "checkout", "auth", "admin", "contenttypes", "sessions"]

# db_table → คำอธิบาย
#   name  = ชื่อที่คนอ่านออก
#   what  = เก็บอะไร (ประโยคเดียว)
#   pii   = มีข้อมูลส่วนบุคคลไหม
#   keep  = นโยบายเก็บ/ลบ (ว่าง = ไม่มีนโยบาย เก็บถาวร)
TABLES = {
    # ---------- ล็อกของระบบ ----------
    "dash_meta_post_snapshot": dict(
        name="ยอดโพสต์ Facebook (ทุกเที่ยงคืน)",
        what="ยอดสะสมของทุกโพสต์ในเพจเรา (วิว/ไลก์/คอมเมนต์/แชร์/คลิก/ดูเฉลี่ย) จดทุกเที่ยงคืน · "
             "เอาแถว cron วันนี้ลบเมื่อวาน = ยอดรายวัน (Meta ไม่ให้ยอดรายวันของไลก์/แชร์) · "
             "เป็นยอดรวม ไม่มีชื่อคนกด",
        pii=False, keep="เก็บถาวร"),
    "dash_meta_ad_daily": dict(
        name="ผลโฆษณา Facebook (รายวัน)",
        what="ใช้เงิน/แสดงผล/เข้าถึง/คลิก + actions ดิบ (ลีด แชท ฯลฯ) ต่อโฆษณาต่อวัน · "
             "เฉพาะบัญชีโฆษณาของบริษัทนี้ (ด่าน META_AD_ACCOUNTS)",
        pii=False, keep="เก็บถาวร"),
    "dash_meta_raw": dict(
        name="ข้อมูลดิบจาก Meta",
        what="คำตอบจาก Facebook ทั้งก้อน (โพสต์ + โฆษณา) ไว้คิดตัวเลขใหม่ย้อนหลัง · "
             "ตัด token ที่ฝังในลิงก์หน้าถัดไปออกแล้ว · ใหญ่สุดในระบบ (~12 MB/วัน)",
        pii=False, keep="เก็บ 90 วัน แล้วลบเอง"),
    "dash_event_log": dict(
        name="ล็อกเหตุการณ์ระบบ",
        what="ส่งอะไรออก LINE บ้าง สำเร็จ/ล้มเพราะอะไร · webhook ขาเข้าที่ผิดปกติ · "
             "งานอัตโนมัติที่ล้ม — เก็บเป็นแถวต่อเหตุการณ์ จึงย้อนดูได้ว่าเริ่มพังเมื่อไหร่ "
             "(ต่างจาก dash_kv ที่เก็บแค่ครั้งล่าสุด)",
        pii=False, keep="เก็บ 90 วัน แล้วลบเอง"),

    # ---------- ยอดขาย ----------
    "dash_kv": dict(
        name="ค่าคอนฟิก + สถานะระบบ (key-value)",
        what="ที่เก็บของจุกจิกทั้งระบบ: ผลสรุปแดชบอร์ดที่คำนวณไว้ล่วงหน้า · heartbeat ของ cron · "
             "ค่าตั้งกลุ่ม LINE · รายชื่อกลุ่มที่บอทรู้จัก · แคชชื่อโปรไฟล์ LINE",
        pii=True, keep="ทับค่าเดิมเรื่อยๆ (ไม่สะสมแถว)"),
    "dash_form": dict(
        name="ฟอร์มไฟแนนซ์ / ขอสินเชื่อ",
        what="ฟอร์ม “เช็คไฟแนนซ์ก่อนเซ็น” และ “ขอสินเชื่อ” ที่เซลล์ส่งเข้ามา (สำเนาไว้ย้อนดู)",
        pii=True, keep=""),
    "dash_followup_log": dict(
        name="สถิติการทวงงานรายวัน",
        what="ต่อวัน/ต่อเซลล์: ยังไม่โทรกี่เคส · ไม่ใส่สถานะกี่เคส · ดีลค้าง · ถูกทวงกี่รอบ",
        pii=False, keep=""),
    "dash_seller_weekly": dict(
        name="ผลงานเซลล์รายสัปดาห์",
        what="ต่อสัปดาห์/ต่อเซลล์: lead · RJ · จอง · ปล่อย · ยอดเงิน · ไลฟ์ · คลิป",
        pii=False, keep=""),
    # ---------- ติดตามรถ ----------
    "cars_car": dict(
        name="รถในระบบ",
        what="ข้อมูลรถแต่ละคัน: รหัส · ทะเบียน · รุ่น/ปี/สี/เลขไมล์ · สเตปปัจจุบัน · ความด่วน · "
             "ธงงานค้าง · โฟลเดอร์รูปใน Google Drive",
        pii=False, keep=""),
    "cars_scanlog": dict(
        name="ประวัติเปลี่ยนสเตป (ไทม์ไลน์รถ)",
        what="ทุกครั้งที่มีคนเปลี่ยนสเตปรถ: ใครเปลี่ยน · เมื่อไหร่ · หมายเหตุ · รูป/วิดีโอที่แนบ",
        pii=True, keep=""),
    "cars_branch": dict(name="สาขา", what="รายชื่อสาขา/ลานจอด", pii=False, keep=""),
    "cars_loginevent": dict(
        name="Log การเข้าสู่ระบบ",
        what="ทุกครั้งที่มีคน login (สำเร็จ/ไม่สำเร็จ): บัญชี · วิธี · บทบาท · IP · อุปกรณ์",
        pii=True, keep=""),
    "cars_presence": dict(
        name="คนออนไลน์ตอนนี้",
        what="แถวละคน — เห็นล่าสุดเมื่อไหร่ อยู่หน้าไหน (ใช้ทำชิป “N ออนไลน์”)",
        pii=True, keep="1 แถว/คน (ทับค่าเดิม ไม่สะสม)"),
    # ---------- เบิก-คืนรถ ----------
    "checkout_carmovement": dict(
        name="รอบเบิก-คืนรถ",
        what="ใครเบิกรถคันไหน ไปทำอะไร ตอนไหน คืนเมื่อไหร่ · มุมที่ถ่ายครบ · ขอน้ำมันไหม · "
             "มาจากทางไหน (กดในเว็บ / บอทอ่านจากกลุ่ม LINE / นำเข้าจาก log)",
        pii=True, keep=""),
    "checkout_movementphoto": dict(
        name="รูปตอนเบิก/คืนรถ",
        what="รายการรูปของแต่ละรอบ (ตัวไฟล์อยู่ใน Google Drive — ตารางนี้เก็บแค่ตัวชี้)",
        pii=False, keep=""),
    "checkout_groupchat": dict(
        name="แชทกลุ่ม LINE + แชทลูกค้า",
        what="ข้อความที่วิ่งผ่านบอท (กลุ่มงาน + ลูกค้าทัก 1:1): ข้อความ · สติกเกอร์ · อิโมจิ · "
             "ธงว่ามีรูป/ไฟล์",
        pii=True, keep="กลุ่ม 90 วัน · ลูกค้า 60 วัน (ตั้งใน checkout/constants.py)"),
    "checkout_lineprofile": dict(
        name="โปรไฟล์คนที่คุยกับบอท LINE",
        what="1 แถว/คน — LINE user id · ชื่อที่ตั้งใน LINE · ชื่อเล่น(ถ้าเป็นพนักงาน) · "
             "เคยคุยกี่ข้อความ · ทักครั้งแรก/ล่าสุดเมื่อไหร่ · เจอจากบัญชีบอทไหน (ไม่เก็บรูปโปรไฟล์)",
        pii=True, keep="โปรไฟล์ลูกค้าที่เงียบเกิน 60 วันถูกลบ · ของพนักงานเก็บไว้ (ใช้เทียบชื่อ)"),
    "checkout_checklistconfig": dict(
        name="ชุดเช็คลิสต์เบิก-คืน",
        what="แม่แบบเช็คลิสต์ (เผื่อทำหลายชุด) — ตอนนี้ใช้ชุดฝังในโค้ดอยู่",
        pii=False, keep=""),
    "checkout_checklistitem": dict(
        name="ข้อในเช็คลิสต์",
        what="รายข้อของชุดเช็คลิสต์ (บังคับ/ไม่บังคับ · ต้องมีรูปกี่รูป)",
        pii=False, keep=""),
    "checkout_violationlog": dict(
        name="บันทึกทำผิดกติกา",
        what="เผื่อบันทึกเคสที่ไม่ทำตามกติกา (เบิกไม่คืน / ไม่ส่งรูป) — ยังไม่เปิดใช้",
        pii=True, keep=""),
    "checkout_equipmentissue": dict(
        name="ของหาย/ของเสียในรถ",
        what="เผื่อบันทึกอุปกรณ์ในรถที่หาย/ชำรุด — ยังไม่เปิดใช้",
        pii=False, keep=""),
    "checkout_lineeventlog": dict(
        name="Log event ดิบจาก LINE",
        what="เผื่อเก็บ event ดิบเพื่อดีบัก — ยังไม่เปิดใช้",
        pii=True, keep=""),
    # ---------- ตารางระบบ ----------
    "auth_user": dict(
        name="บัญชีผู้ใช้ (Django)",
        what="บัญชีของคนที่เข้าระบบติดตามรถ (คนงาน + คนที่ login ผ่าน LINE จะถูกสร้างให้อัตโนมัติ)",
        pii=True, keep=""),
    "auth_group": dict(name="กลุ่มสิทธิ์ (บทบาท)", what="บทบาท 10 แบบของระบบติดตามรถ", pii=False, keep=""),
    "auth_permission": dict(name="สิทธิ์ย่อย", what="สิทธิ์ระดับตารางของ Django (ระบบสร้างเอง)", pii=False, keep=""),
    "auth_user_groups": dict(name="ผู้ใช้ ↔ บทบาท", what="ใครอยู่บทบาทไหน", pii=False, keep=""),
    "auth_group_permissions": dict(name="บทบาท ↔ สิทธิ์ย่อย", what="ระบบสร้างเอง", pii=False, keep=""),
    "auth_user_user_permissions": dict(name="ผู้ใช้ ↔ สิทธิ์ย่อย", what="ระบบสร้างเอง", pii=False, keep=""),
    "django_admin_log": dict(
        name="Log การแก้ข้อมูลใน /dj-admin/",
        what="ใครแก้อะไรผ่านหน้า Django admin", pii=True, keep=""),
    "django_content_type": dict(name="ทะเบียนชนิดข้อมูล", what="ระบบสร้างเอง", pii=False, keep=""),
    "django_migrations": dict(name="ประวัติ migrate", what="ไล่ว่าอัปโครงฐานข้อมูลถึงขั้นไหนแล้ว", pii=False, keep=""),
    "django_session": dict(
        name="เซสชัน",
        what="ปกติ **ว่างเปล่า** — เว็บนี้เก็บ session ในคุกกี้ที่เซ็นชื่อ ไม่ได้เก็บลงตาราง",
        pii=False, keep=""),
}

# คีย์ใน dash_kv (key-value) → อธิบายว่าอะไร · ตารางนี้เป็น "ที่เก็บของรวม" คนอ่านจาก
# ชื่อตารางไม่ออกว่ามีอะไร จึงลิสต์คีย์ให้ดูด้วย
KV_LABEL = {
    "main": "ผลสรุปแดชบอร์ดที่คำนวณไว้ล่วงหน้า (ก้อนใหญ่สุด)",
    "cron_tick": "heartbeat ของ cron (ทำงานล่าสุดเมื่อไหร่)",
    "cron_followup": "log การส่งข้อความ “ตามด่วน”",
    "followup_rounds": "จำนวนรอบส่งต่อวัน (ตัวหารของ %)",
    "precompute_last": "ผลการคำนวณล่วงหน้าครั้งล่าสุด",
    "sheet_config": "การย้ายไฟล์/แท็บ Google Sheets",
    "sheets_fetch_last": "ผลการดึงชีตครั้งล่าสุด (ใช้เตือนเวลาดึงพลาด)",
    "line_groups": "กลุ่ม LINE ที่บอทรู้จัก (id + ชื่อ)",
    "line_webhook_last": "webhook จาก LINE เข้ามาล่าสุดเมื่อไหร่",
    "line_profiles": "แคชชื่อโปรไฟล์ LINE (กันยิง API ซ้ำ)",
    "checkout_line_config": "ตั้งค่ากลุ่มที่ดักเก็บข้อมูลเบิก-คืน",
    "checkout_seen_msgs": "message id ที่อ่านแล้ว (กันนับซ้ำ)",
    "chat_store_last": "ผลการเก็บแชทครั้งล่าสุด",
    "report_line_config": "ตั้งค่ารายงานเข้าไลน์รายวัน",
    "report_line_last": "ส่งรายงานรายวันล่าสุดวันไหน (กันส่งซ้ำ)",
}


def _count(model):
    try:
        return model.objects.count(), ""
    except Exception as e:
        return None, str(e)[:120]


def _bare_tables():
    """ตารางที่มีอยู่จริงใน DB แต่ไม่มีโมเดล (ตาราง m2m + django_migrations)"""
    try:
        from django.db import connection
        with connection.cursor() as c:
            return set(connection.introspection.table_names(c))
    except Exception:
        return set()


def _kv_keys():
    """คีย์ที่มีใน dash_kv + ขนาดคร่าวๆ — ให้เห็นว่า “ที่เก็บของรวม” มีอะไรอยู่"""
    out = []
    try:
        import json as _json
        from dashboard.models import KVStore
        # ⚠️ ฟิลด์เก็บค่าชื่อ **`data`** ไม่ใช่ `value` — เคยเขียนผิดแล้ว `.only("value")`
        #   โยน FieldError ทั้งก้อนโดน except กลืน → ตารางนี้ **ว่างเปล่าเสมอ** ทั้งที่มี 15 คีย์
        for row in KVStore.objects.all().only("key", "data", "updated_at"):
            try:
                size = len(_json.dumps(row.data, ensure_ascii=False))
            except Exception:
                size = 0
            out.append({
                "key": row.key,
                "what": KV_LABEL.get(row.key, ""),
                "sizeKb": round(size / 1024, 1),
                "updatedAt": row.updated_at.isoformat() if getattr(row, "updated_at", None) else "",
            })
    except Exception:
        return []
    out.sort(key=lambda r: -r["sizeKb"])
    return out


def inventory():
    """{ok, generatedAt, engine, groups, kv, totals} — best-effort ทั้งหมด"""
    from django.apps import apps
    from django.conf import settings

    existing = _bare_tables()
    seen = set()
    by_app = {}

    for model in apps.get_models():
        meta = model._meta
        app = meta.app_label
        table = meta.db_table
        seen.add(table)
        n, err = _count(model)
        info = TABLES.get(table, {})
        by_app.setdefault(app, []).append({
            "table": table,
            "model": model.__name__,
            "name": info.get("name") or meta.verbose_name or model.__name__,
            "what": info.get("what", ""),
            "pii": bool(info.get("pii")),
            "keep": info.get("keep", ""),
            "rows": n,
            "cols": len([f for f in meta.get_fields() if getattr(f, "concrete", False)]),
            "error": err,
            "missing": table not in existing if existing else False,
        })
        # ตาราง m2m ที่ Django สร้างให้เอง (auth_user_groups ฯลฯ)
        for m2m in meta.many_to_many:
            t = m2m.m2m_db_table() if hasattr(m2m, "m2m_db_table") else ""
            if t and t not in seen:
                seen.add(t)
                info2 = TABLES.get(t, {})
                by_app.setdefault(app, []).append({
                    "table": t, "model": "", "name": info2.get("name") or t,
                    "what": info2.get("what", ""), "pii": bool(info2.get("pii")),
                    "keep": info2.get("keep", ""), "rows": None, "cols": 2,
                    "error": "", "missing": t not in existing if existing else False,
                })

    # ตารางที่อยู่ใน DB แต่ไม่มีโมเดล (django_migrations)
    for t in sorted(existing - seen):
        info = TABLES.get(t, {})
        by_app.setdefault("_other", []).append({
            "table": t, "model": "", "name": info.get("name") or t,
            "what": info.get("what", ""), "pii": bool(info.get("pii")),
            "keep": info.get("keep", ""), "rows": None, "cols": None,
            "error": "", "missing": False,
        })

    groups, total_rows, total_tables, pii_tables = [], 0, 0, 0
    order = APP_ORDER + [a for a in sorted(by_app) if a not in APP_ORDER]
    sysgroup = None
    for app in order:
        rows = by_app.get(app)
        if not rows:
            continue
        rows.sort(key=lambda r: (-(r["rows"] or 0), r["table"]))
        for r in rows:
            total_tables += 1
            total_rows += r["rows"] or 0
            if r["pii"]:
                pii_tables += 1
        label = APP_LABEL.get(app, _SYSTEM_LABEL if app == "_other" else app)
        if label == _SYSTEM_LABEL:          # ยุบตารางระบบทั้งหมดเข้ากลุ่มเดียว
            if sysgroup is None:
                sysgroup = {"app": "system", "label": label, "tables": [], "system": True}
                groups.append(sysgroup)
            sysgroup["tables"].extend(rows)
        else:
            groups.append({"app": app, "label": label, "tables": rows, "system": False})

    engine = ""
    try:
        db = (settings.DATABASES or {}).get("default") or {}
        eng = (db.get("ENGINE") or "").rsplit(".", 1)[-1]
        engine = "PostgreSQL" if "postgres" in eng else ("SQLite" if "sqlite" in eng else eng)
        if db.get("HOST"):
            engine += " @ %s" % db["HOST"]
    except Exception:
        pass

    return {
        "ok": True,
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "engine": engine or "(ไม่ทราบ)",
        "groups": groups,
        "kv": _kv_keys(),
        "totals": {"tables": total_tables, "rows": total_rows, "pii": pii_tables},
        "sheets": SHEET_NOTE,
    }


# ★ สำคัญ: ข้อมูลการขายทั้งหมด **ไม่ได้อยู่ในฐานข้อมูลนี้** — อยู่ใน Google Sheets
#   ถ้าไม่เขียนไว้ คนอ่านหน้านี้จะเข้าใจผิดว่า "ระบบเก็บแค่นี้"
SHEET_NOTE = [
    {"name": "ลีด (leads)", "what": "รายการลีดทั้งหมด — แท็บรายเดือน"},
    {"name": "รายงานฝ่ายขาย (sales_reports)", "what": "เคสจอง/สถานะ/วันปล่อย/ราคา + โปรไฟล์ลูกค้า"},
    {"name": "จอง (bookings)", "what": "แท็บ จอง/จบ รายเดือน"},
    {"name": "ไลฟ์ (live_sessions / live_followups)", "what": "เซสชันไลฟ์ + คลิปติดตาม"},
    {"name": "พนักงาน (employees)", "what": "ชื่อ · ชื่อเล่น · LINE user id · group id · ตำแหน่ง"},
    {"name": "ชีตตั้งค่า", "what": "ตั้งค่าเซลล์ · แอดมิน · เทเลเซลล์ · ตั้งเวลาส่ง · ONHAND · โฟกัสเซลล์"},
]
