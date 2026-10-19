# -*- coding: utf-8 -*-
"""**เก็บลีดอัตโนมัติ** — ทุกลีดได้เลขรันตั้งแต่ตอนเก็บ (ก่อนถึงเซลล์) · ใบลงกลุ่ม "ADMIN เก็บ Lead"
(★ 19 ต.ค.69 · เจ้าของสั่ง *"เก็บ Lead auto ลง Line กลุ่มและลงระบบของเราเพื่อให้แอดมินจ่ายต่อก็พอ · อย่าเพิ่งให้มันจ่าย Lead auto
· อยากให้รันต่อจากเดิมได้เลย code number"* แล้วต่อด้วย *"ทำทั้งคู่ให้ระบบทำงานร่วมกันได้ละค่อยๆตัดไลน์"*)

ลีดเข้า 3 ทาง — ใช้ตัวนับเลขรันชุดเดียวกัน (`connect.last_running` · ล็อก `code_lock` ตัวเดียวกับปุ่มจ่ายเบอร์)
  1. **แชท LINE/FB** — ลูกค้าให้เบอร์/ID LINE (`connect.capture_contact`) → รอ `after_min` นาที → จองเลข
     → `ChatLead.auto[KEY]` → ใบเลขเต็มลงกลุ่ม (`collect_one`)
  2. **ใบร่างที่แอดมินพักในกลุ่ม ADMIN เก็บ Lead** (TikTok/ไลฟ์/โทรเข้า แบบที่ทำอยู่ทุกวัน) → บอทจองเลข
     → `ExtLead.auto[KEY]` → **ตอบใบเลขเต็มในกลุ่ม** (`number_draft` · สวิตช์ `drafts`)
  3. **ฟอร์ม "เพิ่มลีดเอง" ในห้องพัก Lead ของเว็บ** → ประกอบใบร่างเก็บในคลังแชทกลุ่ม → ทางเดียวกับข้อ 2 (`add_manual`)
     · ทีมค่อยๆ ย้ายมากรอกในเว็บ แล้วตัด LINE ทีหลัง (เจ้าของ "ค่อยๆตัดไลน์")

แล้วแอดมินจ่ายเซลล์ได้ 2 แบบ ได้เลขเดิมทั้งคู่:
  - กดชื่อเซลล์ในห้องพัก Lead → `assign_lead` / `leadpark.assign` **ใช้เลขที่จองไว้** (`code_for_assign`)
  - คัดลอกใบจากกลุ่ม ADMIN เก็บ Lead ไปแท็กในห้องจ่ายเบอร์ → ระบบจับคู่ใบนั้นให้เอง (ลงชีต)
  + **บอทเตือนในห้องจ่ายเบอร์** (`warn_slip` · สวิตช์ `warn`) เมื่อแอดมินโพสต์ใบที่
    (ก) ใช้เลขที่จองไว้ให้ลูกค้าอีกราย (ข) ออกเลขใหม่ให้ลูกค้าที่จองเลขไว้แล้ว (ค) ออกเลขใหม่ให้ลูกค้าที่เพิ่งได้เลขไป

★ ระบบ **ไม่จ่ายเซลล์เอง** — จ่ายอัตโนมัติ (autochat / จ่ายวนใบร่าง) เป็นสวิตช์แยก ปิดอยู่
★ กลุ่ม ADMIN เก็บ Lead ไม่ใช่ห้องจ่ายเบอร์ → ใบในกลุ่มนี้ **ไม่ลงชีต** (ลงตอนมีใบ+แท็กในห้องจ่ายเบอร์)
★ ใบที่ระบบส่ง (message_id ขึ้นต้น `auto-lead-`) ไม่โผล่เป็นใบร่างซ้ำในห้องพัก (`leadpark._scan`) และไม่ใช้จับคู่ (`leadmatch.index`)
★ ข้อความกลุ่มทำ **อย่างมากครั้งเดียว** (ขยับตัวชี้ก่อนทำ) — ระบบล่มกลางทาง = ใบร่างนั้นไม่ได้เลข ดีกว่าบอทตอบซ้ำในกลุ่ม
  (ใบร่างที่ไม่ได้เลขยังจ่ายเบอร์จากห้องพัก Lead ได้ตามเดิม — เลขออกตอนกด)
"""
from __future__ import annotations

import re
import time
import uuid
from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime

KEY = "_autolead"            # .auto[KEY] = {code, num, month, base, admin, at, ok, error, mid, room, tries, src} หรือ {skip, at}
CFG_KEY = "autolead_config"  # KV {enabled, since, after_min, drafts, warn}
PTR_KEY = "autolead_ptr"     # KV {last_id} — ข้อความกลุ่มล่าสุดที่อ่านแล้ว (GroupChat.id)
LAST_GROUP_KEY = "autolead_groups_last"
MSG_PREFIX = "auto-lead-"    # GroupChat.message_id ของใบที่ระบบส่ง (แชท = auto-lead-<ChatLead.pk>-<เลข> · ใบร่าง = auto-lead-x<ExtLead.pk>-<เลข>)
WEB_PREFIX = "web-park-"     # GroupChat.message_id ของใบร่างที่เพิ่มจากฟอร์มในเว็บ
WHAT = "เก็บลีดอัตโนมัติ (กลุ่ม ADMIN เก็บ Lead)"
WHAT_WARN = "เตือนเลขลีด (ห้องจ่ายเบอร์)"
AFTER_MIN = 2
MAX_PER_RUN = 10
RETRY_MIN = 5
MAX_TRIES = 5
DRAFT_MAX_AGE_MIN = 180      # ใบร่าง/ใบเก่ากว่านี้ (ระบบตามหลังนานๆ หลังล่ม) ไม่ตอบ — แอดมินคงจัดการไปแล้ว
HOLD_DAYS = 7                # ลูกค้าที่ระบบจองเลขไว้แล้ว — มองย้อนกี่วัน (เท่าห้องพัก Lead)
SLIP_DUP_DAYS = 2            # ใบร่างใหม่ของลูกค้าที่เพิ่งได้เลขในห้องจ่ายเบอร์ภายในกี่วัน = ซ่อน + บอกเลขเดิม
RENUM_HOURS = 24             # ห้องจ่ายเบอร์: ลูกค้าเดิมได้เลขอื่นไปภายในกี่ชั่วโมง = เตือน "ใช้เลขเดิม"
DUP_REPLY_MIN = 30           # แอดมินโพสต์ใบร่างเดิมซ้ำ — บอกเลขเดิมไม่ถี่กว่านี้ (กันบอทพูดซ้ำในกลุ่ม)
GROUP_BATCH = 100
BG = True                    # เทสต์ปิด (ทำในที่ ไม่แตก thread)
_LOCK_KEY = 7_406_068        # Postgres advisory lock — อ่านข้อความกลุ่มทีละ worker (เลขไม่ชนของ leadflow/leadsheet/autochat)
_RUN = {"at": 0.0}


# ── ค่าตั้ง ─────────────────────────────────────────────────────────────

def _kv(key) -> dict:
    try:
        from dashboard.services import cache_store
        return (cache_store.get_kv(key) or {}).get("data") or {}
    except Exception:
        return {}


def _set_kv(key, val):
    try:
        from dashboard.services import cache_store
        cache_store.set_kv(key, val)
    except Exception:
        pass


def cfg() -> dict:
    d = _kv(CFG_KEY)
    try:
        after = max(0, min(60, int(d.get("after_min", AFTER_MIN))))
    except (TypeError, ValueError):
        after = AFTER_MIN
    return {"enabled": bool(d.get("enabled", True)), "since": str(d.get("since") or ""), "after_min": after,
            "drafts": bool(d.get("drafts", True)), "warn": bool(d.get("warn", True))}


def save_cfg(c: dict) -> bool:
    try:
        from dashboard.services import cache_store
        cache_store.set_kv(CFG_KEY, {"enabled": bool(c.get("enabled")), "since": c.get("since") or "",
                                     "after_min": int(c.get("after_min", AFTER_MIN)),
                                     "drafts": bool(c.get("drafts", True)), "warn": bool(c.get("warn", True))})
        return True
    except Exception:
        return False


def set_enabled(on: bool) -> dict:
    """เปิด = เริ่มนับจากตอนนี้ (ลูกค้าที่ให้เบอร์ก่อนหน้านี้ไม่ส่งย้อนหลัง — แอดมินเก็บไปแล้ว)"""
    c = cfg()
    if on and not c["enabled"]:
        c["since"] = timezone.now().isoformat(timespec="seconds")
    c["enabled"] = bool(on)
    save_cfg(c)
    return c


def set_switch(name: str, on: bool) -> dict:
    """สวิตช์ย่อย `drafts` (บอทรันเลขใบร่างในกลุ่ม) / `warn` (เตือนในห้องจ่ายเบอร์)"""
    c = cfg()
    if name in ("drafts", "warn"):
        c[name] = bool(on)
        save_cfg(c)
    return c


def _dt(s):
    dt = parse_datetime(s) if s else None
    if dt and timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt


# ── เลขที่จองไว้ ───────────────────────────────────────────────────────

def reserved(obj) -> dict:
    """เลขที่ระบบจองไว้ให้ลีดนี้ (ChatLead / ExtLead) → {code, num, month, base, admin, …} หรือ {}"""
    r = ((getattr(obj, "auto", None) or {}).get(KEY)) or {}
    return r if r.get("num") else {}


def reserved_nums(limit: int = 300) -> list:
    """เลขรันที่จองไว้ล่าสุด (แชท + ใบร่าง/ฟอร์มเว็บ) — `connect.last_running` นับรวม (ใบในกลุ่ม ADMIN เก็บ Lead ไม่อยู่ในห้องจ่ายเบอร์)"""
    from .models import ChatLead, ExtLead
    out = []
    for M in (ChatLead, ExtLead):
        for a in (M.objects.filter(auto__has_key=KEY).order_by("-updated_at")
                  .values_list("auto", flat=True)[:limit]):
            try:
                n = int(((a or {}).get(KEY) or {}).get("num") or 0)
            except (TypeError, ValueError):
                n = 0
            if n:
                out.append(n)
    return out


def lead_keys(lead) -> set:
    """ตัวตนของลูกค้าแชท (เบอร์ + ID LINE) — ชุดเดียวกับ `leadpark.keys` ของใบร่าง/ใบจ่ายลีด"""
    from .connect import phones_in
    from .leadpark import keys
    s, _ = keys({"phones": phones_in([lead.phone]) if (lead.phone or "").strip() else [],
                 "line_id": lead.line_id or "", "account": "", "channel": ""})
    return s


def ext_keys(e) -> tuple:
    from .connect import phones_in
    from .leadpark import keys
    return keys({"phones": phones_in([v for v in (e.phone, e.line_id) if v]), "line_id": e.line_id or "",
                 "account": e.account or "", "channel": e.channel or ""})


def _match(strong: set, weak: str, s2: set, w2: str) -> bool:
    """ลูกค้าคนเดียวกันไหม — กติกาเดียวกับ `leadpark._same` (คีย์อ่อนใช้เฉพาะตอนไม่มีคีย์แข็งทั้งคู่)"""
    if strong and s2:
        return bool(strong & s2)
    if not strong and not s2:
        return bool(weak) and weak == w2
    return False


def _who(phones=(), line_id: str = "", account: str = "") -> str:
    """อ้างถึงลูกค้าในข้อความเตือน — เท่าที่ใบในกลุ่มมีอยู่แล้ว (เบอร์ลงท้าย / ID LINE / ชื่อ Account)"""
    from .leadpark import clean_line_id
    if phones:
        return "เบอร์ลงท้าย %s" % str(list(phones)[0])[-4:]
    lid = clean_line_id(line_id)
    if lid:
        return "ID LINE %s" % lid[:40]
    return ("ชื่อ Account %s" % account[:40]) if account else "ลูกค้ารายนี้"


def holder(strong: set, weak: str = "", days: int = HOLD_DAYS, skip_ext=(), skip_lead=None) -> dict | None:
    """ลูกค้าคนนี้มีเลขที่ระบบจองไว้แล้ว (แชท/ใบร่าง/ฟอร์มเว็บ) → ล่าสุด 1 ราย หรือ None

    `{kind: chat|ext, code (เลขจริงถ้าจ่ายแล้ว), reserved, num, at, used (จ่ายเซลล์แล้ว), seller, who}`"""
    from .models import ChatLead, ExtLead
    if not strong and not weak:
        return None
    since = timezone.now() - timedelta(days=days)
    hits = []
    for e in (ExtLead.objects.filter(auto__has_key=KEY, updated_at__gte=since)
              .exclude(message_id__in=list(skip_ext or ())).order_by("-updated_at")[:500]):
        rv = reserved(e)
        if not rv:
            continue
        s2, w2 = ext_keys(e)
        if _match(strong, weak, s2, w2):
            hits.append({"kind": "ext", "id": e.message_id, "code": e.code or rv["code"], "reserved": rv["code"],
                         "num": int(rv["num"]), "at": rv.get("at") or "", "used": bool(e.code),
                         "seller": e.seller_name or "", "who": e.account or e.customer_name or ""})
    if strong:
        for ld in (ChatLead.objects.filter(auto__has_key=KEY, updated_at__gte=since).exclude(pk=skip_lead)
                   .select_related("chat").order_by("-updated_at")[:500]):
            rv = reserved(ld)
            if rv and strong & lead_keys(ld):
                hits.append({"kind": "chat", "id": ld.chat_id, "code": ld.code or rv["code"], "reserved": rv["code"],
                             "num": int(rv["num"]), "at": rv.get("at") or "", "used": bool((ld.code or "").strip()),
                             "seller": "", "who": ld.customer_name or ld.account or ""})
    hits.sort(key=lambda h: h["at"], reverse=True)
    return hits[0] if hits else None


def holder_of_num(num: int, days: int = HOLD_DAYS * 2) -> dict | None:
    """เลขรันนี้ระบบจองไว้ให้ใคร → `{kind, code, strong, used, who}` หรือ None"""
    from .models import ChatLead, ExtLead
    since = timezone.now() - timedelta(days=days)
    for e in ExtLead.objects.filter(auto__has_key=KEY, updated_at__gte=since).order_by("-updated_at")[:500]:
        rv = reserved(e)
        if rv and int(rv["num"]) == int(num):
            s2, _ = ext_keys(e)
            return {"kind": "ext", "code": rv["code"], "strong": s2, "used": bool(e.code),
                    "who": _who(ext_phones(e), e.line_id, e.account)}
    for ld in ChatLead.objects.filter(auto__has_key=KEY, updated_at__gte=since).order_by("-updated_at")[:500]:
        rv = reserved(ld)
        if rv and int(rv["num"]) == int(num):
            from .connect import phones_in
            return {"kind": "chat", "code": rv["code"], "strong": lead_keys(ld), "used": bool((ld.code or "").strip()),
                    "who": _who(phones_in([ld.phone]) if ld.phone else (), ld.line_id, ld.account)}
    return None


def ext_phones(e) -> list:
    from .connect import phones_in
    return phones_in([v for v in (e.phone, e.line_id) if v])


def room_use(num: int, since=None, strong=None) -> dict:
    """เลขรันนี้มีใบในห้องจ่ายเบอร์แล้วไหม → `{code, same, at, tag}` หรือ {}
    `same` = ใบของลูกค้าคนเดียวกัน (เบอร์/ID LINE ตรง — แอดมินคัดลอกใบไปแท็กเองแล้ว) · ไม่นับ R (ไม้ 2 ใช้เลขเดิมของเคสเก่า)"""
    from .connect import _ANY_CODE, _lead_group_ids
    from .leadgroup import _LEAD_NO, parse_leadsheet
    from .leadpark import _phones, keys
    from .models import GroupChat
    gids = _lead_group_ids()
    if not gids or not num:
        return {}
    qs = GroupChat.objects.filter(chat_type=GroupChat.GROUP, group_id__in=gids, text__icontains="lead no",
                                  text__contains=str(num))
    if since:
        qs = qs.filter(sent_at__gte=since - timedelta(days=1))
    first = {}
    for t, at in qs.order_by("-sent_at").values_list("text", "sent_at")[:50]:
        m = _LEAD_NO.search(t or "")
        raw = re.sub(r"[ \t]", "", m.group(1)) if m else ""
        mm = _ANY_CODE.match(raw)
        if not (mm and int(mm.group(3)) == int(num) and not mm.group(1).upper().startswith("R")):
            continue
        f = parse_leadsheet(t or "") or {}
        s2, _ = keys({"phones": _phones(f.get("phone"), f.get("line_id")), "line_id": f.get("line_id") or "",
                      "account": "", "channel": ""})
        hit = {"code": raw.upper(), "same": bool(strong and s2 and (set(strong) & s2)), "at": at,
               "tag": f.get("assigned") or ""}
        if hit["same"]:
            return hit
        first = first or hit
    return first


def num_used_in_rooms(num: int, since=None) -> str:
    """เลขรันนี้ถูกใช้ในห้องจ่ายเบอร์แล้ว → เลขเต็มที่เจอ หรือ \"\" (ไม่สนว่าลูกค้าคนไหน — ดู `room_use`)"""
    return room_use(num, since).get("code", "")


def code_for_assign(obj, prefix: str, strong: set, taken) -> tuple:
    """ปุ่มจ่ายเซลล์ของลีดที่ระบบจองเลขไว้ → `(เลขที่จะใช้, ข้อความต่อท้าย, เหตุผลที่ห้ามจ่าย)`

    - เลขที่จองไว้ยังว่าง → ใช้เลขนั้น (ตัวหน้าตามที่แอดมินเลือก)
    - มีใบในห้องจ่ายเบอร์ด้วยเลขนี้ **ของลูกค้าคนเดียวกัน** แล้ว (แอดมินคัดลอกใบไปแท็กเอง) → ห้ามจ่ายซ้ำ
    - เลขนี้ถูกใช้กับลูกค้าคนอื่น (แอดมินออกเลขมือชน) → ออกเลขใหม่ + บอก
    ไม่มีเลขที่จองไว้ = `("", "", "")` (ผู้เรียกออกเลขถัดไปตามเดิม)"""
    rv = reserved(obj)
    if not rv:
        return "", "", ""
    cand = "%s%s-%s" % (prefix, rv.get("month") or timezone.localdate().month, rv["num"])
    use = room_use(rv["num"], since=_dt(rv.get("at") or ""), strong=strong)
    if use.get("same"):
        return "", "", "ลีดนี้ได้เลข %s ในห้องจ่ายเบอร์แล้ว%s — ไม่ต้องจ่ายซ้ำ" % (
            use["code"], (" (@%s)" % use["tag"]) if use.get("tag") else "")
    if use or taken(cand):
        return "", " · เลขที่จองไว้ %s ถูกใช้ไปแล้ว (%s) — ออกเลขใหม่" % (rv.get("code"), use.get("code") or "ในระบบ"), ""
    return cand, "", ""


# ── ส่งข้อความลงกลุ่ม ───────────────────────────────────────────────────

def _push_key() -> str:
    from dashboard.services.line_channels import key_of_token, push_token
    return key_of_token(push_token()) or ""


def _quote(g) -> str:
    """quoteToken ของข้อความในกลุ่ม — ใช้ได้เฉพาะข้อความที่บอทตัวส่งได้ยินเอง (token ออกต่อบัญชี)"""
    q = str((g.extra or {}).get("quote") or "") if g is not None else ""
    return q if q and (g.channel or "") == _push_key() else ""


def _push(gid: str, text: str, quote: str = "", what: str = WHAT) -> tuple:
    """push ข้อความเดียวเข้ากลุ่มด้วยบอทตัวส่ง → (ok, error, line message id)
    อ้างข้อความเดิมไม่ได้ (quoteToken หมดอายุ/ผิดบัญชี) = ส่งซ้ำแบบไม่อ้าง — ข้อความต้องถึงกลุ่มก่อน"""
    from dashboard.services.line_channels import push_token
    from dashboard.services.line_notify import push_line_message
    from .slippost import _sent_id, explain
    token = push_token()
    if not token:
        return False, "ยังไม่ได้ตั้ง LINE token ของบอทตัวส่ง", ""
    try:
        msg = {"type": "text", "text": text[:4800]}
        if quote:
            sc, resp = push_line_message(gid, [dict(msg, quoteToken=quote)], token, what=what)
            if sc == 400:
                sc, resp = push_line_message(gid, [msg], token, what=what)
        else:
            sc, resp = push_line_message(gid, [msg], token, what=what)
        ok = sc == 200
        return ok, ("" if ok else explain(sc, resp)), (_sent_id(resp) if ok else "")
    except Exception as e:
        return False, "ต่อ LINE ไม่ได้: %s" % str(e)[:120], ""


def _send(text: str, res: dict, mid: str, extra: dict, quote: str = "") -> dict:
    """ส่งใบเลขเต็มลงกลุ่ม ADMIN เก็บ Lead + เก็บลงคลังแชทกลุ่ม → อัปเดตผลใน res (ok/error/mid/room/tries)"""
    from dashboard.services import eventlog
    from .models import GroupChat
    from .weblead import park_room

    res = dict(res)
    res["tries"] = int(res.get("tries") or 0) + 1
    res["tried"] = timezone.now().isoformat(timespec="seconds")
    room = park_room()
    if not room["id"]:
        res.update(ok=False, error="ไม่พบกลุ่ม ADMIN เก็บ Lead ที่บอทตัวส่งอยู่")
        eventlog.log("line_send", name=WHAT, ok=False, error=res["error"])
        return res
    ok, err, line_mid = _push(room["id"], text, quote)
    res.update(ok=ok, error=err, room=room.get("name") or "")
    if ok:
        mid = mid[:64]
        if not GroupChat.objects.filter(message_id=mid).exists():
            GroupChat.objects.create(
                chat_type=GroupChat.GROUP, group_id=room["id"], group_name=(room.get("name") or "")[:120],
                message_id=mid, sender_id="", sender_name="ระบบเก็บลีด", msg_type="text", text=text,
                extra=dict(extra or {}, source="autolead", line_mid=line_mid),
                channel=_push_key()[:24], direction=GroupChat.OUT,
                sent_by_name="ระบบเก็บลีด", sent_at=timezone.now())
        res["mid"] = mid
    return res


def _say(gid: str, text: str, quote: str = "", what: str = WHAT) -> dict:
    """ข้อความสั้น (บอกเลขเดิม/เตือน) — ไม่เก็บลงคลังแชท (ไม่มีใบให้ระบบอ่าน)"""
    if not gid:
        return {"ok": False, "error": "ไม่พบกลุ่มที่บอทตัวส่งอยู่"}
    ok, err, _ = _push(gid, text, quote, what=what)
    if not ok:
        try:
            from dashboard.services import eventlog
            eventlog.log("line_send", name=what, ok=False, error=err)
        except Exception:
            pass
    return {"ok": ok, "error": err}


def _gid_for_push(g) -> str:
    """group id ฝั่งบอทตัวส่งของกลุ่มที่ข้อความนี้อยู่ (group id ออกต่อ provider · ได้ยินจากบอทอื่น = หาจากชื่อกลุ่ม)"""
    from dashboard.services.line_channels import group_visible_to_push
    from .slippost import _kv_groups
    if (g.channel or "") == _push_key():
        return g.group_id
    groups = _kv_groups()
    if g.group_id in groups and group_visible_to_push(groups.get(g.group_id) or {}):
        return g.group_id
    name = (g.group_name or "").strip()
    for gid, x in groups.items():
        if name and ((x or {}).get("name") or "").strip() == name and group_visible_to_push(x or {}):
            return gid
    return ""


# ── 1. แชท LINE/FB ─────────────────────────────────────────────────────

def _contact_at(lead):
    from .connect import CONTACT_AT_KEY
    return _dt((lead.auto or {}).get(CONTACT_AT_KEY) or "")


def candidates(c=None, now=None, limit: int = 200) -> list:
    """แชทในห้องพัก (คุยในระบบแล้ว · ยังไม่มีเลข · มีเบอร์/ID LINE · ลีดขาย) ที่ยังไม่เคยส่ง
    + ให้ช่องทางติดต่อหลังเปิดสวิตช์ + เกิน after_min นาทีแล้ว"""
    from . import connect as C
    from .models import ChatOwner
    c = c or cfg()
    now = now or timezone.now()
    since = parse_datetime(c["since"]) if c.get("since") else None
    qs = (ChatOwner.objects.select_related("profile", "fb_profile", "owner", "lead")
          .filter(C._engaged_q()).filter(C._no_code_q()).filter(C._contact_q()).filter(C._sell_q())
          .exclude(lead__auto__has_key=KEY).order_by("-last_in_at")[:limit])
    out = []
    for o in qs:
        lead = o.lead
        at = _contact_at(lead)
        if not at or (since and at < since) or now - at < timedelta(minutes=c["after_min"]):
            continue
        if C.is_sim_row(o) or getattr(C.cust(o), "is_employee", False):
            continue
        out.append(o)
    return out


def _already_posted(o, lead) -> str:
    """แอดมินโพสต์ใบร่าง/ใบจ่ายลีดของลูกค้าคนนี้เองแล้ว หรือระบบจองเลขให้ทางอื่นแล้ว → เหตุผล (ไม่ส่งซ้ำ) หรือ \"\""""
    from . import connect as C
    from . import leadmatch as LM
    if (lead.auto or {}).get(C.MAYBE_KEY):
        return "ชื่อตรงกับใบจ่ายลีด %s (อาจจ่ายแล้ว)" % ((lead.auto or {}).get(C.MAYBE_KEY) or {}).get("code", "")
    ref = _contact_at(lead) or o.last_in_at or timezone.now()
    hits = LM.find(phones=C.phones_in([lead.phone]) if lead.phone else (), lid=LM.lid_core(lead.line_id),
                   names=LM.chat_names(o, lead), fb=C.is_fb(o), since=ref - timedelta(days=2))
    if hits:
        doc, how, strong = hits[0]
        return "แอดมิน%sแล้ว (ตรงด้วย%s)" % ("โพสต์ใบจ่ายลีด " + doc["code"] if doc["kind"] == "slip" else "พักใบร่าง",
                                         "+".join(how))
    h = holder(lead_keys(lead), "", skip_lead=lead.pk)
    if h:
        return "ลูกค้ารายนี้มีเลข %s แล้ว (%s)" % (h["code"], "ใบร่าง/ฟอร์มเว็บ" if h["kind"] == "ext" else "แชทอื่น")
    return ""


def _fields(o, lead, code: str) -> dict:
    from . import connect as C
    f = C.slip_fields(o, lead)
    f["code"] = code
    if not f.get("channel"):
        f["channel"] = "Facebook" if C.is_fb(o) else "LINE@"
    if not f.get("account"):
        f["account"] = getattr(C.cust(o), "display_name", "") or ""
    return f


def _post(o, lead, res: dict) -> dict:
    from .slippost import body
    return _send(body(_fields(o, lead, res["code"])), res, "%s%s-%s" % (MSG_PREFIX, lead.pk, res["num"]),
                 {"chat": o.id})


def _save(obj, res: dict):
    """เก็บผลการจองลง .auto[KEY] ของ ChatLead / ExtLead (อ่านค่าล่าสุดจากฐานข้อมูลก่อน — ช่องอื่นใน auto ไม่หาย)"""
    M = type(obj)
    auto = dict(M.objects.filter(pk=obj.pk).values_list("auto", flat=True).first() or {})
    auto[KEY] = res
    M.objects.filter(pk=obj.pk).update(auto=auto, updated_at=timezone.now())
    obj.auto = auto


def _reserve(obj, prefix: str, extra: dict) -> dict | None:
    """จองเลขถัดไปให้ ChatLead/ExtLead ในล็อกเดียวกับปุ่มจ่ายเบอร์ → res หรือ None (มีเลข/จองไปแล้วระหว่างนี้)"""
    from . import connect as C
    M = type(obj)
    month = timezone.localdate().month
    with C.code_lock():
        cur = M.objects.get(pk=obj.pk)
        if (cur.code or "").strip() or reserved(cur):
            return None
        num = C.last_running() + 1
        code = "%s%d-%d" % (prefix, month, num)
        kw = {"chat_lead_pk": cur.pk} if M.__name__ == "ChatLead" else {"ext_pk": cur.pk}
        while C.code_taken(code, **kw):
            num += 1
            code = "%s%d-%d" % (prefix, month, num)
        res = dict(extra, code=code, num=num, month=month, at=timezone.now().isoformat(timespec="seconds"),
                   ok=False, sending=True)
        _save(cur, res)
    obj.auto = cur.auto
    return {k: v for k, v in res.items() if k != "sending"}


def _forget():
    try:
        from . import leadmatch, leadpark
        leadpark.forget()
        leadmatch.forget()
    except Exception:
        pass


def collect_one(o, dry: bool = False) -> dict:
    """แชทเดียว → จองเลข + ส่งใบ · คืน {d: posted|failed|skip|would, why, code?}"""
    from . import connect as C
    lead = C.autofill(o)
    if (lead.code or "").strip():
        return {"d": "skip", "why": "มีเลขลีดแล้ว (%s)" % lead.code}
    auto = lead.auto or {}
    if C.BUY_KEY in auto or C.BUYLEAD_KEY in auto or C.NOCODE_KEY in auto:
        return {"d": "skip", "why": "ไม่ใช่ลีดขาย"}
    why = _already_posted(o, lead)
    if why:
        if not dry:
            _save(lead, {"skip": why, "at": timezone.now().isoformat(timespec="seconds")})
        return {"d": "skip", "why": why}
    sg = C.suggest_prefix(lead, o=o)
    prefix = C.build_prefix(sg["base"], bool(sg.get("admin")), False)
    if dry:
        return {"d": "would", "why": sg.get("why") or "", "code": C.next_code(prefix)}
    res = _reserve(lead, prefix, {"base": sg["base"], "admin": bool(sg.get("admin")),
                                  "why": (sg.get("why") or "")[:120], "src": "chat"})
    if not res:
        return {"d": "skip", "why": "มีคนจัดการไปแล้วระหว่างนี้"}
    res = _post(o, lead, res)                     # ยิงเน็ตนอกล็อก
    _save(lead, res)
    _forget()
    return {"d": "posted" if res.get("ok") else "failed", "why": res.get("error") or "", "code": res["code"]}


# ── 2. ใบร่างในกลุ่ม ADMIN เก็บ Lead (+ ฟอร์มเว็บ) ─────────────────────

def _draft_base(d: dict) -> str:
    """ตัวหน้าของใบร่าง — ตามที่แอดมินเขียน · เขียนมาไม่ใช่ตัวหน้าที่รู้จัก = ตามช่องทาง (TikTok → TLD) ไม่งั้น NLD"""
    from .connect import CODE_BASES
    b = (d.get("base") or "").upper()
    if b in {k for k, _ in CODE_BASES}:
        return b
    ch = (d.get("channel") or "").lower().replace(" ", "")
    if "tiktokads" in ch:
        return "TALD"
    if "tiktok" in ch or "ติ๊กต็อก" in ch:
        return "TLD"
    return "NLD"


def _hide(g, d, why: str):
    """ซ่อนใบร่างที่ซ้ำกับลีดที่มีเลขแล้ว (ห้องพัก Lead → "ซ่อนไว้" · แอดมินเอากลับมาจ่ายได้)"""
    from .leadpark import _ext_for
    e = _ext_for(g, d)
    if not e.code:
        e.no_code, e.no_code_by = True, ("ระบบ: %s" % why)[:80]
        e.save(update_fields=["no_code", "no_code_by", "updated_at"])
    return e


def _hm(at) -> str:
    dt = _dt(at) if isinstance(at, str) else at
    return timezone.localtime(dt).strftime("%d/%m %H:%M") if dt else ""


def recent_slip(phones=(), line_id: str = "", since=None, before=None, exclude_pk=None) -> dict | None:
    """ใบในห้องจ่ายเบอร์ของลูกค้าคนนี้ (เบอร์/ID LINE ตรง · ไม่นับ R/ไม้ 2) ล่าสุด → `{code, num, at, tag, pk}`"""
    from .connect import _ANY_CODE, _lead_group_ids
    from .leadgroup import parse_leadsheet
    from .leadpark import _phones, keys
    from .models import GroupChat
    strong, _ = keys({"phones": list(phones or ()), "line_id": line_id or "", "account": "", "channel": ""})
    gids = _lead_group_ids()
    if not strong or not gids:
        return None
    qs = GroupChat.objects.filter(chat_type=GroupChat.GROUP, group_id__in=gids, text__icontains="lead no")
    if since:
        qs = qs.filter(sent_at__gte=since)
    if before:
        qs = qs.filter(sent_at__lte=before)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    for pk, t, at in qs.order_by("-sent_at").values_list("pk", "text", "sent_at")[:400]:
        f = parse_leadsheet(t or "")
        if not f:
            continue
        code = (f.get("lead_code") or "").upper()
        mm = _ANY_CODE.match(code)
        if not mm or code.startswith("R") or f.get("lead_slash"):
            continue
        s2, _ = keys({"phones": _phones(f.get("phone"), f.get("line_id")), "line_id": f.get("line_id") or "",
                      "account": "", "channel": ""})
        if strong & s2:
            return {"code": code, "num": int(mm.group(3)), "at": at, "tag": f.get("assigned") or "", "pk": pk}
    return None


def number_draft(g, d: dict, quote: str = "", force: bool = False) -> dict:
    """ใบร่างในกลุ่ม ADMIN เก็บ Lead (แอดมินพักใน LINE / ฟอร์มในเว็บ) → จองเลขรัน + ตอบใบเลขเต็มในกลุ่ม

    คืน `{d: posted|failed|dup|hidden|skip, why, code?}` · `force` = แอดมินยืนยันในเว็บแล้วว่าไม่ซ้ำ (ข้ามการเช็คลูกค้าเดิม)
    ใบเดียวกันโพสต์ซ้ำ = ลีดเดิม (`leadpark._scan` รวมให้) → บอกเลขเดิม ไม่ออกใหม่"""
    from . import connect as C
    from . import leadpark as LP
    from .models import ExtLead
    if d.get("reject"):
        return {"d": "skip", "why": "ใบ R (ไม้ 2 ใช้เลขเดิม + /1) — ระบบไม่ออกเลขใหม่"}
    now = timezone.now()
    _room, raw = LP._scan(LP.DAYS, now)
    it = next((r for r in raw if g.message_id in r["_mids"]), None)
    if not it:
        return {"d": "skip", "why": "ใบร่างไม่มีเบอร์/ID LINE/ชื่อ Account ให้ระบุตัวลูกค้า"}
    if it["_asgAt"]:
        return {"d": "skip", "why": "ลีดนี้ได้เลข %s ในห้องจ่ายเบอร์แล้ว" % (it.get("code") or "")}
    base_mid = it["id"]
    gid = _gid_for_push(g)
    e0 = ExtLead.objects.filter(message_id=base_mid).first()
    rv0 = reserved(e0) if e0 else {}
    if e0 and e0.code:
        return _dup(e0, rv0, g, quote, gid, "ใบนี้ลูกค้าเดิม — จ่ายเบอร์ %s ให้ @%s ไปแล้วครับ" % (e0.code, e0.seller_name or "-"),
                    e0.code)
    if rv0:
        return _dup(e0, rv0, g, quote, gid, "ใบนี้ลูกค้าเดิม — ระบบจองเลข %s ไว้แล้ว (%s) · ใช้เลขนี้ตอนจ่ายเซลล์ ไม่ต้องออกเลขใหม่ครับ"
                    % (rv0["code"], _hm(rv0.get("at"))), rv0["code"])
    if e0 and e0.no_code:
        if not force:
            return {"d": "skip", "why": "แอดมินซ่อนลีดนี้ไว้ (ไม่ต้องจ่ายเบอร์)"}
        # แอดมินยืนยันในเว็บว่าเป็นลีดใหม่ — ใบร่างเดิมของลูกค้ารายนี้ที่ถูกซ่อนไว้ เอากลับมาแล้วจองเลขให้
        e0.no_code, e0.no_code_by = False, ""
        e0.save(update_fields=["no_code", "no_code_by", "updated_at"])
    # ลีดในห้องพัก = ใบร่างแรกของลูกค้ารายนี้ (ใบที่โพสต์ซ้ำรวมเข้าใบแรก) — จอง/ซ่อน ที่ใบแรกเสมอ
    g0, d0 = (g, d) if base_mid == g.message_id else LP._draft_msg(base_mid)
    if not g0:
        g0, d0 = g, d
    strong, weak = LP.keys(d)
    if not force:
        h = holder(strong, weak, skip_ext={base_mid})
        if h:
            src = "ใบร่าง/ฟอร์มเว็บ" if h["kind"] == "ext" else "แชทที่ลูกค้าทักเข้ามา"
            _hide(g0, d0, "ลูกค้าเดิม %s" % h["code"])
            _say(gid, "ลูกค้ารายนี้มีเลข %s แล้ว (%s · %s) — ซ่อนใบร่างนี้ไว้ในห้องพัก Lead ไม่ออกเลขซ้ำครับ"
                 % (h["code"], src, _hm(h["at"])), quote)
            _forget()
            return {"d": "hidden", "why": "ลูกค้าเดิม (%s)" % h["code"], "code": h["code"]}
        rs = recent_slip(d.get("phones") or (), d.get("line_id") or "", since=now - timedelta(days=SLIP_DUP_DAYS))
        if rs:
            _hide(g0, d0, "ได้เลข %s แล้ว" % rs["code"])
            _say(gid, "ลูกค้ารายนี้ได้เลข %s%s ในห้องจ่ายเบอร์ไปแล้วเมื่อ %s — ซ่อนใบร่างนี้ไว้ ถ้าต้องจ่ายใหม่ให้ใช้เลขเดิมครับ"
                 % (rs["code"], (" (@%s)" % rs["tag"]) if rs.get("tag") else "", _hm(rs["at"])), quote)
            _forget()
            return {"d": "hidden", "why": "ได้เลขในห้องจ่ายเบอร์แล้ว (%s)" % rs["code"], "code": rs["code"]}
    e = LP._ext_for(g0, d0)
    base = _draft_base(d0)
    prefix = C.build_prefix(base, bool(d0.get("admin")), False)
    src = "web" if g.message_id.startswith(WEB_PREFIX) else "draft"
    res = _reserve(e, prefix, {"base": base, "admin": bool(d0.get("admin")), "src": src,
                               "why": "ตามใบร่าง" if base == (d0.get("base") or "").upper() else "ตามช่องทาง"})
    if not res:
        return {"d": "skip", "why": "มีคนจัดการไปแล้วระหว่างนี้"}
    res = _post_ext(e, res, quote)
    _save(e, res)
    _forget()
    return {"d": "posted" if res.get("ok") else "failed", "why": res.get("error") or "", "code": res["code"],
            "mid": e.message_id}


def _dup(e, rv, g, quote, gid, text, code) -> dict:
    """โพสต์ใบร่างเดิมซ้ำ → บอกเลขเดิม (ไม่ถี่กว่า DUP_REPLY_MIN นาทีต่อลีด)"""
    last = _dt((rv or {}).get("dup_at") or "")
    if not last or timezone.now() - last >= timedelta(minutes=DUP_REPLY_MIN):
        _say(gid, text, quote)
        if rv:
            _save(e, dict(rv, dup_at=timezone.now().isoformat(timespec="seconds")))
    return {"d": "dup", "why": text, "code": code}


def _post_ext(e, res: dict, quote: str = "") -> dict:
    from .leadpark import slip_fields
    from .slippost import body
    f = slip_fields(e)
    f["code"] = res["code"]
    return _send(body(f), res, "%sx%s-%s" % (MSG_PREFIX, e.pk, res["num"]), {"ext": e.message_id}, quote)


# ── 3. ฟอร์ม "เพิ่มลีดเอง" ในห้องพัก Lead ──────────────────────────────

FORM_FIELDS = (("channel", 80), ("live", 60), ("account", 120), ("name", 120), ("line_id", 80), ("phone", 40),
               ("car", 300), ("ads", 120), ("more", 600))


def _clean(v, n: int) -> str:
    return re.sub(r"\s*\n\s*", " · ", str(v or "").strip())[:n]


def form_help() -> dict:
    """ตัวเลือกของฟอร์มเพิ่มลีด — ช่องทาง/ทีมไลฟ์ ชุดเดียวกับ dropdown ของชีตลีด · ตัวหน้าเลขลีด"""
    from . import connect as C
    from .weblead import park_room
    c = cfg()
    return {"channels": C.dd_options("channel"), "lives": C.dd_options("live_team"),
            "bases": [{"key": b, "type": t} for b, t in C.CODE_BASES], "room": park_room().get("name") or "",
            "drafts": c["drafts"], "warn": c["warn"], "on": c["enabled"]}


def add_manual(data: dict, by: str = "", force: bool = False) -> dict:
    """ฟอร์มในเว็บ → ใบร่างในห้องพัก Lead + จองเลข + ส่งใบเลขเต็มลงกลุ่ม ADMIN เก็บ Lead

    คืน `{ok, code, posted, error, message, mid}` · ลูกค้าเดิม (มีเลขแล้ว) และไม่ได้ยืนยัน = `{ok: False, status: 409, dup}`"""
    from . import connect as C
    from . import leadpark as LP
    from .models import GroupChat
    from .slippost import body
    from .weblead import park_room
    f = {k: _clean((data or {}).get(k), n) for k, n in FORM_FIELDS}
    phones = C.phones_in([f["phone"]]) if f["phone"] else []
    if f["phone"] and not phones:
        return {"ok": False, "status": 400, "error": "เบอร์โทรไม่ถูกต้อง — ใส่เบอร์ 10 หลัก (หรือเว้นว่างแล้วใส่ ID LINE)"}
    if phones:
        f["phone"] = phones[0]
    if not (phones or LP.clean_line_id(f["line_id"]) or len(f["account"]) >= 2):
        return {"ok": False, "status": 400, "error": "ใส่อย่างน้อย 1 อย่าง: เบอร์โทร / ID LINE / ชื่อ Account"}
    base = str((data or {}).get("base") or "").upper()
    if base not in {k for k, _ in C.CODE_BASES}:
        base = _draft_base({"channel": f["channel"]})
    prefix = C.build_prefix(base, bool((data or {}).get("admin")), False)
    text = body(dict(f, code="%s%d-" % (prefix, timezone.localdate().month), line_name=""))
    d = LP.parse_draft(text)
    if not d:
        return {"ok": False, "status": 400, "error": "ประกอบใบร่างไม่ได้"}
    if not force:
        strong, weak = LP.keys(d)
        h = holder(strong, weak)
        rs = None if h else recent_slip(d.get("phones") or (), d.get("line_id") or "",
                                        since=timezone.now() - timedelta(days=SLIP_DUP_DAYS))
        if h or rs:
            code = (h or rs)["code"]
            how = ("ระบบจองไว้ " + _hm(h["at"])) if h else ("ได้เลขในห้องจ่ายเบอร์ " + _hm(rs["at"]))
            return {"ok": False, "status": 409, "dup": {"code": code, "how": how},
                    "error": "ลูกค้ารายนี้มีเลข %s แล้ว (%s) — ใช้เลขเดิม หรือกดยืนยันเพื่อเพิ่มเป็นลีดใหม่" % (code, how)}
    room = park_room()
    name = room.get("name") or ""
    if not any(hh in name.lower() for hh in LP.PARK_HINTS):
        name = "ADMIN เก็บ Lead"                   # ห้องพัก Lead อ่านใบร่างจากชื่อกลุ่ม
    g = GroupChat.objects.create(
        chat_type=GroupChat.GROUP, group_id=room.get("id") or "", group_name=name[:120],
        message_id=(WEB_PREFIX + uuid.uuid4().hex)[:64], sender_id="", sender_name=(by or "แอดมิน")[:80],
        msg_type="text", text=text, extra={"source": "web-form", "by": (by or "")[:80]},
        channel=_push_key()[:24], direction=GroupChat.OUT, sent_by_name=(by or "")[:80], sent_at=timezone.now())
    LP.forget()
    r = number_draft(g, d, force=True)
    code = r.get("code") or ""
    if r["d"] == "posted":
        msg = "เพิ่มลีดแล้ว · เลข %s · ส่งใบลงกลุ่ม %s แล้ว — กดชื่อเซลล์ในห้องพัก Lead เพื่อจ่ายต่อ" % (code, room.get("name") or "ADMIN เก็บ Lead")
    elif r["d"] == "failed":
        msg = "เพิ่มลีดแล้ว · จองเลข %s ไว้แล้ว แต่ส่งใบลงกลุ่มไม่สำเร็จ (%s) — ระบบส่งใหม่เองทุก %d นาที" % (code, r.get("why") or "-", RETRY_MIN)
    elif r["d"] == "dup":
        msg = "ลูกค้ารายนี้มีใบร่างในห้องพักอยู่แล้ว · เลข %s" % code
    else:
        msg = "เพิ่มลีดในห้องพัก Lead แล้ว (ยังไม่ได้เลข: %s)" % (r.get("why") or "-")
    return {"ok": True, "code": code, "posted": r["d"] == "posted", "error": r.get("why") if r["d"] == "failed" else "",
            "message": msg, "mid": g.message_id, "d": r["d"]}


# ── 4. เตือนในห้องจ่ายเบอร์ ────────────────────────────────────────────

def warn_slip(g, f: dict | None = None) -> dict:
    """ใบจ่ายลีดที่แอดมินโพสต์ในห้องจ่ายเบอร์ → เตือนในห้องเดียวกันถ้าเลขผิด · คืน `{d: warned|ok|skip, why}`

    (ก) เลขนี้ระบบจองไว้ให้ลูกค้าอีกราย (เบอร์/ID LINE คนละคน) = เลขชน
    (ข) ลูกค้ารายนี้มีเลขที่จองไว้แล้ว แต่ใบนี้ใช้เลขใหม่ = ชีตจะมี 2 แถว
    (ค) ลูกค้ารายนี้ได้เลขอื่นในห้องจ่ายเบอร์ไปภายใน RENUM_HOURS ชม. = แท็กใหม่/จ่ายใหม่ ควรใช้เลขเดิม
    เตือนเฉพาะที่ชัด (เบอร์/ID LINE ตรงหรือไม่ตรงจริง) · ใบ R / ไม้ 2 (/n) ไม่เตือน"""
    from .connect import _ANY_CODE
    from .leadgroup import parse_leadsheet
    from .leadpark import _phones, keys
    f = f or parse_leadsheet(g.text or "")
    if not f:
        return {"d": "skip"}
    code = (f.get("lead_code") or "").upper()
    mm = _ANY_CODE.match(code)
    if not mm or code.startswith("R") or f.get("lead_slash"):
        return {"d": "skip"}
    num = int(mm.group(3))
    phones = _phones(f.get("phone"), f.get("line_id"))
    strong, _ = keys({"phones": phones, "line_id": f.get("line_id") or "", "account": "", "channel": ""})
    who = _who(phones, f.get("line_id") or "", f.get("account") or "")
    text = ""
    own = holder_of_num(num)
    if own and strong and own["strong"]:
        if strong & own["strong"]:
            return {"d": "ok", "why": "ใช้เลขที่จองไว้ถูกคน"}
        text = ("⚠️ เลข %s ระบบจองไว้ให้ลูกค้าอีกราย (%s) ในกลุ่ม ADMIN เก็บ Lead แล้ว — เลขชนกัน ตรวจใบนี้ก่อนนะครับ"
                % (code, own["who"]))
    if not text and strong:
        h = holder(strong, "")
        if h and h["num"] != num and not h["used"]:
            text = ("⚠️ %s ระบบจองเลข %s ไว้แล้วในกลุ่ม ADMIN เก็บ Lead · ใบนี้ใช้เลขใหม่ %s — ใช้เลขเดิมแทนนะครับ "
                    "ไม่งั้นชีตจะมี 2 แถว" % (who, h["code"], code))
    if not text and strong:
        rs = recent_slip(phones, f.get("line_id") or "", since=g.sent_at - timedelta(hours=RENUM_HOURS),
                         before=g.sent_at, exclude_pk=g.pk)
        if rs and rs["num"] != num:
            text = ("⚠️ %s ได้เลข %s%s ไปเมื่อ %s แล้ว · ใบนี้ออกเลขใหม่ %s — ถ้าจ่ายใหม่/เปลี่ยนเซลล์ ให้ใช้เลขเดิมนะครับ "
                    "(ระบบลงชีตจะแก้ชื่อเซลล์ในแถวเดิมให้)" % (who, rs["code"], (" (@%s)" % rs["tag"]) if rs.get("tag") else "",
                                                             _hm(rs["at"]), code))
    if not text:
        return {"d": "ok"}
    r = _say(_gid_for_push(g), text, _quote(g), what=WHAT_WARN)
    try:
        from dashboard.services import eventlog
        eventlog.log("autolead", name="เตือนเลขลีด", ok=bool(r.get("ok")), code=code, text=text[:300],
                     error=r.get("error") or "")
    except Exception:
        pass
    return {"d": "warned", "why": text, "code": code, "sent": bool(r.get("ok")), "error": r.get("error") or ""}


# ── อ่านข้อความกลุ่ม (webhook + cron เก็บตก) ───────────────────────────

class _Lock:
    def __init__(self):
        self.got = False

    def __enter__(self):
        from django.db import connection
        if connection.vendor != "postgresql":
            self.got = True
            return self
        with connection.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", [_LOCK_KEY])
            self.got = bool(cur.fetchone()[0])
        return self

    def __exit__(self, *a):
        from django.db import connection
        if self.got and connection.vendor == "postgresql":
            try:
                with connection.cursor() as cur:
                    cur.execute("SELECT pg_advisory_unlock(%s)", [_LOCK_KEY])
            except Exception:
                pass
        return False


def process_groups(limit: int = GROUP_BATCH, now=None) -> dict:
    """ข้อความใหม่ในกลุ่ม ADMIN เก็บ Lead (ใบร่าง → จองเลข) + ห้องจ่ายเบอร์ (ใบจ่ายลีด → เตือนเลขผิด)

    ครั้งแรก = เริ่มจากข้อความล่าสุด (ไม่ไล่ย้อนหลัง) · ขยับตัวชี้ "ก่อน" ทำแต่ละข้อความ (ทำอย่างมากครั้งเดียว)"""
    from django.db.models import Max, Q
    from . import connect as C
    from . import leadpark as LP
    from .models import GroupChat
    c = cfg()
    if not c["enabled"] or not (c["drafts"] or c["warn"]):
        return {"off": True}
    now = now or timezone.now()
    out = []
    with _Lock() as lk:
        if not lk.got:
            return {"busy": True}
        st = _kv(PTR_KEY)
        top = GroupChat.objects.aggregate(m=Max("id"))["m"] or 0
        if not isinstance(st.get("last_id"), int):
            _set_kv(PTR_KEY, {"last_id": top, "at": now.isoformat(timespec="seconds")})
            return {"started": top}
        last = st["last_id"]
        if top <= last:
            return {}
        q = LP._rooms(LP.PARK_HINTS)
        gids = C._lead_group_ids()
        if gids:
            q |= Q(group_id__in=gids)
        rows = list(GroupChat.objects.filter(id__gt=last, id__lte=top, chat_type=GroupChat.GROUP,
                                             direction=GroupChat.IN, text__icontains="lead no")
                    .filter(q).order_by("id")[:limit])
        if len(rows) >= limit:
            top = rows[-1].id                    # ที่เหลือทำรอบหน้า
        for g in rows:
            _set_kv(PTR_KEY, {"last_id": g.id, "at": now.isoformat(timespec="seconds")})
            if g.sent_at < now - timedelta(minutes=DRAFT_MAX_AGE_MIN):
                continue
            # บอท 2 ตัวอยู่กลุ่มเดียวกัน = ข้อความเดียวอาจถูกเก็บ 2 แถว (คนละ message id) — ทำครั้งเดียว
            if GroupChat.objects.filter(group_name=g.group_name, text=g.text, sent_at=g.sent_at, pk__lt=g.pk).exists():
                continue
            park = any(h in (g.group_name or "").lower() for h in LP.PARK_HINTS)
            try:
                if park and c["drafts"]:
                    d = LP.parse_draft(g.text or "")
                    if d:
                        r = number_draft(g, d, quote=_quote(g))
                        r["msg"] = g.id
                        out.append(r)
                elif not park and c["warn"] and g.group_id in gids:
                    r = warn_slip(g)
                    if r.get("d") == "warned":
                        r["msg"] = g.id
                        out.append(r)
            except Exception as e:
                out.append({"d": "failed", "why": "พัง: %s" % str(e)[:150], "msg": g.id})
                try:
                    from dashboard.services import eventlog
                    eventlog.log("autolead", name="อ่านข้อความกลุ่ม", ok=False, msg=g.id, error=str(e)[:300])
                except Exception:
                    pass
        _set_kv(PTR_KEY, {"last_id": top, "at": now.isoformat(timespec="seconds")})
    summary = {k: sum(1 for r in out if r["d"] == k) for k in ("posted", "failed", "dup", "hidden", "skip", "warned")}
    if out:
        _set_kv(LAST_GROUP_KEY, dict(summary, at=now.isoformat(timespec="seconds"), rows=out[:30]))
    summary["rows"] = out[:30]
    return summary


def kick(data=None):
    """เรียกจาก `_checkout_ingest` (อยู่ใน thread แล้ว) หลังเก็บแชท — มีใบ ("lead no") ในข้อความที่เข้ามา = ทำเลย"""
    c = cfg()
    if not c["enabled"] or not (c["drafts"] or c["warn"]):
        return None
    if data is not None and "lead no" not in str(data).lower():
        return None
    return process_groups()


# ── รอบ cron ────────────────────────────────────────────────────────────

def _retry_failed(now, out: list):
    """ใบที่จองเลขแล้วแต่ส่งไม่สำเร็จ → ส่งใหม่ (เลขเดิม) ทุก RETRY_MIN นาที ไม่เกิน MAX_TRIES ครั้ง (แชท + ใบร่าง/ฟอร์มเว็บ)"""
    from .models import ChatLead, ExtLead

    def _due(res):
        if not res.get("num") or res.get("ok") or int(res.get("tries") or 0) >= MAX_TRIES:
            return False
        t = _dt(res.get("tried") or res.get("at") or "")
        return not (t and now - t < timedelta(minutes=RETRY_MIN))

    for lead in (ChatLead.objects.filter(auto__has_key=KEY, code="").select_related("chat", "chat__profile",
                                                                                   "chat__fb_profile")
                 .order_by("-updated_at")[:50]):
        res = (lead.auto or {}).get(KEY) or {}
        if not _due(res):
            continue
        res = _post(lead.chat, lead, res)
        _save(lead, res)
        out.append({"chat": lead.chat_id, "d": "posted" if res.get("ok") else "failed", "code": res.get("code"),
                    "why": res.get("error") or "", "retry": True})
    for e in ExtLead.objects.filter(auto__has_key=KEY, code="", no_code=False).order_by("-updated_at")[:50]:
        res = (e.auto or {}).get(KEY) or {}
        if not _due(res):
            continue
        res = _post_ext(e, res)
        _save(e, res)
        out.append({"ext": e.message_id, "d": "posted" if res.get("ok") else "failed", "code": res.get("code"),
                    "why": res.get("error") or "", "retry": True})


def run(now=None, dry: bool = False, limit: int = MAX_PER_RUN) -> dict:
    """รอบเดียว (cron ทุกนาที) → {posted, failed, skipped, rows, groups}"""
    now = now or timezone.now()
    c = cfg()
    if not c["enabled"]:
        return {"off": True}
    grp = {}
    if not dry:
        try:
            grp = process_groups(now=now)
        except Exception as e:
            grp = {"error": str(e)[:150]}
    if not c["since"] and not dry:
        c["since"] = now.isoformat(timespec="seconds")     # ครั้งแรก = เริ่มนับจากตอนนี้ ไม่ส่งย้อนหลัง
        save_cfg(c)
        return {"started": c["since"], "groups": grp}
    rows = []
    for o in candidates(c, now)[:limit]:
        try:
            r = collect_one(o, dry=dry)
        except Exception as e:
            r = {"d": "failed", "why": "พัง: %s" % str(e)[:150]}
        r["chat"] = o.id
        rows.append(r)
    if not dry:
        try:
            _retry_failed(now, rows)
        except Exception as e:
            rows.append({"d": "failed", "why": "ส่งใหม่พัง: %s" % str(e)[:150]})
    out = {k: sum(1 for r in rows if r["d"] == k) for k in ("posted", "failed", "skip", "would")}
    out["rows"] = rows[:30]
    if grp:
        out["groups"] = {k: v for k, v in grp.items() if k != "rows"}
    if rows and not dry:
        _set_kv("autolead_last", dict(out, at=now.isoformat(timespec="seconds")))
    return out


def tick_bg(now=None) -> dict:
    """เรียกจาก `connect.tick` ทุกนาที — ทำใน thread (autofill อ่านแชท · ยิง LINE) ห้ามหน่วง cron_tick"""
    import threading
    if time.time() - _RUN["at"] < 50:
        return {}
    _RUN["at"] = time.time()
    if not cfg()["enabled"]:
        return {}
    if not BG:
        return run(now)
    from . import connect as C
    if not getattr(C, "BG_FILL", True):           # เทสต์ชุดอื่นที่เรียก connect.tick — ไม่แตก thread ชนฐานข้อมูลทดสอบ
        return {}

    def _work():
        try:
            run()
        except Exception:
            pass
        finally:
            try:
                from django.db import connection
                connection.close()
            except Exception:
                pass

    threading.Thread(target=_work, daemon=True).start()
    return {"started": True}
