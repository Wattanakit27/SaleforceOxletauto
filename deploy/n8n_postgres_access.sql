-- ============================================================
-- เปิดให้ n8n อ่าน "ทะเบียนพนักงาน" จาก Postgres ของเราโดยตรง (แทนโหนด Google Sheets)
-- รันบนเซิร์ฟเวอร์:
--   ครั้งแรก (ตั้งรหัส):  read -rs -p "รหัส n8n: " PW; echo
--                         sudo -u postgres psql -d oxlet -v pw="'$PW'" -f deploy/n8n_postgres_access.sql
--   รันซ้ำ (ซ่อมสิทธิ์):  sudo -u postgres psql -d oxlet -f deploy/n8n_postgres_access.sql
--                         ← ไม่ส่ง pw = ไม่แตะรหัสเดิม (credential ใน n8n ไม่หลุด)
-- ⚠️ **ห้ามเขียนรหัสผ่านลงไฟล์นี้** (ไฟล์อยู่ใน git = ใครอ่าน repo ก็เห็น) — ส่งผ่าน -v pw=... เท่านั้น
-- ★ 16 ก.ย.69
--
-- หลักการ: **ไม่ให้สิทธิ์ตาราง ให้แต่ view ที่จำเป็น**
--   - อ่านได้เฉพาะ 2 view นี้ (ไม่เห็นแชทลูกค้า/เคสเบิกรถ/ตารางอื่นเลย)
--   - เขียนได้ช่องเดียวคือ "หมายเหตุ" ของพนักงาน (workflow เช็คชื่อเขียนช่องนี้)
--   - ห้ามลบ/แก้อย่างอื่น · ห้ามสร้างตาราง
-- ============================================================

-- 1) ผู้ใช้สำหรับ n8n
--    ★ รันซ้ำได้ปลอดภัย: **ไม่ส่ง -v pw= มา = ไม่แตะรหัสผ่านเดิม** (มีแต่เพิ่ม/ซ่อมสิทธิ์)
--    ⚠️★ 16 ก.ย.69 — เวอร์ชันแรกสั่ง ALTER ROLE ... PASSWORD ทุกครั้งที่รัน
--       → พอรันไฟล์ซ้ำตอน deploy (วาง placeholder ไปทั้งบรรทัด) รหัสถูกเปลี่ยนโดยไม่ตั้งใจ
--       n8n ที่ตั้งค่าไว้แล้วล็อกอินไม่ได้ทันที และดูเหมือน "อยู่ดีๆ ก็พัง" หาสาเหตุยาก
--    เปลี่ยนรหัสเมื่อไหร่ค่อยส่ง:  -v pw="'รหัสใหม่'"
\if :{?pw}
\else
\set pw ''
\endif

SELECT CASE
         WHEN :'pw' <> '' AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'n8n')
              THEN 'ALTER ROLE n8n LOGIN PASSWORD ' || quote_literal(:'pw')
         WHEN :'pw' <> ''
              THEN 'CREATE ROLE n8n LOGIN PASSWORD ' || quote_literal(:'pw')
         WHEN EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'n8n')
              THEN 'SELECT ''มี role n8n อยู่แล้ว · ไม่ได้ส่ง -v pw= มา จึงคงรหัสเดิมไว้'' AS note'
         ELSE 'DO $$ BEGIN RAISE EXCEPTION ''ยังไม่มี role n8n — ครั้งแรกต้องส่งรหัสมาด้วย (-v pw=...)''; END $$'
       END AS stmt \gset
:stmt ;

GRANT CONNECT ON DATABASE oxlet TO n8n;
GRANT USAGE ON SCHEMA public TO n8n;

-- 2) view: 1 แถวต่อ "คน" — เอาไปแทนโหนดอ่านชีตรายชื่อพนักงาน
--    line_user_ids = ไอดีครบทุกบอท (บอทเดิม/บอทใหม่) — จุดที่ชีตทำไม่ได้
--
-- ⚠️★ 17 ก.ย.69 — ต้อง DROP ก่อน CREATE (เจอตอนรันจริงบนเซิร์ฟเวอร์)
--    `CREATE OR REPLACE VIEW` ของ Postgres **ต่อคอลัมน์ท้ายได้อย่างเดียว
--    แทรกกลาง/เปลี่ยนชื่อคอลัมน์ไม่ได้** → ตอนเพิ่ม "ต้องเช็คชื่อ" ไว้กลางลิสต์
--    จะได้ `ERROR: cannot change name of view column "line_user_ids" to "ต้องเช็คชื่อ"`
--    แล้ว **view ค้างเป็นของเก่าเงียบๆ** (GRANT ผ่าน แต่คอลัมน์ใหม่ไม่มี)
--    สิทธิ์ที่ DROP ไปจะถูก GRANT คืนด้านล่างในสคริปต์เดียวกัน
DROP VIEW IF EXISTS v_employees;
CREATE VIEW v_employees AS
SELECT e.id                AS employee_id,
       e.nickname          AS "ชื่อเล่น",
       e.display_name      AS display_name,
       e.position          AS "ตำแหน่งงาน",
       e.work_start        AS "เวลาเข้างาน",
       e.day_off           AS "วันหยุด",
       e.note              AS "หมายเหตุ",
       e.group_id,
       e.active,
       e.track_checkin      AS "ต้องเช็คชื่อ",   -- false = ผู้บริหาร ไม่เก็บเวลาเข้างาน
       COALESCE(array_agg(p.user_id) FILTER (WHERE p.user_id IS NOT NULL), '{}') AS line_user_ids
FROM checkout_employee e
LEFT JOIN checkout_lineprofile p ON p.employee_id = e.id
GROUP BY e.id;

-- 3) view: 1 แถวต่อ "บัญชี LINE" — ใช้ตอนรู้ userId แล้วอยากรู้ว่าใคร (เช็คชื่อ/แจ้งลา)
DROP VIEW IF EXISTS v_employee_line;
CREATE VIEW v_employee_line AS
SELECT p.user_id,
       p.channel           AS line_account,   -- crm = บอทเดิม · push = บอทใหม่
       e.id                AS employee_id,
       e.nickname          AS "ชื่อเล่น",
       e.position          AS "ตำแหน่งงาน",
       e.work_start        AS "เวลาเข้างาน",
       e.day_off           AS "วันหยุด",
       e.track_checkin      AS "ต้องเช็คชื่อ",
       e.active
FROM checkout_lineprofile p
JOIN checkout_employee e ON e.id = p.employee_id;

GRANT SELECT ON v_employees, v_employee_line TO n8n;

-- 4) เขียนได้ช่องเดียว: หมายเหตุ (ลา/สาย) — ต้องมีสิทธิ์อ่านตารางด้วยถึงจะ UPDATE ... WHERE ได้
GRANT SELECT (id, nickname, note), UPDATE (note) ON checkout_employee TO n8n;

-- ตัวอย่างที่ n8n ใช้:
--   อ่านรายชื่อ:      SELECT * FROM v_employees WHERE active;
--   หาว่าใครส่งมา:    SELECT * FROM v_employee_line WHERE user_id = $1;
--   บันทึกหมายเหตุ:   UPDATE checkout_employee SET note = $2
--                     WHERE id = (SELECT employee_id FROM v_employee_line WHERE user_id = $1);

-- 5) เช็คชื่อเข้างาน (ย้ายมาจากชีต "เช็คชื่อ" · ★ 16 ก.ย.69)
--    n8n ต้อง "อ่าน + เขียน" ตารางนี้ (ต่างจากทะเบียนพนักงานที่เขียนได้ช่องเดียว)
--    ⚠️ ต้อง `manage.py migrate` ให้ตารางเกิดก่อน ไม่งั้นบรรทัดนี้จะ error
GRANT SELECT, INSERT, UPDATE ON checkout_checkin TO n8n;
GRANT USAGE, SELECT ON SEQUENCE checkout_checkin_id_seq TO n8n;

-- ตัวอย่างที่ n8n ใช้ (ดูของจริงในไฟล์ deploy/n8n_checkin_v2.json):
--   เช็คว่าวันนี้เช็คไปหรือยัง:
--     SELECT count(*)::int AS already FROM checkout_checkin
--     WHERE user_id = $1 AND date_iso = $2::date;
--
--   บันทึก (ส่ง JSON ก้อนเดียว → พารามิเตอร์ตัวเดียว อ่านง่ายกว่าไล่ 12 ช่อง):
--     WITH d AS (SELECT $1::jsonb AS j)
--     INSERT INTO checkout_checkin (user_id, employee_id, display_name, date_iso, checkin_at,
--            time_hm, work_start, status, reason, time_source, full_address, province, note, raw,
--            created_at, updated_at)
--     SELECT j->>'userId', (SELECT employee_id FROM v_employee_line WHERE user_id = j->>'userId'),
--            coalesce(j->>'displayName',''), (j->>'dateIso')::date,
--            nullif(j->>'checkinAt','')::timestamptz, coalesce(j->>'timeHm',''),
--            coalesce(j->>'workStart',''), coalesce(j->>'status','abnormal'),
--            coalesce(j->>'reason',''), coalesce(j->>'timeSource',''),
--            coalesce(j->>'fullAddress',''), coalesce(j->>'province',''), '',
--            coalesce(j->'raw','{}'::jsonb), now(), now()
--     FROM d
--     ON CONFLICT (user_id, date_iso) DO UPDATE SET ... ;

-- 6) โปรไฟล์คน LINE — ให้ workflow "ซื้อขายเทิร์นรถ" เลิกใช้แท็บชีต "รายชื่อสมาชิกกลุ่ม"
--    (★ 17 ก.ย.69 · เจ้าของสั่ง "เปลี่ยนโหนดชีตเป็นโหนด Postgres ในการเก็บชื่อเล่น")
--    อ่าน: เอาไปทำ map ชื่อที่ตั้งใน LINE → ชื่อเล่น · เขียน: อัปเดตชื่อที่ตั้งใน LINE เท่านั้น
GRANT SELECT, INSERT, UPDATE ON checkout_lineprofile TO n8n;
GRANT USAGE, SELECT ON SEQUENCE checkout_lineprofile_id_seq TO n8n;

-- ❗ n8n **ห้ามแตะ nickname / is_employee / employee_id** — 3 ช่องนี้เป็นของระบบเรา
--    (จับคู่กับทะเบียนพนักงานเอง) · ถ้าเขียนทับด้วยค่าว่าง คนที่จับคู่ไว้แล้ว
--    จะถูกรีเซ็ตกลับเป็น "ลูกค้า" ทุกครั้งที่พิมพ์ — คำสั่งใน
--    deploy/n8n_members_postgres.json เขียนแค่ display_name / group_id / last_seen
--    (สิทธิ์ระดับคอลัมน์บังคับไม่ได้เพราะต้อง INSERT ทั้งแถว → คุมด้วยตัวคำสั่งแทน)
--
-- ตรวจว่า map ชื่อได้กี่คน:
--   SELECT count(*) FROM checkout_lineprofile WHERE nickname <> '';
