# -*- coding: utf-8 -*-
"""เทสต์ใบเคสรับซื้อตัวอย่าง + รูปรถ → กลุ่มทดสอบ TestBot02 (★ 21 ต.ค.69 · checkout/buyshow.py)

    python scripts/test_buyshow.py

ฐานข้อมูลทดสอบแยก · โฟลเดอร์รูปชั่วคราว · ปลอมที่ขอบระบบเท่านั้น (`requests` = LINE/Google)
ข้อมูลลูกค้าเป็นค่าสมมติทั้งหมด — ห้ามใส่ข้อมูลลูกค้าจริงในไฟล์นี้
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
TMP = tempfile.mkdtemp(prefix="buyshow-")
settings.MEDIA_ROOT = os.path.join(TMP, "media")
settings.CHAT_MEDIA_ROOT = os.path.join(TMP, "chat")
settings.LINE_CHANNEL_ACCESS_TOKEN = "tok-crm"
settings.LINE_PUSH_CHANNEL_ACCESS_TOKEN = "tok-push"
settings.SITE_URL = "https://oxlet.test"

import requests  # noqa: E402
from django.utils import timezone  # noqa: E402
from PIL import Image  # noqa: E402

import dashboard.services.google_sheets as GS  # noqa: E402
from checkout import autolead as AL  # noqa: E402
from checkout import buyshow as BS  # noqa: E402
from checkout import carvision as CV  # noqa: E402
from checkout import connect as C  # noqa: E402
from checkout import kwdb as KW  # noqa: E402
from checkout.leadgroup import parse_buycase  # noqa: E402
from checkout.models import ChatLead, ChatOwner, Employee, GroupChat, LineProfile  # noqa: E402
from dashboard.services import cache_store  # noqa: E402

C.BG_FILL = False
AL.BG = False
BS.BG = False
import checkout.people as _people  # noqa: E402
_people.BG = False
import checkout.chatmedia as CM  # noqa: E402
CM.BG = False

PUSHES = []          # (to, [messages])
REJECT_IMAGES = [False]


class _R:
    def __init__(self, code=200, js=None):
        self.status_code, self._js = code, (js or {})
        self.text = json.dumps(self._js)
        self.headers = {}

    def json(self):
        return self._js


def _post(url, *a, **k):
    if "/message/push" in url:
        js = k.get("json") or {}
        ms = js.get("messages") or []
        if REJECT_IMAGES[0] and any(m.get("type") == "image" for m in ms):
            return _R(400, {"message": "Invalid image url"})
        PUSHES.append((js.get("to"), ms))
        return _R(200, {"sentMessages": [{"id": "sm-%d" % len(PUSHES), "quoteToken": "qt-%d" % len(PUSHES)}]})
    return _R(200, {})


def _get(url, *a, **k):
    return _R(404, {"message": "Not found"})


requests.post, requests.get = _post, _get
GS.load_sheet_config_overrides = lambda *a, **k: None


def _no_sheet(*a, **k):
    raise RuntimeError("ไม่ต่อ Google Sheets ในเทสต์")


GS.fetch_lead_dropdowns = _no_sheet
OK, BAD = [], []


def ck(name, cond, got=""):
    (OK if cond else BAD).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else "   ได้: %r" % (got,)))


T02 = "C" + "2" * 32
T01 = "C" + "1" * 32
NOGO = "C" + "9" * 32
N = {"u": 0, "m": 0}


def jpeg_with_gps() -> bytes:
    im = Image.new("RGB", (900, 600), (200, 30, 30))
    ex = Image.Exif()
    ex[0x8825] = {1: "N", 2: (13.0, 27.0, 0.0)}          # GPSInfo
    b = io.BytesIO()
    im.save(b, "JPEG", exif=ex)
    return b.getvalue()


def chat(name, msgs, phone="", hours_ago=0.5, buy=True, ads="", photos=0, employee=False):
    """ลูกค้า LINE สมมติ + ข้อความ [(dir, text)] + รูปที่ลูกค้าส่ง `photos` รูป"""
    N["u"] += 1
    at = timezone.now() - timedelta(hours=hours_ago)
    uid = "U%031dy" % N["u"]
    p = LineProfile.objects.create(user_id=uid, display_name=name, is_employee=employee)
    o = ChatOwner.objects.create(profile=p, awaiting_since=at, last_in_at=at, last_at=at)
    for i, (d, t) in enumerate(msgs):
        N["m"] += 1
        GroupChat.objects.create(chat_type=GroupChat.USER, message_id="b%d" % N["m"], sender_id=uid, msg_type="text",
                                 text=t, direction=d, sent_at=at - timedelta(minutes=30 - i))
    for i in range(photos):
        N["m"] += 1
        g = GroupChat.objects.create(chat_type=GroupChat.USER, message_id="b%d" % N["m"], sender_id=uid,
                                     msg_type="image", text="[รูป]", direction="in", has_media=True,
                                     sent_at=at - timedelta(minutes=5 - i))
        path = CM.path_for(CM.LINE, g.pk, 0, "jpg")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(jpeg_with_gps())
        GroupChat.objects.filter(pk=g.pk).update(media_token="ok|jpg|%d" % int(timezone.now().timestamp()))
    lead = C.lead_of(o)
    lead.phone, lead.ads = phone, ads
    auto = {"phone": "แชท"} if phone else {}
    if phone:
        auto["_contact_at"] = (at - timedelta(minutes=20)).isoformat(timespec="seconds")
    if buy:
        auto["_buylead"] = {"by": "ระบบ", "at": (at - timedelta(minutes=20)).isoformat(timespec="seconds"),
                            "why": "สมมติ"}
    lead.auto = auto
    lead.save()
    return ChatOwner.objects.select_related("profile", "fb_profile", "owner", "lead").get(pk=o.pk)


def texts_to(gid):
    return [ms[0].get("text") or "" for to, ms in PUSHES if to == gid]


try:
    KW._load(force=True)
    cache_store.set_kv("line_groups", {T02: {"name": "TestBot02", "channels": ["push"]},
                                       T01: {"name": "TestBot", "channels": ["push"]},
                                       NOGO: {"name": "TestBot03", "channels": ["crm"]}})

    # ═════════════════════════════════════════════════════════════════════
    print("[1] อ่านเลขไมล์ / ทะเบียน")
    for t, want in [("เลขไมล์ 150,000 ครับ", "150000 กม"), ("วิ่งมา 12 หมื่น", "120000 กม"),
                    ("ตอนนี้ 98000 กม.", "98000 กม"), ("1.2 แสนโล", "120000 กม"), ("ไมล์ 12xxxx", ""),
                    ("CRV สีดำ 2013 หรือ 14", ""), ("ผ่อนเดือนละ 9000", "")]:
        ck("ไมล์: %s → %s" % (t, want or "(ไม่มี)"), BS.mile_in(t) == want, BS.mile_in(t))
    for t, want in [("ทะเบียน 1กก 1234 ชลบุรี", "1กก1234 ชลบุรี"), ("ป้าย กข-5678 กทม", "กข5678 กทม"),
                    ("2ขค9999 ครับ", "2ขค9999"), ("รถ 2013 ครับ", ""), ("ทะเบียนรถ 2013", ""),
                    ("โทร 0812345678", "")]:
        ck("ทะเบียน: %s → %s" % (t, want or "(ไม่มี)"), BS.plate_in(t) == want, BS.plate_in(t))
    ck("หมวดคำ \"ใบเคสรับซื้อ\" มาจากฐานข้อมูล (7 บทบาท)",
       {r["value"] for r in KW.rows("buy_info")} == {"mile", "mile_unit", "plate", "reason", "cond", "price", "loan"})

    print("\n[2] โฆษณารับซื้อ = ลีดรับซื้อ (ลูกค้าเล่าสภาพรถ ไม่พิมพ์คำว่าขาย)")
    o_ad = chat("ลูกค้าโฆษณา", [("in", "CRV สีดำ 2013 เข้าศูนย์ตลอด ไม่เคยชนหนัก ไม่เคยจมน้ำ")], phone="0811111111",
                buy=False, ads="รับซื้อ CRV")
    lead = C.autofill(o_ad)
    ck("★ ADS \"รับซื้อ CRV\" → ลีดรับซื้อ", C.deal_of(lead) == "buy" and
       "โฆษณา" in ((lead.auto or {}).get("_buylead") or {}).get("why", ""), lead.auto)
    r = AL.show_one(o_ad)
    ck("ใบซ้อมลีดขาย (TestBot) ข้ามลีดรับซื้อ", r["d"] == "skip" and "ไม่ใช่ลีดขาย" in r["why"], r)
    o_trade = chat("ลูกค้าเทิร์น", [("in", "จะเอารถมาเทิร์นได้ไหมครับ")], phone="0811111112", buy=False,
                   ads="รับซื้อ CRV")
    ck("โฆษณารับซื้อ แต่ลูกค้าพูดถึงเทิร์น = ยังเป็นลีดขาย", C.deal_of(C.autofill(o_trade)) == "sell")

    print("\n[3] กลุ่มทดสอบ")
    c0 = BS.ready(persist=False)
    ck("★ ยังไม่ตั้งกลุ่ม = หาเจอกลุ่มชื่อ TestBot02 ที่บอทตัวส่งอยู่", c0["group"] == T02, c0)
    try:
        BS.set_group("TestBot03")
        ck("กลุ่มที่บอทตัวส่งไม่อยู่ = ตั้งไม่ได้", False)
    except ValueError:
        ck("กลุ่มที่บอทตัวส่งไม่อยู่ = ตั้งไม่ได้", True)

    print("\n[4] ใบตัวอย่าง (ปิดบังเบอร์/ชื่อ)")
    o1 = chat("สมชาย ใจดี", [("in", "สนใจขายรถครับ CRV 2013 สีดำ"), ("out", "รบกวนขอเลขไมล์กับทะเบียนครับ"),
                            ("in", "ไมล์ 150,000 ทะเบียน 1กก 1234 ชลบุรี"),
                            ("in", "เข้าศูนย์ตลอด ไม่เคยชน 0899999999"), ("in", "จะออกคันใหม่ครับ"),
                            ("in", "อยากได้ประมาณ 3 แสน ยังติดไฟแนนซ์อยู่ 5 งวด")],
              phone="0899999999", photos=3, ads="รับซื้อ CRV")
    lead1 = C.autofill(o1)
    f = BS.fields(o1, lead1)
    s = BS.slip(f)
    ck("ขึ้นต้น \"โค้ด : OC-\" ไม่มีเลข · parse_buycase ไม่นับเป็นใบจริง", s.startswith("โค้ด : OC-\n")
       and parse_buycase(s) is None, s[:40])
    ck("เลขไมล์/ทะเบียนลงช่อง", "เลขไมล์ : 150000 กม" in s and "ทะเบียน : 1กก1234 ชลบุรี" in s, s)
    ck("★ เบอร์เหลือ 4 ตัวท้าย · ชื่อเหลือตัวแรก", "เบอร์ติดต่อ : xxx-xxx-9999" in s and "ชื่อลูกค้า : ส… / " in s
       and "0899999999" not in s and "สมชาย" not in s, s)
    ck("ขายเพราะ = คำของลูกค้า", "ขายเพราะ : จะออกคันใหม่ครับ" in s, s)
    ck("เพิ่มเติม = สภาพ/ราคา/ไฟแนนซ์ (ตัดเบอร์ออก) + จำนวนรูป", "เข้าศูนย์ตลอด ไม่เคยชน" in s and "3 แสน" in s
       and "ลูกค้าส่งรูปมา 3 รูป" in s and "0899" not in s.split("เพิ่มเติม")[1], s)

    print("\n[5] รอบแรก = ส่งเคสรับซื้อของวันนี้ 5 ใบ พร้อมรูป (ครั้งเดียว)")
    cases = [o1]
    for i in range(5):
        cases.append(chat("ลูกค้า %d" % i, [("in", "อยากขายรถ city ปี 18 ไมล์ %d0000" % (i + 5))],
                          phone="08100000%02d" % i, photos=1 if i < 2 else 0, hours_ago=0.2 + i * 0.1))
    old = chat("ลูกค้าเมื่อวาน", [("in", "อยากขายรถ vios")], phone="0819999999", hours_ago=30, photos=2)
    emp = chat("พนักงาน", [("in", "ขายรถ")], phone="0819999998", employee=True, photos=1)
    PUSHES.clear()
    r = BS.run()
    tx = texts_to(T02)
    ck("★ ส่ง 5 ใบ + ข้อความหัว 1", r.get("backfill", {}).get("sent") == 5 and len(tx) == 6, (r, len(tx)))
    ck("ข้อความหัวบอกว่าเป็นทดสอบ/ปิดบัง", tx and "ทดสอบรูปแบบใบ" in tx[0] and "ปิดบังเบอร์" in tx[0], tx[:1])
    sent_chats = BS.cfg()["backfill"].get("chats") or []
    ck("เคสที่มีรูปมาก่อน (3 เคสที่มีรูปถูกเลือกครบ)", {o1.id, cases[1].id, cases[2].id} <= set(sent_chats), sent_chats)
    ck("ไม่เอาเคสเมื่อวาน / พนักงาน", old.id not in sent_chats and emp.id not in sent_chats, sent_chats)
    imgs = [m for to, ms in PUSHES if to == T02 for m in ms if m.get("type") == "image"]
    ck("★ รูปไปพร้อมใบ (3+1+1 = 5 รูป) ลิงก์ https", len(imgs) == 5 and all(
        m["originalContentUrl"].startswith("https://oxlet.test/") and m["previewImageUrl"].startswith("https://")
        for m in imgs), imgs[:1])
    first = next(ms for to, ms in PUSHES if to == T02 and ms[0].get("text", "").startswith("โค้ด : OC-\nADS : รับซื้อ CRV"))
    ck("ใบของเคสที่มี 3 รูป = ใบ + 3 รูปในข้อความเดียว", len(first) == 4 and first[0]["type"] == "text", len(first))
    out_dir = os.path.join(settings.MEDIA_ROOT, "chat_out")
    saved = [os.path.join(out_dir, x) for x in os.listdir(out_dir)] if os.path.isdir(out_dir) else []
    ck("สำเนารูป (เต็ม + ตัวอย่าง) อยู่ใน media/chat_out", len(saved) == 10, len(saved))
    with Image.open(next(p for p in saved if not p.endswith("_p.jpg"))) as im:
        ck("★ ตัด EXIF/พิกัด GPS ออกจากรูปที่ส่ง", not im.getexif().get(0x8825) and "exif" not in im.info, im.info)
    st = (ChatLead.objects.get(chat=o1).auto or {}).get(BS.KEY) or {}
    ck("จดผลลงแชท (ok · 3 รูป · quoteToken)", st.get("ok") and st.get("photos") == 3 and st.get("qt"), st)
    allt = "\n".join(t for to, ms in PUSHES for m in ms for t in [m.get("text") or ""])
    ck("★ ไม่มีเบอร์เต็ม / LINE user id ในข้อความที่ส่ง", not re.search(r"0\d{9}", allt) and
       not re.search(r"U[0-9a-z]{31,32}", allt), allt[:200])
    PUSHES.clear()
    BS._RUN["at"] = 0
    r2 = BS.run()
    ck("รอบถัดไปไม่ส่งย้อนหลังซ้ำ", "backfill" not in r2 and not texts_to(T02), r2)

    print("\n[6] ลีดรับซื้อใหม่หลังเริ่ม → ส่งเอง · ใบอัปเดตเมื่อลูกค้าพิมพ์เพิ่ม")
    cc = BS.cfg()
    cc["since"] = (timezone.now() - timedelta(minutes=20)).isoformat(timespec="seconds")
    BS.save_cfg(cc)
    o_new = chat("ลูกค้าใหม่", [("in", "อยากขายรถครับ ยาริส ปี 17")], phone="0812222222", hours_ago=0.05)
    LeadAuto = ChatLead.objects.get(chat=o_new)
    LeadAuto.auto = dict(LeadAuto.auto, _contact_at=timezone.now().isoformat(timespec="seconds"))
    LeadAuto.save()
    o_new2 = chat("ลูกค้าก่อนเริ่ม", [("in", "อยากขายรถครับ")], phone="0812222223", hours_ago=3)
    PUSHES.clear()
    r3 = BS.run()
    posted = {x["chat"] for x in r3["rows"] if x.get("d") == "posted"}
    ck("★ ลีดรับซื้อใหม่ → ส่ง · ลูกค้าก่อนเริ่ม / แชทที่ไม่ได้ทักมาหลังเริ่ม ไม่ส่ง",
       posted == {o_new.id} and len(texts_to(T02)) == 1, r3)
    N["m"] += 1
    GroupChat.objects.create(chat_type=GroupChat.USER, message_id="b%d" % N["m"], sender_id=o_new.profile.user_id,
                             msg_type="text", text="ไมล์ 98,000 ครับ", direction="in",
                             sent_at=timezone.now() - timedelta(minutes=2))
    ChatOwner.objects.filter(pk=o_new.pk).update(last_in_at=timezone.now() - timedelta(minutes=2))
    PUSHES.clear()
    r4 = BS.update_one(ChatOwner.objects.get(pk=o_new.pk))
    up = [ms for to, ms in PUSHES if to == T02]
    ck("★ ใบอัปเดตอ้างใบเดิม + บอกช่องที่เพิ่ม", r4.get("d") == "updated" and up and up[0][0].get("quoteToken")
       and "เลขไมล์" in up[0][0]["text"] and "98000 กม" in up[0][0]["text"], (r4, up[:1]))
    ck("ใบอัปเดตไม่ส่งรูปซ้ำ", up and len(up[0]) == 1)

    print("\n[7] รูปถูก LINE ปฏิเสธ → ส่งใบอย่างเดียว ไม่ทิ้งสำเนารูป")
    o_rej = chat("ลูกค้ารูปเสีย", [("in", "อยากขายรถครับ")], phone="0813333333", photos=2, hours_ago=0.02)
    before = len(os.listdir(out_dir))
    REJECT_IMAGES[0] = True
    PUSHES.clear()
    r5 = BS.post_one(ChatOwner.objects.get(pk=o_rej.pk))
    REJECT_IMAGES[0] = False
    st = (ChatLead.objects.get(chat=o_rej).auto or {}).get(BS.KEY) or {}
    ck("ใบถึงกลุ่ม · บอกว่าส่งรูปไม่ได้", r5["d"] == "posted" and st.get("photos") == 0 and "รูป" in st.get("error", ""),
       (r5, st))
    ck("สำเนารูปที่ไม่ได้ส่งถูกลบ", len(os.listdir(out_dir)) == before, (before, len(os.listdir(out_dir))))

    print("\n[8] ปิด / แก้ที่เกี่ยวข้อง")
    BS.set_group("off")
    ck("off = ไม่หากลุ่ม TestBot02 เองอีก", not BS.ready(persist=False)["group"])
    src, row = CV._row_of("l%d" % GroupChat.objects.first().pk)
    ck("★ carvision ส่งชนิดแชทให้ chatmedia ถูก (\"l\" ไม่ใช่ \"line\")", src == CM.LINE, src)
finally:
    print("\nผ่าน %d · ไม่ผ่าน %d" % (len(OK), len(BAD)))
    _runner.teardown_databases(_old)
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if BAD else 0)
