"""เก็บบทสนทนาห้องโค้ชเซลล์ (Senior ↔ Junior) ลงชีต — **ข้อเท็จจริงล้วน ไม่มี AI**

ที่มา (เจ้าของสั่ง 27 ก.ย.69): *"กลุ่มนี้จะเป็น chatbot ในการถามตอบของ AI ระหว่าง Senior กับ
Junior ตอนนี้ฉันได้ปิดระบบการใช้งานไปแล้ว … แต่ฉันอยากให้เก็บข้อมูลของ Senior และ Junior
ต่อไปนี้ไว้ด้วย … เอาข้อมูลเก่าใส่เข้ามาด้วย"*

━━ ทำไมไม่เก็บแบบเดิม ━━
แท็บเดิม `Sheet A — Log` มี **คอลัมน์ซีเนียร์ 4 ช่องฮาร์ดโค้ด** (`เฟิร์ส | โอ๊ต | นวล | อุ้ม`)
→ กรอกจริงแค่ 192 จาก 1,424 แถว (13%) = ตารางว่างเป็นส่วนใหญ่ **และเพิ่มซีเนียร์คนที่ 5
ต้องแก้โครงตาราง** · แท็บใหม่เป็น **1 แถว = 1 ข้อความ** (long format) → เพิ่มคนไม่ต้องแก้อะไร
และ Pivot นับได้ว่าใครตอบกี่เคส ใครถามบ่อย

━━ กติกาที่ต้องรักษา ━━
- **เขียนต่อท้ายเท่านั้น (append) ไม่เคย clear** — `Sheet A — Log` เดิมเป็นประวัติ 1,424 แถว
  ห้ามทับ · และแท็บใหม่ต้องไม่เสียแถวที่คนเข้าไปแก้มือ
- **กันเขียนซ้ำด้วยคอลัมน์ `รหัสอ้างอิง`** → รันซ้ำกี่ครั้งก็ได้ ไม่เบิ้ล (กติกาเดียวกับ
  `meta_sync`/`tiktok_sync` ที่ลบชุดของวันนั้นก่อนเขียน — ที่นี่ใช้ "ข้ามของที่มีแล้ว")
- **ไม่โชว์ LINE user id** (กติกาเดิมทั้งโปรเจกต์) — ชีตเก็บ "ชื่อ" อย่างเดียว
- **ไม่เดาคนพูด** — เทียบชื่อกับทะเบียนพนักงานแบบตรงตัว ไม่เจอ = ใช้ชื่อที่ตั้งใน LINE
  (ล้างอิโมจิแล้ว) ตามเดิม · ⚠️ **ห้ามทำ fuzzy/substring match** — วัดจริง 27/09:
  `Mod🐜 Oxlet Auto` จะไปจับกับ `เอ็ม` (คนละคน) เพราะ `m` เป็น substring
- **ไม่ส่งข้อความหาใคร** — โมดูลนี้อ่านกับเขียนชีตเท่านั้น (ระบบถามตอบ AI เจ้าของปิดแล้ว)

━━ ทำไมต้องซิงก์ประจำ ━━
แชทดิบใน `checkout_groupchat` **ถูกลบเมื่อครบ `CHAT_KEEP_DAYS` (90 วัน)** ตามกติกา PDPA เดิม
→ ชีตนี้เป็น **ตัวถาวร** ถ้าไม่ซิงก์ ข้อมูลโค้ชจะหายไปเองเงียบๆ (ของเดิมมีย้อนหลัง 4 เดือนแล้ว)
`cron_tick` เรียก `maybe_sync()` วันละครั้ง
"""
import re
import unicodedata

from django.utils import timezone

from dashboard.services.cache_store import get_kv, set_kv

# ── ที่อยู่ข้อมูล ──
SHEET_ID = "1URfK6ILX4xxsifM8hPxqHW-FOt60fYDaCusNB-ky4sQ"
TAB = "บันทึกโค้ช"                 # แท็บใหม่ (สร้างให้เองถ้าไม่มี)
OLD_TAB = "Sheet A — Log"          # แท็บเดิม — **อ่านอย่างเดียว ห้ามเขียน**

CFG_KEY = "coach_config"
SYNC_KEY = "coach_sync_last"
DEFAULT_GROUP = "C7d9fd79e5658470e23f62a8fd1f12670"   # Sale Coaching Room Oxlet auto (ฝั่งบอทตัวส่ง)
DEFAULT_SENIORS = ["อุ้ม", "เฟิร์ส", "โอ๊ต", "นวล"]      # เจ้าของระบุ 27 ก.ย.69

# คอลัมน์ของแท็บใหม่ — **เพิ่มคอลัมน์ให้ต่อท้ายเสมอ** (ของเดิมในชีตจะไม่เลื่อน)
COLUMNS = ["วันที่", "เวลา", "รหัสเคส", "ผู้พูด", "บทบาท", "ทีม", "ข้อความ",
           "สถานะเคส", "ชนิด", "ที่มา", "หมายเหตุ", "รหัสอ้างอิง"]
REF_COL = len(COLUMNS) - 1          # ตำแหน่งคอลัมน์ "รหัสอ้างอิง" (ใช้กันเขียนซ้ำ)

SENIOR, JUNIOR, BOT, UNKNOWN = "ซีเนียร์", "จูเนียร์", "บอท AI (ระบบเดิม)", "(ไม่ทราบ)"
SRC_BOT, SRC_OLD = "บอท", "ชีตเดิม"
SRC_OLD_MISPLACED = "ชีตเดิม-ช่องผิด"
SRC_OLD_AI = "ชีตเดิม-AI"

# ── แท็บเดิม: ตำแหน่งคอลัมน์ (18 ช่อง) ──
O_DATE, O_TIME, O_CODE, O_UID, O_DISPLAY, O_SELLER = 0, 1, 2, 3, 4, 5
O_LEVEL, O_TEXT, O_BOT = 6, 7, 8
O_SENIOR_COLS = {9: "เฟิร์ส", 10: "โอ๊ต", 11: "นวล", 12: "อุ้ม"}
O_TYPE, O_AUTO, O_COUNT, O_LAST, O_STATUS = 13, 14, 15, 16, 17

# ค่าที่ควรอยู่ในช่อง "ประเภทเหตุการณ์" จริงๆ — นอกลิสต์นี้ = ข้อความที่ถูกยัดผิดช่อง
# (วัดจริง 27/09: 38 แถว มีทั้งคำแนะนำซีเนียร์และคำบรรยายเคสของจูเนียร์ปนกัน → ไม่เดาว่าใครพูด)
KNOWN_TYPES = {"อัปเดตเคส", "รายงานจอง", "รายงานเคส", "คืนเคส", "คำแนะนำ",
               "รีเจ็คเคส", "ปล่อยรถ", "คำถาม"}
_ODD_SKIP = {"-", "อื่นๆ", "ไม่ระบุ"}

MSG_TYPE_TH = {"text": "ข้อความ", "image": "รูป", "video": "วิดีโอ", "audio": "เสียง",
               "file": "ไฟล์", "sticker": "สติกเกอร์", "location": "ตำแหน่ง"}

# ── รหัสเคส ──
# รูปแบบจริงในชีตเก่า (41 แบบ): NLD-4095 · TLD-31620 · RBLD-30627/1 · TALD-5408 · LD-4042 · 4047
_CODE_PREFIXED = re.compile(r"\b(R?[A-Z]{1,4}LD)\s*-\s*(\d{3,6})(/\d{1,2})?\b", re.I)
# เลขเปล่า: รับ **เฉพาะตอนอยู่ต้นบรรทัด** เท่านั้น (กติกาเดียวกับ `leadgroup._UPDATE`)
# ไม่งั้นจะไปจับราคา/ค่าผ่อน/อายุ ("ผ่อน 13000" · "อายุ 32 ปี") มาเป็นรหัสเคส
#
# ★ ต้องเป็น "ต้นบรรทัด" (re.M) ไม่ใช่ "ต้นข้อความ" — วัดกับของจริง 28 ก.ย.69:
#   รายงานเคสในห้องโค้ชขึ้นต้นด้วย "รายงานเคสวันที่ 28/9" **เสมอ** แล้วรหัสเคสอยู่
#   บรรทัดถัดๆ ไป → `.match()` ที่ยึดต้นข้อความจับไม่ได้เลยสักเคส (6 จาก 7 ข้อความ
#   มีรหัสเคสอยู่ แต่คอลัมน์ "รหัสเคส" ว่างทั้งหมด)
_CODE_BARE_HEAD = re.compile(r"^[ \t]*(\d{4,5})(/\d{1,2})?\b", re.M)


def cfg() -> dict:
    """ตั้งค่า: กลุ่มไหน · ใครเป็นซีเนียร์ · เปิดซิงก์อัตโนมัติไหม (อ่านไม่ได้ = ใช้ค่าตั้งต้น)"""
    d = {}
    try:
        raw = get_kv(CFG_KEY) or {}
        d = raw.get("data", raw) if isinstance(raw, dict) else {}
    except Exception:
        d = {}
    if not isinstance(d, dict):
        d = {}
    return {
        "group_id": (d.get("group_id") or DEFAULT_GROUP).strip(),
        "seniors": [s for s in (d.get("seniors") or DEFAULT_SENIORS) if str(s).strip()],
        "enabled": bool(d.get("enabled", True)),
        "tab": (d.get("tab") or TAB).strip(),
    }


def save_cfg(**kw) -> dict:
    cur = cfg()
    cur.update({k: v for k, v in kw.items() if v is not None})
    set_kv(CFG_KEY, cur)
    return cur


def _norm_nick(s) -> str:
    """ทำชื่อให้เทียบกันได้ — NFC ไม่ใช่ NFKC (บทเรียนเดิม: NFKC แยกสระ 'ำ' ทำให้ 'ดำ' เทียบไม่ตรง)"""
    return unicodedata.normalize("NFC", str(s or "")).strip().lower()


def is_senior(nick, seniors=None) -> bool:
    want = {_norm_nick(s) for s in (seniors if seniors is not None else cfg()["seniors"])}
    return _norm_nick(nick) in want


def case_code(text) -> str:
    """ดึงรหัสเคสจากข้อความ — ไม่เจอ = คืนค่าว่าง (ไม่เดา)

    ★ คืน **ได้หลายรหัส คั่นด้วยช่องว่าง** เพราะของจริงในห้องโค้ช 1 ข้อความ =
      "รายงานเคสประจำวัน" ที่คร่อมหลายเคส (วัด 28 ก.ย.69: ข้อความเดียวมี 8029 + 8074)
      → ถ้าคืนรหัสแรกตัวเดียว คอลัมน์นี้จะบอกความจริงไม่ครบ
    ⚠️ ผลพลอยได้: คอลัมน์นี้ **Pivot ตรงๆ ไม่ได้** ต้องแยกช่องว่างก่อน — อยากได้
      1 แถว/เคส ต้องแตกแถวตอนเขียน (ref เป็น `line:<mid>#<รหัส>`) ซึ่งยังไม่ได้ทำ
    """
    t = str(text or "")
    out = []
    for m in _CODE_PREFIXED.finditer(t):
        out.append("%s-%s%s" % (m.group(1).upper(), m.group(2), m.group(3) or ""))
    for m in _CODE_BARE_HEAD.finditer(t):
        out.append("%s%s" % (m.group(1), m.group(2) or ""))
    return " ".join(dict.fromkeys(out))          # ไม่ซ้ำ + คงลำดับที่เจอ


def _esc(v) -> str:
    """กัน Google Sheets ตีข้อความเป็นสูตร — ข้อความจาก LINE ขึ้นต้นด้วย `=`/`+`/`-`/`@` ได้

    เขียนด้วย `USER_ENTERED` (เพื่อให้วันที่/เวลาเป็นค่าจริง เรียง-Pivot ได้) แต่แบบนั้น
    `=1+1` จะกลายเป็นสูตร และ `-ครับ` จะกลายเป็น `#ERROR!` → ใส่ `'` นำหน้าให้เป็นข้อความล้วน
    """
    s = "" if v is None else str(v)
    s = s.replace("\r\n", "\n").strip()
    return ("'" + s) if s[:1] in ("=", "+", "-", "@") else s


def _row(date="", time_="", code="", who="", role="", team="", text="",
         status="", kind="ข้อความ", src=SRC_BOT, note="", ref="") -> list:
    return [date, time_, _esc(code), _esc(who), role, _esc(team), _esc(text),
            _esc(status), kind, src, _esc(note), ref]


# ── Google Sheets: อ่าน / ต่อท้าย ──
def _api():
    from google.auth.transport.requests import Request as AuthRequest

    from dashboard.services.google_sheets import SHEETS_API, _get_credentials
    creds = _get_credentials()
    creds.refresh(AuthRequest())
    return SHEETS_API, {"Authorization": "Bearer %s" % creds.token}


def _read(tab, rng="A1:AZ5000") -> list[list[str]]:
    import urllib.parse

    import requests
    base, head = _api()
    q = urllib.parse.quote("%s!%s" % (tab, rng))
    r = requests.get("%s/%s/values/%s?valueRenderOption=FORMATTED_VALUE" % (base, SHEET_ID, q),
                     headers=head, timeout=30)
    if r.status_code != 200:
        raise Exception("อ่านแท็บ '%s' ไม่ได้: %s %s" % (tab, r.status_code, r.text[:200]))
    return r.json().get("values", [])


def _append(tab, rows) -> int:
    """ต่อท้ายแท็บ (ไม่ clear) — แบ่งชุดละ 500 แถว กัน payload ใหญ่เกิน"""
    import urllib.parse

    import requests

    from dashboard.services.google_sheets import ensure_sheet_tab
    if not rows:
        return 0
    ensure_sheet_tab(SHEET_ID, tab)
    base, head = _api()
    head = {**head, "Content-Type": "application/json"}
    q = urllib.parse.quote("%s!A1" % tab)
    url = ("%s/%s/values/%s:append?valueInputOption=USER_ENTERED&insertDataOption=INSERT_ROWS"
           % (base, SHEET_ID, q))
    done = 0
    for i in range(0, len(rows), 500):
        chunk = rows[i:i + 500]
        r = requests.post(url, headers=head, json={"values": chunk}, timeout=60)
        if r.status_code != 200:
            raise Exception("เขียนแท็บ '%s' ไม่ได้: %s %s" % (tab, r.status_code, r.text[:200]))
        done += len(chunk)
    return done


def _col_letter(i) -> str:
    s = ""
    while True:
        s, i = chr(65 + i % 26) + s, i // 26 - 1
        if i < 0:
            return s


def _ensure_header(tab) -> set:
    """ทำให้แท็บมีหัวตาราง แล้วคืน `รหัสอ้างอิง` ที่มีอยู่แล้ว (ใช้กันเขียนซ้ำ)

    ★ อ่าน **เฉพาะคอลัมน์รหัสอ้างอิง ช่วงกว้าง** ไม่ใช่ทั้งตาราง —
    ถ้าอ่านแบบจำกัดแถว (เช่น A1:AZ5000) วันที่แท็บโตเกินนั้น ตัวกันเขียนซ้ำจะมองไม่เห็นแถวเก่า
    แล้ว **เขียนซ้ำแบบเงียบๆ** (แท็บนี้โตทุกวัน · นำเข้าครั้งแรกก็ 1,688 แถวแล้ว)
    """
    from dashboard.services.google_sheets import ensure_sheet_tab
    ensure_sheet_tab(SHEET_ID, tab)
    head = _read(tab, "A1:%s1" % _col_letter(REF_COL))
    if not head or not any(str(c).strip() for c in head[0]):
        _append(tab, [COLUMNS])
        return set()
    col = _col_letter(REF_COL)
    refs = _read(tab, "%s2:%s200000" % (col, col))
    return {str(r[0]).strip() for r in refs if r and str(r[0]).strip()}


# ── ทีมของแต่ละคน (จากทะเบียนพนักงาน) ──
def _team_map() -> dict:
    """{ชื่อเล่น → ทีม} — ทะเบียนในระบบก่อน แล้วเติมจากชีตพนักงาน (กติกาเดียวกับ `people._load`)

    ต้องอ่าน 2 ที่ เพราะถ้าพึ่ง `Employee` อย่างเดียว เครื่องที่ยังไม่มีข้อมูลในฐานข้อมูล
    (เช่นตอนนำเข้าย้อนหลังจากเครื่อง dev) จะได้คอลัมน์ทีมว่างทั้งตาราง **และเติมย้อนหลังไม่ได้อีก**
    เพราะรอบถัดไปแถวนั้นถูกข้ามด้วยกติกากันเขียนซ้ำ
    """
    out = {}
    try:
        from .models import Employee
        for nick, pos in Employee.objects.values_list("nickname", "position"):
            if nick and str(pos or "").strip().startswith("ทีม"):
                out[_norm_nick(nick)] = str(pos).strip()
    except Exception:
        pass                                  # ยังไม่ migrate / DB ล่ม = ใช้ชีตอย่างเดียว
    try:
        from dashboard.services.google_sheets import EMPLOYEE_COL as EM, fetch_sheet
        for r in fetch_sheet("employees"):
            def c(i):
                return str(r[i]).strip() if i < len(r) and r[i] else ""
            nick, pos = c(EM.nickname) or c(EM.display_name), c(EM.position)
            if nick and pos.startswith("ทีม"):
                out.setdefault(_norm_nick(nick), pos)      # ทะเบียนในระบบชนะ
    except Exception:
        pass
    return out


# ── แหล่งที่ 1: แชทที่บอทเก็บไว้แล้ว (ไปข้างหน้า) ──
def rows_from_chat(days=120, group_id="", seniors=None) -> tuple[list, dict]:
    from .models import GroupChat
    gid = (group_id or cfg()["group_id"]).strip()
    sen = seniors if seniors is not None else cfg()["seniors"]
    teams = _team_map()
    since = timezone.now() - timezone.timedelta(days=int(days))

    out, stat = [], {"senior": 0, "junior": 0, "withCode": 0, "unnamed": 0}
    # เรียง `sent_at, id` — ข้อความในกลุ่มมาวินาทีเดียวกันได้ ถ้าเรียงแค่เวลาลำดับจะสลับ
    # ทุกครั้งที่รัน แล้วแถวในชีต (ซึ่งเขียนต่อท้ายอย่างเดียว) จะไม่เรียงตามบทสนทนาจริง
    qs = (GroupChat.objects.filter(group_id=gid, sent_at__gte=since)
          .order_by("sent_at", "id")
          .values("message_id", "sender_id", "sender_name", "msg_type", "text",
                  "has_media", "sent_at"))
    for m in qs:
        from . import people
        who = people.safe_name(m["sender_name"]) or ""
        if not who or who == "ไม่ทราบชื่อ":
            # ไม่มีชื่อ = เก็บไว้แต่ทำเครื่องหมาย (ห้ามเอา sender_id มาโชว์แทน)
            who, stat["unnamed"] = "(ไม่ทราบชื่อ)", stat["unnamed"] + 1
        role = SENIOR if is_senior(who, sen) else JUNIOR
        stat["senior" if role == SENIOR else "junior"] += 1
        local = timezone.localtime(m["sent_at"])
        code = case_code(m["text"])
        if code:
            stat["withCode"] += 1
        kind = MSG_TYPE_TH.get(m["msg_type"] or "", m["msg_type"] or "")
        text = m["text"] or ""
        if not text and m["has_media"]:
            text = "(ส่ง%s — ไฟล์อยู่ใน LINE)" % (kind or "ไฟล์")
        out.append(_row(
            date=local.strftime("%Y-%m-%d"), time_=local.strftime("%H:%M"), code=code,
            who=who, role=role, team=teams.get(_norm_nick(who), ""), text=text,
            kind=kind or "ข้อความ", src=SRC_BOT, ref="line:%s" % m["message_id"]))
    return out, stat


# ── แหล่งที่ 2: แท็บเดิม (ย้อนหลัง · อ่านครั้งเดียวก็พอ แต่รันซ้ำได้) ──
def _old_date(v) -> str:
    """แปลงวันที่ของแท็บเดิม → `YYYY-MM-DD` — ปนกัน 4 แบบ: 17/04/2569 (พ.ศ.) ·
    10/4/2026 · 2026-04-03 · 01/04/26 · แปลงไม่ได้ = คืนค่าเดิม (ไม่ทิ้งแถว)"""
    s = str(v or "").strip()
    if not s:
        return ""
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", s)
    if m:
        return "%04d-%02d-%02d" % tuple(int(x) for x in m.groups())
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})$", s)
    if not m:
        return s
    d, mo, y = (int(x) for x in m.groups())
    if y > 2500:                      # พ.ศ. → ค.ศ.
        y -= 543
    elif y < 100:                     # 2 หลัก ("26" = 2026 · ข้อมูลชุดนี้เริ่มปี 2026)
        y += 2500 - 543 if y > 60 else 2000
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return s
    return "%04d-%02d-%02d" % (y, mo, d)


def _clean_old_code(v) -> str:
    """ล้างขยะที่ระบบเดิมทิ้งไว้ในช่องรหัสเคส (วัดจริง 27/09: 22 จาก 1,424 แถว)

    - `"9057 (no code)"` → `"9057"` (มาร์คของบอทตัวเดิมตอนหารหัสไม่เจอ · 1 แถว)
    - `"-4093"` → `"4093"` (ขีดนำหน้าคือคำนำหน้าที่หลุดไป · 21 แถว) → เทียบกับรหัสอื่นได้
    - **ไม่แตะค่าที่เป็นป้ายจริง** เช่น `หน้าร้าน_Jay_0407` · `ต่างชาติ_แคเมอรูน`
    """
    s = str(v or "").strip()
    s = re.sub(r"\s*\(\s*no\s*code\s*\)\s*$", "", s, flags=re.I)
    return s.strip().lstrip("-").strip()


def _old_time(v) -> str:
    m = re.match(r"^(\d{1,2}):(\d{2})", str(v or "").strip())
    return "%02d:%s" % (int(m.group(1)), m.group(2)) if m else ""


def rows_from_old_sheet(seniors=None) -> tuple[list, dict]:
    """แตกแท็บเดิม 1 แถว → หลายแถว (ข้อความจูเนียร์ + ความเห็นซีเนียร์แต่ละคน + คำตอบบอท)"""
    from . import people
    sen = seniors if seniors is not None else cfg()["seniors"]
    teams = _team_map()
    raw = _read(OLD_TAB)
    body = [r for r in raw[1:] if any(str(c).strip() for c in r)] if raw else []

    def g(r, i):
        return str(r[i]).strip() if i < len(r) and r[i] is not None else ""

    out = []
    stat = {"oldRows": len(body), "junior": 0, "senior": 0, "bot": 0, "misplaced": 0,
            "matched": 0, "unmatchedNames": {}}
    for idx, r in enumerate(body):
        ln = idx + 2                                     # เลขแถวจริงในชีต (นับหัวตาราง)
        date, time_ = _old_date(g(r, O_DATE)), _old_time(g(r, O_TIME))
        code, status = _clean_old_code(g(r, O_CODE)), g(r, O_STATUS)

        # คนพูด: เทียบชื่อ LINE กับทะเบียน (ไอดีในชีตเป็นของบอทที่ปิดไปแล้ว ใช้เทียบไม่ได้)
        dn, short = g(r, O_DISPLAY), g(r, O_SELLER)
        who = people.employee_nick_by_name(dn) or people.employee_nick_by_name(short)
        if who:
            stat["matched"] += 1
        else:
            who = people.safe_name(people.nickname_for("", dn or short)) or ""
            if dn or short:
                key = dn or short
                stat["unmatchedNames"][key] = stat["unmatchedNames"].get(key, 0) + 1
        who = who or "(ไม่ระบุ)"

        note = []
        if g(r, O_LEVEL):
            note.append("ระดับ %s" % g(r, O_LEVEL))
        if g(r, O_TYPE) in KNOWN_TYPES:
            note.append(g(r, O_TYPE))
        if g(r, O_COUNT):
            note.append("อัปเดต %s ครั้ง" % g(r, O_COUNT))

        text = g(r, O_TEXT)
        if text:
            role = SENIOR if is_senior(who, sen) else JUNIOR
            stat["senior" if role == SENIOR else "junior"] += 1
            out.append(_row(date=date, time_=time_, code=code, who=who, role=role,
                            team=teams.get(_norm_nick(who), ""), text=text, status=status,
                            src=SRC_OLD, note=" · ".join(note), ref="old:%d:msg" % ln))

        # ความเห็นซีเนียร์ที่เคยกระจายอยู่ 4 คอลัมน์ → แถวละคน (เพิ่มคนที่ 5 ไม่ต้องแก้อะไร)
        for col, name in O_SENIOR_COLS.items():
            v = g(r, col)
            if not v or v == "-":
                continue
            stat["senior"] += 1
            out.append(_row(date=date, time_=time_, code=code, who=name, role=SENIOR,
                            team=teams.get(_norm_nick(name), ""), text=v, status=status,
                            src=SRC_OLD, ref="old:%d:s-%s" % (ln, name)))

        # คำตอบของบอท AI ตัวเดิม — เก็บไว้เป็นประวัติ ระบุที่มาชัดว่าไม่ใช่คนพูด
        if g(r, O_BOT):
            stat["bot"] += 1
            out.append(_row(date=date, time_=time_, code=code, who=BOT, role=BOT,
                            text=g(r, O_BOT), status=status, src=SRC_OLD_AI,
                            ref="old:%d:bot" % ln))

        # ★ ช่อง "ประเภทเหตุการณ์" ถูกใช้ผิด — มีข้อความจริงยัดมา 38 แถว
        #   ไม่รู้ว่าใครพูด → ลงเป็น "(ไม่ระบุ)/(ไม่ทราบ)" ให้คนไปตรวจเอง **ไม่เดา**
        t = g(r, O_TYPE)
        if t and t not in KNOWN_TYPES and t not in _ODD_SKIP:
            stat["misplaced"] += 1
            out.append(_row(date=date, time_=time_, code=code, who="(ไม่ระบุ)", role=UNKNOWN,
                            text=t, status=status, src=SRC_OLD_MISPLACED,
                            ref="old:%d:odd" % ln))
    return out, stat


# ── ตัวสั่งงาน ──
def sync(days=120, include_old=False, dry_run=False, group_id="", seniors=None) -> dict:
    """เก็บแชทใหม่ (+ ข้อมูลเก่าถ้าสั่ง) ลงแท็บใหม่ — **ข้ามของที่เขียนไปแล้ว รันซ้ำได้**"""
    c = cfg()
    tab = c["tab"]
    sen = seniors if seniors is not None else c["seniors"]
    res = {"tab": tab, "group": (group_id or c["group_id"]), "seniors": sen,
           "dryRun": bool(dry_run)}

    rows, res["chat"] = rows_from_chat(days=days, group_id=group_id, seniors=sen)
    if include_old:
        old, res["old"] = rows_from_old_sheet(seniors=sen)
        rows = old + rows                       # ของเก่าขึ้นก่อน (เรียงตามเวลาอ่านง่าย)

    have = set() if dry_run else _ensure_header(tab)
    fresh = [r for r in rows if r[REF_COL] not in have]
    res.update({"candidates": len(rows), "new": len(fresh),
                "skipped": len(rows) - len(fresh)})
    if dry_run:
        res["preview"] = fresh[:8]
        return res
    res["written"] = _append(tab, fresh) if fresh else 0
    return res


def maybe_sync(now=None) -> str:
    """เรียกจาก `cron_tick` — ทำวันละครั้ง · **ปิดไว้ = ไม่ทำอะไร** · ล้มแล้วไม่ลากงานอื่น

    ทำไมต้องมี: แชทดิบถูกลบเมื่อครบ 90 วัน → ถ้าไม่ซิงก์ ข้อมูลโค้ชจะหายเองเงียบๆ
    """
    c = cfg()
    if not c["enabled"]:
        return ""
    today = (now or timezone.localtime()).date().isoformat()
    try:
        raw = get_kv(SYNC_KEY) or {}
        last = raw.get("data", raw) if isinstance(raw, dict) else {}
        if isinstance(last, dict) and last.get("date") == today:
            return ""
    except Exception:
        pass
    try:
        r = sync(days=120)
        set_kv(SYNC_KEY, {"date": today, "new": r.get("new", 0), "ok": True})
        return "written=%s" % r.get("written", 0)
    except Exception as e:
        msg = str(e)[:200]
        try:
            set_kv(SYNC_KEY, {"date": today, "ok": False, "error": msg})
            from dashboard.services import eventlog
            eventlog.log(eventlog.CRON, name="ซิงก์บันทึกโค้ชเข้าชีต", ok=False, error=msg)
        except Exception:
            pass
        return "error: %s" % msg
