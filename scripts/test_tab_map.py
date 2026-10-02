# -*- coding: utf-8 -*-
"""กันแท็บในหน้าเว็บ กับ `_TAB_ID`/`_CARD_TAB` ของ Playwright หลุดจากกัน

ทำไมต้องมี — บทเรียนจริง (ส.ค.69): ตอนย้ายแท็บเข้าเมนูสามขีด Playwright กดปุ่มไม่โดน
→ แท็บไม่เปลี่ยน → หาการ์ดไม่เจอ → **การ์ดหยุดส่งเข้ากลุ่มเงียบๆ 2-3 วัน ไม่มีใครรู้**
ตอนนี้สลับแท็บด้วย `switchTab(<id>)` ตรง ซึ่งแปลว่า **เลข id ใน `_TAB_ID` ต้องตรงกับ
`NAV_TABS` ใน index.html เป๊ะ** — ไฟล์คนละไฟล์ คนละภาษา ไม่มีอะไรบังคับให้ตรงกันเอง

รัน: python scripts/test_tab_map.py
"""
from __future__ import annotations

import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
os.environ.setdefault("DB_HOST", "")

import django  # noqa: E402

django.setup()

from dashboard.services.report_shot import _CARD_TAB, _TAB_ID  # noqa: E402

IDX = os.path.join(ROOT, "dashboard", "templates", "dashboard", "index.html")

ok, bad = 0, []


def check(cond, msg):
    global ok
    if cond:
        ok += 1
    else:
        bad.append(msg)


src = io.open(IDX, encoding="utf-8").read()

# ── อ่าน NAV_TABS ออกจาก index.html ตรงๆ (ไม่พิมพ์รายชื่อซ้ำไว้ในเทสต์ เดี๋ยวมันก็ตกยุค) ──
m = re.search(r"const NAV_TABS = \[(.*?)\];", src, re.S)
check(bool(m), "หา NAV_TABS ใน index.html ไม่เจอ")
nav = re.findall(r"\{id:'([^']+)'", m.group(1)) if m else []
check(len(nav) >= 10, "NAV_TABS น้อยผิดปกติ (%d แท็บ)" % len(nav))

# ── 1) ทุกแท็บที่ Playwright รู้จัก ต้องมีอยู่จริงในหน้าเว็บ ──
for label, tid in _TAB_ID.items():
    check(tid in nav, "_TAB_ID['%s'] ชี้ไป id '%s' ซึ่งไม่มีใน NAV_TABS" % (label, tid))

# ── 2) ทุกการ์ดที่ตั้งเวลาส่งได้ ต้องรู้ว่าอยู่แท็บไหน และแท็บนั้นต้องแปลงเป็น id ได้ ──
for card, label in _CARD_TAB.items():
    check(label in _TAB_ID,
          "การ์ด %s อยู่แท็บ '%s' แต่ไม่มีใน _TAB_ID → Playwright สลับแท็บไม่ได้ = หยุดส่งเงียบ"
          % (card, label))

# ── 3) แท็บโซเชียลที่แยกเป็นคนละหน้า ต้องผูกกับฝั่งครบ (2 ต.ค.69) ──
m2 = re.search(r"const SO_TAB_SIDE = \{(.*?)\};", src)
check(bool(m2), "หา SO_TAB_SIDE ไม่เจอ")
if m2:
    pairs = dict(re.findall(r"(\w+):\s*'(\w+)'", m2.group(1)))
    check(set(pairs) == {"so", "tt", "yt"}, "SO_TAB_SIDE ควรมี so/tt/yt — เจอ %s" % sorted(pairs))
    check(set(pairs.values()) == {"meta", "tiktok", "youtube"},
          "SO_TAB_SIDE ชี้ฝั่งไม่ครบ — เจอ %s" % sorted(pairs.values()))
    for tid in pairs:
        check(tid in nav, "แท็บโซเชียล '%s' ไม่มีใน NAV_TABS" % tid)
    #  ★ ต้องมีคำอธิบายใต้หัวแท็บทุกอัน — แท็บใหม่ที่ลืมใส่จะขึ้นหัวโล่งๆ
    for tid in list(pairs) + ["ct"]:
        check(("'%s':" % tid) in src, "แท็บ '%s' ยังไม่มีคำอธิบายใน TAB_DESC" % tid)

# ── 4) การ์ดรายงานทีมคอนเทนต์ย้ายไปแท็บของตัวเองแล้ว (ไม่เกาะหน้าใดหน้าหนึ่งของ 3 แพลตฟอร์ม) ──
check(_CARD_TAB.get("content-card") == "คอนเทนต์",
      "content-card ควรอยู่แท็บ 'คอนเทนต์' — เจอ '%s'" % _CARD_TAB.get("content-card"))
check(_TAB_ID.get("คอนเทนต์") == "ct", "แท็บ 'คอนเทนต์' ควรเป็น id 'ct'")
#  คีย์เก่า "โซเชียล" ต้องยังแปลงได้ เผื่อ config ที่บันทึกชื่อนี้ไว้ก่อนแยกหน้า
check(_TAB_ID.get("โซเชียล") in nav, "คีย์เก่า 'โซเชียล' ต้องยังชี้แท็บที่มีจริง")

out = "ผ่านทั้งหมด (%d/%d)" % (ok, ok) if not bad else \
      "ไม่ผ่าน %d ข้อ (ผ่าน %d):\n  - %s" % (len(bad), ok, "\n  - ".join(bad))
try:
    print(out)
except UnicodeEncodeError:
    print(out.encode("ascii", "replace").decode())
sys.exit(1 if bad else 0)
