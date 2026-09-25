# -*- coding: utf-8 -*-
"""รายงานเคสรับซื้อรถเข้าห้อง LINE ของแต่ละคน — 25 ก.ย.69 (เจ้าของสั่ง)

*"อยากส่งการแจ้งเตือนว่า 7 วันย้อนหลังมีกี่เคสที่ยังไม่โทร และจัด ranking
ลำดับความสำคัญกับรถที่เราต้องการหรือรถที่เรายังขาดตลาดอยู่"*

ต่อยอดจาก [purchase_followup.py](purchase_followup.py) ซึ่งดึง "เคสที่ยังไม่ตัดสินรับซื้อ"
จากชีตจัดซื้ออยู่แล้ว · ไฟล์นี้เพิ่ม 2 อย่าง:
  1. **รู้ว่ารถรุ่นไหนขาดตลาด** — เทียบ "ลูกค้าถามหา" (ชีตลีด) กับ "ของที่เรามี" (สต๊อก)
  2. **ส่งแยกห้อง** — เคสHOT (พี่หมี) / เคสHOT (พี่ต๊าด) คนละห้อง เห็นเฉพาะงานตัวเอง

★★ หัวใจ: "ขาดตลาด" ไม่ใช่ความรู้สึก — คำนวณจากของจริง 2 ชุดที่มีอยู่แล้ว
   ลูกค้าถามหากี่ครั้ง (3 เดือนล่าสุด) ÷ จำนวนที่พร้อมขายตอนนี้
   → ถามเยอะแต่ไม่มีของ = ต้องรีบรับซื้อ

⚠️ กติกาชื่อรถที่ต้องรักษา (เสียเวลาไป 3 รอบกว่าจะได้ 90%+ ตอนทำ)
   - **พจนานุกรมรุ่นต้องมาจากฝั่งที่สะอาดที่สุดฝั่งเดียว** = ชื่อในชีตลีด (เป็น dropdown)
     เคยปล่อยให้ชื่อจากสต๊อก ("Corolla Altis ALTIS ปี 14-18") เข้าไปเป็นคำในพจนานุกรมด้วย
     → คีย์ 2 ฝั่งไม่มีวันตรงกัน **Revo โชว์ "มีในสต๊อก 0 คัน" ทั้งที่มีจริง**
   - **ห้าม NFKC กับข้อความไทย** — มันแยกสระ "ำ" (U+0E33) เป็น ' ํ'+'า'
     คำว่า "ดำ" ในลิสต์สีเลยเทียบกับ "ดํา" ที่ได้จากข้อความไม่ตรง (ใช้ NFC)
   - **เทียบแบบ "หารุ่นในข้อความ" ไม่ใช่ "ตัดขยะออกแล้วหวังว่าที่เหลือคือรุ่น"**
     คนกรอกพิมพ์อิสระมาก ("MAZDA 2 ปี22 ขาว" · "Honda City 1.0 เทอร์โบ รถปี21")
     ตัดขยะยังไงก็ไม่มีวันครบ · วัดจริง: วิธีตัดขยะได้ 35% · วิธีพจนานุกรมได้ 90%
"""
import re
import unicodedata

# กี่เดือนล่าสุดที่นับเป็น "ความต้องการตอนนี้" (ทั้งปีจะกลบของใหม่ที่เพิ่งมาแรง)
DEMAND_MONTHS = 3
# ถามหาน้อยกว่านี้ = เสียงรบกวน ไม่ใช่สัญญาณตลาด
MIN_DEMAND = 30
# สูงสุดกี่คันต่อข้อความ (เห็น 20 รายการแล้วท้อ ไม่ทำสักอัน — บทเรียนเดิมของ followup)
MAX_CARS = 6
# รุ่นที่ขาดหนักสุด โชว์ท้ายข้อความกี่รุ่น
TOP_GAP = 5
# "เพิ่งรับเข้ามา" นับย้อนหลังกี่วัน — เผื่อช่วงที่สต๊อกยังตามไม่ทัน (ดู `recent_bought`)
BOUGHT_DAYS = 14

# ห้อง LINE ของแต่ละคน (บอทตัวส่งอยู่ครบทั้ง 2 ห้องแล้ว · ยืนยัน 25/09)
#   แก้ได้ที่ KV "purchase_report_rooms" = {"<group id>": "<ชื่อคนจัดซื้อ>"} โดยไม่ต้อง deploy
ROOMS = {
    "C0ad44e22acf81cd6af619da15ffb363d": "พี่หมี",
    "C6a6450337d5588fdb0882f57d2a09cd4": "พี่ต๊าด",
}

_BRANDS = ("toyota", "honda", "isuzu", "nissan", "mazda", "mitsubishi", "ford", "mg",
           "suzuki", "chevrolet", "hyundai", "kia", "benz", "bmw", "subaru", "lexus",
           "mercedes", "volvo", "peugeot", "haval", "ora", "byd", "neta", "gwm")
# ค่าที่ไม่ใช่ชื่อรถในคอลัมน์รถของชีตลีด (คนกรอกสถานะ/ข้อความลงช่องรุ่น)
_BAD_MODEL = ("ลูกค้า", "ไม่ระบุ", "ไม่ได้ทำ", "ไม่มีรุ่น", "อื่น", "รถรุ่น", "กับ", "ส่งรูป")
_YEAR = re.compile(r"ปี\s*\d{2,4}|\b(?:19|20)\d{2}\b|\d+\s*[-–]\s*\d+")


def _compact(s, drop_brand=False):
    """ข้อความ → ตัวพิมพ์เล็กติดกัน ไม่มีปี/ช่องว่าง (ใช้ถามว่า "รุ่นนี้อยู่ในข้อความไหม")"""
    s = unicodedata.normalize("NFC", str(s or "")).lower()   # NFC — NFKC แยกสระ "ำ" พัง
    s = _YEAR.sub(" ", s)
    if drop_brand:
        for b in _BRANDS:
            s = re.sub(r"\b%s\b" % b, " ", s)
    return re.sub(r"[^0-9a-zก-๙]+", "", s)


def _demand_by_model():
    """ลูกค้าถามหารุ่นไหนกี่ครั้ง (N เดือนล่าสุด) — อ่านจากผลสรุปแดชบอร์ดที่คำนวณไว้แล้ว

    คืน `({คีย์รุ่น: จำนวนครั้ง}, {คีย์รุ่น: ชื่อที่เอาไว้โชว์})`
    """
    from .cache_store import get_kv
    from .fetch_dashboard import bangkok_now

    blob = get_kv("main") or {}
    data = blob.get("data", blob) if isinstance(blob, dict) else {}
    by_month = (data or {}).get("leadCarsByMonth") or {}
    if not by_month:
        return {}, {}

    now = bangkok_now()
    months = {str(((now.month - i - 1) % 12) + 1) for i in range(DEMAND_MONTHS)}
    demand, shown = {}, {}
    for mon, cars in by_month.items():
        if str(mon) not in months or not isinstance(cars, dict):
            continue
        for name, n in cars.items():
            name = str(name or "").strip()
            if len(name) < 2 or any(b in name for b in _BAD_MODEL):
                continue
            k = _compact(name, drop_brand=True)
            if not (2 <= len(k) <= 22):
                continue
            demand[k] = demand.get(k, 0) + int(n or 0)
            shown.setdefault(k, name)          # ชื่อแรกที่เจอ = ชื่อไว้โชว์ให้คนอ่าน
    return _fold_rare(demand, shown)


def _fold_rare(demand, shown):
    """ยุบ "ชื่อเดียวกันเขียนยาวกว่า" ที่แทบไม่มีใครถามหา เข้าไปในชื่อหลัก

    ★★ บั๊กที่เจอ 26/09 (ตอนตัวเลข Altis ไม่ตรงกับที่วัดไว้ จึงไล่ทีละคัน):
       ชีตลีดมีทั้ง **"Altis" (ถามหา 101)** และ **"Corolla Altis" (ถามหา 1)** = คนละคีย์
       · รถในสต๊อกชื่อ `Corolla Altis ALTIS ปี 14-18` → กติกา "เทียบรุ่นยาวก่อน" เลือก
         `corollaaltis` ชนะ `altis` → ไปลงคีย์ที่ดีมานด์ = 1 ซึ่งต่ำกว่า `MIN_DEMAND`
         **→ หายจากตารางทั้งคัน และคีย์ `altis` เหลือ "พร้อมขาย 0" ทั้งที่มีรถ 3 คัน**
       · กติกา "ยาวก่อน" ยังต้องมีอยู่ (`civicfc` ต้องชนะ `civic`) — แต่ต้องยุบเฉพาะ
         **คีย์ยาวที่ดีมานด์ต่ำกว่าเกณฑ์** เท่านั้น · `almeraturbo` (33) ไม่ถูกยุบ = ถูกต้อง
         เพราะ Almera Turbo เป็นรุ่นต่างจาก Almera จริงๆ
    """
    big = [k for k, v in demand.items() if v >= MIN_DEMAND]
    for k in sorted(demand, key=len, reverse=True):
        if demand[k] >= MIN_DEMAND:
            continue
        host = max((b for b in big if b != k and b in k), key=lambda b: demand[b], default="")
        if host:
            demand[host] += demand.pop(k)
            shown.pop(k, None)
    return demand, shown


_PLATE = re.compile(r"^\s*(\d{0,3})\s*([ก-ฮ]{1,3})\s*(\d{1,4})")


def norm_plate(s):
    """ทะเบียนไทยให้เทียบข้ามระบบได้ — เอาแค่ "เลข+อักษร+เลข" ทิ้งชื่อจังหวัดที่ติดมา

    ★ ในชีตกรอกเป็น `5ขล739 กรุงเทพมหานคร` · `4ขย4388กท` · `1 ขด116 กรุงเทพมหานคร`
      (จังหวัดมีทั้งเต็ม/ย่อ/ติดกัน · บางคันเว้นวรรคกลางทะเบียนเอง) · ฝั่งสต๊อกเป็น `8กษ1332` เปล่าๆ
      → **ไม่ตัดจังหวัดออกก่อน จับคู่ได้ 5 จาก 466 คัน · ตัดแล้วได้ 163** (วัดจริง 26/09)
    """
    m = _PLATE.match(str(s or "").strip())
    if m:
        return "%s%s%s" % m.groups()
    return re.sub(r"[\s\-.()]", "", str(s or ""))


def _plate_models():
    """`{ทะเบียน: ชื่อรุ่นสะอาดจากชีต}` — จากบล็อกจัดซื้อรับเข้า (AR ทะเบียน + AV รถตามสูตร)

    ★★ 26 ก.ย.69 (เจ้าของสั่ง *"ลองเทียบทะเบียนดู มันเป็นข้อมูลชุดเดียวกัน"*)
       ชื่อรุ่นในตาราง `Car` มาจาก **Car Spend ซึ่งเป็นป้ายหมวด ไม่ใช่รุ่นจริง**:
       รถปี 2023 ยังถูกป้ายว่า `Civic FC ปี 16-20 FC ปี 16-20` · Corolla Cross ถูกป้ายว่า `Corolla Altis`
       · Almera Turbo เขียนแค่ `Almera` · **ไม่มีคำว่า FE/FK เลยสักคัน** ทั้งที่ฝั่งลูกค้าถามหาแยก 4 ชื่อ
       → เทียบด้วยชื่อ **ไม่มีทางตรง** แต่ทะเบียนเป็นค่าเดียวกันทั้ง 2 ฝั่ง
       · **ห้ามเดารุ่นจากปีรถ** — วัดจริง `2ขล9894` ปี 2021 ชีตบอก **Civic FE** (เจน 11 เปิดกลางปี 2021)
         กฎ "FE = 2022+" ที่เคยคิดไว้จะจับผิดทันที
    """
    from .cache_store import get_kv

    blob = get_kv("main") or {}
    data = blob.get("data", blob) if isinstance(blob, dict) else {}
    out = {}
    for r in (data or {}).get("boughtCars") or []:
        if not isinstance(r, (list, tuple)) or len(r) < 7:
            continue          # แคชรุ่นก่อน 26/09 ยังไม่มีช่องทะเบียน
        k, name = norm_plate(r[6]), str(r[4] or "").strip()
        if k and name:
            out[k] = name     # แถวเดือนหลังชนะ (ข้อมูลใหม่กว่า)
    return out


def _stock_rows():
    """`[(brand, model, stage, plate)]` ของรถที่ยังไม่ขาย · อ่านไม่ได้ = `None`

    แยกเป็นฟังก์ชันเพื่อ **พรีวิว/เทสต์ด้วยสต๊อกจริงจากเซิร์ฟเวอร์บนเครื่อง dev ได้**
    (เครื่อง dev เป็น SQLite ว่าง ถ้าอ่านตรงจะได้ "ทุกรุ่น 0 คัน" ซึ่งเป็นภาพลวง)
    """
    try:
        from cars.models import Car
        return list(Car.objects.exclude(status="sold")
                    .values_list("brand", "model", "stage", "plate"))
    except Exception:
        return None


# ผลการนับสต๊อกรอบล่าสุด — `{show, named, unnamed}` · ให้รายงานบอกได้ว่า "ยังมีอีก N คันที่ไม่รู้รุ่น"
STOCK_INFO = {}


def _stock_by_model(vocab):
    """สต๊อกของเราแยกรุ่น — `({คีย์: พร้อมขาย}, {คีย์: มีทั้งหมด})` · อ่านไม่ได้ = ว่าง

    ชื่อรุ่นเอาจาก **ชีต (จับด้วยทะเบียน) ก่อน** แล้วค่อยตกไปใช้ชื่อของ Car Spend
    """
    rows = _stock_rows()
    if rows is None:
        return {}, {}
    names = _plate_models()
    show, total, n_show, n_named, n_out = {}, {}, 0, 0, 0
    for brand, model, stage, plate in rows:
        if stage == "show":
            n_show += 1
        sheet = names.get(norm_plate(plate))
        if sheet:
            k = match_model(sheet, vocab)
            if stage == "show":
                n_named += 1
        else:
            k = match_model("%s %s" % (brand or "", model or ""), vocab)
        if not k:
            # รุ่นที่ตลาดไม่ได้ถามหาเลย (BMW 116i / Leaf / March) — ไม่มีคีย์ให้ลง
            if stage == "show":
                n_out += 1
            continue
        total[k] = total.get(k, 0) + 1
        if stage == "show":
            show[k] = show.get(k, 0) + 1
    STOCK_INFO.clear()
    # `uncounted` = พร้อมขายแต่ไม่ได้อยู่ในตารางเลย (ต่างจาก `unnamed` ที่แค่ไม่มีชื่อจากชีต
    # แต่ยังนับได้จากชื่อ Car Spend) — เขียนบอกผู้ใช้ต้องใช้ตัวนี้ ไม่ใช่ unnamed
    STOCK_INFO.update(show=n_show, named=n_named, unnamed=n_show - n_named, uncounted=n_out)
    return show, total


def recent_bought(days, vocab):
    """รุ่นที่ "เพิ่งรับเข้ามาแล้ว" ในช่วงนี้ — `{คีย์รุ่น: จำนวนคัน}`

    ★★ ทำไมจำเป็น: ช่อง "พร้อมขาย" มาจากตาราง `Car` ซึ่งเติมด้วย `sync_carspend`
       ที่ **ยังไม่ได้ตั้ง cron** (วัดจริง 25/09: รถที่รับเข้าวันที่ 23 ยังไม่มีในตาราง)
       → รุ่นที่จัดซื้อเพิ่งหามาได้ จะยังขึ้นว่า "ขาดตลาด" แล้วทีมไปวิ่งหาซ้ำ
       ตัวนี้อ่าน **บล็อกจัดซื้อรับเข้า (AP–AV) ในชีตเดียวกับเคส** ที่ทีมกรอกเองวันต่อวัน
       → ทันกว่าสต๊อกหลายวัน · ใช้ช่อง **AV "รถตามสูตร"** (สะอาด ไม่ต้องเดา)
    """
    import datetime

    from .cache_store import get_kv
    from .fetch_dashboard import bangkok_now

    blob = get_kv("main") or {}
    data = blob.get("data", blob) if isinstance(blob, dict) else {}
    rows = (data or {}).get("boughtCars") or []
    now = bangkok_now()
    today = datetime.date(now.year, now.month, now.day)

    out = {}
    for r in rows:
        if not isinstance(r, (list, tuple)) or len(r) < 5:
            continue          # แถวจากแคชรุ่นก่อน 25/09 (ยังไม่มี AV) — ข้าม ไม่เดาจากอะไรอื่น
        try:
            m, d = int(r[0]), int(r[1])
            when = datetime.date(now.year if m <= now.month else now.year - 1, m, d)
        except Exception:
            continue
        age = (today - when).days
        if age < 0 or age > days:
            continue
        k = match_model(r[4] or (r[5] if len(r) > 5 else ""), vocab)
        if k:
            out[k] = out.get(k, 0) + 1
    return out


def match_model(text, vocab):
    """หาว่าในข้อความมีรุ่นไหนอยู่ — คืนรุ่นที่ "ยาวที่สุด" ที่เจอ

    ยาวที่สุดสำคัญ: `civicfc` ต้องชนะ `civic` ไม่งั้น Civic FC ทุกคันถูกนับเป็น Civic เฉยๆ
    """
    c = _compact(text)
    for v in vocab:                        # vocab เรียงยาว→สั้นมาแล้ว
        if v in c:
            return v
    return ""


def market_gap():
    """รุ่นไหน "ตลาดหา แต่เราไม่มีของ" — เรียงขาดมากสุดก่อน

    คืน list ของ dict: `{key, name, demand, show, total, recent, score}`
    `score = ถามหา ÷ (พร้อมขาย + เพิ่งรับเข้า + 1)`
      - +1 กันหารศูนย์ และทำให้ "มี 0 คัน" แรงกว่า "มี 1 คัน"
      - **+ เพิ่งรับเข้า** — รุ่นที่จัดซื้อหามาได้แล้วเมื่อไม่กี่วันก่อน ต้องหยุดขึ้นว่าขาด
        แม้สต๊อกจะยังไม่อัปเดต (ดู `recent_bought`)
    """
    demand, shown = _demand_by_model()
    if not demand:
        return []
    vocab = sorted(demand, key=len, reverse=True)
    show, total = _stock_by_model(vocab)
    bought = recent_bought(BOUGHT_DAYS, vocab)

    out = []
    for k, d in demand.items():
        if d < MIN_DEMAND:
            continue
        s, rec = show.get(k, 0), bought.get(k, 0)
        out.append({"key": k, "name": shown.get(k, k), "demand": d, "show": s,
                    "total": total.get(k, 0), "recent": rec,
                    "score": d / (s + rec + 1.0)})
    out.sort(key=lambda r: -r["score"])
    return out


def rank_cases(cases, gap=None):
    """ใส่ "รุ่น + คะแนนขาดตลาด" ให้เคส แล้วเรียงว่าควรโทรใครก่อน

    ลำดับความสำคัญ (เรียงจากหนักไปเบา):
      1. **ยังไม่ได้โทรเลย** — มาก่อนเสมอ ไม่ว่ารุ่นอะไร (งานที่ยังไม่เริ่ม = เสี่ยงหลุดมือสุด)
      2. **รุ่นที่ขาดตลาด** — ของที่ลูกค้าถามหาแต่เราไม่มี
      3. **ดองนาน** — ยิ่งค้างนานยิ่งเย็น

    ★ 25 ก.ย.69 — จับรุ่นจากช่อง **S "รถตามสูตร"** ก่อน แล้วค่อยเดาจาก D (ที่คนพิมพ์อิสระ)
      ทีมกรอก S ไว้ 98% และเป็นคำตัดสินของคน → ทำสิ่งที่ตัวเดาทำไม่ได้:
      "Toyota Yaris ปี19 เทาดำ" → **New Yaris 5 ประตู** · "CIVIC ปี16 ดำ" → **Civic FC**
      (คนละรุ่นกันในสายตาตลาด แต่ข้อความที่คนพิมพ์ไม่ได้บอกไว้)
    """
    if gap is None:
        gap = market_gap()
    by_key = {g["key"]: g for g in gap}
    vocab = sorted(by_key, key=len, reverse=True)

    for c in cases:
        k = match_model(c.get("model_std"), vocab) or match_model(c.get("car"), vocab)
        g = by_key.get(k)
        c["model"] = g["name"] if g else ""
        c["gap"] = g
        c["score"] = (0 if c.get("talked") else 1000) + (g["score"] if g else 0) + c.get("age", 0)
    return sorted(cases, key=lambda c: -c["score"])


_NUM = "①②③④⑤⑥"


def _not_ready(g):
    """" (มีอีก N คัน แต่ยังไม่พร้อมขาย)" — กัน "0 คัน" ถูกอ่านว่า "ไม่มีรถรุ่นนี้เลย"

    ★ เจ้าของทักตรงนี้เอง (*"ทำไมรถ Civic จะมีศูนย์คันได้ยังไง"*) — วัดจริง: Civic FE พร้อมขาย 0
      **ถูกแล้ว** แต่เรามีรถรุ่นนั้น 4 คัน ติดจอง/ซ่อม/รอปิดการขายอยู่ · ไม่เขียนกำกับ คนอ่านสรุปว่าระบบพัง
    """
    n = (g.get("total") or 0) - (g.get("show") or 0)
    return " (มีอีก %d คัน ยังไม่พร้อมขาย)" % n if n > 0 else ""


def _case_lines(c, i):
    """1 เคส → หลายบรรทัด (ชื่อ/รถ/เบอร์/เหตุผลที่ควรโทร)"""
    L = ["%s %s" % (_NUM[i] if i < len(_NUM) else "%d." % (i + 1),
                    (c.get("car") or "(ไม่ระบุรุ่น)")[:44])]
    who = " · ".join(x for x in ((c.get("name") or "")[:22], c.get("phone") or "") if x)
    if who:
        L.append("   %s" % who)
    g = c.get("gap")
    if g:
        L.append("   %s — ตลาดถามหา %d ครั้ง · เรามีพร้อมขาย %d คัน%s"
                 % (g["name"][:16], g["demand"], g["show"], _not_ready(g)))
        if g.get("recent"):
            L.append("   (รุ่นนี้เพิ่งรับเข้ามาแล้ว %d คัน)" % g["recent"])
    L.append("   %s · ค้าง %d วัน" % (
        "ยังไม่ได้โทร" if not c.get("talked") else "คุยแล้ว รอตัดสิน", c.get("age", 0)))
    return L


def build_room_reports(days=7, max_cars=MAX_CARS, rooms=None, gap=None, cases=None):
    """ข้อความรายห้อง + สรุปให้แอดมิน — คืน `{"rooms": [(gid, ชื่อคน, ข้อความ)], "admin": str}`

    ห้องไหนไม่มีเคสค้างเลย = **ไม่ส่ง** (ข้อความ "วันนี้ไม่มีงาน" ทุกวันจะถูกมองข้ามในสัปดาห์เดียว)
    """
    from .purchase_followup import fetch_open_cases

    rooms = rooms or _rooms()
    # รับ cases/gap จากข้างนอกได้ — ใช้ตอนพรีวิวด้วยข้อมูลจากเซิร์ฟเวอร์จริงบนเครื่อง dev
    cases = fetch_open_cases(days=days) if cases is None else cases
    gap = market_gap() if gap is None else gap
    ranked = rank_cases(cases, gap)

    by_owner = {}
    for c in ranked:
        by_owner.setdefault(c.get("owner") or "(ไม่ระบุ)", []).append(c)

    gap_lines = []
    if gap:
        gap_lines = ["รถที่ขาดหนักสุดตอนนี้ (%d เดือนล่าสุด)" % DEMAND_MONTHS]
        for g in gap[:TOP_GAP]:
            tail = " · เพิ่งรับเข้า %d" % g["recent"] if g.get("recent") else ""
            gap_lines.append("  %-12s ถามหา %3d · พร้อมขาย %d%s%s"
                             % (g["name"][:12], g["demand"], g["show"], tail, _not_ready(g)))
        if STOCK_INFO.get("uncounted"):
            gap_lines.append("  (พร้อมขายอีก %d คันเป็นรุ่นที่ตลาดไม่ได้ถามหา ไม่ได้นับในตารางนี้)"
                             % STOCK_INFO["uncounted"])

    out = []
    for gid, person in rooms.items():
        mine = by_owner.get(person) or []
        if not mine:
            continue
        no_call = [c for c in mine if not c.get("talked")]
        L = ["เคสรับซื้อ %d วันล่าสุด — %s" % (days, person), ""]
        L.append("ค้างอยู่ %d คัน · ยังไม่ได้โทร %d คัน" % (len(mine), len(no_call)))
        L.append("")
        L.append("ควรโทรก่อน (เรียงตามรถที่ตลาดกำลังหา)")
        L.append("")
        for i, c in enumerate(mine[:max_cars]):
            L += _case_lines(c, i) + [""]
        if gap_lines:
            L += gap_lines + [""]
        L.append("─" * 16)
        L.append('คุยจบแล้วกรอกช่อง "รับซื้อ/ไม่รับซื้อ" ในชีต')
        L.append("แล้วชื่อจะหายจากรายการเองค่ะ")
        out.append((gid, person, "\n".join(L)))

    admin = ""
    if by_owner:
        A = ["สรุปงานจัดซื้อ %d วันล่าสุด" % days, ""]
        for person in sorted(by_owner):
            cs = by_owner[person]
            A.append("%-8s ค้าง %3d คัน · ยังไม่ได้โทร %d"
                     % (person, len(cs), sum(1 for c in cs if not c.get("talked"))))
        if gap_lines:
            A += [""] + gap_lines
        admin = "\n".join(A)
    return {"rooms": out, "admin": admin}


def _rooms():
    """ห้อง LINE ของแต่ละคน — KV ทับค่าใน `ROOMS` ได้ (เปลี่ยนคน/ห้องโดยไม่ต้อง deploy)"""
    try:
        from .cache_store import get_kv
        v = get_kv("purchase_report_rooms") or {}
        v = v.get("data", v) if isinstance(v, dict) else {}
        if isinstance(v, dict) and v:
            return {str(k): str(n) for k, n in v.items() if k and n}
    except Exception:
        pass
    return dict(ROOMS)
