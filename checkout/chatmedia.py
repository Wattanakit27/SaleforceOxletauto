# -*- coding: utf-8 -*-
"""รูป/ไฟล์ที่ลูกค้าส่งเข้ามาในแชท (LINE OA · Facebook) — โหลดมาเก็บเอง แล้วเปิดดูในหน้า Connect ได้ · 11 ต.ค.69

เจ้าของแจ้ง *"รูปไม่ขึ้นนิ"* — เดิมระบบจดแค่ว่า "มีรูป" (`has_media`) แต่ไม่เคยโหลดตัวไฟล์มาเลย:
  - **LINE** ไม่ส่งไฟล์มากับ webhook (ส่งมาแค่ message id) → ต้องไปขอจาก content API
    ด้วย token ของบัญชีที่ได้ยินข้อความนั้น · **LINE ลบไฟล์ทิ้งเองหลังผ่านไปช่วงหนึ่ง** (ไม่บอกว่ากี่วัน)
  - **Facebook** ให้ลิงก์ fbcdn แบบมีลายเซ็นที่หมดอายุในไม่กี่วัน

★ ที่เก็บ = `CHAT_MEDIA_ROOT` (**นอก** MEDIA_ROOT) — ไม่ใช่โฟลเดอร์สาธารณะ
  nginx เสิร์ฟทุกอย่างใต้ `/media/` ให้ใครก็ได้ที่รู้ลิงก์ · ไฟล์ที่ลูกค้าส่งมีทั้งบัตรประชาชน/สลิป/รายงานเครดิต
  → เปิดได้ทางเดียวคือ `/connect/api/media` ซึ่งเช็คสิทธิ์แบบเดียวกับการเปิดแชท (connect_views.api_media)

โหลดเมื่อไหร่:
  1. **ทุกนาที** (`sweep_bg` จาก connect.tick · thread แยก) — ข้อความขาเข้าของลูกค้าที่ยังไม่ได้โหลด (7 วันล่าสุด)
  2. **ตอนมีคนเปิดดู** (ไม่ทันรอบ/เก่ากว่านั้น) — ลองโหลดครั้งเดียว · พลาดชั่วคราว = เว้น 10 นาทีค่อยลองใหม่
  3. **ย้อนหลังทีเดียว** — `manage.py chat_media --fetch`

อายุไฟล์ = อายุแถวแชท (ลูกค้า 60 วัน) — แถวถูกลบเมื่อไหร่ ไฟล์ถูกลบตามในรอบกวาดวันละครั้ง

`media_token` ของแถว = สถานะการโหลด · รูปแบบ `<สถานะ>|<นามสกุลแต่ละไฟล์>|<เวลาลองล่าสุด>`
  สถานะ: `ok` ครบ · `err` พลาดชั่วคราว (ลองใหม่ได้) · `gone` ต้นทางไม่มีแล้ว · `big` ใหญ่เกิน · `none` ไม่มีที่ให้โหลด
  นามสกุล: คั่นด้วยจุลภาค ตามลำดับไฟล์แนบ · `-` = ยังไม่มีไฟล์นั้น · ว่าง = ยังไม่เคยลอง
"""
from __future__ import annotations

import os
import re
import secrets
import threading
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .models import FbChat, GroupChat

LINE, FB = "l", "f"
MEDIA_KINDS = ("image", "video", "audio", "file")
RETRY_SEC = 600            # พลาดชั่วคราว (เน็ต/429/5xx) → ลองใหม่ได้หลังกี่วินาที
PREFETCH_DAYS = 7          # รอบกวาดทุกนาทีดูย้อนหลังกี่วัน (ย้อนไกลกว่านี้ใช้คำสั่ง chat_media --fetch)
SWEEP_EVERY = 60           # วินาที · ต่อ process
SWEEP_LIMIT = 30           # ข้อความต่อรอบ
SWEEP_BUDGET = 40          # วินาทีต่อรอบ (cron ยิงทุกนาที — ห้ามยาวจนซ้อนรอบถัดไป)
MAX_FILES = 10             # ไฟล์แนบต่อข้อความ (Facebook ส่งหลายรูปในข้อความเดียวได้)
LINE_CONTENT = "https://api-data.line.me/v2/bot/message/%s/content"
FB_HOSTS = ("fbcdn.net", "fbsbx.com", "facebook.com")    # Facebook เก็บไฟล์แนบไว้แค่โดเมนพวกนี้

# ชนิดที่ "เปิดในเบราว์เซอร์" ได้ — นอกจากนี้บังคับดาวน์โหลด + application/octet-stream เสมอ
#   (ไฟล์ .html/.svg ที่ลูกค้าส่งมา ถ้าเปิดแบบ inline จากโดเมนเรา = รันสคริปต์ในหน้าเราได้)
INLINE_TYPES = {
    "jpg": "image/jpeg", "png": "image/png", "gif": "image/gif", "webp": "image/webp",
    "mp4": "video/mp4", "mov": "video/quicktime", "webm": "video/webm",
    "m4a": "audio/mp4", "aac": "audio/aac", "mp3": "audio/mpeg", "ogg": "audio/ogg", "wav": "audio/wav",
    "pdf": "application/pdf",
}
IMAGE_EXT = {"jpg", "png", "gif", "webp"}
_CT_EXT = {
    "image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png", "image/gif": "gif", "image/webp": "webp",
    "video/mp4": "mp4", "video/quicktime": "mov", "video/webm": "webm",
    "audio/x-m4a": "m4a", "audio/m4a": "m4a", "audio/mp4": "m4a", "audio/aac": "aac", "audio/mpeg": "mp3",
    "audio/mp3": "mp3", "audio/ogg": "ogg", "audio/wav": "wav", "audio/x-wav": "wav",
    "application/pdf": "pdf",
}
_EXT_RE = re.compile(r"^[a-z0-9]{1,8}$")
_FILE_RE = re.compile(r"^(\d+)-(\d+)\.([a-z0-9]{1,8})$")


def max_bytes() -> int:
    try:
        mb = int(getattr(settings, "CHAT_MEDIA_MAX_MB", 25) or 25)
    except Exception:
        mb = 25
    return max(1, mb) * 1024 * 1024


def root() -> Path:
    r = getattr(settings, "CHAT_MEDIA_ROOT", None)
    return Path(r) if r else Path(settings.BASE_DIR) / "private_media" / "chat"


def _dir(src: str) -> Path:
    return root() / ("line" if src == LINE else "fb")


def _model(src: str):
    return GroupChat if src == LINE else FbChat


# ─────────────────────────────────────────────────────────────
#  สถานะ (media_token)
# ─────────────────────────────────────────────────────────────
def parse(tok: str) -> tuple:
    """`media_token` → (สถานะ, [นามสกุลต่อไฟล์ หรือ ""], เวลาลองล่าสุด)"""
    parts = (tok or "").split("|")
    if len(parts) != 3:
        return "", [], 0
    st, exts, at = parts
    try:
        at = int(at or 0)
    except ValueError:
        at = 0
    return st, [("" if e == "-" else e) for e in exts.split(",")] if exts else [], at


def _pack(st: str, exts: list, at: int | None = None) -> str:
    return "%s|%s|%d" % (st, ",".join(e or "-" for e in exts), int(at if at is not None else time.time()))


def path_for(src: str, pk: int, idx: int, ext: str) -> Path | None:
    if not ext or not _EXT_RE.match(ext):
        return None
    return _dir(src) / ("%d-%d.%s" % (int(pk), int(idx), ext))


def stored(src: str, row, idx: int) -> Path | None:
    """ไฟล์ที่โหลดเก็บไว้แล้วของไฟล์แนบลำดับนี้ (ไม่มี = None) — เช็คจาก media_token ไม่ต้องไล่ทั้งโฟลเดอร์"""
    _, exts, _ = parse(row.media_token)
    if idx >= len(exts) or not exts[idx]:
        return None
    p = path_for(src, row.pk, idx, exts[idx])
    return p if p and p.is_file() else None


# ─────────────────────────────────────────────────────────────
#  ไฟล์แนบของแต่ละข้อความ
# ─────────────────────────────────────────────────────────────
def _kind(mime: str, typ: str, fallback: str = "file") -> str:
    m, t = (mime or "").lower(), (typ or "").lower()
    for k in ("image", "video", "audio"):
        if m.startswith(k + "/") or t == k:
            return k
    return fallback if fallback in MEDIA_KINDS else "file"


def attachments(src: str, row) -> list:
    """ไฟล์แนบของข้อความ → [{kind, name, size, url}] (url = ลิงก์ต้นทางของ Facebook · LINE ไม่มี)"""
    if not row.has_media:
        return []
    ex = row.extra if isinstance(row.extra, dict) else {}
    if src == LINE:
        kind = row.msg_type if row.msg_type in MEDIA_KINDS else "file"
        return [{"kind": kind, "name": str(ex.get("fileName") or "")[:120],
                 "size": ex.get("fileSize") or 0, "url": ""}]
    att = ex.get("attachments")
    if isinstance(att, dict):                 # จาก Graph API (รอบซิงก์) = {"data": [...]}
        att = att.get("data")
    out = []
    for a in (att if isinstance(att, list) else [])[:MAX_FILES]:
        if not isinstance(a, dict):
            continue
        url = ((a.get("image_data") or {}).get("url") or (a.get("video_data") or {}).get("url")
               or a.get("file_url") or a.get("url") or "")
        kind = "image" if a.get("image_data") else ("video" if a.get("video_data") else "")
        out.append({"kind": kind or _kind(a.get("mime_type"), a.get("type"), row.msg_type or "file"),
                    "name": str(a.get("name") or "")[:120], "size": a.get("size") or 0, "url": str(url)})
    if not out:
        out = [{"kind": row.msg_type if row.msg_type in MEDIA_KINDS else "file", "name": "", "size": 0, "url": ""}]
    return out


def files_json(o_id: int, src: str, row) -> list:
    """ไฟล์แนบของข้อความ สำหรับหน้าเว็บ/แอป — ลิงก์ผ่าน /connect/api/media (เช็คสิทธิ์ทุกครั้ง) ไม่ใช่ลิงก์ไฟล์ตรง"""
    st, exts, _ = parse(row.media_token)
    out = []
    for i, a in enumerate(attachments(src, row)):
        ext = exts[i] if i < len(exts) else ""
        ready = bool(ext)
        kind = a["kind"]
        if ready and kind == "image" and ext not in IMAGE_EXT:
            kind = "file"                     # ประกาศว่าเป็นรูปแต่ตัวไฟล์ไม่ใช่รูป = ให้ดาวน์โหลดเฉยๆ
        out.append({
            "url": "/connect/api/media?id=%d&m=%s%d.%d" % (int(o_id), src, row.pk, i),
            "kind": kind, "ext": ext,
            "state": "ready" if ready else (st if st in ("gone", "big", "none") else "pending"),
            "name": a["name"], "size": a["size"] if isinstance(a["size"], int) else 0,
        })
    return out


# ─────────────────────────────────────────────────────────────
#  โหลด
# ─────────────────────────────────────────────────────────────
def _sniff(head: bytes) -> str:
    if head[:3] == b"\xff\xd8\xff":
        return "jpg"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head[:5] == b"%PDF-":
        return "pdf"
    return ""


def _ext_for(ctype: str, head: bytes, name: str) -> str:
    """นามสกุลที่จะเก็บ — รูปต้องผ่านการดูไบต์แรกจริง (กันไฟล์อื่นแอบอ้างเป็นรูปแล้วถูกเปิดแบบ inline)"""
    sn = _sniff(head)
    if sn:
        return sn
    ext = _CT_EXT.get((ctype or "").lower(), "")
    if ext and ext not in IMAGE_EXT and ext != "pdf":
        return ext                           # วิดีโอ/เสียง — เชื่อ Content-Type (เสิร์ฟพร้อม nosniff)
    m = re.search(r"\.([A-Za-z0-9]{1,8})$", name or "")
    e = m.group(1).lower() if m else ""
    if e and e not in IMAGE_EXT and e not in INLINE_TYPES:
        return e                             # ชื่อไฟล์บอกนามสกุล (docx/xlsx/zip…) — เสิร์ฟแบบดาวน์โหลดเสมอ
    return "bin"


def _download(url: str, headers: dict | None, dest: Path, pk: int, idx: int, name: str, follow=None):
    """ยิงขอไฟล์แล้วเขียนลงดิสก์ → ("ok", นามสกุล) · ("big", "") · (สถานะ HTTP เป็นตัวเลข, "")
    โยน requests.RequestException เมื่อเน็ตพัง (ผู้เรียกถือเป็นพลาดชั่วคราว)

    `follow` = ฟังก์ชันตรวจลิงก์ปลายทางของ redirect (Facebook ส่งต่อไปโดเมนไฟล์ของมันเองได้)
    ไม่ใส่ = ไม่ตาม redirect เลย · ★ header (token ของ LINE) ไม่ถูกส่งต่อไปโดเมนอื่น"""
    from urllib.parse import urljoin
    cap = max_bytes()
    r = requests.get(url, headers=headers or {}, stream=True, timeout=(5, 30), allow_redirects=False)
    hops = 0
    while r.status_code in (301, 302, 303, 307, 308) and follow and hops < 3:
        nxt = urljoin(url, r.headers.get("Location") or "")
        r.close()
        if not follow(nxt):
            return 403, ""                   # พาไปนอกโดเมนที่ไว้ใจ = ไม่โหลด
        url, hops = nxt, hops + 1
        r = requests.get(url, stream=True, timeout=(5, 30), allow_redirects=False)
    try:
        if r.status_code != 200:
            return r.status_code, ""
        try:
            if int(r.headers.get("Content-Length") or 0) > cap:
                return "big", ""
        except ValueError:
            pass
        dest.mkdir(parents=True, exist_ok=True)
        tmp = dest / ("tmp-%s" % secrets.token_hex(8))
        n, head, big = 0, b"", False
        try:
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(65536):
                    if not chunk:
                        continue
                    n += len(chunk)
                    if n > cap:
                        big = True
                        break
                    if len(head) < 16:
                        head += chunk[:16 - len(head)]
                    f.write(chunk)
            if big or n == 0:
                tmp.unlink(missing_ok=True)
                return ("big", "") if big else (204, "")
            ext = _ext_for((r.headers.get("Content-Type") or "").split(";")[0].strip(), head, name)
            for old in dest.glob("%d-%d.*" % (pk, idx)):     # เคยเก็บเป็นนามสกุลอื่น (ไม่น่าเกิด) — ทิ้งของเก่า
                old.unlink(missing_ok=True)
            os.replace(tmp, dest / ("%d-%d.%s" % (pk, idx, ext)))
            return "ok", ext
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
    finally:
        r.close()


def _line_tokens(row) -> list:
    """token ที่ใช้ขอไฟล์ — ไฟล์เป็นของ "บัญชีที่ได้ยินข้อความ" · ไม่รู้ว่าบัญชีไหน = ลองทุกบัญชี"""
    from dashboard.services import line_channels as ch
    if row.channel:
        t = ch.token_of(row.channel)
        return [t] if t else []
    out = []
    for t in [ch.crm_token()] + ch.group_tokens():
        if t and t not in out:
            out.append(t)
    return out


def _fetch_line(row) -> str:
    toks = _line_tokens(row)
    if not toks:
        return _pack("err", [""])
    name = str((row.extra or {}).get("fileName") or "") if isinstance(row.extra, dict) else ""
    codes = []
    for tok in toks:
        try:
            st, ext = _download(LINE_CONTENT % row.message_id, {"Authorization": "Bearer " + tok},
                                _dir(LINE), row.pk, 0, name)
        except requests.RequestException:
            return _pack("err", [""])
        if st == "ok":
            return _pack("ok", [ext])
        if st == "big":
            return _pack("big", [""])
        codes.append(st)
    # 404 = LINE ลบไฟล์ไปแล้ว · 400 = ไม่ใช่ข้อความของบัญชีนี้ — ลองครบทุก token แล้วยังไม่ได้ = ไม่มีให้โหลดแล้ว
    if codes and all(c in (400, 404) for c in codes):
        return _pack("gone", [""])
    return _pack("err", [""])                 # 401/403 (token) · 202 (วิดีโอยังเตรียมไม่เสร็จ) · 429/5xx


def _fb_url_ok(url: str) -> bool:
    try:
        u = urlparse(url or "")
    except Exception:
        return False
    host = (u.hostname or "").lower()
    return u.scheme == "https" and any(host == h or host.endswith("." + h) for h in FB_HOSTS)


def _fb_fresh(row) -> list:
    """ลิงก์ใหม่ของไฟล์แนบ (ลิงก์เดิมหมดอายุ) — ถามผ่านห้องสนทนาของเพจเรา (ผ่านด่าน meta.py ทุกคำขอ)"""
    from dashboard.services import meta

    from .models import FbProfile
    pid = row.channel or ""
    fp = FbProfile.objects.filter(thread_id=row.thread_id).first()
    psid = (fp.user_id if fp else "") or (row.sender_id if row.direction == FbChat.IN else "")
    if not (pid and psid) or psid == pid:
        return []
    try:
        pt = meta.page_token(pid)
        conv = meta.get("/%s/conversations" % pid, _token=pt, user_id=psid, fields="id")
        tid = str((next(iter(conv.get("data") or []), None) or {}).get("id") or "")
        if not tid:
            return []
        for chunk in meta.paged("/%s/messages" % tid, _token=pt, max_pages=3, limit=100,
                                fields="id,attachments{id,mime_type,name,size,image_data,video_data,file_url}"):
            for m in (chunk.get("data") or []):
                if str(m.get("id") or "") == row.message_id:
                    probe = FbChat(has_media=True, msg_type=row.msg_type, extra={"attachments": m.get("attachments")})
                    return attachments(FB, probe)
    except Exception:
        return []
    return []


def _fetch_fb(row, refresh: bool) -> str:
    atts = attachments(FB, row)
    _, exts, _ = parse(row.media_token)
    exts = (exts + [""] * len(atts))[:len(atts)]
    res = [""] * len(atts)                    # ผลของไฟล์ที่ยังไม่มี: none/gone/big/err
    for i, a in enumerate(atts):
        if exts[i] and stored(FB, row, i):
            continue
        exts[i] = ""
        if not _fb_url_ok(a["url"]):
            res[i] = "none"
            continue
        try:
            st, ext = _download(a["url"], None, _dir(FB), row.pk, i, a["name"], follow=_fb_url_ok)
        except requests.RequestException:
            res[i] = "err"
            continue
        if st == "ok":
            exts[i] = ext
        else:
            res[i] = "big" if st == "big" else ("gone" if st in (403, 404, 410) else "err")
    if refresh and any(r in ("gone", "none") for r in res):
        fresh = _fb_fresh(row)                # ลิงก์หมดอายุ → ขอลิงก์ใหม่ครั้งเดียว
        for i, a in enumerate(fresh[:len(atts)]):
            if exts[i] or res[i] not in ("gone", "none") or not _fb_url_ok(a["url"]):
                continue
            try:
                st, ext = _download(a["url"], None, _dir(FB), row.pk, i, a["name"], follow=_fb_url_ok)
            except requests.RequestException:
                res[i] = "err"
                continue
            if st == "ok":
                exts[i], res[i] = ext, ""
            elif st == "big":
                res[i] = "big"
    missing = [r for e, r in zip(exts, res) if not e]
    if not missing:
        return _pack("ok", exts)
    if "err" in missing:
        return _pack("err", exts)
    if "big" in missing:
        return _pack("big", exts)
    if all(r == "none" for r in missing):
        return _pack("none", exts)
    return _pack("gone", exts)


def ensure(src: str, row, refresh: bool = False, now: float | None = None) -> str:
    """โหลดไฟล์ของข้อความนี้ถ้ายังไม่มี → คืน media_token ใหม่ (บันทึกลงแถวแล้ว)

    ไม่ยิงซ้ำ: มีครบแล้ว · ต้นทางไม่มีแล้ว (gone/big/none) · เพิ่งพลาดชั่วคราวไม่ถึง RETRY_SEC
    """
    now = now or time.time()
    st, _, at = parse(row.media_token)
    if st in ("ok", "gone", "big", "none"):
        if st != "ok" or all(stored(src, row, i) for i in range(len(attachments(src, row)))):
            return row.media_token
    if st == "err" and now - at < RETRY_SEC:
        return row.media_token
    if not row.has_media:
        return row.media_token
    tok = _fetch_line(row) if src == LINE else _fetch_fb(row, refresh)
    _model(src).objects.filter(pk=row.pk).update(media_token=tok[:200])
    row.media_token = tok
    return tok


# ─────────────────────────────────────────────────────────────
#  เสิร์ฟ (เรียกจาก connect_views.api_media หลังเช็คสิทธิ์แล้วเท่านั้น)
# ─────────────────────────────────────────────────────────────
def serve(p: Path, name: str = "", download: bool = False):
    from django.http import FileResponse
    ext = p.suffix[1:].lower()
    ctype = INLINE_TYPES.get(ext)
    inline = bool(ctype) and not download
    base = re.sub(r"[\\/\r\n\"]+", "_", (name or "").strip())[:100]
    if not base or not base.lower().endswith("." + ext):
        base = (base or "file") + "." + ext
    resp = FileResponse(open(p, "rb"), content_type=(ctype if inline else "application/octet-stream"),
                        as_attachment=not inline, filename=base)
    resp["X-Content-Type-Options"] = "nosniff"
    resp["Cache-Control"] = "private, max-age=86400"
    resp["Referrer-Policy"] = "no-referrer"
    if ext != "pdf":                          # เปิดไฟล์ตรงๆ ในแท็บใหม่ = ห้ามรันอะไรทั้งนั้น (ตัวดู PDF ของเบราว์เซอร์ต้องการสิทธิ์ปกติ)
        resp["Content-Security-Policy"] = "default-src 'none'; img-src 'self'; media-src 'self'; sandbox"
    return resp


STATE_TEXT = {
    "gone": "ไฟล์นี้หมดอายุที่ต้นทางแล้ว — เปิดดูในแอป LINE OA / Facebook แทน",
    "big": "ไฟล์ใหญ่เกินกว่าที่ระบบเก็บ — เปิดดูในแอป LINE OA / Facebook แทน",
    "none": "ข้อความนี้ไม่มีไฟล์ให้โหลด",
    "pending": "ยังโหลดไฟล์ไม่สำเร็จ — ระบบจะลองใหม่เอง (ประมาณ 10 นาที)",
}


# ─────────────────────────────────────────────────────────────
#  รอบกวาด (ทุกนาที) + ลบไฟล์ของแชทที่หมดอายุ (วันละครั้ง)
# ─────────────────────────────────────────────────────────────
def pending(days: int, limit: int):
    """ข้อความขาเข้าของลูกค้าที่ยังไม่ได้โหลดไฟล์ — ใหม่→เก่า · LINE กับ FB สลับกันตามเวลา"""
    since = timezone.now() - timedelta(days=days)
    q = Q(media_token="") | Q(media_token__startswith="err|")
    lq = (GroupChat.objects.filter(q, has_media=True, direction=GroupChat.IN, sent_at__gte=since)
          .exclude(chat_type=GroupChat.GROUP).order_by("-sent_at")[:limit])
    fq = (FbChat.objects.filter(q, has_media=True, direction=FbChat.IN, sent_at__gte=since)
          .order_by("-sent_at")[:limit])
    rows = [(LINE, r) for r in lq] + [(FB, r) for r in fq]
    rows.sort(key=lambda x: x[1].sent_at or timezone.now(), reverse=True)
    return rows


def sweep(days: int = PREFETCH_DAYS, limit: int = SWEEP_LIMIT, budget: float = SWEEP_BUDGET) -> dict:
    t0, now = time.time(), time.time()
    out = {"tried": 0, "ok": 0, "gone": 0, "big": 0, "none": 0, "err": 0, "left": 0}
    rows = pending(days, limit * 3)           # เผื่อแถวที่เพิ่งพลาด (รอ RETRY_SEC) ไม่ให้บังแถวใหม่
    for src, row in rows:
        if budget and time.time() - t0 > budget:
            out["left"] += 1
            continue
        st, _, at = parse(row.media_token)
        if st == "err" and now - at < RETRY_SEC:
            continue
        if out["tried"] >= limit:
            out["left"] += 1
            continue
        out["tried"] += 1
        try:
            tok = ensure(src, row, refresh=True, now=now)   # FB ลิงก์หมดอายุ = ขอลิงก์ใหม่ก่อนตัดสินว่า "หมดอายุ"
        except Exception as e:                # พังที่แถวเดียว ไม่ลากทั้งรอบ
            out["err"] += 1
            out["error"] = ("%s: %s" % (type(e).__name__, e))[:160]
            continue
        k = parse(tok)[0] or "err"
        out[k] = out.get(k, 0) + 1
    out["sec"] = round(time.time() - t0, 1)
    return out


def cleanup_files() -> dict:
    """ลบไฟล์ที่แถวแชทถูกลบไปแล้ว (หมดอายุ 60 วัน) + ไฟล์ชั่วคราวค้าง — ข้อมูลส่วนบุคคลต้องหายตามแชท"""
    out = {"deleted": 0, "kept": 0}
    for src in (LINE, FB):
        d = _dir(src)
        if not d.is_dir():
            continue
        files = {}
        for p in d.iterdir():
            if p.name.startswith("tmp-"):
                try:
                    if time.time() - p.stat().st_mtime > 3600:
                        p.unlink(missing_ok=True)
                        out["deleted"] += 1
                except OSError:
                    pass
                continue
            m = _FILE_RE.match(p.name)
            if m:
                files.setdefault(int(m.group(1)), []).append(p)
        pks, alive = list(files), set()
        for i in range(0, len(pks), 1000):
            alive |= set(_model(src).objects.filter(pk__in=pks[i:i + 1000]).values_list("pk", flat=True))
        for pk, ps in files.items():
            if pk in alive:
                out["kept"] += len(ps)
                continue
            for p in ps:
                p.unlink(missing_ok=True)
                out["deleted"] += 1
    return out


BG = True                                     # เทสต์ปิดไว้ (ไม่ให้ thread วิ่งชนฐานข้อมูลทดสอบ)
_RUN = {"busy": False, "at": 0.0}
LAST_KEY, CLEAN_KEY = "chat_media_last", "chat_media_clean"


def _record(res: dict) -> None:
    try:
        from dashboard.services import cache_store
        cache_store.set_kv(LAST_KEY, dict(res, at=timezone.now().isoformat()))
    except Exception:
        pass


def _daily_cleanup() -> dict | None:
    try:
        from dashboard.services import cache_store
        today = timezone.localdate().isoformat()
        last = (cache_store.get_kv(CLEAN_KEY) or {}).get("data") or {}
        if last.get("day") == today:
            return None
        res = cleanup_files()
        cache_store.set_kv(CLEAN_KEY, dict(res, day=today))
        return res
    except Exception as e:
        return {"error": str(e)[:160]}


def sweep_bg() -> dict:
    """เรียกจาก connect.tick ทุกนาที — โหลดไฟล์ใน thread แยก (ห้ามหน่วง cron_tick · กฎเดิม: ของช้าไปไว้ thread)"""
    if not BG or _RUN["busy"] or time.time() - _RUN["at"] < SWEEP_EVERY:
        return {}
    _RUN.update(busy=True, at=time.time())

    def _work():
        res = {}
        try:
            res = sweep()
            c = _daily_cleanup()
            if c:
                res["cleanup"] = c
        except Exception as e:
            res = {"error": str(e)[:200]}
        finally:
            _RUN["busy"] = False
            if res.get("tried") or res.get("error") or res.get("cleanup"):
                _record(res)
            try:
                from django.db import connection
                connection.close()
            except Exception:
                pass

    threading.Thread(target=_work, daemon=True).start()
    return {"started": True}
