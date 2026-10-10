# -*- coding: utf-8 -*-
"""เทสต์หน้ารวมแชท (Chat Inbox · 11 ต.ค.69) — checkout/crm.py + API ใน connect_views.py

    python scripts/test_crm.py

ขั้นของลีด · ความร้อน · นัดหมาย · บันทึกการโทร + หลักฐาน · ใครเคยดูแล · ตัวกรอง · Run Auto ·
ดึงคืนเมื่อไม่ตอบ · แจ้งเตือน · AI สรุป · เตือนนัดทาง LINE · วิเคราะห์ · สิทธิ์ผ่าน API จริง

ฐานข้อมูลทดสอบแยก (สร้างใหม่ทุกครั้ง) · **ปลอมที่ขอบระบบ** (`requests` = LINE/Gemini/Google) ไม่ปลอมฟังก์ชันของเราเอง
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
os.environ.setdefault("DB_HOST", "")
os.environ.setdefault("DEBUG", "True")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.test.runner import DiscoverRunner  # noqa: E402
from django.test.utils import setup_test_environment  # noqa: E402

setup_test_environment()
_runner = DiscoverRunner(verbosity=0, interactive=False)
_old = _runner.setup_databases()
if "testserver" not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]
settings.LINE_CHANNEL_ACCESS_TOKEN = "tok-crm"
settings.LINE_PUSH_CHANNEL_ACCESS_TOKEN = "tok-push"
settings.SITE_URL = "https://oxlet.test"
settings.GEMINI_API_KEY = ""
MEDIA_TMP = tempfile.mkdtemp(prefix="crm_media_")
settings.MEDIA_ROOT = MEDIA_TMP

import requests  # noqa: E402
from django.contrib.sessions.backends.signed_cookies import SessionStore  # noqa: E402
from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402
from django.test import Client  # noqa: E402
from django.utils import timezone  # noqa: E402

import dashboard.services.google_sheets as GS  # noqa: E402
from checkout import connect as C  # noqa: E402
from checkout import crm  # noqa: E402
from checkout import leadflow as LF  # noqa: E402
from checkout.models import (ChatFollowup, ChatLead, ChatOwner, ChatOwnerLog,  # noqa: E402
                             CustomerNeed, Employee, GroupChat, LeadPhone, LineProfile)
from dashboard.services import cache_store  # noqa: E402

C.BG_FILL = False
LF.BG_SLOW = False

# ── ขอบระบบ ─────────────────────────────────────────────────────────
CALLS = []
GEM = {"reply": "", "bodies": []}


class _R:
    def __init__(self, code=200, js=None):
        self.status_code, self._js = code, (js or {})
        self.text = json.dumps(self._js, ensure_ascii=False)
        self.headers = {}

    def json(self):
        return self._js


def _post(url, *a, **k):
    body = k.get("json") or {}
    CALLS.append(("post", url, body))
    if "generativelanguage.googleapis.com" in url:
        GEM["bodies"].append(json.dumps(body, ensure_ascii=False))
        return _R(200, {"candidates": [{"content": {"parts": [{"text": GEM["reply"]}]}}]})
    if "/message/push" in url:
        return _R(200, {"sentMessages": [{"id": "sm-1"}]})
    return _R(200, {})


def _get(url, *a, **k):
    CALLS.append(("get", url, None))
    return _R(404, {"message": "Not found"})


requests.post, requests.get = _post, _get


def _no_sheet(*a, **k):
    raise RuntimeError("ไม่ต่อ Google Sheets ในเทสต์")


GS.fetch_lead_dropdowns = _no_sheet
GS.load_sheet_config_overrides = lambda *a, **k: None

OK, BAD = [], []


def ck(name, cond, got=""):
    (OK if cond else BAD).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else "   ได้: %r" % (got,)))


leak = re.compile(r"U[0-9a-f]{32}")
NOW = timezone.now()
_N = [0]


def emp(nick, pos, day_off=""):
    return Employee.objects.create(nickname=nick, position=pos, day_off=day_off, work_start="9:00")


def cust(name, owner=None, awaiting=False, due_in=None, last_in=None, last_out=None, claimed=None, **lead):
    """ลูกค้า LINE 1 คน + แถว Connect (+ ข้อมูลลีดถ้าส่งมา)"""
    _N[0] += 1
    p = LineProfile.objects.create(user_id="U" + ("%032x" % (0xc00000 + _N[0])), display_name=name, msg_count=3,
                                   first_seen=NOW - timedelta(days=20))
    o = ChatOwner.objects.create(profile=p, owner=owner, claimed_at=claimed or (NOW - timedelta(hours=1) if owner else None),
                                 awaiting_since=(NOW - timedelta(minutes=3)) if awaiting else None,
                                 due_at=(NOW + timedelta(minutes=due_in)) if (awaiting and due_in is not None) else None,
                                 last_in_at=last_in, last_out_at=last_out,
                                 last_at=max([x for x in (last_in, last_out) if x] or [NOW]),
                                 last_dir=("out" if last_out and (not last_in or last_out > last_in) else "in"),
                                 team="A")
    if lead:
        ChatLead.objects.create(chat=o, **lead)
    return ChatOwner.objects.select_related("profile", "fb_profile", "owner", "lead").get(pk=o.pk)


def fresh(o):
    return ChatOwner.objects.select_related("profile", "fb_profile", "owner", "lead").get(pk=o.pk)


def lead(o):
    return ChatLead.objects.filter(chat=o).first()


def client(user):
    cl = Client()
    if user:
        s_ = SessionStore()
        s_["oxlet_user"] = user
        s_.save()
        cl.cookies[settings.SESSION_COOKIE_NAME] = s_.session_key
    return cl


def J(cl, path, body=None):
    r_ = cl.post(path, json.dumps(body), content_type="application/json", secure=True) if body is not None \
        else cl.get(path, secure=True)
    txt = r_.content.decode("utf-8", "replace")
    try:
        return r_.status_code, json.loads(txt), txt
    except Exception:
        return r_.status_code, {}, txt


try:
    # ── พนักงาน + เวร (ทีม A เวรวันนี้) ──
    MAT = emp("มัทซีอาร์เอ็ม", "ทีม A")
    FIRST = emp("เฟิร์สซีอาร์เอ็ม", "ทีม A")
    BIW = emp("บิวซีอาร์เอ็ม", "ทีม B")
    GONE = emp("ลาออกซีอาร์เอ็ม", "ทีม A")
    for e in (MAT, FIRST, BIW, GONE):
        LineProfile.objects.create(user_id="U" + ("%032x" % (0xe00000 + e.id)), display_name=e.nickname,
                                   is_employee=True, employee=e, nickname=e.nickname, channel="push")
    C.save_cfg(dict(C.cfg(), anchor_date=timezone.localdate().isoformat(), anchor_team="A", overrides={}))
    LF.save_cfg(dict(LF.cfg(), rr_teams=["A", "B"], cap_day=12, need_checkin=False))

    # ═════════════════════════════════════════════════════════════════════
    print("[1] ขั้นของลีด — ระบบคิดเอง")
    o_new = cust("ลูกค้าใหม่ 1", awaiting=True, due_in=4, last_in=NOW - timedelta(minutes=3))
    ck("ไม่มีเจ้าของ = ลีดใหม่", crm.stage_of(o_new, lead(o_new)) == "new")
    o_w = cust("ลูกค้ารอติดต่อ", owner=MAT, last_in=NOW - timedelta(hours=2))
    ck("มีเจ้าของ ยังไม่ตอบ = รอติดต่อ", crm.stage_of(o_w, lead(o_w)) == "waiting")
    o_c = cust("ลูกค้าติดต่อแล้ว", owner=MAT, last_in=NOW - timedelta(hours=2), last_out=NOW - timedelta(minutes=30))
    ck("มีเจ้าของ + เราตอบหลังรับ = ติดต่อแล้ว", crm.stage_of(o_c, lead(o_c)) == "contacted")
    o_old = cust("ลูกค้าตอบก่อนรับ", owner=MAT, last_out=NOW - timedelta(hours=5), claimed=NOW - timedelta(hours=1))
    ck("ตอบก่อนรับ (เจ้าของเก่าตอบ) = ยังรอติดต่อ", crm.stage_of(o_old, lead(o_old)) == "waiting")

    print("[2] ตั้งขั้นเอง")
    ok, m = crm.set_stage(o_w, "pool", by="t")
    ck("ตั้ง คืนกองกลาง เองไม่ได้", not ok and "ปุ่มคืนกองกลาง" in m, m)
    ok, m = crm.set_stage(o_w, "lost", by="t")
    ck("ไม่สนใจ ต้องมีเหตุผล", not ok and "เหตุผล" in m, m)
    ok, m = crm.set_stage(o_w, "lost", by="t", reason="เหตุผลมั่ว")
    ck("เหตุผลนอกรายการ = ปฏิเสธ", not ok, m)
    ok, m = crm.set_stage(o_w, "viewing", by="มัท", emp=MAT)
    ck("ตั้ง นัดดูรถ ได้", ok and lead(o_w).stage == "viewing" and lead(o_w).stage_by == "มัท", m)
    lg = ChatOwnerLog.objects.filter(chat=o_w, action=ChatOwnerLog.STAGE).first()
    ck("จดประวัติ เปลี่ยนขั้นลีด", lg and "รอติดต่อ → นัดดูรถ" in lg.note, lg and lg.note)
    ok, m = crm.set_stage(o_w, "lost", by="t", reason="ดาวน์ไม่พอ")
    ck("ไม่สนใจ + เหตุผล", ok and lead(o_w).lost_reason == "ดาวน์ไม่พอ")
    ok, m = crm.set_stage(o_w, "", by="t")
    ck("ตั้งว่าง = กลับให้ระบบคิด (ล้างเหตุผล)", ok and crm.stage_of(fresh(o_w), lead(o_w)) == "waiting"
       and lead(o_w).lost_reason == "", (m, lead(o_w).lost_reason))

    print("[3] เลื่อนขั้นอัตโนมัติ (ไม่ถอยหลัง · ไม่แตะเคสปิด)")
    o_b = cust("ลูกค้าเลื่อนขั้น", owner=MAT)
    ck("รอติดต่อ → ติดต่อแล้ว", crm.bump(o_b, "contacted") and lead(o_b).stage == "contacted")
    ck("ติดต่อแล้ว → ไม่ถอยไปรอติดต่อ", not crm.bump(fresh(o_b), "waiting"))
    crm.set_stage(fresh(o_b), "won", by="t")
    ck("ปิดการขายแล้ว ไม่ถูกเลื่อนเป็นนัดดูรถ", not crm.bump(fresh(o_b), "viewing") and lead(o_b).stage == "won")

    print("[4] คืนกองกลาง / รับ / โอน")
    o_p = cust("ลูกค้าคืนกอง", owner=MAT, awaiting=True, due_in=4, last_in=NOW)
    ok, m = crm.release_by_owner(fresh(o_p), MAT, by="มัท", reason="ลูกค้าอยู่ต่างจังหวัด")
    o_p = fresh(o_p)
    ck("เซลล์คืนกองกลาง → ไม่มีเจ้าของ + ขั้นคืนกองกลาง", ok and not o_p.owner_id and lead(o_p).stage == "pool", m)
    rl = ChatOwnerLog.objects.filter(chat=o_p, action=ChatOwnerLog.RELEASE).first()
    ck("จดว่าเซลล์คืนเพราะอะไร", rl and "เซลล์คืนกองกลาง" in rl.note and "ต่างจังหวัด" in rl.note, rl and rl.note)
    ok, m = C.claim(o_p.id, FIRST)
    o_p = fresh(o_p)
    ck("มีคนรับใหม่ → ขั้นกลับให้ระบบคิด (รอติดต่อ)", ok and lead(o_p).stage == "" and
       crm.stage_of(o_p, lead(o_p)) == "waiting", (m, lead(o_p).stage))
    C.assign(o_p.id, None, by="แอดมิน")
    ck("แอดมินปล่อยคืนคิว → คืนกองกลาง", lead(o_p).stage == "pool")
    C.assign(o_p.id, BIW, by="แอดมิน")
    ck("แอดมินโอน → ล้างคืนกองกลาง", lead(o_p).stage == "")
    crm.set_stage(fresh(o_p), "won", by="t")
    C.assign(o_p.id, None, by="แอดมิน")
    ck("ปิดการขายแล้วปล่อยคืนคิว = ยังเป็นปิดการขาย", lead(o_p).stage == "won")

    print("[5] ความร้อน")
    o_h = cust("ลูกค้าร้อน", owner=MAT, last_in=NOW - timedelta(hours=3), lead_type="Very Hot",
               customer_status="สนใจมาก", phone="0812223344")
    h = crm.heat_of(o_h, lead(o_h))
    ck("Very Hot + สนใจมาก + คุยวันนี้ + มีเบอร์ = ร้อน", h["key"] == "hot" and h["score"] >= 60, h)
    o_d = cust("ลูกค้าเคสเสีย", owner=MAT, last_in=NOW, lead_type="Very Hot", customer_status="ลูกค้าไม่สนใจแล้ว")
    ck("สถานะลูกค้าเป็นเคสเสีย = เย็น", crm.heat_of(o_d, lead(o_d))["key"] == "cold")
    o_s = cust("ลูกค้าเงียบนาน", owner=MAT, last_in=NOW - timedelta(days=20), lead_type="Moderate")
    ck("เงียบ 20 วัน = เย็น", crm.heat_of(o_s, lead(o_s))["key"] == "cold")
    ck("เคสปิดแล้ว = ไม่มีความร้อน", crm.heat_of(fresh(o_b), lead(o_b))["key"] == "")

    # ═════════════════════════════════════════════════════════════════════
    print("[6] นัดหมาย")
    o_a = cust("ลูกค้านัด", owner=MAT, last_in=NOW - timedelta(hours=1), last_out=NOW - timedelta(minutes=10))
    ok, m, f = crm.add_followup(o_a, "follow", "", by="มัท", emp=MAT)
    ck("ไม่มีวันเวลา = ปฏิเสธ", not ok, m)
    ok, m, f = crm.add_followup(o_a, "follow", (NOW - timedelta(days=3)).isoformat(), by="มัท")
    ck("วันที่ผ่านไปแล้ว = ปฏิเสธ", not ok, m)
    ok, m, f = crm.add_followup(o_a, "boom", (NOW + timedelta(hours=1)).isoformat())
    ck("ชนิดมั่ว = ปฏิเสธ", not ok)
    soon = timezone.localtime(NOW + timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M")
    ok, m, f1 = crm.add_followup(o_a, "follow", soon, note="ถามเรื่องดาวน์", by="มัท", emp=MAT)
    ck("นัดติดตาม (เวลาไทยไม่มีโซน)", ok and f1.employee_id == MAT.id and f1.note == "ถามเรื่องดาวน์", m)
    ck("นัดติดตามไม่เปลี่ยนขั้น", crm.stage_of(fresh(o_a), lead(o_a)) == "contacted")
    ok, m, f2 = crm.add_followup(o_a, "viewing", (NOW + timedelta(days=1)).isoformat(), by="มัท", emp=MAT)
    ck("นัดดูรถ → ขั้นเป็นนัดดูรถ", ok and lead(o_a).stage == "viewing")
    ck("แผนที่นัดถัดไป = นัดที่ใกล้สุด", crm.next_appt_map([o_a.id])[o_a.id][0] == "follow")
    ok, m = crm.done_followup(o_a, f1.id, by="มัท", result="ลูกค้าโอเค")
    ck("ทำแล้ว", ok and ChatFollowup.objects.get(pk=f1.id).done_at is not None)
    ok, m = crm.done_followup(o_a, f2.id, by="มัท", cancel=True, result="ลูกค้าเลื่อน")
    ck("ยกเลิกนัด = ผลขึ้นต้นด้วยยกเลิก", ok and ChatFollowup.objects.get(pk=f2.id).result.startswith("ยกเลิกนัด"))
    ck("นัดของลูกค้าคนอื่นแก้ไม่ได้", not crm.done_followup(o_w, f1.id)[0])
    ck("ไม่มีนัดค้าง → แผนที่ว่าง", o_a.id not in crm.next_appt_map([o_a.id]))
    fj = crm.followups_json(fresh(o_a))
    ck("รายการนัด: ทำแล้วยังโชว์ (4 ล่าสุด)", len(fj) == 2 and all(x["done"] for x in fj), fj)

    # ═════════════════════════════════════════════════════════════════════
    print("[7] หลักฐานการโทร (อัปรูป)")
    o_k = cust("ลูกค้าโทร", owner=MAT, last_in=NOW - timedelta(hours=2), phone="0811112222")
    ok, r = crm.save_proof(o_k, SimpleUploadedFile("x.pdf", b"%PDF", content_type="application/pdf"))
    ck("ไม่ใช่รูป = ปฏิเสธ", not ok, r)
    big = SimpleUploadedFile("big.jpg", b"0" * 10, content_type="image/jpeg")
    big.size = (crm.PROOF_MAX_MB + 1) * 1024 * 1024
    ok, r = crm.save_proof(o_k, big)
    ck("ใหญ่เกิน = ปฏิเสธ", not ok, r)
    ok, r = crm.save_proof(o_k, SimpleUploadedFile("call.JPG", b"\xff\xd8\xff\xe0fake", content_type="image/jpeg"))
    ck("รูปเก็บที่ connect/<ลูกค้า>/ชื่อสุ่ม.jpg", ok and r["id"].startswith("connect/%d/" % o_k.id)
       and r["id"].endswith(".jpg") and "call" not in r["id"] and os.path.exists(os.path.join(MEDIA_TMP, r["id"])), r)
    ck("ลิงก์รูป = /media/…", r["url"].startswith("/media/connect/"), r)
    proof = r["id"]

    print("[8] บันทึกการโทร")
    ok, m, c0 = crm.add_call(o_k, "", by="มัท")
    ck("ไม่เลือกผล = ปฏิเสธ", not ok)
    other = cust("ลูกค้าคนอื่น", owner=BIW)
    ok2, r2 = crm.save_proof(other, SimpleUploadedFile("o.png", b"\x89PNG", content_type="image/png"))
    ok, m, c1 = crm.add_call(o_k, "noans", note="โทร 2 ครั้ง", media=[{"id": proof}, {"id": r2["id"]},
                                                                        {"id": "connect/%d/../../etc" % o_k.id}],
                             by="มัท", emp=MAT)
    ck("รับเฉพาะรูปของลูกค้าคนนี้ (กันอ้างไฟล์คนอื่น/../)", ok and c1.media == [{"id": proof}], c1.media)
    ck("ไม่รับสาย ไม่เลื่อนขั้น", crm.stage_of(fresh(o_k), lead(o_k)) == "waiting")
    ck("แนบหลักฐาน → แจ้งหลักฐานการโทร = ส่งแล้ว (จากบันทึกการโทร)",
       lead(o_k).call_proof == "ส่งแล้ว" and (lead(o_k).auto or {}).get("call_proof") == "บันทึกการโทร")
    ok, m, c2 = crm.add_call(fresh(o_k), "ok", note="คุยแล้ว สนใจ City", by="มัท", emp=MAT)
    ck("คุยได้ → ติดต่อแล้ว", ok and lead(o_k).stage == "contacted")
    cl = crm.calls_json(fresh(o_k))
    ck("รายการโทร ใหม่→เก่า + ลิงก์รูป", [x["result"] for x in cl] == ["ok", "noans"]
       and cl[1]["media"][0]["url"].startswith("/media/connect/"), cl)
    ck("จดประวัติ บันทึกการโทร", ChatOwnerLog.objects.filter(chat=o_k, action=ChatOwnerLog.CALL).count() == 2)
    o_hp = cust("ลูกค้าคนตั้งหลักฐานเอง", owner=MAT, call_proof="ยังไม่ส่ง")
    lp = lead(o_hp)
    lp.auto = {"call_proof": C.HUMAN}
    lp.save()
    pr2 = crm.save_proof(o_hp, SimpleUploadedFile("a.jpg", b"\xff\xd8", content_type="image/jpeg"))[1]["id"]
    crm.add_call(fresh(o_hp), "ok", media=[{"id": pr2}], by="มัท", emp=MAT)
    ck("ช่องที่คนตั้งเองไม่ถูกทับ", lead(o_hp).call_proof == "ยังไม่ส่ง")

    print("[9] ลบหลักฐานของลูกค้าที่ถูกลบ")
    gone_id = other.id
    other.delete()
    n = crm.cleanup_files()
    ck("โฟลเดอร์ของลูกค้าที่ถูกลบ หายไป · ของคนที่ยังอยู่ไม่โดน",
       n == 1 and not os.path.exists(os.path.join(MEDIA_TMP, "connect", str(gone_id)))
       and os.path.exists(os.path.join(MEDIA_TMP, proof)), n)

    print("[10] ใครเคยดูแล")
    o_hist = cust("ลูกค้าหลายมือ", awaiting=True, due_in=4, last_in=NOW)
    C.claim(o_hist.id, MAT)
    C.assign(o_hist.id, FIRST, by="แอดมิน")
    C.assign(o_hist.id, None, by="แอดมิน")
    C.assign(o_hist.id, GONE, by="แอดมิน")
    GONE.active = False
    GONE.save()
    po = crm.past_owners(fresh(o_hist))
    ck("ช่วงดูแล ใหม่→เก่า: ลาออก (ยังดูแล) · เฟิร์ส (คืนคิว) · มัท (โอนต่อ)",
       [x["name"] for x in po] == [GONE.nickname, FIRST.nickname, MAT.nickname]
       and po[0]["to"] == "" and po[1]["end"] == "แอดมินปล่อยคืนคิว" and po[2]["end"] == "โอนต่อ", po)
    GONE.delete()
    po = crm.past_owners(fresh(o_hist))
    ck("★ ลบพนักงานแล้วชื่อยังอยู่ในประวัติ", po and po[0]["name"] == "ลาออกซีอาร์เอ็ม", po)

    # ═════════════════════════════════════════════════════════════════════
    print("[11] ตัวกรองรายชื่อ")
    cache_store.set_kv(LF.KV_NEEDS, {"at": "x", "bySeller": {"มัทซีอาร์เอ็ม": [
        {"code": "NLD10-5001", "cars": [{"code": "CS1", "name": "Honda City", "price": 450000, "year": 2021}]}]}})
    crm._MT.update(at=0.0, map={})
    o_m = cust("ลูกค้ารถตรง", owner=MAT, last_in=NOW - timedelta(days=1), code="NLD10-5001", car_text="City ปี 21")
    o_nr = cust("ลูกค้าไม่ตอบกลับ", owner=MAT, last_in=NOW - timedelta(days=4), last_out=NOW - timedelta(days=2))
    o_s7 = cust("ลูกค้าเงียบ 8 วัน", owner=MAT, last_in=NOW - timedelta(days=8), last_out=NOW - timedelta(days=8))
    CustomerNeed.objects.create(profile=o_m.profile, car_model="City", budget_max=450000)

    def ids(**f):
        return {r["id"] for r in C.inbox("all", admin=True, flt=f)}

    ck("ขั้น = นัดดูรถ", ids(stage="viewing") == {o_a.id} or o_a.id in ids(stage="viewing"), ids(stage="viewing"))
    ck("ขั้น = ไม่สนใจ ไม่มีใคร (ตั้งกลับแล้ว)", o_w.id not in ids(stage="lost"))
    ck("ความร้อน = ร้อน มีลูกค้าร้อน", o_h.id in ids(heat="hot") and o_d.id not in ids(heat="hot"))
    ck("รอเราตอบ", o_new.id in ids(awaiting="1") and o_w.id not in ids(awaiting="1"))
    ck("ลูกค้าไม่ตอบกลับ (เราส่งล่าสุด >24 ชม.)", o_nr.id in ids(noreply="1") and o_c.id not in ids(noreply="1"))
    s7 = ids(silent="7")
    ck("เงียบ 7+ วัน", o_s7.id in s7 and o_nr.id not in s7 and o_s.id in s7, s7)
    ck("เงียบ — ตัดเคสปิดแล้ว", o_b.id not in ids(silent="3"))
    ck("รถใหม่ตรง", ids(carmatch="1") == {o_m.id}, ids(carmatch="1"))
    ck("รุ่นรถ (ค้นในรถที่ถาม/CAR)", ids(car="city") == {o_m.id})
    ck("ช่วงราคา (งบที่ลูกค้าบอก)", ids(pmin="400000", pmax="500000") == {o_m.id} and not ids(pmax="300000"))
    crm.add_followup(o_c, "follow", timezone.localtime(NOW + timedelta(minutes=5)).isoformat(), by="t", emp=MAT)
    ck("ต้องติดตามวันนี้", o_c.id in ids(follow="today") and o_new.id not in ids(follow="today"))
    yday = (timezone.localdate() - timedelta(days=15)).isoformat()
    ck("ช่วงวันที่ (ข้อความล่าสุด)", o_s.id in ids(dto=yday) and o_new.id not in ids(dto=yday))
    crm.set_stage(fresh(o_w), "lost", by="t", reason="ซื้อที่อื่นแล้ว")
    ck("เหตุผลที่ไม่ซื้อ", ids(reason="ซื้อที่อื่นแล้ว") == {o_w.id})
    rows = C.inbox("all", admin=True)
    rm = next(r for r in rows if r["id"] == o_m.id)
    ck("แถวรายชื่อมี ขั้น/ความร้อน/เงียบ/รถตรง", rm["stage"] == "waiting" and rm["heat"] and rm["carMatch"] == 1
       and rm["silentDays"] == 1, rm)
    rc = next(r for r in rows if r["id"] == o_c.id)
    ck("แถวรายชื่อมีนัดถัดไป", (rc.get("appt") or {}).get("kind") == "follow", rc.get("appt"))
    ck("คิวเซลล์ (mine) ใช้ตัวกรองได้", {r["id"] for r in C.inbox("mine", me=MAT, flt={"stage": "contacted"})}
       >= {o_c.id})

    # ═════════════════════════════════════════════════════════════════════
    print("[12] Run Auto")
    ChatOwner.objects.filter(owner__isnull=True, awaiting_since__isnull=False).update(awaiting_since=None)
    q1 = cust("คิว 1", awaiting=True, due_in=1, last_in=NOW)
    q2 = cust("คิว 2", awaiting=True, due_in=2, last_in=NOW)
    q3 = cust("คิว 3", awaiting=True, due_in=3, last_in=NOW, phone="0815550001")
    qs = cust("คิวจำลอง", awaiting=True, due_in=4, last_in=NOW)
    qs.profile.user_id = C.SIM_PREFIX + "x1"
    qs.profile.save()
    LeadPhone.objects.create(phone="0815550001", code="NLD9-4001", seller=BIW.nickname, source="sheet")
    r = crm.run_auto(by="แอดมิน")
    to = {a["id"]: a["to"] for a in r["assigned"]}
    ck("จ่าย 3 คน · ข้ามลูกค้าจำลอง", len(r["assigned"]) == 3 and any(s["id"] == qs.id for s in r["skipped"]), r)
    ck("★ เบอร์เคยเป็นลีดของบิว → ส่งกลับบิว", to.get(q3.id) == BIW.nickname, to)
    ck("จ่ายวนเฉลี่ย (คิว 1/2 ไม่ไปคนเดียวกัน)", to.get(q1.id) != to.get(q2.id), to)
    lg = ChatOwnerLog.objects.filter(chat=q1, action=ChatOwnerLog.ASSIGN).first()
    ck("ประวัติจดว่า Run Auto", lg and lg.note.startswith("Run Auto"), lg and lg.note)
    ck("ไม่ส่งอะไรเข้า LINE", not [c for c in CALLS if "/message/push" in c[1]])
    before = crm._auto_today()
    q4 = cust("คิว 4", awaiting=True, due_in=1, last_in=NOW)
    r = crm.run_auto(by="แอดมิน")
    least = min(before.items(), key=lambda kv: kv[1])[0] if before else None
    ck("รอบสอง: นับที่จ่ายไปแล้ววันนี้ด้วย", r["assigned"] and r["assigned"][0]["id"] == q4.id, (r, before, least))
    LF.save_cfg(dict(LF.cfg(), rr_teams=["Z"]))
    q5 = cust("คิว 5", awaiting=True, due_in=1, last_in=NOW)
    r = crm.run_auto(by="แอดมิน")
    ck("ไม่มีเซลล์ในคิวจ่ายวน = ข้ามพร้อมเหตุผล", not r["assigned"] and "คิวจ่ายวน" in r["skipped"][0]["why"], r)
    LF.save_cfg(dict(LF.cfg(), rr_teams=["A", "B"]))
    r = crm.run_auto(by="แอดมิน", ids=[q5.id, q1.id])
    ck("ระบุ id = จ่ายเฉพาะคนที่ยังไม่มีเจ้าของ", [a["id"] for a in r["assigned"]] == [q5.id], r)

    # ═════════════════════════════════════════════════════════════════════
    print("[13] ดึงคืนเมื่อไม่ตอบ (ปิดโดยปริยาย)")
    pu = cust("ลูกค้าไม่ได้ตอบ", owner=MAT, awaiting=True, due_in=-5, last_in=NOW - timedelta(minutes=30),
              claimed=NOW - timedelta(minutes=40))
    replied = cust("ลูกค้าตอบแล้ว", owner=MAT, awaiting=True, due_in=-5, last_in=NOW - timedelta(minutes=8),
                   last_out=NOW - timedelta(minutes=20), claimed=NOW - timedelta(minutes=40))
    ck("ค่าตั้งต้น pull_min = 0 (ปิด)", C.cfg()["pull_min"] == 0)
    crm.tick()
    ck("ปิดอยู่ = ไม่ดึงใคร", fresh(pu).owner_id == MAT.id)
    _c, errs = C.clean_cfg({"pull_min": 2})
    ck("ตั้ง 2 นาที = ฟ้อง (5–240)", errs and "5–240" in errs[0], errs)
    C.save_cfg(dict(C.cfg(), pull_min=15))
    out = crm.tick()
    ck("เกิน 15 นาทีหลังรับ + เลยเส้นตาย + ยังไม่ตอบ → คืนคิว", not fresh(pu).owner_id and out.get("pulled") == 1, out)
    ck("ตอบไปแล้วหลังรับ = ไม่ดึง", fresh(replied).owner_id == MAT.id)
    lg = ChatOwnerLog.objects.filter(chat=pu, action=ChatOwnerLog.RELEASE).first()
    ck("จดว่าระบบดึงคืนเพราะไม่ตอบ + ชื่อเจ้าของเดิม", lg and "ไม่ตอบภายใน 15 นาที" in lg.note and MAT.nickname in lg.note)
    C.save_cfg(dict(C.cfg(), pull_min=0))

    # ═════════════════════════════════════════════════════════════════════
    print("[14] แจ้งเตือน")
    ov = cust("ลูกค้าเลยเวลา", owner=FIRST, awaiting=True, due_in=-3, last_in=NOW - timedelta(minutes=8))
    cust("ลูกค้าใกล้หมด", owner=FIRST, awaiting=True, due_in=1, last_in=NOW)
    qn = cust("ลูกค้ารอรับใหม่", awaiting=True, due_in=4, last_in=NOW)
    crm.add_followup(ov, "viewing", (NOW + timedelta(minutes=30)).isoformat(), by="t", emp=FIRST)
    crm.add_followup(o_c, "follow", (NOW - timedelta(minutes=30)).isoformat(), by="t", emp=MAT)
    a = crm.alerts(FIRST, False)
    kinds = [x["kind"] for x in a["items"]]
    ck("เซลล์เวรวันนี้: ลูกค้าใหม่รอรับ", "queue" in kinds, kinds)
    ck("เลยเวลา + ใกล้หมดเวลา (ของตัวเอง)", "overdue" in kinds and "soon" in kinds, kinds)
    ck("นัดวันนี้ของตัวเอง", any(x["kind"] == "appt" and x["id"] == ov.id for x in a["items"]))
    ck("ไม่เห็นนัดของคนอื่น", not any(x["kind"] == "appt" and x["id"] == o_c.id for x in a["items"]))
    am = crm.alerts(MAT, False)
    ck("นัดเลยเวลา = แดง", any(x["kind"] == "appt" and x["level"] == "err" and x["id"] == o_c.id for x in am["items"]),
       am["items"])
    ck("ลูกค้าเงียบ 7+ วัน (มีตัวกรองติดมา)", any(x["kind"] == "silent" and x["filter"] == {"silent": "7"}
                                              for x in am["items"]), am["items"])
    ck("รถใหม่ตรงลูกค้าของฉัน", any(x["kind"] == "match" and x["n"] == 1 for x in am["items"]))
    ab = crm.alerts(BIW, False)
    ck("ทีม B (ไม่ใช่วันเวร) ไม่เห็นคิวรอรับ", "queue" not in [x["kind"] for x in ab["items"]])
    aa = crm.alerts(None, True)
    ck("แอดมิน: คิว + นัดทั้งหมดพร้อมชื่อเซลล์", "queue" in [x["kind"] for x in aa["items"]]
       and any(x["kind"] == "appt" and "@" in x["text"] for x in aa["items"]), aa["items"])
    ck("แอดมิน: ไม่โชว์เลยเวลารายคน (ทีมตอบในแอป LINE OA)", "overdue" not in [x["kind"] for x in aa["items"]])

    # ═════════════════════════════════════════════════════════════════════
    print("[15] AI สรุปแชท (Gemini ปลอมที่ requests)")
    o_ai = cust("ลูกค้าเอไอ", owner=MAT, last_in=NOW - timedelta(hours=1), car_text="City")
    for i, (d_, t_) in enumerate([("in", "สนใจ City ปี 21 ครับ เบอร์ 081-999-8877 ไลน์ไอดี somchai99"),
                                   ("out", "ได้ครับ ดาวน์ได้เท่าไหร่ครับ"), ("in", "ดาวน์ 30,000 ผ่อนไม่เกิน 8,000")]):
        GroupChat.objects.create(chat_type=GroupChat.USER, message_id="m-ai-%d" % i, sender_id=o_ai.profile.user_id,
                                 text=t_, msg_type="text", direction=d_, sent_at=NOW - timedelta(minutes=30 - i))
    ok, m = crm.ai_draft(o_ai, C.messages(o_ai))
    ck("ไม่มีคีย์ = บอกตรงๆ ไม่ยิงเน็ต", not ok and "GEMINI_API_KEY" in m and not GEM["bodies"], m)
    settings.GEMINI_API_KEY = "fake-key"
    GEM["reply"] = '```json\n{"summary": "หา City ปี 21 ดาวน์ 3 หมื่น ผ่อน 8 พัน", "stage": "contacted",' \
                   ' "stage_reason": "คุยรายละเอียดแล้ว", "follow_in_days": 2, "follow_note": "เสนอรถที่ตรงงบ"}\n```'
    ok, d = crm.ai_draft(o_ai, C.messages(o_ai))
    ck("ร่างสรุป + ขั้นแนะนำ + วันติดตาม", ok and d["stage"] == "contacted" and d["followDays"] == 2
       and d["followAt"].endswith("T10:00") and "City" in d["summary"], d)
    sent = GEM["bodies"][-1]
    ck("★ ปิดบังเบอร์/ไอดีไลน์ก่อนส่ง AI", "999-8877" not in sent and "0819998877" not in sent and "somchai99" not in sent
       and "[เบอร์]" in sent and "[ไอดี]" in sent, sent[:300])
    ck("ร่างแล้วไม่บันทึกเอง", not lead(o_ai).summary)
    n_req = len(GEM["bodies"])
    crm.ai_draft(o_ai, C.messages(o_ai))
    ck("แชทเดิม = ใช้ผลเดิม ไม่ยิงซ้ำ (30 นาที)", len(GEM["bodies"]) == n_req)
    GEM["reply"] = '{"summary": "x", "stage": "pool", "follow_in_days": 99}'
    GroupChat.objects.create(chat_type=GroupChat.USER, message_id="m-ai-9", sender_id=o_ai.profile.user_id,
                             text="ขอบคุณครับ", msg_type="text", direction="in", sent_at=NOW)
    ok, d = crm.ai_draft(o_ai, C.messages(o_ai))
    ck("ขั้นที่ตั้งไม่ได้ = ว่าง · วันติดตามไม่เกิน 30", ok and d["stage"] == "" and d["followDays"] == 30, d)
    GEM["reply"] = "ขอโทษครับ ตอบไม่ได้"
    GroupChat.objects.create(chat_type=GroupChat.USER, message_id="m-ai-10", sender_id=o_ai.profile.user_id,
                             text="ยังอยู่ไหม", msg_type="text", direction="in", sent_at=NOW)
    ok, m = crm.ai_draft(o_ai, C.messages(o_ai))
    ck("AI ตอบไม่เป็น JSON = บอกว่าไม่สำเร็จ", not ok and "ไม่สำเร็จ" in m, m)
    ok, m = crm.save_summary(o_ai, "หา City ปี 21 · ดาวน์ 3 หมื่น", by="มัท", emp=MAT)
    ck("บันทึกสรุป (เซลล์กดเอง) + จดประวัติ", ok and lead(o_ai).summary.startswith("หา City")
       and ChatOwnerLog.objects.filter(chat=o_ai, action=ChatOwnerLog.SUMMARY).exists())
    ck("สรุปยาวเกิน = ปฏิเสธ", not crm.save_summary(o_ai, "x" * 2001)[0])

    # ═════════════════════════════════════════════════════════════════════
    print("[16] เตือนนัดทาง LINE (ปิดโดยปริยาย)")
    CALLS.clear()
    crm.tick()
    ck("ปิดอยู่ = ไม่ส่ง", not [c for c in CALLS if "/message/push" in c[1]])
    C.save_cfg(dict(C.cfg(), appt_line=True))
    crm.tick()
    p1 = [c for c in CALLS if "/message/push" in c[1]]
    txt = json.dumps([c[2] for c in p1], ensure_ascii=False)
    # นัดที่อยู่ในช่วง 30 นาที = นัดติดตาม (+5 นาที · [11]) + นัดดูรถ (+30 นาที · [14]) · นัดที่เลยไป 30 นาทีไม่เตือน
    ck("เปิดแล้ว: เตือนนัดที่ใกล้ถึง (30 นาที) เข้าแชทส่วนตัวเซลล์ของคนที่ต้องทำ", len(p1) == 2
       and "นัดดูรถ" in txt and "นัดติดตาม" in txt and "/connect/?id=" in txt, txt)
    crm.tick()
    ck("รอบถัดไปไม่เตือนซ้ำ", len([c for c in CALLS if "/message/push" in c[1]]) == 2)
    C.save_cfg(dict(C.cfg(), appt_line=False))

    # ═════════════════════════════════════════════════════════════════════
    print("[17] วิเคราะห์ + รายชื่อไม่ต้องการ")
    lw = lead(o_w)
    lw.phone, lw.channel = "0899990000", "LINE@"
    lw.save()
    ins = crm.insights(60)
    st_ = {x["key"]: x["n"] for x in ins["stages"]}
    ck("นับตามขั้น", st_.get("lost", 0) >= 1 and st_.get("won", 0) >= 1, st_)
    ck("เหตุผลที่ไม่ซื้อ", any(x["reason"] == "ซื้อที่อื่นแล้ว" for x in ins["lost"]), ins["lost"])
    ck("ตามช่องทาง (มี LINE@)", any(s["src"] == "LINE@" and s["lost"] == 1 for s in ins["sources"]), ins["sources"])
    ck("นับคนไม่ต้องการ (ไม่สนใจ + เคสเสีย)", ins["unwanted"] >= 2, ins["unwanted"])
    csv_ = crm.unwanted_csv(60).decode("utf-8")
    ck("CSV มี BOM + หัวตาราง + เบอร์ลูกค้าไม่สนใจ", csv_.startswith("﻿ชื่อลูกค้า") and "0899990000" in csv_
       and "ลูกค้าเคสเสีย" in csv_)
    ck("CSV ไม่มีลูกค้าที่ยังสนใจ", "ลูกค้าร้อน" not in csv_)

    # ═════════════════════════════════════════════════════════════════════
    print("[17b] สถานะไฟแนนซ์จากชีตยอดขาย — อ่านเฉพาะผลที่ cron อุ่นไว้ ห้ามคำนวณสด")
    import dashboard.services.fetch_dashboard as FD
    _pre = FD.precompute_dashboard
    LIVE = []
    FD.precompute_dashboard = lambda *a, **k: LIVE.append(1) or {}
    try:
        crm._BK.update(at=0.0, map={})
        FD._dash_cache.update(data=None, ts=0)
        ck("ไม่มีผลที่อุ่นไว้ = ไม่มีสถานะไฟแนนซ์ (ไม่คำนวณสด)", crm.booking_of("NLD10-5001") is None and not LIVE, LIVE)
        FD._dash_cache.update(data={"bookingCases": [{"leadCode": "NLD10-5001", "status": "รอผล", "car": "City",
                                                       "date": "1/10/2026", "price": 459000}]}, ts=0)
        crm._BK.update(at=0.0, map={})
        bk = crm.booking_of("RNLD10-5001/1")
        ck("มีผลที่อุ่นไว้ = เจอเคสจอง (ไม้ 2 ใช้เลขเดิม)", bk and bk["status"] == "รอผล" and bk["price"] == 459000, bk)
        ck("ยังไม่คำนวณสดเลยสักครั้ง", not LIVE)
    finally:
        FD.precompute_dashboard = _pre
        FD._dash_cache.update(data=None, ts=0)
        crm._BK.update(at=0.0, map={})

    # ═════════════════════════════════════════════════════════════════════
    print("[18] API + สิทธิ์")
    ADM = client({"user_id": "admin", "nickname": "admin", "position": "admin"})
    SM = client({"user_id": "U" + "1" * 32, "nickname": MAT.nickname, "seller_name": MAT.nickname, "position": "seller"})
    SB = client({"user_id": "U" + "2" * 32, "nickname": BIW.nickname, "seller_name": BIW.nickname, "position": "seller"})
    NOB = client(None)
    s_, d, raw = J(SM, "/connect/api/inbox?view=mine&stage=contacted")
    ck("เซลล์กรองขั้นผ่าน API", s_ == 200 and o_c.id in {r["id"] for r in d["rows"]}
       and all(r["stage"] == "contacted" for r in d["rows"]), (s_, d.get("error")))
    ck("ตัวเลือกตัวกรองมากับรายชื่อ", len(d["crm"]["stages"]) == 8 and d["crm"]["lostReasons"])
    ck("★ ไม่มี LINE user id หลุดในรายชื่อ", not leak.search(raw))
    s_, d, raw = J(SM, "/connect/api/chat?id=%d" % o_k.id)
    cr = d.get("crm") or {}
    ck("เปิดแชท: รายละเอียด หน้ารวมแชท (นัด/โทร/ใครเคยดูแล/ขั้น)", s_ == 200 and cr.get("calls") and "followups" in cr
       and cr.get("extra", {}).get("stage") == "contacted" and len(cr.get("stages")) == 6, (s_, d.get("crmError")))
    ck("เซลล์เจ้าของ: ปุ่มคืนกองกลาง", d.get("canRelease") is True)
    ck("★ ไม่มี LINE user id หลุดในแชท", not leak.search(raw))
    s_, d, _ = J(SB, "/connect/api/crm", {"action": "stage", "id": o_k.id, "stage": "won"})
    ck("เซลล์คนอื่นเปลี่ยนขั้นไม่ได้ (403)", s_ == 403, (s_, d))
    s_, d, _ = J(SM, "/connect/api/crm", {"action": "stage", "id": o_k.id, "stage": "finance"})
    ck("เจ้าของเปลี่ยนขั้นได้ + ได้แถวใหม่กลับ", s_ == 200 and d["row"]["stage"] == "finance"
       and d["crm"]["extra"]["stage"] == "finance", d)
    s_, d, _ = J(SM, "/connect/api/crm", {"action": "followup", "id": o_k.id, "kind": "viewing",
                                         "due": timezone.localtime(NOW + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"),
                                         "note": "มาดู City"})
    ck("นัดผ่าน API", s_ == 200 and d["crm"]["followups"][0]["note"] == "มาดู City", d)
    fid = d["crm"]["followups"][0]["id"]
    s_, d, _ = J(SM, "/connect/api/crm", {"action": "followup_done", "id": o_k.id, "fid": fid, "result": "มาแล้ว"})
    ck("ปิดนัดผ่าน API", s_ == 200 and d["crm"]["followups"][0]["done"], d)
    up = SM.post("/connect/api/upload", {"id": o_k.id, "file": SimpleUploadedFile(
        "p.png", b"\x89PNG\r\n", content_type="image/png")}, secure=True)
    uj = json.loads(up.content.decode("utf-8"))
    ck("อัปรูปหลักฐานผ่าน API (เจ้าของ)", up.status_code == 200 and uj["id"].startswith("connect/%d/" % o_k.id), uj)
    up2 = SB.post("/connect/api/upload", {"id": o_k.id, "file": SimpleUploadedFile(
        "p.png", b"\x89PNG", content_type="image/png")}, secure=True)
    ck("อัปรูปให้ลูกค้าคนอื่นไม่ได้ (403)", up2.status_code == 403)
    s_, d, _ = J(SM, "/connect/api/crm", {"action": "call", "id": o_k.id, "result": "ok", "note": "นัดมาดูแล้ว",
                                         "media": [{"id": uj["id"]}]})
    ck("บันทึกการโทรผ่าน API + รูป", s_ == 200 and d["crm"]["calls"][0]["media"], d)
    s_, d, _ = J(SM, "/connect/api/crm", {"action": "summary", "id": o_k.id, "text": "สรุปทดสอบ"})
    ck("บันทึกสรุปผ่าน API", s_ == 200 and d["crm"]["summary"] == "สรุปทดสอบ")
    s_, d, _ = J(SM, "/connect/api/crm", {"action": "ai", "id": o_ai.id})
    ck("AI ร่าง (แชทไม่มีข้อความใหม่ = ผลเดิม หรือ error ภาษาคน)", s_ in (200, 400) and ("draft" in d or d.get("error")), d)
    s_, d, _ = J(SM, "/connect/api/crm", {"action": "run_auto"})
    ck("เซลล์ Run Auto ไม่ได้ (403)", s_ == 403)
    rq = cust("คิว API", awaiting=True, due_in=2, last_in=NOW)
    s_, d, _ = J(ADM, "/connect/api/crm", {"action": "run_auto", "ids": [rq.id]})
    ck("แอดมิน Run Auto ผ่าน API", s_ == 200 and d["assigned"] and d["assigned"][0]["id"] == rq.id, d)
    s_, d, _ = J(SM, "/connect/api/crm", {"action": "boom", "id": o_k.id})
    ck("คำสั่งมั่ว = 400", s_ == 400)
    s_, d, _ = J(SM, "/connect/api/crm", {"action": "release", "id": o_k.id, "reason": "ลูกค้าย้ายจังหวัด"})
    ck("เซลล์คืนกองกลางผ่าน API → ขั้นคืนกองกลาง · ไม่ส่งรายละเอียดลูกค้าต่อ", s_ == 200 and "crm" not in d
       and not d["row"]["owner"] and d["row"]["stage"] == "pool", d)
    s_, d, _ = J(SM, "/connect/api/crm", {"action": "stage", "id": o_k.id, "stage": "won"})
    ck("คืนแล้วแก้ต่อไม่ได้ (403)", s_ == 403)
    s_, d, raw = J(SM, "/connect/api/alerts")
    ck("แจ้งเตือนผ่าน API", s_ == 200 and isinstance(d.get("items"), list) and not leak.search(raw), (s_, d))
    s_, d, raw = J(ADM, "/connect/api/insights?days=60")
    ck("วิเคราะห์ (แอดมิน)", s_ == 200 and d.get("stages") and not leak.search(raw), s_)
    s_, d, _ = J(SM, "/connect/api/insights")
    ck("เซลล์เปิดวิเคราะห์ไม่ได้ (403)", s_ == 403)
    r_ = ADM.get("/connect/api/insights?csv=unwanted&days=60", secure=True)
    ck("ดาวน์โหลดรายชื่อไม่ต้องการ (CSV · ชื่อไฟล์ไทย)", r_.status_code == 200 and "text/csv" in r_["Content-Type"]
       and "filename*=UTF-8''" in r_["Content-Disposition"])
    r_ = SM.get("/connect/api/insights?csv=unwanted", secure=True)
    ck("★ เซลล์ดาวน์โหลดรายชื่อ (มีเบอร์) ไม่ได้", r_.status_code == 403)
    s_, d, _ = J(NOB, "/connect/api/alerts")
    ck("ไม่ login = 401", s_ == 401)
    s_, d, _ = J(ADM, "/connect/api/config", {"pull_min": 3})
    ck("ตั้งค่าดึงคืนผิดผ่าน API = 400", s_ == 400, (s_, d))

finally:
    _runner.teardown_databases(_old)
    shutil.rmtree(MEDIA_TMP, ignore_errors=True)

print("\nผ่าน %d / %d" % (len(OK), len(OK) + len(BAD)))
if BAD:
    print("ไม่ผ่าน:\n  - " + "\n  - ".join(BAD))
    sys.exit(1)
