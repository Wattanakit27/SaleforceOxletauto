"""ตามงานจัดซื้อ (รับซื้อรถ) — หาเคสที่ยังไม่ตัดสิน แล้วสร้างข้อความเตือนรายคน

ออกแบบให้ "ง่ายสำหรับผู้ใช้สูงวัย" ตามที่เจ้าของสั่ง:
  - ไม่ต้องเปิดเว็บ ไม่ต้องกดปุ่ม ไม่ต้องกรอกช่องใหม่
  - ระบบดูจากช่องที่ทีมกรอกอยู่แล้ว ("รับซื้อ/ไม่รับซื้อ") → กรอกแล้วชื่อหายจากรายการเอง
  - วันละครั้ง สูงสุด 5 คัน · ไม่มีงานค้าง = ไม่ส่ง

ที่มาข้อมูล: ชีตจัดซื้อ (PURCHASE_SID) แท็บ "ขายรถจบออนไลน์ <เดือน>69"
  A วันที่ · C Code · D รุ่นรถ · F เบอร์ติดต่อ · G ชื่อผู้ขาย
  K รับซื้อ/ไม่รับซื้อ (ว่าง = ยังไม่ตัดสิน = งานค้าง) · M จัดซื้อ (เจ้าของเคส) · Q คอมเมนท์จัดซื้อ

⚠️ ช่อง "Follow วันถัดไป" (T/U) มีในชีตแต่กรอกจริงแค่ ~8% → ไม่เอามาใช้ตัดสินใจ
   ใช้ "คอมเมนท์จัดซื้อ" (กรอก 91%) เป็นตัวบอกว่าคุยแล้วหรือยังแทน
"""
import urllib.parse

import requests

# ระยะเวลาย้อนหลังที่ยังตามงาน (เจ้าของเคาะ 18 วัน)
LOOKBACK_DAYS = 18
# สูงสุดกี่คันต่อคนต่อรอบ (เห็น 20 รายการแล้วท้อ ไม่ทำสักอัน)
MAX_CARS = 5

_COL = {"date": 0, "code": 2, "car": 3, "phone": 5, "name": 6,
        "decision": 10, "owner": 12, "comment": 16}


def _months_to_read(now):
    """อ่านย้อน 2 เดือน (ครอบหน้าต่าง 18 วันที่คร่อมเดือนได้)"""
    from .constants import MONTHS_FULL
    out, y2 = [], (now.year + 543) % 100
    for m in (now.month, now.month - 1):
        if 1 <= m <= 12:
            out.append("ขายรถจบออนไลน์ %s%02d" % (MONTHS_FULL[m - 1], y2))
    return out


def _from_db(days):
    """อ่านจากตาราง `dash_purchase_case` — ★ 17 ก.ย.69 (ย้ายจากชีตมา Postgres)

    คืน `None` = **ยังไม่มีข้อมูลในตารางเลย** (n8n ยังไม่ได้สลับมาเขียน) → ให้ผู้เรียก
    ตกไปอ่านชีตแบบเดิม · คืน `[]` = มีข้อมูลแล้วแต่ไม่มีงานค้าง (ต่างกัน — อย่ารวมเป็นค่าเดียว)
    """
    from django.utils import timezone
    from ..models import PurchaseCase

    try:
        if not PurchaseCase.objects.exists():
            return None
        today = timezone.localdate()
        since = today - __import__("datetime").timedelta(days=days)
        rows = (PurchaseCase.objects
                .filter(decision="", received_at__date__gte=since)
                .only("purchaser", "seller_name", "car_model", "phone", "code",
                      "received_at", "comment"))
        out = []
        for r in rows:
            age = (today - timezone.localtime(r.received_at).date()).days
            if not (0 <= age <= days):
                continue
            out.append({
                "owner": r.purchaser or "(ไม่ระบุ)",
                "name": r.seller_name, "car": r.car_model, "phone": r.phone,
                "code": r.code, "age": age, "talked": bool(r.comment),
            })
        return out
    except Exception:
        return None          # ยังไม่ migrate / DB ล่ม → ใช้ชีตต่อ ไม่ทำให้การเตือนหยุด


def fetch_open_cases(days=LOOKBACK_DAYS):
    """เคสที่ "ยังไม่ตัดสินรับซื้อ" และอายุไม่เกิน N วัน — best-effort (พัง = ลิสต์ว่าง)

    อ่าน **Postgres ก่อน** (ตาราง `dash_purchase_case` ที่ n8n เขียนเข้ามา) ·
    ตารางยังว่าง = ตกไปอ่านชีตแบบเดิม → สลับ n8n มาเขียน DB ได้โดยไม่ต้องแก้โค้ดตรงนี้อีก
    """
    if source() == "db":
        db = _from_db(days)
        if db is not None:
            return db
    return _from_sheet(days)


# ที่อ่านข้อมูล: "sheet" (เดิม) หรือ "db" (Postgres) — เก็บใน KVStore
SRC_KEY = "purchase_source"


def source():
    """อ่านจากไหน — **ค่าเริ่มต้นยังเป็นชีต** (ต้องสั่งสลับเอง)

    ⚠️ **ห้ามสลับอัตโนมัติตอนเห็นว่าตารางมีข้อมูล** — ช่อง "รับซื้อ/ไม่รับซื้อ" คือ
    ตัวปิดงาน และตอนนี้ทีม **ยังกรอกในชีต** · ถ้าสลับมาอ่าน DB ตอนที่ยังไม่มีที่ให้กรอก
    → `decision` ใน DB จะว่างตลอดกาล = **ทุกคนโดนทวงคันเดิมทุกวันไม่มีวันจบ**
    สลับได้ก็ต่อเมื่อมีที่กรอกผลในระบบแล้วเท่านั้น
    """
    try:
        from . import cache_store
        v = (cache_store.get_kv(SRC_KEY) or {}).get("data") or {}
        return "db" if str(v.get("source", "")).lower() == "db" else "sheet"
    except Exception:
        return "sheet"


def _from_sheet(days=LOOKBACK_DAYS):
    """ทางเดิม — อ่านชีตจัดซื้อ (เก็บไว้เป็นทางสำรองช่วงเปลี่ยนผ่าน)"""
    from .fetch_dashboard import PURCHASE_SID, bangkok_now, parse_date
    from .google_sheets import _get_credentials, SHEETS_API
    from google.auth.transport.requests import Request as AuthRequest

    now = bangkok_now()
    today = now.date()
    cases = []
    try:
        creds = _get_credentials()
        creds.refresh(AuthRequest())
        headers = {"Authorization": "Bearer %s" % creds.token}
        for tab in _months_to_read(now):
            rng = urllib.parse.quote("'%s'!A3:W400" % tab)
            url = "%s/%s/values/%s?valueRenderOption=FORMATTED_VALUE" % (SHEETS_API, PURCHASE_SID, rng)
            r = requests.get(url, headers=headers, timeout=30)
            if r.status_code != 200:
                continue
            for row in r.json().get("values", []):
                def g(key, _row=row):
                    i = _COL[key]
                    return (str(_row[i]).strip() if i < len(_row) and _row[i] else "")
                if not (g("code") or g("name")):
                    continue          # แถวว่าง
                if g("decision"):
                    continue          # ตัดสินแล้ว = ไม่ต้องตาม (ช่องที่ทีมกรอกอยู่แล้ว)
                d = parse_date(g("date"))
                if not d:
                    continue
                age = (today - (d.date() if hasattr(d, "date") else d)).days
                if not (0 <= age <= days):
                    continue
                cases.append({
                    "owner": g("owner") or "(ไม่ระบุ)",
                    "name": g("name"), "car": g("car"), "phone": g("phone"),
                    "code": g("code"), "age": age, "talked": bool(g("comment")),
                })
    except Exception:
        return []
    return cases


def _rank(cases):
    """ยังไม่ได้คุยมาก่อน → แล้วค่อยดองนานสุด"""
    return sorted(cases, key=lambda c: (0 if not c["talked"] else 1, -c["age"]))


_NUM = "①②③④⑤"      # ①②③④⑤


def build_messages(cases=None, max_cars=MAX_CARS):
    """คืน {"owner": [(ชื่อคน, ข้อความ)], "admin": ข้อความสรุป} — ไม่มีงานค้าง = ค่าว่าง"""
    if cases is None:
        cases = fetch_open_cases()
    by = {}
    for c in cases:
        by.setdefault(c["owner"], []).append(c)

    nl = "\n"
    owner_msgs = []
    for person in sorted(by):
        top = _rank(by[person])[:max_cars]
        if not top:
            continue
        L = ["สวัสดีค่ะ %s" % person, "", "วันนี้ควรโทร %d คันนี้ค่ะ" % len(top), ""]
        for i, c in enumerate(top, 1):
            bullet = _NUM[i - 1] if i <= 5 else ("%d." % i)
            L.append("%s %s" % (bullet, c["name"][:28] or "(ไม่มีชื่อ)"))
            if c["car"]:
                L.append("   %s" % c["car"][:30])
            if c["phone"]:
                L.append("   %s" % c["phone"])
            why = "ยังไม่ได้คุยเลย" if not c["talked"] else "คุยแล้ว แต่ยังไม่ได้ตัดสิน"
            L.append("   ➜ %s · %d วัน" % (why, c["age"]))
            L.append("")
        L.append("─" * 16)
        L.append("คุยจบแล้วกรอกช่อง \"รับซื้อ/ไม่รับซื้อ\" ในชีต")
        L.append("เดี๋ยวชื่อหายจากรายการเองค่ะ")
        owner_msgs.append((person, nl.join(L)))

    admin = ""
    if by:
        A = ["\U0001F4CB สรุปงานจัดซื้อ เช้านี้", ""]
        for person in sorted(by):
            cs = by[person]
            A.append("%-8s ค้าง %3d คัน · ยังไม่ได้คุย %d"
                     % (person, len(cs), sum(1 for c in cs if not c["talked"])))
        unknown = len(by.get("(ไม่ระบุ)", []))
        if unknown:
            A.append("")
            A.append("⚠️ ยังไม่ระบุคนจัดซื้อ %d คัน" % unknown)
        admin = nl.join(A)
    return {"owner": owner_msgs, "admin": admin}
