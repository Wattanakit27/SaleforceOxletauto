# -*- coding: utf-8 -*-
"""**ลูกค้า Facebook มาจากโฆษณาตัวไหน** (★ 19 ต.ค.69 · เจ้าของสั่ง *"ลูกค้าที่มาจาก Ads ช่วย Tag Ads ด้วย ชื่อ Ads
เก็บไอดีแอดไว้ในฐานข้อมูล ในอนาคตถ้าปิดยอดได้จะได้แท็กถูก แต่การส่งให้แอดมินจะใช้ตัวตามรูปลงกลุ่มไลน์"*)

ลูกค้ากดโฆษณาแบบทักแชท (Click-to-Messenger) → ในห้องแชทมี **การ์ดโฆษณา** (ข้อความขาออกของเพจที่ไม่มีตัวอักษร
แต่มี `attachments.generic_template` = {title "รีบจอง ก่อนหมด !!!", subtitle "จว6456" / "ระหว่าง Mazda3 กับ Yaris Ativ รุ่นไหนดี",
media_url}) — **การ์ดไม่มี ad id** (ได้เฉพาะทาง webhook `referral` ซึ่งต้องผ่าน App Review ก่อน)

  · ช่อง **ADS** ของลีด (= บรรทัด "Ads :" ในใบที่ลงกลุ่ม LINE + คอลัมน์ ADS ในชีต) = **ข้อความบรรทัดล่างของการ์ด** (subtitle)
    ตามที่ลูกค้า/แอดมินเห็นใน Messenger · ไม่มี subtitle = บรรทัดบน
  · **ad id + ชื่อโฆษณา** (ชื่อใน Ads Manager) เก็บที่ `ChatLead.ad_id` / `ad_name` (+ รายละเอียดใน `auto["_ad"]`)
    — จับคู่ข้อความการ์ดกับชื่อโฆษณา: วัดจริง 19 ต.ค.69 แชท 60 ห้อง มีการ์ด 32 ห้อง **จับคู่ได้ทุกห้อง**
    (ตรงโฆษณาเดียว 20 · ชื่อเดียวกันหลายชิ้น 12 = โฆษณาตัวเดียวกันที่ก๊อปไปหลายกลุ่มเป้าหมาย → เลือกตัวที่ใช้เงินวันนั้นมากสุด
    + จดตัวเลือกทั้งหมดใน `ad_ids`) · webhook ส่ง `referral.ad_id` มาเมื่อไหร่ = ใช้ ad id นั้นตรงๆ (`how: exact`)
  · ชื่อโฆษณามาจาก `dash_meta_ad_daily` (meta_sync ทุกคืน) ก่อน · ไม่เจอ = รายชื่อโฆษณาจาก Marketing API (จำ 6 ชม. · KV `meta_ad_catalog`)
"""
from __future__ import annotations

import re
from datetime import timedelta

from django.utils import timezone

CARD_KEY = "_ad"              # ChatLead.auto[CARD_KEY] = {mid, at, title, subtitle, ad_id, ad_ids, ad_name, adset_*, campaign_*, how}
AD_SRC = "โฆษณา"              # auto["ads"] = ช่อง ADS เติมจากการ์ดโฆษณา (การ์ดใหม่แทนได้ · คนแก้แล้วไม่แตะ)
TEMPLATE = "template"         # FbChat.msg_type ของการ์ดโฆษณา
CATALOG_KEY = "meta_ad_catalog"
CATALOG_HOURS = 6
DAILY_DAYS = 14               # มองชื่อโฆษณาย้อนหลังกี่วันก่อนวันที่ลูกค้าทัก


def _nz(s) -> str:
    return re.sub(r"[\s!！.,·:;\-_/()\"'“”‘’|]+", "", str(s or "").lower())


# ── อ่านการ์ดโฆษณาจากข้อความ ────────────────────────────────────────────

def card_from_extra(extra) -> dict | None:
    """ข้อความ FbChat.extra → การ์ดโฆษณา {title, subtitle, media, ad_id} หรือ None
    รับทั้งรูปแบบ Graph API (attachments.data[].generic_template) และ webhook (referral / attachments เป็นลิสต์)"""
    x = extra or {}
    ref = x.get("referral") or {}
    if isinstance(ref, dict) and (ref.get("ad_id") or str(ref.get("source") or "").upper() == "ADS"):
        ctx = ref.get("ads_context_data") or {}
        return {"title": str(ctx.get("ad_title") or "")[:200], "subtitle": "", "media": "",
                "ad_id": str(ref.get("ad_id") or "")[:40], "post_id": str(ctx.get("post_id") or "")[:60]}
    att = x.get("attachments") or {}
    items = att.get("data") if isinstance(att, dict) else att
    for a in items or []:
        gt = (a or {}).get("generic_template") if isinstance(a, dict) else None
        if isinstance(gt, dict) and (gt.get("title") or gt.get("subtitle")):
            return {"title": str(gt.get("title") or "").strip()[:200], "subtitle": str(gt.get("subtitle") or "").strip()[:200],
                    "media": str(gt.get("media_url") or "")[:500], "ad_id": ""}
    return None


def is_card_msg(m: dict) -> bool:
    """ข้อความดิบจาก Graph API เป็นการ์ดโฆษณาไหม (fb_sync ใช้ตั้งชนิดข้อความ — ไม่ใช่ไฟล์ให้ดาวน์โหลด)"""
    return bool(card_from_extra(m))


def label(card: dict) -> str:
    """ข้อความในช่อง ADS / บรรทัด "Ads :" ของใบ — บรรทัดล่างของการ์ด (ตามที่เห็นใน Messenger) ไม่มี = บรรทัดบน"""
    return ((card or {}).get("subtitle") or (card or {}).get("title") or "").strip()[:120]


def preview(m) -> str:
    """ข้อความ 1 บรรทัดของการ์ดโฆษณา (รายชื่อแชท/บับเบิล)"""
    c = card_from_extra(getattr(m, "extra", None))
    if not c:
        return "[การ์ดโฆษณา]"
    t = " · ".join(v for v in (c.get("title"), c.get("subtitle")) if v)
    return "[การ์ดโฆษณา] %s" % t if t else "[การ์ดโฆษณา]"


def latest_card(o) -> dict | None:
    """การ์ดโฆษณาล่าสุดในห้องแชทนี้ (ลูกค้ากดโฆษณาครั้งล่าสุด) → dict + mid/at · ไม่มี = None"""
    from django.db.models import Q
    from .models import FbChat
    fp = getattr(o, "fb_profile", None)
    if not fp or not fp.thread_id:
        return None
    rows = (FbChat.objects.filter(thread_id=fp.thread_id)
            .filter(Q(msg_type=TEMPLATE) | Q(extra__has_key="referral"))
            .order_by("-sent_at", "-id")[:5])
    for m in rows:
        c = card_from_extra(m.extra)
        if c:
            return dict(c, mid=m.message_id, at=m.sent_at)
    return None


# ── จับคู่การ์ดกับโฆษณา ─────────────────────────────────────────────────

def _catalog() -> list:
    """รายชื่อโฆษณาทุกตัวของบัญชีบริษัท (Marketing API) — ใช้เมื่อหาใน dash_meta_ad_daily ไม่เจอ · จำ 6 ชม."""
    from dashboard.services import cache_store, meta
    try:
        kv = (cache_store.get_kv(CATALOG_KEY) or {}).get("data") or {}
    except Exception:
        kv = {}
    at = kv.get("at") or ""
    try:
        from datetime import datetime
        fresh = at and timezone.now() - datetime.fromisoformat(at) < timedelta(hours=CATALOG_HOURS)
    except Exception:
        fresh = False
    if fresh:
        return list(kv.get("ads") or [])
    ads = []
    try:
        for aid in sorted(meta.accounts()):
            for chunk in meta.paged("/act_%s/ads" % aid, fields="id,name,effective_status,adset{id,name},campaign{id,name}",
                                    limit=200, max_pages=10):
                for a in (chunk.get("data") or []):
                    ads.append({"ad_id": str(a.get("id") or ""), "ad_name": str(a.get("name") or "")[:200],
                                "adset_id": str((a.get("adset") or {}).get("id") or ""),
                                "adset_name": str((a.get("adset") or {}).get("name") or "")[:200],
                                "campaign_id": str((a.get("campaign") or {}).get("id") or ""),
                                "campaign_name": str((a.get("campaign") or {}).get("name") or "")[:200],
                                "status": str(a.get("effective_status") or "")})
    except Exception:
        return list(kv.get("ads") or [])          # ถาม Meta ไม่ได้ = ใช้รายชื่อเดิม (ถ้ามี)
    try:
        cache_store.set_kv(CATALOG_KEY, {"at": timezone.now().isoformat(timespec="seconds"), "ads": ads})
    except Exception:
        pass
    return ads


def _hit(card: dict, name: str) -> bool:
    """ชื่อโฆษณานี้ตรงกับการ์ดไหม — บรรทัดล่างของการ์ดอยู่ในชื่อ ("จว6456" ใน "Yaris Ativ จว6456") หรือชื่ออยู่ในบรรทัดล่าง"""
    return _strength(card, name) > 0


def _strength(card: dict, name: str) -> int:
    """ตรงแค่ไหน — 3 ชื่อเท่ากับบรรทัดล่างของการ์ด · 2 บรรทัดล่างอยู่ในชื่อ · 1 ชื่ออยู่ในบรรทัดล่าง/บรรทัดบน · 0 ไม่ตรง

    ★ 20 ต.ค.69 แยกระดับ เพราะชื่อสั้นกว้างๆ ("Fortuner" โฆษณาปี 2022) อยู่ในการ์ด "มุมมอง Fortuner ขับ 4" ด้วย
    ถ้านับเท่ากัน ตัวเก่าที่หยุดไปแล้วชนะตัวจริงได้ (เคสจริง NLD10-9681)"""
    s, n = _nz(card.get("subtitle")), _nz(name)
    if not n:
        return 0
    if s and len(s) >= 4:
        if s == n:
            return 3
        if s in n:
            return 2
        return 1 if (len(n) >= 6 and n in s) else 0
    t = _nz(card.get("title"))
    if not s and t and len(t) >= 6:
        if t == n:
            return 3
        return 1 if (len(n) >= 6 and n in t) else 0
    return 0


def match_ad(card: dict, at=None) -> dict:
    """การ์ดโฆษณา → {ad_id, ad_ids, ad_name, adset_id, adset_name, campaign_id, campaign_name, how}
    how: exact (webhook ให้ ad id) · unique (ชื่อตรงโฆษณาตัวเดียว) · spend (ชื่อตรงหลายตัว → ใช้เงินวันนั้นมากสุด) · none"""
    from dashboard.models import MetaAdDaily
    at = at or timezone.now()
    day = timezone.localtime(at).date() if timezone.is_aware(at) else at.date()
    out = {"ad_id": "", "ad_ids": [], "ad_name": "", "adset_id": "", "adset_name": "", "campaign_id": "",
           "campaign_name": "", "how": "none"}
    fields = ("ad_id", "ad_name", "adset_id", "adset_name", "campaign_id", "campaign_name", "date", "spend")
    if card.get("ad_id"):
        r = (MetaAdDaily.objects.filter(ad_id=card["ad_id"]).order_by("-date").values(*fields).first()
             or next((a for a in _catalog() if a["ad_id"] == card["ad_id"]), None) or {"ad_id": card["ad_id"]})
        out.update({k: str(r.get(k) or "") for k in out if k not in ("ad_ids", "how")})
        out.update(ad_id=card["ad_id"], ad_ids=[card["ad_id"]], how="exact")
        return out
    rows = [r for r in MetaAdDaily.objects.filter(date__gte=day - timedelta(days=DAILY_DAYS), date__lte=day)
            .values(*fields) if _hit(card, r["ad_name"])]
    top = max((_strength(card, r["ad_name"]) for r in rows), default=0)
    if top < 3:
        # ★ 20 ต.ค.69 ยอดรายวันที่เก็บไว้ยังไม่ตรงเป๊ะ → ดูรายชื่อโฆษณาทุกบัญชีด้วย ตรงกว่า = ใช้ตัวนั้น
        #   (เคสจริง: การ์ด "อ่อนนุช ออก CIVIC FE ได้ไหม" ได้โฆษณาบ้านเก่า "ออก CIVIC FE ได้ไหม" เพราะยอดรายวันมีแต่บัญชีบ้านเก่า
        #    ส่วนตัวจริงอยู่บัญชีเพจอ่อนนุชที่เพิ่งเริ่มเก็บ — ไม่ดูรายชื่อเลยเพราะยอดรายวันมีตัวที่ "พอตรง" แล้ว)
        cat = [dict(a, date=None, spend=0) for a in _catalog() if _strength(card, a.get("ad_name")) > top]
        if cat:
            best = max(_strength(card, a.get("ad_name")) for a in cat)
            rows = [a for a in cat if _strength(card, a.get("ad_name")) == best]
    if not rows:
        return out
    # ตรงชัดกว่าก่อน → วันที่ใกล้วันที่ลูกค้าทักที่สุด → ยังเปิดอยู่ → ใช้เงินมากสุด → โฆษณาใหม่กว่า (id มากกว่า)
    by_ad = {}
    for r in rows:
        aid = str(r["ad_id"] or "")
        if not aid:
            continue
        st = str(r.get("status") or "ACTIVE")         # แถวจาก dash_meta_ad_daily = มีใช้เงินวันนั้น ถือว่าเปิดอยู่
        key = (_strength(card, r.get("ad_name")), r.get("date") or day, st == "ACTIVE",
               float(r.get("spend") or 0), int(aid) if aid.isdigit() else 0)
        if aid not in by_ad or key > by_ad[aid][0]:
            by_ad[aid] = (key, r)
    ids = sorted(by_ad, key=lambda a: by_ad[a][0], reverse=True)
    best = by_ad[ids[0]][1]
    out.update({k: str(best.get(k) or "") for k in ("ad_id", "ad_name", "adset_id", "adset_name", "campaign_id", "campaign_name")})
    # ad_ids = โฆษณาชื่อเดียวกัน (ก๊อปหลายกลุ่มเป้าหมาย) ระดับเดียวกับตัวที่เลือก — ไม่เอาตัวที่แค่ชื่อกว้างๆ ติดมา
    same = [a for a in ids if by_ad[a][0][0] == by_ad[ids[0]][0][0]
            and _nz(by_ad[a][1].get("ad_name")) == _nz(best.get("ad_name"))]
    out["ad_ids"] = same[:10]
    out["how"] = "unique" if len(same) == 1 else "spend"
    return out


def apply(o, lead, auto: dict, put) -> list:
    """autofill (แชท FB): การ์ดโฆษณาล่าสุด → ช่อง ADS (ข้อความบนการ์ด) + ad id/ชื่อโฆษณา · คืนชื่อช่องที่เปลี่ยน

    ทำซ้ำเฉพาะตอนมีการ์ดใหม่ (ลูกค้ากดโฆษณาตัวอื่นภายหลัง = ใช้ตัวล่าสุด) หรือรอบก่อนยังจับคู่ ad id ไม่ได้ (รอ meta_sync)"""
    card = latest_card(o)
    if not card:
        return []
    cur = auto.get(CARD_KEY) or {}
    if cur.get("mid") == card["mid"] and (cur.get("ad_id") or cur.get("tried_at", "") > (timezone.now() - timedelta(hours=3)).isoformat()):
        return []
    lab = label(card)
    if lab:
        put("ads", lab, AD_SRC, over=(AD_SRC,))
    try:
        m = match_ad(card, card.get("at"))
    except Exception:
        m = {"ad_id": "", "ad_ids": [], "ad_name": "", "how": "error"}
    info = {"mid": card["mid"], "at": card["at"].isoformat(timespec="seconds") if card.get("at") else "",
            "title": card.get("title") or "", "subtitle": card.get("subtitle") or "",
            "tried_at": timezone.now().isoformat(timespec="seconds")}
    info.update({k: v for k, v in m.items()})
    auto[CARD_KEY] = info
    changed = [CARD_KEY]
    for f in ("ad_id", "ad_name"):
        v = str(m.get(f) or "")[:200 if f == "ad_name" else 40]
        if v and getattr(lead, f, "") != v:
            setattr(lead, f, v)
            changed.append(f)
    return changed


# ── เติมการ์ดให้ข้อความที่เก็บไว้ก่อนมีฟีเจอร์ (ครั้งเดียวหลัง deploy / autolead ก่อนส่งใบ) ─────────────

def refetch_thread(fp) -> int:
    """ถาม Graph API การ์ดโฆษณาของห้องนี้ (ข้อความ 25 อันล่าสุด) → แก้แถว FbChat ที่เก็บไว้แล้วให้มีการ์ด · คืนจำนวนที่แก้"""
    from dashboard.services import meta
    from .models import FbChat
    if not fp or not fp.thread_id or not fp.channel or not fp.user_id:
        return 0
    pt = meta.page_token(fp.channel)
    # ★ 20 ต.ค.69 ถามผ่านห้องแชทของเพจ (`/<page>/conversations?user_id=`) ไม่ใช่ `/<thread>/messages` ตรง —
    #   id ห้อง `t_…` ผ่านด่าน meta ได้เฉพาะเมื่อเคยเห็นในคำตอบของ process นี้ · คำสั่ง fb_adcards / worker ใหม่ = ไม่เคยเห็น
    #   → เคยล้มทุกห้อง (300/300) บน prod · ขึ้นต้นด้วยเพจของเรา = ผ่านด่านเสมอ และได้เฉพาะห้องของลูกค้าคนนี้กับเพจนี้
    d = meta.get("/%s/conversations" % fp.channel, _token=pt, user_id=fp.user_id,
                 fields="id,messages.limit(25){id,attachments{generic_template}}")
    convs = d.get("data") or []
    conv = next((x for x in convs if str(x.get("id") or "") == fp.thread_id), None) or (convs[0] if convs else {})
    n = 0
    for m in ((conv.get("messages") or {}).get("data") or []):
        if not is_card_msg(m):
            continue
        row = FbChat.objects.filter(message_id=str(m.get("id") or "")[:160]).first()
        if not row or row.msg_type == TEMPLATE:
            continue
        ex = dict(row.extra or {})
        ex["attachments"] = m.get("attachments")
        row.extra, row.msg_type, row.has_media = ex, TEMPLATE, False
        row.save(update_fields=["extra", "msg_type", "has_media"])
        n += 1
    return n


def ensure_card(o) -> bool:
    """แชท FB ที่ยังไม่เคยเห็นการ์ด (ข้อความเก็บก่อน deploy) → ถาม Graph ครั้งเดียว · จด auto["_ad_refetch"] กันถามซ้ำ"""
    from .connect import lead_of
    from .models import ChatLead
    if not getattr(o, "fb_profile_id", None) or latest_card(o):
        return False
    lead = lead_of(o, create=False)           # ตัวเดียวกับที่ autofill จะใช้ — จดไว้ในตัวนี้ ไม่งั้น autofill เขียนทับหาย
    if lead and (lead.auto or {}).get("_ad_refetch"):
        return False
    try:
        n = refetch_thread(o.fb_profile)
    except Exception:
        n = 0
    if lead:
        auto = dict(lead.auto or {})
        auto["_ad_refetch"] = timezone.now().isoformat(timespec="seconds")
        ChatLead.objects.filter(pk=lead.pk).update(auto=auto)
        lead.auto = auto
    return bool(n)


def backfill(days: int = 7, limit: int = 300, rematch: bool = False) -> dict:
    """ครั้งเดียวหลัง deploy: แชท FB ที่ลูกค้าทักใน `days` วัน → เติมการ์ดโฆษณา + จับคู่โฆษณา (autofill)
    `rematch` = จับคู่ชื่อโฆษณาใหม่ให้แชทที่จับคู่ไปแล้วด้วย (หลังแก้วิธีจับคู่ · ช่อง ADS ที่คนแก้แล้วไม่แตะเหมือนเดิม)"""
    from . import connect as C
    from .models import ChatLead, ChatOwner
    since = timezone.now() - timedelta(days=days)
    out = {"chats": 0, "cards": 0, "matched": 0, "changed": 0, "errors": 0, "why": []}
    for o in (ChatOwner.objects.select_related("fb_profile", "lead").filter(fb_profile__isnull=False, last_in_at__gte=since)
              .order_by("-last_in_at")[:limit]):
        out["chats"] += 1
        try:
            if not latest_card(o):
                refetch_thread(o.fb_profile)
            before = ""
            if rematch and latest_card(o):
                lead0 = ChatLead.objects.filter(chat=o).first()
                if lead0 and CARD_KEY in (lead0.auto or {}):
                    before = lead0.ad_id or ""
                    a = dict(lead0.auto)
                    a.pop(CARD_KEY, None)
                    ChatLead.objects.filter(pk=lead0.pk).update(auto=a)
                    o = ChatOwner.objects.select_related("fb_profile", "lead").get(pk=o.pk)
            if latest_card(o):
                out["cards"] += 1
                lead = C.autofill(o)
                if (lead.ad_id or "").strip():
                    out["matched"] += 1
                if before and (lead.ad_id or "") != before:
                    out["changed"] += 1
        except Exception as e:
            out["errors"] += 1
            w = "%s: %s" % (type(e).__name__, str(e)[:160])
            if w not in out["why"] and len(out["why"]) < 5:   # ★ ล้มแล้วต้องบอกว่าเพราะอะไร (เคยล้ม 300/300 แบบไม่มีเหตุผล)
                out["why"].append(w)
    return out
