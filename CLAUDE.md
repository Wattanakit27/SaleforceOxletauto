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
- **Mirror/cache**: Supabase (PostgREST ผ่าน `requests` — ไม่มี SDK) เก็บ mirror ของ sheets + pre-compute dashboard + kv heartbeat + ฟอร์ม finance/loan
- **AI**: Google Gemini (REST ผ่าน `requests`) — (1) insights โค้ชเซลล์/พยากรณ์ยอด (2) OCR สแกนเอกสาร finance/loan → กรอกฟอร์มอัตโนมัติ
- **Cron**: External scheduler (**n8n** — เปลี่ยนจาก cron-job.org) ยิงเข้า `/api/cron/tick` ทุก 1 นาที
- **Deps** ([requirements.txt](requirements.txt)): มีแค่ Django, google-auth, requests, python-dotenv, whitenoise — **ไม่มี SDK ของ Supabase/Gemini/LINE** (เรียก REST ผ่าน `requests` หมด)

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
    line_notify.py       # Flex builder + push + schedule loader + finance/loan Flex
    supabase_client.py   # PostgREST client — mirror sheets (sheet_cache), dashboard_cache, kv, finance/loan tables
    gemini_insights.py   # Gemini: โค้ชเซลล์ (analyze_seller) + พยากรณ์ยอด (forecast_narrative) · cache 30 นาที
    gemini_ocr.py        # Gemini vision OCR: สแกนเอกสาร finance/loan → ดึง field (JSON schema mode)
    helpers.py
  templates/dashboard/
    index.html           # หน้า dashboard หลัก (admin / ผู้บริหาร เห็นทั้งหมด, อื่นๆ เห็นเฉพาะตัวเอง)
    login.html           # /login/ — admin login (user+password) + ปุ่ม LINE Login
    magic_link.html      # /u/<token>/ — set cookie แล้ว redirect ไป /dashboard/
    seller.html          # /s/<token>/ — หน้าส่วนตัวของเซลล์ (filter+charts+KPI+lead detail modal + ฟอร์ม finance/loan + สแกนเอกสาร)
  static/dashboard/      # CSS + image (โลโก้บริษัท)
README.md                # เอกสารประกอบ (overview)
```

## รันโปรเจกต์ (Dev)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py runserver
```

- **⚠️ รัน dev บนเครื่องต้องตั้ง env: `DB_HOST=` (ว่าง=SQLite ไม่ต้องมี Postgres) + `DEBUG=True`** — ไม่งั้นมันอ่าน `.env` (DEBUG=False + DB_HOST=127.0.0.1 Postgres) → พังถ้าไม่มี Postgres/ต้อง https. **ไฟล์ [run_dev.bat](run_dev.bat) ตั้งให้แล้ว** — ดับเบิลคลิก/พิมพ์ `run_dev.bat` พอ (รันที่ 127.0.0.1:8000)
- Login dev: admin/รหัส (จาก `.env` `OXLET_ADMIN_PASSWORD`) ที่ `/login/?bg=1`
- **แก้ template (index.html/seller.html) ต้องรีสตาร์ท server เสมอ** (โปรเจกต์ cache template แม้ DEBUG) + บอกผู้ใช้ Ctrl+F5
- ไม่ต้องรัน `migrate` สำหรับ sales — ไม่มี local DB. Session ใช้ signed-cookie backend (แต่ cars/ tracking ต้อง migrate + DB)

## URL Routes

### หน้าเว็บ

| URL | View | สิทธิ์ |
|---|---|---|
| `/` | `index` | redirect → `/dashboard/` |
| `/dashboard/` | `dashboard_page` | **ต้อง login (admin/ผู้บริหาร)** — เซลล์ → redirect ไป `/me/` · ไม่ login → `/login/` |
| `/admin/` | `admin_page` | **ต้อง login admin** เท่านั้น (ไม่งั้น → `/login/`) |
| `/me/` | `me_dashboard` | หน้าส่วนตัวของเซลล์ที่ login — ดึง `seller_name` จาก session, render `seller.html` (data แยกเฉพาะตัว) |
| `/login/` | `login_view` | GET = หน้า login (เหลือปุ่ม **LINE Login** อย่างเดียว) · POST = admin user/pass (env, break-glass — ฟอร์มซ่อนหลัง `?bg=1`). **ตัด path "LINE user_id + รหัสรวม" ออกแล้ว (มิ.ย.69)** กันคนนอก |
| `/logout/` | `logout_view` | clear session → กลับ `/login/` |
| `/u/<token>/` | `magic_link` | login เซลล์ผ่าน LINE user_id (จาก employees sheet) |
| `/s/<token>/` | `seller_dashboard` | หน้าส่วนตัวของเซลล์ — token จาก [seller_tokens.py](dashboard/services/seller_tokens.py) หรือ LINE user_id · **ต้อง login ก่อน (PDPA)**: ไม่มี session → redirect `/login/?next=` · เซลล์ดูได้เฉพาะของตัวเอง (ไม่งั้น → `/me/`) · admin/exec ดูได้ทุกคน |

### API

| URL | View | ใช้ทำอะไร |
|---|---|---|
| `/api/dashboard` | `api_dashboard` | JSON ของ full dashboard data |
| `/api/auth?token=` | `api_auth` | ตรวจ LINE user_id กับ employees sheet |
| `/api/admin/send_line` | `admin_send_line` | admin: GET=preview, POST=ส่ง Flex ทันที |
| `/api/admin/send_followup` | `admin_send_followup` | admin POST: ส่งข้อความ "ตามด่วน" (plain text เฟส 2) เดี๋ยวนี้ — logic เดียวกับ cron 09:00/13:00 (`build_followup_messages`). body `{test, target_user_id?, sellers?}` · test=ส่งเข้า target_user_id · ปุ่ม "🚀 ส่งทันที" รองรับกลุ่ม ADMIN (เทเลเซลล์ 5 คน) |
| `/api/admin/export_leadscore` | `admin_export_leadscore` | admin POST: เขียนคะแนนเซลล์ (diligence) ลงชีต tab "leadscore" — body `{month?, year?}` (default เดือน/ปีนี้) → `export_leadscore_to_sheet()`. เมนูจัดการ "ส่งคะแนนเข้าชีต" |
| `/api/admin/seller_config` | `admin_seller_config` | admin: GET=อ่าน config, POST=บันทึก (เขียน sheet "ตั้งค่าเซลล์") — รวมคอลัมน์ `is_admin` (เซลล์แอดมิน) |
| `/api/admin/admin_config` | `admin_admin_config` | admin: GET=รายชื่อแอดมิน(ไอดี)+employees, POST=บันทึก (เขียน sheet "ตั้งค่าแอดมิน") — เทเลเซลล์/ออฟฟิศที่ไม่ใช่เซลล์ |
| `/api/admin/schedule_config` | `admin_schedule_config` | admin: GET=อ่านตาราง, POST=บันทึก (เขียน sheet "ตั้งเวลาส่ง") |
| `/api/admin/onhand_config` | `admin_onhand_config` | admin: GET=อ่าน ONHAND (รถในมือรายสัปดาห์), POST=บันทึก (เขียน sheet "ONHAND รายสัปดาห์") — body `{ym,week,rows}` · ตัดรอบวันพฤหัส |
| `/api/admin/seller_flags` | `admin_seller_flags` | admin: GET=อ่านสีโฟกัสเซลล์, POST=บันทึก (เขียน sheet "โฟกัสเซลล์") — `{seller:'y'\|'r'}` ระบายทั้งแถวในตารางสรุป |
| `/api/admin/diagnostics` | `admin_diagnostics` | admin: ตรวจ log การกรองข้อมูล (เคสที่หาย, วันที่พัง, สถานะว่าง, "รอปล่อย" cases) |
| `/api/admin/sheets_status` | `admin_sheets_status` | admin: เช็คสด 6 แหล่งข้อมูล + tab รายเดือน + sheet ตั้งค่า (panel "📊 แหล่งข้อมูล" แบบ n8n) |
| `/api/admin/sheet_config` | `admin_sheet_config` | admin POST: ย้าย spreadsheet/tab ของแต่ละแหล่ง (เก็บ Supabase `sheet_config`) — ใช้ตอนขึ้นปีใหม่/ย้ายไฟล์ |
| `/api/admin/list_drive_sheets` | `admin_list_drive_sheets` | admin GET: รายชื่อไฟล์ Google Sheets ที่ service account เข้าถึงได้ (Drive API) — ทำ dropdown เลือกไฟล์แบบ n8n |
| `/api/admin/list_tabs` | `admin_list_tabs` | admin GET `?sid=`: รายชื่อ tab ของ spreadsheet — ทำ dropdown เลือก tab |
| `/api/admin/system_health` | `admin_system_health` | admin GET: สถานะระบบ — อายุ sync, จำนวนข้อมูล, Supabase/LINE, + เช็กข้อมูลผิดอัตโนมัติ (sync ค้าง/วันนี้ไม่มี lead/lead=0) → ให้แอดมินเช็คเองโดยไม่ต้องมี dev |
| `/api/admin/refresh_data` | `admin_refresh_data` | admin POST: สั่ง sync + precompute เดี๋ยวนี้ (ปุ่มรีเฟรชในหน้าสถานะระบบ) — คำนวณสดจาก Google ~10 วิ |
| `/api/admin/trends` | `admin_trends` | admin GET: JSON เทรนด์ followup (`FollowupLog` รายวัน + `SellerWeekly` รายสัปดาห์ + `rounds`) — endpoint สำรอง (หน้า dashboard ฝัง inline ผ่าน `trends_json` context แล้ว · ดู section "เก็บสถิติ followup + เทรนด์") |
| `/api/admin/report_config` | `admin_report_config` | admin: GET=อ่าน, POST=บันทึก config "รายงานเข้าไลน์รายวัน" (`{enabled,time,mode,test_id,group_id}` · เก็บ KVStore `report_line_config`) — เมนูจัดการ "รายงานเข้าไลน์" (ดู section "รายงานเข้าไลน์") |
| `/api/admin/report_test` | `admin_report_test` | admin POST `{target?}`: แคปตารางรายงาน (Playwright) → ส่งรูปเข้า LINE เดี๋ยวนี้ (ปุ่ม "ส่งทดสอบ") · ⚠️ ได้จริงเฉพาะ prod (LINE ต้องดึงรูปจาก URL https สาธารณะ) |
| `/api/admin/line_group_name` | `admin_line_group_name` | admin POST `{id}`: ดึงชื่อกลุ่ม LINE จาก group id (LINE group summary API · บอทต้องอยู่ในกลุ่ม) → ปุ่ม "ตรวจชื่อ" ในพาเนลรายงาน (ยืนยันว่า id คือกลุ่มไหน) |
| `/api/admin/line_groups` | `admin_line_groups` | admin GET: รายชื่อกลุ่ม LINE ที่บอทรู้จัก (สะสมจาก webhook · KVStore `line_groups`) → dropdown เลือกกลุ่มในพาเนลรายงาน |
| `/api/line/webhook` | `line_webhook` | **public** (csrf_exempt) — LINE Messaging API webhook · จับ `groupId`+ชื่อ ตอนบอทได้ event จากกลุ่ม (join/message) → เก็บ `line_groups` (ยืนยัน signature ถ้ามี `LINE_CHANNEL_SECRET`) · **ต้อง register URL นี้ใน LINE Console** (Messaging API → Webhook URL = `SITE_URL/api/line/webhook` · เปิด Use webhook) |
| `/api/line/group_ingest` | `line_group_ingest` | **public** (csrf_exempt · auth `?secret=CRON_SECRET` / header `X-Cron-Secret`) — รับ group event จาก **n8n** (กรณี n8n เป็นตัวรับ LINE webhook แล้ว forward มา) → เก็บ `line_groups` เดียวกับ webhook · body ยืดหยุ่น (LINE raw `{events:[...]}` / `{groupId,groupName?}` / list) · คืน `{ok,count,groups}` |
| `/api/admin/update_release_date` | `update_release_date` | **admin (session) หรือเซลล์ (token/session + ownership)** POST: inline edit วันที่/สถานะ เขียนกลับชีตยอดขายตรงเซลล์ — body `{tab,row,col(2\|13\|14\|18\|19\|20\|21\|23),value,token?}` → `update_release_date()` PUT cell — **2=วันจอง · 13=N สถานะเคส (จอง/จอง(ซื้อสด)/รอเซ็นต์/รอผล/รอปล่อย/ปล่อย/รีเจ็ก · validate ตัด (ซื้อสด) แล้วต้องเป็น 1 ใน 6) · 14=เซ็น · 18=เอกสาร · 19/20=ผล · 21/23=ปล่อย**. เซลล์แก้ได้เฉพาะเคสตัวเอง (เช็คชื่อที่ marker ของแถว = `cell(r,0)`). ใช้จาก `saveReleaseDate`/`saveTimelineDate`/`saveCaseStatus` (index.html แอดมิน + seller.html เซลล์ · modal เคสจองมี dropdown สถานะ + แก้วันที่) |
| `/api/seller/update_note` | `update_lead_note` | เซลล์ (token) เขียนกลับ Google Sheet จาก lead detail — รับ `field` (S=`fill_sheet_note` / Z=`customer_status` / N=`call_proof`) + `value` (back-compat: `note`) → header-aware + ตรวจ ownership |
| `/api/seller/scan_doc` | `scan_doc` | **ต้อง login (any)** POST: รับรูปเอกสาร (base64, ≤8MB) + `form` (`finance`\|`loan`) → Gemini OCR (`gemini_ocr.extract_finance_fields`/`extract_loan_fields`) → คืน `{ok, fields}` ให้ฟอร์มกรอกอัตโนมัติ (ฉบับร่างให้เซลล์ตรวจก่อนส่ง) |
| `/api/seller/finance_check` | `finance_check_submit` | เซลล์ (token) POST: ส่งฟอร์ม "เช็คไฟแนนซ์ก่อนเซ็น" → สร้าง Flex (`build_finance_check_flex`) push เข้า `FINANCE_TEST_LINE_ID` (ช่วง test) + เก็บ Supabase `finance_checks` (best-effort) |
| `/api/seller/loan_submit` | `loan_submit` | เซลล์ (token) POST: ส่งฟอร์มขอสินเชื่อ → สร้าง Flex (`build_loan_flex`) push เข้า `FINANCE_TEST_LINE_ID` + เก็บ Supabase `loan_applications` (best-effort) |
| `/api/insights/seller` | `insights_seller` | **ต้อง login (any)** POST `{seller, stats}` → Gemini โค้ชเซลล์ (`gemini_insights.analyze_seller`) คืน `{ok, analysis}` (cache 30 นาที) |
| `/api/insights/forecast` | `insights_forecast` | **admin/exec** POST `{summary}` → Gemini อธิบายเทรนด์ยอด+ปัจจัยตลาด (`gemini_insights.forecast_narrative`) คืน `{ok, narrative}` |
| `/api/cron/sync` | `cron_sync` | public (`?secret=xxx`) — sync sheets → Supabase `sheet_cache` + precompute dashboard (cron tick ตัวเดียวก็พอ · นี่เป็น endpoint แยกสำรอง) |
| `/api/cron/send_line` | `cron_send_line` | public (`?secret=xxx`) — ส่ง Flex แบบ one-shot, manual params |
| `/api/cron/tick` | `cron_tick` | public (`?secret=xxx`) — (1) sync mirror+precompute **ทุก ~3-4 นาที** (ผลเก่า >180วิ · ห้ามลดต่ำ — ดู "บทเรียน server ล่ม") (2) ส่งแจ้งเตือน **"ตามด่วน" รายเซลล์ ตามเวลาในชีต "ตั้งเวลาส่ง"** (default 09:00/13:00 · แก้เวลา/ผู้รับ/test ในหน้า "ตารางเวลา (Auto)") — cron อ่าน `load_schedules`+`schedule_matches_now` แล้วยิง `build_followup_messages` (3) เขียน heartbeat `cron_tick` + followup log `cron_followup` (Supabase kv) → หน้าสถานะระบบโชว์ "cron ทำงานล่าสุด" |

## Roles (สิทธิ์ผู้ใช้)

| Role | position | สมัครได้ในชื่อ | ทำได้ | UI badge |
|------|---------|----|------|----------|
| **แอดมินสูงสุด** | `admin` | "แอดมินสูงสุด" | เห็นทุกอย่าง + 🚗 Lead รถ + 📋 เคสจอง + impersonate + ปุ่ม 📋 LINE ID / 📤 LINE Flex / 🎯 ตั้งเป้า | 👑 Admin (อำพัน) |
| **ผู้บริหาร (ยุบเข้า admin มิ.ย.69)** | `executive`/`ผู้บริหาร`/`manager`/`exec` → **normalize เป็น `admin` ตอน login** | "ผู้บริหาร" (ในชีต) | = admin เต็มตัว (เครื่องมือ admin ครบ + รับ Overview Flex) | 👑 Admin |
| **เซลล์** | `seller` / อื่นๆ | "เซลล์" | เห็นเฉพาะตัวเอง (ไม่เห็น Analytics tables) — login แล้ว → `/me/` | 👤 ชื่อเล่น (น้ำเงิน) |

**(มิ.ย.69 ยุบ "ผู้บริหาร" → admin)** ใน [index.html](dashboard/templates/dashboard/index.html) `isAdmin`=`position==='admin'` **หรือ exec-type (executive/ผู้บริหาร/manager/exec)** · `isExecutive`=`false` (เลิกใช้ คงตัวแปรกัน ref เก่า) · `canViewAll`=`isAdmin`. backend `_login_with_line_user_id` normalize exec-position → `"admin"`. **สรุปตามด่วน (ทีม)** [ข้อความ followup ตัวเดิม ไม่ใช่ Flex แยก] — schedule ติ๊ก `include_executive` → cron ส่งสรุปทีมให้แอดมิน (`ADMIN_USER_IDS + SUPER_ADMIN_IDS`) เพิ่มจากเทเลเซลล์ · เลิกพึ่ง env `EXECUTIVE_USER_IDS` · `build_overview_flex` เลิกใช้. ตาราง Lead-by-Car/Released-Cars ห่อ `if (canViewAll)`

**⚠️ บังคับ login ทุกหน้า (ไม่มี default test user แล้ว)** — `dashboard_page`/`admin_page`/`api_dashboard` เช็ค session ก่อนเสมอ ([views.py](dashboard/views.py) helper `_session_user`/`_can_view_all`/`_is_admin`). เซลล์ที่เผลอเข้า `/dashboard/` → redirect `/me/` (กันเปิด DevTools เห็น data รวมของทุกคน)

**Login (เหลือ LINE Login อย่างเดียว — มิ.ย.69 ตัดรหัสรวมออกกันคนนอก)** — ทุกทางเก็บ session `oxlet_user = {user_id, nickname, display_name, position, seller_name?}`:
0. **ช่องทางเดียวสำหรับผู้ใช้ทั่วไป (PDPA): LINE Login (OAuth)** — ปุ่ม "เข้าสู่ระบบด้วย LINE" → `/auth/line/start` (redirect ไป LINE authorize, state ใน session) → `/auth/line/callback` แลก code→token→ดึง LINE userId (ยืนยันแล้ว) → `_login_with_line_user_id()` หา employee + set session (หมดอายุ 14 วัน) → exec/admin ไป `/dashboard/`, เซลล์ไป `/me/` (อิง session ไม่ใช่ token). `SUPER_ADMIN_IDS` login ได้แม้ไม่มีใน employees. ต้องตั้ง `LINE_LOGIN_CHANNEL_ID`/`LINE_LOGIN_CHANNEL_SECRET` (env) + Callback URL ใน LINE Login channel = `LINE_LOGIN_CALLBACK`
   - **★ state เก็บฝั่งเซิร์ฟเวอร์ (ก.ค.69 · แก้บั๊ก "state ไม่ตรง กดสองรอบ" บนมือถือ Safari)**: `/start` เก็บ state ใน **KVStore `line_oauth:<state>`** (`cache_store` · single-use + TTL 10 นาที) เป็นตัวหลัก + คุกกี้ session เป็น fallback — เพราะ Safari/WebKit ทิ้ง `Set-Cookie` ที่ติดมากับ 302 redirect ข้ามเว็บไป LINE (signed_cookies เก็บ state ในคุกกี้ล้วนๆ → รอบแรกหาย) · ตรวจ state จากที่เก็บฝั่งเซิร์ฟเวอร์ก่อน else คุกกี้ → **ผ่านรอบเดียวทุกเบราว์เซอร์** · DB ล่ม = fallback คุกกี้เดิม (ไม่พัง)
   - **★ helper `_render_login()`**: ทุกจุด render `login.html` (start/callback ทุก error path) ใช้ helper นี้ → ส่ง `line_login`/`show_breakglass` ครบเสมอ · **กันบั๊กเดิมที่ error path ไม่ส่ง `line_login` → หน้าโชว์ "ยังไม่ได้ตั้งค่า LINE Login" หลอก + ซ่อนปุ่ม LINE + กางฟอร์มสำรอง** (ทั้งที่ env ตั้งไว้จริง)
1. **~~LINE user_id + รหัสรวม~~ (ถอดออกแล้ว มิ.ย.69)** — รหัสรวม (`OXLET_SELLER_PASSWORD`) เป็นช่องโหว่ให้คนนอกเข้าได้ → ลบ path ออกจาก `login_view` + ฟอร์มออกจาก login.html. `OXLET_SELLER_PASSWORD` ไม่ถูกใช้แล้ว (ยังประกาศใน settings.py แต่ dead). เซลล์เข้าผ่าน LINE Login (ข้อ 0) หรือลิงก์ตรง (ข้อ 3)
2. **แอดมินระบบ (สำรอง/break-glass)** — username/password จาก env `OXLET_ADMIN_USER` / `OXLET_ADMIN_PASSWORD` · **ฟอร์มซ่อนแล้ว** — โผล่เฉพาะเปิด `/login/?bg=1` (หรือเมื่อยังไม่ได้ตั้ง LINE Login) · backend ยังรับ POST username/password เสมอ (กันล็อกเอาท์ตัวเองถ้า LINE พัง)
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

#### 👑 แอดมินจาก LINE user_id (3 ทาง — แก้ได้เองในแดชบอร์ด เพราะคนเป็นแอดมินเปลี่ยนบ่อย)
ตอน login ด้วย LINE user_id (`login_view` LINE branch + `_login_with_line_user_id` ทาง LINE Login OAuth) → ได้ `position="admin"` ถ้าเข้าเงื่อนไขข้อใดข้อหนึ่ง (เรียก `refresh_from_sheet()` + `load_admin_user_ids()` ก่อนเช็ค) — **ทั้ง 3 แบบยังนับเป็นเซลล์ปกติในสถิติ** (ยอดมาจากชีต ไม่ขึ้นกับ role):

**1. เซลล์แอดมิน** — เซลล์ใน TEAMS ที่ติ๊ก "แอดมิน":
- คอลัมน์ D `is_admin` ในชีต **"ตั้งค่าเซลล์"** (`SELLER_CONFIG_COL.is_admin=3`) = `TRUE`/ว่าง → `refresh_from_sheet()` สร้าง set **`ADMIN_SELLERS`**
- จัดการ: ปุ่ม **🎯 ตั้งเป้า/ทีม** → checkbox 👑 ต่อเซลล์ (`admin_seller_config`: GET ส่ง `is_admin`, POST เขียน 4 คอลัมน์)

**2. แอดมินไอดี (เทเลเซลล์/ออฟฟิศ ที่ไม่ใช่เซลล์ใน TEAMS)** — รายชื่อ LINE user_id ตรงๆ:
- ชีต **"ตั้งค่าแอดมิน"** (`SHEET_CONFIG["admin_config"]`, cols: LINE user_id | ชื่อ | หมายเหตุ) → `load_admin_user_ids()` สร้าง set **`ADMIN_USER_IDS`** ([constants.py](dashboard/services/constants.py))
- จัดการ: ปุ่ม **👑 จัดการแอดมิน** (เมนูจัดการ) → เลือกจาก employees หรือวาง user_id → เพิ่ม/ลบ (`admin_admin_config`: GET ส่ง admins+employees, POST เขียนชีต) · แก้ในชีตตรงๆ ก็ได้
- ใช้เมื่อแอดมิน**ไม่ได้อยู่ใน 13 เซลล์** (เช่น ทีมโทร/ออฟฟิศ) — checkbox ในตั้งค่าเซลล์จะไม่มีให้ติ๊ก
- **⚠️ แยกเทเลเซลล์ออกจากแอดมิน (มิ.ย.69)**: เทเลเซลล์ (ทีมโทร) ย้ายไปชีตใหม่ **"ตั้งค่าเทเลเซลล์"** (`SHEET_CONFIG["tele_config"]`) → set **`TELE_USER_IDS`** (`load_tele_user_ids()` · จัดการผ่านปุ่ม **📞 จัดการเทเลเซลล์** / `admin_tele_config`). **`ADMIN_USER_IDS` (ชีตตั้งค่าแอดมิน) = สิทธิ์แอดมินอย่างเดียว** · **`TELE_USER_IDS` = ทีมโทร (เคสรวมเป็น seller "ADMIN" + ผู้รับ followup กลุ่ม ADMIN) ไม่ได้สิทธิ์แอดมิน**
  - **precedence: อยู่ทั้ง 2 ลิสต์ → แอดมินชนะ** — login: ถ้าเป็นแอดมิน (ADMIN_USER_IDS/SUPER_ADMIN_IDS/ADMIN_SELLERS) → `/dashboard/` · ถ้าเป็นเทเลเซลล์ล้วน (ไม่ใช่แอดมิน) → `/s/<id>/` (หน้ารวม ADMIN) · เซลล์ทั่วไป → `/me/`
  - ที่ใช้ `TELE_USER_IDS` (ไม่ใช่ ADMIN_USER_IDS แล้ว): `seller_from_token()`, `sellerTokens["ADMIN"]`, `build_followup_messages` admin_recip, `admin_send_followup`
- **"ADMIN" seller = ศูนย์รวมเทเลเซลล์**: เคสที่ลงชื่อเซลล์ = "ADMIN" ในชีต ถูกรวมเป็น seller ชื่อ "ADMIN" (team="ADMIN"). ไอดีเทเลเซลล์ใน `TELE_USER_IDS` → `seller_from_token()` map เป็น "ADMIN" → เปิด `/s/<id>/` เห็นหน้ารวมเทเลเซลล์ (`fetch_seller_stats("ADMIN")`). dropdown แท็บเซลล์ใช้ `sellerTokens["ADMIN"]` = ไอดีเทเลเซลล์คนแรก (ตั้งใน [fetch_dashboard.py](dashboard/services/fetch_dashboard.py))
  - **⚠️ ชื่อที่แสดง (มิ.ย.69)**: key ภายในยังเป็น **"ADMIN"** (ตรงกับชีต — อย่าเปลี่ยน) แต่ **UI โชว์เป็น "เทเลเซลล์"** ทุกที่ (กันสับสนกับบทบาทแอดมิน position="admin"). ใช้ helper `sname(n)` (`n==='ADMIN'?'เทเลเซลล์':n`) ใน [index.html](dashboard/templates/dashboard/index.html) + [seller.html](dashboard/templates/dashboard/seller.html) ตอน render ชื่อเซลล์ (ตาราง/leaderboard/dropdown/team card) · Python `build_followup_messages` ก็ใช้ "เทเลเซลล์" ในข้อความ LINE. **value/onclick ยังส่ง "ADMIN"** (filter/lookup ใช้ key เดิม) — เปลี่ยนแค่ข้อความที่ตา user เห็น. เพิ่ม render ชื่อเซลล์ใหม่ → ห่อด้วย `sname()` (ยกเว้นช่อง input แก้ config ที่ต้องคงค่า key)
- **followup overview (สรุปทีมใน LINE)**: นอกจาก "ต้องตามรวม/ดีลค้าง" เพิ่ม 2 ตัวเลขภาพรวม + รายเซลล์: **ยังไม่โทร** (updateCount=0) · **ยังไม่ใส่สถานะ** (Z ว่าง) — นับจากเคส active (ตัด skip/booked). _(เอา "ค้างเกิน 7 วัน" ออก ก.ค.69 — วัดจาก timestamp อัปเดต แยก "ตันจริง" กับ "ลืมอัพ" ไม่ได้)_ ไม่ใช้อิโมจิ คั่นด้วย `-` (ดู `build_followup_messages` ใน [fetch_dashboard.py](dashboard/services/fetch_dashboard.py))

**3. แอดมินสูงสุด hardcode (break-glass)** — set **`SUPER_ADMIN_IDS`** ([constants.py](dashboard/services/constants.py)):
- LINE user_id ใน set นี้ได้ `position="admin"` เสมอ **และ login ผ่าน LINE ได้ทันทีแม้ไม่มีในชีต employees / อ่าน employees ไม่ได้** (ต่างจากทาง 1–2 ที่ admin-check อยู่ใน loop ของ employees → ต้องมีใน employees ก่อน)
- ใช้กันเคส "แอดมินหลักล็อกตัวเองออก / เข้า UI จัดการแอดมินไม่ได้" — แก้ในโค้ดตรงๆ (ต้อง deploy) หรือเพิ่มผ่าน env `SUPER_ADMIN_IDS` (comma-separated, รวมกับ default)
- ทาง LINE Login OAuth (`_login_with_line_user_id`) = ไม่ต้องรหัส · ทางรหัสรวม (`login_view`) = ยังต้องกรอกรหัสรวมให้ถูก

- แอดมิน(เซลล์)ใช้ปุ่ม "ดูในฐานะ <ตัวเอง>" (impersonate) ดูหน้าเซลล์ตัวเองได้ · ต่างจาก **แอดมินสูงสุด** (env/`app_users role=admin`)

### Source of truth สำหรับนับเคสตามสถานะ
- **"จอง"** → นับจาก **leads sheet** (admin_status หรือ sales_status มีคำว่า "จอง" + ไม่ skipped). ดู `has_booking_status()` ใน [fetch_dashboard.py](dashboard/services/fetch_dashboard.py)
- **"รอเซ็นต์/รอผล/รอปล่อย/ปล่อย/รีเจ็ก"** → นับจาก **sales_reports sheet** (`booking_cases[].status`) — เพราะ admin update ใน "รายงานฝ่ายขาย"
- **★ dedup เคสค้างข้ามเดือน (ก.ค.69) — `_dedup_booking_cases()`**: เคสจองที่ไม่จบใน 1 เดือน แอดมิน **ก๊อปไปแท็บเดือนถัดไปเรื่อยๆ** (วันจองยังเป็นเดือนเดิม) → เคสเดียวโผล่หลายแท็บ. เดิม `booking_cases` อ่านทุกแท็บมารวมโดยไม่ dedup → **ตัวนับสถานะซ้ำ 2-2.6 เท่า** (วัดจริง: รอผล 97→38 · รอปล่อย 36→14 · รอเซ็น 80→40 · จอง(สถานะ) 44→22 · รีเจ็ก 292→271 · **ปล่อย 278→274 แทบไม่กระทบ** เพราะแท็บเก่าเคสยังไม่ปล่อย). **แก้: `_dedup_booking_cases()` ([fetch_dashboard.py](dashboard/services/fetch_dashboard.py)) เก็บสำเนา "แท็บเดือนล่าสุด" ต่อเคส** (= สถานะปัจจุบันจริง · สำเนาแท็บเก่า = สถานะที่ตายแล้ว) — คีย์: `leadCode` (ถ้ามีเลข) ไม่งั้น `ชื่อ+รถ+วันจอง`. เรียกหลัง build `booking_cases` (หน้ารวม) + `my_booking_cases` (หน้าเซลล์). วันจองยังเดิม → จอง นับเดือนถูก · ปล่อย นับตามแท็บ (ดูข้อถัดไป) · inline edit เขียนกลับแท็บ active (ล่าสุด)
- **★ ปล่อย/pipeline รายเดือน = นับ "ตามแท็บ" ไม่ใช่ "วันปล่อย" (ก.ค.69) — `_tab_month(b)`**: เดิม `get_done_month`/`_parse_done_day` นับปล่อยตาม **วันปล่อย** (`extract_release_date`) → แท็บเดือนเก่าคอลัมน์วันปล่อยย้าย/ฟอร์แมตต่าง/ว่าง **parse ไม่ได้** → เดือนต้นปีนับปล่อย**ขาดครึ่ง** (วัดจริง: ม.ค. ได้ 18 แทน 44 · ก.พ. 16 แทน 43). **แก้: ยึด "เดือนของแท็บ" ที่เคสอยู่เป็นหลัก** (`_tab_month` map ชื่อแท็บ→เดือน · fallback วันปล่อย/วันจอง ถ้าไม่มีแท็บ) → ตรงสูตรสรุปในชีตเป๊ะ (ม.ค.-พ.ค. 44/43/50/43/52). **นับจาก `booking_cases_raw` (ก่อน dedup)** — เคสข้ามเดือนนับในทุกแท็บที่มันอยู่ (แบบสูตรชีต · ต่างจาก dedup ที่เก็บแท็บเดียว) · แก้ทั้ง `monthly_summary` (m_done/m_bookings), `daily_by_month`/`daily_by_seller` dones, และ `fetch_seller_stats` (my_monthly/my_daily). **`_daily_names` รวมทุกเซลล์ที่มีเคส** (ADMIN/เซลล์ลาออก/ใบตอง) → ตารางรายเซลล์ครบ ไม่ขาด · `booking_cases` (dedup) ยังส่งให้ frontend กัน date-range นับซ้ำ. **★ รอผล/รอปล่อย ใน report table = `monthlySummary[m].pipeBySeller`** (per-seller wr/wp นับตามแท็บจาก m_bookings · รวมทุกเซลล์) — เดิม frontend `_pipeBy` นับเองจาก `D.bookingCases` กรองด้วย leadDate → ได้น้อยกว่าแท็บ (ก.ค. โชว์ 5/3 แทน 13/6). ตอนนี้ `_row` ใช้ `_mpipe(name)` ดึงจาก pipeBySeller ของเดือน `_cm` (เดือนที่ดู) → ตรงสูตรชีต (พ.ค. รอผล 25/รอปล่อย 6)
- **bookings sheet (separate spreadsheet) ไม่ใช้แล้ว** — เดิม `year_jongs` มาจาก bookings sheet, ตอนนี้ derive จาก leads. `fetch_all_sheets()` ยัง fetch อยู่ แต่ `raw_bookings` ไม่ถูกใช้ใน aggregator
- frontend (seller.html "🎯 เคสในมือ") — `bookingCount` filter จาก `D.leads` ด้วย logic เดียวกัน

### Lead Status (คอลัม Z "สถานะลูกค้า" — layout ใหม่ มิ.ย.69+)
ตั้งแต่ มิ.ย.69 สถานะหลักของ lead อยู่ที่ **คอลัม Z `customer_status`** (controlled vocab) ใช้คัดลำดับว่าเซลล์ตามเคสไหนก่อน:
- **dropdown 16 ค่า** (`Z_STATUSES` ใน seller.html · sync กับ sheet data validation) — ตัวกรองสถานะใน lead list (`STATUS_FILTERS`) ก็ gen จาก `Z_STATUSES` (เลิกใช้ ติดตาม/คืนเคส/ยกเลิก/จ่ายใหม่ จาก admin/sales)
- **priority (`CUSTOMER_STATUS_PRIORITY`, สูง→ต่ำ)**: สนใจมาก(8) · ลังเล(7) · ไม่รับสาย(6) · **ลูกค้าไม่ตอบ(6)** · รอเงิน(5) · รอเช็คเครดิต(4) · ดาวน์ไม่พอ(3) · **เงินสดเงินไม่พอ(3)** · จอง(2) · ส่งมอบ(1) · **ได้รถแล้ว(1)**
- **3 ค่าใหม่ (มิ.ย.69)**: `ได้รถแล้ว`=เคสจบ/ผลบวก (เหมือนส่งมอบ ไม่ remind · อยู่ใน `isBooked`/`_booked`/`should_follow` exclude) · `เงินสดเงินไม่พอ`=ยังตามต่อ (เหมือนดาวน์ไม่พอ · cadence 3) · `ลูกค้าไม่ตอบ`=ยังตามต่อ (เหมือนไม่รับสาย · cadence 1). แก้ต้อง sync 4 ที่: `Z_STATUSES`/`Z_PRIORITY`/`CADENCE` (seller.html) + `CUSTOMER_STATUS_PRIORITY`/`_FU_CADENCE` (fetch_dashboard.py)
- **เคสเสีย (`CUSTOMER_STATUS_DEAD`) = "ไม่ต้องตาม"**: ยังไม่ออกเร็วๆนี้ · ติดแบล็คลิส · เครดิตไม่ผ่าน · ลูกค้าไม่สนใจแล้ว · **คืนเคส** (ผู้ใช้กำหนดว่าพวกนี้ในวงเล็บ = เคสเสีย)
- **`should_follow(r)`**: ตามต่อ = active chase เท่านั้น (priority ≥3). **จอง/ส่งมอบ/ได้รถแล้ว = ไม่ remind ให้โทร** (outcome บวก ไม่ใช่เคสเสีย) · เคสเสีย = ไม่ตาม · **"ตามด่วน" (seller.html) ตัด "คืนเคส" (Z/admin/sales) ออกด้วย** (`_isReturned`)
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
- **ความเร็ว (velocity)**: วัดเฉพาะ**เคสที่ปล่อยแล้ว** (status="ปล่อย") ในช่วงที่เลือก. แต่ละช่วง: ทันกำหนด=1.0, เกินลดเชิงเส้นถึง 0 ที่ **3× กำหนด** (เช่น จอง→เซ็น: 3วัน=เต็ม, 9วัน=0). **ช่องวันว่าง/parse ไม่ได้ = 0 ช่วงนั้น**. ใช้ฟิลด์ booking_cases: `date`(จอง C) `signDate`(เซ็น O) `resultDate`(ผล — **U20 พ.ค.+/T19 เดือนก่อน** ผ่าน `result_date_for`) `releaseDate`(ปล่อย X23/V21). JS `_stageScore()`+`VEL_STAGES` · Python `_stage_score()`+`_case_velocity()`
  - **★ คะแนน sVel ถ่วงตามจำนวนเคส (Bayesian shrink k=1 เข้าหากลาง 0.5)**: `sVel = (ผลรวมความเร็ว + 0.5)/(จำนวนเคส + 1) × 10` — ปล่อยน้อย=ถ่วงเข้ากลาง, ปล่อยเยอะ=เชื่อค่าจริง (ปล่อย 1 เร็ว=7.5 · 4=9.0 · 8=9.4) กันเคสเดียวเร็วได้ 10 เท่าคนปล่อยเยอะ · ปล่อย 0=0 (ไม่มีอะไรให้วัด) · **`velPct` (% ปิดทันกำหนด) ยังเป็นค่าจริงไม่ถ่วง** (tooltip). sync ทั้ง JS+Python
- **2 ที่ต้อง sync กัน**: JS `buildDilMap()` (scorecard ที่โชว์จริง, ใน [index.html](dashboard/templates/dashboard/index.html), const `DONE_TGT=15/JONG_TGT=30/CONV_TGT=5` + `VEL_STAGES`) + Python `compute_diligence_scores()` (สำหรับ export → sheet "leadscore"). แก้สูตรต้องแก้ทั้งคู่
- **ข้อมูลแบน**: `fetch_ban_counts_by_month()` อ่าน tab **"รายงานแบน"** (`SHEET_CONFIG["ban_report"]`, ไฟล์ live) — log 1 แถว=1 ครั้ง (`BAN_COL`), นับตาม banDate. inject เข้า `sellers[].bans` + `monthlySummary[m].sellers[name]["bans"]`
- เปิด modal คะแนน → ปุ่ม "ดูสูตรคะแนน" (`showScoreHelp`) อธิบาย 6 ด้าน
- **แถวรวมท้ายตาราง** (มิ.ย.69): ปล่อย/จอง = ผลรวมทุกเซลล์ · คอลัมน์คะแนน = ค่าเฉลี่ย (เพราะคะแนนเป็น /30 /10 ต่อคน บวกกันจะเกินเพดาน) — ทั้ง index.html + seller.html
- **🏆 leaderboard ในหน้าเซลล์ (มิ.ย.69)**: seller view (`/s/`, `/me/`) ก็โชว์ตารางคะแนนทุกเซลล์ (`renderScorecard()`) ไฮไลท์แถวตัวเอง · view ส่ง `data["scorecard"]` = `compute_diligence_scores()` (คะแนนเดือนนี้ · ส่งแค่ชื่อ+แต้ม ไม่ใช่เคสลูกค้า) — **ข้อยกเว้นเดียวที่ส่งข้อมูลคนอื่นไปหน้าเซลล์** (ปกติ seller.html มีแต่ข้อมูลตัวเอง · ผู้ใช้เลือก leaderboard)

### Seller page KPI structure (`seller.html`)
หน้าเซลล์ (`/s/<token>/`) แบ่ง KPI เป็น 2 zones — ตัวเลขใหญ่ = ภาพรวม, chip = filter ลึกลง:
- **KPI cards (4 cards หลัก)** ใน `KPI_DEFS`: `all` หลีดที่รับ · `called` โทรแล้วมีหลักฐาน · `notCalled` ยังไม่โทร · `follow` ต้องโทรต่อ (status-based)
- **Filter chips ใต้ KPI** ใน `CALL_FILTERS` (disjoint by exact updateCount): `c0` ยังไม่โทร · `c1` 1 ครั้ง · `c2` 2 ครั้ง · `c3` 3 ครั้ง · `cFull` ครบ ${UPD_TGT}+
- ทั้ง 2 zones กดได้ → set `kpiFilter` → filter `lead list` ด้านล่าง (mutually exclusive — กดอันใหม่ override อันเดิม)
- ALL_FILTERS = [...KPI_DEFS, ...CALL_FILTERS] รวมไว้สำหรับ `findFilter(key)` lookup

#### 🔔 กระดิ่งแจ้งเตือนเซลล์ + แก้สถานะ/ตัวกรอง (มิ.ย.69)
- **กระดิ่ง + badge** (`sellerBellHtml`/`openSellerAlertsPanel`/`computeSellerAlerts`) อยู่ในแถบโหมด (`modeBar`) บนสุด ชิดขวาติดปุ่มสลับธีม — รวบ banner เดิมเข้า dropdown แบบหน้าแอดมิน: **งานเดือนนี้** (ยังไม่โทร/ต้องตามต่อ → ปุ่มกด `setPageMode('dashboard')`+`setKpi`) · **ปล่อยลงวันไม่ครบ** (กดเปิดเคส) · **ไม่มีสถานะ Z** · **วันที่ปีผิด** (ปีนอก 2020–2035 เช่น 1969 · กดเปิดแก้ได้แม้หลุดช่วงวันที่). **badge** = ยังไม่โทร + ปล่อยลงวันไม่ครบ + วันที่ปีผิด (งานด่วน/finite · **ไม่รวม** follow/noStatus ก้อนใหญ่ ไม่งั้น badge บวม 99+) · กระดิ่งแดงเมื่อมีปีผิด · **ลบ 3 banner เดิมออกจากหน้า** (ย้ายเข้ากระดิ่งหมด)
- **เปิด/เซฟเคสที่หลุดช่วงวันที่**: `openBookingDetail(idx, arr?)` + `saveTimelineDate`/`saveCaseStatus` ใช้ module var `_bdArr` (array ที่เปิดล่าสุด) → เคสปีผิดเปิด/เซฟจาก `D.bookingCases` เต็มได้ (`openBadYrCase(gi)`) · ของเดิม (ส่งแค่ idx) ใช้ `bookingsInRange()` เหมือนเดิม (backward-compatible)
- **แก้สถานะเคสในรายละเอียด** (`saveCaseStatus`): dropdown สถานะเคส (จอง/จอง(ซื้อสด)/รอเซ็นต์/รอผล/รอปล่อย/ปล่อย/รีเจ็ก) เหนือไทม์ไลน์ ในเคสตัวเอง → POST `update_release_date` col **13 (N)** auto-save + ownership · optimistic `b.status` (mirror ตามรอบ sync) · **status = คอลัมน์ N(13)** (flattened index = sheet column ใน `fetch_sales_by_month_tabs` · เขียนไม่ผิดช่อง)
- **ตัวกรอง dropdown สถานะเพิ่ม 2 ตัว** (`STATUS_FILTERS`): `f_nocall` ยังไม่โทร · `f_nostatus` ยังไม่มีสถานะ (ตัด junk/จอง/ปล่อย — ตรงกับ KPI/กระดิ่ง) เหนือ 16 ค่า Z

#### 🔥 ตามด่วน — สมองจัดลำดับความสำคัญ (`followUrgency` ใน seller.html)
section "ตามด่วน — โทรก่อน" (เดิม "โทรเคสไหนก่อน" เรียงแค่ leadScore) → อัปเกรดเป็น **สมองรวม** ที่ช่วยเซลล์รู้ว่า "ตามใครก่อน":
- **`followUrgency(l)`** รวม 4 สัญญาณ: **ยังไม่โทร** (`updateCount===0` → +120, speed-to-lead) · **ฮอท × ดองนาน** (`leadScore/100 × idleDays × 9` — หัวใจ ทำให้ "ฮอทแต่ค้างนาน" พุ่งบน) · **สถานะลูกค้า** (`followPriority×6`) · **ดองนานเฉยๆ** (`idle×2`). `_idleDays` = วันตั้งแต่ `lastUpdate` (ไม่งั้น `dateIn`)
- **`urgencyReason(l)`** → ป้าย "ด่วนเพราะ: ยังไม่โทรเลย / ฮอทแต่ค้าง X วัน / ค้าง X วัน / ลูกค้าสนใจมาก"
- filter เดิม: `!isSkipped && !isBooked` (junk/จอง/ส่งมอบ ไม่ต้องตาม)
- **จังหวะตาม (cadence)**: เพิ่งตามยังไม่ถึงรอบ → urgency ×0.35 (ไม่เด้งซ้ำ) · `CADENCE` ต่อสถานะ (สนใจมาก 1 · ลังเล 2 · ไม่รับสาย 1 · รอเงิน 3 · รอเช็คเครดิต 2 · ดาวน์ไม่พอ 3 · default 2) · `over = idle − cadenceDays` (เลยรอบ = ด่วน · ฮอท×over) · **ไม่รับสายเกิน `NOANS_CAP`(5) ครั้ง → return −1 (พักไว้ ไม่สแปม)** · section filter ตัด `followUrgency ≤ 0`
- **section "🚩 ดีลค้าง — ดันต่อ"** (ใต้ "ตามด่วน") — จาก `bookingsInRange()` (idx ตรงกับ `openBookingDetail`): จอง/รอเซ็นค้าง >3วัน · รอผลนาน >5วัน · รอปล่อยค้าง >3วัน → เรียงวันค้าง top 8 (ดีลเกือบปิด ต่างจากลีดใหม่)
- **`_skip`/`_booked` ดู Z + AB ร่วมกัน (มิ.ย.69 · followup `build_followup_messages`)**: "ไม่ต้องตาม" เช็คคอลัม **Z (สถานะลูกค้า) + AB (Status แอดมิน) + เซลล์** แบบ OR — อันใดอันหนึ่งเข้า = ตัด. `_skip`=เคสเสีย/ปิด (คำเสียใน Z `_FU_DEAD` หรือ ยกเลิก/คืนเคส/จ่ายใหม่/จบ/ส่งมอบ ใน Z+AB+เซลล์ `_FU_SKIP`) · `_booked`=จอง/ปล่อย/ส่งมอบ/ได้รถแล้ว ใน Z+AB+เซลล์. **ตัวอย่าง**: Z ว่าง·AB=ยกเลิก → ตัด · Z=คืนเคส·AB=ติดตาม → ตัด (คำเสียใน Z ชนะ) · Z=ติดตาม·AB=จอง → ตัด (booked จาก AB). **เดิม `_booked` ดูแค่ Z ถ้า Z มีค่า** → เคส Z=active แต่ AB=จอง/ปล่อย หลุดมาโดนตามผิด (แก้แล้ว · ยัง overlay Z จากแท็บล่าสุดใน `fetch_leads_by_month_tabs`) · **seller.html `isSkipped`/`isBooked` sync แล้ว** (ดู Z+AB+เซลล์ แบบ OR เหมือนกัน · แก้ที่ 2 ฟังก์ชันนี้กระจายทุก KPI/ตัวกรอง/ตามด่วน)
- **เฟส 2 (ทำแล้ว — PRODUCTION ส่งเซลล์จริง)**: `build_followup_messages()` ([fetch_dashboard.py](dashboard/services/fetch_dashboard.py)) = mirror `followUrgency`+cadence+ดีลค้าง เป็น Python (pass เดียว group ตาม seller · ไม่เรียก `fetch_seller_stats` ต่อคน) → ข้อความธรรมดา top N + ลิงก์ `/s/`. **`cron_tick` อ่านตารางจากชีต "ตั้งเวลาส่ง"** (`load_schedules`+`schedule_matches_now`) → ถึงเวลาแถวที่ enabled = ส่ง (default 09:00/13:00 · แอดมินแก้เวลา/ผู้รับ/test ในหน้า "ตารางเวลา (Auto)" ได้เอง — **เลิก hardcode `_FU_TIMES`/`_FU_TEST_TARGET` แล้ว · repurpose schedule sheet ที่เดิมคุม Flex มาคุม followup**). แต่ละแถว: `test_target` ว่าง=ส่งเซลล์จริง · ใส่ user_id=ทดสอบ · `sellers` (*/รายชื่อ)=กรองผู้รับ. กรองเฉพาะลีดย้อนหลัง 14 วัน (rolling · `win_start = today − 14`) · dedup ดีลค้าง · ใช้ canonical URL `_FU_BASE`. ยังไม่มี anti-spam Supabase (อาศัย time-match HH:MM)

#### 📊 เก็บสถิติ followup + เทรนด์ (ก.ค.69) — 2 ตาราง + ตารางเทรนด์ในแดชบอร์ด
cron ตอนส่ง followup (`build_followup_messages(log_daily=True)` ใน `cron_tick`) เขียน 2 ตาราง [dashboard/models.py](dashboard/models.py) — **migration 0002/0003/0004 (ต้อง `migrate` ตอน deploy)**:
- **`FollowupLog`** (`dash_followup_log` · unique date+seller = 1 แถว/วัน/เซลล์) — snapshot รายวัน/เซลล์:
  - state ค่าล่าสุดของวัน: `not_called`/`no_status`/`stuck_deals`/`follow_total`
  - **นับ "โดนทวง" (จำนวนครั้ง = รอบส่ง ไม่ใช่จำนวนเคส)**: `nags`=รอบที่ติดรายการ (มีงานค้างอย่างน้อย 1 เรื่อง) · **`nag_call`/`nag_status`/`nag_deal`**=รอบที่ยังค้างเรื่อง โทร/สถานะ/ดีล (+1 ต่อรอบส่งถ้าเรื่องนั้น>0). เขียนด้วย `get_or_create`+`F()`+1 (ส่งซ้ำในวัน=นับเพิ่ม · state=ค่าล่าสุด)
  - **`followup_rounds` kv** ([cache_store](dashboard/services/cache_store.py) · `{date_iso: จำนวนรอบส่งวันนั้น}`) = ตัวหารของ % (⚠️ `get_kv` ห่อค่าใน `{data,updated_at}` — ต้อง unwrap `["data"]`)
- **`SellerWeekly`** (`dash_seller_weekly` · unique week_start+seller) — ผลงานราย "สัปดาห์" (จันทร์→อาทิตย์ ไม่นับอนาคต) จาก `dailyBySeller`: lead/rj/booking/done/deal_value/live/clip. `snapshot_seller_week()` **กรองเฉพาะ roster ปัจจุบัน** (`ALL_SELLERS`∪`ADMIN` · บังคับ `refresh_from_sheet()` ก่อนสร้าง roster กันตกไป hardcode → กัน orphan/เซลล์เก่า/สะกดผิดโผล่)
- **ตารางเทรนด์ล่างสุด "แท็บภาพรวม"** ([index.html](dashboard/templates/dashboard/index.html) ท้าย `renderOverview`): **"โดนทวงเรื่องอะไรบ่อย รายเซลล์"** — 3 คอลัมน์ โทร/สถานะ/ดีล (โดนทวงกี่ครั้ง + % ของรอบส่ง · สีตามความเรื้อรัง แดง≥70%). **กรองด้วยช่วงวันที่หน้า** แต่เทียบ ISO ตรงๆ `r.date>=dfFrom && r.date<=dfTo` (**ไม่ผ่าน `ir`/`_parseDmy` ที่คาด d/m/y — r.date เป็น ISO "YYYY-MM-DD"**). ข้อมูล inline ผ่าน `trends_json` (context) = `_trends_payload()` [views.py] · endpoint สำรอง `/api/admin/trends` (`admin_trends`)
- **⚠️ บทเรียน: nag ก้อนเดียว ตัน ~100% เกือบทุกคน** (ทุกเซลล์มีลีดค้างตลอด → ติดรายการทุกรอบ) → **ต้องแยก 3 เรื่อง (โทร/สถานะ/ดีล) ถึงเห็นความต่าง** (ใครไม่โทร/ใครไม่ใส่สถานะ/ใครไม่ดันดีล). แก้สูตร nag ต้อง sync: write ใน `build_followup_messages` + `_trends_payload` values + ตาราง index.html

#### 📊 รายงานเข้าไลน์รายวัน (แคปตารางเป็นรูป ก.ค.69) — [report_shot.py](dashboard/services/report_shot.py)
ส่งรูปตาราง "รายงาน จอง/อนุมัติ/ปล่อย" (การ์ด `#rpt-card` ในแท็บภาพรวม) เข้ากลุ่ม LINE อัตโนมัติทุกวัน — **แคปด้วย Playwright (headless Chromium) ในเครื่อง/VPS เอง ไม่ส่งข้อมูลออกนอก** (เคยพิจารณา hcti.io แต่ส่งข้อมูลเซลล์ออก third-party + รูป public URL → เลี่ยง)
- **`capture_report_images()` (พหูพจน์ · แคป 2 รูปใน browser session เดียว — login ครั้งเดียว)**: Playwright login แดชบอร์ด (`/login/?bg=1` · **ต้อง `page.evaluate` เปิด `<details>` break-glass ก่อน fill** เพราะฟอร์มพับอยู่) → รอ `#rpt-shot` → วน `_SHOT_TARGETS` = `[(rpt-shot, rpt-shot-wrap), (rpt-shot-teams, rpt-shot-teams-wrap)]` เปิด wrapper (`height:auto`) แล้ว `.screenshot()` แต่ละอัน → เซฟ `MEDIA_ROOT/reports/report_<ts>_<id>.png` · **คืน list ของ path** (fallback `#rpt-card` ตัวเต็มถ้าแคป #rpt-shot ไม่ได้เลย). `capture_report_image()` (เอกพจน์) = alias คืน path แรก · device_scale=3 (คมชัด)
  - **⚠️ `page.evaluate(fn, arg)` ต้องเป็น arrow function** (`(id)=>{...}`) ถึงจะรับ arg ได้ — ใช้ `arguments[0]` ใน expression ธรรมดา = throw (เคยพลาด ทำ #rpt-shot ตกไป fallback #rpt-card)
  - **timeout รอ #rpt-shot = 35s** กัน cold start (`/api/dashboard` คำนวณสด ~8-20s ตอน cache เย็น → ถ้ารอสั้นไปจะตก fallback)
  - **ยิงที่ `SITE_URL` ตรงๆ (dev=http://127.0.0.1:8000 · prod=https://โดเมน ผ่าน nginx) · อย่าใส่ `X-Forwarded-Proto:https` header เอง** — จะทำ CSRF referer scheme เพี้ยน login ไม่ผ่าน
  - **`#rpt-shot` / `#rpt-shot-teams`** = id ที่เพิ่มให้ตาราง+กราฟใน `renderOverview` ([index.html](dashboard/templates/dashboard/index.html)) เพื่อให้ Playwright จับ
- **`send_report_to_line(target, caption='', mention_all=False)`**: capture 2 รูป → เซฟ → URL `SITE_URL/media/reports/...` → ส่ง **caption + 2 image message** (`push_line_message`). **⚠️ LINE ต้องดึงรูปจาก URL https สาธารณะ → ได้จริงเฉพาะ prod** (localhost ส่งไม่ได้ · dev คืน error "ยังไม่มี URL https")
  - **caption อัตโนมัติ** (`_report_caption()`) = `"ผลงานทีม ตั้งแต่วันที่ 1-<วันนี้>/<เดือน>/<ปี พ.ศ.> ค่ะ"` (โซนไทย `bangkok_now`) · ใส่ `caption` เองได้ทับ default
  - **`mention_all=True` → แท็ก @All ด้วย LINE textV2** (`_caption_message`): `{type:"textV2", text: caption+" {all}", substitution:{all:{type:"mention", mentionee:{type:"all"}}}}` — **ใช้เฉพาะส่งเข้ากลุ่ม** (1:1 แท็กไม่ได้) · ส่งทดสอบเข้า `test_id` = ข้อความธรรมดา (`type:"text"`)
  - **caller ตั้ง mention_all**: `maybe_send_daily_report` → `mention_all = (mode=='group')` · `admin_report_test` → `mention_all` เมื่อ target == group_id (ปุ่มส่งทดสอบเข้า test_id = ไม่แท็ก)
- **config** (KVStore `report_line_config`): `{enabled, time (HH:MM โซนไทย), mode (test/group), test_id, group_id}` · จัดการที่ **เมนูจัดการ → "รายงานเข้าไลน์"** (`openReportLine`/`saveReportLine`/`testReportLine` · เวลาเป็น dropdown ทุก 30 นาที + ปุ่มส่งทดสอบ)
- **cron**: `maybe_send_daily_report(HH:MM, today)` เรียกจาก `cron_tick` → ส่งถ้า enabled + เวลาตรง + ยังไม่ส่งวันนี้ (anti-dup ด้วย KVStore `report_line_last`) · `_cleanup_old` ลบรูป >7 วัน
- **deploy บน VPS ต้องลง Chromium**: `pip install playwright` + **`playwright install chromium --with-deps`** (lib ระบบ + ฟอนต์ไทย `fonts-thai-tlwg` · Chromium launch ใช้ `--no-sandbox`) · set `PLAYWRIGHT_BROWSERS_PATH` ให้ user `oxlet` เจอ browser · ไม่ลง = แคปไม่ได้ (คืน None ไม่พังระบบ)
  - **⚠️ อัปเกรด playwright แล้วต้องลง Chromium ใหม่ทุกครั้ง (ส.ค.69 · เคยทำรายงานรายวันหยุดส่ง)**: `requirements.txt` เขียน `playwright>=1.40` **ไม่ล็อกเวอร์ชัน** → `pip install -r requirements.txt` ตอน deploy อาจอัปเกรดแพ็กเกจเงียบๆ · Playwright **แต่ละเวอร์ชันผูกเลข build ของ Chromium คนละตัว** (`chromium_headless_shell-<build>`) พอไม่ตรงกัน = `Executable doesn't exist` → "แคปรูปไม่สำเร็จ" ทั้งที่เมื่อวานยังส่งได้ · แก้: รัน `playwright install chromium --with-deps` ซ้ำหลัง pip upgrade (ดู [deploy/DEPLOY.md](deploy/DEPLOY.md))
  - **⚠️★ regression ที่เคยทำรายงาน/การ์ดหยุดส่ง 2-3 วัน (ส.ค.69) — เมนูสามขีดทับปุ่มแท็บ**: การ์ดที่จะแคปอยู่ **คนละแท็บกับหน้าแรก** (`#rpt-shot`/`#rpt-shot-teams`/`leadreport-card`… อยู่แท็บ LEAD · `fin-card` อยู่แท็บสถานะจองปล่อย) · โค้ดแคปเดิมเปิดแท็บด้วย `page.click("button.ntab:has-text('...')")` → พอย้ายแท็บเข้า **drawer ที่ปิดอยู่** (`transform:translateX(-104%)` = อยู่นอกจอ) Playwright กดไม่โดน → แท็บไม่เปลี่ยน → ไม่มีการ์ดให้แคป → **หยุดส่งเงียบๆ ไม่มีใครรู้**
    - แก้ด้วย helper **`_goto_tab(page, ชื่อแท็บ)`** — เรียก **`switchTab(<id>)` ตรง** (map ชื่อ→id ที่ `_TAB_ID`) + คง click เป็น fallback · **ใช้ทั้ง 3 ทางแคป**: `capture_report_images` · `capture_card` · `capture_leadsummary` (ตัวหลังเดิม **ไม่สลับแท็บเลย** ทั้งที่การ์ดอยู่แท็บ LEAD)
    - **กฎ: อย่าให้ Playwright คลิกปุ่มที่งาน UI อาจย้าย/ซ่อนได้ — เรียกฟังก์ชัน JS ตรงเสมอ** · เพิ่มแท็บใหม่ต้องเพิ่มใน `_TAB_ID` ให้ตรงกับรายการแท็บใน [index.html](dashboard/templates/dashboard/index.html)
  - **★ งบเวลารวม (`REPORT_SHOT_BUDGET_SEC` default 90s)**: ผลรวม timeout ทุกขั้นเดิม ~186s แต่ **nginx ตัดที่ 120s** (`proxy_read_timeout` ของ `location /`) → ตอนพังจริงคำขอโดนตัดก่อน ผู้ใช้เห็นแค่ "หมุนค้าง" ไม่เคยได้ข้อความบอกสาเหตุ · ตอนนี้ `left_ms()` หดเวลารอทุกขั้นให้จบใน 90s เสมอ
  - **★ ข้อความ error บอกสาเหตุจริงแล้ว (ส.ค.69)**: เดิม `capture_*` กลืน exception ทุกจุด (`except: pass`) แล้วผู้เรียกเดาว่า "เช็ค playwright/chromium" ซึ่งมักไม่ใช่สาเหตุ (อาจเป็น login ไม่ผ่าน/ตารางไม่ render/ชีตพัง) → แอดมินไล่ผิดทาง · เพิ่ม **`diagnose()`** (ลองเปิด Chromium จริง + โชว์ `PLAYWRIGHT_BROWSERS_PATH`) + **`last_error()`** (เก็บ error จากขั้นตอนแคป) + **`_capture_fail_msg()`** ที่ทั้ง 3 จุดส่งข้อความให้ผู้ใช้ — แยกออกว่า "เบราว์เซอร์ไม่พร้อม" หรือ "เบราว์เซอร์โอเคแต่หน้าเว็บมีปัญหา"
- **แคป `#rpt-shot` (เวอร์ชันสไตล์อ่านง่าย · ไม่ใช่ตารางเว็บดิบ)**: ตารางเว็บ `#rpt-card` อัด 11 คอลัมน์แน่น อ่านยากบนมือถือ → ทำ **`#rpt-shot`** ใน `renderOverview` (reuse `_rpt`+`_RC` เดียวกัน = **ครบทุกคอลัมน์ ตัวเลขตรงกับตารางเต็ม**) แต่สไตล์ใหม่: **แถวโค้ง · badge สีทีม · ตัวใหญ่ขึ้น · เว้นระยะ · สี light คงที่** (ไม่อิงธีมเว็บ). **ซ่อนบนเว็บ** ด้วย wrapper `#rpt-shot-wrap` (`height:0;overflow:hidden`) → capture `page.evaluate` เปิดให้เห็น (`height:auto`) ก่อน screenshot · **#rpt-shot ต้องกำหนด `width` เอง (1560px)** (ไม่งั้น block เต็มความกว้าง → รูปมีที่ว่างขวา) · fallback `#rpt-card` ถ้าไม่มี · **แก้คอลัมน์ = แก้ที่ `#rpt-shot` ใน index.html (reuse `_RC` อยู่แล้ว)**
- **★ เคสจบตามไฟแนนซ์ (ส.ค.69)**: ผู้ใช้เพิ่มคอลัมน์ **"ชำระแบบ"** (KK/KL/TTB/AY/NISSAN/เงินสด...) ในฝั่ง "จบ" (บล็อกขวา) ของแท็บ **จอง/จบ** ชีตนับลีด → `fetch_finance_by_month_tabs()` ([google_sheets.py](dashboard/services/google_sheets.py)) อ่านแบบ **header-based** (หา "ชำระแบบ" ใน 5 แถวแรก + คอลัมน์สถานะ "ปิด" ทางขวา ≤8 ช่อง · เจอสถานะ = นับเฉพาะแถวมีคำ "ปิด" ที่ไม่ใช่ "ไม่ปิด/ยังไม่" · ไม่เจอ = นับทุกแถวที่ชำระแบบไม่ว่าง) → `data["financeSummary"]` = `{เดือน:{ไฟแนนซ์:จำนวน}}` (เดือนตามแท็บ · best-effort error={}) · โชว์: **การ์ด `#fin-card` ท้ายแท็บ "สถานะจองปล่อย"** (`renderBookings` · กรองเดือนตามช่วงวันที่) + เวอร์ชันสวย **`#fin-card-shot`** (ซ่อน · ทั้งปี · โทนทอง #b45309) ให้ปุ่ม "ส่งไลน์ ▾" ของการ์ด (cardline `fin-card` — ลงทะเบียนใน `_LINE_CARDS`+`_CARD_TAB` แล้ว) — **ไม่อยู่ในรายงานประจำวัน 2 รูป** (เคยเป็นรูปที่ 3 · ผู้ใช้สั่งถอด ส.ค.69)
- **★ เปลี่ยนชื่อแท็บ 'b' (ส.ค.69)**: "ติดตามสถานะจอง" → **"สถานะจองปล่อย"**
- **★ ขยาย/สมดุลฟอนต์รูปรายงาน (ส.ค.69 ปรับ 3 รอบตาม feedback)**: `#rpt-shot` — หัวหลัก 27 หัวรอง 24 ชื่อเซลล์ 29 ป้ายทีม 18 subtitle 27 · ตัวเลข หลัก 30 รอง 26 (เคยดัน 36/30 → ผู้ใช้บอกเลขใหญ่ไป-หนังสือเล็กไป) · กรอบ 1560→**1700px** (ผู้ใช้อนุญาตขยายกรอบ) · `#rpt-shot-teams` ตาราง 19 หัว 17-18 (1120px)
  - **⚠️ กฎจัดคอลัมน์ #rpt-shot: ทุกช่อง (หัว+ตัวเลข) ใช้ `width` ตายตัว + `flex-shrink:0` — ห้าม `min-width`**: ป้ายหัวยาว (เช่น "เฉลี่ย Lead/วัน") เคยดันช่องหัวกว้างเกินช่องตัวเลข → คอลัมน์เหลื่อมสะสมไปขวา (ผู้ใช้ทัก "ตัวเลขไม่ตรงกับคอลัมน์") · ช่องหลัก 128px รอง 104px ป้ายยาวตัดบรรทัดในช่อง
- **รูปที่ 2 = ตารางสรุปรายทีม `#rpt-shot-teams`** (ก.ค.69 · เลย์เอาต์ตามชีตสรุปของผู้ใช้): คอลัมน์ **ลำดับ | สาขา/ทีม | เป้า | [เดือน<ชื่อเดือน> คร่อม: จอง/เซ็น/อนุมัติ/ปล่อย] | รวมปล่อยทั้งปี** + แถวรวม · aggregate `_rpt` ตาม `r.team` (target/bk/wr/wp/dn) · **เซ็น = รอผล(wr) · อนุมัติ = รอปล่อย(wp)** (แดชบอร์ดไม่มีตัวนับเซ็น/อนุมัติแยก → ใช้ตัวนับสถานะชุดเดียวกับตารางรายงาน · เขียนบอกใต้หัวตาราง) · **รวมปล่อยทั้งปี** = `_yearDone(tid)` sum `monthlySummary[m].teams[tid].done` ทุกเดือน (ADMIN นับจาก `sellers['ADMIN'].done`) · เรียงปล่อยมากสุด ADMIN ล่างสุด · ชื่อทีมจาก `C.TEAM_NAMES` (ADMIN→"เทเลเซลล์")
  - **สีหัวเดือนเปลี่ยนตามเดือน**: `_MONTH_COLORS` 12 สี index ด้วย `_cm` (เดือนที่ดู) → ก.ค. = magenta · แถบซ้าย/รวมปีใช้ `color-mix` ของสีเดือนอ่อนๆ · แถวรวม = สีเดือนเต็ม · สี light คงที่ (ไม่อิงธีม)
  - ซ่อนบนเว็บด้วย `#rpt-shot-teams-wrap` (height:0) เปิดก่อนแคปเหมือน #rpt-shot · width 1120px. ส่งเข้า LINE เป็นรูปที่ 2 ต่อจากตาราง · _(เดิมเป็นกราฟแท่งปล่อยต่อทีม — เปลี่ยนเป็นตารางตามที่ผู้ใช้ขอ ก.ค.69)_
- **เดือนปัจจุบันเสมอ**: capture เปิด `/dashboard/` ใหม่ → ตัวกรองวันที่ default = **1-สิ้นเดือนปัจจุบัน** → `#rpt-shot`/`#rpt-shot-teams` เป็นข้อมูลเดือนนี้อัตโนมัติ (ไม่ต้องตั้งอะไร) · caption ระบุ "1-<วันนี้>" (ถึงวันที่รันจริง)
- **ความชัด**: `device_scale_factor=3` (รูปคม ~4680px กว้าง · ~KB หลักร้อย พอดีลิมิต LINE preview 1MB)
- **เลือกกลุ่มปลายทาง (แก้ปัญหา "ไม่รู้ group id / บอทอยู่กลุ่มไหน")**: **LINE ไม่มี API ลิสต์กลุ่ม** → เพิ่ม **inbound webhook `/api/line/webhook`** (`line_webhook`) บอทจำกลุ่มเองตอนได้ event จากกลุ่ม (join/message) → เก็บ `line_groups` (id+ชื่อ · ดึงชื่อจาก group summary) → พาเนลโชว์ **dropdown เลือกกลุ่มตามชื่อ** (`admin_line_groups`). วิธีลงทะเบียนกลุ่ม: **register Webhook URL ใน LINE Console → เพิ่มบอทเข้ากลุ่ม → พิมพ์อะไรก็ได้ในกลุ่ม 1 ครั้ง → กลุ่มโผล่ใน dropdown**. ปุ่ม "ตรวจชื่อ" (`admin_line_group_name`) = ดึงชื่อจาก id ที่วางเอง (ยืนยัน). set `LINE_CHANNEL_SECRET` (env) เพื่อ verify signature webhook (ไม่ตั้ง = ข้าม verify)
  - **★ ทางเลือก: ให้ n8n เป็นตัวรับ webhook แล้ว forward มา (ก.ค.69)** — LINE ตั้ง Webhook URL ได้ที่เดียว/channel · ถ้า channel ชี้ไป n8n อยู่แล้ว ให้ n8n POST group event มาที่ **`/api/line/group_ingest`** (`line_group_ingest`) แทน: **auth = `?secret=<CRON_SECRET>` หรือ header `X-Cron-Secret`** (ไม่ใช้ลายเซ็น LINE เพราะ n8n serialize body ใหม่ → `X-Line-Signature` ไม่ตรง) · **body ยืดหยุ่น** — ส่ง LINE raw (`{events:[...]}`) ทั้งก้อน หรือแค่ `{groupId, groupName?}` / list ก็ได้ (`_extract_group_events` รับหมด) · เก็บลง `line_groups` เดียวกับ webhook (`_store_line_groups`) → dropdown เด้งชื่อกลุ่มอัตโนมัติเหมือนกัน · คืน `{ok, count, groups:[{id,name}]}`. **หรือไม่ forward ก็ได้** — ดู groupId ใน execution ของ n8n แล้ววางเองในช่อง "กลุ่มปลายทาง" + กด "ตรวจชื่อ" (พาเนลมี input วาง id เอง ไม่บังคับใช้ dropdown)
  - helper ใช้ร่วมกัน: `_extract_group_events(data)` (ดึง `[(gid,name)]` จาก payload หลายรูปแบบ) + `_store_line_groups(pairs)` (เก็บ + ดึงชื่อจาก LINE ถ้าไม่มี) — ทั้ง `line_webhook` และ `line_group_ingest` เรียกคู่นี้

#### 🎯 Lead Score (คุณภาพ lead — `compute_lead_score` ใน fetch_dashboard.py)
คะแนน "เคสนี้น่าปิดแค่ไหน" (ต่างจาก **คะแนนเซลล์**/scorecard) — `leadScore`/`leadTier`/`scoreBreakdown` คำนวณ Python ฝั่ง view ส่งเป็น data ให้ seller.html (ไม่มี JS mirror) · เกณฑ์อยู่ใน `_LEAD_SCORE_DEFAULTS` (fallback) หรือ sheet **"เกณฑ์คะแนน lead"** (override ถ้ามี — `load_lead_score_config`)
- **4 ด้าน (มิ.ย.69 ตัด รถ/ประวัติ ออก)**: ความใหม่ (≤3วัน +20 · เย็น -5) · **ประเภท (Type)** · ช่องทาง (Walk-in +15 · TikTok +10 · FB +5) · Engagement (ลูกค้าตอบ +25 · inbox +15 · โทรไม่รับ -10)
- **Type = match ค่าในชีตตรงๆ** `_apply("ประเภท: " + lead_type)` → รองรับทุกค่า + เพิ่มใหม่ในชีตได้: Very Hot 60 · Hot / TLD&nbsp;Hot 50 · MerHot 38 · TLD / Moderate 35 · BLD 30 · Hot RB 28 · Hot RJ 22 · RJ 15. **(เดิม else=Normal+50 → Moderate/TLD/BLD = 65% ของลีดได้ +50 เท่า Very Hot → "เคสธรรมดาดูฮอท")**
- **tier**: hot ≥55 · warm ≥35 · cold <35 (ปรับลงจาก 80/50 หลังตัดรถ) → distribution จริง ~3% hot / 30% warm / 67% cold
- แก้คะแนน Type → แก้ `_LEAD_SCORE_DEFAULTS` + sync help modal `showLeadScoreHelp()` (seller.html) ให้ตรง

### Date parsing
[fetch_dashboard.py](dashboard/services/fetch_dashboard.py) มี `parse_date()` รองรับ:
- Excel serial date (เลข 4-5 หลัก)
- "d/m/yy" หรือ "d/m/yyyy" (รองรับ พ.ศ. แปลงเป็น ค.ศ. ถ้า year > 2500) — **ต้องมี 3 ส่วน (มีปี)** ไม่งั้นคืน None
- **⚠️ ต้นเหตุ "วันที่ไม่มีปี" = `FORMATTED_VALUE` (ไม่ใช่แอดมินลืมพิมพ์ปี)**: ทุกการอ่านชีตใช้ `valueRenderOption=FORMATTED_VALUE` ([google_sheets.py](dashboard/services/google_sheets.py)) = คืนค่า **ตามที่แสดงในชีต**. เซลล์วันปล่อย (W/X) ของบางเซลล์เป็น **วันที่จริง (serial)** แต่ตั้ง custom format ให้โชว์แค่ `d/m` → API คืน `"10/2"` ปีหายไป (ค่าจริงคือ serial 46063 = 2026-02-10 · กดเข้าไปในชีตเห็นปีครบ). พิสูจน์ด้วย `UNFORMATTED_VALUE`. **ไม่ใช่ data เสีย** — แค่รูปแบบเซลล์
- **`parse_month_day(s)` → `(month, day)` หรือ None** — รองรับทั้งวันเต็ม (ผ่าน `parse_date`) **และแบบไม่มีปี `"d/m"` (เช่น `"10/2"` ที่ได้จาก FORMATTED date)**. ใช้ใน daily bucket (กราฟ + KPI "ปิดได้") ให้นับเดือนเดียวกับ `get_month()` (ที่ใช้ใน monthlySummary) — **กันบั๊ก "9 vs 10"**: เดิม daily ใช้ `parse_date` ตรงๆ ซึ่งต้องมีปี → `"10/2"` parse ไม่ได้ → ตกไปนับตามวันจอง (คนละเดือน) ทำให้ KPI/`buildRangeMs` ≠ ตารางรายเดือน. `_parse_day()` (nested 2 จุด: daily หลัก + `fetch_seller_stats`) เรียก `parse_month_day` แล้ว · frontend `_effDate` (renderBookings) ก็เติมปีของช่วงให้วันปล่อย "d/m" เช่นกัน
- **`get_month(s)`** lenient ดึงเลขเดือนจาก `parts[1]` ตรงๆ (ไม่ต้องมีปี/วันถูก) → ใช้ใน monthlySummary · ต่างจาก `parse_date` (strict) — 2 ตัวนี้เคยไม่ sync กันจนเกิด "9 vs 10" · **กฎ: daily ต้อง parse เดือนได้เท่า `get_month` เสมอ**
- **ทางแก้ถาวร (ถ้าอยากได้ปีจริง)**: อ่านคอลัมน์วันที่แบบ `UNFORMATTED_VALUE` (ได้ serial → `parse_date` แปลงพร้อมปีจริง) แต่กระทบการ parse คอลัมน์อื่น (string/number) → ยังไม่ทำ · ตอนนี้ `parse_month_day` พอสำหรับการนับ (dashboard เป็น single-year อยู่แล้ว)

### Date filter (กรองเดือน / ช่วงวัน)
- **`index.html` หน้าหลัก = ช่วงวันที่ (จาก-ถึง ข้ามเดือนได้)** — แทน month/today filter เดิม:
  - State: `dfFrom`/`dfTo` ("YYYY-MM-DD") · `inRange(ds)` เช็ค dateIn อยู่ในช่วง · `ir = inRange`
  - `buildRangeMs()` = สร้าง summary+**sellers+teams** ของช่วง (รูปร่างเหมือน `monthlySummary[m]`) จาก **`dailyByMonth`/`dailyBySeller`** (lead/RJ/จอง/ปล่อย/ยอด รวมรายวัน) + **`followCases`** (ติดตาม) — bans/leadDist รวมรายเดือน (whole-month). cache ต่อ render (`_rmCache`)
  - **ทุกค่าที่โชว์ผูกกับช่วงวันที่**: KPI cards · scorecard(`buildDilMap`) · **ตารางรายเซลล์ (`_sval` ใช้ `ms.sellers` เสมอ ไม่เช็ค dfMonth)** · **team breakdown (`ms.teams`)** · team modal (filter `ir(b.date)`) · กราฟ (rangeDays) — แก้ bug เดิมที่ `_sval`/team อ่าน `dfMonth` (vestige=0) เลยโชว์รายปีเสมอ
  - **★ ADMIN (เทเลเซลล์) ในตารางรวม (มิ.ย.69)**: ADMIN ไม่อยู่ใน `dailyBySeller` → `buildRangeMs` เคยใส่ entry เป็น **0 ทั้งหมด** (วน `D.sellers` ครบรวม ADMIN แต่ `_sumDaily({})`=0). แก้: `buildRangeMs` + `buildDilMap` + `_sval` เช็ค "ไม่มี dailyBySeller" → ดึงจาก **monthlySummary รวมเดือนในช่วง** แทน → ADMIN โผล่ทั้งตารางสรุป + ตารางคะแนน + ผ่าน `rangeActiveSellers` อัตโนมัติ. **Conv% ของ ADMIN = `ปล่อย÷lead` เหมือนเซลล์ทุกคน (ก.ค.69)** — เดิม special-case ใช้ `จอง÷lead` (เพราะ ADMIN ปล่อย=0) แต่พอเทเลเซลล์มีเครดิตปล่อยได้แล้ว (มาร์ค ADMIN ทำเอง) เลยเอา special-case ออก คิดจากจบ/ปล่อยเหมือนกันหมด (การ์ด "สรุปรายเซลล์" ใน [index.html](dashboard/templates/dashboard/index.html))
  - **เป้า (target) รายเดือน → สเกล × `rangeMonthCount()`** (จำนวนเดือนที่ช่วงครอบ) เพราะ TARGETS ในชีตเป็นเป้า/เดือน (โอ๊ต 8, เฟิร์ส 12...)
  - **`daily_by_seller` รวม orphan/inactive ด้วย** (`_daily_names`) → เซลล์เก่ากรองตามช่วงวันได้ ไม่งั้นโชว์ 0
  - **กรองรายชื่อเซลล์ตามช่วง (`rangeActiveSellers()`)**: ใน `render()` มุมมองรวม (`canViewAll && !impersonate`) กรอง `sellers` ให้เหลือเฉพาะคนที่ **มีกิจกรรมในช่วงที่เลือก** (lead/จอง/ปิด/ยอด/ติดตาม จาก `ms.sellers` + คลิป `la.clips` + ไลฟ์ `la.sessions.hosts` filter `ir(date)`) → ทุกแท็บ (ภาพรวม/เซลล์/LEAD/ไลฟ์) ไม่โชว์เซลล์เก่าที่ไม่มีข้อมูลในช่วง. ดูคนเดียว/impersonate = ไม่กรอง (กันหน้าว่าง)
  - **`NON_SELLER_NAMES`** ([fetch_dashboard.py](dashboard/services/fetch_dashboard.py)) ตัดคำสถานะ (จอง/ส่งมอบ/คืนเคส/จ่ายใหม่/ยกเลิก/(ว่าง)/ติดตาม...) ออกจาก orphan sellers — กันคำที่กรอกผิดลงคอลัมน์ชื่อเซลล์โผล่เป็น "เซลล์เก่า"
  - `dfMonth=0` vestige (โค้ดเก่าอ้าง) · `setDf(m)` ตอนนี้ map เป็นช่วงวัน (กดบาร์เดือนในกราฟ → ทั้งเดือนนั้น)
  - vacant ไม่มีรายวัน → overview KPI ไม่ใช้ (มีแค่หน้า seller detail)
- _(เดิม `<input type="month">` + `dfMonth` 0/-1/1-12 — เปลี่ยนเป็นช่วงวันแล้ว)_
  - `seller.html` ใช้ `fMonth` (เดือน) + `fDateFrom`/`fDateTo` (ช่วงวัน, "YYYY-MM-DD") — mutually exclusive (เลือก month → ล้าง range, เลือก range → ล้าง month). UI มี 2 แถว: เดือน + ช่วงวัน
    - **ปุ่มลัด = เหมือนหน้าหลัก (มิ.ย.69)**: `setRangeMonth()` "เดือนนี้" = ต้นเดือน→**สิ้นเดือน** (default ก็ถึงสิ้นเดือน) · `setRangeYear()` "ทั้งปี" = ม.ค.→**31 ธ.ค.** (เดิมทั้งคู่ถึงแค่วันนี้)
    - **UI หน้าเซลล์อื่นๆ (มิ.ย.69)**: ลบกราฟยอดปล่อย (เหลือ KPI ตัวเลข) · Pipeline funnel → 4 กล่อง KPI · KPI cards+chip โทร ย้ายลงไปติด lead list (ตัวกรอง อยู่ใกล้สิ่งที่กรอง) · banner "เคสไม่มีสถานะ X" (nudge เบาๆ ให้ใส่ Z) บนสุด
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

> _(เอาตาราง "รายงานรายเซลล์ (ละเอียด)" ออกแล้ว มิ.ย.69 — ข้อมูลซ้ำกับตาราง "สรุปรายเซลล์" ด้านบน · ถ้าจะกู้คืน ดู git history บล็อก `_aRows`/`_msSum`/`_tabMonth` ใน [index.html](dashboard/templates/dashboard/index.html))_

**★ ตารางสรุปเต็มรายเซลล์ (mega table · ก.ค.69)** — `_row(s)`/`_RC` cols ใน [index.html](dashboard/templates/dashboard/index.html) (`if(canViewAll)`) · ทุกคอลัมน์ตามตัวกรองวันที่ · คอลัมน์: เป้า(×`rangeMonthCount`)/จองเดือน/จอง/รอผล/รอปล่อย/ปล่อย/จองรายวัน(จอง÷วันที่ผ่านไป)/วันไฟแนนซ์(ผล→ปล่อย ตัดเคสวันผิด)/Lead/RJ/ไลฟ์/คลิป/ONHAND · จัดกลุ่มตามทีม + subtotal + total (คอลัมน์คะแนน=เฉลี่ย · ยอด=ผลรวม)
- **🎨 โฟกัสเซลล์ (sellerFlags)**: dropdown สี ⚪/🟡/🔴 ต่อเซลล์ → ระบายทั้งแถว (`_FLAGS=D.sellerFlags`, `_flagBg`, `_setSellerFlag` optimistic) · เก็บชีต **"โฟกัสเซลล์"** (`SHEET_CONFIG["seller_flags"]` · cols เซลล์|สี) ผ่าน `/api/admin/seller_flags`
- **📋 ONHAND (รถในมือรายสัปดาห์ · กรอกมือ)**: คอลัมน์ ONHAND ในตาราง · แอดมินกรอกยอดรถในมือต่อเซลล์ราย **สัปดาห์ (ตัดรอบทุกวันพฤหัส · week-of-month)** ผ่านฟอร์ม (`openOnhandForm`/`saveOnhand`) → เก็บชีต **"ONHAND รายสัปดาห์"** (`SHEET_CONFIG["onhand_config"]`) ผ่าน `/api/admin/onhand_config` (`_onhand_now`/`_onhand_key(ym,wk)` ใน [views.py](dashboard/views.py)) · ดู/แก้สัปดาห์ย้อนหลัง + เดลต้าเทียบสัปดาห์ก่อนได้

**★ ตาราง "Lead → จอง → จบ (แยกช่องทาง)" (ส.ค.69 · การ์ด `#leadconv-card` แท็บ LEAD)** — ช่องทางไหนได้ลีดเยอะ ปิดจองกี่ % จบจริงกี่ % · คอลัมน์: ช่องทาง | Lead | จอง | จบ | จอง/Lead | จบ/จอง | จบ/Lead · นับตามช่วงวันที่ (Lead=วันรับลีด · จอง=วันจอง · จบ=วันปล่อย)
- **⚠️ ชื่อช่องทาง 2 ฝั่งไม่ตรงกัน**: ฝั่งลีดเป็น dropdown (26 ค่าสะอาด) แต่**ฝั่งจองพิมพ์มือ 198 แบบ ตรงกันเป๊ะแค่ 8** (`Line@`/`line@`/`LINE@`/`": line@"` · `Live tiktok ช่องขายบอส`/`Tiktok ช่องขายบอส`/`ไลฟ์ TT ช่องขายบอส`) → นับตรงๆ ไม่ได้
- **วิธีเทียบ (`_attach_clean_channel` ใน [fetch_dashboard.py](dashboard/services/fetch_dashboard.py))**: (1) ใช้ **รหัสลีด** หาช่องทางจากชีตลีดก่อน (แม่นสุด · ครอบคลุม ~55%) → (2) ไม่มีก็ **ล้างชื่อ** (`_norm_channel` ตัดตัวพิมพ์/ช่องว่าง/`":"` นำหน้า + รวม live tiktok↔tiktok) แล้วเทียบกับชื่อฝั่งลีด → **รวมครอบคลุม 94-95%** · เก็บผลใน `bookingCases[].channelClean` (`''` = จับไม่ได้ → แถว "ไม่ระบุ")
- **ช่องทางที่ Lead=0 แต่มีจอง/จบ ถือว่าปกติ** (เช่น "หน้าร้าน" = ลูกค้าเดินเข้ามาเอง ไม่มีลีด) — % จะโชว์ `–`

**★ ตาราง "รายงาน จอง / อนุมัติ / ปล่อย" (ก.ค.69)** — เลย์เอาต์ตามชีต DL37:DX53 · ข้อมูลแดชบอร์ดสด ตามตัวกรองวันที่ · [index.html](dashboard/templates/dashboard/index.html) `_rpt`/`_RC`/`_rc`
- คอลัมน์: จองทั้งหมด/รอผล/รอปล่อย/ปล่อย/%การจอง/Lead/RJ/เฉลี่ยLead/วัน/ไลฟ์/คลิป/Lead ไลฟ์
- **เรียง: (ปล่อย+รอปล่อย) มากสุด → รองด้วยจอง** (`_rpt` sort)
- **สีแถวอัตโนมัติ `_rc(ปล่อย+รอปล่อย)`: เขียว ≥5 · เหลือง 3-4 · แดง ≤2** (ไม่มีขาว · `_flagBg` เพิ่มเคส `'g'`=เขียว)
- **จอง/ปล่อย** = tab-based (จาก `_sval`) · **รอผล/รอปล่อย** = `monthlySummary[_cm].pipeBySeller` (`_mpipe(name)` · นับตามแท็บ ตรงสูตรชีต · ดู section "Source of truth")

1. **🚗 Lead รถรุ่นยอดนิยม** — top cars by lead count
   - **ไม่นับ RJ ทุกประเภท** (มิ.ย.69) — `lead_cars_by_month`/`lead_car_seller_month` skip `cell(r,L.type) in RJ_TYPES` (ทั้งตารางรวม + modal รายเซลล์) → ~10,680 เคส (จาก ~15k)
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
   - **✏️ Inline edit วันที่ timeline** (เซ็น/ผล/ปล่อย) — ในหน้ารายละเอียดเคส (`openBookingDetail` → `_dateEditRow(label,val,col,idx,hint)`/`saveTimelineDate(idx,col)`) แต่ละแถวมี **`<input type=date>`** (แปลง d/m/yyyy ↔ YYYY-MM-DD ด้วย `_toISODate`/`_fromISODate`) + ปุ่มบันทึก → POST `/api/admin/update_release_date` (body `col`) → เขียนกลับชีตตรง cell. **col** (allow `2,14,18,19,20,21,23`): วันจอง=2(C) · เซ็น=14(O) · ผล=`resultCol`(20 พ.ค.+/19 เดือนก่อน) · ปล่อย=`releaseCol`(23/21). **เอกสารครบ(18) อ่านอย่างเดียว**. **★ วันจองแก้ได้ (มิ.ย.69)**: เคสวันจองปีผิด (เช่น 17/6/1969 — Sheets แปลงปี 2 หลักผิดตอนกรอก → เคสอายุ 2 หมื่นวัน) แก้ได้แล้ว (เดิม read-only) · ผล/ปล่อย อ่าน-เขียนคอลัมน์ตามเดือน (`resultCol`/`releaseCol`) ให้ตรงกัน ไม่งั้น "บันทึกแล้วไม่ติด". ตำแหน่งมาจาก `bookingCases[].sheetTab`/`sheetRow`/`releaseCol` ที่ `fetch_sales_by_month_tabs` แนบไว้ (**col 28=tab name, col 29=แถวในชีต 1-based** ต่อท้าย flattened row · `releaseCol`=23(X พ.ค.+)/21(V เดือนก่อน) จาก `_release_col(r)`). optimistic อัปเดต local (mirror ตามทันรอบ sync ถัดไป) · `sheetTab` ว่าง → read-only
   - **มีทั้ง 2 หน้า**: `index.html` (แอดมิน) + **`seller.html` (เซลล์แก้เคสตัวเอง)** — seller.html มี banner "ปล่อยแล้วยังไม่ลงวันส่งมอบ" (เหนือ filter bar) ลิสต์เคส → กดเปิด `openBookingDetail` ลงวันได้เลย. เซลล์ส่ง `token` ใน body → endpoint เช็ค ownership (ชื่อที่ marker = ตัวเอง) ก่อนเขียน · `/me/` ใช้ session seller_name

### 🤖 AI Insights (Gemini)
ฟีเจอร์ช่วยเซลล์/แอดมินอ่านตัวเลขเป็นภาษาคน — เรียก Gemini ผ่าน REST (`requests`) ไม่มี SDK · cache ในหน่วยความจำ 30 นาที (กันยิงซ้ำ/เปลืองเงิน):
- **โค้ชเซลล์** (`gemini_insights.analyze_seller(name, stats_text)`) — วิเคราะห์จุดแข็ง/จุดต้องแก้ + แผนรายสัปดาห์ของเซลล์คนเดียว → ผ่าน `/api/insights/seller` (login ใครก็ได้)
  - **stats อิงตัวกรอง (มิ.ย.69)**: `aiStatsSummary()` ใช้ `_aiStats` (render() เซ็ตทุกครั้งจาก leadsInRange/bookingsInRange) → เลือกเดือนนี้/ช่วงไหน AI วิเคราะห์อันนั้น (เดิม hardcode เดือนปัจจุบัน+ทั้งปี). forecast ยังใช้ทั้งปี (เป็น "พยากรณ์เทรนด์")
- **พยากรณ์ยอด** (`forecast_narrative(summary_text)`) — อธิบายเทรนด์ยอด + ปัจจัยตลาด (น้ำมัน/EV/เศรษฐกิจ) + กลยุทธ์ 2-3 ข้อ สำหรับเจ้าของเต็นท์ → ผ่าน `/api/insights/forecast` (admin/exec)
- env: `GEMINI_API_KEY` + `GEMINI_INSIGHTS_MODEL` (default `gemini-2.5-flash` — เบา/ถูก สำหรับงาน narrative)

### 📸 OCR สแกนเอกสาร + ฟอร์ม finance/loan (ช่วงทดสอบ)
เซลล์ในหน้า `seller.html` ถ่ายรูป/อัปโหลดเอกสาร → Gemini vision อ่าน field → กรอกฟอร์มอัตโนมัติ (ฉบับร่างให้ตรวจก่อนส่ง) → ส่ง LINE Flex:
- **สแกน** (`/api/seller/scan_doc`) — base64 ≤8MB + `form`(`finance`\|`loan`) → `gemini_ocr.extract_finance_fields()` (27 field) / `extract_loan_fields()` (59 field) · JSON schema mode, temperature=0, field ที่ไม่เจอ=ค่าว่าง (ไม่เดา) · env `GEMINI_API_KEY` + `GEMINI_MODEL` (default `gemini-3.1-pro-preview` ใน settings.py)
- **เช็คไฟแนนซ์ก่อนเซ็น** (`/api/seller/finance_check`) → `build_finance_check_flex` → push เข้า **`FINANCE_TEST_LINE_ID`** (ยังไม่ส่งเข้ากลุ่มจริง — ช่วง test) + เก็บ Supabase `finance_checks`
- **ขอสินเชื่อ** (`/api/seller/loan_submit`) → `build_loan_flex` → push เข้า `FINANCE_TEST_LINE_ID` + เก็บ Supabase `loan_applications`
- ⚠️ `FINANCE_TEST_LINE_ID` เป็น hard requirement (ไม่มี = 500) — กันส่งผิดปลายทางช่วง test · ต้องตั้ง `LINE_CHANNEL_ACCESS_TOKEN` ด้วย

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
| `admin_config` | (เดียวกับ employees) | **"ตั้งค่าแอดมิน"** | รายชื่อ LINE user_id ที่เป็นแอดมิน (สิทธิ์แอดมิน) — `ADMIN_USER_IDS` |
| `tele_config` | (เดียวกับ employees) | **"ตั้งค่าเทเลเซลล์"** | รายชื่อ LINE user_id ของเทเลเซลล์ (ทีมโทร · เคสรวมเป็น seller "ADMIN" · ไม่ใช่สิทธิ์แอดมิน) — `TELE_USER_IDS` |
| `onhand_config` | (เดียวกับ employees) | **"ONHAND รายสัปดาห์"** | รถในมือต่อเซลล์รายสัปดาห์ (แอดมินกรอกมือ · `/api/admin/onhand_config`) |
| `seller_flags` | (เดียวกับ employees) | **"โฟกัสเซลล์"** | สีโฟกัสต่อเซลล์ (เซลล์\|สี ⚪/🟡/🔴) ในตารางสรุป (`/api/admin/seller_flags`) |

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

### 🗄️ ที่เก็บผล (store) — VPS ใช้ PostgreSQL ในเครื่องแทน Supabase (มิ.ย.69 หลังย้าย Hostinger)
ตอนขึ้น VPS เปลี่ยน "ที่เก็บผลสรุป" จาก Supabase (REST) → **PostgreSQL ในเครื่อง** (ตัวเดียวกับ cars/) ผ่าน **facade [cache_store.py](dashboard/services/cache_store.py)**:
- `cache_store.*` เลือก backend อัตโนมัติ: **Supabase ถ้า `USE_SUPABASE=True`+ตั้งครบ · ไม่งั้น local Postgres** ([local_store.py](dashboard/services/local_store.py) · Django ORM) — โหมดหลักบน VPS
- โมเดล [dashboard/models.py](dashboard/models.py): **`KVStore`** (`dash_kv` · key→json: dashboard cache key='main', `cron_tick`/`cron_followup` heartbeat, `sheet_config` override blob) + **`FormSubmission`** (`dash_form` · ฟอร์ม finance/loan)
- ทุก call site เรียกผ่าน `cache_store` (ไม่เรียก `supabase_client` ตรง): `fetch_dashboard_data`/`precompute_dashboard`, `cron_tick` (warm+kv), `system_health`, `admin_sheet_config`, `cron_sync`, `_save_form`, `load_sheet_config_overrides`
- **ดีกว่า Supabase**: local ไม่วิ่งเน็ต (~50ms) · ไม่เจอ NANO timeout ที่เคยทำเว็บล่ม · ฟีเจอร์ครบเท่าเดิม (heartbeat/ย้ายแหล่งข้อมูล/ประวัติฟอร์ม)
- `supabase_client.py` ยังอยู่ (facade เรียกเมื่อ `USE_SUPABASE=True`) — เปิด Supabase กลับได้โดยไม่แก้ call site
- ต้อง `migrate` (สร้าง `dash_kv`/`dash_form`) — รันในขั้น deploy อยู่แล้ว · ไม่มี DB = best-effort คืน None/{} (ไม่พัง)

### ⚡ Pre-compute dashboard (แก้ "ยิ่งข้อมูลเยอะยิ่งช้า")
แทนที่จะอ่าน 15k lead + aggregate สดทุกโหลด → **คำนวณล่วงหน้าเก็บผลไว้ คนเข้าเว็บอ่านผลสำเร็จรูป** (เร็วคงที่ ไม่ขึ้นกับจำนวนข้อมูล):
- **(VPS) store = Postgres ในเครื่อง ผ่าน `cache_store`** (เดิม Supabase) · `cron_tick` อุ่น cache ทุกนาที (threshold 120 วิ) → ทุก gunicorn worker อ่าน store ที่อุ่นแล้ว = **dashboard อุ่นตลอด** ไม่มีใครเจอ recompute สด ~8.5 วิ (ยกเว้น cold start)
- `precompute_dashboard()` ([fetch_dashboard.py](dashboard/services/fetch_dashboard.py)) — คำนวณ `_compute_dashboard_data()` 1 ครั้ง → เก็บลง Supabase table **`dashboard_cache`** (1 แถว key='main', `data` jsonb)
- `fetch_dashboard_data()` อ่านเร็ว→ช้า: **in-memory (30s)** → **ผล pre-compute Supabase** (fresh<5นาที ใช้เลย · **stale ก็ใช้** ดีกว่าคำนวณใหม่) → ของเก่าใน memory → คำนวณสด (cold เท่านั้น)
  - **⚠️ stale-while-revalidate กันลูกโซ่ล่ม (มิ.ย.69)**: เดิมถ้าอ่าน cache ไม่ทัน (Supabase timeout) จะ **คำนวณสด 121 วิ ทันที** (อ่าน 15k + เขียนกลับ) → ยิ่งไปรุม DB ที่อ่อน (NANO) → ทุก request ตายลูกโซ่. ตอนนี้ **user request ห้าม trigger recompute ถ้ามีของเก่าเสิร์ฟ** — recompute เป็นงานของ cron/ปุ่มรีเฟรชเท่านั้น (ดู "บทเรียน NANO ล่ม" ในโค้ด)
  - **followCases ผอมลง (มิ.ย.69)**: เก็บแค่ 8 field ที่ frontend+`compute_diligence_scores` ใช้ (ตัด phone/channel/adminStatus/customerStatus/followPriority/callProof/profile/timeIn) → precompute 3.3→2.35 MB เขียน NANO ได้ง่ายขึ้น. **อย่าเพิ่ม field ที่ไม่ได้ใช้กลับ** (seller.html ใช้ `D.leads` ไม่ใช่ followCases)
- รีเฟรชโดย: **`cron_tick`** (cron ยิงทุก 1 นาที — ถ้าผลเก่า **>30 วิ** → recompute · refresh ~ทุก 1 นาที) + `cron_sync`. ใช้ cron tick ตัวเดียว ไม่ต้องสร้าง cron sync แยก.
  - **threshold = 30 วิ (มิ.ย.69 · refresh ~ทุก 1 นาที)** [views.py `cron_tick`]: Phase 2 ตัด raw mirror แล้ว → `sync_all_sheets_to_supabase()` เป็น **no-op** · recompute = precompute อย่างเดียว (อ่าน Google ~8s + เขียนผล 3MB · รวม ~15-23s) **เบากว่ายุค raw mirror มาก** จึงลด 180→30 ได้. recompute ~23s < tick 60s → ปกติไม่ซ้อน
  - **⚠️ ยังไม่มี distributed lock**: ถ้า cold start ดัน recompute >60s อาจซ้อน (rare) → เจอบ่อยให้ขยับ threshold ขึ้น หรือเพิ่ม kv lock (set_kv ก่อน recompute, skip ถ้า lock สด)
  - **บทเรียนเก่า (7 มิ.ย.69 server ล่ม · ก่อน Phase 2 — ตอนนี้ obsolete)**: ยุค raw mirror เคยตั้ง 45 วิ → ทุก tick upsert leads 15k ~1440 ครั้ง/วัน + sync ซ้อน → ล่ม (commit 977eeae) · เคยตั้ง "ห้ามลดต่ำกว่า 120". **ไม่ applicable แล้ว** เพราะไม่มี raw mirror (sync ไม่ทำอะไรหนัก)
- `upsert_sheet()` ตัด cell ว่างท้ายแถว (`_trim_row`) ลดขนาด jsonb — กัน leads (15k) เขียนชน Supabase statement timeout
- **ไม่แตะ Sheet เพิ่ม** — pre-compute อ่าน mirror (Supabase) ไม่ใช่ Sheet · Sheet ถูกอ่านแค่ตอน sync (~15-20 req ทุก ~5 นาที)
- SQL: `create table if not exists dashboard_cache (key text primary key, data jsonb, updated_at timestamptz default now());`
- ปลอดภัย: ไม่มี table = fallback คำนวณสดเหมือนเดิม (ไม่พัง)

#### 🆕 แผนสถาปัตยกรรม sync ถัดไป (ตัดสินใจแล้ว มิ.ย.69 — ยังไม่ลงมือ · รอทำ)
**สรุปการตัดสินใจ**: เก็บใน Supabase แค่ **"ผลคำนวณสำเร็จรูป" (dashboard_cache ~3MB)** · **ไม่ mirror leads 15k แถวดิบ** · ใช้ **timer (n8n) ทุก ~5-10 นาที** เป็นตัวสั่งคำนวณ · เว็บอ่าน Supabase อย่างเดียว

**ทำไม (ต้นเหตุเว็บ 3 นาที + Supabase ล่ม มิ.ย.69)**:
- ตัวที่ทำ CPU Supabase เต็ม/ค้าง = upsert **leads 15k แถวดิบ** เข้า `sheet_cache` ทุกไม่กี่นาที (jsonb ก้อนใหญ่ + sync ซ้อนไม่มี lock) — **ไม่ใช่** "อ่าน Sheet สดทุก visit" (เว็บอ่าน precompute อยู่แล้ว)
- เว็บช้า 3 นาทีเพราะ **รอ Supabase timeout (30+60+90 วิ)** ตอน DB ป่วย ไม่ใช่เพราะการคำนวณ — วัดจริง: คำนวณสดจาก Google = **8.5 วิ** · ผล precompute ~3MB

**สถาปัตยกรรมเป้าหมาย**:
- timer (n8n ~5-10 นาที) → ยิง endpoint เบา → `_compute_dashboard_data()` (อ่าน Google ~8.5 วิ) → เก็บ **เฉพาะผลสรุป** ลง `dashboard_cache`
- **เลิก `sheet_cache` (mirror 15k ดิบ)** — ตอน sync ให้ `_compute_dashboard_data` อ่าน Google ตรง (`USE_SUPABASE=False` ทำให้ `fetch_all_sheets` อ่าน Google อยู่แล้ว) ไม่อ่าน mirror อีก
- เว็บอ่าน `dashboard_cache` ก้อนเดียว → ~1-2 วิ · ไม่แตะ Sheet · ไม่คำนวณเอง · CPU Supabase แทบไม่ขยับ → **free tier อยู่ได้ยาว**
- เปลี่ยนไฟล์ปีใหม่ = แก้ `sheet_config` แถวเดียว (ไม่ต้อง deploy / ไม่ต้องติดตั้งสคริปต์อะไร)

**ห้ามทำ (บทเรียน + ที่ประเมินแล้วไม่เข้ากับแอปนี้)**:
- ❌ อย่า mirror leads 15k แถวดิบเข้า Supabase อีก = ต้นเหตุ CPU เต็มโดยตรง
- ❌ อย่าให้เว็บอ่านแถวดิบมา aggregate เอง / pagination ราย 50-100 แถว — แอปนี้เป็น dashboard **"สรุปยอด"** ต้องใช้ครบทุกแถวมาคำนวณ KPI → pagination ใช้ไม่ได้ (ต้นทุนจริงคือ "การรวมยอด" ไม่ใช่ "การดึงแถว")
- ❌ ไม่ต้องคิดเรื่อง connection pooler / port 6543 — ระบบคุย Supabase ผ่าน **REST (PostgREST)** ไม่เปิด Postgres connection ตรง (`DATABASES={}`)
- ❌ อย่ายัดหลายปีในไฟล์เดียว (5 ปี ≈ 7.5M cell ใกล้ชน 10M + ไฟล์ ~180k แถว อืดทั้งคนกรอกและ API) → แยกไฟล์รายปีตามเดิม
- Apps Script `onEdit` (sync ทันทีที่แก้) = ทำได้แต่ซับซ้อน (ติดตั้งทุกไฟล์ข้อมูล + ตั้งใหม่ทุกปี + พลาด edit ที่มาจากสูตร/API/import + ต้อง debounce + ต้องมี timer สำรองอยู่ดี) → เก็บเป็น **option เสริมทีหลัง** ไม่ใช่ตัวหลัก · งานเบื้องหลัง (คำนวณ+เก็บผล) เหมือน timer เป๊ะ ต่างแค่ "ตัวกดปุ่ม"

**ไฟล์ต้นทางปัจจุบัน = 5 ไฟล์** (ข้อมูล 4: leads/sales_reports/bookings/live · ตั้งค่า 1: employees) — Apps Script ถ้าทำต้องติดตั้งในไฟล์ข้อมูล 4 ไฟล์

**สถานะ**:
- ✅ **Stopgap ทำแล้ว (มิ.ย.69)** — ลบ Supabase project ทิ้ง → ระบบอ่าน Google ตรง: `USE_SUPABASE` default = **False** ([settings.py](oxlet/settings.py)) · `is_configured()` คืน False เมื่อ USE_SUPABASE ปิด → ทุก Supabase call short-circuit ไม่ค้าง · `fetch_dashboard_data()` เพิ่มทาง "ไม่มี Supabase = อ่าน Google + cache memory `_LOCAL_TTL`=180s (หมดอายุ→คำนวณใหม่)". วัดจริง: cold ~8s · warm ~0s · ไม่มี timeout 15s แล้ว
- ⬜ **Phase 2 (ยังไม่ทำ)** — ถ้าอยากได้ sub-second + อุ่นตลอด: สร้าง Supabase free ใหม่ (เก็บแค่ผลสรุป ~3MB) + timer (n8n) สั่งคำนวณ → เปิดด้วย env `USE_SUPABASE=True` (โครงโค้ดรองรับแล้ว) · **อย่า mirror leads ดิบกลับ**
- งานแก้ login (เหลือ LINE Login) deploy ไปแล้ว (ไม่เกี่ยวกับงานนี้)

#### Supabase tables ทั้งหมด (`supabase_client.py`)
- **`sheet_cache`** — mirror ของ 6 sheets หลัก (leads/sales_reports/bookings/live_sessions/live_followups/employees) · `upsert_sheet`/`get_sheet`/`sync_all_sheets_to_supabase` · lazy background sync ถ้าเก่า >120s
- **`dashboard_cache`** — (1) pre-compute dashboard (key='main') (2) **kv** สถานะ/heartbeat (`set_kv`/`get_kv`): `cron_tick`, `cron_followup` log → หน้าสถานะระบบ
- **`sheet_config`** — override แหล่งข้อมูล (ย้ายไฟล์/tab จากแอดมิน) — ดู section ย้าย spreadsheet ด้านบน
- **`finance_checks` / `loan_applications`** — เก็บฟอร์ม finance/loan ที่เซลล์ส่ง (best-effort) · `ping()` เช็คว่ามี table ครบไหม
- ทุก helper เป็น **silent-fail** — Supabase ล่ม/ไม่ตั้งค่า = ระบบ fallback อ่าน Sheet สด ไม่พัง

**Helpers**:
- `fetch_sheet(key)` — อ่าน 1 tab ตาม SHEET_CONFIG.
- `fetch_leads_by_month_tabs()` — **default สำหรับทุก dashboard** — อ่านจาก monthly tabs (ม.ค.-ธ.ค. 69) **filter ให้แต่ละ row อยู่ใน tab ของเดือนตรงกับวันที่ใน column** (ตัดแถวที่ admin เอามาใส่ผิด tab ออก). ไม่ dedup. ตรงกับการนับ raw ใน Google Sheet ที่ admin คาดหวัง. **ใช้ใน**: `fetch_all_sheets()` (main dashboard), `seller_dashboard`, `line_notify.build_seller_pipelines()`
  - ตัวอย่าง พ.ค. 2026: tab "พฤษภาคม 69" raw=3,101 → filter date=พ.ค. → **2,585 เคส** (ตัด 516 เคสที่ admin เอาเคสเม.ย./มี.ค./ก.พ. มาใส่ tab พ.ค. ออก)
  - **ทำไมไม่ใช้ dedup**: `fetch_leads_dedup` ทำให้ lead เดือนนี้หาย ~30 เคส (2,552 vs 2,582) เพราะ code ซ้ำ + monthly tab override ทำ code "ย้ายเดือน". `fetch_sheet("leads")` ก็ inflated +83 จาก dup ภายใน 'รวม sheet' + orphan codes
  - Failsafe: ถ้า monthly tabs fetch ไม่ได้/ว่าง → fall back ไป `fetch_sheet("leads")`
- `fetch_sales_by_month_tabs()` — **default สำหรับ sales_reports** — อ่านยอดขายจากแท็บรายเดือน **`<เดือน>69` (ไม่เว้นวรรค)** ตรงๆ แทน "รวม sheet" (ที่ใช้สูตร REDUCE). แต่ละแท็บจัดกลุ่มตามเซลล์ด้วย marker **"ชื่อเซลล์ X"** ใน column B → ดึงบล็อกของแต่ละเซลล์ (ใต้ marker ถึง marker ถัดไป), เอาแถวที่ลำดับ(B)เป็นเลข+สถานะ(N)ไม่ว่าง, prepend ชื่อเซลล์เป็น col 0 (ตรง `SALES_COL` flattened เดิม). **match ชื่อกับ `ALL_SELLERS` (dynamic) + `{"ADMIN"}`** (อ่านบล็อก "ชื่อเซลล์ ADMIN" ด้วย) → เซลล์ใหม่เพิ่มเองอัตโนมัติ. **★ (ก.ค.69) อ่านบล็อกชื่ออื่นที่มีเคสจริงด้วย — เซลล์ลาออก/เทเลเซลล์ (เช่น "ใบตอง")**: เดิมตัดบล็อกที่ชื่อไม่อยู่ใน ALL_SELLERS ทิ้ง → เคสของเซลล์ที่ออกไปแล้ว/เทเลเซลล์ที่มีบล็อกชื่อตัวเอง **หายทั้งบล็อก** (เช่น ใบตอง พ.ค.: ปล่อย 1/รีเจ็ก 8/จอง 13 → ทำ dashboard นับปล่อย พ.ค. 51 แทนที่จะเป็น 52 ตามสูตรชีต). ตอนนี้ **บล็อกไหนมีเคสจริง (seq เลข + สถานะ) = อ่าน เก็บชื่อเดิม** (โผล่เป็น orphan seller ไม่มี target/team แต่ยอดนับ · ผู้ใช้: "เซลล์ออกไปแล้วเคสยังนับ แค่เดือนต่อมาไม่มีชื่อ/สิทธิ์") · **ตัดเฉพาะ marker ขยะ**: ชื่อ "A"/ว่าง/สั้นกว่า 2 ตัว หรือบล็อกไม่มีเคส. **★ ย้ายเคส ADMIN ที่อยู่ใต้เซลล์อื่น**: ถ้าแถวมี `"ADMIN"` ในคอลัมน์ AB (idx 24–29) → set seller='ADMIN' (ตัดจากเซลล์เจ้าของบล็อก) — เคสที่แอดมิน/เทเลเซลล์ดูแลแต่บันทึกใต้เซลล์. **★ มาร์ค ADMIN = "เทเลเซลล์ทำเอง" ได้เครดิตปล่อยด้วย (ก.ค.69 — เอากฎยกเว้น "ปล่อย" ออกแล้ว)**: มาร์ค "ADMIN" หมายถึง **เทเลเซลล์ทำเอง (หาลีด+ปิดเอง)** → ย้ายเป็น seller='ADMIN' **ทุกสถานะ รวม "ปล่อย"** (เทเลเซลล์มี done/dealValue ได้). กติกาแยก 2 กรณีด้วย **"มาร์คต่างคำ"**: (1) เทเลเซลล์ทำเอง = มาร์ค "ADMIN" → ปล่อยเป็นของเทเลเซลล์ · (2) เทเลเซลล์แค่หาลีดให้แล้ว **เซลล์เป็นคนปิด** = **ไม่ต้องมาร์ค ADMIN (ลบมาร์คทิ้ง)** → ปล่อยเป็นของเซลล์เจ้าของบล็อกตามปกติ. _(เดิม มิ.ย.69 บังคับเทปล่อยให้เซลล์เสมอ ทำให้เทเลเซลล์ done=0 — ยกเลิกแล้วเพราะบางเคสเทเลเซลล์ปิดเอง)_ ใช้ใน `fetch_all_sheets()` + `sync_all_sheets_to_supabase()`. Failsafe → `fetch_sheet("sales_reports")` ("รวม sheet")
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
- **`result_date_for(r)` (วันผล/อนุมัติเครดิต) — ย้ายตามเดือนเหมือนวันปล่อย**: พ.ค.+ = **U(20)** · เดือนก่อน = **T(19)** (`SALES_COL.result_date=19` = ค่าเดือนเก่า · `result_col_for(r)` คืน 20/19 สำหรับ inline edit เขียนกลับ)
  - **⚠️ บทเรียน velocity ตัน 3.3 (มิ.ย.69)**: เดิม `booking_cases` อ่านวันผลจาก `S.result_date`(19) เสมอ → เดือน พ.ค.+ ได้ค่าว่าง (ผลย้ายไป U/20) → velocity ช่วง เซ็น→ผล + ผล→ปล่อย = 0 ทุกคน → **ทุกคนตัน 3.3**. **ไม่ใช่ "ทีมไม่กรอกผล"** — ทีมกรอก (ใน U) แต่โค้ดอ่าน T. แก้ด้วย `result_date_for(r)` อ่านคอลัมน์ตามเดือน → velocity เด้งจริง (นั่ม 8.9 เฟิร์ส 7.2). **กฎ: วันผล/ปล่อยอ่านด้วย resolver ตามเดือน อย่า fix index ตายตัว**
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
- **★ overlay สถานะล่าสุดข้ามแท็บ — Z + AB(admin_status) + เซลล์(sales_status) (มิ.ย.69)**: เคสเก่า (วันที่เดือนก่อน เช่น 25/5) ถูกเอามาทำต่อในแท็บปัจจุบัน (แอดมินอัปเดต Z/AB) แต่ date-filter เก็บ copy เดือนเก่า (อิง received_date) → **สถานะที่อัปเดต (จ่ายใหม่/คืนเคส/จอง) อยู่ในแท็บใหม่ แต่ row ที่ใช้คือสำเนาเดือนเก่าที่ยังเป็นค่าเดิม** → ตามผิด/นับผิด (เคส HLD-9959/ANLD-9921 · **TLD-10187**: received 28/5 → ใช้สำเนา พ.ค.(admin=ติดตาม) แต่แอดมินใส่ "จ่ายใหม่" ใน AB แท็บ มิ.ย. → ถ้า overlay แค่ Z จะหลุดมาโดนตาม). `fetch_leads_by_month_tabs` รวบ **ค่าล่าสุด (เดือนสูงสุดที่กรอก) ของ Z+admin_status+sales_status** ต่อ `lead_code` มา **overlay** ทับ row ที่เก็บไว้ (ดู `_OVERLAY_FIELDS` · การนับเดือนยังอิงวันที่เดิม — overlay แค่สถานะ) · **กระทบทุกที่ที่อ่าน leads (dashboard/seller/followup)** — admin_status overlay ทำให้ตัวเลขที่อิง admin (จอง/ติดตาม/junk) สะท้อนแท็บล่าสุดด้วย (ถูกต้องขึ้น แต่บางเลขขยับ)
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
- `build_followup_messages()` — ข้อความ "ตามด่วน" (plain text เฟส 2) รายเซลล์ (ดู section "ตามด่วน") — ใช้ทั้ง cron + ปุ่มส่งทันที
- `build_finance_check_flex()` / `build_loan_flex()` — Flex ของฟอร์ม finance/loan (ดู section OCR) → push เข้า `FINANCE_TEST_LINE_ID`
- `load_schedules()` — อ่าน schedule sheet
- `schedule_matches_now(sched)` — เช็คว่าตาราง match เวลา BKK ปัจจุบัน

### Trigger 2 แบบ
1. **Manual** — admin กดปุ่ม "📤 LINE Flex" → tab "ส่งทันที" → POST `/api/admin/send_line`
2. **Auto** — **n8n** ยิง `/api/cron/tick?secret=xxx` ทุก 1 นาที → `cron_tick` ส่ง **followup "ตามด่วน" รายเซลล์ ตามตารางในชีต "ตั้งเวลาส่ง"** (default 09:00/13:00 · ข้อความธรรมดา · `build_followup_messages`) — **schedule sheet (เดิมคุม Flex) ตอนนี้คุม followup**: ถึงเวลาแถว enabled → ส่งตาม `test_target`/`sellers` ของแถวนั้น. manual `/api/admin/send_line` ยังใช้ Flex ได้ (`build_seller_flex`)

### Schedule format (sheet "ตั้งเวลาส่ง")
```
เวลา (HH:MM) | วัน (* / 1-5 / 0,6) | เซลล์ (* / "โอ๊ต,เก้า") | test_target | enabled (TRUE/FALSE) | ป้ายชื่อ
09:00        | 1-5                | *                       |             | TRUE                 | เช้าวันทำการ
13:00        | *                  | *                       |             | TRUE                 | เที่ยง
```
- วัน: 0=อาทิตย์, 1=จันทร์, ..., 6=เสาร์
- test_target ใส่ user_id = ส่งเข้า user นั้นแทน (test mode) / ว่าง = ส่งจริงไปทุกเซลล์

## Conventions

- **⭐ คำอธิบาย/help inline → ใช้ `.info-tip` (ปุ่ม `?` + tooltip) เสมอ** — ไม่ใช้ `<details>`/กล่องแยก สำหรับ tip สั้น ๆ:
  ```html
  <span class="info-tip" tabindex="0" onclick="event.stopPropagation()" data-tip="บรรทัด1\nบรรทัด2">?</span>
  ```
  - CSS `.info-tip` + smart-tooltip JS (กัน parent `overflow:hidden` ตัดหัว) อยู่ใน [index.html](dashboard/templates/dashboard/index.html) แล้ว · `data-tip` รองรับหลายบรรทัดด้วย `\n` · ตัวอย่าง: KPI tips, รหัสในชื่อรถ (popup สถานะรถ), RJ leads
  - tip ยาว/เป็นตาราง (เช่นรายการ 7 บทบาท) ค่อยใช้กล่อง/section แทน
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
2. ครั้งแรกต้องตั้ง **n8n** (Schedule Trigger → HTTP Request) ยิง `https://<your-app>.vercel.app/api/cron/tick?secret=<CRON_SECRET>` ทุก 1 นาที (one-time setup)

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

1. **env vars บน Vercel dashboard** (Settings → Environment Variables) — **ตั้งแค่ 8 SECRET เท่านั้น** (Vercel จำกัด ~15 ตัว). ค่าที่ไม่ลับ inline เป็น default ใน [settings.py](oxlet/settings.py) แล้ว → ไม่ต้องตั้งบน Vercel:
   - **7 SECRET (จำเป็น)**: `GOOGLE_PRIVATE_KEY`, `DJANGO_SECRET_KEY`, `OXLET_ADMIN_PASSWORD`, `LINE_CHANNEL_ACCESS_TOKEN`, `CRON_SECRET`, `GEMINI_API_KEY`, `SUPABASE_SECRET_KEY` · _(`OXLET_SELLER_PASSWORD` เลิกใช้แล้ว มิ.ย.69 — ตัด login รหัสรวมออก เหลือ LINE Login)_
   - **LINE Login (PDPA)**: `LINE_LOGIN_CHANNEL_ID`, `LINE_LOGIN_CHANNEL_SECRET` (จาก LINE Login channel) + ตั้ง Callback URL ใน channel = `https://saleforce-oxletauto.vercel.app/auth/line/callback` (ตรงกับ `LINE_LOGIN_CALLBACK`)
   - **inline แล้ว (ไม่ต้องตั้ง)**: `GOOGLE_SERVICE_ACCOUNT_EMAIL`, `SUPABASE_URL`, `USE_SUPABASE`, `GEMINI_MODEL`, `FINANCE_TEST_LINE_ID`, `OXLET_ADMIN_USER`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` — แก้ได้ใน settings.py
   - **ตัวเลือก**: `DEBUG` (default=False อยู่แล้ว ไม่ต้องตั้งก็ปลอดภัย)
   - **เลิกใช้แล้ว**: `GMAIL_APP_PASSWORD`, `EMAIL_*`, `APPROVAL_NOTIFY_EMAIL`, `SITE_URL` (ถอดระบบสมัครสมาชิก+เมลออกแล้ว มิ.ย.69)
   - **⚠️ `.env` ถูก gitignored แล้ว (ไม่ commit)** — ประวัติ git ถูกล้าง .env ออกหมดแล้ว (filter-repo + force-push มิ.ย.69). ห้ามเอา .env กลับเข้า git อีก

2. **Use canonical URL** (`your-app.vercel.app`) ไม่ใช่ deployment-specific URL (`your-app-xxx.vercel.app`) — อันยาวมี Vercel Auth wall ป้องกันอยู่

3. **n8n** (เปลี่ยนจาก cron-job.org) — workflow: Schedule Trigger (`* * * * *` ทุก 1 นาที) → HTTP Request GET `https://your-app.vercel.app/api/cron/tick?secret=<CRON_SECRET>`

4. **Service account** ต้องมีสิทธิ์ **Editor** บน Google Spreadsheet (เพื่อเขียน config sheets)

## ระบบติดตามรถ (cars/ — tracking) — merge เข้ามา มิ.ย.69

แอป Django ตัวที่ 2 ในโปรเจกต์เดียวกัน (port จาก oxlet_tracking) — ติดตามรถมือสองตั้งแต่ **รับเข้า → ถ่ายรูป → ทำสภาพ → ตรวจ(QC) → ขาย → ปล่อยรถ** (**18 สเตป/4 เฟส · รื้อใหม่ ก.ค.69 + "ซ่อมเสร็จรอตรวจ"/"รอเซลล์ตรวจรถขึ้นโชว์" ส.ค.69** — ดูหัวข้อ "รื้อสเตป+บทบาท" ด้านล่าง) เปลี่ยนสเตปด้วย QR สแกน หรือกดจากบอร์ดตรงๆ. **สีการ์ด = ความด่วน (priority) เลือกมือ ไม่ใช่วันค้าง**. **ต่างจาก sales โดยสิ้นเชิง: ใช้ DB จริง (Postgres) + Django auth/admin** — ไม่ใช่ Sheets

- **แยกขาดจาก sales**: sales (dashboard/) ยังอ่าน Google Sheets ไม่ใช้ DB เหมือนเดิม · cars/ มีตารางของตัวเอง (Car/ScanLog/Branch) ใน Postgres · 2 ระบบอยู่ deploy เดียวกันบน Vercel แต่ข้อมูล/auth แยกกัน
- **URL ทั้งหมดอยู่ใต้ `/track/`** (กันชน login/logout/หน้าแรกของ sales) — `/track/`(dashboard), `/track/kanban/`, `/track/cars/`, `/track/scan/<code>/`, `/track/qr/<code>.png`, `/track/users/`(จัดการบทบาท), `/track/login/`,`/track/logout/`. Django admin ย้ายไป **`/dj-admin/`** (เพราะ sales ใช้ `/admin/` แล้ว)
- **url name ที่ rename กันชน sales**: `dashboard→track_dashboard`, `login→track_login`, `logout→track_logout` (ใน [cars/urls.py](cars/urls.py)) · ชื่ออื่น (car_*/scan/qr_*/kanban/manage_users) ไม่ชน · **ไม่ใช้ app_namespace** (rename ตรงๆ ง่ายกว่า) — เพิ่ม url ใหม่ที่อาจชนกับ sales ต้อง rename ด้วย
- **★ UI หน้าเดียว (มิ.ย.69)**: `/track/` ([dashboard.html](templates/dashboard.html)) รวมทุกอย่างหน้าเดียว — ตัวเลขสรุปต่อสเตป + ตารางรถทั้งหมด (ตัวกรองสาขา/สเตป/เรียง) + ปุ่ม เพิ่มรถ(modal)/พิมพ์QR/ผู้ใช้ · กดแถวรถ → popup รายละเอียด (fetch `/track/cars/<code>/json` = `car_json`) + เปลี่ยนสเตป (ปุ่ม → POST `car_stage`) + ประวัติสแกน + QR. **ตัดเมนูย่อยเดิม (บอร์ด/รถทั้งหมดแยกหน้า) + header ซ้ำออก** ([base.html](templates/base.html) เหลือโลโก้กลับหน้าหลัก+ออก). car_create/car_edit/car_stage redirect → `track_dashboard` (อยู่หน้าเดียว). `car_list`/`kanban`/`car_detail` view ยังอยู่แต่ไม่ลิงก์จากเมนู (kanban/รายการ ถูกแทนด้วยตารางในหน้าเดียว)
- **★ เพิ่มรถ 2 ทาง (มิ.ย.69)**: (1) หน้า `/track/` ([dashboard.html](templates/dashboard.html)) modal ใช้ `CarForm` → POST `car_create` (ฟอร์ม Django ครบฟิลด์ + photo + doc_registration). (2) **แท็บ "สถานะรถ" ในแดชบอร์ด sales** ([index.html](dashboard/templates/dashboard/index.html) `openTrkAdd`/`addTrkCar`) → POST JSON `/track/api/add_car` (`api_add_car`). **`api_add_car` รับฟิลด์ครบตาม DB**: branch/stage(สเตปเริ่มต้น)/status/plate/brand/model/year/color/km/date_in(วันรับเข้า)/tax_due_date/book_status/note + **รูป 1 รูป** — POST ไฟล์เข้า `/track/api/upload` (Google Drive) แล้วส่ง `photo_id` (Drive id) มาเก็บที่ `car.photo.name` · `api_add_car` ย้ายรูปเข้าโฟลเดอร์รถหลัง gen code. choice fields validate กับ constants (ค่านอกลิสต์ = default) · `cars_api` ส่ง `statusChoices`/`bookChoices`/`stages` ให้ dropdown · ต้องตั้ง GDRIVE_* ไม่งั้นอัปรูปไม่ได้ (ฟอร์มยังบันทึกได้ รูปเป็น optional)
- **★ ดีไซน์ส่วนบนแท็บ "สถานะรถ" (ก.ค.69 · `renderTrk`/`buildTrkPies` ใน [index.html](dashboard/templates/dashboard/index.html))**: การ์ดใหญ่ gradient 3 ใบ (สาขา/รถทั้งหมด/ขายแล้ว · ไอคอน lucide ขาว) + แถบเตือนบางๆ (รถในระบบ/ค้างนาน/ใกล้ค้าง/T2L) + **2 โดนัท**: "ขั้นตอนงาน" (5 เฟส จาก `phaseRows`) · "แยกตามสาขา" (นับ `c.branch`). **แทนโดนัทเดิมตัวเดียว (`buildTrkPie`) + KPI cards กอง**. **⚠️ `c.status` มีแค่ `active`/`sold`** (ไม่ใช่ จอง/พร้อมขาย/ซ่อม แบบระบบ 255 คันเดิม) → ทำ pie สถานะขายไม่ได้ · อยากได้ต้องเพิ่ม field ประเภท/สถานะขายในข้อมูลรถก่อน
- **★ เซลล์เปลี่ยนสเตปรถในหน้าเซลล์ (มิ.ย.69)**: [seller.html](dashboard/templates/dashboard/seller.html) มีโหมด **"🚗 สถานะรถ"** (dropdown โหมด `pageMode='cars'` · `renderCarsMode`) → ดึงรถจาก `/track/api/cars` + กดเปลี่ยนสเตปที่ตัวเองมีสิทธิ์ (`myStages` = `allowed_stages(user)` ของ role Sales: qc/show/reserve/finance/closing/sold) → POST `/track/api/seller_set_stage` (`api_seller_set_stage`). **★ ผ่อนกฎ scan-only ให้เซลล์**: endpoint นี้ใช้ `can_set_stage` (ไม่ใช่ `can_set_stage_direct`) → Sales เปลี่ยนได้ตรงๆ ไม่ต้องสแกน QR (ต่างจาก `api_set_stage`) · `csrf_exempt`+`login_required` (seller.html ไม่มี CSRF token เหมือน endpoint ฝั่งเซลล์ตัวอื่น) · เซลล์ได้ role Sales อัตโนมัติตอน bridge · `cars_api` ส่ง `myStages`+`me` เพิ่ม. **ต้องต่อ DB tracking ก่อนถึงใช้จริงได้** (DB ล่ม → โหมดนี้โชว์ "ระบบยังไม่พร้อม")
  - **★ ดีไซน์มือถือ list→detail (มิ.ย.69)**: `renderCarsMode` แตกเป็น 2 view (`_scView` = `'list'`|`'detail'`). **list** (`renderCarsList`/`renderSellerCars`) = ค้นหา/กรองสเตป + การ์ดรถ → **แตะการ์ด** → `openSellerCar(code)` (fetch `/track/cars/<code>/json`). **detail** (`renderCarDetail`) = หน้าจอเปลี่ยนสเตปเต็ม: การ์ดรถ (hero) + **step changer** (chips สเตปที่เปลี่ยนได้ · `renderScChanger`/`scPickStage` · current→selected) + โน้ต + **อัปรูป/วิดีโอ ก่อน/หลัง** + ปุ่มยืนยัน (`scConfirmStage`) + **ไทม์ไลน์ประวัติ** (`scHistoryHtml` จาก `car_json` logs)
  - **อัปรูป**: `scAddPhotos` → POST ไฟล์ (multipart) เข้า `/track/api/upload` (ส่ง `code`) → Google Drive (โฟลเดอร์รถคันนั้น) → ส่ง `media`=`[{id,video}]` ใน `seller_set_stage` → แนบเข้า `ScanLog.media` (เหมือน `scan_submit`) · `car_json` คืน `logs[].media` เป็น `{url,video}` (จาก `_media_urls`) + `logs[].stageKey` (แปลชื่อสเตปข้ามภาษา) + `lastWorker`. _(ดูหัวข้อ "รูป/วิดีโอ → Google Drive" ท้ายไฟล์ · เลิกใช้ `sign_upload`+Supabase)_
  - **★ i18n 4 ภาษา (TH/EN/MM/KH)** สำหรับคนงานหลายสัญชาติ: `SC_T` (label) + `SC_STAGE_I18N` (ชื่อสเตป EN/MM/KH · TH ใช้ค่าจากเซิร์ฟเวอร์) + `scT()`/`scStageName()` · สลับด้วย `setScLang` (เก็บ localStorage `scLang`) · **พม่า/เขมรเป็นฉบับร่าง — ควรให้เจ้าของภาษาตรวจ** · accent ใช้ `--blue` ของหน้าเซลล์ (ไม่ฮาร์ดโค้ดม่วงตามม็อก เพื่อรองรับ light/dark เดิม)
- **auth = Django auth + Group** (**10 บทบาท** · [cars/roles.py](cars/roles.py)): **สิทธิ์เต็ม (เพิ่ม/แก้/ลบรถ + จัดการผู้ใช้)** = Executive/Registration/QC/PaintIn (**QC มีสเตปแค่ 4 ปุ่ม** ตั้งแต่ ส.ค.69) · **เฉพาะสเตปตัวเอง** = Purchasing/Production/Technician/CarWash/Sales · **Admin** = แก้ข้อมูลรถ + จัดการผู้ใช้ (ไม่เปลี่ยนสเตป). **(ก.ค.69: +Production/QC/PaintIn · ยุบ Vendor เข้า Registration)** — ตารางสิทธิ์เต็มดูหัวข้อ "รื้อสเตป+บทบาท" ด้านล่าง
- **★ รื้อสเตป + บทบาท (ก.ค.69) — 16 สเตป/4 เฟส + ความด่วน + บังคับรูป + ถ่ายคอนเทนต์** ([constants.py](cars/constants.py)/[roles.py](cars/roles.py)/[models.py](cars/models.py) · migration **0010_restage_v2_priority** — ต้อง `migrate` ตอน deploy · remap สเตปเก่า→ใหม่ให้อัตโนมัติ):
  - **22 สเตป (4 เฟส · `STAGES`/`PHASES` · ส.ค.69 รอบ 4)**: รับเข้า·รถรอถ่ายรูป | เช็คซ่อม·**ซ่อมเสร็จรอตรวจ**·สั่งของ/รออะไหล่·งานเบาะ·อู่สีใน·อู่สีนอก·**รอตรวจสี**·ติดฟิล์ม·ชงล้าง·**ชงล้างรอปล่อย**·**รอ QC ตรวจ** | **รอเซลล์ตรวจรถขึ้นโชว์**·รถพร้อมขาย·จอง·จัดไฟแนนซ์·**ตรวจขนส่ง**·รอปิดการขาย | ตรวจรถรอปล่อย·ปล่อยรถ·**ขายแล้ว**. **ขายแล้ว (`sold`) = จบจริง (status=sold หลุดบอร์ด) · ปล่อยรถไม่จบแล้ว (เซลล์เก็บรูปต่อ)** · แยกอู่สีเป็น ใน(`paint_in`)/นอก(`paint_out`) · เลิกจุด QC กลาง 3 จุดเดิม → รวมเป็น `qc_show`/`qc_release`
    - **★ `repair_done` "ซ่อมเสร็จรอตรวจ" (ส.ค.69 · migration 0011)** — วางต่อจาก `repair` ทันที (ช่างตรวจเสร็จ กดบอกว่าจะทำงานไหนต่อ) · **ช่างเป็นคนกด** · เพิ่มชื่อใน i18n 2 ที่: `STG` ([dashboard.html](templates/dashboard.html)) + `STAGE_NAMES` ([scan.html](templates/scan.html)) — **ลืมเพิ่ม = คอลัมน์โชว์คีย์ดิบ `repair_done`**
    - **★ ด่านตรวจ 2 ชั้นก่อนขึ้นหน้าร้าน (ส.ค.69 · migration 0012)**: `wash` → **`qc_show` "รอ QC ตรวจ"** (ล้างเสร็จส่งตรวจ) → **`sales_check` "รอเซลล์ตรวจรถขึ้นโชว์"** (QC ตรวจผ่านแล้วติ๊กส่งต่อ) → `show`. **เปลี่ยนชื่อ `qc_show` จาก "รอตรวจรถขึ้นโชว์" → "รอ QC ตรวจ"** เพราะชื่อเดิมไม่บอกว่าใครตรวจ → สับสนกับด่านเซลล์
      - **⚠️ ชั่วคราว: ยังไม่มีคน QC จริง → `sales_check` เปิดให้ `CARWASH` ติ๊กแทนไปก่อน** (ฝ่ายล้างรถจึงมี **2 ปุ่ม**) · **มีคน QC เมื่อไหร่ให้เอา `CARWASH` ออกจาก `sales_check` ใน [roles.py](cars/roles.py)** เหลือสิทธิ์เต็มอย่างเดียว
    - **★ เปลี่ยนชื่อโชว์ 2 สเตป (ส.ค.69 · migration 0014 alter choices)**: `show` "รถพร้อมขาย/หน้าร้าน" → **"รถพร้อมขาย (ตรวจรถขึ้นโชว์)"** · `release` "ปล่อยรถ" → **"ปล่อยรถ (ส่งรูปปล่อยรถ)"** (บอกในชื่อเลยว่าปุ่มนี้ = ผ่านการตรวจ/ต้องส่งรูป — release อยู่ใน `STAGE_FORCE_MEDIA` อยู่แล้ว) — key ไม่เปลี่ยน · sync i18n แล้วใน `STG` ([dashboard.html](templates/dashboard.html)) + `STAGE_I18N` ([scan.html](templates/scan.html)) + `SC_STAGE_I18N` ([seller.html](dashboard/templates/dashboard/seller.html) — ตารางนี้เป็นคีย์สเตปชุดเก่า คีย์ที่หายตกไปใช้ชื่อไทยจากเซิร์ฟเวอร์)
  - **ความด่วน (`Car.priority`)** = สีการ์ด เลือกมือ (แทนสีตามวันค้าง): **ด่วนมาก/ด่วน/ปกติ/ไม่เร่ง — 4 ตัวล้วน** (`PRIORITY_COLOR`/`PRIORITY_NAME`) → `POST /track/api/set_priority` (**`csrf_exempt`** — บอร์ดถูกฝัง iframe ในหน้าเซลล์ที่ไม่มี CSRF token · ไม่ใส่ = ฝ่ายทะเบียน/คนอื่นกดความด่วนไม่ได้ 403)
  - **★ ธงงานค้าง (`CAR_FLAGS` · `Car.need_photo`/`need_content` · ส.ค.69 · migration 0013)** — **แยกจากความด่วน · ติ๊กได้หลายอันพร้อมกัน · ใช้ร่วมกับความด่วนได้**:
    - **"ยังไม่ได้ถ่ายรูป"** (น้ำเงิน · camera) = รับเข้าแล้วแต่ยังถ่ายไม่ได้ → **ติดธงแล้วย้ายไปสเตปอื่นได้เลย** (ซ่อม/สี/ล้าง) ไม่ต้องค้างในคิวถ่ายรูป · **"ยังไม่ได้ถ่ายคอนเทนต์"** (ม่วง · video) — ธงติดตามรถไปทุกสเตป
    - **~~ปุ่ม "ถ่ายคอนเทนต์"~~ ถอดออกแล้ว (ส.ค.69 — เจ้าของบอกซับซ้อนเกิน)**: ปุ่ม+โมดัลใน dashboard.html ลบทิ้ง (ดู git history) · ธง `need_content` ปลดด้วยการติ๊ก checkbox เองเท่านั้น · endpoint `/track/api/content_shoot` (`api_content_shoot`) **ยังอยู่แต่ไม่มี UI เรียก** (legacy เผื่อเอาปุ่มกลับ — ยังปลดธงอัตโนมัติถ้าถูกเรียก)
    - ตั้งค่าผ่าน `POST /track/api/set_flags` (`csrf_exempt` · ส่งเฉพาะคีย์ที่จะเปลี่ยน) · โชว์เป็น **ไอคอนบนการ์ด** + **checkbox ในป๊อปอัปรถ** + **checkbox ในหน้าสแกน** ([scan.html](templates/scan.html) การ์ดรถ hero · `scSetFlag()` · i18n 4 ภาษาใน `SCAN_I18N` คีย์ flags/flagPhoto/flagContent) — checkbox ทุกจุดขนาด 22px (`accent-color` ตามสีธง) ให้กดง่ายบนมือถือหน้างาน (ส.ค.69)
    - **⚠️ บทเรียน (ทำไมต้องแยก)**: เดิม "ยังไม่ได้ถ่ายรูป" เป็นตัวเลือกหนึ่งใน `priority` ซึ่งเป็นช่องเดียวเลือกได้ค่าเดียว → **ติดธงแล้วบอกด่วน/ไม่ด่วนไม่ได้** · migration 0013 ย้ายข้อมูลเก่าให้ (`priority="photo_wait"` → `need_photo=True` + `priority="normal"`)
    - **★ ติ๊ก "ยังไม่ได้ถ่ายรูป" = ไม่นับค้าง (ส.ค.69)**: `Car.flag` คืนค่าใหม่ **"wait"** เมื่อ `need_photo=True` (รถรอทุกอย่างเสร็จก่อน ไม่ใช่งานดอง) → ไม่ขึ้นแดง/เหลือง ไม่เข้าตัวนับ "ค้างนาน/ใกล้ค้าง" · **วันยังเดินตามจริง** (การ์ดโชว์ "รอถ่ายรูป X วัน" สีน้ำเงิน · ป๊อปอัปโชว์ "รอถ่ายรูป — รอทุกอย่างเสร็จก่อน") · ปลดธงเมื่อไหร่กลับมานับตามวันจริงทันที · จุดที่รองรับ "wait": `flags` dict ใน `dashboard`/`cars_api` ([views.py](cars/views.py)) + CSS `.wait` ([base.html](templates/base.html)) + `flagTxt`/i18n `fWait`/`fWaitNote` ([dashboard.html](templates/dashboard.html))
    - **★ ช่องความด่วนโชว์เฉพาะบางสเตป (`PRIORITY_STAGES` · ส.ค.69 รอบ 6)**: **เฟส "รับเข้า" + "ทำสภาพ" เท่านั้น** (13 สเตป — รวม ชงล้าง/ชงล้างรอปล่อย/รอ QC ตรวจ) · **ช่วงขาย + ปล่อยรถ ซ่อนทั้งช่อง** (เจ้าของเคาะสุดท้าย: "ทั้งสายงาน ยกเว้นช่วงขาย-ปล่อย" — เพิ่มสเตปใหม่ใน 2 เฟสแรกได้ช่องนี้อัตโนมัติ ไม่ต้องมาแก้ลิสต์)
      - หลักคิด: ความด่วนคือ "สัญญาณจัดคิว" มีประโยชน์เฉพาะตอนรถหลายคันรอทีมเดียวกันทำ (ถ่ายรูป/ช่าง/สี/ล้าง/QC) · พอเข้าช่วงขาย-ปล่อย รถผูกกับลูกค้าเฉพาะรายแล้ว ไม่มีคิวให้แซง มาร์คด่วนก็ไม่ได้เร็วขึ้น → ซ่อนลดปุ่มรก (เจ้าของสั่ง: "ชงล้างต้องมี · ปล่อยไม่ต้องมี")
      - บล็อก 2 ชั้น: UI ซ่อนทั้งบล็อก (`show_priority` scan · `showPriority` ป๊อปอัปบอร์ด · `priorityStages` หน้าเซลล์) + เซิร์ฟเวอร์ `can_set_priority(user, stage)` → 403
      - **`change_stage` รีเซ็ตความด่วนเป็น "ปกติ" ทุกครั้งที่เปลี่ยนสเตปอยู่แล้ว** → ไม่มีค่าด่วนค้างมาจากช่วงทำสภาพ
    - **★ ความด่วนเลือกได้จากหน้าสแกนแล้ว (ส.ค.69)**: [scan.html](templates/scan.html) การ์ดรถ hero มี dropdown ความด่วน (`scSetPriority()` → `POST /track/api/set_priority` เดิม) — `scan_page` ส่ง `priorities` (key/name/color) เข้า template · เดิมความด่วนตั้งได้แค่ในป๊อปอัปบอร์ด คนงานมือถือไม่เห็น
    - **★ การ์ดบนบอร์ดเรียงตามความด่วนก่อน (ส.ค.69)**: `dashboard` view ([views.py](cars/views.py) `board_cols`) เรียง `(ติดธงไหม, ลำดับความด่วน, stage_since)` — **รถติดธงงานค้างขึ้นบนสุดก่อนเสมอ แม้ความด่วนต่ำกว่า** (ส.ค.69 เจ้าของสั่ง ให้หางานถ่ายคอนเทนต์เจอง่าย) → แล้วค่อยด่วนมาก (แดง) → ค้างนานสุดขึ้นก่อนในระดับเดียวกัน
    - **★ ธง "รอเปลี่ยนยาง" (`need_tire` · slate · disc · ส.ค.69 · migration 0016)** — ธงที่ 3 · ฝ่ายทะเบียน/QC ใช้บอกว่ารถรอยาง (ติ๊กได้ทุกบทบาทเหมือนธงอื่น)
    - **★ รถรับเข้าใหม่ติดธงรูป+คอนเทนต์อัตโนมัติ (ส.ค.69 · migration 0016)**: `need_photo`/`need_content` เปลี่ยน **default = True** ในโมเดล → ครอบทุกทางที่สร้างรถ (ฟอร์ม `car_create` / `api_add_car` / สคริปต์) ไม่ต้องไปติ๊กเอง · แถวเก่าไม่กระทบ · ผลพลอยได้: รถใหม่ `Car.flag`= "wait" (ไม่นับค้าง) จนกว่าจะปลดธงรูป
    - **★ หน้าเซลล์ตั้งความด่วน/ติ๊กธงได้แล้ว (ส.ค.69)**: [seller.html](dashboard/templates/dashboard/seller.html) `renderCarDetail` เพิ่มการ์ด **ความด่วน (dropdown) + ธงงานค้าง (checkbox)** เหนือกล่องเปลี่ยนสเตป (`scSetPriority()`/`scSetFlag()` · โชว์เสมอแม้บทบาทไม่มีสเตปให้กด) — เดิมหน้าเซลล์ **ไม่มี UI ตั้งความด่วนเลย** ต้องไปหน้าสแกน/บอร์ด · `cars_api` ส่ง `priorities` + `flagDefs` เพิ่ม
    - **เพิ่มธงใหม่**: แก้ `CAR_FLAGS` ([constants.py](cars/constants.py)) + เพิ่มฟิลด์ใน [models.py](cars/models.py) + migration + `FLAG_DEFS` ใน [dashboard.html](templates/dashboard.html) + checkbox&i18n ใน [scan.html](templates/scan.html) + `needTire`-style key ใน `car_json`/`cars_api`/`api_set_flags` ให้ตรงกัน (`api_set_flags` วนตาม `FLAG_KEYS` อยู่แล้ว ไม่ต้องแก้)
  - **★ สีการ์ด = `Car.card_color`** ([models.py](cars/models.py)) — ปกติใช้สีความด่วน แต่ **ถึง `show` (รถพร้อมขาย) = เขียว `FRONTLINE_COLOR` ทับ** (จบสายทำสภาพแล้ว) · **หัวการ์ด = `Car.card_label`** = ป้ายทะเบียน (คนหน้างานจำทะเบียนไม่ใช่รหัส) · ไม่มีทะเบียน → fallback รหัสรถ · รหัสยังอยู่ใน `title` ตอน hover
  - **บังคับแนบรูป/วิดีโอ** (`STAGE_FORCE_MEDIA`={`qc_release`,`release`}) ก่อนกดยืนยัน · **ถ่ายคอนเทนต์** = action แทรกได้ทุกสเตป (ไม่เปลี่ยนสเตป · เก็บ ScanLog ที่สเตปเดิม) → `POST /track/api/content_shoot` · **ทั้ง 2 อย่าง + ความด่วน = ใครล็อกอินก็ทำได้ ไม่ผูกบทบาท**
  - **★ รื้อรอบ 2 (ส.ค.69 · migration 0015 · "แก้บัค salefos" ตามเจ้าของสั่ง)**:
    - **สเตปใหม่ 3 ตัว (รวม 21)**: **`paint_check` "รอตรวจสี"** (หลังอู่สีนอก · ฝ่ายทะเบียน+สิทธิ์เต็มเท่านั้น) · **`transport_check` "ตรวจขนส่ง"** (หลังจัดไฟแนนซ์ · เซลล์) · **`sold` "ขายแล้ว"** (ท้ายสุด)
    - **★ ปล่อยรถไม่จบแล้ว**: `release` ไม่ set sold — รถอยู่บนบอร์ด (คอลัมน์ปล่อยรถโผล่แล้ว) ให้เซลล์เก็บรูปส่งมอบต่อ · กด **"ขายแล้ว" (`sold`) ถึงจบจริง** → status=sold หลุดบอร์ดไปหน้า "ขายแล้ว" (toggle ในตาราง `view=sold`) · `_is_sold` = status sold หรือ stage sold (เลิกดู release)
    - **★ เปลี่ยนสเตปแล้วความด่วนรีเซ็ตเป็น "ปกติ" เสมอ** (เว้นแต่ตั้งด่วนใหม่เอง · `change_stage` ใน [models.py](cars/models.py) — `api_set_stage` ที่รับ priority พร้อมกันต้อง apply "หลัง" change_stage)
    - **★ ธงงานค้างค้างจริง**: `change_stage` ใช้ `save(update_fields=...)` — ธง need_photo/need_content โดนการเปลี่ยนสเตปเขียนทับไม่ได้เด็ดขาด · จุดปลดธงเหลือ 2 ที่: ติ๊กออกเอง (`api_set_flags`) + ปุ่มถ่ายคอนเทนต์ปลด need_content (ทีมคอนเทนต์ — เจ้าของอนุญาต)
    - **★ ตัวกรองธงงานค้าง** ในตารางรถหน้า `/track/` (`?flag=need_photo|need_content` · select ข้างตัวกรองสเตป)
    - **★ เซลล์แก้ข้อมูลรถรายคัน**: `can_edit_this_car(user, car)` ([roles.py](cars/roles.py)) — เซลล์แก้ได้เฉพาะ stage ใน `SALES_EDIT_STAGES={show, release, sold}` (car_edit + canEdit ใน car_json ใช้ตัวนี้)
  - **★ /track/ ไม่เป็นหน้าแยกสำหรับแอดมินแล้ว (ส.ค.69)**: แอดมินฝั่งขาย (session position=admin) เปิด `/track/` ตรงแบบหน้าเต็ม → **redirect `/dashboard/?tab=t`** (แท็บสถานะรถ · index.html อ่าน `?tab=` อยู่แล้ว) — เช็คด้วย header `Sec-Fetch-Dest=='document'` (โหลดใน **iframe** ส่ง 'iframe' = ผ่าน ไม่งั้นแท็บสถานะรถ/หน้าเซลล์พังวนลูป · เบราว์เซอร์เก่าไม่ส่ง header = ไม่เด้ง) · **คนงาน (worker) ใช้ /track/ ตรงเหมือนเดิม** · แก้หน้า error ของ index.html ที่โชว์ `${ic(...)}` ดิบ (Django template ใช้ JS template literal ไม่ได้ → ใช้อิโมจิ)
  - **★ 🌐 แปลหมายเหตุพม่า/เขมร → ไทยอัตโนมัติ (ส.ค.69)**: [cars/translate.py](cars/translate.py) — `change_stage` สร้าง ScanLog แล้วยิง `translate_log_async()` (daemon thread · best-effort) → Gemini (คีย์เดิม `GEMINI_API_KEY` · โมเดล flash) แปลเฉพาะ**บรรทัดที่มีอักษรพม่า/เขมร** เติม `(แปล: ...)` ใต้บรรทัดนั้น (ไทย/อังกฤษ/เช็คลิสต์ไม่แตะ · มีคำแปลแล้วไม่แปลซ้ำ) · ไม่มีคีย์/ล่ม = เงียบ ข้อความเดิมอยู่ครบ · ครอบทุกทาง (สแกน/บอร์ด/หน้าเซลล์) เพราะ hook ที่ `change_stage`
  - **★ ☰ แถบแท็บ → เมนูสามขีด (hamburger drawer · ส.ค.69)**: ซ่อนแท็บไว้ กดปุ่ม ☰ ในหัวเว็บ → แผงเลื่อนออกจากซ้าย + ฉากหลังมืด · **ใช้ทุกขนาดจอเหมือนกัน** (drawer ลอยทับ ไม่กินพื้นที่ → เนื้อหาได้ความกว้างเต็มตลอด) · _(เดิม ส.ค.69 ต้นเดือนเป็น sidebar ติดซ้ายถาวรบนจอ ≥1100px — เปลี่ยนตามที่ผู้ใช้ขอ)_
    - **ชิ้นส่วน**: [globals.css](dashboard/static/dashboard/css/globals.css) `.nav-burger` (ปุ่ม ☰) · `.nav-backdrop` (ฉากหลัง กดปิด) · `#nav-slide` = drawer (`position:fixed` + `transform:translateX(-104%)` → `body.nav-open` เลื่อนเข้า) · `.nav-head` (หัว "เมนู" + ปุ่มปิด ✕) · `.nav-sec` (หัวข้อหมวด) · `.nav-act` (รายการเมนูจัดการ) · [index.html](dashboard/templates/dashboard/index.html) `openNav()`/`closeNav()`/`toggleNav()` + ปิดด้วย **Esc** + `switchTab()` เรียก `closeNav()` เอง
    - **★ เมนูจัดการย้ายเข้า drawer + แบ่ง 4 หมวด (ส.ค.69)**: เดิมเป็น dropdown **"เมนูจัดการ ▾"** ในหัวเว็บ 12 รายการเรียงรวดไม่มีหัวข้อ → ย้ายมาต่อท้ายแท็บใน drawer เดียวกัน แบ่งเป็น **หน้าหลัก** (8 แท็บ) · **ทีม & สิทธิ์** (ตั้งเป้า/ทีม · แอดมิน · เทเลเซลล์ · บทบาทติดตามรถ) · **ตั้งค่าระบบ** (Sheets · หมวดวิธีได้รถ · แจ้งเตือนตามด่วน · รายงานเข้าไลน์) · **ตรวจสอบ & Log** (สถานะระบบ · Log ข้อมูล · Log เข้าระบบ · LINE ID · ส่งคะแนนเข้าชีต)
      - รายการทั้งหมดนิยามที่ **`const ADMIN_MENU`** ([index.html](dashboard/templates/dashboard/index.html)) — **เพิ่ม/แก้เมนูจัดการ = แก้ที่นี่ที่เดียว** (render วนลูปเอง) · ทุกปุ่มเรียก **`closeNav()` ก่อนเปิด modal** เพราะ drawer (z-index 1260) บังตัว modal (1000–1200)
      - **หัวเว็บเหลือแค่ "ตัวบอกสถานะสด"**: ชิปออนไลน์ + กระดิ่งแจ้งเตือน (มี badge ต้องเห็นตลอด ไม่ควรซ่อนใน drawer) · ลบ CSS `.admin-nav-menu` + handler click-outside ที่ตายแล้วออก
      - **แก้บั๊ก**: **"รายงานเข้าไลน์" (`openReportLine`) เดิมไม่มีปุ่มเรียกเลยสักที่** (ฟังก์ชันมีอยู่แต่เข้าไม่ถึงจาก UI ทั้งที่เอกสารบอกว่าอยู่ในเมนูจัดการ) — ใส่กลับในหมวด "ตั้งค่าระบบ" แล้ว
      - drawer **เปิด scrollbar แนวตั้ง** (`#nav-slide::-webkit-scrollbar`) ทับค่าฐาน `.nav-slide` ที่ซ่อนไว้ตอนยังเป็นแถบนอน — 21 รายการยาวเกินจอ ถ้าซ่อน scrollbar ผู้ใช้จะไม่รู้ว่ามีเมนูข้างล่างอีก
    - **สถานะเปิด/ปิด = class `nav-open` บน `<body>`** (ห้ามเก็บใน `#dashboard-root`) — เพราะ `render()` ล้าง `innerHTML` ทุกครั้ง ถ้าเก็บข้างในจะเด้งปิดเองทุกรอบ render
    - ไอคอน `menu`/`x` เพิ่มใน dict **`LUCIDE`** (index.html) แล้ว — dict นี้เป็น hardcode ไม่ได้โหลดจาก CDN **ใช้ไอคอนใหม่ต้องเพิ่ม path เข้า dict ก่อน** ไม่งั้น `ic()` คืน svg เปล่า
    - **แก้ CSS ต้อง bump `?v=` ที่ link globals.css** — มี 2 ที่ (index.html + seller.html) ต้องตรงกัน
    - **⚠️ 3 บั๊กที่เคยทำให้แถบนี้ไม่ขึ้นเลย/หน้าตาเพี้ยน (แก้แล้ว ส.ค.69 · อย่าให้กลับมา)**: (1) selector เขียน **`#root`** แต่ id จริงของ container ใน index.html คือ **`#dashboard-root`** (`#root` เป็นของ seller.html ซึ่ง**ไม่มี** `#nav-slide` เลย → กฎตายสนิททั้งคู่) (2) ตอน init JS สั่ง **`root.style.display='block'`** ซึ่งเป็น **inline style ชนะ CSS เสมอ** → ต้องใช้ **`root.style.display=''`** (ล้าง inline `display:none` แล้วปล่อยให้ CSS คุม) (3) สไตล์ฐานของ `#nav-slide` เขียน inline บน element ใน `render()` → CSS override ไม่ได้
    - **กฎ**: สไตล์ของ `#nav-slide` อยู่ใน **คลาส `.nav-slide` ใน globals.css เท่านั้น** — **ห้ามเขียน inline style บน element ใน `render()`**
  - **★ ประวัติในป๊อปอัปบอร์ดโชว์รูปแล้ว (ส.ค.69 · แก้บั๊ก "มือถือเห็นรูป คอมไม่เห็น")**: `car_json` ส่ง `logs[].media` มาให้ตลอด แต่ [dashboard.html](templates/dashboard.html) `openCar()` **ไม่เคย render `l.media`** (หน้าสแกน/หน้าเซลล์ render อยู่แล้ว) → คนดูจากคอมไม่เห็นรูปที่หน้างานถ่ายส่งมา · เพิ่ม `_thumbs(l)` (รูป 56px กดเปิดเต็ม · วิดีโอเป็นปุ่ม ▶) + ขยายกล่องประวัติ 160→300px
    - **⚠️ ตอนทดสอบ template ของ /track/ ต้องรีสตาร์ท dev server** (โปรเจกต์ cache template แม้ DEBUG) · เคยเสียเวลาไล่บั๊กเพราะมี `runserver` ค้างอยู่ 2 ตัวบนพอร์ตเดียวกัน **ตัวเก่าเป็นคนตอบ** → แก้โค้ดแล้วหน้าเว็บไม่เปลี่ยน (เช็คด้วย `netstat -ano | findstr :<port>` ว่าเหลือ process เดียว)
  - **★ ⏱ ระยะเวลาช่วงต่อช่วงใน timeline (ส.ค.69)**: ทุก log โชว์เวลาที่รถ "อยู่ในช่วงนั้น" (จาก log นี้ → log ถัดไป · อันล่าสุด = "อยู่มาแล้ว X" ถึงตอนนี้) — `_fmt_dur()`+`_logs_with_dur()` ([views.py](cars/views.py)) แนบ `dur`/`cur` เข้า logs ของ `car_json`+`scan_page` → โชว์ 3 จุด: ป๊อปอัปบอร์ด · หน้าสแกน · ไทม์ไลน์หน้าเซลล์ · โน้ตใน timeline เปลี่ยนเป็น `white-space:pre-line` (เช็คลิสต์หลายบรรทัดไม่ติดกัน)
  - **★ ☰ เมนูสามขีดของหน้า `/track/` (ส.ค.69)**: หัวบอร์ดเดิมมีปุ่มเรียง 6 ตัว → ยุบเข้าเมนู ☰ (`.trk-drawer`/`.trk-bd`/`toggleTrkNav()` ใน [dashboard.html](templates/dashboard.html) · สถานะ = class `trknav-open` บน `<body>` · ปิดด้วยฉากหลัง/✕/Esc) — แบ่งหมวด **ผู้ใช้ & Log** (ผู้ใช้/บทบาท · Log เข้าระบบ) · **ดาวน์โหลด** (Export ทุกคัน) · **ภาษา** (4 ปุ่ม) · **"เพิ่มรถ" ยังอยู่นอกเมนู** (ปุ่มหลักที่ใช้บ่อยสุด) · ฝังใน iframe = ซ่อนทั้งชุด (`html.embedded`) เพราะแดชบอร์ดขายมีเมนู ☰ ของตัวเอง
  - **★ ⬇ Export ไทม์ไลน์ทุกคัน (ส.ค.69)**: `export_timeline_all()` → **`/track/export`** (`?scope=active` = ตัดรถที่ขายแล้ว) · **CSV ล้วน ไม่แนบรูป** — zip รูปรถทุกคันอาจใหญ่หลาย GB และสร้างในแรม เสี่ยงเซิร์ฟเวอร์ล้ม (อยากได้รูป → Export ทีละคันจากป๊อปอัป) · คอลัมน์ชุดเดียวกับรายคัน (มีรหัสรถ/ทะเบียนทุกแถว → กรองใน Excel ได้) · **แชร์ `_timeline_rows()`/`_csv_row()` กับ export รายคัน** เพื่อไม่ให้คอลัมน์ 2 ที่หลุดจากกัน · เข้าถึงได้ 2 ทาง: เมนู ☰ ของ `/track/` และ **เมนู ☰ แดชบอร์ดขาย → "ตรวจสอบ & Log" → "Export ไทม์ไลน์รถ (beta)"**
  - **★ ⬇ Export ไทม์ไลน์รถ เป็น CSV (+รูปแบบเลือกได้) (ส.ค.69)** — `export_timeline()` ([views.py](cars/views.py)) · route **`/track/cars/<code>/export`** (`export_timeline`) · ปุ่มอยู่ใน **ป๊อปอัปรถ** ([dashboard.html](templates/dashboard.html)) มี **checkbox "เอารูป/วิดีโอมาด้วย"** + ปุ่ม Export (`exportTimeline()` · i18n 4 ภาษา `expBtn`/`expPhotos`/`expWait`/`expGo`)
    - **ไม่ติ๊ก → `.csv` ล้วน** (เร็ว ไฟล์เล็ก) · **ติ๊ก → `.zip`** = CSV + โฟลเดอร์ `photos/`
    - **จับคู่แถว↔รูปได้**: ไฟล์รูปตั้งชื่อ `<ลำดับแถว>_<สเตป>_<n>.<ext>` (เช่น `03_รอเซลล์ตรวจรถขึ้นโชว์_1.jpg`) และคอลัมน์ "ไฟล์แนบ" ใน CSV ระบุชื่อไฟล์เดียวกัน · รูปหน้าปกรถ = `00_ปกรถ.*`
    - คอลัมน์: รหัสรถ · ทะเบียน · ลำดับ · วันที่-เวลา · สเตป · ผู้เปลี่ยน · ระยะเวลาช่วงนี้ · หมายเหตุ · จำนวนไฟล์ · ไฟล์แนบ — **เรียงเก่า→ใหม่** (ต่างจาก timeline บนจอที่ใหม่→เก่า) · BOM ให้ Excel ไทยไม่เพี้ยน
    - **`_media_bytes()` อ่านไฟล์ดิสก์จาก `MEDIA_ROOT` ตรง ไม่ผ่าน `default_storage`** — เพราะถ้าตั้ง `GDRIVE_*` ไว้ `default_storage` จะเป็น `GoogleDriveStorage` แล้วเอา path ดิสก์ไปหาใน Drive → ไม่เจอ (+ กัน path traversal `../`) · Drive ใช้ **`gdrive.download()`** (เพิ่มใหม่ · สตรีมทีละ chunk ตัดที่ 60MB กันวิดีโอใหญ่กินแรม)
    - **`_attachment()` ตั้งชื่อไฟล์ด้วย RFC 5987 (`filename*=UTF-8''…`)** — ถ้าใส่ชื่อไทยดิบ Django จะเข้ารหัสเป็น `=?utf-8?b?…?=` ที่เบราว์เซอร์ไม่แปลงกลับ → ผู้ใช้ได้ไฟล์ชื่อขยะ
    - โหลดไฟล์ไม่ได้ (Drive ล่ม/ไฟล์หาย) = **ข้ามไฟล์นั้น ไม่ล้มทั้ง export** · ติ๊กแล้วไม่มีรูปเลย = ใส่ `photos/อ่านก่อน.txt` อธิบาย (กันผู้ใช้นึกว่าระบบพัง)
  - **★ ⬇ Export CSV แดชบอร์ดหลัก (ส.ค.69)**: ปุ่ม "CSV" เขียวคู่ปุ่ม "ส่งไลน์ ▾" ทุกการ์ดตาราง ([index.html](dashboard/templates/dashboard/index.html) `_cardLineBtn` → `exportCardCSV()`/`dlCSV()`) — ดึงจาก DOM table ตรงๆ (ตรงกับที่ตาเห็น · ตามตัวกรองวันที่) · BOM `﻿` เปิด Excel ไทยไม่เพี้ยน · ชื่อไฟล์ `<ชื่อการ์ด>_<from>_ถึง_<to>.csv` · การ์ดไม่มีตาราง = alert
  - **★ ป๊อปอัปบอร์ดแนบรูปได้ทุกสเตปแล้ว (ส.ค.69 · แก้บั๊ก)**: เดิม `stageMediaWrap` ตั้ง `display:none` แล้วโชว์เฉพาะสเตปใน `FORCE_MEDIA` → **สเตปอื่นแนบรูปไม่ได้เลยจากหน้าเว็บ** ทั้งที่หน้าสแกน/หน้าเซลล์แนบได้ทุกสเตป (คอมเมนต์เดิมเขียนว่า "แนบเพิ่มได้ทุกสเตป" แต่โค้ดไม่ตรง = บั๊ก ไม่ใช่ดีไซน์) · แก้เป็นโชว์เสมอ + สลับหัวข้อ `mediaReq`(บังคับ)/`mediaOpt`(ถ้ามี) · การบังคับแนบใน `qc_release`/`release` ยังอยู่เหมือนเดิม
    - หน้าตาปุ่มแนบรูปทำให้ตรงกันทั้ง 3 จุดแล้ว (กล่องเส้นประ + ไอคอนกล้อง · CSS `.stage-drop` = `.sc-drop` ของหน้าสแกน)
  - **★ เช็คลิสต์ตรวจรถ (ส.ค.69)**: เปลี่ยนเข้าสเตปกลุ่มตรวจ (`CHECKLIST_STAGES` = **show/qc_release/release** · ส.ค.69 เอา qc_show/sales_check ออก — 2 ด่านนั้นเป็นการ "ส่งต่อคิว" ไม่ใช่ตรวจรถเต็มรูปแบบ · รายการ `CHECKLIST_ITEMS` **15 ข้อ** (เพิ่ม "ตรวจศูนย์ล้อแล้ว") ใน [constants.py](cars/constants.py)) → โชว์เช็คลิสต์ (สตาร์ท/ขับขี่/ไฟ/เบรค/แอร์/ยาง/ภาษี ฯลฯ · **default ติ๊กหมด เอาออกเฉพาะข้อมีปัญหา**) → ผลถูกต่อท้ายหมายเหตุอัตโนมัติ marker `[ตรวจรถ]` (**❌ ไม่ผ่านขึ้นก่อน** · ✅ ผ่านตามหลัง) → เห็นใน timeline ตอน "ตีกลับ QC" คนถัดไปรู้ปัญหาทันที · มี 3 จุด: หน้าสแกน (`#chkWrap`+`chkSummary()`) · ป๊อปอัปบอร์ด (`#stageChkWrap` ใน stageModal) · หน้าเซลล์ (`#scChkWrap` · รายการมากับ `cars_api .checklist`) · ปี ยาง/ภาษี พิมพ์ในช่องโน้ต
  - **★ ปุ่มเปลี่ยนสเตป "แต้มสีตามเฟส + บอกว่างานไปอยู่ฝ่ายไหนต่อ" (ส.ค.69)**: แถบสีซ้ายปุ่ม + ไอคอนสีตาม **`PHASE_COLOR`** (รับเข้า=ฟ้า · ทำสภาพ=ส้ม · ขาย=ม่วง · ปล่อยรถ=เขียว) · ต่อท้ายชื่อปุ่มด้วย **"→ ฝ่ายที่รับช่วงต่อ"** จาก **`STAGE_OWNER`** ([constants.py](cars/constants.py)) + `title` tooltip ตอนเอาเมาส์ทาบ (จอแคบซ่อนข้อความ เหลือ tooltip)
    - **`STAGE_OWNER` เป็นตารางแยก ไม่ได้ derive จาก `STAGE_ROLES`** — เพราะ `STAGE_ROLES` คือ "ใครกดเข้าสเตปนี้ได้" ซึ่งคนละเรื่องกับ "ใครเป็นเจ้าของงานในสเตปนี้" (เช่น เซลล์กด "ชงล้างรอปล่อย" แต่คนทำงานต่อคือฝ่ายล้างรถ) · แก้เจ้าของงาน = แก้ตารางนี้ที่เดียว
    - **⚠️ `_stage_options()` คืน tuple 5 ค่าแล้ว** `(key, ชื่อปุ่ม, ไอคอน, สีเฟส, ฝ่าย)` — เพิ่มค่าใหม่ต้องแก้ **ผู้ใช้ทุกจุด**: `car_json` (ป๊อปอัปบอร์ด) · `scan_page` (หน้าสแกน) · `car_detail.html` · `cars_api` `myStages` (หน้าเซลล์ = list 5 ช่อง) — เคยลืมจุดเดียวแล้วหน้าสแกน 500 (`too many values to unpack`)
  - **★ ปุ่มเปลี่ยนสเตปจัดกลุ่มตามเฟส (ส.ค.69)**: บทบาทสิทธิ์เต็มมี 20 ปุ่มกองเดียวรกเกิน → จัดกลุ่มหัวข้อ รับเข้า/ทำสภาพ/ขาย/ปล่อยรถ (เส้นคั่น · กลุ่มเดียว=ไม่มีหัว) ทั้ง 3 จุด: หน้าสแกน (`stage_groups` จาก `scan_page` + CSS `.sc-ph`) · ป๊อปอัปบอร์ด (`d.direct[].ph` + `PHN`/`phName()` ใน dashboard.html) · หน้าเซลล์ (`myStages[2]`=คีย์เฟส + `SC_PH` ใน renderScChanger) — แหล่งความจริง `C.STAGE_PHASE` ([constants.py](cars/constants.py) gen จาก PHASES)
  - **★ ปุ่ม "เพิ่มรถ" = ผู้บริหาร/แอดมิน/จัดซื้อ เท่านั้น (ส.ค.69)**: `can_add_car` = `{EXEC, ADMIN, PURCHASING}` — ฝ่ายทะเบียน/QC/อู่สีใน ไม่เห็นปุ่มและเรียก endpoint ไม่ได้ (คุมทั้งปุ่มใน /track/ + `car_create` + `api_add_car` จากฟังก์ชันเดียว)
  - **สิทธิ์สเตป (`STAGE_ROLES` · ปรับ ส.ค.69 รอบ 2)**: **"รับเข้า" ไม่มีใครกดได้** (`NO_ONE_STAGES` — รถเกิดที่รับเข้าตอนสร้างอยู่แล้ว · จัดซื้อเลยไม่มีปุ่มสเตป) · **โปรดักชัน (3)** รถรอถ่ายรูป/เช็คซ่อม/รถพร้อมขาย (เอาชงล้างออก) · **ช่าง (3)** ซ่อมเสร็จรอตรวจ/อะไหล่/งานเบาะ (เอาฟิล์มออก) · **ฝ่ายล้างรถ (2)** รอ QC ตรวจ + รอเซลล์ตรวจ (ติ๊กแทน QC ชั่วคราว) · **เซลล์ (7)** **ตีกลับ QC** (=qc_show · ป้ายปุ่มเฉพาะเซลล์ผ่าน `STAGE_BUTTON_LABELS`/`stage_button_label()`)/พร้อมขาย/จอง/ไฟแนนซ์/**ตรวจขนส่ง**/ตรวจรถรอปล่อย/ปล่อยรถ (ตัดรอปิดการขาย + **ขายแล้ว** ออก) · **ฝ่ายทะเบียน = ทุกสเตปยกเว้น เบาะ/อะไหล่** (`REGIST_EXCLUDE` — ไม่ full สเตปแล้ว แต่ยัง `FULL_ROLES` ฝั่งจัดการ) · **รอปิดการขาย/รอตรวจสี/ฟิล์ม/ชงล้าง = ฝ่ายทะเบียน+สิทธิ์เต็มเท่านั้น** · `STAGE_FULL_ROLES={EXEC,QC,PAINTIN}` (สิทธิ์เต็มสเตป) · แอดมิน=ไม่เปลี่ยนสเตป
    - **★ ส.ค.69 รอบ 4 (เจ้าของสั่ง) — สเตปใหม่ `wash_release` "ชงล้างรอปล่อย" + จำกัดสิทธิ์ฝ่ายล้างรถ** (migration 0017):
      - **`wash_release` วางติดกับ `wash` ใน `STAGES`** เพื่อให้ **คอลัมน์บนบอร์ดอยู่ข้างกัน** (ลำดับคอลัมน์ = ลำดับใน `STAGES`) · อยู่ใน `recon_phase`
      - **flow**: เซลล์กด **"ล้างรถรอปล่อย"** (`wash_release`) → ฝ่ายล้างกด **"ล้างเสร็จรถรอปล่อย"** (= `qc_release`) → **เด้งกลับไปหน้าเซลล์ให้ทำงานต่อ** (บางเคสสั่งล้างด่วนตอนรอขาย)
      - **ฝ่ายล้างรถเหลือ 2 ปุ่ม**: รอตรวจ QC (`qc_show`) · ล้างเสร็จรถรอปล่อย (`qc_release`) — **เอา `sales_check` ออก** (มีคน QC จริงแล้ว ไม่ต้องติ๊กแทน)
      - **★ สิทธิ์ติ๊กธง "แยกรายช่อง" (ส.ค.69 รอบ 5 · `FLAG_EDIT_ROLES` ใน [roles.py](cars/roles.py))** — ไม่ใช่สิทธิ์เดียวคุมทั้ง 3 · คนที่ไม่อยู่ในลิสต์ของช่องนั้น **เห็นสถานะได้ แต่ติ๊กไม่ได้**:

        | ช่อง | ใครติ๊กได้ |
        |---|---|
        | ยังไม่ได้ถ่ายรูป · ยังไม่ได้ถ่ายคอนเทนต์ | **โปรดักชัน** (ทีมคอนเทนต์) |
        | รอเปลี่ยนยาง | **ช่าง + ฝ่ายทะเบียน** |
        | ความด่วน (แยกจากธง · `READONLY_PRIORITY_ROLES`) | ทุกบทบาท **ยกเว้นฝ่ายล้างรถ** |

        **ผู้บริหาร (+superuser) ติ๊กได้ทุกช่องเสมอ** (`FLAG_ALWAYS_ROLES` — กันล็อกตัวเองออก) · helper: `can_set_priority()` · `can_set_flag(user, key)` · `flag_perms(user)`
      - **บล็อก 2 ชั้นเสมอ**: **UI** (`flag_perms`/`flagPerms` → `disabled` ราย checkbox ใน [scan.html](templates/scan.html) + ป๊อปอัปบอร์ด + [seller.html](dashboard/templates/dashboard/seller.html)) **และเซิร์ฟเวอร์** (`api_set_flags` เช็ครายคีย์ → 403) — ปิดแค่ UI ไม่พอ เพราะยิง API ตรงได้
      - **เพิ่ม/แก้สิทธิ์ช่องไหน = แก้ `FLAG_EDIT_ROLES` ที่เดียว** (UI ทั้ง 3 จุดอ่านจาก `flag_perms()` อัตโนมัติ)
      - **ป้ายปุ่มต่อบทบาท (`STAGE_BUTTON_LABELS`)** ขยายเป็น 3 บทบาท — สเตปเดียวกันแต่คำบนปุ่มต่างกันตามคนกด: **QC** paint_check="ตีกลับฝ่ายทะเบียน" · sales_check="รอตรวจเซลล์" · qc_show="แก้ไขรอตรวจขึ้นโชว์" · qc_release="แก้ไขรอตรวจรอปล่อย" (**เพิ่มป้าย ไม่ได้ตัดปุ่มเดิมของ QC ออก**) · **CARWASH** qc_show="รอตรวจ QC" · qc_release="ล้างเสร็จรถรอปล่อย" · **SALES** +wash_release="ล้างรถรอปล่อย"
    - **★ ส.ค.69 รอบ 9 (เจ้าของสั่ง) — บังคับ "แนบรูป + ใส่หมายเหตุ" ทุกสเตป ทุกบทบาท**: เดิม `STAGE_FORCE_MEDIA` มีแค่ `{qc_release, release}` → สเตปอื่นกดเปลี่ยนรัวๆ ได้โดยไม่ทิ้งหลักฐาน ตามย้อนหลังไม่ได้ว่าใครทำอะไร/รถสภาพไหนตอนส่งต่อ
      - `STAGE_FORCE_MEDIA` / `STAGE_FORCE_NOTE` ([constants.py](cars/constants.py)) = **ทุกคีย์ใน `STAGE_KEYS`** ยกเว้นที่ใส่ใน **`PROOF_EXEMPT_STAGES`** (ตอนนี้ว่าง) — ผ่อนสเตปไหนแก้จุดเดียว
      - **บังคับ 2 ชั้น**: UI ทั้ง 3 จุด (หน้าสแกน · ป๊อปอัปบอร์ด · หน้าเซลล์) **และ** เซิร์ฟเวอร์ `_proof_error(stage, note, media)` ([views.py](cars/views.py)) ที่ `scan_submit`/`api_set_stage`/`api_seller_set_stage`/`car_stage` — ปิดแค่ UI ไม่พอ ยิง API ตรงได้
      - **เช็คหมายเหตุ "ก่อน" ต่อผลเช็คลิสต์เสมอ** — ไม่งั้นผลเช็คลิสต์ที่ระบบเติมเองจะนับเป็นหมายเหตุ = กดผ่านได้โดยไม่พิมพ์อะไรเลย
      - `car_stage` (หน้า car_detail เก่า ไม่มีช่องแนบรูป) → เด้งไปหน้าสแกนพร้อมข้อความ แทนที่จะเป็นรูรั่วข้ามกฎ
      - **⚠️ เพิ่มสเตปใหม่ = ได้กฎนี้อัตโนมัติ** (gen จาก `STAGE_KEYS`) ไม่ต้องมาไล่เพิ่มเอง
    - **★ ส.ค.69 — ฝ่ายล้างรถไม่ต้องเห็นเช็คลิสต์ตรวจรถ** (`CHECKLIST_HIDE_ROLES={CARWASH}` + `checklist_stages_for(user)` ใน [roles.py](cars/roles.py)): ปุ่ม "ล้างเสร็จรถรอปล่อย" (`qc_release`) บังเอิญอยู่ใน `CHECKLIST_STAGES` → เด็กล้างรถเจอเช็คลิสต์ 15 ข้อซึ่งเป็นงาน "ตรวจสภาพรถ" ของ QC/เซลล์ · ซ่อนทั้งชุด เหลือแค่ รูป+หมายเหตุ ซึ่งเป็นงานเขาจริง · ความด่วนถูกล็อกอยู่แล้วผ่าน `READONLY_PRIORITY_ROLES`
    - **★ ส.ค.69 (เจอตอนทดสอบ) — `can_set_stage` กันสเตปที่ไม่มีอยู่จริง**: เดิมบทบาทสิทธิ์เต็ม/ฝ่ายทะเบียนเช็คแบบ "ไม่อยู่ในลิสต์ห้าม = ผ่าน" → ส่ง `stage=""` หรือคีย์มั่วมาก็ผ่าน **ทำให้รถกลายเป็นสเตปว่าง หลุดหายจากทุกคอลัมน์บนบอร์ด** (เจอจริงตอนฟอร์มส่งค่าว่าง) · เพิ่มเช็ค `stage not in STAGE_NAME → False`
    - **★ ส.ค.69 รอบ 8 (เจ้าของสั่ง) — QC เหลือ 4 ปุ่ม**: **เอา QC ออกจาก `STAGE_FULL_ROLES`** (เหลือ `{EXEC, PAINTIN}`) แล้วระบุปุ่มตรงๆ ใน `STAGE_ROLES` แทน → `paint_check` **"ตีกลับฝ่ายทะเบียน"** · `sales_check` **"รอตรวจเซลล์"** · `qc_show` **"แก้ไขรอตรวจขึ้นโชว์"** · `qc_release` **"แก้ไขรอตรวจรอปล่อย"** (ป้ายปุ่มจาก `STAGE_BUTTON_LABELS[QC]` ที่มีอยู่แล้ว)
      - **เลิกใช้ `QC_EXCLUDE`** — วิธี "ให้ทุกสเตปแล้วค่อยตัดออก" ทำให้ QC ยังเหลือ 13 ปุ่ม (รกเกินงานจริง) และทุกครั้งที่เพิ่มสเตปใหม่ QC จะได้ปุ่มนั้นฟรีโดยไม่ตั้งใจ · allow-list ตรงๆ ปลอดภัยกว่า
      - QC ยังอยู่ใน `FULL_ROLES` (จัดการรถ/ผู้ใช้) เหมือนเดิม — เปลี่ยนแค่ "ปุ่มสเตป"
    - **★ ส.ค.69 รอบ 3 (เจ้าของสั่ง)**: **"ขายแล้ว" (`sold`) เอาออกจากเซลล์** → ฝ่ายทะเบียน(+สิทธิ์เต็ม)เป็นคนกด · **QC ไม่ full สเตปแล้ว** — เพิ่ม **`QC_EXCLUDE`** = show/reserve/finance/transport_check/closing/release/sold (ปุ่มฝั่งขาย) **แต่คงไว้ `sales_check` + `qc_release`** เพราะเป็นงาน "ตรวจ" ของ QC เอง · logic รวมที่ helper **`_stage_exclude(role)`** ใน [roles.py](cars/roles.py) (ใช้ทั้ง `allowed_stages` และ `can_set_stage` — แก้ที่เดียว)
  - **board (board เปลี่ยนได้ตรงจาก UI ผ่อน scan-only)**: `api_set_stage`/`api_seller_set_stage` ใช้ `can_set_stage` (ไม่ใช่ `_direct`) · `cars_api`/`car_json` ส่ง `priority`/`priorityColor` · dashboard.html การ์ดสีจาก priority + dropdown ความด่วน + ปุ่มถ่ายคอนเทนต์ + upload รูปในกล่องยืนยันสเตปบังคับ · `seed_role_accounts` = **10 บัญชีทดสอบ** (รหัส `1234` · exec/regist/qc/paintin/purchase/prod/tech/wash/sales/admintrk)
- **★ บอร์ด "สถานะรถ" เต็มจอ (ก.ค.69)**: แท็บ "สถานะรถ" (แอดมิน · `renderTracking` ใน [index.html](dashboard/templates/dashboard/index.html)) + โหมด "สถานะรถ" (เซลล์ · `renderCarsMode` ใน [seller.html](dashboard/templates/dashboard/seller.html)) = ฝัง `/track/` เป็น **iframe เต็มความกว้างจอ (100vw)**. base.html ตั้ง `html.embedded` เมื่ออยู่ใน iframe → [dashboard.html](templates/dashboard.html) ซ่อนหัวบอร์ด+ปุ่มซ้ำ (`#trkHead` · สลับภาษา/แดชบอร์ดขาย/เพิ่มรถ/QR/ผู้ใช้/Log) ให้บอร์ดใหญ่ขึ้น · **workers เข้า `/track/` ตรง (ไม่ใช่ iframe) ยังเห็นหัว + สลับภาษา 4 ภาษาปกติ** · **⚠️ cluster เดิม `renderTrk`/`_kbCol`/`buildTrkPies`/`_trkBanner` (native board ในหน้า sales) = dead code แล้ว** (แทนด้วย iframe · openTrkCar ยังใช้จากกระดิ่ง)
- **★ ยุบเหลือ login เดียว (มิ.ย.69)**: ไม่มีหน้า login แยกของ tracking แล้ว — ใช้หน้า login หลักของ sales (`/login/`) หน้าเดียว
  - `LOGIN_URL=/login/` · `/track/login/` → redirect `/login/?next=/track/` · `/track/logout/` → redirect `/logout/` · ปุ่มออกใน [base.html](templates/base.html) ใช้ `/logout/` ของ sales (flush ทั้ง 2 auth)
  - **middleware [cars/middleware.py](cars/middleware.py) `TrackSessionBridgeMiddleware`**: เข้า `/track/` แล้วถ้ามี session sales (`oxlet_user`) แต่ยังไม่ได้ login Django auth → เรียก `_bridge_line_to_django_user()` ([views.py](dashboard/views.py)) สร้าง/ผูก Django User `line_<userId>` + `auth.login()` ให้อัตโนมัติ → แอดมิน login sales ครั้งเดียว เข้าแท็บ "สถานะรถ" ได้เลย ไม่ login ซ้ำ · ทำเฉพาะ path `/track/` (ไม่แตะ sales · try/except กัน DB ล่มกระทบ sales) · ต้องวางหลัง `AuthenticationMiddleware`
  - **bridge ตั้ง role ครั้งแรก (เฉพาะตอน user เพิ่งสร้าง · ไม่ทับ role ที่ตั้งทีหลัง)**: sales-admin (position=admin) → **Executive** (กันแอดมินล็อกตัวเองออก) · **คนอื่นทั้งหมด = ไม่ตั้ง role ให้** → เข้ามาได้แต่ "ดูอย่างเดียว" รอแอดมินกำหนดที่ `/track/users/` · worker (ช่าง/ทะเบียน) สร้างผ่าน `/track/users/` แยกเหมือนเดิม
    - **⚠️ ช่องโหว่ที่แก้แล้ว (ส.ค.69)**: เดิมแจก **Sales อัตโนมัติ** ให้ user ใหม่ทุกคน (ตั้งไว้ มิ.ย.69 เพื่อให้เซลล์เปลี่ยนสเตปในหน้าเซลล์ได้) → **พนักงานคนไหนก็ได้ที่มีชื่อในชีต employees พอสแกน QR แล้ว login LINE ครั้งแรก กลายเป็นเซลล์ทันที กดเปลี่ยนสเตปรถได้เลย** (จอง/ไฟแนนซ์/ปล่อยรถ) โดยไม่มีใครอนุมัติ · แก้ที่ `_bridge_line_to_django_user` ([dashboard/views.py](dashboard/views.py)) — เหลือเฉพาะ `created and make_exec` → EXEC
    - **ผลข้างเคียงที่ต้องรู้**: เซลล์ **คนใหม่** จะยังเปลี่ยนสเตปรถในหน้าเซลล์ไม่ได้จนกว่าแอดมินจะตั้ง role `Sales` ให้ที่ `/track/users/` (คนเก่าที่มี role อยู่แล้วไม่กระทบ) · **ผู้ที่เคยได้ Sales อัตโนมัติไปแล้วยังถืออยู่** — ต้องเข้าไปไล่ตรวจ/ถอดเองที่ `/track/users/` (`set_user_role(user, "")` = ไม่มีบทบาท)
  - **★ แอดมินระบบ (break-glass user/password) = Django superuser (ส.ค.69 · แก้บั๊ก "ล็อกตัวเองออก")**: session ของ break-glass ใช้ `user_id="admin"` → middleware ส่ง `make_super=True` เข้า `_bridge_line_to_django_user` → ตั้ง `is_superuser`+`is_staff` (**เติมย้อนหลังให้บัญชีเก่าด้วย ไม่ใช่แค่ตอนสร้าง**) · `roles.get_role()` คืน **Executive ให้ superuser ตายตัว** → บทบาทหาย/ถูกแก้ก็ยังเข้าได้. **บั๊กเดิม**: `line_admin` ถูกสร้างไว้ก่อนโดยไม่มี group และ bridge ตั้ง role แค่ตอน `created` → แอดมินเข้า `/track/` แล้วไม่เห็นปุ่มจัดการเลย (หัวมุมขวาโชว์ "admin ·" ว่างเปล่า) และเข้า `/track/users/` ไปตั้งบทบาทเองก็ไม่ได้ = **ล็อกตัวเองออก** · ⚠️ superuser เข้า `/dj-admin/` ได้ด้วย (ยอมรับได้ — บัญชีนี้ป้องกันด้วย `OXLET_ADMIN_PASSWORD` ที่เป็น env secret)
  - **★ กันล็อกซ้ำสำหรับแอดมินทาง LINE**: bridge เพิ่มเคส "บัญชีมีอยู่แล้ว + เป็น sales-admin + **ยังไม่มีบทบาทเลย**" → เติม `Executive` ให้ (ไม่ทับบทบาทที่ตั้งไว้แล้ว — เติมเฉพาะตอนว่างเปล่า)
  - **worker (ช่าง/ฝ่ายทะเบียน) = บัญชี Django username/password** สร้างที่ `/track/users/` → login ผ่านช่องรหัสในหน้า `/login/` เดียวกัน (`login_view` ลอง`authenticate()` หลัง break-glass — DB ล่ม=ข้าม)
    - **★ position ของทางนี้ขึ้นกับ `is_superuser` (ส.ค.69 · แก้บั๊ก "เข้าแดชบอร์ดขายไม่ได้")**: **superuser → `position="admin"`** (เห็นแดชบอร์ดขาย + ปุ่ม "แดชบอร์ดขาย" ใน `/track/`) · ไม่ใช่ superuser → `position="worker"` ตามเดิม (เห็นแค่บอร์ดสถานะรถ ไม่โหลดข้อมูลขาย/ลูกค้า · PDPA). **บั๊กเดิม**: ตี `worker` ให้ทุกคน → superuser ที่ login ด้วย user/password เข้า `/dashboard/` แล้วได้หน้าสถานะรถแทนแดชบอร์ดขาย + ปุ่มจัดการใน `/track/` หายหมด
    - **⚠️ 2 ทางนี้ชื่อผู้ใช้ชนกันได้**: ถ้ามี Django user ชื่อเดียวกับ `OXLET_ADMIN_USER` (เช่นทั้งคู่ชื่อ `admin`) → **break-glass ถูกเช็คก่อน** · รหัสไม่ตรง break-glass = ตกไปทาง `authenticate()` เงียบ ๆ แล้วได้สิทธิ์คนละชุด — เวลาดีบัก "แอดมินสิทธิ์หาย" ให้เช็คก่อนว่า login ผ่านทางไหน (ดู `method` ใน Log เข้าระบบ: `admin` = break-glass · `worker` = Django user)
  - **⚠️ ตัด redirect loop**: ถ้า login sales อยู่แต่ bridge ไม่สำเร็จ (DB ยังไม่ต่อ/ล่ม) → middleware คืนหน้า "ระบบติดตามรถยังไม่พร้อม" (200) แทนเด้ง `/login/` ที่วนกลับ `/track/` (เคยเป็น ERR_TOO_MANY_REDIRECTS บน prod ที่ยังไม่ตั้ง DB)
- **จัดการบทบาทในเว็บ**: หน้า **`/track/users/`** (`manage_users` ใน [cars/views.py](cars/views.py) · เข้าได้เฉพาะ Executive/Admin) — เพิ่มผู้ใช้/เปลี่ยนบทบาท/รีเซ็ตรหัส/ปิด-เปิด โดยไม่ต้องเข้า Django admin · superuser = Executive เสมอ (แก้บทบาทไม่ได้) · `/dj-admin/` เก็บเป็น break-glass
- **🟢 คนเข้าเว็บตอนนี้ (online now · มิ.ย.69)**: model **`Presence`** ([cars/models.py](cars/models.py) · 1 แถว/identity · `update_or_create` ไม่บวมตาราง) + endpoint **`/api/presence`** (`presence_ping` ใน [dashboard/views.py](dashboard/views.py) · GET เลี่ยง CSRF · best-effort) — heartbeat ทุก ~45 วิ จาก **index.html (แอดมิน)** + **seller.html (เซลล์)** → upsert `last_seen` + คืน `online` = นับ identity ที่ last_seen ภายใน 150 วิ · แสดงเป็นชิป **"<n> ออนไลน์" ข้างเมนูจัดการ** ในหน้าหลัก (`#online-count`) · **กดชิป → `openOnlinePanel()`** ดึง `/api/presence/list` (`presence_list` · เฉพาะ position==admin) โชว์รายชื่อคนออนไลน์ + หน้าที่อยู่ + ล่าสุดกี่วินาที · ต้อง `migrate cars` (เพิ่มตาราง) ก่อนใช้
- **📋 Log การเข้าสู่ระบบ (audit · มิ.ย.69)**: model **`LoginEvent`** ([cars/models.py](cars/models.py) · เก็บใน tracking Postgres) บันทึกทุกการ login — บัญชี/ชื่อ/วิธี(`line`/`admin`/`worker`)/สำเร็จ-ล้มเหลว/บทบาท/IP/อุปกรณ์/เวลา · เขียนผ่าน `log_login()` ([dashboard/services/audit.py](dashboard/services/audit.py)) **best-effort** (DB ล่ม/ยังไม่ migrate = ข้ามเงียบ ไม่ทำให้ login พัง) · hook ใน `login_view` (admin/worker สำเร็จ + รหัสผ่านผิด=ล้มเหลว) + `line_login_callback` (LINE สำเร็จ/พนักงานไม่พบ) · ดูได้ 2 ที่: **(1)** หน้าเต็ม **`/track/logins/`** (`login_log` · ปุ่ม "Log เข้าระบบ" ในหน้า `/track/`) **(2)** **modal ในแดชบอร์ด sales** — เมนูจัดการ → "Log เข้าระบบ" (`openLoginLog`/`renderLoginLog` ใน [index.html](dashboard/templates/dashboard/index.html) ดึง JSON `/track/api/logins` = `login_log_api`) · ทั้งคู่ Executive/Admin · สรุปวันนี้ (สำเร็จ/ล้มเหลว/บัญชีไม่ซ้ำ) + ตาราง 200-300 ล่าสุด + กรอง สำเร็จ/ล้มเหลว · ต้อง `migrate cars` (เพิ่มตาราง) ก่อนใช้
- **DB (Postgres)**: [settings.py](oxlet/settings.py) อ่าน `DATABASE_URL` (Supabase) **หรือ** `POSTGRES_URL` (Vercel Postgres ฉีดให้อัตโนมัติ) · pooled 6543 transaction mode สำหรับ runtime → `CONN_MAX_AGE=0` + `DISABLE_SERVER_SIDE_CURSORS=True` (จำเป็นกับ pgbouncer) · ไม่ตั้ง = SQLite (local dev). **migrate ใช้ direct conn (5432)** ไม่ใช่ pooler · **⚠️ ขัดโน้ตเก่า** ที่ว่า "ไม่ต้องใช้ pooler" — อันนั้นจริงเฉพาะตอนคุย Supabase ผ่าน REST · ORM ต้องใช้ pooler
- **รูป/วิดีโอ → Google Drive (ปัจจุบัน · ย้ายจาก Supabase Storage หลังขึ้น VPS)**: [cars/gdrive.py](cars/gdrive.py) อัปผ่าน REST (requests, ไม่มี SDK) ลง Drive ของ `oxletauto@gmail.com` ด้วย **OAuth refresh token** (service account อัปลง Drive ไม่ได้ — quota 0 · ต้องเป็น OAuth ของบัญชีจริง · scope `drive.file` = เห็นเฉพาะไฟล์ที่แอปสร้าง)
  - **env**: `GDRIVE_CLIENT_ID`/`GDRIVE_CLIENT_SECRET`/`GDRIVE_REFRESH_TOKEN` (+ `GDRIVE_ROOT_FOLDER_ID` ออปชั่น · `GDRIVE_MAX_UPLOAD_MB` default 200) · ขอ token ครั้งเดียวด้วย `python manage.py gdrive_auth` (loopback OAuth บนเครื่องมีเบราว์เซอร์) · `gdrive_setup` สร้างโฟลเดอร์แม่
  - **โฟลเดอร์ต่อรถ**: ไฟล์ของรถแต่ละคันแยกโฟลเดอร์ ชื่อ `โค้ดรถ ทะเบียน(ทะเบียนเดิม)` เช่น `CS0011 กก1414(4525)` · `_ensure_car_folder()`/`_car_folder_name()` ([cars/views.py](cars/views.py)) เก็บ id ไว้ที่ `Car.drive_folder_id` (สร้างครั้งแรกที่อัป · rename เมื่อแก้ทะเบียน) · **ทะเบียนเดิม** = `Car.plate_original` ที่ `Car.save()` จำให้อัตโนมัติเมื่อทะเบียนเปลี่ยน (เทียบกับ `from_db` ไม่ยิง query เพิ่ม)
  - **อัปโหลด**: หน้าสแกน/หน้าเซลล์/เพิ่มรถ POST ไฟล์ (multipart) → **`/track/api/upload`** (`api_upload` · csrf_exempt+login_required · ส่ง `code` เพื่อจัดเข้าโฟลเดอร์รถ) → server อัป resumable streaming เข้า Drive + ตั้ง public link → คืน `{id, video, url}` · เก็บใน `ScanLog.media`=`[{id,video}]` / `Car.photo.name`=Drive id. **บน VPS ไม่มีลิมิต body 4.5MB แบบ Vercel** เลยอัปผ่าน server ตรง (เลิกใช้ `sign_upload`+PUT ตรงเข้า Supabase) · `api_sign_upload` ยังอยู่ (legacy ไม่ถูกเรียก)
  - **★ ตั้งชื่อไฟล์ตามสถานะ+ผู้เปลี่ยน+เวลา (ก.ค.69)**: หลังยืนยันเปลี่ยนสเตป (`scan_submit`/`api_seller_set_stage`) → `_label_stage_media(log, car)` ([cars/views.py](cars/views.py)) เปลี่ยนชื่อไฟล์ใน Drive เป็น `สถานะ(ผู้เปลี่ยน) วันเวลา ลำดับ.นามสกุล` เช่น `รับเข้า(หมี) 8ก.ค.69 14-30 1.jpg` — สถานะ=`car.stage_name` · ผู้เปลี่ยน=`log.worker_name` (ชื่อที่ log ไว้ = ชื่อจาก LINE) · เวลา=เวลาเปลี่ยนสเตปจริง (โซนไทย, ปี พ.ศ. 2 หลัก, ใช้ `-` แทน `:` กันชื่อไฟล์พังบน Windows) · นามสกุลจากไฟล์เดิม (`gdrive.get_name`) ไม่งั้น `.mp4/.jpg` ตาม video flag. **เฉพาะไฟล์บน Drive (id ไม่มี "/") — ไฟล์ดิสก์ข้าม** · **best-effort** (Drive ล่ม/ไม่ตั้งค่า = ไม่เปลี่ยนชื่อ ไม่พังงานเปลี่ยนสเตป · ชื่อเป็นแค่ป้าย ลิงก์แสดงผลอิง id ไม่กระทบ) · helper `gdrive.rename()`/`gdrive.get_name()` ([cars/gdrive.py](cars/gdrive.py))
  - **แสดงผล**: `_media_urls()` คืน `{url,video}` — Drive id (ไม่มี "/") → รูป `drive.google.com/thumbnail?id=&sz=w1920` (ฝัง `<img>`) · วิดีโอ `drive.google.com/file/d/<id>/view` (เปิดตัวเล่น Drive) · path เก่ามี "/" → Supabase (legacy back-compat)
  - **storage backend** ([cars/storage.py](cars/storage.py) `GoogleDriveStorage`): ใช้กับ `ImageField`/`FileField` (`Car.photo`/`doc_registration`) — name=Drive id · เลือกใน [settings.py](oxlet/settings.py) **Drive > Supabase(legacy) > FileSystemStorage**
  - **★ แยกที่เก็บตามประเภท (มิ.ย.69)**: `api_upload` รับ `target`:
    - **รูปหน้าปกรถ** (index.html `addTrkCar` ส่ง `target=disk`) → **ดิสก์ VPS เสมอ** (ไฟล์เล็ก ไม่ต้องตั้ง Drive)
    - **รูปรายงาน/วิดีโอ** (scan.html/seller.html · ไม่ส่ง target) → **Google Drive ถ้าตั้งไว้** (โชว์ลิงก์) · ยังไม่ตั้ง = ดิสก์ VPS (fallback)
    - logic: `if target != "disk" and gdrive.is_configured()` → Drive · ไม่งั้น → `_save_local_media` (ดิสก์)
  - **เก็บดิสก์**: `_save_local_media` บันทึก `MEDIA_ROOT/cars/<code>/...` ผ่าน `default_storage` → คืน `{id: path, url: /media/...}` · nginx เสิร์ฟ `location /media/` · `_media_urls` token ที่มี "/" → `/media/<path>` (วิดีโอเล่นตรงใน `<video>` ได้ ต่างจาก Drive ที่ต้อง /view). `MEDIA_URL="/media/"` (leading slash จำเป็น)
  - **Storage backend (ImageField)** เลือกตามลำดับ Drive > Supabase(legacy) > ดิสก์ VPS · Drive เป็นออปชั่นสำหรับรูปรายงาน/วิดีโอ ไม่ใช่ของบังคับ
- **QR**: gen PNG ต่อ request ด้วย `qrcode`+`Pillow` (ไม่เก็บไฟล์) ชี้ไป `{SITE_URL}/track/scan/<code>/` → ต้องตั้ง **`SITE_URL`** เป็นโดเมน prod **ก่อนปริ้น QR**
- **deps เพิ่ม** ([requirements.txt](requirements.txt)): `psycopg2-binary`, `qrcode[pil]`, `Pillow` · **[vercel.json](vercel.json) ขยาย `maxLambdaSize` 15→50mb** (ไม่งั้น build ไม่ผ่าน)
- **settings ที่เพิ่มเข้า sales เดิม**: INSTALLED_APPS (+admin/auth/contenttypes/messages/cars) · MIDDLEWARE (+Authentication/Message/XFrameOptions) · `X_FRAME_OPTIONS="SAMEORIGIN"` (กัน iframe เซลล์ของ sales พัง) · TEMPLATES DIRS (+`templates/`) + context_processors (auth/messages/cars.context.nav) · sales ใช้ signed-cookie session เหมือนเดิม (Django auth ทำงานบน signed_cookies ได้)
- **Django 5.0**: `LogoutView` รับเฉพาะ POST → [base.html](templates/base.html) ปุ่มออกเป็น form POST (ไม่ใช่ลิงก์ GET)
- **env ที่ต้องตั้งบน Vercel (ใหม่)**: `DATABASE_URL` (Supabase pooled 6543, SECRET) **หรือ** `POSTGRES_URL` (Vercel Postgres ใส่ให้เอง) · `SITE_URL` (โดเมน canonical — มี default แล้ว) · ออปชั่น (เก็บรูป): `SUPABASE_STORAGE_BUCKET`+`SUPABASE_URL`+`SUPABASE_SECRET_KEY` · ออปชั่น (push): `LINE_CHANNEL_TOKEN`/`LINE_GROUP_ID`
- **ขั้นตอนเปิดใช้ (ยังไม่ทำ — รอต่อ DB)**: (1) สร้าง DB — Vercel Postgres (Storage→Create→Postgres, ใส่ env ให้เอง) หรือ Supabase (Postgres + bucket `car-photos` public) → (2) ตั้ง `DATABASE_URL`/`POSTGRES_URL`=direct(5432) ในเครื่อง → `python manage.py migrate` + `createsuperuser` (=Executive) [+ `seed_demo` สาขา/รถตัวอย่าง ถ้าต้องการ] → (3) ตั้ง env บน Vercel (pooled 6543) → redeploy. **ไม่ต้องตั้ง bucket ก็ใช้ได้** (แค่อัปรูปรถยังไม่ได้ จนกว่าจะตั้ง Storage)
- **ตรวจแล้ว (local, sqlite)**: `manage.py check` ผ่าน · migrate ผ่าน · ทุกหน้า /track/* render 200 + QR PNG ออก · sales เดิมไม่กระทบ (/login/ 200, /dashboard/ redirect ปกติ)

### 🔗 เชื่อมเว็บโชว์รูม (oxlet_web) — sync รถ+รูป ผ่าน webhook (ก.ค.69)
รถในสต็อก (tracking `cars.Car`) → ประกาศขายบนเว็บโชว์รูม **oxlet_web** (Django project แยก · repo `github.com/Wattanakit27/oxletauto_web` · DB คนละตัว) — เชื่อมด้วย **webhook (HTTP POST) ไม่ใช่แชร์ DB** (decoupled):
- **ตัวผูก**: `Car.code` ↔ `Vehicle.stock_code` (1 รถจริง = 1 ประกาศ)
- **ยิงเมื่อไหร่**: `post_save` signal ของ `Car` ([cars/models.py](cars/models.py) `_notify_showroom_on_car_save`) → `notify_showroom()` ([cars/showroom_sync.py](cars/showroom_sync.py)) ยิงเฉพาะสเตป **show/reserve/sold** (daemon thread · best-effort ไม่บล็อกงาน/ไม่พังถ้าโชว์รูมล่ม)
- **ส่งอะไร** (POST `<SHOWROOM_WEBHOOK_URL>` = โชว์รูม `/api/stock-update/` · JSON · header `X-Stock-Secret`):
  - สเปกพื้นฐาน (brand/model/year/color/km/plate) → โชว์รูม **สร้างประกาศให้อัตโนมัติ** (โชว์ลูกค้าทันที · ราคา/รายละเอียด staff เติมทีหลัง)
  - สถานะ: **show→available · reserve→reserved · sold→ซ่อน (status=sold)** · สเตปอื่นไม่ยิง
  - รูปขาย `photos:[{url,key}]` → โชว์รูม GET โหลดรูปเก็บสำเนาเอง + reconcile (เปลี่ยนปก/เพิ่ม/ลบตาม backend · `key`=ต้นทาง กันสลับผิด/ซ้ำ)
- **รูปขาย (หลายรูป + ปก)** เก็บใน **`Car.extra['sale_photos']`** (list ของ id/path · **รูปแรก=ปก**) — คนละชุดกับ `Car.photo` (รูปติดตาม 1 รูป) และ `ScanLog.media` (รูปรายงานสถานะ):
  - เพิ่มตอนสร้างรถ: หน้า "เพิ่มรถ" ([index.html](dashboard/templates/dashboard/index.html) `addTrkCar` · อัปหลายรูป · target=disk) → `api_add_car` เก็บใน extra **ก่อน** save (post_save ยิง webhook ครั้งเดียวพร้อมรูป · กัน race/ยิงซ้ำ)
  - จัดการทีหลัง: หน้า **car_edit** ([templates/car_form.html](templates/car_form.html) · แกลเลอรี thumbnail + ⭐ ตั้งปก + ลบ + อัปหลายรูป) → `api_car_photos` (`/track/api/car/<code>/photos` · action add/remove/cover) → save → sync
- **env (ว่าง = ปิดสนิท no-op ทั้ง 2 ฝั่ง · ระบบเดิมไม่กระทบ)**: `SHOWROOM_WEBHOOK_URL` (url โชว์รูม + `/api/stock-update/`) · `STOCK_SYNC_SECRET` (ค่าลับ ต้องตรงกับ oxlet_web) · **`SITE_URL`** (โดเมน backend จริง — โชว์รูมโหลดรูปจาก `SITE_URL/media/...` · nginx ต้องเสิร์ฟ `/media/`)
- **ทิศทางเดียว** (backend → โชว์รูม) · lead/จอง จากโชว์รูมยังไม่ sync กลับ · ยังไม่มี pull สำรอง (webhook พลาด = เงียบ)
- **ฝั่งรับ (oxlet_web)**: `Vehicle.stock_code` (0021) + `VehicleImage.src` (0022 · ผูกรูปกับต้นทาง reconcile/dedup กันซ้ำ) · view `api_stock_update` + `_sync_car_photos` · **ต้อง `migrate` ตอน deploy**

### 🔄 ดึงรถสดจากเว็บ Car Spend (ส.ค.69) — `manage.py sync_carspend`
นำเข้ารถจากระบบต้นทาง **Car Spend** (`autosoftware.co.th/oxletauto` · Prosoft Car) เข้าตาราง `Car` **ผ่าน HTTP สด** — ไม่ต้อง export zip มือเหมือน [import_cars](cars/management/commands/import_cars.py)
- **[cars/carspend.py](cars/carspend.py)** = client อ่านอย่างเดียว (login → list → detail) คืน dict **รูปร่างเดียวกับ cars.json ใน zip** → [sync_carspend](cars/management/commands/sync_carspend.py) `import` **mapping/helper ชุดเดียวกับ import_cars** (`STATUS_TO_STAGE`, `BRANCH_MAP`, `_parse_date`, `_int`, `_model`) — **อย่า copy ไปแก้แยก ไม่งั้นกติกาแตกเป็นสองมาตรฐาน**
- **ต้องเข้า 2 หน้าเสมอ** — หน้า list มีแค่ชื่อรถ/ราคา/สถานะ: `?p=cars&sts=&pg=N` (หน้าละ 100 · ได้ `key` md5 + สถานะ) → `?p=car_detail&key=<md5>` (ข้อมูลครบ + อัลบัมรูป)
- **⚠️ Cloudflare หน่วง client ที่ส่ง header น้อยอย่างหนัก** (~90 วิ/หน้า จนโดนตัดสาย `ConnectionResetError`) — ต้องส่ง `HEADERS` ชุดเต็มแบบ Chrome ถึงได้ ~0.8 วิ/หน้า · **ห้ามใส่ `br` ใน Accept-Encoding** (requests ถอด brotli ไม่ได้ → ได้ข้อความเละ เช็ค `"ออกจากระบบ" in html` จะ false หลอก)
- **`--status`** — **รถขายแล้วไม่อยู่ในรายการปกติ**: `stock` (default) = สต็อกปัจจุบัน **236 คัน** (พร้อมขาย 118 · ซ่อม 39 · จอง 36 · รอปิดการขาย 22 · จัดไฟแนนซ์ 21 · **ไม่มี "ขายแล้ว" ปนเลย**) · `sold` = **~3,540 คัน** (~75-90 นาที · ควรรันใน `screen`) · ตัวกรอง `sts` ใช้ได้ **ต่อเมื่อใส่ `pg` คู่กัน** (ไม่งั้น cap 100 แถวและนับซ้ำมั่ว)
- **⚠️ "รหัสรถ" ของต้นทางไม่ unique** — เจอ 2 คู่ที่เป็นคนละคันจริงแต่รหัสเดียวกัน (`CS03820` = TRITON/MG 3 · `CS03789` = VIOS/Hilux Revo) แต่ `Car.code` เป็น **primary key** → `_resolve_code()` เทียบ `extra.source_key` (md5 จาก URL = unique จริง) ก่อน ถ้าชนคันอื่นเติม suffix `-2` พร้อม warning (**ไม่ปล่อยให้รถหายเงียบ**)
- **สเตป/วันรับเข้า ตั้งเฉพาะตอนสร้างใหม่** (`create_defaults`) → re-sync ไม่รีเซ็ตสเตปที่หน้างานขยับไปแล้ว · สถานะต้นทาง "ขายแล้ว" → `stage=sold` + `status=sold` (หลุดบอร์ดตามกติกาเดิม)
- **`--photos`** โหลด **รูปปกคันละ 1 รูป** (~260 KB · อัลบัมเฉลี่ย ~13 รูป/คัน) ลง **ดิสก์ VPS ตรง** ผ่าน `FileSystemStorage` — **ไม่ใช้ `default_storage`** เพราะถ้าตั้ง `GDRIVE_*` ไว้ default จะเป็น Drive แต่กติกาคือ "รูปหน้าปกรถ → ดิสก์เสมอ" · ชื่อไฟล์มี `/` → `GoogleDriveStorage.url()` เสิร์ฟจาก `MEDIA_URL` ให้เอง · ข้ามคันที่มีรูปแล้ว
- **รูปบนเว็บต้นทางเปิดสาธารณะ** (ไม่ต้องล็อกอิน) → `extra.image_urls` = `[{file, full(1280x960), thumb}]` ทั้งอัลบัม เอาไปแปะ `<img src>` ตรงได้โดยไม่ต้องโหลดเก็บ (ประหยัด ~900 MB)
- **env**: `CARSPEND_USER` / `CARSPEND_PASS` · **dep ใหม่**: `beautifulsoup4`
- **`--dry-run` ก่อนเสมอ** (ไม่เขียน DB แค่บอกว่าจะสร้าง/อัปเดตกี่คัน + สถานะ/สาขาที่ยัง map ไม่ได้)
```bash
cd /opt/oxlet && .venv/bin/python manage.py sync_carspend --dry-run --limit 5
cd /opt/oxlet && .venv/bin/python manage.py sync_carspend --photos
```

### 🔖 ป้ายเวอร์ชันมุมขวาล่าง (ส.ค.69)
ทุกหน้า (login/index/seller/track base) โชว์เวอร์ชันมุมขวาล่าง — **สูตร: จำนวน git commit ÷ 10** (100 commits = v10.0 · เจ้าของกำหนด) · `app_version()` ใน [cars/context.py](cars/context.py) (git rev-list --count HEAD · cache ต่อ process · ไม่มี .git = ป้ายซ่อน) → `APP_VERSION` ผ่าน context processor `cars.context.nav` · ใช้เช็คว่า deploy ล่าสุดติดหรือยัง (ดูได้ตั้งแต่หน้า login)

## Known issues / limitations

- **Cold start ช้า** บน Vercel — request แรกหลังนิ่งนาน ~5-10s (pip install + Django boot + auth) · **หน้าสแกน /track/scan/ ก็โดน** — คนงานยืนหน้ารถอาจรอ ~10s (trade-off ของการอยู่บน serverless)
- **Sheets API quota** — ปกติ dashboard อ่าน **mirror/pre-compute (Supabase) ไม่แตะ Sheet** · Sheet ถูกอ่านแค่ตอน sync (~15-20 req ทุก ~5 นาที — ต่ำกว่า 300/min/project มาก)
- **leads upsert ใหญ่** — 15k แถวเป็น jsonb ก้อนเดียว เคยชน Supabase statement timeout (8s) · บรรเทาด้วย `_trim_row` · ถ้ายังชนบ่อย → `alter role service_role set statement_timeout='30s'`
- **Schedule precision = 1 นาที** (ตาม cron interval)
- **No deduplication** — ถ้า n8n ยิง 2 ครั้งใน 1 นาที (rare) จะส่ง Flex 2 ครั้ง
- **Vercel Hobby** = 1 cron job/วัน (ใช้ external n8n แทน)
- **เซลล์ใหม่** ที่เพิ่มผ่าน 🎯 ตั้งเป้า/ทีม จะใช้งานได้ทันที **ยกเว้น URL `/s/<token>/`** ที่ต้อง add token เองใน code
