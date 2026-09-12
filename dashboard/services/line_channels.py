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
    """token สำหรับส่งหา **"คน" (แชท 1:1)** — ค่าเริ่มต้น = บัญชีตัวรับ (บัญชีเดิม)

    ★ ทำไมไม่ใช้ตัวส่งเหมือน push เข้ากลุ่ม: LINE ส่งเข้าแชทส่วนตัวได้
    **เฉพาะคนที่เพิ่มบัญชีนั้นเป็นเพื่อนแล้ว** — พนักงานเพิ่มบัญชีเดิมไว้ ไม่ได้เพิ่มบัญชีใหม่
    → ถ้าย้ายทันที ข้อความ "ตามด่วน" จะหายเงียบทั้งทีม (ระบบยังไม่ได้ log ขาส่ง)

    ย้ายเมื่อไหร่: ให้ทุกคนเพิ่มบัญชีใหม่เป็นเพื่อนก่อน แล้วตั้ง `LINE_DM_CHANNEL=push` ใน .env
    """
    if _st("LINE_DM_CHANNEL").lower() == PUSH:
        return push_token()
    return crm_token() or push_token()


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
    for t in (push_token(), crm_token()):
        if t and t not in out:
            out.append(t)
    return out


def secrets() -> list:
    """[(role, secret)] ของทุก channel ที่ตั้งไว้ — ใช้ตรวจลายเซ็น webhook ให้ครบทั้ง 2 บัญชี"""
    out = []
    for role, key in ((CRM, "LINE_CHANNEL_SECRET"), (PUSH, "LINE_PUSH_CHANNEL_SECRET")):
        s = _st(key)
        if s:
            out.append((role, s))
    return out


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


def describe(live: bool = True) -> list:
    """สรุปบัญชีที่ตั้งไว้ทั้งหมด (ไว้โชว์ในหน้าตรวจ/คำสั่ง `line_accounts`)

    `live=False` = ไม่ยิง LINE (ใช้ตอนแค่อยากรู้ว่าตั้ง env ครบไหม)
    """
    rows = []
    ct, pt = crm_token(), push_token()
    dm = _st("LINE_DM_CHANNEL").lower() or CRM
    shared = bool(ct) and ct == pt
    for role, token, secret_key in (
            (CRM, ct, "LINE_CHANNEL_SECRET"),
            (PUSH, pt, "LINE_PUSH_CHANNEL_SECRET")):
        row = {
            "role": role,
            "roleName": ROLE_NAME[role],
            "configured": bool(token),
            # ★ ตัวส่งยังไม่แยก = ใช้บัญชีเดียวกับตัวรับอยู่ (ยังไม่ได้เอาบัญชีใหม่มาลง)
            "shared": shared and role == PUSH,
            "hasSecret": bool(_st(secret_key)),
            "secretEnv": secret_key,
            "tokenTail": ("…" + token[-6:]) if token else "",
        }
        if live and token:
            row.update({k: v for k, v in bot_info(token).items()
                        if k in ("displayName", "basicId", "userId", "chatMode", "error")})
        if role == PUSH:
            row["dmFrom"] = PUSH if dm == PUSH else CRM   # แชท 1:1 ออกจากบัญชีไหน
        rows.append(row)
    return rows
