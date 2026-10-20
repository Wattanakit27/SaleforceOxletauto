# -*- coding: utf-8 -*-
"""ระบบอัตโนมัติ: แท็กลูกค้าจากคำในแชท — หน้า "ระบบอัตโนมัติ" ใน Oxlet CRM (`/crm/?p=auto`)

★ 20 ต.ค.69 เจ้าของสั่ง *"เพิ่มหน้าหนึ่งขึ้นมาเป็นหน้าของระบบอัตโนมัติ ซึ่งสามารถเพิ่ม ลบ แก้ไขระบบอัตโนมัติที่แท็กได้"*

กฎ 1 ข้อ = **แท็ก 1 คำ** + **คำที่จับ** (คำไหนก็ได้) + **คำยกเว้น** (เจอในข้อความเดียวกัน = ไม่นับข้อความนั้น)
+ ดูข้อความของใคร (ลูกค้า / ลูกค้าและของเรา) + เปิด/ปิด — แอดมินแก้เองในหน้าเว็บ ไม่ต้องแก้โค้ด

  · เก็บที่ KV `autotag_rules` (ไม่ต้อง migrate) · แท็กลงช่อง `ChatLead.tags` ช่องเดียวกับที่คนพิมพ์แท็กในหน้า Connect
  · `ChatLead.auto["_atags"]` = แท็กไหนระบบติดให้ จากกฎไหน คำไหน เมื่อไหร่ (`{แท็ก: {rule, word, at}}`)
  · **คนเอาแท็กออกเอง = ระบบไม่ติดกลับ** (`auto["_tag_no"]`) · คนใส่แท็กเดียวกันไว้เองก่อน = เป็นของคน ระบบไม่ยึด
  · ทำงาน 2 จังหวะ: ข้อความลูกค้าเข้า (`connect.capture_profile` · ติดเพิ่มอย่างเดียว) และ **ทุกครั้งที่แก้กฎ**
    (`rescan_bg` — อ่านแชท `SCAN_DAYS` วันย้อนหลังทั้งหมดใน thread: ติดแท็กใหม่ · เปลี่ยนชื่อแท็กตามกฎ ·
    ลบแท็กของกฎที่ลบ/ปิด · กฎที่แก้คำแล้วไม่ตรงอีก = เอาแท็กออก)
  · จับแบบ "มีคำนี้อยู่ในข้อความ" (ภาษาไทยไม่เว้นวรรค = คำสั้นจับกลางคำอื่นได้) → ปุ่ม **ทดสอบ** ให้เห็นก่อนบันทึก
  · ไม่ใช้ AI · ไม่ส่งอะไรออกนอกระบบ

ระบบจับในตัวที่มีอยู่แล้ว (เบอร์/ไอดีไลน์ · รถ · อาชีพ · รายได้ · อายุงาน · ประวัติผ่อน · สถานะลูกค้า · ลีดรับซื้อ)
อยู่ในโค้ด (`lead_keywords.py` / `connect.py`) — หน้านี้แสดงให้ดูอย่างเดียว (`builtin_stats`)
"""
from __future__ import annotations

import re
import threading
import time
import uuid
from datetime import timedelta

from django.utils import timezone

KV_KEY = "autotag_rules"
LAST_KEY = "autotag_last"          # ผลรอบอ่านแชทย้อนหลังล่าสุด
ATAG_KEY = "_atags"
TAGNO_KEY = "_tag_no"
SCAN_DAYS = 60                     # = อายุแชทลูกค้า (CUSTOMER_CHAT_KEEP_DAYS) — อ่านได้เท่าที่ระบบเก็บไว้
RULE_MAX = 60
WORDS_MAX = 40
WORD_MIN, WORD_LEN, TAG_LEN = 2, 40, 30
TAGS_MAX = 12                      # = เพดานแท็กต่อลูกค้าใน `connect.save_lead_field`
SCOPES = {"in": "ข้อความลูกค้า", "all": "ข้อความลูกค้าและของเรา"}
SAMPLE_MAX = 8

_CACHE = {"at": 0.0, "val": None}
_RUN = {"busy": False}


# ── กฎ ─────────────────────────────────────────────────────────────

def rules(cache: bool = True) -> list:
    """กฎทั้งหมด (เรียงตามที่สร้าง) · จำ 20 วิต่อ process (ถูกเรียกทุกข้อความลูกค้าที่เข้ามา)"""
    if cache and _CACHE["val"] is not None and time.time() - _CACHE["at"] < 20:
        return _CACHE["val"]
    val = []
    try:
        from dashboard.services import cache_store
        raw = cache_store.get_kv(KV_KEY) or {}
        data = raw.get("data") if isinstance(raw, dict) and "data" in raw else raw
        val = [r for r in ((data or {}).get("rules") or []) if isinstance(r, dict) and r.get("id") and r.get("tag")]
    except Exception:
        val = _CACHE["val"] or []
    _CACHE.update(at=time.time(), val=val)
    return val


def active() -> list:
    return [r for r in rules() if r.get("on")]


def _save_rules(rs: list):
    from dashboard.services import cache_store
    cache_store.set_kv(KV_KEY, {"rules": rs})
    _CACHE.update(at=time.time(), val=list(rs))


def _words(v) -> list:
    """ช่องคำ (บรรทัดละคำ หรือคั่นด้วย , ) → ลิสต์ไม่ซ้ำ"""
    if isinstance(v, (list, tuple)):
        parts = [str(x) for x in v]
    else:
        parts = re.split(r"[\n,]+", str(v or ""))
    out, seen = [], set()
    for p in parts:
        w = re.sub(r"\s+", " ", p).strip()
        k = _norm(w)
        if w and k not in seen:
            seen.add(k)
            out.append(w)
    return out


def clean_rule(data: dict, others: list) -> tuple:
    """ข้อมูลจากหน้าเว็บ → (กฎ, "") หรือ (None, ข้อความบอกว่าผิดตรงไหน)"""
    d = data or {}
    tag = re.sub(r"\s+", " ", str(d.get("tag") or "")).strip()
    if not tag:
        return None, "ใส่ชื่อแท็กก่อน"
    if len(tag) > TAG_LEN:
        return None, "ชื่อแท็กยาวเกิน %d ตัวอักษร" % TAG_LEN
    rid = str(d.get("id") or "").strip()
    if any(r["tag"] == tag and r["id"] != rid for r in others):
        return None, "มีกฎที่ติดแท็ก \"%s\" อยู่แล้ว — แก้กฎนั้นแทน" % tag
    words, nots = _words(d.get("words")), _words(d.get("not_words"))
    if not words:
        return None, "ใส่คำที่จะจับอย่างน้อย 1 คำ"
    if len(words) > WORDS_MAX or len(nots) > WORDS_MAX:
        return None, "ใส่คำได้ไม่เกิน %d คำต่อช่อง" % WORDS_MAX
    for w in words + nots:
        if len(_norm(w)) < WORD_MIN:
            return None, "คำ \"%s\" สั้นเกินไป (อย่างน้อย %d ตัวอักษร) — จะไปจับกลางคำอื่นทั้งแชท" % (w, WORD_MIN)
        if len(w) > WORD_LEN:
            return None, "คำ \"%s…\" ยาวเกิน %d ตัวอักษร" % (w[:20], WORD_LEN)
    scope = str(d.get("scope") or "in")
    if scope not in SCOPES:
        return None, "เลือกว่าดูข้อความของใคร"
    return {"id": rid, "tag": tag, "words": words, "not_words": nots, "scope": scope,
            "on": bool(d.get("on", True))}, ""


def save_rule(data: dict, by: str = "") -> tuple:
    """เพิ่ม (ไม่มี id) / แก้ (มี id) → (ok, ข้อความ, กฎ)"""
    rs = [dict(r) for r in rules(cache=False)]
    rule, err = clean_rule(data, rs)
    if err:
        return False, err, None
    now = timezone.now().isoformat(timespec="seconds")
    by = (by or "")[:80]
    if rule["id"]:
        cur = next((r for r in rs if r["id"] == rule["id"]), None)
        if not cur:
            return False, "ไม่พบกฎนี้ (อาจถูกลบไปแล้ว)", None
        cur.update(rule, by=by, at=now)
        rule, msg = cur, "บันทึกกฎ \"%s\" แล้ว" % rule["tag"]
    else:
        if len(rs) >= RULE_MAX:
            return False, "มีกฎครบ %d ข้อแล้ว — ลบกฎที่ไม่ใช้ก่อน" % RULE_MAX, None
        rule.update(id=uuid.uuid4().hex[:10], by=by, at=now, created_by=by, created_at=now)
        rs.append(rule)
        msg = "เพิ่มกฎ \"%s\" แล้ว" % rule["tag"]
    _save_rules(rs)
    rescan_bg(by)
    return True, msg + " — กำลังติดแท็กให้แชทย้อนหลัง %d วัน" % SCAN_DAYS, rule


def delete_rule(rid: str, by: str = "") -> tuple:
    rs = [dict(r) for r in rules(cache=False)]
    cur = next((r for r in rs if r["id"] == str(rid or "")), None)
    if not cur:
        return False, "ไม่พบกฎนี้ (อาจถูกลบไปแล้ว)"
    _save_rules([r for r in rs if r["id"] != cur["id"]])
    rescan_bg(by)
    return True, "ลบกฎ \"%s\" แล้ว — แท็กที่ระบบติดจากกฎนี้จะถูกเอาออก" % cur["tag"]


def toggle(rid: str, on: bool, by: str = "") -> tuple:
    rs = [dict(r) for r in rules(cache=False)]
    cur = next((r for r in rs if r["id"] == str(rid or "")), None)
    if not cur:
        return False, "ไม่พบกฎนี้ (อาจถูกลบไปแล้ว)"
    cur.update(on=bool(on), by=(by or "")[:80], at=timezone.now().isoformat(timespec="seconds"))
    _save_rules(rs)
    rescan_bg(by)
    return True, ("เปิดกฎ \"%s\" แล้ว — กำลังติดแท็กย้อนหลัง" if on else
                  "ปิดกฎ \"%s\" แล้ว — แท็กที่ระบบติดจากกฎนี้จะถูกเอาออก") % cur["tag"]


# ── จับคำ ───────────────────────────────────────────────────────────

def _norm(t) -> str:
    try:
        from .lead_keywords import norm
        t = norm(str(t or ""))
    except Exception:
        t = str(t or "")
    return re.sub(r"\s+", " ", t).strip().lower()


def hit(rule: dict, text: str) -> str:
    """ข้อความนี้เข้ากฎไหม → คำที่จับได้ ("" = ไม่เข้า) · มีคำยกเว้นในข้อความเดียวกัน = ไม่นับ"""
    t = _norm(text)
    if not t:
        return ""
    if any(_norm(w) in t for w in rule.get("not_words") or []):
        return ""
    for w in rule.get("words") or []:
        if _norm(w) in t:
            return w
    return ""


def _texts(rule: dict, msgs) -> list:
    out = []
    for m in msgs or []:
        txt = str(m.get("text") or "")
        if not txt or txt.startswith("["):
            continue
        if rule.get("scope") != "all" and (m.get("dir") or "in") != "in":
            continue
        out.append(txt)
    return out


def tags_for(rs: list, msgs) -> dict:
    """ข้อความ (เก่า→ใหม่ · `{dir, text}`) → `{แท็ก: (id กฎ, คำที่จับได้)}` จากกฎที่เปิดอยู่"""
    out = {}
    for r in rs or []:
        if not r.get("on"):
            continue
        for txt in _texts(r, msgs):
            w = hit(r, txt)
            if w:
                out[r["tag"]] = (r["id"], w)
                break
    return out


def apply_lead(lead, auto: dict, found: dict, rs: list, prune: bool = False) -> bool:
    """ติด/เอาแท็กออกของลูกค้า 1 ราย (แก้ `auto` กับ `lead.tags` ในที่ ไม่ save) → เปลี่ยนอะไรไหม

    แท็กของระบบที่กฎถูกลบ/ปิด = เอาออก · กฎเปลี่ยนชื่อแท็ก = เปลี่ยนตาม · `prune` = อ่านแชทครบแล้ว
    ไม่เจอคำของกฎอีก = เอาออก (ใช้ตอนอ่านย้อนหลัง · ตอนข้อความเข้าติดเพิ่มอย่างเดียว)"""
    by_id = {r["id"]: r for r in rs or []}
    atags = dict(auto.get(ATAG_KEY) or {})
    no = list(auto.get(TAGNO_KEY) or [])
    tags = list(lead.tags or [])
    before = (list(tags), dict(atags))
    for t, rec in list(atags.items()):
        r = by_id.get((rec or {}).get("rule"))
        drop = (not r or not r.get("on") or (prune and r["tag"] not in found))
        if not drop and r["tag"] != t:               # กฎเปลี่ยนชื่อแท็ก
            atags.pop(t)
            if t in tags:
                tags[tags.index(t)] = r["tag"]
            atags[r["tag"]] = rec
            continue
        if drop:
            atags.pop(t)
            if t in tags:
                tags.remove(t)
    now = timezone.now().isoformat(timespec="seconds")
    for t, (rid, w) in (found or {}).items():
        if t in no or (t in tags and t not in atags):   # คนเอาออกเอง / คนใส่ไว้เองแล้ว
            continue
        if t not in tags:
            if len(tags) >= TAGS_MAX:
                continue
            tags.append(t)
        atags[t] = {"rule": rid, "word": w, "at": (atags.get(t) or {}).get("at") or now}
    if (tags, atags) == before:
        return False
    lead.tags = tags
    if atags:
        auto[ATAG_KEY] = atags
    else:
        auto.pop(ATAG_KEY, None)
    return True


def human_edit(lead, auto: dict, new_tags: list):
    """คนแก้แท็กเองในหน้า Connect → แท็กที่ระบบติดแล้วคนเอาออก = จำไว้ไม่ติดกลับ · คนใส่กลับเอง = ล้างที่จำไว้"""
    old = set(lead.tags or [])
    new = set(new_tags or [])
    atags = dict(auto.get(ATAG_KEY) or {})
    no = [t for t in (auto.get(TAGNO_KEY) or []) if t not in new]
    for t in old - new:
        if t in atags:
            atags.pop(t)
            if t not in no:
                no.append(t)
    for t in list(atags):
        if t not in new:
            atags.pop(t)
    if atags:
        auto[ATAG_KEY] = atags
    else:
        auto.pop(ATAG_KEY, None)
    if no:
        auto[TAGNO_KEY] = no[-50:]
    else:
        auto.pop(TAGNO_KEY, None)


# ── อ่านแชทย้อนหลัง (ทดสอบกฎ / ติดแท็กทั้งหมดใหม่หลังแก้กฎ) ──────────────────────

def _corpus(days: int = SCAN_DAYS) -> dict:
    """{ChatOwner.id: [{dir, text}, …] เก่า→ใหม่} ของแชทลูกค้าที่มีข้อความใน `days` วัน (LINE + Facebook · ไม่รวมพนักงาน)"""
    from .models import ChatOwner, FbChat, GroupChat
    since = timezone.now() - timedelta(days=days)
    line, fb = {}, {}
    for uid, d, txt in (GroupChat.objects.filter(sent_at__gte=since).exclude(chat_type=GroupChat.GROUP)
                        .order_by("sent_at", "id").values_list("sender_id", "direction", "text").iterator()):
        if uid and txt:
            line.setdefault(uid, []).append({"dir": d or "in", "text": txt})
    for tid, d, txt in (FbChat.objects.filter(sent_at__gte=since).order_by("sent_at", "id")
                        .values_list("thread_id", "direction", "text").iterator()):
        if tid and txt:
            fb.setdefault(tid, []).append({"dir": d or "in", "text": txt})
    out = {}
    if line:
        for oid, uid in (ChatOwner.objects.filter(profile__user_id__in=list(line), profile__is_employee=False)
                         .exclude(profile__user_id__startswith="TEST-").values_list("id", "profile__user_id")):
            out[oid] = line.get(uid) or []
    if fb:
        for oid, tid in (ChatOwner.objects.filter(fb_profile__thread_id__in=list(fb), fb_profile__is_employee=False)
                         .values_list("id", "fb_profile__thread_id")):
            out[oid] = fb.get(tid) or []
    return out


def _snippet(text: str, word: str, n: int = 90) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    i = t.lower().find((word or "").lower())
    if i < 0 or len(t) <= n:
        return t[:n]
    a = max(0, i - n // 3)
    return ("…" if a else "") + t[a:a + n] + ("…" if a + n < len(t) else "")


def preview(data: dict, days: int = SCAN_DAYS) -> dict:
    """ทดสอบกฎก่อนบันทึก (ยังไม่ติดแท็กใคร) → `{ok, chats, matched, samples:[{id, name, word, text}]}`"""
    rule, err = clean_rule(dict(data or {}, on=True), [])
    if err:
        return {"ok": False, "error": err}
    corpus = _corpus(days)
    hits = []
    for oid, msgs in corpus.items():
        for txt in _texts(rule, msgs):
            w = hit(rule, txt)
            if w:
                hits.append((oid, w, txt))
                break
    samples = []
    if hits:
        from . import connect as C
        from .models import ChatOwner
        pick = hits[-SAMPLE_MAX:]
        objs = ChatOwner.objects.select_related("profile", "fb_profile").in_bulk([h[0] for h in pick])
        for oid, w, txt in reversed(pick):
            o = objs.get(oid)
            if not o:
                continue
            name = ""
            try:
                p = C.cust(o)
                ld = C.lead_of(o, create=False)
                name = (ld.customer_name if ld and ld.customer_name else "") or p.show_name or ""
            except Exception:
                pass
            samples.append({"id": oid, "name": name, "word": w, "text": _snippet(txt, w)})
    return {"ok": True, "days": days, "chats": len(corpus), "matched": len(hits), "samples": samples}


def rescan(by: str = "", days: int = SCAN_DAYS) -> dict:
    """อ่านแชทย้อนหลังทั้งหมดตามกฎปัจจุบัน → ติด/เปลี่ยนชื่อ/เอาแท็กออก ให้ตรงกฎ (ไม่แตะแท็กที่คนใส่เอง)"""
    from . import connect as C
    from .models import ChatLead, ChatOwner
    rs = rules(cache=False)
    corpus = _corpus(days)
    found_by = {oid: tags_for(rs, msgs) for oid, msgs in corpus.items()}
    todo = {oid for oid, f in found_by.items() if f}
    todo |= set(ChatLead.objects.filter(auto__has_key=ATAG_KEY).values_list("chat_id", flat=True))
    changed = tagged = 0
    for o in ChatOwner.objects.filter(pk__in=list(todo)).select_related("profile", "fb_profile"):
        found = found_by.get(o.pk) or {}
        lead = C.lead_of(o, create=bool(found))
        if not lead:
            continue
        auto = dict(lead.auto or {})
        if apply_lead(lead, auto, found, rs, prune=o.pk in corpus):
            lead.auto = auto
            lead.save(update_fields=["tags", "auto", "updated_at"])
            changed += 1
        if auto.get(ATAG_KEY):
            tagged += 1
    res = {"at": timezone.now().isoformat(timespec="seconds"), "by": (by or "")[:80], "days": days,
           "chats": len(corpus), "changed": changed, "tagged": tagged, "error": ""}
    _save_last(res)
    return res


def _save_last(res: dict):
    try:
        from dashboard.services import cache_store
        cache_store.set_kv(LAST_KEY, res)
    except Exception:
        pass


BG = True                          # เทสต์ตั้ง False = ทำทันที (thread ชน SQLite)


def rescan_bg(by: str = ""):
    """อ่านย้อนหลังใน thread (หน้าเว็บไม่ต้องรอ) · กำลังทำอยู่ = จดว่าต้องทำอีกรอบ (แก้กฎติดกันหลายครั้ง)"""
    if not BG:
        rescan(by)
        return
    if _RUN["busy"]:
        _RUN["again"] = by or "1"
        return
    _RUN["busy"] = True

    def job():
        from django.db import close_old_connections
        try:
            who = by
            while True:
                _RUN.pop("again", None)
                try:
                    rescan(who)
                except Exception as e:
                    _save_last({"at": timezone.now().isoformat(timespec="seconds"), "by": who, "error": str(e)[:200]})
                    try:
                        from dashboard.services import eventlog
                        eventlog.log("cron", name="ระบบอัตโนมัติ (แท็กลูกค้า)", ok=False, error=str(e)[:300])
                    except Exception:
                        pass
                if not _RUN.get("again"):
                    break
                who = _RUN.get("again") if _RUN.get("again") != "1" else who
        finally:
            _RUN["busy"] = False
            close_old_connections()
    threading.Thread(target=job, name="autotag-rescan", daemon=True).start()


def last_run() -> dict:
    try:
        from dashboard.services import cache_store
        raw = cache_store.get_kv(LAST_KEY) or {}
        return (raw.get("data") if isinstance(raw, dict) and "data" in raw else raw) or {}
    except Exception:
        return {}


def rule_counts() -> dict:
    """{id กฎ: ลูกค้าที่ติดแท็กอยู่ตอนนี้}"""
    from .models import ChatLead
    out = {}
    for a in ChatLead.objects.filter(auto__has_key=ATAG_KEY).values_list("auto", flat=True):
        for rec in ((a or {}).get(ATAG_KEY) or {}).values():
            rid = (rec or {}).get("rule")
            if rid:
                out[rid] = out.get(rid, 0) + 1
    return out


# ── ระบบจับในตัว (อยู่ในโค้ด · หน้าเว็บแสดงอย่างเดียว) ─────────────────────────

BUILTIN = [
    {"key": "contact", "name": "เบอร์โทร / ไอดีไลน์", "to": "เบอร์โทร · ID LINE",
     "how": "เบอร์ 9–10 หลัก · มีคำว่าไลน์/ไอดีนำหน้า · คำเดียวที่ลูกค้าส่งหลังเราขอไอดี · ไอดีหน้าตาชัด · ลิงก์ line.me · รูป QR",
     "fields": ("phone", "line_id")},
    {"key": "car", "name": "รถที่สนใจ", "to": "รถลูกค้าถาม · CAR/สูตร · ADS",
     "how": "ชื่อรุ่นไทย/อังกฤษ (ดีแม็ก ฟอจูนเนอร์ …) · ยี่ห้อ · ปี/งบที่พิมพ์ต่อกัน · การ์ดโฆษณา Facebook",
     "fields": ("car_text", "car_model", "ads")},
    {"key": "occupation", "name": "อาชีพ + ประเภทลูกค้า", "to": "อาชีพ · ประเภทลูกค้า",
     "how": "~15 หมวด: พนักงานบริษัท/โรงงาน · ราชการ/ทหาร/ครู · เกษตร · เจ้าของกิจการ · ค้าขาย · ไรเดอร์ · ฟรีแลนซ์ · รับจ้าง · ว่างงาน",
     "fields": ("occupation", "customer_type")},
    {"key": "income", "name": "รายได้", "to": "รายได้",
     "how": "ต้องมีคำว่า รายได้/เงินเดือน/ฐาน/สลิป นำหน้าตัวเลข (ค่างวด/ดาวน์/งบ ไม่นับ · รายวันไม่เติม)",
     "fields": ("income",)},
    {"key": "job_tenure", "name": "อายุงาน", "to": "อายุงาน", "how": "\"อายุงาน …\" · \"ทำมา 3 ปี\" · \"ทำงานได้ 8 เดือน\"",
     "fields": ("job_tenure",)},
    {"key": "pay_history", "name": "ประวัติผ่อน", "to": "ประวัติการผ่อน",
     "how": "19 กลุ่ม: ไม่มีเครดิต · ติดแบล็คลิส · ติดบูโร · ผ่อนบ้าน/รถ/มอไซค์/มือถือ · บัตรเครดิต · ช้อปปี้ · ผ่อนตรง · เคยค้างชำระ · โดนยึด · ผ่อนหมดแล้ว",
     "fields": ("pay_history",)},
    {"key": "status", "name": "สถานะลูกค้า (คอลัมน์ Z)", "to": "สถานะลูกค้า",
     "how": "ได้รถแล้ว · ไม่สนใจแล้ว · หาคนออกให้ · ติดแบล็คลิส · ดาวน์ไม่พอ · เงินสดไม่พอ · มีรถเทิร์น · รอเช็คเครดิต · "
            "รอมาดูรถ · ยังไม่ออกเร็วๆนี้ · ยังไม่สะดวกคุย · ลังเล · สนใจมาก (ข้อความล่าสุดชนะ)",
     "fields": ("customer_status",)},
    {"key": "deal", "name": "ลีดรับซื้อ / มีรถเทิร์น", "to": "แยกแท็บรับซื้อรถในห้องพัก Lead",
     "how": "อยากขาย · ขายรถ · รับซื้อ · ประเมินราคา · ขายได้เท่าไหร่ · ข้อความของเรา \"ฝ่ายจัดซื้อ/สำเนาเล่ม\" · "
            "ลูกค้าส่งรูปรถ ≥2 รูปหลังเราขอ · (เทิร์น/แลกรถ = ยังเป็นลีดขาย)",
     "fields": ()},
]
_AUTO_SRC = ("แชท", "โฆษณา", "รูป QR")
_BI = {"at": 0.0, "val": None}


def builtin_stats(days: int = 30) -> list:
    """ระบบจับในตัว + ลูกค้าที่ระบบเติมให้ใน `days` วัน (นับจากช่องที่ `auto` บอกว่ามาจากแชท/โฆษณา/รูป QR) · จำ 5 นาที"""
    if _BI["val"] is not None and time.time() - _BI["at"] < 300:
        return _BI["val"]
    from .models import ChatLead
    since = timezone.now() - timedelta(days=days)
    n = {b["key"]: 0 for b in BUILTIN}
    status = {}
    total = 0
    for a, z in ChatLead.objects.filter(updated_at__gte=since).values_list("auto", "customer_status").iterator():
        a = a or {}
        total += 1
        for b in BUILTIN:
            if b["fields"] and any(a.get(f) in _AUTO_SRC for f in b["fields"]):
                n[b["key"]] += 1
        if "_buylead" in a or "_trade" in a:
            n["deal"] += 1
        if a.get("customer_status") in _AUTO_SRC and z:
            status[z] = status.get(z, 0) + 1
    val = [dict({k: v for k, v in b.items() if k != "fields"}, count=n[b["key"]], days=days, total=total,
                top=(sorted(status.items(), key=lambda x: -x[1])[:5] if b["key"] == "status" else []))
           for b in BUILTIN]
    _BI.update(at=time.time(), val=val)
    return val
