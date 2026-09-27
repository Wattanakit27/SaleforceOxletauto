# เปิดให้คนภายนอกดึงข้อมูลจากฐานข้อมูลจริงเอง (ไม่ต้องมีสำเนา ไม่ต้องผ่านตัวกลาง)

เจ้าของสั่ง 28 ก.ย.69: *"ให้เขาดึงมาจาก Hostinger เองเลย ไม่ต้องผ่านตัวกลางอย่างฉัน
ให้เขาดึงจากฐานข้อมูลจริงได้เลย"*

**ทำไมวิธีนี้ดีกว่าส่งไฟล์ dump ให้:** ไม่มีสำเนาฐานข้อมูลลอยอยู่ข้างนอก ·
เห็นข้อมูลสดเสมอไม่ต้องส่งใหม่ทุกเดือน · **ถอนสิทธิ์ได้ทันทีด้วยคำสั่งเดียว**
(ไฟล์ที่ส่งออกไปแล้วเรียกคืนไม่ได้)

- 📄 **ส่งให้คนภายนอก: [db_guide.md](db_guide.md)** — คู่มือวิธีต่อ + อธิบายทุกตาราง (48 ตาราง)
- 🔧 กลไกที่ใช้ (มีอยู่แล้ว): [postgres_readonly.sql](postgres_readonly.sql) ·
  [db_readonly_access.md](db_readonly_access.md)

---

## ป้องกัน 3 ชั้น

```
เครื่องเขา ──SSH (คีย์ที่เปิดได้แค่อุโมงค์)──▶ srv1793506 ──▶ PostgreSQL 127.0.0.1:5432
 localhost:15432                                             role อ่านอย่างเดียว
```

| ชั้น | กันอะไร |
|---|---|
| **ไม่เปิดพอร์ต 5432 ออกเน็ต** | บอทสแกนพอร์ตยิงรหัสเดาไม่ได้ · ฐานข้อมูลนี้มีแชทลูกค้า |
| **คีย์ SSH ทำได้แค่อุโมงค์** | คีย์หลุด = ได้แค่อุโมงค์ไป Postgres · **ไม่ได้ shell ไม่เห็นไฟล์บนเครื่อง** |
| **Postgres role อ่านอย่างเดียว** | เผลอพิมพ์ `UPDATE`/`DELETE` = ถูกปฏิเสธที่ระดับสิทธิ์ ข้อมูลจริงไม่พัง |

> **★★ ชั้นที่กันได้จริงคือ `GRANT` ไม่ใช่ `default_transaction_read_only`** —
> ทดสอบแล้ว `SET TRANSACTION READ WRITE` **สั่งผ่าน** (ผู้ใช้ปิดโหมดอ่านอย่างเดียวเองได้)
> แต่เขียนจริงยังโดน `permission denied for table`
> → **ห้าม `GRANT INSERT/UPDATE/DELETE` ให้ role ผู้อ่านเด็ดขาด**

---

## ขั้นที่ 0 — เลือกก่อนว่าให้เห็นแค่ไหน

| กลุ่มสิทธิ์ | เห็นอะไร | ให้ใคร |
|---|---|---|
| **`ro_safe`** | **11 ตาราง** — โซเชียล · โฆษณา · สต็อกรถ · **ไม่มีชื่อคน ไม่มีแชท ไม่มี LINE id** | เอเจนซี · ทีมการตลาด · นักวิเคราะห์ภายนอก · ที่ปรึกษา |
| **`ro_all`** | **ทุกตาราง** — รวมแชทลูกค้า 62,000 ข้อความ + ทะเบียนพนักงาน + เวลาเข้างาน | เจ้าของ · ผู้บริหาร เท่านั้น |

**เริ่มจาก `ro_safe` เสมอ** แล้วค่อยขยายถ้างานเขาต้องใช้จริง —
ให้เกินแล้วดึงคืนได้ก็จริง แต่สิ่งที่เขาเห็นไปแล้วดึงคืนไม่ได้

> ถ้าเขาต้องดู **ยอดขาย/ลีด** → **ไม่อยู่ในฐานข้อมูลนี้** (อยู่ใน Google Sheets) ต้องเตรียมแยก

---

## ขั้นที่ 1 — สร้างกลุ่มสิทธิ์ (ทำครั้งเดียวทั้งระบบ)

```bash
cd /opt/oxlet
sudo -u postgres psql -d oxlet -f deploy/postgres_readonly.sql
```

รันซ้ำได้ไม่พัง · ท้ายคำสั่งจะโชว์ตารางสรุปว่าแต่ละบัญชี **อ่านได้กี่ตาราง / เขียนได้กี่ตาราง**
— **`ins`/`upd`/`del` ต้องเป็น 0 ทุกคน** ถ้าไม่ใช่ อย่าไปต่อ

---

## ขั้นที่ 2 — สร้างบัญชีฐานข้อมูลของคนนั้น

เปลี่ยน `somchai` เป็นชื่อคนจริง (ตัวพิมพ์เล็ก ไม่มีช่องว่าง)

```bash
PW=$(openssl rand -base64 24 | tr -d '/+=')
echo "รหัสของ somchai: $PW"          # ★ จดไว้ ส่งให้เจ้าตัวคนละช่องทางกับคีย์ SSH

sudo -u postgres psql -d oxlet <<SQL
CREATE ROLE somchai LOGIN PASSWORD '$PW' IN ROLE ro_safe;
ALTER ROLE somchai SET default_transaction_read_only = on;
ALTER ROLE somchai SET statement_timeout = '30s';
ALTER ROLE somchai SET idle_in_transaction_session_timeout = '60s';
ALTER ROLE somchai CONNECTION LIMIT 3;
SQL
```

- **1 คน = 1 บัญชี ห้ามใช้ร่วมกัน** — ไม่งั้นเวลามีปัญหาไล่ไม่ได้ว่าใครทำ
- ให้เห็นทุกตาราง → เปลี่ยน `IN ROLE ro_safe` เป็น `IN ROLE ro_all`

---

## ขั้นที่ 3 — สร้างทางเข้า SSH ที่ **ทำได้แค่ต่อฐานข้อมูล**

ขอ **public key** จากเจ้าตัวก่อน (เขาสร้างเองด้วย `ssh-keygen -t ed25519`
แล้วส่งไฟล์ `.pub` มา — **ห้ามรับ private key และห้ามสร้างคีย์ให้เขา**)

```bash
# 3.1 user ที่ไม่มี shell (ทำครั้งเดียวต่อคน)
sudo useradd -m -s /usr/sbin/nologin ext_somchai
sudo mkdir -p /home/ext_somchai/.ssh && sudo chmod 700 /home/ext_somchai/.ssh

# 3.2 วาง public key ของเขา แบบเปิดได้แค่อุโมงค์ไป Postgres
#     แทน ssh-ed25519 AAAA... ด้วยคีย์ที่เขาส่งมาทั้งบรรทัด
sudo tee -a /home/ext_somchai/.ssh/authorized_keys >/dev/null <<'KEY'
restrict,port-forwarding,permitopen="127.0.0.1:5432",command="echo tunnel-only" ssh-ed25519 AAAA... somchai-db
KEY
sudo chmod 600 /home/ext_somchai/.ssh/authorized_keys
sudo chown -R ext_somchai:ext_somchai /home/ext_somchai/.ssh
```

- `restrict` = ปิดทุกอย่าง (shell · pty · forwarding ทุกชนิด) แล้วเปิดคืนเฉพาะ `port-forwarding`
- `permitopen="127.0.0.1:5432"` = อุโมงค์ไปได้ที่เดียวคือ Postgres ในเครื่อง —
  ต่อไปที่อื่นหรือเปิด shell ไม่ได้
- **ห้ามใส่คีย์ของคนนอกลงใน `authorized_keys` ของ `root`/`oxlet`/`claude`** — นั่นคือให้ทั้งเครื่อง

### ตรวจว่าจำกัดได้จริง (ทำก่อนส่งให้เขา)
```bash
# ต้อง "ไม่ได้ shell"  → ขึ้น tunnel-only แล้วหลุดออกมา
ssh -i <คีย์ทดสอบ> ext_somchai@srv1793506.hstgr.cloud
# ต้องต่อที่อื่นไม่ได้  → ขึ้น administratively prohibited
ssh -i <คีย์ทดสอบ> -N -L 9999:127.0.0.1:22 ext_somchai@srv1793506.hstgr.cloud
```

---

## ขั้นที่ 4 — ส่งให้เขา

| ส่ง | หมายเหตุ |
|---|---|
| **[db_guide.md](db_guide.md)** | คู่มือวิธีต่อ + อธิบายทุกตาราง + คำสั่งตัวอย่าง |
| ชื่อบัญชี ssh (`ext_somchai`) + โฮสต์ `srv1793506.hstgr.cloud` | |
| ชื่อบัญชีฐานข้อมูล + รหัส | **ส่งคนละช่องทางกับคีย์** (คีย์ทางอีเมล รหัสทางแชท เป็นต้น) |

คำสั่งที่เขาใช้:
```bash
ssh -i <คีย์ของเขา> -N -L 15432:127.0.0.1:5432 ext_somchai@srv1793506.hstgr.cloud
psql "host=127.0.0.1 port=15432 dbname=oxlet user=somchai"
```

---

## เพิกถอน (ทำได้ทันที ไม่กระทบคนอื่น)

```bash
sudo -u postgres psql -d oxlet -c "DROP OWNED BY somchai;"
sudo -u postgres psql -c "DROP ROLE somchai;"
sudo userdel -r ext_somchai
```

ล็อกอินค้างอยู่ก็ตัดเลย:
```bash
sudo -u postgres psql -d oxlet -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE usename='somchai';"
```

---

## เช็กลิสต์ก่อนเปิดให้ใช้จริง

- [ ] ขั้นที่ 1 รันแล้ว และตารางสรุปโชว์ `ins`/`upd`/`del` = **0** ทุกบัญชี
- [ ] บัญชีอยู่ใน `ro_safe` (ไม่ใช่ `ro_all`) เว้นแต่จำเป็นจริง
- [ ] ทดสอบแล้วว่า **ไม่ได้ shell** และ **ต่อพอร์ตอื่นไม่ได้**
- [ ] ยัง **ไม่ได้** เปิดพอร์ต 5432 ออกเน็ต (`ss -lntp | grep 5432` ต้องเห็นแค่ `127.0.0.1`)
- [ ] รหัสฐานข้อมูลกับคีย์ SSH ส่งคนละช่องทาง
- [ ] ส่ง `db_guide.md` ให้เขาแล้ว

---

## ทางเลือกที่ไม่ต้องแจกอะไรเลย

ถ้าเขาแค่ **อยากดูตัวเลข ไม่ได้เขียน SQL เอง** → ใช้หน้าเว็บ **ฐานข้อมูล (SQL)**
(`/dashboard/?panel=sql`) ดีกว่า: อ่านอย่างเดียวอยู่แล้ว · **ปิด LINE user id ของพนักงานให้อัตโนมัติ**
· ซ่อน password/token · ไม่ต้องแจกรหัสฐานข้อมูล ไม่ต้องสอน psql ไม่ต้องทำอุโมงค์
— แต่ต้องให้เขา login เข้าเว็บเรา และสิทธิ์นั้นกว้างกว่า `ro_safe`

**ต่อ psql ตรง = เห็นข้อมูลดิบทุกอย่างที่ role นั้นอ่านได้ ไม่มีการปิดบังใดๆ**
