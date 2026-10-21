# -*- coding: utf-8 -*-
"""เทสต์เช็คชื่อในแอป (★ 14 ต.ค.69 · checkout/checkin_app.py)

    python scripts/test_checkin_app.py

ฐานข้อมูลทดสอบแยก (สร้างใหม่ทุกครั้ง) · เรียกผ่าน test client จริง (middleware Bearer ครบทั้งสาย)
· ปลอมแค่ชีต Google (ขอบระบบ) · รูปเซลฟี่เขียนลงโฟลเดอร์ชั่วคราว
"""
import base64
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import time as dtime

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
TMP = tempfile.mkdtemp(prefix="ckapp-")
settings.CHECKIN_MEDIA_ROOT = TMP

from django.contrib.sessions.backends.signed_cookies import SessionStore  # noqa: E402
from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402
from django.test import Client  # noqa: E402
from django.utils import timezone  # noqa: E402

from checkout import checkin_app as CA  # noqa: E402
from checkout import checkin_report as R  # noqa: E402
from checkout.models import CheckIn, Employee  # noqa: E402
from dashboard.services import google_sheets  # noqa: E402

google_sheets.fetch_sheet = lambda *a, **k: []   # ชีตพนักงาน — ไม่ออกเน็ต

PASS = FAIL = 0


def ok(cond, label):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓", label)
    else:
        FAIL += 1
        print("  ✗", label)


JPG = b"\xff\xd8\xff\xe0" + b"0" * 2000 + b"\xff\xd9"
SHOP = (13.361000, 100.984000)           # สาขาสมมติ
NEAR = (13.361500, 100.984300)           # ~60 ม.
FAR = (13.400000, 101.000000)            # ~4.6 กม.


def pic(name="selfie.jpg", ctype="image/jpeg", data=JPG):
    return SimpleUploadedFile(name, data, content_type=ctype)


def browser(user):
    c = Client()
    st = SessionStore()
    st["oxlet_user"] = user
    st.save()
    c.cookies[settings.SESSION_COOKIE_NAME] = st.session_key
    return c


def token_for(user):
    v = base64.urlsafe_b64encode(os.urandom(40)).decode().rstrip("=")
    ch = base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).decode().rstrip("=")
    b = browser(user)
    r = b.get("/m/login", {"r": "exp://192.168.1.20:8081/--/auth", "c": ch}, secure=True)
    r2 = b.get(r["Location"], secure=True)
    code = re.search(r"code=([^&]+)", r2["Location"]).group(1)
    r3 = Client().post("/api/m/token", json.dumps({"code": code, "verifier": v}),
                       content_type="application/json", secure=True)
    return r3.json()["token"]


def app_get(tok):
    return Client().get("/api/m/checkin", HTTP_AUTHORIZATION="Bearer " + tok, secure=True)


def app_post(tok, ll, acc=15, photo=True):
    data = {"lat": str(ll[0]), "lng": str(ll[1]), "acc": str(acc)}
    if photo:
        data["photo"] = pic()
    return Client().post("/api/m/checkin", data, HTTP_AUTHORIZATION="Bearer " + tok, secure=True)


def at(hh, mm):
    """ตั้งนาฬิกาให้ check_in เห็นเป็นเวลานั้นของวันนี้ (โซนไทย)"""
    real = timezone.localtime

    def fake(value=None, *a, **k):
        if value is None:
            base = real()
            return base.replace(hour=hh, minute=mm, second=0, microsecond=0)
        return real(value, *a, **k)
    timezone.localtime = fake
    return real


try:
    mat = Employee.objects.create(nickname="มัท", position="ทีม A", work_start="9:00", track_checkin=True)
    ou = Employee.objects.create(nickname="อู๋", position="ทีม B", work_start="8:30", track_checkin=True,
                                 checkin_anywhere=True)
    boss = Employee.objects.create(nickname="บอส", position="", work_start="", track_checkin=False)
    SELLER = {"user_id": "U" + "a" * 32, "nickname": "มัท", "display_name": "เซลมัท",
              "position": "seller", "seller_name": "มัท"}
    OU = {"user_id": "U" + "b" * 32, "nickname": "อู๋", "display_name": "อู๋", "position": "seller", "seller_name": "อู๋"}
    BOSS = {"user_id": "U" + "c" * 32, "nickname": "บอส", "display_name": "บอส", "position": "seller", "seller_name": "บอส"}
    NOBODY = {"user_id": "U" + "d" * 32, "nickname": "ไม่มีในทะเบียน", "display_name": "x", "position": "seller",
              "seller_name": "ไม่มีในทะเบียน"}
    ADMIN = {"user_id": "admin", "nickname": "admin", "display_name": "admin", "position": "admin"}

    print("\n[1] พิกัดสาขา — ตรวจค่าให้ครบ ผิดบอกช่อง")
    ok(CA.clean_sites([{"name": "ชลบุรี", "lat": SHOP[0], "lng": SHOP[1], "radius": 300}])[0], "ค่าถูก → ผ่าน")
    for bad, why in [([{"name": "", "lat": 1, "lng": 1}], "ไม่มีชื่อ"),
                     ([{"name": "a", "lat": 99, "lng": 1}], "lat เกิน 90"),
                     ([{"name": "a", "lat": 0, "lng": 0}], "พิกัด 0,0"),
                     ([{"name": "a", "lat": "x", "lng": 1}], "พิกัดไม่ใช่ตัวเลข"),
                     ([{"name": "a", "lat": 1, "lng": 1, "radius": 10}], "รัศมีน้อยกว่า 50"),
                     ([{"name": "a", "lat": 1, "lng": 1}, {"name": "a", "lat": 2, "lng": 2}], "ชื่อซ้ำ"),
                     ("x", "ไม่ใช่ลิสต์")]:
        good, err, _ = CA.clean_sites(bad)
        ok(not good and err, "ปฏิเสธ%s (%s)" % (why, err))
    d = CA.distance_m(SHOP[0], SHOP[1], NEAR[0], NEAR[1])
    ok(40 < d < 80, "ระยะทาง haversine ~60 ม. (ได้ %.0f)" % d)

    print("\n[2] ยังไม่ได้ตั้งสาขา = กดได้ (จดว่าไม่ได้ตรวจ)")
    tok = token_for(SELLER)
    r = app_get(tok)
    j = r.json()
    ok(r.status_code == 200 and j.get("linked") and not j.get("done"), "GET สถานะ: ผูกทะเบียนแล้ว ยังไม่เช็คชื่อ")
    real = at(8, 52)
    try:
        r = app_post(tok, FAR)
    finally:
        timezone.localtime = real
    j = r.json()
    ok(r.status_code == 200 and j.get("ok") and not j.get("already"), "เช็คชื่อได้ (ยังไม่มีสาขาให้เทียบ)")
    c = CheckIn.objects.get(employee=mat)
    ok(c.time_source == "app" and c.user_id == "app:%d" % mat.pk, "แถวจากแอป: time_source=app · user_id=app:<id>")
    ok(c.status == "ontime" and c.time_hm == "8:52", "8:52 กับเวลาเข้างาน 9:00 = ตรงเวลา")
    ok("ยังไม่ได้ตั้งพิกัดสาขา" in (c.raw or {}).get("place", ""), "จดไว้ว่าไม่ได้ตรวจตำแหน่ง")
    p = CA.photo_file(c)
    ok(p and str(p).startswith(TMP) and p.read_bytes() == JPG, "เซลฟี่อยู่ในโฟลเดอร์ส่วนตัว (ไม่ใช่ /media/)")
    ok(not str(p).startswith(str(settings.MEDIA_ROOT)), "  …ไม่ได้อยู่ใต้ MEDIA_ROOT ที่เสิร์ฟสาธารณะ")

    print("\n[3] กดซ้ำวันเดียวกัน = ไม่สร้างแถวใหม่ (กันกดใหม่เพื่อแก้เวลาสาย)")
    real = at(10, 30)
    try:
        r = app_post(tok, FAR)
    finally:
        timezone.localtime = real
    j = r.json()
    ok(r.status_code == 200 and j.get("already") and CheckIn.objects.filter(employee=mat).count() == 1,
       "ตอบว่าเช็คชื่อแล้ว · ยังมีแถวเดียว · เวลาเดิม 8:52")
    ok(len(list(os.scandir(os.path.join(TMP, timezone.localdate().strftime("%Y-%m"))))) == 1,
       "ไม่เก็บรูปของครั้งที่สอง")

    print("\n[4] ตั้งสาขาแล้ว — คนที่ไม่ได้ติ๊กนอกสถานที่ต้องอยู่ในรัศมี")
    CA.save_sites([{"name": "ชลบุรี", "lat": SHOP[0], "lng": SHOP[1], "radius": 300}])
    CheckIn.objects.all().delete()
    r = app_post(tok, FAR)
    j = r.json()
    ok(r.status_code == 403 and "ห่างสาขาชลบุรี" in j.get("error", "") and not CheckIn.objects.exists(),
       "อยู่ห่าง 4.6 กม. → ปฏิเสธพร้อมบอกระยะ · ไม่มีแถว")
    real = at(9, 20)
    try:
        r = app_post(tok, NEAR, acc=20)
    finally:
        timezone.localtime = real
    j = r.json()
    c = CheckIn.objects.get(employee=mat)
    ok(r.status_code == 200 and c.status == "late" and "สาย 20 นาที" in j.get("message", ""),
       "อยู่ในรัศมี · 9:20 กับเวลาเข้างาน 9:00 = สาย 20 นาที")
    ok(c.full_address.startswith("สาขาชลบุรี") and (c.raw or {}).get("site") == "ชลบุรี", "จดว่าเช็คชื่อที่สาขาไหน")
    CheckIn.objects.all().delete()
    real = at(9, 4)
    try:
        r = app_post(tok, NEAR)
    finally:
        timezone.localtime = real
    ok(CheckIn.objects.get(employee=mat).status == "ontime", "9:04 = ยังไม่เกินเผื่อสาย 5 นาที → ตรงเวลา")
    edge = (SHOP[0] + 0.0030, SHOP[1])   # ~333 ม. — เกินรัศมีนิดเดียว แต่ GPS คลาด 60 ม.
    ok(CA.place_check(mat, edge[0], edge[1], 60)["ok"], "เกินรัศมีไม่ถึงค่าคลาดเคลื่อน GPS → ยังนับว่าอยู่สาขา")
    far2 = (SHOP[0] + 0.0045, SHOP[1])   # ~500 ม.
    ok(not CA.place_check(mat, far2[0], far2[1], 1000)["ok"],
       "ห่าง 500 ม. แม้ GPS บอกคลาด 1 กม. ก็ไม่ผ่าน (หักได้ไม่เกิน %d ม.)" % CA.ACC_CAP)
    ok(not CA.place_check(mat, edge[0] + 0.01, edge[1], 1000)["ok"], "  …ห่าง 1.4 กม. + GPS คลาด 1 กม. → ยังไม่ผ่าน")

    print("\n[5] ติ๊กนอกสถานที่ได้ = กดได้ทุกที่")
    tok_ou = token_for(OU)
    r = app_post(tok_ou, FAR)
    ok(r.status_code == 200 and r.json().get("ok") and CheckIn.objects.filter(employee=ou).exists(),
       "อู๋ (ติ๊กนอกสถานที่) อยู่ห่าง 4.6 กม. ก็เช็คชื่อได้")

    print("\n[6] เคสที่ต้องปฏิเสธ")
    tok_boss = token_for(BOSS)
    r = app_post(tok_boss, NEAR)
    ok(r.status_code == 400 and "ไม่ต้องเช็คชื่อ" in r.json().get("error", ""), "ติ๊กไม่ต้องเช็คชื่อ (ผู้บริหาร) → 400")
    tok_no = token_for(NOBODY)
    r = app_post(tok_no, NEAR)
    ok(r.status_code == 403 and "ทะเบียนพนักงาน" in r.json().get("error", ""), "ไม่มีในทะเบียน → 403 บอกเหตุผล")
    ok(app_get(tok_no).json().get("linked") is False, "  GET บอกว่ายังไม่ผูกทะเบียน")
    CheckIn.objects.filter(employee=mat).delete()
    r = app_post(tok, NEAR, photo=False)
    ok(r.status_code == 400 and "เซลฟี่" in r.json().get("error", ""), "ไม่มีรูป → 400")
    r = Client().post("/api/m/checkin", {"lat": "abc", "lng": "1", "photo": pic()},
                      HTTP_AUTHORIZATION="Bearer " + tok, secure=True)
    ok(r.status_code == 400, "ตำแหน่งอ่านไม่ได้ → 400")
    r = Client().post("/api/m/checkin", {"lat": str(NEAR[0]), "lng": str(NEAR[1]),
                                         "photo": pic("x.html", "text/html", b"<script>")},
                      HTTP_AUTHORIZATION="Bearer " + tok, secure=True)
    ok(r.status_code == 400 and "รูป" in r.json().get("error", ""), "ไฟล์ไม่ใช่รูป → 400")
    r = Client().post("/api/m/checkin", {"lat": "1", "lng": "1"}, secure=True)
    ok(r.status_code == 401, "ไม่มี token → 401")

    print("\n[7] 2 ทาง (แอป + กลุ่ม LINE) = นับอันที่มาก่อน")
    CheckIn.objects.all().delete()
    day = timezone.localdate()
    CheckIn.objects.create(employee=mat, user_id="U" + "e" * 32, display_name="มัท", date_iso=day,
                           time_hm="8:40", work_start="9:00", status="ontime", time_source="image")
    r = app_post(tok, NEAR)
    ok(r.json().get("already") and CheckIn.objects.filter(employee=mat).count() == 1,
       "ส่งรูปในกลุ่มไปแล้ว 8:40 → กดในแอปทีหลัง = ไม่สร้างแถวใหม่ บอกว่าเช็คชื่อทางรูปในกลุ่มแล้ว")
    ok("รูปในกลุ่ม LINE" in r.json().get("message", ""), "  ข้อความบอกว่าเช็คชื่อทางไหน")
    # n8n ไม่รู้ว่ามีแถวจากแอป → เขียนแถวที่ 2 ได้ · ตัวอ่านต้องเอาแถวที่มาก่อน
    CheckIn.objects.create(employee=mat, user_id="app:%d" % mat.pk, display_name="มัท", date_iso=day,
                           time_hm="9:30", work_start="9:00", status="late", time_source="app")
    rows = CA.first_per_employee(CheckIn.objects.filter(employee=mat, date_iso=day))
    ok(len(rows) == 1 and rows[0].time_hm == "8:40", "first_per_employee เก็บแถว 8:40")
    real = at(8, 20)
    try:
        app_post(tok_ou, FAR)                     # อู๋เช็คชื่อในแอป 8:20 (ล้างตารางไปตอนต้นข้อนี้)
    finally:
        timezone.localtime = real
    CheckIn.objects.create(employee=ou, user_id="U" + "f" * 32, display_name="อู๋", date_iso=day,
                           time_hm="", status="abnormal", time_source="image")
    ou_rows = CA.first_per_employee(CheckIn.objects.filter(employee=ou, date_iso=day))
    ok(len(ou_rows) == 1 and ou_rows[0].time_source == "app",
       "แถวอ่านเวลาไม่ออกไม่ชนะแถวที่มีเวลา (อู๋เช็คในแอปแล้ว)")
    data = R.collect(day)
    flat = [r for _, rs in data["groups"] for r in rs]
    mats = [r for r in flat if r["name"] == "มัท"]
    ok(len(mats) == 1 and mats[0]["timeHm"] == "8:40" and not mats[0]["late"],
       "ตาราง 9:30 (checkin_report.collect): มัทแถวเดียว เวลา 8:40 ตรงเวลา")

    print("\n[8] พาเนลเช็คชื่อบนเว็บ (แอดมิน)")
    adm = browser(ADMIN)
    r = adm.get("/checkout/api/checkins", secure=True)
    j = r.json()
    names = [x["name"] for x in j.get("rows", [])]
    ok(r.status_code == 200 and names.count("มัท") == 1 and names.count("อู๋") == 1, "รายวัน: คนละแถวเดียว")
    ou_row = [x for x in j["rows"] if x["name"] == "อู๋"][0]
    ok(ou_row["app"] and ou_row["mapUrl"].startswith("https://www.google.com/maps?q=") and ou_row["photoUrl"],
       "แถวจากแอปมีป้าย + ลิงก์แผนที่ + ลิงก์รูป")
    r = adm.get("/checkout/api/checkins", {"from": day.isoformat(), "to": day.isoformat()}, secure=True)
    rr = [x for x in r.json().get("rows", []) if x["name"] == "มัท"]
    ok(rr and rr[0]["days"] == 1, "สรุปช่วง: มัทมา 1 วัน (ไม่นับ 2 แถวเป็น 2 วัน)")
    cid = int(ou_row["photoUrl"].split("id=")[1])
    r = adm.get("/checkout/api/checkin_photo", {"id": cid}, secure=True)
    ok(r.status_code == 200 and b"".join(r.streaming_content) == JPG, "แอดมินเปิดเซลฟี่ได้")
    r = browser(SELLER).get("/checkout/api/checkin_photo", {"id": cid}, secure=True)
    ok(r.status_code == 401, "เซลล์เปิดเซลฟี่คนอื่นไม่ได้ → 401")
    c_line = CheckIn.objects.filter(time_source="image").first()
    r = adm.get("/checkout/api/checkin_photo", {"id": c_line.pk}, secure=True)
    ok(r.status_code == 404, "แถวจากกลุ่ม LINE ไม่มีเซลฟี่ → 404")
    c_app = CheckIn.objects.get(pk=cid)
    c_app.raw = dict(c_app.raw, photo="../../../manage.py")
    c_app.save()
    ok(CA.photo_file(c_app) is None, "path หลุดนอกโฟลเดอร์ (../) → ไม่เปิด")

    print("\n[9] ตั้งค่าพิกัดสาขาผ่านหน้าเว็บ")
    r = adm.post("/checkout/api/checkin_config", json.dumps({"action": "sites", "sites": [
        {"name": "ชลบุรี", "lat": 13.36, "lng": 100.98, "radius": 400},
        {"name": "เทพารักษ์", "lat": 13.62, "lng": 100.64, "radius": 300}]}),
        content_type="application/json", secure=True)
    ok(r.status_code == 200 and len(r.json().get("sites", [])) == 2, "บันทึก 2 สาขา")
    r = adm.post("/checkout/api/checkin_config", json.dumps({"action": "sites", "sites": [
        {"name": "x", "lat": 200, "lng": 1}]}), content_type="application/json", secure=True)
    ok(r.status_code == 400 and len(CA.sites()) == 2, "ค่าผิด → 400 และของเดิมไม่ถูกทับ")
    r = adm.get("/checkout/api/checkin_config", secure=True)
    j = r.json()
    ok([s["name"] for s in j.get("sites", [])] == ["ชลบุรี", "เทพารักษ์"] and j.get("anywhere") == ["อู๋"],
       "GET: รายชื่อสาขา + คนที่เช็คชื่อนอกสถานที่ได้")
    r = browser(SELLER).post("/checkout/api/checkin_config", json.dumps({"action": "sites", "sites": []}),
                             content_type="application/json", secure=True)
    ok(r.status_code == 401 and len(CA.sites()) == 2, "เซลล์ตั้งสาขาไม่ได้")

    print("\n[10] หน้าพนักงาน: ติ๊ก/ไม่ติ๊ก นอกสถานที่")
    r = adm.get("/checkout/api/employees", secure=True)
    emp = {e["nickname"]: e for e in r.json().get("employees", [])}
    ok(emp["อู๋"]["checkinAnywhere"] is True and emp["มัท"]["checkinAnywhere"] is False, "GET ส่งค่าช่องนี้")
    body = {"action": "save", "id": mat.pk, "nickname": "มัท", "position": "ทีม A", "workStart": "9:00",
            "active": True, "trackCheckin": True, "checkinAnywhere": True}
    r = adm.post("/checkout/api/employees", json.dumps(body), content_type="application/json", secure=True)
    mat.refresh_from_db()
    ok(r.status_code == 200 and mat.checkin_anywhere, "POST ติ๊ก → บันทึก")

    print("\n[11] หน้า 'วันนี้' ของแอป")
    from dashboard.services import mobile_home
    info = mobile_home.my_checkin(mat, day)
    ok(info["status"] == "ontime" and info["time"] == "8:40" and info["source"] == "line" and info["anywhere"],
       "my_checkin: เวลาแรก 8:40 · ทางกลุ่ม LINE · บอกว่าเช็คนอกสถานที่ได้")
    summ = mobile_home.checkin_summary(day)
    ok(summ["late"] == 0, "สรุปทั้งบริษัทไม่นับแถวที่ 2 (สาย 9:30) ของมัท")

    print("\n[12] ออกงานในแอป (★ 21 ต.ค.69) — เก็บใน raw['out'] ของแถวแรกของวัน")

    def app_out(tk, ll, acc=15, as_json=False):
        data = {"lat": str(ll[0]), "lng": str(ll[1]), "acc": str(acc)}
        if as_json:
            return Client().post("/api/m/checkout", json.dumps(data), content_type="application/json",
                                 HTTP_AUTHORIZATION="Bearer " + tk, secure=True)
        return Client().post("/api/m/checkout", data, HTTP_AUTHORIZATION="Bearer " + tk, secure=True)

    j = app_get(tok).json()
    ok(isinstance(j.get("siteList"), list) and len(j["siteList"]) == 2
       and {"name", "lat", "lng", "radius"} <= set(j["siteList"][0]), "GET ส่งพิกัดสาขา (siteList) ให้แผนที่")
    ok("outTime" not in j, "ยังไม่ออกงาน = ไม่มี outTime")
    first_pk = CA.first_per_employee(CheckIn.objects.filter(employee=mat, date_iso=day))[0].pk
    n_rows = CheckIn.objects.filter(employee=mat, date_iso=day).count()
    real = at(17, 31)
    try:
        r = app_out(tok, NEAR)
    finally:
        timezone.localtime = real
    j = r.json()
    ok(r.status_code == 200 and j.get("updated") is False and "17:31" in j.get("message", ""), "ออกงาน 17:31")
    ok(j.get("info", {}).get("outTime") == "17:31", "info ส่ง outTime กลับมา")
    c = CheckIn.objects.get(pk=first_pk)
    ok((c.raw or {}).get("out", {}).get("hm") == "17:31", "เก็บใน raw['out'] ของแถวแรกของวัน")
    ok(CheckIn.objects.filter(employee=mat, date_iso=day).count() == n_rows, "ไม่สร้างแถวเช็คชื่อใหม่")
    ok(c.time_hm == "8:40", "เวลาเข้างานเดิมไม่ถูกแตะ")
    real = at(18, 5)
    try:
        r = app_out(tok, NEAR, as_json=True)
    finally:
        timezone.localtime = real
    j = r.json()
    ok(r.status_code == 200 and j.get("updated") is True and "18:05" in j["message"] and "17:31" in j["message"],
       "กดซ้ำ (ส่ง JSON) = บันทึกเวลาใหม่ + บอกเวลาเดิม")
    ok(app_get(tok).json().get("outTime") == "18:05", "GET เห็นเวลาออกล่าสุด")
    r = app_out(tok_boss, NEAR)
    ok(r.status_code == 400, "คนที่ไม่ต้องเช็คชื่อ → 400")
    r = app_out(tok_no, NEAR)
    ok(r.status_code == 403, "ไม่ผูกทะเบียน → 403")
    r = Client().post("/api/m/checkout", {"lat": "x", "lng": "1"}, HTTP_AUTHORIZATION="Bearer " + tok, secure=True)
    ok(r.status_code == 400, "พิกัดอ่านไม่ได้ → 400")
    r = Client().post("/api/m/checkout", {"lat": "13.4", "lng": "101"}, secure=True)
    ok(r.status_code in (401, 403), "ไม่มี token → ปฏิเสธ")
    nobody_today = Employee.objects.create(nickname="ใหม่", position="ทีม A", work_start="9:00", track_checkin=True)
    ok(CA.check_out(nobody_today, {}, NEAR[0], NEAR[1], 10)[0] == 400, "ยังไม่ได้เข้างานวันนี้ → 400")
    far_emp = Employee.objects.create(nickname="ไกล", position="ทีม A", work_start="9:00", track_checkin=True)
    CheckIn.objects.create(employee=far_emp, user_id="app:%d" % far_emp.pk, display_name="ไกล", date_iso=day,
                           checkin_at=timezone.now(), time_hm="9:00", time_source="app", raw={})
    st_code, pl = CA.check_out(far_emp, {}, FAR[0] + 0.5, FAR[1] + 0.5, 10)
    ok(st_code == 403 and "ออกงาน" in pl.get("error", ""), "อยู่นอกรัศมีสาขา (ไม่ได้ติ๊กนอกสถานที่) → 403 บอกเหตุผล")
finally:
    shutil.rmtree(TMP, ignore_errors=True)
    _runner.teardown_databases(_old)

print("\nผ่าน %d · ไม่ผ่าน %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
