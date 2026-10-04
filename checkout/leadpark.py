# -*- coding: utf-8 -*-
"""**ห้องพัก Lead** — กลุ่ม LINE "ADMIN เก็บ Lead" (4 ต.ค.69 · เจ้าของสั่ง "ไปดูห้องนั้นแล้วสร้าง pattern ออกมา")

แพทเทิร์นที่จับได้ (ข้อความจริงในห้องนี้ + ใบร่างที่เคยหลุดไปโพสต์ในห้องจ่ายเบอร์ 4 ใบ ก.ย.69)::

    Ac Lead No.   TLD10-                ← ★ มีแค่ตัวหน้า+เดือน "ยังไม่มีเลขรัน"
    Ads  :
    ชื่อ Account : Porsche              ← ชื่อบัญชี TikTok ของลูกค้า
    ชื่อลูกค้า :
    ID LINE : port0955759309            ← บางทีเบอร์โทรฝังอยู่ใน ID LINE
    ชื่อไลน์ :
    เบอร์โทร :
    ช่องทาง  :    Live tiktok ช่องขายบอส
    รถ : Yaris ativ
    ไลฟ์ :   live sale
    เพิ่มเติม  :
    ติดต่อได้เลยนะครับ                   ← ★ ยังไม่แท็กเซลล์

= **"ใบจ่ายลีดฉบับร่าง"** เทมเพลตเดียวกับใบจริงทุกช่อง ต่างแค่ 2 อย่าง: เลขลีดไม่มีเลขรัน + ไม่มี @เซลล์

**วงจรของลีด 1 ราย (วัดจากเคสจริง 4 ราย ก.ย.69)**:
  1. แอดมินพักใบร่างไว้ (ตอนนี้ = ห้อง "ADMIN เก็บ Lead")
  2. ใบจริงที่มีเลข + @เซลล์ ตามมาในห้องจ่ายเบอร์ (ช่องทาง/บัญชี/เบอร์เหมือนเดิมเป๊ะ) — เร็วสุด 17 วิ ช้าสุด 15 นาที
  3. (บางราย) ถูกส่งต่อในห้อง REJECT เป็น `R<เลข>/1`

ไฟล์นี้: แกะใบร่าง (`parse_draft`) → จับคู่กับใบจริงที่ตามมาด้วย **เบอร์โทร / ID LINE**
(ไม่มีทั้งคู่ = ชื่อ Account + ช่องทาง) → ลีดไหน "ยังรอเลข" · ลีดไหน "จ่ายแล้ว รอไปกี่นาที" (`board`)

⚠️ **อ่านอย่างเดียว** ไม่ส่งอะไรเข้ากลุ่ม · ไม่เก็บข้อมูลเพิ่ม (อ่านจาก `checkout_groupchat` ที่เก็บอยู่แล้ว
อายุ 90 วันตามเดิม) · ห้องนี้เพิ่งมีบอทเข้า 4 ต.ค.69 13:23 — แพทเทิร์นจะชัดขึ้นเมื่อมีข้อความมากกว่านี้
"""
from __future__ import annotations

import re
import time
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from .leadgroup import parse_fields, parse_leadsheet
from .models import GroupChat

# ห้องพัก Lead — จับจากชื่อกลุ่ม (แบบเดียวกับ leadgroup.GROUP_HINTS) · "ทีมAdmin" ทั่วไปไม่โดนจับ
PARK_HINTS = ("เก็บ lead", "เก็บlead", "เก็บลีด", "พัก lead", "พักlead", "พักลีด")
# ห้องที่ใบจริง (มีเลข + @เซลล์) ถูกโพสต์ — รวมห้อง REJECT
ASSIGN_HINTS = ("จ่ายเบอร์",)
WARN_MIN = 30          # พักเกินนี้ = ขึ้นแดง (เคสจริงได้เลขภายใน 15 นาทีทุกราย)
DAYS = 7               # ย้อนดูใบร่างกี่วัน — พักนานกว่านี้แล้วยังไม่จ่าย ถือว่าตกค้าง ไม่โชว์แล้ว

# "Ac Lead No.   TLD10-" — ตัวหน้า + เดือน (มี/ไม่มีก็ได้) + ขีด แล้ว "จบบรรทัด" (ไม่มีเลขรันตามมา)
_DRAFT_NO = re.compile(r"Ac\s*Lead\s*No\.?[ \t]*[:：]?[ \t]*([A-Za-z]{2,6})?[ \t]*(\d{1,2})?[ \t]*-?[ \t\r]*$",
                       re.I | re.M)
_PREFIX = re.compile(r"^(R?)(A?)(NLD|WLD|HLD|BLD|TLD|TALD|LD)$")
_TYPE = {"NLD": "Moderate", "WLD": "Hot", "HLD": "Very Hot", "BLD": "BLD", "TLD": "TLD", "TALD": "TLD", "LD": ""}


def _phones(*vals) -> list:
    from .connect import phones_in          # ตัวเดียวกับที่ Connect ใช้จับเบอร์จากแชท ("port0955759309" ก็จับได้)
    return phones_in([v for v in vals if v])


def parse_draft(text: str) -> dict | None:
    """ใบจ่ายลีดฉบับร่าง (ยังไม่มีเลขรัน) → dict · ใบจริงที่มีเลขแล้ว/ข้อความอื่น → None"""
    t = text or ""
    m = _DRAFT_NO.search(t)
    if not m or parse_leadsheet(t):
        return None
    prefix = (m.group(1) or "").upper()
    pm = _PREFIX.match(prefix)
    out = {
        "prefix": prefix + (m.group(2) or "") + "-",
        "base": pm.group(3) if pm else prefix,
        "reject": bool(pm and pm.group(1)),
        "admin": bool(pm and pm.group(2)),
        "month": int(m.group(2)) if m.group(2) else 0,
        "type": _TYPE.get(pm.group(3), "") if pm else "",
    }
    out.update(parse_fields(t))
    out["phones"] = _phones(out.get("phone"), out.get("line_id"))
    return out


def _norm(s) -> str:
    return re.sub(r"[\s@\-_.]", "", str(s or "")).lower()


def keys(d: dict) -> tuple[set, str]:
    """ตัวตนของลีด → (คีย์แข็ง, คีย์อ่อน)

    คีย์แข็ง = เบอร์โทร + ID LINE (ที่ไม่ใช่เบอร์) — ตรงกัน 1 ตัว = คนเดียวกันแน่
    คีย์อ่อน = ชื่อ Account + ช่องทาง — ใช้เฉพาะตอน "ไม่มีคีย์แข็งเลย" (ชื่อ TikTok สั้นๆ อย่าง "B." ซ้ำกันได้)
    """
    strong = {"p:" + p for p in (d.get("phones") or [])}
    lid = _norm(d.get("line_id"))
    if len(lid) >= 4 and not lid.isdigit():
        strong.add("l:" + lid)
    acc = _norm(d.get("account"))
    weak = ("a:%s|%s" % (acc, _norm(d.get("channel")))) if len(acc) >= 2 else ""
    return strong, weak


def _same(a: dict, b: dict) -> bool:
    if a["strong"] and b["strong"]:
        return bool(a["strong"] & b["strong"])
    if not a["strong"] and not b["strong"]:
        return bool(a["weak"]) and a["weak"] == b["weak"]
    return False


def _rooms(hints) -> Q:
    q = Q()
    for h in hints:
        q |= Q(group_name__icontains=h)
    return q


_CACHE = {"at": 0.0, "key": None, "val": None}


def board(days: int = DAYS, now=None, cache_sec: int = 30) -> dict:
    """ลีดในห้องพัก: ยังรอเลข (`waiting` · พักนานสุดขึ้นก่อน) + จ่ายแล้ว (`assigned` · ล่าสุดก่อน)

    หน้า Connect เรียกทุกครั้งที่โหลดรายชื่อ (ทุก 8 วิ) → จำผลไว้ 30 วิต่อ process
    """
    if cache_sec and now is None and _CACHE["val"] is not None and _CACHE["key"] == days \
            and time.time() - _CACHE["at"] < cache_sec:
        return _CACHE["val"]
    real_now = now is None
    now = now or timezone.now()
    since = now - timedelta(days=days)
    park_q, asg_q = _rooms(PARK_HINTS), _rooms(ASSIGN_HINTS)
    rows = list(GroupChat.objects.filter(chat_type=GroupChat.GROUP, sent_at__gte=since, sent_at__lte=now)
                .filter(park_q | asg_q).filter(text__icontains="lead no")
                .order_by("sent_at", "id").only("group_name", "sender_name", "text", "sent_at"))
    room = (GroupChat.objects.filter(chat_type=GroupChat.GROUP).filter(park_q)
            .order_by("-sent_at").values_list("group_name", flat=True).first()) or ""

    drafts, fulls = [], []
    for g in rows:
        d = parse_draft(g.text)
        if d:
            s, w = keys(d)
            if s or w:                                   # ใบร่างเปล่า (ไม่มีอะไรระบุตัวลูกค้า) จับคู่ไม่ได้ — ข้าม
                drafts.append({"g": g, "d": d, "strong": s, "weak": w})
            continue
        f = parse_leadsheet(g.text)
        if f:
            f["phones"] = _phones(f.get("phone"), f.get("line_id"))
            s, w = keys(f)
            fulls.append({"g": g, "d": f, "strong": s, "weak": w,
                          "reject": f["lead_code"].startswith("R")})

    items = []
    for x in drafts:
        at = x["g"].sent_at
        # ใบร่างเดิมโพสต์ซ้ำ (ยังไม่ได้เลข) = ลีดเดิม ไม่ใช่ลีดใหม่ — นับว่าโพสต์ซ้ำกี่ครั้ง
        dup = next((it for it in items if _same(it, x)
                    and (it["_asg"] is None or it["_asg"]["g"].sent_at > at)), None)
        if dup:
            dup["reposts"] += 1
            continue
        # ใบจริงที่ตามมา: ลีดรีเจ็ค (R…) จับคู่กับใบ R เท่านั้น · ลีดปกติไม่นับใบ R (นั่นคือการส่งต่อเคสรีเจ็คทีหลัง)
        asg = next((f for f in fulls if f["g"].sent_at >= at and f["reject"] == x["d"]["reject"]
                    and _same(f, x)), None)
        d = x["d"]
        items.append({
            "strong": x["strong"], "weak": x["weak"], "_asg": asg, "reposts": 0,
            "at": _iso(at), "by": x["g"].sender_name or "", "room": x["g"].group_name or "",
            "prefix": d["prefix"], "type": d["type"],
            "account": d.get("account", ""), "name": d.get("name", ""), "lineId": d.get("line_id", ""),
            "phone": (d.get("phones") or [""])[0], "channel": d.get("channel", ""), "car": d.get("car", ""),
            "live": d.get("live", ""), "more": d.get("more", ""), "ads": d.get("ads", ""),
            "code": asg["d"]["lead_code"] if asg else "",
            "seller": (asg["d"].get("assigned") or "") if asg else "",
            "assignedAt": _iso(asg["g"].sent_at) if asg else "",
            "assignedBy": (asg["g"].sender_name or "") if asg else "",
            "assignedRoom": (asg["g"].group_name or "") if asg else "",
            "waitMin": int(((asg["g"].sent_at if asg else now) - at).total_seconds() // 60),
        })
    for it in items:
        for k in ("strong", "weak", "_asg"):
            it.pop(k, None)
    waiting = sorted([i for i in items if not i["code"]], key=lambda i: i["at"])
    assigned = sorted([i for i in items if i["code"]], key=lambda i: i["assignedAt"], reverse=True)
    today = timezone.localdate(now)
    done_today = [i for i in assigned if i["assignedAt"][:10] == today.isoformat()]
    out = {
        "room": room, "days": days, "warnMin": WARN_MIN,
        "waiting": waiting, "assigned": assigned[:30],
        "stats": {"waiting": len(waiting), "late": sum(1 for i in waiting if i["waitMin"] >= WARN_MIN),
                  "assignedToday": len(done_today),
                  "avgWaitMinToday": (round(sum(i["waitMin"] for i in done_today) / len(done_today))
                                      if done_today else None)},
    }
    if real_now:
        _CACHE.update(at=time.time(), key=days, val=out)
    return out


def _iso(dt):
    return timezone.localtime(dt).isoformat(timespec="seconds") if dt else ""
