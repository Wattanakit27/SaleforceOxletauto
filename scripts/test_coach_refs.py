# -*- coding: utf-8 -*-
"""ตรวจแท็บอ้างอิงในไฟล์โค้ช (29 ก.ย.69)

    python scripts/test_coach_refs.py

**ข้อที่สำคัญที่สุดคือข้อ [1]** — `coach_refs` เป็นที่เดียวในโปรเจกต์ที่ยิง `:clear`
ใส่ชื่อแท็บผิดครั้งเดียว = ประวัติ `บันทึกโค้ช` 1,695 แถว หายและกู้ไม่ได้
จึงต้องพิสูจน์ว่า **ปฏิเสธก่อนยิงเน็ต** ไม่ใช่ปฏิเสธหลังยิง

ปลอมที่ `requests.Session` (ขอบระบบ) ไม่ปลอมฟังก์ชันของเราเอง — บทเรียนเดิม
ที่เคยปลอม `fetch_profile` ทั้งฟังก์ชันแล้วบั๊กจริงหลุดไป 3 วัน
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
os.environ.setdefault("DB_HOST", "")
os.environ.setdefault("DEBUG", "True")

import django

django.setup()

from django.test.utils import setup_test_environment
from django.test.runner import DiscoverRunner

setup_test_environment()
runner = DiscoverRunner(verbosity=0, interactive=False)
old_cfg = runner.setup_databases()

from checkout import coach_refs as CR
from checkout.models import Employee, LineGroup, LineProfile

OK = [0, 0]


def ck(name, cond, got=""):
    OK[0] += 1
    if cond:
        OK[1] += 1
        print("  ok   %s" % name)
    else:
        print("  FAIL %s   ได้: %r" % (name, got))


# ---- ปลอมที่ "ขอบระบบ" เท่านั้น: HTTP + การขอ token ------------------
# ★ ห้ามปลอม `CR._api` — รอบแรกผมปลอมมันแล้วเทสต์ผ่าน 27/27 ทั้งที่โค้ดจริงพัง
#   (`_api()` คืน `(base_url, headers)` ไม่ใช่ session) → ต้องให้ `_api()` ตัวจริงรัน
CALLS = []


class FakeResp:
    status_code, text = 200, "{}"

    def json(self):
        return {}


def _rec(kind):
    def f(url, **kw):
        CALLS.append((kind, url))
        return FakeResp()
    return f


import requests

import dashboard.services.google_sheets as GS

requests.post, requests.put, requests.get = _rec("post"), _rec("put"), _rec("get")
GS.ensure_sheet_tab = lambda sid, tab: True


class _Cred:
    token = "tok-ปลอม"

    def refresh(self, req):
        pass


GS._get_credentials = lambda: _Cred()

print("[1] ★ ด่านกันลบประวัติ — ต้องปฏิเสธ *ก่อน* ยิงเน็ต")
for bad in ("บันทึกโค้ช", "Sheet A — Log", "", "พนักงาน ", "Sheet1"):
    CALLS.clear()
    try:
        CR._overwrite(bad, ["a"], [["1"]])
        ck("แท็บ %r ต้องถูกปฏิเสธ" % bad, False, "ไม่ raise")
    except ValueError:
        ck("แท็บ %r ถูกปฏิเสธ + ไม่ยิงคำขอเลย" % bad, CALLS == [], CALLS)
    except Exception as e:
        ck("แท็บ %r ถูกปฏิเสธด้วย ValueError" % bad, False, type(e).__name__)

print("\n[2] แท็บที่อนุญาต — ล้างแล้วเขียนทับ")
for good in (CR.EMP_TAB, CR.GRP_TAB):
    CALLS.clear()
    CR._overwrite(good, ["a"], [["1"]])
    kinds = [k for k, _ in CALLS]
    ck("%s: clear ก่อน แล้วค่อยเขียน" % good, kinds == ["post", "put"], kinds)
    # ★ ชื่อแท็บไทยต้องถูก quote ใน URL — ไม่ quote = Google ตอบ 404
    import urllib.parse as _up
    enc = _up.quote(good)
    ck("%s: ยิงไปแท็บนั้นจริง (ชื่อไทยถูก quote)" % good,
       all(enc in u for _, u in CALLS), [u for _, u in CALLS])

print("\n[3] แถวพนักงาน")
e1 = Employee.objects.create(nickname="เฟิร์ส", display_name="First OxletAuto",
                             position="ทีม A", active=True)
e2 = Employee.objects.create(nickname="บิว", display_name="Bew", position="ทีม B")
Employee.objects.create(nickname="ลาออกแล้ว", position="", active=False)
LineProfile.objects.create(user_id="Uold_first", employee=e1, channel="")
LineProfile.objects.create(user_id="Unew_first", employee=e1, channel="push")
LineProfile.objects.create(user_id="Ucustomer", channel="crm")     # ลูกค้า ไม่ผูกคน

rows = CR.employee_rows(seniors=["เฟิร์ส", "อุ้ม"])
by = {r[0]: r for r in rows}
ck("ครบทุกคนรวมคนลาออก (ติดป้ายไว้)", len(rows) == 3, len(rows))
ck("★ ซีเนียร์ถูกติดป้าย", by["เฟิร์ส"][3] == "ซีเนียร์", by["เฟิร์ส"][3])
ck("จูเนียร์ไม่ติดป้าย (ช่องว่าง)", by["บิว"][3] == "", by["บิว"][3])
ck("คนลาออก = ยังทำงานอยู่ 'ไม่'", by["ลาออกแล้ว"][4] == "ไม่", by["ลาออกแล้ว"][4])
# เรียงตามตัวอักษร (ไม่ใช่ลำดับแถวใน DB ซึ่งไม่การันตี) → รันซ้ำได้ผลเดิมทุกครั้ง
ck("★ รวมไอดีทุกบัญชีของคนเดียว + บอกจำนวน · เรียงคงที่",
   (by["เฟิร์ส"][5], by["เฟิร์ส"][6]) == ("2", "Unew_first Uold_first"),
   by["เฟิร์ส"][5:7])
ck("★ ไอดีลูกค้าไม่หลุดเข้าตารางพนักงาน",
   all("Ucustomer" not in r[6] for r in rows))
ck("คนที่ยังไม่ผูก LINE = 0 บัญชี ช่องไอดีว่าง",
   (by["บิว"][5], by["บิว"][6]) == ("0", ""), by["บิว"][5:7])
ck("จำนวนคอลัมน์ตรงกับหัวตาราง",
   all(len(r) == len(CR.EMP_COLUMNS) for r in rows))

print("\n[4] แถวกลุ่ม")
LineGroup.objects.create(group_id="C7d9", name="Sale Coaching Room", kind="coaching",
                         kind_auto=True, channels=["push"])
LineGroup.objects.create(group_id="Cabc", name="จ่ายเบอร์", kind="lead",
                         kind_auto=False, channels=["crm", "push"])
g = {r[0]: r for r in CR.group_rows()}
ck("แปลประเภทงานเป็นภาษาคน", g["C7d9"][2] == "ห้องโค้ชเซลล์", g["C7d9"][2])
ck("★ บอกว่าประเภทนี้ระบบเดาให้ หรือคนตั้งเอง",
   (g["C7d9"][3], g["Cabc"][3]) == ("ใช่", "ไม่"), (g["C7d9"][3], g["Cabc"][3]))
ck("ลิสต์บอทในกลุ่ม", g["Cabc"][4] == "crm push", g["Cabc"][4])
ck("จำนวนคอลัมน์ตรงกับหัวตาราง",
   all(len(r) == len(CR.GRP_COLUMNS) for r in CR.group_rows()))

print("\n[5] push() โหมดดูเฉยๆ ต้องไม่แตะชีต")
CALLS.clear()
r = CR.push(apply=False, seniors=["เฟิร์ส"])
ck("★ ไม่ยิงคำขอเลย", CALLS == [], CALLS)
ck("บอกจำนวนที่จะเขียน", (r["employees"], r["groups"]) == (3, 2),
   (r["employees"], r["groups"]))
ck("บอกว่ายังไม่ได้เขียน", r["applied"] is False)
ck("รายงานคนที่ยังไม่ผูก LINE", "บิว" in r["noIds"], r["noIds"])

CALLS.clear()
r = CR.push(apply=True, seniors=["เฟิร์ส"])
ck("apply=True → เขียน 2 แท็บ (clear+put ต่อแท็บ)", len(CALLS) == 4, CALLS)
ck("แตะแค่แท็บ snapshot ไม่แตะประวัติ",
   all("บันทึกโค้ช" not in u for _, u in CALLS))

print("\n%s (%d/%d)" % ("ผ่านทั้งหมด" if OK[0] == OK[1] else "มีข้อที่ไม่ผ่าน",
                        OK[1], OK[0]))
runner.teardown_databases(old_cfg)
sys.exit(0 if OK[0] == OK[1] else 1)
