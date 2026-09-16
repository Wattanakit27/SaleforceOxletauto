-- ============================================================
-- เปิดให้ n8n อ่าน "ทะเบียนพนักงาน" จาก Postgres ของเราโดยตรง (แทนโหนด Google Sheets)
-- รันบนเซิร์ฟเวอร์:
--   sudo -u postgres psql -d oxlet -v pw="'รหัสที่ตั้งเอง'" -f deploy/n8n_postgres_access.sql
-- ⚠️ **ห้ามเขียนรหัสผ่านลงไฟล์นี้** (ไฟล์อยู่ใน git = ใครอ่าน repo ก็เห็น) — ส่งผ่าน -v pw=... เท่านั้น
-- ★ 16 ก.ย.69
--
-- หลักการ: **ไม่ให้สิทธิ์ตาราง ให้แต่ view ที่จำเป็น**
--   - อ่านได้เฉพาะ 2 view นี้ (ไม่เห็นแชทลูกค้า/เคสเบิกรถ/ตารางอื่นเลย)
--   - เขียนได้ช่องเดียวคือ "หมายเหตุ" ของพนักงาน (workflow เช็คชื่อเขียนช่องนี้)
--   - ห้ามลบ/แก้อย่างอื่น · ห้ามสร้างตาราง
-- ============================================================

-- 1) ผู้ใช้สำหรับ n8n — รหัสผ่านมาจาก -v pw=... (ไม่รับค่า = หยุด ไม่สร้างรหัสเดาง่ายทิ้งไว้)
\if :{?pw}
\else
\echo '*** ต้องส่งรหัสผ่านมาด้วย: psql -d oxlet -v pw="''รหัสที่ตั้งเอง''" -f deploy/n8n_postgres_access.sql'
\quit
\endif

SELECT CASE WHEN EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'n8n')
            THEN 'ALTER ROLE n8n LOGIN PASSWORD ' || quote_literal(:'pw')
            ELSE 'CREATE ROLE n8n LOGIN PASSWORD ' || quote_literal(:'pw')
       END AS stmt \gset
:stmt ;

GRANT CONNECT ON DATABASE oxlet TO n8n;
GRANT USAGE ON SCHEMA public TO n8n;

-- 2) view: 1 แถวต่อ "คน" — เอาไปแทนโหนดอ่านชีตรายชื่อพนักงาน
--    line_user_ids = ไอดีครบทุกบอท (บอทเดิม/บอทใหม่) — จุดที่ชีตทำไม่ได้
CREATE OR REPLACE VIEW v_employees AS
SELECT e.id                AS employee_id,
       e.nickname          AS "ชื่อเล่น",
       e.display_name      AS display_name,
       e.position          AS "ตำแหน่งงาน",
       e.work_start        AS "เวลาเข้างาน",
       e.day_off           AS "วันหยุด",
       e.note              AS "หมายเหตุ",
       e.group_id,
       e.active,
       COALESCE(array_agg(p.user_id) FILTER (WHERE p.user_id IS NOT NULL), '{}') AS line_user_ids
FROM checkout_employee e
LEFT JOIN checkout_lineprofile p ON p.employee_id = e.id
GROUP BY e.id;

-- 3) view: 1 แถวต่อ "บัญชี LINE" — ใช้ตอนรู้ userId แล้วอยากรู้ว่าใคร (เช็คชื่อ/แจ้งลา)
CREATE OR REPLACE VIEW v_employee_line AS
SELECT p.user_id,
       p.channel           AS line_account,   -- crm = บอทเดิม · push = บอทใหม่
       e.id                AS employee_id,
       e.nickname          AS "ชื่อเล่น",
       e.position          AS "ตำแหน่งงาน",
       e.work_start        AS "เวลาเข้างาน",
       e.day_off           AS "วันหยุด",
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
