# -*- coding: utf-8 -*-
"""ลีดรับซื้อรถ → ใบเคสรับซื้อตัวอย่าง + รูปรถ ลงกลุ่มทดสอบ (TestBot02) — ★ 21 ต.ค.69 เจ้าของสั่ง
*"ทดลองส่งเคสย้อนหลังของจัดซื้อวันนี้ สัก 5 เคส พร้อมรูปรถลงกลุ่มทดสอบ 02"*

  · ใบหน้าตาเดียวกับใบในกลุ่มเคสHOT (โค้ด : OC- / ADS / รุ่น / เลขไมล์ / ทะเบียน / เบอร์ติดต่อ / ชื่อลูกค้า : ชื่อ / ช่องทาง /
    เพิ่มเติม / ขายเพราะ / ราคากลางรับซื้อจากตาราง) **ไม่มีเลขโค้ด** + รูปที่ลูกค้าส่ง (ไม่เกิน `PHOTO_MAX` รูป · ข้อความเดียวกัน)
  · ★ ใบทดสอบปิดบังข้อมูลส่วนบุคคล: เบอร์เหลือ 4 ตัวท้าย · ชื่อเหลือตัวแรก · ไม่ใส่ ID LINE (ข้อมูลเต็มอยู่ในหน้า Connect)
  · เลขไมล์/ทะเบียน = ตัวเลขหลังป้าย · ขายเพราะ/เพิ่มเติม = ข้อความของลูกค้าเอง (คำอยู่ในฐานข้อมูล หมวด "ใบเคสรับซื้อ")
  · ไม่ออกเลข OC · ไม่ลงชีต · ไม่ส่งเข้ากลุ่มเคสHOT จริง · `leadgroup.parse_buycase` ไม่นับใบนี้ (ไม่มีเลข)
  · กลุ่ม = KV `buyshow_config.group` · ยังไม่ตั้ง = กลุ่มชื่อ "TestBot02" ที่บอทตัวส่งอยู่
  · รอบแรก = ส่งเคสรับซื้อของวันนี้ `BACKFILL_N` ใบ (เคสที่มีรูปก่อน · ครั้งเดียว) · หลังจากนั้นลีดรับซื้อใหม่ + ใบอัปเดต
"""
from __future__ import annotations

import re
import time
import uuid
from datetime import timedelta

from django.utils import timezone

CFG_KEY = "buyshow_config"         # KV {on, group, group_name, since, off, backfill:{at, sent, failed, chats}}
KEY = "_albuy"                     # ChatLead.auto[KEY] = {at, ok, error, qt, sent, up, tries, tried, upd_at, resent, photos}
LAST_KEY = "buyshow_last"
MSG_PREFIX = "auto-buy-"
WHAT = "เคสรับซื้อ (กลุ่มทดสอบ)"
DEFAULT_GROUP_NAME = "TestBot02"
BACKFILL_N = 5
PHOTO_MAX = 6                      # ★ ส่งเป็นอัลบัม (Flex ข้อความเดียว · ช่องรูปขนาดเท่ากัน) ไม่ใช่รูปทีละข้อความ
UPDATE_HOURS, UPDATE_MAX, UPDATE_QUIET_SEC = 6, 3, 45
RETRY_MIN, MAX_TRIES, MAX_PER_RUN = 5, 5, 10
MORE_MAX_MSGS, MORE_MAX, MSG_MAX = 5, 400, 120
BG = True                          # เทสต์ปิด (ทำในที่ ไม่แตก thread)
_LOCK_KEY = 7_406_074
_RUN = {"at": 0.0}
UPD_FIELDS = (("car", "รุ่น"), ("mile", "เลขไมล์"), ("plate", "ทะเบียน"), ("reason", "เหตุผลที่ขาย"), ("more", "ข้อมูลรถ"))

_PROVINCES = (
    "กรุงเทพมหานคร กรุงเทพฯ กรุงเทพ กทม. กทม กระบี่ กาญจนบุรี กาฬสินธุ์ กำแพงเพชร ขอนแก่น จันทบุรี ฉะเชิงเทรา ชลบุรี ชัยนาท "
    "ชัยภูมิ ชุมพร เชียงราย เชียงใหม่ ตรัง ตราด ตาก นครนายก นครปฐม นครพนม นครราชสีมา นครศรีธรรมราช นครสวรรค์ นนทบุรี "
    "นราธิวาส น่าน บึงกาฬ บุรีรัมย์ ปทุมธานี ประจวบคีรีขันธ์ ปราจีนบุรี ปัตตานี พระนครศรีอยุธยา อยุธยา พะเยา พังงา พัทลุง "
    "พิจิตร พิษณุโลก เพชรบุรี เพชรบูรณ์ แพร่ ภูเก็ต มหาสารคาม มุกดาหาร แม่ฮ่องสอน ยโสธร ยะลา ร้อยเอ็ด ระนอง ระยอง "
    "ราชบุรี ลพบุรี ลำปาง ลำพูน เลย ศรีสะเกษ สกลนคร สงขลา สตูล สมุทรปราการ สมุทรสงคราม สมุทรสาคร สระแก้ว สระบุรี "
    "สิงห์บุรี สุโขทัย สุพรรณบุรี สุราษฎร์ธานี สุรินทร์ หนองคาย หนองบัวลำภู อ่างทอง อำนาจเจริญ อุดรธานี อุตรดิตถ์ "
    "อุทัยธานี อุบลราชธานี").split()
_PROV = "(?:" + "|".join(re.escape(p) for p in sorted(_PROVINCES, key=len, reverse=True)) + ")"
_PLATE_CORE = r"(\d?\s?[ก-ฮ]{1,2}\s?-?\s?\d{1,4})(?![0-9])"
_PLATE_PROV = r"(?:\s*(?:จ\.|จังหวัด)?\s*(" + _PROV + r"))?"
_PLATE_BARE = re.compile(r"(?<![0-9ก-๙A-Za-z])(\d\s?[ก-ฮ]{2}\s?-?\s?\d{1,4})(?![0-9])" + _PLATE_PROV)
_PLATE_NOT = {"รถ", "กม", "คน", "บท"}
_NUM = r"(\d[\d,\.]*)\s*(k(?![a-z])|พัน|หมื่น|แสน)?"
_MULT = {"k": 1000, "พัน": 1000, "หมื่น": 10_000, "แสน": 100_000}


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


def find_group(name: str) -> tuple:
    """ชื่อกลุ่ม/group id → (id, ชื่อ) เฉพาะกลุ่มที่บอทตัวส่งอยู่ · ไม่เจอ/ชื่อซ้ำ = ("", "")"""
    from dashboard.services.line_channels import group_visible_to_push
    from .slippost import _kv_groups
    a = (name or "").strip()
    if not a:
        return "", ""
    groups = _kv_groups()
    if a in groups:
        x = groups[a] or {}
        return (a, x.get("name") or "") if group_visible_to_push(x) else ("", "")
    hits = [(gid, (x or {}).get("name") or "") for gid, x in groups.items()
            if ((x or {}).get("name") or "").strip().lower() == a.lower() and group_visible_to_push(x or {})]
    return hits[0] if len(hits) == 1 else ("", "")


def cfg() -> dict:
    d = _kv(CFG_KEY)
    return {"on": bool(d.get("on", True)), "group": str(d.get("group") or ""),
            "group_name": str(d.get("group_name") or ""), "since": str(d.get("since") or ""),
            "off": bool(d.get("off")), "backfill": dict(d.get("backfill") or {})}


def save_cfg(c: dict):
    _set_kv(CFG_KEY, {k: c.get(k) for k in ("on", "group", "group_name", "since", "off", "backfill")})


def set_group(arg: str) -> dict:
    """ตั้งกลุ่ม (ชื่อ/group id) · "off" = เลิกส่ง (ไม่หากลุ่ม TestBot02 เองอีก) · กลุ่มใหม่ = เริ่มนับจากตอนนี้"""
    c = cfg()
    if (arg or "").strip().lower() == "off":
        c.update(group="", group_name="", off=True)
    else:
        gid, name = find_group(arg)
        if not gid:
            raise ValueError("ไม่พบกลุ่ม \"%s\" ที่บอทตัวส่งอยู่ — เชิญบอทเข้ากลุ่มแล้วพิมพ์อะไรก็ได้ 1 ครั้งก่อน" % arg)
        if gid != c["group"]:
            c["since"] = timezone.now().isoformat(timespec="seconds")
        c.update(group=gid, group_name=name, off=False)
    save_cfg(c)
    return c


def ready(c: dict | None = None, persist: bool = True) -> dict:
    """ค่าตั้งที่ใช้งานได้ · ยังไม่ตั้งกลุ่ม = หากลุ่มชื่อ TestBot02 (เจอแล้วจำไว้ + เริ่มนับจากตอนนี้) · ไม่เจอ = group ว่าง"""
    c = dict(c or cfg())
    if not c["on"]:
        c["group"] = ""
        return c
    if not c["group"] and not c["off"]:
        gid, name = find_group(DEFAULT_GROUP_NAME)
        if gid:
            c.update(group=gid, group_name=name, since=c["since"] or timezone.now().isoformat(timespec="seconds"))
            if persist:
                save_cfg(c)
    return c


# ── อ่านข้อมูลรถจากแชท ──────────────────────────────────────────────────

def _num(s: str, mult: str = ""):
    s = (s or "").strip().rstrip(".,")
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", s):
        s = re.sub(r"[.,]", "", s)
    else:
        s = s.replace(",", "")
    try:
        return int(round(float(s) * _MULT.get((mult or "").lower(), 1)))
    except ValueError:
        return None


def mile_in(text: str) -> str:
    """เลขไมล์ → "120000 กม" หรือ \"\" · ต้องมีป้าย ("ไมล์" · "วิ่ง") หรือหน่วย ("กม" · "โล")"""
    from . import kwdb
    from .lead_keywords import norm
    t = norm(text)
    for rx in (kwdb.rx("buy_info", "mile", r"(?:{})\s*[:：=]?\s*(?:ประมาณ|ราวๆ|ราว|อยู่ที่|ที่|แค่)?\s*" + _NUM),
               kwdb.rx("buy_info", "mile_unit", _NUM + r"\s*(?:{})")):
        for m in rx.finditer(t):
            n = _num(m.group(1), m.group(2) or "")
            if n is not None and 100 <= n <= 1_500_000:
                return "%d กม" % n
    return ""


def _plate_ok(core: str) -> str:
    p = re.sub(r"[\s-]", "", core or "")
    m = re.fullmatch(r"(\d?)([ก-ฮ]{1,2})(\d{1,4})", p)
    if not m or (not m.group(1) and m.group(2) in _PLATE_NOT):
        return ""
    return p


def plate_in(text: str) -> str:
    """ทะเบียนรถ → "1กก1234 ชลบุรี" หรือ \"\" · มีป้าย ("ทะเบียน") = รับ "กข 1234" · ไม่มีป้าย = ต้องมีเลขนำหน้า"""
    from . import kwdb
    lab = kwdb.rx("buy_info", "plate", r"(?:{})\s*[:：=]?\s*" + _PLATE_CORE + _PLATE_PROV)
    for rx in (lab, _PLATE_BARE):
        for m in rx.finditer(str(text or "")):
            p = _plate_ok(m.group(1))
            if p:
                return ("%s %s" % (p, (m.group(2) or "").strip())).strip()
    return ""


def _has(role: str, text: str) -> bool:
    from . import kwdb
    from .lead_keywords import norm
    return bool(kwdb.rx("buy_info", role).search(norm(text)))


def _is_img(m: dict) -> bool:
    if (m.get("type") or "") == "image":
        return True
    return any((f or {}).get("kind") == "image" for f in (m.get("files") or []))


def _clean(t: str) -> str:
    """ตัดเบอร์โทรออกจากข้อความลูกค้า (ใบมีช่องเบอร์ของตัวเอง)"""
    from . import connect as C
    return re.sub(r"\s+", " ", C._PHONE_RE.sub(" ", t or "")).strip(" ,/·-")


def mask_phone(p: str) -> str:
    d = re.sub(r"\D", "", p or "")
    return ("xxx-xxx-" + d[-4:]) if len(d) >= 4 else ""


def mask_name(n: str) -> str:
    n = (n or "").strip()
    return (n[:1] + "…") if n else ""


def fields(o, lead, msgs=None) -> dict:
    """แชท + ข้อมูลลีด → ช่องของใบเคสรับซื้อ"""
    from . import connect as C
    if msgs is None:
        try:
            msgs = C.messages(o, limit=150)
        except Exception:
            msgs = []
    ins = [m for m in msgs or [] if (m.get("dir") or "in") == "in"]
    texts = [t for t in (re.sub(r"\s+", " ", m.get("text") or "").strip() for m in ins) if t and not t.startswith("[")]
    mile = plate = reason = ""
    for t in texts:                               # ล่าสุดชนะ (ลูกค้าแก้ตัวเลขทีหลัง)
        mile = mile_in(t) or mile
        plate = plate_in(t) or plate
        if _has("reason", t):
            reason = _clean(t)[:MSG_MAX] or reason
    notes = []
    for t in texts:
        c = _clean(t)
        if len(c) >= 4 and c != reason and c not in notes and (_has("cond", t) or _has("price", t) or _has("loan", t)):
            notes.append(c[:MSG_MAX])
    more = notes[-MORE_MAX_MSGS:]
    imgs = [m for m in ins if _is_img(m)]
    n_img = img_total(imgs)
    if n_img:
        more.append("ลูกค้าส่งรูปมา %d รูป" % n_img)
    p, fb = C.cust(o), C.is_fb(o)
    ch = C.dd_pick("channel", lead.channel) or lead.channel or ("เพจ Facebook" if fb else "LINE@")
    return {"ads": lead.ads or "", "car": lead.car_text or lead.car_model or "", "mile": mile, "plate": plate,
            "phone": lead.phone or "", "has_line": bool(lead.line_id),
            "name": lead.customer_name or getattr(p, "display_name", "") or "", "channel": ch,
            "more": " / ".join(more)[:MORE_MAX], "reason": reason, "img_ids": [m.get("id") for m in imgs],
            "img_total": n_img}


def img_total(imgs: list) -> int:
    """จำนวนรูปจริง — ข้อความ Facebook ข้อความเดียวแนบได้หลายรูป (เดิมนับเป็นข้อความ = ใบบอก 1 รูป แต่ส่งไป 4)"""
    n = 0
    for m in imgs or []:
        k = sum(1 for f in (m.get("files") or []) if (f or {}).get("kind") == "image")
        n += k or 1
    return n


def slip(f: dict) -> str:
    """ใบเคสรับซื้อตัวอย่าง (ไม่มีเลขโค้ด · ปิดบังเบอร์/ชื่อ) — ลำดับบรรทัดเดียวกับใบจริงในกลุ่มเคสHOT"""
    def v(x):
        return str(x or "").strip() or "-"
    phone = mask_phone(f.get("phone")) or ("(ให้ ID LINE)" if f.get("has_line") else "")
    return "\n".join([
        "โค้ด : OC-",
        "ADS : %s" % v(f.get("ads")),
        "รุ่น : %s" % v(f.get("car")),
        "เลขไมล์ : %s" % v(f.get("mile")),
        "ทะเบียน : %s" % v(f.get("plate")),
        "เบอร์ติดต่อ : %s" % v(phone),
        "ชื่อลูกค้า : %s / %s" % (v(mask_name(f.get("name"))), v(f.get("channel"))),
        "เพิ่มเติม : %s" % v(f.get("more")),
        "ขายเพราะ : %s" % v(f.get("reason")),
        "ราคากลางรับซื้อจากตาราง : -",
    ])


def _snap(f: dict) -> dict:
    return {k: str(f.get(k) or "").strip() for k, _ in UPD_FIELDS}


def _changes(sent: dict, f: dict) -> list:
    return [label for k, label in UPD_FIELDS
            if str(f.get(k) or "").strip() and str(f.get(k) or "").strip() != str((sent or {}).get(k) or "").strip()]


# ── รูปรถ ───────────────────────────────────────────────────────────────

def _photo_bytes(msg_ids: list) -> list:
    """ข้อความรูปของลูกค้า (id "l…"/"f…" จาก `connect.messages`) → [bytes] (รูปแรกๆ ที่ลูกค้าส่ง · ไม่เกิน PHOTO_MAX)"""
    from . import chatmedia as CM
    from .models import FbChat, GroupChat
    out = []
    for mid in msg_ids or []:
        mid = str(mid or "")
        if len(out) >= PHOTO_MAX or not mid or mid[0] not in "lf" or not mid[1:].isdigit():
            continue
        src = CM.LINE if mid[0] == "l" else CM.FB
        row = (GroupChat if src == CM.LINE else FbChat).objects.filter(pk=int(mid[1:])).first()
        if not row:
            continue
        try:
            CM.ensure(src, row, refresh=True)
        except Exception:
            continue
        for i, a in enumerate(CM.attachments(src, row)):
            if a.get("kind") != "image" or len(out) >= PHOTO_MAX:
                continue
            p = CM.stored(src, row, i)
            if p:
                try:
                    out.append(p.read_bytes())
                except OSError:
                    pass
    return out


def _photo_urls(msg_ids: list) -> tuple:
    """รูป → สำเนาสาธารณะ (ชื่อสุ่ม · ตัด EXIF · ย่อ) → ([(ลิงก์รูปเต็ม, ลิงก์รูปตัวอย่าง)], [path ที่สร้าง])
    · ไม่ใช่ https = ไม่ส่งรูป"""
    from . import chatplus as CP
    if not CP._public_base().startswith("https://"):
        return [], []
    urls, rels = [], []
    for raw in _photo_bytes(msg_ids):
        try:
            full, prev = CP._encode(raw)
        except Exception:
            continue
        rf, rp = CP._save_out(full, prev)
        rels += [rf, rp]
        urls.append((CP._media_url(rf), CP._media_url(rp)))
    return urls, rels


# แถวของอัลบัม (จำนวนรูปต่อแถว) ตามจำนวนรูป — แบบเดียวกับอัลบัมในแชท LINE
_ALBUM_ROWS = {1: (1,), 2: (2,), 3: (1, 2), 4: (2, 2), 5: (2, 3), 6: (3, 3)}


def album(urls: list, total: int = 0) -> dict | None:
    """[(รูปเต็ม, รูปตัวอย่าง)] → Flex ข้อความเดียว: ช่องรูปขนาดเท่ากันเป็นตาราง (ตัดขอบให้พอดีช่อง) · แตะ = เปิดรูปเต็ม
    LINE Messaging API ส่ง "อัลบัม" จริงไม่ได้ (รูปทีละข้อความ = ขนาดไม่เท่ากัน เรียงยาว) → ใช้ Flex แทน"""
    urls = [u for u in (urls or []) if u and u[0] and u[1]][:PHOTO_MAX]
    if not urls:
        return None
    rows, i, body = _ALBUM_ROWS[len(urls)], 0, []
    for k in rows:
        ar = "1:1" if k > 1 else ("4:3" if len(rows) == 1 else "2:1")
        cells = []
        for full, prev in urls[i:i + k]:
            cells.append({"type": "image", "url": prev, "size": "full", "aspectRatio": ar, "aspectMode": "cover",
                          "flex": 1, "action": {"type": "uri", "label": "ดูรูป", "uri": full}})
        i += k
        body.append({"type": "box", "layout": "horizontal", "spacing": "xs", "contents": cells})
    total = max(int(total or 0), len(urls))
    note = "รูปรถจากแชทลูกค้า %d รูป" % len(urls)
    if total > len(urls):
        note += " (ลูกค้าส่งมาทั้งหมด %d รูป)" % total
    return {"type": "flex", "altText": "รูปรถ %d รูป (ใบเคสรับซื้อ)" % len(urls),
            "contents": {"type": "bubble", "size": "giga",
                         "body": {"type": "box", "layout": "vertical", "spacing": "xs", "paddingAll": "0px",
                                  "contents": body},
                         "footer": {"type": "box", "layout": "vertical", "paddingAll": "10px",
                                    "contents": [{"type": "text", "text": note + " · แตะรูปเพื่อดูเต็ม",
                                                  "size": "xs", "color": "#888888", "wrap": True}]}}}


# ── ส่งเข้ากลุ่มทดสอบ ──────────────────────────────────────────────────

def _dt(s):
    from django.utils.dateparse import parse_datetime
    d = parse_datetime(s) if s else None
    if d and timezone.is_naive(d):
        d = timezone.make_aware(d)
    return d


def _excluded(o) -> bool:
    from . import autolead as AL
    from . import connect as C
    return C.is_sim_row(o) or bool(getattr(C.cust(o), "is_employee", False)) or o.pk in AL.cfg()["test_chats"]


def _push(gid: str, messages: list, quote: str = "") -> tuple:
    """→ (ok, error, line message id ของใบ, quoteToken ของใบ) · รูปถูกปฏิเสธ = ส่งใบอย่างเดียวซ้ำ (ใบต้องถึงก่อน)"""
    from dashboard.services.line_channels import push_token
    from dashboard.services.line_notify import push_line_message
    from . import autolead as AL
    from .slippost import _sent_id, explain
    token = push_token()
    if not token:
        return False, "ยังไม่ได้ตั้ง LINE token ของบอทตัวส่ง", "", ""
    first = dict(messages[0], quoteToken=quote) if quote else messages[0]
    try:
        sc, resp = push_line_message(gid, [first] + messages[1:], token, what=WHAT)
        if sc == 400 and (quote or len(messages) > 1):
            sc, resp = push_line_message(gid, [messages[0]], token, what=WHAT)
            if sc == 200:
                return True, "ส่งรูปไม่ได้ (ส่งแค่ใบ)", _sent_id(resp), AL._sent_quote(resp)
        ok = sc == 200
        return ok, ("" if ok else explain(sc, resp)), (_sent_id(resp) if ok else ""), (AL._sent_quote(resp) if ok else "")
    except Exception as e:
        return False, "ต่อ LINE ไม่ได้: %s" % str(e)[:120], "", ""


def _send(c: dict, o, lead, prev: dict | None = None, photos: bool = True) -> dict:
    from . import autolead as AL
    from . import chatplus as CP
    f = fields(o, lead)
    text = slip(f)
    urls, rels = _photo_urls(f["img_ids"]) if photos else ([], [])
    alb = album(urls, f.get("img_total") or 0)
    ok, err, line_mid, qt = _push(c["group"], [{"type": "text", "text": text[:4800]}] + ([alb] if alb else []))
    if not ok or err:
        CP._drop(*rels)                           # รูปไม่ถึงกลุ่ม = ไม่ทิ้งสำเนาสาธารณะไว้บนดิสก์
    res = dict(prev or {})
    res.update(ok=ok, error=err, tries=int(res.get("tries") or 0) + 1, tried=timezone.now().isoformat(timespec="seconds"),
               photos=(len(urls) if alb and ok and not err else 0))
    if ok:
        AL._store_out(c["group"], c["group_name"], "%s%s-%s" % (MSG_PREFIX, lead.pk, uuid.uuid4().hex[:6]), text,
                      {"chat": o.pk, "buy": True, "photos": res["photos"]}, line_mid)
        res.update(sent=_snap(f), qt=qt or res.get("qt") or "")
    return res


def _skip_why(lead, resend: bool = False) -> str:
    from . import connect as C
    if (lead.code or "").strip():
        return "มีเลขลีดขายแล้ว (%s)" % lead.code
    if C.deal_of(lead) != "buy":
        return "ไม่ใช่ลีดรับซื้อ"
    if not (lead.phone or lead.line_id):
        return "ยังไม่มีเบอร์/ID LINE"
    if C.BUY_KEY in (lead.auto or {}) and not resend:
        return "แอดมินส่งจัดซื้อแล้ว"
    return ""


def post_one(o, c: dict | None = None, resend: bool = False, photos: bool = True) -> dict:
    """แชทเดียว → ใบเคสรับซื้อตัวอย่าง (+ รูป) เข้ากลุ่มทดสอบ · {d: posted|failed|skip, why}"""
    from django.db import transaction
    from . import autolead as AL
    from . import connect as C
    from .models import ChatLead
    c = c or ready()
    if not c["group"]:
        return {"d": "off", "why": "ยังไม่มีกลุ่มทดสอบ"}
    if _excluded(o):
        return {"d": "skip", "why": "พนักงาน/บัญชีทดสอบ"}
    AL._ensure_ad(o)
    lead = C.autofill(o)
    why = _skip_why(lead, resend)
    if why:
        return {"d": "skip", "why": why}
    now = timezone.now().isoformat(timespec="seconds")
    with transaction.atomic():                    # ข้อความเข้า (thread) + cron ทำแชทเดียวกันพร้อมกัน = ส่งครั้งเดียว
        cur = ChatLead.objects.select_for_update().get(pk=lead.pk)
        prev = (cur.auto or {}).get(KEY) or {}
        if prev and not resend and (prev.get("ok") or prev.get("sending")):
            return {"d": "skip", "why": "ส่งใบไปแล้ว"}
        a = dict(cur.auto or {})
        a[KEY] = dict(prev, at=prev.get("at") or now, sending=True)
        ChatLead.objects.filter(pk=cur.pk).update(auto=a)
    lead.auto = a
    res = _send(c, o, lead, dict(prev, at=prev.get("at") or now, up=0 if resend else int(prev.get("up") or 0)), photos)
    res.pop("sending", None)
    if resend:
        res["resent"] = now
    AL._save(lead, res, KEY)
    return {"d": "posted" if res.get("ok") else "failed", "why": res.get("error") or "", "photos": res.get("photos", 0)}


def candidates(c: dict, pk=None, limit: int = 100) -> list:
    """ลีดรับซื้อ (มีเบอร์/ID LINE · ยังไม่ส่งจัดซื้อ · ยังไม่ส่งใบทดสอบ) ที่เป็นลีดรับซื้อ/ให้ช่องทางติดต่อหลัง `since`"""
    from . import connect as C
    from .models import ChatOwner
    since = _dt(c.get("since") or "")
    qs = (ChatOwner.objects.select_related("profile", "fb_profile", "owner", "lead")
          .filter(lead__auto__has_key=C.BUYLEAD_KEY).filter(C._engaged_q()).filter(C._no_code_q())
          .filter(C._contact_q()).exclude(lead__auto__has_key=KEY))
    if pk:
        qs = qs.filter(pk=pk)
    out = []
    for o in qs.order_by("-last_in_at")[:limit]:
        a = o.lead.auto or {}
        ats = [x for x in (_dt(a.get(C.CONTACT_AT_KEY) or ""), _dt((a.get(C.BUYLEAD_KEY) or {}).get("at") or "")) if x]
        # ให้ช่องทางติดต่อ/เพิ่งกลายเป็นลีดรับซื้อ หลังเริ่ม + ลูกค้าทักมาหลังเริ่ม (แชทเก่าที่เพิ่งถูกจัดประเภทใหม่ไม่ส่ง)
        if since and (not ats or max(ats) <= since or not o.last_in_at or o.last_in_at <= since):
            continue
        if not _excluded(o):
            out.append(o)
    return out


def update_one(o, now=None, c: dict | None = None) -> dict:
    """ส่งใบไปแล้ว + ลูกค้าพิมพ์ข้อมูลรถเพิ่ม → ใบอัปเดตอ้างใบเดิม (ไม่ส่งรูปซ้ำ) · รอพิมพ์จบ · ภายใน 6 ชม. · ไม่เกิน 3 ครั้ง"""
    from . import autolead as AL
    from . import connect as C
    from .models import ChatOwner
    c = c or ready()
    now = now or timezone.now()
    if not c["group"]:
        return {"d": "off"}
    with AL._Lock(_LOCK_KEY) as lk:
        if not lk.got:
            return {"d": "busy"}
        o = ChatOwner.objects.select_related("profile", "fb_profile", "owner", "lead").filter(pk=o.pk).first()
        if not o:
            return {"d": "skip"}
        if o.last_in_at and (now - o.last_in_at).total_seconds() < UPDATE_QUIET_SEC - 3:
            return {"d": "wait"}
        lead = C.lead_of(o, create=False)
        sh = ((lead.auto or {}).get(KEY) or {}) if lead else {}
        if not sh.get("ok") or not sh.get("sent") or (lead.code or "").strip():
            return {"d": "skip"}
        at = _dt(sh.get("upd_at") or sh.get("resent") or sh.get("at") or "")
        if not at or now - at > timedelta(hours=UPDATE_HOURS) or int(sh.get("up") or 0) >= UPDATE_MAX:
            return {"d": "skip"}
        lead = C.autofill(o)
        f = fields(o, lead)
        ch = _changes(sh["sent"], f)
        if not ch:
            return {"d": "same"}
        text = "🔄 อัปเดตเคสรับซื้อ — ลูกค้าพิมพ์%sเพิ่ม (ใบล่าสุดแทนใบเดิม)\n%s" % (" / ".join(ch), slip(f))
        ok, err, line_mid, _qt = _push(c["group"], [{"type": "text", "text": text[:4800]}], sh.get("qt") or "")
        if ok:
            n = int(sh.get("up") or 0) + 1
            AL._store_out(c["group"], c["group_name"], "%s%s-u%d-%s" % (MSG_PREFIX, lead.pk, n, uuid.uuid4().hex[:6]),
                          text, {"chat": o.pk, "buy": True, "update": n}, line_mid)
            AL._save(lead, dict(sh, sent=_snap(f), up=n, upd_at=now.isoformat(timespec="seconds")), KEY)
        return {"d": "updated" if ok else "failed", "why": err, "fields": ch}


def _img_count(o) -> int:
    from .models import FbChat, GroupChat
    if o.fb_profile_id:
        tid = o.fb_profile.thread_id or "-"
        return FbChat.objects.filter(thread_id=tid, direction=FbChat.IN, has_media=True).count()
    return GroupChat.objects.filter(sender_id=o.profile.user_id, direction=GroupChat.IN, has_media=True,
                                    msg_type="image").exclude(chat_type=GroupChat.GROUP).count()


def backfill(limit: int = BACKFILL_N, since=None, dry: bool = False, c: dict | None = None, pause: float = 0.6) -> dict:
    """เคสรับซื้อของวันนี้ (ตั้งแต่เที่ยงคืน · ไม่พอ = 24 ชม.) `limit` ใบ — เคสที่ลูกค้าส่งรูปมาก่อน · รวมเคสที่ส่งจัดซื้อแล้ว
    (บอกเลขใบจริงในข้อความหัว ไว้เทียบ) → {sent, failed, would, real, rows:[{chat, d, photos, mile, plate, reason, more, car}]}
    ผลไม่มีชื่อ/เบอร์ลูกค้า"""
    from django.db.models import Q
    from . import autolead as AL
    from . import connect as C
    from .models import ChatOwner
    c = c or ready()
    if not c["group"]:
        return {"error": "ยังไม่มีกลุ่มทดสอบรับซื้อ (กลุ่มชื่อ TestBot02 ที่บอทตัวส่งอยู่ หรือ --buy-group <ชื่อกลุ่ม>)"}
    now = timezone.now()
    starts = [since] if since else [timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0),
                                    now - timedelta(hours=24)]
    pool = []
    for st in starts:
        qs = (ChatOwner.objects.select_related("profile", "fb_profile", "owner", "lead")
              .filter(Q(lead__auto__has_key=C.BUYLEAD_KEY) | Q(lead__auto__has_key=C.BUY_KEY))
              .filter(C._contact_q()).filter(lead__code="").filter(last_in_at__gte=st).order_by("-last_in_at"))
        pool = [o for o in qs[:60] if not _excluded(o)]
        if len(pool) >= limit:
            break
    scored = sorted(pool, key=lambda o: (_img_count(o) > 0, o.last_in_at), reverse=True)[:limit]
    pick = sorted(scored, key=lambda o: o.last_in_at)          # เก่า → ใหม่
    real = [x for x in (((o.lead.auto or {}).get(C.BUY_KEY) or {}).get("code") or "" for o in pick) if x]
    out = {"sent": 0, "failed": 0, "would": 0, "real": real, "rows": []}
    if pick and not dry:
        head = ("🔁 เคสรับซื้อของวันนี้ %d ใบ — ทดสอบรูปแบบใบ (ไม่มีเลขโค้ด · ปิดบังเบอร์/ชื่อ · ข้อมูลรถ + รูปจากแชทลูกค้า)"
                % len(pick))
        if real:
            head += "\nแอดมินส่งจัดซื้อไปแล้ว %d ใบ (ใบจริง: %s) — เทียบกับใบในกลุ่มเคสHOT ได้" % (len(real), ", ".join(real))
        _push(c["group"], [{"type": "text", "text": head}])
    for o in pick:
        lead = C.autofill(o)
        f = fields(o, lead)
        row = {"chat": o.id, "photos": len(f["img_ids"]), "mile": bool(f["mile"]), "plate": bool(f["plate"]),
               "reason": bool(f["reason"]), "more": bool(f["more"]), "car": bool(f["car"])}
        if dry:
            row["d"] = "would"
            out["would"] += 1
        else:
            r = post_one(o, c, resend=True)
            row.update(d=r["d"], sent_photos=r.get("photos", 0))
            if r.get("why"):
                row["why"] = r["why"]
            if r["d"] in ("posted", "failed"):
                out["sent" if r["d"] == "posted" else "failed"] += 1
            if BG and pause:
                time.sleep(pause)
        out["rows"].append(row)
    if not dry:
        cc = cfg()
        cc.update(group=c["group"], group_name=c["group_name"], since=c.get("since") or cc["since"],
                  backfill={"at": now.isoformat(timespec="seconds"), "sent": out["sent"], "failed": out["failed"],
                            "chats": [r["chat"] for r in out["rows"]]})
        save_cfg(cc)
        _set_kv(LAST_KEY, {"at": now.isoformat(timespec="seconds"), "backfill": {k: out[k] for k in ("sent", "failed")},
                           "rows": out["rows"]})
    return out


def run(now=None) -> dict:
    """รอบเดียว (cron ทุกนาที): ครั้งแรกส่งเคสวันนี้ · ลีดรับซื้อใหม่ · ส่งไม่สำเร็จส่งใหม่ · ใบอัปเดต"""
    from .models import ChatLead, ChatOwner
    now = now or timezone.now()
    c = ready()
    if not c["group"]:
        return {"off": True}
    if not c["backfill"]:
        r = backfill(c=c)
        return {"backfill": {k: r.get(k) for k in ("sent", "failed", "real", "error")}}
    rows = []
    for o in candidates(c)[:MAX_PER_RUN]:
        try:
            r = post_one(o, c)
        except Exception as e:
            r = {"d": "failed", "why": "พัง: %s" % str(e)[:150]}
        r["chat"] = o.id
        rows.append(r)
    for lead in ChatLead.objects.filter(auto__has_key=KEY, code="").select_related("chat").order_by("-updated_at")[:40]:
        sh = (lead.auto or {}).get(KEY) or {}
        if sh.get("ok"):
            last = _dt(sh.get("upd_at") or sh.get("resent") or sh.get("at") or "")
            if (last and now - last <= timedelta(hours=UPDATE_HOURS) and int(sh.get("up") or 0) < UPDATE_MAX
                    and ChatOwner.objects.filter(pk=lead.chat_id, last_in_at__gt=last).exists()):
                r = update_one(lead.chat, now, c)
                if r.get("d") in ("updated", "failed"):
                    rows.append(dict(r, chat=lead.chat_id))
            continue
        t = _dt(sh.get("tried") or sh.get("at") or "")
        if int(sh.get("tries") or 0) < MAX_TRIES and (not t or now - t >= timedelta(minutes=RETRY_MIN)):
            rows.append(dict(post_one(lead.chat, c, resend=True), chat=lead.chat_id, retry=True))
    out = {k: sum(1 for r in rows if r.get("d") == k) for k in ("posted", "failed", "updated")}
    if rows:
        _set_kv(LAST_KEY, dict(out, rows=rows[:30], at=now.isoformat(timespec="seconds")))
    return dict(out, rows=rows[:30])


def _bg(fn, *a):
    import threading

    def _work():
        try:
            fn(*a)
        except Exception as e:
            try:
                from dashboard.services import eventlog
                eventlog.log("autolead", name=WHAT, ok=False, error=str(e)[:300])
            except Exception:
                pass
        finally:
            try:
                from django.db import connection
                connection.close()
            except Exception:
                pass
    threading.Thread(target=_work, daemon=True).start()


def tick_bg(now=None) -> dict:
    """เรียกจาก `connect.tick` ทุกนาที — ทำใน thread (อ่านแชท · ยิง LINE)"""
    if time.time() - _RUN["at"] < 50:
        return {}
    _RUN["at"] = time.time()
    if not ready(persist=False)["group"]:
        return {}
    if not BG:
        return run(now)
    from . import connect as C
    if not getattr(C, "BG_FILL", True):
        return {}
    _bg(run)
    return {"started": True}


def _kick_work(o, c):
    from . import connect as C
    new = False
    for oo in candidates(c, pk=o.pk):
        new = post_one(oo, c).get("d") in ("posted", "failed") or new
    if not new:
        lead = C.lead_of(o, create=False)
        if lead and ((lead.auto or {}).get(KEY) or {}).get("ok"):
            if BG:
                time.sleep(UPDATE_QUIET_SEC)
            update_one(o, None, c)


def kick(o) -> object:
    """ข้อความลูกค้าเพิ่งเข้า → ลีดรับซื้อที่เพิ่งให้ช่องทางติดต่อ = ส่งใบทันที · ส่งไปแล้ว = รอพิมพ์จบแล้วส่งใบอัปเดต"""
    from . import connect as C
    if o is None:
        return None
    c = ready(persist=False)
    if not c["group"] or not c["backfill"]:
        return None                               # รอบแรก (ส่งเคสวันนี้) ให้ cron ทำก่อน
    if not BG:
        return _kick_work(o, c)
    if not getattr(C, "BG_FILL", True):
        return None
    _bg(_kick_work, o, c)
    return {"started": True}
