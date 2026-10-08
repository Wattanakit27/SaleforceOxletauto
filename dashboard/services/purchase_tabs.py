"""เตรียมแท็บเดือนถัดไปของชีตจัดซื้อ "ซื้อขายเทิร์นรถ" ให้ล่วงหน้า — 8 ต.ค.69 (เจ้าของสั่ง "เผื่อเดือนหน้า")

ทำไมต้องมี
  n8n (workflow ซื้อขายเทิร์นรถ) เขียนเคสใหม่ลงแท็บ "ขายรถจบออนไลน์ <เดือนนี้><ปี>" ตามวันที่ส่ง
  · ถ้าวันที่ 1 ยังไม่มีแท็บของเดือนนั้น **โหนดเขียนล้ม แล้วเคสของวันนั้นหายทั้งหมด**
  · เดิมทีมสร้างแท็บเองทุกเดือน (8 ต.ค.69 ยังไม่มีแท็บ พ.ย.) — ลืมเมื่อไหร่ก็หาย

ทำอะไร
  1. หาแท็บเดือนล่าสุดที่มีอยู่ (ถอยได้ 3 เดือน) → **ทำสำเนา** (dropdown/สูตร/ความกว้าง/สีมาครบ)
  2. ในแท็บใหม่ **ล้างเฉพาะข้อมูล** 3 บล็อก (ค่าเท่านั้น — dropdown/รูปแบบเซลล์อยู่ครบ):
       A–W  เคส + Follow ของทีม · Y–AH บล็อก "รับซื้อรถ" · AQ–AV บล็อก "จัดซื้อรับเข้า"
     **ไม่แตะ** X / AP (เลขคันที่ที่ทีมพิมพ์รอไว้) · AI–AM (สรุปเป็นสูตร)
     และ **คอลัมน์ไหนมีสูตรอยู่ข้างใน = ไม่ล้างคอลัมน์นั้นทั้งคอลัมน์** (ทีมอาจเพิ่มสูตรทีหลัง)
  3. แก้ชื่อเดือนในแถว 1 ("ตุลาคม69" → "พฤศจิกายน69" · "รับซื้อรถ ตุลาคม69" → …)

กติกาที่ต้องรักษา
  - **มีแท็บอยู่แล้ว = ไม่ทำอะไรเลย** (ทีมสร้างเองก่อนก็ได้ ระบบไม่ทับ)
  - **ไม่แตะแท็บต้นฉบับเด็ดขาด** — ทุกคำสั่งเขียนอ้าง sheetId/ชื่อของแท็บใหม่เท่านั้น
  - **ล้างข้อมูลในแท็บใหม่ไม่สำเร็จ = ลบแท็บใหม่ทิ้งทันที** — ไม่งั้นเคสของเดือนก่อนจะค้างอยู่ใต้ชื่อเดือนใหม่
    แล้วแดชบอร์ดนับซ้ำ (fetch_dashboard นับเดือนตามชื่อแท็บ)
"""
import re
import urllib.parse

import requests

from .purchase_followup import prev_month, tab_name

# วันที่ของเดือนที่เริ่มเตรียมแท็บเดือนหน้า (เผื่อวันให้ทีมเห็นก่อน + ลองใหม่ได้หลายวันถ้าล้ม)
PREPARE_FROM_DAY = 25
# ถอยหาแท็บต้นแบบได้กี่เดือน
LOOK_BACK = 3
# แถวสุดท้ายที่ล้าง/ตรวจสูตร (เผื่อเยอะได้ — Sheets ตัดแถวว่างท้ายให้เอง)
MAX_ROW = 3000
FIRST_DATA_ROW = 3

# คอลัมน์ที่ล้างข้อมูลในแท็บใหม่ (index เริ่ม 0: A=0)
#   A–W (0–22) เคส+Follow · Y–AH (24–33) รับซื้อรถ · AQ–AV (42–47) จัดซื้อรับเข้า
#   ข้าม X(23) / AP(41) = เลขคันที่ที่ทีมพิมพ์รอไว้ · AI–AM(34–38) = สรุปเป็นสูตร
CLEAR_COLS = list(range(0, 23)) + list(range(24, 34)) + list(range(42, 48))

KV_LAST = "purchase_tab_last"      # ผลรอบล่าสุด (หน้าสถานะระบบอ่าน)
KV_AUTO = "purchase_tab_auto"      # {"on": bool} · ไม่มี = เปิด


def col_letter(i):
    s, i = "", i + 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def col_ranges(cols):
    """[0,1,2,5,6] → [(0,2),(5,6)] — รวมคอลัมน์ติดกันเป็นช่วงเดียว (ยิง API น้อยลง)"""
    out = []
    for c in sorted(set(cols)):
        if out and out[-1][1] == c - 1:
            out[-1][1] = c
        else:
            out.append([c, c])
    return [tuple(x) for x in out]


def retitle(text, src, dst):
    """แก้ชื่อเดือน/ปีในข้อความแถว 1 จากเดือนต้นแบบ → เดือนใหม่ (src/dst = (ปี ค.ศ., เดือน))"""
    from .constants import MONTHS_FULL
    if not isinstance(text, str) or not text or text.startswith("="):
        return text
    sy, sm = src
    dy, dm = dst
    s_name, d_name = MONTHS_FULL[sm - 1], MONTHS_FULL[dm - 1]
    s_y2, d_y2 = "%02d" % ((sy + 543) % 100), "%02d" % ((dy + 543) % 100)
    out = text.replace(s_name + s_y2, d_name + d_y2)          # "ตุลาคม69" (แบบที่ใช้ในชื่อแท็บ)
    out = re.sub(re.escape(s_name) + r"(\s*)" + str(sy), lambda m: d_name + m.group(1) + str(dy), out)
    out = out.replace(s_name, d_name)                         # ชื่อเดือนเดี่ยวๆ ที่เหลือ
    return out


class _Api:
    """ห่อ Sheets API (ขอบระบบ = requests) — เทสต์ปลอมที่ requests ไม่ใช่ที่คลาสนี้"""

    def __init__(self):
        from google.auth.transport.requests import Request as AuthRequest

        from .fetch_dashboard import PURCHASE_SID
        from .google_sheets import SHEETS_API, _get_credentials
        creds = _get_credentials()
        creds.refresh(AuthRequest())
        self.h = {"Authorization": "Bearer %s" % creds.token}
        self.base = "%s/%s" % (SHEETS_API, PURCHASE_SID)

    def _ok(self, r, what):
        if r.status_code != 200:
            raise RuntimeError("%s: HTTP %s %s" % (what, r.status_code, r.text[:200]))
        return r.json()

    def tabs(self):
        j = self._ok(requests.get(self.base, params={"fields": "sheets.properties(sheetId,title,index)"},
                                  headers=self.h, timeout=30), "อ่านรายชื่อแท็บ")
        return {s["properties"]["title"]: s["properties"] for s in j.get("sheets", [])}

    def get(self, rng, render="FORMATTED_VALUE"):
        url = "%s/values/%s" % (self.base, urllib.parse.quote(rng))
        return self._ok(requests.get(url, params={"valueRenderOption": render},
                                     headers=self.h, timeout=60), "อ่าน " + rng).get("values", [])

    def batch(self, requests_list, what):
        return self._ok(requests.post(self.base + ":batchUpdate", json={"requests": requests_list},
                                      headers=self.h, timeout=60), what)

    def clear(self, ranges):
        return self._ok(requests.post(self.base + "/values:batchClear", json={"ranges": ranges},
                                      headers=self.h, timeout=60), "ล้างข้อมูล")

    def put_cells(self, cells):
        """เขียนทีละเซลล์ที่ระบุ ({"'แท็บ'!A1": "ข้อความ"}) — RAW = ข้อความล้วน ไม่ตีเป็นสูตร"""
        data = [{"range": rng, "values": [[val]]} for rng, val in cells.items()]
        return self._ok(requests.post(self.base + "/values:batchUpdate",
                                      json={"valueInputOption": "RAW", "data": data},
                                      headers=self.h, timeout=60), "แก้ชื่อเดือนแถว 1")


def find_source(titles, year, month):
    """แท็บต้นแบบ = เดือนล่าสุดก่อนเดือนเป้าหมายที่มีอยู่จริง (ถอยได้ LOOK_BACK เดือน)"""
    y, m = year, month
    for _ in range(LOOK_BACK):
        y, m = prev_month(y, m)
        if tab_name(y, m) in titles:
            return (y, m)
    return None


def ensure_tab(year, month, apply=False, api=None):
    """ให้มีแท็บของ (ปี ค.ศ., เดือน) — คืน dict บอกว่าทำอะไร/จะทำอะไร

    apply=False = ดูเฉยๆ (อ่านอย่างเดียว ไม่เขียนอะไรลงชีต)
    """
    api = api or _Api()
    target = tab_name(year, month)
    titles = api.tabs()
    res = {"target": target, "exists": target in titles, "apply": apply}
    if res["exists"]:
        res["action"] = "มีอยู่แล้ว — ไม่ทำอะไร"
        return res

    src = find_source(titles, year, month)
    if not src:
        res["action"] = "ไม่มีแท็บต้นแบบย้อนหลัง %d เดือน — สร้างไม่ได้" % LOOK_BACK
        res["error"] = res["action"]
        return res
    src_title = tab_name(*src)
    src_props = titles[src_title]
    res["source"] = src_title

    # ── ดูว่าคอลัมน์ไหนมีสูตร (อ่านจากต้นแบบ = ตัวเดียวกับที่จะถูกทำสำเนา) ──
    last_col = col_letter(max(CLEAR_COLS))
    rows = api.get("'%s'!A%d:%s%d" % (src_title, FIRST_DATA_ROW, last_col, MAX_ROW), render="FORMULA")
    # "คอลัมน์สูตร" = สูตรเป็นส่วนใหญ่ของเซลล์ที่มีค่า (≥ครึ่ง) → เก็บไว้
    #   ห้ามนับแค่ "มีสูตรสักเซลล์" — เคสเดือนก่อนที่บังเอิญมีสูตรเซลล์เดียวจะทำให้ทั้งคอลัมน์ไม่ถูกล้าง
    #   แล้วข้อมูลเดือนก่อนค้างในแท็บใหม่ (n8n หาแถวท้ายจาก A–S จะไปต่อท้ายข้อมูลเก่า)
    n_val, n_fx = {}, {}
    for row in rows:
        for ci, v in enumerate(row):
            if str(v).strip():
                n_val[ci] = n_val.get(ci, 0) + 1
                if isinstance(v, str) and v.startswith("="):
                    n_fx[ci] = n_fx.get(ci, 0) + 1
    formula_cols = sorted(c for c in n_fx if n_fx[c] * 2 >= n_val[c])
    clear = [c for c in CLEAR_COLS if c not in formula_cols]
    res["keepFormulaCols"] = [col_letter(c) for c in formula_cols if c in CLEAR_COLS]
    res["clearRanges"] = ["%s%d:%s%d" % (col_letter(a), FIRST_DATA_ROW, col_letter(b), MAX_ROW)
                          for a, b in col_ranges(clear)]

    head = api.get("'%s'!A1:%s1" % (src_title, col_letter(60)), render="FORMULA")
    head = head[0] if head else []
    titles_new = [retitle(v, src, (year, month)) for v in head]
    res["row1"] = {col_letter(i): [head[i], titles_new[i]] for i in range(len(head))
                   if head[i] != titles_new[i]}

    if not apply:
        res["action"] = "จะทำสำเนาจาก %s (ยังไม่ได้ทำ — ใส่ --apply)" % src_title
        return res

    # ── 1) ทำสำเนา → แท็บใหม่วางต่อจากต้นแบบ ──
    j = api.batch([{"duplicateSheet": {
        "sourceSheetId": src_props["sheetId"],
        "insertSheetIndex": int(src_props.get("index", 0)) + 1,
        "newSheetName": target,
    }}], "ทำสำเนาแท็บ")
    new_id = j["replies"][0]["duplicateSheet"]["properties"]["sheetId"]
    res["sheetId"] = new_id

    # ── 2) ล้างข้อมูลในแท็บใหม่ · ล้มเมื่อไหร่ = ลบแท็บใหม่ทิ้ง ──
    try:
        if res["clearRanges"]:
            api.clear(["'%s'!%s" % (target, r) for r in res["clearRanges"]])
        # ตรวจซ้ำว่าล้างหมดจริง (กันกรณี API ตอบ 200 แต่ชื่อแท็บมีอักขระพิเศษจนล้างผิดที่)
        left = api.get("'%s'!C%d:C%d" % (target, FIRST_DATA_ROW, MAX_ROW))
        if any(r and str(r[0]).strip() for r in left):
            raise RuntimeError("ล้างแล้วคอลัมน์ C ยังมีรหัสเคสค้างอยู่")
    except Exception as e:
        try:
            api.batch([{"deleteSheet": {"sheetId": new_id}}], "ลบแท็บที่ล้างไม่สำเร็จ")
            res["rolledBack"] = True
        except Exception as e2:
            res["rolledBack"] = False
            res["rollbackError"] = str(e2)[:200]
        res["error"] = "ล้างข้อมูลแท็บใหม่ไม่สำเร็จ: %s" % str(e)[:200]
        res["action"] = "ล้มเหลว"
        return res

    # ── 3) แก้ชื่อเดือนแถว 1 — เขียนเฉพาะเซลล์ที่เปลี่ยน (เซลล์สูตรไม่ถูกแตะ) ·
    #       ล้มได้ ไม่ต้องลบแท็บ (เป็นแค่ป้าย) ──
    if res["row1"]:
        try:
            api.put_cells({"'%s'!%s1" % (target, c): pair[1] for c, pair in res["row1"].items()})
        except Exception as e:
            res["row1Error"] = str(e)[:200]

    res["action"] = "สร้างแล้วจาก %s" % src_title
    res["ok"] = True
    return res


def auto_on():
    try:
        from .cache_store import get_kv
        raw = get_kv(KV_AUTO) or {}
        d = raw.get("data", raw) if isinstance(raw, dict) else {}
        return bool(d.get("on", True)) if isinstance(d, dict) else True
    except Exception:
        return True


def maybe_prepare(now):
    """เรียกจาก `cron_tick` — เช็ควันละครั้ง:
      - ทุกวัน: แท็บ **เดือนนี้** ต้องมี (กันกรณีรอบก่อนล้ม/ไม่ได้ deploy ทันวันที่ 25)
      - ตั้งแต่วันที่ PREPARE_FROM_DAY: แท็บ **เดือนหน้า** ต้องมี
    คืน '' เมื่อทำไปแล้ววันนี้ / ปิดอยู่
    """
    from .cache_store import get_kv, set_kv
    if not auto_on():
        return ""
    today = now.date().isoformat()
    try:
        raw = get_kv(KV_LAST) or {}
        last = raw.get("data", raw) if isinstance(raw, dict) else {}
        if isinstance(last, dict) and last.get("date") == today and last.get("ok"):
            return ""
        # ล้มแล้ววันนี้ = ลองใหม่ได้อีกครั้งหลัง 1 ชม. (ไม่ยิงทุกนาที)
        if isinstance(last, dict) and last.get("date") == today and not last.get("ok"):
            from datetime import datetime
            try:
                if (now - datetime.fromisoformat(last.get("at"))).total_seconds() < 3600:
                    return ""
            except Exception:
                pass
    except Exception:
        pass

    targets = [(now.year, now.month)]
    if now.day >= PREPARE_FROM_DAY:
        targets.append((now.year + 1, 1) if now.month == 12 else (now.year, now.month + 1))

    state = {"date": today, "at": now.isoformat(), "ok": True, "results": []}
    try:
        api = _Api()
        for y, m in targets:
            r = ensure_tab(y, m, apply=True, api=api)
            state["results"].append({k: r.get(k) for k in
                                     ("target", "exists", "action", "source", "error", "rolledBack")})
            if r.get("error"):
                state["ok"] = False
    except Exception as e:
        state["ok"] = False
        state["error"] = str(e)[:200]

    created = [x for x in state["results"] if not x.get("exists") and not x.get("error")]
    if created or not state["ok"]:
        try:
            from . import eventlog
            eventlog.log(eventlog.CRON, name="เตรียมแท็บชีตจัดซื้อเดือนใหม่", ok=state["ok"],
                         results=state["results"], error=state.get("error", ""))
        except Exception:
            pass
    try:
        set_kv(KV_LAST, state)
    except Exception:
        pass
    if not state["ok"]:
        return "error"
    return "created:" + ",".join(x["target"] for x in created) if created else "ok"
