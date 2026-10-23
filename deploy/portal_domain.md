# ชื่อเว็บใหม่ `portal.oxletauto.co.th` (หลังบ้าน SaleForce) — ★ 23 ต.ค.69

เจ้าของสั่ง: ใช้ `portal.oxletauto.co.th` แทน `srv1793506.hstgr.cloud`
**ชื่อเดิมยังใช้ต่อได้ตลอด** — QR ที่ติดรถ, webhook LINE/Meta/TikTok, แอปมือถือ, n8n ยังชี้ชื่อเดิม ไม่ต้องรีบย้าย

| | ค่า |
|---|---|
| โดเมนหลัก | `oxletauto.co.th` — DNS อยู่ที่ Hostatom (`ns1/ns2.oxletauto.co.th` · เซิร์ฟเวอร์ `thsv44.hostatom.com`) |
| เซิร์ฟเวอร์ SaleForce | VPS Hostinger `76.13.214.140` |
| ระเบียน DNS ที่ต้องเพิ่ม | `A  portal  76.13.214.140` (TTL 300) |
| ห้ามแตะ | ระเบียน `@` / `www` / `mail` / `ftp` / MX / TXT เดิม (เว็บ WordPress + อีเมลบริษัทอยู่ที่ Hostatom) |

## ขั้นตอน (ทำตามลำดับ)

### 1. DNS (แผงควบคุม Hostatom)
เพิ่ม `A` ชื่อ `portal` → `76.13.214.140` แล้วรอ 5–10 นาที ตรวจจากเครื่องไหนก็ได้:
```bash
nslookup portal.oxletauto.co.th 8.8.8.8
```
ต้องได้ `76.13.214.140`

### 2. เอาโค้ดขึ้น + เช็ค .env (บนเซิร์ฟเวอร์ ด้วย root)
```bash
cd /opt/oxlet && git pull && grep -nE '^(ALLOWED_HOSTS|CSRF_TRUSTED_ORIGINS|LINE_LOGIN_CALLBACK|SITE_URL)=' .env
```
- ไม่มีบรรทัดพวกนี้ หรือค่าว่าง = **ไม่ต้องแก้** (ค่าตั้งต้นในโค้ดรับทั้ง 2 ชื่อแล้ว)
- มีค่าอยู่ = เติมชื่อใหม่ต่อท้าย (คั่นด้วย comma) เช่น
  `ALLOWED_HOSTS=srv1793506.hstgr.cloud,portal.oxletauto.co.th,localhost,127.0.0.1`
  `CSRF_TRUSTED_ORIGINS=https://srv1793506.hstgr.cloud,https://portal.oxletauto.co.th`
  `LINE_LOGIN_CALLBACK=https://srv1793506.hstgr.cloud/auth/line/callback,https://portal.oxletauto.co.th/auth/line/callback`
```bash
sudo systemctl restart oxlet
```

### 3. nginx + ใบรับรอง https
```bash
sudo sed -i 's/server_name srv1793506.hstgr.cloud;/server_name portal.oxletauto.co.th srv1793506.hstgr.cloud;/g' /etc/nginx/sites-available/oxlet && sudo nginx -t && sudo systemctl reload nginx
```
```bash
sudo certbot --nginx --expand -d srv1793506.hstgr.cloud -d portal.oxletauto.co.th
```
เลือก redirect (http → https) ถ้าถาม · ตรวจ: เปิด `https://portal.oxletauto.co.th/login/` ต้องขึ้นหน้า login มีกุญแจ

### 4. LINE Login
LINE Developers → channel LINE Login → **LINE Login → Callback URL** → เพิ่มบรรทัด
`https://portal.oxletauto.co.th/auth/line/callback` (เก็บบรรทัดเดิมไว้) → Update
ไม่เพิ่ม = เข้าทางชื่อใหม่แล้วกด "เข้าสู่ระบบด้วย LINE" LINE จะขึ้น error redirect_uri ไม่ตรง

### 5. (ทำทีหลังได้) ให้ลิงก์ที่ระบบสร้างใช้ชื่อใหม่
`.env` ตั้ง `SITE_URL=https://portal.oxletauto.co.th` แล้ว `sudo systemctl restart oxlet`
มีผลกับ: QR ที่ปริ้นใหม่ · ลิงก์ในข้อความ LINE (ตามด่วน/ใบจ่ายลีด) · รูปรายงานที่ส่งเข้า LINE · ลิงก์ติดตามบรอดแคสต์ · รูปที่ส่งให้เว็บโชว์รูม
**QR/ลิงก์เก่ายังใช้ได้** เพราะชื่อเดิมยังเปิดอยู่

## ที่ยังชี้ชื่อเดิม (ย้ายเมื่อสะดวก ไม่ย้ายก็ไม่พัง)
| ที่ | ค่าเดิม |
|---|---|
| แอปมือถือ (base URL) | `https://srv1793506.hstgr.cloud` |
| n8n: ยิง `/api/cron/tick` · ส่งต่อ LINE webhook `/api/line/group_ingest` | ชื่อเดิม |
| Meta webhook `/api/meta/webhook` · TikTok redirect/webhook `/api/tiktok/webhook` | ชื่อเดิม (ย้าย = ต้องลงทะเบียนใหม่ในหน้านักพัฒนาของแต่ละเจ้า) |
| เว็บโชว์รูม `.env SALEFORCE_LEAD_URL` | `https://srv1793506.hstgr.cloud/api/showroom/lead` |

## เว็บหลัก oxletauto.co.th → เว็บโชว์รูมใหม่ (ยังไม่ทำ · เจ้าของเลือกทำทีหลัง)
ตอนนี้ `oxletauto.co.th` / `www` = เว็บ WordPress เดิมที่ Hostatom · เปลี่ยนแล้ว WordPress หายจากหน้าเว็บทันที (อีเมลไม่กระทบถ้าไม่แตะ `mail`/MX)
**ต้องเตรียมเซิร์ฟเวอร์ก่อนเปลี่ยน DNS** ไม่งั้นช่วงนั้นคนเข้า oxletauto.co.th จะเจอหน้า login หลังบ้าน (nginx ส่งชื่อที่ไม่รู้จักไปที่ server block แรก):
nginx server block ใหม่ `oxletauto.co.th www.oxletauto.co.th` → เว็บโชว์รูม (`/opt/oxletauto_web`) · `.env` ของเว็บโชว์รูม
`ALLOWED_HOSTS`/`SITE_URL=https://oxletauto.co.th` · แล้วค่อยเปลี่ยน `@`/`www` → `76.13.214.140` · certbot ทันที ·
SaleForce `.env SHOWROOM_PUBLIC_URL=https://oxletauto.co.th`
