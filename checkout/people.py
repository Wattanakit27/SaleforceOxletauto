"""แปลง "LINE user id / ชื่อที่ตั้งใน LINE" → **ชื่อเล่น** (เทียบจากชีตพนักงาน)

ทำไมต้องมี (เจ้าของสั่ง ก.ย.69):
  - ในกลุ่ม LINE ระบบรู้จักคนจาก **userId** (`U` + 32 ตัวอักษร) ซึ่ง **ห้ามเอาไปโชว์บนหน้าเว็บ**
    อ่านไม่ออก + เป็นข้อมูลส่วนบุคคล (ใครถือ id ก็ทักหาพนักงานได้ตรง · PDPA)
  - ชื่อเล่นมีเทียบไว้แล้วในชีตพนักงาน (`EMPLOYEE_COL` — userId | displayName | … | nickname)
  - **กติกา: หน้าเว็บโชว์ "ชื่อเล่น" · userId เก็บไว้ใช้ "แท็กในกลุ่ม LINE" อย่างเดียว**

อ่านชีตแล้ว cache ไว้ 10 นาที (ชีตนี้แทบไม่เปลี่ยน · ไม่คุ้มที่จะยิงทุกครั้ง)
อ่านไม่ได้ = คืนชื่อที่ส่งเข้ามาแทน (best-effort ไม่พังงานหลัก)
"""
import re
import time

_TTL = 600
_CACHE = {"at": 0.0, "by_uid": {}, "by_name": {}, "uid_of_name": {}}

# LINE user id = 'U' + hex 32 ตัว — ใช้ตรวจว่าค่าที่ได้มาเป็น id ดิบไหม (จะได้ไม่เผลอโชว์)
_UID_RE = re.compile(r"^U[0-9a-fA-F]{32}$")
# ชื่อใน LINE มักมีอิโมจิ/สัญลักษณ์ปน ("Mai🐶OxletAuto" · "🪷Jay. OxletAuto📜👑")
# → ตัดให้เหลือแต่ตัวอักษร/ตัวเลข ก่อนเทียบกับชีต
_KEEP = re.compile(r"[^0-9A-Za-z฀-๿]+")


def is_line_user_id(s) -> bool:
    return bool(_UID_RE.match((s or "").strip()))


def _norm(s) -> str:
    return _KEEP.sub("", (s or "")).lower()


def _load(force=False):
    """โหลดชีตพนักงานเข้าแคช — เงียบเสมอถ้าอ่านไม่ได้"""
    now = time.time()
    if not force and _CACHE["at"] and (now - _CACHE["at"]) < _TTL:
        return
    try:
        from dashboard.services.google_sheets import fetch_sheet, EMPLOYEE_COL as EM
        rows = fetch_sheet("employees")
    except Exception:
        _CACHE["at"] = now      # กันยิงรัวตอนชีตล่ม
        return

    def cell(r, i):
        return (str(r[i]).strip() if i < len(r) and r[i] else "")

    by_uid, by_name, uid_of = {}, {}, {}
    for r in rows:
        uid, dn = cell(r, EM.user_id), cell(r, EM.display_name)
        nick = cell(r, EM.nickname) or dn
        if not (uid or dn):
            continue
        if uid:
            by_uid[uid] = nick
        for key in (_norm(dn), _norm(nick)):
            if key:
                by_name.setdefault(key, nick)
                if uid:
                    uid_of.setdefault(key, uid)
    _CACHE.update({"at": now, "by_uid": by_uid, "by_name": by_name, "uid_of_name": uid_of})


def nickname_for(user_id="", display_name="") -> str:
    """ชื่อที่เอาไปโชว์ได้ — ชื่อเล่นจากชีตก่อน ไม่งั้นใช้ชื่อที่ตั้งใน LINE
    **ไม่คืน userId ดิบเด็ดขาด** (หาไม่เจอจริงๆ คืน "ไม่ทราบชื่อ")"""
    uid, dn = (user_id or "").strip(), (display_name or "").strip()
    _load()
    if uid and uid in _CACHE["by_uid"]:
        return _CACHE["by_uid"][uid]
    if dn:
        hit = _CACHE["by_name"].get(_norm(dn))
        if hit:
            return hit
        # ชื่อ LINE ที่ไม่มีในชีต — โชว์ได้ (คนในกลุ่มเห็นชื่อนี้อยู่แล้ว) แค่ล้างอิโมจิออก
        clean = re.sub(r"[^\w฀-๿.\-_ ]+", "", dn).strip(" .-_")
        if clean and not is_line_user_id(clean):
            return clean
    return "ไม่ทราบชื่อ"


def line_id_for(display_name="") -> str:
    """userId ของคนนั้น — **ใช้แท็กในกลุ่ม LINE เท่านั้น ห้ามส่งออกหน้าเว็บ**"""
    dn = (display_name or "").strip()
    if not dn:
        return ""
    _load()
    return _CACHE["uid_of_name"].get(_norm(dn), "")


def safe_name(name="") -> str:
    """กันพลาด: ถ้าค่าที่จะโชว์เป็น userId ดิบ (หรือ username `line_<uid>`) → แปลงเป็นชื่อเล่น"""
    n = (name or "").strip()
    if n.startswith("line_") and is_line_user_id(n[5:]):
        return nickname_for(user_id=n[5:])
    if is_line_user_id(n):
        return nickname_for(user_id=n)
    return n
