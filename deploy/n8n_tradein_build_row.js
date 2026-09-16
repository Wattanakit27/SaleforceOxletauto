// =====================================================
// Build Sheet Row (Trade-in) - v20  (17 ก.ย.69)
// โหนด "Build Sheet Row (Trade-in)" ใน workflow ซื้อขายเทิร์นรถ
// ก๊อปทั้งไฟล์นี้ไปวางทับในช่อง Code ของโหนดนั้นได้เลย
//
// ที่แก้จาก v19:
//  9. ★ กลุ่มเคส HOT — เปลี่ยนเป็นไอดีฝั่งบอท OxletautoGiveLead และรองรับ 2 กลุ่ม
//     (พี่หมี / พี่ต๊าด) · ไอดีเดิมเป็นของบอทเก่า คนละ provider → เงื่อนไขไม่เคยเข้าเลย
// 10. ★ "จัดซื้อ" เติมจากเจ้าของกลุ่มให้ เมื่อไม่มีใครถูก @tag (ไม่ทับค่าที่ @tag มา)
//
// เดิม v19:
// 1. Sender Override (Advanced)
// 2. รวม "ขายเพราะ" + "เพิ่มเติม" + "หมายเหตุ" เป็นข้อความเดียว
// 3. แก้ปัญหาการกด Enter (ตัดข้อความ)
// 4. Customer Name: Use Lead No if Name is empty
// 5. Skip groupId: C6fcc3c298417bb71fc3afefd29636a51 (ห้องเก็บรถ)
// 6. ลบ @tag + emoji ออกจากคอมเมนท์จัดซื้อ
// 7. ลบ @tag + emoji ออกจาก finalProfile
// 8. เพิ่มคอลัมน์ "รถตามสูตร" - map รุ่นรถเข้า dropdown
// =====================================================

const items = $input.all();
if (!items || items.length === 0) return [];

const item = items[0].json || {};

const mode = item._mode || "";
const text = item.text || "";
const code = (item.code || "").toUpperCase();

// ตัวแปร Sender (ใช้ let เพื่อให้แก้ค่าได้)
let senderNickname = item.senderNickname || "";
const purchaserNickname = item.purchaserNickname || "";
const groupId = item.groupId || item.source?.groupId || item._line?.groupId || "";

// =====================================================
// ★ v20 — ทะเบียนกลุ่ม (ไอดีฝั่งบอท OxletautoGiveLead)
//
// ⚠️ ไอดีกลุ่มของ LINE "ออกต่อ provider" — กลุ่มเดียวกันมีไอดีคนละตัว
//    ในสายตาบอทแต่ละตัว · โหนด LINE - Get Profile ใช้เครดิต OxletautoGiveLead
//    ดังนั้นไอดีที่วิ่งเข้ามาต้องเป็นชุดนี้เท่านั้น
//
// เคส HOT แยกกลุ่มตามคนจัดซื้อ แต่กติกาเหมือนกันหมด = HOT ทั้งคู่
// =====================================================
const GROUP_HOT = {
  "C0ad44e22acf81cd6af619da15ffb363d": "พี่หมี",
  "C6a6450337d5588fdb0882f57d2a09cd4": "พี่ต๊าด",
};

// ⚠️ 2 ตัวล่างยังเป็นไอดีของบอทเก่า — ยังไม่ได้แก้ (รอยืนยันว่าเป็นกลุ่มไหน)
//    ตราบใดที่ยังไม่แก้ เงื่อนไข VERY HOT และตัวกันกลุ่ม "ห้องเก็บรถ" จะไม่ทำงาน
const GROUP_VERY_HOT = "C3c65c4e97b1df1cadf1395cdefba7c3a";
const GROUP_IGNORED = "C6fcc3c298417bb71fc3afefd29636a51"; // ห้องเก็บรถ

// 🚫 Skip if this is the ignored group (ห้องเก็บรถ)
if (groupId === GROUP_IGNORED) {
  console.log("⚠️ Skipping - Ignored Group (ห้องเก็บรถ):", groupId);
  return [];
}

console.log("=== BUILD SHEET ROW v20 ===");
console.log("Code:", code);
console.log("GroupId:", groupId, "->", GROUP_HOT[groupId] || "(ไม่ใช่กลุ่ม HOT)");
console.log("Original Sender:", senderNickname);

// =====================================================
// Helper Functions
// =====================================================
const clean = (v) => String(v ?? "").replace(/\s+/g, " ").trim();

const extractPhone = (text) => {
  const s = String(text || "").replace(/[-\s]/g, "");
  const m = s.match(/0\d{8,9}/);
  return m ? m[0] : "";
};

const pickCode = (t) => {
  const m = String(t || "").match(/\b([A-Za-z]{1,8})\s*-\s*(\d{1,8})\b/);
  return m ? `${m[1]}-${m[2]}`.toUpperCase().replace(/\s+/g, "") : "";
};

const extractLeadNo = (text) => {
  const match = String(text || "").match(/(?:Lead\s*No|Ac\s*Lead|Ref\s*No)[^:]*[:\s]+([A-Za-z0-9-]+)/i);
  return match ? match[1].trim() : "";
};

// =====================================================
// Car Model Dropdown Mapping
// =====================================================
const CAR_DROPDOWN = [
  "Civic", "Revo cab ตัวเตี้ย", "Fortuner", "D Max", "Mazda2",
  "City 4 ประตู", "City 5 ประตู", "Benz", "BMW", "Brio",
  "Yaris Ativ", "Yaris 5 ประตูตัวเก่า", "Sylphy", "CRV", "Vios",
  "MuX", "Revo 4 ประตู ตัวสูง", "Almera", "Jazz", "New Yaris 5 ประตู",
  "Pajero", "Revo 4 ประตู ตัวเตี้ย", "Xpander", "Accord",
  "Altis", "Innova", "CX-3", "Ford Ranger", "Everest",
  "New Commuter", "Corolla Cross", "Mu7", "HRV", "Mirage",
  "Mazda3", "Vellfire", "Vigo", "Almera Turbo", "Almera Turbo VL",
  "Commuter", "Yaris Cross", "Alphard", "Camry", "Hyundai",
  "Majesty", "MG", "Prius", "Ventury", "Veloz",
  "Attrage", "BRV", "CHR", "CX-30", "Revo cab ตัวสูง",
  "XL7", "Terra", "Teana", "Vigo LPG", "Swift"
];

const matchCarDropdown = (carText) => {
  if (!carText || carText.trim() === "" || carText === "-") return "";

  const lower = carText.toLowerCase().replace(/[-\s]+/g, " ").trim();

  // === Priority 1: Revo variants (ต้องเช็คก่อนเพราะมีหลายรุ่น) ===
  if (/revo|รีโว/.test(lower)) {
    if (/cab|แค็บ|แคป/.test(lower) && /สูง|4x4|ยก/.test(lower)) return "Revo cab ตัวสูง";
    if (/cab|แค็บ|แคป/.test(lower)) return "Revo cab ตัวเตี้ย";
    if (/4\s*ประตู/.test(lower) && /สูง|4x4|ยก/.test(lower)) return "Revo 4 ประตู ตัวสูง";
    if (/4\s*ประตู/.test(lower)) return "Revo 4 ประตู ตัวเตี้ย";
    // Default Revo ถ้าไม่ระบุ
    if (/สูง|4x4|ยก/.test(lower)) return "Revo 4 ประตู ตัวสูง";
    return "Revo cab ตัวเตี้ย";
  }

  // === Priority 2: Vigo variants ===
  if (/vigo|วีโก้/.test(lower)) {
    if (/lpg|แก๊ส/.test(lower)) return "Vigo LPG";
    return "Vigo";
  }

  // === Priority 3: Yaris variants (ต้องเช็คก่อน generic) ===
  if (/yaris|ยาริส/.test(lower)) {
    if (/cross|ครอส/.test(lower)) return "Yaris Cross";
    if (/ativ|เอทีฟ|เอทิฟ/.test(lower)) return "Yaris Ativ";
    if (/new|ใหม่/.test(lower) && /5\s*ประตู/.test(lower)) return "New Yaris 5 ประตู";
    if (/5\s*ประตู|hatchback|แฮทช์แบ็ค/.test(lower)) {
      if (/เก่า|old/.test(lower)) return "Yaris 5 ประตูตัวเก่า";
      return "New Yaris 5 ประตู";
    }
    return "Yaris Ativ"; // default Yaris
  }

  // === Priority 4: Almera variants ===
  if (/almera|อัลเมร่า/.test(lower)) {
    if (/turbo\s*vl/.test(lower)) return "Almera Turbo VL";
    if (/turbo|เทอร์โบ/.test(lower)) return "Almera Turbo";
    return "Almera";
  }

  // === Priority 5: City variants ===
  if (/city|ซิตี้/.test(lower)) {
    if (/5\s*ประตู|hatchback|แฮทช์แบ็ค/.test(lower)) return "City 5 ประตู";
    if (/4\s*ประตู|sedan|ซีดาน/.test(lower)) return "City 4 ประตู";
    return "City 4 ประตู"; // default City
  }

  // === Priority 6: Commuter variants ===
  if (/commuter|คอมมิวเตอร์/.test(lower)) {
    if (/new|ใหม่/.test(lower)) return "New Commuter";
    return "Commuter";
  }

  // === Priority 7: Corolla Cross (ต้องเช็คก่อน Altis) ===
  if (/corolla\s*cross|โครอลล่า\s*ครอส/.test(lower)) return "Corolla Cross";

  // === Priority 8: Keyword matching (เรียงจากยาวไปสั้น) ===
  const KEYWORD_MAP = [
    // Honda
    { keywords: [/civic|ซีวิค/], value: "Civic" },
    { keywords: [/accord|แอคคอร์ด/], value: "Accord" },
    { keywords: [/cr-?v|ซีอาร์วี/], value: "CRV" },
    { keywords: [/hr-?v|เอชอาร์วี/], value: "HRV" },
    { keywords: [/jazz|แจ๊ส/], value: "Jazz" },
    { keywords: [/brio|บริโอ/], value: "Brio" },
    { keywords: [/br-?v|บีอาร์วี/], value: "BRV" },

    // Toyota
    { keywords: [/fortuner|ฟอร์จูนเนอร์|ฟอจูนเนอร์|fotuner/], value: "Fortuner" },
    { keywords: [/altis|อัลติส/], value: "Altis" },
    { keywords: [/camry|แคมรี่/], value: "Camry" },
    { keywords: [/vios|วีออส/], value: "Vios" },
    { keywords: [/innova|อินโนว่า/], value: "Innova" },
    { keywords: [/alphard|อัลฟาร์ด/], value: "Alphard" },
    { keywords: [/vellfire|เวลไฟร์/], value: "Vellfire" },
    { keywords: [/c-?hr|ซีเอชอาร์/], value: "CHR" },
    { keywords: [/prius|พรีอุส/], value: "Prius" },
    { keywords: [/veloz|เวโลซ/], value: "Veloz" },
    { keywords: [/majesty|มาเจสตี้/], value: "Majesty" },

    // Nissan
    { keywords: [/sylphy|ซิลฟี่/], value: "Sylphy" },
    { keywords: [/teana|ทีน่า/], value: "Teana" },
    { keywords: [/terra|เทอร์ร่า/], value: "Terra" },

    // Mazda
    { keywords: [/mazda\s*3|มาสด้า\s*3/], value: "Mazda3" },
    { keywords: [/mazda\s*2|มาสด้า\s*2/], value: "Mazda2" },
    { keywords: [/cx-?30|ซีเอ็กซ์\s*30/], value: "CX-30" },
    { keywords: [/cx-?3|ซีเอ็กซ์\s*3/], value: "CX-3" },

    // Isuzu
    { keywords: [/d-?\s*max|ดีแม็กซ์|ดีแมก/], value: "D Max" },
    { keywords: [/mu-?x|มิว\s*เอ็กซ์/], value: "MuX" },
    { keywords: [/mu-?7|mu\s*7|มิว\s*7/], value: "Mu7" },

    // Mitsubishi
    { keywords: [/pajero|ปาเจโร่/], value: "Pajero" },
    { keywords: [/xpander|เอ็กซ์แพนเดอร์/], value: "Xpander" },
    { keywords: [/mirage|มิราจ/], value: "Mirage" },
    { keywords: [/attrage|แอททราจ/], value: "Attrage" },

    // Ford
    { keywords: [/ranger|เรนเจอร์/], value: "Ford Ranger" },
    { keywords: [/everest|เอเวอเรสต์/], value: "Everest" },

    // Suzuki
    { keywords: [/swift|สวิฟท์/], value: "Swift" },
    { keywords: [/xl-?7|เอ็กซ์แอล\s*7/], value: "XL7" },

    // Luxury / Others
    { keywords: [/benz|เบนซ์|mercedes/], value: "Benz" },
    { keywords: [/bmw|บีเอ็ม/], value: "BMW" },
    { keywords: [/hyundai|ฮุนได/], value: "Hyundai" },
    { keywords: [/mg|เอ็มจี/], value: "MG" },
    { keywords: [/ventury|เวนจูรี่/], value: "Ventury" },
  ];

  for (const entry of KEYWORD_MAP) {
    for (const regex of entry.keywords) {
      if (regex.test(lower)) {
        console.log(`✅ Car Dropdown Match: "${carText}" → "${entry.value}"`);
        return entry.value;
      }
    }
  }

  // === Priority 9: Exact match with dropdown (case-insensitive) ===
  for (const dropdown of CAR_DROPDOWN) {
    if (lower.includes(dropdown.toLowerCase())) {
      console.log(`✅ Car Dropdown Exact: "${carText}" → "${dropdown}"`);
      return dropdown;
    }
  }

  console.log(`⚠️ Car Dropdown No Match: "${carText}"`);
  return "";
};

// =====================================================
// 1. purchase_comment (ลบ @tag + emoji)
// =====================================================
if (mode === "purchase_comment") {
  let commentText = text
    .replace(/^[A-Za-z]{1,8}\s*-\s*\d{1,8}\b/, "")  // ลบ Code ด้านหน้า
    .replace(/@[^\n]+$/g, "")                        // ลบ @tag + ทุกอย่างท้ายบรรทัด
    .replace(/[@•★☆♡♥✨]/g, "")                      // ลบ emoji พิเศษที่เหลือ
    .replace(/\s+/g, " ")                            // ลบช่องว่างซ้ำ
    .trim();

  console.log("✓ Purchase Comment Mode");
  console.log("  Comment:", commentText);

  return [{
    json: {
      _mode: "purchase_comment",
      code,
      comment: commentText,
      purchaserNickname
    }
  }];
}

// =====================================================
// 2. case_form Parsing
// =====================================================

const lines = text.split("\n").map(l => l.trim()).filter(Boolean);

// LOGIC 1: Sender Override (Improved)
const codeLine = lines.find(l => pickCode(l) === code) || lines[0];
let senderFound = false;

if (codeLine) {
    const codePattern = new RegExp(code.replace(/-/g, "\\s*-?\\s*"), "i");
    const suffix = codeLine.replace(codePattern, "").trim();

    const turnMatch = suffix.match(/^(?:เทิร์น|เทริน|จาก)\s*(?:เซลล์|เซล|sale)?\s*([^\s]+)/i);

    if (turnMatch) {
         const possibleName = clean(turnMatch[1]);
         const ignoreWords = ["รถ", "ครับ", "ค่ะ", "คับ", "คาบ", "ka", "krub"];
         if (!ignoreWords.includes(possibleName) && possibleName.length > 1) {
             senderNickname = possibleName;
             senderFound = true;
             console.log("Sender Overridden (After Code):", senderNickname);
         }
    }
}

if (!senderFound) {
    const salesMatch = text.match(/(?:จาก)?\s*(?:เซลล์|เซล|sale)\s*([^\s\n]+)/i);
    if (salesMatch) {
        senderNickname = clean(salesMatch[1]);
        console.log("Sender Overridden (Keyword Search):", senderNickname);
    }
}

let modelRaw = "";
let plate = "";
let phone = "";
let customerName = "";
let channelFromCustomer = "";
let channelRaw = "";
let ads = "";

// --- 🔍 LINE SCANNER (รองรับการกด Enter) ---
let profileParts = [];
let currentProfileText = "";
let isInProfile = false;

for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const lower = line.toLowerCase();

    // เช็คว่าเป็นบรรทัดเริ่มต้นของโปรไฟล์
    if (lower.startsWith("ขายเพราะ") || lower.startsWith("เหตุผล") || lower.startsWith("สาเหตุ")) {
        if (currentProfileText) {
            profileParts.push(currentProfileText.trim());
        }
        currentProfileText = line.replace(/^(ขายเพราะ|เหตุผลขาย|เหตุผล|สาเหตุ)\s*[:：]?\s*/i, "").trim();
        isInProfile = true;
    }
    else if (lower.startsWith("เพิ่มเติม")) {
        if (currentProfileText) {
            profileParts.push(currentProfileText.trim());
        }
        currentProfileText = line.replace(/^เพิ่มเติม\s*[:：]?\s*/i, "").trim();
        isInProfile = true;
    }
    else if (lower.startsWith("หมายเหตุ")) {
        if (currentProfileText) {
            profileParts.push(currentProfileText.trim());
        }
        currentProfileText = line.replace(/^หมายเหตุ\s*[:：]?\s*/i, "").trim();
        isInProfile = true;
    }
    else if (lower.startsWith("รุ่น")) {
        if (currentProfileText) {
            profileParts.push(currentProfileText.trim());
            currentProfileText = "";
        }
        isInProfile = false;
        modelRaw = line.replace(/^รุ่น\s*[:：]?\s*/i, "").trim();
    }
    else if (lower.startsWith("ทะเบียน")) {
        if (currentProfileText) {
            profileParts.push(currentProfileText.trim());
            currentProfileText = "";
        }
        isInProfile = false;
        plate = line.replace(/^ทะเบียน\s*[:：]?\s*/i, "").trim();
    }
    else if (lower.startsWith("ads")) {
        if (currentProfileText) {
            profileParts.push(currentProfileText.trim());
            currentProfileText = "";
        }
        isInProfile = false;
        ads = line.replace(/^ads\s*[:：]?\s*/i, "").trim();
    }
    else if (lower.startsWith("ช่องทาง")) {
        if (currentProfileText) {
            profileParts.push(currentProfileText.trim());
            currentProfileText = "";
        }
        isInProfile = false;
        channelRaw = line.replace(/^ช่องทาง\s*[:：]?\s*/i, "").trim();
    }
    else if (lower.startsWith("ชื่อลูกค้า")) {
        if (currentProfileText) {
            profileParts.push(currentProfileText.trim());
            currentProfileText = "";
        }
        isInProfile = false;
        let raw = line.replace(/^ชื่อลูกค้า\s*[:：]?\s*/i, "").trim();
        if (raw.includes("/")) {
             const parts = raw.split("/");
             customerName = clean(parts[0]);
             channelFromCustomer = clean(parts[1]);
        } else {
             customerName = raw;
        }
    }
    else if (isInProfile && line.length > 0) {
        // บรรทัดต่อเนื่อง - ต่อข้อความเข้ากับบรรทัดก่อนหน้า
        currentProfileText += " " + line.trim();
    }
}

// บันทึก profile สุดท้าย
if (currentProfileText) {
    profileParts.push(currentProfileText.trim());
}

// --- Fallback Parsing ---
phone = extractPhone(text);

if (!modelRaw) {
    const contentLines = lines.filter(l => !pickCode(l) && !extractPhone(l) && !l.includes("@"));
    const carKeywords = /civic|city|accord|crv|cr-v|hrv|hr-v|jazz|brio|brv|br-v|yaris|vios|altis|camry|fortuner|fotuner|revo|vigo|chr|c-hr|alphard|vellfire|innova|commuter|attrage|sylphy|almera|teana|note|march|navara|mazda|cx-3|cx-5|cx-8|cx-30|pajero|xpander|mirage|triton|d-max|dmax|mu-x|mux|mu-7|sienta|everest|ranger|bt-50|bt50|swift|xl7|terra|ventury|veloz|mg|hyundai|benz|bmw|prius|majesty/i;

    for (const line of contentLines) {
        if (/^(ขายเพราะ|เหตุผล|เพิ่มเติม|หมายเหตุ|ทะเบียน|ads|ชื่อลูกค้า|ช่องทาง)/i.test(line)) continue;
        if (carKeywords.test(line)) {
            modelRaw = line;
            break;
        }
    }

    if (!modelRaw && contentLines.length > 0) {
        for (const line of contentLines) {
             if (/^(ขายเพราะ|เหตุผล|เพิ่มเติม|หมายเหตุ|ทะเบียน|ads|ชื่อลูกค้า|ช่องทาง|เทิร์น|ขาย|รับซื้อ|เซลล์)/i.test(line)) continue;
             modelRaw = line;
             break;
        }
    }
}

if (!plate) {
    const platePattern = /([ก-ฮ]{1,3}\s*-?\s*\d{3,4}|\d{1,2}[ก-ฮ]{2}\s*-?\s*\d{3,4})/;
    const m = text.match(platePattern);
    if (m) plate = clean(m[0].replace(/\s/g, ""));
}

let carModel = clean(modelRaw).replace(/^รุ่น\s*[:：]?\s*/i, "");

// Map car model to dropdown value
const carDropdownValue = matchCarDropdown(carModel);
console.log("Car Model Raw:", carModel);
console.log("Car Dropdown:", carDropdownValue);

// =====================================================
// LOGIC 2: Lead No & Customer Name
// =====================================================
const leadNo = extractLeadNo(text);

if ((!customerName || customerName.trim() === "" || customerName === "-") && leadNo) {
    customerName = leadNo;
}

// รวม Profile Parts ทั้งหมด (ไม่รวม Lead No)
let finalProfile = "";

if (profileParts.length > 0) {
  finalProfile = profileParts.join(" ");
} else {
  finalProfile = "-";
}

// Clean up finalProfile (ลบ @tag + emoji)
finalProfile = clean(finalProfile);
finalProfile = finalProfile.replace(/(เพิ่มเติม|หมายเหตุ|ขายเพราะ)\s*[:：]*$/i, "").trim();
finalProfile = finalProfile.replace(/(ขายอย่างเดียว|ครับ|ค่ะ)/gi, "").trim();
finalProfile = finalProfile.replace(/@[^\s]+/g, "").trim();
finalProfile = finalProfile.replace(/[•★☆♡♥✨]/g, "").trim();
finalProfile = finalProfile.replace(/\s+/g, " ").trim();

if (!finalProfile || finalProfile === "") finalProfile = "-";
if (!customerName || customerName.trim() === "") customerName = "-";
if (!ads || ads.trim() === "") ads = "-";

// =====================================================
// Override Logic (OC/TC/SC) & Status
// =====================================================
const matchChannel = (text) => {
  const lower = (text || "").toLowerCase();

  if (lower.includes("facebook") || lower.includes("fb") || lower.includes("ส่วนตัว"))
    return "เพจบ้านเก่า";

  if (lower.includes("เพจบ้านเก่า") || lower.includes("บ้านเก่า"))
    return "เพจบ้านเก่า";

  if (lower.includes("เพจอ่อนนุช") || lower.includes("อ่อนนุช"))
    return "เพจอ่อนนุช";

  if (lower.includes("line@") || lower.includes("ไลน์"))
    return "Line@";

  if (lower.includes("หน้าร้านบ้านเก่า"))
    return "หน้าร้านบ้านเก่า";

  if (lower.includes("หน้าร้านอ่อนนุช"))
    return "หน้าร้านอ่อนนุช";

  if (lower.includes("เทิร์น") || lower.includes("เทริน"))
    return "เทิร์นรถ";

  return "";
};

let channelMapped = matchChannel(channelRaw) || matchChannel(channelFromCustomer) || matchChannel(text);
let sellType = "";
let onlineOffline = "";

if (code.startsWith("OC")) {
  onlineOffline = "Online";
  sellType = "ขายอย่างเดียว";
} else if (code.startsWith("SC")) {
  onlineOffline = "Offline";
  channelMapped = "หน้าร้านบ้านเก่า";
  sellType = "ขายอย่างเดียว";
} else if (code.startsWith("TC")) {
  onlineOffline = "Offline";
  sellType = "เทิร์น";
} else {
  if (text.toLowerCase().includes("online")) onlineOffline = "Online";
  else if (text.toLowerCase().includes("offline")) onlineOffline = "Offline";

  if (text.includes("เทิร์น") || text.includes("เทริน")) sellType = "เทิร์น";
  else if (text.includes("ขาย")) sellType = "ขายอย่างเดียว";
}

const matchBuyStatus = (text) => {
  const lower = (text || "").toLowerCase();
  if (lower.includes("รับซื้อ")) return "รับซื้อ";
  if (lower.includes("ไม่รับซื้อ")) return "ไม่รับซื้อ";
  if (lower.includes("เซลล์คุย") || lower.includes("คุยคันใหม่")) return "เซลล์คุยคันใหม่";
  if (lower.includes("นัดดูรถ")) return "นัดดูรถ";
  if (lower.includes("รอตัดสินใจ")) return "รอตัดสินใจ";
  return "";
};
const buyStatus = matchBuyStatus(text);

// =====================================================
// ★ v20 — Case Type Logic (ใช้ทะเบียนกลุ่มด้านบน)
// =====================================================
let caseType = "";

if (groupId === GROUP_VERY_HOT) {
  caseType = "VERY HOT";
} else if (GROUP_HOT[groupId]) {
  caseType = "HOT";                       // พี่หมี / พี่ต๊าด — กติกาเดียวกัน
} else {
  const lower = (text || "").toLowerCase();
  const codeUpper = (code || "").toUpperCase();

  if (codeUpper.includes("VH") || codeUpper.includes("VERYHOT")) caseType = "VERY HOT";
  else if (codeUpper.includes("HOT") || codeUpper.includes("H-")) caseType = "HOT";
  else if (codeUpper.includes("COOL") || codeUpper.includes("C-")) caseType = "COOL";
  else if (codeUpper.includes("REJ") || codeUpper.includes("REJECT")) caseType = "REJECT";

  else if (lower.includes("very hot") || lower.includes("veryhot")) caseType = "VERY HOT";
  else if (lower.includes("hot")) caseType = "HOT";
  else if (lower.includes("cool")) caseType = "COOL";
  else if (lower.includes("reject")) caseType = "REJECT";
}

// =====================================================
// ★ v20 — จัดซื้อ: ถ้าไม่มีใครถูก @tag ใช้เจ้าของกลุ่มแทน
//   (@tag ยังชนะเสมอ — ตัวนี้เป็นแค่ตัวสำรอง)
// =====================================================
const purchaserFinal = purchaserNickname || GROUP_HOT[groupId] || "";
if (!purchaserNickname && purchaserFinal) {
  console.log("  > จัดซื้อเติมจากกลุ่ม:", purchaserFinal);
}

const now = new Date();
const bangkokTime = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Bangkok" }));
const dateTH = bangkokTime.getDate() + "/" + (bangkokTime.getMonth() + 1) + "/" + String(bangkokTime.getFullYear()).slice(-2);

return [{
  json: {
    values: [
      dateTH,                         // A: วันที่
      "",                             // B: คันที่
      code,                           // C: Code
      carModel,                       // D: รุ่นรถ
      plate,                          // E: ป้ายทะเบียน
      phone,                          // F: เบอร์ติดต่อ
      customerName,                   // G: ชื่อผู้ขาย
      ads,                            // H: Ads
      channelMapped,                  // I: ช่องทาง
      sellType,                       // J: ขาย/เทริน
      buyStatus,                      // K: รับซื้อ/ไม่รับซื้อ
      onlineOffline,                  // L: ออนไลน์/ออฟไลน์
      purchaserFinal,                 // M: จัดซื้อ  ★ v20
      senderNickname,                 // N: ผู้ส่ง
      caseType,                       // O: เคส
      finalProfile,                   // P: โปรไฟล์ลูกค้า
      "",                             // Q: คอมเมนท์จัดซื้อ
      "",                             // R: เหตุผล
      "",                             // S: ประเภทรถ
      carDropdownValue                // T: รถตามสูตร
    ],
    _mode: "case_form",
    _code: code,
    _sender: senderNickname,
    _purchaser: purchaserFinal,
    _group: GROUP_HOT[groupId] || "",

    // ★ v20 — ชื่อฟิลด์สำหรับเขียนลง Postgres (ตาราง dash_purchase_case)
    //   โหนด "บันทึกเคสรับซื้อ (Postgres)" อ่านจากตรงนี้ · `values` ข้างบนเก็บไว้
    //   เผื่อยังต่อโหนดชีตคู่ขนานช่วงเปลี่ยนผ่าน — เลิกใช้ชีตแล้วลบ `values` ทิ้งได้
    code,
    date_th: dateTH,
    car_model: carModel,
    car_dropdown: carDropdownValue,
    plate,
    phone,
    seller_name: customerName,
    ads,
    channel: channelMapped,
    sell_type: sellType,
    decision: buyStatus,
    online_offline: onlineOffline,
    purchaser: purchaserFinal,
    sender: senderNickname,
    case_type: caseType,
    profile: finalProfile,
    group_id: groupId,
    group_name: GROUP_HOT[groupId] || "",
    message_id: item.messageId || item.message_id || "",
    raw_text: text
  }
}];
