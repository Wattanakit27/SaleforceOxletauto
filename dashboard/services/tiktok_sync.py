# -*- coding: utf-8 -*-
"""ดึงยอดวิว + engagement ของทุกช่อง TikTok ที่เชื่อมแล้ว ทุกเที่ยงคืน — ก.ย.69

*"เรายังมีอีกสิบช่องที่ยังไม่เชื่อม เราต้องดึง engagement พร้อมยอดวิวมาจาก TikTok
 เหมือนกัน เช่น Facebook"*  → โครงเดียวกับ `meta_sync.py` ทุกอย่าง

ต่อช่องได้:
- **รายคลิป** (`video.list`) — วิว · ไลก์ · คอมเมนต์ · แชร์ (ยอดสะสม) → `dash_tiktok_video_snapshot`
- **ทั้งช่อง** (`user.info.stats` ถ้าเจ้าของช่องให้สิทธิ์นี้) — ผู้ติดตาม · ไลก์รวม · จำนวนคลิป
  → `dash_tiktok_account_snapshot`
- คำตอบดิบทั้งก้อน → `dash_tiktok_raw` (เก็บ 90 วัน)

TikTok ให้แต่ **ยอดสะสม** → ยอดรายวัน = แถว cron วัน D ลบวัน D-1 (เหมือน Facebook)

★ **บทเรียนจากรอบแรกของ Facebook (20 ก.ย.69)**: ระบบถูกรีสตาร์ทกลางทางตอน 00:07
  thread ที่ดึงอยู่ตายไปด้วย แล้วรอบถัดไปของ cron เริ่มใหม่ → ถ้าไม่ระวัง ยอดของวันเดียวกัน
  จะถูกจด 2 ชุด (ลบกันแล้วยอดรายวันเบิ้ล) · ที่นี่ **ลบแถว cron ของวันนั้นของช่องนั้นก่อนใส่ใหม่**
  ในธุรกรรมเดียว → รันซ้ำกี่รอบก็ได้ 1 แถวต่อคลิปต่อวัน
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone as dt_tz

import requests
from django.db import transaction
from django.utils import timezone

from . import cache_store
from .meta_sync import _bkk_now, _kv, _minutes_since

VIDEO_URL = "https://open.tiktokapis.com/v2/video/list/"
USER_URL = "https://open.tiktokapis.com/v2/user/info/"
TIMEOUT = 25

VIDEO_WINDOW_DAYS = 90       # ตามยอดคลิปย้อนหลังกี่วัน (เก่ากว่านี้ยอดแทบไม่ขยับแล้ว)
MAX_PAGES = 30               # ต่อช่อง × 20 คลิป = สูงสุด 600 คลิปต่อรอบ
DAILY_WINDOW_HOURS = 3       # รอบเที่ยงคืน: เริ่มได้ถึง 02:59 (ไว้ลองใหม่ถ้ารอบแรกล้ม)
MANUAL_GAP_MIN = 15
LOCK_TTL_MIN = 20

_VIDEO_FIELDS = ("id,create_time,title,video_description,duration,share_url,"
                 "view_count,like_count,comment_count,share_count")
_STAT_FIELDS = "open_id,follower_count,following_count,likes_count,video_count"

STATUS_KEY = "tiktok_sync_last"
LOCK_KEY = "tiktok_sync_lock"
DAILY_KEY = "tiktok_sync_daily"


class SyncError(RuntimeError):
    pass


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


# ── ล็อก (แบบเดียวกับ meta_sync) ─────────────────────────────────────
def _locked() -> dict:
    lk = _kv(LOCK_KEY)
    return lk if lk.get("started") and _minutes_since(lk["started"]) < LOCK_TTL_MIN else {}


def _lock(trigger, by) -> bool:
    if _locked():
        return False
    cache_store.set_kv(LOCK_KEY, {"started": timezone.now().isoformat(), "trigger": trigger, "by": by})
    return True


def _touch():
    lk = _kv(LOCK_KEY)
    if lk:
        lk["started"] = timezone.now().isoformat()
        cache_store.set_kv(LOCK_KEY, lk)


def _unlock():
    cache_store.set_kv(LOCK_KEY, {})


# ── เรียก TikTok ─────────────────────────────────────────────────
def _check(r) -> dict:
    """TikTok ตอบ error.code = "ok" เมื่อสำเร็จ · อย่างอื่น = โยน SyncError พร้อมข้อความ"""
    try:
        j = r.json()
    except ValueError:
        raise SyncError("TikTok ตอบไม่ใช่ JSON (HTTP %s)" % r.status_code)
    err = (j.get("error") or {}) if isinstance(j, dict) else {}
    code = err.get("code") or ("ok" if r.status_code == 200 else "http_%s" % r.status_code)
    if code != "ok":
        raise SyncError("%s: %s" % (code, (err.get("message") or "")[:160]))
    return j


def _videos_page(token: str, cursor=None) -> dict:
    body = {"max_count": 20}
    if cursor:
        body["cursor"] = cursor
    try:
        r = requests.post(VIDEO_URL, params={"fields": _VIDEO_FIELDS}, json=body,
                          headers={"Authorization": "Bearer " + token}, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise SyncError("ต่อ TikTok ไม่ได้: %s" % str(e)[:120])
    return _check(r)


def _user_stats(token: str) -> dict:
    try:
        r = requests.get(USER_URL, params={"fields": _STAT_FIELDS},
                         headers={"Authorization": "Bearer " + token}, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise SyncError("ต่อ TikTok ไม่ได้: %s" % str(e)[:120])
    return _check(r)


# ── ดึง 1 ช่อง ─────────────────────────────────────────────────────
def sync_account(acc, trigger: str, snap_date, taken_at) -> dict:
    from dashboard.models import TikTokAccountSnapshot, TikTokRaw, TikTokVideoSnapshot
    from . import tiktok_oauth

    token = tiktok_oauth.access_token_for(acc.open_id)       # ใกล้หมดก็ต่ออายุให้ก่อน
    cutoff = taken_at - timedelta(days=VIDEO_WINDOW_DAYS)
    out = {"videos": 0, "stats": False}

    stat_row = None
    if "user.info.stats" in (acc.scope or ""):
        j = _user_stats(token)
        TikTokRaw.objects.create(kind="user", open_id=acc.open_id, trigger=trigger, data=j)
        u = (j.get("data") or {}).get("user") or {}
        stat_row = TikTokAccountSnapshot(
            taken_at=taken_at, snap_date=snap_date, trigger=trigger, open_id=acc.open_id,
            follower_count=u.get("follower_count"), following_count=u.get("following_count"),
            likes_count=u.get("likes_count"), video_count=u.get("video_count"))

    rows, cursor = [], None
    for _ in range(MAX_PAGES):
        j = _videos_page(token, cursor)
        TikTokRaw.objects.create(kind="videos", open_id=acc.open_id, trigger=trigger, data=j)
        d = j.get("data") or {}
        stop = False
        for v in (d.get("videos") or []):
            ct = None
            if v.get("create_time"):
                try:
                    ct = datetime.fromtimestamp(int(v["create_time"]), tz=dt_tz.utc)
                except (TypeError, ValueError, OverflowError, OSError):
                    ct = None
            if ct and ct < cutoff:                      # เรียงใหม่→เก่า เจอเก่ากว่าเกณฑ์ = จบ
                stop = True
                break
            rows.append(TikTokVideoSnapshot(
                taken_at=taken_at, snap_date=snap_date, trigger=trigger, open_id=acc.open_id,
                video_id=str(v.get("id") or "")[:64], create_time=ct,
                title=((v.get("title") or v.get("video_description") or "").replace("\n", " "))[:300],
                share_url=(v.get("share_url") or "")[:300], duration=_int(v.get("duration")),
                view_count=_int(v.get("view_count")), like_count=_int(v.get("like_count")),
                comment_count=_int(v.get("comment_count")), share_count=_int(v.get("share_count"))))
        if stop or not d.get("has_more") or not d.get("cursor"):
            break
        cursor = d["cursor"]

    with transaction.atomic():
        if trigger == "cron":                           # รันซ้ำวันเดียวกันได้ ไม่เบิ้ล
            TikTokVideoSnapshot.objects.filter(open_id=acc.open_id, snap_date=snap_date,
                                               trigger="cron").delete()
            TikTokAccountSnapshot.objects.filter(open_id=acc.open_id, snap_date=snap_date,
                                                 trigger="cron").delete()
        if rows:
            TikTokVideoSnapshot.objects.bulk_create(rows, batch_size=500)
        if stat_row:
            stat_row.save()
    out["videos"] = len(rows)
    out["stats"] = stat_row is not None
    return out


def trim_raw() -> int:
    from dashboard.models import TikTokRaw
    try:
        cut = timezone.now() - timedelta(days=TikTokRaw.KEEP_DAYS)
        return TikTokRaw.objects.filter(fetched_at__lt=cut).delete()[0]
    except Exception:
        return 0


# ── ตัวรันหลัก ──────────────────────────────────────────────────
def run(trigger: str = "cron", by: str = "") -> dict:
    from dashboard.models import TikTokAccount
    from . import eventlog, tiktok_oauth

    if not tiktok_oauth.is_configured():
        return {"ok": False, "error": "ยังไม่ได้ตั้ง TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET"}
    if not _lock(trigger, by):
        return {"ok": False, "error": "มีการดึงข้อมูลอยู่แล้ว รอให้เสร็จก่อน", "busy": True}

    t0 = time.time()
    now = _bkk_now()
    snap_date = (now.date() - timedelta(days=1)) if trigger == "cron" else now.date()
    res = {"trigger": trigger, "by": by, "snapDate": snap_date.isoformat(),
           "accounts": {}, "videos": 0, "errors": []}
    try:
        accs = list(TikTokAccount.objects.filter(status=TikTokAccount.ACTIVE))
        taken = timezone.now()
        for acc in accs:
            name = acc.label or acc.display_name or acc.open_id[:10]
            try:
                r = sync_account(acc, trigger, snap_date, taken)
                res["accounts"][name] = r["videos"]
                res["videos"] += r["videos"]
            except (SyncError, tiktok_oauth.TikTokError) as e:
                # ช่องเดียวพัง (token ถูกยกเลิก ฯลฯ) ต้องไม่ลากช่องอื่นล้มตาม
                res["errors"].append("%s: %s" % (name, str(e)[:160]))
                if "access_token_invalid" in str(e) or "scope_not_authorized" in str(e):
                    acc.status, acc.last_error = acc.ERROR, str(e)[:300]
                    acc.save(update_fields=["status", "last_error"])
            _touch()
        res["channels"] = len(accs)
        res["trimmed"] = trim_raw()
        res["ok"] = not res["errors"]
        # อย่างน้อยหนึ่งช่องได้ยอด = ถือว่ารอบเที่ยงคืนวันนี้ทำแล้ว (ช่องที่พังดูใน errors)
        res["done"] = bool(accs) and len(res["errors"]) < len(accs)
    except Exception as e:
        res.update(ok=False, done=False, errors=res["errors"] + ["พังกลางทาง: %s" % str(e)[:200]])
    finally:
        _unlock()
    res["ms"] = int((time.time() - t0) * 1000)
    res["at"] = timezone.now().isoformat()
    cache_store.set_kv(STATUS_KEY, res)
    try:
        eventlog.log("tiktok_sync", name=trigger, target=by[:64], ok=res["ok"], ms=res["ms"],
                     channels=res.get("channels", 0), videos=res["videos"], errors=res["errors"][:5])
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
    threading.Thread(target=_job, daemon=True, name="tiktok-sync-%s" % trigger).start()


def maybe_run(now) -> str:
    """เรียกจาก cron_tick ทุกนาที — กติกาเดียวกับ meta_sync.maybe_run"""
    from dashboard.models import TikTokAccount
    from . import tiktok_oauth
    if now.hour >= DAILY_WINDOW_HOURS or not tiktok_oauth.is_configured():
        return ""
    today = now.date().isoformat()
    if _kv(DAILY_KEY).get("date") == today:
        return ""
    if not TikTokAccount.objects.filter(status=TikTokAccount.ACTIVE).exists():
        return ""                                      # ยังไม่มีช่องไหนเชื่อม
    last = _kv(STATUS_KEY)
    if (last.get("trigger") == "cron" and last.get("done")
            and _minutes_since(last.get("at", "")) < DAILY_WINDOW_HOURS * 60):
        cache_store.set_kv(DAILY_KEY, {"date": today, "at": last.get("at")})
        return "done"
    if _locked():
        return "running"
    if (last.get("trigger") == "cron" and not last.get("done")
            and _minutes_since(last.get("at", "")) < LOCK_TTL_MIN):
        return "retry-wait"
    start_background("cron", "เที่ยงคืน")
    return "started"


def can_manual() -> dict:
    from . import tiktok_oauth
    if not tiktok_oauth.is_configured():
        return {"ok": False, "reason": "ยังไม่ได้ตั้งค่า TikTok (client key / secret)", "waitMin": 0}
    if _locked():
        return {"ok": False, "reason": "กำลังดึงข้อมูลอยู่ รอให้เสร็จก่อน", "waitMin": 1}
    ago = _minutes_since(_kv(STATUS_KEY).get("at", ""))
    if ago < MANUAL_GAP_MIN:
        w = max(1, int(MANUAL_GAP_MIN - ago + 0.999))
        return {"ok": False, "waitMin": w,
                "reason": "เพิ่งดึงไปเมื่อ %d นาทีก่อน — กดถี่เกินไป token อาจติดลิมิต "
                          "กรุณาเว้นช่วงอีก %d นาที" % (int(ago), w)}
    return {"ok": True, "reason": "", "waitMin": 0}


def status() -> dict:
    from dashboard.models import TikTokAccount
    now = _bkk_now()
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return {"last": _kv(STATUS_KEY), "running": _locked(), "daily": _kv(DAILY_KEY),
            "nextRun": nxt.strftime("%d/%m/%Y 00:00"), "manual": can_manual(),
            "channels": TikTokAccount.objects.filter(status=TikTokAccount.ACTIVE).count(),
            "limits": {"gapMin": MANUAL_GAP_MIN, "videoDays": VIDEO_WINDOW_DAYS}}
