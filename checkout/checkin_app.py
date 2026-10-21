"""เช็คชื่อเข้างานจากแอปมือถือ — ★ 14 ต.ค.69 (เจ้าของสั่ง)

*"เราจะให้เขาเช็คชื่อแล้วเก็บข้อมูลไว้ใน log ในระบบเรา แต่จะไม่ส่งลงกลุ่ม ยกเว้นส่งแจ้งตอน 9:30-10:00"*
*"จะมีคนที่ต้องออกนอกสาขากับคนที่ต้องเข้าสาขา … admin หรือผู้บริหารจะต้องเป็นคนตั้งเงื่อนไข
ว่าคนไหนสามารถเช็คชื่อนอกสถานที่ได้"*

- เช็คชื่อได้ **2 ทาง**: กดในแอป (เซลฟี่ + ตำแหน่ง · ไฟล์นี้) หรือส่งรูปในกลุ่ม LINE เหมือนเดิม (n8n)
  · **อันไหนมาก่อนนับอันนั้น** — แอปไม่สร้างแถวซ้ำถ้าวันนี้มีแล้ว · คนอ่าน (ตาราง/พาเนล/แอป) ใช้ `first_per_employee`
    คัดแถวแรกของแต่ละคน (n8n ไม่รู้ว่ามีแถวจากแอปแล้ว จึงอาจเขียนแถวที่ 2 ด้วยไอดี LINE ของมันเอง)
- **ไม่ส่งอะไรลงกลุ่มตอนเช็คชื่อ** — ตารางตอน 9:30 และรอบตามตัว 10:00 (checkin_report) อ่านตาราง
  `checkout_checkin` อยู่แล้ว จึงเห็นคนที่เช็คชื่อในแอปเอง
- ตำแหน่ง: `Employee.checkin_anywhere` (แอดมินติ๊กในหน้าพนักงาน) = กดได้ทุกที่ ·
  ไม่ติ๊ก = ต้องอยู่ในรัศมีสาขาใดสาขาหนึ่ง (KV `checkin_sites` · ตั้งในหน้าตั้งค่าเช็คชื่อ)
  · **ยังไม่ได้ตั้งพิกัดสาขาเลย = ยอมให้กด** (ไม่งั้นวันแรกไม่มีใครเช็คชื่อได้) แต่จดไว้ว่าไม่ได้ตรวจ
- เซลฟี่เป็นข้อมูลส่วนบุคคล → เก็บนอก /media/ (`private_media/checkin/…`) เปิดได้ทางเดียวคือ
  endpoint ที่เช็คสิทธิ์แอดมิน · ลบเองเมื่อเกิน `PHOTO_KEEP_DAYS`
"""
import math
import os
import secrets
from pathlib import Path

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

SITES_KEY = "checkin_sites"
CLEAN_KEY = "checkin_photo_clean"
DEFAULT_RADIUS = 300          # เมตร · ลานรถกว้าง + GPS ในอาคารคลาดได้หลายสิบเมตร
MIN_RADIUS, MAX_RADIUS = 50, 5000
MAX_SITES = 20
ACC_CAP = 100                 # ยอมหักความคลาดเคลื่อนของ GPS ได้ไม่เกินเท่านี้ (เมตร)
MAX_PHOTO_MB = 10
PHOTO_KEEP_DAYS = 60
GRACE_MIN = 5                 # เผื่อสาย 5 นาที — กติกาเดียวกับตารางเช็คชื่อ (checkin_report.GRACE_MIN)
SOURCE = "app"                # CheckIn.time_source ของแถวที่มาจากแอป
OUT_KEY = "out"               # ★ 21 ต.ค.69 เวลาออกงาน เก็บใน CheckIn.raw["out"] ของแถวแรกของวัน (ไม่ต้องเพิ่มตาราง)
_IMG_TYPES = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png", "image/heic": ".heic",
              "image/heif": ".heic", "image/webp": ".webp"}


def photo_root() -> Path:
    base = getattr(settings, "CHECKIN_MEDIA_ROOT", "") or os.getenv("CHECKIN_MEDIA_ROOT", "")
    return Path(base) if base else Path(settings.BASE_DIR) / "private_media" / "checkin"


# ─────────────────────────── พิกัดสาขา ───────────────────────────

def sites() -> list:
    from dashboard.services import cache_store
    try:
        v = cache_store.get_kv(SITES_KEY) or {}
        rows = v.get("data", v) if isinstance(v, dict) else v
        rows = rows.get("sites", []) if isinstance(rows, dict) else rows
        return [r for r in (rows or []) if isinstance(r, dict)]
    except Exception:
        return []


def clean_sites(rows) -> tuple:
    """ตรวจรายการสาขา → (ok, error, rows) · ผิดช่องไหนบอกช่องนั้น ไม่เงียบ"""
    if not isinstance(rows, list):
        return False, "รูปแบบข้อมูลไม่ถูกต้อง", []
    if len(rows) > MAX_SITES:
        return False, "ตั้งได้ไม่เกิน %d สาขา" % MAX_SITES, []
    out, names = [], set()
    for i, r in enumerate(rows, 1):
        if not isinstance(r, dict):
            return False, "แถวที่ %d ไม่ถูกต้อง" % i, []
        name = str(r.get("name") or "").strip()[:60]
        if not name:
            return False, "แถวที่ %d: ต้องมีชื่อสาขา" % i, []
        if name in names:
            return False, "ชื่อสาขา \"%s\" ซ้ำ" % name, []
        try:
            lat, lng = float(r.get("lat")), float(r.get("lng"))
        except (TypeError, ValueError):
            return False, "สาขา %s: พิกัดต้องเป็นตัวเลข" % name, []
        if not (-90 <= lat <= 90) or not (-180 <= lng <= 180) or (lat == 0 and lng == 0):
            return False, "สาขา %s: พิกัดไม่ถูกต้อง" % name, []
        try:
            rad = int(float(r.get("radius") or DEFAULT_RADIUS))
        except (TypeError, ValueError):
            return False, "สาขา %s: รัศมีต้องเป็นตัวเลข" % name, []
        if not (MIN_RADIUS <= rad <= MAX_RADIUS):
            return False, "สาขา %s: รัศมีต้องอยู่ระหว่าง %d–%d เมตร" % (name, MIN_RADIUS, MAX_RADIUS), []
        names.add(name)
        out.append({"name": name, "lat": round(lat, 6), "lng": round(lng, 6), "radius": rad})
    return True, "", out


def save_sites(rows) -> tuple:
    ok, err, clean = clean_sites(rows)
    if not ok:
        return False, err, []
    from dashboard.services import cache_store
    cache_store.set_kv(SITES_KEY, {"sites": clean})
    return True, "", clean


def distance_m(lat1, lng1, lat2, lng2) -> float:
    """ระยะทางบนผิวโลก (haversine) เป็นเมตร"""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def nearest(lat, lng, rows=None):
    """สาขาที่ใกล้ที่สุด → (site, ระยะเมตร) · ไม่มีสาขา = (None, None)"""
    rows = sites() if rows is None else rows
    best = (None, None)
    for s in rows:
        d = distance_m(lat, lng, s["lat"], s["lng"])
        if best[1] is None or d < best[1]:
            best = (s, d)
    return best


def place_check(emp, lat, lng, acc) -> dict:
    """ตัดสินว่ากดเช็คชื่อตรงนี้ได้ไหม → {ok, site, distance, note, error}"""
    site, dist = nearest(lat, lng)
    out = {"ok": True, "site": site["name"] if site else "", "distance": round(dist) if dist is not None else None,
           "note": "", "error": ""}
    if emp.checkin_anywhere:
        out["note"] = "เช็คชื่อนอกสถานที่ได้"
        return out
    if site is None:
        out["note"] = "ยังไม่ได้ตั้งพิกัดสาขา (ไม่ได้ตรวจตำแหน่ง)"
        return out
    slack = min(max(float(acc or 0), 0.0), ACC_CAP)
    if dist - slack > site["radius"]:
        out["ok"] = False
        out["error"] = ("อยู่ห่างสาขา%s %s — ต้องเช็คชื่อที่สาขา (ในรัศมี %d เมตร) · ถ้างานวันนี้อยู่นอกสาขา ให้แอดมินตั้งว่า "
                        "\"เช็คชื่อนอกสถานที่ได้\"") % (site["name"], _fmt_dist(dist), site["radius"])
    return out


def _fmt_dist(m) -> str:
    return "%.1f กม." % (m / 1000.0) if m >= 1000 else "%d เมตร" % round(m)


# ─────────────────────────── สถานะ / คัดแถว ───────────────────────────

def _mins(t):
    from .checkin_report import _mins as m
    return m(t)


def _rank(c):
    """แถวที่ "มาก่อน" ของคนเดียวกัน — มีเวลาอ่านได้ก่อนแถวอ่านไม่ออก แล้วเรียงตามเวลา"""
    t = _mins(c.time_hm)
    return (0 if t is not None else 1, t if t is not None else 0, c.checkin_at or c.created_at, c.id)


def first_per_employee(rows) -> list:
    """คนเดียวมีได้ 2 แถวต่อวัน (กดในแอป + ส่งรูปในกลุ่ม) → เก็บแถวที่มาก่อนของแต่ละคน
    แถวที่ยังไม่ผูกทะเบียน (employee ว่าง) คงไว้ทั้งหมด (คัดด้วยไอดีไม่ได้ ข้อมูลต้องไม่หาย)"""
    best, loose = {}, []
    for c in rows:
        if not c.employee_id:
            loose.append(c)
            continue
        key = (c.employee_id, c.date_iso)
        if key not in best or _rank(c) < _rank(best[key]):
            best[key] = c
    return list(best.values()) + loose


def status_for(time_hm: str, work_start: str) -> tuple:
    """(status, late_min) — ตรงเวลาถ้าไม่เกินเวลาเข้างาน + GRACE_MIN · ไม่มีเวลาเข้างาน = ตรงเวลา (ตัดสินไม่ได้)"""
    a, b = _mins(time_hm), _mins(work_start)
    if a is None:
        return "abnormal", 0
    if b is not None and a - b > GRACE_MIN:
        return "late", a - b
    return "ontime", 0


def today_info(emp, day=None) -> dict:
    """สถานะเช็คชื่อวันนี้ + กติกาตำแหน่ง ให้หน้าแอป"""
    from .models import CheckIn
    day = day or timezone.localdate()
    rows = first_per_employee(CheckIn.objects.filter(employee=emp, date_iso=day))
    c = rows[0] if rows else None
    rows_s = sites()
    out = {"done": bool(c), "anywhere": bool(emp.checkin_anywhere), "track": bool(emp.track_checkin),
           "workStart": emp.work_start or "", "sites": [s["name"] for s in rows_s],
           # ★ 21 ต.ค.69 พิกัดสาขาให้แผนที่หน้าหลักของแอปปักหมุด (ตั้งในหน้าตั้งค่าเช็คชื่อ)
           "siteList": [{"name": s.get("name", ""), "lat": s.get("lat"), "lng": s.get("lng"),
                         "radius": s.get("radius", DEFAULT_RADIUS)} for s in rows_s]}
    if c:
        st, late = status_for(c.time_hm, c.work_start or emp.work_start)
        out.update(time=c.time_hm, status=c.status or st, lateMin=late if (c.status or st) == "late" else 0,
                   source="แอป" if c.time_source == SOURCE else "รูปในกลุ่ม LINE",
                   site=(c.raw or {}).get("site", "") if c.time_source == SOURCE else "")
        o = (c.raw or {}).get(OUT_KEY) or {}
        if isinstance(o, dict) and o.get("hm"):
            out.update(outTime=o.get("hm", ""), outSite=o.get("site", ""))
    return out


# ─────────────────────────── เช็คชื่อ ───────────────────────────

def _save_photo(emp, day, f) -> str:
    """เก็บเซลฟี่ไว้นอก /media/ → คืน path สัมพัทธ์จาก photo_root()"""
    ctype = (getattr(f, "content_type", "") or "").lower()
    ext = _IMG_TYPES.get(ctype)
    if not ext:
        name = (getattr(f, "name", "") or "").lower()
        ext = next((e for e in (".jpg", ".jpeg", ".png", ".heic", ".webp") if name.endswith(e)), "")
        ext = ".jpg" if ext == ".jpeg" else ext
    if not ext:
        raise ValueError("ไฟล์ต้องเป็นรูปภาพ")
    if f.size > MAX_PHOTO_MB * 1024 * 1024:
        raise ValueError("รูปใหญ่เกิน %d MB" % MAX_PHOTO_MB)
    rel = "%s/%d-%s-%s%s" % (day.strftime("%Y-%m"), emp.pk, day.isoformat(), secrets.token_hex(6), ext)
    dest = photo_root() / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with open(tmp, "wb") as out:
        for chunk in f.chunks():
            out.write(chunk)
    os.replace(tmp, dest)
    return rel


def check_in(emp, user: dict, lat, lng, acc, photo) -> tuple:
    """กดเช็คชื่อในแอป → (http_status, payload)

    วันนี้มีแถวแล้ว (แอป/กลุ่ม LINE) = ไม่สร้างใหม่ คืนของเดิม (อันไหนมาก่อนนับอันนั้น · กันกดซ้ำเพื่อแก้เวลาสาย)
    """
    from .models import CheckIn
    if not emp:
        return 403, {"ok": False, "error": "บัญชีนี้ยังไม่ผูกกับทะเบียนพนักงาน — แจ้งแอดมินให้เพิ่มชื่อเล่นในหน้าพนักงาน"}
    if not emp.track_checkin:
        return 400, {"ok": False, "error": "บัญชีนี้ตั้งไว้ว่าไม่ต้องเช็คชื่อเข้างาน"}
    try:
        lat, lng = float(lat), float(lng)
        acc = float(acc or 0)
    except (TypeError, ValueError):
        return 400, {"ok": False, "error": "อ่านตำแหน่งไม่ได้ — เปิดการเข้าถึงตำแหน่งให้แอปแล้วลองใหม่"}
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180) or (lat == 0 and lng == 0):
        return 400, {"ok": False, "error": "ตำแหน่งไม่ถูกต้อง — ลองใหม่อีกครั้ง"}
    if photo is None:
        return 400, {"ok": False, "error": "ต้องถ่ายรูปเซลฟี่ก่อนเช็คชื่อ"}

    now = timezone.localtime()
    day = now.date()
    prev = first_per_employee(CheckIn.objects.filter(employee=emp, date_iso=day))
    if prev:
        info = today_info(emp, day)
        return 200, {"ok": True, "already": True, "info": info,
                     "message": "วันนี้เช็คชื่อแล้วเมื่อ %s (%s)" % (info.get("time") or "-", info.get("source"))}

    place = place_check(emp, lat, lng, acc)
    if not place["ok"]:
        return 403, {"ok": False, "error": place["error"], "distance": place["distance"], "site": place["site"]}

    try:
        rel = _save_photo(emp, day, photo)
    except ValueError as e:
        return 400, {"ok": False, "error": str(e)}

    hm = "%d:%02d" % (now.hour, now.minute)
    ws = emp.work_start or ""
    st, late = status_for(hm, ws)
    reason = ("สาย %d นาที (เช็คชื่อในแอป)" % late) if st == "late" else "ตรงเวลา (เช็คชื่อในแอป)"
    addr = place["site"] and ("สาขา%s (%s)" % (place["site"], _fmt_dist(place["distance"] or 0))) or ""
    try:
        with transaction.atomic():
            c = CheckIn.objects.create(
                employee=emp, user_id=("app:%d" % emp.pk), display_name=emp.nickname, date_iso=day,
                checkin_at=now, time_hm=hm, work_start=ws, status=st, reason=reason[:200],
                time_source=SOURCE, full_address=addr[:300],
                raw={"lat": lat, "lng": lng, "acc": round(acc), "site": place["site"],
                     "distance": place["distance"], "place": place["note"], "photo": rel,
                     "login": (user or {}).get("user_id", "")[:64]})
    except IntegrityError:
        # กดซ้ำพร้อมกัน 2 ครั้ง — แถวแรกเข้าไปแล้ว (unique user_id+วัน) · ทิ้งรูปของครั้งหลัง
        try:
            (photo_root() / rel).unlink()
        except OSError:
            pass
        info = today_info(emp, day)
        return 200, {"ok": True, "already": True, "info": info, "message": "วันนี้เช็คชื่อแล้ว"}
    _cleanup_maybe()
    try:
        from dashboard.services import eventlog
        eventlog.log("checkin", name="เช็คชื่อในแอป", target=emp.nickname[:64], ok=True,
                     status=st, site=place["site"], distance=place["distance"])
    except Exception:
        pass
    msg = ("เช็คชื่อแล้ว %s · ตรงเวลา" % hm) if st == "ontime" else \
        ("เช็คชื่อแล้ว %s · สาย %d นาที" % (hm, late)) if st == "late" else ("เช็คชื่อแล้ว %s" % hm)
    if place["note"] and not emp.checkin_anywhere:
        msg += " · " + place["note"]
    return 200, {"ok": True, "already": False, "id": c.pk, "message": msg, "info": today_info(emp, day)}


def check_out(emp, user: dict, lat, lng, acc) -> tuple:
    """กด "ออกงาน" ในแอป (★ 21 ต.ค.69 · เจ้าของสั่ง) → (http_status, payload)

    เก็บที่ `CheckIn.raw["out"]` ของแถวเช็คชื่อแรกของวันนี้ (แถวจากแอปหรือจากรูปในกลุ่ม LINE ก็ได้)
    · ต้องเช็คชื่อเข้างานก่อน · ตำแหน่งกติกาเดียวกับตอนเข้างาน (นอกสถานที่ได้ / ในรัศมีสาขา)
    · กดซ้ำ = บันทึกเวลาออกงานใหม่ (ใช้เวลาล่าสุด — กดก่อนเวลาเลิกงานแล้วกลับมาทำต่อได้) · ไม่ต้องถ่ายเซลฟี่
    · ไม่ส่งอะไรลงกลุ่ม LINE · ตารางเช็คชื่อที่ส่งเข้า LINE ยังไม่แสดงเวลาออก
    """
    from .models import CheckIn
    if not emp:
        return 403, {"ok": False, "error": "บัญชีนี้ยังไม่ผูกกับทะเบียนพนักงาน — แจ้งแอดมินให้เพิ่มชื่อเล่นในหน้าพนักงาน"}
    if not emp.track_checkin:
        return 400, {"ok": False, "error": "บัญชีนี้ตั้งไว้ว่าไม่ต้องเช็คชื่อเข้างาน"}
    try:
        lat, lng = float(lat), float(lng)
        acc = float(acc or 0)
    except (TypeError, ValueError):
        return 400, {"ok": False, "error": "อ่านตำแหน่งไม่ได้ — เปิดการเข้าถึงตำแหน่งให้แอปแล้วลองใหม่"}
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180) or (lat == 0 and lng == 0):
        return 400, {"ok": False, "error": "ตำแหน่งไม่ถูกต้อง — ลองใหม่อีกครั้ง"}

    now = timezone.localtime()
    day = now.date()
    rows = first_per_employee(CheckIn.objects.filter(employee=emp, date_iso=day))
    if not rows:
        return 400, {"ok": False, "error": "วันนี้ยังไม่ได้เช็คชื่อเข้างาน — กด \"เข้างาน\" ก่อน"}

    place = place_check(emp, lat, lng, acc)
    if not place["ok"]:
        err = place["error"].replace("ต้องเช็คชื่อที่สาขา", "ต้องกดออกงานที่สาขา")
        return 403, {"ok": False, "error": err, "distance": place["distance"], "site": place["site"]}

    hm = "%d:%02d" % (now.hour, now.minute)
    prev = ""
    with transaction.atomic():
        c = CheckIn.objects.select_for_update().get(pk=rows[0].pk)
        raw = dict(c.raw or {})
        old = raw.get(OUT_KEY)
        prev = old.get("hm", "") if isinstance(old, dict) else ""
        raw[OUT_KEY] = {"at": now.isoformat(timespec="seconds"), "hm": hm, "lat": lat, "lng": lng,
                        "acc": round(acc), "site": place["site"], "distance": place["distance"],
                        "place": place["note"], "login": (user or {}).get("user_id", "")[:64]}
        c.raw = raw
        c.save(update_fields=["raw"])
    try:
        from dashboard.services import eventlog
        eventlog.log("checkin", name="ออกงานในแอป", target=emp.nickname[:64], ok=True,
                     time=hm, prev=prev, site=place["site"], distance=place["distance"])
    except Exception:
        pass
    msg = ("บันทึกเวลาออกงานใหม่ %s (เดิม %s)" % (hm, prev)) if prev else ("ออกงานแล้ว %s" % hm)
    if place["note"] and not emp.checkin_anywhere:
        msg += " · " + place["note"]
    return 200, {"ok": True, "updated": bool(prev), "message": msg, "info": today_info(emp, day)}


def photo_file(c):
    """ไฟล์เซลฟี่ของแถวเช็คชื่อ (เฉพาะแถวจากแอป) → Path หรือ None · กัน path หลุดออกนอกโฟลเดอร์"""
    rel = (c.raw or {}).get("photo") if c.time_source == SOURCE else ""
    if not rel:
        return None
    root = photo_root().resolve()
    p = (root / rel).resolve()
    if root not in p.parents or not p.is_file():
        return None
    return p


def map_url(c) -> str:
    raw = c.raw or {}
    if c.time_source != SOURCE or raw.get("lat") is None:
        return ""
    return "https://www.google.com/maps?q=%s,%s" % (raw["lat"], raw["lng"])


def _cleanup_maybe():
    """ลบเซลฟี่ที่เก่ากว่า PHOTO_KEEP_DAYS — วันละครั้ง (ข้อมูลส่วนบุคคล ต้องไม่สะสมไม่จบ)"""
    from dashboard.services import cache_store
    today = timezone.localdate().isoformat()
    try:
        last = cache_store.get_kv(CLEAN_KEY) or {}
        last = last.get("data", last) if isinstance(last, dict) else {}
        if isinstance(last, dict) and last.get("date") == today:
            return
        cache_store.set_kv(CLEAN_KEY, {"date": today})
    except Exception:
        return
    cleanup_photos()


def cleanup_photos(days: int = PHOTO_KEEP_DAYS) -> int:
    root = photo_root()
    if not root.is_dir():
        return 0
    cut = timezone.now().timestamp() - days * 86400
    n = 0
    for p in root.rglob("*"):
        try:
            if p.is_file() and p.stat().st_mtime < cut:
                p.unlink()
                n += 1
        except OSError:
            pass
    return n
