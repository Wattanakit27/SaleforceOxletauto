# -*- coding: utf-8 -*-
"""สำเนา "ชีทจ่ายเบอร์ ปี69" + "รายงานแบน" ลง Postgres ทุก 10 นาที — 13 ต.ค.69

เจ้าของสั่ง *"อย่าลืมเก็บลง postgres ด้วยนะ เก็บไว้เผื่อทำอย่างอื่นต่อ"* (หลังย้ายงานลงชีตจาก n8n มาไว้ที่
`checkout/leadsheet.py`) · เดิมระบบอ่านชีตไปคำนวณแดชบอร์ดอย่างเดียว ไม่มีแถวลีดอยู่ในฐานข้อมูลเลย
→ เขียน SQL ดู/ต่อยอด (สถิติเซลล์ · ตรวจลีดซ้ำ · เอาไปสอน AI) ไม่ได้

- **ชีตยังเป็นต้นฉบับ** — ตารางนี้เป็นสำเนา ห้ามเขียนกลับ · แก้ข้อมูล = แก้ในชีต
- ดึงทุกแท็บรายเดือน ("มกราคม 69" … ) ในคำขอเดียว (`values:batchGet`) · **แทนที่ทั้งแท็บในธุรกรรมเดียว**
  → แถวที่ลบ/ย้าย/แก้ในชีตตามมาครบ ไม่มีแถวผีค้าง · แท็บอ่านไม่ได้ = ไม่แตะของเดิมของแท็บนั้น
- ช่องหลักจับคู่ตามหัวตาราง (`_resolve_lead_colmap` ตัวเดียวกับแดชบอร์ด — แต่ละเดือนคอลัมน์ไม่ตรงกัน)
  · ทุกช่องดิบเก็บใน `raw` {หัวคอลัมน์: ค่า} (คอลัมน์ที่ยังไม่ได้แตกเป็นช่องก็ไม่หาย)
- เรียกจาก `cron_tick` ทุก 10 นาที (เธรดแยก · ล็อกข้าม worker) · `manage.py sheet_mirror --run` = เดี๋ยวนี้
"""
from __future__ import annotations

import logging
import re
import time
import urllib.parse
from datetime import date, datetime, timedelta

import requests
from django.utils import timezone

log = logging.getLogger(__name__)

KV_LAST = "sheet_mirror_last"
EVERY_MIN = 10
_LOCK_KEY = 7_406_065

# canonical (LEADS_COL) → ช่องของ LeadSheetRow
_FIELD = {
    "received_date": "received_date", "phone": "phone", "time": "time", "lead_code": "code",
    "sales_rep": "seller", "live_team": "live_team", "admin": "admin", "channel": "channel", "branch": "branch",
    "type": "lead_type", "ads": "ads", "car_inquiry": "car_inquiry", "car_formula": "car_formula",
    "call_proof": "call_proof", "focus": "focus", "contact_datetime": "contact_at", "update_count": "update_count",
    "last_updated_at": "last_updated_at", "fill_sheet_note": "fill_note", "customer_profile": "profile",
    "occupation": "occupation", "income": "income", "job_tenure": "job_tenure",
    "payment_history": "payment_history", "customer_type": "customer_type",
    "customer_status": "customer_status", "admin_status": "admin_status", "sales_status": "sales_status",
}
_BAN_FIELD = {"banDate": "ban_date", "time": "time", "seller": "seller", "sellerDisplay": "seller_display",
              "banType": "ban_type", "reason": "reason", "bannedBy": "banned_by", "unbanDate": "unban_date",
              "status": "status", "rawText": "raw_text", "groupId": "group_id"}


def _kv(key) -> dict:
    from .cache_store import get_kv
    try:
        raw = get_kv(key) or {}
        d = raw.get("data", raw) if isinstance(raw, dict) else {}
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _set_kv(key, val):
    from .cache_store import set_kv
    try:
        set_kv(key, val)
    except Exception:
        pass


# ── แปลงค่า ─────────────────────────────────────────────────────────
_DMY = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{2,4})(?:\s+(\d{1,2})[:.](\d{2})(?::\d{2})?)?\s*$")
_DM = re.compile(r"^\s*(\d{1,2})/(\d{1,2})(?:\s+(\d{1,2})[:.](\d{2}))?\s*$")


def _dm_year(d: int, m: int, base) -> date | None:
    """"15/1" (เซลล์วันที่ที่ตั้งรูปแบบโชว์แค่ วัน/เดือน) → ปีของแท็บ · ก่อนเดือนของแท็บเกิน 1 เดือน = ปีถัดไป
    (แท็บ ธ.ค. มี "3/1" = มกราคมปีหน้า)"""
    if base is None:
        return None
    try:
        x = date(base.year, m, d)
    except ValueError:
        return None
    if x < base - timedelta(days=31):
        try:
            x = date(base.year + 1, m, d)
        except ValueError:
            return None
    return x


def _year(y: int) -> int:
    if y < 100:
        return (2500 + y - 543) if y >= 60 else 2000 + y          # "69" = พ.ศ. 2569 · "26" = ค.ศ. 2026
    return y - 543 if y > 2400 else y


def parse_date(s, base=None):
    """"13/10/26" · "13/10/2026" · "13/10/69" · เลข serial ของ Sheets (46307) → date · อ่านไม่ออก = None
    `base` = เดือนของแท็บ — ใช้เติมปีให้ "15/1" ที่ไม่มีปี"""
    s = str(s or "").strip()
    m = _DM.match(s)
    if m:
        return _dm_year(int(m.group(1)), int(m.group(2)), base)
    if re.fullmatch(r"\d{5}(?:\.\d+)?", s):
        try:
            return date(1899, 12, 30) + timedelta(days=int(float(s)))
        except (ValueError, OverflowError):
            return None
    m = _DMY.match(s)
    if not m:
        return None
    try:
        return date(_year(int(m.group(3))), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def parse_dt(s, base=None):
    """"13/10/26 15:46" → datetime (โซนไทย) · มีแต่วันที่ = เที่ยงคืน · "15/1 10:30" ใช้ปีของแท็บ · อ่านไม่ออก = None"""
    s = str(s or "").strip()
    dm = _DM.match(s)
    if dm:
        d = _dm_year(int(dm.group(1)), int(dm.group(2)), base)
        return timezone.make_aware(datetime(d.year, d.month, d.day, int(dm.group(3) or 0),
                                            int(dm.group(4) or 0))) if d else None
    m = _DMY.match(s)
    if not m:
        d = parse_date(s)
        return timezone.make_aware(datetime(d.year, d.month, d.day)) if d else None
    try:
        dt = datetime(_year(int(m.group(3))), int(m.group(2)), int(m.group(1)),
                      int(m.group(4) or 0), int(m.group(5) or 0))
    except ValueError:
        return None
    return timezone.make_aware(dt)


def _int(s):
    d = re.sub(r"[^\d]", "", str(s or ""))
    try:
        return int(d) if d and len(d) < 9 else None
    except ValueError:
        return None


def _fit(model, name, v):
    """ตัดข้อความให้พอดีความยาวช่อง (Postgres ไม่ยอมให้เกิน · แถวเดียวยาวเกินไม่ควรทำให้ทั้งแท็บล้ม)"""
    f = model._meta.get_field(name)
    if isinstance(v, str) and getattr(f, "max_length", None):
        return v[:f.max_length]
    return v


def _raw(header: list, row: list) -> dict:
    out = {}
    for i, v in enumerate(row):
        if not str(v).strip():
            continue
        k = re.sub(r"\s+", " ", str(header[i] if i < len(header) else "")).strip() or "คอลัมน์ %d" % (i + 1)
        if k in out:
            n = 2
            while "%s (%d)" % (k, n) in out:
                n += 1
            k = "%s (%d)" % (k, n)
        out[k] = v
    return out


def tab_month(title: str):
    """"ตุลาคม 69" → date(2026, 10, 1) · ไม่ใช่แท็บรายเดือน = None"""
    from .google_sheets import _THAI_MONTHS
    m = re.fullmatch(r"\s*(\S+)\s*(\d{2})\s*", title or "")
    if not m or m.group(1) not in _THAI_MONTHS:
        return None
    return date(2500 + int(m.group(2)) - 543, _THAI_MONTHS.index(m.group(1)) + 1, 1)


def lead_rows(title: str, values: list, now=None) -> list:
    """ค่าทั้งแท็บ → LeadSheetRow (ยังไม่บันทึก) · ข้ามแถวว่าง (ไม่มี Code/ว/ด/ป/เบอร์)"""
    from ..models import LeadSheetRow
    from .google_sheets import LEADS_COL, _resolve_lead_colmap
    now = now or timezone.now()
    if not values:
        return []
    header, body = values[0], values[1:]
    cm = _resolve_lead_colmap(header, body[:20])
    canon = {f: getattr(LEADS_COL, c) for c, f in _FIELD.items() if hasattr(LEADS_COL, c)}
    month = tab_month(title)
    out = []
    for i, r in enumerate(body):
        def val(field):
            src = cm.get(canon[field])
            return str(r[src]).strip() if src is not None and src < len(r) else ""
        if not (val("code") or val("received_date") or val("phone")):
            continue
        kw = {"tab": title, "row_no": i + 2, "tab_month": month, "raw": _raw(header, r), "synced_at": now}
        for field in canon:
            v = val(field)
            if field == "received_date":
                v = parse_date(v, month)
            elif field in ("contact_at", "last_updated_at"):
                v = parse_dt(v, month)
            elif field == "update_count":
                v = _int(v)
            elif field == "code":
                v = re.sub(r"\s+", "", v).upper()
            kw[field] = _fit(LeadSheetRow, field, v)
        out.append(LeadSheetRow(**kw))
    return out


def ban_rows(values: list, now=None) -> list:
    from ..models import BanSheetRow
    now = now or timezone.now()
    if not values:
        return []
    header = [str(h).strip() for h in values[0]]
    idx = {k: header.index(k) for k in _BAN_FIELD if k in header}
    out = []
    for i, r in enumerate(values[1:]):
        if not any(str(v).strip() for v in r):
            continue
        kw = {"row_no": i + 2, "raw": _raw(header, r), "synced_at": now}
        for k, field in _BAN_FIELD.items():
            v = str(r[idx[k]]).strip() if k in idx and idx[k] < len(r) else ""
            kw[field] = _fit(BanSheetRow, field, parse_date(v) if field == "ban_date" else v)
        out.append(BanSheetRow(**kw))
    return out


# ── ดึง + บันทึก ──────────────────────────────────────────────────────
def _auth():
    from google.auth.transport.requests import Request as AuthRequest

    from .google_sheets import _get_credentials
    creds = _get_credentials()
    creds.refresh(AuthRequest())
    return {"Authorization": "Bearer %s" % creds.token}


def _batch_get(base: str, h: dict, ranges: list) -> list:
    r = requests.get(base + "/values:batchGet", params=[("ranges", x) for x in ranges] +
                     [("valueRenderOption", "FORMATTED_VALUE")], headers=h, timeout=120)
    if r.status_code != 200:
        raise RuntimeError("อ่านชีต: HTTP %s %s" % (r.status_code, r.text[:200]))
    return [vr.get("values", []) for vr in r.json().get("valueRanges", [])]


class _Lock:
    def __init__(self):
        self.got = False

    def __enter__(self):
        from django.db import connection
        if connection.vendor != "postgresql":
            self.got = True
            return self
        with connection.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", [_LOCK_KEY])
            self.got = bool(cur.fetchone()[0])
        return self

    def __exit__(self, *a):
        from django.db import connection
        if self.got and connection.vendor == "postgresql":
            try:
                with connection.cursor() as cur:
                    cur.execute("SELECT pg_advisory_unlock(%s)", [_LOCK_KEY])
            except Exception:
                pass
        return False


def run(tabs: list | None = None) -> dict:
    """ดึงชีตจ่ายเบอร์ (แท็บรายเดือนทั้งหมด หรือเฉพาะ `tabs`) + รายงานแบน → แทนที่ในตาราง · คืนสรุป"""
    from django.db import transaction

    from ..models import BanSheetRow, LeadSheetRow
    from .google_sheets import SHEETS_API, SHEET_CONFIG, load_sheet_config_overrides
    t0 = time.time()
    res = {"at": timezone.localtime().isoformat(timespec="seconds"), "ok": False, "tabs": {}, "rows": 0,
           "bans": None, "error": ""}
    with _Lock() as lk:
        if not lk.got:
            return {"skipped": "อีกตัวกำลังทำอยู่"}
        try:
            load_sheet_config_overrides()
            h = _auth()
            base = "%s/%s" % (SHEETS_API, SHEET_CONFIG["leads"]["spreadsheet_id"])
            r = requests.get(base, params={"fields": "sheets.properties.title"}, headers=h, timeout=30)
            if r.status_code != 200:
                raise RuntimeError("อ่านรายชื่อแท็บ: HTTP %s %s" % (r.status_code, r.text[:200]))
            titles = [s["properties"]["title"] for s in r.json().get("sheets", [])]
            want = [t for t in titles if tab_month(t) and (not tabs or t in tabs)]
            now = timezone.now()
            vals = _batch_get(base, h, ["'%s'!A1:AZ" % t for t in want]) if want else []
            for title, v in zip(want, vals):
                rows = lead_rows(title, v, now)
                with transaction.atomic():
                    LeadSheetRow.objects.filter(tab=title).delete()
                    LeadSheetRow.objects.bulk_create(rows, batch_size=1000)
                res["tabs"][title] = len(rows)
                res["rows"] += len(rows)
            if not tabs:
                # แท็บที่หายไปจากชีต (ลบ/เปลี่ยนชื่อ) = ลบสำเนาด้วย ไม่งั้นนับซ้ำกับแท็บชื่อใหม่
                LeadSheetRow.objects.exclude(tab__in=want).delete()
                bcfg = SHEET_CONFIG["ban_report"]
                bbase = "%s/%s" % (SHEETS_API, bcfg["spreadsheet_id"])
                bv = _batch_get(bbase, h, ["'%s'!A1:Z" % bcfg["sheet_name"]])
                brows = ban_rows(bv[0] if bv else [], now)
                with transaction.atomic():
                    BanSheetRow.objects.all().delete()
                    BanSheetRow.objects.bulk_create(brows, batch_size=1000)
                res["bans"] = len(brows)
            res["ok"] = True
        except Exception as e:
            res["error"] = ("%s: %s" % (type(e).__name__, e))[:300]
            log.exception("sheet_mirror")
            try:
                from . import eventlog
                eventlog.log(eventlog.CRON, name="สำเนาชีตจ่ายเบอร์ลง Postgres", ok=False, error=res["error"])
            except Exception:
                pass
        res["ms"] = int((time.time() - t0) * 1000)
        if not tabs:
            _set_kv(KV_LAST, res)
        return res


def due(now=None) -> bool:
    """ถึงรอบหรือยัง (ทุก EVERY_MIN นาที · เช็คจาก KV ร่วมทุก worker)"""
    last = _kv(KV_LAST).get("at")
    if not last:
        return True
    try:
        return (now or timezone.now()) - datetime.fromisoformat(last) >= timedelta(minutes=EVERY_MIN - 1)
    except ValueError:
        return True


_BG = {"busy": False}


def maybe_run_bg() -> bool:
    """เรียกจาก cron_tick ทุกนาที — ถึงรอบ = ทำในเธรดแยก (อ่านชีตทั้งก้อน ~10 วิ ห้ามหน่วง cron)"""
    import threading
    if _BG["busy"] or not due():
        return False
    _BG["busy"] = True

    def work():
        try:
            run()
        except Exception:
            pass
        finally:
            _BG["busy"] = False
            try:
                from django.db import connection
                connection.close()
            except Exception:
                pass
    threading.Thread(target=work, daemon=True).start()
    return True


def status() -> dict:
    from django.db.models import Count, Max

    from ..models import BanSheetRow, LeadSheetRow
    by_tab = list(LeadSheetRow.objects.values("tab", "tab_month").annotate(n=Count("id"), at=Max("synced_at"))
                  .order_by("tab_month"))
    return {"last": _kv(KV_LAST), "tabs": [(r["tab"], r["n"]) for r in by_tab],
            "rows": sum(r["n"] for r in by_tab), "bans": BanSheetRow.objects.count()}
