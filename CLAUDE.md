# CLAUDE.md

แนะนำ Claude เกี่ยวกับโปรเจกต์นี้ — Oxlet Sales Dashboard (Django port จาก Next.js เดิม)

## ภาพรวม

Django web app แสดง dashboard ยอดขาย/ลีด/ไลฟ์ ของทีมเซลล์ Oxlet ดึงข้อมูลทั้งหมดจาก
**Google Sheets** (ไม่มี local DB — `DATABASES = {}` ใน [oxlet/settings.py](oxlet/settings.py))
UI เป็น Thai-language, timezone Asia/Bangkok

**Deploy: Vercel** (`@vercel/python` builder via [vercel.json](vercel.json))

## Stack

- **Backend**: Django 4.2+ ([requirements.txt](requirements.txt))
- **Data source**: Google Sheets API v4 (service account, **read+write** scope)
- **Frontend**: Server-rendered template + vanilla JS + Chart.js (CDN) — no build step
- **Auth**: Django signed-cookie session (admin) + magic link / per-seller token (sellers)
- **Static**: WhiteNoise (in-Django static serving) + `WHITENOISE_USE_FINDERS=True` (no `collectstatic` needed)
- **LINE Messaging API**: push Flex messages via env-stored Channel Access Token
- **Cron**: External scheduler (cron-job.org) ยิงเข้า `/api/cron/tick` ทุก 1 นาที

## โครงสร้างไฟล์

```
manage.py
vercel.json              # Vercel build + cron config
.env                     # secrets (committed in private repo)
oxlet/
  settings.py            # config, env vars, ALLOWED_HOSTS, WhiteNoise, session
  urls.py
  wsgi.py                # Vercel python entry point
dashboard/
  urls.py                # ดู URL routes ด้านล่าง
  views.py               # views — dashboard, login, admin tools, cron endpoints
  services/
    constants.py         # TEAMS, TARGETS (dynamic ผ่าน refresh_from_sheet)
    seller_tokens.py     # token /s/<token>/ ของเซลล์แต่ละคน
    google_sheets.py     # auth + read + write helpers (ensure_sheet_tab, write_sheet)
    fetch_dashboard.py   # main aggregator: รวมข้อมูล 7 sheets → dict สำหรับ template
    line_notify.py       # Flex builder + push + schedule loader
    helpers.py
  templates/dashboard/
    index.html           # หน้า dashboard หลัก (admin / ผู้บริหาร เห็นทั้งหมด, อื่นๆ เห็นเฉพาะตัวเอง)
    login.html           # /login/ — admin login (user+password)
    magic_link.html      # /u/<token>/ — set cookie แล้ว redirect ไป /dashboard/
    seller.html          # /s/<token>/ — หน้าส่วนตัวของเซลล์ (filter+charts+KPI+lead detail modal)
  static/dashboard/      # CSS + image (โลโก้บริษัท)
```

## รันโปรเจกต์ (Dev)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py runserver
```

ไม่ต้องรัน `migrate` — ไม่มี local DB. Session ใช้ signed-cookie backend

## URL Routes

### หน้าเว็บ

| URL | View | สิทธิ์ |
|---|---|---|
| `/` | `index` | redirect → `/dashboard/` |
| `/dashboard/` | `dashboard_page` | เปิดสาธารณะ — default = ผู้บริหาร, login admin ผ่านปุ่ม 🔐 |
| `/login/` | `login_view` | GET = form, POST = ตรวจรหัส (user `admin` / pass จาก env) |
| `/logout/` | `logout_view` | clear session → กลับ /dashboard/ |
| `/u/<token>/` | `magic_link` | login เซลล์ผ่าน LINE user_id (จาก employees sheet) |
| `/s/<token>/` | `seller_dashboard` | หน้าส่วนตัวของเซลล์ — token จาก [seller_tokens.py](dashboard/services/seller_tokens.py) |

### API

| URL | View | ใช้ทำอะไร |
|---|---|---|
| `/api/dashboard` | `api_dashboard` | JSON ของ full dashboard data |
| `/api/auth?token=` | `api_auth` | ตรวจ LINE user_id กับ employees sheet |
| `/api/admin/send_line` | `admin_send_line` | admin: GET=preview, POST=ส่ง Flex ทันที |
| `/api/admin/seller_config` | `admin_seller_config` | admin: GET=อ่าน config, POST=บันทึก (เขียน sheet "ตั้งค่าเซลล์") |
| `/api/admin/schedule_config` | `admin_schedule_config` | admin: GET=อ่านตาราง, POST=บันทึก (เขียน sheet "ตั้งเวลาส่ง") |
| `/api/admin/diagnostics` | `admin_diagnostics` | admin: ตรวจ log การกรองข้อมูล (เคสที่หาย, วันที่พัง, สถานะว่าง, "รอปล่อย" cases) |
| `/api/admin/sheets_status` | `admin_sheets_status` | admin: เช็คสด 6 แหล่งข้อมูล + tab รายเดือน + sheet ตั้งค่า (panel "📊 แหล่งข้อมูล" แบบ n8n) |
| `/api/admin/sheet_config` | `admin_sheet_config` | admin POST: ย้าย spreadsheet/tab ของแต่ละแหล่ง (เก็บ Supabase `sheet_config`) — ใช้ตอนขึ้นปีใหม่/ย้ายไฟล์ |
| `/api/seller/update_note` | `update_lead_note` | เซลล์ (token) เขียนกลับ Google Sheet จาก lead detail — รับ `field` (S=`fill_sheet_note` / Z=`customer_status` / N=`call_proof`) + `value` (back-compat: `note`) → header-aware + ตรวจ ownership |
| `/api/cron/send_line` | `cron_send_line` | public (`?secret=xxx`) — ส่ง Flex แบบ one-shot, manual params |
| `/api/cron/tick` | `cron_tick` | public (`?secret=xxx`) — เช็คตาราง schedule + ส่งถ้าถึงเวลา (cron-job.org ยิงทุก 1 นาที) |

## Roles (สิทธิ์ผู้ใช้)

| Role | position | ทำได้ | UI badge |
|------|---------|------|----------|
| **Admin** | `admin` | เห็นทุกอย่าง + 🚗 Lead รถ + 📋 เคสจอง + impersonate + ปุ่ม 📋 LINE ID / 📤 LINE Flex / 🎯 ตั้งเป้า | 👑 Admin (อำพัน) |
| **ผู้บริหาร** | `executive` / `ผู้บริหาร` / `manager` / `exec` | เห็นทุกอย่าง + 🚗 Lead รถ + 📋 เคสจอง + impersonate (ไม่มีเครื่องมือ admin) | 🎩 ผู้บริหาร (ม่วง) |
| **เซลล์** | อื่นๆ | เห็นเฉพาะตัวเอง (ไม่เห็น Analytics tables) | 👤 ชื่อเล่น (น้ำเงิน) |

ใน [index.html](dashboard/templates/dashboard/index.html) ตาราง Lead-by-Car และ Released-Cars ห่อด้วย `if (canViewAll)` — seller ทั่วไป (อ่านจาก `/s/<token>/` หรือ `/u/<token>/`) ไม่เห็น

**Login ทาง 2**:
1. **Admin** — POST `/login/` ด้วย username/password (จาก env `OXLET_ADMIN_USER` / `OXLET_ADMIN_PASSWORD`)
2. **เซลล์** — `/u/<token>/` ที่ token = LINE user_id, หรือ `/s/<token>/` ที่ token จาก seller_tokens.py

## Concepts สำคัญ

### Sellers & Teams (Dynamic)
- **เริ่มต้น (fallback)**: [constants.py](dashboard/services/constants.py) มี `TEAMS` + `TARGETS` hardcode
- **Override (จริง)**: อ่านจาก Google Sheet tab **"ตั้งค่าเซลล์"** (cols: ชื่อเล่น | ทีม | เป้า)
  - `fetch_dashboard_data()` เรียก `refresh_from_sheet()` ทุกครั้ง → mutate TEAMS/TARGETS/ALL_SELLERS/TEAM_ID in-place
  - Sheet ว่าง/error → fallback ใช้ค่า hardcode
- **Admin แก้ในระบบ**: ปุ่ม **🎯 ตั้งเป้า/ทีม** → inline edit table → POST เขียนทับ sheet
- **เพิ่มเซลล์ใหม่**: แค่เพิ่มแถวใน sheet → ระบบ pickup auto (แต่ token ใน [seller_tokens.py](dashboard/services/seller_tokens.py) ต้องเพิ่มเองสำหรับ URL `/s/`)
- **`SELLER_MAP`** = normalize ชื่อสะกดต่าง (เจเจ→เจ, กลอฟ→กอล์ฟ) — ใช้ผ่าน `normalize_seller()` เสมอ

### Source of truth สำหรับนับเคสตามสถานะ
- **"จอง"** → นับจาก **leads sheet** (admin_status หรือ sales_status มีคำว่า "จอง" + ไม่ skipped). ดู `has_booking_status()` ใน [fetch_dashboard.py](dashboard/services/fetch_dashboard.py)
- **"รอเซ็นต์/รอผล/รอปล่อย/ปล่อย/รีเจ็ก"** → นับจาก **sales_reports sheet** (`booking_cases[].status`) — เพราะ admin update ใน "รายงานฝ่ายขาย"
- **bookings sheet (separate spreadsheet) ไม่ใช้แล้ว** — เดิม `year_jongs` มาจาก bookings sheet, ตอนนี้ derive จาก leads. `fetch_all_sheets()` ยัง fetch อยู่ แต่ `raw_bookings` ไม่ถูกใช้ใน aggregator
- frontend (seller.html "🎯 เคสในมือ") — `bookingCount` filter จาก `D.leads` ด้วย logic เดียวกัน

### Lead Status (คอลัม Z "สถานะลูกค้า" — layout ใหม่ มิ.ย.69+)
ตั้งแต่ มิ.ย.69 สถานะหลักของ lead อยู่ที่ **คอลัม Z `customer_status`** (controlled vocab) ใช้คัดลำดับว่าเซลล์ตามเคสไหนก่อน:
- **priority (`CUSTOMER_STATUS_PRIORITY`, สูง→ต่ำ)**: สนใจมาก(8) · ลังเล(7) · ไม่รับสาย(6) · รอเงิน(5) · รอเช็คเครดิต(4) · ดาวน์ไม่พอ(3) · จอง(2) · ส่งมอบ(1)
- **เคสเสีย (`CUSTOMER_STATUS_DEAD`) = "ไม่ต้องตาม"**: ยังไม่ออกเร็วๆนี้ · ติดแบล็คลิส · เครดิตไม่ผ่าน · ลูกค้าไม่สนใจแล้ว · **คืนเคส** (ผู้ใช้กำหนดว่าพวกนี้ในวงเล็บ = เคสเสีย)
- **`should_follow(r)`**: ตามต่อ = active chase เท่านั้น (priority ≥3 = 6 สถานะบน). **จอง/ส่งมอบ = ไม่ remind ให้โทร** (เป็น outcome บวก ไม่ใช่เคสเสีย) · เคสเสีย = ไม่ตาม
- **กลไก fallback**: row-level `should_follow(r)` / `is_lead_vacant(r)` ใช้คอลัม Z ถ้ามีค่า, **ไม่งั้น fallback ไป `is_follow(admin_status)` เดิม** (เดือนเก่า Z ว่าง → ผลเท่าเดิม ไม่ regression). `effective_status(r)` คืน Z ก่อน else admin_status
- **คอลัม U–Y กรอกได้** (canonical 34-38): occupation(U อาชีพ) · income(V รายได้) · job_tenure(W อายุงาน) · payment_history(X ประวัติผ่อน) · customer_type(Y ประเภทลูกค้า) — เซลล์กรอกในหน้า LEAD → เขียนกลับชีต (ประเภทลูกค้า = dropdown preset + เพิ่มเองได้)
- frontend [seller.html](dashboard/templates/dashboard/seller.html): `zVal(l)` + `Z_DEAD` (รวม คืนเคส) — `isSkipped`/`isBooked`/`isInHand`/KPI "ต้องโทรต่อ" ใช้ Z ถ้ามี; lead list default sort = `followPriority` (Z) ก่อน แล้วค่อย urgency. lead detail มีฟอร์มกรอก Z(dropdown)/N(toggle)/S(/-slots)/U-Y → `saveLeadField`/`onSelectField`/`onBlurField`
- **NOTE**: aggregate junk/booking detection (`is_skipped`/`"จอง" in admin/sales`) ยัง**ไม่**ย้ายมา Z (Z เพิ่งเริ่มกรอก) — เมื่อ admin กรอก "จอง" ใน Z เยอะแล้วค่อย migrate booking detection ต่อ
- **ดูเก่า (admin_status/sales_status keyword)**:
- **Follow** (ต้องติดตาม): admin_status / sales_status มีคำว่า "ติดตาม", "รอตอบ", "รอลูกค้า", "โทรไม่รับ", "ผิดนัด", "นัดหมาย" — **และไม่มี** SKIP_STATUS
- **Vacant** (ว่าง): admin_status ว่างหรือ "-"
- **Skipped / Junk** (เคสปิดแล้ว): admin_status หรือ sales_status มีคำว่า "จบ", "ส่งมอบ", "คืนเคส", "คืน", "ยกเลิก", "ไม่สนใจ", "dead", "จ่ายใหม่" — ดู `is_skipped()` ใน [fetch_dashboard.py](dashboard/services/fetch_dashboard.py). Sync กับ `SKIP_STATUS` ใน [line_notify.py](dashboard/services/line_notify.py)
  - **หมายเหตุสำคัญ**: junk เดือนนี้ ~50% ของ leads (คืนเคส 684 / จ่ายใหม่ 335 / ยกเลิก 289). ถ้าตัดออกหมด lead หายไปครึ่งหนึ่ง → ดูภาพรวมไม่ออก. ดังนั้นนโยบายคือ **แสดงเสมอ แค่ไม่เตือนให้โทร**
  - **หน้าเซลล์ `/s/<token>/`** — **เคส junk โผล่ครบ** ใน `my_leads`, lead list, KPI "หลีดที่รับ"/"โทรแล้ว"/"อัพเดท...", chart daily/monthly. **ตัด junk ออกจาก** KPI "ยังไม่โทร" + "ต้องโทรต่อ" + เคสในมือ + banner แจ้งเตือน (frontend ใช้ `SKIP_KEYWORDS` + `isSkipped(l)` check) — เพราะไม่ควร remind ให้โทรเคสที่ admin ปิดแล้ว
  - **หน้า admin/exec `/dashboard/`** — junk อยู่ในตัวเลขรวม. `is_follow()` → exclude จาก KPI "ติดตาม" + `follow_cases` list
  - **LINE Flex แจ้งเตือน** — `build_seller_pipelines()` ใช้ `SKIP_STATUS` filter junk ออกก่อน push (ไม่ remind ผ่าน LINE)
- **RJ types**: "RJ", "Hot RJ", "Hot RB" — แยกออกจาก lead ปกติ
- **Called proof**: `call_proof == "ส่งแล้ว"` = โทรแล้วมีหลักฐาน

### Update Count & "ต้องโทร"
- `UPD_TGT = 4` — เป้าจำนวนครั้งที่ต้องอัปเดตต่อ lead 1 ราย
- `nc(u) = max(0, UPD_TGT - u)` — เหลืออีกกี่ครั้งให้ครบ
- `urg(u)` — urgency score (100 ถ้ายังไม่โทรเลย, +10 ต่อครั้งที่ขาด)

### 🏆 คะแนนเซลล์ (Scorecard 100 คะแนน — สูตรใหม่)
แทนสูตร Diligence/Max-Normalization เดิม. คิดแบบ **เทียบเป้าตายตัว** (ถึงเป้า=เต็ม, ไม่ถึงคิดสัดส่วน):
| ด้าน | เต็ม | สูตร |
|---|---|---|
| จบ (ปล่อย) | 20 | `min(ปล่อย/15,1)×20` |
| จอง | 10 | `min(จอง/60,1)×10` |
| Conv | 30 | `min((ปล่อย/lead×100)/5,1)×30` (ได้ 5%=เต็ม) |
| ติดตาม | 30 | `(Σmin(อัพเดท,4) / (4×เคสที่ต้องตาม)) ×30` |
| โดนแบน | 10 | `max(0, 10−จำนวนแบนเดือนนั้น)` |
- **2 ที่ต้อง sync กัน**: JS `buildDilMap()` (scorecard ที่โชว์จริง, ใน [index.html](dashboard/templates/dashboard/index.html), const `DONE_TGT/JONG_TGT/CONV_TGT`) + Python `compute_diligence_scores()` (สำหรับ export → sheet "leadscore"). แก้สูตรต้องแก้ทั้งคู่
- **ข้อมูลแบน**: `fetch_ban_counts_by_month()` อ่าน tab **"รายงานแบน"** (`SHEET_CONFIG["ban_report"]`, ไฟล์ live) — log 1 แถว=1 ครั้ง (`BAN_COL`), นับตาม banDate. inject เข้า `sellers[].bans` + `monthlySummary[m].sellers[name]["bans"]`
- เปิด modal คะแนน → ปุ่ม "ดูสูตรคะแนน" (`showScoreHelp`) อธิบาย 5 ด้าน

### Seller page KPI structure (`seller.html`)
หน้าเซลล์ (`/s/<token>/`) แบ่ง KPI เป็น 2 zones — ตัวเลขใหญ่ = ภาพรวม, chip = filter ลึกลง:
- **KPI cards (4 cards หลัก)** ใน `KPI_DEFS`: `all` หลีดที่รับ · `called` โทรแล้วมีหลักฐาน · `notCalled` ยังไม่โทร · `follow` ต้องโทรต่อ (status-based)
- **Filter chips ใต้ KPI** ใน `CALL_FILTERS` (disjoint by exact updateCount): `c0` ยังไม่โทร · `c1` 1 ครั้ง · `c2` 2 ครั้ง · `c3` 3 ครั้ง · `cFull` ครบ ${UPD_TGT}+
- ทั้ง 2 zones กดได้ → set `kpiFilter` → filter `lead list` ด้านล่าง (mutually exclusive — กดอันใหม่ override อันเดิม)
- ALL_FILTERS = [...KPI_DEFS, ...CALL_FILTERS] รวมไว้สำหรับ `findFilter(key)` lookup

### Date parsing
[fetch_dashboard.py](dashboard/services/fetch_dashboard.py) มี `parse_date()` รองรับ:
- Excel serial date (เลข 4-5 หลัก)
- "d/m/yy" หรือ "d/m/yyyy" (รองรับ พ.ศ. แปลงเป็น ค.ศ. ถ้า year > 2500)

### Date filter (กรองเดือน / ช่วงวัน)
- **UI**: `<input type="month">` (HTML5 native picker) แทนปุ่ม 12 เดือน → ไม่ต้องไปแก้โค้ดเวลามีเดือนใหม่
- **State**:
  - `index.html` ใช้ `dfMonth` (0=ทั้งปี, -1=วันนี้, 1-12=เดือน) + `setDfFromInput(v)` parse "YYYY-MM" → setDf(month)
  - `seller.html` ใช้ `fMonth` (เดือน) + `fDateFrom`/`fDateTo` (ช่วงวัน, "YYYY-MM-DD") — mutually exclusive (เลือก month → ล้าง range, เลือก range → ล้าง month). UI มี 2 แถว: เดือน + ช่วงวัน
- **Year**: ยังเป็น single-year (`is_this_year` filter ใน backend) — ถ้าผู้ใช้เลือกเดือนของปีอื่นใน picker จะใช้แค่ส่วน month
- **KPI rendering** (seller view ใน index.html):
  - `dfMonth > 0` → ใช้ `D.monthlySummary[dfMonth].sellers[name]` (overlay บน `sdYear` เพื่อคง target/team)
  - `dfMonth = 0` → ใช้ `D.sellers[]` (รายปี)
  - `m_sellers` ต้องมี field ครบ (lead/follow/vacant/booking/done/dealValue/leadTypes/...) — ดู `fetch_dashboard.py` `m_sellers[]` block
- **🔔 Banner แจ้งเตือนเดือนปัจจุบัน** (seller.html, เหนือ filter bar) — แสดง "ยังไม่โทร X เคส / ต้องตามต่อ Y เคส" ของเดือนปัจจุบัน **ไม่ขึ้นกับ filter** (เพื่อ remind เซลล์เสมอ). ใช้ helper `leadsInCurrentMonth()` ดึงข้อมูลจาก `D.leads` filter ด้วยเดือนของ `new Date()`

### MoM (Month-over-Month) Comparison
- JS helper ใน [index.html](dashboard/templates/dashboard/index.html): `getMoM(month, key)` คืน `{cur, prev, delta, pct, isUp}` + `momBadge(mom, invert, fmt)` สร้าง HTML badge `↗ +12.5%`
- **เปิดใช้เมื่อ** กดเลือกเดือนเฉพาะ (`dfMonth > 0`) และ `dfMonth >= 2` (เดือน 1 ไม่มีเดือนก่อน)
- เปรียบเทียบ: `monthlySummary[dfMonth].XXX` vs `monthlySummary[dfMonth-1].XXX`
- `invert=true` สำหรับ metric ที่ "ลด = ดี" (RJ, ติดตามค้าง) — สลับสี green/red
- Special case: `pct === 999` เมื่อเดือนก่อน 0 และเดือนนี้ > 0 → แสดง "✨ ใหม่" badge สีน้ำเงิน
- แสดงที่ไหน:
  - KPI cards หน้า dashboard หลัก (Lead, ติดตาม, จอง, ปิดได้, 💰 ยอดปล่อย, RJ)
  - Team breakdown card (Lead/จอง/ปิด/ยอดปล่อย ของแต่ละทีม)
  - หัวขึ้น hint "📊 % คือเทียบ พ.ค. vs เม.ย." เมื่อ MoM active

### Deal Value (มูลค่าดีล)
- ที่มา: คอลัมน์ `sale_price` (L=11) ใน sales_reports sheet
- `fetch_dashboard_data()` คำนวณ 3 ตัวเลขให้ทุกระดับ:
  - `dealValue` — sum(price) ของแถวที่ status = "ปล่อย"
  - `pipelineValue` — sum(price) ของ จอง/รอเซ็นต์/รอผล/รอปล่อย (ยังไม่จบ ไม่นับรีเจ็ก/ปล่อย) — **เก็บใน data แต่ UI ไม่แสดงตามผู้ใช้ขอ**
  - `avgDealValue` — เฉลี่ยต่อคัน
- มีให้ใน: `summary`, `sellers[]`, `teams`, `monthlySummary[m]`, `monthlySummary[m].sellers[name]`, `monthlySummary[m].teams[tid]`
- Daily breakdown: `dailyByMonth[m].dealValue[0..31]`, `dailyBySeller[name][m].dealValue[0..31]`
- UI: KPI card 💰 ยอดปล่อย + Top มูลค่าดีล panel + ตารางรายเซลล์มีคอลัมน์ ฿ ปล่อย + Line chart (รายเดือน/รายวัน) + Overview Flex executive ส่ง deal value ทุกทีม
- เพิ่ม `fmtBaht()` helper (JS) — แสดง `฿1.2M` / `฿850K` / `฿1,234` แบบกระชับ

### Analytics tables (admin/exec only)
ในหน้า dashboard หลัก มี 2 ตารางที่ guard ด้วย `if (canViewAll)` — เซลล์ทั่วไปไม่เห็น:

1. **🚗 Lead รถรุ่นยอดนิยม** — top cars by lead count
   - ใช้ **คอลัมน์ M เท่านั้น** (car_formula) — clean normalized names
   - มี pagination ไป/กลับ (20 รุ่น/หน้า) + 🔍 search + checkbox "ซ่อน 'ไม่ระบุ'"
   - กดที่แถวรถ → modal `openCarDetail(car)` แสดงเซลล์ที่รับเคสรถนั้น + จอง/ปล่อย/ยอดเงิน per seller
   - Lead match = exact `leadCarSellerMonth[car][seller]`
   - Booking match = substring case-insensitive ใน `b.car` (เพราะ lead car="Fortuner" แต่ booking car="Toyota Fortuner 2.4 V 2020")

2. **📋 เคสจอง (filter ตามสถานะ)** — ดูเคสจริงทุกสถานะ
   - Filter: สถานะ (ปล่อย default / ทุกสถานะ / จอง / รอเซ็นต์ / รอผล / รอปล่อย / รีเจ็ก), เซลล์, sort
   - คอลัมน์ "เก่า" — แสดงอายุเคสเป็นวัน (เขียว ≤30 / เหลือง ≤90 / แดง >90)
   - Sort: ล่าสุดก่อน / เก่าสุดก่อน / ราคามากสุด / เซลล์
   - Pagination ไป/กลับ (50/หน้า)
   - กดที่แถว → modal `openBookingDetail(idx)` แสดงทุกฟิลด์ + ไทม์ไลน์ + อายุเคส

## Google Sheets (7 sheets)

| sheet key | Spreadsheet | Tab | ใช้ |
|-----------|-------------|-----|-----|
| `leads` | `1s9FFPRV53U7pQTnBGSlkSFL8ygmRGRGYOAG1HakzgA0` | "รวม sheet" | รายการ lead ทั้งหมด |
| `sales_reports` | `13_vFkHEZWRAzxZiJ1Uj-NPlzlZtptyXuIjdxkGqlg8Y` | "รวม sheet" | ยอดขาย/สถานะจอง |
| `bookings` | `13jiQTOvcCvlKLGvjrb348_iRWoiMpumqqeEgOTkTgB0` | "รวม sheet" | รายการจอง |
| `live_sessions` | `18Djos3lUJnoZ00gYEBuCCExwm1YknfIQrP-TIuUgjWU` | "รวม sheet" | เซสชั่นไลฟ์ |
| `live_followups` | `18Djos3lUJnoZ00gYEBuCCExwm1YknfIQrP-TIuUgjWU` | "ติดตามไลฟ์สด" | คลิป follow-up |
| `employees` | `1HOhrPSIFTxfOpc4UWvKb-LfMuXGYW2vYkR5vbGzPd_A` | "เก็บข้อมูลพนักงาน..." | นิยามพนักงาน + LINE user_id |
| `sellers_config` | (เดียวกับ employees) | **"ตั้งค่าเซลล์"** | เป้า/ทีม dynamic — admin แก้ผ่าน UI หรือ Sheet ตรงๆ |
| `schedule_config` | (เดียวกับ employees) | **"ตั้งเวลาส่ง"** | ตารางเวลาส่ง LINE Flex อัตโนมัติ |

**OAuth scope**: `https://www.googleapis.com/auth/spreadsheets` (read+write — เปลี่ยนมาจาก readonly เพราะ admin ต้องเขียน config)

**Service account** ต้องมี Editor บน spreadsheet (เพื่อเขียน sheet sellers_config / schedule_config)

### ย้าย/เปลี่ยน spreadsheet ได้จากแอดมิน (override SHEET_CONFIG)
`SHEET_CONFIG` ใน [google_sheets.py](dashboard/services/google_sheets.py) เป็น **default (hardcode)**. Admin ย้ายไฟล์/tab ได้ผ่าน
panel **"📊 แหล่งข้อมูล (Sheets)"** → ปุ่ม **✏️ ย้าย/แก้ไขแหล่งข้อมูล** (ใช้ตอนขึ้นปีใหม่แล้วเปลี่ยนไฟล์ใหม่ — ไม่ต้องแก้โค้ด/deploy)
- เก็บ override ใน **Supabase table `sheet_config`** (cols: `key` PK, `spreadsheet_id`, `sheet_name`, `updated_at`)
- `load_sheet_config_overrides()` อ่านจาก Supabase แล้ว **mutate `SHEET_CONFIG` in-place** — เรียกที่ต้น `fetch_sheet()` (flag โหลดครั้งเดียว/process, admin บันทึก = `force=True`)
- บันทึก (`POST /api/admin/sheet_config`) = save Supabase → reload override → `invalidate_cache()` + เคลียร์ `_dash_cache` → ถ้า `USE_SUPABASE` จะ **re-sync mirror จากไฟล์ใหม่ทันที** (`sync_all_sheets_to_supabase`) ไม่งั้น dashboard เห็นข้อมูลเก่า
- ต้องมี Supabase ตั้งค่าแล้ว (`canEdit` = `is_configured()`); ไฟล์ใหม่ **service account ต้องมีสิทธิ์อ่านด้วย**
- SQL สร้างตาราง: `create table if not exists sheet_config (key text primary key, spreadsheet_id text, sheet_name text, updated_at timestamptz default now());`

### ⚡ Pre-compute dashboard (แก้ "ยิ่งข้อมูลเยอะยิ่งช้า")
แทนที่จะอ่าน 15k lead + aggregate สดทุกโหลด → **คำนวณล่วงหน้าเก็บผลไว้ คนเข้าเว็บอ่านผลสำเร็จรูป** (เร็วคงที่ ไม่ขึ้นกับจำนวนข้อมูล):
- `precompute_dashboard()` ([fetch_dashboard.py](dashboard/services/fetch_dashboard.py)) — คำนวณ `_compute_dashboard_data()` 1 ครั้ง → เก็บลง Supabase table **`dashboard_cache`** (1 แถว key='main', `data` jsonb)
- `fetch_dashboard_data()` อ่านเร็ว→ช้า: **in-memory (30s)** → **ผล pre-compute Supabase (`_PRECOMPUTE_TTL`=5นาที)** → คำนวณสด+เก็บ (fallback)
- รีเฟรชโดย: **`cron_tick`** (ทุก 1 นาที — branch "ไม่มี LINE ต้องส่ง" + ผลเก่า >4.5 นาที → sync+precompute) + `cron_sync`. ใช้ cron tick ตัวเดียว ไม่ต้องสร้าง cron sync แยก
- `upsert_sheet()` ตัด cell ว่างท้ายแถว (`_trim_row`) ลดขนาด jsonb — กัน leads (15k) เขียนชน Supabase statement timeout
- **ไม่แตะ Sheet เพิ่ม** — pre-compute อ่าน mirror (Supabase) ไม่ใช่ Sheet · Sheet ถูกอ่านแค่ตอน sync (~15-20 req ทุก ~5 นาที)
- SQL: `create table if not exists dashboard_cache (key text primary key, data jsonb, updated_at timestamptz default now());`
- ปลอดภัย: ไม่มี table = fallback คำนวณสดเหมือนเดิม (ไม่พัง)

**Helpers**:
- `fetch_sheet(key)` — อ่าน 1 tab ตาม SHEET_CONFIG.
- `fetch_leads_by_month_tabs()` — **default สำหรับทุก dashboard** — อ่านจาก monthly tabs (ม.ค.-ธ.ค. 69) **filter ให้แต่ละ row อยู่ใน tab ของเดือนตรงกับวันที่ใน column** (ตัดแถวที่ admin เอามาใส่ผิด tab ออก). ไม่ dedup. ตรงกับการนับ raw ใน Google Sheet ที่ admin คาดหวัง. **ใช้ใน**: `fetch_all_sheets()` (main dashboard), `seller_dashboard`, `line_notify.build_seller_pipelines()`
  - ตัวอย่าง พ.ค. 2026: tab "พฤษภาคม 69" raw=3,101 → filter date=พ.ค. → **2,585 เคส** (ตัด 516 เคสที่ admin เอาเคสเม.ย./มี.ค./ก.พ. มาใส่ tab พ.ค. ออก)
  - **ทำไมไม่ใช้ dedup**: `fetch_leads_dedup` ทำให้ lead เดือนนี้หาย ~30 เคส (2,552 vs 2,582) เพราะ code ซ้ำ + monthly tab override ทำ code "ย้ายเดือน". `fetch_sheet("leads")` ก็ inflated +83 จาก dup ภายใน 'รวม sheet' + orphan codes
  - Failsafe: ถ้า monthly tabs fetch ไม่ได้/ว่าง → fall back ไป `fetch_sheet("leads")`
- `fetch_sales_by_month_tabs()` — **default สำหรับ sales_reports** — อ่านยอดขายจากแท็บรายเดือน **`<เดือน>69` (ไม่เว้นวรรค)** ตรงๆ แทน "รวม sheet" (ที่ใช้สูตร REDUCE). แต่ละแท็บจัดกลุ่มตามเซลล์ด้วย marker **"ชื่อเซลล์ X"** ใน column B → ดึงบล็อกของแต่ละเซลล์ (ใต้ marker ถึง marker ถัดไป), เอาแถวที่ลำดับ(B)เป็นเลข+สถานะ(N)ไม่ว่าง, prepend ชื่อเซลล์เป็น col 0 (ตรง `SALES_COL` flattened เดิม). **match ชื่อกับ `ALL_SELLERS` (dynamic)** → เซลล์ใหม่เพิ่มเองอัตโนมัติ + ตัด marker ขยะ (A/ว่าง) → แก้ปัญหาสูตร hardcode 13 ชื่อ (สูตรตก "บิว" + ตัวสะกด "กลอฟ"). ใช้ใน `fetch_all_sheets()` + `sync_all_sheets_to_supabase()`. Failsafe → `fetch_sheet("sales_reports")` ("รวม sheet")
- `fetch_bookings_by_month_tabs()` — **default สำหรับ bookings (จอง)** — อ่านจากแท็บ **"จอง/จบ \<เดือน\> 69"** (ไฟล์ bookings) แทน "รวม sheet" (เก่า ไม่อัปเดต). แท็บวาง **จอง(ซ้าย A-K) + จบ(ขวา) แยกกัน** — อ่านแค่ A-K ฝั่งจอง ซึ่งตรง `BOOKINGS_COL` เป๊ะ → `year_jongs` กรอง date เอง. **ชื่อแท็บมี "/" → ใช้ `values:batchGet`** (range เป็น query param กัน URL path พัง 404). ใช้ใน `fetch_all_sheets()` + sync. Failsafe → `fetch_sheet("bookings")`
- `fetch_leads_dedup()` — **ใช้แค่ใน `admin_diagnostics`** (debug page เพื่อดู dedup behavior). รวม "รวม sheet" + monthly tabs แล้ว dedup by `Code` — แถวที่ปรากฏหลังสุดชนะ. ไม่ใช้ใน user-facing dashboard อีกแล้ว.
- `get_leads_dedup_stats()` — คืน `{input_rows, output_rows, duplicates_removed, no_code}` ของการ dedup ครั้งล่าสุด — ใช้ใน `/api/admin/diagnostics` เพื่อให้ admin มองเห็นว่าตัดซ้ำไปกี่แถว (field `leads.dedup` ใน JSON response)
- `ensure_sheet_tab(sid, tab)` — สร้าง tab ใหม่ถ้าไม่มี
- `write_sheet(key, values)` — clear + write ทับทั้ง tab

### Sheet column gotchas — ต้องระวัง

**sales_reports** ([google_sheets.py](dashboard/services/google_sheets.py) `SALES_COL`):
- `car_release_date = 22` (**W**) — ย้ายมาจาก V(21) ตอน sheet ปรับเดือน พ.ค. 2026
  - V(21) ตอนนี้เป็นโน้ตข้อความ (เช่น "รับ 16/5") ไม่ใช่วันที่แล้ว
  - มี `legacy_car_release_date = 21` เก็บไว้ fallback สำหรับข้อมูลเก่า
  - `fetch_dashboard.py` เลือก W ก่อน, ถ้า parse ไม่ได้ ลอง V (legacy)
- `status = 13` (N) — `"ปล่อย"` / `"จอง"` / `"รอเซ็นต์"` / `"รอผล"` / `"รอปล่อย"` / `"รีเจ็ก"` (+ `(ซื้อสด)` suffix)
- `sale_price = 11` (L) — ราคาขาย (สำหรับ deal value)

**leads** ([google_sheets.py](dashboard/services/google_sheets.py) `LEADS_COL`):
- `sales_rep = 4` (**E**) — ชื่อเซลล์
- `car_inquiry = 11` (L) — รถลูกค้าถาม (มีรายละเอียดเยอะ "Nissan Almera 1.2 E 2019")
- `car_formula = 12` (**M**) — CAR / สูตร (normalized "Almera") — **ใช้ตัวนี้สำหรับ aggregation Lead-by-Car**
- ใน Lead-by-Car table จับ M เท่านั้น (สะอาด ~67 รุ่น) — L มี ~2000 รุ่นเพราะข้อความไม่ normalized
- ใน lead/booking detail modal ยังใช้ L ก่อน (มี detail) → fallback M

#### ⚠️ Header-based column mapping (สำคัญ — แต่ละเดือน layout ไม่เหมือนกัน!)
ตั้งแต่ มิ.ย.69 ชีต lead จัดคอลัมน์ใหม่ (U–Y กลายเป็น อาชีพ/รายได้/อายุงาน/ประวัติผ่อน/ประเภทลูกค้า, สถานะหลักย้ายมา **Z "สถานะลูกค้า"**, Status แอดมิน เลื่อนไป AB). เดือนเก่า (ม.ค.–พ.ค.) ยัง layout เดิม → **คอลัมน์ต่างกันต่อ tab**
- **ห้าม fix ตำแหน่งคอลัมน์ตายตัวอีก** — `fetch_leads_by_month_tabs()` อ่าน header แต่ละ tab แล้ว `_resolve_lead_colmap()` จับคู่ field กับ "ชื่อหัวตาราง" (alias ใน `_LEAD_FIELD_ALIASES`) → `_normalize_lead_row()` จัดทุกแถวให้อยู่ canonical `LEADS_COL` เหมือนกันหมด ก่อนส่งต่อ
- field ที่หา header ไม่เจอ = **เคลียร์ว่าง** (กันค่าคอลัมน์อื่นปนแล้วอ่านผิด เช่น "อัพเดทเคส...ดึงคืน" ไปโผล่ sales_status แล้ว match keyword "คืน")
- `LEADS_COL.customer_status = 33` (canonical slot ใหม่สำหรับคอลัม Z) — `admin_status=26`, `sales_status=28` ยังเป็น canonical เดิม (normalize ยัดค่าจาก source ที่ถูกต้องมาให้)
- เพิ่ม alias เมื่อชีตเปลี่ยนชื่อหัวคอลัมน์: แก้แค่ `_LEAD_FIELD_ALIASES` ใน [google_sheets.py](dashboard/services/google_sheets.py)
- **เขียนกลับคอลัม S**: `update_lead_fill_note(code, value, month, expected_seller)` — หา source col ของ fill_sheet_note/lead_code จาก header (รองรับทุก layout), หาแถวจาก Code, PATCH cell เดียว, ตรวจ ownership เซลล์

## LINE Integration

### Channel Access Token
ใส่ใน `.env`:
```
LINE_CHANNEL_ACCESS_TOKEN=xxx...
CRON_SECRET=xxx...
```
ทั้ง 2 ตัวต้องตั้งบน Vercel environment variables ด้วย (`.env` ไม่ถูก push deploy)

### Flex Messages
[line_notify.py](dashboard/services/line_notify.py):
- `build_seller_pipelines()` — group leads ของเดือนปัจจุบัน → called/notCalled/followUp/noStatus
- `build_seller_flex(pipeline, base_url)` — สร้าง Flex JSON (header สี + 3 stat boxes + progress bar + rows + ปุ่ม `/s/<token>/`)
- `push_line_message(uid, msgs, token)` — POST ไป LINE push endpoint
- `load_schedules()` — อ่าน schedule sheet
- `schedule_matches_now(sched)` — เช็คว่าตาราง match เวลา BKK ปัจจุบัน

### Trigger 2 แบบ
1. **Manual** — admin กดปุ่ม "📤 LINE Flex" → tab "ส่งทันที" → POST `/api/admin/send_line`
2. **Auto** — cron-job.org ยิง `/api/cron/tick?secret=xxx` ทุก 1 นาที → `cron_tick` view เช็ค `load_schedules()` → ถ้า match ส่ง Flex

### Schedule format (sheet "ตั้งเวลาส่ง")
```
เวลา (HH:MM) | วัน (* / 1-5 / 0,6) | เซลล์ (* / "โอ๊ต,เก้า") | test_target | enabled (TRUE/FALSE) | ป้ายชื่อ
09:00        | 1-5                | *                       |             | TRUE                 | เช้าวันทำการ
13:00        | *                  | *                       |             | TRUE                 | เที่ยง
```
- วัน: 0=อาทิตย์, 1=จันทร์, ..., 6=เสาร์
- test_target ใส่ user_id = ส่งเข้า user นั้นแทน (test mode) / ว่าง = ส่งจริงไปทุกเซลล์

## Conventions

- **ไม่มี Django models / migrations** — โปรเจกต์ตั้งใจไม่มี local DB
- **ไม่ใช้ Django auth** — auth ผ่าน signed-cookie session + URL token
- **Frontend = template + vanilla JS** — Chart.js ผ่าน CDN เท่านั้น, ไม่ใช้ React/build pipeline
- **Thai สำหรับ user-facing text** (label, error)
- **Timezone**: ใช้ `bangkok_now()` เสมอ ไม่ใช่ `datetime.now()` ดิบ
- **Normalize seller name**: ใช้ `normalize_seller()` ทุกครั้งที่อ่านชื่อจาก sheet
- **In-place mutation**: `refresh_from_sheet()` แก้ TEAMS/TARGETS ด้วย `.clear()` + `.update()` ไม่ reassign (กัน import binding หาย)

## งานที่เจอบ่อย

### เปลี่ยนเป้าเซลล์
1. Login admin → ปุ่ม **🎯 ตั้งเป้า/ทีม** → แก้เลข target → Save
2. หรือแก้ใน Google Sheet tab "ตั้งค่าเซลล์" ตรงๆ → refresh dashboard

### เพิ่มเซลล์ใหม่
1. ปุ่ม **🎯 ตั้งเป้า/ทีม** → ➕ เพิ่ม → ใส่ ชื่อเล่น/ทีม/เป้า → Save
2. ถ้าอยากให้เซลล์มี URL ส่วนตัว → เพิ่ม token ใน [seller_tokens.py](dashboard/services/seller_tokens.py) (commit + push)

### ส่ง LINE Flex ทันที (manual)
ปุ่ม **📤 LINE Flex** → tab "🚀 ส่งทันที" → เลือกเซลล์ + (optional: test mode + user_id) → 📤 ส่ง

### ตั้งเวลาส่งอัตโนมัติ
1. ปุ่ม **📤 LINE Flex** → tab "📅 ตารางเวลา" → ➕ เพิ่ม → ใส่เวลา/วัน/เซลล์/enabled → Save
2. ครั้งแรกต้องตั้ง cron-job.org ยิง `https://<your-app>.vercel.app/api/cron/tick?secret=<CRON_SECRET>` ทุก 1 นาที (one-time setup)

### Debug ข้อมูลผิด
- **ปุ่ม 🔍 Log ข้อมูล** ใน admin header → เปิด modal โชว์เคสที่หาย (วันที่พัง, สถานะว่าง, "รอปล่อย" ที่อาจสับสนกับ "ปล่อย") + status breakdown
- `/api/admin/diagnostics` (admin only) → JSON ของข้อมูลด้านบน
- `/api/dashboard` คืน JSON เต็มของ aggregator
- `/api/admin/send_line` (admin login) → แสดง preview pipeline + `token_debug`
- เช็คว่า `normalize_seller()` ครอบคลุมการสะกดในชีตหรือยัง
- **ยอด "ปิดได้" ไม่ตรง** → เช็คว่า sheet sales_reports คอลัมน์ปล่อยรถยังอยู่ที่ W(22) หรือถูกย้ายอีก (ดู section "Sheet column gotchas")
- **มูลค่าดีลผิด** → เช็คคอลัมน์ L(11) `sale_price` มีข้อมูลครบไหม (`cell_num()` คืน 0 ถ้าว่าง/parse ไม่ได้)
- **เคสหาย / อัพเดทแล้วไม่ขึ้น** → กดปุ่ม 🔍 Log ข้อมูล (admin only) จะเห็น breakdown ว่าทำไมเคสไม่ขึ้น
- **เคสมีใน "พฤษภาคม 69" ครบแล้วแต่ dashboard ยังโชว์ค่าเก่า** → "รวม sheet" pull ข้อมูลจาก tab เก่ากว่า. ใช้ `fetch_leads_dedup()` แล้ว — มันรวมทุก monthly tab + เลือกแถวล่าสุดอัตโนมัติ (ดู `fetch_leads_dedup` ใน [google_sheets.py](dashboard/services/google_sheets.py))

### เพิ่ม feature ใหม่
**ทุกครั้งที่เพิ่ม/แก้ feature → ต้องอัพเดท CLAUDE.md ด้วย** (โดยเฉพาะ section URL routes, Sheet column gotchas, Roles, Concepts)
- Commit รวมกับไฟล์ source เดียวกัน ห้ามแยก

## Deploy บน Vercel

1. **env vars บน Vercel dashboard** (Settings → Environment Variables) ใส่ทุกตัวจาก `.env`:
   - `GOOGLE_SERVICE_ACCOUNT_EMAIL`, `GOOGLE_PRIVATE_KEY`, `DJANGO_SECRET_KEY`, `DEBUG=False`
   - `OXLET_ADMIN_USER`, `OXLET_ADMIN_PASSWORD`
   - `LINE_CHANNEL_ACCESS_TOKEN`, `CRON_SECRET`
   - `ALLOWED_HOSTS=your-app.vercel.app`, `CSRF_TRUSTED_ORIGINS=https://your-app.vercel.app`

2. **Use canonical URL** (`your-app.vercel.app`) ไม่ใช่ deployment-specific URL (`your-app-xxx.vercel.app`) — อันยาวมี Vercel Auth wall ป้องกันอยู่

3. **cron-job.org** ตั้ง webhook URL = `https://your-app.vercel.app/api/cron/tick?secret=<CRON_SECRET>` schedule = `* * * * *` (ทุก 1 นาที)

4. **Service account** ต้องมีสิทธิ์ **Editor** บน Google Spreadsheet (เพื่อเขียน config sheets)

## Known issues / limitations

- **Cold start ช้า** บน Vercel — request แรกหลังนิ่งนาน ~5-10s (pip install + Django boot + auth)
- **Sheets API quota** — ปกติ dashboard อ่าน **mirror/pre-compute (Supabase) ไม่แตะ Sheet** · Sheet ถูกอ่านแค่ตอน sync (~15-20 req ทุก ~5 นาที — ต่ำกว่า 300/min/project มาก)
- **leads upsert ใหญ่** — 15k แถวเป็น jsonb ก้อนเดียว เคยชน Supabase statement timeout (8s) · บรรเทาด้วย `_trim_row` · ถ้ายังชนบ่อย → `alter role service_role set statement_timeout='30s'`
- **Schedule precision = 1 นาที** (ตาม cron interval)
- **No deduplication** — ถ้า cron-job.org ยิง 2 ครั้งใน 1 นาที (rare) จะส่ง Flex 2 ครั้ง
- **Vercel Hobby** = 1 cron job/วัน (ใช้ external cron-job.org แทน)
- **เซลล์ใหม่** ที่เพิ่มผ่าน 🎯 ตั้งเป้า/ทีม จะใช้งานได้ทันที **ยกเว้น URL `/s/<token>/`** ที่ต้อง add token เองใน code
