# -*- coding: utf-8 -*-
"""Connect — ห้องแชทลูกค้ารวม: แอดมินเห็นทุกแชท · เซลล์รับลูกค้าเอง (3 ต.ค.69 · เจ้าของสั่ง)

*"เราจะไม่ให้เซลตอบลูกค้าในไลน์แล้ว เราจะให้มาตอบในระบบเรา ซึ่งจะมีแอดมินคอยจับไลน์ให้
  และเซลก็สามารถรับไลน์ได้ … ทีม B และทีม A จะตอบลูกค้าในไลน์ได้วันเว้นวัน ถ้าเซลคนไหน
  เทคแอคชั่นลูกค้าคนนั้นไปก่อน ก็จะเป็นลูกค้าของคนคนนั้น แต่ถ้าเซลคนไหนไม่ตอบลูกค้าภายใน
  ห้านาที ระบบจะขึ้นแจ้งเตือนให้แอดมินประสานงานต่อ"*

กติกาที่ต้องรักษา (ตัดสินแทนเจ้าของตามที่เสนอไว้ — แก้ได้ในหน้าตั้งค่าของ Connect):
  1. **เวรทีมวันเว้นวัน** — คำนวณจาก "วันตั้งต้น + ทีมของวันนั้น" (`anchor_*`) ไม่ต้องกรอกทุกวัน
     · สลับเวรเฉพาะบางวันได้ (`overrides`) · ตัดวันตอนเที่ยงคืนโซนไทย
  2. **ใครกด "รับลูกค้า" ก่อน = ลูกค้าของคนนั้น** — ล็อกที่ฐานข้อมูล (UPDATE … WHERE owner IS NULL)
     2 คนกดพร้อมกันได้คนเดียว · รับได้เฉพาะวันเวรทีมตัวเอง (แอดมินรับ/โอนได้ทุกวัน)
  3. **ลูกค้าเป็นของเซลล์คนเดิมตลอด** ไม่ว่าวันนั้นเวรทีมไหน — ยกเว้นแอดมินโอน
     หรือเซลล์ถูกปิดใช้งานในทะเบียน (คืนคิวอัตโนมัติ)
  4. **นาฬิกา 5 นาทีหยุดเมื่อ "ตอบ" เท่านั้น** — กดรับเฉยๆ ไม่หยุด (กันกดจองแล้วไม่ตอบ)
     · นับเฉพาะเวลาทำการ: ทักนอกเวลา = เริ่มนับตอนเปิดทำการ (ไม่ปลุกแอดมินตอนตี 2)
  5. **เลยเวลา = ขึ้นแจ้งเตือนในหน้า Connect เสมอ** · ส่ง LINE เข้ากลุ่มแอดมินด้วยถ้าเปิดไว้
     (**ปิดโดยปริยาย** — เจ้าของสั่งไว้ว่าอย่าเพิ่งส่งอะไรออกไป)

⚠️ ห้ามส่ง LINE user id ของลูกค้าออกหน้า Connect — ใช้ `ChatOwner.id` เป็นตัวอ้างอิงแทน
   (เซลล์ไม่จำเป็นต้องรู้ และไม่ควรเอาไปทักลูกค้านอกระบบ)
"""
from __future__ import annotations

import json
import re
import statistics
from contextlib import contextmanager
from datetime import date, timedelta

from django.db import IntegrityError, transaction
from django.db.models import Exists, F, OuterRef, Q
from django.utils import timezone

from .models import (ChatLead, ChatOwner, ChatOwnerLog, Employee, ExtLead, FbChat, FbProfile, GroupChat,
                     LineProfile)

CFG_KEY = "connect_config"

DEFAULTS = {
    # ทีมที่ผลัดกันรับลูกค้าใหม่ — เรียงตามลำดับเวร (เพิ่มทีมที่ 3 ได้ ระบบหมุนเวียนเอง)
    "teams": ["A", "B"],
    # วันตั้งต้นของการนับเวร + ทีมที่เวรวันนั้น → วันถัดไปเป็นทีมถัดไปในลิสต์
    "anchor_date": "2026-10-01",
    "anchor_team": "A",
    # สลับเวรเฉพาะวัน {"2026-10-05": "B"} — วันหยุด/ทีมไปออกงาน
    "overrides": {},
    # ต้องตอบภายในกี่นาที
    "sla_min": 5,
    # เวลาทำการที่นับนาฬิกา (เท่ากัน = นับ 24 ชม.)
    "open": "08:30",
    "close": "20:00",
    # ส่ง LINE เข้ากลุ่มแอดมินเมื่อมีลูกค้ารอเกินเวลา — ปิดโดยปริยาย
    "alert_on": False,
    "alert_group": "",
    # ส่ง LINE หาเซลล์เมื่อมีลูกค้าทักเข้ามา (เจ้าของ หรือทั้งทีมที่เวร) — ปิดโดยปริยาย
    #   ⚠️ push นับโควต้าข้อความรายเดือนของ LINE OA · ทีมละ ~9 คน × ทุกลูกค้าใหม่ = เยอะเร็ว
    "notify_sellers": False,
    # ── Facebook Messenger (4 ต.ค.69 · เจ้าของเลือก "รวมคิวเดียวกับ LINE") ──
    # ดึงแชท FB เข้า Connect ทุกนาที — ปิด = แชท FB ยังซิงก์รอบเที่ยงคืนตามเดิม แต่ไม่ขึ้นคิว
    "fb_on": True,
    # ตอบลูกค้า FB จากหน้า Connect: off = ไม่ได้ · test = เฉพาะแชทที่แอดมินกดเป็น "แชททดสอบ" · on = ทุกแชท
    #   เริ่มที่ test — เจ้าของสั่ง "ทดสอบกับบัญชี FB ของเจ้าของก่อน ไม่ส่งหาลูกค้าจริง"
    "fb_reply": "test",
    "fb_test_rows": [],
    # ★ 9 ต.ค.69 — บัญชีพนักงาน "จริง" ที่ใช้เป็นบัญชีทดสอบ (ชื่อเล่นในทะเบียน · เจ้าของสั่ง)
    #   โผล่ท้ายรายการโอน ป้าย "ทดสอบ" · แอดมินสลับไปใช้หน้าจอแบบเซลล์ของบัญชีนี้ได้ ·
    #   จ่ายเบอร์ให้ = ไม่ส่งใบเข้ากลุ่มจ่ายเบอร์จริง · "ล้างข้อมูลทดสอบ" = คืนลูกค้าที่ถือไว้เข้าคิว (ไม่ลบตัวคน)
    "test_accounts": ["Wattanakit"],
    # ★ ดึงแชท FB สำรองทุกกี่นาที — ตัวหลักคือ webhook (Facebook ส่งมาเอง · fb_webhook.py)
    #   เจ้าของห่วง "ถ้าดึงจาก API ทุกหนึ่งนาที มันจะติด Token" → วัดจริง 4 ต.ค.69 ตอนดึงทุก 1 นาที:
    #   header ของ Meta (x-business-use-case-usage · messenger) = ใช้ไป 1% ทั้ง call/CPU/เวลา → ห่างจากเพดานมาก
    #   ★ ค่าตั้งต้น 2 นาที (ไม่ใช่ 10) — ก่อนผ่าน App Review webhook ส่งแชทลูกค้าจริงมาไม่ได้ ทางสำรองคือทางเดียว
    #     ดึงช้า = แชทถึง Connect ช้าแล้วขึ้น "เลยเวลา" ทันที (เส้นตายนับจากเวลาที่ลูกค้าส่ง) · ผ่านรีวิวแล้วค่อยปรับเป็น 30–60
    "fb_poll_min": 2,
    # ── ปุ่ม "จ่ายเบอร์" (6 ต.ค.69 · เจ้าของสั่ง "กลุ่มจ่ายเบอร์อยากให้มันต่อจริงๆ ส่งจริงๆ") ──
    # True = ส่งใบจ่ายลีดเข้ากลุ่มจ่ายเบอร์จริง + แท็กเซลล์ (slippost.py) · False = โหมดทดลองเดิม (เก็บในระบบอย่างเดียว)
    "slip_post": True,
    # กลุ่มปลายทาง — ว่าง = หาเองจากชื่อกลุ่ม (เลขปกติ → "ห้องจ่ายเบอร์ บ้านเก่า" · เลข R… → "ห้องจ่ายเบอร์ REJECT")
    "slip_group": "",
    "slip_group_reject": "",
    # ── ★ 11 ต.ค.69 หน้ารวมแชท (crm.py) ──
    # เจ้าของรับลูกค้าแล้วไม่ตอบจนเลยเส้นตาย + เกินกี่นาทีหลังรับ → ระบบดึงคืนคิว (0 = ปิด · ปิดโดยปริยาย)
    #   ⚠️ ทีมยังตอบในแอป LINE OA Manager อยู่ (LINE ไม่ส่งกลับมา) — เปิดตอนนี้ = ดึงลูกค้าที่ตอบไปแล้วคืนผิดๆ
    "pull_min": 0,
    # เตือนนัดลูกค้า (นัดติดตาม/นัดดูรถ) ทาง LINE แชทส่วนตัวเซลล์ 30 นาทีก่อนถึงเวลา — ปิดโดยปริยาย
    "appt_line": False,
    # แชทเข้าห้องพัก Lead ยังไง — True = แชทที่ให้เบอร์/ID LINE เข้าห้องเอง · False = เฉพาะแชทที่แอดมินติ๊ก
    #   "รับ lead จากแชทนี้แล้ว" · ใบร่างจากกลุ่ม ADMIN เก็บ Lead เข้าห้องเองทั้ง 2 แบบ
    #   ★ 18 ต.ค.69 กลับมาเข้าเอง (เจ้าของ "ต่อไปนี้ไม่มีแล้วการให้แอดมินมากดรับหลีดไปพัก เราส่งไปเองเลยดีกว่า")
    #   · ตัวจับ "จ่ายแล้วหรือยัง" ด้วย ID LINE (leadmatch) เคลียร์แชทที่แอดมินจ่ายไปแล้วออกจากห้องเอง
    #   · หน้ากฎไม่มีสวิตช์นี้แล้ว · ค่าบนเซิร์ฟเวอร์ถูกเปลี่ยนเป็นเปิดด้วย migration 0041
    #   (11 ต.ค.69 เคยปิดไว้: "ข้อมูลยังไม่ครบ ยังไม่พร้อมทำออโต้ 100")
    "room_chat_auto": True,
}
FB_REPLY_MODES = ("off", "test", "on")

_OVERRIDE_KEEP_DAYS = 31      # สลับเวรที่ผ่านมาเกินนี้ทิ้งตอนบันทึก (กันโตไม่หยุด)


# ─────────────────────────────────────────────────────────────
#  ตั้งค่า
# ─────────────────────────────────────────────────────────────
def _is_team_code(s) -> bool:
    s = str(s or "").strip()
    return 1 <= len(s) <= 2 and all("a" <= ch.lower() <= "z" or ch.isdigit() for ch in s)


def _hm(s, fallback=(0, 0)):
    try:
        h, m = str(s).strip().split(":")
        h, m = int(h), int(m)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h, m
    except Exception:
        pass
    return fallback


def _iso_date(s):
    try:
        return date.fromisoformat(str(s).strip()[:10])
    except Exception:
        return None


def cfg() -> dict:
    """ค่าตั้งปัจจุบัน (ค่าที่บันทึกไว้ทับค่าตั้งต้น) — อ่านไม่ได้ = ค่าตั้งต้นทั้งหมด"""
    raw = {}
    try:
        from dashboard.services import cache_store
        raw = (cache_store.get_kv(CFG_KEY) or {}).get("data") or {}
    except Exception:
        raw = {}
    c = dict(DEFAULTS)
    c.update({k: v for k, v in (raw or {}).items() if k in DEFAULTS})
    teams = [str(t).strip().upper() for t in (c.get("teams") or []) if _is_team_code(t)]
    c["teams"] = teams or list(DEFAULTS["teams"])
    if str(c.get("anchor_team") or "").upper() not in c["teams"]:
        c["anchor_team"] = c["teams"][0]
    c["anchor_team"] = str(c["anchor_team"]).upper()
    if not _iso_date(c.get("anchor_date")):
        c["anchor_date"] = DEFAULTS["anchor_date"]
    c["overrides"] = {k: str(v).upper() for k, v in (c.get("overrides") or {}).items()
                      if _iso_date(k) and str(v).upper() in c["teams"]}
    try:
        c["sla_min"] = max(1, min(120, int(c.get("sla_min") or 5)))
    except Exception:
        c["sla_min"] = DEFAULTS["sla_min"]
    c["fb_on"] = bool(c.get("fb_on"))
    if c.get("fb_reply") not in FB_REPLY_MODES:
        c["fb_reply"] = DEFAULTS["fb_reply"]
    rows = []
    for x in (c.get("fb_test_rows") or []):
        try:
            rows.append(int(x))
        except Exception:
            pass
    c["fb_test_rows"] = list(dict.fromkeys(rows))[:20]
    try:
        c["fb_poll_min"] = max(2, min(60, int(c.get("fb_poll_min") or DEFAULTS["fb_poll_min"])))
    except Exception:
        c["fb_poll_min"] = DEFAULTS["fb_poll_min"]
    c["slip_post"] = bool(c.get("slip_post"))
    c["room_chat_auto"] = bool(c.get("room_chat_auto"))
    c["test_accounts"] = list(dict.fromkeys(
        str(x).strip() for x in (c.get("test_accounts") or []) if str(x).strip()))[:10]
    for k in ("slip_group", "slip_group_reject"):
        c[k] = str(c.get(k) or "").strip()
    return c


def clean_cfg(body: dict) -> tuple[dict, list]:
    """ตรวจค่าที่ส่งมาจากหน้าตั้งค่า → (ค่าที่จะบันทึก, รายการปัญหา)

    **ปฏิเสธพร้อมบอกว่าช่องไหน ไม่เงียบ** — ค่าผิดแล้วบันทึกผ่าน = เวรทั้งเดือนเพี้ยน
    โดยที่คนตั้งเห็นว่า "บันทึกสำเร็จ"
    """
    cur = cfg()
    out, errs = dict(cur), []
    body = body or {}

    if "teams" in body:
        teams = [str(t).strip().upper() for t in (body.get("teams") or [])]
        bad = [t for t in teams if not _is_team_code(t)]
        if bad or not teams:
            errs.append("ทีมที่ผลัดเวรต้องเป็นรหัสทีมสั้นๆ เช่น A, B (ได้: %s)" % (", ".join(bad) or "ว่าง"))
        else:
            out["teams"] = list(dict.fromkeys(teams))
    if "anchor_date" in body:
        d = _iso_date(body.get("anchor_date"))
        if not d:
            errs.append("วันตั้งต้นของเวรไม่ใช่วันที่")
        else:
            out["anchor_date"] = d.isoformat()
    if "anchor_team" in body:
        t = str(body.get("anchor_team") or "").strip().upper()
        if t not in out["teams"]:
            errs.append("ทีมของวันตั้งต้น (%s) ไม่อยู่ในทีมที่ผลัดเวร" % (t or "ว่าง"))
        else:
            out["anchor_team"] = t
    if "overrides" in body:
        ov, keep_from = {}, timezone.localdate() - timedelta(days=_OVERRIDE_KEEP_DAYS)
        for k, v in (body.get("overrides") or {}).items():
            d, t = _iso_date(k), str(v or "").strip().upper()
            if not d:
                errs.append("วันที่สลับเวรไม่ถูกต้อง: %s" % k)
            elif t not in out["teams"]:
                errs.append("สลับเวรวันที่ %s เป็นทีม %s ซึ่งไม่อยู่ในทีมที่ผลัดเวร" % (k, t or "ว่าง"))
            elif d >= keep_from:
                ov[d.isoformat()] = t
        out["overrides"] = ov
    if "sla_min" in body:
        try:
            n = int(body.get("sla_min"))
            if not 1 <= n <= 120:
                raise ValueError
            out["sla_min"] = n
        except Exception:
            errs.append("เวลาที่ต้องตอบต้องเป็นตัวเลข 1–120 นาที")
    for key, label in (("open", "เวลาเปิด"), ("close", "เวลาปิด")):
        if key in body:
            s = str(body.get(key) or "").strip()
            if _hm(s, None) is None:
                errs.append("%s ต้องเป็นรูปแบบ ชม:นาที เช่น 08:30" % label)
            else:
                out[key] = "%02d:%02d" % _hm(s)
    if "alert_on" in body:
        out["alert_on"] = bool(body.get("alert_on"))
    if "alert_group" in body:
        g = str(body.get("alert_group") or "").strip()
        if g and g[:1] not in ("C", "R"):
            errs.append("กลุ่มแจ้งเตือนต้องเป็น group id ของ LINE (ขึ้นต้นด้วย C)")
        else:
            out["alert_group"] = g
    if "notify_sellers" in body:
        out["notify_sellers"] = bool(body.get("notify_sellers"))
    if "fb_on" in body:
        out["fb_on"] = bool(body.get("fb_on"))
    if "fb_reply" in body:
        m = str(body.get("fb_reply") or "").strip()
        if m not in FB_REPLY_MODES:
            errs.append("การตอบแชท Facebook ต้องเป็น ปิด / ทดสอบ / เปิด")
        else:
            out["fb_reply"] = m
    if "fb_poll_min" in body:
        try:
            n = int(body.get("fb_poll_min"))
            if not 2 <= n <= 60:
                raise ValueError
            out["fb_poll_min"] = n
        except Exception:
            errs.append("ดึงแชท Facebook สำรองต้องเป็นตัวเลข 2–60 นาที")
    if "slip_post" in body:
        out["slip_post"] = bool(body.get("slip_post"))
    if "pull_min" in body:
        try:
            n = int(body.get("pull_min") or 0)
            if n and not 5 <= n <= 240:
                raise ValueError
            out["pull_min"] = n
        except Exception:
            errs.append("ดึงลูกค้าคืนเมื่อไม่ตอบ ต้องเป็น 0 (ปิด) หรือ 5–240 นาที")
    if "appt_line" in body:
        out["appt_line"] = bool(body.get("appt_line"))
    if "room_chat_auto" in body:
        out["room_chat_auto"] = bool(body.get("room_chat_auto"))
    for key, label in (("slip_group", "กลุ่มจ่ายเบอร์ (เลขปกติ)"), ("slip_group_reject", "กลุ่มจ่ายเบอร์ (เลข R…)")):
        if key in body:
            g = str(body.get(key) or "").strip()
            if g and g[:1] != "C":
                errs.append("%s ต้องเป็น group id ของ LINE (ขึ้นต้นด้วย C) หรือเว้นว่างให้ระบบหาเอง" % label)
            else:
                out[key] = g
    if out.get("alert_on") and not out.get("alert_group"):
        errs.append("เปิดแจ้งเตือนเข้ากลุ่ม LINE แล้ว แต่ยังไม่ได้เลือกกลุ่ม")
    return out, errs


def save_cfg(c: dict) -> bool:
    _ROOM_AUTO["at"] = 0.0
    try:
        from dashboard.services import cache_store
        cache_store.set_kv(CFG_KEY, {k: c[k] for k in DEFAULTS if k in c})
        return True
    except Exception:
        return False


_ROOM_AUTO = {"at": 0.0, "val": True}


def room_auto() -> bool:
    """แชทที่ให้เบอร์/ID LINE เข้าห้องพัก Lead เอง (`room_chat_auto`) — จำ 20 วิ
    (รายชื่อเรียกต่อแถว ห้ามอ่าน KV ทุกแถว) · อ่านไม่ได้ = ค่าตั้งต้น (เข้าเอง)"""
    import time as _t
    if _t.monotonic() - _ROOM_AUTO["at"] > 20:
        try:
            _ROOM_AUTO["val"] = bool(cfg().get("room_chat_auto"))
        except Exception:
            _ROOM_AUTO["val"] = bool(DEFAULTS["room_chat_auto"])
        _ROOM_AUTO["at"] = _t.monotonic()
    return _ROOM_AUTO["val"]


# ─────────────────────────────────────────────────────────────
#  เวรทีม + เส้นตาย
# ─────────────────────────────────────────────────────────────
def duty_team(d: date, c: dict | None = None) -> str:
    """ทีมที่เวรรับลูกค้าใหม่ในวันนั้น"""
    c = c or cfg()
    ov = (c.get("overrides") or {}).get(d.isoformat())
    if ov:
        return ov
    teams = c["teams"]
    anchor = _iso_date(c.get("anchor_date")) or _iso_date(DEFAULTS["anchor_date"])
    try:
        base = teams.index(c.get("anchor_team"))
    except ValueError:
        base = 0
    return teams[(base + (d - anchor).days) % len(teams)]


def today_team(c: dict | None = None) -> str:
    return duty_team(timezone.localdate(), c)


_TH_DOW = ["จันทร์", "อังคาร", "พุธ", "พฤหัส", "ศุกร์", "เสาร์", "อาทิตย์"]


def off_duty_reason(team: str, c: dict | None = None) -> str:
    """ทำไมวันนี้คนทีมนี้รับลูกค้าใหม่ไม่ได้ ('' = วันนี้เวรทีมนี้ รับได้)

    ★ แยก 3 กรณี — เดิมตอบแบบเดียวว่า "รอวันเวรของทีม" ซึ่ง **ผิดสำหรับทีมที่ไม่อยู่ในเวรเลย**
      (ทีม C / เทเลเซลล์) → เขาจะรอวันที่ไม่มีวันมาถึง (วัดจริง 3 ต.ค.69: ทีม C มี 3 คนในทะเบียน)
    """
    c = c or cfg()
    d0 = timezone.localdate()
    if not team:
        return ("บัญชีนี้ยังไม่ได้ตั้งทีมในทะเบียนพนักงาน (หน้า \"พนักงาน\" → ตำแหน่ง เช่น ทีม A) — "
                "รับลูกค้าใหม่เองไม่ได้ แต่แอดมินโอนลูกค้าให้ได้")
    if team not in c["teams"]:
        return ("ทีม %s ไม่ได้อยู่ในเวรรับลูกค้าใหม่ (เวรมีทีม %s) — แอดมินโอนลูกค้าให้ได้"
                % (team, ", ".join(c["teams"])))
    today = duty_team(d0, c)
    if today == team:
        return ""
    for i in range(1, 31):                      # วันเวรถัดไปของทีมนี้ (นับสลับเวรด้วย)
        d = d0 + timedelta(days=i)
        if duty_team(d, c) == team:
            when = "พรุ่งนี้" if i == 1 else "%s %d/%d" % (_TH_DOW[d.weekday()], d.day, d.month)
            return "วันนี้เป็นเวรทีม %s — ทีม %s รับลูกค้าใหม่ได้อีกทีวันเวรถัดไป (%s)" % (today, team, when)
    return "วันนี้เป็นเวรทีม %s — ทีม %s ไม่มีวันเวรใน 30 วันข้างหน้า (เช็คตารางเวรในหน้าตั้งค่า)" % (today, team)


def roster(days: int = 14, c: dict | None = None) -> list:
    c = c or cfg()
    d0 = timezone.localdate()
    ov = c.get("overrides") or {}
    return [{"date": (d0 + timedelta(days=i)).isoformat(),
             "team": duty_team(d0 + timedelta(days=i), c),
             "override": (d0 + timedelta(days=i)).isoformat() in ov}
            for i in range(days)]


def due_for(t, c: dict | None = None, ignore_hours: bool = False):
    """เส้นตายที่ต้องตอบ ถ้าลูกค้าทักมาตอน `t`

    นับเฉพาะเวลาทำการ: ทักก่อนเปิด = เริ่มนับตอนเปิด · ทักหลังปิด = เริ่มนับตอนเปิดวันรุ่งขึ้น
    ทักใกล้ปิด (19:58) เส้นตายเลยเวลาปิดไปได้ — ไม่ตัดทิ้ง (ลูกค้ารอจริง)
    `ignore_hours` = นับทันทีทุกเวลา (ลูกค้าจำลอง — ให้ทดสอบตอนกลางคืนแล้วเห็นนาฬิกาเดินได้)
    """
    c = c or cfg()
    sla = timedelta(minutes=int(c["sla_min"]))
    lt = timezone.localtime(t)
    oh, om = _hm(c.get("open"), (8, 30))
    ch, cm = _hm(c.get("close"), (20, 0))
    if ignore_hours or (oh, om) == (ch, cm):          # ตั้งเวลาเปิด=ปิด = นับ 24 ชม.
        return t + sla
    open_t = lt.replace(hour=oh, minute=om, second=0, microsecond=0)
    close_t = lt.replace(hour=ch, minute=cm, second=0, microsecond=0)
    if lt < open_t:
        start = open_t
    elif lt >= close_t:
        start = open_t + timedelta(days=1)
    else:
        start = lt
    return start + sla


# ─────────────────────────────────────────────────────────────
#  คน
# ─────────────────────────────────────────────────────────────
def employee_of(user: dict | None):
    """แถวพนักงานของคนที่ login อยู่ (session `oxlet_user`) — ไม่เจอ = None

    เทียบ **ชื่อเล่น** ก่อน (session ได้มาจากชีตพนักงานชุดเดียวกับที่นำเข้าทะเบียน)
    ไม่เจอค่อยเทียบ LINE id ที่ผูกไว้ในทะเบียน
    """
    if not user:
        return None
    nick = (user.get("nickname") or user.get("seller_name") or "").strip()
    uid = (user.get("user_id") or "").strip()
    names = [nick] if nick else []
    if nick:
        try:
            from dashboard.services.constants import normalize_seller
            n2 = normalize_seller(nick)
            if n2 and n2 != nick:
                names.append(n2)
        except Exception:
            pass
    for n in names:
        e = Employee.objects.filter(nickname=n, active=True).first()
        if e:
            return e
    if uid.startswith("U"):
        p = (LineProfile.objects.filter(user_id=uid, employee__isnull=False)
             .select_related("employee").first())
        if p and p.employee.active:
            return p.employee
    return None


def team_of(emp) -> str:
    """ทีมขายของพนักงาน — จากตำแหน่งในทะเบียน (ที่เดียวกับแดชบอร์ดขาย) ไม่เจอค่อยดูตั้งค่าเซลล์"""
    if not emp:
        return ""
    try:
        from dashboard.services.constants import TEAM_ID, normalize_seller, team_id_of
        return team_id_of(emp.position) or TEAM_ID.get(normalize_seller(emp.nickname), "")
    except Exception:
        return ""


def seller_list() -> list:
    """พนักงานที่อยู่ทีมขาย — ตัวเลือกตอนแอดมินโอนลูกค้า

    ★ 9 ต.ค.69 บัญชีทดสอบ (บัญชีจำลอง "ทดสอบเซลล์ X" + บัญชีจริงใน `test_accounts`) อยู่ท้ายรายการ
      ติด `test: True` · ไม่มีทีม = ทีม "ทดสอบ" (ไม่ใช่รหัสทีม → ไม่มีวันอยู่ในเวรรับลูกค้าจริง)
    """
    names = set(cfg()["test_accounts"])
    out = []
    for e in Employee.objects.filter(active=True).order_by("nickname"):
        t = team_of(e)
        test = e.nickname.startswith(TEST_PREFIX) or e.nickname in names
        if t or test:
            out.append({"id": e.id, "name": e.nickname, "team": t or "ทดสอบ", "test": test})
    out.sort(key=lambda r: (r["test"], r["team"], r["name"]))
    return out


def team_members(team: str) -> list:
    return [e for e in Employee.objects.filter(active=True) if team_of(e) == team]


# ─────────────────────────────────────────────────────────────
#  เหตุการณ์จากแชท
# ─────────────────────────────────────────────────────────────
def preview_of(g) -> str:
    """ข้อความ 1 บรรทัดของแถว GroupChat — ชนิดที่ไม่ใช่ตัวอักษรบอกเป็นคำ"""
    if (g.text or "").strip():
        return g.text
    if g.msg_type == GroupChat.STICKER:
        return "[สติกเกอร์]"
    if g.msg_type == GroupChat.IMAGE:
        return "[รูป]"
    if g.msg_type == GroupChat.VIDEO:
        return "[วิดีโอ]"
    if g.msg_type == GroupChat.LOCATION:
        return "[ตำแหน่ง] %s" % ((g.extra or {}).get("address") or "")
    if g.has_media:
        return "[ไฟล์]"
    return "[%s]" % (g.msg_type or "ข้อความ")


# ─────────────────────────────────────────────────────────────
#  ลูกค้า Facebook Messenger ในคิวเดียวกับ LINE (4 ต.ค.69 · เจ้าของเลือก "รวมคิวเดียวกับ LINE")
#  แถว ChatOwner มี `profile` (LINE) หรือ `fb_profile` (FB) อย่างใดอย่างหนึ่ง — **ใช้ cust(o) เสมอ**
# ─────────────────────────────────────────────────────────────
FB_LIVE_MIN = 30      # ข้อความ FB ที่เพิ่งดึงมาแต่เก่ากว่านี้ ไม่เริ่มนับ 5 นาที (กันวันแรกขึ้น "เลยเวลา" ท่วม)
# ★ ข้อความจากเพจที่ออกภายในกี่วินาทีหลังลูกค้าทัก = "ตอบอัตโนมัติ" ของเพจ ไม่ใช่คนตอบ → ไม่หยุดนาฬิกา 5 นาที
#   (4 ต.ค.69 เจอในแชททดสอบของเจ้าของ: ข้อความต้อนรับ/ฟอร์มขอเบอร์ของ Business Suite ออกวินาทีเดียวกับที่ลูกค้าทัก
#   และ Facebook ติดป้ายมาเหมือนคนตอบทุกอย่าง (inbox/sent/source:web) → ทุกแชท FB ถูกปิดรอบทันที ไม่มีวันเลยเวลา)
#   คนจริงอ่านแล้วพิมพ์ตอบไม่ทันใน 15 วิ · ข้อความที่ส่งจาก Connect (มีชื่อคนตอบ) ไม่ใช้กติกานี้
FB_AUTO_SEC = 15
FB_BACKFILL_DAYS = 7  # ลูกค้า FB ที่คุยภายใน 7 วันก่อนเปิดใช้ → มีแถวใน "ทั้งหมด" (ไม่เริ่มรอบรอ)


def is_fb(o) -> bool:
    return bool(getattr(o, "fb_profile_id", None))


def cust(o):
    """โปรไฟล์ลูกค้าของแถวนี้ — LineProfile หรือ FbProfile (มี show_name/display_name/msg_count/first_seen/user_id เหมือนกัน)"""
    return o.fb_profile if is_fb(o) else o.profile


def is_sim_row(o) -> bool:
    return (not is_fb(o)) and bool(o.profile_id) and is_sim(o.profile.user_id)


def fb_on() -> bool:
    try:
        return bool(cfg().get("fb_on"))
    except Exception:
        return False


def fb_preview(m) -> str:
    """ข้อความ 1 บรรทัดของแถว FbChat — ชนิดที่ไม่ใช่ตัวอักษรบอกเป็นคำ (แบบเดียวกับ preview_of ของ LINE)"""
    if (m.text or "").strip():
        return m.text
    if m.msg_type == "template":               # ★ 19 ต.ค.69 การ์ดโฆษณา (ลูกค้ากดโฆษณาแบบทักแชท)
        from .fb_ads import preview
        return preview(m)
    return {"sticker": "[สติกเกอร์]", "image": "[รูป]", "video": "[วิดีโอ]", "audio": "[เสียง]",
            "file": "[ไฟล์]"}.get(m.msg_type or "", "[ข้อความ]")


def fb_page_name(pid: str) -> str:
    """ชื่อเพจ (KV meta_page_names ที่ meta_sync จดไว้) — ไม่รู้ = id เพจ"""
    try:
        from dashboard.services import cache_store
        names = (cache_store.get_kv("meta_page_names") or {}).get("data") or {}
        return names.get(str(pid)) or str(pid)
    except Exception:
        return str(pid)


def fb_reply_state(o, c=None) -> tuple:
    """ตอบลูกค้า FB คนนี้จาก Connect ได้ไหม → (ได้ไหม, เหตุผลเมื่อไม่ได้)"""
    c = c or cfg()
    mode = c.get("fb_reply")
    if mode == "on":
        return True, ""
    if mode == "test" and o.id in (c.get("fb_test_rows") or []):
        return True, ""
    if mode == "test":
        return False, "ช่วงทดสอบ: ตอบแชท Facebook จาก Connect ได้เฉพาะ \"แชททดสอบ\" ที่แอดมินกำหนด — ตอบลูกค้าใน Facebook (Business Suite) ไปก่อน"
    return False, "ปิดการตอบแชท Facebook จาก Connect อยู่ — ตอบลูกค้าใน Facebook (Business Suite)"


# ─────────────────────────────────────────────────────────────
#  โปรไฟล์ลูกค้า — รูป LINE + ข้อมูลจาก LINE + เบอร์ที่พิมพ์มา + รถที่หา
#  (3 ต.ค.69 เจ้าของสั่ง "เอา Profile ลูกค้าเข้ามาด้วย")
# ─────────────────────────────────────────────────────────────
PIC_REFRESH_DAYS = 7          # ลิงก์รูปตายเมื่อลูกค้าเปลี่ยนรูป → ดึงใหม่ทุกสัปดาห์
PIC_RETRY_HOURS = 24          # ดึงไม่ได้ (บล็อกบอท/เน็ตสะดุด) → ลองใหม่พรุ่งนี้ ไม่ใช่ทุกครั้งที่เปิดหน้า
BG_FILL = True                # เทสต์ปิดไว้ (ไม่ให้มี thread วิ่งชนฐานข้อมูลทดสอบ)
_FILL = {"at": 0.0}


def _picture_stale(o) -> bool:
    return (not o.picture_at) or (timezone.now() - o.picture_at) > timedelta(days=PIC_REFRESH_DAYS)


def refresh_profile(o) -> bool:
    """ดึงโปรไฟล์จาก LINE ใหม่ — รูป (เก็บที่ ChatOwner) + ชื่อ/สเตตัส/ภาษา (อัปเดต LineProfile)

    ใช้บัญชี OA ที่ลูกค้าคุยอยู่ (`chat._channel_for`) — โปรไฟล์ดึงได้เฉพาะบัญชีที่เขาเพิ่มเป็นเพื่อน
    """
    from . import people
    prof = o.profile
    try:
        from .chat import _channel_for
        chan = _channel_for(prof)
    except Exception:
        chan = prof.channel or ""
    data = people.fetch_profile(prof.user_id, channel=chan) or {}
    now = timezone.now()
    if data.get("displayName"):
        o.picture_url, o.picture_at = (data.get("pictureUrl") or "")[:500], now
        ChatOwner.objects.filter(pk=o.pk).update(picture_url=o.picture_url, picture_at=now)
        LineProfile.objects.filter(pk=prof.pk).update(
            display_name=(data.get("displayName") or "")[:120],
            status_message=data.get("statusMessage") or "",
            language=(data.get("language") or "")[:16],
            fetched_at=now)
        return True
    o.picture_at = now - timedelta(days=PIC_REFRESH_DAYS) + timedelta(hours=PIC_RETRY_HOURS)
    ChatOwner.objects.filter(pk=o.pk).update(picture_at=o.picture_at)
    return False


def fill_pictures(limit: int = 20) -> int:
    """เติมรูป/โปรไฟล์ให้ลูกค้าที่ยังไม่มี/เก่าแล้ว ทีละชุด — ลูกค้าที่กำลังรอก่อน แล้วค่อยคนที่คุยล่าสุด

    ลูกค้าเก่าที่ทักมาก่อนมีฟีเจอร์นี้ (~380 คนตอนเปิด) ไม่มีรูปเลย · ทยอยเติมเองตอนมีคนเปิดหน้า Connect
    **จองแถวก่อนดึง** (UPDATE … WHERE picture_at = ค่าเดิม) — gunicorn หลาย worker จะไม่ดึงคนเดียวกันซ้ำ
    """
    now = timezone.now()
    stale = now - timedelta(days=PIC_REFRESH_DAYS)
    rows = list(ChatOwner.objects.filter(Q(picture_at__isnull=True) | Q(picture_at__lt=stale))
                .filter(profile__isnull=False)                 # ลูกค้า FB ไม่มีรูปจาก LINE ให้ดึง
                .exclude(profile__user_id__startswith=SIM_PREFIX)
                .order_by(F("awaiting_since").asc(nulls_last=True), F("last_at").desc(nulls_last=True))
                .values_list("id", "picture_at")[:limit])
    done = 0
    hold = now - timedelta(days=PIC_REFRESH_DAYS) + timedelta(minutes=10)   # ตายกลางทาง = ว่างให้คนอื่นใน 10 นาที
    for oid, pat in rows:
        q = ChatOwner.objects.filter(pk=oid)
        q = q.filter(picture_at__isnull=True) if pat is None else q.filter(picture_at=pat)
        if not q.update(picture_at=hold):
            continue                                   # worker อื่นจองไปแล้ว
        o = ChatOwner.objects.select_related("profile").filter(pk=oid).first()
        if o and refresh_profile(o):
            done += 1
    return done


def fill_pictures_bg(limit: int = 20, every: int = 60) -> bool:
    """เรียก `fill_pictures` ใน thread แยก (ห้ามหน่วงหน้าเว็บ — ยิง LINE ทีละคน) · มากสุดนาทีละครั้งต่อ worker"""
    import threading
    import time
    if not BG_FILL or time.time() - _FILL["at"] < every:
        return False
    _FILL["at"] = time.time()

    def _work():
        try:
            fill_pictures(limit)
        except Exception:
            pass
        finally:
            try:
                from django.db import connection
                connection.close()            # thread แยกมี connection ของตัวเอง ต้องปิดเอง
            except Exception:
                pass

    threading.Thread(target=_work, daemon=True).start()
    return True


_PHONE_RE = re.compile(r"(?<!\d)(?:\+?66[\s.-]?|0)(?:\d[\s.-]?){8}\d?(?!\d)")


def phones_in(texts) -> list:
    """เบอร์โทรที่ลูกค้าพิมพ์มาในแชท (มือถือ/บ้าน · รองรับขีด/เว้นวรรค/+66) — ไม่เกิน 5 เบอร์"""
    out = []
    for t in texts or []:
        for m in _PHONE_RE.finditer(t or ""):
            d = re.sub(r"\D", "", m.group(0))
            if d.startswith("66"):
                d = "0" + d[2:]
            ok = (len(d) == 10 and d[:2] in ("06", "08", "09")) or (len(d) == 9 and d[1] in "234567")
            if ok and d not in out:
                out.append(d)
    return out[:5]


def _money(n) -> str:
    return "{:,}".format(int(n)) if n else ""


def profile_json(o, access: str = "full", texts=None) -> dict:
    """การ์ดโปรไฟล์ลูกค้าในหน้าแชท — คิวรอรับ (`preview`) ได้แค่รูป+ชื่อ ข้อมูลที่เหลือต้องกดรับก่อน"""
    p = cust(o)
    out = {"pic": o.picture_url or "", "name": p.show_name, "lineName": p.display_name or "",
           "firstSeen": _iso(p.first_seen), "lastSeen": _iso(p.last_seen), "msgs": p.msg_count or 0,
           "claimedAt": _iso(o.claimed_at), "full": access == "full", "src": "fb" if is_fb(o) else "line"}
    if is_fb(o):
        out["page"] = fb_page_name(p.channel)
    if access != "full":
        return out
    if is_fb(o):
        out["inbox"] = p.inbox_link or ""               # เปิดห้องนี้ใน Facebook (Business Suite)
    needs = []
    try:
        for n in p.needs.order_by("-updated_at")[:3]:
            bits = []
            if n.car_year_min or n.car_year_max:
                bits.append("ปี %s" % "–".join(str(x) for x in (n.car_year_min, n.car_year_max) if x))
            if n.budget_max:
                bits.append("งบไม่เกิน %s" % _money(n.budget_max))
            if n.monthly_max:
                bits.append("ผ่อนไหว %s/เดือน" % _money(n.monthly_max))
            if n.down_max:
                bits.append("ดาวน์ %s" % _money(n.down_max))
            needs.append({"car": n.car_model or (n.car_text or "")[:60] or "(ไม่ระบุรุ่น)",
                          "detail": " · ".join(bits), "status": n.get_status_display(),
                          "waiting": bool(n.waiting), "at": _iso(n.updated_at)})
    except Exception:
        needs = []
    out.update({"status": getattr(p, "status_message", "") or "", "language": getattr(p, "language", "") or "",
                "phones": phones_in(texts), "needs": needs})
    return out


def _row_for(prof):
    o = ChatOwner.objects.filter(profile=prof).select_related("owner").first()
    if o:
        return o
    try:
        return ChatOwner.objects.create(profile=prof)
    except IntegrityError:          # webhook 2 ตัวมาพร้อมกัน — อีกตัวสร้างไปแล้ว
        return ChatOwner.objects.select_related("owner").get(profile=prof)


def _log(o, action, emp=None, by="", **kw):
    try:
        ChatOwnerLog.objects.create(
            chat=o, action=action, employee=emp,
            emp_name=(emp.nickname if emp else kw.pop("emp_name", "")),
            by_name=(by or "")[:80], team=kw.pop("team", "") or (o.team or ""),
            wait_sec=kw.pop("wait_sec", None), on_time=kw.pop("on_time", None),
            note=(kw.pop("note", "") or "")[:200])
    except Exception:
        pass                       # ประวัติเขียนไม่ได้ ต้องไม่ทำให้งานหลัก (รับ/ตอบลูกค้า) พัง


# บัญชี LINE ที่ "ไม่ใช่ช่องลูกค้า" — พนักงานทักบัญชีนี้ = ลงทะเบียนรับแจ้งเตือน ไม่ใช่ลีด (ไม่ขึ้น Connect)
STAFF_SKIP_CHANNELS = ("push",)


def note_customer_message(user_id: str, at=None, preview: str = "", picture: str = "", channel: str = ""):
    """ลูกค้าส่งข้อความเข้ามา — เรียกจาก `store_chat` (แชท 1:1 เท่านั้น)

    เริ่ม "รอบรอคำตอบ" ถ้ายังไม่มี · ลูกค้าส่งรัวๆ หลายข้อความ = รอบเดิม (เส้นตายไม่เลื่อน)
    `picture` = ลิงก์รูปโปรไฟล์ที่ `touch_profile` เพิ่งดึงมา (ว่าง = ไม่ได้ดึงรอบนี้)
    `channel` = บัญชี LINE ที่ได้ยินข้อความนี้ (crm = OA ลูกค้า · push = บอทแจ้งเตือน)

    ★ 4 ต.ค.69 — **พนักงานที่ทักบัญชีลูกค้า ขึ้น Connect ด้วย** (ติดป้าย "พนักงาน")
      เดิมตัดพนักงานทิ้งหมด → เจ้าของทักทดสอบจาก LINE ส่วนตัวแล้วไม่เห็นแชทตัวเอง ·
      และเอ็มส่งชื่อ+เบอร์ลูกค้าที่ถามหา Civic เข้า OA ก็หายไปเงียบๆ (วัดจริง 30 วัน: 4 คน 38 ข้อความ ไม่รก)
      ยกเว้นทักบอทแจ้งเตือน (`STAFF_SKIP_CHANNELS`) — นั่นคือแอดบอทเพื่อรับแจ้งเตือน ไม่ใช่ลีด
    """
    if not user_id:
        return None
    prof = LineProfile.objects.filter(user_id=user_id).first()
    if not prof or (prof.is_employee and (channel or "") in STAFF_SKIP_CHANNELS):
        return None
    at = at or timezone.now()
    c = cfg()
    o = _row_for(prof)
    sim = is_sim(user_id)
    new_round = _customer_in(o, at, preview, c, start_round=True, sim=sim)
    try:                                       # ลูกค้าให้เบอร์/ไอดี = เข้าห้องพัก Lead ทันที
        capture_contact(o, extra=[{"dir": "in", "text": preview or ""}])
    except Exception:
        pass
    try:                                       # อาชีพ/รายได้/สถานะ ฯลฯ จาก keyword — ลงฟอร์มลีดทันที ไม่ต้องรอเปิดแชท
        capture_profile(o, extra=[{"dir": "in", "text": preview or ""}])
    except Exception:
        pass
    try:                                       # ★ 19 ต.ค.69 เก็บลีดอัตโนมัติ — ส่งใบลงกลุ่มทันที ไม่รอรอบ cron (thread แยก)
        from .autolead import kick_chat
        kick_chat(o, preview or "")
    except Exception:
        pass
    if picture:
        o.picture_url, o.picture_at = picture[:500], timezone.now()
        ChatOwner.objects.filter(pk=o.pk).update(picture_url=o.picture_url, picture_at=o.picture_at)
    # รูปโปรไฟล์เก่าเกิน 7 วัน/ยังไม่มี → ดึงใหม่ตอนเริ่มรอบ (ทำใน thread ของ webhook อยู่แล้ว ไม่หน่วงใคร)
    if new_round and not picture and not sim and _picture_stale(o):
        try:
            refresh_profile(o)
        except Exception:
            pass
    if new_round and not sim and c.get("notify_sellers"):
        try:
            _notify_new(o, c)
        except Exception:
            pass
    return o


def _customer_in(o, at, preview: str, c: dict, start_round: bool = True, sim: bool = False) -> bool:
    """ลูกค้าส่งข้อความ (LINE หรือ FB) — ส่วนกลางของทั้ง 2 ช่องทาง → คืนว่า "เริ่มรอบรอใหม่" ไหม

    `start_round=False` = ข้อความเก่าที่เพิ่งดึงมา (FB ย้อนหลัง) — อัปเดตข้อความล่าสุดแต่ไม่เริ่มนับ 5 นาที
    """
    # เจ้าของถูกปิดใช้งานในทะเบียน (ลาออก) → คืนคิว ไม่งั้นลูกค้าค้างอยู่กับคนที่ไม่มีวันตอบ
    if o.owner_id and not o.owner.active:
        _log(o, ChatOwnerLog.RELEASE, emp=o.owner, by="ระบบ",
             note="เซลล์ไม่ได้ทำงานแล้ว — คืนคิวอัตโนมัติ")
        o.owner, o.claimed_at, o.first_reply_at = None, None, None
        _crm_hook("on_release", o)
    new_round = start_round and o.awaiting_since is None
    if new_round:
        o.awaiting_since = at
        o.due_at = due_for(at, c, ignore_hours=sim)
        o.escalated_at = None
        if not o.owner_id:
            o.team = duty_team(timezone.localtime(o.due_at).date(), c)
    if not o.last_in_at or at >= o.last_in_at:
        o.last_in_at = at
    if not o.last_at or at >= o.last_at:
        o.last_at, o.last_preview, o.last_dir = at, (preview or "")[:200], "in"
    o.save()
    return new_round


def _fb_auto(at, last_in) -> bool:
    """ข้อความขาออกของเพจ (ไม่ได้ส่งจาก Connect) ที่ออกตามหลังข้อความลูกค้าไม่เกิน FB_AUTO_SEC วินาที = ตอบอัตโนมัติ"""
    return bool(at and last_in) and 0 <= (at - last_in).total_seconds() < FB_AUTO_SEC


def _reply_done(o, at, preview: str = "", emp=None, by: str = "", close: bool = True):
    """เราตอบลูกค้าแล้ว (LINE หรือ FB) — จบรอบรอ + จดเวลาที่ลูกค้ารอ (เฉพาะคำตอบที่ปิดรอบ)

    `close=False` = ข้อความตอบอัตโนมัติของเพจ — อัปเดตข้อความล่าสุด แต่ไม่ปิดรอบ ไม่นับเป็นการตอบ
    """
    if close and o.awaiting_since and at >= o.awaiting_since:
        _log(o, ChatOwnerLog.REPLY, emp=emp, by=by or (emp.nickname if emp else ""),
             team=team_of(emp) or o.team,
             wait_sec=max(0, int((at - o.awaiting_since).total_seconds())),
             on_time=(at <= o.due_at) if o.due_at else None)
        o.awaiting_since = o.due_at = o.escalated_at = None
    elif o.awaiting_since:
        pass                                  # คำตอบที่เก่ากว่ารอบนี้ (ดึงมาช้า) — ไม่ได้ตอบข้อความรอบนี้
    if close and (not o.read_at or at > o.read_at):
        o.read_at = at                        # คนที่ตอบได้อ่านแชทแล้ว (ตอบอัตโนมัติของเพจไม่นับ)
    if close and o.pk:                        # ★ 10 ต.ค.69 ตอบลูกค้าแล้ว = ติดต่อแล้ว → นาฬิกาโทรของงานแชทนี้หยุด
        try:
            from .leadflow import note_chat_reply
            note_chat_reply(o, at)
        except Exception:
            pass
    if emp and o.owner_id == emp.id and not o.first_reply_at:
        o.first_reply_at = at
    if not o.last_out_at or at >= o.last_out_at:
        o.last_out_at = at
    if not o.last_at or at >= o.last_at:
        o.last_at, o.last_preview, o.last_dir = at, (preview or "")[:200], "out"
    o.save()
    return o


def _row_for_fb(fp):
    o = ChatOwner.objects.filter(fb_profile=fp).select_related("owner").first()
    if o:
        return o
    try:
        return ChatOwner.objects.create(fb_profile=fp)
    except IntegrityError:
        return ChatOwner.objects.select_related("owner").get(fb_profile=fp)


def note_fb_batch(fp, msgs):
    """ข้อความ Messenger ที่เพิ่งดึงมา (ซิงก์ทุกนาที/เที่ยงคืน) → เริ่ม/ปิดรอบรอคำตอบใน Connect

    ★ เพจตอบลูกค้าใน Facebook (Business Suite/แอป) ก็ปิดรอบให้ — Facebook ส่งข้อความขาออกมาด้วย
      (ต่างจาก LINE OA Manager ที่ไม่ส่งมา) → นาฬิกา 5 นาทีหยุดถูกต้องไม่ว่าตอบจากที่ไหน
    ★ ข้อความเก่ากว่า FB_LIVE_MIN นาทีไม่เริ่มรอบรอ — ไม่งั้นวันแรกที่เปิด ลูกค้าเมื่อวานขึ้น "เลยเวลา" ท่วม
    """
    if not fb_on() or fp is None or fp.is_employee:
        return None
    # วินาทีเดียวกัน: ข้อความลูกค้าก่อน แล้วค่อยขาออก (ตอบอัตโนมัติออกวินาทีเดียวกับที่ลูกค้าทักได้)
    rows = sorted([m for m in (msgs or []) if m.sent_at],
                  key=lambda m: (m.sent_at, 1 if m.direction == FbChat.OUT else 0))
    if not rows:
        return None
    c, now = cfg(), timezone.now()
    o = _row_for_fb(fp)
    new_round = False
    for m in rows:
        if m.direction == FbChat.OUT:
            auto = not m.sent_by_id and _fb_auto(m.sent_at, o.last_in_at)
            _reply_done(o, m.sent_at, fb_preview(m), emp=m.sent_by,
                        by=m.sent_by_name or "ตอบใน Facebook", close=not auto)
        else:
            live = (now - m.sent_at) <= timedelta(minutes=FB_LIVE_MIN)
            new_round = _customer_in(o, m.sent_at, fb_preview(m), c, start_round=live) or new_round
    try:                                       # ลูกค้าให้เบอร์/ไอดี = เข้าห้องพัก Lead ทันที
        capture_contact(o)
    except Exception:
        pass
    try:                                       # อาชีพ/รายได้/สถานะ ฯลฯ จาก keyword
        capture_profile(o)
    except Exception:
        pass
    live_in = [fb_preview(m) for m in rows
               if m.direction != FbChat.OUT and (now - m.sent_at) <= timedelta(minutes=FB_LIVE_MIN)]
    if live_in:                                # ★ 19 ต.ค.69 เก็บลีดอัตโนมัติ — ส่งใบทันทีหลังดึงข้อความรอบนี้ (ข้อความเก่า/รอบเที่ยงคืนไม่นับ)
        try:
            from .autolead import kick_chat
            kick_chat(o, "\n".join(live_in))
        except Exception:
            pass
    if new_round and c.get("notify_sellers"):
        try:
            _notify_new(o, c)
        except Exception:
            pass
    return o


def mark_read(o) -> bool:
    """มีคนเปิดอ่านแชทนี้แล้ว (แอดมิน/เจ้าของที่เห็นแชทเต็ม) → รายชื่อเลิกโชว์ตัวหนา/จุดแดง

    อ่านถึง `last_in_at` ที่เห็นตอนเปิด (ไม่ใช่เวลาตอนนี้) — ลูกค้าส่งมาใหม่ระหว่างนั้นจะยังเป็น "ยังไม่อ่าน"
    เขียนเฉพาะตอนสถานะเปลี่ยน — หน้าแชทรีเฟรชทุก 6 วิ ไม่ควรเขียนฐานข้อมูลทุกรอบ
    """
    if not o.last_in_at or (o.read_at and o.read_at >= o.last_in_at):
        return False
    from django.db.models import Q
    ChatOwner.objects.filter(pk=o.pk).filter(Q(read_at__isnull=True) | Q(read_at__lt=o.last_in_at)) \
        .update(read_at=o.last_in_at)
    o.read_at = o.last_in_at
    return True


def is_unread(o) -> bool:
    return bool(o.last_in_at and (not o.read_at or o.read_at < o.last_in_at))


def note_reply(user_id: str, emp=None, at=None, preview: str = "", by: str = ""):
    """เราตอบลูกค้าสำเร็จ — เรียกจาก `chat.send_reply` (ทั้งจากหน้า Connect และพาเนลแชทเดิม)

    ตอบแล้ว = จบรอบรอ · จดเวลาที่ลูกค้ารอไว้เป็นสถิติ (เฉพาะคำตอบที่ปิดรอบ)
    """
    prof = LineProfile.objects.filter(user_id=user_id).first()
    # พนักงานที่ขึ้น Connect (ทักบัญชีลูกค้า) ก็ปิดรอบได้ — คนที่ไม่มีแถว (คุยกับบอทแจ้งเตือน) ไม่ต้องสร้างแถวใหม่
    if not prof or (prof.is_employee and not ChatOwner.objects.filter(profile=prof).exists()):
        return None
    return _reply_done(_row_for(prof), at or timezone.now(), preview, emp=emp, by=by)


# ─────────────────────────────────────────────────────────────
#  งานของคน: รับ · โอน · ปล่อย · ไม่ต้องตอบ
# ─────────────────────────────────────────────────────────────
def claim(row_id, emp, admin: bool = False):
    """เซลล์กด "รับลูกค้า" → (ok, ข้อความ)  · ใครกดก่อนได้ไป ล็อกที่ฐานข้อมูล"""
    if not emp:
        return False, "บัญชีนี้ยังไม่ได้ผูกกับทะเบียนพนักงาน — แจ้งแอดมินให้เพิ่มชื่อเล่นในหน้า \"พนักงาน\""
    o = ChatOwner.objects.select_related("owner", "profile", "fb_profile").filter(pk=row_id).first()
    if not o:
        return False, "ไม่พบลูกค้ารายนี้ (อาจถูกลบไปแล้ว)"
    if o.owner_id == emp.id:
        return True, "เป็นลูกค้าของคุณอยู่แล้ว"
    if o.owner_id:
        return False, "%s รับลูกค้าคนนี้ไปแล้ว" % o.owner.nickname
    my = team_of(emp)
    if not admin:
        why = off_duty_reason(my)
        if why:
            return False, why
        if not o.awaiting_since:
            return False, "ลูกค้าคนนี้ไม่ได้รออยู่ในคิวแล้ว — ถ้าต้องการดูแล ให้แอดมินโอนให้"
    now = timezone.now()
    n = (ChatOwner.objects.filter(pk=o.pk, owner__isnull=True)
         .update(owner=emp, claimed_at=now, first_reply_at=None,
                 team=my or o.team, updated_at=now))
    if not n:
        o.refresh_from_db()
        who = o.owner.nickname if o.owner_id else "มีคน"
        return False, "%s รับลูกค้าคนนี้ไปก่อนแล้ว" % who
    o.refresh_from_db()
    _log(o, ChatOwnerLog.CLAIM, emp=emp, by=emp.nickname, team=my)
    _crm_hook("on_owner", o)
    return True, "รับลูกค้าแล้ว — อย่าลืมตอบก่อนเส้นตาย"


def assign(row_id, emp=None, by: str = "", note: str = ""):
    """แอดมินโอนลูกค้าให้เซลล์ (`emp`) หรือปล่อยคืนคิว (`emp=None`) → (ok, ข้อความ)"""
    o = ChatOwner.objects.select_related("owner", "profile", "fb_profile").filter(pk=row_id).first()
    if not o:
        return False, "ไม่พบลูกค้ารายนี้"
    now = timezone.now()
    old = o.owner if o.owner_id else None
    if emp is None:
        if not old:
            return True, "ลูกค้าอยู่ในคิวอยู่แล้ว"
        o.owner, o.claimed_at, o.first_reply_at = None, None, None
        o.team = today_team()
        o.save()
        _log(o, ChatOwnerLog.RELEASE, emp=old, by=by, note=note or "แอดมินปล่อยคืนคิว")
        _crm_hook("on_release", o)
        return True, "ปล่อยคืนคิวแล้ว — เซลล์ทีมที่เวรวันนี้กดรับได้"
    if not emp.active:
        return False, "%s ถูกปิดใช้งานในทะเบียนพนักงาน" % emp.nickname
    if old and old.id == emp.id:
        return True, "เป็นลูกค้าของ %s อยู่แล้ว" % emp.nickname
    o.owner, o.claimed_at, o.first_reply_at = emp, now, None
    o.team = team_of(emp) or o.team
    o.save()
    _log(o, ChatOwnerLog.ASSIGN, emp=emp, by=by,
         note=note or (("โอนจาก %s" % old.nickname) if old else "โอนจากคิว"))
    _crm_hook("on_owner", o)
    return True, "โอนให้ %s แล้ว" % emp.nickname


def _crm_hook(name, o):
    """แจ้ง crm.py ว่าความเป็นเจ้าของเปลี่ยน (ขั้น "คืนกองกลาง") — พังต้องไม่ทำให้รับ/โอน/ปล่อยพัง"""
    try:
        from . import crm
        getattr(crm, name)(o)
    except Exception:
        pass


def dismiss(row_id, by: str = "", emp=None):
    """ปิดรอบรอโดยไม่ต้องตอบ (ลูกค้าส่ง "ขอบคุณครับ"/สติกเกอร์ · ตอบนอกระบบไปแล้ว)"""
    o = ChatOwner.objects.select_related("owner").filter(pk=row_id).first()
    if not o:
        return False, "ไม่พบลูกค้ารายนี้"
    if not o.awaiting_since:
        return True, "ลูกค้าไม่ได้รอคำตอบอยู่"
    _log(o, ChatOwnerLog.DISMISS, emp=emp, by=by,
         wait_sec=max(0, int((timezone.now() - o.awaiting_since).total_seconds())))
    o.awaiting_since = o.due_at = o.escalated_at = None
    o.save()
    return True, "ปิดรอบนี้แล้ว (ไม่ต้องตอบ)"


# ─────────────────────────────────────────────────────────────
#  cron: เลยเวลา → แจ้งแอดมิน
# ─────────────────────────────────────────────────────────────
def tick(now=None) -> dict:
    """เรียกจาก `cron_tick` ทุกนาที — ติดธง "เลยเวลา" ให้รอบที่เลยเส้นตาย + แจ้ง LINE (ถ้าเปิด)

    หน้า Connect คำนวณ "เลยเวลา" เองจาก `due_at` อยู่แล้ว (ไม่พึ่ง cron) — ตัวนี้มีไว้
    จดประวัติ + ส่งแจ้งเตือนครั้งเดียวต่อรอบ · UPDATE … WHERE escalated_at IS NULL
    กันส่งซ้ำเวลา cron ยิงซ้อนจากหลาย worker
    """
    now = now or timezone.now()
    out = {}
    try:                                     # dropdown ของฟอร์มลีด ตามชีตลีด — ทุกชั่วโมง (แยก try: พังไม่ลากงานเตือน)
        out.update(_dd_tick() or {})
    except Exception as e:
        out["dropdownsError"] = str(e)[:120]
    try:                                     # แชท Facebook Messenger → Connect ทุกนาที (thread แยก · ไม่หน่วง cron)
        r = fb_tick_bg()
        if r:
            out["fb"] = r
    except Exception as e:
        out["fbError"] = str(e)[:120]
    try:                                     # ลีดภายนอก (ห้องพัก Lead) ที่เกิน 90 วัน — มีเบอร์/ID LINE ลูกค้า
        from .leadpark import cleanup
        n = cleanup(now)
        if n:
            out["extLeadDeleted"] = n
    except Exception as e:
        out["extLeadError"] = str(e)[:120]
    try:                                     # ★ 10 ต.ค.69 งานจ่ายเบอร์: นาฬิกาโทร · จ่ายวน · รายงานผล (leadflow.py)
        from .leadflow import tick as _lf_tick
        r = _lf_tick(now)
        if r:
            out["leadflow"] = r
    except Exception as e:
        out["leadflowError"] = str(e)[:120]
    try:                                     # ★ 19 ต.ค.69 เก็บลีดอัตโนมัติ: จองเลขรัน + ส่งใบลงกลุ่ม ADMIN เก็บ Lead (ไม่จ่ายเซลล์ · thread แยก)
        from .autolead import tick_bg as _al_tick
        r = _al_tick(now)
        if r:
            out["autolead"] = r
    except Exception as e:
        out["autoleadError"] = str(e)[:120]
    try:                                     # ห้องพัก Lead: ลีดที่แอดมินจ่ายเบอร์ในกลุ่มแล้ว → จับคู่ใบ/จ่ายให้ใคร เอง (thread แยก)
        r = slip_sweep_bg()
        if r:
            out["slipSweep"] = r
    except Exception as e:
        out["slipSweepError"] = str(e)[:120]
    try:                                     # ★ 11 ต.ค.69 รูป/ไฟล์ที่ลูกค้าส่งในแชท → โหลดมาเก็บก่อนต้นทางลบ (thread แยก)
        from .chatmedia import sweep_bg
        r = sweep_bg()
        if r:
            out["chatMedia"] = r
    except Exception as e:
        out["chatMediaError"] = str(e)[:120]
    try:                                     # ★ 17 ต.ค.69 หน้าคอมเมนต์ — ดึง Facebook/YouTube เป็นรอบ (thread แยก) + ลบเก่าวันละครั้ง
        from .comments import tick_bg as _cm_tick, cleanup_daily as _cm_clean
        r = _cm_tick(now)
        if r:
            out["comments"] = r
        n = _cm_clean()
        if n:
            out["commentsDeleted"] = n
    except Exception as e:
        out["commentsError"] = str(e)[:120]
    try:                                     # ★ 16 ต.ค.69 รูปที่เราส่งหาลูกค้า — ลบสำเนาเมื่อเกินอายุแชทลูกค้า (วันละครั้ง)
        from .chatplus import cleanup_daily
        n = cleanup_daily()
        if n:
            out["chatOutDeleted"] = n
    except Exception as e:
        out["chatOutError"] = str(e)[:120]
    try:                                     # ★ 11 ต.ค.69 หน้ารวมแชท: ดึงคืนเมื่อไม่ตอบ · เตือนนัด · ลบหลักฐานของลูกค้าที่ถูกลบ
        from .crm import tick as _crm_tick
        r = _crm_tick(now)
        if r:
            out["crm"] = r
    except Exception as e:
        out["crmError"] = str(e)[:120]
    c = cfg()
    rows = list(ChatOwner.objects.select_related("owner", "profile", "fb_profile")
                .filter(awaiting_since__isnull=False, escalated_at__isnull=True, due_at__lte=now)
                .order_by("due_at")[:100])
    hit = []
    for o in rows:
        if ChatOwner.objects.filter(pk=o.pk, escalated_at__isnull=True).update(escalated_at=now):
            _log(o, ChatOwnerLog.ESCALATE, emp=o.owner if o.owner_id else None, by="ระบบ",
                 wait_sec=max(0, int((now - o.awaiting_since).total_seconds())),
                 note="" if o.owner_id else "ยังไม่มีเซลล์รับ")
            hit.append(o)
    if not hit:
        return out
    out["escalated"] = len(hit)
    real = [o for o in hit if not is_sim_row(o)]                   # ลูกค้าจำลองไม่ส่ง LINE
    if real and c.get("alert_on") and c.get("alert_group"):
        out["alert"] = _alert_admins(real, c, now)
    return out


def _link(o=None) -> str:
    try:
        from django.conf import settings
        base = (getattr(settings, "SITE_URL", "") or "").rstrip("/")
    except Exception:
        base = ""
    return "%s/connect/%s" % (base, ("?id=%d" % o.id) if o else "")


def _alert_admins(rows, c, now) -> str:
    from dashboard.services.line_channels import token_for
    from dashboard.services.line_notify import push_line_message
    lines = ["⚠️ Connect: ลูกค้ารอเกิน %d นาที (%d คน)" % (c["sla_min"], len(rows))]
    for o in rows[:10]:
        mins = int((now - o.awaiting_since).total_seconds() // 60)
        who = o.owner.nickname if o.owner_id else "ยังไม่มีเซลล์รับ (เวรทีม %s)" % (o.team or "-")
        lines.append("• %s%s — %s · รอ %d นาที" % ("[FB] " if is_fb(o) else "", cust(o).show_name, who, mins))
    if len(rows) > 10:
        lines.append("… และอีก %d คน" % (len(rows) - 10))
    lines.append("เปิดดู: %s" % _link())
    gid = c["alert_group"]
    code, body = push_line_message(gid, [{"type": "text", "text": "\n".join(lines)}],
                                   token_for(gid), what="Connect: ลูกค้ารอเกินเวลา")
    return "ok" if code == 200 else "LINE %s %s" % (code, (body or "")[:120])


def _notify_new(o, c):
    """บอกเซลล์ทาง LINE ว่ามีลูกค้าทักมา — เจ้าของ (ถ้ามี) หรือทุกคนในทีมที่เวร"""
    from dashboard.services.line_channels import dm_token
    from dashboard.services.line_notify import push_line_message
    if o.owner_id:
        people, text = [o.owner], "💬 ลูกค้าของคุณ (%s) ทักมาใน Connect — ตอบภายใน %d นาที\n%s" % (
            cust(o).show_name, c["sla_min"], _link(o))
    else:
        people = team_members(o.team)
        text = "💬 มีลูกค้าใหม่ทักมา (%s) — เวรทีม %s กดรับได้ที่\n%s" % (
            cust(o).show_name, o.team, _link(o))
    tok = dm_token()
    for e in people[:20]:
        uid = (LineProfile.objects.filter(employee=e).order_by("-last_seen")
               .values_list("user_id", flat=True).first())
        if uid:
            push_line_message(uid, [{"type": "text", "text": text}], tok,
                              what="Connect: มีลูกค้าทัก")


# ─────────────────────────────────────────────────────────────
#  สร้างแถวให้ลูกค้าเก่าที่ทักมาก่อนมี Connect
# ─────────────────────────────────────────────────────────────
_SYNC = {"at": 0.0}


def sync_rows(force: bool = False) -> int:
    """ลูกค้าที่มีแชทอยู่แล้วแต่ยังไม่มีแถวใน Connect → สร้างให้ (ไม่มีเจ้าของ · **ไม่เริ่มรอบรอ**)

    ไม่เริ่มรอบรอโดยตั้งใจ — ลูกค้าเก่าหลายร้อยคนจะกลายเป็น "เลยเวลา" พร้อมกันทั้งหมด
    ในวันแรกที่เปิดใช้ · ทำมากสุดทุก 2 นาที (แอดมินเปิดหน้าบ่อย)
    """
    import time
    if not force and time.time() - _SYNC["at"] < 120:
        return 0
    _SYNC["at"] = time.time()
    made = []
    if fb_on():
        # ลูกค้า FB ที่คุยภายใน 7 วันก่อนเปิดใช้ (หรือก่อนเปิดสวิตช์) — มีแถวใน "ทั้งหมด" ไม่เริ่มรอบรอ
        #   ไม่สร้างให้ทั้ง ~6,600 ห้องย้อนหลัง (คุยกันใน Facebook จบไปนานแล้ว)
        cut = timezone.now() - timedelta(days=FB_BACKFILL_DAYS)
        for fp in FbProfile.objects.filter(is_employee=False, owner_row__isnull=True, last_seen__gte=cut)[:1000]:
            m = (FbChat.objects.filter(thread_id=fp.thread_id).order_by("-sent_at", "-id").first()
                 if fp.thread_id else None)
            if not m:
                continue
            made.append(ChatOwner(fb_profile=fp, last_at=m.sent_at, last_preview=fb_preview(m)[:200],
                                  last_dir=m.direction or "in",
                                  last_in_at=m.sent_at if m.direction != FbChat.OUT else None,
                                  read_at=m.sent_at,
                                  last_out_at=m.sent_at if m.direction == FbChat.OUT else None))
    profs = list(LineProfile.objects.filter(is_employee=False, owner_row__isnull=True)[:2000])
    staff_ids = (GroupChat.objects.filter(chat_type=GroupChat.USER, direction=GroupChat.IN,
                                          sent_at__gte=timezone.now() - timedelta(days=7))
                 .exclude(channel__in=STAFF_SKIP_CHANNELS).values_list("sender_id", flat=True).distinct())
    profs += list(LineProfile.objects.filter(is_employee=True, owner_row__isnull=True, user_id__in=list(staff_ids)[:200]))
    for p in profs:
        g = (GroupChat.objects.filter(sender_id=p.user_id).exclude(chat_type=GroupChat.GROUP)
             .order_by("-sent_at", "-id").first())
        if not g:
            continue
        made.append(ChatOwner(profile=p, last_at=g.sent_at, last_preview=preview_of(g)[:200],
                              last_dir=g.direction or "in",
                              last_in_at=g.sent_at if g.direction != GroupChat.OUT else None,
                              read_at=g.sent_at,
                              last_out_at=g.sent_at if g.direction == GroupChat.OUT else None))
    if made:
        ChatOwner.objects.bulk_create(made, ignore_conflicts=True)
    try:
        scan_contacts_bg()                 # thread แยก — เดิมทำในคำขอ ทำให้หน้าแรกหลังรีสตาร์ทช้า 2–3 วิ
    except Exception:
        pass
    return len(made)


# ─────────────────────────────────────────────────────────────
#  ข้อมูลสำหรับหน้าเว็บ
# ─────────────────────────────────────────────────────────────
def _iso(dt):
    return timezone.localtime(dt).isoformat(timespec="seconds") if dt else ""


def _auto_code(o, ld) -> str:
    """เลขที่ระบบเก็บลีดจองไว้ (ป้าย "รอจ่าย" ในรายชื่อ) · แชทของบัญชีทดสอบ = เลขทดสอบ + "ทดสอบ" """
    if o.pk in _test_ids():
        try:
            from .autolead import test_code_of
            c = test_code_of(o.pk)
            return ("%s ทดสอบ" % c) if c else ""
        except Exception:
            return ""
    return ((ld.auto or {}).get("_autolead") or {}).get("code", "") if ld and not ld.code else ""


def row_json(o, me=None, now=None, appt_map=None, matches=None, pend=None) -> dict:
    """`appt_map`/`matches`/`pend` = ส่งมาจาก inbox() (ถามฐานข้อมูลครั้งเดียวทั้งหน้า) · ไม่ส่ง = ถามเองทีละแถว"""
    now = now or timezone.now()
    p = cust(o)
    ld = lead_of(o, create=False)
    out = {
        "id": o.id,
        "name": (ld.customer_name if ld and ld.customer_name else p.show_name),
        "tags": list(ld.tags or [])[:4] if ld else [],
        "preview": o.last_preview or "",
        "lastAt": _iso(o.last_at),
        "lastDir": o.last_dir or "",
        "owner": o.owner.nickname if o.owner_id else "",
        "ownerId": o.owner_id or 0,
        "team": o.team or "",
        "awaiting": bool(o.awaiting_since),
        "since": _iso(o.awaiting_since),
        "due": _iso(o.due_at),
        "overdue": bool(o.awaiting_since and o.due_at and o.due_at <= now),
        "unread": is_unread(o),                      # ตัวหนา + จุดแดงหลังเวลาในรายชื่อ
        "escalated": bool(o.escalated_at),
        "mine": bool(me and o.owner_id == me.id),
        "msgs": p.msg_count or 0,
        "pic": o.picture_url or "",
        "sim": is_sim_row(o),
        "src": "fb" if is_fb(o) else "line",            # ป้ายช่องทางในรายชื่อ (Facebook / LINE)
        "staff": bool(getattr(p, "is_employee", False)),  # พนักงานทักบัญชีลูกค้า (ทดสอบ/ส่งต่อลีด) — ป้าย "พนักงาน"
        "code": (ld.code or "") if ld else "",          # เลขลีด — โชว์เป็นป้ายในรายชื่อ (จ่ายแล้ว/มาจากใบจ่ายลีด)
        # เลขเคสรับซื้อ (OC-…) — ลูกค้าที่อยากขายรถให้เรา ถูกส่งเข้ากลุ่มเคสHOT ของจัดซื้อแล้ว
        "buyCode": ((ld.auto or {}).get(BUY_KEY) or {}).get("code", "") if ld else "",
        # ★ 19 ต.ค.69 เลขที่ระบบเก็บลีดอัตโนมัติจองไว้ (ใบอยู่กลุ่ม ADMIN เก็บ Lead · ยังไม่จ่ายเซลล์)
        "autoCode": _auto_code(o, ld),
        # ★ 11 ต.ค.69 ให้เบอร์/LINE แล้ว แต่ยังไม่มีเลขลีด = ป้าย "รอจ่ายเบอร์" ในรายชื่อ
        #   (เดิมรู้ได้ทางเดียวคือเปิดห้องพัก Lead — ในกล่องแชทรวมไม่มีอะไรบอกว่าแชทนี้กลายเป็นลีดแล้ว)
        "contact": ("qr" if (ld.auto or {}).get("line_id") == QR_SRC and not ld.phone else "yes")
                   if ld and (ld.phone or ld.line_id) else "",
        "nocode": bool(ld and NOCODE_KEY in (ld.auto or {})),
        # ★ 11 ต.ค.69 อยู่ในห้องพัก Lead แล้วไหม (ติ๊ก "รับ lead จากแชทนี้แล้ว" · หรือสวิตช์ให้เข้าเอง) — ป้าย "รอจ่ายเบอร์"
        "inRoom": in_room(ld),
        "parkedAt": ((ld.auto or {}).get(PARK_KEY) or {}).get("at", "") if ld else "",
        "parkedBy": ((ld.auto or {}).get(PARK_KEY) or {}).get("by", "") if ld else "",
        # ★ 11 ต.ค.69 (ค่ำ) ให้เบอร์/ID แล้ว รอแอดมินกด "รับ lead" — อยู่กลุ่ม "รอกดรับ" บนสุดของห้องพัก Lead (ป้ายเด่นในรายชื่อ)
        "pendingPark": (o.id in pend) if pend is not None else pending_one(o, ld),
        # ★ 11 ต.ค.69 ลีดรับซื้อรถ (ลูกค้าอยากขายรถให้เรา) vs ลีดขายรถ · มีรถเทิร์น (ยังเป็นลีดขาย)
        "deal": deal_of(ld),
        "buyRoom": buy_one(ld),
        "trade": bool(ld and TRADE_KEY in (ld.auto or {})),
    }
    # ★ 11 ต.ค.69 หน้ารวมแชท: ขั้นของลีด · ความร้อน · เงียบกี่วัน · นัดถัดไป · รถใหม่ตรง (crm.py)
    try:
        from . import crm
        out.update(crm.row_extra(o, ld, now, appt=(appt_map.get(o.id, False) if appt_map is not None else None),
                                 matches=matches))
    except Exception:
        pass
    return out


# ─────────────────────────────────────────────────────────────
#  ข้อมูลลีดของลูกค้า — ช่องเดียวกับชีตลีด + ใบจ่ายลีด (3 ต.ค.69 · เจ้าของสั่ง)
#  "เก็บข้อมูลตามนี้ และเก็บข้อมูลอัตโนมัติตามนี้"
# ─────────────────────────────────────────────────────────────
# ช่องที่คนแก้ได้ + ความยาวสูงสุด (ลำดับ = ลำดับในฟอร์ม) — แก้ช่องไหนต้องผ่านลิสต์นี้เท่านั้น
LEAD_FIELDS = {
    "customer_name": 120, "phone": 40, "line_id": 80,
    "code": 32, "lead_type": 40, "ads": 120, "account": 120, "channel": 80, "branch": 60,
    "live_team": 60, "admin_name": 60, "focus": 60,
    "car_text": 300, "car_model": 80, "call_proof": 20,
    "fill_note": 500, "admin_profile": 1000,
    "occupation": 80, "income": 60, "job_tenure": 60, "pay_history": 120, "customer_type": 60,
    "customer_status": 40,
    "live": 60, "more": 500,
}
HUMAN = "คน"                      # ค่าใน `auto` = คนแก้ช่องนี้แล้ว → ระบบห้ามเติมทับ
SYSTEM = "ระบบ"                   # ค่าตั้งต้นที่ระบบใส่ให้ (ช่องทาง/สาขา/Admin) — ข้อมูลที่ชัดกว่าแทนได้
_SLIP_EVERY_MIN = 30              # หาใบจ่ายลีดในกลุ่มซ้ำได้ทุกกี่นาที (ต่อลูกค้า)
_VOCAB = {"at": 0.0, "src": None, "cars": [], "names": {}, "bases": []}

# ── ตัวเลือก dropdown = ชุดเดียวกับชีตลีด (4 ต.ค.69 · เจ้าของสั่ง "ไปดูดรอปดาวต่างๆที่ใช้ในนี้") ──
# อ่านกฎ dropdown ของแท็บเดือนล่าสุดทุกชั่วโมง (`refresh_dropdowns` ← `tick`) เก็บ KV `connect_lead_dropdowns`
# รายการเปลี่ยนทุกเดือน (ต.ค. มีเซลล์ใหม่ 3 · ช่องทางใหม่ 5 · รุ่นรถหาย 14) → **ห้ามฮาร์ดโค้ดเป็นของจริง**
# ช่องในฟอร์ม → ชื่อคอลัมน์ใน `LEADS_COL` (จับคอลัมน์ในชีตด้วยชื่อหัวตาราง ไม่ใช่ตำแหน่ง)
DD_COLS = {
    "live_team": "live_team", "admin_name": "admin", "channel": "channel", "branch": "branch",
    "lead_type": "type", "car_model": "car_formula", "call_proof": "call_proof", "focus": "focus",
    "occupation": "occupation", "income": "income", "job_tenure": "job_tenure",
    "pay_history": "payment_history", "customer_type": "customer_type",
    "customer_status": "customer_status",
}
DD_KEY = "connect_lead_dropdowns"
DD_EVERY_MIN = 60                 # อ่านชีตใหม่ทุกชั่วโมง — แอดมินเพิ่มตัวเลือกในชีตแล้วเห็นในหน้า Connect ไม่เกิน 1 ชม.
DD_RETRY_MIN = 15                 # อ่านไม่ได้ = เว้น 15 นาทีค่อยลองใหม่ (ไม่ยิงทุกนาที)
# ชุดที่จดจากแท็บ "ตุลาคม 69" (4 ต.ค.69) — ใช้เฉพาะตอนยังไม่เคยอ่านชีตได้เลย (เครื่อง dev / deploy ใหม่ก่อน cron รอบแรก)
DD_FALLBACK = {
    "live_team": ["Live Infu", "Live Productions", "Live Sale", "Live boss"],
    "admin_name": ["กวาง", "หมิว", "เนเน่", "ADMIN", "เฟิร์น", "ฟิล์ม"],
    "channel": ["เพจบ้านเก่า", "เพจอ่อนนุช", "เพจ Guru", "LINE@", "เบอร์กลาง / เพจ", "เบอร์กลาง / Tiktok",
                "TIKTOK ช่องขายบอส", "Tiktok Guru", "Tiktok  ช่องหลัก", "TIKTOK โอ๊ต", "Tiktok นวล", "Tiktok มัท",
                "TIKTOK อุ้ม", "12car", "web oxlet", "Youtube", "TIKTOK เฟิร์ส", "Line@ / TIKTOK", "Broker oxlet",
                "LIVE Facebook", "LIVE Tiktok / ช่องขายบอส", "LIVE Tiktok / ช่องหลัก", "Market Place",
                "ส่วนตัวแอดมิน", "LIVE Tiktok / ช่อง888", "Roddonjai", "TIKTOK ช่องบอสเจมส์ทะเบียนเทพ",
                "LIVE Tiktok / ช่อง Guru", "TIKTOK ช่อง888", "TikTokAds", "Tiktok มด", "Tiktok ช่องแซน",
                "tiktok บิว", "TIKTOK รถเข้าใหม่อ๊อกเล็ตธ์"],
    "branch": ["ชลบุรี", "เทพารักษ์"],
    "lead_type": ["Very Hot", "Hot", "Moderate", "Hot RB", "Hot RJ", "RJ", "MerHot", "TLD", "TLD / Hot", "BLD"],
    "car_model": ["รถที่ไม่ได้ทำการตลาด", "ลูกค้าไม่ตอบ", "ไม่ระบุรุ่นรถ", "Accord", "Almera", "Almera Turbo",
                  "Alphard", "Altis", "Benz", "BMW", "Brio", "BRV", "Camry", "CHR", "City 4 ประตู", "City 5 ประตู",
                  "Civic FC", "Civic FE", "Civic FK", "Commuter", "Corolla Cross", "CRV", "CX-3", "CX-30", "D Max",
                  "Everest", "Fortuner", "HRV", "Innova", "Jazz", "Majesty", "Mazda2", "Mazda3", "MG", "Mirage",
                  "MuX", "New Commuter", "Pajero", "Revo", "Swift", "Sylphy", "Teana", "Terra", "Vellfire", "Veloz",
                  "Ventury", "Vigo", "Vigo LPG", "Vios", "Xpander", "Hyundai", "Mu7", "Yaris Cross", "Yaris Ativ",
                  "New Yaris 5 ประตู", "Yaris 5 ประตูตัวเก่า", "Ford Ranger", "x-trail", "XL7", "Kia", "Triton"],
    "call_proof": ["ส่งแล้ว", "ยังไม่ส่ง", "รอหลักฐาน"],
    "focus": ["FOCUS", "Concentrate"],
    "customer_type": ["พนักงานบริษัท", "เจ้าของธุรกิจส่วนตัว", "อาชีพอื่นๆ", "ไม่แจ้งอาชีพ", "ข้าราชการ/รัฐวิสาหากิจ",
                      "เกษตกร/ปศุสัตว์", "ไม่มีอาชีพ", "ค้าขาย", "Rider/driver", "ฟลีแลนด์", "ข้อมูลติดต่อผิด",
                      "ลูกจ้างรับสด"],
    "customer_status": ["คืนเคส", "จอง", "สนใจมาก", "ลังเล", "รอตอบ", "ลูกค้าไม่ตอบ", "ติดต่อไม่ได้", "ไม่รับสาย",
                        "ยังไม่สะดวกคุย", "รถขายไปแล้ว", "รอเช็คเครดิต", "ดาวน์ไม่พอ", "ส่งมอบ", "ยังไม่ออกเร็วๆนี้",
                        "ไม่มีรถที่ลูกค้าสนใจ", "ติดแบล็คลิส", "เงินสดเงินไม่พอ", "ลูกค้าไม่สนใจแล้ว", "ได้รถแล้ว",
                        "รับรถแล้ว", "รอมาดูรถ", "หาคนออกให้", "มีรถเทริน", "ติดตาม"],
}
DD_FALLBACK_BRANCH = "ชลบุรี"     # วัดจริง ส.ค.–ต.ค.69: ลีด 6,945 แถว สาขา = ชลบุรี ทั้งหมด
_DD = {"at": 0.0, "val": None}


def dropdowns() -> dict:
    """ตัวเลือก dropdown ของฟอร์มลีด (ชุดเดียวกับชีตลีด) — **ไม่ยิงเน็ตในคำขอหน้าเว็บ** อ่านจาก KV ที่ `tick` เติมให้

    คืน `{"fields": {ช่อง: [ตัวเลือก]}, "tab", "at", "branchBySeller", "branchTop", "fallback"}`
    ยังไม่เคยอ่านชีตได้ = `DD_FALLBACK` (`fallback: True`)
    """
    import time
    if _DD["val"] is not None and time.time() - _DD["at"] < 60:
        return _DD["val"]
    val = None
    try:
        from dashboard.services.cache_store import get_kv
        raw = get_kv(DD_KEY) or {}
        d = raw.get("data", raw) if isinstance(raw, dict) else {}
        if isinstance(d, dict) and isinstance(d.get("fields"), dict) and d["fields"]:
            val = dict(d, fallback=False)
            # ช่องที่เพิ่งเพิ่มใน DD_COLS (เช่น สถานะลูกค้า 7 ต.ค.69) ยังไม่อยู่ในชุดที่อ่านไว้จนกว่ารอบอ่านชีตถัดไป (≤1 ชม.)
            #   → ใช้ชุดที่จดไว้ในโค้ดเฉพาะช่องที่ขาด ช่องที่อ่านจากชีตได้แล้วชีตชนะเสมอ
            val["fields"] = {**{k: v for k, v in DD_FALLBACK.items() if k not in d["fields"]}, **d["fields"]}
    except Exception:
        val = None
    if val is None:
        val = {"fields": DD_FALLBACK, "tab": "", "at": "", "branchBySeller": {},
               "branchTop": DD_FALLBACK_BRANCH, "fallback": True}
    _DD.update(at=time.time(), val=val)
    return val


def dd_options(field: str) -> list:
    return list((dropdowns().get("fields") or {}).get(field) or [])


def _ch_key(s) -> str:
    """คีย์เทียบชื่อช่องทาง — ตัดช่องว่าง · "/" · คำว่า "ช่อง" · ไม่สนตัวพิมพ์
    ("Live tiktok ช่องขายบอส" = "LIVE Tiktok / ช่องขายบอส" · "TikTok แซน" = "Tiktok ช่องแซน" · "เพจguru" = "เพจ Guru")"""
    return re.sub(r"[\s/]+|ช่อง", "", str(s or "")).lower()


def dd_pick(field: str, value) -> str:
    """ค่าใน dropdown ที่ตรงกับ `value` (ไม่สนตัวพิมพ์/ช่องว่าง) — ไม่ตรงสักตัว = "" (ไม่เดา)

    ★ 6 ต.ค.69 ช่องทาง: เทียบด้วย `_ch_key` เพิ่ม — วัดจริงใบจ่ายลีด 30 วัน คนพิมพ์ช่องทางในกลุ่ม
    ไม่ตรงคำใน dropdown ของชีตเลย (ชีต "LIVE Tiktok / ช่องขายบอส" · ในกลุ่ม "Live tiktok ช่องขายบอส" 181 ใบ)
    **ต้องตรงตัวเลือกเดียวเท่านั้น** — ตรงหลายตัว/ไม่ตรงเลย = "" (ไม่เดา · ห้ามจับแบบ "คล้ายกัน")"""
    want = re.sub(r"\s+", "", str(value or "")).lower()
    if not want:
        return ""
    opts = dd_options(field)
    for opt in opts:
        if re.sub(r"\s+", "", opt).lower() == want:
            return opt
    if field == "channel":
        k = _ch_key(value)
        hits = [o for o in opts if _ch_key(o) == k]
        if k and len(hits) == 1:
            return hits[0]
    return ""


def _dd_state() -> dict:
    try:
        from dashboard.services.cache_store import get_kv
        raw = get_kv(DD_KEY) or {}
        cur = raw.get("data", raw) if isinstance(raw, dict) else {}
        return cur if isinstance(cur, dict) else {}
    except Exception:
        return {}


def _dd_due(cur=None, now=None) -> bool:
    """ถึงเวลาอ่านชีตใหม่ไหม — อ่านสำเร็จล่าสุดเกิน 1 ชม. และไม่ได้เพิ่งล้มใน 15 นาที"""
    from django.utils.dateparse import parse_datetime
    cur = _dd_state() if cur is None else cur
    now = now or timezone.now()
    last, fail = parse_datetime(cur.get("at") or ""), parse_datetime(cur.get("failAt") or "")
    if last and now - last < timedelta(minutes=DD_EVERY_MIN):
        return False
    if fail and now - fail < timedelta(minutes=DD_RETRY_MIN):
        return False
    return True


def refresh_dropdowns(force: bool = False) -> dict:
    """อ่าน dropdown จากชีตลีดเดือนล่าสุด → KV · เรียกจาก `tick` (ทุกชั่วโมง)

    **อ่านไม่ได้ = ไม่ทับของเดิม** (จดแค่ `failAt` แล้วเว้น 15 นาที) — ชีตล่มชั่วคราวต้องไม่ทำให้ฟอร์มกลายเป็นช่องพิมพ์เปล่า
    """
    from dashboard.services.cache_store import set_kv
    now = timezone.now()
    cur = _dd_state()
    if not force and not _dd_due(cur, now):
        return {}
    err = ""
    try:
        from dashboard.services.google_sheets import LEADS_COL, fetch_lead_dropdowns
        got = fetch_lead_dropdowns()
    except Exception as e:
        got, err = {}, str(e)[:200]
        LEADS_COL = None
    fields = {}
    if LEADS_COL is not None:
        cols = got.get("columns") or {}
        for f, attr in DD_COLS.items():
            vals = cols.get(str(getattr(LEADS_COL, attr)))
            if vals:
                fields[f] = list(vals)
    if not fields:
        set_kv(DD_KEY, dict(cur, failAt=now.isoformat(), error=err or "ไม่เจอ dropdown ในชีตลีด"))
        _DD.update(at=0.0, val=None)
        return {"dropdowns": "fail", "error": err or "ไม่เจอ dropdown"}
    val = {"fields": fields, "tab": got.get("tab") or "", "at": now.isoformat(),
           "branchBySeller": got.get("branchBySeller") or {}, "branchTop": got.get("branchTop") or ""}
    set_kv(DD_KEY, val)
    _DD.update(at=0.0, val=None)
    return {"dropdowns": val["tab"], "fields": len(fields)}


_DD_RUN = {"busy": False}


def _dd_tick():
    """ถึงเวลาอ่านชีตใหม่ไหม (เช็คถูกๆ ใน KV) → อ่านใน thread แยก
    ใช้ ~5 วิ — ห้ามหน่วง cron_tick ที่ต้องส่งตามด่วนให้ตรงนาที"""
    import threading
    if _DD_RUN["busy"] or not _dd_due():
        return {}
    if not BG_FILL:                      # เทสต์: ทำตรงๆ ไม่แตก thread
        return refresh_dropdowns(force=True)

    def _work():
        try:
            refresh_dropdowns(force=True)
        except Exception:
            pass
        finally:
            _DD_RUN["busy"] = False
            try:
                from django.db import connection
                connection.close()
            except Exception:
                pass

    _DD_RUN["busy"] = True
    threading.Thread(target=_work, daemon=True).start()
    return {}


def lead_of(o, create: bool = True):
    """แถวข้อมูลลีดของลูกค้า (สร้างให้ถ้ายังไม่มี) — None ถ้ายังไม่มีและ create=False"""
    try:
        return o.lead
    except ChatLead.DoesNotExist:
        pass
    if not create:
        return None
    try:
        return ChatLead.objects.create(chat=o)
    except IntegrityError:
        return ChatLead.objects.get(chat=o)


def _vocab() -> dict:
    """คีย์รุ่นรถสำหรับ `match_model` — สร้างจาก dropdown "CAR / สูตร" ของชีตลีด (ชุดเดียวกับที่แอดมินเลือกในชีต)

    เรียงยาวก่อน (`civicfc` ต้องชนะ `civic`) · ตัดตัวเลือกที่ไม่ใช่ชื่อรุ่น ("ลูกค้าไม่ตอบ"/"ไม่ระบุรุ่นรถ")
    และชื่อยี่ห้อล้วน (Benz/BMW/MG — ตัดยี่ห้อแล้วเหลือว่าง) · สร้างใหม่เองเมื่อ dropdown เปลี่ยน
    """
    dd = dropdowns()
    if _VOCAB["src"] is dd:
        return _VOCAB
    names, bases = {}, set()
    try:
        from dashboard.services.purchase_report import _BAD_MODEL, _BRANDS, _compact
        for opt in (dd.get("fields") or {}).get("car_model") or []:
            if any(b in opt for b in _BAD_MODEL) or not re.search(r"[A-Za-z]", opt):
                continue
            k = _compact(opt, drop_brand=True)
            if 2 <= len(k) <= 22 and k not in names:
                names[k] = opt
            # ชื่อรุ่นหลักของตัวเลือกที่มีรุ่นย่อย ("City 4 ประตู" → city · "Civic FE" → civic)
            #   ลูกค้าพิมพ์แค่ "city" = พูดถึงรถแน่ แต่ไม่รู้รุ่นย่อย → ได้ "รถลูกค้าถาม" อย่างเดียว
            head = opt.split()[0].lower() if len(opt.split()) > 1 else ""
            if re.fullmatch(r"[a-z]{3,}", head) and head not in _BRANDS and head != "new":
                bases.add(head)
    except Exception:
        names, bases = {}, set()
    _VOCAB.update(src=dd, names=names, cars=sorted(names, key=lambda k: (-len(k), k)), bases=sorted(bases))
    return _VOCAB


# ยี่ห้อที่ลูกค้าพิมพ์เป็นไทย (★ 4 ต.ค.69 — เจ้าของแจ้ง "ลูกค้าก็บอกอยู่นะ อีซูซุ" แต่ใบจ่ายลีดขึ้น "รถ : -")
#   บอกแค่ยี่ห้อ = รู้ว่าลูกค้าถามรถ แต่ไม่รู้รุ่น (อีซูซุ = D Max / MuX / Mu7?) → ได้ "รถลูกค้าถาม" อย่างเดียว
#   ยกเว้นยี่ห้อที่ชีตใช้ตัวเลือกระดับยี่ห้ออยู่แล้ว (Benz · BMW · MG · Hyundai · Kia) → ได้ "CAR / สูตร" ด้วย
_TH_BRAND = {
    "อีซูซุ": "isuzu", "อิซูซุ": "isuzu", "โตโยต้า": "toyota", "โตโยตา": "toyota", "ฮอนด้า": "honda",
    "ฮอนดา": "honda", "นิสสัน": "nissan", "นิสัน": "nissan", "มาสด้า": "mazda", "มาสดา": "mazda",
    "มิตซูบิชิ": "mitsubishi", "มิตซู": "mitsubishi", "ฟอร์ด": "ford", "เชฟโรเลต": "chevrolet",
    "ซูซูกิ": "suzuki", "เบนซ์": "benz", "เบ๊นซ์": "benz", "บีเอ็ม": "bmw", "เอ็มจี": "mg",
    "ฮุนได": "hyundai", "ซูบารุ": "subaru", "เล็กซัส": "lexus", "วอลโว่": "volvo", "ฮาวาล": "haval",
}
_KIA_TH = re.compile(r"เกีย(?!ร)")          # "เกียร์ออโต้" ไม่ใช่ Kia (คำนี้โผล่บ่อยในแชทซื้อรถ)
_BRAND_EN = re.compile(r"(?<![a-z0-9])(isuzu|toyota|honda|nissan|mazda|mitsubishi|ford|chevrolet|chevy|suzuki|"
                       r"benz|mercedes|bmw|mg|hyundai|kia|subaru|lexus|volvo|haval|byd|gwm|neta|peugeot)(?![a-z])")


def brand_in(text: str) -> str:
    """ยี่ห้อรถในข้อความ (ชื่อภาษาอังกฤษตัวเล็ก) · ไม่มี = ค่าว่าง"""
    low = (text or "").lower()
    for th, en in _TH_BRAND.items():
        if th in low:
            return en
    if _KIA_TH.search(low):
        return "kia"
    m = _BRAND_EN.search(low)
    return {"mercedes": "benz", "chevy": "chevrolet"}.get(m.group(1), m.group(1)) if m else ""


def car_in(text: str):
    """รถที่ข้อความนี้พูดถึง → (ตัวเลือก "CAR / สูตร" ของชีต หรือ "" ถ้าบอกรุ่นไม่ชัด, ข้อความเดิม) · ไม่พูดถึงรถ = None

    "CAR / สูตร" ในชีตเป็น dropdown แบบ strict → เติมเฉพาะค่าที่อยู่ในลิสต์เท่านั้น
    · "สนใจ city" = 4 ประตูหรือ 5 ประตูก็ไม่รู้ → คืน "" (ได้แค่ "รถลูกค้าถาม" ให้คนเลือกรุ่นเอง ไม่เดา)
    · บอกแค่ยี่ห้อ ("อีซูซุ") ก็เหมือนกัน — รู้ว่าถามรถ แต่ไม่รู้รุ่น
    """
    t = (text or "").strip()
    if not t:
        return None
    v = _vocab()
    try:
        from dashboard.services.purchase_report import _compact, match_model
    except Exception:
        _compact = match_model = None
    # 1) ชื่อรุ่นที่ตรงตัวเลือกในชีต ("civic fe" → "Civic FE")
    if v["cars"] and match_model:
        k = match_model(t, v["cars"])
        if k:
            return v["names"].get(k, ""), t
    # 2) ชื่อรุ่นภาษาไทย ("แคมรี่" → camry → "Camry" · "ดีแม็ก" → d-max → "D Max")
    try:
        from .leadgroup import parse_specs
        m = parse_specs(t).get("car_model")
    except Exception:
        m = ""
    if m:
        k = match_model(m, v["cars"]) if (v["cars"] and match_model) else ""
        return (v["names"].get(k, "") if k else dd_pick("car_model", m)), t
    # 3) ชื่อรุ่นหลักที่มีหลายรุ่นย่อย ("city" = 4 หรือ 5 ประตู?) → ไม่เดารุ่น
    if _compact and any(b in _compact(t) for b in v.get("bases") or []):
        return "", t
    # 4) บอกแค่ยี่ห้อ → ตัวเลือกระดับยี่ห้อถ้าชีตมี (Benz/BMW/MG/Hyundai/Kia) ไม่งั้น "" (รู้แค่ว่าถามรถ)
    b = brand_in(t)
    if b:
        return dd_pick("car_model", b), t
    return None


_BARE_YEAR = re.compile(r"(?<!\d)(?:19[89]\d|20[0-4]\d)(?!\d)")   # "2015-2017" ไม่มีคำว่าปี · ไม่จับกลางเบอร์โทร


def _has_spec(text: str) -> bool:
    """ข้อความนี้บอกปี/งบ/ผ่อนของรถไหม ("ปี2015-2017" · "งบ 3 แสน" · "ผ่อน 8000")"""
    try:
        from .leadgroup import parse_specs
        sp = parse_specs(text)
        if sp.get("car_year_min") or sp.get("budget_max") or sp.get("monthly_max"):
            return True
    except Exception:
        pass
    return bool(_BARE_YEAR.search(text or ""))


def _car_context(msgs, hits, i) -> str:
    """ข้อความที่พูดถึงรถ (msgs[i]) + ข้อความสั้นที่ติดกันซึ่งเป็นเรื่องเดียวกัน → ข้อความ "รถลูกค้าถาม"

    ลูกค้ามักพิมพ์แยกทีละข้อความ ("อีซูซุ" / "ปี2015-2017") ถ้าเอาแค่ข้อความเดียวจะเสียปีที่ลูกค้าบอก
    ต่อเฉพาะข้อความที่บอก ปี/งบ/ผ่อน หรือพูดถึงรถแบบไม่ชัด (ยี่ห้อ) · ข้อความที่บอกรุ่นชัดคันอื่น = คนละคัน ไม่ต่อ
    """
    model = hits[i][0] if hits[i] else ""

    def joinable(j):
        t = (msgs[j] or "").strip()
        if not t or len(t) > 80:
            return False
        h = hits[j]
        return (not h[0] or h[0] == model) if h else _has_spec(t)

    lo = hi = i
    while lo > 0 and i - lo < 2 and joinable(lo - 1):
        lo -= 1
    while hi + 1 < len(msgs) and hi - i < 3 and joinable(hi + 1):
        hi += 1
    # ★ 7 ต.ค.69 — เก็บแค่รุ่น+สเปกรถ ไม่เอาทั้งประโยค (เจ้าของ: "ตัดคำเกินออก มีเยอะเลย")
    parts = [car_phrase(msgs[j]) for j in range(lo, hi + 1) if (msgs[j] or "").strip()]
    return _dedupe_words(" ".join(p for p in parts if p))[:LEAD_FIELDS["car_text"]]


# ── "รถลูกค้าถาม" = รุ่น + สเปก เท่านั้น (7 ต.ค.69 · เจ้าของส่งรูป "CX3 ปี2022 ขายอยู่เรทประมาณเท่าไหร่ครับ" — "ตัดคำเกินออก") ──
#   แอดมินเขียนช่องนี้สั้น (ชีต ต.ค. 628 ค่า: ≤10 ตัวอักษร 70% · ≤20 ตัวอักษร 95%) เช่น "Civic FE 2.0RS e:HEV 2024"
#   "รีโว่ z edition 4ประตู AT สีขาว ตัวเตี้ย" · "กะบะ 4 ประตู ออโต้ ปี 20 ขึ้น"
#   → เก็บรุ่น/ยี่ห้อ + ปี/สี/ประตู/เกียร์/เครื่อง/รุ่นย่อย · ตัดคำถาม คำลงท้าย และเรื่องรายได้/อายุงาน/ผ่อน/ดาวน์
#   ภาษาไทยไม่เว้นวรรค → ตัดทีละคำ (เว้นวรรค) แล้วเล็มหัว-ท้ายของคำ + ตัดที่ "คำหยุด" กลางคำ
_CP_PRE = sorted(["สวัสดีครับ", "สวัสดีค่ะ", "สวัสดีคะ", "สวัสดี", "ขอสอบถาม", "สอบถาม", "ขอดูรถ", "ขอดู", "ขอชม", "สนใจเป็น",
                  "สนใจขาย", "สนใจ", "อยากได้", "อยากดู", "อยากชม", "อยากทราบ", "อยากรู้ว่า", "อยากรู้", "ต้องการขาย",
                  "ต้องการ", "กำลังหา", "หารถ", "ที่ร้านมี", "ถ้ามี", "มีรถ", "ตัว", "รถ", "เป็น", "พวก", "ผม", "หนู", "เรา",
                  "ประมาณ", "ประมาน", "สัก", "แต่", "ขอ", "หา", "มี", "ขาย", "รุ่น", "ชอบ", "จะมี", "ที่สนใจ", "แบบ",
                  "อยู่", "รับซื้อ", "ออก"],
                 key=len, reverse=True)
_CP_SUF = sorted(["ครับผม", "ครับพี่", "ครับ", "คับ", "ค่ะ", "คะ", "ค่า", "นะคะ", "นะครับ", "นะ", "จ้า", "จ้ะ", "ฮะ", "อ่ะ",
                  "หรอ", "มีไหม", "มีมั้ย", "ไหม", "มั้ย", "มั๊ย", "ไม๊", "บ้าง", "ได้ไหม", "ได้มั้ย", "ด้วย", "หน่อย", "ป่าว",
                  "หรือเปล่า", "รึเปล่า", "เท่าไหร่", "เท่าไร", "เท่าไหร", "ประมาณ", "ประมาน", "ไหน", "พี่", "ก็ได้", "จ้าาา",
                  "อยู่", "รถ"],
                 key=len, reverse=True)
_CP_STOP = re.compile(r"คัน(?!จริง)|ที่รีวิว|ราคา|ผ่อน|ดาวน์|ดาว(?=\d|\s|$)|เงินเดือน|รายได้|อายุงาน|ออกได้|ได้ไหม|ได้มั้ย|"
                      r"เทิร์น|เทริน|แนะนำ|ใว้|ไว้|นี่|ต้อง|ขายอยู่|ขายได้|ขาย(?!ของ)|เรท|เท่าไหร่|เท่าไร|มีไหม|มีมั้ย|ไหม|มั้ย|"
                      r"ครับ|ค่ะ|คะ|คับ|หรอ|บ้าง|มีแบบ|แบบไหน|ปีไหน|ปีอะไร|สีไหน|ตัวไหน|ฟรีดาวน์|เลยค่ะ|ได้อยู่")
_CP_SPEC = re.compile(r"(?:ปี|ป\.)\s*\d{2,4}|^ปี$|(?<!\d)(?:19[89]\d|20[0-4]\d)(?!\d)|ประตู|เกียร์|ออโต้|ธรรมดา|ดีเซล|เบนซิน|"
                      r"ไฮบริด|เทอร์โบ|โทโบ|^สี\S|ตัว(?:ท็อป|ท๊อป|top|เตี้ย|สูง|รอง|ล่าง|ไฮบริด|สันดา)|ไมล์|โฉม|หน้าใหม่|หน้ายาว|"
                      r"หน้าเก่า|แคป|ตอนเดียว|สองตอน|ยกสูง|เตี้ย|เจน\s?\d|ที่นั่ง|กระบะ|กะบะ|เก๋ง|ขึ้นไป|มือ\s?2|มือสอง|"
                      r"สันดา[ปบ]|ขับ\s?[24]|4wd|4x4|2wd|ยกสูง|^หมื่น|^แสน|^พัน|^\d{2}(?:[-–]\d{2})?\+?$")
_CP_LATIN = re.compile(r"^[a-z0-9.+:/()\-]{1,14}$")
_CP_JOIN = re.compile(r"^(?:กับ|และ|หรือ|/|,|&|\+)$")
_CP_BUDGET = re.compile(r"(?:งบ|ราคา|ไม่เกิน|ผ่อน)\S*\s*[\d,.]+\s*(?:บาท|พัน|หมื่น|แสน|k)?")
_CP_PARTICLE = re.compile(r"(?:ครับ|คับ|ค่ะ|คะ|ค่า|นะ|จ้า|ไหม|มั้ย|หรอ)$")
UNSPEC_MODEL = "ไม่ระบุรุ่นรถ"     # ตัวเลือกใน "CAR / สูตร" ของชีต — ลูกค้าบอกแค่ยี่ห้อ/รุ่นกว้าง


def _cp_trim(w: str):
    """เล็มคำหน้า/ท้าย + ตัดที่คำหยุด → (คำที่เหลือ, จบประโยคไหม)"""
    w = w.strip(" \t()[]\"'“”‘’!?.,~:-")
    end = bool(_CP_PARTICLE.search(w))
    for _ in range(4):
        hit = next((p for p in _CP_PRE if w.startswith(p) and len(w) > len(p)), None)
        if not hit:
            break
        w = w[len(hit):]
    m = _CP_STOP.search(w)
    if m:
        end = True                              # เจอเรื่องอื่น (ราคา/ผ่อน/รายได้/คำถาม) = จบส่วนที่พูดถึงรถ
        w = w[:m.start()]
    for _ in range(4):
        hit = next((s for s in _CP_SUF if w.endswith(s) and len(w) > len(s)), None)
        if not hit:
            break
        w = w[:-len(hit)]
    if w in _CP_PRE or w in _CP_SUF:
        w = ""
    return w.strip(" -/,"), end


def _dedupe_words(s: str) -> str:
    """คำซ้ำ (ไม่สนตัวพิมพ์) ออก · คำที่ขึ้นต้นด้วยคำเดิม ("MuX" แล้ว "muxสีขาว") เหลือแค่ส่วนที่ต่อท้าย"""
    out, seen = [], set()
    for w in s.split():
        k = w.lower()
        if k in seen and not _CP_JOIN.match(w):
            continue
        pre = next((x for x in seen if len(x) >= 3 and k.startswith(x) and len(k) > len(x)), None)
        if pre:
            w, k = w[len(pre):], k[len(pre):]
            if k in seen:
                continue
        seen.add(k)
        out.append(w)
    while out and _CP_JOIN.match(out[-1]):
        out.pop()
    while out and _CP_JOIN.match(out[0]):
        out.pop(0)
    return " ".join(out)


def car_phrase(text: str) -> str:
    """ข้อความลูกค้า 1 ข้อความ → เฉพาะส่วนที่บอกรถ ("CX3 ปี2022 ขายอยู่เรทประมาณเท่าไหร่ครับ" → "CX3 ปี2022")

    เก็บ: ยี่ห้อ/รุ่น (`car_in`) + คำที่ตามมาติดๆ ที่เป็นสเปก (ปี สี ประตู เกียร์ เครื่อง รุ่นย่อยภาษาอังกฤษ)
    · สเปกที่อยู่ก่อนชื่อรุ่นไม่เกิน 2 คำ ("ปี 2024 Toyota Yaris cross") · ตัวเชื่อม กับ/หรือ ระหว่าง 2 รุ่น
    · งบ/ผ่อน เก็บเฉพาะตอนไม่มีชื่อรุ่นเลย ("รถผ่อนไม่เกิน 7 พัน") — มีรุ่นแล้ว งบไม่ใช่ข้อมูลรถ
    ไม่เจอรถเลย = คืนข้อความที่เล็มแล้ว (ไม่เกิน 40 ตัว) — ไม่ทิ้งข้อมูลที่ลูกค้าพิมพ์มา
    """
    raw = re.sub(r"\s+", " ", (text or "").replace("\n", " ")).strip()
    if not raw:
        return ""
    words, has_model = [], False
    for w in raw.split(" "):
        jn = ""
        for c in ("หรือ", "กับ", "และ"):
            if w.startswith(c) and len(w) > len(c) + 1:
                jn, w = c, w[len(c):]
                break
        t, end = _cp_trim(w)
        if jn:
            words.append((jn, "join", False))
        if not t:
            words.append(("", "end" if end else "skip", end))
            continue
        low = t.lower()
        if _CP_JOIN.match(t):
            kind = "join"
        elif car_in(t) is not None:
            kind = "car"
            has_model = has_model or bool(car_in(t)[0])
        elif _CP_SPEC.search(low):
            kind = "spec"
        elif _CP_LATIN.match(low) and not re.search(r"\d{5,}", low.replace(",", "")):   # เลข 5 หลัก = เงิน ไม่ใช่สเปก
            kind = "latin"
        else:
            kind = "other"
        words.append((t, kind, end))
    out, run, after_end, last_car = [], False, False, -9
    for i, (t, kind, end) in enumerate(words):
        if kind == "car":
            # สเปกก่อนชื่อรุ่น ("ปี 2024 Toyota …") — ย้อนเก็บได้ไม่เกิน 2 คำ
            j = i - 1
            pre = []
            while j >= 0 and i - j <= 2 and words[j][1] in ("spec", "latin") and not words[j][2]:
                pre.insert(0, words[j][0])
                j -= 1
            if out and last_car >= 0 and words[i - 1][1] == "join" if i else False:
                out.append(words[i - 1][0])
            out.extend(w for w in pre if w not in out)
            out.append(t)
            run, after_end, last_car = not end, end, i
        elif run and kind in ("spec", "latin") or (run and kind == "other" and len(t) <= 10 and i - last_car <= 2
                                                     and not re.search(r"\d", t)):
            out.append(t)
            if end:
                run, after_end = False, True
        elif after_end and kind == "spec":
            out.append(t)                       # "…5 ประตูไหมคะ ประมาณปี 2018" — สเปกที่ตามมาหลังจบประโยค
        elif kind == "join" and out:
            continue                            # ตัวเชื่อมใส่ตอนเจอรุ่นถัดไป
        else:
            if kind in ("other", "end"):
                after_end = after_end and kind == "end"
            run = run and kind == "skip"
    s = _dedupe_words(" ".join(out))
    b = _CP_BUDGET.search(raw)
    if s and b and not has_model:
        # บอกแค่ยี่ห้อ ("งบ 3 แสน" / "ฮอนด้า") → งบเป็นข้อมูลรถที่มีอยู่ เก็บไว้ตามลำดับที่ลูกค้าพิมพ์
        bt = re.sub(r"\s+", " ", b.group(0)).strip()
        rest = " ".join(w for w in s.split() if w not in bt.split())
        first = next((raw.find(w) for w in rest.split() if raw.find(w) >= 0), len(raw))
        s = (bt + " " + rest if b.start() < first else rest + " " + bt).strip()
    if s:
        return s
    # ไม่มีชื่อรุ่น (เช่น "รถเก๋งผ่อนไม่เกิน 6000") → เล็มคำลงท้าย/คำถามออก เก็บงบไว้
    b = _CP_BUDGET.search(raw)
    keep = [_cp_trim(w)[0] for w in raw.split(" ")]
    s = _dedupe_words(" ".join(w for w in keep if w))
    if b and b.group(0) not in s:
        s = (s + " " + b.group(0)).strip()
    return s[:40]


# ★ 20 ต.ค.69 เจ้าของ "แท็กช่องทางให้ถูกตาม dropdown ของ sheet" — เพจ Facebook → ตัวเลือกช่องทางที่ขึ้นต้นด้วย "เพจ"
#   2 เพจของอ๊อกเล็ตธ์ออโต้ชื่อต่างกันแค่คำท้าย → ระบุเอง (วัดจากใบจ่ายลีดจริง: เพจ …สำนักงานใหญ่ แอดมินเขียน "เพจบ้านเก่า" 273/279 ·
#   เพจ 482041925229408 = "เพจอ่อนนุช" 65/77) · เพจอื่น = ตัวเลือก "เพจ X" ที่ X อยู่ในชื่อเพจ ("เพจ Guru" ↔ "Guru เจมส์ รถมือสอง")
#   ชีตไม่มีตัวเลือกของเพจนั้น / ตรงหลายตัว = ไม่เติม (ไม่เดา · แอดมินเพิ่มตัวเลือกในชีตแล้วระบบเห็นเองภายใน 1 ชม.)
FB_PAGE_CHANNEL = {"2302089596486628": "บ้านเก่า", "482041925229408": "อ่อนนุช", "650823708107550": "guru"}


def _fb_channel(page_id) -> str:
    pid = str(page_id or "")
    opts = [(o, re.sub(r"\s+", "", o).lower()) for o in dd_options("channel")]
    opts = [(o, n) for o, n in opts if n.startswith("เพจ")]
    kw = FB_PAGE_CHANNEL.get(pid)
    if kw:
        hit = [o for o, n in opts if kw in n]
    else:
        name = re.sub(r"\s+", "", fb_page_name(pid) or "").lower()
        if not name or name == pid:
            return ""
        hit = [o for o, n in opts if len(n) > 5 and n[3:] in name]
    return hit[0] if len(hit) == 1 else ""


def _line_channel() -> str:
    """ช่องทางของลูกค้าที่ทักเข้า LINE OA ตาม dropdown ของชีต
    วัดจริง ส.ค.–ต.ค.69: ลีดจาก LINE 741 แถว = "LINE@" 740 · "Line@ / TIKTOK" 1"""
    opts = dd_options("channel")
    for opt in opts:
        if re.sub(r"\s+", "", opt).lower() == "line@":
            return opt
    return next((opt for opt in opts if "line" in opt.lower() and "/" not in opt), "LINE@")


def _norm_name(s) -> str:
    return re.sub(r"[^0-9a-zก-๙]+", "", (s or "").lower())


def _lead_group_ids() -> set:
    """กลุ่มจ่ายเบอร์ (ใบจ่ายลีดถูกโพสต์ที่นี่) — จากทะเบียนกลุ่ม + ชื่อกลุ่มที่มีคำว่า จ่ายเบอร์"""
    ids = set()
    try:
        from .models import LineGroup
        ids |= set(LineGroup.objects.filter(kind=LineGroup.LEAD).values_list("group_id", flat=True))
    except Exception:
        pass
    ids |= set(GroupChat.objects.filter(chat_type=GroupChat.GROUP, group_name__icontains="จ่ายเบอร์")
               .values_list("group_id", flat=True).distinct())
    return {g for g in ids if g}


def find_slip(phone: str = "", line_name: str = ""):
    """หาใบจ่ายลีดที่แอดมินเคยโพสต์ในกลุ่มจ่ายเบอร์ ของลูกค้าคนนี้ → (ข้อมูลใบ, แถวแชท) หรือ None

    จับคู่ด้วย **เบอร์โทรเต็ม** (ค้นด้วย 4 ตัวท้ายก่อนแล้วตรวจซ้ำ) หรือ **ชื่อไลน์ตรงกันทั้งชื่อ**
    — ไม่ใช้ "ชื่อคล้ายกัน" (บทเรียนเดิม: substring จับคนผิดคน)
    """
    from .leadgroup import parse_leadsheet
    gids = _lead_group_ids()
    if not gids or not (phone or line_name):
        return None
    qs = GroupChat.objects.filter(chat_type=GroupChat.GROUP, group_id__in=gids, text__icontains="lead no")
    cands = []
    if phone and len(phone) >= 9:
        cands += list(qs.filter(text__contains=phone[-4:]).order_by("-sent_at")[:40])
    nn = _norm_name(line_name)
    if len(nn) >= 2:
        cands += list(qs.filter(text__icontains=(line_name or "").strip()[:40]).order_by("-sent_at")[:40])
    seen = set()
    for g in sorted(cands, key=lambda x: x.sent_at or timezone.now(), reverse=True):
        if g.pk in seen:
            continue
        seen.add(g.pk)
        d = parse_leadsheet(g.text or "")
        if not d:
            continue
        ph = phones_in([d.get("phone", "")])
        if phone and ph and ph[0] == phone:
            return d, g
        if nn and _norm_name(d.get("line_name")) == nn:
            return d, g
    return None


# ── จ่ายเบอร์ "นอกระบบ" ลงชีตลีดไปแล้ว (11 ต.ค.69 · เจ้าของ: "lead ทุกอย่างต้องออโต้") ──
#   วัดจริง: ลีดแชทที่รอจ่ายเบอร์และมีเบอร์ 72 ราย → **35 รายเบอร์เดียวกันได้เลขในชีตลีดวันเดียวกับที่คุยกันแล้ว**
#   (ใบในกลุ่มจับคู่ไม่ได้ เพราะแอดมินลงชีตตรง/ใบไม่มีเบอร์) → ค้างในห้องพักทั้งที่จ่ายไปแล้ว
#   ตัวจับ = **สมุดเบอร์** (`LeadPhone` · สร้างจากชีตลีดใหม่ทุก 6 ชม.) · เบอร์เต็มเท่านั้น (ไม่ใช่ชื่อ — ไม่ fuzzy)
#   ★ นับเฉพาะเลขที่ "วันที่รับลีด" อยู่ในรอบที่ลูกค้าคุยกับเราอยู่ (≤ SHEET_MATCH_DAYS วันก่อนข้อความล่าสุด)
#     เลขเก่ากว่านั้น = ลูกค้าเก่ากลับมาใหม่ → ไม่เดาให้ ยังอยู่ในห้องพักพร้อมป้าย "เบอร์ซ้ำ" ให้คนตัดสิน
SHEET_KEY = "_sheet"
SHEET_MATCH_DAYS = 14
MAYBE_KEY = "_maybe"              # ★ 18 ต.ค.69 ใบจ่ายลีดที่ตรงแค่ชื่อ — {code, at, tag, how} ให้แอดมินดู · ระบบจ่ายวนข้าม


def _sheet_lid(lead, o):
    """ID LINE นี้ได้เลขในชีตลีดแล้วในรอบที่คุยกันอยู่ (ชีตเขียน "ID LINE : xxx" ในช่องเบอร์) — กติกาเดียวกับ sheet_match"""
    if not lead.line_id:
        return None
    try:
        from . import leadmatch as LM
        return LM.sheet_by_lid(lead.line_id, o.last_in_at, chat_lead_pk=lead.pk)
    except Exception:
        return None


def sheet_match(phone: str, last_in=None, chat_lead_pk=None) -> dict | None:
    """เบอร์นี้ได้เลขลีด (ชีตลีด/ใบในกลุ่ม/ปุ่มในระบบ) ในรอบที่คุยกันอยู่หรือยัง → `{code, seller, date, codes, at}` หรือ None
    หลายเลขในรอบเดียวกัน (จ่ายใหม่/ไม้ 2) = ใช้เลขล่าสุด · เลขอื่นจดไว้ใน `codes`
    ★ เลขในรอบนี้มีลูกค้าอีกรายในระบบถืออยู่แล้ว (แชทอีกบัญชี/ใบร่างที่จ่ายจากห้องพัก) = None
      ไม่ก๊อปเลขเดียวไปไว้ 2 ที่ (เลขซ้ำ = นับซ้ำ + ส่งต่อไม้ 2 พัง) → ให้แอดมินตัดสินจากกล่องเตือนเบอร์ซ้ำเหมือนเดิม"""
    from datetime import datetime as _dt, time as _time
    from . import phonebook
    p = phonebook.norm(phone)
    if not p:
        return None
    ref = timezone.localtime(last_in).date() if last_in else timezone.localdate()
    cut = ref - timedelta(days=SHEET_MATCH_DAYS)
    hits = [x for x in phonebook.lookup(p, days=400)
            if x.get("code") and x.get("date") and x["date"] >= cut.isoformat()]
    if not hits:
        return None
    held = Q()
    for c in {x["code"].upper() for x in hits}:
        held |= Q(code__iexact=c)
    if ChatLead.objects.filter(held).exclude(pk=chat_lead_pk).exists() or ExtLead.objects.filter(held).exists():
        return None
    hits.sort(key=lambda x: (x["date"], "/" in x["code"], x["code"]), reverse=True)
    top = hits[0]
    try:
        at = timezone.make_aware(_dt.combine(_dt.fromisoformat(top["date"]).date(), _time(9, 0)))
    except Exception:
        at = timezone.now()
    return {"code": top["code"].upper(), "seller": top.get("seller") or "", "date": top["date"],
            "src": top.get("source") or "", "codes": [x["code"].upper() for x in hits][:6], "at": _iso(at)}


# ── ลูกค้าที่ "อยากขายรถให้เรา" — แอดมินส่งเข้ากลุ่มเคสHOT ของจัดซื้อ ไม่ใช่ห้องจ่ายเบอร์ (4 ต.ค.69) ──
#   ใบหน้าตาคนละแบบ (`leadgroup.parse_buycase` · "โค้ด : OC-7436") · เลขเป็นของงานรับซื้อ **ไม่ใช่เลขลีดขาย**
#   → ไม่ใส่ลงช่อง Code ของฟอร์ม · จดไว้ที่ `ChatLead.auto[BUY_KEY]` แล้วถือว่า "จ่ายแล้ว" (ออกจากห้องพัก)
BUY_KEY = "_buy"
BUY_GROUP_HINTS = ("ซื้อ-ขายรถ", "ซื้อขายรถ")


def _buy_group_ids() -> set:
    ids = set()
    try:
        from .models import LineGroup
        ids |= set(LineGroup.objects.filter(kind=LineGroup.TRADEIN).values_list("group_id", flat=True))
    except Exception:
        pass
    q = Q()
    for hint in BUY_GROUP_HINTS:
        q |= Q(group_name__icontains=hint)
    ids |= set(GroupChat.objects.filter(q, chat_type=GroupChat.GROUP).values_list("group_id", flat=True).distinct())
    return {g for g in ids if g}


def _channel_fits(channel: str, fb: bool) -> bool:
    """ช่องทางที่เขียนในใบ ไม่ขัดกับที่ลูกค้าทักมาจริง — ใช้ตอนจับคู่ด้วย "ชื่อ" เท่านั้น (เบอร์ตรง = เชื่อได้อยู่แล้ว)
    ชื่อซ้ำกันได้ระหว่างคนทัก LINE กับคนทักเพจ · ใบเขียนว่า LINE@ แต่ลูกค้าคนนี้ทักเพจ = ไม่ใช่คนเดียวกัน"""
    c = (channel or "").lower()
    if not c:
        return True
    says_line = "line" in c or "ไลน์" in c
    says_fb = any(k in c for k in ("เพจ", "page", "fb", "facebook", "เฟส"))
    if fb:
        return not says_line or says_fb
    return not says_fb or says_line


def find_buy_slip(phone: str = "", name: str = "", fb: bool = False):
    """ใบเคสรับซื้อของลูกค้าคนนี้ในกลุ่มเคสHOT → (ข้อมูลใบ, แถวแชท) หรือ None
    จับคู่ด้วย **เบอร์โทรเต็ม** หรือ **ชื่อตรงทั้งชื่อ + ช่องทางไม่ขัดกัน** (ไม่ fuzzy — บทเรียนเดิม)"""
    from .leadgroup import parse_buycase
    gids = _buy_group_ids()
    if not gids or not (phone or name):
        return None
    qs = GroupChat.objects.filter(chat_type=GroupChat.GROUP, group_id__in=gids, text__contains="โค้ด")
    cands = []
    if phone and len(phone) >= 9:
        cands += list(qs.filter(text__contains=phone[-4:]).order_by("-sent_at")[:40])
    nn = _norm_name(name)
    if len(nn) >= 4:
        cands += list(qs.filter(text__icontains=(name or "").strip()[:40]).order_by("-sent_at")[:40])
    seen = set()
    for g in sorted(cands, key=lambda x: x.sent_at or timezone.now(), reverse=True):
        if g.pk in seen:
            continue
        seen.add(g.pk)
        d = parse_buycase(g.text or "")
        if not d:
            continue
        ph = phones_in([d.get("phone", "")])
        if phone and ph and ph[0] == phone:
            return d, g
        if len(nn) >= 4 and _norm_name(d.get("name")) == nn and _channel_fits(d.get("channel", ""), fb):
            return d, g
    return None


def _buy_owner(g, d) -> str:
    """เคสนี้ส่งให้จัดซื้อคนไหน — แท็กท้ายใบก่อน · ไม่แท็ก (ครึ่งหนึ่งของใบจริง) = ชื่อในวงเล็บของกลุ่ม "เคสHOT (พี่หมี)" """
    tag = d.get("assigned", "")
    if tag:
        return tag_nick(tag)
    m = re.search(r"\(([^)]+)\)", g.group_name or "")
    if not m:
        return ""
    who = m.group(1).strip()
    # "พี่ต๊าด" ในชื่อกลุ่ม · ทะเบียนเขียน "ต๊าด" (ส่วน "พี่หมี" ทะเบียนเขียนเต็ม) → ลองทั้ง 2 แบบ ไม่เจอ = ชื่อตามกลุ่ม
    return _tag_match(who) or (who.startswith("พี่") and _tag_match(who[3:])) or who


def buy_mark(d, g) -> dict:
    return {"code": d.get("case_code", ""), "at": _iso(g.sent_at), "group": g.group_name or "",
            "tag": d.get("assigned", ""), "seller": _buy_owner(g, d), "by": _poster(g)}


# ── "จ่ายให้ใคร" (4 ต.ค.69 · เจ้าของ: "หลีดบางตัวก็จ่ายไปแล้ว บางตัวก็ยังไม่จ่าย อยากรู้ว่าจ่ายให้ใครบ้าง") ──
#   ใบจ่ายลีดแท็กเซลล์ท้ายใบ (@ + ชื่อ LINE คำแรก เช่น "@เซลมัท" "@First" "@Mai🐶OxletAuto")
#   → แปลงเป็นชื่อเล่นในทะเบียน · ไม่ชัด (ไม่เจอ / ตรงหลายคน) = คืนแท็กเดิม ไม่เดา
_TAGNICK = {"at": 0.0, "map": {}}


def _tag_key(s) -> str:
    from .people import _norm
    return _norm(s)


def tag_nick(tag) -> str:
    t = (tag or "").strip().lstrip("@")
    return _tag_match(t) or t


def _tag_match(tag) -> str:
    """ชื่อเล่นในทะเบียนของแท็กนี้ · ไม่เจอ/ตรงหลายคน = "" (แยก "ไม่เจอ" ออกจาก "เจอแล้วชื่อเดียวกับแท็ก")"""
    t = (tag or "").strip().lstrip("@")
    if not t:
        return ""
    import time as _t
    if _t.time() - _TAGNICK["at"] > 600:              # จำ 10 นาที — ทะเบียนพนักงานเปลี่ยนไม่บ่อย
        hits = {}
        try:
            names = list(Employee.objects.filter(active=True).values_list("nickname", "display_name"))
            # ★ 6 ต.ค.69 — ชื่อของบัญชีที่ผูกทะเบียนแล้วต้องเป็น **ชื่อในทะเบียน** ไม่ใช่สำเนาเก่า
            #   เดิมอ่าน `LineProfile.nickname` → นิดแก้ชื่อแล้ว แท็ก "@Nid" จับได้ทั้ง "นิด" และ "Nid"
            #   = 2 ชื่อ → ถือว่ากำกวม ไม่ยอมบอกว่าจ่ายให้ใคร
            for nick, enick, dn in (LineProfile.objects.filter(is_employee=True)
                                    .values_list("nickname", "employee__nickname", "display_name")):
                if (enick or nick):
                    names.append((enick or nick, dn))
            for nick, dn in names:
                for k in {_tag_key(nick), _tag_key(dn), _tag_key((dn or "").split()[0] if (dn or "").split() else "")}:
                    if k:
                        hits.setdefault(k, set()).add(nick)
        except Exception:
            pass
        _TAGNICK.update(at=_t.time(), map=hits)
    s = _TAGNICK["map"].get(_tag_key(t)) or set()
    return next(iter(s)) if len(s) == 1 else ""


def _poster(g) -> str:
    """คนโพสต์ใบจ่ายลีด (แอดมินที่จ่าย) — ชื่อเล่น · **ไม่คืน LINE user id ดิบ**"""
    from .people import nickname_for
    return (nickname_for(g.sender_id or "", g.sender_name or "") or "")[:60]


def _slip_by_code(code: str):
    """ใบจ่ายลีดของเลขนี้ในกลุ่มจ่ายเบอร์ (ใบล่าสุด) → (ข้อมูลใบ, แถวแชท) หรือ None"""
    from .leadgroup import parse_leadsheet
    gids = _lead_group_ids()
    if not gids or not code:
        return None
    for g in (GroupChat.objects.filter(chat_type=GroupChat.GROUP, group_id__in=gids, text__icontains=code)
              .order_by("-sent_at")[:10]):
        d = parse_leadsheet(g.text or "")
        if d and d.get("lead_code", "").upper() == code.upper():
            return d, g
    return None


SLIP_SWEEP_MIN = 3                 # ลีดในห้องพัก: หาใบจ่ายลีดซ้ำทุกกี่นาที (ต่อคน · ตอนเปิดแชทยังเป็น 30)
_SWEEP = {"at": 0.0}


def slip_sweep(limit: int = 300, force: bool = False) -> dict:
    """ลีดในห้องพักที่แอดมิน **จ่ายเบอร์ในกลุ่มไปแล้ว** → จับคู่ใบให้เอง (ได้เลข + จ่ายให้ใคร) แล้วออกจากห้องพัก

    เดิมจับคู่ใบจ่ายลีดเฉพาะตอนมีคนเปิดแชทนั้น → ลีดที่จ่ายในกลุ่มแล้วค้างในห้องพักไปเรื่อยๆ
    (วัดจริง 4 ต.ค.69: ห้องพัก 21 คน มีใบจ่ายลีดในกลุ่มแล้ว 10 คน) · เรียกจาก `tick` ทุกนาที
    + เติม "จ่ายให้ใคร" ให้ลีดที่จับคู่ใบไว้ก่อนมีช่องนี้ (ทีละ 20)
    """
    import time as _t
    if not force and _t.time() - _SWEEP["at"] < 55:
        return {}
    _SWEEP["at"] = _t.time()
    now = timezone.now()
    out = {"matched": 0, "seller": 0}
    from datetime import datetime as _dt
    base = ChatOwner.objects.select_related("profile", "fb_profile", "owner", "lead")
    rows = list(to_code(base).order_by(F("last_at").desc(nulls_last=True))[:limit])
    # ★ 11 ต.ค.69 กลุ่ม "รอกดรับ" ด้วย — ลีดที่จ่ายในชีต/ใบในกลุ่มไปแล้ว ไม่ต้องรอแอดมินกดรับก่อนถึงจะหายจากห้องพัก
    seen = {o.id for o in rows}
    rows += [o for o in pending_park(base).order_by(F("last_in_at").desc(nulls_last=True))[:limit] if o.id not in seen]
    # ★ 11 ต.ค.69 แท็บรับซื้อรถ — แอดมินโพสต์ใบเคสรับซื้อในกลุ่มเคสHOT แล้ว = ออกจากแท็บเอง (find_buy_slip ใน autofill)
    seen = {o.id for o in rows}
    rows += [o for o in buy_room(base).order_by(F("last_in_at").desc(nulls_last=True))[:limit] if o.id not in seen]
    for o in rows:
        if is_sim_row(o):
            continue
        last = ((getattr(o, "lead", None) and o.lead.auto) or {}).get("_slip_at") or ""
        try:
            if last and (now - _dt.fromisoformat(last)) <= timedelta(minutes=SLIP_SWEEP_MIN):
                continue                             # เพิ่งหาไป — ไม่โหลดแชทซ้ำทุกนาที
        except Exception:
            pass
        try:
            if autofill(o, slip_min=SLIP_SWEEP_MIN).code:
                out["matched"] += 1
        except Exception:
            pass
    # ลีดที่ได้เลขจากใบจ่ายลีดก่อนมีช่อง "จ่ายให้ใคร" → หาใบจากเลขแล้วเติม
    for lead in (ChatLead.objects.exclude(code="").filter(auto__has_key="_slip")
                 .exclude(auto___slip__has_key="seller")[:20]):
        auto = dict(lead.auto or {})
        sl = dict(auto.get("_slip") or {})
        hit = _slip_by_code(lead.code)
        sl.update({"seller": "", "tag": "", "by": sl.get("by", "")})
        if hit:
            d, g = hit
            sl.update({"tag": d.get("assigned", ""), "seller": tag_nick(d.get("assigned", "")), "by": _poster(g),
                       "at": sl.get("at") or _iso(g.sent_at)})
            out["seller"] += 1
        auto["_slip"] = sl
        ChatLead.objects.filter(pk=lead.pk).update(auto=auto)
    return out


def slip_sweep_bg() -> dict:
    """เรียกจาก `tick` — รอบกวาดใน thread แยก (โหลดแชทหลายสิบคน · ห้ามหน่วง cron_tick ที่ต้องอุ่นข้อมูลแดชบอร์ด)
    ผลรอบล่าสุด = KV `slip_sweep_last` · เทสต์ (`BG_FILL=False`) = ทำในที่เลย"""
    import threading
    import time as _t
    if _t.time() - _SWEEP["at"] < 55:
        return {}
    if not BG_FILL:
        return slip_sweep()

    def _work():
        res = {}
        try:
            res = slip_sweep() or {}
        except Exception as e:
            res = {"error": str(e)[:200]}
        finally:
            try:
                if res:
                    from dashboard.services import cache_store
                    cache_store.set_kv("slip_sweep_last", dict(res, at=timezone.now().isoformat()))
            except Exception:
                pass
            try:
                from django.db import connection
                connection.close()
            except Exception:
                pass

    threading.Thread(target=_work, daemon=True).start()
    return {"started": True}


def assigned_list(me=None, days: int = 7, limit: int = 150) -> list:
    """ลูกค้าแชท (LINE/FB) ที่ **ได้เลขแล้ว** ภายใน `days` วัน — จ่ายให้ใคร · โดยใคร · เมื่อไหร่ · ทางไหน
    ล่าสุดก่อน · ที่มา 2 ทาง: ปุ่มจ่ายเบอร์ในระบบ (`assigned_at`) / ใบจ่ายลีดในกลุ่ม (`auto._slip`)"""
    now = timezone.now()
    since = now - timedelta(days=days)
    out = []
    qs = (ChatLead.objects.select_related("chat", "chat__profile", "chat__fb_profile", "chat__owner", "chat__lead")
          .filter((~Q(code="") & (Q(assigned_at__gte=since) | Q(auto__has_key="_slip")
                                   | Q(auto__has_key=SHEET_KEY)))
                  | Q(auto__has_key=BUY_KEY)))
    from datetime import datetime as _dt
    for lead in qs[:600]:
        o, auto = lead.chat, (lead.auto or {})
        kind, code = "sale", lead.code
        if lead.code and lead.assigned_at:
            pi = lead.post_info or {}
            at, how = lead.assigned_at, ("ระบบ (ทดลอง)" if lead.code_demo else
                                         "ระบบ → ส่งเข้ากลุ่มแล้ว" if pi.get("ok") else
                                         "ระบบ (ยังส่งเข้ากลุ่มไม่สำเร็จ)" if pi.get("error") else "ระบบ")
            seller = o.owner.nickname if o.owner_id else ""
            by = lead.assigned_by or ""
        else:
            # ใบลีดขาย (`_slip`) ก่อน · แล้วเลขจากชีตลีด (`_sheet` · จ่ายนอกระบบ)
            #   · ไม่มีเลขลีดขาย = ส่งเข้ากลุ่มเคสHOT ของจัดซื้อ (`BUY_KEY`)
            sl = auto.get("_slip") if lead.code else None
            sheet = None if sl or not lead.code else auto.get(SHEET_KEY)
            if sheet and (sheet.get("code") or "") != lead.code:
                sheet = None                        # คนแก้เลขเองทีหลัง — ป้ายชีตเดิมไม่ตรงแล้ว
            if sheet:
                sl = dict(sheet, seller=("เทเลเซลล์" if sheet.get("seller") == "ADMIN" else sheet.get("seller", "")),
                          by="")
            if not sl:
                sl, kind, code = auto.get(BUY_KEY) or {}, "buy", (auto.get(BUY_KEY) or {}).get("code", "")
            try:
                at = _dt.fromisoformat(sl.get("at") or "")
            except Exception:
                continue
            # "เคสHOT (พี่หมี) ซื้อ-ขายรถช่องทางออนไลน์" → "เคสHOT (พี่หมี)" (การ์ดแคบ ชื่อเต็มยาวเกิน)
            short = re.sub(r"\s*ซื้อ-?ขายรถ.*$", "", sl.get("group") or "") or "เคสHOT"
            how = (("ส่งจัดซื้อ · " + short) if kind == "buy" else
                   "ชีตลีด (จ่ายนอกระบบ)" if sheet else "ใบในห้องจ่ายเบอร์")
            seller, by = sl.get("seller") or sl.get("tag") or "", sl.get("by") or ""
        if at < since or not code:
            continue
        r = row_json(o, me, now)
        r.update({"code": code, "seller": seller, "by": by, "at": _iso(at), "how": how, "kind": kind})
        out.append(r)
    out.sort(key=lambda r: r["at"], reverse=True)
    return out[:limit]


AD_SRC = "โฆษณา"          # auto[ช่อง] = รุ่นรถจากข้อความต้อนรับของโฆษณา (ลูกค้าพิมพ์รุ่นเองทีหลัง = แทนได้)
AD_KEY = "_adcar"          # auto[AD_KEY] = รุ่นที่เจอในข้อความต้อนรับ ("" = ดูแล้วไม่มี · ไม่ดูซ้ำ)
AD_GREET_SEC = 120         # ข้อความต้อนรับ = ข้อความเพจที่ออกก่อนข้อความแรกของลูกค้าไม่เกินเท่านี้


def _ad_car(o, events=None) -> str:
    """รุ่นรถในข้อความต้อนรับของเพจ (โฆษณาแบบทักแชท) → ชื่อตัวเลือก "CAR / สูตร" ของชีต · ไม่เจอ = ""

    ข้อความต้อนรับ = ข้อความขาออกที่ไม่ได้ส่งจาก Connect · ออกก่อนข้อความแรกของลูกค้าไม่เกิน AD_GREET_SEC วินาที
    (หรือตามหลังไม่เกิน FB_AUTO_SEC — ตอบอัตโนมัติ) · ได้เฉพาะรุ่นที่ตรงตัวเลือกชีตชัด ไม่เอารุ่นกว้าง"""
    from datetime import datetime as _dtm
    try:
        ev = events if events is not None else messages(o, limit=60)
    except Exception:
        return ""
    first_in = next((m for m in ev if m.get("dir") != "out" and m.get("at")), None)
    if not first_in:
        return ""
    try:
        t_in = _dtm.fromisoformat(first_in["at"])
    except Exception:
        return ""
    for m in ev:
        if m.get("dir") != "out" or not m.get("text") or (m.get("by") or "") not in ("", "ตอบอัตโนมัติ (เพจ)", "ตอบใน Facebook"):
            continue
        try:
            gap = (t_in - _dtm.fromisoformat(m["at"])).total_seconds()
        except Exception:
            continue
        if -FB_AUTO_SEC <= gap <= AD_GREET_SEC:
            h = car_in(m["text"])
            if h and h[0] and h[0] != UNSPEC_MODEL:
                return h[0]
    return ""


def autofill(o, msgs=None, slip_min=None, events=None) -> ChatLead:
    """เติมข้อมูลลีดอัตโนมัติ — **เฉพาะช่องที่ว่างและยังไม่เคยเติม** ไม่ทับสิ่งที่คนพิมพ์เด็ดขาด

    ที่มา: แชท (เบอร์ · รถที่ถาม · รุ่นแบบ "CAR / สูตร") · ระบบ (ช่องทาง LINE@ · สาขา · Admin ที่โอน/ตอบ) ·
    **ใบจ่ายลีดในกลุ่มจ่ายเบอร์** (Code/ADS/Account/ชื่อลูกค้า/ID LINE/ช่องทาง/รถ — ถ้าเบอร์หรือชื่อไลน์ตรง)
    ช่องที่ชีตเป็น dropdown → เติมเฉพาะค่าที่อยู่ในตัวเลือกของชีต (`dd_pick`) ไม่ตรงสักตัว = ไม่เติม
    `msgs` = ข้อความลูกค้า (เก่า→ใหม่) ที่โหลดมาแล้วสำหรับหน้าแชท (ไม่ต้อง query ซ้ำ)
    `events` = แชททั้ง 2 ฝั่ง (dict จาก `messages()`) — ใช้จับลีดรับซื้อจากข้อความของเรา/รูปที่ลูกค้าส่ง
    """
    lead = lead_of(o)
    had_contact = bool(lead.phone or lead.line_id)
    # ★ 4 ต.ค.69 — ลูกค้าจำลองก็เติมให้ (เดิมข้ามทั้งหมด → เจ้าของทดสอบด้วยลูกค้าจำลองแล้วเห็นฟอร์มว่างทุกช่อง
    #   นึกว่าระบบไม่เติมอะไรเลย) · เติมจากแชทของตัวเอง + ค่าตั้งต้นของระบบได้ · **ยกเว้นค้นใบจ่ายลีด** (ดูข้างล่าง)
    auto = dict(lead.auto or {})
    changed = []

    def put(field, value, src, over=()):
        """`over` = ที่มาที่ข้อมูลนี้แทนได้ (ข้อมูลที่ชัดกว่าแทนค่าที่ระบบใส่ไว้ก่อน) · **ค่าที่คนพิมพ์ไม่มีวันถูกแทน**"""
        value = str(value or "").strip()[:LEAD_FIELDS.get(field, 200)]
        if not value or getattr(lead, field) == value:
            return
        if auto.get(field) in over and auto.get(field) != HUMAN:
            pass
        elif getattr(lead, field) or field in auto:
            return
        setattr(lead, field, value)
        auto[field] = src
        changed.append(field)

    if msgs is None:
        events = messages(o) if events is None else events
        msgs = [m["text"] for m in events if m["dir"] == "in" and m["text"] and not m["text"].startswith("[")]
    ph = phones_in(msgs)
    if ph:
        put("phone", ph[0], "แชท")
    # ★ 19 ต.ค.69 ลูกค้า Facebook มาจากโฆษณา → ช่อง ADS = ข้อความบนการ์ดโฆษณา (ลงใบในกลุ่ม LINE) + ad id/ชื่อโฆษณา (ฐานข้อมูล)
    ad_new = False
    if is_fb(o):
        try:
            from . import fb_ads
            ch = fb_ads.apply(o, lead, auto, put)
            changed += [f for f in ch if f not in changed]
            ad_new = bool(ch)
        except Exception:
            pass
    # รถที่ลูกค้าถาม: ข้อความแรกที่บอกรุ่นชัด (ตรงตัวเลือก "CAR / สูตร") → ได้ทั้ง 2 ช่องจากข้อความเดียวกัน
    #   ไม่มีข้อความไหนบอกรุ่นชัด ("สนใจ city" · "อีซูซุ" = รุ่นไหน?) → ได้แค่ "รถลูกค้าถาม" ให้คนเลือกรุ่นเอง
    #   ★ 2 ช่องต้องมาจากข้อความเดียวกัน — ไม่งั้นได้ "รถลูกค้าถาม: Civic" คู่กับ "CAR/สูตร: Camry"
    #   ★ 4 ต.ค.69 — ต่อข้อความข้างเคียงที่เป็นเรื่องเดียวกันด้วย ("อีซูซุ" + "ปี2015-2017") ดู _car_context
    hits = [car_in(t) for t in msgs]
    clear_i = next((i for i, h in enumerate(hits) if h and h[0]), None)
    first_i = next((i for i, h in enumerate(hits) if h), None)
    unspec = dd_pick("car_model", UNSPEC_MODEL)
    if clear_i is not None:
        # "ไม่ระบุรุ่นรถ" ที่ระบบใส่ไว้ตอนลูกค้าบอกแค่ยี่ห้อ → แทนด้วยรุ่นจริงได้เมื่อลูกค้าบอกรุ่นชัด
        put("car_model", hits[clear_i][0], "แชท",
            over=("แชท", AD_SRC) if unspec and lead.car_model == unspec else (AD_SRC,))
        put("car_text", _car_context(msgs, hits, clear_i), "แชท", over=("แชท", AD_SRC))   # แทนข้อความกำกวมที่ระบบเติมไว้ได้
    elif first_i is not None:
        said = _car_context(msgs, hits, first_i)[:LEAD_FIELDS["car_text"]]
        cur = lead.car_text or ""
        if auto.get("car_text") == "แชท" and cur and cur != said and cur in said:
            # ลูกค้าพิมพ์ต่อ ("ปี2015-2017" มาทีหลัง "อีซูซุ") → เติมต่อจากข้อความเดิมที่ระบบใส่ไว้ (ไม่แตะที่คนแก้)
            lead.car_text = said
            changed.append("car_text")
        else:
            put("car_text", said, "แชท", over=(AD_SRC,))
        # ★ 7 ต.ค.69 (เจ้าของ: "รถตามสูตรไม่ผูกแชทให้") — บอกแค่ยี่ห้อ/รุ่นกว้าง ("อีซูซุ" "city") = "ไม่ระบุรุ่นรถ"
        #   ไม่เดารุ่น: วัดจริง ส.ค.–ต.ค. ลูกค้าพิมพ์ "city" แอดมินเลือก 5 ประตู 37% · 4 ประตู 20% · ไม่ระบุรุ่นรถ 12%
        #   "civic" → FC แค่ 49% · อีซูซุ → D Max 6 จาก 14 — ไม่มีรุ่นไหนเกินครึ่งชัด เดาผิดแย่กว่าบอกว่ายังไม่รู้
        if unspec:
            put("car_model", unspec, "แชท")
    # ★ 19 ต.ค.69 ลูกค้าทักจากโฆษณา Facebook แล้วไม่ได้พิมพ์ชื่อรุ่นเอง ("สีดำมีไหม") → รุ่นจากข้อความต้อนรับของเพจ
    #   (เคสจริง NLD10-9682: เพจทัก "สนใจ Yaris ativ มีให้เลือกมากกว่า 10 คัน" ลูกค้าตอบ "สีดำมีไหม") · ดูครั้งเดียวต่อแชท
    #   รุ่นจากชื่อโฆษณาก่อน ("Yaris Ativ จว6456" · การ์ดโฆษณาในห้องแชท) แล้วค่อยข้อความต้อนรับ · การ์ดใหม่ = ดูใหม่
    if first_i is None and not lead.car_text and (AD_KEY not in auto or ad_new) and is_fb(o):
        ad = ""
        info = auto.get("_ad") or {}
        for t in (info.get("ad_name"), info.get("subtitle"), info.get("title")):
            h = car_in(t or "")
            if h and h[0] and h[0] != UNSPEC_MODEL:
                ad = h[0]
                break
        ad = ad or _ad_car(o, events)
        auto[AD_KEY] = ad or ""
        changed.append(AD_KEY)
        if ad:
            put("car_model", ad, AD_SRC)
            put("car_text", ad, AD_SRC)
    # ★ 12 ต.ค.69 คำแนะนำให้คนเลือก (ไม่ทับเอง): เบอร์ใหม่ที่ลูกค้าพิมพ์ทีหลัง · รุ่นย่อยของชื่อรุ่นกว้าง ("city" → 4/5 ประตู)
    sg = dict(auto.get(SUGG_KEY) or {})
    no = auto.get(SUGG_NO_KEY) or {}
    sug_before = json.dumps(sg, sort_keys=True, ensure_ascii=False)
    newest = phones_in(list(reversed(msgs)))
    if newest and lead.phone and auto.get("phone") == "แชท" and newest[0] != lead.phone \
            and newest[0] not in (no.get("phone") or []):
        if (sg.get("phone") or {}).get("v") != newest[0]:
            sg["phone"] = {"v": newest[0], "why": "ลูกค้าพิมพ์เบอร์นี้ทีหลัง", "from": lead.phone,
                           "at": timezone.now().isoformat(timespec="seconds")}
    else:
        sg.pop("phone", None)
    opts = _model_choices(msgs[first_i]) if (unspec and first_i is not None and clear_i is None) else []
    okey = "opts:" + "|".join(opts)
    if opts and lead.car_model == unspec and auto.get("car_model") == "แชท" and okey not in (no.get("car_model") or []):
        sg.setdefault("car_model", {"opts": opts, "why": _car_context(msgs, hits, first_i), "from": unspec,
                                    "at": timezone.now().isoformat(timespec="seconds")})
    else:
        sg.pop("car_model", None)
    if json.dumps(sg, sort_keys=True, ensure_ascii=False) != sug_before:
        if sg:
            auto[SUGG_KEY] = sg
        else:
            auto.pop(SUGG_KEY, None)
        changed.append(SUGG_KEY)
    # ค่าเก่าที่ระบบเติมทั้งประโยค (ก่อนมีตัวตัดคำ) → ตัดให้เหลือรุ่น+สเปก · ที่คน/ใบจ่ายลีดใส่ไม่แตะ
    if auto.get("car_text") == "แชท" and lead.car_text:
        tidy = _dedupe_words(car_phrase(lead.car_text))[:LEAD_FIELDS["car_text"]]
        if tidy and tidy != lead.car_text:
            lead.car_text = tidy
            changed.append("car_text")

    # ใบจ่ายลีดที่แอดมินโพสต์ไว้แล้ว — หาซ้ำได้ทุก 30 นาที (ไม่ยิง query ทุกครั้งที่เปิดแชท)
    now = timezone.now()
    last = auto.get("_slip_at") or ""
    try:
        from datetime import datetime as _dt
        stale = (not last) or (now - _dt.fromisoformat(last)) > timedelta(minutes=slip_min or _SLIP_EVERY_MIN)
    except Exception:
        stale = True
    # ลูกค้าจำลอง "ไม่ค้นใบจ่ายลีด" — เบอร์ที่พิมพ์ทดสอบอาจไปตรงใบของลูกค้าจริง แล้วดึงชื่อ/ID LINE ของจริงมาปนในข้อมูลทดสอบ
    if not lead.code and stale and not is_sim_row(o):
        auto["_slip_at"] = now.isoformat()
        changed.append("_slip_at")
        # ชื่อไลน์ใช้หาใบจ่ายลีดได้เฉพาะลูกค้า LINE (ใบเขียน "ชื่อไลน์ :") · ลูกค้า FB หาด้วยเบอร์อย่างเดียว
        hit = find_slip(lead.phone or (ph[0] if ph else ""), "" if is_fb(o) else o.profile.display_name)
        if not hit and lead.line_id:
            # ★ 18 ต.ค.69 ลูกค้าเพจส่วนใหญ่ไม่ให้เบอร์ ให้ ID LINE → แอดมินจับคู่ใบด้วย ID LINE
            #   (วัดจริง: แชทที่จ่ายแล้ว 90 ราย ตัวจับเดิมรู้แค่ 3) · ย้อนเฉพาะรอบที่คุยกันอยู่
            from . import leadmatch as LM
            hit = LM.slip_by_lid(lead.line_id, since=(o.last_in_at or now) - timedelta(days=SHEET_MATCH_DAYS))
        if hit:
            d, g = hit
            for f, k in (("code", "lead_code"), ("ads", "ads"), ("account", "account"),
                         ("customer_name", "name"), ("line_id", "line_id"), ("channel", "channel"),
                         ("car_text", "car"), ("live", "live"), ("more", "more")):
                v = d.get(k, "")
                if f in DD_COLS:               # ช่องที่มี dropdown → ใช้ชื่อตามตัวเลือกในชีต ถ้าตรงกัน
                    v = dd_pick(f, v) or v
                # ใบจ่ายลีด = ข้อมูลจากคน → แทน "ค่าตั้งต้นของระบบ" ได้ (ช่องทาง LINE@ → TikTok ตามใบ)
                #   แต่ไม่แทนสิ่งที่คนพิมพ์ในหน้านี้ และไม่แทนสิ่งที่จับได้จากแชท
                put(f, v, "ใบจ่ายลีด", over=(SYSTEM,))
            # "ไลฟ์" ในใบ = คอลัมน์ "ทีมไลฟ์" ของชีต ("live sale" → "Live Sale") — ตรงตัวเลือกเท่านั้น ไม่เดา
            lt = dd_pick("live_team", d.get("live", ""))
            if lt:
                put("live_team", lt, "ใบจ่ายลีด", over=(SYSTEM,))
            if d.get("phone"):
                put("phone", (phones_in([d["phone"]]) or [d["phone"]])[0], "ใบจ่ายลีด")
            # จ่ายให้ใคร = คนที่ถูกแท็กท้ายใบ (ชื่อ LINE คำแรก → ชื่อเล่นในทะเบียน) · ใครโพสต์ใบ = แอดมินที่จ่าย
            auto["_slip"] = {"at": _iso(g.sent_at), "group": g.group_name or "", "tag": d.get("assigned", ""),
                             "seller": tag_nick(d.get("assigned", "")), "by": _poster(g)}
        elif "code" not in auto and (sh := (sheet_match(lead.phone or (ph[0] if ph else ""), o.last_in_at,
                                                        chat_lead_pk=lead.pk)
                                            or _sheet_lid(lead, o))):
            # ★ 11 ต.ค.69 ไม่มีใบในกลุ่ม แต่เบอร์นี้ได้เลขในชีตลีดแล้วในรอบที่คุยกันอยู่ = จ่ายนอกระบบไปแล้ว
            #   (ช่อง code ที่คนเคยแก้/ลบเอง = "คน" → ไม่เติมกลับ)
            put("code", sh["code"], "ชีตลีด")
            if lead.code == sh["code"]:
                auto[SHEET_KEY] = sh
                changed.append(SHEET_KEY)
        elif BUY_KEY not in auto:
            # ไม่มีใบจ่ายลีดขาย → ลูกค้าอาจ "อยากขายรถให้เรา" แล้วถูกส่งเข้ากลุ่มเคสHOT ของจัดซื้อแทน
            #   ข้อมูลในใบเป็นรถของลูกค้า (รุ่น/ทะเบียน/เลขไมล์) ไม่ใช่รถที่เขาจะซื้อ → ไม่เอามาเติมช่องรถของฟอร์ม
            bh = find_buy_slip(lead.phone or (ph[0] if ph else ""), cust(o).display_name or "", fb=is_fb(o))
            if bh:
                auto[BUY_KEY] = buy_mark(*bh)
                changed.append(BUY_KEY)
                d = bh[0]
                if d.get("phone"):
                    put("phone", (phones_in([d["phone"]]) or [d["phone"]])[0], "ใบเคสรับซื้อ")
        # ★ 18 ต.ค.69 ใบที่ตรงแค่ "ชื่อ" = อาจจ่ายแล้ว (ชื่อซ้ำกันได้) → ไม่ตัดสินเอง แค่บอกแอดมิน + ระบบจ่ายวนข้าม
        mh = None
        if not lead.code and BUY_KEY not in auto:
            try:
                from . import leadmatch as LM
                mh = LM.name_hint(o, lead, since=(o.last_in_at or now) - timedelta(days=SHEET_MATCH_DAYS))
            except Exception:
                mh = auto.get(MAYBE_KEY)
        if mh != auto.get(MAYBE_KEY):
            if mh:
                auto[MAYBE_KEY] = mh
            else:
                auto.pop(MAYBE_KEY, None)
            changed.append(MAYBE_KEY)

    def stale_sys(field) -> tuple:
        """ค่าที่ระบบเคยใส่ไว้แต่ "ไม่อยู่ในตัวเลือกของชีต" (เช่น "LINE OA" ก่อนมี dropdown) → ยอมให้แก้ให้ตรงชีต"""
        v = getattr(lead, field)
        return (SYSTEM,) if auto.get(field) == SYSTEM and v and not dd_pick(field, v) else ()

    # ช่องทาง = ลูกค้าทักเข้า LINE OA → "LINE@" ตาม dropdown ของชีต
    #   ลูกค้า FB → "ชื่อ Account" = ชื่อใน Facebook + ★ 20 ต.ค.69 ช่องทาง = ตัวเลือก "เพจ…" ของชีตตามเพจที่ทักเข้ามา (`_fb_channel`)
    if is_fb(o):
        put("account", o.fb_profile.display_name, SYSTEM)
        fch = _fb_channel(o.fb_profile.channel)
        if fch:
            put("channel", fch, SYSTEM, over=stale_sys("channel"))
    else:
        put("channel", _line_channel(), SYSTEM, over=stale_sys("channel"))
    # สาขา = สาขาที่ลีดของเซลล์คนนี้ไปจริงในชีตเดือนล่าสุด (ยังไม่มีเจ้าของ = สาขาที่ลีดเกือบทั้งหมดไป)
    #   เชื่อเฉพาะตอนชัด (สาขาเดียว ≥ 90%) — ไม่ชัด = ปล่อยว่างให้คนเลือก · วัดจริง ส.ค.–ต.ค.69: ชลบุรี 100%
    dd = dropdowns()
    br = (dd.get("branchBySeller") or {}).get(o.owner.nickname, "") if o.owner_id else ""
    br = dd_pick("branch", br or dd.get("branchTop") or "")
    if br:
        put("branch", br, SYSTEM, over=(SYSTEM,) if o.owner_id else stale_sys("branch"))
    # Admin = คนที่โอนลูกค้าให้เซลล์ล่าสุด (ไม่มี = คนแรกที่ตอบลูกค้าที่ไม่ใช่เจ้าของ)
    #   ต้องเป็นชื่อในตัวเลือก "Admin" ของชีตเท่านั้น (กวาง/หมิว/เฟิร์น/…) — เจ้าของ/เซลล์ที่ตอบเองไม่ใช่ Admin ของลีด
    adm = (ChatOwnerLog.objects.filter(chat=o, action=ChatOwnerLog.ASSIGN).exclude(by_name="")
           .order_by("-at", "-id").values_list("by_name", flat=True).first())
    if not adm:
        if is_fb(o):
            qs = FbChat.objects.filter(thread_id=o.fb_profile.thread_id or "-", direction=FbChat.OUT).exclude(sent_by_name="")
        else:
            qs = GroupChat.objects.filter(sender_id=o.profile.user_id, direction=GroupChat.OUT).exclude(sent_by_name="")
        if o.owner_id:
            qs = qs.exclude(sent_by_name=o.owner.nickname)
        adm = qs.order_by("sent_at", "id").values_list("sent_by_name", flat=True).first()
    #   ★ ตรงตัวเลือกเป๊ะ (ตัวพิมพ์ด้วย) ไม่ใช้ dd_pick — บัญชีแอดมินระบบ (ชื่อเล่น "admin") ต้องไม่กลายเป็นตัวเลือก
    #     "ADMIN" ของชีต ซึ่งเป็นคนละความหมาย · ชื่อเล่นคนจริงเป็นภาษาไทย ตรงเป๊ะอยู่แล้ว ไม่เสียอะไร
    adm = (adm or "").strip()
    adm = adm if adm and not adm.startswith(TEST_PREFIX) and adm in dd_options("admin_name") else ""
    if adm:
        put("admin_name", adm, SYSTEM, over=stale_sys("admin_name"))

    # ★ 7 ต.ค.69 — อาชีพ/รายได้/อายุงาน/ประวัติผ่อน/ประเภทลูกค้า/สถานะลูกค้า จับ keyword จากแชท + โน้ตในฟอร์ม
    changed += apply_keywords(lead, auto, msgs, _lead_notes(lead))
    # ★ 11 ต.ค.69 ลีดรับซื้อรถ vs ลีดขายรถ (+ มีรถเทิร์น) — คนตั้งไว้แล้วไม่เดาทับ
    if apply_deal_kind(lead, auto, msgs, events=deal_events(events)):
        changed.append(BUYLEAD_KEY)
    # type = ตามตัวหน้าของเลขลีด (เลขจากใบจ่ายลีด/คนกรอก) — NLD=Moderate · WLD=Hot · HLD=Very Hot · BLD · TLD
    #   ปุ่มจ่ายเบอร์เติมให้อยู่แล้ว · ตรงนี้สำหรับเลขที่มาทางอื่น (ใบในกลุ่ม/คนพิมพ์) · R/A นำหน้า = type เดียวกับตัวหน้า
    if lead.code and not lead.lead_type:
        cm = _CODE_RE.match(re.sub(r"\s+|/\d+$", "", lead.code))
        if cm:
            put("lead_type", dd_pick("lead_type", dict(CODE_BASES).get(cm.group(1).lstrip("R").lstrip("A"), "")), SYSTEM)

    if not had_contact and _stamp_contact(o, lead, auto):
        changed.append(CONTACT_AT_KEY)
    if changed:
        lead.auto = auto
        lead.save()
    return lead


def lead_json(o, lead=None) -> dict:
    """ข้อมูลลีดสำหรับฟอร์ม + ช่องที่ระบบคำนวณเอง (ไม่เก็บซ้ำ)"""
    lead = lead or lead_of(o)
    p = cust(o)
    if is_fb(o):
        first_out = (FbChat.objects.filter(thread_id=p.thread_id or "-", direction=FbChat.OUT)
                     .order_by("sent_at").values_list("sent_at", flat=True).first())
    else:
        first_out = (GroupChat.objects.filter(sender_id=p.user_id, direction=GroupChat.OUT)
                     .order_by("sent_at").values_list("sent_at", flat=True).first())
    contact = o.first_reply_at or first_out
    out = {k: getattr(lead, k) or "" for k in LEAD_FIELDS}
    out.update({
        "tags": list(lead.tags or []),
        "auto": {k: v for k, v in (lead.auto or {}).items() if not k.startswith("_")},
        "autoWhy": dict((lead.auto or {}).get(KW_KEY) or {}),   # ช่องที่จับจาก keyword → จับจากคำไหน (โชว์ในป้าย)
        # ★ 12 ต.ค.69 ค่าใหม่ที่ลูกค้าพูดทีหลัง รอคนตัดสิน {ช่อง: {v | opts, why, from, at}} (ช่องที่ยังเป็นค่าที่ระบบเติม)
        "sugg": {f: s for f, s in ((lead.auto or {}).get(SUGG_KEY) or {}).items()
                 if (lead.auto or {}).get(f) != HUMAN},
        "slip": (lead.auto or {}).get("_slip") or None,
        # ★ 19 ต.ค.69 ลูกค้ามาจากโฆษณา Facebook ตัวไหน (ป้ายช่อง ADS) — ไม่มี LINE/PSID ในนี้
        "ad": ({k: v for k, v in ((lead.auto or {}).get("_ad") or {}).items()
                if k in ("title", "subtitle", "ad_id", "ad_name", "adset_name", "campaign_name", "how", "ad_ids")}
               if (lead.auto or {}).get("_ad") else None),
        "sheet": (lead.auto or {}).get(SHEET_KEY) or None,     # ★ 11 ต.ค.69 เลขที่ได้จากชีตลีด (จ่ายนอกระบบ)
        # ช่องอัตโนมัติ (คำนวณจากระบบ ไม่ให้แก้มือ — แก้แล้วจะไม่ตรงกับของจริง)
        "leadAt": _iso(p.first_seen),
        "seller": o.owner.nickname if o.owner_id else "",
        "contactAt": _iso(contact),
        "updates": ChatOwnerLog.objects.filter(chat=o, action=ChatOwnerLog.REPLY).count(),
        "lastUpdate": _iso(o.last_out_at),
        "lineName": p.display_name or "",
        "updatedBy": lead.updated_by or "",
        "codeDemo": bool(lead.code_demo),
        "assignedAt": _iso(lead.assigned_at),
        "assignedBy": lead.assigned_by or "",
        # ส่งใบจ่ายลีดเข้ากลุ่มจ่ายเบอร์แล้วหรือยัง ({ok, groupName, tagged, error, …} · ว่าง = ยังไม่เคยส่ง)
        "post": {k: v for k, v in (lead.post_info or {}).items() if k != "mid"} or None,
        # แอดมินกด "ไม่ต้องจ่ายเบอร์" ไว้ ({by, at}) — ไม่ใช่ลีดขาย ออกจากแท็บจ่ายเบอร์
        "noCode": (lead.auto or {}).get(NOCODE_KEY) or None,
        # ★ 11 ต.ค.69 แอดมินติ๊ก "รับ lead จากแชทนี้แล้ว" ({by, at}) → อยู่ในห้องพัก Lead · roomAuto = ไม่ต้องติ๊ก (สวิตช์)
        "park": (lead.auto or {}).get(PARK_KEY) or None,
        "roomAuto": room_auto(),
        # ส่งเข้ากลุ่มเคสHOT ของจัดซื้อแล้ว ({code, at, group, seller, by}) — ลูกค้าอยากขายรถให้เรา ไม่ใช่ลีดขาย
        "buy": (lead.auto or {}).get(BUY_KEY) or None,
        # ★ 11 ต.ค.69 ลีดรับซื้อรถ vs ลีดขายรถ — buyLead/sellLead = {by, at, why} (by "ระบบ" = จับจากแชท) · trade = มีรถเทิร์น
        "deal": deal_of(lead),
        "buyLead": (lead.auto or {}).get(BUYLEAD_KEY) or None,
        "sellLead": (lead.auto or {}).get(SELLLEAD_KEY) or None,
        "trade": (lead.auto or {}).get(TRADE_KEY) or None,
    })
    out["slipText"] = slip_text(o, lead)
    if out["deal"] == "buy" and not out["buy"]:
        out["buySlipText"] = buy_slip_text(o, lead)
    return out


def slip_fields(o, lead) -> dict:
    """ช่องของใบจ่ายลีด (ใช้ทั้งปุ่มคัดลอกและตอนส่งเข้ากลุ่ม) · ช่องทาง/ไลฟ์ = คำตาม dropdown ของชีตจ่ายเบอร์
    · ไลฟ์ในใบ = ช่อง "ทีมไลฟ์" (คอลัมน์เดียวกันในชีต) — ช่อง `live` เดิมใช้เฉพาะตอนยังไม่ได้เลือกทีมไลฟ์"""
    p, fb = cust(o), is_fb(o)
    return {"code": lead.code, "ads": lead.ads, "account": lead.account, "name": lead.customer_name,
            "line_id": lead.line_id, "line_name": "" if fb else (p.display_name or ""), "phone": lead.phone,
            "channel": dd_pick("channel", lead.channel) or lead.channel,
            "car": lead.car_text or lead.car_model,
            "live": lead.live_team or dd_pick("live_team", lead.live) or lead.live, "more": lead.more,
            # ★ 20 ต.ค.69 แบบใบใหม่มีบรรทัดข้อมูลลูกค้า — ค่าที่ระบบจับจากแชท/คนแก้ในหน้า Connect (ช่องเดียวกับชีตลีด U–X)
            "occupation": lead.occupation, "income": lead.income, "job_tenure": lead.job_tenure,
            "pay_history": lead.pay_history}


def slip_text(o, lead=None) -> str:
    """ใบจ่ายลีด (ปุ่มคัดลอก) — pattern เดียวกับที่ส่งเข้ากลุ่ม (`slippost.body`) + @เจ้าของ · อ่านกลับได้"""
    from . import slippost
    lead = lead or lead_of(o)
    lines = [slippost.with_tag(slippost.body(slip_fields(o, lead)), o.owner.nickname if o.owner_id else "")]
    if lead.code_demo:
        # เลขจากโหมดทดลองยังไม่ได้จองในชีต — กันเผลอก๊อปไปวางในกลุ่มจริงแล้วเลขชนกับของแอดมิน
        lines.insert(0, "⚠️ ทดลอง — เลขนี้ยังไม่ได้จองในชีตจริง")
    return "\n".join(lines)


def save_lead_field(o, field: str, value, by: str = ""):
    """แก้ข้อมูลลีด 1 ช่อง → (ok, ข้อความ) · ช่องที่คนแก้แล้ว ระบบจะไม่เติมทับอีก"""
    lead = lead_of(o)
    if field == "tags":
        vals = value if isinstance(value, list) else []
        tags = []
        for t in vals:
            t = str(t or "").strip()[:30]
            if t and t not in tags:
                tags.append(t)
        tags = tags[:12]
        # ★ 20 ต.ค.69 แท็กที่ระบบอัตโนมัติติดให้แล้วคนเอาออก = ไม่ติดกลับ (autotag)
        auto = dict(lead.auto or {})
        try:
            from . import autotag
            autotag.human_edit(lead, auto, tags)
        except Exception:
            pass
        lead.tags = tags
        lead.auto = auto
        lead.updated_by = (by or "")[:80]
        lead.save(update_fields=["tags", "auto", "updated_by", "updated_at"])
        return True, "บันทึกแท็กแล้ว"
    if field not in LEAD_FIELDS:
        return False, "ไม่รู้จักช่อง %s" % field
    v = str(value if value is not None else "").strip()
    if len(v) > LEAD_FIELDS[field]:
        return False, "ยาวเกินไป (ไม่เกิน %d ตัวอักษร)" % LEAD_FIELDS[field]
    if field == "phone" and v:
        ph = phones_in([v])
        if not ph:
            return False, "เบอร์โทรไม่ถูกรูปแบบ (เช่น 0812345678)"
        v = ph[0]
    setattr(lead, field, v)
    auto = dict(lead.auto or {})
    auto[field] = HUMAN
    sg = dict(auto.get(SUGG_KEY) or {})           # คนตัดสินช่องนี้แล้ว (ใช้ค่าใหม่/คงค่าเดิม/พิมพ์เอง) = ไม่มีอะไรรอยืนยัน
    if sg.pop(field, None) is not None:
        if sg:
            auto[SUGG_KEY] = sg
        else:
            auto.pop(SUGG_KEY, None)
    lead.auto = auto
    lead.updated_by = (by or "")[:80]
    lead.save(update_fields=[field, "auto", "updated_by", "updated_at"])
    return True, "บันทึกแล้ว"


# ─────────────────────────────────────────────────────────────
#  เลขลีด (Code) + ปุ่ม "จ่ายเบอร์" — โหมดทดลอง (4 ต.ค.69 · เจ้าของสั่ง: เก็บใน Postgres อย่างเดียว ไม่ลงชีต)
#
#  รูปแบบจริง (วัดจากใบจ่ายลีด + ชีตลีด 18,041 แถว): **<ตัวหน้า><เดือน>-<เลขรัน>** เช่น NLD10-8409
#    · ตัวหน้าตาม type ในชีต: NLD=Moderate · WLD=Hot · HLD=Very Hot · BLD=BLD · TLD=TikTok (TALD=TikTokAds)
#    · เติมหน้า **A** = ลีดของแอดมิน (ANLD/AWLD/AHLD) · **R** = เคสรีเจ็ค (RNLD/RTLD)
#    · **เลขรันใช้ร่วมกันทุกตัวหน้า** (8395 TLD → 8396 NLD → 8397 NLD …) · เดือน = เดือนที่จ่าย
# ─────────────────────────────────────────────────────────────
# ★ 17 ต.ค.69 เพิ่ม LD (Moderate · ให้ข้อมูลแต่เครดิตอ่อน) — ตัวหน้าอัตโนมัติดู checkout/lead_code.py
CODE_BASES = [("NLD", "Moderate"), ("LD", "Moderate"), ("WLD", "Hot"), ("HLD", "Very Hot"), ("BLD", "BLD"),
              ("TLD", "TLD"), ("TALD", "TLD")]
_TYPE_BASE = {"moderate": "NLD", "merhot": "NLD", "hot": "WLD", "very hot": "HLD", "bld": "BLD",
              "tld": "TLD", "tld / hot": "TLD"}
# ★ 10 ต.ค.69 รับ "/n" ท้ายเลข — ส่งต่อไม้ 2 ในห้อง REJECT ใช้ R + เลขเดิม + /1 (leadflow.fwd_code)
_CODE_RE = re.compile(r"^(R?A?(?:NLD|WLD|HLD|BLD|TLD|TALD|LD))(\d{1,2})-(\d{3,6})(?:/\d{1,2})?$")
_ANY_CODE = re.compile(r"^([A-Za-z]+)(\d{0,2})-?(\d{3,6})$")
NOCODE_KEY = "_nocode"            # ChatLead.auto[...] = แอดมินกด "ไม่ต้องจ่ายเบอร์" (ไม่ใช่ลีดขาย)


def to_code(qs):
    """แท็บ **"จ่ายเบอร์"** ของแอดมิน — ลูกค้าที่ **คุยในระบบแล้ว แต่ยังไม่มีเลขลีด** (4 ต.ค.69)

    "คุยในระบบแล้ว" = กำลังรอคำตอบ · มีเซลล์ดูแล · หรือมีประวัติใน Connect (ตอบ/รับ/โอน/เลยเวลา)
    → ลูกค้าเก่าที่ทักมาก่อนเปิด Connect แล้วไม่ได้ทักกลับมาอีก **ไม่นับ** (จ่ายเบอร์นอกระบบไปแล้ว ·
    วัดจริงตอนเปิด: 381 จาก 391 คนเป็นแบบนี้ ถ้านับด้วยแท็บนี้จะใช้งานไม่ได้)
    ไม่นับคนที่แอดมินกด "ไม่ต้องจ่ายเบอร์" ไว้ (`NOCODE_KEY`)

    ★ 4 ต.ค.69 เจ้าของสั่ง *"ลูกค้าทุกคนไม่ได้เข้าห้องพักลีด ต้องเป็นลูกค้าที่ให้เบอร์หรือช่องทางติดต่อแล้วเท่านั้น"*
      → ต้องมี **เบอร์โทร หรือ ID LINE** ในข้อมูลลีด (ระบบจับจากแชทให้เอง `capture_contact` · หรือแอดมินพิมพ์เอง)
      ลูกค้าที่ยังแค่ถามรถ (แอดมินยังขอเบอร์อยู่) อยู่ในคิว "รอรับ"/"ทั้งหมด" ตามเดิม แต่ยังไม่เข้าห้องพัก

    ★ 11 ต.ค.69 เจ้าของสั่ง *"เอามาจากกลุ่ม admin เก็บ lead ก่อน เพราะข้อมูลยังไม่ครบ ยังไม่พร้อมทำออโต้ 100
      อย่างน้อยก็รอคนไปติ๊กว่าไปรับ lead มาจากแชทนี้แล้ว"* → ค่าตั้งต้น (`room_chat_auto` ปิด) = **เฉพาะแชทที่
      แอดมินติ๊ก "รับ lead จากแชทนี้แล้ว"** (`PARK_KEY`) · ระบบยังจับเบอร์/ID ลงข้อมูลลีดให้เหมือนเดิม แค่ไม่ส่งเข้าห้องเอง
      · ติ๊กแล้ว = คนตัดสินแล้ว ไม่ต้องรอเบอร์/ประวัติคุย · เปิดสวิตช์ = กติกาเดิม (ให้เบอร์/ID แล้วเข้าห้องเอง)

    ★ 18 ต.ค.69 กลับมาเข้าเอง (`room_chat_auto` เปิดเป็นค่าตั้งต้น · เจ้าของ "เราส่งไปเองเลยดีกว่า")
    """
    tid = _test_ids()
    if tid:                                   # ★ 19 ต.ค.69 แชทของบัญชีทดสอบ — ใบไปกลุ่มทดสอบ ไม่ขึ้นห้องพัก Lead จริง
        qs = qs.exclude(pk__in=tid)
    if not room_auto():
        return qs.filter(lead__auto__has_key=PARK_KEY).filter(_no_code_q()).filter(_sell_q())
    return qs.filter(_engaged_q()).filter(_no_code_q()).filter(_contact_q()).filter(_sell_q())


def _test_ids() -> list:
    """แชทของบัญชีทดสอบเก็บลีด (`autolead.test_chats`) · อ่านไม่ได้ = ไม่มี"""
    try:
        from .autolead import test_chat_ids
        return test_chat_ids()
    except Exception:
        return []


def _no_code_q():
    """ยังไม่มีเลขลีด · แอดมินไม่ได้กด "ไม่ต้องจ่ายเบอร์" · ยังไม่ได้ส่งใบเคสรับซื้อเข้ากลุ่มจัดซื้อ"""
    return Q(lead__code="") & ~Q(lead__auto__has_key=NOCODE_KEY) & ~Q(lead__auto__has_key=BUY_KEY)


def _sell_q():
    """ลีดขายรถ = ไม่ได้ถูกจัดเป็นลีดรับซื้อ (`BUYLEAD_KEY`) — ห้องพัก Lead / กลุ่มรอกดรับ / Run Auto ใช้ตัวนี้"""
    return ~Q(lead__auto__has_key=BUYLEAD_KEY)


def _engaged_q():
    """คุยในระบบแล้ว = รอคำตอบอยู่ · มีเซลล์ดูแล · หรือมีประวัติใน Connect (ลูกค้าเก่าก่อนเปิด Connect ไม่นับ)"""
    return (Q(awaiting_since__isnull=False) | Q(owner__isnull=False)
            | Exists(ChatOwnerLog.objects.filter(chat=OuterRef("pk"))))


def _contact_q():
    return Q(lead__phone__gt="") | Q(lead__line_id__gt="")


PARK_KEY = "_park"                # ChatLead.auto[...] = แอดมินติ๊ก "รับ lead จากแชทนี้แล้ว" ({by, at}) → เข้าห้องพัก Lead
PENDING_DAYS = 3                  # กลุ่ม "รอกดรับ" — ลูกค้าทักภายในกี่วัน (เก่ากว่านี้ยังมีป้ายในรายชื่อ แต่ไม่ขึ้นห้องพัก)


def pending_park(qs, days: int = PENDING_DAYS):
    """กลุ่ม **"ให้เบอร์แล้ว · รอแอดมินกดรับ"** บนสุดของห้องพัก Lead (★ 11 ต.ค.69 ค่ำ)

    เจ้าของ *"ลูกค้าให้เบอร์แล้วไม่เด่นเลย เอางี้เด้งไปหน้าพักหลีดรอแอดมินกดรับละจ่ายต่อ"* — เดิมโหมดติ๊ก
    แชทที่ให้เบอร์/ID LINE แล้วมีแค่ป้ายเทาในรายชื่อแชท ต้องเปิดแชทไปกดเอง ไม่มีใครเห็น
    = เงื่อนไขชุดเดียวกับกติกาเข้าเอง (คุยในระบบแล้ว + ยังไม่มีเลข + มีเบอร์/ID LINE) ที่ **ยังไม่ติ๊กรับ lead**
    · กด "รับ lead" (`mark_park`) → ย้ายไปรายการรอจ่ายเบอร์ข้างล่าง · เปิดสวิตช์เข้าเอง (`room_auto`) = ว่างเสมอ (อยู่ใน to_code แล้ว)
    · เฉพาะลูกค้าที่ทักภายใน `days` วัน — แชทเก่าที่ไม่มีใครกดรับ ไม่กองค้างบนสุดตลอดไป (ทักกลับมาเมื่อไหร่ก็ขึ้นใหม่)
    """
    if room_auto():
        return qs.none()
    if _test_ids():
        qs = qs.exclude(pk__in=_test_ids())
    qs = (qs.filter(_engaged_q()).filter(_no_code_q()).filter(_contact_q()).filter(_sell_q())
          .filter(~Q(lead__auto__has_key=PARK_KEY)))
    if days:
        qs = qs.filter(last_in_at__gte=timezone.now() - timedelta(days=days))
    return qs


def pending_one(o, lead) -> bool:
    """แชทนี้อยู่ในกลุ่ม "รอกดรับ" ไหม (แถวเดียว · ป้ายในรายชื่อ/หัวแชท) — ตรงกับ `pending_park`"""
    if not lead or room_auto() or (lead.code or "").strip() or not (lead.phone or lead.line_id) or o.pk in _test_ids():
        return False
    auto = lead.auto or {}
    if NOCODE_KEY in auto or BUY_KEY in auto or PARK_KEY in auto or BUYLEAD_KEY in auto:
        return False
    if not o.last_in_at or o.last_in_at < timezone.now() - timedelta(days=PENDING_DAYS):
        return False
    return bool(o.awaiting_since or o.owner_id or ChatOwnerLog.objects.filter(chat=o).exists())


def in_room(lead) -> bool:
    """แชทนี้อยู่ในห้องพัก Lead ไหม (ป้ายในรายชื่อ · ไม่เช็ค "คุยในระบบแล้ว" แบบ `to_code` — ใช้บอกคน ไม่ใช่นับ)"""
    if not lead or (lead.code or "").strip() or lead.chat_id in _test_ids():
        return False
    auto = lead.auto or {}
    if NOCODE_KEY in auto or BUY_KEY in auto or BUYLEAD_KEY in auto:
        return False
    return PARK_KEY in auto or (room_auto() and bool(lead.phone or lead.line_id))


def mark_park(o, on: bool, by: str = ""):
    """ติ๊ก **"รับ lead จากแชทนี้แล้ว"** (แอดมิน) → (ok, ข้อความ) — ส่งแชทนี้เข้าห้องพัก Lead · `on=False` = เอาออก
    เก็บใน `ChatLead.auto["_park"]` = {by, at} (ไม่ต้อง migrate) · ติ๊ก = ยืนยันว่าเป็นลีดขาย → ล้างป้าย "ไม่ต้องจ่ายเบอร์" ด้วย"""
    lead = lead_of(o)
    if (lead.code or "").strip():
        return False, "ลูกค้ารายนี้มีเลขลีด %s แล้ว" % lead.code
    auto = dict(lead.auto or {})
    if on:
        if BUY_KEY in auto:
            return False, "ลูกค้ารายนี้ส่งจัดซื้อแล้ว (%s) — ไม่ใช่ลีดขาย" % ((auto.get(BUY_KEY) or {}).get("code") or "เคสรับซื้อ")
        if BUYLEAD_KEY in auto:
            return False, "ลูกค้ารายนี้เป็นลีดรับซื้อรถ (อยากขายรถให้เรา) — ถ้าจะซื้อรถเรา กด \"เป็นลีดขายรถ\" ก่อน"
        auto[PARK_KEY] = {"by": (by or "")[:80], "at": _iso(timezone.now())}
        auto.pop(NOCODE_KEY, None)
        msg = "ส่งเข้าห้องพัก Lead แล้ว — รอจ่ายเบอร์"
        if not (lead.phone or lead.line_id):
            msg += " (ยังไม่มีเบอร์/ID LINE ในข้อมูลลีด)"
    else:
        if PARK_KEY not in auto:
            return True, "แชทนี้ไม่ได้อยู่ในห้องพัก Lead อยู่แล้ว"
        auto.pop(PARK_KEY, None)
        msg = "เอาออกจากห้องพัก Lead แล้ว"
    lead.auto = auto
    lead.updated_by = (by or "")[:80]
    lead.save(update_fields=["auto", "updated_by", "updated_at"])
    return True, msg


# ── ลีดรับซื้อรถ vs ลีดขายรถ (★ 11 ต.ค.69 เจ้าของ "มันจะมี lead รับซื้อรถกับ lead ขายรถด้วยนะ แยกไว้ด้วย") ──
#   ลีดขาย  = ลูกค้าอยากซื้อรถเรา → ห้องพัก Lead → จ่ายเบอร์ (NLD…) ให้เซลล์ (ของเดิมทั้งหมด)
#   ลีดรับซื้อ = ลูกค้าอยากขายรถให้เรา → แท็บ "รับซื้อรถ" → แอดมินโพสต์ใบเคสรับซื้อ (โค้ด : OC-…) ในกลุ่มเคสHOT ของจัดซื้อ
#     → ระบบเจอใบในกลุ่ม (`find_buy_slip` · `BUY_KEY`) = ส่งจัดซื้อแล้ว ออกจากแท็บเอง
#   จับจากแชทด้วย `lead_keywords.deal_kind` (ไม่ใช้ AI) · คนตั้งเองได้ทั้ง 2 ทาง และระบบไม่เดาทับสิ่งที่คนตั้ง
#   ★ รถเทิร์น = ลีดขาย (เขาจะซื้อรถเรา) — ติดป้าย "มีรถเทิร์น" ให้เซลล์รู้ (`TRADE_KEY`)
BUYLEAD_KEY = "_buylead"          # auto[...] = {by, at, why} · by = "ระบบ" (จับจากแชท) หรือชื่อคนที่ตั้ง
SELLLEAD_KEY = "_selllead"        # auto[...] = {by, at} · คนยืนยันว่าเป็นลีดขาย → ระบบไม่จัดเป็นรับซื้ออีก
TRADE_KEY = "_trade"              # auto[...] = {why, at} · ลูกค้ามีรถเทิร์น (ยังเป็นลีดขาย)
BUY_ROOM_DAYS = 14                # แท็บ "รับซื้อรถ" — ลูกค้าทักภายในกี่วัน (เก่ากว่านี้ยังมีป้ายในรายชื่อแชท)


def deal_of(lead) -> str:
    """"buy" = ลีดรับซื้อรถ (จับได้/คนตั้ง/ส่งจัดซื้อแล้ว) · "sell" = ลีดขายรถ (ค่าตั้งต้น)"""
    auto = (lead.auto or {}) if lead else {}
    return "buy" if (BUY_KEY in auto or BUYLEAD_KEY in auto) else "sell"


def deal_events(msgs) -> list:
    """แชท (dict จาก `messages()`) → ไทม์ไลน์ให้ `lead_keywords.deal_kind` นับรูปที่ลูกค้าส่งหลังเราขอ"""
    return [(m.get("dir") or "in", m.get("text") or "", (m.get("type") or "") in ("image", "video"))
            for m in (msgs or []) if isinstance(m, dict)]


def apply_deal_kind(lead, auto: dict, texts_in, texts_out=(), events=None) -> bool:
    """จับว่าเป็นลีดรับซื้อ/มีรถเทิร์นจากแชท → แก้ `auto` (ยังไม่ save) · คืนว่าเปลี่ยนไหม
    · มีเลขลีดขายแล้ว / คนยืนยันว่าเป็นลีดขาย / แอดมินติ๊กรับ lead (ห้องพักขาย) = ไม่จัดเป็นรับซื้อ
    · ระบบจัดเป็นรับซื้อไว้ แล้วลูกค้าพูดถึงรถเทิร์นทีหลัง = กลับเป็นลีดขาย (คนตั้งไว้ = ไม่แตะ)"""
    from . import lead_keywords as K
    r = K.deal_kind(texts_in, texts_out, events)
    changed = False
    now = _iso(timezone.now())
    if r["trade"] and TRADE_KEY not in auto:
        auto[TRADE_KEY] = {"why": r["trade"], "at": now}
        changed = True
    cur = auto.get(BUYLEAD_KEY)
    if cur and r["trade"] and (cur.get("by") or "") == SYSTEM:
        auto.pop(BUYLEAD_KEY, None)
        changed = True
    elif (r["kind"] == "buy" and not cur and not (lead.code or "").strip()
          and not any(k in auto for k in (SELLLEAD_KEY, PARK_KEY, BUY_KEY))):
        auto[BUYLEAD_KEY] = {"by": SYSTEM, "at": now, "why": r["why"]}
        changed = True
    return changed


def buy_room(qs, days: int = BUY_ROOM_DAYS):
    """แท็บ **"รับซื้อรถ"** ของห้องพัก Lead — ลีดรับซื้อที่คุยในระบบแล้ว + ให้เบอร์/ID LINE แล้ว + ยังไม่ส่งจัดซื้อ
    ไม่ต้องให้แอดมินกดรับก่อน (ไม่มีการจ่ายให้เซลล์ในระบบ — แอดมินคัดลอกใบไปโพสต์ในกลุ่มเคสHOT เอง)"""
    qs = (qs.filter(lead__auto__has_key=BUYLEAD_KEY).filter(_engaged_q()).filter(_no_code_q())
          .filter(_contact_q()))
    if days:
        qs = qs.filter(last_in_at__gte=timezone.now() - timedelta(days=days))
    return qs


def buy_one(lead) -> bool:
    """แชทนี้อยู่ในแท็บรับซื้อรถไหม (ป้ายในรายชื่อ · ไม่เช็คประวัติคุย/วันที่ — ใช้บอกคน ไม่ใช่นับ)"""
    if not lead or (lead.code or "").strip():
        return False
    auto = lead.auto or {}
    return BUYLEAD_KEY in auto and NOCODE_KEY not in auto and BUY_KEY not in auto and bool(lead.phone or lead.line_id)


def set_deal_kind(o, kind: str, by: str = ""):
    """แอดมินตั้งประเภทลีดเอง → (ok, ข้อความ) · `kind` = "buy" (ลีดรับซื้อรถ) / "sell" (ลีดขายรถ)
    ตั้งแล้วระบบไม่เดาทับ · เป็นลีดรับซื้อ = ออกจากห้องพักขาย (ล้างติ๊กรับ lead) · เป็นลีดขาย = ออกจากแท็บรับซื้อ"""
    if kind not in ("buy", "sell"):
        return False, "ไม่รู้จักประเภทลีด %s" % kind
    lead = lead_of(o)
    auto = dict(lead.auto or {})
    now = _iso(timezone.now())
    who = (by or "")[:80]
    if kind == "buy":
        if (lead.code or "").strip():
            return False, "ลูกค้ารายนี้ได้เลขลีดขาย %s แล้ว — เป็นลีดขายรถ" % lead.code
        auto[BUYLEAD_KEY] = {"by": who or "แอดมิน", "at": now, "why": "คนตั้ง"}
        auto.pop(SELLLEAD_KEY, None)
        auto.pop(PARK_KEY, None)
        auto.pop(NOCODE_KEY, None)
        msg = "ตั้งเป็นลีดรับซื้อรถแล้ว — อยู่แท็บ \"รับซื้อรถ\" ของห้องพัก Lead"
        if not (lead.phone or lead.line_id):
            msg += " (ยังไม่มีเบอร์/ID LINE ในข้อมูลลีด)"
    else:
        if BUY_KEY in auto:
            return False, "ลูกค้ารายนี้ส่งจัดซื้อแล้ว (%s)" % ((auto.get(BUY_KEY) or {}).get("code") or "เคสรับซื้อ")
        auto.pop(BUYLEAD_KEY, None)
        auto[SELLLEAD_KEY] = {"by": who or "แอดมิน", "at": now}
        msg = "ตั้งเป็นลีดขายรถแล้ว — กด \"รับ lead\" เพื่อส่งเข้าห้องพักรอจ่ายเบอร์"
        if room_auto() or PARK_KEY in auto:
            msg = "ตั้งเป็นลีดขายรถแล้ว"
    lead.auto = auto
    lead.updated_by = who
    lead.save(update_fields=["auto", "updated_by", "updated_at"])
    return True, msg


def scan_deals(days: int = 30, apply: bool = False, limit: int = 3000) -> dict:
    """เก็บตก: แชทที่ลูกค้าทักภายใน `days` วัน (ก่อนมีตัวจับลีดรับซื้อ) → จัดประเภทย้อนหลัง
    ของใหม่จับตอนข้อความเข้า/เปิดแชทอยู่แล้ว · `apply=False` = ดูเฉยๆ ไม่เขียน · คืน {checked, buy, trade, already, rows}
    ไม่แตะแชทที่คนตั้งประเภทไว้แล้ว/มีเลขลีดขาย/ส่งจัดซื้อแล้ว (กติกาเดียวกับ `apply_deal_kind`)"""
    from . import lead_keywords as K
    since = timezone.now() - timedelta(days=days)
    out = {"checked": 0, "buy": 0, "trade": 0, "already": 0, "rows": []}
    qs = (ChatOwner.objects.select_related("profile", "fb_profile", "lead")
          .filter(last_in_at__gte=since).order_by(F("last_in_at").desc(nulls_last=True)))
    for o in qs[:limit]:
        if is_sim_row(o):
            continue
        out["checked"] += 1
        lead = lead_of(o, create=False)
        if lead and deal_of(lead) == "buy":
            out["already"] += 1
            continue
        ms = messages(o, limit=120)
        ins = [m["text"] for m in ms if m["dir"] == "in" and m["text"] and not m["text"].startswith("[")]
        evs = deal_events(ms)
        r = K.deal_kind(ins, (), evs)
        if not r["kind"] and not r["trade"]:
            continue
        if not apply:
            # ดูเฉยๆ: ประเมินด้วยกติกาเดียวกับตอนเขียน (สำเนา auto ไม่ save)
            probe = lead or ChatLead(chat=o)
            auto = dict(probe.auto or {})
            apply_deal_kind(probe, auto, ins, (), evs)
            got = "buy" if BUYLEAD_KEY in auto else ("trade" if TRADE_KEY in auto else "")
        else:
            lead = lead or lead_of(o)
            auto = dict(lead.auto or {})
            if apply_deal_kind(lead, auto, ins, (), evs):
                lead.auto = auto
                lead.save(update_fields=["auto", "updated_at"])
            got = "buy" if BUYLEAD_KEY in (lead.auto or {}) else ("trade" if TRADE_KEY in (lead.auto or {}) else "")
        if got:
            out[got] += 1
            out["rows"].append({"id": o.id, "kind": got, "src": "fb" if is_fb(o) else "line",
                                "why": r["why"] if got == "buy" else r["trade"]})
    return out


def last_buy_code() -> dict:
    """เลขใบเคสรับซื้อล่าสุดในกลุ่มเคสHOT (OC ใช้เลขรันร่วมกันทุกกลุ่ม · SC = เคสVERY HOT) → {"OC": "OC-7691", …}
    ไว้บอกแอดมินว่าเลขถัดไปน่าจะเป็นเท่าไหร่ · **ไม่ออกเลขให้เอง** (tradein.py กันเลขซ้ำด้วยรหัส — เลขชน = เคสหาย)"""
    from .leadgroup import parse_buycase
    gids = _buy_group_ids()
    out = {}
    if not gids:
        return out
    for t in (GroupChat.objects.filter(chat_type=GroupChat.GROUP, group_id__in=gids, text__contains="โค้ด")
              .order_by("-sent_at").values_list("text", flat=True)[:60]):
        d = parse_buycase(t or "")
        if not d:
            continue
        pre, _, num = d["case_code"].partition("-")
        try:
            n = int(num)
        except Exception:
            continue
        if n > int((out.get(pre) or "-0").partition("-")[2] or 0):
            out[pre] = d["case_code"]
    return out


def buy_slip_text(o, lead=None) -> str:
    """ใบเคสรับซื้อ (ปุ่มคัดลอก) — หน้าตาเดียวกับที่แอดมินโพสต์ในกลุ่มเคสHOT (`leadgroup.parse_buycase` อ่านกลับได้)
    เลขโค้ดเว้นว่างให้แอดมินเติมเอง · ข้อมูลรถ (รุ่น/ไมล์/ทะเบียน) เป็นรถของลูกค้า — ที่จับได้จากแชทคือ "รถที่ลูกค้าพูดถึง" """
    lead = lead or lead_of(o)
    p, fb = cust(o), is_fb(o)
    ch = "เพจ Facebook" if fb else (dd_pick("channel", lead.channel) or lead.channel or "LINE@")
    name = lead.customer_name or p.display_name or "-"
    more = []
    if lead.line_id and not lead.line_id.startswith("line.me/"):
        more.append("ID LINE %s" % lead.line_id)
    if lead.more:
        more.append(lead.more)

    def v(x):
        return str(x or "").strip() or "-"
    return "\n".join([
        "โค้ด : OC-",
        "ADS : %s" % v(lead.ads),
        "รุ่น : %s" % v(lead.car_text or lead.car_model),
        "เลขไมล์ : -",
        "ทะเบียน : -",
        "เบอร์ติดต่อ : %s" % v(lead.phone),
        "ชื่อลูกค้า : %s / %s" % (name, ch),
        "เพิ่มเติม : %s" % v(" · ".join(more)),
        "ขายเพราะ : -",
        "ราคากลางรับซื้อจากตาราง : -",
    ])


# ── ช่องทางติดต่อที่ลูกค้าให้มาในแชท (เบอร์ / ID LINE) — ตัวตัดสินว่าเข้าห้องพัก Lead หรือยัง ──
#   ID LINE: ต้องมี "ป้าย" (ไอดีไลน์ xxx · line id: xxx) **หรือ** ส่งมาเป็นคำเดียวหลังเราขอไอดี/ไลน์
#   ไม่เดาจากคำอังกฤษลอยๆ — ข้อความอย่าง "ok55" / "civic" จะกลายเป็นไอดีปลอมแล้วลีดเข้าห้องพักทั้งที่ยังไม่ได้ช่องทางติดต่อ
_LINE_ID_LABEL = re.compile(r"(?<![A-Za-z])(?:ไอดี\s*ไลน์|ไอดีไลน|ไลน์\s*ไอดี|ไลน์ไอดี|line\s*id|id\s*line|lineid|ไอดี|line|ไลน์|ไลร์)"
                            r"\s*(?:คือ|ครับ|ค่ะ|นะ)?\s*[:：=]?\s*(@?[A-Za-z0-9][A-Za-z0-9._-]{2,29})", re.I)
_ASK_ID = re.compile(r"ไอดี|ไลน์|line|\bid\b", re.I)
_BARE_ID = re.compile(r"^[@.]?[A-Za-z0-9][A-Za-z0-9._-]{2,29}$")
_NOT_ID = {"ok", "okay", "line", "id", "thanks", "thank", "yes", "no", "hello", "hi"}
# ★ 20 ต.ค.69 คำลงท้ายหลังไอดี ("somchai.k ครับ" · "Ab2468 ค่ะ") — เดิมทำให้ไม่นับเป็นไอดีเลย (เฟิร์นบ่นในกลุ่มทดสอบ)
_POLITE_END = re.compile(r"\s*(?:นะ)?(?:ครับผม|ครับพี่|ค่ะพี่|คะพี่|ครับ|คับ|ค่ะ|คะ|ค่า|จ้า|จ้ะ|จ่ะ)\s*$")
_LAUGH = re.compile(r"^(?:ok|okay|oke|55+|ha+|haha+|lol|thx|thank\w*)\d*$", re.I)


def _id_ok(tok: str, allow_phone: bool = False) -> str:
    t = (tok or "").strip().lstrip("@")
    if allow_phone and t.isdigit() and phones_in([t]):
        return t[:80]                              # "ไลน์ 0812345671" = ไอดีไลน์เป็นเบอร์ (แอดมินลงช่อง ID LINE ด้วย)
    if not t or t.isdigit() or t.lower() in _NOT_ID or not re.search(r"[A-Za-z]", t):
        return ""                                  # ตัวเลขล้วน = เบอร์ (จับอีกทาง) · ไม่มีตัวอักษรเลย = ไม่ใช่ไอดี
    return t[:80]


def _strong_id(tok: str) -> bool:
    """หน้าตาเป็นไอดีชัด (ไม่ต้องมีคำว่าไลน์/ไม่ต้องรอเราขอ) — มีตัวอักษร + (ตัวเลข หรือ . _) · ยาว ≥5 · ไม่ใช่ชื่อรถ/หัวเราะ
    ("Ab2468" · "nokky2520" · "somchai.k" · ".ploynam") — คำอังกฤษล้วนอย่าง "civic" / "mark" ไม่นับ"""
    t = (tok or "").lstrip("@")
    if len(t.lstrip(".")) < 5 or not re.search(r"[A-Za-z]", t) or _LAUGH.match(t):
        return False
    if not re.search(r"[0-9._]", t):
        return False
    if re.search(r"\d\.\d", t) and len(re.sub(r"[^A-Za-z]", "", t)) <= 3:
        return False                               # fc1.8 / 1.5e = รุ่น/เครื่องยนต์
    try:
        letters = re.sub(r"[^A-Za-z]+", " ", t).strip()      # "civic2019" → "civic" (ชื่อรุ่นติดปี)
        if car_in(letters) is not None or car_in(t) is not None or brand_in(letters):
            return False
    except Exception:
        pass
    return True


def bare_ids(text: str, asked: bool = False) -> list:
    """ไอดีไลน์ที่ลูกค้าพิมพ์ "ลอยๆ" ไม่มีป้าย → [(เริ่ม, จบ, ไอดี)]
    · ข้อความทั้งข้อความเป็นไอดี (+ คำลงท้าย) → นับเมื่อเราเพิ่งขอไอดี/ไลน์ หรือหน้าตาเป็นไอดีชัด
    · ข้อความที่มีเบอร์ + ส่วนที่หน้าตาเป็นไอดีชัด ("สมชาย / 0812345670 / Johnsmith27") → นับส่วนนั้น"""
    text = text or ""
    core = _POLITE_END.sub("", text.strip()).strip()
    if core and _BARE_ID.match(core):
        v = _id_ok(core)
        i = text.find(core)
        return [(i, i + len(core), v)] if (v and i >= 0 and (asked or _strong_id(core))) else []
    out = []
    if phones_in([text]):
        for part in re.split(r"[/\n,|]+", text):
            p = _POLITE_END.sub("", part.strip()).strip()
            if p and _BARE_ID.match(p) and _strong_id(p):
                v, i = _id_ok(p), text.find(p)
                if v and i >= 0:
                    out.append((i, i + len(p), v))
    return out


def contacts_in(msgs) -> tuple:
    """แชท (เก่า→ใหม่ · dict ที่มี dir/text) → (เบอร์ที่ลูกค้าให้, ID LINE ที่ลูกค้าให้)"""
    texts = [m.get("text") or "" for m in (msgs or []) if (m.get("dir") or "in") == "in"]
    phones = phones_in(texts)
    ids, asked = [], False
    for m in (msgs or []):
        t = (m.get("text") or "").strip()
        if (m.get("dir") or "in") == "out":
            # เราขอไอดี/ไลน์ตั้งแต่ข้อความลูกค้าครั้งก่อน → ข้อความถัดไปที่เป็นคำเดียวคือไอดี
            # ★ 20 ต.ค.69 ข้อความขาออกอื่น (การ์ดโฆษณา/ข้อความระบบของเพจ) ไม่ล้างสถานะ "เพิ่งขอ" แล้ว
            asked = asked or bool(_ASK_ID.search(t))
            continue
        for mm in _LINE_ID_LABEL.finditer(t):
            v = _id_ok(mm.group(1), allow_phone=True)
            if v and v not in ids:
                ids.append(v)
        for _s, _e, v in bare_ids(t, asked):
            if v and v not in ids:
                ids.append(v)
        # ★ 11 ต.ค.69 ลิงก์เพิ่มเพื่อน LINE ("ส่งข้อความและโทรฟรีด้วย LINE กันเถอะ https://line.me/ti/p/…")
        #   เดิมไม่นับ → ลูกค้าแชร์ LINE ด้วยปุ่มแชร์ของแอปแล้วหลุดจากห้องพัก (เจอจริงบน prod)
        from .lead_qr import line_contact
        v = line_contact(t)
        if v and v not in ids:
            ids.append(v)
        asked = False
    return phones, ids


# ── ★ 12 ต.ค.69 ไฮไลต์คำที่ระบบจับได้ในแชท (เจ้าของเลือกจากเดโม CRM "เอาแบบนี้แหละ แก้ไขเลย") ──
#   ใช้ตัวจับชุดเดิมทั้งหมด (phones_in / _LINE_ID_LABEL / car_in+car_phrase / lead_keywords) — แค่หา "ตำแหน่ง"
#   ส่งเป็น m["hl"] = [[เริ่ม, จบ, ช่อง]] ตำแหน่งในข้อความที่ลูกค้าพิมพ์จริง · หน้าเว็บระบายสีตามหมวด กดแล้วไปช่องนั้น
_SPANS = {}                       # (id ข้อความ, เราเพิ่งขอไอดีไหม) → spans · ข้อความไม่เปลี่ยน คิดครั้งเดียวต่อ process
_SPANS_MAX = 20000


def _merge_spans(sp, text) -> list:
    """เรียง · ตัดที่ซ้อนกัน (เอาอันที่เริ่มก่อน/ยาวกว่า) · ต่อคำของช่องเดียวกันที่ห่างกันแค่ช่องว่าง"""
    out = []
    for s, e, f in sorted(sp, key=lambda x: (x[0], -(x[1] - x[0]))):
        if e <= s:
            continue
        if out and s < out[-1][1]:
            continue
        if out and out[-1][2] == f and not text[out[-1][1]:s].strip():
            out[-1][1] = e
            continue
        out.append([s, e, f])
    return out


def _car_spans(text: str) -> list:
    """คำที่บอกรถใน "รถลูกค้าถาม" (car_phrase ตัดคำเกินออกแล้ว) — หาแต่ละคำในข้อความเดิม"""
    if car_in(text) is None:
        return []
    low, out, cur = text.lower(), [], 0
    for w in car_phrase(text).split():
        i = low.find(w.lower(), cur)
        if i < 0:
            i = low.find(w.lower())
        if i >= 0:
            out.append((i, i + len(w), "car_text"))
            cur = i + len(w)
    return out


def msg_spans(text: str, asked: bool = False, outbound: bool = False) -> list:
    """ข้อความ 1 ข้อความ → [[เริ่ม, จบ, ช่อง]] (ช่อง = คีย์ใน LEAD_FIELDS หรือ deal/trade)"""
    from . import lead_keywords as K
    if outbound:
        return _merge_spans(K.deal_spans(text, outbound=True), text)
    sp = []
    for m in _PHONE_RE.finditer(text):
        if phones_in([m.group(0)]):
            sp.append((m.start(), m.end(), "phone"))
    for mm in _LINE_ID_LABEL.finditer(text):
        if _id_ok(mm.group(1), allow_phone=True):
            sp.append((mm.start(1), mm.end(1), "line_id"))
    from .lead_qr import _LINK, line_contact
    for mm in _LINK.finditer(text):
        if line_contact(mm.group(0)):
            sp.append((mm.start(), mm.end(), "line_id"))
    for s, e, _v in bare_ids(text, asked):
        sp.append((s, e, "line_id"))
    try:
        sp += _car_spans(text)
    except Exception:
        pass
    sp += K.spans(text) + K.deal_spans(text)
    return _merge_spans(sp, text)


def _u16(text: str, sp: list) -> list:
    """ตำแหน่งแบบ Python (นับตัวอักษร) → แบบ JavaScript (นับ UTF-16) — อีโมจิ/อักษรนอก BMP นับเป็น 2 ในเบราว์เซอร์
    ไม่แปลง = ไฮไลต์เลื่อนไปทับคำข้างๆ ทุกข้อความที่มีอีโมจินำหน้า (ลูกค้าใส่อีโมจิบ่อย)"""
    if not sp or all(ord(c) < 0x10000 for c in text):
        return sp
    pre, n = [0], 0
    for c in text:
        n += 2 if ord(c) >= 0x10000 else 1
        pre.append(n)
    return [[pre[s], pre[e], f] for s, e, f in sp]


def add_spans(msgs, lead=None) -> list:
    """ใส่ m["hl"] ให้ข้อความในแชท (เฉพาะคนที่เห็นแชทเต็ม) · คำว่า "ขาย/รับซื้อ" ไฮไลต์เฉพาะลีดที่เป็นรับซื้อจริง
    (ลีดขายที่บังเอิญมีคำว่าขาย ไฮไลต์แล้วชวนเข้าใจผิด) · มีรถเทิร์นก็เหมือนกัน"""
    deal = deal_of(lead) if lead else ""
    trade = bool(lead and (lead.auto or {}).get(TRADE_KEY))
    asked = False
    for m in msgs or []:
        t = m.get("text") or ""
        out = m.get("dir") == "out"
        if out:
            asked = asked or bool(_ASK_ID.search(t))
            if deal != "buy" or not t:
                continue
        elif not t.strip() or t.startswith("["):
            asked = False
            continue
        key = (m.get("id") or t, "o" if out else asked)
        sp = _SPANS.get(key) if m.get("id") else None
        if sp is None:
            try:
                sp = _u16(t, msg_spans(t, asked=asked, outbound=out))
            except Exception:
                sp = []
            if m.get("id"):
                if len(_SPANS) > _SPANS_MAX:
                    _SPANS.clear()
                _SPANS[key] = sp
        sp = [x for x in sp if (x[2] != "deal" or deal == "buy") and (x[2] != "trade" or trade)]
        if sp:
            m["hl"] = sp
        if not out:
            asked = False
    return msgs


def capture_contact(o, msgs=None, extra=None) -> bool:
    """เก็บเบอร์/ID LINE ที่ลูกค้าให้ในแชทลงข้อมูลลีด (ช่องที่ยังว่าง + คนยังไม่เคยแก้) → คืนว่าได้อะไรใหม่ไหม

    เรียกตอนข้อความเข้า (LINE/FB) และตอนเปิดแชท — **ลีดเข้าห้องพักทันทีที่ลูกค้าให้ช่องทางติดต่อ**
    ไม่ต้องรอแอดมินเปิดแชทก่อน · ไม่มีช่องทางติดต่อ = ไม่สร้างแถว ChatLead ให้เปล่าๆ
    """
    lead = lead_of(o, create=False)
    if lead and lead.phone and lead.line_id:
        return False
    if msgs is None:
        msgs = messages(o, limit=60)
    ph, ids = contacts_in(list(msgs) + list(extra or []))
    if not ph and not ids:
        return False
    lead = lead or lead_of(o)
    auto = dict(lead.auto or {})
    had = bool(lead.phone or lead.line_id)
    got = []
    if ph and not lead.phone and auto.get("phone") != HUMAN:
        lead.phone, auto["phone"] = ph[0], "แชท"
        got.append("phone")
    if ids and not lead.line_id and auto.get("line_id") != HUMAN:
        lead.line_id, auto["line_id"] = ids[0], "แชท"
        got.append("line_id")
    if got and not had:
        _stamp_contact(o, lead, auto)
    if got:
        lead.auto = auto
        lead.save(update_fields=got + ["auto", "updated_at"])
    return bool(got)


QR_SRC = "รูป QR"                  # ป้ายที่มาในฟอร์มลีด ("จากรูป QR")
CONTACT_AT_KEY = "_contact_at"     # ★ 18 ต.ค.69 เวลาที่ลูกค้าให้ช่องทางติดต่อครั้งแรก (ระบบจ่ายวนจากแชทนับจากตรงนี้)


def _stamp_contact(o, lead, auto) -> bool:
    """ลีดเพิ่งได้ช่องทางติดต่อครั้งแรก → จดเวลา = ข้อความล่าสุดของลูกค้า (ไม่ใช่ "ตอนนี้")
    ตัวเก็บตกแชทเก่า (`scan_contacts`) เติมเบอร์ให้แชทเมื่อหลายวันก่อนได้ — ถ้าจดเป็นตอนนี้
    ระบบจ่ายวนจะเข้าใจว่าเป็นลีดใหม่หลังเปิดสวิตช์ แล้วจ่ายลีดเก่าที่แอดมินอาจจัดการไปแล้ว"""
    if CONTACT_AT_KEY in auto or not (lead.phone or lead.line_id):
        return False
    at = o.last_in_at or timezone.now()
    auto[CONTACT_AT_KEY] = timezone.localtime(min(at, timezone.now())).isoformat(timespec="seconds")
    return True


def capture_qr(o, value: str, ref: str = "") -> bool:
    """ลูกค้าส่งรูป QR ของ LINE ตัวเอง (`lead_qr.scan_row`) → เติม ID LINE ให้ลีด → เข้าห้องพักเหมือนพิมพ์ ID มา

    กติกาเดียวกับ `capture_contact`: เฉพาะช่องที่ยังว่าง · คนแก้/ลบช่องนี้แล้ว = ไม่เติม
    จดว่าได้จากข้อความไหน (`auto["_qr"]`) ให้คนกลับไปดูรูปต้นทางได้
    """
    v = (value or "").strip()[:LEAD_FIELDS["line_id"]]
    if not v:
        return False
    lead = lead_of(o, create=False)
    if lead and (lead.line_id or (lead.auto or {}).get("line_id") == HUMAN):
        return False
    lead = lead or lead_of(o)
    auto = dict(lead.auto or {})
    had = bool(lead.phone or lead.line_id)
    lead.line_id, auto["line_id"] = v, QR_SRC
    auto["_qr"] = {"at": timezone.now().isoformat(timespec="seconds"), "msg": ref[:24]}
    if not had:
        _stamp_contact(o, lead, auto)
    lead.auto = auto
    lead.save(update_fields=["line_id", "auto", "updated_at"])
    return True


# ── จับ keyword จากแชท → ช่องโปรไฟล์ลีด (7 ต.ค.69 · เจ้าของสั่ง "จับ keyword … กรอกลงทุกช่องตามที่ lead ต้องการ") ──
#   ตัวจับอยู่ที่ `lead_keywords.py` (ฟังก์ชันล้วน ไม่ใช้ AI) · ตรงนี้แค่ตัดสินว่าเขียนช่องไหน
KW_KEY = "_kw"                    # ChatLead.auto[KW_KEY] = {ช่อง: คำที่จับได้} — ป้าย "จากแชท" บอกได้ว่าจับจากคำไหน
_KW_SRC = ("แชท", "โน้ต")


def _lead_notes(lead) -> list:
    """โน้ตที่คนพิมพ์ในฟอร์ม (มากรอกชีตกันเถอะ · PROFILE จาก ADMIN · เพิ่มเติม) — อ่านหา keyword ด้วย"""
    return [x for x in (lead.fill_note, lead.admin_profile, lead.more) if x] if lead else []


def apply_keywords(lead, auto: dict, msgs, notes=()) -> list:
    """เติม อาชีพ/รายได้/อายุงาน/ประวัติผ่อน/ประเภทลูกค้า/สถานะลูกค้า จาก keyword → รายชื่อช่องที่เปลี่ยน

    กติกาเดียวกับ `autofill`: **เติมเฉพาะช่องที่ว่างและยังไม่เคยเติม · ช่องที่คนแก้แล้วไม่แตะเด็ดขาด**
    · ช่อง dropdown (ประเภทลูกค้า/สถานะลูกค้า) = ตัวเลือกของชีตเท่านั้น ไม่ตรงสักตัว = ไม่เติม (ไม่เดา)
    · **สถานะลูกค้าเปลี่ยนตามข้อความล่าสุดได้** (ลูกค้าเปลี่ยนใจ) — เฉพาะที่ระบบเติมเอง ช่องอื่นเติมครั้งเดียว
    · โน้ตที่คนพิมพ์ในฟอร์มชนะแชท (คนสรุปมาแล้ว)
    """
    from . import lead_keywords as K
    got = {f: (v, ev, "แชท") for f, (v, ev) in K.extract([t for t in (msgs or []) if t]).items()}
    got.update({f: (v, ev, "โน้ต") for f, (v, ev) in K.extract([t for t in (notes or []) if t]).items()})
    changed, why = [], dict(auto.get(KW_KEY) or {})
    for f, (val, ev, src) in got.items():
        if f == "customer_type":
            val = K.pick(dd_options(f), K.TYPE_SPELL.get(val, []))
        elif f == "customer_status":
            val = K.pick(dd_options(f), K.STATUS_SPELL.get(val, []))
        val = str(val or "").strip()[:LEAD_FIELDS[f]]
        cur, a = (getattr(lead, f) or ""), auto.get(f)
        if not val or a == HUMAN or cur == val:
            continue
        if (cur or f in auto) and not (f == "customer_status" and a in _KW_SRC):
            continue
        setattr(lead, f, val)
        auto[f] = src
        why[f] = str(ev or "")[:120]
        changed.append(f)
    if changed:
        auto[KW_KEY] = why
    # ★ 12 ต.ค.69 ลูกค้าพูดค่าใหม่ทีหลัง ("รายได้ 15,000" → "จริงๆ รวมโอทีได้ 18,000") — ไม่ทับเอง ขึ้นให้คนเลือก
    sg = {f: v for f, v in K.latest(msgs or []).items() if f in SUGG_FIELDS}
    if _suggest(lead, auto, {f: (str(v or "").strip()[:LEAD_FIELDS[f]], ev) for f, (v, ev) in sg.items()},
                fields=SUGG_FIELDS):
        changed.append(SUGG_KEY)
    return changed


# ── ★ 12 ต.ค.69 "ค่าใหม่รอคนตัดสิน" (เดโม CRM ที่เจ้าของเลือก) ──
#   เดิม: ช่องที่ระบบเติมจากแชทแล้ว = เติมครั้งเดียว → ลูกค้าแก้ค่าทีหลัง ค่าใหม่หายเงียบ (ไม่มีใครรู้)
#   ตอนนี้: ค่าใหม่ไม่ทับเอง เก็บไว้ที่ auto[SUGG_KEY] = {ช่อง: {v | opts, why, from, at}} → แผงขวาขึ้นกล่องให้คนเลือก
#   · ใช้ค่าใหม่ = บันทึกช่องตามปกติ (กลายเป็น "คน" → ระบบไม่แตะอีก) · คงค่าเดิม = บันทึกค่าเดิม (คนยืนยันแล้ว)
#   · "ยังไม่รู้"/ปิด = จดไว้ใน auto[SUGG_NO_KEY] ไม่ถามค่าเดิมซ้ำ · ช่องที่คนแก้แล้วไม่ถามเลย
#   · สถานะลูกค้าไม่อยู่ในนี้ (เปลี่ยนตามข้อความล่าสุดเองอยู่แล้ว)
SUGG_KEY = "_sugg"
SUGG_NO_KEY = "_sugg_no"
SUGG_FIELDS = ("occupation", "income", "job_tenure")


def _suggest(lead, auto: dict, latest: dict, fields=SUGG_FIELDS) -> bool:
    """`latest` = {ช่อง: (ค่าล่าสุดในแชท, คำที่จับได้)} → ตั้ง/ล้างคำแนะนำของช่องใน `fields` · คืนว่าเปลี่ยนไหม"""
    sg = dict(auto.get(SUGG_KEY) or {})
    no = auto.get(SUGG_NO_KEY) or {}
    before = json.dumps(sg, sort_keys=True, ensure_ascii=False)
    for f in fields:
        cur, a = (getattr(lead, f) or ""), auto.get(f)
        val, ev = latest.get(f) or ("", "")
        if not cur or a != "แชท" or not val or val == cur or val in (no.get(f) or []):
            sg.pop(f, None)
            continue
        if (sg.get(f) or {}).get("v") != val:
            sg[f] = {"v": val, "why": str(ev or "")[:120], "from": cur, "at": timezone.now().isoformat(timespec="seconds")}
    if json.dumps(sg, sort_keys=True, ensure_ascii=False) == before:
        return False
    if sg:
        auto[SUGG_KEY] = sg
    else:
        auto.pop(SUGG_KEY, None)
    return True


def _model_choices(text: str) -> list:
    """ลูกค้าพิมพ์ชื่อรุ่นหลักที่มีหลายรุ่นย่อย ("city") → ตัวเลือก "CAR / สูตร" ของรุ่นนั้นทั้งหมด (ให้คนเลือก ไม่เดา)"""
    try:
        from dashboard.services.purchase_report import _compact
    except Exception:
        return []
    c = _compact(text)
    for b in _vocab().get("bases") or []:
        if b in c:
            opts = [o for o in dd_options("car_model") if o.split() and o.split()[0].lower() == b]
            if 2 <= len(opts) <= 8:
                return opts
    return []


def dismiss_suggestion(o, field: str, by: str = ""):
    """ปุ่ม "ยังไม่รู้"/ปิดกล่อง — ไม่ถามค่านี้ซ้ำ (ค่าในช่องไม่เปลี่ยน · ระบบยังเติม/แทนได้ตามกติกาเดิม)"""
    lead = lead_of(o, create=False)
    auto = dict((lead.auto if lead else None) or {})
    sg = dict(auto.get(SUGG_KEY) or {})
    item = sg.pop(field, None)
    if not item:
        return False, "ไม่มีค่าใหม่รอยืนยันในช่องนี้แล้ว"
    no = dict(auto.get(SUGG_NO_KEY) or {})
    key = item.get("v") or ("opts:" + "|".join(item.get("opts") or []))
    no[field] = ((no.get(field) or []) + [key])[-5:]
    auto[SUGG_NO_KEY] = no
    if sg:
        auto[SUGG_KEY] = sg
    else:
        auto.pop(SUGG_KEY, None)
    lead.auto = auto
    lead.updated_by = (by or "")[:80]
    lead.save(update_fields=["auto", "updated_by", "updated_at"])
    return True, "ปิดแล้ว — ไม่ถามค่านี้ซ้ำ"


def capture_profile(o, msgs=None, extra=None) -> bool:
    """ตอนข้อความเข้า: จับ keyword แล้วเติมโปรไฟล์ลีดทันที (ไม่ต้องรอใครเปิดแชท) → ได้อะไรใหม่ไหม
    ไม่เจออะไรเลย = ไม่สร้างแถว ChatLead ให้เปล่าๆ (กติกาเดียวกับ `capture_contact`)"""
    if msgs is None:
        msgs = messages(o, limit=80)
    allm = list(msgs) + list(extra or [])
    texts = [m["text"] for m in allm
             if m.get("dir") == "in" and m.get("text") and not m["text"].startswith("[")]
    outs = [m["text"] for m in allm if m.get("dir") == "out" and m.get("text")]
    try:
        return _capture_profile(o, allm, texts, outs)
    finally:
        # ★ 20 ต.ค.69 ลูกค้าอ้างรถในรูป ("สนใจคันล่างสุด") + มีรูปในแชท → AI ดูรูปบอกยี่ห้อ/รุ่น (thread · carvision.py)
        #   เรียกหลังเซฟโปรไฟล์ — ไม่ให้การเซฟข้างบนไปทับผลที่ thread เขียน
        try:
            from . import carvision
            carvision.maybe(o, allm)
        except Exception:
            pass


def _capture_profile(o, allm, texts, outs) -> bool:
    lead = lead_of(o, create=False)
    from . import autotag as AT
    from . import lead_keywords as K
    evs = deal_events(allm)
    # ★ 20 ต.ค.69 กฎแท็กที่แอดมินตั้งเองในหน้า "ระบบอัตโนมัติ" (CRM) — ติดเพิ่มอย่างเดียวตอนข้อความเข้า
    try:
        rs = AT.active()
        found = AT.tags_for(rs, allm) if rs else {}
    except Exception:
        rs, found = [], {}
    if not lead:
        dk = K.deal_kind(texts, outs, evs)
        if not K.extract(texts) and not dk["kind"] and not dk["trade"] and not found:
            return False
    lead = lead or lead_of(o)
    auto = dict(lead.auto or {})
    got = apply_keywords(lead, auto, texts, _lead_notes(lead))
    # ★ 11 ต.ค.69 ลีดรับซื้อ (ลูกค้าอยากขายรถให้เรา) / มีรถเทิร์น — จับตอนข้อความเข้า ลีดแยกแท็บทันที
    deal = apply_deal_kind(lead, auto, texts, outs, evs)
    tagged = False
    if found:
        try:
            tagged = AT.apply_lead(lead, auto, found, rs)
        except Exception:
            tagged = False
    if got or deal or tagged:
        lead.auto = auto
        # got อาจมี SUGG_KEY (คำแนะนำค่าใหม่ — อยู่ใน auto) ซึ่งไม่ใช่ช่องของตาราง
        lead.save(update_fields=[f for f in got if f in LEAD_FIELDS] + (["tags"] if tagged else []) + ["auto", "updated_at"])
    return bool(got or deal or tagged)


CSCAN_KEY = "connect_cscan"        # KV {chat id: เวลาข้อความล่าสุดที่สแกนแล้ว} — จำข้าม worker/รีสตาร์ท
CSCAN_CANDIDATES = 2000            # ดูผู้สมัครกี่แถว (อ่านแค่ id+เวลา ถูก) — ไม่ติดอยู่ที่ 150 แถวบนสุดตลอดไป
_CSCAN_LOCK = 7_406_063            # Postgres advisory lock — worker เดียวสแกนทีละรอบ (เลขไม่ชนของ connect/leadflow/tradein)
_CSCAN_RUN = {"busy": False}


def _cscan_key(dt) -> str:
    return dt.isoformat() if dt else ""


def scan_contacts(limit: int = 150) -> int:
    """เก็บตก: แถวที่คุยในระบบแล้วแต่ข้อมูลลีดยังไม่มีเบอร์/ไอดี → อ่านแชทหาให้
    (ลูกค้าที่คุยก่อนมีกติกานี้ · ของใหม่จับตอนข้อความเข้าอยู่แล้ว) · จำว่าสแกนแล้วถึงข้อความไหน ไม่สแกนซ้ำ

    ★ 11 ต.ค.69 (เจ้าของถาม "โหลดนานเพราะอะไร") — เดิมจำแค่ในหน่วยความจำของ process (`_CSCAN`)
      แล้วเรียกจาก `sync_rows` **ในคำขอของหน้า Connect** → รีสตาร์ท/deploy ทีไร ทุก worker อ่านแชทซ้ำ
      150 ห้องทีละห้องก่อนตอบรายชื่อ (วัด: คำขอแรก 2–3 วิ · ปกติ 0.1 วิ · prod เข้าเงื่อนไข 983 ห้อง)
      และไม่เคยไปถึงแถวที่ 151 เป็นต้นไป · ตอนนี้จำใน KV `connect_cscan` + เรียกจาก thread (`scan_contacts_bg`)
    """
    from dashboard.services import cache_store
    engaged = (Q(awaiting_since__isnull=False) | Q(owner__isnull=False)
               | Exists(ChatOwnerLog.objects.filter(chat=OuterRef("pk"))))
    cand = list(ChatOwner.objects.filter(engaged)
                .filter(Q(lead__isnull=True) | (Q(lead__phone="") | Q(lead__line_id="")))
                .order_by(F("last_in_at").desc(nulls_last=True))
                .values_list("id", "last_in_at", "last_at")[:CSCAN_CANDIDATES])
    try:
        seen = dict((cache_store.get_kv(CSCAN_KEY) or {}).get("data") or {})
    except Exception:
        seen = {}
    # ★ เช็ค "มีในตาราง" ก่อน — แถวที่ไม่มีเวลาข้อความ (ค่าว่าง) ต้องไม่ถูกนับว่าสแกนแล้วตั้งแต่ยังไม่เคยสแกน
    todo = [(i, _cscan_key(a or b)) for i, a, b in cand
            if not (str(i) in seen and seen[str(i)] == _cscan_key(a or b))][:limit]
    keep = {str(i) for i, _a, _b in cand}
    changed = len(seen) != len([k for k in seen if k in keep])
    seen = {k: v for k, v in seen.items() if k in keep}   # แถวที่ได้เบอร์+ไอดีครบ/ถูกลบ = ไม่ต้องจำ (กัน KV โตไม่หยุด)
    n = 0
    objs = ChatOwner.objects.select_related("profile", "fb_profile", "lead").in_bulk([i for i, _k in todo])
    for oid, key in todo:
        o = objs.get(oid)
        seen[str(oid)] = key
        changed = True
        if not o:
            continue
        try:
            n += 1 if capture_contact(o) else 0
        except Exception:
            pass
    if changed:
        try:
            cache_store.set_kv(CSCAN_KEY, seen)
        except Exception:
            pass
    return n


def scan_contacts_bg(limit: int = 150) -> bool:
    """เรียก `scan_contacts` ใน thread แยก (ห้ามหน่วงหน้าเว็บ) · Postgres = worker เดียวทำทีละรอบ
    เทสต์ (`BG_FILL=False`) = ทำในที่เลย"""
    import threading
    if not BG_FILL:
        scan_contacts(limit)
        return True
    if _CSCAN_RUN["busy"]:
        return False

    def _work():
        from django.db import connection
        got = False
        try:
            if connection.vendor == "postgresql":
                with connection.cursor() as cur:
                    cur.execute("SELECT pg_try_advisory_lock(%s)", [_CSCAN_LOCK])
                    got = bool(cur.fetchone()[0])
                if not got:
                    return                              # worker อื่นกำลังสแกนอยู่
            scan_contacts(limit)
        except Exception:
            pass
        finally:
            _CSCAN_RUN["busy"] = False
            try:
                if got:
                    with connection.cursor() as cur:
                        cur.execute("SELECT pg_advisory_unlock(%s)", [_CSCAN_LOCK])
            except Exception:
                pass
            try:
                connection.close()                    # thread แยกมี connection ของตัวเอง ต้องปิดเอง
            except Exception:
                pass

    _CSCAN_RUN["busy"] = True
    threading.Thread(target=_work, daemon=True).start()
    return True


def suggest_prefix(lead, assignee_team: str = "", o=None, msgs=None) -> dict:
    """ตัวหน้าที่ควรใช้ · คนเปลี่ยนเองได้ที่หน้าเว็บ
    ลำดับ: type ที่กรอกแล้ว → ช่องทาง TikTok/TikTokAds → ★ 17 ต.ค.69 **เกณฑ์ของเจ้าของจากข้อมูลในแชท**
    (`lead_code.for_chat` · HLD/WLD/LD/BLD/NLD · บอกเหตุผล) → NLD
    ★ 17 ต.ค.69 **ไม่ติ๊ก R ให้เอง** — เจ้าของยืนยันว่า R = ส่งต่อเคสให้ไม้ 2/แอดมิน ไม่ใช่ลีดใหม่ (ใช้ "ส่งต่อไม้ 2")"""
    t = (getattr(lead, "lead_type", "") or "").strip().lower()
    ch = (getattr(lead, "channel", "") or "").lower().replace(" ", "")
    reasons, auto_code = [], None
    if t in _TYPE_BASE:
        base, why = _TYPE_BASE[t], "ตาม type \"%s\"" % lead.lead_type
    elif "tiktokads" in ch:
        base, why = "TALD", "ช่องทาง TikTokAds"
    elif "tiktok" in ch:
        base, why = "TLD", "ช่องทาง TikTok"
    else:
        base, why = "NLD", "ค่าตั้งต้น (Moderate)"
        if o is None and getattr(lead, "chat_id", None):
            o = getattr(lead, "chat", None)
        if o is not None:
            try:
                from . import lead_code
                auto_code = lead_code.for_chat(o, lead, msgs)
                base, why, reasons = auto_code["base"], auto_code["why"], auto_code["reasons"]
            except Exception as e:
                why = "ค่าตั้งต้น (Moderate) — อ่านแชทไม่สำเร็จ: %s" % str(e)[:60]
    admin = assignee_team == "ADMIN"
    out = {"base": base, "admin": admin, "reject": False, "why": why, "reasons": reasons}
    if auto_code is not None:
        out["auto"] = True
        out["doc"] = bool(auto_code.get("doc"))
        out["docAuto"] = bool(auto_code.get("docAuto"))
    return out


def build_prefix(base: str, admin: bool = False, reject: bool = False) -> str:
    base = (base or "").upper()
    if base not in {b for b, _ in CODE_BASES}:
        base = "NLD"
    return ("R" if reject else "") + ("A" if admin else "") + base


def last_running() -> int:
    """เลขรันล่าสุดที่ใช้จริง — จากใบจ่ายลีด 20 ใบล่าสุดในกลุ่มจ่ายเบอร์ (ไม่นับ R = เคสเก่าที่ส่งต่อ)
    รวมเลขที่โหมดทดลองออกไปแล้ว · ใช้ "มากสุดของ 20 ใบ" เพราะบางใบโพสต์สลับลำดับกัน"""
    from .leadgroup import _LEAD_NO
    nums = []
    gids = _lead_group_ids()
    if gids:
        rows = (GroupChat.objects.filter(chat_type=GroupChat.GROUP, group_id__in=gids, text__icontains="lead no")
                .order_by("-sent_at").values_list("text", flat=True)[:120])
        for t in rows:
            m = _LEAD_NO.search(t or "")
            mm = _ANY_CODE.match(re.sub(r"[ \t]", "", m.group(1))) if m else None     # "TLD10- 8500" ก็นับ
            if mm and not mm.group(1).upper().startswith("R"):
                nums.append(int(mm.group(3)))
            if len(nums) >= 20:
                break
    # เลขที่ปุ่ม "จ่ายเบอร์" ออกไปแล้ว — ทั้งลูกค้า LINE OA (ChatLead) และลีดภายนอกจากห้องพัก Lead (ExtLead)
    #   ใช้เลขรันชุดเดียวกัน · ★ 6 ต.ค.69 นับทั้งโหมดทดลองและโหมดส่งจริง (`assigned_at` = ระบบเป็นคนออกเลข)
    #   — ใบที่ส่งเข้ากลุ่มสำเร็จจะอยู่ในแชทกลุ่มด้านบนด้วย แต่ใบที่ส่งไม่สำเร็จ (รอกดส่งอีกครั้ง) มีที่นี่ที่เดียว
    #   เรียงล่าสุดก่อน (เดิมตัด 500 แถวโดยไม่เรียง = ได้แถวสุ่ม พอเลขเยอะจะเดาเลขถัดไปต่ำกว่าจริง)
    demo = []
    for M in (ChatLead, ExtLead):
        demo += list(M.objects.filter(assigned_at__isnull=False).exclude(code="").order_by("-assigned_at")
                     .values_list("code", flat=True)[:500])
    for c in demo:
        mm = _ANY_CODE.match(c or "")
        if mm:
            nums.append(int(mm.group(3)))
    try:                                          # ★ 19 ต.ค.69 เลขที่ระบบเก็บลีดอัตโนมัติจองไว้ (ใบอยู่กลุ่ม ADMIN เก็บ Lead ไม่ใช่ห้องจ่ายเบอร์)
        from .autolead import reserved_nums
        nums += reserved_nums()
    except Exception:
        pass
    nums += _sheet_running(max(nums) if nums else 0)
    return max(nums) if nums else 0


SHEET_RUN_ROWS = 600      # แถวท้ายๆ ของแท็บเดือนนี้ในสำเนาชีตลีด
SHEET_RUN_GAP = 30        # นับเฉพาะเลขในชีตที่นำหน้าใบในกลุ่มไม่เกินนี้


def _sheet_running(base: int) -> list:
    """★ 18 ต.ค.69 เลขรันที่แอดมินลงในชีตลีดตรงๆ (ไม่ได้โพสต์ใบในกลุ่ม) — กันระบบออกเลขชนกับเลขนั้น

    อ่านจากสำเนาชีตใน Postgres (`dash_lead_sheet_row` · อัปเดตทุก 10 นาที) ไม่ยิง Google ตอนออกเลข
    · **แท็บเดือนนี้เท่านั้น** + นำหน้าใบในกลุ่มไม่เกิน `SHEET_RUN_GAP` — ชีตมีเลขพิมพ์ผิดจริง
      (วัด prod 18 ต.ค.69: แท็บ ก.ย. แถว 2397–2400 = TLD9-9662..9665 แทน 7662..7665 · นำหน้าใบล่าสุด 9522 อยู่ 143)
      ถ้านับ ระบบจะกระโดดไปออก 9666 · แอดมินลงชีตล่วงหน้าจริงมักนำแค่ไม่กี่เลข
    · ไม่มีใบในกลุ่มเลย (`base` = 0) = ไม่นับชีต (ไม่มีอะไรให้เทียบว่าเลขไหนพิมพ์ผิด) · อ่านไม่ได้ = ไม่นับ
    """
    if not base:
        return []
    try:
        from dashboard.models import LeadSheetRow
        first = timezone.localdate().replace(day=1)
        codes = (LeadSheetRow.objects.filter(tab_month=first).exclude(code="")
                 .order_by("-row_no").values_list("code", flat=True)[:SHEET_RUN_ROWS])
    except Exception:
        return []
    out = []
    for c in codes:
        mm = _ANY_CODE.match(re.sub(r"[ 	]", "", (c or "").split("/")[0]))
        if not mm or mm.group(1).upper().startswith("R"):
            continue
        n = int(mm.group(3))
        if base < n <= base + SHEET_RUN_GAP:
            out.append(n)
    return out


def code_taken(code: str, chat_lead_pk=None, ext_pk=None) -> bool:
    """เลขลีดนี้ถูกใช้แล้วหรือยัง — เช็คทั้งลูกค้า LINE OA (ChatLead) และลีดภายนอกจากห้องพัก Lead (ExtLead)"""
    if ChatLead.objects.filter(code__iexact=code).exclude(pk=chat_lead_pk).exists():
        return True
    return ExtLead.objects.filter(code__iexact=code).exclude(pk=ext_pk).exists()


def next_code(prefix: str) -> str:
    return "%s%d-%d" % (prefix, timezone.localdate().month, last_running() + 1)


def code_help(o, lead, msgs=None) -> dict:
    """ข้อมูลให้หน้าเว็บประกอบตัวอย่างเลขลีดก่อนกด "จ่ายเบอร์" (เลขจริงคำนวณใหม่ตอนกด กันซ้ำ)"""
    sug = suggest_prefix(lead, team_of(o.owner) if o.owner_id else "", o=o, msgs=msgs)
    out = {"suggest": sug, "bases": [{"key": b, "type": t} for b, t in CODE_BASES],
           "month": timezone.localdate().month, "next": last_running() + 1,
           "post": post_help(sim=is_sim_row(o), fb=is_fb(o))}
    try:                                          # ★ 19 ต.ค.69 เลขที่ระบบเก็บลีดอัตโนมัติจองไว้ = เลขที่จะได้ตอนกดจ่าย
        from .autolead import reserved
        rv = reserved(lead)
        if rv:
            out.update(month=rv.get("month") or out["month"], next=rv["num"],
                       reserved={"code": rv.get("code"), "ok": bool(rv.get("ok")), "room": rv.get("room") or "",
                                 "error": rv.get("error") or ""})
            if rv.get("base"):
                sug["base"] = rv["base"]
    except Exception:
        pass
    return out


def slip_post_on(c=None) -> bool:
    """ปุ่ม "จ่ายเบอร์" ส่งใบเข้ากลุ่มจ่ายเบอร์จริงไหม (`connect_config.slip_post`) · อ่านค่าไม่ได้ = ไม่ส่ง"""
    try:
        return bool((c or cfg()).get("slip_post"))
    except Exception:
        return False


def post_help(sim: bool = False, fb: bool = False, c=None) -> dict:
    """ข้อมูลให้กล่องจ่ายเบอร์บอกล่วงหน้าว่า "กดแล้วจะส่งเข้ากลุ่มไหน" (ไม่ยิงเน็ต — อ่านทะเบียนกลุ่มใน KV)"""
    from . import slippost
    c = c or cfg()
    try:
        r = slippost.rooms(c)
    except Exception:
        r = {slippost.MAIN: {"name": ""}, slippost.REJECT: {"name": ""}}
    return {"on": slip_post_on(c) and not sim, "sim": bool(sim), "fb": bool(fb),
            "fbNote": slippost.FB_DATA_ONLY if fb else "",
            "room": r[slippost.MAIN].get("name") or "", "rejectRoom": r[slippost.REJECT].get("name") or ""}


_CODE_LOCK = 7406061    # เลขประจำ advisory lock ของการออกเลขลีด (ทั้งโปรเจกต์ยังไม่มีล็อกอื่นใช้ — เลขอะไรก็ได้ที่ไม่ชน)


@contextmanager
def code_lock():
    """ล็อกการออกเลขลีด — ★ 6 ต.ค.69 ส่งเข้ากลุ่มจริงแล้ว 2 แอดมินกดจ่ายเบอร์พร้อมกันต้องไม่ได้เลขเดียวกัน
    (เดิมเป็นข้อจำกัดที่จดไว้ว่า "ยังไม่มีล็อก" ตอนเป็นโหมดทดลอง)
    Postgres = advisory lock ระดับธุรกรรม (ปลดเองตอน commit/rollback) · SQLite (dev/เทสต์) เขียนได้ทีละคนอยู่แล้ว
    ห้ามยิงเน็ตข้างในล็อก — ส่งเข้ากลุ่มหลังออกจากล็อกแล้วเท่านั้น"""
    with transaction.atomic():
        from django.db import connection
        if connection.vendor == "postgresql":
            with connection.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(%s)", [_CODE_LOCK])
        yield


class _Undo(Exception):
    """ยกเลิกธุรกรรมของปุ่มจ่ายเบอร์ พร้อมข้อความที่จะบอกผู้ใช้"""


def assign_lead(o, emp, base: str, admin: bool = False, reject: bool = False, code: str = "", by: str = ""):
    """ปุ่ม "จ่ายเบอร์" → (ok, ข้อความ)

    ออกเลขลีด (ล็อกกันเลขซ้ำ) → ตั้ง type (ถ้ายังว่าง) → โอนลูกค้าให้เซลล์ → จดว่าใครจ่ายเมื่อไหร่
    → ★ 6 ต.ค.69 **ส่งใบจ่ายลีดเข้ากลุ่มจ่ายเบอร์จริง + แท็กเซลล์** (`slippost.py` · สวิตช์ `slip_post`)
      · ลูกค้า LINE: เซลล์ได้แชท ตอบลูกค้าผ่าน Connect ได้
      · ลูกค้า Facebook: เซลล์ได้สิทธิ์ **เพื่อเก็บข้อมูลเท่านั้น** (ตอบจาก Connect ไม่ได้ — `api_reply`)
      · **ไม่ลงชีต** (เจ้าของสั่งไว้ 4 ต.ค.69) · ลูกค้าจำลอง/บัญชีทดสอบ = ไม่ส่งเข้ากลุ่มจริง (เป็นเลขทดลอง)
      · ส่งไม่สำเร็จ = **การจ่ายในระบบยังอยู่** (ไม่ย้อน) แล้วจดเหตุผลใน `post_info` ให้กด "ส่งเข้ากลุ่มอีกครั้ง"
    สวิตช์ปิด = โหมดทดลองเดิม (`code_demo`) — เก็บในระบบอย่างเดียว
    """
    if not emp or not emp.active:
        return False, "เลือกเซลล์ที่จะจ่ายเบอร์ให้ก่อน"
    c = cfg()
    real = slip_post_on(c) and not is_sim_row(o) and not is_test_seller(emp)
    lead = lead_of(o)                             # สร้างแถวก่อนเข้าล็อก (สร้างชนกันใน transaction = transaction พัง)
    prefix = build_prefix(base, admin, reject)
    code = (code or "").strip().upper()
    if code and not _CODE_RE.match(code):
        return False, "เลขลีดไม่ถูกรูปแบบ — ต้องเป็นแบบ NLD10-8410 (ตัวหน้า + เดือน + เลขรัน)"
    try:
        with code_lock():                         # เลขถัดไป → ตรวจซ้ำ → บันทึก ภายในล็อกเดียว · โอนไม่สำเร็จ = ย้อนทั้งหมด
            lead = ChatLead.objects.get(pk=lead.pk)
            if (lead.code or "").strip():
                # มีเลขแล้ว (จากใบจ่ายลีดจริง/คนกรอก/จ่ายไปแล้ว) — ห้ามออกเลขทับ ไม่งั้นเลขจริงที่ผูกกับชีตหาย
                # กรณีหน้าเว็บค้างของเก่าอยู่ / แอดมินอีกคนเพิ่งกดจ่ายไป ก็โดนกันที่นี่
                raise _Undo("ลูกค้ารายนี้มีเลขลีด %s แล้ว — ไม่ออกเลขใหม่ทับ (จะเปลี่ยนเซลล์ใช้ปุ่ม \"โอน\")" % lead.code)
            res_note = ""
            if not code:
                # ★ 19 ต.ค.69 ระบบเก็บลีดอัตโนมัติจองเลขไว้แล้ว (ใบในกลุ่ม ADMIN เก็บ Lead) → ใช้เลขเดิม
                #   แอดมินคัดลอกใบไปแท็กในห้องจ่ายเบอร์เองแล้ว (ลูกค้าคนเดียวกัน) = ห้ามจ่ายซ้ำ
                #   เลขนั้นถูกใช้กับลูกค้าคนอื่น (แอดมินออกเลขมือชน) = ออกเลขใหม่ + บอก
                from . import autolead
                code, res_note, stop = autolead.code_for_assign(
                    lead, prefix, autolead.lead_keys(lead), lambda c: code_taken(c, chat_lead_pk=lead.pk))
                if stop:
                    raise _Undo(stop)
            code = code or next_code(prefix)
            if code_taken(code, chat_lead_pk=lead.pk):
                raise _Undo("เลข %s ถูกใช้กับลูกค้าคนอื่นแล้ว" % code)
            lead.code, lead.code_demo = code, not real
            m_code = _CODE_RE.match(code)
            if not lead.lead_type and m_code:    # type ว่าง → เติมตามตัวหน้าของ "เลขจริงที่ได้" (NLD → Moderate ฯลฯ)
                core = m_code.group(1).lstrip("R").lstrip("A")      # (เลขรันสั้นผิดรูป = ไม่เดา type · เดิมพัง 500)
                lead.lead_type = dict(CODE_BASES).get(core, "")
            auto = dict(lead.auto or {})
            auto.pop(NOCODE_KEY, None)           # เคยกด "ไม่ต้องจ่ายเบอร์" ไว้แล้วเปลี่ยนใจ — จ่ายแล้วป้ายนั้นไม่ต้องค้าง
            auto["code"] = "จ่ายเบอร์" if real else "จ่ายเบอร์(ทดลอง)"
            lead.auto = auto
            lead.assigned_at, lead.assigned_by = timezone.now(), (by or "")[:80]
            lead.updated_by = (by or "")[:80]
            lead.post_info = {"sending": timezone.now().isoformat()} if real else {}
            note = "จ่ายเบอร์ %s" % code + ("" if real else " (ทดลอง)")
            lead.save()
            if o.owner_id == emp.id:             # เป็นของคนนี้อยู่แล้ว — ไม่ต้องโอน แค่จดว่าจ่ายเบอร์
                _log(o, ChatOwnerLog.ASSIGN, emp=emp, by=by, note=note)
            else:
                ok, msg = assign(o.id, emp, by=by, note=note)
                if not ok:
                    raise _Undo(msg)
    except _Undo as e:
        return False, str(e)
    fb_tail = (" · ลูกค้า Facebook: %s ได้สิทธิ์เก็บข้อมูลเท่านั้น (ตอบแชทไม่ได้)" % emp.nickname) if is_fb(o) else ""
    fb_tail = res_note + fb_tail
    if not real:
        from . import leadflow                   # นาฬิกาโทรเดินด้วย (ทดสอบหน้าจอได้) — ไม่มีอะไรส่งออก
        leadflow.before_post(code, emp, by, chat=o, phone=lead.phone, customer=lead.customer_name or lead.account,
                             car=lead.car_model or lead.car_text, demo=True)
        why = "ลูกค้าจำลอง/บัญชีทดสอบ — ไม่ส่งเข้ากลุ่มจริง" if slip_post_on(c) else "ทดลอง — ยังไม่ลงชีต ไม่โพสต์กลุ่ม"
        return True, "จ่ายเบอร์ %s ให้ %s แล้ว (%s)%s" % (code, emp.nickname, why, fb_tail)
    info = _post_slip(o, lead, emp, by, c)
    from . import slippost
    return True, slippost.summary(code, emp.nickname, info) + fb_tail


def post_body(o, lead) -> str:
    """ใบที่ส่งเข้ากลุ่ม — pattern ที่เจ้าของกำหนด (`slippost.body`) · แท็กเซลล์ต่อท้ายตอนส่ง"""
    from . import slippost
    return slippost.body(slip_fields(o, lead))


def _post_slip(o, lead, emp, by: str = "", c=None) -> dict:
    """ส่งใบเข้ากลุ่ม → เก็บผลลง `ChatLead.post_info` (หน้าเว็บโชว์สถานะ/ปุ่มส่งอีกครั้ง)"""
    from . import leadflow, slippost
    task, extra = leadflow.before_post(lead.code, emp, by, chat=o, phone=lead.phone,
                                       customer=lead.customer_name or lead.account,
                                       car=lead.car_model or lead.car_text)
    try:
        info = slippost.post(lead.code, post_body(o, lead), emp, by=by, c=c, extra=extra)
    except Exception as e:                       # ห้ามทำให้การจ่ายเบอร์ที่บันทึกไปแล้วกลายเป็น error 500
        info = {"ok": False, "at": _iso(timezone.now()), "by": (by or "")[:80], "error": "ส่งไม่สำเร็จ: %s" % str(e)[:120]}
    leadflow.after_post(task, info, card=bool(extra))
    ChatLead.objects.filter(pk=lead.pk).update(post_info=info)
    lead.post_info = info
    return info


def repost_lead(o, by: str = ""):
    """ปุ่ม **"ส่งเข้ากลุ่มอีกครั้ง"** (ส่งรอบแรกไม่สำเร็จ) → (ok, ข้อความ) · ส่งสำเร็จไปแล้ว = ไม่ส่งซ้ำ"""
    from . import slippost
    lead = lead_of(o)
    if not lead.code or not lead.assigned_at:
        return False, "ลูกค้ารายนี้ยังไม่ได้จ่ายเบอร์ผ่านระบบ"
    if lead.code_demo:
        return False, "เลข %s ออกในโหมดทดลอง (ไม่ได้จองไว้) — ไม่ส่งเข้ากลุ่มจริง" % lead.code
    if is_sim_row(o):
        return False, "ลูกค้าจำลอง — ไม่ส่งเข้ากลุ่มจริง"
    if not o.owner_id or not o.owner.active:
        return False, "ลูกค้ารายนี้ไม่มีเซลล์แล้ว — โอนให้เซลล์ก่อน"
    with code_lock():                             # กดซ้ำรัวๆ / 2 แอดมินกดพร้อมกัน = ส่งรอบเดียว
        lead = ChatLead.objects.get(pk=lead.pk)
        if (lead.post_info or {}).get("ok"):
            return False, "ส่งใบจ่ายลีด %s เข้ากลุ่มไปแล้ว — ไม่ส่งซ้ำ" % lead.code
        if slippost.sending(lead.post_info):
            return False, "กำลังส่งอยู่ — รอสักครู่"
        lead.post_info = dict(lead.post_info or {}, sending=timezone.now().isoformat())
        lead.save(update_fields=["post_info"])
    info = _post_slip(o, lead, o.owner, by)
    return bool(info.get("ok")), slippost.summary(lead.code, o.owner.nickname, info)


def mark_no_code(o, on: bool, by: str = ""):
    """ปุ่ม **"ไม่ต้องจ่ายเบอร์"** (แอดมิน) → (ok, ข้อความ) — ลูกค้าที่ไม่ใช่ลีดขาย (ถามศูนย์บริการ ·
    อยากขายรถให้เรา · ลูกค้าเก่าทักมาขอบคุณ) ออกจากแท็บ "จ่ายเบอร์" · `on=False` = เอากลับเข้าแท็บ

    เก็บใน `ChatLead.auto["_nocode"]` = {by, at} (คีย์ขึ้นต้น "_" ไม่ใช่ช่องของฟอร์ม · ไม่ต้อง migrate)
    """
    lead = lead_of(o)
    auto = dict(lead.auto or {})
    if on:
        if (lead.code or "").strip():
            return False, "ลูกค้ารายนี้มีเลขลีด %s แล้ว" % lead.code
        auto[NOCODE_KEY] = {"by": (by or "")[:80], "at": _iso(timezone.now())}
        msg = "บันทึกแล้ว — ไม่ต้องจ่ายเบอร์ให้ลูกค้ารายนี้ (ออกจากแท็บจ่ายเบอร์)"
    else:
        if NOCODE_KEY not in auto:
            return True, "ลูกค้ารายนี้รอจ่ายเบอร์อยู่แล้ว"
        auto.pop(NOCODE_KEY, None)
        msg = "เอากลับเข้าแท็บจ่ายเบอร์แล้ว"
    lead.auto = auto
    lead.updated_by = (by or "")[:80]
    lead.save(update_fields=["auto", "updated_by", "updated_at"])
    return True, msg


def lead_options() -> dict:
    """ตัวเลือกของฟอร์มลีด: `dropdowns` = ชุดเดียวกับ dropdown ในชีตลีด (ช่องไหนมี = หน้าเว็บเป็นตัวเลือก ไม่ใช่ช่องพิมพ์)
    + แท็กที่เคยใช้ (ช่วยพิมพ์) · `source` = อ่านมาจากแท็บไหน เมื่อไหร่ (ยังไม่เคยอ่านได้ = ชุดที่จดไว้ในโค้ด)"""
    dd = dropdowns()
    tags = set()
    for ts in ChatLead.objects.exclude(tags=[]).values_list("tags", flat=True)[:300]:
        tags |= set(ts or [])
    return {"dropdowns": dd.get("fields") or {},
            "source": {"tab": dd.get("tab") or "", "at": dd.get("at") or "", "fallback": bool(dd.get("fallback"))},
            "tags": sorted(tags)[:40]}


# ─────────────────────────────────────────────────────────────
#  โหมดทดสอบ — บัญชีเซลล์จำลอง + ลูกค้าจำลอง (3 ต.ค.69 · เจ้าของขอ "จำลองบัญชีเซลล์มาทดสอบเอง")
#
#  ทำไมไม่ให้ "ดูในฐานะเซลล์จริง": กดรับ/ตอบในโหมดนั้นจะกลายเป็นการกระทำของเซลล์คนนั้นจริงๆ
#  → ใช้บัญชีจำลองแยก (ทดสอบเซลล์ A/B) แล้วล้างทิ้งได้ทีเดียว
#  ลูกค้าจำลอง (`TEST-…`) **ไม่มีตัวตนใน LINE** — ตอบไปไม่ออกนอกระบบ · ไม่ส่งแจ้งเตือน LINE ·
#  นับ 5 นาทีทันทีทุกเวลา (ทดสอบกลางคืนได้)
# ─────────────────────────────────────────────────────────────
TEST_PREFIX = "ทดสอบเซลล์ "
SIM_PREFIX = "TEST-"                 # ไม่ขึ้นต้นด้วย U = ไม่มีทางเป็น LINE user id จริง
TEST_NOTE = "บัญชีทดสอบ Connect — ลบได้ที่ Connect → ตั้งค่า → ล้างข้อมูลทดสอบ"


def is_test_seller(emp) -> bool:
    """บัญชีจำลอง (ชื่อขึ้นต้น "ทดสอบเซลล์ ") หรือบัญชีจริงที่ตั้งเป็นบัญชีทดสอบ (`test_accounts`)"""
    nick = (getattr(emp, "nickname", "") or "") if emp else ""
    return bool(nick) and (nick.startswith(TEST_PREFIX) or nick in cfg()["test_accounts"])


def test_accounts() -> list:
    """บัญชีพนักงานจริงที่ตั้งเป็นบัญชีทดสอบ (มีในทะเบียน + ยังใช้งาน) — ปุ่มสลับหน้าจอในการ์ดทดสอบ"""
    names = cfg()["test_accounts"]
    return list(Employee.objects.filter(nickname__in=names, active=True).order_by("nickname")) if names else []


def _test_held():
    """ลูกค้าจริงที่บัญชีทดสอบ (จำลอง + บัญชีจริงที่ตั้งไว้) ถือไว้"""
    from django.db.models import Q
    q = Q(owner__nickname__startswith=TEST_PREFIX)
    names = cfg()["test_accounts"]
    if names:
        q |= Q(owner__nickname__in=names)
    return ChatOwner.objects.filter(q).exclude(profile__user_id__startswith=SIM_PREFIX)


def is_sim(user_id) -> bool:
    return (user_id or "").startswith(SIM_PREFIX)


def test_seller(team: str):
    """บัญชีเซลล์จำลองของทีมนี้ (สร้างให้ถ้ายังไม่มี) — ไม่ต้องเช็คชื่อเข้างาน ไม่ถูกแท็กในกลุ่ม"""
    team = (team or "").strip().upper()
    if not _is_team_code(team):
        return None
    pos = "ทีม %s" % team
    emp, made = Employee.objects.get_or_create(nickname=TEST_PREFIX + team, defaults={
        "position": pos, "track_checkin": False, "notify_missing": False,
        "note": TEST_NOTE, "note_sticky": True, "source": Employee.MANUAL})
    if not made and (not emp.active or emp.position != pos):
        emp.active, emp.position = True, pos
        emp.save(update_fields=["active", "position", "updated_at"])
    return emp


def sim_say(row_id, text: str):
    """ลูกค้าจำลองพิมพ์ข้อความเข้ามา (ผ่านเส้นทางเดียวกับของจริง: เก็บแชท → เริ่ม/ต่อรอบรอ)"""
    import uuid
    o = ChatOwner.objects.select_related("profile").filter(pk=row_id).first()
    if not o or not is_sim_row(o):
        return None
    now = timezone.now()
    g = GroupChat.objects.create(
        chat_type=GroupChat.USER, message_id="test:%s" % uuid.uuid4().hex,
        sender_id=o.profile.user_id, sender_name=o.profile.show_name, direction=GroupChat.IN,
        msg_type=GroupChat.TEXT, text=(text or "")[:2000], channel="test", sent_at=now)
    LineProfile.objects.filter(pk=o.profile_id).update(msg_count=F("msg_count") + 1, last_seen=now)
    return note_customer_message(o.profile.user_id, now, preview_of(g))


def sim_customer(text: str = ""):
    """สร้างลูกค้าจำลอง 1 คน + ข้อความแรก → เข้าคิวรอรับของทีมที่เวรวันนี้"""
    import uuid
    n = LineProfile.objects.filter(user_id__startswith=SIM_PREFIX).count() + 1
    prof = LineProfile.objects.create(
        user_id=SIM_PREFIX + uuid.uuid4().hex[:12], display_name="ลูกค้าทดสอบ %d" % n,
        channel="test", source=LineProfile.USER, msg_count=0)
    o = _row_for(prof)
    return sim_say(o.id, text or "สวัสดีครับ สนใจรถครับ (ข้อความทดสอบ)")


def sim_counts() -> dict:
    return {"customers": LineProfile.objects.filter(user_id__startswith=SIM_PREFIX).count(),
            "sellers": Employee.objects.filter(nickname__startswith=TEST_PREFIX).count(),
            "realHeld": _test_held().count()}


def sim_clear(by: str = "") -> dict:
    """ล้างข้อมูลทดสอบทั้งหมด — ลูกค้าจำลอง + แชท + บัญชีเซลล์จำลอง

    ลูกค้าจริงที่บัญชีจำลองเผลอรับไว้ → **คืนคิว** (ไม่งั้นลูกค้าจริงค้างอยู่กับบัญชีที่ไม่มีใครใช้)
    ข้อความที่บัญชีจำลองเคยส่งหาลูกค้าจริงไม่ถูกลบ — มันถูกส่งออกไปจริงแล้ว ต้องอยู่ในประวัติ
    ★ บัญชีจริงใน `test_accounts` (เช่น Wattanakit): คืนลูกค้าที่ถือไว้เข้าคิวเหมือนกัน แต่ **ไม่ลบตัวคน/ประวัติ**
    """
    released = 0
    for o in _test_held():
        if assign(o.id, None, by=by or "ล้างข้อมูลทดสอบ")[0]:
            released += 1
    msgs = GroupChat.objects.filter(sender_id__startswith=SIM_PREFIX).delete()[0]
    sims = LineProfile.objects.filter(user_id__startswith=SIM_PREFIX)
    n_c = sims.count()
    sims.delete()                                   # ChatOwner + ประวัติ + CustomerNeed หายตาม (CASCADE)
    ChatOwnerLog.objects.filter(emp_name__startswith=TEST_PREFIX).delete()
    testers = Employee.objects.filter(nickname__startswith=TEST_PREFIX)
    n_t = testers.count()
    testers.delete()
    return {"customers": n_c, "messages": msgs, "sellers": n_t, "released": released}


# ★ 7 ต.ค.69 ถอดแท็บ "เลยเวลา" (overdue) ออก — ทีมตอบในแอป LINE OA Manager ซึ่ง LINE ไม่ส่งกลับมา = ค้างเลยเวลาหมด
#   ลิงก์เก่า ?view=overdue ตกไปหน้าเริ่มต้น (รอรับ) เอง · นาฬิกา/สถิติเวลาตอบยังเก็บเหมือนเดิม
VIEWS = ("queue", "tocode", "mine", "owned", "all")


def inbox(view: str, me=None, admin: bool = False, q: str = "", seller_id: int = 0,
          limit: int = 200, src: str = "", flt=None) -> list:
    """แถวของลิสต์ด้านซ้าย — สิทธิ์ถูกเช็คที่ view ก่อนเรียก (เซลล์ได้แค่ queue/mine)

    `flt` = ตัวกรองหน้ารวมแชท (crm.FILTER_KEYS) · ขั้น/ความร้อน/รถใหม่ตรง คิดใน Python (ค่าที่คำนวณเอง)
    """
    from . import crm
    now = timezone.now()
    qs = ChatOwner.objects.select_related("profile", "fb_profile", "owner", "lead")
    if view == "queue":
        qs = qs.filter(owner__isnull=True, awaiting_since__isnull=False).order_by("due_at")
    elif view == "tocode":                   # แอดมินเท่านั้น (เช็คที่ view) — คนที่รอคำตอบขึ้นก่อน ตามเส้นตาย
        qs = to_code(qs).order_by(F("due_at").asc(nulls_last=True), F("last_at").desc(nulls_last=True))
    elif view == "pending":                  # กลุ่ม "รอกดรับ" ของห้องพัก Lead (แอดมิน · ไม่อยู่ใน VIEWS — เรียกจาก api_inbox เท่านั้น)
        qs = pending_park(qs).order_by(F("last_in_at").desc(nulls_last=True))
    elif view == "buyroom":                  # ★ 11 ต.ค.69 แท็บ "รับซื้อรถ" ของห้องพัก Lead (แอดมิน · เรียกจาก api_inbox เท่านั้น)
        qs = buy_room(qs).order_by(F("last_in_at").desc(nulls_last=True))
    elif view == "mine":
        qs = qs.filter(owner=me) if me else qs.none()
        qs = qs.order_by(F("due_at").asc(nulls_last=True), F("last_at").desc(nulls_last=True))
    elif view == "owned":
        qs = qs.filter(owner__isnull=False).order_by(F("last_at").desc(nulls_last=True))
    else:
        qs = qs.order_by(F("last_at").desc(nulls_last=True))
    if seller_id and admin:
        qs = qs.filter(owner_id=seller_id)
    if src == "fb":                          # ตัวกรองช่องทาง (Facebook / LINE)
        qs = qs.filter(fb_profile__isnull=False)
    elif src == "line":
        qs = qs.filter(profile__isnull=False)
    elif src in ("tiktok", "other"):         # ไม่มีแชท TikTok/อื่นๆ ใน Connect — ลีดพวกนี้มาจากห้องพัก Lead เท่านั้น
        qs = qs.none()
    q = (q or "").strip()
    if q:
        qs = qs.filter(Q(profile__display_name__icontains=q) | Q(profile__nickname__icontains=q)
                       | Q(fb_profile__display_name__icontains=q)
                       | Q(last_preview__icontains=q) | Q(lead__customer_name__icontains=q)
                       | Q(lead__phone__contains=re.sub(r"\D", "", q) or q) | Q(lead__code__icontains=q)
                       | Q(lead__tags__icontains=q))
    flt = flt or {}
    if flt:
        qs = crm.db_filter(qs, flt, now)
    if crm.needs_python(flt):
        objs = crm.py_filter(list(qs[:1500]), flt, now)[:limit]
    else:
        objs = list(qs[:limit])
    amap = crm.next_appt_map([o.id for o in objs])
    mm = crm.match_map()
    pend = None
    if admin:
        pend = (set(o.id for o in objs) if view == "pending" else
                set(pending_park(ChatOwner.objects.filter(id__in=[o.id for o in objs])).values_list("id", flat=True)))
    return [row_json(o, me, now, appt_map=amap, matches=mm, pend=pend) for o in objs]


def counts(me=None, admin: bool = False) -> dict:
    now = timezone.now()
    base = ChatOwner.objects
    # ★ 6 ต.ค.69 — ลูกค้า Facebook ของเซลล์ = สิทธิ์เก็บข้อมูลเท่านั้น (ตอบจาก Connect ไม่ได้ · slippost.FB_DATA_ONLY)
    #   → ไม่นับเป็น "รอตอบ/เลยเวลา" ของเซลล์ (ป้ายตัวเลขจะเตือนเรื่องที่เขาทำอะไรไม่ได้) · แอดมินยังเห็นในเลยเวลาตามเดิม
    wait = base.filter(owner=me, awaiting_since__isnull=False) if me else base.none()
    if not admin:
        wait = wait.filter(fb_profile__isnull=True)
    out = {
        "queue": base.filter(owner__isnull=True, awaiting_since__isnull=False).count(),
        "mine": base.filter(owner=me).count() if me else 0,
        "mineWaiting": wait.count() if me else 0,
        "mineOverdue": wait.filter(due_at__lte=now).count() if me else 0,
    }
    if admin:
        out.update({
            "owned": base.filter(owner__isnull=False).count(),
            "all": base.count(),
            "tocode": to_code(base.all()).count(),
            "pending": pending_park(base.all()).count(),     # ให้เบอร์แล้ว รอกดรับ (ป้ายเมนูห้องพัก Lead)
            "buyroom": buy_room(base.all()).count(),         # ★ 11 ต.ค.69 ลีดรับซื้อรถ รอส่งจัดซื้อ (แท็บ "รับซื้อรถ")
        })
    return out


def _files(o, src: str, m) -> list:
    """ไฟล์แนบของข้อความ (รูป/วิดีโอ/เสียง/ไฟล์) — โหลดไม่ได้/ไม่มี = [] · พังต้องไม่ทำให้เปิดแชทไม่ได้"""
    if not m.has_media:
        return []
    if m.direction == "out" and (m.extra or {}).get("out_file"):   # ★ 16 ต.ค.69 รูปที่เราส่งหาลูกค้า (chatplus.send_image)
        from .chatplus import out_files
        return out_files(m)
    try:
        from .chatmedia import files_json
        return files_json(o.id, src, m)
    except Exception:
        return []


def messages(o, limit: int = 200, since=None) -> list:
    """บทสนทนาทั้ง 2 ฝั่ง เก่า→ใหม่ · `since` = เฉพาะข้อความลูกค้าตั้งแต่เวลานั้น (คิวรอรับ)"""
    if is_fb(o):
        fp = o.fb_profile
        fq = FbChat.objects.filter(thread_id=fp.thread_id) if fp.thread_id else FbChat.objects.none()
        if since:
            fq = fq.filter(sent_at__gte=since, direction=FbChat.IN)
        frows = list(fq.order_by("-sent_at", "-id")[:limit])
        frows.reverse()
        ins = [m.sent_at for m in frows if m.direction != FbChat.OUT]

        def _by(m):
            if m.direction != FbChat.OUT:
                return ""
            if m.sent_by_name:
                return m.sent_by_name
            # ขาออกที่ตอบใน Facebook เอง ไม่บอกว่าใครตอบ (เป็นชื่อเพจ) — บอกว่ามาจากไหนแทน
            # ออกตามหลังข้อความลูกค้าไม่เกิน FB_AUTO_SEC = ข้อความอัตโนมัติของเพจ (ไม่นับเป็นการตอบ)
            return "ตอบอัตโนมัติ (เพจ)" if any(_fb_auto(m.sent_at, t) for t in ins) else "ตอบใน Facebook"
        return [{
            "at": _iso(m.sent_at), "text": fb_preview(m), "type": m.msg_type or "", "media": bool(m.has_media),
            "dir": m.direction or "in", "by": _by(m),
            # ★ 11 ต.ค.69 รูป/ไฟล์ที่ส่งในแชท — ลิงก์ผ่าน /connect/api/media (เช็คสิทธิ์) · chatmedia.py
            "files": _files(o, "f", m),
            "id": "f%d" % m.pk,
        } for m in frows]
    qs = GroupChat.objects.filter(sender_id=o.profile.user_id).exclude(chat_type=GroupChat.GROUP)
    if since:
        qs = qs.filter(sent_at__gte=since, direction=GroupChat.IN)
    rows = list(qs.order_by("-sent_at", "-id")[:limit])
    rows.reverse()
    return [{
        "at": _iso(g.sent_at),
        "text": preview_of(g),
        "type": g.msg_type or "",
        "media": bool(g.has_media),
        "dir": g.direction or "in",
        "by": g.sent_by_name or "",
        "files": _files(o, "l", g),
        "id": "l%d" % g.pk,                       # ★ 12 ต.ค.69 อ้างข้อความ (ไฮไลต์ · ป้ายที่มาของช่องข้อมูล) — ไม่ใช่ LINE id
    } for g in rows]


def history(o, limit: int = 30) -> list:
    return [{
        "at": _iso(l.at), "action": l.action, "label": l.get_action_display(),
        "emp": l.emp_name, "by": l.by_name, "waitSec": l.wait_sec, "onTime": l.on_time,
        "note": l.note,
    } for l in o.logs.all()[:limit]]


def stats(days: int = 7) -> dict:
    """เวลาตอบรายคน — จากประวัติ (คำตอบที่ปิดรอบรอเท่านั้น) · รับลูกค้ากี่คน · เลยเวลากี่ครั้ง"""
    since = timezone.now() - timedelta(days=days)
    per = {}

    def P(name, team=""):
        r = per.setdefault(name or "(ไม่ทราบ)", {"name": name or "(ไม่ทราบ)", "team": team,
                                                  "claims": 0, "replies": 0, "onTime": 0,
                                                  "waits": [], "late": 0})
        if team and not r["team"]:
            r["team"] = team
        return r

    unowned_late = 0
    for l in ChatOwnerLog.objects.filter(at__gte=since).only(
            "action", "emp_name", "by_name", "team", "wait_sec", "on_time"):
        if l.action == ChatOwnerLog.CLAIM:
            P(l.emp_name, l.team)["claims"] += 1
        elif l.action == ChatOwnerLog.REPLY:
            r = P(l.emp_name or l.by_name, l.team)
            r["replies"] += 1
            r["onTime"] += 1 if l.on_time else 0
            if l.wait_sec is not None:
                r["waits"].append(l.wait_sec)
        elif l.action == ChatOwnerLog.ESCALATE:
            if l.emp_name:
                P(l.emp_name, l.team)["late"] += 1
            else:
                unowned_late += 1
    rows = []
    for r in per.values():
        w = r.pop("waits")
        r["medianMin"] = round(statistics.median(w) / 60, 1) if w else None
        r["onTimePct"] = round(100 * r["onTime"] / r["replies"]) if r["replies"] else None
        rows.append(r)
    rows.sort(key=lambda r: (-r["replies"], -r["claims"], r["name"]))
    return {"days": days, "rows": rows, "unownedLate": unowned_late}



# ─────────────────────────────────────────────────────────────
#  แชท Facebook → Connect ทุกนาที (เรียกจาก tick ใน thread แยก — ยิง Graph API ห้ามหน่วง cron_tick)
# ─────────────────────────────────────────────────────────────
_FB_RUN = {"busy": False, "at": 0.0}


def fb_poll_due(now=None, c=None) -> bool:
    """ถึงรอบดึงแชท FB สำรองหรือยัง — เช็คจาก KV `fb_live_last` (ร่วมทุก worker ของ gunicorn)
    ★ ถ้าจำเวลาแค่ใน process: 3 worker = ดึงถี่ขึ้น 3 เท่าโดยไม่มีใครรู้ (cron ยิงสลับ worker)"""
    import time as _t
    c = c or cfg()
    every = c.get("fb_poll_min", DEFAULTS["fb_poll_min"]) * 60
    if _t.time() - _FB_RUN["at"] < every:
        return False
    try:
        from datetime import datetime as _dt
        from dashboard.services import cache_store
        at = ((cache_store.get_kv("fb_live_last") or {}).get("data") or {}).get("at") or ""
        if at and ((now or timezone.now()) - _dt.fromisoformat(at)).total_seconds() < every:
            return False
    except Exception:
        pass
    return True


def fb_tick_bg() -> dict:
    """เริ่มดึงแชท FB สำรองใน thread แยก (ปิดสวิตช์/กำลังทำอยู่/ยังไม่ถึงรอบ = ข้าม) · ผลรอบล่าสุดอยู่ KV fb_live_last"""
    import threading
    import time as _t
    if not BG_FILL or not fb_on() or _FB_RUN["busy"] or not fb_poll_due():
        return {}
    _FB_RUN.update(busy=True, at=_t.time())
    try:                                        # จองรอบไว้ก่อน — worker อื่นที่โดน cron ยิงนาทีถัดไปจะไม่ดึงซ้อน
        from dashboard.services import cache_store
        prev = (cache_store.get_kv("fb_live_last") or {}).get("data") or {}
        cache_store.set_kv("fb_live_last", dict(prev, at=timezone.now().isoformat(), running=True))
    except Exception:
        pass

    def _work():
        res = {}
        try:
            from .fb_sync import sync_live
            res = sync_live()
        except Exception as e:
            res = {"error": str(e)[:200]}
        finally:
            _FB_RUN["busy"] = False
            try:
                from dashboard.services import cache_store
                cache_store.set_kv("fb_live_last", dict(res, at=timezone.now().isoformat()))
            except Exception:
                pass
            try:
                from django.db import connection
                connection.close()
            except Exception:
                pass

    threading.Thread(target=_work, daemon=True).start()
    return {"started": True}
