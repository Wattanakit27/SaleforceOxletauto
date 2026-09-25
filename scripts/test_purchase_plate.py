# -*- coding: utf-8 -*-
"""ตรวจ 2 กติกาที่ละเอียดอ่อนของรายงานรับซื้อ — รันได้เลย ไม่ต้องต่อเน็ต/ฐานข้อมูล

    python scripts/test_purchase_plate.py

1. `norm_plate` — ทะเบียนในชีตมีชื่อจังหวัดติดมา ต้องตัดออกให้เทียบกับสต๊อกได้
   (ไม่ตัด = จับคู่ได้ 5 จาก 466 คัน · ตัดแล้วได้ 163 — วัดจริง 26 ก.ย.69)
2. `_fold_rare` — ชื่อรุ่นยาวกว่าที่แทบไม่มีใครถามหา ("Corolla Altis" ถาม 1 ครั้ง)
   ต้องยุบเข้าชื่อหลัก ("Altis" ถาม 101) ไม่งั้นรถ 3 คันหายจากตาราง และ Altis เหลือ "พร้อมขาย 0"
   · แต่รุ่นย่อยที่คนถามหาจริง ("Almera Turbo" 33) ต้องไม่ถูกยุบ
"""
import io
import os
import sys

# console ของ Windows เป็น cp874 — เขียนอิโมจิ/ลูกศรลงจอตรงๆ แล้วเทสต์ตายกลางทาง
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
os.environ.setdefault("DB_HOST", "")
os.environ.setdefault("DEBUG", "True")

import django

django.setup()

from dashboard.services import purchase_report as R

fail = []


def eq(got, want, what):
    if got == want:
        print("  ok   %s" % what)
    else:
        fail.append(what)
        print("  FAIL %s → ได้ %r ควรได้ %r" % (what, got, want))


print("norm_plate — ทะเบียนจากชีต (มีจังหวัด) ต้องได้คีย์เท่าฝั่งสต๊อก")
for sheet, stock in [
    ("5ขล739 กรุงเทพมหานคร", "5ขล739"),      # จังหวัดเต็ม เว้นวรรค
    ("4ขย4388กท", "4ขย4388"),                 # จังหวัดย่อ ติดกัน
    ("1 ขด116 กรุงเทพมหานคร", "1ขด116"),      # เว้นวรรคกลางทะเบียนเอง
    ("งร1535ชลบุรี ", "งร1535"),               # ไม่มีเลขนำหน้า
    ("ขน8081ขอนแก่น", "ขน8081"),
    ("8กษ1332 กรุงเทพมหานคร", "8กษ1332"),
]:
    eq(R.norm_plate(sheet), R.norm_plate(stock), "%r == %r" % (sheet, stock))

eq(R.norm_plate(""), "", "ค่าว่าง")
eq(R.norm_plate(None), "", "None")
eq(R.norm_plate("ทะเบียนแดง"), "ทะเบียนแดง", "ข้อความที่ไม่ใช่ทะเบียน — คืนเดิม ไม่พัง")

print("\n_fold_rare — ยุบชื่อยาวที่ดีมานด์ต่ำ เข้าชื่อหลัก")
demand = {"altis": 101, "corollaaltis": 1, "almera": 243, "almeraturbo": 33,
          "civic": 60, "civicfc": 219, "kicks": 5}
shown = {k: k for k in demand}
d, s = R._fold_rare(dict(demand), dict(shown))
eq(d.get("altis"), 102, "Corolla Altis (1) ยุบเข้า Altis → 102")
eq("corollaaltis" in d, False, "คีย์ corollaaltis ถูกเอาออกจากพจนานุกรม")
eq(d.get("almeraturbo"), 33, "Almera Turbo (33 ≥ เกณฑ์) ไม่ถูกยุบ")
eq(d.get("civicfc"), 219, "Civic FC (219) ไม่ถูกยุบเข้า Civic")
eq(d.get("kicks"), 5, "Kicks (5) ไม่มีชื่อหลักให้ยุบ → คงไว้")

print("\n_not_ready — 0 คัน ต้องมีคำกำกับว่ามีรถแต่ยังไม่พร้อมขาย")
eq(R._not_ready({"show": 0, "total": 4}), " (มีอีก 4 คัน ยังไม่พร้อมขาย)", "พร้อมขาย 0 มี 4")
eq(R._not_ready({"show": 5, "total": 5}), "", "พร้อมขายครบ = ไม่ต้องเขียน")
eq(R._not_ready({}), "", "ไม่มีข้อมูล = ไม่พัง")

print("\n_plate_models — แถวแคชรุ่นเก่า (ยังไม่มีช่องทะเบียน) ต้องข้าม ไม่พัง")
from dashboard.services import cache_store

_real = cache_store.get_kv
cache_store.get_kv = lambda k, *a, **kw: {"data": {"boughtCars": [
    [9, 1, "online", "พี่หมี", "Civic FE", "Honda Civic 2023"],          # เก่า: 6 ช่อง
    [9, 2, "online", "พี่หมี", "Yaris Ativ", "Toyota Yaris", "5ขล739 กรุงเทพมหานคร"],
    [9, 3, "online", "พี่หมี", "", "ไม่มีชื่อรุ่น", "1ขด116 กท"],        # AV ว่าง = ข้าม
]}} if k == "main" else _real(k, *a, **kw)
try:
    m = R._plate_models()
    eq(m, {"5ขล739": "Yaris Ativ"}, "เอาเฉพาะแถวที่มีทั้งทะเบียนและชื่อรุ่น")
finally:
    cache_store.get_kv = _real

print("\n%s" % ("ผ่านทั้งหมด" if not fail else "ไม่ผ่าน %d ข้อ: %s" % (len(fail), fail)))
sys.exit(1 if fail else 0)
