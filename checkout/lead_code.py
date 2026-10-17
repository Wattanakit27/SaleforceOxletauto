# -*- coding: utf-8 -*-
"""ตัวหน้าเลขลีดอัตโนมัติ (★ 17 ต.ค.69 · เจ้าของสั่ง "run code auto")

ตอนจ่ายเบอร์ให้ระบบเลือกตัวหน้า LD / NLD / BLD / WLD / HLD เอง จากข้อมูลที่ลูกค้าให้ในแชท
(+ ช่องข้อมูลลีดที่ระบบ/แอดมินเติมไว้) — **ไม่ใช้ AI** · ทุกการตัดสินบอกได้ว่าจับจากคำไหน แอดมินแก้ได้เสมอ

เกณฑ์ของเจ้าของ (ข้อความเดิม 17 ต.ค.69 — แก้เกณฑ์ที่นี่ที่เดียว):
  Moderate
    LD  = ให้ข้อมูล แต่เครดิตอ่อน · เงินเดือนน้อย · อายุงานไม่ถึงปี · ไม่มีผ่อน
    NLD = ให้เบอร์แต่ไม่ให้ข้อมูล · มีรถมาเทิร์นไม่ทราบโปรไฟล์ · ให้เช็คราคารถเทิร์นก่อน · จะเข้าร้านแต่ไม่แจ้งวัน
    BLD = โยนเบอร์ไม่ให้ข้อมูล + รถราคาต่ำ (ไม่เกิน 3 แสน) เสี่ยงติดแบล็คลิส
  Hot (WLD)
    อายุงาน/ประวัติผ่อนเกิน 1 ปี + เอกสารรายได้ แต่ให้มาแค่ไอดีไลน์ ไม่ให้เบอร์ · จะเข้ามาดูรถที่ร้าน (บอกวัน) ·
    มีรถมาเทิร์น โปรไฟล์ดี · อายุงานเกิน 1 ปี หรือ ประวัติผ่อนเกิน 1 ปี
  Very Hot (HLD)
    ซื้อสด แจ้งราคารถแล้ว/งบเหมาะกับรถที่มี · อายุงาน/ประวัติผ่อนเกิน 1 ปี + เอกสารรายได้ ·
    จัดไฟแนนซ์ผ่านแล้ว / ไปเซ็นที่อื่นผ่านแล้วแต่ไม่ได้รับรถ

ค่าที่ผมตั้งเอง (เจ้าของไม่ได้ระบุ — ตกลงตามที่เสนอ): เงินเดือนน้อย = ต่ำกว่า `LOW_INCOME` · ราคารถ = รถพร้อมขาย
ในสต็อกที่ตรงรุ่นที่ลูกค้าถาม (ไม่มี = งบที่ลูกค้าบอก) · HLD จากโปรไฟล์ต้องมี "อายุงานหรือผ่อน ≥1 ปี **และ** เอกสาร" ·
เอกสาร = จับจากคำในแชท + แอดมินติ๊กเองได้ (`DOC_KEY`) · เข้าหลายระดับ = ใช้ระดับสูงสุด · BLD เฉพาะตอนไม่มีข้อมูลเลย
**R ไม่ออกอัตโนมัติ** — เจ้าของยืนยันว่า R = ส่งต่อเคสให้ไม้ 2 (หรือแอดมิน) ไม่ใช่ลีดใหม่ (ใช้ "ส่งต่อไม้ 2")
"""
from __future__ import annotations

import re
import time

from django.utils import timezone

from . import lead_keywords as LK

LOW_INCOME = 15000
LOW_PRICE = 300000
STRONG_MONTHS = 12
DOC_KEY = "_doc"                 # ChatLead.auto[...] = {on, by, at} · แอดมินติ๊ก "มีเอกสารยืนยันรายได้" (ชนะคำในแชท)
_RANK = {"HLD": 4, "WLD": 3, "LD": 2, "BLD": 1, "NLD": 0}
LABEL = {"HLD": "Very Hot", "WLD": "Hot", "LD": "Moderate", "BLD": "BLD", "NLD": "Moderate"}

# ── ระยะเวลา → เดือน ──
_NUM_TH = {"หนึ่ง": 1, "สอง": 2, "สาม": 3, "สี่": 4, "ห้า": 5, "หก": 6, "เจ็ด": 7, "แปด": 8, "เก้า": 9, "สิบ": 10}


def _n(s):
    s = (s or "").strip()
    if s in _NUM_TH:
        return float(_NUM_TH[s])
    try:
        return float(re.split(r"\s*[-–]\s*", s)[0])
    except ValueError:
        return None


def months(text: str):
    """'2 ปี' → 24 · '1 ปี 6 เดือน' → 18 · '8 เดือน' → 8 · '1 ปีกว่า' → 13 · 'ไม่ถึง 1 ปี' → 11 · 'หลายปี' → 36
    อ่านไม่ออก = None (ไม่เดา)"""
    t = (text or "").strip()
    if not t:
        return None
    if "หลายปี" in t:
        return 36
    total, got = 0, False
    y = re.search(r"(\d+(?:\.\d+)?(?:\s*[-–]\s*\d+)?|หนึ่ง|สอง|สาม|สี่|ห้า|หก|เจ็ด|แปด|เก้า|สิบ)\s*ปี", t)
    if y and _n(y.group(1)) is not None:
        total += round(_n(y.group(1)) * 12)
        got = True
    m = re.search(r"(\d+|หนึ่ง|สอง|สาม|สี่|ห้า|หก|เจ็ด|แปด|เก้า|สิบ)\s*เดือน", t)
    if m and _n(m.group(1)) is not None:
        total += int(_n(m.group(1)))
        got = True
    if not got:
        return None
    if "กว่า" in t:
        total += 1
    if "ไม่ถึง" in t:
        total -= 1
    return max(total, 0)


def money(text: str):
    """'22,000' / '15000' / '1.5 หมื่น' / '2 หมื่น' / '15k' → บาท · อ่านไม่ออก = None"""
    t = (text or "").replace(" ", "")
    m = re.search(r"(\d+(?:[.,]\d+)*)(หมื่น|แสน|k|K)?", t)
    if not m:
        return None
    tok, unit = m.group(1), m.group(2) or ""
    try:
        v = float(tok.replace(",", ""))
    except ValueError:
        return None
    v *= {"หมื่น": 10000, "แสน": 100000, "k": 1000, "K": 1000}.get(unit, 1)
    return int(v)


# ── คำในแชท ──
_DOC = re.compile(r"สลิป\s*เงินเดือน|สลิปเงิน(?!\s*โอน)|ใบ\s*รับรอง\s*(?:เงินเดือน|รายได้|การทำงาน)|"
                  r"หนังสือ\s*รับรอง\s*(?:เงินเดือน|รายได้|การทำงาน)|statement|สเตท\s*เม้?น|เดินบัญชี|ทวิ\s*50|50\s*ทวิ|"
                  r"(?:มี|ส่ง|แนบ|ถ่าย)\s*สลิป(?!\s*โอน)")
_CASH = re.compile(r"(?:ซื้อ|จ่าย|ชำระ|โอน)\s*(?:เป็น)?\s*(?:เงิน)?สด|เงินสด|(?<![a-z])cash(?![a-z])")   # "ไม่พอ" ดู _CASH_BAD
_CASH_BAD = re.compile(r"(?:เงินสด|ซื้อสด|จ่ายสด)\s*(?:ไม่พอ|ไม่ไหว|ไม่ถึง|มีไม่พอ|เงินไม่พอ)")
_FIN_OK = re.compile(r"(?:ไฟแนน(?:ซ์|ส์)?|ยื่น(?:กู้)?|สินเชื่อ|เครดิต|บูโร|เซ็น(?:สัญญา)?|ธนาคาร|แบงค์)[ก-๙a-z\s]{0,20}?"
                     r"(?<!ไม่)(?<!รอ)(?<!ลุ้น)(?<!จะ)(?<!ถ้า)(?<!ให้)(?:ผ่าน|อนุมัติ)"
                     r"(?!\s*(?:ไหม|มั้ย|มัย|ป่าว|หรือ|รึ|ยัง|\?))|อนุมัติแล้ว")
_TRADE_PRICE = re.compile(r"(?:ประเมิน|ตี|เช็ค|เช็ก|ดู)\s*ราคา\s*รถ\s*(?:เก่า|คันเก่า|เทิร์น|เทริน|ของ(?:ผม|หนู|ฉัน|เรา))|"
                          r"รถ\s*(?:เก่า|คันเก่า)[ก-๙a-z\s]{0,12}ได้\s*(?:ราคา)?\s*เท่า(?:ไหร่|ไร)|ประเมินรถ")
_TRADE = re.compile(r"เทิร์น|เทริน|trade\s*-?\s*in|เอารถ(?:เก่า|คันเก่า)?มา(?:แลก|เทิร์น)|มีรถ(?:เก่า)?(?:มา)?แลก")
_VISIT = re.compile(r"(?:(?:เข้า|แวะ)\s*(?:ไป|มา)?|ไป|มา)\s*ดู\s*(?:รถ|คันจริง|ของจริง)(?!\s*(?:แล้ว|มาแล้ว))|"
                    r"นัด\s*ดู\s*รถ|(?:เข้า|แวะ)\s*(?:ไป|มา)\s*(?:ที่)?\s*(?:ร้าน|เต็นท์|โชว์รูม)")
_PAY_DUR = [re.compile(r"(?:ผ่อน|ส่ง\s*(?:ค่า)?งวด|จ่าย\s*(?:ค่า)?งวด)[ก-๙a-z\s]{0,15}?(?:มา(?:ได้|แล้ว)?|ไปแล้ว)\s*"
                       r"(?:ประมาณ|ราวๆ|เกือบ|ได้|แล้ว)*\s*" + LK._DUR),
            re.compile(r"(?:ผ่อน|ส่ง\s*(?:ค่า)?งวด)[ก-๙a-z\s]{0,15}?\s" + LK._DUR + r"\s*แล้ว")]
_QUOTE = re.compile(r"(?:ราคา|ขาย|เหลือ|พิเศษ|เพียง|สด)[^\n]{0,15}?(\d{1,3}(?:,\d{3})+|\d{5,7}|\d+(?:\.\d+)?\s*(?:แสน|ล้าน))")
_BUDGET = re.compile(r"(?:งบ|เงินสด|มีเงิน|มีสด|ซื้อสด)\s*(?:ประมาณ|ราวๆ|อยู่|ที่|ไม่เกิน|ไม่ถึง)?\s*"
                     r"(\d{1,3}(?:,\d{3})+|\d{5,7}|\d+(?:\.\d+)?\s*(?:แสน|ล้าน))")
_WEAK = ("ไม่มีเครดิต", "เครดิตเกิดใหม่", "ติดแบล็คลิสต์", "ติดบูโร", "เครดิตไม่ดี", "เคยยื่นไฟแนนซ์ไม่ผ่าน",
         "เคยค้างชำระ", "เคยคืนรถ/โดนยึด")


def _baht(tok: str) -> int:
    t = (tok or "").replace(" ", "")
    m = re.match(r"(\d+(?:\.\d+)?)(แสน|ล้าน)", t)
    if m:
        return int(float(m.group(1)) * (100000 if m.group(2) == "แสน" else 1000000))
    try:
        return int(t.replace(",", ""))
    except ValueError:
        return 0


def _clip(s, n=36):
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[:n - 1] + "…"


def _find(rx, texts, neg=True):
    """คำแรกที่จับได้ (ข้อความล่าสุดก่อน) → คำนั้น · ข้าม "ไม่…" / ของญาติ"""
    for raw in reversed(texts or []):
        t = LK.norm(raw)
        for m in rx.finditer(t):
            if neg and LK._negated(t, m.start()):
                continue
            if LK._REL.search(t[max(0, m.start() - 10):m.start()]):
                continue
            return _clip(m.group(0))
    return ""


def pay_months(texts) -> tuple:
    """ประวัติผ่อนกี่เดือน (จากประโยคแบบ "ผ่อนรถมา 2 ปี" · "ส่งงวดมาแล้ว 18 เดือน") → (เดือน, คำ) · ไม่เจอ = (None, "")
    "อยากผ่อน 4 ปี" (ระยะผ่อนรถคันใหม่) ไม่นับ — ต้องมี มา/ไปแล้ว/…แล้ว"""
    best = (None, "")
    for raw in texts or []:
        t = LK.norm(raw)
        for rx in _PAY_DUR:
            for m in rx.finditer(t):
                if LK._WANT.search(t[max(0, m.start() - 6):m.start()]) or LK._REL.search(t[max(0, m.start() - 10):m.start()]):
                    continue
                mo = months(LK._fmt_dur(m))
                if mo is not None and (best[0] is None or mo > best[0]):
                    best = (mo, _clip(m.group(0)))
    return best


# ── ราคารถที่ลูกค้าถาม (รถพร้อมขายในสต็อก) ──
_STOCK = {"at": 0.0, "rows": []}


def _stock():
    if time.time() - _STOCK["at"] > 300:
        try:
            from .need_match import _stock as load
            _STOCK["rows"] = load()
        except Exception:
            _STOCK["rows"] = []
        _STOCK["at"] = time.time()
    return _STOCK["rows"]


def car_prices(car_text: str) -> list:
    """ราคารถพร้อมขายที่ตรงรุ่น (ต้องตรงชื่อรุ่น ไม่ใช่แค่ยี่ห้อ — กติกาเดียวกับ need_match)"""
    from .need_match import _tokens
    model_w, brand_w = _tokens(car_text or "")
    if not model_w:
        return []
    out = []
    for c in _stock():
        if not c.get("price") or not any(w in c["key"] for w in model_w):
            continue
        if brand_w and not any(b in c["key"] for b in brand_w):
            continue
        out.append(c["price"])
    return sorted(out)


# ── ตัดสิน ──
def decide(lead, texts_in=(), texts_out=(), visit_date: str = "", prices=None, doc_flag=None) -> dict:
    """ข้อมูลลีด + ข้อความลูกค้า (เก่า→ใหม่) + ข้อความของเรา → {base, label, why, reasons:[[ตัวหน้า, เหตุผล]]}
    ฟังก์ชันล้วน (ไม่แตะฐานข้อมูล) — เทสต์ได้ตรงๆ"""
    g = lambda k: (getattr(lead, k, "") or "").strip()
    notes = [g("fill_note"), g("admin_profile"), g("more")]
    texts = [t for t in list(texts_in or []) + notes if t]
    phone, line_id = g("phone"), g("line_id")
    R = {k: [] for k in _RANK}

    ten = months(g("job_tenure"))
    pay, pay_ev = pay_months(texts)
    hist = g("pay_history")
    if pay is None and "ผ่อนหมดแล้ว" in hist:
        pay, pay_ev = STRONG_MONTHS, "ผ่อนหมดแล้ว"
    strong = (ten is not None and ten >= STRONG_MONTHS) or (pay is not None and pay >= STRONG_MONTHS)
    strong_txt = " · ".join(x for x in (
        ("อายุงาน %s" % g("job_tenure")) if ten is not None and ten >= STRONG_MONTHS else "",
        ("ประวัติผ่อน \"%s\"" % pay_ev) if pay is not None and pay >= STRONG_MONTHS else "") if x)

    if doc_flag is None:
        doc_ev = _find(_DOC, texts)
        doc = bool(doc_ev)
    else:
        doc, doc_ev = bool(doc_flag), ("แอดมินติ๊กว่ามีเอกสารรายได้" if doc_flag else "")

    fin = _find(_FIN_OK, texts)
    cash = "" if _find(_CASH_BAD, texts, neg=False) else _find(_CASH, texts)
    quoted = _find(_QUOTE, list(texts_out or []), neg=False)
    budget = 0
    for raw in reversed(texts):
        m = _BUDGET.search(LK.norm(raw))
        if m:
            budget = _baht(m.group(1))
            break
    prices = list(prices or [])
    budget_fit = bool(budget) and (not prices or budget >= prices[0])

    # Very Hot
    if fin:
        R["HLD"].append("จัดไฟแนนซ์/เซ็นผ่านแล้ว (\"%s\")" % fin)
    if cash and (quoted or budget_fit):
        R["HLD"].append("ซื้อสด (\"%s\") + %s" % (cash, "แจ้งราคาแล้ว" if quoted else "งบ %s พอกับรถ" % "{:,}".format(budget)))
    elif cash:
        R["NLD"].append("ซื้อสด (\"%s\") แต่ยังไม่ได้แจ้งราคา/ไม่รู้งบ" % cash)
    if strong and doc:
        if phone:
            R["HLD"].append("%s + เอกสารรายได้ (\"%s\")" % (strong_txt, doc_ev))
        else:
            R["WLD"].append("%s + เอกสารรายได้ แต่ให้มาแค่ไอดีไลน์ ไม่ให้เบอร์" % strong_txt)
    # Hot
    if visit_date:
        R["WLD"].append("นัดเข้ามาดูรถ มีวันชัด (%s)" % visit_date)
    else:
        v = _find(_VISIT, texts) or ("รอมาดูรถ" if g("customer_status") == "รอมาดูรถ" else "")
        if v:
            R["NLD"].append("จะเข้ามาดูรถ แต่ยังไม่บอกวัน (\"%s\")" % v)
    trade = bool((getattr(lead, "auto", None) or {}).get("_trade")) or g("customer_status") == "มีรถเทริน" \
        or bool(_find(_TRADE, texts))
    if trade and strong:
        R["WLD"].append("มีรถมาเทิร์น + โปรไฟล์ดี (%s)" % strong_txt)
    elif strong and not doc:
        R["WLD"].append(strong_txt)
    elif trade and not strong:
        R["NLD"].append("มีรถมาเทิร์น แต่ยังไม่รู้โปรไฟล์")
    tp = _find(_TRADE_PRICE, texts)
    if tp:
        R["NLD"].append("ให้เช็คราคารถเทิร์นก่อน (\"%s\")" % tp)

    # Moderate
    info = any(g(k) for k in ("occupation", "income", "job_tenure", "pay_history", "customer_type"))
    if info and not strong:
        inc = money(g("income"))
        weak = []
        if inc is not None and 0 < inc < LOW_INCOME:
            weak.append("เงินเดือน %s" % "{:,}".format(inc))
        if ten is not None and ten < STRONG_MONTHS:
            weak.append("อายุงาน %s" % g("job_tenure"))
        bad = [w for w in _WEAK if w in hist]
        if bad:
            weak.append(" · ".join(bad))
        if weak:
            R["LD"].append("ให้ข้อมูลแต่เครดิตอ่อน (%s)" % " · ".join(weak))
        else:
            R["NLD"].append("ให้ข้อมูลบางส่วน ยังไม่เข้าเกณฑ์ Hot/LD")
    if not info:
        low = (prices and prices[-1] <= LOW_PRICE) or (budget and budget <= LOW_PRICE and not prices)
        if low:
            R["BLD"].append("ไม่ให้ข้อมูล + รถราคาไม่เกิน 3 แสน (%s)" % (
                "รถในสต็อก %s บาท" % "{:,}".format(prices[-1]) if prices else "งบ %s" % "{:,}".format(budget)))
        else:
            R["NLD"].append("ให้ช่องทางติดต่อ แต่ยังไม่ให้ข้อมูล" if (phone or line_id) else "ยังไม่มีข้อมูล")

    base = max((k for k in _RANK if R[k]), key=lambda k: _RANK[k], default="NLD")
    reasons = [[k, r] for k in sorted(R, key=lambda k: -_RANK[k]) for r in R[k]]
    why = " · ".join(R[base]) or "ยังไม่มีข้อมูล"
    return {"base": base, "label": LABEL[base], "why": why, "reasons": reasons, "doc": doc,
            "docAuto": doc_flag is None}


# ── ดึงข้อมูลจากแชทจริง ──
_CACHE: dict = {}
CACHE_SEC = 120


def for_chat(o, lead, msgs=None) -> dict:
    """ตัดสินจากแชทจริงของลูกค้า (จำผล 2 นาที — หน้าแชทรีเฟรชทุก 6 วิ)"""
    key = (o.pk, str(getattr(o, "last_in_at", "") or ""), str(getattr(lead, "updated_at", "") or ""))
    hit = _CACHE.get(o.pk)
    if hit and hit[0] == key and time.time() - hit[1] < CACHE_SEC:
        return hit[2]
    from . import connect as C
    if msgs is None:
        msgs = C.messages(o, limit=150)
    tin = [m.get("text") or "" for m in msgs if m.get("dir") == "in"]
    tout = [m.get("text") or "" for m in msgs if m.get("dir") == "out"]
    visit = ""
    try:
        from .models import ChatFollowup
        f = o.followups.filter(done_at__isnull=True, kind=ChatFollowup.VIEWING).exclude(due_at=None).order_by("due_at").first()
        if f:
            visit = timezone.localtime(f.due_at).strftime("%d/%m %H:%M")
        else:
            from . import crm
            hint = crm.appt_hint(o, msgs)
            if hint and hint.get("at"):
                from django.utils.dateparse import parse_datetime
                d = parse_datetime(hint["at"])
                visit = timezone.localtime(d).strftime("%d/%m %H:%M") if d else "ในแชท"
    except Exception:
        visit = ""
    flag = (lead.auto or {}).get(DOC_KEY)
    doc_flag = bool(flag.get("on")) if isinstance(flag, dict) and "on" in flag else None
    car = (lead.car_model or "") if (lead.car_model or "") not in ("", "ไม่ระบุรุ่นรถ") else (lead.car_text or "")
    try:
        prices = car_prices(car)
    except Exception:
        prices = []
    out = decide(lead, tin, tout, visit_date=visit, prices=prices, doc_flag=doc_flag)
    _CACHE[o.pk] = (key, time.time(), out)
    if len(_CACHE) > 3000:
        for k in list(_CACHE)[:1000]:
            _CACHE.pop(k, None)
    return out


def forget(o_pk) -> None:
    _CACHE.pop(o_pk, None)


def mark_doc(o, on, by: str = "") -> tuple:
    """แอดมินติ๊ก/เอาติ๊กออก "มีเอกสารยืนยันรายได้" · on=None = คืนให้ระบบจับจากคำในแชท"""
    from . import connect as C
    lead = C.lead_of(o)
    auto = dict(lead.auto or {})
    if on is None:
        auto.pop(DOC_KEY, None)
        msg = "ให้ระบบดูเอกสารรายได้จากคำในแชทเอง"
    else:
        auto[DOC_KEY] = {"on": bool(on), "by": (by or "")[:80], "at": timezone.now().isoformat()}
        msg = "บันทึกแล้ว: %s" % ("มีเอกสารยืนยันรายได้" if on else "ไม่มีเอกสารยืนยันรายได้")
    lead.auto = auto
    lead.save(update_fields=["auto", "updated_at"])
    forget(o.pk)
    return True, msg
