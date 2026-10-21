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
"""
import csv
import hashlib
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
from django.db.models import Max
from django.utils import timezone

from . import connect as C
from .models import Broadcast, ChatLead, ChatOwner, ChatOwnerLog, GroupChat

MULTICAST_URL = "https://api.line.me/v2/bot/message/multicast"
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


class BError(Exception):
    """ทำไม่ได้ — ข้อความนี้โชว์ผู้ใช้ได้เลย"""


# ─────────────────────────── กลุ่มลูกค้า ───────────────────────────
def _optout(tags) -> bool:
    for t in tags or ():
        s = str(t or "").replace(" ", "")
        if any(s.startswith(x) for x in _OPTOUT):
            return True
    return False


def _rows() -> list:
    """ลูกค้าทุกรายใน Connect (ไม่รวมพนักงาน/ลูกค้าจำลอง) — 1 แถว = 1 ลูกค้า"""
    from . import crm
    qs = (ChatOwner.objects.select_related("profile", "fb_profile", "owner", "lead")
          .exclude(profile__user_id__startswith=C.SIM_PREFIX))
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
    if f["q"]:
        q = f["q"].lower()
        hay = " ".join([r["name"], r["lineName"], r["phone"], r["lineId"], r["car"], " ".join(r["tags"])]).lower()
        if q not in hay and q.replace("-", "") not in r["phone"].replace("-", ""):
            return "q"
    if f["closed"] and r["stage"] in CLOSED:
        return "closed"
    if _optout(r["tags"]):
        return "optout"
    return ""


_EPOCH = timezone.make_aware(datetime(2000, 1, 1))


def audience(f, rows=None) -> dict:
    """{rows: ที่เข้ากลุ่ม · optout · closed} — ไม่เข้าเพราะไม่รับข่าวสาร/ปิดการขาย นับแยกให้หน้าเว็บบอก"""
    rows = _rows() if rows is None else rows
    now = timezone.now()
    hit, optout, closed = [], 0, 0
    for r in rows:
        why = _match(r, f, now)
        if not why:
            hit.append(r)
        elif why == "optout":
            optout += 1
        elif why == "closed":
            closed += 1
    hit.sort(key=lambda r: r["last"] or _EPOCH, reverse=True)
    return {"rows": hit, "optout": optout, "closed": closed}


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
            "last": _iso(r["last"])}


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
        "optout": a["optout"], "closed": a["closed"], "all": len(rows),
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
                "LINE userId", "แท็ก", "รถที่สนใจ", "ขั้นของลีด", "ลีด", "ผู้ดูแล", "คุยล่าสุด"])
    for r in hit:
        last = timezone.localtime(r["last"]).strftime("%d/%m/%Y %H:%M") if r["last"] else ""
        w.writerow([r["id"], r["name"], r["lineName"], "LINE" if r["src"] == "line" else "Facebook",
                    _acc_name(ch.get(r["uid"], "")) if r["src"] == "line" else "",
                    ("'" + r["phone"]) if r["phone"] else "", r["lineId"], r["uid"],
                    ", ".join(r["tags"]), r["car"], STAGE_NAME.get(r["stage"], r["stage"]),
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
    if not (text or imgs or cars):
        raise BError("ยังไม่มีเนื้อหา — พิมพ์ข้อความ แนบรูป หรือเลือกรถอย่างน้อย 1 อย่าง")
    return {"text": text, "images": imgs, "cars": cars}


def content_hash(c) -> str:
    raw = json.dumps({"t": c["text"], "i": [x["full"] for x in c["images"]], "c": c["cars"]},
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


def _bubble(info, img_url) -> dict:
    body = [{"type": "text", "text": info["title"], "weight": "bold", "size": "md", "wrap": True}]
    if info["sub"]:
        body.append({"type": "text", "text": info["sub"], "size": "sm", "color": "#6b6280", "wrap": True})
    if info["priceText"]:
        body.append({"type": "text", "text": info["priceText"], "size": "lg", "weight": "bold", "color": "#7c3aed"})
    b = {"type": "bubble", "size": "kilo",
         "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": body}}
    if img_url:
        b["hero"] = {"type": "image", "url": img_url, "size": "full", "aspectRatio": "4:3", "aspectMode": "cover"}
        if info["link"]:
            b["hero"]["action"] = {"type": "uri", "uri": info["link"]}
    if info["link"]:
        b["footer"] = {"type": "box", "layout": "vertical", "contents": [
            {"type": "button", "style": "primary", "color": "#7c3aed", "height": "sm",
             "action": {"type": "uri", "label": "ดูรายละเอียดรถ", "uri": info["link"]}}]}
    return b


def build(c) -> tuple:
    """เนื้อหา → (ข้อความ LINE ≤5 ชิ้น, ข้อมูลรถ, คำอธิบายแต่ละชิ้นที่จะเก็บลงแชท)"""
    if (c["images"] or c["cars"]) and not _base().startswith("https://"):
        raise BError("ส่งรูป/การ์ดรถได้เฉพาะบนเซิร์ฟเวอร์จริง — LINE ต้องดึงรูปจากลิงก์ https")
    msgs, store = [], []
    if c["text"]:
        msgs.append({"type": "text", "text": c["text"]})
        store.append({"type": GroupChat.TEXT, "text": c["text"]})
    for im in c["images"]:
        msgs.append({"type": "image", "originalContentUrl": _media_url(im["full"]),
                     "previewImageUrl": _media_url(im["prev"])})
        store.append({"type": GroupChat.IMAGE, "text": "[รูป]", "file": im["full"], "prev": im["prev"]})
    infos = []
    cars = cars_of(c["cars"])
    if c["cars"] and not cars:
        raise BError("ไม่พบรถที่เลือก (อาจขายไปแล้ว) — เลือกรถใหม่")
    if cars:
        bubbles = []
        for car in cars:
            info = _car_info(car)
            rel = _car_image(car)
            info["img"] = ("/%s/%s" % (settings.MEDIA_URL.strip("/"), rel)) if rel else ""
            infos.append(info)
            bubbles.append(_bubble(info, _media_url(rel) if rel else ""))
        alt = "รถแนะนำ: " + " · ".join(("%s %s" % (i["title"], i["priceText"])).strip() for i in infos)
        contents = bubbles[0] if len(bubbles) == 1 else {"type": "carousel", "contents": bubbles}
        msgs.append({"type": "flex", "altText": alt[:390], "contents": contents})
        store.append({"type": GroupChat.TEXT,
                      "text": "[การ์ดรถ] " + "\n".join(("%s %s %s" % (i["title"], i["sub"], i["priceText"])).strip()
                                                      for i in infos)})
    if len(msgs) > 5:
        raise BError("LINE ส่งได้ครั้งละไม่เกิน 5 ชิ้น (ข้อความ + รูป + การ์ดรถ)")
    return msgs, infos, store


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


def _test_target(user, account) -> tuple:
    """LINE userId ของแอดมินคนนี้ฝั่งบัญชีที่จะส่ง → (uid, บัญชี) · ไม่มีฝั่งนั้น = ฝั่งไหนก็ได้ที่มี token (หน้าตาเหมือนกัน)"""
    from dashboard.services import line_channels as LC
    from .models import LineProfile
    cands = []
    emp = C.employee_of(user)
    if emp:
        cands += list(LineProfile.objects.filter(employee=emp).values_list("user_id", "channel"))
    uid = ((user or {}).get("user_id") or "").strip()
    if uid.startswith("U"):
        cands += list(LineProfile.objects.filter(user_id=uid).values_list("user_id", "channel")) or [(uid, "")]
    seen, norm = set(), []
    for u, ch in cands:
        if u and u not in seen and u.startswith("U"):
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


def _tests() -> dict:
    from dashboard.services import cache_store
    try:
        return (cache_store.get_kv(KV_TEST) or {}).get("data") or {}
    except Exception:
        return {}


def test_send(body, user) -> dict:
    """ส่งเนื้อหาเดียวกับที่จะบรอดแคสต์ หาแอดมินคนที่กดเอง (ด่านบังคับก่อนส่งจริง)"""
    from dashboard.services import cache_store
    from dashboard.services import line_channels as LC
    from dashboard.services.line_notify import push_line_message
    from .chat import _explain
    c = clean_content(body.get("content"))
    msgs, infos, _ = build(c)
    acc = str(body.get("account") or "").strip().lower()
    uid, ch = _test_target(user, acc)
    if not uid:
        raise BError("ไม่พบ LINE ของคุณในระบบ — แอดบัญชี LINE OA ของร้านเป็นเพื่อนแล้วทักมา 1 ข้อความ แล้วลองใหม่")
    code, res = push_line_message(uid, msgs, LC.token_of(ch), what="บรอดแคสต์ (ส่งทดสอบ)")
    if code != 200:
        raise BError("ส่งทดสอบไม่สำเร็จ: " + _explain(code, res))
    h = content_hash(c)
    t = _tests()
    t[h] = {"at": timezone.now().isoformat(), "by": _who(user)}
    keep = sorted(t.items(), key=lambda x: x[1].get("at", ""), reverse=True)[:30]
    try:
        cache_store.set_kv(KV_TEST, dict(keep))
    except Exception:
        pass
    return {"ok": True, "hash": h, "account": ch, "accountName": _acc_name(ch), "cars": infos,
            "message": "ส่งทดสอบเข้า LINE ของคุณแล้ว (%s) — ตรวจหน้าตาข้อความ แล้วค่อยกดส่งจริง" % _acc_name(ch)}


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


def send(body, user) -> dict:
    """ส่งจริง — ด่านครบแล้วค่อยยิง · คืนผล (เก็บใน `Broadcast`)"""
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
        raise BError("ต้องกด \"ส่งทดสอบหาตัวเอง\" ด้วยเนื้อหานี้ก่อน (ภายใน %d ชม.) — แก้ข้อความแล้วต้องทดสอบใหม่" % TEST_VALID_H)
    msgs, infos, store = build(c)
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
                filters=f, audience=describe(f), total=n, fb_skipped=sum(1 for r in full if r["src"] == "fb"),
                created_by=who, tested_by=t.get("by", "")[:80],
                tested_at=datetime.fromisoformat(t["at"]) if t.get("at") else None)
    except IntegrityError:
        old = Broadcast.objects.filter(client_id=cid).first()
        return {"ok": True, "dup": True, "item": item_json(old) if old else None, "message": "ส่งไปแล้ว (กดซ้ำ)"}

    t0 = time.time()
    done_rows, accounts, errors = [], {}, []
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
    msg = ("ส่งแล้ว %s ราย" % format(sent, ",")) if not failed else (
        "ส่งได้ %s · ไม่สำเร็จ %s ราย — %s" % (format(sent, ","), format(failed, ","), b.error))
    return {"ok": sent > 0, "item": item_json(b), "message": msg, "error": "" if sent else b.error}


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
                                 note=("บรอดแคสต์ #%d: %s" % (b.pk, (b.text or "[รูป/การ์ดรถ]").replace("\n", " ")))[:200]))
    GroupChat.objects.bulk_create(chats, batch_size=500, ignore_conflicts=True)
    ChatOwnerLog.objects.bulk_create(logs, batch_size=500)


# ─────────────────────────── ประวัติ ───────────────────────────
def item_json(b) -> dict:
    return {"id": b.pk, "status": b.status, "statusLabel": b.get_status_display(), "text": b.text,
            "images": ["/%s/%s" % (settings.MEDIA_URL.strip("/"), x[:-4] + "_p.jpg") for x in (b.images or [])],
            "cars": b.cars or [], "audience": b.audience, "total": b.total, "sent": b.sent, "failed": b.failed,
            "fb": b.fb_skipped, "accounts": b.accounts or {}, "error": b.error, "by": b.created_by,
            "testedBy": b.tested_by, "at": _iso(b.created_at), "finished": _iso(b.finished_at)}


def history(limit=20) -> list:
    return [item_json(b) for b in Broadcast.objects.all()[:limit]]
