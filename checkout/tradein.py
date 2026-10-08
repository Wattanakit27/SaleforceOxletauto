"""เคสรับซื้อ/เทิร์นรถ → ชีต "ซื้อขายเทิร์นรถ" — ย้ายมาจาก workflow n8n (8 ต.ค.69 · เจ้าของสั่ง)

เดิม: LINE webhook → n8n (Extract → Get Profile → Resolve Roles → Build Sheet Row → เขียนชีต)
     · **n8n หยุดเขียนเงียบๆ ตั้งแต่ 5 ต.ค.69** โดยไม่มีใครรู้ 3 วัน
ตอนนี้: เว็บเราเก็บทุกข้อความของห้องเคสจัดซื้ออยู่แล้ว (`GroupChat`) → อ่านแล้วเขียนชีตเอง
     · ทำทันทีที่ข้อความเข้า (`_checkout_ingest`) + cron ทุกนาทีเก็บตกที่พลาด
     · ล้ม = จดไว้ + หน้าสถานะระบบร้อง · ไม่ขยับตัวชี้ จนกว่าจะเขียนสำเร็จ (ลองใหม่รอบถัดไป)

ตัวอ่านใบเคส = **แปลตรงตัวจาก n8n** (Resolve Roles V11 + Build Sheet Row v22.1 · deploy/n8n_tradein_*.js)
  มีเทสต์เทียบผลกับโค้ด JS ตัวจริงทีละข้อความ (scripts/test_tradein.py)
  ⚠️ แปลจาก JS ต้องระวัง regex: `\\b` ของ JS ไม่นับอักษรไทยเป็นตัวอักษร (Python นับ) ·
     `\\d` ของ Python รับเลขไทย · `$` ของ Python ยอมให้มี \\n ท้าย → ใช้ `_NW`/`[0-9]`/`\\Z` แทน

ต่างจาก n8n โดยตั้งใจ (ดีขึ้น ไม่ใช่พลาด):
  - ใบเคสรหัสที่มีในแท็บแล้ว (โพสต์ซ้ำ) = ไม่เพิ่มแถวซ้ำ (n8n เพิ่มซ้ำ)
  - ใบเคสที่ไม่มีรหัสเลย = ไม่เพิ่มแถว (n8n อาจได้แถวไม่มี Code ถ้าแชทมีเบอร์)
  - คอมเมนต์โอนเคส ("…ดูแทน @หมีน้อย" / "เปลี่ยนเป็นของพี่ต๊าด @…") = เปลี่ยนช่องจัดซื้อ (M) ตาม
  - วันที่/แท็บ คิดจากเวลาที่ข้อความเข้ากลุ่ม (n8n ใช้เวลาที่ประมวลผล)
"""
import re
from datetime import datetime

from django.utils import timezone

# ── ห้องเคสจัดซื้อ (ไอดีฝั่งบอท OxletautoGiveLead · ยืนยันกับ checkout_linegroup 8 ต.ค.69) ──
#   รายชื่อที่รับ — กลุ่มอื่นข้ามหมด · owner = เติมช่อง "จัดซื้อ" เมื่อไม่มีใครถูก @tag
PURCHASE_GROUPS = {
    "C0ad44e22acf81cd6af619da15ffb363d": {"name": "เคสHOT (พี่หมี)", "caseType": "HOT", "owner": "พี่หมี"},
    "C6a6450337d5588fdb0882f57d2a09cd4": {"name": "เคสHOT (พี่ต๊าด)", "caseType": "HOT", "owner": "พี่ต๊าด"},
    "Cd308fd5c3e1f4c8948856a81fa911332": {"name": "เคสVERY HOT", "caseType": "VERY HOT", "owner": ""},
}

TEST_TAB = "TestBot"
KV_CONFIG = "tradein_config"      # {"enabled": bool, "target": "test"|"month"}
KV_STATE = "tradein_state"        # {"last_id": int} — GroupChat.id ล่าสุดที่จัดการแล้ว
KV_LAST = "tradein_last"          # ผลรอบล่าสุด (หน้าสถานะระบบอ่าน)
# ข้อความก่อนเวลานี้ถูกเติมลง TestBot ย้อนหลังด้วยมือไปแล้ว (8 ต.ค.69 12:40 · ถึง SC-1301)
INITIAL_SINCE = "2026-10-08T12:34:00+07:00"
MAX_ROW = 3000
_LOCK_KEY = 8_100_812              # Postgres advisory lock — กันประมวลผลซ้อน (webhook + cron)

_NW = r"(?<![A-Za-z0-9_])"        # = \b ของ JS (ขอบคำนับเฉพาะ A-Z a-z 0-9 _)
_NWE = r"(?![A-Za-z0-9_])"
_CODE = re.compile(_NW + r"([A-Za-z]{1,8})\s*-\s*([0-9]{1,8})" + _NWE)
_CODE_HEAD = re.compile(r"^[A-Za-z]{1,8}\s*-\s*[0-9]{1,8}" + _NWE)
_PHONE = re.compile(r"0[0-9]{8,9}")
_TAG = re.compile(r"@([^\n@]+)")
_REASSIGN = re.compile(r"ดูแทน|เปลี่ยนเป็นของ|โอนให้")
MANUAL_MAPPING = {"miwa": "มิว", "wattanakit": "เบียร์"}


# ════════════════════════════════════════════════════════════════════
# ตัวอ่าน (แปลจาก n8n)
# ════════════════════════════════════════════════════════════════════
def clean(v):
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip()


def has_phone(t):
    return bool(_PHONE.search(re.sub(r"[-\s]", "", str(t or ""))))


def extract_phone(t):
    m = _PHONE.search(re.sub(r"[-\s]", "", str(t or "")))
    return m.group(0) if m else ""


def pick_code(t):
    m = _CODE.search(str(t or ""))
    return re.sub(r"\s+", "", ("%s-%s" % (m.group(1), m.group(2))).upper()) if m else ""


def pick_tag(t):
    m = _TAG.search(str(t or ""))
    return clean(m.group(1)) if m else ""


def map_purchaser(tag):
    s = str(tag or "").lower()
    if not s:
        return ""
    if "tard" in s or "tad" in s or "ต๊าด" in s or "ตาด" in s:
        return "พี่ต๊าด"
    if "หมี" in s or "bear" in s:
        return "พี่หมี"
    if "miwa" in s or "miw" in s or "มิว" in s:
        return "มิว"
    return ""


def resolve_sender(nick_by_id="", display_name=""):
    """Resolve Roles V11 — ชื่อเล่นจากทะเบียน (userId) ชนะ ถ้าไม่ใช่ชื่อ LINE ที่ถูกตั้งเป็นชื่อเล่นไปเฉยๆ"""
    nick, disp = clean(nick_by_id), clean(display_name)
    if nick and nick.lower() != disp.lower():
        return nick
    sender = MANUAL_MAPPING.get(disp.lower(), "")
    return sender or nick or disp


_CAR_DROPDOWN = [
    "Civic", "Revo cab ตัวเตี้ย", "Fortuner", "D Max", "Mazda2",
    "City 4 ประตู", "City 5 ประตู", "Benz", "BMW", "Brio",
    "Yaris Ativ", "Yaris 5 ประตูตัวเก่า", "Sylphy", "CRV", "Vios",
    "MuX", "Revo 4 ประตู ตัวสูง", "Almera", "Jazz", "New Yaris 5 ประตู",
    "Pajero", "Revo 4 ประตู ตัวเตี้ย", "Xpander", "Accord",
    "Altis", "Innova", "CX-3", "Ford Ranger", "Everest",
    "New Commuter", "Corolla Cross", "Mu7", "HRV", "Mirage",
    "Mazda3", "Vellfire", "Vigo", "Almera Turbo", "Almera Turbo VL",
    "Commuter", "Yaris Cross", "Alphard", "Camry", "Hyundai",
    "Majesty", "MG", "Prius", "Ventury", "Veloz",
    "Attrage", "BRV", "CHR", "CX-30", "Revo cab ตัวสูง",
    "XL7", "Terra", "Teana", "Vigo LPG", "Swift",
]
_KEYWORD_MAP = [
    (r"civic|ซีวิค", "Civic"), (r"accord|แอคคอร์ด", "Accord"), (r"cr-?v|ซีอาร์วี", "CRV"),
    (r"hr-?v|เอชอาร์วี", "HRV"), (r"jazz|แจ๊ส", "Jazz"), (r"brio|บริโอ", "Brio"), (r"br-?v|บีอาร์วี", "BRV"),
    (r"fortuner|ฟอร์จูนเนอร์|ฟอจูนเนอร์|fotuner", "Fortuner"), (r"altis|อัลติส", "Altis"),
    (r"camry|แคมรี่", "Camry"), (r"vios|วีออส", "Vios"), (r"innova|อินโนว่า", "Innova"),
    (r"alphard|อัลฟาร์ด", "Alphard"), (r"vellfire|เวลไฟร์", "Vellfire"), (r"c-?hr|ซีเอชอาร์", "CHR"),
    (r"prius|พรีอุส", "Prius"), (r"veloz|เวโลซ", "Veloz"), (r"majesty|มาเจสตี้", "Majesty"),
    (r"sylphy|ซิลฟี่", "Sylphy"), (r"teana|ทีน่า", "Teana"), (r"terra|เทอร์ร่า", "Terra"),
    (r"mazda\s*3|มาสด้า\s*3", "Mazda3"), (r"mazda\s*2|มาสด้า\s*2", "Mazda2"),
    (r"cx-?30|ซีเอ็กซ์\s*30", "CX-30"), (r"cx-?3|ซีเอ็กซ์\s*3", "CX-3"),
    (r"d-?\s*max|ดีแม็กซ์|ดีแมก", "D Max"), (r"mu-?x|มิว\s*เอ็กซ์", "MuX"), (r"mu-?7|mu\s*7|มิว\s*7", "Mu7"),
    (r"pajero|ปาเจโร่", "Pajero"), (r"xpander|เอ็กซ์แพนเดอร์", "Xpander"), (r"mirage|มิราจ", "Mirage"),
    (r"attrage|แอททราจ", "Attrage"), (r"ranger|เรนเจอร์", "Ford Ranger"), (r"everest|เอเวอเรสต์", "Everest"),
    (r"swift|สวิฟท์", "Swift"), (r"xl-?7|เอ็กซ์แอล\s*7", "XL7"),
    (r"benz|เบนซ์|mercedes", "Benz"), (r"bmw|บีเอ็ม", "BMW"), (r"hyundai|ฮุนได", "Hyundai"),
    (r"mg|เอ็มจี", "MG"), (r"ventury|เวนจูรี่", "Ventury"),
]
_KEYWORD_MAP = [(re.compile(p), v) for p, v in _KEYWORD_MAP]


def match_car_dropdown(car_text):
    if not car_text or not car_text.strip() or car_text == "-":
        return ""
    lower = re.sub(r"[-\s]+", " ", car_text.lower()).strip()
    s = lambda p: re.search(p, lower)
    if s(r"revo|รีโว"):
        if s(r"cab|แค็บ|แคป") and s(r"สูง|4x4|ยก"):
            return "Revo cab ตัวสูง"
        if s(r"cab|แค็บ|แคป"):
            return "Revo cab ตัวเตี้ย"
        if s(r"4\s*ประตู") and s(r"สูง|4x4|ยก"):
            return "Revo 4 ประตู ตัวสูง"
        if s(r"4\s*ประตู"):
            return "Revo 4 ประตู ตัวเตี้ย"
        if s(r"สูง|4x4|ยก"):
            return "Revo 4 ประตู ตัวสูง"
        return "Revo cab ตัวเตี้ย"
    if s(r"vigo|วีโก้"):
        return "Vigo LPG" if s(r"lpg|แก๊ส") else "Vigo"
    if s(r"yaris|ยาริส"):
        if s(r"cross|ครอส"):
            return "Yaris Cross"
        if s(r"ativ|เอทีฟ|เอทิฟ"):
            return "Yaris Ativ"
        if s(r"new|ใหม่") and s(r"5\s*ประตู"):
            return "New Yaris 5 ประตู"
        if s(r"5\s*ประตู|hatchback|แฮทช์แบ็ค"):
            return "Yaris 5 ประตูตัวเก่า" if s(r"เก่า|old") else "New Yaris 5 ประตู"
        return "Yaris Ativ"
    if s(r"almera|อัลเมร่า"):
        if s(r"turbo\s*vl"):
            return "Almera Turbo VL"
        return "Almera Turbo" if s(r"turbo|เทอร์โบ") else "Almera"
    if s(r"city|ซิตี้"):
        if s(r"5\s*ประตู|hatchback|แฮทช์แบ็ค"):
            return "City 5 ประตู"
        return "City 4 ประตู"
    if s(r"commuter|คอมมิวเตอร์"):
        return "New Commuter" if s(r"new|ใหม่") else "Commuter"
    if s(r"corolla\s*cross|โครอลล่า\s*ครอส"):
        return "Corolla Cross"
    for rx, val in _KEYWORD_MAP:
        if rx.search(lower):
            return val
    for d in _CAR_DROPDOWN:
        if d.lower() in lower:
            return d
    return ""


def _match_channel(text):
    lower = (text or "").lower()
    if "facebook" in lower or "fb" in lower or "ส่วนตัว" in lower:
        return "เพจบ้านเก่า"
    if "เพจบ้านเก่า" in lower or "บ้านเก่า" in lower:
        return "เพจบ้านเก่า"
    if "เพจอ่อนนุช" in lower or "อ่อนนุช" in lower:
        return "เพจอ่อนนุช"
    if "line@" in lower or "ไลน์" in lower:
        return "Line@"
    if "หน้าร้านบ้านเก่า" in lower:
        return "หน้าร้านบ้านเก่า"
    if "หน้าร้านอ่อนนุช" in lower:
        return "หน้าร้านอ่อนนุช"
    if "เทิร์น" in lower or "เทริน" in lower:
        return "เทิร์นรถ"
    return ""


def _esc(v):
    s = str(v if v is not None else "")
    return "'" + s if re.match(r"[=+\-@]", s) else s


_SALES = re.compile(r"(?:^|(?<=[^A-Za-zก-๙])|(?<=เทิร์น)|(?<=เทริน)|(?<=จาก))(?:เซลล์|เซล|sale)\s*([^\s0-9][^\s]*)",
                    re.I)
_TURN = re.compile(r"^(?:เทิร์น|เทริน|จาก)\s*(?:เซลล์|เซล|sale)?\s*([^\s]+)", re.I)
_CAR_KEYWORDS = re.compile(
    r"civic|city|accord|crv|cr-v|hrv|hr-v|jazz|brio|brv|br-v|yaris|vios|altis|camry|fortuner|fotuner|revo|vigo|chr|"
    r"c-hr|alphard|vellfire|innova|commuter|attrage|sylphy|almera|teana|note|march|navara|mazda|cx-3|cx-5|cx-8|cx-30|"
    r"pajero|xpander|mirage|triton|d-max|dmax|mu-x|mux|mu-7|sienta|everest|ranger|bt-50|bt50|swift|xl7|terra|"
    r"ventury|veloz|mg|hyundai|benz|bmw|prius|majesty", re.I)


def build(text, group_id, sender_nick="", purchaser_nick="", at=None):
    """ใบเคส/คอมเมนต์ 1 ข้อความ → dict (หรือ None = ไม่ใช่เรื่องของเรา)

    = Resolve Roles V11 + Build Sheet Row v22.1 ของ n8n (ค่าเหมือนกันทุกช่อง · เทียบด้วยเทสต์)
    คืน {"mode": "case_form", "code", "row": [A..S]} หรือ {"mode": "purchase_comment", "code", "comment", "purchaser"}
    """
    grp = PURCHASE_GROUPS.get(group_id)
    if not grp:
        return None
    text = str(text or "").strip()          # n8n ส่งข้อความที่ trim แล้วเข้ามา (โหนด Extract)
    code = pick_code(text).upper()
    mode = "case_form" if has_phone(text) else "purchase_comment"     # Resolve Roles
    head = text.strip()
    if head.startswith("โค้ด"):
        mode = "case_form"
    elif _CODE_HEAD.match(head):
        mode = "purchase_comment"

    if mode == "purchase_comment":
        if not code:
            return None
        c = re.sub(r"^[A-Za-z]{1,8}\s*-\s*[0-9]{1,8}" + _NWE, "", text, count=1)
        c = re.sub(r"@[^\n]+\Z", "", c)
        c = re.sub(r"[@•★☆♡♥✨]", "", c)
        c = re.sub(r"\s+", " ", c).strip()
        return {"mode": "purchase_comment", "code": code, "comment": c, "purchaser": purchaser_nick}

    sender = sender_nick
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    code_line = next((ln for ln in lines if pick_code(ln) == code), lines[0] if lines else "")
    found = False
    if code_line:
        suffix = re.sub(code.replace("-", r"\s*-?\s*"), "", code_line, count=1, flags=re.I).strip()
        tm = _TURN.search(suffix)
        if tm:
            name = clean(tm.group(1))
            if name not in ("รถ", "ครับ", "ค่ะ", "คับ", "คาบ", "ka", "krub") and len(name) > 1:
                sender, found = name, True
    if not found:
        sm = _SALES.search(text)
        if sm:
            sender = clean(sm.group(1))

    model_raw = plate = customer = ch_cust = ch_raw = ads = ""
    parts, cur, in_prof = [], "", False

    def flush():
        nonlocal cur
        if cur:
            parts.append(cur.strip())
            cur = ""

    for line in lines:
        low = line.lower()
        if re.match(r"ราคา(กลาง|ตาราง)", line):
            flush()
            in_prof = False
            continue
        if low.startswith("ขายเพราะ") or low.startswith("เหตุผล") or low.startswith("สาเหตุ"):
            if cur:
                parts.append(cur.strip())
            cur = re.sub(r"^(ขายเพราะ|เหตุผลขาย|เหตุผล|สาเหตุ)\s*[:：]?\s*", "", line, count=1, flags=re.I).strip()
            in_prof = True
        elif low.startswith("เพิ่มเติม"):
            if cur:
                parts.append(cur.strip())
            cur = re.sub(r"^เพิ่มเติม\s*[:：]?\s*", "", line, count=1, flags=re.I).strip()
            in_prof = True
        elif low.startswith("หมายเหตุ"):
            if cur:
                parts.append(cur.strip())
            cur = re.sub(r"^หมายเหตุ\s*[:：]?\s*", "", line, count=1, flags=re.I).strip()
            in_prof = True
        elif low.startswith("รุ่น"):
            flush(); in_prof = False
            model_raw = re.sub(r"^รุ่น\s*[:：]?\s*", "", line, count=1, flags=re.I).strip()
        elif low.startswith("ทะเบียน"):
            flush(); in_prof = False
            plate = re.sub(r"^ทะเบียน\s*[:：]?\s*", "", line, count=1, flags=re.I).strip()
        elif low.startswith("ads"):
            flush(); in_prof = False
            ads = re.sub(r"^ads\s*[:：]?\s*", "", line, count=1, flags=re.I).strip()
        elif low.startswith("ช่องทาง"):
            flush(); in_prof = False
            ch_raw = re.sub(r"^ช่องทาง\s*[:：]?\s*", "", line, count=1, flags=re.I).strip()
        elif low.startswith("ชื่อลูกค้า"):
            flush(); in_prof = False
            raw = re.sub(r"^ชื่อลูกค้า\s*[:：]?\s*", "", line, count=1, flags=re.I).strip()
            if "/" in raw:
                p = raw.split("/")
                customer, ch_cust = clean(p[0]), clean(p[1])
            else:
                customer = raw
        elif in_prof and line:
            cur += " " + line.strip()
    if cur:
        parts.append(cur.strip())

    phone = extract_phone(text)
    if not model_raw:
        content = [ln for ln in lines if not pick_code(ln) and not extract_phone(ln) and "@" not in ln]
        for ln in content:
            if re.match(r"(ขายเพราะ|เหตุผล|เพิ่มเติม|หมายเหตุ|ทะเบียน|ads|ชื่อลูกค้า|ช่องทาง)", ln, re.I):
                continue
            if _CAR_KEYWORDS.search(ln):
                model_raw = ln
                break
        if not model_raw:
            for ln in content:
                if re.match(r"(ขายเพราะ|เหตุผล|เพิ่มเติม|หมายเหตุ|ทะเบียน|ads|ชื่อลูกค้า|ช่องทาง|เทิร์น|ขาย|รับซื้อ|เซลล์)",
                            ln, re.I):
                    continue
                model_raw = ln
                break
    if not plate:
        m = re.search(r"([ก-ฮ]{1,3}\s*-?\s*[0-9]{3,4}|[0-9]{1,2}[ก-ฮ]{2}\s*-?\s*[0-9]{3,4})", text)
        if m:
            plate = clean(re.sub(r"\s", "", m.group(0)))
    car_model = re.sub(r"^รุ่น\s*[:：]?\s*", "", clean(model_raw), count=1, flags=re.I)
    car_dd = match_car_dropdown(car_model)

    lead = re.search(r"(?:Lead\s*No|Ac\s*Lead|Ref\s*No)[^:]*[:\s]+([A-Za-z0-9-]+)", text, re.I)
    if (not customer or not customer.strip() or customer == "-") and lead:
        customer = lead.group(1).strip()

    prof = " ".join(parts) if parts else "-"
    prof = clean(prof)
    prof = re.sub(r"(เพิ่มเติม|หมายเหตุ|ขายเพราะ)\s*[:：]*\Z", "", prof, count=1, flags=re.I).strip()
    prof = re.sub(r"(ขายอย่างเดียว|ครับ|ค่ะ)", "", prof, flags=re.I).strip()
    prof = re.sub(r"@[^\s]+", "", prof).strip()
    prof = re.sub(r"[•★☆♡♥✨]", "", prof).strip()
    prof = re.sub(r"\s+", " ", prof).strip()
    prof = prof or "-"
    customer = customer if customer and customer.strip() else "-"
    ads = ads if ads and ads.strip() else "-"

    channel = _match_channel(ch_raw) or _match_channel(ch_cust) or _match_channel(text)
    sell = online = ""
    if code.startswith("OC"):
        online, sell = "Online", "ขายอย่างเดียว"
    elif code.startswith("SC"):
        online, channel, sell = "Offline", "หน้าร้านบ้านเก่า", "ขายอย่างเดียว"
    elif code.startswith("TC"):
        online, sell = "Offline", "เทิร์น"
    else:
        tl = text.lower()
        online = "Online" if "online" in tl else ("Offline" if "offline" in tl else "")
        sell = "เทิร์น" if ("เทิร์น" in text or "เทริน" in text) else ("ขายอย่างเดียว" if "ขาย" in text else "")

    purchaser = purchaser_nick or grp["owner"] or ""
    at = timezone.localtime(at) if at else timezone.localtime()
    row = [
        "%d/%d/%d" % (at.day, at.month, at.year),   # A วันที่
        "",                                        # B คันที่ — ทีมพิมพ์เอง
        _esc(code), _esc(car_model), _esc(plate),
        ("'" + phone) if phone else "",            # F เบอร์ (คงเลข 0 ตัวหน้า)
        _esc(customer), _esc(ads), _esc(channel), _esc(sell),
        "",                                        # K รับซื้อ/ไม่รับซื้อ — ว่างเสมอ (ทีมกรอก)
        _esc(online), _esc(purchaser), _esc(sender), _esc(grp["caseType"]), _esc(prof),
        "", "",                                    # Q คอมเมนท์ · R เหตุผล
        _esc(car_dd),                              # S car (รถตามสูตร)
    ]
    return {"mode": "case_form", "code": code, "row": row}


# ════════════════════════════════════════════════════════════════════
# เขียนชีต
# ════════════════════════════════════════════════════════════════════
def get_config():
    from dashboard.services.cache_store import get_kv
    cfg = {"enabled": True, "target": "test"}
    try:
        raw = get_kv(KV_CONFIG) or {}
        d = raw.get("data", raw) if isinstance(raw, dict) else {}
        if isinstance(d, dict):
            cfg.update({k: d[k] for k in ("enabled", "target") if k in d})
    except Exception:
        pass
    if cfg["target"] not in ("test", "month"):
        cfg["target"] = "test"
    return cfg


def set_config(**kw):
    from dashboard.services.cache_store import set_kv
    cfg = get_config()
    cfg.update({k: v for k, v in kw.items() if v is not None})
    set_kv(KV_CONFIG, cfg)
    return get_config()


def _kv(key):
    from dashboard.services.cache_store import get_kv
    try:
        raw = get_kv(key) or {}
        d = raw.get("data", raw) if isinstance(raw, dict) else {}
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


class Sheet:
    """แท็บในชีตจัดซื้อ + ดัชนีรหัสเคส → แถว

    ★ 8 ต.ค.69 — **ห้ามใช้ values:append** · Google เดาเองว่า "ตาราง" เริ่มคอลัมน์ไหน แล้วเดาผิด:
      แถวก่อนหน้ามี R กับ T ว่าง → คอลัมน์ S โดดเดี่ยว → มันถือว่าตารางเริ่มที่ S
      → เคสใหม่ 9 แถวแรกบน prod (OC-7634..7642) ไปลงคอลัมน์ S–AK แทน A–S
      · เทสต์กับแท็บว่างไม่เจอ เพราะแท็บว่างไม่มีอะไรให้เดา
      ตอนนี้: อ่าน A–S ใหม่ทุกครั้งก่อนเพิ่ม → หาแถวสุดท้ายที่มีค่าเอง → เขียน A{n}:S{n} ตรงๆ
    """

    def __init__(self, api, tab, first_row):
        self.api, self.tab, self.first = api, tab, first_row
        self._idx = None
        self.last = first_row - 1                      # แถวสุดท้ายที่มีค่าในช่วง A–S

    def _read(self):
        rows = self.api.get("'%s'!A%d:S%d" % (self.tab, self.first, MAX_ROW))
        idx, last = {}, self.first - 1
        for i, r in enumerate(rows):
            n = self.first + i
            if any(str(v).strip() for v in r):        # รวม B (คันที่) — ไม่ทับแถวที่ใครเริ่มพิมพ์ไว้
                last = n
            c = re.sub(r"\s+", "", str(r[2] if len(r) > 2 else "")).upper()
            if c:                                      # รหัสซ้ำ = แถวล่างสุด (ล่าสุด) ชนะ
                idx[c] = {"row": n,
                          "q": str(r[16]).strip() if len(r) > 16 else "",
                          "m": str(r[12]).strip() if len(r) > 12 else ""}
        self._idx, self.last = idx, last

    def index(self):
        if self._idx is None:
            self._read()
        return self._idx

    def append(self, code, row):
        import urllib.parse
        import requests
        self._read()                                   # อ่านสดก่อนเขียน — ทีมอาจเพิ่งพิมพ์แถวในแท็บเดียวกัน
        if code in self._idx:                          # ระหว่างนั้นมีคนลงรหัสนี้ไปแล้ว
            return self._idx[code]["row"]
        n = max(self.last + 1, self.first)
        if n > MAX_ROW:
            raise RuntimeError("แท็บ %s เต็มเกิน %d แถว" % (self.tab, MAX_ROW))
        rng = "'%s'!A%d:S%d" % (self.tab, n, n)
        url = "%s/values/%s" % (self.api.base, urllib.parse.quote(rng))
        r = requests.put(url, params={"valueInputOption": "USER_ENTERED"},
                         json={"values": [row]}, headers=self.api.h, timeout=60)
        if r.status_code != 200:
            raise RuntimeError("เพิ่มแถว %s ลง %s: HTTP %s %s" % (code, self.tab, r.status_code, r.text[:200]))
        upd = str(r.json().get("updatedRange", ""))
        if not re.search(r"!A%d(:|$)" % n, upd):
            raise RuntimeError("เพิ่มแถว %s ลง %s: Google บอกว่าเขียนที่ %s ไม่ใช่ A%d" % (code, self.tab, upd, n))
        self._idx[code] = {"row": n, "q": "", "m": row[12]}
        self.last = n
        return n


def _sheets_for(cfg, at, api):
    """แท็บที่เขียน + แท็บที่ค้นคอมเมนต์ (ตามลำดับ)"""
    from dashboard.services.purchase_followup import prev_month, tab_name
    if cfg["target"] == "month":
        at = timezone.localtime(at)
        cur = Sheet(api, tab_name(at.year, at.month), 3)
        py, pm = prev_month(at.year, at.month)
        return cur, [cur, Sheet(api, tab_name(py, pm), 3)]
    t = Sheet(api, TEST_TAB, 1)
    return t, [t]


def handle(msg, api, cache, cfg, write=True):
    """จัดการ GroupChat 1 แถว → ผลลัพธ์ (dict) · โยน exception เมื่อเขียนชีตล้ม (ให้ลองใหม่รอบหน้า)"""
    from .models import LineProfile
    nick = disp = ""
    try:
        if msg.sender_id:
            p = LineProfile.objects.filter(user_id=msg.sender_id).select_related("employee").first()
            if p:
                disp = p.display_name or ""
                nick = (p.employee.nickname if getattr(p, "employee", None) else "") or ""
    except Exception:
        pass
    sender = resolve_sender(nick, disp) or msg.sender_name
    # อ่านใบพัง = ข้ามข้อความนั้น (ไม่งั้นข้อความเดียวขวางคิวตลอดไป) · เขียนชีตพัง = โยนออกไปให้ลองใหม่
    try:
        b = build(msg.text, msg.group_id, sender, map_purchaser(pick_tag(msg.text)), msg.sent_at)
    except Exception as e:
        return {"action": "parse-error", "error": ("%s: %s" % (type(e).__name__, e))[:200]}
    if not b:
        return {"action": "skip"}
    target, lookup = _sheets_for(cfg, msg.sent_at or timezone.now(), api)
    target = cache.setdefault(target.tab, target)
    lookup = [cache.setdefault(s.tab, s) for s in lookup]

    if b["mode"] == "case_form":
        if not b["code"]:
            return {"action": "skip", "why": "ใบเคสไม่มีรหัส"}
        if b["code"] in target.index():
            return {"action": "dup", "code": b["code"], "tab": target.tab}
        if not write:
            return {"action": "add", "code": b["code"], "tab": target.tab, "row": b["row"]}
        n = target.append(b["code"], b["row"])
        return {"action": "add", "code": b["code"], "tab": target.tab, "sheetRow": n}

    # คอมเมนต์: หาแถวของเคส (แท็บเขียนก่อน แล้วเดือนก่อน)
    hit = None
    for s in lookup:
        if b["code"] in s.index():
            hit = (s, s.index()[b["code"]])
            break
    if not hit:
        return {"action": "comment-miss", "code": b["code"]}
    s, info = hit
    old, new = info["q"], b["comment"]
    upd = {}
    if new and not (old and (old == new or new in old)):
        upd["Q"] = (old + " / " + new) if old else new
    if b["purchaser"] and _REASSIGN.search(msg.text or "") and b["purchaser"] != info["m"]:
        upd["M"] = b["purchaser"]
    if not upd:
        return {"action": "comment-same", "code": b["code"]}
    if write:
        import requests
        data = [{"range": "'%s'!%s%d" % (s.tab, col, info["row"]), "values": [[v]]} for col, v in upd.items()]
        r = requests.post(api.base + "/values:batchUpdate", json={"valueInputOption": "RAW", "data": data},
                          headers=api.h, timeout=60)
        if r.status_code != 200:
            raise RuntimeError("เขียนคอมเมนต์ %s: HTTP %s %s" % (b["code"], r.status_code, r.text[:200]))
        if "Q" in upd:
            info["q"] = upd["Q"]
        if "M" in upd:
            info["m"] = upd["M"]
    return {"action": "comment", "code": b["code"], "tab": s.tab, "sheetRow": info["row"], "cols": sorted(upd)}


# ════════════════════════════════════════════════════════════════════
# วนประมวลผลข้อความที่ค้าง
# ════════════════════════════════════════════════════════════════════
class _Lock:
    def __init__(self):
        self.got = False

    def __enter__(self):
        from django.db import connection
        if connection.vendor != "postgresql":
            self.got = True
            return self
        with connection.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", [_LOCK_KEY])
            self.got = bool(cur.fetchone()[0])
        return self

    def __exit__(self, *a):
        from django.db import connection
        if self.got and connection.vendor == "postgresql":
            try:
                with connection.cursor() as cur:
                    cur.execute("SELECT pg_advisory_unlock(%s)", [_LOCK_KEY])
            except Exception:
                pass
        return False


def _cursor():
    """GroupChat.id ล่าสุดที่จัดการแล้ว — ครั้งแรก = ข้อความก่อน INITIAL_SINCE (เติมย้อนหลังด้วยมือไปแล้ว)"""
    from django.db.models import Max

    from .models import GroupChat
    st = _kv(KV_STATE)
    if isinstance(st.get("last_id"), int):
        return st["last_id"]
    since = datetime.fromisoformat(INITIAL_SINCE)
    return GroupChat.objects.filter(group_id__in=list(PURCHASE_GROUPS), sent_at__lt=since).aggregate(
        m=Max("id"))["m"] or 0


def pending_qs(after_id):
    from .models import GroupChat
    return (GroupChat.objects.filter(id__gt=after_id, group_id__in=list(PURCHASE_GROUPS),
                                     direction=GroupChat.IN, msg_type="text").order_by("id"))


def process_pending(limit=100, api=None):
    """เขียนข้อความที่ยังไม่ได้จัดการลงชีต · คืนสรุป — เรียกได้ถี่ (ไม่มีงาน = query เดียวจบ)"""
    from dashboard.services.cache_store import set_kv
    cfg = get_config()
    if not cfg["enabled"]:
        return {"skipped": "ปิดอยู่"}
    with _Lock() as lk:
        if not lk.got:
            return {"skipped": "อีกตัวกำลังทำอยู่"}
        last_id = _cursor()
        msgs = list(pending_qs(last_id)[:limit])
        if not msgs:
            return {"pending": 0}
        res = {"at": timezone.localtime().isoformat(timespec="seconds"), "target": cfg["target"],
               "processed": 0, "added": [], "comments": [], "dup": [], "miss": [], "error": ""}
        cache = {}
        try:
            if api is None:
                from dashboard.services.purchase_tabs import _Api
                api = _Api()
            for m in msgs:
                r = handle(m, api, cache, cfg)
                a = r.get("action")
                if a == "add":
                    res["added"].append(r["code"])
                elif a == "comment":
                    res["comments"].append(r["code"])
                elif a == "dup":
                    res["dup"].append(r["code"])
                elif a == "comment-miss":
                    res["miss"].append(r["code"])
                elif a == "parse-error":
                    res.setdefault("parseErrors", []).append({"id": m.id, "error": r["error"]})
                last_id = m.id
                res["processed"] += 1
                set_kv(KV_STATE, {"last_id": last_id})
        except Exception as e:
            res["error"] = ("%s: %s" % (type(e).__name__, e))[:300]
            try:
                from dashboard.services import eventlog
                eventlog.log(eventlog.CRON, name="บันทึกเคสรับซื้อลงชีต", ok=False, error=res["error"],
                             messageId=last_id)
            except Exception:
                pass
        res["lastId"] = last_id
        try:
            set_kv(KV_LAST, res)
        except Exception:
            pass
        return res


def maybe_process(data):
    """เรียกจาก webhook (ใน thread ของ `_checkout_ingest` หลังเก็บแชทแล้ว) — ทำเฉพาะเมื่อมีข้อความจากห้องจัดซื้อ"""
    s = str(data)
    if any(g in s for g in PURCHASE_GROUPS):
        return process_pending()
    return None


def pending_count(older_than_min=0):
    """ข้อความที่ยังไม่ได้จัดการ (หน้าสถานะระบบ) — older_than_min = นับเฉพาะที่ค้างเกิน N นาที"""
    from datetime import timedelta
    qs = pending_qs(_cursor())
    if older_than_min:
        qs = qs.filter(sent_at__lt=timezone.now() - timedelta(minutes=older_than_min))
    return qs.count()


# ════════════════════════════════════════════════════════════════════
# ซ่อมแถวที่ลงผิดคอลัมน์ (8 ต.ค.69 · ใช้ครั้งเดียวหลัง deploy ตัวแก้)
# ════════════════════════════════════════════════════════════════════
_SHIFT_CODE = re.compile(r"^[A-Za-z]{1,8}-[0-9]{1,8}$")
_SHIFT = 18            # values:append เดาว่าตารางเริ่มที่ S → ทุกช่องเลื่อนขวา 18 คอลัมน์ (A→S · C→U)


def find_shifted(api, tab, first):
    """แถวที่ A–R ว่างหมด แต่มีรหัสเคสอยู่ที่ U (= ช่อง C ที่เลื่อนไป 18 คอลัมน์)"""
    rows = api.get("'%s'!A%d:AN%d" % (tab, first, MAX_ROW))
    out = []
    for i, r in enumerate(rows):
        head = r[:_SHIFT]
        code = str(r[2 + _SHIFT]).strip() if len(r) > 2 + _SHIFT else ""
        if not any(str(v).strip() for v in head) and _SHIFT_CODE.match(code):
            out.append((first + i, code.upper()))
    below = 0
    if out:
        last_bad = out[-1][0]
        below = sum(1 for i, r in enumerate(rows) if first + i > last_bad and any(str(v).strip() for v in r[:19]))
    return out, below


def repair_shifted(apply=False, api=None):
    """ล้างแถวที่ลงผิดคอลัมน์ แล้วเขียนใหม่จากแชทเดิม (ต้นฉบับอยู่ใน GroupChat ครบ)

    เขียนใหม่ด้วยตัวอ่านเดียวกับปกติ (ไม่ย้ายค่าในชีต — ย้ายแล้วเบอร์โทรเสียเลข 0 / วันที่กลายเป็นตัวเลข)
    · ย้อนตัวชี้กลับไปที่ INITIAL_SINCE แล้วทำใหม่ — แถวที่ถูกอยู่แล้วกันซ้ำด้วยรหัส · คอมเมนต์ที่ลงแล้วไม่ต่อซ้ำ
    """
    from dashboard.services.cache_store import set_kv
    from dashboard.services.purchase_followup import tab_name
    cfg = get_config()
    if api is None:
        from dashboard.services.purchase_tabs import _Api
        api = _Api()
    if cfg["target"] == "month":
        now = timezone.localtime()
        tab, first = tab_name(now.year, now.month), 3
    else:
        tab, first = TEST_TAB, 1
    with _Lock() as lk:
        if not lk.got:
            return {"error": "อีกตัวกำลังเขียนชีตอยู่ ลองใหม่อีกครั้ง"}
        bad, below = find_shifted(api, tab, first)
        res = {"tab": tab, "rows": [n for n, _ in bad], "codes": [c for _, c in bad],
               "rowsBelow": below, "applied": False}
        if not bad or not apply:
            return res
        if below:
            res["error"] = ("มีแถวที่ถูกต้อง %d แถวอยู่ใต้แถวที่ลงผิด — ล้างแล้วจะเหลือช่องว่างกลางตาราง "
                            "ไม่ซ่อมให้อัตโนมัติ" % below)
            return res
        from dashboard.services.purchase_tabs import col_letter
        api.clear(["'%s'!%s%d:%s%d" % (tab, col_letter(_SHIFT), n, col_letter(_SHIFT + 18), n) for n, _ in bad])
        set_kv(KV_STATE, {})                       # ตัวชี้กลับไปที่ INITIAL_SINCE
        runs = []
        for _ in range(20):
            r = process_pending(api=api)
            runs.append(r)
            if r.get("error") or not r.get("processed"):
                break
        res.update(applied=True, added=sum((r.get("added") or [] for r in runs), []),
                   comments=sum((r.get("comments") or [] for r in runs), []),
                   error=next((r["error"] for r in runs if r.get("error")), ""))
        try:
            from dashboard.services import eventlog
            eventlog.log(eventlog.CRON, name="ซ่อมแถวเคสรับซื้อที่ลงผิดคอลัมน์", ok=not res["error"],
                         tab=tab, rows=res["rows"], added=res["added"])
        except Exception:
            pass
        return res
