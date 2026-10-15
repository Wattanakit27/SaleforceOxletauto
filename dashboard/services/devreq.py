# -*- coding: utf-8 -*-
"""แจ้งผู้พัฒนา — บั๊ก / ขอฟีเจอร์ / สอบถาม จากคนใช้ระบบ (15 ต.ค.69 · เจ้าของสั่ง)

*"เพิ่มฟังก์ชันในการตั้งค่า คือ แจ้งเตือนผู้พัฒนา แล้วสร้างแบบฟอร์มขึ้นมา ฉันจะได้รู้ว่าใคร Request ให้ทำอะไรบ้าง
แต่ละวัน · เมื่อมีการแจ้งเตือนต่างๆ ไม่ว่าจะเป็นไฟล์ คลิป วิดีโอ ส่งข้อความแจ้งเตือนมาที่ LINE ส่วนตัวของฉัน
แล้วฉันจะไปดูระบบเอง"*

- แบบฟอร์มอยู่ในหน้าตั้งค่าของแดชบอร์ด (แอดมิน) → ตาราง `dash_dev_request` 1 แถวต่อเรื่อง
- ส่งแล้ว = ข้อความเข้า LINE ส่วนตัวเจ้าของ (ผู้รับเดียวกับแจ้งเตือนลงชีตจ่ายเบอร์ · `leadsheet._send_alert`)
  **ส่งแค่ข้อความ + ลิงก์เข้าระบบ ไม่ส่งไฟล์เข้า LINE** (เจ้าของสั่ง "ฉันจะไปดูระบบเอง")
- ไฟล์แนบ (รูป/คลิป/ไฟล์) เก็บ **นอก /media/** ที่ `DEV_REQUEST_ROOT` (ค่าตั้งต้น private_media/devreq)
  เพราะภาพหน้าจอที่แจ้งบั๊กมักมีข้อมูลลูกค้า · เปิดได้ทางเดียว `/api/admin/dev_requests/file` (แอดมิน)
  · อัปผ่าน `/track/api/upload` (`target=devreq`) — ช่องที่ nginx เปิดรับไฟล์ใหญ่ถึง 220 MB อยู่แล้ว
    (ช่องปกติของเว็บรับแค่ 20 MB ซึ่งคลิปจากมือถือเกินง่าย)
- ไฟล์แนบลบเองเมื่อเกิน `KEEP_FILE_DAYS` วัน (ตัวเรื่องยังอยู่) — ไฟล์คลิปกินพื้นที่
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import uuid
from datetime import timedelta
from pathlib import Path

log = logging.getLogger(__name__)

MAX_FILES = 10
KEEP_FILE_DAYS = 180
LINE_PER_HOUR = 30                 # แจ้ง LINE ไม่เกินเท่านี้/ชม. (กันใครกดส่งรัว) — เกินแล้วยังบันทึก แค่ไม่เด้ง LINE
_TOKEN = re.compile(r"^\d{4}-\d{2}/[0-9a-f]{32}\.[a-z0-9]{1,5}$")
_EXT_OK = re.compile(r"^[a-z0-9]{1,5}$")
INLINE_TYPES = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif",
                "webp": "image/webp", "heic": "image/heic", "mp4": "video/mp4", "mov": "video/quicktime",
                "webm": "video/webm", "m4v": "video/mp4", "pdf": "application/pdf"}
KIND_TH = {"bug": "เจอบั๊ก / ใช้งานไม่ได้", "feature": "ขอฟีเจอร์ / ขอแก้", "question": "สอบถาม", "other": "อื่นๆ"}
STATUS_TH = {"new": "ใหม่", "doing": "กำลังทำ", "done": "เสร็จแล้ว", "rejected": "ไม่ทำ"}


def root() -> Path:
    from django.conf import settings
    base = getattr(settings, "DEV_REQUEST_ROOT", "") or os.getenv("DEV_REQUEST_ROOT", "")
    return Path(base) if base else Path(settings.BASE_DIR) / "private_media" / "devreq"


def _ext(name: str, ctype: str = "") -> str:
    e = os.path.splitext(str(name or ""))[1].lstrip(".").lower()
    if not _EXT_OK.match(e or ""):
        e = {"image/jpeg": "jpg", "image/png": "png", "video/mp4": "mp4", "video/quicktime": "mov",
             "application/pdf": "pdf"}.get((ctype or "").split(";")[0].strip().lower(), "bin")
    return e


def kind_of_file(ext: str) -> str:
    t = INLINE_TYPES.get(ext, "")
    return "image" if t.startswith("image") else "video" if t.startswith("video") else "file"


def save_upload(f) -> dict:
    """ไฟล์ที่อัปจากแบบฟอร์ม → เก็บในที่ปิด · คืน {ok, id (token), name, size, kind}"""
    from django.utils import timezone
    ext = _ext(getattr(f, "name", ""), getattr(f, "content_type", ""))
    token = "%s/%s.%s" % (timezone.localdate().strftime("%Y-%m"), uuid.uuid4().hex, ext)
    p = root() / token
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".part")
        with open(tmp, "wb") as out:
            for chunk in f.chunks():
                out.write(chunk)
        os.replace(tmp, p)
    except OSError as e:
        return {"ok": False, "error": "บันทึกไฟล์ไม่ได้: %s" % str(e)[:120]}
    name = re.sub(r"[\r\n\t]", " ", str(getattr(f, "name", "") or "ไฟล์"))[:120]
    return {"ok": True, "id": token, "name": name, "size": p.stat().st_size, "kind": kind_of_file(ext),
            "video": kind_of_file(ext) == "video"}


def _file_path(token: str):
    """token → path จริง (ต้องอยู่ใต้ root และมีไฟล์อยู่) · ไม่ผ่าน = None"""
    t = str(token or "")
    if not _TOKEN.match(t):
        return None
    p = (root() / t).resolve()
    try:
        p.relative_to(root().resolve())
    except ValueError:
        return None
    return p if p.is_file() else None


def _who(user: dict) -> tuple:
    u = user or {}
    name = (u.get("nickname") or u.get("display_name") or u.get("seller_name") or u.get("user_id") or "").strip()
    return name[:80] or "ไม่ทราบชื่อ", (u.get("position") or "")[:20], (u.get("user_id") or "")[:80]


def create(user: dict, data: dict, user_agent: str = "") -> tuple:
    """สร้างเรื่องใหม่ + แจ้ง LINE เจ้าของ · คืน (item dict, error) — error = ข้อความภาษาคน"""
    from django.utils import timezone

    from dashboard.models import DevRequest
    kind = str(data.get("kind") or "bug")
    if kind not in KIND_TH:
        return None, "ประเภทไม่ถูกต้อง"
    title = re.sub(r"\s+", " ", str(data.get("title") or "")).strip()[:200]
    if not title:
        return None, "ใส่หัวข้อก่อน (สั้นๆ ว่าเจออะไร/อยากได้อะไร)"
    detail = str(data.get("detail") or "").strip()[:5000]
    page = str(data.get("page") or "").strip()[:300]
    raw_files = data.get("files") or []
    if not isinstance(raw_files, list):
        return None, "ไฟล์แนบไม่ถูกต้อง"
    if len(raw_files) > MAX_FILES:
        return None, "แนบได้ไม่เกิน %d ไฟล์" % MAX_FILES
    files = []
    for x in raw_files:
        tok = x.get("id") if isinstance(x, dict) else x
        p = _file_path(tok)
        if p is None:
            return None, "ไฟล์แนบบางไฟล์หาไม่เจอ (อัปใหม่อีกครั้ง)"
        ext = p.suffix.lstrip(".")
        name = (x.get("name") if isinstance(x, dict) else "") or p.name
        files.append({"id": tok, "name": re.sub(r"[\r\n\t]", " ", str(name))[:120], "size": p.stat().st_size,
                      "kind": kind_of_file(ext)})
    name, role, uid = _who(user)
    r = DevRequest.objects.create(kind=kind, urgent=bool(data.get("urgent")), title=title, detail=detail, page=page,
                                  requester=name, requester_role=role, requester_uid=uid, files=files,
                                  user_agent=(user_agent or "")[:300])
    # แจ้ง LINE เจ้าของ (ไม่ทำให้การบันทึกล้มถ้าส่งไม่ได้)
    since = timezone.now() - timedelta(hours=1)
    if DevRequest.objects.filter(created_at__gte=since, line_ok=True).count() >= LINE_PER_HOUR:
        ok, err = False, "เกิน %d ข้อความ/ชม. — บันทึกแล้วแต่ไม่เด้ง LINE" % LINE_PER_HOUR
    else:
        try:
            from checkout import leadsheet
            ok, err = leadsheet._send_alert(line_text(r), what="แจ้งผู้พัฒนา")
        except Exception as e:
            ok, err = False, str(e)[:200]
    DevRequest.objects.filter(pk=r.pk).update(line_ok=ok, line_error=(err or "")[:300])
    r.line_ok, r.line_error = ok, (err or "")[:300]
    try:
        from . import eventlog
        eventlog.log("devreq", name="แจ้งผู้พัฒนา", target=str(r.pk), ok=ok, kind=kind, by=name, error=(err or "")[:200])
    except Exception:
        pass
    _cleanup_daily()
    return item_json(r, full=True), ""


def line_text(r) -> str:
    """ข้อความที่เด้งเข้า LINE ส่วนตัวเจ้าของ — สั้น อ่านจบในจอเดียว + ลิงก์เข้าไปดูในระบบ"""
    from django.conf import settings
    from django.utils import timezone
    at = timezone.localtime(r.created_at).strftime("%d/%m %H:%M") if r.created_at else ""
    cnt = {"image": 0, "video": 0, "file": 0}
    for f in r.files or []:
        cnt[f.get("kind", "file")] = cnt.get(f.get("kind", "file"), 0) + 1
    att = " · ".join(t for t in ("รูป %d" % cnt["image"] if cnt["image"] else "",
                                  "คลิป %d" % cnt["video"] if cnt["video"] else "",
                                  "ไฟล์ %d" % cnt["file"] if cnt["file"] else "") if t)
    detail = (r.detail or "").strip()
    if len(detail) > 400:
        detail = detail[:400] + "…"
    site = (getattr(settings, "SITE_URL", "") or "").rstrip("/")
    lines = ["[แจ้งผู้พัฒนา] %s%s" % (KIND_TH.get(r.kind, r.kind), " · ด่วน" if r.urgent else ""),
             "จาก: %s · %s" % (r.requester or "-", at),
             "เรื่อง: %s" % r.title]
    if detail:
        lines.append(detail)
    if r.page:
        lines.append("หน้า: %s" % r.page)
    if att:
        lines.append("แนบ: %s" % att)
    if site:
        lines.append("ดูในระบบ: %s/dashboard/?panel=devrequests" % site)
    return "\n".join(lines)


def item_json(r, full: bool = False) -> dict:
    from django.utils import timezone
    loc = timezone.localtime(r.created_at) if r.created_at else None
    return {"id": r.pk, "kind": r.kind, "kindTh": KIND_TH.get(r.kind, r.kind), "urgent": r.urgent,
            "title": r.title, "detail": r.detail, "page": r.page, "requester": r.requester,
            "date": loc.date().isoformat() if loc else "", "time": loc.strftime("%H:%M") if loc else "",
            "status": r.status, "statusTh": STATUS_TH.get(r.status, r.status), "note": r.note,
            "files": [{"i": i, "name": f.get("name", ""), "size": f.get("size", 0), "kind": f.get("kind", "file"),
                       "gone": bool(f.get("gone")),
                       "url": "" if f.get("gone") else "/api/admin/dev_requests/file?id=%s&i=%d" % (r.pk, i)}
                      for i, f in enumerate(r.files or [])],
            "lineOk": r.line_ok, "lineError": r.line_error if full else ("" if r.line_ok else (r.line_error or "")[:120]),
            "updated": timezone.localtime(r.updated_at).strftime("%d/%m %H:%M") if r.updated_at else ""}


def listing(days: int = 30, status: str = "") -> dict:
    """เรื่องที่แจ้งย้อนหลัง `days` วัน (ใหม่สุดก่อน) + สรุปจำนวนตามสถานะ"""
    from django.db.models import Count
    from django.utils import timezone

    from dashboard.models import DevRequest
    days = max(1, min(int(days or 30), 3650))
    qs = DevRequest.objects.filter(created_at__gte=timezone.now() - timedelta(days=days))
    counts = {r["status"]: r["n"] for r in qs.values("status").annotate(n=Count("id"))}
    if status in STATUS_TH:
        qs = qs.filter(status=status)
    items = [item_json(r) for r in qs.order_by("-created_at")[:500]]
    return {"items": items, "counts": counts, "days": days, "kinds": KIND_TH, "statuses": STATUS_TH}


def set_status(pk, status: str, note=None) -> tuple:
    from dashboard.models import DevRequest
    if status and status not in STATUS_TH:
        return None, "สถานะไม่ถูกต้อง"
    r = DevRequest.objects.filter(pk=pk).first()
    if r is None:
        return None, "ไม่พบเรื่องนี้"
    if status:
        r.status = status
    if note is not None:
        r.note = str(note).strip()[:2000]
    r.save(update_fields=["status", "note", "updated_at"])
    return item_json(r), ""


def file_of(pk, i: int):
    """(path, ชื่อไฟล์, นามสกุล) ของไฟล์แนบลำดับ i · ไม่มี = None"""
    from dashboard.models import DevRequest
    r = DevRequest.objects.filter(pk=pk).first()
    if r is None:
        return None
    files = r.files or []
    if not (0 <= i < len(files)) or files[i].get("gone"):
        return None
    p = _file_path(files[i].get("id"))
    if p is None:
        return None
    return p, files[i].get("name") or p.name, p.suffix.lstrip(".")


def cleanup_files(days: int = KEEP_FILE_DAYS) -> int:
    """ลบไฟล์แนบของเรื่องที่เก่ากว่า `days` วัน (ตัวเรื่องยังอยู่ · ไฟล์ขึ้นว่า "ลบแล้ว") + ไฟล์ที่อัปแล้วไม่ได้ส่ง"""
    import time

    from django.utils import timezone

    from dashboard.models import DevRequest
    n = 0
    cut = timezone.now() - timedelta(days=days)
    for r in DevRequest.objects.filter(created_at__lt=cut):
        changed = False
        for f in r.files or []:
            if f.get("gone"):
                continue
            p = _file_path(f.get("id"))
            if p is not None:
                try:
                    p.unlink()
                    n += 1
                except OSError:
                    continue
            f["gone"] = True
            changed = True
        if changed:
            DevRequest.objects.filter(pk=r.pk).update(files=r.files)
    # ไฟล์ที่อัปขึ้นมาแต่ไม่ได้กดส่ง (ค้างเกิน 2 วัน) — ไม่มีแถวไหนอ้างถึง
    used = set()
    for fs in DevRequest.objects.values_list("files", flat=True):
        used.update(str(f.get("id")) for f in (fs or []) if isinstance(f, dict))
    old = time.time() - 2 * 86400
    base = root()
    try:
        months = [d for d in base.iterdir() if d.is_dir()]
    except OSError:
        months = []
    for d in months:
        for p in d.iterdir():
            tok = "%s/%s" % (d.name, p.name)
            try:
                if tok not in used and p.stat().st_mtime < old:
                    p.unlink()
                    n += 1
            except OSError:
                continue
        try:
            if not any(d.iterdir()):
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass
    return n


def _cleanup_daily():
    """เรียกตอนมีเรื่องใหม่ — วันละครั้งพอ (KV devreq_cleanup)"""
    try:
        from django.utils import timezone

        from . import cache_store
        today = timezone.localdate().isoformat()
        last = (cache_store.get_kv("devreq_cleanup") or {}).get("data") or {}
        if last.get("date") == today:
            return
        cache_store.set_kv("devreq_cleanup", {"date": today, "removed": cleanup_files()})
    except Exception as e:
        log.debug("devreq cleanup: %s", e)
