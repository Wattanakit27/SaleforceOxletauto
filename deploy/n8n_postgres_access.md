# ให้ n8n ต่อ Postgres ของเราโดยตรง (แทนโหนด Google Sheets) — ★ 16 ก.ย.69

n8n อยู่คนละเครื่องกับฐานข้อมูล (`n8n.srv1102218…` ↔ VPS `srv1793506`) และตอนนี้ Postgres
ตั้ง **`listen_addresses = localhost`** = ไม่รับการเชื่อมต่อจากข้างนอกเลย ต้องเปิดทางก่อน

เลือกได้ 2 ทาง — **ทาง A ปลอดภัยกว่า เพราะไม่เปิดพอร์ตฐานข้อมูลออกอินเทอร์เน็ตเลย**

---

## ทาง A — SSH tunnel (แนะนำ)
โหนด Postgres ของ n8n มีช่อง **SSH Tunnel** ในหน้า credential อยู่แล้ว

⚠️ **n8n ไม่ได้สร้างคีย์ให้** — ต้องสร้างคู่กุญแจเอง แล้วเอา **private key** ไปวางใน n8n

```bash
# บนเซิร์ฟเวอร์ (root) — บัญชีสำหรับ tunnel เท่านั้น
adduser --disabled-password --gecos "" n8ntunnel
mkdir -p /home/n8ntunnel/.ssh && chmod 700 /home/n8ntunnel/.ssh

# สร้างคู่กุญแจ (ไม่ตั้ง passphrase — n8n ใส่ passphrase ไม่ได้)
ssh-keygen -t ed25519 -f /root/n8n_tunnel_key -N "" -C "n8n-tunnel"

# public key -> authorized_keys (ล็อกให้ทำได้แค่ forward พอร์ต 5432 เปิด shell ไม่ได้)
# ⚠️ บรรทัดเดียวจบ ห้ามตัดบรรทัด — ถ้ามีช่องว่างตามหลัง \ เวลาก๊อปวาง bash จะตัดคำสั่ง
#    แล้วไฟล์ authorized_keys จะกลายเป็นไฟล์ว่าง (เจอจริง 16/09)
echo "no-agent-forwarding,no-X11-forwarding,no-pty,permitopen=\"127.0.0.1:5432\" $(cat /root/n8n_tunnel_key.pub)" > /home/n8ntunnel/.ssh/authorized_keys
chown -R n8ntunnel:n8ntunnel /home/n8ntunnel/.ssh && chmod 600 /home/n8ntunnel/.ssh/authorized_keys

# สิทธิ์ในฐานข้อมูล — ส่งรหัสผ่านทาง -v (ห้ามเขียนลงไฟล์ ไฟล์อยู่ใน git)
cd /opt/oxlet && sudo -u postgres psql -d oxlet -v pw="'<รหัสจริงที่ตั้งเอง>'" -f deploy/n8n_postgres_access.sql

# ตรวจว่าเขียนสำเร็จจริง (ต้องได้ 1 บรรทัด และขึ้นต้นด้วย no-agent-forwarding)
wc -l /home/n8ntunnel/.ssh/authorized_keys; head -c 60 /home/n8ntunnel/.ssh/authorized_keys; echo

cat /root/n8n_tunnel_key     # <- ก๊อปทั้งก้อนไปวางในช่อง Private Key ของ n8n แล้วค่อย rm ทิ้ง
# ⚠️ private key = กุญแจเข้าเซิร์ฟเวอร์ ห้ามส่งต่อ/แปะในแชท · หลุดเมื่อไหร่ให้สร้างใหม่ทับ
```

ตั้งใน n8n (Credential → Postgres):
- Host `127.0.0.1` · Port `5432` · Database `oxlet` · User `n8n` · Password ที่ตั้งไว้
- SSH Tunnel = เปิด · SSH Host `76.13.214.140` · SSH Port `22` · SSH User `n8ntunnel`
  · Private Key = เนื้อไฟล์ `/root/n8n_tunnel_key` ทั้งก้อน (รวมบรรทัด BEGIN/END)
- วางใน n8n เสร็จแล้วลบคีย์ออกจากเซิร์ฟเวอร์: `rm /root/n8n_tunnel_key`

**ไม่ต้องแก้ `listen_addresses` · ไม่ต้องเปิดพอร์ต 5432 ออกเน็ต**

---

## ทาง B — เปิดพอร์ต 5432 เฉพาะไอพีของ n8n
```bash
# 1) ให้ Postgres ฟังทุก interface
sudo -u postgres psql -c "ALTER SYSTEM SET listen_addresses = '*';"
# 2) อนุญาตเฉพาะไอพี n8n + บังคับ SSL + รหัสผ่านเข้ารหัส
echo "hostssl oxlet n8n <IP ของ n8n>/32 scram-sha-256" >> /etc/postgresql/*/main/pg_hba.conf
systemctl restart postgresql
# 3) ไฟร์วอลล์
ufw allow from <IP ของ n8n> to any port 5432 proto tcp
# 4) สิทธิ์
cd /opt/oxlet && sudo -u postgres psql -d oxlet -v pw="'รหัสที่ตั้งเอง'" -f deploy/n8n_postgres_access.sql
```
⚠️ **รหัสผ่าน role `n8n` ต้องเป็นรหัสจริง** — อย่าใช้ข้อความตัวอย่างในคู่มือนี้ (มันอยู่ใน git)
⚠️ **ยืนยันไอพีขาออกจริงของ n8n ก่อน** (บนเครื่อง n8n: `curl -s ifconfig.me`) — ใส่ผิดคือเปิดให้คนอื่น
⚠️ ฐานข้อมูลนี้มีแชทลูกค้าและ LINE id พนักงาน — **อย่าใช้ user `oxlet`/`postgres` ใน n8n เด็ดขาด**
ใช้ role `n8n` จากไฟล์ SQL ซึ่งเห็นแค่ 2 view และเขียนได้ช่องเดียว

---

## ทาง C — ไม่ต่อฐานข้อมูลเลย ใช้ HTTP node
`GET /api/v1/employees` (header `X-API-Key`) — ได้ ชื่อเล่น/ตำแหน่ง/**เวลาเข้างาน**/วันหยุด/
`userIds` ครบทุกบอท · ไม่ต้องตั้งอะไรบนเซิร์ฟเวอร์เพิ่มเลย (คีย์ตั้งไว้แล้วใน `.env`)
**ข้อจำกัด: อ่านอย่างเดียว** — ถ้าต้องเขียน "หมายเหตุ" กลับ ต้องใช้ทาง A/B หรือให้เพิ่ม endpoint เขียน

---

## สิ่งที่ n8n ใช้แทนโหนดชีตได้ทันที
| โหนดชีตเดิม | แทนด้วย |
|---|---|
| `ดึงรายชื่อพนักงาน (Text Branch)` | `SELECT * FROM v_employees WHERE active;` |
| หา "คนนี้คือใคร" จาก userId | `SELECT * FROM v_employee_line WHERE user_id = $1;` |
| `Save หมายเหตุ → Sheet พนักงาน` | `UPDATE checkout_employee SET note = $2 WHERE id = (SELECT employee_id FROM v_employee_line WHERE user_id = $1);` |
| `Save User Profile → Sheet` | **ตัดทิ้งได้** — ระบบเก็บโปรไฟล์เองอยู่แล้วทุกข้อความที่ผ่าน n8n |
| `Check Existing Records` / `Save Check-in Data` (ชีตเช็คชื่อ) | **ยังไม่มีตารางในระบบ** — ต้องทำเพิ่มถ้าจะย้าย |

⚠️ **`v_employee_line.user_id` มีทั้งไอดีบอทเดิมและบอทใหม่** → workflow ไม่ต้องแก้ไอดีอีกเวลาสลับบอท
(ต่างจากชีตที่มีชุดเดียว)

---

## เปลี่ยนรหัสผ่าน role `n8n` ทีหลัง
```bash
sudo -u postgres psql -d oxlet -c "ALTER ROLE n8n PASSWORD 'รหัสใหม่';"
```
รันซ้ำไฟล์ SQL ก็ได้ (มันจะ `ALTER` ให้ถ้า role มีอยู่แล้ว) · **เปลี่ยนแล้วอย่าลืมแก้ credential ใน n8n ด้วย**
