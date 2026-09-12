"""ดาวน์โหลดข้อมูลในฐานข้อมูลออกมาเป็น CSV — ★ ก.ย.69 (เจ้าของสั่ง "อยากให้ export ออกมาได้")

คู่กับ [db_inventory.py](db_inventory.py):
  - `db_inventory` ตอบ **"เก็บอะไรไว้บ้าง"** (นับแถว + อธิบาย ไม่ดึงเนื้อข้อมูล)
  - ไฟล์นี้ตอบ **"เอาออกมาได้"** (เนื้อข้อมูลจริง เป็นไฟล์ในมือเจ้าของ)

ทำไมต้องมี: ข้อมูลที่ระบบสะสมไว้ (แชทกลุ่ม · โปรไฟล์ลูกค้า · ไทม์ไลน์รถ · รอบเบิก-คืน)
อ่านได้แต่ในหน้าเว็บ → **เอาไปทำอย่างอื่นไม่ได้เลย** (เปิด Excel · ส่งให้บัญชี · เก็บสำรองไว้เอง
· ย้ายระบบ) ซึ่งเป็นสิทธิ์พื้นฐานของเจ้าของข้อมูล

หลักคิด
  - **เดินตาม `apps.get_models()` เหมือน db_inventory** → เพิ่มโมเดลใหม่ = export ได้เองทันที
    ไม่ต้องมาไล่เพิ่มลิสต์ (ลิสต์ที่ต้องดูแลมือ = วันหนึ่งจะลืมแล้วข้อมูลบางส่วนออกไม่ได้)
  - **CSV ใส่ BOM** — Excel ไทยไม่เพี้ยน (กติกาเดียวกับ export ไทม์ไลน์รถ / ปุ่ม CSV ในการ์ด)
  - **หัวคอลัมน์เป็นภาษาไทย + ชื่อฟิลด์จริงในวงเล็บ** — คนอ่านออก และยังรู้ว่าตรงกับฟิลด์ไหน
    (เผื่อเอากลับเข้าระบบ/เขียนสคริปต์ต่อ)

★ กติกาข้อมูลส่วนบุคคลที่ยึดไว้ (เหมือนที่ใช้ทั้งระบบ)
  - **LINE user id ของพนักงาน = ห้ามออก** (ใครถือ id ก็ทักหาพนักงานได้ตรง) → ปิดเป็น `Uxxxxx…(พนักงาน)`
  - **LINE user id ของลูกค้า = ออกได้** — เจ้าของขอไว้ใช้ทักกลับ และไฟล์นี้ดาวน์โหลดได้เฉพาะ
    แอดมินสูงสุด/ผู้บริหาร (`_is_boss`) เท่านั้น
  - id ที่ระบบ**ยังไม่รู้ว่าใคร** → ปิดไว้ก่อน (ปลอดภัยกว่าเดาว่าเป็นลูกค้า)
  - รหัสผ่าน / เนื้อ session **ไม่ออกทุกกรณี** (`ALWAYS_DROP`)
"""
import csv
import io
import json
import re

# (ตาราง, ฟิลด์) ที่ห้ามออกจากระบบเด็ดขาด — ไม่ใช่ "ข้อมูลของเจ้าของ" แต่เป็นความลับของระบบ
ALWAYS_DROP = {
    ("auth_user", "password"),          # แฮชรหัสผ่าน — หลุดไปก็เอาไปลองถอดได้
    ("django_session", "session_data"), # เท่ากับคุกกี้ล็อกอินของคนอื่น
}

# ตารางที่ export ไปก็ไม่มีประโยชน์ (ตารางเชื่อมของ Django ล้วนๆ)
SKIP_TABLES = {"auth_permission", "django_content_type"}

# LINE user id: ขึ้นต้น U + hex 32 ตัว
# ⚠️ **ห้ามใส่ \b (ขอบเขตคำ) หน้า U** — ชื่อบัญชี Django ของคนที่ login ผ่าน LINE คือ `line_<userId>`
#   ซึ่ง `_` เป็นอักขระคำ → ไม่มีขอบเขตคำระหว่าง `_` กับ `U` → id พนักงานหลุดออกทาง auth_user
#   (เจอตอนทดสอบจริง) · จับแบบไม่มีขอบเขต = เผลอปิดเกินได้ แต่พลาดด้านปล่อยผ่านไม่ได้
_LINE_ID = re.compile(r"U[0-9a-fA-F]{32}")

# `dash_kv.data` มีก้อนผลสรุปแดชบอร์ด (~3 MB/แถว) ซึ่งเป็น **แคชที่คำนวณใหม่ได้**
# ไม่ใช่ข้อมูลต้นฉบับ → ตัดสั้นไว้ ไม่งั้นไฟล์บวมด้วยของที่ไม่มีใครเอาไปใช้
KV_VALUE_MAX = 4000

# กันไฟล์ระเบิด/แรมหมดถ้าวันหนึ่งตารางโตมาก
MAX_ROWS = 200_000


def _employee_line_ids() -> set:
    """LINE user id ของ **พนักงาน** — ไว้ปิดก่อนเขียนลงไฟล์

    2 แหล่ง: `LineProfile.is_employee` (คนที่เคยคุยผ่านบอท) + **ชีตพนักงาน**
    (คนที่ยังไม่เคยพิมพ์ผ่านบอทเลย — ถ้าไม่อ่านชีต id ของคนกลุ่มนี้จะหลุดออกไป)
    """
    ids = set()
    try:
        from checkout.models import LineProfile
        ids |= set(LineProfile.objects.filter(is_employee=True)
                   .values_list("user_id", flat=True))
    except Exception:
        pass
    try:
        from .google_sheets import fetch_sheet, cell, EMPLOYEE_COL as EM
        for r in (fetch_sheet("employees") or [])[1:]:
            uid = (cell(r, EM.user_id) or "").strip()
            if uid:
                ids.add(uid)
    except Exception:
        pass
    return ids


def _mask(uid: str) -> str:
    return uid[:5] + "…(พนักงาน)"


def _scrub(text: str, emp: set) -> str:
    """ปิด LINE user id ของพนักงานที่ปนอยู่ในข้อความ/JSON

    id ที่ระบบไม่รู้จัก (ไม่อยู่ในชีตพนักงานและไม่เคยคุยกับบอท) ก็ปิดไว้ก่อน —
    ที่ปล่อยผ่านคือ id ของ **ลูกค้าที่ระบบรู้จักแล้ว** เท่านั้น
    """
    def rep(m):
        uid = m.group(0)
        return uid if (uid in _KNOWN_CUSTOMERS and uid not in emp) else _mask(uid)
    return _LINE_ID.sub(rep, text)


_KNOWN_CUSTOMERS = set()


def _load_known_customers():
    global _KNOWN_CUSTOMERS
    try:
        from checkout.models import LineProfile
        _KNOWN_CUSTOMERS = set(LineProfile.objects.filter(is_employee=False)
                               .values_list("user_id", flat=True))
    except Exception:
        _KNOWN_CUSTOMERS = set()


def _fmt(val, emp: set, table: str, field: str):
    """1 ค่า → ข้อความที่เขียนลง CSV ได้ (เวลาเป็นโซนไทย · JSON เป็นข้อความไทยอ่านออก)"""
    import datetime as _dt
    if val is None:
        return ""
    if isinstance(val, bool):
        return "ใช่" if val else "ไม่"
    if isinstance(val, _dt.datetime):
        try:
            from django.utils import timezone
            val = timezone.localtime(val)
        except Exception:
            pass
        return val.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(val, (_dt.date, _dt.time)):
        return val.isoformat()
    if isinstance(val, (dict, list)):
        val = json.dumps(val, ensure_ascii=False, default=str)
    s = str(val)
    if table == "dash_kv" and field == "data" and len(s) > KV_VALUE_MAX:
        s = s[:KV_VALUE_MAX] + "…(ตัดสั้น · เต็ม %s ตัวอักษร)" % f"{len(s):,}"
    return _scrub(s, emp) if "U" in s else s


def _header(f):
    """หัวคอลัมน์: "ชื่อไทย (field)" ถ้าโมเดลตั้งชื่อไทยไว้ · ไม่งั้นใช้ชื่อฟิลด์เฉยๆ"""
    name = f.attname
    try:
        vb = str(f.verbose_name or "")
    except Exception:
        vb = ""
    auto = name.replace("_", " ")
    if vb and vb.lower() != auto.lower():
        return "%s (%s)" % (vb, name)
    return name


def _models():
    """{db_table: model} ของทุกโมเดลที่ export ได้"""
    from django.apps import apps
    out = {}
    for m in apps.get_models():
        t = m._meta.db_table
        if t in SKIP_TABLES:
            continue
        out[t] = m
    return out


def datasets():
    """รายการตารางที่ดาวน์โหลดได้ + จำนวนแถว (ให้ UI ทำปุ่ม)"""
    from .db_inventory import TABLES
    out = []
    for table, model in _models().items():
        info = TABLES.get(table, {})
        try:
            n = model.objects.count()
        except Exception:
            n = None
        out.append({
            "table": table,
            "name": info.get("name") or str(model._meta.verbose_name) or model.__name__,
            "rows": n,
            "pii": bool(info.get("pii")),
        })
    out.sort(key=lambda r: (-(r["rows"] or 0), r["table"]))
    return out


def table_csv(table: str) -> tuple:
    """(bytes ของ CSV, จำนวนแถวที่เขียน, ถูกตัดไหม) — พร้อมดาวน์โหลดเลย (มี BOM)"""
    models = _models()
    model = models.get(table)
    if model is None:
        raise ValueError("ไม่รู้จักตาราง '%s'" % table)

    emp = _employee_line_ids()
    _load_known_customers()

    fields = [f for f in model._meta.concrete_fields
              if (table, f.attname) not in ALWAYS_DROP]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([_header(f) for f in fields])

    qs = model.objects.all()
    pk = model._meta.pk
    try:
        qs = qs.order_by(pk.attname)
    except Exception:
        pass
    n, cut = 0, False
    for obj in qs.iterator():
        if n >= MAX_ROWS:
            cut = True
            break
        w.writerow([_fmt(getattr(obj, f.attname, None), emp, table, f.attname) for f in fields])
        n += 1
    return "﻿".encode("utf-8") + buf.getvalue().encode("utf-8"), n, cut


def all_zip() -> tuple:
    """(bytes ของ .zip, สรุปรายตาราง) — ทุกตารางเป็น CSV ไฟล์ละตาราง + อ่านก่อน.txt

    ตารางไหนอ่านไม่ได้ = ข้ามแล้วจดไว้ใน "อ่านก่อน.txt" **ไม่ล้มทั้งไฟล์**
    (export ที่ล้มเพราะตารางเดียวพัง = เจ้าของไม่ได้ข้อมูลอะไรเลย)
    """
    import zipfile

    summary, zbuf = [], io.BytesIO()
    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
        for d in datasets():
            t = d["table"]
            try:
                data, n, cut = table_csv(t)
                z.writestr("%s.csv" % t, data)
                summary.append({"table": t, "name": d["name"], "rows": n, "cut": cut, "error": ""})
            except Exception as e:
                summary.append({"table": t, "name": d["name"], "rows": 0, "cut": False,
                                "error": str(e)[:160]})
        z.writestr("อ่านก่อน.txt", readme(summary).encode("utf-8"))
    return zbuf.getvalue(), summary


def readme(summary) -> str:
    """คำอธิบายที่แนบไปในไฟล์ zip — คนเปิดอีก 6 เดือนต้องอ่านรู้เรื่องเอง"""
    from datetime import datetime
    from .db_inventory import SHEET_NOTE
    L = ["ข้อมูลจากฐานข้อมูล Oxlet",
         "ดึงเมื่อ: %s" % datetime.now().strftime("%d/%m/%Y %H:%M"),
         "",
         "ไฟล์ในนี้เป็น CSV ไฟล์ละตาราง (UTF-8 + BOM → เปิดด้วย Excel ได้เลย ภาษาไทยไม่เพี้ยน)",
         "หัวคอลัมน์เขียนเป็น: ชื่อไทย (ชื่อฟิลด์จริงในระบบ)",
         "",
         "ตาราง:"]
    for s in summary:
        note = ""
        if s["error"]:
            note = "  ← อ่านไม่ได้: %s" % s["error"]
        elif s["cut"]:
            note = "  ← ตัดที่ %s แถว" % f"{MAX_ROWS:,}"
        L.append("  %-34s %8s แถว   %s%s" % (s["table"], f"{s['rows']:,}", s["name"], note))
    L += ["",
          "─" * 60,
          "ข้อมูลการขายไม่ได้อยู่ในไฟล์นี้ — อยู่ใน Google Sheets:"]
    for s in SHEET_NOTE:
        L.append("  • %s — %s" % (s["name"], s["what"]))
    L += ["",
          "ข้อมูลส่วนบุคคล (PDPA):",
          "  • LINE user id ของ **พนักงาน** ถูกปิดไว้ (Uxxxxx…(พนักงาน)) — ใครถือ id ก็ทักหาได้ตรง",
          "  • LINE user id ของ **ลูกค้า** ไม่ปิด (เจ้าของขอไว้ใช้ทักกลับ)",
          "  • ไม่มีรหัสผ่าน / เนื้อ session ในไฟล์นี้",
          "  • ไฟล์นี้มีชื่อ-ข้อความของคนจริง — เก็บให้ดี อย่าส่งต่อโดยไม่จำเป็น",
          "",
          "ไฟล์รูป/วิดีโอไม่ได้อยู่ในนี้ (อยู่ใน Google Drive) —",
          "ตารางเก็บแค่ตัวชี้ · อยากได้รูปของรถคันไหนใช้ปุ่ม Export ในป๊อปอัปรถคันนั้น"]
    return "\n".join(L)
