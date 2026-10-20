"""จับ keyword จากแชทลูกค้า/โน้ต → ช่องโปรไฟล์ลีด (7 ต.ค.69 · เจ้าของสั่ง)

*"จับ keyword แล้วลงตาม dropdown ได้ไหม … จับ keyword เช็คแล้วก็กรอกลงทุกช่องตามที่ lead ต้องการ"*

ฟังก์ชันล้วน ไม่แตะฐานข้อมูล ไม่ยิงเน็ต ไม่ใช้ AI — ผลเหมือนเดิมทุกครั้ง ตรวจย้อนได้ว่าจับจากคำไหน
`extract(texts)` คืนเฉพาะช่องที่จับได้ `{ช่อง: (ค่า, คำที่จับได้)}`:

  occupation     อาชีพ (ข้อความ)            · customer_type   ประเภทลูกค้า (คีย์หมวด → `pick()` แปลงเป็นตัวเลือกของชีต)
  income         รายได้ต่อเดือน (ตัวเลข)     · job_tenure      อายุงาน
  pay_history    ประวัติผ่อน/เครดิต          · customer_status สถานะลูกค้า (คีย์ → `pick()`)

กติกา (วัดกับโน้ตจริงแท็บ ต.ค.69 ~1,150 แถวก่อนใช้)
  · **ภาษาไทยไม่เว้นวรรค** → คำสั้นต้องมีขอบ: "อบจ" ใน "รอตอบจ้า" · "711" ในเลขลีด "7114" · "ทำนา" ใน "ทำนายหน้า"
    เคยจับผิดมาแล้วทั้งหมด (เทสต์กันไว้)
  · **ตัวเลขต้องมาจากข้อความจริง** — รายได้ต้องมีคำบอก (รายได้/เงินเดือน/ฐาน/สลิป…) นำหน้าตัวเลข
    ค่างวด/ดาวน์/งบ/ราคารถ ไม่นับ · ได้เป็นรายวัน/รายสัปดาห์ = ไม่เติม (ไม่แปลงเอง)
  · **คำปฏิเสธนำหน้า = ความหมายกลับ** ("ไม่ติดแบล็คลิส" ≠ ติดแบล็คลิส)
  · อาชีพของแฟน/พ่อแม่/คนค้ำ และอาชีพในอดีต ("ตอนเป็นทหาร") ไม่ใช่ของลูกค้าตอนนี้ → ข้าม
  · อาชีพ = **คำที่ลูกค้าพูดถึงก่อน** (ไม่ใช่หมวดที่มาก่อนในลิสต์) — "ทำปั๊มน้ำมัน … มีบัตรเกษตรกร" = ปั๊ม
  · แบบฟอร์มที่แอดมินใช้ ("อาชีพ : … รายได้ : … อายุงาน : … ประวัติการผ่อน : …") อ่านก่อน แม่นที่สุด
  · สถานะลูกค้า = ข้อความล่าสุดที่บอกสถานะชนะ (ลูกค้าเปลี่ยนใจได้) · ช่องอื่น = ข้อความแรกที่บอก

★ 21 ต.ค.69 คำ/รูปแบบทั้งหมด (อาชีพ · รายได้ · อายุงาน · ประวัติผ่อน · สถานะ · ลีดรับซื้อ · คำกันจับผิด · ตัวสะกดในชีต)
  ย้ายไปอยู่ในฐานข้อมูล `checkout_keywordrule` (แก้ได้ที่ /crm/?p=auto) — ไฟล์นี้เหลือแค่ "วิธีอ่าน" (ตัวเลขเงิน/ระยะเวลา ·
  ลำดับการตัดสิน) · ตัวอ่านคำ = `kwdb.py` · ค่าตั้งต้น = `kw_defaults.py`
  · ชื่อเดิม (`_REL` `_STATUS` `TYPE_SPELL` …) ยังเรียกจากนอกไฟล์ได้ผ่าน `__getattr__` (ได้ค่าปัจจุบันจากฐานข้อมูล)
"""
import functools
import re

from . import kwdb

_T = "ก-๙"                     # ช่วงอักษรไทย (ใช้ทำขอบคำ)


def type_spell() -> dict:
    """หมวด "ประเภทลูกค้า" → ตัวสะกดที่ชีตอาจใช้ (ชีตสะกด "ฟลีแลนด์" "เกษตกร" "รัฐวิสาหากิจ" — เทียบตามของจริง)"""
    return kwdb.cached("type_spell", lambda: {r["value"]: list((r.get("extra") or {}).get("spell") or [r["name"]])
                                              for r in kwdb.rows("cust_type", active=False) if r.get("value")})


def status_spell() -> dict:
    """ค่าสถานะ → ตัวสะกดของตัวเลือก "สถานะลูกค้า" ในชีต"""
    return kwdb.cached("status_spell", lambda: {r["value"]: list((r.get("extra") or {}).get("spell") or [r["value"]])
                                                for r in kwdb.rows("status", active=False) if r.get("value")})


def _key(s) -> str:
    return re.sub(r"\s+", "", str(s or "")).lower()


def pick(options, spellings) -> str:
    """ตัวเลือกของชีตที่ตรงกับตัวสะกดใดตัวหนึ่ง (ไม่สนช่องว่าง/ตัวพิมพ์) — ไม่มีสักตัว = "" (ไม่เดา)"""
    for w in (_key(s) for s in spellings):
        for o in options or []:
            if _key(o) == w:
                return o
    return ""


def norm(t: str) -> str:
    """ล้างคำพิมพ์ที่ทำให้เทียบไม่ตรง: เเ→แ · ํา→ำ · พนง.→พนักงาน · ตัวอักษรล่องหน · ตัวพิมพ์เล็ก"""
    t = str(t or "").replace("เเ", "แ").replace("ํา", "ำ")
    t = re.sub(r"[​-‍﻿]", "", t)
    t = re.sub(r"พนง\.?\s*", "พนักงาน", t)
    t = t.replace("พนังงาน", "พนักงาน")
    return t.lower()


def _neg():
    return kwdb.rx("guard", "neg", r"(?:{})\s*$")


def _rel():
    return kwdb.rx("guard", "rel", "(?:{})")


def _past():
    return kwdb.rx("guard", "past", r"(?:{})\s*(?:เป็น|ทำ)?\s*$")


def _want():
    return kwdb.rx("guard", "want", r"(?:{})\s*$")


def _negated(t, start) -> bool:
    return bool(_neg().search(t[max(0, start - 8):start]))


def _guard(t, start) -> bool:
    """อาชีพที่ไม่ใช่ของลูกค้าตอนนี้: ของญาติ/คนค้ำ (15 ตัวก่อนหน้า) หรือ อดีต ("ตอนเป็นทหาร")"""
    return bool(_rel().search(t[max(0, start - 15):start]) or _past().search(t[max(0, start - 12):start]))


def _clip(s, n) -> str:
    s = re.sub(r"\s+", " ", str(s or "")).strip(" :：=-/,.")
    s = re.sub(r"(?:นะคะ|นะครับ|ค่ะ|คะ|ครับ|คับ|จ้า|จ้ะ|น้า)+$", "", s).strip(" :：=-/,.")
    s = re.sub(r"^(?:มี|เป็น|ทำ)(?=[ก-๙]{3})", "", s)
    return s if len(s) <= n else s[:n].rstrip() + "…"


# ── แบบฟอร์มของแอดมิน "อาชีพ : … รายได้ : …" ──
_LABEL = re.compile(r"(อาชีพ|รายได้|อายุงาน|ประวัติ\s*(?:การ)?\s*ผ่อน|เครดิต|จังหวัด|อายุ(?!งาน)|แพลน\s*ออกรถ|"
                    r"เงินดาวน์|ดาวน์|ชื่อ|เบอร์|สนใจ|ไลน์|line)\s*[:：=]")


def labels(t: str) -> dict:
    """ข้อความแบบฟอร์ม → {ป้าย: ค่า} (ค่า = ตั้งแต่หลัง ":" ถึงป้ายถัดไป) · ป้ายซ้ำ = เอาอันแรก"""
    out = {}
    ms = list(_LABEL.finditer(t))
    for i, m in enumerate(ms):
        lab = re.sub(r"\s+", "", m.group(1))
        lab = "ประวัติผ่อน" if lab.startswith("ประวัติ") else lab
        val = t[m.end():ms[i + 1].start() if i + 1 < len(ms) else len(t)].strip()
        if lab not in out and val and val not in ("-", "ไม่ระบุ"):
            out[lab] = val
    return out


# ── อาชีพ: แถวหมวด occupation ในฐานข้อมูล = (regex, คำที่ใช้เป็นอาชีพ (ว่าง = คำที่จับได้), หมวดประเภทลูกค้า) ──
#   เลือก "คำที่เจอก่อนในข้อความ" · เริ่มตำแหน่งเดียวกัน = ลำดับแถวชนะ
def _occ():
    return kwdb.cached("occ", lambda: [(rx_, r.get("value") or None, r.get("parent") or "")
                                       for r, rx_ in kwdb.row_list("occupation")])


# "ทำอาชีพ X" / "พนักงาน X" ที่ไม่อยู่ในลิสต์ — ตัดที่คำหยุด (ภาษาไทยไม่มีช่องว่างให้ตัด)
_OCC_FREE = re.compile(r"(?:ทำ|ประกอบ)?อาชีพ\s*(?:เป็น|คือ)?\s*(?P<a>[" + _T + r"a-z&]{2,24})|"
                       r"พนักงาน(?P<b>[" + _T + r"a-z]{2,20})")


def _occ_stop():
    return kwdb.rx("guard", "occ_stop")


def _salaried():
    return kwdb.rx("income_kw", "salaried")


def _occ_hits(t: str):
    """[(ตำแหน่ง, ลำดับกลุ่ม, อาชีพ, หมวด, คำที่จับได้)] ที่ผ่านด่าน (ไม่ใช่ญาติ/อดีต/ปฏิเสธ)"""
    hits = []
    for gi, (rx, word, cat) in enumerate(_occ()):
        for m in rx.finditer(t):
            if _guard(t, m.start()) or (cat != "none" and _negated(t, m.start())):
                continue
            if cat == "driver" and re.search(r"(?:แอป|app|กู้)\s*$", t[max(0, m.start() - 6):m.start()]):
                continue                           # "กู้แอป Grab" = เงินกู้ ไม่ใช่อาชีพ
            w = word or m.group(0)
            w = {"รับราชการ": "ข้าราชการ", "ราชการ": "ข้าราชการ", "พนักงานบ": "พนักงานบริษัท",
                 "พนักงานบ.": "พนักงานบริษัท", "ธุระกิจส่วนตัว": "ธุรกิจส่วนตัว"}.get(w, w)
            if w.startswith("เปิดร้าน"):
                w = "เจ้าของร้าน" + w[len("เปิดร้าน"):]
            hits.append((m.start(), gi, w, cat, m.group(0)))
            break
    return hits


def _free_occ(t: str):
    for m in _OCC_FREE.finditer(t):
        if _guard(t, m.start()):
            continue
        raw = m.group("a") or m.group("b") or ""
        cut = _occ_stop().search(raw)
        raw = raw[:cut.start()] if cut else raw
        if len(raw) < 2:
            continue
        w = raw if m.group("a") else "พนักงาน" + raw
        hits = _occ_hits(w)
        if hits:
            h = min(hits, key=lambda x: (x[0], x[1]))
            if h[0] == 0:
                return m.start(), h[2], h[3], m.group(0)
            return m.start(), _clip(w, 30), h[3], m.group(0)
        return m.start(), _clip(w, 30), "company" if w.startswith("พนักงาน") else "", m.group(0)
    return None


def occupation_in(t: str):
    """→ (อาชีพ, หมวด, คำที่จับได้) หรือ None — คำที่ลูกค้าพูดถึงก่อนชนะ"""
    hits = _occ_hits(t)
    free = _free_occ(t)
    best = min(hits, key=lambda x: (x[0], x[1])) if hits else None
    if free and (not best or free[0] < best[0]):
        return free[1], free[2], free[3]
    if best:
        return _clip(best[2], 40), best[3], best[4]
    return None


# ── รายได้ ──
_TH_DIGIT = {"หนึ่ง": 1, "สอง": 2, "สาม": 3, "สี่": 4, "ห้า": 5, "หก": 6, "เจ็ด": 7, "แปด": 8, "เก้า": 9}
_MONEY = re.compile(
    r"(?P<man>(?P<a>\d+(?:\.\d+)?)?\s*หมื่น\s*(?P<b>\d|หนึ่ง|สอง|สาม|สี่|ห้า|หก|เจ็ด|แปด|เก้า)?(?![\d,]))|"
    r"(?P<saen>(?P<c>\d+(?:\.\d+)?)\s*แสน)|"
    r"(?P<num>\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(?P<k>k(?![a-z])|พัน)?")
_RANGE_SEP = re.compile(r"^\s*(?:-|–|~|ถึง|จนถึง)\s*")
_MAX_INCOME = 2_000_000


def _money_one(m) -> int:
    if m.group("man"):
        b = m.group("b")
        b = int(b) if b and b.isdigit() else _TH_DIGIT.get(b or "", 0)
        return int(float(m.group("a") or 1) * 10000 + b * 1000)
    if m.group("saen"):
        return int(float(m.group("c")) * 100000)
    v = float(m.group("num").replace(",", ""))
    return int(v * 1000) if m.group("k") else int(v)


def _unit(m) -> int:
    """ตัวคูณของหน่วยที่ตามหลังตัวเลข (ใช้ขยายปลายแรกของช่วง "3-4 หมื่น" "35-45k")"""
    if m.group("man"):
        return 10000
    if m.group("saen"):
        return 100000
    return 1000 if m.group("k") else 1


def money_at(s: str):
    """ตัวเลขเงินตัวแรกใน `s` → (ข้อความ, ตำแหน่งเริ่ม, ตำแหน่งจบ) หรือ None
    รองรับ 22,000 · 2หมื่น · หมื่น8 · 1แสน · 15k · ช่วง 12000-13000 / 35k-45k / 3-4 หมื่น / 20,002 ถึง 24,000"""
    for m in _MONEY.finditer(s):
        lo = _money_one(m)
        rest = s[m.end():]
        sep = _RANGE_SEP.match(rest)
        m2 = _MONEY.match(rest, sep.end()) if sep else None
        if m2:
            hi = _money_one(m2)
            if m.group("num") and not m.group("k") and lo < 1000 and _unit(m2) > 1:
                lo *= _unit(m2)                      # "3-4 หมื่น" → 30000-40000
            if 3000 <= lo < hi <= _MAX_INCOME:
                return "%d-%d" % (lo, hi), m.start(), m.end() + m2.end()
        if 3000 <= lo <= _MAX_INCOME:
            return str(lo), m.start(), m.end()
    return None


def _income_kw():
    return kwdb.rx("income_kw", "lead")


def _per_day():
    return kwdb.rx("income_kw", "per_day")


def _not_income():
    return kwdb.rx("income_kw", "not_income")


def _total():
    return kwdb.rx("income_kw", "total")


def income_in(t: str):
    """รายได้ต่อเดือน → (ค่า, คำที่จับได้) · ต้องมีคำบอกว่าเป็นรายได้นำหน้าไม่เกิน ~30 ตัวอักษร
    มี "รวม/เบ็ดเสร็จ/จริงๆ" = ใช้ตัวนั้น (ฐาน 12,000 แต่รวมค่าคอม 50,000 → 50000)
    "รวมกับแฟน" ไม่นับ (รายได้ครอบครัว ไม่ใช่ของลูกค้า)"""
    best = None
    for m in _income_kw().finditer(t):
        # ★ 12 ต.ค.69 (เห็นจากไฮไลต์ในหน้าแชท) "ผ่อนได้เดือนละ 7,000" = ค่างวดที่ผ่อนไหว ไม่ใช่รายได้
        if re.search(r"(?:ผ่อน|งวด|ดาวน์|จ่าย)\s*$", t[max(0, m.start() - 6):m.start()]):
            continue
        win = t[m.end():m.end() + 30]
        hit = money_at(win)
        if not hit:
            continue
        val, pos, end = hit
        between = win[:pos]
        if _per_day().search(between) or _not_income().search(between):
            continue
        ctx = m.group(0) + between
        if re.search(r"รวมกับ|กับแฟน|ของแฟน|ของ(?:สามี|ภรรยา)", ctx) or _rel().search(t[max(0, m.start() - 10):m.start()]):
            continue
        cand = (val, _clip(t[m.start():m.end() + end], 60))
        if _total().search(ctx):
            return cand
        best = best or cand
    return best


def _income_after(t: str, end: int):
    """ตัวเลขที่ตามหลังอาชีพติดๆ = รายได้ ("พนักงานโรงงาน 12,000" · "พนง.บัญชี 27,000")
    ต้องเป็นตัวเลขล้วน (ไม่มีหน่วย ปี/เดือน/คัน/งวด ต่อท้าย)"""
    m = re.match(r"\s{0,2}(?P<v>\d{1,3}(?:,\d{3})+|\d{4,6})(?!\s*(?:ปี|เดือน|คัน|งวด|บาท/วัน|\d|/))", t[end:end + 14])
    if m:
        v = int(m.group("v").replace(",", ""))
        if 5000 <= v <= 500000:
            return str(v), _clip(t[max(0, end - 12):end + m.end()], 40)
    return None


# ── อายุงาน ──
_DUR = (r"(?P<not>ไม่ถึง\s*)?(?:(?P<one>เดือนเดียว)|(?P<halfy>ครึ่งปี)|(?P<n>\d+(?:\.\d+)?(?:\s*[-–]\s*\d+)?|หนึ่ง|สอง|สาม|สี่|ห้า|หก|เจ็ด|แปด|เก้า|สิบ|หลาย)?\s*"
        r"(?P<u>ปี|เดือน)(?P<half>ครึ่ง)?(?:\s*(?P<n2>\d+|หนึ่ง|สอง|สาม|สี่|ห้า|หก|เจ็ด|แปด|เก้า|สิบ)\s*เดือน)?"
        r"(?P<more>\s*กว่า(?:ๆ)?)?)")
def _tenure():
    """คำบอกอายุงาน (ฐานข้อมูล · หมวด tenure_kw) + ระยะเวลา (ไวยากรณ์ในโค้ด)"""
    return kwdb.rx("tenure_kw", "lead", r"(?:{})\s*[:：=.]*\s*(?:ประมาณ|ได้|แค่|เกือบ|ราวๆ|ราว|ก็|มา|แล้ว|เป็น|อยู่|ทั้งหมด|"
                                         r"เพียง)*\s*" + _DUR)


_TH_NUM = dict(_TH_DIGIT, สิบ=10)


def _fmt_dur(m) -> str:
    if m.group("one"):
        return "1 เดือน"
    if m.group("halfy"):
        return "6 เดือน"
    n, u = m.group("n"), m.group("u")
    if n == "หลาย":
        return "หลายปี" if u == "ปี" else ""
    if not n:
        if u == "ปี" and m.group("half"):
            return "1 ปี 6 เดือน"
        return "1 ปีกว่า" if (u == "ปี" and m.group("more")) else ""
    n = str(_TH_NUM.get(n, n)).replace(" ", "")
    s = "%s %s" % (n, u)
    if m.group("half") and u == "ปี":
        s += " 6 เดือน"
    elif m.group("n2"):
        s += " %s เดือน" % _TH_NUM.get(m.group("n2"), m.group("n2"))
    if m.group("more"):
        s += "กว่า"
    if m.group("not"):
        s = "ไม่ถึง " + s
    return s


def tenure_in(t: str):
    for m in _tenure().finditer(t):
        if _rel().search(t[max(0, m.start() - 12):m.start()]):
            continue
        v = _fmt_dur(m)
        if v:
            return v, _clip(m.group(0), 40)
    return None


def _tenure_after(t: str, end: int):
    """ระยะเวลาที่ตามหลังอาชีพติดๆ = อายุงาน ("ทำงานบริษัท 3 ปี" · "พนักงานประจำ 9 ปี")"""
    m = re.match(r"\s{0,2}" + _DUR, t[end:end + 20])
    v = _fmt_dur(m) if m else ""
    return (v, _clip(t[max(0, end - 12):end + m.end()], 40)) if v else None


# ── ประวัติผ่อน/เครดิต: แถวหมวด pay ในฐานข้อมูล = (regex, ข้อความ, ข้อความเมื่อมีคำปฏิเสธนำหน้า) ──
def _pay():
    return kwdb.cached("pay", lambda: [(rx_, r.get("value") or r["name"], ((r.get("extra") or {}).get("neg") or None))
                                       for r, rx_ in kwdb.row_list("pay")])


def _always_pos():
    """ค่าที่ไม่กลับความหมายเมื่อมีคำปฏิเสธนำหน้า ("ไม่มีเครดิต" มีคำว่าไม่อยู่ในตัวแล้ว)"""
    return kwdb.cached("pay_always", lambda: tuple(r.get("value") or r["name"] for r in kwdb.rows("pay", active=False)
                                                   if (r.get("extra") or {}).get("always")))


def pay_in(t: str):
    got, ev = [], []
    always = _always_pos()
    for rx, pos, neg in _pay():
        for m in rx.finditer(t):
            if _rel().search(t[max(0, m.start() - 10):m.start()]):
                continue                           # ประวัติของแฟน/พ่อแม่ ไม่ใช่ของลูกค้า
            if pos.startswith("ผ่อน") and _want().search(t[max(0, m.start() - 6):m.start()]):
                continue                           # "อยากผ่อนกระบะ" = รถที่จะซื้อ ไม่ใช่หนี้เดิม
            lab = pos
            if neg is not None and _negated(t, m.start()):
                lab = neg
            elif neg is None and pos not in always and _negated(t, m.start()):
                continue
            if lab not in got:
                got.append(lab)
                ev.append(m.group(0))
            break
    if not got:
        return None
    if "ไม่มีเครดิต" in got and len(got) > 1:      # "ไม่เคยผ่อนอะไร … เคยผ่อนมือถือ" ขัดกัน → เอาเฉพาะของที่มี
        got.remove("ไม่มีเครดิต")
    return " · ".join(got)[:120], " / ".join(ev)


# ── สถานะลูกค้า: แถวหมวด status ในฐานข้อมูล = (regex, ค่า, เช็คคำปฏิเสธไหม) · ข้อความเดียวมีหลายอย่าง = แถวบนสุดชนะ ──
#   ★ ระวังค่าที่ทำให้ "เลิกตาม" ในชีต (ยังไม่ออกเร็วๆนี้ · ติดแบล็คลิส · ลูกค้าไม่สนใจแล้ว) — ใช้คำที่ชัดเท่านั้น
#     "สิ้นปี" ไม่นับว่ายังไม่ออก (เดือน ต.ค. = อีก 2 เดือน ยังต้องตาม) · "ยกเลิก" ต้องบอกว่ายกเลิกอะไร
def _status():
    return kwdb.cached("status", lambda: [(rx_, r.get("value") or r["name"], bool((r.get("extra") or {}).get("check")))
                                          for r, rx_ in kwdb.row_list("status")])


def status_in(t: str):
    for rx, key, chk in _status():
        for m in rx.finditer(t):
            if chk and _negated(t, m.start()):
                continue
            return key, m.group(0)
    return None


def extract(texts) -> dict:
    """ข้อความเรียงเก่า→ใหม่ → `{ช่อง: (ค่า, คำที่จับได้)}` เฉพาะช่องที่จับได้"""
    out = {}
    for raw in texts or []:
        t = norm(raw)
        if not t.strip():
            continue
        lab = labels(t)
        # แบบฟอร์มแอดมินก่อน — ป้ายบอกชัดว่าเป็นช่องไหน
        if "อาชีพ" in lab and "occupation" not in out:
            v = lab["อาชีพ"]
            hit = occupation_in(v)
            short = _clip(v, 99)
            occ = short if len(short) <= 30 or not hit else hit[0]
            if occ and not re.fullmatch(r"[-–/.\s]*|ไม่ระบุ|ไม่ทราบ|ไม่บอก", occ):
                out["occupation"] = (_clip(occ, 40), "อาชีพ : " + _clip(v, 60))
                if hit and hit[1] and "customer_type" not in out:
                    out["customer_type"] = (hit[1], hit[2])
        if "รายได้" in lab and "income" not in out:
            v = lab["รายได้"]
            got = income_in("รายได้ " + v)
            if got and not _per_day().search(v[:14]):
                out["income"] = (got[0], "รายได้ : " + _clip(v, 60))
        if "อายุงาน" in lab and "job_tenure" not in out:
            got = tenure_in("อายุงาน " + lab["อายุงาน"])
            if got:
                out["job_tenure"] = (got[0], "อายุงาน : " + _clip(lab["อายุงาน"], 40))
        for key in ("ประวัติผ่อน", "เครดิต"):
            if key in lab and "pay_history" not in out:
                v = _clip(lab[key], 120)
                if v and not re.fullmatch(r"[-–/.\s]*|ไม่ระบุ|ไม่ทราบ", v):
                    out["pay_history"] = (v, key + " : " + _clip(lab[key], 60))
        # keyword ทั่วไป
        occ_end = None
        if "occupation" not in out:
            hit = occupation_in(t)
            if hit:
                out["occupation"] = (hit[0], hit[2])
                if hit[1] and "customer_type" not in out:
                    out["customer_type"] = (hit[1], hit[2])
                i = t.find(hit[2])
                occ_end = i + len(hit[2]) if i >= 0 else None
        if "income" not in out:
            got = income_in(t) or (_income_after(t, occ_end) if occ_end else None)
            if got:
                out["income"] = got
        if "job_tenure" not in out:
            got = tenure_in(t) or (_tenure_after(t, occ_end) if occ_end else None)
            if got:
                out["job_tenure"] = got
        if "pay_history" not in out:
            got = pay_in(t)
            if got:
                out["pay_history"] = got
        st = status_in(t)
        if st:                                        # สถานะ = ข้อความล่าสุดชนะ
            out["customer_status"] = st
    if "customer_type" not in out:
        m = _salaried().search(norm(" ".join(texts or [])))
        if m:
            out["customer_type"] = ("company", m.group(0))
    return out


# ═════════════════════════════════════════════════════════════════════════════
#  ไฮไลต์คำที่ระบบจับได้ในหน้าแชท + "ลูกค้าพูดค่าใหม่" (12 ต.ค.69 · เจ้าของเลือกจากเดโม "เอาแบบนี้แหละ")
#  ตัวจับยังเป็นตัวเดิมข้างบน (ไม่เขียนกติกาใหม่) — ตรงนี้แค่หา "ตำแหน่ง" ของคำที่ตัวเดิมจับได้ในข้อความที่ลูกค้าพิมพ์จริง
# ═════════════════════════════════════════════════════════════════════════════
@functools.lru_cache(maxsize=8192)
def _extract_one(raw: str) -> tuple:
    """`extract` ของข้อความเดียว (จำผลไว้ — ข้อความแชทไม่เปลี่ยน แต่หน้าแชทรีเฟรชทุก 6 วิ)"""
    return tuple(extract([raw]).items())


def latest(texts) -> dict:
    """ข้อความเรียงเก่า→ใหม่ → `{ช่อง: (ค่า, คำที่จับได้)}` จาก **ข้อความล่าสุด** ที่พูดถึงช่องนั้น

    `extract` ใช้ข้อความแรก (ค่าที่เติมลงฟอร์ม) — ตัวนี้ใช้ดูว่าลูกค้าพูดค่าใหม่ทีหลังไหม
    ("รายได้ 15,000" แล้วต่อมา "จริงๆ รวมโอทีได้ 18,000")"""
    out = {}
    for raw in reversed([str(t) for t in texts or [] if t]):
        for f, v in _extract_one(raw):
            out.setdefault(f, v)
    return out


_NORM_RX = re.compile("เเ|ํา|[​-‍﻿]|พนง\\.?\\s*|พนังงาน")
_NORM_REP = {"เเ": "แ", "ํา": "ำ", "พนังงาน": "พนักงาน"}


def norm_map(raw):
    """เหมือน `norm()` แต่จำด้วยว่าตัวอักษรแต่ละตัวมาจากตรงไหนของข้อความเดิม
    → (ข้อความที่ล้างแล้ว, [(เริ่ม, จบ) ในข้อความเดิม ต่อ 1 ตัวอักษร]) — ใช้ไฮไลต์บนข้อความที่ลูกค้าพิมพ์จริง"""
    raw = str(raw or "")
    chars, pos, i = [], [], 0
    for m in _NORM_RX.finditer(raw):
        for j in range(i, m.start()):
            chars.append(raw[j])
            pos.append((j, j + 1))
        g = m.group(0)
        rep = _NORM_REP.get(g, "พนักงาน" if g.startswith("พนง") else "")
        for c in rep:
            chars.append(c)
            pos.append((m.start(), m.end()))
        i = m.end()
    for j in range(i, len(raw)):
        chars.append(raw[j])
        pos.append((j, j + 1))
    # lower() ทีละตัว — ตัวที่ lower แล้วยาวขึ้น (หายากมาก) คงไว้ ไม่งั้นตำแหน่งเลื่อน
    return "".join(c.lower() if len(c.lower()) == 1 else c for c in chars), pos


def _locate(t: str, ev: str, start: int = 0):
    """หาคำที่จับได้ (ผ่าน `_clip` มาแล้ว — ช่องว่างถูกยุบ/ตัดท้าย) ในข้อความที่ล้างแล้ว → (เริ่ม, จบ) หรือ None"""
    ev = str(ev or "").replace("…", "").strip()
    if len(ev) < 2:
        return None
    i = t.find(ev, start)
    if i >= 0:
        return i, i + len(ev)
    parts = [p for p in re.split(r"\s+", ev) if p]
    rx = r"\s*".join("".join("[:：=]" if c in ":：=" else re.escape(c) for c in p) for p in parts)
    m = re.compile(rx).search(t, start)
    return (m.start(), m.end()) if m else None


SPAN_FIELDS = ("occupation", "income", "job_tenure", "pay_history", "customer_status")


def spans(raw) -> list:
    """ข้อความลูกค้า 1 ข้อความ → [(เริ่ม, จบ, ช่อง)] ตำแหน่ง **ในข้อความเดิม** ของคำที่ `extract` จับได้
    ประเภทลูกค้าไม่ไฮไลต์แยก (มาจากคำเดียวกับอาชีพ)"""
    raw = str(raw or "")
    t, pos = norm_map(raw)
    if not t.strip():
        return []
    out = []
    for f, (_val, ev) in _extract_one(raw):
        if f not in SPAN_FIELDS:
            continue
        evs = [ev]
        if f == "pay_history" and " / " in (ev or "") and not str(ev).startswith(("ประวัติผ่อน", "เครดิต")):
            evs = str(ev).split(" / ")              # หลายเรื่องในข้อความเดียว ("ผ่อนรถ / ผ่อนตรง") = ไฮไลต์ทีละคำ
        for e in evs:
            hit = _locate(t, e)
            if hit:
                out.append((pos[hit[0]][0], pos[hit[1] - 1][1], f))
    return out


def deal_spans(raw, outbound: bool = False) -> list:
    """คำที่ทำให้แชทเป็น "ลีดรับซื้อรถ" (ช่อง `deal`) และ "มีรถเทิร์น" (ช่อง `trade`) — กติกาเดียวกับ `deal_kind`
    · ข้อความของเรา: เฉพาะคำชี้ขาด (ฝ่ายจัดซื้อ / หน้า 4 และ 18) ที่ไม่ได้พูดเรื่องเทิร์น"""
    t, pos = norm_map(raw)
    if not t.strip():
        return []
    span = lambda m, f: (pos[m.start()][0], pos[m.end() - 1][1], f)
    if outbound:
        return [] if _trade().search(t) else [span(m, "deal") for m in _buy_out().finditer(t)]
    out = [span(m, "trade") for m in _trade().finditer(t)]
    if out or _buy_not().search(t) or _job().search(t):
        return out
    for rx in _buy():
        for m in rx.finditer(t):
            if m.end() > m.start() and not _negated(t, m.start()):
                out.append(span(m, "deal"))
    return out


# ═════════════════════════════════════════════════════════════════════════════
#  ลีดรับซื้อรถ (ลูกค้าอยากขายรถให้เรา → ทีมจัดซื้อ) vs ลีดขายรถ (ลูกค้าอยากซื้อรถเรา → เซลล์)
#  ★ 11 ต.ค.69 เจ้าของ: "มันจะมี lead รับซื้อรถกับ lead ขายรถด้วยนะ แยกไว้ด้วย"
#  วัดกับแชทจริงบน prod ก่อนใช้ (ลีดที่มีใบเคสรับซื้อแล้ว vs ลีดที่ได้เลขขาย):
#    คำชัดๆ จับลีดรับซื้อได้ 19/21 · จับลีดขายผิด 3/178 · ที่เหลือที่จับได้ส่วนใหญ่เป็นคนอยากขายรถจริงที่ยังไม่ได้ส่งจัดซื้อ
#  ★ กับดักที่เจอในข้อมูลจริง (มีเทสต์กันทุกข้อ)
#    · คนสมัครงาน ("สนใจสมัครเซลขายรถ" · "เคยขายรถมอไซค์" · "แอดมินรับซื้อรถ") — ไม่ใช่ลีดเลย
#    · "รับซื้อทะเบียน/ป้ายขาว" — ขายเลขทะเบียน ไม่ใช่ขายรถ
#    · เทิร์น ("ถ้าจะเทิร์นตีราคาได้เท่าไหร่") = เขาจะซื้อรถเรา → ลีดขาย (ติดป้ายมีรถเทิร์น) ไม่ใช่ลีดรับซื้อ
#    · "ร้านขายรถอยู่ไหน" / "ขายรถคันนี้ยัง" — ถามถึงรถของเรา
#    · "ประเมินเครดิต/วงเงิน" — เรื่องไฟแนนซ์ของคนซื้อ ไม่ใช่ประเมินราคารถ
#    · เลขไมล์/ยอดปิดไฟแนนซ์/มีเล่ม พูดได้ทั้ง 2 ฝั่ง → ไม่ใช้ตัดสิน
#  ★ 11 ต.ค.69 (ดึก) ผู้ใช้: "คนที่ส่งรูปรถมาเยอะๆ หลังจากที่ admin พิมพ์ขอดูรูปหรือเล่ม (หน้า 18)" — ข้อความ "ของเรา" ชี้ขาดได้เอง
#    แอดมิน/เพจใช้เทมเพลต "รบกวนลูกค้า ส่งภาพรถ ✅ ด้านนอก ✅ ด้านใน ✅ หน้าปัดให้เห็นเลขไมล์ ✅ สำเนาเล่มทะเบียน หน้า 4 และ หน้า 18
#    … เพื่อให้เจ้าหน้าที่ฝ่ายจัดซื้อประเมินราคา" / "แอดมินจะประสานงานให้เจ้าหน้าที่ฝ่ายจัดซื้อติดต่อกลับ" = คนตัดสินแล้วว่าเป็นงานรับซื้อ
#    วัดบน prod: ข้อความของเราชุดนี้เจอใน 12/21 ลีดที่มีใบเคสรับซื้อ · ลีดขายที่ได้เลข 0/179
#    · แอดมินถามเรื่องเทิร์นบ่อยมาก ("ลูกค้าเอารถรุ่นไหนมาเทิร์นครับ" 36 แชท) → เทิร์นที่ "เรา" พูด ไม่ชี้ขาด · ใช้เฉพาะที่ลูกค้าพูด
#    · ขอรูปแบบกว้างๆ ห้ามใช้คำลอยๆ ("รอบคัน" ไปโดนข้อความโฆษณา "Ford Everest พร้อมชุดแต่งรอบคัน")
#    · LINE: แอดมินตอบในแอป LINE OA Manager ซึ่ง LINE ไม่ส่งกลับมา → ข้อความของเราเห็นเฉพาะ Facebook และที่ตอบผ่าน Connect
# ═════════════════════════════════════════════════════════════════════════════
def _buy():
    """แถวบทบาท "buy" ทีละแถว (re.M — บางแถวใช้ ^ ต้นบรรทัด)"""
    return [rx_ for _r, rx_ in kwdb.row_list("deal", "buy", re.M)]


def _buy_not():
    """ข้อความที่ "ห้ามนับ" แม้จะมีคำข้างบน (สมัครงาน · ขายเลขทะเบียน · เรื่องเครดิตของคนซื้อ · ขายของอย่างอื่น)"""
    return kwdb.rx("deal", "buy_not")


def _job():
    """ทั้งแชทเป็นเรื่องสมัครงาน = ไม่ใช่ลีด (ไม่ว่าจะมีคำว่าขายรถกี่ครั้ง)"""
    return kwdb.rx("deal", "job")


def _trade():
    """รถเทิร์น — คนจะซื้อรถเรา เอารถเก่ามาแลก = ลีดขาย (ไม่ใช่ลีดรับซื้อ)"""
    return kwdb.rx("deal", "trade")


def _buy_out():
    """ข้อความ "ของเรา" ที่บอกชัดว่าเป็นงานรับซื้อ (ส่งต่อฝ่ายจัดซื้อ · ขอสำเนาเล่ม/หน้า 4 และ 18) — ชี้ขาดได้เอง"""
    return kwdb.rx("deal", "buy_out")


def _ask_out():
    """เราขอรูปรถลูกค้า (ไม่ใช่เอกสารของคนซื้อ) → ลูกค้าส่งรูปตามมาตั้งแต่ ASK_IMGS รูป = คนขายรถให้เรา"""
    return kwdb.rx("deal", "ask_out")


def _ask_not():
    return kwdb.rx("deal", "ask_not")


ASK_IMGS = 2


def deal_kind(texts_in, texts_out=(), events=None):
    """ลีดนี้เป็น "รับซื้อรถ" ไหม — ข้อความลูกค้า (+ข้อความของเรา) เรียงเก่า→ใหม่
    `events` = ไทม์ไลน์ทั้ง 2 ฝั่ง [(dir "in"/"out", ข้อความ, เป็นรูป/วิดีโอไหม)] — ใช้นับ "รูปที่ลูกค้าส่งหลังเราขอ"
    (ไม่ส่ง texts_out มา = ใช้ข้อความขาออกจาก events)
    คืน `{"kind": "buy"|"", "why": คำที่จับได้, "trade": คำที่บอกว่ามีรถเทิร์น}`
    · kind ว่าง = ไม่ใช่ลีดรับซื้อ (ค่าตั้งต้นของทุกลีด = ลีดขาย)
    · ลูกค้าพูดถึงรถเทิร์นที่ไหนก็ตามในแชท = ลีดขายเสมอ (เขาจะซื้อรถเรา)"""
    ev = [((d or "in"), norm(t), bool(img)) for d, t, img in (events or [])]
    ins = [norm(t) for t in texts_in or [] if str(t or "").strip()]
    outs = [norm(t) for t in texts_out or [] if str(t or "").strip()] or [t for d, t, _ in ev if d == "out" and t.strip()]
    out = {"kind": "", "why": "", "trade": ""}
    for t in ins:
        m = _trade().search(t)
        if m and not out["trade"]:
            out["trade"] = _clip(t[max(0, m.start() - 12):m.end() + 16], 40)
    if out["trade"]:
        return out
    if any(_job().search(t) for t in ins):
        return out
    for t in ins:
        if _buy_not().search(t):
            continue
        for rx in _buy():
            m = rx.search(t)
            if m and not _negated(t, m.start()):
                out["kind"] = "buy"
                out["why"] = _clip(t[max(0, m.start() - 10):m.end() + 24], 48)
                return out
    # ข้อความของเราบอกว่าเป็นงานรับซื้อ (ไม่นับข้อความที่พูดเรื่องเทิร์น — "การเทิร์นจะเป็นเจ้าหน้าที่จัดซื้อประเมินราคา")
    said = next((t for t in outs if _buy_out().search(t) and not _trade().search(t)), "")
    if said:
        m = _buy_out().search(said)
        out["kind"] = "buy"
        out["why"] = "เราแจ้งลูกค้า: " + _clip(said[max(0, m.start() - 16):m.end() + 16], 48)
        return out
    # เราขอรูปรถ แล้วลูกค้าส่งรูปตามมาหลายรูป
    for i, (d, t, _img) in enumerate(ev):
        if d == "out" and _ask_out().search(t) and not _ask_not().search(t) and not _trade().search(t):
            n = sum(1 for dd, _t, img in ev[i + 1:] if dd != "out" and img)
            if n >= ASK_IMGS:
                m = _ask_out().search(t)
                out["kind"] = "buy"
                out["why"] = "ลูกค้าส่งรูป %d รูปหลังเราขอ: %s" % (n, _clip(t[max(0, m.start() - 6):m.end() + 14], 30))
                return out
            break                                   # ดูเฉพาะครั้งแรกที่เราขอรูป
    return out


# ── ชื่อเดิม (ก่อนย้ายไปฐานข้อมูล) — ยังเรียกจากนอกไฟล์ได้ (lead_code ใช้ _REL/_WANT · เทสต์ใช้ _STATUS/_OCC_SRC/TYPE_SPELL) ──
def __getattr__(name):
    m = {
        "TYPE_SPELL": type_spell, "STATUS_SPELL": status_spell,
        "_NEG": _neg, "_REL": _rel, "_PAST": _past, "_WANT": _want, "_OCC_STOP": _occ_stop,
        "_OCC": _occ, "_PAY": _pay, "_STATUS": _status, "_ALWAYS_POS": _always_pos,
        "_INCOME_KW": _income_kw, "_PER_DAY": _per_day, "_NOT_INCOME": _not_income, "_TOTAL": _total,
        "_SALARIED": _salaried, "_TENURE": _tenure, "_BUY": _buy, "_BUY_NOT": _buy_not, "_JOB": _job,
        "_TRADE": _trade, "_BUY_OUT": _buy_out, "_ASK_OUT": _ask_out, "_ASK_NOT": _ask_not,
        "_OCC_SRC": lambda: [(r.get("pattern") or "", r.get("value") or None, r.get("parent") or "")
                             for r in kwdb.rows("occupation")],
    }
    if name in m:
        return m[name]()
    raise AttributeError(name)


# คำเปลี่ยน (มีคนแก้ในหน้า "ระบบอัตโนมัติ") → ผลจับของข้อความเดิมที่จำไว้ใช้ไม่ได้แล้ว
kwdb.on_change(_extract_one.cache_clear)
