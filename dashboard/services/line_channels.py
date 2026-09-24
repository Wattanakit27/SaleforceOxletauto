"""ศูนย์รวม "งานนี้ใช้บัญชี LINE ตัวไหน" — ★ ก.ย.69 (เจ้าของสั่งแยกบอทเป็น 2 ตัว)

เดิมทั้งระบบใช้ **Messaging API channel เดียว** (`LINE_CHANNEL_ACCESS_TOKEN`) ทำทุกอย่าง:
รับ webhook · เก็บแชท · ดึงโปรไฟล์ · push เข้ากลุ่ม · ดึงชื่อกลุ่ม

ตั้งแต่ ก.ย.69 แยกเป็น 2 บทบาท (เจ้าของจะเอาบัญชีใหม่มาลง):

    CRM  = ตัวรับ   — บัญชีที่ลูกค้าทักเข้ามา · เก็บแชท/โปรไฟล์ทำ CRM
                     env: LINE_CHANNEL_ACCESS_TOKEN (+ LINE_CHANNEL_SECRET)
    PUSH = ตัวส่ง   — บอทที่โพสต์เข้ากลุ่มงาน (รายงานรายวัน · ตามด่วน · สรุปเบิก-คืน)
                     env: LINE_PUSH_CHANNEL_ACCESS_TOKEN (+ LINE_PUSH_CHANNEL_SECRET)

**ยังไม่ตั้งตัว PUSH = ใช้ token เดิมไปก่อนทุกอย่าง** → วางโค้ดนี้ลงไปแล้วระบบทำงาน
เหมือนเดิมเป๊ะ ค่อยเอาบัญชีใหม่มาใส่ทีหลังได้โดยไม่ต้องแก้โค้ดอีก

─────────────────────────────────────────────────────────────────
⚠️ กฎที่ต้องรู้ก่อนแก้ (ไม่รู้แล้วจะเจอ 403/404 แบบงงๆ)

1. **token ผูกกับ "ความสัมพันธ์" ไม่ใช่แค่สิทธิ์** — ดึงโปรไฟล์คนได้เฉพาะคนที่
   **เพิ่มบัญชีนั้นเป็นเพื่อน** · ดึงชื่อกลุ่ม/push เข้ากลุ่มได้เฉพาะกลุ่มที่
   **บัญชีนั้นเป็นสมาชิก** → เอา token ของ CRM ไป push เข้ากลุ่มที่มีแต่บอท PUSH = ล้มเหลว
   เพราะงั้นงานระดับ "กลุ่ม" จึง **ลองทีละ token** (`group_tokens()`) ไม่เดาเอา

2. **webhook ต้องรับได้ทั้ง 2 บัญชี** — แต่ละ channel มีลายเซ็นของตัวเอง
   `secrets()` คืนทุกตัวที่ตั้งไว้ให้ผู้เรียกลองครบ ไม่งั้นพอบัญชีใหม่ยิงมาจะโดน 403

3. **ห้ามใช้ `settings.LINE_CHANNEL_ACCESS_TOKEN` ตรงๆ ในโค้ดใหม่** — เรียกผ่านที่นี่
   ไม่งั้นพอสลับบัญชีจะมีจุดที่ตกค้างแล้วหาไม่เจอ
"""
import time

CRM, PUSH = "crm", "push"
ROLE_NAME = {CRM: "ตัวรับ/CRM (ลูกค้าทักเข้ามา)", PUSH: "ตัวส่ง (โพสต์เข้ากลุ่มงาน)"}

# ★ ก.ย.69 — เจ้าของแจ้งว่า "ต่อไปจะมี LINE OA หลายตัว" → เลิกผูกกับ 2 บัญชีตายตัว
#   บัญชีที่ 3 เป็นต้นไปเพิ่มใน .env ได้เลย ไม่ต้องแก้โค้ด/deploy (แค่ restart):
#       LINE_OA_SHOP2_TOKEN=...      → คีย์บัญชี = "shop2"
#       LINE_OA_SHOP2_SECRET=...     (ไว้ตรวจลายเซ็น webhook ของบัญชีนั้น)
#       LINE_OA_SHOP2_NAME=สาขา 2    (ชื่อที่คนอ่านออก · ไม่ใส่ก็ดึงจาก LINE เอง)
#
#   ⚠️ **เก็บ token ไว้ใน env ไม่เก็บลงฐานข้อมูล** — ถึงจะเพิ่มบัญชีผ่านหน้าเว็บได้สะดวกกว่า
#      แต่ token = สิทธิ์ส่งข้อความในนามบริษัท ถ้าหลุดจาก DB/ไฟล์ export = ใครก็ปลอมเป็นเราได้
#      (ไฟล์ export ของเราตัด token ออกอยู่แล้ว แต่ไม่เอาความเสี่ยงนี้มาแลกความสะดวก)
_OA_PREFIX, _OA_SUFFIX = "LINE_OA_", "_TOKEN"


def accounts() -> list:
    """ทุกบัญชี LINE OA ที่ตั้งไว้ — `[{key, name, token, secret, secretEnv, legacy}]`

    เรียง **ตัวรับ → ตัวส่ง → ที่เพิ่มมาทีหลัง** (ตัวรับเป็นบัญชีหลักของงาน CRM)
    บัญชีที่ token ซ้ำกับตัวก่อนหน้า = ตัวเดียวกัน ตัดทิ้ง (เช่นยังไม่ได้แยกตัวส่ง)
    """
    import os
    out, seen = [], set()

    def add(key, name, token, secret, secret_env, legacy=False):
        token = (token or "").strip()
        if not token or token in seen:
            return
        seen.add(token)
        out.append({"key": key, "name": name, "token": token,
                    "secret": (secret or "").strip(), "secretEnv": secret_env, "legacy": legacy})

    add(CRM, ROLE_NAME[CRM], _st("LINE_CHANNEL_ACCESS_TOKEN"),
        _st("LINE_CHANNEL_SECRET"), "LINE_CHANNEL_SECRET", True)
    add(PUSH, ROLE_NAME[PUSH], _st("LINE_PUSH_CHANNEL_ACCESS_TOKEN"),
        _st("LINE_PUSH_CHANNEL_SECRET"), "LINE_PUSH_CHANNEL_SECRET", True)

    # บัญชีที่เพิ่มทีหลัง — อ่านจาก os.environ ตรงๆ เพราะชื่อตัวแปรไม่ได้ประกาศไว้ใน settings.py
    for env_name in sorted(os.environ):
        if not (env_name.startswith(_OA_PREFIX) and env_name.endswith(_OA_SUFFIX)):
            continue
        raw = env_name[len(_OA_PREFIX):-len(_OA_SUFFIX)]
        if not raw:
            continue
        key = raw.lower()
        add(key, (os.environ.get("%s%s_NAME" % (_OA_PREFIX, raw), "") or "").strip() or ("OA " + key),
            os.environ.get(env_name, ""), os.environ.get("%s%s_SECRET" % (_OA_PREFIX, raw), ""),
            "%s%s_SECRET" % (_OA_PREFIX, raw))
    return out


def account_of(key: str) -> dict:
    key = (key or "").strip().lower()
    for a in accounts():
        if a["key"] == key:
            return a
    return {}


def _st(name, default=""):
    try:
        from django.conf import settings
        return (getattr(settings, name, default) or default or "").strip()
    except Exception:
        return ""


# ───────────────────────── token ─────────────────────────
def crm_token() -> str:
    """บัญชีตัวรับ — ใช้กับ: อ่าน webhook · เก็บแชท · ดึงโปรไฟล์ลูกค้าที่ทักเข้า OA"""
    return _st("LINE_CHANNEL_ACCESS_TOKEN")


def push_token() -> str:
    """บัญชีตัวส่ง — ใช้กับ **ทุกการ push** · ยังไม่ตั้ง = ตกไปใช้ตัวรับ (พฤติกรรมเดิม)"""
    return _st("LINE_PUSH_CHANNEL_ACCESS_TOKEN") or crm_token()


def has_push_channel() -> bool:
    """ตั้งบัญชีตัวส่งแยกจริงแล้วหรือยัง (ไม่ใช่แค่ fallback ไปตัวเดิม)"""
    t = _st("LINE_PUSH_CHANNEL_ACCESS_TOKEN")
    return bool(t) and t != crm_token()


def dm_token() -> str:
    """token สำหรับส่งหา **"คน" (แชท 1:1)** — ★ 20 ก.ย.69 ค่าเริ่มต้น = **บัญชีตัวส่ง (GiveLead)**

    เจ้าของกำหนดนโยบายไว้ชัด: *"ตัว OxletAuto ใช้แค่เก็บข้อมูลลูกค้า · บอทจริงๆ ที่ใช้ส่ง
    คือ OxletautoGiveLead"* → **ขาส่งทั้งหมด (กลุ่ม + แชท 1:1) ออกจากบัญชีตัวส่งบัญชีเดียว**
    ส่วนบัญชีตัวรับเหลือหน้าที่ "รับ/เก็บแชทลูกค้า" อย่างเดียว

    ⚠️ ข้อจำกัดของ LINE ที่ยังอยู่: ส่งเข้าแชท 1:1 ได้ **เฉพาะคนที่เพิ่มบัญชีนั้นเป็นเพื่อนแล้ว**
    ★ 24 ก.ย.69 **ถอดตัวสำรอง (ส่งซ้ำด้วยบัญชีตัวรับ) ออกแล้ว** ตามที่เจ้าของสั่งเลิกใช้บัญชีเก่า
    → ส่งไม่ถึง = ไม่ถึงจริงๆ แล้วจดไว้ใน `dash_event_log` · แก้ด้วยการให้คนนั้นแอดบอทตัวส่ง

    กลับไปใช้บัญชีเดิมชั่วคราว: ตั้ง `LINE_DM_CHANNEL=crm` ใน .env
    """
    if _st("LINE_DM_CHANNEL").lower() == CRM:
        return crm_token() or push_token()
    return push_token() or crm_token()


def followup_token() -> str:
    """★★ 24 ก.ย.69 — **"ตามด่วน" ย้ายมาบอทตัวส่งแล้ว** (เจ้าของสั่ง *"การแจ้งเตือน
    จะยกเลิกการใช้ [บัญชีเก่า] ไปเลย จะใช้เป็นบัญชี OxletautoGiveLead"*)

    _(เดิม 20 ก.ย.69 เป็นข้อยกเว้น: ตามด่วน 2 ตัวยังใช้บัญชีตัวรับ เพราะทีมเพิ่มบัญชีเดิม
    ไว้แล้วและส่งได้ดีทุกวัน — ยกเลิกข้อยกเว้นนี้ตามที่เจ้าของสั่ง)_

    ⚠️ **ผลที่ต้องรู้**: LINE ส่งเข้าแชท 1:1 ได้เฉพาะคนที่ **เพิ่มบัญชีนั้นเป็นเพื่อนแล้ว**
    วัดจริง 24/09: คนที่ได้ตามด่วน 18 คน — มีไอดีฝั่งบอทใหม่แล้ว 16 คน · **ยังไม่มี 2 คน**
    → 2 คนนั้นจะไม่ได้รับจนกว่าจะแอดบอทตัวส่งเป็นเพื่อน (ดูใครได้จาก `dash_event_log`
    แถวที่ `kind='line_send' AND NOT ok`) — **ไม่มีตัวสำรองส่งด้วยบัญชีเก่าอีกแล้ว**

    จะย้อนกลับชั่วคราวทั้งระบบ: ตั้ง `LINE_DM_CHANNEL=crm` ใน .env
    """
    return dm_token()


def token_for(target_id: str) -> str:
    """เลือก token จาก **ปลายทาง** — id ของ LINE บอกชนิดอยู่แล้วที่ตัวอักษรแรก

        C… = กลุ่ม · R… = ห้องคุย  → บัญชี "ตัวส่ง"
        U… = คน (แชท 1:1)          → `dm_token()`

    ใช้ตัวนี้แทนการเลือก token ไว้ล่วงหน้า เพราะรอบส่งเดียวกันมีทั้งกลุ่มและคนปนกันได้
    """
    t = (target_id or "").strip()
    return push_token() if t[:1].upper() in ("C", "R") else dm_token()


def group_tokens() -> list:
    """token ที่ควรลองสำหรับงานระดับ "กลุ่ม" (ดึงชื่อกลุ่ม · โปรไฟล์คนในกลุ่ม)

    เรียง **ตัวส่งก่อน** เพราะบอทที่อยู่ในกลุ่มงานคือตัวส่ง · ตัดตัวซ้ำ/ว่างออก
    ผู้เรียกต้องวนลองจนกว่าจะสำเร็จ — บัญชีที่ไม่ได้อยู่ในกลุ่มนั้นจะได้ 403/404
    """
    out = []
    for t in [push_token(), crm_token()] + [a["token"] for a in accounts()]:
        if t and t not in out:
            out.append(t)
    return out


def secrets() -> list:
    """[(key, secret)] ของ **ทุกบัญชี** ที่ตั้ง secret ไว้ — ผู้เรียกต้องลองให้ครบ

    ⚠️ ตั้ง secret ไว้ "บางบัญชี" อันตรายกว่าไม่ตั้งเลย: `line_webhook` จะเริ่มตรวจลายเซ็น
    ทันทีที่มี secret สักตัว → event ของบัญชีที่ยังไม่ได้ตั้งจะโดนปฏิเสธ 403 ทั้งหมด
    (`line_accounts` เตือนให้แล้วถ้าตั้งไม่ครบ)
    """
    return [(a["key"], a["secret"]) for a in accounts() if a["secret"]]


# ───────────────────── ตรวจว่า token เป็นของบัญชีไหน ─────────────────────
_INFO_TTL = 600
_info_cache = {}        # token -> (เวลา, dict)


def bot_info(token: str, timeout: int = 8) -> dict:
    """ถาม LINE ว่า token นี้เป็นของบัญชีไหน → `{displayName, basicId, userId, chatMode}`

    เป็นวิธีเดียวที่ยืนยันได้ว่า "วางคีย์ถูกช่องไหม" โดยไม่ต้องส่งข้อความจริง
    · cache 10 นาที (ค่าพวกนี้แทบไม่เปลี่ยน) · ดึงไม่ได้คืน `{"error": ...}` ไม่โยน exception
    """
    token = (token or "").strip()
    if not token:
        return {"error": "ยังไม่ได้ตั้ง token"}
    hit = _info_cache.get(token)
    if hit and (time.time() - hit[0]) < _INFO_TTL:
        return hit[1]
    try:
        import requests
        r = requests.get("https://api.line.me/v2/bot/info",
                         headers={"Authorization": "Bearer %s" % token}, timeout=timeout)
        if r.status_code == 200:
            info = r.json() or {}
        elif r.status_code == 401:
            info = {"error": "token ไม่ถูกต้อง/หมดอายุ (401)"}
        else:
            info = {"error": "LINE ตอบ %s" % r.status_code}
    except Exception as e:
        info = {"error": str(e)[:120]}
    _info_cache[token] = (time.time(), info)
    return info


def bot_user_id(token: str) -> str:
    """userId ของ "ตัวบอท" เอง — ค่าเดียวกับฟิลด์ `destination` ใน webhook body"""
    return (bot_info(token) or {}).get("userId", "") or ""


def token_of(key: str) -> str:
    """token ของบัญชีตามคีย์ — `"crm"`/`"push"` หรือคีย์ของบัญชีที่เพิ่มเองใน .env

    คีย์ที่ไม่รู้จัก/ว่าง → คืนบัญชีตัวรับ (พฤติกรรมเดิม ไม่ทำให้งานเก่าพัง)
    """
    k = (key or "").strip().lower()
    if k == PUSH:
        return push_token()
    if k and k != CRM:
        a = account_of(k)
        if a:
            return a["token"]
    return crm_token()


def channel_of(destination: str) -> str:
    """event นี้มาจากบัญชีไหน → `"crm"` / `"push"` / `""` (ไม่ทราบ)

    ★ ก.ย.69 — จำเป็นตอนมี 2 บัญชีแล้ว n8n forward มาที่ endpoint เดียวกัน:
    ถ้าไม่รู้ว่าข้อความมาจากบัญชีไหน จะ **ดึงโปรไฟล์ด้วย token ผิดตัว** (ได้ 404)
    และแยกไม่ออกว่าคนคนนี้คุยกับบอทตัวไหน

    LINE ใส่ `destination` = **userId ของบอทที่เป็นเจ้าของ event** มาให้ใน body อยู่แล้ว
    → เทียบกับ userId ของแต่ละ token ก็รู้ทันที (ค่าพวกนี้ cache ไว้ 10 นาที)

    ⚠️ `_unwrap_payload` ที่แกะ "event เดี่ยว" จะไม่มี `destination` ติดมา → คืน `""`
       (ไม่ใช่เดามั่ว — ผู้เรียกค่อยตัดสินใจว่าจะ fallback ยังไง)
    """
    d = (destination or "").strip()
    if not d:
        return ""
    for a in accounts():
        if bot_user_id(a["token"]) == d:
            return a["key"]
    return ""


def describe(live: bool = True) -> list:
    """สรุป **ทุกบัญชี** ที่ตั้งไว้ (ไว้โชว์ในหน้าตรวจ/คำสั่ง `line_accounts`)

    `live=False` = ไม่ยิง LINE (ใช้ตอนแค่อยากรู้ว่าตั้ง env ครบไหม)
    """
    rows = []
    ct, pt = crm_token(), push_token()
    dm = _st("LINE_DM_CHANNEL").lower() or CRM
    accs = accounts()
    # ตัวส่งยังไม่แยก = ไม่มีแถว push ในทะเบียน (token ซ้ำกับตัวรับเลยถูกตัด) → แจ้งให้รู้
    shared = bool(ct) and ct == pt and not any(a["key"] == PUSH for a in accs)
    if shared:
        accs = accs + [{"key": PUSH, "name": ROLE_NAME[PUSH], "token": pt, "secret": _st("LINE_PUSH_CHANNEL_SECRET"),
                        "secretEnv": "LINE_PUSH_CHANNEL_SECRET", "legacy": True}]
    for a in accs:
        row = {
            "role": a["key"],          # ชื่อเดิมของฟิลด์ — ผู้เรียกเก่ายังใช้ได้
            "key": a["key"],
            "roleName": a["name"],
            "configured": bool(a["token"]),
            "shared": shared and a["key"] == PUSH,
            "hasSecret": bool(a["secret"]),
            "secretEnv": a["secretEnv"],
            "legacy": a.get("legacy", False),
            "tokenTail": ("…" + a["token"][-6:]) if a["token"] else "",
        }
        if live and a["token"]:
            row.update({k: v for k, v in bot_info(a["token"]).items()
                        if k in ("displayName", "basicId", "userId", "chatMode", "error")})
        if a["key"] == PUSH:
            row["dmFrom"] = PUSH if dm == PUSH else CRM   # แชท 1:1 ออกจากบัญชีไหน
        rows.append(row)
    return rows


# ───────────────────── กลุ่มที่บอทตัวส่งเข้าถึงได้ ─────────────────────
def push_group_check(group_id: str, timeout: int = 8) -> dict:
    """ถาม LINE ว่า **บอทตัวส่งอยู่ในกลุ่มนี้ไหม** → `{ok, name, status, error}`

    ★ ก.ย.69 (ย้าย push ทั้งระบบไป OxletautoGiveLead): **group id ออกต่อ provider เหมือน user id**
      กลุ่มเดียวกันมี id คนละตัวในสายตาบอทแต่ละตัว → เอา id ที่บอทเดิมจดไว้มาให้บอทใหม่ส่ง
      = LINE ตอบ 400 "Failed to send messages" ทุกรอบ (เกิดจริงกับการ์ดตั้งเวลาทุกใบ 15/09)

    `ok` = True อยู่ในกลุ่ม · False = LINE ยืนยันว่าไม่อยู่ (403/404) · None = ถามไม่ได้ (เน็ต/ไม่มี token)
    """
    gid = (group_id or "").strip()
    token = push_token()
    if not gid or not token:
        return {"ok": None, "name": "", "status": 0, "error": "ไม่มี group id หรือ token ตัวส่ง"}
    if gid[:1].upper() not in ("C", "R"):
        return {"ok": False, "name": "", "status": 0, "error": "ไม่ใช่ group id (ต้องขึ้นต้นด้วย C)"}
    kind = "room" if gid[:1].upper() == "R" else "group"
    try:
        import requests
        url = "https://api.line.me/v2/bot/%s/%s/summary" % (kind, gid)
        if kind == "room":          # ห้องคุยไม่มี summary — ใช้จำนวนสมาชิกยืนยันแทน
            url = "https://api.line.me/v2/bot/room/%s/members/count" % gid
        r = requests.get(url, headers={"Authorization": "Bearer %s" % token}, timeout=timeout)
        if r.status_code == 200:
            return {"ok": True, "name": (r.json() or {}).get("groupName", ""), "status": 200, "error": ""}
        if r.status_code in (400, 403, 404):
            return {"ok": False, "name": "", "status": r.status_code,
                    "error": "บอทตัวส่งไม่ได้อยู่ในกลุ่มนี้ (LINE %s)" % r.status_code}
        return {"ok": None, "name": "", "status": r.status_code, "error": "LINE ตอบ %s" % r.status_code}
    except Exception as e:
        return {"ok": None, "name": "", "status": 0, "error": str(e)[:120]}


def push_group_error(group_id: str) -> str:
    """ใช้ตอน "บันทึก" ปลายทางกลุ่ม — คืนข้อความ error ถ้า **ยืนยันได้** ว่าบอทตัวส่งไม่อยู่ในกลุ่ม

    ถามไม่ได้ (เน็ตล่ม ฯลฯ) = ปล่อยผ่าน ไม่บล็อกการบันทึก · ว่าง = ปล่อยผ่าน (ปิดการส่งกลุ่ม)
    """
    gid = (group_id or "").strip()
    if not gid:
        return ""
    res = push_group_check(gid)
    if res.get("ok") is False:
        name = ""
        try:
            name = (bot_info(push_token()) or {}).get("displayName", "")
        except Exception:
            pass
        return ("บอท %s ไม่ได้อยู่ในกลุ่มนี้ — group id นี้น่าจะเป็นของบอทตัวเดิม "
                "(กลุ่มเดียวกันมี id ต่างกันในแต่ละบอท) · เชิญบอทเข้ากลุ่มแล้วเลือกกลุ่มใหม่จากรายการ"
                % (name or "ตัวส่ง"))
    return ""


def group_visible_to_push(entry: dict) -> bool:
    """แถวใน KV `line_groups` นี้ควรโชว์ใน dropdown "ส่งเข้ากลุ่ม" ไหม

    มีบันทึกว่าบัญชีไหนได้ยิน (`channels`) แต่ไม่มีตัวส่ง = id ของบอทอื่น → ซ่อน (เลือกไปก็ส่งไม่ได้)
    ไม่มีบันทึก (ข้อมูลเก่าก่อนแยกบัญชี) = ยังโชว์ ให้คนตรวจชื่อเอง · ยังไม่ได้แยกบัญชี = โชว์หมด
    """
    if not has_push_channel():
        return True
    chans = (entry or {}).get("channels") or []
    return (not chans) or (PUSH in chans)
