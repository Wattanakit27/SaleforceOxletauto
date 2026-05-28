"""สร้าง/รีเซ็ต tab 'เกณฑ์คะแนน lead' ใน spreadsheet employees พร้อม default values.

รัน 1 ครั้ง:
    python scripts/init_lead_score_config.py

ถ้า tab มีอยู่แล้ว → จะเขียนทับด้วย default (ระวัง! ถ้า admin แก้ไว้แล้วจะหาย)
"""
import os, sys, django
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
django.setup()

from dashboard.services.google_sheets import write_sheet, ensure_sheet_tab, SHEET_CONFIG

# ── Default config: ชื่อเกณฑ์ | หมวด | คะแนน | เปิดใช้ | หมายเหตุ ──
# คะแนนสามารถปรับได้ผ่าน sheet โดยตรง — ระบบจะอ่านมาใช้คำนวณ Lead Score
DEFAULT_ROWS = [
    # หัวตาราง
    ["ชื่อเกณฑ์", "หมวด", "คะแนน", "เปิดใช้", "หมายเหตุ"],

    # ── ความใหม่ของ lead (Freshness) ──
    ["Lead ใหม่ (≤3 วัน)",          "freshness", 20,  "TRUE",  "เร่งติดต่อ — speed-to-lead สำคัญที่สุด"],
    ["Lead ปานกลาง (4-7 วัน)",      "freshness", 10,  "TRUE",  "ยังตามทัน"],
    ["Lead เก่า (8-14 วัน)",        "freshness", 0,   "TRUE",  "neutral"],
    ["Lead เย็น (>14 วัน)",         "freshness", -5,  "TRUE",  "priority ต่ำ"],

    # ── ประเภท lead (Quality) ──
    ["ประเภท: Normal",              "type",      50,  "TRUE",  "lead คุณภาพมาตรฐาน"],
    ["ประเภท: Hot RB",              "type",      30,  "TRUE",  "lead ร้อน แต่ rebooking"],
    ["ประเภท: Hot RJ",              "type",      25,  "TRUE",  "lead ร้อน RJ"],
    ["ประเภท: RJ",                  "type",      15,  "TRUE",  "คุณภาพต่ำสุด — ปิดยาก"],

    # ── รถ (Car) ──
    ["รุ่นรถยอดนิยม (top 20)",       "car",       20,  "TRUE",  "demand สูง closing ง่าย"],
    ["ราคารถสูง (≥500,000)",        "car",       10,  "TRUE",  "margin ดี"],
    ["ราคารถปานกลาง (200-500k)",    "car",       5,   "TRUE",  ""],

    # ── ประวัติ (History) ──
    ["เคยจองแล้วยกเลิก",            "history",   -5,  "TRUE",  "อาจกลับมาได้ — ไม่ลบเยอะ"],
    ["เคยจอง+ปล่อยสำเร็จ",          "history",   -10, "TRUE",  "ซื้อแล้ว priority ต่ำ"],

    # ── Channel ──
    ["มาจาก Facebook Ads",          "channel",   5,   "TRUE",  ""],
    ["มาจาก TikTok / ไลฟ์สด",       "channel",   10,  "TRUE",  "engagement สูงกว่า"],
    ["มาจาก Walk-in / โทรมา",       "channel",   15,  "TRUE",  "intent ชัดเจน"],

    # ── Engagement (ลูกค้าตอบกลับ) ──
    ["ลูกค้าตอบไลน์/โทรกลับ",        "engagement", 25, "TRUE",  "intent สูง"],
    ["ลูกค้าทักก่อน (inbox)",        "engagement", 15, "TRUE",  ""],
    ["โทรไม่รับเกิน 3 ครั้ง",        "engagement", -10, "TRUE", "ลด priority"],
]


def main():
    print("=== สร้าง tab 'เกณฑ์คะแนน lead' ===")
    cfg = SHEET_CONFIG["lead_score_config"]
    print(f"  Spreadsheet: {cfg['spreadsheet_id']}")
    print(f"  Tab name   : {cfg['sheet_name']}")

    # ensure tab exists (no-op if already created)
    ensure_sheet_tab(cfg["spreadsheet_id"], cfg["sheet_name"])
    print(f"  ✓ Tab พร้อมใช้งาน")

    # write default values
    write_sheet("lead_score_config", DEFAULT_ROWS)
    print(f"  ✓ เขียน {len(DEFAULT_ROWS)-1} เกณฑ์ลง sheet")

    print(f"\nเสร็จแล้ว — เปิดดูที่:")
    print(f"  https://docs.google.com/spreadsheets/d/{cfg['spreadsheet_id']}/edit")
    print(f"\nหมายเหตุ: admin สามารถแก้คะแนนใน sheet ได้ตลอด")
    print(f"          ระบบจะอ่านค่าใหม่ทุก 60 วินาที (cache TTL)")


if __name__ == "__main__":
    main()
