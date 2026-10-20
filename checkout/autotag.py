# -*- coding: utf-8 -*-
"""ระบบอัตโนมัติ: แท็กลูกค้าจากคำในแชท — หน้า "ระบบอัตโนมัติ" ใน Oxlet CRM (`/crm/?p=auto`)

★ 20 ต.ค.69 เจ้าของสั่ง *"เพิ่มหน้าหนึ่งขึ้นมาเป็นหน้าของระบบอัตโนมัติ ซึ่งสามารถเพิ่ม ลบ แก้ไขระบบอัตโนมัติที่แท็กได้"*
★ 21 ต.ค.69 *"ระบบอัตโนมัติที่แท็กลูกค้าได้ตรงจุดว่าลูกค้าสนใจอะไร กลุ่มไหน … รุ่นรถที่ลูกค้าถามหา รายได้ … ไอ้พวก Isuzu"*
   *"ถ้าจับจากโค้ด เปลี่ยนจากโค้ดเป็นฐานข้อมูล แล้วเอามาใส่ไว้ในหน้านี้"* → คำทั้งหมดอยู่ในตาราง `checkout_keywordrule` (`kwdb.py`)

แท็กลงช่อง `ChatLead.tags` ช่องเดียวกับที่คนพิมพ์แท็กในหน้า Connect — มาจาก 2 แบบ
  · **จากข้อความในแชท**: ยี่ห้อ (Isuzu) · รุ่น (D Max → ได้ Isuzu ด้วย) · กฎแท็กของเรา (หมวด custom) — ติดเพิ่มอย่างเดียวตอนข้อความเข้า
  · **จากช่องข้อมูลลูกค้า** (`kwdb.STATE_GROUPS`): ช่วงรายได้ · ประเภทลูกค้า · สถานะลูกค้า · ประวัติผ่อน — แท็กเปลี่ยนตามค่าปัจจุบัน
    (รายได้เปลี่ยนช่วง = แท็กเดิมออก แท็กใหม่เข้า) · ช่องที่คนกรอกเองก็นับ
  · แถวไหนติดแท็ก = สวิตช์ "ติดแท็ก" ของแถวนั้น (ยี่ห้อ/รุ่น/ช่วงรายได้/กฎของเรา เปิดไว้ตั้งแต่ต้น · หมวดอื่นเปิดเองได้)
  · `ChatLead.auto["_atags"]` = แท็กไหนระบบติดให้ จากแถวไหน คำไหน (`{แท็ก: {rule: key ของแถว, word, at}}`)
  · **คนเอาแท็กออกเอง = ระบบไม่ติดกลับ** (`auto["_tag_no"]`) · คนใส่แท็กเดียวกันไว้เองก่อน = เป็นของคน ระบบไม่ยึด
  · อ่านแชทย้อนหลังทั้งหมด (`rescan_bg` · ใน thread) ทุกครั้งที่แก้คำ/แถว + วันละครั้งตอนตี 3 (ช่องที่คนแก้ในหน้า Connect จะได้แท็กตาม)
  · ไม่ใช้ AI · ไม่ส่งอะไรออกนอกระบบ
"""
from __future__ import annotations

import re
import threading
import time
from datetime import timedelta

from django.utils import timezone

from . import kwdb

LAST_KEY = "autotag_last"          # ผลรอบอ่านแชทย้อนหลังล่าสุด
DAILY_KEY = "autotag_daily"        # วันที่อ่านย้อนหลังรอบประจำวันแล้ว
ATAG_KEY = "_atags"
TAGNO_KEY = "_tag_no"
SCAN_DAYS = 60                     # = อายุแชทลูกค้า (CUSTOMER_CHAT_KEEP_DAYS) — อ่านได้เท่าที่ระบบเก็บไว้
RULE_MAX = 60
WORDS_MAX = 40
WORD_MIN, WORD_LEN, TAG_LEN = kwdb.WORD_MIN, kwdb.WORD_LEN, 30
TAGS_MAX = 12                      # = เพดานแท็กต่อลูกค้าใน `connect.save_lead_field`
CAR_TAGS_MAX = 4                   # รุ่นที่ติดแท็กได้ต่อลูกค้า (ลูกค้าถามหลายรุ่น = เอารุ่นที่พูดถึงล่าสุด)
SCOPES = {"in": "ข้อความลูกค้า", "all": "ข้อความลูกค้าและของเรา"}
SAMPLE_MAX = 8
DAILY_HOUR = 3

_RUN = {"busy": False}


# ── กฎแท็กของเรา (หมวด custom) — รูปแบบเดิม {id, tag, words, not_words, scope, on} ─────────────

def _as_rule(r: dict) -> dict:
    return {"id": r["key"], "tag": r["name"], "words": list(r.get("words") or []),
            "not_words": list(r.get("not_words") or []), "scope": (r.get("extra") or {}).get("scope") or "in",
            "on": bool(r.get("active")), "group": "custom", "by": r.get("updated_by") or "",
            "at": r["updated_at"].isoformat(timespec="seconds") if hasattr(r.get("updated_at"), "isoformat") else ""}


def rules(cache: bool = True) -> list:
    """กฎแท็กของเรา (หมวด custom) เรียงตามลำดับ"""
    if not cache:
        kwdb._load(force=True)
    return [_as_rule(r) for r in kwdb.rows("custom", active=False)]


def active() -> list:
    return [r for r in rules() if r.get("on")]


def _words(v) -> list:
    return kwdb.split_words(v)


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
    rs = rules(cache=False)
    rule, err = clean_rule(data, rs)
    if err:
        return False, err, None
    if not rule["id"] and len(rs) >= RULE_MAX:
        return False, "มีกฎครบ %d ข้อแล้ว — ลบกฎที่ไม่ใช้ก่อน" % RULE_MAX, None
    ok, msg, row = kwdb.save({"key": rule["id"], "group": "custom", "name": rule["tag"], "words": rule["words"],
                              "not_words": rule["not_words"], "extra": {"scope": rule["scope"]}, "active": rule["on"],
                              "tag": True}, by=by)
    if not ok:
        return False, msg, None
    rescan_bg(by)
    out = _as_rule(row)
    return True, ("บันทึกกฎ \"%s\" แล้ว" if rule["id"] else "เพิ่มกฎ \"%s\" แล้ว") % out["tag"] + \
        " — กำลังติดแท็กให้แชทย้อนหลัง %d วัน" % SCAN_DAYS, out


def delete_rule(rid: str, by: str = "") -> tuple:
    r = next((x for x in rules(cache=False) if x["id"] == str(rid or "")), None)
    if not r:
        return False, "ไม่พบกฎนี้ (อาจถูกลบไปแล้ว)"
    ok, msg = kwdb.delete(r["id"], by=by)
    if not ok:
        return False, msg
    rescan_bg(by)
    return True, "ลบกฎ \"%s\" แล้ว — แท็กที่ระบบติดจากกฎนี้จะถูกเอาออก" % r["tag"]


def toggle(rid: str, on: bool, by: str = "") -> tuple:
    r = next((x for x in rules(cache=False) if x["id"] == str(rid or "")), None)
    if not r:
        return False, "ไม่พบกฎนี้ (อาจถูกลบไปแล้ว)"
    ok, msg, _row = kwdb.toggle(r["id"], "active", on, by=by)
    if not ok:
        return False, msg
    rescan_bg(by)
    return True, ("เปิดกฎ \"%s\" แล้ว — กำลังติดแท็กย้อนหลัง" if on else
                  "ปิดกฎ \"%s\" แล้ว — แท็กที่ระบบติดจากกฎนี้จะถูกเอาออก") % r["tag"]


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
    """ข้อความ (เก่า→ใหม่ · `{dir, text}`) → `{แท็ก: (id กฎ, คำที่จับได้)}` จากกฎแท็กของเราที่เปิดอยู่"""
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


# ── แท็กของระบบ (ยี่ห้อ/รุ่น/ช่วงรายได้/ประเภท/สถานะ/ประวัติผ่อน) ───────────────────────

def tag_rows() -> list:
    """ทุกแถวที่ติดแท็กได้ ในรูปกฎ {id, tag, on, group} (on = เปิดใช้ + สวิตช์ติดแท็ก) — ใช้กับ `apply_lead`"""
    return [{"id": r["key"], "tag": r["name"], "on": bool(r.get("active") and r.get("tag")), "group": r["group"]}
            for r in kwdb.all_rows() if r["group"] in kwdb.TAG_GROUPS]


def car_tags(texts) -> dict:
    """ข้อความลูกค้า → `{แท็ก: (key, คำ)}` ของรุ่น (ล่าสุด CAR_TAGS_MAX รุ่น) + ยี่ห้อของรุ่น + ยี่ห้อที่พิมพ์เอง"""
    brands = {r["name"]: r for r in kwdb.rows("brand")}
    models, brand_hits = [], {}
    for t in texts or []:
        if not t or str(t).startswith("["):
            continue
        for r, w in kwdb.models_in(t):
            models = [m for m in models if m[0]["key"] != r["key"]] + [(r, w)]
        for r, _pos, w in kwdb.brands_in(t):
            brand_hits[r["key"]] = (r, w)
    out = {}
    for r, w in models[-CAR_TAGS_MAX:]:
        if r.get("tag"):
            out[r["name"]] = (r["key"], w)
        b = brands.get(r.get("parent") or "")
        if b and b.get("tag") and b["name"] not in out:
            out[b["name"]] = (b["key"], w)
    for r, w in brand_hits.values():
        if r.get("tag") and r["name"] not in out:
            out[r["name"]] = (r["key"], w)
    return out


def _income_num(v):
    """ช่อง "รายได้" ("25000" · "20000-25000" · "25,000") → ตัวเลขกลาง หรือ None"""
    ns = [int(x.replace(",", "")) for x in re.findall(r"\d[\d,]*", str(v or "")) if x.replace(",", "").isdigit()]
    ns = [n for n in ns if 1000 <= n <= 5_000_000]
    if not ns:
        return None
    return sum(ns[:2]) / len(ns[:2])


def state_tags(lead) -> dict:
    """ช่องข้อมูลลูกค้า → `{แท็ก: (key, ค่าที่ทำให้ติด)}` (ช่วงรายได้ · ประเภทลูกค้า · สถานะลูกค้า · ประวัติผ่อน)"""
    if lead is None:
        return {}
    out = {}
    inc = _income_num(getattr(lead, "income", ""))
    if inc is not None:
        for r in kwdb.rows("income_band"):
            ex = r.get("extra") or {}
            lo, hi = ex.get("min"), ex.get("max")
            if r.get("tag") and lo is not None and inc >= lo and (hi is None or inc < hi):
                out[r["name"]] = (r["key"], str(getattr(lead, "income", "")))
                break
    ct = kwdb.nw(getattr(lead, "customer_type", ""))
    if ct:
        for r in kwdb.rows("cust_type"):
            spell = [kwdb.nw(x) for x in (r.get("extra") or {}).get("spell") or []] + [kwdb.nw(r["name"])]
            if r.get("tag") and ct in spell:
                out[r["name"]] = (r["key"], getattr(lead, "customer_type", ""))
    st = kwdb.nw(getattr(lead, "customer_status", ""))
    if st:
        for r in kwdb.rows("status"):
            spell = [kwdb.nw(x) for x in (r.get("extra") or {}).get("spell") or []] + [kwdb.nw(r.get("value"))]
            if r.get("tag") and st in spell:
                out[r["name"]] = (r["key"], getattr(lead, "customer_status", ""))
    ph = kwdb.nw(getattr(lead, "pay_history", ""))
    if ph:
        for r in kwdb.rows("pay"):
            v = kwdb.nw(r.get("value") or r["name"])
            if r.get("tag") and v and v in ph:
                out[r["name"]] = (r["key"], v)
    return out


def found_for(msgs, lead=None) -> dict:
    """ทุกแท็กที่ลูกค้ารายนี้ควรมีตอนนี้ (ข้อความ + ช่องข้อมูล) → `{แท็ก: (key, คำ)}`"""
    out = tags_for(active(), msgs)
    texts = [m.get("text") or "" for m in msgs or [] if (m.get("dir") or "in") == "in"]
    if lead is not None:
        texts += [getattr(lead, "car_text", "") or "", getattr(lead, "car_model", "") or ""]
    for k, v in car_tags(texts).items():
        out.setdefault(k, v)
    for k, v in state_tags(lead).items():
        out.setdefault(k, v)
    return out


def apply_lead(lead, auto: dict, found: dict, rs: list, prune: bool = False) -> bool:
    """ติด/เอาแท็กออกของลูกค้า 1 ราย (แก้ `auto` กับ `lead.tags` ในที่ ไม่ save) → เปลี่ยนอะไรไหม

    แท็กของระบบที่แถวถูกลบ/ปิด = เอาออก · แถวเปลี่ยนชื่อ = เปลี่ยนตาม · `prune` = อ่านแชทครบแล้ว ไม่เจอคำอีก = เอาออก
    (ตอนข้อความเข้าติดเพิ่มอย่างเดียว) · แท็กจากช่องข้อมูลลูกค้า (ช่วงรายได้ ฯลฯ) เอาออกเสมอเมื่อค่าไม่เข้าแล้ว"""
    by_id = {r["id"]: r for r in rs or []}
    atags = dict(auto.get(ATAG_KEY) or {})
    no = list(auto.get(TAGNO_KEY) or [])
    tags = list(lead.tags or [])
    before = (list(tags), dict(atags))
    for t, rec in list(atags.items()):
        r = by_id.get((rec or {}).get("rule"))
        state = bool(r) and r.get("group") in kwdb.STATE_GROUPS
        drop = (not r or not r.get("on") or ((prune or state) and r["tag"] not in found))
        if not drop and r["tag"] != t:               # แถวเปลี่ยนชื่อแท็ก
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
        atags[t] = {"rule": rid, "word": str(w or "")[:60], "at": (atags.get(t) or {}).get("at") or now}
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


# ── อ่านแชทย้อนหลัง (ทดสอบกฎ / ติดแท็กทั้งหมดใหม่หลังแก้คำ) ──────────────────────

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


def _samples(hits) -> list:
    out = []
    if not hits:
        return out
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
        out.append({"id": oid, "name": name, "word": w, "text": _snippet(txt, w)})
    return out


def preview(data: dict, days: int = SCAN_DAYS) -> dict:
    """ทดสอบกฎแท็กของเราก่อนบันทึก (ยังไม่ติดแท็กใคร) → `{ok, chats, matched, samples:[{id, name, word, text}]}`"""
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
    return {"ok": True, "days": days, "chats": len(corpus), "matched": len(hits), "samples": _samples(hits)}


def preview_row(data: dict, days: int = SCAN_DAYS) -> dict:
    """ทดสอบแถวคำ (หมวดไหนก็ได้ · ยังไม่บันทึก) กับแชทย้อนหลัง → แชทกี่รายมีข้อความที่เข้าแถวนี้ + ตัวอย่าง"""
    from .lead_keywords import norm
    cur = None
    key = str((data or {}).get("key") or "")
    if key:
        cur = next((r for r in kwdb.all_rows() if r["key"] == key), None)
    row, err = kwdb.clean(dict(data or {}, active=True), cur)
    if err:
        return {"ok": False, "error": err}
    alt = kwdb.row_alt(row)
    if not alt:
        return {"ok": False, "error": "แถวนี้ไม่ได้จับจากข้อความ (ใช้ค่าจากช่องข้อมูลลูกค้า)"}
    flags = re.I if row["group"] == "contact" else (re.M if row["group"] == "deal" else 0)
    rx_ = re.compile(alt, flags)
    nots = [kwdb.nw(w) for w in row.get("not_words") or []]
    scope = (row.get("extra") or {}).get("scope") or "in"
    corpus = _corpus(days)
    hits = []
    for oid, msgs in corpus.items():
        for m in msgs:
            if scope != "all" and (m.get("dir") or "in") != "in":
                continue
            raw = str(m.get("text") or "")
            if not raw or raw.startswith("["):
                continue
            t = norm(raw)
            if nots and any(n in t for n in nots):
                continue
            mm = rx_.search(t)
            if mm and mm.end() > mm.start():
                hits.append((oid, mm.group(0), raw))
                break
    return {"ok": True, "days": days, "chats": len(corpus), "matched": len(hits), "samples": _samples(hits)}


def rescan(by: str = "", days: int = SCAN_DAYS) -> dict:
    """อ่านแชทย้อนหลังทั้งหมดตามคำ/แถวปัจจุบัน → ติด/เปลี่ยนชื่อ/เอาแท็กออก ให้ตรง (ไม่แตะแท็กที่คนใส่เอง)"""
    from . import connect as C
    from .models import ChatLead, ChatOwner
    kwdb._load(force=True)
    rs = tag_rows()
    corpus = _corpus(days)
    todo = set(corpus)
    todo |= set(ChatLead.objects.filter(auto__has_key=ATAG_KEY).values_list("chat_id", flat=True))
    changed = tagged = 0
    for o in ChatOwner.objects.filter(pk__in=list(todo)).select_related("profile", "fb_profile"):
        lead = C.lead_of(o, create=False)
        found = found_for(corpus.get(o.pk) or [], lead)
        if lead is None:
            if not found:
                continue
            lead = C.lead_of(o)
            found = found_for(corpus.get(o.pk) or [], lead)
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
    """อ่านย้อนหลังใน thread (หน้าเว็บไม่ต้องรอ) · กำลังทำอยู่ = จดว่าต้องทำอีกรอบ (แก้คำติดกันหลายครั้ง)"""
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


def maybe_daily(now=None):
    """เรียกจาก `connect.tick` ทุกนาที — ตี 3 อ่านย้อนหลังวันละครั้ง (ช่องที่คนแก้ในหน้า Connect ได้แท็กตาม)"""
    from dashboard.services import cache_store
    from dashboard.services.helpers import bangkok_now
    t = bangkok_now()
    if t.hour != DAILY_HOUR:
        return None
    day = t.strftime("%Y-%m-%d")
    raw = cache_store.get_kv(DAILY_KEY) or {}
    d = raw.get("data") if isinstance(raw, dict) and "data" in raw else raw
    if (d or {}).get("day") == day:
        return None
    cache_store.set_kv(DAILY_KEY, {"day": day})
    rescan_bg("ระบบ (รอบประจำวัน)")
    return {"started": True}


def last_run() -> dict:
    try:
        from dashboard.services import cache_store
        raw = cache_store.get_kv(LAST_KEY) or {}
        return (raw.get("data") if isinstance(raw, dict) and "data" in raw else raw) or {}
    except Exception:
        return {}


def rule_counts() -> dict:
    """{key ของแถว: ลูกค้าที่ติดแท็กจากแถวนั้นอยู่ตอนนี้}"""
    from .models import ChatLead
    out = {}
    for a in ChatLead.objects.filter(auto__has_key=ATAG_KEY).values_list("auto", flat=True):
        for rec in ((a or {}).get(ATAG_KEY) or {}).values():
            rid = (rec or {}).get("rule")
            if rid:
                out[rid] = out.get(rid, 0) + 1
    return out


# ── จำนวนลูกค้าที่ระบบเติมช่องให้ (ต่อหมวด · ไว้แสดงในหน้าเว็บ) ─────────────────────────

FILL_FIELDS = {
    "brand": ("car_text", "car_model"), "model": ("car_text", "car_model"), "income_kw": ("income",),
    "income_band": ("income",), "occupation": ("occupation", "customer_type"), "cust_type": ("customer_type",),
    "tenure_kw": ("job_tenure",), "pay": ("pay_history",), "status": ("customer_status",), "contact": ("line_id",),
}
_AUTO_SRC = ("แชท", "โฆษณา", "รูป QR", "รูป")
_BI = {"at": 0.0, "val": None}


def fill_stats(days: int = 30) -> dict:
    """{หมวด: ลูกค้าที่ระบบเติมช่องของหมวดนั้นให้ใน `days` วัน} (+ deal = จัดเป็นลีดรับซื้อ/มีเทิร์น) · จำ 5 นาที"""
    if _BI["val"] is not None and time.time() - _BI["at"] < 300:
        return _BI["val"]
    from .models import ChatLead
    since = timezone.now() - timedelta(days=days)
    n = {k: 0 for k in list(FILL_FIELDS) + ["deal"]}
    total = 0
    for a in ChatLead.objects.filter(updated_at__gte=since).values_list("auto", flat=True).iterator():
        a = a or {}
        total += 1
        for g, fs in FILL_FIELDS.items():
            if any(a.get(f) in _AUTO_SRC for f in fs):
                n[g] += 1
        if "_buylead" in a or "_trade" in a:
            n["deal"] += 1
    val = {"days": days, "total": total, "count": n}
    _BI.update(at=time.time(), val=val)
    return val


def test_text(text: str) -> dict:
    """ลองพิมพ์ข้อความ → ระบบจับอะไรได้บ้าง (ไม่บันทึกอะไร) — หน้าเว็บใช้ดูว่าคำที่แก้ทำงานไหม"""
    from . import connect as C
    from . import lead_keywords as K
    t = str(text or "")[:2000]
    got = K.extract([t])
    fields = []
    names = {"occupation": "อาชีพ", "customer_type": "ประเภทลูกค้า", "income": "รายได้", "job_tenure": "อายุงาน",
             "pay_history": "ประวัติผ่อน", "customer_status": "สถานะลูกค้า"}
    types = {r["value"]: r["name"] for r in kwdb.rows("cust_type", active=False)}
    for f, (v, ev) in got.items():
        fields.append({"field": names.get(f, f), "value": types.get(v, v) if f == "customer_type" else v, "word": ev})
    car = C.car_in(t)
    if car is not None:
        fields.append({"field": "CAR/สูตร", "value": car[0] or "(รุ่นกว้าง/บอกแค่ยี่ห้อ — ไม่เติม)", "word": C.car_phrase(t)})
    ph, ids = C.contacts_in([{"dir": "in", "text": t}])
    if ph:
        fields.append({"field": "เบอร์โทร", "value": ", ".join(ph), "word": ""})
    if ids:
        fields.append({"field": "ID LINE", "value": ", ".join(ids), "word": ""})
    dk = K.deal_kind([t])
    if dk.get("kind") == "buy":
        fields.append({"field": "ลีดรับซื้อ", "value": "ใช่", "word": dk.get("why") or ""})
    if dk.get("trade"):
        fields.append({"field": "มีรถเทิร์น", "value": "ใช่", "word": dk.get("trade") or ""})

    class _L:
        pass
    ld = _L()
    for f in ("income", "customer_type", "customer_status", "pay_history"):
        v = got.get(f, ("", ""))[0]
        if f == "customer_type":
            v = types.get(v, v)
        setattr(ld, f, v)
    tags = found_for([{"dir": "in", "text": t}], ld)
    return {"ok": True, "fields": fields, "tags": [{"tag": k, "word": str(v[1] or "")[:60]} for k, v in tags.items()]}
