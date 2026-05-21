# Oxlet Sales Dashboard

Django web app สำหรับติดตามยอดขาย / Lead / Live ของทีมเซลล์ Oxlet
ดึงข้อมูลทั้งหมดจาก Google Sheets แบบ real-time (ไม่มี local DB)
UI ภาษาไทย, timezone Asia/Bangkok, deploy บน Vercel

> 📘 รายละเอียดเชิงเทคนิคและการตัดสินใจออกแบบ → ดู [CLAUDE.md](CLAUDE.md)

---

## ✨ Features

- 📊 **Dashboard ผู้บริหาร / Admin** — สรุปยอดทั้งทีม, แยกตามทีม/เซลล์, รายเดือน/รายวัน, กราฟ Lead + จอง/ปล่อย + Pipeline + Deal Value
- 👤 **หน้าส่วนตัวเซลล์** (`/s/<token>/`) — เซลล์เห็นเฉพาะเคสตัวเอง + รายการต้องโทร + filter เดือน/วัน
- 💰 **Deal Value Analytics** — มูลค่าดีลรวม per seller/team/month, line chart ยอดปล่อยรายเดือน/รายวัน
- 🚗 **Lead รถรุ่นยอดนิยม** — จัดอันดับรุ่นรถจาก lead, กดเข้าไปดูเซลล์ที่รับเคสรถนั้น (admin/exec only)
- 📋 **เคสจองทุกสถานะ** — filter ตามสถานะ/เซลล์/อายุเคส, กดเข้าไปดูรายละเอียดเต็ม (admin/exec only)
- 🎯 **ตั้งเป้า/ทีมเซลล์ใน UI** — admin แก้ผ่านปุ่มหรือใน Google Sheet ตรงๆ
- 📤 **LINE Flex Notifications** — ส่ง pipeline แต่ละเซลล์ผ่าน LINE; manual + scheduled (ผ่าน cron-job.org)
- 🎩 **Executive Overview Flex** — สรุปยอดทีมทั้งหมดให้ผู้บริหารทาง LINE (เดือนปัจจุบัน)

---

## 🧱 Stack

| Layer | Tech |
|---|---|
| Backend | Django 4.2+ (Python 3.10+) |
| Data source | Google Sheets API v4 (service account, read+write) |
| Frontend | Server-rendered Django template + vanilla JS + [Chart.js](https://chartjs.org) (CDN) |
| Auth | Signed-cookie session (admin) + URL token (sellers) |
| Static | [WhiteNoise](http://whitenoise.evans.io/) (in-process) |
| Notification | [LINE Messaging API](https://developers.line.biz/en/services/messaging-api/) push (Flex) |
| Hosting | [Vercel](https://vercel.com) (`@vercel/python` builder) |
| Cron | External — [cron-job.org](https://cron-job.org) ยิง webhook ทุก 1 นาที |

---

## 🚀 Quick start (Local Dev)

ต้องมี Python 3.10+ ติดตั้งไว้ก่อน

```powershell
# 1. clone repo
git clone <repo-url>
cd oxlet-dashboard-django

# 2. สร้าง virtualenv
python -m venv .venv
.venv\Scripts\activate    # หรือ source .venv/bin/activate บน mac/linux

# 3. ติดตั้ง dependencies
pip install -r requirements.txt

# 4. สร้างไฟล์ .env (ดูด้านล่าง) แล้วใส่ค่า

# 5. รัน dev server
python manage.py runserver
```

เปิด <http://localhost:8000/dashboard/> — default จะเข้าหน้า "ผู้บริหาร" โดยไม่ต้อง login
ถ้าจะใช้เครื่องมือ admin → กดปุ่ม **🔐 ADMIN** → login ด้วย user/pass จาก env

> ⚠️ ไม่ต้องรัน `python manage.py migrate` — โปรเจกต์นี้ไม่มี local database (`DATABASES = {}` ใน [oxlet/settings.py](oxlet/settings.py))

---

## 🔑 Environment Variables

สร้างไฟล์ `.env` ที่ root ของโปรเจกต์:

```env
# Django
DJANGO_SECRET_KEY=<random-string>
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Google Sheets API (service account)
GOOGLE_SERVICE_ACCOUNT_EMAIL=<svc-account>@<project>.iam.gserviceaccount.com
GOOGLE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"

# Admin login
OXLET_ADMIN_USER=admin
OXLET_ADMIN_PASSWORD=<password>

# LINE Messaging API (Channel Access Token แบบ long-lived)
LINE_CHANNEL_ACCESS_TOKEN=<channel-access-token>

# Cron security
CRON_SECRET=<random-string-สำหรับ-protect-/api/cron/*>

# Executive LINE user_ids — รับ Overview Flex (comma-separated)
EXECUTIVE_USER_IDS=Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### Setup Google Sheets API

1. สร้าง Google Cloud project + เปิดใช้งาน **Google Sheets API**
2. สร้าง Service Account → download JSON key
3. คัดลอก `client_email` ไปใส่ `GOOGLE_SERVICE_ACCOUNT_EMAIL`
4. คัดลอก `private_key` ไปใส่ `GOOGLE_PRIVATE_KEY` (escape newline เป็น `\n`)
5. แชร์ทุก Google Sheet ให้ service account email **สิทธิ์ Editor** (เพราะต้องเขียน config sheet)

### Setup LINE Messaging API

1. สร้าง Provider + Channel แบบ Messaging API ใน [LINE Developers Console](https://developers.line.biz)
2. ที่หน้า Channel → Issue Channel Access Token (long-lived) → ใส่ `LINE_CHANNEL_ACCESS_TOKEN`
3. เพิ่ม bot เป็นเพื่อนของเซลล์แต่ละคน → user_id เก็บใน employees sheet

---

## 🌐 URL Routes

### หน้าเว็บ

| URL | สิทธิ์ |
|---|---|
| `/dashboard/` | เปิดสาธารณะ (default = มุมมองผู้บริหาร) |
| `/login/` | Admin login (user/pass) |
| `/logout/` | ออกจากระบบ admin |
| `/u/<line_user_id>/` | Magic link สำหรับเซลล์ — set cookie แล้ว redirect |
| `/s/<token>/` | หน้าส่วนตัวของเซลล์ — token 6-10 หลักจาก [seller_tokens.py](dashboard/services/seller_tokens.py) |

### API endpoints

| URL | สิทธิ์ | ใช้ทำอะไร |
|---|---|---|
| `/api/dashboard` | public | JSON ทั้ง dashboard |
| `/api/auth?token=<line_uid>` | public | ตรวจ LINE user_id |
| `/api/admin/send_line` | admin | preview/ส่ง LINE Flex ทันที |
| `/api/admin/seller_config` | admin | อ่าน/บันทึก config เซลล์ |
| `/api/admin/schedule_config` | admin | อ่าน/บันทึกตารางเวลาส่ง LINE |
| `/api/cron/send_line?secret=` | public + secret | ส่ง Flex แบบ one-shot |
| `/api/cron/tick?secret=` | public + secret | trigger schedule (ยิงทุก 1 นาที) |

---

## 👥 Roles & Authentication

| Role | Login | เห็นอะไร |
|------|-------|----------|
| **Admin** | `/login/` user+pass | ทุกอย่าง + เครื่องมือจัดการ + impersonate |
| **ผู้บริหาร** | default ของ `/dashboard/` | ทุกอย่าง + impersonate (ไม่มีเครื่องมือ admin) |
| **เซลล์** | `/u/<line_uid>/` หรือ `/s/<token>/` | เฉพาะข้อมูลของตัวเอง |

ไม่ใช้ Django auth — auth ผ่าน **signed-cookie session** (ใส่ `position` ใน session) + **URL token** สำหรับเซลล์

---

## 📊 Data — Google Sheets (8 sheets)

ทุกข้อมูลอยู่ใน Google Sheets แยกตาม spreadsheet — ดูรายละเอียด ID + tab names ใน [google_sheets.py](dashboard/services/google_sheets.py) (`SHEET_CONFIG`)

- **leads** — รายการ Lead ทั้งหมด (`L` คอลัมน์ M = CAR / สูตร)
- **sales_reports** — ยอดขาย + สถานะจอง (`N` = สถานะ, `W` = วันที่ปล่อยรถ, `L` = ราคาขาย)
- **bookings** — รายการจอง
- **live_sessions** + **live_followups** — Live + คลิป
- **employees** — พนักงาน + LINE user_id
- **sellers_config** (tab "ตั้งค่าเซลล์") — เป้า/ทีม dynamic
- **schedule_config** (tab "ตั้งเวลาส่ง") — ตารางเวลาส่ง LINE อัตโนมัติ

> ⚠️ คอลัมน์ใน sales_reports เคยมีการ shift (V→W ตอน May 2026) → ดู section "Sheet column gotchas" ใน [CLAUDE.md](CLAUDE.md)

---

## 🚢 Deploy บน Vercel

1. **Push repo เข้า GitHub** (private, เพราะ commit `.env`)
2. **Import project บน Vercel** — เลือก framework "Other", root directory ว่าง
3. **ตั้ง Environment Variables** บน Vercel dashboard ใส่ทุกตัวจาก `.env` (ตามด้านบน)
   - `ALLOWED_HOSTS=your-app.vercel.app`
   - `CSRF_TRUSTED_ORIGINS=https://your-app.vercel.app`
   - `DEBUG=False`
4. **Use canonical URL** (`your-app.vercel.app`) ไม่ใช่ deployment-specific URL (`your-app-xxx.vercel.app`) เพราะอันยาวมี Vercel Auth wall
5. **Setup cron** — ไป [cron-job.org](https://cron-job.org) ตั้ง webhook:
   ```
   URL: https://your-app.vercel.app/api/cron/tick?secret=<CRON_SECRET>
   Schedule: * * * * *  (ทุก 1 นาที)
   ```
6. **แชร์ Google Sheets** ให้ service account email เป็น Editor

---

## 🔧 งานที่เจอบ่อย

| งาน | ทำยังไง |
|---|---|
| **เปลี่ยนเป้าเซลล์** | Login admin → ปุ่ม 🎯 ตั้งเป้า/ทีม → แก้ → Save (หรือแก้ใน Sheet ตรงๆ) |
| **เพิ่มเซลล์ใหม่** | ปุ่ม 🎯 → ➕ เพิ่ม → ใส่ชื่อเล่น/ทีม/เป้า → Save<br>ถ้าจะให้มี URL ส่วนตัว → เพิ่ม token ใน [seller_tokens.py](dashboard/services/seller_tokens.py) แล้ว commit + push |
| **ส่ง LINE Flex ตอนนี้** | ปุ่ม 📤 LINE Flex → tab "🚀 ส่งทันที" → เลือกเซลล์ → 📤 ส่ง |
| **ตั้งเวลาส่งอัตโนมัติ** | ปุ่ม 📤 LINE Flex → tab "📅 ตารางเวลา" → ➕ เพิ่ม → Save |
| **Debug ข้อมูลผิด** | เปิด `/api/dashboard` ดู JSON เต็ม + ตรวจ sheet column ใน `SALES_COL`/`LEADS_COL` |

---

## ⚠️ Known limitations

- **Cold start** บน Vercel ~5-10s (request แรกหลังนิ่ง)
- **Google Sheets API quota** = 60 reads/min — ทุก dashboard load = 7 reads
- **Schedule precision** = 1 นาที (ตาม cron-job.org interval)
- **No deduplication** — ถ้า cron-job.org ยิงซ้ำในนาทีเดียวกัน → Flex ซ้ำ (rare)
- **Vercel Hobby** = 1 cron job/วัน → ต้องใช้ external cron แทน
- เซลล์ใหม่ที่เพิ่มผ่าน 🎯 ตั้งเป้า/ทีม **ยกเว้น** URL `/s/<token>/` ต้อง add token เองในโค้ด

---

## 📂 โครงสร้างโปรเจกต์

```
oxlet-dashboard-django/
├── manage.py
├── vercel.json                # Vercel config
├── requirements.txt
├── .env                       # secrets (private repo)
├── CLAUDE.md                  # คู่มือเชิงเทคนิคและการตัดสินใจออกแบบ
├── oxlet/                     # Django project
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py                # Vercel entry point
└── dashboard/                 # main app
    ├── urls.py
    ├── views.py               # ทุก view + API
    ├── services/
    │   ├── constants.py       # TEAMS, TARGETS, normalize_seller
    │   ├── seller_tokens.py   # /s/<token>/ tokens
    │   ├── google_sheets.py   # auth + read + write helpers
    │   ├── fetch_dashboard.py # main aggregator
    │   ├── line_notify.py     # Flex builder + push
    │   └── helpers.py
    ├── templates/dashboard/
    │   ├── index.html         # หน้า dashboard หลัก
    │   ├── login.html
    │   ├── magic_link.html
    │   └── seller.html        # หน้าส่วนตัวเซลล์
    └── static/dashboard/      # CSS + image
```

---

## 📝 License

Internal use — Oxlet Sales Team
