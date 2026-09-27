# คู่มือฐานข้อมูล Oxlet Auto — สำหรับผู้ที่ต่อเข้ามาอ่านข้อมูลเอง

ปรับปรุง 28 ก.ย. 2569 · PostgreSQL 16 · 48 ตาราง · 108,129 แถว

> เอกสารนี้อธิบายว่า **แต่ละตารางเก็บอะไร และต้องอ่านอย่างไรให้ได้เลขที่ถูก**
> คุณต่อเข้าฐานข้อมูลจริงโดยตรง ไม่มีตัวกลาง ไม่มีสำเนา — ข้อมูลที่เห็นคือข้อมูลสดเสมอ

---

## 1. วิธีต่อเข้าฐานข้อมูล

ฐานข้อมูล **ไม่เปิดพอร์ตออกอินเทอร์เน็ต** (มีข้อมูลส่วนบุคคลของลูกค้า) — ต่อผ่าน **อุโมงค์ SSH**

```
เครื่องคุณ ──SSH (คีย์ที่เปิดได้แค่อุโมงค์)──▶ เซิร์ฟเวอร์ ──▶ PostgreSQL 127.0.0.1:5432
localhost:15432
```

**ขั้นที่ 1** เปิดอุโมงค์ค้างไว้ (เปิดหน้าต่างนี้ทิ้งไว้ระหว่างใช้งาน)

```bash
ssh -i <ไฟล์คีย์ที่ได้รับ> -N -L 15432:127.0.0.1:5432 <ชื่อบัญชี ssh>@srv1793506.hstgr.cloud
```

**ขั้นที่ 2** ต่อฐานข้อมูลที่ `localhost:15432`

```bash
psql "host=127.0.0.1 port=15432 dbname=oxlet user=<บัญชีฐานข้อมูล>"
```

ต่อด้วยเครื่องมืออื่นก็ได้ (DBeaver · pgAdmin · Power BI · Excel · Metabase) ตั้งค่าเหมือนกัน:

| ช่อง | ค่า |
|---|---|
| Host | `127.0.0.1` |
| Port | `15432` |
| Database | `oxlet` |
| User / Password | ที่ได้รับมา |
| SSL | ไม่ต้อง (วิ่งในอุโมงค์ SSH ซึ่งเข้ารหัสอยู่แล้ว) |

### กติกาที่ระบบบังคับไว้

| ข้อ | รายละเอียด |
|---|---|
| **อ่านอย่างเดียว** | `INSERT`/`UPDATE`/`DELETE` ถูกปฏิเสธที่ระดับสิทธิ์ ไม่ใช่แค่ตั้งค่า — แก้ข้อมูลไม่ได้แน่นอน |
| **คำสั่งเกิน 30 วินาที ถูกตัด** | ถ้าโดนตัด ให้ใส่ `WHERE` จำกัดช่วงวันที่ หรือ `LIMIT` |
| **ต่อพร้อมกันได้ 3 สาย** | ปิด connection ที่ไม่ใช้ |
| **1 คน = 1 บัญชี** | ห้ามใช้ร่วมกัน/ส่งต่อ — ทุกคำสั่งมีชื่อบัญชีกำกับในล็อก |

> ⚠️ ฐานข้อมูลนี้มี **ชื่อลูกค้า เบอร์โทร และบทสนทนาจริง** — ข้อมูลส่วนบุคคลตาม PDPA
> ใช้เท่าที่งานต้องการ · ห้ามก๊อปออกไปเก็บที่อื่น · ห้ามส่งต่อให้คนที่ไม่ได้รับอนุญาต

## 2. ⚠️ สิ่งที่ **ไม่ได้** อยู่ในฐานข้อมูลนี้

อ่านข้อนี้ก่อนเสมอ ไม่งั้นจะสรุปผิดว่า "ระบบเก็บแค่นี้"

| เรื่อง | อยู่ที่ไหน |
|---|---|
| **ข้อมูลการขาย · ลีด · ยอดจอง/ปล่อยรถ · เป้าเซลล์** | **Google Sheets** ไม่ได้อยู่ในฐานข้อมูลนี้ |
| รูปรถ · วิดีโอ · เอกสาร | Google Drive (ในฐานข้อมูลเก็บแค่ id ที่ชี้ไป) |
| ไฟล์รูปในแชท LINE | อยู่ที่ LINE (เก็บแค่ `message_id` + ธง `has_media`) |

ตารางในนี้คือ: **โซเชียล/โฆษณา · สต็อกรถและสเตปงาน · พนักงานและการเช็คชื่อ · เบิก-คืนรถ · แชทลูกค้า · ล็อกระบบ**

## 3. ★ อ่านตัวเลขให้ถูก — 6 กับดักที่เจอมาแล้วจริง

**3.1 ตาราง `*_snapshot` เก็บ "ยอดสะสม" ไม่ใช่ยอดรายวัน**

`dash_meta_post_snapshot` · `dash_tiktok_video_snapshot` · `dash_youtube_video_snapshot` เก็บยอด ณ ตอนที่ไปดึง → **ยอดของวันนั้น = ค่าวันนี้ − ค่าเมื่อวาน**

- นับเฉพาะแถว **`trigger='cron'`** (แถว `manual` เกิดกลางวัน เอามาลบจะได้ครึ่งวันปนเต็มวัน)
- วันเดียวกันมีหลายแถวได้ (เซิร์ฟเวอร์รีสตาร์ตกลางรอบ) → หยิบ **แถวที่ดึงล่าสุดของวันนั้น**
- **ผลต่างติดลบ = ไม่นับ** (โพสต์ถูกลบ / แพลตฟอร์มแก้ตัวเลขย้อนหลัง)
- ต้องมี snapshot **อย่างน้อย 2 วัน** ถึงจะคิดยอดรายวันได้

**3.2 อยากได้ยอดรายวันเลย → ใช้ `dash_social_daily`**

ตารางนี้คำนวณไว้ให้แล้ว **1 แถว = โพสต์/คลิป 1 ชิ้น × 1 วัน** มีทั้งยอดที่เพิ่มขึ้นวันนั้น (`views`/`likes`/…) และยอดสะสม ณ สิ้นวัน (`cum_*`) → `WHERE date BETWEEN … AND …` ได้ตรงๆ

**3.3 ต้นทุนต่อหน่วยต้องคิดจาก "ผลรวมหารผลรวม" — ห้ามเฉลี่ยค่าเฉลี่ย**

```sql
-- ถูก:  ต้นทุนต่อแชท
SELECT sum(spend) / nullif(sum(chats), 0) FROM dash_ads_daily WHERE date >= '2026-09-01';
-- ผิด:  avg(spend/chats)  ← วัดจริงต่างกัน 61.31 vs 62.49 บาท
```

**3.4 ยอดของ YouTube ไม่มีช่อง "แชร์"** — API ไม่ให้ → `shares` เป็น 0 เสมอ **ไม่ใช่บั๊ก** (ยอดดิสไลก์ก็ไม่มี YouTube ปิดตั้งแต่ปี 2021)

**3.5 แชทมีวันหมดอายุ — ข้อมูลเก่าถูกลบเองตามกฎ PDPA**

แชทกลุ่มเก็บ 90 วัน · แชทลูกค้าเก็บ 60 วัน · คำตอบดิบจาก API เก็บ 90 วัน · ล็อกเหตุการณ์ 90 วัน → **นับย้อนหลังเกินนั้นไม่ได้** (ดูคอลัมน์ "อายุข้อมูล" ในหัวข้อ 5)

**3.6 LINE user id ในฐานข้อมูลนี้ผูกกับ "บอทตัวที่ได้ยิน"**

คนคนเดียวกันมี id **ต่างกันในแต่ละบอท** (LINE ออก id ต่อ provider) → ดูคอลัมน์ `channel` ประกอบเสมอ · อย่านับ `count(distinct sender_id)` เป็น "จำนวนคน" ตรงๆ เพราะคนเดียวอาจนับ 2 ครั้ง

## 4. อยากรู้อะไร → ดูตารางไหน

| คำถาม | ตาราง |
|---|---|
| โพสต์/คลิปไหนคนดูเยอะสุด · ยอดรายวันของแต่ละชิ้น | `dash_social_daily` |
| ยอดทั้งเพจ Facebook รายวัน (ตัวที่ Facebook รายงานเอง) | `dash_meta_page_daily` |
| ค่าโฆษณา · ต้นทุนต่อแชท/ต่อลีด | `dash_ads_daily` (รวม) · `dash_meta_ad_daily` (รายชิ้น) |
| ผู้ติดตามของแต่ละช่อง TikTok / YouTube | `dash_tiktok_account_snapshot` · `dash_youtube_channel_snapshot` |
| มีรถอะไรในสต็อก ราคาเท่าไหร่ อยู่สเตปไหน | `cars_car` (+ `cars_branch` = สาขา) |
| รถคันนี้ผ่านมือใครมาบ้าง เมื่อไหร่ | `cars_scanlog` |
| ใครเบิกรถออกไป คืนหรือยัง | `checkout_carmovement` (+ `checkout_movementphoto` = รูป) |
| พนักงานมีใคร ตำแหน่งอะไร เข้างานกี่โมง | `checkout_employee` |
| ใครมาสาย มาแล้วกี่วันในเดือนนี้ | `checkout_checkin` |
| ลูกค้ากำลังหารถอะไร งบเท่าไหร่ | `checkout_customerneed` |
| ลูกค้าคุยอะไรกับเรา (LINE / Facebook) | `checkout_groupchat` · `checkout_fbchat` |
| งานส่งข้อความอัตโนมัติล้มไหม เมื่อไหร่ | `dash_event_log` |

## 5. ตารางทั้งหมด

ป้ายกำกับ: **🔒 ข้อมูลส่วนบุคคล** = มีชื่อคน / เบอร์ / LINE id / บทสนทนา · **🟢 ro_safe** = บัญชีระดับ *อ่านเฉพาะตัวเลข* ก็เห็นตารางนี้

---

### ยอดขาย · โซเชียล · โฆษณา · ล็อกระบบ  (`dash_*`)

#### `dash_ads_daily`  —  ยอดโฆษณารายวัน (รวมทั้งบัญชี)

10 แถว  ·  🟢 ro_safe

ผลรวมรายวันของโฆษณา Meta — เงินที่ใช้ · แชทที่เริ่ม · ลีด · คลิกลิงก์ · วิว · แสดงผล · ไม่เก็บ "ต้นทุนต่อแชท" เป็นคอลัมน์โดยตั้งใจ (ต้องคิดจากผลรวมหารผลรวม ไม่ใช่เฉลี่ยรายวัน)

**อายุข้อมูล:** สร้างใหม่ได้เสมอ (manage.py ads_rebuild)

<details><summary>คอลัมน์ (16)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `date` | วันที่ |
| `account_id` | ข้อความ |
| `spend` | ทศนิยม |
| `impressions` | เลขจำนวนเต็ม |
| `reach` | เลขจำนวนเต็ม |
| `clicks` | เลขจำนวนเต็ม |
| `link_clicks` | เลขจำนวนเต็ม |
| `video_views` | เลขจำนวนเต็ม |
| `engagement` | เลขจำนวนเต็ม |
| `chats` | เลขจำนวนเต็ม |
| `chats_replied` | เลขจำนวนเต็ม |
| `leads` | เลขจำนวนเต็ม |
| `ads` | เลขจำนวนเต็ม |
| `campaigns` | เลขจำนวนเต็ม |
| `updated_at` | วันเวลา |

</details>

#### `dash_event_log`  —  ล็อกเหตุการณ์ระบบ

2,913 แถว  ·  🔒 ข้อมูลส่วนบุคคล

ส่งอะไรออก LINE บ้าง สำเร็จ/ล้มเพราะอะไร · webhook ขาเข้าที่ผิดปกติ · งานอัตโนมัติที่ล้ม — เก็บเป็นแถวต่อเหตุการณ์ จึงย้อนดูได้ว่าเริ่มพังเมื่อไหร่ (ต่างจาก dash_kv ที่เก็บแค่ครั้งล่าสุด) · ★ ช่อง target คือปลายทางที่ส่ง = LINE user id ของพนักงาน หรือ group id

**อายุข้อมูล:** เก็บ 90 วัน แล้วลบเอง

<details><summary>คอลัมน์ (8)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `at` | วันเวลา |
| `kind` | ข้อความ |
| `name` | ข้อความ |
| `target` | ข้อความ |
| `ok` | จริง/เท็จ |
| `ms` | เลขจำนวนเต็ม |
| `detail` | JSON |

</details>

#### `dash_followup_log`  —  สถิติการทวงงานรายวัน

874 แถว

ต่อวัน/ต่อเซลล์: ยังไม่โทรกี่เคส · ไม่ใส่สถานะกี่เคส · ดีลค้าง · ถูกทวงกี่รอบ

<details><summary>คอลัมน์ (13)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `date` | วันที่ |
| `seller` | ข้อความ |
| `team` | ข้อความ |
| `follow_total` | เลขจำนวนเต็ม |
| `stuck_deals` | เลขจำนวนเต็ม |
| `not_called` | เลขจำนวนเต็ม |
| `no_status` | เลขจำนวนเต็ม |
| `updated_at` | วันเวลา |
| `nags` | เลขจำนวนเต็ม |
| `nag_call` | เลขจำนวนเต็ม |
| `nag_deal` | เลขจำนวนเต็ม |
| `nag_status` | เลขจำนวนเต็ม |

</details>

#### `dash_form`  —  ฟอร์มไฟแนนซ์ / ขอสินเชื่อ

0 แถว  ·  🔒 ข้อมูลส่วนบุคคล

ฟอร์ม “เช็คไฟแนนซ์ก่อนเซ็น” และ “ขอสินเชื่อ” ที่เซลล์ส่งเข้ามา (สำเนาไว้ย้อนดู)

<details><summary>คอลัมน์ (4)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `kind` | ข้อความ |
| `data` | JSON |
| `created_at` | วันเวลา |

</details>

#### `dash_kv`  —  ค่าคอนฟิก + สถานะระบบ (key-value)

299 แถว  ·  🔒 ข้อมูลส่วนบุคคล

ที่เก็บของจุกจิกทั้งระบบ: ผลสรุปแดชบอร์ดที่คำนวณไว้ล่วงหน้า · heartbeat ของ cron · ค่าตั้งกลุ่ม LINE · รายชื่อกลุ่มที่บอทรู้จัก · แคชชื่อโปรไฟล์ LINE

**อายุข้อมูล:** ทับค่าเดิมเรื่อยๆ (ไม่สะสมแถว)

<details><summary>คอลัมน์ (3)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `key` | ข้อความ |
| `data` | JSON |
| `updated_at` | วันเวลา |

</details>

#### `dash_meta_ad_daily`  —  ผลโฆษณา Facebook (รายวัน)

916 แถว  ·  🟢 ro_safe

ใช้เงิน/แสดงผล/เข้าถึง/คลิก + actions ดิบ (ลีด แชท ฯลฯ) ต่อโฆษณาต่อวัน · เฉพาะบัญชีโฆษณาของบริษัทนี้ (ด่าน META_AD_ACCOUNTS)

**อายุข้อมูล:** เก็บถาวร

<details><summary>คอลัมน์ (22)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `date` | วันที่ |
| `account_id` | ข้อความ |
| `campaign_id` | ข้อความ |
| `campaign_name` | ข้อความ |
| `adset_id` | ข้อความ |
| `adset_name` | ข้อความ |
| `ad_id` | ข้อความ |
| `ad_name` | ข้อความ |
| `spend` | ทศนิยม |
| `impressions` | เลขจำนวนเต็ม |
| `reach` | เลขจำนวนเต็ม |
| `clicks` | เลขจำนวนเต็ม |
| `actions` | JSON |
| `cost_per_action` | JSON |
| `updated_at` | วันเวลา |
| `chats` | เลขจำนวนเต็ม |
| `chats_replied` | เลขจำนวนเต็ม |
| `engagement` | เลขจำนวนเต็ม |
| `leads` | เลขจำนวนเต็ม |
| `link_clicks` | เลขจำนวนเต็ม |
| `video_views` | เลขจำนวนเต็ม |

</details>

#### `dash_meta_page_daily`  —  ยอดระดับเพจที่ Facebook รายงานเอง (รายวัน)

70 แถว  ·  🟢 ro_safe

วิววิดีโอ/การมีส่วนร่วมทั้งเพจต่อวัน ตามที่ Meta สรุปให้ (ย้อนหลังได้ ~30 วัน) · ไว้เทียบว่ายอดที่เรารวมจากโพสต์เก็บครบไหม · เป็นยอดรวม ไม่มีชื่อคน

**อายุข้อมูล:** เก็บถาวร

<details><summary>คอลัมน์ (9)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `page_id` | ข้อความ |
| `date` | วันที่ |
| `video_views` | เลขจำนวนเต็ม |
| `engagements` | เลขจำนวนเต็ม |
| `page_views` | เลขจำนวนเต็ม |
| `follows` | เลขจำนวนเต็ม |
| `likes` | เลขจำนวนเต็ม |
| `updated_at` | วันเวลา |

</details>

#### `dash_meta_post_snapshot`  —  ยอดโพสต์ Facebook (ทุกเที่ยงคืน)

12,681 แถว  ·  🟢 ro_safe

ยอดสะสมของทุกโพสต์ในเพจเรา (วิว/ไลก์/คอมเมนต์/แชร์/คลิก/ดูเฉลี่ย) จดทุกเที่ยงคืน · เอาแถว cron วันนี้ลบเมื่อวาน = ยอดรายวัน (Meta ไม่ให้ยอดรายวันของไลก์/แชร์) · เป็นยอดรวม ไม่มีชื่อคนกด

**อายุข้อมูล:** เก็บถาวร

<details><summary>คอลัมน์ (21)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `taken_at` | วันเวลา |
| `snap_date` | วันที่ |
| `trigger` | ข้อความ |
| `page_id` | ข้อความ |
| `post_id` | ข้อความ |
| `post_type` | ข้อความ |
| `created_time` | วันเวลา |
| `permalink` | ข้อความ |
| `message` | ข้อความ |
| `reactions` | เลขจำนวนเต็ม |
| `reactions_by_type` | JSON |
| `comments` | เลขจำนวนเต็ม |
| `shares` | เลขจำนวนเต็ม |
| `clicks` | เลขจำนวนเต็ม |
| `video_views` | เลขจำนวนเต็ม |
| `video_views_organic` | เลขจำนวนเต็ม |
| `video_views_paid` | เลขจำนวนเต็ม |
| `video_avg_watch_ms` | เลขจำนวนเต็ม |
| `video_complete_30s` | เลขจำนวนเต็ม |
| `video_view_time_ms` | เลขจำนวนเต็ม |

</details>

#### `dash_meta_raw`  —  ข้อมูลดิบจาก Meta

352 แถว

คำตอบจาก Facebook ทั้งก้อน (โพสต์ + โฆษณา) ไว้คิดตัวเลขใหม่ย้อนหลัง · ตัด token ที่ฝังในลิงก์หน้าถัดไปออกแล้ว · ใหญ่สุดในระบบ (~12 MB/วัน)

**อายุข้อมูล:** เก็บ 90 วัน แล้วลบเอง

<details><summary>คอลัมน์ (6)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `fetched_at` | วันเวลา |
| `kind` | ข้อความ |
| `ref_id` | ข้อความ |
| `trigger` | ข้อความ |
| `data` | JSON |

</details>

#### `dash_seller_weekly`  —  ผลงานเซลล์รายสัปดาห์

139 แถว

ต่อสัปดาห์/ต่อเซลล์: lead · RJ · จอง · ปล่อย · ยอดเงิน · ไลฟ์ · คลิป

<details><summary>คอลัมน์ (12)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `week_start` | วันที่ |
| `seller` | ข้อความ |
| `team` | ข้อความ |
| `lead` | เลขจำนวนเต็ม |
| `rj` | เลขจำนวนเต็ม |
| `booking` | เลขจำนวนเต็ม |
| `done` | เลขจำนวนเต็ม |
| `deal_value` | เลขจำนวนเต็ม |
| `live` | เลขจำนวนเต็ม |
| `clip` | เลขจำนวนเต็ม |
| `updated_at` | วันเวลา |

</details>

#### `dash_social_daily`  —  ยอดโซเชียลรายวัน (Facebook + TikTok)

10,645 แถว  ·  🟢 ro_safe

ยอดที่ 'เพิ่มขึ้นจริงในวันนั้น' ของโพสต์/คลิปแต่ละชิ้น — 1 แถว/ชิ้น/วัน · คำนวณมาจากตาราง snapshot (ซึ่งเก็บยอดสะสม) เพื่อให้กรองช่วงวันที่ได้ตรงๆ · ลบทิ้งแล้วสร้างใหม่ได้เสมอด้วย manage.py social_rebuild · เป็นยอดรวม ไม่มีชื่อคน

**อายุข้อมูล:** สร้างใหม่ได้ (ต้นฉบับคือตาราง snapshot)

<details><summary>คอลัมน์ (15)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `date` | วันที่ |
| `platform` | ข้อความ |
| `object_id` | ข้อความ |
| `owner_id` | ข้อความ |
| `title` | ข้อความ |
| `views` | เลขจำนวนเต็ม |
| `likes` | เลขจำนวนเต็ม |
| `comments` | เลขจำนวนเต็ม |
| `shares` | เลขจำนวนเต็ม |
| `cum_views` | เลขจำนวนเต็ม |
| `cum_likes` | เลขจำนวนเต็ม |
| `cum_comments` | เลขจำนวนเต็ม |
| `cum_shares` | เลขจำนวนเต็ม |
| `updated_at` | วันเวลา |

</details>

#### `dash_tiktok_account`  —  ช่อง TikTok ที่เชื่อมแล้ว

10 แถว  ·  🔒 ข้อมูลส่วนบุคคล

ช่องที่เจ้าของกดอนุญาตให้ระบบอ่านข้อมูล 1 แถวต่อช่อง · ชื่อช่อง · สิทธิ์ที่ได้ · สถานะ · token เก็บแบบเข้ารหัส (หน้านี้และไฟล์ export ไม่แสดง)

**อายุข้อมูล:** เก็บจนกว่าเจ้าของช่องยกเลิกสิทธิ์

<details><summary>คอลัมน์ (16)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `open_id` | ข้อความ |
| `label` | ข้อความ |
| `display_name` | ข้อความ |
| `username` | ข้อความ |
| `scope` | ข้อความ |
| `profile` | JSON |
| `access_token` | ข้อความยาว |
| `access_expires_at` | วันเวลา |
| `refresh_token` | ข้อความยาว |
| `refresh_expires_at` | วันเวลา |
| `status` | ข้อความ |
| `last_error` | ข้อความ |
| `connected_by` | ข้อความ |
| `connected_at` | วันเวลา |
| `refreshed_at` | วันเวลา |

</details>

#### `dash_tiktok_account_snapshot`  —  ยอดช่อง TikTok (รายวัน)

45 แถว  ·  🟢 ro_safe

ผู้ติดตาม · ไลก์รวม · จำนวนคลิป ของแต่ละช่อง ณ สิ้นวัน (เฉพาะช่องที่ให้สิทธิ์ user.info.stats)

**อายุข้อมูล:** เก็บถาวร

<details><summary>คอลัมน์ (9)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `taken_at` | วันเวลา |
| `snap_date` | วันที่ |
| `trigger` | ข้อความ |
| `open_id` | ข้อความ |
| `follower_count` | เลขจำนวนเต็ม |
| `following_count` | เลขจำนวนเต็ม |
| `likes_count` | เลขจำนวนเต็ม |
| `video_count` | เลขจำนวนเต็ม |

</details>

#### `dash_tiktok_event`  —  event จาก TikTok (webhook)

0 แถว  ·  🔒 ข้อมูลส่วนบุคคล

สิ่งที่ TikTok for Developers ยิงเข้า /api/tiktok/webhook — 1 แถวต่อ event เก็บ body ดิบทั้งก้อน · signature_ok = ตรวจลายเซ็นผ่าน (ว่าง = ยังไม่ได้ตั้ง TIKTOK_CLIENT_SECRET จึงไม่ได้ตรวจ)

**อายุข้อมูล:** เก็บ 180 วัน แล้วลบเอง

<details><summary>คอลัมน์ (10)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `received_at` | วันเวลา |
| `event` | ข้อความ |
| `client_key` | ข้อความ |
| `user_openid` | ข้อความ |
| `create_time` | วันเวลา |
| `signature_ok` | จริง/เท็จ |
| `content` | JSON |
| `raw` | JSON |
| `body_hash` | ข้อความ |

</details>

#### `dash_tiktok_raw`  —  ข้อมูลดิบจาก TikTok

215 แถว

คำตอบจาก TikTok API ทั้งก้อน (รายการคลิป + ยอดช่อง) ไว้คิดตัวเลขใหม่ย้อนหลัง

**อายุข้อมูล:** เก็บ 90 วัน แล้วลบเอง

<details><summary>คอลัมน์ (6)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `fetched_at` | วันเวลา |
| `kind` | ข้อความ |
| `open_id` | ข้อความ |
| `trigger` | ข้อความ |
| `data` | JSON |

</details>

#### `dash_tiktok_video_snapshot`  —  ยอดคลิป TikTok (ทุกเที่ยงคืน)

2,832 แถว  ·  🟢 ro_safe

ยอดสะสมของทุกคลิป (วิว/ไลก์/คอมเมนต์/แชร์) ของทุกช่องที่เชื่อม จดทุกเที่ยงคืน · แถว cron วันนี้ลบเมื่อวาน = ยอดรายวัน

**อายุข้อมูล:** เก็บถาวร

<details><summary>คอลัมน์ (14)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `taken_at` | วันเวลา |
| `snap_date` | วันที่ |
| `trigger` | ข้อความ |
| `open_id` | ข้อความ |
| `video_id` | ข้อความ |
| `create_time` | วันเวลา |
| `title` | ข้อความ |
| `share_url` | ข้อความ |
| `duration` | เลขจำนวนเต็ม |
| `view_count` | เลขจำนวนเต็ม |
| `like_count` | เลขจำนวนเต็ม |
| `comment_count` | เลขจำนวนเต็ม |
| `share_count` | เลขจำนวนเต็ม |

</details>

#### `dash_youtube_channel_snapshot`  —  ยอดช่อง YouTube (รายวัน)

4 แถว  ·  🟢 ro_safe

ผู้ติดตาม · วิวรวมทั้งช่อง · จำนวนคลิป ของแต่ละช่อง ณ สิ้นวัน · ไม่ต้องให้เจ้าของช่องกดอนุญาต (ใช้ API key ใบเดียว)

**อายุข้อมูล:** เก็บถาวร

<details><summary>คอลัมน์ (10)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `taken_at` | วันเวลา |
| `snap_date` | วันที่ |
| `trigger` | ข้อความ |
| `channel_id` | ข้อความ |
| `handle` | ข้อความ |
| `title` | ข้อความ |
| `subscriber_count` | เลขจำนวนเต็ม |
| `view_count` | เลขจำนวนเต็ม |
| `video_count` | เลขจำนวนเต็ม |

</details>

#### `dash_youtube_raw`  —  ข้อมูลดิบจาก YouTube

52 แถว

คำตอบดิบทั้งก้อนจาก YouTube Data API — ไว้คิดตัวเลขใหม่ย้อนหลังถ้าสูตรเปลี่ยน

**อายุข้อมูล:** ลบเองเมื่อเกิน 90 วัน

<details><summary>คอลัมน์ (6)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `fetched_at` | วันเวลา |
| `kind` | ข้อความ |
| `channel_id` | ข้อความ |
| `trigger` | ข้อความ |
| `data` | JSON |

</details>

#### `dash_youtube_video_snapshot`  —  ยอดคลิป YouTube (ทุกเที่ยงคืน)

1,129 แถว  ·  🟢 ro_safe

ยอดสะสมของคลิปย้อนหลัง 90 วัน (วิว/ไลก์/คอมเมนต์) · แถว cron วันนี้ลบเมื่อวาน = ยอดรายวัน · YouTube ไม่ให้ยอดแชร์และดิสไลก์ จึงไม่มี 2 ช่องนั้น

**อายุข้อมูล:** เก็บถาวร

<details><summary>คอลัมน์ (13)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `taken_at` | วันเวลา |
| `snap_date` | วันที่ |
| `trigger` | ข้อความ |
| `channel_id` | ข้อความ |
| `video_id` | ข้อความ |
| `published_at` | วันเวลา |
| `title` | ข้อความ |
| `duration` | เลขจำนวนเต็ม |
| `is_short` | จริง/เท็จ |
| `view_count` | เลขจำนวนเต็ม |
| `like_count` | เลขจำนวนเต็ม |
| `comment_count` | เลขจำนวนเต็ม |

</details>

---

### รถในสต็อก + การติดตามสเตป  (`cars_*`)

#### `cars_branch`  —  สาขา

2 แถว  ·  🟢 ro_safe

รายชื่อสาขา/ลานจอด

<details><summary>คอลัมน์ (5)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `code` | ข้อความ |
| `name` | ข้อความ |
| `active` | จริง/เท็จ |
| `created_at` | วันเวลา |

</details>

#### `cars_car`  —  รถในระบบ

209 แถว  ·  🟢 ro_safe

ข้อมูลรถแต่ละคัน: รหัส · ทะเบียน · รุ่น/ปี/สี/เลขไมล์ · สเตปปัจจุบัน · ความด่วน · ธงงานค้าง · โฟลเดอร์รูปใน Google Drive

<details><summary>คอลัมน์ (29)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `code` | ข้อความ |
| `branch` | ข้อความ |
| `plate` | ข้อความ |
| `brand` | ข้อความ |
| `model` | ข้อความ |
| `year` | เลขจำนวนเต็ม |
| `color` | ข้อความ |
| `km` | เลขจำนวนเต็ม |
| `stage` | ข้อความ |
| `stage_since` | วันเวลา |
| `date_in` | วันเวลา |
| `frontline_at` | วันเวลา |
| `status` | ข้อความ |
| `book_status` | ข้อความ |
| `tax_due_date` | วันที่ |
| `doc_registration` | ข้อความ |
| `photo` | ข้อความ |
| `note` | ข้อความยาว |
| `created_at` | วันเวลา |
| `updated_at` | วันเวลา |
| `extra` | JSON |
| `deleted_at` | วันเวลา |
| `drive_folder_id` | ข้อความ |
| `plate_original` | ข้อความ |
| `priority` | ข้อความ |
| `need_content` | จริง/เท็จ |
| `need_photo` | จริง/เท็จ |
| `need_tire` | จริง/เท็จ |
| `price` | เลขจำนวนเต็ม |

</details>

#### `cars_loginevent`  —  Log การเข้าสู่ระบบ

6,550 แถว  ·  🔒 ข้อมูลส่วนบุคคล

ทุกครั้งที่มีคน login (สำเร็จ/ไม่สำเร็จ): บัญชี · วิธี · บทบาท · IP · อุปกรณ์

<details><summary>คอลัมน์ (10)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `created_at` | วันเวลา |
| `identity` | ข้อความ |
| `name` | ข้อความ |
| `method` | ข้อความ |
| `success` | จริง/เท็จ |
| `role` | ข้อความ |
| `ip` | ข้อความ |
| `user_agent` | ข้อความ |
| `reason` | ข้อความ |

</details>

#### `cars_presence`  —  คนออนไลน์ตอนนี้

23 แถว  ·  🔒 ข้อมูลส่วนบุคคล

แถวละคน — เห็นล่าสุดเมื่อไหร่ อยู่หน้าไหน (ใช้ทำชิป “N ออนไลน์”)

**อายุข้อมูล:** 1 แถว/คน (ทับค่าเดิม ไม่สะสม)

<details><summary>คอลัมน์ (6)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `identity` | ข้อความ |
| `name` | ข้อความ |
| `role` | ข้อความ |
| `page` | ข้อความ |
| `last_seen` | วันเวลา |

</details>

#### `cars_scanlog`  —  ประวัติเปลี่ยนสเตป (ไทม์ไลน์รถ)

98 แถว  ·  🔒 ข้อมูลส่วนบุคคล

ทุกครั้งที่มีคนเปลี่ยนสเตปรถ: ใครเปลี่ยน · เมื่อไหร่ · หมายเหตุ · รูป/วิดีโอที่แนบ

<details><summary>คอลัมน์ (9)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `stage` | ข้อความ |
| `worker_name` | ข้อความ |
| `worker_id` | ข้อความ |
| `photo` | ข้อความ |
| `note` | ข้อความยาว |
| `created_at` | วันเวลา |
| `car_id` | ข้อความ |
| `media` | JSON |

</details>

---

### พนักงาน · เช็คชื่อ · เบิก-คืนรถ · แชทลูกค้า  (`checkout_*`)

#### `checkout_carmovement`  —  รอบเบิก-คืนรถ

130 แถว  ·  🔒 ข้อมูลส่วนบุคคล

ใครเบิกรถคันไหน ไปทำอะไร ตอนไหน คืนเมื่อไหร่ · มุมที่ถ่ายครบ · ขอน้ำมันไหม · มาจากทางไหน (กดในเว็บ / บอทอ่านจากกลุ่ม LINE / นำเข้าจาก log)

<details><summary>คอลัมน์ (23)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `plate_text` | ข้อความ |
| `borrower_name` | ข้อความ |
| `borrower_line_id` | ข้อความ |
| `purpose` | ข้อความ |
| `destination` | ข้อความ |
| `checked_out_at` | วันเวลา |
| `returned_at` | วันเวลา |
| `odo_out` | เลขจำนวนเต็ม |
| `odo_in` | เลขจำนวนเต็ม |
| `status` | ข้อความ |
| `approved_by` | ข้อความ |
| `damage_reported` | จริง/เท็จ |
| `note` | ข้อความยาว |
| `created_at` | วันเวลา |
| `updated_at` | วันเวลา |
| `car_id` | ข้อความ |
| `config_id` | เลขจำนวนเต็ม |
| `fuel_requested` | จริง/เท็จ |
| `purpose_key` | ข้อความ |
| `source` | ข้อความ |
| `shots_in` | JSON |
| `shots_out` | JSON |

</details>

#### `checkout_checkin`  —  เช็คชื่อเข้างาน

370 แถว  ·  🔒 ข้อมูลส่วนบุคคล

1 แถวต่อ 'คน 1 วัน': มากี่โมง · ตรงเวลา/สาย · เวลาเข้างานของคนนั้น ณ วันนั้น · อ่านเวลาจากรูปหรือจากเวลาที่ส่ง · ที่อยู่ที่แนบมา · ผล OCR ดิบ

**อายุข้อมูล:** เก็บถาวร (เป็นประวัติการทำงาน)

<details><summary>คอลัมน์ (17)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `user_id` | ข้อความ |
| `display_name` | ข้อความ |
| `date_iso` | วันที่ |
| `checkin_at` | วันเวลา |
| `time_hm` | ข้อความ |
| `work_start` | ข้อความ |
| `status` | ข้อความ |
| `reason` | ข้อความ |
| `time_source` | ข้อความ |
| `full_address` | ข้อความ |
| `province` | ข้อความ |
| `note` | ข้อความ |
| `raw` | JSON |
| `created_at` | วันเวลา |
| `updated_at` | วันเวลา |
| `employee_id` | เลขจำนวนเต็ม |

</details>

#### `checkout_checklistconfig`  —  ชุดเช็คลิสต์เบิก-คืน

0 แถว

แม่แบบเช็คลิสต์ (เผื่อทำหลายชุด) — ตอนนี้ใช้ชุดฝังในโค้ดอยู่

<details><summary>คอลัมน์ (9)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `room_line_group_id` | ข้อความ |
| `name` | ข้อความ |
| `active` | จริง/เท็จ |
| `group_window_min` | เลขจำนวนเต็ม |
| `settle_seconds` | เลขจำนวนเต็ม |
| `remind_after_min` | เลขจำนวนเต็ม |
| `escalate_after_min` | เลขจำนวนเต็ม |
| `created_at` | วันเวลา |

</details>

#### `checkout_checklistitem`  —  ข้อในเช็คลิสต์

0 แถว

รายข้อของชุดเช็คลิสต์ (บังคับ/ไม่บังคับ · ต้องมีรูปกี่รูป)

<details><summary>คอลัมน์ (10)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `order` | เลขจำนวนเต็ม |
| `key` | ข้อความ |
| `label` | ข้อความ |
| `media_type` | ข้อความ |
| `required` | จริง/เท็จ |
| `min_count` | เลขจำนวนเต็ม |
| `allow_from_group_shot` | จริง/เท็จ |
| `special_rule` | ข้อความ |
| `config_id` | เลขจำนวนเต็ม |

</details>

#### `checkout_customerneed`  —  ลูกค้าหารถอะไร

548 แถว  ·  🔒 ข้อมูลส่วนบุคคล

1 แถว = ความต้องการ 1 เรื่อง: รุ่นที่หา · ปี · งบ · ผ่อนไหวเดือนละ · ดาวน์ได้ · ชื่อลูกค้า + ช่องทางติดต่อ · ปิดเคสเพราะอะไร · ยังรอรถอยู่ไหม

**อายุข้อมูล:** ตามโปรไฟล์ลูกค้าที่ผูกไว้

<details><summary>คอลัมน์ (26)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `car_text` | ข้อความ |
| `car_model` | ข้อความ |
| `car_year_min` | เลขจำนวนเต็ม |
| `car_year_max` | เลขจำนวนเต็ม |
| `budget_max` | เลขจำนวนเต็ม |
| `budget_min` | เลขจำนวนเต็ม |
| `monthly_max` | เลขจำนวนเต็ม |
| `down_max` | เลขจำนวนเต็ม |
| `status` | ข้อความ |
| `reject_kind` | ข้อความ |
| `reject_note` | ข้อความ |
| `waiting` | จริง/เท็จ |
| `lead_code` | ข้อความ |
| `seller` | ข้อความ |
| `source` | ข้อความ |
| `evidence` | ข้อความยาว |
| `confidence` | ข้อความ |
| `note` | ข้อความยาว |
| `created_at` | วันเวลา |
| `updated_at` | วันเวลา |
| `matched_at` | วันเวลา |
| `profile_id` | เลขจำนวนเต็ม |
| `channel` | ข้อความ |
| `contact` | ข้อความ |
| `customer_name` | ข้อความ |

</details>

#### `checkout_employee`  —  ทะเบียนพนักงาน

51 แถว  ·  🔒 ข้อมูลส่วนบุคคล

ตัวคน 1 แถว/คน: ชื่อเล่น · ชื่อที่ตั้งใน LINE · ตำแหน่ง/ทีม · เวลาเข้างาน · วันหยุด · หมายเหตุ (ลา/สาย) · ต้องเช็คชื่อไหม · แจ้งเตือนไหม — เป็นที่เก็บ 'ทีม' ที่เดียวของทั้งระบบ (แดชบอร์ดขายอ่านทับจากที่นี่)

**อายุข้อมูล:** เก็บถาวร · คนลาออกให้ปิดใช้งาน ไม่ต้องลบ

<details><summary>คอลัมน์ (16)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `nickname` | ข้อความ |
| `display_name` | ข้อความ |
| `position` | ข้อความ |
| `work_start` | ข้อความ |
| `day_off` | ข้อความ |
| `group_id` | ข้อความ |
| `active` | จริง/เท็จ |
| `note` | ข้อความ |
| `source` | ข้อความ |
| `created_at` | วันเวลา |
| `updated_at` | วันเวลา |
| `track_checkin` | จริง/เท็จ |
| `notify_missing` | จริง/เท็จ |
| `note_date` | วันที่ |
| `note_sticky` | จริง/เท็จ |

</details>

#### `checkout_equipmentissue`  —  ของหาย/ของเสียในรถ

0 แถว

เผื่อบันทึกอุปกรณ์ในรถที่หาย/ชำรุด — ยังไม่เปิดใช้

<details><summary>คอลัมน์ (8)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `reporter` | ข้อความ |
| `issue` | ข้อความ |
| `status` | ข้อความ |
| `approved_by` | ข้อความ |
| `approved_at` | วันเวลา |
| `created_at` | วันเวลา |
| `car_id` | ข้อความ |

</details>

#### `checkout_fbchat`  —  แชท Facebook Messenger

45,494 แถว  ·  🔒 ข้อมูลส่วนบุคคล

ข้อความในเพจเรา ทั้งที่ลูกค้าส่งมาและที่เพจตอบ (คู่ขนานกับ checkout_groupchat ฝั่ง LINE) · ดึงจาก Facebook ทุกเที่ยงคืน ไม่ใช่ real-time · sender_id = PSID (id ต่อเพจ ไม่ใช่ LINE id)

**อายุข้อมูล:** เก็บ 60 วัน (เท่าแชทลูกค้าฝั่ง LINE) แล้วลบเอง

<details><summary>คอลัมน์ (19)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `chat_type` | ข้อความ |
| `thread_id` | ข้อความ |
| `message_id` | ข้อความ |
| `sender_id` | ข้อความ |
| `sender_name` | ข้อความ |
| `msg_type` | ข้อความ |
| `text` | ข้อความยาว |
| `sticker_id` | ข้อความ |
| `extra` | JSON |
| `has_media` | จริง/เท็จ |
| `media_token` | ข้อความ |
| `channel` | ข้อความ |
| `direction` | ข้อความ |
| `sent_by_name` | ข้อความ |
| `send_error` | ข้อความ |
| `sent_at` | วันเวลา |
| `created_at` | วันเวลา |
| `sent_by_id` | เลขจำนวนเต็ม |

</details>

#### `checkout_fbprofile`  —  โปรไฟล์คน Facebook

3,463 แถว  ·  🔒 ข้อมูลส่วนบุคคล

คนที่ทักเข้าเพจ 1 แถวต่อคนต่อเพจ — ชื่อ · ห้องสนทนา · ลิงก์เปิดใน Inbox · จำนวนข้อความ (คู่ขนานกับ checkout_lineprofile) · Facebook ให้แค่ชื่อ ไม่มีเบอร์/อีเมลจริง

**อายุข้อมูล:** ลูกค้าที่เงียบเกิน 60 วันลบเอง

<details><summary>คอลัมน์ (16)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `user_id` | ข้อความ |
| `display_name` | ข้อความ |
| `nickname` | ข้อความ |
| `is_employee` | จริง/เท็จ |
| `source` | ข้อความ |
| `channel` | ข้อความ |
| `thread_id` | ข้อความ |
| `inbox_link` | ข้อความ |
| `thread_updated` | วันเวลา |
| `msg_count` | เลขจำนวนเต็ม |
| `first_seen` | วันเวลา |
| `last_seen` | วันเวลา |
| `fetched_at` | วันเวลา |
| `raw` | JSON |
| `employee_id` | เลขจำนวนเต็ม |

</details>

#### `checkout_groupchat`  —  แชทกลุ่ม LINE + แชทลูกค้า

17,029 แถว  ·  🔒 ข้อมูลส่วนบุคคล

ข้อความที่วิ่งผ่านบอท (กลุ่มงาน + ลูกค้าทัก 1:1): ข้อความ · สติกเกอร์ · อิโมจิ · ธงว่ามีรูป/ไฟล์

**อายุข้อมูล:** กลุ่ม 90 วัน · ลูกค้า 60 วัน (ตั้งใน checkout/constants.py)

<details><summary>คอลัมน์ (22)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `group_id` | ข้อความ |
| `group_name` | ข้อความ |
| `message_id` | ข้อความ |
| `sender_id` | ข้อความ |
| `sender_name` | ข้อความ |
| `msg_type` | ข้อความ |
| `text` | ข้อความยาว |
| `sticker_id` | ข้อความ |
| `sticker_package` | ข้อความ |
| `emojis` | JSON |
| `extra` | JSON |
| `has_media` | จริง/เท็จ |
| `media_token` | ข้อความ |
| `sent_at` | วันเวลา |
| `created_at` | วันเวลา |
| `chat_type` | ข้อความ |
| `channel` | ข้อความ |
| `direction` | ข้อความ |
| `send_error` | ข้อความ |
| `sent_by_id` | เลขจำนวนเต็ม |
| `sent_by_name` | ข้อความ |

</details>

#### `checkout_lineeventlog`  —  Log event ดิบจาก LINE

0 แถว  ·  🔒 ข้อมูลส่วนบุคคล

เผื่อเก็บ event ดิบเพื่อดีบัก — ยังไม่เปิดใช้

<details><summary>คอลัมน์ (10)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `line_message_id` | ข้อความ |
| `group_id` | ข้อความ |
| `sender_line_id` | ข้อความ |
| `event_type` | ข้อความ |
| `text` | ข้อความยาว |
| `raw` | JSON |
| `status` | ข้อความ |
| `attempts` | เลขจำนวนเต็ม |
| `created_at` | วันเวลา |

</details>

#### `checkout_lineprofile`  —  โปรไฟล์คนที่คุยกับบอท LINE

378 แถว  ·  🔒 ข้อมูลส่วนบุคคล

1 แถว/คน — LINE user id · ชื่อที่ตั้งใน LINE · ชื่อเล่น(ถ้าเป็นพนักงาน) · เคยคุยกี่ข้อความ · ทักครั้งแรก/ล่าสุดเมื่อไหร่ · เจอจากบัญชีบอทไหน (ไม่เก็บรูปโปรไฟล์)

**อายุข้อมูล:** โปรไฟล์ลูกค้าที่เงียบเกิน 60 วันถูกลบ · ของพนักงานเก็บไว้ (ใช้เทียบชื่อ)

<details><summary>คอลัมน์ (17)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `user_id` | ข้อความ |
| `display_name` | ข้อความ |
| `status_message` | ข้อความยาว |
| `language` | ข้อความ |
| `nickname` | ข้อความ |
| `is_employee` | จริง/เท็จ |
| `source` | ข้อความ |
| `group_id` | ข้อความ |
| `msg_count` | เลขจำนวนเต็ม |
| `first_seen` | วันเวลา |
| `last_seen` | วันเวลา |
| `fetched_at` | วันเวลา |
| `raw` | JSON |
| `channel` | ข้อความ |
| `channels` | JSON |
| `employee_id` | เลขจำนวนเต็ม |

</details>

#### `checkout_movementphoto`  —  รูปตอนเบิก/คืนรถ

154 แถว

รายการรูปของแต่ละรอบ (ตัวไฟล์อยู่ใน Google Drive — ตารางนี้เก็บแค่ตัวชี้)

<details><summary>คอลัมน์ (11)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `phase` | ข้อความ |
| `file` | ข้อความ |
| `media_type` | ข้อความ |
| `ai_label` | ข้อความ |
| `ai_confidence` | ทศนิยม |
| `phash` | ข้อความ |
| `line_message_id` | ข้อความ |
| `created_at` | วันเวลา |
| `checklist_item_id` | เลขจำนวนเต็ม |
| `movement_id` | เลขจำนวนเต็ม |

</details>

#### `checkout_violationlog`  —  บันทึกทำผิดกติกา

0 แถว  ·  🔒 ข้อมูลส่วนบุคคล

เผื่อบันทึกเคสที่ไม่ทำตามกติกา (เบิกไม่คืน / ไม่ส่งรูป) — ยังไม่เปิดใช้

<details><summary>คอลัมน์ (7)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `person` | ข้อความ |
| `person_line_id` | ข้อความ |
| `type` | ข้อความ |
| `detail` | ข้อความ |
| `created_at` | วันเวลา |
| `movement_id` | เลขจำนวนเต็ม |

</details>

---

### ตารางระบบของ Django  (`auth_*` · `django_*`)

#### `auth_group`  —  กลุ่มสิทธิ์ (บทบาท)

10 แถว

บทบาท 10 แบบของระบบติดตามรถ

<details><summary>คอลัมน์ (2)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `name` | ข้อความ |

</details>

#### `auth_group_permissions`  —  บทบาท ↔ สิทธิ์ย่อย

0 แถว

ระบบสร้างเอง

<details><summary>คอลัมน์ (3)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `group_id` | เลขจำนวนเต็ม |
| `permission_id` | เลขจำนวนเต็ม |

</details>

#### `auth_permission`  —  สิทธิ์ย่อย

184 แถว

สิทธิ์ระดับตารางของ Django (ระบบสร้างเอง)

<details><summary>คอลัมน์ (4)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `name` | ข้อความ |
| `content_type_id` | เลขจำนวนเต็ม |
| `codename` | ข้อความ |

</details>

#### `auth_user`  —  บัญชีผู้ใช้ (Django)

67 แถว  ·  🔒 ข้อมูลส่วนบุคคล

บัญชีของคนที่เข้าระบบติดตามรถ (คนงาน + คนที่ login ผ่าน LINE จะถูกสร้างให้อัตโนมัติ)

<details><summary>คอลัมน์ (11)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `password` | ข้อความ |
| `last_login` | วันเวลา |
| `is_superuser` | จริง/เท็จ |
| `username` | ข้อความ |
| `first_name` | ข้อความ |
| `last_name` | ข้อความ |
| `email` | ข้อความ |
| `is_staff` | จริง/เท็จ |
| `is_active` | จริง/เท็จ |
| `date_joined` | วันเวลา |

</details>

#### `auth_user_groups`  —  ผู้ใช้ ↔ บทบาท

65 แถว

ใครอยู่บทบาทไหน

<details><summary>คอลัมน์ (3)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `user_id` | เลขจำนวนเต็ม |
| `group_id` | เลขจำนวนเต็ม |

</details>

#### `auth_user_user_permissions`  —  ผู้ใช้ ↔ สิทธิ์ย่อย

0 แถว

ระบบสร้างเอง

<details><summary>คอลัมน์ (3)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `user_id` | เลขจำนวนเต็ม |
| `permission_id` | เลขจำนวนเต็ม |

</details>

#### `django_admin_log`  —  Log การแก้ข้อมูลใน /dj-admin/

0 แถว  ·  🔒 ข้อมูลส่วนบุคคล

ใครแก้อะไรผ่านหน้า Django admin

<details><summary>คอลัมน์ (8)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `action_time` | วันเวลา |
| `object_id` | ข้อความยาว |
| `object_repr` | ข้อความ |
| `action_flag` | เลขจำนวนเต็ม |
| `change_message` | ข้อความยาว |
| `content_type_id` | เลขจำนวนเต็ม |
| `user_id` | เลขจำนวนเต็ม |

</details>

#### `django_content_type`  —  ทะเบียนชนิดข้อมูล

46 แถว

ระบบสร้างเอง

<details><summary>คอลัมน์ (3)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `app_label` | ข้อความ |
| `model` | ข้อความ |

</details>

#### `django_migrations`  —  ประวัติ migrate

72 แถว

ไล่ว่าอัปโครงฐานข้อมูลถึงขั้นไหนแล้ว

<details><summary>คอลัมน์ (4)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `id` | เลขจำนวนเต็ม |
| `app` | ข้อความ |
| `name` | ข้อความ |
| `applied` | วันเวลา |

</details>

#### `django_session`  —  เซสชัน

0 แถว

ปกติ **ว่างเปล่า** — เว็บนี้เก็บ session ในคุกกี้ที่เซ็นชื่อ ไม่ได้เก็บลงตาราง

<details><summary>คอลัมน์ (3)</summary>

| คอลัมน์ | ชนิด |
|---|---|
| `session_key` | ข้อความ |
| `session_data` | ข้อความยาว |
| `expire_date` | วันเวลา |

</details>

---

## 6. คำสั่งตัวอย่าง (ก๊อปไปรันได้เลย)

```sql
-- ยอดวิว/ไลก์รายวัน แยกแพลตฟอร์ม (ใช้ตารางที่คำนวณไว้แล้ว)
SELECT date, platform, sum(views) AS views, sum(likes) AS likes
FROM dash_social_daily
WHERE date >= current_date - 30
GROUP BY 1, 2 ORDER BY 1 DESC, 2;

-- 20 โพสต์/คลิปที่คนดูเยอะสุดในเดือนนี้
SELECT platform, title, sum(views) AS views, sum(likes) AS likes
FROM dash_social_daily
WHERE date >= date_trunc('month', current_date)
GROUP BY 1, 2 ORDER BY views DESC LIMIT 20;

-- ต้นทุนโฆษณาต่อแชท / ต่อลีด  (ผลรวมหารผลรวม — ห้ามเฉลี่ยค่าเฉลี่ย)
SELECT sum(spend) AS spend, sum(chats) AS chats, sum(leads) AS leads,
       round(sum(spend) / nullif(sum(chats), 0), 2) AS cost_per_chat,
       round(sum(spend) / nullif(sum(leads), 0), 2) AS cost_per_lead
FROM dash_ads_daily WHERE date >= current_date - 30;

-- รถที่พร้อมขายอยู่ตอนนี้ แยกสาขา
--   ★ cars_car.branch เป็น "ข้อความ" ไม่ใช่ FK ไป cars_branch → ไม่ต้อง join
SELECT branch AS สาขา, count(*) AS คัน, round(avg(price)) AS ราคาเฉลี่ย
FROM cars_car
WHERE stage = 'show' AND status <> 'sold'
GROUP BY 1 ORDER BY 2 DESC;

-- คนมาสายบ่อยสุดในเดือนนี้
SELECT e.nickname, e.position, count(*) AS มาทั้งหมด,
       count(*) FILTER (WHERE k.status = 'late') AS สาย
FROM checkout_checkin k JOIN checkout_employee e ON e.id = k.employee_id
WHERE k.date_iso >= date_trunc('month', current_date)::date   -- ★ date_iso เป็นชนิด date
GROUP BY 1, 2 ORDER BY สาย DESC;

-- รถที่เบิกออกไปแล้วยังไม่คืน (ค้างกี่ชั่วโมง)
SELECT id, plate_text AS ทะเบียน, purpose AS งาน, borrower_name AS ผู้เบิก,
       checked_out_at AS เบิกเมื่อ,
       round(extract(epoch FROM now() - checked_out_at) / 3600, 1) AS ค้างชั่วโมง
FROM checkout_carmovement
WHERE returned_at IS NULL
ORDER BY checked_out_at;

-- งานส่งข้อความอัตโนมัติที่ล้ม 7 วันล่าสุด
SELECT date(at) AS วัน, name AS งาน, count(*) AS ครั้ง
FROM dash_event_log
WHERE kind = 'line_send' AND NOT ok AND at >= now() - interval '7 days'
GROUP BY 1, 2 ORDER BY 1 DESC, 3 DESC;

-- ยอดรายวันจากตาราง snapshot เอง (เผื่ออยากคิดจากต้นทางแทนใช้ dash_social_daily)
--   ★ ต้องทำ 3 ชั้น: เลือกแถวล่าสุดของวัน → หาผลต่างกับวันก่อน → ค่อยรวม
--     (Postgres ไม่ยอมให้ใส่ window function ไว้ใน sum() โดยตรง)
WITH latest AS (
  SELECT DISTINCT ON (post_id, snap_date) post_id, snap_date, video_views
  FROM dash_meta_post_snapshot
  WHERE trigger = 'cron'                  -- ★ แถว manual เอามาลบไม่ได้
  ORDER BY post_id, snap_date, id DESC    -- ★ วันเดียวกันเอาแถวที่ดึงล่าสุด
), diff AS (
  SELECT snap_date,
         video_views - lag(video_views) OVER (PARTITION BY post_id ORDER BY snap_date) AS d
  FROM latest
)
SELECT snap_date, sum(greatest(d, 0)) AS views_today   -- ★ ติดลบ = ไม่นับ
FROM diff WHERE d IS NOT NULL
GROUP BY 1 ORDER BY 1 DESC LIMIT 14;
```

## 7. ติดปัญหา

| อาการ | สาเหตุที่พบบ่อย |
|---|---|
| `could not connect to server` | อุโมงค์ SSH ปิดไปแล้ว — เปิดหน้าต่าง `ssh -N -L …` ใหม่ |
| `permission denied for table …` | ตารางนั้นไม่ได้อยู่ในสิทธิ์ของบัญชีคุณ (บัญชี `ro_safe` เห็น 11 ตาราง) |
| `canceling statement due to statement timeout` | คำสั่งเกิน 30 วิ — ใส่ `WHERE` ช่วงวันที่ หรือ `LIMIT` |
| `cannot execute UPDATE in a read-only transaction` | ปกติ — บัญชีนี้อ่านอย่างเดียว |
| ตัวเลขไม่ตรงกับที่ทีมบอก | อ่านหัวข้อ 3 อีกครั้ง (snapshot = ยอดสะสม) หรือข้อมูลนั้นอยู่ใน Google Sheets |

ถามทีมที่ดูแลระบบได้ — บัญชีของคุณอ่านอย่างเดียว ทดลองคำสั่งได้เต็มที่ ไม่มีทางทำข้อมูลพัง
