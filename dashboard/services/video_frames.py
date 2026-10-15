# -*- coding: utf-8 -*-
"""ภาพทีละวินาทีของวิดีโอ Facebook — วางใต้กราฟ "คนดูหลุดตรงไหน" (15 ต.ค.69 · เจ้าของขอ)

*"มี screenshot ของแต่ละเฟรมต่อหนึ่งวิ และเน้นแบบนี้"* — ดูกราฟแล้วต้องเห็นทันทีว่าวินาทีที่คนหลุด
ในคลิปกำลังโชว์อะไรอยู่

★★ **ปิดอยู่ (`ENABLED = False`)** — เจ้าของสั่ง 15 ต.ค.69 ค่ำ *"ไม่ต้องดาวน์โหลดวิดีโอ เราแค่แปะลิงก์ก็พอ
แล้วก็เอารูปหน้าปกของวิดีโอมาก็พอจะได้ประหยัดพื้นที่"* → หน้าคลิปใช้รูปปก (`covers`) + ลิงก์ไป Facebook แทน
· ปิดแล้วไม่มีอะไรโหลดวิดีโอเลย (ensure/for_detail/prefetch/start_prefetch คืนทันที) · ภาพเก่าลบด้วย `purge()`
  (`manage.py meta_frames --purge`) · โค้ดเก็บไว้ ถ้าวันหน้าอยากเปิดกลับ = ตั้ง ENABLED = True

(เดิม) **ทำให้ 2 กลุ่ม** — กราฟคนดูค้างยังมีทุกคลิปเหมือนเดิม
1. **ยิงแอดและวิวสูงสุด `TOP_N` อันดับ** — *"Screenshot ทำแค่ตัวที่ยิง Ads แล้วมียอดวิวเยอะ 20-30 คลิปก็พอ"*
2. **คลิปใหม่ที่ลงภายใน `NEW_DAYS` วัน** — *"เมื่อมีคลิปใหม่มาวิเคราะห์ auto เองเลย และสกรีนช็อตเองเลยนะ"*
· คลิปหนึ่งต้องโหลดไฟล์วิดีโอ ~15 MB แล้วตัดภาพด้วย ffmpeg ~10 วิ · ทำทุกคลิป (~860 คลิป) กินเน็ต/ดิสก์เปล่าๆ
· **ทำเองไม่ต้องรอใครเปิด**: ทุกชั่วโมง (`meta_sync.watch_videos`) + ต่อท้ายรอบเที่ยงคืน (`start_prefetch`) · ทีละคลิป
· คลิปนอกกลุ่ม = ไม่ทำ (`for_detail` คืน state "skip") · หลุดกลุ่มเกิน PRUNE_GRACE_DAYS วัน = ลบภาพ (`prune`)
· ผลการทำภาพจดลงตาราง `dash_meta_video_retention` (frames_n / frames_at / frames_reason / frames_error)

ไฟล์อยู่ที่ `MEDIA_ROOT/frames/meta/<post id>/001.jpg …` (ไฟล์ที่ 1 = วินาทีที่ 0) + `info.json`
· เป็นภาพจากโพสต์สาธารณะของเพจเราเอง ไม่ใช่ข้อมูลส่วนบุคคล จึงเสิร์ฟผ่าน /media/ ได้ (เหมือนรูปปก)
· ffmpeg: ใช้ของเครื่องก่อน ไม่มีค่อยใช้ตัวที่มากับแพ็กเกจ `imageio-ffmpeg`
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from urllib.parse import urlparse

log = logging.getLogger(__name__)

SUBDIR = os.path.join("frames", "meta")
FRAME_H = 240                    # สูง 240px — พอให้กดดูใหญ่ได้ · ภาพละ ~8 KB
MAX_VIDEO_BYTES = 250_000_000    # คลิปเพจเรายาวไม่เกินไม่กี่นาที · เกินนี้ถือว่าผิดปกติ ไม่โหลด
MAX_SECONDS = 600                # ตัดภาพแค่ 10 นาทีแรก
RUN_STALE_SEC = 900              # ทำค้างนานกว่านี้ = thread ตายไปแล้ว เริ่มใหม่ได้
RETRY_AFTER_SEC = 1800           # ทำไม่สำเร็จ = เว้น 30 นาทีค่อยลองใหม่ (ไม่ยิงซ้ำทุกครั้งที่เปิดหน้า)
KEEP_DAYS = 90
ENABLED = False                  # ★ ปิด: ไม่โหลดวิดีโอมาตัดภาพ (เจ้าของสั่ง 15 ต.ค.69 · ใช้รูปปก+ลิงก์แทน)
TOP_N = 25                       # ภาพทีละวินาที: คลิปที่ยิงแอด วิวสูงสุดกี่อันดับ
NEW_DAYS = 7                     # + คลิปที่ลงภายในกี่วัน (คลิปใหม่ = วิเคราะห์+ภาพให้เองทุกชั่วโมง)
PRUNE_GRACE_DAYS = 3             # หลุดเกณฑ์แล้วเก็บภาพไว้อีกกี่วันก่อนลบ
ELIG_TTL_SEC = 600               # รายชื่อคลิปที่เข้าเกณฑ์ จำไว้ 10 นาที (เปิดหน้าเว็บทุกครั้งไม่ต้องคำนวณใหม่)
_HOSTS = ("fbcdn.net", "facebook.com", "fbsbx.com")   # ไฟล์วิดีโอต้องมาจาก Facebook เท่านั้น
_SAFE = re.compile(r"[^A-Za-z0-9_-]")
_LOCK = threading.Lock()
_RUNNING: set = set()
_ELIG: dict = {"at": 0.0, "nd": None, "ads": [], "new": []}
_PREFETCH = {"on": False}


def _key(post_id: str) -> str:
    return _SAFE.sub("", str(post_id or ""))[:80]


def _root() -> str:
    from django.conf import settings
    return os.path.join(str(settings.MEDIA_ROOT), SUBDIR)


def _dir(post_id: str) -> str:
    k = _key(post_id)
    return os.path.join(_root(), k) if k else ""


def _info(d: str) -> dict:
    try:
        with open(os.path.join(d, "info.json"), encoding="utf-8") as f:
            v = json.load(f)
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_info(d: str, data: dict):
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, "info.json.part")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, os.path.join(d, "info.json"))


def status(post_id: str) -> dict:
    """{"state": ready|running|none|error, "urls": [...ทีละวินาที], "error": ""}"""
    from django.conf import settings
    k = _key(post_id)
    d = _dir(post_id)
    if not d:
        return {"state": "error", "urls": [], "error": "ไม่รู้จักโพสต์นี้"}
    if k in _RUNNING:
        return {"state": "running", "urls": []}
    info = _info(d)
    if info.get("n"):
        base = settings.MEDIA_URL.rstrip("/") + "/" + SUBDIR.replace(os.sep, "/") + "/" + k + "/"
        ver = str(info.get("at") or "")[:19].replace(":", "").replace("-", "")
        return {"state": "ready", "error": "",
                "urls": [base + "%03d.jpg?v=%s" % (i + 1, ver) for i in range(int(info["n"]))]}
    if info.get("running") and time.time() - float(info.get("running") or 0) < RUN_STALE_SEC:
        return {"state": "running", "urls": []}           # worker อื่นกำลังทำอยู่
    if info.get("error"):
        return {"state": "error", "urls": [], "error": info["error"],
                "retry": time.time() - float(info.get("failedAt") or 0) >= RETRY_AFTER_SEC}
    return {"state": "none", "urls": []}


def _ads_rows() -> list:
    """วิดีโอที่ **ยิงแอดแล้ว** (วิวจากโฆษณา > 0) เรียงวิวรวมมากสุด — snapshot ล่าสุดของแต่ละโพสต์

    ดูเฉพาะแถวที่ดึงไม่เกิน 2 วันก่อนรอบล่าสุดของเพจนั้น (โพสต์ที่หลุดหน้าต่างดึงไปแล้ว = เก่าเกินจะมาตัดภาพ)
    """
    from datetime import timedelta

    from django.db.models import Max

    from dashboard.models import MetaPostSnapshot
    best: dict = {}
    for pg in MetaPostSnapshot.objects.values("page_id").annotate(m=Max("taken_at")):
        if not pg["m"]:
            continue
        qs = (MetaPostSnapshot.objects
              .filter(page_id=pg["page_id"], taken_at__gte=pg["m"] - timedelta(days=2),
                      post_type__icontains="video")
              .order_by("-taken_at")
              .values("post_id", "page_id", "video_views", "video_views_paid"))
        for r in qs:
            if r["post_id"] in best:                     # แถวแรกที่เจอ = ล่าสุดของโพสต์นั้น
                continue
            best[r["post_id"]] = r
    rows = [{"post_id": r["post_id"], "page_id": r["page_id"], "reason": "ads",
             "views": r["video_views"] or 0, "paid": r["video_views_paid"] or 0}
            for r in best.values() if (r["video_views_paid"] or 0) > 0]
    rows.sort(key=lambda r: (-r["views"], r["post_id"]))
    return rows


def _new_rows(days: int) -> list:
    """คลิปที่ลงภายใน `days` วัน (มีกราฟแล้ว = มีคนดูแล้ว) · ใหม่สุดก่อน"""
    if days <= 0:
        return []
    from datetime import timedelta

    from django.utils import timezone

    from dashboard.models import MetaVideoRetention
    qs = (MetaVideoRetention.objects.filter(created_time__gte=timezone.now() - timedelta(days=days))
          .order_by("-created_time").values("post_id", "page_id"))
    return [{"post_id": r["post_id"], "page_id": r["page_id"], "reason": "new", "views": 0, "paid": 0}
            for r in qs]


def eligible(n: int = TOP_N, fresh: bool = False, new_days: int | None = None) -> list:
    """คลิปที่ได้ภาพทีละวินาที = **ยิงแอดวิวสูงสุด `n` อันดับ** + **คลิปใหม่ `NEW_DAYS` วัน**

    คืน [{post_id, page_id, reason (ads/new), views, paid}] — ยิงแอดก่อน แล้วตามด้วยคลิปใหม่ที่ยังไม่อยู่ในกลุ่มแรก
    """
    nd = NEW_DAYS if new_days is None else new_days
    now = time.time()
    if fresh or not _ELIG["at"] or now - _ELIG["at"] >= ELIG_TTL_SEC or _ELIG.get("nd") != nd:
        _ELIG.update(at=now, nd=nd, ads=_ads_rows()[:max(n, TOP_N)], new=_new_rows(nd))
    ads = _ELIG["ads"][:n]
    seen = {r["post_id"] for r in ads}
    return ads + [r for r in _ELIG["new"] if r["post_id"] not in seen]


def reason_of(post_id: str) -> str:
    """ได้ภาพเพราะอะไร ('' = ไม่เข้าเกณฑ์)"""
    for r in eligible():
        if r["post_id"] == str(post_id):
            return r["reason"]
    return ""


def is_eligible(post_id: str) -> bool:
    return bool(reason_of(post_id))


def _claim(post_id: str) -> bool:
    """จองคลิปนี้ไว้ทำ (กันทำซ้อน) · คืน False ถ้ามีคนทำอยู่แล้ว/เขียนไฟล์ไม่ได้"""
    k = _key(post_id)
    with _LOCK:
        if k in _RUNNING:
            return False
        _RUNNING.add(k)
    try:
        _write_info(_dir(post_id), {"running": time.time()})
    except OSError:
        _RUNNING.discard(k)
        return False
    return True


def _todo(st: dict) -> bool:
    """สถานะนี้ต้องทำภาพใหม่ไหม (ยังไม่มี · หรือพลาดมานานพอจะลองใหม่)"""
    return st["state"] == "none" or (st["state"] == "error" and st.get("retry"))


def ensure(post_id: str, reason: str = "") -> dict:
    """มีภาพแล้วคืนเลย · ยังไม่มี = เริ่มทำใน thread แล้วคืนสถานะ running"""
    if not ENABLED:
        return {"state": "off", "urls": []}
    st = status(post_id)
    if not _todo(st):
        return st
    if not _claim(post_id):
        return {"state": "running", "urls": []}
    threading.Thread(target=_job, args=(post_id,), kwargs={"reason": reason},
                     daemon=True, name="video-frames").start()
    return {"state": "running", "urls": []}


def for_detail(post_id: str) -> dict:
    """ภาพของหน้า "คนดูหลุดตรงไหน" — มีแล้วคืนเลย · อยู่ในกลุ่มที่ได้ภาพแต่ยังไม่มี = เริ่มทำ ·
    นอกกลุ่ม = state "skip" (หน้าเว็บบอกเกณฑ์) ไม่โหลดคลิป · ปิดอยู่ = state "off" (ไม่แสดงภาพเลย)"""
    if not ENABLED:
        return {"state": "off", "urls": []}
    st = status(post_id)
    if st["state"] in ("ready", "running"):
        return st
    try:
        why = reason_of(post_id)
    except Exception as e:                                  # อ่านรายชื่อไม่ได้ = ไม่ทำ แต่บอกเหตุผล
        log.warning("video_frames eligible: %s", e)
        why = ""
    if not why:
        return {"state": "skip", "urls": [], "top": TOP_N, "newDays": NEW_DAYS}
    return ensure(post_id, reason=why)


def prefetch(n: int = TOP_N, limit: int | None = None, new_days: int | None = None) -> dict:
    """ทำภาพให้คลิปในกลุ่มที่ยังไม่มี **ทีละคลิป** (ไม่แย่งเน็ต/CPU กับเว็บ) · ลบภาพของคลิปที่หลุดเกณฑ์ · คืนสรุป"""
    from django.db import close_old_connections
    if not ENABLED:
        return {"total": 0, "made": 0, "ready": 0, "failed": 0, "busy": 0, "pruned": 0, "errors": [], "off": True}
    rows = eligible(n, fresh=True, new_days=new_days)
    out = {"total": len(rows), "made": 0, "ready": 0, "failed": 0, "busy": 0, "pruned": 0, "errors": []}
    for r in rows:
        if limit is not None and out["made"] + out["failed"] >= limit:
            break
        pid = r["post_id"]
        st = status(pid)
        if st["state"] == "ready":
            out["ready"] += 1
            continue
        if not _todo(st) or not _claim(pid):
            out["busy"] += 1
            continue
        _job(pid, cleanup=False, reason=r["reason"])
        st = status(pid)
        if st["state"] == "ready":
            out["made"] += 1
        else:
            out["failed"] += 1
            out["errors"].append("%s: %s" % (pid, (st.get("error") or "")[:80]))
    close_old_connections()
    if rows:                       # รายชื่อว่าง (อ่านไม่ได้/ยังไม่มีข้อมูล) = ห้ามลบ ไม่งั้นภาพหายหมด
        try:
            out["pruned"] = prune({r["post_id"] for r in rows})
        except Exception as e:
            out["errors"].append("ลบภาพเก่าพัง: %s" % str(e)[:80])
    try:
        cleanup_old()
    except Exception:
        pass
    return out


def prefetch_guarded(**kw):
    """prefetch แบบกันรันซ้อนในโปรเซสเดียวกัน (รอบเที่ยงคืน + รอบรายชั่วโมง) · กำลังทำอยู่ = None"""
    with _LOCK:
        if _PREFETCH["on"]:
            return None
        _PREFETCH["on"] = True
    try:
        res = prefetch(**kw)
        try:
            from . import cache_store
            cache_store.set_kv("video_frames_last", {**res, "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
        except Exception:
            pass
        return res
    finally:
        _PREFETCH["on"] = False


def start_prefetch() -> bool:
    """เรียกต่อท้ายรอบดึง Meta (thread แยก · ไม่หน่วงรอบดึง) · มีอันกำลังทำอยู่แล้ว = ไม่เริ่มซ้ำ"""
    if not ENABLED or _PREFETCH["on"]:
        return False

    def _run():
        from django.db import connection
        try:
            prefetch_guarded()
        except Exception as e:
            log.warning("video_frames prefetch: %s", e)
        finally:
            connection.close()
    threading.Thread(target=_run, daemon=True, name="video-frames-prefetch").start()
    return True


def prune(keep: set, grace_days: int = PRUNE_GRACE_DAYS) -> int:
    """ลบชุดภาพของคลิปที่หลุดเกณฑ์ (ไม่ใช่คลิปใหม่แล้ว/หลุดอันดับแอด) เมื่อทำไว้นานเกิน `grace_days` วัน

    เว้นไว้ก่อนสักพัก กันคลิปที่ขยับเข้า-ออกอันดับวันต่อวันถูกลบแล้วต้องโหลดคลิปตัดใหม่ซ้ำๆ
    """
    keep_k = {_key(p) for p in keep}
    cut = time.time() - grace_days * 86400
    n = 0
    try:
        entries = list(os.scandir(_root()))
    except OSError:
        return 0
    for e in entries:
        if not e.is_dir() or e.name in keep_k or e.name in _RUNNING:
            continue
        info_p = os.path.join(e.path, "info.json")
        try:
            if os.path.getmtime(info_p) >= cut:
                continue
        except OSError:
            continue
        info = _info(e.path)
        if info.get("running") and not info.get("n"):
            continue
        shutil.rmtree(e.path, ignore_errors=True)
        _mark_db(e.name, frames_n=0, frames_reason="", frames_error="")
        n += 1
    return n


def purge() -> dict:
    """ลบภาพทีละวินาทีทั้งหมด + ล้างช่อง frames_* ในตาราง (ใช้ตอนปิดฟีเจอร์ · ประหยัดพื้นที่)"""
    root = _root()
    n, size = 0, 0
    try:
        for e in os.scandir(root):
            if e.is_dir():
                for f in os.scandir(e.path):
                    try:
                        size += f.stat().st_size
                    except OSError:
                        pass
                n += 1
    except OSError:
        pass
    shutil.rmtree(root, ignore_errors=True)
    try:
        from dashboard.models import MetaVideoRetention
        MetaVideoRetention.objects.exclude(frames_n=0, frames_error="", frames_reason="").update(
            frames_n=0, frames_at=None, frames_reason="", frames_error="")
    except Exception:
        pass
    return {"clips": n, "mb": round(size / 1e6, 1)}


def _mark_db(post_id: str, **fields):
    """จดผลการทำภาพลงตาราง `dash_meta_video_retention` (best-effort · ยังไม่ migrate/ไม่มีแถว = ข้าม)"""
    try:
        from dashboard.models import MetaVideoRetention
        MetaVideoRetention.objects.filter(post_id=str(post_id)).update(**fields)
    except Exception:
        pass


def ffmpeg_exe() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return ""


def _job(post_id: str, cleanup: bool = True, reason: str = ""):
    from django.db import close_old_connections
    from django.utils import timezone
    k, d = _key(post_id), _dir(post_id)
    try:
        n, length = _extract(post_id, d)
        _write_info(d, {"n": n, "len": length, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "reason": reason})
        _mark_db(post_id, frames_n=n, frames_at=timezone.now(), frames_reason=reason, frames_error="")
    except Exception as e:                                  # บอกเหตุผลเป็นภาษาคน · ไม่ทำให้อะไรล้มตาม
        log.warning("video_frames %s: %s", post_id, e)
        _mark_db(post_id, frames_error=str(e)[:200])
        try:
            _write_info(d, {"error": str(e)[:200], "failedAt": time.time()})
        except OSError:
            pass
    finally:
        _RUNNING.discard(k)
        close_old_connections()
        if cleanup:
            try:
                cleanup_old()
            except Exception:
                pass


def _extract(post_id: str, d: str) -> tuple:
    from . import meta
    pid = str(post_id).split("_")[0]
    if pid not in meta.pages():
        raise RuntimeError("โพสต์นี้ไม่ได้อยู่ใต้เพจของบริษัทนี้")
    exe = ffmpeg_exe()
    if not exe:
        raise RuntimeError("เครื่องนี้ไม่มี ffmpeg — ลง imageio-ffmpeg (pip install -r requirements.txt)")
    pt = meta.page_token(pid)
    p = meta.get("/" + post_id, _token=pt, fields="attachments{target,media_type}")
    att = ((p.get("attachments") or {}).get("data") or [{}])[0]
    vid = str((att.get("target") or {}).get("id") or "")
    if not vid or "video" not in (att.get("media_type") or ""):
        raise RuntimeError("โพสต์นี้ไม่ใช่วิดีโอ")
    v = meta.get("/" + vid, _token=pt, fields="source,length")   # vid สืบมาจากคำตอบข้างบน (ผ่านด่าน meta)
    src = v.get("source") or ""
    host = (urlparse(src).hostname or "").lower()
    if not src or not any(host == h or host.endswith("." + h) for h in _HOSTS):
        raise RuntimeError("Facebook ไม่ให้ไฟล์วิดีโอของโพสต์นี้")
    try:
        length = round(float(v.get("length")), 2)
    except (TypeError, ValueError):
        length = None
    import requests
    tmpdir = tempfile.mkdtemp(prefix="vframes_")
    try:
        mp4 = os.path.join(tmpdir, "v.mp4")
        got = 0
        with requests.get(src, stream=True, timeout=60) as r:
            if r.status_code != 200:
                raise RuntimeError("โหลดไฟล์วิดีโอไม่ได้ (HTTP %s)" % r.status_code)
            with open(mp4, "wb") as f:
                for chunk in r.iter_content(1 << 16):
                    got += len(chunk)
                    if got > MAX_VIDEO_BYTES:
                        raise RuntimeError("ไฟล์วิดีโอใหญ่เกิน %d MB" % (MAX_VIDEO_BYTES // 1_000_000))
                    f.write(chunk)
        out = os.path.join(tmpdir, "f")
        os.makedirs(out)
        cp = subprocess.run([exe, "-v", "error", "-nostdin", "-i", mp4, "-t", str(MAX_SECONDS),
                             "-vf", "fps=1,scale=-2:%d" % FRAME_H, "-q:v", "5",
                             os.path.join(out, "%03d.jpg")], capture_output=True, timeout=300)
        frames = sorted(x for x in os.listdir(out) if x.endswith(".jpg"))
        if cp.returncode != 0 or not frames:
            raise RuntimeError("ตัดภาพไม่สำเร็จ: %s" % (cp.stderr or b"").decode("utf-8", "replace")[:150])
        os.makedirs(d, exist_ok=True)
        for x in os.listdir(d):                              # ของเก่า (ถ้ามี) ออกก่อน
            if x.endswith(".jpg"):
                os.remove(os.path.join(d, x))
        for x in frames:
            shutil.move(os.path.join(out, x), os.path.join(d, x))
        return len(frames), length
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def cleanup_old(days: int = KEEP_DAYS) -> int:
    """ลบชุดภาพที่ทำไว้เกิน `days` วัน (ดิสก์ไม่โตไม่หยุด — บทเรียนรูปรายงาน 1.3 GB)"""
    root = _root()
    cut = time.time() - days * 86400
    n = 0
    try:
        entries = list(os.scandir(root))
    except OSError:
        return 0
    for e in entries:
        try:
            if e.is_dir() and e.stat().st_mtime < cut:
                shutil.rmtree(e.path, ignore_errors=True)
                n += 1
        except OSError:
            continue
    return n
