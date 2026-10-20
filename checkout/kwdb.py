# -*- coding: utf-8 -*-
"""ตัวอ่าน "คำที่ระบบจับ" จากฐานข้อมูล (ตาราง `checkout_keywordrule`) — ★ 21 ต.ค.69 เจ้าของสั่ง
*"ถ้าจับจากโค้ด เปลี่ยนจากโค้ดเป็นฐานข้อมูล แล้วเอามาใส่ไว้ในหน้านี้"* (หน้า "ระบบอัตโนมัติ" · /crm/?p=auto)

ทุกตัวที่จับคำจากแชท (lead_keywords · connect.brand_in/ไอดีไลน์ · leadgroup.parse_specs · autotag) อ่านจากที่นี่
  · จำไว้ต่อ process · เช็คทุก `CHECK_SEC` วิว่ามีคนแก้ไหม (KV `keyword_version`) → แก้ในหน้าเว็บแล้วทุก worker ตามภายใน ~15 วิ
  · ตารางยังไม่มี/อ่านไม่ได้ = ใช้ค่าตั้งต้น `kw_defaults.py` (ระบบไม่หยุดจับ)
  · แถวหนึ่งจับเมื่อข้อความเข้า **รูปแบบขั้นสูง** (`pattern` · ค่าเดิมจากโค้ด) **หรือ** มี **คำที่จับ** (`words` · คนเพิ่มเองได้)
    คำภาษาอังกฤษต้องขึ้นต้นคำ (กัน "line" ใน "online") · ช่องว่างในคำ = มีหรือไม่มีช่องว่างก็ได้
"""
from __future__ import annotations

import re
import threading
import time
import uuid

VER_KEY = "keyword_version"
CHECK_SEC = 15
NEVER = r"(?!x)x"                       # regex ที่ไม่มีวันจับอะไร (หมวดที่ปิดหมด)
WORD_MIN, WORD_LEN, WORDS_MAX, NAME_LEN, PATTERN_MAX, GROUP_MAX = 2, 40, 80, 60, 4000, 400

# ── หมวด (ลำดับ = ลำดับในหน้าเว็บ) ──
#   tag = แถวในหมวดนี้ติดแท็กลูกค้าได้ · roles = บทบาทที่แถวในหมวดนี้เลือกได้ (แถวที่ไม่มีบทบาท = ไม่ต้องเลือก)
GROUPS = [
    {"k": "brand", "name": "ยี่ห้อรถ", "sec": "car", "tag": True,
     "desc": "ลูกค้าพิมพ์ชื่อยี่ห้อ → แท็กยี่ห้อ · ลงช่อง \"รถลูกค้าถาม\" (บอกแค่ยี่ห้อ = รู้ว่าถามรถ แต่ไม่รู้รุ่น)"},
    {"k": "model", "name": "รุ่นรถ", "sec": "car", "tag": True,
     "desc": "ลูกค้าพิมพ์ชื่อรุ่น (ไทย/อังกฤษ) → แท็กรุ่น + แท็กยี่ห้อของรุ่นนั้น · ใช้เติม \"รถลูกค้าถาม\" และ \"CAR/สูตร\""},
    {"k": "income_band", "name": "ช่วงรายได้", "sec": "money", "tag": True,
     "desc": "จากช่อง \"รายได้\" ของลูกค้า (ระบบจับจากแชท หรือคนกรอกเอง) → แท็กช่วงรายได้ · แท็กเปลี่ยนตามเมื่อรายได้เปลี่ยน"},
    {"k": "income_kw", "name": "คำบอกรายได้", "sec": "money",
     "roles": {"lead": "คำบอกรายได้ (หน้าตัวเลข)", "per_day": "รายวัน/รายสัปดาห์ (ไม่เติม)",
               "not_income": "ไม่ใช่รายได้", "total": "รายได้รวม (ใช้ตัวนี้ก่อน)", "salaried": "= พนักงานบริษัท"},
     "desc": "ตัวเลขเงินจะนับเป็นรายได้ก็ต่อเมื่อมีคำบอกรายได้นำหน้า (ไม่เกิน ~30 ตัวอักษร) — ค่างวด/ดาวน์/งบ ไม่นับ"},
    {"k": "occupation", "name": "อาชีพ", "sec": "profile",
     "desc": "คำที่บอกอาชีพ → ช่อง \"อาชีพ\" + \"ประเภทลูกค้า\" (หมวดที่แถวนั้นอยู่) · อาชีพของแฟน/พ่อแม่ และอาชีพในอดีต ไม่นับ"},
    {"k": "cust_type", "name": "ประเภทลูกค้า", "sec": "profile", "tag": True,
     "desc": "หมวดของอาชีพ → ตัวเลือก \"ประเภทลูกค้า\" ในชีต (คำที่จับ = ตัวสะกดในชีต) · ติดแท็กได้"},
    {"k": "tenure_kw", "name": "อายุงาน", "sec": "profile", "roles": {"lead": "คำบอกอายุงาน"},
     "desc": "คำที่อยู่หน้าระยะเวลา (\"อายุงาน 3 ปี\" · \"ทำมา 8 เดือน\") → ช่อง \"อายุงาน\""},
    {"k": "pay", "name": "ประวัติผ่อน", "sec": "profile", "tag": True,
     "desc": "คำที่บอกเครดิต/หนี้เดิม → ช่อง \"ประวัติการผ่อน\" · มีคำปฏิเสธนำหน้า = ใช้ข้อความ \"ถ้าปฏิเสธ\""},
    {"k": "status", "name": "สถานะลูกค้า", "sec": "status", "tag": True,
     "desc": "ข้อความล่าสุดที่บอกสถานะชนะ → ช่อง \"สถานะลูกค้า\" (คอลัมน์ Z) · แถวบนสุดชนะเมื่อข้อความเดียวมีหลายสถานะ"},
    {"k": "deal", "name": "ลีดรับซื้อ / รถเทิร์น", "sec": "status",
     "roles": {"buy": "อยากขายรถให้เรา", "buy_not": "ห้ามนับ", "job": "สมัครงาน (ไม่ใช่ลีด)",
               "trade": "มีรถเทิร์น", "buy_out": "ข้อความของเรา (ชี้ขาด)", "ask_out": "เราขอรูปรถ",
               "ask_not": "ขอเอกสารคนซื้อ", "ad": "โฆษณารับซื้อ (ช่อง ADS)"},
     "desc": "แยกลีดรับซื้อรถ (ลูกค้าอยากขายรถให้เรา) ออกจากลีดขาย → แท็บ \"รับซื้อรถ\" ในห้องพัก Lead"},
    {"k": "buy_info", "name": "ใบเคสรับซื้อ — ข้อมูลรถลูกค้า", "sec": "status",
     "roles": {"mile": "ป้ายเลขไมล์", "mile_unit": "หน่วยระยะทาง", "plate": "ป้ายทะเบียน", "reason": "เหตุผลที่ขาย",
               "cond": "สภาพรถ/ประวัติ", "price": "ราคาที่อยากได้", "loan": "ไฟแนนซ์/เล่ม"},
     "desc": "ลีดรับซื้อ → ใบเคสรับซื้อ (โค้ด : OC-) · เลขไมล์/ทะเบียนจับตัวเลขหลังป้าย · "
             "ข้อความลูกค้าที่มีคำในหมวดเหตุผล/สภาพ/ราคา/ไฟแนนซ์ ลงช่อง \"ขายเพราะ\" / \"เพิ่มเติม\" ด้วยคำของลูกค้าเอง"},
    {"k": "contact", "name": "ไอดีไลน์", "sec": "contact", "roles": {"label": "ป้ายไอดีไลน์", "ask": "เราขอไอดี/ไลน์"},
     "desc": "คำที่บอกว่าข้างหน้า/ข้างหลังคือไอดีไลน์ (เบอร์โทร 9–10 หลัก จับเองไม่ต้องตั้ง)"},
    {"k": "guard", "name": "คำกันจับผิด", "sec": "guard",
     "roles": {"neg": "คำปฏิเสธ", "rel": "ญาติ/คนค้ำ", "past": "อดีต", "want": "ความอยาก", "occ_stop": "คำหยุดอาชีพ"},
     "desc": "บริบทรอบคำ — ใช้กันไม่ให้จับผิด (\"ไม่ติดบูโร\" · \"แฟนเป็นทหาร\" · \"ตอนเป็นทหาร\" · \"อยากผ่อนกระบะ\")"},
    {"k": "custom", "name": "กฎแท็กของเรา", "sec": "custom", "tag": True,
     "desc": "แท็กอะไรก็ได้ที่อยากรู้จากแชท เช่น ลูกค้าถามเรื่องดาวน์ → แท็ก \"ถามดาวน์\""},
]
GROUP = {g["k"]: g for g in GROUPS}
TAG_GROUPS = tuple(g["k"] for g in GROUPS if g.get("tag"))
STATE_GROUPS = ("income_band", "cust_type", "status", "pay")   # แท็กจากช่องข้อมูลลูกค้า (เปลี่ยนตามค่าปัจจุบัน)
LATIN_END = {"brand"}                   # หมวดที่คำอังกฤษต้องจบคำด้วย (เดิม _BRAND_EN มี (?![a-z]))
FIELDS = ("key", "group", "name", "value", "parent", "words", "pattern", "not_words", "extra", "tag", "active",
          "order", "system", "edited", "updated_by", "updated_at")

_C = {"at": 0.0, "ver": None, "rows": None, "src": "", "cache": {}}
_LOCK = threading.Lock()
_HOOKS = []


def on_change(fn):
    """ฟังก์ชันที่ต้องล้างของที่จำไว้เมื่อคำเปลี่ยน (เช่น lru_cache ของ lead_keywords)"""
    if fn not in _HOOKS:
        _HOOKS.append(fn)
    return fn


def defaults() -> list:
    from .kw_defaults import default_rows
    return [dict(r, edited=False, updated_by="", updated_at=None) for r in default_rows()]


def _read_ver():
    try:
        from dashboard.services import cache_store
        raw = cache_store.get_kv(VER_KEY) or {}
        d = raw.get("data") if isinstance(raw, dict) and "data" in raw else raw
        return str((d or {}).get("v") or "")
    except Exception:
        return None


def _db_rows():
    from .models import KeywordRule
    return [{f: getattr(r, f) for f in FIELDS} for r in KeywordRule.objects.all().order_by("group", "order", "id")]


def _load(force: bool = False) -> list:
    now = time.time()
    if not force and _C["rows"] is not None and now - _C["at"] < CHECK_SEC:
        return _C["rows"]
    ver = None if force else _read_ver()
    if not force and _C["rows"] is not None and (ver is None or ver == _C["ver"]) and _C["src"] == "db":
        _C["at"] = now
        return _C["rows"]
    try:
        rows, src = _db_rows(), "db"
        if not rows:
            rows, src = defaults(), "defaults"
    except Exception:
        rows, src = defaults(), "defaults"
    if ver is None:
        ver = _read_ver()
    with _LOCK:
        _C.update(at=now, ver=ver, rows=rows, src=src, cache={})
    for fn in list(_HOOKS):
        try:
            fn()
        except Exception:
            pass
    return rows


def source() -> str:
    _load()
    return _C["src"]


def bump(by: str = ""):
    """มีคนแก้คำ → ทุก worker โหลดใหม่ (รอบเช็คถัดไป) · worker นี้โหลดใหม่ทันที"""
    try:
        from django.utils import timezone

        from dashboard.services import cache_store
        cache_store.set_kv(VER_KEY, {"v": uuid.uuid4().hex, "by": (by or "")[:80],
                                     "at": timezone.now().isoformat(timespec="seconds")})
    except Exception:
        pass
    _load(force=True)


def all_rows() -> list:
    return list(_load())


def rows(group: str, role: str | None = None, active: bool = True) -> list:
    out = [r for r in _load() if r["group"] == group and (r["active"] or not active)]
    if role is not None:
        out = [r for r in out if r["value"] == role]
    return out


# ── แปลงแถว → regex ───────────────────────────────────────────────────────────

def nw(w) -> str:
    """คำที่คนพิมพ์ → รูปที่ใช้เทียบ (ตัวเล็ก · ยุบช่องว่าง · ล้างคำพิมพ์ไทยแบบเดียวกับข้อความ)"""
    t = str(w or "").replace("เเ", "แ").replace("ํา", "ำ")
    return re.sub(r"\s+", " ", t).strip().lower()


def _latin(w: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9 .&+\-/:]+", w))


def word_rx(w: str, latin_end: bool = False) -> str:
    w = nw(w)
    e = re.escape(w).replace("\\ ", r"\s*")
    if _latin(w) and re.match(r"[a-z0-9]", w):
        e = r"(?<![a-z0-9])" + e + (r"(?![a-z])" if latin_end else "")
    return e


def row_alt(r: dict) -> str:
    """แถว → alternation (ไม่ครอบวงเล็บ — แถวที่มีแต่รูปแบบเดิม = regex เดิมตรงตัวอักษร)"""
    parts = []
    if (r.get("pattern") or "").strip():
        parts.append(r["pattern"])
    ws = sorted({nw(w) for w in r.get("words") or [] if nw(w)}, key=len, reverse=True)
    parts += [word_rx(w, r.get("group") in LATIN_END) for w in ws]
    return "|".join(parts)


def _compile(alt: str, wrap: str, flags: int):
    return re.compile(wrap.replace("{}", alt) if alt else NEVER, flags)


def rx(group: str, role: str | None = None, wrap: str = "{}", flags: int = 0):
    """ทุกแถว (ที่เปิด) ของหมวด/บทบาท รวมเป็น regex เดียว · จำไว้จนกว่าคำจะเปลี่ยน"""
    _load()
    k = ("rx", group, role, wrap, flags)
    c = _C["cache"]
    if k not in c:
        alt = "|".join(a for a in (row_alt(r) for r in rows(group, role)) if a)
        try:
            c[k] = _compile(alt, wrap, flags)
        except re.error:                          # มีแถวที่ regex พัง (ไม่น่าเกิด — ตรวจตอนบันทึกแล้ว) → ค่าตั้งต้น
            alt = "|".join(a for a in (row_alt(r) for r in defaults()
                                       if r["group"] == group and (role is None or r["value"] == role)) if a)
            c[k] = _compile(alt, wrap, flags)
    return c[k]


def row_list(group: str, role: str | None = None, flags: int = 0) -> list:
    """[(แถว, regex)] ทีละแถวตามลำดับ (อาชีพ/ประวัติผ่อน/สถานะ — ลำดับมีผล) · แถวที่ไม่มีคำ/regex พัง = ข้าม"""
    _load()
    k = ("list", group, role, flags)
    c = _C["cache"]
    if k not in c:
        out = []
        for r in rows(group, role):
            a = row_alt(r)
            if not a:
                continue
            try:
                out.append((r, re.compile(a, flags)))
            except re.error:
                continue
        c[k] = out
    return c[k]


def cached(name: str, fn):
    """ของที่คำนวณจากแถว (จำไว้จนกว่าคำจะเปลี่ยน)"""
    _load()
    c = _C["cache"]
    k = ("x", name)
    if k not in c:
        c[k] = fn()
    return c[k]


# ── รถ ─────────────────────────────────────────────────────────────────────────

def th_fold(s: str) -> str:
    """ภาษาไทยพิมพ์ได้หลายแบบ — ตัดตัวการันต์ + วรรณยุกต์ + ู→ุ (ตัวเดียวกับ leadgroup.th_fold)"""
    s = re.sub(r"[ก-ฮ]์", "", s or "")
    s = re.sub(r"[่-์]", "", s)
    return s.replace("ู", "ุ")


def th_model() -> dict:
    """คำไทยของรุ่นรถ → ค่าอังกฤษ (เดิม leadgroup._TH_MODEL) · `keys` ยาวก่อน · `fold` = แบบพับ (≥5 ตัว)"""
    def build():
        mp = {}
        for r in rows("model"):
            for w in r.get("words") or []:
                w2 = str(w or "").lower().strip()
                if w2 and re.search(r"[ก-๙]", w2) and w2 not in mp:
                    mp[w2] = r.get("value") or nw(r.get("name"))
        keys = sorted(mp, key=len, reverse=True)
        fold = sorted({(th_fold(k), v) for k, v in mp.items() if len(th_fold(k)) >= 5}, key=lambda x: len(x[0]), reverse=True)
        return {"map": mp, "keys": keys, "fold": fold}
    return cached("th_model", build)


def brands_in(text: str) -> list:
    """[(แถวยี่ห้อ, ตำแหน่ง, คำที่จับได้)] เรียงตามตำแหน่งในข้อความ"""
    low = str(text or "").lower()
    out = []
    for r, rx_ in row_list("brand"):
        m = rx_.search(low)
        if m:
            out.append((r, m.start(), m.group(0)))
    out.sort(key=lambda x: x[1])
    return out


def models_in(text: str) -> list:
    """[(แถวรุ่น, คำที่จับได้)] — คำยาวชนะ ("yaris ativ" ไม่นับ "yaris" ซ้อนข้างใน) · แบบพับใช้กับคำไทย ≥5 ตัว"""
    low = str(text or "").lower()
    if not low.strip():
        return []
    spans = []
    for r, rx_ in row_list("model"):
        for m in rx_.finditer(low):
            if m.end() > m.start():
                spans.append((m.start(), m.end(), r, m.group(0)))
    spans.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    keep, seen, touched = [], set(), set()
    for s, e, r, w in spans:
        touched.add(r["key"])
        if any(s >= ks and e <= ke and (e - s) < (ke - ks) for ks, ke, _r, _w in keep):
            continue
        if r["key"] in seen:
            continue
        keep.append((s, e, r, w))
        seen.add(r["key"])
    fl = th_fold(low)
    longest = [th_fold(w) for _s, _e, _r, w in keep]
    for r in rows("model"):
        if r["key"] in touched:
            continue
        for w in r.get("words") or []:
            f = th_fold(str(w or "").lower())
            if len(f) >= 5 and re.search(r"[ก-๙]", f) and f in fl and not any(f in x and f != x for x in longest):
                keep.append((fl.find(f), 0, r, w))
                seen.add(r["key"])
                break
    return [(r, w) for _s, _e, r, w in keep]


# ── ตรวจ/บันทึก (หน้าเว็บ) ──────────────────────────────────────────────────────

def split_words(v) -> list:
    if isinstance(v, (list, tuple)):
        parts = [str(x) for x in v]
    else:
        parts = re.split(r"[\n,]+", str(v or ""))
    out, seen = [], set()
    for p in parts:
        w = re.sub(r"\s+", " ", p).strip()
        if w and nw(w) not in seen:
            seen.add(nw(w))
            out.append(w)
    return out


def _int(v):
    if v in (None, ""):
        return None
    try:
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return "bad"


def clean(data: dict, cur: dict | None = None) -> tuple:
    """ข้อมูลจากหน้าเว็บ → (แถว, "") หรือ (None, บอกว่าผิดตรงไหน) · `cur` = แถวเดิม (แก้)"""
    d = dict(data or {})
    group = (cur or {}).get("group") or str(d.get("group") or "")
    g = GROUP.get(group)
    if not g:
        return None, "ไม่รู้จักหมวดนี้"
    name = re.sub(r"\s+", " ", str(d.get("name") if d.get("name") is not None else (cur or {}).get("name") or "")).strip()
    if not name:
        return None, "ใส่ชื่อก่อน"
    if len(name) > NAME_LEN:
        return None, "ชื่อยาวเกิน %d ตัวอักษร" % NAME_LEN
    words = split_words(d.get("words") if "words" in d else (cur or {}).get("words"))
    nots = split_words(d.get("not_words") if "not_words" in d else (cur or {}).get("not_words"))
    if len(words) > WORDS_MAX or len(nots) > WORDS_MAX:
        return None, "ใส่คำได้ไม่เกิน %d คำต่อช่อง" % WORDS_MAX
    for w in words + nots:
        if len(nw(w).replace(" ", "")) < WORD_MIN:
            return None, "คำ \"%s\" สั้นเกินไป (อย่างน้อย %d ตัวอักษร) — จะไปจับกลางคำอื่นทั้งแชท" % (w, WORD_MIN)
        if len(w) > WORD_LEN:
            return None, "คำ \"%s…\" ยาวเกิน %d ตัวอักษร" % (w[:20], WORD_LEN)
    pattern = str(d.get("pattern") if "pattern" in d else (cur or {}).get("pattern") or "").strip()
    if len(pattern) > PATTERN_MAX:
        return None, "รูปแบบขั้นสูงยาวเกินไป"
    row = dict(cur or {}, group=group, name=name, words=words, not_words=nots, pattern=pattern)
    alt = row_alt(row)
    if alt:
        try:
            c = re.compile(alt)
        except re.error as e:
            return None, "รูปแบบขั้นสูงเขียนผิด: %s" % e
        if c.search("") is not None or c.search(" ") is not None:
            return None, "รูปแบบนี้จับข้อความว่างได้ — จะติดทุกแชท แก้ให้ต้องมีตัวอักษรก่อน"
    extra = dict((cur or {}).get("extra") or {})
    extra.update({k: v for k, v in (d.get("extra") or {}).items()})
    value = str(d.get("value") if "value" in d else (cur or {}).get("value") or "").strip()[:120]
    parent = str(d.get("parent") if "parent" in d else (cur or {}).get("parent") or "").strip()[:60]
    roles = g.get("roles") or {}
    if roles and value not in roles:
        return None, "เลือกบทบาทของแถวนี้ (%s)" % " / ".join(roles.values())
    if group == "income_band":
        lo, hi = _int(extra.get("min")), _int(extra.get("max"))
        if lo == "bad" or hi == "bad" or lo is None or lo < 0:
            return None, "ช่วงรายได้: ใส่ตัวเลข \"ตั้งแต่\" (บาท/เดือน)"
        if hi is not None and hi <= lo:
            return None, "ช่วงรายได้: \"ถึง\" ต้องมากกว่า \"ตั้งแต่\" (ไม่มีเพดาน = เว้นว่าง)"
        extra.update(min=lo, max=hi)
    elif not alt and group not in ("cust_type",):
        return None, "ใส่คำที่จะจับอย่างน้อย 1 คำ"
    if group == "model":
        brands = {r["name"] for r in rows("brand", active=False)}
        if parent not in brands:
            return None, "เลือกยี่ห้อของรุ่นนี้"
        value = value or nw(name)
    if group == "brand":
        value = value or re.sub(r"[^a-z0-9]", "", nw(name)) or nw(name)
    if group == "occupation":
        types = {r["value"] for r in rows("cust_type", active=False)}
        if parent and parent not in types:
            return None, "เลือกประเภทลูกค้าของอาชีพนี้"
    if group in ("pay", "status"):
        value = value or name
    if group == "status":
        extra["check"] = bool(extra.get("check", True))
        extra["spell"] = split_words(extra.get("spell")) or [value]
    if group == "pay":
        extra["neg"] = str(extra.get("neg") or "")[:60]
        extra["always"] = bool(extra.get("always"))
    if group == "cust_type":
        extra["spell"] = split_words(extra.get("spell")) or [name]
    if group == "custom":
        sc = str(extra.get("scope") or "in")
        extra["scope"] = sc if sc in ("in", "all") else "in"
    tag = bool(d.get("tag")) if "tag" in d else bool((cur or {}).get("tag", group in ("brand", "model", "income_band", "custom")))
    if not g.get("tag"):
        tag = False
    if group == "custom":
        tag = True
    if tag:
        clash = [r for r in all_rows() if r.get("tag") and r["group"] in TAG_GROUPS and r["key"] != (cur or {}).get("key")
                 and nw(r["name"]) == nw(name)]
        if clash:
            return None, "ชื่อแท็ก \"%s\" ซ้ำกับ %s — ตั้งชื่ออื่น" % (name, GROUP[clash[0]["group"]]["name"])
    active = bool(d.get("active")) if "active" in d else bool((cur or {}).get("active", True))
    row.update(value=value, parent=parent, extra=extra, tag=tag, active=active)
    return row, ""


def save(data: dict, by: str = "") -> tuple:
    """เพิ่ม (ไม่มี key) / แก้ (มี key) → (ok, ข้อความ, แถว)"""
    from .models import KeywordRule
    key = str((data or {}).get("key") or "").strip()
    obj = KeywordRule.objects.filter(key=key).first() if key else None
    if key and not obj:
        return False, "ไม่พบแถวนี้ (อาจถูกลบไปแล้ว)", None
    cur = {f: getattr(obj, f) for f in FIELDS} if obj else None
    row, err = clean(data, cur)
    if err:
        return False, err, None
    if not obj:
        if KeywordRule.objects.filter(group=row["group"]).count() >= GROUP_MAX:
            return False, "หมวดนี้มีครบ %d แถวแล้ว" % GROUP_MAX, None
        last = KeywordRule.objects.filter(group=row["group"]).order_by("-order").values_list("order", flat=True).first()
        k = ("c-" if row["group"] == "custom" else row["group"] + ":u-") + uuid.uuid4().hex[:10]
        obj = KeywordRule(key=k, group=row["group"], order=(last or 0) + 1, system=False)
    for f in ("name", "value", "parent", "words", "pattern", "not_words", "extra", "tag", "active"):
        setattr(obj, f, row[f])
    if obj.system:
        obj.edited = True
    obj.updated_by = (by or "")[:80]
    obj.save()
    bump(by)
    out = {f: getattr(obj, f) for f in FIELDS}
    return True, "บันทึก \"%s\" แล้ว" % obj.name, out


def toggle(key: str, field: str, on: bool, by: str = "") -> tuple:
    from .models import KeywordRule
    obj = KeywordRule.objects.filter(key=str(key or "")).first()
    if not obj:
        return False, "ไม่พบแถวนี้ (อาจถูกลบไปแล้ว)", None
    if field not in ("active", "tag"):
        return False, "ไม่รู้จักคำสั่งนี้", None
    if field == "tag":
        if not GROUP.get(obj.group, {}).get("tag"):
            return False, "หมวดนี้ไม่ติดแท็ก", None
        if obj.group == "custom" and not on:
            return False, "กฎแท็กของเรา ปิดด้วยปุ่มเปิด/ปิดกฎแทน", None
        if on:
            clash = [r for r in all_rows() if r.get("tag") and r["key"] != obj.key and nw(r["name"]) == nw(obj.name)]
            if clash:
                return False, "ชื่อแท็ก \"%s\" ซ้ำกับแถวอื่น — เปลี่ยนชื่อก่อน" % obj.name, None
    setattr(obj, field, bool(on))
    if obj.system:
        obj.edited = True
    obj.updated_by = (by or "")[:80]
    obj.save(update_fields=[field, "edited", "updated_by", "updated_at"])
    bump(by)
    word = {"active": ("เปิด", "ปิด"), "tag": ("ติดแท็ก", "ไม่ติดแท็ก")}[field]
    return True, "%s \"%s\" แล้ว" % (word[0] if on else word[1], obj.name), {f: getattr(obj, f) for f in FIELDS}


def delete(key: str, by: str = "") -> tuple:
    from .models import KeywordRule
    obj = KeywordRule.objects.filter(key=str(key or "")).first()
    if not obj:
        return False, "ไม่พบแถวนี้ (อาจถูกลบไปแล้ว)"
    if obj.system:
        return False, "แถวของระบบลบไม่ได้ — ปิดใช้ หรือกด \"คืนค่าเดิม\" แทน"
    name = obj.name
    obj.delete()
    bump(by)
    return True, "ลบ \"%s\" แล้ว" % name


def reset(key: str, by: str = "") -> tuple:
    """แถวของระบบที่มีคนแก้ → คืนค่าตั้งต้น"""
    from .models import KeywordRule
    obj = KeywordRule.objects.filter(key=str(key or "")).first()
    d = next((r for r in defaults() if r["key"] == str(key or "")), None)
    if not obj or not d:
        return False, "แถวนี้ไม่มีค่าตั้งต้นของระบบ"
    for f in ("name", "value", "parent", "words", "pattern", "not_words", "extra", "tag", "active", "order"):
        setattr(obj, f, d[f])
    obj.edited = False
    obj.updated_by = (by or "")[:80]
    obj.save()
    bump(by)
    return True, "คืนค่าเดิมของ \"%s\" แล้ว" % obj.name


def sync_defaults(model=None, apply: bool = True) -> dict:
    """เติมแถวของระบบที่ยังไม่มีในตาราง + อัปเดตแถวของระบบที่ยังไม่มีใครแก้ ให้ตรงค่าตั้งต้นล่าสุด
    (`model` = model ของ migration · ไม่ใส่ = ของจริง)"""
    if model is None:
        from .models import KeywordRule as model
    have = {o.key: o for o in model.objects.all()}
    added = updated = 0
    for d in defaults():
        o = have.get(d["key"])
        if o is None:
            added += 1
            if apply:
                model.objects.create(**{f: d[f] for f in ("key", "group", "name", "value", "parent", "words", "pattern",
                                                         "not_words", "extra", "tag", "active", "order", "system")})
            continue
        if o.edited:
            continue
        ch = [f for f in ("name", "value", "parent", "words", "pattern", "extra", "order") if getattr(o, f) != d[f]]
        if ch:
            updated += 1
            if apply:
                for f in ch:
                    setattr(o, f, d[f])
                o.save()
    return {"added": added, "updated": updated}


# ── แสดงผลในหน้าเว็บ ─────────────────────────────────────────────────────────────

def _split_top(p: str) -> list:
    """แยก regex ที่ | ระดับบนสุด (ไม่แยกในวงเล็บ/วงเล็บเหลี่ยม)"""
    out, depth, cls, esc, cur = [], 0, False, False, ""
    for ch in p:
        if esc:
            cur += ch
            esc = False
            continue
        if ch == "\\":
            cur += ch
            esc = True
            continue
        if cls:
            cls = ch != "]"
            cur += ch
            continue
        if ch == "[":
            cls = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "|" and depth == 0:
            out.append(cur)
            cur = ""
            continue
        cur += ch
    out.append(cur)
    return out


def readable(p: str, n: int = 40) -> list:
    """regex → คำอ่านง่าย (ประมาณ — ไว้แสดงผล ไม่ได้ใช้จับ)"""
    out = []
    for a in _split_top(p or ""):
        t = re.sub(r"\(\?<?[=!](?:[^()]|\([^()]*\))*\)", "", a)          # ตัด lookaround
        t = re.sub(r"\\[sS][*+?]?|\\s\{[^}]*\}", " ", t)
        t = re.sub(r"\[[^\]]*\](?:\{[^}]*\}|[*+?])?", "…", t)
        t = re.sub(r"\\S\{[^}]*\}|\\d[*+?]?|\\S[*+?]?", "…", t)
        t = re.sub(r"\{\d*,?\d*\}", "", t)
        t = t.replace("(?:", "(")
        for _ in range(4):
            t = re.sub(r"\(([^()]*)\)\?", r"[\1]", t)
            t = re.sub(r"\(([^()|]*)\)", r"\1", t)
            t = re.sub(r"\(([^()]*\|[^()]*)\)", lambda m: "(" + m.group(1).replace("|", "/") + ")", t)
        t = re.sub(r"(.)\?", r"\1", t)
        t = t.replace("\\.", ".").replace("\\", "").replace("^", "").replace("$", "")
        t = re.sub(r"\s+", " ", t).strip()
        if t and t not in out:
            out.append(t)
        if len(out) >= n:
            break
    return out


def row_json(r: dict) -> dict:
    d = {f: r.get(f) for f in FIELDS}
    d["updated_at"] = r["updated_at"].isoformat(timespec="seconds") if hasattr(r.get("updated_at"), "isoformat") else ""
    d["readable"] = readable(r.get("pattern") or "")
    return d
