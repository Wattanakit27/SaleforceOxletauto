# -*- coding: utf-8 -*-
"""ดึงยอดโพสต์ + ผลโฆษณาจาก Meta เก็บเป็น raw data — ก.ย.69

*"ดึงทุกๆ เที่ยงคืน ตั้งเวลาไว้เลย · ข้อมูลโฆษณาก็ดึงมาเป็น raw data ดึงพร้อมกัน
 เว้นแต่จะมีการกด sync ข้อมูลภายในตอนนั้น ซึ่งขึ้นข้อความแจ้งเตือนด้วยกรณีที่ sync
 ถี่หรือบ่อยเกินไป ว่า token อาจจะติด limit ให้เว้นช่วงสำหรับผู้ใช้ด้วย"*

**2 ทางที่ทำงาน**
- **อัตโนมัติ**: `cron_tick` (ยิงทุกนาที) เรียก `maybe_run()` → ช่วง 00:00–02:59 ถ้าวันนี้
  ยังไม่ได้ดึงก็เริ่ม · ช่วงเวลา 3 ชม. มีไว้ **ลองใหม่** ถ้ารอบแรกล้ม (ไม่ใช่ดึงหลายรอบ)
- **กดเอง**: ปุ่ม sync ในพาเนล "Meta (Facebook)" → `can_manual()` ต้องผ่านก่อน

**ทำไมกันกดถี่** — token เดียวใช้ทั้งดึงยอด ทั้งอ่านแชท ทั้งโฆษณา ถ้าใครกดรัวจนโควต้าเต็ม
Meta จะพัก *ทุกงาน* ของ token นั้น (รอบเที่ยงคืนก็ล้มตามไปด้วย) · ตัวเลขโควต้าอ่านจาก
header ที่ Meta ส่งมาจริง (`meta.last_usage`) ไม่ได้เดาจากจำนวนครั้งที่กด

**งานหนัก → รันใน thread** — ดึงโพสต์ 90 วันย้อนหลังใช้หลายสิบวินาที ถ้าทำในคำขอ
nginx จะตัดที่ 120 วิ (บทเรียนเดิมของรายงานรายวัน) และ cron_tick จะช้าจนงานอื่นเสีย
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from . import cache_store, meta

# ── ค่าตั้ง ─────────────────────────────────────────────────────────
POST_WINDOW_DAYS = 90        # ตามยอดโพสต์ย้อนหลังกี่วัน (โพสต์เก่ากว่านี้ยอดแทบไม่ขยับแล้ว)
ADS_LOOKBACK_DAYS = 3        # ดึงโฆษณาย้อนกี่วันมาทับ (Meta แก้ตัวเลขโฆษณาย้อนหลังได้)
# ★ 20 ก.ย.69 — ต้องขอทีละ 50 แถวเท่านั้น (เดิม 500 = ดึงโฆษณาไม่ได้เลยสักรอบ)
#   วัดจริงกับบัญชีที่ยิงแอดอยู่: limit=500 → Meta คิดนาน 101 วิแล้วโยน "An unknown error occurred"
#   (ไม่ใช่สิทธิ์/ไม่ใช่ลิมิต) · limit=50 → 13 วิ ได้ครบ · ตัวที่ทำให้ช้าคือฟิลด์ actions/reach
#   ซึ่งเราต้องใช้ จึงลดขนาดหน้าแทนการตัดฟิลด์
ADS_PAGE = 50
DAILY_WINDOW_HOURS = 3       # รอบเที่ยงคืน: เริ่มได้ถึง 02:59 (ไว้ลองใหม่ถ้ารอบแรกล้ม)
MANUAL_GAP_MIN = 15          # กด sync เองได้ห่างกันอย่างน้อยกี่นาที
USAGE_BLOCK_PCT = 75         # โควต้าใช้ไปเกินนี้ = ห้ามกด sync เอง (เผื่อไว้ให้รอบเที่ยงคืน)
USAGE_WINDOW_MIN = 60        # Meta นับโควต้าเป็นหน้าต่าง 1 ชม. — เลยนี้ถือว่าค่าเก่าหมดอายุ
LOCK_TTL_MIN = 20            # ล็อกกันรันซ้อน (ค้างนานกว่านี้ถือว่า thread ตายไปแล้ว)

STATUS_KEY = "meta_sync_last"
LOCK_KEY = "meta_sync_lock"
DAILY_KEY = "meta_sync_daily"

_POST_METRICS = ",".join([
    "post_clicks", "post_reactions_by_type_total", "post_video_views",
    "post_video_views_organic", "post_video_views_paid", "post_video_avg_time_watched",
    "post_video_complete_views_30s", "post_video_view_time",
])
_POST_FIELDS = ("id,created_time,message,permalink_url,status_type,attachments{media_type},"
                "reactions.summary(total_count).limit(0),comments.summary(total_count).limit(0),"
                "shares,insights.metric(%s)" % _POST_METRICS)
_AD_FIELDS = ("date_start,account_id,campaign_id,campaign_name,adset_id,adset_name,"
              "ad_id,ad_name,spend,impressions,reach,clicks,actions,cost_per_action_type")


# ── ตัวช่วย ────────────────────────────────────────────────────────
def _bkk_now() -> datetime:
    from .fetch_dashboard import bangkok_now
    return bangkok_now()


def _int(v) -> int:
    try:
        return int(float(v or 0))
    except (TypeError, ValueError):
        return 0


def _dt(s):
    """'2026-09-19T04:00:00+0000' → datetime (Meta ไม่ใส่ : ใน timezone)"""
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")
    except (TypeError, ValueError):
        return None


def _kv(key) -> dict:
    return (cache_store.get_kv(key) or {}).get("data") or {}


def _minutes_since(iso: str) -> float:
    try:
        t = datetime.fromisoformat(iso)
        return (timezone.now() - t).total_seconds() / 60.0
    except (TypeError, ValueError):
        return 1e9


def _raw(chunk) -> dict:
    """คำตอบดิบที่จะเก็บ — ★ ตัด `paging` ทิ้ง

    ลิงก์ `paging.next` ที่ Meta ส่งมา **มี access_token ฝังอยู่ใน URL**
    ถ้าเก็บทั้งก้อน token จะไปนอนในฐานข้อมูล และโผล่ในหน้า "ฐานข้อมูล (SQL)" /
    ไฟล์ export (ตัวกรองข้อมูลส่วนบุคคลของเรากรองแค่ LINE id ไม่ได้กรอง token ของ Meta)
    """
    # ★ ต้องไล่ทุกชั้น — `paging` ไม่ได้อยู่แค่ชั้นนอก ยังซ้อนอยู่ใน `insights`/`comments`
    #   ของ *ทุกโพสต์* (เจอตอนทดสอบ: ตัดแค่ชั้นนอกแล้ว token ยังหลุด 2 แถว)
    if isinstance(chunk, dict):
        return {k: _raw(v) for k, v in chunk.items() if k != "paging"}
    if isinstance(chunk, list):
        return [_raw(v) for v in chunk]
    return chunk


# ── ล็อก ──────────────────────────────────────────────────────────
def _locked() -> dict:
    """ล็อกที่ยังไม่หมดอายุ (ไม่มี = {})"""
    lk = _kv(LOCK_KEY)
    if lk.get("started") and _minutes_since(lk["started"]) < LOCK_TTL_MIN:
        return lk
    return {}


def _lock(trigger, by) -> bool:
    if _locked():
        return False
    cache_store.set_kv(LOCK_KEY, {"started": timezone.now().isoformat(),
                                  "trigger": trigger, "by": by})
    return True


def _unlock():
    cache_store.set_kv(LOCK_KEY, {})


def _touch():
    """ต่ออายุล็อกระหว่างงานยาว — รอบแรกของแชท Messenger อาจยาว 10+ นาที
    ถ้าไม่ต่อ ล็อกหมดอายุกลางทาง แล้วรอบถัดไปของ cron จะเริ่มซ้อนขึ้นมา"""
    lk = _kv(LOCK_KEY)
    if lk:
        lk["started"] = timezone.now().isoformat()
        cache_store.set_kv(LOCK_KEY, lk)


# ── ดึงยอดโพสต์ ─────────────────────────────────────────────────
def sync_posts(trigger: str, snap_date, taken_at) -> dict:
    """ยอดสะสมของทุกโพสต์ในเพจของเรา (ย้อน POST_WINDOW_DAYS วัน) → 1 แถว/โพสต์"""
    from dashboard.models import MetaPostSnapshot, MetaRaw

    cutoff = taken_at - timedelta(days=POST_WINDOW_DAYS)
    out = {"pages": {}, "snapshots": 0, "raw": 0, "errors": []}
    for pid in sorted(meta.pages()):
        try:
            pt = meta.page_token(pid)
        except meta.MetaError as e:
            out["errors"].append("เพจ %s: ขอ page token ไม่ได้ (%s)" % (pid, str(e)[:80]))
            continue
        rows, stop = [], False
        try:
            for chunk in meta.paged("/%s/posts" % pid, _token=pt, fields=_POST_FIELDS, limit=50):
                MetaRaw.objects.create(kind="posts", ref_id=pid, trigger=trigger, data=_raw(chunk))
                out["raw"] += 1
                for p in (chunk.get("data") or []):
                    ct = _dt(p.get("created_time"))
                    if ct and ct < cutoff:      # เรียงใหม่→เก่า เจอเก่ากว่าเกณฑ์ = จบ
                        stop = True
                        break
                    rows.append(_post_row(p, pid, trigger, snap_date, taken_at, ct))
                if stop:
                    break
        except meta.MetaError as e:
            out["errors"].append("เพจ %s: %s" % (pid, str(e)[:120]))
        if rows:
            # ★ 20 ก.ย.69 — รอบ cron ของวันเดียวกัน "รันซ้ำได้ ไม่เบิ้ล"
            #   เจอจริงคืน 19→20/09: gunicorn ถูกรีสตาร์ตกลางรอบ → thread ตาย → cron เริ่มรอบใหม่
            #   ได้ **3 ชุดของวันเดียวกัน (3,429 แถวแทนที่จะเป็น 1,143)** · ฝั่งอ่านเลือกแถวล่าสุดอยู่แล้ว
            #   จึงไม่ทำให้ตัวเลขผิด แต่ตารางบวม 3 เท่าโดยไม่มีประโยชน์
            #   → ลบชุด cron ของวันนั้น/เพจนั้นก่อนเขียนใหม่ (กติกาเดียวกับฝั่ง TikTok)
            with transaction.atomic():
                if trigger == "cron":
                    MetaPostSnapshot.objects.filter(page_id=pid, snap_date=snap_date,
                                                    trigger="cron").delete()
                MetaPostSnapshot.objects.bulk_create(rows, batch_size=500)
        out["pages"][pid] = len(rows)
        out["snapshots"] += len(rows)
    return out


def _post_row(p, pid, trigger, snap_date, taken_at, ct):
    from dashboard.models import MetaPostSnapshot

    # ★ Meta ส่ง metric วิดีโอมา **2 ชุด**: `period=lifetime` (ยอดสะสม) กับ `period=day`
    #   (รายวันย้อนหลังไม่กี่วัน) ชื่อเดียวกัน — เดิมเก็บเป็น dict ตัวหลังทับตัวแรก
    #   ได้ค่าของ "วันเก่าสุดใน series" ซึ่งมักเป็น 0 → วิวเป็น 0 ทุกโพสต์ (เจอตอนทดสอบ)
    #   ตารางนี้คือยอดสะสม จึงเอาเฉพาะ lifetime · ชุด day ยังอยู่ครบใน raw
    ins = {}
    for i in ((p.get("insights") or {}).get("data") or []):
        if (i.get("period") or "lifetime") != "lifetime":
            continue
        ins[i.get("name")] = (i.get("values") or [{}])[0].get("value")
    att = ((p.get("attachments") or {}).get("data") or [{}])[0]
    rbt = ins.get("post_reactions_by_type_total")
    return MetaPostSnapshot(
        taken_at=taken_at, snap_date=snap_date, trigger=trigger,
        page_id=pid, post_id=str(p.get("id") or ""),
        post_type=(att.get("media_type") or p.get("status_type") or "")[:32],
        created_time=ct, permalink=(p.get("permalink_url") or "")[:300],
        message=(p.get("message") or "").replace("\n", " ")[:200],
        reactions=_int(((p.get("reactions") or {}).get("summary") or {}).get("total_count")),
        reactions_by_type=rbt if isinstance(rbt, dict) else {},
        comments=_int(((p.get("comments") or {}).get("summary") or {}).get("total_count")),
        shares=_int((p.get("shares") or {}).get("count")),
        clicks=_int(ins.get("post_clicks")),
        video_views=_int(ins.get("post_video_views")),
        video_views_organic=_int(ins.get("post_video_views_organic")),
        video_views_paid=_int(ins.get("post_video_views_paid")),
        video_avg_watch_ms=_int(ins.get("post_video_avg_time_watched")),
        video_complete_30s=_int(ins.get("post_video_complete_views_30s")),
        video_view_time_ms=_int(ins.get("post_video_view_time")),
    )


# ── ดึงผลโฆษณา ─────────────────────────────────────────────────
# ═══════════ ★ 21 ก.ย.69 — ยอด "ระดับเพจ" ที่ Facebook รายงานเอง ═══════════
#  เจ้าของถาม: *"วันที่ 10 มี 15 ล้าน ทำไมวันที่ 20 มีแค่ 1 หมื่น 3 · มันจะเก็บไม่ครบ"*
#
#  ตัวเลขที่เรามีเดิมคือ **ผลรวมวิววิดีโอรายโพสต์ที่ดึงมาจากฟีด** ซึ่งตอบไม่ได้ว่า
#  "ขาดอะไรไปไหม" (ฟีดอาจไม่มีรีลส์ · รูป/สเตตัสไม่มีตัวเลขวิว · นิยาม "วิว" ของ
#  Business Suite กว้างกว่ามาก) → **ดึงยอดที่ Facebook สรุปให้เองระดับเพจมาวางเทียบ**
#  แล้วช่องว่างจะกลายเป็นตัวเลขที่เห็นได้ ไม่ใช่เรื่องที่ต้องเถียงกัน
#
#  **ตัวนี้ไม่ต้องรอสะสมเหมือน snapshot** — Facebook ให้ย้อนหลังมาเลย (ปกติ ~30 วัน)
PAGE_LOOKBACK_DAYS = 30

#  แยกเป็น 2 ชุด เพราะ **Meta ปฏิเสธทั้งคำขอถ้ามี metric ที่ใช้ไม่ได้แม้ตัวเดียว**
#  (เช่น `page_impressions` ถูกถอดตั้งแต่ v21) → ชุดหลักพังไม่ได้ · ชุดเสริมขาดได้
_PAGE_METRICS_CORE = ("page_video_views", "page_post_engagements")
_PAGE_METRICS_EXTRA = ("page_views_total", "page_daily_follows_unique",
                       "page_actions_post_reactions_like_total")
_PAGE_FIELD = {"page_video_views": "video_views", "page_post_engagements": "engagements",
               "page_views_total": "page_views", "page_daily_follows_unique": "follows",
               "page_actions_post_reactions_like_total": "likes"}


def _insight_date(end_time: str):
    """แปลง `end_time` ของ Meta → วันที่ของยอดนั้น

    Meta ส่ง "เวลาสิ้นสุดของช่วง" มา (เช่น `2026-09-21T07:00:00+0000` = เที่ยงคืนตามโซนของเพจ)
    ซึ่ง **เป็นยอดของวันก่อนหน้า** → ลบ 1 วันเสมอ (ไม่ว่าเพจตั้งโซนอะไร ลบแล้วได้วันที่ถูก)
    """
    d = _dt(end_time)
    return (d - timedelta(days=1)).date() if d else None


def sync_pages(days: int = PAGE_LOOKBACK_DAYS) -> dict:
    """ยอดรายวันระดับเพจ (Facebook สรุปให้เอง) → `dash_meta_page_daily` · upsert ทับได้

    เพจเดียวพังไม่ลากเพจอื่น · ชุด metric เสริมพัง = ข้ามเฉพาะชุดนั้น (ยอดหลักยังได้)
    """
    from dashboard.models import MetaPageDaily

    out = {"rows": 0, "pages": 0, "raw": 0, "errors": []}
    until = _bkk_now().date()
    since = until - timedelta(days=max(1, days))
    for pid in sorted(meta.pages()):
        try:
            pt = meta.page_token(pid)
        except Exception as e:
            out["errors"].append("เพจ %s: ขอ token ไม่ได้ (%s)" % (pid, str(e)[:80]))
            continue
        by_day = {}
        for group in (_PAGE_METRICS_CORE, _PAGE_METRICS_EXTRA):
            try:
                r = meta.get("/%s/insights" % pid, _token=pt, metric=",".join(group),
                             period="day", since=since.isoformat(), until=until.isoformat())
            except Exception as e:
                # ชุดหลักพัง = ต้องรู้ · ชุดเสริมพัง = เงียบได้ (บาง metric ถูกถอดตามเวอร์ชัน)
                if group is _PAGE_METRICS_CORE:
                    out["errors"].append("เพจ %s: %s" % (pid, str(e)[:110]))
                continue
            out["raw"] += 1 if _raw(r) else 0
            for item in (r.get("data") or []):
                f = _PAGE_FIELD.get(item.get("name") or "")
                if not f:
                    continue
                for v in (item.get("values") or []):
                    d = _insight_date(v.get("end_time") or "")
                    if d and since <= d <= until:
                        by_day.setdefault(d, {})[f] = _int(v.get("value"))
        for d, vals in by_day.items():
            MetaPageDaily.objects.update_or_create(page_id=pid, date=d, defaults=vals)
            out["rows"] += 1
        out["pages"] += 1
    return out

def sync_ads(trigger: str, days: int = ADS_LOOKBACK_DAYS) -> dict:
    """ผลโฆษณารายวันระดับ ad (Meta แยกวันให้เอง) → upsert ทับของเดิมในช่วงเดียวกัน"""
    from dashboard.models import MetaAdDaily, MetaRaw

    today = _bkk_now().date()
    rng = json.dumps({"since": (today - timedelta(days=max(1, days))).isoformat(),
                      "until": today.isoformat()})
    out = {"accounts": {}, "rows": 0, "raw": 0, "errors": []}
    for aid in sorted(meta.accounts()):
        n = 0
        try:
            for chunk in meta.paged("/act_%s/insights" % aid, level="ad", time_increment=1,
                                    time_range=rng, fields=_AD_FIELDS, limit=ADS_PAGE):
                MetaRaw.objects.create(kind="ads", ref_id="act_" + aid, trigger=trigger, data=_raw(chunk))
                out["raw"] += 1
                with transaction.atomic():
                    for a in (chunk.get("data") or []):
                        if not a.get("ad_id") or not a.get("date_start"):
                            continue
                        MetaAdDaily.objects.update_or_create(
                            date=a["date_start"], ad_id=str(a["ad_id"]),
                            defaults=dict(
                                account_id=str(a.get("account_id") or aid),
                                campaign_id=str(a.get("campaign_id") or ""),
                                campaign_name=(a.get("campaign_name") or "")[:300],
                                adset_id=str(a.get("adset_id") or ""),
                                adset_name=(a.get("adset_name") or "")[:300],
                                ad_name=(a.get("ad_name") or "")[:300],
                                spend=a.get("spend") or 0,
                                impressions=_int(a.get("impressions")),
                                reach=_int(a.get("reach")),
                                clicks=_int(a.get("clicks")),
                                actions=a.get("actions") or [],
                                cost_per_action=a.get("cost_per_action_type") or [],
                            ))
                        n += 1
        except meta.MetaError as e:
            out["errors"].append("act_%s: %s" % (aid, str(e)[:120]))
        out["accounts"][aid] = n
        out["rows"] += n
    return out


def trim_raw() -> int:
    """ลบข้อมูลดิบเก่ากว่า KEEP_DAYS — ไม่ลบ = กินดิสก์ ~4 GB/ปี"""
    from dashboard.models import MetaRaw
    try:
        cut = timezone.now() - timedelta(days=MetaRaw.KEEP_DAYS)
        return MetaRaw.objects.filter(fetched_at__lt=cut).delete()[0]
    except Exception:
        return 0


# ── ตัวรันหลัก ──────────────────────────────────────────────────
def run(trigger: str = "cron", by: str = "", ads_days: int | None = None) -> dict:
    """ดึงโพสต์ + โฆษณา 1 รอบ · คืนสรุป และเก็บไว้ที่ KV `meta_sync_last`"""
    from . import eventlog

    if not meta.is_configured():
        return {"ok": False, "error": "ยังไม่ได้ตั้ง Meta token / asset ของบริษัท"}
    if not _lock(trigger, by):
        return {"ok": False, "error": "มีการดึงข้อมูลอยู่แล้ว รอให้เสร็จก่อน", "busy": True}

    t0 = time.time()
    now = _bkk_now()
    # รอบเที่ยงคืน = ยอดสะสมของ "วันที่เพิ่งจบไป" · กดเอง = ยอดของวันนี้ (ณ ตอนกด)
    snap_date = (now.date() - timedelta(days=1)) if trigger == "cron" else now.date()
    res = {"trigger": trigger, "by": by, "snapDate": snap_date.isoformat(),
           "started": timezone.now().isoformat()}
    try:
        p = sync_posts(trigger, snap_date, timezone.now())
        a = sync_ads(trigger, ads_days or ADS_LOOKBACK_DAYS)
        # ยอดระดับเพจที่ Facebook สรุปเอง — ไว้เทียบว่าที่เรารวมจากโพสต์ครบไหม
        try:
            g = sync_pages()
        except Exception as e:
            g = {"rows": 0, "raw": 0, "errors": ["ยอดเพจพัง: %s" % str(e)[:160]]}
        # แชท Messenger (CRM raw) → checkout_fbchat / checkout_fbprofile
        # ทำ **หลังสุด** เพราะช้าสุดและมีเพดานต่อรอบ — ถ้ามันล้ม ยอดโพสต์/โฆษณาต้องได้ไปแล้ว
        try:
            from checkout.fb_sync import sync as _fb_sync
            _touch()
            m = _fb_sync(trigger, touch=_touch)
        except Exception as e:
            m = {"errors": ["แชท Messenger พัง: %s" % str(e)[:160]]}
        res.update(posts=p["snapshots"], pages=p["pages"], adsRows=a["rows"],
                   pageRows=g["rows"], accounts=a["accounts"], raw=p["raw"] + a["raw"] + g["raw"],
                   messenger={k: m.get(k) for k in ("threadsSeen", "threadsSynced", "unchanged",
                                                   "newMsgs", "profiles", "stopped", "sec")},
                   errors=p["errors"] + a["errors"] + g["errors"] + (m.get("errors") or []),
                   trimmed=trim_raw())
        res["ok"] = not res["errors"]
        res["postsOk"] = p["snapshots"] > 0 and not p["errors"]
    except Exception as e:                       # ห้ามทำให้ cron_tick ล้มตาม
        res.update(ok=False, postsOk=False, errors=["พังกลางทาง: %s" % str(e)[:200]])
    finally:
        _unlock()

    res["ms"] = int((time.time() - t0) * 1000)
    res["at"] = timezone.now().isoformat()
    res["usage"] = {"pct": meta.last_usage.get("pct", 0),
                    "regainMin": meta.last_usage.get("regain_min", 0)}
    cache_store.set_kv(STATUS_KEY, res)
    try:
        eventlog.log("meta_sync", name=trigger, target=by[:64], ok=res["ok"], ms=res["ms"],
                     posts=res.get("posts", 0), adsRows=res.get("adsRows", 0),
                     errors=res.get("errors", [])[:5], usage=res["usage"])
    except Exception:
        pass
    return res


def start_background(trigger: str, by: str = "") -> None:
    """รันใน thread — ปิด DB connection เองตอนจบ (thread ไม่ได้อยู่ในวงจร request)"""
    def _job():
        from django.db import connection
        try:
            run(trigger, by)
        finally:
            connection.close()
    threading.Thread(target=_job, daemon=True, name="meta-sync-%s" % trigger).start()


# ── รอบเที่ยงคืน (เรียกจาก cron_tick ทุกนาที) ─────────────────────
def maybe_run(now) -> str:
    """ถึงช่วงเที่ยงคืนและวันนี้ยังไม่ได้ดึง → เริ่มใน thread · คืนสิ่งที่ทำ ('' = ไม่ได้ทำ)

    กันซ้ำด้วย KV `meta_sync_daily` — จดว่าวันนี้ทำแล้ว **เฉพาะตอนดึงโพสต์สำเร็จ**
    (ล้ม = รอบถัดไปในช่วง 3 ชม. ลองใหม่ได้เอง หลังล็อกหมดอายุ)
    """
    if now.hour >= DAILY_WINDOW_HOURS or not meta.is_configured():
        return ""
    today = now.date().isoformat()
    if _kv(DAILY_KEY).get("date") == today:
        return ""
    last = _kv(STATUS_KEY)
    if (last.get("trigger") == "cron" and last.get("postsOk")
            and _minutes_since(last.get("at", "")) < DAILY_WINDOW_HOURS * 60):
        cache_store.set_kv(DAILY_KEY, {"date": today, "at": last.get("at")})
        return "done"
    if _locked():
        return "running"
    # ล้มไปแล้ว → เว้นช่วงก่อนลองใหม่ · ถ้าล้มเร็ว (เช่น token หมดอายุ) แล้วลองทุกนาที
    # จะยิงไป ~180 รอบใน 3 ชม. เปลืองโควต้าเปล่า ๆ และไม่มีทางสำเร็จอยู่ดี
    if (last.get("trigger") == "cron" and not last.get("postsOk")
            and _minutes_since(last.get("at", "")) < LOCK_TTL_MIN):
        return "retry-wait"
    start_background("cron", "เที่ยงคืน")
    return "started"


# ── ปุ่ม sync เอง ───────────────────────────────────────────────
def can_manual() -> dict:
    """กด sync เองได้ไหม — ไม่ได้ต้องบอก "ทำไม" และ "รออีกกี่นาที" ให้ผู้ใช้"""
    if not meta.is_configured():
        return {"ok": False, "reason": "ยังไม่ได้ตั้งค่า Meta token", "waitMin": 0}
    lk = _locked()
    if lk:
        return {"ok": False, "waitMin": 1,
                "reason": "กำลังดึงข้อมูลอยู่ (%s) รอให้เสร็จก่อน"
                          % ("รอบเที่ยงคืน" if lk.get("trigger") == "cron" else "มีคนกดไว้")}
    last = _kv(STATUS_KEY)
    ago = _minutes_since(last.get("at", ""))
    use = last.get("usage") or {}
    # โควต้า: ใช้ค่าจากรอบล่าสุด ถ้ายังอยู่ในหน้าต่าง 1 ชม. ของ Meta
    if ago < USAGE_WINDOW_MIN and (use.get("regainMin") or 0) > 0:
        return {"ok": False, "waitMin": int(use["regainMin"]),
                "reason": "Meta พักการเรียกของ token นี้อยู่ — ต้องรออีกประมาณ %d นาที"
                          % int(use["regainMin"])}
    if ago < USAGE_WINDOW_MIN and (use.get("pct") or 0) >= USAGE_BLOCK_PCT:
        w = max(1, int(USAGE_WINDOW_MIN - ago))
        return {"ok": False, "waitMin": w,
                "reason": "ใช้โควต้า Meta ไปแล้ว %d%% — ถ้ากดต่อ token อาจติดลิมิตจนรอบเที่ยงคืน"
                          "ดึงไม่ได้ · รออีกประมาณ %d นาที" % (use["pct"], w)}
    if ago < MANUAL_GAP_MIN:
        w = max(1, int(MANUAL_GAP_MIN - ago + 0.999))
        return {"ok": False, "waitMin": w,
                "reason": "เพิ่งดึงไปเมื่อ %d นาทีก่อน — กดถี่เกินไป token อาจติดลิมิต"
                          " กรุณาเว้นช่วงอีก %d นาที" % (int(ago), w)}
    return {"ok": True, "reason": "", "waitMin": 0}


def status() -> dict:
    """สรุปสำหรับพาเนล — ไม่ส่ง token ออกไป"""
    now = _bkk_now()
    last = _kv(STATUS_KEY)
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return {
        "configured": meta.is_configured(),
        "pages": sorted(meta.pages()),
        "accounts": ["act_" + a for a in sorted(meta.accounts())],
        "last": last,
        "running": _locked(),
        "daily": _kv(DAILY_KEY),
        "nextRun": nxt.strftime("%d/%m/%Y 00:00"),
        "manual": can_manual(),
        "limits": {"gapMin": MANUAL_GAP_MIN, "usagePct": USAGE_BLOCK_PCT,
                   "postDays": POST_WINDOW_DAYS, "adsDays": ADS_LOOKBACK_DAYS},
    }
