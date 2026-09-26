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


def _channel_rows(inc: dict, cum: dict, posts: dict, names: dict,
                  subs: dict | None = None, always=()) -> list:
    """รวมเป็นแถวตาราง "แยกตามช่อง" — ทั้งยอดที่เพิ่มในช่วง **และ** ยอดสะสม

    ★ 24 ก.ย.69 (เจ้าของแจ้ง *"TikTok ก็มีตั้งหลายช่อง Facebook ก็มีตั้งหลายช่อง ทำไมไม่แยกหน่อย"*)

    2 กติกาที่ทำให้ตารางนี้ใช้งานได้ตั้งแต่วันแรก:
    - **ส่งยอดสะสมมาด้วยเสมอ** — ยอด "ที่เพิ่มขึ้น" ต้องมี snapshot 2 คืนถึงคำนวณได้
      ถ้าส่งแต่ยอดเพิ่ม ช่วงที่เพิ่งเริ่มเก็บจะเป็น 0 ทั้งตาราง แล้วดูเหมือนระบบพัง
    - **`always` = ช่องที่เชื่อมไว้แล้ว ต้องมีแถวเสมอ** แม้เดือนนี้ไม่ได้ลงคลิป/โพสต์เลย
      ไม่งั้นช่องจะ *หายไปเฉยๆ* แล้วคนอ่านสรุปเองว่าระบบมองไม่เห็นช่องนั้น
    """
    out = []
    for cid in (set(inc) | set(cum) | {str(a) for a in always if a}):
        if not cid:
            continue
        i, c = inc.get(cid) or {}, cum.get(cid) or {}
        out.append({
            "id": cid, "name": names.get(cid) or cid[:14],
            # ★ `live` ต้องดูเป็น "รายช่อง" ไม่ใช่รายแพลตฟอร์ม — ช่องที่เพิ่งเก็บคืนแรก
            #   ยังคิดยอดรายวันไม่ได้ ถ้าโชว์ 0 จะอ่านเป็น "ไม่มีใครดู" ซึ่งไม่จริง
            "live": cid in inc,
            **{m: int(i.get(m, 0)) for m in METRICS},
            "cum": {m: int(c.get(m, 0)) for m in METRICS},
            "posts": int(posts.get(cid, 0)),
            "subs": (subs or {}).get(cid),
        })
    out.sort(key=lambda r: (r["views"], r["cum"]["views"]), reverse=True)
    return out


def _meta_pages() -> set:
    try:
        from . import meta
        return meta.pages()
    except Exception:                       # ยังไม่ตั้ง META_PAGE_IDS = ไม่มีรายชื่อบังคับ
        return set()


def _page_names() -> dict:
    """ชื่อเพจ Facebook — `meta_sync` จดไว้ตอนดึงยอดระดับเพจ (KV `meta_page_names`)

    เก็บใน KV ไม่ใช่คอลัมน์ในตาราง เพราะเป็นแค่ "ป้ายชื่อ" ที่เปลี่ยนได้ตลอด
    และไม่อยากให้ทุกแถว snapshot ต้องแบกชื่อซ้ำกันเป็นล้านแถว
    """
    try:
        from .cache_store import get_kv
        v = get_kv("meta_page_names") or {}
        v = v.get("data", v) if isinstance(v, dict) else {}
        return {str(k): str(n) for k, n in (v or {}).items() if n}
    except Exception:
        return {}


def meta_stats(frm=None, to=None, top: int = 10) -> dict:
    """ยอดของเพจ Facebook — รายวัน + โพสต์ที่ปังสุดในช่วง"""
    from dashboard.models import MetaAdDaily, MetaPostSnapshot

    f, t = _range(frm, to)
    # ดึงย้อนไป 1 วันก่อนช่วงที่ขอ — ไว้เป็น "ฐาน" ให้ลบหายอดวันแรกของช่วงได้
    qs = (MetaPostSnapshot.objects
          .filter(trigger="cron", snap_date__gte=f - timedelta(days=1), snap_date__lte=t)
          .values("post_id", "page_id", "snap_date", "taken_at", "video_views", "reactions",
                  "comments", "shares"))
    rows = [{"post_id": r["post_id"], "snap_date": r["snap_date"], "taken_at": r["taken_at"],
             "views": r["video_views"], "likes": r["reactions"],
             "comments": r["comments"], "shares": r["shares"]} for r in qs]
    owner_of = {r["post_id"]: r["page_id"] for r in qs}
    daily = {d: v for d, v in _daily_from_snapshots(rows, "post_id").items()
             if f.isoformat() <= d <= t.isoformat()}

    # โพสต์ที่ปังสุด = ยอดสะสมล่าสุดในช่วง (ใช้ได้แม้มี snapshot วันเดียว)
    best: dict = {}
    for r in (MetaPostSnapshot.objects
              .filter(snap_date__gte=f, snap_date__lte=t)
              .values("post_id", "page_id", "taken_at", "message", "permalink", "post_type",
                      "created_time", "video_views", "reactions", "comments", "shares")):
        old = best.get(r["post_id"])
        if not old or r["taken_at"] > old["taken_at"]:
            best[r["post_id"]] = r
        owner_of.setdefault(r["post_id"], r["page_id"])
    cum = {"views": 0, "likes": 0, "comments": 0, "shares": 0}
    cum_by, posts_by = {}, {}
    for r in best.values():                     # ยอดสะสมของ "ทุกโพสต์" ที่มี snapshot ในช่วง
        cum["views"] += int(r["video_views"] or 0)
        cum["likes"] += int(r["reactions"] or 0)
        cum["comments"] += int(r["comments"] or 0)
        cum["shares"] += int(r["shares"] or 0)
        c = cum_by.setdefault(r["page_id"], {m: 0 for m in METRICS})
        for key, col in (("views", "video_views"), ("likes", "reactions"),
                         ("comments", "comments"), ("shares", "shares")):
            c[key] += int(r[col] or 0)
        posts_by[r["page_id"]] = posts_by.get(r["page_id"], 0) + 1
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
    per_item = _daily_one(rows, "post_id", set())
    return {
        "dailyItems": _daily_cover(per_item, f, t),   # คิดยอดรายวันได้กี่โพสต์ (เทียบกับ postCount)
        "byChannel": _channel_rows(_owner_totals(per_item, owner_of, f, t),
                                   cum_by, posts_by, _page_names(), always=_meta_pages()),
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
    from dashboard.models import TikTokAccount, TikTokAccountSnapshot, TikTokVideoSnapshot

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
    cum_by, posts_by = {}, {}
    for r in best.values():
        cum["views"] += int(r["view_count"] or 0)
        cum["likes"] += int(r["like_count"] or 0)
        cum["comments"] += int(r["comment_count"] or 0)
        cum["shares"] += int(r["share_count"] or 0)
        c = cum_by.setdefault(r["open_id"], {m: 0 for m in METRICS})
        for key, col in (("views", "view_count"), ("likes", "like_count"),
                         ("comments", "comment_count"), ("shares", "share_count")):
            c[key] += int(r[col] or 0)
        posts_by[r["open_id"]] = posts_by.get(r["open_id"], 0) + 1
    clips = sorted(best.values(), key=lambda r: r["view_count"] or 0, reverse=True)[:top]

    accs = list(TikTokAccount.objects.values("open_id", "label", "display_name", "status", "scope"))
    top_ids = {c["video_id"] for c in clips}
    # ★ แยกรายช่อง (เจ้าของแจ้ง 24 ก.ย.69 "มันไม่มี TikTok แยกช่อง")
    ch_name = {a["open_id"]: (a["label"] or a["display_name"] or a["open_id"][:10]) for a in accs}
    owner_of = {r["video_id"]: r["open_id"] for r in qs}
    for r in best.values():
        owner_of.setdefault(r["video_id"], r["open_id"])
    per_item = _daily_one(rows, "video_id", set())
    by = _owner_totals(per_item, owner_of, f, t)
    subs = {}                                   # ผู้ติดตาม = แถวล่าสุดของช่องนั้น
    for r in TikTokAccountSnapshot.objects.order_by("taken_at").values("open_id", "follower_count"):
        subs[r["open_id"]] = r["follower_count"]
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
        "dailyItems": _daily_cover(per_item, f, t),   # คิดยอดรายวันได้กี่คลิป (เทียบกับ postCount)
        "byChannel": _channel_rows(by, cum_by, posts_by, ch_name, subs,
                                   always=[a["open_id"] for a in accs]),
        "accounts": [{"label": a["label"], "name": a["display_name"],
                      "status": a["status"], "scope": a["scope"]} for a in accs],
        # บอกหน้าเว็บให้รู้ว่า "ไม่มีข้อมูล" เพราะอะไร จะได้บอกวิธีแก้แทนกราฟเปล่า
        "needScope": bool(accs) and not any("video.list" in (a["scope"] or "") for a in accs),
    }


def _owner_totals(per_item: dict, owner_of: dict, f, t) -> dict:
    """ยอด "ที่เพิ่มขึ้นในช่วง" แยกตามเจ้าของ (ช่อง/เพจ) — `{owner: {views:.., likes:..}}`

    ★ 24 ก.ย.69 (เจ้าของแจ้ง "มันไม่มี TikTok แยกช่อง")
    รับ `per_item` = ผลของ `_daily_one` (คิดรายชิ้นมาแล้ว) — **ห้ามรวมยอดสะสมของช่องตรงๆ
    แล้วลบกัน** เพราะคลิปที่เพิ่งโพสต์วันนี้จะทำให้ผลต่างพุ่งทั้งที่ไม่มีใครดูเพิ่ม
    """
    out: dict = {}
    for item_id, days in per_item.items():
        o = owner_of.get(item_id) or ""
        agg = out.setdefault(o, {m: 0 for m in METRICS})
        for d, v in days.items():
            if f.isoformat() <= d <= t.isoformat():
                for m in METRICS:
                    agg[m] += v.get(m, 0)
    return out


def _daily_cover(per_item: dict, f, t) -> int:
    """คิดยอดรายวันได้กี่ชิ้นในช่วงนี้ (ชิ้นที่มี snapshot อย่างน้อย 2 คืนติดกัน)

    ★ 24 ก.ย.69 (เจ้าของถาม *"ไม่เข้าใจทำไม TikTok เป็นศูนย์วิวอ่ะ"*)
    วัดจริง 23/09: TikTok มีคลิปในระบบ 533 คลิป แต่คืนก่อนหน้าเก็บได้แค่ **1 คลิป**
    (เพิ่งเชื่อมช่องครบตอนบ่าย 23/09) → จับคู่ลบกันได้คลิปเดียว = "วิว 1"
    ซึ่ง *ถูกตามสูตร* แต่วางข้าง Facebook 76,494 แล้วอ่านเป็น "TikTok ตายแล้ว"
    → หน้าเว็บต้องรู้สัดส่วนนี้ เพื่อเลือกโชว์ยอดสะสมแทนเมื่อความครอบคลุมต่ำเกินไป
    """
    n = 0
    for days in per_item.values():
        if any(f.isoformat() <= d <= t.isoformat() for d in days):
            n += 1
    return n


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
    cum_by, posts_by = {}, {}
    for r in best.values():
        cum["views"] += int(r["view_count"] or 0)
        cum["likes"] += int(r["like_count"] or 0)
        cum["comments"] += int(r["comment_count"] or 0)
        c = cum_by.setdefault(r["channel_id"], {m: 0 for m in METRICS})
        for key, col in (("views", "view_count"), ("likes", "like_count"),
                         ("comments", "comment_count")):
            c[key] += int(r[col] or 0)
        posts_by[r["channel_id"]] = posts_by.get(r["channel_id"], 0) + 1
        owner_of.setdefault(r["video_id"], r["channel_id"])
    clips = sorted(best.values(), key=lambda r: r["view_count"] or 0, reverse=True)[:top]

    # ชื่อช่อง = แถวล่าสุดของ snapshot ช่อง
    names, subs = {}, {}
    for r in YouTubeChannelSnapshot.objects.order_by("taken_at").values(
            "channel_id", "title", "subscriber_count"):
        names[r["channel_id"]] = r["title"] or r["channel_id"]
        subs[r["channel_id"]] = r["subscriber_count"]

    top_ids = {c["video_id"] for c in clips}
    per_item = _daily_one(rows, "video_id", set())
    by = _owner_totals(per_item, owner_of, f, t)
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
        "dailyItems": _daily_cover(per_item, f, t),
        "byChannel": _channel_rows(by, cum_by, posts_by, names, subs, always=names.keys()),
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


def _side_cfg() -> dict:
    """ชื่อคอลัมน์ของแต่ละแพลตฟอร์ม — 3 ตารางเก็บเรื่องเดียวกันแต่ตั้งชื่อคนละแบบ

    **เพิ่มแพลตฟอร์มใหม่ = เติมที่นี่ที่เดียว** แล้ว `channel_posts()` ใช้ได้เลย
    """
    from dashboard.models import MetaPostSnapshot, TikTokVideoSnapshot, YouTubeVideoSnapshot

    return {
        "meta": dict(model=MetaPostSnapshot, owner="page_id", pid="post_id", when="created_time",
                     title="message", link="permalink", kind="post_type",
                     cols={"views": "video_views", "likes": "reactions",
                           "comments": "comments", "shares": "shares"}),
        "tiktok": dict(model=TikTokVideoSnapshot, owner="open_id", pid="video_id", when="create_time",
                       title="title", link="share_url", kind=None,
                       cols={"views": "view_count", "likes": "like_count",
                             "comments": "comment_count", "shares": "share_count"}),
        "youtube": dict(model=YouTubeVideoSnapshot, owner="channel_id", pid="video_id",
                        when="published_at", title="title", link=None, kind=None,
                        cols={"views": "view_count", "likes": "like_count",
                              "comments": "comment_count", "shares": None}),
    }


SORT_KEYS = ("date", "views", "likes", "comments", "shares")


def _sort_rows(rows: list, sort: str, direction: str, basis: str) -> list:
    """เรียงคลิป/โพสต์ — ทำฝั่งเซิร์ฟเวอร์เสมอ

    ★ ห้ามเรียงฝั่งหน้าเว็บ เพราะหน้าเว็บโหลดมาทีละ 48 ชิ้นจาก 580
      เรียงเฉพาะที่โหลดมา = "คลิปวิวน้อยสุด" จะเป็นคลิปวิวน้อยสุด *ในหน้านี้* ซึ่งไม่ใช่คำตอบ

    ★ เรียงจากน้อยไปมากด้วย "ยอดในช่วง" → ชิ้นที่ยัง **คิดยอดรายวันไม่ได้** ต้องไปอยู่ท้าย
      (ต้องมี snapshot 2 คืนถึงลบกันได้) ไม่งั้น "วิวน้อยที่สุด" จะกลายเป็นกอง 0
      ของคลิปที่ยังไม่มีข้อมูล — เลขที่ถูกตามสูตร แต่ตอบผิดคำถาม
    """
    asc = direction == "asc"
    if sort == "date":
        rows.sort(key=lambda r: (r.get("date") or ""), reverse=not asc)
        return rows
    m = sort if sort in METRICS else "views"
    use_inc = basis != "total"
    def key(r):
        v = (r["inc"].get(m, 0) if use_inc else r.get(m, 0)) or 0
        unknown = 1 if (use_inc and not r.get("live")) else 0   # ยังคิดรายวันไม่ได้ = ท้ายแถวเสมอ
        return (unknown, v if asc else -v, -(r.get(m) or 0))
    rows.sort(key=key)
    return rows


def channel_posts(side: str, owner: str, frm=None, to=None, limit: int = 48, offset: int = 0,
                  sort: str = "views", direction: str = "desc",
                  basis: str = "range") -> dict:
    """คลิป/โพสต์ **ทั้งหมดของช่องเดียว** — สำหรับหน้า "ดูรายช่อง" (26 ก.ย.69 · เจ้าของขอ)

    *"อยากให้มันสามารถกดเข้าไปดูรายละเอียดของคลิปนั้นได้ แล้วก็อยากให้มันแบ่งช่องได้ด้วย
    ถ้าคุณรู้จักแอดไลบรารี ฉันอยากได้ประมาณนั้น … อยากวัด performance ของคลิปหนึ่งคลิป
    หรือช่องหนึ่งช่องไปเลย"*

    ทำไมต้องมี endpoint แยก แทนที่จะส่งมาพร้อมก้อนแรก: เพจเดียวมีโพสต์ **580-589 ชิ้น**
    (วัดจริง 26/09) รวมทุกช่อง ~2,000 ชิ้น · ถ้าส่งมาหมดพร้อม `postDaily` ของทุกชิ้น
    ก้อน JSON จะหลายร้อย KB ต่อการเปลี่ยนช่วงวันที่หนึ่งครั้ง → ดึงเฉพาะตอนกดเข้าไปดูช่องนั้น

    คืน `{rows, total, daily}` — `daily` เป็นของเฉพาะแถวที่ส่งไป (หน้าเว็บเอาไป merge
    เข้า `postDaily` แล้วหน้ารายชิ้นเดิมทำงานต่อได้ทันที ไม่ต้องแก้)
    """
    cfg = _side_cfg().get(side)
    if not cfg or not owner:
        return {"rows": [], "total": 0, "daily": {}}
    f, t = _range(frm, to)
    M, own, pid, cols = cfg["model"], cfg["owner"], cfg["pid"], cfg["cols"]

    want = {pid, "snap_date", "taken_at", cfg["when"], cfg["title"]}
    want |= {c for c in cols.values() if c}
    for k in ("link", "kind"):
        if cfg[k]:
            want.add(cfg[k])

    def _num(r, m):
        col = cols.get(m)
        return int(r.get(col) or 0) if col else 0

    # ยอดรายวัน = ผลต่างของ snapshot รอบ cron (ต้องเผื่อวันก่อนหน้า 1 วันไว้เป็นฐานลบ)
    daily_rows = [{"id": r[pid], "snap_date": r["snap_date"], "taken_at": r["taken_at"],
                   **{m: _num(r, m) for m in METRICS}}
                  for r in M.objects.filter(trigger="cron", snap_date__gte=f - timedelta(days=1),
                                            snap_date__lte=t, **{own: owner}).values(*want)]
    per_item = _daily_one(daily_rows, "id", set())
    per_item = {k: {d: v for d, v in days.items() if f.isoformat() <= d <= t.isoformat()}
                for k, days in per_item.items()}

    best: dict = {}
    for r in M.objects.filter(snap_date__gte=f, snap_date__lte=t, **{own: owner}).values(*want):
        old = best.get(r[pid])
        if not old or r["taken_at"] > old["taken_at"]:
            best[r[pid]] = r

    # อ่านรายชื่อรูปปกที่เก็บไว้ทีเดียว ดีกว่าเช็คไฟล์ทีละแถว (หน้าหนึ่ง 48 แถว)
    try:
        from . import covers
        thumb_cache = covers.have(side) if side in covers.SIDES else None
    except Exception:
        thumb_cache = None

    rows = []
    for vid, r in best.items():
        days = per_item.get(vid) or {}
        inc = {m: sum(v.get(m, 0) for v in days.values()) for m in METRICS}
        when = r.get(cfg["when"])
        rows.append({
            "id": vid,
            "text": (r.get(cfg["title"]) or "")[:160],
            "link": (r.get(cfg["link"]) if cfg["link"] else "") or _fallback_link(side, vid),
            "thumb": _thumb(side, vid, cache=thumb_cache),
            "type": (r.get(cfg["kind"]) if cfg["kind"] else "") or "",
            "date": when.date().isoformat() if when else "",
            "live": bool(days),          # คิดยอดรายวันของชิ้นนี้ได้หรือยัง
            "inc": inc,
            **{m: _num(r, m) for m in METRICS},      # ยอดสะสม
        })
    _sort_rows(rows, sort if sort in SORT_KEYS else "views",
               "asc" if direction == "asc" else "desc",
               "total" if basis == "total" else "range")
    page = rows[max(0, offset):max(0, offset) + max(1, limit)]
    return {"rows": page, "total": len(rows),
            "daily": {r["id"]: per_item.get(r["id"], {}) for r in page}}


def _thumb(side: str, vid: str, cache=None) -> str:
    """รูปปกของคลิป/โพสต์

    · **YouTube** — ประกอบจาก video id ได้ฟรี ไม่หมดอายุ ไม่ต้องเก็บไฟล์
    · **TikTok / Facebook** — ลิงก์ที่ API ให้มาหมดอายุใน ~6 ชม. จึง **โหลดไฟล์มาเก็บเอง**
      ตอน sync แล้วเสิร์ฟจาก /media/ ของเรา (ดู [covers.py](covers.py) · 26 ก.ย.69)
      ยังไม่มีไฟล์ = คืน '' แล้วหน้าเว็บใช้แถบสีประจำแพลตฟอร์มแทน

    `cache` = ชุด id ที่มีไฟล์แล้ว (อ่านทีเดียวต่อคำขอ) — ไม่งั้นต้องเช็คไฟล์ทีละแถว
    """
    if side == "youtube":
        return "https://i.ytimg.com/vi/%s/mqdefault.jpg" % vid if vid else ""
    try:
        from . import covers
        return covers.url_for(side, vid, cache=cache)
    except Exception:
        return ""


def _fallback_link(side: str, vid: str) -> str:
    """ลิงก์ไปโพสต์จริง สำหรับฝั่งที่ไม่ได้เก็บลิงก์ไว้ (YouTube ประกอบจาก id ได้)"""
    return "https://www.youtube.com/watch?v=%s" % vid if side == "youtube" and vid else ""


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
