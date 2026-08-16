"""
carspend — ดึงข้อมูลรถสดจากเว็บ Car Spend (autosoftware.co.th/oxletauto) ผ่าน HTTP

ใช้แทนการ export zip มือ — คืน dict รูปร่างเดียวกับ cars.json ใน zip
เพื่อให้ management command ใช้ helper/mapping ชุดเดียวกับ import_cars ได้เลย

โครงเว็บ (สำรวจ 16 ส.ค. 2569):
  POST /oxletauto/core/takelogin.core.php          -> login (cookie session)
  GET  /oxletauto/dashboard/?p=cars&sts=&pg=N      -> หน้า list: key (md5) + สถานะ · หน้าละ 100 คัน
  GET  /oxletauto/dashboard/?p=car_detail&key=<md5> -> หน้า detail: ข้อมูลครบ + อัลบัมรูป

ข้อควรรู้:
- เว็บอยู่หลัง Cloudflare และหน่วง client ที่ส่ง header น้อยอย่างหนัก (~90 วิ/หน้า จนโดนตัดสาย)
  ต้องส่ง header ชุดเต็มแบบ Chrome ถึงจะได้ ~0.8 วิ/หน้า · ห้ามใส่ br ใน Accept-Encoding
  (requests ถอด brotli ไม่ได้ จะได้ข้อความเละ)
- "รถขายแล้ว" ไม่อยู่ในรายการปกติ ต้องใส่ sts ของสถานะนั้น (ดู STATUS_FILTER)
- รูปเปิดสาธารณะ ดึงได้โดยไม่ต้องล็อกอิน
"""
from __future__ import annotations

import logging
import re
import time

import requests
from bs4 import BeautifulSoup

BASE = "https://www.autosoftware.co.th/oxletauto"
LOGIN_URL = f"{BASE}/core/takelogin.core.php"
DASH = f"{BASE}/dashboard/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate",
    "Sec-Ch-Ua": '"Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Connection": "keep-alive",
    "Referer": f"{DASH}?p=cars",
}

# ตัวกรองสถานะ (พารามิเตอร์ sts=) — "" = สต็อกปัจจุบัน (ไม่รวมรถขายแล้ว)
STATUS_FILTER = {
    "stock": "",
    "sold": "f8895f347b4bf9185d34118b9d853d23",
    "booked": "7d86d047fd45a99827218bcdcda2cc3c",
    "finance": "1636c14758153af1e03f7284fa4df7e4",
    "ready": "b4072e896a230ca463d407471098085c",
    "closing": "6bac5a6f0f5c0dbb2f531030e379c624",
    "repair": "8706f73455d2f118a18f285aa6105bea",
}

_KEY_RE = re.compile(r"key=([a-f0-9]{32})")

log = logging.getLogger(__name__)


def _norm(s):
    """ยุบ whitespace ทุกชนิด (รวม &nbsp;) ให้เหลือช่องว่างเดียว"""
    if not s:
        return ""
    return re.sub(r"\s+", " ", str(s).replace("\xa0", " ")).strip()


class CarSpendError(RuntimeError):
    pass


class CarSpend:
    """client อ่านอย่างเดียว — ไม่มีการเขียนกลับไปที่เว็บต้นทาง"""

    def __init__(self, username, password, delay=0.3, timeout=30):
        if not username or not password:
            raise CarSpendError("ต้องมี username/password (ตั้ง CARSPEND_USER / CARSPEND_PASS)")
        self.delay = delay
        self.timeout = timeout
        self.s = requests.Session()
        self.s.headers.update(HEADERS)
        self._login(username, password)

    # ------------------------------------------------------------ http

    def _get(self, url, tries=3):
        for attempt in range(tries):
            try:
                r = self.s.get(url, timeout=self.timeout)
                r.raise_for_status()
                return r
            except requests.RequestException as e:
                if attempt == tries - 1:
                    raise
                log.warning("GET ล้มเหลว retry %d/%d (%s): %s", attempt + 1, tries - 1, url, e)
                time.sleep(2 * (attempt + 1))

    def _soup(self, url):
        html = self._get(url).text
        time.sleep(self.delay)
        return BeautifulSoup(html, "html.parser")

    def _login(self, username, password):
        self._get(f"{BASE}/")
        r = self.s.post(
            LOGIN_URL,
            data={"username": username, "password": password, "login": "Login"},
            timeout=self.timeout,
        )
        r.raise_for_status()
        if "ออกจากระบบ" not in self._get(DASH).text:
            raise CarSpendError("ล็อกอินไม่ผ่าน — ตรวจ CARSPEND_USER / CARSPEND_PASS")
        log.info("carspend: ล็อกอินสำเร็จ")

    # ------------------------------------------- หน้าที่ 1: list -> keys

    def iter_keys(self, sts="", max_pages=100):
        """yield (key, สถานะ) จากหน้า list — ไล่ pg=1,2,3,... จนหมด"""
        seen = set()
        for pg in range(1, max_pages + 1):
            soup = self._soup(f"{DASH}?p=cars&sts={sts}&type=&search=&pg={pg}")
            found = 0
            for tr in soup.select("tbody tr"):
                a = tr.find("a", href=_KEY_RE)
                if not a:
                    continue
                key = _KEY_RE.search(a["href"]).group(1)
                found += 1
                if key in seen:
                    continue
                seen.add(key)
                cells = tr.find_all("td")
                yield key, (_norm(cells[1].get_text()) if len(cells) > 1 else "")
            log.info("carspend: หน้า %d เจอ %d คัน (สะสม %d)", pg, found, len(seen))
            if not found:
                break

    # ------------------------------------ หน้าที่ 2: detail -> ข้อมูลรถ

    def fetch_car(self, key, status=""):
        """คืน dict รูปร่างเดียวกับรายการใน cars.json ของ zip export"""
        soup = self._soup(f"{DASH}?p=car_detail&key={key}")

        # ตารางแสดงผล: label ซ้าย -> value ขวา (เก็บครบทุกคู่ ไม่ตกหล่น)
        cells = soup.find_all("td")
        detail = {}
        for i in range(len(cells) - 1):
            label = _norm(cells[i].get_text())
            if label and label not in detail:
                detail[label] = _norm(cells[i + 1].get_text())

        def inp(name):
            el = soup.find(attrs={"name": name})
            return _norm(el.get("value")) if el is not None and el.has_attr("value") else ""

        code = detail.get("รหัสรถ", "")
        if not code:
            return None

        return {
            "key": key,
            "status": status,
            "branch": detail.get("สาขาที่รถอยู่", ""),
            "brand": inp("car_brand") or detail.get("ยี่ห้อ", ""),
            "model": inp("car_face") or detail.get("รุ่นรถ", ""),
            "name": detail.get("ชื่อรถ", ""),
            "price": inp("p_car_price"),
            # ทะเบียนไม่มีในตาราง อยู่ใน input ของฟอร์มแก้ไข (แยกจังหวัดไว้แล้ว)
            "plate": inp("car_reg_number"),
            "province": inp("car_reg_province"),
            "note": detail.get("หมายเหตุ", ""),
            "detail": detail,
            "owner": {
                "หมายเลขทะเบียน": inp("car_reg_number"),
                "จังหวัด": inp("car_reg_province"),
                "ชื่อผู้ครอบครอง": inp("p_car_own"),
                "จำนวนผู้ครอบครอง": inp("p_car_own_count"),
            },
            "image_urls": self._parse_images(soup),
        }

    @staticmethod
    def _parse_images(soup):
        """
        อัลบัมรูปอยู่ใน <a class="thumbnail" data-image="...">
        รูปแรก = รูปปก (เว็บโชว์ซ้ำอีกรอบด้านบน จึงต้อง dedupe โดยคงลำดับเดิม)
        คืน [{"file","full","thumb"}] · full ~1280x960 ~260KB · thumb ~27KB
        """
        out, seen = [], set()
        for a in soup.select("a.thumbnail[data-image]"):
            url = _norm(a["data-image"])
            if "/resource/cars/" not in url:
                continue
            fn = url.rsplit("/", 1)[-1]
            if not fn or fn in seen:
                continue
            seen.add(fn)
            out.append({
                "file": fn,
                "full": f"{BASE}/resource/cars/images/{fn}",
                "thumb": f"{BASE}/resource/cars/thumbs/{fn}",
            })
        return out

    # ------------------------------------------------------------ รวม

    def iter_cars(self, sts="", limit=0):
        """yield dict ของรถทีละคัน (streaming — ไม่กองในหน่วยความจำ)"""
        n = 0
        for key, status in self.iter_keys(sts):
            if limit and n >= limit:
                return
            car = self.fetch_car(key, status)
            if car:
                n += 1
                yield car

    def download(self, url, max_bytes=8 * 1024 * 1024):
        """โหลดไฟล์รูป (เปิดสาธารณะ ไม่ต้องใช้ session แต่ใช้ร่วมได้)"""
        r = self._get(url)
        return r.content[:max_bytes]
