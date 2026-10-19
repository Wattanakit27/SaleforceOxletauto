# CLAUDE.md

แนะนำ Claude เกี่ยวกับโปรเจกต์นี้ — Oxlet Sales Dashboard (Django port จาก Next.js เดิม)

## ภาพรวม

Django web app แสดง dashboard ยอดขาย/ลีด/ไลฟ์ ของทีมเซลล์ Oxlet ดึงข้อมูลทั้งหมดจาก
**Google Sheets** (ไม่มี local DB — `DATABASES = {}` ใน [oxlet/settings.py](oxlet/settings.py))
UI เป็น Thai-language, timezone Asia/Bangkok

**Deploy: VPS Hostinger** (`srv1793506` · gunicorn + nginx · ดู [deploy/DEPLOY.md](deploy/DEPLOY.md)) — _เดิมอยู่บน Vercel ถึง มิ.ย.69 · ลบ vercel.json แล้ว 16 ต.ค.69_

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
| `/crm/` | `crm_views.page` | **หน้า Oxlet CRM** (13 ต.ค.69 · แบบ "Oxlet CRM.html" · **หน้าใหม่แยก ไม่แตะหน้าเดิม**) — แดชบอร์ด · ไปป์ไลน์ลีด · ลูกค้า · แชท · สต็อกรถ · รายงาน · `?p=dash\|pipe\|cust\|chat\|stock\|report` · เซลล์เห็นของตัวเอง · แอดมิน `?seller=` เลือกดูได้ · คนงาน → /track/ · จัดซื้อ → /buy/ · ดู section "Oxlet CRM" |
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
| `/connect/` | `connect_views.page` | **หน้า Connect — แชทลูกค้า LINE OA รวมที่เดียว** (3 ต.ค.69 · **11 ต.ค.69 หน้าตาใหม่ "ศูนย์ควบคุมลีด"** · `?p=dist\|db\|pipe\|dash\|rules` เปิดหน้านั้น · `?classic=1` = หน้าเดิม) · แอดมิน/ผู้บริหาร = เห็นทุกแชท + โอน/ปล่อยคืนคิว + ตั้งค่า · เซลล์ = เห็นเต็มเฉพาะลูกค้าที่ตัวเองรับ + คิวรอรับ (เฉพาะวันเวรทีม) · คนงาน = 403 · ไม่ login → `/login/?next=/connect/` · `?id=` เปิดแชทนั้นเลย · `?embed=1` = ฝังในแท็บแดชบอร์ด · ดู section "Connect" |
| `/connect/api/comments` | `connect_views.api_comments` | **แอดมิน/ผู้บริหาร** (17 ต.ค.69 · หน้า "คอมเมนต์" ใน Connect · `checkout/comments.py`) — GET `?platform=fb\|yt\|tt&status=wait\|all\|done&cat=greet\|interest\|attack\|complaint\|none&q=&limit=` = คอมเมนต์ Facebook (โพสต์เพจ+โฆษณา) · YouTube · TikTok รออนุมัติ + `counts` (รอตอบ 7 วัน) + `catCounts` (ประเภทลูกค้า) + `sources` (ดึงล่าสุด/พัง) · POST `{action:"done", id, on}` = จัดการแล้ว · `{action:"category", id, cat}` = จัดประเภทลูกค้าเอง (`auto` = ให้ระบบจัด) · `{action:"sync"}` = ดึงเดี๋ยวนี้ (ห่าง ≥2 นาที · 429) · เซลล์ 403 · ดู section "หน้าคอมเมนต์" |
| `/connect/api/inbox` · `chat` · `claim` · `reply` · `reply_image` · `canned` · `assign` · `dismiss` · `lead` · `assign_lead` · `park_assign` · `park_add` · `fb_test` · `fb_webhook` · `config` · `stats` · `summary` · `test` | `connect_views.*` | API ของ Connect — **เช็คสิทธิ์ฝั่งเซิร์ฟเวอร์ทุกตัว** · POST ต้องมี CSRF (ไม่ใช่ csrf_exempt) · อ้างลูกค้าด้วย `ChatOwner.id` **ไม่ส่ง LINE user id ออก** · `summary` = ตัวเลขบนเมนู (แอดมิน: รอรับ · เซลล์: ลูกค้าของฉันที่รอตอบ+คิว) · `inbox?view=tocode` = แท็บ "ห้องพัก Lead" (แอดมิน · ศูนย์กระจายลีดทุกช่องทาง) · `inbox?src=line|fb|tiktok|other` = ตัวกรองช่องทาง · `assign_lead {id, skip}` = "ไม่ต้องจ่ายเบอร์" · `assign_lead {id, park}` = "รับ lead จากแชทนี้แล้ว" (ส่งเข้าห้องพัก · 11 ต.ค.69) · `assign_lead {id, kind:"buy"|"sell"}` = ตั้งเป็นลีดรับซื้อรถ/ลีดขายรถ (11 ต.ค.69) · `park_assign` = จ่ายเบอร์ใบร่างในห้องพัก · `{…, resend: true}` = ส่งใบเข้ากลุ่มจ่ายเบอร์อีกครั้ง (6 ต.ค.69) · `park_add` = ฟอร์มเพิ่มลีดเองในห้องพัก (จองเลข + ใบลงกลุ่ม ADMIN เก็บ Lead · 19 ต.ค.69) · `fb_test` = แชททดสอบการตอบ Facebook · `fb_webhook` = ผูกเพจกับ Messenger webhook (GET ตรวจ · POST ผูก) |
| `/api/admin/refresh_data` | `admin_refresh_data` | admin POST: สั่ง sync + precompute เดี๋ยวนี้ (ปุ่มรีเฟรชในหน้าสถานะระบบ) — คำนวณสดจาก Google ~10 วิ |
| `/api/admin/trends` | `admin_trends` | admin GET: JSON เทรนด์ followup (`FollowupLog` รายวัน + `SellerWeekly` รายสัปดาห์ + `rounds`) — endpoint สำรอง (หน้า dashboard ฝัง inline ผ่าน `trends_json` context แล้ว · ดู section "เก็บสถิติ followup + เทรนด์") |
| `/api/admin/report_config` | `admin_report_config` | admin: GET=อ่าน, POST=บันทึก config "รายงานเข้าไลน์รายวัน" (`{enabled,time,mode,test_id,group_id}` · เก็บ KVStore `report_line_config`) — เมนูจัดการ "รายงานเข้าไลน์" (ดู section "รายงานเข้าไลน์") |
| `/api/admin/social` | `admin_social` | admin GET `?from=&to=`: ตัวเลข **engagement โซเชียล** (Meta + TikTok + YouTube) ให้แท็บ **"โซเชียล"** — ยอดรายวัน (หาผลต่างจาก snapshot สะสม) · ยอดรวมช่วง · โพสต์/คลิปที่ปังสุด · แยกรายช่อง · ค่าโฆษณา · **`?side=&owner=&offset=` = คลิป/โพสต์ของช่องนั้นช่องเดียว** (หน้า "ดูรายช่อง" · `social_stats.channel_posts`) · ดู section "แท็บโซเชียล" |
| `/api/admin/meta_sync` | `admin_meta_sync` | admin: GET=สถานะดึงข้อมูล Meta (รอบล่าสุด · โควต้า · กดได้ไหม) · POST=ดึงเดี๋ยวนี้ (รันใน thread) — **มีด่านกันกดถี่ ไม่ผ่าน=429+เหตุผล+นาทีที่ต้องรอ** · เมนู "Meta (Facebook) — ดึงข้อมูล" · `?panel=meta` |
| `/api/admin/report_test` | `admin_report_test` | admin POST `{target?}`: แคปตารางรายงาน (Playwright) → ส่งรูปเข้า LINE เดี๋ยวนี้ (ปุ่ม "ส่งทดสอบ") · ⚠️ ได้จริงเฉพาะ prod (LINE ต้องดึงรูปจาก URL https สาธารณะ) |
| `/api/admin/line_group_name` | `admin_line_group_name` | admin POST `{id}`: ดึงชื่อกลุ่ม LINE จาก group id (LINE group summary API · บอทต้องอยู่ในกลุ่ม) → ปุ่ม "ตรวจชื่อ" ในพาเนลรายงาน (ยืนยันว่า id คือกลุ่มไหน) |
| `/api/admin/line_groups` | `admin_line_groups` | admin GET: รายชื่อกลุ่ม LINE ที่บอทรู้จัก (สะสมจาก webhook · KVStore `line_groups`) → dropdown เลือกกลุ่มในพาเนลรายงาน |
| `/api/meta/webhook` | `fb_webhook.view` | **public** (csrf_exempt) — **Messenger webhook** (4 ต.ค.69 · แทนการถาม API ทุกนาที) · GET = verify (`META_WEBHOOK_VERIFY_TOKEN`) · POST = แชทเพจ → Connect ทันที · ตรวจ `X-Hub-Signature-256` ด้วย `META_APP_SECRET` (**ไม่ตั้ง = 503 ไม่รับ**) · ดู section "Connect" + [deploy/meta_webhook.md](deploy/meta_webhook.md) |
| `/api/tiktok/webhook` | `tiktok_webhook` | **public** (csrf_exempt) — **webhook ของ TikTok for Developers** (ก.ย.69 เจ้าของขอ callback ไปวางในหน้า TikTok) · POST = event → `dash_tiktok_event` (raw) · GET = 200 (`?challenge=` ตอบค่ากลับ) · ตรวจลายเซ็น `TikTok-Signature` ด้วย `TIKTOK_CLIENT_SECRET` · ดู section "TikTok webhook" |
| `/api/admin/tiktok/accounts` | `admin_tiktok_accounts` | admin: GET=ช่อง TikTok ที่เชื่อมแล้ว (**ไม่มี token**) · POST `{label}` = สร้างลิงก์ขออนุญาตรายช่อง (ใช้ได้ครั้งเดียว หมดอายุ 7 วัน) |
| `/api/admin/tiktok/sync` | `admin_tiktok_sync` | admin: GET=สถานะดึงยอดคลิป · POST=ดึงเดี๋ยวนี้ (ด่านกันกดถี่ 15 นาที → 429) |
| `/api/line/webhook` | `line_webhook` | **public** (csrf_exempt) — LINE Messaging API webhook · จับ `groupId`+ชื่อ ตอนบอทได้ event จากกลุ่ม (join/message) → เก็บ `line_groups` (ยืนยัน signature ถ้ามี `LINE_CHANNEL_SECRET`) · **ต้อง register URL นี้ใน LINE Console** (Messaging API → Webhook URL = `SITE_URL/api/line/webhook` · เปิด Use webhook) |
| `/api/line/group_ingest` | `line_group_ingest` | **public** (csrf_exempt · auth `?secret=CRON_SECRET` / header `X-Cron-Secret`) — รับ group event จาก **n8n** (กรณี n8n เป็นตัวรับ LINE webhook แล้ว forward มา) → เก็บ `line_groups` เดียวกับ webhook · body ยืดหยุ่น (LINE raw `{events:[...]}` / `{groupId,groupName?}` / list) · คืน `{ok,count,groups}` |
| `/api/notify/owner` | `api_notify_owner` | **public** (csrf_exempt · POST · header `X-Cron-Secret` = `CRON_SECRET` เทียบแบบไบต์) — `{text}` (≤1000 ตัว) → LINE ส่วนตัวเจ้าของ (`leadsheet._send_alert` ผู้รับ `ALERT_TO` = วัฒนกิจ) · จำกัด 12 ข้อความ/ชม. (KV `notify_owner_sent` · เกิน = 429) · **ใช้กับ hook ของ Claude Code บนเครื่อง dev** (`~/.claude/hooks/long_task_notify.py` · งานเกิน 10 นาทีเสร็จ = แจ้ง) · ไม่ตั้ง CRON_SECRET = 503 · เทสต์ `scripts/test_notify_owner.py` |
| `/api/admin/dev_requests` | `admin_dev_requests` | **แอดมิน** — "แจ้งผู้พัฒนา" (16 ต.ค.69) · GET `?days=&status=` = เรื่องที่แจ้ง (ใหม่สุดก่อน) + `counts` + `canManage` · POST `{action:"create", kind, urgent, title, detail, page, files:[{id,name}]}` = บันทึก + เด้ง LINE ส่วนตัวเจ้าของ · POST `{action:"status", id, status, note}` = **แอดมินสูงสุด/ผู้บริหาร (`_is_boss`) เท่านั้น** · ไฟล์แนบอัปก่อนผ่าน `/track/api/upload` (`target=devreq`) · ดู section "แจ้งผู้พัฒนา" |
| `/api/admin/dev_requests/file` | `admin_dev_request_file` | **แอดมิน** GET `?id=&i=` = เปิดไฟล์แนบ (เก็บนอก /media/) · รูป/คลิป/PDF เปิดในเบราว์เซอร์ · ไฟล์อื่น = ดาวน์โหลดเสมอ · `nosniff` + CSP `sandbox` |
| `/api/admin/update_release_date` | `update_release_date` | **admin (session) หรือเซลล์ (token/session + ownership)** POST: inline edit วันที่/สถานะ เขียนกลับชีตยอดขายตรงเซลล์ — body `{tab,row,col(2\|13\|14\|18\|19\|20\|21\|23),value,token?}` → `update_release_date()` PUT cell — **2=วันจอง · 13=N สถานะเคส (จอง/จอง(ซื้อสด)/รอเซ็นต์/รอผล/รอปล่อย/ปล่อย/รีเจ็ก · validate ตัด (ซื้อสด) แล้วต้องเป็น 1 ใน 6) · 14=เซ็น · 18=เอกสาร · 19/20=ผล · 21/23=ปล่อย**. เซลล์แก้ได้เฉพาะเคสตัวเอง (เช็คชื่อที่ marker ของแถว = `cell(r,0)`). ใช้จาก `saveReleaseDate`/`saveTimelineDate`/`saveCaseStatus` (index.html แอดมิน + seller.html เซลล์ · modal เคสจองมี dropdown สถานะ + แก้วันที่) |
| `/connect/api/leadflow` | `connect_views.api_leadflow` | **แอดมิน/ผู้บริหาร** งานจ่ายเบอร์ (10 ต.ค.69 · `checkout/leadflow.py`) — GET = ค่าตั้ง + คิวจ่ายวน + งานวันนี้ · POST `{action:"config", …}` ตั้งค่า (ค่าผิด = 400 บอกช่อง) · `{action:"reassign", task, emp?}` จ่ายใหม่เลขเดิม (emp ว่าง = คนถัดไปในคิว) · `{action:"forward", id\|mid, emp}` ส่งต่อไม้ 2 (R+เลขเดิม+/1 → ห้อง REJECT) · ดู section "งานจ่ายเบอร์" |
| `/api/seller/check_phone` | `seller_check_phone` | **ต้อง login** (เซลล์ · token `/s/` หรือ session `/me/` · token ของคนอื่นใช้ไม่ได้) POST `{token?, phone}` → เบอร์นี้เคยเป็นลีดของใคร เดือนไหน (`phonebook.check_for_seller`) · ของคนอื่น = บอกแค่ชื่อ+เดือน **ไม่ส่งเลขลีด** · รับเฉพาะเบอร์เต็ม · จด `dash_event_log` |
| `/connect/api/leaddb` · `pipeline` · `team` | `connect_views.api_leaddb` · `api_pipeline` · `api_team` | **แอดมิน/ผู้บริหาร** (11 ต.ค.69 · หน้า Connect แบบใหม่ · `checkout/console_data.py` อ่านอย่างเดียว) — `leaddb?q=&mode=all\|dup\|unsheeted\|returned\|match&status=&seller=&limit=` = ค้นแถวชีตลีด (จำ 10 นาที · ส่ง **26 ค่าดิบตามคอลัมน์ชีต** · limit 150–600) + เลขที่ระบบออกแต่ยังไม่ลงชีต · `?key=` / `?code=` = รายละเอียดแถว (ลีดที่ตรงกันด้วย Code/เบอร์/ไลน์ + เหตุผล) (เลขอื่นของเบอร์เดียวกัน · งานจ่ายเบอร์ · รายงานผล · เลขไม้ 2 / ส่งต่อไปแล้ว) · `pipeline` = เคสจองจากชีตยอดขาย (ค้างเกินกำหนด = ติดป้าย) · `team` = ใบวันนี้/รายงานผล/ตอบแชท/จอง-ปล่อยรายเซลล์ · ดู section "ศูนย์ควบคุมลีด" |
| `/connect/api/crm` · `upload` · `alerts` · `insights` | `connect_views.api_crm` · `api_upload` · `api_alerts` · `api_insights` | **หน้ารวมแชท (Chat Inbox · 11 ต.ค.69 · `checkout/crm.py`)** — `crm` POST `{action, id, …}`: `stage {stage, reason}` · `followup {kind, due, note}` · `followup_done {fid, result, cancel}` · `call {result, note, media}` · `summary {text}` · `ai` (ร่าง ไม่บันทึก) · `release {reason}` (คืนกองกลาง) = **เจ้าของลูกค้า/แอดมิน** · `auto_plan {src?}` = แผน Run Auto ของห้องพัก Lead (**แอดมินเท่านั้น · แค่วางแผน ไม่เขียนอะไร** · `run_auto` เดิมเลิกแล้ว) · `upload` = รูปหลักฐานการโทร (multipart · ดิสก์ `media/connect/<id>/`) · `alerts` = กระดิ่ง (ทุกคนที่เข้า Connect ได้) · `insights` = วิเคราะห์ (แอดมิน · `?csv=unwanted` = รายชื่อไม่ต้องการ มีเบอร์) · `inbox` รับตัวกรองเพิ่ม `stage heat awaiting noreply silent follow dfrom dto car pmin pmax carmatch reason` · ดู section "หน้ารวมแชท" |
| `/api/seller/today` | `seller_today` | **ต้อง login** (เซลล์) GET `?token=` → ใบจ่ายลีดของฉัน 2 วันล่าสุด + นาฬิกาโทร (`kind`/`dueAt`) · เห็นเฉพาะของตัวเอง · ใบทดลองไม่นับ — หน้าเซลล์แบบใหม่ "งานวันนี้" |
| `/api/seller/car_matches` | `seller_car_matches` | **ต้อง login** (เซลล์) GET `?token=` → ลูกค้าของฉันที่รอรถ + รถพร้อมขายที่ตรงรุ่น/งบ (`leadflow.seller_matches` · คำนวณทุก 30 นาที) · ระบบไม่ทักลูกค้าเอง |
| `/api/seller/update_note` | `update_lead_note` | เซลล์ (token) เขียนกลับ Google Sheet จาก lead detail — รับ `field` (S=`fill_sheet_note` / Z=`customer_status` / N=`call_proof`) + `value` (back-compat: `note`) → header-aware + ตรวจ ownership · **★ 13 ต.ค.69 token ว่าง (หน้า /me/) = ใช้เซลล์ที่ login อยู่** (เดิม 401 ทุกครั้ง — เซลล์ที่เข้าผ่าน LINE Login บันทึกจาก /me/ ไม่ได้เลย) · แอดมินยังต้องใช้ token |
| `/crm/api/data` · `customer` · `lead_status` | `crm_views.*` | API ของหน้า Oxlet CRM — `data?seller=&fresh=1` = ข้อมูลทั้งหน้าก้อนเดียว (จำ 20 วิ) · `customer?id=<ChatOwner.id>` = แผงลูกค้าแชท (**ไม่นับว่าอ่านแชทแล้ว**) · `lead_status` POST `{code, value, seller?}` = เขียนสถานะลูกค้า (Z) ให้ลีดจากชีต (CSRF จริง · เฉพาะแถวของเซลล์คนนั้น) |
| `/api/seller/scan_doc` | `scan_doc` | **ต้อง login (any)** POST: รับรูปเอกสาร (base64, ≤8MB) + `form` (`finance`\|`loan`) → Gemini OCR (`gemini_ocr.extract_finance_fields`/`extract_loan_fields`) → คืน `{ok, fields}` ให้ฟอร์มกรอกอัตโนมัติ (ฉบับร่างให้เซลล์ตรวจก่อนส่ง) |
| `/api/seller/finance_check` | `finance_check_submit` | เซลล์ (token) POST: ส่งฟอร์ม "เช็คไฟแนนซ์ก่อนเซ็น" → สร้าง Flex (`build_finance_check_flex`) push เข้า `FINANCE_TEST_LINE_ID` (ช่วง test) + เก็บ Supabase `finance_checks` (best-effort) |
| `/api/seller/loan_submit` | `loan_submit` | เซลล์ (token) POST: ส่งฟอร์มขอสินเชื่อ → สร้าง Flex (`build_loan_flex`) push เข้า `FINANCE_TEST_LINE_ID` + เก็บ Supabase `loan_applications` (best-effort) |
| `/api/insights/seller` | `insights_seller` | **ต้อง login (any)** POST `{seller, stats}` → Gemini โค้ชเซลล์ (`gemini_insights.analyze_seller`) คืน `{ok, analysis}` (cache 30 นาที) |
| `/api/insights/forecast` | `insights_forecast` | **admin/exec** POST `{summary}` → Gemini อธิบายเทรนด์ยอด+ปัจจัยตลาด (`gemini_insights.forecast_narrative`) คืน `{ok, narrative}` |
| `/api/v1/` | `api_v1_index` | **API สาธารณะ (ต้องมีคีย์)** — สารบัญ endpoint + วิธี auth |
| `/api/v1/employees` | `api_v1_employees` | **API สาธารณะ** GET: รายชื่อพนักงาน — `userId`(LINE) · `displayName` · `nickname` · `position` · `groupId` · กรองได้ `?nickname=` `?user_id=` `?position=` `?q=` |
| `/api/v1/groups` | `api_v1_groups` | **API สาธารณะ** GET: กลุ่ม LINE — **รวม 2 ที่**: KVStore `line_groups` (บอทจำเอง มีชื่อกลุ่ม) + **คอลัมน์ group id ในชีตพนักงาน** (ใช้ได้ทันทีไม่ต้องรอบอท) · คืน `groupId`/`name`/`lastSeen`/`source`(bot\|sheet\|both)/`employeeCount` |
| `/m/login` · `/m/handoff/<pid>` | `mobile_views.m_login` · `m_handoff` | **login ของแอปมือถือ** (9 ต.ค.69) — แอปเปิดเบราว์เซอร์ที่ `/m/login?r=<ที่อยู่กลับเข้าแอป>&c=<PKCE challenge>&via=line\|pw` → LINE Login / หน้า `/login/` (คนงานใช้ชื่อผู้ใช้+รหัส) → `/m/handoff/<pid>` ส่งรหัสใช้ครั้งเดียวกลับเข้าแอป · ดู section "แอปมือถือ" |
| `/api/m/token` · `/api/m/me` · `/api/m/logout` | `mobile_views.*` | แอปแลกรหัส+PKCE verifier เป็น token (30 วัน · เก็บแฮช) · ดูตัวเอง (`me.role` = admin\|seller\|worker\|buyer · แอปใช้จัดแท็บ) · ยกเลิก token · **ไม่คืน LINE user id** |
| `/api/m/home` | `mobile_views.m_home` | **หน้า "วันนี้" ของแอป** (11 ต.ค.69 · `services/mobile_home.py`) — ข้อมูลจริงก้อนเดียวต่อบทบาท · `?lazy=1` = ไม่รวม "ตามด่วน" (แอปขอแยก) · `?part=follow` = เฉพาะตามด่วนของเซลล์ · ส่วนไหนพังขึ้นใน `errors` · ดู section "แอปมือถือ" |
| `/api/m/charts` | `mobile_views.m_charts` | **กราฟบนสุดของหน้า "ภาพรวม" (แอดมิน = ทั้งทีม) / "วันนี้" (เซลล์ = ของตัวเอง) ของแอป (★ 18 ต.ค.69 · `services/mobile_charts.py`)** — เซลล์: ชื่อจาก token เท่านั้น (`?seller=` ไม่มีผล) · ตัวเลขจาก `dailyBySeller` + เคสจองของตัวเอง + เป้า × เดือน · ทั้ง 2 บทบาทได้ **อันดับคะแนน** (`compute_diligence_scores` · ชื่อ+ทีม+คะแนนเท่านั้น — ข้อยกเว้นเดิมของหน้าเซลล์ มิ.ย.69) · คนงาน = 403 · **จัดซื้อ = กราฟรับซื้อรถของตัวเองเสมอ (`mode=buy` · ชื่อจาก token → `purchase_page.owner_keys`) · แอดมิน `?mode=buy` = จัดซื้อทั้งทีม** (ดูหัวข้อ "กราฟทีมจัดซื้อ") · แอปโชว์: ตัวเลข 4 ช่อง + กราฟใบเดียวสลับ Lead/จอง-ปล่อย/ยอดเงิน/สถานะ + อันดับ (เจ้าของ "รกไป" รอบ 2) · ตัวเลขชุดเดียวกับ 4 กราฟในแท็บภาพรวมของแดชบอร์ด (Lead ปกติ+RJ · จอง vs ปล่อย · สถานะเคสจอง (โดนัท · กลางวง % ปล่อยแล้ว) · ยอดปล่อย ฿) อ่านจากผลที่ cron อุ่นไว้ ไม่มีสูตรใหม่ · `?range=month|prev|year` · ≤31 วัน = รายวัน ยาวกว่า = รายเดือน · วันที่ยังไม่ถึง = null · เทสต์ `scripts/test_mobile_charts.py` (58 ข้อ) |
| `/track/api/m/car/<code>` | `mobile_views.m_car` | แอปเปิดรถจาก QR = `car_json` + `role` + `rules` (สเตปไหนต้องแนบรูป/หมายเหตุ · เช็คลิสต์) + **`checkout`** (เบิก-คืนรถ: ใครเบิกอยู่/ของฉันไหม · ประเภทงาน · รูปขั้นต่ำ · มุมที่ต้องถ่าย · 11 ต.ค.69) · อยู่ใต้ `/track/` ให้ bridge login ระบบรถทำงาน |
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
  - **⚠️★ 28 ก.ย.69 — "แถบสีม่วงมันโผล่ออกมาด้วย" (เจ้าของแจ้ง) · `_hide_chrome()`**
    - **ต้นเหตุ**: 19 ก.ย. แถบเมนูซ้ายกลายเป็น **แถบถาวรบนจอ ≥1100px** (`body.has-sidebar`) และเป็น
      **`position:fixed`** · viewport ที่ใช้แคปคือ **1680–1780px** → แถบโผล่เสมอ
    - **★ ทำไม `element.screenshot()` ถึงติดแถบมาด้วย ทั้งที่ครอปตามกรอบ element**: การ์ด
      **กว้างกว่าจอ** (`#rpt-shot` = 1700px · จอ 1680px) → Playwright ต้อง **เลื่อนแนวนอน** ตอนแคป
      แต่ของที่เป็น `fixed` **ตรึงอยู่กับจอ ไม่เลื่อนตาม** → ไปนั่งทับการ์ดพอดี
      · วัดจริงในเทสต์: **สีม่วงกิน 12.7% ของรูป**
    - **ไม่มีใครเห็นมา 9 วัน** เพราะการ์ดที่ยิงเข้ากลุ่ม **ส่งไม่ออกมาตั้งแต่ 15 ก.ย.** (ปลายทางเป็น id บอทเก่า)
      → พอแก้ปลายทางเสร็จ 28 ก.ย. รูปก็โผล่พร้อมแถบม่วงทันที
    - **แก้: `_hide_chrome(page, keep_sel)`** เรียกก่อนแคปทั้ง **3 ทาง** (`capture_report_images` ·
      `capture_card` · `capture_leadsummary`) — **ซ่อน `position:fixed` ทั้งหมด** แทนไล่ระบุทีละคลาส
      → ของลอยที่จะเพิ่มในอนาคต (toast/drawer/ป้ายใหม่) หายจากรูปเองโดยไม่ต้องกลับมาแก้
      · **`keep_sel` = เป้าหมายที่จะแคป — ตัวมันเอง/ลูก/บรรพบุรุษ ห้ามซ่อน** ไม่งั้นวันที่กรอบครอบ
        การ์ดเป็น fixed ขึ้นมา จะได้รูปเปล่า · **ไม่แตะ `sticky`** (หัวตารางตรึงในการ์ดต้องเห็น)
      · ย้ายการซ่อน `.linesend-btn`/`.info-tip`/`.no-capture` เข้ามารวมที่นี่ที่เดียว
    - **เทสต์**: `python scripts/test_capture_chrome.py` — **วัดสีในรูปจริง ไม่ใช่เช็คว่า JS รันผ่าน**
      (ข้อ 1 พิสูจน์ก่อนว่าบั๊กมีจริง 12.7% แล้วข้อ 2 ยืนยันเหลือ 0.000%) · **เทสต์รอบแรกผ่านแบบหลอก**
      เพราะหน้าจำลองทำการ์ดแคบกว่าจอ = ไม่เกิดการเลื่อนแนวนอน แถบเลยไม่ทับ — **หน้าจำลองต้องกว้างกว่า viewport**
    - **⚠️ รันเทสต์ในเครื่อง dev**: `.env` ตั้ง `PLAYWRIGHT_BROWSERS_PATH=/opt/oxlet/pw-browsers`
      (ของเซิร์ฟเวอร์) → หา Chromium ไม่เจอ · เทสต์ตรวจแล้วถอดตัวแปรนี้ให้เองถ้า path ไม่มีจริง
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
- **⚠️★ 13 ต.ค.69 แก้บั๊กใน `parse_month_day` — "d/m" ถูกอ่านเป็นเดือนขึ้นก่อน**: ฟังก์ชันเดิมเรียก `parse_date` ก่อน
  ซึ่งมีทางสำรอง **dateutil (รูปแบบอเมริกัน)** → `"9/8"` (9 ส.ค.) กลายเป็น **8 ก.ย.** · `"10/2"` (10 ก.พ.) กลายเป็น **2 ต.ค.**
  (วันที่ > 12 ไม่โดน เพราะ dateutil สลับให้เอง) — สาขาที่อ่าน "d/m" ไม่เคยถูกใช้เลย · **กระทบกราฟรายวัน/ตัวเลข "ปิดได้"
  ตามช่วงวันที่ของเคสที่วันปล่อยไม่มีปี** (ยอดรายเดือนไม่กระทบ เพราะนับตามแท็บ) · แก้: เช็ค "d/m" ก่อน parse_date
  · **⚠️ ห้ามแก้ที่ `parse_date` เป็น `dayfirst=True`** — ทดสอบแล้ว `"2026-10-12"` จะกลายเป็น 10 ธ.ค.
  · `parse_date("10/2")` ตัวมันเองยังคืน 2 ต.ค. อยู่ (ไม่ได้แก้ เพราะใช้กว้าง) → **วันที่ 2 ส่วนให้ใช้ `parse_month_day` เสมอ**
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
- **⚠️ 13 ต.ค.69 แก้ข้อมูลในบันทึก**: `_attach_clean_channel` **ไม่ได้ถูกเรียกจากตัวคำนวณแดชบอร์ด** — `bookingCases[]` จึง **ไม่มี** `channelClean`
  (ตาราง Lead → จอง → จบ ใช้ `doneChannelByMonth` ที่เทียบช่องทางด้วยกติกาเดียวกันแทน) · ตอนนี้หน้า /crm/ เรียกฟังก์ชันนี้เองกับเคสของเซลล์ (`crm_page._done_channels`)
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

#### 🏢 แผนก + ตำแหน่ง (`Employee.department`) — [departments.py](checkout/departments.py) · 18 ต.ค.69 (เจ้าของสั่ง)
*"สถานะในระบบ QC อะไรต่างๆ ที่เป็นสถานะรถ เราจะใช้เป็นสถานะในโปรไฟล์นั้นเลย ซึ่งต้องแก้ภายในเว็บด้วย
เราจะมีแผนก แล้วก็ตำแหน่ง แผนกจะเป็นเซลล์ ตำแหน่งจะเป็นเซลล์ทีม A, เซลล์ทีม B"* · เจ้าของเคาะ 11 แผนก + **สิทธิ์ระบบรถตามแผนกอัตโนมัติ**

| แผนก (คีย์) | ตำแหน่ง (ตัวอย่าง) | บทบาทแอป | สิทธิ์ระบบรถ (Group) |
|---|---|---|---|
| ผู้บริหาร `exec` | ผู้บริหาร | แอดมิน* | Executive |
| แอดมิน `admin` | ออฟฟิศ บ้านเก่า/อ่อนนุช | แอดมิน* | Admin |
| เทเลเซลล์ `telesale` · เซลล์ `sales` | เทเลเซลล์ · ทีม A/B/C | เซลล์ | Sales |
| จัดซื้อ `purchasing` | จัดซื้อ | จัดซื้อ | Purchasing |
| ฝ่ายทะเบียน `registration` · QC `qc` · ช่าง `technician` · ล้างรถ `carwash` · อู่สี `paint` · โปรดักชัน `production` | ช่างและคนงาน / เด็กฝึกงาน … | คนงาน | Registration · QC · Technician · CarWash · PaintIn · Production |

- **แผนก = ตัวกำหนดแท็บในแอป + สิทธิ์กดสเตปรถ** · **ตำแหน่ง = ค่าเดิม (`position`) ไม่ถูกเขียนทับ** — ยังเป็นตัวกำหนดทีมขาย (`team_id_of`) ·
  กลุ่มในตารางเช็คชื่อ (`TEAM_ORDER`) · เวร Connect เหมือนเดิม · `team_id_of` รับ **"เซลล์ทีม A"** ด้วยแล้ว (ตัวอย่างของเจ้าของ)
  แต่ตัวเลือกแนะนำยังเป็น "ทีม A" เพราะตารางเช็คชื่อจัดกลุ่มด้วยข้อความตำแหน่งตรงตัว ("เซลล์ทีม A" จะไปอยู่ท้ายตาราง)
- **checkout migration 0042** เติมแผนกให้คนเดิมแบบ **"ระบบเดา" (`department_auto=True`)**: บทบาทระบบรถของบัญชี LINE ที่ผูกไว้ก่อน
  (แซน "ทีมโปรดักชัน" + Sales = เซลล์) → ไม่มีค่อยเดาจากตำแหน่ง → "ออฟฟิศ บ้านเก่า" ที่ไม่มีบทบาท = **ว่างไว้** (มีหลายแผนกปนกัน)
  · ตรรกะเดาแช่ไว้ในไฟล์ migration (มีเทสต์ยืนยันว่าให้ผลเดียวกับ `departments.guess`)
- **★ กติกาความปลอดภัย (ห้ามถอด)**
  1. **แผนกที่ระบบเดา = ไม่เปลี่ยนสิทธิ์ระบบรถของใคร** จนกว่าแอดมินจะเลือก/กด "ยืนยัน" ในหน้าพนักงาน — ไม่งั้น migration
     แจกสิทธิ์กดสเตปรถให้ทุกคนที่ตำแหน่งเป็นทีมขาย (ช่องโหว่เดียวกับที่ปิดไป ส.ค.69 ตอน bridge แจก Sales ทุกคน)
     · **แก้ช่องอื่นในแถว (หมายเหตุ/เวลา) ไม่นับว่ายืนยันแผนก** — ต้องมาจากช่องแผนก (`confirmDept`) เท่านั้น
  2. **แผนกไม่ยกสิทธิ์ "แอดมินฝั่งขาย"** (ดูข้อมูลลูกค้า/ยอดขายทั้งหมด) — ยังตั้งที่ "จัดการแอดมิน" ที่เดิม ·
     *แผนกผู้บริหาร/แอดมินได้แท็บแอดมินในแอปเฉพาะคนที่ login มาเป็นแอดมินอยู่แล้ว* คนอื่นในแผนกนี้ = แท็บคนงาน
     (เหตุผล: ไม่งั้นแอปโชว์แท็บแอดมินแต่เซิร์ฟเวอร์ปฏิเสธทุก API + migration จะเปิดสิทธิ์ดูลูกค้าให้คนที่ไม่เคยมี)
  3. superuser ไม่ถูกแตะ (ผู้บริหารเสมอ)
- **ตั้งสิทธิ์ระบบรถเมื่อไหร่**: (1) แอดมินเลือก/ยืนยันแผนกในหน้าพนักงาน → `sync_track_role` ตั้ง Group ให้ทุกบัญชี `line_<id>` ที่ผูก
  (ยังไม่เคยเข้าระบบรถ = ไม่สร้างบัญชีให้) (2) `_bridge_line_to_django_user` ทุกครั้งที่ bridge → **แผนกที่ยืนยันแล้วชนะ**
  (ชนะกติกาเดิม "แอดมินฝั่งขายครั้งแรก = ผู้บริหาร" ด้วย · แก้บทบาทตรงๆ ที่ /track/users/ จะถูกตั้งกลับตอน login ครั้งถัดไป)
  · **/track/users/ ล็อกช่องเปลี่ยนบทบาทของบัญชีที่ตั้งตามแผนก** ("ตามแผนก: QC (เฟิร์น)" · POST = ปฏิเสธพร้อมบอกให้ไปแก้แผนก) ·
  บัญชีชื่อผู้ใช้+รหัส (คนงาน `django_*`) ไม่ผูกทะเบียน = ตั้งที่ /track/users/ เหมือนเดิม · จด `dash_event_log` kind=`dept`
- **บทบาทในแอป** (`mobile_home.role_of`): login เป็นแอดมิน = แอดมินเสมอ → บัญชีคนงาน → **มีแผนก = ตามแผนก** → ไม่มี = กติกาเดิม
  · ผลข้างเคียงที่ตั้งใจ: ฝ่ายทะเบียน/QC/ล้างรถที่ login ด้วย LINE เดิม **ตกเป็น "เซลล์"** (ตำแหน่งไม่ใช่ admin/worker) → ตอนนี้เป็นคนงาน
  · คิวรถคนงานในแอป (`_team_queue`) อ่านบทบาทจากบัญชี `line_<id>` ของคนนั้นเอง (คำขอของแอปไม่ผ่าน bridge ของ /track/)
    ยังไม่มีบัญชี = ใช้บทบาทตามแผนกที่ยืนยันแล้ว
- **จัดซื้อ** (`purchase_page.is_purchaser`): แผนกจัดซื้อ = จัดซื้อ · ยืนยันแผนกอื่นแล้ว = ไม่ใช่ (แม้ชื่ออยู่ใน `OWNER_ALIAS`) ·
  แผนกที่เดา/ไม่มี = กติกาเดิม (ตำแหน่ง/รายชื่อ) · ใช้ทั้ง login → `/buy/` และแท็บแอป
- **หน้าพนักงาน** (`openEmployees`/`renderEmployees` · `/checkout/api/employees`): คอลัมน์ **แผนก** (dropdown · เลือก = บันทึก+ยืนยันทันที ·
  ป้าย **"ระบบเดา · ยืนยัน"** · บรรทัด "แอป: X · รถ: Y" · สิทธิ์ระบบรถของบัญชีที่ผูกตอนนี้ถ้ายังไม่ตรง) · ชิปกรองตามแผนก ·
  ตำแหน่งมีตัวเลือกแนะนำ (datalist จาก `POSITION_HINTS` + ตำแหน่งที่มีอยู่) · เพิ่มคนใหม่เลือกแผนกได้ ·
  บันทึกแล้วบอก "สิทธิ์ระบบรถ ฝ่ายทะเบียน → QC" · API ไม่ส่งชื่อบัญชี `line_<id>` ออก (มี LINE id)
  · POST `{department, confirmDept}` · แผนกมั่ว = 400 · GET คืน `departments` (ตัวเลือก + บทบาทแอป/ระบบรถ/ตำแหน่งแนะนำ) + ต่อแถว `department`/`departmentAuto`/`trackRoles`
- **ยังไม่ได้ทำ**: view `v_employees` ของ n8n ยังไม่มีคอลัมน์แผนก · `/api/v1/employees` ยังไม่ส่งแผนก · แอปยังไม่โชว์แผนก/ตำแหน่งในหน้า "ฉัน"
- **Deploy**: `migrate` (checkout **0042**) → เปิดหน้าพนักงาน ตรวจแผนกที่ระบบเดา แล้วกด "ยืนยัน" ทีละคน (หรือเลือกใหม่) ·
  คนที่ยังไม่ได้แผนก (ออฟฟิศที่ไม่มีบทบาทระบบรถ) ต้องเลือกเอง
- **เทสต์**: `python scripts/test_departments.py` (54 ข้อ · เดา · migration · API · bridge · role_of · จัดซื้อ · /track/users/ · คิวรถ ·
  ไม่มี LINE id หลุด) · ตรวจหน้าพนักงานใน Chrome (เลือก/ยืนยัน/กรองแผนก · ไม่มี JS error)

#### 📍 เช็คชื่อในแอปมือถือ — [checkin_app.py](checkout/checkin_app.py) · 14 ต.ค.69 (เจ้าของสั่ง)
*"เราจะให้เขาเช็คชื่อแล้วเก็บข้อมูลไว้ใน log ในระบบเรา แต่จะไม่ส่งลงกลุ่ม ยกเว้นส่งแจ้งตอน 9:30-10:00"*
- **2 ทาง อันไหนมาก่อนนับอันนั้น**: กดในแอป (เซลฟี่กล้องหน้า + ตำแหน่ง · `POST /api/m/checkin` multipart) หรือส่งรูปในกลุ่มเหมือนเดิม (n8n)
  · แอปไม่สร้างแถวซ้ำถ้าวันนี้มีแล้ว (ตอบ `already`) · n8n ไม่รู้ว่ามีแถวจากแอป อาจเขียนแถวที่ 2 →
    **ทุกตัวอ่านใช้ `first_per_employee()`** (มีเวลาก่อนไม่มีเวลา แล้วเวลาน้อยสุด): `checkin_report.collect` · `api_checkins` (รายวัน+สรุปช่วง) ·
    `mobile_home.my_checkin`/`checkin_summary` · **ตัวอ่านใหม่ต้องใช้ตัวนี้ด้วย** ไม่งั้นคนเดียวขึ้น 2 แถว/นับ 2 วัน
- **ไม่ส่งอะไรลงกลุ่มตอนเช็คชื่อ** — ตาราง 9:30 / รอบตามตัว 10:00 อ่านตาราง `checkout_checkin` อยู่แล้ว
- แถวจากแอป: `user_id="app:<Employee.pk>"` · `time_source="app"` · `raw={lat,lng,acc,site,distance,place,photo,login}` ·
  สาย = เกินเวลาเข้างาน + `GRACE_MIN` 5 นาที (กติกาเดียวกับตาราง) · กดซ้ำพร้อมกัน → unique ชน → ตอบ already ทิ้งรูปครั้งหลัง
- **ตำแหน่ง**: `Employee.checkin_anywhere` (checkout migration **0037** · ช่อง "นอกสถานที่" ในหน้าพนักงาน) = กดได้ทุกที่ ·
  ไม่ติ๊ก = ต้องอยู่ในรัศมีสาขา (KV `checkin_sites` · หน้า "ตั้งค่าส่งเช็คชื่อเข้าไลน์" → "เช็คชื่อในแอป — พิกัดสาขา" · `{action:"sites"}`)
  · หักค่าคลาดเคลื่อน GPS ได้ไม่เกิน `ACC_CAP` 100 ม. · **ยังไม่ตั้งสาขาเลย = ยอมให้กด** แต่จดว่าไม่ได้ตรวจ (วันแรกต้องเช็คชื่อได้)
  · ⚠️ ตำแหน่งปลอมได้ด้วยแอปปลอม GPS — เซลฟี่คือหลักฐานชั้นที่สอง
- **เซลฟี่ = ข้อมูลส่วนบุคคล** → `private_media/checkin/YYYY-MM/` (`CHECKIN_MEDIA_ROOT`) นอก /media/ · เปิดได้ทางเดียว
  `/checkout/api/checkin_photo?id=` (แอดมิน) · กัน `../` · ลบเองเกิน `PHOTO_KEEP_DAYS` 60 วัน (วันละครั้งตอนมีคนเช็คชื่อ)
- พาเนลเช็คชื่อบนเว็บโชว์ "เช็คชื่อในแอป" + ลิงก์ แผนที่ / รูป · แอป: หน้า `checkin` + ปุ่มใหญ่ในหน้า "วันนี้"/"ฉัน" ตอนยังไม่เช็คชื่อ
- **เทสต์**: `python scripts/test_checkin_app.py` (53 ข้อ · token จริงผ่าน middleware · ปลอมแค่ชีต Google)

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

**★ 7 ต.ค.69 — คนออกจากกลุ่มเช็คชื่อ = เอาออกจากระบบเช็คชื่อเอง (เจ้าของ: "ลบชื่อออโต้ได้มั้ย")** [membership.py](checkout/membership.py)
- LINE ส่ง event **`memberLeft` / `memberJoined`** (มี userId) ให้บอทที่อยู่ในกลุ่ม · กลุ่มเช็คชื่อ ("อ๊อกเล็ตธ์ ออโต้"
  = `checkin_notify_config.group_id`) วิ่งมาทาง n8n อยู่แล้ว (2,488 ข้อความตั้งแต่ 16 ก.ย.) · เดิมโค้ดอ่านแค่ข้อความ +
  บอทถูกเตะ (`leave`) ส่วน event คนเข้า-ออก **ถูกข้ามทิ้ง** · ตอนนี้ `_checkout_ingest` เรียก `handle_member_events` (try แยก)
- **ไม่ลบตัวคนออกจากทะเบียน** (ประวัติเช็คชื่อ/แชทผูกอยู่) → **ปิดช่อง "เช็คชื่อ" (`track_checkin`)** = ไม่ขึ้นตาราง ไม่ถูกแท็กตาม
  · **กลับเข้ากลุ่ม = เปิดคืนให้เอง** เฉพาะคนที่ระบบปิด (จดที่ KV **`checkin_left_members`**) — คนที่แอดมินปิดเอง (ผู้บริหาร) ไม่แตะ
  · ดูเฉพาะกลุ่มเช็คชื่อ · ออกจากกลุ่มอื่นไม่เกี่ยว · อัปเดตแคช `checkin_group_member` ให้ทันที
- หน้า "พนักงาน" ขึ้นป้าย **"ออกจากกลุ่ม 7/10"** ใต้ช่องเช็คชื่อ (`leftGroupAt`) · แอดมินติ๊กเช็คชื่อคืนเอง = ล้างป้าย
- จดทุกครั้งที่ `dash_event_log` (kind=`line_member`) + KV **`line_member_last`** — **ยังไม่เคยเห็น event นี้จริง** (เพิ่งเริ่มจับ)
  ถ้ามีคนออกแล้ว `line_member_last` ยังว่าง = n8n ไม่ได้ส่ง event ชนิดนี้มา (ต้องไปดูที่ workflow)
- **เทสต์**: `python scripts/test_member_left.py` (16 ข้อ · รวมทางจริง n8n → `/api/line/group_ingest`)

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

**⚠️★ 6 ต.ค.69 — "นิดตั้งชื่อเล่นแล้ว แต่ยังขึ้นชื่อ account" (เจ้าของแจ้ง · ครั้งนี้เป็นบั๊กโค้ดจริง)**
- วัดจริง prod: ทะเบียน `นิด` (แก้ 5/10 10:36) แต่ `LineProfile.nickname` ทั้ง 2 บัญชียังเป็น `Nid` ·
  **ข้อความที่นิดพิมพ์หลังแก้ชื่อ 49 ข้อความยังถูกบันทึกเป็น "Nid"** · เหล (เดิม Weerasak) โดนแบบเดียวกัน
- **ต้นเหตุ = วงจรซ้ำตัวเอง**: `people._load()` สร้างแผนที่ id→ชื่อ จาก **สำเนา `LineProfile.nickname`**
  ไม่ใช่ทะเบียน → `touch_profile` (ทุกข้อความ) เอาชื่อที่อ่านได้เขียนกลับลงสำเนาเดิม → ชื่อใหม่ไม่มีวันเข้า
  · การแก้ชื่อในหน้า "พนักงาน" ไม่เคยตามไปแก้สำเนาเลย
- **กระทบ**: ชื่อผู้ส่งในแชท/บันทึกโค้ช · รายชื่อใน Connect (`show_name`) · ชื่อคนโพสต์ใบจ่ายลีด ·
  **แท็ก "@Nid" ในใบจ่ายลีดจับได้ 2 ชื่อ (นิด/Nid) → ถือว่ากำกวม ไม่บอกว่าจ่ายให้ใคร**
  · **หน้าเช็คชื่อบนเว็บ + n8n ไม่โดน** (อ่าน `employee.nickname` ตรง)
- **แก้**: `_load` อ่าน `employee__nickname` ก่อน (สำเนาใช้เฉพาะบัญชีที่ยังไม่ผูกใคร) ·
  `touch_profile` ให้ชื่อในทะเบียนชนะทุกข้อความ (ไม่รอแคช 10 นาที) · `connect._tag_match` อ่านทะเบียน ·
  **`people.propagate_nickname(emp)`** = แก้ชื่อในหน้าพนักงานแล้วตามแก้ `LineProfile.nickname` +
  `GroupChat.sender_name` (เฉพาะข้อความขาเข้าของ id ที่ผูกกับคนนั้น — ลูกค้าชื่อซ้ำไม่โดน) + `sent_by_name`
  · **ไม่แตะ `CoachLog`** (บันทึกถาวร/ชีตเขียนต่อท้ายอย่างเดียว)
- **ซ่อมของที่ค้างบน prod**: `manage.py sync_employee_names [--apply] [--out ไฟล์]` (ไม่ใส่ = ดูเฉยๆ · รันซ้ำได้)
- **★ บั๊กที่ 2 ที่เจอไปพร้อมกัน — นิดถูกตั้ง "ไม่ต้องเช็คชื่อ"** ทั้งที่เช็คชื่อ 10 วันใน 14 วัน
  · migration 0015 เดาว่าเป็นผู้บริหาร (ตอนนั้นตำแหน่ง/เวลาว่าง) · พอเติมตำแหน่ง/เวลาแล้วช่องก็ยังปิด
  → **หายจากตารางเช็คชื่อที่ส่งเข้า LINE ทุกวัน + ขาดก็ไม่ถูกตาม** (หน้าเว็บยังเห็นเพราะเช็คชื่อเข้ามาจริง)
  · ไม่เปลี่ยนให้เอง (กติกาเดิม: ช่องนี้ติ๊กเองล้วนๆ) → `api_employees` ส่ง **`checkinsWhileOff`**
    (ปิดเช็คชื่อแต่เช็คชื่อเข้ามากี่วันใน 14 วัน) · หน้าพนักงานขึ้น **แถบแดง + ป้าย "เช็คชื่อจริง N วัน"** ในแถว
- **กฎ: ข้อมูลที่คัดลอกไปเก็บหลายที่ ต้องมีที่เดียวที่ "ชนะ" และทุกตัวอ่านต้องอ่านจากที่นั้น** —
  สำเนามีไว้กันข้อมูลหายตอนคนถูกลบ ไม่ใช่แหล่งความจริง
- **เทสต์**: `python scripts/test_employee_names.py` (24 ข้อ · ปลอมแค่ชีต Google) — **ย้อนโค้ดเดิมแล้วไม่ผ่าน 4 ข้อ**
  (พิสูจน์ว่าจับบั๊กได้จริง) · `test_connect.py` แก้ค่าที่คาดหวัง 1 ข้อให้ตรงกติกาใหม่ (473/473)

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

### 🔔 หน้าสถานะระบบร้องเมื่อ "รายงานส่งไม่ออก" — 26 ก.ย.69
เจ้าของถาม *"report ขาดอะไรอยู่"* → ไล่ `dash_event_log` แล้วพบว่า **การ์ดตั้งเวลา 4 ใบ
ล้มติดกัน 10 วัน (17–26 ก.ย. · 528 ครั้ง)** และ **รายงานรายวัน 2 รูปปิดอยู่ ไม่เคยส่งเลย**

- **ต้นเหตุปลายทาง (ไม่ใช่บั๊กโค้ด)**: `rpt-card` ยิงเข้ากลุ่ม **"จองรถ"** ซึ่งมีแต่บอทตัวรับ ·
  อีก 3 ใบ (mega/scorecard/alloc) ยิงเข้า **"ทดลองงาาน"** ซึ่ง **ไม่มีบอทอยู่เลยสักตัว**
  → `line_push_switch` แก้ให้ไม่ได้ ต้องเชิญบอท `@693tyhah` เข้ากลุ่ม หรือเปลี่ยนปลายทางเอง
- **⚠️ ปัญหาที่แท้จริงคือ "ไม่มีใครรู้"** — ร่องรอยอยู่ใน KV `cardline_last_<card>` เท่านั้น
  ต้องเปิดพาเนลของการ์ดทีละใบถึงจะเห็น · `admin_system_health` **ไม่เคยเช็คเรื่องนี้เลย**
- **แก้: `admin_system_health` เช็คเพิ่ม 3 อย่าง** ([views.py](dashboard/views.py))
  1. การ์ดที่ **เปิดอยู่ + รอบล่าสุดล้ม** → `err` พร้อมชื่อการ์ด + วันที่ + บอกให้รัน `line_push_switch`
  2. การ์ดที่ **เปิดอยู่แต่ยังไม่ได้เลือกปลายทาง** → `warn`
  3. **รายงานรายวัน**: เปิดแต่ไม่มีกลุ่ม → `err` · หรือ **เลยเวลาส่งมาแล้ว 30 นาทีแต่ยังไม่ได้ส่ง** → `err`
- **บล็อกนี้ import `get_kv` เอง ไม่พึ่งตัวแปรจากบล็อกก่อนหน้า** — ถ้าบล็อกนั้นล้มตอน import
  ตัวแปรจะไม่ถูกผูก แล้วบล็อกนี้จะพังตามแบบเงียบ (ซึ่งคือบั๊กแบบเดียวกับที่กำลังแก้อยู่พอดี)
- **กฎซ้ำรอบที่ 3**: *"หยุดส่งเงียบๆ" คือโหมดพังที่แพงที่สุดของระบบนี้* — รายงานรายวันเคยหยุด 2-3 วัน
  (ส.ค.69) · การ์ดหยุดตั้งแต่ 15/09 (ก.ย.69) · รอบนี้ 10 วัน · **ทุกงานที่ส่งออกอัตโนมัติ
  ต้องมีที่ให้คนเห็นว่าล้ม ไม่ใช่เก็บไว้ใน KV ที่ไม่มีใครเปิด**

### 📅 ช่วงวันที่ของการ์ดที่ส่งเข้าไลน์ + 2 บั๊กที่เจ้าของเจอ — 29 ก.ย.69

**`report_shot.DATE_MODES` = แหล่งความจริงเดียวของตัวเลือกช่วงวันที่** —
`month` · `today` · **`yesterday`** · **`last7` (รวมวันนี้)** · `range`
· `card_line_config` (GET) ส่งลิสต์นี้ให้หน้าเว็บไปทำ dropdown → **เพิ่มตัวเลือกใหม่แก้ที่ Python ที่เดียว**
(ใน index.html มี `CL_DATE_MODES_FB` เป็นตัวสำรองเผื่อ API รุ่นเก่า ไม่ใช่ตัวหลัก)
· POST ที่ส่ง `date_mode` ไม่รู้จัก = **ตอบ 400 ไม่เงียบๆ ตกไปเป็น "เดือนปัจจุบัน"**
(ถ้าปล่อยผ่าน คนตั้งจะเห็นว่าบันทึกสำเร็จ แต่รูปเป็นช่วงอื่น — ไล่หาสาเหตุแทบไม่ได้)

**★ `_date_range_for()` คิดวันที่ฝั่ง Python ด้วย `bangkok_now()` ไม่ใช่ฝั่ง JS** —
เบราว์เซอร์ที่ Playwright เปิดใช้โซนเวลาของเซิร์ฟเวอร์ (UTC) → ถ้าให้ JS คิด "เมื่อวาน" เอง
จะเพี้ยนไป 1 วันช่วงหัวค่ำไทย · ของเดิม `today` ใช้ `setDf(-1)` ซึ่งอิงนาฬิกาเบราว์เซอร์ (มีบั๊กนี้แฝงอยู่)

**⚠️★ บั๊ก 1 — "กรองวันที่ 28 แต่ได้รูปของวันที่ 29 ที่ว่างเปล่า"**
- `admin_card_line_test` อ่านช่วงวันที่จาก **config ที่บันทึกไว้** ไม่ใช่ค่าที่กรอกบนหน้าจอ ·
  ปุ่ม "ส่งทดสอบ" เดิมส่งแค่ `{card, target}` → **กดทดสอบโดยไม่กด "บันทึก" ก่อน = ใช้ค่าเก่า**
- วัดจริง 29/09: หน้าจอโชว์ `range 28/9–28/9` แต่ KV เก็บ `date_mode: "today"` →
  ตอนกดคือตี 1 ของวันที่ 29 → ได้รูปของวันที่ 29 ซึ่งยังไม่มีข้อมูล (ลีด 28/9 = 79 · 29/9 = 0)
- **แก้: `testCardLine()` เรียก `saveCardLine()` ก่อนเสมอ** · `saveCardLine()` คืน `true/false` →
  บันทึกไม่ผ่าน (เช่นเลือกช่วงวันที่ไม่ครบ) = **ไม่ยิงส่งเลย**
- **กฎ: ปุ่ม "ทดสอบ" ที่อ่านค่าจากฝั่งเซิร์ฟเวอร์ ต้องบันทึกก่อนเสมอ** — ไม่งั้นหน้าจอโชว์ค่าหนึ่ง
  แต่ทำงานด้วยอีกค่าหนึ่ง ซึ่งหลอกกว่าการพังตรงๆ มาก

**⚠️★ บั๊ก 2 — ส่งแชทส่วนตัวขึ้น `LINE 400: Failed to send messages`**
- **ไอดีปลายทางเป็นของ บอทตัวเก่า** บอทตัวส่งจึงไม่รู้จัก (ดู `_dm_target`)
- **★★ แก้แล้วด้วย `dm_route()` — เจ้าของทักว่า *"ตัวเก่าหรือตัวใหม่ก็น่าจะส่งได้"* ซึ่งถูกต้อง**
  ไอดีที่มีอยู่ใช้กับบอทตัวเดิมได้ ระบบแค่ไม่ยอมสลับ token ให้ · ตอนนี้เลือกบัญชีตั้งแต่ก่อนยิง:
  มีไอดีฝั่งบัญชีที่ควรใช้ → ใช้บัญชีนั้น (ทางหลัก) · **ไม่มีเลย → ส่งด้วยบัญชีที่ไอดีนั้นเป็นของมัน**
  (จด `viaChannel` ใน `dash_event_log`) · ไม่รู้อะไรเลย → ของเดิม
  - **⚠️ ต่างจาก "ตัวรับสำรอง" ที่ถอดออก 24 ก.ย. — อันนั้นห้ามเอากลับมา**: ของเดิมคือ
    **ลองซ้ำด้วยบัญชีเก่าทุกครั้งที่ส่งล้ม** → ทำงานทุกวันจนกลบต้นเหตุจริง (บทเรียน 21 ก.ย.:
    *ตัวสำรองที่ทำงานทุกวัน = ต้นเหตุที่ยังไม่ได้แก้*) · อันใหม่ **ไม่ใช่การลองซ้ำ** —
    เลือกก่อนยิง เฉพาะเคสที่ตรวจแล้วว่าบัญชีที่ควรใช้ไม่มีไอดีของคนนั้นเลย = ยังไงก็ส่งไม่ถึง
    · **คนที่มีไอดีฝั่งใหม่แล้วไม่ถูกแตะสักคน**
  - `people.channel_of_id(uid)` = ไอดีนี้เป็นของบัญชีไหน (คู่กับ `id_for_channel`) ·
    `channel=''` (แถวที่นำเข้าจากชีต) ถือเป็น **`crm`** ตาม `_UNKNOWN_ID_CHANNEL`
    — เดาแบบมีหลักฐาน (ทั้งหมดมาจากชีตซึ่งเก็บไอดีบอทเดิม) และถึงเดาผิดก็ไม่แย่กว่าเดิม (ล้มอยู่แล้ว)
- วัดจริง 29/09: พนักงานมีไอดีฝั่ง `push` แล้ว **49 คน** · ยังไม่มี **46 คน** —
  **เจ้าของอยู่ในกลุ่มหลัง** (`U6bf1d72…` · `channel=''` = นำเข้าจากชีต) → ทุกการส่ง 1:1 ล้มหมด
  รวม **"ตามด่วน (สรุปทีมให้แอดมิน)" ที่ล้มวันละ 2 รอบมาตลอด** โดยไม่มีใครรู้
- **แก้ที่คน ไม่ใช่ที่โค้ด**: ให้เจ้าตัว **แอดบอทตัวส่ง (`@693tyhah`) เป็นเพื่อน แล้วทักไป 1 ข้อความ**
  → ระบบจำไอดีฝั่งใหม่ให้เอง · ส่งเข้ากลุ่มไม่กระทบเลย (กลุ่มเดียวกันสำเร็จทุกครั้ง)
- **`line_notify.dm_hint(uid)`** = แปล 400 เป็นภาษาคน (ยังไม่มีไอดีฝั่งใหม่ / มีแล้วแต่ยังไม่ได้แอดบอท)
  · `admin_card_line_test` เติมต่อท้าย `info` → หน้าเว็บบอกวิธีแก้แทนที่จะโยน error ดิบ
  · ไล่ว่าใครยังส่งไม่ได้: `SELECT target, count(*) FROM dash_event_log WHERE kind='line_send' AND NOT ok GROUP BY 1`

**เทสต์**: `python scripts/test_cardline.py` (14 ข้อ — แปลง date_mode ทุกแบบ · เมื่อวาน/7 วันต้องเป็นวันไทย ·
ค่ามั่วต้องไม่คืนช่วงมั่ว · `dm_hint` ไม่แตะกลุ่ม) · **ตรวจ UI ด้วย Chromium จริง** โดยดึงฟังก์ชัน
`saveCardLine`/`testCardLine` ออกมารันแล้ว **วัดลำดับคำขอที่ยิงออก** (ต้องเป็น config → test เสมอ)

### 📤 ส่งการ์ดเข้า "หลายกลุ่ม" + เป้ารับซื้อรถแก้ได้เอง — 30 ก.ย.69 (เจ้าของสั่ง)
*"ให้มันสามารถแก้เป้าได้ และให้มันส่งไปสองกลุ่มได้ จะมีกลุ่มจัดซื้อพี่หมีกับพี่ต๊าด"*

**1) ส่งการ์ดหลายกลุ่ม** ([report_shot.py](dashboard/services/report_shot.py))
- `_DEFAULT_CFG` เพิ่ม **`group_ids`** (กลุ่มเพิ่มเติม) · **`group_id` เดิมยังเป็นกลุ่มหลัก ห้ามถอด**
  (config ที่บันทึกไว้แล้วทุกใบใช้ช่องนั้น)
- **`card_targets(cfg)`** = แหล่งความจริงเดียวของ "ส่งไปไหนบ้าง" → `[(id, เป็นกลุ่มไหม), …]` ·
  มีกลุ่ม = ส่งทุกกลุ่ม (แท็ก @All) · ไม่มีเลย = ตกไป `test_id` (แชทส่วนตัว ไม่แท็ก)
  · ใช้ทั้งใน cron (`maybe_send_cards`) และปุ่มส่งทดสอบ → ไม่มีทางส่งคนละชุดกัน
- **★★ แคปรูปครั้งเดียว แล้วส่งซ้ำทุกปลายทาง** — `send_card_to_line` รับได้ทั้ง id เดี่ยวและลิสต์
  · เรียกฟังก์ชัน 2 รอบแทน = เปิด Chromium 2 ครั้ง กินแรม VPS เป็นเท่าตัวโดยได้รูปเหมือนกัน
- **★ `ok` = ต้องถึงทุกปลายทาง** — ถึงบ้างไม่ถึงบ้างถือว่ายังไม่เรียบร้อย ไม่งั้น self-heal
  เลิกลองทั้งที่มีกลุ่มไม่ได้รับ · ข้อความผลบอกว่ากลุ่มไหนล้มเพราะอะไร
- **`_clean_gids()`** ตัดตัวซ้ำ/ซ้ำกับกลุ่มหลัก · **ตัด `U…` ทิ้ง** (แท็ก @All ในแชท 1:1 ทำไม่ได้
  LINE ปฏิเสธทั้งข้อความ รูปก็ไม่ถึง — ปลายทางแบบคนใช้ช่อง `test_id`) · เพดาน 5 กลุ่ม
- **`_push_group_guard` ตรวจกลุ่มเพิ่มเติมด้วย** — ไม่งั้นกลุ่มที่บอทตัวส่งเข้าไม่ได้จะถูกบันทึกเงียบๆ
  แล้วการ์ด "ส่งไม่ครบ" ทุกวันโดยไม่มีใครรู้ (บทเรียนเดิม 20 ก.ย.)
- **★★ UI = รายการเดียว ติ๊กได้หลายกลุ่ม** (เจ้าของทัก *"ซ้ำซ้อนไปมั้ย"* — ถูกต้อง)
  · รอบแรกผมเพิ่ม checkbox "กลุ่มอื่น" ไว้**ใต้**ของเดิม → กลายเป็น **3 ตัวควบคุมสำหรับเรื่องเดียวกัน**
  (dropdown เลือกกลุ่ม + ช่องพิมพ์ id "กลุ่มหลัก" + checkbox "กลุ่มอื่น") · กลุ่มเดียวกันโผล่ 2 ที่
  และคนต้องเข้าใจว่า "หลัก" ต่างจาก "อื่น" ยังไง ทั้งที่คำถามจริงมีข้อเดียว: **ส่งเข้ากลุ่มไหนบ้าง**
  · ตอนนี้เหลือ **รายการติ๊กชุดเดียว** · ช่องวาง id เอง/ปุ่มลบกลุ่ม ยุบไว้ใน `<details>`
  · เบื้องหลังยังเก็บ `group_id` (ตัวแรกที่ติ๊ก) + `group_ids` (ที่เหลือ) เหมือนเดิม — **config เก่าไม่พัง**
  · **กฎ: เพิ่มความสามารถให้ของเดิม ให้ยุบตัวควบคุมเก่าด้วย** อย่าวางของใหม่ต่อท้ายแล้วปล่อยของเก่าไว้

**2) เป้ารับซื้อรถ แก้ได้จากหน้าเว็บ** (`/api/admin/purchase_targets` · `admin_purchase_targets`)
- เดิมฮาร์ดโค้ด `B_TARGETS` ใน [index.html](dashboard/templates/dashboard/index.html) →
  **เป้าเปลี่ยนทุกเดือนแต่ต้องแก้โค้ด+deploy ทุกครั้ง**
- เก็บ kv **`purchase_targets`** · ค่าตั้งต้นอยู่ที่ `PURCHASE_TARGETS_DEFAULT` ([views.py](dashboard/views.py))
- **★ เก็บเป็น "เป้า/เดือน"** — ตารางคูณ `rangeMonthCount()` เอง (เหมือนเป้าของเซลล์) ·
  ถ้าเก็บเป็นเป้าของช่วงที่ดู ค่าจะเพี้ยนทันทีที่เปลี่ยนตัวกรองวันที่
- **ปฏิเสธค่าที่ไม่ใช่เลข 0–9999 พร้อมบอกว่าช่องไหน** ไม่เงียบ — พิมพ์พลาดทีเดียวเป้าเพี้ยนทั้งตาราง
  · ปฏิเสธแล้ว **ของเดิมต้องไม่ถูกทับ** (มีเทสต์)
- **รายชื่อคนมาจากเป้าที่ตั้งไว้** (`PPL` เลิกฮาร์ดโค้ด) + พาเนลเพิ่มคนที่**มีรถซื้อจริงแต่ยังไม่มีเป้า**
  เข้ามาให้ตั้งด้วย → เพิ่มคนจัดซื้อใหม่ = ตั้งในหน้าเว็บ ไม่ต้องแตะโค้ด
- เมนู: **ตั้งค่า → ทีม & สิทธิ์** มี "ตั้งเป้า / ทีม (เซลล์)" อยู่แล้ว → เพิ่ม **"เป้ารับซื้อรถ (จัดซื้อ)"** คู่กัน

**เทสต์**: `python scripts/test_cardline_multi.py` (29 ข้อ — เลือกปลายทาง · **แคปครั้งเดียวจริงไหม** ·
กลุ่มหนึ่งล้มต้องได้ `ok=False` · id เดี่ยวแบบเดิมต้องไม่พัง · เป้าติดลบ/ไม่ใช่ตัวเลขต้องถูกปฏิเสธ)
· **ตรวจ UI ด้วย Chromium จริง** — ดึง `renderPurchaseTargets`/`saveBuyTargets` ออกมารัน แล้ว
**วัดว่าค่าที่แก้ถูกส่งออกไปจริง** (แก้ 12→20 แล้ว body ที่ POST ต้องเป็น 20) + ยอดรวมขยับตาม

**⚠️ 2 กับดักของเทสต์ที่เสียเวลาไปรอบนี้ (จดไว้ในเทสต์แล้ว)**
- **Django test client ต้องใส่ `secure=True`** — โปรเจกต์บังคับ https ไม่งั้นได้ **301** เปล่าๆ
- **session เป็น signed-cookie → `client.session.save()` ไม่พอ** ต้องสร้าง `SessionStore()`
  แล้วยัด `c.cookies[SESSION_COOKIE_NAME] = _store.session_key` เอง (ข้อมูลอยู่ในตัวคุกกี้)

### 🔐 เปิดให้คนอื่นอ่านฐานข้อมูล — [deploy/postgres_readonly.sql](deploy/postgres_readonly.sql) · 26 ก.ย.69
*"อยากให้คนอื่นดูได้ด้วย แต่แค่อ่านข้อมูล เพราะกลัวพัง"*

**สิทธิ์ที่มีอยู่ตอนนี้ (วัดจริง 26/09)** — 48 ตาราง · 171 MB · ฟังแค่ `127.0.0.1:5432`

| role | อ่าน | เขียน | เป็นใคร |
|---|---|---|---|
| `postgres` | 48 | 48 | superuser |
| `oxlet` | 48 | 48 | ตัวแอป |
| **`claude`** | **48** | **0** | ผู้ช่วย — `default_transaction_read_only=on` + ไม่มี GRANT เขียนเลย |
| `n8n` | 1 | 1 | เขียนได้เฉพาะ `checkout_checkin` |
| `oxletauto` | 0 | 0 | เว็บโชว์รูม (คนละ DB) |

- **★★ กันได้จริงคือ GRANT ไม่ใช่ `default_transaction_read_only`** — ทดสอบแล้ว
  `SET TRANSACTION READ WRITE` **สั่งผ่าน** (ปิดโหมดอ่านอย่างเดียวเองได้) แต่เขียนจริงยังโดน
  `permission denied for table` · **ห้าม `GRANT INSERT/UPDATE` ให้ role ผู้อ่านเด็ดขาด**
  ชั้น read-only เป็นแค่ตัวกันพิมพ์พลาด ไม่ใช่ตัวล็อก
- **2 กลุ่มสิทธิ์ในสคริปต์**: `ro_all` (ทุกตาราง — เห็นแชทลูกค้า 55,000 ข้อความ ให้เฉพาะเจ้าของ/ผู้บริหาร)
  · **`ro_safe`** (โซเชียล/โฆษณา/สต๊อกรถ 11 ตาราง — ไม่มีชื่อคน ไม่มีแชท)
- **★ `ro_safe` เป็น allow-list และ *ตั้งใจ* ไม่ตั้ง `ALTER DEFAULT PRIVILEGES`** —
  ถ้าตั้ง ตารางใหม่ที่ migrate ขึ้นมา (ซึ่งอาจมีข้อมูลลูกค้า) จะเห็นได้เองโดยไม่มีใครตัดสินใจ
  · ตรงข้ามกับ `ro_all` ที่ต้องตั้ง **ทั้ง 2 creator role** (`oxlet` + `postgres`) ไม่งั้นตารางใหม่อ่านไม่ได้
- **1 คน = 1 บัญชี** (`IN ROLE ro_safe`) + `statement_timeout 30s` · `CONNECTION LIMIT 3` ·
  คนลาออก = `DROP ROLE` ตัวเดียว
- **⚠️ psql ตรง ≠ หน้าเว็บ "ฐานข้อมูล (SQL)"** — หน้าเว็บ **ปิด LINE user id พนักงานให้อัตโนมัติ**
  และซ่อน password/token · ต่อ psql ตรง = **เห็นดิบทุกอย่าง ไม่มีการปิดบัง** →
  คนที่แค่อยากดูตัวเลข ให้ใช้หน้าเว็บ อย่าเพิ่งแจกบัญชีฐานข้อมูล
- **⚠️ ห้ามเปิดพอร์ต 5432 ออกเน็ต** — DB นี้มีแชทลูกค้า · ต่อจากข้างนอกด้วย **SSH tunnel** เท่านั้น
  (`ssh -N -L 5432:127.0.0.1:5432 …`) · แต่ SSH เข้าเครื่องได้ = ถึงไฟล์บนเซิร์ฟเวอร์ด้วย
  ถ้าไม่อยากให้ถึงขนาดนั้น → หน้าเว็บ SQL คือคำตอบ
- **★ 2 จุดที่แก้ไปพร้อมกัน (เจอตอนไล่ว่าตารางไหนมีข้อมูลส่วนบุคคล)**
  1. **`dash_event_log` ติดป้าย `pii=False` ทั้งที่ช่อง `target` เป็น LINE user id ของพนักงาน 464 แถว**
     → ตารางนี้ดู "ปลอดภัย" เกินจริงมาตลอดในหน้าสารบัญ · แก้เป็น `pii=True` แล้ว
  2. **`checkout_employee` · `checkout_checkin` · `checkout_customerneed` ไม่มีคำอธิบายใน `TABLES`**
     → โผล่เป็นชื่อโมเดลดิบ **และไม่มีจุดส้มบอกว่ามีข้อมูลส่วนบุคคล** ทั้งที่มีเต็มๆ
     (ชื่อ-เวลาเข้างานพนักงาน 51 คน · ชื่อ+ช่องทางติดต่อลูกค้า 500 ราย) · เติมครบแล้ว **48/48 ตาราง**
  - **กฎ: เพิ่มโมเดลใหม่ต้องเติม `TABLES` ทุกครั้ง** — ไม่เติมแล้วไม่พัง แต่กลายเป็นตารางที่
    "ไม่มีใครรู้ว่ามีข้อมูลอะไร" ซึ่งอันตรายกว่าตารางที่ไม่มีอยู่

### 🌐 ให้คนภายนอกดึงข้อมูลจากฐานข้อมูลจริงเอง — [external_analyst.md](deploy/external_analyst.md) + [db_guide.md](deploy/db_guide.md) · 28 ก.ย.69
*"ให้เขาดึงมาจาก Hostinger เองเลย ไม่ต้องผ่านตัวกลางอย่างฉัน ให้เขาดึงจากฐานข้อมูลจริงได้เลย"*

ต่อจากงาน 26 ก.ย. (role `ro_all`/`ro_safe`) — คราวนี้เติม 2 ชิ้นที่ยังขาดเพื่อ **เปิดให้คนนอกใช้ได้จริง**
- **[deploy/db_guide.md](deploy/db_guide.md) — คู่มือส่งให้คนภายนอก (48 ตาราง · ~65 KB)**
  วิธีต่อผ่านอุโมงค์ SSH · **อธิบายทุกตาราง** (เก็บอะไร · กี่แถว · เป็นข้อมูลส่วนบุคคลไหม ·
  อายุข้อมูล · คอลัมน์ทั้งหมด) · ตาราง "อยากรู้อะไร → ดูตารางไหน" · คำสั่งตัวอย่าง 8 อัน
- **[deploy/external_analyst.md](deploy/external_analyst.md) — ขั้นตอนเปิดบัญชีรายคน (ฝั่งเจ้าของ)**
  เลือก `ro_safe`/`ro_all` → สร้าง role → **สร้าง user SSH ที่ทำได้แค่อุโมงค์** → ส่งอะไรให้เขา →
  วิธีเพิกถอน + เช็กลิสต์ · อ้างไฟล์เดิม ไม่เขียนกลไกซ้ำ

**★ ทำไมเลือก "ต่อฐานข้อมูลจริง" ไม่ใช่ "ส่งไฟล์ dump"**
ไม่มีสำเนาลอยอยู่ข้างนอก · เห็นข้อมูลสดไม่ต้องส่งใหม่ทุกเดือน · **ถอนสิทธิ์ได้ทันทีคำสั่งเดียว**
(ไฟล์ที่ส่งออกไปแล้วเรียกคืนไม่ได้) · **เริ่มจาก `ro_safe` เสมอ** (11 ตาราง ไม่มีชื่อคน/แชท)
แล้วค่อยขยาย — ให้เกินแล้วดึงคืนได้ แต่สิ่งที่เขาเห็นไปแล้วดึงคืนไม่ได้

**★★ `db_guide.md` สร้างจาก `db_inventory.TABLES` (แหล่งความจริงเดียว) ไม่ได้พิมพ์คำอธิบายชุดใหม่**
· ลิสต์ตารางของ `ro_safe` **อ่านจาก [postgres_readonly.sql](deploy/postgres_readonly.sql) ตรงๆ**
(regex หาบล็อก `GRANT SELECT … TO ro_safe`) → แก้สิทธิ์ในไฟล์ SQL แล้วคู่มือตามเอง ไม่หลุดจากกัน
· **เพิ่มตารางใหม่ = เติม `TABLES` แล้วสร้างคู่มือใหม่** (สคริปต์เตือนถ้ามีตารางที่ยังไม่มีคำอธิบาย)

**★ หัวข้อ 3 ของคู่มือ = "อ่านตัวเลขให้ถูก" 6 กับดักที่เจอมาแล้วจริง** — สำคัญกว่ารายชื่อคอลัมน์
เพราะคนนอกจะได้เลขผิดถ้าไม่รู้: ตาราง `*_snapshot` เป็น **ยอดสะสม** (รายวัน = D − D−1 ·
เฉพาะ `trigger='cron'` · วันเดียวกันเอาแถวล่าสุด · ติดลบไม่นับ) · อยากได้รายวันเลยใช้
`dash_social_daily` · **ต้นทุนต่อหน่วยต้องผลรวมหารผลรวม ห้ามเฉลี่ยค่าเฉลี่ย** (วัดจริง 61.31 vs 62.49) ·
YouTube ไม่มียอดแชร์ · แชทมีวันหมดอายุ (90/60 วัน) · **LINE id ต่างกันต่อบอท → `count(distinct
sender_id)` ≠ จำนวนคน**

**⚠️★ ตรวจคำสั่งตัวอย่างด้วย `EXPLAIN` บนฐานข้อมูลจริง — เจอผิด 4 ที่**
เขียนคำสั่งจากความจำแล้วชื่อคอลัมน์ผิด ถ้าไม่ตรวจ คนนอกก๊อปไปรันแล้วพังทันที:
- **`cars_car.branch` เป็นข้อความ ไม่ใช่ FK ไป `cars_branch`** → join ไม่ได้ (เขียน `GROUP BY branch` ตรงๆ)
- **`checkout_carmovement`** ใช้ `plate_text` / `checked_out_at` / `returned_at` (ไม่ใช่ `plate`/`out_at`/`in_at`)
- **`checkout_checkin.date_iso` เป็นชนิด `date`** ไม่ใช่ข้อความ → เทียบกับ `to_char(...)` = `operator does not exist`
- **Postgres ไม่ยอมให้ window function อยู่ใน `sum()`** → ต้องแยก CTE 3 ชั้น (เลือกแถวล่าสุด → หาผลต่าง → รวม)
- **กฎ: เอกสารที่มีคำสั่ง SQL ให้คนอื่นก๊อปไปใช้ ต้อง `EXPLAIN` ทุกคำสั่งก่อนส่งมอบ**
  (`EXPLAIN` ตรวจชื่อคอลัมน์/ชนิดข้อมูลครบ **โดยไม่ดึงข้อมูลออกมาเลย**)

**⚠️ ตัวเลขที่วัดได้ 28 ก.ย.69**: 48 ตาราง · **108,129 แถว** · 192 MB · แชทลูกค้า
**LINE 17,029 + Facebook 45,494 = 62,523 ข้อความ** · 20 ตารางมีข้อมูลส่วนบุคคล

**★ สแกนหา LINE user id ทุกคอลัมน์แล้ว — เจอ 12 ที่ (เดาเอาจะพลาดหลายอัน)**
`checkout_groupchat.sender_id`(17,028) · `dash_event_log.target`(510) ·
`checkout_lineprofile.user_id`/`.raw` · `checkout_checkin.user_id`/`.raw` ·
**`cars_loginevent.identity`(304)** · `checkout_carmovement.borrower_line_id` ·
**`auth_user.username`(55 · รูปแบบ `line_<id>`)** · **`cars_presence.identity`(19)** · `dash_kv.data`
→ ตารางที่มีคอลัมน์พวกนี้ **ห้ามใส่ใน `ro_safe`** (ที่ไม่ได้ใส่ไว้ถูกแล้ว)

**⚠️ ที่ยังต้องระวังเหมือนเดิม**: **ห้ามเปิดพอร์ต 5432 ออกเน็ต** · **ห้ามใส่คีย์ของคนนอกใน
`authorized_keys` ของ `root`/`oxlet`/`claude`** (= ให้ทั้งเครื่อง) · psql ตรง **ไม่มีการปิดบังใดๆ**
ต่างจากหน้าเว็บ SQL ที่ปิด LINE id พนักงานให้อัตโนมัติ → คนที่แค่อยากดูตัวเลข ให้ใช้หน้าเว็บ

### 📒 พจนานุกรมข้อมูลเป็น Excel — [deploy/db_dictionary.xlsx](deploy/db_dictionary.xlsx) · 3 ต.ค.69 (เจ้าของขอ)
*"ทำดิกชันนารีว่าฐานข้อมูลไหนเก็บอะไร ออกมาเป็น sheet เพราะต้องส่งฐานข้อมูล postgres ให้คนอื่นใช้"*
ต่อจากงาน 28 ก.ย. ([db_guide.md](deploy/db_guide.md)) — ฉบับ Excel สำหรับส่งคนนอก กรอง/ค้นได้
- **7 แท็บ**: อ่านก่อน (ภาพรวม · ป้ายสี · สิ่งที่ไม่อยู่ในฐานข้อมูล · กับดัก 7 ข้อ · วิธีต่อ) ·
  **ตาราง** (52 ตาราง: เก็บอะไร · จำนวนแถว · ขนาด · ข้อมูลตั้งแต่-ถึง · PII · ro_safe เห็นไหม · อายุข้อมูล) ·
  **คอลัมน์** (582 คอลัมน์: ชนิด · ความหมายไทย · ค่าที่เป็นไปได้ · PK/FK/UNIQUE · ช่องที่อ่อนไหว) ·
  ความสัมพันธ์ (FK จริง + join ด้วยการเทียบค่า) · View · อยากรู้อะไร→ดูที่ไหน · คีย์ใน dash_kv
- **สร้างใหม่ได้ด้วย `python scripts/gen_db_dictionary.py`** ([gen_db_dictionary.py](scripts/gen_db_dictionary.py))
  · โครงสร้าง/จำนวนแถว/ช่วงวันที่ อ่านสดจากเซิร์ฟเวอร์ผ่าน `ssh oxlet psql` (บัญชี `claude` อ่านอย่างเดียว ·
  **นับแถวกับอ่านโครงสร้างเท่านั้น ไม่ดึงเนื้อข้อมูล**) · คำอธิบายตารางจาก `db_inventory.TABLES` ·
  ความหมายคอลัมน์จาก `verbose_name` ในโมเดล (+ `COL_OVR` ในสคริปต์สำหรับช่องที่โมเดลไม่ได้ตั้งชื่อไทย)
  · **ต้องใช้ Python หลักของเครื่อง** (มีทั้ง Django + openpyxl) — `.venv` ไม่มี openpyxl
  · สูตรในแท็บ "อ่านก่อน"/แถวรวม ต้องให้ Excel คำนวณ+เซฟอีกรอบ (openpyxl ไม่ใส่ค่าที่คำนวณแล้ว ·
    `recalc.py` ของ LibreOffice ใช้บน Windows ไม่ได้ → ใช้ Excel COM)
- **ช่วงวันที่นับตามเวลาไทย** (`SET TIME ZONE 'Asia/Bangkok'`) — เซิร์ฟเวอร์ตั้งเป็น **UTC**
- **สิทธิ์ ro_safe อ่านจาก `pg_class.relacl` จริง** ไม่ใช่จากไฟล์ SQL (11 ตาราง ณ 3 ต.ค.69)
- **⚠️ `db_guide.md` ตกยุคแล้ว** (48 ตาราง · ขาด `checkout_chatowner`/`chatownerlog`/`coachlog`) — Excel ฉบับนี้ใหม่กว่า
- **⚠️ `checkout_coachlog` บน prod ยังว่าง** (0 แถว) — ยังไม่ได้รัน `coach_db --import-sheet --sync` บนเซิร์ฟเวอร์

### 🌍 เปิดฐานข้อมูลออนไลน์ให้คนนอกต่อตรง — [deploy/postgres_online.sh](deploy/postgres_online.sh) · 4 ต.ค.69 (เจ้าของสั่ง)
*"เปิดทุกอย่างให้คนภายนอกอ่านได้ อ่านเท่านั้น · เปิดพอร์ต · ตั้งไม่ให้ยิงเยอะเกินไป · ทุกตาราง รวมข้อมูลส่วนบุคคล"*
**★ เจ้าของตัดสินใจเองหลังเห็นทางเลือก** — ยกเลิกกฎเดิม "ห้ามเปิดพอร์ต 5432 ออกเน็ต" (ทางอุโมงค์ SSH ยังใช้ได้ตามเดิม)
- `sudo bash deploy/postgres_online.sh setup | add <ชื่อ> | reset <ชื่อ> | remove <ชื่อ> | list | close`
  · ต้องรันด้วย root บนเซิร์ฟเวอร์ (บัญชี `claude` ของผู้ช่วยอ่านอย่างเดียว ไม่มี sudo)
  · ให้ Claude in Chrome รันผ่าน Browser terminal ของ hPanel ได้ — คำสั่งอยู่ใน [deploy/claude_chrome_db_online.md](deploy/claude_chrome_db_online.md)
- **กลุ่ม `ext_online`** (แยกจาก `ro_all` — รัน `postgres_readonly.sql` ซ้ำแล้วจะไม่เปิดคอลัมน์รหัสกลับ)
  อ่านได้ทุกตาราง/view + ตารางใหม่ในอนาคต (`ALTER DEFAULT PRIVILEGES` ทั้ง oxlet และ postgres)
- **ซ่อน 4 คอลัมน์ที่เป็นกุญแจเข้าระบบ ไม่ใช่ข้อมูล**: `auth_user.password` (มีพนักงาน 11 คนตั้งรหัสไว้ —
  แฮชหลุด = แกะรหัสแล้ว login เข้าระบบเราได้) · `dash_tiktok_account.access_token/refresh_token` ·
  `django_session.session_data` → ตาราง 3 ตัวนี้ **`SELECT *` ไม่ได้ ต้องระบุคอลัมน์**
- pg_hba: เฉพาะ `+ext_online` ต่อจากข้างนอกได้ (`hostssl` + scram) · บัญชีอื่นทุกตัวจากข้างนอก = `reject`
  · ตรวจไฟล์ด้วย `pg_hba_file_rules` ก่อนรีสตาร์ต พังแล้วคืนไฟล์เดิมเอง
- **จำกัดความถี่**: `ufw limit 5432/tcp` (IP เดียวกันต่อใหม่ ≤6 ครั้ง/30 วิ) · บัญชีละ 3 สาย ·
  `statement_timeout 30s` · `temp_file_limit 1GB` · `idle_session_timeout 15min` · timezone ไทย
  · **ไม่ได้จำกัดเป็น Mbps** — ฐานข้อมูลทั้งก้อน ~300 MB ที่ทำให้เครื่องหนักคือคำสั่งหนัก ซึ่งตัดที่ 30 วิแล้ว
- SSL ใช้ใบ Let's Encrypt ตัวเดียวกับเว็บ + deploy hook ก๊อปให้ Postgres ตอนต่ออายุ
- **⚠️ ทดสอบได้แค่บางส่วน**: ไวยากรณ์ bash + ตัวเช็คพอร์ต/ufw + คำสั่ง SELECT ที่ใช้ตรวจหลัง setup
  (รันกับ prod ผ่านบัญชีอ่านอย่างเดียว) · ส่วนสร้าง role/แก้ pg_hba ยังไม่เคยรันจริง → **ดูผล setup ครั้งแรกให้ดี**
- **⚠️ หลังเปิดแล้ว psql ตรง = เห็นข้อมูลดิบทั้งหมด** (LINE id · เบอร์ · แชทลูกค้า) ไม่มีการปิดบังแบบหน้าเว็บ SQL
- **★ 17 ต.ค.69 ต่อจากเครื่อง dev: `.env.serverdb` + [scripts/srvdb.py](scripts/srvdb.py)** — ไฟล์เก็บ host/พอร์ต/ฐานข้อมูล/บัญชี/รหัส
  (อยู่ใน .gitignore · **เปลี่ยนรหัสแก้บรรทัด `SRV_DB_PASSWORD=` ที่เดียว**) · `python scripts/srvdb.py --ping` / `"SELECT …"` / `--out ไฟล์`
  · เปิดแบบอ่านอย่างเดียว (`set_session(readonly=True)`) + `statement_timeout` 30 วิ · ไม่พิมพ์รหัสออกที่ไหน ·
  สคริปต์อื่นใช้ `from srvdb import connect` · **รหัสต้องให้เจ้าของพิมพ์ลงไฟล์เอง** (ผู้ช่วยหยิบรหัสจากแชทมาใส่ให้ไม่ได้)

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

### 🛠️ แจ้งผู้พัฒนา (บั๊ก / ขอฟีเจอร์) — [devreq.py](dashboard/services/devreq.py) · 16 ต.ค.69 (เจ้าของสั่ง)
*"เพิ่มฟังก์ชันในการตั้งค่า คือ แจ้งเตือนผู้พัฒนา … สร้างแบบฟอร์มขึ้นมา ฉันจะได้รู้ว่าใคร Request ให้ทำอะไรบ้างแต่ละวัน
… ส่งข้อความแจ้งเตือนมาที่ไลน์ส่วนตัวของฉันแล้ว ฉันจะไปดูระบบเอง"*
- **ที่อยู่**: เมนู ☰ → ตั้งค่า → งานประจำวัน → **"แจ้งผู้พัฒนา (บั๊ก / ขอฟีเจอร์)"** (รายการแรก) · ลิงก์ตรง **`/dashboard/?panel=devrequests`**
- **ฟอร์ม**: ประเภท (เจอบั๊ก / ขอฟีเจอร์ / สอบถาม / อื่นๆ) · หัวข้อ (บังคับ) · รายละเอียด · หน้าที่เจอ (เติมชื่อแท็บที่เปิดอยู่ให้) ·
  ติ๊ก "ด่วน" · แนบรูป/คลิป/ไฟล์ได้ 10 ไฟล์ ไฟล์ละ ≤200 MB
- **ส่งแล้วเด้ง LINE ส่วนตัวเจ้าของ** ด้วย `leadsheet._send_alert` (ผู้รับ `ALERT_TO` = Wattanakit/วัฒนกิจ · บอทตัวส่ง) — **ข้อความอย่างเดียว ไม่ส่งไฟล์เข้า LINE**
  (บอก ประเภท/ด่วน/ใครแจ้ง/หัวข้อ/รายละเอียด 400 ตัว/หน้า/จำนวนรูป-คลิป-ไฟล์ + ลิงก์ `SITE_URL/dashboard/?panel=devrequests`) ·
  **เพดาน `LINE_PER_HOUR`=30/ชม.** (เกิน = บันทึกแต่ไม่เด้ง) · **LINE ไม่ถึง = ยังบันทึก** + จดเหตุผลที่ `line_error` (หน้าเว็บบอกเหตุผลเป็นภาษาคน)
- **รายการด้านล่างแยกรายวัน** ("วันนี้ · 16/10 · 3 เรื่อง · กวาง 2 · มัท 1") · ช่วง 7/30/90/365 วัน · กรองตามสถานะ
  · สถานะ ใหม่ / กำลังทำ / เสร็จแล้ว / ไม่ทำ + หมายเหตุ — **เปลี่ยนได้เฉพาะ `_is_boss`** (แอดมินทั่วไปเห็นอย่างเดียว · เซิร์ฟเวอร์ตอบ 403)
- **สิทธิ์**: แจ้ง/ดู = แอดมินทุกคน (`_is_admin`) · เซลล์/คนงาน = 401 (ยังไม่มีปุ่มในหน้าเซลล์)
- **ตาราง `dash_dev_request`** (`DevRequest` · dashboard migration **0019**) — ใครแจ้ง (ชื่อเล่น + บทบาท · LINE id เก็บไว้แต่ **ไม่ส่งออกหน้าเว็บ**) ·
  `files` JSON `[{id,name,size,kind}]` · `line_ok`/`line_error` · `user_agent` · เติม `db_inventory.TABLES` แล้ว (pii)
- **★ ไฟล์แนบเก็บนอก `/media/`** — `DEV_REQUEST_ROOT` (ค่าตั้งต้น `private_media/devreq/YYYY-MM/<uuid>.<ext>` · gitignored แล้ว)
  เพราะภาพหน้าจอบั๊กมักมีข้อมูลลูกค้า · เปิดได้ทางเดียวคือ `/api/admin/dev_requests/file` (เช็คสิทธิ์ · กัน `../` · id ต้องตรงรูปแบบ)
  · ชื่อไฟล์สุ่มใหม่ ไม่ใช้ชื่อที่อัปมา · **HTML/SVG/ไฟล์อื่นดาวน์โหลดเสมอ** (กันไปรันในโดเมนเรา)
- **★ อัปผ่าน `/track/api/upload` (`target=devreq`) ไม่ใช่ endpoint ใหม่** — nginx เปิดช่องนั้นรับ 220 MB อยู่แล้ว (ช่องปกติ 20 MB · คลิปมือถือเกินง่าย)
  → **ไม่ต้องแก้ config เซิร์ฟเวอร์**
- **ลบไฟล์เก่าเอง**: เรื่องเกิน `KEEP_FILE_DAYS`=180 วัน = ลบไฟล์ (ตัวเรื่องยังอยู่ · ไฟล์ขึ้น "ถูกลบแล้ว") · ไฟล์ที่อัปแล้วไม่ได้กดส่ง ค้างเกิน 2 วัน = ลบ
  · ทำวันละครั้งตอนมีคนส่งเรื่อง (KV `devreq_cleanup`) · จด `dash_event_log` kind=`devreq` ทุกเรื่อง
- **Deploy**: `migrate` (dashboard 0019) + restart · **โฟลเดอร์ `private_media/` สร้างเองตอนอัปครั้งแรก — ต้องเป็นของ user `oxlet`** (อย่ารันคำสั่งด้วย root ให้มันเกิดก่อน)
- **เทสต์**: `python scripts/test_dev_requests.py` (37 ข้อ · test client จริงทั้งสาย upload→create→LINE→list→status→file→cleanup · ปลอมแค่ `requests.post`)
  · ตรวจ UI ด้วย Chrome จริง (ส่งเรื่อง+แนบรูป/ไฟล์ · เปลี่ยนสถานะ · เปิดไฟล์ · จอ 1400/375 ไม่ล้นจอ · ไม่มี JS error)
- **ยังไม่ได้ทำ**: ปุ่มแจ้งจากหน้าเซลล์/แอปมือถือ · แจ้งกลับคนแจ้งเมื่อเปลี่ยนสถานะ

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

### 💬 Connect — ห้องแชทลูกค้ารวม: แอดมินคุม · เซลล์รับลูกค้าตามวันเวร — [connect.py](checkout/connect.py) · 3 ต.ค.69
*"เราจะไม่ให้เซลตอบลูกค้าในไลน์แล้ว เราจะให้มาตอบในระบบเรา … ทีม B และทีม A จะตอบลูกค้าในไลน์ได้วันเว้นวัน
ถ้าเซลคนไหนเทคแอคชั่นลูกค้าคนนั้นไปก่อน ก็จะเป็นลูกค้าของคนคนนั้น แต่ถ้าไม่ตอบภายในห้านาที ระบบจะขึ้น
แจ้งเตือนให้แอดมินประสานงานต่อ · Admin เห็นแชทได้ทั้งหมด แต่เซลล์เห็นได้แค่แชทของตัวเอง"* (เซลล์ ~18 คน)

**ต่อยอดของเดิม ไม่ได้สร้างใหม่** — คลังแชท 2 ฝั่ง (`GroupChat.direction`/`sent_by`) + ตอบผ่าน `chat.send_reply`
มีอยู่แล้ว · ที่เพิ่มคือ "ลูกค้าเป็นของใคร" + "ใครเห็นอะไร" + นาฬิกา 5 นาที

- **ตาราง (checkout migration 0025)**: **`ChatOwner`** (1 แถว/ลูกค้า · OneToOne `LineProfile` CASCADE) =
  เจ้าของ (`owner` ว่าง = อยู่ในคิว) · ทีม · `awaiting_since`/`due_at`/`escalated_at` · ข้อความล่าสุด ·
  **`ChatOwnerLog`** = ประวัติ รับ/โอน/ปล่อย/เลยเวลา/ตอบ (`wait_sec`, `on_time`)/ไม่ต้องตอบ → ที่มาของสถิติเวลาตอบ
- **hook 2 จุด (ห่อ try แยก — Connect พังต้องไม่ทำให้แชท/การส่งพัง)**: `store_chat` (แชท 1:1 ขาเข้า) →
  `note_customer_message` · `chat.send_reply` (ส่งสำเร็จ) → `note_reply` · cron `cron_tick` → `connect.tick()`
- **หน้า**: `/connect/` ([connect.html](checkout/templates/checkout/connect.html)) · มือถือ = รายชื่อ→แตะ→แชทเต็มจอ ·
  แอดมินเข้าทางแท็บ **"Connect (แชทลูกค้า)"** (iframe `?embed=1` · ป้ายตัวเลข = ลูกค้ารอเซลล์รับ) ·
  เซลล์เข้าทางปุ่ม **"แชทลูกค้า"** ในแถบโหมดของหน้าเซลล์ (ป้าย = ลูกค้าของฉันที่รอตอบ + คิว)
  · **ไม่มีหน้าต่างลอย** — ตั้งค่า/สถิติ เปิดในช่องขวาของหน้าเอง

**★ กติกาที่ผมตัดสินแทนเจ้าของ (เจ้าของสั่ง "ลองออกแบบมาดู" โดยไม่ได้ตอบ 6 ข้อที่ถาม) — แก้ได้ในหน้าตั้งค่า**
1. **เวรวันเว้นวัน** คำนวณจาก `anchor_date` + `anchor_team` (ไม่ต้องกรอกทุกวัน) · สลับเวรเฉพาะวันได้ (`overrides`)
   · ตัดวันเที่ยงคืนโซนไทย · **นับเสาร์-อาทิตย์ด้วย** · ค่าตั้งต้น 1 ต.ค.69 = ทีม A · หมุนได้ >2 ทีม
2. **"Take action" = กดรับลูกค้า** — `UPDATE … WHERE owner IS NULL` ล็อกที่ DB (2 คนกดพร้อมกันได้คนเดียว)
   · เซลล์รับได้เฉพาะ **วันเวรทีมตัวเอง + ลูกค้าที่กำลังรออยู่ในคิว** · แอดมินรับ/โอนได้ทุกวัน
3. **ลูกค้าเป็นของคนเดิมตลอด** ไม่ว่าวันนั้นเวรทีมไหน — ยกเว้นแอดมินโอน หรือ **เจ้าของถูกปิดใช้งานในทะเบียน
   (`Employee.active=False`) = คืนคิวเองตอนลูกค้าทักครั้งถัดไป**
4. **นาฬิกาหยุดเมื่อ "ตอบ" เท่านั้น** กดรับเฉยๆ ไม่หยุด (กันกดจองแล้วไม่ตอบ) · ลูกค้าส่งรัวๆ = รอบเดิม เส้นตายไม่เลื่อน
   · ใช้กับ **ทุกข้อความ** ทั้งลูกค้าใหม่และลูกค้าที่มีเจ้าของแล้ว · ปุ่ม **"ไม่ต้องตอบ"** ปิดรอบ (ลูกค้าส่งขอบคุณ/สติกเกอร์)
5. **นับเฉพาะเวลาทำการ** (ค่าตั้งต้น 08:30–20:00 · ตั้งเปิด=ปิด = 24 ชม.) — ทักนอกเวลา = เริ่มนับตอนเปิด
   (ไม่ปลุกแอดมินตอนตี 2) · `due_for()`
6. **เลยเวลา = ขึ้นในหน้า Connect เสมอ** (คำนวณจาก `due_at` เอง ไม่พึ่ง cron) · cron ติดธง `escalated_at`
   · **★ 7 ต.ค.69 ถอดแท็บ "เลยเวลา" ของแอดมินออก (เจ้าของสั่ง "น่าจะบัค เอาออกเลย")** — ไม่ใช่บั๊กโค้ด:
     ทีมตอบลูกค้าในแอป LINE OA Manager ซึ่ง LINE ไม่ส่งกลับมา → แชทที่ตอบแล้วค้าง "เลยเวลา" หมด (วัดจริง 102 แชท)
     · แท็บแรกของแอดมิน = **"รอรับ"** · `VIEWS` ไม่มี `overdue` แล้ว (ลิงก์เก่าตกไปรอรับ) · `counts()` ไม่นับ `overdue`
     · ป้ายเมนูแดชบอร์ด/ชื่อแท็บเบราว์เซอร์ = จำนวนรอรับ · **ยังคงไว้**: นาฬิกา/ป้ายแดงรายแถว · `escalated_at` · สถิติเวลาตอบ
       · ป้ายแดงของเซลล์ (`mineOverdue`) · ถ้าวันหน้าทีมตอบผ่าน Connect จริง จะเอาแท็บกลับต้องเติมคืนทั้ง 4 จุด
   ครั้งเดียวต่อรอบ + จดประวัติ · **ส่ง LINE เข้ากลุ่มแอดมิน = ปิดโดยปริยาย** (`alert_on`) ·
   **บอกเซลล์ทาง LINE ตอนลูกค้าทัก = ปิดโดยปริยาย** (`notify_sellers` — ทีมละ ~9 คน × ทุกลูกค้าใหม่ = กินโควต้าเร็ว)
- ค่าตั้งอยู่ KV **`connect_config`** · `clean_cfg()` **ปฏิเสธพร้อมบอกช่อง** (ไม่เงียบ) · กลุ่มแจ้งเตือนเช็ค
  `push_group_error` (บอทตัวส่งต้องอยู่ในกลุ่ม)
- **สิทธิ์ (เช็คที่เซิร์ฟเวอร์ ไม่ใช่ซ่อนปุ่ม)**: แอดมิน=`full` ทุกแชท · เจ้าของ=`full` · คิวรอรับในวันเวร=`preview`
  (เห็นแค่ข้อความลูกค้าตั้งแต่เริ่มรอบ ≤10 ข้อความ ตอบไม่ได้) · อย่างอื่น=403 · ตัวตนเซลล์ = `employee_of(session)`
  (ชื่อเล่น → ทะเบียน · ทีมจาก `team_id_of(position)`) · **บัญชีที่ไม่มีในทะเบียน = เข้าไม่ได้ พร้อมบอกเหตุผล**
- **ลูกค้าเก่าที่ทักก่อนมี Connect**: `sync_rows()` สร้างแถวให้ (ไม่มีเจ้าของ · **ไม่เริ่มรอบรอ** — ไม่งั้นวันแรก
  ลูกค้าหลายร้อยคนขึ้น "เลยเวลา" พร้อมกัน) · แอดมินเปิดหน้าทีไหนทำให้ (ทุก 2 นาทีพอ)
- **login**: เซลล์ที่กดลิงก์ `/connect/` แล้วต้อง login ด้วย LINE → `_login_with_line_user_id` ส่งกลับ `/connect/`
  (เดิมเซลล์ถูกส่ง `/me/` เสมอ)
- **★ โปรไฟล์ลูกค้า (3 ต.ค.69 · เจ้าของสั่ง "เอา Profile ลูกค้าเข้ามาด้วย" · checkout migration 0026)**
  - **รูปโปรไฟล์ LINE จริง** แทนวงกลมตัวอักษร (ลิสต์ + หัวแชท + การ์ด) · ลิงก์ตาย = `onerror` ลบรูป เห็นตัวอักษรแทน
  - **การ์ดโปรไฟล์ด้านขวาของแชท** (จอ ≥1180px · มือถือ = พับได้ "ข้อมูลลูกค้า" ใต้หัวแชท · กางค้างไว้ไม่พับเองตอนรีเฟรช 6 วิ):
    ชื่อ/ชื่อใน LINE · **สเตตัส LINE** · ทักครั้งแรก (วันที่เต็ม) · จำนวนข้อความ · ภาษา · ดูแลโดย/รับเมื่อ ·
    **เบอร์ที่ลูกค้าพิมพ์มาในแชท** (`phones_in` · มือถือ/บ้าน/ขีด/เว้นวรรค/+66 · ปุ่มโทร+คัดลอก) ·
    **รถที่ลูกค้าหา** (`CustomerNeed` 3 รายการล่าสุด · ปี/งบ/ผ่อน/ดาวน์ · รอรถที่ตรงสเปก)
  - **คิวรอรับ (preview) ได้แค่รูป+ชื่อ+ตัวเลข** — เบอร์/รถที่หา/สเตตัส **ไม่ถูกส่งออกจากเซิร์ฟเวอร์เลย** จนกว่าจะกดรับ
  - **★ ข้อยกเว้นของกติกา "ไม่เก็บรูปโปรไฟล์" (ก.ย.69)**: เก็บลิงก์รูปที่ **`ChatOwner.picture_url`** ไม่ใช่ `LineProfile`
    → **พนักงานไม่มีวันมีรูปเก็บไว้** (ไม่มีแถวในตาราง Connect) · รูปหายพร้อมลูกค้า (60 วัน) · เก็บแค่ลิงก์ LINE ไม่โหลดไฟล์
    · `touch_profile()` คืน `picture` ออกมาให้ (ไม่ต้องยิง LINE ซ้ำ) แต่ **ไม่เขียนลง LineProfile** (มีเทสต์ยืนยัน)
  - **ดึงใหม่ทุก 7 วัน** (`PIC_REFRESH_DAYS` · ลิงก์ตายเมื่อลูกค้าเปลี่ยนรูป) · ดึงไม่ได้ (บล็อกบอท/เน็ต) = **เว้น 1 วัน** ไม่ยิงทุกครั้ง
    · ดึงตอนลูกค้าเริ่มรอบรอใหม่ (ใน thread ของ webhook อยู่แล้ว) + **`fill_pictures_bg()`** ทยอยเติมลูกค้าเก่า
    นาทีละ 20 คนต่อ worker ตอนมีคนเปิดหน้า Connect · **จองแถวก่อนดึง** (UPDATE … WHERE picture_at = ค่าเดิม)
    กัน gunicorn หลาย worker ดึงคนเดียวกันซ้ำ · ดึงแล้วอัปเดตชื่อ/สเตตัส/ภาษาใน `LineProfile` ไปด้วย

- **★ โหมดทดสอบ (3 ต.ค.69 · เจ้าของขอ "จำลองบัญชีเซลล์สักคนมาได้มั้ย เดี๋ยวทดสอบเอง")** — Connect → ตั้งค่า →
  การ์ด "ทดสอบระบบด้วยบัญชีจำลอง" · API `POST /connect/api/test {action: as|exit|customer|say|clear}` (แอดมินเท่านั้น)
  - **บัญชีเซลล์จำลอง** `ทดสอบเซลล์ A` / `ทดสอบเซลล์ B` (`Employee` · ทีมตามชื่อ · `track_checkin=False` ไม่โผล่ในเช็คชื่อ)
    สร้างตอนกดใช้ครั้งแรก · แอดมินสลับไปใช้หน้าจอแบบนั้นด้วย session `connect_as` → **สิทธิ์คิดแบบเซลล์เป๊ะ**
    · แถบม่วงบอกตลอดว่ากำลังใช้บัญชีจำลอง + ปุ่มกลับเป็นแอดมิน
  - **★ สลับเป็นเซลล์จริงไม่ได้** — `_ctx` เช็คซ้ำทุกคำขอว่าคนจริงยังเป็นแอดมิน **และ** เป้าหมายชื่อขึ้นต้น `ทดสอบเซลล์ `
    (ปลอม session ชี้ไปเซลล์จริง = ถูกเมิน · มีเทสต์) · เหตุผล: กดรับ/ตอบในโหมดนั้นจะกลายเป็นการกระทำของเซลล์จริง
  - **ลูกค้าจำลอง** `user_id` ขึ้นต้น **`TEST-`** (ไม่มีทางเป็น LINE id) — **ตอบไปไม่ยิง LINE · ไม่ติดสวิตช์ล็อกการส่ง**
    (`chat.send_reply` + `replyOn` ใน `api_chat` ต้องตรงกัน — เคยพลาดฝั่งหน้าเว็บ ช่องตอบถูกล็อกทั้งที่ส่งได้) ·
    **นับ 5 นาทีทันทีทุกเวลา** (`due_for(ignore_hours=True)` — ทดสอบกลางคืนได้) · ไม่ส่ง LINE แจ้งเตือน/ไม่ดึงรูป ·
    มีช่อง **"พิมพ์แทนลูกค้า"** ทดสอบข้อความใหม่จากลูกค้า
  - บัญชีจำลองรับ/ตอบ **ลูกค้าจริงได้** (ทดสอบกับ LINE ของคนในบ้าน) — หน้าเว็บ `confirm()` ก่อนส่งหาลูกค้าจริงทุกครั้ง
  - **"ล้างข้อมูลทดสอบ"** (`sim_clear`) ลบลูกค้าจำลอง+แชท+บัญชีจำลอง+ประวัติของบัญชีจำลอง ·
    **ลูกค้าจริงที่บัญชีจำลองถือไว้ → คืนคิว** · ข้อความที่บัญชีจำลองส่งหาลูกค้าจริงไม่ลบ (ส่งออกไปจริงแล้ว)
  - **★ 9 ต.ค.69 — บัญชีทดสอบที่เป็น "คนจริง" (`connect_config.test_accounts` · ค่าตั้งต้น `["Wattanakit"]` · เจ้าของสั่ง)**
    ชื่อเล่นในทะเบียน · โผล่ **ท้ายรายการโอน** เป็น "Wattanakit · ทีม ทดสอบ" (`seller_list()` ติด `test: True` ·
    ไม่มีทีมจริง = ทีม "ทดสอบ" ซึ่งไม่มีวันอยู่ในเวร และไม่ถูกนับเป็นตัวเลือกเวรใน `api_config`) ·
    การ์ดทดสอบมีปุ่ม **"ใช้หน้าจอแบบ Wattanakit"** (`api_test {action:"as", emp:<id>}` — **รับเฉพาะ `is_test_seller()`**
    สลับเป็นเซลล์จริงยังทำไม่ได้) · จ่ายเบอร์ให้ = ไม่ส่งใบเข้ากลุ่มจ่ายเบอร์จริง (`is_test_seller` เดิม) ·
    "ล้างข้อมูลทดสอบ" **คืนลูกค้าที่ถือไว้เข้าคิว แต่ไม่ลบตัวคน/ประวัติ** (ลบเฉพาะชื่อขึ้นต้น "ทดสอบเซลล์ ")
    · ⚠️ บัญชีนี้ **ตอบลูกค้าจริงได้จริง** เหมือนบัญชีจำลอง — ใช้กับ LINE ของคนในบ้าน

- **★ 9 ต.ค.69 — รายชื่อโชว์ "ยังไม่อ่าน" + ตัดป้ายทีมรายแถว (เจ้าของสั่ง)** · checkout migration **0033**
  *"ไม่ต้องบอกทีมว่าทีมไหนของวันนี้ มันดูรกตา · เพิ่มฟอนต์ตัวหนาหรือติ๊กสีแดงด้านหลังเวลา … ยังไม่อ่าน"*
  - **ป้าย "ทีม A" ในแต่ละแถวออกแล้ว** (ทุกแถวขึ้นทีมเวรวันนี้ซ้ำกันหมด) · ชิป "เวรวันนี้ ทีม A · พรุ่งนี้ทีม B"
    บนหัวหน้า + ทีมในหัวแชท/การ์ดข้อมูลลูกค้า **ยังอยู่**
  - **`ChatOwner.read_at`** = อ่านถึงข้อความลูกค้าเมื่อ · **ยังไม่อ่าน = `last_in_at > read_at`** (`is_unread()`)
    → ชื่อ+ข้อความล่าสุดตัวหนา · เวลาสีแดง + **จุดแดงหลังเวลา** (`row_json.unread` · CSS `.cn-row.unread`/`.cn-dot`)
  - **อ่านแล้ว = ใช้ร่วมกันทั้งทีม** (แบบ LINE OA ไม่แยกรายคน): แอดมิน/เจ้าของ **เปิดแชทเต็ม** (`mark_read` ใน `api_chat`)
    หรือ **ตอบแล้ว** (`_reply_done` ที่ปิดรอบ) · **เซลล์ดูตัวอย่างในคิวรอรับไม่นับ** · **ตอบอัตโนมัติของเพจไม่นับ**
    · อ่านถึง `last_in_at` ที่เห็นตอนเปิด (ไม่ใช่เวลาตอนนี้) — ลูกค้าส่งมาระหว่างนั้นยังเป็นยังไม่อ่าน
    · เขียนฐานข้อมูลเฉพาะตอนสถานะเปลี่ยน (หน้าแชทรีเฟรชทุก 6 วิ)
  - migration ตั้งแถวเดิมทั้งหมดเป็นอ่านแล้ว **ยกเว้นลูกค้าที่ยังรอคำตอบ** (วัด prod 9 ต.ค.: 141 แถว · 86 แถวรอเกิน 2 วัน
    = ส่วนใหญ่ทีมตอบในแอป LINE OA Manager ไปแล้ว) · แถวที่ `sync_rows` สร้างให้ลูกค้าเก่า = อ่านแล้ว
  - ⚠️ อ่านใน **แอป LINE OA Manager ไม่ถูกนับ** (LINE ไม่ส่งกลับมา) — เหมือนปัญหาเดียวกับนาฬิกา 5 นาที

- **★ 3 ต.ค.69 เจ้าของแจ้ง "หน้าจอแชทเล็กมาก" — จัดใหม่ให้พื้นที่ไปที่แชท** (วัดจริงบนจอ 1590×915 ในแท็บแดชบอร์ด:
  พื้นที่ข้อความ **285 → 541px**) · หัวแชทเหลือแถวเดียว (ชื่อซ้าย ปุ่มขวา · นาฬิกาเป็นป้ายเล็ก · ประวัติซ่อนหลังปุ่ม) ·
  สถิติ/ตั้งค่าย้ายไปแถบบน (แท็บในลิสต์ไม่กินแถว) · ปุ่ม **"ข้อมูลลูกค้า"** ซ่อนคอลัมน์ขวาได้ (จำไว้ใน localStorage
  `cn_side` · แชทกว้าง 672 → 942px) · แดชบอร์ดไม่โชว์บรรทัดอธิบาย/เวลาดึงข้อมูลในแท็บนี้ + **`fitConnectFrame()`
  วัดตำแหน่งจริงให้ iframe ยาวถึงขอบล่างจอพอดี** (เดิมสูงตายตัว `100vh-190px`) · ปุ่ม "เต็มจอ ↗" อยู่ในแถบบนของ Connect
  · **หัวแชทถูกวาดใหม่ทุก 6 วิ** → สถานะที่ผู้ใช้เปิดค้าง (ประวัติ/ข้อมูลลูกค้าบนมือถือ/เซลล์ที่เลือกโอน) เก็บใน `S` ไม่ใช่ DOM
- **★ 11 ต.ค.69 รอบ 2 (หน้าตาใหม่ "ศูนย์ควบคุมลีด") — เจ้าของ "ช่อง chat เล็กไป · ตัวหนังสือบอกเฉยๆ ไม่ต้องใหญ่ มันเปลืองพื้นที่"**
  (วัดใน Chrome: ฝังในแดชบอร์ด พื้นที่ข้อความ **370 → 515px** · เต็มจอ 1590×905 **537 → 653px** · มือถือรายชื่อ 496 → 546px)
  · หัวหน้า (`.lc-top`) เหลือบรรทัดเดียว — ชื่อหน้า 15px + คำอธิบายต่อท้ายตัดด้วย … (`.lc-tt` · ชี้เมาส์เห็นเต็ม) · จอ ≤600 ซ่อนนาฬิกา
  · แถบ 3 ชั้น (`#lc-flow`) เป็นแถวเดียว ~28px (เดิม 94) · บรรทัดอธิบาย "ลัด" ย่อเป็นป้าย "ใบร่าง/สายเข้า → ชั้น 2" รายละเอียดอยู่ใน `title`
    · จอแคบยังเป็นแถวเดียว (เดิมซ้อน 3 บรรทัด)
  · แท็บรายชื่อแถวเดียว ไม่มีไอคอน (เดิม 2 บรรทัด) · ตัวกรองด่วนไม่มีแถบเลื่อน · ล้อเมาส์เลื่อนแนวนอน · ขอบขวาจางเมื่อมีต่อ ·
    **"ตัวกรองเพิ่ม" ย้ายมาอยู่หน้าสุด** (เดิมอยู่ท้ายต้องเลื่อนหา) · แถบเตือน (`.cn-banner`) เตี้ยลง
  · แดชบอร์ดแท็บ Connect: หัวเว็บเตี้ย (`_hdrSlim` ใน `render()` — ไม่มี breadcrumb · ชื่อหน้า 16px · โลโก้ 30px) แก้แบบ inline
    **ไม่แตะ globals.css** (ไม่ต้อง collectstatic) · แท็บอื่นหน้าตาเดิม
- **★ 11 ต.ค.69 รอบ 5 — เจ้าของ "ตัดออก ไม่ก็เหลือแค่ส่วนที่จำเป็นเท่านั้น" (แถบซ้อนกัน 4 ชั้นเหนือแชท)**
  (วัดใน Chrome · แท็บ Connect 1590×905: กรอบแชทเริ่มที่ **y=14** สูง 883 จาก 905 · ไม่มี JS error · ไม่ล้นจอ)
  · **ตัดทิ้งทั้งแถว**: หัวหน้า `.lc-top` (ชื่อหน้าซ้ำกับเมนู + คำอธิบาย + นาฬิกา "นับเวลาจริง") · แถบ 3 ชั้น `#lc-flow`
    (ตัวเลขซ้ำกับป้ายบนเมนู) · `renderFlow()` ลบแล้ว · **คำอธิบายของแต่ละหน้าย้ายไปเป็น `title` ของปุ่มเมนู** (ชี้เมาส์เห็น)
  · **ที่เหลือ = "เวรวันนี้ + กระดิ่ง" ย้ายเข้าแถบเมนู** (`.lc-st` ใน `#lc-rail`) — เมนูซ้ายจอกว้าง: ใต้โลโก้ ·
    แถบแนวนอน (ฝัง/จอ ≤900): ชิดขวา **`position: sticky; right: 0`** (แอดมินมือถือแท็บ 6 อันเลื่อนเกินจอ กระดิ่งต้องไม่เลื่อนหายตาม)
    · มือถือ ≤600 = "เวรวันนี้ ทีม A" ไม่มี "พรุ่งนี้" (`.lc-tmr`) · ชิปในเมนูซ้ายต้อง `display:block` (`.cn-chip` เป็น flex → ข้อความแตกทีละคำ)
  · ฝังในแดชบอร์ด/จอแคบ: **ซ่อนโลโก้ `.lc-brand`** (แดชบอร์ด/หน้าเซลล์มีของตัวเอง) · ฝัง = ซ่อนลิงก์ "หน้าแบบเดิม" ในแถบ
    → ย้ายไปไว้ท้ายหัวข้อ "ตั้งค่าละเอียด" ในหน้ากฎ (ยังส่ง `&embed=1` ต่อ)
  · **กล่องแจ้งเตือน `.cn-alerts` วางเทียบกับ `.lc-main`** (`position: relative`) ไม่ใช่ทั้งหน้า — แถบแนวนอน: top 6 / right 12 ·
    เมนูซ้ายจอกว้าง: left 8 / top 8 (ข้างเมนู) · ⚠️ เคยตั้งเป็นพิกัดทั้งหน้า (left 232) แล้วกล่องไปโผล่กลางจอ
  · **แดชบอร์ดแท็บ Connect (index.html)**: header ติดคลาส **`hdr-cn`** → **จอ ≥1100px ซ่อนหัวเว็บทั้งแถบ** (`<style>` ในหน้า ·
    แถบเมนูซ้ายมีโลโก้/ผู้ใช้/ออกจากระบบอยู่แล้ว) · จอแคบเหลือ ☰ + โลโก้ + สลับธีม + ออกจากระบบ (ตัดป้ายบทบาท/ออนไลน์/
    กระดิ่งแดชบอร์ด/ดูในฐานะ/รีเฟรช — ไม่เกี่ยวกับแชท · `online-count`/`alerts-bell` เช็ค null อยู่แล้ว) · แท็บอื่นหน้าตาเดิม
- **★ 11 ต.ค.69 รอบ 6 — เจ้าของ "กรอบแดงซ้ำซ้อนกัน ลดอันล่างออก"** (แถบเมนูด้านบน กับหัวรายชื่อ รอรับ/มีเจ้าของ/ทั้งหมด
  ที่เป็นแถบปุ่มมีตัวเลขเหมือนกัน · "กล่องแชทรวม 202" = "รอรับ 202")
  · **หัวรายชื่อเหลือแถวเดียว** (`#cn-tools`): **มุมมองเป็น dropdown** `#cn-view` (ตัวเลขอยู่ในชื่อตัวเลือก ·
    ไม่วาดทับตอนกำลังเปิดเลือก — รายชื่อรีเฟรชทุก 8 วิ) + ค้นหา + ปุ่ม **"ตัวกรอง"** `#cn-fbtn` (★ 17 ต.ค.69 เป็น dropdown `#cn-fsel` แล้ว — ดูด้านล่าง)
  · ช่องทาง/เซลล์/ปุ่มลัด 7 ตัว/ตัวกรองเพิ่ม ย้ายเข้ากล่อง `#cn-fbox` ที่กางจากปุ่มนั้น (`S.fltOpen`)
  · **กรองอยู่ = ปุ่มเป็นสีม่วง + นับจำนวน + บรรทัด "กรองอยู่: … ล้าง"** (`#cn-active` · `activeFilters()`) — ตัวกรองที่ซ่อนอยู่ต้องเห็นเสมอ
  · **★ 17 ต.ค.69 เจ้าของ "ตัวกรองเยอะไป เหลือแค่นี้พอ" แล้ว "ตัวกรองเป็น Drop Down ดีกว่า"** → ปุ่ม "ตัวกรอง" + กล่อง `#cn-fbox` + บรรทัด `#cn-active`
    **เลิกแล้ว** แทนด้วย **dropdown `#cn-fsel` ตัวเดียว 5 ตัวเลือก (เลือกได้ทีละอย่าง)**: รวมทุกช่องทาง · Facebook · LINE@ · TikTok (→ `src`) ·
    รอตอบกลับ (→ `awaiting=1` ทุกช่องทาง) · กรองอยู่ = dropdown สีม่วง · `FLT_OPTS`/`fltValue()`/`renderFilter()`
    · เอาออก: ปุ่มลัด 6 ตัวที่เหลือ · แผงขั้น/ความร้อน/เหตุผล/รุ่น/งบ/วันที่ · dropdown เลือกเซลล์ (เซิร์ฟเวอร์ยังรับตัวกรองเดิมทุกตัว — แอป/กระดิ่งใช้ได้ต่อ)
    · TikTok = ยังไม่มีแชท TikTok ใน Connect → รายชื่อว่างพร้อมบอกเหตุผล · รายชื่อว่างเพราะตัวกรอง = มีปุ่ม "ล้างตัวกรอง"
    · **กระดิ่งตั้งตัวกรองอื่น (เงียบ N+ วัน / รถใหม่ตรง) = dropdown มีตัวเลือกที่ 6 ชื่อตัวกรองนั้น** (`_x` · ห้ามกรองแบบมองไม่เห็น) · เลือกอย่างอื่น = ล้างทิ้ง
    ไม่งั้นรายชื่อหายแล้วไม่มีใครรู้ว่าเพราะกรอง · "ล้าง" ล้างทั้ง S.f + ช่องทาง + เซลล์ (`clearFilters()`)
  · แท็บของห้องพัก Lead (รอจ่ายเบอร์/จ่ายแล้ว/นาฬิกาโทร) ยังใช้ `.cn-tab` เหมือนเดิม · `cn-tabs` ไม่มีแล้ว
  · ตรวจ Chrome 1590/390 (แอดมิน/เซลล์): หัวรายชื่อสูง 48px · ปุ่มลัดยิง `awaiting=1` · dropdown ยิง `view=` ถูก · ไม่ล้นจอ · ไม่มี JS error
- **★ 11 ต.ค.69 รอบ 7 — เจ้าของ "โหลดนานเพราะอะไร"** (หลัง deploy รายชื่อค้าง "กำลังโหลด…" · รูปในแชทเทาค้าง)
  · **ไม่ใช่เครื่องเต็ม** (load 0.14) · **ไม่ใช่โหลดรูปจาก LINE** (รูปของแชทนั้นอยู่บนดิสก์แล้ว) · วัดที่ข้อมูลขนาดเท่า prod
    (ลูกค้า 2,314 · ข้อความ 33k): คำขอรายชื่อปกติ ~0.1 วิ แต่ **คำขอแรกของแต่ละ worker หลังรีสตาร์ท 2–3 วิ** · 4 ต้นเหตุ:
  1. **`scan_contacts` (เก็บตกเบอร์/ไอดีจากแชทเก่า) จำแค่ในหน่วยความจำ + ทำในคำขอรายชื่อ** → deploy ทีไร ทุก worker (5 ตัว)
     อ่านแชท 150 ห้องทีละห้องก่อนตอบ (prod เข้าเงื่อนไข **983 ห้อง** และไม่เคยไปถึงแถวที่ 151) · แก้: จำใน KV
     **`connect_cscan`** (`{chat id: เวลาข้อความล่าสุดที่สแกน}` · ตัดแถวที่ครบแล้วทิ้ง) + **`scan_contacts_bg()`** thread แยก +
     Postgres advisory lock `7_406_063` (worker เดียวสแกนทีละรอบ) · ดูผู้สมัคร 2,000 แถว (id+เวลา) แล้วทำทีละ 150 ที่ยังไม่เคยสแกน
  2. **`checkout_groupchat` ไม่มี index ที่ `sender_id`** → เปิดแชท/รีเฟรช 6 วิ/เก็บตก = อ่านทั้งตาราง 33k แถวทุกครั้ง
     (EXPLAIN prod: Seq Scan · 12 ms · 1,527 buffers) · แก้: index `(sender_id, -sent_at)` — **checkout migration 0036**
  3. **`people._load` อ่านชีตพนักงานในคำขอทุก 10 นาที/worker** (วัด 4 วิ ตอน token เย็น) → **แคชหมดอายุแต่ยังมีของเดิม
     = ตอบด้วยของเดิม แล้วโหลดใหม่ใน thread** (`people.BG` · ยังไม่เคยโหลด/`invalidate()` = โหลดตรงเหมือนเดิม · เทสต์ตั้ง `BG=False`)
  4. **nginx ไม่บีบอัด JSON** (`gzip_types` ถูกคอมเมนต์ใน nginx.conf ของเครื่อง) → รายชื่อ ~140 KB ทุก 8 วิ ·
     แก้: [deploy/nginx-gzip.conf](deploy/nginx-gzip.conf) → `/etc/nginx/conf.d/oxlet-gzip.conf` (root · ไม่แตะไฟล์ของ certbot)
  · ผลวัด: คำขอแรกหลังรีสตาร์ท **2.1 → 0.34 วิ** · ปกติ ~0.09 วิ เท่าเดิม · เทสต์ใหม่ใน `test_connect.py` [26] (9 ข้อ ·
    รีสตาร์ทแล้วไม่อ่านซ้ำ · รอบถัดไปไปต่อแถวที่ยังไม่สแกน · แคชชื่อหมดอายุตอบทันที)
  · **บทเรียน**: งานเก็บตก/งานหนักที่ "ทำครั้งเดียวต่อ process" = **ทำซ้ำทุก deploy คูณจำนวน worker** และถ้าอยู่ในคำขอ
    คนแรกที่เปิดหน้าหลัง deploy รับไปเต็มๆ — ต้องจำผลไว้นอก process และทำนอกคำขอเสมอ

- **★ ข้อมูลลีดของลูกค้า (3 ต.ค.69 · เจ้าของสั่ง "ส่วนนี้เราจะเก็บข้อมูลตามนี้ และเก็บข้อมูลอัตโนมัติตามนี้" ·
  checkout migration 0027 · `ChatLead` 1 แถว/ลูกค้า)** — แผงขวาของแชทกลายเป็นฟอร์มลีด **ช่องเดียวกับชีตลีด**
  + ช่องของ **ใบจ่ายลีด** + แก้ชื่อ/ใส่แท็กได้แบบ LINE OA Manager · API `POST /connect/api/lead {id, field, value}`
  - **ช่องที่คำนวณได้ "ไม่เก็บซ้ำ"** (โชว์อย่างเดียว): ว/ด/ป·เวลา = ทักครั้งแรก · เซลล์ = เจ้าของ ·
    วันเวลาที่ติดต่อ = ตอบครั้งแรก · จำนวนอัพเดท = รอบที่ตอบ (`ChatOwnerLog.REPLY`) · อัพเดทล่าสุด = เราตอบล่าสุด
  - **เติมอัตโนมัติ (`autofill`) เฉพาะช่องที่ว่างและยังไม่เคยเติม** · `auto` จดว่าเติมจาก `แชท`/`ใบจ่ายลีด`/`ระบบ`
    (หน้าเว็บโชว์ป้าย "จาก…") · **คนแก้/ลบช่องไหน = `คน` → ระบบไม่เติมทับ/ไม่เติมกลับอีกเลย**
    · ข้อยกเว้นเดียว: **ใบจ่ายลีดแทน "ค่าตั้งต้นของระบบ" ได้** (เช่นช่องทาง LINE OA → TikTok ตามใบ) แต่ไม่แทนที่จับจากแชท
  - **จากแชท**: เบอร์ (`phones_in`) · รุ่นที่ถาม (`car_in` = `purchase_report.match_model` กับชื่อรุ่นใน dropdown
    "CAR / สูตร" ของชีตลีด) · **จากระบบ**: ช่องทาง `LINE@` · สาขา · Admin (คนที่โอนล่าสุด ไม่งั้นคนแรกที่ตอบที่ไม่ใช่เจ้าของ)
    — กติกาละเอียดดูหัวข้อ "dropdown ชุดเดียวกับชีตลีด" ด้านล่าง
  - **★ จากใบจ่ายลีดที่แอดมินโพสต์ในกลุ่มจ่ายเบอร์** (`find_slip`): หาใน `GroupChat` ของกลุ่ม `LineGroup.kind=lead`
    หรือชื่อมี "จ่ายเบอร์" → อ่านด้วย **`leadgroup.parse_leadsheet` ตัวเดิม** → จับคู่ด้วย **เบอร์เต็ม** (ค้น 4 ตัวท้าย
    แล้วตรวจซ้ำ) หรือ **ชื่อไลน์ตรงทั้งชื่อ** (ไม่ fuzzy — บทเรียนเดิม) → เติม Code/ADS/Account/ชื่อลูกค้า/ID LINE/
    ช่องทาง/รถ/ไลฟ์/เพิ่มเติม · **ค้นซ้ำได้ทุก 30 นาทีต่อลูกค้า** (`_slip_at`) · หยุดค้นเมื่อมี Code แล้ว
    · ⚠️ ใช้ได้ต่อเมื่อเปิด "เก็บแชทกลุ่ม" (prod เปิดแล้ว) และใบยังไม่หมดอายุ 90 วัน
  - **ใบจ่ายลีด (ย่อ)** `slip_text()` รูปแบบเดียวกับที่แอดมินโพสต์ + `@เจ้าของ` ท้ายสุด → **`parse_leadsheet` อ่านกลับได้**
    (มีเทสต์) · ปุ่มคัดลอกไปวางในกลุ่มจ่ายเบอร์
  - **บันทึกทีละช่อง** (2 คนแก้คนละช่องไม่ทับกัน) · **แผงไม่ถูกวาดทับตอนกำลังพิมพ์** (รีเฟรช 6 วิ เช็ค `activeElement`
    + ลายเซ็นข้อมูล) · สิทธิ์ = เจ้าของ/แอดมิน · คิวรอรับ (preview) **ไม่ส่งข้อมูลลีดออกเลย** ·
    ลูกค้าจำลองเติมอัตโนมัติได้ **ยกเว้นค้นใบจ่ายลีด** (4 ต.ค.69 · ดูข้างล่าง)
  - รายชื่อลูกค้าใช้ **ชื่อลูกค้าที่กรอก** ก่อนชื่อ LINE · โชว์แท็ก · ค้นด้วยเบอร์/เลขลีด/แท็กได้
  - **ยังไม่ได้ทำ (ต้องถามเจ้าของก่อน)**: เขียนลงชีตลีดอัตโนมัติ — กระทบตัวเลขแดชบอร์ดทั้งระบบ + เสี่ยงซ้ำกับแถว
    ที่แอดมินกรอกเอง · ตอนนี้เก็บใน Postgres อย่างเดียว

- **★★ ฟอร์มลีดใช้ dropdown "ชุดเดียวกับชีตลีด" + เติมอัตโนมัติตามข้อมูลจริง (4 ต.ค.69 · เจ้าของถาม
  "มันต้องกรอกออโต้มั้ย ไปดูดรอปดาวต่างๆ ที่ใช้ในนี้" พร้อมรูปฟอร์มของลูกค้าจำลองที่ว่างทุกช่อง)**
  - **ต้นเหตุฟอร์มว่าง**: `autofill` **ข้ามลูกค้าจำลองทั้งฟังก์ชัน** → ทดสอบด้วยลูกค้าจำลองแล้วดูเหมือนระบบไม่เติมอะไรเลย
    · ตอนนี้ลูกค้าจำลองเติมจากแชทของตัวเอง + ค่าตั้งต้นของระบบ · **ยกเว้นค้นใบจ่ายลีด** — เบอร์ที่พิมพ์ทดสอบอาจตรงใบ
    ของลูกค้าจริง แล้วดึงชื่อ/ID LINE ของจริงมาปนในข้อมูลทดสอบ (มีเทสต์ยืนยัน)
  - **`google_sheets.fetch_lead_dropdowns()`** อ่านกฎ dropdown (data validation) ของ **แท็บเดือนล่าสุดที่ไม่ใช่อนาคต**
    (ตอนนี้ "ตุลาคม 69") · จับคอลัมน์ด้วย **ชื่อหัวตาราง** (`_resolve_lead_colmap` ตัวเดิม) ไม่ใช่ตำแหน่ง ·
    รองรับ `ONE_OF_LIST` + `ONE_OF_RANGE` · ตัดช่องว่างหัวท้าย + ตัวซ้ำ
    · **ไม่อ่านแถวลูกค้า** — ขอแค่หัวตาราง + กฎ dropdown (`fields=…dataValidation`) + คอลัมน์ เซลล์/สาขา (หาสาขาของเซลล์)
  - **อ่านใหม่ทุกชั่วโมง** จาก `cron_tick` → `connect.tick()` (ใน thread) เก็บ KV **`connect_lead_dropdowns`** ·
    หน้าเว็บอ่านจาก KV เท่านั้น (**ไม่ยิงเน็ตในคำขอหน้าเว็บ**) · อ่านไม่ได้ = **คงชุดเดิม** + เว้น 15 นาทีค่อยลองใหม่ ·
    ยังไม่เคยอ่านได้เลย = `DD_FALLBACK` (ชุดที่จดจากแท็บ ต.ค.69 · หน้าเว็บบอกว่าเป็น "ชุดที่จำไว้")
    · **ทำไมไม่ฮาร์ดโค้ด**: ตัวเลือกเปลี่ยนตามเดือน (แท็บ ก.ค. กับ ต.ค. ไม่เหมือนกัน) · แอดมินเพิ่มตัวเลือกในชีต
      แล้วเห็นในหน้า Connect ไม่เกิน 1 ชม.
  - **ฟอร์ม**: ช่องไหนในชีตเป็น dropdown → เป็น `<select>` ตัวเลือกชุดเดียวกันเอง (`leadOptions.dropdowns` · ไม่ต้องแก้
    `LEAD_UI`) — ตอนนี้ 9 ช่อง: type · ช่องทาง · สาขา · Admin · ทีมไลฟ์ · FOCUS · แจ้งหลักฐานการโทร (เดิมเป็นติ๊ก
    แต่ชีตมี 3 ค่า) · CAR/สูตร · ประเภทลูกค้า · อาชีพ/รายได้/อายุงาน/ประวัติผ่อน กลายเป็น dropdown เองถ้าชีตตั้ง ·
    ค่าเดิมที่ไม่อยู่ในตัวเลือก = โชว์เป็น "(นอกตัวเลือกชีต)" **ไม่ทิ้งข้อมูล** · ช่องที่ map อยู่ที่ `DD_COLS`
  - **กติกาเติมอัตโนมัติ (ข้อมูลจริงเป็นตัวตัดสิน)**:
    · ช่องทาง = **`LINE@`** (ลีดจาก LINE ส.ค.–ต.ค. 741 แถว เขียน `LINE@` 740)
    · สาขา = **สาขาที่ลีดของเซลล์คนนั้นไปจริง** (เชื่อเมื่อสาขาเดียว ≥90% และ ≥10 แถว) · ยังไม่มีเจ้าของ = สาขาภาพรวม
      (≥90% · ≥20 แถว) — วัดจริง ส.ค.–ต.ค. 6,945 แถว ชลบุรี 100% · รับลูกค้าแล้วสาขาตามเซลล์ (แทนค่าตั้งต้นของระบบได้)
    · Admin = คนที่โอน/ตอบ **เฉพาะชื่อที่ตรงตัวเลือก Admin ของชีตเป๊ะ (ตัวพิมพ์ด้วย)** (เจ้าของ/เซลล์ที่ตอบเองไม่ใช่
      Admin ของลีด) · ⚠️ ห้ามใช้ `dd_pick` ช่องนี้ — บัญชีแอดมินระบบชื่อเล่น `admin` จะกลายเป็นตัวเลือก `ADMIN` ของชีต
      ซึ่งเป็นคนละความหมาย (เจอตอนรีวิว · มีเทสต์ที่พิสูจน์แล้วว่าโค้ดเดิมพัง)
    · **CAR/สูตร เติมเฉพาะชื่อที่ตรงตัวเลือกเป๊ะ** · รุ่นกำกวม ("สนใจ city" = 4 หรือ 5 ประตู? "civic" = FC/FE/FK?)
      = เติมแค่ "รถลูกค้าถาม" ให้คนเลือกรุ่นเอง · **2 ช่องต้องมาจากข้อความเดียวกัน** (กัน "Civic" คู่กับ "Camry")
      · ตัวเลือกที่ไม่ใช่ชื่อรุ่น (ลูกค้าไม่ตอบ/ไม่ระบุรุ่นรถ/ยี่ห้อล้วน) ไม่ถูกใช้จับรถ
    · **★ บอกแค่ยี่ห้อก็นับ (4 ต.ค.69 · เจ้าของแจ้ง "ลูกค้าก็บอกอยู่นะ อีซูซุ" แต่ใบจ่ายลีดขึ้น "รถ : -")** —
      `brand_in()` (`_TH_BRAND` ไทย + `_BRAND_EN` อังกฤษ) → ได้ "รถลูกค้าถาม" · CAR/สูตร ว่างไว้ (อีซูซุ = D Max/MuX/Mu7?)
      **ยกเว้นยี่ห้อที่ชีตมีตัวเลือกระดับยี่ห้อ** (Benz/BMW/MG/Hyundai/Kia) → ได้ CAR/สูตร ด้วย ·
      **"เกียร์" ≠ Kia** (`เกีย(?!ร)` — คำว่าเกียร์โผล่บ่อยมากในแชทซื้อรถ)
    · **★ ต่อข้อความข้างเคียงที่เป็นเรื่องเดียวกัน** (`_car_context`) — ลูกค้าพิมพ์ทีละข้อความ ("อีซูซุ" / "ปี2015-2017")
      → "รถลูกค้าถาม" = `อีซูซุ ปี2015-2017` · ต่อเฉพาะข้อความสั้น (≤80 ตัว) ที่บอก ปี/งบ/ผ่อน (`_has_spec` · ปีไม่มีคำว่า
      "ปี" ก็นับ แต่ไม่จับกลางเบอร์โทร) หรือพูดถึงรถแบบไม่ชัด · **รุ่นชัดคันอื่น = คนละคัน ไม่ต่อ** · ย้อนหลังได้ 2 ข้อความ ไปข้างหน้า 3
      · **ลูกค้าพิมพ์ตามมาทีหลัง = เติมต่อจากของเดิมที่ระบบใส่** (เฉพาะตอนข้อความเดิมอยู่ในข้อความใหม่ · ที่คนแก้ไม่แตะ)
    · **ชื่อรุ่นภาษาไทยเพิ่ม** ใน `leadgroup._TH_MODEL` (ดีแม็ค · มิวเอ็กซ์ · ไทรทัน · เรนเจอร์ · มาสด้า 2 · ยาริสครอส ·
      โคโรล่าครอส ฯลฯ) + **เทียบชื่อยาวก่อน** (`_TH_MODEL_KEYS` — "ยาริสครอส" ต้องชนะ "ยาริส") · ใช้ร่วมกับ
      `customer_needs --group` ด้วย · ชื่อไทย → อังกฤษ → `match_model` กับตัวเลือกในชีต ("ดีแม็ก" → d-max → "D Max")
    · ค่าที่ระบบเคยใส่ไว้แต่ **ไม่อยู่ในตัวเลือกชีต** (เช่น "LINE OA" ก่อนมี dropdown) → แก้ให้ตรงชีตเอง (`stale_sys`)
      · ค่าที่คน/ใบจ่ายลีดใส่ **ไม่แตะ** · ใบจ่ายลีดแปลงค่าเป็นชื่อตามตัวเลือกก่อนเติม (`dd_pick`)
    · **ที่ระบบไม่เดา (คนต้องเลือก)**: FOCUS · ทีมไลฟ์ · แจ้งหลักฐานการโทร · รุ่นที่กำกวม
      _(ประเภทลูกค้า + type เติมได้แล้ว 7 ต.ค.69 — ดูหัวข้อถัดไป)_
  - **⚠️ ทดสอบอ่านชีตจากเครื่อง dev**: `load_dotenv()` แบบไม่ใส่ path หา `.env` จาก **โฟลเดอร์ที่รัน** (โดยเฉพาะ
    `python -c`) → รันจากที่อื่นแล้ว **ไม่มี credential Google** ทั้งที่ไฟล์มี · สคริปต์ต้อง `load_dotenv(<path เต็ม>)`

- **★★ จับ keyword จากแชท → อาชีพ/รายได้/อายุงาน/ประวัติผ่อน/ประเภทลูกค้า/สถานะลูกค้า (7 ต.ค.69 · เจ้าของสั่ง
  *"จับ keyword แล้วลงตาม dropdown ได้ไหม … จับ keyword เช็คแล้วก็กรอกลงทุกช่องตามที่ lead ต้องการ"*)**
  [lead_keywords.py](checkout/lead_keywords.py) (ฟังก์ชันล้วน **ไม่ใช้ AI** · ผลเหมือนเดิมทุกครั้ง · ตรวจย้อนได้ว่าจับจากคำไหน)
  - **ช่องใหม่ `ChatLead.customer_status`** "สถานะลูกค้า" = คอลัมน์ Z ของชีต (dropdown 24 ค่า · checkout migration **0032**)
    · ฟอร์มลีดเพิ่มช่องนี้ข้างประเภทลูกค้า · ใส่ `DD_COLS` + `DD_FALLBACK` แล้ว
    · `dropdowns()` เติมชุดที่จำไว้ **เฉพาะช่องที่ชุดในชีตยังไม่มี** (KV ที่อ่านก่อนเพิ่มช่องใหม่ ไม่มีช่องนี้จนกว่ารอบอ่าน ≤1 ชม.)
      ช่องที่อ่านจากชีตได้แล้ว **ชีตชนะเสมอ**
  - **ทำงาน 2 จังหวะ**: ข้อความลูกค้าเข้า (`capture_profile` ← `note_customer_message`/`note_fb_batch`) และตอนเปิดแชท
    (`autofill` → `apply_keywords`) · อ่านทั้ง **แชทลูกค้า** และ **โน้ตที่คนพิมพ์ในฟอร์ม** (มากรอกชีตกันเถอะ/PROFILE/เพิ่มเติม · โน้ตชนะแชท)
    · ไม่เจอ keyword = **ไม่สร้างแถว ChatLead เปล่า** (กติกาเดียวกับ `capture_contact`)
  - **กติกาเขียน (เหมือน autofill เดิม)**: เติมเฉพาะช่องว่างที่ยังไม่เคยเติม · **ช่องที่คนแก้แล้ว (`auto=คน`) ไม่แตะเด็ดขาด**
    · **สถานะลูกค้าเปลี่ยนตามข้อความล่าสุดได้** (ลูกค้าเปลี่ยนใจ) เฉพาะที่ระบบเติมเอง ช่องอื่นเติมครั้งเดียว
    · ช่อง dropdown = **ตัวเลือกของชีตเท่านั้น** (`lead_keywords.pick` + `TYPE_SPELL`/`STATUS_SPELL` — ชีตสะกด "ฟลีแลนด์"
      "เกษตกร" "รัฐวิสาหากิจ") · ชีตไม่มีตัวเลือกนั้น = ไม่เติม (อาชีพยังเติม)
    · `auto["_kw"]` = จับจากคำไหน → `lead_json.autoWhy` → ป้าย "จากแชท" บนฟอร์ม **เอาเมาส์ชี้เห็นคำที่จับได้** (คนตรวจได้ทันที)
  - **type ว่าง + มีเลขลีด → เติมตามตัวหน้า** (NLD=Moderate · WLD=Hot · HLD=Very Hot · BLD · TLD · R/A นำหน้าใช้ตัวหน้าเดียวกัน
    · ตัด "/1" ท้ายเลขออกก่อน) — ปุ่มจ่ายเบอร์เติมอยู่แล้ว ตรงนี้สำหรับเลขที่มาจากใบในกลุ่ม/คนพิมพ์
  - **⚠️★ ภาษาไทยไม่เว้นวรรค = คำสั้นจับกลางคำอื่น** (เจอจริงตอนวัดกับโน้ต ต.ค. ทั้งแท็บ — มีเทสต์กันทุกข้อ):
    "อบจ" ใน "รอตอบ**จ้า**" (40 แถวกลายเป็นข้าราชการ) · "711" ในเลขลีด "7114" · "ทำนา" ใน "ทำนายหน้า" · "ชอบตรง" มี "อบต"
    → คำสั้นต้องมีขอบ (`(?<![ก-๙])` / ต้องมี "พนักงาน|ทำงาน" นำหน้า) · **เพิ่มคำใหม่ = ทดสอบกับข้อความจริงก่อนเสมอ**
  - **อาชีพ = คำที่ลูกค้าพูดถึงก่อน** (ไม่ใช่หมวดที่อยู่บนในลิสต์) — "ทำปั๊มน้ำมัน … มีบัตรเกษตรกร" = ปั๊ม
    · ข้ามอาชีพของ **แฟน/พ่อแม่/คนค้ำ** (15 ตัวก่อนหน้า) และ **อดีต** ("ตอนเป็นทหาร") · "กู้แอป Grab" ไม่ใช่ไรเดอร์
    · แบบฟอร์มแอดมิน ("อาชีพ : … รายได้ : …") อ่านก่อน · "ทำอาชีพ X"/"พนักงาน X" ที่ไม่อยู่ในลิสต์ = ตัดที่คำหยุด
  - **รายได้ต้องมีคำบอก** (รายได้/เงินเดือน/ฐาน/สลิป/รับรวม) นำหน้าตัวเลข · ค่างวด/ดาวน์/งบ/ยอดหนี้ ไม่นับ · รายวัน/รายสัปดาห์ = ไม่เติม
    · มี "รวม/เบ็ดเสร็จ/จริงๆ" = ใช้ตัวนั้น · "รวมกับแฟน" ไม่นับ · ตัวเลขติดหลังอาชีพ ("พนง.บัญชี 27,000") = รายได้
    · รองรับ 22,000 · 2หมื่น · หมื่น8 · 1แสน · 15k · 3-4 หมื่น · 35k-45k · 20,002 ถึง 24,000
  - **สถานะลูกค้า: ค่าที่ทำให้ "เลิกตาม" ในชีต (ยังไม่ออกเร็วๆนี้/ติดแบล็คลิส/ลูกค้าไม่สนใจแล้ว) ต้องชัด** —
    "สิ้นปี" ไม่นับ (ต.ค. = อีก 2 เดือน ยังต้องตาม) · "ยกเลิก" ต้องบอกว่ายกเลิกอะไร (เคยจับ "ยกเลิกกับร้านอื่น") ·
    ติดแบล็คลิส + ใช้ชื่อพ่อ = **หาคนออกให้** (ยังตามต่อ) · "มาดูรถแล้ว" ≠ รอมาดูรถ
  - **วัดกับโน้ตจริงแท็บ ต.ค.69 (~1,150 แถว) เทียบค่าในชีต**: รายได้ตรง 96% · อายุงาน 96% · อาชีพ 85% · ประเภทลูกค้า 83%
    (ที่ไม่ตรงส่วนใหญ่แค่คำต่างกัน เช่น "ทำงานโรงงาน"/"พนักงานโรงงาน") · ประวัติผ่อนสรุปเป็นคำสั้น
    ("ผ่อนมอเตอร์ไซค์ · ผ่อนตรง") ไม่ใช่ข้อความเต็มแบบที่คนพิมพ์ · **สถานะในชีตตรงแค่ 15%** — ไม่ใช่จับผิด
    แต่คนละเรื่อง: ในชีตเป็นสถานะการตามเคสจากการโทร (คืนเคส/ติดตาม/รอตอบ) ส่วนนี้จับจากคำที่ลูกค้าพูด
  - **ยังไม่ลงชีตลีด** (ตามที่สั่งไว้ 4 ต.ค.) — เก็บใน Postgres อย่างเดียว
  - **★ "รถลูกค้าถาม" = รุ่น+สเปกเท่านั้น (`car_phrase` · เจ้าของส่งรูป "CX3 ปี2022 ขายอยู่เรทประมาณเท่าไหร่ครับ" — "ตัดคำเกินออก")**
    · เดิมเอาทั้งประโยคลูกค้า (วัดบน prod 89 ค่า: ปนรายได้/อายุงาน/คำถาม/คำลงท้ายเกือบทุกค่า) · แอดมินเขียนช่องนี้สั้น
      (ชีต ต.ค. ≤10 ตัว 70% · ≤20 ตัว 95%) → เก็บ ยี่ห้อ/รุ่น + ปี สี ประตู เกียร์ เครื่อง รุ่นย่อยอังกฤษ · ตัดที่เหลือ
    · ตัดทีละคำ (เว้นวรรค) + เล็มหัว (`_CP_PRE` สนใจ/มี/อยากได้…) ท้าย (`_CP_SUF` ครับ/ไหม/เท่าไหร่…) + ตัดที่คำหยุดกลางคำ
      (`_CP_STOP` ราคา/ผ่อน/เงินเดือน/เทิร์น… — ภาษาไทยไม่เว้นวรรค "แคมรี่ปี12คันสุดท้าย") · เลข 5 หลัก = เงิน ไม่ใช่สเปก
    · **งบ/ผ่อน เก็บเฉพาะตอนไม่มีชื่อรุ่น** (บอกแค่ยี่ห้อ "งบ 3 แสน ฮอนด้า") · ตัดซ้ำได้ค่าเดิม (idempotent)
    · **ค่าเก่าที่ระบบเติมทั้งประโยค ตัดให้เองตอนเปิดแชท** (`auto.car_text == แชท`) · ที่คน/ใบจ่ายลีดใส่ไม่แตะ
  - **★ CAR/สูตร = "ไม่ระบุรุ่นรถ" เมื่อบอกแค่ยี่ห้อ/รุ่นกว้าง** (เจ้าของ: "รถตามสูตรไม่ผูกแชทให้" · `UNSPEC_MODEL`)
    · **ไม่เดารุ่น**: วัด ส.ค.–ต.ค. ลูกค้าพิมพ์ "city" แอดมินเลือก 5 ประตู 37% · 4 ประตู 20% · ไม่ระบุรุ่นรถ 12% ·
      "civic" → FC 49% · อีซูซุ → D Max 6/14 — ไม่มีรุ่นไหนชัดพอ · **ลูกค้าบอกรุ่นชัดทีหลัง = เปลี่ยนเป็นรุ่นจริงเอง**
      (เฉพาะที่ระบบใส่ไว้ · คนเลือกเองไม่แตะ)
  - **เทสต์**: `python scripts/test_lead_keywords.py` (54 ข้อ · ข้อ "บั๊ก:" = จับผิดจริงรอบแรก) + `test_connect.py` [31] (13 ข้อ ·
    ข้อความเข้าเติมทันที · คนแก้แล้วไม่ทับ · สถานะเปลี่ยนตามข้อความล่าสุด · ชีตไม่มีตัวเลือก = ไม่เติม · type จากเลขลีด)
    + [32] (8 ข้อ · ตัดคำ 14 ข้อความจริงจาก prod · ไม่ระบุรุ่นรถ → รุ่นจริง · ค่าเก่าถูกตัด · ที่คนพิมพ์ไม่ตัด)
    · ตรวจฟอร์มใน Chromium จริงแล้ว (ช่องสถานะเป็น dropdown 24 ตัวเลือก · ป้ายบอกคำที่จับได้ · ไม่มี JS error)

- **★ ปุ่ม "จ่ายเบอร์" (เริ่มเป็นทดลอง 4 ต.ค.69 · ★★ 6 ต.ค.69 ส่งเข้ากลุ่มจ่ายเบอร์จริงแล้ว — ดูหัวข้อถัดไป) (เจ้าของสั่ง "ระบบส่วนนี้ยังเป็น Demo อยู่ ยังไม่อยากให้ลง Sheet จริง
  เอาแค่ลงระบบเก็บใน Postgres ของเราก่อน" · checkout migration 0028)** — แอดมินกดในแผงขวาของแชท: เลือกตัวหน้า +
  เซลล์ → ระบบ **ออกเลขลีด + โอนลูกค้าให้เซลล์ + จดว่าใครจ่ายเมื่อไหร่** · API `POST /connect/api/assign_lead
  {id, emp, base, admin, reject, code?}` · **แอดมินเท่านั้น** (เซลล์ = 403 · ไม่ได้ `codeHelp` = ไม่เห็นกล่องด้วย)
  - **★ ไม่ลงชีตลีด** · ~~ไม่โพสต์เข้ากลุ่มจ่ายเบอร์~~ (**6 ต.ค.69 โพสต์จริงแล้ว** — เหลือแบบเดิมเฉพาะตอนปิดสวิตช์ `slip_post`
    / ลูกค้าจำลอง / บัญชีทดสอบ → `code_demo=True` · มีเทสต์ยืนยันว่าโหมดนี้ไม่มีคำขอออกนอกระบบ)
  - **รูปแบบเลขจริง (วัดจากชีตลีด 18,041 แถวที่มี Code + ใบจ่ายลีด)**: **`<ตัวหน้า><เดือน>-<เลขรัน>`** เช่น `NLD10-8409`
    · **NLD**=Moderate (7,792 แถว) · **WLD**=Hot · **HLD**=Very Hot · **BLD**=BLD (2,181) · **TLD**=TikTok (6,292) ·
    **TALD**=TikTokAds · นำหน้า **A** = ลีดของแอดมินเอง (ANLD/AWLD/AHLD/ABLD/ATLD) · นำหน้า **R** = เคสรีเจ็ค
    (RNLD/RTLD · `RB` = Hot RB) · `LD`/`ALD` = แบบเก่าก่อนแยก type (ยังอ่านได้ แต่ไม่ออกเลขใหม่แบบนี้)
    · ตัวหน้าทั้งหมดอยู่ที่ `CODE_BASES` ([connect.py](checkout/connect.py)) — **เพิ่มตัวหน้าใหม่แก้ที่เดียว** (+ `_CODE_RE`)
  - **★ เลขรันใช้ร่วมกันทุกตัวหน้า** (8395 TLD → 8396 NLD → 8397 NLD …) → `last_running()` = **มากสุดของใบจ่ายลีด
    20 ใบล่าสุด** ในกลุ่มจ่ายเบอร์ (ไม่นับ R — เป็นเคสเก่าที่โพสต์ซ้ำ) **+ เลขที่โหมดทดลองออกไปแล้ว** · ใช้ "มากสุด"
    ไม่ใช่ "ใบล่าสุด" เพราะแอดมินโพสต์สลับลำดับกันได้ · เดือน = เดือนที่จ่าย · เลขบนกล่องเป็นตัวอย่าง
    **เลขจริงคำนวณใหม่ตอนกด** (กันซ้ำ)
  - **ตัวหน้าแนะนำ** (`suggest_prefix`): ตาม type ที่กรอก → ไม่มีก็ตามช่องทาง (TikTokAds→TALD · TikTok→TLD) →
    ไม่งั้น NLD · ~~type RJ/Hot RJ/Hot RB → ติ๊ก R ให้~~ (**17 ต.ค.69 เลิกแล้ว** — R ใช้ตอนส่งต่อไม้ 2 เท่านั้น) · เจ้าของเป็นเทเลเซลล์ → ติ๊ก A ให้ · **แอดมินเปลี่ยนเองได้ทุกอย่าง**
    · **★ 17 ต.ค.69 ตัวหน้าอัตโนมัติจากข้อมูลในแชท** (HLD/WLD/LD/BLD/NLD) — ดูหัวข้อ "ตัวหน้าเลขลีดอัตโนมัติ"
    · ที่เลือกค้างไว้ **ไม่หายตอนแผงรีเฟรช 6 วิ** (`S.assignDraft` — ตรวจในเบราว์เซอร์จริงแล้ว)
  - **⚠️ ทำไมต้องติดป้าย "ทดลอง"**: แอดมินยังออกเลขจริงในชีตอยู่พร้อมกัน → เลขถัดไปของเรา **อาจชนกับเลขที่แอดมิน
    เพิ่งออกในชีต** · ใบย่อของเคสทดลองขึ้นบรรทัดแรก "⚠️ ทดลอง — เลขนี้ยังไม่ได้จองในชีตจริง" (กันก๊อปไปวางในกลุ่มจริง)
    · หน้าเว็บขึ้น "จ่ายเบอร์ X แล้ว · เวลา โดย … · ทดลอง (ยังไม่ลงชีต)" แทนกล่อง
  - **กันพลาด**: **มีเลขอยู่แล้ว (จากใบจ่ายลีดจริง/คนกรอก/จ่ายไปแล้ว) = ไม่ออกเลขทับ** (หน้าเว็บค้างของเก่าก็โดนกัน
    ที่เซิร์ฟเวอร์) · เลขซ้ำกับลูกค้าคนอื่น = ปฏิเสธ · เลขที่ส่งมาเองผิดรูปแบบ = ปฏิเสธ · **โอนไม่สำเร็จ = ย้อนทั้งธุรกรรม**
    (เลขไม่ค้างอยู่กับลูกค้าที่ไม่มีเซลล์) · type ว่าง = เติมตามตัวหน้าของ **เลขที่ได้จริง** (RAHLD → Very Hot)
  - ~~ยังไม่มีล็อกกันกดพร้อมกัน~~ → **6 ต.ค.69 มีแล้ว** (`connect.code_lock()` — Postgres advisory lock) ดูหัวข้อถัดไป
  - **★ บั๊กที่แก้ไปพร้อมกัน — ใบจ่ายลีดเดือน ต.ค.–ธ.ค. อ่านไม่ออกเลยสักใบ**: `leadgroup._LEAD_NO` รับเดือนได้
    **หลักเดียว** (`\d?`) → ตั้งแต่ 1 ต.ค.69 `NLD10-8409` คืน `None` เงียบๆ · กระทบ 2 ที่: Connect เติมข้อมูลจาก
    ใบจ่ายลีดไม่ได้ + **`customer_needs --group` นับใบเดือนนี้เป็น "ไม่เข้าเงื่อนไข" ทั้งหมด** · แก้เป็น `\d{0,2}`
    · **กฎ: regex ที่มี "เดือน" ต้องรับ 2 หลักเสมอ** — ทดสอบแค่เดือน 1–9 จะผ่านหมด แล้วไปพังเงียบตอน ต.ค.

- **★★ ส่งใบจ่ายลีดเข้ากลุ่มจ่ายเบอร์จริง + แท็กเซลล์ (6 ต.ค.69 · เจ้าของสั่ง *"กลุ่มจ่ายเบอร์อยากให้มันต่อจริงๆ ส่งจริงๆ ได้
  ทั้งสิทธิ์ในระบบเราและแท็กในไลน์กลุ่ม · ถ้าเป็น LINE จะส่งให้ทั้ง LINE และแท็กในกลุ่ม · ช่องทางอื่นแท็กในกลุ่มก็พอ ·
  ให้สิทธิ์ในระบบเพื่อเก็บข้อมูลเท่านั้น ถ้าไม่ใช่ LINE ของฝั่ง Connect ลูกค้า"*)** — [slippost.py](checkout/slippost.py) ·
  checkout migration **0031** (`ChatLead.post_info` / `ExtLead.post_info`)

  | ลูกค้า | สิทธิ์ในระบบเรา | กลุ่มจ่ายเบอร์ |
  |---|---|---|
  | แชท LINE OA ใน Connect | โอนแชทให้เซลล์ — **ตอบลูกค้าผ่าน Connect ได้** | ใบ + แท็ก @เซลล์ |
  | แชท Facebook ใน Connect | โอนให้เซลล์ **เพื่อเก็บข้อมูลเท่านั้น** (ดูแชท/กรอกข้อมูลลีด · ตอบ/ปิดรอบไม่ได้) | ใบ + แท็ก |
  | ลีดภายนอกในห้องพัก (TikTok ฯลฯ) | จดว่าจ่ายให้ใคร (`ExtLead.seller`) | ใบ + แท็ก |

  - **ห้องปลายทาง** (วัดจากใบจริง 30 วัน): เลขปกติ → **"ห้องจ่ายเบอร์ บ้านเก่า"** · เลขขึ้นต้น R → **"ห้องจ่ายเบอร์ REJECT"**
    (ใบ R… อยู่ห้อง REJECT 967/968 ใบ) · หาเองจากชื่อกลุ่ม (`lead_rooms()` — **เฉพาะกลุ่มที่บอทตัวส่งอยู่** · ซ่อน id ของบอทเดิม)
    · ตั้งเองได้ที่ Connect → ตั้งค่า → การ์ด "ส่งใบจ่ายลีดเข้ากลุ่มจ่ายเบอร์" (`slip_group`/`slip_group_reject` · บันทึกแล้วถาม LINE
    ว่าบอทอยู่ในกลุ่มจริง `push_group_error`) · วัดจริง 6 ต.ค.69: บอทตัวส่งอยู่ทั้ง 2 ห้องแล้ว (`channels: ["push"]`)
  - **สวิตช์ `connect_config.slip_post` — เปิดโดยปริยาย** (เจ้าของสั่งส่งจริง) · ปิด = โหมดทดลองเดิม ·
    **ลูกค้าจำลอง (`TEST-`) / บัญชีทดสอบ ไม่ส่งเข้ากลุ่มจริงเสมอ** (ออกเป็นเลขทดลอง)
  - **แท็ก** = ไอดีของเซลล์ **ฝั่งบอทตัวส่ง** (`checkin_report._pick_id` + `push_channel`) + **ถาม LINE ก่อนว่าอยู่ในกลุ่มจริง**
    (`outsiders` · จำคำตอบใน KV `checkin_group_member`) · แท็กไม่ได้ = พิมพ์ "@ชื่อเล่น" ท้ายใบแทน ·
    LINE ปฏิเสธการแท็ก = ส่งซ้ำแบบพิมพ์ชื่อ (`checkin_report._send_msgs` ตัวเดียวกับตารางเช็คชื่อ) — **ใบต้องถึงกลุ่มก่อนเสมอ**
    · textV2 แทน `{}` ในข้อความลูกค้าเป็น `()` (ไม่งั้นถูกตีเป็นตัวแทนที่)
  - **★ ใบตาม pattern ที่เจ้าของกำหนดจากรูป (6 ต.ค.69 · "จัดเลยให้มันอยู่ใน pattern นี้")** — `slippost.body()` ตัวเดียว
    ใช้ทั้ง **ส่งเข้ากลุ่ม** และ **ปุ่มคัดลอก** ทั้งลูกค้าแชท (`connect.slip_fields`) และลีดภายนอก (`leadpark.slip_fields`):
    `Ac Lead No. X` / `Ads : -` / `ชื่อ Account: …` / `ชื่อลูกค้า : -` / `ID LINE : …` / `ชื่อไลน์ : -` / `เบอร์โทร : -` /
    `ช่องทาง : -` / `รถ : -` / `ไลฟ์ : -` / `เพิ่มเติม : -` แล้วแท็ก @เซลล์บรรทัดสุดท้าย · **ช่องว่าง = "-"** ·
    **ไม่มีบรรทัดอื่นแทรก** (รอบแรกมี "จ่ายโดย" / ลิงก์ Connect / "ติดต่อได้เลยนะครับ" — ตัดออกตามที่สั่ง) · ห้ามแยกเขียนอีกชุด
    · `leadgroup.parse_fields` อ่าน "-" เป็นช่องว่าง (ไม่งั้นอ่านใบที่ระบบส่งกลับมาแล้วได้ ช่องทาง "-" / รถ "-")
  - **★ ช่องทาง/ไลฟ์ในใบ = คำตาม dropdown ของชีตจ่ายเบอร์** — ไลฟ์ = ช่อง **"ทีมไลฟ์"** (คอลัมน์ F เดียวกันในชีต ·
    เลิกมีช่องพิมพ์ "ไลฟ์" แยกในหน้า Connect) · `dd_pick("channel")` เทียบด้วย `_ch_key` (ตัดช่องว่าง/"/"/คำว่า "ช่อง" ·
    ไม่สนตัวพิมพ์) **ต้องตรงตัวเลือกเดียว** ไม่งั้นคงคำเดิม (ไม่เดา) · อ่านใบจริงแล้วเติม "ทีมไลฟ์" จาก "ไลฟ์" ให้ด้วย
  - **★ ใบที่ส่งสำเร็จ เก็บลง `GroupChat` ด้วย** (direction=out · message id จากคำตอบของ LINE) — **LINE ไม่ส่งข้อความของบอทเอง
    กลับมาทาง webhook** · ถ้าไม่เก็บ เลขรัน/ห้องพัก Lead/`customer_needs --group` จะไม่เห็นใบที่ระบบโพสต์เอง
  - **★ ส่งไม่สำเร็จ ≠ ยกเลิกการจ่ายเบอร์** — เลข + เซลล์ในระบบยังอยู่ · `post_info` จดเหตุผลเป็นภาษาคน (`slippost.explain`) →
    ปุ่ม **"ส่งเข้ากลุ่มอีกครั้ง"** (`assign_lead {id, resend}` · `park_assign {mid, resend}`) · ส่งสำเร็จแล้ว = ไม่ส่งซ้ำ ·
    กดซ้ำระหว่างกำลังส่ง (60 วิ · `post_info.sending`) = ปฏิเสธ · **ไม่ย้อนธุรกรรมหลังยิงเน็ต** (ใบอาจถึงกลุ่มไปแล้วจริง)
  - **★ ล็อกการออกเลข `connect.code_lock()`** — Postgres advisory lock ระดับธุรกรรม · เลขถัดไป → ตรวจซ้ำ → บันทึก ในล็อกเดียว ·
    **ห้ามยิงเน็ตในล็อก** (ส่งเข้ากลุ่มหลังออกจากล็อก) · `last_running()` นับเลขที่ระบบออกทั้งหมด (`assigned_at` ไม่ว่าง)
    ไม่ใช่แค่เลขทดลอง — ใบที่ส่งไม่สำเร็จจึงยังกันเลขซ้ำได้
  - **หน้าเว็บ**: กล่องจ่ายเบอร์บอก **ก่อนกด** ว่าจะส่งเข้าห้องไหน (`codeHelp.post`) · **ถามยืนยัน (confirm) ทุกครั้งก่อนส่งจริง** ·
    หลังจ่ายโชว์ "ส่งเข้า … แล้ว · แท็ก @…" หรือเหตุผล + ปุ่มส่งอีกครั้ง · รายการ "จ่ายแล้ว" บอกสถานะ (ป้ายแดงเมื่อส่งไม่สำเร็จ)
  - **★ ลูกค้า Facebook = เซลล์ได้สิทธิ์เก็บข้อมูลเท่านั้น (ทั้งที่จ่ายเบอร์ให้ และที่รับเองจากคิว)** — `api_reply`/`api_dismiss`
    ตอบ 403 (`slippost.FB_DATA_ONLY`) · `api_chat` replyOn=False + เหตุผล · ไม่นับเป็น "รอตอบ/เลยเวลา" ของเซลล์ (`counts`)
    · **แอดมินยังตอบได้ตามโหมด `fb_reply`** · ⚠️ **เปลี่ยนจากแผน 4 ต.ค.69** ที่ให้เซลล์ตอบแชท FB จาก Connect (`fb_reply=on`)
  - **ยังไม่ลงชีตลีด** (เจ้าของสั่งไว้ 4 ต.ค.69) → แอดมินต้องเพิ่มแถวในชีตเองเหมือนเดิม · **เลขอาจชนกับเลขที่แอดมินออกเองในชีต**
    ถ้าทำพร้อมกัน (ระบบเห็นใบของแอดมินในกลุ่มภายในไม่กี่วินาที แต่ไม่เห็นเลขที่เพิ่งพิมพ์ในชีต)
  - **📋 dropdown ของ "ชีทจ่ายเบอร์ ปี69" (= ชีตลีด `1s9FFPRV…` · วัดจริง 6 ต.ค.69 แท็บ "ตุลาคม 69" · 12 คอลัมน์)**:
    E เซลล์ (21) · F ทีมไลฟ์ (Live Infu/Productions/Sale/boss) · G Admin (กวาง/หมิว/เนเน่/ADMIN/เฟิร์น/ฟิล์ม) ·
    **H ช่องทาง (34)** · I สาขา (ชลบุรี/เทพารักษ์) · J type (10) · M CAR/สูตร (61) · N แจ้งหลักฐานการโทร (3) · O FOCUS (2) ·
    Y ประเภทลูกค้า (12) · Z สถานะลูกค้า (24) · AB Status แอดมิน (6) — **ทุกตัวเป็นรายการพิมพ์ในกฎ (ONE_OF_LIST) ไม่อ้างช่วงเซลล์**
    · ช่อง **ADS ไม่มี dropdown** (พิมพ์ชื่อโฆษณาเอง เช่น "ออแกนิก") · Connect อ่านชุดนี้ทุกชั่วโมง (`fetch_lead_dropdowns`)
    แต่ **ยังไม่ใช้ E/Z/AB** (เซลล์มาจากทะเบียนพนักงาน · สถานะลูกค้า/แอดมินไม่มีช่องในฟอร์ม Connect)
    · **⚠️ วัดใบจ่ายลีดในกลุ่ม 30 วัน: คนพิมพ์ "ช่องทาง" ไม่ตรงคำในชีตเกือบทั้งหมด** ("Live tiktok ช่องขายบอส" 181 ·
    "TikTok แซน" 80 · "Line@" 155 ฯลฯ) และ "ไลฟ์" ตัวพิมพ์/ช่องว่างปนกัน ("live sale" / "Live  sale") → ใบที่ระบบส่งใช้คำของชีตเสมอ
  - **⚠️ R ของระบบ ≠ R ในห้อง REJECT**: ห้อง REJECT ใช้ **เลขเดิม + "/1"** (ส่งต่อเคสเก่า เช่น `RNLD9-8129/1`) · ปุ่ม R ของระบบ
    ออก **เลขรันใหม่** ขึ้นต้น R → ยังไม่ตรงกับวิธีที่ทีมใช้ (ถ้าจะใช้ R จริงต้องทำ "ส่งต่อเคสเก่า" แยก)
  - หน้าสถานะระบบเฝ้าให้เอง (ชื่องานใน `dash_event_log` = **"ใบจ่ายลีด (Connect)"**)

- **★ แท็บ "จ่ายเบอร์" ของแอดมิน (4 ต.ค.69 · เจ้าของถาม *"ขาดหน้าแอดมินจ่ายเบอร์มั้ย"*)** — เดิมกล่องจ่ายเบอร์อยู่ใน
  แผงขวาของแชท **ทีละคนเท่านั้น** ไม่มีที่ไหนบอกว่าใครยังรอจ่ายเบอร์ (+ แผงขวาซ่อนได้ = มองไม่เห็นกล่องเลย)
  - แท็บ **`tocode`** ต่อจาก "รอรับ" (แอดมินเท่านั้น · เซลล์ขอ view นี้ = ได้แท็บของตัวเองแทน) · ตัวเลข `counts.tocode`
  - **`connect.to_code(qs)`** = ยังไม่มีเลขลีด **และ "คุยในระบบแล้ว"** (รอคำตอบ · มีเจ้าของ · หรือมีประวัติใน
    `ChatOwnerLog`) → **ลูกค้าเก่าก่อนเปิด Connect ที่ไม่ได้ทักกลับมาไม่นับ** (วัดจริงตอนเปิด: 381/391 คนเป็นแบบนี้
    ถ้านับด้วยแท็บนี้ใช้งานไม่ได้) · ทักกลับมาใหม่ = เข้าแท็บเอง · เรียง: รอคำตอบก่อน (ตามเส้นตาย) แล้วข้อความล่าสุด
  - **ปุ่ม "ไม่ต้องจ่ายเบอร์ (ไม่ใช่ลีดขาย)"** ในกล่องจ่ายเบอร์ — ถามศูนย์บริการ / อยากขายรถให้เรา / ลูกค้าเก่าทักขอบคุณ
    → ออกจากแท็บ · เก็บที่ `ChatLead.auto["_nocode"]` = `{by, at}` (**ไม่ต้อง migrate**) · กด "เอากลับมาจ่ายเบอร์" ได้
    · API เดิม `POST /connect/api/assign_lead {id, skip: true|false}` · จ่ายเบอร์ทีหลัง = ล้างป้ายให้เอง
  - **ปุ่ม "จ่ายเบอร์" บนหัวแชท** (แอดมิน · ลูกค้ายังไม่มีเลข) → `goAssign()` เปิดคอลัมน์ข้อมูลลูกค้าที่ซ่อนไว้ /
    กางแบบพับบนจอแคบ แล้วเลื่อนไปกล่องจ่ายเบอร์ + โฟกัสช่องเลือกเซลล์
  - รายชื่อลูกค้าโชว์ **ป้ายเลขลีด** (`row_json.code`) ทุกแท็บ — เห็นว่าใครได้เลขแล้วโดยไม่ต้องเปิดแชท
  - **⚠️ บั๊กเก่าที่แก้ไปพร้อมกัน**: (1) หัวแชทวาดใหม่ทุก 6 วิ **ล้างแผง "ข้อมูลลูกค้า" แบบพับ (จอ ≤1180px) ให้ว่าง**
    (`paintProfile` ไม่วาดซ้ำเมื่อข้อมูลเดิม) → `paintHeader` ย้ายแผงเดิมกลับเข้าไปทั้งก้อน + **ไม่วาดหัวแชทระหว่างพิมพ์/เลือก
    ในหัวแชท** (ช่องโอน/ฟอร์มพับ) · (2) กดกลับแล้วเปิดลูกค้าคนเดิม = แผงขวาว่าง → `paintChat` บังคับ `paintProfile(true)`
    · (3) ชื่อคนใช้ (`#cn-me`) ดันหน้าล้นจอแนวนอน 47px บนมือถือตอนฝังในแดชบอร์ด → หดเป็น "…"

- **★ ห้องพัก Lead — กลุ่ม LINE "ADMIN เก็บ Lead" (4 ต.ค.69 · เจ้าของสั่ง "ไปดูห้องนั้นแล้วสร้าง pattern ออกมา")**
  [leadpark.py](checkout/leadpark.py) · บอทเข้าห้องนี้ 4 ต.ค.69 13:23 (`channels: ["push"]`)
  - **แพทเทิร์น = "ใบจ่ายลีดฉบับร่าง"**: เทมเพลตเดียวกับใบจริงทุกช่อง ต่างแค่ **เลขลีดมีแค่ตัวหน้า+เดือน (`TLD10-`)
    ไม่มีเลขรัน** + **ยังไม่แท็ก @เซลล์** · เบอร์โทรบางทีฝังอยู่ใน ID LINE (`port0955759309`)
  - **วงจรจริง (วัดจากใบร่าง 4 ใบที่เคยหลุดไปห้องจ่ายเบอร์ ก.ย.69)**: พักใบร่าง → **ใบจริง (เลข + @เซลล์) ในห้องจ่ายเบอร์
    ภายใน 17 วิ–15 นาที** (ช่องทาง/บัญชี/เบอร์เหมือนเดิมเป๊ะ) → บางรายถูกส่งต่อในห้อง REJECT เป็น `R<เลข>/1`
  - `parse_draft()` แกะใบร่าง (ใบที่มีเลขแล้ว = None) · `board()` จับคู่ใบร่างกับใบจริงที่ตามมา:
    **เบอร์โทร / ID LINE** (คีย์แข็ง) · ไม่มีทั้งคู่ = **ชื่อ Account + ช่องทาง** (คีย์อ่อน · ชื่อ TikTok สั้นๆ ซ้ำกันได้
    จึงใช้เฉพาะตอนไม่มีคีย์แข็งทั้ง 2 ฝั่ง) · **ใบ R… ไม่นับว่าได้เลข** (นั่นคือการส่งต่อเคสรีเจ็ค) · โพสต์ใบร่างซ้ำ = ลีดเดิม
    (นับ `reposts`) · ย้อนดู 7 วัน · จำผล 30 วิต่อ process
  - **หน้าเว็บ**: ขึ้น **บนสุดของแท็บ "จ่ายเบอร์"** ใน Connect (พักนานสุดก่อน · เกิน 30 นาที = แดง · กดกางดูทุกช่อง) +
    ตัวเลขแท็บรวม `counts.parked` · **หายจากรายการเองเมื่อมีใบจริงในห้องจ่ายเบอร์** · แอดมินเท่านั้น
  - **★ จ่ายเบอร์ลีดภายนอกจากหน้า Connect ได้แล้ว (4 ต.ค.69 · เจ้าของถาม *"แล้วจะจ่ายให้เซลล์ยังไง … รวม lead ไม่ว่าจะเป็น
    tt หรือ fb"*)** — กางลีด → เลือกตัวหน้า (ตั้งตามใบร่าง) + เซลล์ + A/R → "จ่ายเบอร์" → ย้ายไป **"จ่ายแล้ววันนี้"** พร้อมปุ่ม
    **คัดลอกใบจ่ายลีด** (เลข + @เซลล์ · อ่านกลับด้วย `parse_leadsheet` ได้) · "ไม่ต้องจ่ายเบอร์ (ลีดซ้ำ/ไม่ใช่ลีดขาย)" → "ซ่อนไว้" (เอากลับได้)
    · ป้ายช่องทาง **TikTok / Facebook / LINE / อื่นๆ** (`source_of(channel)`) · API `POST /connect/api/park_assign
    {mid, emp, base, admin, reject, code?}` / `{mid, skip}` · `mid` = message id ของใบร่างในกลุ่ม (ไม่ใช่ LINE user id)
    - **ตาราง `ExtLead`** (checkout migration **0029**) — **สร้างเฉพาะตอนกดจ่าย/ซ่อน** (ใบร่างที่ไม่มีใครแตะอ่านสดจากแชทกลุ่ม) ·
      เก็บสำเนาข้อมูลลีด (แชทกลุ่มหมดอายุ 90 วัน แต่ต้องประกอบใบใหม่ได้) · **ลบเองเมื่อพักเกิน 90 วัน** (`cleanup()` ใน `connect.tick`)
    - **★ เลขรันชุดเดียวกับลูกค้า LINE OA** — `connect.last_running()` นับเลขทดลองของทั้ง `ChatLead` และ `ExtLead` ·
      `connect.code_taken()` กันเลขซ้ำข้าม 2 ตาราง · (แก้ไปด้วย: เดิมตัดเลขทดลอง 500 แถว **โดยไม่เรียง** = แถวสุ่ม)
    - **กันพลาด**: ได้เลขในห้องจ่ายเบอร์แล้ว (แอดมินโพสต์เอง) = ไม่ออกเลขซ้อน · จ่ายแล้วจ่ายซ้ำ/ซ่อนไม่ได้ · เลขซ้ำ/ผิดรูปแบบ = ปฏิเสธ
    - ~~โหมดทดลอง~~ → **6 ต.ค.69 ส่งเข้ากลุ่มจ่ายเบอร์จริง + แท็กเซลล์แล้ว** (ดูหัวข้อ "ส่งใบจ่ายลีดเข้ากลุ่มจ่ายเบอร์จริง") ·
      ข้อความเดิม (โหมดทดลองที่เหลือตอนปิดสวิตช์): **ไม่ลงชีต ไม่โพสต์กลุ่ม** · ใบที่คัดลอกขึ้นบรรทัดแรก
      "⚠️ ทดลอง — เลขนี้ยังไม่ได้จองในชีตจริง" · ถ้าแอดมินโพสต์ใบจริงตามมา ระบบจับคู่แล้วโชว์เลขจริง (+ เลขทดลองถ้าไม่ตรง)
    - `board()`: ส่วนอ่านแชทกลุ่มจำผล 30 วิ แต่ **ExtLead อ่านสดทุกครั้ง** → กดจ่ายแล้วหายทันทีแม้คำขอถัดไปตก worker อื่น
    - หน้าเว็บ: รายชื่อวาดใหม่ทุก 8 วิ **แต่ไม่วาดตอนกำลังเลือกในกล่อง** · ที่เลือกค้างเก็บ `S.parkDraft` · ที่กางไว้ `S.parkOpen`
    - **ยังไม่ได้ทำ**: เซลล์ยังไม่เห็นลีดภายนอกที่ถูกจ่ายให้ในหน้าของตัวเอง (ตอนนี้ต้องดูจากใบที่แอดมินโพสต์ในกลุ่ม) ·
      แชท Facebook Messenger (`checkout_fbchat`) ยังไม่เข้า Connect (ซิงก์เที่ยงคืน ไม่ใช่ real-time)
  - หาห้องจากชื่อกลุ่ม (`PARK_HINTS` "เก็บ lead"/"พักลีด" …) ไม่ใช่ `LineGroup.kind` — "ทีมAdmin" ทั่วไปไม่โดนจับ
  - **`manage.py lead_park [--days N] [--out ไฟล์]`** — ข้อความในห้องถูกอ่านเป็นอะไร + **ยกตัวอย่างข้อความที่อ่านไม่ออก**
    (แอดมินเริ่มพิมพ์แบบใหม่เมื่อไหร่ เห็นตรงนี้ก่อน) + ลีดที่รอ/ได้เลขแล้ว · ใช้ทบทวนแพทเทิร์นเมื่อห้องมีข้อความมากขึ้น
  - **ทดสอบกับข้อความจริง 30 วัน (2,317 ใบ)**: ใบร่าง 6 · ใบจริง 2,311 · อ่านไม่ออก 0 · ใบร่างเก่า 4 ใบจับคู่ถูกเลขทุกใบ
  - **★ บั๊กที่แก้ไปพร้อมกัน — `leadgroup._LEAD_NO` อ่านเลขที่เว้นวรรคหลังขีดไม่ได้** (`RTLD9- 6456/1` ห้อง REJECT
    หลุด 2 ใบ) · เว้นได้แค่ `[ \t]` ในบรรทัดเดียวกัน **ห้ามใช้ `\s`** — ไม่งั้นใบร่าง `TLD10-` ที่บรรทัดถัดไปขึ้นต้นด้วย
    เบอร์โทรจะกลายเป็นเลขลีดปลอม · `connect.last_running()` ตัดช่องว่างก่อนเทียบด้วย · `parse_fields()` แยกออกมาใช้ร่วม
    + อ่าน `*เพิ่มเติม*` (ตัวหนาแบบ LINE) ได้

- **★★ ห้องพัก Lead = ศูนย์กระจายลีด "ทุกช่องทาง" (4 ต.ค.69 · เจ้าของ *"ควรทำที่พัก lead จากทุกช่องทาง เพื่อเป็นศูนย์กระจาย
  ให้แอดมินจ่าย"*)** — แท็บ `tocode` เปลี่ยนชื่อเป็น **"ห้องพัก Lead"** · `hubHtml()` รวม **รายการเดียว เรียงรอนานสุดก่อน**:
  แชท LINE / Facebook ที่ยังไม่มีเลข (เปิดแชท → จ่ายเบอร์ในแผงขวา) + ใบร่างจากกลุ่ม "ADMIN เก็บ Lead" (กดกาง → จ่ายได้เลย)
  · หัวห้องนับแยก **LINE / Facebook / TikTok / อื่นๆ** · ตัวกรองช่องทางในห้องนี้มี TikTok/อื่นๆ เพิ่ม (แท็บอื่นมีแค่ LINE/Facebook
  — ออกจากห้องแล้วล้างตัวกรอง TikTok ให้เอง ไม่งั้นรายการว่าง) · ป้ายช่องทาง `chTag()` ชุดเดียวทั้งหน้า
  - **★ เข้าห้องพักได้เฉพาะลูกค้าที่ให้เบอร์หรือ ID LINE แล้ว** (4 ต.ค.69 เจ้าของสั่ง *"ลูกค้าทุกคนไม่ได้เข้าห้องพักลีด
    ต้องเป็นลูกค้าที่ให้เบอร์หรือช่องทางติดต่อแล้วเท่านั้น"*) — `to_code()` ต้องมี `ChatLead.phone` หรือ `line_id`
    · ลูกค้าที่ยังแค่ถามรถอยู่คิว "รอรับ"/"ทั้งหมด" ตามเดิม · วัดตอนแก้: แชทในห้อง 26 → เหลือ ~6 (ที่เหลือแอดมินยังขอเบอร์อยู่)
    · ใบร่างในห้องพัก (กลุ่ม ADMIN เก็บ Lead) **ไม่ใช้กติกานี้** — แอดมินคัดมาแล้ว
    · **11 ต.ค.69: ลิงก์เพิ่มเพื่อน LINE + รูป QR ของ LINE ก็นับเป็น ID LINE แล้ว** + ป้าย "รอจ่ายเบอร์" ในรายชื่อแชท
      (ดูหัวข้อ "ลูกค้าให้ LINE เป็นรูป QR")
    · **⚠️★ 11 ต.ค.69 (ค่ำ) กติกานี้ถูก "ปิดไว้" แล้ว — แชทเข้าห้องพักเมื่อแอดมินกด "รับ lead" เท่านั้น** (สวิตช์ `room_chat_auto`
      · ดูหัวข้อ "ห้องพัก Lead รับแชทเมื่อแอดมินกดรับ lead") · เปิดสวิตช์ = กลับมาใช้กติกาข้อนี้
  - **`capture_contact(o)`** จับจากแชทลงข้อมูลลีด **ตอนข้อความเข้า** (LINE: `note_customer_message` · FB: `note_fb_batch`)
    + ตอนเปิดแชท → ลีดเข้าห้องทันทีไม่ต้องรอแอดมินเปิด · ไม่มีช่องทางติดต่อ = ไม่สร้างแถว ChatLead เปล่า ·
    ช่องที่คนแก้/ลบแล้ว (`auto[...] == "คน"`) ไม่เติมกลับ · `scan_contacts()` เก็บตกแชทเดิมครั้งเดียวต่อ process (ใน `sync_rows`)
    - **`contacts_in()`**: เบอร์ = `phones_in` เฉพาะข้อความลูกค้า (เบอร์ที่เราพิมพ์ไม่นับ) · **ID LINE ต้องมีป้าย**
      ("ไอดีไลน์ xxx" / "line id: xxx") **หรือเป็นคำเดียวที่ส่งมาหลังเราขอไอดี/ไลน์** — ไม่เดาจากคำอังกฤษลอยๆ ("civic"/"ok55"
      จะกลายเป็นไอดีปลอมแล้วลีดเข้าห้องทั้งที่ยังไม่ได้ช่องทางติดต่อ) · `(?<![A-Za-z])` กัน "online shop"
    - ⚠️ บั๊กที่เทสต์จับได้: เช็ค "สแกนแล้ว" ด้วย `dict.get(id) == key` ทำให้แถวที่ไม่มีเวลาข้อความ (`None`) ถูกข้ามตลอด
      → ต้องเช็ค `id in _CSCAN` ก่อน
  - **★ ห้องพัก Lead เป็นบอร์ดเต็มจอ (4 ต.ค.69 · เจ้าของ *"ห้องพักลีดเป็นหน้าจอใหญ่ๆ เต็มๆ เลยได้ไหม"*)** —
    เดิมอัดอยู่ในคอลัมน์รายชื่อซ้าย 350px · ตอนนี้แท็บ `tocode` ใส่ class **`hub`** ที่ `#cn-main` (`applyHub()`) →
    ไม่มีช่องแชทขวา · ลีดเป็น **การ์ดหลายคอลัมน์** (`repeat(auto-fill, minmax(min(360px,100%),1fr))` · จอ 1590 = 4 คอลัมน์ ·
    1180 = 3 · มือถือ = 1) · หัวห้องพัก/ส่วน "ได้เลขวันนี้" กินเต็มแถว
    · **กดการ์ดแชท = แชทเต็มจอแทนบอร์ด** (ใช้กลไก `body.pane` ตัวเดียวกับมือถือ) + ปุ่ม **"← ห้องพัก Lead"** กลับ ·
      กลับแล้ว `loadInbox` ทันที ลีดที่เพิ่งจ่ายเบอร์หายจากบอร์ดเลย
    · **เข้าแท็บนี้ = ปิดแชทที่ค้างไว้** (ไม่งั้นเปิดแท็บมาเจอแชทเต็มจอแทนบอร์ด) · สถิติ/ตั้งค่า และแท็บอื่น = 2 ช่องเหมือนเดิม
    · ⚠️ CSS ต้องมี `.cn-main.hub { grid-template-columns: minmax(0,1fr) }` — ซ่อนแค่ช่องแชท บอร์ดยังติดคอลัมน์ 350px (เทสต์จับได้)
  - **★★ "จ่ายให้ใคร" — ห้องพักแยก รอจ่ายเบอร์ / จ่ายแล้ว (4 ต.ค.69 · เจ้าของ *"หลีดบางตัวก็จ่ายไปแล้ว บางตัวก็ยังไม่จ่าย
    อยากรู้ว่าจ่ายให้ใครบ้าง"*)**
    - **ต้นเหตุที่ลีดจ่ายแล้วยังค้างในห้อง**: จับคู่ใบจ่ายลีด (`find_slip`) ทำ **เฉพาะตอนมีคนเปิดแชทนั้น** → แอดมินโพสต์ใบ
      ในกลุ่มจ่ายเบอร์แล้ว แต่ลีดยังค้างในห้องพักไปเรื่อยๆ (วัดจริง 4 ต.ค.69: ห้องพัก 21 คน **มีใบในกลุ่มแล้ว 10 คน**)
    - **`slip_sweep()`** ([connect.py](checkout/connect.py)) กวาดลีดในห้องพักแล้วเรียก `autofill(o, slip_min=3)` ให้เอง
      · ได้เลข = ออกจากห้องเอง · ต่อคนหาซ้ำทุก **3 นาที** (`SLIP_SWEEP_MIN` · ตอนเปิดแชทยัง 30) · ทั้งรอบเว้น ≥55 วิต่อ worker
      · **`slip_sweep_bg()` = thread แยก** เรียกจาก `tick` (cron ทุกนาที) **และ** ตอนแอดมินเปิดแท็บห้องพัก
        — ห้ามรันในที่ใน cron_tick (โหลดแชทหลายสิบคน · กฎเดิม: ของช้าต้องไม่หน่วงงานอุ่นข้อมูล) · ผลล่าสุด KV `slip_sweep_last`
      · ลูกค้าจำลองข้าม (กติกาเดิม: ไม่ดึงใบของลูกค้าจริงมาปน)
    - **`auto["_slip"]` เก็บเพิ่ม `tag` (แท็กท้ายใบ) · `seller` (ชื่อเล่น) · `by` (คนโพสต์ใบ = แอดมินที่จ่าย)**
      · **`tag_nick()`** แปลงแท็ก (ชื่อ LINE คำแรก "@เซลมัท") → ชื่อเล่นในทะเบียน (Employee + LineProfile พนักงาน · จำ 10 นาที)
        **ตรงหลายคน/ไม่เจอ = คืนแท็กเดิม ไม่เดา** · `_poster()` ใช้ `nickname_for` → **ไม่คืน LINE id ดิบ**
      · ลีดที่จับคู่ใบไว้ก่อนมีช่องนี้ → รอบกวาดเติมผู้รับจากเลขลีด (`_slip_by_code` · ทีละ 20)
    - **`assigned_list()`** = ลูกค้าแชทที่ได้เลขใน 7 วัน รวม 2 ทาง: ปุ่มจ่ายเบอร์ในระบบ (`assigned_at` · ผู้รับ = เจ้าของ ·
      "ระบบ (ทดลอง)") / ใบในกลุ่ม (`_slip` · "ใบในห้องจ่ายเบอร์") → `inbox?view=tocode` ส่ง **`assigned`** (แอดมินเท่านั้น)
      + ใบร่างที่ได้เลข (`parked.assigned[].sellerNick`)
    - **หน้าเว็บ**: หัวห้องพักมีปุ่มสลับ **รอจ่ายเบอร์ N / จ่ายแล้ววันนี้ N** · หน้าจ่ายแล้ว = ช่วง **วันนี้ / 7 วัน** ·
      **แถบสรุปผู้รับ** (`@นวล 2 · @มัท 1 · ไม่ทราบ 1` — กดชื่อ = กรองเฉพาะคนนั้น · กดซ้ำ = ทั้งหมด) · การ์ดบอก
      **"จ่ายให้ @ใคร"** + เลข + ทางไหน + โดยใคร · การ์ดแชทกดเปิดแชทได้ (กลับมายังอยู่หน้าจ่ายแล้ว) ·
      ส่วน "ใบร่างที่ได้เลขวันนี้" เดิมย้ายมารวมในหน้านี้ · ตัวกรองช่องทาง/ค้นหาใช้กับหน้านี้ด้วย (ค้นชื่อผู้รับได้)
    - เทสต์ `scripts/test_connect.py` [28] (ปลอมแค่ข้อมูล · ใบจริงผ่าน `parse_leadsheet`) + Chromium (จอ 1590 / 390)
  - **★★ ลูกค้าที่ "อยากขายรถให้เรา" ไม่ได้ถูกจ่ายในห้องจ่ายเบอร์ (4 ต.ค.69 · เจ้าของ *"สังเกตดูกลุ่มจ่ายเบอร์"*)**
    - **สำรวจกลุ่มจริง 14 วัน**: ใบลีดขาย `Ac Lead No.` อยู่ใน **ห้องจ่ายเบอร์ บ้านเก่า** (1,008) + **REJECT** (563) ·
      ลูกค้าที่จะขายรถ → แอดมินโพสต์ **ใบเคสรับซื้อ** คนละแบบใน **"เคสHOT (พี่หมี|พี่ต๊าด) ซื้อ-ขายรถช่องทางออนไลน์"**
      + **"เคสVERY HOT …"** (30 วัน: OC 269 · SC 4) · ตัวอย่างที่เจ้าของยกมา (New_matter ขายมาสด้า 2) = **OC-7436 → @หมีน้อย**
    - **รูปใบ** `leadgroup.parse_buycase()`: `โค้ด : OC-7436` · ADS · รุ่น · เลขไมล์ · ทะเบียน · **เบอร์ติดต่อ** ·
      **ชื่อลูกค้า : <ชื่อ> / <ช่องทาง>** · เพิ่มเติม · ขายเพราะ · ราคากลาง · `@หมีน้อย`/`@•Tard'ANUPonG•`
      (**ครึ่งหนึ่งไม่แท็ก** — ชื่อในวงเล็บของกลุ่มบอกว่าของใคร · `_buy_owner` ลอง "พี่ต๊าด" แล้ว "ต๊าด" ในทะเบียน)
      · ต้อง **ขึ้นต้นด้วย "โค้ด"** — ข้อความตามงาน "OC-7436 ลูกค้าทักมาใน Line@ … @หมีน้อย" ไม่ใช่ใบ
      · ทดสอบกับใบจริง 30 วัน: **อ่านได้ 273/273** · เบอร์ใช้ได้ 270
    - **`find_buy_slip()`** จับคู่ด้วย **เบอร์เต็ม** หรือ **ชื่อตรงทั้งชื่อ + ช่องทางไม่ขัด** (`_channel_fits`: ใบเขียน
      "เพจguru" แต่ลูกค้าทัก LINE = คนละคน) · เรียกใน `autofill` **เฉพาะตอนไม่มีใบลีดขาย** (มีทั้งคู่ = ใบขายชนะ)
    - **เลข OC/SC ไม่ใส่ช่อง Code ของลีดขาย** — เก็บที่ **`ChatLead.auto[BUY_KEY="_buy"]`** = `{code, at, group, tag,
      seller, by}` · `to_code()` ตัดออก (ออกจากห้องพัก) · `assigned_list` ใส่ `kind:"buy"` · `how` = "ส่งจัดซื้อ · เคสHOT (พี่หมี)"
      · `row_json.buyCode` (ป้าย "ส่งจัดซื้อ OC-…" ในรายชื่อ) · `lead_json.buy` → แผงขวาขึ้น "ส่งจัดซื้อแล้ว … → @พี่หมี"
      แทนกล่องจ่ายเบอร์ · ปุ่ม "จ่ายเบอร์" บนหัวแชทซ่อน · รถในใบเป็นรถของลูกค้า **ไม่เอามาเติมช่องรถของฟอร์ม**
    - **`tag_nick` แยกตัวจับคู่ออกเป็น `_tag_match()`** (คืน "" เมื่อไม่เจอ) — เดิมคืนแท็กเดิมทั้งตอนเจอและไม่เจอ
      เลยแยกไม่ออกว่า "พี่ต๊าด" ไม่มีในทะเบียน (เทสต์จับได้)
    - ⚠️ **ที่หน้าเว็บโชว์ "ใบจ่ายลีด (ย่อ)" แบบ `Ac Lead No. -` / `@` ว่าง = ใบที่ระบบประกอบให้คัดลอก** ยังไม่มีเลข/เซลล์
      ไม่ใช่ใบที่อยู่ในกลุ่ม (เจ้าของก๊อปมาให้ดู 4 ต.ค. — ใบจริงของลูกค้าคนนั้นคือ OC-7436 ในกลุ่มเคสHOT)

- **★★ Facebook Messenger ในคิวเดียวกับ LINE (4 ต.ค.69 · เจ้าของเลือก "รวมคิวเดียวกับ LINE")** — checkout migration **0030**
  - **`ChatOwner.fb_profile`** (OneToOne FbProfile · `profile` กลายเป็น null ได้) — แถวมีอย่างใดอย่างหนึ่ง ·
    **ใช้ `connect.cust(o)` / `is_fb(o)` / `is_sim_row(o)` เสมอ ห้ามเรียก `o.profile.…` ตรงๆ ในโค้ดใหม่** (FB = None)
  - **★★ ทางหลัก = Messenger webhook (Facebook ส่งมาเอง)** [fb_webhook.py](checkout/fb_webhook.py) · `/api/meta/webhook`
    (เจ้าของสั่ง 4 ต.ค.69 *"ถ้าดึงจาก API ทุกหนึ่งนาที มันจะติด Token ลองเปลี่ยนวิธีอื่นดู"*)
    - GET = Meta ทักทายตอนลงทะเบียน URL (`hub.verify_token` เทียบ `META_WEBHOOK_VERIFY_TOKEN` → ตอบ `hub.challenge`)
    - POST = ตรวจ `X-Hub-Signature-256` (HMAC-SHA256 ด้วย `META_APP_SECRET`) → **ไม่ตั้ง secret = 503 ไม่รับ**
      (ต่างจาก TikTok ที่รับไว้ก่อน — ตรงนี้แชทกลายเป็นลูกค้าในคิวเซลล์ทันที ใครรู้ URL ก็ยิงของปลอมได้) ·
      ลายเซ็นผิด = 403 · ตอบ `EVENT_RECEIVED` ทันทีแล้วประมวลผลใน thread (`INLINE=True` เฉพาะเทสต์)
    - `handle_payload()`: เพจที่ไม่อยู่ใน `META_PAGE_IDS` = ไม่เก็บ · `is_echo` = ข้อความเพจตอบ (หยุดนาฬิกา) ·
      read/delivery = ข้าม · ซ้ำ `mid` = ไม่เก็บซ้ำ · **ลูกค้าเดิม = ไม่ยิง Graph API เลย** · ลูกค้าใหม่ =
      `/<page>/conversations?user_id=` 1 ครั้ง (หาห้อง+ชื่อ) · หาไม่เจอ = **ห้องชั่วคราว `psid:<id>`** แล้ว
      `fb_sync._upsert_profile` ย้ายข้อความเข้าห้องจริงตอนรอบสำรองเจอ
    - ผลล่าสุด KV `fb_webhook_last` (รวม "ส่งมาแต่ไม่รับเพราะอะไร") · การ์ด FB ในตั้งค่า Connect โชว์ URL/สถานะ secret/ส่งล่าสุด
    - **ผูกเพจกับแอป** `POST /connect/api/fb_webhook` (แอดมิน) → `/<page>/subscribed_apps` fields `messages,message_echoes` ·
      GET = ตรวจว่าผูกแล้วหรือยัง
    - **ขั้นตอนฝั่งเจ้าของ (ยังไม่ได้ทำ ณ 4 ต.ค.69)**: [deploy/meta_webhook.md](deploy/meta_webhook.md) — env 2 ตัว ·
      ลงทะเบียน Callback URL ในแอป Meta · กดผูกเพจ
    - **★★ webhook จากลูกค้าจริงต้องมี Advanced Access ของ `pages_messaging` = ผ่าน App Review + ยืนยันธุรกิจ**
      (เอกสาร Messenger webhook: *Standard Access = รับได้เฉพาะคนที่มีบทบาทในแอป · Advanced Access = รับจากลูกค้า
      ต้องผ่าน App Review*) · เจ้าของทัก 4 ต.ค.69 ว่า "ต้อง Live ก่อนไม่ใช่หรอ" — ถูก และหนักกว่านั้นคือต้องผ่าน review ด้วย
      · **ระหว่างยังไม่ผ่าน แชทลูกค้าจริงเข้าทางดึงสำรองอย่างเดียว** → ถ้าตั้งห่าง (เช่น 10 นาที) แชทจะมาถึงช้าและขึ้น "เลยเวลา"
      ทันที (เส้นตายนับจาก `sent_at` ของลูกค้า) · ช่วงนี้ควรตั้งทางสำรอง 2–5 นาที
      (`sync_live` หยุดเองเมื่อโควต้าถึง `STOP_USAGE_PCT` อยู่แล้ว)
  - **ทางสำรอง = ดึงเอง** `fb_sync.sync_live()` ทุก **`fb_poll_min` นาที (ค่าตั้งต้น 2 · ตั้งได้ 2–60)** · เดิมทุก 1 นาที
    · **★ ไม่ติดลิมิต token (วัดจริง 4 ต.ค.69 ตอน prod ดึงทุก 1 นาที)**: header `x-business-use-case-usage`
      ของ Meta ประเภท `messenger` = call/CPU/เวลา **1%** ทุกตัว · ลิมิตนับ **ต่อเพจ** (ใช้ page token)
      ไม่ใช่ต่อ user token · token ของคนใช้แค่ขอ page token (จำ 1 ชม.) · มีด่านหยุดเองที่ 60% (`STOP_USAGE_PCT`)
      · ค่าตั้งต้นเคยเป็น 10 (ผมตั้งเผื่อเกินไป) → แก้เป็น 2 ก่อน deploy
    (เรียกจาก `connect.tick` → `fb_tick_bg()` ใน thread · ผล KV `fb_live_last`) ·
    **`fb_poll_due()` เช็คเวลาจาก KV ร่วมทุก worker** (จำแค่ใน process = 3 worker ดึงถี่ขึ้น 3 เท่า) + `fb_tick_bg` จองรอบใน KV ก่อนเริ่ม ·
    เพจละ 1 คำขอ (25 ห้องล่าสุด) · ห้องที่ `updated_time` ไม่เปลี่ยน = ไม่ยิง API · ห้องที่ขยับ = ดึงเฉพาะข้อความใหม่
    → `note_fb_batch()` · รอบเที่ยงคืนเดิม (`sync`) ก็แจ้ง Connect ด้วย (`_notify_connect`)
  - **ข้อความเก่ากว่า `FB_LIVE_MIN` (30 นาที) ไม่เริ่มนับ 5 นาที** — กันวันแรก "เลยเวลา" ท่วม · ลูกค้า FB ที่คุยใน 7 วัน
    (`FB_BACKFILL_DAYS`) มีแถวใน "ทั้งหมด" ผ่าน `sync_rows` (ไม่สร้างให้ทั้ง ~6,600 ห้องย้อนหลัง)
  - **★ ตอบในแอป Facebook / Business Suite = หยุดนาฬิกาให้** (Facebook ส่งข้อความขาออกมาด้วย ต่างจาก LINE OA Manager)
    — จด REPLY โดย "ตอบใน Facebook" · บับเบิลขาออกบอกว่าใครตอบ
  - **★★ ข้อความ "ตอบอัตโนมัติ" ของเพจไม่นับว่าตอบ (4 ต.ค.69 · เจอในแชททดสอบของเจ้าของ)** — Business Suite ส่ง
    ข้อความต้อนรับ/ฟอร์มขอ ชื่อ-เบอร์-ไลน์ **วินาทีเดียวกับที่ลูกค้าทัก** และ Facebook ติดป้ายมาเหมือนคนตอบทุกอย่าง
    (`inbox/sent/source:web`) → เดิมปิดรอบทันที = **แชท FB ไม่มีวันขึ้นเลยเวลา** (prod: 8 จาก 44 รอบที่ปิดด้วย
    "ตอบใน Facebook" ปิดภายใน 15 วิ) · ตอนนี้ `FB_AUTO_SEC`=15: ขาออกที่ไม่ได้ส่งจาก Connect และออกตามหลังข้อความ
    ลูกค้าไม่เกิน 15 วิ = `_reply_done(close=False)` (อัปเดตข้อความล่าสุด ไม่ปิดรอบ ไม่จด REPLY) · บับเบิลขึ้น
    **"ตอบอัตโนมัติ (เพจ)"** · `note_fb_batch` เรียงวินาทีเดียวกันให้ข้อความลูกค้ามาก่อน · ⚠️ คนที่ตอบใน Facebook
    เร็วกว่า 15 วิ จะไม่ถูกนับ (เกิดยากมาก)
  - ส่วนกลาง LINE/FB: `_customer_in()` (เริ่มรอบ/คืนคิวเมื่อเซลล์ลาออก) + `_reply_done()` (ปิดรอบ · ไม่ปิดถ้าคำตอบเก่ากว่ารอบ)
  - **★ 6 ต.ค.69 — เซลล์ตอบ/ปิดรอบลูกค้า FB ไม่ได้แล้ว (สิทธิ์เก็บข้อมูลเท่านั้น · เจ้าของสั่ง)** — ตอบจาก Connect เหลือแค่แอดมิน
    (ดูหัวข้อ "ส่งใบจ่ายลีดเข้ากลุ่มจ่ายเบอร์จริง")
  - **ตอบจาก Connect** [fb_send.py](checkout/fb_send.py) — Send API `POST /<page>/messages` (`messaging_type=RESPONSE`)
    ผ่าน **`meta.post()`** (ใหม่ · ด่านเพจบริษัทอื่นเหมือน `get` · **ไม่ลองซ้ำ** กันลูกค้าได้ 2 ข้อความ) · ส่งไม่ได้ = ไม่บันทึก ·
    แปล error เป็นภาษาคน (**เกิน 24 ชม.** = subcode 2018278 · บล็อกเพจ · สิทธิ์แอป)
  - **★ สวิตช์ `connect_config.fb_reply`: off / test (ค่าตั้งต้น) / on** — test = ตอบได้เฉพาะ `fb_test_rows`
    (แอดมินกด "ใช้แชทนี้ทดสอบการตอบ" ใต้ช่องพิมพ์ · `POST /connect/api/fb_test {id, on}`) ·
    เจ้าของสั่ง "ทดสอบกับบัญชี FB ของเจ้าของก่อน ไม่ส่งหาลูกค้าจริง" · `fb_on` = ดึงแชท FB เข้าคิว (เปิด)
    · ตั้งได้ที่ Connect → ตั้งค่า → การ์ด "Facebook Messenger" (บอกสถานะดึงล่าสุดด้วย)
  - ข้อมูลลีด FB: เบอร์จากแชท · **ชื่อ Account = ชื่อใน Facebook** · **ไม่เดาช่องทาง** (ชีตแยก "เพจบ้านเก่า"/"เพจอ่อนนุช"
    แต่ชื่อจริง 2 เพจต่างกันแค่คำท้าย — บอกไม่ได้ว่าเพจไหนคือช่องไหน · ถ้าเจ้าของบอกได้ค่อยทำตารางจับคู่)
  - **PSID ลูกค้าไม่ออกหน้าเว็บ** (อ้างด้วย `ChatOwner.id` เหมือน LINE) · `meta.page_token()` จำไว้ 1 ชม.ต่อ process
  - **ไม่มีรูปโปรไฟล์ลูกค้า FB** (`fill_pictures` กรองเฉพาะ LINE) — โชว์ตัวอักษรบนวงกลมแทน
- **TikTok**: แอป Login Kit ที่เชื่อม 10 ช่องไม่มี DM/คอมเมนต์เลย → เจ้าของเลือก **ยื่นขอ TikTok API for Business**
  ขั้นตอนอยู่ที่ [deploy/tiktok_business_api.md](deploy/tiktok_business_api.md) · ระหว่างรอ ลีด TikTok เข้าทางห้องพัก Lead

- **⚠️★ 4 ต.ค.69 — "แชทไม่อัพเดทตั้งแต่เมื่อคืน" (เจ้าของแจ้ง) — ไม่ใช่ระบบรับข้อความพัง**: วัดจาก prod
  ข้อความลูกค้าเข้าครบ (160 ข้อความ/24 ชม. · ล่าสุด 14:24) และแถว Connect อัปเดตครบทุกคน **แต่คำตอบที่ส่งผ่าน Connect
  ล่าสุดคือ 23:21 เมื่อคืน** → ทีมตอบใน **แอป LINE OA Manager ซึ่ง LINE ไม่ส่งกลับมาให้ระบบ** → Connect เห็นเหมือนไม่มีใคร
  ตอบ ทุกคนขึ้น "เลยเวลา" · ทางแก้ = ตอบผ่าน Connect (เปิดอยู่แล้ว) หรือกด "ไม่ต้องตอบ" ให้แชทที่ตอบในแอปแล้ว ·
  **ข้อ 4 ของรายการข้างล่าง (ถอดสิทธิ์ LINE OA Manager) คือต้นเหตุตรงๆ**

- **★ 4 ต.ค.69 — พนักงานที่ทักบัญชีลูกค้า ขึ้น Connect ด้วย (ป้าย "พนักงาน")** — เจ้าของทักทดสอบจาก LINE ส่วนตัวแล้ว
  "ไม่มีชื่อขึ้น": ข้อความ **ถูกเก็บแล้ว** แต่ `note_customer_message` ตัดทุกบัญชีที่ผูกทะเบียนพนักงานทิ้ง · เอ็มส่งชื่อ+เบอร์
  ลูกค้าที่ถามหา Civic FC เข้า OA (08:35–09:35) ก็หายเงียบแบบเดียวกัน · วัด 30 วัน: พนักงาน 4 คน 38 ข้อความ (ไม่รก)
  - ตอนนี้: พนักงานทัก **บัญชีลูกค้า** = ขึ้นคิวเหมือนลูกค้า + ป้าย "พนักงาน" (`row_json.staff`) ·
    ทัก **บอทแจ้งเตือน** (`STAFF_SKIP_CHANNELS = ("push",)`) = ไม่ขึ้น (นั่นคือแอดบอทเพื่อรับแจ้งเตือน ไม่ใช่ลีด)
  - `store_chat` ส่ง `channel=` (บัญชีที่ได้ยิน) ให้ `note_customer_message` · `note_reply` ปิดรอบให้พนักงานที่มีแถวแล้วเท่านั้น
  - `sync_rows` เติมแถว (ไม่เริ่มรอบรอ) ให้พนักงานที่ทักบัญชีลูกค้าใน 7 วันก่อนแก้

- **★★ งานจ่ายเบอร์ — นาฬิกาโทร · จ่ายวน · ไม้ 2 · การ์ดปุ่ม · อ่านรายงานผล (10 ต.ค.69 · เจ้าของสั่ง)** —
  [leadflow.py](checkout/leadflow.py) + [phonebook.py](checkout/phonebook.py) · checkout migration **0034** (`LeadPhone` · `LeadTask` · `LeadReport`)
  - ที่มา: เจ้าของส่งตัวอย่างหน้าจอ 3 ชุด (ศูนย์ควบคุมลีด · มือถือเซลล์ · หน้าเซลล์ — คนนอกทำ) แล้วสั่ง
    *"ปรับให้เข้ากับระบบเรา ไม่ใช่ปรับไฟล์ของเขา"* → เลือก 7 อย่าง (ทำครบ):
    แอดมิน ① เช็คเบอร์ซ้ำตอนจ่ายเบอร์ ② ส่งต่อไม้ 2 ③ จ่ายวน + นาฬิกาโทร · เซลล์ ④ รถใหม่ตรงกับลูกค้าของฉัน
    ⑤ เช็คเบอร์ซ้ำเอง ⑥ การ์ดปุ่ม รับเคส/ขอผ่าน ⑦ อ่านรายงาน "เลข + ผล" → การ์ดยืนยันแชทส่วนตัว → ลงชีต
  - **ข้อเท็จจริงจากห้องจริง (วัดก่อนทำ)**: เซลล์รายงานผลด้วย **เลขรัน + ผล** ("9075 รอตอบครับ" · ไม่เว้นวรรคก็มี)
    ~1,189 ข้อความ/สัปดาห์ · แอดมินทวงในรูปแบบเดียวกันแต่มี **@** ("9075 @มัท ตามด้วย") → **มี @ = ไม่นับ** ·
    ไม้ 2 ในห้อง REJECT = **R + เลขเดิม + /1** (1,075/1,077 ใบ · ไม่เคยเห็น /2) · `_CODE_RE` รับ `/n` แล้ว
  - **สมุดเบอร์ (`LeadPhone`)** เก็บแค่ เบอร์+เลขลีด+เซลล์+ช่องทาง+รถ+วันที่ (ไม่เก็บชื่อลูกค้า) · 3 แหล่ง: ชีตลีด
    (`rebuild_from_sheet` ทั้งชุดทุก 6 ชม. · thread) · ใบในห้องจ่ายเบอร์ · ปุ่มจ่ายเบอร์ · ชีตชนะเรื่อง "เซลล์"
    · แอดมิน: กล่องจ่ายเบอร์ (แชท + ใบร่างในห้องพัก) ขึ้น **"เบอร์นี้เคยเป็นลีด X ของ @Y"** + ปุ่มจ่ายให้เจ้าของเดิม
      + **ถามยืนยันถ้าจะจ่ายให้คนอื่น** · เซลล์: หน้าเซลล์มีช่อง "เช็คเบอร์ลูกค้าซ้ำ" (ของคนอื่นบอกแค่ชื่อ+เดือน)
  - **นาฬิกาโทร (`LeadTask` · 1 แถว/ใบ)** — ใบจากปุ่มในระบบ (`before_post`/`after_post` ใน `connect._post_slip` + `leadpark._post`)
    **และใบที่แอดมินโพสต์เองในห้อง** (`note_group_slip`) · เริ่มนับเมื่อใบถึงกลุ่มจริง · ต้องรายงานภายใน `call_min` (15)
    นับเวลาทำการของ Connect · **ระบบรู้ไม่ได้ว่าโทรจริงไหม** → หยุดเมื่อ "รายงานผล" ในห้อง หรือตอบลูกค้าผ่าน Connect
    (`note_chat_reply` ใน `_reply_done`) · กดรับเคส = รับทราบ ไม่หยุดนาฬิกา · ใบทดลอง/บัญชีทดสอบ = มีนาฬิกา (ทดสอบหน้าจอได้) ไม่ส่งอะไรออก
    · หน้าเว็บ: Connect → ห้องพัก Lead → แท็บ **"นาฬิกาโทร"** (เลยเวลา/ขอผ่าน/รอ/รายงานแล้ว · จ่ายใหม่ · ไม้ 2) +
      กล่อง "นาฬิกาโทร / ส่งต่อไม้ 2" ในแผงขวาของแชทที่มีเลขแล้ว
  - **อ่านรายงาน** (`process_pending` · ตัวชี้ GroupChat.id ใน KV `leadflow_state` · advisory lock · webhook + cron เก็บตก):
    ผู้ส่งต้องเป็น **ทีมขาย** (ผูกทะเบียน + `team_of`) · จับคู่งานด้วยเลขรัน (/n = งานที่ขึ้นต้น R · หลายงาน = ของคนรายงานก่อน)
    · ใบเก่าก่อนเปิดระบบ = หาใบในห้องย้อน 60 วันแล้วสร้างงานย้อนหลัง (`_lazy_task`) · อ่านคำ **ไม่ใช้ AI**:
    สถานะ Z (คำในรายงาน + `lead_keywords`) · อาชีพ/รายได้/อายุงาน/ประวัติผ่อน/ประเภทลูกค้า · **วันนัด** (`parse_appt` —
    ต้องมีคำว่า นัด/เข้ามา/มาดู ก่อน · พรุ่งนี้/มะรืน/วันในสัปดาห์/หน้า/d/m · 10 โมง/บ่ายสอง/4 โมงเย็น/3 ทุ่ม/เที่ยง/14:30 ·
    เวลาที่ผ่านไปแล้ว = ไม่เดา)
  - **การ์ดยืนยัน** (`report_on`): เฉพาะรายงานที่ **มีข้อมูลจริง** (`rich` — "รอตอบ" เฉยๆ ไม่ส่ง) → แชทส่วนตัวเซลล์ →
    กด "ถูกต้อง" = `google_sheets.update_lead_fields` (หาแถวรอบเดียว · `values:batchUpdate` · **เขียนเฉพาะแถวที่เซลล์ในชีต =
    คนกด** ไม่งั้นบอกว่าเป็นของใคร) + เติมข้อมูลลีด Connect ช่องที่คนยังไม่แก้ · "ไม่บันทึก" = ข้าม · เตือนนัด (`remind_on`) ครั้งเดียว
  - **การ์ดปุ่ม** (`card_on`): ต่อท้ายใบใน **push เดียวกัน** (`slippost.post(extra=…)` — LINE นับโควต้าต่อผู้รับต่อครั้งที่ยิง)
    · ปุ่ม รับเคส / ขอผ่าน / โทรหาลูกค้า (tel:) · บอก "รายงานผลภายใน HH:MM" (การ์ด LINE แก้ย้อนหลังไม่ได้ → ไม่ใช่นับถอยหลัง)
    · postback ลงชื่อ **HMAC (`SECRET_KEY`)** · กดได้เฉพาะคนที่ได้เคส · ตอบด้วย **reply token (ฟรี)** · มาทาง webhook เดิม
      (`_checkout_ingest` → `leadflow.handle_events` · n8n ส่ง body ดิบอยู่แล้ว ไม่ต้องแก้) · ล่าสุดที่ KV `leadflow_postback_last`
  - **คิวจ่ายวน** (`rr_candidates`): ทีมใน `rr_teams` · ตัดวันหยุดของคนนั้น (ช่อง "วันหยุด") · บัญชีทดสอบ · ยังไม่เช็คชื่อ
    (ถ้าเปิด `need_checkin`) · เต็ม `cap_day` · เรียงคนได้ใบน้อยสุดวันนี้ก่อน (เท่ากัน = ได้ใบล่าสุดนานกว่า) · หน้าเว็บโชว์เป็นชิปให้กดเลือก
    · **★★ 11 ต.ค.69 — "ใบวันนี้" นับตามเวลาที่ใบถึงกลุ่ม (`posted_at`) ไม่ใช่เวลาที่ระบบสร้างงาน** (`leadflow.slip_since()`)
      เจ้าของถาม *"ทำไมชื่อเซลล์เหลือแค่นี้"* (ห้องพัก Lead เหลือปุ่ม 5 คน) · ต้นเหตุ: เซลล์รายงานผลเคสเก่า → `_lazy_task`
      สร้างงานย้อนหลังให้ใบเก่า (ย้อนได้ 60 วัน) → `created_at` = วันนี้ → นับเป็น "ใบวันนี้" → **เต็มเพดานแล้วหลุดคิว**
      (วัด prod: มัท 30/12 แต่ใบที่ถึงกลุ่มวันนี้จริง 4 · เฟิร์ส 20→4 · เจ 16→1) · ใช้ตัวเดียวกันทุกจุดที่นับ "ใบวันนี้":
      `_today_counts` (คิว/มือเซลล์วันนี้) · `tasks_json` (นาฬิกาโทร) · `seller_tasks` (งานวันนี้/แอป) · `console_data` (แดชบอร์ดทีม)
      · ใบที่ระบบออกเลขแต่ส่งเข้ากลุ่มไม่สำเร็จ (`posted_at` ว่าง) นับตามเวลาที่จ่าย · **นับ "ใบวันนี้" ที่ไหนใหม่ ใช้ `slip_since` ห้ามใช้ `created_at`**
    · ปุ่มเซลล์ในการ์ดห้องพัก = **ทุกคนที่อยู่ในคิว** (เดิมตัดที่ 9 คน · ทีม A+B+C เกิน 9 ได้ = มีคนหายเงียบ) · คอลัมน์ปุ่ม `max-width: 440px`
      ให้ตัดบรรทัด ไม่ดันข้อมูลลีดจนเหลือคำละบรรทัด · คนที่เต็มเพดาน/หยุด จ่ายได้ทาง "ตั้งเลข/เซลล์เอง" หรือกล่องจ่ายเบอร์ในแชท
    · **`auto_assign`** = ใบร่างในห้องพัก Lead ที่รอเกิน `auto_after_min` → จ่ายวนเอง (ทีละ 3 ใบ/นาที) · **เบอร์ซ้ำ = ไม่จ่ายเอง** ·
      **แชท LINE/FB ไม่จ่ายเอง** (ยังต้องดูว่าเป็นลีดขายไหม) · ผลที่ KV `leadflow_auto_last`
      · **★ 18 ต.ค.69 (เจ้าของ "ห้องพักหลีดตั้งแต่ตอนนี้ 9523 … เข้าเองอัตโนมัติ · รอ 10 นาที")**: รอตั้งต้น 3 → **10 นาที** ·
        **เปิดสวิตช์ = จด `auto_since`** (`clean_cfg` · ปิด = ล้าง) → จ่ายเฉพาะใบร่างที่โพสต์หลังเปิด ใบเก่าที่ค้าง (บางใบตั้งใจไม่จ่าย/ลูกค้าเก่า)
        ไม่ถูกจ่ายรวดเดียว · `save_cfg` ตรงๆ ไม่มี since = พฤติกรรมเดิม · หน้าตั้งค่า/หน้ากฎบอกเวลาที่เปิด
        · ⚠️ prod เก็บ `auto_after_min: 3` ไว้ใน KV แล้ว — ค่าตั้งต้นใหม่ไม่ทับ ต้องแก้ช่อง "รอเกิน" เป็น 10 ตอนเปิดสวิตช์
      · **★ 18 ต.ค.69 "QR code" ไม่ใช่ไอดี (`leadpark.clean_line_id`)** — แอดมินพิมพ์ "ID LINE : QR code" แทนไอดีเมื่อลูกค้าส่งรูป QR
        (prod 30 วัน: 96/709 ใบร่าง) · เดิมกลายเป็นคีย์ `l:qrcode` ร่วมกัน → ใบร่างคนละคนถูกนับเป็นโพสต์ซ้ำ (7 วัน = 13 ใบหาย) +
        จับคู่ใบจริงของลูกค้าคนอื่น (ขึ้นว่าจ่ายแล้วทั้งที่ยังไม่จ่าย) · ตอนนี้ไม่มีไอดี = ใช้ชื่อ Account+ช่องทาง · "Qr code / yingat9015" → yingat9015
      · **★ 18 ต.ค.69 เลขรันอ่านสำเนาชีตลีดด้วย (`connect._sheet_running`)** — เลขที่แอดมินลงชีตตรงๆ ไม่ได้โพสต์ใบ ·
        **แท็บเดือนนี้เท่านั้น + นำหน้าใบในกลุ่มไม่เกิน 30** — ชีตมีเลขพิมพ์ผิดจริง (แท็บ ก.ย. แถว 2397–2400 = TLD9-9662..9665
        แทน 7662..7665) ถ้านับจะกระโดดไปออก 9666 · ไม่มีใบในกลุ่ม = ไม่นับชีต · เทสต์ `python scripts/test_park_qr.py` (42 ข้อ)
    · **`auto_pull`** = เลยเวลา/ขอผ่าน → จ่ายใหม่คนถัดไป **เลขเดิม ใบเดิม แท็กคนใหม่** (โอนแชทตาม) · ใบละไม่เกิน `pull_max` ·
      ใบที่แอดมินโพสต์เองจ่ายใหม่จากระบบไม่ได้ (ไม่มีลูกค้า/ลีดให้โอน → ใช้ไม้ 2)
  - **ส่งต่อไม้ 2** (`forward_chat`/`forward_ext`): เลข `fwd_code` · จำเลขเดิมใน `ChatLead.auto["_prev_codes"]` · โอน · ใบเข้าห้อง REJECT
  - **④ รถตรงกับลูกค้าของฉัน**: `refresh_needs` ทุก 30 นาที (thread) อ่านห้องจ่ายเบอร์ **ต่อจากที่ค้าง** (`leadgroup.ingest(since_id=)`
    — เดิมอ่าน 4,000 ข้อความ **เก่าสุด** เสมอ พอห้องเกิน ~3 สัปดาห์ข้อความใหม่ไม่ถูกอ่านเลย) → `need_match.scan` → แยกตามเซลล์
    (`tag_nick`) ใน KV `leadflow_needs` · หน้าเซลล์โชว์ใต้ "ดีลค้าง"
  - **สวิตช์ทั้งหมดใน KV `leadflow_config`** — ตั้งที่ Connect → ตั้งค่า → การ์ด "งานจ่ายเบอร์" (เปิดอันที่ส่งออก = ถามยืนยัน)
    · **ทุกอย่างที่ส่งออก/จ่ายเอง ปิดโดยปริยาย** (`card_on` · `report_on` · `remind_on` · `auto_assign` · `auto_pull`) ·
    นาฬิกา + สมุดเบอร์ + อ่านรายงาน (จดอย่างเดียว) ทำงานเลยหลัง deploy
  - **พังเงียบไม่ได้**: `before_post`/`refresh_needs` ล้ม = จด KV `leadflow_error` + `dash_event_log` (kind=`leadflow`) · ใบยังส่งได้ตามเดิม
  - **อายุข้อมูล**: `LeadTask`/`LeadReport` 90 วัน (`cleanup`) · สมุดเบอร์จากชีตสร้างใหม่ทุก 6 ชม.
  - **เทสต์**: `python scripts/test_leadflow.py` (**129 ข้อ** · ปลอมที่ `requests` + ใบรับรอง Google) · `LF.BG_SLOW = False` ในเทสต์
    (thread งานช้าชน SQLite — `test_connect.py` ตั้งด้วย) · ตรวจ UI ด้วย Chrome จริง (template ตัวจริง · stub เฉพาะ API · ไม่มี JS error ·
    ไม่ล้นจอ 1590/390) · **บทเรียน**: `exclude(card__demo=True)` บนคีย์ JSON ที่ไม่มีอยู่ **ตัดแถวทิ้งหมดบน SQLite** → กรองใน Python

- **★★★ 11 ต.ค.69 — หน้าตาใหม่ตามแบบที่เจ้าของส่งมา: "ศูนย์ควบคุมลีด" (Connect) + หน้าเซลล์แบบเมนูซ้าย**
  *"เปลี่ยนตามแบบ ไฟล์เอามาแทนอันเดิมของเราอะ … หน้าแชท จ่ายหลีด ต่างๆ"* → เจ้าของเลือก **หน้าเซลล์ /me/ ทั้งหน้า + Connect ฝั่งเซลล์ + ฝั่งแอดมิน**
  และ **เก็บหน้าเดิมไว้ที่ลิงก์สำรอง** · **ตรรกะ/ข้อมูลเดิมทั้งหมดใช้ต่อ** เปลี่ยนแค่ "เปลือก" + เพิ่มหน้าที่แบบมีแต่ระบบยังไม่มี
  - **หน้าเดิม**: `/connect/?classic=1` ([connect_classic.html](checkout/templates/checkout/connect_classic.html)) ·
    `/me/?classic=1` / `/s/<token>/?classic=1` ([seller_classic.html](dashboard/templates/dashboard/seller_classic.html)) ·
    ทั้ง 2 หน้าใหม่มีลิงก์ "หน้าแบบเดิม" ที่ท้ายเมนูซ้าย · **⚠️ แก้ฟีเจอร์ในหน้าใหม่ หน้าเดิมไม่ได้ตามไปด้วย** (สำเนา ณ 10 ต.ค.69 —
    เป็นทางหนีช่วงเปลี่ยนผ่าน ไม่ใช่ของที่ต้องดูแลคู่กัน · ถ้าไม่มีใครใช้แล้วให้ลบทิ้ง)
  - **Connect แบบใหม่ ([connect.html](checkout/templates/checkout/connect.html))** — เมนูซ้ายสีม่วงเข้ม `#lc-rail` (แอดมิน 6 หน้า ·
    เซลล์ 1 หน้า) · ~~หัวหน้า + นาฬิกา · แถบขั้นตอน 3 ชั้น~~ (ตัดทิ้ง 11 ต.ค.69 รอบ 5 — เหลือ "เวรวันนี้ + กระดิ่ง" ในแถบเมนู) ·
    `?p=dist|db|pipe|dash|rules` เปิดหน้านั้นตรง (`setPanel()` · URL เปลี่ยนตามหน้า) · ฝังในแดชบอร์ด/จอแคบ = เมนูเป็นแถบแนวนอน
    | หน้า | ทำอะไร | ข้อมูลจาก |
    |---|---|---|
    | กล่องแชทรวม | รายชื่อ + แชท + ข้อมูลลูกค้า (ของเดิมทั้งหมด) | `inbox` · `chat` |
    | **ห้องพัก Lead** | ลีด 1 แถว = ข้อมูล + **เวลาพัก (นับสด)** + **ปุ่มชื่อเซลล์ — กดเดียวจ่ายเลย** (กรอบชมพู = คิวถัดไป) · เบอร์ซ้ำ = กล่องแดง + ปุ่ม "จ่ายให้เจ้าของเดิม" · ด้านขวา **มือเซลล์วันนี้** (`rrBoard` ได้กี่ใบ/เพดาน/ทำไมหลุดคิว) + กติกา (สถานะจริง) + บันทึกการจ่ายวันนี้ · แท็บ จ่ายแล้ว / นาฬิกาโทร = ของเดิม | `inbox?view=tocode` (+`rrBoard`/`lfStrip`) |
    | **ฐานข้อมูล Lead** | **ตารางดิบ 26 คอลัมน์เรียงตามชีตลีด** + คอลัมน์ "ตรวจซ้ำ" · ค้น เบอร์/4 ตัวท้าย/ID LINE/เลข/รุ่น · 5 โหมด: ทั้งหมด / **ลีดซ้ำ (Code·เบอร์·ไลน์)** / **ในระบบ ยังไม่ลงชีต** / คืนเคสรอไม้ 2 / รถใหม่แมตช์ลูกค้าเก่า · กดแถว = ตรวจลีดซ้ำ + ประวัติ + **ส่งต่อไม้ 2** + ทุกช่องที่มีค่า | `leaddb` |
    | **ไปป์ไลน์** | จอง → รอเซ็นต์ → รอผล → รอปล่อย → ปล่อย(เดือนนี้) · กรอบแดง = ค้างเกินกำหนด | `pipeline` |
    | **แดชบอร์ดทีม** | ใบวันนี้ · % รายงานผล · % ตอบแชททัน · ปล่อยเดือนนี้ · กรวยแชท→ปล่อย (บอกที่มาทุกแถว) · ตารางรายเซลล์ + 6 วันล่าสุด · สถิติเวลาตอบเดิมอยู่ข้างล่าง | `team` + `stats` |
    | **กฎและเส้นทาง** | **สวิตช์ใช้ได้จริง** (บันทึกทันที · เปิดเรื่องที่ส่งออก = ถามยืนยัน) + สองเส้นทาง/ลูกค้าหลายร่าง · ตั้งค่าละเอียดเดิมทั้งหมดอยู่ข้างล่าง | `config` + `leadflow` |
  - **ส่งต่อไม้ 2 จากเลขที่มีแต่ในชีต** (`leadflow.forward_code`) = สร้างลีดภายนอก `fwd:<เลขใหม่>` จากแถวชีต แล้วส่งใบเข้าห้อง REJECT ·
    **`forwarded_as(code)` กันส่งต่อซ้ำ** — เลขเดิมในแชท Connect ถูกเปลี่ยนเป็น R…/1 ไปแล้ว ค้นด้วยเลขเดิมไม่เจอ
    ถ้าไม่กัน จะได้ลูกค้าคนเดียว 2 เลข (เทสต์จับได้ก่อนขึ้น) · ส่งไปแล้ว = บอกเลข+คน และให้ใช้ "จ่ายใหม่" ในนาฬิกาโทรแทน
  - **"เลขอื่นของเบอร์เดียวกัน" = แถวชีตลีด + สมุดเบอร์** (สมุดเบอร์อย่างเดียวพลาดแถวที่ยังไม่ถูกสร้างสมุดใหม่ — เทสต์จับได้)
  - **ชื่อลูกค้าในฐานข้อมูล Lead มาจากใบจ่ายลีด/แชท** (ชีตลีดไม่มีช่องชื่อ) — ไม่เจอ = "—"
  - **★★ 11 ต.ค.69 (รอบ 2) — ฐานข้อมูล Lead ตรวจลีดซ้ำ 2 ทาง + ตารางตามคอลัมน์ชีต** ([console_data.py](checkout/console_data.py))
    *"ฐานข้อมูลหลีดเก็บ raw data อยู่สองแบบ … เช็คหลีดความ match อยู่สองแบบคือโค้ดและเบอร์ เพื่อป้องกันหลีดซ้ำกัน แล้วก็ออกแบบคอลัมน์ตามเดิม"*
    - **ช่อง "เบอร์โทร" ของชีตเก็บ 2 แบบ**: เบอร์ หรือ `ID LINE : xxx` (บางแถวมีทั้งคู่ `081… / ID LINE : …`) → `contact_keys()` คืน
      `p:<เบอร์ 10 หลัก>` / `l:<ไอดีตัวเล็ก>` · ตัดป้าย/คำลงท้าย ("ครับ") · ลิงก์ `line.me/ti/p/~xxx` = ไอดี xxx · ไอดีที่เป็นเลขเบอร์ = เบอร์
      · **`QR code` / `Line@` / `-` / "ชื่อไลน์ : …" = ไม่ใช่ไอดี** (ไม่งั้นทุกแถว QR code ซ้ำกันหมด) → แถวพวกนี้ติดป้าย "เทียบแค่ Code"
    - **ซ้ำ 2 แบบ**: **Code ซ้ำ** = เลขเดียวกันลงชีตมากกว่า 1 แถว (`Code ×N`) · **เบอร์/ไลน์ซ้ำ** = ติดต่อเดียวกันเป็นลีดคนละเลข (`เบอร์ ×N`/`ไลน์ ×N` = จำนวนลีดรวมตัวเอง)
      · **ไม้ 2 (`R`+เลขเดิม+`/n`) = ลีดเดียวกับเลขเดิม ไม่นับว่าซ้ำ** (`lineage()` ตัด `/n` + `R` เฉพาะตอนมี `/n`) · ติดต่อที่ผูกเกิน 12 ลีด = ค่าขยะ ไม่ใช้เทียบ (`KEY_CAP`)
      · โหมด "ลีดซ้ำ" จัดกลุ่มด้วย union-find (Code + ติดต่อ) · หัวกลุ่มบอกว่าซ้ำเพราะอะไร
    - **รวมลีดที่ระบบออกเลขแต่ยังไม่ลงชีต** (ChatLead/ExtLead ที่มีเลข · ไม่นับเลขทดลอง/ลูกค้าจำลอง) — เป็นแถว 26 ช่องที่ประกอบจากข้อมูลในระบบ
      ป้าย "ยังไม่ลงชีต" · นับรวมในการตรวจซ้ำด้วย · เลขที่มีในชีตแล้ว = ใช้แถวชีต (ไม่ขึ้นซ้ำ) แต่ผูก `chatId` ให้ปุ่ม "เปิดแชทลูกค้า"
    - วัดกับชีตจริง 11 ต.ค.69: **Code ซ้ำ 931 เลข · เบอร์/ไลน์ซ้ำ 1,217 แถว · 2,923 แถวไม่มีเบอร์/ไลน์ให้เทียบ** (ส่วนใหญ่ QR code)
    - **⚠️ กล่องเตือนตอนจ่ายเบอร์ยังเช็คแค่เบอร์** (สมุดเบอร์ `phonebook`) — ไลน์ซ้ำเห็นในหน้านี้เท่านั้น
    - ตาราง 5 คอลัมน์แรก (ตรวจซ้ำ · ว/ด/ป · เบอร์ · เวลา · Code) ตรึงซ้ายตอนเลื่อนแนวนอน (จอ ≥901px) · โหลดทีละ 150 แถว สูงสุด 600
  - **หน้าเซลล์แบบใหม่ ([seller.html](dashboard/templates/dashboard/seller.html))** — เมนูซ้าย `#sl-rail` 8 หน้า (`SL_NAV` · `pageMode` ·
    `?m=` เปิดหน้านั้นตรง · ค่าเริ่มต้น **งานวันนี้** · ฝังใน iframe แดชบอร์ดแอดมิน = เริ่มที่ "สถิติของฉัน" เหมือนเดิม):
    **งานวันนี้** (ใบจ่ายลีดของฉัน + นับถอยหลังรายงานผล · ยังไม่โทรเลย 30 วัน · รอมาดูรถ/นัด · ดีลค้าง ≤60 วัน · ครบรอบตาม · ลูกค้าไม่ตอบ —
    ลำดับใช้ `followUrgency` ตัวเดิม · ปุ่ม โทร / เปิดแชท / บันทึกผล = `openLeadDetail` เดิม) · **รถเข้าใหม่** · **ลูกค้าของฉัน** (ตารางค้นได้) ·
    **แชทลูกค้า** (`/connect/?embed=1` · **เฉพาะเจ้าของหน้า** `self_view` — แอดมินดูแทนเปิดไม่ได้ เพราะ Connect เป็นของคนที่ login) ·
    **สถิติของฉัน** = หน้าแดชบอร์ดเดิมทั้งหน้า (`renderDashboard`) · **เช็คเบอร์ซ้ำ** · สถานะรถ · ยื่นสินเชื่อ (ของเดิม)
    · `modeBar()` เปลี่ยนจาก dropdown โหมดเป็นหัวหน้า (ชื่อหน้า + นาฬิกา + กระดิ่ง + ธีม) · แอดมินดูแทน = แถบเหลืองบอก
  - **ไม่มี migration** · ไม่มีอะไรส่งออก LINE เพิ่ม (สวิตช์ในหน้ากฎ = ตัวเดิมใน `connect_config`/`leadflow_config`)
  - **เทสต์**: `test_leadflow.py` [19] + **[20] ตรวจลีดซ้ำ Code/เบอร์/ไลน์** (**158 ข้อ** รวม) — ฐานข้อมูล/ไปป์ไลน์/ทีม/ไม้ 2 จากชีต/กันส่งต่อซ้ำ/งานวันนี้ของเซลล์/สิทธิ์/ไม่มี LINE id หลุด ·
    `test_connect.py` 589/589 · ตรวจด้วย Chrome จริง (template ตัวจริงผ่าน test client · Connect stub API · หน้าเซลล์ใช้ข้อมูลชีตจริง อ่านอย่างเดียว):
    กดชื่อเซลล์แล้ว POST ถูก `{id, emp}` / `{mid, emp, base…}` · เปิดแชทจากห้องพักแล้วปุ่มกลับพากลับห้องพัก · สวิตช์กฎยิง config ถูกตัว ·
    ทุกหน้าไม่มี JS error · ไม่ล้นจอ 1590/1180(ฝัง)/390

- **★★★ 11 ต.ค.69 (รอบ 3) — หน้ารวมแชท (Chat Inbox): ขั้นของลีด · นัด · บันทึกการโทร · Run Auto · แจ้งเตือน · AI สรุป · วิเคราะห์**
  ([crm.py](checkout/crm.py) · checkout migration **0035** · เว็บ [connect.html](checkout/templates/checkout/connect.html) + แอปมือถือ (โปรเจกต์แยก `C:\Users\watta\OneDrive\Desktop\Project OXLETAUTO\OxletautoMobile`))
  เจ้าของส่งสเปก 10 ข้อ ("รวมแชททุกช่องทาง … ปุ่มลัด") ถามว่าครบไหม แล้วสั่ง *"ทำหน้าเว็บและ Mobile App ออกมาเลย ใช้ฐานข้อมูลจากที่เรามี"*
  · **ของเดิมใช้ต่อทั้งหมด** (คิว/รับ/โอน/นาฬิกาตอบ/ข้อมูลลีด/จ่ายเบอร์/ไม้ 2/สมุดเบอร์) — ไฟล์ใหม่เพิ่มแค่ที่ยังไม่มี
  - **ขั้นของลีด** (`ChatLead.stage`) ลีดใหม่ → รอติดต่อ → ติดต่อแล้ว → นัดดูรถ → ยื่นไฟแนนซ์ → ปิดการขาย / ไม่สนใจ-ลูกค้าผี · คืนกองกลาง
    · **คนละเรื่องกับคอลัมน์ Z "สถานะลูกค้า"** (Z = ท่าทีลูกค้า · stage = งานเราไปถึงไหน) — เก็บทั้งคู่
    · **ว่าง = ระบบคิดเอง** (`stage_of`: ไม่มีเจ้าของ = ลีดใหม่ · มีเจ้าของยังไม่ตอบหลังรับ = รอติดต่อ · ตอบแล้ว = ติดต่อแล้ว) · คนตั้งแล้วใช้ค่าที่ตั้ง
    · เลื่อนให้เอง **เฉพาะไปข้างหน้า ไม่แตะเคสปิด** (`bump`: บันทึกโทร "คุยได้" → ติดต่อแล้ว · นัดดูรถ → นัดดูรถ)
    · **ไม่สนใจ ต้องเลือกเหตุผล** (`LOST_REASONS` 8 ข้อ) — ที่มาของ "ไม่ซื้อเพราะอะไร" ในหน้าวิเคราะห์
    · คืนกองกลาง/ปล่อยคืนคิว = ขั้น `pool` (`connect._crm_hook` ใน claim/assign/คืนคิวเมื่อเซลล์ลาออก) · มีคนรับใหม่ = ล้าง `pool` ให้ระบบคิด
  - **ความร้อน** (`heat_of` · ร้อน ≥60 / อุ่น ≥35 / เย็น · 0–100 + เหตุผล) คิดจากของที่มีอยู่แล้ว: type (Very Hot 40 … RJ 6) · Z (สนใจมาก +25 ·
    นัด +20 · ลังเล +10 · ไม่รับสาย −10 · **คำเคสเสียชุดเดียวกับแดชบอร์ด = เย็นทันที**) · ขั้น (นัดดูรถ +20 · ไฟแนนซ์ +25) · ลูกค้าคุยล่าสุด
    (≤1 วัน +20 · >7 วัน −15 · >14 วัน −25) · มีเบอร์/ไลน์ +8 · รอเราตอบ +5 · **ไม่มีช่องให้กรอกเพิ่ม** · เคสปิด = ไม่มีความร้อน
  - **นัดหมาย** (`ChatFollowup`: นัดติดตาม / นัดดูรถ · ทำแล้ว / ยกเลิก) · **บันทึกการโทร** (`ChatCall`: คุยได้/ไม่รับสาย/ปิดเครื่อง/เบอร์ผิด/โทรกลับ/อื่นๆ
    + หมายเหตุ + **รูปหลักฐาน** ≤6 รูป) — ระบบรู้เองไม่ได้ว่าโทรจริงไหม เซลล์จดเอง · แนบรูปแล้ว "แจ้งหลักฐานการโทร" = ส่งแล้ว (ถ้าคนยังไม่ตั้งเอง)
    · รูปเก็บ **ดิสก์ VPS `media/connect/<ChatOwner.id>/<ชื่อสุ่ม>`** (`save_proof` · รูปเท่านั้น ≤10MB) · `_clean_media` รับเฉพาะไฟล์ในโฟลเดอร์ของลูกค้าคนนั้น
    (กันอ้างไฟล์อื่น/`..`) · **ลูกค้าถูกลบ (60 วัน) = โฟลเดอร์ถูกลบตามวันละครั้ง** (`cleanup_files`) · ทุกอย่างจดลง `ChatOwnerLog` (STAGE/APPT/CALL/SUMMARY ใหม่)
  - **ใครเคยดูแล** (`past_owners` จากประวัติ — ชื่อเก็บเป็นข้อความ **ลบพนักงานแล้วชื่อยังอยู่** มีเทสต์) · **สถานะไฟแนนซ์** = เคสจองในชีตยอดขายที่เลขลีดตรง
    (ไม้ 2 ใช้เลขเดิม) · **⚠️ `_booking_map` อ่านเฉพาะผลแดชบอร์ดที่ cron อุ่นไว้ ห้ามคำนวณสด** (เปิดแชททุก 6 วิ · คำนวณสด ~8 วิ — มีเทสต์ยืนยันว่าไม่เรียก
    `precompute_dashboard`) · **รถพร้อมขายที่ตรง** = ผลจับคู่ใน KV `leadflow_needs` (คำนวณทุก 30 นาทีอยู่แล้ว)
  - **★ Run Auto อยู่ที่ "ห้องพัก Lead → รอจ่ายเบอร์" เท่านั้น — หน้าแชทไม่มี** (11 ต.ค.69 รอบ 4 · เจ้าของ *"อันนี้มันหน้าแชท ให้แอดมินตอบแชทได้เท่านั้น
    ไม่มีการ run auto ใดๆ ทั้งสิ้นในหน้า chat"*) · รอบแรกผมวางไว้แท็บ "รอรับ" ของกล่องแชทรวม (เว็บ + แอป) และให้แค่ **โอนแชท** → ถอดออกทั้ง 2 ที่
    · ตอนนี้ = **กดปุ่มกรอบชมพู (คิวถัดไป) ให้ทุกใบที่รอ** · ขั้น 1 **ดูแผนก่อน ไม่เขียนอะไร** (`crm.room_plan()` ← `crm {action:"auto_plan", src?}`)
    → ติ๊กออกใบที่ยังไม่อยากจ่าย → **"จ่ายตามแผน N ใบ"** (ถามยืนยันพร้อมบอกว่าส่งเข้าห้องไหนกี่ข้อความ) → หน้าเว็บยิง **endpoint เดิมทีละใบ**
    (`assign_lead {id, emp}` / `park_assign {mid, emp, base, admin, reject}` — ด่านกันเลขซ้ำ/มีเลขแล้ว/ส่งใบเข้ากลุ่ม+แท็ก ตัวเดียวกับกดเอง)
    · แผนครอบทั้งแชท LINE/FB ที่ให้เบอร์/ไลน์แล้ว (`to_code`) + ใบร่างกลุ่ม ADMIN เก็บ Lead · เรียงรอนานสุดก่อน · **รอบละไม่เกิน `AUTO_LIMIT`=30**
    · กติกาเลือกคน: **แชทที่มีเซลล์ดูแลอยู่ (ยังทำงาน) = คนเดิม** → **เบอร์เคยเป็นลีดของใคร (สมุดเบอร์) = คนนั้น** (ติดป้ายเบอร์ซ้ำ ·
      เจ้าของเดิมลาออก/ไม่อยู่ในทะเบียน = **ข้าม ให้แอดมินเลือกเอง**) → ไม่งั้น **คิวจ่ายวน** (`LF.rr_candidates` · เพดาน `cap_day` · คนได้ใบน้อยสุดวันนี้ก่อน
      นับรวมที่แผนรอบนี้จัดให้) · ไม่มีใครว่าง = ข้ามพร้อมเหตุผล · ข้ามลูกค้าจำลอง/บัญชีพนักงาน · ตัวกรองช่องทางของห้องพักใช้กับแผนด้วย
    · จ่ายวนอัตโนมัติ (สวิตช์ `auto_assign` ใน `leadflow_config`) ยังแยกอยู่ในหน้ากฎ (ปิดโดยปริยาย) — Run Auto คือแอดมินสั่งเองทีละรอบ
    · เซลล์ **คืนกองกลาง** ลูกค้าของตัวเองได้ (ใส่เหตุผล · จดประวัติ)
    · ⚠️ แก้ไปพร้อมกัน: `assign_lead` เคย **500** เมื่อเลขรันที่ออกได้สั้นกว่า 3 หลัก (`_CODE_RE` ไม่ match → `.group` บน None) — เจอเฉพาะระบบว่าง
      (prod เลขรัน ~8,400) · ตอนนี้ type ว่างไว้แทนการพัง · **ระบบที่ยังไม่มีใบจ่ายลีดเลย เลขรันเริ่ม 1 แล้วตัวนับอ่านเลข <3 หลักไม่ออก = ใบที่ 2 ชนเลขซ้ำ**
      (ชุดทดสอบใส่ใบตั้งต้น NLD10-8400 กันไว้ · ของจริงไม่เจอ)
  - **ดึงคืนเมื่อไม่ตอบ** `connect_config.pull_min` (**0 = ปิดโดยปริยาย** · 5–240) = รับแล้วไม่ตอบจนเลยเส้นตาย + เกิน N นาทีหลังรับ → คืนคิว
    · **⚠️ อย่าเปิดจนกว่าทีมจะเลิกตอบในแอป LINE OA Manager** (LINE ไม่ส่งกลับมา = ระบบเห็นว่าไม่ได้ตอบ → ดึงลูกค้าที่ตอบไปแล้วคืนผิดๆ) · สวิตช์อยู่หน้า "กฎและเส้นทาง"
  - **แจ้งเตือน** (`alerts` · กระดิ่งบนหัวหน้า Connect ทุก 30 วิ + หน้าแจ้งเตือนในแอป): ลูกค้าใหม่รอรับ (แอดมิน/ทีมเวร) · ของฉันเลยเวลา/ใกล้หมด 2 นาที ·
    นัดวันนี้ (เลยนัด = แดง · แอดมินเห็นทุกนัดพร้อม @ชื่อ) · ลูกค้าเงียบ 3/5/7+ วัน · รถใหม่ตรงลูกค้า · **แอดมินไม่โชว์เลยเวลารายคน** (เหตุผลเดียวกับที่ถอดแท็บเลยเวลา 7 ต.ค.)
    · **เตือนนัดทาง LINE แชทส่วนตัวเซลล์ 30 นาทีก่อน = `appt_line` ปิดโดยปริยาย** (ครั้งเดียว · `reminded_at`) · แอป Expo Go ส่ง push ไม่ได้ → แจ้งเตือนอยู่ในแอป
  - **AI สรุปแชท** (`ai_draft` · Gemini ตัวเดียวกับโค้ชเซลล์ · กดเองเท่านั้น): ร่างสรุป + ขั้นที่แนะนำ + วันควรติดตาม → **เซลล์ตรวจ/แก้แล้วกดบันทึกเอง**
    (ร่างไม่บันทึกอัตโนมัติ · ปุ่ม "ใช้ขั้นนี้" / "สร้างนัดติดตามนี้" แยก) · **ปิดบังเบอร์/ไอดีไลน์ก่อนส่งให้ AI** (`mask` — มีเทสต์ตรวจ body ที่ส่งออก) ·
    จำผล 30 นาทีต่อแชทเดิม · ตอบไม่เป็น JSON / ขั้นที่ตั้งไม่ได้ = ไม่ใช้ · ไม่มี `GEMINI_API_KEY` = ปุ่มไม่โผล่ พิมพ์สรุปเองได้
  - **ตัวกรอง** (รายชื่อ · เว็บ + แอป): ปุ่มลัด รอเราตอบ · ติดตามวันนี้ · ลูกค้าไม่ตอบกลับ (เราส่งล่าสุด >24 ชม.) · เงียบ 3+/7+ · ร้อน · รถใหม่ตรง +
    แผง "ตัวกรองเพิ่ม" ขั้น · ความร้อน · เหตุผลไม่ซื้อ · รุ่นรถ · งบ (จาก `CustomerNeed.budget_max` — ลูกค้า LINE) · ช่วงวันที่คุยล่าสุด
    · ขั้น/ความร้อน/รถตรง คิดใน Python (ค่าที่คำนวณ · อ่านสูงสุด 1,500 แถวแล้วกรอง) · **ตัวกรองใช้เฉพาะหน้ากล่องแชทรวม** (ห้องพัก Lead ใช้ตัวโหลดเดียวกันแต่ไม่กรอง)
    · ช่องวันที่ใช้ `change` ไม่ใช่ `input` (Chrome ยิง input ตอนเลื่อนเดือน — บทเรียน 4 ต.ค.) · แผงวาดครั้งเดียว ไม่วาดทับตอนรายชื่อรีเฟรช 8 วิ
  - **ป้ายในรายชื่อ**: ขั้น (ไม่ติด "ลีดใหม่") · ร้อน/อุ่น · นัด/ดูรถ + เวลา (เลยนัด = แดง) · เงียบ N วัน / ลูกค้าไม่ตอบ · รถใหม่ตรง N
  - **แผงขวาของแชท** (บนสุดของข้อมูลลูกค้า): ขั้น (ปุ่ม) · ความร้อน+เหตุผล · ไฟแนนซ์ · รถตรง · นัด · โทร · สรุป · ใครเคยดูแล
    · ที่พิมพ์ค้างไว้เก็บใน `S.apptDraft/callDraft/sumDraft[id]` (แผงวาดใหม่เมื่อข้อมูลเปลี่ยน ห้ามทำให้ที่พิมพ์หาย) · หัวแชทเซลล์มีปุ่ม **คืนกองกลาง**
  - **วิเคราะห์** (หน้าแดชบอร์ดทีม · `insights` 7/30/90 วัน): ร้อน/อุ่น/เย็น · จำนวนตามขั้น · ตามช่องทาง (ติดต่อแล้ว/นัด/ไฟแนนซ์/ปิด/ไม่สนใจ/% ปิด) ·
    ไม่ซื้อเพราะอะไร · ตาม ADS · **รายชื่อ "ไม่ต้องการ" CSV** (ไม่สนใจ + Z เคสเสีย · มีเบอร์ → ไว้ตัดออกจากกลุ่มเป้าหมายโฆษณา · **แอดมินเท่านั้น** ·
    จดใน `dash_event_log` kind=`export`) · ทีมสถิติ (ชีต) โหลดไม่ได้ ส่วนวิเคราะห์ยังโชว์
  - **แอปมือถือ**: รายชื่อมีปุ่มลัดตัวกรอง + ขั้น · ป้ายเดียวกับเว็บ · **ไม่มี Run Auto** (หน้าแชทมีไว้ตอบแชทเท่านั้น) · กระดิ่งบนหัว → หน้า `alerts` (กดเรื่อง = เปิดแชท / ตั้งตัวกรองให้) ·
    หน้าแชทมีบรรทัด "ขั้น · ความร้อน · นัด" + ปุ่ม **งาน/นัด** → หน้า `lead/[id]` (ขั้น + เหตุผลไม่ซื้อ · นัด: เลือกวัน 14 วัน × เวลา · โทร: ผล + หมายเหตุ +
    ถ่าย/เลือกรูปหลักฐาน · สรุป + AI ร่าง · ใครเคยดูแล · คืนกองกลาง) · **ไม่มี API ใหม่สำหรับแอป** (ใช้ตัวเดียวกับเว็บผ่าน Bearer)
  - **ยังไม่ได้ทำ**: แชท TikTok/IG จริง (ข้อ 1 · รอ API) · push จริง (ต้องออกจาก Expo Go) · จัดเกรด A/B/C แยกจากความร้อน · ส่งรูปหาลูกค้า ·
    ขั้นของลีดยังไม่ลงชีต (ตามที่สั่งไว้ 4 ต.ค. — ไม่เขียนชีตลีดจากข้อมูล Connect จนกว่าเจ้าของตัดสิน)
  - **เทสต์**: `python scripts/test_crm.py` (**145 ข้อ** · ปลอมที่ `requests` = Gemini/LINE · ไม่ปลอมฟังก์ชันของเรา) — ขั้นคิดเอง/ตั้งเอง/เลื่อนเอง ·
    คืนกองกลาง/รับใหม่ · ความร้อน · นัด (วันผ่านแล้ว/ชนิดมั่ว) · หลักฐาน (ไม่ใช่รูป/ใหญ่เกิน/ไฟล์คนอื่น/`..`) · ลบโฟลเดอร์ของลูกค้าที่ถูกลบ · ใครเคยดูแล (ลบพนักงานแล้ว) ·
    ตัวกรองทุกตัว · Run Auto ห้องพัก Lead (แค่แผนต้องไม่เขียนอะไร/เจ้าของเดิม/เบอร์ซ้ำ/เจ้าของเดิมลาออก/เพดาน/ไม่มีคิว/กรองช่องทาง/จ่ายตามแผนผ่าน endpoint เดิม) · ดึงคืน (ปิด/เปิด/ตอบแล้วไม่ดึง) · แจ้งเตือน (เซลล์/แอดมิน/นอกเวร) · AI (ไม่มีคีย์/ปิดบังเบอร์/
    ไม่บันทึกเอง/จำผล/ตอบผิดรูป) · เตือนนัด LINE ครั้งเดียว · วิเคราะห์ + CSV · ไฟแนนซ์ไม่คำนวณสด · **สิทธิ์ผ่าน test client จริง + ไม่มี LINE id หลุด**
    · `test_mobile_api.py` [5b] (แอปเรียกด้วย token + CSRF เปิด) · ตรวจ Chrome จริง (template + **API ตัวจริงทุกตัว**ผ่าน route · จอ 1590/1180/390 · ไม่มี JS error ·
    ไม่ล้นจอ) · แอป `tsc` + `expo lint` + bundle iOS ผ่าน

**⚠️ ต้องทำก่อนใช้จริง (ระบบพร้อม แต่ยังเปิดใช้จริงไม่ได้จนกว่าจะทำครบ)**
1. `migrate` (checkout **0025** · เช็คชื่อในแอป = **0037** · งานจ่ายเบอร์ = **0034** · ลีดภายนอกจากห้องพัก Lead = **0029** · Facebook ใน Connect = **0030** · ส่งใบเข้ากลุ่มจ่ายเบอร์ = **0031** · สถานะลูกค้า (จับ keyword) = **0032** · ยังไม่อ่าน = **0033** · หน้ารวมแชท (ขั้น/นัด/โทร) = **0035** · index แชทลูกค้า (sender_id) = **0036** · หน้าคอมเมนต์ = **0038** · ประเภทลูกค้าในคอมเมนต์ = **0039** + **0040**)
2. **`manage.py checkout_config --customer-chat on`** — ไม่เปิด = ลูกค้าที่ทักเข้ามาไม่เข้า Connect (หน้าเว็บขึ้นแถบแดงบอก)
3. **`manage.py checkout_config --reply on`** — ยังล็อกไว้ตามที่เจ้าของสั่ง ("อย่าเพิ่งส่งข้อความหาลูกค้า")
   ระหว่างล็อก ดู/รับ/โอนได้ แต่กดส่งไม่ได้ (หน้าเว็บบอกเหตุผล)
4. **ถอดสิทธิ์ LINE OA Manager ของเซลล์** — LINE ไม่ส่งข้อความที่ตอบจากแอปนั้นกลับมา ตอบที่นั่น = แชทหายจากระบบ
   และนาฬิกา 5 นาทีไม่หยุด (จะขึ้นเลยเวลาทั้งที่ตอบแล้ว)
5. ตั้งเวรวันแรกในหน้า Connect → ตั้งค่า ("วันนี้เป็นเวรของ")

**⚠️ ข้อจำกัดที่รู้อยู่ (ยังไม่ได้ทำ)**
- ~~รูป/ไฟล์ที่ลูกค้าส่ง ยังเปิดในระบบไม่ได้~~ → **เปิดได้แล้ว 11 ต.ค.69** (ดูหัวข้อ "รูป/ไฟล์ที่ลูกค้าส่งในแชท" ข้างล่าง)
  · **เซลล์ยังส่งรูปกลับไม่ได้** — งานถัดไปที่สำคัญที่สุด (ลูกค้าส่งรูปรถ/บัตรบ่อย)
- **การตอบจากระบบใช้ push = นับโควต้าข้อความรายเดือนของ LINE OA** — เปลี่ยนให้ทุกคนตอบผ่านระบบ ยอดจะเพิ่มมาก ต้องเช็คแพ็กเกจ
- **ตอบลูกค้าด้วยบัญชี OxletAuto (ตัวรับ)** ตามที่ลูกค้าแอดไว้ (`chat._channel_for`) — เป็นข้อยกเว้นของนโยบาย
  "ส่งออกจากบอทตัวส่งบัญชีเดียว" (ต้องเป็นแบบนี้ ไม่งั้นส่งไม่ถึงลูกค้า)
- แชทลูกค้า + แถว Connect **หายเมื่อลูกค้าเงียบเกิน 60 วัน** (`CUSTOMER_CHAT_KEEP_DAYS`) — ถ้าอยากเก็บแชทเซลล์ไว้นานกว่านี้
  ต้องตัดสินใจเรื่อง PDPA ก่อน
- ยังไม่ผูกลูกค้า Connect กับลีดในชีต / ยังไม่มีข้อความสำเร็จรูป (★ 17 ต.ค.69 มีแล้ว) / ยังไม่มีแชท Facebook ในหน้านี้

**★ สถานะจริงบน prod (3 ต.ค.69 22:00)**: deploy `f652db2` + migrate 0025 + restart 21:58 → ลูกค้าคนแรกเข้าคิวเอง 21:59
· เปิด `store_customer_chat` + `reply_customer` แล้ว (= **ตอบลูกค้าจริงได้แล้ว**) · ยังไม่มี `connect_config` (ใช้ค่าตั้งต้น)
- **ใครรับลูกค้าได้ ขึ้นกับ "ตำแหน่ง" ในทะเบียนพนักงาน** (วัดจริง): ทีม A = มัท เฟิร์ส โอ๊ต · ทีม B = นวล บิว อุ้ม เก้า เหล
  (+แซน ผ่านตั้งค่าเซลล์ เพราะทะเบียนเขียน "ทีมโปรดักชัน") · **ทีม C (ทู นิด ภู) + เทเลเซลล์ (เจ) ไม่อยู่ในเวร**
  = รับลูกค้าใหม่เองไม่ได้ แอดมินโอนให้ได้ · ⚠️ เหล = ทีม B ในทะเบียนแต่ "เลิกใช้" ในแดชบอร์ดขาย (ต้องให้เจ้าของเคาะ)
- **★ 9 ต.ค.69 เทเลเซลล์ "ใหม่" ไม่อยู่ในรายการโอน (เจ้าของแจ้ง)** — ตำแหน่งในทะเบียนเป็น "ออฟฟิศ บ้านเก่า"
  และไม่อยู่ในตั้งค่าเซลล์ (เจ โผล่ได้เพราะอยู่ในตั้งค่าเซลล์ทีม ADMIN) · **ทางแก้ = ตั้งตำแหน่งเป็น "เทเลเซลล์"
  ในหน้าพนักงาน** → `team_id_of` = ADMIN (รับ เทเลเซล/เทเลเซลส์/telesale ด้วย) · ตารางเช็คชื่อมีกลุ่ม "เทเลเซลล์"
  ต่อจากออฟฟิศ บ้านเก่า (`TEAM_ORDER`) · **ไม่ใช้ `TELE_USER_IDS`** (ชีตตั้งค่าเทเลเซลล์มี 6 คนรวมแอดมินออฟฟิศ = เกิน)
- **`off_duty_reason()`** แยกเหตุผล 3 แบบ: ไม่มีทีม / ทีมไม่อยู่ในเวร / ไม่ใช่วันเวร (+บอกวันเวรถัดไปจริง)
  — เดิมตอบแบบเดียวว่า "รอวันเวรของทีม" ซึ่งทีม C จะรอวันที่ไม่มีวันมาถึง

**เทสต์**: `python scripts/test_connect.py` (**589 ข้อ** · ⚠️ รันด้วย Python หลักของเครื่อง — `.venv` เป็น Django 5.0 ซึ่งพังกับ Python 3.14 ตอน test client คัดลอก context — ใบตาม pattern ของเจ้าของทุกบรรทัด · ช่องทาง/ไลฟ์ที่คนพิมพ์จริง → คำของชีต · ส่งใบเข้ากลุ่มจ่ายเบอร์จริง [30] (ห้องตามเลข R · ซ่อนห้องบอทเดิม · แท็กไอดีฝั่งบอทตัวส่ง ·
ไม่อยู่ในกลุ่ม = พิมพ์ชื่อ · LINE ปฏิเสธแท็ก = ส่งซ้ำ · ส่งไม่สำเร็จยังจ่ายในระบบ + ส่งอีกครั้ง · ไม่ส่งซ้ำ · ลูกค้าจำลอง/บัญชีทดสอบไม่ส่ง ·
FB เก็บข้อมูลเท่านั้น · ใบเก็บลงคลังแชทกลุ่ม · ไม่มี LINE id หลุด) · ใบเคสรับซื้อในกลุ่มเคสHOT (อ่านใบ · เบอร์/ชื่อ+ช่องทาง · ผู้รับจากแท็ก/ชื่อกลุ่ม · ใบขายชนะ) · จับใบจ่ายลีดในกลุ่มเอง + จ่ายให้ใคร (ปุ่มในระบบ/ใบในกลุ่ม · แท็กกำกวมไม่เดา · cron กวาดให้) · ตอบอัตโนมัติของเพจไม่ปิดรอบ · Messenger webhook (verify · ไม่มี secret = 503 · ลายเซ็นผิด = 403 · ลูกค้าเดิมไม่ยิง API · echo หยุดนาฬิกา · ห้องชั่วคราวย้ายเข้าห้องจริง · ดึงสำรองเช็คข้าม worker) · ห้องพักเฉพาะลูกค้าที่ให้เบอร์/ไอดีไลน์ (ไอดีหลังเราขอ · ไม่เดาคำลอยๆ · เก็บตกแชทเดิม) · พนักงานทักบัญชีลูกค้าขึ้น Connect (บอทแจ้งเตือนไม่ขึ้น) · Facebook ในคิวเดียวกับ LINE (ซิงก์ · รอบรอ · ตอบใน FB หยุดนาฬิกา · โหมดทดสอบ · 24 ชม. · PSID ไม่หลุด) · จ่ายเบอร์ลีดภายนอก (เลขรันร่วม · กันซ้ำ · ซ่อน · ลบ 90 วัน) · ห้องพัก Lead (ใบร่าง→ใบจริง · R ไม่นับ · โพสต์ซ้ำ · เซลล์ไม่เห็น) · แท็บจ่ายเบอร์ (ลูกค้าเก่าก่อนเปิด Connect ไม่นับ · ไม่ต้องจ่ายเบอร์ · เซลล์ขอแท็บนี้ไม่ได้) · เวร/สลับเวร/3 ทีม · เส้นตายนอกเวลา · ค่าตั้งผิดต้องฟ้อง ·
ใครกดก่อนได้ไป · ไม่ใช่วันเวรรับไม่ได้ · ลูกค้าติดเจ้าของเดิม · เลยเวลาแจ้งครั้งเดียว · โอน/ปล่อย/ลาออกคืนคิว ·
webhook → เข้าคิวเอง · **สิทธิ์ผ่าน test client จริง** · ตอบผ่าน API ยิง LINE จริง (ปลอมที่ `requests`) ·
**สแกนทุก endpoint ว่าไม่มี LINE user id หลุด** · โปรไฟล์: จับเบอร์ 7 แบบ · รูปไม่ลง LineProfile · พนักงานไม่มีรูป ·
เติมรูปลูกค้าเก่า/ดึงไม่ได้เว้น 1 วัน · คิวรอรับไม่ส่งเบอร์ออก · โหมดทดสอบ: สลับเซลล์จริงไม่ได้ · ลูกค้าจำลองไม่ยิง LINE ·
ล้างแล้วคืนลูกค้าจริงเข้าคิว · ข้อมูลลีด: เติมจากแชท/ใบจ่ายลีด · ไม่ทับที่คนแก้ · ใบย่ออ่านกลับได้ · คิวรอรับไม่ได้ข้อมูลลีด ·
จ่ายเบอร์: อ่านเลขเดือน 2 หลัก · ตัวหน้าตาม type/ช่องทาง · เลขรันต่อจากใบล่าสุด (ไม่นับ R) · เซลล์กดไม่ได้ · ไม่มีคำขอออกนอกระบบ ·
มีเลขแล้วไม่ทับ · เลขซ้ำ/ผิดรูปแบบปฏิเสธ · โอนไม่สำเร็จย้อนธุรกรรม ·
dropdown: Sheets API ปลอม (หัวตารางสลับตำแหน่ง · แท็บเดือนหน้าต้องไม่ถูกเลือก · แบบอ้างช่วงเซลล์) · ไม่ขอแถวลูกค้า ·
สาขาตามเซลล์ ≥90% · อ่านไม่ได้คงชุดเดิม/เว้น 15 นาที · รุ่นกำกวมไม่เดา · ค่าเก่าของระบบแก้ให้ตรงชีต แต่ค่าของคนไม่แตะ ·
ลูกค้าจำลองไม่ดึงใบจ่ายลีดของจริง)
· ตรวจ UI ด้วย Chromium จริง (จอคอม/มือถือ 390px ·
แท็บในแดชบอร์ด · ไม่มี JS error · ไม่ล้นจอแนวนอน)

### 🤖 จ่ายลีดขายจากแชทอัตโนมัติ + ตัวจับ "จ่ายแล้วหรือยัง" — [autochat.py](checkout/autochat.py) · [leadmatch.py](checkout/leadmatch.py) · 18 ต.ค.69
เจ้าของ *"ไม่ต้องการให้แอดมินมาเก็บแล้ว … อยากมั่นใจว่ามันไม่มีข้อมูลส่วนไหนหลุดหรือซ้ำกับที่เราหรือแอดมินเก็บมาแล้ว"* → *"ขอเอาหลีดขายก่อน"*
- **ปัญหาที่ต้องแก้ก่อน**: ตรวจแชท 7 วัน (124 รายที่ให้เบอร์/ID LINE) — แอดมินจ่ายแล้ว 90 แต่ตัวจับเดิม (`find_slip` เบอร์+ชื่อไลน์ · `sheet_match` เบอร์)
  **รู้เองแค่ 3** (ลูกค้าเพจส่วนใหญ่ให้ ID LINE/รูป QR ไม่ให้เบอร์) → เปิดจ่ายเองด้วยตัวจับเดิม = เลขซ้ำ ~87 ราย
- **[leadmatch.py](checkout/leadmatch.py)** — `lid_core()` (ID LINE → ตัวเทียบ: ตัด @ . _ - ~ · ตัวเล็ก · "QR code"/Line@/เลขล้วน/<4 ตัว = "" ·
  `line.me/ti/p/~xxx` = xxx) · `name_key()` (NFC · ตัดอีโมจิ/ช่องว่าง/"Oxlet Auto") · `index()` = ใบจ่ายลีด (ห้องจ่ายเบอร์) + ใบร่าง (กลุ่มพักลีด)
  21 วัน จำ 60 วิ · `find()` → (ใบ, ตรงด้วย, strong) · `slip_by_lid` · `sheet_by_lid` (สำเนาชีตลีด `_sheet_lid_index` จำ 10 นาที ·
  อ่านช่องเบอร์ด้วย `console_data.line_ids` · กติกา "เลขที่คนอื่นถืออยู่ไม่ก๊อป" เหมือน `sheet_match`) · `lid_taken(days=0 = ทุกช่วง)` ·
  `name_hint` · `chat_name_taken`
  - **★ เทียบ ID LINE ด้วยตัวเทียบเสมอ ห้ามค้นข้อความ (`icontains`)** — "abc.def99"/"abc_def99"/"@ABCdef99" คือไอดีเดียวกัน
    · และห้ามเทียบแบบ "มีคำนี้อยู่ข้างใน" — ตรวจด้วยมือรอบแรกใช้ substring แล้วบอกว่า #551 เป็นลูกค้าเก่า 5 เลข
      ทั้งที่ ID ยาว 4 ตัวไปโผล่กลางไอดีคนอื่น (เทียบตรงทั้งคำ = ลูกค้าใหม่)
- **`connect.autofill`** (เปิดแชท/`slip_sweep`/autochat): ไม่เจอใบด้วยเบอร์ → **ลองด้วย ID LINE** · ไม่เจอในชีตด้วยเบอร์ → **ลองด้วย ID LINE** ·
  ยังไม่มีเลข → **ตรงแค่ชื่อ = `auto["_maybe"]`** `{code, at, tag, how}` (ชื่อซ้ำกันได้ = ไม่ใส่เลขให้ · ช่องทางในใบต้องไม่ขัด `_channel_fits`)
  · **`auto["_contact_at"]`** = เวลาที่ลีดได้ช่องทางติดต่อครั้งแรก (`_stamp_contact` ใน capture_contact/capture_qr/autofill ·
  **ใช้เวลาข้อความล่าสุดของลูกค้า ไม่ใช่ตอนนี้** — ตัวเก็บตกแชทเก่าจะได้ไม่ดูเหมือนลีดใหม่) · ลีดที่มีเบอร์ก่อนแล้ว = ไม่จด
- **สวิตช์ `leadflow_config.auto_chat`** = `off` (ค่าตั้งต้น) / `observe` (จดอย่างเดียว ไม่ออกเลข ไม่ส่ง LINE) / `on` (จ่ายจริงผ่าน `assign_lead`)
  · **เปลี่ยนโหมด = จด `auto_chat_since` ใหม่** → ดูเฉพาะลูกค้าที่ให้ช่องทางติดต่อหลังเวลานั้น (`_contact_at ≥ since`) · รอ `auto_after_min` (ตัวเดียวกับจ่ายวนใบร่าง)
  · ตั้งที่ Connect → กฎและเส้นทาง (ปุ่ม 3 ตัว) หรือการ์ดงานจ่ายเบอร์ (dropdown + การตัดสินล่าสุด 15 รายการ · กดเลขแชท = เปิดแชท)
- **ตัดสิน (`decide`) เรียงตามนี้**: จำลอง/พนักงาน = ข้าม → autofill → **ได้เลขแล้ว = "แอดมินจ่ายแล้ว"** → รับซื้อ/ไม่ต้องจ่ายเบอร์ = ข้าม →
  `_maybe` = ข้าม → **ใบร่างในกลุ่มพักลีดตรง (เบอร์/ID/ชื่อ) = ข้าม** (จ่ายทางห้องพัก) → **แชทอื่นของลูกค้าคนเดียวกัน** (เบอร์/ID LINE · 30 วัน ·
  มีเลขแล้ว หรือแชทนั้นเก่ากว่า) = ข้าม → **ลูกค้าเก่า** (`dup_info` สมุดเบอร์ · ID LINE เคยได้เลขในแชท/ห้องพัก/ชีต ทุกช่วง) = ข้าม →
  เซลล์: เจ้าของแชทเดิม ไม่งั้นคิวจ่ายวน (นับที่รอบนี้จัดไปแล้ว) → ตัวหน้า `suggest_prefix`
- **รอบ (`run`)**: `leadflow.tick` → `autochat.tick_bg` (thread · advisory lock `7_406_067`) · ตรวจไม่เกิน 25 แชท · แชทเดิมตรวจซ้ำทุก 10 นาที ·
  **on: ไม่เกิน 3 ใบ/รอบ · เฉพาะเวลาทำการของ Connect** · จด KV `autochat_log` (400 รายการ · เลขแชท ไม่มีชื่อ/เบอร์) · `autochat_state` · `autochat_last`
  · ⚠️ observe ก็ **เขียนเลขที่จับคู่ได้ลง ChatLead** (เหมือนเปิดแชท) — ไม่ใช่การจ่าย แค่ทำให้ห้องพัก Lead ไม่ค้างลีดที่จ่ายแล้ว
- **จ่ายวนใบร่าง (`_auto_assign`) กันซ้ำเพิ่ม**: ID LINE เคยได้เลข · ชื่อ Account ตรงกับแชทที่ระบบเพิ่งจ่าย (2 วัน) = ข้าม
- **กล่องจ่ายเบอร์ในแชท**: ป้าย "ชื่อตรงกับใบจ่ายลีด X — อาจจ่ายไปแล้ว" + "ID LINE นี้เคยได้เลข X" (`codeHelp.maybe` / `lidDup`)
- **`manage.py autochat`** (สถานะ) · `--backtest --days 7` (ถ้าเปิดตอนนี้จะทำอะไร · **ย้อนธุรกรรมทิ้ง ไม่เขียนอะไร**) · `--mode off|observe|on` ·
  `--run` · `--report --days 7` (เทียบสิ่งที่ระบบตัดสินกับที่แอดมินทำจริง: จ่ายเซลล์เดียวกัน/คนละคน/ยังไม่มีใครจ่าย) · `--out ไฟล์`
- **ทดลองย้อนหลังกับข้อมูลจริง 18 ต.ค.69 (7 วัน · อ่านอย่างเดียว)**: แชทลีดขายที่ยังไม่มีเลข 112 → **จับได้ว่าแอดมินจ่ายแล้ว 52** (ใบตรงเบอร์/ID LINE) ·
  **จะจ่าย 17** (= ลีดใหม่จริงที่ไล่ด้วยมือทั้ง 16 ราย + #551) · ข้าม 43 (ตรงแค่ชื่อ 36 · มีใบร่าง 6 · ลูกค้าเก่า 1)
  · "ตรงแค่ชื่อ" ส่วนใหญ่คือจ่ายแล้วจริง (ลูกค้าเพจส่ง QR ใบเขียน "QR code") — ระบบไม่จ่ายซ้ำ แต่ก็ไม่ได้ยืนยันเอง
- ไม่มี migration · **เทสต์** `python scripts/test_autochat.py` (69 ข้อ · ปลอมที่ `requests`) · test_connect/leadflow/crm/park_qr/lead_code/chatplus/mobile ผ่านเหมือนเดิม

### 📥 เก็บลีดอัตโนมัติ → เลขรันต่อจากเดิม → ใบลงกลุ่ม "ADMIN เก็บ Lead" — [autolead.py](checkout/autolead.py) · 19 ต.ค.69
เจ้าของ *"เก็บ Lead auto ลง Line กลุ่มและลงระบบของเราเพื่อให้แอดมินจ่ายต่อก็พอ · อย่าเพิ่งให้มันจ่าย Lead auto · อยากให้รันต่อจากเดิมได้เลย code number"*
(เลือกกลุ่ม **ADMIN เก็บ Lead** — ถามแล้ว)
- ลูกค้าให้เบอร์/ID LINE (`_contact_at`) **หลังเปิดสวิตช์** + รอ `after_min` 2 นาที → `autofill` → **จองเลขรัน** (`last_running()+1` ใน `code_lock`
  · ตัวหน้าตาม `suggest_prefix`) เก็บที่ `ChatLead.auto["_autolead"]` = `{code, num, month, base, admin, ok, error, room, tries}`
  · **ไม่ใส่ช่อง code** → แชทยังอยู่ในห้องพัก Lead → ส่งใบเลขเต็ม **ไม่แท็กเซลล์** ลงกลุ่ม (`weblead.park_room` · บอทตัวส่ง) +
  เก็บ `GroupChat` (`message_id` ขึ้นต้น `auto-lead-` · `extra.source="autolead"`)
- **ไม่จ่ายเซลล์เอง** — แอดมินกดชื่อเซลล์ในห้องพัก (ปุ่มเดิม) → `assign_lead` **ใช้เลขที่จองไว้** (+ตัวหน้าเดิมถ้าไม่ส่ง base) → ใบ + แท็กเข้าห้องจ่ายเบอร์ → ลงชีต
  · `code_for_assign`: ใบในห้องจ่ายเบอร์ใช้เลขนี้ **กับลูกค้าคนเดียวกัน** แล้ว (แอดมินคัดลอกใบไปแท็กเอง · `room_use.same`) = **ห้ามจ่ายซ้ำ** ·
    ใช้กับลูกค้าคนอื่น / `code_taken` = ออกเลขใหม่ + บอกในข้อความ
- `last_running()` นับเลขที่จองไว้ (`reserved_nums`) · กลุ่ม ADMIN เก็บ Lead = kind admin ไม่ใช่ห้องจ่ายเบอร์ → ใบนี้ไม่ลงชีต/ไม่ถูกนับในกลุ่ม
  · ⚠️ แอดมินออกเลขมือในห้องจ่ายเบอร์ต้องดูเลขในกลุ่ม ADMIN เก็บ Lead ด้วย
- ใบ `auto-lead-` ไม่ขึ้นเป็นใบร่างซ้ำ (`leadpark._scan`) · ไม่ใช้จับคู่ (`leadmatch.index`) · แอดมินพักใบร่าง/โพสต์ใบเองแล้ว (เบอร์/ID/ชื่อ) หรือ `_maybe` = ไม่ส่ง (จด `{skip}`)
- ส่ง LINE ไม่สำเร็จ = เลขยังจอง · ส่งใหม่ทุก 5 นาที ≤5 ครั้ง · หน้าเว็บ: ป้าย "จองเลขแล้ว · รอจ่ายเซลล์" (การ์ดห้องพัก/รายชื่อ `row_json.autoCode`) + กล่องจ่ายเบอร์บอกเลขที่จองไว้ (`codeHelp.reserved`)
- สวิตช์ KV `autolead_config` **เปิดโดยปริยาย** · รอบแรกจด `since` = ตอนนั้น (ไม่ส่งย้อนหลัง) · `manage.py autolead [--off|--on|--preview|--run]`
  · ผลรอบล่าสุด KV `autolead_last` · cron → `connect.tick` → `tick_bg` (thread · ≤10 แชท/รอบ)
- **จ่ายอัตโนมัติยังปิด**: `leadflow_config.auto_chat` (off) · `auto_assign` (False) — ไม่เกี่ยวกับตัวนี้
- **★★ 19 ต.ค.69 (ค่ำ) "ทำทั้งคู่ให้ระบบทำงานร่วมกันได้ละค่อยๆตัดไลน์"** — ทุกลีดได้เลขตั้งแต่ตอนเก็บ ไม่ว่ามาทางไหน (ตัวนับ+ล็อกชุดเดียว):
  | ทาง | ระบบทำอะไร | เก็บเลขที่ |
  |---|---|---|
  | แชท LINE/FB (ข้างบน) | จองเลข → ใบเลขเต็มลงกลุ่ม | `ChatLead.auto["_autolead"]` |
  | **แอดมินพักใบร่างในกลุ่ม ADMIN เก็บ Lead** (TikTok/ไลฟ์/โทรเข้า แบบเดิม) | **บอทจองเลข → ตอบใบเลขเต็มในกลุ่ม (อ้างใบร่าง · quoteToken)** | `ExtLead.auto["_autolead"]` (migration **0043**) |
  | **ฟอร์ม "เพิ่มลีดเอง" ในห้องพัก Lead** | ประกอบใบร่าง (`message_id` `web-park-…` เก็บในคลังแชทกลุ่ม) → ทางเดียวกับข้อบน (ใบเลขเต็มลงกลุ่ม) | `ExtLead.auto["_autolead"]` |
  · **`number_draft`**: ใบร่างที่ `leadpark._scan` รวมเป็นลีดเดียว (โพสต์ซ้ำ) = จอง/ซ่อนที่ใบแรกเสมอ · โพสต์ซ้ำ = บอกเลขเดิม (ไม่ถี่กว่า 30 นาที) ·
    ใบ R = ไม่ออกเลข (ไม้ 2 ใช้เลขเดิม+/1) · ลูกค้าที่มีเลขจองไว้แล้ว (`holder` · แชท/ใบร่างอื่น 7 วัน) หรือเพิ่งได้เลขในห้องจ่ายเบอร์ (`recent_slip` 2 วัน)
    = **ซ่อนใบร่าง** (`ExtLead.no_code` · "ซ่อนไว้" เอากลับได้) + บอกเลขเดิมในกลุ่ม · ได้เลขในห้องจ่ายเบอร์แล้ว (`_asg`) = ข้าม
  · **เตือนในห้องจ่ายเบอร์** (`warn_slip` · ข้อความขาเข้าเท่านั้น · ไม่นับ R//n) ตอบในห้องเดียวกัน (อ้างใบ): (ก) ใช้เลขที่จองไว้ให้ลูกค้าอีกราย = เลขชน ·
    (ข) ลูกค้าที่จองเลขไว้แล้วแต่ใบนี้ใช้เลขใหม่ · (ค) ลูกค้าเพิ่งได้เลขอื่นภายใน 24 ชม. (`RENUM_HOURS`) → "ใช้เลขเดิม" (ระบบลงชีตแก้เซลล์ในแถวเดิมให้) ·
    เตือนเฉพาะที่ชัด (เบอร์/ID LINE ตรงหรือไม่ตรงจริง) · จด `dash_event_log` kind=`autolead`
  · **อ่านข้อความกลุ่ม** `process_groups` ตัวชี้ KV `autolead_ptr` (GroupChat.id · ครั้งแรก = ข้อความล่าสุด ไม่ไล่ย้อน) · **ขยับตัวชี้ก่อนทำ = ทำอย่างมากครั้งเดียว**
    (ล่มกลางทาง = ใบนั้นไม่ได้เลข ดีกว่าบอทพูดซ้ำในกลุ่ม) · ใบเก่ากว่า 3 ชม. ไม่ตอบ · ข้อความเดียวกัน 2 แถว (บอท 2 ตัว) = ทำครั้งเดียว ·
    advisory lock `7_406_068` · เรียกจาก `_checkout_ingest` (`kick` · มี "lead no" ในข้อความ) + cron ทุกนาที (`run`) · ผล KV `autolead_groups_last`
  · `store_chat` เก็บ `extra["quote"]` (quoteToken ของข้อความกลุ่ม) · อ้างได้เฉพาะข้อความที่บอทตัวส่งได้ยินเอง · อ้างไม่ได้ (400) = ส่งซ้ำแบบไม่อ้าง
  · **API `POST /connect/api/park_add`** (แอดมิน) `{channel, live, account, name, line_id, phone, car, ads, more, base, admin, force?}` —
    ต้องมีเบอร์/ID LINE/ชื่อ Account · เบอร์ผิด = 400 · **ลูกค้าเดิม = 409 + เลขเดิม** → หน้าเว็บถามยืนยัน → `force` (ใบร่างเดิมที่ซ่อนไว้ถูกเอากลับมาจองเลข)
  · หน้าเว็บ (ห้องพัก Lead → รอจ่ายเบอร์): ปุ่ม **"+ เพิ่มลีดเอง (TikTok / ไลฟ์ / โทรเข้า)"** กางฟอร์มในหน้า (ไม่ใช่หน้าต่างลอย · ช่องทาง/ทีมไลฟ์ = dropdown ชีต ·
    เลือกช่องทาง TikTok = ตัวหน้า TLD ให้เอง · ที่กรอกค้างไม่หายตอนรายการรีเฟรช `S.addDraft`) · การ์ดใบร่างโชว์เลขที่จองไว้ + "จองเลขแล้ว · รอจ่ายเซลล์" ·
    "เพิ่มในเว็บ" · ส่งลงกลุ่มยังไม่สำเร็จ = บอกเหตุผล · กล่อง "ตั้งเลข/เซลล์เอง" เลขที่จะได้ = เลขที่จองไว้ · กติกามี 2 บรรทัดใหม่ (`parked.form`)
  · `leadpark.board()` ใส่ `reserved` + `base/admin` ตามที่จอง + `webForm` · `leadpark.assign` ใช้เลขที่จองไว้ (`code_for_assign`) · `last_running` นับเลขที่จองไว้ของ ExtLead ด้วย ·
    ส่งไม่สำเร็จส่งใหม่ทุก 5 นาที (แชท + ใบร่าง)
  · สวิตช์ย่อยใน `autolead_config`: **`drafts`** (บอทรันเลขใบร่าง) · **`warn`** (เตือนห้องจ่ายเบอร์) — เปิดโดยปริยาย ·
    `manage.py autolead --drafts on|off --warn on|off` (สถานะบอกตัวชี้ + รอบล่าสุดของข้อความกลุ่ม)
  · ⚠️ ทีมควรคัดลอกใบจากกลุ่ม ADMIN เก็บ Lead ไปแท็กในห้องจ่ายเบอร์ (หรือกดชื่อเซลล์ในเว็บ) — พิมพ์เลขใหม่ = บอทเตือน
  · **Deploy**: `migrate` (checkout **0043**) + restart · รอบแรกเริ่มอ่านจากข้อความล่าสุด
- **★★ 19 ต.ค.69 (ดึก) ส่งทันที + กลุ่มทดสอบ TestBot + ใบอัปเดต + จับรุ่นรถดีขึ้น** (เจ้าของ *"ช้ามาก · ทดลองงานจริงเดะเละ ·
  มันไม่แท็ครุ่นรถ · ตัวเองแท็ลีดตัวเองที่ส่งลงกลุ่มด้วย"* แล้วสร้างกลุ่ม "TestBot")
  · **ส่งทันที**: `AFTER_MIN` 2 → **0** · `connect.note_customer_message` (LINE) / `note_fb_batch` (FB · เฉพาะข้อความสด ≤`FB_LIVE_MIN`)
    เรียก **`kick_chat(o, text)`** (thread) → เช็คแชทนี้เลย (`candidates(pk=)`) ไม่รอ cron · ยังไม่เคยเริ่มรอบแรก (`since` ว่าง) = ไม่ทำ
    · ⚠️ prod เก็บ `after_min: 2` ไว้ใน KV แล้ว → ต้องรัน `autolead --after 0` · FB ยังช้า ≤2 นาที (ดึงทุก `fb_poll_min` · webhook ต้องผ่าน App Review)
  · **ใบอัปเดต** (`update_chat`): ระบบส่งใบไปแล้ว + ลูกค้าพิมพ์รุ่นรถ/ชื่อ/เบอร์/ID LINE เพิ่ม → บอท **อ้างใบตัวเอง** (quoteToken ที่ LINE คืนมากับ push ·
    `res["qt"]`) แล้วส่ง "🔄 อัปเดต Lead No. X — ลูกค้าพิมพ์รุ่นรถเพิ่ม" + ใบเต็ม · เทียบกับ `res["sent"]` (ช่องที่ส่งไปแล้ว `UPD_FIELDS`) ·
    รอลูกค้าพิมพ์จบ `UPDATE_QUIET_SEC` 45 วิ (thread ข้อความล่าสุดเป็นคนส่ง · cron `_updates` เก็บตก) · ภายใน 6 ชม. · ไม่เกิน 3 ครั้ง/ใบ ·
    จ่ายเซลล์แล้ว = ไม่ส่ง · ใบเก่าก่อนมีฟีเจอร์ (ไม่มี `sent`) = ไม่ส่ง · **กลุ่มจริง = สวิตช์ `update` ปิดโดยปริยาย** (`--update on`) · กลุ่มทดสอบเปิดเสมอ
  · **กลุ่มทดสอบ** (`test_group` + `test_chats` ใน `autolead_config` · `--test-group TestBot --test-chat 2213,2231`):
    แชทของบัญชีทดสอบ (พนักงานก็ได้) ให้เบอร์ → ใบ **เลขทดสอบ** (`<ตัวหน้า><เดือน>-0001` · ตัวนับ KV `autolead_test` แยก · ไม่กินเลขจริง)
    เข้ากลุ่มทดสอบ + บรรทัด `TEST_NOTE` · เบอร์เดิม = บอกว่ามีเลขแล้ว (ระบบจริงไม่ส่งซ้ำ) · เบอร์ใหม่ = ใบใหม่ (ทดสอบซ้ำได้) ·
    **ในกลุ่มทดสอบ**: ใบร่าง = จำลองกลุ่ม ADMIN เก็บ Lead (`_test_draft` · ไม่สร้าง ExtLead) · ใบเต็มมีเลข = จำลองห้องจ่ายเบอร์ (`_test_warn` ·
    ใบถูก = บอก "ไม่มีปัญหา" ให้รู้ว่าอ่านแล้ว) · พิมพ์ **"ล้างทดสอบ"** = เริ่มนับใหม่ · แชทบัญชีทดสอบ **ไม่ขึ้นห้องพัก Lead จริง**
    (`connect._test_ids` ใน to_code/pending_park/in_room/pending_one) · ป้ายรายชื่อ = "เลขทดสอบ ทดสอบ" · message id `auto-lead-t…`
    · ชื่อกลุ่ม TestBot ไม่ตรง PARK_HINTS/ห้องจ่ายเบอร์ → ห้องพัก/ลงชีต/จับคู่ไม่เห็น · group id (prod) `Ca18645435479c8d625ce6eb9505a31c6`
  · **จับรุ่นรถ**: `leadgroup.th_fold` (ตัดการันต์/วรรณยุกต์ · ู→ุ) — "ฟอจูนเนอร์"/"ฟอจุนเนอ"/"เรนเจอ" จับได้ (คำที่พับแล้ว <5 ตัวไม่ใช้ กัน "มาชม"=March) ·
    `_CP_SPEC` + ขับ4/4wd/4x4 · **FB: ลูกค้าไม่พิมพ์รุ่นเอง → รุ่นจากข้อความต้อนรับของโฆษณา** (`connect._ad_car` · ข้อความเพจก่อนข้อความแรกของลูกค้า
    ≤`AD_GREET_SEC` 120 วิ · ไม่นับที่แอดมินพิมพ์ผ่าน Connect · ที่มา `โฆษณา` · ลูกค้าพิมพ์รุ่นเองทีหลังแทนได้ · ดูครั้งเดียว `auto["_adcar"]`)
    · เคสจริง NLD10-9681 ("ฟอจูนเนอร์ 2.8 ขับ4 ปี2017") / NLD10-9682 (ตอบ "สีดำมีไหม" ใต้โฆษณา Yaris Ativ) ใบเดิมขึ้น "รถ : -"
- **★★ 19 ต.ค.69 (ดึกมาก) ลูกค้า Facebook จากโฆษณา → แท็ก Ads** [fb_ads.py](checkout/fb_ads.py) (เจ้าของ *"ช่วย Tag Ads ด้วย ชื่อ Ads เก็บไอดีแอดไว้ในฐานข้อมูล
  ในอนาคตถ้าปิดยอดได้จะได้แท็กถูก แต่การส่งให้แอดมินจะใช้ตัวตามรูปลงกลุ่มไลน์"* + รูปการ์ด "ระหว่าง Mazda3 กับ Yaris Ativ รุ่นไหนดี")
  · ลูกค้ากดโฆษณาแบบทักแชท → ห้องแชทมี **การ์ดโฆษณา** = ข้อความขาออกของเพจที่ไม่มีตัวอักษร แต่มี `attachments.generic_template`
    {title "รีบจอง ก่อนหมด !!!", subtitle "จว6456"/"ระหว่าง Mazda3 กับ Yaris Ativ รุ่นไหนดี", media_url} · **ไม่มี ad id** (ได้เฉพาะ webhook `referral`)
    · เดิม `fb_sync._MSG_FIELDS` ขอ attachments แบบระบุช่อง ไม่มี generic_template → การ์ดหายเป็นข้อความว่าง · ตอนนี้ขอแล้ว · ชนิด `template`
    (`has_media=False` ไม่ใช่ไฟล์ให้ดาวน์โหลด · `fb_preview` = "[การ์ดโฆษณา] title · subtitle")
  · **ช่อง ADS** (= "Ads :" ในใบลงกลุ่ม LINE + คอลัมน์ ADS ชีต) = **subtitle ของการ์ด** (ไม่มี = title) · ที่มา `โฆษณา` · การ์ดใหม่แทนได้ · คนแก้แล้วไม่แตะ
  · **`ChatLead.ad_id` / `ad_name`** (checkout migration **0044**) + `auto["_ad"]` {title, subtitle, ad_id, ad_ids, ad_name, adset/campaign, how}
    · จับคู่ subtitle กับ **ชื่อโฆษณา** (`dash_meta_ad_daily` 14 วัน → ไม่เจอ = รายชื่อจาก Marketing API จำ 6 ชม. KV `meta_ad_catalog`) ·
    how: `exact` (webhook ให้ ad id) / `unique` / `spend` (ชื่อซ้ำหลายชิ้น = โฆษณาเดียวก๊อปหลายกลุ่มเป้าหมาย → ใช้เงินวันนั้นมากสุด + `ad_ids` ทุกตัว) / `none`
    · วัดจริง 19 ต.ค.69: แชท FB 60 ห้อง มีการ์ด 32 · **จับคู่ได้ทั้ง 32** (ตรงตัวเดียว 20 · ชื่อซ้ำ 12)
    · **★ 20 ต.ค.69 เรียงความตรงก่อน (`_strength`: ชื่อ = การ์ด 3 · การ์ดอยู่ในชื่อ 2 · ชื่ออยู่ในการ์ด 1) → วันที่ → เปิดอยู่ → เงิน → id ใหม่กว่า**
      — เคสจริง NLD10-9681 การ์ด "มุมมอง Fortuner ขับ 4" เดิมได้โฆษณา "fortuner" ปี 2022 (หยุดแล้ว) เพราะคะแนนเท่ากัน · `ad_ids` = ชื่อเดียวกับตัวที่เลือกเท่านั้น
  · รุ่นรถ: ลูกค้าไม่พิมพ์รุ่น → จากชื่อโฆษณา/การ์ดก่อน แล้วค่อยข้อความต้อนรับ · ป้าย "จากโฆษณา" ของช่อง ADS ในหน้าแชท = tooltip ชื่อโฆษณา/แคมเปญ/ad id
  · ข้อความที่เก็บก่อน deploy ไม่มีการ์ด → `manage.py fb_adcards --apply [--days 7]` (ครั้งเดียว · ถาม Graph ห้องละ 1 ครั้ง) · autolead ก่อนส่งใบถามเองครั้งเดียว (`ensure_card` · `auto["_ad_refetch"]`)
  · webhook (ถ้าผ่าน App Review) เก็บ `extra["referral"]` → ad id ตรง
- **★ 20 ต.ค.69 เจ้าของสั่ง "พักการ run number ไปก่อน จนกว่าทุกอย่างจะลงที่"** → `manage.py autolead --off` (prod)
  · `--off` = **พักการรันเลขจริงทั้งหมด**: แชท (`kick_chat`/`run`) · ใบร่างในกลุ่ม ADMIN เก็บ Lead · เตือนห้องจ่ายเบอร์ · ใบอัปเดตกลุ่มจริง ·
    **ฟอร์ม "เพิ่มลีดเอง"** (`add_manual` ตอบ 400 + ปุ่มขึ้น "พักอยู่" — เดิมฟอร์มไม่เช็คสวิตช์ จองเลขได้แม้ปิด)
  · **กลุ่มทดสอบยังทำงาน** (ไม่ขึ้นกับ `enabled` · ขึ้นกับ `test_group` อย่างเดียว · `run`/`tick_bg`/`process_groups` ทำเฉพาะส่วนทดสอบ)
  · **★ โหมดซ้อม `--show on`** (เจ้าของ *"วันนี้ส่งลงกลุ่มนี้ไปก่อน อย่าพึ่งส่งลงกลุ่มจริง"*) — ตอนพักการรันเลข + มีกลุ่มทดสอบ:
    ลูกค้าจริงที่ให้เบอร์/ID LINE หลัง `show_since` = **ใบหน้าตาเดียวกับใบจริงแต่ไม่มีเลขรัน** (`NLD10-` · ตัวหน้าตาม `suggest_prefix`)
    เข้ากลุ่มทดสอบเท่านั้น · **ไม่มีบรรทัดทดสอบ/ชื่อโฆษณาต่อท้าย** · ไม่จองเลข · ไม่แตะกลุ่ม ADMIN เก็บ Lead · `show_one` / `ChatLead.auto[SHOW_KEY="_alshow"]`
    (กันส่งซ้ำด้วย `select_for_update`) · message id `auto-lead-s…` · ลูกค้าพิมพ์เพิ่ม = ใบอัปเดตอ้างใบซ้อม · ส่งไม่สำเร็จ = cron ส่งใหม่ (`_retry_show`)
    · แอดมินพักใบร่าง/โพสต์ใบเองแล้ว = ข้าม (`_already_posted` เหมือนของจริง) · **เปิดรันเลขจริง (`--on`) = ซ้อมหยุดเอง** (`show_on`)
  · เลขที่จองไว้แล้วยังใช้ตอนจ่ายเซลล์ได้ตามเดิม · `--on` = เริ่มนับจากตอนนั้น (ลูกค้าที่ให้เบอร์ตอนพักไม่ถูกส่งย้อนหลัง)
- **★ 20 ต.ค.69 เพจ Facebook 4 เพจ + ช่องทางตาม dropdown ชีต** (เจ้าของส่ง token ใหม่ "แท็กช่องทางให้ถูกตาม dropdown ของ sheet")
  · token ใหม่เห็นเพจเพิ่ม: **Guru เจมส์ รถมือสอง `650823708107550`** · **บอสเจมส์ ทะเบียนเทพ `765581723300455`** → prod ต้องแก้ `.env`
    `META_PAGE_IDS=2302089596486628,482041925229408,650823708107550,765581723300455` + `META_ACCESS_TOKEN` (เจ้าของแก้เอง · ผู้ช่วยไม่เขียน token ลงไฟล์)
  · **`connect._fb_channel(page_id)`** — ลีด FB ได้ช่องทาง = ตัวเลือกชีตที่ขึ้นต้น "เพจ": `FB_PAGE_CHANNEL` (2302089596486628 สำนักงานใหญ่ → "เพจบ้านเก่า"
    · 482041925229408 → "เพจอ่อนนุช" · Guru → "เพจ Guru" — วัดจากใบจ่ายลีดจริง 273/279 และ 65/77) · เพจอื่น = ตัวเลือก "เพจ X" ที่ X อยู่ในชื่อเพจ
    (KV `meta_page_names`) · ไม่มีตัวเลือก/ตรงหลายตัว = ไม่เติม (บอสเจมส์ตอนนี้ชีตมีแค่ "TIKTOK ช่องบอสเจมส์ทะเบียนเทพ" → ใบขึ้น "ช่องทาง : -")
    · ใบ autolead เลิกใส่ "Facebook" (ไม่อยู่ใน dropdown) · LINE = `_line_channel()` ("LINE@")
- เทสต์ `python scripts/test_autolead.py` (154 ข้อ · [7]–[10] ใบร่าง/จ่ายเซลล์/เตือน/ฟอร์ม API · [11] รุ่นรถ · [12] ส่งทันที+ใบอัปเดต · [13] กลุ่มทดสอบ · [14] Ads · [15] พักการรันเลข · [16] โหมดซ้อม)
  · ⚠️ test_connect "ทีมตามเวร" ล้มช่วง 23:54–24:00 (เส้นตาย 5 นาทีข้ามเที่ยงคืน) · test_crm "นัดวันนี้" ล้มหลัง ~23:30 — เป็นเรื่องเวลาที่รัน ไม่ใช่บั๊ก
  · ตรวจหน้าเว็บด้วย Chrome จริง (dev server ปิด token LINE · stub เฉพาะ POST · จอ 1400/390 · ไม่ล้นจอ · ที่กรอกไม่หาย · ยืนยันลูกค้าเดิมแล้วส่ง force)

### 🏷️ ตัวหน้าเลขลีดอัตโนมัติ (run code auto) — [lead_code.py](checkout/lead_code.py) · 17 ต.ค.69 (เจ้าของสั่ง)
ตอนจ่ายเบอร์ ระบบเลือกตัวหน้า **LD / NLD / BLD / WLD / HLD** เองจากข้อมูลในแชท + ช่องข้อมูลลีด — **ไม่ใช้ AI** · บอกเหตุผลทุกครั้ง · แอดมินเปลี่ยนเองได้
- **เกณฑ์ของเจ้าของ** (ข้อความเต็มอยู่หัวไฟล์ — แก้เกณฑ์ที่ `decide()` ที่เดียว):
  **HLD** = ไฟแนนซ์/เซ็นที่อื่นผ่านแล้ว · ซื้อสด + (เราแจ้งราคาแล้ว หรือ งบ ≥ ราคารถที่ถาม) · อายุงาน/ประวัติผ่อน ≥1 ปี **และ** เอกสารรายได้ **และ** มีเบอร์
  · **WLD** = อายุงานหรือประวัติผ่อน ≥1 ปี · โปรไฟล์ดี+เอกสารแต่ให้แค่ไอดีไลน์ · นัดดูรถมีวัน (นัดดูรถค้าง / `crm.appt_hint`) · มีรถเทิร์น+โปรไฟล์ดี
  · **LD** = ให้ข้อมูลแต่อ่อน (เงินเดือน < `LOW_INCOME` 15,000 · อายุงาน <1 ปี · ไม่มีเครดิต/ติดบูโร/เครดิตไม่ดี ฯลฯ)
  · **BLD** = ไม่ให้ข้อมูลเลย + รถพร้อมขายที่ตรงรุ่นทุกคัน ≤ 3 แสน (ไม่มีในสต็อก = งบที่ลูกค้าบอก)
  · **NLD** = ให้เบอร์ไม่ให้ข้อมูล · รถเทิร์นไม่รู้โปรไฟล์ · ให้เช็คราคารถเทิร์นก่อน · จะเข้าร้านไม่บอกวัน · ซื้อสดแต่ยังไม่แจ้งราคา · ข้อมูลบางส่วน
  · **เข้าหลายระดับ = ใช้ระดับสูงสุด** · ค่าที่ผมตั้งเอง (เจ้าของตอบ "ตามที่เสนอ"): 15,000 · ราคาจากสต็อก · HLD ต้องมีเอกสาร · เอกสารจับจากคำ+ติ๊กเอง
- **ลำดับใน `connect.suggest_prefix`**: type ที่กรอกแล้ว → ช่องทาง TikTok/TikTokAds (TLD/TALD เหมือนเดิม) → `lead_code.for_chat` → NLD
  · **★ ไม่ติ๊ก R ให้ลีดใหม่แล้ว** — เจ้าของยืนยัน *"R = เคสที่ไม้แรกคุยไม่ผ่าน/ติดเงื่อนไข ส่งให้ไม้ 2 หรือแอดมิน"* = ใช้ "ส่งต่อไม้ 2" (R+เลขเดิม+/1)
    (เดิม type RJ/Hot RJ/Hot RB = ติ๊ก R) · A (จ่ายให้เทเลเซลล์) ยังติ๊กให้เหมือนเดิม · **เพิ่ม `LD` ใน `CODE_BASES`** (Moderate) ออกเลขได้แล้ว
- **คำในแชท** (ลูกค้า + โน้ตแอดมิน `fill_note/admin_profile/more`): ประวัติผ่อน "ผ่อนรถมา 2 ปี" (ต้องมี มา/ไปแล้ว — "อยากผ่อน 4 ปี" ไม่นับ · ของแฟน/พ่อแม่ไม่นับ) ·
  เอกสาร (สลิปเงินเดือน/ใบรับรอง/statement · "ไม่มีสลิป"/"สลิปโอน" ไม่นับ) · ซื้อสด ("เงินสดไม่พอ" ไม่นับ) · ไฟแนนซ์ผ่าน (ไม่ผ่าน/รออนุมัติ/ผ่านไหม ไม่นับ) ·
  ราคาที่เราแจ้ง (ข้อความขาออก) · งบ · รถเทิร์น · จะเข้ามาดูรถ · อายุงาน/รายได้/ประวัติผ่อนจากช่องที่ `lead_keywords` เติมไว้แล้ว
- **ติ๊ก "มีเอกสารยืนยันรายได้"** ในกล่องจ่ายเบอร์ → `POST /connect/api/assign_lead {id, doc: true|false|null}` → `ChatLead.auto["_doc"]` (ชนะคำในแชท · null = คืนให้ระบบดู) · แอดมินเท่านั้น
- **โชว์ที่ไหน**: กล่องจ่ายเบอร์ (ระบบแนะนำ + เหตุผล + "เกณฑ์ที่เข้าทั้งหมด") · การ์ดแชทในห้องพัก Lead (`inbox?view=tocode` → `pfx`/`pfxWhy`) ·
  แผน Run Auto (`crm.room_plan` → `pfx`) · กดชื่อเซลล์/Run Auto (ไม่ส่ง base) ใช้ตัวหน้าเดียวกัน · `profSig` รวม `codeHelp.suggest` (ติ๊กแล้วแผงวาดใหม่)
- จำผล 2 นาทีต่อแชท (`_CACHE` · คีย์ = เวลาข้อความล่าสุด + lead.updated_at) · สต็อกจำ 5 นาที · ใบร่างในห้องพัก (กลุ่ม ADMIN เก็บ Lead) ใช้ตัวหน้าที่แอดมินเขียนในใบเหมือนเดิม
- ไม่มี migration · **เทสต์** `python scripts/test_lead_code.py` (53 ข้อ · เกณฑ์ทีละข้อ + กับดักคำไทย + ผ่านหน้าเว็บจริง: แนะนำ/ติ๊กเอกสาร/กดชื่อเซลล์ออกเลข HLD/LD/ห้องพัก/Run Auto/type ชนะ/TikTok/สิทธิ์)

### 💬 หน้า "คอมเมนต์" (Connect) — รวมคอมเมนต์ Facebook · TikTok (รออนุมัติ) · YouTube — [comments.py](checkout/comments.py) · 17 ต.ค.69
เจ้าของสั่ง *"ระหว่าง กล่องแชทรวม กับ ห้องพัก Lead อยากให้เพิ่มหน้า Comment … รวมคอมเม้นจากทุกช่องทาง FB TT(รออนุมัติ) YT"*
- **เมนูซ้ายของ Connect (แอดมินเท่านั้น)** ระหว่าง กล่องแชทรวม กับ ห้องพัก Lead · `?p=cmt` เปิดตรง · ป้ายตัวเลข = รอตอบ 7 วัน
  (`inbox` ของแอดมินส่ง `counts.comments` = `comments.wait_count()`) · รีเฟรชเองทุก 60 วิตอนเปิดหน้านี้
- **ตาราง `checkout_socialcomment`** (`SocialComment` · checkout migration **0038**) — 1 แถว/คอมเมนต์ระดับบนสุด · unique (platform, ext_id) ·
  คำตอบใต้คอมเมนต์เก็บแค่ `reply_count` + **`replied` = เพจ/ช่องเราตอบแล้ว** (+ `replied_at`) · `done_at/done_by` = กด "จัดการแล้ว" (รอบดึงไม่ทับ)
  · **"รอตอบ" = ยังไม่ replied + ยังไม่จัดการแล้ว + ไม่เก่ากว่า `WAIT_DAYS`=7 วัน** · เก่ากว่า `KEEP_DAYS`=90 วันลบเองวันละครั้ง
- **ดึงเองเป็นรอบ** (`connect.tick` → `comments.tick_bg()` · thread แยก · ล็อก KV `comments_sync_lock` ค้างเกิน 15 นาทีรับช่วงได้ · สถานะ KV `comments_sync`)
  · **Facebook ทุก `FB_EVERY_MIN`=10 นาที** — `/<page>/feed` (โพสต์ย้อน `POST_WINDOW_DAYS`=60 วัน · 4 หน้า×25) + **`/<page>/ads_posts`**
    (`include_inline_create=true` · 2 หน้า · คอมเมนต์ใต้โฆษณาไม่อยู่ใน feed) · คอมเมนต์ 50 ล่าสุด/โพสต์ + คำตอบ 25 อัน (ดูว่าเพจตอบแล้วไหม)
    · **ผ่าน `meta.get/paged` เท่านั้น** (ด่านแยกบริษัท) · page token · โควต้า Meta ≥ `fb_sync.STOP_USAGE_PCT` = ข้ามรอบ (เก็บไว้ให้แชท Messenger)
    · คอมเมนต์ของเพจเองไม่เก็บ · รูป/สติกเกอร์ไม่มีข้อความ = "[รูป]" ฯลฯ · ⚠️ **ชื่อคนคอมเมนต์ Facebook มักไม่มา** (FB ปิดตั้งแต่ 2018) → หน้าเว็บขึ้น "ผู้ใช้ Facebook"
    · รูปโพสต์เป็นลิงก์มีอายุ → อัปเดตให้วันละครั้ง (ไม่เขียนทุกรอบ)
  · **YouTube ทุก `YT_EVERY_MIN`=15 นาที** — `commentThreads?allThreadsRelatedToChannelId=<UC…>&order=time` (1 หน่วย/หน้า · ช่องละ ≤2 หน้า×100)
    · ช่องจากตาราง `dash_youtube_channel_snapshot` 7 วันล่าสุด (ไม่เปลืองโควต้า · ยังไม่มี = `resolve_channel` ตาม `YOUTUBE_CHANNELS`)
    · ชื่อคลิปจาก `dash_youtube_video_snapshot` · คอมเมนต์ของช่องเองไม่เก็บ · ตอบแล้ว = มีคำตอบจากช่องเราใน `replies` (YouTube ส่งมาบางส่วน)
    · ⚠️ API key ล็อก IP ไว้ที่ VPS — ในเครื่อง dev ได้ 403 · เห็นเฉพาะคอมเมนต์สาธารณะ (ที่ YouTube กักไว้รอตรวจไม่มา)
  · **TikTok = รออนุมัติ** (Login Kit ที่ดึงยอดวิวไม่ให้คอมเมนต์ · ต้องได้ TikTok API for Business ก่อน) — แท็บโชว์ข้อความอธิบาย ไม่มีแถว
  · ช่องหนึ่งพังไม่ลากช่องอื่น · เพจ/ช่องไหนพังขึ้นในบรรทัดสถานะของหน้า
- **ปุ่ม "ดึงตอนนี้"** (`request_sync` · ห่างกัน ≥ `MANUAL_GAP_SEC`=120 วิ · กำลังดึงอยู่ = ปฏิเสธ) · **"จัดการแล้ว"** = ออกจากรายการรอตอบ (ยกเลิกได้)
  · **ตอบคอมเมนต์จากหน้านี้ยังไม่ได้** — ปุ่ม "เปิดใน Facebook/YouTube ↗" ไปตอบที่แพลตฟอร์ม · ตอบแล้วรอบถัดไปเห็นว่า "ตอบแล้ว" เอง
- **หน้าเว็บ** (`openCmt`/`paintCmt`/`cmRow` ใน connect.html): **dropdown 3 ตัว** ช่องทาง (ทุกช่องทาง/Facebook/TikTok·รออนุมัติ/YouTube + ตัวเลขรอตอบ) ·
  **จำแนกประเภทลูกค้า** (ดูข้างล่าง) · สถานะ รอตอบ/ทั้งหมด/ตอบแล้ว · ช่องค้น (ข้อความ/ชื่อ/โพสต์/เพจ) · บรรทัดสถานะการดึงต่อช่องทาง ·
  การ์ดคอมเมนต์ (รูปคน · ป้ายช่องทาง · เพจ/ช่อง · เวลา · ป้ายประเภท · ข้อความ · โพสต์/คลิป+รูป · ป้ายโฆษณา · dropdown เปลี่ยนประเภท)
  · **หัวหน้า (ตัวกรอง/ช่องค้น) วาดครั้งเดียวตอนเข้าหน้า** เปลี่ยนตัวกรองวาดแค่รายการ (เคยวาดทั้งหน้า = ช่องค้นหลุดโฟกัสระหว่างพิมพ์)
  · dropdown (ตัวกรอง + รายคอมเมนต์) **ไม่ถูกวาดทับตอนกำลังเปิดเลือก** (รายการรีเฟรชเองทุก 60 วิ — เช็ค `document.activeElement`)
  · _(เดิมช่องทางเป็นแถบปุ่ม — 17 ต.ค.69 เจ้าของสั่งเปลี่ยนเป็น dropdown)_
  · **★ รอบ 3 (17 ต.ค.69 เจ้าของ "ตัวหนังสือจาง · พื้นที่เหลือเยอะไม่จำเป็น")**: รายการเป็น **การ์ดหลายคอลัมน์** (`#lc-cm-rows` grid
    `minmax(560px,1fr)` · จอ 1830 = 2 คอลัมน์ · ≤1280 = คอลัมน์เดียว) แทนแถวกว้างทั้งจอที่ป้าย/เวลาไปอยู่สุดขวา · การ์ดโพสต์กว้างเต็มการ์ด ·
    ปุ่มชิดล่างการ์ด · ตัวหนังสือรอง t3 → t2 (ชื่อเพจ/เวลา/ป้ายตัวกรอง/บรรทัดสถานะ) · ข้อความคอมเมนต์ 14.5px ตัวหนา
  · **การ์ดคอมเมนต์เป็นกริดตายตัว** (17 ต.ค.69 เจ้าของ "เรียงดูแปลกๆ ให้มันเท่ากัน"): หัว = ชื่อคน ··· [ประเภท][สถานะ][เวลา] ชิดขวา ·
    บรรทัด 2 = ป้ายช่องทาง (กว้างเท่ากัน) + ชื่อเพจ/ช่อง · การ์ดโพสต์กว้าง/สูงเท่ากันทุกแถว (ไม่มีรูป = กรอบไอคอนแทน) · ปุ่ม/ช่องเลือกกว้างตายตัว
    (`.cm-head/.cm-right/.cm-st/.cm-cat/.cm-time/.cm-sub/.cm-pth/.cm-open`) · ชื่อคนกด "จัดการแล้ว" ย้ายไปอยู่ใน title ของป้าย (ไม่งั้นป้ายยาวไม่เท่ากัน)
    · ตรวจด้วยการวัดพิกัดจริงใน Chrome (จอ 1280/900/390 · 43/43)
- **★ จำแนกประเภทลูกค้า (17 ต.ค.69 · เจ้าของสั่ง · checkout migration 0039)** — 4 ประเภท: **ทักทาย/พูดคุยเล่น · สนใจ/สอบถาม · โจมตีแบรนด์ · คอมเพลน**
  · **★ รอบ 2 (17 ต.ค.69 · migration 0040 เปลี่ยนชื่อที่โชว์)** เจ้าของ: *"สีบรอนเงินมีมียัง" ควรอยู่หมวดสอบถาม* → ชื่อ "สนใจ/ถามราคา" → **"สนใจ/สอบถาม"**
    (คีย์ `interest` เดิม) + ถามสี/ถามว่ามีไหม (`สี…มี/ไหม/ยัง` · `มี(มี)?ยัง/ไหม`) + **คอมเมนต์ที่มีแค่ชื่อสี** (`_COLOR_ONLY` · "ขาว" ใต้โพสต์รถ = ถามว่ามีสีนี้ไหม)
    + **คอมเมนต์ที่เป็นคำถามแต่ไม่เข้าประเภทอื่น** (`_ASK` ไหม/มั้ย/ป่าว/ปะ/หรือยัง/? · กัน ไหม้ · สมัย · ปะทะ) · `CLASSIFY_V = 2` → แถวที่ระบบจัดไว้ถูกจัดใหม่ตอนเปิดหน้า
    · ⚠️ หลัง deploy รอบแรก เจ้าของส่งรูปที่คอมเมนต์ "สนใจ" อยู่ในตัวกรอง "ยังไม่จัดประเภท" — ในเครื่อง/เทสต์จัดเป็นสนใจถูกต้อง หาสาเหตุไม่ได้
      (อ่านฐานข้อมูล prod ไม่ได้) · `CLASSIFY_V = 2` จัดใหม่ทุกแถว ถ้ายังเจออีกต้องดูข้อมูลแถวนั้นบนเซิร์ฟเวอร์
  (เจ้าของพิมพ์ "คมเพลน" — ใช้คำสะกดทั่วไป "คอมเพลน") + "ยังไม่จัดประเภท"
  · **ระบบจัดจากคำในคอมเมนต์ ไม่ใช้ AI** (`comments.classify(text)` → `(ประเภท, คำที่จับได้)` · `_RULES`) · ลำดับชนะ โจมตีแบรนด์ > คอมเพลน > สนใจ > ทักทาย
    · คำที่มี "ไม่/ไม่ได้/ยังไม่" นำหน้า (`_NEG`) ไม่นับสำหรับคำที่ติดธง (ไม่โกง · ไม่สนใจ · ไม่ชอบ) · อีโมจิล้วน/สติกเกอร์/GIF = ทักทาย · [รูป]/ชื่อคนล้วน = ยังไม่จัด
    · **⚠️ กับดักภาษาไทย (มีเทสต์ครบ)**: เท่≠เท่าไหร่ · ชอบ≠รับผิดชอบ · แย่≠แย่ง · ผ่อน≠ผ่อนคลาย · ดาวน์≠ดาวน์โหลด · ไลน์≠ออนไลน์ · ทัก≠ทักทาย ·
      สัด≠สัดส่วน · กาก≠กากบาท · hi≠Hilux · 555 ในเบอร์โทรไม่นับ · **เพิ่มคำใหม่ = ใส่ขอบกัน + เพิ่มเทสต์**
  · ช่อง `category` · `category_why` (คำที่จับได้ · โชว์ใน tooltip ป้าย) · `category_by` (**ว่าง = ระบบจัด** · มีชื่อ = คนจัด → รอบดึงไม่ทับ) · `category_v`
    · จัดตอน `_upsert` (คอมเมนต์ใหม่ + ข้อความถูกแก้) · **แก้กติกา = เพิ่ม `CLASSIFY_V`** → `classify_pending()` (เรียกใน `list_json`) จัดแถวเดิมของระบบใหม่เอง ไม่แตะที่คนจัด
  · API: GET `cat=greet|interest|attack|complaint|none` + `catCounts` (นับตามช่องทาง/สถานะ/คำค้นที่เลือก ไม่ถูกตัวกรองประเภทบีบ) + `cats` ·
    POST `{action:"category", id, cat}` (`cat:"auto"` = คืนให้ระบบจัด · `""` = ไม่จัดประเภท · ค่ามั่ว = 400) · แอดมินเท่านั้น
- **ไม่มีอะไรส่งออกนอกระบบ** (อ่านอย่างเดียว) · `db_inventory.TABLES` มีคำอธิบายแล้ว (pii)
- **Deploy**: `migrate` (checkout **0038** + **0039** + **0040**) + restart · รอบแรกเริ่มเองภายในนาทีถัดไป (ต้องมี `META_*` และ/หรือ `YOUTUBE_*` ตั้งอยู่แล้ว)
  · คอมเมนต์ที่ดึงมาก่อน 0039 ถูกจัดประเภทเองตอนเปิดหน้าครั้งแรก
- **เทสต์**: `python scripts/test_comments.py` (125 ข้อ · ปลอมที่ `requests` = Graph/YouTube) — ลองแกล้งไม่ข้ามคอมเมนต์ของเพจ/ไม่อัปเดตแถว/ไม่เช็คโควต้า แล้วล้ม 10 ข้อ
  · [8] จำแนกประเภท: 29 ข้อความตัวอย่าง + 12 กับดักคำไทย · จัดตอนดึง · ข้อความเปลี่ยนจัดใหม่ · คนจัดแล้วไม่ทับ · จัดแถวเก่าตอนเปิดหน้า · ตัวกรอง/ตัวเลข · API สิทธิ์
  · ตรวจ UI ด้วยเบราว์เซอร์จริง (เมนู/ป้ายตัวเลข · จัดการแล้ว/ยกเลิก · dropdown ช่องทาง/ประเภทยิง query ถูก · เปลี่ยนประเภทรายคอมเมนต์ · คืนให้ระบบจัด ·
    ค้นไม่หลุดโฟกัส · TikTok · จอ 1280/390 ไม่ล้น · ไม่มี JS error · 36/36)
- **ยังไม่ได้ทำ**: ตอบคอมเมนต์จากหน้านี้ (FB ทำได้ด้วยสิทธิ์ที่มี · YouTube ต้อง OAuth รายช่อง) · ส่งข้อความส่วนตัวหาคนคอมเมนต์ FB (private reply) ·
  รับคอมเมนต์ FB แบบทันทีผ่าน webhook `feed` (ต้องผูกสิทธิ์ในแอป Meta) · จับเบอร์/ความสนใจจากคอมเมนต์เข้าห้องพัก Lead · TikTok

### 🖼️ รูป/ไฟล์ที่ลูกค้าส่งในแชท (Connect) — [chatmedia.py](checkout/chatmedia.py) · 11 ต.ค.69
เจ้าของแจ้ง *"รูปไม่ขึ้นนิ"* — บับเบิลขึ้น "[รูป] (รูป/ไฟล์ยังเปิดในระบบไม่ได้)" เพราะระบบจดแค่ `has_media` ไม่เคยโหลดตัวไฟล์
- **LINE** ไม่ส่งไฟล์มากับ webhook → ขอจาก `api-data.line.me/v2/bot/message/<id>/content` ด้วย **token ของบัญชีที่ได้ยินข้อความ**
  (`GroupChat.channel` → `line_channels.token_of` · ไม่รู้บัญชี = ลองตัวรับแล้วทุกบัญชี) · **LINE ลบไฟล์เองหลังผ่านไปช่วงหนึ่ง (ไม่บอกกี่วัน)**
  · 400/404 ทุก token = หมดอายุ (`gone`) · 401/202/429/5xx/เน็ต = พลาดชั่วคราว ลองใหม่หลัง 10 นาที
- **Facebook** ลิงก์ fbcdn มีลายเซ็นหมดอายุ → หมดอายุแล้วขอลิงก์ใหม่ผ่านห้องสนทนาของเพจ (`meta.get` → ผ่านด่านเพจบริษัทอื่น)
  · **โหลดเฉพาะ https บนโดเมน FB** (`FB_HOSTS`) · redirect ตามเฉพาะไปโดเมน FB (ไม่ตาม = ไม่ยิงออกนอก) · webhook เก็บ `extra.attachments[].url` แล้ว
- **★ ที่เก็บ = `CHAT_MEDIA_ROOT` (ค่าตั้งต้น `private_media/chat/{line,fb}/<pk แถวแชท>-<ลำดับ>.<นามสกุล>`) นอก `/media/`**
  — nginx เสิร์ฟ `/media/` ให้ใครก็ได้ที่รู้ลิงก์ · ลูกค้าส่งบัตรประชาชน/สลิป/รายงานเครดิต → **เปิดได้ทางเดียวคือ `/connect/api/media`**
  ซึ่งเช็คสิทธิ์แบบเดียวกับเปิดแชท (`_access`) · คิวรอรับ (preview) เปิดได้เฉพาะไฟล์ในข้อความที่ลูกค้าส่งตั้งแต่เริ่มรอบ ·
  ข้อความต้องเป็นของลูกค้ารายนั้นจริง (LINE `sender_id` · FB `thread_id`) · แชทกลุ่มไม่เปิดผ่านทางนี้
  · `.gitignore` มี `private_media/` แล้ว · **ห้ามย้ายไปไว้ใต้ MEDIA_ROOT**
- **API** `GET /connect/api/media?id=<ChatOwner.id>&m=<l|f><pk>.<ลำดับ>[&dl=1]` · ยังไม่โหลด = โหลดตอนนั้นเลย ·
  ไม่มีไฟล์ = JSON `{state, error}` (หมดอายุ 410 · อื่นๆ 404) · **ไม่มี LINE user id ในลิงก์**
- **ชนิดไฟล์**: รูปต้องผ่านการดูไบต์แรกจริง (`_sniff` — Content-Type บอกว่ารูปแต่ไบต์เป็น HTML = `bin`) · เปิดในเบราว์เซอร์ได้เฉพาะ
  `INLINE_TYPES` (jpg/png/gif/webp · mp4/mov/webm · m4a/aac/mp3/ogg/wav · pdf) **นอกนั้น (svg/html/docx…) = ดาวน์โหลด + octet-stream เสมอ**
  · header: `nosniff` · `Cache-Control: private, max-age=86400` · `Content-Security-Policy … sandbox` (ยกเว้น pdf) · `Referrer-Policy: no-referrer`
  · เพดาน `CHAT_MEDIA_MAX_MB` (25) — เกิน = `big` บอกให้เปิดในแอป LINE OA/Facebook
- **`media_token`** = `<สถานะ>|<นามสกุลต่อไฟล์ คั่น , (- = ยังไม่มี)>|<เวลาลองล่าสุด>` · สถานะ `ok`/`err`/`gone`/`big`/`none`
  · ข้อความใน `connect.messages()` ได้ช่อง **`files`** = `[{url, kind, ext, state(ready|pending|gone|big|none), name, size}]`
- **โหลดเมื่อไหร่**: (1) `connect.tick` → `sweep_bg()` ทุกนาที (thread · ≤30 ข้อความ/40 วิ · ข้อความขาเข้าของลูกค้า 7 วันล่าสุด)
  (2) ตอนมีคนเปิดดู (3) ย้อนหลังด้วยคำสั่ง · ผลรอบล่าสุด KV `chat_media_last` · **ลบไฟล์ของแชทที่ถูกลบ (60 วัน) วันละครั้ง**
  (`cleanup_files` · KV `chat_media_clean`) — ข้อมูลส่วนบุคคลต้องหายตามแชท
- **หน้าเว็บ** ([connect.html](checkout/templates/checkout/connect.html) `filesHtml`): รูป = กดเปิดเต็ม · วิดีโอ/เสียง = ตัวเล่น (`preload="none"`) ·
  ไฟล์อื่น = ปุ่มดาวน์โหลด (+ "เปิดดู" สำหรับ pdf) · ข้อความ "[รูป]" ที่เป็นคำแทนถูกซ่อนเมื่อมีไฟล์ · โหลดไม่ขึ้น = บอกเหตุผลแทนกรอบแตก
  · **`paintMsgs` ไม่วาดใหม่ถ้าข้อความไม่เปลี่ยน** (`_msgSig`) — เดิมวาดทับทุก 6 วิ = รูปกะพริบ + เลื่อนดูรูปเก่าแล้วถูกดีดลงล่าง
- **แอปมือถือ**: รูปขึ้นในแชท (แนบ token ใน header) · วิดีโอ/ไฟล์บอกให้เปิดหน้าเว็บ (ดูหัวข้อ "แอปมือถือ")
- **คำสั่ง** `manage.py chat_media [--fetch [--days 60] [--limit N]] [--cleanup] [--out ไฟล์]` — ไม่ใส่อะไร = สถานะแยก LINE/FB ·
  `--fetch` สรุป **ผลตามอายุข้อความ** (= ใช้วัดว่า LINE เก็บไฟล์ไว้กี่วันจริง) · **ห้ามรันด้วย root** (คำสั่งปฏิเสธเอง + บอกคำสั่งที่ถูก)
  — โฟลเดอร์จะเกิดมาเป็นของ root แล้วเว็บ (รันในนาม oxlet) เขียนไฟล์ไม่ได้อีกเลยแบบเงียบๆ
- **หน้าสถานะระบบร้อง** เมื่อรอบล่าสุด (≤2 ชม.) พลาด ≥5 แต่สำเร็จ 0 หรือมี error (มักเป็น LINE token หรือสิทธิ์โฟลเดอร์)
- **Deploy (ไม่มี migration)**: `git pull` → `systemctl restart oxlet` → **ครั้งเดียว**
  `sudo -u oxlet .venv/bin/python manage.py chat_media --fetch --out /tmp/chat_media.txt` (โหลดของเก่าก่อน LINE ลบ + วัดอายุไฟล์)
- **⚠️ ยังไม่ได้วัดว่า LINE เก็บไฟล์กี่วัน** (token ในเครื่อง dev หมดอายุ · บัญชี `claude` อ่าน .env บนเซิร์ฟเวอร์ไม่ได้) — ดูจากรายงาน `--fetch` ครั้งแรก
  · ไฟล์ที่ LINE ลบไปแล้วขึ้น "หมดอายุที่ต้นทาง" (ถูกต้อง ไม่ใช่บั๊ก)
- **เทสต์**: `python scripts/test_chat_media.py` (131 ข้อ รวม QR [12] · ปลอมที่ `requests.get` · พิสูจน์แล้วว่าแกล้งปิดด่านโดเมน/สิทธิ์/การดูไบต์ = ล้ม 11 ข้อ)
  · ตรวจ Chrome จริง (template + API ตัวจริง · รูปขึ้น · ไม่วาดซ้ำ · จอ 1590/390 · ไม่มี JS error/LINE id หลุด)
- **ยังไม่ได้ทำ**: ส่งรูปหาลูกค้า · ไฟล์ในแชทกลุ่ม · ย่อรูป (เสิร์ฟไฟล์เต็ม · LINE ส่งรูป ~100–500 KB อยู่แล้ว)

### 🔳 ลูกค้าให้ LINE เป็น "รูป QR / ลิงก์เพิ่มเพื่อน" → นับเป็นลีด — [lead_qr.py](checkout/lead_qr.py) · 11 ต.ค.69
ผู้ใช้ถาม (พร้อมรูปหน้า "QR โค้ดของฉัน" ของ LINE) *"เราจะรู้ได้ไงว่ากลายเป็นลีดแล้ว … ถ้าลูกค้าส่งรูปมา เราไม่มีตัวที่ดูว่าเป็น Lead จริงไหม?"*
- **กติกาเดิม (ไม่เปลี่ยน)**: แชทเป็นลีด = ลูกค้าให้ **เบอร์ หรือ ID LINE** แล้ว → เข้าห้องพัก Lead เอง (`to_code()`) · แต่ `contacts_in`
  อ่านเฉพาะ **ตัวอักษร** → ลูกค้าที่ส่ง **รูป QR** หรือแปะ **ลิงก์ `line.me/ti/p/…`** หลุดทั้งคู่
  (วัด prod 30 วัน: แชทที่คุยแล้วยังไม่มีช่องทางติดต่อ 66 ราย · ส่งรูปมา 16 ราย · เป็น QR LINE อย่างน้อย 2 · แปะลิงก์ 1)
- **ลิงก์ในข้อความ**: `contacts_in` เรียก `lead_qr.line_contact()` กับ **ข้อความขาเข้าเท่านั้น** (ลิงก์ที่เราส่งไม่นับ)
  · `line.me/ti/p/~myid` = แชร์ด้วย ID → เก็บ `myid` (ผ่าน `_id_ok`) · `line.me/ti/p/<โทเคน>` = QR/ลิงก์ส่วนตัว (ไม่ใช่ ID แต่กดแล้ว
  เพิ่มเพื่อนได้) → เก็บ `line.me/ti/p/<โทเคน>` · **`@xxx`/`%40xxx` (บัญชีทางการ) · ลิงก์กลุ่ม `/ti/g/` · `lin.ee` = ไม่นับ**
- **รูป QR**: `chatmedia.ensure()` โหลดรูปเสร็จ → `lead_qr.scan_row()` (try แยก — อ่านพังไม่ทำให้โหลดรูปพัง) → อ่าน QR ด้วย
  **zxing-cpp ในเครื่อง** → เป็นลิงก์ LINE ส่วนตัว = `connect.capture_qr()` เติม `ChatLead.line_id` (`auto.line_id = "รูป QR"` ·
  `auto._qr = {at, msg}`) → ลีดเข้าห้องพักเอง · QR พร้อมเพย์ในสลิป/QR ร้าน = ไม่นับ
  · **มี ID LINE อยู่แล้ว / คนแก้-ลบช่องนี้แล้ว (`HUMAN`) = ไม่อ่านรูปเลย ไม่ทับ** · ลูกค้าจำลองข้าม
  · ทดสอบความทนแล้ว: QR มีโลโก้เขียวกลาง ย่อเหลือ 160–300px ในภาพหน้าจอ 1080×2400 JPEG คุณภาพ 50–70 = อ่านออกทุกรูป
- **★ ไม่ส่งรูปลูกค้าออกไปไหน (PDPA)** — รูปในแชทมีบัตรประชาชน/เล่มทะเบียน/สลิป · อ่านด้วยไลบรารีในเครื่องเท่านั้น
  · **ไม่มีไลบรารี (ยังไม่ pip install) = ข้ามเงียบ** โหลดรูป/ระบบเดิมทำงานปกติ (มีเทสต์)
- **ป้าย "รอจ่ายเบอร์" ในรายชื่อแชท (แอดมินเท่านั้น · เว็บ + แอป)** — `row_json.contact` = `yes` (มีเบอร์/ID) / `qr` (ได้จากรูป QR
  และยังไม่มีเบอร์) · `nocode` = แอดมินกด "ไม่ต้องจ่ายเบอร์" แล้ว (ไม่ขึ้นป้าย) · มีเลขลีด/ส่งจัดซื้อแล้วขึ้นป้ายเลขแทน
  · เดิมไม่มีอะไรในกล่องแชทรวมบอกเลยว่าแชทไหนกลายเป็นลีดแล้ว ต้องเข้าไปดูในห้องพัก Lead
- **ย้อนหลัง (ครั้งเดียวตอน deploy)**: `manage.py chat_media --qr [--days 60]` (`lead_qr.scan_existing`) อ่านรูปที่โหลดไว้แล้ว ·
  รายงานบอกแค่จำนวน + อ้างแถวแชท **ไม่พิมพ์ ID/ลิงก์ลงรายงาน** · รันซ้ำได้ (เติมแล้ว = ข้าม) · **ห้ามรันด้วย root** (กติกาเดียวกับ `--fetch`)
- **ที่ยังตัดสินให้ไม่ได้ (ต้องให้เจ้าของเลือก)**: รูปรถ / เล่มทะเบียน (เขียว) / บัตร / ภาพหน้าจอที่พิมพ์ ID เป็นตัวหนังสือ —
  จะอ่านได้ต้องใช้ AI ดูรูป (Gemini vision) = **ส่งรูปลูกค้าไปให้ Google** · รูปรถที่ลูกค้า "อยากขาย" อยู่ในสายเคสรับซื้อ (กลุ่มเคสHOT) อยู่แล้ว
- **Deploy (ไม่มี migration)**: `.venv/bin/pip install -r requirements.txt` (zxing-cpp 3.1.1 · wheel abi3 รองรับ Python 3.12/glibc 2.39 ของ VPS)
  → `systemctl restart oxlet` → `sudo -u oxlet .venv/bin/python manage.py chat_media --qr --days 60 --out /tmp/chat_qr.txt`
- **⚠️ รันเทสต์ในเครื่อง dev**: Python หลักของเครื่อง (3.14) ไม่มี zxing-cpp → ลงแยกด้วย `pip install --target <โฟลเดอร์>` แล้วตั้ง `PYTHONPATH`
  (ไม่มีไลบรารี เทสต์ QR ส่วนใหญ่จะข้ามแบบ "ไม่มีไลบรารี")
- **⚠️ อย่ารันเทสต์หลายชุดพร้อมกัน** — `test_connect` ล้ม 3 ข้อ (แจ้ง LINE เลยเวลา) ตอนรันคู่กับชุดอื่น · รันเดี่ยวผ่าน 622/622

### 🧾 ลีดที่แอดมิน "จ่ายในชีตลีดตรง" ออกจากห้องพัก Lead เอง — `connect.sheet_match` · 11 ต.ค.69
ผู้ใช้ *"lead ทุกอย่างต้องออโต้"* — ห้องพัก Lead ค้างทั้งที่ลีดถูกจ่ายไปแล้ว เพราะแอดมิน **ลงเลขในชีตลีดตรงๆ** (หรือโพสต์ใบที่ไม่มีเบอร์)
→ `find_slip` (เบอร์เต็ม/ชื่อไลน์ตรงในใบในกลุ่ม) หาไม่เจอ ลีดเลยค้างไปเรื่อยๆ
- **หลักฐาน prod 11 ต.ค.69**: ลีดที่รอจ่ายและมีเบอร์ 72 ราย — **35 รายมีเลขในชีตลีดแล้ว** (วันที่ห่างไม่เกิน 7 วัน)
- **`sheet_match(phone, last_in, chat_lead_pk)`** — ค้นสมุดเบอร์ (`LeadPhone` · สร้างจากชีตทุก 6 ชม. + ใบในกลุ่ม + ปุ่มในระบบ)
  · นับเฉพาะเลขที่ `seen_on` อยู่ใน **14 วันก่อนข้อความล่าสุดของลูกค้า** (`SHEET_MATCH_DAYS`) = "รอบที่คุยกันอยู่"
  · หลายเลขในรอบเดียวกัน (จ่ายใหม่/ไม้ 2) = **เลขล่าสุด** (วันเท่ากัน = เลข /n ก่อน) · เลขอื่นจดไว้ใน `codes`
  · **เลขเก่ากว่า 14 วัน = ลูกค้าเก่ากลับมา** → ยังอยู่ในห้องพัก (กล่องเตือนเบอร์ซ้ำ + ปุ่ม "จ่ายให้เจ้าของเดิม" เดิม)
  · **★ เลขในรอบนี้มีลูกค้าอีกรายในระบบถืออยู่ (ChatLead/ExtLead) = ไม่เติม** — ห้ามก๊อปเลขเดียวไป 2 ที่
    (เคยพลาดรอบแรก: ลูกค้าเบอร์เดียวกัน 2 แชท ได้เลขเดียวกัน → กล่องเบอร์ซ้ำชี้ผิดคน + ฐานข้อมูล Lead นับซ้ำ · `test_leadflow` จับได้)
- `autofill` เรียกต่อจาก `find_slip` (ใบในกลุ่มชนะ) ก่อนเช็คเคสรับซื้อ → `put("code", …, "ชีตลีด")` + `auto["_sheet"]` (`SHEET_KEY`)
  · **ช่อง code ที่คนเคยลบ/แก้เอง (`auto.code == "คน"`) ไม่เติมกลับ** · type เติมตามตัวหน้าของเลข (กติกาเดิม)
- **ทำเองทุกนาที**: `slip_sweep` (thread จาก cron + ตอนเปิดห้องพัก · ต่อคน 3 นาที) — **เพดานต่อรอบ 60 → 300 แถว**
  (เดิมกวาดแค่ 60 แถวล่าสุด ลีดที่เก่ากว่านั้นไม่เคยถูกเช็ค)
- **ใบร่างในห้องพัก (กลุ่ม ADMIN เก็บ Lead)** — `leadpark._sheet_hits` เบอร์ได้เลขตั้งแต่ 1 วันก่อนโพสต์ใบร่าง (`SHEET_DRAFT_DAYS`)
  → ย้ายไป "จ่ายแล้ว" (แสดงเฉยๆ ไม่สร้าง ExtLead) · ป้ายบอกที่มาตามสมุดเบอร์ (`SHEET_SRC_LABEL` ชีต/ใบในกลุ่ม/ปุ่มในระบบ)
  · ไม่นับในเวลารอเฉลี่ย (ชีตบอกแค่วันที่) · กดจ่ายซ้ำ = ปฏิเสธพร้อมบอกเลข
- **หน้าเว็บ**: รายการ "จ่ายแล้ว" ขึ้น "ชีตลีด (จ่ายนอกระบบ)" + ผู้รับ (ADMIN = เทเลเซลล์) · แผงขวาของแชทบอกว่าเลขมาจากชีต
  + เลขอื่นของเบอร์นี้ในรอบเดียวกัน · คนแก้เลขเองทีหลัง = ไม่อ้างว่ามาจากชีตอีก
- **ที่ยังต้องให้แอดมินกด**: ลีดที่มีแต่ **รูป QR / ID LINE ไม่มีเบอร์** (สมุดเบอร์เก็บแค่เบอร์ · ชีตไม่มีช่องชื่อ) ·
  ลูกค้าเก่ากลับมาเกิน 14 วัน · เบอร์เดียวกับลูกค้าอีกรายในระบบที่ได้เลขแล้ว
- **ไม่มี migration** · เทสต์ `test_connect.py` [33] · ตัวชี้วัดหลังขึ้น prod: จำนวนลีดที่รอจ่ายในห้องพักควรลดลงเองภายในไม่กี่นาที

### ✋ ห้องพัก Lead รับแชทเมื่อแอดมินกด "รับ lead จากแชทนี้แล้ว" — `connect.mark_park` · 11 ต.ค.69 (ค่ำ)
> **★★ 18 ต.ค.69 ยกเลิกแล้ว — แชทที่ให้เบอร์/ID LINE เข้าห้องพักเองอีกครั้ง** (เจ้าของ *"ต่อไปนี้ไม่มีแล้วการให้แอดมินมากดรับหลีดไปพัก เราส่งไปเองเลยดีกว่า"*)
> · `DEFAULTS["room_chat_auto"] = True` · **checkout migration 0041** เปลี่ยนค่าที่บันทึกไว้บนเซิร์ฟเวอร์ (`connect_config.room_chat_auto: false` ตั้งแต่ 12 ต.ค.) เป็น true ตอน migrate
> · **หน้ากฎไม่มีสวิตช์แล้ว** (เหลือเป็นกฎถาวร) · โค้ดโหมดติ๊ก (`mark_park`/`pending_park`) ยังอยู่ ใช้ได้เมื่อตั้ง `room_chat_auto=false` ผ่าน API/KV เท่านั้น
> · กลุ่ม "รอแอดมินกดรับ" ว่างเสมอ · ปุ่ม "รับ lead" บนหัวแชทหาย · ป้ายในรายชื่อเป็น "รอจ่ายเบอร์"
> · ที่ทำให้กลับมาเปิดได้: ตัวจับ "จ่ายแล้วหรือยัง" ด้วย ID LINE (`leadmatch` · ดูหัวข้อ "จ่ายลีดขายจากแชทอัตโนมัติ") — `slip_sweep` เคลียร์แชทที่แอดมินจ่ายไปแล้วออกจากห้องเอง (11 ต.ค. ห้องเต็มเพราะยังจับด้วย ID LINE ไม่ได้)
> · เนื้อหาข้างล่างคือโหมดติ๊กเดิม (11–18 ต.ค.69)
ผู้ใช้ *"ตอนนี้อยากให้เอามาจากกลุ่ม admin เก็บ lead ก่อน เพราะข้อมูลยังไม่ครบ ยังไม่พร้อมทำออโต้ 100
อย่างน้อยก็รอคนไปติ๊กว่าไปรับ lead มาจากแชทนี้แล้ว"* — ห้องพักเต็มไปด้วยแชทที่ระบบจับเบอร์/ID LINE/QR ได้เอง
(ส่วนใหญ่แชท Facebook ที่มีแต่ ID LINE → `sheet_match` เคลียร์ไม่ได้) แต่แอดมินยังไม่ได้ดู
- **สวิตช์ `connect_config.room_chat_auto` — ปิดโดยปริยาย** (หน้า "กฎและเส้นทาง" → "แชทที่ให้เบอร์/ID LINE เข้าห้องพักเอง")
  · ปิด = ห้องพักรับ **ใบร่างจากกลุ่ม ADMIN เก็บ Lead** (เหมือนเดิม ไม่ต้องกด) + **แชทที่แอดมินกดรับ lead**
  · เปิด = กติกาเดิม 4 ต.ค. (ให้เบอร์/ID LINE แล้วเข้าห้องเอง)
  · `room_auto()` จำค่า 20 วิต่อ process (`to_code` ถูกเรียกบ่อย) · `save_cfg` ล้างค่าที่จำใน worker ที่บันทึก · worker อื่นตามภายใน 20 วิ
- **ติ๊ก = `ChatLead.auto["_park"]` = `{by, at}`** (`PARK_KEY` · ไม่ต้อง migrate · เหมือน `_nocode`/`_buy`)
  · `mark_park(o, on, by)` → (ok, ข้อความ) · มีเลขลีดแล้ว/ส่งจัดซื้อแล้ว = ปฏิเสธ · ติ๊กแชทที่เคยกด "ไม่ต้องจ่ายเบอร์" = ล้างป้ายนั้น
    · ติ๊กแชทที่ยังไม่มีเบอร์ได้ (แอดมินตัดสินแล้ว) แต่ข้อความบอกว่ายังไม่มีเบอร์ · เอาออกซ้ำ = ไม่พัง
  · API `POST /connect/api/assign_lead {id, park: true|false}` (แอดมินเท่านั้น — endpoint เดิม)
  · `in_room(lead)` = ตัวตัดสินเดียวกับ `to_code` สำหรับแถวเดี่ยว → `row_json.inRoom` / `parkedAt` / `parkedBy` ·
    `lead_json.park` / `roomAuto` · `inbox?view=tocode` ส่ง `roomAuto`
- **ระบบยังจับเบอร์/ID LINE/QR จากแชทลงข้อมูลลีดเหมือนเดิม** (`capture_contact`) — แค่ไม่ดันแชทเข้าห้องพักเอง
- **ทุกอย่างที่ใช้ `to_code` ตามไปเอง**: ตัวเลขแท็บ (`counts.tocode`) · แผน Run Auto (`crm.room_plan`) · `slip_sweep`
  (แชทที่ติ๊กแล้วได้เลขในชีต/ใบในกลุ่ม → ออกจากห้องเอง) · แท็บห้องพักในแอปมือถือ
- **หน้าเว็บ**: หัวแชทมีปุ่ม **"รับ lead"** (ไม่ต้องเลื่อนหาในแผงขวา) + ในแผงขวาเหนือกล่องจ่ายเบอร์ · ติ๊กแล้วขึ้น
  "อยู่ในห้องพัก Lead · ติ๊กรับ lead โดย …" + ปุ่ม "เอาออกจากห้องพัก" · รายชื่อแชท: ติ๊กแล้ว = **"รอจ่ายเบอร์"** ·
  ให้เบอร์แล้วแต่ยังไม่ติ๊ก = **"ให้เบอร์แล้ว"** (สีเทา) · การ์ดในห้องพัก: เวลาพักนับจากตอนติ๊ก + "ติ๊กรับ lead โดย …" +
  ลิงก์ "เอาออกจากห้องพัก" · แอปมือถือใช้ `inRoom` กับป้ายเดียวกัน (กดรับ lead ในแอปยังไม่มี — ใช้หน้าเว็บ)
- **ไม่มี migration** · deploy = `git pull` + restart · เทสต์ `test_connect.py` [34] (เทสต์เดิมที่ทดสอบกติกา 4 ต.ค.
  ตั้ง `room_chat_auto=True` ไว้ตอนต้น: test_connect / test_crm / test_chat_media)
- **แก้ไปพร้อมกัน**: `test_connect.py` ปิด `chatmedia.BG` — `tick()` เคยแตก thread โหลดรูปชน SQLite ("database table is locked" ใน [8] แบบสุ่ม)

### 🟧 ลูกค้าให้เบอร์แล้ว → เด้งขึ้นห้องพัก Lead "รอแอดมินกดรับ" — `connect.pending_park` · 11 ต.ค.69 (ค่ำ)
ผู้ใช้ *"ลูกค้าให้เบอร์แล้วไม่เด่นเลย เอางี้เด้งไปหน้าพักหลีดรอแอดมินกดรับละจ่ายต่อ"* — หลังเปลี่ยนเป็นโหมดติ๊ก
(หัวข้อข้างบน) แชทที่ระบบจับเบอร์/ID LINE ได้เหลือแค่ป้ายเทา "ให้เบอร์แล้ว" ในรายชื่อ → แอดมินมองข้าม
- **กลุ่มใหม่บนสุดของห้องพัก Lead → "ลูกค้าให้เบอร์/ID LINE แล้ว — รอแอดมินกดรับ N ราย"** → กด **"รับ lead"** (= `mark_park`
  ผ่าน API เดิม `assign_lead {id, park:true}`) → ลีดลงไปรายการรอจ่ายเบอร์ข้างล่างพร้อมปุ่มชื่อเซลล์ (จ่ายต่อแบบเดิม)
  · "ไม่ใช่ลีด" = `assign_lead {id, skip:true}` เดิม · "เปิดแชท" = ดูก่อนตัดสิน
- **`pending_park(qs, days=PENDING_DAYS)`** = กติกาเดียวกับห้องพักโหมดอัตโนมัติ (คุยในระบบแล้ว + ไม่มีเลข/ไม่ได้กดไม่ต้องจ่ายเบอร์/ไม่ได้ส่งจัดซื้อ
  \+ มีเบอร์หรือ ID LINE · `_engaged_q`/`_no_code_q`/`_contact_q` แยกออกมาใช้ร่วมกับ `to_code`) **แต่ยังไม่ได้ติ๊ก** ·
  **เฉพาะลูกค้าที่ทักภายใน `PENDING_DAYS`=3 วัน** (เก่ากว่านั้นยังติ๊กเองได้จากหัวแชท) · **`room_chat_auto` เปิด = ว่างเสมอ**
  (แชทพวกนี้อยู่ในห้องพักเองอยู่แล้ว) · `pending_one(o, lead)` = ตัวตัดสินแถวเดี่ยว
  · **`to_code()` ไม่เปลี่ยน** → Run Auto (`crm.room_plan`) / ตัวเลข `tocode` ไม่นับกลุ่มนี้ (ต้องให้แอดมินกดรับก่อน)
- **ป้ายในรายชื่อแชท (แอดมิน)**: `row_json.pendingPark` → ป้ายส้มทึบ **"ให้เบอร์แล้ว · รอรับ lead"** + ขีดส้มซ้ายแถว (`.cn-row.lead`)
  · ติ๊กแล้ว = "รอจ่ายเบอร์" เหมือนเดิม · เก่ากว่า 3 วัน = ป้ายเทา "ให้เบอร์แล้ว" เหมือนเดิม
- **API**: `inbox?view=tocode` ส่ง **`pending`** (แถวพร้อม `phone`/`lineId` · **ได้จากรูป QR ไม่ส่งลิงก์ออก** · เบอร์ซ้ำ `dup` ชุดเดียวกับการ์ดลีด)
  \+ `pendingDays` · `counts.pending` (แอดมิน) → ป้ายเมนูห้องพัก/`/connect/api/summary` บวกรวม · `view="pending"` ใช้ภายใน (เซลล์ขอไม่ได้)
- **`slip_sweep` กวาดกลุ่มนี้ด้วย** → ลีดที่แอดมินลงเลขในชีต/โพสต์ใบในกลุ่มแล้ว (`sheet_match`/`find_slip`) หายจากกลุ่มเองโดยไม่ต้องกด
- **แอปมือถือ**: แท็บห้องพัก (แอดมิน) มีการ์ดส้มกลุ่มเดียวกัน (รับ lead / ไม่ใช่ลีด / เปิดแชท · ดูอีก) · ป้ายแท็บ + "รอจ่ายเบอร์" ในหน้าภาพรวมบวก `pending`
- **ไม่มี migration** · วัด prod 11 ต.ค.69: ผู้สมัคร 144 ราย → ภายใน 3 วัน **73 ราย** (66 ราย = Facebook ที่ให้ ID LINE) · ภายใน 1 วัน 29
- **เทสต์**: `test_connect.py` [35] (671/671) · ตรวจ Chrome จริง 39/39 (จอ 1590/390 · กดรับ lead แล้วยิง `{id, park:true}` · ลงรายการจ่ายเบอร์พร้อมปุ่มเซลล์ ·
  ไม่ล้นจอ · ไม่มี JS error) · `test_crm`/`test_leadflow`/`test_chat_media`/`test_mobile_home`/`test_mobile_api` ผ่าน · แอป `tsc` + `expo lint` + bundle iOS ผ่าน

### 🔀 ลีดรับซื้อรถ vs ลีดขายรถ — แยกแท็บในห้องพัก Lead · `lead_keywords.deal_kind` · 11 ต.ค.69 (ค่ำ)
ผู้ใช้ *"มันจะมี lead รับซื้อรถกับ lead ขายรถด้วยนะ แยกไว้ด้วย"* — **ลีดขาย** = ลูกค้าอยากซื้อรถเรา (ห้องพัก → จ่ายเบอร์ NLD… ให้เซลล์ · ของเดิมทั้งหมด) ·
**ลีดรับซื้อ** = ลูกค้าอยากขายรถให้เรา (ทีมจัดซื้อ · ใบ "โค้ด : OC-…" ในกลุ่มเคสHOT) · เดิมปนกันในกลุ่ม "รอกดรับ" ทั้งที่ทางไปคนละทาง
- **ตัวจับ `lead_keywords.deal_kind(texts_in, texts_out)`** (ไม่ใช้ AI) → `{kind: "buy"|"", why, trade}` · ค่าตั้งต้นทุกลีด = ลีดขาย
  · คำชัด: อยาก/สนใจ/ต้องการ/จะ + ขาย · ขายรถ (ต้นข้อความ/หลัง "สอบถาม") · รับซื้อ · ประเมินราคา/รถ · ตีราคา · ขายได้เท่าไหร่ · ได้ราคาเท่าไร
  · **ห้ามนับ** (`_BUY_NOT`/`_JOB` · เจอจริงในแชท prod): สมัครงานเซล/ประสบการณ์/เคยขายรถ/นายหน้า/แอดมินรับซื้อ · รับซื้อทะเบียน/ป้ายขาว ·
    ร้านขายรถอยู่ไหน · ขายรถคันนี้ยัง · ประเมินเครดิต/วงเงิน · คำปฏิเสธนำหน้า ("ไม่ได้จะขาย")
  · **รถเทิร์น** (เทิร์น/เทริน/เพิ่มเงิน/แลกรถ · ไม่จับ "เทรนนิ่ง") = **ลีดขายเสมอ** (เขาจะซื้อรถเรา) + ป้าย "มีรถเทิร์น"
  · ยอดปิดไฟแนนซ์/มีเล่ม/เลขไมล์ พูดได้ทั้ง 2 ฝั่ง → ไม่ใช้ตัดสิน
  · วัดกับแชทจริง: ลีดที่มีใบเคสรับซื้อแล้ว **จับได้ 19/21** · ลีดขายที่ได้เลข **จับผิด 3/178** · ไม่ตรงที่เหลือ = คนพิมพ์แค่รุ่น+ไมล์ ไม่บอกว่าจะขาย
  · **★ 11 ต.ค.69 (ดึก) ข้อความ "ของเรา" ชี้ขาดได้เอง** — ผู้ใช้ส่งเคสจริง (FB: ลูกค้าส่งรูปรถ → แอดมินตอบ "จะประสานงานให้เจ้าหน้าที่
    ฝ่ายจัดซื้อติดต่อกลับ") แล้วสั่ง *"คนที่ส่งรูปรถมาเยอะๆ หลัง admin ขอดูรูปหรือเล่ม (หน้า 18)"* · แอดมิน/เพจใช้เทมเพลต
    "รบกวนลูกค้า ส่งภาพรถ ✅ ด้านนอก ✅ ด้านใน ✅ หน้าปัดให้เห็นเลขไมล์ ✅ สำเนาเล่มทะเบียน หน้า 4 และ หน้า 18 … เพื่อให้เจ้าหน้าที่ฝ่ายจัดซื้อประเมินราคา"
    → `_BUY_OUT` (ฝ่าย/ทีม/เจ้าหน้าที่จัดซื้อ · ราคารับซื้อ · สำเนาเล่ม · รูป/หน้าเล่ม · หน้า 4 และ 18) **ข้อความเดียวพอ** ·
    `_ASK_OUT` (ขอรูป/ภาพ · ส่งรูปรถ · ภายนอก-ภายใน · หน้าปัดเลขไมล์ — ไม่นับขอบัตร/สลิป/เงินเดือน) + **ลูกค้าส่งรูป ≥ `ASK_IMGS`=2 รูปหลังเราขอ**
    (นับจาก `events` ไทม์ไลน์ 2 ฝั่ง · `connect.deal_events(messages())`) · วัด prod: ข้อความของเราเจอใน **12/21** ลีดรับซื้อ · ลีดขาย **0/179**
  · ⚠️ **เทิร์นที่ "เรา" พูดไม่ชี้ขาด** (แอดมินถาม "ลูกค้าเอารถรุ่นไหนมาเทิร์นครับ" 36 แชท) — ใช้เฉพาะที่ลูกค้าพูด · ข้อความของเราที่พูดเรื่องเทิร์น
    ("การเทิร์นจะเป็นเจ้าหน้าที่จัดซื้อประเมินราคา") ไม่นับเป็นสัญญาณรับซื้อ · ห้ามใช้คำลอยๆ อย่าง "รอบคัน" (โดนข้อความโฆษณา "ชุดแต่งรอบคัน")
  · ⚠️ **LINE: แอดมินตอบในแอป LINE OA Manager → LINE ไม่ส่งกลับมา** (ขาออกในฐานข้อมูลมีแค่ 4 ข้อความ) → กติกาข้อความของเราใช้ได้กับ Facebook
    และแชทที่ตอบผ่าน Connect เท่านั้น · LINE ต้องพึ่งคำที่ลูกค้าพิมพ์
  · **เก็บตกแชทเก่า** `manage.py connect_deal_scan [--apply] [--days 30] [--out ไฟล์]` (`connect.scan_deals` · ไม่ใส่ `--apply` = ดูเฉยๆ ·
    รายงานอ้าง ChatOwner.id ปิดเบอร์ · ไม่แตะที่คนตั้งไว้) — แชทที่คุยก่อน deploy จัดประเภทเองเฉพาะตอนข้อความใหม่เข้า/เปิดแชท
- **เก็บใน `ChatLead.auto`** (ไม่ต้อง migrate): `_buylead` {by, at, why} (by "ระบบ" = จับจากแชท) · `_selllead` {by, at} (คนยืนยันลีดขาย → ระบบไม่เดาทับ) ·
  `_trade` {why, at} · `deal_of(lead)` = "buy" ถ้ามี `_buylead` หรือ `_buy` (ส่งจัดซื้อแล้ว)
  · `apply_deal_kind` เรียกใน `capture_profile` (ข้อความเข้า · อ่านทั้งขาเข้า/ขาออก) + `autofill` · **ไม่จัดเป็นรับซื้อ** เมื่อมีเลขลีดขาย /
    คนตั้งลีดขาย / ติ๊กรับ lead แล้ว · ระบบจัดไว้แล้วลูกค้าพูดถึงเทิร์นทีหลัง = กลับเป็นลีดขาย (ที่คนตั้งไม่แตะ)
- **ห้องพัก Lead**: `to_code`/`pending_park`/`in_room`/`pending_one` ตัดลีดรับซื้อออก (`_sell_q`) → Run Auto (`crm.room_plan`) ก็ไม่จ่ายลีดรับซื้อ ·
  **แท็บ "รับซื้อรถ"** = `buy_room()` (คุยในระบบแล้ว + เบอร์/ID LINE + ยังไม่มีใบเคสรับซื้อ + ทักภายใน `BUY_ROOM_DAYS`=14 วัน · **ไม่ต้องกดรับก่อน**)
  · `inbox?view=tocode` ส่ง `buyRoom` (เบอร์/ID ลูกค้า · รถที่พูดถึง · `dealWhy`/`dealBy` · `slip` = ใบเคสรับซื้อ) + `buyLast` (เลข OC/SC ล่าสุดในกลุ่มเคสHOT) ·
    `counts.buyroom` (ป้ายเมนูห้องพัก + แอป) · `view=buyroom` ใช้ภายใน (เซลล์ขอไม่ได้)
  · **ไม่ออกเลข OC ให้เอง** — แค่บอกเลขล่าสุด (`last_buy_code`) · ใบที่คัดลอก (`buy_slip_text`) เว้นเลขโค้ดว่าง · เหตุผล: tradein.py กันซ้ำด้วยรหัส เลขชน = เคสหาย
  · แอดมินโพสต์ใบในกลุ่มเคสHOT → `slip_sweep` (ตอนนี้กวาดแท็บรับซื้อด้วย) เจอใบ (`find_buy_slip`) → `_buy` → ออกจากแท็บ + ขึ้น "จ่ายแล้ว" เป็นส่งจัดซื้อ
- **แอดมินตั้งเอง** `POST /connect/api/assign_lead {id, kind:"buy"|"sell"}` (`set_deal_kind` · แอดมินเท่านั้น) — เป็นลีดรับซื้อ = ล้างติ๊กรับ lead/ไม่ต้องจ่ายเบอร์ ·
  มีเลขลีดขายแล้ว / ส่งจัดซื้อแล้ว = ปฏิเสธ · `mark_park` กับลีดรับซื้อ = ปฏิเสธพร้อมบอกให้เปลี่ยนเป็นลีดขายก่อน
- **หน้าเว็บ**: ห้องพัก Lead มีแท็บ **รับซื้อรถ N** (คัดลอกใบเคสรับซื้อ / เป็นลีดขายรถ / ไม่ใช่ลีด / เปิดแชท) · กลุ่มรอกดรับมีลิงก์ "ลีดรับซื้อ" + ป้ายมีรถเทิร์น ·
  รายชื่อแชทมีป้าย **"ลีดรับซื้อ · รอส่งจัดซื้อ"** (เขียว) / "มีรถเทิร์น" · แผงขวาของลีดรับซื้อ = กล่องเขียว (ที่มา + ใบเคสรับซื้อ + ปุ่ม) แทนกล่องจ่ายเบอร์ ·
  หัวแชทไม่มีปุ่มรับ lead/จ่ายเบอร์ · แผงลีดขายมีลิงก์ "ย้ายไปเป็นลีดรับซื้อรถ"
- **แอปมือถือ** (ห้องพัก): แท็บ "รับซื้อรถ" — ปุ่ม **ส่งใบเคสรับซื้อ** ใช้ Share ของระบบ (ส่งเข้า LINE กลุ่มเคสHOT ได้ตรง · ไม่ต้องลงไลบรารีคลิปบอร์ด) ·
  กลุ่มรอกดรับมี "ลีดรับซื้อ" · ป้ายแท็บ/หน้าวันนี้นับ `buyroom`
- **ยังไม่ได้ทำ**: ส่งใบเคสรับซื้อเข้ากลุ่มเคสHOT ให้เองพร้อมแท็กพี่หมี/พี่ต๊าด (ต้องให้เจ้าของเคาะเรื่องออกเลข OC กับเลือกกลุ่มตามวัน) ·
  ลีดภายนอก (ใบร่างกลุ่ม ADMIN เก็บ Lead) ยังไม่แยกรับซื้อ/ขาย
- **ไม่มี migration** · **เทสต์**: `test_lead_keywords.py` [8]+[9] (101/101 · ข้อความจริงจากแชท) · `test_connect.py` [36]+[36b] (710/710 · เคส Bryan บน FB ผ่าน API จริง · คำสั่งเก็บตกดูเฉยๆ/apply/รันซ้ำ) · Chrome จริง 42/42 (จอ 1590/390 ·
  คัดลอกใบเคสรับซื้อแล้วอ่านกลับด้วย `parse_buycase` ได้ · ยิง `{id, kind}` ถูก · ไม่ล้นจอ · ไม่มี JS error) · `test_crm`/`test_leadflow`/`test_chat_media`/
  `test_mobile_home`/`test_mobile_api` ผ่าน · แอป `tsc` + `expo lint` + bundle iOS ผ่าน

### 🖍️ คำที่ระบบจับได้ในแชท — ไฮไลต์ · ป้ายที่มา · ค่าใหม่รอคนตัดสิน · ความพร้อม · ตอบด่วน (12 ต.ค.69)
ผู้ใช้ให้ค้นว่า CRM ทั่วไปทำหน้าแชทยังไง → ทำเดโมเป็น artifact (https://claude.ai/artifact/C7X4iveyfpnQWY2Rmh6m7d · ข้อมูลสมมติ)
→ เจ้าของเลือก *"เอาแบบนี้แหละ แก้ไขเลย"* · **ตัวจับ keyword ไม่ได้เปลี่ยน** (ไม่ใช้ AI เหมือนเดิม) — ที่เพิ่มคือ "ให้คนเห็น" ว่าระบบจับอะไรจากไหน
- **ไฮไลต์คำในแชท** — `connect.add_spans(msgs, lead)` (เรียกใน `api_chat` เฉพาะคนที่เห็นแชทเต็ม) ใส่ `m["hl"] = [[เริ่ม, จบ, ช่อง]]`
  · ใช้ตัวจับชุดเดิมทั้งหมด: เบอร์ (`_PHONE_RE`) · ID LINE (`_LINE_ID_LABEL` / ลิงก์ line.me / คำเดียวหลังเราขอไอดี) · รถ (`car_in` + `car_phrase` ทีละคำ) ·
    อาชีพ/รายได้/อายุงาน/ประวัติผ่อน/สถานะ (`lead_keywords.spans`) · ขาย/รับซื้อ/ฝ่ายจัดซื้อ/เทิร์น (`lead_keywords.deal_spans` — ไฮไลต์เฉพาะลีดที่เป็นรับซื้อ/มีเทิร์นจริง)
  · **`lead_keywords.norm_map()`** = `norm()` ที่จำตำแหน่งในข้อความเดิม (พนง.→พนักงาน · ตัวอักษรล่องหน · สระพิมพ์ซ้อน) → ไฮไลต์ตรงคำที่ลูกค้าพิมพ์จริง
  · **ตำแหน่งส่งเป็น UTF-16** (`_u16` · แบบเดียวกับ JS) — อีโมจินำหน้า = นับ 2 ในเบราว์เซอร์ ไม่แปลงแล้วไฮไลต์เลื่อนทับคำข้างๆ (มีเทสต์)
  · จำผลต่อข้อความใน `_SPANS` (เพดาน 20,000 · ข้อความแชทไม่เปลี่ยน แต่หน้าแชทรีเฟรชทุก 6 วิ) · `lead_keywords._extract_one` lru_cache
  · `messages()` เพิ่ม **`id`** (`l<pk>`/`f<pk>`) ทุกข้อความ — ไม่ใช่ LINE id
- **หน้าเว็บ** ([connect.html](checkout/templates/checkout/connect.html)): คำระบายสี 4 หมวด (ติดต่อ `kw-c` · รถ `kw-r` · การเงิน `kw-m` · เจตนา `kw-i`)
  · **กดคำ = ไปช่องข้อมูลที่คำนั้นลง** (`kwGo` · เปิดคอลัมน์ขวาที่ซ่อนไว้/กางแบบพับบนจอแคบ · กรอบกระพริบสีหมวด)
  · **ช่องที่ระบบเติมจากแชท = ป้าย "จากแชท 14:02" กดแล้วย้อนไปข้อความต้นทาง** (`kwSrc`/`kwFindMsg` เทียบคำที่จับได้ `autoWhy` / เบอร์ / ID ก่อน) — ป้ายเดิม "จากแชท" ไม่มีเวลา กดไม่ได้
  · **กล่องความพร้อม** บนสุดของแผงขวา (`kwBoxHtml`): ลีดขาย "ข้อมูลพร้อมจ่ายเบอร์ x/5" (เบอร์/ไลน์ · รถ · อาชีพ+รายได้ · อายุงาน · ประวัติผ่อน ·
    มีเลขแล้ว = "ข้อมูลลูกค้าสำหรับไฟแนนซ์") · ลีดรับซื้อ "พร้อมส่งจัดซื้อ x/3" (เบอร์/ไลน์ · รุ่น+ปี · รูป ≥2) + **ประโยคถามต่อ + "ใส่ในช่องพิมพ์"** + สวิตช์ไฮไลต์ (localStorage `cn_hl`)
  · **แถบตอบด่วนเหนือช่องพิมพ์** (`paintQuick` · `#cn-qr-wrap`) — ข้อที่ขาดขึ้นก่อน · **กดแล้วแค่ใส่ช่องพิมพ์ ไม่ส่งเอง** · คำลงท้าย ครับ/ค่ะ (localStorage `cn_pt` ·
    `{q}`=ครับ/คะ `{p}`=ครับ/ค่ะ ใน `KW_ASK`) · โชว์เฉพาะคนที่ตอบได้ (`canReply && replyOn`)
  · `refreshKw()` วาดเฉพาะกล่องความพร้อม/ค่าใหม่ใหม่ตอนคนแก้ช่อง (ไม่วาดทั้งแผง — คนอาจกำลังพิมพ์ช่องถัดไป) · ลายเซ็นแผง (`profSig`) รวมจำนวน/ข้อความล่าสุดด้วย
- **★ ค่าใหม่รอคนตัดสิน** — เดิมช่องที่ระบบเติมจากแชท "เติมครั้งเดียว" → **ลูกค้าแก้ค่าทีหลัง ค่าใหม่หายเงียบ** · ตอนนี้เก็บที่
  `ChatLead.auto["_sugg"] = {ช่อง: {v | opts, why, from, at}}` (ไม่ต้อง migrate) แล้วแผงขวาขึ้นกล่องส้มให้เลือก
  · **อาชีพ/รายได้/อายุงาน** (`SUGG_FIELDS` · `_suggest` ใน `apply_keywords` — ใช้ `lead_keywords.latest()` = ค่าจากข้อความ **ล่าสุด**) ·
    **เบอร์ใหม่** ที่ลูกค้าพิมพ์ทีหลัง · **รุ่นกว้าง ("city") → ตัวเลือกรุ่นย่อยของชีต** (`_model_choices` จาก `_vocab().bases` · 2–8 ตัวเลือก) — ใน `autofill`
  · ถามเฉพาะช่องที่ **ระบบเติมจากแชท** (`auto[f] == "แชท"`) · ช่องที่คนแก้แล้วไม่ถามเลย · สถานะลูกค้าไม่อยู่ในนี้ (เปลี่ยนตามข้อความล่าสุดเองอยู่แล้ว)
  · **ใช้ค่าใหม่ / คงค่าเดิม** = `POST /connect/api/lead {id, field, value}` ตามปกติ → ช่องเป็น "คน" + `save_lead_field` ล้างกล่องของช่องนั้น
  · **"ยังไม่รู้"** = `{id, field, dismiss: true}` → `dismiss_suggestion` จดที่ `auto["_sugg_no"]` (ไม่ถามค่านั้นซ้ำ · ค่าในช่องไม่เปลี่ยน · ระบบยังเปลี่ยนเป็นรุ่นจริงได้ตามกติกาเดิม)
  · `capture_profile` (ข้อความเข้า) save แบบ `update_fields` กรองเฉพาะช่องจริง (`_sugg` ไม่ใช่คอลัมน์) · `lead_json.sugg` ไม่ส่งช่องที่คนแก้แล้ว
- **แอปมือถือ** (`src/lib/kw.tsx` + `chat/[id].tsx`): ไฮไลต์คำในบับเบิล (แตะ = เปิดแผงชี้ช่องนั้น) ·
  แถบ "ระบบจับได้ N ช่อง · รอยืนยัน M · พร้อมจ่ายเบอร์ x/5" แตะเปิดแผง (ความพร้อม · ค่าใหม่ใช้/คง/ยังไม่รู้ · ช่องที่ระบบเติม + "แชท 14:02" ย้อนไปข้อความ) ·
  แถบตอบด่วน + ครับ/ค่ะ · **ใช้ API ตัวเดียวกับเว็บ ไม่มี API ใหม่**
- **★ บั๊กเก่าที่ไฮไลต์ทำให้เห็นทันที (แก้แล้ว)**: "ผ่อน**ได้เดือนละ 7,000**" ถูกอ่านเป็นรายได้ (`_INCOME_KW` มี "ได้ เดือนละ") → `income_in`
  ข้ามคำบอกรายได้ที่มี ผ่อน/งวด/ดาวน์/จ่าย นำหน้า · **นี่คือประโยชน์ของการไฮไลต์ — ตัวจับอ่านผิดตรงไหน คนเห็นทันที**
- **ไม่มี migration** · ไม่มีอะไรส่งออกนอกระบบเพิ่ม · **เทสต์**: `test_lead_keywords.py` [10] (115/115) · `test_connect.py` [37] (ผ่าน API จริง · อีโมจิ · ใช้/คง/ยังไม่รู้ ·
  ข้อความเข้าเก็บค่าใหม่ทันที · ลีดรับซื้อไฮไลต์ฝ่ายจัดซื้อ · เซลล์ที่ไม่ใช่เจ้าของไม่ได้ไฮไลต์/ข้อมูลลีด · ไม่มี LINE id หลุด) ·
  Chrome จริง 61/61 (จอ 1590/1180/390 · กดคำ → ช่องกระพริบ · กดป้าย → ข้อความกระพริบ · ตอบด่วนไม่ส่งเอง · ไม่ล้นจอ · ไม่มี JS error) ·
  `test_crm`/`test_leadflow`/`test_chat_media`/`test_mobile_home`/`test_mobile_api` ผ่าน · แอป `tsc` + `expo lint` + bundle iOS ผ่าน (ยังไม่ได้ลองบนเครื่องจริง)

### 🗂️ แผงขวาของแชท = "เก็บข้อมูลจากแชท" 4 หัวข้อบนสุด (17 ต.ค.69 · เจ้าของสั่ง)
เจ้าของส่งสเปก *"ฝั่งขวาเก็บข้อมูล — เก็บข้อมูลจากแชทที่คุย Ai ดูดข้อมูล auto กรอกให้ / หรือแอดมิน copy จากแชทกรอกมือได้ ถ้า ai error
-รุ่นรถที่สนใจ -เบอร์/ไลน์ ติดต่อ -ประวัติลูกค้า -นัดดูรถ"* แล้วเลือก **"4 หัวข้อขึ้นบนสุด"** + **"ไม่ใช้ AI"** (ใช้ตัวจับคำในเครื่องชุดเดิม)
- **บนสุด** ([connect.html](checkout/templates/checkout/connect.html) `profileHtml`): กล่อง **"เก็บข้อมูลจากแชท x/4"** (`chatCapHtml` · ติ๊กว่าเก็บหัวข้อไหนแล้ว
  \+ สวิตช์ไฮไลต์/คำอธิบายสีย้ายมาจากกล่องความพร้อม) → ค่าใหม่รอคนตัดสิน (`kwSuggHtml`) → 4 หัวข้อ (`.pf-q[data-q]` · หัวข้อมีป้ายสถานะ `data-qst`):
  1. **รุ่นรถที่สนใจ** — รถลูกค้าถาม · CAR/สูตร · รถที่ลูกค้าหา (CustomerNeed) · รถพร้อมขายที่ตรง (ย้ายมาจาก crmHtml) · ป้ายมีรถเทิร์น
  2. **เบอร์ / ไลน์ ติดต่อ** — เบอร์ · ID LINE · เบอร์อื่นที่เจอในแชท (กดใช้) · ปุ่มโทร
  3. **ประวัติลูกค้า** — อาชีพ/รายได้ · อายุงาน/ประวัติผ่อน · ประเภท/สถานะลูกค้า · PROFILE จาก ADMIN (ครบ = 4 ช่องแรก)
  4. **นัดดูรถ** (`apptHtml` · ย้ายมาจาก crmHtml) — นัดที่ค้าง (รวมนัดติดตาม ไม่งั้นหายจากแผง) · ฟอร์มนัด **ค่าเริ่มต้น = นัดดูรถ** (เดิมนัดติดตาม)
- **พับไว้ใน `<details class="pf-more">` "ข้อมูลเพิ่มเติม"** (ป้ายบนหัวบอกเลขลีด/ลีดรับซื้อ/ขั้น · `moreBadge`): ความพร้อม x/5 · ขั้นของลีด · โทร · สรุป ·
  ใครเคยดูแล · ช่องคำนวณ (ผู้รับผิดชอบ/วันที่) · กล่องจ่ายเบอร์/รับ lead/ลีดรับซื้อ · นาฬิกาโทร · ช่องอื่นของชีต (`LEAD_UI` เหลือ ลูกค้า + ข้อมูลลีด) · ใบจ่ายลีด
  · คนกาง/พับเอง = จำใน localStorage **`cn_more`** · **ระบบกางให้** (`openMore()` — ปุ่ม "จ่ายเบอร์" บนหัวแชท `goAssign` / กดคำในแชท `kwGo`) **ไม่จำ** (`_moreAuto`)
  · **ช่องแต่ละช่องอยู่ที่เดียวเท่านั้น** (`LEAD_TOP` + `LEAD_UI` · data-f ซ้ำ = 2 ช่องค่าไม่ตรงกัน)
- **"ลูกค้าพูดถึงนัด"** — **`crm.appt_hint(o, msgs)`** (ไม่ใช้ AI · ตัวอ่านวันนัดชุดเดียวกับรายงานผล `leadflow.parse_appt`) → `api_chat` ส่ง **`crm.apptHint`**
  = `{at, text, mid, dir}` · ดูข้อความล่าสุด `HINT_MSGS`=40 ใน `HINT_DAYS`=3 วัน ใหม่→เก่า · ต้องมีคำนัดดูรถ (`_VIEW_KW`) หลังตัดคำนัดโทร (`_CALL_KW` — "นัดโทรกลับ" ไม่ใช่นัดดูรถ) ·
  "พรุ่งนี้" นับจากวันที่ส่งข้อความ · เวลาผ่านไปแล้ว = ไม่เสนอ · **มีนัดดูรถค้างอยู่ = ไม่เสนอ** · ทั้งข้อความลูกค้าและที่เราพิมพ์ยืนยัน
  · หน้าเว็บ: **"ใส่ในฟอร์มนัด"** (เติม `S.apptDraft` · ยังไม่บันทึก — คนตรวจแล้วกด "บันทึกนัด") · "ดูในแชท" · "ไม่ใช่นัด" (ซ่อนในหน้านี้ `S.hintNo`)
- **⚠️ ชื่อฟังก์ชันใน connect.html ชนกันได้เงียบๆ** — รอบแรกตั้งชื่อ `capHtml` ซ้ำกับของห้องพัก Lead (มือเซลล์วันนี้) → function ที่ประกาศทีหลังชนะ
  กล่องบนสุดกลายเป็น "ยังไม่มีเซลล์ในทีมของคิวจ่ายวน" · **เพิ่มฟังก์ชันใหม่ให้ grep ชื่อก่อนเสมอ**
- ไม่มี migration · แอปมือถือไม่ได้แก้ (แผงนี้เป็นของเว็บ) · **เทสต์**: `test_crm.py` [17 ต.ค.69] (13 ข้อ · 158 รวม) · Chrome จริง 19/19
  (ลำดับ 4 หัวข้อ · ไม่มีช่องซ้ำ · ใส่ในฟอร์มนัดแล้วไม่หายตอนแชทรีเฟรช · บันทึกนัดแล้วติ๊ก · ปุ่มจ่ายเบอร์กางให้ · จอ 1400/390 ไม่ล้น · ไม่มี JS error)

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

### 🎓 ห้องโค้ชเซลล์ (Senior ↔ Junior) — [coaching.py](checkout/coaching.py) · 27 ก.ย.69
*"กลุ่มนี้จะเป็น chatbot ในการถามตอบของ AI ระหว่าง Senior กับ Junior ตอนนี้ฉันได้ปิดระบบ
การใช้งานไปแล้ว … แต่ฉันอยากให้เก็บข้อมูลของ Senior และ Junior ต่อไปนี้ไว้ด้วย …
เอาข้อมูลเก่าใส่เข้ามาด้วย"* (เจ้าของเลือก **"เก็บข้อเท็จจริงก่อน ไม่ต้องมี AI"**)

- **กลุ่ม `C7d9fd79e5658470e23f62a8fd1f12670` "Sale Coaching Room Oxlet auto"** (`channels: ["push"]`)
  · ชื่อจริงในทะเบียนไม่ใช่ "OutletAuto" ตามที่เจ้าของพิมพ์
- **ซีเนียร์ = อุ้ม · เฟิร์ส · โอ๊ต · นวล** (`DEFAULT_SENIORS` · แก้ได้ด้วย `--seniors` ไม่ต้อง deploy)
  · ยืนยันแล้วว่าทั้ง 4 คนอยู่ในทะเบียน ไม่มีชื่อซ้ำ · **ระวัง เฟิร์น (ออฟฟิศ บ้านเก่า) ≠ เฟิร์ส (ทีม A)**
- **การเก็บดิบทำงานอยู่แล้ว** — `checkout_line_config.store_chat = true` เก็บ *ทุกกลุ่มที่บอทอยู่*
  ลง `checkout_groupchat` → **ไม่มีอะไรหายตั้งแต่บอทเข้ากลุ่ม** · ที่ขาดคือ "แยกซีเนียร์/จูเนียร์"
  กับ "บันทึกถาวรที่คนอ่านได้"
- **★★ ต้องซิงก์ประจำ เพราะแชทดิบถูกลบเมื่อครบ 90 วัน** (`CHAT_KEEP_DAYS`) → **ชีตเป็นตัวถาวร**
  · `cron_tick` เรียก `maybe_sync()` **วันละครั้ง** (KV `coach_sync_last` · ปิดไว้ = ไม่ทำอะไร)
  · ไม่มีตัวนี้ = ข้อมูลโค้ชหายเองเงียบๆ (ของเดิมมีย้อนหลัง 4 เดือนแล้ว)

**★ ทำไมเลิกใช้คอลัมน์เดิม (เจ้าของเปิดทางให้ออกแบบใหม่)**
แท็บ `Sheet A — Log` มี **คอลัมน์ซีเนียร์ 4 ช่องฮาร์ดโค้ด** (`เฟิร์ส | โอ๊ต | นวล | อุ้ม`)
→ กรอกจริง **192 จาก 1,424 แถว (13%)** = ว่างเป็นส่วนใหญ่ **และเพิ่มซีเนียร์คนที่ 5 ต้องแก้โครงตาราง**
· แท็บใหม่ **`บันทึกโค้ช`** เป็น **1 แถว = 1 ข้อความ**:
`วันที่ | เวลา | รหัสเคส | ผู้พูด | บทบาท | ทีม | ข้อความ | สถานะเคส | ชนิด | ที่มา | หมายเหตุ | รหัสอ้างอิง`
→ เพิ่มคนไม่ต้องแก้อะไร · Pivot นับได้ว่าใครตอบกี่เคส ใครถามบ่อย
· **เพิ่มคอลัมน์ให้ต่อท้ายเสมอ** (ของเดิมในชีตจะไม่เลื่อน) · `หมายเหตุ` เก็บของเก่า (ระดับ A/B/C ·
อัปเดตกี่ครั้ง) **แทนที่จะทำคอลัมน์ที่ว่าง 95%** ซึ่งคือข้อเสียเดิมที่กำลังแก้

**★ กติกาที่ต้องรักษา**
- **เขียนต่อท้ายเท่านั้น (append) ไม่เคย clear/PUT** — `Sheet A — Log` เดิม **ห้ามแตะ** (ประวัติ 1,424 แถว)
  · แท็บใหม่ต้องไม่เสียแถวที่คนเข้าไปแก้มือ · **มีเทสต์ยืนยันว่าไม่เคยเรียก `:clear` และไม่ใช้ PUT**
- **กันเขียนซ้ำด้วยคอลัมน์ `รหัสอ้างอิง`** (`line:<message_id>` · `old:<แถว>:<ช่อง>`) → รันซ้ำกี่ครั้งก็ได้
  (ต่างจาก `meta_sync`/`tiktok_sync` ที่ "ลบชุดของวันนั้นก่อนเขียน" — ที่นี่ชีตมีคนแก้มือ ลบไม่ได้)
- **ไม่โชว์ LINE user id** (กติกาเดิมทั้งโปรเจกต์) · **ไอดีในชีตเก่าใช้เทียบไม่ได้เลย** เพราะเป็นของ
  **บอทตัวที่ 3 (chatbot โค้ชที่ปิดไปแล้ว)** — ไอดีออกต่อ provider → **นำเข้าของเก่าต้องจับคู่ด้วยชื่อ**
- **★ ห้ามทำ fuzzy/substring match เด็ดขาด** — วัดจริง 27/09: `Mod🐜 Oxlet Auto` จะไปจับ **`เอ็ม`**
  (คนละคน) เพราะ `m` เป็น substring · ตัดคำต่อท้าย ("OxletAuto") ก็ไม่ช่วยเลยสักชื่อ (ทดสอบแล้ว)
  → เทียบตรงตัวเท่านั้น ไม่เจอ = **ใช้ชื่อที่ตั้งใน LINE (ล้างอิโมจิแล้ว) ตามเดิม** ไม่เดา
- **`_norm_nick` ใช้ NFC ไม่ใช่ NFKC** — บทเรียนเดิม: NFKC แยกสระ `ำ` ทำให้ "ดำ" เทียบไม่ตรง
- **`_esc()` กัน Google Sheets ตีข้อความเป็นสูตร** — เขียนด้วย `USER_ENTERED` (ให้วันที่/เวลาเป็นค่าจริง
  เรียง-Pivot ได้) แต่แบบนั้น `=1+1` จะกลายเป็นสูตร และ `-ครับ` เป็น `#ERROR!`
  → ใส่ `'` นำหน้าเมื่อขึ้นต้นด้วย `= + - @` · **ข้อความจาก LINE ขึ้นต้นแบบนี้ได้จริง**
- **เรียง `sent_at, id`** — ข้อความในกลุ่มมาวินาทีเดียวกันได้ ถ้าเรียงแค่เวลา ลำดับจะสลับทุกครั้งที่รัน
  แล้วแถวในชีต (เขียนต่อท้ายอย่างเดียว) จะไม่เรียงตามบทสนทนาจริง
- **ไม่ส่งข้อความหาใคร** — โมดูลนี้อ่านกับเขียนชีตเท่านั้น (ระบบถามตอบ AI เจ้าของปิดแล้ว)

**คำสั่ง**: `manage.py coach_log [--dry-run] [--import-old] [--sync] [--days N] [--group Cxxx]
[--seniors "อุ้ม,เฟิร์ส"] [--on|--off] [--out ไฟล์]`
· ไม่ใส่อะไร = โชว์สถานะ + นับแชทที่เก็บไว้ · **`--dry-run --import-old` ก่อนเสมอ**
· ⚠️ console ไทยบน Windows เพี้ยน (cp874) → ใช้ `--out`

**★ ผลนำเข้าจริง 27 ก.ย.69 (ทำแล้ว · ไม่ต้องรันซ้ำ)** — ชีตเก่า **1,424 แถว → 1,688 แถวในแท็บใหม่**
(ช่วง 1 เม.ย. – 23 ก.ค.69) แตกเป็น: ข้อความจูเนียร์ 1,416 · **ความเห็นซีเนียร์ 196**
(เฟิร์ส 154 · อุ้ม 22 · โอ๊ต 13 · นวล 7) · คำตอบบอท AI ตัวเดิม 39 · **ช่องที่ใช้ผิด 37**
· ตรวจแล้ว: ไม่มี `#ERROR!` · ไม่มีรหัสอ้างอิงซ้ำ · **ไม่มี LINE user id หลุดสักตัว** · รันซ้ำได้ 0 แถวใหม่

**⚠️ 3 เรื่องของข้อมูลเก่าที่ต้องรู้**
1. **ชีตเก่าเป็น 3 ยุคปนกันในแท็บเดียว**: ยุค AI ทำงาน ~69 แถว (มีระดับ A/B/C + ความเห็นซีเนียร์) ·
   ขยะ 4 แถว (มีแต่วันที่+รหัส) · **log ดิบ ~1,350 แถว** ซึ่ง **คือสิ่งที่ `checkout_groupchat` ทำอยู่แล้ว**
2. **คอลัมน์ "ประเภทเหตุการณ์" ถูกใช้ผิด 37 แถว** — มีทั้งคำแนะนำซีเนียร์ ("เค้าซื้อสดหรือจัดเคสนี้")
   และคำบรรยายเคสของจูเนียร์ปนกัน → **ลงเป็น `(ไม่ระบุ)` / `(ไม่ทราบ)` + ที่มา `ชีตเดิม-ช่องผิด`
   ให้คนไปตรวจเอง ไม่เดาว่าใครพูด** · ค่ามาตรฐานที่ควรอยู่ในช่องนี้อยู่ใน `KNOWN_TYPES`
3. **วันที่ปนกัน 4 แบบ**: `17/04/2569` (พ.ศ. 1,285 แถว) · `10/4/2026` · `2026-04-03` · `01/04/26`
   → `_old_date()` แปลงเป็น `YYYY-MM-DD` ทั้งหมด · แปลงไม่ได้ = **คืนค่าเดิม ไม่ทิ้งแถว**
   · `_clean_old_code()` ล้าง `"9057 (no code)"` → `9057` และขีดนำหน้า `-4093` → `4093` (22 แถว)

**⚠️ ชื่อที่จับคู่กับทะเบียนไม่ได้ 7 ชื่อ (561 แถว) — เป็นช่องว่างใน *ทะเบียน* ไม่ใช่บั๊กโค้ด**
`GoLF⛳️`(197) · `Mod🐜 Oxlet Auto`(173) · `Anxmb OxletAuto`(73) · `SaiSia`(47+9) ·
`ใบตองเซลล์ทีชอบขาย🚘`(33) · `TW②`(29) → แถวยังเข้าครบ แต่คอลัมน์ **ทีม ว่าง** (509 แถวที่รู้ทีม)
· แก้ได้ที่ **เมนู → พนักงาน** (เติม "ชื่อที่ตั้งใน LINE" ให้ตรง) แล้วรอบซิงก์ถัดไปคนใหม่จะได้ทีม
· **แถวเก่าที่เขียนไปแล้วไม่ถูกเติมย้อนหลัง** (กติกากันเขียนซ้ำข้ามไป) — จะเติมต้องแก้ในชีตเอง

**⚠️★ 29 ก.ย.69 — 2 เรื่องที่เจอตอนซิงก์ข้อมูลจริงรอบแรก (แก้แล้ว)**

**1. รหัสเคสอยู่ "ต้นบรรทัด" ไม่ใช่ "ต้นข้อความ" → จับไม่ได้เลยสักเคส**
- ของจริงในห้องโค้ชคือ **รายงานประจำวัน 1 ข้อความ = หลายเคส** ขึ้นต้นด้วย
  `รายงานเคสวันที่ 28/9` **เสมอ** แล้วรหัสอยู่บรรทัดถัดๆ ไป
  (`8029 ยังไม่ทราบโปรไฟล์…` ขึ้นบรรทัดใหม่ `8074 เงินเดือนประมาณ 20,000…`)
- `_CODE_BARE_HEAD` เดิมใช้ `.match()` ยึดต้นข้อความ → **วัดจริง: 6 จาก 7 ข้อความมีรหัสเคส
  แต่คอลัมน์ "รหัสเคส" ว่างทั้งหมด** · แก้เป็น `re.M` + `finditer` → ได้ 5/7 แถวมีรหัส
- **`case_code()` คืนได้หลายรหัส คั่นด้วยช่องว่าง** (`"8029 8074 8059"`) เพราะรายงานเดียว
  คร่อมหลายเคสจริง — คืนรหัสแรกตัวเดียวจะบอกความจริงไม่ครบ
  · **ผลพลอยได้: คอลัมน์นี้ Pivot ตรงๆ ไม่ได้ ต้องแยกช่องว่างก่อน** · อยากได้ 1 แถว/เคส
    ต้องแตกแถวตอนเขียน (ref เป็น `line:<mid>#<รหัส>`) — **ยังไม่ได้ทำ**
- **ต้องแก้ก่อนเขียนแถว ไม่ใช่แก้ทีหลัง** — ชีตนี้เขียนต่อท้าย + กันซ้ำด้วย `รหัสอ้างอิง`
  → **แถวที่เขียนไปแล้วด้วยรหัสว่าง จะไม่มีอะไรมาเติมย้อนหลังให้ตลอดไป**
- กติกากันจับผิดยังอยู่: ต้องเป็น **ต้นบรรทัด + 4-5 หลัก** → `ลูกค้าอายุ 32 ปี ผ่อนไหว 13000`
  (กลางบรรทัด) และ `28/9/69` (สั้นกว่า 4 หลัก) ไม่ถูกจับ

**2. ★★ prod กับเครื่อง dev ใช้ service account คนละตัว — "เขียนชีตได้ในเครื่อง" ≠ "prod เขียนได้"**
| | ไฟล์พนักงาน/ตั้งค่า | ไฟล์โค้ช |
|---|---|---|
| `google-account-oxletauto@gen-lang-client-0431582933…` (**ค่าตั้งต้นใน settings.py = prod ใช้ตัวนี้**) | writer | **ไม่มี → 403** |
| `n8n-sheets@sylvan-road-477705-q4…` (`.env` ในเครื่องทับไว้) | writer | writer |
| ใครมีลิงก์ | **writer** ← prod เขียนไฟล์นี้ผ่านช่องนี้ก็ได้ | reader |
- อาการ: `coach_sync_last` = `{"ok": false, error: "…403 PERMISSION_DENIED"}` ทุกวัน
  **ทั้งที่ผมนำเข้า 1,688 แถวจากเครื่องสำเร็จ** → หลงคิดว่าใช้งานได้แล้ว
- **กฎ: แตะไฟล์ Google ไฟล์ใหม่ = เช็คสิทธิ์ทั้ง 2 บัญชีก่อนเสมอ** (Drive API
  `/files/<id>/permissions`) · ยืนยันตัวที่ prod ใช้จริงด้วย
  `grep '^GOOGLE_SERVICE_ACCOUNT_EMAIL=' /opt/oxlet/.env`
- **ท่าซิงก์ให้ทันทีโดยไม่ต้องรอแก้สิทธิ์** (ใช้ตอน prod 403): ดึงแชทจาก prod เป็น JSON
  (`psql -At` ผ่าน ssh) → ใส่ SQLite ในเครื่อง → รัน `coach_log --sync` **ตัวจริง**
  → ใช้โค้ดเส้นเดียวกันเป๊ะ + กันซ้ำด้วย `รหัสอ้างอิง` ในชีต **รันกี่รอบก็ไม่เบิ้ล**
  · ⚠️ `sent_at` ที่ `json_agg` คืนมาเป็น **UTC พร้อม offset** (`…T10:50:59+00:00`)
    → `parse_datetime` แล้ว `localtime` ได้ 17:50 โซนไทย **ถูกแล้ว ไม่ใช่บวกเกิน**
    (ยืนยันด้วย `sent_at AT TIME ZONE 'Asia/Bangkok'` ฝั่ง Postgres ก่อนเขียน)

**เทสต์**: `python scripts/test_coaching.py` (55 ข้อ — ดึงรหัสเคส **รวมรูปแบบรายงานประจำวันของจริง** ·
กันสูตร · วันที่ 4 แบบ · แยกบทบาท · แตกแถวเก่า · **ยืนยันว่าไม่เคย clear/PUT** · รันซ้ำไม่เบิ้ล ·
dry-run · สวิตช์ปิด) · **ปลอมที่ `requests` + การขอ token (ขอบระบบ) ไม่ปลอมฟังก์ชันของเราเอง**

**★★ 29 ก.ย.69 — เปิดห้องโค้ชให้คนนอกดึง raw data (เจ้าของถาม "ผ่าน api หรือ db")**
*"แค่แชทกลุ่ม sale coaching แค่กลุ่มนี้ก่อน ยังไม่เปิดสิทธิ์เยอะ … userid พนักงานกับ groupid
กลุ่มที่มี 3 สิทธิ์พอ"* · งานปลายทาง = **สอน AI/chatbot + วัดการตอบของซีเนียร์–จูเนียร์**

**★★ คำตอบ: ไม่ต้องแตะฐานข้อมูล และ *ไม่ต้องแจกคีย์ API* — รวมเป็นชีตไฟล์เดียว 3 แท็บ**

เจ้าของทักต่อ (29 ก.ย.): *"External API key เนี่ยมาจากไหนอ่ะ คนที่ดึงข้อมูลเป็นคนธรรมดา
ไม่น่าเข้าใจ เขาน่าจะใช้ claude ไม่ก็ chatgpt ในการดึง"* — **ถูกต้อง และคีย์เป็นทางที่ผิด**:
แชท AI ทั่วไปยิง API ของเราไม่ถึง · **ถ้าเขาเอาคีย์ไปวางในแชท AI = คีย์หลุดออกนอกบริษัท**
(เราสร้างความเสี่ยงเอง) · คนทั่วไปไม่เขียน `curl`
→ ให้เป็น **ชีตที่กด Download CSV แล้วอัปเข้า Claude/ChatGPT ได้เลย** (AI อ่าน CSV ดีกว่า JSON)

| สิทธิ์ที่ขอ | ให้ทางไหน |
|---|---|
| แชทห้องโค้ช | แท็บ **`บันทึกโค้ช`** 1,695 แถว (มีอยู่แล้ว) |
| userid พนักงาน | แท็บ **`พนักงาน`** 51 คน ← ทำใหม่ |
| groupid | แท็บ **`กลุ่มไลน์`** 21 กลุ่ม ← ทำใหม่ |

**★ `EXTERNAL_API_KEY` ไม่ได้มาจากใคร — เราสุ่มตั้งเองใน `.env`** ([settings.py](oxlet/settings.py) `EXTERNAL_API_KEYS`
อ่านมาคั่น comma → เทียบด้วย `hmac.compare_digest`) · ตั้งอยู่แล้วบน prod (ยิงทดสอบได้ 401 = คีย์ทำงาน · 503 = ยังไม่ตั้ง)
· **ไม่ได้แจกให้คนนอกในรอบนี้** — API v1 ยังมีไว้ให้ n8n/partner ที่เรียกแบบ server-to-server

**📄 [checkout/coach_refs.py](checkout/coach_refs.py) + `manage.py coach_refs [--apply] [--seniors] [--out]`**
- **แยกไฟล์จาก [coaching.py](checkout/coaching.py) โดยตั้งใจ**: 2 แท็บนี้เป็น **snapshot เขียนทับได้**
  (รันซ้ำ = ทับด้วยค่าล่าสุด) ส่วน `บันทึกโค้ช` เป็น **ประวัติ append-only ห้าม clear/PUT**
  → ถ้าอยู่ไฟล์เดียวกัน วันหนึ่งจะมีคนหยิบตัวเขียนทับไปใช้กับแท็บประวัติ
- **★★ `_SAFE_TABS` = ด่านกันลบประวัติ** — ไฟล์นี้เป็น**ที่เดียวในโปรเจกต์ที่ยิง `:clear`**
  ชื่อแท็บผิดครั้งเดียว = ประวัติ 1,695 แถวหายและกู้ไม่ได้ → ปฏิเสธ **ก่อน**ยิงเน็ต
  (เทสต์พิสูจน์ว่าไม่มีคำขอออกเลยตอนปฏิเสธ · รวมเคส `'พนักงาน '` มีช่องว่างต่อท้าย)
- **แท็บ `พนักงาน` เพิ่มคอลัมน์ `บทบาทในห้องโค้ช`** (ซีเนียร์ 4 คนจาก `DEFAULT_SENIORS`)
  → **แก้ปัญหา "คอลัมน์ทีมว่าง 70%" ให้ด้วย** เพราะคนนอก join `ผู้พูด` ↔ `ชื่อเล่น` เอาทีมได้
- **`LINE userId` รวมทุกบัญชีในช่องเดียว + คอลัมน์ `จำนวนบัญชี LINE` กำกับ** —
  คนเดียวมีไอดีคนละตัวต่อบอท → `count(distinct userId)` นับคนเกินจริง (เขียนเตือนในคู่มือแล้ว)
- **⚠️ prod รันคำสั่งนี้ไม่ได้ (403 บนไฟล์โค้ช)** — ต้องรันจากเครื่องที่ SA มี writer
  · ท่าที่ใช้จริง 29/09: ดึง employee/profile/group จาก prod เป็น JSON (`psql -At json_agg` ผ่าน ssh)
  → โหลดลง SQLite ในเครื่อง → รัน `coach_refs --apply` **ตัวจริง** → **ลบข้อมูลออกจากเครื่องทันที**
  (ไม่ทิ้งชื่อพนักงาน+userid ไว้ในเครื่อง dev)
- **ผลจริง 29/09**: พนักงาน 51 · กลุ่ม 21 · ซีเนียร์ติดป้ายครบ 4 คน · ยังไม่ผูก LINE 1 คน (tuinui)
  · ตรวจแล้ว **`บันทึกโค้ช` ยัง 1,695 แถวครบ ไม่ถูกแตะ · ไม่มี `#ERROR!`**

**⚠️★ บทเรียนซ้ำรอยเดิม (เจอในรอบนี้เอง)**: เทสต์รอบแรก **ปลอม `CR._api` ทั้งฟังก์ชัน**
→ ผ่าน 27/27 ทั้งที่โค้ดจริงพัง (`_api()` คืน `(base_url, headers)` ไม่ใช่ session
และชื่อแท็บไทย**ต้อง `urllib.parse.quote`** ไม่งั้น Google ตอบ 404)
· แก้เป็นปลอมที่ **`requests.post/put` + `_get_credentials`** (ขอบระบบ) → `_api()` ตัวจริงได้รัน
· **กฎเดิมย้ำรอบที่ 3: ปลอมฟังก์ชันของเราเอง = ไม่ได้ทดสอบฟังก์ชันนั้นเลย**

**เทสต์**: `python scripts/test_coach_refs.py` (27 ข้อ — ด่านกันลบประวัติ 5 เคส ·
ไอดีลูกค้าต้องไม่หลุดเข้าตารางพนักงาน · เรียงไอดีคงที่รันซ้ำได้ผลเดิม · `apply=False` ต้องไม่ยิงเน็ต)

- **★ ชีตชนะ DB 89 เท่า** (วัดจริง 29/09): ชีต **1,695 แถว** (1 เม.ย.–28 ก.ย.) ·
  `checkout_groupchat` ห้องโค้ช **19 ข้อความ** (28–29 ก.ย.) เพราะแชทดิบลบเมื่อครบ 90 วัน
  · และชีตมีคอลัมน์ **บทบาท/ทีม/รหัสเคส** ที่ตรงกับงาน "วัดซีเนียร์–จูเนียร์" อยู่แล้ว DB ไม่มี
- **ไม่ต้องเปิด SSH/สร้าง role/แตะ `ro_all`** → ไม่เสี่ยงให้เห็นแชทลูกค้า 75,744 ข้อความ
  (LINE 19,224 + FB 56,520) ที่อยู่ในฐานข้อมูลเดียวกัน · ถอนสิทธิ์ = เอาออกจากชีต คลิกเดียว
- **⚠️ `v_group_chat` GRANT ให้แค่ `claude`** (วัดจริง 29/09) — `ro_all` ยังเข้าไม่ได้ ·
  **ฝั่ง Facebook 56,520 ข้อความยังไม่มี view เลย** → วันหน้าถ้าจะเปิดแชทให้คนนอกจริง
  ต้องทำ view FB ก่อน ไม่งั้นต้องแจกตารางดิบซึ่งมี `sender_id`
- **⚠️ userid พนักงานใช้ "วัดคน" ไม่ได้** — คนเดียวมีไอดีคนละตัวต่อบอท (บอทเก่า/ใหม่ คนละ provider)
  → `count(distinct sender_id)` นับเป็น 2 คน · ชีตจึงใช้ **ชื่อเล่น** ซึ่งแม่นกว่า
  · เจ้าของอนุญาตให้ปล่อย userid ทาง API แล้ว แต่**งานนี้ไม่ต้องใช้**

**📄 [deploy/coaching_external.md](deploy/coaching_external.md) — คู่มือส่งคนนอก** (เขียนให้เขาอ่าน ไม่ใช่ dev)
อธิบาย 12 คอลัมน์ + วิธีเรียก API + **7 กับดัก** + สิ่งที่ชุดนี้ตอบไม่ได้ + ข้อตกลง PDPA

**⚠️★ 3 ข้อจำกัดของข้อมูลที่วัดได้ตอนเปิด (ต้องบอกก่อนส่งมอบ ไม่ใช่ให้เขาไปเจอเอง)**
1. **ข้อมูลกระจุก เม.ย.+พ.ค. = 91%** (943 + 606) · มิ.ย. 32 · ก.ค. 107 · **ส.ค. 0 ไม่มีเลย** · ก.ย. 7
   → **ดูเทรนด์รายเดือน/เทียบข้ามเดือนทำไม่ได้** (chatbot ถูกปิด ห้องเงียบ + บอทเราเพิ่งเก็บ 28 ก.ย.)
2. **"ซีเนียร์" คือเฟิร์สคนเดียว 154/197 = 78%** (อุ้ม 23 · โอ๊ต 13 · นวล 7)
   → "วัดคุณภาพซีเนียร์" = วัดเฟิร์ส · อีก 3 คนน้อยเกินสรุป
3. **ช่อง `ทีม` ว่าง 1,183 แถว = 70%** (ชื่อ LINE 7 คนยังจับคู่ทะเบียนไม่ได้) → แบ่งผลตามทีมไม่ได้
   · **มากกว่าที่บันทึกไว้เดิม (561)** — ตัวเลขเดิมนับแค่แถวที่มาจาก 7 ชื่อนั้น ไม่ใช่แถวที่ทีมว่างทั้งหมด
- **★ `บอท AI (ระบบเดิม)` 39 แถว ต้องกรองออกก่อนสอนโมเดล** — เป็นคำตอบของ chatbot ตัวเก่า
  เอาไปฝึกเท่ากับให้โมเดลเรียนจากเอาต์พุตตัวเอง (เขียนเตือนไว้ในคู่มือแล้ว)

### 🗃️ `CoachLog` — ที่รวมถาวรของบันทึกโค้ช (30 ก.ย.69 · migration checkout **0024**)
เจ้าของเปิดหน้า "ฐานข้อมูล (SQL)" เห็นห้องโค้ชมี **20 ข้อความ** จึงถาม
*"ค่าเก่าที่เคยส่งให้ไปไหน เอาไปเรียงใหม่หน่อยและเอามารวมกัน"* → เคาะว่า **รวมใน DB**

- **★★ ทำไมต้องเป็นตารางใหม่ ยัดกลับเข้า `GroupChat` ไม่ได้**: ตารางนั้นลบข้อมูลเกิน
  **90 วัน** อัตโนมัติ (`CHAT_KEEP_DAYS`) → ของ เม.ย.–ก.ค.69 ถูกลบไปแล้ว **และถ้านำเข้ากลับไป
  รอบ cleanup ถัดไปจะลบซ้ำทันที** · `checkout_coachlog` **ไม่มีวันหมดอายุ** เพราะเป็น
  บันทึกการสอนงาน ไม่ใช่แชทดิบที่หมุนเวียน
- **[checkout/coach_db.py](checkout/coach_db.py)** — `sync_chat()` (จากแชทบอท) · `import_sheet()`
  (จากแท็บ `บันทึกโค้ช`) · `save_rows()` · `stats()`
  · **แปลงจาก `coaching._row()` ตัวเดิม ไม่เขียนตรรกะซ้ำ** (บทบาท/รหัสเคส/ทีม/กัน LINE id หลุด
  ใช้ของ coaching.py ทั้งหมด — แยกสูตรเมื่อไหร่ ตัวเลข DB กับชีตจะไม่ตรงแล้วไม่มีใครรู้ว่าอันไหนถูก)
  · **กันซ้ำด้วย `ref`** (`line:<message_id>` / `old:<แถว>:<ช่อง>`) = **คีย์ชุดเดียวกับในชีต**
  → นำเข้าซ้ำกี่รอบก็ไม่เบิ้ล และข้อมูล 2 ที่อ้างถึงกันได้
  · **แถวไม่มี `ref` = ข้าม** (ไม่มีอะไรกันซ้ำได้ → รันซ้ำจะเบิ้ล)
  · `sent_at` แปลงจาก `วันที่ + เวลา` เป็นโซนไทย (**วัดจริง: 1,695 แถวแปลงได้ 100%**)
  แปลงไม่ได้ = `NULL` **แต่ยังเก็บแถวไว้** (`date_text` ค่าดิบ) ห้ามทิ้งข้อมูล
- **`manage.py coach_db [--sync] [--import-sheet] [--days] [--seniors] [--out]`**
  · ไม่ใส่อะไร = โชว์ว่ามีอะไรอยู่ · **`--import-sheet` แค่ *อ่าน* ชีต → prod รันได้**
  (ไฟล์โค้ชตั้ง "ใครมีลิงก์ = reader" · ที่ 403 คือตอน *เขียน*)
- **★★ `maybe_sync()` เก็บเข้าฐานข้อมูลก่อน แล้วค่อยชีต** — แก้ปัญหาที่ค้างมา 2 วัน:
  prod เขียนชีตไม่ได้ (403) → เดิม cron ล้มทั้งงาน **ข้อมูลใหม่ไม่ถูกเก็บที่ไหนเลย
  แล้วโดนลบทิ้งเมื่อครบ 90 วัน** · ตอนนี้ DB สำเร็จแน่นอน (ไม่ต้องใช้สิทธิ์ Google)
  ชีตล้มแยก try ไม่ลากกัน · KV `coach_sync_last` เก็บผลแยก `{db:{...}, sheet:{...}}`
- **เติมคำอธิบายใน `db_inventory.TABLES` แล้ว** (กฎเดิม: เพิ่มโมเดลใหม่ต้องเติมทุกครั้ง)
- **เทสต์**: `python scripts/test_coach_db.py` (24 ข้อ — กันซ้ำทั้งข้ามรอบและในชุดเดียวกัน ·
  ถอด `'` ที่ `_esc` ใส่กันชีตตีเป็นสูตร · วันที่แปลงไม่ได้ต้องไม่ทิ้งแถว ·
  **ห้ามมี LINE user id หลุดเข้าตาราง** · หัวตารางชีตไม่ตรง = ปฏิเสธ ไม่เขียนมั่ว)

**⚠️ ต้องทำตอน deploy**: `migrate` (checkout **0024**) แล้วรัน
`manage.py coach_db --import-sheet --sync` ครั้งเดียวเพื่อรวมของเก่า 1,695 + ของใหม่

**ยังไม่ได้ทำ**: หน้าเว็บดูบันทึกโค้ช (ตอนนี้ดูในชีต/หน้า SQL) · ดึงไฟล์รูปจากห้อง
(LINE ส่งมาแค่ `message.id`) · เอาบทสนทนาไปสอน chatbot (ข้อมูลพร้อมแล้ว) ·
จับคู่รหัสเคสกับชีตลีด/ยอดขายเพื่อดูว่าคำแนะนำซีเนียร์ทำให้เคสจบจริงไหม

### 🗂️ ทะเบียนกลุ่ม LINE เป็นตารางจริง — `checkout.LineGroup` · 28 ก.ย.69 (migration **0023**)
*"จริงๆ ควรแยกชัดกลุ่มแต่ละกลุ่มนะ"* (เจ้าของแจ้งหลังเห็นว่าแชทห้องโค้ชกับทุกกลุ่มอยู่ตารางเดียวกัน)

**ปัญหาเดิม**: ทะเบียนกลุ่มเป็น **JSON ก้อนเดียวใน `dash_kv['line_groups']`** → เขียน SQL หากลุ่มไม่ได้
· ไม่มีที่ติดป้ายว่ากลุ่มไหนทำงานอะไร · `checkout_groupchat` มีแค่ `group_id` ดิบ
**16 กลุ่มกองรวมกันแยกไม่ออก** (วัดจริง 28/09: 17,034 ข้อความ · ชื่อกลุ่มครบทุกแถว)

- **★ ไม่แยกตารางแชทต่อกลุ่ม** — กลุ่มใหม่ = เพิ่ม **แถว** ไม่ใช่เพิ่มตาราง/migration ใหม่
  · แยกด้วย **`kind`** (ประเภทงาน 12 แบบ: `coaching`/`lead`/`tradein`/`booking`/`purchase`/
  `finance`/`transfer`/`checkin`/`admin`/`content`/`hr`/`other`) แล้ว join เข้าแชทที่ `group_id`
- **★ ไม่แตะ `checkout_groupchat` เลย (ไม่เพิ่ม FK)** — 17,034 แถว · join ที่ `group_id` ซึ่งมี index
  อยู่แล้วก็พอ → **deploy เสี่ยงน้อยกว่ามาก** ได้ประโยชน์เท่ากัน
- **★ KVStore `line_groups` ยังเขียนเหมือนเดิม** — ของเดิมหลายตัวอ่านคีย์นั้น
  (`line_push_switch` · dropdown เลือกกลุ่ม · `/api/v1/groups` · `group_visible_to_push`)
  **ตารางมาเสริม ไม่ได้มาแทน** · `_store_line_groups` เขียนทั้ง 2 ที่ (ฝั่งตาราง best-effort —
  ยังไม่ migrate/DB ล่ม = ข้ามเงียบ **ห้ามทำให้ webhook พัง**)
- **`kind_auto`** = ประเภทนี้ **ระบบเดาให้จากชื่อกลุ่ม** ยังไม่มีคนยืนยัน · คนตั้งเองเมื่อไหร่
  (`--set`) จะเป็น `False` แล้ว **ระบบจะไม่เดาทับอีกตลอดไป**
  · บทเรียนเดิมย้ำอีกรอบ: *ค่าที่ระบบเดาใส่ให้ ต้องติดป้ายว่าเดาให้* ไม่งั้นมันกลายเป็นของจริง
    ในสายตาคนใช้แล้วไม่มีใครไปแก้ (เคยเกิดกับชื่อเล่นในทะเบียนพนักงาน)

**คำสั่ง**: `manage.py line_groups_sync [--apply] [--set <group id|ชื่อบางส่วน>=<ประเภท>] [--kinds] [--out ไฟล์]`
· ไม่ใส่ `--apply` = ดูเฉยๆ ไม่เขียน · รวมกลุ่มจาก **2 แหล่ง**: ทะเบียน KV + กลุ่มที่เคยมีข้อความจริง
(กลุ่มที่บอทได้ยินแต่ยังไม่เข้าทะเบียน จะไม่ตกหล่น)

**view สำหรับคนที่เขียน SQL**: [deploy/line_group_views.sql](deploy/line_group_views.sql)
· **`v_line_group`** = สารบัญกลุ่ม (ไม่มีชื่อคน ไม่มีเนื้อแชท → เปิดให้ `ro_safe` ได้ถ้าต้องการ)
· **`v_group_chat`** = แชทพร้อมชื่อ+ประเภทกลุ่ม · **ไม่มี `sender_id` → ปลอดภัยกว่าตารางดิบ**
· ⚠️ `v_group_chat` มีเนื้อแชท → **GRANT ให้ `ro_all` เท่านั้น ห้ามให้ `ro_safe`**

**เทสต์**: `python scripts/test_line_groups.py` (20 ข้อ) — **ทดสอบกับชื่อกลุ่มจริงบน prod ทั้ง 13 กลุ่ม**
ไม่ใช่ชื่อสมมติ · เคสที่ชื่อใกล้กันต้องไม่สับ (`รับสมัครพนักงาน` ≠ `รับ-ส่งระหว่างสาขา` ·
`จัดซื้อ` ≠ `จัดไฟแนนซ์`) · รันซ้ำไม่สร้างซ้ำ · **ค่าที่คนตั้งเองต้องไม่ถูกเดาทับ** · ประเภทมั่ว/คำสั่งผิดรูปต้องไม่ล้ม

**⚠️ ต้องทำตอน deploy**: `migrate` (checkout **0023**) **และ**
`sudo -u postgres psql -d oxlet -f deploy/line_group_views.sql` (สร้าง view · รันหลัง migrate เท่านั้น)
แล้วค่อย `manage.py line_groups_sync --apply` ครั้งแรกเพื่อย้ายของเดิมเข้าตาราง

**⚠️★ 29 ก.ย.69 — `permission denied for view v_group_chat` ในหน้า "ฐานข้อมูล (SQL)"**
- เจ้าของลองรัน `SELECT * FROM v_group_chat …` ในหน้าเว็บแล้วโดนปฏิเสธ **ทั้งที่ view มีอยู่จริง**
- **ต้นเหตุ**: view เจ้าของเป็น `postgres` แต่ **เว็บรันด้วย user `oxlet`** ซึ่งไม่เคยถูก GRANT ·
  วัดจริง: `v_group_chat`/`v_line_group` มี GRANT ให้ **`claude` ตัวเดียว** ·
  บรรทัด `GRANT … TO ro_all` ในไฟล์ SQL **ก็ยังไม่ถูกรัน** (role `ro_all` มีอยู่แล้ว แต่ไม่มีสิทธิ์)
  → แปลว่าตอน deploy มีการสร้าง view แยกมือ ไม่ได้รันไฟล์ทั้งไฟล์
- **แก้ถาวร** (เติม `TO oxlet` ในไฟล์แล้ว · รันซ้ำได้): `sudo -u postgres psql -d oxlet -f deploy/line_group_views.sql`
- **ระหว่างยังไม่ได้รัน ใช้ตารางดิบ join เองได้** — `oxlet` เข้าถึง `checkout_groupchat` +
  `checkout_linegroup` ได้อยู่แล้ว (view เป็นแค่ความสะดวก ไม่ใช่ชั้นความปลอดภัยของหน้าเว็บ —
  หน้านั้นปิด LINE id พนักงานด้วย `db_export._scrub` อยู่แล้วไม่ว่าจะ query จากอะไร)
- **กฎ: สร้าง view ใหม่ = ต้อง GRANT ให้ `oxlet` ด้วยเสมอ** ไม่ใช่แค่ role ผู้อ่านภายนอก
  ไม่งั้นของที่ทำเพื่อ "ให้ดูง่ายขึ้น" กลับใช้ในหน้าเว็บของเราเองไม่ได้
- **⚠️★ ตรวจสิทธิ์ต้องดู `pg_class.relacl` ไม่ใช่ `information_schema.role_table_grants`**
  ตารางนั้น**โชว์เฉพาะสิทธิ์ที่บัญชีผู้ถามเกี่ยวข้อง** (เป็น grantor/grantee/สมาชิก) →
  ถามด้วยบัญชี `claude` แล้วเห็นแค่ `claude=r` **ทั้งที่ `ro_all` มีสิทธิ์อยู่** ·
  ผมสรุปผิดเพราะตรงนี้มาแล้ว 1 รอบ · คำสั่งที่เห็นครบ:
  `select relname, array_to_string(relacl,' , ') from pg_class where relname='v_group_chat'`
  (`oxlet=arwdDxt` = เจ้าของตาราง · `claude=r` = อ่านอย่างเดียว · ไม่มีชื่อ = เข้าไม่ได้)

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
- **★★★ 27 ก.ย.69 — "ตามด่วนหยุดส่งทั้งทีม 3 วัน" · ต้นเหตุคือ **ส่งไปไอดีผิดฝั่งบอท**
  (เจ้าของแจ้ง *"ตัวที่รายงานลงกลุ่มที่ควรรายงานหายไปไหนหมด … เช่นห้องจอง"*)**
  - **วัดจาก `dash_event_log` (ตัวเลขจริง)**: 17–24 ก.ย. ตามด่วนสำเร็จ **46 ครั้ง/วัน ไม่เคยล้ม**
    → **25–27 ก.ย. ล้ม 46 ครั้ง/วัน สำเร็จ 0** · ส่งเข้ากลุ่ม (เช็คชื่อ 09:30/10:00) **ยังสำเร็จทุกวัน**
    = token ตัวส่งไม่ได้พัง · พังเฉพาะขา **แชท 1:1**
  - **★★ ต้นเหตุ ไม่ใช่ "ยังไม่ได้แอดบอทใหม่" อย่างที่ผมสรุปไว้เมื่อ 24 ก.ย.** — ไล่ไอดีที่ล้มทั้ง 23 ตัว
    เทียบกับ `checkout_lineprofile` แล้วพบว่า **ไม่มีสักตัวที่เป็นฝั่ง `push`** (เป็น `channel=''`
    = ไอดีที่นำเข้าจากชีต = **ของบอทเดิม**) แต่ **15 จาก 16 คนมีไอดีฝั่ง `push` อยู่ในทะเบียนแล้ว**
    → ตอนย้ายขาส่ง 1:1 ไปบอทตัวส่ง **ลืมย้ายฝั่งของ "ไอดีผู้รับ"** · LINE ไม่รู้จักผู้รับ = 400 ทุกคน
    · ต่างจากที่บันทึกไว้ว่า "จะไม่ถึงแค่ 2 คน" — **จริงคือไม่ถึงเลยทั้ง 18 คน**
  - **แก้ที่จุดเดียว — `line_notify._dm_target()`** (เรียกใน `push_line_message` ก่อนยิง):
    ปลายทางเป็น `U…` → หาไอดีของคนนั้น **ฝั่งเดียวกับ token ที่กำลังใช้** ด้วย
    **`people.id_for_channel()`** + **`line_channels.key_of_token()`** (เทียบสตริง ไม่ยิงเน็ต)
    → **ครอบทุกงานที่ส่ง 1:1 ทีเดียว** (ตามด่วน · เช็คชื่อโหมด test · รายงานรายวัน · ตามงานจัดซื้อ)
    · **ไม่ใช่การกลับไปใช้บัญชีเก่า** — ยังออกจากบอทตัวส่งบัญชีเดียวตามที่เจ้าของกำหนด
    · **แปลงให้เฉพาะพนักงาน** (แถวที่ผูก `Employee`) — **ลูกค้าไม่แตะเลย** เพราะการตอบแชท
      เลือกบัญชีตามที่ลูกค้าคุยอยู่แล้ว (`chat._channel_for`) ถ้าแปลงด้วยจะส่งข้ามบัญชีที่เขาไม่ได้แอด
    · แปลงไม่ได้ = **ส่งด้วยไอดีเดิม** (ไม่กลืนงาน) · แปลงแล้วจดฟิลด์ `remap` ไว้ในล็อก
    · **วัดผล: 16 จาก 18 คนกลับมาได้รับทันที** · เหลือ 2 คนที่ยังไม่มีไอดีฝั่งบอทใหม่เลย
    · **⚠️ ไอดีถูกฝั่งแล้วยังไม่พอ** — LINE ยังต้องการให้คนนั้น **แอดบอทตัวส่งเป็นเพื่อน** ถึงจะส่ง 1:1 ได้
      (ไอดีฝั่ง `push` ที่ได้จาก event ในกลุ่ม ไม่ได้แปลว่าเขาแอดบอทแล้ว) → ที่เหลือดูจากล็อก
  - **★ ส่วน "ห้องจอง" เป็นคนละเรื่อง แก้ด้วยโค้ดไม่ได้** — การ์ด **`rpt-card` (รายงาน จอง/อนุมัติ/ปล่อย)**
    ยิง 10:30 ทุกวันเข้ากลุ่ม **"จองรถ" `C40b836d…` ซึ่ง `channels: ["crm"]` = มีแต่บอทตัวรับ**
    · อีก 3 ใบ (mega/scorecard/alloc) ยิงเข้า **"ทดลองงาาน" `C3ee0d44…`** ที่ **ไม่มีบอทไหนอยู่เลย**
      (`lastSeen` ค้างที่ 24 ก.ค.) · 2 ใบที่ยิงเข้า **ทีมAdmin `C9412426…` สำเร็จทุกวัน**
    · **ขั้นตอนแก้ (ต้องทำที่ LINE ไม่ใช่ที่โค้ด)**: เชิญบอท **`@693tyhah`** เข้ากลุ่ม →
      **พิมพ์อะไรก็ได้ในกลุ่ม 1 ครั้ง** (บอทต้องได้ยินก่อนจะรู้ id ฝั่งตัวเอง) →
      รัน **`manage.py line_push_switch --apply`** เพราะ **group id ออกต่อ provider**
      (ปลายทางที่บันทึกไว้เป็น id ฝั่งบอทเดิม เชิญบอทเข้าเฉยๆ ยังส่งไม่ออก)
  - **★★ หน้าสถานะระบบเฝ้า "งานส่งออกทุกตัว" แล้ว ไม่ใช่เฉพาะการ์ด** (`admin_system_health`) —
    อ่าน `dash_event_log` 24 ชม.ล่าสุด จัดกลุ่มตามชื่องาน: **ล้มหมดไม่มีสำเร็จเลย = `err`** ·
    **สำเร็จบ้างไม่ถึงบ้าง = `warn`** · สำเร็จล้วน = เงียบ
    · บล็อกเดิม (26 ก.ย.) ดูแต่ KV ของการ์ด → **ตามด่วน/เช็คชื่อ/ตามงานจัดซื้อ ไม่มีใครเฝ้า**
    · วิธีนี้ **งานส่งออกที่จะเพิ่มในอนาคตได้การเฝ้าฟรี** ไม่ต้องมาไล่เพิ่มเช็คทีละตัว
    · **กฎซ้ำรอบที่ 4**: *"หยุดส่งเงียบๆ" คือโหมดพังที่แพงที่สุดของระบบนี้* —
      ครั้งนี้เสียหาย 3 วันเต็ม และรู้เพราะ**เจ้าของทักมา** ไม่ใช่เพราะระบบร้อง
  - **เทสต์**: `python scripts/test_dm_channel.py` (18 ข้อ — แปลงไอดีถูกฝั่ง · ลูกค้าไม่ถูกแตะ ·
    กลุ่มไม่ถูกแตะ · แปลงไม่ได้ต้องไม่กลืนงาน · **ปลอมที่ `requests.post` แล้วเช็คว่า `to` ที่ยิงออกถูกตัว**)
    · `python scripts/test_health_send.py` (เรียก view จริงผ่าน test client — พิสูจน์ว่าบล็อกเช็ค
    **ได้รันจริง ไม่ได้โดน `except` กลืน** ตามบทเรียนเดิม)
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
  - **⚠️★ 28 ก.ย.69 — บรรทัดสรุปท้ายคำสั่งบอกข้อมูลผิดมา 8 วัน**: เขียนตายตัวว่า *"แชท 1:1
    (ตามด่วนรายเซลล์) ไม่ได้ย้าย — ยังส่งจากบัญชีเดิมจนกว่าจะตั้ง `LINE_DM_CHANNEL=push`"*
    ซึ่ง **ตกยุคตั้งแต่ 20 ก.ย.** (`dm_token()` ค่าเริ่มต้นเป็นบัญชีตัวส่งไปแล้ว · 24 ก.ย. `followup_token()`
    ตามไปด้วย) → เจ้าของอ่านแล้วจะสรุปว่าตามด่วนยังออกจากบัญชีเก่า ทั้งที่ย้ายแล้วและส่งสำเร็จ 42 ครั้ง/วัน
    · แก้เป็น **อ่านสถานะจริงจาก `ch.dm_token()` แล้วค่อยพิมพ์** + บอกคำสั่ง SQL ไล่ว่าใครยังไม่ได้แอดบอท
    · **กฎ: ข้อความสรุปที่เขียนค่าตายตัว = จะผิดวันที่นโยบายเปลี่ยน — ให้อ่านจากตัวระบบจริงเสมอ**
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

### 🎞️ "คนดูหลุดตรงไหน" — กราฟคนดูค้างของวิดีโอ Facebook + ภาพทีละวินาที · 15 ต.ค.69 (เจ้าของสั่ง)
เจ้าของส่งแบบหน้าจอมา (Hook/Hold/หายครึ่ง/ดูจบ · กราฟ · ภาพทีละวินาทีใต้กราฟ เน้นจุดสำคัญ) · **โทนม่วงขาว**
- **ข้อมูล**: `post_video_retention_graph` (+ `_autoplayed` · `_clicked_to_play`) = **41 จุด ทุก 2.5% ของความยาวคลิป**
  ค่า 0–1 · ไม่ได้ให้เป็นวินาที → ความยาวคลิปจาก `/<เพจ>/videos?fields=length` (**`?ids=` ใช้ไม่ได้แล้วตั้งแต่ Graph v26**)
  · โพสต์ที่ไม่ใช่วิดีโอ Meta คืน `{}` ไม่ error · ทดสอบกับเพจจริงแล้ว 33/33 วิดีโอมีกราฟ
- **`meta_sync.sync_retention()`** — **คำขอแยกจากยอดโพสต์** (ถ้า Meta ถอด metric นี้ ยอดโพสต์ต้องไม่ล้มตาม) ·
  เรียกใน `run()` หลังยอดเพจ (try แยก) + รอบรายชั่วโมง → **`dash_meta_video_retention`** (`MetaVideoRetention` · migration **0017**/**0018**)
  **1 แถว/โพสต์ ค่าล่าสุด** (ไม่เก็บรายวัน — กราฟแทบไม่ขยับ) · ผล `res["retention"]` ใน `meta_sync_last`
- **ตัวเลข คิดฝั่งเซิร์ฟเวอร์ที่เดียว** `social_stats._kpi()`: **Hook** = เหลือกี่ % ที่วิที่ 3 · **Hold** = ของคนที่ดูถึง 3 วิ
  ยังดูถึงวิที่ 15 (คลิปสั้นกว่า = ถึงจบ) · **หายครึ่ง** = วินาทีแรกที่คนที่ดูถึง 3 วิ เหลือไม่ถึงครึ่ง · **หลุดหนักสุด** =
  วินาทีที่ลดจากวินาทีก่อนมากสุด · **ดูจบ** · `_ret_at()` ประมาณค่าระหว่างจุด (จุด i = วินาที i/40 × ความยาว)
  · `_page_avg()` ค่าเฉลี่ย Hook/ดูจบ ของเพจ 60 วัน ไว้เทียบ
- **★ ข้อมูลดิบ + ผลวิเคราะห์ลงฐานข้อมูล (15 ต.ค.69 · เจ้าของสั่ง "อย่าลืมเก็บ raw data ลงฐานข้อมูล")**
  · คำตอบดิบของ Facebook ทุกก้อนที่ `sync_retention` ดึง → **`dash_meta_raw`** (kind = `retention` / `videos` · ตัด paging ที่มี token)
  · ผลวิเคราะห์เป็นคอลัมน์ใน `dash_meta_video_retention` (dashboard migration **0018**): `hook_pct` · `hold_pct` · `hold_to` ·
    `half_sec` · `drop_sec` · `drop_pct` · `end_pct` · `persec` (% ทีละวินาที) · `analyzed_at` · `first_seen`
    — คิดด้วย **`social_stats.analysis_fields()` ซึ่งเรียก `_kpi` ตัวเดียวกับหน้าเว็บ** (ห้ามเขียนสูตรใหม่) · คิดใหม่ทุกครั้งที่กราฟอัปเดต
    · แถวที่ยังไม่มีผล (ก่อน migrate) = `analyze_missing()` (ไม่ยิง Facebook · รอบรายชั่วโมงเรียกให้เอง)
  · สถานะภาพทีละวินาทีเป็นคอลัมน์ด้วย: `frames_n` · `frames_at` · `frames_reason` (`new`/`ads`) · `frames_error`
  · ตัวอย่าง SQL: `SELECT post_id, hook_pct, end_pct, drop_sec FROM dash_meta_video_retention WHERE hook_pct < 60 ORDER BY created_time DESC`
- **★ คลิปใหม่ = วิเคราะห์ + แคปภาพเอง ทุกชั่วโมง (15 ต.ค.69 · *"เมื่อมีคลิปใหม่มาวิเคราะห์ auto เองเลย และสกรีนช็อตเองเลยนะ"*)**
  · `cron_tick` → **`meta_sync.maybe_watch(now)`** ทุก `WATCH_EVERY_MIN`=60 นาที (03:00–23:59 · ช่วงเที่ยงคืนรอบใหญ่ทำอยู่) ·
    ไม่ทำถ้ารอบใหญ่/กด sync เองกำลังทำ (`_locked`) หรือโควต้าเกิน `USAGE_BLOCK_PCT` · จองรอบใน KV ก่อนเริ่ม · ทำใน thread
  · **`watch_videos()`** = `sync_retention(days=WATCH_DAYS=7)` (เพจละ ~2 คำขอ · วัดจริง 18 วิ · โควต้า 1%) → `analyze_missing()` →
    `video_frames.prefetch_guarded()` (ทำภาพทีละคลิป · กันรันซ้อนกับรอบเที่ยงคืน) · ผล KV **`video_watch_last`**
    (`videos` · `new` = คลิปที่เพิ่งเจอครั้งแรก · `frames` · `errors`) · พังจด `dash_event_log` kind=meta_sync name=video_watch
  · หน้าสถานะระบบเตือน: รอบนี้มี error · หรือไม่ได้ทำงานเกิน 3 ชม.
- **★★ 15 ต.ค.69 ค่ำ — เลิกโหลดวิดีโอ: ใช้รูปหน้าปก + ลิงก์แทน** (เจ้าของสั่ง *"ไม่ต้องดาวน์โหลดวิดีโอ เราแค่แปะลิงก์ก็พอ
  แล้วก็เอารูปหน้าปกของวิดีโอมาก็พอจะได้ประหยัดพื้นที่"*)
  · **`video_frames.ENABLED = False`** → ไม่มีอะไรโหลดไฟล์วิดีโอเลย (ensure/for_detail/prefetch/start_prefetch คืนทันที ·
    รอบรายชั่วโมงยังดึงกราฟ+วิเคราะห์ แค่ไม่ทำภาพ · `frames.state = "off"`) · ภาพที่ทำไปแล้วลบด้วย
    **`manage.py meta_frames --purge`** · โค้ดตัดภาพเก็บไว้ (เปิดกลับ = ตั้ง ENABLED = True)
  · หน้าคลิป: ซ้าย = **รูปหน้าปก (กดแล้วไปดูคลิปใน Facebook) + ลิงก์ "ดูคลิปใน Facebook ↗"** · ไม่มีตัวเล่นคลิป/ลิงก์ดาวน์โหลด ·
    `video_detail` ไม่ขอลิงก์ไฟล์วิดีโอแล้ว (`_video_source` ไม่ถูกเรียก) · ส่ง `cover` = รูปปกที่เก็บไว้ (`covers`)
  · **คลิปเก่าที่รอบปกติไม่ครอบ (เก่ากว่า 90 วัน) ดึงกราฟตอนเปิดดู** — เจ้าของเปิดคลิป 10/7 แล้ว "กราฟไม่ขึ้น" ·
    `meta_sync.fetch_retention_one(post_id)` = คลิปเดียว: กราฟ + ความยาว + `full_picture` (รูปปก) · ข้อมูลดิบลง `dash_meta_raw` ·
    เรียกจาก `video_detail` เมื่อยังไม่มีกราฟหรือไม่มีรูปปก · **ลองครั้งเดียวต่อชั่วโมงต่อคลิป** (`_RET_TRY` · `RET_RETRY_SEC`) ·
    วัดจริง: คลิป 10/7 (24.7 วิ) ได้ Hook 97.8% · ดูจบ 47.1% · เปิดครั้งแรก ~13 วิ ครั้งต่อไปไม่ยิง Facebook
  · **รูปปกย่อก่อนเก็บ** (`covers._shrink` · ด้านยาว ≤720px · JPEG q78) — Facebook ให้รูปเต็ม 1080×1920 ~400 KB ·
    วัดจริงในเครื่อง dev: รูปปกเพจ 521 รูป **179 MB → 34 MB** · รูปเดิมย่อด้วย **`manage.py social_covers --shrink`**
- (ปิดอยู่) **ภาพทีละวินาที** [video_frames.py](dashboard/services/video_frames.py) — **2 กลุ่ม**: **ยิงแอดวิวสูงสุด `TOP_N`=25 อันดับ**
  (เจ้าของสั่ง *"Screenshot ทำแค่ตัวที่ยิง Ads มียอดวิวเยอะ 20-30 คลิปก็พอ"*) **+ คลิปใหม่ที่ลงภายใน `NEW_DAYS`=7 วัน**
  (*"สกรีนช็อตเองเลยนะ"* — ตีความว่าคลิปใหม่ทุกคลิป ไม่ต้องยิงแอด · ปิดได้ด้วย `NEW_DAYS = 0`)
  · กลุ่มยิงแอด (`_ads_rows`) = snapshot ล่าสุดของแต่ละโพสต์ (แถวที่ดึงไม่เกิน 2 วันก่อนรอบล่าสุดของเพจ) · `post_type` มี video ·
    **`video_views_paid > 0`** · เรียงวิวรวมมากสุด · กลุ่มคลิปใหม่ (`_new_rows`) = แถวกราฟที่ `created_time` ภายใน 7 วัน
    · `eligible()` จำ 10 นาที · **กราฟคนดูค้างยังมีทุกคลิปเหมือนเดิม**
  · **ทำเองไม่ต้องรอใครเปิด**: รอบรายชั่วโมง (ข้างบน) + ท้ายรอบเที่ยงคืน (`start_prefetch`) · **ทำทีละคลิป** (วัดจริง ~40 วิ/คลิป)
    · คลิปในกลุ่มที่ยังไม่มีภาพ = ทำตอนเปิดดูได้ด้วย
  · `for_detail()`: มีภาพอยู่แล้ว = โชว์ · นอกกลุ่ม = `{"state":"skip","top":25,"newDays":7}` ไม่โหลดคลิป →
    หน้าเว็บเขียน "ภาพทีละวินาทีทำให้เองเฉพาะคลิปใหม่ 7 วัน และคลิปที่ยิงแอดวิวสูงสุด 25 อันดับ · คลิปนี้ดูได้จากกราฟ"
  · **หลุดกลุ่มเกิน `PRUNE_GRACE_DAYS`=3 วัน = ลบภาพ** (`prune` · เว้นไว้ก่อนกันคลิปที่ขยับเข้า-ออกอันดับถูกตัดซ้ำ) ·
    **รายชื่อว่าง (อ่านไม่ได้) = ห้ามลบ** · ดิสก์คงที่ราว 25 + ~60 คลิปใหม่/สัปดาห์ × ~550 KB ≈ 50 MB
  · `manage.py meta_frames` (รายชื่อ + เหตุผล [คลิปใหม่]/[ยิงแอด] + มีภาพหรือยัง) · `--watch` (ทำรอบคลิปใหม่เดี๋ยวนี้) ·
    `--analyze` (คิดผลวิเคราะห์ที่ขาด) · `--fetch [--limit N]` · **บนเซิร์ฟเวอร์รันในนาม `oxlet`**
    (`sudo -u oxlet .venv/bin/python manage.py meta_frames --watch`) ไม่งั้นโฟลเดอร์ภาพเป็นของ root
  · วัดจริงในเครื่อง dev 15 ต.ค.69: เข้าเกณฑ์ 88 คลิป (ยิงแอด 25 + ใหม่ 63) · รอบแรกบน prod จะทำภาพ ~85 คลิป ≈ 1 ชม. (เบื้องหลัง)
  · ทำงาน: โหลดคลิปจาก `source` ของ Facebook ~15 MB → ffmpeg `fps=1,scale=-2:240` → `MEDIA_ROOT/frames/meta/<post id>/001.jpg…`
  (ไฟล์ 1 = วิที่ 0 · ~8 KB/ภาพ) + `info.json` · ทำค้าง/พลาดมีสถานะ · พลาดลองใหม่หลัง 30 นาที · ลบเองเกิน 90 วัน
  · ลิงก์คลิปต้องเป็นโดเมน Facebook (fbcdn) · ffmpeg ของเครื่องก่อน ไม่มีใช้ **`imageio-ffmpeg==0.6.0`** (ใน requirements)
  · เป็นภาพจากโพสต์สาธารณะของเพจเรา → เสิร์ฟผ่าน /media/ ได้ (เหมือนรูปปก)
- **API** `/api/admin/social?video=<post id>` (`video_detail`: ตัวเลขโพสต์ · กราฟ · KPI · รูปปก · `retError` ถ้าดึงกราฟไม่ได้)
  · `?frames=<post id>` = สถานะตัดภาพอย่างเดียว (หน้าเว็บถามทุก 4 วิ — ไม่ยิง Facebook) · แอดมินเท่านั้น
- **หน้าเว็บ** (แท็บ Facebook → กดโพสต์วิดีโอ): ซ้าย = รูปปก + ลิงก์ไป Facebook + ตัวเลข (ม่วงเข้ม/ม่วง) · ขวา = แท็บ **คนดูหลุดตรงไหน** | ยอดรายวัน
  · (ข้อด้านล่างเรื่องแถบภาพ/กดภาพเลื่อนคลิป ใช้เฉพาะตอนเปิด `video_frames.ENABLED`)
  · การ์ด 4 ตัว + กราฟพื้นม่วง + เส้นประ 3 วิ (เทา) / หลุดหนักสุด (แดง) / หายครึ่ง (ส้ม) + **แถบภาพวางตรงแกน x ของกราฟ**
  (อ่านตำแหน่งจาก `chartArea`/`getPixelForValue` — ไม่เดาระยะขอบ) ภาพตรงจุดสำคัญขยาย + กรอบสี + % ใต้ภาพ
  · **กดภาพ = เลื่อนตัวเล่นคลิปไปวินาทีนั้น** · ย่อพอดีจอ / ซูม (เลื่อนแนวนอน) · สรุปเป็นประโยค + กล่องจุดหลุดหนักสุด
  · ★ ภาพมาทีหลัง/กดภาพ = วาดใหม่เฉพาะส่วนขวา (`_soStripDraw`) ไม่วาดทั้งหน้า — ไม่งั้นตัวเล่นคลิปถูกรีเซ็ต
  · ตารางโพสต์ Facebook มีคอลัมน์ **ดูถึง 3 วิ** · การ์ดในหน้าเพจมี "ดูถึง 3 วิ X%" + ปุ่ม "คนดูหลุดตรงไหน"
- **ยังไม่มี** (แบบที่เจ้าของส่งมามี): จุด "key message" จากคำพูดในคลิป · แท็บแคปชัน/โทนเสียง · ใบตัดต่อ — ต้องถอดเสียงคลิป (AI)
- **Deploy**: `pip install -r requirements.txt` + `migrate` (dashboard **0017 + 0018**) + restart ·
  รอบรายชั่วโมงเริ่มเองภายในชั่วโมงแรก (ดึงกราฟคลิป 7 วัน + วิเคราะห์ทุกแถว) · คลิปเก่าดึงตอนเปิดดู ·
  ครั้งเดียวหลัง deploy: `sudo -u oxlet .venv/bin/python manage.py meta_frames --purge` (ลบภาพที่เคยทำ) +
  `sudo -u oxlet .venv/bin/python manage.py social_covers --shrink` (ย่อรูปปกเดิม) ·
  เทสต์ `python scripts/test_video_retention.py` (96 ข้อ · ปลอมที่ `requests.get` · [6] เกณฑ์ภาพ · [7] ข้อมูลดิบ/ผลวิเคราะห์/รอบคลิปใหม่/หน้าสถานะ ·
  [8] ปิดโหลดวิดีโอ/รูปปก/คลิปเก่าดึงเอง/purge/ย่อรูป)

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

### 📋 รายงานทีมคอนเทนต์ — [content_report.py](dashboard/services/content_report.py) · 30 ก.ย.69
*"คลิปลงใหม่ ผลเป็นยังไง · คลิปลงภายใน 7 วันจัดแรงค์ที่มียอดวิวเยอะ · คลิป 7 วัน+ ที่มียอดวิวน้อย ·
คลิป 7วัน+ ที่มียอดวิวเยอะที่สุด · และรายงานทั้ง 10 ช่อง และยอดลีดที่ได้จากช่องทางนี้กี่คน ·
7 วันมียอดวิว เม้น ไลก์ แชร์ บันทึก กี่คน"* — **เจ้าของเสนอโครงเอง**

- **กลุ่มปลายทาง**: `C63f6d477d60a8ed8eea99302786d1fb0` **"Branding and Content Maketing Team"**
  · `channels: ["push"]` = **บอทตัวส่งอยู่ในกลุ่มแล้ว ไม่ต้องเชิญบอท**
- การ์ด **`content-card`** ในแท็บ **คอนเทนต์** _(ย้ายจาก "โซเชียล" 2 ต.ค.69 ตอนแยกหน้าต่อแพลตฟอร์ม)_
  \+ เวอร์ชันแคป `#content-card-shot` (กว้าง 1500px · สี light คงที่)
  · ลงทะเบียนใน `_LINE_CARDS`/`_CARD_TAB` แล้ว → ได้ตั้งเวลา/เลือกกลุ่ม/ส่งทดสอบจากระบบการ์ดเดิมทั้งหมด
  · **เพิ่มแท็บเข้า `_TAB_ID`** ด้วย ไม่งั้น Playwright สลับแท็บไม่ได้แล้วหาการ์ดไม่เจอ
  (ตอนนี้ `"คอนเทนต์": "ct"` · มี **`scripts/test_tab_map.py`** กันแท็บกับ `_TAB_ID` หลุดจากกันแล้ว)
- **API แยก `/api/admin/content_report`** (ไม่รวมกับ `/api/admin/social`) — ต้องอ่าน snapshot ทั้ง 3
  แพลตฟอร์มแล้วคิดยอดรายวันรายชิ้น ~2,000 ชิ้น · ไม่ควรไปหน่วงทุกครั้งที่เปลี่ยนช่วงวันที่ในแท็บ

**★★ `#content-card` ถูกสร้างหลังข้อมูลมาแล้วเท่านั้น**
Playwright รอ element นี้ (35 วิ) ก่อนแคป · ถ้าวางกล่องเปล่าไว้ก่อนแล้วค่อยเติม
มันจะ **แคปการ์ดว่างแล้วส่งเข้ากลุ่มเลย** — ระหว่างรอโชว์ตัวหมุนที่ไม่มี id นั้น

**★★ `_crCard(shot)` ฟังก์ชันเดียวสร้างทั้งเวอร์ชันเว็บและเวอร์ชันรูป**
เขียนแยก 2 ชุดเมื่อไหร่ ตัวเลขในรูปกับบนเว็บจะไม่ตรงกันแล้วไม่มีใครรู้ว่าอันไหนถูก
(บทเรียนเดิมจาก `#rpt-shot` ที่ reuse `_rpt`/`_RC`) · เทสต์เทียบตัวเลขของ 2 เวอร์ชันว่าตรงกัน

**★ ลีดรายช่อง — `LEAD_ALIAS` เขียนมือ ห้าม fuzzy**
ชีตลีดเขียนชื่อช่องคนละแบบกับทะเบียนช่อง: ระบบ `ช่องพี่แซน` ↔ ชีต `Tiktok ช่องแซน` ·
ระบบ `ช่อง 888` ↔ ชีต `TIKTOK ช่อง888` + `LIVE Tiktok / ช่อง888` (ต้องรวมทั้ง LIVE และปกติ)
· **10 ช่องเขียนมือได้หมด และผิดแล้วเห็นทันที** ต่างจาก substring ที่ผิดเงียบ
(บทเรียนเดิม: `Mod🐜` ไปจับ `เอ็ม` เพราะ `m` เป็น substring)
· ช่องที่ยังไม่ได้จับคู่ขึ้น **"ยังไม่จับคู่" ไม่ใช่ 0** — 0 อ่านเป็น "ช่องนี้ไม่ได้ลีดเลย" ซึ่งไม่จริง
· **Facebook จับคู่รายเพจไม่ได้** — ชีตเรียก `เพจบ้านเก่า`/`เพจอ่อนนุช` ส่วนชื่อจริง 2 เพจ
ต่างกันแค่คำท้าย ("…สำนักงานใหญ่") → ฝั่ง FB ขึ้น `–` ในช่องลีด และนับรวมที่ยอดกลุ่มแทน

**★ "คลิปเก่าที่เงียบสุด" นับเฉพาะคลิปที่คิดยอดรายวันได้จริง**
คลิปที่ยังมี snapshot คืนเดียวจะได้ 0 ทุกตัวแล้วไปกองหัวตาราง = **ตอบผิดคำถาม**
(กติกาเดียวกับ `_sort_rows` ของหน้าโซเชียล) · หมายเหตุท้ายการ์ดบอกว่า
"คลิปเก่า N ชิ้น คิดยอดรายวันได้ M ชิ้น"

**⚠️ "บันทึก" (saves) ทำไม่ได้ — ไม่ได้ลืม**
TikTok Display API (`video.list`) ให้แค่ วิว/ไลก์/คอมเมนต์/แชร์ · YouTube `favoriteCount`
เลิกใช้ตั้งแต่ปี 2015 (คืน 0 เสมอ) · Facebook Graph ไม่เปิดยอดบันทึกของโพสต์เพจ
→ **ไม่ใส่คอลัมน์ที่จะเป็น 0 ทุกแถว** (คนอ่านจะนึกว่าไม่มีใครบันทึกเลย ซึ่งไม่จริง)
แต่**เขียนบอกไว้ท้ายการ์ด** ว่าดึงไม่ได้ · YouTube ไม่มียอดแชร์เช่นกัน

**เทสต์**: `python scripts/test_content_report.py` (23 ข้อ — แยกคลิปใหม่/เก่าตามวันโพสต์ ·
คลิปที่คิดรายวันไม่ได้ต้องไม่โผล่ใน "วิวน้อยสุด" · ลีดรวม LIVE+ปกติ · ช่วงที่ไม่มีข้อมูลต้องไม่พัง)
· **ตรวจ UI ด้วย Chromium จริง** — ดูรูป + วัดว่าเวอร์ชันแคปกับเวอร์ชันเว็บมีตัวเลขชุดเดียวกัน

**★★ 30 ก.ย.69 (รอบ 2) — คอลัมน์ช่องเป็น "โปรไฟล์" แทนชื่อยาว** (เจ้าของขอ
*"อยากให้มันสามารถแสดงเป็นโปรไฟล์ของช่องทางนั้นดีกว่า ไม่ต้องมาทำแบบนี้"*)
- ชื่อเพจกินเต็มช่อง ("อ๊อกเล็ตธ์ออโต้ โชว์รูมรถมือสอง สาขาชลบุรี") → เปลี่ยนเป็น
  **รูปกลม + ชื่อ + @username + ผู้ติดตาม** (`_crFace()` ใน [index.html](dashboard/templates/dashboard/index.html))
- **[avatars.py](dashboard/services/avatars.py)** เก็บรูปโปรไฟล์ที่ `MEDIA_ROOT/avatars/<side>/<id>.jpg`
  · **ใช้ตัวดาวน์โหลดร่วมกับ [covers.py](dashboard/services/covers.py)** (`covers._fetch` ที่แยกออกมา)
  → กติกาการรับรูป (ชนิดไฟล์ · เพดานขนาด · เขียน `.part` แล้ว `os.replace`) เป็นชุดเดียวกัน
- **★ ต่างจากรูปปกคลิปตรง `overwrite=True`** — โปรไฟล์เปลี่ยนได้ตลอด ส่วนรูปปกคลิปนิ่งหลังโพสต์
- แหล่งรูป: **TikTok** `avatar_url_100` (อยู่ใน scope `user.info.basic` ที่ทุกช่องให้มาแล้ว —
  เพิ่มใน `_STAT_FIELDS` ของ [tiktok_sync.py](dashboard/services/tiktok_sync.py)) ·
  **YouTube** `snippet.thumbnails` (`part=snippet` ดึงมาอยู่แล้ว **ไม่ยิง API เพิ่ม**) ·
  **Facebook** `picture.width(200)` (ขอพร้อมชื่อเพจใน `sync_pages` ที่ยิงอยู่แล้ว)
- **★ ยังไม่มีรูป = อักษรย่อบนวงกลมสีแพลตฟอร์ม ไม่ใช่กล่องว่าง** · `onerror="this.remove()"`
  โหลดไม่ขึ้นก็เห็นวงกลมที่รออยู่ข้างหลัง (กติกาเดียวกับการ์ดคลิปในหน้าโซเชียล)
- `tiktok_sync` เก็บ **ผู้ติดตาม/ชื่อ/username ล่าสุดลงทะเบียนช่อง** (`TikTokAccount.profile`) ด้วย →
  รายงานอ่านจากที่เดียว ไม่ต้องไล่หา snapshot ล่าสุดทุกครั้งที่เปิดหน้า
- **`manage.py social_avatars [--fetch] [--side] [--out]`** — ดึงเดี๋ยวนี้ ไม่ต้องรอเที่ยงคืน
  · **⚠️ รันด้วย root ไม่ได้** (`media/` เป็นของ `oxlet`) — คำสั่งเตือนให้พร้อมบอกคำสั่งที่ถูก
  · **★★ 3 ต.ค.69 (เจอตอนรีวิวโค้ด) — ขอ field เกินสิทธิ์ = ได้ศูนย์ทุกช่องแบบเงียบ**
    `_tiktok_avatar()` ขอ `username` มาด้วยทุกครั้ง แต่ field นั้นอยู่ใต้ **`user.info.profile`**
    ซึ่ง**ไม่ได้อยู่ในค่าตั้งต้น** (`user.info.basic,video.list`) · **TikTok ปฏิเสธทั้งคำขอเมื่อขอเกินสิทธิ์**
    → ตัวที่เขียนมาแก้เคส "TikTok 0/10" กลับคืน 0 ทุกช่องเสียเอง
    · `tiktok_oauth._fetch_user` gate ไว้ถูกแล้วตั้งแต่แรก — **ของใหม่ต้องเดินตามกติกาเดิม ไม่ใช่เขียนคำขอเอง**
  · **★ ลองใหม่เมื่อ "ลิงก์หมดอายุ" ไม่ใช่แค่ "ไม่มีลิงก์"** — ลิงก์รูปเป็น signed URL
    ของเดิมเช็คแค่ว่าทะเบียนมีลิงก์ไหม → รันหลังรอบ sync ไปไม่กี่ชั่วโมงก็ได้ 0 โดยไม่บอกอะไร
    · ตอนนี้โหลดจากลิงก์เดิมก่อน **ล้มแล้วค่อยขอใหม่**
  · **★ `except Exception: return ""` ครอบทั้งฟังก์ชัน = "ขอเกินสิทธิ์" กับ "เน็ตล่ม" หน้าตาเหมือนกัน**
    → เช็ค `status_code`/`error` จริง แล้วคืนเหตุผลออกมาโชว์ในบรรทัดสรุป (บทเรียนเดิมซ้ำรอบที่ N)
  · **วัดจริง 30/09**: Facebook ได้ 2/2 เพจทันที · TikTok 0/10 (ลิงก์รูปมากับรอบ sync ถัดไป
    เพราะเพิ่ง เพิ่ม field) · YouTube ต้องรันบน prod (API key ล็อก IP ของ VPS)

**ยังไม่ได้ทำ (รอเจ้าของบอก)**: ใครอยู่ทีมคอนเทนต์บ้าง + ให้สิทธิ์ดูแท็บโซเชียล —
ตอนนี้แท็บโซเชียลยังเป็น **admin เท่านั้น** (`_is_admin`)

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

### 📈 แท็บโซเชียล — Facebook / TikTok / YouTube **คนละหน้า** (ก.ย.69 · แยกหน้า 2 ต.ค.69)
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
- **★★ 26 ก.ย.69 — กดช่องเข้าไปดูคลิปรายชิ้นได้ (เจ้าของขอ *"ถ้าคุณรู้จักแอดไลบรารี ฉันอยากได้ประมาณนั้น"*)**
  *"อยากให้มันสามารถกดเข้าไปดูรายละเอียดของคลิปนั้นได้ แล้วก็อยากให้มันแบ่งช่องได้ด้วย …
  อยากวัด performance ของคลิปหนึ่งคลิปหรือช่องหนึ่งช่องไปเลย"*
  - **กดแถวในตาราง "แยกตามช่อง" → หน้าของช่องนั้น** (`soOpenChannel`) = KPI ของช่อง +
    **การ์ดคลิปแบบกริด** (`_soCard`) · กดการ์ด → หน้ารายชิ้นเดิม (`soOpenPostId`) ·
    กด "กลับ" จากหน้าคลิป **กลับมาที่หน้าช่อง ไม่ใช่หน้ารวม** (`_soCh` ไม่ถูกล้าง)
  - **`social_stats.channel_posts(side, owner, …)`** + `/api/admin/social?side=&owner=&offset=`
    · **★ ต้องเป็นคำขอแยก ห้ามส่งมาพร้อมก้อนภาพรวม** — เพจเดียวมีโพสต์ **580-589 ชิ้น**
      (วัดจริง 26/09) รวมทุกช่อง ~2,000 ชิ้น · ถ้าแนบ `postDaily` ของทุกชิ้นไปด้วยทุกครั้ง
      ที่เปลี่ยนช่วงวันที่ = JSON หลายร้อย KB ต่อครั้ง
    · คืน `{rows, total, daily}` — หน้าเว็บ **merge `daily` เข้า `postDaily` + `rows` เข้า `posts`**
      แล้วหน้ารายชิ้นเดิมทำงานต่อได้ทันที **ไม่ต้องแก้ `_soDetailHtml` เลย**
    · **`_side_cfg()` = ชื่อคอลัมน์ของ 3 แพลตฟอร์ม** (3 ตารางเก็บเรื่องเดียวกันแต่ตั้งชื่อคนละแบบ)
      → **เพิ่มแพลตฟอร์มใหม่ = เติมที่นี่ที่เดียว**
  - **★ KPI ของหน้าช่อง เอาจาก `byChannel` ไม่ใช่รวมจากการ์ดที่โหลดมา** — การ์ดโหลดทีละหน้า
    ถ้ารวมเองตัวเลขจะต่ำกว่าจริง **และขยับทุกครั้งที่กด "ดูเพิ่ม"**
  - **★ หน้าช่องไม่มีกราฟ โดยตั้งใจ** — ยอดรายวันที่ส่งมาเป็นของเฉพาะคลิปในหน้านั้น
    ลากเป็นเส้นของ "ทั้งช่อง" จะผิด · อยากดูกราฟให้กดเข้าไปรายคลิป (กติกาเดิม: เลขที่สื่อผิด
    อันตรายกว่าไม่มีเลข)
  - **⚠️ รูปปกมีเฉพาะ YouTube** (`_thumb` สร้างจาก video id ได้ฟรี) · **TikTok/Facebook ยังไม่มี** —
    API ให้ลิงก์รูปแบบ **มีวันหมดอายุ (signed URL)** เก็บลง DB แล้วอีกไม่กี่ชั่วโมงก็เปิดไม่ขึ้น
    → จะให้มีจริงต้อง **โหลดไฟล์มาเก็บเอง** ตอน sync (ยังไม่ทำ) · ระหว่างนี้การ์ด 2 ฝั่งนี้ใช้
    **แถบสีประจำแพลตฟอร์มสูง 44px** แทน (เคยทำ 130px แล้วเป็นกล่องเทาว่างเปล่า — ดูจากรูปจริงแล้วลด)
  - **เทสต์**: `python scripts/test_social_channel.py` (สร้างข้อมูลจำลองใน SQLite แล้วเรียกฟังก์ชันจริง —
    แยกช่อง/ผลต่างรายวัน/ยอดลดลงไม่ติดลบ/แบ่งหน้า/รูปปก YouTube/ฝั่งที่ไม่รู้จัก) ·
    **ตรวจ UI ด้วย Chromium จริง** (stub API ด้วย `page.route` แล้ว **ดูรูป + วัดพิกัด** —
    การ์ดสูงเท่ากันไหม · แถวละกี่ใบที่จอ 1180/820 · ล้นจอแนวนอนไหม · กดกลับแล้วไปไหน)
- **★★ 26 ก.ย.69 (รอบ 2) — การ์ดสรุปแยกช่องให้เห็นเลย + ย้ายตารางขึ้นก่อนกราฟ**
  (เจ้าของแจ้ง *"ยังไม่เห็นมีการแยกนะ กระจุกกันอยู่เลย"* ทั้งที่ตารางแยกช่องทำไปแล้วเมื่อ 24/09)
  - **ต้นเหตุไม่ใช่ "ไม่มี" แต่คือ "อยู่ไกลเกินกว่าจะเจอ"** — ตาราง `#so-ch` ถูกวางไว้
    **ใต้กราฟรายวันสูง 290px** → ต้องเลื่อนลงเกือบเต็มจอถึงเห็น · สิ่งที่อยู่บนสุดคือ
    การ์ด 3 ใบที่โชว์ **เลขก้อนเดียวต่อแพลตฟอร์ม** (TikTok 343,635 = รวม 10 ช่อง)
  - **`_soChanRows(side, d)`** = รายชื่อช่องย่อ **ในการ์ดสรุปเลย** — ชื่อ + วิว เรียงมากสุด
    **4 อันดับแรก** (`SO_CHAN_TOP`) แล้ว **"+ อีก N ช่อง — ดูตารางเต็ม"** → `soGotoChannels()`
    · กดแต่ละแถว = เข้าหน้าช่องนั้นตรงๆ (`soOpenChannel`) ไม่ต้องเลื่อนไปกดในตาราง
    · **ช่องเดียว = ไม่แสดงอะไร** (Facebook/YouTube ตอนนี้) — ไม่มีอะไรให้แยก
  - **ช่องที่ยังคิดยอดรายวันไม่ได้ โชว์ "ยอดสะสม" + ป้าย `สะสม` กำกับ** ไม่ใช่ `0` หรือเว้นว่าง
    (ในตารางเต็มยังเป็น `–` เหมือนเดิม เพราะที่นั่นมีคอลัมน์ "วิวสะสม" แยกอยู่แล้ว)
  - **ย้าย `_soChannels()` ขึ้นมาก่อนกราฟ** — "ช่องไหนทำได้เท่าไหร่" สำคัญกว่าเส้นกราฟรวม
  - **กฎ: ของที่เจ้าของขอ ถ้าวางไว้ใต้ของชิ้นใหญ่ = เท่ากับยังไม่ได้ทำ** — รอบนี้เสียไป 2 วัน
    เพราะสร้างตารางถูกแล้วแต่วางผิดที่ · ทำอะไรเสร็จให้เช็คด้วยว่า **เห็นได้โดยไม่ต้องเลื่อน**
- **★★ 26 ก.ย.69 (รอบ 3) — รูปปกคลิปจริง + แถบเรียงลำดับ** (เจ้าของขอ
  *"เอาหน้าปกคลิปมาใส่ในนี้เลยไม่ได้หรอ"* + ลิสต์ตัวกรอง 7 ข้อ)
  - **[covers.py](dashboard/services/covers.py) — โหลดไฟล์รูปปกมาเก็บเอง**
    · TikTok `cover_image_url` / Facebook `full_picture` เป็น **signed URL หมดอายุ ~6 ชม.**
      → เก็บลิงก์ลง DB ไม่ได้ ต้องโหลดตัวไฟล์ · เก็บที่ `MEDIA_ROOT/covers/<side>/<id>.jpg`
    · **YouTube ไม่ต้องเก็บ** — ประกอบจาก video id ได้ฟรีและไม่หมดอายุ
    · ทำ **หลัง** เขียนตัวเลขเสร็จเสมอ + `except` ครอบ — **ตัวเลขเสียแล้วเสียเลย รูปปกโหลดใหม่รอบหน้าได้**
    · sanitize id ก่อนทำชื่อไฟล์ (กัน `../`) · ตรวจ content-type · ตัดที่ 600 KB · เขียน `.part` แล้ว `os.replace`
    · ขนาดที่คาด: 2,244 ชิ้น × ~25 KB ≈ **56 MB**
  - **`manage.py social_covers [--fetch] [--side] [--out]`** — ดูว่ามีรูปปกกี่ใบ / ดึงเดี๋ยวนี้
    ไม่ต้องรอ sync เที่ยงคืน · **ดึงได้เฉพาะที่ยังอยู่ในหน้าต่างของ API** (TikTok ~90 วันล่าสุด)
    ของเก่ากว่านั้นไม่มีรูปปกถาวร — การ์ดใช้โลโก้บนพื้นสีแทน ไม่พัง
  - **⚠️★ 2 กับดักของคำสั่งนี้ (เจอตอนเจ้าของรันจริง — แก้แล้ว)**
    1. **กรองสถานะช่องผิดค่า**: เขียน `status="ok"` ซึ่ง **ไม่มีอยู่จริง** (ของจริงคือ
       `TikTokAccount.ACTIVE` = `"active"`) → กรองได้ **0 ช่อง** แล้วคำสั่งรายงาน
       "โหลดใหม่ 0" เงียบๆ เหมือนทำงานปกติ · **กฎ: กรองด้วยค่าคงที่ของโมเดล ห้ามพิมพ์สตริงเอง**
       · ตอนนี้ไม่มีช่องเลย = **บอกออกมาตรงๆ** ไม่ปล่อยให้เงียบ
    2. **★ รันด้วย root ไม่ได้** — บนเซิร์ฟเวอร์ `media/` เป็นของ user **`oxlet`** (ตัวที่รันเว็บ+cron)
       ถ้ารันด้วย root โฟลเดอร์ `media/covers/` จะเกิดมาเป็นของ root → **รอบ sync เที่ยงคืน
       เขียนรูปใหม่ไม่ได้อีกเลยแบบเงียบๆ** · คำสั่งเช็คเจ้าของ `MEDIA_ROOT` แล้วเตือน
       พร้อมบอกคำสั่งที่ถูก: `sudo -u oxlet .venv/bin/python manage.py social_covers --fetch`
  - **ทดสอบท่อโหลดรูปจริงแล้ว**: โหลด+เขียนไฟล์ได้ · URL ที่ส่งให้หน้าเว็บถูก · มีไฟล์แล้วข้าม ·
    **id อันตราย `../../etc/passwd` ถูกล้างเหลือ `etcpasswd.jpg` อยู่ในโฟลเดอร์รูปปก** ·
    ลิงก์เสีย/ไม่ใช่รูป (หน้า HTML) ปฏิเสธถูก
  - **★ กรอบรูปสูง 150px เสมอ ไม่ว่ามีรูปหรือไม่** — วัดจากรูปที่แคปจริง: ของเดิม
    มีรูป 150px / ไม่มีรูป 44px → **การ์ดในกริดสูงไม่เท่ากัน ดูขรุขระ**
  - **★ เลิกใช้ `onerror="this.parentNode.innerHTML=…"`** — ต้อง escape ซ้อน 2 ชั้น
    (`JSON.stringify` แล้วแทน `"` ด้วย `&quot;` ทับ `\"` ที่ escape ไว้แล้ว) → บางจังหวะได้กล่องว่าง
    · ตอนนี้ **วางรูปทับโลโก้ที่รออยู่ข้างใน** (`position:absolute;inset:0`) โหลดไม่ขึ้นก็ `this.remove()`
      เห็นโลโก้ที่อยู่ข้างหลัง — **ไม่ต้อง escape อะไรเลย**
  - **แถบเรียงลำดับ = 3 ช่องเล็ก** (`SO_SORTS` · `soChSort` · `_soSortNote`) แทน dropdown ยาว 14 บรรทัด:
    **เรียงตาม** (วิว/ไลก์/คอมเมนต์/แชร์/วันลงคลิป) × **มาก→น้อย หรือ น้อย→มาก** ×
    **ยอดในช่วงนี้ หรือ ยอดสะสม** = 20 แบบจากตัวควบคุม 3 ตัว · เลือก "วันลงคลิป" = ซ่อนช่องที่ 3
  - **★★ เรียงทำฝั่งเซิร์ฟเวอร์เสมอ** (`channel_posts(sort=, direction=, basis=)`) —
    หน้านี้โหลดทีละ 48 จาก 580 ชิ้น · เรียงฝั่งหน้าเว็บ = ได้ **"วิวน้อยสุดในหน้านี้"**
    ไม่ใช่ "วิวน้อยสุดของช่อง" ซึ่งตอบผิดคำถาม (มีเทสต์กันไว้)
  - **★ เรียงจากน้อยไปมากด้วย "ยอดในช่วง" → ชิ้นที่ยังคิดรายวันไม่ได้ต้องไปอยู่ท้าย**
    (ต้องมี snapshot 2 คืนถึงลบกันได้) ไม่งั้น "วิวน้อยที่สุด" กลายเป็นกอง 0 ของคลิปที่ไม่มีข้อมูล
    — เลขถูกตามสูตรแต่ตอบผิดคำถาม (กติกาเดิม: เลขที่สื่อผิด อันตรายกว่าไม่มีเลข)
  - **⚠️ "ยอดบันทึก (saves)" ทำไม่ได้ — ไม่มีแพลตฟอร์มไหนให้** ผ่าน API ที่เราใช้อยู่:
    TikTok Display API (`video.list`) ให้แค่ วิว/ไลก์/คอมเมนต์/แชร์ ·
    YouTube `favoriteCount` เลิกใช้ไปตั้งแต่ปี 2015 (คืน 0 เสมอ) · Facebook Graph ไม่เปิดยอดบันทึกของโพสต์เพจ
    → **ไม่ทำปุ่มที่กดแล้วได้ 0 ทุกคลิป** · อยากได้ต้องพิมพ์จากหลังบ้านของแต่ละแพลตฟอร์มเอง
  - **เทสต์**: `scripts/test_social_channel.py` เพิ่ม 9 ข้อเรื่องการเรียง ·
    **ตรวจ UI ด้วย Chromium จริง** (`page.route` stub แล้ววัดว่า **ยิงคำขอใหม่พร้อม sort/dir/basis จริง** ·
    การ์ดสูงเท่ากันหมด · รูปโหลดไม่ขึ้นแล้วเหลือโลโก้ · เลือกวันลงคลิปแล้วช่องที่ 3 หายไป)
- **★★★ 2 ต.ค.69 — แยกเป็น "คนละหน้า" ต่อแพลตฟอร์ม (เจ้าของสั่ง *"มันเทียบกันไม่ได้"*)**
  | แท็บ | id | เนื้อหา |
  |---|---|---|
  | **Facebook** | `so` | เพจ · + เส้นประ "ยอดที่เพจรายงานเอง" · ค่าโฆษณาในช่วง |
  | **TikTok** | `tt` | ช่อง |
  | **YouTube** | `yt` | ช่อง (คอลัมน์แชร์ขึ้น `–` — API ไม่ให้) |
  | **คอนเทนต์** | `ct` | รายงานทีมคอนเทนต์ (`content-card`) — **ข้ามแพลตฟอร์มโดยเจตนา จึงมีหน้าของตัวเอง** |
  - **ทำไมเทียบกันไม่ได้จริง** (ไม่ใช่แค่ความรู้สึก): นิยามเมตริกคนละชุด (YouTube ไม่มียอดแชร์เลย) ·
    **ความครอบคลุมของยอดรายวันคนละระดับ** — วัดจริง 23/09: FB จับคู่ได้ **1,126/1,158 โพสต์ (97%)**
    แต่ TikTok ได้ **1 จาก 533 คลิป** → วาง "TikTok 1" ข้าง "Facebook 76,494" แล้วอ่านเป็น
    "TikTok ตายแล้ว" ซึ่งไม่จริง · ชื่อหน่วยคนละคำ (เพจ/ช่อง) · ตัวเทียบของ FB ไม่มีในอีก 2 ฝั่ง
  - **★★ ยังยิง API ก้อนเดียว** — `/api/admin/social` คืนทั้ง 3 ฝั่งเหมือนเดิม แล้วแคชร่วมกัน
    (`_soRange` = ช่วงวันที่) → **สลับแท็บไม่โหลดใหม่ · เซิร์ฟเวอร์ไม่ได้ทำงานเพิ่มเลยสักนัด**
    (ยืนยันในเบราว์เซอร์จริง: เข้า Facebook ยิง 1 ครั้ง · TikTok/YouTube ยิง 0)
  - **`SO_TAB_SIDE = {so:'meta', tt:'tiktok', yt:'youtube'}`** + `_soSide` = ฝั่งที่หน้านี้ดูอยู่
    · **ลบ `SO_SIDES` ทิ้งแล้ว** (กลายเป็นลิสต์ที่ไม่มีใครใช้ = รอวันที่คนแก้ผิดตัว)
    · `_soKpi/_soChannels/_soTopRows` รับ `side` · `_soPiece()`/`_soUnit()` คุมคำว่า โพสต์/คลิป · เพจ/ช่อง ที่เดียว
    · **เพิ่มแพลตฟอร์มใหม่** = `SO_TAB_SIDE` + `SO_NAME/SO_COLOR/SO_ICON` + `NAV_TABS` + `TAB_DESC` + `_TAB_ID`
  - **★★ 4 ต.ค.69 — เมนูซ้ายรวมเหลือปุ่ม "โซเชียล" ปุ่มเดียว** (เจ้าของ *"เอาไปรวมกัน แยกออกมาทำไม"* +
    รูปเมนูที่มี Facebook/TikTok/YouTube/คอนเทนต์ เรียง 4 แถว)
    · **เนื้อหายังแยกคนละหน้าเหมือนเดิม** (กติกา 2 ต.ค. "เทียบกันไม่ได้" ยังอยู่) — รวมแค่ทางเข้า
    · บนหน้ามี **แถบสลับ `socialSubBar()`** (Facebook | TikTok | YouTube | คอนเทนต์) · หัวเว็บขึ้น "โซเชียล · TikTok"
    · NAV_TABS ยังมีครบ 4 id (`so/tt/yt/ct`) แต่ 3 ตัวติด **`sub:1`** = ไม่วาดในเมนู → ลิงก์ `?tab=` เดิม ·
      `report_shot._TAB_ID` (แคปการ์ดคอนเทนต์) · `test_tab_map.py` ใช้ได้ตามเดิม · ปุ่ม "โซเชียล" ติด `.on`
      เมื่ออยู่หน้าไหนก็ได้ใน 4 หน้า และพากลับไปแพลตฟอร์มที่ดูล่าสุด (`_soLastTab` · `var` กัน TDZ)
    · ตรวจด้วย Chromium บน dev server จริง 22/22 (จอ 1590 / 390)
  - **ตารางโพสต์ไม่มีคอลัมน์ "ช่องทาง" แล้ว** — หน้ามันบอกอยู่แล้วว่าดูแพลตฟอร์มไหน
  - **เมนูใช้โลโก้จริงของแพลตฟอร์ม** (`NAV_TABS[].img`) — dict `LUCIDE` ไม่มีไอคอน facebook/tiktok/youtube
    · ปุ่มเมนูรองรับ `img` แล้ว (ไม่มี = ใช้ `ic()` เหมือนเดิม)
  - **★ ย้ายแพลตฟอร์มแล้วต้องล้างหน้าที่เปิดค้าง** — `renderSocial(side)` เคลียร์ `_soCh`/`_soOpen`
    ถ้าเป็นของฝั่งก่อนหน้า ไม่งั้นกดเข้าช่อง TikTok แล้วสลับไป Facebook จะเจอคลิป TikTok ค้างอยู่
  - **★ บั๊กเก่าที่เจอตอนแยก — การ์ดคอนเทนต์หายเมื่อกลับเข้าแท็บ**: `loadContentReport` เคย
    `return` ทิ้ง**ก่อน**บรรทัดวาด เมื่อข้อมูลแคชไว้แล้ว → slot ถูกสร้างใหม่ว่างเปล่าแต่ไม่มีใครเติม
    · แยกเป็น **`_crPaint()`** แล้วเรียกทั้ง 2 ทาง
  - ช่องตัวเลขใน KPI เปลี่ยนจาก 2 คอลัมน์ตายตัวเป็น `auto-fit minmax(150px)` — การ์ดเต็มจอแล้ว
    (จอกว้าง 4 ช่องเรียงเดียว · มือถือห่อเป็น 2×2 · วัดจริง 390/820/1440px ไม่มีเลขล้นกล่อง)
  - **เทสต์**: `python scripts/test_tab_map.py` (41 ข้อ — **อ่าน `NAV_TABS` ออกจาก index.html จริง**
    แล้วเช็กว่าทุกค่าใน `_TAB_ID`/`_CARD_TAB` ชี้แท็บที่มีอยู่) · พิสูจน์แล้วว่าจับ regression ได้จริง
    (ลองแก้แท็บของ `content-card` ให้ผิด → ร้อง 2 ข้อ) · **ตรวจ UI ด้วย Chromium จริง**
    (stub `/api/admin/social` แล้ววัดว่าแต่ละหน้ามีการ์ดฝั่งเดียว · เส้นกราฟกี่เส้น · ยิง API ซ้ำไหม)
- **★★ 3 ต.ค.69 — เมตริกที่แพลตฟอร์มไม่มีให้ ต้องขึ้น `–` ทั้งหน้า ไม่ใช่ 0** (เจอตอนรีวิวโค้ด)
  - ตารางแยกช่องใช้ `–` มาตั้งแต่ ก.ย.69 แล้ว แต่ **ที่อื่นยังโชว์ 0**: KPI การ์ด · ตารางคลิป ·
    การ์ดคลิปในหน้าช่อง · KPI หน้าช่อง · KPI หน้ารายคลิป — รวม **5 จุด**
  - ตอนรวม 3 แพลตฟอร์มไว้หน้าเดียวยังพอให้อภัย (แถว YouTube ปนกับแถวที่มีเลขจริง)
    · **พอแยกเป็นหน้าของ YouTube เอง เลข 0 ไปโผล่ทั้งหน้า** = อ่านเป็น "ไม่มีใครแชร์เลย" ซึ่งไม่จริง
  - **`SO_NO_METRIC = { youtube: ['shares'] }`** + `soHas()` / `soDash()` / `soNum()` / `soMetrics()`
    → **เพิ่มเมตริกที่ฝั่งไหนไม่มี = เติมที่เดียว** ทุกจุดตามเอง
  - **ชิปเลือกเมตริกซ่อน "แชร์" บนหน้า YouTube ด้วย** + `drawSocial` รีเซ็ต `_soMetric` เป็น `views`
    ถ้าเมตริกที่ค้างมาจากหน้าก่อนไม่มีในฝั่งนี้ — ไม่งั้นได้**กราฟแบนติดศูนย์** ซึ่งสื่อผิดหนักกว่าเดิม
- **★ 3 ต.ค.69 — เปลี่ยนช่วงวันที่ต้องล้าง "หน้าช่อง" ด้วย** (`_soCh`) ไม่ใช่แค่หน้าคลิป (`_soOpen`)
  — แถวในหน้าช่องถูกดึงมาด้วยช่วงวันที่เดิม ถ้าไม่ล้างจะค้างเลขของช่วงเก่าทั้งที่ตัวกรองเปลี่ยนไปแล้ว
- **★ 3 ต.ค.69 — `loadContentReport` ต้องล้าง `_crRange` เมื่อโหลดล้ม**
  ของเดิมเก็บ `_crData = {error}` ไว้แต่ `_crRange` ยังเป็น**ช่วงที่โหลดสำเร็จก่อนหน้า**
  → สลับกลับไปช่วงนั้น แคชจะ "ตรง" แล้ววาด**การ์ด error ซ้ำ โดยไม่ลองใหม่อีกเลย**
  (`loadSocial` ไม่มีปัญหานี้เพราะไม่แตะ `_soData`/`_soRange` ตอนล้ม)
- **ยังไม่ได้ทำ**: ผู้ติดตามเพจ Facebook (ตารางขึ้น `–` — ยังไม่ได้เก็บ) ·
  ยอด "ไลก์รายวัน" ของ TikTok ระดับช่อง · ผูกยอดโฆษณากับโพสต์ (Meta ให้ ad_id ไม่ใช่ post_id ตรงๆ) ·
  **ยอดบันทึก (saves)** — API ไม่ให้ทุกแพลตฟอร์ม

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
  - **แก้รอบแรก** (`dfType()` — เปลี่ยน `onchange` เป็น `oninput`): (1) ปีนอก 2000–2100 = ยังพิมพ์ไม่เสร็จ
    (2) หน่วง 450ms หลังหยุดพิมพ์ (3) คืนโฟกัสให้ช่องเดิมหลัง `render()` (`_dfFocus`)
  - **⚠️ กฎ: ช่องกรอกอะไรก็ตามที่เรียก `render()` ต้องคิดเรื่อง "DOM หายระหว่างพิมพ์" เสมอ** —
    `render()` ล้างทั้งหน้า ไม่ใช่แค่ส่วนที่เปลี่ยน · ถ้าไม่หน่วง+คืนโฟกัส ผู้ใช้จะพิมพ์ไม่ได้
- **⭐⭐ 4 ต.ค.69 — "ยังไม่เลือกวัน แค่เลื่อนเดือน มันเลือกวันให้เอง" (เจ้าของแจ้ง · regression ของตัวแก้รอบแรก)**
  - **ต้นเหตุ**: **Chrome เปลี่ยนค่าในช่องสดๆ ทุกครั้งที่เลื่อนเดือนในปฏิทิน** (วันเดิมของเดือนใหม่) แล้วยิง `input`
    → `dfType` หน่วง 450ms แล้ว `render()` → **ปฏิทินถูกปิดทิ้ง + ตัวกรองกลายเป็นวันที่ไม่ได้เลือก**
    · พิสูจน์ด้วยโค้ดเดิมใน Chrome จริง: เลื่อนเดือน 1 ครั้ง → ตัวกรองเป็น 1 ต.ค. เอง หน้าวาดใหม่ ปฏิทินปิด
  - **★ พฤติกรรมจริงของ Chrome 154 (วัดด้วย Playwright + Chrome ที่ติดตั้งในเครื่อง · คุมปฏิทินด้วยคีย์บอร์ดได้)**
    | ทำอะไร | event ที่ได้ |
    |---|---|
    | เลื่อนเดือน / ขยับวันในปฏิทิน | `input` อย่างเดียว · ระหว่างนั้น **`el.matches(':open')` = true** |
    | เลือกวัน (คลิก/Enter) | `change` หลังปฏิทินปิด (`:open` = false) · โฟกัสยังอยู่ที่ช่อง |
    | คลิกที่อื่นบนหน้า (ปิดเฉยๆ) | หน้าเว็บได้ **`pointerdown` ก่อน** แล้ว blur → `change` · **ค่าค้างเป็นเดือนที่เลื่อนไป** |
    | คลิกไอคอนปฏิทินซ้ำ | `pointerdown` → `change` (ตอนนั้นปฏิทินเปิดใหม่แล้ว `:open` = true) |
    | Escape | Chrome คืนค่าเดิมเอง (`input` ขณะยังเปิด) · กดอีกครั้งถึงปิด ไม่มี `change` |
    | พิมพ์ | keydown → `input` + `change` **ทุกตัวอักษร** (ปี "2" = 0002) |
    · **คลิกในตัวปฏิทินไม่ถึงหน้าเว็บ** (เป็น widget แยก) → `pointerdown` บนหน้า = ปิดปฏิทินโดยไม่ได้เลือกแน่นอน
  - **แก้: `dateEvt()` ตัวเดียวคุมทุกช่องวันที่ที่ "เลือกแล้วใช้ทันที"** ผูกด้วย `_dtOn('ชื่อฟังก์ชัน', allowEmpty)`
    (ใส่ onkeydown/oninput/onchange/onblur ให้) · กติกา: **ปฏิทินเปิดอยู่ = ไม่ทำอะไร** · **เลือกวัน (`change`) = ใช้ทันที**
    · **ปิดเฉยๆ = คืนค่าเดิม** (`pointerdown` capture คืน `el.value = el.defaultValue` ให้ช่องที่กำลังเลื่อนดู) ·
    **พิมพ์** (input/change ตามหลัง keydown ตัวเลข/↑↓/Backspace/Delete ภายใน 300ms) = รอหยุดพิมพ์ 450ms ·
    Enter = ใช้ทันที · ปีไม่ครบแล้วออกจากช่อง = คืนค่าเดิม
    · **ค่าที่ "ใช้อยู่" = attribute `value` ของช่อง (`el.defaultValue`)** → ใช้ได้เพราะทุกครั้งที่ใช้ค่าใหม่ หน้าวาดช่องใหม่
    · ตัวหน่วงที่ค้างอยู่ตอนหน้าวาดใหม่ (เช่นกดปุ่มลัดระหว่างพิมพ์) ถูกทิ้งด้วย `el.isConnected` — ไม่มาทับค่าที่เพิ่งเลือก
    · เบราว์เซอร์ที่ไม่รู้จัก `:open` = `matches` โยน error → ถือว่าปิด แล้วใช้ค่าตอน `change` (Firefox ไม่เปลี่ยนค่าตอนเลื่อนเดือนอยู่แล้ว)
  - **ใช้อยู่ 3 ที่**: ตัวกรองช่วงวันที่หน้ารวม (`dfApplyFrom`/`dfApplyTo`) · พาเนลเช็คชื่อ (รายวัน + สรุปช่วง) ·
    **ตัวกรองหน้าเซลล์ [seller.html](dashboard/templates/dashboard/seller.html)** (`sfApplyFrom`/`sfApplyTo` · ค่าว่าง = ล้างช่วง
    เหมือนเดิม) — **seller.html มีสำเนาโค้ดชุดเดียวกัน แก้กติกาต้องแก้ทั้ง 2 ไฟล์** (ไม่แยกเป็นไฟล์ JS กลาง เพราะไฟล์ static
    ใหม่ต้อง `collectstatic` ตอน deploy · ลืมเมื่อไหร่ = ตัวกรองวันที่พังทั้งหน้า)
    · หน้าเซลล์เดิมใช้ `onchange` → **พิมพ์วันที่ไม่ได้มาตลอด** (บั๊กเดียวกับ 24 ก.ย. ที่แก้ไปแค่หน้ารวม) — แก้ไปพร้อมกันแล้ว
  - **⚠️ ที่ยังเป็นพฤติกรรมของ Chrome เอง (แก้ไม่ได้)**: ตอนเลื่อนเดือน **ตัวเลขในช่องยังเปลี่ยนตาม + วันเดิมของเดือนใหม่ถูกไฮไลต์**
    — แต่ระบบไม่เอาไปใช้จนกว่าจะคลิกเลือกวันจริง
  - **เทสต์** (สคริปต์ใน scratch ของเซสชัน 4 ต.ค. · ดึงโค้ดจาก template ตัวจริงมารันกับ Chrome ที่ติดตั้งในเครื่อง):
    index 23/23 · seller 24/24 — เลื่อนเดือน/ขยับวัน/Escape/คลิกนอก/คลิกไอคอนซ้ำ/ข้ามไปช่อง "ถึง"/Alt+↓/พิมพ์ปี/พิมพ์วัน/
    พิมพ์ไม่ครบแล้วออก/Enter/ปุ่มลัดระหว่างพิมพ์ · **คลิกเมาส์ในตัวปฏิทินทดสอบอัตโนมัติไม่ได้** (คลิกจาก Playwright
    ไปโดนหน้าเว็บ = ปิดปฏิทิน) → ใช้คีย์บอร์ดคุมแทน (ตอนปฏิทินเปิด Chrome ส่งคีย์ไปที่ปฏิทิน) · ใช้ `channel="chrome"`
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

## Deploy บน Vercel (ประวัติ — เลิกใช้แล้ว)

> **เลิกใช้ตั้งแต่ มิ.ย.69** — ย้ายไป VPS Hostinger แล้ว (ดู [deploy/DEPLOY.md](deploy/DEPLOY.md)) · ลบ `vercel.json`/`.vercelignore` แล้ว 16 ต.ค.69 · เก็บหัวข้อนี้ไว้เพราะรายชื่อ env ยังใช้อ้างอิงได้

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
        - **★ 12 ต.ค.69 ปุ่มลูกศร « / » ย่อ-กางแถบซ้าย** (ผู้ใช้: "หน้าแชทค่อนข้างแคบ" · ชี้ตำแหน่งข้างชื่อ Oxlet Dashboard)
          · `.nav-mini` ใน `.nav-head` → `toggleSbMini()` สลับ class **`sb-mini`** บน `<body>` (ไม่ render ใหม่) · จำไว้ใน localStorage **`sbMini`**
          · ย่อ = `--sb-w: 68px` เหลือไอคอน (ชื่อแท็บอยู่ใน `<span class="ntab-l">` ซ่อนได้ · `title` = ชื่อตอนชี้เมาส์) · ป้ายตัวเลข Connect ย้ายไปมุมไอคอน
            · กรอบแชท Connect กว้างขึ้น 184px (1294 → 1478 ที่จอ 1590) · หลังสลับวัดแคปซูล/กรอบแชทใหม่ (`positionNavInd` · `fitConnectFrame`)
          · **CSS อยู่ใน `<style>` ของ index.html ไม่ใช่ globals.css** → ไม่ต้อง collectstatic · จอ <1100px ปุ่มไม่โผล่ (ยังเป็น ☰ drawer เห็นชื่อครบ)
          · ปุ่มกินที่หัวแถบ → โลโก้ 28px + ชื่อไม่ตัดบรรทัด (เดิม "Oxlet Dashboard" แตก 2-3 บรรทัดตอนใส่ปุ่ม)
          · ตรวจ Chrome 21/21 (ย่อ/กาง · สลับแท็บ/รีเฟรชยังจำ · มือถือ · ไม่ล้นจอ · ไม่มี JS error)
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
  - **★ 13 ต.ค.69 กรอบไม่ใช่ 100vw แล้ว** — กรอบลอดใต้แถบเมนูซ้าย (จอ ≥1100px) คอลัมน์ รูป/รหัส โดนบัง ~220px ที่จอ 1280 →
    **`fitTrkFrame()`** (index.html) วัดขอบขวาของ `#nav-slide` แล้วตั้ง `marginLeft`/`width` ให้กรอบเริ่มต่อจากแถบเมนูพอดี
    (เรียกหลัง render + 350ms + `onload` ของกรอบ + resize + ตอนย่อ/กางแถบเมนู) · ไม่มีแถบเมนู (จอแคบ) = เต็มจอเหมือนเดิม
- **★ หน้าตาใหม่ "เรียบหรู" ของหน้าสถานะรถ (13 ต.ค.69 · เจ้าของส่งคลิปตัวอย่าง SaaS + ขอ "ปุ่มสมูดลื่นๆ · Luxury")**
  - เจ้าของเลือก: **ทำเฉพาะหน้าสถานะรถ** · **โทนม่วงขาวเดิม** (ไม่ใช่ดำขาวแบบคลิป — กติกา 19 ก.ย.)
  - **สไตล์อยู่ใน `<style>` ของ [dashboard.html](templates/dashboard.html) ทั้งหมด ขึ้นต้น `html.lux`** — คลาส `lux` ถูกใส่บน `<html>`
    ตอนต้น block content ของหน้านี้หน้าเดียว → **หน้าอื่นที่ใช้ base.html (หน้าสแกน QR ของคนงาน · ฟอร์มแก้รถ · ผู้ใช้) ไม่โดน**
    · จะขยายไปหน้าอื่น = ใส่ `<script>document.documentElement.classList.add('lux')</script>` + ย้ายกฎไปไฟล์กลาง
  - ของที่เปลี่ยน: โทเคนสี/เงา (`--sh1`/`--sh2`/`--sh-pri`/`--ease`) ทั้งสว่าง+มืด · ปุ่ม `.btn` ยกขึ้นตอนชี้/ยุบตอนกด/วงโฟกัสม่วง ·
    `.btn.pri` ไล่สีม่วง · ช่องกรอก/select ลูกศรเอง (กฎรวมใช้ `:where()` เพื่อให้กฎเฉพาะชนะ — เคยทำไอคอนค้นหาทับตัวอักษร) ·
    **ตัวเลือกแบบแถบเลื่อน `.seg`** (`segSync`/`segInit` · แผ่นขาวเลื่อนตามตัวที่เลือก · ลิงก์ เลื่อนก่อน 180ms แล้วค่อยเปลี่ยนหน้า) ใช้กับ
    "รถในระบบ/ขายแล้ว" และ "งานของฉัน/ทั้งหมด" · KPI การ์ดใหม่ (`.k-top`) · บอร์ด (`.bcol`/`.bcard` ยกตอนชี้ · ตัวเลขใน `.bc-n`) ·
    ตาราง (`.twrap` หัวตรึง · `.cthumb` · `.chev` เลื่อนตอนชี้) · ป๊อปอัปพื้นหลังเบลอ + เด้งขึ้น (`luxFade`/`luxPop`) ·
    เคารพ `prefers-reduced-motion`
  - **⚠️ ไอคอน lucide ถูกแปลง `<i>` → `<svg>` หลังโหลด** — CSS ที่เขียน `.x i{}` จะไม่โดน ต้องเขียน `.x svg{}` (เคยทำแว่นขยายลอยเหนือช่องค้นหา)
  - `.chartgrid>*{min-width:0}` — กราฟวาดตอนกรอบยังกว้างแล้วไม่หดตาม → ทั้งหน้าล้นแนวนอน
  - ปุ่ม "เพิ่มรถ" ในกรอบซ่อนเมื่อหน้าแม่มีแถบ `.trk-tb` (แท็บสถานะรถของแดชบอร์ดขาย) · หน้าเซลล์ยังเห็น
  - แถบปุ่มเหนือกรอบใน index.html = คลาส `.trk-tb` (ใน `<style>` ของ index.html · ไม่ต้อง collectstatic) · เพิ่มไอคอน
    `qr-code`/`building-2` เข้า `LUCIDE` แล้ว
  - แก้ไปพร้อมกัน: มือถือซ่อนคอลัมน์ผิด (`nth-child(7)` = คอลัมน์ Active ตั้งแต่เพิ่มคอลัมน์ → เปลี่ยนเป็น 8 = ลูกศร)
- **★★ 13 ต.ค.69 (รอบ 2) — หัวเว็บบาง + "ไม่มีหน้าต่างลอย" ในหน้าสถานะรถ** (เจ้าของ: *"แถบด้านบนใหญ่เกินไป รก · ไม่เอาหน้าต่างลอย
  ต่อให้จะดูสถานะ หรือเพิ่มลบแก้ไขรูป แบ่งออกไปเป็นหน้าหนึ่งเลย"*)
  - **หัวเว็บแท็บ 't'** (`_hdrThin` ใน `render()` ของ index.html) = แถวเดียว ~43px: `Oxlet Dashboard › สถานะรถ` · ไม่มีป้ายบทบาท/ดูในฐานะ/รีเฟรช/
    บรรทัดเวลาดึงข้อมูล/คำอธิบายแท็บ · มือถือ: ซ่อนชื่อเว็บ ปุ่มออนไลน์/ออกจากระบบเหลือไอคอน `nowrap` (เดิมแตก 3 แถว)
  - **ในกรอบ `/track/` ([dashboard.html](templates/dashboard.html))**: ทุก `.ov` (รายละเอียดรถ · ยืนยันเปลี่ยนสเตป · เพิ่มรถ · ยืนยันถ่ายเสร็จ)
    เป็น "หน้า" — `pgSync()` จัดลำดับตามที่เปิด (ตัวบนสุดได้ `.pg-top`) · `body.paged` ซ่อนเนื้อหาอื่นใน `.wrap` · แต่ละหน้ามีแถบ "← กลับ" + ชื่อ
    (`PG_TITLE`) · `pgBack()` เรียกตัวปิดเดิม (`PG_CLOSE`) · Esc = กลับ · กดพื้นหลังไม่ปิดแล้ว · ปิดหมด = เลื่อนกลับตำแหน่งเดิมบนบอร์ด
    · **ตัวปิดเดิม (closeCar/closeStage/…) ไม่ได้แก้** — แค่ซ่อน/โชว์ด้วย `style.display` ตามเดิม แล้ว MutationObserver จับ
  - **หน้าต่างของแดชบอร์ดขาย** (เพิ่มรถ/ถังขยะ/สาขา/ผู้ใช้ + `openTrkCar` จากกระดิ่ง) — `_trkOverlay()` เรียก `_pageNext(id)` → กลไก `_pageify`
    เดิมแปลงเป็นหน้า · ปุ่ม "กลับหน้าสถานะรถ" · URL `?tab=t&panel=trk-…` (ปุ่ม Back ของเบราว์เซอร์ใช้ได้ · ปิดแล้วเหลือ `?tab=t`)
  - **กรอบสูงพอดีจอ**: `fitTrkFrame()` ตั้งความสูง = ขอบล่างจอ − ตำแหน่งกรอบ · ResizeObserver ที่ `#dashboard-root` วัดซ้ำ
  - **กราฟในกรอบไม่หดตาม** (Chart.js ไม่จับตอนกรอบถูกปรับขนาดทีหลัง → หน้าล้นแนวนอน) → `resize` + ResizeObserver ที่ `.chartgrid` สั่ง
    `chart.resize()` เอง + `.chartgrid canvas{max-width:100%}`
  - ตรวจ Chrome: การ์ด → หน้ารถ → หน้ายืนยันสเตป → กลับ 2 ครั้งถึงบอร์ดที่ตำแหน่งเดิม · ปุ่มแถบเครื่องมือ 4 ปุ่ม + กระดิ่ง เปิดเป็นหน้า ·
    จอ 1280/375 ไม่ล้นแนวนอน · ไม่มี JS error
- **★ 13 ต.ค.69 (รอบ 4) — แกลเลอรีรูปรถ + "⭐ ตั้งเป็นรูปหลัก" อยู่ในหน้ารายละเอียดรถแล้ว** (เจ้าของถาม *"ปุ่มเพิ่มรูปรถ … เลือกเป็นหน้าหลัก หายไปไหน"*
  — ของเดิมอยู่หน้า "แก้ไข" ซึ่งเป็นปุ่มเล็กล่างสุด หาไม่เจอ) · ใต้รูปรถ: รูปย่อทุกรูป · รูปแรก = รูปหลัก (กรอบม่วง) · ปุ่มตั้งเป็นรูปหลัก/ลบ ·
    เพิ่มรูปหลายรูป (`/track/api/upload` target=disk → `api_car_photos` add) · `_photosHtml`/`_cpInner`/`cpCall`/`cpUpload` ใน [dashboard.html](templates/dashboard.html)
  · `car_json` ส่ง `salePhotos` (= `_sale_photos_ctx`) + `canPhotos` (= `can_edit_car` ตรงกับ API) · ไม่มีสิทธิ์ = เห็นรูปย่อกดดูอย่างเดียว
  · รูปหลัก = `Car.photo` = ปกบนเว็บโชว์รูม (api_car_photos save → post_save ส่งไปเว็บเองถ้าอยู่พร้อมขาย/จอง) · หน้า "แก้ไข" ยังมีแกลเลอรีเดิม
  · **รูปเต็มกรอบ** (เจ้าของ: "รูปไม่เต็ม ดูแปลก" — เดิมบีบสูง 340px วางกลางกรอบเทากว้างทั้งจอ) — จอ ≥900px: รูปซ้าย (`.cp-main` 4:3 cover) ข้อมูล+หมายเหตุขวา (`.cd-top`) · จอแคบเรียงบนลงล่าง
  · **หมายเหตุยาวไม่บังช่องอื่นแล้ว** (เจ้าของ: "หมายเหตุยาวเกินก็บัง") — `_noteHtml()` ย้ายหมายเหตุออกจากตารางช่องแคบมาเต็มความกว้างใต้ตาราง ·
    ตัวคั่น `•••••//•••••` ของ Car Spend → ขึ้นบรรทัดใหม่ · ยาวเกิน 160 ตัว/3 บรรทัด = พับไว้ 3 บรรทัด + ปุ่ม "ดูหมายเหตุทั้งหมด" · escape แล้ว (เดิม `kv()` ไม่ escape)
  · ⚠️ ทดสอบในเครื่อง: `.env` dev มี `GDRIVE_*` ที่ token หมดอายุ → อัปรูป 502 (`default_storage` เป็น Drive แม้ target=disk) — รัน dev ด้วย `GDRIVE_REFRESH_TOKEN=` ว่าง
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
- **deps เพิ่ม** ([requirements.txt](requirements.txt)): `psycopg2-binary`, `qrcode[pil]`, `Pillow` · **`vercel.json` (ลบแล้ว 16 ต.ค.69) ขยาย `maxLambdaSize` 15→50mb** (ไม่งั้น build ไม่ผ่าน)
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
        · **ข้อยกเว้น 3 ต.ค.69**: ลูกค้าใน Connect เก็บลิงก์รูปที่ `ChatOwner.picture_url` (เจ้าของขอ) — ดู section "Connect"
          · `LineProfile` ยังไม่มีช่องรูปเหมือนเดิม
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
  - **รูป/ไฟล์ของแชทลูกค้า 1:1 โหลดเก็บแล้ว (11 ต.ค.69)** — ดูหัวข้อ "รูป/ไฟล์ที่ลูกค้าส่งในแชท" · `media_token` = สถานะการโหลด
  - **ยังไม่ทำ**: ดึง**ไฟล์รูปจากกลุ่ม LINE** (แชทกลุ่มไม่โหลด — โหลดเฉพาะแชทลูกค้า)
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
  `ลูกค้าถามหากี่ครั้ง (leadCarsByMonth · 3 เดือนล่าสุด) ÷ (พร้อมขาย + เพิ่งรับเข้า + 1)`
  · สต๊อกจาก `cars_car` (stage `show` = พร้อมขาย · **ตรงกับสถานะ "พร้อมขาย" ของ Car Spend เป๊ะ**
  วัดจริง 26/09: 90 = 90) · +1 กันหารศูนย์ + ทำให้ "มี 0 คัน" แรงกว่า "มี 1 คัน"
  · **ชื่อรุ่นของรถในสต๊อกเอาจากชีต จับด้วยทะเบียน** ไม่ใช่ชื่อจาก Car Spend (ดูรอบ 26/09 ด้านล่าง)
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

**★★ 25 ก.ย.69 (รอบ 2) — เลิกเดาชื่อรุ่น เมื่อทีมกรอกไว้ให้แล้ว** (เจ้าของเลือก *"ใช้เลย ทั้ง S และ AV"*)

ชีตจัดซื้อมี **ช่องรถตามสูตรที่สะอาดอยู่แล้ว 2 ช่อง** ที่ผมไม่เคยอ่าน — ไปนั่งเดาจากข้อความที่คนพิมพ์อิสระแทน
- **S (18) "car" ฝั่งเคส** — ทีมกรอกไว้ **375/379 = 98%** · `purchase_followup` คืนมาเป็น `model_std`
  · `rank_cases` **ใช้ S ก่อน แล้วค่อยเดาจาก D** → ทำสิ่งที่ตัวเดาทำไม่ได้เลย:
  `"HONDA CITY 2021 ขาว"` → **City 4 ประตู** · `"CITY HATCHBACk ปี24"` → **City 5 ประตู**
  (คนละรุ่นในสายตาตลาด แต่ข้อความไม่ได้บอก) · `"CIVIC 2019 ขาว"` → **Civic FC**
  · **วัดจริง: จับรุ่นที่ขาดตลาดได้ 85/109 เคส · 10 เคสในนั้นจับได้เพราะ S เท่านั้น**
- **AV (47) "รถตามสูตร" ฝั่งจัดซื้อรับเข้า (AP–AV)** → `recent_bought()` = **"รุ่นนี้เพิ่งรับเข้ามาแล้วกี่คัน"**
  · สูตรขาดตลาดเปลี่ยนเป็น `ถามหา ÷ (พร้อมขาย + เพิ่งรับเข้า + 1)` (`BOUGHT_DAYS`=14)
  · **★ ทำไมจำเป็น**: ช่อง "พร้อมขาย" มาจาก `cars_car` ที่เติมด้วย `sync_carspend` ซึ่ง **ยังไม่ได้ตั้ง cron**
    (วัดจริง 25/09: รถที่รับเข้าวันที่ 23 ยังไม่มีในตาราง) → รุ่นที่จัดซื้อเพิ่งหามาได้ **ยังขึ้นว่าขาดตลาด
    แล้วทีมไปวิ่งหาซ้ำ** · ชีต AP–AV ทีมกรอกเองวันต่อวัน จึงทันกว่าสต๊อกหลายวัน
  · วัดจริง: 11 รุ่นถูกลดอันดับ (Yaris Ativ +2 · Civic FE +2 · HRV +4 · Mazda3 +3 …)
  · **⚠️ `boughtCars` ต่อ AV/AQ ไว้ท้ายลิสต์เท่านั้น** — index 0-3 เดิมห้ามขยับ (index.html อ่าน `r[2]`/`r[3]` อยู่)
    · แถวจากแคชรุ่นก่อน 25/09 ยังไม่มี AV → `recent_bought` **ข้ามแถวนั้น ไม่เดาจากอะไรอื่น**

**★★ 25 ก.ย.69 — กันแท็บชีต "หายทั้งเดือน" ตอนข้ามปี / ตอนทีมยังไม่สร้างแท็บ** (เจ้าของสั่ง *"ทำต่อยาวๆ ถึงปีหน้าเลย"*)
- **`_be2(year=None)`** ([fetch_dashboard.py](dashboard/services/fetch_dashboard.py)) = ปี พ.ศ. 2 หลักของตอนนี้
  (`(ปี ค.ศ. + 543) % 100`) · แท็บ `ขายรถจบออนไลน์ <เดือน>69` **เคยฮาร์ดโค้ด "69"**
  → **1 ม.ค. 2570 ทั้งฝั่งจัดซื้อจะอ่านไม่ได้เลยทั้งไฟล์** แบบไม่มีอะไรฟ้อง
- **`_find_yod_tab(titles, m, look_back=6)`** — แท็บ `ยอดรถเข้า` ของเดือนที่ขอไม่มี =
  **ถอยไปเดือนก่อนหน้าได้ถึง 6 เดือน** แล้วติดธง `stale` · เดิมไม่เจอ = คืน `None`
  → **ตารางวางแผน "ต้องเติมรุ่นไหน" หายจากหน้าเว็บมา 2 เดือน** (แท็บมีถึง `กรกฎาคม69`) โดยไม่มีใครรู้
  · หน้าเว็บขึ้นป้ายเหลือง **"ข้อมูลเดือน กรกฎาคม (ยังไม่มีแท็บของเดือนนี้)"** — คืนข้อมูลแล้วต้องบอกด้วยว่าเป็นของเดือนไหน
  · **⚠️ ห้ามให้ทางถอยข้ามปี** — เวอร์ชันแรกเดือน ม.ค. ถอย 6 เดือนแล้วไป fuzzy เจอ `ยอดรถเข้า กรกฎาคม69`
    **ของปีที่แล้ว** · ตอนนี้ fuzzy ทำได้เฉพาะ `year_off == 0` และต้องมี `_be2()` ในชื่อแท็บ
  · **เทียบชื่อเดือนด้วย `name[:3]` ไม่ใช่ `[:4]`** — ในชีตมีแท็บสะกดเพี้ยน `ยอดรถเข้า กุมพาพันธู์69`
    (`กุมภ` ≠ `กุมพ`) · 3 ตัวแรกไม่ซ้ำกันทั้ง 12 เดือนอยู่แล้ว
  · **แท็บบางอันมีช่องว่างนำหน้าจริง** (`' จอง/จบ กันยายน 69'`) → เทียบแบบ strip แต่ **คืนชื่อดิบเสมอ**
    (เอาไปประกอบ range ต้องตรงเป๊ะ)

**★★★ 26 ก.ย.69 — เลิกเทียบชื่อรุ่น ให้ **จับด้วยทะเบียน** แทน (เจ้าของสั่ง)**
*"ข้อมูลส่วนนี้มันควรแมทกันเพราะเป็นข้อมูลชุดเดียวกัน ตัว Car Spend มันหยาบไปหน่อย
ถ้าคุณลองเทียบทะเบียนดู … ในช่องรถเข้าใหม่ มันจะมีรถเข้าใหม่ขึ้นมาเรื่อยๆ"*

เริ่มจากเจ้าของทักว่า **"ทำไมรถ Civic จะมีศูนย์คันได้ยังไง"** → ไล่ในฐานข้อมูลจริงแล้วเจอ 3 ชั้น:

**ชั้นที่ 1 — ชื่อรุ่นในสต๊อกเป็น "ป้ายหมวด" ไม่ใช่รุ่นจริง**
`Car.brand/model` มาจาก Car Spend ซึ่งเขียนหยาบและผิดด้วย (วัดจริง 26/09):
| ของจริง (ชีตบอก) | Car Spend เขียนว่า |
|---|---|
| Civic FE (ปี 2023) | `Civic FC ปี 16-20 FC ปี 16-20` (ข้อความซ้ำตัวเอง) |
| Corolla Cross | `Corolla Altis ALTIS ปี 14-18` |
| Almera Turbo | `Almera ปี 11-16` |
| Kicks | `Leaf ปี 12-16` |
· **ไม่มีคำว่า FE/FK เลยสักคัน** ทั้งที่ฝั่งลูกค้าถามหาแยก 4 ชื่อ (FC 1,248 · FE 780 · Civic 698 · FK 256)
· **101 จาก 163 คัน ที่จับคู่ได้ ชื่อ 2 ฝั่งไม่ตรงกัน** = เทียบด้วยชื่อไม่มีทางถูก

**ชั้นที่ 2 — ทะเบียนเป็นกุญแจที่ใช้ได้ แต่ต้องตัดชื่อจังหวัดก่อน**
ชีตกรอกเป็น `5ขล739 กรุงเทพมหานคร` · `4ขย4388กท` · `1 ขด116 กรุงเทพมหานคร` · `งร1535ชลบุรี`
(จังหวัดมีทั้งเต็ม/ย่อ/ติดกัน · บางคันเว้นวรรคกลางทะเบียนเอง) ส่วนสต๊อกเป็น `8กษ1332` เปล่าๆ
→ **`norm_plate()` ดึงเฉพาะ "เลข+อักษร+เลข"** · **ไม่ตัดจังหวัด จับคู่ได้ 5/466 · ตัดแล้วได้ 163/466**
· `_plate_models()` = `{ทะเบียน: ชื่อรุ่นจาก AV}` → `_stock_by_model` ใช้ชื่อจากชีตก่อน
  แล้วค่อยตกไปใช้ชื่อ Car Spend
· **⚠️ ห้ามเดารุ่นจากปีรถ** (เคยคิดจะทำ) — `2ขล9894` ปี **2021** ชีตบอก **Civic FE**
  (เจน 11 เปิดตัวกลางปี 2021) → กฎ "FE = 2022+" จับผิดทันที

**ชั้นที่ 3 — "ยาวก่อน" ทำให้รถไปลงคีย์ที่ไม่มีใครถามหา แล้วคีย์หลักเหลือ 0**
ชีตลีดมีทั้ง **"Altis" (ถาม 101)** และ **"Corolla Altis" (ถาม 1)** = คนละคีย์ ·
รถชื่อ `Corolla Altis ALTIS ปี 14-18` → กติกา "เทียบรุ่นยาวก่อน" เลือก `corollaaltis` ชนะ `altis`
→ ไปลงคีย์ที่ดีมานด์ = 1 ซึ่งต่ำกว่า `MIN_DEMAND` **→ หายจากตาราง และ Altis เหลือ "พร้อมขาย 0"**
· **`_fold_rare()`** ยุบคีย์ยาวที่ดีมานด์ **ต่ำกว่าเกณฑ์** เข้าคีย์หลักที่เป็น substring ·
  กติกา "ยาวก่อน" ยังอยู่ (`civicfc` ต้องชนะ `civic`) · `almeraturbo` (33) **ไม่ถูกยุบ** = ถูกต้อง
  เพราะเป็นรุ่นต่างจาก Almera จริงๆ

**ผลจริงหลังแก้ (สต๊อกพร้อมขาย 90 คัน · รู้รุ่นจากชีต 61 คัน)**
| รุ่น | พร้อมขาย เดิม | ใหม่ |
|---|---|---|
| **จับรุ่นไม่ได้เลย** | **27 คัน** | **6 คัน** |
| Corolla Cross | 0 | **7** |
| City 5 ประตู | 0 | **6** |
| Almera Turbo | 0 | **5** |
| New Yaris 5 ประตู | 0 | **4** |
| City 4 ประตู · Yaris Ativ | 0 | **3** |
| Altis | 7 (ผิด) | **3** |
| Civic FC | 4 | **5** |
· **Corolla Cross กับ Yaris Ativ เคยขึ้นเป็น "ขาดหนักสุด" ทั้งที่มีของพร้อมขาย 7 และ 3 คัน**

**★ "0 คัน" ต้องมีคำกำกับเสมอ — `_not_ready()`**
`Civic FE พร้อมขาย 0` **ถูกแล้ว** (รถ FE ที่มี 4 คัน ติดรอปิดการขาย 2 · จัดไฟแนนซ์ 1 · ซ่อม 1)
แต่ถ้าไม่เขียนว่า **"(มีอีก 4 คัน ยังไม่พร้อมขาย)"** คนอ่านสรุปว่าระบบพัง — ซึ่งเกิดขึ้นจริง
· ท้ายตารางบอกด้วยว่า "พร้อมขายอีก N คันเป็นรุ่นที่ตลาดไม่ได้ถามหา" (`STOCK_INFO["uncounted"]`)
  · **ห้ามใช้ `unnamed` (29) มาเขียนแทน** — พวกนั้นยังนับได้จากชื่อ Car Spend

**⚠️ 12 คันที่ 2 ฝั่งบอกรุ่น "คนละคัน" — ต้องให้คนตรวจ ไม่ใช่บั๊กโค้ด**
`งฉ7537` ชีต=City 5 ประตู / สต๊อก=Civic ปี2024 · `5ขฉ8584` ชีต=HRV / สต๊อก=Civic FC ·
`3ขญ4178` ชีต=Veloz / สต๊อก=VIOS · `4ขอ3060` ชีต=Kicks / สต๊อก=Leaf
· ตอนนี้ **ชีตชนะ** (แม่นกว่าเพราะคนกรอกตอนรับรถเข้า) แต่ควรไล่แก้ที่ต้นทาง

**⚠️ สต๊อกมีแค่ 209 คัน = รถที่ยังไม่ขาย** (`sync_carspend --status sold` ไม่เคยรัน)
→ รถเข้าใหม่ 466 คันทั้งปี จับคู่ได้ 163 · ที่เหลือขายไปแล้ว ไม่อยู่ในตาราง `Car`
· **ส.ค.+ก.ย. จับได้แค่ 14 จาก 99** เพราะรถที่เพิ่งรับซื้อยังไม่ถูกบันทึกเข้า Car Spend
  → ตัวเลข "เพิ่งรับเข้า" (`recent_bought` อ่านจากชีตตรง) จึงยังจำเป็น

**เทสต์**: `python scripts/test_purchase_plate.py` — ครอบ `norm_plate` (6 รูปแบบทะเบียนจริง) ·
`_fold_rare` · `_not_ready` · `_plate_models` (แถวแคชรุ่นเก่าที่ยังไม่มีช่องทะเบียนต้องข้าม ไม่พัง)

**วัดจริง 25/09** (7 วัน): ค้าง 109 เคส · **ยังไม่ได้โทร 19** (พี่หมี 14 · พี่ต๊าด 5)
· รถขาดหนักสุด: Altis (ถาม 101 · มี 0) · Yaris Cross (79 · 0) · Corolla Cross (79 · 0)
· Yaris Ativ ถาม 207 แต่ **เพิ่งรับเข้า 2 คัน** → ตกจากอันดับ 1 ไปอันดับ 4 (ถูกต้องแล้ว)

**⚠️★ 28 ก.ย.69 — ลีดรับซื้อถูกตัดทิ้งเงียบๆ 28% (เจ้าของถาม *"หลีดรับซื้อรถไม่มีหรอ"*)**
`_fetch_purchase_data()` อ่านชีตด้วยช่วง **`A3:AV400` ตายตัว = เพดาน 398 แถว/เดือน**
· **ลายเซ็นที่ควรสังเกตให้ออก: ทุกเดือนได้ 398 เท่ากันเป๊ะ** — เลขเท่ากันทุกเดือนคือธรรมชาติของ
"ชนเพดาน" ไม่ใช่ของข้อมูลจริง
- วัดจริง (ก่อน → หลังแก้): **3,486 → 4,825 ลีด · หายไป 1,339 (28%)**
  · เม.ย. 398→**797** (หายครึ่งหนึ่ง) · พ.ค. →680 · มี.ค. →675 · มิ.ย. →587 · ก.ย. →445
  · `boughtCars` ไม่กระทบ (466 เท่าเดิม — บล็อก AS:AV อยู่แถวต้นๆ)
- **แก้: `_PURCHASE_MAX_ROW = 3000`** · **เผื่อเยอะได้ ไม่เปลือง** เพราะ Sheets **ตัดแถวว่างท้ายให้เอง**
  (ขอ 3000 แต่ได้กลับ ~445 สำหรับ ก.ย.) — ของเดิมตั้ง 400 ไว้เหมือนจะประหยัด แต่ไม่ได้ประหยัดอะไรเลย
- **+ กันเงียบรอบหน้า**: ชนเพดานอีกเมื่อไหร่ จด `truncated` ลง KV **`purchase_fetch_last`**
  (`{at, leads, bought, truncated:[{tab,rows,cap}]}`) → มีที่ให้คนเห็น ไม่ใช่หายไปเฉยๆ
- **กฎ: ช่วงอ่านชีตที่เขียนแถวสุดท้ายตายตัว = ระเบิดเวลา** — วันที่ข้อมูลโตเกิน มันจะตัดทิ้งโดยไม่มีอะไรฟ้อง
  · เจอมาแล้วทั้งชีตลีด (`_fetch_tab` ยิงพลาดแล้วเงียบ) และรอบนี้ · **ตั้งเพดานให้สูงเกินจริงหลายเท่า + จดเมื่อชน**

**⚠️ การ์ด "ฝั่งจัดซื้อ (รับซื้อรถ)" + "รถซื้อเข้า รายคน" อยู่ใน แท็บ LEAD ไม่ใช่แท็บ "จัดซื้อ"**
(`renderLeadTab` · [index.html](dashboard/templates/dashboard/index.html)) · แท็บ **"จัดซื้อ"** มีแต่
**ยอดรถเข้า รายรุ่น** (`renderPurchaseTab` → `yodrot-card`) → **ชื่อแท็บกับที่อยู่การ์ดไม่ตรงกัน คนหาไม่เจอ**
· เจ้าของถามเรื่องนี้แล้ว 28 ก.ย. — ถ้าจะย้ายต้องย้าย `_CARD_TAB` ใน [report_shot.py](dashboard/services/report_shot.py) ด้วย
(ไม่งั้น Playwright สลับแท็บผิดแล้วแคปการ์ดไม่เจอ)

**ยังไม่ได้ทำ**: ผูก cron (ตอนนี้สั่งมือ) · **`sync_carspend` ยังไม่ได้ตั้ง cron** (สต๊อกค้างวันที่ 22/09) ·
หน้าเว็บดูลีดรับซื้อ · เก็บเคสลง Postgres (เจ้าของสั่งให้อยู่ในชีต) ·
"รถที่เราอยากได้" แบบกำหนดเอง (ตอนนี้คิดจากดีมานด์ล้วน — ตาราง `ยอดรถเข้า` มีเลข "ต้องเติม" ของทีมเองอยู่ ยังไม่ได้เอามารวม)

### 🛒 หน้าส่วนตัวของทีมจัดซื้อ `/buy/` — "จัดซื้อ force" · [purchase_page.py](dashboard/services/purchase_page.py) · 30 ก.ย.69
*"ช่วยทำ จัดซื้อ force ให้หน่อยคล้ายๆเซลล์"* — เซลล์มีหน้าที่บอกว่า "วันนี้ตามใครก่อน"
ทีมจัดซื้อยังไม่มี ต้องรอข้อความเข้า LINE อย่างเดียว · เจ้าของเคาะเนื้อหา **2 อย่าง**
(งานที่ต้องทำวันนี้ · รถที่ขาดตลาด) และสิทธิ์ **"เห็นเฉพาะของตัวเอง เหมือนเซลล์"**

- **`/buy/`** (`buy_dashboard` · [views.py](dashboard/views.py) · template [purchase.html](dashboard/templates/dashboard/purchase.html))
  · ไม่ login → `/login/?next=/buy/` · **ไม่ใช่ทีมจัดซื้อ → เด้งไป `/me/`** (ไม่โชว์หน้าว่าง)
  · แอดมิน/ผู้บริหารดูของคนอื่นได้ด้วย `?owner=`
- **★ ตอน login ตำแหน่ง "จัดซื้อ" ไป `/buy/` ไม่ใช่ `/me/`** (`_login_with_line_user_id`) —
  `/me/` เป็นหน้าเซลล์ซึ่ง**ไม่มีข้อมูลของคนจัดซื้อเลยสักอย่าง**
- **★★ ไม่เขียนตรรกะใหม่เลย** — เรียก `purchase_followup.fetch_open_cases()` ·
  `purchase_report.rank_cases()` · `purchase_report.market_gap()` ที่ส่ง LINE อยู่ทุกวัน
  → **ตัวเลขบนหน้าเว็บกับในข้อความ LINE เป็นชุดเดียวกันเสมอ** · แยกสูตรเมื่อไหร่
  จะมีเลข 2 ชุดที่ไม่ตรงกันแล้วไม่มีใครรู้ว่าอันไหนถูก (บทเรียนเดิมจาก `coach_db`)
- **`OWNER_ALIAS`** — ทะเบียนพนักงานเขียน **"ต๊าด"** แต่ชีตจัดซื้อเขียน **"พี่ต๊าด"**
  · **เขียนมือ 3 คน ห้าม substring** (บทเรียนเดิม: `Mod🐜` ไปจับ `เอ็ม`)
  · มีเทสต์ยืนยันว่า `"มิวสิค"` ต้องไม่ถูกนับเป็น `"มิว"`
- **ลำดับในหน้าเว็บ = ลำดับจากเซิร์ฟเวอร์ (`rank_cases`) ห้ามเรียงใหม่ฝั่ง JS** —
  ยังไม่ได้โทรมาก่อนเสมอ → รุ่นที่ขาดตลาด → ค้างนาน
- **★ "พร้อมขาย 0" ต้องมีคำกำกับ** (`notReady()` = ฝั่ง JS ของ `purchase_report._not_ready`) ·
  ท้ายการ์ดเขียน **"พร้อมขายอีก N คันเป็นรุ่นที่ตลาดไม่ได้ถามหา ไม่ได้นับในตารางนี้"**
  (`STOCK_INFO["uncounted"]`) — ไม่เขียน คนอ่านบวกเลขในตารางแล้วไม่ตรงสต๊อกจริง
  · **`STOCK_INFO` ถูกเติมเป็นผลพลอยได้ของ `market_gap()`** → ต้องอ่าน **หลัง** เรียกเสมอ
- **โชว์ 10 เคสแรก แล้วมีปุ่ม "ดูอีก N เคส"** — คนเดียวมีเคสค้างเป็นร้อย (วัดจริง ก.ย.69:
  พี่หมี 131 · พี่ต๊าด 96) กางรวดเดียวหาของไม่เจอ
- **อ่านชีตไม่ได้ = หน้าไม่พัง** — เคสล่มยังได้ตารางรุ่นขาดตลาด · ตารางรุ่นล่มยังได้เคส
- **⚠️ ตัวปิดงานยังเป็นช่องเดิมในชีต** — กรอก "รับซื้อ / ไม่รับซื้อ" (คอลัมน์ K) แล้วเคสหลุดเอง
  · **หน้านี้อ่านอย่างเดียว ไม่มีปุ่มแก้ชีต** (ตั้งใจ — ทีมกรอกในชีตอยู่แล้วทุกวัน)
- **เทสต์**: `python scripts/test_purchase_page.py` (38 ข้อ — จับคู่ชื่อ · เห็นเฉพาะของตัวเอง ·
  ลำดับ · ชีตล่ม · เซลล์เปิดแล้วต้องเด้ง) · **ตรวจ UI ด้วย Chromium จริง** (วัดจำนวนแถว/ปุ่ม/
  ป้าย/ล้นจอ ที่ 1280 และ 390px)
  - **⚠️ 2 กับดักของเทสต์** (นอกจาก `secure=True` + ยัดคุกกี้ session เองตามบทเรียนเดิม):
    ต้องเติม **`testserver` ใน `ALLOWED_HOSTS`** ไม่งั้นได้ **400 เปล่าๆ** ·
    และใน Chromium **`.card:nth-of-type(1)` นับตามชนิด element (div) ไม่ใช่ตามคลาส**
    → ไปโดน `.kpi` แล้วนับได้ 0 แถว (เกือบสรุปว่าโค้ดพัง ทั้งที่ harness ผิด)
  - **⚠️ `.env` ตั้ง `PLAYWRIGHT_BROWSERS_PATH` เป็น path ของเซิร์ฟเวอร์** → ต้องถอดตัวแปรนี้
    **หลัง `django.setup()`** (ถอดก่อน setup จะโหลด .env ทับกลับมา)

**★★ 30 ก.ย.69 (รอบ 2) — 2 เรื่องที่เจ้าของเจอทันทีที่ deploy**

**1. แอดมินระบบเปิด `/buy/` แล้วขึ้น "ยังไม่ได้ผูกชื่อเล่นในทะเบียนพนักงาน"**
(*"ทำไม superuser เข้าดูไม่ได้ เล่นตลกป้ะนิ"*)
- **ต้นเหตุ**: แอดมิน break-glass มี `nickname` ว่าง (session เป็น `user_id="admin"`) →
  โค้ดเอาชื่อเล่นไปหาเคส ไม่เจอ = ตอบ **404 หน้าแดง** ทั้งที่เขามีสิทธิ์เต็ม
- **แก้**: แอดมิน/ผู้บริหารที่ไม่ได้ระบุ `?owner=` → **`purchase_page.ALL` = รวมทุกคน** +
  **ปุ่มสลับคนดู** (`owners()` นับเคสต่อคน · เรียงคนค้างเยอะก่อน)
- **กฎ: บัญชีที่สิทธิ์สูงสุด ห้ามเจอทางตันเพราะข้อมูลโปรไฟล์ไม่ครบ** — ให้ค่าตั้งต้นที่กว้างที่สุด
  ที่สิทธิ์เขาอนุญาต ดีกว่าปิดประตูแล้วให้ไปตามแก้ทะเบียนก่อน

**2. ★★ ย้ายขึ้น "หัวแท็บ จัดซื้อ" ด้วย** (*"ทำไมไม่รวมกับอันนี้ หรือแทนอันนี้ไปเลย"*)
- แอดมินอยู่ในแดชบอร์ดอยู่แล้ว **ไม่มีเหตุให้ต้องรู้จัก URL `/buy/`** → การ์ด
  **"งานจัดซื้อวันนี้"** ขึ้น **บนสุดของแท็บ "จัดซื้อ"** (เหนือตาราง `ยอดรถเข้า รายรุ่น`)
  · `renderPurchaseTab` วาง `#pw-slot` แล้วเรียก `loadPurchaseWork()`
- **★ วางบนสุด ไม่ใช่ต่อท้าย** — บทเรียนเดิม (26 ก.ย. หน้าโซเชียล): ตารางที่เจ้าของขอ
  ถูกวางใต้กราฟสูง 290px → เจ้าของบอก *"ยังไม่เห็นมีการแยกนะ"* ทั้งที่ทำไปแล้ว 2 วัน
  · **ของที่ต้องลงมือ ต้องเห็นโดยไม่ต้องเลื่อน**
- **★★ `/api/purchase/work` = แหล่งเดียวของทั้ง 2 หน้า** (`api_purchase_work`) →
  เลขบนแท็บ · บนหน้า `/buy/` · ในข้อความ LINE ทุกเช้า **เป็นชุดเดียวกันเสมอ**
  (มีเทสต์เทียบ API กับ `summary()` ว่าตรงกัน)
  · แอดมิน: `?owner=` เลือกคน · ไม่ใส่ = รวมทุกคน · **ทีมจัดซื้อส่ง `owner` มาก็ไม่มีผล
    ได้ของตัวเองเสมอ** (กติกา "เห็นเฉพาะของตัวเอง" อยู่ที่เซิร์ฟเวอร์ ไม่ใช่แค่ซ่อนปุ่ม)
  · เซลล์เรียก = **403** · ไม่ login = **401**
- **⚠️ HTML วาดคนละที่ (index.html กับ purchase.html) แต่ข้อมูลชุดเดียว** — ตัวเลขไม่มีทางเพี้ยน
  ต่างกันได้แค่หน้าตา · แก้สูตรนับ = แก้ที่ `purchase_page.summary()` ที่เดียวเสมอ
- **เทสต์**: `scripts/test_purchase_page.py` **49 ข้อ** (+แอดมินไม่มีชื่อเล่น · API สิทธิ์ 3 ระดับ ·
  API ตรงกับ summary) · **ตรวจการ์ดในแท็บด้วย Chromium จริง** — **ดึงโค้ด `pwCard` ออกจาก
  index.html มารัน** (ไม่เขียน HTML จำลอง) + stub แค่ `fetch` แล้ววัดว่า **กดสลับคนแล้วยิงคำขอใหม่จริง**

**ยังไม่ได้ทำ**: ปุ่มกดจากหน้าเว็บให้กลายเป็น "โทรแล้ว" (ตอนนี้ดูจากคอมเมนท์ในชีต) ·
รวมยอดรับซื้อรายคน/รายเดือนในหน้านี้ · ลิงก์เข้าหน้านี้จากข้อความ LINE ที่ส่งทุกเช้า

### 🔁 เคสรับซื้อ/เทิร์นรถ → ชีต — **ย้ายจาก n8n มาอยู่ในเว็บเราแล้ว** [checkout/tradein.py](checkout/tradein.py) · 8 ต.ค.69
*"ย้ายระบบ N8N มาไว้ที่เว็บเรา … เราแค่กรอกลง Sheet ก็พอ แทน N8N คัดลอกฟังก์ชันมาทุกอย่าง แต่เราทำแทนเอง"*
(เจ้าของสั่ง หลังพบว่า n8n หยุดเขียนเงียบๆ ตั้งแต่ 5 ต.ค.69 · 3 วันไม่มีใครรู้)
- **ที่มาข้อมูล = `GroupChat`** (เว็บเก็บทุกข้อความของห้องเคสHOT/VERY HOT อยู่แล้ว · ต้องเปิด `store_chat`) ·
  **ทำทันทีที่ข้อความเข้า** (`_checkout_ingest` → `maybe_process` หลัง `store_chat`) + **cron ทุกนาทีเก็บตก**
  (`process_pending` ใน thread) · ล็อก Postgres advisory กันสองทางทำซ้อน
- **ตัวชี้ = `GroupChat.id` ล่าสุดที่จัดการแล้ว** (KV `tradein_state`) · **เขียนชีตล้ม = ไม่ขยับตัวชี้** รอบหน้าลองใหม่ ·
  อ่านใบพัง = ข้ามข้อความนั้น (ไม่ให้ข้อความเดียวขวางคิว) · จุดเริ่มครั้งแรก `INITIAL_SINCE` = 8 ต.ค.69 12:34
  (ก่อนหน้านั้นเติม TestBot ด้วยมือแล้ว)
- **ตัวอ่าน = แปลตรงตัวจาก n8n** (Resolve Roles V11 + Build Sheet Row v22.1) · **เทียบกับโค้ด JS ตัวจริง
  บนข้อความจริงทั้งหมด 487 ข้อความ (ใบเคส 355 · คอมเมนต์ 78) ตรงกันทุกช่อง A–S**
  · ⚠️ แปล regex JS→Python: `\b` ของ JS ไม่นับอักษรไทย (ใช้ `_NW`/`_NWE`) · `\d` Python รับเลขไทย (ใช้ `[0-9]`) ·
    `$` Python ยอม \n ท้าย (ใช้ `\Z`) · lookbehind ความยาวต่างกันต้องแตกเป็น `(?<=a)|(?<=bb)`
- **ต่างจาก n8n โดยตั้งใจ**: โพสต์ใบรหัสเดิมซ้ำ = ไม่เพิ่มแถว · ใบไม่มีรหัส = ไม่เพิ่ม · คอมเมนต์โอนเคส
  (`ดูแทน|เปลี่ยนเป็นของ|โอนให้` + @tag) = เปลี่ยนช่อง M ด้วย · วันที่/แท็บ = เวลาข้อความเข้า (ไม่ใช่เวลาประมวลผล)
- **ปลายทาง** KV `tradein_config.target`: **`test` (ค่าเริ่มต้น) = แท็บ TestBot** (เหมือน n8n เดิม · ข้อมูลเริ่มแถว 1) ·
  `month` = แท็บ `ขายรถจบออนไลน์ <เดือน><ปี>` (เริ่มแถว 3 · คอมเมนต์ค้นเดือนนี้แล้วเดือนก่อน)
  · **ห้ามสลับเป็น `month` จนกว่าทีมจะเลิกพิมพ์เคสเอง** ไม่งั้นซ้ำ 2 แถว (ดูข้อเท็จจริงข้างล่าง)
- **⚠️★ ห้ามใช้ `values:append` (บั๊กจริงบน prod 8 ต.ค.69 · เจ้าของเห็นในชีต)** — Google **เดาเอง**ว่า "ตาราง"
  เริ่มคอลัมน์ไหน: แถวก่อนหน้า (SC-1301) มี R กับ T ว่าง → คอลัมน์ S โดดเดี่ยว → มันถือว่าตารางเริ่มที่ S
  → **9 เคสแรกหลัง deploy (OC-7634..7642) ลงคอลัมน์ S–AK แทน A–S** (เลื่อนขวา 18 ช่องทั้งแถว)
  · เทสต์เดิมผ่านเพราะ (1) ชีตปลอมทำ append แบบ "ถูกเสมอ" (2) ทดสอบกับแท็บว่าง ซึ่งไม่มีอะไรให้เดา
  · **ตอนนี้ `Sheet.append` อ่าน A–S สดก่อนเขียนทุกครั้ง → หาแถวสุดท้ายที่มีค่าเอง (รวม B) → PUT `A{n}:S{n}` ตรง**
    แล้วเช็ค `updatedRange` ว่าลง `A{n}` จริง · ชีตปลอมในเทสต์จำลอง append แบบ Google จริง (ย้อนโค้ดเดิมแล้วเทสต์ล้ม 6 ข้อ)
  · **ซ่อม**: `manage.py tradein --repair` (ดู) / `--repair --apply` (ล้างแถวที่ A–R ว่างแต่มีรหัสที่ U แล้วย้อนตัวชี้ไป
    `INITIAL_SINCE` เขียนใหม่จากแชทเดิม — ไม่ย้ายค่าในชีต เพราะย้ายแล้วเบอร์เสียเลข 0/วันที่กลายเป็นตัวเลข) ·
    มีแถวถูกอยู่ใต้แถวผิด = ไม่ซ่อมเอง (กันช่องว่างกลางตาราง) · **ชุดโหนด n8n v2 ก็ใช้ append — ถ้าจะเอากลับมาต้องแก้ก่อน**
- `manage.py tradein` (สถานะ) · `--preview` (ดูว่าจะเขียนอะไร ไม่เขียน) · `--run` · `--target test|month` ·
  `--on/--off` · `--since "YYYY-MM-DD HH:MM"` · ผลรอบล่าสุด KV `tradein_last` · ล้มจดที่ `dash_event_log`
  · **หน้าสถานะระบบร้อง**: เขียนล้ม (err) · ข้อความค้างเกิน 10 นาที (warn)
- **เทสต์**: `python scripts/test_tradein.py` (57 ข้อ · มีเทียบกับโค้ด n8n ด้วย node 8 ข้อ · ปลอมที่ `requests`)
- **workflow ใน n8n ต้องปิด (Deactivate)** — ถ้ามันกลับมาทำงาน จะเขียน TestBot ซ้ำกับเรา (n8n ไม่กันซ้ำ)

### 🧾 ห้องจ่ายเบอร์ → "ชีทจ่ายเบอร์ ปี69" + "รายงานแบน" — **ย้ายจาก n8n** [checkout/leadsheet.py](checkout/leadsheet.py) · 13 ต.ค.69
เจ้าของถาม *"ทำไมมันกรอกชีทมั่ว อยากให้เอา n8n อันนี้ลง saleforce"* แล้วเคาะ *"จ่ายจาก SaleForce ก็ลง sheet ใน SaleForce เลย
ไม่ต้องทำระบบซ้ำ · จ่ายใน LINE ก็ลงเหมือนกัน · แบ่งสองฝั่ง แต่ผลลัพธ์ต้องได้แค่หนึ่ง"* + *"ซ่อมด้วย"*
- **★ ต้นเหตุ "วันที่ 13 โผล่กลางวันที่ 12" (ตอบเจ้าของแล้ว)**: โหนด n8n **"Update Report Status1"** map `ว/ด/ป = reportDate`
  → **ทุกครั้งที่เซลล์รายงานผล ("9075 รอตอบ") คอลัมน์ A ถูกเขียนทับเป็นวันที่รายงาน** · ลายเซ็น: ว/ด/ป = วันของ "อัพเดทล่าสุด"
  · วัดจริง 13 ต.ค.69 แท็บ ต.ค.: **112 แถว** มี "วันที่ติดต่อ" ก่อน ว/ด/ป (เป็นไปไม่ได้) · ในช่วงแถววันที่ 12 มีแถว A=13/10 อยู่ 64 แถว
    ทุกแถวมีอัพเดทล่าสุด = 13/10 · **ผลเสีย**: เคสค้างที่ก๊อปจาก ก.ย. ถูกนับเป็นลีด ต.ค. ซ้ำ + ลีดรายวันของแดชบอร์ดเพี้ยน
  · หยุดเดี๋ยวนี้ได้ใน n8n: เปิดโหนด Update Report Status1 → ลบช่อง ว/ด/ป ออกจาก mapping
- **ทางเดียวสำหรับทั้ง 2 ฝั่ง = คลังแชทกลุ่ม (`GroupChat`) ของห้องจ่ายเบอร์** (`connect._lead_group_ids()`):
  ใบที่แอดมินโพสต์ใน LINE = แถวขาเข้า · ใบที่ระบบส่ง (ปุ่มจ่ายเบอร์/ห้องพัก/จ่ายใหม่/ไม้ 2) = แถวขาออกที่ `slippost._store`
  เก็บไว้ (`extra.source="connect"` — LINE ไม่ส่งข้อความของบอทเองกลับมา) → ตัวชี้ `GroupChat.id` ตัวเดียว (KV `leadsheet_state`)
  · **Code เดิมมีแถวแล้ว (แท็บเดือนนี้/เดือนก่อน/เดือนตามเลข) = ไม่เพิ่มแถว** · เซลล์ต่าง = เปลี่ยนช่องเซลล์ (จ่ายใหม่) ·
    ช่องที่ยังว่างเติมให้ ไม่ทับที่คนแก้ · เลขเดิมแต่เบอร์/ไลน์คนละคน = เพิ่มแถวใหม่ + จด `conflicts`
- **งาน 3 อย่าง (ครบตาม workflow n8n "LINE → Sheet")**:
  1. **ใบจ่ายลีด** → เพิ่มแถว: ว/ด/ป+เวลา = **เวลาที่ใบถึงกลุ่ม** · เบอร์ (ไม่มี = `ID LINE : …` / `ID LINE : QR code`) · Code ·
     เซลล์ (**แท็กจริงของ LINE** → งานจ่ายเบอร์ของระบบ → `@ข้อความ` ผ่าน `_tag_match`) · ทีมไลฟ์ · Admin (คนโพสต์ / คนกดจ่าย) ·
     ช่องทาง (คำย่อจาก n8n + dropdown จริง · **ไม่มี fuzzy** ไม่ตรง = คำเดิม) · สาขา · type (ตัวหน้าเลข: R+HLD=Hot RJ ·
     R=RJ · RB=Hot RB · HLD=Very Hot · WLD=Hot · TLD · BLD · LD=Moderate · ช่องทาง TikTokAds = TLD) · ADS · รถลูกค้าถาม ·
     CAR/สูตร (`connect.car_in` = ชุดเดียวกับ Connect) · PROFILE (ช่องเพิ่มเติม ตัดที่ "ติดต่อได้เลย") · ใบระบบใช้ type/รุ่น/Admin
     จาก `ChatLead`/`ExtLead` ถ้ามี
  2. **รายงานผล** `9075 รอตอบ` · `TLD10-9075 …` · `10-9075 …` · `9075/1 …` → จำนวนอัพเดท+1 · อัพเดทล่าสุด · ที่ติดต่อ (ถ้าว่าง) ·
     แจ้งหลักฐาน=ส่งแล้ว · **ไม่แตะ ว/ด/ป** · คนรายงานต้องอยู่ในทะเบียน + เป็นเจ้าของแถว (ช่องเซลล์ว่าง+แถวเดียว = รับ) ·
     แท็บเดือนนี้ก่อน (เคสค้างถูกก๊อปไปเดือนใหม่) ย้อนได้ 2 เดือน · มี `@` = แอดมินทวง ไม่ใช่รายงาน
  3. **แบน** (แท็กจริง + แบน/ปรับ/รีเจ) → ต่อท้าย "รายงานแบน" (Sheet Master · หัวคอลัมน์ banDate|time|seller|…) ·
     **"ขอปลดแบน" ไม่นับ** (n8n นับ → เคยมีแถวขยะ) · ปี พ.ศ. 2 หลักแปลงถูก (n8n ได้ 1969) · ไม่เขียน LINE id (n8n เขียนตอนหาชื่อไม่เจอ) ·
     ชีตแบนไม่มีสิทธิ์/หาแท็บไม่เจอ = ข้ามข้อความนั้น ไม่ขวางคิว · ปิดได้ `--ban off`
- **store_chat เก็บคนที่ถูกแท็กจริง** `GroupChat.extra["mention"]` (LINE user id · เฉพาะข้อความในกลุ่ม · ไม่เอา @All · `[]` = ไม่มีใครถูกแท็ก)
- **เขียนชีต**: `values:batchUpdate` เฉพาะเซลล์ที่ต้องเขียน (ไม่ใช้ `values:append` — บทเรียน tradein) · แถวใหม่ = ต่อจากแถวสุดท้ายที่
  คอลัมน์ A–E มีค่า · ตารางเต็ม = `appendDimension` เพิ่มแถวก่อน · วันที่เขียนเป็น d/m/ปี ค.ศ. 4 หลัก · เบอร์/เวลาใส่ `'` นำหน้า
  · **ไม่สร้างแท็บเดือนใหม่เอง** (แอดมินสร้าง) · เขียนล้ม = ไม่ขยับตัวชี้ (ลองใหม่ทุกนาที)
  · **★ ขึ้นเดือนใหม่ (13 ต.ค.69 เจ้าของสั่ง)**: ใบลงแท็บของเดือนที่ใบถึงกลุ่ม · **ยังไม่มีแท็บใหม่ (หรือมีแต่ยังไม่มีหัวตาราง)
    = ลงแท็บเดือนล่าสุดที่มีไปก่อน** (`Ctx.month_tab` · ย้อนได้ 3 เดือน) แล้วจดไว้ที่ KV `leadsheet_fallback`
    → แท็บใหม่มีหัวตารางเมื่อไหร่ `settle_fallback` (เช็คทุก 5 นาที แม้ไม่มีข้อความใหม่) **ย้ายทั้งแถวไปต่อท้ายแท็บใหม่**
    ด้วย `cutPaste` + `deleteDimension` ในคำขอเดียว (ค่า/รูปแบบไปครบ) · ไม่ย้ายถ้าเลขนั้นมีในแท็บใหม่แล้ว (แอดมินก๊อปเอง)
    หรือ ว/ด/ป ไม่ใช่เดือนใหม่ · **ต้องย้ายเพราะแดชบอร์ดกรองแถวตามเดือนของแท็บ** — แถว 1/11 ในแท็บตุลาคมไม่ถูกนับ
    · แท็บเปล่าไม่มีหัวตาราง = `Ctx.tab` คืน None (เดิมโยน SheetError ค้างทั้งคิว รวมรายงานผลเคสเดือนก่อน)
- **ทำงานเมื่อไหร่**: webhook (`_checkout_ingest` → `maybe_process`) · ระบบส่งใบสำเร็จ (`slippost._store` → `kick()` เธรดแยก) ·
  cron ทุกนาทีเก็บตก (เธรดเดียวกับ tradein) · advisory lock `7_406_064`
- **สวิตช์ KV `leadsheet_config.enabled` ปิดโดยปริยาย** — เปิดแล้วต้องปิด workflow n8n วันเดียวกัน (ไม่งั้นเขียน 2 ที่ · ใบซ้ำกันด้วย Code
  ได้ แต่รายงานผลจะ +1 ซ้ำ) · เปิดครั้งแรกเริ่มจากข้อความล่าสุด (ไม่ไล่ย้อน) · `--since` = เวลาที่ปิด n8n
- **คำสั่ง** `manage.py leadsheet` (สถานะ) · `--preview --last 80` (**อ่านอย่างเดียว** · ใบที่ n8n ลงแล้วขึ้น "มีแล้ว" + ช่องที่ต่างกัน
  ใช้เทียบก่อนเปิดจริง) · `--on [--since "YYYY-MM-DD HH:MM"]` · `--off` · `--ban on|off` · `--run` ·
  **`--repair-dates [--tab "ตุลาคม 69"] [--apply]`** = หาแถวที่ ว/ด/ป = วันอัพเดทล่าสุด แล้วคืนวันที่ใบถึงกลุ่มจริง (`slip_dates()` จาก
  คลังแชท 120 วัน + `LeadTask.posted_at`) · เขียนเฉพาะคอลัมน์ A · หาใบไม่เจอแต่วันที่ติดต่อมาก่อน ว/ด/ป = รายงานให้คนตรวจ ไม่แก้
  · **ต้องรันบนเซิร์ฟเวอร์** (คลังแชทอยู่ที่นั่น) และ **หลังลบ mapping ว/ด/ป ใน n8n** ไม่งั้นโดนทับอีก
- หน้าสถานะระบบร้อง: เขียนล้ม (err) · ค้างเกิน 10 นาที (warn) · รายงานที่คนรายงานไม่ใช่เจ้าของ (warn) · ลงแท็บเดิมรอย้าย (warn) · แจ้งเตือน LINE ส่งไม่ถึง (warn)
- **★ แจ้ง LINE ส่วนตัวเจ้าของ (13 ต.ค.69 เจ้าของสั่ง)** ผู้รับ = `ALERT_TO` ("Wattanakit"/"วัฒนกิจ" ในทะเบียนพนักงาน ·
  เปลี่ยนด้วย `--alert-to` · ปิด `--alert off` · ทดสอบ `--alert-test`) · ส่งด้วยบอทตัวส่ง (`dm_token` + `dm_route`)
  · **รวมเป็นข้อความเดียวต่อรอบ** · บันทึกชีตไม่ได้ = แจ้งซ้ำทุก 1 ชม. (ไม่ใช่ทุกนาทีที่ cron ลองใหม่) + แจ้ง "กลับมาบันทึกได้แล้ว"
  · ข้อความที่ลงชีตไม่ได้แจ้งครั้งเดียวต่อข้อความ: ไม่ใช่เจ้าของ · หาเลขไม่เจอ · **คนรายงานไม่อยู่ในทะเบียน (เดิมข้ามเงียบ
  → ตอนนี้ action `report-noemp`)** · อ่านข้อความพัง · บันทึกแบนไม่ได้ · ลงแล้วแต่หาเซลล์ไม่เจอ · เลขซ้ำคนละลูกค้า ·
  ลงแท็บเดิม (ซ้ำทุก 6 ชม.) · ย้ายไปแท็บใหม่แล้ว · กันซ้ำด้วย KV `leadsheet_alert` · ไม่มี LINE id ในข้อความ
  · preview/simulate ไม่แจ้ง (แจ้งเฉพาะ `process_pending`) · เทสต์ 103 ข้อ (ปลอม LINE push + cutPaste ที่ `requests`)
  · **★ หัวคอลัมน์ขยับ/เปลี่ยนชื่อ/ถูกลบ (14 ต.ค.69 เจ้าของ: "เคสที่เจอบ่อย")** — อ่านหัวตารางใหม่ทุกรอบ จับคู่ด้วยชื่ออยู่แล้ว
    (ขยับ = ตามได้เอง → แจ้ง "คอลัมน์ขยับ ปรับให้แล้ว") · **เดิมหัวคอลัมน์ถูกเปลี่ยนชื่อ = `cells()` ข้ามช่องนั้นเงียบๆ**
    → จำตำแหน่งที่ใช้ได้ล่าสุดต่อแท็บใน KV `leadsheet_cols` (`_heal_columns` · จำเฉพาะรอบเขียนจริง) → ชื่อไม่ตรงแต่
    ตำแหน่งเดิมมีหัวที่ไม่ใช่ของช่องอื่น **และคอลัมน์ข้างๆ ยังอยู่ที่เดิม** = เปลี่ยนชื่อในที่เดิม → ใช้คอลัมน์เดิมต่อ + แจ้ง ·
    คอลัมน์ข้างๆ เลื่อน (= มีคนลบ/แทรก) = **ไม่เดา** แจ้ง "หาหัวคอลัมน์ X ไม่เจอ ช่องนี้ไม่ได้บันทึก" ซ้ำทุก 1 ชม. ·
    หัว Code หายเดาไม่ได้ = แท็บนั้นใช้ไม่ได้ → ใบลงแท็บเดือนก่อน + แจ้ง (แก้หัวแล้วย้ายกลับเอง)
  · **ย้ายใบไปแท็บใหม่: หัวตารางตรงกัน = cutPaste ทั้งแถว · ไม่ตรง = เขียนค่าตามชื่อหัวคอลัมน์ (`_col_map`) แล้วลบแถวเดิม**
    (ตัดแปะทั้งแถวตอนแท็บใหม่จัดคอลัมน์ต่าง = ลงผิดช่อง · เทสต์จับได้) · แจ้งคอลัมน์ที่แท็บใหม่ไม่มี · เทสต์ 121 ข้อ
  · **`--test-month-move`** = ลองย้ายแถวข้ามแท็บกับ Google จริง (`move_selftest`: สร้างแท็บชั่วคราว 2 แท็บ · ย้ายด้วย
    `_move_rows` ตัวเดียวกับของจริง · ตรวจเบอร์/วันที่/เวลา · ลบแท็บทิ้งใน finally) — **cutPaste ข้ามแท็บยังไม่เคยลองกับ
    Google จริงจนกว่าจะรันคำสั่งนี้บน prod** · ลบหลายแท็บในคำขอเดียวให้เรียงรหัสมาก→น้อย (`_del_tabs` · ชุดปลอมใช้ลำดับเป็นรหัส)
- **★ 14 ต.ค.69 log ทุกเรื่อง + ตัวเฝ้าระบบ (เจ้าของสั่ง "ถ้ามี error หรือข้อผิดพลาดอะไร บันทึก log ไว้ และแจ้งเตือนฉันด้วย")**
  · **ทุกเรื่องที่ `alert()` แจ้ง = 1 แถวใน `dash_event_log` kind=`leadsheet`** (target = คีย์ · detail.text = ข้อความ) —
    **จดแม้ปิดแจ้งเตือน LINE** (`--alert off` ปิดแค่การส่ง) · ดูย้อนหลัง **`manage.py leadsheet --log [--days 7]`**
    (รวมเขียนชีตล้ม kind=cron · สำเนาชีตล้ม · ผลส่งแจ้งเตือน LINE) · `recent_log()` ไม่ส่ง LINE id ออก
  · **`alert(failing=None)` = ไม่แตะสถานะ "บันทึกไม่ได้"** (ตัวเฝ้าระบบ/สำเนาชีตเรียก) · `""` = ผลรอบนี้บันทึกได้ (แจ้งหายแล้ว)
  · **`safe_process(source)`** แทน `except: pass` 3 จุดที่เคยกลืนเงียบ: `kick()` (ระบบส่งใบ) · `maybe_process` (ข้อความ LINE เข้า) ·
    cron `_ti_job` — ล้มกะทันหัน (บั๊ก/DB ล่ม) = log + แจ้ง LINE ซ้ำทุก 1 ชม. ต่อข้อความ error เดียวกัน
  · **สำเนาชีตลง Postgres ล้ม → แจ้ง LINE ด้วย** (`sheet_mirror.run` · ซ้ำทุก 1 ชม.)
  · **ตัวเฝ้าระบบ** `watchdog_check()` + `start_watchdog()` — เธรดในเว็บเอง (**ไม่ขึ้นกับ n8n/cron**) เริ่มจาก `CheckoutConfig.ready()`
    **เฉพาะใต้ gunicorn** (`"gunicorn" in sys.argv[0]` · ไม่เริ่มตอน manage.py/runserver/เทสต์ · ปิด env `LEADSHEET_WATCHDOG=0`)
    · ตรวจทุก 5 นาที · worker เดียวทำงาน (advisory lock `7_406_066` ถือไว้บน connection ของเธรด) · เทียบ pid กันหลัง fork
    · ตรวจ 3 อย่าง: (1) `cron_tick` เก่าเกิน 10 นาที (2) ข้อความค้างเกิน 15 นาที → **ลงเองก่อน** แล้วแจ้ง "ลงให้แล้ว"/"ยังค้าง + เหตุผล"
      (กำลังบันทึกไม่ได้อยู่แล้ว = ข้าม — แจ้งไปทางนั้นแล้ว) (3) 10:00–19:00 ไม่มีข้อความขาเข้าจากห้องจ่ายเบอร์เกิน 90 นาที (n8n ส่งต่อ LINE อาจหยุด · ซ้ำทุก 3 ชม.)
      **นับจากข้อความล่าสุด หรือ 10:00 ของวันนั้น (อันที่หลังกว่า)** → แจ้งได้เร็วสุด 11:30 (เวอร์ชันแรกนับจากข้อความเมื่อคืน = แจ้งหลอกทุก 10:00)
    · รอบล่าสุดที่ KV `leadsheet_watchdog` {at, pid, issues} · `manage.py leadsheet --watchdog` = ตรวจเดี๋ยวนี้ (ข้อความค้าง = ลงให้จริง)
    · หน้าสถานะระบบร้องเมื่อตัวเฝ้าเจอปัญหา หรือ **ไม่ได้ตรวจเกิน 20 นาที** (= เธรดตาย/ไม่ได้เริ่ม → รีสตาร์ทเว็บ)
  · เทสต์ `test_leadsheet.py` [11] (151 ข้อรวม · พิสูจน์แล้วว่าย้อนพฤติกรรมเดิมแล้วล้ม) · ⚠️ ในเทสต์ `QuerySet.count()` ใช้ผลที่จำไว้ถ้าเคยวนแถวแล้ว
    → นับใหม่ด้วย `.all()` · SQLite ค้นใน JSON (`detail__text__contains`) ไม่ได้
- **★ 15 ต.ค.69 "ใหม่" โผล่ในช่องเซลล์ ทั้งที่ตั้งไว้เป็น ADMIN (เจ้าของแจ้ง) — ขั้นที่หลุดตอนย้ายจาก n8n**
  · n8n แปลง "คน" เป็น "ชื่อในชีต" ด้วยแท็บ **"รายชื่อสมาชิกกลุ่ม Lead"** (userId | displayName | Nickname) **ทุกขั้น**:
    เซลล์ของใบจ่ายลีด · เจ้าของตอนรายงานผล · คนโดนแบน/คนสั่งแบน · แท็บนี้ตั้ง `Mai🐶OxletAuto` (เทเลเซลล์ใหม่) = **ADMIN**
    (dropdown ช่องเซลล์ไม่มี "ใหม่" มีแต่ ADMIN) · ตอนย้ายมาผมใช้ชื่อเล่นในทะเบียนพนักงานแทน → ลงเป็น "ใหม่"
    (วัดจริง: แถวของใหม่ลงเป็น ADMIN ถึง 15/10 11:10 · 11:25 ขึ้น "ใหม่" 2 แถว NLD10-9365 / LD10-9366)
  · แก้: `load_members()` อ่านแท็บนั้น (จำ 10 นาที) → **`member_name()` ชนะทะเบียน** — เทียบ LINE id ก่อน →
    บัญชี LINE ของคนในทะเบียนชื่อเล่นนั้น (ใบที่ระบบส่งมีแต่ชื่อเล่น) → ชื่อที่ตั้งใน LINE ตรงตัว (ตัดอิโมจิ/ตัวพิมพ์ · ไม่ fuzzy ·
    ชื่อซ้ำแต่ Nickname ต่าง = ไม่ใช้) · ใช้กับ `_seller_of` · `handle_report` (เจ้าของได้ทั้งชื่อเล่น**และ**ชื่อในแท็บ —
    แถวเก่าที่ลงเป็น "ใหม่" ยังรายงานได้) · `_ban_targets` + คนสั่งแบน
  · **แท็บนี้อ่านไม่ได้และยังไม่เคยอ่านได้ = ไม่ลงชีต รอรอบหน้า** (ลงชื่อผิดแล้วต้องตามแก้ แย่กว่ารอ) · ไม่มีแท็บ = ใช้ทะเบียนตามเดิม
  · **อยากให้ใครลงชีตด้วยชื่ออื่น = แก้ช่อง Nickname ในแท็บนั้น** (ที่เดียวกับที่ n8n ใช้) · ระบบไม่เขียนแท็บนี้
    (n8n upsert userId/displayName ทุกข้อความ — ไม่ได้ย้ายมา คนที่ไม่เคยอยู่ในแท็บเทียบด้วยชื่อเล่นในทะเบียน)
  · **ADMIN ตัวใหญ่เสมอ** (เจ้าของสั่ง *"ใช้คำว่า ADMIN ตัวใหญ่หมด"*) — `_upper_admin()` แปลง Admin/admin ในแท็บเป็น ADMIN
  · **แก้แถวที่ลงไปแล้ว**: `manage.py leadsheet --fix-names [--tab "ตุลาคม 69"] [--apply]` (`fix_member_names`) — ช่องเซลล์
    ที่เป็นชื่อเล่นในทะเบียนตรงตัว แต่แท็บรายชื่อสมาชิกตั้งชื่อในชีตอีกแบบ → แก้ให้ตรง · เขียนเฉพาะช่องเซลล์ · ไม่ใส่ `--apply` = ดูเฉยๆ
    · **ต้องรันบนเซิร์ฟเวอร์** (ทะเบียนพนักงานอยู่ใน Postgres ของ prod) · ไม่มีแท็บ ไม่ใส่ = เดือนนี้+เดือนก่อน
  · เทสต์ `test_leadsheet.py` [12] (171 ข้อรวม · ย้อนโค้ดเดิมแล้วล้ม 7 ข้อ)
- **★ 15 ต.ค.69 เลขไม้ 2 ลงชีตโดยไม่มี "/1" → รายงานผล "8286/1 …" ขึ้นแจ้งเตือน "หาเลขไม่เจอ" (เจ้าของแจ้ง)**
  · ต้นเหตุ: `leadgroup._LEAD_NO` จับเลขถึงตัวเลขเท่านั้น → ใบ `Ac Lead No. RNLD10-8286/1` ลงชีตเป็น `RNLD10-8286`
    · n8n เขียนครบ /1 มาตลอด → **แถว R ที่ไม่มี /1 เริ่ม 14/10 วันที่ระบบนี้ลงชีตแทน (วัดจริง 72 แถว: 14/10 22 · 15/10 50)**
    · รายงานไม้ 2 ทุกข้อความที่มี /1 = `report-miss` (จำนวนอัพเดทของเคสไม้ 2 ไม่ขึ้นตั้งแต่ 14/10)
  · แก้: `parse_leadsheet` คืน **`lead_code_full`** + `lead_slash` เพิ่ม (**`lead_code` คงเลขฐานเดิม** — ห้องพัก/งานจ่ายเบอร์/
    สมุดเบอร์ใช้อยู่) · `slip_row` ใช้เลขเต็ม · `LeadTab.find_legacy()` = แถว R ที่ไม่มี /n ของเลขเดียวกัน →
    `handle_slip` เจอแล้ว **ซ่อมช่อง Code ให้เต็ม** (ไม่เพิ่มแถวซ้ำ) · `handle_report` รายงาน /n หาแถว R ไม่มี / ของเลขรันเดียวกันได้
  · **ซ่อมของที่ลงไปแล้ว**: `manage.py leadsheet --fix-slash [--tab …] [--apply]` (`fix_slash_codes`) — หาใบต้นฉบับในคลังแชท
    ห้องจ่ายเบอร์ (70 วัน) → แก้ Code เป็นเลขเต็ม · ไม่เจอใบ/มีแถวเลขเต็มอยู่แล้ว = ไม่แตะ (รายงาน) · แล้ว **ลงรายงานไม้ 2 ที่พลาด
    ตั้งแต่ 14/10 ให้ใหม่** ด้วยเวลาเดิมของข้อความ (ก่อนแก้หาแถวไม่เจอแน่นอน = ไม่นับซ้ำ · ไม่ใช่เจ้าของ = ไม่ลง)
    · **ต้องรันบนเซิร์ฟเวอร์** (คลังแชทอยู่ที่นั่น) · ไม่ใส่ `--apply` = ดูเฉยๆ
  · แจ้งเตือน "8268/1 — บิว รายงาน แต่ในชีตเป็นเคสของ เหล" ของวันเดียวกัน **ถูกต้อง** (แถว RBLD10-8268/1 = เหล ·
    ไม้ 2 ของบิวคือ 8286 — เลขสลับหลัก) · เทสต์ `test_leadsheet.py` [13] (185 ข้อรวม)
- **★ 15 ต.ค.69 เลขลีดซ้ำในชีต = ยึดแถวล่าสุด (เจ้าของสั่ง "โค้ดมันจะมีตัวซ้ำกัน ยึดตัวล่าสุด")**
  · รายงานผล: หาแถวของเลขนั้น (เลขเต็ม → เลขรัน · ระบุ /n มา = แถว /n ตรงก่อน) แล้ว **แถวล่างสุดของแท็บใหม่สุดที่เจอ = เจ้าของ**
    · เจ้าของแถวล่าสุด ≠ คนรายงาน = `not-owner` (เดิมเลือก "แถวของคนรายงาน" แม้เป็นแถวเก่า → เจ้าของเดิมที่เคสย้ายไปไม้ 2/
    จ่ายใหม่แล้ว ยังรายงานลงแถวเก่าได้) · แถวล่าสุดไม่มีชื่อเซลล์ = ลงได้ · เลิกกติกา "รายงานเลขเปล่า = แถวไม่มี / ก่อน"
  · ใบจ่ายลีด: เลขเต็ม + แถวเก่าไม่มี /n รวมกันแล้ว **เทียบกับแถวล่าสุด** · `--fix-slash`: ใบหลายเลข = ยึดใบล่าสุด ·
    มีแถวเลขเต็มอยู่แล้วก็ยังซ่อม (เลขซ้ำได้) พร้อมบอก · เทสต์ [14] (191 ข้อรวม)
- **ไม่ได้ย้าย (ตั้งใจ)**: n8n upsert แท็บ "รายชื่อสมาชิกกลุ่ม Lead" ทุกข้อความ — SaleForce **อ่าน**แท็บนี้ (ด้านบน) แต่ไม่เขียน ·
  ข้อความรับสมัครงาน (Parse Comment1 ไม่ต่อกับอะไรอยู่แล้ว) · ข้อความ "บันทึกการแบน" ตอบกลับเข้ากลุ่ม (Build Confirm ไม่ได้ต่อโหนดส่ง)
- **⚠️ workflow n8n มี LINE channel access token จริงฝังอยู่** (เจ้าของวางทั้งก้อนในแชท 13 ต.ค.69) → ควรออก token ใหม่
- **ทดสอบแบบไม่โพสต์จริง** `manage.py leadsheet --simulate --seller มัท --admin กวาง [--other เฟิร์ส]` (`simulate()`) —
  สร้างข้อความใบจ่ายลีดเหมือนแอดมินพิมพ์ (แท็กจริงชี้เซลล์) **ไม่ส่ง LINE · ไม่บันทึกลงคลังแชท** แล้วส่งผ่านโค้ดตัวจริงทุกขั้น:
  โพสต์ใบ → โพสต์ซ้ำ (ต้อง dup) → เจ้าของรายงาน → คนอื่นรายงาน (ต้อง not-owner) · ลงแท็บแยก **"ทดสอบลงชีต (ลบได้)"**
  (`Ctx(redirect=…)` ชี้ทุกแท็บเดือนไปแท็บนี้ — แท็บจริง/แดชบอร์ด/สำเนา Postgres ไม่เห็น) · อ่านแถวกลับมาแสดง + เช็ค ว/ด/ป ไม่ถูกทับ ·
  เลขรันจำลอง 6 หลักขึ้นต้น 9 (ไม่ชนเลขจริง) · ไม่จำลองแบน (จะเขียนชีตรายงานแบนจริง = กระทบคะแนนเซลล์) · `--simulate-cleanup` ลบแท็บ
  · ⚠️ แท็บใหม่ของ Google มี 26 คอลัมน์ (A–Z) หัวตารางจริงมี 29 → ต้องตั้ง `columnCount` ตอนสร้าง (เจอตอนลองกับชีตจริง)
  · **`--in-month-tab`** = ต่อท้ายแท็บเดือนจริง (เจ้าของขอ "อยากให้ทดสอบต่อท้ายแถวที่มีอยู่แล้ว") · ระหว่างที่แถวยังอยู่ แดชบอร์ดนับเป็นลีด
    → จดเลขไว้ใน KV `leadsheet_sim` · `--simulate-cleanup` ลบแถว (`deleteDimension` จากล่างขึ้นบน) **เฉพาะเลขที่จดไว้
    และช่อง ADS = "ทดสอบระบบลงชีต"** (อ่านสดก่อนลบ — แถวจริงเลขบังเอิญซ้ำไม่โดน) + ลบแท็บทดสอบ
- **★ เปลี่ยนช่องเซลล์ของแถวเดิมเฉพาะตอนรู้แน่ว่าเป็นใคร** (`SURE_SELLER` = แท็กจริง/งานจ่ายเบอร์ของระบบ/@ที่เจอในทะเบียน)
  — พรีวิวบน prod 13 ต.ค.69 เจอ NLD10-9275: ข้อความเก่าไม่มีข้อมูลแท็กจริง "@POOH" หาไม่เจอ เกือบทับ "ภู" ที่ถูกอยู่แล้ว
  · ผลพรีวิวจริง: รายงานผล 40+ รายการจับเจ้าของถูกทุกอัน · ใบที่ n8n ลงแล้วขึ้น "มีแล้ว" ทุกใบ · ซ่อมวันที่ได้ 123 แถว (หาวันจริงเจอทุกแถว)
- **เทสต์**: `python scripts/test_leadsheet.py` (77 ข้อ · ปลอมที่ `requests` + ใบรับรอง Google) · ทดสอบอ่านชีตจริงแล้ว
  (อ่านอย่างเดียว · ห้ามเขียน): แท็บ ต.ค. 1,692 แถว จับคู่คอลัมน์ครบ · พบ 112 แถวที่โดนทับ

### 🗄️ สำเนาชีตจ่ายเบอร์ + รายงานแบน ลง Postgres — [sheet_mirror.py](dashboard/services/sheet_mirror.py) · 13 ต.ค.69
เจ้าของสั่ง *"อย่าลืมเก็บลง postgres ด้วยนะ เก็บไว้เผื่อทำอย่างอื่นต่อ · มีแพลนอยากย้ายมา full ระบบเลย"*
- เดิมระบบ **อ่านชีตไปคำนวณแดชบอร์ดอย่างเดียว** (ผลสรุปอยู่ใน `dash_kv`) ไม่มีแถวลีดในฐานข้อมูลเลย → SQL ต่อยอดไม่ได้
- **`dash_lead_sheet_row`** (`LeadSheetRow` · dashboard migration **0016**) = ทุกแถวของทุกแท็บรายเดือน ("มกราคม 69" …)
  · ช่องหลักแตกเป็นคอลัมน์ (Code · ว/ด/ป · เบอร์/ID LINE · เซลล์ · ช่องทาง · type · CAR/สูตร · ติดต่อ · จำนวน/เวลาอัพเดท ·
  สถานะลูกค้า · อาชีพ/รายได้/อายุงาน/ประวัติผ่อน ฯลฯ) จับคู่ด้วย `_resolve_lead_colmap` ตัวเดียวกับแดชบอร์ด
  · **ทุกช่องดิบอยู่ใน `raw` {หัวคอลัมน์: ค่า}** (หัวซ้ำ = เติม " (2)") — คอลัมน์ที่ยังไม่แตกก็ไม่หาย = ฐานสำหรับย้ายออกจากชีต
  · **`dash_ban_sheet_row`** (`BanSheetRow`) = แท็บ "รายงานแบน" (Sheet Master)
- **ชีตยังเป็นต้นฉบับ** — ห้ามเขียนกลับ/แก้ที่ตาราง · ดึงทุก **10 นาที** (`cron_tick` → เธรดเดียวกับ tradein/leadsheet ·
  `due()` เช็คจาก KV `sheet_mirror_last` ร่วมทุก worker · advisory lock `7_406_065`) · อ่านทุกแท็บในคำขอเดียว (`values:batchGet` ~20 วิ)
  · **แทนที่ทั้งแท็บในธุรกรรมเดียว** → แถวที่ลบ/เลื่อน/แก้ในชีตตามมาครบ · แท็บที่หายจากชีต = ลบสำเนา · อ่านชีตล้ม = ของเดิมไม่แตะ
- **วันที่**: d/m/yy · d/m/yyyy · ปี พ.ศ. 2 หลัก · เลข serial · **"15/1" ไม่มีปี** (เซลล์วันที่ที่ตั้งรูปแบบโชว์แค่ วัน/เดือน —
  แท็บต้นปี) = เติมปีจากชื่อแท็บ (ก่อนเดือนแท็บเกิน 1 เดือน = ปีถัดไป) · ข้อความยาวเกินช่องตัดให้พอดี (Postgres ไม่ยอม)
- `manage.py sheet_mirror` (สถานะ: แท็บละกี่แถว) · `--run [--tab "ตุลาคม 69"]` · หน้าสถานะระบบเตือนเมื่อล้ม/ไม่อัปเดตเกิน 40 นาที
- **วัดจริง 13 ต.ค.69**: 10 แท็บ **32,079 แถว** + แบน 152 · อ่านวันที่ออก 99.98% (ที่เหลือคือคนพิมพ์เบอร์/ข้อความลงช่องวันที่)
  · แท็บ ม.ค.–มี.ค. ไม่มีคอลัมน์จำนวน/เวลาอัพเดท (layout เก่า) · สถานะลูกค้า (Z) เริ่ม มิ.ย.
- **★ บั๊กแดชบอร์ดที่เจอระหว่างทำ (แก้แล้ว)**: แท็บ **มี.ค.69 หัว A เขียน "DATE"** ไม่ใช่ "ว/ด/ป" → `_resolve_lead_colmap`
  ไปจับ "ว/ด/ป" ที่**คอลัมน์ S** (วันที่อีกตัว · ว่าง 229 แถว) → **แดชบอร์ดนับลีด มี.ค. ได้ 2,507 แทน 2,723 (หาย 216)**
  · เพิ่ม alias `"DATE"` ใน `_LEAD_FIELD_ALIASES` (เทียบหัวจากซ้ายไปขวา → คอลัมน์ A ชนะ) · ตัวเลข มี.ค. บนแดชบอร์ดจะขยับขึ้นหลัง deploy
- `db_inventory.TABLES` มีคำอธิบาย + ป้ายข้อมูลส่วนบุคคลแล้ว · ⚠️ บัญชีอ่านจากข้างนอก (`ext_online`) เห็นตารางใหม่เองตาม
  `ALTER DEFAULT PRIVILEGES` (เจ้าของตัดสินให้เปิดทุกตารางเมื่อ 4 ต.ค.69) · `ro_safe` ไม่เห็น (allow-list)
- **เทสต์**: `python scripts/test_sheet_mirror.py` (35 ข้อ · ปลอมที่ `requests`)

### 🧳 ย้าย n8n มาเครื่องเดียวกับ SaleForce — [deploy/n8n_move/](deploy/n8n_move/README.md) · 13 ต.ค.69
เจ้าของแจ้ง *"N8N เหมือนจะหมดโปรแล้ว"* → เลือก **ยก n8n ทั้งก้อนมาเครื่อง SaleForce** (ไม่เขียน workflow ใหม่เป็นโค้ด)
- **ตรวจผ่าน Hostinger API (เจ้าของเชื่อมไว้)**: เครื่อง n8n = VPS id `1102218` `srv1102218` (72.61.114.81) KVM 2 ·
  subscription `non_renewing` **หมดอายุ 3 พ.ย.69** (ไม่ใช่ 7 วันอย่างที่คิดตอนแรก) · เครื่อง SaleForce = id `1793506`
  · ทั้งคู่ 2 CPU / 8 GB / 100 GB · แรมใช้จริง ~2.5 + ~2.4 GB · CPU 2–7% / ~4% · ดิสก์ 54 GB / 9 GB → **รวมได้**
- เครื่องเดิม = docker compose project `root` (`/root/docker-compose.yml`): **n8n 2.22.5 + postgres:16 (DB ของ n8n)
  + n8nio/runners + traefik (ถือพอร์ต 80/443)** · `GENERIC_TIMEZONE=Europe/Berlin` (คงไว้ — schedule จะไม่เลื่อน)
  · compose มีค่าลับฝังตรง (กุญแจถอดรหัส · รหัส DB · โทเคน runner) — **ห้ามคัดลงไฟล์ในโปรเจกต์**
- **`*.srv1793506.hstgr.cloud` มี wildcard DNS ชี้เครื่องเราอยู่แล้ว** → n8n ใหม่ = `https://n8n.srv1793506.hstgr.cloud`
- [move.sh](deploy/n8n_move/move.sh) รันบนเครื่อง SaleForce (root) คุยกับเครื่องเดิมผ่าน ssh (ControlMaster = ถามรหัสครั้งเดียว)
  · `check` (ดูอย่างเดียว) → `prepare` (ลง docker.io + compose · `/opt/n8n` · nginx `sites-available/n8n` + certbot ·
  เปิดแค่ postgres เปล่า) → `cutover` (หยุด n8n เดิม + ตั้ง restart=no · pg_dump + tar ข้อมูล · scp · ตรวจ sha256 +
  จำนวน workflow · เปิด n8n ใหม่) → `webhooks` (URL ที่ต้องแก้) → `fixurls` (แทนชื่อเครื่องเดิมใน `workflow_entity`/
  `workflow_history`) · `rollback` · `cleanup`
  · กุญแจถอดรหัส **ดึงจาก container เดิมตรงลง `/opt/n8n/.env` (600) ไม่พิมพ์ออกจอ** · รหัส DB/โทเคน runner สุ่มใหม่
  (ย้ายด้วย pg_dump ไม่ได้ย้ายบัญชี) · เวอร์ชัน = ที่รันจริง (`n8n --version`) ไม่ใช่ tag ใน compose
  · nginx ของ n8n ฟัง **IPv4 อย่างเดียว** เหมือน block ของ SaleForce — ใส่ `[::]:80` ที่นี่ที่เดียว certbot จะให้
    `[::]:443` แก่ block นี้ แล้วคนเข้า SaleForce ทาง IPv6 อาจได้หน้า n8n
- n8n ต่อ Postgres ของ SaleForce ผ่าน **SSH tunnel ไป 76.13.214.140** (deploy/n8n_postgres_access.md ทาง A) → ย้ายแล้วใช้ได้เดิม
  · SaleForce ไม่มีโค้ดเรียก URL ของ n8n (ค้นแล้ว) · n8n ยิงเข้า SaleForce ทาง URL สาธารณะ ยังใช้ได้
- **สิ่งที่เจ้าของต้องทำเอง**: แก้ Webhook URL ใน LINE Developers / Fireflies (เปลี่ยนแค่ชื่อเครื่อง) · ทำ cutover ตอนดึก
  (นอก 06:00–10:00 ช่วงเช็คชื่อ) · ยังไม่มี snapshot ของเครื่อง SaleForce (เสนอให้ถ่ายก่อน prepare)
- สำรวจ workflow (Claude in Chrome · อ่านอย่างเดียว) ได้ 50 จาก 63 · ⚠️ "ซื้อขายเทิร์นรถ" ยังขึ้น Published (ย้ายเข้า
  SaleForce แล้ว 8 ต.ค.) · "สร้างตารางเช็คชื่อ" เปิดอยู่ (ซ้อนกับ checkin_report ถ้าเปิดฝั่ง SaleForce ด้วย) ·
  "Cron Tick Every Minute" ไม่ได้ Published แต่ cron_tick ยังถูกยิง = workflow อื่นยิงอยู่
  · ⚠️ API ภายใน `/rest/workflows` ตอบ 401 แม้ใส่ browser-id และหลังลองแล้วหน้า n8n เด้งไป signin — อย่าลองซ้ำ อ่านจากหน้าจอแทน
- **ทรัพยากรรวม (เจ้าของถาม "สองเว็บ + แอป + n8n รับไหวไหม")**: เว็บโชว์รูม (:8080) กับ API แอปมือถืออยู่เครื่อง SaleForce
  อยู่แล้ว → ของใหม่คือ n8n อย่างเดียว · วัดจริง: SaleForce กลางวัน **แรมไต่ 2.4 → 4.0 GB** (12 ต.ค. · ลดหลังรีสตาร์ต =
  gunicorn worker บวม) CPU ≤12% · รวม n8n ช่วงพีค ~6–6.5/8 GB → **ตึงที่แรม ไม่ใช่ CPU/ดิสก์**
  · compose ใส่ **`mem_limit`** (n8n 3g · runner 1536m · postgres 1g) + `NODE_OPTIONS` ต่ำกว่าเพดาน (2048/1024 — เดิม 4096/2048)
    + **หมุน log 10m×3** (เครื่องเดิมไม่มีเพดาน) → n8n แรมพุ่งตายแค่ตัวเอง ไม่ลากเว็บ · แนะนำ swap 4 GB + gunicorn
    `--max-requests 2000 --max-requests-jitter 200` (README หัวข้อทรัพยากร · `check` บอกว่ามี swap ไหม)
- `bash -n` ผ่านทั้งสคริปต์หลักและสคริปต์ที่ส่งไปรันบนเครื่องเดิม · **ยังไม่ได้รันจริง** (ไม่มีสิทธิ์ SSH เข้าเซิร์ฟเวอร์)

### 🔁 workflow ซื้อขายเทิร์นรถ (อยู่ฝั่ง n8n · **เลิกใช้แล้ว 8 ต.ค.69** — ดูหัวข้อข้างบน) — 17 ก.ย.69
**ไม่ใช่โค้ดของระบบเรา** แต่เก็บสำเนาไว้เพราะเจ้าของให้ช่วยแก้ · workflow อ่านข้อความเคสรับซื้อ/เทิร์น
จากกลุ่ม LINE → parse → เขียนลงชีต **"ซื้อขายเทิร์นรถ"** · ไฟล์ `deploy/n8n_tradein_*` เก็บไว้เป็นต้นฉบับที่เทสต์เทียบ
- **📄 [deploy/n8n_tradein_build_row.js](deploy/n8n_tradein_build_row.js)** = โค้ดเต็มของโหนด
  **`Build Sheet Row (Trade-in)`** (**v22**) — ก๊อปวางทับในช่อง Code ของโหนดนั้น
  · สำเนาเดียวกันฝังอยู่ใน [n8n_tradein_nodes.json](deploy/n8n_tradein_nodes.json) — **แก้ .js แล้วต้องซิงก์ตัวนั้นด้วย**
- **📄 [deploy/n8n_tradein_sheet_section.json](deploy/n8n_tradein_sheet_section.json)** = ชุดโหนดเขียนชีต (v2 · 8 ต.ค.69)
  วางทับชุดเดิมหลัง Build Sheet Row: `If1` → **เพิ่มแถวเคสใหม่** / **อ่านเคส 2 เดือน → รวมคอมเมนท์ → อัปเดตคอมเมนท์**
  · **เทสต์: `node scripts/test_n8n_tradein.js`** (26 ข้อ · ไม่ใช้ข้อมูลจริง)
- **★ ชีต "ซื้อขายเทิร์นรถ" = `PURCHASE_SID` ไฟล์เดียวกับที่ตามงานจัดซื้อ/`/buy/`/รายงานห้องเคสHOT อ่านอยู่**
  → ค่าที่ workflow นี้เขียน **กระทบตัวเลขของระบบเราโดยตรง** (โดยเฉพาะช่อง K)
- **★ ต้นเหตุที่แก้: group id ที่ฝังในโค้ดเป็นของบอทเก่า** — `GROUP_HOT`/`GROUP_VERY_HOT`/`GROUP_IGNORED`
  ทั้ง 3 ตัว **ไม่มีในทะเบียน `line_groups` และไม่มีสักข้อความใน `checkout_groupchat`**
  แต่โหนด `LINE - Get Profile` ใช้เครดิต **OxletautoGiveLead** → ไอดีที่วิ่งเข้ามาเป็นคนละชุด
  = **เงื่อนไข `caseType` ไม่เคยเข้าเลย · ตัวกันกลุ่ม "ห้องเก็บรถ" ไม่ทำงาน**
  · น่าจะเป็นต้นเหตุ "ชื่อหาย" ที่ต้องเขียน Scavenger Mode + `MANUAL_MAPPING` มาปะด้วย
  (groupId ผิดฝั่ง → group member API ตอบ 404 → โหนดตั้ง `onError: continueRegularOutput` = ผ่านเงียบ)
- **v20 เปลี่ยน `GROUP_HOT` เป็น map 2 กลุ่ม** (เจ้าของยืนยัน "ทุกอย่างเหมือนกันหมด ต่างแค่คน"):
  `C0ad44e22…`=พี่หมี · `C6a645033…`=พี่ต๊าด → **HOT ทั้งคู่** · แถม **เติมช่อง "จัดซื้อ" จากเจ้าของกลุ่ม
  เมื่อไม่มีใครถูก @tag** (`purchaserFinal` — @tag ยังชนะเสมอ)
- **★★ v21 (8 ต.ค.69) — เจ้าของยืนยัน "webhook ตัวเดียวกับบอทตอนนี้ · กลุ่มตามลิสต์จัดซื้อ"**
  - **`PURCHASE_GROUPS` = รายชื่อที่รับ (allow-list) 3 ห้อง** ไอดีฝั่งบอทตัวส่ง ยืนยันกับ `checkout_linegroup`:
    `C0ad44e22…` เคสHOT (พี่หมี) · `C6a645033…` เคสHOT (พี่ต๊าด) · **`Cd308fd5c…` เคสVERY HOT** (owner ว่าง —
    ห้องนี้พี่หมี/พี่ต๊าดสลับกันดู ใช้ @tag อย่างเดียว) · **กลุ่มอื่นข้ามหมด** (เดิมกันแค่ห้องเก็บรถด้วยไอดีบอทเก่า
    → webhook เดียวกันได้ยินห้องจ่ายเบอร์ด้วย ใบจ่ายลีดมีเบอร์โทร = กลายเป็นแถวเคสเทิร์นได้) · มีห้องใหม่ = เติมบรรทัดเดียว
  - **เคส (O) = ตามห้อง** เลิกเดาจากรหัส (`includes("C-")` ทำ OC/SC/TC เป็น COOL หมด)
  - **★ ช่อง K "รับซื้อ/ไม่รับซื้อ" เว้นว่างเสมอ** — เดิมเติม "รับซื้อ" ทันทีที่เจอคำนี้ ซึ่งมีใน**แม่แบบใบทุกใบ**
    (บรรทัด `ราคากลางรับซื้อจากตาราง :` 274 ใบ + ADS `รับซื้อ CIVIC`) → วัดจริง 85% ของใบ · แท็บ TestBot ได้ "รับซื้อ" 64/70 แถว
    · ชีตจริงทีมเว้นว่าง 448/480 แถว · **K คือตัวปิดงานของ `purchase_followup`** มีค่า = ถือว่าตัดสินแล้ว
    → ถ้าย้ายไปเขียนแท็บจริงโดยไม่แก้ เคสใหม่จะหายจาก "ยังไม่ได้โทร" ทันที · ("ไม่รับซื้อ" ก็ได้ "รับซื้อ" ด้วย — เช็คคำสั้นก่อน)
  - โปรไฟล์ลูกค้า (P) หยุดที่บรรทัด `ราคากลาง…`/`ราคาตาราง` (อยู่หลัง ขายเพราะ/หมายเหตุ → เคยปนทุกใบ · บรรทัดนี้ไม่มีตัวเลขเลยสักใบ)
  - ขึ้นต้น `โค้ด` = เคสใหม่เสมอ · ขึ้นต้นรหัส `OC-1234` = คอมเมนท์เสมอ (เดิมดู "มีเบอร์ไหม" → ใบไม่มีเบอร์ 2 ใบหาย)
    · **คอมเมนท์ที่ไม่มีรหัส = ข้าม** (แชทคุยทั่วไป 47/600 ข้อความ เดิมถูกส่งไปค้นแถวด้วย Code ว่าง)
  - ทดสอบกับแชทจริง 600 ข้อความ + ห้องอื่น 150: ใบเคส 345/345 เป็นแถว · K ว่างทุกแถว · ห้องอื่นออก 0 · v20 พลาด 11 จุด
  - **⚠️ ยังไม่ได้แก้ (ต้องแก้ในหน้าจอ n8n เอง)**: โหนด Postgres ชื่อเล่นยังตั้ง `onError: continueRegularOutput`
- **★★ v22 + ชุดโหนดชีต v2 (8 ต.ค.69 · เจ้าของสั่ง "เผื่อเดือนหน้าหรือเดือนต่อไปด้วย")**
  - Build Sheet Row ส่ง **`_tab`** (แท็บเดือนนี้ คิดจากเวลาไทย · ข้ามปีได้) + **`_tabPrev`** + **`rowAS`** (ค่า A–S ตามตำแหน่ง ·
    เบอร์ใส่ `'` · ข้อความขึ้นต้น `= + - @` ใส่ `'` · วันที่ปี ค.ศ. 4 หลัก · S = car) · ช่อง `values` เดิมยังอยู่
  - **เลิกใช้โหนด Google Sheets (append/lookup/update ตามชื่อหัวคอลัมน์)** → HTTP Request ยิง Sheets API ตรง:
    **เพิ่มแถว** = `values/'<_tab>'!A3:S:append` + `USER_ENTERED` + **`insertDataOption=OVERWRITE`**
    (**ห้าม INSERT_ROWS** — แทรกแถว = บล็อก X–AV ข้างๆ เลื่อนลงทั้งแผง) · ชีตหาแถวท้าย**เฉพาะในช่วง A–S**
    → ต้นเดือนลงแถว 3 ถูก ไม่สนบล็อกข้างๆ · ไม่ขึ้นกับชื่อหัว (O ว่าง / `ADS` / `car`) อีก
    · **คอมเมนท์** = `values:batchGet` C3:Q ของ `_tab` + `_tabPrev` ในคำขอเดียว → โหนดโค้ดหาแถว (เดือนนี้ก่อน ·
    ซ้ำ = แถวล่างสุด) → `PUT 'แท็บ'!Q<แถว>` แบบ **RAW** (วัดจริง: ต.ค. คอมเมนท์ 1 ใน 9 พูดถึงเคส ก.ย. · ห่างได้ 11 วัน)
  - **credential `Google Service Account account 2` ต้องเปิด "Set up for use in HTTP Request node"**
    + scope `https://www.googleapis.com/auth/spreadsheets` ไม่งั้นโหนด HTTP ใช้ไม่ได้
  - **v22.1** ผู้ส่ง (N): คำว่า "เซล" ต้องขึ้นคำใหม่หรือต่อจาก เทิร์น/เทริน/จาก — เดิม **"ดีเซล 1,898 ซีซี"**
    (บรรทัดเครื่องยนต์) ทำให้ผู้ส่งเป็น "1,898" (บั๊กมีมาตั้งแต่ v19) · "เทิร์นเซลล์เก้า" ยังได้ "เก้า" ตามเดิม
  - **⚠️★ ข้อเท็จจริงที่ต้องรู้ก่อนให้บอทเขียนแท็บจริง (วัด 8 ต.ค.69)**: **ทีมแอดมินกรอกเคสลงแท็บรายเดือนเองทุกใบ**
    (B เลขคันที่ · N = แอดมินที่โพสต์ใบ หมิว/โดนัท/มิว) ภายในไม่กี่ชั่วโมงหลังโพสต์ → ถ้าบอทเขียนแท็บเดียวกัน
    **ทุกเคสจะซ้ำ 2 แถว** (นับซ้ำทั้งตามงานจัดซื้อและแดชบอร์ด) · ต้องให้เจ้าของเลือกก่อน: บอทเขียน+ทีมเลิกพิมพ์เคส
    หรือทีมกรอกต่อ+บอทเขียน TestBot · **ยังไม่ได้ตัดสิน**
  - **⚠️ workflow ใน n8n ไม่ได้เขียนอะไรเลยตั้งแต่ 5 ต.ค.69** (แถวสุดท้ายใน TestBot = OC-7573) — สาเหตุอยู่ฝั่ง n8n
    (เข้าไปดูไม่ได้) · **เติม TestBot ย้อนหลังให้แล้ว 8 ต.ค. 12:40** (แถว 73–135 · OC-7574 ถึง SC-1301 · 63 เคส +
    คอมเมนต์ 9 แถว) ด้วยโค้ด v22.1 ตัวจริง · โพสต์ซ้ำ = แถวเดียว · `OC-764` = พิมพ์รหัสผิดของ OC-7604 (เบอร์เดียวกัน) ไม่เติม
    · **เบอร์เดียวกันไม่ได้แปลว่าเคสซ้ำ** (OC-7614/OC-7616 ลูกค้าคนเดียวขาย 2 คัน ทีมกรอกแยก 2 แถว)
  - **ยังไม่ได้ทำใน n8n**: คอมเมนต์โอนเคส ("ติดต่อพี่หมีไม่ได้ เปลี่ยนเป็นของพี่ต๊าด @…" / "พี่หมีดูแทน @หมีน้อย")
    ควรเปลี่ยนช่องจัดซื้อ (M) ตาม — ตอนนี้บอทเขียนแค่ Q · ตอนเติมย้อนหลังแก้ M ให้ SC-1299/SC-1300 ด้วยมือแล้ว
  - **ทดสอบกับชีตจริงแล้ว** (แท็บชั่วคราวทำสำเนาจาก ต.ค. แล้วลบทิ้ง): แถวแรกลง **A3** ทั้งที่ X/AP มีค่าถึงแถว ~58 ·
    วันที่เป็นค่าวันจริง · เบอร์ไม่หาย 0 · batchGet 2 แท็บได้ · **dropdown strict ไม่ปฏิเสธค่าที่เขียนผ่าน API**
    (รับไว้แต่ขึ้นว่าค่าผิด — ไม่ต้องกลัวแถวหาย)
  - **📐 โครงแท็บ `ขายรถจบออนไลน์ <เดือน>69` (วัดจริง 8 ต.ค.69)** — แท็บเดียวมี 4 บล็อกเรียงข้างกัน:
    **A–S เคส (บอทเขียนตรงนี้เท่านั้น)** · T–W ทีมตาม Follow เอง · X–AH "รับซื้อรถ" · AI–AM สรุปเป็นสูตร (แถว 3–~38)
    · AP–AV "จัดซื้อรับเข้า" · แถว 1 = ชื่อเดือน/ชื่อบล็อก · แถว 2 = หัว · ข้อมูลเริ่มแถว 3 ต่อจากแถวสุดท้ายที่มี Code (C)
    · **B "คันที่" = เลขลำดับ = เลขแถว − 2** (ทีมพิมพ์เอง · บอทเว้นว่าง)
    · **⚠️ ห้ามให้ n8n หาแถวท้ายจากทั้งแท็บ** — X/AP เลขคันที่พิมพ์รอไว้ถึงแถว ~46–61 และ AI–AM สูตรถึงแถว 38
    → ต้นเดือนแถวแรกของบอทจะไปตกแถว ~60 เว้นช่องว่างข้างบน · ต้องจำกัดช่วงที่ **A–S**
    · dropdown I–O,R ตั้ง **strict** — ค่าที่บอทเขียนแต่ไม่อยู่ในลิสต์: ช่องทาง `หน้าร้านอ่อนนุช` (ลิสต์มี `หน้าร้านเทพารักษ์`)
    · car (S) ในลิสต์มีช่องว่างท้าย `D Max ` `HRV ` `Vigo ` และไม่มี `Civic` เฉยๆ (มี FC/FE/FK/FB/FD)
    · ชื่อแท็บเปลี่ยนทุกเดือน (ปี พ.ศ. 2 หลักติดท้าย ไม่เว้นวรรค) · **แท็บเดือนหน้าต้องสร้างก่อนวันที่ 1** ไม่งั้นโหนดเขียนล้ม
      → **ระบบเราสร้างให้เองแล้ว** (ดูหัวข้อ "เตรียมแท็บชีตจัดซื้อเดือนใหม่" ข้างล่าง)
    · ห้อง VERY HOT มีคอมเมนท์ "พี่ต๊าดติดต่อไม่ได้ พี่หมีดูแทน @หมีน้อย" → ช่อง "จัดซื้อ" (M) ยังไม่เปลี่ยนตาม

**🗂️ เตรียมแท็บชีตจัดซื้อเดือนใหม่ให้อัตโนมัติ — [purchase_tabs.py](dashboard/services/purchase_tabs.py) · 8 ต.ค.69**
- `cron_tick` (ทุก 10 นาทีที่นาที :x7 · ใน thread) → `maybe_prepare()` เช็ควันละครั้ง: **แท็บเดือนนี้ต้องมี** ·
  ตั้งแต่ **วันที่ 25** แท็บ**เดือนหน้า**ต้องมี · มีแล้ว (ทีมสร้างเอง) = ไม่ทำอะไร · ล้ม = ลองใหม่หลัง 1 ชม.
- วิธีสร้าง: **ทำสำเนาแท็บเดือนล่าสุด** (ถอยได้ 3 เดือน · dropdown/สูตร/สีมาครบ) → **ล้างค่า** A–W · Y–AH · AQ–AV
  (ไม่แตะ X/AP เลขคันที่ · AI–AM สูตรสรุป · **คอลัมน์ที่สูตร ≥ ครึ่งของเซลล์ที่มีค่า = เก็บไว้**) → แก้ชื่อเดือนแถว 1
  (เฉพาะเซลล์ที่เปลี่ยน · RAW) · **ล้างไม่หมด/ล้างล้ม = ลบแท็บใหม่ทิ้งทันที** (ไม่งั้นเคสเดือนก่อนค้างใต้ชื่อเดือนใหม่
  แล้ว fetch_dashboard ที่นับเดือนตามชื่อแท็บจะนับซ้ำ) · **ไม่มีคำขอเขียนใดอ้างแท็บต้นฉบับ** (มีเทสต์)
- `manage.py purchase_tab` (สถานะ) · `--month 2026-11` (ดูแผน · อ่านอย่างเดียว) · `--month … --apply` (สร้างจริง) ·
  `--auto off|on` (KV `purchase_tab_auto` · เปิดโดยปริยาย) · ผลรอบล่าสุด KV `purchase_tab_last` ·
  สร้างแล้ว/ล้ม จดที่ `dash_event_log` (kind=cron) · **หน้าสถานะระบบร้องเมื่อเตรียมไม่สำเร็จ หรือไม่ได้เช็คเกิน 2 วัน**
- ทั้ง 2 service account (prod `google-account-oxletauto` · dev `n8n-sheets`) เป็น **writer** บนไฟล์นี้ (เช็ค 8 ต.ค.69)
- **เทสต์**: `python scripts/test_purchase_tabs.py` (35 ข้อ · ปลอมที่ `requests`) + ทดสอบกับชีตจริงบนแท็บชั่วคราวแล้ว
- **★ แก้ไปพร้อมกันใน `purchase_followup`** (ตามงานจัดซื้อ · `/buy/` · รายงานห้องเคสHOT ใช้ตัวนี้):
  (1) อ่านแค่ `A3:W400` = 398 แถว/เดือน — **ก.ย.69 มี 480 แถว เคสปลายเดือน ~80 เคสหายจากรายการตามงาน**
  (บั๊กเดียวกับที่แก้ใน fetch_dashboard 28 ก.ย.) → ใช้ `_PURCHASE_MAX_ROW` ·
  (2) **เดือน ม.ค. ข้ามเดือนก่อนทิ้ง** (`m-1=0`) และใช้ปี พ.ศ. เดียวกันทั้ง 2 แท็บ → ตอนนี้ ม.ค.70 อ่าน `ธันวาคม69` ด้วย
  · helper ใหม่ `tab_name(ปี, เดือน)` / `prev_month()` ใช้ร่วมกับ purchase_tabs

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

#### 🌐 ปุ่ม Active — รถขึ้นเว็บเมื่อกดเท่านั้น (13 ต.ค.69 · เจ้าของสั่ง)
*"เพิ่มปุ่ม Active … เมื่อกด Active แล้ว รถถึงจะแสดงหน้าใน Web Oxlet"* · เจ้าของเลือก: **ต้องถึงพร้อมขายก่อน** ·
**รถที่ขึ้นเว็บอยู่แล้วโชว์ต่อ (นับเป็น Active)** · **กดได้เฉพาะผู้บริหาร + แอดมิน** · **สวิตช์อยู่ในป๊อปอัปรถ (หน้าสถานะรถ)**
- **ขึ้นเว็บ = `web_active` AND สเตปพร้อมขาย/จอง (`C.WEB_STAGES`)** · ขายแล้ว = หายเสมอ · **เลิกพฤติกรรมเดิมที่รถขึ้นเว็บเองทุกคันที่ถึงพร้อมขาย**
  · กด Active ก่อนถึงพร้อมขายได้ = รอ แล้วขึ้นเองตอนถึง (post_save ส่งเหมือนเดิม)
- **`Car` (cars migration 0019)**: `web_active` · `web_active_at` · `web_active_by` (= ความตั้งใจ) ·
  **`web_listed` = เว็บโชว์รูมตอบกลับมาว่าลูกค้าเห็นอยู่ (ของจริง ไม่เดาจากสเตป)** · `web_synced_at` · `web_sync_error`
  · `Car.web_state` → `{key: live|wait|pending|error, text, color}` หรือ None — ใช้ทั้งป้ายลูกโลกบนการ์ด + ป๊อปอัป
  · migration นับ Active ให้รถที่ **อยู่พร้อมขาย/จอง หรือเคยถึงพร้อมขาย (`frontline_at`) และสถานะ active** (พัก/ขายแล้ว/ยังทำสภาพ = ไม่)
- **[showroom_sync.py](cars/showroom_sync.py)** เขียนใหม่: payload มี **`active`** · **`push_showroom(car)`** (ยิงแล้วรอผล · ปุ่ม/คำสั่ง) +
  `notify_showroom(car)` (post_save · thread) · **ทั้ง 2 ทางบันทึกผลลงรถด้วย `.update()`** (ไม่ยิง post_save ซ้ำ = ไม่วน) ·
  ส่งไม่สำเร็จ = แปลเป็นภาษาคน (เน็ต/timeout/401 รหัสลับไม่ตรง/HTTP) เก็บที่ `web_sync_error` + `dash_event_log` kind=`showroom`
  · ปุ่ม = จดทุกครั้ง · อัตโนมัติ = จดเฉพาะตอนพลาด · `BG=False` ในเทสต์
- **API `POST /track/api/web_active {code, active}`** (`api_web_active` · csrf_exempt แบบ set_priority) — `roles.can_set_web_active` = **{EXEC, ADMIN}**
  (superuser = EXEC) · บันทึกก่อนแล้วส่ง → คืน `message` ภาษาคน + `web` · ส่งไม่สำเร็จ Active ยังติด (กด "ส่งอีกครั้ง" ได้) · รถขายแล้วกด = 400
- **ป๊อปอัป** ([dashboard.html](templates/dashboard.html) `_webSection`/`_webStateHtml`/`setWebActive`/`_cardWeb`): สวิตช์ + สถานะจริง + ลิงก์ "ดูบนเว็บ" +
  ใครกดเมื่อไหร่ · **ถามยืนยันทั้งเปิด/ปิด** · คนที่ไม่มีสิทธิ์เห็นแค่บรรทัดสถานะ · การ์ดบนบอร์ด = ไอคอน `globe` ใน `<span class="webb" style="display:contents">`
  (สีตามสถานะ · อัปเดตทันทีไม่ต้องรีโหลด) · i18n `webTitle`/`webOpen` ใน `UT`
- **ลิงก์ "ดูบนเว็บ"** = `<SHOWROOM_PUBLIC_URL>/stock/<รหัสรถ>/` (โชว์รูมเด้งไปหน้ารถเอง) · **env ใหม่ `SHOWROOM_PUBLIC_URL`** ·
  ไม่ตั้ง = เดาจาก webhook URL · **webhook เป็น 127.0.0.1/localhost (2 เว็บ VPS เดียวกัน) = ไม่มีลิงก์ ต้องตั้งเอง**
  · ⚠️ `.env` ในเครื่อง dev ตั้ง `SHOWROOM_WEBHOOK_URL=http://127.0.0.1:8080/…` → prod น่าจะยิงทางในเครื่องเหมือนกัน
- **`manage.py showroom_push [--apply] [--code X] [--errors] [--out]`** — ส่งรถ Active ทุกคันแล้วบันทึกสถานะจริง ·
  **รันครั้งเดียวหลัง deploy** (migration รู้แค่ว่า Active ไม่รู้ว่าเว็บมีประกาศจริงไหม) · ไม่ใส่ `--apply` = ดูเฉยๆ
- **หน้าสถานะระบบร้อง**: มีรถ Active แต่ยังไม่ตั้ง webhook (warn) · รถ Active ส่งไม่สำเร็จ (err)
- **⚠️ ลำดับ deploy: โชว์รูมก่อน แล้วค่อย SaleForce** — โชว์รูมรุ่นเก่าไม่รู้จัก `active` จะถือว่า true → รถไม่ Active ถึงพร้อมขายแล้วถูกสร้างประกาศ ·
  กลับกัน (โชว์รูมใหม่ + SaleForce เก่าที่ไม่ส่ง active) = ถือว่า true = พฤติกรรมเดิม ไม่พัง
- **★ ราคาขายส่งไปเว็บด้วย (13 ต.ค.69 รอบ 2 · เจ้าของสั่ง)** — `showroom_sync.sale_price(car)` = **`Car.price` (กรอกเอง) ก่อน →
  `extra["price_num"]` (นำเข้า Car Spend)** ลำดับเดียวกับ `cars_api.priceNum`/need_match · ใส่ payload ช่อง `price` ทุกครั้ง
  · **SaleForce = แหล่งความจริงของราคา**: มีราคา = ทับราคาบนเว็บทุกรอบ (staff แก้ราคาในโชว์รูมจะโดนทับ → แก้ที่หน้าแก้ไขรถฝั่งนี้) ·
  ไม่มีราคา = เว็บคงราคาเดิม · แก้ราคาที่หน้าแก้ไขรถ → post_save ส่งราคาใหม่เอง (ถ้ารถอยู่พร้อมขาย/จอง)
  · ข้อความหลังกด Active บอกราคาที่ขึ้นเว็บ / บอกให้ไปใส่ราคาถ้ายังไม่มี
- **★ คอลัมน์ "Active" ในตารางรถ (หน้า /track/)** — สวิตช์เลื่อน (`.wsw`/`.wsl` · **มุมมน 7px ไม่ใช่แคปซูล** ตามกติกาหน้าตา) +
  ป้ายสั้นใต้สวิตช์ (`Car.web_state["short"]` = `C.WEB_STATE_SHORT`) · ข้อความเต็มใน `title` · `td` หยุด click (ไม่เปิดป๊อปอัป)
  · สวิตช์โชว์เฉพาะ `can_web` (context จาก `dashboard` view) · คนอื่นเห็นป้ายอย่างเดียว · รถขายแล้ว = สวิตช์กดไม่ได้
  · JS ใช้ตัวส่งเดียวกับป๊อปอัป (`_postWebActive` → `_syncWebUI` อัปเดตการ์ด/ตาราง/ป๊อปอัปพร้อมกัน) · ส่งไปเว็บไม่สำเร็จ = `alert`
- **★ รูปหน้าปกไปเว็บด้วย (13 ต.ค.69 รอบ 3 · เจ้าของ: "รูปหน้าปกไม่มา")** — `_photo_urls()` ส่งรูปขาย (`extra.sale_photos`) เหมือนเดิม
  · **ไม่มีรูปขาย = `_cover_fallback()` ส่งรูปเดียว**: `Car.photo` (ไฟล์บนดิสก์ต้องมีอยู่จริง เช็คที่ `MEDIA_ROOT`) → ไม่มี/หาย = รูปแรกของอัลบัม Car Spend
  (`extra.image_urls[0].full` · ลิงก์สาธารณะ ทดสอบแล้วดึงได้ด้วย UA ธรรมดา) · key คงที่ (`path` / `carspend:<file>`) → อัปรูปขายทีหลัง โชว์รูมลบปกนี้แล้วใช้รูปขายแทนเอง
  · รถที่ขึ้นเว็บไปแล้วจะได้รูปเมื่อส่งรอบถัดไป (`showroom_push --apply` ซ้ำ) · เทสต์ `python scripts/test_showroom_photos.py` (11 ข้อ · ไม่ใช้ DB)
- **⚠️★ บนเซิร์ฟเวอร์จริงไม่เคยตั้ง `SHOWROOM_WEBHOOK_URL`/`STOCK_SYNC_SECRET` เลย** (เจอ 13 ต.ค.69 ตอน `showroom_push` ขึ้น "ยังไม่ได้ตั้ง")
  → ระบบรถไม่เคยส่งรถไปเว็บโชว์รูมสักคันตั้งแต่ทำ webhook (ก.ค.69) ทั้งที่ `.env` ในเครื่อง dev มีค่า · **`.env` เครื่อง dev ≠ `/opt/oxlet/.env`**
  · ตั้งแล้ว: secret คัดลอกจาก `/opt/oxletauto_web/.env` · URL = `http://76.13.214.140:8080/api/stock-update/` (IP สาธารณะ — ทดสอบจากข้างนอกแล้วผ่าน ·
  `127.0.0.1:8080` ยังไม่เคยทดสอบ อาจโดน ALLOWED_HOSTS ของโชว์รูม) · `SHOWROOM_PUBLIC_URL=http://76.13.214.140:8080`
  · **เว็บโชว์รูมบน VPS** = `/opt/oxletauto_web` · branch `feat/plates-postgres` · `.venv` · ไฟล์เป็นของ `oxlet` · service **`oxletauto`** · nginx ฟังพอร์ต 8080
  · deploy โชว์รูม: `cd /opt/oxletauto_web && git pull && sudo -u oxlet .venv/bin/python manage.py migrate cars && sudo systemctl restart oxletauto`
  · หลังตั้งค่า + `showroom_push --apply`: เว็บโชว์รูมมีรถ 99 คัน (เดิม 8 คันนำเข้าจาก `scraped_cars.json` + จากระบบหลังบ้าน 91)
- **★ ฟอร์ม "ขอราคาพิเศษ / นัดดูรถ" ของเว็บโชว์รูม → ห้องพัก Lead (13 ต.ค.69 · เจ้าของ: "กรอกแล้วให้ส่งไปที่กลุ่มพักหลีด")**
  · เดิมฟอร์มนี้เก็บในฐานข้อมูลเว็บโชว์รูมเฉยๆ ไม่มีใครได้รับแจ้ง · ตอนนี้ [checkout/weblead.py](checkout/weblead.py) **`POST /api/showroom/lead`**
  (auth `X-Stock-Secret` = `STOCK_SYNC_SECRET` ตัวเดียวกับ webhook สต็อก · ไม่ตั้ง = 503) รับ `{lead_id, name, phone, email, message, source_page, car:{…}}`
  → โพสต์ **ใบจ่ายลีดฉบับร่าง** (`Ac Lead No. NLD<เดือน>-` ไม่มีเลขรัน · ช่องทาง **`web oxlet`** = ตัวเลือกในชีตลีด) เข้ากลุ่ม **"ADMIN เก็บ Lead"**
  ด้วยบอทตัวส่ง → เก็บลง `GroupChat` ของกลุ่มนั้นเอง (`message_id = web-lead-<id ฝั่งโชว์รูม>`) → **`leadpark.board()` เห็นเป็นลีดรอจ่ายเบอร์ทันที**
  (จ่ายเบอร์/ส่งใบเข้ากลุ่มจ่ายเบอร์ตามขั้นตอนเดิม) · ใช้ `slippost.body()` ตัวเดียวกับใบจริง
  · **LINE ล่ม = ยังเก็บลงห้องพัก Lead** (`extra.pushed=false` + เหตุผล) ลีดต้องไม่หาย · ส่งซ้ำ (lead_id เดิม) = ไม่โพสต์ซ้ำ
  · กลุ่มปลายทาง: หาจากชื่อกลุ่ม (`leadpark.PARK_HINTS`) เฉพาะที่บอทตัวส่งอยู่ · ตั้งเองได้ที่ KV `connect_config.web_lead_group`
    (⚠️ กดบันทึกหน้าตั้งค่า Connect อาจล้างคีย์นี้ — ตกกลับไปหาจากชื่อกลุ่ม) · ไม่พบกลุ่ม = 503 (เว็บโชว์รูมจดว่าส่งไม่ถึง)
  · ฝั่งเว็บโชว์รูม: env **`SALEFORCE_LEAD_URL`** (= `https://srv1793506.hstgr.cloud/api/showroom/lead`) · ผลการส่งจดที่ `Lead.forwarded_at/forward_error`
    (หน้า `/admin/cars/lead/` ของเว็บโชว์รูม) · ไม่ตั้ง = เก็บในเว็บโชว์รูมอย่างเดียวเหมือนเดิม
  · เทสต์ `python scripts/test_web_lead.py` (31 ข้อ · ปลอมแค่ `requests.post`) · ฝั่งโชว์รูม `scripts/test_lead_forward.py` (17 ข้อ)
- **ยังไม่ได้ทำ**: ตัวกรอง "ขึ้นเว็บ/ยังไม่ขึ้น" ในตารางรถ
- **เทสต์**: `python scripts/test_web_active.py` (64 ข้อ · ปลอมแค่ `requests.post` ด้วยตัวปลอมที่ทำตามสัญญา api_stock_update) ·
  ฝั่งโชว์รูม `python scripts/test_stock_active.py` (44 ข้อ) · ตรวจ E2E แล้ว: รัน 2 เว็บในเครื่อง (8000/8001 · SQLite) กดสวิตช์จริงในป๊อปอัป →
  ลูกค้าเห็นรถในโชว์รูม · ปิด = หาย · กดตอนซ่อมอยู่ = รอ แล้วขึ้นเองตอนถึงพร้อมขาย
  · ⚠️ รัน dev 2 เว็บพร้อมกัน: cmd `set DB_HOST=` = **ลบ**ตัวแปร แล้ว `load_dotenv` เติม Postgres จาก `.env` กลับ → ต้องตั้งเป็นค่าว่างจาก Python

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

### 📱 แอปมือถือ (เวอร์ชันทดลอง · Expo Go) — โปรเจกต์แยก `C:\Users\watta\OneDrive\Desktop\Project OXLETAUTO\OxletautoMobile` · 9 ต.ค.69
- **★ 16 ต.ค.69 แยกออกเป็นโปรเจกต์ของตัวเองแล้ว** (เจ้าของสั่ง "ไม่เอากองรวมกัน") — โฟลเดอร์ `C:\Users\watta\OneDrive\Desktop\Project OXLETAUTO\OxletautoMobile` · git แยก (ประวัติ 17 commit ติดมาครบ · ยังไม่มี remote GitHub) · **ฝั่งเซิร์ฟเวอร์ยังอยู่ใน SaleForce** (`/api/m/*` · `MobileTokenMiddleware` · `mobile_auth.py` · `mobile_home.py` · `scripts/test_mobile_api.py`) · path `src/...` ในหัวข้อนี้ = ในโปรเจกต์แอป
*"ทำ Demo ลง iOS ก่อนได้ไหม ฉันขอประเมินดูก่อนว่าควรจะจ่ายดีไหม · เรื่องแชท เรื่องสแกน QR Code เหมือนต้องใช้ใน Mobile ง่ายที่สุด"*
(เจ้าของเลือกให้ต่อ **เซิร์ฟเวอร์จริง**)

- **ทำไม Expo Go**: ทางเดียวที่ลงแอปจริงบน iPhone ได้ **ฟรี ไม่ต้องมี Mac ไม่ต้องจ่าย $99** · ข้อจำกัด: ไม่มี push ·
  ต้องเปิดผ่าน Expo Go + คอมรัน `npx expo start` วง Wi-Fi เดียวกัน · ใช้ได้เฉพาะ native module ที่มากับ Expo Go
  (camera/image-picker/secure-store/web-browser/crypto มีครบ) · Expo **SDK 57** + Expo Router (`src/app/`)
- **★ ไม่มี API ชุดใหม่ — แอปเรียก API เดิมของเว็บทั้งหมด** ด้วย `Authorization: Bearer`
  · **[dashboard/middleware.py](dashboard/middleware.py) `MobileTokenMiddleware`** (อยู่หลัง AuthenticationMiddleware
  ก่อน TrackSessionBridgeMiddleware) ใส่ `oxlet_user` ลง session ชั่วคราว **ไม่ส่งคุกกี้กลับ** · ข้าม CSRF เฉพาะคำขอที่ใช้ token
  (CSRF อาศัยคุกกี้ — header Authorization เว็บอื่นแนบให้ไม่ได้) · token ผิด/หมดอายุ = 401 `{relogin:true}` ไม่ตกไปใช้คุกกี้
  · **บัญชีคนงาน (`user_id="django_<ชื่อ>"`) ผูก Django user ตัวจริงตรงๆ** — ไม่งั้น bridge สร้าง `line_django_<ชื่อ>`
    บัญชีใหม่ไม่มีบทบาท ช่างเปลี่ยนสเตปไม่ได้ (มีเทสต์) · ปิดบัญชีที่ /track/users/ = token ใช้ไม่ได้ทันที
- **login** ([mobile_auth.py](dashboard/services/mobile_auth.py)): ใช้หน้า login เดิมของเว็บ (ไม่ใช้ LINE SDK ·
  ไม่ต้องแก้อะไรใน LINE Developers) → รหัสใช้ครั้งเดียว 2 นาที → แลก token ด้วย **PKCE**
  · ที่อยู่กลับเข้าแอปรับเฉพาะ `oxletauto://` หรือ `exp://<IPv4 วงใน>:<port>/--/…` (`MOBILE_DEV_REDIRECTS` · ไม่รับ
  tunnel/IP สาธารณะ — ไม่งั้นใครก็ตั้งเครื่องตัวเองแล้วหลอกให้พนักงานกดลิงก์ รหัสจะวิ่งไปหาเขา)
  · `via=pw` → `/login/` (คนงานกรอกชื่อผู้ใช้+รหัส) · `login_view` อนุญาต next `/m/handoff/` แล้ว
  · ตาราง **`dash_mobile_login`** (ใบผ่านทาง · ลบเองเกิน 1 วัน) + **`dash_mobile_token`** (เก็บแฮช · 30 วัน)
    — dashboard migration **0015** · เติมใน `db_inventory.TABLES` แล้ว · login จดใน `dash_event_log` kind=`mobile`
- **ในแอป** (แถบล่าง `src/app/(tabs)/` · จัดตามบทบาท — ดู "11 ต.ค.69 ข้อมูลจริง" ข้างล่าง · **หน้าแรกหลัง login = แชท** ตามที่เจ้าของสั่ง "ระบบที่อยากให้เห็นก่อนคือแชท" ·
  คนงาน/จัดซื้อซ่อนแท็บแชท เปิดมาที่ "วันนี้" · ตัวเลขบนแท็บแชทจาก `/connect/api/summary` ทุก 30 วิ · ค้นหา ชื่อ/เบอร์/เลขลีด ผ่าน `inbox?q=`):
  แชทลูกค้า (คิวรอรับ/ลูกค้าของฉัน · แอดมิน: รอรับ/มีเจ้าของ/ทั้งหมด · รีเฟรชทุก 5–10 วิ · ตอบ/รับลูกค้า ·
  **ถามยืนยันครั้งแรกก่อนตอบลูกค้าจริงในแต่ละแชท**) · สแกน QR → หน้ารถ → เปลี่ยนสเตป (ปุ่มตามบทบาท แยกเฟส ·
  ถ่าย/เลือกรูป อัปทันทีเข้า `/track/api/upload` · เช็คลิสต์ตรวจรถรูปแบบเดียวกับเว็บ `[ตรวจรถ] ❌/✅`)
  → `POST /track/api/seller_set_stage` (ตั้งชื่อไฟล์ใน Drive ให้) · คนงาน (`position=worker`) ไม่เห็นเมนูแชท
  · **เช็ค "ต้องใส่หมายเหตุ" ในแอปก่อนต่อผลเช็คลิสต์** (เซิร์ฟเวอร์เห็นแค่ข้อความรวม — ต่อก่อนเช็ค = ผ่านโดยไม่พิมพ์อะไร)
- **★ 11 ต.ค.69 หน้ารวมแชท**: ตัวกรองลัด + ขั้นในรายชื่อ · ป้ายขั้น/ความร้อน/นัด/เงียบ/รถตรง · ~~Run Auto~~ (ถอดแล้ว — อยู่ห้องพัก Lead บนเว็บ) · กระดิ่ง → `src/app/alerts.tsx` ·
  หน้า **งาน/นัด** `src/app/lead/[id].tsx` (ขั้น · นัด · โทร + รูปหลักฐาน · สรุป + AI ร่าง · ใครเคยดูแล · คืนกองกลาง) · ของใช้ร่วม `src/lib/crm.tsx`
  · ตัวกรองจากหน้าแจ้งเตือนส่งผ่าน param `preset` (ปรับ state ตอน render ไม่ใช้ effect — กฎ lint ของ React) · ดู section "หน้ารวมแชท"
- **★ 11 ต.ค.69 รูปที่ลูกค้าส่งขึ้นในแชทแล้ว** — `<Image source={{uri, headers: authHeaders()}}>` (ลิงก์ `/connect/api/media` ต้องแนบ token ·
  `authHeaders()` ใน `src/lib/api.ts`) · แตะรูป = ดูเต็มจอ · ~~วิดีโอ/เสียง/ไฟล์อื่น = บอกให้เปิดในหน้าเว็บ~~ (13 ต.ค.69 เปิดในแอปได้แล้ว — ดูข้อถัดไป)
- **★ 13 ต.ค.69 — 3 อย่างที่เคยต้องไปทำในหน้าเว็บ ทำในแอปได้แล้ว** (ไม่มี API ใหม่ · ไม่มี migration · ใช้ endpoint เดิมของเว็บผ่าน Bearer)
  - **วิดีโอ/ข้อความเสียง/ไฟล์ที่ลูกค้าส่ง** (`src/lib/files.tsx`) — แตะ = โหลดลงเครื่องก่อน (`expo-file-system`
    `File.downloadFileAsync` + header token · โฟลเดอร์ `cache/chat-files/` ชื่อไฟล์ = id ในระบบ `m=l123.0` · โหลดซ้ำไม่ยิงเน็ต) แล้ว
    วิดีโอ/เสียง = เล่นในแอป (`expo-video` · ไฟล์ในเครื่อง ไม่ต้องพึ่ง Range ของเซิร์ฟเวอร์) · ไฟล์อื่น = หน้าแชร์ของเครื่อง (`expo-sharing`)
    · เซิร์ฟเวอร์ตอบ error เป็น JSON แล้วถูกเขียนลงไฟล์ = ตรวจไฟล์เล็ก <4KB ที่ขึ้นต้น `{` แล้วลบทิ้ง + บอกเหตุผล
  - **ความด่วน + ธงงานค้างของรถ** (`src/lib/carmarks.tsx` · ใต้กล่องเปลี่ยนสเตปในหน้ารถ) → `/track/api/set_priority` · `set_flags`
    · `m_car` ส่ง `priorities` + `flagDefs` (`proof` = ปลดแล้วต้องมีหลักฐาน · `done` = ชื่อตอนงานเสร็จ) · สิทธิ์ใช้ `canPriority`/`flagPerms`
    ที่มากับ `car_json` อยู่แล้ว (ช่องที่ไม่มีสิทธิ์ = สวิตช์ปิด · เซิร์ฟเวอร์ตรวจซ้ำ) · ปลด "ยังไม่ได้ถ่ายรูป" = ฟอร์มแนบรูป+หมายเหตุก่อน (สวิตช์ยังติดจนกว่าจะยืนยัน)
  - **บันทึกสถานะลูกค้า (Z) จากรายการตามด่วน** (`src/lib/leadstatus.tsx`) → `/crm/api/lead_status` ตัวเดียวกับหน้า `/crm/`
    · ตัวเลือกมากับ `follow.zOptions` (`crm_page._z_options` · เทเลเซลล์ได้ลิสต์ว่าง = ไม่มีปุ่ม เพราะ API ตอบ 400)
    · **รายการตามด่วนจำผลไว้ฝั่งเซิร์ฟเวอร์ ~1–2 นาที** (แคช 60 วิของ mobile_home + fetch_all_sheets ต่อ worker) → แอปจำค่าที่เพิ่งบันทึกไว้ 10 นาที
      (`shownStatus` · ป้าย "✓ บันทึกแล้ว") กันโชว์ค่าเก่าแล้วนึกว่าไม่ติด · ล้างตอนออกจากระบบ (`clearHome` → `clearSavedStatus`)
    · **⚠️ ใช้ได้หลัง deploy commit `86dcd92` ขึ้นไป** (ที่มี `/crm/api/lead_status`)
  - แพ็กเกจใหม่ `expo-file-system` · `expo-video` · `expo-sharing` (+ `expo-font` ที่ expo-doctor ฟ้องว่าเป็น peer ของ vector-icons) — **มีใน Expo Go อยู่แล้ว ไม่ต้อง build เอง**
  - **⚠️ กฎ lint ของ React compiler**: แก้ตัวแปรระดับโมดูล / เรียก `Date.now()` ใน handler ที่ประกาศในคอมโพเนนต์ = error →
    ย้ายไปเป็นฟังก์ชันระดับโมดูล (`remember()` ใน leadstatus.tsx)
  - **ยังไม่ได้ลองบน iPhone จริง** — ผ่าน `tsc` + `expo lint` + `expo-doctor` 21/21 + bundle iOS + เทสต์ฝั่งเซิร์ฟเวอร์
- **★★ 16 ต.ค.69 — แชทแบบแอปทั่วไป + ฝั่งเซิร์ฟเวอร์ [checkout/chatplus.py](checkout/chatplus.py)** (เจ้าของ "ทำตามที่แนะนำ ทั้งฟังก์ชันหลัก ฟังก์ชันรอง · UI ตามเว็บชาวบ้าน")
  - **กันส่งซ้ำ `client_id`** — `reply` / `reply_image` รับ `client_id` (แอปส่งแบบขึ้นข้อความทันที แล้วลองซ้ำเมื่อเน็ตหลุด)
    · ล็อกเป็นแถวใน `dash_kv` key `reply_cid:<ChatOwner.id>:<client_id>` (ใช้ร่วมทุก gunicorn worker) · ส่งสำเร็จ = จดแถวแชท ·
    **ส่งซ้ำ client_id เดิม = คืนข้อความเดิม (`dup: true`) ไม่ยิง LINE อีก** · ส่งล้ม = ปลดล็อก (กดส่งอีกครั้งได้) · รอบก่อนยังส่งอยู่ = 409 ·
    ล็อกค้างเกิน 90 วิ (worker ตายกลางทาง) = รับช่วงต่อ · ล็อกเก่าเกิน 2 วันกวาดทิ้ง · ไม่ส่ง client_id (หน้าเว็บเดิม) = ทำงานเหมือนเดิม
    · `reply` คืนข้อความรูปแบบเดียวกับ `messages()` แล้ว (มี `id` `l<pk>`/`f<pk>`)
  - **ส่งรูปหาลูกค้า `POST /connect/api/reply_image` (multipart `id, file, client_id`)** — สิทธิ์/สวิตช์ล็อก/ลูกค้าจำลอง กติกาเดียวกับตอบข้อความ
    · **★ 17 ต.ค.69 หน้าเว็บ Connect ส่งรูปได้แล้ว** (`connect.html` `pickImg/sendImg`): ปุ่มรูปซ้ายช่องพิมพ์ · วางรูป Ctrl+V
      (คลิปบอร์ดมีข้อความติดมา = วางเป็นข้อความตามเดิม) · ลากไฟล์มาวางในช่องแชท → **โชว์ตัวอย่างก่อน กด "ส่งรูป" เอง** (ช่องพิมพ์ว่าง + Enter = ส่งรูป)
      · client_id เดิมทั้งรอบ = เน็ตหลุดแล้วกดส่งอีกครั้ง ลูกค้าไม่ได้รูปเบิ้ล · `connect_classic.html` (`?classic=1`) ไม่ได้ทำ
    · Pillow ย่อด้านยาว ≤2048 + รูปตัวอย่าง 640 (LINE บังคับ ≤1MB) · **หมุนตาม EXIF แล้วตัด EXIF ทิ้ง (พิกัด GPS ในรูปห้ามหลุดถึงลูกค้า)** · รับเฉพาะรูป
    · LINE/Facebook ต้องดึงรูปจากลิงก์ https สาธารณะ → สำเนาที่ **`MEDIA_ROOT/chat_out/<uuid>.jpg`** (ชื่อสุ่มเดาไม่ได้ · ไม่ใช่ `private_media`)
      · ลบเองเมื่อเกิน `CUSTOMER_CHAT_KEEP_DAYS` (60) วันละครั้งจาก `connect.tick` · `SITE_URL` ไม่ใช่ https = ปฏิเสธ (ยกเว้นลูกค้าจำลอง)
    · บันทึก `GroupChat`/`FbChat` ขาออก `msg_type=image` `text="[รูป]"` `extra.out_file` **เฉพาะตอนส่งสำเร็จ** · ส่งล้ม = ลบไฟล์ทิ้ง
    · `connect._files` ข้อความขาออกที่มี `out_file` = ลิงก์ `/media/chat_out/…` ตรง (ไม่ผ่าน `/connect/api/media`)
  - **ข้อความสำเร็จรูป `GET/POST /connect/api/canned`** — KV `connect_canned` · ทุกคนที่เข้า Connect ได้เห็น · `{action: save|delete}` แอดมินเท่านั้น ·
    สูงสุด 60 ข้อความ · หัวข้อ ≤40 · ข้อความ ≤1000 · แก้ในแอป (แท็บ "ฉัน" → ข้อความสำเร็จรูป) หรือในหน้าเว็บ
    · **★ 17 ต.ค.69 หน้าเว็บ Connect มีปุ่มข้อความสำเร็จรูปแล้ว** (`connect.html` `cndToggle/paintCnd`): ปุ่มข้างปุ่มรูป → กล่องลอยเหนือช่องพิมพ์ ·
      เลือกแล้วต่อท้ายช่องพิมพ์ (ไม่ส่งเอง) · เกิน 5 ข้อความมีช่องค้น (Enter = ใช้อันแรก) · แอดมินเพิ่ม/แก้/ลบในกล่องเดียวกัน ·
      Esc / คลิกที่อื่น = ปิด (ยกเว้นกำลังแก้) · ดึงรายการใหม่ทุกครั้งที่เปิด (แก้จากแอปแล้วเห็นทันที)
  - **`inbox` ทุกแถวมี `unreadCount`** (`chatplus.unread_counts` · นับเฉพาะแถวที่ยังไม่อ่าน · เพดาน 99 · ยังไม่อ่าน = อย่างน้อย 1)
  - **`chat` เพิ่ม `sellers`** (แอดมิน · เมนูโอนลูกค้า) + **`claimWhy`** (ดูตัวอย่างคิวแต่กดรับไม่ได้ เพราะอะไร)
  - ไม่มี migration · **เทสต์ `python scripts/test_chatplus.py` (52 ข้อ · ปลอมแค่ `requests`)** — ลองถอดตัวกันส่งซ้ำแล้วล้ม 5 ข้อ (จับได้จริง)
    · `test_connect` 732/732 · `test_crm` 145/145 · `test_mobile_api` 76/76 · `test_chat_media` 131/131 (ต้องมี zxing-cpp)
  - **ฝั่งแอป** (โปรเจกต์ OxletautoMobile): ส่งทันที+ส่งอีกครั้ง · ส่งรูป · ข้อความสำเร็จรูป · ป้ายคั่นวัน · รวมกลุ่มข้อความ · กดค้าง=คัดลอก/โทร ·
    ปุ่มลงล่างสุด · ร่างต่อแชท · เมนูสามจุด (งาน/นัด · ไม่ต้องตอบ · โอน · คืนกองกลาง) · ไทม์ไลน์รวมในหน้างานกับลูกค้า · toast · หน้าโหลดไม่ได้มีปุ่มลองใหม่ ·
    แถบเชื่อมต่อไม่ได้ · หยุดดึงตอนแอปอยู่เบื้องหลัง · ไอคอนแทนอิโมจิ · **ขนาดตัวหนังสือ 3 ระดับ** · **ภาษา ไทย/อังกฤษ/พม่า/เขมร สำหรับหน้าคนงาน**
    (ชื่อสเตปคัดจาก `templates/scan.html` `STAGE_I18N` — แก้ชื่อสเตปต้องแก้แอปด้วย `src/lib/i18n.ts`) · ดู README ของแอป
- **★★ 11 ต.ค.69 — เอาหน้าจอของต้นแบบมาใส่ข้อมูลจริง** (*"อยากให้คุณเอาข้อมูลจริงลงในหน้าแอปเลย"* — ต้นแบบใช้ข้อมูลสมมติ)
  - **แท็บตามบทบาท** (`(tabs)/_layout.tsx` · บทบาทจาก `me.role` ของ `/api/m/me` · ของที่จำไว้รุ่นเก่าไม่มี role → `roleOf()` เดาจากตำแหน่ง):
    เซลล์ **แชท · วันนี้ · รถ · ฉัน** · แอดมิน **แชท · ภาพรวม · ห้องพัก · รถ · ฉัน** · คนงาน **งานวันนี้ · รถ · ฉัน** · จัดซื้อ **วันนี้ · รถ · ฉัน**
    · **login แล้วยังเปิดมาที่แชท** (เจ้าของสั่ง 9 ต.ค.) — ต้นแบบวาง "วันนี้" ไว้แรก ถ้าจะสลับ แก้ลำดับ `Tabs.Screen` + Redirect ใน `(tabs)/index.tsx`
    · **สแกน QR ย้ายจากแท็บมาเป็นหน้าซ้อน `app/scan.tsx`** (ปุ่มบนแท็บ "รถ" + หน้า "งานวันนี้" ของคนงาน) · จัดซื้อไม่มีแท็บแชท (`canChat`)
  - **`GET /api/m/home`** ([mobile_home.py](dashboard/services/mobile_home.py)) — **ไม่มีสูตรใหม่สักตัว** ประกอบจากตัวเดียวกับเว็บ/LINE:
    ตามด่วน+ดีลค้าง = `fetch_dashboard.seller_followups` · ยอดเดือน = `monthlySummary` ที่ cron อุ่นไว้ · คะแนน = `compute_diligence_scores` ·
    ใบจ่ายลีด = `leadflow.seller_tasks` · งานจัดซื้อ = `purchase_page.summary` · เช็คชื่อ = `CheckIn` (ของตัวเอง `checkin` · แอดมินทั้งบริษัท `staff`
    — "ยังไม่มา" นับเฉพาะคนที่**เลยเวลาเข้างานของตัวเองแล้ว**) · คิวรถคนงาน = รถในสเตปที่ `STAGE_OWNER` เป็นทีมเขา (เรียงแบบบอร์ด) · รถที่ฉันเบิก = `CarMovement` ค้างของชื่อเล่นฉัน
    · **ทุกส่วนห่อ try แยก** (พัง = `errors[<ส่วน>]` · ส่วนอื่นยังมา) · จำผลส่วนหนัก 60 วิ/process
  - **★ แยกสมอง "ตามด่วน" ออกจาก `build_followup_messages` เป็นฟังก์ชันระดับโมดูล** (`fu_idle/fu_cadence/fu_skip/fu_booked/fu_urgency/
    fu_reason/fu_stuck/fu_collect/fu_rank` · `FU_WINDOW_DAYS`=14) → แอปกับข้อความ LINE ใช้สูตรเดียว · **ตรวจกับชีตจริงแล้ว: ข้อความ LINE
    ทั้ง 13 ข้อความเหมือนเดิมทุกตัวอักษร** + ลำดับลีดของ `seller_followups` ตรงกับข้อความของเซลล์คนนั้น · แก้สูตร = แก้ที่ฟังก์ชันเหล่านี้ที่เดียว
  - **ตามด่วนโหลดแยกคำขอ** (`?lazy=1` แล้ว `?part=follow`) — ต้องอ่านชีตลีดทั้งก้อน (`fetch_all_sheets` จำแค่ 60 วิต่อ worker · เย็น ~8 วิบน VPS)
    หน้าจอขึ้นส่วนอื่นทันที · ตอนรีเฟรชทุก 60 วิโชว์ตามด่วนรอบก่อนไว้ (ไม่กะพริบ) · วัดจริง: อุ่นแล้ว 0.04–3 วิ
  - **ห้องพัก Lead (แอดมิน · `(tabs)/hub.tsx`)** = `inbox?view=tocode` ตัวเดียวกับเว็บ · กดชื่อเซลล์ = `assign_lead`/`park_assign` เดิม
    (ปุ่มแรก = คิวถัดไป) · **ถามยืนยันทุกครั้งก่อนส่งใบเข้ากลุ่ม** + **เบอร์ซ้ำถามอีกชั้น** (เหมือนเว็บ) · "ไม่ต้องจ่ายเบอร์" · จ่ายแล้ววันนี้
    · ไม่มี Run Auto / ตั้งเลขเอง / ไม้ 2 (ใช้เว็บ) · ป้ายแท็บ = `summary.counts.tocode + parked` (**`/connect/api/summary` ของแอดมินเพิ่ม `parked`**)
  - **รถ (`(tabs)/cars.tsx`)** = `/track/api/cars` · ค้นหา · กรอง พร้อมขาย/ค้างนาน/ออกนอกลาน/ฉันเบิกอยู่/รายเฟส · **`cars_api` เพิ่ม `out`
    ต่อคัน** (`{who, purpose, mine, since}` — ชื่อเล่นเท่านั้น · เว็บไม่ได้ใช้ ไม่กระทบบอร์ด)
  - **เบิก-คืนรถในหน้ารถ** (`src/lib/checkout.tsx`) = `/checkout/api/car_out` · `car_return` เดิม · รูปขั้นต่ำ + ติ๊กมุม
    (ไม่ครบยังบันทึกได้ กติกาเดียวกับเว็บ) · คืนรถแทนคนอื่นถามก่อน · ตัวอัปโหลดรูปย้ายมา `src/lib/media.tsx` ใช้ร่วมกับเปลี่ยนสเตป
  - **ฉัน** = เช็คชื่อวันนี้ + คะแนนแยก 6 ด้าน (เซลล์) · **ออกจากระบบ/หมดเวลา = ล้างข้อมูลหน้า "วันนี้" ในเครื่อง** (`clearHome` — เครื่องเดียวใช้หลายคน)
  - **เช็คชื่อด้วยเซลฟี่+พิกัดแบบในต้นแบบ ไม่ได้ทำ** — ระบบจริงเช็คชื่อด้วยรูปในกลุ่ม LINE ผ่าน n8n (แอปแค่โชว์ผล)
  - **เทสต์**: `python scripts/test_mobile_home.py` (73 ข้อ · [3c] สถานะลูกค้าผ่าน token · test client จริง · ปลอมแค่ชีต/ผลแดชบอร์ด) — ตามด่วน/ดีลค้าง/ใบจ่ายลีดไม่มีของคนอื่น ·
    ปุ่มเปิดแชทเฉพาะแชทของตัวเอง · เช็คชื่อ (สาย X นาที · ยังไม่ถึงเวลา/วันหยุด/ผู้บริหารไม่นับ) · คิวรถตามบทบาท · จัดซื้อเห็นเฉพาะของตัวเอง ·
    ส่วนหนึ่งพังไม่ลากทั้งหน้า · **ไม่มี LINE user id หลุด** · `seller_today` เดิมยังได้ผลเดิม · แอป `tsc` + `expo lint` + bundle iOS ผ่าน
- **★ 18 ต.ค.69 — กราฟทีมจัดซื้อ (เจ้าของ "ทำหน้ากราฟให้จัดซื้อด้วย")** — `mobile_charts.build_buyer` · GET `/api/m/charts` (จัดซื้อ = ของตัวเองเสมอ ·
  แอดมิน `?mode=buy` = ทั้งทีม · เซลล์ส่ง `mode=buy` ไม่มีผล) · **ตัวเลขชุดเดียวกับ 2 การ์ดในแดชบอร์ด** ("ฝั่งจัดซื้อ (รับซื้อรถ)" + "รถซื้อเข้า รายคน")
  ไม่มีสูตรใหม่: ลีดรับซื้อ/รับซื้อ/ไม่รับซื้อ (`purchaseLeads`) · รถซื้อเข้า (`boughtCars`) · หมวดวิธีได้รถ (`buy_cat` = `_catOf` ของเว็บ + map ที่แอดมินตั้ง) ·
  เป้า (`purchaseTargets` × เดือนในช่วง · ไม่เคยตั้ง = `PURCHASE_TARGETS_DEFAULT`) · % รับซื้อ = รับซื้อ ÷ ลีดทั้งหมด (แบบคอลัมน์ในเว็บ) ·
  กรองช่วงแบบเว็บ (ไม่รู้วัน = นับถ้าเดือนอยู่ในช่วง แต่ไม่ลงกราฟรายวัน) · อันดับ = รถซื้อเข้า/เป้า ของทุกคนในทีม (ชื่อ+ตัวเลข ไม่มีข้อมูลลูกค้า)
  · แอป (`lib/charts.tsx` `BuyCharts`/`AdminCharts`): ตัวเลข 4 ช่อง (ลีดรับซื้อ + รอตัดสิน · รับซื้อ % · ไม่รับซื้อ · ซื้อเข้า/เป้า) +
  กราฟสลับ ลีด/ซื้อเข้า/วิธีได้รถ (แถบเทียบเป้า)/ช่องทาง (แถบ + คุณภาพ) + อันดับ · จัดซื้อเห็นบนสุดของหน้า "วันนี้" · แอดมินมีปุ่มสลับ **ฝ่ายขาย / จัดซื้อ** บนหน้าภาพรวม
  · ⚠️ ช่อง "รับซื้อ/ไม่รับซื้อ" (K) ทีมเว้นว่างเกือบทั้งหมด → % รับซื้อต่ำ + "รอตัดสิน" สูง เป็นข้อมูลจริง ไม่ใช่บั๊ก
- **ยังไม่มี**: push แจ้งเตือน · ส่งรูปหาลูกค้า · Run Auto/ไม้ 2/ตั้งเลขเอง ในห้องพัก (ใช้เว็บ) · หน้าแบบ `/crm/` (ไปป์ไลน์/รายงาน)
- **ต้นแบบ + วิดีโอสอน** (9 ต.ค.69 · **ย้ายออกจากโปรเจกต์แล้ว 10 ต.ค.69** → `Downloads/oxlet-mobile-prototype/` เครื่องผู้พัฒนา · ต้นแบบ https://claude.ai/artifact/XEmbwUNwLcbPEz2fj1iADH · คู่มือวิดีโอมีเสียงพากย์ https://claude.ai/artifact/9Rrspbmts7eZV1GGsKHoec): ต้นแบบ HTML 4 บทบาท (ข้อมูลสมมติ) + หัวข้อทรัพยากร/ค่าใช้จ่าย (50–60 คน: เซิร์ฟเวอร์เดิมพอ · ปีแรก ~4,400 บาท) · วิดีโอสอนเซลล์/แอดมิน (Playwright + เสียงพากย์ — ชุดแรกทำด้วย Gemini TTS · **10 ต.ค.69 ห้ามใช้ API พากย์เสียงแล้ว** `tts.py` เปลี่ยนเป็นเสียง Windows ออฟไลน์ "Microsoft Pattara") · **ข้อค้นพบจากการวัด: nginx ไม่บีบอัด JSON (`gzip_types` ถูกคอมเมนต์ไว้ = บีบแค่ HTML)** · worker 5 ตัวตึงตอนอัปรูปพร้อมกัน 8 โมง
- **เทสต์**: `python scripts/test_mobile_api.py` (76 ข้อ · รวมความด่วน/ธงผ่าน token · test client จริงทั้งสาย middleware · ปลอมแค่ชีตพนักงาน)
  · แอป (ในโฟลเดอร์ OxletautoMobile): `npx tsc --noEmit && npx expo lint && npx expo-doctor` (ผ่านหมด · bundle iOS ผ่าน)
- **⚠️ `npx expo lint` ครั้งแรกติด peer dependency** (npm ดึง react-dom 19.3 ที่ไม่ตรง react 19.2.3) →
  ติดตั้ง eslint เองด้วย `--legacy-peer-deps` แล้ว (อยู่ใน devDependencies แล้ว)

### 🧭 Oxlet CRM (`/crm/`) — หน้าใหม่แยกตามแบบ "Oxlet CRM.html" · 13 ต.ค.69
ผู้ใช้ส่งไฟล์แบบหน้าจอ (Claude Design · 5 หน้า ข้อมูลสมมติ) แล้วสั่ง "ปรับระบบตามนี้" → เลือก **ทำเป็นหน้าใหม่แยก** (ไม่แตะ /me/ · /connect/ · /dashboard/)
และไปป์ไลน์ใช้ **"แชท + ลีดจากชีต"** · ไฟล์: [crm_views.py](dashboard/crm_views.py) · [services/crm_page.py](dashboard/services/crm_page.py) ·
[crm.html](dashboard/templates/dashboard/crm.html) (**CSS/JS ฝังในหน้า — ไม่ต้อง collectstatic** · ไม่มี migration)
- **6 เมนู** (แถบซ้ายสีม่วงเข้ม · จอ ≤900px เป็นแถบบน) — แดชบอร์ด · ไปป์ไลน์ลีด · ลูกค้า · แชทลูกค้า (iframe `/connect/?embed=1`) ·
  สต็อกรถ (`/track/api/cars` · พร้อมขาย/จอง/ทำสภาพ) · รายงาน · ธีมสว่างเป็นค่าเริ่มต้น สลับเข้มได้ (คีย์ `oxlet_theme` ชุดเดียวกับหน้าอื่น)
- **ไม่มีสูตรนับใหม่** (ตัวเลขตรงกับหน้าเซลล์/ข้อความ LINE): ยอดไตรมาส/เดือน/รายวัน = `fetch_seller_stats` · ผู้ช่วย "เสี่ยงหลุด" = `mobile_home._follow`
  (สูตรตามด่วน) · นาฬิกาโทร = `mobile_home._tasks` (`leadflow.seller_tasks`) · ขั้น/ความร้อนลูกค้าแชท = `crm.stage_of/heat_of` ·
  เป้าทีม/อันดับ = `monthlySummary`/`dailyBySeller` ที่ cron อุ่นไว้ (ส่งแค่ชื่อ+ตัวเลข — ข้อยกเว้นเดียวกับตารางคะแนน)
- **ไปป์ไลน์ 5 คอลัมน์** ลีดใหม่ · ติดต่อแล้ว · นัดดูรถ · ยื่นไฟแนนซ์ · จอง/ปิดการขาย (`COLS`)
  · **ลูกค้าแชท** = ขั้นใน Connect (`CHAT_COL`) · **ลากได้** → `POST /connect/api/crm {action:"stage"}` ตัวเดิม (`COL_STAGE` · คอลัมน์ลีดใหม่ = "รอติดต่อ")
  · **ลีดจากชีต** (`PIPE_DAYS`=60 วัน) วางตาม `sheet_stage()` — `fu_booked` → จอง (**เช็คก่อน** fu_skip เพราะ "ส่งมอบ" อยู่ในคำไม่ต้องตามด้วย) ·
    `fu_skip` = ไม่อยู่บนกระดาน · Z "รอเช็คเครดิต" = ยื่นไฟแนนซ์ · Z "รอมาดูรถ" = นัดดูรถ · ไม่มี Z + ไม่เคยอัปเดต = ลีดใหม่ · นอกนั้น = ติดต่อแล้ว
    · **ลากไม่ได้** → กดแล้วเลือกสถานะ Z ในหน้าลูกค้า → `POST /crm/api/lead_status` (คืนคอลัมน์ใหม่จาก `sheet_stage` ฝั่งเซิร์ฟเวอร์ — หน้าเว็บไม่มีสูตรของตัวเอง)
  · **เคสจองที่ยังไม่ปล่อย** (ชีตยอดขาย · จองไม่เกิน `DEAL_DAYS`=90 วัน) อยู่คอลัมน์จอง · ลีดที่มีเคสจองแล้วไม่ขึ้นซ้ำ (ใบเคสจองแทน)
  · ลูกค้าแชทที่มีเลขลีดตรงกับลีดในชีต = ใบแชทใบเดียว (ใบแชทชนะเพราะลากได้)
- **หน้าลูกค้า** = ลูกค้าแชท + ลีดจากชีต `CUST_DAYS`=90 วัน · **เคสเสีย/คืนเคสที่เก่ากว่า `DEAD_DAYS`=14 วันไม่ส่ง** (บอกเป็นจำนวน — ~90% ของลีดเป็นแบบนี้ · ทั้งปีหนัก ~600 KB)
  · แผงขวา (ไม่ใช่หน้าต่างลอย): ลูกค้าแชท = `/crm/api/customer` (ขั้น · นัด · บันทึกการโทร ผ่าน `/connect/api/crm` ตัวเดิม · ประวัติไม่รวมการตอบ ·
    **ไม่แตะ `read_at`** — ดูโปรไฟล์ไม่ใช่อ่านแชท) · ลีดจากชีต = เลือกสถานะ Z · เคสจอง = อ่านอย่างเดียว
- **รายงาน** 30 วัน / 90 วัน / ปีนี้ คิดฝั่งเซิร์ฟเวอร์ (`report()`): ยอดปล่อย · ปล่อยรถ · จองถึงปล่อยเฉลี่ย · ลีด→ปล่อย (เทียบช่วงก่อน · **ปีนี้ไม่มีช่วงก่อน**
  เพราะแดชบอร์ดเก็บปีเดียว · ช่วงที่คร่อมข้ามปีถูกตัดที่ต้นปี) · กรวย = ลีดปกติที่รับในช่วงนั้นไปถึงขั้นไหน (นัด/ไฟแนนซ์อ่านจาก Z — ไม่กรอก = ไม่ถูกนับ) ·
  ช่องทางเคสปล่อย = `_done_channels()` (เรียก `_attach_clean_channel` ตัวเทียบเดียวกับตาราง Lead → จอง → จบ) · อันดับเซลล์
- **สิ่งที่แบบมีแต่ไม่ได้ทำ (ข้อมูลไม่มีจริง)**: เส้น "ปีก่อน" · ปุ่ม "นำเข้าลีด"/"ลีดใหม่" (ไม่มีขั้นตอนให้เซลล์สร้างลีดเอง — เปลี่ยนเป็น "เช็คเบอร์ซ้ำ"/"เปิดไปป์ไลน์") ·
  ตัวกรอง "ปิดได้ใน 30 วัน" (ไม่มีข้อมูลคาดการณ์ → ใช้ "ยังไม่โทร/รอเราตอบ" · "มีนัด" แทน) · "มูลค่าคาดการณ์" (ใช้ "ดีลกำลังเดินเดือนนี้" = pipelineValue แทน) ·
  ปุ่มรายงานผลบนนาฬิกาโทร (รายงานยังทำในห้องจ่ายเบอร์ — หน้าเว็บบอกวิธี)
- **แชท = Connect ของบัญชีที่ login** — แอดมินที่เลือกดูเซลล์คนอื่นจะเห็นแชททุกคน (ไม่ได้กรองตามเซลล์ที่เลือก · หน้าเว็บเขียนบอก)
- **เทสต์**: `python scripts/test_crm_page.py` (66 ข้อ · test client จริง + CSRF จริง · ปลอมแค่ชีต/ผลแดชบอร์ด) — สิทธิ์ทุกบทบาท · ไม่มีลีด/แชทของคนอื่นหลุด ·
  ไม่มี LINE id · คอลัมน์ของลีดจากชีต · เขียน Z เฉพาะแถวของตัวเอง · CSRF · ไม่แตะ read_at · ลากการ์ดของคนอื่นไม่ได้ · บั๊กวันที่ "d/m" · บั๊ก /me/
  · ตรวจ UI ด้วย Chromium จริง (template ตัวจริง + ข้อมูลชีตจริง · ลากการ์ดแล้ว POST ถูกตัว · ตั้งนัด/บันทึก Z/ไม่สนใจ+เหตุผล · จอ 1590/1180/390 ไม่ล้นจอ · ไม่มี JS error)
- **⚠️ เครื่อง dev**: ตั้งค่าเซลล์ในฐานข้อมูลทดสอบ (SQLite) มีชื่อปลอม (`TEAMS={"C":["เดลต้า"]}`) → ทีม/เป้า/อันดับในเครื่องว่าง ไม่ใช่บั๊ก (บนเซิร์ฟเวอร์อ่านจากชีต)

### 🔖 ป้ายเวอร์ชันมุมขวาล่าง (ส.ค.69)
ทุกหน้า (login/index/seller/track base) โชว์เวอร์ชันมุมขวาล่าง — **สูตร: จำนวน git commit ÷ 10** (100 commits = v10.0 · เจ้าของกำหนด) · `app_version()` ใน [cars/context.py](cars/context.py) (git rev-list --count HEAD · cache ต่อ process · ไม่มี .git = ป้ายซ่อน) → `APP_VERSION` ผ่าน context processor `cars.context.nav` · ใช้เช็คว่า deploy ล่าสุดติดหรือยัง (ดูได้ตั้งแต่หน้า login)

## Known issues / limitations

- **★ 14 ต.ค.69 แท็บที่เปิดค้างไว้ = ตัวเลขค้าง → ตอนนี้อัปเดตเอง (`_liveData` ใน index.html + seller.html)** — ข้อมูลแดชบอร์ด (`const D`)
  ฝังมากับหน้าตอนเปิดครั้งเดียว แต่ตัวกรองวันที่/ตัวหาร "ต่อวัน" ใช้วันนี้ → เจ้าของเจอเครื่องหนึ่งโชว์ "1–14 ต.ค." ลีด 485/RJ 244
  ทั้งที่จริง 890/417 (ตรงกับชีต ณ เช้า 8 ต.ค. เกือบทุกคน = แท็บเปิดค้างตั้งแต่วันนั้น)
  · **ไม่ให้ผู้ใช้กดเอง** (เจ้าของสั่ง — รอบแรกผมทำแถบ "โหลดข้อมูลใหม่" แล้วโดนตีกลับ)
  · แอดมิน: ถาม `/api/dashboard?since=<meta.generatedAt>` ทุก 5 นาทีเฉพาะตอนเปิดดู + ทันทีที่กลับมาที่แท็บ · ไม่เปลี่ยน = คำตอบ ~70 ไบต์
    · เปลี่ยน = ข้อมูลทั้งก้อน (~3.3 MB · `@gzip_page` บีบให้) → แทนที่ D (คง `onhand/onhandMeta/sellerFlags` ที่มากับหน้าเท่านั้น) +
    ล้าง `_rmCache` → `render()` ที่ตำแหน่งเลื่อนเดิม
  · เซลล์: `/s/<token>/?format=json&h=<D._hash>` (ผ่านด่านสิทธิ์เดียวกับหน้า · `_hash` = md5 ของข้อมูลไม่รวม meta) ทุก 10 นาที
  · **ไม่วาดทับ** ตอนเปิดหน้าต่าง/พาเนล (`-overlay`/`-ov`/`?panel=`/เมนูเปิด) หรือ **เพิ่งพิมพ์/คลิกในช่องภายใน 2 นาที** → เก็บไว้ วาดตอนว่าง
    · ⚠️ ห้ามนับ "ช่องที่โฟกัสค้าง" เป็นยุ่งตลอด — ช่องวันที่ดึงโฟกัสกลับเองหลังเลือกวัน คนเลือกวันแล้วเปิดค้างจะไม่ได้ข้อมูลใหม่อีกเลย (เจอตอนทดสอบ)
  · หน้าที่มีกรอบฝัง (Connect/สถานะรถ/เบิก-คืน/หน้าเซลล์ในแท็บแอดมิน · หน้าแชท/รถ/ฟอร์มสินเชื่อในหน้าเซลล์) = แทนที่ D เงียบๆ ไม่วาดใหม่
  · เซิร์ฟเวอร์เองไม่ได้ดึงชีตใหม่เกิน 30 นาที = แถบแจ้ง (ไม่มีปุ่ม — โหลดซ้ำก็ไม่ช่วย ต้องดูว่า cron หยุดไหม)
  · ⚠️ dev ไม่มี cron → ผล precompute ใน SQLite ค้างตลอด แถบนี้จะขึ้นเสมอในเครื่อง dev (ถูกต้อง)

- **Cold start ช้า** บน Vercel — request แรกหลังนิ่งนาน ~5-10s (pip install + Django boot + auth) · **หน้าสแกน /track/scan/ ก็โดน** — คนงานยืนหน้ารถอาจรอ ~10s (trade-off ของการอยู่บน serverless)
- **Sheets API quota** — ปกติ dashboard อ่าน **mirror/pre-compute (Supabase) ไม่แตะ Sheet** · Sheet ถูกอ่านแค่ตอน sync (~15-20 req ทุก ~5 นาที — ต่ำกว่า 300/min/project มาก)
- **leads upsert ใหญ่** — 15k แถวเป็น jsonb ก้อนเดียว เคยชน Supabase statement timeout (8s) · บรรเทาด้วย `_trim_row` · ถ้ายังชนบ่อย → `alter role service_role set statement_timeout='30s'`
- **Schedule precision = 1 นาที** (ตาม cron interval)
- **No deduplication** — ถ้า n8n ยิง 2 ครั้งใน 1 นาที (rare) จะส่ง Flex 2 ครั้ง
- **Vercel Hobby** = 1 cron job/วัน (ใช้ external n8n แทน)
- **เซลล์ใหม่** ที่เพิ่มผ่าน 🎯 ตั้งเป้า/ทีม จะใช้งานได้ทันที **ยกเว้น URL `/s/<token>/`** ที่ต้อง add token เองใน code
