# -*- coding: utf-8 -*-
"""ยิง SQL ดูข้อมูลดิบจากหน้าเว็บ (แบบ DbVisualizer) — ★ 16 ก.ย.69 เจ้าของขอ

*"ให้มันแสดง query แบบเป็น raw data · ให้มันเป็นการ query จาก postgres จริงๆ
และให้มันสามารถ export ข้อมูลตาม filter ได้ด้วย เช่น ช่วงวันที่นี้ถึงวันที่นี้"*

สารบัญฐานข้อมูล ([db_inventory.py](db_inventory.py)) ตอบว่า **"เก็บอะไรไว้"** ·
ดาวน์โหลด ([db_export.py](db_export.py)) ตอบว่า **"เอาทั้งตารางออกมา"** ·
ไฟล์นี้ตอบว่า **"ขอดู/ขอเอาเฉพาะที่อยากได้"** — เลือกคอลัมน์เอง กรองเอง join เองได้

═══ ความปลอดภัย — ฐานข้อมูลนี้มีแชทลูกค้าและข้อมูลพนักงานอยู่ ═══
เปิดช่องให้พิมพ์ SQL จากหน้าเว็บ = ต้องกันหลายชั้น **ห้ามพึ่งการกรองคำอย่างเดียว**
(blocklist พลาดได้เสมอ และคอลัมน์ชื่อ `set`/`copy` ก็ทำให้ false positive):

  1. **`SET TRANSACTION READ ONLY` ที่ฝั่ง Postgres** — ชั้นที่เชื่อได้จริง
     ต่อให้หลุดด่านอื่นมาได้ คำสั่งเขียนก็ล้มที่ตัวฐานข้อมูลเอง
  2. **rollback เสมอ** ไม่ว่าจะสำเร็จหรือไม่ — ไม่มีอะไรค้างให้ commit
  3. **`statement_timeout`** — กัน query หนักลากเซิร์ฟเวอร์ทั้งเครื่องล่ม
  4. ต้องขึ้นต้นด้วย `SELECT`/`WITH` · **ห้ามมี `;` คั่น** (psycopg2 ยิงหลายคำสั่งรวดเดียวได้)
  5. บล็อกฟังก์ชันอ่านไฟล์/เรียกเครือข่ายของ Postgres (`pg_read_file`, `dblink`, `lo_export`…)
  6. **ปิด LINE user id ของพนักงานในผลลัพธ์และไฟล์ export** เหมือน db_export เป๊ะ
     + ไม่แสดงแฮชรหัสผ่าน/เนื้อ session (กติกาเดิมของโปรเจกต์)

สิทธิ์เข้าถึง = `_is_boss` (แอดมินสูงสุด + ผู้บริหาร) — คุมที่ view ไม่ใช่ที่นี่
"""
import re
import time

# ── ขีดจำกัด ──
ROWS_SCREEN = 200          # โชว์บนจอกี่แถว (ปรับได้จากหน้าเว็บ)
ROWS_SCREEN_MAX = 2000     # เพดานของ "โชว์บนจอ" — เกินนี้เบราว์เซอร์อืด
ROWS_EXPORT_MAX = 200_000  # เพดานของไฟล์ export (เท่ากับ db_export.MAX_ROWS)
TIMEOUT_MS = 20_000        # query นานเกินนี้ = ตัด (nginx ตัดที่ 120 วิ)
CELL_MAX = 2000            # ตัดข้อความยาวๆ ก่อนส่งขึ้นจอ (ไฟล์ export ไม่ตัด)

# ── ชื่อคอลัมน์ที่ไม่แสดงค่าเด็ดขาด (กติกาเดิมจาก db_export.ALWAYS_DROP) ──
HIDE_FIELDS = {"password", "session_data"}

_START = re.compile(r"^\s*(select|with)\b", re.I)
# ★ คำสั่งเขียนที่ "ซ่อนใน WITH" — `WITH x AS (DELETE ... RETURNING *) SELECT * FROM x`
#   ผ่านด่าน "ขึ้นต้นด้วย WITH" ได้ และไม่มี `;` ด้วย → ต้องดักคำเขียนทั้งประโยค
#   (ขอบคำ `\b` ทำให้ชื่อคอลัมน์อย่าง `deleted_at`/`updated_at` ไม่โดนจับ)
_WRITE = re.compile(r"\b(insert|update|delete|merge|truncate|drop|alter|create|grant"
                    r"|revoke|vacuum|reindex|cluster|refresh)\b", re.I)
# ฟังก์ชันที่อ่านไฟล์/ออกเน็ต/เขียนไฟล์ได้ — READ ONLY ไม่ได้กันพวกนี้
_DANGER = re.compile(
    r"\b(pg_read_file|pg_read_binary_file|pg_ls_dir|pg_stat_file|lo_import|lo_export"
    r"|dblink|pg_sleep|pg_terminate_backend|pg_cancel_backend|copy)\s*\(", re.I)
# :from / :to — ไม่ใช่ `::text` (cast ของ Postgres)
_PARAM = re.compile(r"(?<!:):(from|to)\b", re.I)

# LINE id ของพนักงานเปลี่ยนไม่บ่อย แต่ `_employee_line_ids()` ต้องอ่าน Google Sheets
# → แคชไว้ ไม่งั้นทุกครั้งที่กด "รัน" จะรอชีตหลายวินาที
_EMP_CACHE = {"at": 0.0, "ids": None}
_EMP_TTL = 300


class QueryError(Exception):
    """ข้อความที่เอาไปโชว์ผู้ใช้ได้ตรงๆ (ไม่ใช่ traceback)"""


def _emp_ids() -> set:
    from .db_export import _employee_line_ids, _load_known_customers
    now = time.time()
    if _EMP_CACHE["ids"] is None or (now - _EMP_CACHE["at"]) > _EMP_TTL:
        try:
            _load_known_customers()
            _EMP_CACHE["ids"] = _employee_line_ids()
        except Exception:
            _EMP_CACHE["ids"] = set()
        _EMP_CACHE["at"] = now
    return _EMP_CACHE["ids"] or set()


def check(sql: str) -> str:
    """ตรวจว่า SQL นี้ยอมให้รันไหม — คืน SQL ที่ตัดช่องว่าง/`;` ท้ายออกแล้ว"""
    s = (sql or "").strip().rstrip(";").strip()
    if not s:
        raise QueryError("ยังไม่ได้พิมพ์คำสั่ง")
    if not _START.match(s):
        raise QueryError("อนุญาตเฉพาะคำสั่งอ่านข้อมูล — ต้องขึ้นต้นด้วย SELECT หรือ WITH")
    if ";" in s:
        raise QueryError("ใส่ได้ครั้งละ 1 คำสั่ง (ห้ามมี ; คั่นกลาง)")
    m = _WRITE.search(s)
    if m:
        raise QueryError(
            "หน้านี้อ่านข้อมูลได้อย่างเดียว — เจอคำว่า %s ในคำสั่ง" % m.group(1).upper())
    m = _DANGER.search(s)
    if m:
        raise QueryError("ใช้ฟังก์ชัน %s ไม่ได้ (อ่านไฟล์/ออกเน็ตจากฐานข้อมูล)" % m.group(1))
    return s


def bind(sql: str, d_from="", d_to=""):
    """แปลง `:from` / `:to` เป็นพารามิเตอร์จริง — คืน `(sql, params)`

    **ผูกเป็นพารามิเตอร์ ไม่ใช่ต่อสตริง** → ใส่ค่าอะไรมาก็ไม่กลายเป็นคำสั่ง

    `:to` = **วันถัดจากวันที่เลือก** แล้วให้เขียนเงื่อนไขเป็น `< :to` —
    ทำแบบนี้ช่องที่เป็น "วันที่+เวลา" จะได้ครบทั้งวันสุดท้ายโดยไม่ต้อง cast
    (เขียน `<= :to` กับคอลัมน์ timestamp จะตกของวันสุดท้ายไปทั้งวัน ซึ่งคนมักไม่ทันสังเกต)
    """
    from datetime import date, timedelta
    need = {m.group(1).lower() for m in _PARAM.finditer(sql)}
    if not need:
        return sql, []

    def _d(v, label):
        try:
            return date.fromisoformat((v or "").strip())
        except ValueError:
            raise QueryError("ช่วงวันที่ (%s) ไม่ถูกต้อง" % label)

    vals = {}
    if "from" in need:
        vals["from"] = _d(d_from, "จาก").isoformat()
    if "to" in need:
        vals["to"] = (_d(d_to, "ถึง") + timedelta(days=1)).isoformat()

    params = []

    def rep(m):
        params.append(vals[m.group(1).lower()])
        return "%s"

    return _PARAM.sub(rep, sql), params


def _cursor(conn):
    """เปิด cursor ที่ **เขียนอะไรไม่ได้** + มีเวลาจำกัด

    **ตั้งไม่สำเร็จ = ไม่รันคำสั่งเลย (fail-closed)** — ถ้าปล่อยผ่านไปทั้งที่ยังเขียนได้
    เท่ากับเหลือด่านแค่การกรองคำ ซึ่งเป็นด่านที่พลาดได้ง่ายที่สุด
    """
    cur = conn.cursor()
    if conn.vendor == "postgresql":
        try:
            # ชั้นที่เชื่อได้จริง — ฝั่งฐานข้อมูลปฏิเสธการเขียนเอง
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL statement_timeout = %s", [TIMEOUT_MS])
        except Exception as e:
            cur.close()
            raise QueryError("ตั้งโหมดอ่านอย่างเดียวไม่สำเร็จ จึงไม่รันคำสั่งนี้ (%s)"
                             % str(e).splitlines()[0][:120])
    return cur


def _clean(val, emp, field=""):
    """1 ค่า → ข้อความที่ส่งขึ้นจอได้ (ปิด id พนักงาน · เวลาโซนไทย)"""
    import datetime as _dt
    import json as _json
    if field.lower() in HIDE_FIELDS:
        return "(ไม่แสดง)"
    if val is None:
        return None
    if isinstance(val, bool):
        return "ใช่" if val else "ไม่"
    if isinstance(val, (int, float)):
        return val
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
        val = _json.dumps(val, ensure_ascii=False, default=str)
    s = str(val)
    if "U" in s:
        from .db_export import _scrub
        s = _scrub(s, emp)
    return s


def run(sql: str, d_from="", d_to="", limit=ROWS_SCREEN) -> dict:
    """รัน query → `{columns, rows, rowCount, truncated, ms}` (ทั้งหมด rollback ทิ้ง)"""
    from django.db import connection, transaction

    s = check(sql)
    q, params = bind(s, d_from, d_to)
    try:
        limit = max(1, min(int(limit or ROWS_SCREEN), ROWS_SCREEN_MAX))
    except (TypeError, ValueError):
        limit = ROWS_SCREEN

    emp = _emp_ids()
    t0 = time.time()
    # atomic + rollback เสมอ → ไม่มีทางมีอะไรค้างให้ commit แม้ query จะแอบเขียนได้
    try:
        with transaction.atomic():
            cur = _cursor(connection)
            try:
                cur.execute(q, params)
                cols = [c[0] for c in (cur.description or [])]
                raw = cur.fetchmany(limit + 1)
            finally:
                cur.close()
            transaction.set_rollback(True)
    except QueryError:
        raise
    except Exception as e:
        raise QueryError(_friendly(e))

    more = len(raw) > limit
    rows = [[_clean(v, emp, cols[i] if i < len(cols) else "") for i, v in enumerate(r)]
            for r in raw[:limit]]
    for r in rows:                       # ตัดข้อความยาวก่อนส่งขึ้นจอ (ไฟล์ export ไม่ตัด)
        for i, v in enumerate(r):
            if isinstance(v, str) and len(v) > CELL_MAX:
                r[i] = v[:CELL_MAX] + "…"
    return {"ok": True, "columns": cols, "rows": rows, "rowCount": len(rows),
            "truncated": more, "limit": limit,
            "ms": int((time.time() - t0) * 1000)}


def _friendly(e) -> str:
    """ข้อความ error ของ Postgres → บอกให้คนอ่านรู้เรื่อง"""
    msg = str(e).strip().split("\n")[0]
    low = msg.lower()
    if "read-only" in low or "read only" in low:
        return "หน้านี้อ่านข้อมูลได้อย่างเดียว เขียน/แก้/ลบไม่ได้"
    if "statement timeout" in low or "canceling statement" in low:
        return "query ใช้เวลานานเกิน %d วินาที — ลองใส่เงื่อนไขให้แคบลง" % (TIMEOUT_MS // 1000)
    if "does not exist" in low:
        return msg + "  (กดชื่อตารางทางซ้ายเพื่อใส่ชื่อให้ถูก)"
    return msg


def export_rows(sql: str, d_from="", d_to=""):
    """generator ของแถวสำหรับเขียน CSV — `(columns, iterator)`

    ดึงทีละก้อน (`fetchmany`) ไม่ใช่ `fetchall` — ผลลัพธ์แสนแถวไม่ควรกองอยู่ในแรมทั้งก้อน
    """
    from django.db import connection, transaction

    s = check(sql)
    q, params = bind(s, d_from, d_to)
    emp = _emp_ids()

    with transaction.atomic():
        cur = _cursor(connection)
        try:
            try:
                cur.execute(q, params)
            except Exception as e:
                raise QueryError(_friendly(e))
            cols = [c[0] for c in (cur.description or [])]
            out, n = [], 0
            while True:
                batch = cur.fetchmany(1000)
                if not batch:
                    break
                for r in batch:
                    out.append([_clean(v, emp, cols[i] if i < len(cols) else "")
                                for i, v in enumerate(r)])
                    n += 1
                    if n >= ROWS_EXPORT_MAX:
                        break
                if n >= ROWS_EXPORT_MAX:
                    break
        finally:
            cur.close()
        transaction.set_rollback(True)
    return cols, out


# ─────────────────────────── รายชื่อตาราง/คอลัมน์ (แถบซ้าย) ───────────────────────────

_DATE_TYPES = ("date", "datetime", "timestamp")


def schema() -> dict:
    """ตาราง + คอลัมน์ทั้งหมด — ให้หน้าเว็บทำแถบซ้ายแบบ DbVisualizer

    แนบ **ชื่อไทย** จาก `db_inventory.TABLES` (ถ้ามี) และ **ช่องวันที่ของตารางนั้น**
    เพื่อเอาไปสร้างคำสั่งกรองช่วงวันที่ให้อัตโนมัติตอนกดชื่อตาราง
    """
    from django.db import connection
    from .db_inventory import TABLES

    out = []
    with connection.cursor() as cur:
        names = sorted(connection.introspection.table_names(cur))
        for t in names:
            try:
                desc = connection.introspection.get_table_description(cur, t)
            except Exception:
                continue
            cols, dates = [], []
            for c in desc:
                typ = ""
                try:
                    typ = (connection.introspection.get_field_type(c.type_code, c) or "")
                except Exception:
                    typ = ""
                typ = typ.replace("Field", "").lower()
                cols.append({"name": c.name, "type": typ})
                if any(k in typ for k in _DATE_TYPES):
                    dates.append(c.name)
            meta = TABLES.get(t) or {}
            out.append({"table": t, "label": meta.get("name", ""), "pii": bool(meta.get("pii")),
                        "columns": cols, "dateColumns": dates})
    return {"ok": True, "tables": out, "vendor": connection.vendor}


def starter_sql(table: str, date_col="") -> str:
    """คำสั่งตั้งต้นตอนกดชื่อตาราง — มีกรองช่วงวันที่ให้ถ้าตารางนั้นมีช่องวันที่"""
    t = re.sub(r"[^A-Za-z0-9_.]", "", table or "")
    if not t:
        return ""
    if date_col:
        c = re.sub(r"[^A-Za-z0-9_]", "", date_col)
        return ('SELECT *\nFROM %s\nWHERE %s >= :from AND %s < :to\nORDER BY %s DESC'
                % (t, c, c, c))
    return "SELECT *\nFROM %s" % t
