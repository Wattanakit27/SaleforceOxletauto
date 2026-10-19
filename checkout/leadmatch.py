# -*- coding: utf-8 -*-
"""จับคู่ลูกค้าแชทกับลีดที่แอดมินเก็บ/จ่ายไปแล้ว — เบอร์ · ID LINE · ชื่อ Account (★ 18 ต.ค.69)

เจ้าของ *"แมทเบอร์และแอคเค้าด้วยนะ … อยากมั่นใจว่ามันไม่มีข้อมูลส่วนไหนหลุดหรือซ้ำกับที่เราหรือแอดมินเก็บมาแล้ว"*

ตรวจของจริง 18 ต.ค.69 (แชท 7 วันที่ให้เบอร์/ID แล้ว 124 ราย): แอดมินจ่ายไปแล้ว 90 ราย แต่ตัวจับคู่เดิม
(`connect.find_slip` = เบอร์ + ชื่อไลน์ · `sheet_match` = เบอร์) **รู้เองแค่ 3 ราย** — ที่เหลือแอดมินจับคู่ด้วย
ID LINE หรือชื่อบัญชี (ลูกค้าเพจส่วนใหญ่ไม่ให้เบอร์ · ส่งรูป QR แล้วใบเขียนว่า "QR code")
→ ถ้าเปิดจ่ายอัตโนมัติด้วยตัวจับคู่เดิม 87 รายจะได้เลขซ้ำ

กติกา
  · **เบอร์ / ID LINE ตรง = เชื่อได้** (ใช้ตัดสินว่าจ่ายแล้ว)
  · **ตรงแค่ชื่อ = "อาจใช่"** — ชื่อเฟซบุ๊กซ้ำกันได้ ไม่ให้ระบบตัดสินเอง (แจ้งแอดมินพร้อมเลขที่น่าจะใช่)
    ชื่อต้องตรงทั้งชื่อ (หลังตัดช่องว่าง/อีโมจิ/ตัวพิมพ์) · ไม่ fuzzy (บทเรียนเดิม: substring จับคนผิดคน)
    · ช่องทางในใบต้องไม่ขัด (ใบเขียน LINE@ แต่ลูกค้าทักเพจ = คนละคน)
  · ID LINE ที่เป็นคำแทนรูป QR ("QR code"/"Line@") ไม่นับ (`leadpark.clean_line_id`)
"""
from __future__ import annotations

import re
import time
import unicodedata
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from .models import ChatLead, ExtLead, GroupChat

INDEX_DAYS = 21          # ใบในกลุ่มที่ใช้จับคู่ (แชทกลุ่มเก็บ 90 วัน — แต่จับคู่เฉพาะรอบที่คุยกันอยู่)
CACHE_SEC = 60
MIN_NAME = 3
_IDX = {"at": 0.0, "val": None}


_LME = re.compile(r"(?i)line\.me/(?:r/)?ti/p/~?([a-z0-9._%\-~@]+)")


def lid_core(v) -> str:
    """ID LINE → ตัวที่ใช้เทียบ ("@Abc.Def" → "abcdef") · คำแทนรูป QR/สั้นเกิน/เป็นเลขล้วน = ""
    ลิงก์ line.me/ti/p/~xxx = xxx (ลิงก์จากรูป QR แบบโทเคนเทียบกับใบไม่ได้อยู่แล้ว — ใบเขียน "QR code")
    ★ เทียบด้วยตัวนี้เสมอ ห้ามค้นข้อความตรงๆ — คนพิมพ์ "abc.def99" / "abc_def99" / "@ABCdef99" คือไอดีเดียวกัน"""
    from .leadpark import clean_line_id
    raw = str(v or "")
    m = _LME.search(raw)
    s = m.group(1) if m else clean_line_id(raw)
    s = re.sub(r"[\s@\-_.~%]", "", s).lower()
    return s if len(s) >= 4 and not s.isdigit() else ""


def name_key(v) -> str:
    """ชื่อบัญชี → ตัวเทียบ · NFC (ไม่ใช่ NFKC — แยกสระ "ำ") · ตัดอีโมจิ/ช่องว่าง/เครื่องหมาย · ตัด "Oxlet Auto" ท้ายชื่อพนักงาน"""
    s = unicodedata.normalize("NFC", str(v or "")).lower()
    s = re.sub(r"oxlet\s*auto|อ๊อกเล็ตธ์\s*ออโต้", "", s)
    s = "".join(ch for ch in s if ch.isalnum() or "฀" <= ch <= "๿")
    return s if len(s) >= MIN_NAME else ""


def _phones(*vals) -> set:
    from .connect import phones_in
    return set(phones_in([v for v in vals if v]))


def _park_q() -> Q:
    from .leadpark import PARK_HINTS
    q = Q()
    for h in PARK_HINTS:
        q |= Q(group_name__icontains=h)
    return q


def index(force: bool = False) -> list:
    """ใบจ่ายลีด (ห้องจ่ายเบอร์) + ใบร่าง (กลุ่มพักลีด) ย้อน INDEX_DAYS วัน → ตัวเทียบ · จำผล 60 วิต่อ process
    `[{kind: slip|draft, pk, at, code, phones, lid, names, channel, tag}]`"""
    now = time.time()
    if not force and _IDX["val"] is not None and now - _IDX["at"] < CACHE_SEC:
        return _IDX["val"]
    from .connect import _lead_group_ids
    from .leadgroup import parse_fields, parse_leadsheet
    from .leadpark import parse_draft
    since = timezone.now() - timedelta(days=INDEX_DAYS)
    gids = _lead_group_ids()
    base = (GroupChat.objects.filter(chat_type=GroupChat.GROUP, sent_at__gte=since, text__icontains="lead no")
            .exclude(message_id__startswith="auto-lead-"))     # ★ 19 ต.ค.69 ใบของระบบเก็บลีดเอง ไม่ใช่ของแอดมิน
    qs = base.filter(Q(group_id__in=gids) | _park_q()) if gids else base.filter(_park_q())
    out = []
    for pk, gid, gname, text, at in qs.values_list("pk", "group_id", "group_name", "text", "sent_at").iterator():
        park = any(h in (gname or "").lower() for h in _park_hints())
        d = parse_draft(text or "") if park else parse_leadsheet(text or "")
        if not d:
            continue
        f = dict(parse_fields(text or ""))
        f.update({k: v for k, v in d.items() if isinstance(v, str)})
        names = {name_key(f.get(k)) for k in ("account", "name", "line_name")}
        out.append({"kind": "draft" if park else "slip", "pk": pk, "at": at,
                    "code": "" if park else (d.get("lead_code_full") or d.get("lead_code") or ""),
                    "phones": _phones(f.get("phone"), f.get("line_id"), *(d.get("phones") or [])), "lid": lid_core(f.get("line_id")),
                    "names": {n for n in names if n}, "channel": f.get("channel") or "", "tag": d.get("assigned") or ""})
    _IDX.update(at=now, val=out)
    return out


def _park_hints():
    from .leadpark import PARK_HINTS
    return PARK_HINTS


def forget():
    _IDX.update(at=0.0, val=None)
    _SHEET_LID.update(at=0.0, val=None)


def find(phones=(), lid: str = "", names=(), fb=None, since=None, kinds=("slip", "draft")) -> list:
    """ใบที่ตรงกับลูกค้าคนนี้ → `[(ใบ, [ตรงด้วย…], strong)]` ใหม่สุดก่อน · strong = เบอร์/ID LINE ตรง"""
    from .connect import _channel_fits
    phones, names = set(phones or ()), {n for n in (names or ()) if n}
    out = []
    for doc in index():
        if doc["kind"] not in kinds or (since and doc["at"] and doc["at"] < since):
            continue
        how = []
        if phones & doc["phones"]:
            how.append("เบอร์")
        if lid and lid == doc["lid"]:
            how.append("ID LINE")
        if names & doc["names"] and (fb is None or _channel_fits(doc["channel"], fb)):
            how.append("ชื่อ")
        if how:
            out.append((doc, how, "เบอร์" in how or "ID LINE" in how))
    out.sort(key=lambda x: x[0]["at"] or timezone.now(), reverse=True)
    return out


def slip_by_lid(line_id, since=None):
    """ใบในห้องจ่ายเบอร์ที่ ID LINE ตรง (ล่าสุด) → (ข้อมูลใบ, แถวแชท) แบบเดียวกับ `connect.find_slip`"""
    from .leadgroup import parse_leadsheet
    lid = lid_core(line_id)
    if not lid:
        return None
    for doc, how, strong in find(lid=lid, since=since, kinds=("slip",)):
        g = GroupChat.objects.filter(pk=doc["pk"]).first()
        d = parse_leadsheet(g.text or "") if g else None
        if d:
            return d, g
    return None


SHEET_LID_TTL = 600
_SHEET_LID = {"at": 0.0, "val": None}


def _sheet_lid_index() -> dict:
    """สำเนาชีตลีดทุกแท็บ → `{ตัวเทียบ ID LINE: [(วันรับลีด, แถว, Code, เซลล์), …]}` ใหม่สุดก่อน · จำ 10 นาที
    ช่อง "เบอร์โทร" ของชีตเก็บ "ID LINE : xxx" ด้วย → อ่านด้วย `console_data.line_ids` ตัวเดียวกับฐานข้อมูล Lead"""
    now = time.time()
    if _SHEET_LID["val"] is not None and now - _SHEET_LID["at"] < SHEET_LID_TTL:
        return _SHEET_LID["val"]
    idx = {}
    try:
        from dashboard.models import LeadSheetRow
        from .console_data import line_ids
        rows = (LeadSheetRow.objects.exclude(code="").filter(phone__iregex=r"[a-z]")
                .values_list("phone", "code", "seller", "received_date", "row_no"))
        for phone, code, seller, rd_, rn in rows.iterator():
            for x in line_ids(phone):
                core = lid_core(x)
                if core:
                    idx.setdefault(core, []).append((rd_, rn or 0, (code or "").strip().upper(), seller or ""))
    except Exception:
        return _SHEET_LID["val"] or {}
    from datetime import date as _date
    for v in idx.values():
        v.sort(key=lambda t: (t[0] or _date.min, t[1]), reverse=True)
    _SHEET_LID.update(at=now, val=idx)
    return idx


def sheet_by_lid(line_id, last_in=None, chat_lead_pk=None, days: int = 14) -> dict | None:
    """ID LINE นี้ได้เลขในชีตลีด (สำเนาใน Postgres) ในรอบที่คุยกันอยู่ → รูปเดียวกับ `connect.sheet_match`
    เลขที่ลีดอื่นในระบบถืออยู่แล้ว = None (ไม่ก๊อปเลขเดียวไป 2 ที่)"""
    core = lid_core(line_id)
    if not core:
        return None
    ref = timezone.localtime(last_in).date() if last_in else timezone.localdate()
    cut = ref - timedelta(days=days)
    rows = [r for r in _sheet_lid_index().get(core, []) if r[0] and r[0] >= cut and r[2]]
    if not rows:
        return None
    held = Q()
    for c in {r[2] for r in rows}:
        held |= Q(code__iexact=c)
    if ChatLead.objects.filter(held).exclude(pk=chat_lead_pk).exists() or ExtLead.objects.filter(held).exists():
        return None
    top = rows[0]
    from datetime import datetime as _dt, time as _time
    from .connect import _iso
    at = timezone.make_aware(_dt.combine(top[0], _time(9, 0)))
    return {"code": top[2], "seller": top[3], "date": top[0].isoformat(), "src": "sheet-lid",
            "codes": [r[2] for r in rows][:6], "at": _iso(at)}


def sheet_lid_any(line_id) -> dict | None:
    """ID LINE นี้เคยเป็นลีดในชีต (ทุกแท็บ) → `{code, seller, date}` ล่าสุด — ใช้ดูว่าเป็นลูกค้าเก่าไหม"""
    rows = _sheet_lid_index().get(lid_core(line_id) or "-", [])
    if not rows:
        return None
    r = rows[0]
    return {"code": r[2], "seller": r[3], "date": r[0].isoformat() if r[0] else ""}


def lid_taken(line_id, days: int = 14, exclude_lead=None, exclude_ext=None) -> dict | None:
    """ID LINE นี้ได้เลขไปแล้วใน `days` วัน (แชท/ลีดภายนอก/ชีต) → `{code, where}` · ใช้กันจ่ายซ้ำ
    `days=0` = ทุกช่วงเวลา (ใช้ดูว่าเป็นลูกค้าเก่าไหม) · เทียบด้วยตัวเทียบ (จุด/ขีด/ตัวพิมพ์ไม่มีผล)"""
    core = lid_core(line_id)
    if not core:
        return None
    cut = timezone.now() - timedelta(days=days) if days else None
    qs = ChatLead.objects.exclude(code="").exclude(line_id="").exclude(pk=exclude_lead)
    if cut is not None:
        qs = qs.filter(updated_at__gte=cut)
    for chat_id, lid, code in qs.values_list("chat_id", "line_id", "code").iterator():
        if lid_core(lid) == core:
            return {"code": code, "where": "แชท #%s" % chat_id}
    qe = ExtLead.objects.exclude(code="").exclude(line_id="").exclude(pk=exclude_ext)
    if cut is not None:
        qe = qe.filter(Q(assigned_at__gte=cut) | Q(assigned_at__isnull=True, updated_at__gte=cut))
    for lid, code in qe.values_list("line_id", "code").iterator():
        if lid_core(lid) == core:
            return {"code": code, "where": "ลีดในห้องพัก"}
    if cut is None:
        sh = sheet_lid_any(line_id)
        return {"code": sh["code"], "where": ("ชีตลีด " + (sh.get("date") or "")).strip()} if sh else None
    sh = sheet_by_lid(line_id, days=days)
    return {"code": sh["code"], "where": "ชีตลีด"} if sh else None


def chat_names(o, lead=None) -> set:
    """ชื่อของลูกค้าแชทนี้ที่ใช้เทียบกับใบ: ชื่อใน LINE/Facebook + ชื่อ Account/ชื่อลูกค้าในข้อมูลลีด"""
    from .connect import cust
    p = cust(o)
    vals = [getattr(p, "display_name", "")]
    if lead is not None:
        vals += [lead.account, lead.customer_name]
    return {n for n in (name_key(v) for v in vals) if n}


def name_hint(o, lead, since=None) -> dict | None:
    """ใบจ่ายลีดที่ตรงแค่ "ชื่อ" (เบอร์/ID ไม่ตรงหรือไม่มี) → `{code, at, tag}` = อาจจ่ายแล้ว ให้แอดมินดู"""
    from .connect import _iso, is_fb
    hits = find(names=chat_names(o, lead), fb=is_fb(o), since=since, kinds=("slip",))
    hits = [h for h in hits if not h[2] and h[0]["code"]]
    if not hits:
        return None
    doc = hits[0][0]
    return {"code": doc["code"], "at": _iso(doc["at"]), "tag": doc["tag"], "how": "ชื่อ"}


def chat_name_taken(name, fb=None, days: int = 2) -> dict | None:
    """ชื่อในใบร่างตรงกับลูกค้าแชทที่ระบบเพิ่งจ่ายเลขให้ (จ่ายวนอัตโนมัติ) → `{code, chat}` — กันใบร่างซ้ำกับแชท"""
    key = name_key(name)
    if not key:
        return None
    from .connect import cust, is_fb
    cut = timezone.now() - timedelta(days=days)
    for lead in (ChatLead.objects.filter(assigned_at__gte=cut, assigned_by__startswith="จ่ายวนอัตโนมัติ")
                 .exclude(code="").select_related("chat", "chat__profile", "chat__fb_profile")[:200]):
        o = lead.chat
        if fb is not None and is_fb(o) != fb:
            continue
        if key in {name_key(getattr(cust(o), "display_name", "")), name_key(lead.account)}:
            return {"code": lead.code, "chat": o.id}
    return None
