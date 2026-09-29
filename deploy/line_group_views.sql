-- ════════════════════════════════════════════════════════════════════════
--  view สำหรับ "อ่านแชทแบบแยกกลุ่มชัด"  (28 ก.ย.69)
--  เจ้าของสั่ง: "จริงๆ ควรแยกชัดกลุ่มแต่ละกลุ่มนะ"
--
--      sudo -u postgres psql -d oxlet -f deploy/line_group_views.sql
--
--  ⚠️ รันหลัง `migrate` เท่านั้น (ต้องมีตาราง checkout_linegroup ก่อน)
--  ⚠️ รันซ้ำได้ (CREATE OR REPLACE)
-- ════════════════════════════════════════════════════════════════════════

-- ══ 1) สารบัญกลุ่ม — กลุ่มไหนทำงานอะไร คุยกันเยอะแค่ไหน ════════════════════
--    ไม่มีชื่อคน ไม่มีเนื้อแชท → เป็น "สารบัญ" ล้วนๆ
CREATE OR REPLACE VIEW v_line_group AS
SELECT g.group_id                       AS "group_id",
       g.name                           AS "ชื่อกลุ่ม",
       g.kind                           AS "ประเภท",
       g.kind_auto                      AS "ประเภทนี้ระบบเดาให้",
       g.channels                       AS "บอทที่อยู่ในกลุ่ม",
       g.active                         AS "ยังใช้งาน",
       count(c.id)                      AS "ข้อความที่เก็บไว้",
       max(c.sent_at)                   AS "ข้อความล่าสุด",
       g.last_seen                      AS "บอทได้ยินล่าสุด",
       g.note                           AS "หมายเหตุ"
FROM checkout_linegroup g
LEFT JOIN checkout_groupchat c ON c.group_id = g.group_id
GROUP BY g.id
ORDER BY count(c.id) DESC;


-- ══ 2) แชทกลุ่ม พร้อมชื่อ+ประเภทกลุ่ม ═══════════════════════════════════
--    ★ **ไม่มี sender_id (LINE user id)** — view นี้จึงปลอดภัยกว่าตารางดิบ
--      ใช้ `sender_name` (ชื่อเล่น) แทนตามกติกาเดิมของระบบ
CREATE OR REPLACE VIEW v_group_chat AS
SELECT c.id,
       c.sent_at                                  AS "เมื่อไหร่",
       coalesce(g.name, c.group_name, '')         AS "กลุ่ม",
       coalesce(g.kind, 'other')                  AS "ประเภทกลุ่ม",
       c.sender_name                              AS "ผู้พูด",
       c.direction                                AS "ทิศทาง",
       c.msg_type                                 AS "ชนิด",
       c.text                                     AS "ข้อความ",
       c.has_media                                AS "มีไฟล์แนบ",
       c.channel                                  AS "บอทที่ได้ยิน",
       c.group_id                                 AS "group_id"
FROM checkout_groupchat c
LEFT JOIN checkout_linegroup g ON g.group_id = c.group_id
WHERE c.chat_type = 'group';


-- ══ 3) สิทธิ์ ══════════════════════════════════════════════════════════
--  ★★ 29 ก.ย.69 — ต้องให้ `oxlet` (user ที่เว็บใช้) ก่อนใครเลย
--  view นี้เจ้าของเป็น `postgres` → ตัวเว็บที่รันด้วย `oxlet` เข้าไม่ได้โดยอัตโนมัติ
--  ลืมบรรทัดนี้ = หน้า "ฐานข้อมูล (SQL)" ตอบ `permission denied for view v_group_chat`
--  ทั้งที่ view มีอยู่จริง (เกิดขึ้นแล้ว — เจ้าของเจอตอนลองรันคำสั่งในหน้าเว็บ)
GRANT SELECT ON v_group_chat TO oxlet;
GRANT SELECT ON v_line_group TO oxlet;

--  v_group_chat มี "เนื้อแชท" → ให้เฉพาะ ro_all เท่านั้น **ห้ามให้ ro_safe**
GRANT SELECT ON v_group_chat TO ro_all;
GRANT SELECT ON v_line_group TO ro_all;

--  v_line_group เป็นสารบัญล้วน (ไม่มีชื่อคน ไม่มีแชท) — จะเปิดให้ ro_safe ก็ได้
--  เอาคอมเมนต์ออกถ้าต้องการ:
-- GRANT SELECT ON v_line_group TO ro_safe;


-- ══ 4) ตัวอย่างใช้งาน ═══════════════════════════════════════════════════
-- กลุ่มทั้งหมด + คุยกันเยอะแค่ไหน
--   SELECT * FROM v_line_group;
--
-- เฉพาะห้องโค้ชเซลล์ (Senior/Junior)
--   SELECT "เมื่อไหร่", "ผู้พูด", "ข้อความ" FROM v_group_chat
--   WHERE "ประเภทกลุ่ม" = 'coaching' ORDER BY "เมื่อไหร่" DESC LIMIT 50;
--
-- นับข้อความรายวัน แยกประเภทกลุ่ม
--   SELECT date("เมื่อไหร่") AS วัน, "ประเภทกลุ่ม", count(*)
--   FROM v_group_chat WHERE "เมื่อไหร่" >= now() - interval '14 days'
--   GROUP BY 1, 2 ORDER BY 1 DESC, 3 DESC;
