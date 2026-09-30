# -*- coding: utf-8 -*-
"""หน้าส่วนตัวของทีมจัดซื้อ — "จัดซื้อ force" (30 ก.ย.69 · เจ้าของสั่ง)

*"ช่วยทำ จัดซื้อ force ให้หน่อยคล้ายๆเซลล์"* — เซลล์มีหน้าของตัวเองที่บอกว่า
"วันนี้ต้องตามใครก่อน" · ทีมจัดซื้อยังไม่มี ต้องรอข้อความเข้า LINE อย่างเดียว

**เจ้าของเคาะเนื้อหา 2 อย่าง**: (1) งานที่ต้องทำวันนี้ (2) รถที่ขาดตลาด — ควรหารุ่นไหน
**สิทธิ์**: เห็นเฉพาะเคสของตัวเอง (กติกาเดียวกับเซลล์)

**★ ไม่เขียนตรรกะใหม่เลย** — ใช้ของที่ส่ง LINE อยู่ทุกวันอยู่แล้ว:
`purchase_followup.fetch_open_cases()` (เคสค้างจากชีตจัดซื้อ) ·
`purchase_report.rank_cases()` (ยังไม่โทรมาก่อน → รุ่นขาดตลาด → ดองนาน) ·
`purchase_report.market_gap()` (รุ่นที่ตลาดหาแต่เราไม่มีของ)
→ **ตัวเลขบนหน้าเว็บกับในข้อความ LINE เป็นชุดเดียวกันเสมอ**
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

#  ย้อนหลังกี่วันที่ถือว่า "ยังต้องตาม" — ตรงกับที่ส่งเข้า LINE
from .purchase_followup import LOOKBACK_DAYS   # noqa: E402

#  ชื่อในทะเบียนพนักงานกับในชีตจัดซื้อไม่ตรงกัน (ทะเบียน "ต๊าด" · ชีต "พี่ต๊าด")
#  ★ เขียนมือ ไม่ใช้ substring — 3 คนเขียนได้หมด และผิดแล้วเห็นทันที
#    (บทเรียนเดิม: substring ทำให้ `Mod🐜` ไปจับ `เอ็ม`)
OWNER_ALIAS = {
    "หมี": ["พี่หมี"],
    "พี่หมี": ["พี่หมี"],
    "ต๊าด": ["พี่ต๊าด"],
    "พี่ต๊าด": ["พี่ต๊าด"],
    "มิว": ["มิว"],
}


def _norm(s) -> str:
    return "".join(str(s or "").lower().split())


def owner_keys(nickname: str) -> list:
    """ชื่อเล่นในทะเบียน → ชื่อที่ใช้ในชีตจัดซื้อ (อาจมีหลายแบบ)"""
    n = str(nickname or "").strip()
    return OWNER_ALIAS.get(n) or ([n] if n else [])


def is_purchaser(nickname: str, position: str = "") -> bool:
    """คนนี้เป็นทีมจัดซื้อไหม — ดูตำแหน่งในทะเบียนก่อน แล้วค่อยดูรายชื่อที่จับคู่ไว้"""
    if "จัดซื้อ" in str(position or ""):
        return True
    return bool(OWNER_ALIAS.get(str(nickname or "").strip()))


def my_cases(nickname: str, days: int = LOOKBACK_DAYS) -> tuple[list, list]:
    """เคสค้างของคนนี้ (เรียงว่าควรโทรใครก่อน) + รุ่นที่ขาดตลาด

    คืน `(cases, gap)` · อ่านชีตไม่ได้ = `([], [])` **ไม่ทำให้หน้าเว็บพัง**
    (หน้าเว็บจะขึ้นว่าอ่านข้อมูลไม่ได้ แทนที่จะขาว)
    """
    from . import purchase_followup, purchase_report

    try:
        gap = purchase_report.market_gap()
    except Exception as e:
        log.warning("อ่านรุ่นที่ขาดตลาดไม่ได้: %s", e)
        gap = []
    try:
        cases = purchase_followup.fetch_open_cases(days) or []
    except Exception as e:
        log.warning("อ่านเคสจัดซื้อไม่ได้: %s", e)
        return [], gap

    keys = [_norm(k) for k in owner_keys(nickname)]
    mine = [c for c in cases if _norm(c.get("owner")) in keys] if keys else []
    try:
        mine = purchase_report.rank_cases(mine, gap)
    except Exception as e:
        log.warning("จัดลำดับเคสไม่ได้: %s", e)
    return mine, gap


def summary(nickname: str, days: int = LOOKBACK_DAYS) -> dict:
    """ก้อนเดียวจบสำหรับหน้า `/buy/`

    `cases`   — เคสที่ต้องตาม เรียงแล้ว (ยังไม่โทรมาก่อน)
    `notCalled`/`stale` — ตัวเลขสรุปไว้โชว์เป็น KPI
    `gap`     — รุ่นที่ขาดตลาด (เหมือนที่ส่งเข้า LINE)
    """
    from . import purchase_report

    cases, gap = my_cases(nickname, days)
    not_called = [c for c in cases if not c.get("talked")]
    #  "ดองนาน" = ครึ่งทางของหน้าต่างที่เรายังตามอยู่ — เลยครึ่งแล้วยังไม่จบ ถือว่าเย็น
    stale_days = max(3, days // 2)
    stale = [c for c in cases if c.get("age", 0) >= stale_days]
    return {
        "owner": nickname,
        "days": days,
        "staleDays": stale_days,
        "cases": cases,
        "total": len(cases),
        "notCalled": len(not_called),
        "stale": len(stale),
        "gap": gap,
        "topGap": purchase_report.TOP_GAP,
        "demandMonths": purchase_report.DEMAND_MONTHS,
        #  ★ `STOCK_INFO` ถูกเติมเป็นผลพลอยได้ของ `market_gap()` — อ่าน "หลัง" my_cases เท่านั้น
        #    "พร้อมขายอีก N คันเป็นรุ่นที่ตลาดไม่ได้ถามหา" — ไม่เขียนกำกับ คนอ่านจะบวกเลขในตารางแล้วไม่ตรงสต๊อก
        "stockInfo": dict(purchase_report.STOCK_INFO or {}),
    }
