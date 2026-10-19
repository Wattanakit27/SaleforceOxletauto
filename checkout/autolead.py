# -*- coding: utf-8 -*-
"""**เก็บลีดอัตโนมัติ** — ลูกค้าให้เบอร์/ID LINE ในแชท → ระบบออกเลขรันต่อจากเดิม → ส่งใบลงกลุ่ม "ADMIN เก็บ Lead"
(★ 19 ต.ค.69 · เจ้าของสั่ง *"เก็บ Lead auto ลง Line กลุ่มและลงระบบของเราเพื่อให้แอดมินจ่ายต่อก็พอ · อย่าเพิ่งให้มันจ่าย Lead auto
· อยากให้รันต่อจากเดิมได้เลย code number"* · เลือกกลุ่ม "ADMIN เก็บ Lead")

ทางเดิน
  1. ลูกค้าให้เบอร์/ID LINE (ระบบจับเองอยู่แล้ว `connect.capture_contact`) → แชทอยู่ในห้องพัก Lead ของ Connect
  2. รอ `after_min` นาที (ลูกค้ามักพิมพ์รุ่นรถ/ข้อมูลตามมา) → เติมข้อมูลลีด (`connect.autofill`)
  3. **จองเลขรัน** = เลขล่าสุด + 1 (ล็อกเดียวกับปุ่มจ่ายเบอร์ `code_lock`) · ตัวหน้าตามที่ระบบแนะนำ
     → เก็บที่ `ChatLead.auto["_autolead"]` (**ไม่ใส่ช่อง code** — แชทต้องยังอยู่ในห้องพัก ให้แอดมินกดจ่ายเซลล์)
  4. ส่งใบ (เลขเต็ม · **ไม่แท็กเซลล์**) ลงกลุ่ม ADMIN เก็บ Lead ด้วยบอทตัวส่ง + เก็บลงคลังแชทกลุ่ม
  5. แอดมินกดชื่อเซลล์ในห้องพัก Lead (ปุ่มเดิม) → `assign_lead` **ใช้เลขที่จองไว้** → ใบ + แท็กเซลล์เข้าห้องจ่ายเบอร์ → ลงชีต

★ ระบบ **ไม่จ่ายเซลล์เอง** — จ่ายอัตโนมัติ (autochat / จ่ายวนใบร่าง) เป็นสวิตช์แยก ปิดอยู่
★ กลุ่ม ADMIN เก็บ Lead ไม่ใช่ห้องจ่ายเบอร์ → ใบนี้ **ไม่ลงชีต** (ลงตอนจ่ายเซลล์) · ตัวนับเลขรันรวมเลขที่จองไว้ (`connect.last_running`)
  · ⚠️ แอดมินที่ออกเลขมือในห้องจ่ายเบอร์ต้องดูเลขในกลุ่ม ADMIN เก็บ Lead ด้วย ไม่งั้นเลขชน
    (ตอนจ่ายเซลล์ ระบบเช็คซ้ำ — เลขที่จองไว้ถูกใช้ในห้องจ่ายเบอร์ไปแล้ว = ออกเลขใหม่ให้ พร้อมบอก)
★ ใบที่ระบบส่ง (message_id ขึ้นต้น `auto-lead-`) ไม่โผล่เป็นใบร่างซ้ำในห้องพัก (`leadpark._scan`) และไม่ใช้จับคู่ (`leadmatch.index`)
  — แชทนั้นอยู่ในห้องพักอยู่แล้ว
★ ลูกค้าที่แอดมินโพสต์ใบร่าง/ใบจ่ายลีดเองแล้ว (เบอร์/ID LINE/ชื่อตรง) = ไม่ส่งซ้ำ
"""
from __future__ import annotations

import re
import time
from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime

KEY = "_autolead"            # ChatLead.auto[KEY] = {code, num, month, base, admin, at, ok, error, mid, room, tries} หรือ {skip, at}
CFG_KEY = "autolead_config"  # KV {enabled, since, after_min}
MSG_PREFIX = "auto-lead-"    # GroupChat.message_id ของใบที่ระบบส่ง
WHAT = "เก็บลีดอัตโนมัติ (กลุ่ม ADMIN เก็บ Lead)"
AFTER_MIN = 2
MAX_PER_RUN = 10
RETRY_MIN = 5
MAX_TRIES = 5
BG = True                    # เทสต์ปิด (ทำในที่ ไม่แตก thread)
_RUN = {"at": 0.0}


# ── ค่าตั้ง ─────────────────────────────────────────────────────────────

def cfg() -> dict:
    try:
        from dashboard.services import cache_store
        d = (cache_store.get_kv(CFG_KEY) or {}).get("data") or {}
    except Exception:
        d = {}
    try:
        after = max(0, min(60, int(d.get("after_min", AFTER_MIN))))
    except (TypeError, ValueError):
        after = AFTER_MIN
    return {"enabled": bool(d.get("enabled", True)), "since": str(d.get("since") or ""), "after_min": after}


def save_cfg(c: dict) -> bool:
    try:
        from dashboard.services import cache_store
        cache_store.set_kv(CFG_KEY, {"enabled": bool(c.get("enabled")), "since": c.get("since") or "",
                                     "after_min": int(c.get("after_min", AFTER_MIN))})
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


# ── เลขที่จองไว้ ───────────────────────────────────────────────────────

def reserved(lead) -> dict:
    """เลขที่ระบบจองไว้ให้ลีดนี้ (ยังไม่ได้จ่ายเซลล์) → {code, num, month, base, admin} หรือ {}"""
    r = ((getattr(lead, "auto", None) or {}).get(KEY)) or {}
    return r if r.get("num") else {}


def reserved_nums(limit: int = 300) -> list:
    """เลขรันที่จองไว้ล่าสุด — `connect.last_running` นับรวม (ใบในกลุ่ม ADMIN เก็บ Lead ไม่อยู่ในห้องจ่ายเบอร์)"""
    from .models import ChatLead
    out = []
    for a in (ChatLead.objects.filter(auto__has_key=KEY).order_by("-updated_at")
              .values_list("auto", flat=True)[:limit]):
        try:
            n = int(((a or {}).get(KEY) or {}).get("num") or 0)
        except (TypeError, ValueError):
            n = 0
        if n:
            out.append(n)
    return out


def num_used_in_rooms(num: int, since=None) -> str:
    """เลขรันนี้ถูกใช้ในห้องจ่ายเบอร์แล้ว (แอดมินออกเลขมือชน) → เลขเต็มที่เจอ หรือ ""
    ไม่นับ R (ไม้ 2 ใช้เลขเดิมของเคสเก่า)"""
    from .connect import _ANY_CODE, _lead_group_ids
    from .leadgroup import _LEAD_NO
    from .models import GroupChat
    gids = _lead_group_ids()
    if not gids or not num:
        return ""
    qs = GroupChat.objects.filter(chat_type=GroupChat.GROUP, group_id__in=gids, text__icontains="lead no",
                                  text__contains=str(num))
    if since:
        qs = qs.filter(sent_at__gte=since - timedelta(days=1))
    for t in qs.order_by("-sent_at").values_list("text", flat=True)[:50]:
        m = _LEAD_NO.search(t or "")
        raw = re.sub(r"[ \t]", "", m.group(1)) if m else ""
        mm = _ANY_CODE.match(raw)
        if mm and int(mm.group(3)) == int(num) and not mm.group(1).upper().startswith("R"):
            return raw
    return ""


# ── เลือกแชท ───────────────────────────────────────────────────────────

def _contact_at(lead):
    from .connect import CONTACT_AT_KEY
    s = (lead.auto or {}).get(CONTACT_AT_KEY) or ""
    dt = parse_datetime(s) if s else None
    if dt and timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt


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
    """แอดมินโพสต์ใบร่าง/ใบจ่ายลีดของลูกค้าคนนี้เองแล้ว → เหตุผล (ไม่ส่งซ้ำ) หรือ \"\""""
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
    return ""


# ── ส่ง ────────────────────────────────────────────────────────────────

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
    """ส่งใบลงกลุ่ม ADMIN เก็บ Lead + เก็บลงคลังแชทกลุ่ม → อัปเดตผลใน res (ok/error/mid/room/tries)"""
    from dashboard.services import eventlog
    from dashboard.services.line_channels import key_of_token, push_token
    from dashboard.services.line_notify import push_line_message
    from .models import GroupChat
    from .slippost import _sent_id, body, explain
    from .weblead import park_room

    res = dict(res)
    res["tries"] = int(res.get("tries") or 0) + 1
    res["tried"] = timezone.now().isoformat(timespec="seconds")
    room = park_room()
    if not room["id"]:
        res.update(ok=False, error="ไม่พบกลุ่ม ADMIN เก็บ Lead ที่บอทตัวส่งอยู่")
        eventlog.log("line_send", name=WHAT, ok=False, error=res["error"])
        return res
    text = body(_fields(o, lead, res["code"]))
    token = push_token()
    if not token:
        res.update(ok=False, error="ยังไม่ได้ตั้ง LINE token ของบอทตัวส่ง", room=room.get("name") or "")
        return res
    try:
        sc, resp = push_line_message(room["id"], [{"type": "text", "text": text}], token, what=WHAT)
        ok = sc == 200
        err = "" if ok else explain(sc, resp)
        line_mid = _sent_id(resp) if ok else ""
    except Exception as e:
        ok, err, line_mid = False, "ต่อ LINE ไม่ได้: %s" % str(e)[:120], ""
    res.update(ok=ok, error=err, room=room.get("name") or "")
    if ok:
        mid = ("%s%s-%s" % (MSG_PREFIX, lead.pk, res["num"]))[:64]
        if not GroupChat.objects.filter(message_id=mid).exists():
            GroupChat.objects.create(
                chat_type=GroupChat.GROUP, group_id=room["id"], group_name=(room.get("name") or "")[:120],
                message_id=mid, sender_id="", sender_name="ระบบเก็บลีด", msg_type="text", text=text,
                extra={"source": "autolead", "chat": o.id, "line_mid": line_mid},
                channel=(key_of_token(token) or "")[:24], direction=GroupChat.OUT,
                sent_by_name="ระบบเก็บลีด", sent_at=timezone.now())
        res["mid"] = mid
    return res


def _save(lead, res: dict):
    from .models import ChatLead
    auto = dict(ChatLead.objects.filter(pk=lead.pk).values_list("auto", flat=True).first() or {})
    auto[KEY] = res
    ChatLead.objects.filter(pk=lead.pk).update(auto=auto, updated_at=timezone.now())
    lead.auto = auto


def collect_one(o, dry: bool = False) -> dict:
    """แชทเดียว → จองเลข + ส่งใบ · คืน {d: posted|failed|skip|would, why, code?}"""
    from . import connect as C
    from .models import ChatLead
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
    month = timezone.localdate().month
    with C.code_lock():                           # เลขถัดไป → จอง ในล็อกเดียวกับปุ่มจ่ายเบอร์ (ไม่ชนกัน)
        lead = ChatLead.objects.get(pk=lead.pk)
        if (lead.code or "").strip() or KEY in (lead.auto or {}):
            return {"d": "skip", "why": "มีคนจัดการไปแล้วระหว่างนี้"}
        num = C.last_running() + 1
        code = "%s%d-%d" % (prefix, month, num)
        while C.code_taken(code, chat_lead_pk=lead.pk):
            num += 1
            code = "%s%d-%d" % (prefix, month, num)
        res = {"code": code, "num": num, "month": month, "base": sg["base"], "admin": bool(sg.get("admin")),
               "why": (sg.get("why") or "")[:120], "at": timezone.now().isoformat(timespec="seconds"),
               "ok": False, "sending": True}
        _save(lead, res)
    res = _post(o, lead, {k: v for k, v in res.items() if k != "sending"})   # ยิงเน็ตนอกล็อก
    _save(lead, res)
    try:
        from . import leadmatch, leadpark
        leadpark.forget()
        leadmatch.forget()
    except Exception:
        pass
    return {"d": "posted" if res.get("ok") else "failed", "why": res.get("error") or "", "code": code}


def _retry_failed(now, out: list):
    """ใบที่จองเลขแล้วแต่ส่งไม่สำเร็จ → ส่งใหม่ (เลขเดิม) ทุก RETRY_MIN นาที ไม่เกิน MAX_TRIES ครั้ง"""
    from .models import ChatLead
    for lead in (ChatLead.objects.filter(auto__has_key=KEY, code="").select_related("chat", "chat__profile",
                                                                                   "chat__fb_profile")
                 .order_by("-updated_at")[:50]):
        res = (lead.auto or {}).get(KEY) or {}
        if not res.get("num") or res.get("ok") or int(res.get("tries") or 0) >= MAX_TRIES:
            continue
        t = parse_datetime(res.get("tried") or res.get("at") or "")
        if t and now - t < timedelta(minutes=RETRY_MIN):
            continue
        res = _post(lead.chat, lead, res)
        _save(lead, res)
        out.append({"chat": lead.chat_id, "d": "posted" if res.get("ok") else "failed", "code": res.get("code"),
                    "why": res.get("error") or "", "retry": True})


def run(now=None, dry: bool = False, limit: int = MAX_PER_RUN) -> dict:
    """รอบเดียว (cron ทุกนาที) → {posted, failed, skipped, rows}"""
    now = now or timezone.now()
    c = cfg()
    if not c["enabled"]:
        return {"off": True}
    if not c["since"] and not dry:
        c["since"] = now.isoformat(timespec="seconds")     # ครั้งแรก = เริ่มนับจากตอนนี้ ไม่ส่งย้อนหลัง
        save_cfg(c)
        return {"started": c["since"]}
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
    if rows and not dry:
        try:
            from dashboard.services import cache_store
            cache_store.set_kv("autolead_last", dict(out, at=now.isoformat(timespec="seconds")))
        except Exception:
            pass
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
