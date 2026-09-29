# -*- coding: utf-8 -*-
"""ตรวจ: ส่งการ์ดเข้าหลายกลุ่ม + เป้ารับซื้อรถที่แก้ได้ (30 ก.ย.69)

    python scripts/test_cardline_multi.py

เจ้าของขอ: *"ให้มันส่งไปสองกลุ่มได้ จะมีกลุ่มจัดซื้อพี่หมีกับพี่ต๊าด"* + *"ให้มันสามารถแก้เป้าได้"*

ปลอมเฉพาะ **ขอบระบบ**: `capture_card` (Chromium) และ `requests.post` (LINE)
— ตรรกะการเลือกปลายทาง/ตัดสินว่าสำเร็จ เป็นของเรา ต้องได้รันจริง
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

from django.test import Client, override_settings

from dashboard.services import report_shot as RS

OK = [0, 0]


def ck(name, cond, got=""):
    OK[0] += 1
    if cond:
        OK[1] += 1
        print("  ok   %s" % name)
    else:
        print("  FAIL %s   ได้: %r" % (name, got))


print("[1] เลือกปลายทางจาก config")
ck("กลุ่มหลัก + เพิ่มอีก 2 = 3 ปลายทาง (แท็ก @All ได้ทุกกลุ่ม)",
   RS.card_targets({"group_id": "C1", "group_ids": ["C2", "C3"]})
   == [("C1", True), ("C2", True), ("C3", True)])
ck("ไม่มีกลุ่มเลย → ตกไป test id (แชทส่วนตัว ไม่แท็ก)",
   RS.card_targets({"test_id": "Uabc"}) == [("Uabc", False)])
ck("★ มีกลุ่มแล้ว ไม่ต้องส่งเข้า test id ซ้ำ",
   RS.card_targets({"group_id": "C1", "test_id": "Uabc"}) == [("C1", True)])
ck("ไม่ได้ตั้งอะไรเลย = ไม่มีปลายทาง", RS.card_targets({}) == [])

print("\n[2] ล้างรายการกลุ่มเพิ่มเติม")
ck("ตัดตัวซ้ำกับกลุ่มหลัก + ตัวซ้ำกันเอง",
   RS._clean_gids(["C1", "C2", "C2", ""], "C1") == ["C2"])
ck("★ ตัด U… ทิ้ง (แท็ก @All ในแชท 1:1 ทำไม่ได้ LINE ปฏิเสธทั้งข้อความ)",
   RS._clean_gids(["Uxxx", "C9"], "") == ["C9"])
ck("รับห้อง R… ด้วย", RS._clean_gids(["Rroom"], "") == ["Rroom"])
ck("เพดาน 5 กลุ่ม", len(RS._clean_gids(["C%d" % i for i in range(9)], "")) == 5)

print("\n[3] ส่งจริง — แคปครั้งเดียว ส่งทุกปลายทาง")
CAPS, SENT = [], []


def fake_capture(card_id, cfg=None):
    CAPS.append(card_id)
    return ["/tmp/x.png"]


class Res:
    status_code, text = 200, "{}"


def fake_post(url, headers=None, json=None, timeout=None):
    SENT.append(json.get("to"))
    return Res()


RS.capture_card = fake_capture
RS._public_url = lambda p: "https://example.com/x.png"
from dashboard.services import line_notify as LN

_real_post = LN.requests.post
LN.requests.post = fake_post

with override_settings(LINE_CHANNEL_ACCESS_TOKEN="tok-crm",
                       LINE_PUSH_CHANNEL_ACCESS_TOKEN="tok-push"):
    ok, info = RS.send_card_to_line("bought-card", [("C1", True), ("C2", True)])
    ck("ส่งสำเร็จทั้ง 2 กลุ่ม", ok is True, (ok, info))
    ck("★ แคปรูป **ครั้งเดียว** ไม่ใช่ครั้งต่อกลุ่ม (ไม่งั้นเปิด Chromium ซ้ำ กินแรม VPS)",
       len(CAPS) == 1, CAPS)
    ck("ยิงครบ 2 ปลายทาง", SENT == ["C1", "C2"], SENT)
    ck("บอกจำนวนปลายทางในผล", "2 ปลายทาง" in info, info)

    # ★ กลุ่มหนึ่งล้ม = ยังไม่เรียบร้อย — ไม่งั้น self-heal เลิกลองทั้งที่มีกลุ่มไม่ได้รับ
    CAPS.clear(); SENT.clear()

    def half_post(url, headers=None, json=None, timeout=None):
        to = json.get("to")
        SENT.append(to)
        r = Res()
        if to == "C2":
            r.status_code, r.text = 400, '{"message":"not found"}'
        return r

    LN.requests.post = half_post
    ok2, info2 = RS.send_card_to_line("bought-card", [("C1", True), ("C2", True)])
    ck("★ ถึงกลุ่มเดียว ไม่ถึงอีกกลุ่ม = ok เป็น False", ok2 is False, (ok2, info2))
    ck("บอกว่ากลุ่มไหนล้ม", "C2" in info2, info2)
    ck("แต่ยังส่งให้กลุ่มที่เหลือครบ (ไม่หยุดกลางคัน)", SENT == ["C1", "C2"], SENT)

    LN.requests.post = fake_post
    CAPS.clear(); SENT.clear()
    ok3, _ = RS.send_card_to_line("bought-card", "C9")
    ck("รับ id เดี่ยวแบบเดิมได้ (ของเก่าไม่พัง)", ok3 and SENT == ["C9"], SENT)
    ok4, info4 = RS.send_card_to_line("bought-card", [])
    ck("ไม่มีปลายทาง = ไม่แคปรูปเปล่า", (not ok4) and len(CAPS) == 1, (info4, CAPS))

LN.requests.post = _real_post

print("\n[4] บันทึก config — กลุ่มเพิ่มเติมถูกล้างก่อนเก็บ")
RS.save_card_config("bought-card", {"group_id": "C1", "group_ids": ["C1", "C2", "Uz"],
                                    "enabled": True, "time": "10:00"})
cfg = RS.get_card_config("bought-card")
ck("★ เก็บเฉพาะกลุ่มจริงที่ไม่ซ้ำกลุ่มหลัก", cfg["group_ids"] == ["C2"], cfg["group_ids"])
ck("ค่าอื่นยังอยู่", (cfg["group_id"], cfg["time"]) == ("C1", "10:00"), cfg)
ck("config เก่าที่ไม่มี group_ids อ่านได้ ไม่พัง",
   RS.get_card_config("ไม่เคยตั้ง")["group_ids"] == [])

print("\n[5] เป้ารับซื้อรถ — แก้ได้ผ่าน API")
# โปรเจกต์ใช้ session แบบ signed-cookie → ต้องยัดคุกกี้เอง
# (`client.session.save()` ไม่เขียนคุกกี้ให้ เพราะข้อมูลอยู่ใน key ของคุกกี้เอง)
# และต้อง secure=True เพราะบังคับ https (ไม่งั้นได้ 301) — 2 ข้อนี้จดไว้ใน test_health_send.py แล้ว
from importlib import import_module

from django.conf import settings as _S

c = Client()
_store = import_module(_S.SESSION_ENGINE).SessionStore()
_store["oxlet_user"] = {"user_id": "admin", "nickname": "แอดมิน", "position": "admin"}
_store.save()
c.cookies[_S.SESSION_COOKIE_NAME] = _store.session_key

r = c.get("/api/admin/purchase_targets", secure=True)
d = r.json()
ck("ยังไม่เคยตั้ง = ได้ค่าตั้งต้น + ติดป้ายว่าเป็นค่าตั้งต้น",
   d["ok"] and d["isDefault"] and d["targets"]["หาเอง"]["พี่หมี"] == 12, d)
ck("บอกรายชื่อคน", "พี่ต๊าด" in d["people"], d["people"])

r = c.post("/api/admin/purchase_targets", secure=True,
           data='{"targets":{"หาเอง":{"พี่หมี":20,"พี่ต๊าด":15},"online":{"พี่หมี":5}}}',
           content_type="application/json")
ck("บันทึกได้", r.json().get("ok"), r.json())
d2 = c.get("/api/admin/purchase_targets", secure=True).json()
ck("อ่านกลับได้ค่าที่เพิ่งบันทึก", d2["targets"]["หาเอง"]["พี่หมี"] == 20, d2["targets"])
ck("★ ไม่ใช่ค่าตั้งต้นแล้ว", d2["isDefault"] is False)

bad = c.post("/api/admin/purchase_targets", secure=True,
             data='{"targets":{"หาเอง":{"พี่หมี":-5}}}', content_type="application/json")
ck("★ เป้าติดลบ = ปฏิเสธ (พิมพ์พลาดแล้วเป้าเพี้ยนทั้งตาราง)",
   bad.status_code == 400 and not bad.json().get("ok"), bad.json())
bad2 = c.post("/api/admin/purchase_targets", secure=True,
              data='{"targets":{"หาเอง":{"พี่หมี":"เยอะ"}}}', content_type="application/json")
ck("ค่าที่ไม่ใช่ตัวเลข = ปฏิเสธ พร้อมบอกว่าช่องไหน",
   bad2.status_code == 400 and "พี่หมี" in bad2.json().get("error", ""), bad2.json())
ck("★ ปฏิเสธแล้วของเดิมต้องไม่ถูกทับ",
   c.get("/api/admin/purchase_targets", secure=True).json()["targets"]["หาเอง"]["พี่หมี"] == 20)

c2 = Client()
ck("ไม่ได้ login = 401", c2.get("/api/admin/purchase_targets", secure=True).status_code == 401)

print("\n%s (%d/%d)" % ("ผ่านทั้งหมด" if OK[0] == OK[1] else "มีข้อที่ไม่ผ่าน",
                        OK[1], OK[0]))
runner.teardown_databases(old_cfg)
sys.exit(0 if OK[0] == OK[1] else 1)
