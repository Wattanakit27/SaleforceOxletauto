// เทสต์โค้ด n8n workflow ซื้อขายเทิร์นรถ (ไม่ใช้ข้อมูลจริง · ปลอมเวลา/โหนดอื่น)
//   node scripts/test_n8n_tradein.js
// 1) Build Sheet Row v22 — ชื่อแท็บตามเดือน/ข้ามปี + แถว A–S
// 2) รวมคอมเมนท์ (หาเคสข้ามเดือน)
const path = require("path");
const ROOT = path.join(__dirname, "..");
let FAILS = 0;
process.on("exit", () => console.log(FAILS ? FAILS + " FAIL" : "ALL PASS"));
{
const fs = require("fs");
const src = fs.readFileSync(path.join(ROOT, "deploy/n8n_tradein_build_row.js"), "utf8");
const fails = [];
const ok = (n, c, x) => { console.log((c ? "PASS " : "FAIL ") + n + (c ? "" : " — " + JSON.stringify(x))); if (!c) { fails.push(n); FAILS++; } };
function run(item, iso) {
  const Real = Date;
  if (iso) global.Date = class extends Real { constructor(...a) { if (a.length === 0) super(iso); else super(...a); } static now() { return new Real(iso).getTime(); } };
  try { return new Function("$input", "console", src)({ all: () => [{ json: item }] }, { log() {} }); }
  finally { global.Date = Real; }
}
const HOT = "C0ad44e22acf81cd6af619da15ffb363d";
const slip = "โค้ด : OC-7999\nADS : รับซื้อ CIVIC\nรุ่น : Mazda3 ปี18 แดง\nเลขไมล์ : 80,000\nทะเบียน : 1กก1234\nเบอร์ติดต่อ : 081-234-5678\nชื่อลูกค้า : -ทดสอบ / Line@\nเพิ่มเติม : -\nขายเพราะ : จะซื้อคันใหม่\nราคากลางรับซื้อจากตาราง :\n@หมีน้อย";
const base = { _mode: "case_form", code: "OC-7999", text: slip, senderNickname: "ฟิล์ม", purchaserNickname: "พี่หมี", groupId: HOT };

let o = run(base, "2026-10-08T03:00:00Z")[0].json;
ok("ต.ค.: _tab", o._tab === "ขายรถจบออนไลน์ ตุลาคม69", o._tab);
ok("rowAS 19 ช่อง (A–S)", Array.isArray(o.rowAS) && o.rowAS.length === 19, o.rowAS && o.rowAS.length);
ok("A วันที่ ปี 4 หลัก", o.rowAS[0] === "8/10/2026", o.rowAS[0]);
ok("C Code", o.rowAS[2] === "OC-7999");
ok("F เบอร์มี ' นำหน้า", o.rowAS[5] === "'0812345678", o.rowAS[5]);
ok("G ชื่อขึ้นต้น - ได้ ' นำหน้า", o.rowAS[6] === "'-ทดสอบ", o.rowAS[6]);
ok("K ว่าง", o.rowAS[10] === "");
ok("O เคส = HOT", o.rowAS[14] === "HOT");
ok("P โปรไฟล์ไม่มีราคากลาง", !/ราคา/.test(o.rowAS[15]), o.rowAS[15]);
ok("S car = Mazda3", o.rowAS[18] === "Mazda3", o.rowAS[18]);
ok("values เดิมยังอยู่ 20 ช่อง", o.values && o.values.length === 20);

o = run(base, "2027-01-05T03:00:00Z")[0].json;
ok("ม.ค.70: _tab", o._tab === "ขายรถจบออนไลน์ มกราคม70", o._tab);
const c = run({ ...base, _mode: "purchase_comment", text: "OC-7999 คาดหวัง 400,000 @หมีน้อย", code: "OC-7999" }, "2027-01-05T03:00:00Z")[0].json;
ok("ม.ค.70 คอมเมนท์: _tabPrev = ธันวาคม69", c._tabPrev === "ขายรถจบออนไลน์ ธันวาคม69", c._tabPrev);
o = run(base, "2026-10-31T17:30:00Z")[0].json;   // 00:30 น. 1 พ.ย. เวลาไทย
ok("เที่ยงคืนครึ่ง 1 พ.ย. (ไทย) → แท็บ พ.ย.", o._tab === "ขายรถจบออนไลน์ พฤศจิกายน69", o._tab);
}
{
const d = require(path.join(ROOT, "deploy/n8n_tradein_sheet_section.json"));
const src = d.nodes.find(n => n.type.endsWith(".code")).parameters.jsCode;
const fails = [];
const ok = (n, c, x) => { console.log((c ? "PASS " : "FAIL ") + n + (c ? "" : " — " + JSON.stringify(x))); if (!c) { fails.push(n); FAILS++; } };
const b = { _mode: "purchase_comment", code: "OC-7999", comment: "คาดหวัง 400,000", _tab: "ขายรถจบออนไลน์ ตุลาคม69", _tabPrev: "ขายรถจบออนไลน์ กันยายน69" };
const row = (code, q) => { const r = [code]; for (let i = 1; i < 15; i++) r.push(""); r[14] = q || ""; return r; };
function run(build, ranges, names = ["Build Sheet Row (Trade-in)"]) {
  const $ = (n) => { if (!names.includes(n)) throw new Error("no node " + n); return { first: () => ({ json: build }) }; };
  try { return new Function("$", "$input", "console", src)($, { first: () => ({ json: { valueRanges: ranges } }) }, { log() {} }); }
  catch (e) { return { error: e.message }; }
}
let o = run(b, [{ values: [row("OC-1"), [], row("OC-7999", "")] }, { values: [] }]);
ok("เจอในเดือนนี้ แถว 5 (มีแถวว่างคั่น)", o[0] && o[0].json.tab === b._tab && o[0].json.row === 5 && o[0].json.comment === b.comment, o);
o = run(b, [{ values: [row("OC-1")] }, { values: [row("OC-2"), row("OC-7999", "โทรแล้ว")] }]);
ok("ไม่เจอเดือนนี้ → เดือนก่อน แถว 4 + ต่อคอมเมนท์", o[0] && o[0].json.tab === b._tabPrev && o[0].json.row === 4 && o[0].json.comment === "โทรแล้ว / คาดหวัง 400,000", o);
o = run(b, [{ values: [row("OC-7999", "x")] }, { values: [row("OC-7999", "y")] }]);
ok("เจอทั้ง 2 เดือน → เดือนนี้ชนะ", o[0] && o[0].json.tab === b._tab, o);
o = run(b, [{ values: [row("OC-7999"), row("oc- 7999")] }, { values: [] }]);
ok("รหัสซ้ำ → แถวล่างสุด · ไม่สนช่องว่าง/ตัวพิมพ์", o[0] && o[0].json.row === 4, o);
o = run(b, [{ values: [row("OC-7999", "a / คาดหวัง 400,000")] }, { values: [] }]);
ok("คอมเมนท์ซ้ำ → ไม่เขียน", Array.isArray(o) && o.length === 0, o);
o = run(b, [{ values: [row("OC-1")] }, { values: [] }]);
ok("ไม่เจอเคส → ข้าม", Array.isArray(o) && o.length === 0, o);
o = run(b, [{ values: [row("OC-7999")] }], ["Build Sheet Row v22"]);
ok("ชื่อโหนด v22 ก็หาเจอ", o[0] && o[0].json.row === 3, o);
o = run({ ...b, _mode: "case_form" }, [{ values: [] }]);
ok("ต่อสายผิด → error ชัด", o.error && o.error.includes("ต่อสายผิด"), o);
o = run({ ...b, _tab: undefined }, [{ values: [] }]);
ok("Build Sheet Row รุ่นเก่า → error ชัด", o.error && o.error.includes("รุ่นเก่า"), o);
}
{
// 3) ผู้ส่ง (N) — "ดีเซล" ต้องไม่ถูกจับเป็นคำว่า "เซล" · "เทิร์นเซลล์X" ยังจับได้
const fs = require("fs");
const src = fs.readFileSync(path.join(ROOT, "deploy/n8n_tradein_build_row.js"), "utf8");
const run = (text, code) => new Function("$input", "console", src)({ all: () => [{ json: {
  _mode: "case_form", code, text, senderNickname: "โดนัท", purchaserNickname: "", groupId: "C0ad44e22acf81cd6af619da15ffb363d" } }] }, { log() {} })[0].json;
const ok = (n, c, x) => { console.log((c ? "PASS " : "FAIL ") + n + (c ? "" : " — " + JSON.stringify(x))); if (!c) FAILS++; };
let o = run("โค้ด : OC-7625\nรุ่น : Isuzu MU-X ปี23\nเครื่องยนต์: ดีเซล 1,898 ซีซี\nเบอร์ติดต่อ : 0812345678", "OC-7625");
ok("ดีเซล 1,898 ไม่ใช่ชื่อผู้ส่ง (บั๊กจริง 8 ต.ค.69)", o.rowAS[13] === "โดนัท", o.rowAS[13]);
o = run("โค้ด : SC-1299 เทิร์นเซลล์เก้า\nรุ่น : Benz GLE350d ปี17\nเบอร์ติดต่อ : 0812345678", "SC-1299");
ok("เทิร์นเซลล์เก้า → ผู้ส่ง = เก้า", o.rowAS[13] === "เก้า", o.rowAS[13]);
}
