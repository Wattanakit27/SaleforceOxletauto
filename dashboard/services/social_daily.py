"""ทำตาราง "ยอดโซเชียลรายวัน" (`dash_social_daily`) จากตาราง snapshot ที่เก็บยอดสะสม

★ 23 ก.ย.69 — เจ้าของสั่ง: *"อย่าลืมแยกตาราง Daily Day กับภาพรวม เพราะถ้าแยก Daily ได้
  เราก็กรองวันได้"*

**ทำไมต้องมีตารางนี้** — ตาราง snapshot เก็บ "ยอด ณ ตอนดึง" (สะสมตลอดกาล) ใครอยากรู้ว่า
"วันที่ 20 ได้กี่วิว" ต้องเอาวันที่ 20 ลบวันที่ 19 เองทุกครั้ง · เขียน SQL เองยาก และ
กรองช่วงวันที่ตรงๆ ไม่ได้ · ตารางนี้คือผลที่ลบไว้ให้แล้ว → `WHERE date BETWEEN` ได้เลย

**กติกาที่ยึด**
- **สูตรเดียวกับหน้าเว็บเป๊ะ** — เรียก `social_stats._daily_one()` ตัวเดียวกับที่แท็บโซเชียลใช้
  (ห้ามเขียนสูตรใหม่ ไม่งั้นได้เลข 2 ชุดที่ไม่ตรงกัน แล้วไม่มีใครรู้ว่าอันไหนถูก)
- **นับเฉพาะแถว `trigger='cron'`** — แถว manual เกิดกลางวัน เอามาลบจะได้ครึ่งวันปนเต็มวัน
- **เป็นข้อมูล derived** — ลบทิ้งแล้วสร้างใหม่ได้เสมอ (`manage.py social_rebuild`)
- **เขียนแบบลบ-แล้วใส่ใหม่ต่อแพลตฟอร์ม** ในธุรกรรมเดียว → รันซ้ำกี่รอบก็ไม่เบิ้ล
"""
from __future__ import annotations

from datetime import date, timedelta

from django.db import transaction

from . import social_stats as S

# เก็บย้อนหลังแค่ไหนตอน rebuild (snapshot เองก็มีคลิปย้อน ~90 วันอยู่แล้ว)
DEFAULT_DAYS = 120


def _latest_per_day(rows, key_id: str) -> dict:
    """แถวล่าสุดของแต่ละ (ชิ้นงาน, วัน) — ใช้หา "ยอดสะสม ณ สิ้นวัน" + ชื่อเจ้าของ

    วันเดียวกันมีได้หลายแถว (เคยเจอ 19/09 มี 3 ชุด เพราะ gunicorn ถูกรีสตาร์ตกลางรอบ)
    """
    out: dict = {}
    for r in rows:
        d = S._d(r.get("snap_date"))
        if not d:
            continue
        k = (r.get(key_id), d)
        old = out.get(k)
        if not old or (r.get("taken_at") or 0) > (old.get("taken_at") or 0):
            out[k] = r
    return out


def _build(model, platform: str, key_id: str, owner_field: str, title_field: str,
           fmap: dict, days: int) -> list:
    """คืนลิสต์ `SocialDaily` (ยังไม่เขียน DB) ของแพลตฟอร์มหนึ่ง

    ⚠️ **ชื่อคอลัมน์ใน DB ของ 2 แพลตฟอร์มไม่เหมือนกัน** (Meta: `video_views`/`reactions` ·
    TikTok: `view_count`/`like_count`) → ต้องแปลงเป็นชื่อกลาง (`views`/`likes`/…) ก่อน
    ส่งเข้าสูตร เหมือนที่ `meta_stats`/`tiktok_stats` ทำ
    """
    from dashboard.models import SocialDaily

    since = date.today() - timedelta(days=max(1, days))
    cols = ["snap_date", "taken_at", key_id, owner_field] + list(fmap.values())
    if title_field:
        cols.append(title_field)
    rows = []
    for r in model.objects.filter(trigger="cron", snap_date__gte=since).values(*cols):
        row = {key_id: r.get(key_id), "snap_date": r.get("snap_date"),
               "taken_at": r.get("taken_at"),
               "_owner": r.get(owner_field) or "",
               "_title": (r.get(title_field) or "") if title_field else ""}
        for m, src in fmap.items():
            row[m] = r.get(src) or 0
        rows.append(row)
    if not rows:
        return []

    daily = S._daily_one(rows, key_id, set())      # ★ สูตรเดียวกับหน้าเว็บ
    latest = _latest_per_day(rows, key_id)

    out = []
    for oid, days_map in daily.items():
        for iso, m in days_map.items():
            d = S._d(iso)
            cum = latest.get((oid, d)) or {}
            out.append(SocialDaily(
                date=d, platform=platform, object_id=str(oid or "")[:64],
                owner_id=str(cum.get("_owner") or "")[:120],
                title=str(cum.get("_title") or "")[:200],
                views=m.get("views", 0), likes=m.get("likes", 0),
                comments=m.get("comments", 0), shares=m.get("shares", 0),
                cum_views=int(cum.get("views") or 0), cum_likes=int(cum.get("likes") or 0),
                cum_comments=int(cum.get("comments") or 0),
                cum_shares=int(cum.get("shares") or 0),
            ))
    return out


def rebuild(days: int = DEFAULT_DAYS) -> dict:
    """สร้างตารางรายวันใหม่ทั้งหมดจาก snapshot · คืนจำนวนแถวต่อแพลตฟอร์ม

    best-effort ต่อแพลตฟอร์ม — ฝั่งหนึ่งพังไม่ลากอีกฝั่ง (เช่นยังไม่ได้เชื่อม TikTok)
    """
    from dashboard.models import (MetaPostSnapshot, SocialDaily, TikTokVideoSnapshot,
                                  YouTubeVideoSnapshot)

    res = {"meta": 0, "tiktok": 0, "youtube": 0, "errors": []}
    plan = [
        (SocialDaily.META, MetaPostSnapshot, "post_id", "page_id", "message",
         {"views": "video_views", "likes": "reactions",
          "comments": "comments", "shares": "shares"}),
        (SocialDaily.TIKTOK, TikTokVideoSnapshot, "video_id", "open_id", "title",
         {"views": "view_count", "likes": "like_count",
          "comments": "comment_count", "shares": "share_count"}),
        # ⚠️ YouTube ไม่มี "แชร์" ใน Data API (และดิสไลก์ถูกปิดตั้งแต่ปี 2021)
        #    → ไม่ต้องใส่ใน fmap · `_daily_one` จะคิดให้เป็น 0 เอง ไม่ใช่บั๊ก
        (SocialDaily.YOUTUBE, YouTubeVideoSnapshot, "video_id", "channel_id", "title",
         {"views": "view_count", "likes": "like_count", "comments": "comment_count"}),
    ]
    for platform, model, key_id, owner, title, fmap in plan:
        try:
            rows = _build(model, platform, key_id, owner, title, fmap, days)
            with transaction.atomic():
                SocialDaily.objects.filter(platform=platform).delete()
                SocialDaily.objects.bulk_create(rows, batch_size=500)
            res[platform] = len(rows)
        except Exception as e:                      # ตารางยังไม่ migrate / ฟิลด์ไม่ตรง
            res["errors"].append("%s: %s" % (platform, str(e)[:160]))
    return res


def refresh_quiet(days: int = DEFAULT_DAYS) -> dict:
    """เรียกต่อท้ายรอบ sync — พังก็เงียบ **ห้ามทำให้การเก็บ snapshot ล้มตาม**

    (snapshot คือต้นฉบับ ถ้าเสียคือเสียถาวร · ตารางรายวันสร้างใหม่เมื่อไหร่ก็ได้)
    """
    try:
        return rebuild(days)
    except Exception as e:
        return {"errors": ["rebuild พัง: %s" % str(e)[:160]]}
