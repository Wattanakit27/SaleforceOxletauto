"""บรอดแคสต์ลูกค้า — ค้นหากลุ่มลูกค้า → ดาวน์โหลดรายชื่อ / ส่ง LINE ในระบบ (★ 21 ต.ค.69 · เจ้าของสั่ง)

*"มันจะมีกรณีที่นำไปใช้งานอย่าง Broadcast ซึ่งควรมีตัวค้นหา แล้วก็ Export รายชื่อหรือ Broadcast ภายในแอปได้เลยยิ่งดี
เช่น เรามีรถรุ่นปีกว่าเก่าเข้ามาใหม่ แต่ว่ายังหาลูกค้าที่ซื้อไม่ได้ เราก็จะ Broadcast ไปหากลุ่มลูกค้านั้นที่เราแท็กไว้แล้วว่า
"สนใจรถปีเก่าๆ""* · เจ้าของเลือก: ค้นหา + Export + ส่ง LINE · แอดมินเท่านั้น · ข้อความพิมพ์เอง + รูปที่อัปเอง + รูปรถจากสต็อก +
ลิงก์หน้ารถบนเว็บโชว์รูม

หน้าเว็บ `/crm/?p=bcast` · API `/crm/api/broadcast` (dashboard/crm_views.py)

กลุ่มลูกค้า = แถวลูกค้าใน Connect (`ChatOwner` · LINE + Facebook) ไม่รวมพนักงาน/ลูกค้าจำลอง · กรองด้วยแท็ก (`ChatLead.tags` —
แท็กที่คนใส่ในหน้า Connect + แท็กจากระบบอัตโนมัติ ยี่ห้อ/รุ่น/ช่วงรายได้) · ช่องทาง · คุยล่าสุดภายในกี่วัน · ขั้นของลีด ·
ลีดขาย/รับซื้อ · ผู้ดูแล · คำค้น · **แท็ก "ไม่รับข่าวสาร" ไม่ได้รับเสมอ** (ใส่แท็กนี้ในหน้า Connect เมื่อลูกค้าขอ)

ส่ง = LINE multicast ของ **บัญชีที่ลูกค้าแต่ละคนคุยอยู่** (`chat._channel_for` แบบทำทีเดียวทั้งกลุ่ม) · ครั้งละ 500 คน ·
`X-Line-Retry-Key` ต่อชุด (ส่งซ้ำชุดเดิม LINE ไม่ส่งซ้ำ) · ด่าน: สวิตช์ส่งหาลูกค้า (`chat.reply_on`) · ต้องส่งทดสอบหาตัวเอง
ด้วยเนื้อหาเดียวกันก่อน (ภายใน `TEST_VALID_H`) · จำนวนผู้รับที่หน้าเว็บยืนยันต้องตรงกับที่เซิร์ฟเวอร์นับได้ตอนกดส่ง ·
โควต้าข้อความเดือนนี้ของบัญชีต้องพอ · กดซ้ำ (client_id เดิม) = คืนผลเดิม ไม่ส่งซ้ำ
**ลูกค้า Facebook ส่งผ่านระบบไม่ได้** (Facebook ไม่ให้เพจส่งข่าวหาคนที่ไม่ได้ทักมาภายใน 24 ชม.) — ดาวน์โหลดรายชื่อไปใช้แทน

ส่งสำเร็จ = เก็บข้อความลงบทสนทนาของลูกค้าแต่ละคน (`GroupChat` message_id ขึ้นต้น `bc:` · เซลล์เห็นในแชทว่าส่งอะไรไป)
+ ประวัติ `ChatOwnerLog` "ส่งบรอดแคสต์" · **ไม่แตะนาฬิกาตอบ/สถานะยังไม่อ่าน** และ **ตัวจับคำในแชทไม่เห็นข้อความเหล่านี้**
(`connect.messages(bc=False)` โดยปริยาย) — ประโยคเดียวส่งหาหลายร้อยคน ห้ามกลายเป็นข้อมูลลีดของทุกคน

★ 21 ต.ค.69 ลิงก์ติดตาม + ส่งทดสอบหาทีม (แบบ MAAC · เจ้าของ "มีหน้าทดสอบส่งข้อความไปหาเขาก่อน … แนบลิงก์หรือซ่อนลิงก์แบบ flex
แท็กลูกค้าด้วยใครกด"): ลิงก์ ≤3 อัน แนบในข้อความ หรือซ่อนหลังปุ่ม (การ์ด Flex) + ปุ่ม "ดูรายละเอียดรถ" ของการ์ดรถ
→ ลิงก์ของลูกค้าแต่ละคนไม่ซ้ำกัน (`/b/<token>` · `click()`) → กดแล้วจดว่าใครกด (`BroadcastClick`) + ติดแท็กของลิงก์ให้
(ครั้งแรก) แล้วพาไปปลายทาง · มีลิงก์ = ส่งทีละคนเบื้องหลัง (multicast ใส่ลิงก์ต่างกันไม่ได้) · ส่งทดสอบเลือกคนในทีมได้ ≤10 คน
(`testers` · ลิงก์ทดสอบไม่ติดแท็กใคร แต่บอกหน้าเว็บว่าใครกดแล้ว)
"""
import csv
import hashlib
import hmac
import io
import json
import os
import re
import time
import uuid
from datetime import datetime, timedelta

import requests
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F, Max
from django.utils import timezone

from . import connect as C
from .models import Broadcast, BroadcastClick, ChatLead, ChatOwner, ChatOwnerLog, GroupChat

MULTICAST_URL = "https://api.line.me/v2/bot/message/multicast"
PUSH_URL = "https://api.line.me/v2/bot/message/push"
QUOTA_URL = "https://api.line.me/v2/bot/message/quota"
USAGE_URL = "https://api.line.me/v2/bot/message/quota/consumption"

BATCH = 500                 # LINE multicast รับผู้รับได้ไม่เกิน 500 ต่อครั้ง
MAX_RECIPIENTS = 3000       # ส่งครั้งเดียวไม่เกินนี้ (กันกดผิดกลุ่มแล้วส่งทั้งฐาน)
MAX_TEXT = 2000
MAX_IMAGES = 3
MAX_CARS = 6
TEST_VALID_H = 6            # ส่งทดสอบแล้วต้องส่งจริงภายในกี่ชั่วโมง (เนื้อหาเดิม)
SHOW_ROWS = 150             # รายชื่อที่โชว์บนหน้าเว็บ (ดาวน์โหลดได้ทั้งหมด)
OPTOUT_TAG = "ไม่รับข่าวสาร"
_OPTOUT = ("ไม่รับข่าวสาร", "ไม่รับข่าว", "ไม่รับโปร", "ไม่ต้องส่งข่าว")
_REL = re.compile(r"^chat_out/[0-9a-f]{32}\.jpg$")
KV_TEST = "bcast_test"
KV_TESTERS = "bcast_testers"     # คนในทีมที่เลือกส่งทดสอบครั้งล่าสุด (Employee.pk · 0 = ตัวเองที่ไม่มีในทะเบียน)
KV_TCLICK = "bcast_tclick"       # ใครกดลิงก์ในข้อความทดสอบ {hash12: {at, c: {emp: {ลำดับลิงก์: เวลา}}}}
JOB_KEY = "bcast_job:%d"         # งานส่งทีละคน (ข้อความต้นแบบ + รายชื่อ)
JOBST_KEY = "bcast_jobst:%d"     # ความคืบหน้าล่าสุด + คนที่ส่งไม่ถึง
BTAG_KEY = "_btags"              # ChatLead.auto — แท็กไหนติดจากการกดลิงก์บรอดแคสต์
MAX_LINKS = 3
MAX_URL = 1000
MAX_TITLE = 80
LINK_LABEL = 20                  # LINE จำกัดชื่อปุ่ม 20 ตัวอักษร
LINK_TAG = 30
MAX_TESTERS = 10
DEFAULT_TITLE = "รายละเอียดเพิ่มเติม"
PH = "__OXBCL%02d__"             # ตัวแทนลิงก์ในข้อความต้นแบบ → แทนด้วยลิงก์ของลูกค้าแต่ละคนตอนส่ง
SIG_LEN = 12
PUSH_WORKERS = 8                 # ส่งทีละคนพร้อมกันกี่สาย
PUSH_RATE = 40                   # ประมาณคน/วินาที (ไว้บอกเวลาโดยประมาณ)
FLUSH_N, FLUSH_SEC = 40, 3       # บันทึกความคืบหน้าทุก N คน หรือทุก N วินาที
JOB_STALE_SEC = 180              # งานไม่ขยับเกินนี้ = ถือว่าค้าง (เซิร์ฟเวอร์รีสตาร์ท) → ทำต่อ
JOB_LOCK = 7406070               # pg advisory lock (คู่กับเลขบรอดแคสต์)
_URL = re.compile(r"^https?://[^\s/?#'\"<>]+(?:[/?#][^\s'\"<>]*)?$", re.I)


class BError(Exception):
    """ทำไม่ได้ — ข้อความนี้โชว์ผู้ใช้ได้เลย"""


# ─────────────────────────── กลุ่มลูกค้า ───────────────────────────
def _optout(tags) -> bool:
    for t in tags or ():
        s = str(t or "").replace(" ", "")
        if any(s.startswith(x) for x in _OPTOUT):
            return True
    return False


# ★ 21 ต.ค.69 (เจ้าของ "ตัว tag เปลี่ยนเป็นปุ่มค้นหาก็ได้ … ค้นหากลุ่มลูกค้าตามเงินเดือนหรือตามอาชีพ และอื่นๆ")
#   เงื่อนไข = (ช่อง, ค่า, ไม่เอา?) · ช่องเดียวกันหลายค่า = อย่างใดอย่างหนึ่ง · ต่างช่อง = ต้องตรงทุกช่อง · "ไม่เอา" ตรงอันไหน = ตัดออก
FIELDS = [("occupation", "อาชีพ"), ("band", "ช่วงรายได้"), ("ctype", "ประเภทลูกค้า"), ("brand", "ยี่ห้อที่สนใจ"),
          ("model", "รุ่นที่สนใจ"), ("tag", "แท็ก"), ("cstatus", "สถานะลูกค้า"), ("pay", "ประวัติผ่อน"),
          ("tenure", "อายุงาน"), ("text", "คำค้น")]
FIELD_NAME = dict(FIELDS)
_TAG_FIELDS = ("band", "brand", "model", "tag")      # เทียบเท่ากันทั้งคำ · ช่องข้อความอื่น = มีคำนี้อยู่ในช่อง
_LEAD_FIELD = {"occupation": "occupation", "ctype": "customer_type", "cstatus": "customer_status",
               "pay": "pay_history", "tenure": "job_tenure"}
FACET_TOP = 60


def _nv(v) -> str:
    return re.sub(r"\s+", " ", str(v or "").replace("เเ", "แ")).strip().lower()


def _tag_groups() -> dict:
    """ชื่อแท็ก → ช่อง (ยี่ห้อ/รุ่น/ช่วงรายได้ จากตารางคำ · ชื่อที่เป็นค่าของช่องอื่น = ไม่โชว์ซ้ำในแท็ก)"""
    out = {}
    try:
        from . import kwdb
        for r in kwdb.all_rows():
            g = {"brand": "brand", "model": "model", "income_band": "band",
                 "cust_type": "-", "status": "-", "pay": "-"}.get(r["group"])
            if g and r.get("name"):
                out.setdefault(_nv(r["name"]), g)
    except Exception:
        pass
    return out


def income_range(v):
    """ช่อง "รายได้" (ข้อความอิสระ) → (ต่ำสุด, สูงสุด) บาท/เดือน หรือ None — "22,000" · "2หมื่น" · "20000-25000" · "15k" """
    t = str(v or "").strip()
    if not t:
        return None
    try:
        from .lead_keywords import money_at
        m = money_at(t)
        if m:
            a, _, b = m[0].partition("-")
            lo = int(a)
            return (lo, int(b) if b else lo)
    except Exception:
        pass
    ns = [int(x.replace(",", "")) for x in re.findall(r"\d[\d,]*", t) if x.replace(",", "").isdigit()]
    ns = [n for n in ns if 1000 <= n <= 5_000_000]
    return (min(ns[:2]), max(ns[:2])) if ns else None


def _rows() -> list:
    """ลูกค้าทุกรายใน Connect (ไม่รวมพนักงาน/ลูกค้าจำลอง) — 1 แถว = 1 ลูกค้า"""
    from . import crm
    qs = (ChatOwner.objects.select_related("profile", "fb_profile", "owner", "lead")
          .exclude(profile__user_id__startswith=C.SIM_PREFIX))
    tg = _tag_groups()
    out = []
    for o in qs.iterator(chunk_size=500):
        p = C.cust(o)
        if p is None or getattr(p, "is_employee", False):
            continue
        try:
            ld = o.lead
        except ChatLead.DoesNotExist:
            ld = None
        fb = C.is_fb(o)
        tags = [str(t).strip() for t in ((ld.tags if ld else None) or []) if str(t or "").strip()]
        fv = {k: [] for k, _ in FIELDS}
        for t in tags:
            g = tg.get(_nv(t), "tag")
            if g != "-":
                fv[g].append(t)
        for k, col in _LEAD_FIELD.items():
            v = str(getattr(ld, col, "") or "").strip() if ld else ""
            if v:
                fv[k].append(v)
        out.append({
            "id": o.id, "src": "fb" if fb else "line", "o": o, "p": p, "ld": ld,
            "name": (ld.customer_name if ld and ld.customer_name else p.show_name) or "",
            "lineName": p.display_name or "",
            "phone": (ld.phone if ld else "") or "",
            "lineId": (ld.line_id if ld else "") or "",
            "tags": tags,
            "car": ((ld.car_model or ld.car_text) if ld else "") or "",
            "stage": crm.stage_of(o, ld),
            "deal": C.deal_of(ld),
            "owner": o.owner.nickname if o.owner_id else "",
            "last": o.last_in_at or o.last_at,
            "uid": (p.user_id or "") if not fb else "",
            "f": fv,
            "occupation": (ld.occupation if ld else "") or "", "income": (ld.income if ld else "") or "",
            "inc": income_range(ld.income) if ld else None,
        })
    return out


def clean_filters(f) -> dict:
    f = f if isinstance(f, dict) else {}

    def tags(k):
        v = f.get(k) or []
        if isinstance(v, str):
            v = [v]
        out = []
        for t in v[:20]:
            t = str(t or "").strip()[:40]
            if t and t not in out:
                out.append(t)
        return out

    from .crm import STAGE_NAME
    try:
        days = max(0, min(365, int(f.get("days") or 0)))
    except (TypeError, ValueError):
        days = 0

    def money(k):
        try:
            n = int(float(str(f.get(k) or "").replace(",", "").strip() or 0))
        except (TypeError, ValueError):
            return 0
        return n if 0 < n <= 10_000_000 else 0

    conds = []
    for c in (f.get("conds") or [])[:30]:
        if not isinstance(c, dict):
            continue
        k, v = str(c.get("f") or ""), str(c.get("v") or "").strip()[:60]
        if k in FIELD_NAME and v and not any(x["f"] == k and x["v"] == v for x in conds):
            conds.append({"f": k, "v": v, "neg": bool(c.get("neg"))})
    return {
        "any": tags("any"), "all": tags("all"), "not": tags("not"),
        "src": f.get("src") if f.get("src") in ("line", "fb") else "",
        "days": days,
        "stages": [s for s in (f.get("stages") or []) if s in STAGE_NAME][:10],
        "closed": f.get("closed") is not False,          # ค่าตั้งต้น = ไม่รวมลูกค้าที่ปิดการขาย/ไม่สนใจแล้ว
        "deal": f.get("deal") if f.get("deal") in ("sell", "buy") else "",
        "owner": str(f.get("owner") or "").strip()[:80],
        "q": str(f.get("q") or "").strip()[:60],
        "contact": bool(f.get("contact")),
        "conds": conds, "imin": money("imin"), "imax": money("imax"),
    }


def describe(f) -> str:
    """เงื่อนไข → ข้อความสั้นๆ (บันทึกในประวัติ)"""
    from .crm import STAGE_NAME
    p = []
    if f["any"]:
        p.append("แท็ก " + " / ".join(f["any"]))
    if f["all"]:
        p.append("ต้องมีแท็ก %s" % " + ".join(f["all"]))
    if f["not"]:
        p.append("ไม่เอาแท็ก %s" % ", ".join(f["not"]))
    if f["src"]:
        p.append("LINE" if f["src"] == "line" else "Facebook")
    if f["days"]:
        p.append("คุยภายใน %d วัน" % f["days"])
    if f["stages"]:
        p.append("ขั้น " + ", ".join(STAGE_NAME.get(s, s) for s in f["stages"]))
    if f["deal"]:
        p.append("ลีดรับซื้อ" if f["deal"] == "buy" else "ลีดขาย")
    if f["owner"]:
        p.append("ยังไม่มีผู้ดูแล" if f["owner"] == "__none__" else "ผู้ดูแล " + f["owner"])
    for c in f["conds"]:
        p.append("%s%s %s" % ("ไม่เอา " if c["neg"] else "", FIELD_NAME.get(c["f"], c["f"]), c["v"]))
    if f["imin"] or f["imax"]:
        p.append("รายได้ %s–%s" % (format(f["imin"], ",") if f["imin"] else "", format(f["imax"], ",") if f["imax"] else ""))
    if f["contact"]:
        p.append("มีเบอร์/ไลน์")
    if f["q"]:
        p.append('ค้น "%s"' % f["q"])
    if f["closed"]:
        p.append("ไม่รวมปิดการขาย/ไม่สนใจ")
    return (" · ".join(p) or "ลูกค้าทุกราย")[:300]


def _match(r, f, now) -> str:
    """"" = เข้ากลุ่ม · ไม่งั้น = เหตุผลที่ไม่เข้า (ใช้นับ)"""
    from .crm import CLOSED
    tg = set(r["tags"])
    if f["src"] and r["src"] != f["src"]:
        return "src"
    if f["any"] and not (tg & set(f["any"])):
        return "tag"
    if f["all"] and not set(f["all"]) <= tg:
        return "tag"
    if f["not"] and (tg & set(f["not"])):
        return "tag"
    if f["days"] and (not r["last"] or r["last"] < now - timedelta(days=f["days"])):
        return "days"
    if f["stages"] and r["stage"] not in f["stages"]:
        return "stage"
    if f["deal"] and r["deal"] != f["deal"]:
        return "deal"
    if f["owner"]:
        if f["owner"] == "__none__":
            if r["owner"]:
                return "owner"
        elif r["owner"] != f["owner"]:
            return "owner"
    if f["contact"] and not (r["phone"] or r["lineId"]):
        return "contact"
    if f["conds"]:
        need = {}
        for c in f["conds"]:
            hit = _cond_hit(r, c)
            if c["neg"]:
                if hit:
                    return "cond"
            else:
                need[c["f"]] = need.get(c["f"], False) or hit
        if need and not all(need.values()):
            return "cond"
    if f["q"]:
        q = f["q"].lower()
        hay = " ".join([r["name"], r["lineName"], r["phone"], r["lineId"], r["car"], " ".join(r["tags"])]).lower()
        if q not in hay and q.replace("-", "") not in r["phone"].replace("-", ""):
            return "q"
    # เหตุผลที่หน้าเว็บนับแยกให้ (ไม่รู้รายได้ · ปิดการขาย · ไม่รับข่าวสาร) — นับเฉพาะคนที่หลุดเพราะเรื่องนั้นเรื่องเดียว
    soft = []
    if f["imin"] or f["imax"]:
        inc = r.get("inc")
        if not inc:
            soft.append("noinc")
        elif (f["imin"] and inc[1] < f["imin"]) or (f["imax"] and inc[0] > f["imax"]):
            return "income"
    if f["closed"] and r["stage"] in CLOSED:
        soft.append("closed")
    if _optout(r["tags"]):
        soft.append("optout")
    return "" if not soft else soft[0] if len(soft) == 1 else "multi"


_EPOCH = timezone.make_aware(datetime(2000, 1, 1))


def _cond_hit(r, c) -> bool:
    v = _nv(c["v"])
    if c["f"] == "text":
        hay = " ".join([r["name"], r["lineName"], r["phone"], r["lineId"], r["car"], " ".join(r["tags"]),
                        " ".join(" ".join(x) for x in r["f"].values())])
        return v in _nv(hay) or (v.replace("-", "") and v.replace("-", "") in r["phone"].replace("-", ""))
    vals = r["f"].get(c["f"]) or []
    if c["f"] in _TAG_FIELDS:
        return any(_nv(x) == v for x in vals)
    return any(v in _nv(x) for x in vals)


def facets(rows) -> list:
    """ค่าที่มีจริงในแต่ละช่อง + จำนวนลูกค้า (ให้ช่องค้นหาเงื่อนไขเสนอ) — ไม่รวมคำค้น"""
    out = []
    for k, label in FIELDS:
        if k == "text":
            continue
        cnt, show = {}, {}
        for r in rows:
            seen = set()
            for x in r["f"].get(k) or []:
                key = _nv(x)
                if key and key not in seen:
                    seen.add(key)
                    cnt[key] = cnt.get(key, 0) + 1
                    show.setdefault(key, x.strip()[:60])
        items = sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))[:FACET_TOP]
        if items:
            out.append({"f": k, "label": label, "items": [{"v": show[key], "n": n} for key, n in items]})
    return out


def audience(f, rows=None) -> dict:
    """{rows: ที่เข้ากลุ่ม · optout · closed} — ไม่เข้าเพราะไม่รับข่าวสาร/ปิดการขาย นับแยกให้หน้าเว็บบอก"""
    rows = _rows() if rows is None else rows
    now = timezone.now()
    hit, optout, closed, noinc = [], 0, 0, 0
    for r in rows:
        why = _match(r, f, now)
        if not why:
            hit.append(r)
        elif why == "optout":
            optout += 1
        elif why == "closed":
            closed += 1
        elif why == "noinc":
            noinc += 1
    hit.sort(key=lambda r: r["last"] or _EPOCH, reverse=True)
    return {"rows": hit, "optout": optout, "closed": closed, "noinc": noinc}


def _channels(rows) -> dict:
    """ลูกค้า LINE แต่ละคนคุยอยู่กับบัญชีไหน (กติกาเดียวกับ chat._channel_for) — ถามฐานข้อมูล 2 ครั้งทั้งกลุ่ม"""
    uids = [r["uid"] for r in rows if r["src"] == "line" and r["uid"]]
    out = {}
    if not uids:
        return out
    last = {}
    for i in range(0, len(uids), 900):
        part = uids[i:i + 900]
        ids = (GroupChat.objects.filter(sender_id__in=part, direction=GroupChat.IN).exclude(channel="")
               .values("sender_id").annotate(m=Max("id")).values_list("m", flat=True))
        for sid, ch in GroupChat.objects.filter(pk__in=list(ids)).values_list("sender_id", "channel"):
            last[sid] = ch
    for r in rows:
        if r["src"] == "line" and r["uid"]:
            out[r["uid"]] = (last.get(r["uid"]) or getattr(r["p"], "channel", "") or "crm").strip().lower()
    return out


def _acc_name(key) -> str:
    try:
        from dashboard.services import line_channels as LC
        a = LC.account_of(key)
        if a:
            return a.get("name") or key
    except Exception:
        pass
    return {"crm": "บัญชีลูกค้า (ตัวรับ)", "push": "บัญชีตัวส่ง"}.get(key, key)


def _iso(dt):
    return timezone.localtime(dt).isoformat(timespec="seconds") if dt else ""


def _row_json(r) -> dict:
    from .crm import STAGE_NAME
    return {"id": r["id"], "src": r["src"], "name": r["name"], "phone": r["phone"], "lineId": r["lineId"],
            "tags": r["tags"][:8], "car": r["car"][:60], "stage": r["stage"],
            "stageLabel": STAGE_NAME.get(r["stage"], r["stage"]), "deal": r["deal"], "owner": r["owner"],
            "last": _iso(r["last"]), "occupation": r["occupation"][:40], "income": r["income"][:30]}


def preview(f, with_quota=False) -> dict:
    from .chat import reply_on
    f = clean_filters(f)
    rows = _rows()
    a = audience(f, rows)
    hit = a["rows"]
    line = [r for r in hit if r["src"] == "line" and r["uid"]]
    ch = _channels(line)
    acc = {}
    for uid, k in ch.items():
        acc[k] = acc.get(k, 0) + 1
    tags = {}
    for r in rows:
        for t in r["tags"]:
            tags[t] = tags.get(t, 0) + 1
    owners = sorted({r["owner"] for r in rows if r["owner"]})
    out = {
        "ok": True, "filters": f, "summary": describe(f),
        "total": len(hit), "line": len(line), "fb": sum(1 for r in hit if r["src"] == "fb"),
        "optout": a["optout"], "closed": a["closed"], "noinc": a["noinc"], "all": len(rows),
        "facets": facets(rows), "fieldNames": FIELD_NAME,
        "rows": [_row_json(r) for r in hit[:SHOW_ROWS]],
        "tags": [{"t": t, "n": n} for t, n in sorted(tags.items(), key=lambda x: (-x[1], x[0]))[:120]],
        "owners": owners,
        "accounts": [{"key": k, "name": _acc_name(k), "n": n} for k, n in sorted(acc.items(), key=lambda x: -x[1])],
        "replyOn": reply_on(),
        "https": _base().startswith("https://"),
        "optoutTag": OPTOUT_TAG,
        "limits": {"text": MAX_TEXT, "images": MAX_IMAGES, "cars": MAX_CARS, "max": MAX_RECIPIENTS},
    }
    if with_quota:
        out["quota"] = {k: quota(k) for k in acc}
    return out


# ─────────────────────────── ดาวน์โหลดรายชื่อ ───────────────────────────
def export_csv(f) -> tuple:
    """(ชื่อไฟล์, ไบต์ CSV ใส่ BOM) — ลูกค้าทุกรายที่เข้ากลุ่ม (รวม Facebook)"""
    from .crm import STAGE_NAME
    f = clean_filters(f)
    hit = audience(f)["rows"]
    ch = _channels(hit)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["เลขแชท (Connect)", "ชื่อ", "ชื่อใน LINE/Facebook", "ช่องทาง", "บัญชี LINE OA", "เบอร์โทร", "ID LINE (ที่ลูกค้าให้)",
                "LINE userId", "แท็ก", "รถที่สนใจ", "อาชีพ", "รายได้", "อายุงาน", "ประวัติผ่อน", "ประเภทลูกค้า", "สถานะลูกค้า",
                "ขั้นของลีด", "ลีด", "ผู้ดูแล", "คุยล่าสุด"])
    for r in hit:
        last = timezone.localtime(r["last"]).strftime("%d/%m/%Y %H:%M") if r["last"] else ""
        w.writerow([r["id"], r["name"], r["lineName"], "LINE" if r["src"] == "line" else "Facebook",
                    _acc_name(ch.get(r["uid"], "")) if r["src"] == "line" else "",
                    ("'" + r["phone"]) if r["phone"] else "", r["lineId"], r["uid"],
                    ", ".join(r["tags"]), r["car"], r["occupation"], r["income"], ", ".join(r["f"]["tenure"]),
                    ", ".join(r["f"]["pay"]), ", ".join(r["f"]["ctype"]), ", ".join(r["f"]["cstatus"]),
                    STAGE_NAME.get(r["stage"], r["stage"]),
                    "รับซื้อ" if r["deal"] == "buy" else "ขาย", r["owner"], last])
    name = "รายชื่อลูกค้า_%s.csv" % timezone.localtime().strftime("%Y%m%d_%H%M")
    return name, ("﻿" + buf.getvalue()).encode("utf-8"), len(hit)


def export_ids(f, account="") -> tuple:
    """(ชื่อไฟล์, ไบต์) — LINE userId บรรทัดละคน ของบัญชีที่เลือก · สำหรับ "อัปโหลด userId" สร้างกลุ่มเป้าหมายใน LINE OA Manager
    (userId ใช้ได้กับบัญชีของ provider ที่ได้ยินลูกค้าคนนั้นเท่านั้น — จึงต้องแยกไฟล์ตามบัญชี)"""
    f = clean_filters(f)
    hit = [r for r in audience(f)["rows"] if r["src"] == "line" and r["uid"]]
    ch = _channels(hit)
    account = (account or "").strip().lower()
    ids = [r["uid"] for r in hit if not account or ch.get(r["uid"]) == account]
    name = "line_userid_%s_%s.txt" % (account or "all", timezone.localtime().strftime("%Y%m%d_%H%M"))
    return name, ("\n".join(ids) + ("\n" if ids else "")).encode("utf-8"), len(ids)


# ─────────────────────────── เนื้อหา ───────────────────────────
def _base() -> str:
    return (getattr(settings, "SITE_URL", "") or "").rstrip("/")


def _media_url(rel: str) -> str:
    return "%s/%s/%s" % (_base(), settings.MEDIA_URL.strip("/"), rel)


def _abs(rel: str) -> str:
    return os.path.join(str(settings.MEDIA_ROOT), rel)


def upload(f) -> dict:
    """รูปที่แอดมินอัปเอง → สำเนาสาธารณะใน media/chat_out (ย่อ · หมุนตาม EXIF · ตัด EXIF/พิกัด) · ลบเองเกิน 60 วัน"""
    from . import chatplus as CP
    if not f:
        raise BError("ยังไม่ได้เลือกรูป")
    if f.size > CP.MAX_IN_MB * 1024 * 1024:
        raise BError("รูปใหญ่เกินไป (ไม่เกิน %d MB)" % CP.MAX_IN_MB)
    try:
        full, prev = CP._encode(f.read())
    except CP.ImageError as e:
        raise BError(str(e))
    rf, rp = CP._save_out(full, prev)
    return {"full": rf, "prev": rp, "url": "/%s/%s" % (settings.MEDIA_URL.strip("/"), rp)}


def _clean_links(raw) -> list:
    """ลิงก์ที่แอดมินใส่ → [{url, label, mode(button|text), tag}] · ช่องว่างทั้งแถว = ข้าม · ผิด = บอกว่าลิงก์ที่เท่าไหร่"""
    out = []
    for n, it in enumerate((raw if isinstance(raw, list) else [])[:MAX_LINKS + 3], 1):
        if not isinstance(it, dict):
            continue
        url = str(it.get("url") or "").strip()
        label = re.sub(r"\s+", " ", str(it.get("label") or "")).strip()
        if not url and not label:
            continue
        if not url:
            raise BError("ลิงก์ที่ %d ยังไม่มีที่อยู่ลิงก์ (URL)" % n)
        if len(url) > MAX_URL or not _URL.match(url):
            raise BError("ลิงก์ที่ %d ไม่ถูกต้อง — ต้องขึ้นต้นด้วย https:// (หรือ http://) และไม่มีช่องว่าง" % n)
        if not label:
            raise BError("ลิงก์ที่ %d ยังไม่มีชื่อปุ่ม / ข้อความที่ลูกค้าเห็น" % n)
        if len(label) > LINK_LABEL:
            raise BError("ชื่อปุ่มลิงก์ที่ %d ยาวเกินไป (%d ตัว · LINE ให้ไม่เกิน %d ตัว)" % (n, len(label), LINK_LABEL))
        tag = ""
        if it.get("tagOn", True) is not False:
            tag = re.sub(r"\s+", " ", str(it.get("tag") or "")).strip()[:LINK_TAG] or ("กดลิงก์ " + label)[:LINK_TAG]
        out.append({"url": url, "label": label, "mode": "text" if it.get("mode") == "text" else "button", "tag": tag})
    if len(out) > MAX_LINKS:
        raise BError("ใส่ลิงก์ได้ไม่เกิน %d ลิงก์" % MAX_LINKS)
    return out


def clean_content(body) -> dict:
    b = body if isinstance(body, dict) else {}
    text = str(b.get("text") or "").replace("\r\n", "\n").strip()
    if len(text) > MAX_TEXT:
        raise BError("ข้อความยาวเกินไป (%d ตัว · ไม่เกิน %d)" % (len(text), MAX_TEXT))
    imgs = []
    for it in (b.get("images") or [])[:MAX_IMAGES + 1]:
        full = str((it or {}).get("full") or "") if isinstance(it, dict) else str(it or "")
        if not _REL.match(full):
            raise BError("รูปที่แนบไม่ถูกต้อง — อัปรูปใหม่อีกครั้ง")
        prev = full[:-4] + "_p.jpg"
        if not os.path.exists(_abs(full)) or not os.path.exists(_abs(prev)):
            raise BError("หารูปที่แนบไม่เจอ (อาจถูกลบไปแล้ว) — อัปรูปใหม่อีกครั้ง")
        if full not in [x["full"] for x in imgs]:
            imgs.append({"full": full, "prev": prev})
    if len(imgs) > MAX_IMAGES:
        raise BError("แนบรูปได้ไม่เกิน %d รูป" % MAX_IMAGES)
    cars = []
    for c in (b.get("cars") or [])[:MAX_CARS + 1]:
        c = str(c or "").strip()[:30]
        if c and c not in cars:
            cars.append(c)
    if len(cars) > MAX_CARS:
        raise BError("เลือกรถได้ไม่เกิน %d คัน" % MAX_CARS)
    links = _clean_links(b.get("links"))
    title = re.sub(r"\s+", " ", str(b.get("link_title") or "")).strip()[:MAX_TITLE]
    if not (text or imgs or cars or links):
        raise BError("ยังไม่มีเนื้อหา — พิมพ์ข้อความ แนบรูป เลือกรถ หรือใส่ลิงก์อย่างน้อย 1 อย่าง")
    return {"text": text, "images": imgs, "cars": cars, "links": links, "link_title": title,
            "car_tag": b.get("car_tag", True) is not False}


def content_hash(c) -> str:
    raw = json.dumps({"t": c["text"], "i": [x["full"] for x in c["images"]], "c": c["cars"],
                      "l": [[x["url"], x["label"], x["mode"], x["tag"]] for x in c.get("links") or []],
                      "lt": c.get("link_title", ""), "ct": bool(c.get("car_tag", True))},
                     ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


_CARIMG = {}


def _car_image(car) -> str:
    """รูปปกรถ → สำเนา JPEG ในโดเมนเรา (LINE ต้องดึงรูปจาก https ที่ตอบเร็ว · รูป Drive/Car Spend ใช้ตรงไม่แน่นอน)
    คืน path ใต้ MEDIA_ROOT ("" = ไม่มีรูป/โหลดไม่ได้) · จำไว้ต่อ process"""
    from cars import showroom_sync as SS
    from . import chatplus as CP
    urls = SS._photo_urls(car)
    if not urls:
        return ""
    first = urls[0]
    key = "%s|%s" % (car.code, first.get("key") or first.get("url"))
    hit = _CARIMG.get(key)
    if hit and os.path.exists(_abs(hit)):
        return hit
    raw = None
    k = str(first.get("key") or "")
    if "/" in k and not k.startswith("carspend:"):
        p = _abs(k)
        if os.path.exists(p):
            with open(p, "rb") as fh:
                raw = fh.read()
    if raw is None:
        try:
            r = requests.get(first["url"], timeout=15, stream=True,
                             headers={"User-Agent": "Mozilla/5.0 (OxletAuto broadcast)"})
            if r.status_code != 200 or not (r.headers.get("Content-Type") or "").startswith("image"):
                return ""
            buf = io.BytesIO()
            for chunk in r.iter_content(65536):
                buf.write(chunk)
                if buf.tell() > 12 * 1024 * 1024:
                    return ""
            raw = buf.getvalue()
        except Exception:
            return ""
    try:
        full, prev = CP._encode(raw)
    except Exception:
        return ""
    rf, _rp = CP._save_out(full, prev)
    _CARIMG[key] = rf
    return rf


def _car_link(car) -> str:
    """ลิงก์หน้ารถบนเว็บโชว์รูม — เฉพาะรถที่ลูกค้าเห็นบนเว็บอยู่จริง (ไม่งั้นลิงก์เปิดแล้วไม่เจอ)"""
    try:
        from cars import showroom_sync as SS
        if getattr(car, "web_listed", False):
            return SS.web_url(car) or ""
    except Exception:
        pass
    return ""


def _car_info(car) -> dict:
    from cars import showroom_sync as SS
    title = ("%s %s" % (car.brand or "", car.model or "")).strip() or car.code
    sub = []
    if car.year:
        sub.append("ปี %s" % car.year)
    if car.color:
        sub.append("สี%s" % car.color)
    if car.km:
        sub.append("%s กม." % format(car.km, ","))
    price = SS.sale_price(car)
    return {"code": car.code, "title": title[:60], "sub": " · ".join(sub), "price": price,
            "priceText": ("฿" + format(price, ",")) if price else "", "link": _car_link(car)}


def cars_of(codes) -> list:
    from cars.models import Car
    by = {c.code: c for c in Car.objects.filter(code__in=list(codes or [])).exclude(status="sold")}
    return [by[c] for c in codes if c in by]


def _bubble(info, img_url, link=None) -> dict:
    """การ์ดรถ 1 ใบ · `link` = ลิงก์ที่ใส่ในปุ่ม (ตัวแทนลิงก์ติดตาม) — ไม่ส่ง = ลิงก์หน้ารถตรงๆ"""
    link = info["link"] if link is None else link
    body = [{"type": "text", "text": info["title"], "weight": "bold", "size": "md", "wrap": True}]
    if info["sub"]:
        body.append({"type": "text", "text": info["sub"], "size": "sm", "color": "#6b6280", "wrap": True})
    if info["priceText"]:
        body.append({"type": "text", "text": info["priceText"], "size": "lg", "weight": "bold", "color": "#7c3aed"})
    b = {"type": "bubble", "size": "kilo",
         "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": body}}
    if img_url:
        b["hero"] = {"type": "image", "url": img_url, "size": "full", "aspectRatio": "4:3", "aspectMode": "cover"}
        if link:
            b["hero"]["action"] = {"type": "uri", "uri": link}
    if link:
        b["footer"] = {"type": "box", "layout": "vertical", "contents": [
            {"type": "button", "style": "primary", "color": "#7c3aed", "height": "sm",
             "action": {"type": "uri", "label": "ดูรายละเอียดรถ", "uri": link}}]}
    return b


def _link_card(title, btn) -> dict:
    """การ์ดปุ่มลิงก์ (ซ่อนลิงก์ไว้หลังปุ่ม) · `btn` = [(ลำดับลิงก์, ลิงก์)]"""
    buttons = []
    for k, (i, L) in enumerate(btn):
        bt = {"type": "button", "height": "sm", "style": "primary" if k == 0 else "secondary",
              "action": {"type": "uri", "label": L["label"], "uri": PH % i}}
        if k == 0:
            bt["color"] = "#7c3aed"
        buttons.append(bt)
    title = title or DEFAULT_TITLE
    return {"type": "flex", "altText": title[:390], "contents": {
        "type": "bubble", "size": "kilo",
        "body": {"type": "box", "layout": "vertical", "contents": [
            {"type": "text", "text": title, "weight": "bold", "size": "md", "wrap": True}]},
        "footer": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": buttons}}}


def build(c) -> tuple:
    """เนื้อหา → (ข้อความ LINE ≤5 ชิ้น, ข้อมูลรถ, คำอธิบายแต่ละชิ้นที่จะเก็บลงแชท, ลิงก์ติดตาม)

    ลิงก์ทุกอันในข้อความเป็นตัวแทน `__OXBCLnn__` (nn = ลำดับในลิงก์ติดตาม) → ตอนส่งแทนด้วยลิงก์ของลูกค้าคนนั้น (`_fill`)
    ลิงก์ติดตาม = ลิงก์ที่แอดมินใส่ (ตามลำดับ) แล้วต่อด้วยปุ่ม "ดูรายละเอียดรถ" ของรถที่ขึ้นเว็บแล้ว"""
    links = [dict(x) for x in (c.get("links") or [])]
    if (c["images"] or c["cars"] or links) and not _base().startswith("https://"):
        raise BError("ส่งรูป/การ์ดรถ/ลิงก์ติดตามได้เฉพาะบนเซิร์ฟเวอร์จริง — LINE ต้องดึงรูป/เปิดลิงก์จาก https")
    msgs, store = [], []
    text, shown = c["text"], c["text"]
    tl = [(i, L) for i, L in enumerate(links) if L["mode"] == "text"]
    if tl:
        add = "\n".join("%s: %s" % (L["label"], PH % i) for i, L in tl)
        add_s = "\n".join("%s: %s" % (L["label"], L["url"]) for _i, L in tl)
        text = (text + "\n\n" + add) if text else add
        shown = (shown + "\n\n" + add_s) if shown else add_s
    if text:
        msgs.append({"type": "text", "text": text})
        store.append({"type": GroupChat.TEXT, "text": shown})
    for im in c["images"]:
        msgs.append({"type": "image", "originalContentUrl": _media_url(im["full"]),
                     "previewImageUrl": _media_url(im["prev"])})
        store.append({"type": GroupChat.IMAGE, "text": "[รูป]", "file": im["full"], "prev": im["prev"]})
    infos = []
    cars = cars_of(c["cars"])
    if c["cars"] and not cars:
        raise BError("ไม่พบรถที่เลือก (อาจขายไปแล้ว) — เลือกรถใหม่")
    btn = [(i, L) for i, L in enumerate(links) if L["mode"] == "button"]
    if cars:
        bubbles = []
        for car in cars:
            info = _car_info(car)
            rel = _car_image(car)
            info["img"] = ("/%s/%s" % (settings.MEDIA_URL.strip("/"), rel)) if rel else ""
            infos.append(info)
            ph = ""
            if info["link"]:
                ph = PH % len(links)
                links.append({"url": info["link"], "label": "ดูรถ " + info["title"][:30], "mode": "car", "car": car.code,
                              "tag": ("กดดูรถ " + info["title"])[:LINK_TAG] if c.get("car_tag", True) else ""})
            bubbles.append(_bubble(info, _media_url(rel) if rel else "", ph))
        alt = "รถแนะนำ: " + " · ".join(("%s %s" % (i["title"], i["priceText"])).strip() for i in infos)
        contents = bubbles[0] if len(bubbles) == 1 else {"type": "carousel", "contents": bubbles}
        msgs.append({"type": "flex", "altText": alt[:390], "contents": contents})
        store.append({"type": GroupChat.TEXT,
                      "text": "[การ์ดรถ] " + "\n".join(("%s %s %s" % (i["title"], i["sub"], i["priceText"])).strip()
                                                      for i in infos)})
    if btn:
        title = c.get("link_title") or DEFAULT_TITLE
        msgs.append(_link_card(title, btn))
        store.append({"type": GroupChat.TEXT,
                      "text": ("[ปุ่มลิงก์] %s\n" % title) + "\n".join("%s: %s" % (L["label"], L["url"]) for _i, L in btn)})
    if len(msgs) > 5:
        raise BError("LINE ส่งได้ครั้งละไม่เกิน 5 ชิ้น (ข้อความ + รูป + การ์ดรถ + การ์ดปุ่มลิงก์) — ลดรูปลง "
                     "หรือเปลี่ยนลิงก์เป็นแบบแนบในข้อความ")
    return msgs, infos, store, links


def card_preview(codes) -> list:
    """ข้อมูลการ์ดรถสำหรับหน้าเว็บ (ไม่โหลดรูปใหม่ — ใช้ลิงก์รูปเดิมของรถ)"""
    from cars import showroom_sync as SS
    out = []
    for car in cars_of(codes):
        info = _car_info(car)
        urls = SS._photo_urls(car)
        info["img"] = (urls[0]["url"] if urls else "")
        out.append(info)
    return out


def _fill(tpl: str, n: int, url_for) -> list:
    """แทนตัวแทนลิงก์ทุกอันด้วยลิงก์ของผู้รับคนนี้ (`url_for(i)` · เป็น ASCII ล้วน ใส่ใน JSON ได้ตรง)"""
    s = tpl
    for i in range(n):
        s = s.replace(PH % i, url_for(i))
    return json.loads(s)


# ─────────────────────────── ลิงก์ติดตาม (/b/<token>) ───────────────────────────
# ลิงก์จริง:   <SITE_URL>/b/<บรอดแคสต์ base36>-<ลูกค้า base36>-<ลำดับลิงก์>-<ลายเซ็น>
# ลิงก์ทดสอบ: <SITE_URL>/b/t-<hash 12 ตัว>-<พนักงาน base36>-<ลำดับลิงก์>-<ลายเซ็น>  (นับจำนวนช่องแยก — ไม่สับกัน)
# ลายเซ็น = HMAC(SECRET_KEY) 12 ตัว → เดา/ปลอมลิงก์ของลูกค้าคนอื่นไม่ได้ · ปลายทางอ่านจากบรอดแคสต์ในฐานข้อมูล (ไม่ใช่จากลิงก์ = ไม่ใช่ open redirect)
_TOK = re.compile(r"^([0-9a-z]{1,13})-([0-9a-z]{1,13})-(\d{1,2})-([0-9a-f]{%d})$" % SIG_LEN)
_TOK_T = re.compile(r"^t-([0-9a-f]{12})-([0-9a-z]{1,13})-(\d{1,2})-([0-9a-f]{%d})$" % SIG_LEN)
_BOT_UA = re.compile(r"line-poker|facebookexternalhit|facebot|twitterbot|slackbot|discordbot|telegrambot|whatsapp|"
                     r"skypeuripreview|bingpreview|googlebot|bot/|\bbot\b|crawl|spider|preview|curl/|wget|"
                     r"python-requests|python-urllib|headless|go-http-client|scrapy", re.I)


def _b36(n: int) -> str:
    n = int(n)
    s = ""
    while True:
        n, r = divmod(n, 36)
        s = "0123456789abcdefghijklmnopqrstuvwxyz"[r] + s
        if not n:
            return s


def _sig(*parts) -> str:
    raw = "|".join(str(p) for p in parts).encode("utf-8")
    return hmac.new(str(settings.SECRET_KEY).encode("utf-8"), raw, hashlib.sha256).hexdigest()[:SIG_LEN]


def click_url(bid, oid, i) -> str:
    return "%s/b/%s-%s-%d-%s" % (_base(), _b36(bid), _b36(oid), i, _sig("bc", bid, oid, i))


def test_url(h, emp, i) -> str:
    h12 = str(h)[:12]
    return "%s/b/t-%s-%s-%d-%s" % (_base(), h12, _b36(emp), i, _sig("bt", h12, emp, i))


def is_bot(ua) -> bool:
    """ตัวดึงลิงก์ไปทำตัวอย่าง (LINE/Facebook ฯลฯ) — ไม่นับเป็นลูกค้ากด"""
    return not ua or bool(_BOT_UA.search(str(ua)))


def click(tok: str, ua: str = "", method: str = "GET") -> str:
    """ลูกค้ากดลิงก์ → ลิงก์ปลายทาง ("" = ลิงก์ไม่ถูกต้อง) · จดว่าใครกด + ติดแท็ก (ครั้งแรก) · จดพลาด = ยังพาไปปลายทาง"""
    tok = str(tok or "").strip().lower()
    count = method in ("GET", "POST") and not is_bot(ua)
    m = _TOK_T.match(tok)
    if m:
        h12, emp, i = m.group(1), int(m.group(2), 36), int(m.group(3))
        if not hmac.compare_digest(m.group(4), _sig("bt", h12, emp, i)):
            return ""
        ent = next((v for k, v in _tests().items() if k.startswith(h12)), None) or {}
        links = ent.get("links") or []
        if i >= len(links):
            return ""
        if count:
            try:
                _test_click(h12, emp, i)
            except Exception:
                pass
        return str(links[i].get("url") or "")
    m = _TOK.match(tok)
    if not m:
        return ""
    bid, oid, i = int(m.group(1), 36), int(m.group(2), 36), int(m.group(3))
    if not hmac.compare_digest(m.group(4), _sig("bc", bid, oid, i)):
        return ""
    b = Broadcast.objects.filter(pk=bid).first()
    links = (b.links if b else None) or []
    if i >= len(links):
        return ""
    url = str(links[i].get("url") or "")
    if url and count:
        try:
            _record(b, oid, i)
        except Exception as e:
            try:
                from dashboard.services import eventlog
                eventlog.log("bcast_click", name="บรอดแคสต์ #%d — จดคนกดไม่ได้" % bid, ok=False, error=str(e)[:200])
            except Exception:
                pass
    return url


def _record(b, oid, i):
    now = timezone.now()
    o = ChatOwner.objects.filter(pk=oid).first()
    if not o:
        return
    try:
        with transaction.atomic():
            ck = BroadcastClick.objects.create(broadcast=b, chat=o, link=i, first_at=now, last_at=now)
    except IntegrityError:
        BroadcastClick.objects.filter(broadcast=b, chat=o, link=i).update(count=F("count") + 1, last_at=now)
        return
    L = (b.links or [])[i]
    tag = str(L.get("tag") or "").strip()
    note = 'ลูกค้ากด "%s" ในบรอดแคสต์ #%d' % (L.get("label") or "ลิงก์", b.pk)
    if tag and _add_tag(o, tag, b.pk, i, now):
        BroadcastClick.objects.filter(pk=ck.pk).update(tagged=tag[:40])
        note += " · ติดแท็ก " + tag
    ChatOwnerLog.objects.create(chat_id=o.pk, action=ChatOwnerLog.BCAST, by_name="ลูกค้า", at=now, note=note[:200])


def _add_tag(o, tag, bid, i, now) -> bool:
    """ติดแท็กของลิงก์ให้ลูกค้า (ช่องเดียวกับที่คนใส่ในหน้า Connect) · มีอยู่แล้ว / คนเคยเอาออก / เต็ม 12 แท็ก = ไม่ติด
    จดที่ `auto["_btags"]` ว่าติดจากบรอดแคสต์ไหน ลิงก์ไหน · ระบบแท็กอัตโนมัติไม่เอาออก (ไม่ใช่แท็กของมัน)"""
    from .autotag import TAGNO_KEY, TAGS_MAX
    from .connect import lead_of
    lead = lead_of(o)
    with transaction.atomic():
        lead = ChatLead.objects.select_for_update().get(pk=lead.pk)
        tags = list(lead.tags or [])
        auto = dict(lead.auto or {})
        if tag in tags or tag in (auto.get(TAGNO_KEY) or []) or len(tags) >= TAGS_MAX:
            return False
        tags.append(tag)
        bt = dict(auto.get(BTAG_KEY) or {})
        bt[tag] = {"b": bid, "link": i, "at": now.isoformat(timespec="seconds")}
        auto[BTAG_KEY] = bt
        lead.tags, lead.auto = tags, auto
        lead.save(update_fields=["tags", "auto", "updated_at"])
    return True


def _test_click(h12, emp, i):
    from dashboard.services import cache_store
    try:
        d = dict((cache_store.get_kv(KV_TCLICK) or {}).get("data") or {})
    except Exception:
        d = {}
    now = timezone.now().isoformat(timespec="seconds")
    ent = dict(d.get(h12) or {})
    who = dict(ent.get("c") or {})
    rec = dict(who.get(str(emp)) or {})
    rec.setdefault(str(i), now)
    who[str(emp)] = rec
    ent.update({"at": now, "c": who})
    d[h12] = ent
    keep = sorted(d.items(), key=lambda x: (x[1] or {}).get("at", ""), reverse=True)[:30]
    cache_store.set_kv(KV_TCLICK, dict(keep))


def test_state(h) -> dict:
    """ใครในทีมกดลิงก์ในข้อความทดสอบแล้วบ้าง (หน้าเว็บถามเป็นระยะหลังส่งทดสอบ)"""
    from dashboard.services import cache_store
    from .models import Employee
    h12 = str(h or "")[:12]
    if not re.match(r"^[0-9a-f]{12}$", h12):
        return {"ok": True, "clicks": [], "links": []}
    try:
        ent = ((cache_store.get_kv(KV_TCLICK) or {}).get("data") or {}).get(h12) or {}
    except Exception:
        ent = {}
    t = next((v for k, v in _tests().items() if k.startswith(h12)), None) or {}
    links = t.get("links") or []
    ids = [int(k) for k in (ent.get("c") or {}) if str(k).isdigit() and int(k)]
    names = dict(Employee.objects.filter(pk__in=ids).values_list("pk", "nickname"))
    out = []
    for k, rec in (ent.get("c") or {}).items():
        emp = int(k) if str(k).isdigit() else 0
        got = []
        for i, at in sorted((rec or {}).items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else 0):
            ii = int(i) if str(i).isdigit() else 0
            L = links[ii] if ii < len(links) else {}
            got.append({"i": ii, "label": L.get("label") or "ลิงก์", "tag": L.get("tag") or "", "at": at})
        out.append({"name": names.get(emp) or t.get("by") or "คุณ", "links": got})
    return {"ok": True, "clicks": out,
            "links": [{"label": L.get("label") or "", "tag": L.get("tag") or "", "mode": L.get("mode") or ""} for L in links]}


# ─────────────────────────── LINE ───────────────────────────
_QUOTA = {}


def quota(account) -> dict:
    """โควต้าข้อความเดือนนี้ของบัญชี → {limit (None = ไม่จำกัด), used, left, error} · จำ 2 นาที"""
    from dashboard.services import line_channels as LC
    key = (account or "").strip().lower()
    hit = _QUOTA.get(key)
    if hit and time.time() - hit[0] < 120:
        return hit[1]
    tok = LC.token_of(key)
    res = {"limit": None, "used": None, "left": None, "error": ""}
    if not tok:
        res["error"] = "ยังไม่ได้ตั้ง token ของบัญชีนี้"
        return res
    try:
        h = {"Authorization": "Bearer " + tok}
        q = requests.get(QUOTA_URL, headers=h, timeout=8)
        u = requests.get(USAGE_URL, headers=h, timeout=8)
        if q.status_code != 200 or u.status_code != 200:
            res["error"] = "ถามโควต้าไม่ได้ (%s/%s)" % (q.status_code, u.status_code)
        else:
            qj, uj = q.json(), u.json()
            res["used"] = int(uj.get("totalUsage") or 0)
            if qj.get("type") == "limited":
                res["limit"] = int(qj.get("value") or 0)
                res["left"] = max(0, res["limit"] - res["used"])
    except Exception as e:
        res["error"] = "ถามโควต้าไม่ได้: %s" % str(e)[:80]
    _QUOTA[key] = (time.time(), res)
    return res


def _who(user) -> str:
    return ((user or {}).get("nickname") or (user or {}).get("display_name") or "แอดมิน").strip()[:80]


def _pick(cands, account) -> tuple:
    """[(userId, บัญชี)] → (uid, บัญชี) ที่ส่งได้ · บัญชีเดียวกับลูกค้าก่อน ไม่มีค่อยบัญชีไหนก็ได้ที่มี token"""
    from dashboard.services import line_channels as LC
    seen, norm = set(), []
    for u, ch in cands:
        if u and u not in seen and str(u).startswith("U"):
            seen.add(u)
            norm.append((u, (ch or "crm").strip().lower()))
    want = (account or "crm").strip().lower()
    for u, ch in norm:
        if ch == want and LC.account_of(ch):
            return u, ch
    for u, ch in norm:
        if LC.account_of(ch):
            return u, ch
    return "", ""


def _test_target(user, account) -> tuple:
    """LINE userId ของแอดมินคนนี้ฝั่งบัญชีที่จะส่ง → (uid, บัญชี) · ไม่มีฝั่งนั้น = ฝั่งไหนก็ได้ที่มี token (หน้าตาเหมือนกัน)"""
    from .models import LineProfile
    cands = []
    emp = C.employee_of(user)
    if emp:
        cands += list(LineProfile.objects.filter(employee=emp).values_list("user_id", "channel"))
    uid = ((user or {}).get("user_id") or "").strip()
    if uid.startswith("U"):
        cands += list(LineProfile.objects.filter(user_id=uid).values_list("user_id", "channel")) or [(uid, "")]
    return _pick(cands, account)


def _tests() -> dict:
    from dashboard.services import cache_store
    try:
        return (cache_store.get_kv(KV_TEST) or {}).get("data") or {}
    except Exception:
        return {}


def testers(user) -> dict:
    """คนในทีมที่ส่งทดสอบหาได้ (พนักงานที่ทักบัญชี LINE OA ของร้านไว้แล้ว) — ชื่อเล่นเท่านั้น ไม่ส่ง LINE userId ออก
    + รายชื่อที่เลือกไว้ครั้งก่อน (`bcast_testers`)"""
    from dashboard.services import cache_store
    from dashboard.services import line_channels as LC
    from .models import Employee, LineProfile
    me = C.employee_of(user)
    by = {}
    for eid, uid, ch in (LineProfile.objects.filter(employee__isnull=False, employee__active=True)
                         .values_list("employee_id", "user_id", "channel")):
        k = (ch or "crm").strip().lower()
        if uid and str(uid).startswith("U") and LC.account_of(k):
            by.setdefault(eid, set()).add(k)
    emps = {e.pk: e for e in Employee.objects.filter(pk__in=list(by))}
    out = []
    for eid, chs in by.items():
        e = emps.get(eid)
        if e:
            out.append({"id": eid, "name": e.nickname, "self": bool(me and me.pk == eid),
                        "accounts": sorted(_acc_name(c) for c in chs)})
    if not any(x["self"] for x in out):
        uid, ch = _test_target(user, "")
        if uid:
            out.append({"id": me.pk if me else 0, "name": _who(user), "self": True, "accounts": [_acc_name(ch)]})
    out.sort(key=lambda x: (not x["self"], x["name"]))
    try:
        saved = list((cache_store.get_kv(KV_TESTERS) or {}).get("data") or [])
    except Exception:
        saved = []
    have = {x["id"] for x in out}
    return {"ok": True, "testers": out, "saved": [i for i in saved if i in have], "max": MAX_TESTERS}


def _tester_ids(raw, me) -> list:
    out = []
    for v in (raw if isinstance(raw, list) else [])[:MAX_TESTERS + 5]:
        try:
            v = int(v)
        except (TypeError, ValueError):
            continue
        if v >= 0 and v not in out:
            out.append(v)
    if not out:
        out = [me.pk if me else 0]
    if len(out) > MAX_TESTERS:
        raise BError("ส่งทดสอบได้ครั้งละไม่เกิน %d คน" % MAX_TESTERS)
    return out


def test_send(body, user) -> dict:
    """ส่งเนื้อหาเดียวกับที่จะบรอดแคสต์ หาคนในทีมก่อน (ด่านบังคับก่อนส่งจริง) — แบบ "Test recipients" ของ MAAC
    ลิงก์ในข้อความทดสอบเป็นลิงก์ทดสอบ: กดแล้วพาไปปลายทางจริง + บอกหน้าเว็บว่าใครกดแล้ว · ไม่ติดแท็กใคร"""
    from dashboard.services import cache_store
    from dashboard.services import line_channels as LC
    from dashboard.services.line_notify import push_line_message
    from .chat import _explain
    from .models import Employee, LineProfile
    c = clean_content(body.get("content"))
    msgs, infos, _store_, links = build(c)
    acc = str(body.get("account") or "").strip().lower()
    me = C.employee_of(user)
    ids = _tester_ids(body.get("testers"), me)
    h = content_hash(c)
    tpl = json.dumps(msgs, ensure_ascii=False)
    results, ok_names = [], []
    for tid in ids:
        if tid == 0 or (me and tid == me.pk):
            uid, ch = _test_target(user, acc)
            name = me.nickname if me else _who(user)
        else:
            e = Employee.objects.filter(pk=tid, active=True).first()
            if not e:
                results.append({"id": tid, "name": "พนักงาน #%d" % tid, "ok": False, "error": "ไม่พบในทะเบียนพนักงาน"})
                continue
            name = e.nickname
            uid, ch = _pick(LineProfile.objects.filter(employee=e).values_list("user_id", "channel"), acc)
        if not uid:
            results.append({"id": tid, "name": name, "ok": False,
                            "error": "ยังไม่มี LINE ของคนนี้ — ให้แอดบัญชี LINE OA ของร้านเป็นเพื่อนแล้วทักมา 1 ข้อความ"})
            continue
        m = _fill(tpl, len(links), lambda i, _t=tid: test_url(h, _t, i))
        code, res = push_line_message(uid, m, LC.token_of(ch), what="บรอดแคสต์ (ส่งทดสอบ)")
        if code == 200:
            results.append({"id": tid, "name": name, "ok": True, "account": _acc_name(ch)})
            ok_names.append(name)
        else:
            results.append({"id": tid, "name": name, "ok": False, "error": _explain(code, res)})
    if not ok_names:
        bad = results[0] if results else {}
        raise BError("ส่งทดสอบไม่สำเร็จ: %s%s" % (bad.get("name", ""), (" — " + bad["error"]) if bad.get("error") else ""))
    t = _tests()
    t[h] = {"at": timezone.now().isoformat(), "by": _who(user), "to": ok_names,
            "links": [{"url": L["url"], "label": L["label"], "tag": L.get("tag", ""), "mode": L["mode"]} for L in links]}
    keep = sorted(t.items(), key=lambda x: x[1].get("at", ""), reverse=True)[:30]
    try:
        cache_store.set_kv(KV_TEST, dict(keep))
        cache_store.set_kv(KV_TESTERS, ids)
    except Exception:
        pass
    msg = "ส่งทดสอบถึง %s แล้ว — เปิดดูใน LINE" % " · ".join(ok_names)
    if links:
        msg += " · กดลิงก์ทดสอบได้ (พาไปหน้าจริง ไม่ติดแท็กใคร)"
    fail = [r for r in results if not r["ok"]]
    if fail:
        msg += " · ส่งไม่ถึง: " + " · ".join(r["name"] for r in fail)
    return {"ok": True, "hash": h, "results": results, "cars": infos, "links": len(links), "message": msg}


def tested(c) -> dict:
    t = _tests().get(content_hash(c)) or {}
    try:
        at = datetime.fromisoformat(t.get("at", ""))
    except Exception:
        return {}
    if timezone.is_naive(at):
        at = timezone.make_aware(at)
    return t if timezone.now() - at <= timedelta(hours=TEST_VALID_H) else {}


def _multicast(token, uids, msgs, retry_key) -> tuple:
    """ยิง 1 ชุด → (สำเร็จไหม, สถานะ, คำตอบ) · 409 = LINE รับชุดนี้ไปแล้ว (retry key เดิม) นับว่าสำเร็จ"""
    last = (0, "")
    for attempt in range(2):
        try:
            r = requests.post(MULTICAST_URL, timeout=30, json={"to": uids, "messages": msgs},
                              headers={"Authorization": "Bearer " + token, "Content-Type": "application/json",
                                       "X-Line-Retry-Key": retry_key})
            last = (r.status_code, r.text[:300])
            if r.status_code in (200, 409):
                return True, r.status_code, r.text[:300]
            if r.status_code < 500 and r.status_code != 429:
                return False, r.status_code, r.text[:300]
        except Exception as e:
            last = (0, "%s: %s" % (type(e).__name__, str(e)[:200]))
        time.sleep(1.5 * (attempt + 1))
    return False, last[0], last[1]


def _push(token, uid, msgs, retry_key) -> tuple:
    """push หา 1 คน (ลิงก์ของแต่ละคนไม่ซ้ำกัน) → (สำเร็จไหม, สถานะ, คำตอบ) · 409 = รับไปแล้ว · ไม่จด eventlog รายคน"""
    last = (0, "")
    for attempt in range(2):
        try:
            r = requests.post(PUSH_URL, timeout=20, json={"to": uid, "messages": msgs},
                              headers={"Authorization": "Bearer " + token, "Content-Type": "application/json",
                                       "X-Line-Retry-Key": retry_key})
            last = (r.status_code, r.text[:300])
            if r.status_code in (200, 409):
                return True, r.status_code, ""
            if r.status_code < 500 and r.status_code != 429:
                return False, r.status_code, r.text[:300]
        except Exception as e:
            last = (0, "%s: %s" % (type(e).__name__, str(e)[:200]))
        time.sleep(1.0 * (attempt + 1))
    return False, last[0], last[1]


def send(body, user) -> dict:
    """ส่งจริง — ด่านครบแล้วค่อยยิง · คืนผล (เก็บใน `Broadcast`)
    ไม่มีลิงก์ = multicast ชุดละ 500 คน (รอผลในคำขอนี้) · มีลิงก์ติดตาม = ส่งทีละคนเบื้องหลัง (ลิงก์ของแต่ละคนไม่ซ้ำกัน)"""
    from dashboard.services import eventlog
    from dashboard.services import line_channels as LC
    from .chat import _explain, reply_on
    cid = str(body.get("client_id") or "").strip()[:40]
    if not re.match(r"^[A-Za-z0-9_-]{8,40}$", cid):
        raise BError("คำขอไม่ถูกต้อง (ไม่มีรหัสกันกดซ้ำ) — รีเฟรชหน้าแล้วลองใหม่")
    old = Broadcast.objects.filter(client_id=cid).first()
    if old:
        return {"ok": True, "dup": True, "item": item_json(old), "message": "ส่งไปแล้ว (กดซ้ำ)"}
    if not reply_on():
        raise BError("ยังปิดการส่งหาลูกค้าอยู่ (ตั้งใจล็อกไว้) — เปิดด้วย `manage.py checkout_config --reply on`")
    c = clean_content(body.get("content"))
    t = tested(c)
    if not t:
        raise BError("ต้องกด \"ส่งทดสอบ\" ด้วยเนื้อหานี้ก่อน (ภายใน %d ชม.) — แก้ข้อความแล้วต้องทดสอบใหม่" % TEST_VALID_H)
    msgs, infos, store, links = build(c)
    f = clean_filters(body.get("filters"))
    full = audience(f)["rows"]
    hit = [r for r in full if r["src"] == "line" and r["uid"]]
    n = len(hit)
    if not n:
        raise BError("ไม่มีลูกค้า LINE ในกลุ่มนี้")
    if n > MAX_RECIPIENTS:
        raise BError("กลุ่มนี้ใหญ่เกินไป (%s ราย · ส่งได้ครั้งละไม่เกิน %s) — กรองให้แคบลง" % (format(n, ","), format(MAX_RECIPIENTS, ",")))
    try:
        confirm = int(body.get("confirm") or 0)
    except (TypeError, ValueError):
        confirm = 0
    if confirm != n:
        return {"ok": False, "needConfirm": True, "count": n,
                "error": "จำนวนผู้รับเปลี่ยนเป็น %s ราย (ข้อมูลขยับระหว่างนี้) — ตรวจแล้วกดส่งอีกครั้ง" % format(n, ",")}
    ch = _channels(hit)
    groups = {}
    for r in hit:
        groups.setdefault(ch.get(r["uid"]) or "crm", []).append(r)
    for k, rs in groups.items():
        if not LC.account_of(k):
            raise BError("ยังไม่ได้ตั้ง token ของบัญชี %s (ลูกค้า %s ราย)" % (_acc_name(k), format(len(rs), ",")))
        q = quota(k)
        if q.get("left") is not None and q["left"] < len(rs):
            raise BError("โควต้าข้อความเดือนนี้ของ %s เหลือ %s แต่ต้องส่ง %s ราย — ซื้อเพิ่มใน LINE OA Manager หรือกรองกลุ่มให้เล็กลง"
                         % (_acc_name(k), format(q["left"], ","), format(len(rs), ",")))
    who = _who(user)
    emp = C.employee_of(user)
    try:
        with transaction.atomic():
            b = Broadcast.objects.create(
                client_id=cid, text=c["text"], images=[x["full"] for x in c["images"]], cars=c["cars"],
                links=links, link_title=c.get("link_title", ""), mode="push" if links else "multicast",
                filters=f, audience=describe(f), total=n, fb_skipped=sum(1 for r in full if r["src"] == "fb"),
                accounts={k: {"name": _acc_name(k), "n": len(rs), "ok": 0, "fail": 0, "error": ""} for k, rs in groups.items()},
                created_by=who, tested_by=t.get("by", "")[:80],
                tested_at=datetime.fromisoformat(t["at"]) if t.get("at") else None)
    except IntegrityError:
        old = Broadcast.objects.filter(client_id=cid).first()
        return {"ok": True, "dup": True, "item": item_json(old) if old else None, "message": "ส่งไปแล้ว (กดซ้ำ)"}

    if links:
        now = timezone.now().isoformat(timespec="seconds")
        _kv_set(JOB_KEY % b.pk, {"tpl": json.dumps(msgs, ensure_ascii=False), "n": len(links), "store": store,
                                 "plan": [[r["id"], r["uid"], ch.get(r["uid"]) or "crm"] for r in hit],
                                 "cid": cid, "who": who, "emp": emp.pk if emp else None, "at": now})
        _kv_set(JOBST_KEY % b.pk, {"at": now, "failed": {}})
        _start(b.pk)
        b.refresh_from_db()
        secs = max(5, n // PUSH_RATE)
        eta = ("%d วินาที" % secs) if secs < 90 else ("%d นาที" % round(secs / 60.0))
        if b.status == Broadcast.SENDING:
            msg = ("เริ่มส่งทีละคนแล้ว %s ราย (ลิงก์ของแต่ละคนไม่ซ้ำกัน เพื่อรู้ว่าใครกด) · ใช้เวลาประมาณ %s "
                   "— ดูความคืบหน้าในประวัติด้านล่าง" % (format(n, ","), eta))
        else:
            msg = _done_msg(b)
        return {"ok": b.status != Broadcast.FAILED, "sending": b.status == Broadcast.SENDING, "item": item_json(b),
                "message": msg, "error": "" if b.status != Broadcast.FAILED else b.error}

    t0 = time.time()
    done_rows, accounts, errors = [], dict(b.accounts or {}), []
    for k, rs in groups.items():
        tok = LC.token_of(k)
        st = accounts.setdefault(k, {"name": _acc_name(k), "n": len(rs), "ok": 0, "fail": 0, "error": ""})
        for i in range(0, len(rs), BATCH):
            part = rs[i:i + BATCH]
            ok, code, text = _multicast(tok, [r["uid"] for r in part], msgs, str(uuid.uuid5(uuid.NAMESPACE_URL, "%s:%s:%d" % (cid, k, i))))
            if ok:
                st["ok"] += len(part)
                done_rows += part
            else:
                st["fail"] += len(part)
                st["error"] = _explain(code, text) if code else text
                errors.append("%s: %s" % (st["name"], st["error"]))
            try:
                eventlog.log(eventlog.SEND, name="บรอดแคสต์ #%d" % b.pk, target=k, ok=ok,
                             status=code or None, recipients=len(part), msgs=len(msgs),
                             error=(None if ok else (text or "")[:300]))
            except Exception:
                pass
    sent = sum(a["ok"] for a in accounts.values())
    failed = sum(a["fail"] for a in accounts.values())
    try:
        _store(b, done_rows, ch, store, who, emp)
    except Exception as e:
        errors.append("บันทึกลงแชทไม่สำเร็จ: %s" % str(e)[:120])
    b.sent, b.failed, b.accounts = sent, failed, accounts
    b.recipients = [r["id"] for r in done_rows]
    b.status = Broadcast.DONE if not failed else (Broadcast.PARTIAL if sent else Broadcast.FAILED)
    b.error = "; ".join(errors)[:300]
    b.finished_at = timezone.now()
    b.save(update_fields=["sent", "failed", "accounts", "recipients", "status", "error", "finished_at"])
    try:
        eventlog.log("broadcast", name="บรอดแคสต์ #%d" % b.pk, target=who, ok=not failed,
                     ms=int((time.time() - t0) * 1000), total=n, sent=sent, failed=failed, audience=b.audience)
    except Exception:
        pass
    return {"ok": sent > 0, "item": item_json(b), "message": _done_msg(b), "error": "" if sent else b.error}


def _done_msg(b) -> str:
    if not b.failed:
        return "ส่งแล้ว %s ราย" % format(b.sent, ",")
    return "ส่งได้ %s · ไม่สำเร็จ %s ราย — %s" % (format(b.sent, ","), format(b.failed, ","), b.error)


def _store(b, rows, ch, store, who, emp):
    """เก็บข้อความลงบทสนทนาของลูกค้าที่ส่งถึง + ประวัติ "ส่งบรอดแคสต์" — ไม่แตะนาฬิกาตอบ/ยังไม่อ่าน"""
    if not rows:
        return
    now = timezone.now()
    by = ("บรอดแคสต์ · %s" % who)[:80]
    chats, logs = [], []
    for r in rows:
        p, uid = r["p"], r["uid"]
        for i, s in enumerate(store):
            extra = {"source": "broadcast", "broadcast": b.pk}
            media = s["type"] == GroupChat.IMAGE
            if media:
                extra.update({"out_file": s["file"], "out_preview": s["prev"]})
            chats.append(GroupChat(
                chat_type=GroupChat.USER, message_id="%s%d:%d:%d" % (C.BCAST_PREFIX, b.pk, r["id"], i),
                sender_id=uid, sender_name=(p.show_name or "")[:120], direction=GroupChat.OUT,
                msg_type=s["type"], text=s["text"], channel=ch.get(uid, "") or "crm", has_media=media,
                extra=extra, sent_by=emp, sent_by_name=by, sent_at=now))
        logs.append(ChatOwnerLog(chat_id=r["id"], action=ChatOwnerLog.BCAST, by_name=who[:80], at=now,
                                 note=("บรอดแคสต์ #%d: %s" % (b.pk, (b.text or "[รูป/การ์ดรถ/ลิงก์]").replace("\n", " ")))[:200]))
    GroupChat.objects.bulk_create(chats, batch_size=500, ignore_conflicts=True)
    ChatOwnerLog.objects.bulk_create(logs, batch_size=500)


# ─────────────────────────── ส่งทีละคนเบื้องหลัง (มีลิงก์ติดตาม) ───────────────────────────
# งานอยู่ใน KV `bcast_job:<id>` (ข้อความต้นแบบ + รายชื่อ) · ความคืบหน้าเก็บที่แถว Broadcast (sent/failed/recipients)
# + KV `bcast_jobst:<id>` (เวลาล่าสุด + คนที่ส่งไม่ถึง) → เซิร์ฟเวอร์รีสตาร์ทกลางทาง = `resume_stale` ทำต่อจากที่ค้าง
# (X-Line-Retry-Key ต่อคน = ส่งซ้ำคนเดิม LINE ไม่ส่งซ้ำ ภายใน 24 ชม.)
BG = True
_RUNNING = set()


def _kv_get(k) -> dict:
    from dashboard.services import cache_store
    try:
        return (cache_store.get_kv(k) or {}).get("data") or {}
    except Exception:
        return {}


def _kv_set(k, data):
    from dashboard.services import cache_store
    cache_store.set_kv(k, data)


class _JobLock:
    def __init__(self, bid):
        self.bid, self.got = int(bid), False

    def __enter__(self):
        from django.db import connection
        if connection.vendor != "postgresql":
            self.got = True
            return self
        with connection.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s, %s)", [JOB_LOCK, self.bid])
            self.got = bool(cur.fetchone()[0])
        return self

    def __exit__(self, *a):
        from django.db import connection
        if self.got and connection.vendor == "postgresql":
            try:
                with connection.cursor() as cur:
                    cur.execute("SELECT pg_advisory_unlock(%s, %s)", [JOB_LOCK, self.bid])
            except Exception:
                pass
        return False


def _start(bid):
    if not BG:
        _run_job(bid)
        return
    if bid in _RUNNING:
        return
    import threading
    threading.Thread(target=_run_bg, args=(bid,), daemon=True, name="bcast-%d" % bid).start()


def _run_bg(bid):
    from django.db import connection
    try:
        _run_job(bid)
    except Exception as e:
        try:
            from dashboard.services import eventlog
            eventlog.log("broadcast", name="บรอดแคสต์ #%d — งานส่งพัง" % bid, ok=False, error=str(e)[:300])
        except Exception:
            pass
    finally:
        try:
            connection.close()
        except Exception:
            pass


def _run_job(bid):
    if bid in _RUNNING:
        return
    with _JobLock(bid) as lk:
        if not lk.got:
            return
        _RUNNING.add(bid)
        try:
            _job_body(bid)
        finally:
            _RUNNING.discard(bid)


def _job_body(bid):
    from dashboard.services import eventlog
    from dashboard.services import line_channels as LC
    from .chat import _explain
    from .models import Employee
    b = Broadcast.objects.filter(pk=bid).first()
    if not b or b.status != Broadcast.SENDING:
        return
    job = _kv_get(JOB_KEY % bid)
    if not job.get("plan"):
        b.status, b.error, b.finished_at = Broadcast.FAILED, "ข้อมูลงานส่งหาย — สร้างบรอดแคสต์ใหม่", timezone.now()
        b.save(update_fields=["status", "error", "finished_at"])
        return
    st = _kv_get(JOBST_KEY % bid)
    tpl, n, store = job["tpl"], int(job.get("n") or 0), job.get("store") or []
    cid = job.get("cid") or b.client_id or str(bid)
    who = job.get("who") or b.created_by or "แอดมิน"
    emp = Employee.objects.filter(pk=job.get("emp")).first() if job.get("emp") else None
    done = set(b.recipients or [])
    failed = {str(k): v for k, v in (st.get("failed") or {}).items()}
    todo = [x for x in job["plan"] if x[0] not in done and str(x[0]) not in failed]
    accounts = dict(b.accounts or {})
    for k in accounts:
        accounts[k] = dict(accounts[k])
    toks = {}
    for _oid, _uid, k in todo:
        if k not in toks:
            toks[k] = LC.token_of(k)
    t0 = time.time()

    def one(item):
        oid, uid, k = item
        tok = toks.get(k)
        if not tok:
            return oid, uid, k, False, 0, "ยังไม่ได้ตั้ง token ของบัญชีนี้"
        msgs = _fill(tpl, n, lambda i: click_url(bid, oid, i))
        ok, code, text = _push(tok, uid, msgs, str(uuid.uuid5(uuid.NAMESPACE_URL, "%s:%s" % (cid, oid))))
        return oid, uid, k, ok, code, text

    pend, last = [], time.time()
    errors = {}

    def flush():
        nonlocal pend, last
        if pend:
            rows = []
            by_id = {o.pk: o for o in ChatOwner.objects.select_related("profile").filter(pk__in=[x[0] for x in pend])}
            for oid, uid, _k in pend:
                o = by_id.get(oid)
                if o and o.profile_id:
                    rows.append({"id": oid, "p": o.profile, "uid": uid})
            try:
                _store(b, rows, {uid: k for _o, uid, k in pend}, store, who, emp)
            except Exception as e:
                errors["store"] = "บันทึกลงแชทไม่สำเร็จ: %s" % str(e)[:120]
        b.sent = len(done)
        b.failed = len(failed)
        b.recipients = sorted(done)
        b.accounts = accounts
        b.save(update_fields=["sent", "failed", "recipients", "accounts"])
        _kv_set(JOBST_KEY % bid, {"at": timezone.now().isoformat(timespec="seconds"), "failed": failed})
        pend, last = [], time.time()

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=PUSH_WORKERS) as ex:
        for oid, uid, k, ok, code, text in ex.map(one, todo):
            a = accounts.setdefault(k, {"name": _acc_name(k), "n": 0, "ok": 0, "fail": 0, "error": ""})
            if ok:
                a["ok"] = int(a.get("ok") or 0) + 1
                done.add(oid)
                pend.append((oid, uid, k))
            else:
                err = (_explain(code, text) if code else text) or "ส่งไม่สำเร็จ"
                a["fail"] = int(a.get("fail") or 0) + 1
                a["error"] = err[:200]
                failed[str(oid)] = err[:120]
                errors.setdefault("acc:" + k, "%s: %s" % (a.get("name") or k, err[:150]))
            if len(pend) >= FLUSH_N or time.time() - last > FLUSH_SEC:
                flush()
    flush()
    b.status = Broadcast.DONE if not failed else (Broadcast.PARTIAL if done else Broadcast.FAILED)
    b.error = "; ".join(errors.values())[:300]
    b.finished_at = timezone.now()
    b.save(update_fields=["status", "error", "finished_at"])
    _kv_set(JOB_KEY % bid, {"done": True, "at": timezone.now().isoformat(timespec="seconds"), "n": n})
    try:
        eventlog.log("broadcast", name="บรอดแคสต์ #%d (ทีละคน)" % bid, target=who, ok=not failed,
                     ms=int((time.time() - t0) * 1000), total=b.total, sent=b.sent, failed=b.failed, audience=b.audience)
    except Exception:
        pass


def resume_stale(now=None) -> list:
    """เรียกจาก `connect.tick` ทุกนาที — งานส่งทีละคนที่ค้าง (เซิร์ฟเวอร์รีสตาร์ทกลางทาง) ทำต่อจากที่ค้าง
    เกิน 20 ชม. (retry key ของ LINE หมดอายุ 24 ชม. → ส่งต่ออาจซ้ำ) = ปิดงานเป็น "ส่งได้บางส่วน" แทน"""
    now = now or timezone.now()
    out = []
    for b in Broadcast.objects.filter(status=Broadcast.SENDING, mode="push").only("id", "created_at", "sent"):
        if b.pk in _RUNNING:
            continue
        if now - b.created_at > timedelta(hours=20):
            Broadcast.objects.filter(pk=b.pk, status=Broadcast.SENDING).update(
                status=Broadcast.PARTIAL if b.sent else Broadcast.FAILED, finished_at=now,
                error="งานส่งหยุดกลางทางเกิน 20 ชม. — ไม่ส่งต่อ (กันลูกค้าได้ซ้ำ)")
            continue
        st = _kv_get(JOBST_KEY % b.pk)
        try:
            at = datetime.fromisoformat(st.get("at", ""))
            if timezone.is_naive(at):
                at = timezone.make_aware(at)
        except Exception:
            at = b.created_at
        if (now - at).total_seconds() < JOB_STALE_SEC:
            continue
        _start(b.pk)
        out.append(b.pk)
    return out


# ─────────────────────────── ประวัติ + คนกด ───────────────────────────
def _click_stats(bids) -> dict:
    from django.db.models import Count, Sum
    out = {}
    if not bids:
        return out
    qs = BroadcastClick.objects.filter(broadcast_id__in=list(bids))
    for r in qs.values("broadcast_id", "link").annotate(p=Count("id"), n=Sum("count")):
        s = out.setdefault(r["broadcast_id"], {"people": 0, "total": 0, "tagged": 0, "links": {}})
        s["links"][r["link"]] = {"people": r["p"], "n": r["n"] or 0}
        s["total"] += r["n"] or 0
    for r in qs.values("broadcast_id").annotate(u=Count("chat_id", distinct=True)):
        out.setdefault(r["broadcast_id"], {"people": 0, "total": 0, "tagged": 0, "links": {}})["people"] = r["u"]
    for r in qs.exclude(tagged="").values("broadcast_id").annotate(t=Count("chat_id", distinct=True)):
        out.setdefault(r["broadcast_id"], {"people": 0, "total": 0, "tagged": 0, "links": {}})["tagged"] = r["t"]
    return out


def item_json(b, stats=None) -> dict:
    links = list(b.links or [])
    s = (stats if stats is not None else _click_stats([b.pk])).get(b.pk) or {}
    per = s.get("links") or {}
    return {"id": b.pk, "status": b.status, "statusLabel": b.get_status_display(), "text": b.text,
            "images": ["/%s/%s" % (settings.MEDIA_URL.strip("/"), x[:-4] + "_p.jpg") for x in (b.images or [])],
            "cars": b.cars or [], "audience": b.audience, "total": b.total, "sent": b.sent, "failed": b.failed,
            "fb": b.fb_skipped, "accounts": b.accounts or {}, "error": b.error, "by": b.created_by,
            "testedBy": b.tested_by, "at": _iso(b.created_at), "finished": _iso(b.finished_at),
            "mode": b.mode or "multicast", "linkTitle": b.link_title,
            "links": [{"label": L.get("label") or "", "url": L.get("url") or "", "mode": L.get("mode") or "",
                       "tag": L.get("tag") or "", "people": (per.get(i) or {}).get("people", 0),
                       "clicks": (per.get(i) or {}).get("n", 0)} for i, L in enumerate(links)],
            "clickPeople": s.get("people", 0), "clickTotal": s.get("total", 0), "clickTagged": s.get("tagged", 0)}


def history(limit=20) -> list:
    rows = list(Broadcast.objects.all()[:limit])
    stats = _click_stats([b.pk for b in rows if b.links])
    return [item_json(b, stats) for b in rows]


def export_clicks(bid) -> tuple:
    """(ชื่อไฟล์, ไบต์ CSV, จำนวนคน) — ลูกค้าที่กดลิงก์ในบรอดแคสต์นี้ (1 แถว = 1 คน)"""
    try:
        b = Broadcast.objects.get(pk=int(bid))
    except (Broadcast.DoesNotExist, TypeError, ValueError):
        raise BError("ไม่พบบรอดแคสต์นี้")
    links = list(b.links or [])
    people = {}
    for ck in (BroadcastClick.objects.filter(broadcast=b, chat__isnull=False)
               .select_related("chat__profile", "chat__fb_profile", "chat__owner").order_by("first_at")):
        o = ck.chat
        e = people.setdefault(o.pk, {"o": o, "links": [], "n": 0, "first": ck.first_at, "last": ck.last_at, "tags": []})
        L = links[ck.link] if ck.link < len(links) else {}
        e["links"].append(L.get("label") or "ลิงก์ %d" % (ck.link + 1))
        e["n"] += ck.count
        e["first"] = min(e["first"], ck.first_at)
        e["last"] = max(e["last"], ck.last_at)
        if ck.tagged:
            e["tags"].append(ck.tagged)
    leads = {ld.chat_id: ld for ld in ChatLead.objects.filter(chat_id__in=list(people))}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["เลขแชท (Connect)", "ชื่อ", "ชื่อใน LINE", "เบอร์โทร", "ID LINE (ที่ลูกค้าให้)", "ลิงก์ที่กด", "กดรวม (ครั้ง)",
                "กดครั้งแรก", "กดล่าสุด", "แท็กที่ติดให้", "ผู้ดูแล"])
    for oid, e in people.items():
        o, ld = e["o"], leads.get(oid)
        p = C.cust(o)
        fmt = lambda d: timezone.localtime(d).strftime("%d/%m/%Y %H:%M") if d else ""
        w.writerow([oid, (ld.customer_name if ld and ld.customer_name else (p.show_name if p else "")) or "",
                    (p.display_name if p else "") or "",
                    ("'" + ld.phone) if ld and ld.phone else "", (ld.line_id if ld else "") or "",
                    ", ".join(e["links"]), e["n"], fmt(e["first"]), fmt(e["last"]), ", ".join(e["tags"]),
                    o.owner.nickname if o.owner_id else ""])
    name = "คนกดลิงก์_บรอดแคสต์%d_%s.csv" % (b.pk, timezone.localtime().strftime("%Y%m%d_%H%M"))
    return name, ("﻿" + buf.getvalue()).encode("utf-8"), len(people)
