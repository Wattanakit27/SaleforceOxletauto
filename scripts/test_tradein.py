# -*- coding: utf-8 -*-
"""เทสต์ เคสรับซื้อ/เทิร์นรถ → ชีต (checkout/tradein.py · ย้ายมาจาก n8n 8 ต.ค.69)

    python scripts/test_tradein.py

1) ตัวอ่านใบเคส/คอมเมนต์ (ข้อความสมมติ ไม่ใช่ข้อมูลลูกค้าจริง)
2) **ผลต้องตรงกับโค้ด n8n ตัวจริงทุกช่อง** (รัน deploy/n8n_tradein_build_row.js ด้วย node)
   — ตอนย้ายระบบ (8 ต.ค.69) เทียบกับข้อความจริง 487 ข้อความแล้วตรงทุกช่อง
3) วนประมวลผล + เขียนชีต (ฐานข้อมูลทดสอบแยก · ปลอมที่ `requests` = Google Sheets API)
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone as dtz

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
os.environ.setdefault("DB_HOST", "")
os.environ.setdefault("DEBUG", "True")

import django  # noqa: E402

django.setup()

from django.test.runner import DiscoverRunner  # noqa: E402
from django.test.utils import setup_test_environment  # noqa: E402

setup_test_environment()
_runner = DiscoverRunner(verbosity=0, interactive=False)
_old = _runner.setup_databases()

from unittest import mock  # noqa: E402

from checkout import tradein as T  # noqa: E402
from checkout.models import Employee, GroupChat, LineProfile  # noqa: E402
from dashboard.services import cache_store  # noqa: E402

FAILS = []


def ok(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else " — " + str(extra)))
    if not cond:
        FAILS.append(name)


HOT_BEAR, HOT_TARD, VHOT = list(T.PURCHASE_GROUPS)
AT = datetime(2026, 10, 8, 5, 0, tzinfo=dtz.utc)          # 12:00 เวลาไทย

SLIP = ("โค้ด : OC-9001\nADS : รับซื้อ CIVIC\nรุ่น : Honda Civic FC ปี19 ขาว\nเลขไมล์ : 80,000 กม\n"
        "ทะเบียน : 1กก1234\nเบอร์ติดต่อ : 081-234-5678\nชื่อลูกค้า : -ทดสอบ / Line@\nเพิ่มเติม : -\n"
        "ขายเพราะ : จะซื้อคันใหม่\nต่อบรรทัดสอง\nราคากลางรับซื้อจากตาราง :\n@หมีน้อย")
SLIP_DIESEL = ("โค้ด : OC-9002\nรุ่น : Isuzu MU-X ปี23\nเครื่องยนต์: ดีเซล 1,898 ซีซี\n"
               "เบอร์ติดต่อ : 0899999999\nชื่อลูกค้า : ทดสอบสอง / เพจguru")
SLIP_TURN = ("โค้ด : SC-9003 เทิร์นเซลล์เก้า\nรุ่น : Benz GLE350d ปี17 ดำ\nทะเบียน : งต3\n"
             "เบอร์ : 0811111111\nหมายเหตุ : มือเดียว\nราคาตาราง :")
COMMENT = "OC-9001 คาดหวัง 400,000 ให้ไว้ 380,000 @หมีน้อย"
REASSIGN = "SC-9003 ติดต่อพี่หมีไม่ได้ เปลี่ยนเป็นของพี่ต๊าดครับ @•Tard'ANUPonG•"
CHAT = "ซื้อมือสองมาครับ"

# ── 1) ตัวอ่าน ─────────────────────────────────────────────
b = T.build(SLIP, HOT_BEAR, "หมิว", T.map_purchaser(T.pick_tag(SLIP)), AT)
r = b["row"]
ok("ใบเคส → case_form + รหัส", b["mode"] == "case_form" and b["code"] == "OC-9001", b)
ok("A วันที่ตามเวลาที่ข้อความเข้า (ไทย)", r[0] == "8/10/2026", r[0])
ok("F เบอร์มี ' นำหน้า", r[5] == "'0812345678", r[5])
ok("G ชื่อขึ้นต้น - ได้ ' นำหน้า", r[6] == "'-ทดสอบ", r[6])
ok("I ช่องทางจากชื่อลูกค้า/ช่องทาง", r[8] == "Line@", r[8])
ok("K รับซื้อ/ไม่รับซื้อ ว่างเสมอ", r[10] == "", r[10])
ok("M จัดซื้อจาก @tag", r[12] == "พี่หมี", r[12])
ok("N ผู้ส่ง = คนโพสต์", r[13] == "หมิว", r[13])
ok("O เคสตามห้อง = HOT", r[14] == "HOT", r[14])
ok("P โปรไฟล์ต่อบรรทัด + ไม่มีราคากลาง", r[15] == "'- จะซื้อคันใหม่ ต่อบรรทัดสอง", r[15])
ok("S car", r[18] == "Civic", r[18])
r = T.build(SLIP_DIESEL, HOT_TARD, "โดนัท", "", AT)["row"]
ok("ดีเซล 1,898 ไม่ใช่ชื่อผู้ส่ง", r[13] == "โดนัท", r[13])
ok("ไม่มี @tag → จัดซื้อ = เจ้าของห้อง", r[12] == "พี่ต๊าด", r[12])
r = T.build(SLIP_TURN, VHOT, "มิว", "", AT)["row"]
ok("เทิร์นเซลล์เก้า → ผู้ส่ง = เก้า", r[13] == "เก้า", r[13])
ok("SC = หน้าร้านบ้านเก่า/Offline/VERY HOT", (r[8], r[11], r[14]) == ("หน้าร้านบ้านเก่า", "Offline", "VERY HOT"), r)
ok("ห้อง VERY HOT ไม่มีเจ้าของประจำ", r[12] == "", r[12])
c = T.build(COMMENT, HOT_BEAR, "พี่หมี", T.map_purchaser(T.pick_tag(COMMENT)), AT)
ok("คอมเมนต์ตัดรหัส/แท็กออก", c["mode"] == "purchase_comment" and c["comment"] == "คาดหวัง 400,000 ให้ไว้ 380,000", c)
ok("แชทไม่มีรหัส = ข้าม", T.build(CHAT, HOT_BEAR, "x", "", AT) is None)
ok("ห้องอื่น = ข้าม", T.build(SLIP, "Cxxxxxxxx", "x", "", AT) is None)
ok("ชื่อเล่นจากทะเบียนชนะ", T.resolve_sender("มัท", "เซลมัท OxletAuto") == "มัท")
ok("ชื่อเล่นที่เป็นชื่อ LINE → MANUAL_MAPPING", T.resolve_sender("Miwa", "Miwa") == "มิว")

# ── 2) ตรงกับโค้ด n8n ตัวจริง ─────────────────────────────────
node = shutil.which("node")
if not node:
    print("SKIP เทียบกับ n8n — ไม่มี node ในเครื่องนี้")
else:
    fixtures = [(SLIP, HOT_BEAR, "หมิว"), (SLIP_DIESEL, HOT_TARD, "โดนัท"), (SLIP_TURN, VHOT, "มิว"),
                (COMMENT, HOT_BEAR, "พี่หมี"), (REASSIGN, VHOT, "มิว"), (CHAT, HOT_BEAR, "x"),
                ("โค้ด : TC-9004 จากเซลล์มัท\nYaris ativ ปี20\n089-1234567\nเพิ่มเติม : -ครับ", HOT_TARD, "โดนัท"),
                ("OC-9001\n\nขอบคุณครับ @หมีน้อย\n", HOT_BEAR, "พี่หมี")]
    harness = r"""
const fs=require("fs");const src=fs.readFileSync(process.argv[1],"utf8");const fx=JSON.parse(fs.readFileSync(0,"utf8"));
const hasPhone=t=>/0\d{8,9}/.test(String(t||"").replace(/[-\s]/g,""));
const pc=t=>{const m=String(t||"").match(/\b([A-Za-z]{1,8})\s*-\s*(\d{1,8})\b/);return m?`${m[1]}-${m[2]}`.toUpperCase().replace(/\s+/g,""):""};
const tag=t=>{const m=String(t||"").match(/@([^\n@]+)/);return m?m[1].trim():""};
const mp=g=>{const s=String(g||"").toLowerCase();if(!s)return"";if(s.includes("tard")||s.includes("tad")||s.includes("ต๊าด")||s.includes("ตาด"))return"พี่ต๊าด";if(s.includes("หมี")||s.includes("bear"))return"พี่หมี";if(s.includes("miwa")||s.includes("miw")||s.includes("มิว"))return"มิว";return""};
const out=fx.map(([text0,g,sender])=>{const text=String(text0).trim();const Real=Date;
 global.Date=class extends Real{constructor(...a){if(a.length===0)super("2026-10-08T05:00:00Z");else super(...a)}};
 let r;try{r=new Function("$input","console",src)({all:()=>[{json:{_mode:hasPhone(text)?"case_form":"purchase_comment",code:pc(text),text,senderNickname:sender,purchaserNickname:mp(tag(text)),groupId:g}}]},{log(){}})}finally{global.Date=Real}
 if(!r||!r.length)return null;const j=r[0].json;
 return j._mode==="case_form"?{mode:"case_form",code:j._code,row:j.rowAS}:{mode:"purchase_comment",code:j.code,comment:j.comment,purchaser:j.purchaserNickname}});
process.stdout.write(JSON.stringify(out));"""
    p = subprocess.run([node, "-e", harness, os.path.join(ROOT, "deploy", "n8n_tradein_build_row.js")],
                       input=json.dumps(fixtures, ensure_ascii=False).encode("utf-8"), capture_output=True)
    js = json.loads(p.stdout.decode("utf-8") or "null") if p.returncode == 0 else None
    ok("รันโค้ด n8n ได้", js is not None, p.stderr.decode("utf-8", "replace")[:300])
    for i, (text, g, sender) in enumerate(fixtures if js else []):
        py = T.build(text, g, sender, T.map_purchaser(T.pick_tag(text.strip())), AT)
        if py and py["mode"] == "purchase_comment":
            py = {k: py[k] for k in ("mode", "code", "comment", "purchaser")}
        ok("ตรงกับ n8n #%d (%s)" % (i + 1, text.split("\n")[0][:24]), py == js[i], {"py": py, "js": js[i]})


# ── 3) วนประมวลผล + เขียนชีต (ปลอม Sheets API) ───────────────
class R:
    def __init__(self, code=200, js=None):
        self.status_code, self._js = code, js or {}
        self.text = json.dumps(self._js, ensure_ascii=False)

    def json(self):
        return self._js


def _ci(col):
    n = 0
    for ch in col:
        n = n * 26 + ord(ch) - 64
    return n - 1


def _cl(i):
    s, i = "", i + 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


_RNG = re.compile(r"'(.+)'!([A-Z]+)([0-9]+)(?::([A-Z]+)([0-9]*))?$")


class FakeSheets:
    """Google Sheets ปลอม — อ่าน/เขียนตามช่วงจริง

    `:append` ทำแบบ Google ของจริง (บั๊กที่เจอบน prod 8 ต.ค.69): "ตาราง" = ช่วงติดกันก้อนสุดท้าย
    ของแถวล่างสุดที่มีค่า → แถวก่อนหน้ามี S โดดเดี่ยว (R/T ว่าง) = เริ่มเขียนที่ S
    """

    def __init__(self, tabs):
        self.tabs = {k: [list(r) for r in v] for k, v in tabs.items()}   # แท็บ → แถว เริ่มแถว 1
        self.calls, self.fail_write = [], False

    def _row(self, tab, n):
        rows = self.tabs[tab]
        while len(rows) < n:
            rows.append([])
        return rows[n - 1]

    def _set(self, tab, n, c, v):
        row = self._row(tab, n)
        while len(row) <= c:
            row.append("")
        row[c] = v

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(("GET", urllib.parse.unquote(url)))
        if "/values/" not in url:
            return R(200, {"sheets": [{"properties": {"title": t, "sheetId": i, "index": i}}
                                      for i, t in enumerate(self.tabs)]})
        m = _RNG.match(urllib.parse.unquote(url.split("/values/", 1)[1]))
        tab = m.group(1)
        if tab not in self.tabs:
            return R(400, {"error": {"message": "Unable to parse range"}})
        c0, r0 = _ci(m.group(2)), int(m.group(3))
        c1 = _ci(m.group(4)) if m.group(4) else c0
        r1 = int(m.group(5)) if m.group(5) else len(self.tabs[tab])
        out = [list(r[c0:c1 + 1]) for r in self.tabs[tab][r0 - 1:r1]]
        while out and not any(str(v).strip() for v in out[-1]):
            out.pop()
        return R(200, {"values": out})

    def put(self, url, params=None, json=None, headers=None, timeout=None):
        u = urllib.parse.unquote(url)
        self.calls.append(("PUT", u, json))
        if self.fail_write:
            return R(500, {"error": "boom"})
        m = _RNG.match(u.split("/values/", 1)[1])
        tab, c0, r0 = m.group(1), _ci(m.group(2)), int(m.group(3))
        for i, vals in enumerate(json["values"]):
            for j, v in enumerate(vals):
                self._set(tab, r0 + i, c0 + j, v)
        return R(200, {"updatedRange": "'%s'!%s%d:%s%d" % (
            tab, _cl(c0), r0, _cl(c0 + len(json["values"][0]) - 1), r0 + len(json["values"]) - 1)})

    def post(self, url, params=None, json=None, headers=None, timeout=None):
        u = urllib.parse.unquote(url)
        self.calls.append(("POST", u, json))
        if self.fail_write:
            return R(500, {"error": "boom"})
        if u.endswith(":append"):
            m = _RNG.match(u.split("/values/", 1)[1][:-len(":append")])
            tab, first = m.group(1), int(m.group(3))
            rows = self.tabs[tab]
            last = max((i + 1 for i, r in enumerate(rows) if i + 1 >= first and any(str(v).strip() for v in r[:19])),
                       default=0)
            start = 0
            if last:
                r = rows[last - 1][:19]
                j = max(k for k, v in enumerate(r) if str(v).strip())
                while j > 0 and str(r[j - 1]).strip():
                    j -= 1
                start = j
            n = max(first, last + 1)
            for j, v in enumerate(json["values"][0]):
                self._set(tab, n, start + j, v)
            return R(200, {"updates": {"updatedRange": "'%s'!%s%d" % (tab, _cl(start), n)}})
        if u.endswith("values:batchUpdate"):
            for d in json["data"]:
                m = _RNG.match(d["range"])
                self._set(m.group(1), int(m.group(3)), _ci(m.group(2)), d["values"][0][0])
            return R(200, {"totalUpdatedCells": len(json["data"])})
        if u.endswith("values:batchClear"):
            for rng in json["ranges"]:
                m = _RNG.match(rng)
                tab, c0, r0 = m.group(1), _ci(m.group(2)), int(m.group(3))
                c1, r1 = _ci(m.group(4)), int(m.group(5))
                for n in range(r0, r1 + 1):
                    row = self._row(tab, n)
                    for c in range(c0, min(c1 + 1, len(row))):
                        row[c] = ""
            return R(200, {"clearedRanges": json["ranges"]})
        return R(400, {})

    def writes(self):
        return [c for c in self.calls if c[0] in ("POST", "PUT")]


class Creds:
    token = "t"

    def refresh(self, _):
        pass


def row(code, q="", m=""):
    r = [""] * 19
    r[2], r[12], r[16] = code, m, q
    return r


emp = Employee.objects.create(nickname="หมิว")
LineProfile.objects.create(user_id="Uadmin1", display_name="Miw OxletAuto", employee=emp, is_employee=True)
n = [0]


def msg(text, g=HOT_BEAR, uid="Uadmin1", minutes=0):
    n[0] += 1
    return GroupChat.objects.create(chat_type="group", group_id=g, group_name="x", message_id="m%d" % n[0],
                                    sender_id=uid, sender_name="?", msg_type="text", text=text,
                                    sent_at=AT + timedelta(minutes=minutes))


def run(fake):
    with mock.patch("dashboard.services.google_sheets._get_credentials", return_value=Creds()), \
            mock.patch("requests.get", fake.get), mock.patch("requests.post", fake.post),             mock.patch("requests.put", fake.put):
        return T.process_pending()


def run_repair(fake, apply):
    with mock.patch("dashboard.services.google_sheets._get_credentials", return_value=Creds()),             mock.patch("requests.get", fake.get), mock.patch("requests.post", fake.post),             mock.patch("requests.put", fake.put):
        return T.repair_shifted(apply=apply)


old = msg("โค้ด : OC-8000\nเบอร์ 0800000000", minutes=-600)        # ก่อนจุดเริ่ม (ถือว่าจัดการแล้ว)
cache_store.set_kv(T.KV_STATE, {"last_id": old.id})
T.set_config(enabled=True, target="test")
msg(SLIP, minutes=1)
msg(SLIP_TURN, g=VHOT, minutes=2)
msg(CHAT, minutes=3)
msg("โค้ด : OC-1000 โพสต์ซ้ำ\nเบอร์ 0822222222", minutes=4)          # มีในชีตแล้ว
msg("OC-1000 รอลูกค้าตัดสินใจ", minutes=5)
msg(REASSIGN, g=VHOT, minutes=6)
msg(SLIP, g="Cother", minutes=7)                                      # ห้องอื่น — ไม่ใช่งานเรา
_good = row("OC-1000", q="โทรแล้ว", m="พี่หมี")
_good[18] = "Fortuner"          # S มีค่าแต่ R/T ว่าง = แบบเดียวกับ SC-1301 บน prod ที่ทำให้ append เดาผิด
# พิสูจน์ก่อนว่าชีตปลอมจำลองบั๊กจริงได้: append ไปลงคอลัมน์ S
_probe = FakeSheets({"TestBot": [row("OC-0999"), list(_good)]})
_probe.post("x/values/'TestBot'!A1:S:append",
            json={"values": [["8/10/2026", "", "OC-1"]]})
ok("ชีตปลอม: append แบบเดิมไปลงคอลัมน์ S (จำลองบั๊ก prod 8 ต.ค.)",
   len(_probe.tabs["TestBot"]) == 3 and _probe.tabs["TestBot"][2][18] == "8/10/2026"
   and _probe.tabs["TestBot"][2][20] == "OC-1", _probe.tabs["TestBot"][2])
fake = FakeSheets({"TestBot": [row("OC-0999"), _good]})
res = run(fake)
tb = fake.tabs["TestBot"]
codes = [r[2] for r in tb if len(r) > 2 and r[2]]
ok("เพิ่ม 2 เคสใหม่ต่อท้าย TestBot", codes == ["OC-0999", "OC-1000", "OC-9001", "SC-9003"], codes)
ok("แถวใหม่ผู้ส่ง = ชื่อเล่นจากทะเบียน", tb[2][13] == "หมิว", tb[2][13])
ok("แถวใหม่เริ่มคอลัมน์ A (วันที่) ไม่เลื่อน", tb[2][0] == "8/10/2026" and tb[3][2] == "SC-9003", tb[2][:3])
ok("ไม่มีค่าเกินคอลัมน์ S", all(not any(str(v).strip() for v in r[19:]) for r in tb), [len(r) for r in tb])
ok("ไม่เรียก values:append เลย", not any(":append" in c[1] for c in fake.calls))
ok("โพสต์ซ้ำรหัสเดิม = ไม่เพิ่มแถว", res["dup"] == ["OC-1000"], res)
ok("คอมเมนต์ต่อท้ายช่อง Q", tb[1][16] == "โทรแล้ว / รอลูกค้าตัดสินใจ", tb[1][16])
ok("คอมเมนต์โอนเคส → ช่อง M เปลี่ยนตาม", tb[3][12] == "พี่ต๊าด", tb[3][12])
ok("ห้องอื่น/แชทไม่มีรหัส ไม่เขียนอะไร", len(fake.writes()) == 4, len(fake.writes()))
ok("ไม่เขียนแถวต้นฉบับเดิม (OC-0999)", tb[0] == row("OC-0999"))
ok("ไม่มีข้อความค้าง", T.pending_count() == 0, T.pending_count())
fake.calls.clear()
res2 = run(fake)
ok("รอบถัดไปไม่มีงาน = ไม่ยิง Google เลย", res2 == {"pending": 0} and not fake.calls, (res2, fake.calls[:2]))

# เขียนล้ม → ไม่ขยับตัวชี้ · รอบหน้าลองใหม่
m1 = msg("โค้ด : OC-9100\nเบอร์ 0833333333", minutes=10)
fake.fail_write = True
res3 = run(fake)
ok("เขียนล้ม → จด error", "HTTP 500" in res3.get("error", ""), res3)
ok("เขียนล้ม → ข้อความยังค้าง", T.pending_count() == 1, T.pending_count())
fake.fail_write = False
res4 = run(fake)
ok("รอบถัดไปลองใหม่สำเร็จ", res4.get("added") == ["OC-9100"] and not res4.get("error"), res4)

# โหมดแท็บรายเดือน: เขียนแท็บของเดือนที่ข้อความเข้า · คอมเมนต์หาเคสเดือนก่อนได้
T.set_config(target="month")
fake2 = FakeSheets({"ขายรถจบออนไลน์ กันยายน69": [["กันยายน69"], ["หัว"], row("OC-7000", q="")],
                    "ขายรถจบออนไลน์ ตุลาคม69": [["ตุลาคม69"], ["หัว"], ["", "1"]]})
msg("โค้ด : OC-9200\nเบอร์ 0844444444", minutes=20)
msg("OC-7000 ลูกค้าเลื่อนนัด", minutes=21)
res5 = run(fake2)
oct_ = fake2.tabs["ขายรถจบออนไลน์ ตุลาคม69"]
ok("เดือน: เคสลงแท็บ ตุลาคม69 แถวถัดไป (ไม่ทับแถวที่พิมพ์ B ไว้)",
   len(oct_) >= 4 and oct_[3][2] == "OC-9200" and oct_[2] == ["", "1"], oct_)
ok("เดือน: คอมเมนต์เคสเดือนก่อนลงแท็บ กันยายน69",
   fake2.tabs["ขายรถจบออนไลน์ กันยายน69"][2][16] == "ลูกค้าเลื่อนนัด", fake2.tabs["ขายรถจบออนไลน์ กันยายน69"][2])

# ซ่อมแถวที่ลงผิดคอลัมน์ (ของจริงบน prod 8 ต.ค.69) — ข้อความหลัง INITIAL_SINCE (12:34)
T.set_config(enabled=True, target="test")
msg("โค้ด : OC-9500\nรุ่น : city 2022\nเบอร์ 0866666666", minutes=40)
msg("โค้ด : OC-9501\nรุ่น : mazda 2\nเบอร์ 0877777777", minutes=41)
msg("OC-9500 ลูกค้าขอคิดก่อน", minutes=42)
shifted = lambda code: [""] * 18 + ["8/10/2026", "", code, "รุ่น", "", "0866666666"]
_g2 = row("OC-1000", m="พี่หมี"); _g2[18] = "Fortuner"
fake3 = FakeSheets({"TestBot": [row("OC-0999"), _g2, shifted("OC-9500"), shifted("OC-9501")]})
rp = run_repair(fake3, False)
ok("ซ่อม: ดูเฉยๆ เจอ 2 แถว (3,4) ไม่เขียนอะไร",
   rp.get("rows") == [3, 4] and rp.get("codes") == ["OC-9500", "OC-9501"] and not fake3.writes(), rp)
rp = run_repair(fake3, True)
tb3 = fake3.tabs["TestBot"]
ok("ซ่อม: เขียนใหม่ที่แถวเดิม เริ่มคอลัมน์ A", tb3[2][2] == "OC-9500" and tb3[3][2] == "OC-9501"
   and tb3[2][0] == "8/10/2026", [r[:3] for r in tb3])
ok("ซ่อม: ไม่มีค่าเกินคอลัมน์ S เหลือ", all(not any(str(v).strip() for v in r[19:]) for r in tb3),
   [r[18:] for r in tb3])
ok("ซ่อม: คอมเมนต์ที่เคยหาเคสไม่เจอ ลงแล้ว", tb3[2][16] == "ลูกค้าขอคิดก่อน", tb3[2][16:17])
ok("ซ่อม: ไม่มีแถวซ้ำ", [r[2] for r in tb3 if len(r) > 2 and r[2]] == ["OC-0999", "OC-1000", "OC-9500", "OC-9501"])
ok("ซ่อม: ผลบอกเคสที่เขียนใหม่", rp.get("applied") and rp.get("added") == ["OC-9500", "OC-9501"], rp)
ok("ซ่อม: รันซ้ำไม่เจออะไรแล้ว", run_repair(fake3, True).get("rows") == [])
fake4 = FakeSheets({"TestBot": [row("OC-0999"), shifted("OC-9500"), row("OC-0998")]})
ok("ซ่อม: มีแถวถูกอยู่ใต้แถวผิด = ไม่ซ่อมเอง (กันช่องว่างกลางตาราง)",
   run_repair(fake4, True).get("rowsBelow") == 1 and not fake4.writes())

# ปิดอยู่ = ไม่ทำอะไร
T.set_config(enabled=False)
msg("โค้ด : OC-9300\nเบอร์ 0855555555", minutes=30)
ok("ปิดอยู่ = ไม่ทำอะไร", T.process_pending() == {"skipped": "ปิดอยู่"})

_runner.teardown_databases(_old)
print("\n%d FAIL" % len(FAILS) if FAILS else "\nALL PASS")
sys.exit(1 if FAILS else 0)
