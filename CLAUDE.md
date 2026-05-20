# CLAUDE.md

แนะนำ Claude เกี่ยวกับโปรเจกต์นี้ — Oxlet Sales Dashboard (Django port จาก Next.js เดิม)

## ภาพรวม

Django web app แสดง dashboard ยอดขาย/ลีด/ไลฟ์ ของทีมเซลล์ Oxlet ดึงข้อมูลทั้งหมดจาก
**Google Sheets** (ไม่มี local DB — `DATABASES = {}` ใน [oxlet/settings.py](oxlet/settings.py))
UI เป็น Thai-language, timezone Asia/Bangkok

## Stack

- **Backend**: Django 4.2+ ([requirements.txt](requirements.txt))
- **Data source**: Google Sheets API v4 (service account credentials ผ่าน env)
- **Frontend**: Server-rendered template + vanilla JS (no React/Vue, no build step)
- **Auth**: Magic link / per-seller token (ไม่มี Django user model)

## โครงสร้างไฟล์

```
manage.py
oxlet/
  settings.py          # config, env vars, Google Sheets creds
  urls.py              # include dashboard.urls
dashboard/
  urls.py              # routes: /, /dashboard, /api/*, /u/<token>, /s/<token>
  views.py             # มี 5 views: index, dashboard_page, api_dashboard, api_auth, magic_link, seller_dashboard
  services/
    constants.py       # TEAMS, TARGETS, SELLER_MAP, STATUS_COLOR ฯลฯ
    seller_tokens.py   # token 6-10 หลักของเซลล์แต่ละคน → ใช้กับ /s/<token>/
    google_sheets.py   # auth + fetch (SHEET_CONFIG, *_COL classes สำหรับ column index)
    fetch_dashboard.py # main aggregator: รวมข้อมูล 6 sheets → dict สำหรับ template
    helpers.py         # pct/nc/urg/dots_html ฯลฯ
  templates/dashboard/
    index.html         # หน้า dashboard หลัก (admin เห็นทั้งหมด, เซลล์เห็นเฉพาะตัวเอง)
    magic_link.html    # /u/<token>/ — set cookie แล้ว redirect ไป /dashboard/
    seller.html        # /s/<token>/ — หน้าส่วนตัวของเซลล์ พร้อม section "ต้องโทร"
  static/dashboard/    # CSS + JS (ถ้ามี)
  templatetags/
```

## รันโปรเจกต์

```powershell
# Setup env (ครั้งแรก)
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# ต้องมี .env ที่มี GOOGLE_SERVICE_ACCOUNT_EMAIL + GOOGLE_PRIVATE_KEY
# (private key คั่นบรรทัดด้วย \n หรือใส่ multiline ในเครื่องหมายคำพูด)

python manage.py runserver
```

ไม่ต้องรัน `migrate` — ไม่มี local DB

## URL Routes

| URL | View | ใครเข้าได้ |
|---|---|---|
| `/` | `index` | redirect → `/dashboard/` |
| `/dashboard/` | `dashboard_page` | ทุกคน (filter ด้วย cookie `oxlet_employee`) |
| `/api/dashboard` | `api_dashboard` | JSON ของ full dashboard data |
| `/api/auth?token=` | `api_auth` | ตรวจ token กับ employees sheet → คืน user info |
| `/u/<token>/` | `magic_link` | เข้าสู่ระบบผ่าน magic link (token = user_id จาก employees sheet) |
| `/s/<token>/` | `seller_dashboard` | หน้าส่วนตัวของเซลล์ (token จาก `SELLER_TOKENS`) |

**ความแตกต่างของ `/u/` vs `/s/`**:
- `/u/<token>/` — token มาจาก employees Google Sheet, ใช้ set cookie แล้ว redirect ไปหน้า dashboard เต็ม
- `/s/<token>/` — token hardcode ใน [seller_tokens.py](dashboard/services/seller_tokens.py), แสดงหน้าส่วนตัวแบบ focused (call helper) ไม่ set cookie

## Concepts สำคัญ

### Sellers & Teams
นิยามใน [constants.py](dashboard/services/constants.py):
- ทีม A: โอ๊ต, เฟิร์ส, เจ, บอย, นั่ม, กอล์ฟ
- ทีม B: นวล, เก้า, มด, มัท, อุ้ม, แซน
- ทีม C: ใบตอง
- `TARGETS` = เป้าจำนวนคันต่อเดือนของแต่ละคน
- `SELLER_MAP` = normalize ชื่อที่สะกดต่างกัน (เช่น "เจเจ"→"เจ", "กลอฟ"→"กอล์ฟ")
- **ใช้ `normalize_seller()` เสมอ** ก่อนเปรียบเทียบชื่อเซลล์จาก sheet

### Lead Status
- **Follow** (ต้องติดตาม): admin_status มีคำว่า "ติดตาม", "รอตอบ", "รอลูกค้า", "โทรไม่รับ", "ผิดนัด"
- **Vacant** (ว่าง): admin_status ว่างหรือเป็น "-"
- **RJ types**: "RJ", "Hot RJ", "Hot RB" — แยกออกจาก lead ปกติในสถิติ

### Update Count & "ต้องโทร"
- `UPD_TGT = 4` — เป้าจำนวนครั้งที่ต้องอัปเดตต่อ lead 1 ราย
- `nc(u) = max(0, UPD_TGT - u)` — เหลืออีกกี่ครั้งให้ครบ
- `urg(u)` — urgency score (100 ถ้ายังไม่โทรเลย, +10 ต่อครั้งที่ขาด)
- หน้า [/s/<token>/](dashboard/templates/dashboard/seller.html) ใช้ค่านี้ flag `mustCall`

### Date parsing
[fetch_dashboard.py](dashboard/services/fetch_dashboard.py) มี `parse_date()` รองรับ:
- Excel serial date (เลข 4-5 หลัก)
- "d/m/yy" หรือ "d/m/yyyy" (รองรับ พ.ศ. แปลงเป็น ค.ศ. ถ้า year > 2500)
- fallback dateutil

## Google Sheets

6 sheets ใน [SHEET_CONFIG](dashboard/services/google_sheets.py#L12):
1. **leads** — รายการ lead ทั้งหมด (column map: `LEADS_COL`)
2. **sales_reports** — รายงานยอดขาย/สถานะการจอง (`SALES_COL`)
3. **bookings** — รายการจอง (`BOOKINGS_COL`)
4. **live_sessions** — เซสชั่นไลฟ์ (`LIVE_COL`)
5. **live_followups** — คลิป follow-up ของไลฟ์ (`FOLLOWUP_COL`)
6. **employees** — ข้อมูลพนักงาน + user_id สำหรับ magic link (`EMPLOYEE_COL`)

**Column index hardcode** เป็น 0-based ใน class attributes — ถ้า sheet ขยับ column ต้องอัปเดตที่นี่

`cell(row, idx)` คืน string, `cell_num(row, idx)` คืน float (parse จาก string ที่มี comma) — ดู [google_sheets.py](dashboard/services/google_sheets.py)

## Conventions

- **ไม่มี Django models / migrations** — อย่าเพิ่มโดยไม่ปรึกษา (โปรเจกต์ตั้งใจไม่มี DB)
- **ไม่ใช้ Django auth** — auth ทำผ่าน cookie `oxlet_employee` (JSON ใน client) หรือ token ใน URL
- **Frontend = template + vanilla JS** — อย่าใส่ React/build pipeline เว้นแต่ user สั่ง
- **ใช้ Thai สำหรับ user-facing text** (label, ข้อความ error) แต่ code/comment สั้นๆ ใช้ Eng ก็ได้
- **Timezone**: ใช้ `bangkok_now()` จาก helpers/fetch_dashboard เสมอ ไม่ใช้ `datetime.now()` ดิบ
- **Normalize seller name**: ใช้ `normalize_seller()` ทุกครั้งที่อ่านชื่อจาก sheet

## งานที่เจอบ่อย

### เพิ่ม/รีโทเทต token ของเซลล์
แก้แค่ [dashboard/services/seller_tokens.py](dashboard/services/seller_tokens.py) — ไม่ต้อง migrate

### เพิ่ม column ใหม่ใน sheet
1. อัปเดต column index class ใน [google_sheets.py](dashboard/services/google_sheets.py)
2. ใช้ใน [fetch_dashboard.py](dashboard/services/fetch_dashboard.py)
3. ถ้าจะแสดง — แก้ template

### เพิ่มเซลล์ใหม่
1. เพิ่มชื่อใน `TEAMS` + `TARGETS` ที่ [constants.py](dashboard/services/constants.py)
2. เพิ่ม token ใน [seller_tokens.py](dashboard/services/seller_tokens.py)
3. (ถ้าจำเป็น) เพิ่ม alias ใน `SELLER_MAP`

### Debug ข้อมูลผิด
- `/api/dashboard` คืน JSON เต็มของ aggregator → ดูค่าได้ทุกชั้น
- เช็คว่า `normalize_seller()` ครอบคลุมการสะกดในชีตหรือยัง
- เช็ค Excel serial date vs "d/m/yy" — `parse_date()` จัดการทั้งคู่
