# -*- coding: utf-8 -*-
"""เทสต์หน้า "คอมเมนต์" ของ Connect (★ 17 ต.ค.69 · checkout/comments.py)

    python scripts/test_comments.py

  - Facebook: โพสต์เพจ + โพสต์โฆษณา · ข้ามคอมเมนต์ของเพจเอง · เพจตอบแล้ว = replied · โพสต์เก่าเกินหยุดไล่ ·
    รันซ้ำไม่เบิ้ล · "จัดการแล้ว" ไม่ถูกรอบดึงทับ · โควต้า Meta เกิน = ไม่ยิง · ยิงเฉพาะเพจของบริษัท
  - YouTube: ข้ามคอมเมนต์ของช่องเอง · ช่องตอบแล้ว = replied · ชื่อคลิปจากตาราง snapshot · ช่องหนึ่งพังไม่ลากช่องอื่น
  - รายการ/ตัวเลขรอตอบ · ตัวกรอง · สิทธิ์ (แอดมินเท่านั้น) · ปุ่มดึงตอนนี้ห่างกัน ≥2 นาที · ลบเก่า · ล็อกกันรันซ้อน

ฐานข้อมูลทดสอบแยก · **ปลอมที่ขอบระบบเท่านั้น** (`requests` = Graph API / YouTube) — ไม่ปลอมฟังก์ชันของเราเอง
"""
import io
import json
import os
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
settings.META_ACCESS_TOKEN = "tok-meta"
settings.META_PAGE_IDS = ["111"]
settings.META_AD_ACCOUNTS = []
settings.YOUTUBE_API_KEY = "yt-key"
settings.YOUTUBE_CHANNELS = ["UCabc"]
settings.LINE_CHANNEL_ACCESS_TOKEN = ""

import requests  # noqa: E402
from django.contrib.sessions.backends.signed_cookies import SessionStore  # noqa: E402
from django.test import Client  # noqa: E402
from django.utils import timezone  # noqa: E402

from checkout import connect as C  # noqa: E402
C.BG_FILL = False
import checkout.people as _people  # noqa: E402
_people.BG = False
from checkout import leadflow as _LF  # noqa: E402
_LF.BG_SLOW = False
from checkout import chatmedia as _CMD  # noqa: E402
_CMD.BG = False
from checkout import comments as CM  # noqa: E402
CM.BG = False
from checkout.models import Employee, SocialComment as SC  # noqa: E402
from dashboard.models import KVStore, YouTubeChannelSnapshot, YouTubeVideoSnapshot  # noqa: E402
from dashboard.services import meta  # noqa: E402

NOW = timezone.now()


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S+0000")


def yiso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class _R:
    def __init__(self, code=200, js=None):
        self.status_code, self._js = code, (js or {})
        self.text = json.dumps(self._js)
        self.headers = {}

    def json(self):
        return self._js


CALLS = []
LIKES = {"c1": 0}
YT_FAIL = set()


def _feed():
    return {"data": [
        {"id": "111_p1", "message": "รถเข้าใหม่ Civic FE\nราคาพิเศษ", "created_time": iso(NOW - timedelta(days=1)),
         "permalink_url": "https://facebook.com/111/posts/p1", "full_picture": "https://scontent.example/p1.jpg",
         "comments": {"data": [
             {"id": "p1_c1", "message": "ราคาเท่าไหร่ครับ", "created_time": iso(NOW - timedelta(hours=3)),
              "from": {"id": "u1", "name": "สมชาย"}, "like_count": LIKES["c1"], "comment_count": 0,
              "permalink_url": "https://facebook.com/c1"},
             {"id": "p1_c2", "message": "สนใจ ทักแชทไปแล้ว", "created_time": iso(NOW - timedelta(hours=5)),
              "from": {"id": "u2", "name": "สมหญิง"}, "comment_count": 1,
              "comments": {"data": [{"from": {"id": "111", "name": "เพจทดสอบ"}, "created_time": iso(NOW - timedelta(hours=4))}]}},
             {"id": "p1_c3", "message": "ขอบคุณที่สนใจครับ", "created_time": iso(NOW - timedelta(hours=2)),
              "from": {"id": "111", "name": "เพจทดสอบ"}},
             {"id": "p1_c4", "message": "เก่ามาก", "created_time": iso(NOW - timedelta(days=100)),
              "from": {"id": "u4", "name": "เก่า"}},
             {"id": "p1_c6", "created_time": iso(NOW - timedelta(hours=1)), "attachment": {"type": "photo"},
              "from": {"id": "u6", "name": "ส่งรูป"}},
         ]}},
        {"id": "111_p2", "message": "โพสต์เก่า", "created_time": iso(NOW - timedelta(days=70)),
         "comments": {"data": [{"id": "p2_c1", "message": "ไม่ควรถูกเก็บ", "created_time": iso(NOW - timedelta(days=1)),
                                "from": {"id": "u9", "name": "x"}}]}},
    ]}


def _ads():
    return {"data": [
        {"id": "111_ad1", "message": "โฆษณา HRV", "created_time": iso(NOW - timedelta(days=200)),
         "permalink_url": "https://facebook.com/111/posts/ad1",
         "comments": {"data": [{"id": "ad1_c1", "message": "ผ่อนเดือนละเท่าไหร่", "created_time": iso(NOW - timedelta(hours=6))}]}},
    ]}


def _yt(params):
    cid = params.get("allThreadsRelatedToChannelId")
    if cid in YT_FAIL:
        return _R(403, {"error": {"message": "forbidden", "errors": [{"reason": "forbidden"}]}})
    return _R(200, {"items": [
        {"id": "t1", "snippet": {"videoId": "v1", "totalReplyCount": 1, "topLevelComment": {"id": "t1", "snippet": {
            "authorDisplayName": "@viewer", "authorProfileImageUrl": "https://yt3.example/a.jpg",
            "authorChannelId": {"value": "UCviewer"}, "textOriginal": "คันนี้ยังอยู่ไหม", "likeCount": 2,
            "publishedAt": yiso(NOW - timedelta(hours=2))}}},
         "replies": {"comments": [{"snippet": {"authorChannelId": {"value": cid}, "publishedAt": yiso(NOW - timedelta(hours=1))}}]}},
        {"id": "t2", "snippet": {"videoId": "v1", "topLevelComment": {"id": "t2", "snippet": {
            "authorDisplayName": "@ช่องเรา", "authorChannelId": {"value": cid}, "textOriginal": "ปักหมุด",
            "publishedAt": yiso(NOW - timedelta(hours=3))}}}},
        {"id": "t3", "snippet": {"videoId": "v2", "totalReplyCount": 0, "topLevelComment": {"id": "t3", "snippet": {
            "authorDisplayName": "@buyer", "authorChannelId": {"value": "UCbuyer"}, "textOriginal": "ขอเบอร์ติดต่อ",
            "publishedAt": yiso(NOW - timedelta(hours=4))}}}},
    ]})


def _get(url, params=None, **k):
    params = params or {}
    CALLS.append((url, dict(params)))
    if "googleapis.com/youtube" in url:
        return _yt(params)
    if "graph.facebook.com" in url:
        path = url.split("graph.facebook.com/", 1)[1].split("/", 1)[1]
        if path == "111" and params.get("fields") == "access_token":
            return _R(200, {"id": "111", "access_token": "ptok"})
        if path == "111" and params.get("fields") == "name":
            return _R(200, {"id": "111", "name": "เพจทดสอบ"})
        if path == "111/feed":
            return _R(200, _feed())
        if path == "111/ads_posts":
            return _R(200, _ads())
    return _R(404, {"error": {"message": "not found"}})


def _post(url, *a, **k):
    return _R(404, {})


requests.get, requests.post = _get, _post

OK, BAD = [], []


def ck(name, cond, got=""):
    (OK if cond else BAD).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else "   ได้: %r" % (got,)))


def client(user):
    cl = Client()
    if user:
        st = SessionStore()
        st["oxlet_user"] = user
        st.save()
        cl.cookies[settings.SESSION_COOKIE_NAME] = st.session_key
    return cl


def J(cl, path, body=None):
    r = cl.post(path, json.dumps(body), content_type="application/json", secure=True) if body is not None \
        else cl.get(path, secure=True)
    try:
        return r.status_code, json.loads(r.content.decode("utf-8"))
    except Exception:
        return r.status_code, {}


try:
    print("[1] Facebook — โพสต์เพจ + โฆษณา")
    r = CM.sync_fb()
    fb = {x.ext_id: x for x in SC.objects.filter(platform=SC.FB)}
    ck("เก็บคอมเมนต์ลูกค้า 4 อัน (2 ข้อความ + 1 รูป + 1 ใต้โฆษณา)", set(fb) == {"p1_c1", "p1_c2", "p1_c6", "ad1_c1"}, sorted(fb))
    ck("ข้ามคอมเมนต์ของเพจเอง", "p1_c3" not in fb)
    ck("ข้ามคอมเมนต์เก่ากว่า 90 วัน", "p1_c4" not in fb)
    ck("โพสต์เก่ากว่า 60 วัน = หยุดไล่ (ไม่เก็บคอมเมนต์ใต้โพสต์นั้น)", "p2_c1" not in fb)
    ck("เพจตอบใต้คอมเมนต์แล้ว = replied", fb["p1_c2"].replied and fb["p1_c2"].replied_at is not None)
    ck("ยังไม่ได้ตอบ = replied False", not fb["p1_c1"].replied)
    ck("คอมเมนต์รูปไม่มีข้อความ = [รูป]", fb["p1_c6"].text == "[รูป]", fb["p1_c6"].text)
    ck("คอมเมนต์ใต้โฆษณา = is_ad + ชื่อคนว่างได้", fb["ad1_c1"].is_ad and fb["ad1_c1"].author_name == "")
    ck("ชื่อเพจ + ชื่อโพสต์บรรทัดแรก", fb["p1_c1"].account_name == "เพจทดสอบ" and fb["p1_c1"].post_title == "รถเข้าใหม่ Civic FE",
       (fb["p1_c1"].account_name, fb["p1_c1"].post_title))
    ck("ผลรอบแรก new=4", r.get("new") == 4, r)
    nodes = {u.split("graph.facebook.com/", 1)[1].split("/")[1] for u, _ in CALLS if "graph.facebook.com" in u}
    ck("ยิงเฉพาะเพจของบริษัท (111)", nodes == {"111"}, nodes)
    ck("ดึงโฆษณาพร้อม include_inline_create", any("ads_posts" in u and p.get("include_inline_create") == "true" for u, p in CALLS))

    print("[2] รันซ้ำ / จัดการแล้ว")
    CM.set_done(fb["p1_c1"].id, "แอดมินทดสอบ", True)
    r2 = CM.sync_fb()
    ck("รันซ้ำไม่เบิ้ล", SC.objects.filter(platform=SC.FB).count() == 4 and r2.get("new") == 0, r2)
    LIKES["c1"] = 7
    r3 = CM.sync_fb()
    c1 = SC.objects.get(platform=SC.FB, ext_id="p1_c1")
    ck("ไลก์เปลี่ยน = อัปเดตแถวเดิม", c1.like_count == 7 and r3.get("updated") == 1, (c1.like_count, r3))
    ck("รอบดึงไม่ทับ 'จัดการแล้ว'", c1.done_at is not None and c1.done_by == "แอดมินทดสอบ")

    print("[3] YouTube")
    YouTubeChannelSnapshot.objects.create(taken_at=NOW, snap_date=NOW.date(), channel_id="UCabc", title="ช่องทดสอบ")
    YouTubeVideoSnapshot.objects.create(taken_at=NOW, snap_date=NOW.date(), channel_id="UCabc", video_id="v1", title="รีวิว City")
    ry = CM.sync_yt()
    yt = {x.ext_id: x for x in SC.objects.filter(platform=SC.YT)}
    ck("เก็บ 2 กระทู้ (ข้ามของช่องเอง)", set(yt) == {"t1", "t3"}, sorted(yt))
    ck("ช่องตอบแล้ว = replied", yt["t1"].replied and not yt["t3"].replied)
    ck("ชื่อคลิปจากตาราง snapshot", yt["t1"].post_title == "รีวิว City", yt["t1"].post_title)
    ck("ลิงก์คอมเมนต์ไปตรงกระทู้ (&lc=)", "&lc=t1" in yt["t1"].url and yt["t1"].post_thumb.endswith("/v1/mqdefault.jpg"))
    ck("ขอแบบ allThreadsRelatedToChannelId + เรียงเวลา", any("commentThreads" in u and p.get("allThreadsRelatedToChannelId") == "UCabc"
                                                          and p.get("order") == "time" for u, p in CALLS))
    YouTubeChannelSnapshot.objects.create(taken_at=NOW, snap_date=NOW.date(), channel_id="UCbad", title="ช่องพัง")
    YT_FAIL.add("UCbad")
    ry2 = CM.sync_yt()
    ck("ช่องหนึ่งพัง ช่องอื่นยังเก็บ + บอกเหตุผล", "ช่องพัง" in (ry2.get("error") or "") and SC.objects.filter(platform=SC.YT).count() == 2, ry2)

    print("[4] รายการ / ตัวเลข / ตัวกรอง")
    d = CM.list_json()
    ck("รอตอบ: Facebook 2 (c1 จัดการแล้ว · c2 เพจตอบแล้ว ไม่นับ)", d["counts"]["fb"] == 2, d["counts"])
    ck("รอตอบ: YouTube 1", d["counts"]["yt"] == 1, d["counts"])
    ck("รวม = 3 · TikTok 0", d["counts"]["all"] == 3 and d["counts"]["tt"] == 0, d["counts"])
    ck("รายการรอตอบไม่มีที่ตอบแล้ว/จัดการแล้ว", {r["id"] for r in d["rows"]} == set(
        SC.objects.filter(ext_id__in=["p1_c6", "ad1_c1", "t3"]).values_list("id", flat=True)))
    d2 = CM.list_json(platform="yt", status="all")
    ck("กรองช่องทาง YouTube + ทั้งหมด", {r["platform"] for r in d2["rows"]} == {"yt"} and len(d2["rows"]) == 2)
    d3 = CM.list_json(status="done")
    ck("ตอบแล้ว/จัดการแล้ว", {r["id"] for r in d3["rows"]} == set(
        SC.objects.filter(ext_id__in=["p1_c1", "p1_c2", "t1"]).values_list("id", flat=True)), [r["id"] for r in d3["rows"]])
    d4 = CM.list_json(status="all", q="ผ่อน")
    ck("ค้นข้อความ", [r["text"] for r in d4["rows"]] == ["ผ่อนเดือนละเท่าไหร่"], [r["text"] for r in d4["rows"]])
    ck("ไม่ส่ง id คนคอมเมนต์ออกหน้าเว็บ", all("author_id" not in r and "authorId" not in r for r in d2["rows"]))
    ck("TikTok = รออนุมัติ", d["sources"]["tt"]["pending"] and not d["sources"]["tt"]["on"])

    print("[5] รอบดึง / โควต้า / ล็อก")
    out = CM.run([SC.FB, SC.YT], "cron")
    st = CM.state()
    ck("run() จดสถานะทั้ง 2 ช่องทาง", st.get("fb", {}).get("at") and st.get("yt", {}).get("at"), st)
    ck("ช่องพัง = yt ok False แต่ fb ok True", out["fb"]["ok"] and out["yt"]["ok"] is False, out)
    ck("ไม่ถึงรอบ = ไม่ดึง", not CM._due(SC.FB, CM.FB_EVERY_MIN, timezone.now()))
    ck("ถึงรอบ", CM._due(SC.FB, CM.FB_EVERY_MIN, timezone.now() + timedelta(minutes=11)))
    meta.last_usage.update(pct=80)
    n0 = len(CALLS)
    out2 = CM.run([SC.FB], "cron")
    ck("โควต้า Meta เกิน = ไม่ยิง Graph + บอกเหตุผล", out2["fb"]["ok"] is False and "โควต้า" in out2["fb"]["error"]
       and not any("graph.facebook.com" in u for u, _ in CALLS[n0:]), out2)
    meta.last_usage.update(pct=0)
    ck("ล็อกครั้งแรกได้", CM._lock())
    ck("ล็อกซ้อนไม่ได้", not CM._lock())
    CM._unlock()
    KVStore.objects.create(key=CM.LOCK_KEY, data={})
    KVStore.objects.filter(pk=CM.LOCK_KEY).update(updated_at=timezone.now() - timedelta(minutes=30))
    ck("ล็อกค้างเกิน 15 นาที = รับช่วงต่อได้", CM._lock())
    CM._unlock()
    ck("tick ในเทสต์ไม่แตก thread", CM.tick_bg(timezone.now() + timedelta(hours=1)) == {})

    print("[6] หน้าเว็บ / สิทธิ์")
    Employee.objects.create(nickname="เซลล์เอ", position="ทีม A")
    ADM = client({"user_id": "admin", "nickname": "admin", "position": "admin"})
    SEL = client({"user_id": "Usel", "nickname": "เซลล์เอ", "position": "seller"})
    s_, d = J(Client(), "/connect/api/comments")
    ck("ไม่ login = 401", s_ == 401, s_)
    s_, d = J(SEL, "/connect/api/comments")
    ck("เซลล์ = 403", s_ == 403, (s_, d))
    s_, d = J(ADM, "/connect/api/comments?status=all&limit=20")
    ck("แอดมินเปิดได้", s_ == 200 and d.get("ok") and len(d.get("rows") or []) == 6, (s_, len(d.get("rows") or [])))
    t3 = SC.objects.get(ext_id="t3")
    s_, d = J(ADM, "/connect/api/comments", {"action": "done", "id": t3.id, "on": True})
    ck("กดจัดการแล้ว", s_ == 200 and d["row"]["done"] and d["row"]["doneBy"] == "admin", (s_, d))
    s_, d = J(ADM, "/connect/api/comments", {"action": "done", "id": t3.id, "on": False})
    ck("ยกเลิกจัดการแล้ว", s_ == 200 and not d["row"]["done"], d)
    s_, d = J(SEL, "/connect/api/comments", {"action": "done", "id": t3.id})
    ck("เซลล์กดจัดการแล้วไม่ได้", s_ == 403, s_)
    s_, d = J(ADM, "/connect/api/comments", {"action": "done", "id": 999999})
    ck("ไม่พบคอมเมนต์ = 404", s_ == 404, s_)
    KVStore.objects.filter(pk=CM.STATE_KEY).update(data={})
    s_, d = J(ADM, "/connect/api/comments", {"action": "sync"})
    ck("ดึงตอนนี้ได้", s_ == 200 and d.get("ok"), (s_, d))
    s_, d = J(ADM, "/connect/api/comments", {"action": "sync"})
    ck("กดซ้ำทันที = 429 + บอกให้รอ", s_ == 429 and "รอ" in (d.get("error") or ""), (s_, d))
    s_, inbox = J(ADM, "/connect/api/inbox?view=all")
    ck("ตัวเลขเมนูคอมเมนต์อยู่ใน inbox ของแอดมิน", (inbox.get("counts") or {}).get("comments") == CM.wait_count(), inbox.get("counts"))
    s_, inbox_s = J(SEL, "/connect/api/inbox")
    ck("เซลล์ไม่ได้ตัวเลขคอมเมนต์", "comments" not in (inbox_s.get("counts") or {}), inbox_s.get("counts"))

    print("[7] ลบของเก่า")
    SC.objects.create(platform=SC.FB, ext_id="old1", account_id="111", text="เก่า", created_at=NOW - timedelta(days=120))
    CM._CLEAN["day"] = ""
    n = CM.cleanup_daily()
    ck("ลบคอมเมนต์เก่ากว่า 90 วัน", n == 1 and not SC.objects.filter(ext_id="old1").exists(), n)
    ck("วันเดียวกันไม่ลบซ้ำ", CM.cleanup_daily() is None)

finally:
    _runner.teardown_databases(_old)

print("\nผ่าน %d / %d" % (len(OK), len(OK) + len(BAD)))
if BAD:
    print("ไม่ผ่าน:\n  - " + "\n  - ".join(BAD))
    sys.exit(1)
