# -*- coding: utf-8 -*-
"""ตรวจรูปที่ส่งไปเว็บโชว์รูม (13 ต.ค.69 · เจ้าของ: "รูปหน้าปกไม่มา")

    python scripts/test_showroom_photos.py

ไม่ใช้ฐานข้อมูล — ส่งของหน้าตาเหมือน Car เข้า showroom_sync._photo_urls ตรงๆ ·
โฟลเดอร์ MEDIA_ROOT ชั่วคราว (ตรวจกรณีไฟล์ปกหายจากดิสก์)
"""
import io
import os
import sys
import tempfile
from types import SimpleNamespace

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
os.environ["DB_HOST"] = ""

import django

django.setup()

from django.conf import settings

from cars import gdrive, showroom_sync as S

tmp = tempfile.mkdtemp()
settings.MEDIA_ROOT = tmp
settings.MEDIA_URL = "/media/"
settings.SITE_URL = "https://backend.example"
os.makedirs(os.path.join(tmp, "cars", "CS1"), exist_ok=True)
open(os.path.join(tmp, "cars", "CS1", "cover.jpg"), "wb").write(b"x")
gdrive.photo_url = lambda pid: "https://drive.example/thumb?id=" + pid

ALBUM = [{"file": "abc.jpg", "full": "https://cs.example/images/abc.jpg", "thumb": "https://cs.example/thumbs/abc.jpg"},
         {"file": "def.jpg", "full": "https://cs.example/images/def.jpg", "thumb": "x"}]

fail = []


def eq(got, want, what):
    if got == want:
        print("  ok   %s" % what)
    else:
        fail.append(what)
        print("  FAIL %s → ได้ %r ควรได้ %r" % (what, got, want))


def car(photo="", **extra):
    return SimpleNamespace(code="CS1", photo=SimpleNamespace(name=photo), extra=extra)


print("[1] มีรูปขาย = ใช้รูปขายเหมือนเดิม (ไม่เอารูปปกมาปน)")
eq(S._photo_urls(car("cars/CS1/cover.jpg", sale_photos=["cars/CS1/a.jpg", "DRIVEID"], image_urls=ALBUM)),
   [{"url": "https://backend.example/media/cars/CS1/a.jpg", "key": "cars/CS1/a.jpg"},
    {"url": "https://drive.example/thumb?id=DRIVEID", "key": "DRIVEID"}], "รูปขาย 2 รูป ตามลำดับ")

print("[2] ไม่มีรูปขาย → รูปหน้าปกของระบบ")
eq(S._photo_urls(car("cars/CS1/cover.jpg", image_urls=ALBUM)),
   [{"url": "https://backend.example/media/cars/CS1/cover.jpg", "key": "cars/CS1/cover.jpg"}], "ปกบนดิสก์")
eq(S._photo_urls(car("cars/CS1/cover.jpg", sale_photos=[], image_urls=ALBUM))[0]["key"], "cars/CS1/cover.jpg",
   "รายการรูปขายว่าง = ใช้ปก")
eq(S._photo_urls(car("DRIVEPHOTO")), [{"url": "https://drive.example/thumb?id=DRIVEPHOTO", "key": "DRIVEPHOTO"}],
   "ปกเป็นไฟล์ใน Drive")

print("[3] ไฟล์ปกหายจากดิสก์ → รูปแรกของอัลบัม Car Spend")
eq(S._photo_urls(car("cars/CS1/gone.jpg", image_urls=ALBUM)),
   [{"url": "https://cs.example/images/abc.jpg", "key": "carspend:abc.jpg"}], "ปกหาย = Car Spend รูปแรก")
eq(S._photo_urls(car("", image_urls=ALBUM)), [{"url": "https://cs.example/images/abc.jpg", "key": "carspend:abc.jpg"}],
   "ไม่มีปก = Car Spend รูปแรก")
eq(len(S._photo_urls(car("", image_urls=ALBUM))), 1, "ส่งแค่รูปเดียว (ไม่ส่งทั้งอัลบัม)")

print("[4] ไม่มีอะไรเลย / ข้อมูลเพี้ยน = ไม่ส่งรูป (ไม่พัง)")
eq(S._photo_urls(car("")), [], "ไม่มีรูปเลย")
eq(S._photo_urls(car("", image_urls=[{"file": "x"}, "junk", {"full": "ftp://x"}])), [], "อัลบัมเพี้ยน = ข้าม")
eq(S._photo_urls(SimpleNamespace(code="X", photo=None, extra=None)), [], "photo/extra เป็น None")

print("[5] payload ที่ส่งไปมีรูปปก")
c = car("cars/CS1/cover.jpg")
c.__dict__.update(stage="show", status="active", web_active=True, brand="Toyota", model="Yaris", year=2020,
                  color="ขาว", km=1, plate="1กก1", price=None)
p = S._payload(c)
eq(p.get("photos"), [{"url": "https://backend.example/media/cars/CS1/cover.jpg", "key": "cars/CS1/cover.jpg"}],
   "payload.photos")

print()
print("ผ่านทั้งหมด" if not fail else "ไม่ผ่าน %d ข้อ" % len(fail))
sys.exit(1 if fail else 0)
