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

import re
import statistics
from datetime import date, timedelta

from django.db import IntegrityError
from django.db.models import F, Q
from django.utils import timezone

from .models import ChatLead, ChatOwner, ChatOwnerLog, Employee, GroupChat, LineProfile

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
}

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
    if out.get("alert_on") and not out.get("alert_group"):
        errs.append("เปิดแจ้งเตือนเข้ากลุ่ม LINE แล้ว แต่ยังไม่ได้เลือกกลุ่ม")
    return out, errs


def save_cfg(c: dict) -> bool:
    try:
        from dashboard.services import cache_store
        cache_store.set_kv(CFG_KEY, {k: c[k] for k in DEFAULTS if k in c})
        return True
    except Exception:
        return False


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
    """พนักงานที่อยู่ทีมขาย — ตัวเลือกตอนแอดมินโอนลูกค้า"""
    out = []
    for e in Employee.objects.filter(active=True).order_by("nickname"):
        t = team_of(e)
        if t:
            out.append({"id": e.id, "name": e.nickname, "team": t})
    out.sort(key=lambda r: (r["team"], r["name"]))
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
    p = o.profile
    out = {"pic": o.picture_url or "", "name": p.show_name, "lineName": p.display_name or "",
           "firstSeen": _iso(p.first_seen), "lastSeen": _iso(p.last_seen), "msgs": p.msg_count or 0,
           "claimedAt": _iso(o.claimed_at), "full": access == "full"}
    if access != "full":
        return out
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
    out.update({"status": p.status_message or "", "language": p.language or "",
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


def note_customer_message(user_id: str, at=None, preview: str = "", picture: str = ""):
    """ลูกค้าส่งข้อความเข้ามา — เรียกจาก `store_chat` (แชท 1:1 เท่านั้น)

    เริ่ม "รอบรอคำตอบ" ถ้ายังไม่มี · ลูกค้าส่งรัวๆ หลายข้อความ = รอบเดิม (เส้นตายไม่เลื่อน)
    `picture` = ลิงก์รูปโปรไฟล์ที่ `touch_profile` เพิ่งดึงมา (ว่าง = ไม่ได้ดึงรอบนี้)
    """
    if not user_id:
        return None
    prof = LineProfile.objects.filter(user_id=user_id).first()
    if not prof or prof.is_employee:
        return None
    at = at or timezone.now()
    c = cfg()
    o = _row_for(prof)

    # เจ้าของถูกปิดใช้งานในทะเบียน (ลาออก) → คืนคิว ไม่งั้นลูกค้าค้างอยู่กับคนที่ไม่มีวันตอบ
    if o.owner_id and not o.owner.active:
        _log(o, ChatOwnerLog.RELEASE, emp=o.owner, by="ระบบ",
             note="เซลล์ไม่ได้ทำงานแล้ว — คืนคิวอัตโนมัติ")
        o.owner, o.claimed_at, o.first_reply_at = None, None, None

    sim = is_sim(user_id)
    new_round = o.awaiting_since is None
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
    if picture:
        o.picture_url, o.picture_at = picture[:500], timezone.now()
    o.save()
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


def note_reply(user_id: str, emp=None, at=None, preview: str = "", by: str = ""):
    """เราตอบลูกค้าสำเร็จ — เรียกจาก `chat.send_reply` (ทั้งจากหน้า Connect และพาเนลแชทเดิม)

    ตอบแล้ว = จบรอบรอ · จดเวลาที่ลูกค้ารอไว้เป็นสถิติ (เฉพาะคำตอบที่ปิดรอบ)
    """
    prof = LineProfile.objects.filter(user_id=user_id).first()
    if not prof or prof.is_employee:
        return None
    at = at or timezone.now()
    o = _row_for(prof)
    if o.awaiting_since:
        _log(o, ChatOwnerLog.REPLY, emp=emp, by=by or (emp.nickname if emp else ""),
             team=team_of(emp) or o.team,
             wait_sec=max(0, int((at - o.awaiting_since).total_seconds())),
             on_time=(at <= o.due_at) if o.due_at else None)
    if emp and o.owner_id == emp.id and not o.first_reply_at:
        o.first_reply_at = at
    o.awaiting_since = o.due_at = o.escalated_at = None
    o.last_out_at = at
    o.last_at, o.last_preview, o.last_dir = at, (preview or "")[:200], "out"
    o.save()
    return o


# ─────────────────────────────────────────────────────────────
#  งานของคน: รับ · โอน · ปล่อย · ไม่ต้องตอบ
# ─────────────────────────────────────────────────────────────
def claim(row_id, emp, admin: bool = False):
    """เซลล์กด "รับลูกค้า" → (ok, ข้อความ)  · ใครกดก่อนได้ไป ล็อกที่ฐานข้อมูล"""
    if not emp:
        return False, "บัญชีนี้ยังไม่ได้ผูกกับทะเบียนพนักงาน — แจ้งแอดมินให้เพิ่มชื่อเล่นในหน้า \"พนักงาน\""
    o = ChatOwner.objects.select_related("owner", "profile").filter(pk=row_id).first()
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
    return True, "รับลูกค้าแล้ว — อย่าลืมตอบก่อนเส้นตาย"


def assign(row_id, emp=None, by: str = ""):
    """แอดมินโอนลูกค้าให้เซลล์ (`emp`) หรือปล่อยคืนคิว (`emp=None`) → (ok, ข้อความ)"""
    o = ChatOwner.objects.select_related("owner", "profile").filter(pk=row_id).first()
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
        _log(o, ChatOwnerLog.RELEASE, emp=old, by=by, note="แอดมินปล่อยคืนคิว")
        return True, "ปล่อยคืนคิวแล้ว — เซลล์ทีมที่เวรวันนี้กดรับได้"
    if not emp.active:
        return False, "%s ถูกปิดใช้งานในทะเบียนพนักงาน" % emp.nickname
    if old and old.id == emp.id:
        return True, "เป็นลูกค้าของ %s อยู่แล้ว" % emp.nickname
    o.owner, o.claimed_at, o.first_reply_at = emp, now, None
    o.team = team_of(emp) or o.team
    o.save()
    _log(o, ChatOwnerLog.ASSIGN, emp=emp, by=by,
         note=("โอนจาก %s" % old.nickname) if old else "โอนจากคิว")
    return True, "โอนให้ %s แล้ว" % emp.nickname


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
    c = cfg()
    rows = list(ChatOwner.objects.select_related("owner", "profile")
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
        return {}
    out = {"escalated": len(hit)}
    real = [o for o in hit if not is_sim(o.profile.user_id)]       # ลูกค้าจำลองไม่ส่ง LINE
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
        lines.append("• %s — %s · รอ %d นาที" % (o.profile.show_name, who, mins))
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
            o.profile.show_name, c["sla_min"], _link(o))
    else:
        people = team_members(o.team)
        text = "💬 มีลูกค้าใหม่ทักมา (%s) — เวรทีม %s กดรับได้ที่\n%s" % (
            o.profile.show_name, o.team, _link(o))
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
    profs = list(LineProfile.objects.filter(is_employee=False, owner_row__isnull=True)[:2000])
    if not profs:
        return 0
    made = []
    for p in profs:
        g = (GroupChat.objects.filter(sender_id=p.user_id).exclude(chat_type=GroupChat.GROUP)
             .order_by("-sent_at", "-id").first())
        if not g:
            continue
        made.append(ChatOwner(profile=p, last_at=g.sent_at, last_preview=preview_of(g)[:200],
                              last_dir=g.direction or "in",
                              last_in_at=g.sent_at if g.direction != GroupChat.OUT else None,
                              last_out_at=g.sent_at if g.direction == GroupChat.OUT else None))
    if made:
        ChatOwner.objects.bulk_create(made, ignore_conflicts=True)
    return len(made)


# ─────────────────────────────────────────────────────────────
#  ข้อมูลสำหรับหน้าเว็บ
# ─────────────────────────────────────────────────────────────
def _iso(dt):
    return timezone.localtime(dt).isoformat(timespec="seconds") if dt else ""


def row_json(o, me=None, now=None) -> dict:
    now = now or timezone.now()
    p = o.profile
    ld = lead_of(o, create=False)
    return {
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
        "escalated": bool(o.escalated_at),
        "mine": bool(me and o.owner_id == me.id),
        "msgs": p.msg_count or 0,
        "pic": o.picture_url or "",
        "sim": is_sim(p.user_id),
    }


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
    "live": 60, "more": 500,
}
LEAD_TYPES = ["Very Hot", "Hot", "TLD / Hot", "MerHot", "TLD", "Moderate", "BLD", "Hot RB", "Hot RJ", "RJ"]
CUSTOMER_TYPES = ["พนักงานบริษัท", "เจ้าของธุรกิจส่วนตัว", "ข้าราชการ/รัฐวิสาหกิจ", "ค้าขาย", "เกษตกร/ปศุสัตว์",
                  "Rider/driver", "ฟรีแลนด์", "อาชีพอื่นๆ", "ไม่แจ้งอาชีพ", "ไม่มีอาชีพ"]
HUMAN = "คน"                      # ค่าใน `auto` = คนแก้ช่องนี้แล้ว → ระบบห้ามเติมทับ
_SLIP_EVERY_MIN = 30              # หาใบจ่ายลีดในกลุ่มซ้ำได้ทุกกี่นาที (ต่อลูกค้า)
_VOCAB = {"at": 0.0, "cars": [], "names": {}, "channels": []}


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
    """ชื่อรุ่นรถ + ช่องทาง จากผลสรุปแดชบอร์ด (dropdown ของชีตลีด = ชุดที่สะอาดที่สุด) · แคช 1 ชม.

    อ่านไม่ได้/ยังไม่มีผลสรุป (เครื่อง dev) = ลิสต์ว่าง → ระบบใช้แค่ชื่อรุ่นภาษาไทยของ `leadgroup.parse_specs`
    """
    import time
    if _VOCAB["at"] and time.time() - _VOCAB["at"] < 3600:
        return _VOCAB
    cars, names, channels = [], {}, []
    try:
        from dashboard.services.purchase_report import _demand_by_model
        demand, names = _demand_by_model()
        cars = sorted(demand, key=lambda k: (-len(k), k))           # ยาวก่อน (civicfc ต้องชนะ civic)
    except Exception:
        cars, names = [], {}
    try:
        from dashboard.services.cache_store import get_kv
        blob = get_kv("main") or {}
        data = blob.get("data", blob) if isinstance(blob, dict) else {}
        cnt = {}
        for _m, chs in ((data or {}).get("leadChannelByMonth") or {}).items():
            for ch, n in (chs or {}).items():
                if ch:
                    cnt[ch] = cnt.get(ch, 0) + int(n or 0)
        channels = [c for c, _ in sorted(cnt.items(), key=lambda x: -x[1])][:40]
    except Exception:
        channels = []
    _VOCAB.update({"at": time.time(), "cars": cars, "names": names, "channels": channels})
    return _VOCAB


def car_in(text: str):
    """(รุ่นแบบชีต, ข้อความเดิม) ถ้าข้อความนี้พูดถึงรุ่นรถ — ไม่เจอ = None (ไม่เดา)"""
    t = (text or "").strip()
    if not t:
        return None
    v = _vocab()
    if v["cars"]:
        try:
            from dashboard.services.purchase_report import match_model
            k = match_model(t, v["cars"])
            if k:
                return v["names"].get(k, k), t
        except Exception:
            pass
    try:
        from .leadgroup import parse_specs
        m = parse_specs(t).get("car_model")
        if m:
            return m[:1].upper() + m[1:], t           # "camry" → "Camry" (หน้าตาเดียวกับชีต)
    except Exception:
        pass
    return None


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


def autofill(o, msgs=None) -> ChatLead:
    """เติมข้อมูลลีดอัตโนมัติ — **เฉพาะช่องที่ว่างและยังไม่เคยเติม** ไม่ทับสิ่งที่คนพิมพ์เด็ดขาด

    ที่มา: แชท (เบอร์ · รุ่นรถที่ถาม) · ระบบ (ช่องทาง · Admin ที่โอน/ตอบ) ·
    **ใบจ่ายลีดในกลุ่มจ่ายเบอร์** (Code/ADS/Account/ชื่อลูกค้า/ID LINE/ช่องทาง/รถ — ถ้าเบอร์หรือชื่อไลน์ตรง)
    `msgs` = ข้อความลูกค้า (เก่า→ใหม่) ที่โหลดมาแล้วสำหรับหน้าแชท (ไม่ต้อง query ซ้ำ)
    """
    lead = lead_of(o)
    if is_sim(o.profile.user_id):
        return lead
    auto = dict(lead.auto or {})
    changed = []

    def put(field, value, src):
        value = (str(value or "")).strip()
        if not value:
            return
        # ใบจ่ายลีดที่แอดมินโพสต์ = ข้อมูลจากคน → แทน "ค่าตั้งต้นของระบบ" ได้ (เช่น ช่องทาง LINE OA)
        #   แต่ไม่แทนสิ่งที่คนพิมพ์ในหน้านี้ และไม่แทนสิ่งที่จับได้จากแชท
        if auto.get(field) == "ระบบ" and src == "ใบจ่ายลีด":
            pass
        elif getattr(lead, field) or field in auto:
            return
        setattr(lead, field, value[:LEAD_FIELDS.get(field, 200)])
        auto[field] = src
        changed.append(field)

    if msgs is None:
        msgs = [g.text for g in GroupChat.objects.filter(sender_id=o.profile.user_id, direction=GroupChat.IN)
                .exclude(chat_type=GroupChat.GROUP).order_by("sent_at", "id")[:200] if g.text]
    ph = phones_in(msgs)
    if ph:
        put("phone", ph[0], "แชท")
    for t in msgs:
        hit = car_in(t)
        if hit:
            put("car_model", hit[0], "แชท")
            put("car_text", hit[1][:200], "แชท")
            break

    # ใบจ่ายลีดที่แอดมินโพสต์ไว้แล้ว — หาซ้ำได้ทุก 30 นาที (ไม่ยิง query ทุกครั้งที่เปิดแชท)
    now = timezone.now()
    last = auto.get("_slip_at") or ""
    try:
        from datetime import datetime as _dt
        stale = (not last) or (now - _dt.fromisoformat(last)) > timedelta(minutes=_SLIP_EVERY_MIN)
    except Exception:
        stale = True
    if not lead.code and stale:
        auto["_slip_at"] = now.isoformat()
        changed.append("_slip_at")
        hit = find_slip(lead.phone or (ph[0] if ph else ""), o.profile.display_name)
        if hit:
            d, g = hit
            for f, k in (("code", "lead_code"), ("ads", "ads"), ("account", "account"),
                         ("customer_name", "name"), ("line_id", "line_id"), ("channel", "channel"),
                         ("car_text", "car"), ("live", "live"), ("more", "more")):
                put(f, d.get(k, ""), "ใบจ่ายลีด")
            if d.get("phone"):
                put("phone", (phones_in([d["phone"]]) or [d["phone"]])[0], "ใบจ่ายลีด")
            auto["_slip"] = {"at": _iso(g.sent_at), "group": g.group_name or ""}

    # ช่องทาง = บัญชี LINE ที่ลูกค้าทักเข้ามา — ใช้ชื่อตามชีต ("Line@"/"LINE OA") ถ้ามีในลิสต์
    line_ch = next((c for c in _vocab()["channels"] if "line" in c.lower()), "LINE OA")
    put("channel", line_ch, "ระบบ")
    # Admin = คนที่โอนลูกค้าให้เซลล์ล่าสุด (ไม่มี = คนแรกที่ตอบลูกค้าที่ไม่ใช่เจ้าของ)
    adm = (ChatOwnerLog.objects.filter(chat=o, action=ChatOwnerLog.ASSIGN).exclude(by_name="")
           .order_by("-at").values_list("by_name", flat=True).first())
    if not adm:
        qs = GroupChat.objects.filter(sender_id=o.profile.user_id, direction=GroupChat.OUT).exclude(sent_by_name="")
        if o.owner_id:
            qs = qs.exclude(sent_by_name=o.owner.nickname)
        adm = qs.order_by("sent_at", "id").values_list("sent_by_name", flat=True).first()
    if adm and not adm.startswith(TEST_PREFIX):
        put("admin_name", adm, "ระบบ")

    if changed:
        lead.auto = auto
        lead.save()
    return lead


def lead_json(o, lead=None) -> dict:
    """ข้อมูลลีดสำหรับฟอร์ม + ช่องที่ระบบคำนวณเอง (ไม่เก็บซ้ำ)"""
    lead = lead or lead_of(o)
    p = o.profile
    contact = o.first_reply_at or (GroupChat.objects.filter(sender_id=p.user_id, direction=GroupChat.OUT)
                                   .order_by("sent_at").values_list("sent_at", flat=True).first())
    out = {k: getattr(lead, k) or "" for k in LEAD_FIELDS}
    out.update({
        "tags": list(lead.tags or []),
        "auto": {k: v for k, v in (lead.auto or {}).items() if not k.startswith("_")},
        "slip": (lead.auto or {}).get("_slip") or None,
        # ช่องอัตโนมัติ (คำนวณจากระบบ ไม่ให้แก้มือ — แก้แล้วจะไม่ตรงกับของจริง)
        "leadAt": _iso(p.first_seen),
        "seller": o.owner.nickname if o.owner_id else "",
        "contactAt": _iso(contact),
        "updates": ChatOwnerLog.objects.filter(chat=o, action=ChatOwnerLog.REPLY).count(),
        "lastUpdate": _iso(o.last_out_at),
        "lineName": p.display_name or "",
        "updatedBy": lead.updated_by or "",
    })
    out["slipText"] = slip_text(o, lead)
    return out


def slip_text(o, lead=None) -> str:
    """ใบจ่ายลีดแบบย่อ — รูปแบบเดียวกับที่แอดมินโพสต์ในกลุ่มจ่ายเบอร์ (`leadgroup.parse_leadsheet` อ่านกลับได้)"""
    lead = lead or lead_of(o)
    p = o.profile
    car = lead.car_text or lead.car_model
    lines = [
        "Ac Lead No. %s" % (lead.code or "-"),
        "Ads : %s" % (lead.ads or "-"),
        "ชื่อ Account: %s" % (lead.account or "-"),
        "ชื่อลูกค้า : %s" % (lead.customer_name or "-"),
        "ID LINE : %s" % (lead.line_id or "-"),
        "ชื่อไลน์ : %s" % (p.display_name or "-"),
        "เบอร์โทร : %s" % (lead.phone or "-"),
        "ช่องทาง : %s" % (lead.channel or "-"),
        "รถ : %s" % (car or "-"),
        "ไลฟ์ : %s" % (lead.live or "-"),
        "เพิ่มเติม : %s" % (lead.more or "-"),
    ]
    if o.owner_id:
        lines.append("@%s" % o.owner.nickname)
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
        lead.tags = tags[:12]
        lead.updated_by = (by or "")[:80]
        lead.save(update_fields=["tags", "updated_by", "updated_at"])
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
    lead.auto = auto
    lead.updated_by = (by or "")[:80]
    lead.save(update_fields=[field, "auto", "updated_by", "updated_at"])
    return True, "บันทึกแล้ว"


def lead_options() -> dict:
    """ตัวเลือกช่วยกรอก (datalist) — ช่องทางจากชีตลีดจริง · สาขา/แอดมินจากที่เคยกรอก"""
    v = _vocab()
    used = ChatLead.objects.exclude(branch="").values_list("branch", flat=True).distinct()[:30]
    branches = sorted(set(used))
    try:
        from cars.models import Branch
        branches = sorted(set(branches) | set(Branch.objects.filter(active=True).values_list("name", flat=True)))
    except Exception:
        pass
    tags = set()
    for ts in ChatLead.objects.exclude(tags=[]).values_list("tags", flat=True)[:300]:
        tags |= set(ts or [])
    return {"types": LEAD_TYPES, "customerTypes": CUSTOMER_TYPES, "channels": v["channels"],
            "branches": branches, "tags": sorted(tags)[:40]}


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
    return bool(emp) and (getattr(emp, "nickname", "") or "").startswith(TEST_PREFIX)


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
    if not o or not is_sim(o.profile.user_id):
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
            "realHeld": ChatOwner.objects.filter(owner__nickname__startswith=TEST_PREFIX)
                                         .exclude(profile__user_id__startswith=SIM_PREFIX).count()}


def sim_clear(by: str = "") -> dict:
    """ล้างข้อมูลทดสอบทั้งหมด — ลูกค้าจำลอง + แชท + บัญชีเซลล์จำลอง

    ลูกค้าจริงที่บัญชีจำลองเผลอรับไว้ → **คืนคิว** (ไม่งั้นลูกค้าจริงค้างอยู่กับบัญชีที่ไม่มีใครใช้)
    ข้อความที่บัญชีจำลองเคยส่งหาลูกค้าจริงไม่ถูกลบ — มันถูกส่งออกไปจริงแล้ว ต้องอยู่ในประวัติ
    """
    released = 0
    for o in ChatOwner.objects.filter(owner__nickname__startswith=TEST_PREFIX) \
                              .exclude(profile__user_id__startswith=SIM_PREFIX):
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


VIEWS = ("overdue", "queue", "mine", "owned", "all")


def inbox(view: str, me=None, admin: bool = False, q: str = "", seller_id: int = 0,
          limit: int = 200) -> list:
    """แถวของลิสต์ด้านซ้าย — สิทธิ์ถูกเช็คที่ view ก่อนเรียก (เซลล์ได้แค่ queue/mine)"""
    now = timezone.now()
    qs = ChatOwner.objects.select_related("profile", "owner", "lead")
    if view == "overdue":
        qs = qs.filter(awaiting_since__isnull=False, due_at__lte=now).order_by("due_at")
    elif view == "queue":
        qs = qs.filter(owner__isnull=True, awaiting_since__isnull=False).order_by("due_at")
    elif view == "mine":
        qs = qs.filter(owner=me) if me else qs.none()
        qs = qs.order_by(F("due_at").asc(nulls_last=True), F("last_at").desc(nulls_last=True))
    elif view == "owned":
        qs = qs.filter(owner__isnull=False).order_by(F("last_at").desc(nulls_last=True))
    else:
        qs = qs.order_by(F("last_at").desc(nulls_last=True))
    if seller_id and admin:
        qs = qs.filter(owner_id=seller_id)
    q = (q or "").strip()
    if q:
        qs = qs.filter(Q(profile__display_name__icontains=q) | Q(profile__nickname__icontains=q)
                       | Q(last_preview__icontains=q) | Q(lead__customer_name__icontains=q)
                       | Q(lead__phone__contains=re.sub(r"\D", "", q) or q) | Q(lead__code__icontains=q)
                       | Q(lead__tags__icontains=q))
    return [row_json(o, me, now) for o in qs[:limit]]


def counts(me=None, admin: bool = False) -> dict:
    now = timezone.now()
    base = ChatOwner.objects
    out = {
        "queue": base.filter(owner__isnull=True, awaiting_since__isnull=False).count(),
        "mine": base.filter(owner=me).count() if me else 0,
        "mineWaiting": base.filter(owner=me, awaiting_since__isnull=False).count() if me else 0,
        "mineOverdue": (base.filter(owner=me, awaiting_since__isnull=False, due_at__lte=now).count()
                        if me else 0),
    }
    if admin:
        out.update({
            "overdue": base.filter(awaiting_since__isnull=False, due_at__lte=now).count(),
            "owned": base.filter(owner__isnull=False).count(),
            "all": base.count(),
        })
    return out


def messages(o, limit: int = 200, since=None) -> list:
    """บทสนทนาทั้ง 2 ฝั่ง เก่า→ใหม่ · `since` = เฉพาะข้อความลูกค้าตั้งแต่เวลานั้น (คิวรอรับ)"""
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
