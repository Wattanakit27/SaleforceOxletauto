# -*- coding: utf-8 -*-
"""รูปโปรไฟล์ของช่อง / เพจ — โหลดมาเก็บเอง (30 ก.ย.69 · เจ้าของขอ)

*"อยากให้มันสามารถแสดงเป็นโปรไฟล์ของช่องทางนั้นดีกว่า ไม่ต้องมาทำแบบนี้"*
— ตารางเดิมเขียนชื่อเพจยาวเต็มช่อง ("อ๊อกเล็ตธ์ออโต้ โชว์รูมรถมือสอง สาขาชลบุรี")
อ่านยากและกินที่ · โปรไฟล์ = **รูป + ชื่อ + @username** ซึ่งคนจำได้เร็วกว่ามาก

**★ ทำไมต้องโหลดไฟล์มาเก็บ ไม่เก็บลิงก์**
ลิงก์รูปโปรไฟล์ของ TikTok/Facebook เป็น **signed URL หมดอายุ** (แบบเดียวกับรูปปกคลิป)
เก็บลิงก์ลงฐานข้อมูลแล้วอีกไม่กี่ชั่วโมงก็เปิดไม่ขึ้น · YouTube ไม่หมดอายุแต่เก็บด้วยเลย
เพื่อให้ **รูปทุกแพลตฟอร์มมาจากที่เดียวกัน** ตอนแคปเป็นรูปส่งไลน์ (ไม่ต้องรอโหลดจากเน็ตนอก)

**ใช้ตัวดาวน์โหลดร่วมกับ [covers.py](covers.py)** (`covers._fetch`) — กติกาเดียวกันหมด:
ตรวจ content-type · ตัดไฟล์ใหญ่ผิดปกติ · เขียน `.part` แล้ว `os.replace` (กันไฟล์ครึ่งๆ)
"""
from __future__ import annotations

import logging
import os
import re

from . import covers

log = logging.getLogger(__name__)

SIDES = ("tiktok", "meta", "youtube")
SUBDIR = "avatars"
#  รูปโปรไฟล์จริงราว 5-30 KB — เกินนี้ถือว่าไม่ใช่ (กันโหลดของใหญ่มาทิ้งไว้บนดิสก์)
MAX_BYTES = 300_000

_SAFE = re.compile(r"[^A-Za-z0-9_-]")


def _base() -> str:
    from django.conf import settings
    return os.path.join(str(settings.MEDIA_ROOT), SUBDIR)


def _key(ch_id: str) -> str:
    """ล้าง id ก่อนเอาไปทำชื่อไฟล์ — TikTok open_id มี `-` นำหน้า (เก็บไว้ได้) · กัน `../`"""
    return _SAFE.sub("", str(ch_id or ""))[:80]


def path_for(side: str, ch_id: str) -> str:
    k = _key(ch_id)
    return os.path.join(_base(), side, k + ".jpg") if k else ""


def have(side: str) -> set:
    """id ที่มีรูปแล้ว — อ่านทีเดียวต่อคำขอ ดีกว่าเช็คไฟล์ทีละแถว"""
    try:
        return {e.name[:-4] for e in os.scandir(os.path.join(_base(), side))
                if e.name.endswith(".jpg")}
    except OSError:
        return set()


def url_for(side: str, ch_id: str, cache: set | None = None) -> str:
    """URL ของรูปที่เก็บไว้ · ยังไม่มี = คืน `''` (หน้าเว็บใช้อักษรย่อบนวงกลมสีแทน)"""
    k = _key(ch_id)
    if not k:
        return ""
    if cache is not None:
        if k not in cache:
            return ""
    elif not os.path.exists(path_for(side, ch_id)):
        return ""
    from django.conf import settings
    return "%s%s/%s/%s.jpg" % (settings.MEDIA_URL, SUBDIR, side, k)


def save(side: str, ch_id: str, url: str, overwrite: bool = True) -> bool:
    """โหลดรูปโปรไฟล์มาเก็บ

    ★ `overwrite=True` ต่างจากรูปปกคลิป — **โปรไฟล์เปลี่ยนได้** (ช่องเปลี่ยนรูปเมื่อไหร่ก็ได้)
      ส่วนรูปปกคลิปนิ่งหลังโพสต์ จึงข้ามถ้ามีแล้ว
    """
    k = _key(ch_id)
    if not k or not url or side not in SIDES:
        return False
    p = path_for(side, ch_id)
    if not overwrite and os.path.exists(p):
        return False
    buf = covers._fetch(url, MAX_BYTES)
    if not buf:
        return False
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".part"
        with open(tmp, "wb") as f:
            f.write(buf)
        os.replace(tmp, p)
        return True
    except Exception as e:
        log.debug("เขียนรูปโปรไฟล์ %s/%s ไม่ได้: %s", side, k, e)
        return False


def save_many(side: str, pairs) -> int:
    """`pairs` = [(channel_id, url), …] · คืนจำนวนที่โหลดมาได้จริง"""
    n = 0
    for ch_id, url in pairs:
        if url and save(side, ch_id, url):
            n += 1
    return n


def stats() -> dict:
    return {s: len(have(s)) for s in SIDES}
