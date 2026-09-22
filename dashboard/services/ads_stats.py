# -*- coding: utf-8 -*-
"""ตัวเลขโฆษณา Meta — แตกจาก `actions` JSON + รวมรายวัน + คิดต้นทุน (23 ก.ย.69)

*"อย่าลืมเก็บข้อมูลของ Ads เป็น Daily Day กับภาพรวม เก็บพวกค่าต่างๆ ด้วย พวก cost per chat"*

**ปัญหาเดิม**: `dash_meta_ad_daily` เก็บ `actions` เป็น JSON ดิบก้อนเดียว → อยากรู้แค่
"เดือนนี้ได้แชทกี่ครั้ง ต้นทุนต่อแชทเท่าไหร่" ต้องงัด jsonb ทุกครั้ง คนทั่วไปเขียน SQL เองไม่ได้
→ แตกตัวเลขที่ใช้จริงออกมาเป็นคอลัมน์ (`ACTION_MAP`) แล้วรวมเป็นรายวันไว้ที่ `dash_ads_daily`

**★ กติกาสำคัญ: ต้นทุนต้องคิดจาก "ผลรวมหารผลรวม" เสมอ ห้ามเฉลี่ยค่าเฉลี่ย**
Meta ส่ง `cost_per_action_type` มาให้รายแถวอยู่แล้ว แต่เอามาเฉลี่ยตรงๆ จะได้เลขผิด
· วัดจริง 23 ก.ย.69: เฉลี่ยของ Meta = **฿61.31** · ผลรวมจริง (45,365 ÷ 726) = **฿62.49**
→ เราจึงเก็บแต่ "จำนวน" ลงตาราง แล้วคิดต้นทุนตอนแสดงผลทุกครั้ง (`stats`)
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Sum

# คีย์ของเรา -> action_type ของ Meta (ชื่อพวกนี้มาจากการวัดของจริง ไม่ได้เดา)
ACTION_MAP = {
    "link_clicks": "link_click",
    "video_views": "video_view",
    "engagement": "post_engagement",
    "chats": "onsite_conversion.messaging_conversation_started_7d",
    "chats_replied": "onsite_conversion.messaging_conversation_replied_7d",
    "leads": "lead",
}
METRIC_TH = {
    "spend": "ใช้เงิน (บาท)", "impressions": "แสดงผล", "reach": "เข้าถึง (คน)",
    "clicks": "คลิกทั้งหมด", "link_clicks": "คลิกลิงก์", "video_views": "วิววิดีโอ",
    "engagement": "มีส่วนร่วม", "chats": "เริ่มแชท", "chats_replied": "แชทที่ตอบกลับ",
    "leads": "ลีด",
}
COUNT_FIELDS = ["impressions", "reach", "clicks", "link_clicks", "video_views",
                "engagement", "chats", "chats_replied", "leads"]
DEFAULT_DAYS = 120


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def extract(actions) -> dict:
    """`actions` (list ของ {action_type, value}) -> {chats: 12, leads: 3, ...}"""
    got = {k: 0 for k in ACTION_MAP}
    if not isinstance(actions, list):
        return got
    want = {v: k for k, v in ACTION_MAP.items()}
    for a in actions:
        if not isinstance(a, dict):
            continue
        k = want.get(a.get("action_type"))
        if k:
            try:
                got[k] += int(float(a.get("value") or 0))
            except (TypeError, ValueError):
                pass
    return got


def backfill(limit: int = 0) -> dict:
    """เติมคอลัมน์ที่แตกใหม่ให้แถวเก่าที่มีแต่ JSON · รันซ้ำได้ (เขียนทับด้วยค่าที่คำนวณใหม่)"""
    from dashboard.models import MetaAdDaily

    qs = MetaAdDaily.objects.exclude(actions=[]).order_by("-date")
    if limit:
        qs = qs[:limit]
    rows, n = [], 0
    for r in qs.iterator(chunk_size=500):
        got = extract(r.actions)
        changed = any(getattr(r, k) != v for k, v in got.items())
        if changed:
            for k, v in got.items():
                setattr(r, k, v)
            rows.append(r)
        n += 1
        if len(rows) >= 500:
            MetaAdDaily.objects.bulk_update(rows, list(ACTION_MAP), batch_size=500)
            rows = []
    if rows:
        MetaAdDaily.objects.bulk_update(rows, list(ACTION_MAP), batch_size=500)
    return {"scanned": n}


def rebuild_daily(days: int = DEFAULT_DAYS) -> dict:
    """สร้าง `dash_ads_daily` ใหม่จาก `dash_meta_ad_daily` · ลบ-แล้วใส่ใหม่ในธุรกรรมเดียว"""
    from dashboard.models import AdsDaily, MetaAdDaily

    since = date.today() - timedelta(days=max(1, days))
    agg = (MetaAdDaily.objects.filter(date__gte=since)
           .values("date", "account_id")
           .annotate(spend=Sum("spend"), impressions=Sum("impressions"), reach=Sum("reach"),
                     clicks=Sum("clicks"), link_clicks=Sum("link_clicks"),
                     video_views=Sum("video_views"), engagement=Sum("engagement"),
                     chats=Sum("chats"), chats_replied=Sum("chats_replied"), leads=Sum("leads"),
                     ads=Count("ad_id", distinct=True),
                     campaigns=Count("campaign_id", distinct=True)))
    rows = [AdsDaily(date=r["date"], account_id=r["account_id"],
                     spend=r["spend"] or 0,
                     **{f: (r[f] or 0) for f in COUNT_FIELDS},
                     ads=r["ads"] or 0, campaigns=r["campaigns"] or 0)
            for r in agg]
    with transaction.atomic():
        AdsDaily.objects.filter(date__gte=since).delete()
        AdsDaily.objects.bulk_create(rows, batch_size=500)
    return {"rows": len(rows)}


def refresh_quiet(days: int = DEFAULT_DAYS) -> dict:
    """เรียกต่อท้ายรอบ sync — พังก็เงียบ ห้ามทำให้การเก็บข้อมูลดิบล้มตาม"""
    try:
        backfill()
        return rebuild_daily(days)
    except Exception as e:
        return {"errors": ["ads rebuild พัง: %s" % str(e)[:160]]}


# ── ตัวเลขสำหรับหน้าเว็บ / รายงาน ────────────────────────────────
def _costs(t: dict) -> dict:
    """ต้นทุนต่อหน่วย — **คิดจากผลรวมหารผลรวมเสมอ** (ดูหัวไฟล์ว่าทำไมห้ามเฉลี่ยค่าเฉลี่ย)"""
    sp = _f(t.get("spend"))
    def per(k):
        n = _f(t.get(k))
        return round(sp / n, 2) if n else None
    imp = _f(t.get("impressions"))
    return {
        "perChat": per("chats"),
        "perChatReplied": per("chats_replied"),
        "perLead": per("leads"),
        "perLinkClick": per("link_clicks"),
        "perClick": per("clicks"),
        "cpm": round(sp / imp * 1000, 2) if imp else None,
        "ctr": round(_f(t.get("clicks")) / imp * 100, 2) if imp else None,
        "replyRate": (round(_f(t.get("chats_replied")) / _f(t["chats"]) * 100, 1)
                      if _f(t.get("chats")) else None),
    }


def _z(t: dict) -> dict:
    out = {"spend": round(_f(t.get("spend")), 2)}
    for f in COUNT_FIELDS:
        out[f] = int(t.get(f) or 0)
    return out


def stats(dfrom: str, dto: str, top: int = 12) -> dict:
    """ตัวเลขโฆษณาของช่วงวันที่ — ใช้ทั้งหน้าเว็บ (`/api/admin/ads`) และรายงาน

    คืน: ยอดรวม + ต้นทุนต่อหน่วย + รายวัน + แยกแคมเปญ + โฆษณาที่ได้แชทเยอะสุด
    · `days` = ทุกวันในช่วง (วันที่ไม่มีข้อมูลส่ง null ไม่ใช่ 0 — กราฟจะได้ไม่ดิ่งลงศูนย์หลอกตา)
    """
    from dashboard.models import AdsDaily, MetaAdDaily

    try:
        s = date.fromisoformat(dfrom)
        e = date.fromisoformat(dto)
    except (TypeError, ValueError):
        e = date.today()
        s = e - timedelta(days=29)
    if s > e:
        s, e = e, s

    qs = AdsDaily.objects.filter(date__gte=s, date__lte=e)
    tot = qs.aggregate(spend=Sum("spend"), **{f: Sum(f) for f in COUNT_FIELDS})
    total = _z(tot)

    by_day = {r["date"].isoformat(): _z(r) for r in
              qs.values("date").annotate(spend=Sum("spend"),
                                         **{f: Sum(f) for f in COUNT_FIELDS})}
    days, cur = [], s
    while cur <= e and len(days) < 800:
        days.append(cur.isoformat())
        cur += timedelta(days=1)

    ad_qs = MetaAdDaily.objects.filter(date__gte=s, date__lte=e)
    camps = [dict(_z(r), id=r["campaign_id"], name=r["campaign_name"] or r["campaign_id"],
                  cost=_costs(r))
             for r in ad_qs.values("campaign_id", "campaign_name")
             .annotate(spend=Sum("spend"), **{f: Sum(f) for f in COUNT_FIELDS})
             .order_by("-spend")[:top]]
    ads = [dict(_z(r), id=r["ad_id"], name=r["ad_name"] or r["ad_id"],
                campaign=r["campaign_name"], cost=_costs(r))
           for r in ad_qs.values("ad_id", "ad_name", "campaign_name")
           .annotate(spend=Sum("spend"), **{f: Sum(f) for f in COUNT_FIELDS})
           .order_by("-chats", "-spend")[:top]]

    have = len(by_day)
    span = (e - s).days + 1
    return {
        "ok": True, "from": s.isoformat(), "to": e.isoformat(),
        "days": days, "daily": by_day,
        "total": total, "cost": _costs(total),
        "campaigns": camps, "ads": ads,
        "metricTh": METRIC_TH, "countFields": COUNT_FIELDS,
        "coverage": {"haveDays": have, "spanDays": span,
                     "first": min(by_day) if by_day else "", "last": max(by_day) if by_day else ""},
    }
