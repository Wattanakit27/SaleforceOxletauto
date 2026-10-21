# -*- coding: utf-8 -*-
"""เทสต์ลา + ปฏิทินเข้างานของแอป (★ 21 ต.ค.69 · dashboard/services/leave.py · /api/m/leave · /api/m/calendar)

    python scripts/test_leave.py

ฐานข้อมูลทดสอบแยก (สร้างใหม่ทุกครั้ง) · เรียกผ่าน test client จริง (middleware Bearer ครบทั้งสาย)
· ปลอมแค่ชีต Google (ขอบระบบ)
"""
import base64
import datetime as dt
import hashlib
import io
import json
import os
import re
import sys

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

from checkout.models import CheckIn, Employee  # noqa: E402
from dashboard.models import LeaveRequest  # noqa: E402
from dashboard.services import cache_store, google_sheets  # noqa: E402
from dashboard.services import leave as LV  # noqa: E402

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


def get(tok, path, **q):
    return Client().get(path, q, HTTP_AUTHORIZATION="Bearer " + tok, secure=True)


def post(tok, body):
    return Client().post("/api/m/leave", json.dumps(body), content_type="application/json",
                         HTTP_AUTHORIZATION="Bearer " + tok, secure=True)


LINE_ID = re.compile(r"U[0-9a-f]{32}")
today = timezone.localdate()


def nxt(dow, after=None):
    """วันถัดไป (หลัง after) ที่เป็นวันในสัปดาห์ dow (0 = จันทร์)"""
    d = (after or today) + dt.timedelta(days=1)
    while d.weekday() != dow:
        d += dt.timedelta(days=1)
    return d


try:
    # มัท หยุดวันอาทิตย์ · อู๋ หยุด เสาร์ อาทิตย์ (เขียนย่อ)
    mat = Employee.objects.create(nickname="มัท", position="ทีม A", work_start="9:00", day_off="อาทิตย์",
                                  track_checkin=True)
    ou = Employee.objects.create(nickname="อู๋", position="ทีม B", work_start="8:30", day_off="เสาร์ อาทิตย์",
                                 track_checkin=True)
    SELLER = {"user_id": "U" + "a" * 32, "nickname": "มัท", "display_name": "เซลมัท",
              "position": "seller", "seller_name": "มัท"}
    OU = {"user_id": "U" + "b" * 32, "nickname": "อู๋", "display_name": "อู๋", "position": "seller", "seller_name": "อู๋"}
    NOBODY = {"user_id": "U" + "d" * 32, "nickname": "ไม่มีในทะเบียน", "display_name": "x", "position": "seller",
              "seller_name": "ไม่มีในทะเบียน"}
    ADMIN = {"user_id": "admin", "nickname": "admin", "display_name": "admin", "position": "admin"}
    tok, tok_ou, tok_no, tok_adm = token_for(SELLER), token_for(OU), token_for(NOBODY), token_for(ADMIN)

    print("\n[1] นับวันลา — ตัดวันหยุดประจำสัปดาห์ + วันหยุดบริษัท")
    mon = nxt(0)
    sun = mon + dt.timedelta(days=6)
    ok(LV.count_days(mat, mon, sun, hol=set()) == 6, "มัท จันทร์–อาทิตย์ = 6 วัน (ตัดอาทิตย์)")
    ok(LV.count_days(ou, mon, sun, hol=set()) == 5, "อู๋ (หยุด เสาร์ อาทิตย์) = 5 วัน")
    ok(LV.count_days(mat, mon, sun, hol={(mon + dt.timedelta(days=1)).isoformat()}) == 5, "วันหยุดบริษัทไม่นับ")
    ok(LV.count_days(mat, mon, mon, half="am", hol=set()) == 0.5, "ครึ่งวัน = 0.5")
    ok(LV.is_day_off("พฤหัส", nxt(3)) and LV.is_day_off("พฤหัสบดี", nxt(3)), "ช่องวันหยุดเขียนย่อ/เต็มตรงทั้งคู่")

    print("\n[2] ยื่นลา — ค่าผิดบอกเหตุผล")
    tue = mon + dt.timedelta(days=1)
    for body, why in [({"kind": "x", "start": tue.isoformat()}, "ประเภทมั่ว"),
                      ({"kind": "sick", "start": "2026-13-40"}, "วันที่มั่ว"),
                      ({"kind": "sick", "start": tue.isoformat(), "end": mon.isoformat()}, "วันสุดท้ายก่อนวันแรก"),
                      ({"kind": "sick", "start": mon.isoformat(), "end": tue.isoformat(), "half": "am"}, "ครึ่งวันหลายวัน"),
                      ({"kind": "sick", "start": (today - dt.timedelta(days=40)).isoformat()}, "ย้อนหลังเกิน 30 วัน"),
                      ({"kind": "sick", "start": (today + dt.timedelta(days=400)).isoformat()}, "ล่วงหน้าเกินกำหนด"),
                      ({"kind": "sick", "start": sun.isoformat()}, "วันหยุดทั้งหมด"),
                      ({"kind": "sick", "start": tue.isoformat(), "reason": "x" * 600}, "เหตุผลยาวเกิน")]:
        r = post(tok, dict(body, action="create"))
        ok(r.status_code == 400 and r.json().get("error"), "ปฏิเสธ%s (%s)" % (why, r.json().get("error")))
    r = post(tok_no, {"action": "create", "kind": "sick", "start": tue.isoformat()})
    ok(r.status_code == 403, "ไม่ผูกทะเบียน → 403")
    r = Client().post("/api/m/leave", "{}", content_type="application/json", secure=True)
    ok(r.status_code in (401, 403), "ไม่มี token → ปฏิเสธ")

    r = post(tok, {"action": "create", "kind": "vacation", "start": mon.isoformat(), "end": sun.isoformat(),
                   "reason": "ไปต่างจังหวัด"})
    j = r.json()
    ok(r.status_code == 200 and j["row"]["days"] == 6 and j["row"]["status"] == "pending", "ยื่นลาพักร้อน 6 วัน → รออนุมัติ")
    vac_id = j["row"]["id"]
    r = post(tok, {"action": "create", "kind": "sick", "start": tue.isoformat()})
    ok(r.status_code == 400 and "อยู่แล้ว" in r.json().get("error", ""), "ช่วงทับคำขอเดิม → ปฏิเสธ")
    r = post(tok_ou, {"action": "create", "kind": "sick", "start": tue.isoformat(), "half": "pm"})
    ok(r.status_code == 200 and r.json()["row"]["days"] == 0.5, "อู๋ลาป่วยครึ่งบ่าย 0.5 วัน (คนอื่นวันเดียวกันได้)")
    ou_id = r.json()["row"]["id"]

    print("\n[3] อนุมัติ — แอดมินเท่านั้น")
    r = post(tok, {"action": "approve", "id": vac_id})
    ok(r.status_code == 403, "เซลล์อนุมัติเองไม่ได้")
    j = get(tok_adm, "/api/m/leave").json()
    ok(j["admin"] and len(j.get("pending", [])) == 2 and not j["linked"], "แอดมินเห็นรออนุมัติ 2 รายการ (แอดมินระบบไม่ผูกทะเบียน)")
    r = post(tok_adm, {"action": "approve", "id": vac_id})
    ok(r.status_code == 200 and r.json()["row"]["status"] == "approved" and r.json()["row"]["decidedBy"], "แอดมินอนุมัติ")
    r = post(tok_adm, {"action": "approve", "id": vac_id})
    ok(r.status_code == 400, "อนุมัติซ้ำ → 400")
    r = post(tok_adm, {"action": "reject", "id": ou_id, "note": "ช่วงนั้นคนไม่พอ"})
    ok(r.status_code == 200 and r.json()["row"]["decideNote"] == "ช่วงนั้นคนไม่พอ", "ไม่อนุมัติ + หมายเหตุ")
    r = post(tok_adm, {"action": "approve", "id": 999999})
    ok(r.status_code == 404, "ไม่พบคำขอ → 404")

    print("\n[4] ยกเลิก")
    r = post(tok, {"action": "cancel", "id": vac_id})
    ok(r.status_code == 400 and "แอดมิน" in r.json().get("error", ""), "อนุมัติแล้ว คนยื่นยกเลิกเองไม่ได้")
    r = post(tok_ou, {"action": "cancel", "id": vac_id})
    ok(r.status_code == 403, "ยกเลิกคำขอของคนอื่นไม่ได้")
    nxt_mon = nxt(0, after=sun)
    r = post(tok, {"action": "create", "kind": "personal", "start": nxt_mon.isoformat()})
    pid = r.json()["row"]["id"]
    r = post(tok, {"action": "cancel", "id": pid})
    ok(r.status_code == 200 and r.json()["row"]["status"] == "cancelled", "ยกเลิกคำขอที่ยังรออนุมัติของตัวเองได้")
    r = post(tok, {"action": "create", "kind": "personal", "start": nxt_mon.isoformat()})
    ok(r.status_code == 200, "ยกเลิกแล้ว ยื่นวันเดิมใหม่ได้")

    print("\n[5] หน้า 'ลา' ของฉัน")
    j = get(tok, "/api/m/leave").json()
    ok(j["linked"] and len(j["mine"]) == 3 and not j.get("pending"), "เซลล์เห็นคำขอของตัวเอง 3 รายการ ไม่เห็นรออนุมัติของคนอื่น")
    ok(j["used"]["vacation"] == (6 if mon.year == today.year else 0), "สรุปลาพักร้อนปีนี้นับเฉพาะที่อนุมัติ")
    ok({k["key"] for k in j["kinds"]} == {"sick", "personal", "vacation", "other"}, "ส่งประเภทการลาให้แอป")

    print("\n[6] ปฏิทินเดือน")
    # เดือนที่มีวันทำงานผ่านมาแล้ว: ใช้เดือนก่อน (มีวันจบแน่นอน)
    first_prev = (today.replace(day=1) - dt.timedelta(days=1)).replace(day=1)
    Employee.objects.filter(pk=mat.pk).update(created_at=timezone.now() - dt.timedelta(days=120))
    mat.refresh_from_db()
    d_on = first_prev + dt.timedelta(days=(7 - first_prev.weekday()) % 7)   # จันทร์แรกของเดือนก่อน
    d_late = d_on + dt.timedelta(days=1)
    d_leave = d_on + dt.timedelta(days=2)
    d_abs = d_on + dt.timedelta(days=3)
    for d, hm, st in [(d_on, "8:50", "ontime"), (d_late, "9:20", "late")]:
        CheckIn.objects.create(employee=mat, user_id="app:%d" % mat.pk, display_name="มัท", date_iso=d,
                               checkin_at=timezone.now(), time_hm=hm, work_start="9:00", status=st, time_source="app",
                               raw={"out": {"hm": "18:01"}} if st == "ontime" else {})
    LeaveRequest.objects.create(employee=mat, nickname="มัท", kind="sick", start_date=d_leave, end_date=d_leave,
                                days=1, status="approved")
    r = get(tok, "/api/m/calendar", month=first_prev.strftime("%Y-%m"))
    j = r.json()
    days = {x["date"]: x for x in j["days"]}
    ok(r.status_code == 200 and len(j["days"]) >= 28, "ได้ทุกวันของเดือน")
    ok(days[d_on.isoformat()]["state"] == "ontime" and days[d_on.isoformat()]["checkin"]["out"] == "18:01",
       "วันมาตรงเวลา + เวลาออกงาน")
    ok(days[d_late.isoformat()]["state"] == "late" and days[d_late.isoformat()]["checkin"]["lateMin"] > 0, "วันมาสาย + นาทีที่สาย")
    ok(days[d_leave.isoformat()]["state"] == "leave" and days[d_leave.isoformat()]["leave"]["kindName"] == "ลาป่วย",
       "วันลา (อนุมัติแล้ว) ไม่นับขาด")
    ok(days[d_abs.isoformat()]["state"] == "absent", "วันทำงานที่ผ่านไปไม่มีเช็คชื่อ = ขาด")
    sun_prev = d_on + dt.timedelta(days=6)
    if sun_prev.month == first_prev.month:
        ok(days[sun_prev.isoformat()]["state"] == "dayoff", "วันอาทิตย์ (วันหยุดของมัท) = วันหยุด")
    ok(j["summary"]["ontime"] == 1 and j["summary"]["late"] == 1 and j["summary"]["leave"] == 1, "สรุปเดือน")
    ok("team" not in j, "เซลล์ไม่เห็นตารางลาของทั้งบริษัท")
    jn = get(tok, "/api/m/calendar", month=(today + dt.timedelta(days=40)).strftime("%Y-%m")).json()
    ok(all(x["state"] in ("future", "dayoff", "holiday", "leave", "leavePending") for x in jn["days"]), "เดือนหน้า = ยังไม่ถึง (ไม่ขึ้นขาด)")
    cache_store.set_kv("checkin_notify_config", {"holidays": [d_abs.isoformat()]})
    j2 = get(tok, "/api/m/calendar", month=first_prev.strftime("%Y-%m")).json()
    ok({x["date"]: x for x in j2["days"]}[d_abs.isoformat()]["state"] == "holiday", "วันหยุดบริษัท = ไม่ขึ้นขาด")
    ja = get(tok_adm, "/api/m/calendar", month=first_prev.strftime("%Y-%m")).json()
    ok(not ja["linked"] and ja["team"].get(d_leave.isoformat(), [{}])[0].get("nickname") == "มัท",
       "แอดมินเห็นว่าใครลาวันไหน")
    jbad = get(tok, "/api/m/calendar", month="abc").json()
    ok(jbad["month"] == today.strftime("%Y-%m"), "เดือนมั่ว → เดือนนี้")

    print("\n[7] ไม่มี LINE user id หลุดออกไป")
    blob = "".join(get(t, p).content.decode("utf-8") for t in (tok, tok_adm) for p in ("/api/m/leave", "/api/m/calendar"))
    ok(not LINE_ID.search(blob), "ทุกคำตอบไม่มี LINE user id")
finally:
    _runner.teardown_databases(_old)

print("\nผ่าน %d · ไม่ผ่าน %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
