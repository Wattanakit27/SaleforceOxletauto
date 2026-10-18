# -*- coding: utf-8 -*-
"""จ่ายลีดขายจากแชท (LINE/Facebook) อัตโนมัติ (★ 18 ต.ค.69 · เจ้าของ "ขอเอาหลีดขายก่อน")

เจ้าของ *"ฉันไม่ได้ต้องการให้แอดมินมาเก็บแล้ว ตอนนี้ฉันอยากทดลองระบบออโต้ ซึ่งฉันอยากมั่นใจว่าตรวจสอบแล้ว
มันไม่มีข้อมูลส่วนไหนหลุดหรือซ้ำกับที่เราหรือแอดมินเก็บมาแล้ว"*

สวิตช์ `leadflow_config.auto_chat` 3 ระดับ
  off      — ไม่ทำอะไร (ค่าตั้งต้น)
  observe  — "จดอย่างเดียว": ตัดสินเหมือนจะจ่ายจริง แต่ **ไม่จ่าย ไม่ส่งอะไรออก** จดผลลง KV `autochat_log`
             ไว้เทียบกับสิ่งที่แอดมินทำจริง (`report()` · `manage.py autochat --report`)
  on       — จ่ายจริงผ่าน `connect.assign_lead` ตัวเดียวกับปุ่มจ่ายเบอร์ (ล็อกเลข · ส่งใบเข้ากลุ่ม · แท็กเซลล์)

แชทที่ระบบดู = ลีดขาย · คุยในระบบแล้ว · ยังไม่มีเลข · มีเบอร์/ID LINE · **ลูกค้าให้ช่องทางติดต่อหลังเปิดสวิตช์**
(`_contact_at` ≥ `auto_chat_since`) · ให้มาแล้วเกิน `auto_after_min` นาที (เผื่อแอดมินจ่ายเองก่อน)

ข้าม (ให้คนตัดสิน) เมื่อ — เรียงตามที่ตรวจ:
  1. ลูกค้าจำลอง / บัญชีพนักงาน
  2. ได้เลขแล้ว (ใบจ่ายลีด/ชีตลีด ตรงเบอร์หรือ ID LINE · `connect.autofill`) = แอดมินจ่ายแล้ว
  3. เป็นลีดรับซื้อ / ส่งจัดซื้อแล้ว / แอดมินกด "ไม่ต้องจ่ายเบอร์"
  4. ใบจ่ายลีดตรง "ชื่อ" อย่างเดียว (`_maybe`) — อาจจ่ายแล้ว
  5. แอดมินโพสต์ใบร่างของลูกค้าคนนี้ในกลุ่มพักลีดแล้ว (จ่ายทางห้องพักแทน)
  6. ลูกค้าคนเดียวกันทักอีกช่องทาง (เบอร์/ID LINE ตรงกับแชทอื่น)
  7. ลูกค้าเก่า — เบอร์เคยเป็นลีด (สมุดเบอร์) / ID LINE เคยได้เลข (แชท · ห้องพัก · ชีต)
  8. ไม่มีเซลล์ว่างในคิวจ่ายวน
"""
from __future__ import annotations

import threading
import time
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import ChatLead, ChatOwner, Employee

KV_LOG = "autochat_log"
KV_STATE = "autochat_state"
KV_LAST = "autochat_last"
MODES = ("off", "observe", "on")
MODE_NAME = {"off": "ปิด", "observe": "จดอย่างเดียว (ไม่จ่ายจริง)", "on": "จ่ายจริง"}
BY = "จ่ายวนอัตโนมัติ (แชท)"
RECHECK_MIN = 10            # แชทที่ข้ามไปแล้ว ตรวจซ้ำได้ทุกกี่นาที (ลูกค้าอาจให้ข้อมูลเพิ่ม/แอดมินจ่ายไปแล้ว)
CHECK_PER_RUN = 25          # ตรวจกี่แชทต่อรอบ (autofill อ่านแชท — ไม่ไล่ทุกแชททุกนาที)
MAX_PER_RUN = 3             # จ่ายจริงได้กี่ใบต่อรอบ (เท่ากับจ่ายวนใบร่าง)
LOG_MAX = 400
SAME_DAYS = 30              # แชทอื่นของลูกค้าคนเดียวกัน — ดูย้อนกี่วัน
BG = True                   # เทสต์ปิด (thread ชน SQLite)
_LOCK_KEY = 7_406_067       # Postgres advisory lock — worker เดียวทำทีละรอบ (เลขไม่ชนตัวอื่น)
_RUN = {"at": 0.0, "busy": False}

WOULD, ASSIGNED, FAILED, SKIP, HUMAN = "would", "assigned", "failed", "skip", "human"


def _kv(key):
    try:
        from dashboard.services import cache_store
        return (cache_store.get_kv(key) or {}).get("data")
    except Exception:
        return None


def _set_kv(key, val):
    try:
        from dashboard.services import cache_store
        cache_store.set_kv(key, val)
    except Exception:
        pass


def _iso(dt):
    return timezone.localtime(dt).isoformat(timespec="seconds") if dt else ""


def mode(c=None) -> str:
    from . import leadflow as LF
    c = c or LF.cfg()
    m = c.get("auto_chat") or "off"
    return m if m in MODES else "off"


def since(c=None):
    from . import leadflow as LF
    c = c or LF.cfg()
    v = c.get("auto_chat_since") or ""
    return parse_datetime(v) if v else None


# ─────────────────────────────────────────────────────────────
#  ตัดสินทีละแชท
# ─────────────────────────────────────────────────────────────
def _contact_at(lead):
    v = (lead.auto or {}).get("_contact_at") if lead else ""
    return parse_datetime(v) if v else None


def _same_customer(o, lead) -> dict | None:
    """แชทอื่นที่เป็นลูกค้าคนเดียวกัน (เบอร์ตรง / ID LINE ตรง) — มีเลขแล้ว หรือแชทนั้นเก่ากว่า = ข้ามแชทนี้
    เทียบในโปรแกรม (ไม่ค้นข้อความ) — "081-234-5678" กับ "0812345678" · "abc.def" กับ "abc_def" คือคนเดียวกัน"""
    from . import leadmatch as LM
    from .connect import phones_in
    cut = timezone.now() - timedelta(days=SAME_DAYS)
    mine_p = set(phones_in([lead.phone])) if lead.phone else set()
    mine_l = LM.lid_core(lead.line_id)
    if not mine_p and not mine_l:
        return None
    best = None
    rows = (ChatLead.objects.filter(updated_at__gte=cut).exclude(pk=lead.pk)
            .filter(Q(phone__gt="") | Q(line_id__gt=""))
            .values_list("chat_id", "phone", "line_id", "code"))
    for chat_id, ph, lid, code in rows.iterator():
        if mine_p and mine_p & set(phones_in([ph])):
            how = "เบอร์"
        elif mine_l and LM.lid_core(lid) == mine_l:
            how = "ID LINE"
        else:
            continue
        if (code or "").strip():
            return {"chat": chat_id, "code": code, "how": how}
        if chat_id and chat_id < o.id and best is None:
            best = {"chat": chat_id, "code": "", "how": how}
    return best


def _returning(lead) -> str:
    """ลูกค้าเก่า? → ข้อความบอกเหตุผล · ใหม่ = "" """
    from . import leadflow as LF
    from . import leadmatch as LM
    if lead.phone:
        d = LF.dup_info(lead.phone, exclude_code=lead.code or "")
        if d:
            return "เบอร์เคยเป็นลีด %s ของ %s (%s)" % (d.get("code") or "-", d.get("seller") or "?", d.get("date") or "-")
    if lead.line_id:
        t = LM.lid_taken(lead.line_id, days=0, exclude_lead=lead.pk)
        if t:
            return "ID LINE เคยได้เลข %s (%s)" % (t["code"], t["where"])
    return ""


def _draft_hit(o, lead) -> dict | None:
    """แอดมินโพสต์ใบร่างของลูกค้าคนนี้ในกลุ่มพักลีดแล้ว → จ่ายทางห้องพัก (จ่ายวนใบร่าง) ไม่ใช่ทางแชท"""
    from . import leadmatch as LM
    from .connect import is_fb, phones_in
    ref = _contact_at(lead) or o.last_in_at or timezone.now()
    hits = LM.find(phones=phones_in([lead.phone]) if lead.phone else (), lid=LM.lid_core(lead.line_id),
                   names=LM.chat_names(o, lead), fb=is_fb(o), since=ref - timedelta(days=2), kinds=("draft",))
    if not hits:
        return None
    doc, how, strong = hits[0]
    return {"at": _iso(doc["at"]), "how": "+".join(how), "strong": strong}


def decide(o, c=None, cand=None, load=None) -> dict:
    """ตัดสินแชทเดียว → `{d: would|skip|human, why, emp?, pfx?, base?, admin?}` · ไม่เขียนอะไรนอกจาก autofill"""
    from . import connect as C
    if C.is_sim_row(o):
        return {"d": SKIP, "why": "ลูกค้าจำลอง"}
    if getattr(C.cust(o), "is_employee", False):
        return {"d": SKIP, "why": "บัญชีพนักงาน"}
    lead = C.autofill(o, slip_min=1)           # จับคู่ใบจ่ายลีด/ชีตลีด (เบอร์ · ID LINE · ชื่อ) รอบนี้เลย (0 = ค่าตั้งต้น 30 นาที)
    auto = lead.auto or {}
    if (lead.code or "").strip():
        src = auto.get("code") or ""
        sl = auto.get("_slip") or auto.get(C.SHEET_KEY) or {}
        return {"d": HUMAN, "why": "ได้เลข %s แล้ว (%s)" % (lead.code, src or "แอดมิน"), "code": lead.code,
                "seller": (sl.get("seller") if isinstance(sl, dict) else "") or ""}
    if C.BUY_KEY in auto or C.BUYLEAD_KEY in auto:
        return {"d": SKIP, "why": "ลีดรับซื้อรถ (อยากขายรถให้เรา)"}
    if C.NOCODE_KEY in auto:
        return {"d": SKIP, "why": "แอดมินกด \"ไม่ต้องจ่ายเบอร์\""}
    if not (lead.phone or lead.line_id):
        return {"d": SKIP, "why": "ยังไม่มีเบอร์/ID LINE"}
    mb = auto.get(C.MAYBE_KEY)
    if mb:
        return {"d": SKIP, "why": "ชื่อตรงใบจ่ายลีด %s — อาจจ่ายแล้ว ให้แอดมินดู" % (mb.get("code") or "-")}
    dh = _draft_hit(o, lead)
    if dh:
        return {"d": SKIP, "why": "มีใบร่างในกลุ่มพักลีดแล้ว (ตรง %s) — จ่ายทางห้องพัก" % dh["how"]}
    same = _same_customer(o, lead)
    if same:
        if same["code"]:
            return {"d": SKIP, "why": "ลูกค้าคนเดียวกับแชท #%s (ตรง%s) ได้เลข %s แล้ว" % (same["chat"], same["how"], same["code"])}
        return {"d": SKIP, "why": "ลูกค้าคนเดียวกับแชท #%s (ตรง%s) — จ่ายที่แชทนั้น" % (same["chat"], same["how"])}
    ret = _returning(lead)
    if ret:
        return {"d": SKIP, "why": "ลูกค้าเก่า: " + ret}
    # ใครได้: มีเซลล์ดูแลอยู่ = คนเดิม · ไม่งั้นคิวจ่ายวน (คนได้ใบน้อยสุดวันนี้ก่อน · นับที่รอบนี้จัดไปแล้ว)
    emp, why = None, ""
    if o.owner_id and o.owner.active and not C.is_test_seller(o.owner):
        emp, why = o.owner, "ดูแลแชทนี้อยู่"
    else:
        from . import leadflow as LF
        c = c or LF.cfg()
        cand = LF.rr_candidates(c) if cand is None else cand
        load = {} if load is None else load
        cap = c.get("cap_day") or 0
        ok = [x for x in cand if not cap or (x["today"] + load.get(x["id"], 0)) < cap]
        if not ok:
            return {"d": SKIP, "why": "ไม่มีเซลล์ว่างในคิวจ่ายวน (หยุด/ยังไม่เช็คชื่อ/เต็มเพดาน)"}
        pick = min(ok, key=lambda x: (x["today"] + load.get(x["id"], 0), x["_last"], x["name"]))
        emp, why = pick["emp"], "คิวจ่ายวน"
    sg = C.suggest_prefix(lead, C.team_of(emp), o=o)
    return {"d": WOULD, "why": why, "emp": emp, "base": sg["base"], "admin": bool(sg["admin"]),
            "pfx": C.build_prefix(sg["base"], sg["admin"], False), "pfxWhy": sg.get("why") or ""}


# ─────────────────────────────────────────────────────────────
#  รอบ (cron ทุกนาที)
# ─────────────────────────────────────────────────────────────
def candidates(c=None, now=None) -> list:
    """แชทที่เข้าเงื่อนไขให้ดู (ยังไม่ตัดสิน) — ลูกค้าให้ช่องทางติดต่อหลังเปิดสวิตช์ + รอเกิน auto_after_min"""
    from . import connect as C
    from . import leadflow as LF
    c = c or LF.cfg()
    now = now or timezone.now()
    st = since(c)
    if not st:
        return []
    wait = timedelta(minutes=c.get("auto_after_min") or 10)
    qs = (ChatOwner.objects.select_related("profile", "fb_profile", "owner", "lead")
          .filter(last_in_at__gte=st).filter(C._engaged_q()).filter(C._no_code_q())
          .filter(C._contact_q()).filter(C._sell_q()).order_by("last_in_at"))
    out = []
    for o in qs[:400]:
        at = _contact_at(getattr(o, "lead", None))
        if at and at >= st and at <= now - wait:
            out.append(o)
    return out


def _state() -> dict:
    s = _kv(KV_STATE)
    return s if isinstance(s, dict) else {}


def _log(rows: list):
    if not rows:
        return
    cur = _kv(KV_LOG)
    cur = cur if isinstance(cur, list) else []
    _set_kv(KV_LOG, (rows + cur)[:LOG_MAX])


def _row(o, res: dict, m: str) -> dict:
    from .connect import is_fb
    r = {"at": _iso(timezone.now()), "chat": o.id, "ch": "FB" if is_fb(o) else "LINE", "d": res["d"],
         "why": (res.get("why") or "")[:200], "mode": m}
    if res.get("emp") is not None:
        r["to"], r["toId"] = res["emp"].nickname, res["emp"].id
    for k in ("pfx", "code", "seller", "msg"):
        if res.get(k):
            r[k] = str(res[k])[:160]
    return r


def run(now=None, c=None) -> dict:
    """1 รอบ: ตรวจแชทที่เข้าเงื่อนไข → จด (observe) หรือจ่ายจริง (on) · คืนสรุป"""
    from . import connect as C
    from . import leadflow as LF
    c = c or LF.cfg()
    now = now or timezone.now()
    m = mode(c)
    if m == "off":
        return {"mode": "off"}
    st = _state()
    recheck = timedelta(minutes=RECHECK_MIN)
    cand_rr, load = LF.rr_candidates(c), {}
    logs, out = [], {"mode": m, "checked": 0, "would": 0, "assigned": 0, "skipped": 0, "human": 0, "failed": 0}
    in_hours = _in_hours(now)
    for o in candidates(c, now):
        if out["checked"] >= CHECK_PER_RUN:
            break
        prev = st.get(str(o.id)) or {}
        last = parse_datetime(prev.get("at") or "") if prev.get("at") else None
        if prev.get("d") == ASSIGNED or (last and now - last < recheck):
            continue
        out["checked"] += 1
        try:
            res = decide(o, c, cand_rr, load)
        except Exception as e:
            res = {"d": SKIP, "why": "ตรวจไม่สำเร็จ: %s" % str(e)[:120]}
        d = res["d"]
        if d == WOULD and m == "on":
            if not in_hours:
                res = dict(res, d=SKIP, why="นอกเวลาทำการ — รอเปิด")
                d = SKIP
            elif out["assigned"] >= MAX_PER_RUN:
                continue                       # ครบโควตารอบนี้ — รอบหน้าค่อยจ่าย (ไม่จดสถานะ)
            else:
                try:
                    ok, msg = C.assign_lead(o, res["emp"], res["base"], admin=res["admin"], by=BY)
                except Exception as e:
                    ok, msg = False, "จ่ายไม่สำเร็จ: %s" % str(e)[:120]
                res = dict(res, d=ASSIGNED if ok else FAILED, msg=msg)
                d = res["d"]
        if res.get("emp") is not None and d in (WOULD, ASSIGNED):
            load[res["emp"].id] = load.get(res["emp"].id, 0) + 1
        out[{WOULD: "would", ASSIGNED: "assigned", SKIP: "skipped", HUMAN: "human", FAILED: "failed"}[d]] += 1
        changed = prev.get("d") != d or prev.get("why") != res.get("why")
        st[str(o.id)] = {"at": _iso(now), "d": d, "why": (res.get("why") or "")[:160]}
        if changed or d in (ASSIGNED, FAILED):
            logs.append(_row(o, res, m))
    # ตัดสถานะของแชทที่ไม่อยู่ในรอบแล้ว (ได้เลข/ออกจากเงื่อนไข) ที่เก่ากว่า 3 วัน
    cut = now - timedelta(days=3)
    st = {k: v for k, v in st.items() if (parse_datetime(v.get("at") or "") or now) >= cut}
    _set_kv(KV_STATE, st)
    _log(logs)
    _set_kv(KV_LAST, dict(out, at=_iso(now)))
    if out["failed"]:
        try:
            from dashboard.services import eventlog
            eventlog.log("autochat", name="จ่ายวนอัตโนมัติ (แชท)", ok=False, failed=out["failed"])
        except Exception:
            pass
    return out


def _in_hours(now) -> bool:
    """เวลาทำการของ Connect (ส่งใบเข้ากลุ่มตอนตี 2 = เซลล์ไม่เห็น นาฬิกาโทรเดินฟรี)"""
    from . import connect as C
    try:
        c = C.cfg()
        oh, om = C._hm(c.get("open"), (8, 30))
        ch, cm = C._hm(c.get("close"), (20, 0))
        if (oh, om) == (ch, cm):
            return True
        lt = timezone.localtime(now)
        return (oh, om) <= (lt.hour, lt.minute) < (ch, cm)
    except Exception:
        return True


def tick_bg(now=None) -> dict:
    """เรียกจาก leadflow.tick ทุกนาที — ทำใน thread (autofill อ่านแชทหลายคน · ห้ามหน่วง cron)"""
    if mode() == "off":
        return {}
    if time.time() - _RUN["at"] < 55 or _RUN["busy"]:
        return {}
    _RUN["at"] = time.time()
    if not BG:
        return _locked_run(now)

    def _work():
        _RUN["busy"] = True
        try:
            _locked_run(now)
        except Exception as e:
            _set_kv(KV_LAST, {"at": _iso(timezone.now()), "error": str(e)[:200]})
        finally:
            _RUN["busy"] = False
            try:
                from django.db import connection
                connection.close()
            except Exception:
                pass

    threading.Thread(target=_work, daemon=True).start()
    return {"started": True}


def _locked_run(now=None) -> dict:
    from django.db import connection
    if connection.vendor != "postgresql":
        return run(now)
    with connection.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(%s)", [_LOCK_KEY])
        got = bool(cur.fetchone()[0])
    if not got:
        return {"skipped": "อีกตัวกำลังทำอยู่"}
    try:
        return run(now)
    finally:
        try:
            with connection.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s)", [_LOCK_KEY])
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────
#  รายงาน "ระบบจะทำอะไร vs แอดมินทำจริง" (โหมดจดอย่างเดียว)
# ─────────────────────────────────────────────────────────────
def report(days: int = 7) -> dict:
    """เทียบสิ่งที่ระบบตัดสิน (log) กับสถานะจริงตอนนี้ของแต่ละแชท

    ระบบจะจ่าย (would) → ตอนนี้แชทนั้น: แอดมินจ่ายแล้ว (เซลล์เดียวกัน/คนละคน) · ยังไม่มีใครจ่าย
    ระบบข้าม → แอดมินจ่ายแล้ว (ระบบระวังเกินไป?) · ยังไม่จ่าย
    ไม่มีชื่อ/เบอร์ลูกค้า — อ้างเลขแชทเท่านั้น
    """
    from . import connect as C
    logs = _kv(KV_LOG)
    logs = logs if isinstance(logs, list) else []
    cut = timezone.now() - timedelta(days=days)
    last = {}
    for r in reversed(logs):                  # เก่า→ใหม่ — เก็บการตัดสินล่าสุดต่อแชท (ไม่นับ human)
        at = parse_datetime(r.get("at") or "")
        if not at or at < cut or r.get("d") == HUMAN:
            continue
        last[r["chat"]] = r
    leads = {x.chat_id: x for x in ChatLead.objects.filter(chat_id__in=list(last)).only(
        "chat_id", "code", "auto", "assigned_by")}
    owners = dict(ChatOwner.objects.filter(id__in=list(last)).values_list("id", "owner__nickname"))
    rows, sm = [], {"would": 0, "would_paid_same": 0, "would_paid_other": 0, "would_open": 0,
                    "assigned": 0, "skip": 0, "skip_paid": 0, "skip_open": 0, "failed": 0}
    reasons = {}
    for cid, r in last.items():
        ld = leads.get(cid)
        code = (ld.code or "").strip() if ld else ""
        by_sys = bool(ld and (ld.assigned_by or "").startswith("จ่ายวนอัตโนมัติ"))
        auto = (ld.auto or {}) if ld else {}
        sl = auto.get("_slip") or auto.get(C.SHEET_KEY) or {}
        seller = (sl.get("seller") if isinstance(sl, dict) else "") or (owners.get(cid) if code else "") or ""
        row = {"chat": cid, "ch": r.get("ch"), "d": r["d"], "why": r.get("why"), "to": r.get("to") or "",
               "pfx": r.get("pfx") or "", "code": code, "seller": seller, "bySystem": by_sys}
        if r["d"] == WOULD:
            sm["would"] += 1
            if code:
                same = bool(seller and seller == r.get("to"))
                sm["would_paid_same" if same else "would_paid_other"] += 1
                row["verdict"] = "แอดมินจ่ายแล้ว · " + ("เซลล์เดียวกัน" if same else "คนละเซลล์ (%s)" % (seller or "?"))
            else:
                sm["would_open"] += 1
                row["verdict"] = "ยังไม่มีใครจ่าย — ระบบจะจ่ายให้ %s" % (r.get("to") or "?")
        elif r["d"] == ASSIGNED:
            sm["assigned"] += 1
            row["verdict"] = "ระบบจ่ายแล้ว %s" % code
        elif r["d"] == FAILED:
            sm["failed"] += 1
            row["verdict"] = "จ่ายไม่สำเร็จ"
        else:
            sm["skip"] += 1
            key = (r.get("why") or "").split(":")[0].split(" — ")[0][:40]
            reasons[key] = reasons.get(key, 0) + 1
            if code:
                sm["skip_paid"] += 1
                row["verdict"] = "ระบบข้าม · แอดมินจ่าย %s แล้ว" % code
            else:
                sm["skip_open"] += 1
                row["verdict"] = "ระบบข้าม · ยังไม่จ่าย (รอแอดมิน)"
        rows.append(row)
    rows.sort(key=lambda x: x["chat"], reverse=True)
    return {"days": days, "summary": sm, "reasons": sorted(reasons.items(), key=lambda x: -x[1]), "rows": rows}


def status_json() -> dict:
    """หน้าตั้งค่า: โหมด · เปิดเมื่อไหร่ · รอบล่าสุด · การตัดสิน 30 รายการล่าสุด (ไม่มีชื่อ/เบอร์ลูกค้า)"""
    from . import leadflow as LF
    c = LF.cfg()
    logs = _kv(KV_LOG)
    logs = logs if isinstance(logs, list) else []
    return {"mode": mode(c), "modeName": MODE_NAME[mode(c)], "since": c.get("auto_chat_since") or "",
            "last": _kv(KV_LAST) or {}, "recent": logs[:30]}


# ─────────────────────────────────────────────────────────────
#  ทดลองย้อนหลัง (ไม่เขียนอะไรเลย — ย้อนธุรกรรมทิ้ง)
# ─────────────────────────────────────────────────────────────
def backtest(days: int = 7, limit: int = 300) -> dict:
    """แชทลีดขายที่ลูกค้าให้เบอร์/ID LINE ใน `days` วันล่าสุด และในระบบยังไม่มีเลข → ถ้าเปิดสวิตช์ตอนนี้ ระบบจะทำอะไร
    = ตัวเลขเดียวกับที่ตรวจด้วยมือ 18 ต.ค.69 (แอดมินจ่ายแล้วแต่ระบบเดิมจับไม่ได้ / ยังไม่จ่ายจริง)
    รันใน transaction แล้วย้อนทิ้งทั้งหมด → autofill ที่จับคู่ใบได้ ก็ไม่ถูกบันทึก (ดูอย่างเดียว)"""
    from django.db import transaction
    from . import connect as C
    from . import leadflow as LF
    cut = timezone.now() - timedelta(days=days)
    rows, sm, reasons = [], {"total": 0, "human": 0, "would": 0, "skip": 0}, {}
    with transaction.atomic():
        c = LF.cfg()
        cand, load = LF.rr_candidates(c), {}
        qs = (ChatOwner.objects.select_related("profile", "fb_profile", "owner", "lead")
              .filter(last_in_at__gte=cut).filter(C._engaged_q()).filter(C._no_code_q())
              .filter(C._contact_q()).filter(C._sell_q()).order_by("-last_in_at"))
        for o in qs[:limit]:
            try:
                res = decide(o, c, cand, load)
            except Exception as e:
                res = {"d": SKIP, "why": "ตรวจไม่สำเร็จ: %s" % str(e)[:100]}
            if res["d"] == WOULD and res.get("emp") is not None:
                load[res["emp"].id] = load.get(res["emp"].id, 0) + 1
            sm["total"] += 1
            sm[res["d"]] = sm.get(res["d"], 0) + 1
            if res["d"] == SKIP:
                key = (res.get("why") or "").split(":")[0].split(" — ")[0].split(" (")[0][:40]
                reasons[key] = reasons.get(key, 0) + 1
            rows.append(_row(o, res, "backtest"))
        transaction.set_rollback(True)
    return {"days": days, "summary": sm, "reasons": sorted(reasons.items(), key=lambda x: -x[1]), "rows": rows}
