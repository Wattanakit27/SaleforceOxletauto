# เชื่อมฐานข้อมูลจริง (Hostinger) แบบอ่านอย่างเดียว — ผ่านอุโมงค์ SSH

ให้ Claude Code บนโน้ตบุ๊กอ่านฐานข้อมูล PostgreSQL บนเซิร์ฟเวอร์ `srv1793506` (`76.13.214.140`)
ได้สด ไม่ต้อง copy ผลคำสั่งมาวาง และไม่ต้องเข้าหน้าเว็บ

## ภาพรวม — ป้องกัน 3 ชั้น

```
โน้ตบุ๊ก ──SSH (คีย์ที่เปิดได้แค่อุโมงค์)──▶ เซิร์ฟเวอร์ ──▶ PostgreSQL 127.0.0.1:5432
  localhost:15432                                          role: claude_ro (SELECT อย่างเดียว)
```

| ชั้น | กันอะไร |
|---|---|
| **ไม่เปิดพอร์ต 5432 ออกอินเทอร์เน็ต** | ฐานข้อมูลที่มีชื่อ/แชทลูกค้าไม่โผล่ให้ใครยิงรหัสเดาได้ |
| **คีย์ SSH ทำได้แค่อุโมงค์ไปที่ Postgres** | คีย์หลุด = ได้แค่อุโมงค์ ไม่ได้ shell · ไม่ได้เข้าเครื่อง |
| **Postgres role อ่านอย่างเดียว** | พิมพ์คำสั่งผิด/โค้ดเผลอเขียน = DB ปฏิเสธ ข้อมูลจริงไม่พัง |

> ⚠️ **ห้ามเปิด Postgres รับการเชื่อมต่อจากภายนอก** (`listen_addresses='*'` + เปิด firewall 5432)
> แม้จะดูง่ายกว่า — ฐานข้อมูลนี้มีข้อมูลส่วนบุคคลลูกค้า (PDPA) และบอทสแกนพอร์ต 5432 ตลอดเวลา

---

## ขั้นที่ 1 — บนเซิร์ฟเวอร์ (ทำครั้งเดียว)

### 1.1 ดูชื่อฐานข้อมูล + user ที่แอปใช้
```bash
grep -E '^DB_(NAME|USER)=' /opt/oxlet/.env
```

### 1.2 สร้าง role อ่านอย่างเดียว
```bash
PW=$(openssl rand -base64 24 | tr -d '/+=')   # รหัสสุ่ม — จดไว้ใช้ขั้นที่ 3
echo "$PW"
sudo -u postgres psql -d <DB_NAME> <<SQL
CREATE ROLE claude_ro LOGIN PASSWORD '$PW';
ALTER ROLE claude_ro SET default_transaction_read_only = on;
GRANT CONNECT ON DATABASE <DB_NAME> TO claude_ro;
GRANT USAGE ON SCHEMA public TO claude_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO claude_ro;
-- ⚠️ ตารางที่ migration สร้างทีหลัง: ต้องผูกกับ "user ของแอป" (คนสร้างตาราง) ไม่ใช่ postgres
ALTER DEFAULT PRIVILEGES FOR ROLE <DB_USER> IN SCHEMA public GRANT SELECT ON TABLES TO claude_ro;
SQL
```
> ถ้าลืมบรรทัด `ALTER DEFAULT PRIVILEGES FOR ROLE <DB_USER>` — ตารางใหม่หลัง migrate รอบหน้า
> จะอ่านไม่ได้ (`permission denied`) ทั้งที่ตารางเก่าอ่านได้ปกติ

### 1.3 สร้าง user สำหรับอุโมงค์ (ไม่มี shell)
```bash
useradd -m -s /usr/sbin/nologin claude_tunnel
mkdir -p /home/claude_tunnel/.ssh && chmod 700 /home/claude_tunnel/.ssh
```

### 1.4 ใส่ public key แบบเปิดได้แค่อุโมงค์ไป Postgres
เอา public key จากขั้นที่ 2 มาวางแทน `ssh-ed25519 AAAA...`
```bash
cat >> /home/claude_tunnel/.ssh/authorized_keys <<'KEY'
restrict,port-forwarding,permitopen="127.0.0.1:5432",command="echo tunnel-only" ssh-ed25519 AAAA... claude-db-readonly
KEY
chmod 600 /home/claude_tunnel/.ssh/authorized_keys
chown -R claude_tunnel:claude_tunnel /home/claude_tunnel/.ssh
```
- `restrict` = ปิดทุกอย่าง (shell/pty/forwarding) · แล้วเปิดคืนเฉพาะ `port-forwarding`
- `permitopen="127.0.0.1:5432"` = อุโมงค์ไปได้ที่เดียวคือ Postgres ในเครื่อง

---

## ขั้นที่ 2 — บนโน้ตบุ๊ก: สร้างคีย์ (คุณทำเอง)

```powershell
ssh-keygen -t ed25519 -f $HOME\.ssh\oxlet_db -C claude-db-readonly
Get-Content $HOME\.ssh\oxlet_db.pub      # เอาบรรทัดนี้ไปใส่ขั้นที่ 1.4
```

## ขั้นที่ 3 — บนโน้ตบุ๊ก: เก็บที่อยู่ฐานข้อมูลเป็นตัวแปรของ Windows

**ห้ามวางรหัสผ่านลงในแชท และห้ามใส่ใน `.env` ของโปรเจกต์**
(`.env` ในเครื่องมี `DB_HOST=127.0.0.1` อยู่แล้ว ถ้าผสมกันอาจทำให้ dev server ไปชี้ของจริง)

```powershell
[Environment]::SetEnvironmentVariable(
  "OXLET_PROD_RO_URL",
  "postgres://claude_ro:<รหัสจากขั้น 1.2>@127.0.0.1:15432/<DB_NAME>",
  "User")
```
ปิด-เปิด VS Code ใหม่ 1 ครั้งให้ตัวแปรมีผล

## ขั้นที่ 4 — ใช้งาน

เปิดอุโมงค์ (ค้างไว้ในหน้าต่างหนึ่ง):
```powershell
ssh -i $HOME\.ssh\oxlet_db -N -L 15432:127.0.0.1:5432 claude_tunnel@76.13.214.140
```

รันคำสั่งเดิมของโปรเจกต์กับข้อมูลจริง (อีกหน้าต่าง):
```powershell
$env:DATABASE_URL = $env:OXLET_PROD_RO_URL; $env:DB_SSLMODE = "disable"
.venv\Scripts\python manage.py checkout_status
.venv\Scripts\python manage.py db_export --list
```
- `DB_SSLMODE=disable` ปลอดภัยเพราะข้อมูลวิ่งในอุโมงค์ SSH ที่เข้ารหัสอยู่แล้ว
  (settings.py ตั้ง `require` เป็นค่าเริ่มต้น ซึ่ง Postgres ในเครื่องไม่ได้เปิด SSL ไว้)
- `DATABASE_URL` ที่ตั้งตรงนี้ **ชนะ `.env`** (`load_dotenv()` ไม่ทับตัวแปรที่มีอยู่แล้ว)

## ข้อจำกัดที่ต้องรู้

- **"สด" = ตอนที่ถาม** ไม่ใช่สตรีมต่อเนื่อง · ฐานข้อมูลบนเซิร์ฟเวอร์เป็น real-time อยู่แล้ว
  (n8n → เซิร์ฟเวอร์ → เขียนลง DB ทันที) สิ่งที่ได้คือ Claude อ่านของจริงได้เองทุกครั้งที่ถาม
- โน้ตบุ๊กพัก/เน็ตหลุด = อุโมงค์ขาด ต้องเปิดใหม่
- **อ่านได้อย่างเดียว** — คำสั่งไหนพยายามเขียน (เช่นอัปเดต heartbeat) จะ error `read-only transaction`
  ซึ่งคือพฤติกรรมที่ตั้งใจ
- **ห้าม `migrate` จากโน้ตบุ๊ก** (role นี้ทำไม่ได้อยู่แล้ว) — migrate บนเซิร์ฟเวอร์เท่านั้น

## ถ้าอยากให้ "แก้ข้อมูล" ได้ด้วย (ยังไม่แนะนำ)

ต้องทำ **snapshot VPS ก่อนทุกครั้ง** และแยก role เขียนได้เฉพาะตารางที่จำเป็น
การเขียน SQL ตรงลง DB ข้ามกติกาของแอป (อายุข้อมูล · ปิด LINE id พนักงาน · การแยกบัญชี OA)
→ งานแก้ข้อมูลควรทำผ่าน management command ที่ทดสอบแล้ว ไม่ใช่ UPDATE มือ

## เลิกใช้ / เพิกถอน

```bash
# บนเซิร์ฟเวอร์
sudo -u postgres psql -d <DB_NAME> -c "DROP OWNED BY claude_ro;"   # ต้องรันในฐานข้อมูลนั้น
sudo -u postgres psql -c "DROP ROLE claude_ro;"
userdel -r claude_tunnel
```
