# -*- coding: utf-8 -*-
"""เทสต์หน้า /buy/ ของทีมจัดซื้อ (30 ก.ย.69)

    python scripts/test_purchase_page.py

**ปลอมที่ `fetch_open_cases` / `market_gap` (ขอบของข้อมูล = ชีต)** — ไม่ปลอม
`rank_cases`/`summary` ซึ่งเป็นตรรกะของเราเอง · บทเรียนเดิม: ปลอมฟังก์ชันของเราเอง
= ไม่ได้ทดสอบฟังก์ชันนั้นเลย (เคยทำให้บั๊กโปรไฟล์ลูกค้าหลุด 3 วัน)
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
os.environ.setdefault("DB_HOST", "")
os.environ.setdefault("DEBUG", "True")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.sessions.backends.signed_cookies import SessionStore  # noqa: E402
from django.test import Client  # noqa: E402

#  ⚠️ test client ยิงมาที่ host "testserver" ซึ่งไม่อยู่ใน ALLOWED_HOSTS ของ prod → ได้ 400 เปล่าๆ
if "testserver" not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]

from dashboard.services import purchase_followup, purchase_page, purchase_report  # noqa: E402

OK, BAD = [], []


def t(name, cond, extra=""):
    (OK if cond else BAD).append(name + (" — " + str(extra) if extra and not cond else ""))


# ── ข้อมูลจำลอง (หน้าตาเดียวกับที่ `fetch_open_cases` คืนจริง) ──────────────
def case(owner, name, car, age, talked, model_std="", phone="081", code="C-1"):
    return {"owner": owner, "name": name, "car": car, "phone": phone, "code": code,
            "age": age, "talked": talked, "model_std": model_std, "date": "", "comment": ""}


CASES = [
    case("พี่ต๊าด", "ลูกค้า A", "Toyota Altis ปี19", 2, True, "Altis"),
    case("พี่ต๊าด", "ลูกค้า B", "Honda Jazz ปี15", 15, False),
    case("พี่ต๊าด", "ลูกค้า C", "Mazda 2 ปี20", 12, True),
    case("พี่หมี", "ลูกค้า D", "Yaris Ativ ปี22", 4, True, "Yaris Ativ"),
    case("(ไม่ระบุ)", "ลูกค้า E", "MG ZS ปี21", 9, False),
]
GAP = [
    {"key": "altis", "name": "Altis", "demand": 101, "show": 0, "total": 3, "recent": 0, "score": 101.0},
    {"key": "yarisativ", "name": "Yaris Ativ", "demand": 207, "show": 3, "total": 5, "recent": 2, "score": 34.5},
]

_real_fetch, _real_gap = purchase_followup.fetch_open_cases, purchase_report.market_gap
purchase_followup.fetch_open_cases = lambda *a, **k: [dict(c) for c in CASES]
purchase_report.market_gap = lambda *a, **k: [dict(g) for g in GAP]

try:
    # ── 1. ใครเป็นทีมจัดซื้อ ────────────────────────────────────────────
    t("ตำแหน่ง 'จัดซื้อ' = ใช่", purchase_page.is_purchaser("ใครก็ได้", "จัดซื้อ"))
    t("ชื่อในตารางจับคู่ = ใช่", purchase_page.is_purchaser("ต๊าด", ""))
    t("เซลล์ = ไม่ใช่", not purchase_page.is_purchaser("โอ๊ต", "เซลล์"))
    t("ชื่อว่าง = ไม่ใช่", not purchase_page.is_purchaser("", ""))
    t("None = ไม่ใช่ (ไม่พัง)", not purchase_page.is_purchaser(None, None))

    # ★ ห้ามจับด้วย substring — ชื่อที่มีคำว่า "มิว" ปนต้องไม่ถูกนับเป็นคนเดียวกัน
    t("ไม่จับด้วย substring", not purchase_page.is_purchaser("มิวสิค", ""))

    # ── 2. ชื่อในทะเบียน → ชื่อในชีต ────────────────────────────────────
    t("ต๊าด → พี่ต๊าด", purchase_page.owner_keys("ต๊าด") == ["พี่ต๊าด"])
    t("พี่หมี → พี่หมี", purchase_page.owner_keys("พี่หมี") == ["พี่หมี"])
    t("ชื่อที่ไม่มีในตาราง = ใช้ชื่อตัวเอง", purchase_page.owner_keys("สมชาย") == ["สมชาย"])
    t("ชื่อว่าง = ไม่มีคีย์", purchase_page.owner_keys("  ") == [])

    # ── 3. เห็นเฉพาะของตัวเอง ───────────────────────────────────────────
    s = purchase_page.summary("ต๊าด")
    t("เห็นแค่เคสตัวเอง 3 เคส", s["total"] == 3, s["total"])
    t("ไม่มีเคสของคนอื่นหลุดมา",
      all(c["owner"] == "พี่ต๊าด" for c in s["cases"]),
      [c["owner"] for c in s["cases"]])

    s2 = purchase_page.summary("พี่หมี")
    t("อีกคนได้เคสของตัวเอง", s2["total"] == 1 and s2["cases"][0]["name"] == "ลูกค้า D")

    t("ชื่อที่ไม่มีเคส = ว่าง ไม่พัง", purchase_page.summary("สมชาย")["total"] == 0)
    t("ชื่อว่าง = ไม่เห็นเคสใครเลย", purchase_page.summary("")["total"] == 0)

    # ── 4. ลำดับ: ยังไม่โทรมาก่อนเสมอ ───────────────────────────────────
    t("ยังไม่ได้โทรขึ้นบนสุด", s["cases"][0]["name"] == "ลูกค้า B",
      [c["name"] for c in s["cases"]])
    t("รุ่นขาดตลาดชนะเคสที่ค้างนานกว่า",
      s["cases"][1]["name"] == "ลูกค้า A",     # Altis score 101 > ค้าง 12 วัน
      [c["name"] for c in s["cases"]])

    # ── 5. ตัวเลข KPI ───────────────────────────────────────────────────
    t("นับยังไม่ได้โทรถูก", s["notCalled"] == 1, s["notCalled"])
    t("ค้างนานใช้ครึ่งของหน้าต่าง", s["staleDays"] == max(3, s["days"] // 2))
    t("นับค้างนานถูก", s["stale"] == 2, s["stale"])   # 15 และ 12 วัน (เกิน 9)

    # ── 6. ข้อมูลรุ่นที่ขาดตลาด ─────────────────────────────────────────
    t("ส่ง gap ไปให้หน้าเว็บ", len(s["gap"]) == 2)
    t("เรียงขาดมากสุดก่อน", s["gap"][0]["key"] == "altis")
    t("บอกเกณฑ์ให้หน้าเว็บเขียนกำกับได้",
      s["topGap"] == purchase_report.TOP_GAP and s["demandMonths"] == purchase_report.DEMAND_MONTHS)
    t("เคสที่จับรุ่นได้ พ่วง gap มาด้วย", s["cases"][1].get("gap", {}).get("key") == "altis")
    t("เคสที่จับรุ่นไม่ได้ ไม่เดาให้", s["cases"][0].get("gap") is None)

    # ── 7. อ่านชีตไม่ได้ต้องไม่พังหน้าเว็บ ──────────────────────────────
    def boom(*a, **k):
        raise RuntimeError("ชีตล่ม")

    purchase_followup.fetch_open_cases = boom
    s3 = purchase_page.summary("ต๊าด")
    t("ชีตเคสล่ม = 0 เคส ไม่ throw", s3["total"] == 0)
    t("ชีตเคสล่ม แต่ยังได้รุ่นที่ขาดตลาด", len(s3["gap"]) == 2)

    purchase_followup.fetch_open_cases = lambda *a, **k: [dict(c) for c in CASES]
    purchase_report.market_gap = boom
    s4 = purchase_page.summary("ต๊าด")
    t("ตารางรุ่นล่ม = ยังได้เคสครบ", s4["total"] == 3)
    t("ตารางรุ่นล่ม = gap ว่าง ไม่ throw", s4["gap"] == [])
    purchase_report.market_gap = lambda *a, **k: [dict(g) for g in GAP]

    # ── 8. หน้าเว็บ /buy/ ───────────────────────────────────────────────
    #  ⚠️ ต้อง secure=True (โปรเจกต์บังคับ https ไม่งั้นได้ 301 เปล่าๆ)
    #  ⚠️ session เป็น signed-cookie → ต้องยัดคุกกี้เอง client.session.save() ไม่พอ
    def login(c, user):
        st = SessionStore()
        st["oxlet_user"] = user
        st.save()
        c.cookies[settings.SESSION_COOKIE_NAME] = st.session_key

    c = Client()
    r = c.get("/buy/", secure=True)
    t("ไม่ login → เด้งไปหน้า login",
      r.status_code == 302 and "/login/" in r["Location"], r.status_code)

    login(c, {"user_id": "U1", "nickname": "ต๊าด", "position": "จัดซื้อ"})
    r = c.get("/buy/", secure=True)
    body = r.content.decode("utf-8")
    t("จัดซื้อเปิดหน้าได้", r.status_code == 200, r.status_code)
    t("หน้ามีชื่อเจ้าของงาน", '"owner": "ต๊าด"' in body)
    t("หน้ามีเคสของตัวเอง", "ลูกค้า B" in body)
    t("หน้าไม่มีเคสของคนอื่น", "ลูกค้า D" not in body and "ลูกค้า E" not in body)
    t("หน้ามีตารางรุ่นที่ขาดตลาด", "รถที่ขาดตลาด" in body)

    c2 = Client()
    login(c2, {"user_id": "U2", "nickname": "โอ๊ต", "position": "เซลล์"})
    r = c2.get("/buy/", secure=True)
    t("เซลล์เปิด /buy/ → เด้งกลับ /me/",
      r.status_code == 302 and r["Location"] == "/me/", (r.status_code, r.get("Location")))

    c3 = Client()
    login(c3, {"user_id": "U3", "nickname": "แอดมิน", "position": "admin"})
    r = c3.get("/buy/?owner=พี่หมี", secure=True)
    b3 = r.content.decode("utf-8")
    t("แอดมินดูของคนอื่นได้", r.status_code == 200 and "ลูกค้า D" in b3, r.status_code)
    t("แอดมินไม่ใส่ owner = ไม่พัง", c3.get("/buy/", secure=True).status_code in (200, 404))

    # ── 9. แอดมินที่ไม่มีชื่อเล่น (break-glass) ต้องได้ "รวมทุกคน" ไม่ใช่ 404 ──
    #    เจ้าของเจอจริงบน prod 30/09: หน้าขึ้น "ยังไม่ได้ผูกชื่อเล่น" ทั้งที่มีสิทธิ์เต็ม
    c4 = Client()
    login(c4, {"user_id": "admin", "nickname": "", "position": "admin"})
    r = c4.get("/buy/", secure=True)
    b4 = r.content.decode("utf-8")
    t("แอดมินไม่มีชื่อเล่น เปิดได้ ไม่ 404", r.status_code == 200, r.status_code)
    t("เห็นเคสของทุกคน", "ลูกค้า B" in b4 and "ลูกค้า D" in b4 and "ลูกค้า E" in b4)
    t("บอกว่ากำลังดูรวมทุกคน", '"isAll": true' in b4)
    t("มีปุ่มสลับคนดู", '"people"' in b4 and "พี่ต๊าด" in b4)

    t("owners() นับเคสต่อคน",
      {o["owner"]: o["cases"] for o in purchase_page.owners()}
      == {"พี่ต๊าด": 3, "พี่หมี": 1, "(ไม่ระบุ)": 1})
    t("owners() เรียงคนที่ค้างเยอะก่อน", purchase_page.owners()[0]["owner"] == "พี่ต๊าด")

    # ── 10. API ที่การ์ดในแท็บ "จัดซื้อ" ใช้ — ต้องได้เลขชุดเดียวกับหน้า /buy/ ──
    r = c4.get("/api/purchase/work", secure=True)
    j = r.json()
    t("API แอดมิน = รวมทุกคน", j.get("ok") and j.get("isAll") and j["total"] == 5, j.get("total"))
    t("API เลขตรงกับ summary()",
      j["notCalled"] == purchase_page.summary(purchase_page.ALL)["notCalled"])
    j2 = c4.get("/api/purchase/work?owner=พี่หมี", secure=True).json()
    t("API เลือกคนได้", j2["total"] == 1 and j2["cases"][0]["name"] == "ลูกค้า D")

    r = c.get("/api/purchase/work?owner=พี่หมี", secure=True)   # c = ต๊าด (ทีมจัดซื้อ)
    j3 = r.json()
    t("ทีมจัดซื้อขอดูของคนอื่นไม่ได้ (ได้ของตัวเอง)",
      j3["total"] == 3 and all(x["owner"] == "พี่ต๊าด" for x in j3["cases"]))

    r = c2.get("/api/purchase/work", secure=True)               # c2 = เซลล์
    t("เซลล์เรียก API ไม่ได้ (403)", r.status_code == 403, r.status_code)
    t("ไม่ login เรียก API ไม่ได้ (401)",
      Client().get("/api/purchase/work", secure=True).status_code == 401)

finally:
    purchase_followup.fetch_open_cases = _real_fetch
    purchase_report.market_gap = _real_gap

out = ["ผ่าน %d ข้อ" % len(OK)]
for x in OK:
    out.append("  ok   " + x)
if BAD:
    out.append("")
    out.append("ไม่ผ่าน %d ข้อ" % len(BAD))
    for x in BAD:
        out.append("  FAIL " + x)
txt = "\n".join(out)
io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_out_purchase_page.txt"),
        "w", encoding="utf-8").write(txt + "\n")
try:
    print(txt)
except UnicodeEncodeError:
    print(txt.encode("ascii", "replace").decode())
sys.exit(1 if BAD else 0)
