# -*- coding: utf-8 -*-
"""ข้อมูลของ **ศูนย์ควบคุมลีด** (หน้า Connect แบบใหม่ · 10 ต.ค.69) — ฐานข้อมูล Lead · ไปป์ไลน์ · แดชบอร์ดทีม

เจ้าของสั่งเอาแบบหน้าจอ "ศูนย์ควบคุมลีด" มาแทน Connect เดิม (ของเดิมยังเปิดได้ที่ `?classic=1`)
ไฟล์นี้ทำแค่ "อ่าน + รวมตัวเลข" จากของที่ระบบมีอยู่แล้ว — ไม่มีตารางใหม่ ไม่ส่งอะไรออก:

  - **ฐานข้อมูล Lead** = แถวในชีตลีด 26 คอลัมน์ตามชีต (ทุกแท็บรายเดือน · `fetch_leads_by_month_tabs`)
    + ลีดที่ระบบออกเลขแล้วแต่ยังไม่ลงชีต (Connect/ลีดภายนอก) · **จับคู่ลีดซ้ำ 2 ทาง: Code และช่องเบอร์โทร**
    (ช่องนี้เก็บได้ทั้งเบอร์และ "ID LINE : …" — เทียบทั้งสองแบบ) · ไม้ 2 (R…/n) ของเลขเดิม = ลีดเดียวกัน ไม่นับว่าซ้ำ
    + ชื่อลูกค้าจากใบจ่ายลีด/แชท (ชีตลีดไม่มีช่องชื่อ) + ประวัติงานจ่ายเบอร์ (`LeadTask`)
  - **ไปป์ไลน์** = เคสจองจากชีตยอดขาย (`bookingCases` ในผลสรุปแดชบอร์ด · สถานะชุดเดียวกับรายงานฝ่ายขาย)
  - **แดชบอร์ดทีม** = งานจ่ายเบอร์วันนี้ (`LeadTask`) + เวลาตอบแชท (`ChatOwnerLog`) + จอง/ปล่อยเดือนนี้
    (ผลสรุปแดชบอร์ด) — **ไม่ใช้ตัวนับ "แชทเลยเวลา"** เพราะทีมตอบในแอป LINE OA Manager ซึ่ง LINE ไม่ส่งกลับมา
    (ตัวเลขนั้นไม่มีความหมาย — เจ้าของสั่งถอดแท็บเลยเวลาไปแล้ว 7 ต.ค.69)
"""
from __future__ import annotations

import heapq
import re
import time
import unicodedata
from datetime import datetime, timedelta

from django.db.models import Count, Q
from django.utils import timezone

_ROWS = {"at": 0.0, "val": None}     # ดัชนีแถวชีตลีด (ดู _sheet_idx)
ROWS_TTL = 600                      # ชีตลีดหลายหมื่นแถว — อ่านใหม่ทุก 10 นาที (อ่านครั้งแรก ~8 วิ)
_SYS = {"at": 0.0, "key": None, "val": None}
SYS_TTL = 30                        # ลีดในระบบ (Connect) เปลี่ยนบ่อย — อ่านใหม่ทุก 30 วิ
KEY_CAP = 12                        # เบอร์/ไลน์เดียวเป็นลีดเกิน 12 เลข = ค่ากลาง (เบอร์ร้าน/ค่าตัวอย่าง) ไม่ใช้จับคู่
RETURN_WORDS = ("คืนเคส",)

# ── 26 คอลัมน์ของชีตลีด ตามลำดับในชีต (เจ้าของสั่ง 11 ต.ค.69 "ออกแบบคอลัมน์ตามเดิม") ──
COLS = ["ว/ด/ป", "เบอร์โทร", "เวลา", "Code", "เซลล์", "ทีมไลฟ์", "Admin", "ช่องทาง", "สาขา", "type", "ADS",
        "รถลูกค้าถาม", "CAR / สูตร", "แจ้งหลักฐานการโทร", "FOCUS", "วัน เวลา ที่ติดต่อ", "จำนวนอัพเดท",
        "วัน เวลา อัพเดทล่าสุด", "มากรอกชีตกันเถอะ", "PROFILE ลูกค้า จาก ADMIN", "อาชีพ", "รายได้", "อายุงาน",
        "ประวัติการผ่อน", "ประเภทลูกค้า", "สถานะลูกค้า"]


_CIX = []


def _col_idx() -> list:
    """ตำแหน่ง canonical (`LEADS_COL`) ของ 26 คอลัมน์ — ชีตแต่ละเดือนวางคอลัมน์ต่างกัน ตัวอ่านจัดให้ตรงชื่อหัวแล้ว"""
    if _CIX:
        return _CIX
    from dashboard.services.google_sheets import LEADS_COL as L
    _CIX[:] = [L.received_date, L.phone, L.time, L.lead_code, L.sales_rep, L.live_team, L.admin, L.channel, L.branch,
            L.type, L.ads, L.car_inquiry, L.car_formula, L.call_proof, L.focus, L.contact_datetime, L.update_count,
            L.last_updated_at, L.fill_sheet_note, L.customer_profile, L.occupation, L.income, L.job_tenure,
            L.payment_history, L.customer_type, L.customer_status]
    return _CIX


def _cell(r, i):
    return (r[i] if i < len(r) else "") or ""


def _date(s):
    try:
        from dashboard.services.fetch_dashboard import parse_date
        d = parse_date(s)
        return d.date() if hasattr(d, "date") else d
    except Exception:
        return None


def _time_key(s) -> int:
    """"13:09" / "10.30" / "9:55" → นาทีของวัน (ใช้เรียงลีดวันเดียวกัน)"""
    m = re.match(r"\s*(\d{1,2})\s*[:.]\s*(\d{2})", str(s or ""))
    return int(m.group(1)) * 60 + int(m.group(2)) if m else -1


# ─────────────────────────────────────────────────────────────
#  ตัวจับคู่ลีด: **Code** + **ช่องเบอร์โทร** (เบอร์ หรือ ID LINE)
# ─────────────────────────────────────────────────────────────
# ช่อง "เบอร์โทร" ในชีตเก็บได้ 2 แบบ (วัดจริง 11 ต.ค.69 · 26,759 แถว): เบอร์โทร ~16,400 แถว ·
# "ID LINE : xxx" แทนเบอร์ ~10,300 แถว — ในนั้น ~2,800 แถวเป็นค่าที่ไม่ใช่ไอดี ("QR code" / "Line@" / "-")
# ของเดิมเทียบแค่เบอร์ → ลูกค้าที่ให้แต่ไลน์ (4 ใน 10 แถว) ไม่เคยถูกจับว่าซ้ำเลย
def norm_code(s) -> str:
    return re.sub(r"\s+", "", str(s or "")).upper()


def lineage(code: str) -> str:
    """เลขไม้ 2 (R + เลขเดิม + /n) = ลีดเดียวกับเลขเดิม · "RTLD9-6456/1" → "TLD9-6456"
    R ที่ไม่มี /n = เลขรันใหม่ของปุ่ม R ในระบบ (เคสรีเจ็คใหม่) → เป็นลีดของตัวเอง"""
    base = re.sub(r"/\d+$", "", code or "")
    return base[1:] if base != code and base.startswith("R") else base


_LID_URL = re.compile(r"(?i)line\.me/(?:r/)?ti/p/~?([a-z0-9._\-~]+)")
_LID_JUNK = re.compile(r"(?i)q\s*r\s*[-_.]?\s*c\s*o\s*[a-z]{0,3}|(?<![a-z])qr(?![a-z])|line\s*@|@\s*line")
_LID_LABEL = re.compile(r"(?i)(?<![a-z])(?:id\s*line|line\s*id|id|line)\s*[:：=]+|^\s*(?:id\s*line|line\s*id)(?![a-z])")
_LID_NAME = re.compile(r"(?i)ชื่อ\s*(?:ไลน์|line)")
_THAI = re.compile(r"[฀-๿]+")
_LID_OK = re.compile(r"[a-z0-9._\-]{4,40}")
_LID_STOP = {"line", "idline", "lineid", "qrcode", "none", "null", "nan"}


def line_ids(text) -> list:
    """ID LINE ในช่องเบอร์โทร (หรือช่อง ID LINE ของระบบ) → ["sayompoo2546", …] พิมพ์เล็ก
    · ไม่นับ: QR code / Line@ / "-" / ชื่อที่ตั้งใน LINE (ซ้ำกันได้ ไม่ใช่ไอดี) · ลิงก์ line.me/ti/p/xxx = ไอดี xxx
    · เบอร์ที่อยู่ในช่องเดียวกันไม่นับเป็นไอดี (นับเป็นเบอร์แล้ว)"""
    from . import phonebook
    s = str(text or "")
    if not s.strip() or _LID_NAME.search(s):
        return []
    out = [m.group(1).lower().strip("._-~") for m in _LID_URL.finditer(s)]
    s = _LID_URL.sub(" ", s)
    s = re.sub(r"(?i)https?://\S*|www\.\S*", " ", s)
    s = phonebook._PHONE_RE.sub(lambda m: " " if phonebook.norm(m.group(0)) else m.group(0), s)
    s = _LID_JUNK.sub(" ", s)
    s = _LID_LABEL.sub(" ", s)
    s = _THAI.sub(" ", s)                       # ป้าย/คำลงท้ายภาษาไทย (ไอดี · ไลน์ · ครับ · คะ)
    for tok in re.split(r"[\s/|,;:：=()\[\]<>\"']+", s):
        tok = unicodedata.normalize("NFKD", tok).encode("ascii", "ignore").decode().lower().strip("._-~@!?*")
        if tok in _LID_STOP or not _LID_OK.fullmatch(tok):
            continue
        if not re.search(r"[a-z]", tok) and len(tok) < 6:
            continue                            # เลขสั้นๆ ไม่ใช่ไอดี
        if tok not in out:
            out.append(tok)
    return [x for x in out if x][:3]


def contact_keys(phone_text, line_text=None) -> list:
    """คีย์จับคู่ลูกค้า: "p:<เบอร์>" + "l:<ไอดีไลน์>" · ช่องเบอร์โทรของชีตส่งค่าเดียวกันทั้ง 2 อาร์กิวเมนต์"""
    from . import phonebook
    keys = ["p:" + p for p in phonebook.phones_in(phone_text)]
    if line_text:                                   # ไอดีไลน์ที่ตั้งเป็นเบอร์ = เบอร์
        keys += ["p:" + p for p in phonebook.phones_in(line_text) if "p:" + p not in keys]
    for x in line_ids(phone_text if line_text is None else line_text):
        if "l:" + x not in keys:
            keys.append("l:" + x)
    return keys


def _names() -> dict:
    """เลขลีด → ชื่อลูกค้า (ชีตลีดไม่มีช่องชื่อ) — จากงานจ่ายเบอร์ · แชท · ลีดภายนอก · ใบจ่ายลีดในกลุ่ม"""
    from .models import ChatLead, CustomerNeed, ExtLead, LeadTask
    out = {}
    for code, name in CustomerNeed.objects.exclude(lead_code="").exclude(customer_name="") \
            .values_list("lead_code", "customer_name")[:60000]:
        out.setdefault(norm_code(code), name)
    for M, f in ((ExtLead, "customer_name"), (ExtLead, "account"), (ChatLead, "customer_name"),
                 (ChatLead, "account"), (LeadTask, "customer")):
        for code, name in M.objects.exclude(code="").exclude(**{f: ""}).values_list("code", f)[:60000]:
            out[norm_code(code)] = out.get(norm_code(code)) or name
    return out


def _hay(*parts) -> str:
    return " ".join(str(p or "")[:200] for p in parts).lower()


def _index(rows_, junk=None) -> dict:
    """ดัชนีจับคู่: code → แถว · คีย์ติดต่อ → แถว / ชุดลีด (lineage) · คีย์ที่ซ้ำเกินจริง = junk"""
    by_code, by_key, key_lins = {}, {}, {}
    for n, r in enumerate(rows_):
        if r["code"]:
            by_code.setdefault(r["code"], []).append(n)
        for k in r["keys"]:
            by_key.setdefault(k, []).append(n)
            key_lins.setdefault(k, set()).add(r["lin"])
    if junk is None:
        junk = {k for k, s in key_lins.items() if len(s) > KEY_CAP}
    for k in junk:
        by_key.pop(k, None)
        key_lins.pop(k, None)
    return {"by_code": by_code, "by_key": by_key, "key_lins": key_lins, "junk": junk}


def _sheet_idx(force: bool = False) -> dict:
    """ชีตลีดทุกแท็บ → แถว + ดัชนีจับคู่ (จำ 10 นาทีต่อ process) · ใหม่สุดก่อน
    แถวเก็บ **อ้างอิงแถวดิบ** (`raw`) ไม่คัดลอก 26 ช่อง — หน้าเว็บขอทีละไม่กี่ร้อยแถว ค่อยดึงตอนส่งออก"""
    if not force and _ROWS["val"] is not None and time.time() - _ROWS["at"] < ROWS_TTL:
        return _ROWS["val"]
    from dashboard.services.constants import normalize_seller
    from dashboard.services.google_sheets import LEADS_COL as L
    from dashboard.services.google_sheets import fetch_leads_by_month_tabs
    raw = fetch_leads_by_month_tabs() or []
    names = _names()
    out = []
    for r in raw:
        code = norm_code(_cell(r, L.lead_code))
        rawph = _cell(r, L.phone)
        keys = contact_keys(rawph)
        d = _date(_cell(r, L.received_date))
        z = _cell(r, L.customer_status).strip()
        ad = _cell(r, L.admin_status).strip()
        seller_raw = _cell(r, L.sales_rep).strip()
        car = (_cell(r, L.car_formula) or _cell(r, L.car_inquiry)).strip()[:80]
        row = {"src": "sheet", "raw": r, "code": code, "lin": lineage(code), "keys": keys,
               "date": d.isoformat() if d else "", "tk": _time_key(_cell(r, L.time)),
               "phone": next((k[2:] for k in keys if k[0] == "p"), ""),
               "lineId": next((k[2:] for k in keys if k[0] == "l"), ""),
               "seller": normalize_seller(seller_raw) or seller_raw,
               "channel": _cell(r, L.channel).strip(), "type": _cell(r, L.type).strip(), "car": car,
               "carAsk": _cell(r, L.car_inquiry).strip()[:120], "z": z, "admin": ad,
               "note": _cell(r, L.fill_sheet_note).strip()[:300], "name": names.get(code, "")}
        row["returned"] = any(w in (z + " " + ad) for w in RETURN_WORDS)
        row["hay"] = _hay(code, rawph, row["name"], car, row["carAsk"], row["channel"], seller_raw,
                          _cell(r, L.ads), row["type"], row["note"], z, ad)
        out.append(row)
    out.sort(key=lambda x: (x["date"], x["tk"], x["code"]), reverse=True)
    for n, row in enumerate(out):
        row["i"] = n
        row["lin"] = row["lin"] or "row:%d" % n          # ไม่มีเลขลีด = ลีดของตัวเอง
    ix = _index(out)
    for row in out:
        row["keys"] = [k for k in row["keys"] if k not in ix["junk"]]
        _set_flags(row, ix, None)
    stats = {"rows": len(out), "codes": len(ix["by_code"]),
             "codeDup": sum(1 for v in ix["by_code"].values() if len(v) > 1),
             "codeDupRows": sum(len(v) for v in ix["by_code"].values() if len(v) > 1),
             "phones": sum(1 for k in ix["key_lins"] if k[0] == "p"),
             "lineIds": sum(1 for k in ix["key_lins"] if k[0] == "l"),
             "contactDup": sum(1 for s in ix["key_lins"].values() if len(s) > 1),
             "noContact": sum(1 for r in out if not r["keys"]),
             "dupRows": sum(1 for r in out if r["codeDup"] or r["dup"]),
             "returned": sum(1 for r in out if r["returned"])}
    val = dict(ix, rows=out, stats=stats, at=time.time(),
               sellers=sorted({r["seller"] for r in out if r["seller"]})[:60])
    _ROWS.update(at=time.time(), val=val)
    return val


def rows(force: bool = False) -> list:
    """แถวชีตลีด (ใหม่สุดก่อน) — ใช้ใน leadflow.forward_code ด้วย"""
    return _sheet_idx(force)["rows"]


def _fmt_d(dt) -> str:
    if not dt:
        return ""
    d = timezone.localtime(dt) if timezone.is_aware(dt) else dt
    return "%d/%d/%02d" % (d.day, d.month, d.year % 100)        # รูปแบบเดียวกับชีต (8/10/26)


def _fmt_t(dt) -> str:
    if not dt:
        return ""
    d = timezone.localtime(dt) if timezone.is_aware(dt) else dt
    return "%02d:%02d" % (d.hour, d.minute)


def _fmt_dt(dt) -> str:
    return ("%s %s" % (_fmt_d(dt), _fmt_t(dt).lstrip("0") or "0")) if dt else ""


def _sys_idx(ix: dict) -> dict:
    """ลีดที่ **ระบบออกเลขให้แล้ว แต่ยังไม่มีแถวในชีตลีด** (จ่ายเบอร์ใน Connect · ลีดภายนอก · ไม้ 2)
    — Connect ไม่เขียนชีตเอง แอดมินลงชีตตามทีหลัง ช่วงนั้นลีดมีอยู่ที่เดียวคือระบบ
    เลขที่อยู่ในชีตแล้ว = แถวชีตชนะ (จด chatId ไว้เปิดแชทจากฐานข้อมูล) · ใบทดลอง/ลูกค้าจำลอง ไม่นับ"""
    if _SYS["val"] is not None and _SYS["key"] == ix["at"] and time.time() - _SYS["at"] < SYS_TTL:
        return _SYS["val"]
    from .models import ChatLead, ChatOwnerLog, ExtLead
    from . import connect as C
    out, linked = [], {}
    cls = list(ChatLead.objects.exclude(code="").filter(code_demo=False)
               .select_related("chat", "chat__owner", "chat__profile", "chat__fb_profile").order_by("-id")[:3000])
    nrep = {x["chat_id"]: x["n"] for x in ChatOwnerLog.objects.filter(
        action=ChatOwnerLog.REPLY, chat_id__in=[c.chat_id for c in cls]).values("chat_id").annotate(n=Count("id"))}
    for cl in cls:
        o = cl.chat
        try:
            if C.is_sim_row(o):
                continue
        except Exception:
            continue
        code = norm_code(cl.code)
        if code in ix["by_code"]:
            linked.setdefault(code, o.id)
            continue
        at = cl.assigned_at or o.last_in_at or cl.created_at
        seller = o.owner.nickname if o.owner_id else ""
        ph = cl.phone or ("ID LINE : %s" % cl.line_id if cl.line_id else "")
        v = [_fmt_d(at), ph, _fmt_t(at), cl.code, seller, cl.live_team, cl.admin_name or cl.assigned_by, cl.channel,
             cl.branch, cl.lead_type, cl.ads, cl.car_text, cl.car_model, cl.call_proof, cl.focus,
             _fmt_dt(o.first_reply_at), str(nrep.get(o.id) or ""), _fmt_dt(o.last_out_at), cl.fill_note,
             cl.admin_profile, cl.occupation, cl.income, cl.job_tenure, cl.pay_history, cl.customer_type,
             cl.customer_status]
        out.append(_sys_row("c:%d" % cl.id, o.id, code, at, v, contact_keys(cl.phone, cl.line_id),
                            cl.customer_name or cl.account))
    for e in ExtLead.objects.exclude(code="").filter(code_demo=False, no_code=False).order_by("-id")[:3000]:
        code = norm_code(e.code)
        if code in ix["by_code"]:
            continue
        at = e.assigned_at or e.parked_at or e.created_at
        ph = e.phone or ("ID LINE : %s" % e.line_id if e.line_id else "")
        v = [_fmt_d(at), ph, _fmt_t(at), e.code, e.seller_name, e.live, e.assigned_by, e.channel, "", "", e.ads,
             e.car_text, "", "", "", "", "", "", "", "", "", "", "", "", "", ""]
        out.append(_sys_row("e:%d" % e.id, None, code, at, v, contact_keys(e.phone, e.line_id),
                            e.customer_name or e.account))
    out.sort(key=lambda x: (x["date"], x["tk"], x["code"]), reverse=True)
    for r in out:
        r["keys"] = [k for k in r["keys"] if k not in ix["junk"]]
    sx = _index(out, junk=ix["junk"])
    val = dict(sx, rows=out, linked=linked)
    _SYS.update(at=time.time(), key=ix["at"], val=val)
    return val


def _sys_row(key, chat_id, code, at, v, keys, name) -> dict:
    v = [str(x or "").strip()[:300] for x in v]
    d = timezone.localtime(at).date() if at and timezone.is_aware(at) else (at.date() if at else None)
    return {"src": "system", "key": key, "chatId": chat_id, "v": v, "code": code, "lin": lineage(code) or key,
            "keys": keys, "date": d.isoformat() if d else "", "tk": _time_key(v[2]),
            "phone": next((k[2:] for k in keys if k[0] == "p"), ""),
            "lineId": next((k[2:] for k in keys if k[0] == "l"), ""),
            "seller": v[4], "channel": v[7], "type": v[9], "car": (v[12] or v[11])[:80], "carAsk": v[11][:120],
            "z": v[25], "admin": "", "note": v[18], "name": name or "", "returned": False,
            "hay": _hay(code, v[1], name, v[11], v[12], v[7], v[4], v[10], v[9], v[18], v[25])}


def _set_flags(row, ix, sx) -> None:
    """Code ซ้ำ = เลขเดียวกันมีกี่แถว · เบอร์/ไลน์ซ้ำ = คีย์ติดต่อเดียวกันอยู่กับลีด (lineage) อื่นกี่เลข
    (ไม้ 2 ของเลขเดิมไม่นับว่าซ้ำ — เป็นลีดเดียวกันที่ส่งต่อ)"""
    code = row["code"]
    nc = len(ix["by_code"].get(code, ())) + (len(sx["by_code"].get(code, ())) if sx else 0) if code else 0
    others, kinds = set(), set()
    for k in row["keys"]:
        s = set(ix["key_lins"].get(k, ()))
        if sx:
            s |= sx["key_lins"].get(k, set())
        s.discard(row["lin"])
        if s:
            others |= s
            kinds.add("phone" if k[0] == "p" else "line")
    row["codeDup"], row["dup"], row["dupKind"] = nc if nc > 1 else 0, len(others), sorted(kinds)


def _flags(row, ix, sx) -> dict:
    """ธงของแถว ณ ตอนนี้ (รวมลีดในระบบ) — แถวที่ไม่เกี่ยวกับลีดในระบบใช้ค่าที่คำนวณไว้"""
    touch = (row["code"] and row["code"] in sx["by_code"]) or any(k in sx["key_lins"] for k in row["keys"]) \
        or row["src"] == "system"
    if not touch:
        return {"codeDup": row["codeDup"], "dup": row["dup"], "dupKind": row["dupKind"]}
    tmp = {"code": row["code"], "keys": row["keys"], "lin": row["lin"]}
    _set_flags(tmp, ix, sx)
    return {"codeDup": tmp["codeDup"], "dup": tmp["dup"], "dupKind": tmp["dupKind"]}


def _key_of(row) -> str:
    return row["key"] if row["src"] == "system" else "s:%d:%s" % (row["i"], row["code"])


def _pub(row, ix, sx) -> dict:
    """แถวที่ส่งให้หน้าเว็บ — `v` = 26 ช่องตามลำดับชีต (ค่าดิบ)"""
    v = row["v"] if row["src"] == "system" else [str(_cell(row["raw"], i)).strip()[:300] for i in _col_idx()]
    lin = row["lin"]
    out = {"key": _key_of(row), "src": row["src"], "code": row["code"], "date": row["date"], "v": v,
           "name": row["name"], "z": row["z"], "returned": row["returned"], "phone": row["phone"],
           "lineId": row["lineId"], "seller": row["seller"], "channel": row["channel"], "car": row["car"],
           "carAsk": row["carAsk"], "admin": row["admin"], "note": row["note"],
           "fwdOf": lin if row["code"] and lin != row["code"] and not lin.startswith(("row:", "c:", "e:")) else ""}
    out.update(_flags(row, ix, sx))
    return out


def _forwarded(codes) -> set:
    """เลขที่ส่งต่อไม้ 2 ไปแล้ว (มีเลข R…/n ของเลขนั้นในระบบ)"""
    from .models import ChatLead, ExtLead, LeadTask
    done = set()
    for M in (LeadTask, ChatLead, ExtLead):
        for c in M.objects.filter(code__contains="/").values_list("code", flat=True)[:5000]:
            base = re.sub(r"/\d+$", "", c.upper())
            done.add(base[1:] if base.startswith("R") else base)
    return {c for c in codes if c in done}


def _groups(rows_, ix, sx) -> list:
    """แถวที่ซ้ำ (Code / เบอร์ / ไลน์) → รวมเป็นกลุ่มลูกค้าเดียวกัน (union-find) · กลุ่มใหม่สุดก่อน"""
    par = list(range(len(rows_)))

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a

    seen = {}
    for n, r in enumerate(rows_):
        for k in ([("c", r["code"])] if r["code"] else []) + [("k", k) for k in r["keys"]]:
            if k in seen:
                a, b = find(n), find(seen[k])
                if a != b:
                    par[a] = b
            else:
                seen[k] = n
    comp = {}
    for n in range(len(rows_)):
        comp.setdefault(find(n), []).append(n)
    groups = []
    for members in comp.values():
        rs = [rows_[n] for n in members]
        codes = {}
        for r in rs:
            if r["code"]:
                codes[r["code"]] = codes.get(r["code"], 0) + 1
        lins = {r["lin"] for r in rs}
        dup_codes = [c for c, n in codes.items() if n > 1]
        if len(lins) < 2 and not dup_codes:
            continue                                # มีแต่ไม้ 2 ของเลขเดียวกัน = ไม่ใช่ลีดซ้ำ
        rs.sort(key=lambda x: (x["date"], x["tk"]), reverse=True)
        parts = []
        if dup_codes:
            parts.append("Code %s ลงชีต %d แถว" % (dup_codes[0], codes[dup_codes[0]])
                         + (" (+อีก %d เลข)" % (len(dup_codes) - 1) if len(dup_codes) > 1 else ""))
        if len(lins) > 1:
            from . import phonebook
            ks = {}
            for r in rs:
                for k in r["keys"]:
                    ks[k] = ks.get(k, 0) + 1
            k = max(ks, key=ks.get) if ks else ""
            who = ("เบอร์ " + phonebook.pretty(k[2:])) if k.startswith("p:") else ("LINE " + k[2:]) if k else ""
            parts.append("%s · %d ลีด" % (who, len(lins)))
        groups.append({"label": " · ".join(p for p in parts if p), "rows": rs, "top": rs[0]["date"]})
    groups.sort(key=lambda g: g["top"], reverse=True)
    return groups


def search(q: str = "", mode: str = "all", status: str = "", seller: str = "", limit: int = 150) -> dict:
    """ค้นฐานข้อมูล Lead — เบอร์ (เต็ม/4 ตัวท้าย) · ID LINE · ชื่อ · รุ่นรถ · เลขลีด
    mode: all · dup (ลีดซ้ำ จัดกลุ่ม) · unsheeted (ในระบบ ยังไม่ลงชีต) · returned (คืนเคส รอไม้ 2)"""
    ix = _sheet_idx()
    sx = _sys_idx(ix)
    limit = max(20, min(int(limit or 150), 600))
    q = (q or "").strip().lower()
    # ค้นด้วยตัวเลข (เบอร์เต็ม / 4 ตัวท้าย / เลขรัน) เฉพาะตอนพิมพ์มาเป็นตัวเลขล้วน — พิมพ์ ID LINE ที่มีเลขท้าย
    # ("sayompoo2546") ต้องไม่ไปโดนลีดที่เลขรัน/เบอร์มี 2546
    digits = re.sub(r"\D", "", q) if re.fullmatch(r"[\d\s\-+()]+", q or "-") else ""

    def keep(r):
        if seller and r["seller"] != seller:
            return False
        if status and status not in (r["z"] or ""):
            return False
        if q:
            if digits and len(digits) >= 4 and (digits in r["phone"] or digits in re.sub(r"\D", "", r["code"])):
                return True
            return q in r["hay"]
        return True

    if mode == "unsheeted":
        base = list(sx["rows"])
    elif mode == "returned":
        base = [r for r in ix["rows"] if r["returned"]]
        fw = _forwarded({r["code"] for r in base})
        base = [r for r in base if r["code"] not in fw]
    else:
        base = heapq.merge(sx["rows"], ix["rows"], key=lambda x: (x["date"], x["tk"], x["code"]), reverse=True)
    res = [r for r in base if keep(r)]
    out_rows, total = [], len(res)
    if mode == "dup":
        dups = [r for r in res if any(_flags(r, ix, sx)[k] for k in ("codeDup", "dup"))]
        groups = _groups(dups, ix, sx)
        total = sum(len(g["rows"]) for g in groups)
        for gi, g in enumerate(groups):
            if len(out_rows) >= limit:
                break
            for j, r in enumerate(g["rows"]):
                p = _pub(r, ix, sx)
                p["grp"] = gi
                if j == 0:
                    p["grpLabel"] = g["label"]
                out_rows.append(p)
        extra = {"groups": len(groups)}
    else:
        out_rows = [_pub(r, ix, sx) for r in res[:limit]]
        extra = {}
    st = dict(ix["stats"], unsheeted=len(sx["rows"]))
    return dict({"rows": out_rows, "total": total, "stats": st, "cols": COLS, "sellers": ix["sellers"],
                 "limit": limit}, **extra)


def _find(ix, sx, key: str = "", code: str = ""):
    key = (key or "").strip()
    if key.startswith("s:"):
        try:
            _s, n, c = key.split(":", 2)
            r = ix["rows"][int(n)]
            if r["code"] == c:
                return r
            code = code or c                        # ชีตอ่านใหม่แล้ว ลำดับแถวเปลี่ยน → หาด้วยเลขแทน
        except (ValueError, IndexError):
            pass
    elif key[:2] in ("c:", "e:"):
        return next((r for r in sx["rows"] if r["key"] == key), None)
    code = norm_code(code)
    if not code:
        return None
    return next((r for r in ix["rows"] if r["code"] == code), None) or \
        next((r for r in sx["rows"] if r["code"] == code), None)


WHY = {"code": "Code เดียวกัน", "fwd": "ไม้ 2 / เลขเดิม", "phone": "เบอร์เดียวกัน", "line": "ไลน์เดียวกัน",
       "book": "ใบจ่ายลีด (ยังไม่ลงชีต)"}


def detail(code: str = "", key: str = "") -> dict:
    """ลีด 1 แถว: 26 ช่อง + **ลีดที่ตรงกัน** (Code / ไม้ 2 / เบอร์ / ไลน์ / ใบจ่ายลีด) + งานจ่ายเบอร์ + รายงานผล"""
    from .models import LeadReport, LeadTask
    from . import leadflow, phonebook
    ix = _sheet_idx()
    sx = _sys_idx(ix)
    row = _find(ix, sx, key, code)
    if not row:
        return {"error": "ไม่พบเลข %s ในชีตลีด" % (norm_code(code) or key)}
    code = row["code"]
    matches, seen = [], {id(row)}

    def add(r, why):
        if id(r) in seen:
            return
        seen.add(id(r))
        matches.append({"key": _key_of(r), "code": r["code"], "date": r["date"], "seller": r["seller"],
                        "channel": r["channel"], "z": r["z"], "src": r["src"], "why": why, "whyText": WHY[why],
                        "lin": r["lin"], "name": r["name"], "contact": r["phone"] and phonebook.pretty(r["phone"]) or r["lineId"]})

    for src, x in (("sheet", ix), ("system", sx)):
        rs = x["rows"]
        if code:
            for n in x["by_code"].get(code, ()):
                add(rs[n], "code")
    for src, x in (("sheet", ix), ("system", sx)):
        rs = x["rows"]
        for k in row["keys"]:
            for n in x["by_key"].get(k, ()):
                r = rs[n]
                add(r, "fwd" if r["lin"] == row["lin"] else ("phone" if k[0] == "p" else "line"))
    if row["phone"]:
        for b in phonebook.lookup(row["phone"], exclude_code=code):
            bc = norm_code(b.get("code"))
            if bc and not any(m["code"] == bc for m in matches) and bc != code:
                matches.append({"key": "", "code": bc, "date": b.get("date") or "", "seller": b.get("seller") or "",
                                "channel": b.get("channel") or "", "z": "", "src": b.get("source") or "", "why": "book",
                                "whyText": WHY["book"], "name": "", "contact": phonebook.pretty(row["phone"])})
    order = {"code": 0, "fwd": 1, "phone": 2, "line": 2, "book": 3}
    matches.sort(key=lambda m: m["date"], reverse=True)          # ใหม่สุดก่อน แล้วค่อยจัดตามเหตุผล (เรียงคงที่)
    matches.sort(key=lambda m: order[m["why"]])
    tasks, reps = [], []
    if code:
        base = re.sub(r"/\d+$", "", code)
        core = base[1:] if base.startswith("R") else base
        for t in LeadTask.objects.filter(Q(code__iexact=code) | Q(code__istartswith="R" + core)).order_by("-id")[:10]:
            tasks.append(dict(leadflow.task_state(t), code=t.code, seller=t.seller_name, by=t.by,
                              postedAt=leadflow._iso(t.posted_at), reports=t.reports, lastReport=t.last_report,
                              history=[h.get("seller") for h in (t.history or [])]))
        reps = [{"at": leadflow._iso(r.sent_at), "seller": r.seller_name, "text": r.text[:300], "state": r.state}
                for r in LeadReport.objects.filter(code__iexact=code).order_by("-sent_at")[:20]]
    done = leadflow.forwarded_as(code) if code else None
    pub = _pub(row, ix, sx)
    chat_id = row.get("chatId") or sx["linked"].get(code)
    others = [{"code": m["code"], "seller": m["seller"], "date": m["date"], "channel": m["channel"], "why": m["why"]}
              for m in matches if m["why"] in ("phone", "line", "book")]
    return {"row": pub, "cols": COLS, "matches": matches[:40], "others": others[:20], "tasks": tasks, "reports": reps,
            "fwd": "" if (done or not code) else leadflow.fwd_code(code), "fwdDone": done, "chatId": chat_id}


# ─────────────────────────────────────────────────────────────
#  ไปป์ไลน์
# ─────────────────────────────────────────────────────────────
PIPE_COLS = ["จอง", "รอเซ็นต์", "รอผล", "รอปล่อย", "ปล่อย"]
STUCK = {"จอง": 3, "รอเซ็นต์": 3, "รอผล": 5, "รอปล่อย": 3}


def _days_since(s, today):
    d = _date(s)
    return (today - d).days if d else None


def pipeline(limit: int = 60) -> dict:
    """เคสจองเดือนนี้ (ที่ยังเดินอยู่) + ปล่อยเดือนนี้ — จากชีตยอดขาย · ค้างนานเกินกำหนด = ติดป้าย"""
    from dashboard.services.fetch_dashboard import fetch_dashboard_data, parse_month_day
    data = fetch_dashboard_data() or {}
    today = timezone.localdate()
    cols = {c: [] for c in PIPE_COLS}
    for b in data.get("bookingCases") or []:
        st = (b.get("status") or "").strip()
        if st not in cols:
            continue
        if st == "ปล่อย":
            md = parse_month_day(b.get("releaseDate") or "")
            if not md or md[0] != today.month:
                continue
            ref, days = b.get("releaseDate"), None
        else:
            ref = {"จอง": b.get("date"), "รอเซ็นต์": b.get("date"),
                   "รอผล": b.get("signDate") or b.get("date"),
                   "รอปล่อย": b.get("resultDate") or b.get("signDate") or b.get("date")}[st]
            days = _days_since(ref, today)
            if days is not None and (days > 120 or days < 0):
                continue                                    # วันที่ปีผิด/เคสเก่ามาก — ไม่ใช่งานที่กำลังเดิน
        cols[st].append({"customer": b.get("customer") or "-", "car": b.get("car") or "", "seller": b.get("seller") or "",
                         "price": b.get("price") or 0, "code": b.get("leadCode") or "", "date": b.get("date") or "",
                         "days": days, "stuck": bool(days is not None and st in STUCK and days > STUCK[st])})
    out = []
    for c in PIPE_COLS:
        items = sorted(cols[c], key=lambda x: (-(x["days"] or 0) if c != "ปล่อย" else 0))
        out.append({"status": c, "count": len(items), "value": sum(x["price"] for x in items),
                    "stuck": sum(1 for x in items if x["stuck"]), "items": items[:limit]})
    return {"cols": out, "stuckRule": STUCK, "at": data.get("generatedAt") or ""}


# ─────────────────────────────────────────────────────────────
#  แดชบอร์ดทีม
# ─────────────────────────────────────────────────────────────
def _month_summary(data, m):
    ms = data.get("monthlySummary") or {}
    return ms.get(m) or ms.get(str(m)) or {}


def team(now=None) -> dict:
    from dashboard.services.fetch_dashboard import fetch_dashboard_data
    from . import connect as C
    from .checkin_report import THAI_DAYS
    from .models import ChatLead, ChatOwner, ChatOwnerLog, LeadTask
    now = now or timezone.now()
    today = timezone.localdate()
    t0 = timezone.make_aware(datetime.combine(today, datetime.min.time()))
    m0 = timezone.make_aware(datetime.combine(today.replace(day=1), datetime.min.time()))
    data = fetch_dashboard_data() or {}
    ms = _month_summary(data, today.month)
    msel = ms.get("sellers") or {}

    # ใบทดลอง (บัญชีทดสอบ/ลูกค้าจำลอง) ไม่นับ — กรองใน Python (exclude บนคีย์ JSON ตัดแถวทิ้งหมดบน SQLite)
    tasks_today = [t for t in LeadTask.objects.filter(created_at__gte=t0)
                   .values("seller_id", "posted_at", "due_at", "first_report_at", "passed_at", "card")
                   if not (t["card"] or {}).get("demo")]
    reps = ChatOwnerLog.objects.filter(action=ChatOwnerLog.REPLY, at__gte=t0)
    rep_all = reps.count()
    rep_ok = reps.filter(on_time=True).count()

    def overdue(t):
        return bool(t["posted_at"] and t["due_at"] and not t["passed_at"]
                    and ((t["first_report_at"] and t["first_report_at"] > t["due_at"])
                         or (not t["first_report_at"] and now > t["due_at"])))

    chats_m = ChatOwner.objects.filter(created_at__gte=m0).count()
    contact_m = (ChatLead.objects.filter(chat__created_at__gte=m0)
                 .filter(~Q(phone="") | ~Q(line_id="")).count())
    funnel = [{"k": "แชทใหม่เข้า Connect", "v": chats_m, "src": "Connect"},
              {"k": "ได้เบอร์/ID LINE", "v": contact_m, "src": "Connect"},
              {"k": "ลีดในชีตเดือนนี้", "v": int(ms.get("lead") or 0), "src": "ชีตลีด"},
              {"k": "จองเดือนนี้", "v": int(ms.get("booking") or 0), "src": "ชีตลีด"},
              {"k": "ปล่อยเดือนนี้", "v": int(ms.get("done") or 0), "src": "ชีตยอดขาย"}]

    c = C.cfg()
    duty = C.duty_team(today, c)
    dname = THAI_DAYS[today.weekday()]
    by_emp = {}
    for t in tasks_today:
        by_emp.setdefault(t["seller_id"], []).append(t)
    six = [today - timedelta(days=i) for i in range(5, -1, -1)]
    s0 = timezone.make_aware(datetime.combine(six[0], datetime.min.time()))
    spark = {}
    for sid, d in (LeadTask.objects.filter(created_at__gte=s0, seller__isnull=False)
                   .values_list("seller_id", "created_at")):
        spark.setdefault(sid, {}).setdefault(timezone.localtime(d).date(), 0)
        spark[sid][timezone.localtime(d).date()] += 1
    rep_by = {r["employee_id"]: r for r in reps.values("employee_id")
              .annotate(n=Count("id"), ok=Count("id", filter=Q(on_time=True)))}
    sellers = []
    from .models import Employee
    emps = {e.id: e for e in Employee.objects.filter(active=True)}
    for s in C.seller_list():
        if s.get("test"):
            continue
        e = emps.get(s["id"])
        mine = by_emp.get(s["id"], [])
        rp = rep_by.get(s["id"]) or {}
        stat = "หยุดวันนี้" if (e and e.day_off and dname in e.day_off) else \
               ("เวรรับแชทวันนี้" if s["team"] == duty else "รับลีดอยู่")
        mm = msel.get(s["name"]) or {}
        sellers.append({"id": s["id"], "name": s["name"], "team": s["team"], "leadsToday": len(mine),
                        "reported": sum(1 for t in mine if t["first_report_at"]),
                        "late": sum(1 for t in mine if overdue(t)),
                        "replies": rp.get("n", 0), "repliesOk": rp.get("ok", 0),
                        "booking": int(mm.get("booking") or 0), "done": int(mm.get("done") or 0),
                        "spark": [spark.get(s["id"], {}).get(d, 0) for d in six], "status": stat})
    sellers.sort(key=lambda x: (x["team"], x["name"]))
    return {"date": today.isoformat(), "dayName": dname, "duty": duty,
            "tiles": {"tasksToday": len(tasks_today),
                      "lateToday": sum(1 for t in tasks_today if overdue(t)),
                      "reportedToday": sum(1 for t in tasks_today if t["first_report_at"]),
                      "repAll": rep_all, "repOk": rep_ok,
                      "doneMonth": int(ms.get("done") or 0), "bookingMonth": int(ms.get("booking") or 0)},
            "funnel": funnel, "sellers": sellers, "sixDays": [d.isoformat() for d in six]}
