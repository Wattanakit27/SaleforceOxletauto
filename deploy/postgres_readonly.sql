-- ════════════════════════════════════════════════════════════════════════
--  เปิดให้คนอื่น "อ่าน" ฐานข้อมูลได้ โดยแก้อะไรไม่ได้เลย  (26 ก.ย.69)
--  เจ้าของสั่ง: "อยากให้คนอื่นดูได้ด้วย แต่แค่อ่านข้อมูล เพราะกลัวพัง"
--
--  รันในนาม postgres เท่านั้น:
--      sudo -u postgres psql -d oxlet -f deploy/postgres_readonly.sql
--
--  ⚠️ ไฟล์นี้ "รันซ้ำได้" ไม่พัง แต่ **ไม่ได้สร้างบัญชีคนให้** —
--     ส่วนสร้างบัญชีอยู่ท้ายไฟล์ ต้องแก้ชื่อ+รหัสเองก่อนรัน
-- ════════════════════════════════════════════════════════════════════════

-- ─────────────────────────────────────────────────────────────────────
-- ★★ อ่านก่อนตัดสินใจ — psql ตรง ≠ หน้าเว็บ "ฐานข้อมูล (SQL)"
--
--  หน้าเว็บ /dashboard/?panel=sql มีให้อยู่แล้ว และ **ปลอดภัยกว่า**:
--    · อ่านอย่างเดียวอยู่แล้ว (READ ONLY ฝั่ง Postgres)
--    · **ปิด LINE user id ของพนักงานให้อัตโนมัติ** · ซ่อน password / token
--    · ไม่ต้องแจกรหัสฐานข้อมูล ไม่ต้องสอน psql ไม่ต้องทำ SSH tunnel
--
--  ต่อ psql ตรง = **เห็นข้อมูลดิบทุกอย่างที่ role นั้นอ่านได้ ไม่มีการปิดบังใดๆ**
--  → ใช้เฉพาะคนที่ต้องเขียน SQL เอง / ต่อเครื่องมือ BI เท่านั้น
-- ─────────────────────────────────────────────────────────────────────


-- ══ 1) กลุ่มสิทธิ์ "อ่านได้ทุกตาราง" ════════════════════════════════════
--    ★ เห็นแชทลูกค้า 55,000 ข้อความ + LINE user id + ข้อมูลพนักงาน ครบทุกอย่าง
--      ให้เฉพาะคนระดับเจ้าของ/ผู้บริหารเท่านั้น
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ro_all') THEN
    CREATE ROLE ro_all NOLOGIN;
  END IF;
END $$;

GRANT CONNECT ON DATABASE oxlet TO ro_all;
GRANT USAGE   ON SCHEMA public  TO ro_all;
GRANT SELECT  ON ALL TABLES IN SCHEMA public TO ro_all;

-- ตารางที่จะสร้างใหม่ในอนาคต (ตอน migrate) ให้อ่านได้เองด้วย
-- ⚠️ default privileges ผูกกับ "ใครเป็นคนสร้างตาราง" → ต้องตั้งให้ครบทั้ง 2 role
ALTER DEFAULT PRIVILEGES FOR ROLE oxlet    IN SCHEMA public GRANT SELECT ON TABLES TO ro_all;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT SELECT ON TABLES TO ro_all;


-- ══ 2) กลุ่มสิทธิ์ "อ่านเฉพาะที่ไม่มีข้อมูลส่วนบุคคล" ═══════════════════
--    ตัวเลขโซเชียล/โฆษณา/สต๊อกรถ — ไม่มีชื่อคน ไม่มีแชท ไม่มี LINE id
--    เหมาะกับ: ทีมการตลาด · เอเจนซี · คนนอกทีมที่ต้องดูตัวเลข
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ro_safe') THEN
    CREATE ROLE ro_safe NOLOGIN;
  END IF;
END $$;

GRANT CONNECT ON DATABASE oxlet TO ro_safe;
GRANT USAGE   ON SCHEMA public  TO ro_safe;

-- ★★ เป็น "ลิสต์ที่อนุญาต" ทีละตาราง — ห้ามเปลี่ยนเป็น ALL TABLES แล้วค่อย REVOKE
--    เพราะวันที่มีตารางใหม่ (ซึ่งอาจมีข้อมูลลูกค้า) มันจะหลุดเข้ามาเองโดยไม่มีใครตัดสินใจ
--    ด้วยเหตุผลเดียวกัน **ตั้งใจไม่ตั้ง ALTER DEFAULT PRIVILEGES ให้ ro_safe**
--    → มีตารางใหม่ที่อยากให้เห็น ต้องมาเติมบรรทัดตรงนี้เอง
GRANT SELECT ON
  -- โซเชียล (ยอดวิว/ไลก์/คอมเมนต์ ของโพสต์และคลิป)
  dash_meta_post_snapshot,
  dash_meta_page_daily,
  dash_tiktok_video_snapshot,
  dash_tiktok_account_snapshot,
  dash_youtube_video_snapshot,
  dash_youtube_channel_snapshot,
  dash_social_daily,
  -- โฆษณา
  dash_meta_ad_daily,
  dash_ads_daily,
  -- สต๊อกรถ
  cars_car,
  cars_branch
TO ro_safe;

-- ⚠️ ที่ "ไม่ได้" ใส่ไว้ในลิสต์ข้างบน และเหตุผล —
--   checkout_fbchat / checkout_groupchat        แชทลูกค้า 55,000 ข้อความ
--   checkout_fbprofile / checkout_lineprofile   ชื่อ + LINE user id/PSID ของลูกค้า
--   checkout_customerneed                       ชื่อลูกค้า + ช่องทางติดต่อ 500 ราย
--   checkout_employee / checkout_checkin        ทะเบียนพนักงาน + เวลาเข้า-ออกงาน
--   cars_loginevent                             ประวัติเข้าระบบ + IP + อุปกรณ์
--   auth_user                                   บัญชีผู้ใช้ (ชื่อผู้ใช้เป็น line_<userId>)
--   dash_event_log                              **มี LINE user id ในช่อง target 464 แถว**
--   dash_kv                                     แคชแดชบอร์ด — มีชื่อ/เคสลูกค้าปนอยู่
--   dash_tiktok_account                         token ของช่อง (ถึงเข้ารหัสไว้ก็ไม่ควรให้)
--   dash_*_raw                                  คำตอบดิบจาก API — รับประกันไม่ได้ว่ามีอะไรปน


-- ══ 3) สร้างบัญชีให้แต่ละคน ════════════════════════════════════════════
--    ★ 1 คน = 1 บัญชี ห้ามใช้ร่วมกัน — ไม่งั้นเวลามีปัญหาจะไล่ไม่ได้ว่าใครทำ
--    ★ เลิกใช้/คนลาออก: DROP ROLE ชื่อนั้น (ไม่กระทบคนอื่น)
--
--    แก้ 3 อย่างก่อนรัน: ชื่อบัญชี · รหัสผ่าน · เลือก ro_safe หรือ ro_all
/*
CREATE ROLE somchai LOGIN PASSWORD 'เปลี่ยนรหัสนี้ก่อนรัน' IN ROLE ro_safe;

-- กันพลาดอีก 4 ชั้น (ชั้นที่กันได้จริงคือ GRANT ข้างบน ส่วนนี้คือกันอุบัติเหตุ)
ALTER ROLE somchai SET default_transaction_read_only = on;   -- เผลอพิมพ์ UPDATE ก็ไม่ผ่าน
ALTER ROLE somchai SET statement_timeout = '30s';            -- query หนักไม่ลากเซิร์ฟเวอร์ทั้งเครื่อง
ALTER ROLE somchai SET idle_in_transaction_session_timeout = '60s';  -- ลืมปิด transaction ค้าง
ALTER ROLE somchai CONNECTION LIMIT 3;                       -- ต่อพร้อมกันได้ 3 สาย
*/


-- ══ 4) ตรวจว่าตั้งถูกจริง ══════════════════════════════════════════════
--    รันแล้วต้องได้ reads > 0 และ ins/upd/del = 0 ทุกคน
SELECT r.rolname AS "บัญชี",
       count(*) FILTER (WHERE has_table_privilege(r.rolname, c.oid, 'SELECT')) AS "อ่านได้",
       count(*) FILTER (WHERE has_table_privilege(r.rolname, c.oid, 'INSERT')) AS "ins",
       count(*) FILTER (WHERE has_table_privilege(r.rolname, c.oid, 'UPDATE')) AS "upd",
       count(*) FILTER (WHERE has_table_privilege(r.rolname, c.oid, 'DELETE')) AS "del",
       r.rolsuper AS "superuser"
FROM pg_roles r, pg_class c
WHERE r.rolcanlogin
  AND c.relkind IN ('r','p') AND c.relnamespace = 'public'::regnamespace
GROUP BY r.rolname, r.rolsuper
ORDER BY 2 DESC;


-- ════════════════════════════════════════════════════════════════════════
--  วิธีต่อ — ฐานข้อมูลฟังแค่ 127.0.0.1 ต่อจากข้างนอกตรงๆ ไม่ได้
--
--  ★ ไม่เปิดพอร์ต 5432 ออกเน็ตเด็ดขาด — ฐานข้อมูลนี้มีแชทลูกค้า
--    วิธีที่ถูกคือ SSH tunnel (คนนั้นต้องมีสิทธิ์ ssh เข้าเครื่องอยู่แล้ว)
--
--    เครื่องของคนที่จะดู:
--        ssh -N -L 5432:127.0.0.1:5432 <user>@srv1793506.hstgr.cloud
--
--    แล้วต่อที่ localhost:5432 (psql / DBeaver / Excel / Power BI):
--        psql "host=127.0.0.1 port=5432 dbname=oxlet user=somchai"
--
--  ⚠️ อย่าลืมว่า SSH เข้าเครื่องได้ = เข้าถึงไฟล์บนเซิร์ฟเวอร์ได้ด้วย
--     ถ้าไม่อยากให้ถึงขนาดนั้น → ให้เขาใช้ **หน้าเว็บ "ฐานข้อมูล (SQL)"** แทน
-- ════════════════════════════════════════════════════════════════════════
