# จับคู่ "ชื่อเล่น" ด้วย LINE user id (workflow ซื้อขายเทิร์นรถ) — 17 ก.ย.69

เดิม workflow เดา "ใครเป็นคนส่ง" ด้วยการ **เทียบชื่อที่ตั้งใน LINE** กับแท็บชีต `รายชื่อสมาชิกกลุ่ม`
ซึ่งพลาดบ่อยจนต้องเขียนโค้ดปะเพิ่มเรื่อยๆ (`Scavenger Mode`, `MANUAL_MAPPING`, ตัดอิโมจิ, partial match)

**ต้นเหตุ**: ชื่อที่ตั้งใน LINE **เจ้าตัวเปลี่ยนเองได้ทุกเมื่อ** · มีอิโมจิ/ช่องว่างท้าย ·
บอทคนละตัวอาจเห็นคนละชื่อ → เทียบด้วยชื่อเมื่อไหร่ก็มีวันหลุด

**ทางแก้**: ฐานข้อมูลเรามี `LINE user id → ชื่อเล่น` อยู่แล้ว (95 บัญชี) → **เทียบด้วย userId ไปเลย**

---

## 1. โหนด Postgres

ก๊อป [n8n_members_postgres.json](n8n_members_postgres.json) วางบน canvas — หรือวาง SQL นี้ทับในโหนดเดิม

```sql
SELECT coalesce(max(l."ชื่อเล่น"), '')   AS "nickByUserId",
       coalesce(max(l.display_name), '') AS "displayNameDb",
       $1::text                          AS "lookupUserId"
FROM v_employee_line l
WHERE l.user_id = $1::text;
```

**Options → Query Parameters**
```
{{ $json.body?.events?.[0]?.source?.userId || $json.userId || $json.source?.userId || '' }}
```

- `max()` ทำให้ **คืน 1 แถวเสมอ** แม้หา userId ไม่เจอ — ถ้าคืน 0 แถว n8n จะไม่มี item ส่งต่อ **เคสนั้นหายทั้งเคส**
- **ห้ามเปิด Continue On Fail** — โหนดล้มแล้วปล่อยผ่าน ก้อน error จะไหลเข้า `Merge All (with master)`
  แล้ว `Resolve Roles` อ่านมันเป็นรายชื่อ → ชื่อเล่นว่างทุกเคสโดยไม่มีอะไรแดง (เจอมาแล้ว)

---

## 2. แพตช์ `Resolve Roles` — 3 จุด

### จุดที่ 1 — ประกาศตัวแปร (ต่อจาก `let adminMasterData = [];`)

```js
let nickById = "";          // ★ ชื่อเล่นที่ได้จาก userId ตรงๆ (แม่นสุด)
```

### จุดที่ 2 — ในลูปกวาดข้อมูล (ต่อจาก `if (j.displayName) profileDisplayName = j.displayName;`)

```js
  // ★ มาจากโหนด "หาชื่อเล่นจาก userId (Postgres)"
  if (j.nickByUserId) nickById = j.nickByUserId;
```

### จุดที่ 3 — ต่อจากบล็อก `MANUAL_MAPPING` (ก่อน `if (!senderNickname) senderNickname = profileDisplayName;`)

```js
// ★ userId ชนะทุกวิธีเดา — ไม่ต้องพึ่ง MANUAL_MAPPING / partial match อีก
if (nickById) senderNickname = nickById;
```

ทำแค่นี้ · **ไม่ต้องลบโค้ดเดิม** — ของเดิมกลายเป็นทางสำรองเวลาหา userId ไม่เจอ (เช่นคนนอกที่ไม่ได้อยู่ในทะเบียน)

---

## 3. ⚠️ ที่ยังต้องแก้ด้วยมือ — 6 คนยังไม่มี "ชื่อเล่น" จริง

เทียบด้วย userId แม่นขึ้นจริง **แต่ถ้าในทะเบียนไม่มีชื่อเล่น ก็ยังได้ชื่อ LINE เหมือนเดิม**
(วัดจริง 17/09 — พนักงานใช้งานอยู่ 49 คน มี 6 คนที่ช่อง "ชื่อเล่น" ถูกตั้งเป็นชื่อ LINE)

| ชื่อเล่นที่บันทึกไว้ | ควรเป็น | ผูก LINE |
|---|---|---|
| `Wattanakit` | ? | 1 บัญชี |
| `janey...` | ? | 2 บัญชี |
| `tuinui` | ? | 0 บัญชี |
| `Nid` | ? | 2 บัญชี |
| `Sirun` | ? | 1 บัญชี |
| `เจมส์ oxletauto.co.th` | เจมส์ | 3 บัญชี |

แก้ที่ **`/dashboard/?panel=employees`** → ช่อง "ชื่อเล่น" (แก้แล้วบันทึกเอง)
พอแก้เสร็จ workflow จะได้ชื่อที่ถูกทันทีโดยไม่ต้องแตะ n8n อีก

> ทั้ง 6 คนช่อง "ตำแหน่ง" ว่างหมด = กลุ่มเดียวกับที่ติ๊ก "ไม่ต้องเช็คชื่อ" (ผู้บริหาร)
> ถ้าไม่อยากให้โผล่ในระบบเลย ก็ปล่อยไว้ได้ — แค่ชื่อในชีตจะเป็นชื่อ LINE
