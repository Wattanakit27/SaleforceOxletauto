# -*- coding: utf-8 -*-
"""ตารางเช็คชื่อเข้างาน → รูป → ส่งเข้า LINE — ★ 16 ก.ย.69 (เจ้าของขอ)

*"เรื่องสำคัญคือเป็นการสร้างตารางเช็คชื่อ รวบรวมชื่อของทุกคน คุณลองสร้างเองได้ไหม
โดยที่ไม่ต้องพึ่ง API นอก"*

**แทน workflow เดิมใน n8n ทั้งเส้น** (Google Sheets ×2 → รวมร่าง → สร้าง HTML → **hcti.io** → ส่ง LINE):
- ข้อมูลมาจาก **Postgres ของเรา** (`checkout_employee` + `checkout_checkin`) ไม่ใช่ชีต
- แปลง HTML → PNG ด้วย **Playwright ในเครื่องเราเอง** (ลงไว้อยู่แล้วสำหรับรายงานรายวัน)
  → **ไม่ต้องจ่าย/ไม่ต้องพึ่ง hcti.io** และ **ข้อมูลพนักงานไม่หลุดออกไปนอกบริษัท**
  (ของเดิมส่ง HTML ที่มีชื่อพนักงานทุกคนไปให้บริการภายนอกเรนเดอร์)
- ยังคงกติกาเดิมของ workflow ครบ: จัดกลุ่มตามทีม · ติ๊กเขียว/แดง · เผื่อสาย 5 นาที ·
  ข้ามคนที่วันนี้เป็นวันหยุด/ลา · **แท็กคนที่ถึงคิวมาทำงานแล้วแต่ยังไม่เช็คชื่อ**

★ ต่างจากของเดิม 2 อย่าง (ตั้งใจ):
1. **สาย/ตรงเวลาเทียบ "เวลาเข้างานของแต่ละคน"** — ของเดิมหัวตารางเขียน "9.00 น." ทั้งที่จริง
   มีทั้ง 8:00 / 8:30 / 9:00 → หัวตารางที่นี่เขียน "ตรงเวลา" และมีคอลัมน์บอกเวลาเข้างานจริง
2. **ผู้บริหารที่ติ๊ก "ไม่ต้องเช็คชื่อ" ไม่อยู่ในตาราง** (`Employee.track_checkin`)
"""
import os
import re

GRACE_MIN = 5          # เผื่อสาย 5 นาที (ตามกติกาเดิมใน workflow)
IMG_WIDTH = 520        # ความกว้างตาราง (px) — กว้างกว่านี้บนมือถืออ่านยาก
SCALE = 2              # ความคมของรูป

THAI_DAYS = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
THAI_MON = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
            "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]

# ลำดับทีมบนตาราง (ยกมาจาก workflow เดิม) · ทีมที่ไม่อยู่ในลิสต์ต่อท้ายให้อัตโนมัติ
TEAM_ORDER = ["ฝ่ายขาย", "ทีม A", "ทีม B", "ทีม C", "ออฟฟิศ อ่อนนุช", "ออฟฟิศ บ้านเก่า",
              "ทีมโปรดักชัน", "จัดซื้อ", "ช่างและคนงาน", "เด็กฝึกงาน", "นศ.ฝึกงาน"]

# หมายเหตุที่เป็น "ข้อความของระบบ" ไม่ใช่เรื่องของคน → ไม่เอาขึ้นตาราง (ตามกติกาเดิม)
_JUNK_NOTE = ("ไม่พบข้อมูลรูป", "no overlay text", "ไม่พบข้อมูลที่", "ไม่มีข้อมูล",
              "ไม่พบข้อมูล", "ไม่พบตัวหนังสื", "overlay text")
# หมายเหตุที่ "ลา/หยุด" = ไม่ต้องตามตัว
_LEAVE_NOTE = ("ลา", "หยุด", "สลับ")


def _mins(t):
    """"8:30" → 510 นาที · อ่านไม่ออกคืน None"""
    m = re.match(r"^\s*(\d{1,2})[:.](\d{2})", str(t or ""))
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def _hhmm(t):
    m = re.match(r"^\s*(\d{1,2})[:.](\d{2})", str(t or ""))
    return "%d:%02d" % (int(m.group(1)), int(m.group(2))) if m else ""


def _late_text(n):
    if n >= 60:
        h, mm = divmod(n, 60)
        return "สาย %d ชม." % h if not mm else "สาย %d ชม. %d นาที" % (h, mm)
    return "สาย %d นาที" % n


def _clean_note(s):
    s = str(s or "").strip()
    return "" if any(k in s.lower() for k in _JUNK_NOTE) else s


def collect(day=None) -> dict:
    """รวมข้อมูลของวันนั้น → `{date, dayName, groups, missing, counts}`

    `missing` = คนที่ **ถึงคิวมาทำงานวันนี้แล้วยังไม่เช็คชื่อ** (ตัดคนหยุด/ลาออกแล้ว) — เอาไปแท็ก
    """
    from django.utils import timezone
    from .models import CheckIn, Employee

    day = day or timezone.localdate()
    day_name = THAI_DAYS[day.weekday()]

    checks = {}
    orphan = []          # เช็คชื่อเข้ามาแต่จับคู่กับทะเบียนไม่ได้ — ต้องไม่ทำหาย
    for c in CheckIn.objects.filter(date_iso=day).select_related("employee"):
        if c.employee_id:
            checks[c.employee_id] = c
        else:
            orphan.append(c)

    groups, missing = {}, []
    for e in Employee.objects.filter(active=True, track_checkin=True).order_by("nickname"):
        c = checks.get(e.id)
        t_in = _hhmm(c.time_hm) if c else ""
        note = _clean_note((c.reason if c else "") or e.note)
        off_today = bool(e.day_off) and day_name in e.day_off
        on_leave = any(k in note for k in _LEAVE_NOTE)

        late = 0
        if t_in:
            a, b = _mins(t_in), _mins(e.work_start)
            if a is not None and b is not None and (a - b) > GRACE_MIN:
                late = a - b

        row = {"name": e.nickname, "workStart": _hhmm(e.work_start), "timeHm": t_in,
               "late": late, "off": off_today, "note": note,
               "unreadable": bool(c and c.status == "abnormal" and not t_in)}

        # ข้อความในช่องหมายเหตุ — เรียงตามความสำคัญ: สาย > ยังไม่มา > วันหยุด/ลา
        if t_in:
            row["note_show"] = _late_text(late) if late else ""
            if off_today:                      # วันหยุดแต่มาทำงาน — ต้องเห็น
                row["note_show"] = (row["note_show"] + " | " if row["note_show"] else "") + day_name
            elif note and (on_leave or late):
                row["note_show"] = (row["note_show"] + " | " if row["note_show"] else "") + note
        elif off_today:
            row["note_show"] = note or day_name
        elif on_leave:
            row["note_show"] = note
        else:
            row["note_show"] = ("ยังไม่เช็คชื่อ" + (" | " + note if note else ""))
            missing.append({"id": e.id, "name": e.nickname, "position": e.position,
                            "workStart": _hhmm(e.work_start)})

        groups.setdefault(e.position or "ไม่ระบุทีม", []).append(row)

    if orphan:
        groups["เช็คชื่อเข้ามาแต่ยังไม่มีในทะเบียน"] = [
            {"name": c.display_name or "ไม่ทราบชื่อ", "workStart": "", "timeHm": _hhmm(c.time_hm),
             "late": 0, "off": False, "note": "", "unreadable": False,
             "note_show": "ยังไม่ผูกกับทะเบียนพนักงาน"} for c in orphan]

    order = [t for t in TEAM_ORDER if t in groups] + sorted(t for t in groups if t not in TEAM_ORDER)
    ordered = [(t, groups[t]) for t in order]

    flat = [r for _, rs in ordered for r in rs]
    counts = {"total": len(flat),
              "ontime": sum(1 for r in flat if r["timeHm"] and not r["late"]),
              "late": sum(1 for r in flat if r["late"]),
              "missing": len(missing),
              "off": sum(1 for r in flat if r["off"] and not r["timeHm"])}
    return {"date": day, "dayName": day_name, "groups": ordered,
            "missing": missing, "counts": counts}


# ─────────────────────────── HTML → PNG ───────────────────────────

_TICK = ('<svg viewBox="0 0 24 24" width="15" height="15" fill="currentColor">'
         '<path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>')


def _esc(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def build_html(data: dict) -> str:
    """HTML ของตาราง — **ฟอนต์ใช้ของในเครื่อง ไม่ดึงจากเน็ต**

    ของเดิมโหลด Google Fonts ตอนเรนเดอร์ → ถ้าเน็ตเซิร์ฟเวอร์สะดุด ตัวหนังสือจะเพี้ยน
    บน VPS มี `fonts-thai-tlwg` ลงไว้แล้ว (ขั้นตอนติดตั้ง Playwright)
    """
    d = data["date"]
    title = "วันที่ %d %s %d" % (d.day, THAI_MON[d.month - 1], d.year + 543)

    body = ""
    for team, rows in data["groups"]:
        body += '<tr class="sec"><td colspan="5">%s</td></tr>' % _esc(team)
        for r in rows:
            ok_cell = late_cell = ""
            cls_note = ""
            if r["timeHm"] and not r["late"]:
                ok_cell = '<span class="ok">%s</span>' % _TICK
            elif r["late"]:
                late_cell = '<span class="bad">%s</span>' % _TICK
            elif r["off"] or not r["note_show"].startswith("ยังไม่"):
                cls_note = "off"                       # วันหยุด/ลา = ตัวอักษรน้ำเงิน
            else:
                late_cell = '<span class="bad">%s</span>' % _TICK
            body += (
                '<tr><td class="nm">%s</td><td class="ws">%s</td><td class="c">%s</td>'
                '<td class="c">%s</td><td class="nt %s">%s</td></tr>'
                % (_esc(r["name"]), _esc(r["workStart"] or "-"), ok_cell, late_cell,
                   cls_note, _esc(r["note_show"])))

    c = data["counts"]
    foot = ("มา %d คน (ตรงเวลา %d · สาย %d) · ยังไม่เช็คชื่อ %d · วันหยุด %d"
            % (c["ontime"] + c["late"], c["ontime"], c["late"], c["missing"], c["off"]))

    return """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#fff;font-family:'Sarabun','Noto Sans Thai','Leelawadee UI','Waree','Loma',Tahoma,sans-serif}
table{width:%(w)dpx;border-collapse:collapse;font-size:13px;background:#fff}
table,th,td{border:1px solid #333}
td{padding:3px 4px;text-align:center;vertical-align:middle;line-height:1.25}
.top{background:#dce6f1;text-align:center;font-weight:700;font-size:18px;padding:7px 4px}
.hd td{font-weight:600;padding:5px 6px;font-size:12.5px;background:#fff}
.sec td{background:#b8cce4;font-weight:700;padding:4px;font-size:13px}
.nm{width:104px;text-align:left;padding-left:8px;font-size:14px;font-weight:600}
.ws{width:58px;color:#555;font-size:11.5px}
td.c{width:66px}
.nt{width:188px;text-align:left;padding-left:8px;font-size:11px;color:#333}
.nt.off{color:#0070c0;font-weight:600}
.ok{color:#00b050}.bad{color:#f00}
.ft{background:#f4f6f9;font-size:11px;color:#444;padding:5px 8px;text-align:center}
tr{height:25px}
</style></head><body><table>
<tr><td colspan="5" class="top">%(title)s</td></tr>
<tr class="hd"><td>รายชื่อ</td><td>เข้างาน</td><td>ตรงเวลา</td><td>มาสาย</td><td>หมายเหตุ</td></tr>
%(body)s
<tr><td colspan="5" class="ft">%(foot)s</td></tr>
</table></body></html>""" % {"w": IMG_WIDTH, "title": _esc(title), "body": body, "foot": _esc(foot)}


def render_png(data: dict, out_path="") -> str:
    """HTML → PNG ด้วย Playwright ในเครื่อง · คืน path (ว่าง = ทำไม่ได้)

    ใช้ `set_content()` **ไม่ต้องเปิดเว็บเซิร์ฟเวอร์/ไม่ต้อง login** — ต่างจากการแคปการ์ด
    ในแดชบอร์ดที่ต้องเปิดหน้าเว็บจริง (ซึ่งเคยพังเพราะปุ่มแท็บย้ายที่)
    """
    from django.conf import settings

    if not out_path:
        d = os.path.join(settings.MEDIA_ROOT, "reports")
        os.makedirs(d, exist_ok=True)
        out_path = os.path.join(d, "checkin_%s.png" % data["date"].isoformat())

    html = build_html(data)
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        raise RuntimeError("ยังไม่ได้ติดตั้ง playwright (%s)" % e)

    # ★ ทางหนีทีไล่: ระบุตัวเบราว์เซอร์เองได้ด้วย env `PLAYWRIGHT_EXECUTABLE`
    #   เพราะ playwright แต่ละเวอร์ชันผูกเลข build ของ Chromium คนละตัว — พอ pip อัปเกรด
    #   แล้วยังไม่ได้ `playwright install` ใหม่ จะขึ้น "Executable doesn't exist" แล้วแคปไม่ได้เลย
    #   (เคยทำรายงานรายวันหยุดส่งมาแล้ว · ดู DEPLOY.md)
    exe = (os.environ.get("PLAYWRIGHT_EXECUTABLE") or "").strip()
    with sync_playwright() as p:
        kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
        if exe:
            kw["executable_path"] = exe
        b = p.chromium.launch(**kw)
        try:
            pg = b.new_page(viewport={"width": IMG_WIDTH + 40, "height": 900},
                            device_scale_factor=SCALE)
            pg.set_content(html, wait_until="load")
            el = pg.query_selector("table")
            el.screenshot(path=out_path)
        finally:
            b.close()
    return out_path


# ─────────────────────────── ส่งเข้า LINE ───────────────────────────

def _channel_of_token(token: str) -> str:
    """token → คีย์บัญชี (`crm` / `push` / …) — ใช้เลือกไอดีให้ตรง provider ตอนแท็ก"""
    try:
        from dashboard.services.line_channels import accounts
        for a in accounts():
            if a.get("token") == token:
                return a.get("key") or ""
    except Exception:
        pass
    return ""


def _mention_ids(missing, channel):
    """LINE user id ของคนที่ต้องแท็ก **เฉพาะไอดีฝั่งบัญชีที่กำลังส่ง**

    ⚠️ id ออกต่อ provider — เอา id ของบอทเดิมไปแท็กผ่านบอทใหม่ LINE จะปฏิเสธทั้งข้อความ
    """
    from .models import LineProfile

    out = {}
    if not missing:
        return out
    qs = LineProfile.objects.filter(employee_id__in=[m["id"] for m in missing])
    for p in qs:
        if channel and p.channel and p.channel != channel:
            continue
        out.setdefault(p.employee_id, p.user_id)
    return out


def build_messages(data: dict, image_url="", channel="", tag=True, mention=True) -> list:
    """ข้อความที่จะส่ง: รูปตาราง + (ถ้ามีคนยังไม่มา) ข้อความตามตัว

    `mention=False` → บอกเป็น "รายชื่อ" แทนการแท็ก · ใช้กับ **แชทส่วนตัว (U…)**
    เพราะ **LINE แท็กได้เฉพาะในกลุ่ม/ห้อง** — ยิง mention เข้าแชท 1:1 จะโดนปฏิเสธทั้งข้อความ
    (รูปก็ไม่ถึงด้วย เพราะส่งไปพร้อมกัน) ตอนทดสอบเลยต้องปิดการแท็กเอง
    """
    msgs = []
    if image_url:
        msgs.append({"type": "image", "originalContentUrl": image_url,
                     "previewImageUrl": image_url})

    miss = data["missing"]
    if not (tag and miss):
        return msgs

    ids = _mention_ids(miss, channel) if mention else {}
    tagged = [m for m in miss if ids.get(m["id"])]
    plain = [m for m in miss if not ids.get(m["id"])]

    if tagged:
        text, sub = "รบกวนเช็คชื่อด้วยครับ (%d):\n\n" % len(miss), {}
        for i, m in enumerate(tagged):
            k = "u%d" % (i + 1)
            text += "{%s}%s" % (k, " " if i < len(tagged) - 1 else "")
            sub[k] = {"type": "mention", "mentionee": {"type": "user", "userId": ids[m["id"]]}}
        msgs.append({"type": "textV2", "text": text, "substitution": sub})

    if plain:
        # แท็กไม่ได้ (แชทส่วนตัว หรือยังไม่เคยพิมพ์ผ่านบอทตัวนี้) → พิมพ์ชื่อไปแทน ดีกว่าเงียบหาย
        head = "รบกวนเช็คชื่อด้วยครับ (%d):\n" % len(miss) if not tagged else "ยังไม่เช็คชื่อ (แท็กไม่ได้):\n"
        t = head + "\n".join(
            "• %s%s" % (m["name"], " (%s)" % m["position"] if m["position"] else "") for m in plain)
        msgs.append({"type": "text", "text": t})
    return msgs


def send(target_id: str, day=None, tag=True) -> tuple:
    """สร้างรูป + ส่งเข้า LINE · คืน `(ok, ข้อความสถานะ)`

    ⚠️ **LINE ต้องดึงรูปจาก URL https สาธารณะ → ส่งได้จริงเฉพาะบนเซิร์ฟเวอร์จริง**
    (บนเครื่อง dev จะสร้างรูปได้ แต่ส่งไม่ออก — เหมือนรายงานรายวัน)
    """
    from django.conf import settings
    from dashboard.services.line_channels import token_for
    from dashboard.services.line_notify import push_line_message
    from dashboard.services.report_shot import _public_url

    if not target_id:
        return False, "ไม่ได้บอกว่าจะส่งให้ใคร"

    data = collect(day)
    if not data["counts"]["total"]:
        return False, "ยังไม่มีพนักงานในทะเบียน (ต้องมีคนที่ติ๊ก 'เช็คชื่อ' ไว้)"

    path = render_png(data)
    url = _public_url(path)
    if not url.lower().startswith("https://"):
        return False, ("รูปสร้างแล้วที่ %s แต่ LINE ต้องการ URL https สาธารณะ "
                       "(SITE_URL=%s) → ต้องรันบนเซิร์ฟเวอร์จริง"
                       % (path, getattr(settings, "SITE_URL", "")))

    token = token_for(target_id)
    if not token:
        return False, "ยังไม่ได้ตั้ง LINE token"
    # แชทส่วนตัว (U…) แท็กไม่ได้ → ส่งเป็นรายชื่อแทน (ดู build_messages)
    msgs = build_messages(data, url, _channel_of_token(token), tag,
                          mention=not target_id.startswith("U"))
    sc, resp = push_line_message(target_id, msgs, token, what="ตารางเช็คชื่อเข้างาน")
    return (sc == 200), (url if sc == 200 else "LINE %s: %s" % (sc, (resp or "")[:250]))


# ═══════════ รอบสาย: ตามคนที่ยังไม่เช็คชื่อ + แท็กผู้บริหาร ═══════════
#  คัดลอกการทำงานจาก workflow "Schedule Trigger 10:00" ของ n8n มาทั้งชุด
#  ต่างกันตรง **ไม่ฝัง userId ของผู้บริหารไว้ในโค้ด** — ติ๊กเลือกคนได้ในหน้า "พนักงาน"
#  (`Employee.notify_missing`) เพราะของเดิมเปลี่ยนคนทีต้องไปแก้โค้ด และไอดีที่ฝังไว้
#  เป็นของบอทตัวเก่า (คนละ provider กับบอทที่ส่งอยู่ตอนนี้ = แท็กไม่ติด)

def managers(channel="") -> list:
    """คนที่ต้องถูกแท็กเวลามีคนไม่เช็คชื่อ — `[{name, userId}]` (เฉพาะไอดีฝั่งบัญชีที่ส่ง)"""
    from .models import Employee, LineProfile

    out = []
    for e in Employee.objects.filter(notify_missing=True).order_by("nickname"):
        uid = ""
        for p in LineProfile.objects.filter(employee_id=e.id):
            if channel and p.channel and p.channel != channel:
                continue
            uid = p.user_id
            break
        out.append({"name": e.nickname, "userId": uid})
    return out


def escalation_messages(data: dict, channel="", mention=True, round_name="10:00 น.") -> list:
    """ข้อความรอบสาย — ไม่มีใครขาด = คืนลิสต์ว่าง (ไม่ต้องส่งอะไรเลย ตามของเดิม)"""
    miss = data["missing"]
    if not miss:
        return []

    ids = _mention_ids(miss, channel) if mention else {}
    text = "⚠️ แจ้งเตือนรอบ %s\nพนักงาน %d คน ยังไม่เช็คชื่อ:\n\n" % (round_name, len(miss))
    sub = {}
    for i, m in enumerate(miss):
        uid = ids.get(m["id"])
        pos = " (%s)" % m["position"] if m["position"] else ""
        if uid:
            k = "emp%d" % (i + 1)
            sub[k] = {"type": "mention", "mentionee": {"type": "user", "userId": uid}}
            text += "%d. {%s}%s\n" % (i + 1, k, pos)
        else:
            text += "%d. %s%s\n" % (i + 1, m["name"], pos)

    mgrs = managers(channel) if mention else []
    tag_m = [g for g in mgrs if g["userId"]]
    if tag_m:
        text += "\nยังไม่เช็คครับ\n"
        for i, g in enumerate(tag_m):
            k = "mgr%d" % (i + 1)
            sub[k] = {"type": "mention", "mentionee": {"type": "user", "userId": g["userId"]}}
            text += "{%s}%s" % (k, " " if i < len(tag_m) - 1 else "")
    elif mgrs:
        # ติ๊กไว้แต่แท็กไม่ได้ (ไม่มีไอดีฝั่งบัญชีนี้) — บอกชื่อไปแทน ดีกว่าเงียบ
        text += "\nยังไม่เช็คครับ " + " ".join(g["name"] for g in mgrs)

    return [{"type": "textV2", "text": text, "substitution": sub} if sub
            else {"type": "text", "text": text}]


def send_escalation(target_id: str, day=None, round_name="10:00 น.") -> tuple:
    """ส่งข้อความรอบสายเข้าปลายทาง · คืน `(ok, ข้อความสถานะ)`"""
    from dashboard.services.line_channels import token_for
    from dashboard.services.line_notify import push_line_message

    if not target_id:
        return False, "ไม่ได้บอกว่าจะส่งให้ใคร"
    data = collect(day)
    msgs = escalation_messages(data, _channel_of_token(token_for(target_id)),
                               mention=not target_id.startswith("U"), round_name=round_name)
    if not msgs:
        return True, "ทุกคนเช็คชื่อครบแล้ว — ไม่ต้องส่ง"
    token = token_for(target_id)
    if not token:
        return False, "ยังไม่ได้ตั้ง LINE token"
    sc, resp = push_line_message(target_id, msgs, token, what="ตามคนยังไม่เช็คชื่อ (รอบสาย)")
    return (sc == 200), ("ส่งแล้ว %d คน" % len(data["missing"]) if sc == 200
                         else "LINE %s: %s" % (sc, (resp or "")[:250]))


# ═══════════ ตั้งเวลาส่งเอง (แทน Schedule Trigger ของ n8n) ═══════════
CFG_KEY = "checkin_notify_config"
_LAST_KEY = "checkin_notify_last"
DEFAULT_CFG = {"enabled": False, "table_time": "09:30", "escalate_time": "10:00",
               "mode": "test", "group_id": "", "test_id": ""}


def config() -> dict:
    from dashboard.services import cache_store
    c = dict(DEFAULT_CFG)
    c.update(((cache_store.get_kv(CFG_KEY) or {}).get("data") or {}))
    return c


def save_config(cfg: dict) -> dict:
    from dashboard.services import cache_store
    clean = dict(DEFAULT_CFG)
    clean.update({k: cfg[k] for k in DEFAULT_CFG if k in cfg})
    clean["enabled"] = bool(clean["enabled"])
    cache_store.set_kv(CFG_KEY, clean)
    return clean


def maybe_send(now_hhmm: str, today_iso: str) -> str:
    """เรียกจาก `cron_tick` ทุกนาที — ถึงเวลาที่ตั้งไว้ค่อยส่ง · คืนสิ่งที่ทำ ('' = ไม่ได้ทำ)

    **กันส่งซ้ำด้วย KV `checkin_notify_last`** (วัน+รอบ) — cron ยิงทุกนาที ถ้าไม่กัน
    นาทีเดียวกันอาจถูกยิงซ้ำจากคนละ worker
    """
    from dashboard.services import cache_store

    cfg = config()
    if not cfg.get("enabled"):
        return ""
    target = cfg["test_id"] if cfg.get("mode") == "test" else cfg["group_id"]
    if not target:
        return ""

    which = ("table" if now_hhmm == (cfg.get("table_time") or "") else
             "escalate" if now_hhmm == (cfg.get("escalate_time") or "") else "")
    if not which:
        return ""

    last = (cache_store.get_kv(_LAST_KEY) or {}).get("data") or {}
    if last.get("date") == today_iso and last.get(which):
        return ""
    if last.get("date") != today_iso:
        last = {"date": today_iso}

    try:
        if which == "table":
            ok, msg = send(target)
        else:
            ok, msg = send_escalation(target, round_name=(cfg.get("escalate_time") or "") + " น.")
    except Exception as e:
        ok, msg = False, str(e)[:200]

    last[which] = True
    cache_store.set_kv(_LAST_KEY, last)
    return "%s: %s (%s)" % (which, "ok" if ok else "ล้มเหลว", msg)
