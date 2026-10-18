# -*- coding: utf-8 -*-
"""เทสต์กราฟหน้า "ภาพรวม" ของแอป (★ 18 ต.ค.69 · services/mobile_charts.py · GET /api/m/charts)

    python scripts/test_mobile_charts.py

ฐานข้อมูลทดสอบแยก · เรียก endpoint ผ่าน test client จริง (middleware token ครบ)
· ปลอมแค่ผลแดชบอร์ดที่ cron อุ่นไว้ (ขอบระบบ — มาจาก Google Sheets) ไม่ปลอมฟังก์ชันกราฟเอง
"""
import base64
import hashlib
import io
import json
import os
import re
import sys
from datetime import date

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

from django.test import Client  # noqa: E402

from dashboard.services import fetch_dashboard as FD  # noqa: E402
from dashboard.services import mobile_auth as MA  # noqa: E402
from dashboard.services import mobile_charts as MC  # noqa: E402

PASS = FAIL = 0


def ok(cond, label, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓", label)
    else:
        FAIL += 1
        print("  ✗", label, extra)


def arr(pairs):
    """{วัน: ค่า} → list ที่ index = วันที่ (แบบ dailyByMonth ของแดชบอร์ด)"""
    a = [0] * 32
    for d, v in pairs.items():
        a[d] = v
    return a


# ผลแดชบอร์ดปลอม — คีย์เดือนเป็นสตริง (แบบที่อ่านจาก JSON ที่เก็บไว้)
DATA = {
    "meta": {"generatedAt": "2026-10-18T09:00:00+07:00"},
    "dailyByMonth": {
        "9": {"leads": arr({1: 10, 30: 5}), "leadRJ": arr({1: 2}), "bookings": arr({2: 3}), "dones": arr({3: 1}),
              "dealValue": arr({3: 450000})},
        "10": {"leads": arr({1: 7, 18: 4, 25: 99}), "leadRJ": arr({18: 1}), "bookings": arr({5: 2}),
               "dones": arr({6: 1, 18: 2}), "dealValue": arr({6: 300000, 18: 800000})},
    },
    "dailyBySeller": {
        "มัท": {"10": {"leads": arr({2: 3, 18: 1}), "leadRJ": arr({}), "bookings": arr({5: 1}), "dones": arr({6: 1}),
                       "dealValue": arr({6: 300000})}},
        "นวล": {"10": {"leads": arr({1: 50}), "leadRJ": arr({}), "bookings": arr({}), "dones": arr({}), "dealValue": arr({})}},
    },
    "bookingCases": [
        {"date": "2/10/2026", "status": "ปล่อย", "seller": "มัท"},
        {"date": "5/10/2569", "status": "รอผล", "seller": "นวล"},       # ปี พ.ศ.
        {"date": "9/10/2026", "status": "ปล่อย", "seller": "นวล"},
        {"date": "20/10/2026", "status": "จอง", "seller": "มัท"},
        {"date": "30/9/2026", "status": "รีเจ็ก", "seller": "มัท"},      # เดือนก่อน — ไม่นับในเดือนนี้
        {"date": "", "status": "จอง", "seller": "มัท"},                 # ไม่มีวันที่ — ไม่นับ
        {"date": "3/10/2026", "status": "ไม่รู้จัก", "seller": "มัท"},   # สถานะนอกรายการ — ไม่นับ
    ],
    # ฝั่งจัดซื้อ: [เดือน, วัน, ช่องทาง, รับซื้อ1/ไม่รับ2/ยัง0, จัดซื้อ, คุณภาพ]
    "purchaseLeads": [
        [10, 2, "Line@", 1, "พี่หมี", "HOT"],
        [10, 3, "Line@", 2, "พี่หมี", "COOL"],
        [10, 3, "เพจguru", 0, "พี่หมี", "VERY HOT"],
        [10, 0, "TIKTOK", 1, "พี่หมี", "hot"],          # ไม่รู้วัน = นับทั้งเดือน (แบบเว็บ) แต่ไม่ลงกราฟรายวัน
        [10, 18, "Line@", 1, "พี่ต๊าด", "HOT"],
        [10, 25, "Line@", 1, "พี่หมี", "HOT"],          # วันที่ยังไม่ถึง — อยู่ในช่วงเดือนนี้ (เว็บนับ) แต่ไม่ลงกราฟ
        [9, 30, "Line@", 1, "พี่หมี", "HOT"],           # เดือนก่อน
    ],
    # รถซื้อเข้า: [เดือน, วัน, วิธี, จัดซื้อ, …]
    "boughtCars": [
        [10, 4, "Online Line@", "พี่หมี", "City", "", ""],
        [10, 5, "เทิร์นรถ", "พี่หมี", "Yaris", "", ""],
        [10, 5, "นายหน้า", "พี่หมี", "", "", ""],
        [10, 6, "ลูกค้าหน้าร้าน", "พี่ต๊าด", "", "", ""],
        [10, 7, "เต็นท์เพื่อน", "มิว", "", "", ""],
        [9, 20, "Online", "พี่หมี", "", "", ""],
    ],
    "purchaseMethodMap": {"เต็นท์เพื่อน": "online"},
    "purchaseTargets": {"หาเอง": {"พี่หมี": 2, "พี่ต๊าด": 1}, "online": {"พี่หมี": 3, "มิว": 1},
                        "รถเทิร์น": {"พี่หมี": 1}, "ขายหน้าร้าน": {"พี่ต๊าด": 4}},
}
SCORES = [{"name": "มัท", "team": "A", "score": 77.24}, {"name": "นวล", "team": "B", "score": 86.0},
          {"name": "เฟิร์ส", "team": "A", "score": 81.5}]
TODAY = date(2026, 10, 18)
# ขอบระบบ: ตารางคะแนนคิดจากชีต Google — ปลอมตั้งแต่ต้น (build ที่ไม่ส่ง scores มาจะไปอ่านชีตจริงแล้วค้างตามเน็ต)
FD.compute_diligence_scores = lambda *a, **k: SCORES

print("[1] เดือนนี้ = รายวัน · วันที่ยังมาไม่ถึง = None")
r = MC.build("month", data=DATA, today=TODAY, scores=SCORES)
ok(r["daily"] is True and len(r["labels"]) == 31 and r["labels"][0] == "1/10" and r["labels"][-1] == "31/10", "31 วัน 1/10–31/10")
ok(r["series"]["lead"][0] == 7 and r["series"]["lead"][17] == 4, "ลีดวันที่ 1 และ 18 ตรงข้อมูล")
ok(r["series"]["lead"][18] is None and r["series"]["lead"][24] is None, "วันที่ 19 เป็นต้นไป = None (เลข 99 วันที่ 25 ไม่โผล่)")
ok(r["totals"]["lead"] == 11 and r["totals"]["rj"] == 1, "ยอดรวมนับเฉพาะวันที่ผ่านมาแล้ว", r["totals"])
ok(r["totals"]["done"] == 3 and r["totals"]["value"] == 1100000 and r["totals"]["booking"] == 2, "จอง/ปล่อย/ยอดเงินรวม")
ok(r["from"] == "2026-10-01" and r["to"] == "2026-10-31", "ช่วงวันที่ที่ส่งกลับ")

print("[2] โดนัทสถานะเคสจองในช่วง")
pl = {x["status"]: x["n"] for x in r["pipeline"]}
ok(pl["ปล่อย"] == 2 and pl["รอผล"] == 1 and pl["จอง"] == 1, "นับตามสถานะ (ปี พ.ศ. ก็อ่านได้)", pl)
ok(pl["รีเจ็ก"] == 0, "เคสเดือนก่อนไม่นับ")
ok(r["pipelineTotal"] == 4 and r["releasedPct"] == 50, "กลางวง = % ปล่อยแล้ว", (r["pipelineTotal"], r["releasedPct"]))
ok([x["status"] for x in r["pipeline"]] == ["จอง", "รอเซ็นต์", "รอผล", "รอปล่อย", "ปล่อย", "รีเจ็ก"], "เรียงลำดับเดียวกับเว็บ")
ok(all(x["color"].startswith("#") for x in r["pipeline"]), "มีสีทุกสถานะ")

print("[3] เดือนก่อน · ทั้งปี · ค่ามั่ว")
p = MC.build("prev", data=DATA, today=TODAY)
ok(len(p["labels"]) == 30 and None not in p["series"]["lead"], "ก.ย. 30 วัน ไม่มี None (ผ่านมาแล้วทั้งเดือน)")
ok(p["totals"]["lead"] == 15 and p["totals"]["value"] == 450000, "ยอดเดือนก่อน", p["totals"])
y = MC.build("year", data=DATA, today=TODAY)
ok(y["daily"] is False and len(y["labels"]) == 12 and y["labels"][9] == "ต.ค.", "ทั้งปี = รายเดือน 12 เดือน")
ok(y["series"]["lead"][8] == 15 and y["series"]["lead"][9] == 110, "รวมทั้งเดือน (ต.ค. รวมวันที่ 25 ที่ยังไม่ถึงด้วย แบบเว็บ)", y["series"]["lead"][8:10])
ok(y["series"]["lead"][10] is None and y["series"]["lead"][0] == 0, "เดือนที่ยังมาไม่ถึง = None · เดือนที่ไม่มีข้อมูล = 0")
ok(MC.build("มั่ว", data=DATA, today=TODAY)["range"] == "month", "ช่วงที่ไม่รู้จัก = เดือนนี้")
ok(MC.build("month", data={}, today=TODAY)["totals"]["lead"] == 0, "ไม่มีข้อมูลแดชบอร์ด = ศูนย์ ไม่พัง")


def token_for(user):
    v = base64.urlsafe_b64encode(os.urandom(40)).decode().rstrip("=")
    ch = base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).decode().rstrip("=")
    pid, err = MA.start("oxletauto://auth", ch)
    code = re.search(r"code=([^&]+)", MA.hand_off(MA.pending(pid), user)).group(1)
    tok, _rec, err = MA.exchange(code, v, "เทสต์")
    assert tok, err
    return tok


print("[3b] เซลล์ = ของตัวเองเท่านั้น + อันดับคะแนน")
m = MC.build("month", data=DATA, today=TODAY, seller="มัท", scores=SCORES)
ok(m["who"] == "มัท" and m["totals"]["lead"] == 4 and m["totals"]["done"] == 1, "ตัวเลขจาก dailyBySeller ของตัวเอง", m["totals"])
ok(50 not in m["series"]["lead"], "ไม่มีลีดของเซลล์คนอื่นปน")
mp = {x["status"]: x["n"] for x in m["pipeline"]}
ok(m["pipelineTotal"] == 2 and mp["ปล่อย"] == 1 and mp["จอง"] == 1 and mp["รอผล"] == 0, "โดนัท = เคสจองของตัวเองในช่วงนี้", mp)
rk = m["ranking"]["rows"]
ok([x["name"] for x in rk] == ["นวล", "เฟิร์ส", "มัท"] and rk[2]["me"] and rk[2]["rank"] == 3, "อันดับเรียงคะแนน · ไฮไลต์ตัวเอง")
ok(set(rk[0].keys()) == {"rank", "name", "team", "score", "me"}, "อันดับมีแค่ชื่อ/ทีม/คะแนน (ไม่มีลีด/ยอดของคนอื่น)")
ok(rk[2]["score"] == 77.2 and m["ranking"]["month"] == "ต.ค. 69", "คะแนนปัด 1 ตำแหน่ง · บอกเดือน")
ok(MC.build("prev", data=DATA, today=TODAY, scores=SCORES)["ranking"]["month"] == "ก.ย. 69", "เดือนก่อน = อันดับของเดือนก่อน")
ok(MC.build("year", data=DATA, today=TODAY, scores=SCORES)["ranking"]["yearNote"] is True, "ทั้งปี = อันดับเดือนนี้ + บอกว่าคะแนนคิดรายเดือน")
ok(not any(x["me"] for x in r["ranking"]["rows"]), "แอดมิน (ทั้งทีม) ไม่มีแถว \"ของฉัน\"")
ok(MC.build("month", data=DATA, today=TODAY, seller="ไม่มีชื่อนี้", scores=SCORES)["totals"]["lead"] == 0, "เซลล์ที่ไม่มีข้อมูล = ศูนย์ ไม่พัง")

print("[3c] จัดซื้อ — ลีดรับซื้อ · รถซื้อเข้า · เป้า (สูตรเดียวกับ 2 การ์ดในแดชบอร์ด)")
ok(MC.buy_cat("Online Line@") == "online" and MC.buy_cat("เทิร์นรถ") == "รถเทิร์น"
   and MC.buy_cat("ลูกค้าหน้าร้าน") == "ขายหน้าร้าน" and MC.buy_cat("นายหน้า") == "หาเอง", "หมวดวิธีได้รถ = _catOf ของเว็บ")
ok(MC.buy_cat("เต็นท์เพื่อน", {"เต็นท์เพื่อน": "online"}) == "online", "หมวดที่แอดมินตั้งชนะคำในชื่อ")
b = MC.build_buyer("month", data=DATA, today=TODAY, buyer_keys=["พี่หมี"], who="พี่หมี")
ok(b["mode"] == "buy" and b["who"] == "พี่หมี", "โหมดจัดซื้อ + ชื่อเจ้าของ")
ok(b["totals"] == {"lead": 5, "buy": 3, "no": 1, "pending": 1, "bought": 3}, "ตัวเลขรวมของตัวเอง (รวมแถวที่ไม่รู้วัน · ไม่รวมคนอื่น/เดือนก่อน)", b["totals"])
ok(b["series"]["lead"][1] == 1 and b["series"]["lead"][2] == 2 and b["series"]["buy"][1] == 1, "กราฟรายวันลงถูกวัน")
ok(b["series"]["lead"][24] is None and sum(v or 0 for v in b["series"]["lead"]) == 3, "วันที่ยังไม่ถึง = None · แถวไม่รู้วันไม่ลงกราฟรายวัน")
cats = {c["key"]: (c["n"], c["target"]) for c in b["cats"]}
ok(cats == {"หาเอง": (1, 2), "online": (1, 3), "รถเทิร์น": (1, 1), "ขายหน้าร้าน": (0, 0)}, "หมวดวิธี × เป้าของตัวเอง", cats)
ok(b["target"] == 6 and b["buyPct"] == 60, "เป้ารวม · % รับซื้อ = รับซื้อ ÷ ลีดทั้งหมด (แบบเว็บ)", (b["target"], b["buyPct"]))
chs = {c["name"]: c["n"] for c in b["channels"]}
ok(chs == {"Line@": 3, "เพจguru": 1, "TIKTOK": 1} and b["channels"][0]["name"] == "Line@", "ช่องทางเรียงมากไปน้อย", chs)
q = {x["key"]: x["n"] for x in b["quality"]}
ok(q["HOT"] == 3 and q["VERY HOT"] == 1 and q["COOL"] == 1, "คุณภาพไม่สนตัวพิมพ์ (hot = HOT)", q)
rk = b["ranking"]["rows"]
ok([x["name"] for x in rk] == ["พี่หมี", "มิว", "พี่ต๊าด"] and rk[0]["me"] and not rk[1]["me"],
   "อันดับรถซื้อเข้า (เท่ากัน = % ของเป้าสูงกว่าขึ้นก่อน) · ไฮไลต์ตัวเอง", [x["name"] for x in rk])
ok(rk[0]["bought"] == 3 and rk[0]["target"] == 6 and rk[0]["pct"] == 50, "อันดับบอกยอด/เป้า/% ของแต่ละคน", rk[0])
ok(set(rk[0].keys()) == {"rank", "name", "bought", "target", "pct", "me"}, "อันดับไม่มีข้อมูลลูกค้า")
t = MC.build_buyer("month", data=DATA, today=TODAY)
ok(t["who"] == "" and t["totals"]["lead"] == 6 and t["totals"]["bought"] == 5 and t["target"] == 12, "ทั้งทีม (แอดมิน)", t["totals"])
ok(not any(x["me"] for x in t["ranking"]["rows"]), "ทั้งทีมไม่มีแถวของฉัน")
yb = MC.build_buyer("year", data=DATA, today=TODAY, buyer_keys=["พี่หมี"])
ok(yb["daily"] is False and yb["series"]["bought"][8] == 1 and yb["series"]["bought"][9] == 3 and yb["target"] == 6 * 12,
   "ทั้งปี = รายเดือน · เป้า × 12 เดือน", (yb["series"]["bought"][8:10], yb["target"]))
nd = dict(DATA)
nd.pop("purchaseTargets")
ok(MC.build_buyer("month", data=nd, today=TODAY, buyer_keys=["พี่หมี"])["target"] > 0, "ยังไม่เคยตั้งเป้า = ใช้เป้าตั้งต้นของระบบ")
ok(MC.build_buyer("month", data={}, today=TODAY)["totals"]["lead"] == 0, "ไม่มีข้อมูล = ศูนย์ ไม่พัง")

print("[4] endpoint /api/m/charts — สิทธิ์")
MC._SC.clear()
FD.compute_diligence_scores = lambda *a, **k: SCORES   # ขอบระบบ: ตารางคะแนนคิดจากชีต
FD.fetch_dashboard_data = lambda *a, **k: DATA      # ขอบระบบ: ผลแดชบอร์ดที่ cron อุ่นไว้
ADMIN = {"user_id": "admin", "nickname": "admin", "display_name": "admin", "position": "admin"}
SELLER = {"user_id": "U" + "a" * 32, "nickname": "มัท", "display_name": "เซลมัท", "position": "seller", "seller_name": "มัท"}
c = Client()
ok(c.get("/api/m/charts", secure=True).status_code == 401, "ไม่มี token = 401")
rs = c.get("/api/m/charts", secure=True, HTTP_AUTHORIZATION="Bearer " + token_for(SELLER))
js = json.loads(rs.content)
ok(rs.status_code == 200 and js.get("who") == "มัท" and js["totals"]["lead"] == 4, "เซลล์ = 200 + ตัวเลขของตัวเอง", js.get("totals"))
ok(any(x["me"] and x["name"] == "มัท" for x in js["ranking"]["rows"]), "เซลล์เห็นอันดับ ไฮไลต์ตัวเอง")
rs2 = c.get("/api/m/charts?seller=นวล", secure=True, HTTP_AUTHORIZATION="Bearer " + token_for(SELLER))
ok(json.loads(rs2.content).get("who") == "มัท", "ส่ง ?seller= ของคนอื่นมา = ไม่มีผล (ได้ของตัวเองเสมอ)")
from django.contrib.auth.models import User  # noqa: E402
User.objects.create_user("tech")                 # token ของคนงานผูกกับบัญชี Django ตัวจริง (middleware เช็ค)
WORKER = {"user_id": "django_tech", "nickname": "ช่าง", "display_name": "ช่าง", "position": "worker"}
ok(c.get("/api/m/charts", secure=True, HTTP_AUTHORIZATION="Bearer " + token_for(WORKER)).status_code == 403, "คนงาน = 403")
rr = c.get("/api/m/charts?range=year", secure=True, HTTP_AUTHORIZATION="Bearer " + token_for(ADMIN))
j = json.loads(rr.content)
ok(rr.status_code == 200 and j.get("ok") and j.get("range") == "year" and len(j["labels"]) == 12, "แอดมิน = 200 + ข้อมูลทั้งปี")
ok("U" + "a" * 32 not in rr.content.decode(), "ไม่มี LINE user id ในคำตอบ")
BUYER = {"user_id": "U" + "b" * 32, "nickname": "หมี", "display_name": "หมีน้อย", "position": "จัดซื้อ"}
rb = c.get("/api/m/charts?mode=sale", secure=True, HTTP_AUTHORIZATION="Bearer " + token_for(BUYER))
jb = json.loads(rb.content)
ok(rb.status_code == 200 and jb.get("mode") == "buy" and jb.get("who") == "พี่หมี" and jb["totals"]["bought"] == 3,
   "จัดซื้อ = กราฟรับซื้อของตัวเองเสมอ (ชื่อทะเบียน 'หมี' → ชีต 'พี่หมี')", jb.get("totals"))
BUYER2 = {"user_id": "U" + "c" * 32, "nickname": "ใครไม่รู้", "display_name": "x", "position": "จัดซื้อ"}
j2 = json.loads(c.get("/api/m/charts", secure=True, HTTP_AUTHORIZATION="Bearer " + token_for(BUYER2)).content)
ok(j2.get("who") == "ใครไม่รู้" and j2["totals"]["bought"] == 0, "จัดซื้อชื่อที่ชีตไม่มี = ศูนย์ของตัวเอง (ไม่เดาว่าเป็นคนอื่น)")
ra = c.get("/api/m/charts?mode=buy", secure=True, HTTP_AUTHORIZATION="Bearer " + token_for(ADMIN))
ja = json.loads(ra.content)
ok(ra.status_code == 200 and ja.get("mode") == "buy" and ja.get("who") == "" and ja["totals"]["bought"] == 5, "แอดมิน ?mode=buy = จัดซื้อทั้งทีม")
rs3 = c.get("/api/m/charts?mode=buy", secure=True, HTTP_AUTHORIZATION="Bearer " + token_for(SELLER))
ok(json.loads(rs3.content).get("mode") != "buy", "เซลล์ส่ง ?mode=buy = ไม่มีผล (ได้กราฟขายของตัวเอง)")
FD.fetch_dashboard_data = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("ชีตล่ม"))
rr = c.get("/api/m/charts", secure=True, HTTP_AUTHORIZATION="Bearer " + token_for(ADMIN))
ok(rr.status_code == 500 and "ชีตล่ม" in json.loads(rr.content).get("error", ""), "อ่านข้อมูลไม่ได้ = บอกเหตุผล ไม่พังเงียบ")

_runner.teardown_databases(_old)
print()
print("ผ่าน %d · ไม่ผ่าน %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
