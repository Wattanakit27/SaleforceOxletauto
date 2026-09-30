# -*- coding: utf-8 -*-
"""ตรวจรายงานทีมคอนเทนต์ (30 ก.ย.69)

    python scripts/test_content_report.py

สร้างข้อมูลจำลองใน SQLite แล้วเรียกฟังก์ชันจริง — ไม่ปลอมฟังก์ชันของเราเอง
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
os.environ.setdefault("DB_HOST", "")
os.environ.setdefault("DEBUG", "True")

import django

django.setup()

from django.test.utils import setup_test_environment
from django.test.runner import DiscoverRunner

setup_test_environment()
runner = DiscoverRunner(verbosity=0, interactive=False)
old_cfg = runner.setup_databases()

from datetime import date, timedelta

from django.utils import timezone

from dashboard.models import KVStore, TikTokAccount, TikTokVideoSnapshot
from dashboard.services import content_report as CR

OK = [0, 0]


def ck(name, cond, got=""):
    OK[0] += 1
    if cond:
        OK[1] += 1
        print("  ok   %s" % name)
    else:
        print("  FAIL %s   ได้: %r" % (name, got))


TODAY = date.today()
D1, D2 = TODAY - timedelta(days=1), TODAY      # 2 คืน = คิดยอดรายวันได้
OLD = TODAY - timedelta(days=60)               # คลิปเก่า
NEW = TODAY - timedelta(days=2)                # คลิปลงใหม่ (ในช่วง 7 วัน)


def snap(vid, owner, posted, day, views, title="", likes=0, comments=0, shares=0):
    TikTokVideoSnapshot.objects.create(
        snap_date=day, taken_at=timezone.now(), trigger="cron",
        open_id=owner, video_id=vid, title=title or vid,
        create_time=timezone.make_aware(
            timezone.datetime.combine(posted, timezone.datetime.min.time())),
        view_count=views, like_count=likes, comment_count=comments, share_count=shares)


print("[1] ตั้งข้อมูลจำลอง — 2 ช่อง · คลิปใหม่/เก่า")
TikTokAccount.objects.create(open_id="o1", label="ช่องพี่แซน", status="active")
TikTokAccount.objects.create(open_id="o2", label="ช่องขายบอส", status="active")

#  คลิปใหม่ (ลง 2 วันก่อน) — วิวโตจาก 100 → 1,100 = ได้ 1,000 ในช่วง
snap("new1", "o1", NEW, D1, 100, "คลิปใหม่ วิวเยอะ")
snap("new1", "o1", NEW, D2, 1100, "คลิปใหม่ วิวเยอะ")
snap("new2", "o2", NEW, D1, 50, "คลิปใหม่ วิวน้อย")
snap("new2", "o2", NEW, D2, 150, "คลิปใหม่ วิวน้อย")
#  คลิปเก่า — ตัวหนึ่งยังทำวิวได้ อีกตัวเงียบ
snap("old_hi", "o1", OLD, D1, 9000, "คลิปเก่า ยังปัง")
snap("old_hi", "o1", OLD, D2, 9500, "คลิปเก่า ยังปัง")
snap("old_lo", "o2", OLD, D1, 8000, "คลิปเก่า เงียบ")
snap("old_lo", "o2", OLD, D2, 8005, "คลิปเก่า เงียบ")
#  ★ คลิปเก่าที่มี snapshot คืนเดียว = คิดยอดรายวันไม่ได้ → ต้องไม่โผล่ใน "วิวน้อยสุด"
snap("old_nodata", "o2", OLD, D2, 7777, "คลิปเก่า ไม่มีข้อมูลรายวัน")

KVStore.objects.update_or_create(key="main", defaults={"data": {"leadChannelByMonth": {
    str(D2.month): {str(D2.day): {
        "Tiktok ช่องแซน": 76,
        "LIVE Tiktok / ช่องขายบอส": 40,
        "TIKTOK ช่องขายบอส": 12,
        "เพจบ้านเก่า": 206,
        "LINE@": 57,
    }}}}})

r = CR.weekly(D1, D2)

print("\n[2] ยอดรวมในช่วง")
tk = r["totals"]["tiktok"]
ck("วิวรวม = ผลต่างของทุกคลิป (1000+100+500+5)", tk["views"] == 1605, tk)
ck("นับจำนวนคลิปทั้งหมด", tk["clips"] == 5, tk)
ck("นับคลิปที่ลงใหม่ในช่วงได้", tk["newClips"] == 2, tk)
ck("★ บอกด้วยว่าคิดยอดรายวันได้กี่คลิป (ไม่ใช่เหมาว่าได้หมด)",
   tk["liveClips"] == 4, tk)

print("\n[3] คลิปลงใหม่ — เรียงวิวมากสุด")
new = r["newClips"]
ck("มี 2 คลิป", len(new) == 2, len(new))
ck("อันดับ 1 = คลิปใหม่ วิวเยอะ (1,000)",
   new and new[0]["text"] == "คลิปใหม่ วิวเยอะ" and new[0]["views"] == 1000, new[:1])
ck("★ ไม่มีคลิปเก่าปนเข้ามา",
   all("เก่า" not in c["text"] for c in new), [c["text"] for c in new])
ck("บอกชื่อช่องด้วย", new[0]["owner"] == "ช่องพี่แซน", new[0].get("owner"))

print("\n[4] คลิปเก่า — ที่ยังปัง / ที่เงียบ")
ck("เก่าที่ทำวิวมากสุด = old_hi (500)",
   r["oldTop"] and r["oldTop"][0]["text"] == "คลิปเก่า ยังปัง", r["oldTop"][:1])
low_texts = [c["text"] for c in r["oldLow"]]
ck("เก่าที่วิวน้อยสุด = old_lo (5)", low_texts and low_texts[0] == "คลิปเก่า เงียบ", low_texts)
ck("★★ คลิปที่ยังคิดยอดรายวันไม่ได้ ต้องไม่โผล่ใน 'วิวน้อยสุด' (ไม่งั้นได้กอง 0 ที่ตอบผิดคำถาม)",
   "คลิปเก่า ไม่มีข้อมูลรายวัน" not in low_texts, low_texts)
ck("บอกจำนวนคลิปเก่าทั้งหมด + ที่คิดรายวันได้",
   (r["oldCount"], r["oldLive"]) == (3, 2), (r["oldCount"], r["oldLive"]))

print("\n[5] รายช่อง + ลีด")
by = {c["name"]: c for c in r["channels"]}
ck("มีครบ 2 ช่อง", set(by) == {"ช่องพี่แซน", "ช่องขายบอส"}, list(by))
ck("★ ลีดของช่องแซน = 76 (ชีตเขียน 'Tiktok ช่องแซน' ระบบชื่อ 'ช่องพี่แซน')",
   by["ช่องพี่แซน"]["leads"] == 76, by["ช่องพี่แซน"]["leads"])
ck("★ ลีดช่องขายบอส รวมทั้ง LIVE และปกติ (40+12)",
   by["ช่องขายบอส"]["leads"] == 52, by["ช่องขายบอส"]["leads"])
ck("วิวรายช่องถูก (แซน 1000+500)", by["ช่องพี่แซน"]["views"] == 1500, by["ช่องพี่แซน"]["views"])
ck("เรียงช่องตามวิวมากสุด", r["channels"][0]["name"] == "ช่องพี่แซน", r["channels"][0]["name"])

print("\n[6] ลีดรวม")
g = r["leads"]["group"]
ck("แยกกลุ่ม TikTok ได้ (76+40+12)", g["tiktok"] == 128, g)
ck("แยกกลุ่มเพจได้", g["page"] == 206, g)
ck("★ LINE@ ไม่ถูกนับเป็นโซเชียล", r["leads"]["social"] == 334, r["leads"]["social"])

print("\n[7] สิ่งที่ทำไม่ได้ ต้องบอกตรงๆ ไม่ใช่ใส่ช่อง 0")
ck("★ ไม่มีช่อง 'บันทึก' ในผลลัพธ์",
   not any("save" in str(k).lower() for k in (r["grand"] or {})), r["grand"])
ck("บอกไว้ว่ายอดบันทึกดึงไม่ได้",
   any("บันทึก" in m for m in r["missing"]), r["missing"])

print("\n[8] ช่วงวันที่ไม่มีข้อมูลเลย = ต้องไม่พัง")
empty = CR.weekly(TODAY - timedelta(days=400), TODAY - timedelta(days=395))
ck("คืนโครงครบ ไม่ throw",
   empty["newClips"] == [] and empty["channels"] == [] and "totals" in empty,
   {k: empty[k] for k in ("newClips", "channels")})

print("\n%s (%d/%d)" % ("ผ่านทั้งหมด" if OK[0] == OK[1] else "มีข้อที่ไม่ผ่าน", OK[1], OK[0]))
runner.teardown_databases(old_cfg)
sys.exit(0 if OK[0] == OK[1] else 1)
