# -*- coding: utf-8 -*-
"""ตารางอ้างอิงในไฟล์โค้ช — แท็บ "พนักงาน" + "กลุ่มไลน์" (29 ก.ย.69)

**ทำไมแยกไฟล์จาก [coaching.py](coaching.py)** — 2 แท็บนี้เป็น **snapshot ที่เขียนทับได้**
(รันซ้ำ = ทับของเดิมด้วยค่าล่าสุด) ต่างจากแท็บ `บันทึกโค้ช` ที่เป็น **ประวัติ append-only
ห้าม clear/PUT เด็ดขาด** (มีเทสต์กันไว้) · ถ้าเอามารวมไฟล์เดียว วันหนึ่งจะมีคนหยิบ
ตัวเขียนทับไปใช้กับแท็บประวัติ

**ทำไมต้องมี** — เจ้าของเปิดให้คนนอกดึงข้อมูลห้องโค้ชไปสอน AI / วัดซีเนียร์–จูเนียร์
แต่คนดึงเป็นคนทั่วไปที่ใช้ Claude/ChatGPT ช่วยอ่าน **ไม่ได้เขียน curl หรือถือคีย์ API**
→ เอา `/api/v1/employees` + `/api/v1/groups` มาวางเป็นแท็บในชีตเดียวกัน
เขากด Download CSV แล้วอัปเข้า AI ได้เลย · ไม่ต้องแจกคีย์ = คีย์ไม่หลุดไปอยู่ในแชท AI

**★ `_SAFE_TABS` = ด่านกันลบประวัติ** — ไฟล์นี้เป็นที่เดียวในโปรเจกต์ที่ยิง `:clear`
ใส่ชื่อแท็บผิดครั้งเดียวคือประวัติ 1,695 แถวหาย และกู้ไม่ได้ → เช็คก่อนยิงทุกครั้ง
"""
from __future__ import annotations

from .coaching import SHEET_ID, _api, _esc, cfg, is_senior

# แท็บที่ "อนุญาตให้เขียนทับ" ได้เท่านั้น — ชื่ออื่นถือว่าพลาด ไม่ยิงเลย
EMP_TAB = "พนักงาน"
GRP_TAB = "กลุ่มไลน์"
_SAFE_TABS = {EMP_TAB, GRP_TAB}

EMP_COLUMNS = [
    "ชื่อเล่น", "ชื่อที่ตั้งใน LINE", "ตำแหน่ง/ทีม", "บทบาทในห้องโค้ช",
    "ยังทำงานอยู่", "จำนวนบัญชี LINE", "LINE userId",
]
GRP_COLUMNS = [
    "group id", "ชื่อกลุ่ม", "ประเภทงาน", "ระบบเดาประเภทให้",
    "บอทที่อยู่ในกลุ่ม", "ยังใช้งานอยู่", "ได้ยินล่าสุด",
]

# ชื่อประเภทงานเป็นภาษาคน (คีย์ตรงกับ LineGroup.KIND_CHOICES)
KIND_TH = {
    "coaching": "ห้องโค้ชเซลล์", "lead": "จ่ายลีด", "tradein": "ซื้อขายเทิร์นรถ",
    "booking": "จองรถ", "purchase": "จัดซื้อ", "finance": "จัดไฟแนนซ์",
    "transfer": "รับ-ส่งระหว่างสาขา", "checkin": "เช็คชื่อเข้างาน",
    "admin": "แอดมิน/ทีมงาน", "content": "คอนเทนต์/มาร์เก็ตติ้ง",
    "hr": "บุคคล/รับสมัคร", "other": "อื่น ๆ",
}


def _yes(v) -> str:
    return "ใช่" if v else "ไม่"


def employee_rows(seniors=None) -> list[list[str]]:
    """1 แถว = 1 คน · เรียงชื่อเล่น

    `LINE userId` รวมทุกบัญชีในช่องเดียว คั่นช่องว่าง — คนเดียวมีไอดีคนละตัวต่อบอท
    (คนละ provider) จึงมีคอลัมน์ `จำนวนบัญชี LINE` กำกับไว้ให้เห็นว่าอย่าเอาไอดีไปนับคน
    """
    from .models import Employee, LineProfile

    ids: dict[int, list[str]] = {}
    for p in LineProfile.objects.exclude(employee=None).values("employee_id", "user_id"):
        uid = (p["user_id"] or "").strip()
        if uid:
            ids.setdefault(p["employee_id"], []).append(uid)

    out = []
    for e in Employee.objects.all().order_by("nickname"):
        mine = sorted(ids.get(e.id, []))
        out.append([
            _esc(e.nickname), _esc(e.display_name), _esc(e.position),
            "ซีเนียร์" if is_senior(e.nickname, seniors) else "",
            _yes(e.active), str(len(mine)), " ".join(mine),
        ])
    return out


def group_rows() -> list[list[str]]:
    """1 แถว = 1 กลุ่ม · เรียงประเภทงานแล้วชื่อกลุ่ม"""
    from django.utils import timezone

    from .models import LineGroup

    out = []
    for g in LineGroup.objects.all().order_by("kind", "name"):
        seen = timezone.localtime(g.last_seen).strftime("%Y-%m-%d %H:%M") if g.last_seen else ""
        out.append([
            g.group_id, _esc(g.name),
            KIND_TH.get(g.kind, g.kind or ""),
            _yes(g.kind_auto),
            " ".join(str(c) for c in (g.channels or [])),
            _yes(g.active), seen,
        ])
    return out


def _overwrite(tab: str, header: list[str], rows: list[list[str]]) -> int:
    """ล้างแท็บแล้วเขียนใหม่ — **ใช้ได้กับแท็บใน `_SAFE_TABS` เท่านั้น**

    ⚠️ ชื่อแท็บเป็นภาษาไทย **ต้อง `quote()` ก่อนใส่ URL** (ท่าเดียวกับ `coaching._append`)
    """
    if tab not in _SAFE_TABS:
        raise ValueError(
            "ปฏิเสธ: '%s' ไม่ใช่แท็บ snapshot — เขียนทับได้เฉพาะ %s "
            "(แท็บอื่นในไฟล์นี้เป็นประวัติ ห้ามล้าง)" % (tab, " · ".join(sorted(_SAFE_TABS)))
        )
    import urllib.parse

    import requests

    from dashboard.services.google_sheets import ensure_sheet_tab

    ensure_sheet_tab(SHEET_ID, tab)
    base, head = _api()
    head = {**head, "Content-Type": "application/json"}

    r = requests.post("%s/%s/values/%s:clear" % (base, SHEET_ID, urllib.parse.quote(tab)),
                      headers=head, json={}, timeout=60)
    if r.status_code != 200:
        raise Exception("ล้างแท็บ '%s' ไม่ได้: %s %s" % (tab, r.status_code, r.text[:200]))

    q = urllib.parse.quote("%s!A1" % tab)
    r = requests.put("%s/%s/values/%s?valueInputOption=USER_ENTERED" % (base, SHEET_ID, q),
                     headers=head, json={"values": [header] + rows}, timeout=120)
    if r.status_code != 200:
        raise Exception("เขียนแท็บ '%s' ไม่ได้: %s %s" % (tab, r.status_code, r.text[:200]))
    return len(rows)


def push(apply: bool = False, seniors=None) -> dict:
    """เขียน 2 แท็บอ้างอิง · `apply=False` = ดูเฉยๆ ไม่แตะชีต"""
    if seniors is None:
        seniors = cfg().get("seniors") or None
    emp, grp = employee_rows(seniors), group_rows()
    res = {
        "employees": len(emp),
        "groups": len(grp),
        "seniors": [r[0] for r in emp if r[3] == "ซีเนียร์"],
        "noIds": [r[0] for r in emp if r[5] == "0"],
        "applied": False,
    }
    if apply:
        _overwrite(EMP_TAB, EMP_COLUMNS, emp)
        _overwrite(GRP_TAB, GRP_COLUMNS, grp)
        res["applied"] = True
    return res
