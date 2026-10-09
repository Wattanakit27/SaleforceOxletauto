# ยื่นขอ TikTok API for Business — เพื่อดึงลีด TikTok เข้า Connect

เขียนให้: เจ้าของ / คนที่ถือบัญชี TikTok ของบริษัท · 4 ต.ค.69

## ทำไมต้องยื่นใหม่

แอป TikTok ที่เราเชื่อม 10 ช่องอยู่ตอนนี้ (Login Kit) ได้แค่ **ข้อมูลช่อง + ยอดวิวคลิป**
(`user.info.basic` `user.info.profile` `user.info.stats` `video.list`) — **ไม่มีทางอ่านแชท DM หรือคอมเมนต์ได้เลย**
ไม่ว่าจะขอสิทธิ์เพิ่มแค่ไหน เพราะเป็นคนละระบบกัน

ระหว่างรอ: ลีด TikTok เข้าทาง **ห้องพัก Lead** (แอดมินพักใบร่างในกลุ่ม "ADMIN เก็บ Lead") ซึ่งขึ้นใน Connect
และจ่ายเบอร์ได้แล้ว — ไม่ต้องรอผลยื่นถึงจะทำงานได้

## สิ่งที่ได้ / ไม่ได้ (ต้องยืนยันกับ TikTok ตอนยื่น)

| อยากได้ | ทางที่เป็นไปได้ | หมายเหตุ |
|---|---|---|
| คอมเมนต์ใต้คลิป | TikTok API for Business — การจัดการคอมเมนต์ของ **บัญชีธุรกิจ** | ทางที่มีโอกาสได้มากสุด |
| DM (แชทส่วนตัว) | **Business Messaging API** ของ TikTok | **ไทยใช้ได้** (เช็ค 4 ต.ค.69): เปิดแบบ Open Beta ใน APAC · ไม่เปิดเฉพาะบัญชีที่จดในสหรัฐ/EEA/สวิส/UK · ลูกค้าต้องทักก่อน (ธุรกิจเริ่มแชทเองไม่ได้) · รับข้อความเข้าทาง webhook ทันที |
| คอมเมนต์ระหว่างไลฟ์ | ไม่มี API สาธารณะ | ยังต้องให้แอดมินจดแบบเดิม (ห้องพัก Lead) |

ชื่อสิทธิ์ (scope) และเงื่อนไขของ TikTok เปลี่ยนบ่อย — ตารางนี้ให้ใช้เป็นตัวตั้งคำถาม แล้วยึดตามหน้าเอกสารของ TikTok
ตอนยื่นจริง

## ★ เช็คลึกจากเอกสารทางการ 9 ต.ค.69 — แชทได้จริงไหม
ดึงเนื้อหาจาก docs API ของพอร์ทัลตรง (`/gateway/api/doc/client/node/get/v2/?content_slug=<slug>&language=ENGLISH`
หรือ `?doc_id=<id>&language=ENGLISH` — หน้าเว็บเป็น SPA, WebFetch อ่านไม่ได้)

- **ไทยใช้ได้จริง**: ไม่เปิดเฉพาะบัญชีที่สมัครใน EEA/สวิส/UK · US ต้องผ่านรีวิวเพิ่ม · ที่เหลือ (Rest of World)
  ผ่าน DSPR อย่างเดียวพอ · ภูมิภาค = ที่อยู่ตอนสมัครบัญชีธุรกิจ · พาร์ทเนอร์ใช้งานจริงแล้ว (SleekFlow · respond.io ·
  Chatwoot · Qiscus · Infobip) = ระบบมีอยู่จริง ไม่ใช่แค่ประกาศ
- **ตัวเสี่ยงจริงคือ DSPR ของบริษัทเรา ไม่ใช่ตัว API** — "no exceptions" · ตรวจ 2–4 สัปดาห์ · TikTok คาดว่าเรามี:
  ผู้รับผิดชอบข้อมูลส่วนบุคคล · privacy notice (เว็บเรายังไม่มี) · รองรับสิทธิ์เจ้าของข้อมูล (ขอดู/ลบ) · ลบข้อมูลเมื่อเลิกอนุญาต ·
  **นโยบายความปลอดภัยเป็นลายลักษณ์อักษร ผู้บริหารเซ็น** · นโยบาย access control (least privilege + ทบทวนสิทธิ์ปีละครั้ง + เก็บ log) ·
  นโยบายรับมือเหตุ + ซ้อมปีละครั้ง · เข้ารหัสข้อมูลที่เก็บ AES-256 / ส่ง TLS 1.2+ · MFA บัญชีแอดมิน · ล็อกจออัตโนมัติ ·
  antivirus/HIPS · แยกเครือข่าย + NIDS · สแกนช่องโหว่/เพนเทสต์เก็บรายงาน · แนะนำแนบ ISO 27001 / SOC 2 (ไม่บังคับ แต่ช่วยให้ผ่านเร็ว)
  · ⚠️ ของเราตอนนี้: token TikTok เข้ารหัสด้วย Fernet = AES-128 (ต่ำกว่าที่ระบุ) · ยังไม่มีเอกสารนโยบายใดๆ · ยังไม่เคยสแกนช่องโหว่
- **ข้อจำกัดหลังได้สิทธิ์** (หน้า messaging limits): ลูกค้าต้องทักก่อน · หลังข้อความแรกส่งได้ 10 ข้อความใน 48 ชม. ·
  ลูกค้าตอบกลับ = ส่งได้ไม่จำกัดใน 48 ชม. นับจากข้อความล่าสุดของลูกค้า · เงียบเกิน 48 ชม. = ส่งได้อีก 3 ข้อความจนกว่าลูกค้าจะตอบ ·
  ดึงย้อนหลังได้ 100 ห้อง ห้องละ 20 ข้อความ (ต้องเก็บจาก webhook ทันที) · รูปภาพใช้ได้เฉพาะประเทศที่รองรับ · ข้อความ TikTok Shop คนละระบบ
  · บัญชีต้องตั้งให้ทุกคนทักได้ (Settings and privacy → Privacy → Direct messages → Everyone)
- **แอปใหม่ควรมี scope "CTM (click-to-message) event management" ด้วย** — เอกสารบอกให้ใส่ "Ad Account Management",
  "CTX Events Management", "Measurement" ตอนยื่นแอปก่อนขอ Business Messaging
- **TikTok account holder redirect URL** (คนละช่องกับ Advertiser redirect URL) ส่งกลับมาเป็น `?code=` ชนกับ callback ของ
  แอป Login Kit ที่ `/api/tiktok/webhook` → ตอนทำจริงให้ใช้ path แยก
- **ทางเลือกไม่ต้องผ่าน DSPR เอง**: ใช้พาร์ทเนอร์ที่ผ่านแล้ว (respond.io บอกว่าช่อง TikTok ใช้ฟรี) — ทดลองวัดปริมาณแชทได้ภายในวันเดียว
  · ข้อเสีย: แชทไปอยู่ระบบคนอื่น (เป็นผู้ประมวลผลข้อมูลตาม PDPA) · ต้องเช็คว่ามี API/webhook ส่งต่อเข้า Connect ไหม (ยังไม่ได้ยืนยัน)

## ขั้นตอน

> **ยืนยันจากเอกสาร TikTok แล้ว (4 ต.ค.69 · หน้า "Access to Business Messaging API")**
> - **ไม่มีโหมดทดสอบก่อนได้สิทธิ์** — ต้องผ่าน **Data security & privacy review (DSPR)** ก่อนถึงเรียก API แชทได้
> - ไทยอยู่กลุ่ม "Rest of World" = ผ่าน DSPR อย่างเดียวพอ (ไม่ต้องผ่าน US data security review — **ตอนยื่นอย่าติ๊ก US** ไม่งั้นรอนานขึ้น)
> - TikTok เริ่มตรวจภายใน **10 วันทำการ** หลังส่งฟอร์ม แล้วส่งแบบสอบถาม **"TikTok/ByteDance Third-Party Due Diligence
>   Questionnaire"** มาทางอีเมลผู้ติดต่อ — ตอบละเอียด แนบเอกสารความปลอดภัยถ้ามี · **ติดตามสถานะในเว็บไม่ได้** รอดูอีเมลอย่างเดียว
> - ได้สิทธิ์แล้ว: ลูกค้าทัก = webhook แจ้งทันที · ตอบด้วย `/business/message/send/` · **ดึงรายการแชทได้ 100 ห้องล่าสุด
>   ห้องละ 20 ข้อความล่าสุด** · โหลดรูปที่ลูกค้าส่งได้ · **ห้ามทักลูกค้าก่อน** · แชทของ TikTok Shop เป็นคนละระบบ

1. **เปลี่ยนช่องเป็นบัญชีธุรกิจ (Business Account)** — ในแอป TikTok: ตั้งค่า → บัญชี → เปลี่ยนเป็นบัญชีธุรกิจ
   (บัญชีส่วนตัว/ครีเอเตอร์ใช้ API กลุ่มนี้ไม่ได้) · **4 ต.ค.69 เป็นแล้ว 2 ช่อง: @oxletauto · @guru_jamesoxlet** ← เริ่มจาก 2 ช่องนี้
2. **สมัครนักพัฒนาที่ TikTok API for Business** (business-api.tiktok.com/portal → My Apps → **Become a Developer**)
   ด้วยบัญชี TikTok For Business ของบริษัท · ผลภายใน **3 วันทำการ**
   - **⚠️ อีเมลติดต่อต้องเป็นโดเมนบริษัท (`@oxletauto.co.th`) — Gmail/อีเมลส่วนตัวโดนปฏิเสธ** ·
     โดเมนเรามีเมลเซิร์ฟเวอร์อยู่แล้วที่ Hostatom (MX `mail.oxletauto.co.th`) → ให้คนดูแลเว็บ/โฮสติ้งสร้างกล่องเมล
     เช่น `developers@oxletauto.co.th` ที่หลังบ้าน Hostatom (TikTok แนะนำกล่องกลางที่ทีมเปิดอ่านร่วมกัน)
   - ประเภทผู้ใช้: **Direct Advertiser** (บริษัทที่ใช้กับบัญชีของตัวเอง) · ชื่อบริษัท = ชื่ออังกฤษตามหนังสือรับรอง ·
     เว็บไซต์ `https://www.oxletauto.co.th/` (ต้องตรงกับโดเมนอีเมล) · Primary Developer Location = **Thailand**
   - ช่องอธิบายการใช้งาน (ภาษาอังกฤษ · เขียนละเอียด ไม่งั้นโดนปฏิเสธ):
     > Oxlet Auto is a used-car dealership headquartered in Thailand, operating the brand Oxlet Auto and the website
     > oxletauto.co.th. We are the company's in-house development team. We are building an internal tool that connects
     > our own TikTok Business Accounts (@oxletauto, @guru_jamesoxlet) so that customer direct messages and comments
     > about cars for sale reach our sales staff quickly, and so we can report the performance of our own organic content.
     > The tool is used only by our employees, only for accounts owned by our company, and is not offered to any third party.

   → **สร้างแอปนักพัฒนา (developer app) ให้ผ่านการอนุมัติก่อน** (2–3 วันทำการ · ถ้าเลือกสิทธิ์ "TikTok Accounts"
   ต้องกรอก **Accounts API Access Application Form** ก่อนกดส่ง) — TikTok แนะนำให้ขอสิทธิ์
   "Ad Account Management" · "CTX Events Management" · "Measurement" ในใบสมัครแอปใหม่
   (คนละแอปกับแอป Login Kit ที่ใช้ดึงยอดวิวอยู่) · **อัปโหลดโลโก้แอป** (≤512×512) ไม่งั้นหน้าขออนุญาตของช่องจะ error
3. **ส่งฟอร์ม "Data security and privacy review intake form"** (ลิงก์อยู่ในหน้า Access to Business Messaging API)
   → ตอบแบบสอบถามที่ส่งมาทางอีเมล → รออนุมัติ · หลังอนุมัติ เลือกสิทธิ์ **Business Messaging** + **TikTok Accounts**
   (และสิทธิ์คอมเมนต์ของบัญชีธุรกิจ ถ้าอยากได้คอมเมนต์ด้วย)
4. **กรอกเหตุผลการใช้งาน** — ใช้ข้อความนี้ได้:
   > ระบบภายในของโชว์รูมรถมือสอง ใช้รวมคอมเมนต์/ข้อความจากลูกค้าที่สนใจรถ ให้แอดมินส่งต่อให้พนักงานขาย
   > ติดต่อกลับภายใน 5 นาที · อ่านและตอบเฉพาะบัญชีของบริษัทเอง ไม่เก็บข้อมูลเกินจำเป็น (ลบเองภายใน 60–90 วัน)
5. **Callback / Redirect URL** = `https://srv1793506.hstgr.cloud/api/tiktok/webhook` (ตัวเดียวกับที่ใช้อยู่)
6. **เตรียมไว้** (TikTok มักขอ): ลิงก์นโยบายความเป็นส่วนตัวของบริษัท · วิดีโอสาธิตการใช้งานสั้นๆ (อัดหน้าจอ Connect ได้) ·
   เอกสารยืนยันธุรกิจ
7. **ได้รับอนุมัติแล้ว** — ส่ง **client key + client secret ของแอปใหม่** มา (ใส่ใน `.env` บนเซิร์ฟเวอร์ ไม่ส่งในแชท/อีเมล)
   แล้วบอกผม — ผมทำส่วนดึงเข้า Connect (คิวเดียวกับ LINE/Facebook · ป้าย TikTok · จ่ายเบอร์ได้) ต่อ

## สิ่งที่ผมทำให้ไม่ได้

- ยื่นแทน — ต้องล็อกอินด้วยบัญชี TikTok for Business ของบริษัท
- รับประกันว่าจะได้ — TikTok เป็นคนพิจารณา ใช้เวลาหลายวันถึงหลายสัปดาห์

## วิดีโอสำหรับฟอร์ม (ข้อ 8 Screen Recordings)
- เปิด [tiktok_review_demo.html](tiktok_review_demo.html) ใน Chrome (ดับเบิลคลิกไฟล์) → กด F11 เต็มจอ → อัดด้วย `Win + Shift + R`
- กด → / ← เลื่อนทีละขั้น (14 ขั้น · ราว 1.5–2 นาทีถ้าค้างขั้นละ 6–8 วินาที) · กด H ซ่อน/โชว์แถบคำอธิบายด้านบน
- เนื้อหา: เชื่อมบัญชีของบริษัท → คอมเมนต์เข้าคิวเดียวกับ LINE/Facebook + นาฬิกา 5 นาที → แอดมินโอนให้เซลล์ →
  เซลล์ตอบ (โพสต์ลง TikTok + จดผู้ตอบ/เวลา) → ซ่อนสแปม → รายงานยอดของช่อง/คลิป → สิทธิ์ตามบทบาท + ลบข้อมูล 60 วัน → สรุปสิทธิ์ที่ขอ
- **เป็นต้นแบบ ข้อมูลตัวอย่างทั้งหมด** (เขียนกำกับในหน้าแล้ว) · ไม่ต่อ API จริง · ไม่เลียนหน้าจอ TikTok (ขั้นขออนุญาตเขียนว่า "หน้าของ TikTok เปิดที่ขั้นนี้")
