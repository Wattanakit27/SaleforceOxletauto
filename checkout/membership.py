"""คนเข้า/ออกกลุ่ม LINE เช็คชื่อ → เอาชื่อออก/คืนเข้าระบบเช็คชื่อเอง (7 ต.ค.69 · เจ้าของถาม
*"คนที่ออกจากกลุ่มเช็คชื่อ ลบชื่อออโต้ได้มั้ย"*)

LINE ส่ง event ให้บอทที่อยู่ในกลุ่มเอง: `memberLeft` (มีคนออก) · `memberJoined` (มีคนเข้า) พร้อม userId
ข้อมูลกลุ่มเช็คชื่อวิ่งมาถึงเซิร์ฟเวอร์ทาง n8n อยู่แล้ว → แค่อ่าน event 2 ชนิดนี้เพิ่ม

กติกา
  · **ไม่ลบตัวคนออกจากทะเบียนพนักงาน** — ประวัติเช็คชื่อ/แชทผูกกับคนนั้นอยู่ ลบ = ประวัติหายตาม
    → ปิดช่อง "เช็คชื่อ" (`track_checkin`) แทน = ไม่ขึ้นในตาราง ไม่ถูกแท็กตาม (ผลเหมือนลบชื่อออกจากเช็คชื่อ)
  · **กลับเข้ากลุ่ม = คืนให้เอง** เฉพาะคนที่ระบบเป็นคนปิดเพราะออกจากกลุ่ม (จดไว้ที่ KV `LEFT_KEY`)
    คนที่แอดมินปิดเอง (ผู้บริหาร) ระบบไม่เปิดคืนให้
  · ดูเฉพาะ **กลุ่มที่ตั้งส่งตารางเช็คชื่อ** (`checkin_notify_config.group_id`) — ออกจากกลุ่มอื่นไม่เกี่ยว
  · จดทุกครั้งลง `dash_event_log` (kind=`line_member`) + KV `line_member_last` (รู้ว่า n8n ส่ง event นี้มาจริงไหม)
  · อัปเดตแคช "อยู่ในกลุ่มไหม" ของตารางเช็คชื่อด้วย (`checkin_group_member`) ไม่ต้องรอแคชหมดอายุ
"""
import time

LEFT_KEY = "checkin_left_members"      # {employee_id: {at, nick, group}} — คนที่ระบบปิดเช็คชื่อเพราะออกจากกลุ่ม
LAST_KEY = "line_member_last"
_MEMBER_KEY = "checkin_group_member"   # แคชของ checkin_report.outsiders — {group: {uid: {in, at}}}


def _kv(key) -> dict:
    from dashboard.services import cache_store
    try:
        raw = cache_store.get_kv(key) or {}
        d = raw.get("data", raw) if isinstance(raw, dict) else {}
        return dict(d) if isinstance(d, dict) else {}
    except Exception:
        return {}


def checkin_group_ids() -> set:
    """กลุ่มที่ตั้งส่งตารางเช็คชื่อ (โหมดกลุ่ม)"""
    g = (_kv("checkin_notify_config").get("group_id") or "").strip()
    return {g} if g.startswith("C") else set()


def left_members() -> dict:
    return _kv(LEFT_KEY)


def _employee_of(uid):
    from .models import LineProfile
    p = LineProfile.objects.filter(user_id=uid).select_related("employee").first()
    return p.employee if p and p.employee_id else None


def _set_member_cache(group_id, uid, inside: bool):
    from dashboard.services import cache_store
    try:
        cache = _kv(_MEMBER_KEY)
        g = dict(cache.get(group_id) or {})
        g[uid] = {"in": bool(inside), "at": time.time()}
        cache[group_id] = g
        cache_store.set_kv(_MEMBER_KEY, cache)
    except Exception:
        pass


def handle_member_events(data) -> dict:
    """อ่าน memberLeft/memberJoined จาก body ของ LINE (หลัง `_unwrap_payload`) → สรุปว่าทำอะไรไป"""
    from django.utils import timezone

    from dashboard.services import cache_store, eventlog

    evs = [e for e in ((data or {}).get("events") or [])
           if isinstance(e, dict) and e.get("type") in ("memberLeft", "memberJoined")]
    if not evs:
        return {}
    groups = checkin_group_ids()
    left = left_members()
    done = {"left": [], "back": [], "unknown": 0, "other_group": 0}
    for ev in evs:
        gid = ((ev.get("source") or {}).get("groupId") or "").strip()
        joined = ev.get("type") == "memberJoined"
        members = ((ev.get("joined") if joined else ev.get("left")) or {}).get("members") or []
        if gid not in groups:
            done["other_group"] += len(members)
            continue
        for m in members:
            uid = (m or {}).get("userId") or ""
            if not uid:
                continue
            _set_member_cache(gid, uid, joined)
            emp = _employee_of(uid)
            if not emp:
                done["unknown"] += 1
                eventlog.log("line_member", name=("เข้า" if joined else "ออกจาก") + "กลุ่มเช็คชื่อ (ไม่อยู่ในทะเบียน)",
                             target=uid, ok=True, group=gid)
                continue
            key = str(emp.id)
            if not joined:
                if emp.track_checkin:
                    emp.track_checkin = False
                    emp.save(update_fields=["track_checkin", "updated_at"])
                    left[key] = {"at": timezone.localtime().isoformat(timespec="seconds"),
                                 "nick": emp.nickname, "group": gid}
                    done["left"].append(emp.nickname)
                    eventlog.log("line_member", name="ออกจากกลุ่มเช็คชื่อ → เอาออกจากระบบเช็คชื่อ",
                                 target=emp.nickname, ok=True, group=gid)
                else:                       # แอดมินปิดไว้อยู่แล้ว (ผู้บริหาร) — จดอย่างเดียว ไม่ต้องจำว่าระบบปิด
                    eventlog.log("line_member", name="ออกจากกลุ่มเช็คชื่อ (ปิดเช็คชื่ออยู่แล้ว)",
                                 target=emp.nickname, ok=True, group=gid)
            elif key in left:
                emp.track_checkin = True
                emp.save(update_fields=["track_checkin", "updated_at"])
                left.pop(key, None)
                done["back"].append(emp.nickname)
                eventlog.log("line_member", name="กลับเข้ากลุ่มเช็คชื่อ → คืนเข้าระบบเช็คชื่อ",
                             target=emp.nickname, ok=True, group=gid)
            else:
                eventlog.log("line_member", name="เข้ากลุ่มเช็คชื่อ", target=emp.nickname, ok=True, group=gid)
    try:
        cache_store.set_kv(LEFT_KEY, left)
        cache_store.set_kv(LAST_KEY, dict(done, at=timezone.localtime().isoformat(timespec="seconds"),
                                          events=len(evs)))
    except Exception:
        pass
    return done
