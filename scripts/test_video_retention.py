# -*- coding: utf-8 -*-
"""เทสต์กราฟ "คนดูหลุดตรงไหน" ของวิดีโอ Facebook (15 ต.ค.69)

    python scripts/test_video_retention.py

ฐานข้อมูลทดสอบแยก · ปลอมที่ `requests.get` (= Graph API ของ Facebook) · ไม่ปลอมตรรกะของเราเอง
(`sync_retention` · `_kpi` · `retention` · `video_detail` ได้รันของจริง) · การตัดภาพปลอมแค่ขั้นโหลดคลิป+ffmpeg
"""
import io
import os
import sys
import tempfile
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
os.environ["DB_HOST"] = ""
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

from unittest import mock  # noqa: E402

import requests  # noqa: E402
from django.contrib.sessions.backends.signed_cookies import SessionStore  # noqa: E402
from django.test import Client  # noqa: E402
from django.utils import timezone  # noqa: E402

from dashboard.models import MetaPostSnapshot, MetaVideoRetention  # noqa: E402
from dashboard.services import meta, meta_sync, social_stats, video_frames  # noqa: E402

FAILS = []


def ok(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else " — " + str(extra)))
    if not cond:
        FAILS.append(name)


PID = "111222333"
settings.META_ACCESS_TOKEN = "USER_TOKEN"
settings.META_PAGE_IDS = [PID]
settings.META_AD_ACCOUNTS = []
MEDIA = tempfile.mkdtemp(prefix="vr_media_")
settings.MEDIA_ROOT = MEDIA

LIN = {str(i): round(1 - 0.8 * i / 40, 4) for i in range(41)}           # ลดลงเป็นเส้นตรง 100% → 20%
STEP = {str(i): (1.0 if i < 5 else (0.5 if i < 40 else 0.4)) for i in range(41)}   # หลุดครึ่งที่วิ 5
NOW = timezone.now()
ISO = NOW.strftime("%Y-%m-%dT%H:%M:%S+0000")


def ins(curve):
    return {"data": [{"name": "post_video_retention_graph", "period": "lifetime", "values": [{"value": curve}]},
                     {"name": "post_video_retention_graph_autoplayed", "period": "lifetime", "values": [{"value": curve}]},
                     {"name": "post_video_retention_graph_clicked_to_play", "period": "lifetime", "values": [{"value": {}}]}]}


POSTS = [
    {"id": PID + "_1", "created_time": ISO, "insights": ins(LIN),
     "attachments": {"data": [{"media_type": "video", "target": {"id": "V1"}}]}},
    {"id": PID + "_2", "created_time": ISO, "insights": ins({}),
     "attachments": {"data": [{"media_type": "photo", "target": {"id": "X2"}}]}},
    {"id": PID + "_3", "created_time": ISO, "insights": ins(STEP),
     "attachments": {"data": [{"media_type": "video", "target": {"id": "V3"}}]}},
    {"id": PID + "_4", "created_time": ISO, "insights": ins({}),          # วิดีโอที่ยังไม่มีคนดู = ไม่มีกราฟ
     "attachments": {"data": [{"media_type": "video", "target": {"id": "V4"}}]}},
]
VIDEOS = [{"id": "V1", "length": 40.0, "created_time": ISO}, {"id": "V3", "length": 10.0, "created_time": ISO}]
CALLS = []
SOURCE = {"url": "https://video.xx.fbcdn.net/v/t42/clip.mp4?oh=1"}


class R:
    def __init__(self, js, code=200, body=b"", ctype=""):
        self._js, self.status_code, self.text = js, code, str(js)
        self.headers = {"content-type": ctype} if ctype else {}
        self._body = body

    def json(self):
        return self._js

    def iter_content(self, n=65536):
        yield self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


PIC = "https://scontent.xx.fbcdn.net/v/pic_%s.jpg?oh=1"
OLD = []                                           # โพสต์เก่ากว่าหน้าต่างดึงปกติ (ไม่อยู่ใน /posts)


def fake_get(url, params=None, timeout=None, **kw):
    if "/pic_" in url:                             # โหลดรูปหน้าปก (covers.save)
        CALLS.append("PIC")
        return R({}, body=b"\xff\xd8" + b"x" * 2000, ctype="image/jpeg")
    path = url.split("graph.facebook.com/", 1)[-1].split("/", 1)[-1]   # ตัดเวอร์ชัน
    CALLS.append(path)
    fields = (params or {}).get("fields", "")
    if path == PID and "access_token" in fields:
        return R({"id": PID, "access_token": "PAGE_TOKEN"})
    if path == PID + "/videos":
        return R({"data": VIDEOS})
    if path == PID + "/posts":
        return R({"data": POSTS})
    if path.startswith(PID + "_"):
        p = next((x for x in POSTS + OLD if x["id"] == path), None)
        if not p:
            return R({"error": {"message": "no", "code": 100}})
        if "insights" in fields:                   # ดึงคลิปเดียว (fetch_retention_one)
            return R(dict(p, full_picture=PIC % path))
        return R({"id": path, "attachments": p["attachments"]})
    if path == "V9":
        return R({"id": "V9", "length": 30.0, "created_time": ISO})
    if path in ("V1", "V3", "V5"):
        return R({"id": path, "source": SOURCE["url"], "length": 40.0})
    return R({"error": {"message": "unknown path " + path, "code": 100}})


P = [mock.patch("requests.get", fake_get)]
video_frames.ENABLED = True        # ข้อ [3]–[7] ทดสอบกลไกตัดภาพ (ของจริงปิดอยู่ — ข้อ [8])
for p in P:
    p.start()

try:
    # ── 1) แปลงกราฟ + ประมาณค่าระหว่างจุด ──────────────────────────────
    print("\n[1] คำนวณ")
    ok("แปลง 41 จุดตามลำดับเลข ไม่ใช่ลำดับตัวอักษร", meta_sync._curve({"10": .5, "2": .9, "0": 1}) == [1.0, .9, .5])
    ok("ไม่มีข้อมูล = []", meta_sync._curve({}) == [] and meta_sync._curve(None) == [])
    lin = meta_sync._curve(LIN)
    ok("วินาที = จุดพอดี (คลิป 40 วิ · วิที่ 10 = จุดที่ 10)", abs(social_stats._ret_at(lin, 40, 10) - lin[10]) < 1e-9)
    ok("ประมาณค่าระหว่างจุด (คลิป 80 วิ · วิที่ 5 = กึ่งกลางจุด 2–3)",
       abs(social_stats._ret_at(lin, 80, 5) - (lin[2] + lin[3]) / 2) < 1e-9)
    ok("เกินความยาวคลิป = None", social_stats._ret_at(lin, 40, 41) is None)
    ok("ไม่รู้ความยาว = None", social_stats._ret_at(lin, None, 3) is None)
    k = social_stats._kpi(lin, 40)
    ok("Hook = วิที่ 3", k["hook"] == 94.0, k)
    ok("Hold 3→15 = ret(15)/ret(3)", k["hold"] == round(0.7 / 0.94 * 100, 1) and k["holdTo"] == 15, k)
    ok("หายครึ่ง = วินาทีแรกที่เหลือไม่ถึงครึ่งของคนที่ดูถึง 3 วิ", k["halfSec"] == 27, k)
    ok("ดูจบ = จุดสุดท้าย", k["end"] == 20.0, k)
    k2 = social_stats._kpi(meta_sync._curve(STEP), 40)
    ok("หลุดหนักสุด = วิที่ 5 · หาย 50%", (k2["dropSec"], k2["dropPct"]) == (5, 50.0), k2)
    ok("หลุดฮวบครึ่ง = หายครึ่งที่วิ 5", k2["halfSec"] == 5, k2)
    k3 = social_stats._kpi(lin, 10)
    ok("คลิปสั้นกว่า 15 วิ = Hold ถึงจบคลิป", k3["holdTo"] == "end", k3)
    k4 = social_stats._kpi(lin, None)
    ok("ไม่รู้ความยาว = ไม่เดา Hook · ดูจบยังได้", k4["hook"] is None and k4["end"] == 20.0, k4)

    # ── 2) ดึงจาก Facebook ลงตาราง ─────────────────────────────────────
    print("\n[2] ดึงกราฟ (sync_retention)")
    r = meta_sync.sync_retention(timezone.now())
    ok("เก็บเฉพาะวิดีโอที่มีกราฟ (ข้ามรูป + วิดีโอที่ยังไม่มีคนดู)", r["videos"] == 2 and not r["errors"], r)
    v1 = MetaVideoRetention.objects.get(post_id=PID + "_1")
    ok("ความยาวคลิปจาก /videos ผูกด้วย video id", v1.length_sec == 40.0 and v1.video_id == "V1", v1.length_sec)
    ok("เก็บ 41 จุด 3 เส้น (เส้นที่ว่าง = [])", len(v1.curve) == 41 and len(v1.curve_auto) == 41 and v1.curve_click == [])
    ok("ใช้ page token ไม่ใช่ /me", not any(c.startswith("me") for c in CALLS), CALLS)
    r = meta_sync.sync_retention(timezone.now())
    ok("รันซ้ำ = อัปเดตแถวเดิม ไม่เพิ่ม", MetaVideoRetention.objects.count() == 2)

    # ── 3) ตัวเลขที่ส่งให้หน้าเว็บ ────────────────────────────────────
    print("\n[3] ข้อมูลหน้าเว็บ")
    m = social_stats.retention_map([PID + "_1", PID + "_2", PID + "_3"])
    ok("ดูถึง 3 วิ ในตาราง (วิดีโอที่มีกราฟเท่านั้น)", m.get(PID + "_1", {}).get("ret3") == 94.0 and PID + "_2" not in m, m)
    d = social_stats.retention(PID + "_1")
    ok("กราฟรายวินาที 0..40 (41 ค่า) = ตรงกับภาพทีละวินาที", len(d["persec"]) == 41 and d["persec"][0] == 100.0, d["persec"][:3])
    ok("หน่วยเป็นวินาทีเมื่อรู้ความยาว", d["unit"] == "sec" and d["x"][-1] == 40.0)
    ok("ไม่มีกราฟ = has False", social_stats.retention(PID + "_2") == {"has": False})

    MetaPostSnapshot.objects.create(taken_at=timezone.now(), snap_date=timezone.localdate(), trigger="cron",
                                    page_id=PID, post_id=PID + "_1", post_type="video", created_time=NOW,
                                    message="ทดสอบคลิป", video_views=1000, reactions=40, comments=5, shares=5,
                                    video_avg_watch_ms=8500, video_views_paid=300, video_views_organic=700)

    def fake_extract(post_id, d):
        os.makedirs(d, exist_ok=True)
        for i in range(3):
            open(os.path.join(d, "%03d.jpg" % (i + 1)), "wb").write(b"\xff\xd8jpg")
        return 3, 40.0

    with mock.patch.object(video_frames, "_extract", fake_extract):
        det = social_stats.video_detail(PID + "_1")
        ok("รายละเอียดคลิป: ตัวเลขโพสต์", det["stats"]["views"] == 1000 and det["stats"]["avgSec"] == 8.5
           and det["stats"]["engPct"] == 5.0, det.get("stats"))
        ok("ค่าเฉลี่ยของเพจ (Hook ของ 2 คลิป)", det["pageAvg"]["hook"] == round((94.0 + social_stats._kpi(meta_sync._curve(STEP), 10.0)["hook"]) / 2, 1)
           and det["pageAvg"]["n"] == 2, det["pageAvg"])
        ok("ไม่เล่น/ไม่โหลดวิดีโอในหน้า (ไม่มีลิงก์ไฟล์วิดีโอ) · มีรูปหน้าปกจาก Facebook",
           "source" not in det and "/media/covers/meta/" + PID + "_1.jpg" in det.get("cover", ""), det.get("cover"))
        ok("เริ่มตัดภาพในเบื้องหลัง", det["frames"]["state"] in ("running", "ready"), det["frames"])
        for _ in range(50):
            if video_frames.status(PID + "_1")["state"] == "ready":
                break
            time.sleep(0.05)
        st = video_frames.status(PID + "_1")
        ok("ตัดเสร็จ = ภาพทีละวินาที (ไฟล์ 001 = วินาทีที่ 0)", st["state"] == "ready" and len(st["urls"]) == 3
           and "/media/frames/meta/" + PID + "_1/001.jpg" in st["urls"][0], st)
        ok("เปิดอีกครั้ง = ไม่ตัดซ้ำ", video_frames.ensure(PID + "_1")["state"] == "ready")
    ok("โพสต์ของเพจอื่น = ปฏิเสธ", social_stats.video_detail("999_1").get("has") is False
       and "ไม่ได้อยู่ใต้เพจ" in social_stats.video_detail("999_1").get("error", ""))
    ok("id แปลก (../) ถูกล้าง ไม่หลุดออกนอกโฟลเดอร์", video_frames._dir("../../etc/passwd").startswith(
        os.path.join(MEDIA, "frames")) and ".." not in video_frames._dir("../../etc/passwd"))

    # ── 4) ด่านไฟล์วิดีโอ ──────────────────────────────────────────────
    print("\n[4] ตัดภาพ")
    SOURCE["url"] = "https://evil.example.com/clip.mp4"
    try:
        video_frames._extract(PID + "_3", os.path.join(MEDIA, "x"))
        ok("ลิงก์คลิปที่ไม่ใช่ของ Facebook = ไม่โหลด", False)
    except RuntimeError as e:
        ok("ลิงก์คลิปที่ไม่ใช่ของ Facebook = ไม่โหลด", "Facebook ไม่ให้ไฟล์" in str(e) or "ffmpeg" in str(e), e)
    try:
        video_frames._extract(PID + "_2", os.path.join(MEDIA, "y"))
        ok("โพสต์ที่ไม่ใช่วิดีโอ = บอกเหตุผล", False)
    except RuntimeError as e:
        ok("โพสต์ที่ไม่ใช่วิดีโอ = บอกเหตุผล", "ไม่ใช่วิดีโอ" in str(e) or "ffmpeg" in str(e), e)
    SOURCE["url"] = "https://video.xx.fbcdn.net/v/t42/clip.mp4?oh=1"

    # ── 5) API ผ่าน test client (สิทธิ์จริง) ───────────────────────────
    print("\n[5] API")

    def client(user):
        c = Client()
        if user:
            s = SessionStore()
            s["oxlet_user"] = user
            s.save()
            c.cookies[settings.SESSION_COOKIE_NAME] = s.session_key
        return c

    adm = client({"user_id": "admin", "position": "admin", "nickname": "admin"})
    r = adm.get("/api/admin/social?frames=" + PID + "_1", secure=True)
    ok("?frames= (แอดมิน) ได้สถานะ", r.status_code == 200 and r.json()["state"] == "ready", r.content[:200])
    with mock.patch.object(video_frames, "_extract", fake_extract):
        r = adm.get("/api/admin/social?video=" + PID + "_1", secure=True)
    j = r.json()
    ok("?video= (แอดมิน) ได้กราฟ + KPI + ภาพ", r.status_code == 200 and j["kpi"]["hook"] == 94.0
       and j["frames"]["state"] == "ready", str(j)[:300])
    ok("ไม่มี token หลุดในคำตอบ", b"PAGE_TOKEN" not in r.content and b"USER_TOKEN" not in r.content)
    sale = client({"user_id": "Uxx", "position": "seller", "nickname": "มัท"})
    ok("เซลล์เรียกไม่ได้", sale.get("/api/admin/social?video=" + PID + "_1", secure=True).status_code == 401)
    ok("ไม่ login เรียกไม่ได้", client(None).get("/api/admin/social?frames=x", secure=True).status_code == 401)

    # ── 6) ภาพทีละวินาที: ยิงแอดวิวสูง TOP_N + คลิปใหม่ ─────────────────
    print("\n[6] เกณฑ์ภาพทีละวินาที (ยิงแอด + วิวสูงสุด TOP_N · + คลิปใหม่)")
    import json as _json
    from datetime import timedelta

    from django.core.management import call_command

    from dashboard.models import MetaRaw
    t_now = timezone.now()

    def snap(n, views, paid, ptype="video", at=None):
        MetaPostSnapshot.objects.create(taken_at=at or t_now, snap_date=timezone.localdate(), trigger="cron",
                                        page_id=PID, post_id="%s_%d" % (PID, n), post_type=ptype,
                                        created_time=NOW, video_views=views, video_views_paid=paid)
    # 30 คลิปยิงแอด วิว 100..3000 (ตัวที่ 129 วิวมากสุด) + คลิปไม่ยิงแอดวิวสูงมาก + รูปที่ยิงแอด
    for i in range(30):
        snap(100 + i, 100 + i * 100, 10)
    snap(200, 99999, 0)                                   # วิวสูงสุดแต่ไม่ได้ยิงแอด
    snap(201, 50000, 500, ptype="photo")                  # ยิงแอดแต่เป็นรูป
    snap(202, 88888, 800, at=t_now - timedelta(days=5))   # ยิงแอดแต่หลุดหน้าต่างดึงไปแล้ว
    snap(129, 2900, 10, at=t_now - timedelta(hours=1))    # แถวเก่าของโพสต์เดิม (ต้องเลือกแถวล่าสุด)
    # อันดับ 2 (ยิงแอด) มีแถวกราฟเก่า 20 วัน = ไม่ใช่คลิปใหม่ · ไว้ดูว่าทำภาพพลาดแล้วจดเหตุผลลงตาราง
    MetaVideoRetention.objects.create(page_id=PID, post_id=PID + "_128", created_time=t_now - timedelta(days=20),
                                      length_sec=40.0, curve=meta_sync._curve(LIN))
    el = video_frames.eligible(fresh=True)
    ids = [r["post_id"] for r in el]
    ads = [r for r in el if r["reason"] == "ads"]
    new = [r["post_id"] for r in el if r["reason"] == "new"]
    ok("ยิงแอดได้ %d คลิป (TOP_N)" % video_frames.TOP_N, len(ads) == video_frames.TOP_N, len(ads))
    ok("เรียงวิวมากสุดก่อน (แถวล่าสุดของโพสต์ = 3000 ไม่ใช่แถวเก่า 2900)", ids[0] == PID + "_129" and el[0]["views"] == 3000, el[:2])
    ok("ไม่ได้ยิงแอด = ไม่เข้า (แม้วิวสูงสุด)", PID + "_200" not in ids)
    ok("รูปที่ยิงแอด = ไม่เข้า", PID + "_201" not in ids)
    ok("แถวเก่ากว่ารอบล่าสุดเกิน 2 วัน = ไม่นับ", PID + "_202" not in ids)
    ok("โพสต์เดียวไม่ซ้ำ (ยิงแอด + คลิปใหม่ไม่ซ้ำกัน)", len(ids) == len(set(ids)))
    # 25 อันดับ = _129.._106 (24 คลิป) + _1 (วิว 1000 ยิงแอดจากข้อ [3]) → _105 อันดับ 26
    ok("อันดับ 26 ลงไปไม่เข้า", PID + "_105" not in ids and PID + "_106" in ids and PID + "_1" in ids, ids[-3:])
    ok("คลิปใหม่ 7 วัน (มีกราฟ) ได้ภาพด้วย แม้ไม่ยิงแอด", new == [PID + "_3"], new)
    ok("คลิปเก่า 20 วัน ไม่นับเป็นคลิปใหม่", video_frames.reason_of(PID + "_128") == "ads")
    ok("ปิดคลิปใหม่ได้ (new_days=0)", not [r for r in video_frames.eligible(new_days=0) if r["reason"] == "new"])

    EXTRACTED = []

    def fake_extract2(post_id, d):
        EXTRACTED.append(post_id)
        if post_id == PID + "_128":
            raise RuntimeError("ไฟล์วิดีโอใหญ่เกิน")
        return fake_extract(post_id, d)

    with mock.patch.object(video_frames, "_extract", fake_extract2):
        st = video_frames.for_detail(PID + "_200")
        ok("นอกกลุ่ม = skip ไม่โหลดคลิป · บอกเกณฑ์", st["state"] == "skip" and st["top"] == video_frames.TOP_N
           and st["newDays"] == video_frames.NEW_DAYS and not EXTRACTED, st)
        ok("คลิปที่มีภาพอยู่แล้ว ยังเปิดดูได้", video_frames.for_detail(PID + "_1")["state"] == "ready")
        r = video_frames.prefetch(3, new_days=0)
        ok("ทำล่วงหน้าทีละคลิป: 3 อันดับแรก (สำเร็จ 2 พลาด 1)", r["total"] == 3 and r["made"] == 2
           and r["failed"] == 1 and len(r["errors"]) == 1, r)
        ok("ภาพของอันดับ 1 พร้อมแล้ว", video_frames.status(PID + "_129")["state"] == "ready")
        e128 = MetaVideoRetention.objects.get(post_id=PID + "_128")
        ok("ทำภาพพลาด = จดเหตุผลลงตาราง", "ใหญ่เกิน" in e128.frames_error and e128.frames_n == 0, e128.frames_error)
        n0 = len(EXTRACTED)
        r = video_frames.prefetch(3, new_days=0)
        ok("รอบซ้ำ = ไม่ทำซ้ำของที่มีแล้ว · ที่พลาดยังไม่ลองใหม่ทันที", r["ready"] == 2 and r["made"] == 0
           and len(EXTRACTED) == n0, r)
        r = video_frames.prefetch(10, limit=2, new_days=0)
        ok("--limit จำกัดจำนวนที่ทำต่อรอบ", r["made"] + r["failed"] == 2, r)
        r = video_frames.prefetch(0)
        ok("คลิปใหม่ได้ภาพเองโดยไม่ต้องมีคนเปิด", r["made"] == 1 and video_frames.status(PID + "_3")["state"] == "ready", r)
        r3 = MetaVideoRetention.objects.get(post_id=PID + "_3")
        ok("ทำภาพสำเร็จ = จดจำนวนภาพ/เวลา/เหตุผลลงตาราง", r3.frames_n == 3 and r3.frames_at and r3.frames_reason == "new"
           and not r3.frames_error, (r3.frames_n, r3.frames_reason))
        st = video_frames.for_detail(PID + "_120")
        ok("ในกลุ่มแต่ยังไม่มีภาพ = เริ่มทำตอนเปิดดู", st["state"] in ("running", "ready"), st)
        for _ in range(50):
            if video_frames.status(PID + "_120")["state"] == "ready":
                break
            time.sleep(0.05)
        r = adm.get("/api/admin/social?video=" + PID + "_200", secure=True)
        ok("API คลิปนอกกลุ่ม = frames.state skip", r.status_code == 200 and r.json()["frames"]["state"] == "skip",
           str(r.content[:200]))

    # ลบภาพของคลิปที่หลุดเกณฑ์ (ทำไว้นานเกิน PRUNE_GRACE_DAYS) · ยังไม่ถึงกำหนด = เก็บไว้
    old_d, fresh_d = video_frames._dir(PID + "_998"), video_frames._dir(PID + "_997")
    for d in (old_d, fresh_d):
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "001.jpg"), "wb").write(b"x")
        video_frames._write_info(d, {"n": 1, "at": "x"})
    ten = time.time() - 10 * 86400
    os.utime(os.path.join(old_d, "info.json"), (ten, ten))
    n = video_frames.prune({PID + "_129"})
    ok("หลุดเกณฑ์นานเกินกำหนด = ลบภาพ · เพิ่งทำ = เก็บไว้", n >= 1 and not os.path.exists(old_d)
       and os.path.exists(fresh_d), (n, os.path.exists(old_d), os.path.exists(fresh_d)))

    video_frames._PREFETCH["on"] = True
    ok("กำลังทำล่วงหน้าอยู่ = ไม่เริ่มซ้ำ", video_frames.start_prefetch() is False
       and video_frames.prefetch_guarded() is None)
    video_frames._PREFETCH["on"] = False
    out = os.path.join(MEDIA, "mf.txt")
    call_command("meta_frames", out=out)
    txt = open(out, encoding="utf-8").read()
    ok("คำสั่ง meta_frames บอกรายชื่อ + เหตุผล + มีภาพกี่คลิป", PID + "_129" in txt and "มีภาพแล้ว" in txt
       and "มีภาพ 3 ภาพ" in txt and "[คลิปใหม่]" in txt and "[ยิงแอด]" in txt, txt[:300])

    # ── 7) ข้อมูลดิบ + ผลวิเคราะห์ในฐานข้อมูล + รอบคลิปใหม่รายชั่วโมง ───────
    print("\n[7] ข้อมูลดิบ · ผลวิเคราะห์ · คลิปใหม่อัตโนมัติ")
    raws = list(MetaRaw.objects.filter(kind__in=("retention", "videos")))
    ok("คำตอบดิบของ Facebook เก็บลง dash_meta_raw (กราฟ + ความยาวคลิป)",
       {r.kind for r in raws} == {"retention", "videos"}, {r.kind for r in raws})
    ok("ข้อมูลดิบไม่มี token", not any("PAGE_TOKEN" in _json.dumps(r.data) or "access_token" in _json.dumps(r.data)
                                       for r in raws))
    v1 = MetaVideoRetention.objects.get(post_id=PID + "_1")
    ok("ผลวิเคราะห์เป็นคอลัมน์ (ตรงกับ _kpi ของหน้าเว็บ)", v1.hook_pct == 94.0 and v1.end_pct == 20.0
       and v1.half_sec == 27 and v1.hold_to == "15" and v1.analyzed_at is not None,
       (v1.hook_pct, v1.end_pct, v1.half_sec, v1.hold_to))
    ok("% ทีละวินาที 41 ค่า (คลิป 40 วิ)", len(v1.persec) == 41 and v1.persec[0] == 100.0, v1.persec[:3])
    ok("จดเวลาที่ระบบเจอคลิปครั้งแรก", v1.first_seen is not None)
    MetaVideoRetention.objects.create(page_id=PID, post_id=PID + "_77", length_sec=40.0, curve=meta_sync._curve(STEP))
    ok("analyze_missing คิดให้แถวที่ยังไม่มีผลวิเคราะห์", social_stats.analyze_missing() == 2   # _77 + _128 (สร้างเองในข้อ 6)
       and MetaVideoRetention.objects.get(post_id=PID + "_77").drop_sec == 5)
    ok("analyze_missing รอบสอง = ไม่มีอะไรต้องทำ", social_stats.analyze_missing() == 0)

    # คลิปใหม่โผล่ใน Facebook → รอบรายชั่วโมงดึงกราฟ + วิเคราะห์ + ทำภาพเอง
    POSTS.insert(0, {"id": PID + "_5", "created_time": ISO, "insights": ins(LIN),
                     "attachments": {"data": [{"media_type": "video", "target": {"id": "V5"}}]}})
    VIDEOS.insert(0, {"id": "V5", "length": 20.0, "created_time": ISO})
    fs = v1.first_seen
    with mock.patch.object(video_frames, "_extract", fake_extract):
        w = meta_sync.watch_videos("test")
    ok("รอบคลิปใหม่: เจอคลิปใหม่ 1 คลิป", w["new"] == 1 and w["newIds"] == [PID + "_5"] and w["ok"], w)
    v5 = MetaVideoRetention.objects.get(post_id=PID + "_5")
    ok("คลิปใหม่ถูกวิเคราะห์ทันที", v5.hook_pct is not None and v5.length_sec == 20.0 and len(v5.persec) == 21,
       (v5.hook_pct, v5.length_sec))
    ok("คลิปใหม่ได้ภาพทันที (ไม่ต้องรอใครเปิด)", v5.frames_n == 3 and v5.frames_reason == "new"
       and video_frames.status(PID + "_5")["state"] == "ready", (v5.frames_n, v5.frames_reason))
    ok("คลิปเดิมไม่ถูกนับเป็นคลิปใหม่ซ้ำ · first_seen ไม่เปลี่ยน",
       MetaVideoRetention.objects.get(post_id=PID + "_1").first_seen == fs)
    from dashboard.services import cache_store
    ok("ผลรอบล่าสุดเก็บที่ KV video_watch_last", (cache_store.get_kv("video_watch_last") or {}).get("data", {}).get("new") == 1)

    # ตัวตั้งเวลา (cron_tick เรียกทุกนาที)
    from datetime import datetime as _dt
    started = []

    class _T:
        def __init__(self, target=None, **kw):
            self.t = target

        def start(self):
            started.append(self.t)
    cache_store.set_kv("video_watch_last", {})
    with mock.patch.object(meta_sync.threading, "Thread", _T):
        ok("ช่วงเที่ยงคืน–ตี 3 ไม่ทำ (รอบใหญ่ทำอยู่)", meta_sync.maybe_watch(_dt(2026, 10, 15, 1, 0)) == "")
        ok("ถึงรอบ = เริ่มใน thread", meta_sync.maybe_watch(_dt(2026, 10, 15, 10, 0)) == "started" and len(started) == 1)
        ok("ยังไม่ครบชั่วโมง = ไม่ทำซ้ำ", meta_sync.maybe_watch(_dt(2026, 10, 15, 10, 5)) == "" and len(started) == 1)
        cache_store.set_kv("video_watch_last", {})
        meta_sync._lock("manual", "test")
        ok("รอบใหญ่/กด sync เองกำลังทำ = ไม่ซ้อน", meta_sync.maybe_watch(_dt(2026, 10, 15, 11, 0)) == "busy")
        meta_sync._unlock()
    # ── 8) ปิดการตัดภาพ (เจ้าของสั่ง "ไม่ต้องดาวน์โหลดวิดีโอ แค่ลิงก์ + รูปปก") · คลิปเก่าดึงกราฟตอนเปิดดู ──
    print("\n[8] ปิดการโหลดวิดีโอ · รูปปก + ลิงก์ · คลิปเก่าดึงกราฟเอง")
    video_frames.ENABLED = False
    EXTRACTED.clear()
    with mock.patch.object(video_frames, "_extract", fake_extract2):
        ok("ปิดอยู่: for_detail/ensure = off · ไม่โหลดคลิป", video_frames.for_detail(PID + "_120")["state"] == "off"
           and video_frames.ensure(PID + "_120")["state"] == "off" and not EXTRACTED)
        r = video_frames.prefetch()
        ok("ปิดอยู่: prefetch ไม่ทำอะไร", r.get("off") and r["total"] == 0 and not EXTRACTED, r)
        ok("ปิดอยู่: start_prefetch ไม่เริ่ม", video_frames.start_prefetch() is False)
        w = meta_sync.watch_videos("test")
        ok("ปิดอยู่: รอบคลิปใหม่ยังดึงกราฟ+วิเคราะห์ แต่ไม่ทำภาพ", w["videos"] >= 1 and w["frames"].get("off")
           and not EXTRACTED and w["ok"], w)
    # คลิปเก่ากว่า 90 วัน: อยู่ในตารางโพสต์ (snapshot) แต่รอบปกติไม่ได้ดึงกราฟ — เหมือนคลิป 10/7 ที่เจ้าของเปิด
    OLD.append({"id": PID + "_9", "created_time": (NOW - timedelta(days=120)).strftime("%Y-%m-%dT%H:%M:%S+0000"),
                "insights": ins(LIN), "attachments": {"data": [{"media_type": "video", "target": {"id": "V9"}}]}})
    MetaPostSnapshot.objects.create(taken_at=t_now, snap_date=timezone.localdate(), trigger="cron", page_id=PID,
                                    post_id=PID + "_9", post_type="video", created_time=NOW - timedelta(days=120),
                                    video_views=142868, permalink="https://www.facebook.com/x/videos/9")
    ok("ก่อนเปิด: ยังไม่มีกราฟคลิปเก่า", not MetaVideoRetention.objects.filter(post_id=PID + "_9").exists())
    nraw = MetaRaw.objects.count()
    CALLS.clear()
    d9 = social_stats.video_detail(PID + "_9")
    H9 = social_stats._kpi(meta_sync._curve(LIN), 30.0)["hook"]        # คลิปยาว 30 วิ
    ok("เปิดคลิปเก่า → ดึงกราฟคลิปเดียวเดี๋ยวนั้น + วิเคราะห์", d9.get("has") and d9["kpi"]["hook"] == H9 == 92.0
       and d9["len"] == 30.0, {k: d9.get(k) for k in ("has", "len", "retError")})
    ok("คลิปเก่า: เก็บรูปหน้าปก · ไม่มีลิงก์ไฟล์วิดีโอ · ภาพ = off", "_9.jpg" in d9.get("cover", "")
       and "source" not in d9 and d9["frames"]["state"] == "off", (d9.get("cover"), d9.get("frames")))
    ok("คลิปเก่า: คำตอบดิบเก็บลงฐานข้อมูล (กราฟ + ความยาว)", MetaRaw.objects.count() - nraw == 2)
    ok("คลิปเก่า: แถวกราฟ + ผลวิเคราะห์อยู่ในตาราง", MetaVideoRetention.objects.get(post_id=PID + "_9").hook_pct == H9)
    CALLS.clear()
    social_stats.video_detail(PID + "_9")
    ok("เปิดซ้ำ = ไม่ยิง Facebook อีก (มีกราฟ + รูปปกแล้ว)", not CALLS, CALLS)
    # คลิปที่ Facebook ยังไม่ให้กราฟ (ยังไม่มีคนดู) — ลองครั้งเดียวต่อชั่วโมง ไม่ยิงทุกครั้งที่เปิด
    MetaPostSnapshot.objects.create(taken_at=t_now, snap_date=timezone.localdate(), trigger="cron", page_id=PID,
                                    post_id=PID + "_4", post_type="video", created_time=NOW)
    social_stats._RET_TRY.pop(PID + "_4", None)
    CALLS.clear()
    d4 = social_stats.video_detail(PID + "_4")
    n1 = len(CALLS)
    social_stats.video_detail(PID + "_4")
    ok("ไม่มีกราฟ: ลองดึงครั้งเดียว · เปิดซ้ำในชั่วโมงเดียวกันไม่ยิงซ้ำ", not d4.get("has") and n1 >= 1 and len(CALLS) == n1,
       (n1, len(CALLS)))
    r = adm.get("/api/admin/social?video=" + PID + "_9", secure=True)
    ok("API: คลิปเก่าได้กราฟ + รูปปก", r.status_code == 200 and r.json()["has"] and r.json()["cover"], str(r.content[:200]))
    # ลบภาพที่ทำไปแล้ว (manage.py meta_frames --purge)
    nclip = len([e for e in os.scandir(video_frames._root()) if e.is_dir()])
    pr = video_frames.purge()
    ok("purge: ลบภาพทั้งหมด + ล้างช่อง frames ในตาราง", pr["clips"] == nclip and nclip > 0
       and not os.path.exists(video_frames._root())
       and not MetaVideoRetention.objects.exclude(frames_n=0).exists(), (pr, nclip))
    out = os.path.join(MEDIA, "mf2.txt")
    call_command("meta_frames", out=out)
    ok("คำสั่ง meta_frames บอกว่าปิดอยู่", "ปิดอยู่" in open(out, encoding="utf-8").read())

    # รูปปกเก็บแบบย่อ (Facebook ให้รูปเต็ม 1080×1920 ~400 KB) — ประหยัดพื้นที่
    import io as _io

    from PIL import Image as _Img

    from dashboard.services import covers as _cv
    _b = _io.BytesIO()
    _Img.effect_noise((1080, 1920), 60).convert("RGB").save(_b, "JPEG", quality=95)
    big = _b.getvalue()
    small = _cv._shrink(big)
    ok("ย่อรูปปก: ด้านยาวไม่เกิน 720 · ไฟล์เล็กลง", max(_Img.open(_io.BytesIO(small)).size) <= _cv.MAX_SIDE_PX
       and len(small) < len(big) / 3, (len(big), len(small)))
    ok("ไฟล์ที่ไม่ใช่รูป = คืนของเดิม (ไม่พัง)", _cv._shrink(b"not-an-image") == b"not-an-image")
    _p = _cv.path_for("meta", PID + "_big")
    os.makedirs(os.path.dirname(_p), exist_ok=True)
    open(_p, "wb").write(big)
    _r = _cv.shrink_all("meta")
    ok("shrink_all ย่อรูปเดิมที่ใหญ่ · รูปเล็กอยู่แล้วไม่แตะ", _r["files"] == 1 and os.path.getsize(_p) < len(big) / 3, _r)

    cache_store.set_kv("video_watch_last", {"at": timezone.now().isoformat(), "errors": ["ทดสอบ: ดึงกราฟพัง"]})
    r = adm.get("/api/admin/system_health", secure=True)
    ok("หน้าสถานะระบบร้องเมื่อรอบคลิปใหม่พัง (บล็อกเช็คได้รันจริง)",
       r.status_code == 200 and "รอบวิเคราะห์คลิปใหม่" in r.content.decode("utf-8"), r.content[:300])
finally:
    for p in P:
        p.stop()
    _runner.teardown_databases(_old)

print()
print("ผ่านทั้งหมด" if not FAILS else "ไม่ผ่าน %d ข้อ: %s" % (len(FAILS), ", ".join(FAILS)))
sys.exit(1 if FAILS else 0)
