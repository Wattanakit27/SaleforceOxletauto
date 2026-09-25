# -*- coding: utf-8 -*-
"""ตรวจ `social_stats.channel_posts()` — หน้า "ดูรายช่อง" (26 ก.ย.69)

    python scripts/test_social_channel.py

สร้างข้อมูลจำลองลง SQLite ของเครื่อง dev แล้วเรียกฟังก์ชันจริง (ไม่ปลอมฟังก์ชันของเราเอง
ตามบทเรียนเดิม) · ตรวจว่า:
  - แยกตามช่องจริง ไม่ปนช่องอื่น
  - "ยอดที่เพิ่มในช่วง" = ผลต่างของ snapshot (ไม่ใช่ยอดสะสม) · ยอดลดลงไม่นับ
  - เรียงตามยอดที่เพิ่มขึ้น · แบ่งหน้าด้วย offset/limit ได้
  - คลิปที่มี snapshot คืนเดียว → live=False (ยังคิดรายวันไม่ได้) แต่ยอดสะสมยังมา
  - YouTube ได้รูปปก + ลิงก์ฟรีจาก video id
"""
import io
import os
import sys
from datetime import date, datetime, timedelta, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
os.environ.setdefault("DB_HOST", "")
os.environ.setdefault("DEBUG", "True")

import django

django.setup()

from django.test.utils import setup_test_environment, teardown_test_environment
from django.test.runner import DiscoverRunner

setup_test_environment()
runner = DiscoverRunner(verbosity=0, interactive=False)
old_cfg = runner.setup_databases()

from dashboard.models import TikTokVideoSnapshot, YouTubeVideoSnapshot
from dashboard.services import social_stats as S

fail = []


def eq(got, want, what):
    if got == want:
        print("  ok   %s" % what)
    else:
        fail.append(what)
        print("  FAIL %s → ได้ %r ควรได้ %r" % (what, got, want))


T = date(2026, 9, 25)
Y = T - timedelta(days=1)


def tt(vid, own, d, views, likes=0, trig="cron"):
    TikTokVideoSnapshot.objects.create(
        taken_at=datetime(d.year, d.month, d.day, 1, 0, tzinfo=timezone.utc),
        snap_date=d, trigger=trig, open_id=own, video_id=vid,
        title="คลิป %s" % vid, share_url="https://tiktok.com/%s" % vid,
        create_time=datetime(2026, 9, 1, tzinfo=timezone.utc),
        view_count=views, like_count=likes, comment_count=0, share_count=0)


# ช่อง A: 3 คลิป · ช่อง B: 1 คลิป (ต้องไม่ปนกัน)
tt("a1", "chA", Y, 1000); tt("a1", "chA", T, 1500, 20)          # +500
tt("a2", "chA", Y, 100);  tt("a2", "chA", T, 9100)               # +9000  ← ควรมาก่อน
tt("a3", "chA", T, 777)                                           # คืนเดียว = live False
tt("b1", "chB", Y, 50);   tt("b1", "chB", T, 5050)               # คนละช่อง

print("channel_posts — TikTok ช่อง chA")
r = S.channel_posts("tiktok", "chA", T, T)
ids = [x["id"] for x in r["rows"]]
eq(r["total"], 3, "ช่อง chA มี 3 คลิป (ไม่ปนของ chB)")
eq(ids[:2], ["a2", "a1"], "เรียงตามวิวที่เพิ่มขึ้น (a2 +9000 มาก่อน a1 +500)")
eq(r["rows"][0]["inc"]["views"], 9000, "a2 เพิ่ม 9,000 วิว")
eq(r["rows"][0]["views"], 9100, "a2 ยอดสะสม 9,100")
eq(r["rows"][1]["inc"]["likes"], 20, "a1 ไลก์เพิ่ม 20")
a3 = [x for x in r["rows"] if x["id"] == "a3"][0]
eq(a3["live"], False, "a3 มี snapshot คืนเดียว = ยังคิดรายวันไม่ได้")
eq(a3["views"], 777, "แต่ยอดสะสมของ a3 ยังส่งมา")
eq(r["rows"][0]["link"], "https://tiktok.com/a2", "ลิงก์คลิปจาก share_url")
eq(r["rows"][0]["thumb"], "", "TikTok ยังไม่มีรูปปก (API ให้ลิงก์หมดอายุ)")
eq(sorted(r["daily"]), ["a1", "a2", "a3"], "ส่งยอดรายวันมาเฉพาะแถวในหน้านี้")

print("\nยอดลดลง (โพสต์ถูกลบ/ตัวเลขถูกแก้) ต้องไม่นับเป็นติดลบ")
tt("c1", "chC", Y, 900); tt("c1", "chC", T, 400)
rc = S.channel_posts("tiktok", "chC", T, T)
eq(rc["rows"][0]["inc"]["views"], 0, "ยอดลดลง → นับ 0 ไม่ใช่ -500")

print("\nแบ่งหน้า")
p1 = S.channel_posts("tiktok", "chA", T, T, limit=2, offset=0)
p2 = S.channel_posts("tiktok", "chA", T, T, limit=2, offset=2)
eq(len(p1["rows"]), 2, "หน้าแรก 2 แถว")
eq(len(p2["rows"]), 1, "หน้าสอง 1 แถว")
eq(p1["total"], 3, "total บอกจำนวนเต็มเสมอ")
eq(len(set(x["id"] for x in p1["rows"]) & set(x["id"] for x in p2["rows"])), 0, "2 หน้าไม่ซ้ำกัน")

print("\nYouTube — รูปปก/ลิงก์สร้างจาก video id ได้ฟรี")
for d, v in ((Y, 10), (T, 60)):
    YouTubeVideoSnapshot.objects.create(
        taken_at=datetime(d.year, d.month, d.day, 1, 0, tzinfo=timezone.utc),
        snap_date=d, trigger="cron", channel_id="UCx", video_id="vid9",
        title="คลิปยูทูบ", published_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        duration=100, is_short=False, view_count=v, like_count=0, comment_count=0)
ry = S.channel_posts("youtube", "UCx", T, T)
eq(ry["rows"][0]["thumb"], "https://i.ytimg.com/vi/vid9/mqdefault.jpg", "รูปปก YouTube")
eq(ry["rows"][0]["link"], "https://www.youtube.com/watch?v=vid9", "ลิงก์ YouTube")
eq(ry["rows"][0]["inc"]["views"], 50, "วิวเพิ่ม 50")
eq(ry["rows"][0]["inc"]["shares"], 0, "YouTube ไม่มียอดแชร์ = 0 ไม่พัง")

print("\nกันพลาด")
eq(S.channel_posts("tiktok", "", T, T)["rows"], [], "ไม่ส่ง owner = ไม่คืนอะไร")
eq(S.channel_posts("ไม่มีฝั่งนี้", "chA", T, T)["total"], 0, "ฝั่งที่ไม่รู้จัก = ไม่พัง")
eq(S.channel_posts("tiktok", "chไม่มีจริง", T, T)["total"], 0, "ช่องที่ไม่มีข้อมูล = 0 แถว")

runner.teardown_databases(old_cfg)
teardown_test_environment()
print("\n%s" % ("ผ่านทั้งหมด" if not fail else "ไม่ผ่าน %d ข้อ: %s" % (len(fail), fail)))
sys.exit(1 if fail else 0)
