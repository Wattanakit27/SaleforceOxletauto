# -*- coding: utf-8 -*-
"""คุย Meta Graph API — **แตะได้เฉพาะ asset ของบริษัทนี้** (ก.ย.69)

*"ตอนนี้ฉันทำงานอยู่สองบริษัท ซึ่งฉันต้องจัดการแยกกัน มันไม่ควรไปรวมกัน"*

**ทำไมต้องมีไฟล์นี้ (ไม่ใช่เรียก requests ตรง ๆ)**

token ของ Meta ออกในนาม **โปรไฟล์ Facebook ของคน** ไม่ใช่ในนามบริษัท →
`/me/adaccounts` คืน *ทุก* บัญชีที่คนนั้นแตะได้ ข้ามบริษัทหมด
วัดจริง ก.ย.69: token เห็น 4 บัญชี หนึ่งในนั้นเป็นของ **OSUKA (คนละบริษัท ขายเลื่อยยนต์
ใช้เงินสะสม 5 ล้านบาท)** เพราะโปรไฟล์เจ้าของถูกเพิ่มเป็นผู้ใช้บนบัญชีนั้นโดยตรง

**ออก token ใหม่ไม่ช่วย** — สิทธิ์ผูกกับตัวคน ไม่ใช่ตัว token (ทดสอบแล้ว 3 ตัว เห็น OSUKA ทุกตัว)
ทางเดียวที่กันได้คือ **ฝั่งเราต้องระบุให้ชัดว่าบริษัทนี้มี asset อะไร** แล้วปฏิเสธที่เหลือ

**กฎเหล็ก 3 ข้อ**
1. โค้ดที่ใช้งานจริง **ห้ามเรียก `/me/adaccounts` · `/me/accounts` · `/me/businesses`**
   — พวกนี้เหวี่ยงข้ามบริษัททุกครั้ง · จะดูได้เฉพาะใน `audit()` ซึ่งมีไว้ "ตรวจ" ไม่ใช่ "ใช้งาน"
2. ทุกคำขอผ่าน `get()` ซึ่งเช็ค id ปลายทางกับ allowlist ก่อนยิงออก
3. **ไม่ตั้ง `META_AD_ACCOUNTS` / `META_PAGE_IDS` = ปิดสนิท** (ไม่ใช่ "เปิดหมด")
   — เปิดโดยปริยายแล้ววันหนึ่งข้อมูลบริษัทอื่นจะไหลเข้าแดชบอร์ดนี้แบบไม่มีใครรู้
   แล้วตัวเลขเพี้ยนโดยหาต้นตอไม่เจอ (บทเรียนเดียวกับ EXTERNAL_API_KEY)
"""
from __future__ import annotations

import re

import requests
from django.conf import settings

TIMEOUT = 40


class MetaError(RuntimeError):
    """คุย Graph API ไม่ได้"""


class NotConfigured(MetaError):
    """ยังไม่ได้ตั้ง token หรือยังไม่ได้ระบุ asset ของบริษัท"""


class ForeignAsset(MetaError):
    """★ กำลังจะแตะของบริษัทอื่น — ตัดทิ้งก่อนยิงออกเน็ต"""


# ── ตัวช่วยอ่านค่าตั้ง ────────────────────────────────────────────
def token() -> str:
    t = (getattr(settings, "META_ACCESS_TOKEN", "") or "").strip()
    if not t:
        raise NotConfigured("ยังไม่ได้ตั้ง META_ACCESS_TOKEN")
    return t


def _base() -> str:
    v = getattr(settings, "META_API_VERSION", "v21.0") or "v21.0"
    return "https://graph.facebook.com/%s" % v


def accounts() -> set:
    """รหัสบัญชีโฆษณาของบริษัทนี้ (ไม่มี 'act_' นำหน้า)"""
    return {str(a).replace("act_", "").strip()
            for a in (getattr(settings, "META_AD_ACCOUNTS", None) or []) if str(a).strip()}


def pages() -> set:
    """รหัสเพจของบริษัทนี้"""
    return {str(p).strip() for p in (getattr(settings, "META_PAGE_IDS", None) or []) if str(p).strip()}


def is_configured() -> bool:
    """พร้อมใช้ไหม — ต้องมี token **และ** ระบุ asset อย่างน้อยหนึ่งอย่าง"""
    try:
        token()
    except NotConfigured:
        return False
    return bool(accounts() or pages())


# ── ทะเบียน id ลูกที่ "สืบมาจากของเรา" ──────────────────────────────
# post/video/ad/adset id เป็นเลขล้วนเหมือนกันหมด แยกจาก id ของบริษัทอื่นด้วยตาไม่ได้
# → เก็บ id ที่ **โผล่มาจากคำตอบของคำขอที่ผ่าน allowlist แล้ว** เอาไว้ แล้วอนุญาตเฉพาะพวกนั้น
#   (ปลอดภัยกว่าให้ผู้เรียกยืนยันเอง เพราะผู้เรียกในอนาคตจะยืนยันมั่ว ๆ แล้วรูรั่วกลับมา)
_known: set = set()

_ACT_RE = re.compile(r"^act_(\d+)$")
_NUM_RE = re.compile(r"^\d+$")
_COMPOUND_RE = re.compile(r"^(\d+)_(\d+)$")     # <page_id>_<post_id>


def _harvest(obj, depth: int = 0) -> None:
    """เก็บ id ทุกตัวจากคำตอบที่ผ่านด่านแล้ว — ใช้อนุญาตคำขอลูกรอบถัดไป"""
    if depth > 6:
        return
    if isinstance(obj, dict):
        v = obj.get("id")
        if isinstance(v, (str, int)):
            _known.add(str(v))
        for x in obj.values():
            _harvest(x, depth + 1)
    elif isinstance(obj, list):
        for x in obj[:500]:
            _harvest(x, depth + 1)


def _check(node: str) -> None:
    """ปลายทางนี้เป็นของบริษัทเราไหม — ไม่ใช่ = โยน ForeignAsset"""
    node = (node or "").strip()
    if not node:
        raise ForeignAsset("ไม่ได้ระบุปลายทาง")

    if node in ("me", "debug_token"):
        raise ForeignAsset(
            "ห้ามใช้ /%s ในโค้ดใช้งานจริง — มันคืน asset ของ *ทุก* บริษัทที่เจ้าของโปรไฟล์"
            " แตะได้ (รวมบริษัทอื่น) · ถ้าต้องการสำรวจให้ใช้ meta.audit()" % node)

    m = _ACT_RE.match(node)
    if m:
        if m.group(1) in accounts():
            return
        raise ForeignAsset(
            "บัญชีโฆษณา act_%s ไม่อยู่ใน META_AD_ACCOUNTS — เป็นของบริษัทอื่น" % m.group(1))

    if node in pages():
        return

    # ★ id ที่สืบมาจากคำตอบที่ผ่านด่านแล้ว — เช็ค **ก่อน** ดูรูปแบบ
    #   เพราะ id ลูกของ Meta มีหลายทรงเกินกว่าจะไล่เขียน regex ได้หมด:
    #   โพสต์ `<page>_<post>` · วิดีโอเลขล้วน · **บทสนทนา Messenger `t_123…`** ·
    #   คอมเมนต์ `<post>_<comment>` · adset/ad เลขล้วน
    #   (เจอจริงตอนใช้งาน: conversation id ขึ้นต้น `t_` โดนปฏิเสธทั้งที่เป็นของเพจเราเอง
    #    เพราะโค้ดเดิมเช็ค _known แค่ในกิ่ง "เลขล้วน" กับ "<a>_<b>")
    if node in _known:
        return

    m = _COMPOUND_RE.match(node)             # โพสต์: <page_id>_<post_id>
    if m:
        if m.group(1) in pages():
            return
        raise ForeignAsset("โพสต์ %s ไม่ได้อยู่ใต้เพจของบริษัทนี้" % node)

    if _NUM_RE.match(node):
        raise ForeignAsset(
            "id %s ไม่อยู่ใน META_PAGE_IDS และไม่ได้สืบมาจาก asset ของเรา"
            " — ถ้าเป็นเพจของบริษัทนี้จริง ให้เพิ่มใน META_PAGE_IDS" % node)

    raise ForeignAsset(
        "ปลายทาง %r ไม่รู้จัก และไม่ได้สืบมาจาก asset ของเรา — ปฏิเสธไว้ก่อน" % node[:40])


# ── ตัวยิงคำขอ ───────────────────────────────────────────────────
def get(path: str, _token: str = "", **params):
    """GET Graph API โดยเช็ค allowlist ก่อน

    `path` = "/act_123/insights" หรือ "/456/feed" · `_token` ใส่ page token ได้ถ้ามี
    """
    if not is_configured():
        raise NotConfigured(
            "ยังไม่ได้ระบุ asset ของบริษัทนี้ — ตั้ง META_AD_ACCOUNTS / META_PAGE_IDS ก่อน"
            " (ไม่ตั้ง = ปิดสนิท ตั้งใจให้เป็นแบบนี้ กันข้อมูลบริษัทอื่นปนเข้ามา)")
    p = "/" + (path or "").lstrip("/")
    _check(p.split("/")[1] if len(p.split("/")) > 1 else "")

    try:
        r = requests.get(_base() + p, params=dict(access_token=_token or token(), **params),
                         timeout=TIMEOUT)
        data = r.json()
    except requests.RequestException as e:
        raise MetaError("ต่อ Graph API ไม่ได้: %s" % e)
    except ValueError:
        raise MetaError("Graph API ตอบไม่ใช่ JSON (HTTP %s)" % r.status_code)

    if isinstance(data, dict) and data.get("error"):
        raise MetaError(str((data["error"] or {}).get("message"))[:200])
    _harvest(data)
    return data


def page_token(page_id: str) -> str:
    """token ของเพจ — งานระดับเพจ (คอมเมนต์/แชท) ต้องใช้ตัวนี้ ไม่ใช่ user token

    ดึงทีละเพจจาก `/<page_id>?fields=access_token` **ไม่ใช่** `/me/accounts`
    (ตัวหลังคืนเพจของทุกบริษัท)
    """
    pid = str(page_id).strip()
    if pid not in pages():
        raise ForeignAsset("เพจ %s ไม่อยู่ใน META_PAGE_IDS" % pid)
    t = (get("/" + pid, fields="access_token") or {}).get("access_token") or ""
    if not t:
        raise MetaError("ขอ page token ของเพจ %s ไม่ได้" % pid)
    return t


def ad_accounts(fields: str = "account_id,name,account_status,currency") -> list:
    """บัญชีโฆษณา **ของบริษัทนี้เท่านั้น** — วนจาก allowlist ไม่ได้ถาม /me"""
    out = []
    for aid in sorted(accounts()):
        try:
            d = get("/act_%s" % aid, fields=fields)
        except MetaError as e:
            d = {"account_id": aid, "error": str(e)}
        d.setdefault("account_id", aid)
        out.append(d)
    return out


def page_list(fields: str = "id,name,fan_count") -> list:
    """เพจ **ของบริษัทนี้เท่านั้น**"""
    out = []
    for pid in sorted(pages()):
        try:
            out.append(get("/" + pid, fields=fields))
        except MetaError as e:
            out.append({"id": pid, "error": str(e)})
    return out


# ── ตรวจสอบ (ที่เดียวที่มองข้ามบริษัทได้) ─────────────────────────
def audit() -> dict:
    """เทียบ "token เอื้อมถึงอะไร" กับ "allowlist ของบริษัทนี้"

    **ฟังก์ชันเดียวที่เรียก /me ได้** เพราะหน้าที่มันคือตรวจว่ามีของบริษัทอื่นหลุดเข้ามาไหม
    ผลลัพธ์ `foreign*` = ของที่ token แตะได้แต่ **ไม่ใช่ของบริษัทนี้** → ต้องเหลือเป็น
    "รู้ว่ามี แต่โค้ดแตะไม่ได้" เท่านั้น
    """
    t = token()
    b = _base()

    def me(edge, fields):
        try:
            r = requests.get("%s/me/%s" % (b, edge),
                             params={"access_token": t, "fields": fields, "limit": 100},
                             timeout=TIMEOUT).json()
        except Exception as e:
            return [], str(e)
        if r.get("error"):
            return [], str((r["error"] or {}).get("message"))[:160]
        return (r.get("data") or []), ""

    acc, acc_err = me("adaccounts", "account_id,name")
    pg, pg_err = me("accounts", "id,name")
    allow_a, allow_p = accounts(), pages()

    reach_a = {str(x.get("account_id")): (x.get("name") or "") for x in acc}
    reach_p = {str(x.get("id")): (x.get("name") or "") for x in pg}
    return {
        "configured": is_configured(),
        "allowAdAccounts": sorted(allow_a),
        "allowPages": sorted(allow_p),
        "reachAdAccounts": reach_a,
        "reachPages": reach_p,
        # ของบริษัทอื่นที่ token เอื้อมถึง — ต้อง "มองเห็นแต่แตะไม่ได้"
        "foreignAdAccounts": {k: v for k, v in reach_a.items() if k not in allow_a},
        "foreignPages": {k: v for k, v in reach_p.items() if k not in allow_p},
        # ตั้งไว้ใน allowlist แต่ token เอื้อมไม่ถึง (พิมพ์ผิด / ถูกถอดสิทธิ์)
        "missingAdAccounts": sorted(allow_a - set(reach_a)),
        "missingPages": sorted(allow_p - set(reach_p)),
        "errors": [e for e in (acc_err, pg_err) if e],
    }
