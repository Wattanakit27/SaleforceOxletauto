# -*- coding: utf-8 -*-
"""รายงานทีมคอนเทนต์ — โครงตามที่เจ้าของเสนอ (30 ก.ย.69)

*"คลิปลงใหม่ ผลเป็นยังไง · คลิปลงภายใน 7 วันจัดแรงค์ที่มียอดวิวเยอะ · คลิป 7 วัน+
ที่มียอดวิวน้อย · คลิป 7วัน+ ที่มียอดวิวเยอะที่สุด · และรายงานทั้ง 10 ช่อง
และยอดลีดที่ได้จากช่องทางนี้กี่คน · 7 วันมียอดวิว เม้น ไลก์ แชร์ บันทึก กี่คน"*

**★ ใช้สูตรของ [social_stats.py](social_stats.py) ทั้งหมด ไม่เขียนใหม่**
(`_daily_one` = ยอดรายวันจาก snapshot สะสม · `_range` · `_side_cfg`)
— แยกสูตรเมื่อไหร่ ตัวเลขในรายงานกับในหน้าเว็บจะไม่ตรงกันแล้วไม่มีใครรู้ว่าอันไหนถูก

**⚠️ "บันทึก" (saves) ไม่มีในรายงาน — ไม่ใช่ลืม**
TikTok Display API (`video.list`) ให้แค่ วิว/ไลก์/คอมเมนต์/แชร์ ·
YouTube `favoriteCount` เลิกใช้ตั้งแต่ปี 2015 (คืน 0 เสมอ) ·
Facebook Graph ไม่เปิดยอดบันทึกของโพสต์เพจ
→ **ไม่ใส่ช่องที่จะเป็น 0 ทุกแถว** เพราะคนอ่านจะนึกว่าไม่มีใครบันทึกเลย
ซึ่งไม่จริง · อยากได้ต้องเปิดหลังบ้านของแต่ละแพลตฟอร์มดูเอง
"""
from __future__ import annotations

from datetime import timedelta

from . import social_stats as S

#  กี่วันนับว่า "คลิปลงใหม่"
NEW_DAYS = 7
#  แสดงกี่อันดับต่อบล็อก
TOP_N = 5

#  ★ จับคู่ "ช่องในระบบ" ↔ "ชื่อช่องทางที่ทีมกรอกในชีตลีด" — เขียนมือโดยตั้งใจ
#
#  ชีตลีดเขียนชื่อช่องคนละแบบกับทะเบียนช่อง TikTok:
#    ระบบ "ช่องพี่แซน"  ↔ ชีต "Tiktok ช่องแซน"
#    ระบบ "ช่อง 888"    ↔ ชีต "TIKTOK ช่อง888" · "LIVE Tiktok / ช่อง888"
#  ★ ห้ามใช้ substring/fuzzy match — บทเรียนเดิม: `Mod🐜` ไปจับ `เอ็ม` เพราะ m เป็น substring
#    10 ช่องเขียนมือได้หมด และผิดแล้วเห็นทันที ต่างจากตัวเดาที่ผิดเงียบๆ
#  ชื่อที่ใส่ตรงนี้ = คำที่อยู่ใน "ชื่อช่องทาง" ของชีต (เทียบแบบตัดช่องว่าง/ตัวพิมพ์)
LEAD_ALIAS = {
    "ช่องพี่แซน": ["ช่องแซน"],
    "ช่องขายบอส": ["ช่องขายบอส"],
    "ช่องหลัก": ["ช่องหลัก"],
    "ช่อง 888": ["ช่อง888"],
    "Tiktok guru": ["guru"],
    "ช่องปรึกษา": ["ช่องปรึกษา"],
    "คู่หู อ๊อกเล็ต": ["คู่หู"],
    "บอสเจมส์": ["บอสเจมส์"],
    "บอสเจมส์ทะเบียนเทพ": ["ทะเบียนเทพ"],
    "บัญชีเจ้าของ": [],          # ยังไม่มีชื่อนี้ในชีตลีด
}


def _norm(s) -> str:
    """ตัดช่องว่าง/ตัวพิมพ์ เพื่อเทียบชื่อช่องทาง — **ไม่ตัดอย่างอื่น** (กันจับคู่มั่ว)"""
    return "".join(str(s or "").lower().split())


def _lead_by_channel(frm, to) -> tuple[dict, dict]:
    """ลีดที่ได้ในช่วง แยกตามชื่อช่องทางในชีต → `({ชื่อช่องทาง: จำนวน}, สรุปกลุ่ม)`

    อ่านจากผลสรุปแดชบอร์ดที่คำนวณไว้แล้ว (`leadChannelByMonth` = {เดือน:{วัน:{ช่องทาง:n}}})
    — ไม่ยิง Google Sheets เอง เพราะรายงานนี้ถูกแคปตอนไหนก็ได้ ต้องไม่ไปหน่วงชีต
    """
    try:
        from .cache_store import get_kv
        raw = (get_kv("main") or {}).get("data") or {}
        by_month = raw.get("leadChannelByMonth") or {}
    except Exception:
        return {}, {}

    out: dict = {}
    d = frm
    while d <= to:
        days = by_month.get(str(d.month)) or by_month.get(d.month) or {}
        one = days.get(str(d.day)) or days.get(d.day) or {}
        for ch, n in one.items():
            try:
                out[ch] = out.get(ch, 0) + int(n or 0)
            except Exception:
                continue
        d += timedelta(days=1)

    # สรุปเป็นกลุ่มกว้างๆ ให้คนอ่านเห็นภาพ (TikTok ทุกช่องรวมกัน · เพจทุกเพจรวมกัน)
    group = {"tiktok": 0, "page": 0, "line": 0, "other": 0}
    for ch, n in out.items():
        k = _norm(ch)
        if "tiktok" in k:
            group["tiktok"] += n
        elif "เพจ" in k or "facebook" in k:
            group["page"] += n
        elif "line" in k:
            group["line"] += n
        else:
            group["other"] += n
    return out, group


def _lead_for(name: str, lead_ch: dict) -> int:
    """ลีดของช่องนี้ = รวมทุกชื่อช่องทางในชีตที่ตรงกับ alias (ทั้ง Tiktok ปกติและ LIVE)"""
    keys = LEAD_ALIAS.get(name)
    if not keys:
        return 0
    total = 0
    for ch, n in lead_ch.items():
        k = _norm(ch)
        if any(_norm(a) in k for a in keys):
            total += n
    return total


def _rows(side: str, f, t) -> tuple[list, dict]:
    """ทุกคลิป/โพสต์ของแพลตฟอร์มนั้นในช่วง → `(rows, per_item_daily)`

    แต่ละแถว: `id · text · owner · date(วันโพสต์) · live(คิดรายวันได้ไหม) · inc(ยอดในช่วง) · ยอดสะสม`
    """
    cfg = (S._side_cfg() or {}).get(side)
    if not cfg:
        return [], {}
    M, own, pid, cols = cfg["model"], cfg["owner"], cfg["pid"], cfg["cols"]

    want = {pid, own, "snap_date", "taken_at", cfg["when"], cfg["title"]}
    want |= {c for c in cols.values() if c}
    if cfg.get("link"):
        want.add(cfg["link"])

    def num(r, m):
        col = cols.get(m)
        return int(r.get(col) or 0) if col else 0

    base = M.objects.filter(snap_date__gte=f - timedelta(days=1), snap_date__lte=t)
    daily_rows = [{"id": r[pid], "snap_date": r["snap_date"], "taken_at": r["taken_at"],
                   **{m: num(r, m) for m in S.METRICS}}
                  for r in base.filter(trigger="cron").values(*want)]
    per_item = S._daily_one(daily_rows, "id", set())
    per_item = {k: {d: v for d, v in days.items() if f.isoformat() <= d <= t.isoformat()}
                for k, days in per_item.items()}

    best: dict = {}
    for r in M.objects.filter(snap_date__gte=f, snap_date__lte=t).values(*want):
        old = best.get(r[pid])
        if not old or r["taken_at"] > old["taken_at"]:
            best[r[pid]] = r

    rows = []
    for vid, r in best.items():
        days = per_item.get(vid) or {}
        when = r.get(cfg["when"])
        rows.append({
            "id": vid, "side": side, "owner": r.get(own) or "",
            "text": (r.get(cfg["title"]) or "").strip()[:120],
            "link": (r.get(cfg["link"]) if cfg.get("link") else "") or "",
            "date": when.date().isoformat() if when else "",
            "live": bool(days),
            "inc": {m: sum(v.get(m, 0) for v in days.values()) for m in S.METRICS},
            **{m: num(r, m) for m in S.METRICS},
        })
    return rows, per_item


def _owner_names() -> dict:
    """{owner_id: ชื่อที่คนอ่านออก} — ครบทั้ง 3 แพลตฟอร์ม"""
    names: dict = {}
    try:
        from dashboard.models import TikTokAccount
        for a in TikTokAccount.objects.all():
            names[a.open_id] = (a.label or a.open_id)
    except Exception:
        pass
    try:
        names.update(S._page_names() or {})
    except Exception:
        pass
    try:
        from dashboard.models import YouTubeChannelSnapshot
        for r in (YouTubeChannelSnapshot.objects.values("channel_id", "title")
                  .order_by("channel_id").distinct()):
            if r.get("title"):
                names.setdefault(r["channel_id"], r["title"])
    except Exception:
        pass
    return names


def weekly(frm=None, to=None, new_days: int = NEW_DAYS, top: int = TOP_N) -> dict:
    """รายงานทีมคอนเทนต์ 1 ก้อน — ใช้ทั้งในหน้าเว็บและรูปที่ส่งเข้าไลน์

    บล็อกที่คืน:
      `totals`   — ยอดรวมในช่วง แยกแพลตฟอร์ม (วิว/ไลก์/คอมเมนต์/แชร์ + จำนวนชิ้นงาน)
      `newClips` — คลิปที่ **ลงใหม่ในช่วง** เรียงวิวมากสุด
      `oldTop`   — คลิปเก่า (ลงก่อนช่วงนี้) ที่ยังทำวิวได้มากสุดในช่วง
      `oldLow`   — คลิปเก่าที่วิวน้อยสุดในช่วง (**เฉพาะที่คิดยอดรายวันได้** ไม่งั้นได้กอง 0)
      `channels` — ทุกช่อง + ลีดที่ได้จากช่องนั้น
      `leads`    — ลีดรวมจากโซเชียล แยกกลุ่ม
    """
    f, t = S._range(frm, to)
    cutoff = (t - timedelta(days=max(1, new_days) - 1)).isoformat()   # ลงวันนี้ก็ถือว่าใหม่
    lead_ch, lead_group = _lead_by_channel(f, t)
    names = _owner_names()

    all_rows: list = []
    totals: dict = {}
    for side in ("tiktok", "meta", "youtube"):
        rows, _ = _rows(side, f, t)
        all_rows += rows
        live = [r for r in rows if r["live"]]
        totals[side] = {
            **{m: sum(r["inc"].get(m, 0) for r in rows) for m in S.METRICS},
            "clips": len(rows),
            "liveClips": len(live),
            "newClips": len([r for r in rows if r["date"] >= cutoff]),
        }

    def pack(r):
        return {"side": r["side"], "text": r["text"] or "(ไม่มีชื่อ)", "link": r["link"],
                "date": r["date"], "owner": names.get(r["owner"], r["owner"]),
                **{m: r["inc"].get(m, 0) for m in S.METRICS},
                "cumViews": r.get("views", 0)}

    new_rows = [r for r in all_rows if r["date"] and r["date"] >= cutoff]
    old_rows = [r for r in all_rows if r["date"] and r["date"] < cutoff]
    # ★ "วิวน้อยสุด" ต้องนับเฉพาะคลิปที่ **คิดยอดรายวันได้จริง** — คลิปที่ยังไม่มี snapshot
    #   2 คืนจะได้ 0 ทุกตัวแล้วไปกองอยู่หัวตาราง = ตอบผิดคำถาม (บทเรียนเดิมของ `_sort_rows`)
    old_live = [r for r in old_rows if r["live"]]

    new_rows.sort(key=lambda r: -r["inc"].get("views", 0))
    old_live_sorted = sorted(old_live, key=lambda r: -r["inc"].get("views", 0))

    chans: list = []
    by_owner: dict = {}
    for r in all_rows:
        o = by_owner.setdefault((r["side"], r["owner"]), {
            "side": r["side"], "id": r["owner"],
            "name": names.get(r["owner"], r["owner"] or "(ไม่ทราบชื่อ)"),
            "clips": 0, "newClips": 0, "live": 0,
            **{m: 0 for m in S.METRICS},
        })
        o["clips"] += 1
        if r["date"] >= cutoff:
            o["newClips"] += 1
        if r["live"]:
            o["live"] += 1
        for m in S.METRICS:
            o[m] += r["inc"].get(m, 0)
    for o in by_owner.values():
        o["leads"] = _lead_for(o["name"], lead_ch) if o["side"] == "tiktok" else 0
        o["leadKnown"] = bool(LEAD_ALIAS.get(o["name"])) if o["side"] == "tiktok" else False
        chans.append(o)
    chans.sort(key=lambda c: -c["views"])

    return {
        "from": f.isoformat(), "to": t.isoformat(), "newDays": new_days,
        "cutoff": cutoff,
        "totals": totals,
        "grand": {m: sum(v[m] for v in totals.values()) for m in S.METRICS},
        "newClips": [pack(r) for r in new_rows[:top]],
        "newCount": len(new_rows),
        "oldTop": [pack(r) for r in old_live_sorted[:top]],
        "oldLow": [pack(r) for r in reversed(old_live_sorted[-top:])] if old_live_sorted else [],
        "oldCount": len(old_rows), "oldLive": len(old_live),
        "channels": chans,
        "leads": {"byChannel": lead_ch, "group": lead_group,
                  "social": lead_group.get("tiktok", 0) + lead_group.get("page", 0)},
        # ★ บอกตรงๆ ว่าอะไรไม่มี — ไม่ใส่ช่องที่จะเป็น 0 ทุกแถว
        "missing": ["ยอดบันทึก (saves) — ไม่มีแพลตฟอร์มไหนเปิดให้ดึงผ่าน API",
                    "ยอดแชร์ของ YouTube — API ไม่ให้"],
    }
