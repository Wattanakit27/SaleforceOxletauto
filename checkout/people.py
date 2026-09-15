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


# ---------------------------------------------------------------
#  ชื่อที่แสดงของคนนอกองค์กร (ลูกค้าที่ทักเข้า LINE OA)
# ---------------------------------------------------------------
_PROFILE_KEY = "line_profiles"      # KVStore: {userId: {"name":..., "at": iso}}
_PROFILE_MAX = 2000                 # กันโตไม่หยุด — เกินนี้ตัดตัวเก่าทิ้ง


def line_display_name(user_id="") -> str:
    """ชื่อที่ลูกค้าตั้งไว้ใน LINE — ใช้กับ "คนที่ไม่ใช่พนักงาน" เท่านั้น

    ทำไมต้องมี: พนักงานเทียบชื่อเล่นจากชีตได้ ([nickname_for]) แต่ **ลูกค้าไม่มีในชีต**
    → ถ้าไม่ดึงชื่อมา หน้าเว็บจะเห็นแต่ "ไม่ทราบชื่อ" ทุกแถว ใช้งานไม่ได้จริง
    ดึงจาก LINE profile API แล้ว **cache ถาวรใน KVStore** (ชื่อคนแทบไม่เปลี่ยน)
      → ยิง API ครั้งเดียวต่อคน ไม่ใช่ทุกข้อความ
    ไม่มี token / ยิงไม่ผ่าน = คืน "" (ไม่พัง · ค่อยได้ชื่อรอบหน้า)
    """
    uid = (user_id or "").strip()
    if not uid:
        return ""
    try:
        from django.conf import settings
        from dashboard.services import cache_store
    except Exception:
        return ""
    try:
        cache = (cache_store.get_kv(_PROFILE_KEY) or {}).get("data") or {}
    except Exception:
        cache = {}
    hit = cache.get(uid)
    if isinstance(hit, dict) and hit.get("name"):
        return hit["name"]

    try:
        from dashboard.services.line_channels import crm_token
        token = crm_token()      # ★ คนที่ทักเข้ามา = เพื่อนของบัญชี "ตัวรับ"
    except Exception:
        token = ""
    if not token:
        return ""
    try:
        import requests
        r = requests.get("https://api.line.me/v2/bot/profile/%s" % uid,
                         headers={"Authorization": "Bearer %s" % token}, timeout=8)
        name = r.json().get("displayName", "") if r.status_code == 200 else ""
    except Exception:
        name = ""
    if not name:
        return ""
    try:
        cache[uid] = {"name": name, "at": time.strftime("%Y-%m-%d")}
        if len(cache) > _PROFILE_MAX:               # ตัดตัวเก่าสุดทิ้ง
            for k in list(cache)[: len(cache) - _PROFILE_MAX]:
                cache.pop(k, None)
        cache_store.set_kv(_PROFILE_KEY, cache)
    except Exception:
        pass
    return name


def display_name_for(user_id="") -> str:
    """ชื่อที่เอาไปโชว์ได้ — พนักงานใช้ชื่อเล่นจากชีตก่อน · ไม่ใช่พนักงานค่อยดึงชื่อ LINE
    **ไม่คืน userId ดิบเด็ดขาด**"""
    n = nickname_for(user_id=user_id)
    if n and n != "ไม่ทราบชื่อ":
        return n
    return line_display_name(user_id) or ""


# ---------------------------------------------------------------
#  โปรไฟล์เต็ม → เก็บลงตาราง `LineProfile` (★ ก.ย.69 เจ้าของสั่ง)
# ---------------------------------------------------------------
def fetch_profile(user_id="", group_id="", room_id="", channel="") -> dict:
    """ดึงโปรไฟล์จาก LINE — คืน {} ถ้าดึงไม่ได้ (ไม่โยน exception)

    ⚠️ **ต้องเลือก endpoint ให้ถูกตามที่มา** ไม่งั้นได้ 404 ทั้งที่ข้อมูลมีอยู่:
      - `/v2/bot/profile/<uid>` ใช้ได้เฉพาะคนที่ **เพิ่มบอทเป็นเพื่อนแล้ว** (ลูกค้าที่ทักเข้า OA)
      - คนในกลุ่มที่ไม่ได้เพิ่มเพื่อน ต้องใช้ **group member API** แทน
        (ได้แค่ชื่อ · ไม่มี statusMessage/language)
    """
    uid = (user_id or "").strip()
    if not uid:
        return {}
    try:
        import requests
        from dashboard.services.line_channels import crm_token, group_tokens
    except Exception:
        return {}

    # ★ ก.ย.69 — 2 บัญชี: **โปรไฟล์ผูกกับบัญชีที่เขามีความสัมพันธ์ด้วย**
    #   1:1  → บัญชี "ตัวรับ" ก่อน (คนที่ทักเข้ามาเพิ่มตัวนั้นเป็นเพื่อน) แล้วค่อยลองตัวส่ง
    #   กลุ่ม → ลองทุกบัญชี เพราะบอทคนละตัวอยู่คนละกลุ่มได้
    # token ของบัญชีที่ได้ยินข้อความนี้ → ลองก่อนเสมอ (ถ้ารู้)
    first = []
    if channel:
        try:
            from dashboard.services.line_channels import token_of
            first = [t for t in [token_of(channel)] if t]
        except Exception:
            first = []
    grp = first + [t for t in group_tokens() if t not in first]
    one_to_one = [t for t in (first + [crm_token()] + grp) if t]
    # ⚠️ ห้ามเขียนแบบ `seen, x = set(), [... seen ...]` — ฝั่งขวาถูกประเมินก่อน `seen` มีค่า
    #   → UnboundLocalError ทุกครั้ง (บั๊กจริง 12-16 ก.ย.69: โปรไฟล์ลูกค้าใหม่ไม่ถูกบันทึกเลย 3 วัน
    #   เพราะทุกเทสต์ปลอม fetch_profile ทั้งฟังก์ชัน เลยไม่มีเทสต์ไหนรันบรรทัดนี้จริง)
    one_to_one = list(dict.fromkeys(one_to_one))   # ตัดตัวซ้ำ คงลำดับเดิม
    if not one_to_one:
        return {}

    tries = []
    if group_id:
        tries += [("https://api.line.me/v2/bot/group/%s/member/%s" % (group_id, uid), t) for t in grp]
    if room_id:
        tries += [("https://api.line.me/v2/bot/room/%s/member/%s" % (room_id, uid), t) for t in grp]
    # เผื่อเขาเพิ่มบอทเป็นเพื่อนไว้ — ทางนี้ได้ข้อมูลครบกว่า (statusMessage/language)
    tries += [("https://api.line.me/v2/bot/profile/%s" % uid, t) for t in one_to_one]

    best = {}
    for u, token in tries:
        try:
            r = requests.get(u, headers={"Authorization": "Bearer %s" % token}, timeout=8)
            if r.status_code != 200:
                continue
            data = r.json() or {}
        except Exception:
            continue
        if not isinstance(data, dict) or not data.get("displayName"):
            continue
        # ตัวที่มี statusMessage = มาจาก /profile (ข้อมูลครบกว่า) → เอาตัวนั้น
        if data.get("statusMessage") or data.get("language") or not best:
            best = data
        if best.get("statusMessage"):
            break
    return best


def touch_profile(user_id="", group_id="", room_id="", chat_type="user", channel="") -> dict:
    """บันทึก/อัปเดตโปรไฟล์คนนี้ แล้วคืน `{"name": ชื่อที่โชว์ได้, "is_employee": bool}`

    รวมงาน 3 อย่างไว้ที่เดียว (เดิมกระจายอยู่หลายที่แล้วยิง LINE API ซ้ำ):
      1. เทียบชีตพนักงาน → ได้ชื่อเล่น (คนใน)
      2. ไม่ใช่พนักงาน → ดึงโปรไฟล์จาก LINE (ลูกค้า)
      3. upsert ลง `LineProfile` + นับจำนวนข้อความ + ปั๊มเวลาล่าสุด

    **ดึงโปรไฟล์ซ้ำเฉพาะตอนของเก่าเกิน `PROFILE_REFRESH_DAYS`** — ไม่ใช่ทุกข้อความ
    best-effort ทั้งหมด: ตารางยังไม่ migrate / LINE ล่ม = คืนชื่อเท่าที่รู้ ไม่ทำให้การเก็บแชทพัง
    """
    uid = (user_id or "").strip()
    if not uid:
        return {"name": "", "is_employee": False}

    nick = ""
    try:
        n = nickname_for(user_id=uid)
        nick = "" if n == "ไม่ทราบชื่อ" else n
    except Exception:
        nick = ""

    try:
        from django.utils import timezone as tz
        from datetime import timedelta
        from . import constants as C
        from .models import LineProfile
    except Exception:
        return {"name": nick, "is_employee": bool(nick)}

    now = tz.now()
    try:
        row = LineProfile.objects.filter(user_id=uid).first()
    except Exception:
        return {"name": nick, "is_employee": bool(nick)}

    stale = (not row or not row.fetched_at
             or (now - row.fetched_at) > timedelta(days=C.PROFILE_REFRESH_DAYS))
    prof = {}
    # พนักงานมีชื่อเล่นในชีตอยู่แล้ว ไม่ต้องไปถาม LINE ว่าเขาชื่ออะไร
    if stale and not nick:
        # ★ ถามด้วย token ของ "บัญชีที่ได้ยินข้อความนี้" ก่อน — userId ผูกกับ provider
        #   ใช้ token ของอีกบัญชีถามอาจได้ 404 ทั้งที่คนนั้นมีตัวตนจริง
        # ★ ห่อไว้ — ดึงโปรไฟล์พลาดต้อง "ไม่มีชื่อ" ไม่ใช่ "ไม่มีแถว"
        #   เดิมไม่ได้ห่อ: exception ทะลุออกไปให้ store_chat กลืน → ข้อความเก็บได้ แต่ข้ามการสร้าง
        #   LineProfile ทั้งแถว (ลูกค้า 79 คนหายจากตารางโปรไฟล์โดยไม่มี error ให้เห็นที่ไหนเลย)
        try:
            prof = fetch_profile(uid, group_id=group_id, room_id=room_id, channel=channel)
        except Exception as e:
            prof = {}
            try:
                from dashboard.services import cache_store
                cache_store.set_kv("profile_fetch_last", {
                    "at": now.isoformat(), "error": ("%s: %s" % (type(e).__name__, e))[:200]})
            except Exception:
                pass

    fields = {
        "nickname": nick,
        "is_employee": bool(nick),
        "last_seen": now,
    }
    if channel:          # จดว่าเคยเห็นคนนี้จากบัญชีไหนบ้าง (กันนับลูกค้าซ้ำตอนทำ CRM)
        seen = list(getattr(row, "channels", None) or []) if row else []
        if channel not in seen:
            seen.append(channel)
        fields["channels"] = seen
    if prof:
        fields.update({
            "display_name": (prof.get("displayName") or "")[:120],
            "status_message": prof.get("statusMessage") or "",
            "language": (prof.get("language") or "")[:16],
            "fetched_at": now,
            # เก็บคำตอบดิบไว้เผื่อตรวจ แต่ **ตัด pictureUrl ทิ้ง** (เจ้าของสั่งไม่เก็บรูป)
            "raw": {k: v for k, v in prof.items() if k != "pictureUrl"},
        })
    try:
        if row:
            for k, v in fields.items():
                setattr(row, k, v)
            row.msg_count = (row.msg_count or 0) + 1
            row.save(update_fields=list(fields.keys()) + ["msg_count"])
        else:
            row = LineProfile.objects.create(
                user_id=uid, msg_count=1, first_seen=now, channel=channel or "",
                source=chat_type if chat_type in ("user", "group", "room") else "user",
                group_id=group_id or "", **fields)
    except Exception:
        return {"name": nick or (prof.get("displayName") or ""), "is_employee": bool(nick)}

    return {"name": row.show_name if row.show_name != "ไม่ทราบชื่อ" else "",
            "is_employee": bool(nick)}
