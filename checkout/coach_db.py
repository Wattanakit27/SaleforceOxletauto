# -*- coding: utf-8 -*-
"""บันทึกห้องโค้ชลงฐานข้อมูล — ที่รวมถาวรของเก่า+ใหม่ (30 ก.ย.69 · เจ้าของสั่ง)

เจ้าของเปิดหน้า "ฐานข้อมูล (SQL)" แล้วเห็นห้องโค้ชมีแค่ 20 ข้อความ จึงถามว่า
*"ค่าเก่าที่เคยส่งให้ไปไหน เอาไปเรียงใหม่หน่อยและเอามารวมกัน"*

**ทำไมข้อมูลเก่าไม่อยู่ใน `GroupChat`** — ตารางนั้นลบข้อมูลเกิน 90 วันอัตโนมัติ
(`CHAT_KEEP_DAYS`) · ของ เม.ย.–ก.ค.69 ถูกลบไปแล้ว · ฉบับเต็ม 1,695 แถวอยู่ในชีต
**ยัดกลับเข้า `GroupChat` ไม่ได้** เพราะรอบ cleanup ถัดไปจะลบซ้ำทันที
→ `CoachLog` เป็นตารางของตัวเอง ไม่มีวันหมดอายุ

**★ แปลงจาก `coaching._row()` ตัวเดิม ไม่เขียนตรรกะซ้ำ** — บทบาทซีเนียร์/จูเนียร์ ·
รหัสเคส · ทีม · การกันชื่อ LINE id หลุด ใช้ของ [coaching.py](coaching.py) ทั้งหมด
ถ้าแยกสูตรกัน วันหนึ่งตัวเลขใน DB กับในชีตจะไม่ตรงแล้วไม่มีใครรู้ว่าอันไหนถูก

**★ `sync_chat()` รันบน prod ได้ ไม่ติด 403** (ต่างจากการซิงก์เข้าชีต ซึ่ง service account
ของ prod ยังไม่มีสิทธิ์เขียนไฟล์โค้ช) → ข้อมูลใหม่เข้าฐานข้อมูลได้ทุกวันแน่นอน
"""
from __future__ import annotations

from . import coaching as C

# ลำดับช่องใน `coaching._row()` — ห้ามสลับ ถ้าจะเพิ่มคอลัมน์ให้ต่อท้ายทั้ง 2 ที่
COL = ("date_text", "time_text", "case_code", "who", "role", "team", "text",
       "case_status", "kind", "source", "note", "ref")


def _unesc(v) -> str:
    """ถอด `'` นำหน้าที่ `_esc()` ใส่กันชีตตีเป็นสูตร — ในฐานข้อมูลไม่ต้องมี"""
    s = str(v or "")
    return s[1:] if s[:1] == "'" and s[1:2] in ("=", "+", "-", "@") else s


def _dt(date_text: str, time_text: str):
    """`YYYY-MM-DD` + `HH:MM` → datetime โซนไทย · แปลงไม่ได้ = None (ไม่ทิ้งแถว)"""
    from django.utils import timezone

    s = "%s %s" % ((date_text or "").strip(), (time_text or "00:00").strip())
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            import datetime as _d
            naive = _d.datetime.strptime(s, fmt)
            return timezone.make_aware(naive, timezone.get_current_timezone())
        except Exception:
            continue
    return None


def _to_fields(row: list) -> dict:
    d = {k: _unesc(row[i]) if i < len(row) else "" for i, k in enumerate(COL)}
    d["sent_at"] = _dt(d["date_text"], d["time_text"])
    return d


def save_rows(rows: list) -> dict:
    """เขียนลง `CoachLog` · กันซ้ำด้วย `ref` — รันซ้ำกี่รอบก็ไม่เบิ้ล

    แถวที่ไม่มี `ref` = ข้าม (ไม่มีอะไรกันซ้ำได้ → รันซ้ำแล้วจะเบิ้ล)
    """
    from .models import CoachLog

    seen = set(CoachLog.objects.values_list("ref", flat=True))
    add, skip, dup, norefs = [], 0, 0, 0
    batch = set()
    for r in rows:
        f = _to_fields(r)
        ref = f.get("ref") or ""
        if not ref:
            norefs += 1
            continue
        if ref in seen:
            skip += 1
            continue
        if ref in batch:        # ซ้ำภายในชุดเดียวกัน (ชีตมีแถวซ้ำได้)
            dup += 1
            continue
        batch.add(ref)
        add.append(CoachLog(**f))
    if add:
        CoachLog.objects.bulk_create(add, batch_size=500)
    return {"added": len(add), "skipped": skip, "dupInBatch": dup,
            "noRef": norefs, "total": CoachLog.objects.count()}


def sync_chat(days: int = 120, group_id: str = "", seniors=None) -> dict:
    """ดึงจาก `GroupChat` ห้องโค้ช → `CoachLog` · **ไม่แตะชีต ทำงานบน prod ได้**"""
    rows, stat = C.rows_from_chat(days=days, group_id=group_id, seniors=seniors)
    out = save_rows(rows)
    out["read"] = len(rows)
    out["stat"] = stat
    return out


def import_sheet(limit_rows: int = 20000) -> dict:
    """นำเข้าแท็บ `บันทึกโค้ช` (ฉบับประมวลผลแล้ว 1,695 แถว) → `CoachLog`

    อ่าน**แท็บใหม่** ไม่ใช่ `Sheet A — Log` ดิบ — เพราะแท็บใหม่แยกบทบาท/ทีม/รหัสเคส
    ไว้แล้ว (และ `Sheet A — Log` มีคอลัมน์ `userid` ซึ่งห้ามเอาเข้าที่นี่)

    ⚠️ ต้องรันจากเครื่องที่ service account อ่านไฟล์โค้ชได้ (prod ยังเป็น 403)
    """
    rows = C._read(C.TAB, "A1:L%d" % limit_rows)
    if not rows:
        return {"added": 0, "read": 0, "error": "อ่านแท็บ '%s' ไม่ได้/ว่าง" % C.TAB}
    head, body = rows[0], rows[1:]
    if head[:3] != C.COLUMNS[:3]:
        return {"added": 0, "read": len(body),
                "error": "หัวตารางไม่ตรงกับที่คาด: %s" % " | ".join(head[:4])}
    # เติมช่องที่หายให้ครบ 12 ช่อง (ชีตตัดช่องว่างท้ายแถวออก)
    fixed = [list(r) + [""] * (len(COL) - len(r)) for r in body]
    out = save_rows(fixed)
    out["read"] = len(body)
    return out


def stats() -> dict:
    """สรุปสิ่งที่อยู่ในตาราง — ใช้ในคำสั่งและหน้าตรวจสอบ"""
    from django.db.models import Count, Max, Min

    from .models import CoachLog

    qs = CoachLog.objects.all()
    agg = qs.aggregate(n=Count("id"), first=Min("date_text"), last=Max("date_text"))
    by_role = dict(qs.values_list("role").annotate(n=Count("id")))
    by_src = dict(qs.values_list("source").annotate(n=Count("id")))
    return {"total": agg["n"], "from": agg["first"] or "", "to": agg["last"] or "",
            "byRole": by_role, "bySource": by_src}
