# ย้าย Oxlet Dashboard จาก Vercel → Hostinger VPS

คู่มือนี้ตั้งค่า VPS (Ubuntu) ให้รันแอป Django ตัวเดิมแบบถาวร:
Python venv → gunicorn → nginx (reverse proxy + SSL) → systemd (กัน process ตาย) →
Postgres ในเครื่อง (ระบบติดตามรถ cars/) → crontab ในเครื่อง (แทน n8n)

> สมมติ: VPS IP = `76.13.214.140`, login root, OS Ubuntu 22.04/24.04
> โดเมน = `srv1793506.hstgr.cloud` (hostname ของ VPS — Hostinger ชี้ DNS มาที่เครื่องให้อัตโนมัติแล้ว)
> ตำแหน่งแอปบนเครื่อง = `/opt/oxlet`

---

## 0) ก่อนเริ่ม — push โค้ดล่าสุดขึ้น GitHub

VPS จะ `git clone` จาก GitHub ดังนั้นต้องมีการแก้ครั้งนี้อยู่บน repo ก่อน
(เพิ่ม `gunicorn` ใน requirements.txt, env `SECURE_SSL_REDIRECT`, โฟลเดอร์ `deploy/`)

- commit + push branch `main` ขึ้น `github.com/Wattanakit27/SaleforceOxletauto`
- ถ้า repo เป็น private: เตรียม GitHub Personal Access Token ไว้ใส่ตอน clone

(บอกผมได้ถ้าให้ช่วย commit ให้ — ผมไม่ push เองจนกว่าจะสั่ง)

---

## 1) โดเมน — ใช้ hostname ของ VPS (ไม่ต้องตั้ง DNS เอง)

ใช้ `srv1793506.hstgr.cloud` ที่ Hostinger ชี้มาที่ VPS ให้อัตโนมัติแล้ว — ไม่ต้องอ้างสิทธิ์โดเมนฟรี/ตั้ง A record
เช็คว่าชี้ถูกเครื่อง:
```bash
ping srv1793506.hstgr.cloud      # ต้องได้ 76.13.214.140
```

> อยากใช้โดเมนสวย ๆ ของตัวเองภายหลัง: ชี้ A record มาที่ IP นี้ แล้วแก้ค่าโดเมนใน .env + nginx + รัน certbot ใหม่

---

## 2) SSH เข้า VPS แล้วติดตั้งแพ็กเกจระบบ

```bash
ssh root@76.13.214.140

apt update && apt upgrade -y
apt install -y python3 python3-venv python3-dev build-essential \
    git nginx postgresql postgresql-contrib \
    certbot python3-certbot-nginx ufw curl libpq-dev
```

---

## 3) firewall

```bash
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable
```

---

## 4) สร้าง user + clone โค้ด

```bash
# user เฉพาะแอป (ไม่ login ตรง — ปลอดภัยกว่ารัน root)
adduser --system --group --home /opt/oxlet oxlet

# clone (public): 
git clone https://github.com/Wattanakit27/SaleforceOxletauto.git /opt/oxlet
# ถ้า private ใช้ token:
# git clone https://<TOKEN>@github.com/Wattanakit27/SaleforceOxletauto.git /opt/oxlet
```

---

## 5) venv + ติดตั้ง dependencies

```bash
cd /opt/oxlet
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
# gunicorn อยู่ใน requirements แล้ว · เผื่อ clone เวอร์ชันเก่า:
.venv/bin/pip install gunicorn
```

---

## 6) ตั้ง PostgreSQL (สำหรับระบบติดตามรถ cars/)

```bash
# ตั้งรหัสผ่าน DB ของคุณเอง แทน CHANGE_ME
sudo -u postgres psql -c "CREATE USER oxlet WITH PASSWORD 'CHANGE_ME';"
sudo -u postgres psql -c "CREATE DATABASE oxlet OWNER oxlet;"
```

---

## 7) สร้างไฟล์ .env

```bash
cp /opt/oxlet/deploy/.env.example /opt/oxlet/.env
nano /opt/oxlet/.env
```

แก้ค่าในไฟล์:
- `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SITE_URL`, `LINE_LOGIN_CALLBACK` → ใส่โดเมนจริง
- `DB_PASSWORD` → รหัสเดียวกับขั้นตอน 6
- ค่า `***copy-from-vercel***` ทุกตัว → เปิด Vercel dashboard → Settings → Environment Variables
  แล้วคัดลอกมา (ตัวที่ต้องเอามา): `DJANGO_SECRET_KEY`, `OXLET_ADMIN_PASSWORD`,
  `GOOGLE_PRIVATE_KEY`, `LINE_CHANNEL_ACCESS_TOKEN`, `LINE_LOGIN_CHANNEL_ID`,
  `LINE_LOGIN_CHANNEL_SECRET`, `GEMINI_API_KEY`, `CRON_SECRET`
- ตอนนี้ปล่อย `SECURE_SSL_REDIRECT=False` ไว้ก่อน (จะเปิดเป็น True หลังติด SSL)

> `GOOGLE_PRIVATE_KEY` วางทั้งก้อน (ขึ้นต้น `-----BEGIN PRIVATE KEY-----`) ครอบด้วย `"..."`
> ถ้าบน Vercel เก็บเป็นบรรทัดเดียวมี `\n` ก็วางแบบนั้นได้ (settings.py แปลง `\n` ให้เอง)

---

## 8) migrate + static + สร้าง superuser

```bash
cd /opt/oxlet
.venv/bin/python manage.py migrate
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py createsuperuser   # บัญชีนี้ = Executive (เข้า /track/ จัดการได้)

# ให้ user oxlet เป็นเจ้าของทุกอย่าง (gunicorn รันเป็น oxlet + เขียน media ได้)
mkdir -p /opt/oxlet/media
chown -R oxlet:oxlet /opt/oxlet
```

---

## 9) systemd service (gunicorn)

```bash
cp /opt/oxlet/deploy/oxlet.service /etc/systemd/system/oxlet.service
systemctl daemon-reload
systemctl enable --now oxlet
systemctl status oxlet --no-pager     # ต้องเห็น active (running)

# smoke test ผ่าน gunicorn ตรงๆ (ยังไม่ผ่าน nginx)
curl -s -H "X-Forwarded-Proto: https" http://127.0.0.1:8000/login/ | head -c 200
```

ถ้าพัง: `journalctl -u oxlet -n 50 --no-pager` ดู error

---

## 10) nginx

```bash
# nginx-oxlet.conf ตั้ง server_name = srv1793506.hstgr.cloud ไว้แล้ว — วางได้เลย
cp /opt/oxlet/deploy/nginx-oxlet.conf /etc/nginx/sites-available/oxlet

ln -sf /etc/nginx/sites-available/oxlet /etc/nginx/sites-enabled/oxlet
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
```

ทดสอบ: เปิด `http://srv1793506.hstgr.cloud/login/` ในเบราว์เซอร์ ต้องเห็นหน้า login

---

## 11) ติด SSL (Let's Encrypt) — จำเป็นสำหรับ LINE Login

```bash
certbot --nginx -d srv1793506.hstgr.cloud --redirect -m oxletauto@gmail.com --agree-tos
```

certbot จะเติม block 443 + redirect http→https + ตั้ง auto-renew ให้เอง

จากนั้นเปิด HTTPS เต็มรูปแบบ:
```bash
nano /opt/oxlet/.env      # เปลี่ยน SECURE_SSL_REDIRECT=False → True
systemctl restart oxlet
```

ทดสอบ: `https://srv1793506.hstgr.cloud/login/` ต้องเป็นกุญแจเขียว

---

## 12) crontab ในเครื่อง (แทน n8n — ยิง followup LINE + รีเฟรชข้อมูล)

```bash
# แทน YOUR_CRON_SECRET ด้วยค่า CRON_SECRET ใน .env
crontab -e
```
เพิ่มบรรทัด (ทุก 1 นาที):
```
* * * * * curl -fsS -H "X-Forwarded-Proto: https" "http://127.0.0.1:8000/api/cron/tick?secret=YOUR_CRON_SECRET" -o /dev/null
```

> ปิด workflow n8n เดิมได้เลย (ไม่ต้องใช้แล้ว) · ระบบส่ง followup ตามตารางในชีต "ตั้งเวลาส่ง" เหมือนเดิม

---

## 13) อัปเดต LINE Login channel (สำคัญ — ไม่งั้น login ไม่ได้)

ที่ LINE Developers Console → LINE Login channel → ตั้ง **Callback URL**:
```
https://srv1793506.hstgr.cloud/auth/line/callback
```
(ต้องตรงกับ `LINE_LOGIN_CALLBACK` ใน .env เป๊ะ)

---

## 13.1) เก็บรูป/วิดีโอลง Google Drive (ระบบติดตามรถ)

รูป/วิดีโอของรถถูกเก็บลง Google Drive ของ `oxletauto@gmail.com` (ใช้พื้นที่ Google One ที่ซื้อไว้)
ไฟล์ของรถแต่ละคันแยกโฟลเดอร์ ชื่อ `โค้ดรถ ทะเบียน(ทะเบียนเดิม)` เช่น `CS0011 กก1414(4525)`

ตั้งครั้งเดียว:
1. Google Cloud Console (โปรเจกต์เดียวกับ Sheets) → APIs & Services → เปิด **Google Drive API**
2. OAuth consent screen → User type **External** → เพิ่ม scope `.../auth/drive.file`
   → Publishing status ตั้งเป็น **In production** (กัน token หมดอายุใน 7 วันของโหมด Testing)
3. Credentials → Create OAuth client ID → Application type **Desktop app** → ได้ Client ID + Secret
4. บนเครื่องตัวเอง (มีเบราว์เซอร์) ในโฟลเดอร์โปรเจกต์:
   ```bash
   python manage.py gdrive_auth --client-id <ID> --client-secret <SECRET>
   ```
   → เบราว์เซอร์เด้ง → ล็อกอิน `oxletauto@gmail.com` → อนุญาต → คำสั่งพิมพ์ 3 ค่า
5. เอา `GDRIVE_CLIENT_ID` / `GDRIVE_CLIENT_SECRET` / `GDRIVE_REFRESH_TOKEN` ใส่ `.env` บน VPS
6. (แนะนำ) สร้างโฟลเดอร์แม่ บน VPS:
   ```bash
   cd /opt/oxlet && .venv/bin/python manage.py gdrive_setup
   ```
   → เอา `GDRIVE_ROOT_FOLDER_ID` ที่ได้ใส่ `.env` → `systemctl restart oxlet`

> ตั้งครบแล้ว: อัปรูป/วิดีโอจากหน้าสแกน/หน้าเซลล์/เพิ่มรถ จะเข้าโฟลเดอร์ของรถคันนั้นใน Drive อัตโนมัติ
> ไม่ตั้ง GDRIVE_* = อัปไฟล์ไม่ได้ (ฟอร์มอื่นยังทำงานปกติ)

---

## 14) เช็คลิสต์สุดท้าย

- [ ] `https://srv1793506.hstgr.cloud/login/` เปิดได้ มี SSL
- [ ] login LINE ได้ → เด้งเข้า /dashboard/ (admin) หรือ /me/ (เซลล์)
- [ ] ตัวเลข dashboard มาครบ (อ่าน Google Sheets ตรง)
- [ ] `/track/` เข้าได้ (ระบบติดตามรถ — ต่อ Postgres แล้ว)
- [ ] รอ ~2 นาที เช็ค followup cron ทำงาน: `grep cron /var/log/syslog | tail`
- [ ] ส่ง LINE Flex ทดสอบจากเมนูแอดมิน

---

## วิธี deploy อัปเดตครั้งต่อไป

```bash
cd /opt/oxlet
sudo -u oxlet git pull
.venv/bin/pip install -r requirements.txt          # ถ้ามี dep ใหม่
.venv/bin/python manage.py migrate                 # ถ้ามี migration ใหม่ (cars/)
.venv/bin/python manage.py collectstatic --noinput # ถ้าแก้ static
systemctl restart oxlet
```

---

## คำสั่ง debug ที่ใช้บ่อย

```bash
systemctl status oxlet            # สถานะแอป
journalctl -u oxlet -n 80 -f      # log สด (Python error / traceback)
systemctl restart oxlet           # รีสตาร์ทแอป
nginx -t && systemctl reload nginx
tail -f /var/log/nginx/error.log
```
