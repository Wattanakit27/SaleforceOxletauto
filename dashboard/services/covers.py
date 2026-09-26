# -*- coding: utf-8 -*-
"""รูปปกคลิป/โพสต์ — โหลดไฟล์มาเก็บเอง (26 ก.ย.69 · เจ้าของขอ "เอาหน้าปกคลิปมาใส่เลยไม่ได้หรอ")

**ทำไมต้องโหลดมาเก็บ ไม่เก็บแค่ลิงก์**
TikTok (`cover_image_url`) และ Facebook (`full_picture`) ให้ลิงก์รูปแบบ **มีวันหมดอายุ**
(signed URL ของ CDN · TikTok อยู่ได้ราว 6 ชั่วโมง) → เก็บลิงก์ลงฐานข้อมูลแล้วพรุ่งนี้เปิดไม่ขึ้น
ต้องโหลดตัวไฟล์มาเก็บไว้เองตอน sync ครั้งเดียว แล้วเสิร์ฟจาก `/media/` ของเรา

**YouTube ไม่ต้องใช้ไฟล์นี้** — ประกอบลิงก์จาก video id ได้ฟรีและไม่หมดอายุ
(`i.ytimg.com/vi/<id>/mqdefault.jpg`)

ทุกฟังก์ชัน **best-effort** — โหลดไม่ได้/ดิสก์เต็ม = ข้ามเงียบ ห้ามทำให้รอบ sync ล้ม
(รูปปกเป็นของแถม ส่วนตัวเลขคือของจริงที่เสียแล้วเสียเลย)
"""
from __future__ import annotations

import os
import re
import logging

log = logging.getLogger(__name__)

SIDES = ("tiktok", "meta")          # YouTube ไม่ต้องเก็บ (ลิงก์ฟรีไม่หมดอายุ)
SUBDIR = "covers"
MAX_BYTES = 600_000                 # รูปปกจริงราว 20-60 KB · เกินนี้ถือว่าผิดปกติ
TIMEOUT = 8
_OK_TYPES = ("image/jpeg", "image/jpg", "image/png", "image/webp")

# id จาก API เอามาต่อเป็นชื่อไฟล์ตรงๆ ไม่ได้ (กัน ../ และอักขระที่ระบบไฟล์ไม่รับ)
_SAFE = re.compile(r"[^A-Za-z0-9_-]")


def _base() -> str:
    from django.conf import settings
    return os.path.join(str(settings.MEDIA_ROOT), SUBDIR)


def _key(item_id: str) -> str:
    return _SAFE.sub("", str(item_id or ""))[:80]


def path_for(side: str, item_id: str) -> str:
    k = _key(item_id)
    return os.path.join(_base(), side, k + ".jpg") if k else ""


def have(side: str) -> set:
    """id ที่มีไฟล์แล้ว — อ่านทีเดียวต่อคำขอ ดีกว่าเช็คไฟล์ทีละแถว"""
    d = os.path.join(_base(), side)
    try:
        return {e.name[:-4] for e in os.scandir(d) if e.name.endswith(".jpg")}
    except OSError:
        return set()


def url_for(side: str, item_id: str, cache: set | None = None) -> str:
    """URL ของรูปปกที่เก็บไว้ · ยังไม่มี = คืน '' (หน้าเว็บจะใช้แถบสีแทน)"""
    k = _key(item_id)
    if not k:
        return ""
    if cache is not None:
        if k not in cache:
            return ""
    elif not os.path.exists(path_for(side, item_id)):
        return ""
    from django.conf import settings
    return "%s%s/%s/%s.jpg" % (settings.MEDIA_URL, SUBDIR, side, k)


def save(side: str, item_id: str, url: str, overwrite: bool = False) -> bool:
    """โหลดรูปปกมาเก็บ · มีอยู่แล้ว = ข้าม (รูปปกไม่เปลี่ยนหลังโพสต์)"""
    k = _key(item_id)
    if not k or not url or side not in SIDES:
        return False
    p = path_for(side, item_id)
    if not overwrite and os.path.exists(p):
        return False
    try:
        import requests
        r = requests.get(url, timeout=TIMEOUT, stream=True)
        if r.status_code != 200:
            return False
        ctype = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
        if ctype and ctype not in _OK_TYPES:
            return False
        buf = bytearray()
        for chunk in r.iter_content(65536):
            buf += chunk
            if len(buf) > MAX_BYTES:      # ไม่ใช่รูปปกแน่ๆ — ทิ้ง
                return False
        if len(buf) < 500:
            return False
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".part"                 # เขียนไฟล์ชั่วคราวก่อนแล้วค่อยย้าย
        with open(tmp, "wb") as f:        # กันไฟล์ครึ่งๆ ถ้าโดนตัดกลางทาง
            f.write(bytes(buf))
        os.replace(tmp, p)
        return True
    except Exception as e:
        log.debug("โหลดรูปปก %s/%s ไม่ได้: %s", side, k, e)
        return False


def save_many(side: str, pairs) -> int:
    """`pairs` = [(id, url), …] · คืนจำนวนที่โหลดมาใหม่ได้จริง"""
    got = have(side)
    n = 0
    for item_id, url in pairs:
        if _key(item_id) in got:
            continue
        if save(side, item_id, url):
            n += 1
    return n


def stats() -> dict:
    out = {}
    for s in SIDES:
        d = os.path.join(_base(), s)
        try:
            files = [e for e in os.scandir(d) if e.name.endswith(".jpg")]
            out[s] = {"files": len(files), "mb": round(sum(e.stat().st_size for e in files) / 1e6, 1)}
        except OSError:
            out[s] = {"files": 0, "mb": 0.0}
    return out
