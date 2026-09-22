# -*- coding: utf-8 -*-
"""ดึงยอดวิว + engagement ของช่อง YouTube ทุกเที่ยงคืน — ก.ย.69

*"แล้วก็เรื่องคลิป YouTube เราจะทำยังไงดี มันมีตัวไหนที่สามารถดึงมาได้ไหม"*

**ง่ายกว่า TikTok/Meta มาก** — ยอดสาธารณะของ YouTube ขอด้วย **API key ใบเดียว**
ไม่ต้องให้เจ้าของช่องกดอนุญาต ไม่มี OAuth ไม่มี sandbox ไม่มี Target Users
→ ตัดปัญหา "เจ้าของช่องอยู่ต่างจังหวัด นัดเวลาไม่ตรงกัน" ที่เจอกับ TikTok ออกทั้งหมด

ต่อช่องได้:
- **ทั้งช่อง** → `dash_youtube_channel_snapshot` (ผู้ติดตาม · วิวรวม · จำนวนคลิป)
- **รายคลิป** → `dash_youtube_video_snapshot` (วิว · ไลก์ · คอมเมนต์ · ยาวกี่วินาที · Shorts ไหม)
- คำตอบดิบ → `dash_youtube_raw` (เก็บ 90 วัน)

**ยอดรายวัน = แถว cron วัน D ลบวัน D-1** (กติกาเดียวกับ Meta/TikTok) → ไหลเข้า
`dash_social_daily` เองผ่าน `social_daily.refresh_quiet()` ท้ายรอบ

⚠️ **YouTube ไม่ให้ยอดแชร์/ดิสไลก์** (ปิดดิสไลก์ตั้งแต่ปี 2021 · แชร์ไม่เคยมีใน Data API)
   → `shares` ของฝั่ง YouTube เป็น 0 เสมอ **ไม่ใช่บั๊ก**
⚠️ อยากได้ watch time / % ดูจบ / คนดูเป็นใคร ต้องใช้ **YouTube Analytics API** ซึ่งต้อง
   OAuth รายช่องเหมือน TikTok — ยังไม่ได้ทำ

**โควต้า**: ฟรี 10,000 หน่วย/วัน · รอบหนึ่งใช้ ~(3 + จำนวนคลิป/50 × 2) หน่วยต่อช่อง
= ช่องที่มี 500 คลิป ใช้ราว 25 หน่วย → 13 ช่องยังไม่ถึง 1% ของโควต้า
"""
from __future__ import annotations

import re
import threading
import time
from datetime import datetime, timedelta, timezone as dt_tz

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import cache_store
from .meta_sync import _bkk_now, _kv, _minutes_since

API = "https://www.googleapis.com/youtube/v3"
TIMEOUT = 25

VIDEO_WINDOW_DAYS = 90       # ตามยอดคลิปย้อนหลังกี่วัน (เก่ากว่านี้ยอดแทบไม่ขยับแล้ว)
MAX_PAGES = 40               # ต่อช่อง × 50 คลิป = สูงสุด 2,000 คลิปต่อรอบ
SHORT_MAX_SEC = 180          # YouTube นับ Shorts ที่ยาวไม่เกิน 3 นาที (ตั้งแต่ ต.ค. 2024)
DAILY_WINDOW_HOURS = 3       # รอบเที่ยงคืน: เริ่มได้ถึง 02:59 (ไว้ลองใหม่ถ้ารอบแรกล้ม)
MANUAL_GAP_MIN = 15
LOCK_TTL_MIN = 20

STATUS_KEY = "youtube_sync_last"
LOCK_KEY = "youtube_sync_lock"
DAILY_KEY = "youtube_sync_daily"

# PT1H2M3S → วินาที (YouTube ส่งความยาวคลิปมาเป็น ISO 8601 duration)
_DUR = re.compile(r"^P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")


class SyncError(RuntimeError):
    pass


def is_configured() -> bool:
    """★ ไม่ตั้งคีย์ หรือไม่ระบุช่อง = ปิดสนิท (กติกาเดียวกับ META_* / EXTERNAL_API_KEY)"""
    return bool(getattr(settings, "YOUTUBE_API_KEY", "")
                and getattr(settings, "YOUTUBE_CHANNELS", []))


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _dur_sec(s: str) -> int:
    m = _DUR.match((s or "").strip())
    if not m:
        return 0
    d, h, mi, sec = (_int(x) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + sec


def _dt(s: str):
    """"2026-09-20T10:00:00Z" → datetime (UTC) · แปลงไม่ได้คืน None ไม่ทำให้ทั้งรอบล้ม"""
    try:
        return datetime.fromisoformat((s or "").replace("Z", "+00:00")).astimezone(dt_tz.utc)
    except (TypeError, ValueError):
        return None


# ── ล็อก (แบบเดียวกับ meta_sync / tiktok_sync) ────────────────────────
def _locked() -> dict:
    lk = _kv(LOCK_KEY)
    return lk if lk.get("started") and _minutes_since(lk["started"]) < LOCK_TTL_MIN else {}


def _lock(trigger, by) -> bool:
    if _locked():
        return False
    cache_store.set_kv(LOCK_KEY, {"started": timezone.now().isoformat(),
                                  "trigger": trigger, "by": by})
    return True


def _touch():
    lk = _kv(LOCK_KEY)
    if lk:
        lk["started"] = timezone.now().isoformat()
        cache_store.set_kv(LOCK_KEY, lk)


def _unlock():
    cache_store.set_kv(LOCK_KEY, {})


# ── เรียก YouTube ────────────────────────────────────────────────
def _get(path: str, **params) -> dict:
    """ยิง Data API · ลองซ้ำเฉพาะ error ชั่วคราว (เน็ตสะดุด / 5xx)

    **ห้ามลองซ้ำตอนโควต้าหมดหรือคีย์ผิด** — ยิงซ้ำไม่ช่วยอะไร มีแต่เผาโควต้าเพิ่ม
    (บทเรียนเดียวกับ meta.get)
    """
    params["key"] = settings.YOUTUBE_API_KEY
    last = ""
    for attempt in range(3):
        try:
            r = requests.get("%s/%s" % (API, path.strip("/")), params=params, timeout=TIMEOUT)
        except requests.RequestException as e:
            last = "ต่อ YouTube ไม่ได้: %s" % str(e)[:120]
            if attempt < 2:
                time.sleep(2 + attempt * 4)
                continue
            raise SyncError(last)
        if r.status_code == 200:
            return r.json()
        try:
            err = (r.json() or {}).get("error", {})
            reason = ((err.get("errors") or [{}])[0]).get("reason", "")
            msg = err.get("message", "")
        except ValueError:
            reason, msg = "", r.text[:160]
        last = "HTTP %s %s: %s" % (r.status_code, reason, msg[:160])
        if r.status_code >= 500 and attempt < 2:      # ฝั่ง Google สะดุดชั่วคราว
            time.sleep(2 + attempt * 4)
            continue
        raise SyncError(last)
    raise SyncError(last)


def resolve_channel(ref: str) -> dict:
    """`@handle` หรือ `UCxxxx` → ข้อมูลช่อง + id ของเพลย์ลิสต์ "อัปโหลดทั้งหมด"

    ช่องเดียวกันเรียกด้วย @handle หรือ channelId ก็ได้ผลเท่ากัน — เก็บ `handle` ไว้ด้วย
    เพื่อให้ไล่ย้อนได้ว่าแถวนี้มาจากบรรทัดไหนใน `.env`
    """
    ref = (ref or "").strip()
    p = {"part": "snippet,statistics,contentDetails"}
    p["forHandle" if ref.startswith("@") else "id"] = ref
    j = _get("channels", **p)
    items = j.get("items") or []
    if not items:
        raise SyncError("หาช่อง %s ไม่เจอ (ตรวจ @handle ใน .env อีกที)" % ref)
    it = items[0]
    st = it.get("statistics") or {}
    return {
        "raw": j,
        "channel_id": it.get("id") or "",
        "handle": ref if ref.startswith("@") else ((it.get("snippet") or {}).get("customUrl") or ""),
        "title": (it.get("snippet") or {}).get("title") or "",
        "uploads": (((it.get("contentDetails") or {}).get("relatedPlaylists") or {})
                    .get("uploads") or ""),
        # ซ่อนจำนวนผู้ติดตามได้ → hiddenSubscriberCount = true แล้วไม่ส่งตัวเลขมา
        "subscribers": None if st.get("hiddenSubscriberCount") else _int(st.get("subscriberCount")),
        "views": _int(st.get("viewCount")),
        "videos": _int(st.get("videoCount")),
    }


def _video_ids(uploads: str, cutoff, raws: list) -> list:
    """ไล่เพลย์ลิสต์ "อัปโหลดทั้งหมด" (เรียงใหม่→เก่า) เก็บ id จนเจอคลิปเก่ากว่าเกณฑ์"""
    ids, page = [], None
    for _ in range(MAX_PAGES):
        p = {"part": "contentDetails", "playlistId": uploads, "maxResults": 50}
        if page:
            p["pageToken"] = page
        j = _get("playlistItems", **p)
        raws.append(("videos", j))
        stop = False
        for it in (j.get("items") or []):
            cd = it.get("contentDetails") or {}
            pub = _dt(cd.get("videoPublishedAt"))
            if pub and pub < cutoff:
                stop = True
                break
            vid = cd.get("videoId")
            if vid:
                ids.append(vid)
        page = j.get("nextPageToken")
        if stop or not page:
            break
    return ids


# ── ดึง 1 ช่อง ──────────────────────────────────────────────────────
def sync_channel(ref: str, trigger: str, snap_date, taken_at) -> dict:
    from dashboard.models import YouTubeChannelSnapshot, YouTubeRaw, YouTubeVideoSnapshot

    ch = resolve_channel(ref)
    cid = ch["channel_id"]
    raws = [("channels", ch["raw"])]
    cutoff = taken_at - timedelta(days=VIDEO_WINDOW_DAYS)

    rows = []
    if ch["uploads"]:
        ids = _video_ids(ch["uploads"], cutoff, raws)
        for i in range(0, len(ids), 50):            # videos.list รับได้ทีละ 50 id
            j = _get("videos", part="snippet,statistics,contentDetails",
                     id=",".join(ids[i:i + 50]))
            raws.append(("videos", j))
            for v in (j.get("items") or []):
                sn, st, cd = (v.get("snippet") or {}), (v.get("statistics") or {}), (v.get("contentDetails") or {})
                sec = _dur_sec(cd.get("duration"))
                rows.append(YouTubeVideoSnapshot(
                    taken_at=taken_at, snap_date=snap_date, trigger=trigger, channel_id=cid,
                    video_id=str(v.get("id") or "")[:64],
                    published_at=_dt(sn.get("publishedAt")),
                    title=((sn.get("title") or "").replace("\n", " "))[:300],
                    duration=sec, is_short=0 < sec <= SHORT_MAX_SEC,
                    view_count=_int(st.get("viewCount")),
                    like_count=_int(st.get("likeCount")),
                    comment_count=_int(st.get("commentCount"))))

    chan_row = YouTubeChannelSnapshot(
        taken_at=taken_at, snap_date=snap_date, trigger=trigger, channel_id=cid,
        handle=(ch["handle"] or "")[:120], title=(ch["title"] or "")[:200],
        subscriber_count=ch["subscribers"], view_count=ch["views"], video_count=ch["videos"])

    with transaction.atomic():
        if trigger == "cron":                       # รันซ้ำวันเดียวกันได้ ไม่เบิ้ล
            YouTubeVideoSnapshot.objects.filter(channel_id=cid, snap_date=snap_date,
                                                trigger="cron").delete()
            YouTubeChannelSnapshot.objects.filter(channel_id=cid, snap_date=snap_date,
                                                  trigger="cron").delete()
        if rows:
            YouTubeVideoSnapshot.objects.bulk_create(rows, batch_size=500)
        chan_row.save()
        YouTubeRaw.objects.bulk_create(
            [YouTubeRaw(kind=k, channel_id=cid, trigger=trigger, data=d) for k, d in raws],
            batch_size=50)
    return {"videos": len(rows), "title": ch["title"], "channelId": cid,
            "subscribers": ch["subscribers"]}


def trim_raw() -> int:
    from dashboard.models import YouTubeRaw
    try:
        cut = timezone.now() - timedelta(days=YouTubeRaw.KEEP_DAYS)
        return YouTubeRaw.objects.filter(fetched_at__lt=cut).delete()[0]
    except Exception:
        return 0


# ── ตัวรันหลัก ─────────────────────────────────────────────────────
def run(trigger: str = "cron", by: str = "") -> dict:
    from . import eventlog

    if not is_configured():
        return {"ok": False, "error": "ยังไม่ได้ตั้ง YOUTUBE_API_KEY / YOUTUBE_CHANNELS ใน .env"}
    if not _lock(trigger, by):
        return {"ok": False, "error": "มีการดึงข้อมูลอยู่แล้ว รอให้เสร็จก่อน", "busy": True}

    t0 = time.time()
    now = _bkk_now()
    snap_date = (now.date() - timedelta(days=1)) if trigger == "cron" else now.date()
    res = {"trigger": trigger, "by": by, "snapDate": snap_date.isoformat(),
           "channels": {}, "videos": 0, "errors": []}
    refs = list(settings.YOUTUBE_CHANNELS)
    try:
        taken = timezone.now()
        for ref in refs:
            try:
                r = sync_channel(ref, trigger, snap_date, taken)
                res["channels"][r["title"] or ref] = r["videos"]
                res["videos"] += r["videos"]
            except SyncError as e:
                # ช่องเดียวพังต้องไม่ลากช่องอื่นล้มตาม (กติกาเดียวกับ TikTok)
                res["errors"].append("%s: %s" % (ref, str(e)[:170]))
            _touch()
        res["channelCount"] = len(refs)
        res["trimmed"] = trim_raw()
        from . import social_daily
        res["daily"] = social_daily.refresh_quiet().get("youtube", 0)
        res["ok"] = not res["errors"]
        res["done"] = bool(refs) and len(res["errors"]) < len(refs)
    except Exception as e:
        res.update(ok=False, done=False,
                   errors=res["errors"] + ["พังกลางทาง: %s" % str(e)[:200]])
    finally:
        _unlock()
    res["ms"] = int((time.time() - t0) * 1000)
    res["at"] = timezone.now().isoformat()
    cache_store.set_kv(STATUS_KEY, res)
    try:
        eventlog.log("youtube_sync", name=trigger, target=by[:64], ok=res["ok"], ms=res["ms"],
                     channels=res.get("channelCount", 0), videos=res["videos"],
                     errors=res["errors"][:5])
    except Exception:
        pass
    return res


def start_background(trigger: str, by: str = "") -> None:
    def _job():
        from django.db import connection
        try:
            run(trigger, by)
        finally:
            connection.close()
    threading.Thread(target=_job, daemon=True, name="youtube-sync-%s" % trigger).start()


def maybe_run(now) -> str:
    """เรียกจาก cron_tick ทุกนาที — กติกาเดียวกับ meta_sync / tiktok_sync"""
    if now.hour >= DAILY_WINDOW_HOURS or not is_configured():
        return ""
    today = now.date().isoformat()
    if _kv(DAILY_KEY).get("date") == today:
        return ""
    last = _kv(STATUS_KEY)
    if (last.get("trigger") == "cron" and last.get("done")
            and _minutes_since(last.get("at", "")) < DAILY_WINDOW_HOURS * 60):
        cache_store.set_kv(DAILY_KEY, {"date": today, "at": last.get("at")})
        return "done"
    if _locked():
        return "running"
    if (last.get("trigger") == "cron" and not last.get("done")
            and _minutes_since(last.get("at", "")) < LOCK_TTL_MIN):
        return "retry-wait"                          # เพิ่งล้ม เว้นช่วงก่อนลองใหม่
    start_background("cron", "เที่ยงคืน")
    return "started"


def can_manual() -> dict:
    if not is_configured():
        return {"ok": False, "reason": "ยังไม่ได้ตั้ง YOUTUBE_API_KEY / YOUTUBE_CHANNELS",
                "waitMin": 0}
    if _locked():
        return {"ok": False, "reason": "กำลังดึงข้อมูลอยู่ รอให้เสร็จก่อน", "waitMin": 1}
    ago = _minutes_since(_kv(STATUS_KEY).get("at", ""))
    if ago < MANUAL_GAP_MIN:
        w = max(1, int(MANUAL_GAP_MIN - ago + 0.999))
        return {"ok": False, "waitMin": w,
                "reason": "เพิ่งดึงไปเมื่อ %d นาทีก่อน — เว้นอีก %d นาที" % (int(ago), w)}
    return {"ok": True, "reason": "", "waitMin": 0}


def status() -> dict:
    now = _bkk_now()
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return {"last": _kv(STATUS_KEY), "running": _locked(), "daily": _kv(DAILY_KEY),
            "nextRun": nxt.strftime("%d/%m/%Y 00:00"), "manual": can_manual(),
            "configured": is_configured(),
            "channels": list(getattr(settings, "YOUTUBE_CHANNELS", [])),
            "limits": {"gapMin": MANUAL_GAP_MIN, "videoDays": VIDEO_WINDOW_DAYS}}
