# -*- coding: utf-8 -*-
"""จับคู่ "ลูกค้าที่รอรถ" กับรถที่มีในสต็อกตอนนี้ — ก.ย.69

*"ถ้าเพราะราคาไม่ถึงก็เก็บไว้รอรถที่ราคาพอดีตามงบ"*

**โมดูลนี้ไม่ส่งอะไรหาลูกค้าเด็ดขาด** — คืนผลให้ *คนของเรา* ดูแล้วตัดสินใจเองว่าจะทักไหม
(เจ้าของสั่ง "อย่าเพิ่งส่งข้อความอะไรหาลูกค้า") · และต่อให้เปิดส่งแล้ว การทักลูกค้าเก่า
ที่เคยปฏิเสธไปควรผ่านสายตาคนก่อนเสมอ — ทักผิดคนคือไปตามคนที่ซื้อรถไปแล้ว

**รถที่นับว่า "เสนอได้"** = สเตป `show` (รถพร้อมขาย) เท่านั้น · ยังไม่ขึ้นโชว์ =
ยังไม่ผ่าน QC/ยังทำสภาพอยู่ เอาไปเสนอแล้วลูกค้ามาดูไม่ได้จริง
"""
from __future__ import annotations

import re

from django.utils import timezone

from .models import CustomerNeed

SELLABLE_STAGES = ["show"]          # รถพร้อมขาย (ดู cars/constants.py)
PRICE_GRACE = 1.05                  # เกินงบได้ 5% — ลูกค้าส่วนใหญ่ต่อรองได้นิดหน่อย


def _norm(s: str) -> str:
    """ตัดให้เหลือแก่นของชื่อรุ่น — ชื่อในสต็อกมีส่วนหางแบบ "Almera ปี 11-16" ปนอยู่"""
    s = (s or "").lower()
    s = re.sub(r"ปี\s*[\d\-/]+", " ", s)          # "ปี 11-16" ไม่ใช่ชื่อรุ่น
    s = re.sub(r"[^0-9a-zก-๙]+", " ", s)
    return " ".join(s.split())


def _stock():
    """รถที่เสนอได้ตอนนี้ + ราคา — คืน list ของ dict (ไม่ผูกกับ ORM ของ cars เกินจำเป็น)"""
    from cars.models import Car
    out = []
    qs = Car.objects.filter(status="active", stage__in=SELLABLE_STAGES, deleted_at__isnull=True)
    for c in qs.only("code", "brand", "model", "year", "plate", "extra"):
        ex = c.extra or {}
        try:
            price = int(ex.get("price_num") or 0)
        except (TypeError, ValueError):
            price = 0
        out.append({
            "code": c.code, "brand": c.brand or "", "model": c.model or "",
            "year": c.year, "plate": c.plate or "", "price": price,
            "key": _norm("%s %s" % (c.brand, c.model)),
        })
    return out


def matches_for(need: CustomerNeed, stock=None) -> list:
    """รถในสต็อกที่ตรงกับความต้องการนี้ (ตรงรุ่น + เข้างบ + ปีตรง)"""
    want = _norm(need.car_model or need.car_text)
    if not want:
        return []                                  # ไม่รู้ว่าหารุ่นไหน = จับคู่ไม่ได้
    words = [w for w in want.split() if len(w) >= 3]
    if not words:
        return []

    cap = int((need.budget_max or 0) * PRICE_GRACE) if need.budget_max else 0
    hits = []
    for c in (stock if stock is not None else _stock()):
        # ตรงรุ่น: คำใดคำหนึ่งของสิ่งที่ลูกค้าหา ต้องอยู่ในชื่อรถ
        if not any(w in c["key"] for w in words):
            continue
        # เข้างบ — รถที่ยังไม่ได้ใส่ราคา (0) ไม่ตัดทิ้ง แต่ติดป้ายว่าไม่รู้ราคา
        if cap and c["price"] and c["price"] > cap:
            continue
        if need.car_year_min and c["year"] and c["year"] < need.car_year_min:
            continue
        if need.car_year_max and c["year"] and c["year"] > need.car_year_max:
            continue
        hits.append(dict(c, noPrice=not c["price"]))
    hits.sort(key=lambda x: (x["noPrice"], x["price"]))
    return hits


def scan(mark: bool = True) -> list:
    """ไล่ทุกคนที่ "รอรถ" อยู่ → คืนรายการที่เจอรถตรงสเปก

    `mark=True` จดเวลาที่เจอไว้ใน `matched_at` — ไว้ดูว่าเคสนี้มีของให้เสนอตั้งแต่เมื่อไหร่
    แล้วยังไม่มีใครไปทักสักที
    """
    stock = _stock()
    out = []
    qs = (CustomerNeed.objects
          .filter(waiting=True)
          .exclude(status=CustomerNeed.WON)
          .select_related("profile")
          .order_by("-updated_at"))
    for need in qs:
        hits = matches_for(need, stock)
        if not hits:
            continue
        if mark and not need.matched_at:
            CustomerNeed.objects.filter(pk=need.pk).update(matched_at=timezone.now())
        out.append({
            "need": need,
            "customer": need.profile.show_name,
            "user_id": need.profile.user_id,
            "want": need.car_model or need.car_text,
            "budget": need.budget_max,
            "why": need.get_reject_kind_display() if need.reject_kind else "",
            "cars": hits[:5],
        })
    return out
