# -*- coding: utf-8 -*-
"""เทสต์หน้า Oxlet CRM — /crm/ + /crm/api/* (★ 13 ต.ค.69)

    python scripts/test_crm_page.py

ฐานข้อมูลทดสอบแยก · เรียกผ่าน test client จริง (signed-cookie session + CSRF จริง)
ปลอมแค่ขอบระบบ: ชีต Google (fetch_all_sheets / update_lead_field) + ผลแดชบอร์ดที่ cron อุ่นไว้
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

from checkout import connect as C  # noqa: E402
from checkout.models import ChatFollowup, ChatLead, ChatOwner, ChatOwnerLog, Employee, LineProfile  # noqa: E402
from dashboard.services import constants as CONST  # noqa: E402
from dashboard.services import crm_page as CP  # noqa: E402
from dashboard.services import fetch_dashboard as FD  # noqa: E402
from dashboard.services import google_sheets as GS  # noqa: E402

PASS = FAIL = 0


def ok(cond, label, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓", label)
    else:
        FAIL += 1
        print("  ✗", label, ("· " + str(extra)) if extra != "" else "")


LEAK = re.compile(r"U[0-9a-f]{32}")
NOW = timezone.localtime()
TODAY = NOW.date()


def dmy(d):
    return "%d/%d/%d" % (d.day, d.month, d.year)


L, S = GS.LEADS_COL, GS.SALES_COL


def _width(col):
    return max(v for v in vars(col).values() if isinstance(v, int)) + 8


def lead(seller, code, days_ago, updates=0, z="", admin="", car="City", phone="0811111111", typ="Hot", ch="LINE@"):
    r = [""] * _width(L)
    d = TODAY - timedelta(days=days_ago)
    r[L.sales_rep], r[L.lead_code], r[L.received_date] = seller, code, dmy(d)
    r[L.update_count], r[L.customer_status], r[L.admin_status] = str(updates), z, admin
    r[L.car_inquiry], r[L.phone], r[L.type], r[L.channel] = car, phone, typ, ch
    r[L.last_updated_at] = dmy(d) if updates else ""
    return r


def sale(seller, seq, status, days_ago, customer, code, price=0, release=""):
    r = [""] * (_width(S) + 40)
    r[S.sales_rep], r[S.order_num], r[S.status] = "ชื่อเซลล์ " + seller, str(seq), status
    r[S.date] = dmy(TODAY - timedelta(days=days_ago))
    r[S.customer_name], r[S.lead_code], r[S.sale_price] = customer, code, str(price)
    r[S.car_detail], r[S.channel] = ":Toyota Yaris", "line@"
    if release:
        r[S.car_release_date] = release
    # ชื่อแท็บรายเดือน (fetch_sales_by_month_tabs แนบไว้ที่ช่อง 28) — ยอดปล่อยรายเดือนนับ "ตามแท็บ"
    tab_d = (TODAY - timedelta(days=1)) if release else (TODAY - timedelta(days=days_ago))
    r[28] = FD.MONTHS_FULL_TH[tab_d.month - 1] + "69"
    return r


def d_ago(n):
    return TODAY - timedelta(days=n)


LEADS = [
    lead("มัท", "NLD10-9001", 1, updates=2, z="สนใจมาก"),                       # ติดต่อแล้ว
    lead("มัท", "NLD10-9002", 2, updates=0, car="*เพิ่มเติม* :", phone="ID LINE : abc1"),  # ลีดใหม่ · รถว่าง → CAR/สูตร
    lead("มัท", "NLD10-9003", 3, updates=1, admin="ยกเลิก"),                     # เคสเสีย (ไม่อยู่บนกระดาน)
    lead("มัท", "NLD10-9004", 5, updates=1, z="ส่งมอบ"),                        # จอง/ส่งมอบ (ต้องไม่ตกเป็นเคสเสีย)
    lead("มัท", "NLD10-9005", 4, updates=3, z="รอเช็คเครดิต"),                   # ยื่นไฟแนนซ์
    lead("มัท", "NLD10-9006", 6, updates=1, z="รอมาดูรถ"),                       # นัดดูรถ
    lead("มัท", "NLD10-9007", 40, updates=1, admin="คืนเคส"),                    # เคสเสียเก่ากว่า 14 วัน → ไม่ส่งให้หน้าเว็บ
    lead("นวล", "NLD10-9900", 1, updates=0),                                    # ของคนอื่น
]
L_FORMULA = L.car_formula
LEADS[1][L_FORMULA] = "Civic FE"
SALES = [
    sale("มัท", 1, "จอง", 6, "คุณสมชาย", ":NLD10-9001", price=650000),              # เคสจองเปิดอยู่ (เลขมี ":" ติด)
    sale("มัท", 2, "ปล่อย", 4, "คุณสมหญิง", "NLD10-9010", price=500000, release=dmy(d_ago(1))),
    sale("มัท", 3, "รอผล", 200, "คุณเก่ามาก", "NLD10-8000", price=1),                 # จองเกิน 90 วัน ไม่ใช่ดีลที่กำลังเดิน
    sale("นวล", 1, "จอง", 8, "คุณคนอื่น", "NLD10-9900", price=1),
]
FAKE = {"leads": LEADS, "sales_reports": SALES, "bookings": []}
FD.fetch_all_sheets = lambda *a, **k: FAKE
GS.fetch_all_sheets = lambda *a, **k: FAKE
GS.fetch_sheet = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("ไม่ต่อชีตในเทสต์"))
CONST.refresh_from_sheet = lambda *a, **k: True
CONST.TEAMS.clear()
CONST.TEAMS.update({"A": ["มัท", "โอ๊ต"], "B": ["นวล"]})
CONST.TARGETS.clear()
CONST.TARGETS.update({"มัท": 8, "โอ๊ต": 6, "นวล": 6})
CONST.ALL_SELLERS[:] = ["มัท", "โอ๊ต", "นวล"]
CONST.TEAM_ID.clear()
CONST.TEAM_ID.update({"มัท": "A", "โอ๊ต": "A", "นวล": "B"})


def _dz():
    return {k: [0] * 32 for k in ("leads", "leadRJ", "bookings", "dones", "dealValue")}


DBS = {"มัท": {m: _dz() for m in range(1, 13)}, "นวล": {m: _dz() for m in range(1, 13)}}
DBS["นวล"][TODAY.month]["dealValue"][TODAY.day] = 900000
DBS["นวล"][TODAY.month]["dones"][TODAY.day] = 2
DASH = {"monthlySummary": {str(TODAY.month): {"sellers": {"มัท": {"done": 1, "dealValue": 500000, "pipelineValue": 650000},
                                                          "โอ๊ต": {"done": 3}, "นวล": {"done": 2}}}},
        "dailyBySeller": DBS, "bookingCases": []}
FD.fetch_dashboard_data = lambda: DASH

# ── ฐานข้อมูลทดสอบ ──
MAT = Employee.objects.create(nickname="มัท", position="ทีม A", active=True)
NUAN = Employee.objects.create(nickname="นวล", position="ทีม B", active=True)
p1 = LineProfile.objects.create(user_id="U" + "a" * 32, display_name="ลูกค้ามัท")
chat = ChatOwner.objects.create(profile=p1, owner=MAT, claimed_at=timezone.now(), team="A",
                                awaiting_since=timezone.now() - timedelta(minutes=3), last_in_at=timezone.now(),
                                last_at=timezone.now())
ChatLead.objects.create(chat=chat, code="NLD10-9001", phone="0811111111", customer_name="คุณแชทมัท", car_model="Vios")
ChatOwnerLog.objects.create(chat=chat, action=ChatOwnerLog.ASSIGN, emp_name="มัท", by_name="กวาง", note="จ่ายเบอร์")
ChatOwnerLog.objects.create(chat=chat, action=ChatOwnerLog.REPLY, emp_name="มัท", note="ตอบ")
ChatFollowup.objects.create(chat=chat, kind=ChatFollowup.VIEWING, due_at=timezone.now() + timedelta(hours=2),
                            employee=MAT, emp_name="มัท")
p2 = LineProfile.objects.create(user_id="U" + "b" * 32, display_name="ลูกค้านวล")
chat2 = ChatOwner.objects.create(profile=p2, owner=NUAN, claimed_at=timezone.now(), team="B", last_at=timezone.now())


def client(user=None, csrf=False):
    c = Client(enforce_csrf_checks=csrf)
    if user:
        st = SessionStore()
        st["oxlet_user"] = user
        st.save()
        c.cookies[settings.SESSION_COOKIE_NAME] = st.session_key
    return c


U_MAT = {"user_id": "U" + "1" * 32, "nickname": "มัท", "position": "seller", "seller_name": "มัท"}
U_ADMIN = {"user_id": "admin", "nickname": "", "position": "admin"}

print("\n[1] ตัวช่วยใหม่ + บั๊กวันที่ไม่มีปี")
ok(FD.parse_month_day("9/8") == (8, 9), '"9/8" = 9 ส.ค. (เดิม dateutil อ่านเป็น 8 ก.ย.)', FD.parse_month_day("9/8"))
ok(FD.parse_month_day("10/2") == (2, 10), '"10/2" = 10 ก.พ.', FD.parse_month_day("10/2"))
ok(FD.parse_month_day("13/8") == (8, 13), '"13/8" ยังถูก')
ok(FD.parse_month_day("7/2/26") == (2, 7), 'วันเต็ม "7/2/26" ยังถูก')
ok(FD.parse_month_day("2026-10-12") == (10, 12), "ISO ยังถูก (ไม่ได้เปลี่ยน parse_date เป็นวันขึ้นก่อน)")
ok(CP._pdate_loose("9/8", 2026).isoformat() == "2026-08-09", "_pdate_loose อ่าน d/m ไม่มีปี")
ok(CP._clean_car("*เพิ่มเติม* :", "Civic FE") == "Civic FE", "รถ = หัวข้อแม่แบบ → ใช้ CAR/สูตร")
ok(CP._clean_car(":Toyota Yaris") == "Toyota Yaris", 'ตัด ":" หน้าชื่อรถ')
ok(CP._clean_code(":TLD10-8832") == "TLD10-8832" and CP._clean_code("-") == "", 'เลขลีดตัด ":" · "-" = ว่าง')
ok(CP.sheet_stage({"customerStatus": "ส่งมอบ", "adminStatus": "", "salesStatus": "", "updateCount": 1}) == "booked",
   '"ส่งมอบ" = จอง (ไม่ตกเป็นเคสเสีย ทั้งที่อยู่ในคำ "ไม่ต้องตาม")')

print("\n[2] สิทธิ์เข้าหน้า")
r = client().get("/crm/", secure=True)
ok(r.status_code == 302 and "/login/?next=" in r["Location"], "ไม่ login → /login/?next=", r.status_code)
r = client({"user_id": "django_x", "nickname": "ช่าง", "position": "worker"}).get("/crm/", secure=True)
ok(r.status_code == 302 and r["Location"] == "/track/", "คนงาน → /track/", r.get("Location"))
r = client({"user_id": "U2", "nickname": "ต๊าด", "position": "จัดซื้อ"}).get("/crm/", secure=True)
ok(r.status_code == 302 and r["Location"] == "/buy/", "จัดซื้อ → /buy/", r.get("Location"))
r = client(U_MAT).get("/crm/?seller=นวล", secure=True)
body = r.content.decode("utf-8")
boot = json.loads(re.search(r'id="crm-boot" type="application/json">(.*?)</script>', body, re.S).group(1))
ok(r.status_code == 200 and boot["seller"] == "มัท", "เซลล์ส่ง ?seller= ของคนอื่นมาก็ยังเห็นของตัวเอง", boot.get("seller"))
ok("roster" not in boot and boot["admin"] is False, "เซลล์ไม่ได้รายชื่อเซลล์คนอื่น")
ok("{{" not in body and "{%" not in body, "template ไม่มีแท็กหลุด")
ok(r.cookies.get("csrftoken") is not None, "หน้าตั้งคุกกี้ CSRF (ใช้ POST ไป Connect)")
r = client(U_ADMIN).get("/crm/?seller=นวล", secure=True)
boot = json.loads(re.search(r'id="crm-boot" type="application/json">(.*?)</script>', r.content.decode(), re.S).group(1))
ok(boot["seller"] == "นวล" and boot["admin"] and "roster" not in boot,
   "แอดมินดูของนวลได้ทางลิงก์ · ไม่มีตัวเลือก \"ดูของเซลล์\" แล้ว (20 ต.ค.69 เจ้าของสั่งเอาออก)")
r = client(U_ADMIN).get("/crm/?seller=ใครก็ไม่รู้", secure=True)
boot = json.loads(re.search(r'id="crm-boot" type="application/json">(.*?)</script>', r.content.decode(), re.S).group(1))
ok(boot["seller"] in ("มัท", "โอ๊ต", "นวล", "ADMIN"), "ชื่อมั่ว = ตกไปคนแรกในรายชื่อ ไม่พัง", boot["seller"])

print("\n[3] ข้อมูลของเซลล์ (GET /crm/api/data)")
CP.invalidate()
r = client(U_MAT).get("/crm/api/data?seller=นวล", secure=True)
d = r.json()
raw = r.content.decode("utf-8")
ok(r.status_code == 200 and d["seller"] == "มัท", "เซลล์ได้ข้อมูลของตัวเอง", d.get("seller"))
codes = {l["code"] for l in d["leads"]}
ok("NLD10-9900" not in codes and "NLD10-9900" not in raw, "ไม่มีลีดของคนอื่นหลุดมา")
ok("NLD10-9007" not in codes and d["deadHidden"] == 1, "เคสเสียเก่ากว่า 14 วันไม่ส่ง (บอกเป็นจำนวน)", d.get("deadHidden"))
ok("NLD10-9003" in codes, "เคสเสียที่เพิ่งเกิดยังส่ง (เผื่อเปลี่ยนสถานะ)")
st = {l["code"]: l["stage"] for l in d["leads"]}
ok(st.get("NLD10-9002") == "new" and st.get("NLD10-9001") == "contacted" and st.get("NLD10-9003") == ""
   and st.get("NLD10-9004") == "booked" and st.get("NLD10-9005") == "finance" and st.get("NLD10-9006") == "viewing",
   "คอลัมน์ของลีดจากชีตถูกตามสถานะ Z/แอดมิน", st)
l2 = next(l for l in d["leads"] if l["code"] == "NLD10-9002")
ok(l2["car"] == "Civic FE", "รถที่เป็นหัวข้อแม่แบบ → CAR/สูตร", l2["car"])
ok("adminStatus" not in l2 and "salesStatus" not in l2, "ไม่ส่งช่องที่หน้าเว็บไม่ใช้")
ok(not LEAK.search(raw), "ไม่มี LINE user id หลุด")
ok([c["id"] for c in d["chats"]] == [chat.id], "ลูกค้าแชท = เฉพาะที่มัทดูแล", [c["id"] for c in d["chats"]])
c0 = d["chats"][0]
ok(c0["col"] == "new" and c0["stage"] == "waiting" and c0["awaiting"], "แชทที่ยังไม่ตอบ = คอลัมน์ลีดใหม่ (รอติดต่อ)", c0)
ok(c0["appt"] and c0["appt"]["kind"] == "viewing", "นัดดูรถติดมาที่การ์ด")
deals = d["deals"]
ok([x["name"] for x in deals] == ["คุณสมชาย"] and deals[0]["code"] == "NLD10-9001" and deals[0]["car"] == "Toyota Yaris",
   "เคสจองเปิดอยู่ ≤90 วัน ของตัวเอง · เลข/รถล้าง ':' แล้ว", deals)
k = d["kpi"]
ok(k["target"] == 24 and k["targetMonth"] == 8, "เป้าไตรมาส = เป้าเดือน × 3", k)
ok(k["done"] >= 1 and k["dealValue"] >= 500000, "ยอดปล่อยไตรมาสมาจากยอดของเซลล์ (นับตามแท็บ/วัน)", k)
tt = d["teamTargets"]
ok([r_["name"] for r_ in tt["rows"]] and set(r_["name"] for r_ in tt["rows"]) == {"มัท", "โอ๊ต"} and tt["team"] == "A",
   "เป้าเดือนนี้ = คนในทีมเดียวกันเท่านั้น", tt)
ok(tt["pipelineValue"] == 650000, "ดีลกำลังเดินเดือนนี้ = pipelineValue ชุดเดียวกับแดชบอร์ด")
w = d["week"]
ok(len(w["days"]) == 7 and sum(1 for x in w["days"] if x["today"]) == 1, "ลีดสัปดาห์นี้ 7 วัน มีวันนี้ 1 วัน")
ok(all(x["n"] is None for x in w["days"][TODAY.weekday() + 1:]), "วันที่ยังไม่ถึง = คาดการณ์ (ไม่ใช่ 0)")
ok(d["appts"] and d["appts"][0]["kind"] == "viewing" and d["appts"][0]["id"] == chat.id, "นัดถัดไปจาก Connect")
R = d["report"]["ranges"]
ok(R["r30"]["cur"]["done"] == 1 and R["r30"]["cur"]["dealValue"] == 500000, "รายงาน 30 วัน: ปล่อย 1 คัน ฿500k", R["r30"]["cur"])
ok(R["r30"]["cur"]["b2r"] == 3, "จองถึงปล่อยเฉลี่ย = 3 วัน (จอง 4 วันก่อน · ปล่อยเมื่อวาน)", R["r30"]["cur"]["b2r"])
ok(R["year"]["prev"] is None, "ปีนี้ไม่มีช่วงก่อนให้เทียบ (แดชบอร์ดเก็บปีเดียว)")
rk = [x["name"] for x in R["r30"]["rank"]]
ok(rk and rk[0] == "นวล" and "มัท" in rk, "อันดับเซลล์เรียงยอดปล่อย (มีตัวเองเสมอ)", rk)
ch = R["r30"]["channels"]
ok(ch and ch[0]["name"] == "LINE@", 'ช่องทางเคสปล่อย: "line@" → ชื่อฝั่งลีด "LINE@"', ch)
fun = R["r30"]["funnel"]
ok([f["n"] for f in fun][0] >= [f["n"] for f in fun][-1], "กรวยไม่กลับหัว")
ok(d["zOptions"] and "รอเช็คเครดิต" in d["zOptions"], "ตัวเลือกสถานะลูกค้า = ชุดเดียวกับชีต")

r = client(U_ADMIN).get("/crm/api/data?seller=นวล", secure=True)
ok(r.json()["seller"] == "นวล" and r.json()["admin"] is True, "แอดมินดูของนวลได้")
ok(client().get("/crm/api/data", secure=True).status_code == 401, "ไม่ login → 401")

print("\n[4] รายละเอียดลูกค้าแชท (GET /crm/api/customer)")
before = ChatOwner.objects.get(pk=chat.id).read_at
r = client(U_MAT).get("/crm/api/customer?id=%d" % chat.id, secure=True)
j = r.json()
ok(r.status_code == 200 and j["canEdit"], "เจ้าของเปิดได้")
ok([t["action"] for t in j["timeline"]] == ["assign"], "ประวัติไม่รวมการตอบ (ไม่รก)", [t["action"] for t in j["timeline"]])
ok(not LEAK.search(r.content.decode()), "ไม่มี LINE user id หลุด")
ok(ChatOwner.objects.get(pk=chat.id).read_at == before, "เปิดดูโปรไฟล์ ≠ อ่านแชทแล้ว (ไม่แตะ read_at)")
ok(client(U_MAT).get("/crm/api/customer?id=%d" % chat2.id, secure=True).status_code == 403, "ลูกค้าของคนอื่น → 403")
ok(client(U_ADMIN).get("/crm/api/customer?id=%d" % chat2.id, secure=True).status_code == 200, "แอดมินเปิดได้ทุกคน")

print("\n[5] เลือกสถานะลูกค้าให้ลีดจากชีต (POST /crm/api/lead_status)")
calls = []


def fake_update(code, field, value, month=None, expected_seller=""):
    calls.append((code, field, value, month, expected_seller))
    return {"ok": True, "tab": "ตุลาคม 69", "cell": "Z12"}


GS.update_lead_field = fake_update
c = client(U_MAT)
r = c.post("/crm/api/lead_status", json.dumps({"code": "NLD10-9002", "value": "รอเช็คเครดิต", "seller": "นวล"}),
           content_type="application/json", secure=True)
ok(r.status_code == 200 and r.json()["stage"] == "finance", "บันทึกแล้วได้คอลัมน์ใหม่จากเซิร์ฟเวอร์", r.content[:200])
ok(calls and calls[-1] == ("NLD10-9002", "customer_status", "รอเช็คเครดิต", d_ago(2).month, "มัท"),
   "เขียนช่อง Z ช่องเดียว · เดือนของลีด · เฉพาะแถวของมัท (ส่ง seller คนอื่นมาก็ไม่มีผล)", calls[-1:])
r = c.post("/crm/api/lead_status", json.dumps({"code": "NLD10-9900", "value": "จอง"}), content_type="application/json", secure=True)
ok(r.status_code == 404, "ลีดของคนอื่น → 404 ไม่เขียน", r.status_code)
n = len(calls)
r = c.post("/crm/api/lead_status", json.dumps({"code": "NLD10-9002", "value": "พิมพ์มั่ว"}), content_type="application/json", secure=True)
ok(r.status_code == 400 and len(calls) == n, "สถานะนอกตัวเลือกชีต → 400 ไม่เขียน")
GS.update_lead_field = lambda *a, **k: {"error": "Google 500"}
r = c.post("/crm/api/lead_status", json.dumps({"code": "NLD10-9002", "value": "จอง"}), content_type="application/json", secure=True)
ok(r.status_code == 502 and "Google" in r.json()["error"], "ชีตเขียนไม่ได้ → บอกสาเหตุ (502)")
GS.update_lead_field = fake_update
r = client(U_MAT, csrf=True).post("/crm/api/lead_status", json.dumps({"code": "NLD10-9002", "value": "จอง"}),
                                  content_type="application/json", secure=True)
ok(r.status_code == 403, "ไม่มี CSRF token → 403 (endpoint ไม่ได้ปิด CSRF)", r.status_code)
r = client(U_ADMIN).post("/crm/api/lead_status", json.dumps({"code": "NLD10-9900", "value": "จอง", "seller": "นวล"}),
                         content_type="application/json", secure=True)
ok(r.status_code == 200 and calls[-1][4] == "นวล", "แอดมินเลือกสถานะให้ลีดของเซลล์ที่เลือกดู (เขียนเฉพาะแถวของนวล)")

print("\n[6] ลากการ์ดแชทเปลี่ยนขั้น — ใช้ API Connect ตัวเดิม")
c = client(U_MAT)
c.get("/crm/", secure=True)
r = c.post("/connect/api/crm", json.dumps({"action": "stage", "id": chat.id, "stage": "finance"}),
           content_type="application/json", secure=True)
ok(r.status_code == 200 and r.json()["row"]["stage"] == "finance", "เปลี่ยนเป็นยื่นไฟแนนซ์ได้")
r = c.post("/connect/api/crm", json.dumps({"action": "stage", "id": chat2.id, "stage": "won"}),
           content_type="application/json", secure=True)
ok(r.status_code == 403, "ลากการ์ดของคนอื่นไม่ได้ (403)")
CP.invalidate()
d2 = client(U_MAT).get("/crm/api/data", secure=True).json()
ok(d2["chats"][0]["col"] == "finance", "โหลดใหม่ การ์ดอยู่คอลัมน์ยื่นไฟแนนซ์")

print("\n[7] บั๊กเดิม: หน้า /me/ บันทึกลงชีตไม่ได้ (token ว่าง)")
calls.clear()
r = client(U_MAT).post("/api/seller/update_note", json.dumps({"token": "", "code": "NLD10-9001", "field": "customer_status",
                                                              "value": "ลังเล", "month": TODAY.month}),
                       content_type="application/json", secure=True)
ok(r.status_code == 200 and calls and calls[-1][4] == "มัท", "เซลล์ที่ login (ไม่มี token) บันทึกได้ · เฉพาะแถวของตัวเอง", r.status_code)
r = client().post("/api/seller/update_note", json.dumps({"token": "", "code": "NLD10-9001", "value": "x"}),
                  content_type="application/json", secure=True)
ok(r.status_code == 401, "ไม่ login + ไม่มี token → 401 เหมือนเดิม")
r = client(U_ADMIN).post("/api/seller/update_note", json.dumps({"token": "", "code": "NLD10-9001", "value": "x"}),
                         content_type="application/json", secure=True)
ok(r.status_code == 401, "แอดมินไม่มี token → 401 (แอดมินแก้ผ่านลิงก์เซลล์ /s/<token>/ เหมือนเดิม)")

_runner.teardown_databases(_old)
print("\nผล: ผ่าน %d · ไม่ผ่าน %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
