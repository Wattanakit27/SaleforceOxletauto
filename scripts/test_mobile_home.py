# -*- coding: utf-8 -*-
"""เทสต์หน้า "วันนี้" ของแอปมือถือ — GET /api/m/home (★ 11 ต.ค.69)

    python scripts/test_mobile_home.py

ฐานข้อมูลทดสอบแยก · เรียกผ่าน test client จริง (middleware Bearer token ครบทั้งสาย)
ปลอมแค่ขอบระบบ: ชีต Google (fetch_all_sheets / ชีตจัดซื้อ) + ผลแดชบอร์ดที่ cron อุ่นไว้ + ตารางคะแนน
"""
import base64
import hashlib
import io
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

from django.contrib.auth.models import User  # noqa: E402
from django.contrib.sessions.backends.signed_cookies import SessionStore  # noqa: E402
from django.test import Client  # noqa: E402
from django.utils import timezone  # noqa: E402

from cars import roles  # noqa: E402
from cars.models import Car  # noqa: E402
from checkout import leadflow as LF  # noqa: E402
from checkout.models import CarMovement, ChatLead, ChatOwner, CheckIn, Employee, LeadTask, LineProfile  # noqa: E402
from dashboard.services import constants as CONST  # noqa: E402
from dashboard.services import fetch_dashboard as FD  # noqa: E402
from dashboard.services import google_sheets as GS  # noqa: E402
from dashboard.services import mobile_auth as MA  # noqa: E402
from dashboard.services import mobile_home as MH  # noqa: E402
from dashboard.services import purchase_followup, purchase_report  # noqa: E402

LF.BG_SLOW = False
PASS = FAIL = 0


def ok(cond, label):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓", label)
    else:
        FAIL += 1
        print("  ✗", label)


LEAK = re.compile(r"U[0-9a-f]{32}")
NOW = timezone.localtime()
TODAY = NOW.date()
M = TODAY.month


def dmy(d):
    return "%d/%d/%d" % (d.day, d.month, d.year)


# ── ขอบระบบ: ชีต Google ─────────────────────────────────────────────
L, S = GS.LEADS_COL, GS.SALES_COL


def _width(col):
    return max(v for v in vars(col).values() if isinstance(v, int)) + 8


def lead(seller, code, days_ago, updates=0, z="", admin="", car="City", phone="0811111111", typ="Hot"):
    r = [""] * _width(L)
    d = TODAY - timedelta(days=days_ago)
    r[L.sales_rep], r[L.lead_code], r[L.received_date] = seller, code, dmy(d)
    r[L.update_count], r[L.customer_status], r[L.admin_status] = str(updates), z, admin
    r[L.car_inquiry], r[L.phone], r[L.type] = car, phone, typ
    r[L.last_updated_at] = dmy(d) if updates else ""
    return r


def sale(seller, seq, status, days_ago, customer, plate, sign=""):
    r = [""] * (_width(S) + 40)
    r[S.sales_rep], r[S.order_num], r[S.status] = "ชื่อเซลล์ " + seller, str(seq), status
    r[S.date] = dmy(TODAY - timedelta(days=days_ago))
    r[S.customer_name], r[S.license_plate], r[S.sign_date] = customer, plate, sign
    r[S.car_detail], r[S.lead_code] = "Toyota Yaris", "NLD10-77%02d" % seq
    return r


LEADS = [
    lead("มัท", "NLD10-9001", 1, updates=2, z="สนใจมาก"),          # ตามต่อ
    lead("มัท", "NLD10-9002", 2, updates=0),                        # ยังไม่โทรเลย → ด่วนสุด
    lead("มัท", "NLD10-9003", 3, updates=1, admin="ยกเลิก"),         # เคสปิด ไม่ต้องตาม
    lead("มัท", "NLD10-9004", 5, updates=1, z="จอง"),               # จองแล้ว ไม่ต้องตาม
    lead("มัท", "NLD10-9005", 40, updates=0),                       # เก่ากว่า 14 วัน ไม่นับ
    lead("นวล", "NLD10-9006", 1, updates=0),                        # ของคนอื่น
]
SALES = [
    sale("มัท", 1, "จอง", 6, "คุณสมชาย", "1กก1111"),               # จองค้าง ยังไม่เซ็น 6 วัน → ดีลค้าง
    sale("มัท", 2, "ปล่อย", 4, "คุณสมหญิง", "2ขข2222", sign=dmy(TODAY)),
    sale("นวล", 1, "จอง", 8, "คุณคนอื่น", "3คค3333"),
]
FD.fetch_all_sheets = lambda *a, **k: {"leads": LEADS, "sales_reports": SALES}
GS.fetch_all_sheets = FD.fetch_all_sheets          # หน้า CRM (ตัวเขียนสถานะลูกค้า) อ่านผ่าน google_sheets
GS.fetch_sheet = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("ไม่ต่อชีตในเทสต์"))
CONST.refresh_from_sheet = lambda *a, **k: None
CONST.ALL_SELLERS.clear() if hasattr(CONST.ALL_SELLERS, "clear") else None
for n in ("มัท", "นวล"):
    if isinstance(CONST.ALL_SELLERS, set):
        CONST.ALL_SELLERS.add(n)
    else:
        CONST.ALL_SELLERS.append(n)
CONST.TARGETS.clear()
CONST.TARGETS.update({"มัท": 8, "นวล": 6})

# ผลแดชบอร์ดที่ cron อุ่นไว้ (คีย์เดือนเป็นสตริง = แบบที่อ่านจากที่เก็บจริง)
_daily = {k: [0] * 32 for k in ("leads", "leadRJ", "bookings", "dones", "dealValue")}
_daily["leads"][TODAY.day], _daily["bookings"][TODAY.day], _daily["dones"][TODAY.day] = 37, 4, 2
_daily["dealValue"][TODAY.day] = 980000
DASH = {"monthlySummary": {str(M): {
    "totalLeads": 812, "totalBookings": 61, "totalDone": 40, "totalDealValue": 21000000,
    "sellers": {"มัท": {"lead": 44, "booking": 6, "done": 3, "dealValue": 1500000, "notCalled": 2}}}},
    "dailyByMonth": {str(M): _daily}}
FD.fetch_dashboard_data = lambda: DASH
FD.compute_diligence_scores = lambda *a, **k: [
    {"name": "นวล", "score": 81.2, "sDone": 30, "sJong": 8, "sConv": 20, "sVel": 7, "sFollow": 10, "sBan": 6.2},
    {"name": "มัท", "score": 64.5, "sDone": 6, "sJong": 2, "sConv": 20, "sVel": 7, "sFollow": 19.5, "sBan": 10},
]

# ชีตจัดซื้อ
purchase_followup.fetch_open_cases = lambda days=18: [
    {"owner": "พี่หมี", "name": "คุณขายรถ", "car": "City 2019", "phone": "0899999999", "code": "OC-7001",
     "age": 2, "talked": False, "model_std": "City 4 ประตู"},
    {"owner": "พี่หมี", "name": "คุณคุยแล้ว", "car": "Yaris 2020", "phone": "0888888888", "code": "OC-7002",
     "age": 6, "talked": True, "model_std": ""},
    {"owner": "พี่ต๊าด", "name": "ของคนอื่น", "car": "Vios", "phone": "0877777777", "code": "OC-7003",
     "age": 1, "talked": False, "model_std": ""},
]
purchase_report.market_gap = lambda *a, **k: [
    {"key": "city4", "name": "City 4 ประตู", "demand": 120, "show": 0, "total": 2, "recent": 0, "score": 120.0}]


# ── ข้อมูลในฐานข้อมูลทดสอบ ──────────────────────────────────────────
MAT = Employee.objects.create(nickname="มัท", position="ทีม A", work_start="09:00", active=True)
NUAN = Employee.objects.create(nickname="นวล", position="ทีม B", work_start="00:00", active=True)
LATE_GUY = Employee.objects.create(nickname="เก้า", position="ทีม B", work_start="00:01", active=True)
FUTURE = Employee.objects.create(nickname="โอ๊ต", position="ทีม A", work_start="23:59", active=True)
OFFDAY = Employee.objects.create(nickname="บิว", position="ทีม B", work_start="00:00", active=True,
                                 day_off=MH.THAI_DAYS[TODAY.weekday()])
BOSS = Employee.objects.create(nickname="เจ้านาย", position="", work_start="", active=True, track_checkin=False)
CheckIn.objects.create(employee=MAT, user_id="U" + "1" * 32, date_iso=TODAY, time_hm="09:12", work_start="09:00",
                       status="late", checkin_at=timezone.now())
CheckIn.objects.create(employee=NUAN, user_id="U" + "2" * 32, date_iso=TODAY, time_hm="08:40", work_start="08:45",
                       status="ontime", checkin_at=timezone.now())

prof = LineProfile.objects.create(user_id="U" + "c" * 32, display_name="ลูกค้าแชท")
chat = ChatOwner.objects.create(profile=prof, owner=MAT, claimed_at=timezone.now(), team="A",
                                awaiting_since=timezone.now() - timedelta(minutes=20),
                                due_at=timezone.now() - timedelta(minutes=15), last_in_at=timezone.now())
ChatLead.objects.create(chat=chat, code="NLD10-9002", phone="0811111111")
prof2 = LineProfile.objects.create(user_id="U" + "d" * 32, display_name="ลูกค้าคนอื่น")
other = ChatOwner.objects.create(profile=prof2, owner=NUAN, claimed_at=timezone.now(), team="B")
ChatLead.objects.create(chat=other, code="NLD10-9001", phone="0822222222")   # เลขเดียวกันแต่เป็นแชทของคนอื่น

LeadTask.objects.create(code="NLD10-9010", run="9010", seller=MAT, seller_name="มัท", customer="คุณใบใหม่",
                        car="Civic", posted_at=timezone.now() - timedelta(minutes=20),
                        due_at=timezone.now() - timedelta(minutes=5))                      # เลยเวลา
LeadTask.objects.create(code="NLD10-9011", run="9011", seller=MAT, seller_name="มัท", customer="คุณรอโทร",
                        posted_at=timezone.now(), due_at=timezone.now() + timedelta(minutes=12))
LeadTask.objects.create(code="NLD10-9012", run="9012", seller=MAT, seller_name="มัท", customer="รายงานแล้ว",
                        posted_at=timezone.now(), due_at=timezone.now() + timedelta(minutes=12),
                        first_report_at=timezone.now(), reports=1, last_report="รอตอบ")
LeadTask.objects.create(code="NLD10-9013", run="9013", seller=MAT, seller_name="มัท", customer="ใบทดลอง",
                        posted_at=timezone.now(), due_at=timezone.now() + timedelta(minutes=12), card={"demo": True})
LeadTask.objects.create(code="NLD10-9014", run="9014", seller=NUAN, seller_name="นวล", customer="ของนวล",
                        posted_at=timezone.now(), due_at=timezone.now() + timedelta(minutes=12))


def car(code, stage, days=0, **kw):
    Car.objects.create(code=code, plate=kw.pop("plate", ""), brand="Toyota", model="Yaris", year=2020,
                       stage=stage, need_photo=kw.pop("need_photo", False), need_content=False, **kw)
    Car.objects.filter(code=code).update(stage_since=timezone.now() - timedelta(days=days))
    return Car.objects.get(code=code)


car("CS9001", "repair", 12, plate="1กข1001")                         # คิวช่าง ค้างนาน
car("CS9002", "parts", 1, plate="1กข1002", priority="urgent_high")  # คิวช่าง ด่วนมาก
car("CS9003", "repair", 2, plate="1กข1003", need_tire=True)         # คิวช่าง ติดธง → ขึ้นก่อน
car("CS9004", "show", 30, plate="1กข1004")                          # พร้อมขาย (ไม่ใช่คิวช่าง)
car("CS9005", "wash", 9, plate="1กข1005")
car("CS9006", "sold", 1, plate="1กข1006", status="sold")            # ขายแล้ว ไม่นับ
CarMovement.objects.create(car=Car.objects.get(code="CS9004"), plate_text="1กข1004", borrower_name="มัท",
                           purpose="ตรวจขนส่ง", checked_out_at=timezone.now() - timedelta(hours=3),
                           status=CarMovement.PENDING_HUMAN)
CarMovement.objects.create(car=Car.objects.get(code="CS9005"), plate_text="1กข1005", borrower_name="นวล",
                           purpose="ส่งลูกค้า", checked_out_at=timezone.now(), status=CarMovement.PENDING_HUMAN)

tech = User.objects.create_user("chang1", password="x", first_name="ช่างหนึ่ง")
roles.set_user_role(tech, roles.TECH)
wash = User.objects.create_user("wash1", password="x", first_name="ล้างหนึ่ง")
roles.set_user_role(wash, roles.CARWASH)
norole = User.objects.create_user("nobody1", password="x", first_name="ไม่มีบทบาท")


def token_for(user):
    v = base64.urlsafe_b64encode(os.urandom(40)).decode().rstrip("=")
    ch = base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).decode().rstrip("=")
    pid, err = MA.start("oxletauto://auth", ch)
    rec = MA.pending(pid)
    code = re.search(r"code=([^&]+)", MA.hand_off(rec, user)).group(1)
    tok, _rec, err = MA.exchange(code, v, "เทสต์")
    assert tok, err
    return tok


def home(user):
    t = token_for(user)
    r = Client().get("/api/m/home", HTTP_AUTHORIZATION="Bearer " + t, secure=True)
    return r.status_code, (r.json() if r["Content-Type"].startswith("application/json") else {}), r.content


SELLER = {"user_id": "U" + "1" * 32, "nickname": "มัท", "display_name": "เซลมัท", "position": "seller",
          "seller_name": "มัท"}
ADMIN = {"user_id": "admin", "nickname": "admin", "display_name": "admin", "position": "admin"}
BUYER = {"user_id": "U" + "3" * 32, "nickname": "หมี", "display_name": "หมีน้อย", "position": "จัดซื้อ"}
WORKER = {"user_id": "django_chang1", "nickname": "ช่างหนึ่ง", "display_name": "ช่างหนึ่ง", "position": "worker"}
WASHER = {"user_id": "django_wash1", "nickname": "ล้างหนึ่ง", "display_name": "ล้างหนึ่ง", "position": "worker"}
NOROLE = {"user_id": "django_nobody1", "nickname": "ไม่มีบทบาท", "display_name": "x", "position": "worker"}

try:
    # ─────────────────────────────────────────────────────────────
    print("\n[1] บทบาท — แอปจัดแท็บตามนี้")
    ok(MH.role_of(ADMIN) == "admin", "admin → admin")
    ok(MH.role_of({"position": "ผู้บริหาร", "nickname": "x"}) == "admin", "ผู้บริหาร → admin")
    ok(MH.role_of(WORKER) == "worker", "worker → worker")
    ok(MH.role_of(BUYER) == "buyer", "ตำแหน่ง 'จัดซื้อ' → buyer")
    ok(MH.role_of({"position": "seller", "nickname": "ต๊าด"}) == "buyer", "ชื่อเล่นในรายชื่อจัดซื้อ → buyer")
    ok(MH.role_of(SELLER) == "seller", "เซลล์ → seller")
    t = token_for(SELLER)
    r = Client().get("/api/m/me", HTTP_AUTHORIZATION="Bearer " + t, secure=True).json()
    ok(r["me"].get("role") == "seller", "/api/m/me ส่ง role มาด้วย")

    print("\n[2] สิทธิ์")
    r = Client().get("/api/m/home", secure=True)
    ok(r.status_code == 401, "ไม่มี token → 401")
    r = Client().get("/api/m/home", HTTP_AUTHORIZATION="Bearer ผิด", secure=True)
    ok(r.status_code == 401 and r.json().get("relogin"), "token ผิด → 401 + relogin")

    # ─────────────────────────────────────────────────────────────
    print("\n[3] เซลล์")
    st, d, raw = home(SELLER)
    ok(st == 200 and d.get("role") == "seller", "200 · role=seller")
    ok(not d.get("errors"), "ไม่มีส่วนไหนพัง (%s)" % (d.get("errors") or ""))
    k = d.get("kpi") or {}
    ok(k.get("lead") == 44 and k.get("booking") == 6 and k.get("done") == 3 and k.get("target") == 8,
       "ยอดเดือนนี้จาก monthlySummary (คีย์เดือนเป็นสตริง) + เป้าจากตั้งค่าเซลล์")
    sc = d.get("score") or {}
    ok(sc.get("rank") == 2 and sc.get("of") == 2 and sc.get("total") == 64.5, "คะแนน + อันดับ 2/2")
    ok(len(sc.get("parts") or []) == 6 and sc["parts"][0]["max"] == 30, "แยก 6 ด้าน (จบ เต็ม 30)")
    f = d.get("follow") or {}
    codes = [u["code"] for u in f.get("urgent") or []]
    ok(codes[:1] == ["NLD10-9002"] and f["urgent"][0]["reason"] == "ยังไม่โทรเลย", "ตามด่วน: ยังไม่โทรขึ้นก่อน")
    ok("NLD10-9003" not in codes and "NLD10-9004" not in codes, "ยกเลิก/จองแล้ว ไม่อยู่ในตามด่วน")
    ok("NLD10-9005" not in codes, "ลีดเก่ากว่า 14 วันไม่นับ (เหมือนข้อความ LINE)")
    ok("NLD10-9006" not in codes, "ไม่มีลีดของคนอื่น")
    ok(f.get("notCalled") == 1, "นับยังไม่โทร = 1")
    ok(f["urgent"][0].get("chatId") == chat.id, "ลีดที่คุยใน Connect (แชทของตัวเอง) มีปุ่มเปิดแชท")
    u1 = next((u for u in f["urgent"] if u["code"] == "NLD10-9001"), {})
    ok(u1 and not u1.get("chatId"), "เลขเดียวกันแต่เป็นแชทของคนอื่น → ไม่ให้เปิด")
    deals = f.get("deals") or []
    ok(len(deals) == 1 and deals[0]["customer"] == "คุณสมชาย" and deals[0]["reason"] == "ค้างเซ็น",
       "ดีลค้าง: จองแล้วยังไม่เซ็น 6 วัน (ไม่มีของคนอื่น)")
    tk = d.get("tasks") or {}
    ok(tk.get("open") == 2 and tk.get("late") == 1, "ใบจ่ายลีด: ค้าง 2 (เลยเวลา 1) · ไม่นับใบทดลอง/ที่รายงานแล้ว")
    ok([x["code"] for x in tk.get("rows") or []][:1] == ["NLD10-9010"], "ใบที่เลยเวลาขึ้นก่อน")
    ok(all(x["code"] != "NLD10-9014" for x in tk.get("rows") or []), "ไม่มีใบของคนอื่น")
    ch = d.get("chats") or {}
    ok(ch.get("mineWaiting") == 1 and ch.get("mineOverdue") == 1, "แชท: ลูกค้าของฉันรอตอบ 1 (เลยเวลา 1)")
    ok(ch.get("team") == "A" and ch.get("onDuty") == (ch.get("dutyToday") == "A"), "ทีม/เวรวันนี้")
    ci = d.get("checkin") or {}
    ok(ci.get("status") == "late" and ci.get("time") == "09:12" and ci.get("lateMin") == 12, "เช็คชื่อ: สาย 12 นาที")
    mo = d.get("myOut") or []
    ok([x["code"] for x in mo] == ["CS9004"] and mo[0]["hours"] >= 2.9, "รถที่ฉันเบิกอยู่ (ไม่รวมของนวล)")
    ok(not LEAK.search(raw.decode("utf-8")), "ไม่มี LINE user id ในคำตอบ")

    print("\n[3b] โหลดตามด่วนแยกคำขอ (หน้าแรกไม่ต้องรออ่านชีตลีด)")
    t = token_for(SELLER)
    r = Client().get("/api/m/home?lazy=1", HTTP_AUTHORIZATION="Bearer " + t, secure=True).json()
    ok(r.get("followLazy") is True and "follow" not in r and (r.get("kpi") or {}).get("lead") == 44,
       "lazy=1 → ไม่มี follow แต่บอก followLazy · ส่วนอื่นมาครบ")
    r = Client().get("/api/m/home?part=follow", HTTP_AUTHORIZATION="Bearer " + t, secure=True).json()
    ok([u["code"] for u in (r.get("follow") or {}).get("urgent") or []][:1] == ["NLD10-9002"] and "kpi" not in r,
       "part=follow → เฉพาะตามด่วน (ลำดับเดียวกับก้อนเต็ม)")
    tb = token_for(BUYER)
    r = Client().get("/api/m/home?part=follow", HTTP_AUTHORIZATION="Bearer " + tb, secure=True).json()
    ok(r.get("ok") and "follow" not in r, "บทบาทอื่นขอ part=follow → ไม่ได้อะไร")

    print("\n[3c] บันทึกสถานะลูกค้า (Z) จากรายการตามด่วน (★ 13 ต.ค.69)")
    zo = (Client().get("/api/m/home?part=follow", HTTP_AUTHORIZATION="Bearer " + t, secure=True).json()
          .get("follow") or {}).get("zOptions") or []
    ok(len(zo) >= 10 and "สนใจมาก" in zo, "ตามด่วนส่งตัวเลือกสถานะลูกค้า (ชุดเดียวกับ dropdown ชีต) มาด้วย")
    _writes = []
    _gs_upd = GS.update_lead_field

    def _fake_upd(code, field, value, month=None, expected_seller=None):
        _writes.append((code, field, value, expected_seller))
        return {"ok": True, "tab": "ตุลาคม 69", "cell": "Z10"}

    GS.update_lead_field = _fake_upd
    try:
        cz = Client(enforce_csrf_checks=True)          # แอปไม่มีคุกกี้ CSRF — token ต้องผ่านได้เอง
        r = cz.post("/crm/api/lead_status", {"code": "NLD10-9002", "value": "สนใจมาก"},
                    content_type="application/json", HTTP_AUTHORIZATION="Bearer " + t, secure=True)
        ok(r.status_code == 200 and r.json().get("ok"), "เซลล์บันทึกสถานะจากแอปได้ (token ข้าม CSRF)"
           + ("" if r.status_code == 200 else " [%s %s]" % (r.status_code, r.content[:120])))
        ok(_writes[-1:] == [("NLD10-9002", "customer_status", "สนใจมาก", "มัท")],
           "  …เขียนช่อง Z ช่องเดียว ของแถวที่ชื่อเซลล์ = คนที่ login")
        n = len(_writes)
        r = cz.post("/crm/api/lead_status", {"code": "NLD10-9006", "value": "สนใจมาก"},
                    content_type="application/json", HTTP_AUTHORIZATION="Bearer " + t, secure=True)
        ok(r.status_code == 404 and len(_writes) == n, "ลีดของคนอื่น → 404 ไม่เขียนอะไร")
        r = cz.post("/crm/api/lead_status", {"code": "NLD10-9002", "value": "ค่ามั่ว"},
                    content_type="application/json", HTTP_AUTHORIZATION="Bearer " + t, secure=True)
        ok(r.status_code == 400 and len(_writes) == n, "ค่านอก dropdown → 400 ไม่เขียน")
        r = Client(enforce_csrf_checks=True).post("/crm/api/lead_status", {"code": "NLD10-9002", "value": "ลังเล"},
                                                  content_type="application/json", secure=True)
        ok(r.status_code in (401, 403) and len(_writes) == n, "ไม่มี token → เขียนไม่ได้")
        r = cz.post("/crm/api/lead_status", {"code": "NLD10-9002", "value": "สนใจมาก"},
                    content_type="application/json", HTTP_AUTHORIZATION="Bearer " + token_for(WORKER), secure=True)
        ok(r.status_code == 403 and len(_writes) == n, "คนงานเขียนสถานะลูกค้าไม่ได้")
    finally:
        GS.update_lead_field = _gs_upd

    print("\n[4] ส่วนหนึ่งพัง ไม่ลากทั้งหน้า")
    _bak = FD.compute_diligence_scores
    MH._slow.clear()
    FD.compute_diligence_scores = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("พัง"))
    st, d, _ = home(SELLER)
    ok(st == 200 and "score" in (d.get("errors") or {}) and (d.get("kpi") or {}).get("lead") == 44,
       "ตารางคะแนนพัง → errors.score · ส่วนอื่นยังมา")
    FD.compute_diligence_scores = _bak
    MH._slow.clear()

    # ─────────────────────────────────────────────────────────────
    print("\n[5] แอดมิน")
    st, d, raw = home(ADMIN)
    ok(st == 200 and d.get("role") == "admin" and not d.get("errors"), "200 · role=admin · ไม่มีส่วนพัง (%s)"
       % (d.get("errors") or ""))
    nb = d.get("numbers") or {}
    ok(nb.get("today") == {"lead": 37, "leadRJ": 0, "booking": 4, "done": 2, "dealValue": 980000},
       "ยอดวันนี้จาก dailyByMonth")
    ok((nb.get("monthTotal") or {}).get("lead") == 812, "ยอดทั้งเดือน")
    ck = d.get("staff") or {}
    names = [x["name"] for x in ck.get("missing") or []]
    ok(ck.get("came") == 2 and ck.get("late") == 1 and ck.get("ontime") == 1, "มาแล้ว 2 (สาย 1)")
    ok("เก้า" in names and "โอ๊ต" not in names, "ยังไม่มา = เฉพาะคนที่เลยเวลาเข้างานแล้ว (ยังไม่ถึงเวลาไม่นับ)")
    ok("บิว" not in names and ck.get("dayoff") == 1, "คนวันหยุดไม่นับเป็นขาด")
    ok("เจ้านาย" not in names, "คนที่ไม่ต้องเช็คชื่อ (ผู้บริหาร) ไม่นับ")
    cs = d.get("cars") or {}
    ok(cs.get("total") == 5 and cs.get("outNow") == 2, "รถในระบบ 5 (ไม่นับขายแล้ว) · ออกนอกลาน 2")
    stuck = [x["code"] for x in cs.get("stuck") or []]
    ok(stuck[:1] == ["CS9001"] and "CS9004" not in stuck,
       "รถค้างนานสุดขึ้นก่อน · รถพร้อมขายไม่นับว่าค้าง (กติกาเดียวกับบอร์ด)")
    ok((d.get("chats") or {}).get("queue") is not None, "ตัวเลขแชท/ห้องพัก")
    ok(not LEAK.search(raw.decode("utf-8")), "ไม่มี LINE user id ในคำตอบ")

    # ─────────────────────────────────────────────────────────────
    print("\n[6] คนงาน")
    st, d, raw = home(WORKER)
    q = d.get("queue") or {}
    codes = [x["code"] for x in q.get("rows") or []]
    ok(st == 200 and d.get("role") == "worker", "200 · role=worker")
    ok(q.get("roleLabel") == "ช่าง" and set(codes) == {"CS9001", "CS9002", "CS9003"},
       "คิวช่าง = รถในสเตปที่ช่างเป็นเจ้าของงาน (ซ่อม/อะไหล่) เท่านั้น")
    ok(codes == ["CS9003", "CS9002", "CS9001"], "เรียงแบบบอร์ด: ติดธงก่อน → ด่วนมาก → ค้างนาน")
    st, d, _ = home(WASHER)
    ok([x["code"] for x in (d.get("queue") or {}).get("rows") or []] == ["CS9005"], "ฝ่ายล้างรถเห็นคิวล้างรถ")
    st, d, _ = home(NOROLE)
    ok(st == 200 and (d.get("queue") or {}).get("rows") == [] and (d.get("queue") or {}).get("note"),
       "ยังไม่มีบทบาท → คิวว่าง + บอกให้แอดมินตั้งบทบาท")

    # ─────────────────────────────────────────────────────────────
    print("\n[7] จัดซื้อ")
    st, d, raw = home(BUYER)
    p = d.get("purchase") or {}
    ok(st == 200 and d.get("role") == "buyer" and not d.get("errors"), "200 · role=buyer")
    ok([c["code"] for c in p.get("cases") or []] == ["OC-7001", "OC-7002"], "เห็นเฉพาะเคสของตัวเอง · ยังไม่โทรขึ้นก่อน")
    ok(p.get("notCalled") == 1 and (p.get("gap") or [{}])[0].get("name") == "City 4 ประตู", "ยังไม่โทร 1 · รุ่นขาดตลาด")
    ok(isinstance((p.get("cases") or [{}])[0].get("gapDemand"), int), "เคสบอกว่ารุ่นนี้ตลาดถามหาเท่าไหร่")

    # ─────────────────────────────────────────────────────────────
    print("\n[8] หน้ารถในแอป — ข้อมูลเบิก-คืน")
    t = token_for(SELLER)
    r = Client().get("/track/api/m/car/CS9004", HTTP_AUTHORIZATION="Bearer " + t, secure=True)
    j = r.json()
    co = j.get("checkout") or {}
    ok(r.status_code == 200 and (co.get("open") or {}).get("mine") is True, "รถที่ฉันเบิกอยู่ → open.mine")
    ok(len(co.get("purposes") or []) >= 5 and co.get("outMin", 0) >= 1 and co.get("shotsOut"),
       "ประเภทงาน + จำนวนรูปขั้นต่ำ + มุมที่ต้องถ่าย")
    r = Client().get("/track/api/m/car/CS9005", HTTP_AUTHORIZATION="Bearer " + t, secure=True).json()
    ok((r.get("checkout") or {}).get("open", {}).get("mine") is False and r["checkout"]["open"]["who"] == "นวล",
       "รถที่คนอื่นเบิก → บอกชื่อ (ไม่ใช่ของฉัน)")
    r = Client().get("/track/api/m/car/CS9001", HTTP_AUTHORIZATION="Bearer " + t, secure=True).json()
    ok((r.get("checkout") or {}).get("open") is None, "รถที่อยู่ลาน → open = null")

    print("\n[9] /api/seller/today ยังใช้ได้หลังย้ายไปใช้ leadflow.seller_tasks")
    b = Client()
    sst = SessionStore()
    sst["oxlet_user"] = SELLER
    sst.save()
    b.cookies[settings.SESSION_COOKIE_NAME] = sst.session_key
    r = b.get("/api/seller/today", secure=True)
    rows = r.json().get("tasks") or []
    ok(r.status_code == 200 and {x["code"] for x in rows} == {"NLD10-9010", "NLD10-9011", "NLD10-9012"},
       "ใบของตัวเอง 3 ใบ (ไม่นับใบทดลอง/ของคนอื่น)")
    ok(all("kind" in x and "leftMin" in x for x in rows), "มีสถานะนาฬิกาโทรครบ")

    print("\n[10] แท็บ \"รถ\" — /track/api/cars บอกว่าใครเบิกรถออกไป")
    r = Client().get("/track/api/cars", HTTP_AUTHORIZATION="Bearer " + token_for(SELLER), secure=True)
    cars = {c["code"]: c for c in r.json().get("cars") or []}
    ok(r.status_code == 200 and (cars.get("CS9004") or {}).get("out", {}).get("mine") is True,
       "รถที่ฉันเบิก → out.mine")
    o5 = (cars.get("CS9005") or {}).get("out") or {}
    ok(o5.get("who") == "นวล" and o5.get("mine") is False, "รถที่คนอื่นเบิก → ชื่อเล่นคนเบิก")
    ok((cars.get("CS9001") or {}).get("out") is None, "รถที่อยู่ลาน → out = null")
    ok(not LEAK.search(r.content.decode("utf-8")), "ไม่มี LINE user id ในคำตอบ")

    print("\n[11] ป้ายแท็บ \"ห้องพัก\" — /connect/api/summary ของแอดมินมีจำนวนใบร่าง")
    r = Client().get("/connect/api/summary", HTTP_AUTHORIZATION="Bearer " + token_for(ADMIN), secure=True).json()
    ok("parked" in (r.get("counts") or {}) and "tocode" in r["counts"], "แอดมิน: counts.parked + tocode")
    r = Client().get("/connect/api/summary", HTTP_AUTHORIZATION="Bearer " + token_for(SELLER), secure=True).json()
    ok("parked" not in (r.get("counts") or {}), "เซลล์ไม่ได้ตัวเลขห้องพัก")
finally:
    _runner.teardown_databases(_old)

print("\nผ่าน %d · ไม่ผ่าน %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
