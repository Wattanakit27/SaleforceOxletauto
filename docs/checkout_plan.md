# แผนสร้างระบบเบิก-คืนรถส่วนกลาง (checkout/)

แมพจากสเปก `OXLET_CAR_CHECKOUT_SPEC.md` ลงบนโปรเจกต์ SaleforceOxletauto จริง
สถานะล่าสุด: **เฟส 1 ก้อน 1 (โครงข้อมูล) — เสร็จ** · ที่เหลือรอลงมือตามลำดับ

## ที่อยู่ของโค้ด
- Django app ระดับบน `checkout/` (แยกจาก cars/ เพราะเฟส 4 จะขยายไปตรวจ "ห้อง" ที่ไม่เกี่ยวรถ)
- อยู่ในโปรเจกต์นี้ (มี line_notify.py / gemini_ocr.py / cache_store / cron_tick / Drive+ดิสก์ ครบ)
- ใช้ DB จริง (Postgres บน VPS · SQLite ตอน dev) — ต้อง `migrate` ตอน deploy

## โครงข้อมูล (checkout/models.py) — เสร็จแล้ว
- `ChecklistConfig` + `ChecklistItem` — กติการายห้อง (ผูก LINE group id) · เพิ่มห้อง = เพิ่ม config
- `CarMovement` — 1 รอบเบิก-คืน (FK cars.Car · สถานะ 9 แบบ · ไมล์ออก/เข้า · ผู้อนุมัติ)
- `MovementPhoto` — ไฟล์หลักฐาน (phase out/in · ai_label/confidence · phash กันซ้ำ)
- `ViolationLog` — บันทึกฝ่าฝืน (หลักฐานฝ่ายบุคคล)
- `EquipmentIssue` — แจ้งกล้อง/อุปกรณ์เสีย + การอนุมัติ (log ผู้อนุมัติ — หลักฐานเคลมประกัน)
- `LineEventLog` — จด webhook event ดิบก่อนเป็นอย่างแรก (worker ไล่โหลดไฟล์จากคิว · dedupe message id)

## แผน 4 เฟส (แต่ละเฟสจบแล้วใช้งานได้จริง)
1. **โครงรับ-บันทึก-ทวง (ไม่มี AI)** — models✓ + LINE webhook journal + worker โหลดไฟล์ + parse เบิก/คืน
   + จับกลุ่มไฟล์เป็นรายงาน (ตะกร้ารอ) + เช็คจำนวนไฟล์ + ทวง + cron สรุปเย็น + แดชบอร์ด supervisor
2. **AI ตรวจ checklist (Gemini)** — จำแนกรูป/เฟรมวิดีโอ + OCR ไมล์ + phash + แย้ง/override/รอคนยืนยัน
3. **ฟอร์ม LIFF ช่องบังคับ** — เส้นทางชัวร์ 100% + AI ตรวจซ้ำ
4. **ขยายห้องอื่น** — เพิ่ม ChecklistConfig ใหม่ ไม่เขียนโค้ดใหม่

## ลำดับลงมือ (ก้อนย่อย)
- **ก้อน 1 — โครงข้อมูล** ✓ (app + 7 models + migration + admin + settings)
- ก้อน 2 — แดชบอร์ด supervisor (แท็บ "เบิก-คืนรถ" ใน index.html) + urls/views + กรอก/อนุมัติเอง (ยังไม่แตะ LINE)
- ก้อน 3 — LINE webhook journal + worker โหลดไฟล์ + parse เบิก/คืน + จับกลุ่มไฟล์
- ก้อน 4 — ทวง + แจ้งหัวหน้า + cron สรุปเย็น 17:30
- ก้อน 5+ — AI (เฟส 2) → LIFF (เฟส 3) → ขยายห้อง (เฟส 4)

## จุดเทคนิคต้องระวัง
- webhook จด DB ก่อน แล้ว worker ค่อยโหลด (LINE content API หมดอายุเร็ว · restart ต้องทำต่อได้)
- LINE ตั้ง webhook URL ที่เดียว/channel — ต่อยอด `/api/line/group_ingest` (n8n forward) หรือชี้ตรงมา
- จับกลุ่มไฟล์: รูปมาคนละ event/ลำดับไม่แน่ → ตะกร้ารอ + ตรวจเมื่อไฟล์หยุดไหล + ผลตรวจอัปเดตได้
- เก็บรูป WebP 90 วันบนดิสก์ VPS + cron ลบเก่า (ต่อยอด `_cleanup_old`)
- ชั้น AI เป็นฟังก์ชันกลางถอดเปลี่ยน provider (เริ่ม Gemini)

## คำถามที่บล็อก (ตอบก่อนถึงเฟสที่เกี่ยว)
- กลุ่ม LINE ไหน (group id) + บอทตัวเดิม/แยก
- รถส่วนกลางกี่คัน + อยู่ใน cars.Car แล้วไหม + ทะเบียน 4 หลักท้ายซ้ำข้ามคันไหม
- ใครคือคนตรวจ/อนุมัติ (สาขาเดียว/หลายคน) + ใครจ่ายกุญแจแต่ละสาขา
- เวลาสรุปเย็น 17:30 ตรงเลิกงานไหม
