# -*- coding: utf-8 -*-
"""**สมุดเบอร์ลูกค้า** — เบอร์นี้เคยเป็นลีดเลขไหน ของเซลล์คนไหน (10 ต.ค.69)

เจ้าของเลือกจากตัวอย่างหน้าจอ "ศูนย์ควบคุมลีด": *เช็คเบอร์ซ้ำตอนจ่ายเบอร์* + *เซลล์เช็คเบอร์ซ้ำได้เอง*

ปัญหาที่แก้: ลูกค้าคนเดียวทักไลน์ → กรอกฟอร์มเว็บ → ทักจากไลฟ์ กลายเป็น 3 เลขลีด ไปตก 3 เซลล์
(ตัวอย่างในหน้าจอเดิม: คุณเอก RTLD9-…/1 ถูกโทรจากเซลล์ 3 คน รู้สึกว่าเต็นท์ไม่เป็นระบบ)
**ตัวจับคู่ที่เชื่อได้มีแค่เบอร์โทร** — LINE userId กับ Facebook PSID เป็นคนละระบบ จับคู่กันเองไม่ได้

แหล่งข้อมูล 3 ทาง (ตาราง `LeadPhone`):
  - **ชีตลีด** — ประวัติทั้งปี · สร้างใหม่ทั้งชุดทุก 6 ชม. (`rebuild_from_sheet` · cron ใน thread)
  - **ใบจ่ายลีดในห้องจ่ายเบอร์** — ใบที่แอดมินโพสต์เอง/ระบบโพสต์ · จดตอนข้อความเข้า (`leadflow`)
  - **ปุ่มจ่ายเบอร์ในระบบ** — จดทันทีตอนกด ไม่ต้องรอชีต

เก็บแค่ เบอร์ + เลขลีด + เซลล์ + วันที่ (ไม่เก็บชื่อลูกค้า) — เท่าที่ต้องใช้ตอบว่า "ซ้ำไหม ของใคร"
เซลล์ถามได้แค่ "เบอร์เต็ม" (ไม่รับ 4 ตัวท้าย) และได้คำตอบแค่ ชื่อเซลล์ + เดือน — ไม่เห็นข้อมูลลูกค้าคนอื่น
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from django.utils import timezone

from .models import LeadPhone

_PHONE_RE = re.compile(r"(?:\+?66[\s-]?|0)\d[\d\s-]{6,12}\d")
REBUILD_HOURS = 6
KV_LAST = "phonebook_last"


def norm(s) -> str:
    """เบอร์ → ตัวเลข 9–10 หลักขึ้นต้น 0 · ไม่ใช่เบอร์ไทย = ''"""
    d = re.sub(r"\D", "", str(s or ""))
    if d.startswith("66") and len(d) in (10, 11):
        d = "0" + d[2:]
    if len(d) == 9 and d[0] in "689":                 # มือถือที่พิมพ์ขาด 0 ตัวหน้า
        d = "0" + d
    if len(d) == 10 and d[:2] in ("06", "08", "09"):
        return d
    if len(d) == 9 and d[0] == "0" and d[1] in "234567":
        return d                                      # เบอร์บ้าน
    return ""


def phones_in(text) -> list:
    """ทุกเบอร์ในข้อความ (ช่องเบอร์ในชีตบางแถวมี 2 เบอร์: "081-… / 089-…")"""
    out = []
    for m in _PHONE_RE.finditer(str(text or "")):
        p = norm(m.group(0))
        if p and p not in out:
            out.append(p)
    if not out:
        p = norm(text)
        if p:
            out.append(p)
    return out[:3]


def pretty(p: str) -> str:
    p = norm(p)
    if len(p) == 10:
        return "%s-%s-%s" % (p[:3], p[3:6], p[6:])
    return p


def _nick(seller: str) -> str:
    """ชื่อเซลล์ในชีต/แท็ก → ชื่อเล่นที่ใช้ในระบบ (ADMIN = เทเลเซลล์ คงคีย์เดิม)"""
    s = (seller or "").strip()
    if not s:
        return ""
    try:
        from dashboard.services.constants import normalize_seller
        return normalize_seller(s) or s
    except Exception:
        return s


def note(phone, code: str = "", seller: str = "", source: str = LeadPhone.SYSTEM,
         seen_on=None, channel: str = "", car: str = "") -> int:
    """จด 1 ลีด (ทุกเบอร์ในช่อง) — เรียกตอนจ่ายเบอร์ในระบบ / ใบจ่ายลีดเข้ากลุ่ม · ไม่โยน exception"""
    n = 0
    for p in phones_in(phone):
        try:
            LeadPhone.objects.update_or_create(
                phone=p, code=(code or "")[:32], source=source,
                defaults={"seller": _nick(seller)[:80], "channel": (channel or "")[:80],
                          "car": (car or "")[:120], "seen_on": seen_on or timezone.localdate()})
            n += 1
        except Exception:
            pass
    return n


def _sheet_date(s):
    try:
        from dashboard.services.fetch_dashboard import parse_date
        d = parse_date(s)
        return d.date() if hasattr(d, "date") else d
    except Exception:
        return None


def rebuild_from_sheet(rows=None) -> dict:
    """สร้างแถวที่มาจากชีตลีดใหม่ทั้งชุด (ลบของชีตเดิม แล้วใส่ใหม่ในธุรกรรมเดียว — รันซ้ำไม่เบิ้ล)"""
    from django.db import transaction
    if rows is None:
        from dashboard.services.google_sheets import fetch_leads_by_month_tabs
        rows = fetch_leads_by_month_tabs()
    from dashboard.services.google_sheets import LEADS_COL as L

    def cell(r, i):
        return (r[i] if i < len(r) else "") or ""

    seen, objs = set(), []
    for r in rows or []:
        code = cell(r, L.lead_code).strip().upper()[:32]
        for p in phones_in(cell(r, L.phone)):
            key = (p, code)
            if key in seen:
                continue
            seen.add(key)
            objs.append(LeadPhone(phone=p, code=code, seller=_nick(cell(r, L.sales_rep))[:80],
                                  channel=cell(r, L.channel)[:80], car=cell(r, L.car_formula)[:120],
                                  seen_on=_sheet_date(cell(r, L.received_date)), source=LeadPhone.SHEET))
    with transaction.atomic():
        LeadPhone.objects.filter(source=LeadPhone.SHEET).delete()
        LeadPhone.objects.bulk_create(objs, batch_size=2000, ignore_conflicts=True)
    out = {"at": timezone.localtime().isoformat(timespec="seconds"), "rows": len(rows or []), "phones": len(objs)}
    try:
        from dashboard.services import cache_store
        cache_store.set_kv(KV_LAST, out)
    except Exception:
        pass
    return out


def due_rebuild() -> bool:
    """ถึงรอบสร้างจากชีตใหม่หรือยัง (ทุก REBUILD_HOURS ชม. · ข้าม worker ด้วย KV)"""
    try:
        from dashboard.services import cache_store
        last = ((cache_store.get_kv(KV_LAST) or {}).get("data") or {}).get("at") or ""
        if not last:
            return True
        from datetime import datetime
        return (timezone.now() - datetime.fromisoformat(last)).total_seconds() >= REBUILD_HOURS * 3600
    except Exception:
        return False


def lookup(phone, exclude_code: str = "", days: int = 400) -> list:
    """ลีดเดิมของเบอร์นี้ → `[{code, seller, date, channel, car, source}]` ใหม่สุดก่อน · รวมแถวเลขเดียวกัน

    ชีตชนะเรื่อง "เซลล์" (แอดมินแก้ในชีตเมื่อจ่ายใหม่) · ใบในกลุ่ม/ปุ่มในระบบเติมเลขที่ชีตยังไม่มี
    """
    ps = phones_in(phone)
    if not ps:
        return []
    cut = timezone.localdate() - timedelta(days=days)
    rows = (LeadPhone.objects.filter(phone__in=ps)
            .exclude(seen_on__lt=cut).order_by("-seen_on", "-updated_at")[:50])
    rank = {LeadPhone.SHEET: 0, LeadPhone.SYSTEM: 1, LeadPhone.SLIP: 2}
    by = {}
    ex = (exclude_code or "").strip().upper()
    for r in rows:
        k = (r.code or "").upper() or ("?" + str(r.seen_on))
        if ex and k == ex:
            continue
        cur = by.get(k)
        if cur is None or rank[r.source] < rank[cur["_rank"]] or (not cur["seller"] and r.seller):
            by[k] = {"code": r.code, "seller": r.seller, "date": r.seen_on.isoformat() if r.seen_on else "",
                     "channel": r.channel, "car": r.car, "source": r.source, "_rank": r.source}
    out = sorted(by.values(), key=lambda x: x["date"], reverse=True)
    for x in out:
        x.pop("_rank", None)
    return out[:8]


def owner_of(phone, exclude_code: str = "") -> dict | None:
    """เจ้าของล่าสุดของเบอร์นี้ (ลีดใหม่สุดที่มีชื่อเซลล์) — None = ไม่เคยเป็นลีด"""
    for x in lookup(phone, exclude_code):
        if x["seller"]:
            return x
    return None


def check_for_seller(phone, me: str) -> dict:
    """เซลล์เช็คเบอร์ซ้ำเอง → `{ok, found, mine, seller, month}` — ไม่ส่งเลขลีด/รถ/ช่องทางของคนอื่นออก"""
    p = norm(phone)
    if not p:
        return {"ok": False, "error": "พิมพ์เบอร์เต็ม 9–10 หลัก (เช่น 081 234 5678)"}
    hit = owner_of(p)
    if not hit:
        return {"ok": True, "found": False}
    me_n = _nick(me)
    mine = bool(me_n) and hit["seller"] == me_n
    month = ""
    try:
        d = date.fromisoformat(hit["date"])
        month = "%s %d" % (["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.",
                            "ต.ค.", "พ.ย.", "ธ.ค."][d.month - 1], (d.year + 543) % 100)
    except Exception:
        pass
    seller = "เทเลเซลล์" if hit["seller"] == "ADMIN" else hit["seller"]
    out = {"ok": True, "found": True, "mine": mine, "seller": seller, "month": month}
    if mine:                                   # ของตัวเอง = บอกเลขลีดได้ (เปิดเคสต่อได้เลย)
        out["code"] = hit["code"]
    return out
