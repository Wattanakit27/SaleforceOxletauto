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

ส่วนอ่านห้องพัก = **อ่านอย่างเดียว** ไม่เก็บข้อมูลเพิ่ม (อ่านจาก `checkout_groupchat` ที่เก็บอยู่แล้ว อายุ 90 วันตามเดิม)
★ 6 ต.ค.69 — ปุ่ม "จ่ายเบอร์" ของลีดในห้องพัก **ส่งใบเข้ากลุ่มจ่ายเบอร์จริง + แท็กเซลล์** (`slippost.py`)
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


def source_of(channel: str) -> str:
    """ช่องทางหลักจากช่อง "ช่องทาง" ของใบจ่ายลีด → tiktok / facebook / line / other (ป้ายสีในหน้า Connect)"""
    c = (channel or "").lower()
    if "tiktok" in c or "ติ๊กต็อก" in c or re.search(r"(^|[^a-z])tt([^a-z]|$)", c):
        return "tiktok"
    if "facebook" in c or "เพจ" in c or "messenger" in c or re.search(r"(^|[^a-z])fb([^a-z]|$)", c):
        return "facebook"
    if "line" in c or "ไลน์" in c:
        return "line"
    return "other"


_CACHE = {"at": 0.0, "key": None, "val": None}


def _scan(days: int, now):
    """อ่านแชทกลุ่ม → ใบร่างแต่ละราย + ใบจริงที่ตามมา (ส่วนที่หนัก — จำผลไว้ใน board)"""
    since = now - timedelta(days=days)
    park_q, asg_q = _rooms(PARK_HINTS), _rooms(ASSIGN_HINTS)
    rows = list(GroupChat.objects.filter(chat_type=GroupChat.GROUP, sent_at__gte=since, sent_at__lte=now)
                .filter(park_q | asg_q).filter(text__icontains="lead no")
                .order_by("sent_at", "id").only("group_name", "sender_name", "text", "sent_at", "message_id"))
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
            dup["_mids"].append(x["g"].message_id)
            continue
        # ใบจริงที่ตามมา: ลีดรีเจ็ค (R…) จับคู่กับใบ R เท่านั้น · ลีดปกติไม่นับใบ R (นั่นคือการส่งต่อเคสรีเจ็คทีหลัง)
        asg = next((f for f in fulls if f["g"].sent_at >= at and f["reject"] == x["d"]["reject"]
                    and _same(f, x)), None)
        d = x["d"]
        items.append({
            "strong": x["strong"], "weak": x["weak"], "_asg": asg, "_at": at, "_mids": [x["g"].message_id],
            "id": x["g"].message_id, "reposts": 0,
            "at": _iso(at), "by": x["g"].sender_name or "", "room": x["g"].group_name or "",
            "prefix": d["prefix"], "type": d["type"], "base": d["base"], "reject": d["reject"], "admin": d["admin"],
            "source": source_of(d.get("channel")),
            "account": d.get("account", ""), "name": d.get("name", ""), "lineId": d.get("line_id", ""),
            "phone": (d.get("phones") or [""])[0], "channel": d.get("channel", ""), "car": d.get("car", ""),
            "live": d.get("live", ""), "more": d.get("more", ""), "ads": d.get("ads", ""),
            # ใบจริงในห้องจ่ายเบอร์ (แอดมินโพสต์เอง)
            "code": asg["d"]["lead_code"] if asg else "",
            "seller": (asg["d"].get("assigned") or "") if asg else "",
            "assignedAt": _iso(asg["g"].sent_at) if asg else "",
            "assignedBy": (asg["g"].sender_name or "") if asg else "",
            "assignedRoom": (asg["g"].group_name or "") if asg else "",
        })
    for it in items:
        it["_asgAt"] = it["_asg"]["g"].sent_at if it["_asg"] else None
        for k in ("strong", "weak", "_asg"):
            it.pop(k, None)
    return room, items


def board(days: int = DAYS, now=None, cache_sec: int = 30) -> dict:
    """ลีดในห้องพัก: ยังรอเลข (`waiting` · พักนานสุดขึ้นก่อน) + ได้เลขแล้ว (`assigned` · ล่าสุดก่อน)
    + ซ่อนไว้ (`skipped` — แอดมินกด "ไม่ต้องจ่ายเบอร์")

    ได้เลขได้ 2 ทาง: **ใบจริงในห้องจ่ายเบอร์** (แอดมินโพสต์เอง · `code`) หรือ **กดจ่ายเบอร์ในหน้า Connect**
    (ตาราง ExtLead · `sys`) · ส่วนอ่านแชทกลุ่มจำผลไว้ 30 วิต่อ process แต่ ExtLead อ่านสดทุกครั้ง
    → กดจ่ายแล้วหายจากรายการทันที แม้คำขอถัดไปไปตก worker อื่นของ gunicorn
    """
    real_now = now is None
    now = now or timezone.now()
    if cache_sec and real_now and _CACHE["val"] is not None and _CACHE["key"] == days \
            and time.time() - _CACHE["at"] < cache_sec:
        room, raw = _CACHE["val"]
    else:
        room, raw = _scan(days, now)
        if real_now:
            _CACHE.update(at=time.time(), key=days, val=(room, raw))

    from .models import ExtLead
    mids = [m for it in raw for m in it["_mids"]]
    ext = {e.message_id: e for e in ExtLead.objects.filter(message_id__in=mids)} if mids else {}
    items = []
    for r in raw:
        it = {k: v for k, v in r.items() if not k.startswith("_")}
        e = next((ext[m] for m in r["_mids"] if m in ext), None)
        sys_at = None
        if e and e.code:
            sys_at = e.assigned_at
            it["sys"] = {"code": e.code, "seller": e.seller_name, "at": _iso(e.assigned_at), "by": e.assigned_by,
                         "demo": e.code_demo, "slip": slip_text(e),
                         # ส่งเข้ากลุ่มจ่ายเบอร์แล้วหรือยัง (ไม่สำเร็จ = หน้าเว็บมีปุ่ม "ส่งเข้ากลุ่มอีกครั้ง")
                         "post": {k: v for k, v in (e.post_info or {}).items() if k != "mid"} or None}
        if e and e.no_code and not e.code:
            it["skipped"] = {"by": e.no_code_by, "at": _iso(e.updated_at)}
        done = [t for t in (r["_asgAt"], sys_at) if t]
        end = min(done) if done else now
        it["doneAt"] = _iso(end) if done else ""
        it["waitMin"] = max(0, int((end - r["_at"]).total_seconds() // 60))
        items.append(it)

    waiting = sorted([i for i in items if not i["doneAt"] and not i.get("skipped")], key=lambda i: i["at"])
    assigned = sorted([i for i in items if i["doneAt"]], key=lambda i: i["doneAt"], reverse=True)
    skipped = [i for i in items if i.get("skipped") and not i["doneAt"]]
    today = timezone.localdate(now).isoformat()
    done_today = [i for i in assigned if i["doneAt"][:10] == today]
    return {
        "room": room, "days": days, "warnMin": WARN_MIN,
        "waiting": waiting, "assigned": assigned[:30], "skipped": skipped[:30],
        "stats": {"waiting": len(waiting), "late": sum(1 for i in waiting if i["waitMin"] >= WARN_MIN),
                  "assignedToday": len(done_today), "skipped": len(skipped),
                  "avgWaitMinToday": (round(sum(i["waitMin"] for i in done_today) / len(done_today))
                                      if done_today else None)},
    }


def forget():
    """ล้างผลที่จำไว้ (เรียกหลังจ่ายเบอร์/ซ่อนลีด) — ให้คำขอถัดไปใน process นี้อ่านใหม่"""
    _CACHE["val"] = None


# ─────────────────────────────────────────────────────────────
#  จ่ายเบอร์ลีดภายนอกจากหน้า Connect — ★ 6 ต.ค.69 ส่งเข้ากลุ่มจ่ายเบอร์จริง + แท็กเซลล์ (ไม่ลงชีต · slippost.py)
# ─────────────────────────────────────────────────────────────
KEEP_DAYS = 90         # ExtLead มีข้อมูลลูกค้า (เบอร์/ID LINE) — อายุเท่าแชทกลุ่มที่เป็นต้นทาง


def _draft_msg(mid: str):
    """ใบร่างจากแชทกลุ่ม (ห้องพัก/ห้องจ่ายเบอร์) → (GroupChat, parsed) · ไม่ใช่ใบร่าง = (None, None)"""
    g = (GroupChat.objects.filter(chat_type=GroupChat.GROUP, message_id=str(mid or ""))
         .filter(_rooms(PARK_HINTS) | _rooms(ASSIGN_HINTS)).first())
    d = parse_draft(g.text) if g else None
    return (g, d) if d else (None, None)


def _ext_for(g, d):
    from .models import ExtLead
    e, _ = ExtLead.objects.get_or_create(message_id=g.message_id, defaults=dict(
        group_id=g.group_id or "", group_name=(g.group_name or "")[:160], parked_at=g.sent_at,
        parked_by=(g.sender_name or "")[:80], source=source_of(d.get("channel")), prefix=d["prefix"][:16],
        account=(d.get("account") or "")[:120], customer_name=(d.get("name") or "")[:120],
        line_id=(d.get("line_id") or "")[:80], phone=((d.get("phones") or [""])[0])[:40],
        channel=(d.get("channel") or "")[:80], car_text=(d.get("car") or "")[:300],
        live=(d.get("live") or "")[:60], ads=(d.get("ads") or "")[:120], more=d.get("more") or ""))
    return e


def assign(mid: str, emp, base: str, admin: bool = False, reject: bool = False, code: str = "", by: str = ""):
    """ปุ่ม "จ่ายเบอร์" ของลีดในห้องพัก → (ok, ข้อความ, ExtLead|None)

    เลขรันชุดเดียวกับลูกค้า LINE OA (ล็อกกันเลขซ้ำ) · เลขซ้ำ = ปฏิเสธ · ได้เลขในห้องจ่ายเบอร์ไปแล้ว = ไม่ออกเลขทับ
    ★ 6 ต.ค.69 — **ส่งใบเข้ากลุ่มจ่ายเบอร์จริง + แท็กเซลล์** (เจ้าของ: "ช่องทางอื่นแท็กในกลุ่มก็พอ")
      สิทธิ์ในระบบ = จดว่าจ่ายให้ใคร (ลีดพวกนี้ไม่มีแชทให้ตอบ) · สวิตช์ปิด = โหมดทดลองเดิม
    """
    from . import connect as C
    if not emp or not emp.active:
        return False, "เลือกเซลล์ที่จะจ่ายเบอร์ให้ก่อน", None
    g, d = _draft_msg(mid)
    if not g:
        return False, "ไม่พบใบร่างนี้ในห้องพัก Lead (อาจหมดอายุแล้ว)", None
    it = next((i for i in board(cache_sec=0)["assigned"] if i["id"] == g.message_id and i.get("code")), None)
    if it:
        return False, "ลีดนี้ได้เลข %s ในห้องจ่ายเบอร์แล้ว (โดย %s)" % (it["code"], it["assignedBy"] or "-"), None
    c = C.cfg()
    real = C.slip_post_on(c) and not C.is_test_seller(emp)
    e = _ext_for(g, d)                            # สร้างแถวก่อนเข้าล็อก
    prefix = C.build_prefix(base, admin, reject)
    code = (code or "").strip().upper()
    if code and not C._CODE_RE.match(code):
        return False, "เลขลีดไม่ถูกรูปแบบ — ต้องเป็นแบบ TLD10-8410 (ตัวหน้า + เดือน + เลขรัน)", e
    try:
        with C.code_lock():
            e = type(e).objects.get(pk=e.pk)
            if e.code:
                raise C._Undo("ลีดนี้จ่ายเบอร์ %s ไปแล้ว — ไม่ออกเลขทับ" % e.code)
            code = code or C.next_code(prefix)
            if C.code_taken(code, ext_pk=e.pk):
                raise C._Undo("เลข %s ถูกใช้กับลูกค้าคนอื่นแล้ว" % code)
            e.code, e.code_demo = code, not real
            e.seller, e.seller_name = emp, emp.nickname[:80]
            e.assigned_at, e.assigned_by = timezone.now(), (by or "")[:80]
            e.no_code, e.no_code_by = False, ""
            e.post_info = {"sending": timezone.now().isoformat()} if real else {}
            e.save()
    except C._Undo as x:
        return False, str(x), e
    forget()
    if not real:
        why = "บัญชีทดสอบ — ไม่ส่งเข้ากลุ่มจริง" if C.slip_post_on(c) else "ทดลอง — ยังไม่ลงชีต ไม่โพสต์กลุ่ม"
        return True, "จ่ายเบอร์ %s ให้ %s แล้ว (%s)" % (code, emp.nickname, why), e
    from . import slippost
    info = _post(e, emp, by, c)
    return True, slippost.summary(code, emp.nickname, info), e


def post_body(e, by: str = "") -> str:
    """ใบที่ส่งเข้ากลุ่ม — ช่องเดียวกับใบร่างที่แอดมินพักไว้ + เลข"""
    from . import slippost
    f = {"code": e.code, "ads": e.ads, "account": e.account, "name": e.customer_name, "line_id": e.line_id,
         "line_name": "", "phone": e.phone, "channel": e.channel, "car": e.car_text, "live": e.live, "more": e.more}
    return slippost.body(f, ["จ่ายโดย: %s (ผ่านระบบ Connect)" % by] if by else [])


def _post(e, emp, by: str = "", c=None) -> dict:
    from . import slippost
    try:
        info = slippost.post(e.code, post_body(e, by), emp, by=by, c=c)
    except Exception as x:                        # การจ่ายในระบบบันทึกไปแล้ว — ห้ามกลายเป็น error 500
        info = {"ok": False, "at": _iso(timezone.now()), "by": (by or "")[:80], "error": "ส่งไม่สำเร็จ: %s" % str(x)[:120]}
    type(e).objects.filter(pk=e.pk).update(post_info=info)
    e.post_info = info
    forget()                                      # ใบที่ส่งสำเร็จถูกเก็บลงแชทกลุ่มแล้ว — ห้องพักต้องเห็นทันที
    return info


def repost(mid: str, by: str = ""):
    """ปุ่ม **"ส่งเข้ากลุ่มอีกครั้ง"** ของลีดภายนอก → (ok, ข้อความ) · ส่งสำเร็จไปแล้ว = ไม่ส่งซ้ำ"""
    from . import connect as C
    from . import slippost
    from .models import ExtLead
    e = ExtLead.objects.select_related("seller").filter(message_id=str(mid or "")).first()
    if not e or not e.code:
        return False, "ลีดนี้ยังไม่ได้จ่ายเบอร์"
    if e.code_demo:
        return False, "เลข %s ออกในโหมดทดลอง (ไม่ได้จองไว้) — ไม่ส่งเข้ากลุ่มจริง" % e.code
    if not e.seller or not e.seller.active:
        return False, "เซลล์ที่จ่ายให้ถูกปิดใช้งานแล้ว — จ่ายใหม่ไม่ได้จากปุ่มนี้"
    with C.code_lock():
        e = ExtLead.objects.select_related("seller").get(pk=e.pk)
        if (e.post_info or {}).get("ok"):
            return False, "ส่งใบจ่ายลีด %s เข้ากลุ่มไปแล้ว — ไม่ส่งซ้ำ" % e.code
        if slippost.sending(e.post_info):
            return False, "กำลังส่งอยู่ — รอสักครู่"
        e.post_info = dict(e.post_info or {}, sending=timezone.now().isoformat())
        e.save(update_fields=["post_info"])
    info = _post(e, e.seller, by)
    return bool(info.get("ok")), slippost.summary(e.code, e.seller.nickname, info)


def skip(mid: str, on: bool, by: str = ""):
    """ปุ่ม "ไม่ต้องจ่ายเบอร์" (ลีดซ้ำ/ไม่ใช่ลีดขาย) → (ok, ข้อความ) · on=False = เอากลับเข้ารายการรอเลข"""
    g, d = _draft_msg(mid)
    if not g:
        return False, "ไม่พบใบร่างนี้ในห้องพัก Lead (อาจหมดอายุแล้ว)"
    e = _ext_for(g, d)
    if on and e.code:
        return False, "ลีดนี้จ่ายเบอร์ %s ไปแล้ว" % e.code
    e.no_code, e.no_code_by = bool(on), ((by or "")[:80] if on else "")
    e.save(update_fields=["no_code", "no_code_by", "updated_at"])
    forget()
    return True, ("ซ่อนลีดนี้แล้ว — ไม่ต้องจ่ายเบอร์" if on else "เอากลับเข้ารายการรอเลขแล้ว")


def slip_text(e) -> str:
    """ใบจ่ายลีดของลีดภายนอก — รูปแบบเดียวกับที่แอดมินโพสต์ในห้องจ่ายเบอร์ (`parse_leadsheet` อ่านกลับได้)"""
    lines = [
        "Ac Lead No.   %s" % (e.code or "-"),
        "Ads  :   %s" % (e.ads or ""),
        "ชื่อ Account : %s" % (e.account or ""),
        "ชื่อลูกค้า : %s" % (e.customer_name or ""),
        "ID LINE : %s" % (e.line_id or ""),
        "ชื่อไลน์ : ",
        "เบอร์โทร : %s" % (e.phone or ""),
        "ช่องทาง  : %s" % (e.channel or ""),
        "รถ : %s" % (e.car_text or ""),
        "ไลฟ์ : %s" % (e.live or ""),
        "เพิ่มเติม  : %s" % (e.more or ""),
        "",
        "ติดต่อได้เลยนะครับ",
    ]
    if e.seller_name:
        lines.append("@%s" % e.seller_name)
    if e.code_demo:
        # เลขโหมดทดลองยังไม่ได้จองในชีต — กันเผลอก๊อปไปวางในกลุ่มจริงแล้วเลขชนกับของแอดมิน
        lines.insert(0, "⚠️ ทดลอง — เลขนี้ยังไม่ได้จองในชีตจริง")
    return "\n".join(lines)


def cleanup(now=None) -> int:
    """ลบ ExtLead ที่พักไว้เกิน KEEP_DAYS (มีเบอร์/ID LINE ลูกค้า — PDPA) · เรียกจาก connect.tick ทุกนาที (query เดียว)"""
    from .models import ExtLead
    now = now or timezone.now()
    n, _ = ExtLead.objects.filter(parked_at__lt=now - timedelta(days=KEEP_DAYS)).delete()
    return n


def _iso(dt):
    return timezone.localtime(dt).isoformat(timespec="seconds") if dt else ""
