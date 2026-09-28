# -*- coding: utf-8 -*-
"""พิสูจน์ว่า `_hide_chrome()` เอา "แถบเมนูซ้ายสีม่วง" ออกจากรูปที่แคปได้จริง (28 ก.ย.69)

    python scripts/test_capture_chrome.py

**วัดสีในรูปจริง ไม่ใช่เช็คว่า JS รันผ่าน** — บั๊กนี้เกิดจากพฤติกรรมของ Playwright เอง
(แคปแบบครอปตามกรอบ element แต่ **ยังเรนเดอร์ของที่ `position:fixed` ลอยทับด้วย**)
ถ้าเทสต์แค่ "เรียกฟังก์ชันแล้วไม่ error" จะผ่านทั้งที่รูปยังมีแถบม่วงอยู่
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

from PIL import Image
from playwright.sync_api import sync_playwright

from dashboard.services.report_shot import _hide_chrome

# ⚠️ `.env` ตั้ง PLAYWRIGHT_BROWSERS_PATH ไว้เป็น path ของ **เซิร์ฟเวอร์** (/opt/oxlet/pw-browsers)
#    พอรันในเครื่อง dev จะหา Chromium ไม่เจอ → ชี้กลับที่เก็บของเครื่องเองเมื่อ path นั้นไม่มีจริง
_bp = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")
if _bp and not os.path.isdir(_bp):
    os.environ.pop("PLAYWRIGHT_BROWSERS_PATH", None)
    print("หมายเหตุ: ไม่มี %s ในเครื่องนี้ → ใช้ Chromium ที่ติดตั้งไว้ตามปกติแทน" % _bp)

PURPLE = (124, 58, 237)          # --ink ม่วงบริษัท (เหมือนแถบเมนูซ้าย)
TMP = os.environ.get("TEMP") or "/tmp"

# หน้าจำลอง: แถบม่วง fixed ทับซ้ายมือ + ป้ายเวอร์ชัน fixed มุมขวาล่าง + การ์ดที่จะแคป
PAGE = """
<!doctype html><meta charset="utf-8">
<style>
  body { margin:0; background:#fff; }
  #nav-slide { position:fixed; left:0; top:0; bottom:0; width:220px;
               background:rgb(124,58,237); z-index:900; }
  .ver       { position:fixed; right:10px; bottom:6px; background:rgb(124,58,237);
               width:60px; height:20px; z-index:9999; }
  #wrap      { padding-left:220px; }
  /* ★ การ์ดต้อง **กว้างกว่า viewport** ถึงจะเกิดบั๊กจริง — Playwright ต้องเลื่อนแนวนอนตอนแคป
     แล้วแถบที่เป็น fixed ตรึงอยู่กับจอ เลยไปทับการ์ด (ของจริง #rpt-shot กว้าง 1700px · จอ 1680px) */
  #card      { width:1700px; height:700px; background:#fff; border:1px solid #ddd; }
  .linesend-btn { background:#16a34a; width:80px; height:24px; }   /* เขียว — กันปนกับสีม่วงที่กำลังวัด */
  #outer     { position:fixed; left:220px; top:0; }   /* บรรพบุรุษของการ์ดที่ลอย — ห้ามซ่อน */
</style>
<div id="nav-slide"></div><div class="ver"></div>
<div id="wrap"><div id="card"><div class="linesend-btn"></div></div></div>
"""

PAGE_FIXED_PARENT = PAGE.replace(
    '<div id="wrap">', '<div id="outer"><div id="wrap">'
).replace("</div>\n", "</div></div>\n", 1)

fail = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        if extra:
            print("        " + str(extra)[:300])
        fail.append(name)


def purple_ratio(path):
    """สัดส่วนพิกเซลที่เป็นสีม่วงบริษัท (เผื่อความคลาดเคลื่อนการบีบอัด ±12)"""
    im = Image.open(path).convert("RGB")
    im = im.resize((im.width // 4 or 1, im.height // 4 or 1))     # ย่อให้นับเร็ว
    px = list(im.getdata())
    hit = sum(1 for r, g, b in px
              if abs(r - PURPLE[0]) < 12 and abs(g - PURPLE[1]) < 12 and abs(b - PURPLE[2]) < 12)
    return hit / float(len(px))


with sync_playwright() as p:
    br = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
    pg = br.new_page(viewport={"width": 1680, "height": 1000})

    # ── 1. ยืนยันว่าบั๊กมีจริง: ไม่ซ่อนอะไร แถบม่วงต้องติดมาในรูป ──
    print("\n[1] ก่อนแก้ — แถบม่วงต้องติดมาในรูป (พิสูจน์ว่าบั๊กมีจริง)")
    pg.set_content(PAGE)
    before = os.path.join(TMP, "_cap_before.png")
    pg.query_selector("#card").screenshot(path=before)
    r_before = purple_ratio(before)
    ck("แคปแบบเดิมมีสีม่วงปนจริง (%.1f%% ของรูป)" % (r_before * 100), r_before > 0.01,
       "ถ้าข้อนี้ไม่ผ่าน = หน้าจำลองไม่ตรงกับของจริง เทสต์ที่เหลือเชื่อไม่ได้")

    # ── 2. หลังเรียก _hide_chrome: ต้องไม่เหลือสีม่วงเลย ──
    print("\n[2] หลังแก้ — ต้องไม่เหลือแถบม่วง")
    pg.set_content(PAGE)
    _hide_chrome(pg, "#card")
    after = os.path.join(TMP, "_cap_after.png")
    pg.query_selector("#card").screenshot(path=after)
    r_after = purple_ratio(after)
    ck("ไม่มีสีม่วงเหลือในรูปเลย (%.3f%%)" % (r_after * 100), r_after < 0.001,
       "ยังเหลือ %.2f%%" % (r_after * 100))
    ck("รูปยังมีขนาดเท่าเดิม (ไม่ได้หายทั้งการ์ด)",
       Image.open(after).size == Image.open(before).size,
       "%s vs %s" % (Image.open(after).size, Image.open(before).size))

    # ── 3. ปุ่ม/ไอคอนตัวช่วยที่อยู่ "ในการ์ด" ต้องถูกซ่อนด้วย (ของเดิมทำอยู่แล้ว ห้ามหาย) ──
    print("\n[3] ปุ่มส่งไลน์ในการ์ดต้องถูกซ่อนเหมือนเดิม")
    hidden = pg.evaluate("getComputedStyle(document.querySelector('.linesend-btn')).display")
    ck("ปุ่ม .linesend-btn ถูกซ่อน", hidden == "none", hidden)

    # ── 4. ★ บรรพบุรุษของเป้าหมายที่เป็น fixed ต้องไม่ถูกซ่อน (ไม่งั้นได้รูปเปล่า) ──
    print("\n[4] ถ้ากรอบครอบการ์ดเป็น fixed ต้องไม่ถูกซ่อน (กันแคปได้รูปเปล่า)")
    pg.set_content(PAGE_FIXED_PARENT)
    _hide_chrome(pg, "#card")
    vis = pg.evaluate("getComputedStyle(document.getElementById('outer')).display")
    ck("บรรพบุรุษที่เป็น fixed ยังไม่ถูกซ่อน", vis != "none", vis)
    el = pg.query_selector("#card")
    ck("ยังแคปการ์ดได้ (element มองเห็นอยู่)", el is not None and el.is_visible())

    # ── 5. ไม่ส่ง keep มา ก็ต้องไม่พัง ──
    print("\n[5] เรียกโดยไม่ระบุเป้าหมาย ต้องไม่ error")
    pg.set_content(PAGE)
    _hide_chrome(pg)
    ck("แถบเมนูถูกซ่อน", pg.evaluate("getComputedStyle(document.getElementById('nav-slide')).display") == "none")
    ck("body ไม่มีคลาส has-sidebar แล้ว", not pg.evaluate("document.body.classList.contains('has-sidebar')"))

    br.close()

for f in (before, after):
    try:
        os.remove(f)
    except Exception:
        pass

print()
print("ไม่ผ่าน %d ข้อ: %s" % (len(fail), " · ".join(fail)) if fail else "ผ่านทั้งหมด")
sys.exit(1 if fail else 0)
