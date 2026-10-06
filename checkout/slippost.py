# -*- coding: utf-8 -*-
"""**ส่งใบจ่ายลีดเข้ากลุ่มจ่ายเบอร์จริง + แท็กเซลล์** (6 ต.ค.69 · เจ้าของสั่ง)

*"กลุ่มจ่ายเบอร์อยากให้มันต่อจริงๆ ส่งจริงๆ ได้ ทั้งสิทธิ์ในระบบเราและแท็กในไลน์กลุ่ม
  ถ้าเป็น LINE จะส่งให้ทั้ง LINE และแท็กในกลุ่ม · ถ้าเป็นช่องทางอื่นจะแท็กในกลุ่มก็พอ
  แล้วก็ให้สิทธิ์ในระบบของเราเพื่อเก็บข้อมูลเท่านั้น ถ้าไม่ใช่ LINE ของฝั่ง Connect ลูกค้า"*

ปุ่ม "จ่ายเบอร์" ได้อะไรบ้าง แยกตามช่องทางของลูกค้า:

  | ลูกค้า                                | สิทธิ์ในระบบเรา                                   | กลุ่มจ่ายเบอร์          |
  |---------------------------------------|---------------------------------------------------|-------------------------|
  | แชท LINE OA ใน Connect               | โอนแชทให้เซลล์ — **ตอบลูกค้าผ่าน Connect ได้**     | โพสต์ใบ + แท็ก @เซลล์   |
  | แชท Facebook ใน Connect              | โอนให้เซลล์ **เพื่อเก็บข้อมูลเท่านั้น** (ตอบไม่ได้) | โพสต์ใบ + แท็ก @เซลล์   |
  | ลีดภายนอกในห้องพัก (TikTok/FB/อื่นๆ) | จดว่าจ่ายให้ใคร (ExtLead)                         | โพสต์ใบ + แท็ก @เซลล์   |

กลุ่มปลายทาง (วัดจากใบจริง 30 วัน): เลขปกติ → **"ห้องจ่ายเบอร์ บ้านเก่า"** · เลขขึ้นต้น R → **"ห้องจ่ายเบอร์ REJECT"**
(ใบ R… อยู่ห้อง REJECT 967 จาก 968 ใบ) · ตั้งเองได้ที่ Connect → ตั้งค่า (`slip_group` / `slip_group_reject`)

กติกาที่ต้องรักษา:
  - **ส่งจากบอทตัวส่ง (OxletautoGiveLead) เท่านั้น** — เจ้าของกำหนดไว้ 20 ก.ย.69
  - **แท็กด้วยไอดีฝั่งบอทตัวส่ง + ถาม LINE ก่อนว่าอยู่ในกลุ่มจริงไหม** — แท็กพลาดคนเดียว LINE ปฏิเสธ
    ทั้งข้อความ (บทเรียนตารางเช็คชื่อ 20-21 ก.ย.69) · แท็กไม่ได้ = พิมพ์ "@ชื่อเล่น" แทน ใบยังถึงกลุ่ม
  - **ส่งไม่สำเร็จ ≠ ยกเลิกการจ่ายเบอร์** — เลข/เซลล์ในระบบยังอยู่ แล้วจดเหตุผลไว้ใน `post_info`
    ให้หน้าเว็บโชว์ปุ่ม "ส่งเข้ากลุ่มอีกครั้ง" (ย้อนธุรกรรมหลังยิงเน็ตไปแล้ว ทำให้สถานะไม่ตรงความจริงได้)
  - **ใบที่ส่งสำเร็จ เก็บลง `GroupChat` ด้วย** — LINE ไม่ส่งข้อความของบอทเองกลับมาทาง webhook
    ถ้าไม่เก็บ ตัวนับเลขรัน/ห้องพัก Lead/ตัวจับความต้องการลูกค้า จะไม่เห็นใบที่ระบบโพสต์เอง
  - **ไม่ลงชีตลีด** (เจ้าของสั่งไว้ 4 ต.ค.69 · ยังไม่ได้เปลี่ยน)
"""
from __future__ import annotations

import json
import re
import uuid

from django.utils import timezone

MAIN, REJECT = "main", "reject"
WHAT = "ใบจ่ายลีด (Connect)"          # ชื่อเรื่องใน dash_event_log — หน้าสถานะระบบเฝ้าให้เองถ้าล้มติดกัน
FB_DATA_ONLY = ("ลูกค้า Facebook — เซลล์ได้สิทธิ์ในระบบเพื่อเก็บข้อมูลเท่านั้น (ดูแชท/กรอกข้อมูลลีด) "
                "ตอบแชทจาก Connect ไม่ได้ · ติดต่อลูกค้าตามเบอร์/ID LINE ในใบจ่ายลีด")
_ROOM_HINT = "จ่ายเบอร์"
_REJECT_HINT = "reject"
_MAX_TEXT = 4800                         # LINE รับข้อความละไม่เกิน 5,000 ตัวอักษร


# ─────────────────────────────────────────────────────────────
#  กลุ่มปลายทาง
# ─────────────────────────────────────────────────────────────
def _kv_groups() -> dict:
    try:
        from dashboard.services import cache_store
        return (cache_store.get_kv("line_groups") or {}).get("data") or {}
    except Exception:
        return {}


def lead_rooms() -> list:
    """กลุ่มจ่ายเบอร์ที่ **บอทตัวส่งอยู่** → `[{id, name, reject, lastSeen}]` (ได้ยินล่าสุดก่อน)

    ซ่อน id ที่มีแต่บอทตัวรับได้ยิน — group id ออกต่อ provider เลือกไปก็ส่งไม่ได้
    (ต้นเหตุการ์ดตั้งเวลาส่งไม่ออกทุกใบ 15/09)
    """
    from dashboard.services.line_channels import group_visible_to_push
    lead_ids = set()
    try:
        from .models import LineGroup
        lead_ids = set(LineGroup.objects.filter(kind=LineGroup.LEAD).values_list("group_id", flat=True))
    except Exception:
        pass
    out = []
    for gid, g in _kv_groups().items():
        g = g or {}
        name = g.get("name") or ""
        if not (gid in lead_ids or _ROOM_HINT in name) or not group_visible_to_push(g):
            continue
        out.append({"id": gid, "name": name, "reject": _REJECT_HINT in name.lower(),
                    "lastSeen": g.get("lastSeen") or ""})
    out.sort(key=lambda r: r["lastSeen"], reverse=True)
    return out


def rooms(c=None) -> dict:
    """ห้องปลายทาง `{main: {id, name, auto}, reject: {…}}` — ตั้งเองในหน้าตั้งค่า Connect ชนะ
    · ไม่ได้ตั้ง = หาจากชื่อกลุ่ม (`auto=True`)"""
    if c is None:
        from .connect import cfg
        c = cfg()
    found = lead_rooms()
    names = {gid: (g or {}).get("name") or "" for gid, g in _kv_groups().items()}
    out = {}
    for key, want_reject, ck in ((MAIN, False, "slip_group"), (REJECT, True, "slip_group_reject")):
        gid = (c.get(ck) or "").strip()
        if gid:
            out[key] = {"id": gid, "name": names.get(gid, ""), "auto": False}
            continue
        hit = next((r for r in found if r["reject"] == want_reject), None)
        out[key] = {"id": hit["id"] if hit else "", "name": hit["name"] if hit else "", "auto": True}
    return out


def room_for(code: str, c=None) -> dict:
    """เลขขึ้นต้น R (เคสรีเจ็ค) → ห้อง REJECT · อื่นๆ → ห้องปกติ · ไม่มีห้อง REJECT = ห้องปกติ"""
    r = rooms(c)
    if (code or "").strip().upper().startswith("R") and r[REJECT]["id"]:
        return r[REJECT]
    return r[MAIN]


# ─────────────────────────────────────────────────────────────
#  แท็กเซลล์
# ─────────────────────────────────────────────────────────────
def mention_id(emp, group_id: str, token: str = "") -> tuple:
    """LINE id ของเซลล์ **ฝั่งบอทตัวส่ง** ที่ยืนยันแล้วว่าอยู่ในกลุ่มนี้ → `(uid, เหตุผลที่แท็กไม่ได้)`

    หาไม่ได้/ไม่อยู่ในกลุ่ม = ไม่แท็ก (คืน uid ว่าง) — ยอมพิมพ์ชื่อ ดีกว่าแท็กพลาดแล้วใบไม่ถึงกลุ่มเลย
    """
    if not emp:
        return "", "ไม่ได้เลือกเซลล์"
    try:
        from .checkin_report import _pick_id, outsiders, push_channel
        from .models import LineProfile
        ch = push_channel()
        if not ch:
            return "", "ไม่รู้ว่าบอทตัวส่งเป็นบัญชีไหน"
        profs = list(LineProfile.objects.filter(employee=emp).order_by("-last_seen"))
        uid = _pick_id(profs, ch)
        if not uid:
            return "", "ยังไม่มีไอดี LINE ของ %s ฝั่งบอทตัวส่ง (ต้องเคยพิมพ์ในกลุ่มที่บอทอยู่)" % emp.nickname
        if uid in outsiders(group_id, [uid], token):
            return "", "%s ไม่ได้อยู่ในกลุ่มนี้" % emp.nickname
        return uid, ""
    except Exception as e:
        return "", "หาไอดี LINE ไม่ได้: %s" % str(e)[:80]


# ─────────────────────────────────────────────────────────────
#  ตัวใบ
# ─────────────────────────────────────────────────────────────
_ROWS = [("Ac Lead No.   ", "code"), ("Ads  :  ", "ads"), ("ชื่อ Account : ", "account"),
         ("ชื่อลูกค้า : ", "name"), ("ID LINE : ", "line_id"), ("ชื่อไลน์ : ", "line_name"),
         ("เบอร์โทร : ", "phone"), ("ช่องทาง  : ", "channel"), ("รถ : ", "car"), ("ไลฟ์ : ", "live"),
         ("เพิ่มเติม  : ", "more")]


def _v(s) -> str:
    # ค่าหลายบรรทัด (เพิ่มเติม) ต่อเป็นบรรทัดเดียว — บรรทัดถัดไปที่มี ":" จะถูกอ่านเป็นช่องอื่นของใบ
    return re.sub(r"\s*\n\s*", " · ", str(s or "").strip())


def body(f: dict, notes=()) -> str:
    """ใบจ่ายลีด — หน้าตาเดียวกับที่แอดมินโพสต์ในห้องจ่ายเบอร์ (`leadgroup.parse_leadsheet` อ่านกลับได้)
    แท็กเซลล์ต่อท้ายตอนส่ง (`messages`) · `notes` = บรรทัดเสริมก่อน "ติดต่อได้เลยนะครับ" """
    lines = [(h + _v(f.get(k))).rstrip() for h, k in _ROWS]
    lines.append("")
    lines += [n for n in notes if n]
    lines.append("ติดต่อได้เลยนะครับ")
    return "\n".join(lines)[:_MAX_TEXT]


def messages(text: str, nick: str, uid: str, mention: bool) -> list:
    """ข้อความที่ส่ง — แท็กได้ = textV2 (กดชื่อแล้วเด้งหาคนนั้น) · แท็กไม่ได้ = พิมพ์ "@ชื่อเล่น" ท้ายใบ"""
    if mention and uid:
        # textV2 ใช้ {…} เป็นตัวแทนที่ — ข้อความลูกค้าที่มีวงเล็บปีกกา ต้องไม่ถูกตีความเป็นตัวแทนที่
        safe = text.replace("{", "(").replace("}", ")")
        return [{"type": "textV2", "text": safe + "\n{seller}",
                 "substitution": {"seller": {"type": "mention",
                                             "mentionee": {"type": "user", "userId": uid}}}}]
    return [{"type": "text", "text": text + "\n@" + (nick or "")}]


def explain(code: int, resp: str = "") -> str:
    """คำตอบของ LINE → ภาษาคน (แอดมินต้องรู้ว่าต้องทำอะไรต่อ ไม่ใช่เห็น error ดิบ)"""
    detail = ""
    try:
        detail = (json.loads(resp or "{}") or {}).get("message") or ""
    except Exception:
        detail = (resp or "")[:120]
    tail = (" (%s)" % detail[:120]) if detail else ""
    if code == 401:
        return "token ของบอทตัวส่งใช้ไม่ได้ (401)"
    if code == 429:
        return "LINE ไม่รับ — ส่งถี่เกิน หรือโควต้าข้อความของ LINE OA เดือนนี้หมด (429)" + tail
    if code in (400, 403, 404):
        return ("LINE ไม่รับ (%s) — บอทตัวส่งอาจไม่ได้อยู่ในกลุ่มนี้ หรือ group id เป็นของบอทเดิม" % code) + tail
    return ("LINE ตอบ %s" % code) + tail


def _sent_id(resp: str) -> str:
    try:
        return str(((json.loads(resp or "{}") or {}).get("sentMessages") or [{}])[0].get("id") or "")
    except Exception:
        return ""


def _store(room: dict, code: str, text: str, nick: str, info: dict, by: str, channel: str):
    """เก็บใบที่ส่งสำเร็จลงคลังแชทกลุ่ม — ให้เลขรัน/ห้องพัก Lead/ตัวจับความต้องการลูกค้าเห็นใบนี้ด้วย
    (LINE ไม่ส่งข้อความของบอทเองกลับมาทาง webhook) · เก็บไม่ได้ = ข้าม (ใบถึงกลุ่มแล้ว)"""
    try:
        from .models import GroupChat
        GroupChat.objects.create(
            chat_type=GroupChat.GROUP, group_id=room["id"], group_name=(room.get("name") or "")[:120],
            message_id=(info.get("mid") or ("connect-" + uuid.uuid4().hex))[:64],
            sender_id="", sender_name=(by or "ระบบ")[:80], msg_type="text",
            text=text + "\n@" + (nick or ""), extra={"source": "connect", "code": code, "tagged": info.get("tagged")},
            channel=(channel or "")[:24], direction=GroupChat.OUT, sent_by_name=(by or "")[:80],
            sent_at=timezone.now())
    except Exception:
        pass


def post(code: str, text: str, emp, by: str = "", c=None) -> dict:
    """ส่งใบเข้ากลุ่มจ่ายเบอร์ + แท็กเซลล์ → ผลการส่ง (ผู้เรียกเก็บลง `post_info` ของลีด)

    `{ok, at, by, group, groupName, seller, tagged, tagWhy, error, mid}` · ไม่โยน exception
    """
    from dashboard.services.line_channels import key_of_token, push_token
    from .checkin_report import _send_msgs

    room = room_for(code, c)
    nick = emp.nickname if emp else ""
    info = {"ok": False, "at": timezone.localtime().isoformat(timespec="seconds"), "by": (by or "")[:80],
            "group": room["id"], "groupName": room["name"], "seller": nick,
            "tagged": False, "tagWhy": "", "error": ""}
    if not room["id"]:
        info["error"] = "ยังไม่พบกลุ่มจ่ายเบอร์ที่บอทตัวส่งอยู่ — เลือกกลุ่มได้ที่ Connect → ตั้งค่า"
        return info
    token = push_token()
    if not token:
        info["error"] = "ยังไม่ได้ตั้ง LINE token ของบอทตัวส่ง"
        return info
    uid, why = mention_id(emp, room["id"], token)
    try:
        # แท็กโดนปฏิเสธ = สร้างใหม่แบบพิมพ์ชื่อแล้วส่งซ้ำ (ตัวเดียวกับตารางเช็คชื่อ) · ล้มเพราะอย่างอื่นไม่ส่งซ้ำ
        sc, resp, tagged = _send_msgs(room["id"], lambda m: messages(text, nick, uid, m), token, WHAT)
    except Exception as e:
        info["error"] = "ต่อ LINE ไม่ได้: %s" % str(e)[:120]
        return info
    if sc != 200:
        info["error"] = explain(sc, resp)
        info["tagWhy"] = why
        return info
    info["tagged"] = bool(tagged and uid)
    info["tagWhy"] = why or ("" if info["tagged"] else "LINE ไม่รับการแท็ก — ส่งแบบพิมพ์ชื่อแทน")
    info["ok"] = True
    info["mid"] = _sent_id(resp)
    _store(room, code, text, nick, info, by, key_of_token(token))
    return info


def summary(code: str, nick: str, info: dict) -> str:
    """ข้อความบอกแอดมินหลังกดจ่ายเบอร์"""
    room = info.get("groupName") or "กลุ่มจ่ายเบอร์"
    if info.get("ok"):
        tag = ("พร้อมแท็ก @%s" % nick) if info.get("tagged") else \
              ("(แท็กไม่ได้: %s — พิมพ์ @%s แทน)" % (info.get("tagWhy") or "-", nick))
        return "จ่ายเบอร์ %s ให้ %s แล้ว · ส่งเข้า \"%s\" %s" % (code, nick, room, tag)
    return ("จ่ายเบอร์ %s ให้ %s ในระบบแล้ว แต่ส่งเข้ากลุ่มไม่สำเร็จ: %s — กด \"ส่งเข้ากลุ่มอีกครั้ง\""
            % (code, nick, info.get("error") or "-"))


SENDING_SEC = 60        # กำลังส่งอยู่ (กดซ้ำรัวๆ) — ภายในเวลานี้ไม่รับคำสั่งส่งซ้ำ


def sending(info: dict) -> bool:
    """มีคำสั่งส่งค้างอยู่ไหม (กันกด "ส่งอีกครั้ง" ซ้ำแล้วใบเบิ้ลในกลุ่ม)"""
    from datetime import datetime
    at = (info or {}).get("sending") or ""
    try:
        return (timezone.now() - datetime.fromisoformat(at)).total_seconds() < SENDING_SEC
    except Exception:
        return False
