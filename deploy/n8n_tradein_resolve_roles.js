// =====================================================
// Resolve Roles (Trade-in) - V11  (17 ก.ย.69)
// ก๊อปทั้งไฟล์นี้ไปวางทับในช่อง Code ของโหนด "Resolve Roles"
//
// ★ ที่เปลี่ยนจาก V10: **ชื่อเล่นมาจาก LINE user id ไม่ใช่จากการเทียบชื่อที่ตั้งใน LINE**
//   โหนด "หาชื่อเล่นจาก userId (Postgres)" ส่ง `nickByUserId` มาให้ → ใช้ตัวนั้นก่อนเสมอ
//
//   ทำไม: ชื่อที่ตั้งใน LINE **เจ้าตัวเปลี่ยนเองได้ทุกเมื่อ** · มีอิโมจิ/ช่องว่างท้าย ·
//   บอทคนละตัวเห็นคนละชื่อ → เทียบด้วยชื่อเมื่อไหร่ก็มีวันหลุด จึงต้องมี Scavenger/
//   partial match/MANUAL_MAPPING มาปะกันไม่จบ · **userId ไม่เปลี่ยน เทียบแล้วจบ**
//
// ★ ของเดิมไม่ได้ลบทิ้ง — กลายเป็น "ทางสำรอง" เวลาหา userId ในทะเบียนไม่เจอ
//   (เช่นคนนอก/คนใหม่ที่ยังไม่ได้ผูกบัญชี)
// =====================================================

const items = $input.all();

// 1. ประกาศตัวแปร Global เพื่อ "กวาด" ข้อมูลมารวมกัน
let profileDisplayName = "";
let profileUserId = "";
let messageText = "";
let codeFromExtract = "";
let groupId = "";
let nickById = "";              // ★ V11 — ชื่อเล่นที่ได้จาก userId ตรงๆ (แหล่งความจริง)
let adminMasterData = [];

// 2. ลูปกวาดข้อมูล (Scavenger Loop)
// ไม่สนว่าข้อมูลจะอยู่ item ไหน เจอที่ไหนเก็บที่นั่น
for (const it of items) {
  const j = it.json || {};

  // --- A. แยก Master Data (รายชื่อ) ---
  if (j.row_number) {
    // ต้องมีคอลัมน์ "ชื่อเล่น" ถึงจะเก็บ
    if (j['ชื่อเล่น']) {
      adminMasterData.push(j);
    }
    // ถ้าเป็น Master Data เราไม่ดึง Event จากบรรทัดนี้ (ข้ามไป)
    continue;
  }

  // --- B. กวาดข้อมูล Event / Profile ---

  // ★ V11 — ชื่อเล่นจากฐานข้อมูล (มาจากโหนด "หาชื่อเล่นจาก userId (Postgres)")
  if (j.nickByUserId) nickById = String(j.nickByUserId);

  // 1. เก็บชื่อ (ถ้ามี)
  if (j.displayName) profileDisplayName = j.displayName;

  // 2. เก็บ User ID (ถ้ามี)
  if (j.userId) profileUserId = j.userId;

  // 3. เก็บข้อความ (ถ้ามี)
  if (j.text) messageText = String(j.text);

  // 4. เก็บ Code (ถ้ามี)
  if (j.code) codeFromExtract = String(j.code);

  // 5. เก็บ Group ID (หาจากทุกซอกทุกมุม)
  if (!groupId) { // เก็บแค่ครั้งเดียวถ้าเจอแล้ว
    if (j.groupId) groupId = j.groupId;
    else if (j.source && j.source.groupId) groupId = j.source.groupId;
    else if (j._line && j._line.groupId) groupId = j._line.groupId;
    else if (j.body && j.body.events && j.body.events[0]?.source?.groupId) {
      groupId = j.body.events[0].source.groupId;
    }
  }

  // userId เผื่อกรณีที่ยังไม่ได้ถูกกวาดจากช่อง userId ตรงๆ
  if (!profileUserId) {
    if (j.source && j.source.userId) profileUserId = j.source.userId;
    else if (j._line && j._line.userId) profileUserId = j._line.userId;
    else if (j.body && j.body.events && j.body.events[0]?.source?.userId) {
      profileUserId = j.body.events[0].source.userId;
    }
  }
}

// ★★ V11 — ถ้ายังไม่เจอ nickByUserId ใน items ให้ไปหยิบจากโหนด Postgres ตรงๆ
//   จำเป็นเพราะ "ต่อสายเข้า Merge" พลาดง่ายมาก (ลืมลาก / ลากผิดช่อง / Merge ตัดทิ้ง)
//   แล้วอาการที่ได้คือ "ชื่อเล่นไม่เปลี่ยน" ซึ่งดูไม่ออกเลยว่าเป็นเพราะสายไม่ถึง
//   ดึงตรงแบบนี้ = ขอแค่โหนดนั้นรันไปแล้วในรอบเดียวกัน ไม่สนว่าต่อสายยังไง
if (!nickById) {
  const NODE_NAMES = [
    "หาชื่อเล่นจาก userId (Postgres)",
    "ดึงชื่อเล่นพนักงาน (Postgres)",
    "Get Members (Master)",
  ];
  for (const name of NODE_NAMES) {
    if (nickById) break;
    // n8n มี 2 แบบตามรุ่นของโหนด (Code ใหม่ใช้ $(), Function เดิมใช้ $node)
    try { nickById = String($(name).first().json.nickByUserId || ""); } catch (e) { /* ข้าม */ }
    if (!nickById) {
      try { nickById = String($node[name].json.nickByUserId || ""); } catch (e) { /* ข้าม */ }
    }
  }
}

// 3. Helper Functions
const clean = (v) => String(v ?? "").trim();
const hasPhone = (t) => /0\d{8,9}/.test(String(t || "").replace(/[-\s]/g, ""));

const pickCodeAny = (t) => {
  const m = String(t || "").match(/\b([A-Za-z]{1,8})\s*-\s*(\d{1,8})\b/);
  return m ? `${m[1]}-${m[2]}`.toUpperCase().replace(/\s+/g, "") : "";
};

const stripEmoji = (s) =>
  String(s || "").replace(/[\uD800-\uDFFF]/g, "").replace(/[☀-➿]/g, "").trim();

// ★ V11 — ทะเบียน "กรอกชื่อเล่นจริงแล้วหรือยัง"
//   บางคนในทะเบียนช่องชื่อเล่นถูกตั้งเป็นชื่อ LINE ไปเลย (ยังไม่มีใครกรอกชื่อจริง)
//   กรณีนั้นถือว่า "ยังไม่มีชื่อเล่น" → ปล่อยให้ตัวเดาเดิม/MANUAL_MAPPING ทำงานต่อ
//   พอไปกรอกชื่อเล่นที่หน้า /dashboard/?panel=employees แล้ว ตัวนี้จะชนะเองทันที
const nickIsReal =
  !!nickById && clean(nickById).toLowerCase() !== clean(profileDisplayName).toLowerCase();

console.log("=== RESOLVE ROLES V11 ===");
console.log("nickByUserId:", nickById || "(ไม่เจอในทะเบียน)", "| ใช้ได้:", nickIsReal);
console.log("LINE name   :", profileDisplayName);
console.log("GroupID     :", groupId);

// 4. สร้าง Map ชื่อเล่นจาก Master Data (ทางสำรอง — เผื่อไม่มี nickByUserId)
const adminMap = {};
for (const a of adminMasterData) {
  const dn = clean(a.displayName);
  const nn = clean(a['ชื่อเล่น']);

  if (!dn || !nn) continue;

  adminMap[dn.toLowerCase()] = nn;

  const noEmoji = stripEmoji(dn);
  if (noEmoji && noEmoji !== dn) {
    adminMap[noEmoji.toLowerCase()] = nn;
  }
}

// 5. หาชื่อเล่นผู้ส่ง (Sender Logic)
let senderNickname = "";

if (profileDisplayName) {
  const dn = clean(profileDisplayName);
  const dnNoEmoji = stripEmoji(dn);

  // 1. หาจาก Map
  if (adminMap[dn.toLowerCase()]) senderNickname = adminMap[dn.toLowerCase()];
  else if (adminMap[dnNoEmoji.toLowerCase()]) senderNickname = adminMap[dnNoEmoji.toLowerCase()];
  else {
    // Partial match
    const key = Object.keys(adminMap).find(
      (k) => dnNoEmoji.toLowerCase().includes(k) || k.includes(dnNoEmoji.toLowerCase())
    );
    if (key) senderNickname = adminMap[key];
  }
}

// MANUAL MAPPING (ของเดิม — เหลือไว้เป็นทางสำรองสำหรับคนที่ยังไม่ได้กรอกชื่อเล่นในระบบ)
// ★ พอกรอกชื่อเล่นที่หน้า /dashboard/?panel=employees แล้ว ลบตารางนี้ทิ้งได้เลย
const MANUAL_MAPPING = {
  "miwa": "มิว",
  "wattanakit": "เบียร์"
};

const chkName = clean(profileDisplayName).toLowerCase();
if (MANUAL_MAPPING[chkName]) {
  senderNickname = MANUAL_MAPPING[chkName];
}

// ★★ V11 — ชื่อเล่นจาก userId ชนะทุกวิธีเดา (ถ้าในทะเบียนกรอกชื่อจริงไว้แล้ว)
if (nickIsReal) {
  senderNickname = nickById;
  console.log("  > ใช้ชื่อเล่นจาก userId:", senderNickname);
}

// ถ้าสุดท้ายยังว่าง: ใช้ค่าจากทะเบียน (แม้จะเท่ากับชื่อ LINE) แล้วค่อยตกไปชื่อ LINE
if (!senderNickname) senderNickname = nickById || profileDisplayName;

// 6. จัดการ Purchaser Tag (จัดซื้อ)
const pickPurchaserTag = (text) => {
  const m = String(text || "").match(/@([^\n@]+)/);
  return m ? clean(m[1]) : "";
};
const purchaserTag = pickPurchaserTag(messageText);

const mapPurchaserFromTag = (tag) => {
  const s = String(tag || "").toLowerCase();
  if (!s) return "";
  if (s.includes("tard") || s.includes("tad") || s.includes("ต๊าด") || s.includes("ตาด")) return "พี่ต๊าด";
  if (s.includes("หมี") || s.includes("bear")) return "พี่หมี";
  if (s.includes("miwa") || s.includes("miw") || s.includes("มิว")) return "มิว";
  return "";
};
const purchaserNickname = mapPurchaserFromTag(purchaserTag);

// 7. Final Output (รวมร่าง)
const mode = hasPhone(messageText) ? "case_form" : "purchase_comment";
const finalCode = (codeFromExtract || pickCodeAny(messageText)).toUpperCase();

return [
  {
    json: {
      _mode: mode,
      code: finalCode,

      // Roles
      senderNickname: senderNickname,
      purchaserTag: purchaserTag,
      purchaserNickname: purchaserNickname,

      // Profile
      userId: profileUserId,
      displayName: profileDisplayName,

      // ★ V11 — เก็บไว้ดูเวลาไล่ปัญหา (ไม่ได้เอาไปลงชีต)
      nickByUserId: nickById,
      nickSource: nickIsReal ? "userId" : (senderNickname === profileDisplayName ? "ชื่อไลน์" : "เดาจากชื่อ"),

      // Group ID
      groupId: groupId,

      // Payload
      text: messageText,
      lineEventType: "message"
    }
  }
];
