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
.env                     # secrets — gitignored (ไม่ commit) · local เท่านั้น + Vercel env
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
| `/dashboard/` | `dashboard_page` | **ต้อง login (admin/ผู้บริหาร)** — เซลล์ → redirect ไป `/me/` · ไม่ login → `/login/` |
| `/admin/` | `admin_page` | **ต้อง login admin** เท่านั้น (ไม่งั้น → `/login/`) |
| `/me/` | `me_dashboard` | หน้าส่วนตัวของเซลล์ที่ login — ดึง `seller_name` จาก session, render `seller.html` (data แยกเฉพาะตัว) |
| `/login/` | `login_view` | GET = form, POST = **LINE user_id + รหัสรวม** (`OXLET_SELLER_PASSWORD`) หรือ admin user/pass (env, สำรอง) |
| `/logout/` | `logout_view` | clear session → กลับ `/login/` |
| `/u/<token>/` | `magic_link` | login เซลล์ผ่าน LINE user_id (จาก employees sheet) |
| `/s/<token>/` | `seller_dashboard` | หน้าส่วนตัวของเซลล์ — token จาก [seller_tokens.py](dashboard/services/seller_tokens.py) หรือ LINE user_id · **ต้อง login ก่อน (PDPA)**: ไม่มี session → redirect `/login/?next=` · เซลล์ดูได้เฉพาะของตัวเอง (ไม่งั้น → `/me/`) · admin/exec ดูได้ทุกคน |

### API

| URL | View | ใช้ทำอะไร |
|---|---|---|
| `/api/dashboard` | `api_dashboard` | JSON ของ full dashboard data |
| `/api/auth?token=` | `api_auth` | ตรวจ LINE user_id กับ employees sheet |
| `/api/admin/send_line` | `admin_send_line` | admin: GET=preview, POST=ส่ง Flex ทันที |
| `/api/admin/seller_config` | `admin_seller_config` | admin: GET=อ่าน config, POST=บันทึก (เขียน sheet "ตั้งค่าเซลล์") — รวมคอลัมน์ `is_admin` (เซลล์แอดมิน) |
| `/api/admin/admin_config` | `admin_admin_config` | admin: GET=รายชื่อแอดมิน(ไอดี)+employees, POST=บันทึก (เขียน sheet "ตั้งค่าแอดมิน") — เทเลเซลล์/ออฟฟิศที่ไม่ใช่เซลล์ |
| `/api/admin/schedule_config` | `admin_schedule_config` | admin: GET=อ่านตาราง, POST=บันทึก (เขียน sheet "ตั้งเวลาส่ง") |
| `/api/admin/diagnostics` | `admin_diagnostics` | admin: ตรวจ log การกรองข้อมูล (เคสที่หาย, วันที่พัง, สถานะว่าง, "รอปล่อย" cases) |
| `/api/admin/sheets_status` | `admin_sheets_status` | admin: เช็คสด 6 แหล่งข้อมูล + tab รายเดือน + sheet ตั้งค่า (panel "📊 แหล่งข้อมูล" แบบ n8n) |
| `/api/admin/sheet_config` | `admin_sheet_config` | admin POST: ย้าย spreadsheet/tab ของแต่ละแหล่ง (เก็บ Supabase `sheet_config`) — ใช้ตอนขึ้นปีใหม่/ย้ายไฟล์ |
| `/api/admin/list_drive_sheets` | `admin_list_drive_sheets` | admin GET: รายชื่อไฟล์ Google Sheets ที่ service account เข้าถึงได้ (Drive API) — ทำ dropdown เลือกไฟล์แบบ n8n |
| `/api/admin/list_tabs` | `admin_list_tabs` | admin GET `?sid=`: รายชื่อ tab ของ spreadsheet — ทำ dropdown เลือก tab |
| `/api/admin/system_health` | `admin_system_health` | admin GET: สถานะระบบ — อายุ sync, จำนวนข้อมูล, Supabase/LINE, + เช็กข้อมูลผิดอัตโนมัติ (sync ค้าง/วันนี้ไม่มี lead/lead=0) → ให้แอดมินเช็คเองโดยไม่ต้องมี dev |
| `/api/admin/refresh_data` | `admin_refresh_data` | admin POST: สั่ง sync + precompute เดี๋ยวนี้ (ปุ่มรีเฟรชในหน้าสถานะระบบ) |
| `/api/admin/update_release_date` | `update_release_date` | **admin (session) หรือเซลล์ (token/session + ownership)** POST: inline edit "วันปล่อย" เขียนกลับชีตยอดขายตรงเซลล์ — body `{tab,row,col(14\|18\|19\|21\|23),value,token?}` → `update_release_date()` PUT cell (เซ็น/ผล/เอกสาร/ปล่อย). เซลล์แก้ได้เฉพาะเคสตัวเอง (เช็คชื่อที่ marker ของแถว = `cell(r,0)`). ใช้จาก `saveReleaseDate` ทั้ง index.html (แอดมิน) + seller.html (เซลล์) |
| `/api/seller/update_note` | `update_lead_note` | เซลล์ (token) เขียนกลับ Google Sheet จาก lead detail — รับ `field` (S=`fill_sheet_note` / Z=`customer_status` / N=`call_proof`) + `value` (back-compat: `note`) → header-aware + ตรวจ ownership |
| `/api/cron/send_line` | `cron_send_line` | public (`?secret=xxx`) — ส่ง Flex แบบ one-shot, manual params |
| `/api/cron/tick` | `cron_tick` | public (`?secret=xxx`) — (1) sync mirror+precompute **ทุก ~3-4 นาที** (ผลเก่า >180วิ · ห้ามลดต่ำ — ดู "บทเรียน server ล่ม") (2) ส่งแจ้งเตือน **"ตามด่วน" รายเซลล์ ตามเวลาในชีต "ตั้งเวลาส่ง"** (default 09:00/13:00 · แก้เวลา/ผู้รับ/test ในหน้า "ตารางเวลา (Auto)") — cron อ่าน `load_schedules`+`schedule_matches_now` แล้วยิง `build_followup_messages` (3) เขียน heartbeat `cron_tick` + followup log `cron_followup` (Supabase kv) → หน้าสถานะระบบโชว์ "cron ทำงานล่าสุด" |

## Roles (สิทธิ์ผู้ใช้)

| Role | position | สมัครได้ในชื่อ | ทำได้ | UI badge |
|------|---------|----|------|----------|
| **แอดมินสูงสุด** | `admin` | "แอดมินสูงสุด" | เห็นทุกอย่าง + 🚗 Lead รถ + 📋 เคสจอง + impersonate + ปุ่ม 📋 LINE ID / 📤 LINE Flex / 🎯 ตั้งเป้า | 👑 Admin (อำพัน) |
| **ผู้บริหาร** | `executive` / `ผู้บริหาร` / `manager` / `exec` | "ผู้บริหาร" | เห็นทุกอย่าง + 🚗 Lead รถ + 📋 เคสจอง + impersonate (ไม่มีเครื่องมือ admin) | 🎩 ผู้บริหาร (ม่วง) |
| **เซลล์** | `seller` / อื่นๆ | "เซลล์" | เห็นเฉพาะตัวเอง (ไม่เห็น Analytics tables) — login แล้ว → `/me/` | 👤 ชื่อเล่น (น้ำเงิน) |

ใน [index.html](dashboard/templates/dashboard/index.html) `isAdmin`=`position==='admin'` · `isExecutive`=position ∈ {executive,ผู้บริหาร,manager,exec} · `canViewAll`=isAdmin||isExecutive. ตาราง Lead-by-Car และ Released-Cars ห่อด้วย `if (canViewAll)`

**⚠️ บังคับ login ทุกหน้า (ไม่มี default test user แล้ว)** — `dashboard_page`/`admin_page`/`api_dashboard` เช็ค session ก่อนเสมอ ([views.py](dashboard/views.py) helper `_session_user`/`_can_view_all`/`_is_admin`). เซลล์ที่เผลอเข้า `/dashboard/` → redirect `/me/` (กันเปิด DevTools เห็น data รวมของทุกคน)

**Login (แบบง่าย — ไม่มีสมัครสมาชิก)** — ทุกทางเก็บ session `oxlet_user = {user_id, nickname, display_name, position, seller_name?}`:
0. **หลัก (PDPA): LINE Login (OAuth)** — ปุ่ม "เข้าสู่ระบบด้วย LINE" → `/auth/line/start` (redirect ไป LINE authorize, state ใน session) → `/auth/line/callback` แลก code→token→ดึง LINE userId (ยืนยันแล้ว) → `_login_with_line_user_id()` หา employee + set session (หมดอายุ 14 วัน) → exec/admin ไป `/dashboard/`, เซลล์ไป `/me/` (อิง session ไม่ใช่ token). ต้องตั้ง `LINE_LOGIN_CHANNEL_ID`/`LINE_LOGIN_CHANNEL_SECRET` (env) + Callback URL ใน LINE Login channel = `LINE_LOGIN_CALLBACK`
1. **สำรอง: LINE user_id + รหัสรวม** — POST `/login/` ด้วย `token`(LINE user_id) + `password`. รหัสต้องตรง `OXLET_SELLER_PASSWORD` (env, default `OXletauto55555`) → หา user_id ใน employees sheet → role จาก [ชีตตั้งค่าแอดมิน/เซลล์แอดมิน](#-แอดมินจาก-line-user_id-2-ทาง) → exec/admin ไป `/dashboard/`, เซลล์ไป `/s/<user_id>/`
2. **แอดมินระบบ (สำรอง/break-glass)** — username/password จาก env `OXLET_ADMIN_USER` / `OXLET_ADMIN_PASSWORD`
3. **เซลล์ (ลิงก์ตรง ไม่ต้อง login)** — `/s/<token>/` (token จาก seller_tokens.py) หรือ `/u/<token>/` (LINE user_id) — เซลล์ใช้ลิงก์ส่วนตัวเข้าได้เลย

> **เลิกใช้แล้ว (มิ.ย.69)**: ระบบสมัครสมาชิก + อนุมัติทางเมล (email/password, Supabase `app_users`, Gmail SMTP, signed token, `/register/`, `/account/review/`) — ถอดออกเพราะซับซ้อนเกินจำเป็น (เซลล์มีลิงก์อยู่แล้ว). LINE user_id หาได้ที่ปุ่ม 📋 LINE ID พนักงาน · รหัสรวมตั้งให้ทุกคนใช้ร่วมกัน. **ไม่ต้องใช้ Gmail/app_users อีก**

## Concepts สำคัญ

### Sellers & Teams (Dynamic)
- **เริ่มต้น (fallback)**: [constants.py](dashboard/services/constants.py) มี `TEAMS` + `TARGETS` hardcode
- **Override (จริง)**: อ่านจาก Google Sheet tab **"ตั้งค่าเซลล์"** (cols: ชื่อเล่น | ทีม | เป้า | **แอดมิน**)
  - `fetch_dashboard_data()` เรียก `refresh_from_sheet()` ทุกครั้ง → mutate TEAMS/TARGETS/ALL_SELLERS/TEAM_ID/**ADMIN_SELLERS** in-place
  - Sheet ว่าง/error → fallback ใช้ค่า hardcode
- **Admin แก้ในระบบ**: ปุ่ม **🎯 ตั้งเป้า/ทีม** → inline edit table (มี checkbox 👑 แอดมิน) → POST เขียนทับ sheet
- **เพิ่มเซลล์ใหม่**: แค่เพิ่มแถวใน sheet → ระบบ pickup auto (แต่ token ใน [seller_tokens.py](dashboard/services/seller_tokens.py) ต้องเพิ่มเองสำหรับ URL `/s/`)
- **`SELLER_MAP`** = normalize ชื่อสะกดต่าง (เจเจ→เจ, กลอฟ→กอล์ฟ) — ใช้ผ่าน `normalize_seller()` เสมอ

#### 👑 แอดมินจาก LINE user_id (2 ทาง — แก้ได้เองในแดชบอร์ด เพราะคนเป็นแอดมินเปลี่ยนบ่อย)
ตอน login ด้วย LINE user_id (`login_view` LINE branch) → ได้ `position="admin"` ถ้าเข้าเงื่อนไขข้อใดข้อหนึ่ง (เรียก `refresh_from_sheet()` + `load_admin_user_ids()` ก่อนเช็ค) — **ทั้ง 2 แบบยังนับเป็นเซลล์ปกติในสถิติ** (ยอดมาจากชีต ไม่ขึ้นกับ role):

**1. เซลล์แอดมิน** — เซลล์ใน TEAMS ที่ติ๊ก "แอดมิน":
- คอลัมน์ D `is_admin` ในชีต **"ตั้งค่าเซลล์"** (`SELLER_CONFIG_COL.is_admin=3`) = `TRUE`/ว่าง → `refresh_from_sheet()` สร้าง set **`ADMIN_SELLERS`**
- จัดการ: ปุ่ม **🎯 ตั้งเป้า/ทีม** → checkbox 👑 ต่อเซลล์ (`admin_seller_config`: GET ส่ง `is_admin`, POST เขียน 4 คอลัมน์)

**2. แอดมินไอดี (เทเลเซลล์/ออฟฟิศ ที่ไม่ใช่เซลล์ใน TEAMS)** — รายชื่อ LINE user_id ตรงๆ:
- ชีต **"ตั้งค่าแอดมิน"** (`SHEET_CONFIG["admin_config"]`, cols: LINE user_id | ชื่อ | หมายเหตุ) → `load_admin_user_ids()` สร้าง set **`ADMIN_USER_IDS`** ([constants.py](dashboard/services/constants.py))
- จัดการ: ปุ่ม **👑 จัดการแอดมิน** (เมนูจัดการ) → เลือกจาก employees หรือวาง user_id → เพิ่ม/ลบ (`admin_admin_config`: GET ส่ง admins+employees, POST เขียนชีต) · แก้ในชีตตรงๆ ก็ได้
- ใช้เมื่อแอดมิน**ไม่ได้อยู่ใน 13 เซลล์** (เช่น ทีมโทร/ออฟฟิศ) — checkbox ในตั้งค่าเซลล์จะไม่มีให้ติ๊ก
- **"ADMIN" seller = ศูนย์รวมเทเลเซลล์**: เคสที่ลงชื่อเซลล์ = "ADMIN" ในชีต ถูกรวมเป็น seller ชื่อ "ADMIN" (team="ADMIN"). ไอดีเทเลเซลล์ทั้ง 5 → `seller_from_token()` map เป็น "ADMIN" → เปิด `/s/<id>/` เห็นหน้ารวมเทเลเซลล์ (`fetch_seller_stats("ADMIN")`). dropdown แท็บเซลล์ใช้ `sellerTokens["ADMIN"]` = ไอดีเทเลเซลล์คนแรก (ตั้งใน [fetch_dashboard.py](dashboard/services/fetch_dashboard.py))

- แอดมิน(เซลล์)ใช้ปุ่ม "ดูในฐานะ <ตัวเอง>" (impersonate) ดูหน้าเซลล์ตัวเองได้ · ต่างจาก **แอดมินสูงสุด** (env/`app_users role=admin`)

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
| จบ (ปล่อย) | 30 | `min(ปล่อย/15,1)×30` |
| จอง | 10 | `min(จอง/30,1)×10` |
| Conv | 20 | `min((ปล่อย/lead ปกติ×100)/5,1)×20` (ได้ 5%=เต็ม · **lead ปกติ = ไม่รวม RJ**) |
| สถานะ (เดิม "ความเร็ว"/"เวลาปิดดีล") | 10 | เคสปล่อย: เฉลี่ย 3 ช่วง (จอง→เซ็น ≤3วัน · เซ็น→ผล ≤3วัน · ผล→ปล่อย ≤1วัน) ×10 — ความเร็วการขยับสถานะ |
| ติดตาม | 20 | `(Σmin(อัพเดท,4) / (4×เคสที่ต้องตาม)) ×20` |
| โดนแบน | 10 | `max(0, 10−จำนวนแบนเดือนนั้น)` |
- **ความเร็ว (velocity)**: วัดเฉพาะ**เคสที่ปล่อยแล้ว** (status="ปล่อย") ในช่วงที่เลือก. แต่ละช่วง: ทันกำหนด=1.0, เกินลดเชิงเส้นถึง 0 ที่ **3× กำหนด** (เช่น จอง→เซ็น: 3วัน=เต็ม, 9วัน=0). **ช่องวันว่าง/parse ไม่ได้ = 0 ช่วงนั้น** (จูงใจให้เซลล์กรอก `signDate`/`resultDate` ในชีตยอดขาย). ใช้ฟิลด์ booking_cases: `date`(จอง C) `signDate`(เซ็น O) `resultDate`(ผล T) `releaseDate`(ปล่อย V). JS helper `_stageScore()` + const `VEL_STAGES` · Python `_stage_score()`+`_case_velocity()`
- **2 ที่ต้อง sync กัน**: JS `buildDilMap()` (scorecard ที่โชว์จริง, ใน [index.html](dashboard/templates/dashboard/index.html), const `DONE_TGT=15/JONG_TGT=30/CONV_TGT=5` + `VEL_STAGES`) + Python `compute_diligence_scores()` (สำหรับ export → sheet "leadscore"). แก้สูตรต้องแก้ทั้งคู่
- **ข้อมูลแบน**: `fetch_ban_counts_by_month()` อ่าน tab **"รายงานแบน"** (`SHEET_CONFIG["ban_report"]`, ไฟล์ live) — log 1 แถว=1 ครั้ง (`BAN_COL`), นับตาม banDate. inject เข้า `sellers[].bans` + `monthlySummary[m].sellers[name]["bans"]`
- เปิด modal คะแนน → ปุ่ม "ดูสูตรคะแนน" (`showScoreHelp`) อธิบาย 6 ด้าน

### Seller page KPI structure (`seller.html`)
หน้าเซลล์ (`/s/<token>/`) แบ่ง KPI เป็น 2 zones — ตัวเลขใหญ่ = ภาพรวม, chip = filter ลึกลง:
- **KPI cards (4 cards หลัก)** ใน `KPI_DEFS`: `all` หลีดที่รับ · `called` โทรแล้วมีหลักฐาน · `notCalled` ยังไม่โทร · `follow` ต้องโทรต่อ (status-based)
- **Filter chips ใต้ KPI** ใน `CALL_FILTERS` (disjoint by exact updateCount): `c0` ยังไม่โทร · `c1` 1 ครั้ง · `c2` 2 ครั้ง · `c3` 3 ครั้ง · `cFull` ครบ ${UPD_TGT}+
- ทั้ง 2 zones กดได้ → set `kpiFilter` → filter `lead list` ด้านล่าง (mutually exclusive — กดอันใหม่ override อันเดิม)
- ALL_FILTERS = [...KPI_DEFS, ...CALL_FILTERS] รวมไว้สำหรับ `findFilter(key)` lookup

#### 🔥 ตามด่วน — สมองจัดลำดับความสำคัญ (`followUrgency` ใน seller.html)
section "ตามด่วน — โทรก่อน" (เดิม "โทรเคสไหนก่อน" เรียงแค่ leadScore) → อัปเกรดเป็น **สมองรวม** ที่ช่วยเซลล์รู้ว่า "ตามใครก่อน":
- **`followUrgency(l)`** รวม 4 สัญญาณ: **ยังไม่โทร** (`updateCount===0` → +120, speed-to-lead) · **ฮอท × ดองนาน** (`leadScore/100 × idleDays × 9` — หัวใจ ทำให้ "ฮอทแต่ค้างนาน" พุ่งบน) · **สถานะลูกค้า** (`followPriority×6`) · **ดองนานเฉยๆ** (`idle×2`). `_idleDays` = วันตั้งแต่ `lastUpdate` (ไม่งั้น `dateIn`)
- **`urgencyReason(l)`** → ป้าย "ด่วนเพราะ: ยังไม่โทรเลย / ฮอทแต่ค้าง X วัน / ค้าง X วัน / ลูกค้าสนใจมาก"
- filter เดิม: `!isSkipped && !isBooked` (junk/จอง/ส่งมอบ ไม่ต้องตาม)
- **จังหวะตาม (cadence)**: เพิ่งตามยังไม่ถึงรอบ → urgency ×0.35 (ไม่เด้งซ้ำ) · `CADENCE` ต่อสถานะ (สนใจมาก 1 · ลังเล 2 · ไม่รับสาย 1 · รอเงิน 3 · รอเช็คเครดิต 2 · ดาวน์ไม่พอ 3 · default 2) · `over = idle − cadenceDays` (เลยรอบ = ด่วน · ฮอท×over) · **ไม่รับสายเกิน `NOANS_CAP`(5) ครั้ง → return −1 (พักไว้ ไม่สแปม)** · section filter ตัด `followUrgency ≤ 0`
- **section "🚩 ดีลค้าง — ดันต่อ"** (ใต้ "ตามด่วน") — จาก `bookingsInRange()` (idx ตรงกับ `openBookingDetail`): จอง/รอเซ็นค้าง >3วัน · รอผลนาน >5วัน · รอปล่อยค้าง >3วัน → เรียงวันค้าง top 8 (ดีลเกือบปิด ต่างจากลีดใหม่)
- **เฟส 2 (ทำแล้ว — PRODUCTION ส่งเซลล์จริง)**: `build_followup_messages()` ([fetch_dashboard.py](dashboard/services/fetch_dashboard.py)) = mirror `followUrgency`+cadence+ดีลค้าง เป็น Python (pass เดียว group ตาม seller · ไม่เรียก `fetch_seller_stats` ต่อคน) → ข้อความธรรมดา top N + ลิงก์ `/s/`. **`cron_tick` อ่านตารางจากชีต "ตั้งเวลาส่ง"** (`load_schedules`+`schedule_matches_now`) → ถึงเวลาแถวที่ enabled = ส่ง (default 09:00/13:00 · แอดมินแก้เวลา/ผู้รับ/test ในหน้า "ตารางเวลา (Auto)" ได้เอง — **เลิก hardcode `_FU_TIMES`/`_FU_TEST_TARGET` แล้ว · repurpose schedule sheet ที่เดิมคุม Flex มาคุม followup**). แต่ละแถว: `test_target` ว่าง=ส่งเซลล์จริง · ใส่ user_id=ทดสอบ · `sellers` (*/รายชื่อ)=กรองผู้รับ. กรองเฉพาะเคสใหม่ (เดือนนี้ + 1 สัปดาห์ท้ายเดือนก่อน) · dedup ดีลค้าง · ใช้ canonical URL `_FU_BASE`. ยังไม่มี anti-spam Supabase (อาศัย time-match HH:MM)

#### 🎯 Lead Score (คุณภาพ lead — `compute_lead_score` ใน fetch_dashboard.py)
คะแนน "เคสนี้น่าปิดแค่ไหน" (ต่างจาก **คะแนนเซลล์**/scorecard) — `leadScore`/`leadTier`/`scoreBreakdown` คำนวณ Python ฝั่ง view ส่งเป็น data ให้ seller.html (ไม่มี JS mirror) · เกณฑ์อยู่ใน `_LEAD_SCORE_DEFAULTS` (fallback) หรือ sheet **"เกณฑ์คะแนน lead"** (override ถ้ามี — `load_lead_score_config`)
- **4 ด้าน (มิ.ย.69 ตัด รถ/ประวัติ ออก)**: ความใหม่ (≤3วัน +20 · เย็น -5) · **ประเภท (Type)** · ช่องทาง (Walk-in +15 · TikTok +10 · FB +5) · Engagement (ลูกค้าตอบ +25 · inbox +15 · โทรไม่รับ -10)
- **Type = match ค่าในชีตตรงๆ** `_apply("ประเภท: " + lead_type)` → รองรับทุกค่า + เพิ่มใหม่ในชีตได้: Very Hot 60 · Hot / TLD&nbsp;Hot 50 · MerHot 38 · TLD / Moderate 35 · BLD 30 · Hot RB 28 · Hot RJ 22 · RJ 15. **(เดิม else=Normal+50 → Moderate/TLD/BLD = 65% ของลีดได้ +50 เท่า Very Hot → "เคสธรรมดาดูฮอท")**
- **tier**: hot ≥55 · warm ≥35 · cold <35 (ปรับลงจาก 80/50 หลังตัดรถ) → distribution จริง ~3% hot / 30% warm / 67% cold
- แก้คะแนน Type → แก้ `_LEAD_SCORE_DEFAULTS` + sync help modal `showLeadScoreHelp()` (seller.html) ให้ตรง

### Date parsing
[fetch_dashboard.py](dashboard/services/fetch_dashboard.py) มี `parse_date()` รองรับ:
- Excel serial date (เลข 4-5 หลัก)
- "d/m/yy" หรือ "d/m/yyyy" (รองรับ พ.ศ. แปลงเป็น ค.ศ. ถ้า year > 2500)

### Date filter (กรองเดือน / ช่วงวัน)
- **`index.html` หน้าหลัก = ช่วงวันที่ (จาก-ถึง ข้ามเดือนได้)** — แทน month/today filter เดิม:
  - State: `dfFrom`/`dfTo` ("YYYY-MM-DD") · `inRange(ds)` เช็ค dateIn อยู่ในช่วง · `ir = inRange`
  - `buildRangeMs()` = สร้าง summary+**sellers+teams** ของช่วง (รูปร่างเหมือน `monthlySummary[m]`) จาก **`dailyByMonth`/`dailyBySeller`** (lead/RJ/จอง/ปล่อย/ยอด รวมรายวัน) + **`followCases`** (ติดตาม) — bans/leadDist รวมรายเดือน (whole-month). cache ต่อ render (`_rmCache`)
  - **ทุกค่าที่โชว์ผูกกับช่วงวันที่**: KPI cards · scorecard(`buildDilMap`) · **ตารางรายเซลล์ (`_sval` ใช้ `ms.sellers` เสมอ ไม่เช็ค dfMonth)** · **team breakdown (`ms.teams`)** · team modal (filter `ir(b.date)`) · กราฟ (rangeDays) — แก้ bug เดิมที่ `_sval`/team อ่าน `dfMonth` (vestige=0) เลยโชว์รายปีเสมอ
  - **เป้า (target) รายเดือน → สเกล × `rangeMonthCount()`** (จำนวนเดือนที่ช่วงครอบ) เพราะ TARGETS ในชีตเป็นเป้า/เดือน (โอ๊ต 8, เฟิร์ส 12...)
  - **`daily_by_seller` รวม orphan/inactive ด้วย** (`_daily_names`) → เซลล์เก่ากรองตามช่วงวันได้ ไม่งั้นโชว์ 0
  - **กรองรายชื่อเซลล์ตามช่วง (`rangeActiveSellers()`)**: ใน `render()` มุมมองรวม (`canViewAll && !impersonate`) กรอง `sellers` ให้เหลือเฉพาะคนที่ **มีกิจกรรมในช่วงที่เลือก** (lead/จอง/ปิด/ยอด/ติดตาม จาก `ms.sellers` + คลิป `la.clips` + ไลฟ์ `la.sessions.hosts` filter `ir(date)`) → ทุกแท็บ (ภาพรวม/เซลล์/LEAD/ไลฟ์) ไม่โชว์เซลล์เก่าที่ไม่มีข้อมูลในช่วง. ดูคนเดียว/impersonate = ไม่กรอง (กันหน้าว่าง)
  - **`NON_SELLER_NAMES`** ([fetch_dashboard.py](dashboard/services/fetch_dashboard.py)) ตัดคำสถานะ (จอง/ส่งมอบ/คืนเคส/จ่ายใหม่/ยกเลิก/(ว่าง)/ติดตาม...) ออกจาก orphan sellers — กันคำที่กรอกผิดลงคอลัมน์ชื่อเซลล์โผล่เป็น "เซลล์เก่า"
  - `dfMonth=0` vestige (โค้ดเก่าอ้าง) · `setDf(m)` ตอนนี้ map เป็นช่วงวัน (กดบาร์เดือนในกราฟ → ทั้งเดือนนั้น)
  - vacant ไม่มีรายวัน → overview KPI ไม่ใช้ (มีแค่หน้า seller detail)
- _(เดิม `<input type="month">` + `dfMonth` 0/-1/1-12 — เปลี่ยนเป็นช่วงวันแล้ว)_
  - `seller.html` ใช้ `fMonth` (เดือน) + `fDateFrom`/`fDateTo` (ช่วงวัน, "YYYY-MM-DD") — mutually exclusive (เลือก month → ล้าง range, เลือก range → ล้าง month). UI มี 2 แถว: เดือน + ช่วงวัน
    - **กราฟอิงช่วงวันที่ (`buildRangeSeries()`)**: ≤45 วัน = รายวัน (label `d/m`) · >45 วัน = รายเดือนเฉพาะเดือนในช่วง — เลิก bug เดิมที่ `isDaily=fMonth>0` (fMonth=0 เสมอ) เลยตกไป else โชว์ 12 เดือนทั้งปีไม่อิง filter
    - **เป้าสเกลตามช่วง (`rangeMonthCount()`)**: header `เป้า = s.target × เดือนในช่วง` (เดือนละ 8 · ทั้งปี = ×เดือนในช่วง)
    - **รับ `?from=&to=` จาก URL**: ตอนต้นไฟล์ override `fDateFrom`/`fDateTo` ถ้ามี query — ใช้ตอนฝัง iframe ในแท็บ "เซลล์" ของ admin (`renderSeller` ส่ง `?from/to` เข้า iframe + ลิงก์เต็มจอ) ให้หน้าเซลล์อิงตัวกรองเดียวกับ admin
  - **index.html — `rangeActiveSellers()`** กรอง `sellers` ตามช่วง (ดูข้อด้านบน) · **notCalled panel** ("ยังไม่อัพเดท") ใช้ `ms.sellers[].notCalled` (นับจาก `followCases` ในช่วง ใน `buildRangeMs`) แทน `s.notCalled` รายปี · เป้า overview/team สเกล `× rangeMonthCount()` ครบ (1493/1575/2489/2495)
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

> **📋 ตาราง "รายงานรายเซลล์ (ละเอียด)"** (gate `canViewAll`) — ใต้ตาราง "สรุปรายเซลล์" · แสดง **ทุกเซลล์ (13 + ADMIN, กรอง `!s.inactive` ตัด orphan)** ตามรูปแบบรายงานในชีต. คอลัมน์: ลำดับ·เซลล์·จองทั้งหมด·รอผล·รอปล่อย·ปล่อย·%การจอง·Lead·RJ·เฉลี่ยรับ Lead/วัน·ไลฟ์·คลิป·Lead ไลฟ์ + footer รวม. ค่า lead/จอง/ปล่อย/RJ มาจาก **`monthlySummary` รวมตามเดือนในช่วง** (`_msSum` — เพราะ ADMIN/orphan ไม่อยู่ใน `dailyBySeller`→`buildRangeMs`/`_sval` ใช้ไม่ได้ · keys เป็น string '1'-'12' JS coerce เลขเข้าได้) + **รอผล/รอปล่อย จาก `D.bookingCases` นับตาม "แท็บเดือน" (`_tabMonth(b.sheetTab)` ∈ เดือนในช่วง) ไม่ใช่วันจอง** — เพราะเคส pipeline จองปลายเดือนก่อนแต่อยู่ในแท็บเดือนนี้ (ถ้ากรองด้วยวันจองจะตก) + live/clip จาก `liveActivity` · **Lead ไลฟ์ = `leadLive`** (lead ที่ channel col H มีคำว่า "LIVE" — เพิ่มใน m_sellers ทั้ง 3 จุด: configured/orphan/ADMIN). แถวกรอง `lead\|\|booking\|\|done\|\|rj > 0` · เรียงตาม (รอปล่อย+ปล่อย) ก่อน (ตรงกับสีแถว) แล้ว ปล่อย→รอปล่อย→จอง. **เคส ADMIN**: ดู `fetch_sales_by_month_tabs` (อ่านบล็อก ADMIN + ย้ายเคส col27='ADMIN' มาเป็น ADMIN) → ADMIN มี รอผล/รอปล่อย จริง

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

3. **🔔 กระดิ่งแจ้งเตือน (header, admin)** — `computeAdminAlerts()` + `openAlertsPanel()` (ข้างเมนูจัดการ มี badge จำนวน) · **แทน panel "ข้อมูลต้องเติม/แก้" เดิม** (`renderDataQualityPanel` ยังอยู่ในโค้ดแต่ไม่ render แล้ว — ตัดออกจาก LEAD tab มิ.ย.69)
   - เน้น **"เคสปล่อยไม่ลงวันปล่อย"** — เช็ค `releaseDatePrimary` (คอลัมน์หลัก X/W ว่าง แม้ extract เจอ V) · **ไม่กรองช่วง** (ไม่ใช้ `_inRangeStr` — เพราะ extract อาจดึงวันอนาคต/นอกช่วงทำให้เคสหลุด เช่น เข็มทอง release 12/6 แต่ X ว่าง) แต่ **เริ่มนับตั้งแต่ พ.ค.69** (`_ALERT_START` = 1 พ.ค. 2026 · กรองด้วยวันจอง — ตัด backlog ก่อนใช้ระบบ จาก ~93 เหลือไม่กี่เคส)
   - **เซลล์ใหม่/ยังไม่ตั้งทีม** (`s.inactive===true` + active ในช่วง `rangeActiveSellers` — orphan ไม่อยู่ใน config) → `openSellerConfigPanel`
   - **วันที่ปีผิด** (นอก 2020–2035 มักพิมพ์ 1969) · กรองตามวันจอง · กดแถว → `openBookingDetail(idx)`
   - **✏️ Inline edit วันที่ timeline** (เซ็น/ผล/ปล่อย) — ในหน้ารายละเอียดเคส (`openBookingDetail` → `_dateEditRow(label,val,col,idx,hint)`/`saveTimelineDate(idx,col)`) แต่ละแถวมี **`<input type=date>`** (แปลง d/m/yyyy ↔ YYYY-MM-DD ด้วย `_toISODate`/`_fromISODate`) + ปุ่มบันทึก → POST `/api/admin/update_release_date` (body `col`) → เขียนกลับชีตตรง cell. **col**: เซ็น=14(O) · ผล=19(T) · ปล่อย=`releaseCol`(23/21). **เอกสารครบ(18)/วันจอง อ่านอย่างเดียว**. ⚠ คอลัมน์ timeline ในชีตไม่สะอาด (col19 ผล แอดมินแทบไม่กรอก, col14 บางแถว='สด') แต่เขียนตรงที่ระบบอ่าน → consistent. ตำแหน่งมาจาก `bookingCases[].sheetTab`/`sheetRow`/`releaseCol` ที่ `fetch_sales_by_month_tabs` แนบไว้ (**col 28=tab name, col 29=แถวในชีต 1-based** ต่อท้าย flattened row · `releaseCol`=23(X พ.ค.+)/21(V เดือนก่อน) จาก `_release_col(r)`). optimistic อัปเดต local (mirror ตามทันรอบ sync ถัดไป) · `sheetTab` ว่าง → read-only
   - **มีทั้ง 2 หน้า**: `index.html` (แอดมิน) + **`seller.html` (เซลล์แก้เคสตัวเอง)** — seller.html มี banner "ปล่อยแล้วยังไม่ลงวันส่งมอบ" (เหนือ filter bar) ลิสต์เคส → กดเปิด `openBookingDetail` ลงวันได้เลย. เซลล์ส่ง `token` ใน body → endpoint เช็ค ownership (ชื่อที่ marker = ตัวเอง) ก่อนเขียน · `/me/` ใช้ session seller_name

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
| `admin_config` | (เดียวกับ employees) | **"ตั้งค่าแอดมิน"** | รายชื่อ LINE user_id ที่เป็นแอดมิน (เทเลเซลล์/ออฟฟิศ ที่ไม่ใช่เซลล์) — `ADMIN_USER_IDS` |

**OAuth scope**: `https://www.googleapis.com/auth/spreadsheets` (read+write — เปลี่ยนมาจาก readonly เพราะ admin ต้องเขียน config)

**Service account** ต้องมี Editor บน spreadsheet (เพื่อเขียน sheet sellers_config / schedule_config)

### ย้าย/เปลี่ยน spreadsheet ได้จากแอดมิน (override SHEET_CONFIG)
`SHEET_CONFIG` ใน [google_sheets.py](dashboard/services/google_sheets.py) เป็น **default (hardcode)**. Admin ย้ายไฟล์/tab ได้ผ่าน
panel **"📊 แหล่งข้อมูล (Sheets)"** → ปุ่ม **✏️ ย้าย/แก้ไขแหล่งข้อมูล** (ใช้ตอนขึ้นปีใหม่แล้วเปลี่ยนไฟล์ใหม่ — ไม่ต้องแก้โค้ด/deploy)
- **เลือกไฟล์/tab จาก dropdown (แบบ n8n — มิ.ย.69)**: `renderSheetsEdit()` ดึงรายชื่อไฟล์จาก `/api/admin/list_drive_sheets` (Drive API) → dropdown เลือกไฟล์ · เปลี่ยนไฟล์ → `__loadTabsFor()` ดึง tab จาก `/api/admin/list_tabs` → dropdown เลือก tab. **ไฟล์ใหม่ขึ้นปีใหม่ = แค่แชร์ไฟล์ให้ service account → กด "เช็คใหม่" → ไฟล์โผล่ในdropdown → เลือก** (ไม่ต้องก๊อป ID). ต้องมี scope `drive.metadata.readonly` (เพิ่มใน `_get_credentials`) + Drive API เปิดใน GCP project. ถ้าอ่านรายชื่อไฟล์ไม่ได้ → fallback เป็น text input (พิมพ์ ID เอง)
- เก็บ override ใน **Supabase table `sheet_config`** (cols: `key` PK, `spreadsheet_id`, `sheet_name`, `updated_at`)
- `load_sheet_config_overrides()` อ่านจาก Supabase แล้ว **mutate `SHEET_CONFIG` in-place** — เรียกที่ต้น `fetch_sheet()` (flag โหลดครั้งเดียว/process, admin บันทึก = `force=True`)
- บันทึก (`POST /api/admin/sheet_config`) = save Supabase → reload override → `invalidate_cache()` + เคลียร์ `_dash_cache` → ถ้า `USE_SUPABASE` จะ **re-sync mirror จากไฟล์ใหม่ทันที** (`sync_all_sheets_to_supabase`) ไม่งั้น dashboard เห็นข้อมูลเก่า
- ต้องมี Supabase ตั้งค่าแล้ว (`canEdit` = `is_configured()`); ไฟล์ใหม่ **service account ต้องมีสิทธิ์อ่านด้วย**
- SQL สร้างตาราง: `create table if not exists sheet_config (key text primary key, spreadsheet_id text, sheet_name text, updated_at timestamptz default now());`

### ⚡ Pre-compute dashboard (แก้ "ยิ่งข้อมูลเยอะยิ่งช้า")
แทนที่จะอ่าน 15k lead + aggregate สดทุกโหลด → **คำนวณล่วงหน้าเก็บผลไว้ คนเข้าเว็บอ่านผลสำเร็จรูป** (เร็วคงที่ ไม่ขึ้นกับจำนวนข้อมูล):
- `precompute_dashboard()` ([fetch_dashboard.py](dashboard/services/fetch_dashboard.py)) — คำนวณ `_compute_dashboard_data()` 1 ครั้ง → เก็บลง Supabase table **`dashboard_cache`** (1 แถว key='main', `data` jsonb)
- `fetch_dashboard_data()` อ่านเร็ว→ช้า: **in-memory (30s)** → **ผล pre-compute Supabase (`_PRECOMPUTE_TTL`=5นาที)** → คำนวณสด+เก็บ (fallback)
- รีเฟรชโดย: **`cron_tick`** (cron ยิงทุก 1 นาที — ถ้าผลเก่า **>180 วิ** → sync+precompute · sync ทุก ~3-4 นาที) + `cron_sync`. ใช้ cron tick ตัวเดียว ไม่ต้องสร้าง cron sync แยก.
  - **⚠️ บทเรียน (7 มิ.ย.69 server ล่ม)**: เคยตั้ง threshold = **45 วิ** (< tick 60s) → ทุก tick ทำ full sync (upsert leads 15k) ~1440 ครั้ง/วัน + ถ้า sync ก่อนยังไม่เสร็จใน 60s ตัวใหม่เริ่ม**ซ้อน** → Supabase/Vercel โหลดพุ่ง **ล่ม** (commit 977eeae). แก้กลับเป็น **180** (sync ทุก ~3-4 นาที ~360 ครั้ง/วัน เทียบของเดิม 270วิ ~288 ครั้ง). **ห้ามลดต่ำกว่า ~120** — แต่ละ sync หนัก (leads 15k jsonb ก้อนเดียว เสี่ยง statement timeout). อยากเร็วกว่านี้แบบปลอดภัย → ต้องแยก sync leads (หนัก) ออกจาก sales/bookings/live (เล็ก) ให้ความถี่ต่างกัน
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
- `fetch_sales_by_month_tabs()` — **default สำหรับ sales_reports** — อ่านยอดขายจากแท็บรายเดือน **`<เดือน>69` (ไม่เว้นวรรค)** ตรงๆ แทน "รวม sheet" (ที่ใช้สูตร REDUCE). แต่ละแท็บจัดกลุ่มตามเซลล์ด้วย marker **"ชื่อเซลล์ X"** ใน column B → ดึงบล็อกของแต่ละเซลล์ (ใต้ marker ถึง marker ถัดไป), เอาแถวที่ลำดับ(B)เป็นเลข+สถานะ(N)ไม่ว่าง, prepend ชื่อเซลล์เป็น col 0 (ตรง `SALES_COL` flattened เดิม). **match ชื่อกับ `ALL_SELLERS` (dynamic) + `{"ADMIN"}`** (อ่านบล็อก "ชื่อเซลล์ ADMIN" ด้วย) → เซลล์ใหม่เพิ่มเองอัตโนมัติ + ตัด marker ขยะ (A/ว่าง). **★ ย้ายเคส ADMIN ที่อยู่ใต้เซลล์อื่น**: ถ้าแถวมี `"ADMIN"` ในคอลัมน์ AB (idx 24–29) → set seller='ADMIN' (ตัดจากเซลล์เจ้าของบล็อก) — เคสที่แอดมิน/เทเลเซลล์ดูแลแต่บันทึกใต้เซลล์. ใช้ใน `fetch_all_sheets()` + `sync_all_sheets_to_supabase()`. Failsafe → `fetch_sheet("sales_reports")` ("รวม sheet")
- `fetch_bookings_by_month_tabs()` — **default สำหรับ bookings (จอง)** — อ่านจากแท็บ **"จอง/จบ \<เดือน\> 69"** (ไฟล์ bookings) แทน "รวม sheet" (เก่า ไม่อัปเดต). แท็บวาง **จอง(ซ้าย A-K) + จบ(ขวา) แยกกัน** — อ่านแค่ A-K ฝั่งจอง ซึ่งตรง `BOOKINGS_COL` เป๊ะ → `year_jongs` กรอง date เอง. **ชื่อแท็บมี "/" → ใช้ `values:batchGet`** (range เป็น query param กัน URL path พัง 404). ใช้ใน `fetch_all_sheets()` + sync. Failsafe → `fetch_sheet("bookings")`
- `fetch_live_by_month_tabs()` — **default สำหรับ live_sessions (ไลฟ์สด)** — อ่านจากแท็บ **"สรุปไลฟ์สด \<เดือนไทย\>"** (มี.ค./เม.ย./พ.ค./มิ.ย....) ในไฟล์ live แทน "รวม sheet" (สูตร REDUCE เดือนล่าสุด lag — เคย มิ.ย. มี 1 session ทั้งที่จริง 30). list tab → filter prefix `สรุปไลฟ์สด` → รวมทุกเดือน (ตัด header). โครงสร้างตรง `LIVE_COL` เป๊ะ (date/host_1-5/inbox/lead). ใช้ใน `fetch_all_sheets()` + sync. Failsafe → `fetch_sheet("live_sessions")`
- `fetch_leads_dedup()` — **ใช้แค่ใน `admin_diagnostics`** (debug page เพื่อดู dedup behavior). รวม "รวม sheet" + monthly tabs แล้ว dedup by `Code` — แถวที่ปรากฏหลังสุดชนะ. ไม่ใช้ใน user-facing dashboard อีกแล้ว.
- `get_leads_dedup_stats()` — คืน `{input_rows, output_rows, duplicates_removed, no_code}` ของการ dedup ครั้งล่าสุด — ใช้ใน `/api/admin/diagnostics` เพื่อให้ admin มองเห็นว่าตัดซ้ำไปกี่แถว (field `leads.dedup` ใน JSON response)
- `ensure_sheet_tab(sid, tab)` — สร้าง tab ใหม่ถ้าไม่มี
- `write_sheet(key, values)` — clear + write ทับทั้ง tab

### Sheet column gotchas — ต้องระวัง

**sales_reports** ([google_sheets.py](dashboard/services/google_sheets.py) `SALES_COL`):
- `car_release_date` — **`extract_release_date()`** ใน [fetch_dashboard.py](dashboard/services/fetch_dashboard.py) สแกนหลายคอลัมน์ **X(23)·W(22)·V(21)·U(20)** (พ.ค.+ เริ่ม X, เดือนก่อนเริ่ม W) เพราะ layout วันปล่อยย้ายตามเดือน
  - **2 รอบ**: รอบ 1 หาวันที่ "สะอาด" (ทั้งช่องเป็นวันที่) ก่อน → รอบ 2 ค่อย fallback ดึงวันที่ฝังในโน้ต (เช่น "รับ 16/5")
  - **ทำไมต้องสะอาดก่อน**: บางช่องเป็นโน้ตที่มีวันที่ปน เช่น W="นัดเซ็น 29/04/69" ทั้งที่ X มีวันปล่อยจริง "19/5" สะอาดอยู่ — ถ้าหยิบโน้ตก่อนจะนับผิดเดือน (เคสจอง เม.ย. ปล่อย พ.ค. หลุดไปเมษา)
  - คืน '' ถ้าไม่เจอวันที่เลย → caller fallback ไปวันจอง (`get_done_month`)
  - **`release_date_primary(r)`** (คู่กับ `extract_release_date`) — วันปล่อยจาก **"คอลัมน์หลัก" เท่านั้น**: พ.ค.+ = X(23) (รับถ้ามี pattern วันที่ `\d+/\d+`), เดือนก่อน = `extract_release_date` (layout เก่าวันปล่อยอยู่ V). ใส่ใน `bookingCases[].releaseDatePrimary`. **ใช้ในกระดิ่งแจ้งเตือน + data quality panel** จับ "เคสปล่อยแต่ X ว่าง" — แม้ `extract` จะ fallback เจอวันที่ใน V/โน้ต (เช่น กิตติมา: X ว่าง แต่ V=2/6 → `releaseDate`=2/6 แต่ `releaseDatePrimary`='' → ถูกจับ). frontend มี fallback `('releaseDatePrimary' in b)?...:releaseDate` กันช่วง deploy ที่ cache ยังไม่มีฟิลด์
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
2. **Auto** — cron-job.org ยิง `/api/cron/tick?secret=xxx` ทุก 1 นาที → `cron_tick` ส่ง **followup "ตามด่วน" รายเซลล์ ตามตารางในชีต "ตั้งเวลาส่ง"** (default 09:00/13:00 · ข้อความธรรมดา · `build_followup_messages`) — **schedule sheet (เดิมคุม Flex) ตอนนี้คุม followup**: ถึงเวลาแถว enabled → ส่งตาม `test_target`/`sellers` ของแถวนั้น. manual `/api/admin/send_line` ยังใช้ Flex ได้ (`build_seller_flex`)

### Schedule format (sheet "ตั้งเวลาส่ง")
```
เวลา (HH:MM) | วัน (* / 1-5 / 0,6) | เซลล์ (* / "โอ๊ต,เก้า") | test_target | enabled (TRUE/FALSE) | ป้ายชื่อ
09:00        | 1-5                | *                       |             | TRUE                 | เช้าวันทำการ
13:00        | *                  | *                       |             | TRUE                 | เที่ยง
```
- วัน: 0=อาทิตย์, 1=จันทร์, ..., 6=เสาร์
- test_target ใส่ user_id = ส่งเข้า user นั้นแทน (test mode) / ว่าง = ส่งจริงไปทุกเซลล์

## Conventions

- **⭐ กฎเหล็ก: ทุกตาราง/การ์ด/กราฟ/modal/พาเนล ในหน้ารวม (`index.html`) ต้อง "กรองตามตัวกรองวันที่ด้านบนเสมอ"** — เพิ่มอะไรใหม่ก็ต้องผูกกับช่วงวันที่ (`dfFrom`/`dfTo`)
  - ใช้ `ir(ds)` / `inRange(ds)` เช็คว่า date string อยู่ในช่วงไหม · หรือ `buildRangeMs()` (มี summary+sellers+teams ของช่วง) · หรือ `rangeDays()` (list วัน/เดือนในช่วง)
  - **ห้ามใช้ `dfMonth`** — เป็น vestige (=0 ตลอด) โค้ดเก่าที่ยังเช็ค `dfMonth > 0` = bug โชว์รายปีเสมอ (ดู `_sval`/charts/modal ที่แก้ไปแล้ว)
  - เป้า (target) รายเดือน → คูณ `rangeMonthCount()` · เคสที่วันที่ปีพิมพ์ผิด → กรองด้วยวัน/เดือน (ดู `renderDataQualityPanel`)
  - ดู section "Date filter" สำหรับรายละเอียด
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

1. **env vars บน Vercel dashboard** (Settings → Environment Variables) — **ตั้งแค่ 7 SECRET เท่านั้น** (Vercel จำกัด ~15 ตัว). ค่าที่ไม่ลับ inline เป็น default ใน [settings.py](oxlet/settings.py) แล้ว → ไม่ต้องตั้งบน Vercel:
   - **7 SECRET (จำเป็น)**: `GOOGLE_PRIVATE_KEY`, `DJANGO_SECRET_KEY`, `OXLET_ADMIN_PASSWORD`, `LINE_CHANNEL_ACCESS_TOKEN`, `CRON_SECRET`, `GEMINI_API_KEY`, `SUPABASE_SECRET_KEY`
   - **LINE Login (PDPA)**: `LINE_LOGIN_CHANNEL_ID`, `LINE_LOGIN_CHANNEL_SECRET` (จาก LINE Login channel) + ตั้ง Callback URL ใน channel = `https://saleforce-oxletauto.vercel.app/auth/line/callback` (ตรงกับ `LINE_LOGIN_CALLBACK`)
   - **inline แล้ว (ไม่ต้องตั้ง)**: `GOOGLE_SERVICE_ACCOUNT_EMAIL`, `SUPABASE_URL`, `USE_SUPABASE`, `GEMINI_MODEL`, `FINANCE_TEST_LINE_ID`, `OXLET_ADMIN_USER`, `OXLET_SELLER_PASSWORD` (รหัสรวม login = OXletauto55555), `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` — แก้ได้ใน settings.py
   - **ตัวเลือก**: `DEBUG` (default=False อยู่แล้ว ไม่ต้องตั้งก็ปลอดภัย)
   - **เลิกใช้แล้ว**: `GMAIL_APP_PASSWORD`, `EMAIL_*`, `APPROVAL_NOTIFY_EMAIL`, `SITE_URL` (ถอดระบบสมัครสมาชิก+เมลออกแล้ว มิ.ย.69)
   - **⚠️ `.env` ถูก gitignored แล้ว (ไม่ commit)** — ประวัติ git ถูกล้าง .env ออกหมดแล้ว (filter-repo + force-push มิ.ย.69). ห้ามเอา .env กลับเข้า git อีก

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
