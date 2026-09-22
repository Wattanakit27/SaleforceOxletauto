# -*- coding: utf-8 -*-
"""สรุป engagement ของโซเชียล (Meta + TikTok) ให้หน้ากราฟ — ก.ย.69

*"เหลือหน้าของ Graph ดู Engagement ฝั่ง TikTok กับฝั่ง Meta"*

**หัวใจของไฟล์นี้: ตารางที่เราเก็บเป็น "ยอดสะสม" ไม่ใช่ "ยอดรายวัน"**
ทั้ง `dash_meta_post_snapshot` และ `dash_tiktok_video_snapshot` เก็บ *ยอด ณ ตอนที่ดึง*
(วิว 1,200 = ตั้งแต่โพสต์มาจนถึงเมื่อคืน) → ยอดของ "วันนี้" ต้องเอา **วันนี้ − เมื่อวาน**

กติกาที่ต้องรักษา (เคยเขียนไว้ตอนทำตัวดึง · ที่นี่คือฝั่งอ่าน):
- **นับเฉพาะแถว `trigger='cron'`** — แถว `manual` (คนกดดึงเอง) เกิดกลางวัน ถ้าเอามาลบด้วย
  จะได้ยอดครึ่งวันปนกับยอดเต็มวัน
- **วันเดียวกันอาจมีหลายแถว** (เคยเกิดจริง 19/09: gunicorn รีสตาร์ตกลางรอบ → cron เริ่มใหม่
  ได้ 3 ชุดในวันเดียว) → หยิบ **แถวที่ดึงล่าสุดของวันนั้น** ต่อโพสต์เสมอ
- **ยอดลดลง = ไม่นับ** (ติดลบเกิดได้ตอนโพสต์ถูกลบ/Meta แก้ตัวเลขย้อนหลัง) → ตัดเป็น 0
- **ต้องมีอย่างน้อย 2 วันถึงจะมีกราฟรายวัน** — วันแรกไม่มีวันก่อนหน้าให้ลบ
"""
from __future__ import annotations

from datetime import date, timedelta

# ชนิดตัวเลขที่เอามาโชว์ — ชื่อกลางใช้ร่วมกันทั้ง 2 ฝั่ง (หน้าเว็บวาดจากคีย์พวกนี้)
METRICS = ("views", "likes", "comments", "shares")
METRIC_TH = {"views": "วิว", "likes": "ไลก์", "comments": "คอมเมนต์", "shares": "แชร์"}


def _d(v) -> date | None:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _daily_from_snapshots(rows, key_id: str) -> dict:
    """แปลง "ยอดสะสมรายวัน" → "ยอดที่เพิ่มขึ้นในแต่ละวัน"

    `rows` = [{snap_date, taken_at, <key_id>, views, likes, comments, shares}] (เฉพาะ cron)
    คืน `{วันที่ iso: {views:.., likes:.., ...}}`
    """
    # 1) แถวล่าสุดของแต่ละ (โพสต์, วัน)
    latest: dict = {}
    for r in rows:
        d = _d(r.get("snap_date"))
        if not d:
            continue
        k = (r.get(key_id), d)
        old = latest.get(k)
        if not old or (r.get("taken_at") or 0) > (old.get("taken_at") or 0):
            latest[k] = r

    # 2) ต่อโพสต์: เรียงตามวัน แล้วหาผลต่างกับวันก่อนหน้า (ของโพสต์นั้นเอง)
    by_post: dict = {}
    for (pid, d), r in latest.items():
        by_post.setdefault(pid, []).append((d, r))
    out: dict = {}
    for pid, items in by_post.items():
        items.sort(key=lambda x: x[0])
        prev = None
        for d, r in items:
            if prev is not None:
                day = out.setdefault(d.isoformat(), {m: 0 for m in METRICS})
                for m in METRICS:
                    diff = int(r.get(m) or 0) - int(prev.get(m) or 0)
                    if diff > 0:                    # ยอดลดลง = โพสต์ถูกลบ/ตัวเลขถูกแก้ → ไม่นับ
                        day[m] += diff
            prev = r
    return out


def _daily_one(rows, key_id: str, ids: set) -> dict:
    """ยอดรายวัน **แยกรายชิ้น** — `{post_id: {วันที่: {views..}}}` (ใช้ตอนกดดูโพสต์/คลิปทีละอัน)

    ใช้ตรรกะเดียวกับ `_daily_from_snapshots` เป๊ะ (แถวล่าสุดของวัน · ผลต่างกับวันก่อน · ติดลบไม่นับ)
    ต่างแค่ **ไม่รวมทุกโพสต์เข้าด้วยกัน** — คิดแยกทีละชิ้นแล้วเก็บไว้ใต้ id ของมัน
    """
    latest: dict = {}
    for r in rows:
        pid = r.get(key_id)
        d = _d(r.get("snap_date"))
        if not d or (ids and pid not in ids):
            continue
        k = (pid, d)
        old = latest.get(k)
        if not old or (r.get("taken_at") or 0) > (old.get("taken_at") or 0):
            latest[k] = r
    by_post: dict = {}
    for (pid, d), r in latest.items():
        by_post.setdefault(pid, []).append((d, r))
    out: dict = {}
    for pid, items in by_post.items():
        items.sort(key=lambda x: x[0])
        prev, days = None, {}
        for d, r in items:
            if prev is not None:
                days[d.isoformat()] = {m: max(0, int(r.get(m) or 0) - int(prev.get(m) or 0))
                                       for m in METRICS}
            prev = r
        if days:
            out[pid] = days
    return out


def _range(frm, to) -> tuple:
    t = _d(to) or date.today()
    f = _d(frm) or (t - timedelta(days=29))
    return f, t


def meta_stats(frm=None, to=None, top: int = 10) -> dict:
    """ยอดของเพจ Facebook — รายวัน + โพสต์ที่ปังสุดในช่วง"""
    from dashboard.models import MetaAdDaily, MetaPostSnapshot

    f, t = _range(frm, to)
    # ดึงย้อนไป 1 วันก่อนช่วงที่ขอ — ไว้เป็น "ฐาน" ให้ลบหายอดวันแรกของช่วงได้
    qs = (MetaPostSnapshot.objects
          .filter(trigger="cron", snap_date__gte=f - timedelta(days=1), snap_date__lte=t)
          .values("post_id", "snap_date", "taken_at", "video_views", "reactions",
                  "comments", "shares"))
    rows = [{"post_id": r["post_id"], "snap_date": r["snap_date"], "taken_at": r["taken_at"],
             "views": r["video_views"], "likes": r["reactions"],
             "comments": r["comments"], "shares": r["shares"]} for r in qs]
    daily = {d: v for d, v in _daily_from_snapshots(rows, "post_id").items()
             if f.isoformat() <= d <= t.isoformat()}

    # โพสต์ที่ปังสุด = ยอดสะสมล่าสุดในช่วง (ใช้ได้แม้มี snapshot วันเดียว)
    best: dict = {}
    for r in (MetaPostSnapshot.objects
              .filter(snap_date__gte=f, snap_date__lte=t)
              .values("post_id", "taken_at", "message", "permalink", "post_type",
                      "created_time", "video_views", "reactions", "comments", "shares")):
        old = best.get(r["post_id"])
        if not old or r["taken_at"] > old["taken_at"]:
            best[r["post_id"]] = r
    cum = {"views": 0, "likes": 0, "comments": 0, "shares": 0}
    for r in best.values():                     # ยอดสะสมของ "ทุกโพสต์" ที่มี snapshot ในช่วง
        cum["views"] += int(r["video_views"] or 0)
        cum["likes"] += int(r["reactions"] or 0)
        cum["comments"] += int(r["comments"] or 0)
        cum["shares"] += int(r["shares"] or 0)
    posts = sorted(best.values(),
                   key=lambda r: (r["reactions"] or 0) + (r["comments"] or 0) + (r["shares"] or 0),
                   reverse=True)[:top]

    ads = {}
    for a in (MetaAdDaily.objects.filter(date__gte=f, date__lte=t)
              .values("date", "spend", "impressions", "clicks")):
        d = _d(a["date"]).isoformat()
        x = ads.setdefault(d, {"spend": 0.0, "impressions": 0, "clicks": 0})
        x["spend"] += float(a["spend"] or 0)
        x["impressions"] += int(a["impressions"] or 0)
        x["clicks"] += int(a["clicks"] or 0)

    # ★ 21 ก.ย.69 — ยอดที่ **Facebook รายงานเองระดับเพจ** (ไม่ได้รวมจากโพสต์)
    #   เอาไว้วางคู่กันในหน้าเว็บ → ตอบคำถาม "ที่เรารวมจากโพสต์ เก็บครบไหม" ด้วยตัวเลข
    page_daily, page_total = {}, {"views": 0, "engagements": 0, "pageViews": 0, "follows": 0}
    try:
        from dashboard.models import MetaPageDaily
        for r in (MetaPageDaily.objects.filter(date__gte=f, date__lte=t)
                  .values("date", "video_views", "engagements", "page_views", "follows")):
            k = _d(r["date"]).isoformat()
            x = page_daily.setdefault(k, {"views": 0, "engagements": 0, "pageViews": 0, "follows": 0})
            for a, b in (("views", "video_views"), ("engagements", "engagements"),
                         ("pageViews", "page_views"), ("follows", "follows")):
                x[a] += int(r[b] or 0)
                page_total[a] += int(r[b] or 0)
    except Exception:                 # ยังไม่ migrate / ตารางยังว่าง = ไม่มีตัวเทียบ ไม่พัง
        page_daily, page_total = {}, {}

    top_ids = {p["post_id"] for p in posts}
    return {
        "pageDaily": page_daily, "pageTotal": page_total,
        "pageDays": len(page_daily),
        "daily": daily,
        # ★ ยอดสะสม = ใช้โชว์ตอนที่ยังทำยอดรายวันไม่ได้ (เก็บไม่ถึง 2 คืน) — ดีกว่าโชว์ "—" เปล่าๆ
        "cum": cum, "postCount": len(best),
        # ยอดรายวันแยกรายชิ้น — ส่งมาพร้อมก้อนแรกเลย (เฉพาะที่อยู่ในตาราง) กดดูแล้วไม่ต้องยิงใหม่
        "postDaily": {k: {d: v for d, v in days.items() if f.isoformat() <= d <= t.isoformat()}
                      for k, days in _daily_one(rows, "post_id", top_ids).items()},
        "ads": ads,
        "posts": [{
            "id": p["post_id"],
            "text": (p["message"] or "")[:120],
            "link": p["permalink"] or "",
            "type": p["post_type"] or "",
            "date": (p["created_time"].date().isoformat() if p["created_time"] else ""),
            "views": p["video_views"] or 0, "likes": p["reactions"] or 0,
            "comments": p["comments"] or 0, "shares": p["shares"] or 0,
        } for p in posts],
        "days": _cron_days(MetaPostSnapshot, f, t),
    }


def tiktok_stats(frm=None, to=None, top: int = 10) -> dict:
    """ยอดของช่อง TikTok — โครงเดียวกับฝั่ง Meta (หน้าเว็บวาดด้วยโค้ดชุดเดียวกัน)"""
    from dashboard.models import TikTokAccount, TikTokVideoSnapshot

    f, t = _range(frm, to)
    qs = (TikTokVideoSnapshot.objects
          .filter(trigger="cron", snap_date__gte=f - timedelta(days=1), snap_date__lte=t)
          .values("video_id", "open_id", "snap_date", "taken_at", "view_count", "like_count",
                  "comment_count", "share_count"))
    rows = [{"video_id": r["video_id"], "snap_date": r["snap_date"], "taken_at": r["taken_at"],
             "views": r["view_count"], "likes": r["like_count"],
             "comments": r["comment_count"], "shares": r["share_count"]} for r in qs]
    daily = {d: v for d, v in _daily_from_snapshots(rows, "video_id").items()
             if f.isoformat() <= d <= t.isoformat()}

    best: dict = {}
    for r in (TikTokVideoSnapshot.objects
              .filter(snap_date__gte=f, snap_date__lte=t)
              .values("video_id", "open_id", "taken_at", "title", "share_url", "create_time",
                      "view_count", "like_count", "comment_count", "share_count")):
        old = best.get(r["video_id"])
        if not old or r["taken_at"] > old["taken_at"]:
            best[r["video_id"]] = r
    cum = {"views": 0, "likes": 0, "comments": 0, "shares": 0}
    for r in best.values():
        cum["views"] += int(r["view_count"] or 0)
        cum["likes"] += int(r["like_count"] or 0)
        cum["comments"] += int(r["comment_count"] or 0)
        cum["shares"] += int(r["share_count"] or 0)
    clips = sorted(best.values(), key=lambda r: r["view_count"] or 0, reverse=True)[:top]

    accs = list(TikTokAccount.objects.values("open_id", "label", "display_name", "status", "scope"))
    top_ids = {c["video_id"] for c in clips}
    # ★ แยกรายช่อง (เจ้าของแจ้ง 24 ก.ย.69 "มันไม่มี TikTok แยกช่อง")
    ch_name = {a["open_id"]: (a["label"] or a["display_name"] or a["open_id"][:10]) for a in accs}
    owner_of = {r["video_id"]: r["open_id"] for r in qs}
    by = _owner_totals(rows, "video_id", owner_of, f, t)
    return {
        "daily": daily,
        "cum": cum, "postCount": len(best),
        "postDaily": {k: {d: v for d, v in days.items() if f.isoformat() <= d <= t.isoformat()}
                      for k, days in _daily_one(rows, "video_id", top_ids).items()},
        "posts": [{
            "id": c["video_id"],
            "text": (c["title"] or "")[:120],
            "link": c["share_url"] or "",
            "type": "คลิป",
            "date": (c["create_time"].date().isoformat() if c["create_time"] else ""),
            "views": c["view_count"] or 0, "likes": c["like_count"] or 0,
            "comments": c["comment_count"] or 0, "shares": c["share_count"] or 0,
        } for c in clips],
        "days": _cron_days(TikTokVideoSnapshot, f, t),
        "byChannel": [dict(v, id=k, name=ch_name.get(k, k[:10]))
                      for k, v in sorted(by.items(), key=lambda kv: -kv[1]["views"])],
        "accounts": [{"label": a["label"], "name": a["display_name"],
                      "status": a["status"], "scope": a["scope"]} for a in accs],
        # บอกหน้าเว็บให้รู้ว่า "ไม่มีข้อมูล" เพราะอะไร จะได้บอกวิธีแก้แทนกราฟเปล่า
        "needScope": bool(accs) and not any("video.list" in (a["scope"] or "") for a in accs),
    }


def _owner_totals(rows, key_id: str, owner_of: dict, f, t) -> dict:
    """ยอด "ที่เพิ่มขึ้นในช่วง" แยกตามเจ้าของ (ช่อง/เพจ) — `{owner: {views:.., likes:..}}`

    ★ 24 ก.ย.69 (เจ้าของแจ้ง "มันไม่มี TikTok แยกช่อง")
    คิดรายชิ้นด้วย `_daily_one` ก่อน แล้วค่อยรวมเข้าเจ้าของ — **ห้ามรวมยอดสะสมของช่องตรงๆ
    แล้วลบกัน** เพราะคลิปที่เพิ่งโพสต์วันนี้จะทำให้ผลต่างพุ่งทั้งที่ไม่มีใครดูเพิ่ม
    """
    out: dict = {}
    for item_id, days in _daily_one(rows, key_id, set()).items():
        o = owner_of.get(item_id) or ""
        agg = out.setdefault(o, {m: 0 for m in METRICS})
        for d, v in days.items():
            if f.isoformat() <= d <= t.isoformat():
                for m in METRICS:
                    agg[m] += v.get(m, 0)
    return out


def youtube_stats(frm=None, to=None, top: int = 10) -> dict:
    """ยอดของช่อง YouTube — โครงเดียวกับ Meta/TikTok (หน้าเว็บวาดด้วยโค้ดชุดเดียวกัน)

    ⚠️ YouTube **ไม่มียอดแชร์** ใน Data API → `shares` เป็น 0 เสมอ ไม่ใช่ตัวเลขผิด
    """
    from dashboard.models import YouTubeChannelSnapshot, YouTubeVideoSnapshot

    f, t = _range(frm, to)
    qs = (YouTubeVideoSnapshot.objects
          .filter(trigger="cron", snap_date__gte=f - timedelta(days=1), snap_date__lte=t)
          .values("video_id", "channel_id", "snap_date", "taken_at",
                  "view_count", "like_count", "comment_count"))
    rows = [{"video_id": r["video_id"], "snap_date": r["snap_date"], "taken_at": r["taken_at"],
             "views": r["view_count"], "likes": r["like_count"],
             "comments": r["comment_count"], "shares": 0} for r in qs]
    owner_of = {r["video_id"]: r["channel_id"] for r in qs}
    daily = {d: v for d, v in _daily_from_snapshots(rows, "video_id").items()
             if f.isoformat() <= d <= t.isoformat()}

    best: dict = {}
    for r in (YouTubeVideoSnapshot.objects
              .filter(snap_date__gte=f, snap_date__lte=t)
              .values("video_id", "channel_id", "taken_at", "title", "published_at",
                      "is_short", "view_count", "like_count", "comment_count")):
        old = best.get(r["video_id"])
        if not old or r["taken_at"] > old["taken_at"]:
            best[r["video_id"]] = r
    cum = {"views": 0, "likes": 0, "comments": 0, "shares": 0}
    for r in best.values():
        cum["views"] += int(r["view_count"] or 0)
        cum["likes"] += int(r["like_count"] or 0)
        cum["comments"] += int(r["comment_count"] or 0)
    clips = sorted(best.values(), key=lambda r: r["view_count"] or 0, reverse=True)[:top]

    # ชื่อช่อง = แถวล่าสุดของ snapshot ช่อง
    names, subs = {}, {}
    for r in YouTubeChannelSnapshot.objects.order_by("taken_at").values(
            "channel_id", "title", "subscriber_count"):
        names[r["channel_id"]] = r["title"] or r["channel_id"]
        subs[r["channel_id"]] = r["subscriber_count"]

    top_ids = {c["video_id"] for c in clips}
    by = _owner_totals(rows, "video_id", owner_of, f, t)
    return {
        "daily": daily,
        "cum": cum, "postCount": len(best),
        "postDaily": {k: {d: v for d, v in days.items() if f.isoformat() <= d <= t.isoformat()}
                      for k, days in _daily_one(rows, "video_id", top_ids).items()},
        "posts": [{
            "id": c["video_id"],
            "text": (c["title"] or "")[:120],
            "link": "https://www.youtube.com/watch?v=" + (c["video_id"] or ""),
            "type": "Shorts" if c["is_short"] else "คลิป",
            "date": (c["published_at"].date().isoformat() if c["published_at"] else ""),
            "views": c["view_count"] or 0, "likes": c["like_count"] or 0,
            "comments": c["comment_count"] or 0, "shares": 0,
        } for c in clips],
        "days": _cron_days(YouTubeVideoSnapshot, f, t),
        "byChannel": [dict(v, id=k, name=names.get(k, k), subs=subs.get(k))
                      for k, v in sorted(by.items(), key=lambda kv: -kv[1]["views"])],
        "accounts": [{"label": n, "name": n, "status": "active", "scope": ""}
                     for n in names.values()],
        "needScope": False,
    }

def _cron_days(model, f: date, t: date) -> int:
    """มี snapshot รอบ cron กี่วันในช่วง — <2 วัน = ยังทำกราฟรายวันไม่ได้ (ต้องมีวันก่อนหน้าให้ลบ)"""
    try:
        return (model.objects.filter(trigger="cron", snap_date__gte=f - timedelta(days=1),
                                     snap_date__lte=t)
                .values("snap_date").distinct().count())
    except Exception:
        return 0


def overview(frm=None, to=None) -> dict:
    """ก้อนเดียวที่หน้าเว็บเรียกใช้ — 2 ฝั่ง + ยอดรวมของช่วง"""
    f, t = _range(frm, to)
    m, k, y = meta_stats(f, t), tiktok_stats(f, t), youtube_stats(f, t)

    def _sum(daily):
        out = {x: 0 for x in METRICS}
        for v in daily.values():
            for x in METRICS:
                out[x] += v.get(x, 0)
        return out

    days = [(f + timedelta(days=i)).isoformat() for i in range((t - f).days + 1)]
    return {
        "from": f.isoformat(), "to": t.isoformat(), "days": days,
        "metrics": list(METRICS), "metricTh": METRIC_TH,
        "meta": {**m, "total": _sum(m["daily"]),
                 "adSpend": round(sum(a["spend"] for a in m["ads"].values()), 2)},
        "tiktok": {**k, "total": _sum(k["daily"])},
        "youtube": {**y, "total": _sum(y["daily"])},
    }
