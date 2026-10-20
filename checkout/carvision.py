# -*- coding: utf-8 -*-
"""ลูกค้าพูดถึงรถในรูป ("จัดไฟแนนซ์ครับ สนใจคันล่างสุด") → ให้ AI ดูรูปที่ส่งในแชทก่อนหน้า บอก **ยี่ห้อ + รุ่น**

★ 20 ต.ค.69 เจ้าของสั่ง *"ถ้ากล่าวถึงรูป ฉันอยากให้วิเคราะห์รูปออกมา เช่น มันเป็นรถรุ่นไหนคร่าวๆ ก็ได้
   แบรนด์แล้วก็รุ่น ไม่ต้องใส่รุ่นย่อย เพราะว่าวิเคราะห์ลึกไป"*
   เคสจริง (เพจบ้านเก่า 20 ต.ค. 21:04): แอดมินส่งรูปรถ 9 รูปติดกัน → 21:11 ลูกค้า "สนใจคันล่างสุด" = รูปสุดท้าย
   ใบเก็บลีดขึ้น "รถ : Civic FE" (จากการ์ดโฆษณา) ซึ่งไม่ใช่คันที่ลูกค้าเลือก

  · ทำเมื่อ **ข้อความล่าสุดของลูกค้าอ้างถึงรถในรูป** (`REF_RE` — คันนี้/คันล่างสุด/คันสีขาว/ตามรูป/รูปนี้ …)
    **และมีรูปในแชทก่อนหน้า** (`WINDOW_MIN` นาที · ไม่เกิน `MAX_IMAGES` รูป) — ไม่มีรูป = ไม่เรียก AI
  · ส่งรูปเรียงตามลำดับในแชท (รูปแรก = บนสุด · รูปสุดท้าย = ล่างสุด) + ข้อความลูกค้า → Gemini (โมเดลเบา)
    ตอบ JSON {brand, model, image, confidence} · มั่นใจไม่ถึง `MIN_CONF` / ดูไม่ออก = ไม่เติมอะไร
  · ผลลงช่อง **"รถลูกค้าถาม"** (ที่มา `รูป`) + "CAR / สูตร" ถ้าตรงตัวเลือกในชีต — **ช่องที่คนแก้/ใบจ่ายลีดใส่ไว้ไม่แตะ**
    · แทนค่าที่มาจากการ์ดโฆษณา/ค่าตั้งต้นได้ (ลูกค้าเลือกคันจากรูปชัดกว่า) · เก็บผลที่ `ChatLead.auto["_vision"]`
  · ใบเก็บลีด/ใบซ้อมเห็นรถคันนี้ทันที · ส่งใบไปแล้ว = ใบอัปเดตตามกติกาเดิม (`autolead.update_chat`)
  · 1 ข้อความอ้างรูป = เรียก AI ครั้งเดียว (`auto["_vision_done"]`) · ทำใน thread ไม่หน่วงตัวรับข้อความ
  · รูปส่วนใหญ่เป็นรูปรถที่ร้านส่งเอง · รูปที่ลูกค้าส่งนับเฉพาะที่ส่งใกล้ข้อความ (เผื่อแคปรถจากที่อื่นมาถาม)
    ส่งเฉพาะรูป (ย่อ ≤1024px) ไม่ส่งชื่อ/เบอร์ลูกค้า · ไม่มี GEMINI_API_KEY = ปิดเงียบ
"""
from __future__ import annotations

import base64
import io
import json
import re
import threading
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

KEY = "_vision"
DONE_KEY = "_vision_done"
SRC = "รูป"
WINDOW_MIN = 180          # รูปที่ส่งก่อนข้อความลูกค้าไม่เกินกี่นาที
AFTER_MIN = 5             # ลูกค้าพิมพ์ก่อนแล้วส่งรูปตาม
CUST_IMG_MIN = 30         # รูปที่ "ลูกค้า" ส่ง นับเฉพาะที่ใกล้ข้อความอ้างรูป (รูปลูกค้าอาจเป็นเอกสาร)
RECENT_MIN = 30           # ข้อความอ้างรูปเก่ากว่านี้ไม่ทำ (ตัวเรียกเป็นข้อความที่เพิ่งเข้า)
MAX_IMAGES = 10
MIN_CONF = 0.5
MAX_SIDE = 1024
DONE_MAX = 20
_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# คำที่ลูกค้าใช้ชี้รถในรูป — ต้องมีรูปในแชทด้วยถึงจะทำ (ไม่งั้น "คันนี้" อาจหมายถึงรถในโฆษณา/ที่คุยกันอยู่)
_NUM = r"(?:\d+|หนึ่ง|สอง|สาม|สี่|ห้า|หก|เจ็ด|แปด|เก้า|สิบ)"
REF_RE = re.compile(
    r"(?:คัน|อัน|ตัว)\s*(?:นี้|นั้น|นี่|โน้น|ล่าง\s*สุด|ล่าง|บน\s*สุด|บน|แรก|สุดท้าย|ซ้าย|ขวา|กลาง|"
    r"ที่\s*" + _NUM + r"|ที่\s*ส่ง|ใน\s*รูป|ใน\s*ภาพ|สี\s*[ก-๙a-z]{2,8})|"
    r"(?:ตาม|ใน|จาก)\s*(?:รูป|ภาพ)|(?:รูป|ภาพ)\s*(?:นี้|นั้น|ที่\s*ส่ง|ล่าง|บน|แรก|สุดท้าย|ที่\s*" + _NUM + r")|"
    r"แบบ\s*(?:นี้|ใน\s*รูป)", re.I)

PROMPT = (
    "คุณเป็นผู้เชี่ยวชาญรถยนต์มือสอง รูปด้านล่างคือรูปที่ส่งกันในแชทของร้านขายรถมือสอง เรียงตามลำดับในแชท "
    "(รูปที่ 1 อยู่บนสุด รูปสุดท้ายอยู่ล่างสุด · \"ร้าน\" = รูปรถที่ร้านส่งให้ลูกค้าดู · \"ลูกค้า\" = รูปที่ลูกค้าส่งมา)\n"
    "ลูกค้าพิมพ์ว่า: \"{text}\"\n"
    "ลูกค้าหมายถึงรถคันไหน ตอบ ยี่ห้อ และ รุ่นหลัก เท่านั้น (เช่น Toyota / Yaris Ativ, Honda / City, Isuzu / D-Max) "
    "ไม่ต้องบอกรุ่นย่อย ปี เครื่องยนต์ หรือสี · ถ้าในรูปเดียวมีหลายคัน ให้ดูตำแหน่งตามที่ลูกค้าพูด · "
    "image = ลำดับรูปที่เป็นคันนั้น · confidence 0–1 · ถ้าดูไม่ออก/ไม่ใช่รถ/ไม่แน่ใจว่าลูกค้าหมายถึงคันไหน ให้ brand เป็นค่าว่าง"
)
SCHEMA = {"type": "OBJECT", "properties": {
    "brand": {"type": "STRING"}, "model": {"type": "STRING"},
    "image": {"type": "INTEGER"}, "confidence": {"type": "NUMBER"}, "reason": {"type": "STRING"}},
    "required": ["brand", "model", "image", "confidence"]}

BG = True                 # เทสต์ตั้ง False = ทำทันที


def enabled() -> bool:
    return bool((getattr(settings, "GEMINI_API_KEY", "") or "").strip())


def _model_name() -> str:
    return ((getattr(settings, "GEMINI_VISION_MODEL", "") or getattr(settings, "GEMINI_INSIGHTS_MODEL", "")
             or "gemini-2.5-flash").strip())


def _dt(s):
    from django.utils.dateparse import parse_datetime
    try:
        d = parse_datetime(s or "")
    except Exception:
        d = None
    if d and timezone.is_naive(d):
        d = timezone.make_aware(d)
    return d


def is_ref(text: str) -> bool:
    t = (text or "").strip()
    return bool(t) and not t.startswith("[") and bool(REF_RE.search(t))


def _is_image(m: dict) -> bool:
    if (m.get("type") or "") == "image":
        return True
    return any((f or {}).get("kind") == "image" for f in (m.get("files") or []))


def find_ref(msgs, now=None):
    """ข้อความลูกค้าล่าสุดที่อ้างถึงรถในรูป (ไม่เก่ากว่า RECENT_MIN นาที) → ข้อความนั้น หรือ None"""
    now = now or timezone.now()
    for m in reversed(list(msgs or [])):
        if (m.get("dir") or "in") != "in" or not m.get("text") or (m.get("text") or "").startswith("["):
            continue
        at = _dt(m.get("at"))
        if not at or now - at > timedelta(minutes=RECENT_MIN):
            return None
        return m if is_ref(m["text"]) else None
    return None


def images_for(msgs, ref) -> list:
    """รูปในแชทที่ข้อความอ้างรูปน่าจะหมายถึง → [ข้อความที่มีรูป] เรียงตามเวลา (รูปร้าน ≤ WINDOW_MIN นาทีก่อน ·
    รูปลูกค้าใกล้ข้อความ ≤ CUST_IMG_MIN นาที · ลูกค้าส่งรูปตามหลังได้ AFTER_MIN นาที)"""
    at = _dt(ref.get("at"))
    if not at:
        return []
    before, after = [], []
    for m in msgs or []:
        if not _is_image(m):
            continue
        t = _dt(m.get("at"))
        if not t:
            continue
        mine = (m.get("dir") or "in") == "out"
        if at - timedelta(minutes=WINDOW_MIN if mine else CUST_IMG_MIN) <= t <= at:
            before.append(m)
        elif at < t <= at + timedelta(minutes=AFTER_MIN) and not mine:
            after.append(m)
    return (before[-MAX_IMAGES:] + after)[-MAX_IMAGES:]


def _row_of(mid: str):
    from .models import FbChat, GroupChat
    if not mid or mid[0] not in "lf" or not mid[1:].isdigit():
        return None, None
    M, src = (GroupChat, "line") if mid[0] == "l" else (FbChat, "fb")
    return src, M.objects.filter(pk=int(mid[1:])).first()


def _shrink(path) -> bytes | None:
    try:
        from PIL import Image
        with Image.open(path) as im:
            im = im.convert("RGB")
            im.thumbnail((MAX_SIDE, MAX_SIDE))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=82)
            return buf.getvalue()
    except Exception:
        return None


def _image_bytes(msgs: list) -> list:
    """ข้อความที่มีรูป → [(ใครส่ง, bytes)] (โหลดรูปผ่าน chatmedia ตัวเดียวกับหน้าแชท · ข้อความเดียวมีหลายรูปได้)"""
    from pathlib import Path

    from . import chatmedia as CM
    out = []
    for m in msgs:
        src, row = _row_of(str(m.get("id") or ""))
        if not row:
            continue
        who = "ร้าน" if (m.get("dir") or "in") == "out" else "ลูกค้า"
        of = (row.extra or {}).get("out_file") if isinstance(row.extra, dict) else ""
        if of:                                    # รูปที่เราส่งจาก Connect (สำเนาอยู่ใน MEDIA_ROOT/chat_out)
            p = Path(settings.MEDIA_ROOT) / str(of)
            b = _shrink(p) if p.is_file() else None
            if b:
                out.append((who, b))
            continue
        try:
            CM.ensure(src, row, refresh=True)     # ลิงก์รูปของ Facebook หมดอายุ = ขอลิงก์ใหม่ครั้งเดียว
        except Exception:
            continue
        for i, a in enumerate(CM.attachments(src, row)):
            if a.get("kind") != "image":
                continue
            p = CM.stored(src, row, i)
            b = _shrink(p) if p else None
            if b:
                out.append((who, b))
    return out[-MAX_IMAGES:]


def ask(text: str, images: list) -> dict:
    """เรียก Gemini → {brand, model, image, confidence, reason} (ยกเว้นเมื่อเรียกไม่สำเร็จ)"""
    import requests
    key = (getattr(settings, "GEMINI_API_KEY", "") or "").strip()
    if not key:
        raise ValueError("ยังไม่ได้ตั้ง GEMINI_API_KEY")
    parts = [{"text": PROMPT.replace("{text}", (text or "")[:300])}]
    for i, (who, b) in enumerate(images, 1):
        parts.append({"text": "รูปที่ %d (%s)" % (i, who)})
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(b).decode("ascii")}})
    body = {"contents": [{"parts": parts}],
            "generationConfig": {"responseMimeType": "application/json", "responseSchema": SCHEMA, "temperature": 0}}
    r = requests.post(_URL.format(model=_model_name()) + "?key=" + key, json=body, timeout=60)
    if r.status_code != 200:
        raise RuntimeError("Gemini %s: %s" % (r.status_code, (r.text or "")[:200]))
    try:
        res = json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
    except Exception:
        raise RuntimeError("Gemini ตอบรูปแบบไม่ถูกต้อง")
    if not isinstance(res, dict):
        raise RuntimeError("Gemini ตอบรูปแบบไม่ถูกต้อง")
    return res


def car_name(res: dict) -> str:
    """ผลจาก AI → "ยี่ห้อ รุ่น" (ตัดรุ่นย่อยที่หลุดมา · มั่นใจไม่พอ/ว่าง = "")"""
    brand = re.sub(r"\s+", " ", str(res.get("brand") or "")).strip()[:30]
    model = re.sub(r"\s+", " ", str(res.get("model") or "")).strip()[:40]
    try:
        conf = float(res.get("confidence") or 0)
    except (TypeError, ValueError):
        conf = 0.0
    if not brand or not model or conf < MIN_CONF:
        return ""
    if model.lower().startswith(brand.lower()):
        model = model[len(brand):].strip()
    model = re.sub(r"\b(?:19|20)\d{2}\b|\b\d\.\d\s*[a-z]*\b", "", model, flags=re.I).strip(" -/")  # ปี/เครื่องที่หลุดมา
    return ("%s %s" % (brand, model)).strip() if model else ""


def _reserve(o, ref_id: str) -> bool:
    """จดว่าข้อความนี้กำลังวิเคราะห์ (กันเรียก AI ซ้ำเมื่อข้อความเดียวถูกส่งมาหลายทาง) → ได้สิทธิ์ทำไหม

    ★ อ่านแถวสดจาก DB เสมอ — `o.lead` ถูก Django จำไว้บนตัวแปร ถ้าใช้ตัวนั้น ค่าที่เพิ่งเขียนจะถูกทับ
      (เทสต์จับได้: จดว่าทำแล้ว แต่ apply เซฟทับด้วยค่าเก่า → เรียก AI ซ้ำ)"""
    from django.db import transaction
    from . import connect as C
    from .models import ChatLead
    C.lead_of(o)                                  # สร้างแถวให้ถ้ายังไม่มี
    with transaction.atomic():
        cur = ChatLead.objects.select_for_update().get(chat_id=o.pk)
        auto = dict(cur.auto or {})
        done = list(auto.get(DONE_KEY) or [])
        if ref_id in done:
            return False
        auto[DONE_KEY] = (done + [ref_id])[-DONE_MAX:]
        ChatLead.objects.filter(pk=cur.pk).update(auto=auto)
    try:                                          # ตัวที่จำไว้บน o ให้ตรงกับ DB (ผู้เรียกอาจเซฟต่อ)
        o.lead.auto = auto
    except Exception:
        pass
    return True


def apply(o, res: dict, ref: dict, n_img: int) -> str:
    """ผล AI → ช่องรถของข้อมูลลีด → ชื่อรถที่เติม ("" = ไม่ได้เติม)

    ทำใน thread → อ่านแถวสดแล้วล็อกก่อนเขียน (ระหว่างรอ AI อาจมีข้อความใหม่เข้ามาแก้ข้อมูลลีดไปแล้ว)"""
    from django.db import transaction
    from . import connect as C
    from .models import ChatLead
    car = car_name(res)
    hit = None
    if car:
        try:
            hit = C.car_in(car)                   # อ่านชีต/คำนวณนอกล็อก
        except Exception:
            hit = None
    with transaction.atomic():
        lead = ChatLead.objects.select_for_update().get(chat_id=o.pk)
        auto = dict(lead.auto or {})
        auto[KEY] = {"at": timezone.now().isoformat(timespec="seconds"), "mid": ref.get("id") or "", "car": car,
                     "brand": str(res.get("brand") or "")[:30], "model": str(res.get("model") or "")[:40],
                     "image": res.get("image"), "conf": res.get("confidence"), "n": n_img,
                     "text": (ref.get("text") or "")[:120], "reason": str(res.get("reason") or "")[:160]}
        fields = ["auto", "updated_at"]
        if car and auto.get("car_text") not in (C.HUMAN, "ใบจ่ายลีด"):
            lead.car_text = car[:300]
            auto["car_text"] = SRC
            fields.append("car_text")
            if auto.get("car_model") not in (C.HUMAN, "ใบจ่ายลีด"):
                model = (hit[0] if hit and hit[0] else "")
                if model:
                    lead.car_model = model[:80]
                elif lead.car_model:
                    # รุ่นกว้าง ("Honda City" = 4 หรือ 5 ประตู?) — ไม่เดา แต่ไม่ปล่อย CAR/สูตร ของคันเดิม (การ์ดโฆษณา) ค้างไว้
                    model = C.UNSPEC_MODEL
                    lead.car_model = model
                if model:
                    auto["car_model"] = SRC
                    fields.append("car_model")
        lead.auto = auto
        lead.save(update_fields=fields)
    return car if "car_text" in fields else ""


def analyze(o, ref: dict, imgs: list) -> dict:
    """ข้อความอ้างรูป + ข้อความที่มีรูป → เรียก AI → เติมช่องรถ → {car, error}"""
    out = {"car": "", "error": ""}
    try:
        pics = _image_bytes(imgs)
        if not pics:
            out["error"] = "โหลดรูปไม่ได้"
            return out
        res = ask(ref.get("text") or "", pics)
        out["car"] = apply(o, res, ref, len(pics))
    except Exception as e:
        out["error"] = str(e)[:200]
        try:
            from dashboard.services import eventlog
            eventlog.log("vision", name="วิเคราะห์รูปรถในแชท", ok=False, chat=o.pk, error=out["error"])
        except Exception:
            pass
    return out


def _after(o):
    """ส่งใบไปแล้ว + ลูกค้าพิมพ์จบแล้ว = ใบอัปเดต (ถ้ายังพิมพ์อยู่ ตัวรับข้อความเรียกเองหลังรอ)"""
    try:
        from . import autolead
        o2 = type(o).objects.filter(pk=o.pk).first()
        if o2 and o2.last_in_at and (timezone.now() - o2.last_in_at).total_seconds() >= autolead.UPDATE_QUIET_SEC - 3:
            autolead.update_chat(o2)
    except Exception:
        pass


def maybe(o, msgs, now=None):
    """เรียกจาก `connect.capture_profile` (ข้อความลูกค้าเข้า) — ข้อความล่าสุดอ้างรูป + มีรูปในแชท = วิเคราะห์ใน thread"""
    if not enabled():
        return None
    ref = find_ref(msgs, now)
    if not ref or not ref.get("id"):
        return None
    imgs = images_for(msgs, ref)
    if not imgs:
        return None
    from . import connect as C
    if C.is_sim_row(o):
        return None
    if not _reserve(o, ref["id"]):
        return None

    def work():
        try:
            r = analyze(o, ref, imgs)
            if r.get("car"):
                _after(o)
        finally:
            if BG:
                from django.db import close_old_connections
                close_old_connections()
    if not BG:
        return work()
    threading.Thread(target=work, name="carvision", daemon=True).start()
    return {"started": True}
