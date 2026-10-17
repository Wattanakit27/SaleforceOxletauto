# -*- coding: utf-8 -*-
"""หน้า "คอมเมนต์" ใน Connect — รวมคอมเมนต์จากทุกช่องทางไว้ที่เดียว · 17 ต.ค.69

เจ้าของสั่ง *"ระหว่าง กล่องแชทรวม กับ ห้องพัก Lead อยากให้เพิ่มหน้า Comment มาอีกหน้านึง
รวมคอมเม้นจากทุกช่องทาง FB TT(รออนุมัติ) YT"*

ดึงเองเป็นรอบ (`connect.tick` → `tick_bg()` ใน thread แยก) แล้วเก็บลง `checkout_socialcomment`:
- **Facebook** — ทุก `FB_EVERY_MIN` นาที · โพสต์ของเพจ (`/<page>/feed` ย้อน `POST_WINDOW_DAYS` วัน)
  + โพสต์โฆษณา (`/<page>/ads_posts` — คอมเมนต์ใต้โฆษณาไม่อยู่ใน feed) · **ผ่าน `meta.get()` เท่านั้น**
  (ด่านแยกบริษัท: เพจนอก `META_PAGE_IDS` ยิงไม่ออก) · ใช้ page token (สิทธิ์ `pages_read_user_content`)
  · ⚠️ ชื่อคนคอมเมนต์ Facebook อาจไม่มา (FB ปิดตัวตนตั้งแต่ 2018) → หน้าเว็บขึ้น "ผู้ใช้ Facebook"
  · โควต้า Meta เกิน `fb_sync.STOP_USAGE_PCT` = ข้ามรอบนี้ (เก็บโควต้าไว้ให้แชท Messenger)
- **YouTube** — ทุก `YT_EVERY_MIN` นาที · `commentThreads?allThreadsRelatedToChannelId=` 1 หน่วยต่อหน้า
  (ช่องละ 1–2 หน้า × 13 ช่อง × 96 รอบ/วัน ≈ 2,500 หน่วย จาก 10,000) · API key ใบเดียวกับ youtube_sync
  (⚠️ คีย์ล็อก IP ไว้ที่ VPS — รันในเครื่องได้ 403) · เห็นเฉพาะคอมเมนต์สาธารณะ (ที่รออนุมัติในช่องไม่มา)
- **TikTok** — รอ TikTok อนุมัติสิทธิ์อ่านคอมเมนต์ (Login Kit ที่ใช้ดึงยอดวิวไม่ให้คอมเมนต์) → ยังไม่มีแถว

1 แถว = คอมเมนต์ระดับบนสุด · คำตอบใต้คอมเมนต์เก็บแค่จำนวน + **เพจ/ช่องเราตอบแล้วหรือยัง** (`replied`)
"รอตอบ" = ยังไม่มีคำตอบจากเพจ/ช่องเรา + ยังไม่มีใครกด "จัดการแล้ว" + ไม่เก่ากว่า `WAIT_DAYS` วัน
คอมเมนต์ของเพจ/ช่องเราเองไม่เก็บ · เก่ากว่า `KEEP_DAYS` วันลบเองวันละครั้ง
"""
from __future__ import annotations

import threading
import time
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import SocialComment as SC

FB_EVERY_MIN = 10
YT_EVERY_MIN = 15
POST_WINDOW_DAYS = 60        # Facebook: ไล่โพสต์ย้อนหลังกี่วัน (โพสต์เก่ากว่านี้ไม่ไล่หาคอมเมนต์ใหม่)
FB_FEED_PAGES = 4            # × 25 โพสต์
FB_AD_PAGES = 2              # × 25 โพสต์โฆษณา
FB_COMMENTS_PER_POST = 50
YT_PAGES = 2                 # × 100 กระทู้ต่อช่อง
KEEP_DAYS = 90
WAIT_DAYS = 7                # "รอตอบ" นับเฉพาะคอมเมนต์ไม่เกินกี่วัน (เก่ากว่านี้ยังอยู่ใน "ทั้งหมด")
MANUAL_GAP_SEC = 120
LOCK_KEY = "comments_sync_lock"
LOCK_STALE_SEC = 15 * 60
STATE_KEY = "comments_sync"
BG = True                    # เทสต์ปิดไว้ (ไม่ให้มี thread วิ่งชนฐานข้อมูลทดสอบ)

PLATFORMS = (SC.FB, SC.YT, SC.TT)
TT_NOTE = "รอ TikTok อนุมัติสิทธิ์อ่านคอมเมนต์ — อนุมัติแล้วคอมเมนต์ TikTok จะขึ้นที่นี่"


class SyncError(RuntimeError):
    pass


# ─────────────────────────────────────────────────────────────
#  สถานะ / ล็อก (KV ใช้ร่วมทุก gunicorn worker)
# ─────────────────────────────────────────────────────────────
def _kv():
    from dashboard.models import KVStore
    return KVStore


def state() -> dict:
    kv = _kv().objects.filter(pk=STATE_KEY).first()
    return dict(kv.data or {}) if kv else {}


def _save_state(**parts) -> None:
    KV = _kv()
    with transaction.atomic():
        kv, _ = KV.objects.select_for_update().get_or_create(pk=STATE_KEY, defaults={"data": {}})
        d = dict(kv.data or {})
        for k, v in parts.items():
            d[k] = dict(d.get(k) or {}, **v) if isinstance(v, dict) else v
        kv.data = d
        kv.save(update_fields=["data", "updated_at"])


def _lock() -> bool:
    KV = _kv()
    now = timezone.now()
    try:
        with transaction.atomic():
            KV.objects.create(key=LOCK_KEY, data={"at": now.isoformat()})
        return True
    except IntegrityError:
        pass
    kv = KV.objects.filter(pk=LOCK_KEY).first()
    if not kv:
        return False
    if (now - kv.updated_at).total_seconds() < LOCK_STALE_SEC:
        return False
    # ค้างจากรอบที่ตายกลางทาง (worker ถูกรีสตาร์ท) → รับช่วงต่อ · เงื่อนไข updated_at เดิม = ชนะได้คนเดียว
    return bool(KV.objects.filter(pk=LOCK_KEY, updated_at=kv.updated_at)
                .update(data={"at": now.isoformat()}, updated_at=now))


def _unlock() -> None:
    _kv().objects.filter(pk=LOCK_KEY).delete()


def fb_on() -> bool:
    try:
        from dashboard.services import meta
        return meta.is_configured() and bool(meta.pages())
    except Exception:
        return False


def yt_on() -> bool:
    try:
        from dashboard.services import youtube_sync
        return youtube_sync.is_configured()
    except Exception:
        return False


def _due(kind: str, every_min: int, now) -> bool:
    at = parse_datetime(((state().get(kind) or {}).get("at")) or "")
    return not at or (now - at).total_seconds() >= every_min * 60 - 20


# ─────────────────────────────────────────────────────────────
#  เขียนลงตาราง — ดึงแถวเดิมทีเดียวทั้งก้อน (รอบหนึ่งเจอได้หลายพันคอมเมนต์ · ห้ามยิงทีละแถว)
# ─────────────────────────────────────────────────────────────
_UPD = ("account_name", "post_title", "post_url", "is_ad", "author_name", "author_pic", "text", "url",
        "like_count", "reply_count", "replied", "replied_at")


def _upsert(platform: str, items: list) -> dict:
    now = timezone.now()
    keep_from = now - timedelta(days=KEEP_DAYS)
    items = [x for x in items if x["created_at"] and x["created_at"] >= keep_from]
    seen = {}
    for x in items:                                  # id เดียวกันมา 2 ครั้ง (โพสต์ปกติ + โพสต์โฆษณาเดียวกัน)
        seen[x["ext_id"]] = x
    items = list(seen.values())
    new, upd = [], []
    ids = [x["ext_id"] for x in items]
    have = {}
    for i in range(0, len(ids), 500):
        for r in SC.objects.filter(platform=platform, ext_id__in=ids[i:i + 500]):
            have[r.ext_id] = r
    for x in items:
        r = have.get(x["ext_id"])
        if not r:
            new.append(SC(platform=platform, fetched_at=now, **x))
            continue
        changed = False
        for k in _UPD:
            if getattr(r, k) != x[k]:
                setattr(r, k, x[k])
                changed = True
        # รูปโพสต์ของ Facebook เป็นลิงก์มีอายุ (เปลี่ยนทุกครั้งที่ขอ) — ต่อให้วันละครั้ง ไม่เขียนทุกรอบ
        if changed or (x["post_thumb"] != r.post_thumb and (now - r.fetched_at).total_seconds() > 86400):
            r.post_thumb = x["post_thumb"]
            r.fetched_at = now
            upd.append(r)
    if new:
        SC.objects.bulk_create(new, batch_size=200, ignore_conflicts=True)
    if upd:
        SC.objects.bulk_update(upd, list(_UPD) + ["post_thumb", "fetched_at"], batch_size=200)
    return {"seen": len(items), "new": len(new), "updated": len(upd)}


def _dt(v):
    if not v:
        return None
    if isinstance(v, (int, float)):
        from datetime import datetime, timezone as dt_tz
        return datetime.fromtimestamp(v, tz=dt_tz.utc)
    d = parse_datetime(str(v).replace("+0000", "+00:00"))
    if d and timezone.is_naive(d):
        d = timezone.make_aware(d, timezone.utc)
    return d


def _cut(s, n):
    s = (s or "").strip()
    return s if len(s) <= n else s[:n - 1] + "…"


# ─────────────────────────────────────────────────────────────
#  Facebook
# ─────────────────────────────────────────────────────────────
_POST_FIELDS = ("id,message,story,created_time,permalink_url,full_picture,"
                "comments.order(reverse_chronological).limit(%d)"
                "{id,message,created_time,from,like_count,comment_count,permalink_url,attachment{type},"
                "comments.limit(25){from,created_time}}" % FB_COMMENTS_PER_POST)
_ATT = {"photo": "[รูป]", "sticker": "[สติกเกอร์]", "animated_image_share": "[GIF]", "video_inline": "[วิดีโอ]",
        "animated_image_video": "[GIF]", "share": "[ลิงก์]"}
_PAGE_NAME: dict = {}


def _page_name(pid: str, pt: str) -> str:
    hit = _PAGE_NAME.get(pid)
    if hit and time.time() - hit[1] < 6 * 3600:
        return hit[0]
    from dashboard.services import meta
    name = ""
    try:
        name = (meta.get("/" + pid, _token=pt, fields="name") or {}).get("name") or ""
    except Exception:
        pass
    _PAGE_NAME[pid] = (name, time.time())
    return name


def _fb_post_items(pid: str, pname: str, post: dict, is_ad: bool) -> list:
    title = (post.get("message") or post.get("story") or "").strip().split("\n")[0]
    out = []
    for c in ((post.get("comments") or {}).get("data") or []):
        frm = c.get("from") or {}
        if str(frm.get("id") or "") == pid:          # เพจเราคอมเมนต์เอง
            continue
        mine = [r for r in ((c.get("comments") or {}).get("data") or []) if str((r.get("from") or {}).get("id") or "") == pid]
        rat = sorted(_dt(r.get("created_time")) for r in mine if r.get("created_time"))
        text = (c.get("message") or "").strip() or _ATT.get(((c.get("attachment") or {}).get("type") or ""), "[ไฟล์แนบ]")
        out.append({
            "ext_id": str(c.get("id") or ""), "account_id": pid, "account_name": _cut(pname, 200),
            "post_id": str(post.get("id") or ""), "post_title": _cut(title, 300),
            "post_url": (post.get("permalink_url") or "")[:500], "post_thumb": (post.get("full_picture") or "")[:1000],
            "is_ad": is_ad,
            "author_id": str(frm.get("id") or "")[:120], "author_name": _cut(frm.get("name") or "", 200), "author_pic": "",
            "text": text, "url": (c.get("permalink_url") or post.get("permalink_url") or "")[:500],
            "created_at": _dt(c.get("created_time")),
            "like_count": int(c.get("like_count") or 0), "reply_count": int(c.get("comment_count") or 0),
            "replied": bool(mine), "replied_at": rat[0] if rat else None,
        })
    return [x for x in out if x["ext_id"]]


def sync_fb() -> dict:
    from dashboard.services import meta
    from .fb_sync import STOP_USAGE_PCT
    if (meta.last_usage.get("pct") or 0) >= STOP_USAGE_PCT:
        raise SyncError("โควต้า Meta เกิน %d%% — ข้ามรอบนี้ (เก็บไว้ให้แชท Messenger)" % STOP_USAGE_PCT)
    cutoff = timezone.now() - timedelta(days=POST_WINDOW_DAYS)
    items, errs = [], []
    for pid in sorted(meta.pages()):
        try:
            pt = meta.page_token(pid)
        except Exception as e:
            errs.append("เพจ %s: %s" % (pid, str(e)[:100]))
            continue
        pname = _page_name(pid, pt)
        try:
            stop = False
            for d in meta.paged("/%s/feed" % pid, _token=pt, max_pages=FB_FEED_PAGES, fields=_POST_FIELDS, limit=25):
                for p in d.get("data") or []:
                    at = _dt(p.get("created_time"))
                    if at and at < cutoff:
                        stop = True
                        break
                    items += _fb_post_items(pid, pname, p, False)
                if stop:
                    break
        except Exception as e:
            errs.append("โพสต์เพจ %s: %s" % (pname or pid, str(e)[:120]))
        try:                                         # คอมเมนต์ใต้โฆษณา (โพสต์โฆษณาไม่อยู่ใน feed)
            for d in meta.paged("/%s/ads_posts" % pid, _token=pt, max_pages=FB_AD_PAGES, fields=_POST_FIELDS,
                                limit=25, include_inline_create="true"):
                for p in d.get("data") or []:
                    items += _fb_post_items(pid, pname, p, True)
        except Exception as e:
            errs.append("โพสต์โฆษณาเพจ %s: %s" % (pname or pid, str(e)[:120]))
    res = _upsert(SC.FB, items)
    if errs:
        res["error"] = " · ".join(errs)[:400]
    return res


# ─────────────────────────────────────────────────────────────
#  YouTube
# ─────────────────────────────────────────────────────────────
def _yt_channels() -> list:
    """[(channel_id, ชื่อช่อง)] — อ่านจากตาราง snapshot ของรอบเที่ยงคืนก่อน (ไม่เปลืองโควต้า)
    ยังไม่เคยมีรอบเที่ยงคืน = ถามช่องจาก `YOUTUBE_CHANNELS` ทีละช่อง (1 หน่วย)"""
    from dashboard.models import YouTubeChannelSnapshot as CS
    out = {}
    for r in CS.objects.filter(taken_at__gte=timezone.now() - timedelta(days=7)).order_by("-taken_at") \
            .values("channel_id", "title"):
        out.setdefault(r["channel_id"], r["title"])
    if out:
        return list(out.items())
    from dashboard.services import youtube_sync as Y
    for ref in list(getattr(settings, "YOUTUBE_CHANNELS", None) or []):
        try:
            c = Y.resolve_channel(ref)
            out.setdefault(c["channel_id"], c["title"])
        except Exception:
            continue
    return list(out.items())


def _yt_titles(vids: list) -> dict:
    from dashboard.models import YouTubeVideoSnapshot as VS
    out = {}
    for r in VS.objects.filter(video_id__in=list(set(vids))[:2000]).order_by("-taken_at").values("video_id", "title"):
        out.setdefault(r["video_id"], r["title"])
    return out


def _yt_items(cid: str, cname: str, threads: list) -> list:
    out = []
    for it in threads:
        sn = it.get("snippet") or {}
        top = sn.get("topLevelComment") or {}
        ts = top.get("snippet") or {}
        if ((ts.get("authorChannelId") or {}).get("value") or "") == cid:   # ช่องเราคอมเมนต์เอง
            continue
        vid = sn.get("videoId") or ts.get("videoId") or ""
        reps = ((it.get("replies") or {}).get("comments") or [])
        mine = [r for r in reps if (((r.get("snippet") or {}).get("authorChannelId") or {}).get("value") or "") == cid]
        rat = sorted(_dt((r.get("snippet") or {}).get("publishedAt")) for r in mine if (r.get("snippet") or {}).get("publishedAt"))
        tid = str(it.get("id") or top.get("id") or "")
        out.append({
            "ext_id": tid, "account_id": cid, "account_name": _cut(cname, 200),
            "post_id": vid, "post_title": "",
            "post_url": ("https://www.youtube.com/watch?v=%s" % vid) if vid else "",
            "post_thumb": ("https://i.ytimg.com/vi/%s/mqdefault.jpg" % vid) if vid else "",
            "is_ad": False,
            "author_id": ((ts.get("authorChannelId") or {}).get("value") or "")[:120],
            "author_name": _cut(ts.get("authorDisplayName") or "", 200),
            "author_pic": (ts.get("authorProfileImageUrl") or "")[:1000],
            "text": (ts.get("textOriginal") or ts.get("textDisplay") or "").strip(),
            "url": ("https://www.youtube.com/watch?v=%s&lc=%s" % (vid, tid)) if vid else "",
            "created_at": _dt(ts.get("publishedAt")),
            "like_count": int(ts.get("likeCount") or 0), "reply_count": int(sn.get("totalReplyCount") or 0),
            "replied": bool(mine), "replied_at": rat[0] if rat else None,
        })
    return [x for x in out if x["ext_id"]]


def sync_yt() -> dict:
    from dashboard.services import youtube_sync as Y
    keep_from = timezone.now() - timedelta(days=KEEP_DAYS)
    items, errs = [], []
    for cid, cname in _yt_channels():
        try:
            tok = ""
            for _ in range(YT_PAGES):
                p = {"part": "snippet,replies", "allThreadsRelatedToChannelId": cid, "maxResults": 100,
                     "order": "time", "textFormat": "plainText"}
                if tok:
                    p["pageToken"] = tok
                j = Y._get("commentThreads", **p)
                got = _yt_items(cid, cname, j.get("items") or [])
                items += got
                tok = j.get("nextPageToken") or ""
                oldest = min((x["created_at"] for x in got if x["created_at"]), default=None)
                if not tok or (oldest and oldest < keep_from):
                    break
        except Exception as e:
            errs.append("ช่อง %s: %s" % (cname or cid, str(e)[:120]))
    titles = _yt_titles([x["post_id"] for x in items if x["post_id"]])
    for x in items:
        x["post_title"] = _cut(titles.get(x["post_id"], ""), 300)
    res = _upsert(SC.YT, items)
    if errs:
        res["error"] = " · ".join(errs)[:400]
    return res


# ─────────────────────────────────────────────────────────────
#  รอบดึง
# ─────────────────────────────────────────────────────────────
_RUNNERS = {SC.FB: sync_fb, SC.YT: sync_yt}


def run(kinds=None, trigger: str = "cron") -> dict:
    kinds = [k for k in (kinds or (SC.FB, SC.YT)) if k in _RUNNERS]
    if not _lock():
        return {"skipped": "กำลังดึงอยู่"}
    out = {}
    try:
        for k in kinds:
            t0 = time.time()
            try:
                r = _RUNNERS[k]()
                out[k] = dict(r, ok=not r.get("error"))
            except Exception as e:
                out[k] = {"ok": False, "error": str(e)[:300]}
            out[k].update(at=timezone.now().isoformat(), sec=round(time.time() - t0, 1), trigger=trigger)
            _save_state(**{k: out[k]})
    finally:
        _unlock()
    return out


def _start(kinds, trigger: str) -> None:
    def _work():
        try:
            run(kinds, trigger)
        finally:
            try:
                from django.db import connection
                connection.close()
            except Exception:
                pass
    threading.Thread(target=_work, daemon=True).start()


def tick_bg(now=None) -> dict:
    """เรียกจาก connect.tick ทุกนาที — ถึงรอบของช่องทางไหนก็เริ่มดึงใน thread แยก (ไม่หน่วง cron)"""
    now = now or timezone.now()
    kinds = []
    if fb_on() and _due(SC.FB, FB_EVERY_MIN, now):
        kinds.append(SC.FB)
    if yt_on() and _due(SC.YT, YT_EVERY_MIN, now):
        kinds.append(SC.YT)
    from .connect import BG_FILL               # เทสต์ของ Connect ปิดตัวนี้ไว้ — ห้ามมี thread ยิงเน็ตจริงระหว่างเทสต์
    if not kinds or not BG or not BG_FILL:
        return {}
    if _kv().objects.filter(pk=LOCK_KEY, updated_at__gte=now - timedelta(seconds=LOCK_STALE_SEC)).exists():
        return {}
    _start(kinds, "cron")
    return {"started": kinds}


def request_sync(by: str = "") -> tuple[bool, str]:
    """ปุ่ม "ดึงตอนนี้" (แอดมิน) — ห่างกันอย่างน้อย MANUAL_GAP_SEC"""
    kinds = [k for k, on in ((SC.FB, fb_on()), (SC.YT, yt_on())) if on]
    if not kinds:
        return False, "ยังไม่ได้ตั้งค่าการเชื่อมต่อ Facebook / YouTube"
    st = state()
    last = parse_datetime(st.get("manual_at") or "")
    if last and (timezone.now() - last).total_seconds() < MANUAL_GAP_SEC:
        return False, "เพิ่งดึงไปเมื่อสักครู่ — รอ %d นาทีแล้วค่อยกดใหม่" % max(1, MANUAL_GAP_SEC // 60)
    if _kv().objects.filter(pk=LOCK_KEY, updated_at__gte=timezone.now() - timedelta(seconds=LOCK_STALE_SEC)).exists():
        return False, "กำลังดึงอยู่ — รอสักครู่"
    _save_state(manual_at=timezone.now().isoformat(), manual_by=by)
    if BG:
        _start(kinds, "manual")
    else:
        run(kinds, "manual")
    return True, "กำลังดึงคอมเมนต์ใหม่ — รอสักครู่แล้วรายการจะอัปเดตเอง"


_CLEAN = {"day": ""}


def cleanup_daily() -> int | None:
    today = timezone.localdate().isoformat()
    if _CLEAN["day"] == today:
        return None
    _CLEAN["day"] = today
    n, _ = SC.objects.filter(created_at__lt=timezone.now() - timedelta(days=KEEP_DAYS)).delete()
    return n


# ─────────────────────────────────────────────────────────────
#  หน้าเว็บ
# ─────────────────────────────────────────────────────────────
def _wait_q(now=None) -> Q:
    now = now or timezone.now()
    return Q(replied=False, done_at__isnull=True, created_at__gte=now - timedelta(days=WAIT_DAYS))


def wait_count() -> int:
    return SC.objects.filter(_wait_q()).count()


def row_json(r: SC) -> dict:
    return {
        "id": r.id, "platform": r.platform, "account": r.account_name,
        "postTitle": r.post_title, "postUrl": r.post_url, "thumb": r.post_thumb, "isAd": r.is_ad,
        "author": r.author_name, "authorPic": r.author_pic, "text": r.text, "url": r.url,
        "at": timezone.localtime(r.created_at).isoformat(timespec="seconds"),
        "likes": r.like_count, "replies": r.reply_count, "replied": r.replied,
        "done": bool(r.done_at), "doneBy": r.done_by,
    }


def sources() -> dict:
    st = state()
    def one(k, on):
        s = st.get(k) or {}
        return {"on": on, "at": s.get("at") or "", "ok": s.get("ok"), "error": s.get("error") or ""}
    return {SC.FB: one(SC.FB, fb_on()), SC.YT: one(SC.YT, yt_on()),
            SC.TT: {"on": False, "pending": True, "note": TT_NOTE}}


def list_json(platform: str = "", status: str = "wait", q: str = "", limit: int = 60) -> dict:
    now = timezone.now()
    limit = max(20, min(int(limit or 60), 300))
    base = SC.objects.all()
    if platform in PLATFORMS:
        base = base.filter(platform=platform)
    if status == "wait":
        base = base.filter(_wait_q(now))
    elif status == "done":
        base = base.filter(Q(replied=True) | Q(done_at__isnull=False))
    q = (q or "").strip()
    if q:
        base = base.filter(Q(text__icontains=q) | Q(author_name__icontains=q) | Q(post_title__icontains=q)
                           | Q(account_name__icontains=q))
    rows = list(base.order_by("-created_at", "-id")[:limit + 1])
    counts = {p: 0 for p in PLATFORMS}
    for r in SC.objects.filter(_wait_q(now)).values("platform").annotate(n=Count("id")):
        counts[r["platform"]] = r["n"]
    counts["all"] = sum(counts[p] for p in PLATFORMS)
    return {"rows": [row_json(r) for r in rows[:limit]], "more": len(rows) > limit, "counts": counts,
            "sources": sources(), "waitDays": WAIT_DAYS,
            "every": {SC.FB: FB_EVERY_MIN, SC.YT: YT_EVERY_MIN}}


def set_done(cid: int, by: str, on: bool = True) -> SC | None:
    r = SC.objects.filter(pk=cid).first()
    if not r:
        return None
    r.done_at, r.done_by = (timezone.now(), (by or "")[:80]) if on else (None, "")
    r.save(update_fields=["done_at", "done_by"])
    return r
