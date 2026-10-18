"""กราฟหน้า "ภาพรวม" ของแอปมือถือ (แอดมิน · เซลล์ · จัดซื้อ) — ★ 18 ต.ค.69
เจ้าของ "อยากเปลี่ยนหน้าภาพรวมเป็นกราฟที่แสดงอยู่ในหน้า dashboard เราอยู่แล้ว เอาขึ้นมาก่อน"

ตัวเลขชุดเดียวกับ 4 กราฟในแท็บภาพรวมของแดชบอร์ด (`initCharts` ใน index.html) — **ไม่มีสูตรใหม่**
อ่านผลที่ cron อุ่นไว้ (`fetch_dashboard_data`) แล้วตัดตามช่วงวันที่ แบบเดียวกับหน้าเว็บ:
  1) Lead ปกติ + RJ            (dailyByMonth.leads / leadRJ)
  2) จอง vs ปล่อย               (dailyByMonth.bookings / dones)
  3) สถานะเคสที่จองในช่วงนี้      (bookingCases · กลางวง = % ปล่อยแล้ว)
  4) ยอดปล่อย (฿)               (dailyByMonth.dealValue)
ช่วง ≤ 31 วัน = รายวัน · ยาวกว่า = รายเดือน · วัน/เดือนที่ยังมาไม่ถึง = None (เส้นกราฟไม่ดิ่งลงศูนย์ — กติกาเดียวกับเว็บ)

★ เซลล์ (เจ้าของเลือก "ของตัวเอง + อันดับ") — ตัวเลข/กราฟของตัวเองเท่านั้น (dailyBySeller · เคสจองของตัวเอง ·
  ชุดเดียวกับกราฟหน้าเซลล์ในเว็บ) + **อันดับคะแนน** = `compute_diligence_scores` ตารางเดียวกับที่หน้าเซลล์ในเว็บโชว์
  (ชื่อ + คะแนนเท่านั้น — ข้อยกเว้นเดิมที่เจ้าของเลือกไว้ มิ.ย.69 · ไม่ส่งลีด/ยอดของคนอื่น)
"""
import time
from datetime import date, timedelta

RANGES = ("month", "prev", "year")          # เดือนนี้ · เดือนก่อน · ทั้งปี
_KEYS = (("lead", "leads"), ("rj", "leadRJ"), ("booking", "bookings"), ("done", "dones"), ("value", "dealValue"))


def _mget(d, k):
    """dict ที่คีย์เป็นเดือน — คำนวณสดได้ int · อ่านจากที่เก็บ (JSON) ได้ str"""
    if not isinstance(d, dict):
        return {}
    v = d.get(k)
    if v is None:
        v = d.get(str(k))
    return v if isinstance(v, dict) else {}


def _day(dd: dict, key: str, day: int):
    a = dd.get(key) or []
    try:
        return a[day] or 0
    except (IndexError, TypeError):
        return 0


def date_range(kind: str, today: date) -> tuple:
    first = today.replace(day=1)
    if kind == "prev":
        end = first - timedelta(days=1)
        return end.replace(day=1), end
    if kind == "year":
        return date(today.year, 1, 1), date(today.year, 12, 31)
    nxt = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    return first, nxt - timedelta(days=1)


_SC: dict = {}          # คะแนนรายเดือน {(เดือน, ปี): (เวลา, rows)} — คำนวณจากผลแดชบอร์ด จำ 2 นาที


def _scores(month: int, year: int) -> list:
    from .fetch_dashboard import compute_diligence_scores
    hit = _SC.get((month, year))
    if hit and time.monotonic() - hit[0] < 120:
        return hit[1]
    rows = compute_diligence_scores(month, year) or []
    _SC[(month, year)] = (time.monotonic(), rows)
    return rows


def ranking(kind: str, today: date, me: str = "", rows: list | None = None) -> dict:
    """อันดับคะแนนเซลล์ของเดือนในช่วงที่เลือก (ทั้งปี = เดือนนี้ — คะแนนคิดรายเดือน) · ชื่อ + คะแนนเท่านั้น"""
    from .constants import MONTHS_SHORT
    start, _end = date_range("prev" if kind == "prev" else "month", today)
    rows = rows if rows is not None else _scores(start.month, start.year)
    rows = sorted(rows, key=lambda e: -(e.get("score") or 0))
    out = [{"rank": i + 1, "name": e.get("name") or "", "team": e.get("team") or "",
            "score": round(e.get("score") or 0, 1), "me": bool(me) and e.get("name") == me}
           for i, e in enumerate(rows)]
    return {"month": "%s %s" % (MONTHS_SHORT[start.month - 1], str(start.year + 543)[-2:]), "rows": out,
            "yearNote": kind == "year"}


def build(kind: str = "month", data: dict | None = None, today: date | None = None, seller: str = "",
          scores: list | None = None) -> dict:
    """`seller` ว่าง = ทั้งทีม (แอดมิน) · มีชื่อ = เฉพาะของเซลล์คนนั้น (ตัวเลข/กราฟ/เคสจอง/เป้า)"""
    from .constants import MONTHS_SHORT, STATUS_COLOR, STATUS_ORDER, TARGETS
    from .fetch_dashboard import bangkok_now, fetch_dashboard_data, parse_date

    kind = kind if kind in RANGES else "month"
    today = today or bangkok_now().date()
    start, end = date_range(kind, today)
    data = data if data is not None else (fetch_dashboard_data() or {})
    dbm = ((data.get("dailyBySeller") or {}).get(seller) or {}) if seller else (data.get("dailyByMonth") or {})

    days, d = [], start
    while d <= end:
        days.append(d)
        d += timedelta(days=1)
    daily = len(days) <= 31
    labels, series = [], {k: [] for k, _ in _KEYS}
    if daily:
        for d in days:
            dd = _mget(dbm, d.month)
            labels.append("%d/%d" % (d.day, d.month))
            for k, src in _KEYS:
                series[k].append(None if d > today else _day(dd, src, d.day))
    else:
        for m in sorted({x.month for x in days}):
            dd = _mget(dbm, m)
            labels.append(MONTHS_SHORT[m - 1])
            for k, src in _KEYS:
                series[k].append(None if date(start.year, m, 1) > today
                                 else sum(_day(dd, src, x.day) for x in days if x.month == m))

    # โดนัท: สถานะปัจจุบันของเคสที่ "จอง" ในช่วงนี้ (ตัวเดียวกับ chart-pipeline ของเว็บ)
    pl = {k: 0 for k in STATUS_ORDER}
    for b in data.get("bookingCases") or []:
        bd = parse_date(str(b.get("date") or ""))
        if seller and (b.get("seller") or "") != seller:
            continue
        if bd and start <= bd <= end and b.get("status") in pl:
            pl[b["status"]] += 1
    total = sum(pl.values())

    months = len({x.month for x in days})
    try:
        target = int(TARGETS.get(seller) or 0) * months if seller else 0
    except (TypeError, ValueError):
        target = 0
    try:
        rank = ranking(kind, today, seller, scores)
    except Exception as e:                     # คะแนนพัง = กราฟยังมา (บอกเหตุผลแทน)
        rank = {"error": str(e)[:200], "rows": []}
    return {
        "ok": True,
        "who": seller,
        "target": target,
        "ranking": rank,
        "range": kind,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "daily": daily,
        "labels": labels,
        "series": series,
        "totals": {k: sum(v or 0 for v in vals) for k, vals in series.items()},
        "pipeline": [{"status": k, "n": pl[k], "color": STATUS_COLOR.get(k, "#888888")} for k in STATUS_ORDER],
        "pipelineTotal": total,
        "releasedPct": round(pl.get("ปล่อย", 0) * 100 / total) if total else None,
        "updatedAt": (data.get("meta") or {}).get("generatedAt") or "",
    }


# ─────────────────────────────────────────────────────────────
#  ★ 18 ต.ค.69 — กราฟของทีมจัดซื้อ (เจ้าของ "ทำหน้ากราฟให้จัดซื้อด้วย")
#  ตัวเลขชุดเดียวกับ 2 การ์ดในแดชบอร์ด: "ฝั่งจัดซื้อ (รับซื้อรถ)" + "รถซื้อเข้า รายคน (ตามวิธี)"
#  (index.html · `plRows`/`chAgg`/`byAgg` และ `bcF`/`_catOf`/`B_TARGETS`) — **ไม่มีสูตรใหม่**:
#    ลีดรับซื้อ = purchaseLeads [เดือน, วัน, ช่องทาง, รับซื้อ(1)/ไม่รับซื้อ(2)/ยังไม่ตัดสิน(0), จัดซื้อ, คุณภาพ]
#    รถซื้อเข้า = boughtCars    [เดือน, วัน, วิธีได้รถ, จัดซื้อ, …]
#    เป้า       = purchaseTargets {หมวดวิธี: {คน: เป้า/เดือน}} × จำนวนเดือนในช่วง (ว่าง = ค่าตั้งต้นใน views.py)
#  กรองช่วงแบบเดียวกับเว็บ: รู้วัน = เทียบวันที่ · ไม่รู้วัน (0) = นับถ้าเดือนอยู่ในช่วง
# ─────────────────────────────────────────────────────────────
BUY_CATS = (("หาเอง", "#ca8a04"), ("online", "#16a34a"), ("รถเทิร์น", "#2563eb"), ("ขายหน้าร้าน", "#dc2626"))
BUY_QUALITY = (("HOT", "Hot", "#2563eb"), ("VERY HOT", "Very Hot", "#dc2626"),
               ("COOL", "Cool", "#0891b2"), ("REJECT", "REJECT", "#6b7280"))
BUY_CH_COLORS = {"Line@": "#22c55e", "เพจบ้านเก่า": "#0ea5e9", "เพจอ่อนนุช": "#06b6d4", "เพจguru": "#8b5cf6",
                 "กลุ่มรับซื้อรถ": "#ef4444", "เทิร์นรถ": "#d97706", "หน้าร้านบ้านเก่า": "#f97316",
                 "หน้าร้านเทพารักษ์": "#a855f7", "เบอร์กลางส่วนตัว": "#3b82f6", "TIKTOK": "#64748b"}
BUY_CH_TOP = 6              # ช่องทางที่โชว์แยก · ที่เหลือรวมเป็น "อื่นๆ"
_BUY_KEYS = ("lead", "buy", "no", "bought")


def _nkey(s) -> str:
    return "".join(str(s or "").lower().split())


def buy_cat(method: str, mmap: dict | None = None) -> str:
    """หมวดของ "วิธีได้รถ" — map ที่แอดมินตั้ง (ชนะ) → คำในชื่อ → หาเอง (ตรงกับ `_catOf` ของเว็บ)"""
    s = str(method or "").strip()
    if mmap and mmap.get(s):
        return mmap[s]
    if "online" in s.lower():
        return "online"
    if "เทิร์น" in s:
        return "รถเทิร์น"
    if "หน้าร้าน" in s:
        return "ขายหน้าร้าน"
    return "หาเอง"


def _buy_targets(data: dict) -> dict:
    tg = data.get("purchaseTargets") or {}
    if isinstance(tg, dict) and tg:
        return tg
    try:
        from dashboard.views import PURCHASE_TARGETS_DEFAULT
        return PURCHASE_TARGETS_DEFAULT
    except Exception:
        return {}


def build_buyer(kind: str = "month", data: dict | None = None, today: date | None = None,
                buyer_keys: list | None = None, who: str = "") -> dict:
    """`buyer_keys` ว่าง = ทั้งทีม (แอดมิน) · มีค่า = ชื่อที่ชีตจัดซื้อใช้ของคนนั้น (purchase_page.owner_keys)
    อันดับ = รถซื้อเข้าเทียบเป้าของแต่ละคนในช่วงเดียวกัน (ชื่อ + ตัวเลขเท่านั้น · ไม่มีข้อมูลลูกค้า)"""
    from .constants import MONTHS_SHORT
    from .fetch_dashboard import bangkok_now, fetch_dashboard_data

    kind = kind if kind in RANGES else "month"
    today = today or bangkok_now().date()
    start, end = date_range(kind, today)
    data = data if data is not None else (fetch_dashboard_data() or {})
    keys = {_nkey(k) for k in (buyer_keys or []) if _nkey(k)}

    days, d = [], start
    while d <= end:
        days.append(d)
        d += timedelta(days=1)
    months = sorted({x.month for x in days})
    daily = len(days) <= 31

    def in_range(m, dd):
        try:
            m, dd = int(m or 0), int(dd or 0)
        except (TypeError, ValueError):
            return False
        if dd > 0:
            try:
                return start <= date(start.year, m, dd) <= end
            except ValueError:
                return False
        return m in months

    def mine(name):
        return (not keys) or _nkey(name) in keys

    leads = [r for r in (data.get("purchaseLeads") or [])
             if isinstance(r, (list, tuple)) and len(r) >= 6 and in_range(r[0], r[1]) and mine(r[4])]
    bought_all = [r for r in (data.get("boughtCars") or [])
                  if isinstance(r, (list, tuple)) and len(r) >= 4 and in_range(r[0], r[1])]
    bought = [r for r in bought_all if mine(r[3])]

    # ── series (รายวัน ≤31 วัน · ไม่งั้นรายเดือน) — แถวที่ไม่รู้วันไม่ลงกราฟรายวัน แต่นับในตัวเลขรวม ──
    def slot(m, dd):
        try:
            m, dd = int(m or 0), int(dd or 0)
        except (TypeError, ValueError):
            return None
        if daily:
            if dd <= 0:
                return None
            try:
                return days.index(date(start.year, m, dd))
            except ValueError:
                return None
        return months.index(m) if m in months else None

    n = len(days) if daily else len(months)
    series = {k: [0] * n for k in _BUY_KEYS}
    for r in leads:
        i = slot(r[0], r[1])
        if i is None:
            continue
        series["lead"][i] += 1
        if r[3] == 1:
            series["buy"][i] += 1
        elif r[3] == 2:
            series["no"][i] += 1
    for r in bought:
        i = slot(r[0], r[1])
        if i is not None:
            series["bought"][i] += 1
    if daily:
        labels = ["%d/%d" % (x.day, x.month) for x in days]
        for k in _BUY_KEYS:
            series[k] = [None if days[i] > today else v for i, v in enumerate(series[k])]
    else:
        labels = [MONTHS_SHORT[m - 1] for m in months]
        for k in _BUY_KEYS:
            series[k] = [None if date(start.year, months[i], 1) > today else v for i, v in enumerate(series[k])]

    n_buy = sum(1 for r in leads if r[3] == 1)
    n_no = sum(1 for r in leads if r[3] == 2)
    totals = {"lead": len(leads), "buy": n_buy, "no": n_no, "pending": len(leads) - n_buy - n_no,
              "bought": len(bought)}

    # ── หมวดวิธีได้รถ เทียบเป้า ──
    mmap = data.get("purchaseMethodMap") or {}
    targets = _buy_targets(data)
    mc = len(months)

    def tgt(cat, person=None):
        row = targets.get(cat) or {}
        if person is not None:
            return int(round((row.get(person) or 0) * mc))
        if keys:
            return int(round(sum(v or 0 for p, v in row.items() if _nkey(p) in keys) * mc))
        return int(round(sum(v or 0 for v in row.values()) * mc))

    cat_n = {c: 0 for c, _ in BUY_CATS}
    for r in bought:
        c = buy_cat(r[2], mmap)
        cat_n[c] = cat_n.get(c, 0) + 1
    cats = [{"key": c, "n": cat_n.get(c, 0), "target": tgt(c), "color": col} for c, col in BUY_CATS]
    target = sum(c["target"] for c in cats)

    # ── ช่องทางลีด (ตามจำนวน) + คุณภาพ ──
    ch = {}
    for r in leads:
        a = ch.setdefault(r[2] or "(ไม่ระบุ)", {"n": 0, "buy": 0, "no": 0})
        a["n"] += 1
        if r[3] == 1:
            a["buy"] += 1
        elif r[3] == 2:
            a["no"] += 1
    ch_rows = sorted(ch.items(), key=lambda kv: -kv[1]["n"])
    channels = [{"name": k, "color": BUY_CH_COLORS.get(k, "#94a3b8"), **v} for k, v in ch_rows[:BUY_CH_TOP]]
    rest = ch_rows[BUY_CH_TOP:]
    if rest:
        channels.append({"name": "อื่นๆ (%d ช่อง)" % len(rest), "color": "#cbd5e1",
                         "n": sum(v["n"] for _, v in rest), "buy": sum(v["buy"] for _, v in rest),
                         "no": sum(v["no"] for _, v in rest)})
    q_n = {}
    for r in leads:
        q = str(r[5] or "").upper()
        q_n[q] = q_n.get(q, 0) + 1
    quality = [{"key": k, "name": nm, "n": q_n.get(k, 0), "color": col} for k, nm, col in BUY_QUALITY]

    # ── อันดับรถซื้อเข้า (ทั้งทีม · ชื่อ + ยอด + เป้า) ──
    people = []
    for row in targets.values():
        for p in (row or {}):
            if p not in people:
                people.append(p)
    got = {}
    for r in bought_all:
        p = str(r[3] or "").strip() or "(ไม่ระบุ)"
        got[p] = got.get(p, 0) + 1
        if p not in people:
            people.append(p)
    rk = [{"name": p, "bought": got.get(p, 0), "target": sum(tgt(c, p) for c, _ in BUY_CATS),
           "me": bool(keys) and _nkey(p) in keys} for p in people]
    rk = [r for r in rk if r["bought"] or r["target"]]
    rk.sort(key=lambda r: (-r["bought"], -(r["bought"] / r["target"] if r["target"] else 0), r["name"]))
    for i, r in enumerate(rk):
        r["rank"] = i + 1
        r["pct"] = round(r["bought"] * 100 / r["target"]) if r["target"] else None

    return {
        "ok": True,
        "mode": "buy",
        "who": who,
        "range": kind,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "daily": daily,
        "labels": labels,
        "series": series,
        "totals": totals,
        "target": target,
        "cats": cats,
        "channels": channels,
        "quality": quality,
        "ranking": {"rows": rk},
        # % รับซื้อ = รับซื้อ ÷ ลีดทั้งหมด (สูตรเดียวกับคอลัมน์ "% รับซื้อ" ในตารางช่องทางของเว็บ)
        "buyPct": round(n_buy * 100 / len(leads)) if leads else None,
        "updatedAt": (data.get("meta") or {}).get("generatedAt") or "",
    }
