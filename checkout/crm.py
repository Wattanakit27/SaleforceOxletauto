# -*- coding: utf-8 -*-
"""**หน้ารวมแชท (Chat Inbox)** — ส่วนที่ต่อจาก Connect (11 ต.ค.69 · เจ้าของส่งสเปก 10 ข้อ
"ทำหน้าเว็บและ Mobile App ออกมาเลย ใช้ฐานข้อมูลจากที่เรามี")

ของเดิมใน Connect ใช้ต่อทั้งหมด (คิวรอรับ · รับ/โอน/ปล่อย · นาฬิกาตอบ · ข้อมูลลีด · จ่ายเบอร์ · ไม้ 2)
ไฟล์นี้เพิ่มเฉพาะที่ยังไม่มี:
  - **ขั้นของลีด** ลีดใหม่ → รอติดต่อ → ติดต่อแล้ว → นัดดูรถ → ยื่นไฟแนนซ์ → ปิดการขาย / ไม่สนใจ · คืนกองกลาง
    (คนละเรื่องกับ "สถานะลูกค้า" คอลัมน์ Z ของชีต — อันนั้นคือท่าทีลูกค้า อันนี้คืองานของเราไปถึงไหน)
  - **ความร้อน** (ร้อน/อุ่น/เย็น + คะแนน + เหตุผล) — คิดจากข้อมูลที่มีอยู่แล้ว ไม่มีช่องให้กรอกเพิ่ม
  - **นัดหมาย** (นัดติดตาม / นัดดูรถ) · **บันทึกการโทร + หลักฐาน** · **ใครเคยดูแล**
  - **Run Auto** (ห้องพัก Lead · แผนจ่ายเบอร์ตามคิวจ่ายวน — ไม่อยู่ในหน้าแชท) · **คืนกองกลาง** (เซลล์ปล่อยลูกค้าเอง)
  - **ดึงคืนเมื่อไม่ตอบ** (ปิดโดยปริยาย) · **แจ้งเตือนในระบบ** · **AI สรุปแชท** (เซลล์ตรวจก่อนบันทึก)
  - **วิเคราะห์**: ขั้นของลีดตามช่องทาง · เหตุผลที่ไม่ซื้อ · รายชื่อ "ไม่ต้องการ" ไว้ตัดออกจากโฆษณา

⚠️ ไม่ส่งอะไรหาลูกค้าจากไฟล์นี้ · เตือนนัดทาง LINE (แชทส่วนตัวเซลล์) ปิดโดยปริยาย
⚠️ ไม่ส่ง LINE user id ออกหน้าเว็บ — อ้างลูกค้าด้วย `ChatOwner.id` เหมือนเดิม
"""
import csv
import hashlib
import io
import json
import os
import re
import time
import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from . import connect as C
from .models import ChatCall, ChatFollowup, ChatLead, ChatOwner, ChatOwnerLog, Employee

# ─────────────────────────────────────────────────────────────
#  ขั้นของลีด
# ─────────────────────────────────────────────────────────────
STAGES = [("new", "ลีดใหม่"), ("waiting", "รอติดต่อ"), ("contacted", "ติดต่อแล้ว"), ("viewing", "นัดดูรถ"),
          ("finance", "ยื่นไฟแนนซ์"), ("won", "ปิดการขาย"), ("lost", "ไม่สนใจ/ลูกค้าผี"), ("pool", "คืนกองกลาง")]
STAGE_NAME = dict(STAGES)
# คนตั้งได้ — "ลีดใหม่" ระบบคิดเอง (ยังไม่มีเจ้าของ) · "คืนกองกลาง" มาจากปุ่มคืนกองกลางเท่านั้น
SET_STAGES = ("waiting", "contacted", "viewing", "finance", "won", "lost")
CLOSED = ("won", "lost")
_ORDER = {"new": 0, "pool": 0, "waiting": 1, "contacted": 2, "viewing": 3, "finance": 4, "won": 5}
LOST_REASONS = ["ดาวน์ไม่พอ", "เครดิตไม่ผ่าน/ติดบูโร", "ราคาสูงไป", "ไม่มีรถที่ต้องการ", "ซื้อที่อื่นแล้ว",
                "ไม่ตอบ/ลูกค้าผี", "ยังไม่พร้อมซื้อ", "อื่นๆ"]
HEAT_NAME = {"hot": "ร้อน", "warm": "อุ่น", "cold": "เย็น"}
SILENT_STEPS = (3, 5, 7)                  # ลูกค้าเงียบกี่วัน — ป้าย + แจ้งเตือน (สเปกข้อ 7)
NOREPLY_HOURS = 24                        # เราส่งล่าสุดแล้วลูกค้าเงียบเกินนี้ = "ลูกค้าไม่ตอบกลับ"

# คำในคอลัมน์ Z ที่ชีตถือว่า "เคสเสีย" — ชุดเดียวกับแดชบอร์ด (fetch_dashboard.CUSTOMER_STATUS_DEAD)
_DEAD_FALLBACK = ("ยังไม่ออก", "แบล็คลิส", "แบล็คลิสต์", "เครดิตไม่ผ่าน", "ไม่สนใจ", "คืนเคส")


def _dead_words():
    try:
        from dashboard.services.fetch_dashboard import CUSTOMER_STATUS_DEAD
        return tuple(CUSTOMER_STATUS_DEAD)
    except Exception:
        return _DEAD_FALLBACK


def _iso(dt):
    return C._iso(dt)


def stage_of(o, ld=None) -> str:
    """ขั้นของลีดตอนนี้ — คนตั้งไว้ใช้ค่าที่ตั้ง · ไม่งั้นระบบคิดจากความเป็นเจ้าของ + เราตอบไปหรือยัง"""
    st = (getattr(ld, "stage", "") or "") if ld else ""
    if st:
        return st
    if not o.owner_id:
        return "new"
    if o.first_reply_at or (o.last_out_at and (not o.claimed_at or o.last_out_at >= o.claimed_at)):
        return "contacted"
    return "waiting"


def _log(o, action, emp=None, by="", note=""):
    C._log(o, action, emp=emp, by=by, note=note)


def set_stage(o, stage: str, by: str = "", emp=None, reason: str = "") -> tuple:
    """เปลี่ยนขั้นของลีด → (ok, ข้อความ) · "" = ให้ระบบคิดเอง · ไม่สนใจ ต้องบอกเหตุผล (ใช้วิเคราะห์ข้อ 8)"""
    stage = (stage or "").strip()
    if stage and stage not in SET_STAGES:
        return False, "ขั้นนี้ตั้งเองไม่ได้ (ลีดใหม่ = ระบบคิดเอง · คืนกองกลาง = ปุ่มคืนกองกลาง)"
    reason = (reason or "").strip()[:40]
    if stage == "lost" and not reason:
        return False, "เลือกเหตุผลที่ไม่ซื้อก่อน — ใช้วิเคราะห์ว่าเสียลูกค้าเพราะอะไร"
    if reason and stage == "lost" and reason not in LOST_REASONS:
        return False, "เหตุผลนี้ไม่อยู่ในรายการ"
    ld = C.lead_of(o)
    before = stage_of(o, ld)
    ld.stage = stage
    ld.lost_reason = reason if stage == "lost" else ""
    ld.stage_at = timezone.now()
    ld.stage_by = (by or "")[:80]
    ld.save(update_fields=["stage", "lost_reason", "stage_at", "stage_by", "updated_at"])
    now_st = stage_of(o, ld)
    _log(o, ChatOwnerLog.STAGE, emp=emp, by=by,
         note=("%s → %s%s" % (STAGE_NAME.get(before, before), STAGE_NAME.get(now_st, now_st),
                              (" · " + reason) if reason else ""))[:200])
    return True, "เปลี่ยนเป็น \"%s\" แล้ว" % STAGE_NAME.get(now_st, now_st)


def bump(o, to: str, by: str = "", emp=None, why: str = "") -> bool:
    """เลื่อนขั้นไปข้างหน้าให้เอง (บันทึกโทร → ติดต่อแล้ว · นัดดูรถ → นัดดูรถ) — ไม่ถอยหลัง ไม่แตะเคสที่ปิดแล้ว"""
    ld = C.lead_of(o)
    cur = stage_of(o, ld)
    if cur in CLOSED or _ORDER.get(cur, 0) >= _ORDER.get(to, 0):
        return False
    ld.stage, ld.stage_at, ld.stage_by = to, timezone.now(), (by or "")[:80]
    ld.save(update_fields=["stage", "stage_at", "stage_by", "updated_at"])
    _log(o, ChatOwnerLog.STAGE, emp=emp, by=by,
         note=("%s → %s (อัตโนมัติ%s)" % (STAGE_NAME.get(cur, cur), STAGE_NAME[to],
                                          (" · " + why) if why else ""))[:200])
    return True


def on_release(o) -> None:
    """ลูกค้าถูกคืนกองกลาง/คืนคิว → ขั้น "คืนกองกลาง" (เว้นเคสที่ปิดแล้ว)"""
    try:
        ld = C.lead_of(o)
        if ld.stage not in CLOSED:
            ld.stage, ld.stage_at = "pool", timezone.now()
            ld.save(update_fields=["stage", "stage_at", "updated_at"])
    except Exception:
        pass


def on_owner(o) -> None:
    """มีเจ้าของใหม่ (รับ/โอน/จ่ายเบอร์) → ถ้าค้างที่ "คืนกองกลาง" ให้ระบบคิดขั้นใหม่"""
    try:
        ld = C.lead_of(o, create=False)
        if ld and ld.stage == "pool":
            ld.stage = ""
            ld.save(update_fields=["stage", "updated_at"])
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
#  ความร้อน — คิดจากข้อมูลที่มีอยู่แล้ว (type · สถานะลูกค้า Z · ขั้น · ลูกค้าคุยล่าสุดเมื่อไหร่ · ให้เบอร์ไหม)
# ─────────────────────────────────────────────────────────────
def _type_pts(t: str) -> tuple:
    t = (t or "").strip().lower()
    if not t:
        return 12, ""
    if "very hot" in t:
        return 40, "Very Hot"
    if "hot rb" in t or "hot rj" in t:
        return 14, t.title()
    if "merhot" in t:
        return 26, "MerHot"
    if "hot" in t:
        return 34, "Hot"
    if t in ("rj",) or t.endswith(" rj"):
        return 6, "RJ"
    return 18, t.upper() if len(t) <= 4 else t.title()


def silent_days(o, now=None):
    """ลูกค้าไม่ได้ทักมากี่วัน (นับจากข้อความล่าสุดของลูกค้า) — None = ยังไม่เคยทัก"""
    if not o.last_in_at:
        return None
    now = now or timezone.now()
    return max(0, int((now - o.last_in_at).total_seconds() // 86400))


def heat_of(o, ld=None, now=None) -> dict:
    """{key: hot/warm/cold/'' , score 0–100, why: [...]} · เคสที่ปิดแล้ว = ไม่มีความร้อน"""
    now = now or timezone.now()
    st = stage_of(o, ld)
    if st in CLOSED:
        return {"key": "", "score": 0, "why": [STAGE_NAME[st]]}
    why = []
    pts, lbl = _type_pts(getattr(ld, "lead_type", "") if ld else "")
    score = pts
    if lbl:
        why.append("type " + lbl)
    z = (getattr(ld, "customer_status", "") or "") if ld else ""
    if z and any(w in z for w in _dead_words()):
        return {"key": "cold", "score": 5, "why": ["สถานะลูกค้า: " + z]}
    if z:
        if "สนใจมาก" in z:
            score += 25
        elif "นัด" in z or "มาดู" in z:
            score += 20
        elif "ลังเล" in z:
            score += 10
        elif z.startswith("รอ"):
            score += 8
        elif "ไม่รับสาย" in z or "ไม่ตอบ" in z:
            score -= 10
        why.append(z)
    score += {"viewing": 20, "finance": 25, "contacted": 5}.get(st, 0)
    if st in ("viewing", "finance"):
        why.append(STAGE_NAME[st])
    sd = silent_days(o, now)
    if sd is not None:
        if sd <= 1:
            score += 20
            why.append("คุยล่าสุดไม่เกิน 1 วัน")
        elif sd <= 3:
            score += 10
        elif sd > 14:
            score -= 25
            why.append("เงียบ %d วัน" % sd)
        elif sd > 7:
            score -= 15
            why.append("เงียบ %d วัน" % sd)
    if ld and (ld.phone or ld.line_id):
        score += 8
    if o.awaiting_since:
        score += 5
    score = max(0, min(100, score))
    key = "hot" if score >= 60 else "warm" if score >= 35 else "cold"
    return {"key": key, "score": score, "why": why[:3]}


# ─────────────────────────────────────────────────────────────
#  นัดหมาย (นัดติดตาม / นัดดูรถ)
# ─────────────────────────────────────────────────────────────
def parse_due(s):
    """"2026-10-12T14:30" (เวลาไทย) หรือ ISO มีโซน → datetime มีโซน · ผิดรูปแบบ = None"""
    s = (s or "").strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def add_followup(o, kind: str, due, note: str = "", by: str = "", emp=None) -> tuple:
    """→ (ok, ข้อความ, ChatFollowup|None) · นัดดูรถ = ขั้นเลื่อนเป็น "นัดดูรถ" เอง"""
    if kind not in (ChatFollowup.FOLLOW, ChatFollowup.VIEWING):
        return False, "ชนิดนัดไม่ถูกต้อง", None
    dt = due if isinstance(due, datetime) else parse_due(due)
    if not dt:
        return False, "ใส่วันเวลานัดให้ครบ (เช่น 12/10 14:00)", None
    now = timezone.now()
    if dt < now - timedelta(days=1):
        return False, "วันนัดเป็นวันที่ผ่านไปแล้ว", None
    if dt > now + timedelta(days=180):
        return False, "นัดล่วงหน้าได้ไม่เกิน 6 เดือน", None
    who = o.owner if o.owner_id else emp
    f = ChatFollowup.objects.create(chat=o, kind=kind, due_at=dt, note=(note or "").strip()[:300],
                                    employee=who, emp_name=(who.nickname if who else ""), by_name=(by or "")[:80])
    lt = timezone.localtime(dt)
    _log(o, ChatOwnerLog.APPT, emp=who, by=by,
         note=("%s %d/%d %s%s" % (f.get_kind_display(), lt.day, lt.month, lt.strftime("%H:%M"),
                                  (" · " + f.note) if f.note else ""))[:200])
    if kind == ChatFollowup.VIEWING:
        bump(o, "viewing", by=by, emp=emp, why="นัดดูรถ")
    return True, "นัดแล้ว — %s %d/%d %s น." % (f.get_kind_display(), lt.day, lt.month, lt.strftime("%H:%M")), f


def done_followup(o, fid, by: str = "", result: str = "", cancel: bool = False) -> tuple:
    f = ChatFollowup.objects.filter(pk=fid, chat=o).first()
    if not f:
        return False, "ไม่พบนัดนี้"
    if f.done_at:
        return True, "นัดนี้ปิดไปแล้ว"
    f.done_at, f.done_by = timezone.now(), (by or "")[:80]
    f.result = ("ยกเลิกนัด" + ((" · " + result.strip()) if result.strip() else "")) if cancel else (result or "").strip()
    f.result = f.result[:300]
    f.save(update_fields=["done_at", "done_by", "result"])
    _log(o, ChatOwnerLog.APPT, by=by, note=("%s%s · %s" % ("ยกเลิก" if cancel else "เสร็จ", f.get_kind_display(),
                                                          f.result or "-"))[:200])
    return True, "ยกเลิกนัดแล้ว" if cancel else "บันทึกว่าทำแล้ว"


def followups_json(o, limit: int = 12) -> list:
    now = timezone.now()
    rows = list(o.followups.filter(done_at__isnull=True).order_by("due_at")[:limit])
    rows += list(o.followups.filter(done_at__isnull=False).order_by("-done_at")[:4])
    return [{"id": f.id, "kind": f.kind, "kindLabel": f.get_kind_display(), "due": _iso(f.due_at),
             "note": f.note, "who": f.emp_name, "by": f.by_name, "done": _iso(f.done_at), "doneBy": f.done_by,
             "result": f.result, "late": bool(not f.done_at and f.due_at < now)} for f in rows]


def next_appt_map(ids) -> dict:
    """{chat_id: (kind, due_at)} — นัดที่ยังไม่ทำ ใกล้ที่สุด (โชว์ในรายชื่อ · query เดียวทั้งหน้า)"""
    out = {}
    if not ids:
        return out
    for f in ChatFollowup.objects.filter(chat_id__in=list(ids), done_at__isnull=True).order_by("due_at"):
        out.setdefault(f.chat_id, (f.kind, f.due_at))
    return out


# ─────────────────────────────────────────────────────────────
#  บันทึกการโทร + หลักฐาน (รูปหน้าจอการโทร · เก็บดิสก์ VPS ชื่อไฟล์สุ่ม)
# ─────────────────────────────────────────────────────────────
MEDIA_DIR = "connect"
PROOF_EXT = {"jpg", "jpeg", "png", "webp", "heic", "heif", "gif"}
PROOF_MAX_MB = 10
PROOF_MAX_FILES = 6


def _store():
    from django.core.files.storage import FileSystemStorage
    return FileSystemStorage(location=settings.MEDIA_ROOT)


def media_url(path: str) -> str:
    return getattr(settings, "MEDIA_URL", "/media/").rstrip("/") + "/" + path.lstrip("/")


def save_proof(o, f) -> tuple:
    """อัปรูปหลักฐานการโทร → (ok, {id, url} | ข้อความ) · เฉพาะรูป ≤ 10 MB"""
    if not f:
        return False, "ไม่มีไฟล์"
    ext = (os.path.splitext(f.name or "")[1] or "").lower().lstrip(".")
    if ext not in PROOF_EXT or not (f.content_type or "image/").startswith("image"):
        return False, "แนบได้เฉพาะรูปภาพ (jpg/png/webp/heic)"
    if f.size and f.size > PROOF_MAX_MB * 1024 * 1024:
        return False, "รูปใหญ่เกิน %d MB" % PROOF_MAX_MB
    name = "%s/%d/%s.%s" % (MEDIA_DIR, o.id, uuid.uuid4().hex, ext)
    try:
        saved = _store().save(name, f)
    except Exception as e:
        return False, "บันทึกรูปไม่สำเร็จ: %s" % str(e)[:120]
    return True, {"id": saved, "url": media_url(saved)}


def _clean_media(o, media) -> list:
    """รับเฉพาะไฟล์ที่อัปให้ลูกค้าคนนี้จริง (`connect/<id>/…`) — กันอ้างไฟล์อื่นบนเซิร์ฟเวอร์"""
    out, pre = [], "%s/%d/" % (MEDIA_DIR, o.id)
    st = _store()
    for m in (media or [])[:PROOF_MAX_FILES]:
        mid = str((m or {}).get("id") if isinstance(m, dict) else m or "").strip()
        if mid.startswith(pre) and ".." not in mid and st.exists(mid):
            out.append({"id": mid})
    return out


def add_call(o, result: str, note: str = "", media=None, by: str = "", emp=None) -> tuple:
    keys = dict(ChatCall.RESULT_CHOICES)
    if result not in keys:
        return False, "เลือกผลการโทรก่อน", None
    note = (note or "").strip()[:500]
    md = _clean_media(o, media)
    c = ChatCall.objects.create(chat=o, employee=emp, emp_name=(emp.nickname if emp else (by or ""))[:80],
                                result=result, note=note, media=md)
    _log(o, ChatOwnerLog.CALL, emp=emp, by=by,
         note=("%s%s%s" % (keys[result], (" · " + note) if note else "",
                           (" · หลักฐาน %d รูป" % len(md)) if md else ""))[:200])
    if result == ChatCall.OK:
        bump(o, "contacted", by=by, emp=emp, why="บันทึกการโทร")
    if md:                                       # แนบหลักฐานแล้ว = "แจ้งหลักฐานการโทร: ส่งแล้ว" (ถ้าคนยังไม่ได้ตั้งเอง)
        try:
            ld = C.lead_of(o)
            auto = dict(ld.auto or {})
            if auto.get("call_proof") != C.HUMAN and not ld.call_proof:
                ld.call_proof = "ส่งแล้ว"
                auto["call_proof"] = "บันทึกการโทร"
                ld.auto = auto
                ld.save(update_fields=["call_proof", "auto", "updated_at"])
        except Exception:
            pass
    return True, "บันทึกการโทรแล้ว", c


def calls_json(o, limit: int = 20) -> list:
    return [{"id": c.id, "at": _iso(c.at), "result": c.result, "resultLabel": c.get_result_display(),
             "note": c.note, "by": c.emp_name, "media": [{"url": media_url(m["id"])} for m in (c.media or [])
                                                         if isinstance(m, dict) and m.get("id")]}
            for c in o.calls.all()[:limit]]


def cleanup_files(now=None) -> int:
    """โฟลเดอร์หลักฐานของลูกค้าที่ถูกลบไปแล้ว (เงียบเกิน 60 วัน · PDPA) → ลบทิ้ง · วันละครั้ง"""
    import shutil
    root = os.path.join(str(settings.MEDIA_ROOT), MEDIA_DIR)
    if not os.path.isdir(root):
        return 0
    alive = set(ChatOwner.objects.values_list("id", flat=True))
    n = 0
    for name in os.listdir(root):
        if name.isdigit() and int(name) not in alive:
            try:
                shutil.rmtree(os.path.join(root, name))
                n += 1
            except Exception:
                pass
    return n


# ─────────────────────────────────────────────────────────────
#  ใครเคยดูแล — จากประวัติ (ชื่อเก็บเป็นข้อความ → เซลล์ลาออกแล้วก็ยังเห็น)
# ─────────────────────────────────────────────────────────────
def past_owners(o) -> list:
    acts = (ChatOwnerLog.CLAIM, ChatOwnerLog.ASSIGN, ChatOwnerLog.RELEASE)
    periods, cur = [], None
    for l in o.logs.filter(action__in=acts).order_by("at", "id"):
        if l.action == ChatOwnerLog.RELEASE:
            if cur:
                cur["to"], cur["end"] = _iso(l.at), l.note or "คืนคิว"
                periods.append(cur)
                cur = None
            continue
        if cur:
            cur["to"], cur["end"] = _iso(l.at), "โอนต่อ"
            periods.append(cur)
        cur = {"name": l.emp_name or "-", "from": _iso(l.at), "to": "", "end": "",
               "how": l.get_action_display() + ((" · " + l.note) if l.note else ""), "by": l.by_name}
    if cur:
        periods.append(cur)
    periods.reverse()
    return periods[:12]


# ─────────────────────────────────────────────────────────────
#  สถานะไฟแนนซ์ — จากชีตยอดขาย (เคสจองที่เลขลีดตรงกัน) · จำผล 5 นาที
# ─────────────────────────────────────────────────────────────
_BK = {"at": 0.0, "map": {}}
BK_TTL = 300


def _dash_cached() -> dict:
    """ผลแดชบอร์ดที่ cron อุ่นไว้แล้วเท่านั้น — **ห้ามคำนวณสด** (เปิดแชททุก 6 วิ · คำนวณสดใช้ ~8 วิ)
    ไม่มีของอุ่นไว้ = {} (แผงลูกค้าแค่ไม่มีสถานะไฟแนนซ์ ไม่ใช่เปิดแชทช้า)"""
    try:
        from dashboard.services import fetch_dashboard as FD
        if (FD._dash_cache or {}).get("data") is not None:
            return FD._dash_cache["data"]
        from dashboard.services.cache_store import available, get_dashboard_cache
        if available():
            c = get_dashboard_cache()
            if c and c.get("data"):
                return c["data"]
    except Exception:
        pass
    return {}


def _booking_map() -> dict:
    if time.time() - _BK["at"] < BK_TTL:
        return _BK["map"]
    m = {}
    try:
        for b in (_dash_cached() or {}).get("bookingCases") or []:
            code = (b.get("leadCode") or "").strip().upper()
            if code:
                m[code] = {"status": b.get("status") or "", "car": b.get("car") or "", "date": b.get("date") or "",
                           "signDate": b.get("signDate") or "", "resultDate": b.get("resultDate") or "",
                           "releaseDate": b.get("releaseDate") or "", "price": b.get("price") or 0,
                           "seller": b.get("seller") or ""}
    except Exception:
        m = _BK["map"]
    _BK.update(at=time.time(), map=m)
    return m


def booking_of(code: str):
    code = (code or "").strip().upper()
    if not code:
        return None
    from .console_data import lineage
    m = _booking_map()
    return m.get(code) or m.get(lineage(code))


# ─────────────────────────────────────────────────────────────
#  รถใหม่ตรงกับลูกค้าเก่า — ผลจับคู่ที่ leadflow.refresh_needs คำนวณไว้ทุก 30 นาที (KV)
# ─────────────────────────────────────────────────────────────
_MT = {"at": 0.0, "map": {}}


def match_map() -> dict:
    """{เลขลีด: [รถ…]} ของทุกเซลล์ · จำผล 60 วิ"""
    if time.time() - _MT["at"] < 60:
        return _MT["map"]
    m = {}
    try:
        from . import leadflow as LF
        for rows in ((LF._kv(LF.KV_NEEDS) or {}).get("bySeller") or {}).values():
            for r in rows or []:
                code = (r.get("code") or "").strip().upper()
                if code and r.get("cars"):
                    m[code] = r["cars"]
    except Exception:
        m = {}
    _MT.update(at=time.time(), map=m)
    return m


# ─────────────────────────────────────────────────────────────
#  ช่องเพิ่มในแถวรายชื่อ
# ─────────────────────────────────────────────────────────────
def row_extra(o, ld, now, appt=None, matches=None) -> dict:
    st = stage_of(o, ld)
    ht = heat_of(o, ld, now)
    sd = silent_days(o, now)
    silent = 0
    if o.owner_id and st not in CLOSED and sd is not None:
        silent = max([n for n in SILENT_STEPS if sd >= n] or [0])
    if appt is None:                         # ไม่ได้ส่งแผนที่นัดมา (เปิดทีละแถว) → ถามเอง
        f = o.followups.filter(done_at__isnull=True).order_by("due_at").first() if o.pk else None
        appt = (f.kind, f.due_at) if f else None
    elif appt is False:                      # ส่งแผนที่มาแล้ว แถวนี้ไม่มีนัด
        appt = None
    matches = match_map() if matches is None else matches
    code = ((ld.code if ld else "") or "").strip().upper()
    return {
        "stage": st, "stageLabel": STAGE_NAME.get(st, st),
        "heat": ht["key"], "heatScore": ht["score"], "heatWhy": ht["why"],
        "silentDays": sd if sd is not None else -1, "silent": silent,
        "noReply": bool(o.last_dir == "out" and o.last_out_at
                        and (now - o.last_out_at) >= timedelta(hours=NOREPLY_HOURS)),
        "appt": ({"kind": appt[0], "due": _iso(appt[1]), "late": appt[1] < now} if appt else None),
        "carMatch": len(matches.get(code) or []) if code else 0,
        "lostReason": (ld.lost_reason if ld else "") or "",
    }


# ─────────────────────────────────────────────────────────────
#  ตัวกรอง (สเปกข้อ 9)
# ─────────────────────────────────────────────────────────────
FILTER_KEYS = ("stage", "heat", "awaiting", "noreply", "silent", "follow", "dfrom", "dto", "car", "pmin", "pmax",
               "carmatch", "reason")


def clean_filters(get) -> dict:
    f = {}
    for k in FILTER_KEYS:
        v = (get.get(k) or "").strip() if hasattr(get, "get") else ""
        if v:
            f[k] = v[:60]
    return f


def _int(v, lo=0, hi=10 ** 9):
    try:
        return max(lo, min(hi, int(float(str(v).replace(",", "")))))
    except Exception:
        return None


def _local_day(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def needs_python(f: dict) -> bool:
    return bool(f.get("stage") or f.get("heat") or f.get("carmatch") or f.get("silent"))


def db_filter(qs, f: dict, now=None):
    now = now or timezone.now()
    tz = timezone.get_current_timezone()
    if f.get("awaiting"):
        qs = qs.filter(awaiting_since__isnull=False)
    if f.get("noreply"):
        qs = qs.filter(last_dir="out", last_out_at__lte=now - timedelta(hours=NOREPLY_HOURS))
    n = _int(f.get("silent"), 1, 365) if f.get("silent") else None
    if n:
        qs = qs.filter(owner__isnull=False, last_in_at__lte=now - timedelta(days=n))
    if f.get("follow"):
        end = timezone.make_aware(datetime.combine(timezone.localdate(), datetime.max.time()), tz)
        ids = ChatFollowup.objects.filter(done_at__isnull=True, due_at__lte=end).values("chat_id")
        qs = qs.filter(pk__in=ids)
    d1, d2 = _local_day(f.get("dfrom", "")), _local_day(f.get("dto", ""))
    if d1:
        qs = qs.filter(last_at__gte=timezone.make_aware(datetime.combine(d1, datetime.min.time()), tz))
    if d2:
        qs = qs.filter(last_at__lt=timezone.make_aware(datetime.combine(d2 + timedelta(days=1), datetime.min.time()), tz))
    car = (f.get("car") or "").strip()
    if car:
        qs = qs.filter(Q(lead__car_model__icontains=car) | Q(lead__car_text__icontains=car))
    pmin, pmax = _int(f.get("pmin")) if f.get("pmin") else None, _int(f.get("pmax")) if f.get("pmax") else None
    if pmin or pmax:
        # ช่วงราคา = งบที่ลูกค้าบอก (ระบบจับความต้องการ · ลูกค้า LINE) — ไม่มีงบ = ไม่ผ่านตัวกรองนี้
        #   ใช้ subquery ไม่ใช้ join+DISTINCT (Postgres เรื่องมากกับ DISTINCT + ORDER BY · ลูกค้าหลายความต้องการ = แถวซ้ำ)
        from .models import CustomerNeed
        nq = CustomerNeed.objects.filter(profile__isnull=False, budget_max__isnull=False)
        if pmin:
            nq = nq.filter(budget_max__gte=pmin)
        if pmax:
            nq = nq.filter(budget_max__lte=pmax)
        qs = qs.filter(profile_id__in=nq.values("profile_id"))
    if f.get("reason"):
        qs = qs.filter(lead__lost_reason=f["reason"])
    return qs


def py_filter(objs, f: dict, now=None) -> list:
    now = now or timezone.now()
    st, ht = f.get("stage"), f.get("heat")
    mm = match_map() if f.get("carmatch") else None
    out = []
    for o in objs:
        ld = C.lead_of(o, create=False)
        s = stage_of(o, ld)
        if st and s != st:
            continue
        if f.get("silent") and s in CLOSED:
            continue
        if ht and heat_of(o, ld, now)["key"] != ht:
            continue
        if mm is not None:
            code = ((ld.code if ld else "") or "").strip().upper()
            if not code or not mm.get(code):
                continue
        out.append(o)
    return out


# ─────────────────────────────────────────────────────────────
#  Run Auto (แอดมิน · ★ 11 ต.ค.69 ย้ายไปอยู่ "ห้องพัก Lead") — จ่ายเบอร์ลีดที่รอ ตามคิวจ่ายวน
#    เจ้าของสั่ง: "อันนี้มันหน้าแชท ให้แอดมินตอบแชทได้เท่านั้น ไม่มีการ run auto ใดๆ ทั้งสิ้นในหน้า chat"
#    → ไม่มี Run Auto ในกล่องแชทรวมแล้ว · ในห้องพัก Lead = "กดชื่อเซลล์คิวถัดไปให้ทุกใบ" (ตัวเดียวกับปุ่มกรอบชมพู)
#    ฟังก์ชันนี้ **แค่วางแผน ไม่ทำอะไรเลย** — หน้าเว็บโชว์ให้แอดมินดู/ติ๊กออกก่อน แล้วยิงจ่ายทีละใบผ่าน
#    endpoint เดิม (assign_lead / park_assign) ซึ่งมีด่านกันเลขซ้ำ/มีเลขแล้ว/ส่งเข้ากลุ่มครบอยู่แล้ว
# ─────────────────────────────────────────────────────────────
AUTO_LIMIT = 30          # ต่อรอบ — ใบละ 1 ข้อความเข้ากลุ่มจ่ายเบอร์ · กดซ้ำได้ถ้ายังเหลือ


def _src_key(kind, o=None, it=None) -> str:
    if kind == "chat":
        return "fb" if C.is_fb(o) else "line"
    s = (it or {}).get("source") or "other"
    return "fb" if s == "facebook" else s


def room_plan(src: str = "", limit: int = AUTO_LIMIT) -> dict:
    """ลีดใน "ห้องพัก Lead" ที่รอจ่ายเบอร์ → ใครจะได้ (เรียงรอนานสุดก่อน · สูงสุด `limit` ใบ)

    · แชทที่มีเซลล์ดูแลอยู่แล้ว = ให้คนเดิม (ไม่ดึงลูกค้าออกจากคนที่คุยอยู่)
    · เบอร์เคยเป็นลีดของใคร (สมุดเบอร์) = ให้เจ้าของเดิม · เจ้าของเดิมไม่อยู่แล้ว = ข้าม ให้แอดมินเลือกเอง
    · ที่เหลือ = คิวจ่ายวน (คนได้ใบน้อยสุดวันนี้ก่อน · ข้ามคนหยุด/ยังไม่เช็คชื่อ/เต็มเพดาน — กติกาเดียวกับหน้าห้องพัก)
    · ข้าม: ลูกค้าจำลอง · บัญชีพนักงาน
    """
    from . import leadflow as LF
    from . import leadpark
    c = LF.cfg()
    cand = LF.rr_candidates(c)
    load = {x["id"]: x["today"] for x in cand}
    cap = c.get("cap_day") or 0
    src = (src or "").strip()

    pool = []
    for o in C.to_code(ChatOwner.objects.select_related("profile", "fb_profile", "owner", "lead")):
        k = _src_key("chat", o)
        if src and k != src:
            continue
        pool.append(("chat", o, None, o.awaiting_since or o.last_in_at or o.last_at, k))
    try:
        waiting = leadpark.board(cache_sec=0).get("waiting") or []
    except Exception:
        waiting = []
    for it in waiting:
        if it.get("code"):
            continue
        k = _src_key("park", it=it)
        if src and k != src:
            continue
        at = parse_datetime(it.get("at") or "") if it.get("at") else None
        pool.append(("park", None, it, at, k))
    epoch = timezone.make_aware(datetime(2000, 1, 1))
    pool.sort(key=lambda x: x[3] or epoch)
    total = len(pool)

    plan, skipped = [], []
    for kind, o, it, at, k in pool[:max(1, int(limit or AUTO_LIMIT))]:
        if kind == "chat":
            name = C.row_json(o)["name"]
            ref = {"kind": "chat", "id": o.id, "name": name, "src": k}
            if C.is_sim_row(o):
                skipped.append(dict(ref, why="ลูกค้าจำลอง"))
                continue
            if getattr(C.cust(o), "is_employee", False):
                skipped.append(dict(ref, why="บัญชีพนักงาน — ให้แอดมินดูเอง"))
                continue
            ld = C.lead_of(o, create=False)
            phone, code = (ld.phone if ld else ""), (ld.code if ld else "")
            owner = o.owner if (o.owner_id and o.owner.active and not C.is_test_seller(o.owner)) else None
        else:
            name = it.get("account") or it.get("name") or it.get("lineId") or it.get("phone") or "(ไม่มีชื่อ)"
            ref = {"kind": "park", "id": it["id"], "name": name, "src": k,
                   "base": it.get("base") or "", "admin": bool(it.get("admin")), "reject": bool(it.get("reject"))}
            phone, code, owner = it.get("phone") or "", "", None
        target, why, dup = None, "", None
        if owner:
            target, why = owner, "ดูแลแชทนี้อยู่"
        elif phone:
            dup = LF.dup_info(phone, exclude_code=code)
        if not target and dup:
            e = Employee.objects.filter(pk=dup["sellerId"], active=True).first() if dup.get("sellerId") else None
            if not e or C.is_test_seller(e):
                skipped.append(dict(ref, why="เบอร์ซ้ำ — เคยเป็นลีด %s ของ %s (ไม่อยู่ในคิวแล้ว) ให้แอดมินเลือกเอง"
                                    % (dup.get("code") or "-", dup.get("seller") or "?")))
                continue
            target, why = e, "เบอร์เคยเป็นลีด %s ของ %s" % (dup.get("code") or "-", e.nickname)
        if not target:
            if cap:
                cand = [x for x in cand if load.get(x["id"], 0) < cap]
            if not cand:
                skipped.append(dict(ref, why="ไม่มีเซลล์ว่างในคิวจ่ายวน (หยุด/ยังไม่เช็คชื่อ/เต็มเพดาน)"))
                continue
            pick = min(cand, key=lambda x: (load.get(x["id"], 0), x["_last"], x["name"]))
            target, why = pick["emp"], "คิวจ่ายวน"
        load[target.id] = load.get(target.id, 0) + 1
        plan.append(dict(ref, emp=target.id, to=target.nickname, why=why, dup=bool(dup),
                         since=at.isoformat() if at else ""))
    return {"ok": True, "plan": plan, "skipped": skipped, "total": total, "limit": int(limit or AUTO_LIMIT),
            "post": C.post_help()}


def release_by_owner(o, emp, by: str = "", reason: str = "") -> tuple:
    """เซลล์ "คืนกองกลาง" ลูกค้าของตัวเอง → กลับเข้าคิวรอรับ (จดประวัติว่าใครคืน เพราะอะไร)"""
    note = "เซลล์คืนกองกลาง" + ((" · " + reason.strip()) if (reason or "").strip() else "")
    return C.assign(o.id, None, by=by or (emp.nickname if emp else ""), note=note[:200])


# ─────────────────────────────────────────────────────────────
#  แจ้งเตือนในระบบ (สเปกข้อ 7) — กระดิ่งในหน้า Connect + หน้าแชทในแอป
# ─────────────────────────────────────────────────────────────
def _end_today(now):
    tz = timezone.get_current_timezone()
    return timezone.make_aware(datetime.combine(timezone.localtime(now).date(), datetime.max.time()), tz)


def alerts(me=None, admin: bool = False, now=None) -> dict:
    now = now or timezone.now()
    items = []

    def add(kind, level, text, **kw):
        items.append(dict(kind=kind, level=level, text=text, **kw))

    base = ChatOwner.objects.select_related("profile", "fb_profile", "lead")
    nq = base.filter(owner__isnull=True, awaiting_since__isnull=False).count()
    on_duty = bool(me) and C.team_of(me) == C.today_team()
    if nq and (admin or on_duty):
        add("queue", "info", "ลูกค้าใหม่รอรับ %d คน" % nq, view="queue", n=nq)
    if me:
        mine = base.filter(owner=me, awaiting_since__isnull=False)
        if not admin:
            mine = mine.filter(fb_profile__isnull=True)     # FB ของเซลล์ = เก็บข้อมูลเท่านั้น (ตอบไม่ได้)
        for o in mine.filter(due_at__lte=now).order_by("due_at")[:5]:
            add("overdue", "err", "%s รอคำตอบเลยเวลา %d นาที" % (
                C.row_json(o)["name"], max(1, int((now - o.due_at).total_seconds() // 60))), id=o.id)
        for o in mine.filter(due_at__gt=now, due_at__lte=now + timedelta(minutes=2)).order_by("due_at")[:5]:
            add("soon", "warn", "%s ใกล้หมดเวลาตอบ" % C.row_json(o)["name"], id=o.id, due=_iso(o.due_at))
    fq = ChatFollowup.objects.filter(done_at__isnull=True, due_at__lte=_end_today(now)).select_related("chat")
    if not admin:
        fq = fq.filter(Q(employee=me) | Q(chat__owner=me)) if me else fq.none()
    for f in fq.order_by("due_at")[:8]:
        o = f.chat
        lt = timezone.localtime(f.due_at)
        late = f.due_at < now
        add("appt", "err" if late else "warn",
            "%s %s %s น.%s" % (f.get_kind_display(), C.row_json(o)["name"], lt.strftime("%H:%M"),
                              " (เลยนัดแล้ว)" if late else "") + ((" · @" + f.emp_name) if admin and f.emp_name else ""),
            id=o.id, due=_iso(f.due_at))
    if me and not admin:
        owned = list(base.filter(owner=me, last_in_at__lte=now - timedelta(days=SILENT_STEPS[0])))
        buckets = {n: 0 for n in SILENT_STEPS}
        for o in owned:
            if stage_of(o, C.lead_of(o, create=False)) in CLOSED:
                continue
            sd = silent_days(o, now) or 0
            buckets[max(n for n in SILENT_STEPS if sd >= n)] += 1
        for n in reversed(SILENT_STEPS):
            if buckets[n]:
                add("silent", "warn" if n >= 7 else "info",
                    "ลูกค้าเงียบ %s วัน %d คน — ทักไปถามอีกครั้ง" % ("%d+" % n if n == SILENT_STEPS[-1] else n, buckets[n]),
                    filter={"silent": str(n)}, n=buckets[n])
    mm = match_map()
    if mm:
        codes = set(mm)
        q = ChatLead.objects.filter(code__in=list(codes))
        if not admin:
            q = q.filter(chat__owner=me) if me else q.none()
        n = q.count()
        if n:
            add("match", "info", "รถเข้าใหม่ตรงกับลูกค้า %d คน%s" % (n, "" if admin else "ของคุณ"),
                filter={"carmatch": "1"}, n=n)
    return {"items": items, "count": sum(1 for x in items if x["level"] in ("err", "warn")) or len(items),
            "now": _iso(now)}


# ─────────────────────────────────────────────────────────────
#  AI สรุปแชท (สเปกข้อ 6) — Gemini ร่าง · เซลล์ตรวจ/แก้ แล้วกดบันทึกเอง · ไม่บันทึกอัตโนมัติ
#    ส่งข้อความแชทไป Google (Gemini · ผู้ให้บริการเดียวกับ OCR เอกสารไฟแนนซ์) — **ปิดบังเบอร์/ไอดีก่อนส่ง**
# ─────────────────────────────────────────────────────────────
_AI = {}
AI_TTL = 1800
_MASK_LID = re.compile(r"(?i)((?:line\s*id|id\s*line|ไอดี\s*ไลน์|ไอดี|ไลน์|line)\s*[:：=]?\s*)@?[a-z0-9._\-]{3,}")


def mask(text: str) -> str:
    t = C._PHONE_RE.sub("[เบอร์]", text or "")
    return _MASK_LID.sub(r"\1[ไอดี]", t)


def _ai_prompt(o, ld, msgs) -> str:
    lines = []
    for m in msgs[-60:]:
        t = mask((m.get("text") or "").strip())[:300]
        if t:
            lines.append(("ลูกค้า: " if m.get("dir") != "out" else "เรา: ") + t)
    ctx = []
    if ld:
        for k, lab in (("car_text", "รถที่ถาม"), ("car_model", "รุ่น"), ("customer_status", "สถานะลูกค้า"),
                       ("occupation", "อาชีพ"), ("income", "รายได้")):
            v = getattr(ld, k, "")
            if v:
                ctx.append("%s: %s" % (lab, mask(v)))
    ctx.append("ขั้นตอนตอนนี้: %s" % STAGE_NAME.get(stage_of(o, ld), "-"))
    stages = ", ".join("%s=%s" % (k, STAGE_NAME[k]) for k in SET_STAGES)
    return ("คุณคือผู้ช่วยเซลล์เต็นท์รถมือสอง อ่านแชทลูกค้าแล้วสรุปให้เซลล์ (ภาษาไทย กระชับ อิงข้อความจริงเท่านั้น ห้ามเดา)\n"
            "ข้อมูลที่มี:\n%s\n\nแชท (เก่า→ใหม่):\n%s\n\n"
            "ตอบเป็น JSON อย่างเดียว ไม่มีข้อความอื่น:\n"
            '{"summary": "สรุป 2-4 บรรทัด: ลูกค้าต้องการรถอะไร งบ/ผ่อน/ดาวน์ ข้อกังวล ทำอะไรค้างไว้",'
            ' "stage": "คีย์ขั้นที่เหมาะ (%s)", "stage_reason": "เหตุผลสั้นๆ",'
            ' "follow_in_days": จำนวนวันที่ควรติดตามครั้งถัดไป (0-30) หรือ null,'
            ' "follow_note": "ควรคุยเรื่องอะไรตอนติดตาม"}'
            % ("\n".join(ctx), "\n".join(lines) or "(ไม่มีข้อความ)", stages))


def _parse_json(text: str) -> dict:
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.M).strip()
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j <= i:
        raise ValueError("AI ไม่ได้ตอบเป็น JSON")
    return json.loads(t[i:j + 1])


def ai_draft(o, msgs) -> tuple:
    """→ (ok, {summary, stage, stageLabel, stageReason, followDays, followAt, followNote} | ข้อความ)"""
    if not (getattr(settings, "GEMINI_API_KEY", "") or "").strip():
        return False, "ยังไม่ได้ตั้ง GEMINI_API_KEY — ใช้ AI สรุปไม่ได้ (พิมพ์สรุปเองได้)"
    if not msgs:
        return False, "ยังไม่มีข้อความให้สรุป"
    ld = C.lead_of(o, create=False)
    prompt = _ai_prompt(o, ld, msgs)
    key = hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:20]
    hit = _AI.get(key)
    if hit and time.time() - hit[0] < AI_TTL:
        return True, hit[1]
    try:
        from dashboard.services.gemini_insights import _gemini_text
        raw = _gemini_text(prompt, 700)
        d = _parse_json(raw)
    except Exception as e:
        return False, "AI สรุปไม่สำเร็จ: %s" % str(e)[:140]
    st = str(d.get("stage") or "").strip()
    st = st if st in SET_STAGES else ""
    days = d.get("follow_in_days")
    try:
        days = max(0, min(30, int(days))) if days is not None and str(days).strip() not in ("", "null") else None
    except Exception:
        days = None
    fa = ""
    if days is not None:
        day = timezone.localdate() + timedelta(days=days or 1)
        fa = "%sT10:00" % day.isoformat()
    out = {"summary": str(d.get("summary") or "").strip()[:2000], "stage": st, "stageLabel": STAGE_NAME.get(st, ""),
           "stageReason": str(d.get("stage_reason") or "").strip()[:200], "followDays": days, "followAt": fa,
           "followNote": str(d.get("follow_note") or "").strip()[:300]}
    if len(_AI) > 300:
        _AI.clear()
    _AI[key] = (time.time(), out)
    return True, out


def save_summary(o, text: str, by: str = "", emp=None) -> tuple:
    text = (text or "").strip()
    if len(text) > 2000:
        return False, "สรุปยาวเกินไป (ไม่เกิน 2,000 ตัวอักษร)"
    ld = C.lead_of(o)
    ld.summary, ld.summary_at, ld.summary_by = text, timezone.now(), (by or "")[:80]
    ld.save(update_fields=["summary", "summary_at", "summary_by", "updated_at"])
    _log(o, ChatOwnerLog.SUMMARY, emp=emp, by=by, note=(text[:120] or "ลบสรุป"))
    return True, "บันทึกสรุปแล้ว"


# ─────────────────────────────────────────────────────────────
#  รายละเอียดลูกค้า (แผงขวาของแชท / หน้าแชทในแอป)
# ─────────────────────────────────────────────────────────────
def detail_json(o, ld=None, now=None) -> dict:
    now = now or timezone.now()
    ld = ld if ld is not None else C.lead_of(o, create=False)
    bk = booking_of(ld.code if ld else "")
    code = ((ld.code if ld else "") or "").strip().upper()
    return {
        "stages": [{"key": k, "label": STAGE_NAME[k]} for k in SET_STAGES],
        "lostReasons": LOST_REASONS,
        "callResults": [{"key": k, "label": v} for k, v in ChatCall.RESULT_CHOICES],
        "extra": row_extra(o, ld, now),
        "stageBy": (ld.stage_by if ld else "") or "", "stageAt": _iso(ld.stage_at) if ld else "",
        "summary": (ld.summary if ld else "") or "", "summaryAt": _iso(ld.summary_at) if ld else "",
        "summaryBy": (ld.summary_by if ld else "") or "",
        "followups": followups_json(o), "calls": calls_json(o), "pastOwners": past_owners(o),
        "booking": bk, "cars": (match_map().get(code) or [])[:5] if code else [],
        "aiOn": bool((getattr(settings, "GEMINI_API_KEY", "") or "").strip()),
    }


# ─────────────────────────────────────────────────────────────
#  วิเคราะห์ (สเปกข้อ 8) — ขั้นของลีดตามช่องทาง · ความร้อน · เหตุผลที่ไม่ซื้อ
# ─────────────────────────────────────────────────────────────
def _src_of(o, ld) -> str:
    ch = ((ld.channel if ld else "") or "").strip()
    return ch or ("Facebook" if C.is_fb(o) else "LINE")


def insights(days: int = 30, now=None) -> dict:
    now = now or timezone.now()
    since = now - timedelta(days=days)
    stages = {k: 0 for k, _ in STAGES}
    heat = {"hot": 0, "warm": 0, "cold": 0}
    src, ads, lost = {}, {}, {}
    dead = _dead_words()
    unwanted = 0
    for o in ChatOwner.objects.select_related("lead", "profile", "fb_profile").filter(last_at__gte=since):
        ld = C.lead_of(o, create=False)
        st = stage_of(o, ld)
        stages[st] = stages.get(st, 0) + 1
        hk = heat_of(o, ld, now)["key"]
        if hk:
            heat[hk] += 1
        s = src.setdefault(_src_of(o, ld), {"src": _src_of(o, ld), "total": 0, "contacted": 0, "viewing": 0,
                                             "finance": 0, "won": 0, "lost": 0})
        s["total"] += 1
        o_ = _ORDER.get(st, 0)
        if st != "lost" and o_ >= 2:
            s["contacted"] += 1
        if st != "lost" and o_ >= 3:
            s["viewing"] += 1
        if st != "lost" and o_ >= 4:
            s["finance"] += 1
        if st == "won":
            s["won"] += 1
        if st == "lost":
            s["lost"] += 1
            r = (ld.lost_reason if ld else "") or "ไม่ระบุ"
            lost[r] = lost.get(r, 0) + 1
        ad = ((ld.ads if ld else "") or "").strip()
        if ad:
            a = ads.setdefault(ad, {"ads": ad, "total": 0, "won": 0, "lost": 0})
            a["total"] += 1
            a["won"] += st == "won"
            a["lost"] += st == "lost"
        z = (ld.customer_status if ld else "") or ""
        if st == "lost" or (z and any(w in z for w in dead)):
            unwanted += 1
    for s in src.values():
        s["winRate"] = round(100.0 * s["won"] / s["total"], 1) if s["total"] else 0
    return {"days": days, "stages": [{"key": k, "label": STAGE_NAME[k], "n": stages.get(k, 0)} for k, _ in STAGES],
            "heat": heat, "sources": sorted(src.values(), key=lambda x: -x["total"]),
            "ads": sorted(ads.values(), key=lambda x: -x["total"])[:12],
            "lost": sorted(({"reason": k, "n": v} for k, v in lost.items()), key=lambda x: -x["n"]),
            "unwanted": unwanted}


def unwanted_csv(days: int = 180) -> bytes:
    """รายชื่อลูกค้า "ไม่ต้องการ" (ปิดเป็นไม่สนใจ / สถานะลูกค้าเป็นเคสเสีย) — ไว้ตัดออกจากกลุ่มเป้าหมายโฆษณา
    มีเบอร์โทร = ข้อมูลส่วนบุคคล · แอดมิน/ผู้บริหารเท่านั้น (เช็คที่ view) · BOM ให้ Excel ไทยไม่เพี้ยน"""
    since = timezone.now() - timedelta(days=days)
    dead = _dead_words()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ชื่อลูกค้า", "เบอร์โทร", "ID LINE", "ช่องทาง", "ADS", "ขั้น", "เหตุผลที่ไม่ซื้อ", "สถานะลูกค้า",
                "เซลล์", "อัปเดตล่าสุด"])
    for o in ChatOwner.objects.select_related("lead", "owner", "profile", "fb_profile").filter(last_at__gte=since):
        ld = C.lead_of(o, create=False)
        if not ld:
            continue
        st = stage_of(o, ld)
        z = ld.customer_status or ""
        if not (st == "lost" or (z and any(x in z for x in dead))):
            continue
        lt = timezone.localtime(o.last_at) if o.last_at else None
        w.writerow([C.row_json(o)["name"], ld.phone, ld.line_id, _src_of(o, ld), ld.ads, STAGE_NAME.get(st, st),
                    ld.lost_reason, z, o.owner.nickname if o.owner_id else "",
                    lt.strftime("%Y-%m-%d %H:%M") if lt else ""])
    return ("﻿" + buf.getvalue()).encode("utf-8")


# ─────────────────────────────────────────────────────────────
#  cron (เรียกจาก connect.tick ทุกนาที)
# ─────────────────────────────────────────────────────────────
WHAT_APPT = "นัดลูกค้า (Connect)"


def _pull_back(c, now) -> list:
    """เจ้าของรับลูกค้าแล้วไม่ตอบ จนเลยเส้นตาย + เกิน pull_min นาทีหลังรับ → คืนคิวให้คนอื่นรับ (ปิดโดยปริยาย)"""
    n = int(c.get("pull_min") or 0)
    if n <= 0:
        return []
    out = []
    rows = (ChatOwner.objects.select_related("owner", "profile", "fb_profile")
            .filter(owner__isnull=False, awaiting_since__isnull=False, due_at__lte=now,
                    claimed_at__lte=now - timedelta(minutes=n), first_reply_at__isnull=True)[:20])
    for o in rows:
        if C.is_sim_row(o) or (o.last_out_at and o.claimed_at and o.last_out_at >= o.claimed_at):
            continue
        who = o.owner.nickname
        ok, _m = C.assign(o.id, None, by="ระบบ", note="ไม่ตอบภายใน %d นาทีหลังรับ — ระบบดึงคืนคิว (%s)" % (n, who))
        if ok:
            out.append(o.id)
    return out


def _remind_appts(c, now) -> int:
    """นัดที่ใกล้ถึง (30 นาที) → แชทส่วนตัวเซลล์ทาง LINE ครั้งเดียว · ปิดโดยปริยาย (`appt_line`)"""
    if not c.get("appt_line"):
        return 0
    from dashboard.services.line_channels import dm_token
    from dashboard.services.line_notify import push_line_message
    from . import leadflow as LF
    n = 0
    for f in (ChatFollowup.objects.filter(done_at__isnull=True, reminded_at__isnull=True, employee__isnull=False,
                                          due_at__lte=now + timedelta(minutes=30), due_at__gte=now - timedelta(minutes=5))
              .select_related("employee", "chat")[:10]):
        if not ChatFollowup.objects.filter(pk=f.pk, reminded_at__isnull=True).update(reminded_at=now):
            continue
        if C.is_sim_row(f.chat):
            continue
        uid = LF._dm_uid(f.employee)
        if not uid:
            continue
        lt = timezone.localtime(f.due_at)
        text = "⏰ %s %s น.\nลูกค้า: %s%s\n%s" % (f.get_kind_display(), lt.strftime("%H:%M"), C.row_json(f.chat)["name"],
                                                ("\n" + f.note) if f.note else "", C._link(f.chat))
        sc, _b = push_line_message(uid, [{"type": "text", "text": text[:900]}], dm_token(), what=WHAT_APPT)
        n += 1 if sc == 200 else 0
    return n


_CLEAN = {"day": None}


def tick(now=None) -> dict:
    now = now or timezone.now()
    c = C.cfg()
    out = {}
    try:
        p = _pull_back(c, now)
        if p:
            out["pulled"] = len(p)
    except Exception as e:
        out["pullError"] = str(e)[:120]
    try:
        n = _remind_appts(c, now)
        if n:
            out["apptReminded"] = n
    except Exception as e:
        out["apptError"] = str(e)[:120]
    d = timezone.localdate()
    if _CLEAN["day"] != d:
        _CLEAN["day"] = d
        try:
            n = cleanup_files(now)
            if n:
                out["proofDirsDeleted"] = n
        except Exception as e:
            out["proofCleanError"] = str(e)[:120]
    return out
