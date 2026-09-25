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
| `/api/admin/db_tables` | `admin_db_tables` | **superuser/ผู้บริหารเท่านั้น** (`_is_boss`) GET: สารบัญฐานข้อมูล — ทุกตาราง + จำนวนแถว + คำอธิบายว่าเก็บอะไร + ป้าย PDPA + คีย์ใน `dash_kv` (นับแถวอย่างเดียว **ไม่ดึงเนื้อข้อมูล**) → เมนูจัดการ "ฐานข้อมูล" · ดู section "สารบัญฐานข้อมูล" |
| `/api/admin/db_export` | `admin_db_export` | **superuser/ผู้บริหารเท่านั้น** (`_is_boss`) GET: **ดาวน์โหลดข้อมูลออกมาเป็นไฟล์** — `?table=<ชื่อตาราง>` = CSV ตารางเดียว · `?all=1` = .zip ทุกตาราง + `อ่านก่อน.txt` · ไม่ใส่อะไร = JSON ลิสต์ตารางที่ดึงได้ · **ปิด LINE user id ของพนักงานให้ก่อนเขียนไฟล์** (ดู section "ดาวน์โหลดข้อมูล (export)") |
| `/dashboard/sql/` | `sql_page` | **superuser/ผู้บริหารเท่านั้น** (`_is_boss`) — **หน้าเต็ม "ดูข้อมูลดิบ (SQL)"** แทนหน้าต่างลอยเดิม (เจ้าของสั่ง ก.ย.69 "ไม่อยากให้มีหน้าต่างลอย") · `?table=<ชื่อตาราง>` = เปิดตารางนั้นให้เลย และ URL เปลี่ยนตามตารางที่กด (ก๊อปลิงก์ส่งต่อได้) · ไม่ login → `/login/?next=` · ใช้ API เดิม (`db_query`/`db_tables`/`db_export`) · template แยก [sql.html](dashboard/templates/dashboard/sql.html) **ไม่ได้อยู่ใน index.html** |
| `/api/admin/db_query` | `admin_db_query` | **superuser/ผู้บริหารเท่านั้น** (`_is_boss`) — **ยิง SQL ดูข้อมูลดิบ** · GET = รายชื่อตาราง+คอลัมน์ (`?table=` = ขอคำสั่งตั้งต้น) · POST `{sql, from, to, limit}` = ผลลัพธ์ JSON · POST `{…, export:1}` = CSV ทุกแถวตามเงื่อนไข · **อ่านอย่างเดียว** (READ ONLY transaction ฝั่ง Postgres) · ดู section "ดูข้อมูลดิบ (SQL)" |
| `/checkout/api/checkins` | `api_checkins` | **admin/ผู้บริหาร** GET `?date=YYYY-MM-DD` (ไม่ใส่ = วันนี้): เช็คชื่อเข้างานรายวัน — มาแล้ว (ตรงเวลา/สาย/อ่านเวลาไม่ออก) · **ยังไม่เช็คชื่อ** · **วันหยุดของคนนั้น** (ตัดคนที่ตรงกับช่อง "วันหยุด" ออก ไม่งั้นขึ้นค้างทั้งที่เขาหยุดจริง) · **ตัดคนที่ติ๊ก "เช็คชื่อ" ออก (ผู้บริหาร) ทิ้งทั้งหมด** → เมนู "เช็คชื่อเข้างาน" · ลิงก์ตรง `/dashboard/?panel=checkin` |
| `/checkout/api/employees` | `api_employees` | **admin/ผู้บริหาร** GET: ทะเบียนพนักงานในระบบ (ชื่อเล่น · ชื่อที่ตั้งใน LINE · ตำแหน่ง · **เวลาเข้างาน** · วันหยุด · ผูก LINE กี่บัญชี) · POST `{action:"save"\|"delete", …}` เพิ่ม/แก้/ลบ · ช่อง **"เช็คชื่อ"** (`trackCheckin`) ติ๊กออก = ผู้บริหาร ไม่ต้องเช็คชื่อเข้างาน · **ไม่ส่ง LINE user id ของพนักงานออกมา** (บอกแค่จำนวนบัญชีที่ผูก) → เมนู "ทีม & สิทธิ์ → พนักงาน" |
| `/checkout/api/customers` | `api_customers` | **admin/ผู้บริหาร** GET: **แชทลูกค้าที่ทักเข้า LINE OA** — ไม่ใส่อะไร = รายชื่อลูกค้า (ชื่อ · LINE id · จำนวนข้อความ · ทักครั้งแรก/ล่าสุด · เข้ามาทางบัญชีไหน) · `?q=` ค้นหาชื่อ · `?user_id=` = บทสนทนาย้อนหลังของคนนั้น · **ซ่อน LINE id ของพนักงาน** (`LineProfile.is_employee`) แต่โชว์ของลูกค้า (เจ้าของขอไว้ทักกลับ) |
| `/checkout/api/reply` | `api_reply` | **admin/ผู้บริหาร** POST `{user_id, text}`: **ตอบแชทลูกค้า** — ส่งผ่าน LINE push ด้วย token ของบัญชี OA ที่ลูกค้าคุยอยู่ + บันทึกลง `GroupChat` เป็น `direction=out` พร้อมชื่อคนตอบ · **ส่งสำเร็จเท่านั้นถึงบันทึก** (ดู section "ตอบแชทลูกค้า") |
| `/api/admin/refresh_data` | `admin_refresh_data` | admin POST: สั่ง sync + precompute เดี๋ยวนี้ (ปุ่มรีเฟรชในหน้าสถานะระบบ) — คำนวณสดจาก Google ~10 วิ |
| `/api/admin/trends` | `admin_trends` | admin GET: JSON เทรนด์ followup (`FollowupLog` รายวัน + `SellerWeekly` รายสัปดาห์ + `rounds`) — endpoint สำรอง (หน้า dashboard ฝัง inline ผ่าน `trends_json` context แล้ว · ดู section "เก็บสถิติ followup + เทรนด์") |
| `/api/admin/report_config` | `admin_report_config` | admin: GET=อ่าน, POST=บันทึก config "รายงานเข้าไลน์รายวัน" (`{enabled,time,mode,test_id,group_id}` · เก็บ KVStore `report_line_config`) — เมนูจัดการ "รายงานเข้าไลน์" (ดู section "รายงานเข้าไลน์") |
| `/api/admin/social` | `admin_social` | admin GET `?from=&to=`: ตัวเลข **engagement โซเชียล** (Meta + TikTok) ให้แท็บ **"โซเชียล"** — ยอดรายวัน (หาผลต่างจาก snapshot สะสม) · ยอดรวมช่วง · โพสต์/คลิปที่ปังสุด · ค่าโฆษณา · ดู section "แท็บโซเชียล" |
| `/api/admin/meta_sync` | `admin_meta_sync` | admin: GET=สถานะดึงข้อมูล Meta (รอบล่าสุด · โควต้า · กดได้ไหม) · POST=ดึงเดี๋ยวนี้ (รันใน thread) — **มีด่านกันกดถี่ ไม่ผ่าน=429+เหตุผล+นาทีที่ต้องรอ** · เมนู "Meta (Facebook) — ดึงข้อมูล" · `?panel=meta` |
| `/api/admin/report_test` | `admin_report_test` | admin POST `{target?}`: แคปตารางรายงาน (Playwright) → ส่งรูปเข้า LINE เดี๋ยวนี้ (ปุ่ม "ส่งทดสอบ") · ⚠️ ได้จริงเฉพาะ prod (LINE ต้องดึงรูปจาก URL https สาธารณะ) |
| `/api/admin/line_group_name` | `admin_line_group_name` | admin POST `{id}`: ดึงชื่อกลุ่ม LINE จาก group id (LINE group summary API · บอทต้องอยู่ในกลุ่ม) → ปุ่ม "ตรวจชื่อ" ในพาเนลรายงาน (ยืนยันว่า id คือกลุ่มไหน) |
| `/api/admin/line_groups` | `admin_line_groups` | admin GET: รายชื่อกลุ่ม LINE ที่บอทรู้จัก (สะสมจาก webhook · KVStore `line_groups`) → dropdown เลือกกลุ่มในพาเนลรายงาน |
| `/api/tiktok/webhook` | `tiktok_webhook` | **public** (csrf_exempt) — **webhook ของ TikTok for Developers** (ก.ย.69 เจ้าของขอ callback ไปวางในหน้า TikTok) · POST = event → `dash_tiktok_event` (raw) · GET = 200 (`?challenge=` ตอบค่ากลับ) · ตรวจลายเซ็น `TikTok-Signature` ด้วย `TIKTOK_CLIENT_SECRET` · ดู section "TikTok webhook" |
| `/api/admin/tiktok/accounts` | `admin_tiktok_accounts` | admin: GET=ช่อง TikTok ที่เชื่อมแล้ว (**ไม่มี token**) · POST `{label}` = สร้างลิงก์ขออนุญาตรายช่อง (ใช้ได้ครั้งเดียว หมดอายุ 7 วัน) |
| `/api/admin/tiktok/sync` | `admin_tiktok_sync` | admin: GET=สถานะดึงยอดคลิป · POST=ดึงเดี๋ยวนี้ (ด่านกันกดถี่ 15 นาที → 429) |
| `/api/line/webhook` | `line_webhook` | **public** (csrf_exempt) — LINE Messaging API webhook · จับ `groupId`+ชื่อ ตอนบอทได้ event จากกลุ่ม (join/message) → เก็บ `line_groups` (ยืนยัน signature ถ้ามี `LINE_CHANNEL_SECRET`) · **ต้อง register URL นี้ใน LINE Console** (Messaging API → Webhook URL = `SITE_URL/api/line/webhook` · เปิด Use webhook) |
| `/api/line/group_ingest` | `line_group_ingest` | **public** (csrf_exempt · auth `?secret=CRON_SECRET` / header `X-Cron-Secret`) — รับ group event จาก **n8n** (กรณี n8n เป็นตัวรับ LINE webhook แล้ว forward มา) → เก็บ `line_groups` เดียวกับ webhook · body ยืดหยุ่น (LINE raw `{events:[...]}` / `{groupId,groupName?}` / list) · คืน `{ok,count,groups}` |
| `/api/admin/update_release_date` | `update_release_date` | **admin (session) หรือเซลล์ (token/session + ownership)** POST: inline edit วันที่/สถานะ เขียนกลับชีตยอดขายตรงเซลล์ — body `{tab,row,col(2\|13\|14\|18\|19\|20\|21\|23),value,token?}` → `update_release_date()` PUT cell — **2=วันจอง · 13=N สถานะเคส (จอง/จอง(ซื้อสด)/รอเซ็นต์/รอผล/รอปล่อย/ปล่อย/รีเจ็ก · validate ตัด (ซื้อสด) แล้วต้องเป็น 1 ใน 6) · 14=เซ็น · 18=เอกสาร · 19/20=ผล · 21/23=ปล่อย**. เซลล์แก้ได้เฉพาะเคสตัวเอง (เช็คชื่อที่ marker ของแถว = `cell(r,0)`). ใช้จาก `saveReleaseDate`/`saveTimelineDate`/`saveCaseStatus` (index.html แอดมิน + seller.html เซลล์ · modal เคสจองมี dropdown สถานะ + แก้วันที่) |
| `/api/seller/update_note` | `update_lead_note` | เซลล์ (token) เขียนกลับ Google Sheet จาก lead detail — รับ `field` (S=`fill_sheet_note` / Z=`customer_status` / N=`call_proof`) + `value` (back-compat: `note`) → header-aware + ตรวจ ownership |
| `/api/seller/scan_doc` | `scan_doc` | **ต้อง login (any)** POST: รับรูปเอกสาร (base64, ≤8MB) + `form` (`finance`\|`loan`) → Gemini OCR (`gemini_ocr.extract_finance_fields`/`extract_loan_fields`) → คืน `{ok, fields}` ให้ฟอร์มกรอกอัตโนมัติ (ฉบับร่างให้เซลล์ตรวจก่อนส่ง) |
| `/api/seller/finance_check` | `finance_check_submit` | เซลล์ (token) POST: ส่งฟอร์ม "เช็คไฟแนนซ์ก่อนเซ็น" → สร้าง Flex (`build_finance_check_flex`) push เข้า `FINANCE_TEST_LINE_ID` (ช่วง test) + เก็บ Supabase `finance_checks` (best-effort) |
| `/api/seller/loan_submit` | `loan_submit` | เซลล์ (token) POST: ส่งฟอร์มขอสินเชื่อ → สร้าง Flex (`build_loan_flex`) push เข้า `FINANCE_TEST_LINE_ID` + เก็บ Supabase `loan_applications` (best-effort) |
| `/api/insights/seller` | `insights_seller` | **ต้อง login (any)** POST `{seller, stats}` → Gemini โค้ชเซลล์ (`gemini_insights.analyze_seller`) คืน `{ok, analysis}` (cache 30 นาที) |
| `/api/insights/forecast` | `insights_forecast` | **admin/exec** POST `{summary}` → Gemini อธิบายเทรนด์ยอด+ปัจจัยตลาด (`gemini_insights.forecast_narrative`) คืน `{ok, narrative}` |
| `/api/v1/` | `api_v1_index` | **API สาธารณะ (ต้องมีคีย์)** — สารบัญ endpoint + วิธี auth |
| `/api/v1/employees` | `api_v1_employees` | **API สาธารณะ** GET: รายชื่อพนักงาน — `userId`(LINE) · `displayName` · `nickname` · `position` · `groupId` · กรองได้ `?nickname=` `?user_id=` `?position=` `?q=` |
| `/api/v1/groups` | `api_v1_groups` | **API สาธารณะ** GET: กลุ่ม LINE — **รวม 2 ที่**: KVStore `line_groups` (บอทจำเอง มีชื่อกลุ่ม) + **คอลัมน์ group id ในชีตพนักงาน** (ใช้ได้ทันทีไม่ต้องรอบอท) · คืน `groupId`/`name`/`lastSeen`/`source`(bot\|sheet\|both)/`employeeCount` |
| `/api/cron/sync` | `cron_sync` | public (`?secret=xxx`) — sync sheets → Supabase `sheet_cache` + precompute dashboard (cron tick ตัวเดียวก็พอ · นี่เป็น endpoint แยกสำรอง) |
| `/api/cron/send_line` | `cron_send_line` | public (`?secret=xxx`) — ส่ง Flex แบบ one-shot, manual params |
| `/api/cron/tick` | `cron_tick` | public (`?secret=xxx`) — (1) sync mirror+precompute **ทุก ~3-4 นาที** (ผลเก่า >180วิ · ห้ามลดต่ำ — ดู "บทเรียน server ล่ม") (2) ส่งแจ้งเตือน **"ตามด่วน" รายเซลล์ ตามเวลาในชีต "ตั้งเวลาส่ง"** (default 09:00/13:00 · แก้เวลา/ผู้รับ/test ในหน้า "ตารางเวลา (Auto)") — cron อ่าน `load_schedules`+`schedule_matches_now` แล้วยิง `build_followup_messages` (3) เขียน heartbeat `cron_tick` + followup log `cron_followup` (Supabase kv) → หน้าสถานะระบบโชว์ "cron ทำงานล่าสุด" |

> **★ ส.ค.69 — บั๊ก "ข้อมูลค้างเป็นสัปดาห์" ที่แก้แล้ว (ต้องไม่ให้กลับมาอีก)**
> `cron_tick` เคยเช็ค `LINE_CHANNEL_ACCESS_TOKEN` แล้ว **`return 500` ก่อน** เขียน heartbeat และก่อนอุ่น dashboard
> → ไม่มี LINE token = **การรีเฟรชข้อมูลทั้งระบบตาย** ทั้งที่ 2 เรื่องนี้ไม่เกี่ยวกัน
> อาการ: แดชบอร์ดแช่ค้างเป็นสัปดาห์ · กดปุ่มรีเฟรชมือหายชั่วคราว (ปุ่มนั้นไม่เช็ค token) แล้วกลับมาค้างอีก
> · หน้าสถานะระบบขึ้น "cron ไม่ทำงาน" ทั้งที่ cron ยิงถึงจริง → **แยกไม่ออกว่าไม่ถูกยิง หรือถูกยิงแล้วตาย**
> โผล่ตอนขึ้นเดือนใหม่ (ตัวกรองเด้งไปเดือนที่ไม่เคยถูกคำนวณ → โชว์ 0)
> **กฎที่ต้องรักษา**: งานข้อมูล (heartbeat + อุ่น cache) ต้องทำ **ก่อน** และ **ไม่ผูก** กับ LINE/Playwright เสมอ
> · ของช้า (แคปรูป ~90 วิ) ต้องอยู่ท้ายสุด ไม่งั้น nginx ตัดที่ 120 วิ แล้วงานข้อมูลไม่ได้ทำ
> · `precompute_dashboard` เลิก `except: pass` แล้ว — เก็บผลไม่ได้จะบันทึกไว้ที่ kv `precompute_last`
> · heartbeat `cron_tick` เก็บ `{ok, refreshed, error, lineToken}` (เดิม `ok:True` เสมอ = เขียวหลอก)


### 🔑 API สำหรับระบบภายนอก (v1 · ส.ค.69 — เจ้าของขอ)
ให้ **n8n / เว็บโชว์รูม / partner** ดึงรายชื่อพนักงาน + LINE id + group id ได้โดยไม่ต้อง login เข้าเว็บ
- **อ่านอย่างเดียว (GET)** · `/api/v1/employees` · `/api/v1/groups` · `/api/v1/` (สารบัญ)
- **auth = คีย์**: header `X-API-Key: <คีย์>` หรือ `?key=<คีย์>` · เทียบด้วย `hmac.compare_digest` (กันเดาคีย์ทีละตัว)
- **env `EXTERNAL_API_KEY`** → `settings.EXTERNAL_API_KEYS` (**คั่น comma ได้หลายคีย์** = แจกคนละคีย์ต่อเจ้า → เพิกถอนทีละเจ้าโดยไม่กระทบคนอื่น)
- **★ ไม่ตั้งคีย์ = ปิดสนิท (503)** — ตั้งใจให้ "ปิดโดยปริยาย" เพราะ LINE user id + ชื่อพนักงาน = **ข้อมูลส่วนบุคคล (PDPA)** ใครถือ id ก็ทักหาพนักงานได้ตรง
- **ไม่คืน**: รูปโปรไฟล์ · reply token · เวลาเข้างาน/วันหยุด (มีในชีตแต่ไม่ได้ขอ + เกินจำเป็น)
- JSON ตอบเป็นภาษาไทยอ่านออก (`ensure_ascii=False`) · ไม่เปิด CORS (ตั้งใจ — ให้เรียกแบบ server-to-server ถ้าต้องเรียกจากเบราว์เซอร์ค่อยเพิ่มทีหลัง)
- **★ `/api/v1/groups` รวม 2 แหล่ง (ส.ค.69 · เจ้าของแจ้งว่า "group id ยังไม่ออกมา")**: เดิมอ่านจาก KVStore `line_groups` อย่างเดียว ซึ่ง **ว่างจนกว่าบอทจะได้ event จากกลุ่มจริง** (ต้องตั้ง Webhook URL + มีคนพิมพ์ในกลุ่ม) → บนโปรดักชันเลยคืน 0 กลุ่ม · เพิ่มการอ่าน **group id จากชีตพนักงาน** (คอลัมน์ D `EMPLOYEE_COL.group_id`) มา merge → ใช้ได้ทันที · `source` บอกที่มา · `employeeCount` = มีพนักงานผูกกับกลุ่มนั้นกี่คน
- **⚠️ ข้อมูลในชีตยังไม่ครบ (วัด ส.ค.69)**: พนักงาน 48 คน **มี group id แค่ 36 คน · ขาด 12 คน** (ส่วนใหญ่เด็กฝึกงาน/พนักงานใหม่) — เป็นช่องว่างใน**ชีต** ไม่ใช่บั๊กโค้ด · ชีตมี group id แค่ **2 ค่า** (ต่างกันตัวท้าย `…ded1` 35 คน · `…ded2` 1 คน)
- **⚠️ ยังไม่มี rate limit / log การเรียก** — ถ้าเปิดให้ partner ภายนอกจริงควรเพิ่ม

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

#### 👥 ทีมมีที่เก็บที่เดียว: ทะเบียนพนักงาน (★★ 24 ก.ย.69 · เจ้าของสั่ง)
*"เรื่องของชื่อเล่นและชื่อทีม ฉันอยากให้ลิงก์กันให้หมดเลย … แค่มาเพิ่มทีมในนี้ก็สามารถโผล่ที่อื่นได้ด้วย"*

เดิมทีมของคนคนเดียวถูกเก็บ **2 ที่ที่ไม่รู้จักกัน** → ย้ายทีมทีต้องแก้ 2 รอบ:
`cfg_sellers_config` (แดชบอร์ดขาย — เป้า/คะแนน/ตารางรายทีม) · `Employee.position` (ตารางเช็คชื่อ)

- **`constants.apply_registry_teams()`** — เรียกท้าย `refresh_from_sheet()` ทุกครั้ง:
  **อ่านทีมจากทะเบียนทับ** → แก้ที่หน้า "พนักงาน" ที่เดียว แดชบอร์ดขายตามรอบ sync ถัดไป
- **`team_id_of(position)`** — `"ทีม B"` → `"B"` · `"ADMIN"`/`"เทเลเซลล์"` → `"ADMIN"`
  - **⚠★ รับเฉพาะ "ทีม + รหัสสั้น (A-Z/0-9 ไม่เกิน 2 ตัว)"** — ขึ้นต้นด้วยคำว่า "ทีม" อย่างเดียวไม่พอ
    เวอร์ชันแรกเขียนหลวมๆ → วัดกับข้อมูล prod แล้วพบว่า **แซน** (ทีมขาย B · ทะเบียน "ทีมโปรดักชัน")
    จะโดนย้ายไปทีมขายใหม่ชื่อ "โปรดักชัน" โดยไม่มีใครสั่ง
- **ตำแหน่งที่ไม่ใช่ทีมขาย = ไม่ย้ายใคร** (ช่าง/ออฟฟิศ/เด็กฝึกงาน) — ของเดิมในตั้งค่าเซลล์ชนะ
  · **เฉพาะคนที่เป็นเซลล์อยู่แล้ว** (มีใน `TARGETS`) — พนักงานทั่วไปไม่ถูกดึงเข้าแดชบอร์ดขาย
  · **ทีมใหม่สร้างจากทะเบียนได้** ("ทีม D" → `D`) · เติมชื่อให้ `TEAM_NAMES` เอง
  · ทะเบียนอ่านไม่ได้/ยังไม่ migrate = ไม่ทำอะไร (คงทีมจากตั้งค่าเซลล์)
- **`admin_seller_config` POST เขียนทีมกลับเข้าทะเบียนด้วย** (`syncedToStaff` ใน response) —
  ถ้าไม่เขียนกลับ ทีมที่เพิ่งแก้ในหน้า "ตั้งเป้า/ทีม" จะโดนทะเบียนทับกลับรอบ sync ถัดไป
  = ดูเหมือน "บันทึกไม่ติด"
- **ตารางเช็คชื่อไม่เพิ่มคอลัมน์จากงานนี้** — เจ้าของสั่งล็อกหน้าตาตารางไว้ 5 คอลัมน์

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
    - **★ บั๊กที่แก้ 16 ก.ย.69**: ตัวเขียนไม่ได้แกะห่อ → ทุกรอบส่งซ้อน `{"data":{"data":…}}` ลึกขึ้นเรื่อยๆ (บนเซิร์ฟเวอร์ ~9 KB) และตัวอ่านเห็นแค่ชั้นนอก = % โดนทวงผิด · ตอนนี้ทั้งอ่านและเขียนผ่าน **`_flat_rounds()`** ([fetch_dashboard.py](dashboard/services/fetch_dashboard.py)) ที่ไล่เก็บวันที่จากทุกชั้น (ซ่อมข้อมูลเก่าเองตอนเขียนรอบถัดไป)
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
  - **⚠️★ 16 ก.ย.69**: `_cleanup_old` เดิมกวาดแต่ `report_*.png` **ลืม `card_*.png`** (รูปการ์ดที่แคปวันละหลายใบตั้งแต่ ก.ค.69) → ค้างบนดิสก์ VPS **5,575 ไฟล์ = 1.3 GB** (เก่ากว่า 7 วัน 933 MB) · แก้ให้กวาดทั้ง 2 แบบ + คืนจำนวนไฟล์ที่ลบ · **ลบของเก่าที่ค้างอยู่ด้วยมือครั้งเดียว** (`find /opt/oxlet/media/reports -name '*.png' -mtime +7 -delete`)
- **deploy บน VPS ต้องลง Chromium**: `pip install playwright` + **`playwright install chromium --with-deps`** (lib ระบบ + ฟอนต์ไทย `fonts-thai-tlwg` · Chromium launch ใช้ `--no-sandbox`) · set `PLAYWRIGHT_BROWSERS_PATH` ให้ user `oxlet` เจอ browser · ไม่ลง = แคปไม่ได้ (คืน None ไม่พังระบบ)
  - **⚠️ อัปเกรด playwright แล้วต้องลง Chromium ใหม่ทุกครั้ง (ส.ค.69 · เคยทำรายงานรายวันหยุดส่ง)**: `requirements.txt` เขียน `playwright>=1.40` **ไม่ล็อกเวอร์ชัน** → `pip install -r requirements.txt` ตอน deploy อาจอัปเกรดแพ็กเกจเงียบๆ · Playwright **แต่ละเวอร์ชันผูกเลข build ของ Chromium คนละตัว** (`chromium_headless_shell-<build>`) พอไม่ตรงกัน = `Executable doesn't exist` → "แคปรูปไม่สำเร็จ" ทั้งที่เมื่อวานยังส่งได้ · แก้: รัน `playwright install chromium --with-deps` ซ้ำหลัง pip upgrade (ดู [deploy/DEPLOY.md](deploy/DEPLOY.md))
  - **⚠️★ regression ที่เคยทำรายงาน/การ์ดหยุดส่ง 2-3 วัน (ส.ค.69) — เมนูสามขีดทับปุ่มแท็บ**: การ์ดที่จะแคปอยู่ **คนละแท็บกับหน้าแรก** (`#rpt-shot`/`#rpt-shot-teams`/`leadreport-card`… อยู่แท็บ LEAD · `fin-card` อยู่แท็บสถานะจองปล่อย) · โค้ดแคปเดิมเปิดแท็บด้วย `page.click("button.ntab:has-text('...')")` → พอย้ายแท็บเข้า **drawer ที่ปิดอยู่** (`transform:translateX(-104%)` = อยู่นอกจอ) Playwright กดไม่โดน → แท็บไม่เปลี่ยน → ไม่มีการ์ดให้แคป → **หยุดส่งเงียบๆ ไม่มีใครรู้**
    - แก้ด้วย helper **`_goto_tab(page, ชื่อแท็บ)`** — เรียก **`switchTab(<id>)` ตรง** (map ชื่อ→id ที่ `_TAB_ID`) + คง click เป็น fallback · **ใช้ทั้ง 3 ทางแคป**: `capture_report_images` · `capture_card` · `capture_leadsummary` (ตัวหลังเดิม **ไม่สลับแท็บเลย** ทั้งที่การ์ดอยู่แท็บ LEAD)
    - **กฎ: อย่าให้ Playwright คลิกปุ่มที่งาน UI อาจย้าย/ซ่อนได้ — เรียกฟังก์ชัน JS ตรงเสมอ** · เพิ่มแท็บใหม่ต้องเพิ่มใน `_TAB_ID` ให้ตรงกับรายการแท็บใน [index.html](dashboard/templates/dashboard/index.html)
  - **★ งบเวลารวม (`REPORT_SHOT_BUDGET_SEC` default 90s)**: ผลรวม timeout ทุกขั้นเดิม ~186s แต่ **nginx ตัดที่ 120s** (`proxy_read_timeout` ของ `location /`) → ตอนพังจริงคำขอโดนตัดก่อน ผู้ใช้เห็นแค่ "หมุนค้าง" ไม่เคยได้ข้อความบอกสาเหตุ · ตอนนี้ `left_ms()` หดเวลารอทุกขั้นให้จบใน 90s เสมอ
  - **★ ข้อความ error บอกสาเหตุจริงแล้ว (ส.ค.69)**: เดิม `capture_*` กลืน exception ทุกจุด (`except: pass`) แล้วผู้เรียกเดาว่า "เช็ค playwright/chromium" ซึ่งมักไม่ใช่สาเหตุ (อาจเป็น login ไม่ผ่าน/ตารางไม่ render/ชีตพัง) → แอดมินไล่ผิดทาง · เพิ่ม **`diagnose()`** (ลองเปิด Chromium จริง + โชว์ `PLAYWRIGHT_BROWSERS_PATH`) + **`last_error()`** (เก็บ error จากขั้นตอนแคป) + **`_capture_fail_msg()`** ที่ทั้ง 3 จุดส่งข้อความให้ผู้ใช้ — แยกออกว่า "เบราว์เซอร์ไม่พร้อม" หรือ "เบราว์เซอร์โอเคแต่หน้าเว็บมีปัญหา"
- **แคป `#rpt-shot` (เวอร์ชันสไตล์อ่านง่าย · ไม่ใช่ตารางเว็บดิบ)**: ตารางเว็บ `#rpt-card` อัด 11 คอลัมน์แน่น อ่านยากบนมือถือ → ทำ **`#rpt-shot`** ใน `renderOverview` (reuse `_rpt`+`_RC` เดียวกัน = **ครบทุกคอลัมน์ ตัวเลขตรงกับตารางเต็ม**) แต่สไตล์ใหม่: **แถวโค้ง · badge สีทีม · ตัวใหญ่ขึ้น · เว้นระยะ · สี light คงที่** (ไม่อิงธีมเว็บ). **ซ่อนบนเว็บ** ด้วย wrapper `#rpt-shot-wrap` (`height:0;overflow:hidden`) → capture `page.evaluate` เปิดให้เห็น (`height:auto`) ก่อน screenshot · **#rpt-shot ต้องกำหนด `width` เอง (1560px)** (ไม่งั้น block เต็มความกว้าง → รูปมีที่ว่างขวา) · fallback `#rpt-card` ถ้าไม่มี · **แก้คอลัมน์ = แก้ที่ `#rpt-shot` ใน index.html (reuse `_RC` อยู่แล้ว)**
- **★ ตาราง "โปรไฟล์ลูกค้าที่ปิดการขายได้" (ส.ค.69 · เจ้าของขอ · การ์ด `#custprofile-card` ถัดจาก `#fin-card` ในแท็บ "สถานะจองปล่อย")** — ตอบว่า "คนที่ซื้อรถเราเป็นใคร"
  - ที่มา: 5 ช่องที่แอดมินแทรกในชีตรายงานฝ่ายขายตั้งแต่ เม.ย.69 (อาชีพ/รายได้/อายุงาน/ประวัติผ่อน/อายุ) → เก็บที่ canonical 23-27 ตอน normalize → ส่งออกใน `bookingCases[]` เป็น `occupation/income/jobTenure/payHistory/age`
  - นับเฉพาะเคสสถานะ **"ปล่อย"** ตามช่วงวันที่ของหน้า · แบ่ง 3 ตาราง: **อาชีพ** (top 8) · **รายได้ต่อเดือน** (5 ช่วง) · **อายุ** (5 ช่วง) + โชว์ **รายได้กลาง (median)**
  - **⚠️ % คิดจากเฉพาะเคสที่กรอกช่องนั้น ไม่ใช่เคสปล่อยทั้งหมด** — หัวการ์ดเขียน "ปิดการขาย X เคส · มีโปรไฟล์ Y เคส" กำกับเสมอ (วัดจริง ส.ค.69: ปล่อย 375 · มีโปรไฟล์ 117 = ~31%) ไม่งั้นคนอ่านเข้าใจผิดว่าเป็นสัดส่วนลูกค้าทั้งหมด
  - รายได้/อายุเป็น**ข้อความอิสระ** (เช่น "20,000" "1 ปี 6 เดือน") → แปลงเป็นตัวเลขแล้วจัดช่วง · แปลงไม่ได้ = ไม่นับ
  - **⚠️ บทเรียนตอนทำ**: บล็อกการ์ดไฟแนนซ์ห่อด้วย `try { } catch` ที่ **กลืน error เงียบ** → ตอนแรกผมเรียก `bookingsInRange()` ซึ่งไม่มีในขอบเขตของ `renderBookings` → **การ์ดหายทั้ง 2 ใบพร้อมกัน** (ไฟแนนซ์ด้วย) โดยไม่มี error โผล่ · ในนั้นให้ใช้ตัวแปร **`base`** (เคสในช่วงวันที่ของ `renderBookings`)
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
- **★ ก.ย.69 — เซลล์ในทีมต้องไม่หายจากตารางตอนต้นเดือน**: เดิมกรอง `_sval(s,'lead') > 0` อย่างเดียว → วันที่ 1 ของเดือนที่ยังไม่มีลีดเข้า **เซลล์ที่ยังทำงานอยู่หายจากตารางทั้งแถว** (เจ้าของแจ้งว่า "บิว/มัท หาย" — จริงๆ ข้อมูลเดือนก่อนอยู่ครบ แค่ยังไม่มียอดเดือนใหม่) · ตอนนี้ **`s.inactive !== true` = โชว์เสมอ** (เซลล์เก่า/ลาออกยังกรองด้วยกิจกรรมเหมือนเดิม) · `rangeActiveSellers()` ก็เพิ่มเซลล์ในทีมเข้า set ด้วยเหตุผลเดียวกัน
- **🎨 โฟกัสเซลล์ (sellerFlags)**: dropdown สี ⚪/🟡/🔴 ต่อเซลล์ → ระบายทั้งแถว (`_FLAGS=D.sellerFlags`, `_flagBg`, `_setSellerFlag` optimistic) · เก็บชีต **"โฟกัสเซลล์"** (`SHEET_CONFIG["seller_flags"]` · cols เซลล์|สี) ผ่าน `/api/admin/seller_flags`
- **📋 ONHAND (รถในมือรายสัปดาห์ · กรอกมือ)**: คอลัมน์ ONHAND ในตาราง · แอดมินกรอกยอดรถในมือต่อเซลล์ราย **สัปดาห์ (ตัดรอบทุกวันพฤหัส · week-of-month)** ผ่านฟอร์ม (`openOnhandForm`/`saveOnhand`) → เก็บชีต **"ONHAND รายสัปดาห์"** (`SHEET_CONFIG["onhand_config"]`) ผ่าน `/api/admin/onhand_config` (`_onhand_now`/`_onhand_key(ym,wk)` ใน [views.py](dashboard/views.py)) · ดู/แก้สัปดาห์ย้อนหลัง + เดลต้าเทียบสัปดาห์ก่อนได้

**★ ตาราง "Lead → จอง → จบ (แยกช่องทาง)" (ส.ค.69 · การ์ด `#leadconv-card` แท็บ LEAD)** — ช่องทางไหนได้ลีดเยอะ ปิดจองกี่ % จบจริงกี่ % · คอลัมน์: ช่องทาง | Lead | จอง | จบ | จอง/Lead | จบ/จอง | จบ/Lead · นับตามช่วงวันที่ (Lead=วันรับลีด · จอง=วันจอง · จบ=วันปล่อย)
- **⚠️ ชื่อช่องทาง 2 ฝั่งไม่ตรงกัน**: ฝั่งลีดเป็น dropdown (26 ค่าสะอาด) แต่**ฝั่งจองพิมพ์มือ 198 แบบ ตรงกันเป๊ะแค่ 8** (`Line@`/`line@`/`LINE@`/`": line@"` · `Live tiktok ช่องขายบอส`/`Tiktok ช่องขายบอส`/`ไลฟ์ TT ช่องขายบอส`) → นับตรงๆ ไม่ได้
- **วิธีเทียบ (`_attach_clean_channel` ใน [fetch_dashboard.py](dashboard/services/fetch_dashboard.py))**: (1) ใช้ **รหัสลีด** หาช่องทางจากชีตลีดก่อน (แม่นสุด · ครอบคลุม ~55%) → (2) ไม่มีก็ **ล้างชื่อ** (`_norm_channel` ตัดตัวพิมพ์/ช่องว่าง/`":"` นำหน้า + รวม live tiktok↔tiktok) แล้วเทียบกับชื่อฝั่งลีด → **รวมครอบคลุม 94-95%** · เก็บผลใน `bookingCases[].channelClean` (`''` = จับไม่ได้ → แถว "ไม่ระบุ")
- **★ ยอด Lead ในตารางนี้น้อยกว่า "ลีดรวม" ของแดชบอร์ด — ตั้งใจ ไม่ใช่บั๊ก** (วัดจริง ส.ค.69: ชีต 22,275 แถว → เข้าตาราง 14,790): ตัด **RJ/RB 6,857** (ไม่ใช่ลีดขายรถ) + **รหัสลีดซ้ำ 626** (นับครั้งเดียว) · **ลีดที่ไม่ได้กรอกช่องทางมีแค่ 2 แถว** (เดิม `continue` ทิ้ง → ตอนนี้เก็บใน `leadNoChannelByMonth` แล้วลงแถว "ไม่ระบุ") · เขียนอธิบายไว้ใน tooltip ของการ์ดแล้ว
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

### 🗂️ สารบัญฐานข้อมูล (เมนู "ฐานข้อมูล" · ก.ย.69 — เจ้าของขอ)
ตอบคำถาม **"ตอนนี้ระบบเก็บอะไรไว้บ้าง"** ในหน้าเดียว — เป็นคำถามแรกที่ต้องตอบได้เวลาคุยเรื่อง PDPA / จะลบข้อมูลทิ้ง
- **[db_inventory.py](dashboard/services/db_inventory.py)** `inventory()` — เดินตาม `apps.get_models()` เอง
  (**เพิ่มโมเดลใหม่ = โผล่อัตโนมัติ ไม่ต้องมาไล่เพิ่มลิสต์**) + นับแถว + เทียบกับตารางจริงใน DB
  (`connection.introspection`) → ตารางที่ยังไม่ migrate ติดป้าย "ยังไม่ migrate" · อ่านไม่ได้ติดป้าย "อ่านไม่ได้"
  - `TABLES` = คำอธิบายรายตาราง (ชื่อไทย · เก็บอะไร · `pii` · นโยบายเก็บ) — **เพิ่มตารางใหม่ควรเติมคำอธิบายที่นี่**
    (ไม่เติมก็ไม่พัง แค่โชว์ชื่อโมเดลดิบ)
  - `KV_LABEL` = อธิบายคีย์ใน **`dash_kv`** ซึ่งเป็น "ที่เก็บของรวม" — ชื่อตารางไม่บอกอะไรเลย จึงลิสต์คีย์ข้างในให้ดู
    พร้อมขนาด KB (เห็นทันทีว่า `main` คือก้อนใหญ่สุด)
  - `SHEET_NOTE` = **ข้อมูลการขายไม่ได้อยู่ในฐานข้อมูลนี้** (อยู่ใน Google Sheets) — ขึ้นเป็นกล่องเตือนสีเหลือง
    **ห้ามเอาออก** ไม่งั้นคนอ่านเข้าใจผิดว่า "ระบบเก็บแค่นี้"
- **นับแถว + อธิบาย เท่านั้น ไม่ดึงเนื้อข้อมูลออกมาโชว์** (หน้านี้ตอบ "มีอะไร" ไม่ใช่ "ข้อมูลใครบ้าง")
- **สิทธิ์ = `_is_boss(request)`** ([views.py](dashboard/views.py)) — **แอดมินสูงสุด + ผู้บริหาร เท่านั้น**
  ผ่านได้ 4 ทาง: `SUPER_ADMIN_IDS` · แอดมินระบบ break-glass (`user_id=="admin"`) · Django superuser · บทบาท `Executive`
  - **ทำไมไม่ใช้ `_is_admin`**: `position=="admin"` ครอบถึง **เซลล์ที่ติ๊กแอดมิน** + **แอดมินไอดี (เทเลเซลล์/ออฟฟิศ)** ด้วย → กว้างเกิน
  - **⚠️ ข้อ 3-4 ใช้ไม่ได้บน `/dashboard/`** เพราะ `TrackSessionBridgeMiddleware` bridge เฉพาะ path `/track/`
    → `request.user` เป็น anonymous ที่นี่ · **ข้อ 1-2 (session ฝั่งขาย) จึงเป็นทางหลัก**
  - **บล็อก 2 ชั้น**: frontend ซ่อนเมนู (`IS_BOSS` จาก context `is_boss` + `boss:true` ใน `ADMIN_MENU`)
    **และ** endpoint เช็คเอง (403) — ปิดแค่ UI ไม่พอ ยิง API ตรงได้
- **★ 16 ก.ย.69 — ยุบพาเนลสารบัญเดิมทิ้ง (เจ้าของสั่ง "ตัวเก่าก็ตัดทิ้งได้เลย")**
  `openDbPanel`/`renderDbPanel`/`_dbSearch`/`dbExportTable` **ลบออกแล้ว** (~9.9 KB) ·
  เมนูเหลือรายการเดียว **"ฐานข้อมูล (SQL)"** → `openSqlPanel()` (ดู section "ดูข้อมูลดิบ (SQL)")
  - **`inventory()` ยังใช้อยู่** — หน้า SQL เรียก `/api/admin/db_tables` มาเติม **จำนวนแถว + ป้าย PDPA**
    ในแถบตารางทางซ้าย (โหลดคู่กับ schema · ล้มก็ไม่พัง แค่ไม่มีตัวเลขโชว์) → **`TABLES`/`KV_LABEL`
    ยังต้องดูแลต่อ** เวลาเพิ่มตารางใหม่
  - **กล่องเตือน `SHEET_NOTE` ยกไปไว้หัวหน้า SQL แล้ว** — กฎเดิม "ห้ามเอาออก" ยังมีผล
  - **ลิงก์เก่า `?panel=db` ชี้มาหน้าใหม่** (`_PANEL_URL.db = openSqlPanel`) — ที่เคยแจกไว้จะได้ไม่ตาย
  - ที่หายไปจริงๆ คือ **รายการคีย์ใน `dash_kv`** ที่เคยลิสต์ให้ดู → ตอนนี้ดูด้วยคำสั่งแทน:
    `SELECT key, length(data::text) FROM dash_kv ORDER BY 2 DESC`
  _(ก.ย.69 เคยย้ายจากหมวด "ตรวจสอบ & Log" — เจ้าของหาไม่เจอ เพราะชื่อหมวดไม่ได้บอกว่ามีข้อมูลลูกค้า)_
- **ไอคอน `database` ต้องมีใน dict `LUCIDE`** ([index.html](dashboard/templates/dashboard/index.html)) — dict นี้ hardcode ไม่ได้โหลดจาก CDN

### ⬇ ดาวน์โหลดข้อมูล (export) — [db_export.py](dashboard/services/db_export.py) · ก.ย.69 (เจ้าของขอ)
คู่กับสารบัญด้านบน: สารบัญตอบ **"เก็บอะไรไว้"** · ตัวนี้ตอบ **"เอาออกมาได้"** (เนื้อข้อมูลจริงเป็นไฟล์ในมือเจ้าของ
— เปิด Excel · ส่งต่อ · เก็บสำรอง · ย้ายระบบ)
- **เดินตาม `apps.get_models()` เหมือน db_inventory → เพิ่มโมเดลใหม่ = ดึงได้เองทันที** ไม่ต้องมาไล่เพิ่มลิสต์
  (ลิสต์ที่ต้องดูแลมือ = วันหนึ่งจะลืม แล้วข้อมูลบางส่วนออกไม่ได้แบบไม่มีใครรู้)
- **CSV ใส่ BOM** (Excel ไทยไม่เพี้ยน) · หัวคอลัมน์ = `ชื่อไทย (ชื่อฟิลด์จริง)` · เวลาโซนไทย · JSON เป็นไทยอ่านออก
  · ตั้งชื่อไฟล์ด้วย `_attachment()` **ตัวเดียวกับ export ไทม์ไลน์รถ** (RFC 5987 — ชื่อไทยไม่กลายเป็นขยะ)
- **3 ทาง**: ปุ่ม **⬇ ทั้งหมด (.zip)** หัวหน้า **ฐานข้อมูล (SQL)** · **ดาวน์โหลดผลของคำสั่ง** ในหน้าเดียวกัน
  (กดชื่อตาราง = ได้ทั้งตาราง · ใส่เงื่อนไข/ช่วงวันที่ = ได้เฉพาะที่กรอง — **แทนปุ่ม ⬇ รายตารางเดิมที่ลบไปแล้ว**) · และ
  **`manage.py db_export [--list] [--table X] [--all] [--out ไฟล์|โฟลเดอร์/]`** (ทาง SSH — เอาไปตั้ง cron สำรองรายวันได้)
  - endpoint `/api/admin/db_export?table=` **ยังอยู่** (คำสั่ง CLI + ปุ่ม .zip ใช้อยู่) แค่ไม่มีปุ่มรายตารางในหน้าเว็บแล้ว
- **★ กติกา PDPA ที่ยึด**: **LINE user id ของพนักงาน = ปิดเป็น `Uxxxxx…(พนักงาน)`** (ใครถือ id ก็ทักหาพนักงานได้ตรง)
  · **ของลูกค้า = ไม่ปิด** (เจ้าของขอไว้ทักกลับ + ไฟล์นี้ดาวน์โหลดได้เฉพาะ `_is_boss`) · **id ที่ระบบยังไม่รู้ว่าใคร = ปิดไว้ก่อน**
  · รายชื่อพนักงานมาจาก **`LineProfile.is_employee` + ชีตพนักงาน** (ถ้าอ่านแต่ LineProfile จะพลาดคนที่ยังไม่เคยพิมพ์ผ่านบอท)
  · **ไม่ออกเลย**: แฮชรหัสผ่าน (`auth_user.password`) · เนื้อ session (`ALWAYS_DROP`)
  - **⚠️ ห้ามใส่ `\b` หน้า `U` ใน regex จับ LINE id** — ชื่อบัญชี Django ของคนที่ login ผ่าน LINE คือ `line_<userId>`
    ซึ่ง `_` เป็นอักขระคำ → ไม่มีขอบเขตคำ → **id พนักงานหลุดออกทาง `auth_user.username`** (เจอตอนทดสอบ · มี test กันไว้แล้ว)
- `dash_kv.data` **ตัดสั้นที่ 4,000 ตัวอักษร** — คีย์ `main` เป็นแคชผลสรุปแดชบอร์ด ~2.5 MB ที่คำนวณใหม่ได้
  ไม่ใช่ข้อมูลต้นฉบับ (ถ้าไม่ตัด ไฟล์จะบวมด้วยของที่ไม่มีใครเอาไปใช้)
- **ตารางไหนอ่านไม่ได้ = ข้ามแล้วจดใน `อ่านก่อน.txt` ไม่ล้มทั้งไฟล์** (export ที่ล้มเพราะตารางเดียวพัง = เจ้าของไม่ได้อะไรเลย)
  · `อ่านก่อน.txt` ยังเตือนว่า **ข้อมูลการขายอยู่ใน Google Sheets ไม่ได้อยู่ในไฟล์นี้** และรูป/วิดีโออยู่ใน Drive
- **⚠️★ บั๊กที่เจอตอนทำ (แก้แล้ว) — "ข้างใน dash_kv" ในพาเนลว่างเปล่ามาตลอด**: `_kv_keys()` เขียน
  `.only("key", "value", ...)` แต่ฟิลด์จริงชื่อ **`data`** → `FieldError` โดน `except` กลืน → คืน `[]` เสมอ
  ทั้งที่มี 15 คีย์ (ตารางนี้เลยไม่เคยโผล่ให้ใครเห็น) · **บทเรียนเดิมย้ำอีกครั้ง: `except` ที่ครอบทั้งฟังก์ชัน
  ทำให้ "ไม่มีข้อมูล" กับ "โค้ดพัง" หน้าตาเหมือนกัน**

### 👤 ทะเบียนพนักงาน — ย้ายออกจากชีตมาเป็นของระบบ (16 ก.ย.69 · เจ้าของสั่ง)
*"เราจะให้เขาแก้ในระบบ SaleForce ของเรา ถ้ามีคนเพิ่มเข้ามา"* + *"คัดลอกตำแหน่ง เวลาเข้างานมาด้วย แมทจาก display name เอา"*

- **ทำไมต้องย้าย**: ทั้งระบบเคยจับคู่คนด้วย **LINE user id ในชีต** ซึ่งเป็น id ของ **บอทเดิม** ·
  พอกลุ่มเปลี่ยนมาใช้บอทใหม่ (คนละ provider) id ที่วิ่งเข้ามาเป็นคนละชุด → **จับคู่ไม่ได้เลยสักคน**
  (วัดจริง 16/09: บอทเดิมได้ยิน 48 คน จับคู่ชีตได้ 46 · บอทใหม่ได้ยิน 45 คน จับคู่ได้ **0** · id ซ้อนกัน 0 ตัว)
- **โครงใหม่**: **`checkout.Employee`** = "ตัวคน" (ชื่อเล่น · ชื่อที่ตั้งใน LINE · ตำแหน่ง · **เวลาเข้างาน** ·
  วันหยุด · group id · ใช้งานอยู่ไหม) + **`LineProfile.employee`** (FK) = **1 คนผูก LINE id กี่บัญชีก็ได้**
  (migration **0013**) → บอทเดิม 1 ตัว บอทใหม่ 1 ตัว ก็ยังเป็นคนเดียวกัน
- **`python manage.py import_employees [--apply] [--out ไฟล์]`**
  ([import_employees.py](checkout/management/commands/import_employees.py)) — ย้ายครั้งแรก:
  อ่านชีต → สร้าง/อัปเดต `Employee` → ผูก LINE id **2 ทาง**: id ที่ตรงกับชีต (บอทเดิม) +
  **ชื่อโปรไฟล์ LINE ตรงกัน** (บอทใหม่ — ชีตไม่มี id ชุดนี้) · **ชื่อซ้ำหลายคน = ไม่ผูก (ไม่เดา)** ·
  แก้ชื่อผู้ส่งในข้อความเก่าให้เป็นชื่อเล่นด้วย · รันซ้ำได้ ไม่สร้างซ้ำ
- **`people._load()` อ่านฐานข้อมูลก่อน แล้วค่อยเติมจากชีต** (DB ชนะ) → **แก้/เพิ่มคนในระบบเราได้เลย
  ไม่ต้องกลับไปแก้ชีต** · ชีตอ่านไม่ได้ก็ยังทำงานจากทะเบียนในระบบ
- **หน้าจัดการ**: เมนูสามขีด → **ทีม & สิทธิ์ → พนักงาน (ตำแหน่ง/เวลาเข้างาน)**
  · **ลิงก์ตรง `/dashboard/?panel=employees`** (พาเนลเป็น modal ไม่มี URL ของตัวเอง → `_PANEL_URL` ที่ท้าย index.html แปลง `?panel=` เป็นการเรียกฟังก์ชัน · รองรับ `customers`/`db` ด้วย)
  (`openEmployees()`/`renderEmployees()` ใน [index.html](dashboard/templates/dashboard/index.html)) —
  ตารางแก้ในช่องได้เลย + เพิ่มคนใหม่ + ปิดใช้งาน/ลบ
- **★ `/api/v1/employees` ตอบจากฐานข้อมูลแล้ว** (n8n เอาไปใช้แทนโหนดชีตได้): เพิ่ม **`userIds`**
  (ทุกบัญชีของคนนั้น) · **`workStart`** · `dayOff` · `source` บอกว่าตอบจาก `db` หรือ `sheet` ·
  ยังไม่ได้ย้าย (ตารางว่าง) หรือ `?source=sheet` = อ่านชีตแบบเดิม · **ต้องมี `EXTERNAL_API_KEY`** (ตั้งแล้วบน prod)
- **ผลย้ายจริง 16/09**: ชีต 48 คน → ผูก LINE **92 บัญชี** (จาก id ในชีต 47 · จากชื่อโปรไฟล์ 45) ·
  43 คนมีครบ 2 บัญชี (บอทเดิม+บอทใหม่) · เหลือคนในกลุ่มที่ยังจับคู่ไม่ได้ **2 คน** (ชื่อ LINE ไม่ตรงชีต)
- **`_norm()` ทำ NFKC ก่อนตัดอักขระ** — ชื่อ LINE แฟนซี (`𝑃` `𝗠𝗮𝗶` `Ｍａｉ`) เดิมโดนตัดจนเหลือสตริงว่าง
  เทียบกับชีตไม่ได้เลย · NFKC แปลงกลับเป็นตัวอักษรปกติก่อน
- **★★ คนใหม่เข้ากลุ่ม = ระบบเพิ่มชื่อเข้าทะเบียนให้เอง (16 ก.ย.69 · เจ้าของขอ)**
  *"เมื่อมีคนใหม่เข้ากลุ่ม มันจะได้เพิ่มรายชื่อเอง คนแค่ต้องมาตามใส่ชื่อเล่นกับเวลาเข้างานแล้วก็วันหยุด"*
  - **เดิมไม่เพิ่มให้** — คนใหม่ที่พิมพ์ในกลุ่มถูกสร้างเป็น `LineProfile` เท่านั้น **และถูกนับเป็นลูกค้า**
    (`is_employee=False`) · ต้องมีคนไปเพิ่มในทะเบียนเองถึงจะเข้าระบบเช็คชื่อ
  - **`people._employee_for()`** (เรียกจาก `touch_profile`) — เจอ userId/ชื่อในทะเบียนแล้ว = ผูกเข้าแถวเดิม ·
    ไม่เจอ **และเป็นข้อความจากกลุ่ม** = **สร้าง `Employee` ใหม่ด้วยชื่อจาก LINE** (`source=auto`)
    แล้วผูก `LineProfile.employee` + ตั้ง `is_employee=True` ให้ทันที
  - แถวที่สร้างให้มีแต่ชื่อ → ไปโผล่เองในกลุ่ม **"ยังไม่ได้ตั้งเวลาเข้างาน"** ของพาเนลเช็คชื่อ
    และติดป้าย **"ใหม่"** + แถบสรุปในหน้าพนักงาน = **กลายเป็นรายการงานให้คนมาเติม**
    (ตำแหน่ง / เวลาเข้างาน / วันหยุด) แทนที่จะต้องคอยสังเกตเองว่ามีใครเข้ามาใหม่
  - **⚠️ เฉพาะข้อความจากกลุ่มเท่านั้น** — แชท 1:1 คือลูกค้าทักเข้า OA ถ้าเอามาสร้างด้วย
    **ทะเบียนพนักงานจะเต็มไปด้วยลูกค้าภายในไม่กี่วัน** (มีเทสต์กันไว้แล้ว)
  - **ชื่อซ้ำ = ผูกเข้าแถวเดิม ไม่สร้างซ้ำ** — บอท 2 ตัวให้ userId คนละชุดกับคนเดียวกัน
    ถ้าไม่เช็คชื่อก่อนจะได้พนักงานซ้ำคนละแถวทุกคน
  - **สวิตช์ `checkout_line_config["auto_employee"]` · เปิดโดยปริยาย** ·
    ปิดได้ด้วย `manage.py checkout_config --auto-employee off` (เผื่อวันหนึ่งมีกลุ่มที่ลูกค้าปนอยู่)
- **★ ช่อง "เช็คชื่อ" — ผู้บริหารไม่ต้องเช็คชื่อเข้างาน (16 ก.ย.69 · เจ้าของแจ้ง)**
  *"คนที่ไม่มีชื่อเล่นหรืออะไรเลย จะนับว่าเป็นผู้บริหาร ซึ่งเราจะไม่ใช้เก็บข้อมูลกัน"*
  - **`Employee.track_checkin`** (migration **0015** · default `True`) — ติ๊กออกในหน้า "พนักงาน" แล้วคนนั้น
    **หายจากพาเนลเช็คชื่อทั้งหมด**: ไม่นับในยอด "ต้องมาวันนี้" · ไม่ขึ้น "ยังไม่เช็คชื่อ" ·
    ไม่ขึ้น "ยังไม่ได้ตั้งเวลาเข้างาน" · ไม่นับในโหมดสรุปช่วง
  - **แต่ถ้าเขาเช็คชื่อเข้ามาจริง แถวนั้นยังโชว์** — ซ่อนคนออกจาก "รายการที่ต้องตาม" ไม่ใช่ซ่อนข้อมูลที่มีอยู่
  - **⚠️ ไม่เดาจาก "ไม่ได้กรอกตำแหน่ง/เวลา"** ทั้งที่กฎนั้นตรงกับ 5 คนที่เจ้าของหมายถึงพอดี —
    เพราะ**พนักงานใหม่ที่ยังกรอกไม่ครบจะหายไปจากพาเนลแบบเงียบๆ** ซึ่งอันตรายกว่าการมีชื่อเกิน ·
    migration 0015 เติมค่าย้อนหลัง **ครั้งเดียวกับแถวที่มีอยู่ตอน migrate** (ตำแหน่ง+เวลา+วันหยุด ว่างทั้งหมด)
    แล้วหลังจากนั้นเป็นการติ๊กเองล้วนๆ
  - view `v_employees`/`v_employee_line` เพิ่มคอลัมน์ **`"ต้องเช็คชื่อ"`** ให้ n8n ข้ามคนกลุ่มนี้ได้
    (ต้องรัน [deploy/n8n_postgres_access.sql](deploy/n8n_postgres_access.sql) ซ้ำ · รันซ้ำไม่แตะรหัสผ่าน)
- **⚠️ กติกาเดิมยังอยู่: ห้ามส่ง LINE user id ของพนักงานออกหน้าเว็บ** — พาเนลโชว์แค่ "ผูกไว้กี่บัญชี" ·
  `/api/v1/employees` ส่ง id ได้ (ป้องกันด้วยคีย์ + เป็น server-to-server)
- **📄 [deploy/n8n_checkin_v2.json](deploy/n8n_checkin_v2.json)** — **workflow เช็คชื่อฉบับใหม่ทั้งอัน** (import ใน n8n) · กลุ่มเป็นไอดีฝั่งบอทใหม่ · token เป็น placeholder ให้ใส่เอง · รายชื่อ/หมายเหตุอ่าน-เขียนผ่าน Postgres · **ตัดสินสายด้วยเวลาเข้างานรายคน** (เดิมฟิกซ์ 09:00) · **เก็บประวัติเช็คชื่อลง `checkout_checkin` แล้ว — ไม่ใช้ Google Sheets อีกเลยทั้ง workflow**
  - **⚠️ 16/09 workflow เดิมหยุดทำงานทั้งวัน** — `If2` กรอง groupId ของบอทเดิม แต่กลุ่มย้ายไปบอทใหม่แล้ว (วัดจริง: รูปเช็คชื่อ 48 รูป/36 คน เข้ากลุ่มตามปกติ แต่ไม่ถูกบันทึกสักรายการ)
- **📄 [deploy/n8n_employees_postgres.json](deploy/n8n_employees_postgres.json)** — โหนด Postgres 3 ตัวสำเร็จรูป (ดึงรายชื่อ · หา userId นี้คือใคร · บันทึกหมายเหตุ) ก๊อปวางบน canvas ของ n8n ได้เลย เหลือแค่เลือก credential
- **📄 [deploy/n8n_postgres_access.md](deploy/n8n_postgres_access.md) + [.sql](deploy/n8n_postgres_access.sql)** — ถ้าจะให้ n8n ใช้ **โหนด Postgres** แทนโหนดชีต: SSH tunnel (แนะนำ) / เปิดพอร์ตเฉพาะ IP / หรือใช้ HTTP API ·
  ไฟล์ SQL สร้าง role `n8n` + view **`v_employees`** (1 แถว/คน · มี `line_user_ids` ครบทุกบอท) และ **`v_employee_line`** (1 แถว/บัญชี LINE) · เขียนได้ช่องเดียวคือ `note` (หมายเหตุ ลา/สาย) — **ห้ามให้ n8n ใช้ user `oxlet`/`postgres`** (ฐานข้อมูลนี้มีแชทลูกค้า)
- **⚠️ ต่อ Postgres ตรงจาก n8n ยังทำไม่ได้** — ฐานข้อมูลตั้ง `listen_addresses = localhost`
  (n8n อยู่คนละเครื่อง) · ถ้าจะทำต้องเปิดพอร์ต/ทำ SSH tunnel + สร้าง role อ่านอย่างเดียว →
  **ใช้ API ง่ายกว่าและไม่ต้องเปิดฐานข้อมูลออกเน็ต**

### 🕘 เช็คชื่อเข้างาน — ย้ายจากชีตมาเก็บใน Postgres (16 ก.ย.69 · เจ้าของสั่ง)
*"มันเป็นการเก็บทุกๆ วันอยู่แล้ว ไม่ต้องมานั่งลบข้อมูลแบบเดิม เก็บใน Postgres"*

- **`checkout.CheckIn`** (migration **0014**) — **1 แถวต่อ "คน 1 วัน"** · `UniqueConstraint(user_id, date_iso)`
  → n8n ใช้ `ON CONFLICT` upsert · ส่งรูปซ้ำ = ทับแถวเดิม **ไม่ต้องไล่ลบแถวซ้ำแบบชีต**
- เก็บ: `employee` (FK) · `user_id` · `date_iso` · `checkin_at` · `time_hm` · **`work_start` (สำเนาเวลาเข้างาน
  ตอนนั้น — เปลี่ยนเวลาเข้างานทีหลัง ประวัติเก่าต้องไม่เปลี่ยนตาม)** · `status` (ontime/late/abnormal) ·
  `reason` · `time_source` (`image` = อ่านจากรูป · `message` = เวลาที่ส่งเข้ากลุ่ม) · ที่อยู่ · `raw` (ผล OCR ดิบ)
- **★ สาย/ตรงเวลา ตัดสินด้วย "เวลาเข้างานรายคน"** — ของเดิมใน n8n ฟิกซ์ 09:00 ทุกคน ทั้งที่ชีตมี 8:00/8:30/9:00
  → คนเข้า 8:00 มาถึง 8:59 เคยถูกนับว่า "ตรงเวลา"
- **โหมดสรุปช่วง** (`?from=&to=` · ปุ่ม "สรุปทั้งเดือน" ในพาเนล) — รายคน: มากี่วัน · สายกี่ครั้ง · **มาเฉลี่ยกี่โมง** · ล่าสุดวันไหน · เรียงคนสายบ่อยขึ้นก่อน
- **หน้าดู**: เมนู → **ตรวจสอบ & Log → เช็คชื่อเข้างาน** (`openCheckins()` · ลิงก์ตรง `/dashboard/?panel=checkin`)
  - **★ ออกแบบใหม่ 16 ก.ย.69 (เจ้าของขอ "ดูง่ายกว่านี้หน่อย")** — ของเดิมเป็น KPI 5 ก้อน + ชิปชื่อคน 45 อันเรียงรวด
    ต้องไล่อ่านทีละชื่อถึงจะรู้ว่าใครมีปัญหา · ตอนนี้:
    - **เลื่อนวันด้วยปุ่ม ‹ › ข้างช่องวันที่** (เดิมต้องเปิดปฏิทินเลือกทุกครั้ง)
    - **แถบความคืบหน้าบรรทัดเดียว + คำอธิบายสี** แทนกล่องตัวเลข 5 ใบ — เห็นสัดส่วนมา/สาย/ขาดในแวบเดียว
    - **ตารางคนที่มาแล้ว** บอก **"สาย X นาที"** เป็นตัวเลขจริง (`_ckiLate()` = เวลาเช็คชื่อ − เวลาเข้างานของคนนั้น)
      ไม่ใช่แค่ป้าย "สาย" · มีคอลัมน์เวลาเข้างานให้เทียบข้างกัน
    - **★ คนที่ยังไม่เช็คชื่อแยก 2 ก้อน**: **"เลยเวลาเข้างานแล้ว"** (แดง · เทียบกับนาฬิกาจริง **เฉพาะตอนดูวันนี้**)
      กับ **"ยังไม่ถึงเวลาเข้างาน"** — เดิมกองรวมกันจนคนที่เข้า 9:00 ตอน 8:40 ดูเหมือนขาดงาน
    - **จัดกลุ่มตามตำแหน่ง + บอกจำนวนต่อกลุ่ม** → หัวหน้าฝ่ายกวาดตาเฉพาะทีมตัวเองได้
    - แยก **"วันหยุดวันนี้"** และ **"ยังไม่ได้ตั้งเวลาเข้างาน"** (พร้อมบอกว่าไปตั้งที่เมนู "พนักงาน") ออกจากก้อนขาดงาน
  - ป้าย **"ยังไม่ผูก"** เมื่อจับคู่กับทะเบียนพนักงานไม่ได้ · ป้าย "อ่านจากรูปไม่ได้ ใช้เวลาที่ส่ง" เมื่อ `time_source=message`
- **n8n เขียนเข้ามาโดยตรง** (`deploy/n8n_checkin_v2.json`) — ต้อง `GRANT SELECT, INSERT, UPDATE ON checkout_checkin`
  + `USAGE ON SEQUENCE` (อยู่ใน [deploy/n8n_postgres_access.sql](deploy/n8n_postgres_access.sql) ข้อ 5 ·
  **รันหลัง `migrate` เท่านั้น** ไม่งั้นตารางยังไม่เกิด)
- **⚠️ `date_iso` เป็นวันตามโซนไทย** ที่ n8n คำนวณมาให้ (ไม่ใช่ UTC) — ถ้าไปแก้โค้ดฝั่ง n8n ต้องคงกติกานี้

#### 🖼️ ตารางเช็คชื่อเป็นรูปส่งเข้า LINE — [checkin_report.py](checkout/checkin_report.py) · 16 ก.ย.69
*"เรื่องสำคัญคือเป็นการสร้างตารางเช็คชื่อ รวบรวมชื่อของทุกคน คุณลองสร้างเองได้ไหม โดยที่ไม่ต้องพึ่ง API นอก"*

**แทน workflow เดิมทั้งเส้น** (Google Sheets ×2 → รวมร่าง → สร้าง HTML → **hcti.io** → ส่ง LINE):
- ข้อมูลจาก **Postgres ของเรา** · แปลง HTML→PNG ด้วย **Playwright ในเครื่อง** (ลงไว้อยู่แล้ว)
  → ไม่ต้องจ่าย/ไม่ต้องพึ่งบริการนอก และ **ชื่อพนักงานทุกคนไม่ต้องถูกส่งออกไปให้เว็บอื่นเรนเดอร์**
- **`render_png` ใช้ `page.set_content()`** — ไม่ต้องเปิดเว็บเซิร์ฟเวอร์/ไม่ต้อง login
  (ต่างจากการแคปการ์ดแดชบอร์ดที่ต้องเปิดหน้าเว็บจริง ซึ่งเคยพังเพราะปุ่มแท็บย้ายที่)
- **`manage.py checkin_report [--to ชื่อเล่น|Uxxx|Cxxx] [--date] [--out ไฟล์] [--dry-run] [--no-tag]`**
  · `--to` ใส่ **ชื่อเล่น** ได้เลย ระบบหา LINE id ให้เอง
- คงกติกาเดิมของ workflow: จัดกลุ่มตามทีม (`TEAM_ORDER`) · ติ๊กเขียว/แดง · **เผื่อสาย 5 นาที**
  (`GRACE_MIN`) · ข้ามคนหยุด/ลา · ตัดหมายเหตุที่เป็นข้อความระบบ (`_JUNK_NOTE`) ·
  **แท็กคนที่ถึงคิวมาทำงานแล้วยังไม่เช็คชื่อ**
- **ต่างจากเดิม 2 อย่าง (ตั้งใจ)**: หัวตารางเป็น **"ตรงเวลา"** + มีคอลัมน์ **"เข้างาน"** รายคน
  (ของเดิมเขียน "9.00 น." ทั้งที่จริงมี 8:00/8:30/9:00) · **ผู้บริหารที่ติ๊กไม่ต้องเช็คชื่อไม่อยู่ในตาราง**
- **★ 17 ก.ย.69 — ช่องหมายเหตุขึ้นเฉพาะ "หยุดวันนี้" กับ "หมายเหตุที่คนพิมพ์เอง"** (เจ้าของแจ้งว่า "มันรกไป")
  - **ต้นเหตุ**: n8n เขียน `CheckIn.reason` ให้ **ทุกแถว** เป็นคำอธิบายสถานะ
    (`ตรงเวลา (จากรูป · เข้างาน 8:30)` / `สาย (จากเวลาส่ง · …)` — วัดจริงบนเซิร์ฟเวอร์ **ทุกค่าเป็นแบบนี้หมด**)
    ซึ่ง **ซ้ำกับคอลัมน์ ✓ ที่อยู่ติดกัน** → 43 แถวมีข้อความเต็มหมด อ่านไม่ออกว่าใครลาจริง
  - **`_human_note()`** ตัดทิ้งด้วยร่องรอย **`_AUTO_NOTE` = `("(จากรูป", "(จากเวลาส่ง")`** + คำเดี่ยว ตรงเวลา/สาย
    → เหลือเฉพาะที่คนพิมพ์ในช่อง "หมายเหตุ" ของหน้าพนักงาน · **กติกา "มีหมายเหตุ = ไม่ตามตัว" ไม่เปลี่ยน**
    (ข้อความอัตโนมัติไม่เคยควรนับเป็นการลาอยู่แล้ว)
  - **⚠️ ที่ตัดออกไปด้วย: "สาย X นาที" และ "ยังไม่เช็คชื่อ"** — อันแรกคอลัมน์ "มาสาย" บอกอยู่แล้ว ·
    อันหลังเคยเป็น **ตัวเดียวที่แยก "มาสาย" ออกจาก "ไม่มา"** (เดิมทั้งคู่ขึ้นติ๊กแดงอันเดียวกัน)
    → เปลี่ยนคนที่ยังไม่เช็คชื่อเป็น **กากบาทแดง `_CROSS`** แทน + เขียนคำอธิบายไว้ท้ายตาราง
    · **ถ้าเอา "สาย X นาที" กลับ ให้ใส่ที่ `note_show` จุดเดียว** (`_late_text` ถูกลบไปแล้ว ดู git history)

**⚠️★ 21 ก.ย.69 (รอบ 2) — "มันไม่แท็กด้วยซ้ำ" · ตัวสำรองกลายเป็นตัวปัญหา**
- อาการ: ทั้ง 2 รอบส่งถึงกลุ่มก็จริง แต่ **ไม่มีใครถูกแท็กสักคน** และยังเอ่ยชื่อคนนอกกลุ่ม
- **ต้นเหตุ**: ตัวสำรองที่เพิ่งใส่ไปเมื่อวาน (แท็กพลาด = ส่งซ้ำแบบไม่แท็ก) **ทำงานทุกวัน**
  · วัดจากล็อกจริง: `ตารางเช็คชื่อเข้างาน` ล้ม → `(ส่งซ้ำแบบไม่แท็ก)` สำเร็จ — ซ้ำแบบนี้ 19–21/09
  · LINE บอกชัด `substitution["u1"].mentionee` = **แท็กพลาดคนเดียว ทั้งข้อความโดนตีกลับ**
    → ตัวสำรองเลย **ถอดแท็กของทุกคนทิ้ง** ทั้งที่ผิดอยู่คนเดียว
- **แก้ที่ต้นทาง: ถาม LINE ก่อนส่งว่า "คนนี้อยู่ในกลุ่มนี้จริงไหม"**
  (`GET /v2/bot/group/<gid>/member/<uid>` → 200 อยู่ · 404 ไม่อยู่) — `outsiders()`/`only_in_group()`
  · **คนนอกกลุ่ม = ตัดทั้งชื่อ ไม่ใช่แค่ไม่แท็ก** (ส่งเข้ากลุ่มเพื่อ "ตามตัว" คนที่ไม่ได้อยู่ในนั้น
    เอ่ยชื่อไปก็ไม่มีใครเห็น) · เขายังอยู่ในตาราง/หน้าเว็บตามเดิม
  · **จำคำตอบไว้ใน KV `checkin_group_member`** (อยู่=7 วัน · ไม่อยู่=1 วัน เผื่อเพิ่งถูกเชิญเข้า)
    → ถามแค่วันละไม่กี่ครั้ง ไม่ยิง API ทุกเช้า
  · **ถาม LINE ไม่ได้ (เน็ต/401/429) = ถือว่าอยู่ในกลุ่ม** — ตัดผิดแล้วคนหายเงียบ แย่กว่ามีชื่อเกิน
- **ตัวสำรอง "ส่งซ้ำแบบไม่แท็ก" ยังอยู่** แต่กลายเป็นด่านสุดท้ายจริงๆ (ไม่ใช่ทางที่วิ่งทุกวัน)
- **กฎ**: *ตัวสำรองที่ทำงานทุกวัน = ต้นเหตุที่ยังไม่ได้แก้* — เห็นล็อกขึ้น "(ส่งซ้ำ…)" ติดกัน
  ต้องถือว่าเป็นบั๊ก ไม่ใช่ระบบกันพลาดที่ทำงานดี

**⚠️★ 21 ก.ย.69 — ตารางเช็คชื่อมีชื่อคนที่ "ไม่อยู่ในกลุ่มด้วยซ้ำ" (เจ้าของแจ้ง · แก้แล้ว)**
- อาการ: กลุ่ม **"ไม่ระบุทีม"** ท้ายตารางมี `Sirun` · `Weerasak` · `โด่ง` (เข้างาน `-`) ขึ้น ✗ ทุกวัน
  · ทั้ง 2 รอบยังแท็กตามตัวด้วย — ทั้งที่ไม่ได้อยู่ในกลุ่มเช็คชื่อเลย
- **ต้นเหตุ**: `people._employee_for()` สร้างพนักงานให้เองเมื่อมีคนพิมพ์ใน **กลุ่มไหนก็ได้**
  (วัดจริง: Sirun มาจากกลุ่ม *Branding and Content Marketing* · โด่ง จาก *รับ-ส่งระหว่างสาขา*
  · Weerasak จาก *ห้องจ่ายเบอร์ REJECT*) → แถวใหม่ได้ `track_checkin=True` ตาม default
  **= เข้าระบบเช็คชื่อทันทีโดยไม่มีใครยืนยัน**
- **แก้ 3 ชั้น**: (1) แถวที่ระบบสร้างเอง **เกิดมาเป็น `track_checkin=False`** (ยังโผล่ในหน้าพนักงาน
  ป้าย "ใหม่" ให้คนมาเติมแล้วค่อยติ๊กเอง) · (2) `collect()` **ข้ามคนที่ยังไม่ได้ตั้งเวลาเข้างาน**
  (ตัดสินสาย/ตรงเวลาไม่ได้อยู่แล้ว) **เว้นแต่เขาเช็คชื่อเข้ามาจริง** — ไม่ซ่อนเงียบ ท้ายตารางเขียน
  "ยังไม่ได้ตั้งเวลาเข้างาน N คน (ไม่นับ)" · (3) **migration 0021** ปิด `track_checkin` ย้อนหลัง
  ให้แถว auto ที่ไม่มีเวลาเข้างาน **และไม่เคยเช็คชื่อเลย** (แถวที่คนกรอกเอง/มาจากชีต ไม่แตะ)
- **กฎ: "อยู่ในทะเบียนพนักงาน" ≠ "ต้องเช็คชื่อ"** — การเพิ่มชื่ออัตโนมัติมีไว้ให้คน*เห็น*ว่ามีคนใหม่
  ไม่ใช่ให้ระบบเริ่มตามตัวเขาเอง · เกณฑ์ที่ใช้ตัดสินว่า "เข้าระบบแล้ว" = **มีเวลาเข้างาน**

**⚠️★ 20 ก.ย.69 — การแจ้งเตือน "ไม่ลงกลุ่ม" 3-4 วันติด (เจ้าของแจ้ง · ไล่จาก `dash_event_log` เจอ 2 สาเหตุคนละเรื่อง)**
- **เช็คชื่อ (ตาราง 09:30 + รอบสาย 10:00) ล้มทุกวันตั้งแต่ 18/09** — LINE 400
  `"The mentioned user is not found in the group"` = **ไอดีถูก (ฝั่งบัญชีที่ส่ง) แต่คนนั้นไม่ได้อยู่ในกลุ่มนั้น**
  (ลาออก/ไม่เคยเข้ากลุ่ม) → **LINE ปฏิเสธทั้งข้อความ คนทั้งกลุ่มเลยไม่ได้เห็นตาราง เพราะแท็กพลาดคนเดียว**
  · แก้: **`_send_msgs()`** — โดนปฏิเสธเพราะแท็ก = **สร้างข้อความใหม่แบบไม่แท็กแล้วส่งซ้ำ**
  (ชื่อยังอยู่ในข้อความครบ) · **ล้มด้วยเหตุอื่นไม่ส่งซ้ำ** (กันสแปม) · ใช้ทั้ง `send()` และรอบสาย
- **การ์ดตั้งเวลา ("สรุปลีดเข้าไลน์") ล้ม 480 ครั้งใน 7 วัน** — ปลายทาง 2 กลุ่มเป็น **id ที่บอทตัวส่งไม่ได้อยู่**
  (`C3ee0d44…` · `C40b836d…` "จองรถ" ซึ่งมีแต่บอทตัวรับได้ยิน) → LINE 400 ทุกครั้ง
  แต่ self-heal เดิม **ลองใหม่ทุกนาทีตลอดหน้าต่าง 20 นาที = แคปรูปด้วย Chromium ทิ้งเปล่า 480 ครั้ง**
  · แก้: บันทึก **`fatal:true` เมื่อ LINE ตอบ 4xx** แล้ว **ข้ามทั้งวัน** · เหลือ self-heal ไว้เฉพาะพลาดชั่วคราว
  (แคปไม่ออก/เน็ต/5xx) · **ตัวปลายทางต้องแก้ที่คน**: เชิญบอทตัวส่งเข้ากลุ่ม หรือเปลี่ยนเป็น group id ฝั่งบอทตัวส่ง
- **กฎที่ได้จากรอบนี้**: *การแท็กเป็นของแถม ไม่ใช่เงื่อนไขของการส่ง* — ข้อความต้องถึงกลุ่มไว้ก่อนเสมอ
  · และ *ล้มแบบเดิมซ้ำๆ ต้องหยุด* ไม่ใช่ลองใหม่ไปเรื่อยๆ (เปลือง Chromium/แรมของ VPS โดยไม่มีใครรู้)

**⚠️ 3 กับดักที่เจอตอนทำ (อย่าลืม)**
1. **LINE แท็กได้เฉพาะในกลุ่ม/ห้อง** — ยิง `textV2` mention เข้า **แชท 1:1 จะโดนปฏิเสธทั้งข้อความ
   รูปก็ไม่ถึงด้วย** (ส่งไปพร้อมกัน) → `send()` เห็นปลายทางเป็น `U…` จะเปลี่ยนเป็น **รายชื่อธรรมดา** ให้เอง
2. **ไอดีออกต่อ provider** — แท็กต้องใช้ไอดี **ฝั่งบัญชีที่กำลังส่ง** (`_pick_id`) ·
   ไอดีผิดฝั่ง = LINE ตอบ 400 แบบไม่บอกสาเหตุ · คำสั่งเตือนล่วงหน้าถ้าคนที่จะส่งหาไม่มีไอดีบัญชีนั้น
   - **⚠️★ 17 ก.ย.69 — ไอดีที่ `channel` ว่าง ต้องไม่ถูกเอาไปแท็ก** (แก้ก่อนใช้จริงทัน):
     เวอร์ชันแรกเขียน `if channel and p.channel and p.channel != channel: continue`
     → **ไอดีที่ไม่รู้ที่มา (`channel=''`) หลุดผ่าน** แล้วยังหยิบมาก่อนได้ด้วยเพราะลำดับแถวไม่แน่นอน
     · วัดบนเซิร์ฟเวอร์จริง: พนักงาน 43 คน **มีไอดีแบบนี้ถึง 41 คน** (ของที่นำเข้าจากชีต = ไอดีบอทเดิม)
     · **แท็กพลาดคนเดียว LINE ปฏิเสธทั้งข้อความ คนอื่นก็ไม่ได้รับ** → เสียทั้งรอบทุกวันโดยไม่มีใครรู้
     · ตอนนี้ **ต้องตรงบัญชีเป๊ะเท่านั้น ไม่ตรง = ไม่แท็ก แต่ยังพิมพ์ชื่อไว้ในข้อความ** (fail-safe)
     · `tag_coverage()` + `--dry-run` บอกล่วงหน้าว่า **จะแท็กได้กี่คนจากกี่คน** และใครแท็กไม่ได้
     (วัดจริง: แท็กได้ 41/43)
3. **รูปใหม่ต้องเข้าคิวโดนกวาดด้วย** — เพิ่ม `checkin_*.png` ใน `_cleanup_old`
   (บทเรียนเดิม: ลืมใส่ `card_*.png` แล้วค้าง **1.3 GB**)
- **ส่งได้จริงเฉพาะบนเซิร์ฟเวอร์จริง** — LINE ต้องดึงรูปจาก URL https สาธารณะ (เหมือนรายงานรายวัน)
- **`PLAYWRIGHT_EXECUTABLE`** (env · ออปชั่น) = ระบุตัวเบราว์เซอร์เอง — ใช้ตอนเวอร์ชัน playwright
  กับ Chromium ไม่ตรงกัน (`Executable doesn't exist`) ซึ่งเคยทำรายงานรายวันหยุดส่งมาแล้ว

**★ รอบสาย 10:00 — ตามคนที่ยังไม่เช็คชื่อ + แท็กผู้บริหาร (คัดลอกจาก workflow "Schedule Trigger 10:00")**
- `escalation_messages()` → ข้อความหน้าตาเดียวกับของเดิม: `⚠️ แจ้งเตือนรอบ 10:00 น.` → ลิสต์คนที่ยัง
  ไม่เช็คพร้อมแท็กทีละคน → ปิดท้าย `ยังไม่เช็คครับ` + แท็กผู้บริหาร · **ไม่มีใครขาด = ไม่ส่งอะไรเลย**
- **★ เลือกได้ว่าจะแท็กใคร — `Employee.notify_missing`** (migration **0017**) ติ๊กช่อง **"แจ้งเตือน"**
  ในหน้าพนักงาน · ของเดิม n8n **ฝัง `MANAGERS` userId ไว้ในโค้ด** → เปลี่ยนคนทีต้องไปแก้โค้ด
  และไอดีที่ฝังไว้เป็นของ**บอทตัวเก่า** (คนละ provider กับบอทที่ส่งอยู่ = แท็กไม่ติด)
- **`DAYOFF_LOCK` ที่ n8n hardcode ไม่ต้องมีแล้ว** — ช่อง "วันหยุด" รับหลายวันในช่องเดียวอยู่แล้ว
  (เช่น `ศุกร์ เสาร์ อาทิตย์`) `collect()` เช็คด้วย "ชื่อวันนี้อยู่ในช่องไหม"
- ทดสอบ: `manage.py checkin_report --escalate --dry-run` (เห็นข้อความเต็ม + **จะแท็กได้กี่คน**) ·
  `--escalate --to <ชื่อเล่น|Cxxxx>` = ส่งจริง

**★ 24 ก.ย.69 — "ตั้งชื่อเล่นแล้ว แต่มันขึ้นเป็นชื่อ user" (เจ้าของแจ้ง)**
- **โค้ดการแก้ชื่อไม่ได้พัง** — ทดสอบในเบราว์เซอร์จริงแล้ว แก้ชื่อเล่น → ขึ้นครบทั้ง
  ฐานข้อมูล / พาเนลเช็คชื่อ / ตารางรูปที่ส่งเข้า LINE
- **ต้นเหตุจริง**: แถวที่ **ระบบสร้างเอง** (`_employee_for`) ใช้ **ชื่อ LINE เป็นชื่อเล่น**
  ไปก่อน (nickname เป็น unique + บังคับมีค่า) → ทุกหน้าเลยโชว์ชื่อ LINE
  · และป้าย **"ใหม่"** หายทันทีที่มีคนกรอกตำแหน่ง/เวลา **ทั้งที่ชื่อเล่นยังไม่ได้ตั้ง**
  → ไม่มีอะไรบอกว่ายังต้องมาตั้งชื่อ คนเลยนึกว่าระบบไม่ยอมบันทึกที่ตั้งไป
  · วัดจริงบน prod 24/09: มีคนเดียวในสถานะนี้ — **Weerasak** (auto · ทีม B · 9.00)
- **แก้**: `needsNick` (API พนักงาน) + `rawName` (API เช็คชื่อ) = ชื่อเล่นยังเท่ากับชื่อ LINE
  → หน้า "พนักงาน" ขึ้นป้าย **"ยังเป็นชื่อ LINE"** · พาเนลเช็คชื่อขึ้น **"(ชื่อ LINE)"** ต่อท้ายชื่อ
  · ตั้งชื่อเล่นจริงเมื่อไหร่ ป้ายหายเองทั้ง 2 ที่
- **กฎ: ค่าที่ระบบเดาใส่ให้ชั่วคราว ต้องติดป้ายว่าเดาให้** — ไม่งั้นมันกลายเป็น
  ของจริงในสายตาคนใช้ แล้วไม่มีใครไปแก้

**⚠️★ 24 ก.ย.69 — "ลาป่วยเมื่อวาน กลายเป็นลาป่วยทุกวัน" (เจ้าของแจ้ง · แก้แล้ว)**
- อาการ: *"เหมือนมันจะเอาคนที่ลาป่วยเมื่อวาน มาลาป่วยวันนี้ด้วย"*
- **ต้นเหตุ = เอาเรื่อง "รายวัน" ไปเก็บในช่องของ "ตัวคน"** — `Employee.note`
  เป็นหมายเหตุประจำตัว แต่ n8n คัดข้อความลาจากกลุ่ม LINE มาเขียนลงช่องนี้
  (`UPDATE checkout_employee SET note = …`) แล้ว **ไม่มีใครลบ** → ขึ้นว่าลาป่วยทุกวันตลอดไป
  · วัดจริง 24/09: ค้างอยู่ 3 คน — `คิมลาป่วยครับ` · `ฟิล์มลาป่วยครับ` · ข้อความสั่งงานไลฟ์ของอุ้ม
- **★ ผลที่หนักกว่าตารางรก: คนพวกนั้น "ไม่ถูกตามตัว" ทุกวัน** เพราะกติกา `hasAnyNote`
  (มีหมายเหตุ = ไม่แท็ก) → ขาดงานจริงก็ไม่มีใครรู้
- **แก้**: `Employee.note_date` (วันที่เขียน) + `Employee.note_sticky` (ค้างไว้จนกว่าจะลบ)
  · `_note_for(e, day)` ใน [checkin_report.py](checkout/checkin_report.py) — ใช้หมายเหตุ
  **เฉพาะวันที่เขียน** เว้นแต่ติ๊ก sticky · แถวเก่าที่ `note_date` ว่าง = ถือว่าหมดอายุแล้ว
  · หน้า "พนักงาน" โชว์ **"เขียนไว้ 23/9"** ใต้ช่อง + ติ๊ก **"ค้างไว้"** สำหรับลายาว (ลาคลอด)
- **⚠️ ต้องรัน 2 อย่างตอน deploy**: `migrate` (checkout **0022**) **และ**
  [deploy/n8n_postgres_access.sql](deploy/n8n_postgres_access.sql) **ข้อ 7** —
  trigger ประทับ `note_date` ฝั่ง Postgres · **จำเป็นเพราะ n8n เขียน SQL ตรง ไม่ผ่าน Django**
  (ไม่รัน = หมายเหตุจาก n8n ไม่มีวันที่ → ไม่โชว์เลยสักวัน)
  · trigger ใช้เวลาโซนไทย ไม่ใช่ `CURRENT_DATE` (เซิร์ฟเวอร์เป็น UTC → ก่อนเที่ยงคืนไทยจะได้วันก่อนหน้า)
- **กฎ: ข้อมูลที่เป็น "ของวันนั้น" ต้องอยู่กับวันนั้น** (`CheckIn.reason`) ไม่ใช่กับตัวคน —
  ถ้าจำเป็นต้องเก็บที่ตัวคน ต้องมีวันหมดอายุเสมอ

**★ 17 ก.ย.69 — วิธี "ไม่ให้โดนแท็ก" + กันแท็กหมู่ (เจ้าของถาม "หยุดยาวต้องพิมพ์ยังไง")**
- **มีหมายเหตุอะไรก็ตาม = ไม่แท็ก** (กติกาเดียวกับของเดิมที่เช็ค `hasAnyNote`) —
  ก่อนหน้านี้ผมยกเว้นเฉพาะคำ ลา/หยุด/สลับ ทำให้คนพิมพ์ "ทดเวลา"/"ไปธุระก่อนเข้า" ยังโดนแท็ก
  · หมายเหตุ**ยังโชว์ในตาราง** แค่ไม่ตามตัว · ข้อความระบบ (`_JUNK_NOTE`) ไม่นับ
  · **หมายเหตุถาวรในทะเบียนไม่หายเอง** (เช่น "ลาคลอด") — กลับมาทำงานต้องลบเอง
- **`max_tag` (default 20)** — ขาดเกินเพดาน = **ไม่แท็กรายคน** บอกจำนวนแทน
  **แต่ยังแท็กผู้บริหาร** · เหตุผล: วันที่ระบบเช็คชื่อมีปัญหา/หยุดยาว จะขาดทั้งบริษัท
  ถ้าแท็ก 43 คนทุกเช้า **คนจะปิดแจ้งเตือนกลุ่ม แล้วทีหลังเตือนอะไรก็ไม่มีใครเห็น**
  (แก้ยากกว่าตอนที่ยังไม่พัง) · `--max-tag 0` = ไม่กัน
- **`holidays`** — วันหยุดบริษัท (YYYY-MM-DD) วันนั้น **ไม่ส่งทั้ง 2 รอบ** ·
  ตั้งด้วย `checkin_schedule --holiday 2026-12-31,2027-01-01` (`none` = ล้าง)
- **📄 คู่มือผู้ใช้: [deploy/checkin_howto.md](deploy/checkin_howto.md)** — หน้าไหนตั้งอะไร ·
  พิมพ์ยังไงไม่โดนแท็ก · หยุดยาวทำยังไง (เขียนให้คนใช้อ่าน ไม่ใช่ dev)

**★ 17 ก.ย.69 — หน้าตั้งค่าบนเว็บ + ล็อกบอทเป็นตัวส่ง (เจ้าของสั่ง)**
- **`/dashboard/?panel=checkinset`** (`openCheckinConfig` · เมนู → ลูกค้า & ข้อมูล →
  "ตั้งค่าส่งเช็คชื่อเข้าไลน์") · API **`/checkout/api/checkin_config`** (GET/POST · `_admin`)
  - เปิด/ปิด · เวลา 2 รอบ (dropdown ทุก 15 นาที) · โหมด test/group · เพดานกันแท็กหมู่ ·
    วันหยุดบริษัท · **ปุ่มส่งทดสอบทั้ง 2 รอบ**
  - **dropdown กลุ่มกรองด้วย `group_visible_to_push()`** — โชว์เฉพาะกลุ่มที่บอทตัวส่งอยู่จริง
    กันเลือกกลุ่มของบอทเก่าแล้วส่งไม่ออก (เคยเป็นต้นเหตุการ์ดส่งไม่ออกทุกใบมาแล้ว)
  - หัวจอบอก **แท็กได้กี่คนจากกี่คน + ใครแท็กไม่ได้** ก่อนกดใช้จริง
- **`bot()` — ล็อกเป็นบัญชีตัวส่ง (OxletautoGiveLead) ทุกกรณี** *"Bot ที่ต้องใช้ในการส่งคือ
  OxletautoGiveLead"* · เดิมใช้ `token_for(ปลายทาง)` ซึ่ง **แชทส่วนตัวจะตกไปใช้บอทเดิม**
  → ทดสอบแล้วไม่ตรงกับของจริง · **ผลข้างเคียง: คนรับแชทส่วนตัวต้องแอดบอทตัวนี้ก่อน**
  · `bot()` ถาม LINE ว่าบัญชีชื่ออะไรจริง (`bot_info`) เอามาโชว์บนหน้าตั้งค่า
- **⚠️ `h()` ใน index.html รับเฉพาะสตริง** (`s ? s.replace(...) : ''`) — ส่งตัวเลข (เช่น `maxTag`)
  เข้าไปตรงๆ = `TypeError` แล้ว **พาเนลพังทั้งอัน** · ต้อง `h(String(v))`
- **⚠️ แก้ template แล้วต้องรีสตาร์ท dev server เสมอ** (โปรเจกต์ cache template แม้ DEBUG) —
  ผมลืมกฎนี้เองตอนทดสอบ แล้วไล่บั๊กที่แก้ไปแล้วอยู่รอบหนึ่ง

**★ ตั้งเวลาส่งเอง — แทน Schedule Trigger ของ n8n** (`maybe_send()` เรียกจาก **`cron_tick`** ทุกนาที)
- config อยู่ที่ KV **`checkin_notify_config`** = `{enabled, table_time, escalate_time, mode, group_id, test_id}`
  · **ปิดโดยปริยาย** · `escalate_time` ว่าง = ไม่ส่งรอบสาย
- **`manage.py checkin_schedule [--on|--off] [--table-time HH:MM] [--escalate-time HH:MM]
  [--group Cxxx] [--test-id Uxxx] [--mode test|group]`** — ไม่ใส่อะไร = โชว์ค่าปัจจุบัน
  + บอกว่าตอนนี้จะแท็กใครบ้าง
- **กันส่งซ้ำด้วย KV `checkin_notify_last`** (วัน+รอบ) — cron ยิงทุกนาที ถ้าไม่กัน
  นาทีเดียวกันอาจถูกยิงซ้ำจากคนละ worker
- ผลลัพธ์แต่ละรอบโผล่ใน response ของ `cron_tick` (`"checkin"`) และใน **`dash_event_log`**
- **⚠️ โหมด `test` = ส่งเข้าแชทส่วนตัว ซึ่งแท็กคนไม่ได้** (ระบบเปลี่ยนเป็นรายชื่อให้) —
  ใช้จริงต้อง `--mode group` ไม่งั้นจะดูเหมือนแท็กพัง

### 🔎 ดูข้อมูลดิบด้วย SQL — [db_query.py](dashboard/services/db_query.py) · 16 ก.ย.69 (เจ้าของขอ)
*"ให้มันแสดง query แบบเป็น raw data · ก็อปหน้า PostgreSQL มา · ให้มันเป็นการ query จาก postgres จริงๆ
และให้มันสามารถ export ข้อมูลตาม filter ได้ด้วย เช่น ช่วงวันที่นี้ถึงวันที่นี้"*

**3 หน้านี้ตอบคนละคำถาม — อย่าเอามารวมกัน**: สารบัญ = "เก็บอะไรไว้" · ดาวน์โหลด = "เอาทั้งตารางออกมา" ·
**อันนี้ = "ขอดู/ขอเอาเฉพาะที่อยากได้"** (เลือกคอลัมน์เอง กรองเอง join เองได้)
- เมนู → **ลูกค้า & ข้อมูล → ฐานข้อมูล (SQL)** (`openSqlPanel()`) · ลิงก์ตรง **`/dashboard/?panel=sql`**
  (**`?panel=db` ก็มาที่นี่** — พาเนลสารบัญเดิมถูกยุบรวมเข้ามาแล้ว 16 ก.ย.69)
- **หัวหน้ามีของจากพาเนลสารบัญเดิม**: กล่องเตือน "ข้อมูลการขายอยู่ใน Google Sheets" + ยอดแถวรวม +
  ปุ่ม **⬇ ทั้งหมด (.zip)** · แถบตารางซ้ายโชว์ **จำนวนแถว + จุดส้ม = มีข้อมูลส่วนบุคคล**
- หน้าตาแบบ DbVisualizer: **แถบตารางทางซ้าย** (กดชื่อ = ใส่คำสั่งให้ + รันเลย · กดลูกศรดูคอลัมน์
  · กดชื่อคอลัมน์ = แทรกลงในคำสั่ง) · ช่องพิมพ์ SQL (**Ctrl+Enter = รัน**) · ตารางผลลัพธ์แบบ raw
- **ช่วงวันที่**: ใส่ **`:from` / `:to`** ในคำสั่ง แล้วเลือกวันที่ในช่องด้านบน — กดชื่อตารางที่มีช่องวันที่
  ระบบใส่ `WHERE <ช่องวันที่> >= :from AND <ช่องวันที่> < :to` ให้เอง
  - **`:to` = วันถัดจากที่เลือก** จึงต้องเขียน `< :to` — ถ้าใช้ `<= :to` กับคอลัมน์ที่มีเวลาด้วย
    **ของวันสุดท้ายจะตกทั้งวัน** ซึ่งคนมักไม่ทันสังเกต
  - **ผูกเป็นพารามิเตอร์ ไม่ใช่ต่อสตริง** → ใส่ค่าอะไรมาก็ไม่กลายเป็นคำสั่ง
- **⬇ ดาวน์โหลด CSV** = ผลของคำสั่งเดิม **ทุกแถว** (ไม่ตัดที่ limit ของหน้าจอ · เพดาน 200,000 แถว)
  · BOM ให้ Excel ไทยไม่เพี้ยน · ชื่อไฟล์ติดช่วงวันที่มาด้วย

**★ ความปลอดภัย — เปิดช่องพิมพ์ SQL จากหน้าเว็บ ต้องกันหลายชั้น (ฐานข้อมูลนี้มีแชทลูกค้า)**
1. **`SET TRANSACTION READ ONLY` ฝั่ง Postgres = ชั้นที่เชื่อได้จริง** · ตั้งไม่สำเร็จ = **ไม่รันเลย (fail-closed)**
2. **`transaction.set_rollback(True)` เสมอ** — ไม่มีอะไรค้างให้ commit
3. **`statement_timeout` 20 วิ** — กัน query หนักลากทั้งเครื่อง (nginx ตัดที่ 120 วิ)
4. ต้องขึ้นต้น `SELECT`/`WITH` · **ห้ามมี `;` คั่น** (psycopg2 ยิงหลายคำสั่งรวดเดียวได้)
5. **บล็อกคำเขียนทั้งประโยค** — `WITH x AS (DELETE … RETURNING *) SELECT * FROM x`
   **ผ่านด่าน "ขึ้นต้นด้วย WITH" ได้และไม่มี `;`** · ด่านนี้สำคัญเป็นพิเศษบน **SQLite (dev)**
   ที่ไม่มี READ ONLY มากันให้ (`\b` ทำให้ `deleted_at`/`updated_at` ไม่โดนจับผิด)
6. บล็อกฟังก์ชันอ่านไฟล์/ออกเน็ตของ Postgres (`pg_read_file`, `dblink`, `lo_export`, `copy(`)
7. **ปิด LINE user id ของพนักงาน** ในผลลัพธ์**และ**ไฟล์ export (ใช้ `db_export._scrub` ตัวเดียวกัน
   · แคชรายชื่อ 5 นาที เพราะต้องอ่าน Google Sheets) · **`password`/`session_data` = "(ไม่แสดง)"**
8. สิทธิ์ **`_is_boss`** เท่ากับสารบัญ/ดาวน์โหลด — แอดมินทั่วไป/เซลล์แอดมิน **403**

**⚠️ บทเรียนตอนทำ (ซ้ำรอยเดิม)**: เขียน patch script ผ่าน **bash heredoc แล้วแบ็กสแลชถูกกิน** —
`\b` ในสตริง regex กลายเป็นอักขระ backspace (0x08) ทำให้ `_WRITE` ไม่มีขอบคำ และมี syntax error ติดไปด้วย
· **ไฟล์ที่มี regex/escape ต้องเขียนด้วย Write tool เท่านั้น** (กฎนี้มีอยู่แล้วในบันทึก — พลาดเพราะมักง่าย)

### 🧾 ล็อกเหตุการณ์ระบบ — [eventlog.py](dashboard/services/eventlog.py) · 16 ก.ย.69 (เจ้าของสั่ง)
*"ล็อกอะไรต่างๆ ก็ควรเก็บไว้ในนี้นะ"*

**ปัญหาเดิม**: ร่องรอยการทำงานถูกเก็บใน `dash_kv` แบบ **"ค่าล่าสุดค่าเดียว"** (ทับทุกครั้ง) —
`line_webhook_last` · `chat_store_last` · `precompute_last` · `sheets_fetch_last` · `cardline_last_*` ·
`profile_fetch_last` → **ย้อนดูไม่ได้ว่าเริ่มพังเมื่อไหร่** · และ **ขาส่งออก LINE ไม่มีล็อกเลย**
(`push_line_message` ยิงแล้วจบ) ซึ่งเป็นต้นเหตุจริงของ 2 เหตุการณ์ที่เคยเกิด:
**รายงานรายวันหยุดส่งเงียบ 2-3 วัน** และ **การ์ดตั้งเวลาส่งไม่ออกทุกใบตั้งแต่ 15/09**

- **`dashboard.EventLog`** (`dash_event_log` · migration **0005**) — 1 แถวต่อเหตุการณ์:
  `at` · `kind` · `name` (ส่งเรื่องอะไร) · `target` · `ok` · `ms` · `detail` (JSON)
- **`eventlog.log(kind, name=…, target=…, ok=…, **detail)`** — **best-effort ทั้งหมด**
  เขียนไม่ได้ (ยังไม่ migrate / DB ล่ม) = ข้ามเงียบ · **ห้ามให้การจดล็อกทำให้งานหลักพัง** (มีเทสต์กันไว้)
- **จดที่ไหนบ้าง** (จดเฉพาะที่ต้องตรวจย้อนหลังได้ ไม่ใช่ทุกอย่าง — ไม่งั้นตารางบวมโดยไม่มีใครใช้):
  - **`line_send` — ทุกการส่งออก LINE ทั้งสำเร็จและล้ม** (สถานะ · คำตอบของ LINE ตอนพลาด · เน็ตล่ม)
    · **ทุกจุดที่เรียกต้องใส่ `what=` บอกว่าส่งเรื่องอะไร** (รายงานรายวัน / การ์ด / ตามด่วน /
    สรุปเบิก-คืนรถ / ฟอร์มไฟแนนซ์ / ตามงานจัดซื้อ) — **ล็อกที่ไม่บอกเรื่อง แทบไม่มีประโยชน์**
    · ครบแล้วทั้ง **13 จุดที่เรียก** (views.py 7 · report_shot.py 3 · lineout.py 2 · notify_purchase 1)
  - **`webhook`** — เฉพาะตอนผิดปกติ (ลายเซ็นไม่ผ่าน / ยิงมาแต่ไม่มี event) · **ปกติไม่จด**
    เพราะข้อความขาเข้าถูกเก็บเป็นแถวใน `checkout_groupchat` อยู่แล้ว จดซ้ำ = บวมเปล่า
  - **`cron`** — งานอุ่นข้อมูลแดชบอร์ดล้ม (อาการ "แดชบอร์ดค้างเป็นสัปดาห์" เคยเกิดแล้ว)
- **อายุข้อมูล `KEEP_DAYS`=90 วัน** — `trim_daily()` เรียกจาก `cron_tick` (กันรันซ้ำเองด้วย KV
  `eventlog_trim_last` วันละครั้ง) · **ล็อกที่ไม่มีวันหมดอายุ = ตารางโตไม่หยุดแล้วไปกินดิสก์**
  (เคยโดนมาแล้วกับรูปรายงาน 1.3 GB ที่ไม่มีใครกวาด)
- **ดูย้อนหลังที่หน้า "ดูข้อมูลดิบ (SQL)"** เช่น
  `SELECT at, name, target, ok, detail FROM dash_event_log WHERE kind='line_send' AND NOT ok ORDER BY at DESC`

**⚠️ สิ่งที่ยัง "ไม่ได้อยู่ในฐานข้อมูลนี้" (ต้องบอกเจ้าของทุกครั้งที่ถามว่าครบหรือยัง)**
- **ข้อมูลการขาย/ลีด/ยอด อยู่ใน Google Sheets** ไม่ได้อยู่ใน Postgres (กล่องเหลืองในหน้าสารบัญเตือนไว้)
- **รูป/วิดีโอ อยู่ใน Google Drive** — ในฐานข้อมูลเก็บแค่ id ที่ชี้ไป
- `dash_kv` ยังเก็บ heartbeat แบบค่าล่าสุดอยู่เหมือนเดิม (หน้าสถานะระบบอ่านตัวนั้น) —
  **ตารางล็อกมาเสริม ไม่ได้มาแทน**

### 💬 หน้าแชทลูกค้า (CRM) — ก.ย.69
เมนูสามขีด → **ลูกค้า & ข้อมูล** → **แชทลูกค้า (LINE OA)** (`openCustomerChat` ใน [index.html](dashboard/templates/dashboard/index.html))
- รายชื่อลูกค้าที่ทักเข้ามา + ค้นหา → **กดที่แถวเพื่อดูบทสนทนาย้อนหลัง** (สูงสุด 100 ข้อความ)
- ข้อความที่ไม่ใช่ตัวอักษรแปลเป็นคำอ่านออก (`[สติกเกอร์]` · `[รูป/ไฟล์ — ตัวไฟล์อยู่ใน LINE…]`) ไม่ใช่ช่องว่าง
- **แยกตามบัญชี OA ที่ได้ยิน** (`byChannel`) — เห็นทันทีว่าลูกค้าเข้ามาทางตัวไหน (รองรับหลาย OA)
- **⚠️★ บทเรียน (เจ้าของแจ้ง "กดลูกค้าและแชท แต่เด้งไปหน้าเบิกรถ")**: เดิมข้อมูลลูกค้าถูกฝังอยู่ใน
  **พาเนลตั้งค่า "⚙️ กลุ่ม LINE" ของหน้าเบิก-คืนรถ** เพราะตอนนั้นทำมาเพื่อดีบักการดักเก็บ ไม่ได้ตั้งใจให้เป็นหน้า CRM
  · พอทำเมนู "ลูกค้า & ข้อมูล" ผมชี้เข้าหน้านั้นเลย → ผู้ใช้กดแล้วไปโผล่หน้างานที่ไม่เกี่ยวกัน
  - **กฎ: ข้อมูลที่คนละบทบาทใช้ อย่าอยู่หน้าเดียวกัน** — ของตั้งค่า (ดักเก็บกลุ่มไหน) กับของงานประจำ
    (ดูลูกค้าคุยอะไร) คนละคนใช้ คนละความถี่ · ตอนนี้แยกเป็น `api_customers` + พาเนลของตัวเอง
    ส่วนสวิตช์ตั้งค่ายังอยู่ที่เดิม แต่ย้ายเมนูไปหมวด **"ตั้งค่าระบบ → ตั้งค่ากลุ่ม LINE ที่ดักเก็บ"**
- **★ ตอบกลับได้แล้ว (ก.ย.69)** — ดู section **"ตอบแชทลูกค้า + เก็บบทสนทนา 2 ฝั่ง"** ด้านล่าง
- **⚠️ ข้อความที่แอดมินตอบจากแอป LINE OA Manager ยังไม่เห็น** — LINE ไม่ส่ง event ขาออก
  ของตัวเองกลับมาทาง webhook · จะได้บทสนทนาครบ 2 ฝั่งก็ต่อเมื่อ **ตอบผ่านหน้านี้** เท่านั้น
  (หน้าเว็บเขียนบอกไว้ตรงๆ กันเข้าใจผิดว่าเห็นครบ)

### 💬 ตอบแชทลูกค้า + เก็บบทสนทนา 2 ฝั่ง — [chat.py](checkout/chat.py) · ก.ย.69 (เจ้าของสั่ง)
*"อยากให้พัฒนาระบบแชทขึ้นมา เอาไว้ตอบแชทของลูกค้าที่เราเก็บใน CRM ไว้ … การที่เราตอบแชทในนี้
จะบอกได้ด้วยว่า admin ตอบลูกค้ายังไงบ้าง และเราสามารถพัฒนา chatbot เองได้ด้วยจากช่องทางของเราเอง"*

- **`GroupChat.direction`** (`in`/`out`) + **`sent_by`** (FK ทะเบียนพนักงาน) + `sent_by_name`
  (migration **0018**) — **เก็บขาออกลงตารางเดียวกับขาเข้า** เพื่อให้อ่านเป็นบทสนทนาต่อเนื่องได้
  · เดิมเก็บแต่ขาเข้า = เห็นแต่ฝั่งลูกค้าพูด **เอาไปสอน chatbot ไม่ได้เพราะไม่มีคู่ถาม-ตอบ**
- **★ เลือกบัญชี OA ตามที่ลูกค้าคุยอยู่จริง** (`_channel_for`) — ไล่จาก **บัญชีที่ได้ยินข้อความ
  ล่าสุดของคนนี้** → บัญชีที่เจอเขาครั้งแรก → ตัวรับ · **push เข้าแชท 1:1 ได้เฉพาะคนที่เพิ่ม
  *บัญชีนั้น* เป็นเพื่อนแล้ว** → เดาบัญชีผิด = LINE ตอบ 400 หรือส่งไม่ถึงแบบเงียบ
  (บทเรียนเดิม: เคยย้าย push ทั้งหมดไปบัญชีใหม่แล้วเกือบทำข้อความตามด่วนหายทั้งทีม)
- **★ ส่งไม่สำเร็จ = ไม่บันทึกลงบทสนทนา** — ถ้าจดตอนล้มด้วย จะมีข้อความที่ลูกค้าไม่เคยได้รับ
  ปนอยู่ แล้วคนอ่านทีหลัง (หรือ chatbot ที่เอาไปเรียน) เข้าใจผิดว่าเราตอบไปแล้ว
  · ที่ล้มไปจดใน `dash_event_log` ผ่าน `push_line_message(what="ตอบแชทลูกค้า")` อยู่แล้ว
- **`_explain()`** แปลคำตอบของ LINE เป็นภาษาคน (`Invalid to` → "ลูกค้าอาจบล็อก/ลบบัญชีนี้
  ออกจากเพื่อนแล้ว") — โยน error ดิบให้แอดมินดูแล้วไม่มีใครรู้ว่าต้องทำอะไรต่อ
- **UI**: พาเนล "แชทลูกค้า (LINE OA)" → กดชื่อลูกค้า → **บับเบิลซ้าย(ลูกค้า)/ขวา(เรา)** +
  ช่องพิมพ์ (`ccBubble`/`ccSend`/`ccBindInput` ใน [index.html](dashboard/templates/dashboard/index.html))
  · **Enter = ส่ง · Shift+Enter = ขึ้นบรรทัด** · ส่งไม่ออก **คงข้อความไว้ในช่อง** ไม่ต้องพิมพ์ใหม่
  · **สิทธิ์ = `_admin`** (ใช้ของเดิม ไม่สร้างระบบสิทธิ์ใหม่ตามที่เจ้าของบอก)
- **★★ สวิตช์ล็อกการส่ง `chat.reply_on()` — ปิดโดยปริยาย** (เจ้าของสั่ง *"อย่าเพิ่งส่งข้อความ
  อะไรหาลูกค้านะ"*) · คีย์ `reply_customer` ใน `checkout_line_config` ·
  **เปิด: `manage.py checkout_config --reply on`** · อ่านค่าไม่ได้ = ถือว่าปิด (fail-safe)
  · ล็อกที่เซิร์ฟเวอร์ **ไม่ใช่แค่ซ่อนปุ่ม** (ยิง API ตรงได้) · หน้าเว็บขึ้นแถบเหลืองบอกวิธีเปิด
  · กติกาเดียวกับ `lineout.send_on()` ที่คุมการโพสต์เข้ากลุ่ม
- **⚠️ `h()` รับเฉพาะสตริง** → ทุกที่ที่ส่งค่าจาก API ต้อง `h(String(v))` ไม่งั้นพาเนลพังทั้งอัน
- ทดสอบแล้ว: ปลอมที่ **`requests.post`** (ขอบระบบ ไม่ปลอมฟังก์ชันเราเอง ตามบทเรียนเดิม) ·
  เลือกบัญชีถูกตัว · ส่งล้มไม่บันทึก · ข้อความว่าง/ยาวเกิน/ไม่รู้จักลูกค้าฟ้องก่อนยิง LINE ·
  **เรนเดอร์ด้วย Chromium จริงแล้ววัดพิกัด** ว่าบับเบิลอยู่ถูกฝั่ง + ข้อความลูกค้าถูก escape (กัน XSS)

### 🚗 ความต้องการลูกค้า (`CustomerNeed`) — "หารถอะไร งบเท่าไหร่" · ก.ย.69
*"เก็บทุกอย่างที่คิดว่าเป็นข้อมูล ทั้งลูกค้าหารถราคาเท่านี้ แท็กลูกค้าคนนี้เป็น lead
แล้วตามต่อว่าเป็น rj เพราะอะไร ถ้าเพราะราคาไม่ถึงก็เก็บไว้รอรถที่ราคาพอดีตามงบ"*

- **1 แถว = ความต้องการ 1 เรื่อง** ผูกกับ `LineProfile` — **ไม่ยัดเป็นฟิลด์ในโปรไฟล์**
  เพราะคนเดียวหารถได้หลายรอบ (รอบนี้ Yaris งบ 3 แสน · อีกสามเดือนมาหากระบะ) ยัดลงโปรไฟล์จะทับกัน
- เก็บ: รุ่นที่หา · ปี · **งบสูงสุด/ต่ำสุด · ผ่อนไหวเดือนละ · ดาวน์ได้** · สถานะ
  (`new`/`lead`/`booked`/`won`/`rj`) · `evidence` (ข้อความที่ใช้สรุป — ไว้ตรวจว่าจับถูกไหม)
- **★ หัวใจอยู่ที่ `reject_kind` + `waiting`** — ปิดเคสเพราะ **ราคา/ไม่มีรถ** ไม่ใช่การเสียลูกค้า
  แต่เป็น **ใบสั่งซื้อที่รอของ** → `mark_reject()` ตั้ง `waiting=True` ให้เอง (`WAITABLE`)
  · ส่วน **เครดิตไม่ผ่าน/ซื้อที่อื่นแล้ว/เงียบไป** = `waiting=False` **ห้ามทักซ้ำ**
  (อย่าให้คนมานั่งจำเองว่าเหตุผลไหนรอได้ — พลาดทีคือไปทักคนที่ซื้อรถไปแล้ว)
- **ยังไม่ได้ทำ (เฟสถัดไป)**: ตัวจับความต้องการจากแชทอัตโนมัติ (Gemini) · จับคู่กับสต็อก
  `cars.Car` แล้วเตือนเซลล์เมื่อรถที่ตรงสเปก/งบเข้ามา · หน้าจัดการในแดชบอร์ด


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

- **★ ที่มา 2 ทาง** (`source`): **`chat`** = [need_extract.py](checkout/need_extract.py) อ่านบทสนทนา
  ลูกค้าด้วย **Gemini** · **`group`** = [leadgroup.py](checkout/leadgroup.py) อ่าน **กลุ่มจ่ายเบอร์**
  ด้วย regex · เคสจากกลุ่มเป็นลูกค้าจาก TikTok/FB ที่ยังไม่เคยทักเข้า LINE OA →
  **`profile` ว่างได้** (migration **0019**) ใช้ `lead_code`+`customer_name` แทน ·
  **ห้ามสร้าง LineProfile ปลอมให้** ไม่งั้นทะเบียนลูกค้าจะเต็มไปด้วยคนที่บอทไม่เคยเห็น
- **ทำไม chat ใช้ AI แต่ group ใช้ regex**: ใบจ่ายลีดเป็นแบบฟอร์มที่ก๊อปเทมเพลตเดิมทุกครั้ง
  โครงคงที่จริง (วัดของจริง 600 ข้อความ: จับรหัสลีด/ช่องทาง/เบอร์ได้ **100%** · คนที่ถูกแท็ก 99%)
  · ส่วนแชทลูกค้าเป็นภาษาพูดอิสระ ("งบ 4 แสน"/"ผ่อนไหวเดือนละแปดพัน") regex เอาไม่อยู่
- **pattern ในกลุ่มจ่ายเบอร์** (สังเคราะห์จากของจริง): ใบจ่ายลีด `Ac Lead No. TLD9-7376` +
  ช่อง Ads/ชื่อ Account/ID LINE/เบอร์/ช่องทาง/รถ + `@เซลล์` · อัปเดต `7364 รอตอบ` ·
  ปิดเคสในห้อง REJECT `6480/1 ได้รถแล้วครับ` · **`7260 สนใจแคมรี่ … ไม่มีรถครับ`**
- **⚠️ ช่อง "รถ" ในใบจ่ายลีดมักว่าง → ตกไปใช้ชื่อโฆษณา (Ads) ซึ่งบางทีก็ไม่ใช่ชื่อรถเลย**
  ("ทำไมคนชลบุรีไม่ซื้อรถผมเลย") → ใช้ได้แต่ติด `confidence=low` · และ **เขียนเฉพาะตอนยังว่าง**
  ห้ามให้ใบจ่ายลีดทับข้อความอัปเดตที่บอกความต้องการจริงละเอียดกว่า
  ("หา city hybrid ปี 23-24 อยากผ่อน 7-8000")
- **`manage.py customer_needs [--analyze|--group|--match] [--dry-run] [--out ไฟล์]`**
  · `--analyze` มี **ลายนิ้วมือบทสนทนา** — ไม่มีข้อความใหม่ = ไม่ยิง Gemini ซ้ำ
  · `--group` รันซ้ำได้ไม่สร้างแถวซ้ำ · **ไม่มีคำสั่งไหนส่งข้อความหาลูกค้า**
- **จับคู่สต็อก** [need_match.py](checkout/need_match.py): เฉพาะรถสเตป **`show`** (พร้อมขายจริง)
  · เกินงบได้ 5% · ตัด "ปี 11-16" ออกก่อนเทียบชื่อรุ่น · ราคาจาก `Car.extra["price_num"]`
  · **คืนผลให้คนของเราตัดสินใจเอง ไม่ทักลูกค้า** · `profile` ว่างได้ (ใช้ `need.who` + เบอร์)
- **⚠️★ 2 บั๊กคุณภาพที่เจอตอนทดสอบกับข้อมูล prod จริง (แก้แล้ว — อย่าให้กลับมา)**
  1. **ตรงแค่ยี่ห้อ = ไม่นับว่าตรงสเปก** — ลูกค้าหา "Toyota Camry" แล้วระบบจับ **Toyota Yaris**
     มาด้วย เพราะคำว่า `toyota` ตรงกับรถโตโยต้าทุกคัน → `_tokens()` แยก **ชื่อรุ่น** ออกจาก
     **ยี่ห้อ** (`_BRANDS`) · ต้องตรงที่ชื่อรุ่น · รู้แค่ยี่ห้อถือว่ากว้างเกิน ไม่เดาให้
  2. **ไม่แกะงบ = เสนอรถเกินงบ** — เคสจริง `TLD9-7106` "ซื้อสดหา city civic **ไม่ข้าม 250000**"
     ระบบเสนอ City **409,000-489,000** เพราะ `budget_max` ว่าง จึงไม่มีตัวกรองราคา
     → **`leadgroup.parse_specs()`** แกะ งบ/ผ่อนไหว/ปี/ชื่อรุ่นไทย จากข้อความที่คนพิมพ์
     ("ไม่ข้าม 250000" · "งบ 3 แสน" · "ปี 23-24" · **"แคมรี่" → camry** ผ่าน `_TH_MODEL`)
     · แยก "ผ่อน 4000" (ต่อเดือน) ออกจาก "งบ 200,000" ด้วยสเกลตัวเลข
     · วัดผลกับ prod: **รถที่เกินงบหลุดมา 2 เคส → 0**
- **พาเนล "ลูกค้าหารถอะไร (รอรถอยู่)"** (`openNeedsPanel` · `?panel=needs` ·
  GET `/checkout/api/needs?waiting=1&match=1`) — แถบเขียว "มีรถตรงสเปกในสต็อกตอนนี้" +
  ปุ่มเปิดแชทลูกค้า · โชว์ `evidence` + ป้าย "⚠ ไม่ค่อยมั่นใจ" เมื่อ AI confidence=low
  **เพื่อให้คนตรวจได้ก่อนเอาไปใช้ตัดสินใจ**
- **ยังไม่ได้ทำ**: cron รันอัตโนมัติ (ตอนนี้สั่งมือ) · เตือนเซลล์เมื่อรถเข้าตรงสเปก ·
  เอาบทสนทนาไปสอน chatbot จริง (ข้อมูลเก็บครบแล้วใน `GroupChat.direction`)

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

#### ⚠️★ 3 บั๊ก "เดือนหายทั้งเดือนแบบเงียบๆ" ในชีตลีด (ส.ค.69 — เจอตอนเจ้าของถามว่าทำไมไม่มีลีดเดือน ก.ย.)
**1. หัวตารางช่องวันที่พังช่องเดียว = เดือนนั้นสูญทั้งเดือน**
- แท็บ "กันยายน 69" มีคนพิมพ์ทับ **A1** จาก `ว/ด/ป` เป็นตัวเลข `46234` (วันที่ในรูป serial)
- `_resolve_lead_colmap` จับคู่ช่องวันที่ไม่ได้ → `_normalize_lead_row` **เคลียร์วันที่เป็นค่าว่างทุกแถว** → ตัวกรอง "วันที่ต้องตรงกับเดือนของแท็บ" ตัดทิ้งหมด → **48 ลีดจริงกลายเป็น 0**
- แก้: `_resolve_lead_colmap(header, sample_rows)` — หาช่องวันที่ไม่เจอจากหัวตาราง ให้ **เดาจากเนื้อข้อมูล** (สแกน 4 คอลัมน์แรก ดูว่าคอลัมน์ไหน parse เป็นวันที่ได้เกินครึ่งของ 20 แถวตัวอย่าง) + log เตือนให้ไปแก้หัวตาราง
- **ช่องวันที่เป็นหัวใจ** (ใช้กรองว่าแถวอยู่เดือนไหน) ต่างจากช่องอื่นที่หายแล้วแค่ field นั้นว่าง

**2. ดึงแท็บพลาดครั้งเดียว = เดือนนั้นหาย + ถูก cache ทับ**
- เดิม `_fetch_tab` ยิงครั้งเดียว ไม่ 200 = คืนลิสต์ว่าง แล้ว `continue` เงียบ → เดือนนั้นหาย **แล้ว cache ผลที่ขาดไว้ 60 วิ + ถูกเขียนลง precompute ต่อ**
- วัดจริงตอนตรวจ: อ่านพลาด 3 แท็บพร้อมกัน (มี.ค./มิ.ย./ก.ค.) — น่าจะโดน Google จำกัดจำนวนครั้ง (อ่าน 9 แท็บพร้อมกัน แต่ละแท็บหลายพันแถว)
- แก้: ลองซ้ำ **3 ครั้งแบบเว้นระยะ** (1s → 3s) · ลดการยิงพร้อมกัน **6 → 3** · **ถ้ายังพลาด = ไม่ cache ผลนั้น** (รอบหน้าลองใหม่) + เก็บ kv `sheets_fetch_last` ให้หน้าสถานะระบบเตือน

**3. ทางสำรอง (fallback ไป "รวม sheet") กลืน error เงียบ**
- `except Exception: return fetch_sheet("leads")` — พอ fallback **ตัวเลขเปลี่ยนไปคนละชุด** (รวม sheet ไม่ครบเดือนใหม่) แต่ไม่มีใครรู้ว่าเกิดอะไรขึ้น
- แก้: log พร้อม traceback + เก็บ `sheets_fetch_last {fallback:true, error}`

#### ⚠️★ ชีตยอดขาย (sales_reports) ก็ header-based แล้ว (ส.ค.69 — เจอตอนเจ้าของแจ้งว่า "คอลัมน์เคลื่อนนิดหน่อย")
**อาการที่เจอจริง (ก่อนแก้)**: แอดมินแทรก 5 คอลัมน์ (อาชีพ/รายได้/อายุงาน/ประวัติผ่อน/อายุ) ไว้**ก่อน**ช่อง "สถานะ" ตั้งแต่แท็บ **เม.ย.69** → ทุกอย่างหลังจากนั้นเลื่อนขวา
- **สถานะ 13 → 18** · **วันนัดเซ็น 14 → 19** · **วันผลออกจริง → 26** · **วันปล่อยรถ 21/22 → 27/28** · เอกสารครบ 18 → 23
- ผลกระทบ: **เม.ย. + พ.ค. หายทั้งเดือน** (ตัวกรอง "สถานะไม่ว่าง" ไปอ่านช่องอาชีพที่ว่าง) · **มิ.ย.-ส.ค. อ่าน "พนักงานบริษัท/ค้าขาย" มาเป็นสถานะ** · วันปล่อยอยู่นอกช่วงที่โค้ดคัดลอก (`range(1,28)`) = **อ่านไม่ได้เลย**
- วัดจริง: ระบบเห็น **595 แถว → 1,076 แถว** หลังแก้ (หายไป 481 เคส)

**วิธีแก้ (แบบเดียวกับชีตลีด)**: `_resolve_sales_colmap(header_row)` + `_SALES_HDR_RULES` + `_SALES_CANON` ([google_sheets.py](dashboard/services/google_sheets.py))
- อ่าน **หัวตารางของแต่ละแท็บ** (แถวถัดจาก marker "ชื่อเซลล์" ตัวแรก) → map ชื่อหัว → ฟิลด์
- **normalize ทุกแถวเข้าตำแหน่ง canonical เดิม** (`SALES_COL`) → โค้ดที่อ่านทั้งระบบไม่ต้องแก้เลย
- ช่องใหม่ 5 ช่องเก็บไว้ท้ายแถว (23-27) ไม่ทิ้งข้อมูล
- **แนบ "ตำแหน่งจริงในชีต" ท้ายแถว** สำหรับเขียนกลับ: **30=วันผล · 31=วันปล่อย · 32=สถานะ · 33=วันเซ็น** (`SALES_IDX_*`)
- `_release_col`/`result_col_for`/`result_date_for`/`extract_release_date`/`release_date_primary` อ่านตัวแนบก่อน → ไม่มีตัวแนบ (แถวจาก `รวม sheet` fallback) ค่อยเดาตามเดือนแบบเดิม
- `booking_cases[]` เพิ่ม **`statusCol`/`signCol`** · frontend ส่งคอลัมน์จริงของแถวนั้นตอนเขียนกลับ (`b.statusCol`/`b.signCol`) + ส่ง `field:'status'` ให้เซิร์ฟเวอร์ตรวจชนิดค่าแทนการเดาจากเลขคอลัมน์
- `update_release_date` **เลิก whitelist ตำแหน่งตายตัว** (เดิม `(2,13,14,18,19,20,21,23)` → คอลัมน์ใหม่จะถูกปฏิเสธหมด) เหลือตรวจช่วง 0-40 + ตรวจชนิดค่าตาม `field`
- **ยืนยันความถูกต้อง**: ปล่อย ม.ค.-พ.ค. = **44/43/50/43/52 ตรงกับสูตรในชีตเป๊ะ** · มิ.ย.-ส.ค. = 52/48/43
- **⚠️ ผลข้างเคียงที่ต้องรู้**: เดิม `extract_release_date` ไล่เดา 4 คอลัมน์แล้วดึงวันที่จากโน้ตมาด้วย · ตอนนี้อ่านช่อง "วันที่ปล่อยรถ" ตรงๆ → **เคสที่แอดมินไม่ได้กรอกวันปล่อยจะโผล่ในกระดิ่งแจ้งเตือนมากขึ้น** (ถูกต้องแล้ว — ของเดิมกลบปัญหาไว้)
- **เพิ่ม/เปลี่ยนชื่อหัวคอลัมน์ในชีต = เติม alias ใน `_SALES_HDR_RULES` จุดเดียว**

#### ⚠️ Header-based column mapping (สำคัญ — แต่ละเดือน layout ไม่เหมือนกัน!)
ตั้งแต่ มิ.ย.69 ชีต lead จัดคอลัมน์ใหม่ (U–Y กลายเป็น อาชีพ/รายได้/อายุงาน/ประวัติผ่อน/ประเภทลูกค้า, สถานะหลักย้ายมา **Z "สถานะลูกค้า"**, Status แอดมิน เลื่อนไป AB). เดือนเก่า (ม.ค.–พ.ค.) ยัง layout เดิม → **คอลัมน์ต่างกันต่อ tab**
- **ห้าม fix ตำแหน่งคอลัมน์ตายตัวอีก** — `fetch_leads_by_month_tabs()` อ่าน header แต่ละ tab แล้ว `_resolve_lead_colmap()` จับคู่ field กับ "ชื่อหัวตาราง" (alias ใน `_LEAD_FIELD_ALIASES`) → `_normalize_lead_row()` จัดทุกแถวให้อยู่ canonical `LEADS_COL` เหมือนกันหมด ก่อนส่งต่อ
- field ที่หา header ไม่เจอ = **เคลียร์ว่าง** (กันค่าคอลัมน์อื่นปนแล้วอ่านผิด เช่น "อัพเดทเคส...ดึงคืน" ไปโผล่ sales_status แล้ว match keyword "คืน")
- `LEADS_COL.customer_status = 33` (canonical slot ใหม่สำหรับคอลัม Z) — `admin_status=26`, `sales_status=28` ยังเป็น canonical เดิม (normalize ยัดค่าจาก source ที่ถูกต้องมาให้)
- เพิ่ม alias เมื่อชีตเปลี่ยนชื่อหัวคอลัมน์: แก้แค่ `_LEAD_FIELD_ALIASES` ใน [google_sheets.py](dashboard/services/google_sheets.py)
- **★ overlay สถานะล่าสุดข้ามแท็บ — Z + AB(admin_status) + เซลล์(sales_status) (มิ.ย.69)**: เคสเก่า (วันที่เดือนก่อน เช่น 25/5) ถูกเอามาทำต่อในแท็บปัจจุบัน (แอดมินอัปเดต Z/AB) แต่ date-filter เก็บ copy เดือนเก่า (อิง received_date) → **สถานะที่อัปเดต (จ่ายใหม่/คืนเคส/จอง) อยู่ในแท็บใหม่ แต่ row ที่ใช้คือสำเนาเดือนเก่าที่ยังเป็นค่าเดิม** → ตามผิด/นับผิด (เคส HLD-9959/ANLD-9921 · **TLD-10187**: received 28/5 → ใช้สำเนา พ.ค.(admin=ติดตาม) แต่แอดมินใส่ "จ่ายใหม่" ใน AB แท็บ มิ.ย. → ถ้า overlay แค่ Z จะหลุดมาโดนตาม). `fetch_leads_by_month_tabs` รวบ **ค่าล่าสุด (เดือนสูงสุดที่กรอก) ของ Z+admin_status+sales_status** ต่อ `lead_code` มา **overlay** ทับ row ที่เก็บไว้ (ดู `_OVERLAY_FIELDS` · การนับเดือนยังอิงวันที่เดิม — overlay แค่สถานะ) · **กระทบทุกที่ที่อ่าน leads (dashboard/seller/followup)** — admin_status overlay ทำให้ตัวเลขที่อิง admin (จอง/ติดตาม/junk) สะท้อนแท็บล่าสุดด้วย (ถูกต้องขึ้น แต่บางเลขขยับ)
- **เขียนกลับคอลัม S**: `update_lead_fill_note(code, value, month, expected_seller)` — หา source col ของ fill_sheet_note/lead_code จาก header (รองรับทุก layout), หาแถวจาก Code, PATCH cell เดียว, ตรวจ ownership เซลล์

## LINE Integration

### Channel Access Token — ★ ก.ย.69 แยกเป็น **2 บัญชี** (เจ้าของสั่ง)
```
LINE_CHANNEL_ACCESS_TOKEN=xxx        # ตัวรับ/CRM — ลูกค้าทักเข้ามา · เก็บแชท/โปรไฟล์ · รับ webhook
LINE_CHANNEL_SECRET=xxx              # ลายเซ็น webhook ของตัวรับ
LINE_PUSH_CHANNEL_ACCESS_TOKEN=xxx   # ตัวส่ง — โพสต์เข้ากลุ่มงาน (รายงาน/ตามด่วน/สรุปเบิก-คืน)
LINE_PUSH_CHANNEL_SECRET=xxx         # ลายเซ็น webhook ของตัวส่ง (ตั้งเมื่อให้ตัวส่งยิง webhook มาด้วย)
CRON_SECRET=xxx
```
- **ทุกจุดในโค้ดต้องเรียกผ่าน [line_channels.py](dashboard/services/line_channels.py) เท่านั้น** —
  `push_token()` (ส่ง) · `crm_token()` (รับ/โปรไฟล์ลูกค้า) · `group_tokens()` (งานระดับกลุ่ม) · `secrets()` (ลายเซ็น)
  · **ห้ามอ่าน `settings.LINE_CHANNEL_ACCESS_TOKEN` ตรงๆ** ไม่งั้นพอสลับบัญชีจะมีจุดตกค้างแล้วหาไม่เจอ
- **ยังไม่ตั้งตัวส่ง = ตกไปใช้ token ตัวรับทุกอย่าง** → เอาโค้ดขึ้นก่อน ค่อยเอาบัญชีใหม่มาลงทีหลังได้
- **⚠️ token ผูกกับ "ความสัมพันธ์" ไม่ใช่แค่สิทธิ์**: ดึงโปรไฟล์ได้เฉพาะคนที่เพิ่ม*บัญชีนั้น*เป็นเพื่อน ·
  push / ดึงชื่อกลุ่มได้เฉพาะกลุ่มที่*บัญชีนั้น*เป็นสมาชิก → งานระดับกลุ่ม (`_store_line_groups`,
  `admin_line_group_name`, `people.fetch_profile`) **ลองทีละ token** ไม่เดาตัวเดียว ไม่งั้นได้ 403/404 แบบงงๆ
- **ตรวจลายเซ็น webhook รับได้ทั้ง 2 บัญชี** (`line_webhook` วน `secrets()`) — เช็คตัวเดียว = บัญชีใหม่ยิงมาแล้วโดน 403
- **⚠️★ บั๊กที่แก้ไปพร้อมกัน: `LINE_CHANNEL_SECRET` ไม่เคยถูกประกาศใน settings.py** ทั้งที่ `line_webhook`
  อ่านผ่าน `getattr` → คืน `""` เสมอ = **ข้ามการตรวจลายเซ็นมาตลอด** (ใครก็ยิง `/api/line/webhook` ได้) ·
  ประกาศแล้ว → ตั้งค่าใน .env เมื่อไหร่การตรวจเริ่มทำงานทันที
- **`manage.py line_accounts [--offline] [--groups] [--out ไฟล์]`** — ถาม LINE ว่า token แต่ละช่องเป็นของ
  **บัญชีชื่ออะไร** (`/v2/bot/info`) + `--groups` บอกว่าบัญชีไหนอยู่ในกลุ่มไหน · ใช้ยืนยันว่า "วางคีย์ถูกช่อง"
  โดยไม่ต้องส่งข้อความจริงเข้ากลุ่ม · เตือนด้วยถ้ายังไม่ได้ตั้ง secret เลย
- **★ เลือกบัญชีตาม "ปลายทาง" ไม่ใช่ตามชนิดงาน** — `token_for(target_id)`: id ของ LINE บอกชนิดที่ตัวแรก
  **C…=กลุ่ม · R…=ห้อง → บัญชีตัวส่ง** · **U…=คน (1:1) → `dm_token()`**
  - **⚠️ บทเรียน (ก.ย.69 · regression ที่เกือบทำข้อความตามด่วนหายทั้งทีม)**: ตอนแรกย้าย "ทุกการ push"
    ไปบัญชีตัวส่งรวดเดียว → ลืมว่า **LINE ส่งเข้าแชท 1:1 ได้เฉพาะคนที่เพิ่มบัญชีนั้นเป็นเพื่อนแล้ว** ·
    เซลล์ 14 คนเพิ่มไว้แต่บัญชีเดิม (วัดจริง: followup ส่ง 23 ข้อความ/รอบ เปิดอยู่ 09:00+13:00)
    → ถ้าปล่อยไว้ รอบถัดไปจะล้มทั้งทีม **แบบเงียบ** เพราะยังไม่มี log ขาส่ง
  - `dm_token()` default = **บัญชีตัวรับ (เดิม)** → ย้ายเมื่อทุกคนเพิ่มบัญชีใหม่เป็นเพื่อนครบแล้ว
    ด้วย **`LINE_DM_CHANNEL=push`** ใน .env (ไม่ต้องแก้โค้ด) · `line_accounts` บอกว่าตอนนี้ 1:1 ออกจากบัญชีไหน
  - **รายงานรายวันส่งได้ทั้ง 2 แบบ** (mode=group → C… · mode=test → test_id ซึ่งเป็น U…) จึงต้องใช้
    `token_for()` ทุกจุดที่ push ไม่ใช่เลือก token ไว้ล่วงหน้าตอนต้นฟังก์ชัน
- **★★★ 20 ก.ย.69 — แบ่งหน้าที่ 2 บัญชีให้ขาด (เจ้าของกำหนด)**
  *"เราแบ่งแยก LINE OA ชัดเจนแล้ว · ตัว OxletAuto ใช้แค่เก็บข้อมูลของลูกค้า · บอทจริงๆ ที่ใช้ส่งคือ OxletautoGiveLead"*
  | บัญชี | หน้าที่ |
  |---|---|
  | **OxletAuto** (`crm`) | **รับอย่างเดียว** — ลูกค้าทักเข้ามา · เก็บแชท/โปรไฟล์ · รับ webhook |
  | **OxletautoGiveLead** (`push`) | **ส่งทุกอย่าง** — กลุ่มงาน **และแชท 1:1** (ตามด่วน/เช็คชื่อ/รายงาน/การ์ด) |
  - **`dm_token()` ค่าเริ่มต้นเปลี่ยนเป็นบัญชีตัวส่งแล้ว** (เดิมเป็นตัวรับ) · กลับของเดิมชั่วคราวด้วย `LINE_DM_CHANNEL=crm`
  - **★ ข้อยกเว้นที่เจ้าของสั่งไว้ — "ตามด่วน" 2 ตัวนี้ **ไม่ย้าย** ใช้บัญชีเดิม**
    (`ตามด่วน (cron ตามตารางส่ง)` · `ตามด่วน (สรุปทีมให้แอดมิน)` · รวมปุ่มส่งทันที)
    · ทีมเพิ่มบัญชีเดิมเป็นเพื่อนไว้แล้ว **และส่งได้ดีทุกวัน** (วัดจริง 7 วัน: สำเร็จ 112 + 72 ครั้ง ไม่เคยล้ม)
      → ย้าย = เสี่ยงหายทั้งทีมโดยไม่ได้อะไรเพิ่ม
    · บังคับผ่าน **`followup_token()`** ([line_channels.py](dashboard/services/line_channels.py)) +
      **`_fu_tok()`** ([views.py](dashboard/views.py)) — **ห้ามเปลี่ยน 3 จุดนี้กลับไปใช้ `_tok()`**
      ไม่งั้นจะโดนนโยบายรวมลากไปบัญชีใหม่โดยไม่ตั้งใจ · จะย้ายจริงค่อยแก้ที่ `followup_token()` ที่เดียว
  - **★★ 24 ก.ย.69 — ยกเลิกบัญชีเก่าในขาส่งทั้งหมด** (เจ้าของสั่ง *"การแจ้งเตือนจะยกเลิก
    การใช้ [บัญชีเก่า] ไปเลย จะใช้เป็นบัญชี OxletautoGiveLead"*)
    · **`followup_token()` คืน `dm_token()` แล้ว** — ข้อยกเว้น "ตามด่วนใช้บัญชีเดิม" ถูกยกเลิก
    · **ถอดตัวสำรอง "ส่งซ้ำด้วยบัญชีตัวรับ" ใน `push_line_message()` ออก** —
      มันทำให้ข้อความไปโผล่ในนามบัญชีที่เลิกใช้แล้ว โดยคนรับไม่รู้ว่าทำไม
      (เหตุการณ์จริง 24/09: ตารางเช็คชื่อที่เจ้าของสั่งส่ง → ตัวส่งล้ม → สำรองส่งจาก OxletAuto)
    · **วัดก่อนตัด**: 7 วัน ตัวสำรองถูกใช้ **1 ครั้ง** (ของเจ้าของเอง) = ไม่มีใครพึ่งมันอยู่
      · คนที่ได้ตามด่วน 18 คน — มีไอดีฝั่งบอทใหม่แล้ว **16** · ยังไม่มี **2** (หนึ่งในนั้นคือเจ้าของ)
    · **ส่งไม่ถึง = ไม่ถึงจริงๆ แล้วจดล็อก** — แก้ด้วยการให้คนนั้น **แอดบอทตัวส่งเป็นเพื่อน**
      ไม่ใช่แอบส่งด้วยบัญชีอื่น · ไล่ว่าใครยังไม่ได้แอด:
      `SELECT target, name FROM dash_event_log WHERE kind='line_send' AND NOT ok ORDER BY at DESC`
    · ย้อนกลับทั้งระบบชั่วคราว: `LINE_DM_CHANNEL=crm` ใน .env
  - **⚠️ ข้อจำกัดที่ยังอยู่**: LINE ส่งเข้า **แชท 1:1** ได้เฉพาะคนที่ **เพิ่มบัญชีนั้นเป็นเพื่อนแล้ว**
    → ระหว่างที่พนักงานยังเพิ่มบอทใหม่ไม่ครบ มี **ตัวสำรองใน `push_line_message()`**:
    ส่งด้วยตัวส่งไม่สำเร็จ **และปลายทางเป็นคน (U…)** = ลองซ้ำด้วยบัญชีตัวรับ 1 ครั้ง
    · ล็อกจะมี 2 แถว แถวที่สองชื่อ **"… (บัญชีตัวส่งไม่ถึง ใช้ตัวรับสำรอง)"** → **ใช้ไล่ว่าใครยังไม่ได้เพิ่มบอทใหม่**:
    `SELECT target, count(*) FROM dash_event_log WHERE name LIKE '%ใช้ตัวรับสำรอง%' GROUP BY 1`
    · **ไม่ทำกับกลุ่ม (C…)** — กลุ่มที่บอทตัวส่งเข้าไม่ได้ ต้องไปเชิญบอท ไม่ใช่แอบส่งด้วยบัญชีอื่น
  - **ถอดตัวสำรองเมื่อไหร่**: ล็อกไม่มีแถว "ใช้ตัวรับสำรอง" ติดกันหลายวัน = ทุกคนเพิ่มครบแล้ว
- **★★ LINE user id ผูกกับ "provider" ไม่ใช่ค่าสากล — เรื่องใหญ่ที่สุดของการมีหลายบอท**
  - คนเดียวกันคุยกับบอท 2 ตัว: **provider เดียวกัน → ได้ `userId` ตัวเดียวกัน** (ข้อมูลรวมเป็นคนเดียวอัตโนมัติ) ·
    **คนละ provider → ได้ `userId` คนละตัว** → กลายเป็น **2 คนในระบบ และรวมเองไม่ได้** (ไม่มีข้อมูลอะไรบอกว่าเป็นคนเดียวกัน)
  - **ก่อนเปิดใช้จริงต้องเช็คใน LINE Developers Console ว่า 2 channel อยู่ใต้ Provider เดียวกันไหม** ·
    **ย้าย channel ข้าม provider ไม่ได้** → ถ้าคนละ provider ต้องยอมรับว่าข้อมูลลูกค้าแยกกันถาวร
  - รองรับไว้แล้ว (migration **0011**): `GroupChat.channel` = บัญชีที่ได้ยินข้อความนี้ ·
    `LineProfile.channel` (เจอครั้งแรกจากบัญชีไหน) + `LineProfile.channels` (เคยเห็นจากบัญชีไหนบ้าง) →
    เห็นทันทีว่าเริ่มนับลูกค้าซ้ำหรือยัง (`_profile_counts().byChannel` · `checkout_status` ข้อ 5.5)
  - **`channel_of(destination)`** — LINE ใส่ `destination` (= userId ของตัวบอท) มาใน webhook body อยู่แล้ว →
    เทียบกับ `bot_info()["userId"]` ของแต่ละ token ก็รู้ว่า event มาจากบัญชีไหน · **จำเป็นเพราะ n8n forward
    ทั้ง 2 บัญชีมาที่ endpoint เดียวกัน** — ไม่รู้ = ดึงโปรไฟล์ด้วย token ผิดตัว (404) และแยกข้อมูลไม่ออก
  - **⚠️ `_unwrap_payload` ที่แกะ "event เดี่ยว" ทำ `destination` หาย** → `channel` เป็นค่าว่าง (ไม่เดามั่ว) ·
    ยังเก็บข้อความได้ปกติ แต่จะไม่รู้ว่ามาจากบัญชีไหน → **ถ้าอยากได้ครบ n8n ต้อง forward body ดิบทั้งก้อน**
  - `touch_profile(channel=…)` / `fetch_profile(channel=…)` ลอง token ของบัญชีที่ได้ยินก่อนเสมอ
- **★★ ก.ย.69 — รองรับ LINE OA "กี่ตัวก็ได้" (เจ้าของแจ้งว่าต่อไปจะมีหลายตัว)**
  - เดิม [line_channels.py](dashboard/services/line_channels.py) ฮาร์ดโค้ดไว้ **2 บทบาท** (`crm`/`push`)
    → ตอนนี้เป็น **ทะเบียนบัญชี** `accounts()` · เพิ่มตัวที่ 3 เป็นต้นไปใน `.env` แล้ว restart **ไม่ต้องแก้โค้ด**:
    ```
    LINE_OA_SHOP2_TOKEN=...      # คีย์บัญชี = "shop2"
    LINE_OA_SHOP2_SECRET=...     # ลายเซ็น webhook ของบัญชีนั้น
    LINE_OA_SHOP2_NAME=สาขา 2    # ชื่อที่คนอ่านออก (ไม่ใส่ = ดึงจาก LINE)
    ```
  - `secrets()` · `channel_of()` · `group_tokens()` · `describe()` วน **ทุกบัญชี** แล้ว ·
    `token_of(key)` รับคีย์อะไรก็ได้ (ไม่รู้จัก → ตกไปตัวรับ เหมือนเดิม) · ของเดิม 2 บัญชีทำงานเหมือนเดิมเป๊ะ
  - **token อยู่ใน env ไม่เก็บลง DB** — ถึงจะเพิ่มผ่านหน้าเว็บได้สะดวกกว่า แต่ token = สิทธิ์ส่งข้อความ
    ในนามบริษัท หลุดจาก DB/ไฟล์ export เมื่อไหร่ = ใครก็ปลอมเป็นเราได้
  - `GroupChat.channel` / `LineProfile.channel` ขยาย 8 → **24 ตัวอักษร** (migration **0012**) เพราะคีย์บัญชี
    ไม่ใช่แค่ `crm`/`push` แล้ว
  - **⛔ ตั้ง channel secret "บางบัญชี" อันตรายกว่าไม่ตั้งเลย** — `line_webhook` เริ่มตรวจลายเซ็นทันทีที่มี
    secret สักตัว → event ของบัญชีที่ยังไม่ตั้งโดน 403 ทั้งหมด (ถ้ายิง webhook ตรง ไม่ผ่าน n8n) ·
    `line_accounts` เตือนพร้อมบอกว่าขาดตัวไหน
- **★★ ก.ย.69 — สรุปเรื่อง Provider (เจ้าของถามละเอียด · ตอบไปแล้ว บันทึกกันลืม)**
  - โครงสร้าง: **Provider → หลาย channel** (Messaging API หลายตัว = หลาย OA + LINE Login channel) ·
    **provider เดียวใส่ OA ได้หลายตัว** เป็นเรื่องปกติที่ LINE ออกแบบมา
  - **userId ออกต่อ provider** → OA หลายตัวใต้ provider เดียวกัน = ลูกค้าคนเดียวได้ id เดียวกัน **รวมอัตโนมัติ** ·
    คนละ provider = คนละ id **รวมเองไม่ได้** (LINE ตั้งใจแยกเพื่อความเป็นส่วนตัว ไม่ใช่ข้อจำกัดทางเทคนิค)
  - **ย้าย channel ข้าม provider ไม่ได้ · รวม provider ไม่ได้** → ทางเดียวคือสร้างใหม่ = OA เริ่มนับหนึ่ง
    (เพื่อน/ประวัติ/แพ็กเกจที่จ่ายไม่ย้ายตาม)
  - **จุดที่คนพลาด**: ตอนเปิด Messaging API ครั้งแรก LINE ถามว่าจะผูก provider ไหน + มีปุ่ม "สร้างใหม่" →
    กดสร้างใหม่ทุกครั้ง = OA ละ provider โดยไม่รู้ตัว (เกิดกับ `@zpb0787e` กับ `@693tyhah` แล้ว)
  - **สถานะจริง ก.ย.69: 2 OA อยู่คนละ provider และจ่ายเงินไปแล้ว → ตัดสินใจ "ไม่รื้อ"**
    เพราะ `@693tyhah` **ไม่ได้รับแชทลูกค้า 1:1 เลย** (เป็นบอทส่งเข้ากลุ่ม) → ไม่มีลูกค้าให้ซ้ำ = ไม่กระทบ
  - **กฎสำหรับ OA ตัวถัดไป**: ตัวไหนที่ **ลูกค้าจะทักเข้ามา** ต้องสร้างใต้ provider เดียวกับ `@zpb0787e`
    (เลือกตอนสร้าง ฟรี) · ตัวที่เป็นบอทส่งอย่างเดียวอยู่ provider ไหนก็ได้
  - **⚠️ ต้องเช็คด้วย**: **LINE Login channel** อยู่ provider เดียวกับ OA ที่เก็บ CRM ไหม — ถ้าไม่ใช่
    `userId` ตอนพนักงาน login **จะไม่ตรง**กับที่เก็บในตารางแชท → จับคู่ "คนที่ login" กับ "คนที่ตอบแชท" ไม่ได้
    (จำเป็นตอนทำ "วัด performance แอดมิน")
- **`python manage.py line_group_add [--file g.json] [--id C… --name "…"] [--dry-run] [--out ไฟล์]`**
  ([line_group_add.py](dashboard/management/commands/line_group_add.py)) — ลงทะเบียนกลุ่มด้วยมือ ไม่ต้องรอ webhook
  - จำเป็นเพราะ **กลุ่มจะเข้าระบบเองตอนมีข้อความจากกลุ่มนั้นวิ่งมาเท่านั้น** — กลุ่มที่มีแต่บอทตัวใหม่
    (ซึ่งยังไม่มีโหนด n8n ส่งชื่อกลุ่มมา) จะไม่โผล่เลย → เอา group id มาใส่ตรงๆ ก่อนได้
  - รับ JSON ที่ก๊อปจาก n8n ได้เลย รวมถึง **หลายก้อนวางต่อกัน** (`[{...}]` ตามด้วย `[{...}]`) · ไม่เก็บ `pictureUrl`
  - **ถาม LINE ยืนยันว่าบัญชีไหนอยู่ในกลุ่มนั้นจริง แล้วจดลง `line_groups[gid].channels`** —
    ลงทะเบียนมือไม่มี `destination` ให้ดู ถ้าไม่ยืนยันจะไม่รู้ว่าสั่ง push เข้ากลุ่มไหนได้
- **`line_groups` KV เก็บเพิ่ม** `channels` (บัญชีไหนอยู่ในกลุ่มนี้) + `source` (`webhook`/`manual`) ·
  `_store_line_groups(pairs, channel=…, source=…)` — ทาง webhook เติม channel จาก `destination` ให้เอง
- **📄 สัญญาเชื่อมต่อฝั่ง n8n: [deploy/n8n_line_contract.md](deploy/n8n_line_contract.md)** — เอกสารส่งมอบ
  **ฝั่งรับเป็นคนกำหนดรูปแบบ ไม่ใช่ฝั่งส่ง** (เจ้าของฐานข้อมูลเป็นคนกำหนด ไม่งั้นมี schema 2 ชุดให้ดูแล)
  - กฎข้อเดียว: **ส่ง body ดิบของ LINE ทั้งก้อน ห้ามแปลง** · มีตารางบอกว่าฟิลด์ไหนหายแล้วพังยังไง
  - **Webhook node ต้องตั้ง `Respond: Immediately`** — ห้ามรอผลจาก HTTP node ก่อนตอบ
    LINE รอ response แป๊บเดียวแล้ว retry → ตั้งผิดจะได้ event ซ้ำรัวๆ · LINE ไม่อ่าน body ที่ตอบกลับ ขอแค่ 200
  - **2 channel ชี้มา URL เดียวกันได้** ไม่ต้องแยก node — ฝั่งเราแยกเองจาก `destination`
  - อธิบาย response ที่เราตอบกลับทีละฟิลด์ + ตารางอ่านผล (`events: 0` = body ไม่ถูกส่งมา ฯลฯ)
- **★ ทางเข้าข้อมูลมีทางเดียว: n8n** (เจ้าของกำหนด ก.ย.69) — *"คุณมีหน้าที่รับข้อมูลจาก N8N เท่านั้น"* ·
  **ห้ามเพิ่มทางรับใหม่** · บัญชีใหม่จะส่ง event เข้ามาก็ต้องผ่าน n8n → `/api/line/group_ingest` เหมือนกัน
  (โหนดเดิมใช้ได้เลย ไม่ต้องแก้ — body ดิบมี `destination` ติดมาอยู่แล้ว)
- **★★ 16 ก.ย.69 — ย้าย push เข้ากลุ่ม "ทั้งระบบ" ไป OxletautoGiveLead (`@693tyhah` · เจ้าของสั่ง)**
  - **group id ก็ออกต่อ provider เหมือน user id** — กลุ่มเดียวกันมี id คนละตัวในสายตาบอทแต่ละตัว
    (วัดจริง: "ทีมAdmin" = `C053bbf5…` ในบอทเดิม · `C9412426…` ในบอทใหม่)
  - **⚠️ บั๊กที่เจอตอนย้าย**: โค้ด push เข้ากลุ่มด้วยบัญชีตัวส่งอยู่แล้ว (`token_for`) แต่ปลายทางที่บันทึกไว้
    (`cardline_*`, `checkout_line_config`) เป็น id ของบอทเดิม → **การ์ดตั้งเวลาทุกใบส่งไม่ออก**
    (`cardline_last_*` = LINE 400 "Failed to send messages" · 15/09) · ร่องรอยอยู่ใน KV เท่านั้น ไม่มีใครเห็น
  - **`python manage.py line_push_switch [--apply] [--out ไฟล์]`**
    ([line_push_switch.py](dashboard/management/commands/line_push_switch.py)) — ไล่ทุกปลายทางกลุ่ม
    (การ์ดทุกใบ · รายงานรายวัน · กลุ่มเบิก-คืนรถ) → บอทใหม่อยู่แล้ว = ไม่แตะ · ไม่อยู่ = หาชื่อกลุ่มจากบอทเดิม
    แล้วหา id ฝั่งบอทใหม่ที่ชื่อตรง **และถาม LINE ยืนยันซ้ำ** · หาไม่เจอ/ชื่อซ้ำ = ไม่แตะ บอกว่าต้องเชิญบอทเข้ากลุ่มไหน
    · หาชื่อกลุ่มจาก LINE → ทะเบียน → **คลังแชท `GroupChat.group_name`** (บอทเดิมออกจากกลุ่มแล้ว + ทะเบียนเคยทำกลุ่มหาย)
    · **ไม่ใส่ `--apply` = ดูเฉยๆ** · ไม่แตะ test id (U…) · รายงาน `.env LINE_GROUP_ID` ของระบบรถให้ด้วย (แก้เองเท่านั้น)
  - **กันกลับมาอีก 2 ชั้น** ([line_channels.py](dashboard/services/line_channels.py)):
    `push_group_error()` — ตอน **เปลี่ยน** group id ในหน้าตั้งค่า (การ์ด/รายงาน/เบิก-คืน) ถาม LINE ว่าบอทตัวส่งอยู่ในกลุ่มไหม
    ยืนยันว่าไม่อยู่ = บันทึกไม่ได้ (400) · ถามไม่ได้ = ปล่อยผ่าน ·
    `group_visible_to_push()` — dropdown เลือกกลุ่ม **ซ่อน id ที่มีแต่บอทตัวรับได้ยิน** (`/api/admin/line_groups?all=1` = ดูทั้งหมด)
  - **แท็กคนในสรุปเบิก-คืนผ่านบอทใหม่ไม่ได้** (user id คนละ provider) → `lineout._push` ส่งซ้ำแบบไม่แท็กเมื่อ LINE ปฏิเสธ
  - **`_store_line_groups` อ่านทะเบียนใหม่ก่อนเขียน** แล้วทับเฉพาะกลุ่มที่อัปเดต — เดิมเขียนทั้งก้อนที่อ่านไว้ตั้งแต่ต้น
    (ระหว่างนั้นรอ LINE หลายวินาที) → request อื่นโดนทับ **กลุ่มหายจากทะเบียน** (เจอจริง 16/09)
  - **ยังไม่ย้าย (ตั้งใจ)**: แชท 1:1 ตามด่วนรายเซลล์ (`dm_token` · ต้องให้ทุกคนเพิ่มบอทใหม่เป็นเพื่อนก่อน)
- **LINE Login เป็นคนละ channel** (`LINE_LOGIN_CHANNEL_ID/SECRET`) — ไม่เกี่ยวกับ 2 บัญชีนี้
- **`LINE_CHANNEL_TOKEN`/`LINE_GROUP_ID`** ([cars/line.py](cars/line.py) · push สเตปรถ) ยังเป็นช่องแยกของเดิม
  **ตั้งใจไม่ผูกเข้า resolver** — ไม่ตั้ง = no-op เงียบอยู่แล้ว ถ้าผูกจะกลายเป็นเปิดการส่งที่ไม่มีใครสั่งเปิด
- พาเนล "⚙️ กลุ่ม LINE" เตือนเมื่อติ๊ก "ให้บอทโพสต์" แต่ยังไม่มี token ตัวส่ง / ยังไม่ได้แยกบัญชี ·
  `admin_system_health` คืน `lineAccounts` (2 = แยกแล้ว)

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

## Meta (Facebook) API — ★ แยก 2 บริษัทให้ขาด (ก.ย.69 · เจ้าของสั่ง)
*"ตอนนี้ฉันทำงานอยู่สองบริษัท ซึ่งฉันต้องจัดการแยกกัน มันไม่ควรไปรวมกัน"*

**ปัญหาราก (ไม่ใช่บั๊กเรา แก้ที่ token ไม่ได้)**: token ของ Meta ออกในนาม **โปรไฟล์ Facebook ของคน**
ไม่ใช่ในนามบริษัท → `/me/adaccounts` คืน *ทุก* บัญชีที่คนนั้นแตะได้ **ข้ามบริษัท**
- วัดจริง: token เห็น 4 บัญชี — ของเรา 2 · บัญชีส่วนตัว 1 · **OSUKA 1 (คนละบริษัท ขายเลื่อยยนต์
  ใช้เงินสะสม 5,002,970 บาท · 7 วัน 493,637)** เพราะโปรไฟล์เจ้าของถูกเพิ่มเป็นผู้ใช้บนบัญชีนั้นโดยตรง
  (บัญชีนั้น **ไม่ได้อยู่ใน BM ของเรา** ทั้ง owned และ client)
- **ทดสอบ token 3 ตัว เห็น OSUKA ทุกตัว** → ออกใหม่ไม่ช่วย สิทธิ์ผูกกับตัวคน
- บ้านเราสะอาด: BM "ธุรกิจของ อ๊อกเล็ตธ์ ออโต้" มีคนเดียว (เจ้าของ ADMIN) · agency 0 · client 0
  → **ไม่มีใครจากฝั่ง OSUKA เห็นของเรา** เป็นทางเดียว

### ทางแก้ = ด่านฝั่งเรา [meta.py](dashboard/services/meta.py)
- **`META_AD_ACCOUNTS` / `META_PAGE_IDS`** (env · คั่น comma) = asset ของบริษัทนี้
  · **★ ไม่ตั้ง = ปิดสนิท** (แบบเดียวกับ `EXTERNAL_API_KEY`) — เปิดโดยปริยายวันหนึ่งข้อมูล
  บริษัทอื่นจะไหลเข้าแดชบอร์ดนี้แบบไม่มีใครรู้ แล้วตัวเลขเพี้ยนโดยหาต้นตอไม่เจอ
- **ทุกคำขอผ่าน `meta.get(path)`** ซึ่งเช็ค id ปลายทางก่อน **แล้วค่อยยิงออกเน็ต**
  (มีเทสต์ยืนยันว่า `requests.get` ไม่ถูกเรียกเลยตอนบล็อก) · ไม่ผ่าน = `ForeignAsset`
- **★ `/me/*` ถูกห้ามในโค้ดใช้งานจริง** (`/me`, `/me/adaccounts`, `/me/accounts`, `/me/businesses`)
  — พวกนี้เหวี่ยงข้ามบริษัททุกครั้ง · ดูได้ที่เดียวคือ **`meta.audit()`** ที่มีไว้ "ตรวจ" ไม่ใช่ "ใช้งาน"
- **`_known` — ทะเบียน id ลูก**: post/video/ad id เป็นเลขล้วนเหมือนกันหมด แยกด้วยตาไม่ได้
  → เก็บ id ที่ **โผล่จากคำตอบของคำขอที่ผ่านด่านแล้ว** (`_harvest`) แล้วอนุญาตเฉพาะพวกนั้น
  · ปลอดภัยกว่าให้ผู้เรียกยืนยันเอง (ผู้เรียกในอนาคตจะยืนยันมั่ว แล้วรูรั่วกลับมา)
- **`page_token(pid)`** ดึงทีละเพจจาก `/<page_id>?fields=access_token` **ไม่ใช่ `/me/accounts`**
- **⚠️ ด่านนี้กันได้แค่คนที่เรียกผ่าน `meta.py`** — ใครเขียน `requests.get` ยิง Graph API ตรง ๆ
  ด่านไม่ช่วยอะไรเลย · **เพิ่มโค้ดที่คุย Meta = ต้องเรียกผ่าน `meta.get()` เท่านั้น**

### `python manage.py meta_check [--suggest] [--out ไฟล์]`
เทียบ "token เอื้อมถึงอะไร" กับ "allowlist ของบริษัทนี้" → ขึ้นเตือนถ้ามีของบริษัทอื่นเอื้อมถึง
· `--suggest` ร่างค่า `META_*` ให้ก๊อปลง .env · อ่านอย่างเดียว ไม่แก้อะไร

### สิทธิ์ที่มีจริง (วัดจริง ก.ย.69 — 24 scopes)
| ได้ | ไม่ได้ |
|---|---|
| เพจ 2 ใบ (อ่าน/โพสต์/แก้) | **ตัวตนคนคอมเมนต์/คนกดไลก์** — FB ปิดตั้งแต่ 2018 แก้ไม่ได้ด้วยสิทธิ์ |
| **คอมเมนต์: อ่าน+ตอบ+ซ่อน+ลบ** (`pages_read_user_content`) | **เวลาที่กดไลก์** — ไม่มี `created_time` ให้เลย |
| **แชท Messenger อ่านย้อนหลัง** (≥800 ห้อง/เพจ · 23,803 ข้อความ) | ไลก์ **รายโพสต์** แยกวัน (post insights บังคับ `lifetime`) |
| สถิติเพจรายวัน 30 วัน (`read_insights`) | Instagram — **เพจยังไม่ผูก IG Professional เลย** |
| โฆษณา: อ่าน+สร้าง+แก้ (`ads_management`) | ชื่อ/เบอร์จากฟอร์มลีด — ฟอร์มทั้ง 17 ใบ `leads_count=0` (ของปี 2020-22) |
- **ลีด 217/135 ที่เห็นในสถิติโฆษณาเป็น conversion event** (`onsite_web_lead`) = ยิงจากเว็บเรา
  **ไม่ใช่ Instant Form** → Meta มีแต่ตัวเลข ไม่มีตัวคน
- **ไลก์รายวันได้เฉพาะระดับเพจ**: `page_actions_post_reactions_like_total` · `page_post_engagements`
  · `page_daily_follows_unique` · `page_views_total` (period=day) — **`page_impressions` ถูกถอดจาก v21**
- อยากได้ "ไลก์โพสต์นี้วันนี้กี่คน" ต้อง **จด snapshot เองรายวันแล้วหาผลต่าง** (ย้อนหลังไม่ได้)
- `recommendation_type` ของรีวิวเชื่อไม่ได้ (รีวิวขึ้นต้น "แย่ 👎👎👎" ถูกติดป้าย `positive`)

### 🌙 ดึงยอดโพสต์ + ผลโฆษณาทุกเที่ยงคืน — [meta_sync.py](dashboard/services/meta_sync.py) · ก.ย.69
*"ดึงทุกๆ เที่ยงคืน ตั้งเวลาไว้เลย · ข้อมูลโฆษณาก็ดึงมาเป็น raw data พร้อมกัน · เว้นแต่จะกด sync
 เอง ซึ่งขึ้นแจ้งเตือนกรณี sync ถี่เกินไปว่า token อาจติด limit ให้เว้นช่วง"*

**3 ตาราง** (dashboard migration **0008**):
| ตาราง | เก็บอะไร | อายุ |
|---|---|---|
| `dash_meta_post_snapshot` | **ยอดสะสม**ของโพสต์ 1 แถว/โพสต์/รอบ (วิวแยกแอด-ออร์แกนิก · ไลก์แยกชนิด · คอมเมนต์ · แชร์ · คลิก · ดูเฉลี่ย · ดูครบ 30 วิ) | ถาวร |
| `dash_meta_ad_daily` | ผลโฆษณา **1 แถว/ad/วัน** (upsert) · `actions` = ของดิบ | ถาวร |
| `dash_meta_raw` | คำตอบดิบจาก Meta ทั้งก้อน | **90 วัน** (`KEEP_DAYS`) |

- **ยอดรายวันของโพสต์ = แถว `trigger='cron'` วัน D ลบวัน D-1** · `snap_date` ของรอบเที่ยงคืน =
  **วันที่เพิ่งจบไป** (ไม่ใช่วันที่ดึง) · แถว `manual` (กดเอง) **ห้ามเอาไปลบหายอดรายวัน**
- **★ 20 ก.ย.69 — รอบ cron ของวันเดียวกัน "รันซ้ำได้ ไม่เบิ้ล" แล้ว** (เดิมมีแต่ฝั่ง TikTok)
  วัดจริงคืน 19→20/09: **3,429 แถวแทนที่จะเป็น 1,143** (3 ชุดของวันเดียว) เพราะ gunicorn ถูกรีสตาร์ต
  กลางรอบ → thread ตาย → cron เริ่มรอบใหม่ · ตัวเลขไม่ผิด (ฝั่งอ่านหยิบแถวล่าสุดต่อโพสต์) แต่ตารางบวม 3 เท่า
  → `sync_posts` **ลบชุด cron ของวัน/เพจนั้นก่อนเขียนใหม่** ในธุรกรรมเดียว · **ไม่แตะแถว manual**
- **โฆษณาต่างจากโพสต์**: Meta แยกรายวันให้เอง + ย้อนหลังได้ → upsert ทับ 3 วันล่าสุดทุกรอบ
  (Meta แก้ตัวเลขโฆษณาย้อนหลัง)
- **เวลา**: `cron_tick` → `maybe_run()` ช่วง **00:00–02:59** ถ้าวันนี้ยังไม่สำเร็จ → เริ่ม **ใน thread**
  (ดึง 90 วันใช้ ~40-60 วิ ห้ามหน่วง cron_tick/ชน nginx 120 วิ) · ล้ม = เว้น 20 นาทีค่อยลองใหม่
  (ไม่ลองทุกนาที = ไม่เผาโควต้า) · KV `meta_sync_daily` จดว่าวันนี้ทำแล้ว **เฉพาะตอนดึงโพสต์สำเร็จ**
- **ล็อกกันรันซ้อน** KV `meta_sync_lock` (หมดอายุ 20 นาที กัน thread ตายแล้วล็อกค้างตลอดไป)
- **ปุ่มกดเอง `can_manual()`**: ห่างกัน ≥15 นาที · โควต้า ≥75% = ห้าม · Meta ส่ง
  `estimated_time_to_regain_access` = บอกเวลารอจริง · กำลังรันอยู่ = ห้าม
  **บล็อก 2 ชั้น**: ปุ่มถูกปิดในหน้าเว็บ **และ** endpoint ตอบ 429 เอง
- **โควต้าอ่านจาก header จริง** (`meta.last_usage` · `x-business-use-case-usage` ฯลฯ) ไม่ได้เดาจากจำนวนครั้งที่กด
- **ดึงโพสต์ทีละ 50 พร้อม insights ในคำขอเดียว** (field expansion) — ไม่ยิงทีละโพสต์
- **ผลรอบล่าสุด**: KV `meta_sync_last` · **ประวัติ**: `dash_event_log` kind=`meta_sync`
- คำสั่งดูผลรายวัน (หน้า "ฐานข้อมูล (SQL)"):
  `SELECT snap_date, sum(video_views) FROM dash_meta_post_snapshot WHERE trigger='cron' GROUP BY 1 ORDER BY 1`

**⚠️★ 3 บั๊กที่เจอตอนทดสอบกับ API จริง (แก้แล้ว — อย่าให้กลับมา)**
1. **token หลุดลง raw** — ลิงก์ `paging.next` **มี access_token ฝังใน URL** และ `paging` ไม่ได้อยู่แค่
   ชั้นนอก ยังซ้อนใน `insights` ของ*ทุกโพสต์* → `_raw()` ต้องตัด `paging` **ทุกชั้น** (ตัดแค่ชั้นนอกแล้วยังหลุด)
   · ตัวกรองข้อมูลส่วนบุคคลของหน้า SQL/export กรองแค่ LINE id **ไม่ได้กรอง token ของ Meta**
2. **วิวเป็น 0 ทุกโพสต์** — Meta ส่ง metric วิดีโอชื่อเดียวกัน **2 ชุด** (`period=lifetime` กับ `period=day`)
   เก็บเป็น dict แล้วตัว `day` ทับ → ได้ค่าวันเก่าสุดใน series (มักเป็น 0) · ต้องเลือก `lifetime` เท่านั้น
3. **conversation id `t_…` โดนด่านบล็อก** ทั้งที่เป็นของเพจเรา — `_check()` ต้องเช็ค `_known` ก่อนดูรูปแบบ id
- **Meta ตอบ "An unknown error occurred" แบบสุ่ม** → `meta.get` ลองซ้ำ 2 ครั้ง **เฉพาะ error ชั่วคราว**
- **⚠️★ 20 ก.ย.69 — โฆษณาไม่เข้าเลยสักแถวตั้งแต่เริ่มทำ (แก้แล้ว)**: `dash_meta_ad_daily` = **0 แถว**
  ทุกคืนขึ้น `act_381128876128993: Service temporarily unavailable` · **ไม่ใช่สิทธิ์ ไม่ใช่โควต้า**
  — วัดจริง: `limit=500` Meta คิดนาน **101 วิแล้วโยน error** · `limit=50` เสร็จใน 13 วิ
  (ตัวถ่วงคือฟิลด์ `actions`/`reach` ซึ่งเราต้องใช้ → ลดขนาดหน้าแทนการตัดฟิลด์ · `ADS_PAGE=50`)
  · หลังแก้ดึงได้ **355 แถว/3 วัน ใน 76 วิ** (ค่าโฆษณา ฿23,185)
- **★ เน็ตสะดุดก็ลองใหม่ (ไม่ใช่แค่ error ของ Meta)** — `requests.RequestException` เดิมโยนทิ้งทันที
  → `ConnectionReset` ระหว่างบัญชีที่สอง = **บัญชีนั้นหลุดทั้งรอบ** · ตอนนี้ลองซ้ำในลูปเดียวกัน (2 วิ → 6 วิ)
  (code 1/2/`is_transient`) · **ห้ามลองซ้ำตอนติดลิมิต** (ยิงซ้ำ = โดนพักนานขึ้น)

**★ แก้ข้อมูลที่เคยบอกเจ้าของผิด**: เคยบอกว่า "วิวรายวันต่อโพสต์ Meta ไม่ให้" — **ผิดสำหรับวิดีโอ**
Meta ส่ง `post_video_views`/`_organic`/`_paid`/`avg_time_watched`/`view_time` แบบ `period=day` มาด้วย
(เห็นในคำตอบของ field expansion) · **ที่ไม่มีรายวันจริงคือ ไลก์/แชร์/คอมเมนต์ระดับโพสต์**
· ชุด `day` อยู่ใน `dash_meta_raw` ครบ (ยังไม่ได้แตกเป็นตาราง) · ยังไม่ได้วัดว่าย้อนได้กี่วัน

**ขนาดข้อมูล (วัดจริง)**: ฐานข้อมูล prod ทั้งก้อน **25 MB** (ก.ย.69) · raw ~6.5 KB/โพสต์ ×
~2,000 โพสต์ใน 90 วัน ≈ **12-15 MB/วัน** ก่อนบีบอัด → **raw ใหญ่กว่าทั้งฐานข้อมูลภายใน 2 วัน**
ดิสก์ว่าง 90 GB รับไหว แต่ถ้าวันหนึ่งฐานข้อมูลโตผิดปกติ ต้นเหตุน่าจะอยู่ที่ตารางนี้

### 💬 แชท Facebook Messenger (CRM raw) — [fb_sync.py](checkout/fb_sync.py) · ก.ย.69
*"ส่วนระบบ CRM ก็เป็น raw data ตั้งชื่อ table ให้เหมือนกับ CRM ฝั่ง LINE"* →
เจ้าของเลือก **ตารางแยก ชื่อคู่ขนาน** (ถามแล้ว ไม่ได้เลือกแบบรวมตารางเดียวกับ LINE)

| ฝั่ง LINE | ฝั่ง Facebook (checkout migration **0020**) | 1 แถว = |
|---|---|---|
| `checkout_groupchat` | **`checkout_fbchat`** (`FbChat`) | 1 ข้อความ |
| `checkout_lineprofile` | **`checkout_fbprofile`** (`FbProfile`) | 1 คนต่อเพจ |

- **ชื่อช่องเหมือนฝั่ง LINE ทุกช่องที่ความหมายตรงกัน** (message_id · sender_id · sender_name ·
  msg_type · text · extra · has_media · channel · direction · sent_at …) → SQL ข้าม 2 ฝั่งเขียนคล้ายกัน
  · ต่างกัน: `group_id` → **`thread_id`** (ห้อง `t_…`) · `channel` = **id เพจ** (ฝั่ง LINE = บัญชีบอท)
  · ไม่มีช่องที่มีแต่ LINE (สติกเกอร์แพ็ก / LINE emoji / สเตตัส / ภาษา)
- **`extra` = ข้อความดิบทั้งก้อน** (tags `read`/`source:mobile` · ไฟล์แนบ) — ตัด `paging` (มี token) +
  email ปลอมของ Meta (`<id>@facebook.com`) ออกแล้ว
- **`FbProfile` unique = (เพจ, PSID)** — Facebook ออก id **ต่อเพจ** คนเดียวทัก 2 เพจ = 2 แถว
  ระบบรู้เองไม่ได้ว่าคนเดียวกัน (ปัญหาเดียวกับ LINE คนละ provider) · PSID **ไม่ใช่ LINE id**
- **ข้อมูลไม่ใช่ real-time** — ดึงจาก API ทุกเที่ยงคืน (ต่อท้าย `meta_sync.run()`) ไม่ได้มาจาก webhook
  → ข้อความวันนี้เห็นพรุ่งนี้ · **ใครในทีมตอบ Facebook ไม่บอก** (ขาออกเป็นชื่อเพจเสมอ)
- **ไม่ยิงทุกห้องทุกคืน** (≥8,200 ห้อง): จำ `thread_updated` ของห้องไว้ · **เวลาเท่าเดิม = ข้ามโดยไม่ยิง API**
  · ห้องที่ขยับ: ดึงใหม่→เก่า **หยุดทันทีที่เจอข้อความที่มีแล้ว**
- **เพดานต่อรอบ**: cron 600 ห้อง / 12 นาที · กดเอง 150 ห้อง / 4 นาที · โควต้า ≥60% หยุด
  → **รอบแรก (ย้อน 60 วัน) ไม่ครบในคืนเดียวโดยตั้งใจ** เก็บต่อเองทุกคืน (ทดสอบแล้ว: รอบ 2 ข้ามห้องเดิม
  แล้วไปต่อห้องใหม่) · คืนปกติห้องขยับ ~100-150 ห้อง
- **อายุข้อมูล = แชทลูกค้าฝั่ง LINE** (`CUSTOMER_CHAT_KEEP_DAYS` 60 วัน) · โปรไฟล์ลูกค้าเงียบเกิน 60 วันลบ ·
  **โปรไฟล์พนักงานไม่ลบ** · ย้อนหลังเก่ากว่า 60 วันไม่ดึง
- **ล็อกต่ออายุระหว่างทาง** (`meta_sync._touch()`) — รอบแรกยาวเกิน 20 นาทีได้ ถ้าไม่ต่อ ล็อกหมดอายุกลางทาง
  แล้ว cron รอบถัดไปจะเริ่มซ้อน
- **`meta._known` มีเพดาน 200,000** (ทิ้งของเก่าสุด) — เดิมเป็น set โตไม่หยุดใน worker ที่อยู่หลายวัน
- **ยังไม่ได้ทำ**: หน้าเว็บอ่าน/ตอบแชท FB · ตัวจับ "หารถอะไร งบเท่าไหร่" จากแชท FB (ของเดิมอ่านแค่ฝั่ง LINE)
  · จับคู่ว่าลูกค้า FB คนไหนคือคนเดียวกับฝั่ง LINE (55% ของห้องแชท FB มีไอดี LINE อยู่ในข้อความ)

**Deploy**: `git pull` → `migrate` (สร้าง 3+2 ตาราง: dashboard 0008 + checkout 0020) → เติม `META_ACCESS_TOKEN` / `META_AD_ACCOUNTS` /
`META_PAGE_IDS` ใน `.env` → restart · ไม่ตั้ง = ปิดสนิท รอบเที่ยงคืนไม่ทำอะไร

### ⚠️★ อุบัติเหตุที่เกือบเกิด (ก.ย.69) — token จริงไปอยู่ใน `deploy/.env.example`
ไฟล์นี้ **ถูก track ใน git** แต่เนื้อไฟล์ทั้ง 68 บรรทัดถูกทับด้วย **token จริงบรรทัดเดียว**
→ ถ้า commit ไป token จะขึ้น GitHub · ตรวจแล้ว **ยังไม่หลุด** (ไม่อยู่ใน history และไม่ staged)
กู้คืนด้วย `git checkout --` แล้วเติมเป็น `***copy-from-vercel***`
- **กฎ: `deploy/.env.example` ใส่ได้แค่ค่าตัวอย่าง/ชื่อคีย์** ค่าจริงอยู่ใน `.env` (gitignored) เท่านั้น
- **เช็คก่อน commit ทุกครั้ง**: `git grep -I -n "EAAa"` (token ของ Meta ขึ้นต้น `EAAa`)

### ⚠️ `.env` มี `META_ACCESS_TOKEN` ซ้ำ 2 บรรทัด — **ตัวหลังเป็นค่าว่างและมันทับตัวจริง**
python-dotenv ใช้ **ตัวท้ายสุด** → `settings.META_ACCESS_TOKEN` เป็น `""` มาตลอดโดยไม่มีใครรู้
· แก้แล้ว (ลบตัวว่างออก) · **เวลาเติมคีย์ใหม่ใน `.env` ให้ค้นก่อนว่ามีอยู่แล้วหรือยัง**

## TikTok webhook — [tiktok_webhook.py](dashboard/services/tiktok_webhook.py) · ก.ย.69
*"เตรียมสภาพแวดล้อมอีกอันหนึ่ง เอาไว้เก็บ TikTok Dev · ขอ callback ไปวางที่ webhook ของเว็บนั้น"*

- **callback URL = `https://srv1793506.hstgr.cloud/api/tiktok/webhook`** (= `SITE_URL` + path)
  · ต้องเป็น https สาธารณะ → **ใช้ได้หลัง deploy ขึ้นเซิร์ฟเวอร์เท่านั้น** (localhost TikTok ยิงไม่ถึง)
- **env**: `TIKTOK_CLIENT_KEY` · `TIKTOK_CLIENT_SECRET` (ประกาศใน settings.py แล้ว — บทเรียน
  `LINE_CHANNEL_SECRET` ที่ไม่ถูกประกาศจนข้ามการตรวจลายเซ็นมาตลอด)
- **ลายเซ็น** = HMAC-SHA256(client_secret, `"<t>.<body ดิบ>"`) เทียบกับ `s` ใน header
  `TikTok-Signature: t=…,s=…` · เวลา `t` เก่า/ล้ำได้ไม่เกิน 10 นาที (กันเอาของเก่ามายิงซ้ำ)
  - **ตั้ง secret แล้ว** → ไม่ตรง/ไม่มี header/เวลาเก่า = **401 ไม่เก็บ** (+ จดใน `dash_event_log`)
  - **ยังไม่ตั้ง** → รับและเก็บ แต่ `signature_ok = NULL` — ตั้งใจให้ผ่านช่วงตั้งค่าครั้งแรก
    (TikTok อาจยิงทดสอบก่อนที่เราจะใส่ secret) · **⚠️ อย่าปล่อยไว้แบบไม่ตั้ง** ใครรู้ URL ก็ยิงของปลอมได้
- **ตาราง `dash_tiktok_event`** (dashboard migration **0009**): event · client_key · user_openid ·
  create_time · signature_ok · `content` (**แกะ JSON ที่ TikTok ห่อเป็น string ซ้อนมาแล้ว**) · `raw` (body ทั้งก้อน)
- **กันซ้ำด้วย `body_hash`** (sha256 ของ body) — TikTok ไม่มี event id และส่งซ้ำเมื่อเราตอบช้า
  · ซ้ำแล้วยังตอบ **200** (ถ้าตอบอย่างอื่นมันจะยิงซ้ำไม่หยุด)
- **อายุ 180 วัน** (`KEEP_DAYS`) ลบเองวันละครั้งตอนมี event เข้า · body เกิน 1 MB = 413 · ไม่ใช่ JSON = 400
- **heartbeat** KV `tiktok_webhook_last` = ครั้งล่าสุดที่ถูกยิง + ผ่าน/ไม่ผ่านเพราะอะไร
- `authorization.removed` (ตรวจลายเซ็นผ่านเท่านั้น) → ปิดช่องนั้น + ลบ token ทิ้ง (`tiktok_oauth.mark_revoked`)
- **GET บน path เดียวกัน = Redirect URI ของ Login Kit ด้วย** (เจ้าของลงทะเบียนไว้แบบนี้ในแท็บ Web)
  → มี `code`/`error` ใน query = เจ้าของช่องเพิ่งกดอนุญาต/ยกเลิก → `tiktok_oauth.callback()`

### 🎵 เชื่อม 10+ ช่อง + ดึงยอดวิว/engagement — [tiktok_oauth.py](dashboard/services/tiktok_oauth.py) · [tiktok_sync.py](dashboard/services/tiktok_sync.py)
*"เรายังมีอีกสิบช่องที่ยังไม่เชื่อม เราต้องดึง engagement พร้อมยอดวิวมาจาก TikTok เหมือนกัน เช่น Facebook"*

**เชื่อมช่อง (Login Kit / OAuth v2)**
1. `python manage.py tiktok_accounts --link "ชื่อช่อง" --link …` (หรือ `--links-file`) → ลิงก์ **1 ลิงก์ต่อช่อง**
   · หรือ POST `/api/admin/tiktok/accounts {label}`
2. เจ้าของช่องเปิดลิงก์ กดอนุญาต → TikTok พากลับ `/api/tiktok/webhook?code=&state=`
3. ตรวจ state → แลก code (`open.tiktokapis.com/v2/oauth/token/`) → ดึงชื่อช่อง → เก็บ `dash_tiktok_account`
- **state = เลขสุ่ม เก็บฝั่งเซิร์ฟเวอร์ (KV `tiktok_oauth:<state>`) ใช้ได้ครั้งเดียว หมดอายุ 7 วัน**
  — เอกสารที่เจ้าของได้มาให้ใส่ `state=CHANNEL_ID` ซึ่งเดาได้ = ใครก็พาช่องตัวเองมาผูกกับชื่อช่องเราได้
- **token เข้ารหัส Fernet** (กุญแจ = sha256 ของ SECRET_KEY) · **เปลี่ยน SECRET_KEY = ถอดไม่ได้ ต้องกดอนุญาตใหม่ทุกช่อง**
  · หน้า SQL ซ่อนคอลัมน์ `access_token`/`refresh_token` · ไฟล์ export ตัดทิ้ง (`ALWAYS_DROP`) — กันหลายชั้น
- **access token อายุ ~24 ชม. → `cron_tick` เรียก `refresh_due()` ต่ออายุก่อนหมด 2 ชม.** ทีละ 3 ช่องต่อนาที
  · refresh token ~365 วัน · ต่ออายุไม่ได้ = `status=error` + `last_error`
- `TIKTOK_SCOPES` (env · default `user.info.basic,video.list`) — **สิทธิ์ต้องเปิดในหน้าแอปก่อน ไม่งั้น TikTok
  ปฏิเสธทั้งลิงก์** · อยากได้ผู้ติดตาม/ไลก์รวมของช่อง ต้องเพิ่ม `user.info.stats`
- `dependency`: `cryptography` (ใส่ใน requirements.txt แล้ว · เดิมติดมากับแพ็กเกจอื่นทั้งในเครื่องและเซิร์ฟเวอร์)

**ดึงยอดทุกเที่ยงคืน (กติกาเดียวกับ Facebook)**: `cron_tick` → `tiktok_sync.maybe_run()` ช่วง 00:00–02:59 ใน thread
| ตาราง (dashboard migration **0010**) | เก็บอะไร |
|---|---|
| `dash_tiktok_video_snapshot` | ยอดสะสมรายคลิป (วิว · ไลก์ · คอมเมนต์ · แชร์) คลิปย้อน 90 วัน · ยอดรายวัน = cron D − D-1 |
| `dash_tiktok_account_snapshot` | ผู้ติดตาม · ไลก์รวม · จำนวนคลิป (เฉพาะช่องที่ให้ `user.info.stats`) |
| `dash_tiktok_raw` | คำตอบดิบทั้งก้อน · เก็บ 90 วัน |
- **★ รอบ cron ของวันเดียวกันรันซ้ำได้ ไม่เบิ้ล** — ลบแถว cron ของวันนั้นของช่องนั้นก่อนใส่ (ในธุรกรรมเดียว)
  · บทเรียนจากรอบแรกของ Facebook 20 ก.ย.69: **gunicorn ถูกรีสตาร์ทตอน 00:07 thread ที่ดึงอยู่ตายตาม**
  แล้ว cron เริ่มรอบใหม่ → ถ้าไม่กันจะมียอด 2 ชุดในวันเดียว
- **ช่องเดียวพังไม่ลากช่องอื่น** · token ถูกยกเลิก/สิทธิ์ไม่พอ → ช่องนั้น `status=error` ช่องอื่นดึงต่อ
- ปุ่มกดเอง: `/api/admin/tiktok/sync` ห่างกัน ≥15 นาที · `manage.py tiktok_accounts --sync` ดึงแล้วรอจนเสร็จ
- ผลรอบล่าสุด KV `tiktok_sync_last` · ประวัติ `dash_event_log` kind=`tiktok_sync` / `tiktok_oauth`
- **ยังไม่ได้ทำ**: หน้าจอ (ส่งต่อหน้า UI) · คอมเมนต์รายอันของ TikTok (API ของ Login Kit ไม่ให้)

### 💰 แท็บ "โฆษณา" — แยกออกจากหน้าโซเชียล · [ads_stats.py](dashboard/services/ads_stats.py) · 23 ก.ย.69
*"จากหน้า Social แยกออกมาเป็นหน้า Ads … อย่าลืมเก็บข้อมูลของ Ads เป็น Daily Day กับภาพรวม
เก็บพวกค่าต่างๆ ด้วย พวก cost per chat"*

- **แท็บใหม่ `ad` "โฆษณา"** ใน `NAV_TABS` → `renderAds()` / `loadAds()` / `drawAds()`
  ([index.html](dashboard/templates/dashboard/index.html)) · **ผูกกับตัวกรองวันที่ของหน้าตามกฎเหล็ก**
- **API `/api/admin/ads`** (`admin_ads` · admin เท่านั้น) → `ads_stats.stats(from, to)`
- **`dash_ads_daily`** (migration **0014**) = 1 แถว/วัน/บัญชีโฆษณา — คู่ขนานกับ `dash_social_daily`
  · `dash_meta_ad_daily` (รายวัน**ต่อโฆษณาแต่ละชิ้น**) ยังเป็นต้นฉบับ ตารางนี้คือผลรวมที่พร้อมใช้
  · **สร้างใหม่ได้เสมอ**: `manage.py ads_rebuild [--days N] [--show]`

**★ แตกตัวเลขจาก `actions` JSON มาเป็นคอลัมน์ (`ACTION_MAP`)** — เดิมมีแต่ JSON ดิบ
จะรู้ "ต้นทุนต่อแชท" ต้องงัด jsonb ทุกครั้ง เขียน SQL เองแทบไม่ได้
| คอลัมน์ | action_type ของ Meta |
|---|---|
| `chats` | `onsite_conversion.messaging_conversation_started_7d` |
| `chats_replied` | `onsite_conversion.messaging_conversation_replied_7d` |
| `leads` | `lead` |
| `link_clicks` / `video_views` / `engagement` | `link_click` / `video_view` / `post_engagement` |
· ชื่อพวกนี้มาจากการวัดของจริงบน prod ไม่ได้เดา · **เพิ่ม metric ใหม่ = เติม `ACTION_MAP` ที่เดียว**
แล้วรัน `ads_rebuild` (มันเติมย้อนหลังจาก JSON ที่เก็บไว้แล้ว)

**★★ ต้นทุนต้องคิดจาก "ผลรวมหารผลรวม" เสมอ — ห้ามเฉลี่ยค่าเฉลี่ย**
Meta ส่ง `cost_per_action_type` มารายแถวอยู่แล้ว แต่เอามาเฉลี่ยตรงๆ ได้เลขผิด
· **วัดจริง 23 ก.ย.69**: เฉลี่ยของ Meta = **฿61.31** · ผลรวมจริง (45,365 ÷ 726) = **฿62.49**
→ `dash_ads_daily` จึง **ไม่มีคอลัมน์ต้นทุน** โดยตั้งใจ (เก็บไว้จะมีคนเอาไปเฉลี่ยผิด)
· คิดตอนแสดงผลเสมอที่ `ads_stats._costs()` — ต่อแชท/ต่อแชทที่ตอบ/ต่อลีด/ต่อคลิกลิงก์/CPC/CPM/CTR/%ตอบกลับ

**⚠️★ บั๊ก "ตัวกรองค้าง" ของหน้าโซเชียล (เจ้าของแจ้ง 23 ก.ย.69 · แก้แล้ว)**
- `loadSocial` เดิมขึ้นต้นด้วย `if (_soLoading || ...) return;` → **กำลังโหลดอยู่แล้วผู้ใช้เปลี่ยน
  ช่วงวันที่ = คำขอใหม่ถูกทิ้งไปเลย** · พอคำขอเก่าเสร็จ หน้าจอโชว์ข้อมูล**ช่วงเก่า** แต่ช่องวันที่
  เป็น**ช่วงใหม่** และ **ไม่มีอะไรมาสั่งโหลดช่วงใหม่อีก** → ค้างจนกว่าจะสลับแท็บ
- แก้: คำขอใหม่ **ยกเลิกคำขอเก่าด้วย `AbortController`** + ใช้เลขลำดับ (`_soSeq`) กันผลเก่ามาทับผลใหม่
  · `AbortError` ไม่นับเป็น error (ไม่โชว์ "เปิดไม่ได้" หลอก)
- **กฎ: แท็บใหม่ที่ผูกกับช่วงวันที่ต้องใช้ท่านี้ทุกตัว** — `loadAds` คัดลอกมาเป๊ะ
  · เขียนแบบ "กำลังโหลดอยู่ = ไม่รับคำขอใหม่" เมื่อไหร่ บั๊กนี้กลับมาทันที

**ยังไม่ได้ทำ**: ผูกยอดโฆษณากับโพสต์ (Meta ให้ `ad_id` ไม่ใช่ `post_id` ตรงๆ) ·
แยกตามบัญชีโฆษณาในหน้าเว็บ (ตอนนี้รวมทุกบัญชี · ข้อมูลมีบัญชีเดียวที่ยิงจริง)

### ▶️ YouTube — ดึงยอดช่อง/คลิปทุกเที่ยงคืน · [youtube_sync.py](dashboard/services/youtube_sync.py) · 23 ก.ย.69
*"แล้วก็เรื่องคลิป YouTube เราจะทำยังไงดี มันมีตัวไหนที่สามารถดึงมาได้ไหม"*

**★ ง่ายกว่า TikTok/Meta มาก — ไม่ต้องให้เจ้าของช่องกดอนุญาตเลยสักช่อง**
ยอดสาธารณะขอด้วย **API key ใบเดียวใช้ได้ทุกช่อง** · ไม่มี OAuth · ไม่มี sandbox · ไม่มี Target Users
→ ตัดปัญหา "เจ้าของช่องอยู่คนละจังหวัด นัดเวลาสแกน QR/OTP ไม่ตรงกัน" ที่ติดกับ TikTok ออกทั้งหมด

| ตาราง (dashboard migration **0013**) | เก็บอะไร |
|---|---|
| `dash_youtube_channel_snapshot` | ผู้ติดตาม · วิวรวมทั้งช่อง · จำนวนคลิป ณ สิ้นวัน |
| `dash_youtube_video_snapshot` | ยอดสะสมรายคลิป (วิว · ไลก์ · คอมเมนต์) คลิปย้อน 90 วัน · ยอดรายวัน = cron D − D-1 |
| `dash_youtube_raw` | คำตอบดิบทั้งก้อน · เก็บ 90 วัน |

- **env**: `YOUTUBE_API_KEY` + `YOUTUBE_CHANNELS` (คั่น comma · ใส่ได้ทั้ง `@handle` และ `UCxxxx`)
  · **ประกาศใน [settings.py](oxlet/settings.py) แล้ว** — บทเรียน `LINE_CHANNEL_SECRET` ที่ลืมประกาศ
  แล้ว `getattr` คืนค่าว่างตลอดจนข้ามการตรวจลายเซ็นมาเป็นเดือน · **ไม่ตั้ง = ปิดสนิท** รอบเที่ยงคืนไม่ทำอะไร
- **ไหลเข้า `dash_social_daily` เอง** ท้ายรอบ (`social_daily.refresh_quiet()`) — ใช้สูตรเดียวกับ Meta/TikTok
- **รอบ cron ของวันเดียวกันรันซ้ำได้ ไม่เบิ้ล** (ลบชุด cron ของวัน/ช่องนั้นก่อนเขียนใหม่ ในธุรกรรมเดียว)
  · ช่องเดียวพังไม่ลากช่องอื่น · เรียกจาก `cron_tick` ช่วง 00:00–02:59 ใน thread
- **โควต้าฟรี 10,000 หน่วย/วัน** — รอบหนึ่งใช้ ~(3 + คลิป/50 × 2) หน่วยต่อช่อง → 13 ช่องยังไม่ถึง 1%

**⚠️ ที่ YouTube ไม่ให้ (อย่าไปตามหา)**
- **ยอดแชร์** — ไม่เคยมีใน Data API → `shares` ของฝั่ง YouTube ใน `dash_social_daily` **เป็น 0 เสมอ ไม่ใช่บั๊ก**
- **ยอดดิสไลก์** — YouTube ปิดตั้งแต่ปี 2021 แก้ด้วยสิทธิ์ไม่ได้
- **watch time · CTR · % ดูจบ · คนดูเป็นใคร · รายได้** — ต้องใช้ **YouTube Analytics API** ซึ่งต้อง
  OAuth รายช่องเหมือน TikTok · **ยังไม่ได้ทำ**
- `subscriber_count` / `like_count` เป็น null ได้ ถ้าเจ้าของตั้งซ่อนไว้

**⚠️★ บทเรียนตอนตั้งค่า (23 ก.ย.69 — เสียเวลาไป 4 รอบ)**
1. **คีย์ขาดตัวท้าย 1 ตัว** (39 → 38 ตัว) ตอนก๊อป → Google ตอบ `400 API key not valid`
   · **`400` = ตัวคีย์ผิดรูป · `403` = คีย์ถูกแต่ติดสิทธิ์/IP** — แยก 2 อันนี้ให้ออกจะไล่ได้เร็วขึ้นมาก
2. **`.env` ในเครื่อง กับ `/opt/oxlet/.env` บน VPS เป็นคนละไฟล์** — ทดสอบผิดเครื่องแล้วสรุปผิด
3. **VPS ออกเน็ตทาง IPv6** (`2a02:4780:5e:d059::1`) ไม่ใช่ IPv4 `76.13.214.140` ที่ล็อกไว้
   → ต้องใส่ **`2a02:4780:5e:d059::/64`** ใน Application restrictions (ใส่เป็น `/64` ไม่ใช่ `::1`
   เพราะ Hostinger จัดสรรเป็นบล็อก ตัวท้ายขยับได้)
4. **กด `ADD AN ITEM` แล้วลืมกด Save** — อาการเหมือน propagation delay เป๊ะ (403 เดิมซ้ำๆ)
   **ถ้าลองเกิน ~5 นาทีแล้วยัง 403 ข้อความเดิม ให้สงสัยว่าไม่ได้เซฟ ก่อนจะโทษ propagate**

**ยังไม่ได้ทำ**: หน้าจอในแท็บ "โซเชียล" (ตอนนี้วาดแค่ Facebook/TikTok) · คอมเมนต์รายอัน ·
แยก Shorts ออกจากคลิปยาวในหน้าเว็บ (เก็บ `is_short` ไว้ในตารางแล้ว)

### 📈 แท็บ "โซเชียล" — กราฟ Engagement (Meta + TikTok) · ก.ย.69 (เจ้าของขอ)
*"เหลือหน้าของ Graph ดู Engagement ฝั่ง TikTok กับฝั่ง Meta ออกมาเป็นอีกเมนูหนึ่ง"*

- **แท็บใหม่ `so` "โซเชียล"** ใน `NAV_TABS` ([index.html](dashboard/templates/dashboard/index.html))
  · `renderSocial()` วางโครง → `loadSocial()` ดึง `/api/admin/social` → `drawSocial()` วาด
  · **ผูกกับตัวกรองวันที่ของหน้า** (`dfFrom`/`dfTo`) ตามกฎเหล็ก — เปลี่ยนช่วง = โหลดใหม่ (cache ต่อช่วง)
- **[social_stats.py](dashboard/services/social_stats.py)** — คำนวณฝั่งเซิร์ฟเวอร์ทั้งหมด
  **★ หัวใจ: ตาราง snapshot เก็บ "ยอดสะสม" ไม่ใช่ "ยอดรายวัน"** → ยอดของวันนี้ = วันนี้ − เมื่อวาน
  · **นับเฉพาะ `trigger='cron'`** (แถว manual เกิดกลางวัน เอามาลบจะได้ครึ่งวันปนเต็มวัน)
  · **วันเดียวกันมีหลายแถวได้** (19/09 เคยได้ 3 ชุดเพราะ gunicorn รีสตาร์ตกลางรอบ) → หยิบแถวที่ดึงล่าสุดของวันนั้น
  · **ผลต่างติดลบ = ไม่นับ** (โพสต์ถูกลบ/Meta แก้ย้อนหลัง)
  · **ต้องมี snapshot ≥ 2 วันถึงจะมีกราฟรายวัน** — วันแรกไม่มีวันก่อนหน้าให้ลบ
- **หน้าตา**: การ์ดสรุป 2 ฝั่ง (Facebook ม่วง · TikTok เขียวน้ำทะเล) → กราฟเส้นรายวันสลับตัวเลขด้วยชิป
  (วิว/ไลก์/คอมเมนต์/แชร์) → ตารางโพสต์/คลิปที่คนมีส่วนร่วมมากสุด (รวม 2 ฝั่ง มีคอลัมน์ช่องทาง)
- **★★ หน้ารายชิ้นต้องตอบว่า "ช่วงวันที่เลือกนี้ ชิ้นนี้ได้เท่าไหร่"** (เจ้าของย้ำ ก.ย.69)
  · ตัวเลขใหญ่ = **ผลรวมยอดรายวันในช่วง** (ไม่ใช่ยอดสะสมตลอดกาล) · ยอดสะสมลดชั้นเป็นบรรทัดเล็กใต้ตัวเลข
  · หัวการ์ดเขียนช่วงวันที่ไว้ตรงๆ ("ยอดที่เกิดขึ้นระหว่าง 1/9 – 30/9") + บอกว่าคำนวณจากข้อมูลกี่วัน
  · **ตารางหน้ารวมยังเป็น "ยอดสะสม"** (เรียงหาโพสต์ที่ปังตลอดกาล) — เขียนกำกับไว้ที่หัวตาราง+หัวคอลัมน์
    ไม่งั้นคนอ่านเทียบเลข 2 หน้าแล้วงงว่าทำไมไม่ตรงกัน
- **★ กดแถวในตาราง = เปิด "หน้ารายชิ้น"** (เจ้าของขอ ก.ย.69) — กราฟหน้าตาเดียวกับหน้ารวม
  แต่เป็นของโพสต์/คลิปนั้นอันเดียว · **ไม่ใช่หน้าต่างลอย** — สลับเนื้อหาในแท็บเดิม + ปุ่ม "กลับ"
  · `soOpenPost(i)` / `soBackToList()` / `_soDetailHtml()` · ชิปสลับตัวเลขใช้ตัวเดียวกับหน้ารวม
  · **ยอดรายวันรายชิ้นส่งมาพร้อมก้อนแรก** (`postDaily` — เฉพาะโพสต์ที่อยู่ในตาราง) กดแล้วไม่ต้องยิง API ใหม่
  · **เปลี่ยนช่วงวันที่ = เด้งกลับหน้ารวม** (ชิ้นที่เปิดอยู่อาจไม่อยู่ในช่วงใหม่)
- **★ ฝั่งที่ยังไม่มีข้อมูล ต้องบอกสาเหตุ+ทางแก้ ไม่ใช่โชว์ 0** — ยังไม่เชื่อมช่อง TikTok / เชื่อมแล้วแต่ไม่มีสิทธิ์
  `video.list` / เก็บยังไม่ถึง 2 คืน · และ **ไม่มียอดรายวัน = โชว์ "—" ไม่ใช่ 0** (0 แปลว่า "ไม่มีใครมีส่วนร่วม" ซึ่งไม่จริง)
- **★★ 23 ก.ย.69 — `dash_social_daily` = ตาราง "รายวันจริง" แยกจาก "ยอดสะสม"** (เจ้าของสั่ง
  *"อย่าลืมแยกตาราง Daily Day กับภาพรวม เพราะถ้าแยก Daily ได้ เราก็กรองวันได้"*)
  - **ปัญหาเดิม**: ตาราง snapshot (`dash_meta_post_snapshot` / `dash_tiktok_video_snapshot`)
    เก็บ **ยอดสะสม ณ ตอนดึง** → อยากรู้ "วันที่ 20 ได้กี่วิว" ต้องเอา 2 วันมาลบกันเองทุกครั้ง
    · เขียน SQL เองยาก และ **กรองช่วงวันที่ตรงๆ ไม่ได้**
  - **1 แถว = โพสต์/คลิป 1 ชิ้น × 1 วัน** · เก็บทั้ง **ยอดที่เพิ่มขึ้นวันนั้น** (`views`/`likes`/…)
    และ **ยอดสะสม ณ สิ้นวัน** (`cum_*`) + `title`/`owner_id` ติดมาด้วย → `SELECT … WHERE date
    BETWEEN` ได้เลยในหน้า "ฐานข้อมูล (SQL)" ไม่ต้อง join
  - **★ ใช้สูตรตัวเดียวกับหน้าเว็บเป๊ะ** — เรียก `social_stats._daily_one()` ตรงๆ
    **ห้ามเขียนสูตรใหม่** (บทเรียนเดิม: เลข 2 ชุดที่ไม่ตรงกันแล้วไม่มีใครรู้ว่าอันไหนถูก
    · มีเทสต์เทียบกับ `meta_stats()` ว่าตรงกันทุกวัน)
  - **⚠️ ชื่อคอลัมน์ 2 แพลตฟอร์มไม่เหมือนกัน** (Meta `video_views`/`reactions` ·
    TikTok `view_count`/`like_count`) → `_build()` แปลงเป็นชื่อกลางก่อนเข้าสูตร
    (เคยพลาดตอนเขียนรอบแรก คิดว่าชื่อตรงกัน)
  - **เป็นข้อมูล derived ลบทิ้งได้** — `manage.py social_rebuild [--days 120]` สร้างใหม่จาก
    snapshot ทั้งหมด · เขียนแบบ **ลบของแพลตฟอร์มนั้นแล้วใส่ใหม่ในธุรกรรมเดียว** → รันซ้ำไม่เบิ้ล
  - **อัปเดตเองทุกคืน** — ต่อท้าย `meta_sync.run()` + `tiktok_sync.run()` ผ่าน
    `social_daily.refresh_quiet()` · **พังก็เงียบ ไม่ทำให้การเก็บ snapshot ล้มตาม**
    (snapshot คือต้นฉบับ เสียแล้วเสียถาวร · ตารางรายวันสร้างใหม่เมื่อไหร่ก็ได้)
  - **หน้าเว็บยังคำนวณสดเหมือนเดิม** (ไม่ได้เปลี่ยนมาอ่านตารางนี้) — ตารางนี้มีไว้ให้ **คนเขียน SQL
    เอง/ดูข้อมูลดิบ** ก่อน · ถ้าวันหนึ่งจะให้หน้าเว็บอ่านจากตารางนี้แทน ต้องเผื่อกรณี
    "ยังไม่เคย rebuild" ให้ fallback ไปคำนวณสด
- **★★ 21 ก.ย.69 — `dash_meta_page_daily` = ยอดที่ **Facebook รายงานเองระดับเพจ** (ตัวเทียบ)**
  เจ้าของถาม *"วันที่ 10 มี 15 ล้าน ทำไมวันที่ 20 มีแค่ 1 หมื่น 3 · มันจะเก็บไม่ครบ"*
  → ตัวเลขเดิมคือ **ผลรวมวิววิดีโอรายโพสต์จากฟีด** ซึ่งตอบไม่ได้ว่าขาดอะไร
  · `sync_pages()` ดึง `page_video_views`/`page_post_engagements` (+ชุดเสริม) แบบ `period=day`
    **ย้อนหลัง 30 วันทันที — ไม่ต้องรอสะสมเหมือน snapshot** · upsert 1 แถว/เพจ/วัน
  · **แยก metric เป็น 2 ชุด** เพราะ Meta **ปฏิเสธทั้งคำขอถ้ามี metric ที่ใช้ไม่ได้แม้ตัวเดียว**
    (เช่น `page_impressions` ถูกถอดตั้งแต่ v21) → ชุดหลักพัง = ฟ้อง · ชุดเสริมพัง = ข้ามเงียบ
  · **`end_time` ของ Meta = "เวลาสิ้นสุดช่วง" → ต้องลบ 1 วัน** ถึงจะได้วันที่ของยอดนั้น
    (`2026-09-21T07:00:00+0000` = ยอดของวันที่ 20)
  · หน้าโซเชียลวางคู่กัน: "Facebook รายงานทั้งเพจ X · ที่เรารวมจากโพสต์ได้ Y (P% ของยอดเพจ)"
    + **เส้นประในกราฟ** · ต่ำกว่า 80% = ขึ้นเตือนว่าน่าจะขาดรีลส์/โพสต์ที่ไม่อยู่ในฟีด
- **★ 21 ก.ย.69 — การ์ด/กราฟต้องบอกว่า "ตัวเลขนี้มาจากข้อมูลกี่วัน"** (เจ้าของทัก *"มันเหมือนยังแยกไม่ได้
  เมื่อวาน วันก่อน วันนี้ เท่ากันหมดเลย"*) · **ไม่ใช่บั๊ก** — วัดจริง: snapshot รอบ cron มีแค่ 19+20 ก.ย.
  → **ยอดรายวันคำนวณได้วันเดียว (20/9 = วิว 13,914)** ทุกช่วงวันที่ที่คร่อมวันนั้นจึงได้เลขเดียวกันหมด
  · แก้ด้วยการ**เขียนบอกตรงๆ**: หัวการ์ด "· มีข้อมูลวันเดียว (20/9)" + หัวกราฟเตือนสีเหลืองเมื่อ <3 วัน
  · **บทเรียน: ตัวเลขที่ "ถูกแต่ดูเหมือนพัง" ต้องมีคำกำกับเสมอ** ไม่งั้นคนอ่านสรุปเองว่าระบบเสีย
- **★ ยังไม่มียอดรายวัน (เก็บไม่ถึง 2 คืน) = โชว์ "ยอดสะสมของ N โพสต์ในช่วงนี้" แทน** — เจ้าของถามว่า
  *"ตอนนี้ยังไม่มีข้อมูลหรอ?"* ทั้งที่ตารางข้างล่างมียอดเป็นแสน · หน้าเว็บที่ขึ้น "—" ทำให้เข้าใจว่าไม่มีข้อมูล
  → ตอนนี้ API ส่ง `cum` (ยอดสะสมรวมทุกโพสต์ในช่วง) + `postCount` มาด้วย · หัวการ์ดบอกชัดว่ากำลังดูเลขแบบไหน
- **โลโก้แพลตฟอร์มใช้ไฟล์จริงของเจ้าของ** — `static/dashboard/image/fb.png` · `tiktok.jpg` (ส่งมาเอง ก.ย.69)
  · **เพิ่มรูปใหม่ = ต้อง `collectstatic` ตอน deploy** ไม่งั้นรูปไม่ขึ้นบนเซิร์ฟเวอร์
- **⚠️ ห้ามใส่ `class="shdr"` ให้ `<table>` จริง** — คลาสนั้นเป็น **grid ของแถวแบบอื่น** (`display:grid` +
  `grid-template-columns` ตายตัว) → พอไปครอบ `<table>` **หัวตารางแตกไปกองอยู่ซ้ายจอ** (เจ้าของเห็นก่อนผม)
- **วันที่ยังไม่มี snapshot ส่งเป็น `null` ไม่ใช่ 0** → เส้นกราฟไม่ดิ่งลงศูนย์หลอกตา (กติกาเดียวกับกราฟหน้าภาพรวม)
- **★★ 24 ก.ย.69 — เพิ่ม YouTube เป็นฝั่งที่ 3 + ตาราง "แยกตามช่อง"** (เจ้าของแจ้ง *"มันไม่มี
  TikTok แยกช่อง … YouTube หายไปไหนก็ไม่รู้ ไม่มีเลยในหน้านี้"*)
  - **`SO_SIDES = ['meta','tiktok','youtube']`** ([index.html](dashboard/templates/dashboard/index.html))
    — **เพิ่มแพลตฟอร์มใหม่ = เติมที่นี่ที่เดียว** (การ์ดสรุป · เส้นกราฟ · ตารางโพสต์ วนจากตัวนี้หมด)
  - **`social_stats.youtube_stats()`** โครงเดียวกับ `tiktok_stats` เป๊ะ · `overview()` คืน 3 ฝั่ง
  - **`_owner_totals()`** = ยอดแยกช่อง · **คิดรายคลิปด้วย `_daily_one` ก่อนแล้วค่อยรวมเข้าช่อง**
    ⚠️ **ห้ามเอายอดสะสมของทั้งช่องมาลบกันตรงๆ** — คลิปที่เพิ่งโพสต์วันนี้จะทำให้ผลต่างพุ่ง
    ทั้งที่ไม่มีใครดูเพิ่ม (ทดสอบแล้ว: 3 คลิป 1000/2000/3000 → 2000/4000/6000 ต้องได้ 6,000)
  - **โลโก้ YouTube เป็น SVG ฝังใน data URI** (`YT_ICON`) ไม่ต้องเพิ่มไฟล์ static → **ไม่ต้อง collectstatic**
    · ⚠️ ข้างใน `encodeURIComponent()` ต้องเขียน `#FF0000` ตรงๆ **ห้ามเขียน `%23`** ไม่งั้นโดนเข้ารหัสซ้ำ
      เป็น `%2523` แล้วสีใช้ไม่ได้ → **โลโก้กลายเป็นสี่เหลี่ยมดำ** (เจอตอนแคปรูปตรวจ)
  - แชร์ของ YouTube ในตารางแยกช่องโชว์ **"–" ไม่ใช่ 0** (API ไม่ให้ — 0 จะอ่านเป็น "ไม่มีใครแชร์")
- **⚠️ แก้ template แล้วต้องรีสตาร์ท server เสมอ** — รอบนี้ผมลืมเอง แล้วแคปรูปออกมาไม่เห็น YouTube
  ทั้งที่โค้ดถูกแล้ว เสียเวลาไล่หาสาเหตุอยู่รอบหนึ่ง (กฎนี้มีในบันทึกอยู่แล้ว)
- **★★ 24 ก.ย.69 — "ครอบคลุมน้อย" ต้องไม่โชว์เป็นยอดรายวัน** (เจ้าของถาม *"ไม่เข้าใจทำไม TikTok
  เป็นศูนย์วิวอ่ะ"*)
  - **วัดจริง 23/09**: TikTok มีคลิปในระบบ **533 คลิป** แต่คืนก่อนหน้า (22/09) เก็บได้แค่ **1 คลิป**
    (เพิ่งเชื่อมช่องครบตอนบ่าย 23/09) → จับคู่ลบกันได้คลิปเดียว = การ์ดขึ้น **"วิว 1"**
    · Facebook วันเดียวกันจับคู่ได้ **1,126 จาก 1,158 โพสต์ (97%)** = 76,494 ซึ่งเชื่อได้
  - **"1" ถูกตามสูตร แต่วางข้าง Facebook 76,494 แล้วอ่านเป็น "TikTok ตายแล้ว"** — เลขที่ถูก
    แต่สื่อผิด อันตรายกว่าเลขที่ผิดแล้วเห็นชัด
  - **`dailyItems`** (ฝั่งละตัว · `_daily_cover()`) = คิดยอดรายวันได้กี่ชิ้นในช่วงนั้น →
    หน้าเว็บเทียบกับ `postCount`: **ครอบคลุมไม่ถึงครึ่ง = ถือว่ายังคิดไม่ได้** → โชว์ **ยอดสะสม**
    แทน + เขียนบอกด้วยตัวเลขจริง ("ยอดรายวันยังคิดได้แค่ 1 จาก 533 คลิป")
    · **กราฟก็ไม่ลากเส้นฝั่งนั้น** — เส้นที่ลากจากคลิปเดียวจะแบนติดศูนย์ สื่อผิดแบบเดียวกัน
  - **⚠️ อย่าเช็คแค่ `daily` มีคีย์ไหม** (ของเดิม `!Object.keys(d.daily).length`) — มียอดรายวัน
    "บางชิ้น" ไม่ได้แปลว่าใช้ได้ · ต้องดูสัดส่วนเสมอ
- **★ "% ของยอดเพจ" เกิน 100% ได้ ไม่ใช่บั๊ก** — ของเรานับวิวรายโพสต์ (รวมวิวที่มาจากโฆษณา)
  ส่วนยอดเพจเป็นตัวเลขที่ Facebook สรุปเอง คนละวิธีนับ · วัดจริง 23/09 ได้ **136%**
  → เขียนกำกับไว้ในการ์ดแล้วเมื่อเกิน 110%
- **★★ 24 ก.ย.69 (รอบ 2) — ตาราง "แยกตามช่อง / เพจ" ครบทั้ง 3 ฝั่ง + ยอดสะสม**
  (เจ้าของแจ้ง *"TikTok ก็มีตั้งหลายช่อง Facebook ก็มีตั้งหลายช่อง ทำไมไม่แยกหน่อย"*)
  - **`_channel_rows()`** ([social_stats.py](dashboard/services/social_stats.py)) = ตัวรวมแถวตัวเดียวที่ทั้ง 3 ฝั่งใช้
    · รับ 3 dict (เพิ่มในช่วง / สะสม / จำนวนชิ้นงาน) + ชื่อ + ผู้ติดตาม → คืนแถวพร้อมโชว์
  - **★ ส่ง "ยอดสะสม" (`cum`) มาด้วยเสมอ** — ยอดที่เพิ่มขึ้นต้องมี snapshot 2 คืนถึงคิดได้
    ถ้ามีแต่ยอดเพิ่ม ช่วงที่เพิ่งเริ่มเก็บจะเป็น 0 ทั้งตาราง **แล้วดูเหมือนระบบพัง**
    (วัดจริง 24/09: TikTok 9 ช่องยอดเพิ่มคิดไม่ได้ แต่ยอดสะสมมีตั้งแต่ 94 ถึง 3 ล้าน)
  - **★ `live` เป็น "รายช่อง" ไม่ใช่รายแพลตฟอร์ม** — ช่องที่ยังคิดยอดรายวันไม่ได้โชว์ **`–` ไม่ใช่ `0`**
    · เคยผิดรอบแรก: TikTok มีคลิปเดียวที่คิดได้ → ทั้งฝั่งถูกตีว่า "คิดได้แล้ว" → อีก 9 ช่องขึ้น 0
      ซึ่งอ่านเป็น "ไม่มีใครดู" ทั้งที่ช่องหลักมีผู้ติดตามแสนสอง
  - **★ `always` = ช่องที่เชื่อมไว้แล้วต้องมีแถวเสมอ** แม้ช่วงนั้นไม่ได้ลงคลิปเลย (จางไว้ + เขียน
    "ไม่มีคลิปในช่วงนี้") — ไม่งั้นช่องหายไปเฉยๆ แล้วคนอ่านสรุปว่าระบบมองไม่เห็นช่องนั้น
  - **ชื่อเพจ Facebook เก็บใน KV `meta_page_names`** — `meta_sync.sync_pages()` ถาม
    `/<page_id>?fields=name` แล้วจดไว้ (ขอชื่อไม่ได้ = ใช้ของเดิม/รหัสเพจ ไม่ล้มทั้งรอบ)
    · เก็บใน KV ไม่ใช่คอลัมน์ เพราะเป็นแค่ป้ายชื่อที่เปลี่ยนได้ ไม่ควรให้ snapshot ล้านแถวแบกซ้ำกัน
  - การ์ดสรุปแต่ละฝั่งมีปุ่ม **"N เพจ / N ช่อง"** → `soGotoChannels()` เลื่อนลงไปตารางข้างล่าง
  - **ห้ามตัดชื่อช่องด้วย `.slice()`** — 2 เพจของบริษัทชื่อต่างกันแค่คำท้าย ("…สำนักงานใหญ่")
    ตัดที่ 44 ตัวแล้ว **2 แถวหน้าตาเหมือนกันเป๊ะ** · ตอนนี้โชว์ชื่อเต็มแล้วปล่อยให้ตัดบรรทัดเอง
- **ยังไม่ได้ทำ**: ผู้ติดตามเพจ Facebook (ตารางขึ้น `–` — ยังไม่ได้เก็บ) ·
  ยอด "ไลก์รายวัน" ของ TikTok ระดับช่อง · ผูกยอดโฆษณากับโพสต์ (Meta ให้ ad_id ไม่ใช่ post_id ตรงๆ)

## Conventions

- **⭐ โทนสี = ม่วงขาว (สีบริษัท) — ห้ามเปลี่ยนเป็นดำขาว** · 19 ก.ย.69 เคยลองเปลี่ยนทั้งเว็บเป็นดำขาวตามที่เจ้าของขอ
  แล้วเจ้าของสั่งกลับภายในวันเดียว: *"เหมือนไว้อาลัยเลย ไม่เอาสีดำ มันตัดกับธีมบริษัท"* → ย้อนสีกลับหมด
  (คงไว้เฉพาะตัวอักษร 3 ขนาด · คอลัมน์ทีม · แถบเมนูซ้ายสีม่วงเข้ม) · สีหลักอยู่ที่ตัวแปรใน
  [globals.css](dashboard/static/dashboard/css/globals.css) `:root` / `html[data-theme="dark"]`
  - มีตัวแปร `--on-blue` (ตัวอักษรบนพื้นสีหลักทึบ · ตอนนี้ = ขาวทั้ง 2 โหมด) — ใช้แทน `color:#fff` เวลาเขียนปุ่มใหม่
  - สีกราฟภาพรวม: ชุดหลัก `_INK` = ม่วง `#7c3aed` · ชุดรอง `_SOFT` = ม่วงอ่อน `#a78bfa`
- **⭐ ตัวอักษร 3 ขนาดหลัก header > subheader > text (19 ก.ย.69)** — `--fs-h` 17px · `--fs-sub` 14.5px · `--fs-body` 13px
  - **เขียนขนาดใหม่ = ใช้ตัวแปร ห้ามพิมพ์ px เอง** (`font-size:var(--fs-body)`) · ข้อยกเว้นเดียว: ตัวเลขใหญ่ ≥18px (KPI)
    และตัวเลขในจุดแจ้งเตือน <9.5px
  - ตอนเปลี่ยนใช้สคริปต์แปลงอัตโนมัติ: เดิม 9.5–13px → text · 13.5–15px → subheader · 15.5–17.5px → header ·
    `.card-title` = header · body = text · ระบบรถ/เบิก-คืน (ไม่มีตัวแปร) ใช้เลข px ชุดเดียวกัน
  - ฟอนต์ **Noto Sans Thai ทุกหน้า** (ระบบรถเดิม Segoe UI · เบิก-คืนเดิม Sarabun ที่ไม่ได้โหลดจริง)
- **⭐ ห้ามทำกรอบทรงแคปซูล (ปลายมนกลม) — ใช้สี่เหลี่ยมมุมมนนิดเดียว** (20 ก.ย.69 · เจ้าของ: "กรอบมุมตัดแบบนี้ไม่สวย ทุกตัว")
  - ปุ่ม/ชิป/ป้าย: `border-radius` **5–8px** (ของจิ๋ว padding ≤2px = 5px · ปุ่มเตี้ย = 7px · ทั่วไป = 8px)
    · **ห้ามใช้ 20px/999px หรือมุม ≥ ครึ่งหนึ่งของความสูง** · วงกลมจริง (จุดสถานะ/รูปโปรไฟล์) ใช้ `50%` ได้ตามเดิม
    · ยกเว้น: แถบความคืบหน้าเส้นบาง (`.pbr`/`.pbf`) · การ์ดใหญ่ (10–16px ไม่ใช่แคปซูลอยู่แล้ว) · รูปรายงานที่ส่งไลน์
  - วิธีตรวจ: เปิดหน้าในเบราว์เซอร์แล้วหา element ที่ `radius ≥ height/2` และกว้างกว่าสูง — รอบนี้เหลือ 0 ทุกหน้า
- **⭐ ตาราง: ห้ามต่อป้าย (ทีม/สถานะ) ท้ายชื่อ → แยกเป็นคอลัมน์ของตัวเอง** (19 ก.ย.69 · เจ้าของแจ้ง "ต่อท้ายมั่วซั่ว แถวไม่เท่ากัน")
  - ทีมใช้ `teamCell(team, inactive)` ([index.html](dashboard/templates/dashboard/index.html)) → ป้าย `.tm-tag` สีประจำทีม
    ขนาดตายตัว · เทเลเซลล์ = "เทเล" · เซลล์เก่า = "เก่า" · ใช้แล้วใน: จัดสรร Lead · สรุปรายเซลล์ · รายละเอียดรถรายเซลล์
- **⭐ คำอธิบาย/help inline → ใช้ `.info-tip` (ปุ่ม `?` + tooltip) เสมอ** — ไม่ใช้ `<details>`/กล่องแยก สำหรับ tip สั้น ๆ:
  ```html
  <span class="info-tip" tabindex="0" onclick="event.stopPropagation()" data-tip="บรรทัด1\nบรรทัด2">?</span>
  ```
  - CSS `.info-tip` + smart-tooltip JS (กัน parent `overflow:hidden` ตัดหัว) อยู่ใน [index.html](dashboard/templates/dashboard/index.html) แล้ว · `data-tip` รองรับหลายบรรทัดด้วย `\n` · ตัวอย่าง: KPI tips, รหัสในชื่อรถ (popup สถานะรถ), RJ leads
  - tip ยาว/เป็นตาราง (เช่นรายการ 7 บทบาท) ค่อยใช้กล่อง/section แทน
- **⭐⭐ 24 ก.ย.69 — ปุ่มลัดช่วงวันที่ + บั๊ก "พิมพ์วันที่ไม่ได้เลย" (เจ้าของแจ้ง "ตัวกรองวันที่ใช้งานไม่ได้เลย")**
  - **ปุ่มลัด 7 ปุ่ม** (`_DF_PRESETS` ใน [index.html](dashboard/templates/dashboard/index.html)):
    วันนี้ · เมื่อวาน · 7 วัน · 30 วัน · 1 ปี · เดือนนี้ · ทั้งปี — **เพิ่มปุ่มใหม่ = เติมที่ลิสต์นี้ที่เดียว**
    · "N วันย้อนหลัง" **นับวันนี้ด้วย** (7 วัน = วันนี้ + ย้อนไป 6) · ปุ่มที่ตรงกับช่วงที่เลือกอยู่จะถูกไฮไลต์
  - **★ ต้นเหตุที่พิมพ์วันที่ไม่ได้**: `<input type=date>` ยิง `onchange` **ตั้งแต่พิมพ์ตัวแรก** —
    พิมพ์ `2` ของปี 2026 ค่ากลายเป็นปี **0002** ซึ่งเป็นวันที่ "ครบ" แล้ว → `setDfRange` → `render()`
    → **ล้าง `innerHTML` ทั้งหน้า → ช่องที่กำลังพิมพ์หายไปพร้อมโฟกัส** → ตัวเลขที่เหลือตกหมด
    · วัดในเบราว์เซอร์จริง: กด `2` แล้วโฟกัสเด้งไป `BODY` ทันที ค้างที่ `0002-09-01` ตลอด
    · **เป็นมาทุกแท็บ ไม่ใช่แค่โซเชียล** — ใช้ได้แค่ปฏิทินป๊อปอัปกับปุ่มลัดเท่านั้น
  - **แก้ 3 ชั้น** (`dfType()` — ช่องวันที่เปลี่ยนจาก `onchange` เป็น **`oninput`**):
    (1) **ปีนอก 2000–2100 = ยังพิมพ์ไม่เสร็จ ไม่ต้องรีเฟรช** (กัน 0002/0021/0210 ระหว่างพิมพ์)
    (2) **หน่วง 450ms หลังหยุดพิมพ์** ค่อยรีเฟรช — พิมพ์ "2" แล้ว "1" ติดกัน = รีเฟรชครั้งเดียว
    (3) **คืนโฟกัสให้ช่องเดิมหลัง `render()`** (`_dfFocus`) เพราะ DOM เพิ่งถูกล้างทิ้ง
  - **⚠️ กฎ: ช่องกรอกอะไรก็ตามที่เรียก `render()` ต้องคิดเรื่อง "DOM หายระหว่างพิมพ์" เสมอ** —
    `render()` ล้างทั้งหน้า ไม่ใช่แค่ส่วนที่เปลี่ยน · ถ้าไม่หน่วง+คืนโฟกัส ผู้ใช้จะพิมพ์ไม่ได้
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
  - **⚠️★ DEAD CODE เตือนก่อนแก้ (ตรวจพบ ส.ค.69)**: บล็อกถัดไปบรรยาย UI รายการ/รายละเอียดรถ "ของหน้าเซลล์เอง" ซึ่ง **ไม่ทำงานแล้ว** — ตั้งแต่ ก.ค.69 `renderCarsMode()` render **แค่ `<iframe src="/track/">`** เท่านั้น · `renderCarsList` ถูกประกาศไว้แต่ **ไม่มีใครเรียก** → `renderCarDetail`/`renderScChanger`/`scConfirmStage`/`scHistoryHtml`/`openSellerCar` **เข้าไม่ถึงทั้งชุด**
    - **แปลว่า: เซลล์ใช้ป๊อปอัปของ [dashboard.html](templates/dashboard.html) (ในกรอบ iframe) ไม่ใช่โค้ดใน seller.html** → จะแก้พฤติกรรมการเปลี่ยนสเตปของเซลล์ **ต้องไปแก้ที่ dashboard.html** แก้ใน seller.html จะไม่มีผลอะไรเลย
    - เคยพลาดมาแล้ว (ส.ค.69 รอบ 9 แก้ seller.html ไปก่อนจะรู้ว่าเป็น dead code) — เก็บโค้ดไว้เผื่อกลับมาใช้ แต่ **อย่าเชื่อว่ามันรันอยู่**
  - **★ ดีไซน์มือถือ list→detail (มิ.ย.69 · _ดูคำเตือน DEAD CODE ข้างบน_)**: `renderCarsMode` แตกเป็น 2 view (`_scView` = `'list'`|`'detail'`). **list** (`renderCarsList`/`renderSellerCars`) = ค้นหา/กรองสเตป + การ์ดรถ → **แตะการ์ด** → `openSellerCar(code)` (fetch `/track/cars/<code>/json`). **detail** (`renderCarDetail`) = หน้าจอเปลี่ยนสเตปเต็ม: การ์ดรถ (hero) + **step changer** (chips สเตปที่เปลี่ยนได้ · `renderScChanger`/`scPickStage` · current→selected) + โน้ต + **อัปรูป/วิดีโอ ก่อน/หลัง** + ปุ่มยืนยัน (`scConfirmStage`) + **ไทม์ไลน์ประวัติ** (`scHistoryHtml` จาก `car_json` logs)
  - **อัปรูป**: `scAddPhotos` → POST ไฟล์ (multipart) เข้า `/track/api/upload` (ส่ง `code`) → Google Drive (โฟลเดอร์รถคันนั้น) → ส่ง `media`=`[{id,video}]` ใน `seller_set_stage` → แนบเข้า `ScanLog.media` (เหมือน `scan_submit`) · `car_json` คืน `logs[].media` เป็น `{url,video}` (จาก `_media_urls`) + `logs[].stageKey` (แปลชื่อสเตปข้ามภาษา) + `lastWorker`. _(ดูหัวข้อ "รูป/วิดีโอ → Google Drive" ท้ายไฟล์ · เลิกใช้ `sign_upload`+Supabase)_
  - **★ i18n 4 ภาษา (TH/EN/MM/KH)** สำหรับคนงานหลายสัญชาติ: `SC_T` (label) + `SC_STAGE_I18N` (ชื่อสเตป EN/MM/KH · TH ใช้ค่าจากเซิร์ฟเวอร์) + `scT()`/`scStageName()` · สลับด้วย `setScLang` (เก็บ localStorage `scLang`) · **พม่า/เขมรเป็นฉบับร่าง — ควรให้เจ้าของภาษาตรวจ** · accent ใช้ `--blue` ของหน้าเซลล์ (ไม่ฮาร์ดโค้ดม่วงตามม็อก เพื่อรองรับ light/dark เดิม)
- **auth = Django auth + Group** (**10 บทบาท** · [cars/roles.py](cars/roles.py)): **สิทธิ์เต็ม (เพิ่ม/แก้/ลบรถ + จัดการผู้ใช้)** = Executive/Registration/QC/PaintIn (**QC มีสเตปแค่ 4 ปุ่ม** ตั้งแต่ ส.ค.69) · **เฉพาะสเตปตัวเอง** = Purchasing/Production/Technician/CarWash/Sales · **Admin** = แก้ข้อมูลรถ + จัดการผู้ใช้ (ไม่เปลี่ยนสเตป). **(ก.ค.69: +Production/QC/PaintIn · ยุบ Vendor เข้า Registration)** — ตารางสิทธิ์เต็มดูหัวข้อ "รื้อสเตป+บทบาท" ด้านล่าง
- **★ รื้อสเตป + บทบาท (ก.ค.69) — 16 สเตป/4 เฟส + ความด่วน + บังคับรูป + ถ่ายคอนเทนต์** ([constants.py](cars/constants.py)/[roles.py](cars/roles.py)/[models.py](cars/models.py) · migration **0010_restage_v2_priority** — ต้อง `migrate` ตอน deploy · remap สเตปเก่า→ใหม่ให้อัตโนมัติ):
  - **22 สเตป (4 เฟส · `STAGES`/`PHASES` · ส.ค.69 รอบ 4)**: รับเข้า·รถรอถ่ายรูป | เช็คซ่อม·**ซ่อมเสร็จรอตรวจ**·สั่งของ/รออะไหล่·งานเบาะ·อู่สีใน·อู่สีนอก·**รอตรวจสี**·ติดฟิล์ม·ชงล้าง·**ชงล้างรอปล่อย**·**รอ QC ตรวจ** | **รอเซลล์ตรวจรถขึ้นโชว์**·รถพร้อมขาย·จอง·จัดไฟแนนซ์·**ตรวจขนส่ง**·รอปิดการขาย | ตรวจรถรอปล่อย·ปล่อยรถ·**ขายแล้ว**. **ขายแล้ว (`sold`) = จบจริง (status=sold หลุดบอร์ด) · ปล่อยรถไม่จบแล้ว (เซลล์เก็บรูปต่อ)** · แยกอู่สีเป็น ใน(`paint_in`)/นอก(`paint_out`) · เลิกจุด QC กลาง 3 จุดเดิม → รวมเป็น `qc_show`/`qc_release`
    - **★ `repair_done` "ซ่อมเสร็จรอตรวจ" (ส.ค.69 · migration 0011)** — วางต่อจาก `repair` ทันที (ช่างตรวจเสร็จ กดบอกว่าจะทำงานไหนต่อ) · **ช่างเป็นคนกด** · เพิ่มชื่อใน i18n 2 ที่: `STG` ([dashboard.html](templates/dashboard.html)) + `STAGE_NAMES` ([scan.html](templates/scan.html)) — **ลืมเพิ่ม = คอลัมน์โชว์คีย์ดิบ `repair_done`**
    - **★ ด่านตรวจ 2 ชั้นก่อนขึ้นหน้าร้าน (ส.ค.69 · migration 0012)**: `wash` → **`qc_show` "รอ QC ตรวจ"** (ล้างเสร็จส่งตรวจ) → **`sales_check` "รอเซลล์ตรวจรถขึ้นโชว์"** (QC ตรวจผ่านแล้วติ๊กส่งต่อ) → `show`. **เปลี่ยนชื่อ `qc_show` จาก "รอตรวจรถขึ้นโชว์" → "รอ QC ตรวจ"** เพราะชื่อเดิมไม่บอกว่าใครตรวจ → สับสนกับด่านเซลล์
      - ~~ชั่วคราว: ให้ `CARWASH` ติ๊ก `sales_check` แทน QC~~ **(จบแล้ว — ส.ค.69 รอบ 4 เอา CARWASH ออกจาก `sales_check` เพราะมีคน QC จริงแล้ว · ตอนนี้ `sales_check` = `{QC}` + สิทธิ์เต็ม)**
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
    - **★ หน้าเซลล์ตั้งความด่วน/ติ๊กธงได้แล้ว (ส.ค.69 · _dead code — ของจริงมาจากป๊อปอัปใน iframe_)**: [seller.html](dashboard/templates/dashboard/seller.html) `renderCarDetail` เพิ่มการ์ด **ความด่วน (dropdown) + ธงงานค้าง (checkbox)** เหนือกล่องเปลี่ยนสเตป (`scSetPriority()`/`scSetFlag()` · โชว์เสมอแม้บทบาทไม่มีสเตปให้กด) — เดิมหน้าเซลล์ **ไม่มี UI ตั้งความด่วนเลย** ต้องไปหน้าสแกน/บอร์ด · `cars_api` ส่ง `priorities` + `flagDefs` เพิ่ม
    - **เพิ่มธงใหม่**: แก้ `CAR_FLAGS` ([constants.py](cars/constants.py)) + เพิ่มฟิลด์ใน [models.py](cars/models.py) + migration + `FLAG_DEFS` ใน [dashboard.html](templates/dashboard.html) + checkbox&i18n ใน [scan.html](templates/scan.html) + `needTire`-style key ใน `car_json`/`cars_api`/`api_set_flags` ให้ตรงกัน (`api_set_flags` วนตาม `FLAG_KEYS` อยู่แล้ว ไม่ต้องแก้)
  - **★ สีการ์ด = `Car.card_color`** ([models.py](cars/models.py)) — ปกติใช้สีความด่วน แต่ **ถึง `show` (รถพร้อมขาย) = เขียว `FRONTLINE_COLOR` ทับ** (จบสายทำสภาพแล้ว) · **หัวการ์ด = `Car.card_label`** = ป้ายทะเบียน (คนหน้างานจำทะเบียนไม่ใช่รหัส) · ไม่มีทะเบียน → fallback รหัสรถ · รหัสยังอยู่ใน `title` ตอน hover
  - **บังคับแนบรูป/วิดีโอ + หมายเหตุ** — _(ส.ค.69 รอบ 9: ขยายจาก `{qc_release, release}` เป็น **ทุกสเตป** · ดู "รอบ 9" ด้านล่าง)_ · **ถ่ายคอนเทนต์** = action แทรกได้ทุกสเตป (ไม่เปลี่ยนสเตป · เก็บ ScanLog ที่สเตปเดิม) → `POST /track/api/content_shoot` · ~~ความด่วน = ใครล็อกอินก็ทำได้~~ **(ตกยุค — ส.ค.69 รอบ 5-6 จำกัดทั้งบทบาทและสเตปแล้ว)**
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
    - **★★ ก.ย.69 — ทุกหมวดใน drawer "พับได้" (accordion) + จัดหมวดใหม่** (เจ้าของแจ้ง *"สไลด์เมนูเยอะเกินไปแล้ว"*)
      - เปิดเมนูมาเห็น **แท็บ 8 อัน + หัวข้อหมวด 4 บรรทัด** เท่านั้น — รายการจัดการ 16 อันพับไว้หมด
        (เดิมยาว 21+ รายการ ต้องเลื่อนหา) · กดหัวข้อเพื่อกาง · **จำสถานะไว้ใน localStorage `navSec`**
      - **หมวดใหม่ 4 หมวด**: **ลูกค้า & ข้อมูล** (แชทลูกค้า/กลุ่ม LINE · ฐานข้อมูล (SQL) ·
        Export ไทม์ไลน์รถ · ส่งคะแนนเข้าชีต) · **ทีม & สิทธิ์** (+ย้าย "LINE ID พนักงาน" มาจากหมวด Log) ·
        **ตั้งค่าระบบ** · **ตรวจสอบ & Log** (เหลือ 3 รายการที่เป็น log จริงๆ)
      - **`k` ในแต่ละหมวด = คีย์จำสถานะ** (`crm`/`team`/`sys`/`log`/`main`) — คงที่แม้เปลี่ยนชื่อหมวดทีหลัง
        ถ้าใช้ชื่อไทยเป็นคีย์ พอแก้ชื่อหมวดผู้ใช้จะถูกรีเซ็ตกลับเป็นพับหมดโดยไม่มีเหตุผล
      - **`toggleNavSec()` สลับใน DOM ตรงๆ (attribute `hidden`) ไม่เรียก `render()`** — render ล้างทั้งหน้า
        (คำนวณ+วาดใหม่หมด) แค่กางเมนูไม่คุ้ม และจะเห็นหน้ากระพริบ
      - **⚠️ `positionNavInd()` ต้องเช็ค `active.offsetParent === null`** — แท็บที่อยู่ในหมวดที่พับไว้
        ไม่มีตำแหน่งจริง (`offsetTop/Left` = 0) → แคปซูล gradient จะไปค้างมุมซ้ายบน ถ้าไม่ซ่อนก่อน
      - **`gotoCheckout(panel)`** — แท็บ "เบิก-คืนรถ" เป็น **iframe ของ `/checkout/`** สั่งข้างในตรงๆ ไม่ได้
        → ส่งผ่าน query (`/checkout/?line=1` → หน้านั้นเรียก `toggleLine()` เอง) · **เก็บ src ไว้ในตัวแปร
        `_ckSrc` ไม่คำนวณใหม่ทุก render** ไม่งั้น re-render รอบถัดไปจะเปลี่ยน src → iframe รีโหลด → พาเนลปิดเอง
      - ไอคอนใหม่ `chevron-down` / `download` / `message-circle` เพิ่มใน dict **`LUCIDE`** แล้ว
        (dict นี้ hardcode — ไม่เพิ่มก่อน `ic()` คืน svg เปล่า)
      - **★ 19 ก.ย.69 (เจ้าของแจ้ง "เมนูรก") — แตกเป็น 6 หมวดเล็ก + กางได้ทีละหมวด**
        - หมวดเดิมใหญ่ 6-7 รายการปนหลายเรื่อง → **ลูกค้า (2)** · **พนักงาน & เช็คชื่อ (4)** ·
          **ทีมขาย & สิทธิ์ (4)** · **ส่ง LINE อัตโนมัติ (3)** · **ข้อมูล & ดาวน์โหลด (6)** · **ตรวจสอบ & Log (3)**
          · คีย์ใหม่ `staff`/`line` (คีย์เดิม `crm`/`team`/`sys`/`log` ยังใช้ แต่ข้างในเปลี่ยน)
        - **กางหมวดจัดการอันใหม่ = พับอันอื่นให้เอง** (`toggleNavSec` · หัวข้อมี `data-k`) → เมนูไม่ยาวเกินจอ
          · "หน้าหลัก" (แท็บ) ไม่ร่วมกติกานี้ · หัวข้อโชว์ **จำนวนรายการ** (`.nav-cnt` · ไม่มี CSS ก็เป็นตัวเลขธรรมดา)
        - ทุกรายการ **ไอคอนไม่ซ้ำกัน** (เดิม bell ×2 · car-front ×3 · repeat ×2 กวาดตาหายาก) → เพิ่ม
          `shield`/`users`/`id-card` เข้า `LUCIDE` · แถวเตี้ยลง (ntab 11→9px) แต่ตัวหนังสือ/ไอคอนใหญ่ขึ้น
      - **★★ 19 ก.ย.69 — กลับมาเป็นแถบเมนูซ้ายถาวรบนจอกว้าง (เจ้าของส่งรูปตัวอย่าง "อยากได้ประมาณนี้ แต่สีของเรา สัญลักษณ์ของเรา")**
        - **จอ ≥1100px = แถบซ้ายถาวร** (`body.has-sidebar` · `render()` ใส่ class ให้) · **จอแคบ = ☰ drawer เหมือนเดิม**
          · แถบเป็น **สีม่วงเข้ม** (`--sb-bg` ฯลฯ ใน globals.css) ทั้ง 2 โหมด + แคปซูล gradient ม่วงเดิมที่แท็บ active
        - หัวแถบ = **โลโก้ + "Oxlet Dashboard"** (`.nav-brand`) · ท้ายแถบ = **ผู้ใช้ + ปุ่มออกจากระบบ** (`.nav-foot`)
          → จอกว้างซ่อนโลโก้/ชื่อ/ปุ่มสามขีด/ปุ่มออกจากระบบบนหัวเว็บ แล้วโชว์ **ชื่อหน้าปัจจุบัน** (`.hdr-page`) แทน
        - `.hdr-page` มี **inline `display:none`** แล้วค่อยเปิดด้วย `!important` ใน media query — CSS ใหม่ไม่มา = หัวเว็บเหมือนเดิมทุกอย่าง
          (กติกาเดิม "โครงห้ามขึ้นกับ CSS ใหม่") · แท็บย้ายไปเป็นค่าคงที่ **`NAV_TABS`** ใน `render()` (ใช้ทั้งเมนูและชื่อหน้า)
        - แถบซ้าย **z-index 900** (ต่ำกว่า modal 1000–1200) · drawer มือถือยัง 1260 ตามเดิม
        - _ประวัติ: ส.ค.69 เคยเป็นแถบซ้าย → เปลี่ยนเป็น drawer ทุกจอตามที่ผู้ใช้ขอ → ก.ย.69 กลับมาเป็นแถบซ้ายตามรูปตัวอย่าง_
      - **★★ 19 ก.ย.69 — หน้าตากราฟแบบรูปตัวอย่าง (แท็บภาพรวม · helper อยู่เหนือ `initCharts`)**
        - เส้นตรง ไม่ระบายใต้เส้น (`_LINE_DS`) · แท่งมน (`_BAR_DS`) · เส้นตารางแนวนอนจาง แกน y ≤4 ขีด (`_scalesClean`)
        - ชี้แล้วขึ้น **กล่องขาวบอกทุกชุด + "รวม"** + **เส้นประแนวตั้ง** (ปลั๊กอิน `oxCrosshair`) · ตั้งค่ากลางใน `_chartLook()`
        - คำอธิบายสีใต้กราฟบอก **ยอดรวม** (`_legendTotals`) · โดนัทบอก **%** (`_legendPct`) + **ตัวเลขใหญ่กลางวง**
          (ปลั๊กอิน `centerText` → `options.plugins.centerText = {big, small}` · ตอนนี้ = % ปล่อยแล้ว)
        - **เส้นแนวโน้มติด `_trend:true`** → ไม่นับเข้ายอดรวม + ไม่โชว์ในกล่อง (เป็นค่าคำนวณ ไม่ใช่ยอดจริง)
        - **วัน/เดือนที่ยังมาไม่ถึง = `null` ไม่ใช่ 0** — เดิมท้ายกราฟเส้นดิ่งลงศูนย์ ดูเหมือนยอดตก
        - กราฟยอดปล่อย + โดนัท **อยู่แถวเดียวกัน** (เอา `span2` ออก) · กล่องกราฟสูง 240→270px
      - **★ 19 ก.ย.69 (เจ้าของแจ้ง "ไอคอนบางตัวเล็ก") — `ic()` ขยายไอคอน ≤16px ขึ้น 2px อัตโนมัติ**
        (index.html + seller.html · จุดเดียวครอบทั้งหน้า) · ไอคอน ≥17px คงเดิม · `.info-tip` 15→17px ·
        บอร์ด /track/ ไอคอนสเตป 13→15 · ธงบนการ์ด 13→16 · หน้าเบิก-คืน 🔍 13→16 · รูปย่อ 26→34px
        · **หน้าสแกนไม่ต้องแก้** (lucide วาดที่ 24px อยู่แล้ว — กฎ `i[data-lucide]{16px}` ใน base.html
        ไม่มีผลหลัง `createIcons()` เพราะ `<i>` ถูกแทนด้วย `<svg>` แล้ว · ขนาดคุมด้วย inline style บน `<i>` เท่านั้น)
      - **⚠️★ บทเรียนรอบนี้ (เจ้าของเปิดใช้จริงแล้วเมนูพังทันที — ต้องไม่ให้เกิดอีก)**: รอบแรกผมทำหัวข้อเป็น
        `<button>` + ครอบรายการด้วย `<div class="nav-grp">` → **ทั้งคู่ต้องมีกฎ CSS ใหม่ถึงจะหน้าตาถูก** ·
        พอเบราว์เซอร์/เซิร์ฟเวอร์ยังเสิร์ฟ `globals.css` ตัวเก่า → หัวข้อกลายเป็น**กล่องเทาปุ่มเบราว์เซอร์**
        และ `.ntab` (inline-flex) ไหลเป็น**แถวละ 2 ปุ่ม** = เมนูพังทั้งอัน
        - **กฎ: โครงเมนูห้ามขึ้นกับ CSS ที่เพิ่งเพิ่ม** — ใช้ element/คลาสที่มีสไตล์อยู่แล้ว
          (`.nav-sec` เป็น `<div>` · `.ntab`/`.nav-act` เป็น**ลูกตรงของ `#nav-slide`** ซึ่ง `flex-direction:column`)
          แล้วให้ CSS ใหม่เป็นแค่ "ของแต่ง" (ลูกศร/cursor/จัดขวา) ที่ขาดได้
        - **การพับใช้ inline `style.display` จาก JS ไม่ใช่ attribute `hidden`** — `.nav-act{display:flex}`
          (class) **ชนะ** กฎ `[hidden]` ของเบราว์เซอร์ → ต้องมี CSS ช่วย = ผูกกับเวอร์ชัน CSS อีก
        - **`:first-of-type` นับตามชนิด element** — พอ `.nav-sec` เป็น `<div>` ไปชนกับ `#nav-ind` (div เหมือนกัน)
          ที่อยู่ก่อนหน้า → กฎไม่ทำงาน เส้นคั่นโผล่เกิน · เปลี่ยนเป็นคลาส `.nav-sec.first` ที่ระบุเอง
        - **ทดสอบต้อง "ดูรูป" ไม่ใช่นับปุ่ม** — เทสต์รอบแรกนับ `:visible` ผ่านหมดทั้งที่เลย์เอาต์พัง ·
          ตอนนี้แคปรูป + วัดพิกัดจริง (ปุ่มอยู่คนละแถวไหม · เต็มความกว้างไหม) **และรันซ้ำโดยบังคับใช้ CSS ตัวเก่า**
          (`page.route` ยัด globals.css เวอร์ชันก่อนหน้า) เพื่อพิสูจน์ว่า degrade แล้วยังใช้งานได้
      - **★ 20 ก.ย.69 (รอบ 4 · ล็อกหน้าตาแล้ว) — เมนูไม่มีลูกศรพับ/กางอีกต่อไป**
        เจ้าของสั่ง *"ล็อกเมนูตามนี้เลย ไม่ต้องมีติ๊ก ให้เลื่อนลงเอา · ตั้งค่าไม่ต้องมีเลข 22"*
        - หัวข้อ **"หน้าหลัก" = ป้ายเฉยๆ** (ไม่ใช่ปุ่ม) · **แท็บ 8 อันโชว์ครบตลอด** ยาวเกินจอก็เลื่อนเอา
        - ปุ่ม **"ตั้งค่า" ไม่มีเลขจำนวนรายการ** (`.nav-cnt`) — เป็นทางเข้าหน้าหนึ่ง ไม่ใช่กองรายการที่ต้องนับ
        - `navSecHtml`/`navSecOn`/`toggleNavSec` **ยังอยู่ในโค้ด** (เผื่อของเดิมอ้างถึง) แต่เมนูไม่เรียกใช้แล้ว
          · จะเอาการพับกลับมาต้องถามเจ้าของก่อน — สั่งล็อกไว้ชัด
      - **★★★ 20 ก.ย.69 (รอบ 3 · สถานะปัจจุบัน) — เมนูซ้ายเหลือ "แท็บ + ปุ่มตั้งค่า" เท่านั้น**
        เจ้าของสั่ง *"เอาพวกนี้ไปรวมกับตั้งค่าสิ ทำไมยังไม่ไปรวม"* (รอบ 2 ยังเหลือ 2 หมวดในเมนู = ยังไม่พอ)
        - **`ADMIN_MENU` เหลือรายการเดียว** = ปุ่ม "ตั้งค่า" (`solo:true`) · เครื่องมือทั้ง **22 รายการ**
          อยู่ใน **`SETTINGS_MENU`** ทั้งหมด **5 กลุ่ม**: งานประจำวัน 4 · ข้อมูลดิบ 3 · พื้นฐาน 6 · ขั้นสูง 6 · ตรวจสอบ & Log 3
        - **เพิ่มเครื่องมือใหม่ = เติมใน `SETTINGS_MENU` ที่เดียว** (ได้ URL `?panel=<key>` อัตโนมัติ)
          · จะเอาอะไรกลับขึ้นเมนูซ้ายค่อยย้ายมา `ADMIN_MENU`
        - วัดจริงในเบราว์เซอร์: เมนูซ้าย = แท็บ 8 + "ตั้งค่า 22" · ในหน้าตั้งค่ากดได้ **20/22 เปิดเป็นหน้า**
          (อีก 2 ไม่ใช่พาเนล: ไปแท็บเบิก-คืนรถ · สั่งเขียนคะแนนลงชีต) · ไม่มี JS error
      - **★★ 20 ก.ย.69 (รอบ 2) — เมนูซ้ายเหลือ "ของที่ใช้บ่อย" · ของตั้งค่าย้ายเข้าหน้าเดียว**
        เจ้าของแจ้ง *"เมนูรกหูรกตา บางทีเยอะมากๆ"* + ยกตัวอย่าง Facebook ที่แยก **ตั้งค่าพื้นฐาน / ขั้นสูง**
        - **เดิม 7 หมวด 22 รายการ → ตอนนี้ 2 หมวด + ปุ่ม "ตั้งค่า" 1 ปุ่ม** (รวม 7 แถว)
          · **งานประจำวัน (4)**: แชทลูกค้า · เช็คชื่อ · พนักงาน · ลูกค้าหารถ
          · **ข้อมูลดิบ (3)**: ฐานข้อมูล (SQL) · **LINE ID พนักงาน** · Export ไทม์ไลน์รถ
            (เจ้าของทัก ก.ย.69 ว่า "LINE ID พนักงาน ก็เป็น raw data" — เป็นการ *ดู* ไม่ใช่ *ตั้งค่า* จึงย้ายออกจากหน้าตั้งค่า)
          · **⚙️ ตั้งค่า** → หน้า `?panel=settings` (`openSettings()` · `SETTINGS_MENU` 3 กลุ่ม **15 รายการ**:
            **ปุ่มนี้ทำหน้าตาเป็น "หัวข้อหมวด" (`.nav-sec`) เหมือนหมวดอื่น** แต่ลูกศรชี้ขวา = กดแล้วไปหน้านั้น
            ไม่ใช่กางรายการ (เจ้าของทักว่าปุ่มเดี่ยวๆ ดูแปลกแยก · กางจริงก็กลับไปรก 15 รายการเหมือนเดิม)
            พื้นฐาน 6 · ขั้นสูง 6 · ตรวจสอบ & Log 3) — การ์ดมีชื่อ + คำอธิบายใต้ชื่อ กดแล้วเปิดเป็นหน้าของตัวเอง
        - **เกณฑ์แบ่ง = ความถี่ที่เปิด** ไม่ใช่ "เรื่องเดียวกันไหม" — เปิดทุกวัน = อยู่ในเมนู ·
          ตั้งครั้งเดียวแล้วแทบไม่แตะอีก = อยู่ในหน้าตั้งค่า (ของเดิมเอา "ตั้งค่า 10 รายการ" มากินที่เท่ากับของที่ใช้ทุกวัน)
        - **เพิ่มรายการใหม่**: ใช้บ่อย → `ADMIN_MENU` · ตั้งค่า → **`SETTINGS_MENU`** (ได้ URL ของตัวเองอัตโนมัติ)
        - หมวดที่มี `solo:true` = ไม่วาดหัวข้อหมวด (ใช้กับปุ่ม "ตั้งค่า" ปุ่มเดียว)
        - **⚠️ `settingsGo()` ต้องปิดหน้าตั้งค่าก่อนแล้วค่อยเปิดหน้าใหม่** (หน่วง 40ms) — ไม่งั้นตัวแปลงหน้า
          จะเจอ "ลบ" กับ "เพิ่ม" ในจังหวะเดียวกันแล้วสลับหน้าไม่ทัน
        - วัดจริงในเบราว์เซอร์: เมนูเหลือ 7 แถว · ในหน้าตั้งค่ากดได้ **14/16 เปิดเป็นหน้า** (อีก 2 ไม่ใช่พาเนล
          คือ "กลุ่ม LINE ที่ดักเก็บ" ที่ไปแท็บเบิก-คืนรถ กับ "ส่งคะแนนเข้าชีต" ที่เป็นคำสั่ง) · ไม่มี JS error
      - **★★ 20 ก.ย.69 — เมนูจัดการเปิดเป็น "หน้า" ไม่ใช่หน้าต่างลอยแล้ว (เจ้าของสั่งซ้ำรอบ 2)**
        *"ไม่เอาหน้าต่างลอย ให้แบ่งเป็นหน้านั้นๆ เลย ฉันยังเจอหน้าต่างลอยหลายหน้าอยู่เลย"*
        - พาเนล **27 ตัวต่างคนต่างสร้างกล่องลอยเอง** (`position:fixed;inset:0`) → **ไม่ไล่แก้ทีละตัว**
          (นอกจากยาวแล้ว วันหลังมีคนเขียนเพิ่มแบบเดิมก็หลุดอีก) · ใช้ **MutationObserver ดักตอนถูกใส่เข้าหน้า
          แล้วแปลงเป็นหน้าเต็มที่จุดเดียว** — `_pageNext()` / `_pageify()` / `_pageClose()` (index.html ใกล้ `_PANEL_URL`)
        - **แปลงเฉพาะพาเนลที่เปิดจากเมนู** (ปุ่มตั้งธง `_pageNext(key)` ก่อนเรียก) · กล่องยืนยัน/รายละเอียดเคส
          ที่เด้งจากในพาเนล **ยังลอยเหมือนเดิม** เพราะเป็น dialog จริง (ถามแล้วกลับที่เดิม ไม่ใช่ย้ายหน้า)
        - **ทุกรายการได้ URL ของตัวเองอัตโนมัติ** (`?panel=<key>` · เติมเข้า `_PANEL_URL` ให้เอง) → ก๊อปลิงก์ส่งต่อได้
          · ปุ่ม Back ของเบราว์เซอร์กลับแดชบอร์ด · คีย์เดิมที่เคยแจกไปแล้ว (`employees`/`sql`/`meta`…) คงไว้ ห้ามเปลี่ยน
        - **วัดผลจริงในเบราว์เซอร์: 19/22 รายการเป็นหน้าแล้ว** · อีก 3 ไม่ใช่พาเนล (ไปแท็บเบิก-คืนรถ ·
          ดาวน์โหลดไฟล์ · สั่งเขียนคะแนนลงชีต) จึงไม่ต้องแปลง
        - **⚠️ 3 กับดักที่เจอตอนทำ (อย่าให้กลับมา)**
          1. **ห้ามประกาศตัวช่วยเป็น `const`/arrow** — `render()` ถูกเรียกตั้งแต่ต้นไฟล์ ซึ่ง**ก่อน**บล็อกนี้
             → `Cannot access '_pageKey' before initialization` แล้ว **หน้าพังทั้งหน้า** · ใช้ `function` (hoist) + `var`
          2. **การ "ย้าย" node นับเป็น `removedNodes` ด้วย** — ตอน `_pageify` ย้ายพาเนลเข้า `#dashboard-root`
             ตัวดักลบมองว่าปิดหน้า → **หน้าปิดตัวเองทันทีที่เปิด** · ต้องเช็ค `!document.contains(n)` ก่อน
          3. **ซ่อน `#dashboard-root` ทั้งก้อนไม่ได้** — `#nav-slide` (แถบเมนูซ้าย) อยู่ข้างในนั้น → แถบเมนูหายไปด้วย
             · ตอนนี้ซ่อน **ลูกของ root ทีละตัว ยกเว้น nav** แล้วคืนค่าเดิมตอนปิด
          4. `_pageKey()` คืน `''` ถ้าไม่ใช่ `open*()` — เคยไม่กรอง แล้วคำสั่งอย่าง `location.href='/track/export'`
             ทำให้เครื่องหมาย `'` หลุดเข้า onclick = **ปุ่มนั้นพังทั้งปุ่ม** (`Unexpected token 'export'`)
      - รายการทั้งหมดนิยามที่ **`const ADMIN_MENU`** ([index.html](dashboard/templates/dashboard/index.html)) — **เพิ่ม/แก้เมนูจัดการ = แก้ที่นี่ที่เดียว** (render วนลูปเอง) · ทุกปุ่มเรียก **`closeNav()` ก่อนเปิด modal** เพราะ drawer (z-index 1260) บังตัว modal (1000–1200)
      - **หัวเว็บเหลือแค่ "ตัวบอกสถานะสด"**: ชิปออนไลน์ + กระดิ่งแจ้งเตือน (มี badge ต้องเห็นตลอด ไม่ควรซ่อนใน drawer) · ลบ CSS `.admin-nav-menu` + handler click-outside ที่ตายแล้วออก
      - **แก้บั๊ก**: **"รายงานเข้าไลน์" (`openReportLine`) เดิมไม่มีปุ่มเรียกเลยสักที่** (ฟังก์ชันมีอยู่แต่เข้าไม่ถึงจาก UI ทั้งที่เอกสารบอกว่าอยู่ในเมนูจัดการ) — ใส่กลับในหมวด "ตั้งค่าระบบ" แล้ว
      - drawer **เปิด scrollbar แนวตั้ง** (`#nav-slide::-webkit-scrollbar`) ทับค่าฐาน `.nav-slide` ที่ซ่อนไว้ตอนยังเป็นแถบนอน — 21 รายการยาวเกินจอ ถ้าซ่อน scrollbar ผู้ใช้จะไม่รู้ว่ามีเมนูข้างล่างอีก
    - **สถานะเปิด/ปิด = class `nav-open` บน `<body>`** (ห้ามเก็บใน `#dashboard-root`) — เพราะ `render()` ล้าง `innerHTML` ทุกครั้ง ถ้าเก็บข้างในจะเด้งปิดเองทุกรอบ render
    - ไอคอน `menu`/`x` เพิ่มใน dict **`LUCIDE`** (index.html) แล้ว — dict นี้เป็น hardcode ไม่ได้โหลดจาก CDN **ใช้ไอคอนใหม่ต้องเพิ่ม path เข้า dict ก่อน** ไม่งั้น `ic()` คืน svg เปล่า
    - **แก้ CSS ต้อง bump `?v=` ที่ link globals.css** — มี 2 ที่ (index.html + seller.html) ต้องตรงกัน
    - **★ 20 ก.ย.69 — ตอนนี้มี 5 หน้า** (index · seller · sql · login · magic_link) ใช้เลขเดียวกันทั้งหมด
    - **⚠️★ ต้องรัน `collectstatic` ก่อน `restart` ทุกครั้งที่แก้ CSS/JS** — เว็บเสิร์ฟจากสำเนาใน `staticfiles/`
      ไม่ใช่ไฟล์ในโค้ด · และสั่งให้เบราว์เซอร์**จำไฟล์ 30 วัน** (`Cache-Control: max-age=2592000`)
    - **เหตุการณ์จริง 20 ก.ย.69**: หน้า UI deploy (`78ccded`) โดยไม่รัน collectstatic → เว็บส่ง **CSS เก่า 12 ส.ค.
      ภายใต้เลขใหม่ `?v=20260920a`** → เบราว์เซอร์ที่เปิดช่วงนั้นจำไฟล์ผิดไว้ในชื่อที่ถูก **รัน collectstatic ทีหลัง
      ก็ไม่หาย** (เมนูซ้ายพัง: โลโก้ขยายเต็มกล่อง ชื่อ 2 บรรทัดติดกัน) · แก้ด้วยการเปลี่ยนเลขเป็น `20260920b`
      · **กฎ: ถ้าเผลอเสิร์ฟ CSS เก่าภายใต้เลขใหม่ไปแล้ว ต้องเปลี่ยนเลขอีกรอบเสมอ** — Ctrl+F5 แก้ได้แค่เครื่องเดียว
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
  - **สิทธิ์สเตป (`STAGE_ROLES` · ปรับ ส.ค.69 รอบ 2)**: **"รับเข้า" ไม่มีใครกดได้** (`NO_ONE_STAGES` — รถเกิดที่รับเข้าตอนสร้างอยู่แล้ว · จัดซื้อเลยไม่มีปุ่มสเตป) · **โปรดักชัน (3)** รถรอถ่ายรูป/เช็คซ่อม/รถพร้อมขาย (เอาชงล้างออก) · **ช่าง (3)** ซ่อมเสร็จรอตรวจ/อะไหล่/งานเบาะ (เอาฟิล์มออก) · **ฝ่ายล้างรถ (2)** รอ QC ตรวจ + **ล้างเสร็จรถรอปล่อย** _(อัปเดตรอบ 4 — เดิมเป็น "รอเซลล์ตรวจ")_ · **เซลล์ (7)** **ตีกลับ QC** (=qc_show · ป้ายปุ่มเฉพาะเซลล์ผ่าน `STAGE_BUTTON_LABELS`/`stage_button_label()`)/พร้อมขาย/จอง/ไฟแนนซ์/**ตรวจขนส่ง**/ตรวจรถรอปล่อย/ปล่อยรถ (ตัดรอปิดการขาย + **ขายแล้ว** ออก) · **ฝ่ายทะเบียน = ทุกสเตปยกเว้น เบาะ/อะไหล่** (`REGIST_EXCLUDE` — ไม่ full สเตปแล้ว แต่ยัง `FULL_ROLES` ฝั่งจัดการ) · **รอปิดการขาย/รอตรวจสี/ฟิล์ม/ชงล้าง = ฝ่ายทะเบียน+สิทธิ์เต็มเท่านั้น** · `STAGE_FULL_ROLES={EXEC,PAINTIN}` (สิทธิ์เต็มสเตป · **QC ออกจากกลุ่มนี้แล้วรอบ 8 — เหลือ 4 ปุ่ม**) · แอดมิน=ไม่เปลี่ยนสเตป
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
    - **★ ส.ค.69 รอบ 10 (เจ้าของสั่ง) — ปลดธง "ยังไม่ได้ถ่ายรูป" ต้องมีหลักฐาน**: `FLAG_PROOF_REQUIRED = {"need_photo"}` ([constants.py](cars/constants.py)) — เอาติ๊กออก = ประกาศว่าถ่ายเสร็จ ต้อง **แนบรูปที่ถ่ายแล้ว + ใส่หมายเหตุ** (ติ๊ก "กลับเข้า" = แค่บอกว่ายังค้าง ไม่ต้องมีหลักฐาน)
      - `api_set_flags` รับ `note`/`media` เพิ่ม → เมื่อปลดสำเร็จ **สร้าง `ScanLog` ที่สเตปเดิม** (ไม่เปลี่ยนสเตป) พร้อมรูป → หลักฐานเข้าไทม์ไลน์รถ ย้อนดูได้ว่าถ่ายเสร็จตอนไหน · ข้อความใช้ `FLAG_DONE_NAME` ("ถ่ายรูปรถเสร็จแล้ว") ไม่ใช่ชื่อธง ไม่งั้นได้ประโยคขัดกันเอง
      - UI 2 จุด: หน้าสแกน แผง `#fpWrap` (`fpConfirm` · ใช้ `window.__scUpload` = ตัวอัปโหลดเดิม) · ป๊อปอัปบอร์ด `#flagModal` (`openFlagProof`/`doFlagProof` · ใช้ `_uploadInto` เดิม) — **กดยกเลิก = ติ๊กกลับให้อัตโนมัติ**
      - เพิ่ม `need_content`/`need_tire` เข้ากฎนี้ = เติมคีย์ใน `FLAG_PROOF_REQUIRED` จุดเดียว (UI ทั้ง 2 จุดต้อง sync `FLAG_PROOF` ใน JS ด้วย)
    - **★ ส.ค.69 รอบ 9 (เจ้าของสั่ง) — บังคับ "แนบรูป + ใส่หมายเหตุ" ทุกสเตป ทุกบทบาท**: เดิม `STAGE_FORCE_MEDIA` มีแค่ `{qc_release, release}` → สเตปอื่นกดเปลี่ยนรัวๆ ได้โดยไม่ทิ้งหลักฐาน ตามย้อนหลังไม่ได้ว่าใครทำอะไร/รถสภาพไหนตอนส่งต่อ
      - `STAGE_FORCE_MEDIA` / `STAGE_FORCE_NOTE` ([constants.py](cars/constants.py)) = **ทุกคีย์ใน `STAGE_KEYS`** ยกเว้นที่ใส่ใน **`PROOF_EXEMPT_STAGES`** (ตอนนี้ = `{"wash"}` · ดู 22 ก.ย.69) — ผ่อนสเตปไหนแก้จุดเดียว
      - **บังคับ 2 ชั้น**: UI ทั้ง 3 จุด (หน้าสแกน · ป๊อปอัปบอร์ด · หน้าเซลล์) **และ** เซิร์ฟเวอร์ `_proof_error(stage, note, media)` ([views.py](cars/views.py)) ที่ `scan_submit`/`api_set_stage`/`api_seller_set_stage`/`car_stage` — ปิดแค่ UI ไม่พอ ยิง API ตรงได้
      - **เช็คหมายเหตุ "ก่อน" ต่อผลเช็คลิสต์เสมอ** — ไม่งั้นผลเช็คลิสต์ที่ระบบเติมเองจะนับเป็นหมายเหตุ = กดผ่านได้โดยไม่พิมพ์อะไรเลย
      - `car_stage` (หน้า car_detail เก่า ไม่มีช่องแนบรูป) → เด้งไปหน้าสแกนพร้อมข้อความ แทนที่จะเป็นรูรั่วข้ามกฎ
      - **⚠️ เพิ่มสเตปใหม่ = ได้กฎนี้อัตโนมัติ** (gen จาก `STAGE_KEYS`) ไม่ต้องมาไล่เพิ่มเอง
    - **★ ส.ค.69 — ฝ่ายล้างรถไม่ต้องเห็นเช็คลิสต์ตรวจรถ** (`CHECKLIST_HIDE_ROLES={CARWASH}` + `checklist_stages_for(user)` ใน [roles.py](cars/roles.py)): ปุ่ม "ล้างเสร็จรถรอปล่อย" (`qc_release`) บังเอิญอยู่ใน `CHECKLIST_STAGES` → เด็กล้างรถเจอเช็คลิสต์ 15 ข้อซึ่งเป็นงาน "ตรวจสภาพรถ" ของ QC/เซลล์ · ซ่อนทั้งชุด เหลือแค่ รูป+หมายเหตุ ซึ่งเป็นงานเขาจริง · ความด่วนถูกล็อกอยู่แล้วผ่าน `READONLY_PRIORITY_ROLES`
    - **★ ส.ค.69 (เจอตอนทดสอบ) — `can_set_stage` กันสเตปที่ไม่มีอยู่จริง**: เดิมบทบาทสิทธิ์เต็ม/ฝ่ายทะเบียนเช็คแบบ "ไม่อยู่ในลิสต์ห้าม = ผ่าน" → ส่ง `stage=""` หรือคีย์มั่วมาก็ผ่าน **ทำให้รถกลายเป็นสเตปว่าง หลุดหายจากทุกคอลัมน์บนบอร์ด** (เจอจริงตอนฟอร์มส่งค่าว่าง) · เพิ่มเช็ค `stage not in STAGE_NAME → False`
    - **★ ส.ค.69 รอบ 8 (เจ้าของสั่ง) — QC เหลือ 4 ปุ่ม**: **เอา QC ออกจาก `STAGE_FULL_ROLES`** (เหลือ `{EXEC, PAINTIN}`) แล้วระบุปุ่มตรงๆ ใน `STAGE_ROLES` แทน → `paint_check` **"ตีกลับฝ่ายทะเบียน"** · `sales_check` **"รอตรวจเซลล์"** · `qc_show` **"แก้ไขรอตรวจขึ้นโชว์"** · `qc_release` **"แก้ไขรอตรวจรอปล่อย"** (ป้ายปุ่มจาก `STAGE_BUTTON_LABELS[QC]` ที่มีอยู่แล้ว)
      - **เลิกใช้ `QC_EXCLUDE`** — วิธี "ให้ทุกสเตปแล้วค่อยตัดออก" ทำให้ QC ยังเหลือ 13 ปุ่ม (รกเกินงานจริง) และทุกครั้งที่เพิ่มสเตปใหม่ QC จะได้ปุ่มนั้นฟรีโดยไม่ตั้งใจ · allow-list ตรงๆ ปลอดภัยกว่า
      - QC ยังอยู่ใน `FULL_ROLES` (จัดการรถ/ผู้ใช้) เหมือนเดิม — เปลี่ยนแค่ "ปุ่มสเตป"
    - **★ ส.ค.69 รอบ 3 (เจ้าของสั่ง)**: **"ขายแล้ว" (`sold`) เอาออกจากเซลล์** → ฝ่ายทะเบียน(+สิทธิ์เต็ม)เป็นคนกด · **QC ไม่ full สเตปแล้ว** — เพิ่ม **`QC_EXCLUDE`** _(ยกเลิกไปแล้วรอบ 8 — QC ระบุ 4 ปุ่มตรงๆ แทน)_ = show/reserve/finance/transport_check/closing/release/sold (ปุ่มฝั่งขาย) **แต่คงไว้ `sales_check` + `qc_release`** เพราะเป็นงาน "ตรวจ" ของ QC เอง · logic รวมที่ helper **`_stage_exclude(role)`** ใน [roles.py](cars/roles.py) (ใช้ทั้ง `allowed_stages` และ `can_set_stage` — แก้ที่เดียว)
  - **board (board เปลี่ยนได้ตรงจาก UI ผ่อน scan-only)**: `api_set_stage`/`api_seller_set_stage` ใช้ `can_set_stage` (ไม่ใช่ `_direct`) · `cars_api`/`car_json` ส่ง `priority`/`priorityColor` · dashboard.html การ์ดสีจาก priority + dropdown ความด่วน + ปุ่มถ่ายคอนเทนต์ + upload รูปในกล่องยืนยันสเตปบังคับ · `seed_role_accounts` = **10 บัญชีทดสอบ** (รหัส `1234` · exec/regist/qc/paintin/purchase/prod/tech/wash/sales/admintrk)
- **★★ 22 ก.ย.69 — 6 เรื่องที่เจ้าของแจ้งรวดเดียว (QR/จัดซื้อ/ชงล้าง/ปุ่ม QC)**
  - **ค้นหาทะเบียนในหน้า `/track/`** (`?q=` · `cur_q`) — เดิมมีแต่ตัวกรองสาขา/สเตป **ไม่มีช่องค้น**
    ทั้งที่หน้างานจำ "ทะเบียน" ไม่ใช่รหัสรถ · ค้นได้ทั้ง ทะเบียน/ทะเบียนเดิม/รหัสรถ/ยี่ห้อ/รุ่น
    · **ตัดช่องว่างกับขีดก่อนเทียบ** (คนพิมพ์ทั้ง `1กก1234` และ `1กก 1234`)
  - **`Car.price` "ราคาขาย (บาท)"** (migration **0018**) — เดิมราคามีแต่ของที่นำเข้าจาก Car Spend
    (`extra["price"]` แก้ไม่ได้จากหน้าเว็บ) → จัดซื้อกรอกเองไม่ได้ · เพิ่มช่องใน **ฟอร์มเพิ่ม/แก้รถ
    (`CarForm`) + ฟอร์มเพิ่มรถฝั่งแดชบอร์ดขาย (`ta_price` → `api_add_car`)**
    · **`_price_show(car)`** = ช่องในระบบชนะของนำเข้าเสมอ (ใช้ทั้ง `car_json`/`cars_api`)
    · `need_match` (จับคู่รถกับความต้องการลูกค้า) อ่าน `c.price` ก่อน `extra["price_num"]`
  - **★ ปุ่ม "เพิ่มรถ" ย้ายออกจากหัวเว็บ (ต้นเหตุ "จัดซื้อเข้าหน้าเว็บแล้วเพิ่มรถไม่ได้")**
    — สิทธิ์ถูกอยู่แล้ว (`can_add_car` มี PURCHASING) แต่ปุ่มอยู่ใน `#trkHead` ซึ่ง **ถูกซ่อนทั้งก้อน
    ตอนฝังในกรอบ** (`html.embedded`) → ใครเข้าทางแท็บ "สถานะรถ"/หน้าเซลล์ **ไม่เห็นปุ่มเลย**
    · ย้ายไปไว้ **เหนือการ์ด KPI (นอก `#trkHead`)** → เห็นทั้ง 2 ทาง · วัดจริงในเบราว์เซอร์: ปุ่มอยู่ที่ y=168
    (เคยลองวางแถวตาราง = y=1213 ต้องเลื่อนลงทั้งหน้าถึงเจอ → เท่ากับหาไม่เจอเหมือนเดิม)
  - **ชงล้าง (`wash`) ไม่บังคับรูป/หมายเหตุแล้ว** — `PROOF_EXEMPT_STAGES = {"wash"}` (จุดเดียว
    คุมทั้งเซิร์ฟเวอร์และ UI ทั้ง 2 หน้า) · เหตุผล: ส่งรถเข้าคิวล้าง = **ย้ายคิว ไม่ใช่ทำงานกับตัวรถ**
    ไม่มีอะไรให้ถ่าย · **ขาออกยังบังคับเหมือนเดิม** (ล้างเสร็จ `qc_show`/`qc_release` ต้องแนบรูป)
  - **★ ปุ่ม QC 2 ตัวเลิกวนกลับหาตัวเอง — `STAGE_BUTTON_TARGET`** ([roles.py](cars/roles.py)):
    QC กด **"แก้ไขรอตรวจขึ้นโชว์" / "แก้ไขรอตรวจรอปล่อย"** → ไป **`sales_check` (รอเซลล์ตรวจ)**
    ทั้งคู่ (เจ้าของเคาะเอง) · ของเดิมพารถกลับเข้า `qc_show`/`qc_release` = **คิวของ QC เอง →
    รถค้างไม่มีใครรับช่วง** · `_stage_options` คืน **"สเตปปลายทางจริง"** เป็น key แล้ว
    (การบังคับรูป/เช็คลิสต์/การบันทึก อิงปลายทางเสมอ) + **เรียงตามปลายทาง → ปุ่มที่ไปที่เดียวกันอยู่ติดกัน**
    (ตอบข้อ "ย้ายแก้ไขรอตรวจขึ้นโชว์ มาคู่กับรถรอเซลล์ตรวจ")
    · **ผลข้างเคียงที่ต้องรู้: QC เหลือปลายทางจริง 2 ที่ (ตีกลับฝ่ายทะเบียน / รอเซลล์ตรวจ) แต่มี 3 ปุ่ม
      ที่ไปรอเซลล์ตรวจเหมือนกัน** — ต่างกันแค่คำบนปุ่ม (เจ้าของขอให้คงไว้ทั้งคู่) ยุบเหลือปุ่มเดียวได้ถ้าจะเอา
  - **⚠️★ 3 กับดักที่เจอตอนทำ (อย่าให้กลับมา)**
    1. **แทรกฟังก์ชันใหม่ไว้ "ก่อน `def X`" = ขโมย decorator ของ X** — ผมแทรก `_price_show` หน้า
       `def car_json` ซึ่งมี `@login_required` อยู่บรรทัดบน → **`car_json` กลายเป็น public** (หลุด auth)
       และ `_price_show` ถูกห่อด้วย decorator จนเรียกไม่ได้ · จับได้เพราะทดสอบแล้ว `AttributeError:
       'Car' object has no attribute 'user'` · **anchor ที่ `def X` ต้องดูบรรทัดเหนือมันเสมอ**
    2. **`T(k)` ของหน้า /track/ คืน "ชื่อคีย์" เมื่อไม่มีในดิก** → ปุ่มใหม่ที่ใส่ `data-i18n="addCar"`
       โชว์คำว่า `addCar` แทนภาษาคน · **เพิ่ม `data-i18n` ใหม่ = ต้องเติมคำแปลใน `UT` ครบ 4 ภาษา**
       (มี `data-i18n-ph` สำหรับ placeholder ด้วย)
    3. **`const` ที่ประกาศระดับบนสุดของ `<script>` ธรรมดา ไม่ได้อยู่บน `window`** → เทสต์ที่เขียน
       `window.FORCE_MEDIA` ได้ `undefined` แล้ว **ผ่านแบบหลอกๆ** · ต้องอ้างชื่อเปล่า `FORCE_MEDIA`
       (บทเรียนเดียวกับ `window._soChart` เมื่อ ก.ย.69 — พลาดซ้ำรอบที่สอง)
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

### 🚗 ระบบเบิก-คืนรถ (checkout/ · เฟส 2 ส.ค.69) — "กดในเว็บ บอทสรุปเข้ากลุ่ม LINE"
แทนการพิมพ์ "เบิกรถ/คืนรถ" ในกลุ่ม LINE ล้วน (เดิมไม่มี state — ไม่รู้ว่ารถอยู่กับใคร ใครเบิกไม่คืน ต้องมีคนไล่ทวงรูปเอง)
- **เลือกแบบ C (ลูกผสม) ตามที่เจ้าของเคาะ**: คนงาน**สแกน QR ที่รถ** (ซึ่งทำอยู่แล้วทุกวัน) → กดเบิก/คืนในหน้าสแกน → **บอทโพสต์สรุปเข้ากลุ่ม LINE** ให้หัวหน้าเห็น/อนุมัติเหมือนเดิม
  - เหตุผล: เว็บล้วน = หัวหน้าไม่เห็นความเคลื่อนไหว ระบบจะถูกเมิน · LINE ล้วน = ต้องเดาใจจากข้อความ ไม่มี state
- **[checkout/constants.py](checkout/constants.py)** — `PURPOSES` **7 ประเภท** (สังเคราะห์จาก log จริง: ตรวจขนส่ง/เข้าศูนย์/ส่งลูกค้า/ไฟแนนซ์/ย้ายสาขา/**ไปดูรถ-รับรถเข้าใหม่ (จัดซื้อ)**/งานทั่วไป) = **กดปุ่ม ไม่ต้องพิมพ์** → นับสถิติได้ (ของเดิมพิมพ์อิสระ นับไม่ได้เลย)
  - **★ ก.ย.69 เพิ่มหมวด `buying` "ไปดูรถ / รับรถเข้าใหม่ (จัดซื้อ)"** — จาก log 10 วัน: "เบิกรถไปดูรถที่พานทอง" · "เบิกรถ เข้าใหม่ 739 กลับชลบุรี" เดิมตกไปอยู่ "ส่งลูกค้า" (ผิด คนละทีมคนละงาน) · **ใน `_PURPOSE_HINTS` ต้องวาง `buying` ไว้ก่อน `customer`** ไม่งั้นคำว่า "ดูรถ" ของ customer กินไปก่อน
  - `DEFAULT_CHECKLIST` (ตอนเบิก) = **บังคับ 2 ข้อ** (รอบคัน ≥2 · เลขไมล์ 1) + ตัวเลือก 3 · `RETURN_CHECKLIST` (ตอนคืน) บังคับ 2 รูป
  - **★★ ก.ย.69 — "ถ่ายครบมุมไหน" ให้คนงานติ๊กเอง (เจ้าของเลือกแนวทาง A)**
    - `SHOT_ANGLES_OUT` **6 มุมตอนเบิก** (ด้านซ้าย/ด้านขวา/ด้านหน้า/ด้านหลัง/ห้องเครื่อง/เลขไมล์) · `SHOT_ANGLES_IN` **3 มุมตอนคืน** (รอบคัน/เลขไมล์/จุดที่มีปัญหา — อันหลังไม่บังคับ)
    - **UX ที่เจ้าของขอ**: อัปรูป **รวมทีเดียวหลายไฟล์** แล้ว **ติ๊ก checkbox** ว่าถ่ายครบมุมไหน — ไม่ใช่ช่องอัปแยก 6 ช่อง (กดน้อยกว่า) · มีปุ่ม **"ครบทุกมุม"** ติ๊กรวดเดียว
    - **ทำไมให้คนติ๊กแทนให้ AI เดา**: แม่น 100% · ไม่มีค่าใช้จ่ายต่อรูป · ไม่ต้องรอ AI ตอบตอนคนยืนอยู่หน้ารถ
    - **⚠️ ติ๊กไม่ครบ = ยังกดยืนยันได้** ระบบแค่จดว่าขาดมุมไหน (`missing_shots()`) → โชว์ให้หัวหน้าเห็นเป็นชิป **"ขาด N"** ในตาราง + ใส่ในข้อความสรุปเข้ากลุ่ม LINE
      **ห้ามเปลี่ยนเป็นบล็อกไม่ให้ออกรถ** — บทเรียนเดิม: บังคับเยอะ = คนเลิกใช้ระบบ กลับไปพิมพ์ในกลุ่มเหมือนเดิม
    - เก็บที่ `CarMovement.shots_out` / `shots_in` (JSON list ของคีย์ · migration **0006_movement_shots**) · เซิร์ฟเวอร์กรองคีย์ด้วย `_clean_shots()` (กันส่งคีย์มั่ว)
    - UI อยู่ใน [scan.html](templates/scan.html) `ckRenderShots()`/`ckAllShots()`/`ckShotWarn()` + CSS `.sc-shots`/`.sc-shot` (2 คอลัมน์ · ช่องติ๊ก 20px กดง่ายบนมือถือ)
    - **เพิ่ม/แก้มุม = แก้ `SHOT_ANGLES_*` ใน [constants.py](checkout/constants.py) ที่เดียว** (หน้าสแกนรับผ่าน `ck_shots_out`/`ck_shots_in` จาก `_checkout_ctx`)
  - **⚠️ ตั้งใจบังคับน้อย**: seed เดิมมี 7 ข้อ (~11 ไฟล์/ครั้ง) แต่ log จริงคนส่ง 1-3 รูป → บังคับเยอะ = ไม่มีใครทำตาม · แก้เพิ่มได้ทีหลังผ่าน `ChecklistConfig`/`ChecklistItem` ในฐานข้อมูล (คีย์ `WEB_CONFIG_KEY="__web__"`)
- **API** (`login_required` · csrf_exempt เพราะหน้าสแกนโพสต์ JSON): `POST /checkout/api/car_out` · `POST /checkout/api/car_return` — ใช้ตัวอัปโหลดเดิม `/track/api/upload` แล้วส่ง `media:[{id,video}]` มา · เก็บ token ลง `MovementPhoto.file.name` (วิธีเดียวกับ `Car.photo`)
- **📁 รูปเบิก/คืน → Google Drive โฟลเดอร์ของรถคันนั้น** (เหมือนรูปสเตป — ใช้ท่อเดียวกันทั้งหมด)
  - หน้าสแกนเรียก `window.__scUpload(file, car.code)` → `/track/api/upload` **ไม่ส่ง `target`** → เข้า Drive ถ้าตั้ง `GDRIVE_*` (ไม่ตั้ง = ดิสก์ VPS) · โฟลเดอร์ต่อรถจาก `_ensure_car_folder()`
  - **★ ก.ย.69 — `_label_movement_media(m, phase)`** ([checkout/views.py](checkout/views.py)): ตั้งชื่อไฟล์ใน Drive เป็น **`เบิกรถ(ใหม่) 9ก.ย.69 11-02 01.jpg`** / **`คืนรถ(ใหม่) 9ก.ย.69 12-52 01.jpg`**
    - เดิม**ไม่ตั้งชื่อเลย** → กองเป็น `IMG_1234.jpg` ในโฟลเดอร์รถ แยกไม่ออกว่ารูปไหนตอนเบิก/ตอนคืน ใครถ่าย เมื่อไหร่
    - **เลขลำดับเติม 0 (`01`,`02`)** ให้ Drive เรียงถูก · ใช้ `_safe_filename`/`_THAI_MON` ชุดเดียวกับ `cars.views._label_stage_media` (อย่าเขียนกติกาชื่อไฟล์ซ้ำ)
    - best-effort — Drive ล่ม/ไม่ตั้งค่า = ไม่เปลี่ยนชื่อ ไม่ทำให้การเบิก/คืนพัง (ลิงก์แสดงผลอิง id ไม่ใช่ชื่อ)
  - **★ ดูรูปจากหน้าเว็บได้แล้ว**: `_mv_json` ส่ง `media:{out:[],in:[]}` (สร้าง URL ด้วย `cars.views._media_urls`) → ตารางโชว์ **thumbnail 26px กดเปิดไฟล์เต็ม** (`thumbs()` · เกิน 3 รูปโชว์ `+N` · โหลดรูปไม่ขึ้น → `imgFail()` เปลี่ยนเป็นไอคอน)
    - **⚠️ ต้อง `prefetch_related("photos")` + ใช้ `len(list(m.photos.all()))` ไม่ใช่ `.count()`** — ตารางโหลด 1000 แถว ถ้ายิง query ต่อแถวจะได้ 2000 query · วัดแล้ว: 72 เคส = **2 query**
    - เคสที่นำเข้าจาก log โชว์เป็น**ตัวเลขเทา** (รู้ว่าส่งกี่ไฟล์ในกลุ่ม แต่ไฟล์อยู่ใน LINE ไม่ได้อยู่ในระบบ)
- **[checkout/lineout.py](checkout/lineout.py)** — สรุปเข้ากลุ่ม (ข้อความหน้าตาใกล้เคียงที่คนพิมพ์กันอยู่ จะได้คุ้นทันที)
- **★★ ก.ย.69 — เลือกกลุ่ม LINE ที่จะ "ดักเก็บข้อมูล" (ฟังก์ชันหลักของเฟสนี้ · เจ้าของย้ำว่าสำคัญที่สุด)**
  - **KVStore `checkout_line_config`** = `{group_id, listen, send}` — **แยก "อ่าน" กับ "เขียน" ออกจากกัน**
    - `listen` = บอทอ่านข้อความในกลุ่มนี้แล้วสร้างเคสให้ · `send` = ให้บอทโพสต์สรุปกลับเข้ากลุ่ม
    - **`send` ปิดโดยปริยาย** (`lineout.send_on()` · เจ้าของสั่ง ก.ย.69: *"อ่านอย่างเดียวก่อน อย่าเพิ่งส่งอะไร"*) — เดิม `_push` ใช้ `cfg.get("enabled", True)` = **ส่งเป็นค่าเริ่มต้น** ซึ่งอันตราย
  - **พาเนล "⚙️ กลุ่ม LINE" ในหน้า `/checkout/`** (`api_line_config` GET/POST): dropdown เลือกกลุ่มที่บอทรู้จัก (KVStore `line_groups`) หรือวาง group id เอง · ติ๊ก listen/send · โชว์ Webhook URL ที่ต้องไปตั้ง + เตือนเมื่อยังไม่มี token / ยังไม่เลือกกลุ่ม / เลือกแล้วแต่ไม่ติ๊กเก็บ
  - **`ingest_group_events(data)`** ([checkout/views.py](checkout/views.py)) — hook จาก `line_webhook` ผ่าน `_checkout_ingest()`
    - **เก็บเฉพาะข้อความที่ parser จับ pattern ได้** (เบิก/คืน/น้ำมัน/เลขทะเบียน) — ไม่ดูดทั้งกลุ่มลง DB
    - `out` = สร้างเคสใหม่ · `in` = ปิดรอบที่ค้างของคนนั้น · `fuel` = ติดธง ⛽ ให้รอบที่เปิดอยู่ · `plate_only` = เติมทะเบียน
    - หาเจ้าของรอบด้วย **LINE user id ก่อน** ไม่เจอค่อยเทียบชื่อ (`_open_of`)
    - **กัน webhook ซ้ำ** ด้วย KVStore `checkout_seen_msgs` (เก็บ message id ล่าสุด 300)
    - **ข้ามกลุ่มอื่นทั้งหมด** — เทียบ `groupId` กับที่ตั้งไว้เท่านั้น
    - **⚠️ รันใน daemon thread** (`_checkout_ingest`) — การเทียบชื่อเล่นต้องอ่านชีตพนักงาน ครั้งแรกหลังรีสตาร์ทกินหลายวินาที **ห้ามบล็อก webhook** ไม่งั้น LINE timeout แล้ว retry รัว · ปิด DB connection ท้าย thread เอง
  - **`CarMovement.source`** (migration **0005_movement_source**) = `web` (กดในเว็บ) · `line` (บอทเดาจากกลุ่ม — **ยังไม่มีคนยืนยัน**) · `import` (นำเข้าจาก log) → ตารางติดป้าย **LINE** สีฟ้า + มีตัวกรอง "จากกลุ่ม LINE" ให้ไล่ตรวจ
  - **★★ ก.ย.69 — `_unwrap_payload()` แกะห่อที่ n8n ส่งมา (ต้นเหตุ "push ได้ แต่เก็บข้อความไม่ได้")**
    - **push กับ receive คนละเส้นทางกัน**: push ใช้แค่ `LINE_CHANNEL_ACCESS_TOKEN` + group id → ทำงานได้โดยไม่ต้องมี webhook เลย · **receive ต้องให้ข้อความวิ่งมาถึงเซิร์ฟเวอร์นี้จริงๆ** → "บอทตัวอื่นส่งเข้ากลุ่มได้" **ไม่ได้แปลว่า** การดักเก็บจะทำงาน
    - n8n ส่ง body มาได้หลายทรงแล้วแต่ต่อโหนดยังไง: `{"body":{...}}` · `{"json":{...}}` · `[{...}]` · **event เดี่ยว** (พบบ่อยสุด เพราะ n8n แตกเป็น item ทีละอันอยู่แล้ว)
    - เดิม `_extract_group_events` รับ **flat `{groupId}`** ได้ → **group id เข้า dropdown มีชื่อกลุ่ม** แต่ `ingest_group_events` อ่านแค่ `data["events"]` → **ข้อความไม่ถูกอ่านสักข้อความ** = อาการ "ตั้งค่าครบแล้วแต่ไม่มีเคสเลย"
    - `_unwrap_payload()` normalize ทุกทรงให้เป็น `{"events":[...]}` ก่อน แล้วใช้ทั้ง `line_webhook` และ `line_group_ingest` · **ทดสอบครบ 7 ทรง** (LINE raw / body / json ซ้อน / event เดี่ยว / list / list ห่อ body / แค่ groupId)
    - **★ โหนดสำเร็จรูปสำหรับ n8n**: [deploy/n8n_send_chat_to_oxlet.json](deploy/n8n_send_chat_to_oxlet.json) — ก๊อปทั้งไฟล์แล้ว **วาง (Ctrl+V) บน canvas ของ n8n ได้เลย** · เหลือแค่ใส่ `CRON_SECRET` ในช่อง header แล้วลากเส้นจาก **Webhook** มาเข้าโหนดนี้ · body ใช้ `{{ JSON.stringify($json.body || $json) }}` (ได้ทั้งกรณีต่อจาก Webhook ตรงๆ และกรณีมีโหนดคั่น)
    - **★ วินิจฉัยจริงที่เจอ (ก.ย.69)**: workflow n8n ต่อเป็น `Webhook → Get Group Summary → Send Group Info` — โหนดที่ยิงมาหาเราส่ง **ผลของ Get Group Summary** (`{groupId, groupName}`) **ไม่ใช่ body ดิบที่ LINE ส่งมา** → กลุ่มเข้า dropdown ครบ 6 กลุ่มพร้อมชื่อ แต่ `events=0` ตลอด · **แก้ที่ n8n**: ต่อ `Webhook → HTTP Request` ตรงๆ แล้วส่ง body = `{{ $json }}` (ทั้ง item ของ Webhook node — `_unwrap_payload` แกะ `.body` ให้เอง) · **ไม่ต้องมี Get Group Summary** เพราะเซิร์ฟเวอร์ดึงชื่อกลุ่มเองอยู่แล้วใน `_store_line_groups`
    - `line_group_ingest` ตอบ **`events` + `textEvents` + `forGroup` + `listening`** กลับไปด้วย (`forGroup` = ข้อความที่ส่งมาตรงกับกลุ่มที่ตั้งดักเก็บกี่ข้อความ) → เปิด execution ใน n8n แล้วรู้ทันทีว่า forward body มาครบไหม (ได้ `0` = ส่งมาแต่ groupId)
  - **★ ก.ย.69 — `line_group_ingest` (ทาง n8n) ก็ต้อง ingest ด้วย**: เดิม hook `_checkout_ingest` อยู่แค่ใน `line_webhook` → ถ้า LINE channel ชี้ Webhook URL ไป **n8n** (ตั้งได้ที่เดียวต่อ channel) ข้อความจะเข้าทาง `/api/line/group_ingest` ทั้งหมด แล้ว **ไม่เก็บอะไรเลยโดยไม่มีใครรู้**
  - **★★ ก.ย.69 — `line_ingest_last` จด "หน้าตา body" ตอนอ่าน event ไม่ได้** (`_ingest_debug()` ใน [dashboard/views.py](dashboard/views.py))
    - **ปัญหาที่แก้**: heartbeat บอกได้แค่ `events = 0` ซึ่ง **ยังแยกไม่ออก** ว่า n8n ส่ง `{groupId}` มาแทน body ดิบ / ส่งเป็นสตริง JSON ซ้อน / หรือ **body ว่างเปล่า** → ไล่ต่อไม่ได้ ต้องเดา (เสียเวลาไป 3 รอบ)
    - เก็บ `{at, path, bytes, parsedType, topKeys, preview(600 ตัว)}` — **เฉพาะตอน events=0** + **ทับค่าเดิมทุกครั้ง** (เป็นร่องรอยดีบัก ไม่ใช่คลังข้อมูล)
    - `checkout_status` โชว์เป็น **ข้อ 2.5** + สรุปสาเหตุตามหลักฐานจริง (body ว่าง / ส่งคีย์อื่นมา) — เลิกเดาเหมาว่า "ส่งมาแต่ groupId" เสมอ
    - **สาเหตุจริงที่เจอ (ก.ย.69)**: body = `{}` (2 bytes) เพราะโหนด HTTP ใน n8n **รับ input จากโหนดที่ไม่มีข้อมูล** (ต่อท้าย HTTP node อื่น) → สูตร `$json.body || $json` ได้ `{}`
      **แก้ด้วยการอ้างชื่อโหนดตรงๆ**: `{{ JSON.stringify($('Webhook').first().json.body) }}` → วางโหนดไว้ตรงไหนในสายก็ทำงาน (แก้ใน [deploy/n8n_send_chat_to_oxlet.json](deploy/n8n_send_chat_to_oxlet.json) แล้ว · **ชื่อโหนดต้องตรงของจริง** ไม่งั้น expression พัง = n8n ไม่ยิงออกมาเลย)
    - `_unwrap_payload` รองรับ **body ที่เป็นสตริง JSON** เพิ่มแล้ว ทั้งชั้นนอก (`"{...}"`) และชั้นใน (`{"body": "{...}"}`) — n8n ตั้ง Body=JSON แล้วใส่ `JSON.stringify(...)` จะโดน encode ซ้ำ · **ทดสอบครบ 11 ทรง**
  - **★ ⚠️ `chatTotal` ใน response ของ `line_group_ingest` = ยอด "ก่อน" รอบนี้** — `_checkout_ingest` ทำใน **daemon thread** (ห้ามบล็อก webhook) เลยยังเขียนไม่เสร็จตอนตอบกลับ → **ยิงรอบ 2 ถึงเห็นเลขขยับ** · เคยทำให้เข้าใจผิดว่า "ไม่เก็บ" ทั้งที่เก็บแล้ว · ตอนนี้แนบ **`lastStore`** (= `chat_store_last` ของรอบก่อน) ไปด้วย · **ยอดจริงดูที่ `manage.py checkout_config`**
  - **★★ ก.ย.69 — เตือนเองเมื่อ `migrate` ค้าง** ([schema_check.py](dashboard/services/schema_check.py))
    - **เหตุการณ์จริง**: deploy แล้ว `git pull` แต่**ลืม `migrate`** → โค้ดใหม่เขียนคอลัมน์ที่ยังไม่มีในตาราง
      → ข้อความที่วิ่งเข้ามา **ถูกทิ้งทั้งหมดแบบเงียบ** (`saved: 0, skipped: 1`) เพราะงานเก็บอยู่ใน
      background thread · ร่องรอยไปโผล่แค่ใน KV `chat_store_last` ที่ไม่มีใครเปิดดู
    - เจ้าของสั่ง: *"ถ้าไม่เข้าฐานข้อมูล ก็ช่วยแจ้งมาด้วย"* → `pending_migrations()` (cache 60 วิ) ร้องใน **3 ที่**:
      **response ที่ตอบ n8n** (`ok:false` + `pendingMigrations` + `warning` — เห็นทันทีใน execution) ·
      **`checkout_status` บรรทัดแรกสุด** · **หน้าสถานะระบบของแอดมิน** (issue ระดับ `err`)
    - **⚠️ `MigrationExecutor.migration_plan()` คืน `(Migration, ถอยหลังไหม)` ไม่ใช่ `(app, name)`** —
      เผลอ unpack เป็น 2 ตัวแล้วต่อสตริงจะได้ชื่อห้อย `.False` (เจอตอนทดสอบ · แก้แล้ว)
  - **★ `checkout_ingest_last`** — งานใน daemon thread เดิม `except Exception: pass` เฉยๆ **พังเมื่อไหร่ก็เงียบสนิท** (คนละ thread กับ response ไม่มีใครเห็น error) → ตอนนี้จด `{at, error}` ลง KV
  - **วิธียืนยันว่าฝั่งเซิร์ฟเวอร์ปกติ โดยไม่ผ่าน n8n/LINE** (แยกให้ขาดว่าปัญหาอยู่ฝั่งไหน):
    ```bash
    cd /opt/oxlet && SECRET=$(grep -m1 '^CRON_SECRET=' .env | cut -d= -f2-) && \
    curl -s -X POST "$SITE/api/line/group_ingest" -H "X-Cron-Secret: $SECRET" \
      -H "Content-Type: application/json" \
      -d '{"events":[{"type":"message","source":{"type":"user","userId":"Utest…"},"message":{"id":"test-1","type":"text","text":"ทดสอบ"}}]}'
    ```
    ได้ `"events": 1` = เซิร์ฟเวอร์ถูกต้องครบ → ที่เหลือเป็นเรื่อง n8n 100%
  - **★ heartbeat `line_webhook_last`** (`_webhook_beat()` ใน [dashboard/views.py](dashboard/views.py)) — จด `{at, path(webhook|n8n), events, hits, sigFail}` ทุกครั้งที่ webhook เข้า **รวมตอนลายเซ็นไม่ผ่าน (403)** · ไม่มีตัวนี้ = เวลาข้อมูลไม่เข้าจะ **แยกไม่ออกว่า LINE ไม่ยิง / ยิงแล้วลายเซ็นไม่ผ่าน / ยิงถึงแล้วแต่ไม่ตรงกลุ่ม**
    - ⚠️ `timezone` **ไม่ได้ import ระดับไฟล์** ใน `dashboard/views.py` → ต้อง `from django.utils import timezone as _tz` ในฟังก์ชัน ไม่งั้น NameError โดน `except` กลืน = heartbeat ไม่เขียนแบบเงียบ
  - **⚠️ อย่าสรุปจาก heartbeat อย่างเดียว** — `line_webhook_last` เพิ่งมี ก.ย.69 **นับตั้งแต่รีสตาร์ทเท่านั้น** · หลักฐานย้อนหลังที่เชื่อได้คือ **`line_groups[gid].lastSeen`** (บอทได้ยินกลุ่มนั้นล่าสุดเมื่อไหร่ — มีมานานแล้ว)
    - **ลายเซ็นชี้ขาด**: `lastSeen` สดๆ (ไม่กี่ ชม.) **แต่** `checkout_seen_msgs` = 0 → **ตัว forward ส่งมาแต่ `groupId` ไม่ได้ส่งตัวข้อความ** (ไม่ใช่ "webhook ไม่ถึง")
  - **`python manage.py checkout_config [--store-chat on|off] [--customer-chat on|off] [--listen on|off] [--send on|off] [--auto-employee on|off] [--group Cxxx]`** ([checkout_config.py](checkout/management/commands/checkout_config.py)) — ดู/ตั้งค่าจาก SSH ตรงๆ **ไม่ต้องเปิดเว็บ**
    - ทำขึ้นเพราะเวลาตั้งผ่านหน้าเว็บแล้วข้อมูลยังไม่เข้า **แยกไม่ออก**ว่า ลืมกดบันทึก / เบราว์เซอร์ค้างหน้าเก่า / ค่าไม่ถูกเก็บจริง — คำสั่งนี้อ่านกลับจาก DB หลังเขียนเสมอ
    - ไม่มีเรียกใช้ = แค่โชว์ค่าปัจจุบัน + จำนวนแชทที่เก็บแล้ว + เตือนถ้ายังไม่ได้เปิดเก็บ
  - **`python manage.py checkout_status [--days N] [--out ไฟล์]`** ([checkout_status.py](checkout/management/commands/checkout_status.py)) — ตรวจว่าติดตรงไหนในหน้าเดียว ไล่ 6 ขั้นจากต้นทางไปปลายทาง: webhook เข้าไหม → ลายเซ็นผ่านไหม → บอทได้ยินกลุ่มไหน → ตั้งกลุ่ม/ติ๊กเก็บแล้วยัง → อ่านไปกี่ข้อความ → เป็นเคสกี่เคส + เตือนเคสที่เทียบชื่อเล่นไม่ได้/ไม่รู้ทะเบียน
  - **★★ ก.ย.69 — เก็บแชทแยกกลุ่มลง Postgres (`GroupChat` · migration 0007)** — เจ้าของสั่งหลังเห็นว่า n8n forward ได้แล้ว
    - **ต่างจาก `GroupMessage` เดิมที่ยุบทิ้ง**: แยกตามกลุ่มชัดเจน (`group_id` + ชื่อกลุ่ม) · เก็บ **สติกเกอร์ / LINE emoji / พิกัด / ตำแหน่งไฟล์** ไม่ใช่ข้อความล้วน · **มีอายุข้อมูล `CHAT_KEEP_DAYS`=90 วัน** ลบเก่าอัตโนมัติ (`_cleanup_chat()` วันละครั้งผ่าน KV `chat_cleanup_last`) — คลังแชทที่ไม่มีวันหมดอายุ = กองข้อมูลส่วนบุคคลที่โตไม่หยุด
    - **เก็บทุกกลุ่มที่บอทอยู่** (ต่างจาก `ingest_group_events` ที่ดูเฉพาะกลุ่มที่ตั้งไว้กลุ่มเดียว) · ไม่เก็บแชทส่วนตัว (ไม่มี `groupId` = ข้าม)
    - เปิด/ปิดที่ **`checkout_line_config["store_chat"]`** — ติ๊กในพาเนล "⚙️ กลุ่ม LINE" · **ปิดโดยปริยาย**
    - กันซ้ำด้วย `message_id` (unique) · `sender_name` = **ชื่อเล่น** (`sender_id` เก็บไว้เทียบ/แท็กเท่านั้น ห้ามโชว์)
    - `chat_stats()` → พาเนลโชว์ "เก็บแล้ว N ข้อความ · แยกรายกลุ่ม · ล่าสุดเมื่อไหร่"
    - **★★ เก็บ "แชทลูกค้าที่ทักเข้า LINE OA" ด้วย (ก.ย.69 · เจ้าของสั่งเพิ่ม)** — `chat_type` = `group` / `user` / `room` (migration **0008**)
      - **บั๊กที่แก้ไปพร้อมกัน**: เดิม `store_chat` เขียนว่า *"ไม่มี groupId = ข้าม"* → **ลูกค้าที่ทักเข้า OA หลุดหมด** ทั้งที่ข้อมูลวิ่งมาถึงเซิร์ฟเวอร์แล้ว
      - **เปิด/ปิดแยกจากแชทกลุ่ม** (`store_customer_chat`) · **อายุข้อมูลสั้นกว่า** `CUSTOMER_CHAT_KEEP_DAYS`=60 วัน (แชทกลุ่ม 90) — บทสนทนากับบุคคลภายนอกที่ไม่ได้ยินยอมอะไรกับเรา เก็บเท่าที่ใช้พอ
      - **ชื่อลูกค้า**: ไม่มีในชีตพนักงาน → `people.display_name_for()` ดึง **LINE profile displayName** มาแทน แล้ว **cache ถาวรใน KVStore `line_profiles`** (ยิง API ครั้งเดียวต่อคน ไม่ใช่ทุกข้อความ · เกิน 2000 คนตัดตัวเก่าทิ้ง)
      - **`chat_stats()` ไม่ส่ง `sender_id` ออกหน้าเว็บ** — โชว์แค่ชื่อ (กติกาเดิม: ห้ามโชว์ LINE user id)
      - **⚠️ สิ่งที่เก็บไม่ได้เลย**: พนักงานทักลูกค้าจาก **LINE ส่วนตัว** — ไม่ผ่านบอท LINE ไม่เปิดให้ระบบภายนอกเห็น · จะเก็บได้ต่อเมื่อคุยผ่าน **LINE OA** เท่านั้น
      - **ยังไม่ทำ**: log **ขาส่งออก** (`push_line_message` ยิงแล้วจบ ไม่บันทึกอะไร) → ตรวจย้อนหลังไม่ได้ว่ารายงานรายวันส่งออกจริงไหม (เคยหยุดส่งเงียบ 2-3 วันมาแล้ว)
      - **★★ ก.ย.69 — เก็บ LINE user id + โปรไฟล์ลงตาราง `LineProfile` (migration 0009 · เจ้าของสั่ง)**
      - **1 แถวต่อคน ไม่ใช่ต่อข้อความ** — โปรไฟล์เป็นของ "คน" ถ้ายัดลง `GroupChat` จะซ้ำทุกแถวและตกยุคคนละเวลา
        · ตอบคำถามที่ตารางแชทตอบไม่ได้: **ลูกค้าทักเข้ามากี่คน · ใครทักบ่อย · ทักครั้งแรกเมื่อไหร่**
        · ได้ `user_id` ไว้ **ทักกลับหาลูกค้าได้ตรง** (push ต้องใช้ id ไม่ใช่ชื่อ)
      - ฟิลด์: `user_id` · `display_name` · `status_message` · `language` · `nickname`(ชีตพนักงาน) ·
        `is_employee` · `msg_count` · `first_seen`/`last_seen`/`fetched_at` · `raw`
      - **★ ไม่เก็บรูปโปรไฟล์ (เจ้าของสั่ง ก.ย.69 · migration 0010 ถอด `picture_url` ออก)** — ที่เคยเก็บคือ
        "ลิงก์" ไม่ใช่ไฟล์ จึงไม่ได้กินที่จริง แต่ไม่มีใครใช้ → ตัดออก **เก็บน้อยที่สุดเท่าที่ใช้จริงพอ (PDPA)**
        · `raw` ก็กรอง `pictureUrl` ทิ้งก่อนบันทึก
      - **`people.touch_profile()`** = จุดเดียวที่ทำ 3 อย่างรวมกัน (เดิมกระจายอยู่หลายที่แล้วยิง LINE API ซ้ำ):
        เทียบชีตพนักงาน → ไม่ใช่พนักงานค่อยถาม LINE → upsert + นับข้อความ · `store_chat` เรียกตัวนี้แทน `display_name_for`
        · **ดึงโปรไฟล์ซ้ำเฉพาะตอนเก่าเกิน `PROFILE_REFRESH_DAYS`(30)** ไม่ใช่ทุกข้อความ · **พนักงานไม่ยิง API เลย** (มีชื่อเล่นในชีตแล้ว)
      - **⚠️★ บั๊กจริง 12–16 ก.ย.69 — โปรไฟล์ลูกค้าใหม่ไม่ถูกบันทึกเลย 3 วัน (เจอด้วยการอ่าน DB จริงผ่าน SSH)**
        - อาการ: ข้อความลูกค้าเก็บครบ (378 ข้อความ · 79 คน) แต่ **ไม่มีแถวใน `LineProfile` สักคน** และ `sender_name` ว่างทั้งหมด ·
          พนักงานไม่โดน (มีชื่อเล่นในชีต → ไม่เรียก `fetch_profile`) · ลูกค้าเดิมไม่โดน (โปรไฟล์ยังสด ไม่ดึงซ้ำ)
        - ต้นเหตุ: commit `8df7c6b` (12/09 15:51 · แยก 2 บัญชี) เขียน `seen, one_to_one = set(), [... seen ...]` —
          ฝั่งขวาถูกประเมินก่อน `seen` มีค่า → **`UnboundLocalError` ทุกครั้ง** · โปรไฟล์ลูกค้าคนสุดท้ายถูกบันทึก 15:48
        - **ทำไมไม่มีใครเห็น**: (1) `touch_profile` ไม่ได้ห่อการเรียก `fetch_profile` → exception ทะลุไปให้ `store_chat` กลืน
          (2) **ทุกเทสต์ปลอม `fetch_profile` ทั้งฟังก์ชัน** → ไม่มีเทสต์ไหนรันบรรทัดที่พังจริงเลย
        - แก้: `list(dict.fromkeys(...))` · ห่อ `fetch_profile` ใน `touch_profile` ให้ "ดึงไม่ได้ = แถวไม่มีชื่อ" ไม่ใช่ "ไม่มีแถว"
          + จด error ลง KV **`profile_fetch_last`** · เทสต์ใหม่ปลอมแค่ `requests.get` ให้ตัวฟังก์ชันจริงได้รัน
        - **กฎเทสต์: ปลอมที่ขอบระบบ (HTTP) ไม่ใช่ปลอมฟังก์ชันของเราเอง** — ปลอมทั้งฟังก์ชัน = ไม่ได้ทดสอบฟังก์ชันนั้นเลย
        - **`python manage.py backfill_profiles [--dry-run] [--limit N] [--out ไฟล์]`**
          ([backfill_profiles.py](checkout/management/commands/backfill_profiles.py)) — เติมโปรไฟล์ย้อนหลังให้คนที่มีแชทแต่ไม่มีแถว
          · **ไม่ใช้ `touch_profile`** (มันตั้ง `first_seen`=ตอนนี้ + `msg_count`=1 ซึ่งผิดสำหรับย้อนหลัง) → คำนวณจากคลังแชทจริง
          · เติม `sender_name` ในข้อความเก่าที่ว่างด้วย · ไม่เก็บรูปโปรไฟล์ · รันซ้ำไม่สร้างซ้ำ · **ต้องรันบนเซิร์ฟเวอร์** (ใช้ token + เขียน DB)
      - **★★ 16 ก.ย.69 — จับคู่พนักงานด้วย "ชื่อโปรไฟล์ LINE" เมื่อ id เทียบกับชีตไม่ได้**
        - **วัดจริงหลังย้ายกลุ่มไปบอทใหม่**: คนพิมพ์ในกลุ่มที่บอทเดิมได้ยิน 48 คน **จับคู่ชีตได้ 46** ·
          ที่บอทใหม่ได้ยิน 45 คน **จับคู่ได้ 0** · id ของ 2 บอท **ซ้อนกัน 0 ตัว** (คนกลุ่มเดียวกันแท้ๆ)
          → ชีตเก็บ id ของบอทเดิม ส่วน event ที่วิ่งเข้ามาตอนนี้เป็น id ของบอทใหม่
        - อาการ: พนักงานถูกนับเป็น "คนนอก" · หน้าเว็บโชว์ชื่อ LINE แทนชื่อเล่น (มัท → "เซลมัท OxletAuto")
          · กระทบการแท็กผู้เบิกในสรุปเบิก-คืน และการวัดผลงานแอดมินในอนาคต
        - **แก้: `employee_nick_by_name()`** ([people.py](checkout/people.py)) — เทียบ **ชื่อโปรไฟล์**
          (ของคนนั้น ไม่เปลี่ยนตามบอท) กับชีต · `touch_profile` เรียกตัวนี้ **หลังดึงโปรไฟล์** เมื่อ id เทียบไม่เจอ
          → ผลเก็บใน **ฐานข้อมูลเรา** (`LineProfile.nickname`/`is_employee`) **ไม่เขียนกลับชีต**
        - **⚠️ ห้ามเขียนทับ `nickname` ด้วยค่าว่าง** — เดิม `touch_profile` ตั้ง `nickname=nick` ทุกข้อความ
          (nick มาจาก id ซึ่งของบอทใหม่หาไม่เจอ) → คนที่จับคู่ไว้แล้วจะถูกรีเซ็ตกลับเป็นลูกค้าทุกครั้งที่พิมพ์
        - **`python manage.py line_link_employees [--apply] [--include-dm] [--out ไฟล์]`**
          ([line_link_employees.py](checkout/management/commands/line_link_employees.py)) — จับคู่ย้อนหลังให้คนที่เก็บไว้ก่อนแก้
          · **ค่าเริ่มต้นดูเฉยๆ** · เทียบเฉพาะ **คนที่พิมพ์ในกลุ่ม** (1:1 = ลูกค้า ถ้าชื่อซ้ำพนักงานจะจับคู่ผิด → ต้องใส่ `--include-dm` เอง)
          · ชื่อไม่ตรงชีต = **ไม่แตะ** แล้วลิสต์ให้ดู · `--apply` แก้ชื่อผู้ส่งในข้อความเก่าให้เป็นชื่อเล่นด้วย
        - **ทางเลือกที่ตัดทิ้ง**: ให้ n8n ถือรายชื่อ/จับคู่เอง — n8n เห็น id ชุดเดียวกับเราเป๊ะ จับคู่ไม่ได้เหมือนกัน
          และจะกลายเป็นรายชื่อ 2 ที่ + body ไม่ดิบ (เคยทำให้เก็บข้อความไม่ได้มาแล้ว)
      - **⚠️ `people.fetch_profile()` ต้องเลือก endpoint ให้ถูก ไม่งั้นได้ 404 ทั้งที่ข้อมูลมี**:
        `/v2/bot/profile/<uid>` ใช้ได้เฉพาะคนที่ **เพิ่มบอทเป็นเพื่อนแล้ว** (ลูกค้าที่ทักเข้า OA) ·
        **คนในกลุ่มที่ไม่ได้เพิ่มเพื่อน ต้องใช้ group member API** (`/v2/bot/group/<gid>/member/<uid>` — ได้แค่ชื่อ+รูป ไม่มี statusMessage/language)
      - **กติกา LINE user id (ปรับ ก.ย.69)**: **พนักงาน = ห้ามโชว์ id เด็ดขาด** (ของเดิม) · **ลูกค้า = โชว์ได้**
        เพราะเจ้าของขอไว้ใช้ทักกลับ + หน้านี้มีแค่ admin/ผู้บริหารเห็น → พาเนลโชว์ **ชื่อ + id ที่กดคัดลอกได้** (`ckCopy()`)
      - **`python manage.py line_who <ชื่อ|user id>`** ([line_who.py](checkout/management/commands/line_who.py)) — หา id จากชื่อ
        (หรือหาชื่อจาก id) · ค้น **3 แหล่งพร้อมกัน** เพราะคนละแหล่งรู้คนละกลุ่ม: `LineProfile` (คนที่เคยคุยกับบอท) ·
        `GroupChat` (แถวแชทเก่าที่ยังไม่มีโปรไฟล์) · **ชีตพนักงาน** (คนที่ยังไม่เคยพิมพ์ผ่านบอทเลย) · `--all` ลิสต์ทุกคน
        · **⚠️ console ไทยเพี้ยน (cp874) → ใช้ `--out` เขียนไฟล์**
      - **อายุข้อมูล**: `_cleanup_chat()` ลบโปรไฟล์ **ลูกค้า** ที่เงียบเกิน `CUSTOMER_CHAT_KEEP_DAYS`(60) ด้วย ·
        **โปรไฟล์พนักงานไม่ลบ** (ใช้เทียบชื่อในงานประจำ)
      - ทดสอบแล้ว: 3 event → 2 โปรไฟล์ (ลูกค้า msg=2 · พนักงานได้ชื่อเล่นจากชีต) · **ยิง LINE API ครั้งเดียว** ·
        ส่ง message id ซ้ำ = ไม่นับเพิ่ม · พาเนลโชว์รูป+ปุ่มคัดลอก id ผ่าน ไม่มี JS error
  - **⚠️ รูปภาพยังไม่ได้ตัวไฟล์** — LINE ส่งมาแค่ `message.id` ต้องไปโหลดจาก content API ภายในเวลาจำกัด · ตอนนี้เก็บ `has_media`+`message_id` ไว้ก่อน (`media_token` รอเฟสโหลดเข้า Drive)
  - **ยังไม่ทำ**: ดึง**ไฟล์รูปจากกลุ่ม LINE** (ต้องใช้ content API `api-data.line.me/v2/bot/message/<id>/content` ภายในเวลาจำกัด) — ตอนนี้เก็บเฉพาะข้อความ
- **หน้าสแกน** ([scan.html](templates/scan.html)): ปุ่ม **เบิกรถ / คืนรถ** สลับตามสถานะจริง (`ck_open`) · แผง `#ckWrap` (`ckOpenPanel`/`ckSubmit`) · ตอนคืนซ่อนช่องเลือกงาน + โชว์ช่อง "มีความเสียหาย"
- **ป้าย "🚗 ออกนอกลาน"** บนการ์ดบอร์ด + `car_json.outNow` — `out_now_codes()` ([cars/views.py](cars/views.py)) แนบ `.out_now` ให้รถแต่ละคัน → **ตอบคำถาม "รถคันนี้อยู่ไหน ใครเอาไป" ได้ทันที** (เดิมต้องไล่อ่านแชต)
- **สถานะเคส**: เบิกแล้ว = `PENDING_HUMAN` (รอหัวหน้ารับทราบในกลุ่ม เหมือนที่ทำกันอยู่) · คืนแล้วไม่มีความเสียหาย = `APPROVED_HUMAN` · มีความเสียหาย = `PENDING_HUMAN` ให้หัวหน้าตรวจ
- **⚠️ เบิก-คืน ≠ สเตปรถ** — รถพร้อมขายที่เอาไปตรวจขนส่ง **ยังพร้อมขายอยู่** แค่ไม่อยู่ที่ลาน → เป็นชั้นแยก ไม่แตะ `Car.stage` เด็ดขาด (ถ้าเอาไปปนจะพังทั้งบอร์ด)
- **หน้าหัวหน้า `/checkout/`** (แท็บ "เบิก-คืนรถ" ในแดชบอร์ด · admin/ผู้บริหาร): KPI + **ค้นหา/ตัวกรอง** + **รถที่ถูกเบิกบ่อยสุด** + ตารางทุกเคส · คอลัมน์ **งาน** (+⛽ ถ้าขอน้ำมัน) · ป้าย **"ค้าง N ชม."** (`overdueChip` · `outHours` จาก API)
  - **★ ก.ย.69 (เจ้าของขอ) — ช่องค้นหา + ตัวกรอง**: พิมพ์ ทะเบียน/ผู้เบิก/งาน/ปลายทาง กรองทันที (`render()` ฝั่งหน้าเว็บ · Esc = ล้าง) · ปุ่มกรอง **ทั้งหมด / รถออกอยู่ / ค้างเกินเวลา / คืนแล้ว** · ท้ายหัวตารางบอก "แสดง X จาก Y เคส" · **`api_movements` โหลด 1000 แถว** (เดิม 300) เพื่อให้ค้นหาครอบคลุมของเก่า
  - **★ ก.ย.69 — การ์ด "🚗 รถที่ถูกเบิกบ่อยสุด"** (`_top_cars()` ใน [views.py](checkout/views.py) → `topCars`): นับจาก **ทุกเคสในระบบ** ไม่ใช่แค่แถวที่โหลดมา · จัดกลุ่มด้วย `car_id` ถ้ารู้ว่าคันไหน ไม่งั้นใช้ทะเบียนที่พิมพ์ · จุดส้ม = ตอนนี้ออกนอกลาน · **กดชิป = ค้นหาทะเบียนนั้นทันที**
    - **⚠️ ตัวเลขยังต่ำกว่าความจริงมากตอนนี้** เพราะเคสที่นำเข้าจาก log **รู้ทะเบียนแค่ 18/64** (คนพิมพ์ในกลุ่มไม่บอกทะเบียน ส่งรูปแทน) — เคสที่เกิดจาก **สแกน QR จริง** จะผูกกับ `Car` เสมอ ตัวเลขถึงจะแม่น
  - **KPI ตัวเลข 0 = สีเทา** (มีค่าค่อยใส่สีตามความหมาย) · เพิ่ม KPI **"ค้างเกิน N ชม."** (`counts.overdue` นับฝั่งเซิร์ฟเวอร์ด้วยเกณฑ์เดียวกัน) · เอาสีม่วงออกจากหน้านี้
    - **⚠️ ห้าม `from . import constants as C` ในตัว `api_movements`** — จะทำให้ `C` เป็นตัวแปร local แล้วบล็อก `counts` ข้างบนพัง (`UnboundLocalError`) · module-level import มีอยู่แล้ว
  - **★ ก.ย.69 ลดเกณฑ์ค้าง 12 → `OVERDUE_HOURS`=4 ชม. (แดง) · `WARN_HOURS`=2 ชม. (เหลือง)** — วัด log จริง 10 วัน: ใช้รถเฉลี่ย **2.2 ชม.** (นานสุด 8) และในกลุ่มมีคนทวงตั้งแต่ ~2.5 ชม. → เกณฑ์ 12 ชม. เท่ากับไม่เคยเตือนเลย
  - **เกณฑ์มาจาก `constants.py` ผ่าน `api_movements` → `d.config`** (`CK_OVERDUE`/`CK_WARN` ใน template) — **เดิม template ฝัง 12/4 ไว้เอง แก้ constants แล้วหน้าเว็บไม่เปลี่ยนตาม**
- **ข้อมูลตัวอย่างไว้ดูหน้าตา**: `python manage.py seed_checkout_demo` ([seed_checkout_demo.py](checkout/management/commands/seed_checkout_demo.py)) — 8 รอบจำลองจาก log จริง ครบทุกสถานะ (คืนแล้ว/ยังไม่คืน/ค้างข้ามคืน/มีความเสียหาย/ขอน้ำมัน)
- **★ นำเข้า log กลุ่มจริง → สร้างเป็น "เคสเบิก-คืน" เลย (ก.ย.69 · เจ้าของสั่ง)**
  - **[checkout/parser.py](checkout/parser.py)** `parse(text)` → `{kind, plate, purpose, fuel, cancel, confidence, why}` · กติกาสังเคราะห์จากข้อความจริงในกลุ่ม
    - **⚠️ อย่าใส่คำสั้นในลิสต์คำใบ้** — เคยใส่ `"รับ"` แล้วไปโดน **"ครับ"** ที่ต่อท้ายเกือบทุกประโยค · เดาประเภทงานเฉพาะตอน `kind=="out"`
    - จับทะเบียนจากเลข 3-4 ตัวที่คนพิมพ์ (`เบิก5655`) → หา `Car.plate__endswith` · **ตัดลิงก์แผนที่ทิ้งก่อน** ไม่งั้นเลขพิกัดกลายเป็นทะเบียน
  - **ชุดตัวอย่าง** [checkout/samples/group_log_sep69.txt](checkout/samples/group_log_sep69.txt) = บทสนทนาจริง 403 ข้อความ (31 ส.ค. – 9 ก.ย.69) · รูปแบบ `HH:MM <ชื่อ> <ข้อความ>` คั่นวันด้วย `YYYY.MM.DD`
  - **`python manage.py import_group_log [--dry-run] [--clear] [--out ไฟล์]`** ([import_group_log.py](checkout/management/commands/import_group_log.py)) — อ่าน log → **จับ pattern → สร้าง `CarMovement` จริง** → โผล่ที่ **แท็บ "เบิก-คืนรถ" (`/dashboard/?tab=ck`)** เหมือนเคสที่คนกดในเว็บทุกอย่าง
    - จับคู่ต่อคนตามเวลา: "เบิก" เปิดรอบ · "คืน" ปิดรอบที่ค้าง · "ขอเบิกน้ำมัน" ระหว่างรอบ = ติดธง ⛽ ให้รอบนั้น (ไม่ใช่รอบใหม่) · "พิมพ์แต่เลขทะเบียน" = เติมทะเบียนให้รอบที่เปิดอยู่
    - รูป/วิดีโอที่ส่งใกล้กัน (±6 นาที คนเดียวกัน) → สร้าง `MovementPhoto` **ที่ไม่มีตัวไฟล์** (ไฟล์อยู่ใน LINE) → คอลัมน์ "รูป" บอกจำนวนจริงที่ส่งในกลุ่ม
    - เคสที่นำเข้าติดเครื่องหมาย `SAMPLE_MARK` ต้นช่อง note → `--clear` ลบเฉพาะพวกนี้ (ไม่แตะเคสจริง)
    - **วัดจริง**: 403 ข้อความ → **64 เคส** (คืนแล้ว 49 · ยังไม่คืน 15) · รู้ทะเบียน 18/64 · ใช้รถเฉลี่ย 2.2 ชม.
    - **⚠️ console ไทยเพี้ยน (cp874) → ใช้ `--out` เขียนไฟล์ UTF-8 แทนการพิมพ์ลงจอ**
  - **★ ห้ามโชว์ LINE user id — [checkout/people.py](checkout/people.py)**: `nickname_for(user_id, display_name)` เทียบกับ **ชีตพนักงาน** (`EMPLOYEE_COL` userId|displayName|…|nickname · cache 10 นาที) → **หน้าเว็บโชว์ "ชื่อเล่น" เท่านั้น** · `safe_name()` กันค่าเก่าแบบ `line_<userId>` หลุดออก API
    - **`borrower_line_id` = userId เก็บไว้ "แท็กในกลุ่ม LINE" อย่างเดียว — API ไม่ส่งออกหน้าเว็บ**
    - `_actor_name()` เดิม fallback ไป `user.username` ซึ่งของคนที่เข้าผ่าน LINE คือ **`line_<userId>`** → id หลุดไปโชว์ (แก้แล้ว)
    - **[lineout.py](checkout/lineout.py) `_msg()`** — มี userId = ส่งแบบ `textV2` + substitution **แท็กตัวจริงในกลุ่ม** (แบบเดียวกับ @All ของรายงานรายวัน) · ไม่มี = ข้อความธรรมดา
  - **★ ยุบ "โหมดเฝ้าดู" (หน้า `/checkout/observe/`) ทิ้งแล้ว ก.ย.69** — เจ้าของสั่ง: *"ฉันให้คุณจับ pattern ไม่ใช่เก็บข้อมูลทั้งหมดลงในระบบ"*
    - ลบ: หน้า observe + `api/observe*` 3 endpoint + `record_group_events` + hook `_observe_record` ใน `line_webhook` + **model `GroupMessage`** (migration **0004_drop_groupmessage** — ต้อง `migrate` ตอน deploy)
    - **บทเรียน**: เก็บข้อความดิบทั้งกลุ่มลง DB = ได้ข้อมูลส่วนบุคคลกองโต (ชื่อ/ที่อยู่/พิกัด/userId) ที่ไม่มีใครใช้ · สิ่งที่ต้องการจริงคือ **"เคส"** ไม่ใช่ "แชท"
- **ยังไม่ได้ทำ (เฟสถัดไป)**: บอทอ่านกลุ่ม LINE เพื่อจับคนที่ยังพิมพ์แบบเดิม · AI จำแนกว่ารูปไหนคือข้อไหนในเช็คลิสต์ (`MovementPhoto.checklist_item`/`ai_label` รองรับไว้แล้ว · ตอนนี้เช็คแค่ "จำนวนรวมพอไหม") · OCR เลขไมล์ · ทวงอัตโนมัติเมื่อค้างเกิน `OVERDUE_HOURS` · หน้าตั้งค่ากลุ่ม LINE ในเมนูแอดมิน (ตอนนี้ตั้งผ่าน KVStore)

### 📞 ตามงานจัดซื้อ (รับซื้อรถ · ก.ย.69 — เจ้าของสั่ง "ทำให้ง่าย คนใช้เป็นผู้สูงวัย")
เตือน "วันนี้ควรโทรคันไหน" ให้ทีมจัดซื้อ — **ออกแบบให้ไม่ต้องเรียนรู้อะไรเพิ่มเลย**
- **ไม่ต้องเปิดเว็บ ไม่ต้อง login ไม่ต้องกดปุ่ม ไม่ต้องกรอกช่องใหม่** — ข้อความมาหาใน LINE เอง
- **ตัวปิดงานคือช่องที่ทีมกรอกอยู่แล้ว**: กรอก "รับซื้อ/ไม่รับซื้อ" (คอลัมน์ K) → เคสหลุดจากรายการเอง
- **[purchase_followup.py](dashboard/services/purchase_followup.py)** `fetch_open_cases(days)` + `build_messages()` · **ย้อนหลัง 18 วัน** (`LOOKBACK_DAYS` — เจ้าของเคาะ) · **สูงสุด 5 คัน/คน** (`MAX_CARS`) · ไม่มีงานค้าง = ไม่ส่ง
- **จัดลำดับ**: ยังไม่ได้คุยเลยมาก่อน → แล้วค่อยดองนานสุด (ไม่มีคะแนน/tier ให้ผู้ใช้ต้องตีความ)
- **ผู้รับ = ช่อง "จัดซื้อ" (M) ของเคสนั้น** (วัดจริง: พี่ต๊าด 54% · พี่หมี 46%) · แอดมิน (มิว) ได้ **สรุปภาพรวมอย่างเดียว ไม่มีรายชื่อรายคัน**
- **⚠️ ไม่ใช้ช่อง "Follow วันถัดไป" (T/U)** ทั้งที่มีในชีต — วัดจริงกรอกแค่ **8%** (คอมเมนท์จัดซื้อกรอก 91% → ใช้ตัวนั้นบอกว่า "คุยแล้วหรือยัง" แทน) · ออกแบบบนช่องที่ไม่มีใครกรอก = ระบบตายตั้งแต่วันแรก
- **ทดสอบ/ดูหน้าตา**: `python manage.py notify_purchase --dry-run` (ไม่ส่ง) · `--to <LINE user id>` (ส่งเข้าไอดีเดียวเพื่อทดสอบ) · `--days` / `--max` ปรับได้
- **ยังไม่ผูก cron** — ตั้งใจให้ทดสอบด้วยมือก่อน · เปิดใช้จริงค่อยเรียก `build_messages()` จาก `cron_tick` แล้ว map ชื่อ→LINE id ผ่านชีตพนักงาน
- **⚠️ เคสค้างเยอะกว่าที่ส่งได้มาก** (วัดจริง ก.ย.69: ในช่วง 18 วันมี 242 เคส · พี่หมี 131 · พี่ต๊าด 96) — วันละ 5 คันจะไล่ไม่ทัน เคสจะทยอยเกิน 18 วันแล้วหลุดไปเอง · ถ้าจะให้ครอบคลุมต้องเพิ่ม `--max` หรือขยายวัน

### 🔎 รายงานเคสรับซื้อ + รถที่ขาดตลาด — [purchase_report.py](dashboard/services/purchase_report.py) · 25 ก.ย.69
*"อยากส่งการแจ้งเตือนว่า 7 วันย้อนหลังมีกี่เคสที่ยังไม่โทร และจัด ranking … กับรถที่เราต้องการหรือรถที่เรายังขาดตลาดอยู่"*

ต่อยอดจาก [purchase_followup.py](dashboard/services/purchase_followup.py) (ดึงเคสค้างจากชีตจัดซื้อ) · เพิ่ม 2 อย่าง:
- **`market_gap()` — "รถขาดตลาด" คำนวณจากของจริง ไม่ใช่ความรู้สึก**:
  `ลูกค้าถามหากี่ครั้ง (leadCarsByMonth · 3 เดือนล่าสุด) ÷ (พร้อมขายตอนนี้ + 1)`
  · สต๊อกจาก `cars_car` (stage `show` = พร้อมขาย) · +1 กันหารศูนย์ + ทำให้ "มี 0 คัน" แรงกว่า "มี 1 คัน"
- **`build_room_reports()` — ส่งแยกห้อง** (`ROOMS`): เคสHOT (พี่หมี) / เคสHOT (พี่ต๊าด)
  · แต่ละห้องเห็นเฉพาะงานตัวเอง · **บอทตัวส่งอยู่ในทั้ง 2 ห้องแล้ว** (`channels=["push"]` · ยืนยัน 25/09)
  · แก้คน/ห้องได้ที่ KV `purchase_report_rooms` ไม่ต้อง deploy
- **ลำดับความสำคัญ**: ยังไม่ได้โทร (มาก่อนเสมอ) → รุ่นที่ขาดตลาด → ดองนาน
- `manage.py purchase_report [--dry-run] [--days 7] [--gap] [--to Cxxxx] [--out ไฟล์]`

**⚠★ กติกาชื่อรถที่ต้องรักษา (เสียเวลา 3 รอบกว่าจะได้ 90%)**
1. **พจนานุกรมรุ่นต้องมาจากฝั่งที่สะอาดที่สุดฝั่งเดียว** = ชื่อในชีตลีด (dropdown)
   · เคยปล่อยชื่อจากสต๊อก ("Corolla Altis ALTIS ปี 14-18") เข้าพจนานุกรมด้วย
   → คีย์ 2 ฝั่งไม่มีวันตรงกัน **Revo โชว์ "มีในสต๊อก 0 คัน" ทั้งที่มีจริง**
2. **ห้าม `NFKC` กับข้อความไทย** — มันแยกสระ "ำ" (U+0E33) เป็น ' ํ'+'า'
   คำว่า "ดำ" ในลิสต์สีเทียบกับ "ดํา" ที่ได้จากข้อความไม่ตรง → ใช้ **NFC**
3. **เทียบแบบ "หารุ่นในข้อความ" ไม่ใช่ "ตัดขยะออกแล้วหวังว่าที่เหลือคือรุ่น"**
   คนกรอกพิมพ์อิสระมาก ("MAZDA 2 ปี22 ขาว" · "Honda City 1.0 เทอร์โบ รถปี21")
   · **วัดจริง: วิธีตัดขยะ 35% · วิธีพจนานุกรม 90%**
   · เทียบรุ่นที่ **ยาวก่อน** — `civicfc` ต้องชนะ `civic` ไม่งั้น Civic FC ถูกนับเป็น Civic เฉยๆ

**วัดจริง 25/09** (7 วัน): ค้าง 109 เคส · **ยังไม่ได้โทร 19** (พี่หมี 14 · พี่ต๊าด 5)
· รถขาดหนักสุด: Yaris Ativ (ถาม 207 · มี 0) · Civic FE (144 · 0) · Altis (101 · 0)

**ยังไม่ได้ทำ**: ผูก cron (ตอนนี้สั่งมือ) · หน้าเว็บดูลีดรับซื้อ ·
เก็บเคสลง Postgres (เจ้าของสั่งให้อยู่ในชีต) · "รถที่เราอยากได้" แบบกำหนดเอง (ตอนนี้คิดจากดีมานด์ล้วน)

### 🔁 workflow ซื้อขายเทิร์นรถ (อยู่ฝั่ง n8n · เจ้าของดูแลเอง) — 17 ก.ย.69
**ไม่ใช่โค้ดของระบบเรา** แต่เก็บสำเนาไว้เพราะเจ้าของให้ช่วยแก้ · workflow อ่านข้อความเคสรับซื้อ/เทิร์น
จากกลุ่ม LINE → parse → เขียนลงชีต **"ซื้อขายเทิร์นรถ"**
- **📄 [deploy/n8n_tradein_build_row.js](deploy/n8n_tradein_build_row.js)** = โค้ดเต็มของโหนด
  **`Build Sheet Row (Trade-in)`** (v20) — ก๊อปวางทับในช่อง Code ของโหนดนั้น
- **★ ต้นเหตุที่แก้: group id ที่ฝังในโค้ดเป็นของบอทเก่า** — `GROUP_HOT`/`GROUP_VERY_HOT`/`GROUP_IGNORED`
  ทั้ง 3 ตัว **ไม่มีในทะเบียน `line_groups` และไม่มีสักข้อความใน `checkout_groupchat`**
  แต่โหนด `LINE - Get Profile` ใช้เครดิต **OxletautoGiveLead** → ไอดีที่วิ่งเข้ามาเป็นคนละชุด
  = **เงื่อนไข `caseType` ไม่เคยเข้าเลย · ตัวกันกลุ่ม "ห้องเก็บรถ" ไม่ทำงาน**
  · น่าจะเป็นต้นเหตุ "ชื่อหาย" ที่ต้องเขียน Scavenger Mode + `MANUAL_MAPPING` มาปะด้วย
  (groupId ผิดฝั่ง → group member API ตอบ 404 → โหนดตั้ง `onError: continueRegularOutput` = ผ่านเงียบ)
- **v20 เปลี่ยน `GROUP_HOT` เป็น map 2 กลุ่ม** (เจ้าของยืนยัน "ทุกอย่างเหมือนกันหมด ต่างแค่คน"):
  `C0ad44e22…`=พี่หมี · `C6a645033…`=พี่ต๊าด → **HOT ทั้งคู่** · แถม **เติมช่อง "จัดซื้อ" จากเจ้าของกลุ่ม
  เมื่อไม่มีใครถูก @tag** (`purchaserFinal` — @tag ยังชนะเสมอ)
- **⚠️ บั๊กที่ยังไม่ได้แก้ (เจอตอนทดสอบ · เจ้าของสั่ง "ส่วนอื่นค่อยว่ากัน")**: fallback เดา `caseType`
  จากรหัสเช็ค `codeUpper.includes("C-")` → **`OC-xxxx` / `SC-xxxx` / `TC-xxxx` เข้าเงื่อนไขหมด = COOL**
  · ทุกเคสที่ไม่ได้มาจากกลุ่ม HOT จึงถูกตีเป็น COOL มาตลอด · แก้ได้ด้วยเทียบ**ต้นรหัส**แทน
  (เช่น `/^C-/.test(codeUpper)`) · `GROUP_VERY_HOT`/`GROUP_IGNORED` ก็ยังเป็นไอดีบอทเก่าอยู่

**★ ย้าย "รายชื่อ/ชื่อเล่น" จากชีตมา Postgres + จับคู่ด้วย userId (17 ก.ย.69 · เจ้าของสั่ง)**
- **📄 [deploy/n8n_members_postgres.md](deploy/n8n_members_postgres.md)** = วิธีทำทีละขั้น ·
  **[.json](deploy/n8n_members_postgres.json)** = โหนดพร้อมวาง (แทน `Get Members (Master)`)
- **★★ เลิกเทียบด้วย "ชื่อที่ตั้งใน LINE" — เทียบด้วย `user_id` แทน** (เจ้าของทัก
  *"เรามีทั้งชื่อเล่นและ User ID ก็เอามาเทียบสิ"*)
  - ชื่อ LINE **เจ้าตัวเปลี่ยนเองได้ทุกเมื่อ** · มีอิโมจิ/ช่องว่างท้าย · บอทคนละตัวเห็นคนละชื่อ
    → เป็นเหตุให้ต้องเขียนโค้ดปะทับกันไปเรื่อยๆ (`Scavenger Mode` / `MANUAL_MAPPING` /
    ตัดอิโมจิ / partial match) · `user_id` ไม่เปลี่ยน เทียบแล้วจบ
  - SQL คืน **1 แถวเสมอ** (`max()`) แม้หา userId ไม่เจอ — **ถ้าคืน 0 แถว n8n จะไม่มี item
    ส่งต่อ = เคสนั้นหายทั้งเคส**
  - ต้องแพตช์ `Resolve Roles` **3 จุด** (ประกาศ `nickById` → เก็บใน loop → ให้ชนะท้ายสุด) ·
    **ไม่ต้องลบโค้ดเดิม** ของเดิมกลายเป็นทางสำรองเวลาหา userId ไม่เจอ
  - ⚠️ SQL **ห้ามคืนคีย์ชื่อ `displayName` / `userId` / `row_number`** — `Resolve Roles`
    เอา 3 คีย์นั้นไปใช้อย่างอื่น คืนมาเมื่อไหร่จะไปทับของจริง (ใช้ `displayNameDb`/`lookupUserId` แทน)
- **⚠️ ข้อจำกัดที่เหลือ — เป็นเรื่องข้อมูล ไม่ใช่โค้ด**: พนักงานใช้งานอยู่ 49 คน มี **6 คน
  ที่ช่อง "ชื่อเล่น" ถูกตั้งเป็นชื่อ LINE** (`Wattanakit` · `janey...` · `tuinui` · `Nid` ·
  `Sirun` · `เจมส์ oxletauto.co.th` — ตำแหน่งว่างทั้งหมด = กลุ่มผู้บริหาร) → เทียบ userId
  แม่นแล้วก็ยังได้ชื่อเดิม **ต้องไปกรอกชื่อเล่นจริงที่ `/dashboard/?panel=employees`**
- **★ อ่านผ่าน view เท่านั้น — ไม่ GRANT ตาราง** (`v_employee_line` + `v_employees` ที่มีสิทธิ์อยู่แล้ว)
  - เวอร์ชันแรกผมสั่ง `GRANT ... ON checkout_lineprofile` ซึ่ง **ผิดหลักของไฟล์ SQL เอง**
    ("ไม่ให้สิทธิ์ตาราง ให้แต่ view") — ตารางนั้น **มีโปรไฟล์ลูกค้าปนอยู่**
    (วัดจริง 17/09: 217 แถว = พนักงาน 95 + **ลูกค้า 122**) → n8n จะอ่านโปรไฟล์ลูกค้าได้หมด
  - แก้เป็น **เพิ่ม `display_name` เข้า `v_employee_line`** แทน · view นั้น JOIN ทะเบียนพนักงานอยู่แล้ว
    จึงเห็นเฉพาะ **95 บัญชีพนักงาน** · วัดจริง: จับคู่ได้ **49 ชื่อ** (`Donut ♡`→โดนัท · `Miwa`→มิว)
- **⚠️ โหนดนี้ห้ามใส่ `onError: continueRegularOutput`** — เจอมาแล้ว: ตอนสิทธิ์ยังไม่ผ่าน
  **ก้อน error ไหลเข้า `Merge All (with master)` แล้ว `Resolve Roles` อ่านมันเป็นรายชื่อ**
  → ชื่อเล่นว่างทุกเคสแบบไม่มีอะไรฟ้อง (หน้าจอ n8n เขียวหมด) · ให้มันแดงไปเลยจะรู้ทันที
- **ไม่มีโหนดเขียนกลับ (ตัดทิ้ง)** — ระบบเก็บโปรไฟล์เองอยู่แล้วจาก webhook (`people.touch_profile`)
  · ถ้าให้ n8n เขียน ต้องเปิดสิทธิ์ INSERT/UPDATE ทั้งตารางซึ่งมีข้อมูลลูกค้า = ไม่คุ้ม
- **⚠️ ตัว SELECT ต้องคืน `row_number` ด้วย** — `Resolve Roles` ใช้ `if (j.row_number)` แยกว่า
  แถวไหนคือ "รายชื่อ" แถวไหนคือ "ข้อความที่เพิ่งเข้ามา" · ใส่ `row_number() OVER (...)` ให้แล้ว
  → **ไม่ต้องแก้โค้ด `Resolve Roles` เลยสักบรรทัด**
- **ได้ชื่อครบกว่าชีต**: รวม **ชื่อที่ตั้งใน LINE ของทุกบัญชี (บอทเดิม+บอทใหม่)** เข้ากับชื่อในทะเบียน
  → `MANUAL_MAPPING` (`miwa`→มิว, `wattanakit`→เบียร์) ที่ปะไว้ใน `Resolve Roles` **ไม่จำเป็นแล้ว**
  · คนเดียวที่มี 2 บอทชื่อเดียวกัน = **แถวเดียว** (ไม่คืน `userId` เพราะ Resolve Roles ไม่ได้ใช้
  และถ้าใส่จะกลายเป็นแถวซ้ำ)
- **★ เคสซื้อขาย/เทิร์นรถ (โหนดสุดท้าย) ยังอยู่ในชีตเหมือนเดิม — เจ้าของสั่งไว้ชัด ห้ามย้าย**
  · ผมเคยทำเกิน (สร้างตาราง `dash_purchase_case` + โหนด Postgres) แล้วถอยออกใน migration **0007**
  · ถ้าวันหนึ่งจะย้ายจริง ดู git history `be27f0d` (โมเดล + โหนด upsert + สวิตช์อ่าน DB เขียนไว้ครบแล้ว)

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
