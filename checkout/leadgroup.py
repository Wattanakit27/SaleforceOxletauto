# -*- coding: utf-8 -*-
"""อ่าน "กลุ่มจ่ายเบอร์" แล้วเก็บเป็นความต้องการลูกค้า — ก.ย.69 (ข้อ 4 ที่เจ้าของสั่ง)

กติกาสังเคราะห์จากข้อความจริง 2,013 ข้อความในกลุ่ม **"ห้องจ่ายเบอร์ บ้านเก่า"**
และ 570 ข้อความใน **"ห้องจ่ายเบอร์ REJECT"**:

1. **ใบจ่ายลีด** — ขึ้นต้น `Ac Lead No.` แล้วตามด้วยช่องต่างๆ บรรทัดละช่อง::

       Ac Lead No.   TLD9-7376
       Ads  :
       ชื่อ Account: โมจิโม
       ID LINE : maraamo112
       เบอร์โทร :
       ช่องทาง  : Live tiktok ช่องขายบอส
       รถ
       ไลฟ์ :   live sale
       ติดต่อได้เลยนะครับ  @เซลมัท OxletAuto

2. **อัปเดตรายลีด** — `<เลขลีด> <ข้อความ>` เช่น `7364 รอตอบ` · `7327 ยังไม่รับสาย`
3. **ปิดเคส (ห้อง REJECT)** — `<เลข>/1 <เหตุผล>` เช่น `6480/1 ได้รถแล้วครับ`
4. **★ รถที่เราไม่มี** — `7260 สนใจแคมรี่ หรือ accord ปี 12-14 ราคาไม่แรงมาก … ไม่มีรถครับ`
   ← อันนี้คือที่เจ้าของชี้ให้เก็บ: *"ลูกค้าถามหารถที่เรายังไม่มี เราก็เก็บไว้ก่อน"*

**ทำไมใช้ regex ตรงนี้ (ต่างจาก [need_extract.py](need_extract.py) ที่ใช้ AI)** — ใบจ่ายลีด
เป็นแบบฟอร์มที่แอดมินก๊อปเทมเพลตเดิมทุกครั้ง โครงคงที่จริง · ส่วนแชทลูกค้าเป็นภาษาพูด
อิสระ regex เอาไม่อยู่ · ข้อความอัปเดตแบบข้อ 4 เป็นภาษาพูด → ส่งต่อให้ AI สรุปได้ (`--ai`)

⚠️ **อ่านอย่างเดียว ไม่ส่งอะไรกลับเข้ากลุ่มและไม่ทักลูกค้า**
"""
from __future__ import annotations

import logging
import re

from .models import CustomerNeed, GroupChat

log = logging.getLogger(__name__)

# ชื่อกลุ่มที่อ่าน — ตรงกับที่เก็บไว้จริงใน checkout_groupchat
GROUP_HINTS = ["จ่ายเบอร์"]

# ── ใบจ่ายลีด ──────────────────────────────────────────────────────
_LEAD_NO = re.compile(r"Ac\s*Lead\s*No\.?\s*[:：]?\s*([A-Za-z]{0,6}\d?-?\d{3,6})", re.I)
_FIELDS = {
    "ads": ["ads"],
    "account": ["ชื่อ account", "ชื่อaccount"],
    "name": ["ชื่อลูกค้า"],
    "line_id": ["id line", "idline", "ไอดีไลน์"],
    "line_name": ["ชื่อไลน์"],
    "phone": ["เบอร์โทร", "เบอร์"],
    "channel": ["ช่องทาง"],
    "car": ["รถ"],
    "live": ["ไลฟ์"],
    "more": ["เพิ่มเติม"],
}
# `7364 รอตอบ` · `6480/1 ได้รถแล้วครับ` — เลขลีดต้องอยู่ต้นข้อความเท่านั้น
_UPDATE = re.compile(r"^\s*(\d{3,6})\s*(?:/\d+)?\s+(.{3,})$", re.S)

# "เราไม่มีรถที่เขาหา" — เก็บรอไว้ได้
NO_CAR = ["ไม่มีรถ", "รถไม่มี", "ไม่มีรุ่น", "ไม่มีคัน", "ยังไม่มีรถ", "หารถไม่ได้"]
# เคสที่จบจริง ไม่ต้องรอ
DONE_HINTS = {
    CustomerNeed.RJ_LOST: ["ได้รถแล้ว", "ซื้อที่อื่น", "ออกรถกับที่อื่น", "ไม่เปลี่ยนรถแล้ว",
                           "ไม่ขายแล้ว", "ปิดการขาย"],
    CustomerNeed.RJ_CREDIT: ["เครดิตไม่ผ่าน", "ไฟแนนซ์ไม่ผ่าน", "ติดบูโร", "กู้ไม่ผ่าน",
                             "เช็คเครดิต"],
    CustomerNeed.RJ_SILENT: ["ไม่รับสาย", "ติดต่อไม่ได้", "เบอร์ผิด", "ปิดเครื่อง", "บล็อก"],
}


def parse_leadsheet(text: str) -> dict | None:
    """แกะใบจ่ายลีด → dict · คืน None ถ้าไม่ใช่ใบจ่ายลีด"""
    m = _LEAD_NO.search(text or "")
    if not m:
        return None
    out = {"lead_code": m.group(1).upper().replace(" ", ""), "assigned": ""}
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or ":" not in line and "：" not in line:
            continue
        head, _, val = line.replace("：", ":").partition(":")
        key = head.strip().lower()
        val = val.strip()
        for field, aliases in _FIELDS.items():
            if any(key == a or key.startswith(a) for a in aliases):
                if val and field not in out:
                    out[field] = val
                break
    tags = re.findall(r"@([^\s@]+)", text or "")
    if tags:
        out["assigned"] = tags[-1]          # คนที่ถูกจ่ายงานมักถูกแท็กท้ายสุด
    return out


def parse_update(text: str) -> tuple[str, str] | None:
    """`7364 รอตอบ` → ("7364", "รอตอบ") · คืน None ถ้าไม่ใช่รูปแบบนี้"""
    t = (text or "").strip()
    if not t or _LEAD_NO.search(t):
        return None                          # ใบจ่ายลีด ไม่ใช่ข้อความอัปเดต
    m = _UPDATE.match(t)
    if not m:
        return None
    return m.group(1), m.group(2).strip()


def classify(msg: str) -> tuple[str, bool]:
    """ข้อความอัปเดตนี้ = ปิดเคสเพราะอะไร · คืน (reject_kind, ปิดเคสไหม)

    **"ไม่มีรถ" มาก่อนเสมอ** — ประโยคอย่าง "ลูกค้าอยากได้ X ไม่มีรถครับ" มีคำว่า
    "ไม่รับสาย" ปนไม่ได้อยู่แล้ว แต่ถ้าวันหนึ่งมี ต้องให้ "ของขาด" ชนะ เพราะเก็บรอได้
    """
    low = (msg or "").lower()
    if any(k in low for k in NO_CAR):
        return CustomerNeed.RJ_NOCAR, True
    for kind, words in DONE_HINTS.items():
        if any(w in low for w in words):
            return kind, True
    return "", False


# ── แกะตัวเลขจากข้อความอัปเดต ────────────────────────────────────
# **ทำไมต้องแกะ** — ถ้าไม่รู้งบ ตอนจับคู่สต็อกจะไม่มีตัวกรองราคา แล้วเสนอรถ 489,000
# ให้คนที่บอกว่า "ไม่ข้าม 250000" (เจอจริงตอนทดสอบกับข้อมูล prod) = เสียเครดิตกับลูกค้า

# "แสน"/"ล้าน" ต้องคูณ — "3 แสน" = 300,000 ไม่ใช่ 3
_UNIT = [("ล้าน", 1000000), ("แสน", 100000), ("หมื่น", 10000), ("พัน", 1000)]
# ผ่อนต่อเดือนกับราคารถอยู่คนละสเกล ใช้แยกว่าเลขที่เจอเป็นอะไร
_MONTHLY_CAP = 40000
_PRICE_FLOOR = 40000


def _money(tok: str, unit: str = "") -> int:
    """'250000' / '250,000' / '3 แสน' / '2.5 แสน' → จำนวนเต็มบาท"""
    try:
        n = float(tok.replace(",", "").strip())
    except ValueError:
        return 0
    for name, mul in _UNIT:
        if name in unit:
            return int(n * mul)
    return int(n)


_NUM = r"(\d[\d,]*(?:\.\d+)?)\s*(ล้าน|แสน|หมื่น|พัน)?"
_BUDGET_RE = re.compile(
    r"(?:งบ|ราคา|ไม่เกิน|ไม่ข้าม|ไม่ถึง|ภายใน|วงเงิน|สด)\s*(?:ไม่เกิน|ไม่ข้าม)?\s*" + _NUM)
_MONTHLY_RE = re.compile(r"ผ่อน\D{0,8}" + _NUM)
# "ปี 18" · "ปี 2014" · "ปี 23-24" · "ปี 12-14"
_YEAR_RE = re.compile(r"ปี\s*(\d{2,4})\s*(?:[-–ถึง/]\s*(\d{2,4}))?")

# ชื่อรุ่นที่คนพิมพ์เป็นไทย — สต็อกเก็บเป็นอังกฤษ ไม่แปลงก็จับคู่ไม่เจอ
_TH_MODEL = {
    "แคมรี่": "camry", "แคมรี": "camry", "ซีวิค": "civic", "ซิตี้": "city",
    "ยาริส": "yaris", "อัลเมร่า": "almera", "ฟอร์จูนเนอร์": "fortuner",
    "วีออส": "vios", "แจ๊ส": "jazz", "แอคคอร์ด": "accord", "มาร์ช": "march",
    "อัลติส": "altis", "รีโว่": "revo", "วีโก้": "vigo", "ดีแม็ก": "d-max",
    "ปาเจโร่": "pajero", "เทอร์ร่า": "terra", "ครอส": "cross", "ซิตี": "city",
}


def _year4(v: int) -> int:
    """18 → 2018 · 67 → 2024 (พ.ศ. 2 หลัก) · 2014 → 2014"""
    if v >= 1000:
        return v - 543 if v > 2500 else v
    return 2500 + v - 543 if v >= 50 else 2000 + v


def parse_specs(text: str) -> dict:
    """แกะ งบ/ผ่อน/ปี/ชื่อรุ่น จากข้อความที่คนพิมพ์ — ไม่เจอก็คืนค่าว่าง ไม่เดา"""
    t = (text or "")
    out = {}

    m = _BUDGET_RE.search(t)
    if m:
        v = _money(m.group(1), m.group(2) or "")
        if v >= _PRICE_FLOOR:
            out["budget_max"] = v

    m = _MONTHLY_RE.search(t)
    if m:
        v = _money(m.group(1), m.group(2) or "")
        # "ผ่อน 7-8000" → regex จับ 7 มาก่อน · ค่าที่เล็กเกินไปถือว่าอ่านไม่ออก ทิ้ง
        if 1000 <= v <= _MONTHLY_CAP:
            out["monthly_max"] = v

    m = _YEAR_RE.search(t)
    if m:
        a = _year4(int(m.group(1)))
        b = _year4(int(m.group(2))) if m.group(2) else None
        if 1990 <= a <= 2100:
            out["car_year_min"] = a
            if b and a <= b <= 2100:
                out["car_year_max"] = b

    low = t.lower()
    for th, en in _TH_MODEL.items():
        if th in low:
            out["car_model"] = en
            break
    return out


def _find(lead_code: str) -> CustomerNeed | None:
    """หาเคสจากเลขลีด — เทียบด้วย **ตัวเลขท้าย** เพราะในกลุ่มพิมพ์แค่ `7364`
    แต่ใบจ่ายลีดเป็น `TLD9-7364`
    """
    tail = re.sub(r"\D", "", lead_code or "")[-4:]
    if not tail:
        return None
    return (CustomerNeed.objects
            .filter(source=CustomerNeed.GROUP, lead_code__endswith=tail)
            .order_by("-updated_at").first())


def ingest(limit: int = 4000) -> dict:
    """อ่านข้อความในกลุ่มจ่ายเบอร์ → สร้าง/อัปเดต `CustomerNeed` (source=group)"""
    from django.db.models import Q
    cond = Q()
    for hint in GROUP_HINTS:
        cond |= Q(group_name__icontains=hint)
    rows = list(GroupChat.objects
                .filter(chat_type=GroupChat.GROUP)
                .exclude(text="")
                .filter(cond)
                .order_by("sent_at", "id")[:limit])

    st = {"ข้อความ": len(rows), "ใบจ่ายลีด": 0, "อัปเดต": 0,
          "ไม่มีรถ (เก็บรอ)": 0, "ปิดเคส": 0, "ไม่เข้าเงื่อนไข": 0}

    for g in rows:
        text = g.text or ""
        sheet = parse_leadsheet(text)
        if sheet:
            st["ใบจ่ายลีด"] += 1
            code = sheet["lead_code"]
            need = (CustomerNeed.objects
                    .filter(source=CustomerNeed.GROUP, lead_code=code).first())
            if need is None:
                need = CustomerNeed(source=CustomerNeed.GROUP, lead_code=code)
            need.customer_name = (sheet.get("name") or sheet.get("account")
                                  or sheet.get("line_name") or "")[:120]
            need.contact = (sheet.get("phone") or sheet.get("line_id") or "")[:120]
            need.channel = (sheet.get("channel") or "")[:80]
            # ★ ช่อง "รถ" ในใบจ่ายลีดมักว่าง → ตกไปใช้ชื่อโฆษณา (Ads) ซึ่ง **บางทีก็เป็นชื่อรถ
            #   ("กองทัพ Nissan Almera" / "อัพเดท Camry") บางทีก็ไม่ใช่เลย ("ทำไมคนชลบุรีไม่ซื้อรถผมเลย")**
            #   → ใช้ได้แต่ต้องติดป้ายว่าไม่มั่นใจ ไม่งั้นตอนจับคู่สต็อกจะเอาชื่อโฆษณาไปหารถ
            # ★ และ **เขียนเฉพาะตอนยังว่าง** — ข้อความอัปเดต ("หา city hybrid ปี 23-24 ผ่อน 7-8000")
            #   บอกความต้องการจริงละเอียดกว่ามาก ห้ามให้ใบจ่ายลีดมาทับตอน ingest รอบถัดไป
            if not need.car_text:
                car, ads = (sheet.get("car") or "").strip(), (sheet.get("ads") or "").strip()
                need.car_text = (car or ads)[:300]
                need.confidence = "high" if car else ("low" if ads else "")
            if sheet.get("ads"):
                need.note = ("โฆษณา: %s" % sheet["ads"])[:200]
            need.seller = (sheet.get("assigned") or "")[:80]
            need.evidence = text[:1000]
            if need.status == CustomerNeed.NEW and need.seller:
                need.status = CustomerNeed.LEAD      # ถูกจ่ายให้เซลล์แล้ว = เป็นลีด
            need.save()
            continue

        up = parse_update(text)
        if not up:
            st["ไม่เข้าเงื่อนไข"] += 1
            continue
        st["อัปเดต"] += 1
        lead_no, msg = up
        kind, closed = classify(msg)
        need = _find(lead_no)
        if need is None:
            if not closed:
                continue                     # อัปเดตทั่วไปของลีดที่ไม่รู้จัก = ข้าม
            # ★ ไม่มีใบจ่ายลีดในระบบ แต่ข้อความบอกว่า "ไม่มีรถ" = ยังมีค่า เก็บไว้
            need = CustomerNeed(source=CustomerNeed.GROUP, lead_code=lead_no)
        if closed:
            need.mark_reject(kind, msg)
            if kind == CustomerNeed.RJ_NOCAR:
                st["ไม่มีรถ (เก็บรอ)"] += 1
                # ข้อความนี้แหละคือ "รถที่ลูกค้าหาแล้วเราไม่มี" — เชื่อถือกว่าชื่อโฆษณาเสมอ
                need.car_text = msg[:300]
                need.confidence = "high"
                # ★ แกะ งบ/ผ่อน/ปี/ชื่อรุ่นไทย ออกมาด้วย ไม่งั้นตอนจับคู่สต็อกไม่มีตัวกรองราคา
                #   แล้วจะเสนอรถ 489,000 ให้คนที่บอกว่า "ไม่ข้าม 250000" (เจอจริงกับข้อมูล prod)
                for k, v in parse_specs(msg).items():
                    setattr(need, k, v)
            else:
                st["ปิดเคส"] += 1
        need.evidence = (need.evidence or "")[:600] + "\n[อัปเดต] " + msg[:300]
        need.note = (need.note or "")[:200]
        need.save()
    return st
