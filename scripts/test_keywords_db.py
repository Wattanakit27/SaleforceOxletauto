# -*- coding: utf-8 -*-
"""เทสต์คำที่ระบบจับ ย้ายจากโค้ดมาอยู่ในฐานข้อมูล (★ 21 ต.ค.69 · checkout/kwdb.py · checkout_keywordrule)

    python scripts/test_keywords_db.py

ฐานข้อมูลทดสอบแยก (migration 0045 เติมค่าตั้งต้นให้) · เรียก API ผ่าน test client จริง (signed-cookie session + CSRF จริง)
ข้อความลูกค้าเป็นค่าสมมติทั้งหมด — ห้ามใส่ข้อมูลลูกค้าจริงในไฟล์นี้
"""
import io
import json
import os
import re
import sys
from datetime import timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
os.environ.setdefault("DB_HOST", "")
os.environ.setdefault("DEBUG", "True")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.test.runner import DiscoverRunner  # noqa: E402
from django.test.utils import setup_test_environment  # noqa: E402

setup_test_environment()
_runner = DiscoverRunner(verbosity=0, interactive=False)
_old = _runner.setup_databases()
if "testserver" not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]

from django.contrib.sessions.backends.signed_cookies import SessionStore  # noqa: E402
from django.test import Client  # noqa: E402
from django.utils import timezone  # noqa: E402

from checkout import autotag as AT  # noqa: E402
from checkout import connect as C  # noqa: E402
from checkout import kwdb as KW  # noqa: E402
from checkout import lead_keywords as K  # noqa: E402
from checkout.models import ChatOwner, GroupChat, KeywordRule, LineProfile  # noqa: E402
from dashboard.services import constants as CONST  # noqa: E402

AT.BG = False
CONST.refresh_from_sheet = lambda *a, **k: True
CONST.ALL_SELLERS[:] = ["มัท"]

PASS = FAIL = 0
LEAK = re.compile(r"U[0-9a-f]{32}")


def ok(cond, label, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓", label)
    else:
        FAIL += 1
        print("  ✗", label, ("· " + str(extra)[:400]) if extra != "" else "")


def client(user=None, csrf=False):
    c = Client(enforce_csrf_checks=csrf)
    if user:
        st = SessionStore()
        st["oxlet_user"] = user
        st.save()
        c.cookies[settings.SESSION_COOKIE_NAME] = st.session_key
    return c


def post(c, body):
    r = c.post("/crm/api/auto", json.dumps(body), content_type="application/json", secure=True)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {}


def tagnames(text):
    return {t["tag"] for t in AT.test_text(text)["tags"]}


def row(key):
    return next((r for r in KW.all_rows() if r["key"] == key), None)


U_ADMIN = {"user_id": "admin", "nickname": "แอดมินทดสอบ", "position": "admin"}
U_SELLER = {"user_id": "U" + "1" * 32, "nickname": "มัท", "position": "seller", "seller_name": "มัท"}
NOW = timezone.now()
_N = {"i": 0}


def line_chat(name, msgs):
    _N["i"] += 1
    uid = "U%032x" % (0xdef000 + _N["i"])
    p = LineProfile.objects.create(user_id=uid, display_name=name)
    o = ChatOwner.objects.create(profile=p, last_in_at=NOW, last_at=NOW)
    for j, (d, t, hrs) in enumerate(msgs):
        GroupChat.objects.create(chat_type=GroupChat.USER, message_id="k%d-%d" % (_N["i"], j), sender_id=uid,
                                 msg_type="text", text=t, direction=d, sent_at=NOW - timedelta(hours=hrs))
    return o


A = client(U_ADMIN)

# ═════════════════════════════════════════════════════════════════════
print("\n[1] migration เติมค่าตั้งต้นจากโค้ดลงตาราง")
KW._load(force=True)
ok(KW.source() == "db", "อ่านจากฐานข้อมูล (ไม่ใช่ค่าในโค้ด)", KW.source())
n_def = len(KW.defaults())
ok(KeywordRule.objects.count() == n_def and n_def > 100, "แถวในตาราง = ค่าตั้งต้นทุกแถว (%d)" % n_def,
   KeywordRule.objects.count())
ok(KW.sync_defaults(apply=False) == {"added": 0, "updated": 0}, "ไม่มีอะไรต้องเติม/อัปเดต (ตรงกับโค้ดเป๊ะ)")
dmax = row("model:d-max")
ok(dmax and dmax["parent"] == "Isuzu" and dmax["tag"] and "ดีแม็ก" in dmax["words"], "รุ่น D Max อยู่ใต้ Isuzu + คำไทยครบ", dmax)
bands = KW.rows("income_band")
ok(len(bands) == 5 and bands[0]["extra"] == {"min": 0, "max": 15000} and bands[-1]["extra"]["max"] is None,
   "ช่วงรายได้ 5 ช่วงเดียวกับแดชบอร์ด", [b["name"] for b in bands])
ok(all(r["system"] and not r["edited"] for r in KW.all_rows()), "ทุกแถวเป็นของระบบ ยังไม่มีใครแก้")
_lim = {f.name: f.max_length for f in KeywordRule._meta.fields if getattr(f, "max_length", None)}
_long = [(r["key"], f, len(r[f])) for r in KW.defaults() for f, m in _lim.items() if isinstance(r.get(f), str) and len(r[f]) > m]
ok(not _long, "★ ค่าตั้งต้นทุกแถวสั้นพอดีช่องฐานข้อมูล (SQLite ไม่ตรวจ แต่ Postgres ตรวจ — deploy 21 ต.ค.69 ล้มเพราะเรื่องนี้)", _long)
ok(all(not r["tag"] for r in KW.rows("occupation")) and all(r["tag"] for r in KW.rows("brand")),
   "อาชีพไม่ติดแท็ก · ยี่ห้อติดแท็กโดยปริยาย")

print("\n[2] ตัวจับเดิมยังทำงานเหมือนเดิม (อ่านจากตาราง)")
g = K.extract(["เงินเดือน 25,000 ทำงานโรงงาน อายุงาน 3 ปี ไม่ติดบูโร"])
ok(g.get("income", ("",))[0] == "25000", "รายได้ 25000", g.get("income"))
ok("3" in (g.get("job_tenure", ("",))[0] or ""), "อายุงาน 3 ปี", g.get("job_tenure"))
ok(g.get("pay_history", ("",))[0] == "ไม่ติดบูโร", "ประวัติผ่อน = ไม่ติดบูโร (คำปฏิเสธนำหน้า)", g.get("pay_history"))
ok(C.car_in("สนใจดีแม็กปี 20 ครับ") and C.car_in("สนใจดีแม็กปี 20 ครับ")[0] == "D Max", "รถ = D Max",
   C.car_in("สนใจดีแม็กปี 20 ครับ"))
ok(C.brand_in("อยากได้อีซูซุครับ") == "isuzu", "ยี่ห้อ = isuzu", C.brand_in("อยากได้อีซูซุครับ"))
ok(C.brand_in("เกียร์ออโต้ไหม") == "", "\"เกียร์\" ไม่ใช่ Kia (กติกาเดิมยังอยู่)")

print("\n[3] แท็กลูกค้า: ยี่ห้อ + รุ่น + ช่วงรายได้")
tn = tagnames("สนใจดีแม็กครับ เงินเดือน 30,000")
ok({"D Max", "Isuzu", "รายได้ 25,000–40,000"} <= tn, "ถามดีแม็ก + เงินเดือน 3 หมื่น = 3 แท็ก", tn)
tn = tagnames("อยากได้รถฮอนด้าครับ")
ok("Honda" in tn and not any(t.startswith("รายได้") for t in tn), "บอกแค่ยี่ห้อ = แท็กยี่ห้อ", tn)
tn = tagnames("เกียร์ออโต้ไหม")
ok(not tn, "ไม่มีคำรถ = ไม่ติดแท็ก", tn)

print("\n[4] แท็กจากช่องข้อมูลลูกค้าเปลี่ยนตามค่าปัจจุบัน · คนเอาออกแล้วไม่ติดกลับ")
o = line_chat("ลูกค้าทดสอบ 1", [("in", "สนใจดีแม็กครับ", 2)])
lead = C.lead_of(o)
lead.income = "30000"
lead.save()
msgs = C.messages(o)
auto = dict(lead.auto or {})
AT.apply_lead(lead, auto, AT.found_for(msgs, lead), AT.tag_rows())
ok({"D Max", "Isuzu", "รายได้ 25,000–40,000"} <= set(lead.tags), "ติด 3 แท็ก", lead.tags)
lead.income = "80000"
AT.apply_lead(lead, auto, AT.found_for(msgs, lead), AT.tag_rows())
ok("รายได้ 70,000 ขึ้นไป" in lead.tags and "รายได้ 25,000–40,000" not in lead.tags and "D Max" in lead.tags,
   "★ รายได้เปลี่ยน = ช่วงรายได้เปลี่ยนตาม (ไม่ค้างช่วงเก่า) · แท็กรถคงอยู่", lead.tags)
new = [t for t in lead.tags if t != "Isuzu"]
AT.human_edit(lead, auto, new)
lead.tags = new
AT.apply_lead(lead, auto, AT.found_for(msgs, lead), AT.tag_rows())
ok("Isuzu" not in lead.tags and "D Max" in lead.tags, "★ คนเอาแท็ก Isuzu ออกเอง = ระบบไม่ติดกลับ", lead.tags)

print("\n[5] แก้คำในฐานข้อมูล = ตัวจับเปลี่ยนตามทันที (ไม่ต้อง deploy)")
ok(C.car_in("อยากได้รถกระบะยอดฮิตครับ") is None or C.car_in("อยากได้รถกระบะยอดฮิตครับ")[0] != "D Max",
   "ก่อนแก้: \"กระบะยอดฮิต\" ไม่ใช่ D Max")
st, d = post(A, {"action": "save", "row": {"key": "model:d-max", "words": dmax["words"] + ["กระบะยอดฮิต"]}})
ok(st == 200 and d.get("ok"), "บันทึกคำใหม่ให้ D Max ผ่าน API", d)
ok(C.car_in("อยากได้รถกระบะยอดฮิตครับ") and C.car_in("อยากได้รถกระบะยอดฮิตครับ")[0] == "D Max",
   "★ หลังแก้: \"กระบะยอดฮิต\" = D Max", C.car_in("อยากได้รถกระบะยอดฮิตครับ"))
ok("D Max" in tagnames("อยากได้รถกระบะยอดฮิตครับ"), "แท็ก D Max ติดด้วยคำใหม่")
ok(row("model:d-max")["edited"] and row("model:d-max")["updated_by"] == "แอดมินทดสอบ", "แถวติดป้าย \"แก้จากค่าเดิมแล้ว\" + ใครแก้")
before = K.extract(["เป็นนักบินอวกาศครับ"]).get("occupation")
st, d = post(A, {"action": "save", "row": {"group": "occupation", "name": "นักบินอวกาศ", "value": "นักบินอวกาศ",
                                         "parent": "other", "words": "นักบินอวกาศ"}})
after = K.extract(["เป็นนักบินอวกาศครับ"]).get("occupation")
ok(st == 200 and not before and after and after[0] == "นักบินอวกาศ",
   "★ เพิ่มอาชีพใหม่ = ตัวจับอาชีพเห็นทันที (ล้างของที่จำไว้ให้เอง)", (before, after, d))
okey = (d.get("row") or {}).get("key", "")
ok(okey.startswith("occupation:u-") and not row(okey)["system"], "แถวที่เพิ่มเอง = ไม่ใช่ของระบบ (ลบได้)", okey)

print("\n[6] เพิ่มยี่ห้อ + รุ่นใหม่ · ปิดสวิตช์ติดแท็ก · ปิดใช้ · ลบ")
st, d = post(A, {"action": "save", "row": {"group": "brand", "name": "แบรนด์ทดสอบ", "words": "แบรนด์ทดสอบ"}})
bkey = (d.get("row") or {}).get("key", "")
st2, d2 = post(A, {"action": "save", "row": {"group": "model", "name": "รุ่นทดสอบเอ็กซ์", "parent": "แบรนด์ทดสอบ",
                                           "words": "รุ่นทดสอบเอ็กซ์"}})
mkey = (d2.get("row") or {}).get("key", "")
ok(st == 200 and st2 == 200 and bkey.startswith("brand:u-") and mkey.startswith("model:u-"), "เพิ่มยี่ห้อ + รุ่น", (d, d2))
tn = tagnames("สนใจรุ่นทดสอบเอ็กซ์ครับ")
ok({"รุ่นทดสอบเอ็กซ์", "แบรนด์ทดสอบ"} <= tn, "ถามรุ่นใหม่ = แท็กรุ่น + ยี่ห้อของรุ่น", tn)
st, d = post(A, {"action": "toggle", "key": mkey, "field": "tag", "on": False})
tn = tagnames("สนใจรุ่นทดสอบเอ็กซ์ครับ")
ok(st == 200 and "รุ่นทดสอบเอ็กซ์" not in tn and "แบรนด์ทดสอบ" in tn, "ปิด \"ติดแท็ก\" ของรุ่น = ไม่ติดรุ่น แต่ยังรู้ยี่ห้อ", tn)
st, d = post(A, {"action": "toggle", "key": mkey, "field": "active", "on": False})
ok(st == 200 and C.car_in("สนใจรุ่นทดสอบเอ็กซ์ครับ") is None or (C.car_in("สนใจรุ่นทดสอบเอ็กซ์ครับ") or [""])[0] != "รุ่นทดสอบเอ็กซ์",
   "ปิดใช้แถว = ไม่จับคำนี้แล้ว")
st, d = post(A, {"action": "delete", "key": mkey})
ok(st == 200 and row(mkey) is None, "ลบแถวที่เพิ่มเอง", d)
st, d = post(A, {"action": "delete", "key": "model:d-max"})
ok(st == 400 and "ลบไม่ได้" in (d.get("error") or ""), "★ แถวของระบบลบไม่ได้ (บอกให้ปิดใช้/คืนค่าเดิมแทน)", d)

print("\n[7] คืนค่าเดิม")
st, d = post(A, {"action": "reset", "key": "model:d-max"})
r = row("model:d-max")
ok(st == 200 and not r["edited"] and "กระบะยอดฮิต" not in r["words"], "คืนค่าเดิม = คำที่เพิ่มหาย + ป้าย \"แก้แล้ว\" หาย", d)
ok(not (C.car_in("อยากได้รถกระบะยอดฮิตครับ") and C.car_in("อยากได้รถกระบะยอดฮิตครับ")[0] == "D Max"),
   "หลังคืนค่า \"กระบะยอดฮิต\" ไม่ใช่ D Max แล้ว")
ok(KW.sync_defaults(apply=False) == {"added": 0, "updated": 0}, "ตรงกับค่าตั้งต้นอีกครั้ง")

print("\n[8] ตรวจค่าก่อนบันทึก (ไม่ให้ใส่ของที่ทำให้ตัวจับพัง)")
cases = [
    ({"group": "occupation", "name": "ก", "words": "ก"}, "สั้นเกินไป", "คำ 1 ตัวอักษร"),
    ({"group": "occupation", "name": "x", "pattern": "(abc"}, "เขียนผิด", "regex ผิด"),
    ({"group": "occupation", "name": "x", "pattern": ".*"}, "ข้อความว่าง", "regex ที่จับข้อความว่าง (ติดทุกแชท)"),
    ({"group": "model", "name": "รุ่นลอย", "words": "รุ่นลอยฟ้า"}, "เลือกยี่ห้อ", "รุ่นไม่มียี่ห้อ"),
    ({"group": "custom", "name": "Isuzu", "words": "อีซูซุสวย"}, "ซ้ำ", "ชื่อแท็กซ้ำกับยี่ห้อ"),
    ({"group": "income_band", "name": "ช่วงเพี้ยน", "extra": {"min": 50000, "max": 10000}}, "มากกว่า", "ช่วงรายได้กลับด้าน"),
    ({"group": "deal", "name": "x", "words": "ขายรถด่วน"}, "บทบาท", "หมวดที่มีบทบาท ต้องเลือกบทบาท"),
    ({"group": "nope", "name": "x", "words": "abc"}, "ไม่รู้จักหมวด", "หมวดมั่ว"),
]
for body, frag, label in cases:
    st, d = post(A, {"action": "save", "row": body})
    ok(st == 400 and frag in (d.get("error") or ""), label + " = 400 บอกเหตุผล", (st, d))
st, d = post(A, {"action": "toggle", "key": "type:company", "field": "bogus", "on": True})
ok(st == 400, "สวิตช์ที่ไม่มีจริง = 400")
st, d = post(A, {"action": "delete", "key": "ไม่มีแถวนี้"})
ok(st == 400, "ลบแถวที่ไม่มี = 400 ไม่พัง")

print("\n[9] API: สิทธิ์ · CSRF · ไม่มี LINE id หลุด")
r = A.get("/crm/api/auto", secure=True)
g = r.json()
ok(r.status_code == 200 and len(g["rows"]) >= n_def and g["source"] == "db", "แอดมิน GET = ทุกแถว", r.status_code)
occ = next((x for x in g["rows"] if x["key"] == "occ:driver"), {})
ok(occ.get("readable") and any("ไรเดอร์" in w for w in occ["readable"]), "รูปแบบเดิม (regex) แสดงเป็นคำอ่านง่าย", occ.get("readable"))
ok(not LEAK.search(r.content.decode()), "GET ไม่มี LINE user id หลุด")
r = client(U_SELLER).get("/crm/api/auto", secure=True)
ok(r.status_code == 403, "เซลล์ = 403", r.status_code)
r = client().get("/crm/api/auto", secure=True)
ok(r.status_code == 401, "ไม่ login = 401", r.status_code)
r = client(U_SELLER).post("/crm/api/auto", json.dumps({"action": "save", "row": {"group": "brand", "name": "แฮ็ก",
                                                                                   "words": "แฮ็กเกอร์"}}),
                          content_type="application/json", secure=True)
ok(r.status_code == 403 and not KeywordRule.objects.filter(name="แฮ็ก").exists(), "เซลล์บันทึกคำไม่ได้")
r = client(U_ADMIN, csrf=True).post("/crm/api/auto", json.dumps({"action": "delete", "key": okey}),
                                    content_type="application/json", secure=True)
ok(r.status_code == 403 and row(okey) is not None, "★ ไม่มี CSRF token = 403 ไม่ลบ", r.status_code)
st, d = post(A, {"action": "test", "text": "สนใจดีแม็ก เงินเดือน 30,000 ทำงานโรงงาน 3 ปี"})
fs = {f["field"] for f in d.get("fields") or []}
ok(st == 200 and {"รายได้", "CAR/สูตร"} <= fs and any(t["tag"] == "D Max" for t in d.get("tags") or []),
   "ลองพิมพ์ข้อความ = บอกช่องที่จับได้ + แท็ก (ไม่บันทึก)", d)

print("\n[10] ทุก worker เห็นคำใหม่ (เช็คเวอร์ชันใน KV)")
KW._C["ver"] = "เก่า"
KW._C["at"] = 0
KW._load()
ok(KW._C["ver"] not in ("เก่า", None), "เวอร์ชันไม่ตรง = โหลดใหม่จากตาราง", KW._C["ver"])

print("\n[11] ตารางว่าง/อ่านไม่ได้ = ใช้ค่าในโค้ด ระบบไม่พัง")
KeywordRule.objects.all().delete()
KW._load(force=True)
ok(KW.source() == "defaults" and C.car_in("สนใจดีแม็กครับ")[0] == "D Max", "ไม่มีแถว = ค่าตั้งต้นในโค้ด (ยังจับ D Max ได้)",
   KW.source())
res = KW.sync_defaults()
KW._load(force=True)
ok(res["added"] == n_def and KW.source() == "db", "sync_defaults เติมกลับครบ", res)

print("\n" + "=" * 50)
print("ผ่าน %d · ไม่ผ่าน %d" % (PASS, FAIL))
_runner.teardown_databases(_old)
sys.exit(1 if FAIL else 0)
