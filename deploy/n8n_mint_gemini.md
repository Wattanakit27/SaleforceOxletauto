# เปลี่ยน workflow "มินท์ สรุปประชุม" (n8n) จาก Claude เป็น Gemini

**สรุป:** แก้ค่าในโหนดเดิม 7 จุด **ไม่ต้องลบโหนด ไม่ต้องลากสายใหม่** · prompt ของมินท์และคิวซีไม่เปลี่ยนสักตัวอักษร ·
ผลสรุปที่เคยเซฟไว้ใน Drive (สมัยใช้ Claude) ยังโหลดมาใช้ได้เหมือนเดิม

> **ทางลัด — วางทับทั้ง workflow:** ไฟล์ [n8n_mint_workflow_gemini.json](n8n_mint_workflow_gemini.json)
> คือ workflow ที่แก้ครบทั้ง 8 ขั้นด้านล่างแล้ว (รวมขั้นที่ 8 ใส่ credential Drive) — ดูวิธีวางที่หัวข้อ
> "วางทับทั้ง workflow" ท้ายไฟล์นี้ · ถ้าไม่อยากวางทับ ให้แก้ทีละโหนดตามขั้นด้านล่างแทน

**ทำไมแก้จุดเดียวไม่พอ:** Claude กับ Gemini รับคำขอคนละรูปแบบ **และ** ตอบกลับคนละรูปแบบ
จึงต้องแก้ 3 ขา ต่อ AI 1 ตัว: ขาประกอบคำขอ · ขายิง (HTTP) · ขาอ่านคำตอบ
และ workflow นี้ใช้ Claude อยู่ **2 ตัว** คือ มินท์ (ตัวสรุป) กับ คิวซี (ตัวตรวจ) — ถ้าเปลี่ยนแค่มินท์
คิวซียังเรียก Claude อยู่ พอเครดิตหมดก็ยังพังที่คิวซีเหมือนเดิม

| AI | เดิม | ใหม่ |
|---|---|---|
| มินท์ (สรุปประชุม) | `claude-sonnet-5` effort low | `gemini-2.5-flash` · คิดได้ไม่เกิน 4,096 token · บังคับตอบเป็น JSON |
| คิวซี (ตรวจ 7 ข้อ) | `claude-haiku-4-5` | `gemini-2.5-flash` · ไม่คิด · บังคับตอบเป็น JSON |

> ถ้าสรุปออกมาคุณภาพไม่พอ เปลี่ยนมินท์เป็น `gemini-2.5-pro` ได้ (แก้ URL ในขั้นที่ 2 คำเดียว)
> แต่ `thinkingBudget` ของรุ่น pro ห้ามเป็น 0 (ต่ำสุด 128) · ถ้าใช้รุ่น `gemini-3.x` ให้เปลี่ยน
> `thinkingConfig: { thinkingBudget: 4096 }` เป็น `thinkingConfig: { thinkingLevel: 'low' }`
> (ทั้ง 3 รุ่นนี้ key ของบริษัทใช้อยู่แล้วในระบบ SaleForce)

---

## ก่อนเริ่ม — เตรียม 5 อย่าง

1. **เก็บสำรองของเดิม** — เปิด workflow → `⋯` มุมขวาบน → **Download** เก็บไฟล์ JSON ไว้
   (ตั้งชื่อเช่น `มินท์-claude-ก่อนเปลี่ยน.json`) ไฟล์นี้มีค่าเดิมของทุกโหนด ใช้ย้อนกลับได้
   · **อย่าลบ credential `Anthropic account`** จนกว่าจะใช้ Gemini ราบรื่นสัก 2 สัปดาห์
2. **ใช้ key จากโปรเจกต์ที่เปิด billing แล้ว (paid tier) เท่านั้น** — transcript ประชุมมีชื่อพนักงาน
   ตัวเลขยอดขาย และเรื่องลูกค้า · ตามเงื่อนไขของ Google ถ้าใช้แบบฟรี Google เอา prompt กับคำตอบ
   ไปพัฒนาผลิตภัณฑ์ได้ และมีคนตรวจอ่านได้ · เปิด billing แล้วจะไม่ถูกเอาไปใช้แบบนั้น
   (แต่ Google ยังเก็บ log 55 วันไว้ตรวจการใช้ผิดกติกา) · **อย่าเปิด "แชร์ข้อมูลให้ Google" (dataset sharing)**
   ในโปรเจกต์นั้น
3. **ทำ key แยกสำหรับ workflow นี้** — ไม่ใช้ key เดียวกับระบบ SaleForce (`GEMINI_API_KEY` บนเซิร์ฟเวอร์)
   จะได้ดูยอดใช้แยกกัน และถ้า key หลุดก็ยกเลิกได้โดยไม่กระทบระบบขาย
4. **ตั้งเตือนงบ** — Google Cloud Console → **Billing → Budgets & alerts** → ตั้งงบรายเดือน (เช่น $10)
   ให้ส่งอีเมลที่ 50% / 90% / 100% · ⚠️ ตัวนี้ **แค่เตือน ไม่ได้หยุด** การใช้ —
   ตัวกันจ่ายซ้ำจริงๆ คือเพดาน 6 รอบใน workflow + ขั้นที่ 8 ในคู่มือนี้
5. **เช็คว่า workflow อื่นยังใช้ Claude อยู่ไหม** — ถ้ามีตัวอื่นใช้ credential `Anthropic account` ด้วย
   (เช่นตัวลงทะเบียนประชุม WF0) เครดิต Claude ก็ยังหมดอยู่ดี · ใช้
   [claude_chrome_find_mint_workflows.md](claude_chrome_find_mint_workflows.md) แล้วดูคำว่า
   `cred-anthropic` / `anthropic-api` ในผล

## ค่าใช้จ่ายที่คาด

ราคาจากหน้า pricing ของ Google (ดูเมื่อ 9 ต.ค.69 · ราคาเปลี่ยนได้ เช็คอีกทีก่อนตั้งงบ) ต่อ 1 ล้านโทเคน:

| รุ่น | ขาเข้า | ขาออก (รวมส่วนที่คิด) |
|---|---|---|
| `gemini-2.5-flash` — มินท์ + คิวซี ตามคู่มือนี้ | $0.30 | $2.50 |
| `gemini-2.5-flash-lite` — ทางเลือกที่ถูกกว่าสำหรับคิวซี | $0.10 | $0.40 |
| `claude-sonnet-5` — มินท์ของเดิม | $2.00 | $10.00 |

**สูตรต่อประชุม:** `(input × 0.30 + (output + thinking) × 2.50) ÷ 1,000,000` ดอลลาร์
— เลข token ดูได้จากช่อง `usage` ในโหนด `เตรียมเซฟผลมินท์` หลังรันประชุมจริงประชุมแรก

**ตัวอย่างสมมติ** ประชุมที่ใช้ input 40,000 + output 8,000 โทเคน:
Gemini ≈ $0.03 · Sonnet 5 เดิม ≈ $0.16 → **ถูกลงราว 5 เท่า**
แต่ถ้าประชุมล้มแล้วถูกทำซ้ำ 6 รอบ ก็ต้องคูณ 6 — **ขั้นที่ 8 จึงสำคัญกว่าการเปลี่ยนรุ่น**

---

## ขั้นที่ 0 — สร้าง credential ของ Gemini (ทำครั้งเดียว)

1. เอา API key จาก https://aistudio.google.com/apikey
2. n8n → **Credentials** → **Add credential** → เลือก **Header Auth**
3. ตั้งค่า:
   - **Name** = `x-goog-api-key`
   - **Value** = API key ที่ได้มา
4. ตั้งชื่อ credential ว่า `Gemini (เลขาประชุม)` แล้ว Save

> ใส่ key ใน credential เท่านั้น **ห้ามพิมพ์ key ลงในโค้ดหรือ URL** — workflow ที่ export ออกมาจะติด key ไปด้วย

---

## มินท์ (4 จุด)

### ขั้นที่ 1 — โหนด `ประกอบ Prompt มินท์` (แทนบรรทัดสุดท้ายบรรทัดเดียว)

ลบบรรทัดสุดท้ายนี้:

```js
return [{ json: { ...c, anthropicBody: body } }];
```

แล้ววางอันนี้แทน (ส่วน prompt ข้างบนไม่ต้องแตะ — `body` ที่มี `claude-sonnet-5` อยู่ กลายเป็นแค่ต้นแบบที่ถูกแปลงต่อ):

```js
// ---- 9 ต.ค.69: เปลี่ยนเป็น Gemini — แปลง body เดิมเป็นรูปแบบของ Gemini (prompt เดิมทุกตัวอักษร) ----
const geminiBody = {
  systemInstruction: { parts: body.system.map(s => ({ text: s.text })) },
  contents: [{ role: 'user', parts: body.messages[0].content.map(x => ({ text: x.text })) }],
  generationConfig: {
    responseMimeType: 'application/json',      // บังคับตอบเป็น JSON ล้วน
    temperature: 0.2,
    maxOutputTokens: 32768,                    // เพดาน — ส่วนที่ไม่ได้ใช้ไม่เสียเงิน
    thinkingConfig: { thinkingBudget: 4096 }   // คุมค่าคิด (แทน effort: 'low' ของ Claude)
  }
};
return [{ json: { ...c, geminiBody } }];
```

### ขั้นที่ 2 — โหนด HTTP `มินท์ สรุปประชุม`

| ช่อง | ค่าใหม่ |
|---|---|
| **URL** | `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent` |
| **Authentication** | `Generic Credential Type` → **Generic Auth Type** = `Header Auth` → เลือก `Gemini (เลขาประชุม)` |
| **Send Headers** | ลบแถว `anthropic-version` ทิ้ง (เหลือ `content-type` ไว้ได้) |
| **Body (JSON)** | `={{ JSON.stringify($('ประกอบ Prompt มินท์').item.json.geminiBody) }}` |
| **Options → Timeout** | `600000` (10 นาที — เดิม 3 นาที ถ้าตัดสายกลางทางก็ยังเสียเงินแต่ไม่ได้ผล) |
| **Settings → Retry On Fail** | เปิด · Max Tries `3` · Wait Between Tries `10000` |

> เปิด Retry ได้เพราะ Gemini ตอบ 503 (คนใช้เยอะ) / 429 อยู่บ้าง และคำขอที่ล้มแบบนั้นไม่คิดเงิน

### ขั้นที่ 3 — โหนด `เตรียมเซฟผลมินท์` (แทนโค้ดทั้งหมด)

```js
// 9 ต.ค.69: เปลี่ยนเป็น Gemini
// แปลงคำตอบ Gemini ให้หน้าตาเหมือนคำตอบ Claude เดิม ({content:[{type:'text',text}], stop_reason, usage})
// → โหนดถัดไปทำงานเหมือนเดิม และไฟล์ mint-raw-v2.json ที่เซฟไว้รอบก่อนๆ ยังใช้ได้
const g = $input.first().json;
const cand = (g.candidates || [])[0] || {};
const fin = cand.finishReason || '';
const text = ((cand.content || {}).parts || []).filter(p => !p.thought).map(p => p.text || '').join('');
const u = g.usageMetadata || {};
const usage = {
  input_tokens: u.promptTokenCount || 0,
  output_tokens: (u.candidatesTokenCount || 0) + (u.thoughtsTokenCount || 0),
  thinking_tokens: u.thoughtsTokenCount || 0
};

// ห้ามเซฟคำตอบที่ไม่สมบูรณ์ ไม่งั้นรอบหน้าจะโหลดของเสียมาใช้วนไม่จบ
if (g.promptFeedback && g.promptFeedback.blockReason) {
  throw new Error('Gemini ไม่รับ prompt นี้: ' + g.promptFeedback.blockReason);
}
if (fin === 'MAX_TOKENS') {
  throw new Error('Gemini ตอบไม่จบ (ชน maxOutputTokens) · ใช้คิดไป ' + usage.thinking_tokens + ' token');
}
if (fin && fin !== 'STOP') {
  throw new Error('Gemini หยุดกลางทางเพราะ ' + fin + ' — ไม่เซฟผลนี้');
}
if (!text.trim()) {
  throw new Error('Gemini ตอบว่างเปล่า: ' + JSON.stringify(g).slice(0, 300));
}

const res = { content: [{ type: 'text', text }], stop_reason: 'end_turn', model: g.modelVersion || 'gemini', usage };
const bin = await this.helpers.prepareBinaryData(Buffer.from(JSON.stringify(res), 'utf8'), 'mint-raw-v2.json', 'application/json');
return [{ json: res, binary: { data: bin } }];
```

### ขั้นที่ 4 — โหนด `อ่านผลมินท์` (แก้ข้อความ 2 จุด ใช้ Ctrl+F หาแล้วแก้)

| หา | แก้เป็น |
|---|---|
| `$('มินท์ สรุปประชุม').first().json` | `$('เตรียมเซฟผลมินท์').first().json` |
| `anthropicBody: undefined,` | `anthropicBody: undefined, geminiBody: undefined,` |

จุดแรกสำคัญ — โหนด `มินท์ สรุปประชุม` ตอนนี้คืนคำตอบดิบของ Gemini ส่วนตัวที่แปลงแล้วอยู่ที่ `เตรียมเซฟผลมินท์`
จุดที่สองแค่ทิ้งก้อนคำขอ (ซึ่งมี transcript ทั้งก้อน) ไม่ให้ลากต่อไปทุกโหนด

---

## คิวซี (3 จุด)

### ขั้นที่ 5 — โหนด `ประกอบ Prompt คิวซี` (แทนบรรทัดสุดท้ายบรรทัดเดียว)

ลบบรรทัดสุดท้ายนี้:

```js
return [{ json: { ...c, qcBody: body } }];
```

แล้ววางอันนี้แทน:

```js
// ---- 9 ต.ค.69: เปลี่ยนเป็น Gemini (prompt เดิม) · ใช้ชื่อ qcBody เดิม โหนด HTTP จึงไม่ต้องแก้ช่อง Body ----
const qcGemini = {
  systemInstruction: { parts: body.system.map(s => ({ text: s.text })) },
  contents: [{ role: 'user', parts: [{ text: body.messages[0].content }] }],
  generationConfig: {
    responseMimeType: 'application/json',
    temperature: 0,
    maxOutputTokens: 4096,
    thinkingConfig: { thinkingBudget: 0 }   // งานตรวจตามรายการ ไม่ต้องคิด
  }
};
return [{ json: { ...c, qcBody: qcGemini } }];
```

### ขั้นที่ 6 — โหนด HTTP `คิวซี ตรวจ 7 ข้อ`

| ช่อง | ค่าใหม่ |
|---|---|
| **URL** | `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent` |
| **Authentication** | `Generic Credential Type` → `Header Auth` → `Gemini (เลขาประชุม)` |
| **Send Headers** | ลบแถว `anthropic-version` ทิ้ง |
| **Body (JSON)** | **ไม่ต้องแก้** (ยังเป็น `$json.qcBody`) |
| **Settings → Retry On Fail** | เปิด · Max Tries `3` · Wait Between Tries `10000` |

### ขั้นที่ 7 — โหนด `อ่านผลคิวซี` (แทนโค้ดทั้งหมด)

````js
const c = $('ประกอบ Prompt คิวซี').first().json;
const res = $input.first().json;
// 9 ต.ค.69: คำตอบมาจาก Gemini (candidates[0].content.parts)
const cand = (res.candidates || [])[0] || {};
let text = ((cand.content || {}).parts || []).filter(p => !p.thought).map(p => p.text || '').join('');
text = text.trim().replace(/^```(?:json)?/, '').replace(/```$/, '').trim();

let qc = null;
try { qc = JSON.parse(text); } catch (e) { qc = null; }

// คิวซีตอบพัง ≠ มินท์ทำผิด → ห้ามส่งกลับให้มินท์แก้
// (เดิมส่งกลับ = จ่ายค่ามินท์ซ้ำอีกรอบ ทั้งที่มินท์แก้อะไรไม่ได้) · ติดธงให้คนตรวจเองแทน
const อ่านได้ = !!qc && typeof qc.pass === 'boolean';
if (!อ่านได้) {
  qc = { pass: false, failed: [{ ข้อ: 0, เหตุผล: 'คิวซีตอบผิดรูปแบบ (' + (cand.finishReason || 'ไม่มีคำตอบ') + ') — ยังไม่ได้ตรวจ โปรดตรวจเอง' }] };
}
const feedback = (qc.failed || []).map(f => `ข้อ ${f.ข้อ}: ${f.เหตุผล}`).join('\n');
return [{ json: { ...c, qcBody: undefined, qc, qc_feedback: feedback,
  needRetry: อ่านได้ && !qc.pass && c.qc_attempt < 1 } }];
````

---

## ขั้นที่ 8 — แนะนำมาก: ซ่อมระบบ "เคยสรุปไว้แล้ว โหลดมาใช้ฟรี"

โหนด **`หาผลมินท์ที่เซฟไว้`** และ **`โหลดผลมินท์ที่เซฟไว้ (ฟรี)`** ยังไม่มี credential Google Drive
→ โหนดแรกล้มแบบเงียบ (ตั้ง Continue on error ไว้) → workflow คิดว่า "ยังไม่เคยสรุป" ทุกครั้ง
→ **ประชุมที่ทำไม่จบรอบแรก จะถูกส่งให้ AI สรุปใหม่ทั้ง transcript ทุกรอบที่ลองใหม่ (สูงสุด 6 รอบ)**
ซึ่งน่าจะเป็นสาเหตุหลักข้อหนึ่งที่เครดิต Claude หมดไว — เปลี่ยนเป็น Gemini แล้วไม่แก้ข้อนี้ ก็จะจ่ายซ้ำแบบเดิม (แค่ถูกกว่า)

แก้: เปิดทั้ง 2 โหนด → **Authentication** = `Predefined Credential Type` → `Google Drive OAuth2 API`
→ เลือก `Google Drive account` (ตัวเดียวกับโหนด `หาไฟล์ transcript.md`)

---

## หลังเปลี่ยนแล้ว

### วันแรก — ลอง 1 ประชุมก่อนปล่อยใช้จริง

- ข้อความสรุปไปที่ **ห้องตรวจ** (James + ฮอน/เนย์) อยู่แล้ว → รันจริงได้เลย
- ถ้าไม่อยากให้ลงห้องตรวจ/Notion/ชีตตอนลอง: คลิกขวา **Deactivate** 4 โหนดท้าย
  (`LINE ห้องตรวจ` · `สร้างหน้า Notion` · `ชีต: สรุปแล้ว=ใช่` · `บันทึก Action Items`) → กด Execute workflow
  → ดูผลที่โหนด `อ่านผลมินท์` และ `อ่านผลคิวซี` → เปิด 4 โหนดกลับ
  (ประชุมที่ลองจะค้างสถานะ `⏳ กำลังทำ` 30 นาที แล้วรอบตั้งเวลาถัดไปจะทำต่อเอง —
  ถ้าทำขั้นที่ 8 แล้ว รอบนั้นจะโหลดผลที่เซฟไว้มาใช้ ไม่เรียก AI ซ้ำ)
- ดูโหนด `เตรียมเซฟผลมินท์` → `usage` บอกจำนวน token ที่ใช้จริงของแต่ละประชุม

**เช็คลิสต์ 2–3 สรุปแรก** (ให้ห้องตรวจช่วยดู — ใช้ Gemini เป็นครั้งแรก ต้องเทียบกับมาตรฐานเดิม):

- [ ] มีหัว 📋 และ 4 หมวด ✅ ⚠️ ❓ 📌 ครบ เรียงถูก ยาวไม่เกินราว 30 บรรทัด
- [ ] ชื่อคนเป็นชื่อเล่นที่ทีมใช้ ไม่มีชื่อคนที่ไม่ได้อยู่ในประชุม
- [ ] กำหนดส่งเป็นวันที่ (YYYY-MM-DD) หรือเขียนว่า "ไม่มีวัน" — ไม่มีวันที่ที่ห้องไม่ได้พูด
- [ ] ตัวเลข/จำนวนเงินตรงกับที่พูดจริง ไม่มีตัวเลขงอกขึ้นมาเอง
- [ ] ไม่มีประโยคแนะนำ/ความเห็นของ AI เอง เช่น "ควร…" "แนะนำให้…"
- [ ] ภาษาไทยเป็นธรรมชาติ ลงท้าย "ค่ะ"
- [ ] หน้า Notion มีหัวข้อ ตารางตัวเลข และตารางงานครบ

ตกหลายข้อ → ลองปุ่มปรับ "คุณภาพไม่พอ" ด้านล่างก่อน ค่อยสรุปว่า Gemini ใช้ไม่ได้

### สัปดาห์แรก — เฝ้าดู 3 ที่ (วันละครั้งพอ)

| ดูที่ไหน | ปกติ | ถ้าผิดปกติ |
|---|---|---|
| ชีตทะเบียนประชุม คอลัมน์ "สรุปแล้ว" | `ใช่` | `⏳ กำลังทำ … #2` ขึ้นไป = ล้มแล้วถูกทำซ้ำ → เปิด Executions ดู error · `ใช่ (คิวซีไม่ผ่าน)` บ่อย → ปรับรุ่นหรือ prompt |
| n8n → **Executions** | เขียวเกือบทั้งหมด | แดงซ้ำที่โหนดเดิม → ดูตาราง "ถ้าเจอ error" ด้านล่าง |
| Google AI Studio → **Usage / Billing** | ยอดต่อวันพอๆ กับจำนวนประชุม | วันไหนกระโดดสูง = มีประชุมถูกทำซ้ำ → ดูชีตทะเบียนของวันนั้น |

### ปุ่มปรับ

| อาการ | ปรับตรงไหน |
|---|---|
| คุณภาพสรุปไม่พอ | ขั้นที่ 2 เปลี่ยน URL เป็น `gemini-2.5-pro` (แพงกว่า flash · `thinkingBudget` ห้ามเป็น 0) หรือเพิ่ม `thinkingBudget` ของ flash |
| ค่าคิดสูง (`thinking_tokens` ใน usage ชนเกือบ 4,096 ทุกครั้ง) | ขั้นที่ 1 ลด `thinkingBudget` เหลือ 2048 หรือ 1024 แล้วดูว่าคุณภาพยังได้ไหม |
| อยากถูกลงอีก | ขั้นที่ 6 คิวซีใช้ `gemini-2.5-flash-lite` · หรือตัดคิวซีทิ้งเปลี่ยนเป็นโค้ดตรวจ (ไม่ใช้ AI) |
| `Gemini ตอบไม่จบ` บ่อย | ขั้นที่ 1 เพิ่ม `maxOutputTokens` |
| `429` บ่อย | เกินโควต้าของ tier โปรเจกต์ — ดู rate limit ใน AI Studio |

### ถ้าต้องย้อนกลับไปใช้ Claude

ใช้ไฟล์ JSON ที่ Download ไว้ตอน "ก่อนเริ่ม" ข้อ 1 — ค่าเดิมของทั้ง 7 จุดอยู่ในนั้น
(คัดลอกโค้ด/ค่าของโหนดที่แก้กลับไป หรือส่งไฟล์มาให้ช่วยทำคืน)
ไฟล์ `mint-raw-v2.json` ที่เซฟไว้ระหว่างใช้ Gemini เป็นรูปแบบเดียวกับของ Claude → ย้อนกลับแล้วยังโหลดใช้ได้

### งานที่ยังค้าง (เจอตอนรีวิว · ยังไม่ได้แก้ในคู่มือนี้)

- [ ] ID งานของไฟล์อัปโหลด/สายโทรศัพท์ซ้ำกันได้ (`วันที่-x-01`) — ควรใช้ `fireflies_id` แทนรหัสห้อง
- [ ] ประชุมที่ล้มครบ 6 รอบไม่มีใครรู้ — ควรส่งแจ้งเตือนเข้าห้องตรวจ
- [ ] งานค้างเดิมส่งเข้า prompt ทุกงานจากทุกประชุม — prompt ยาวขึ้นเรื่อยๆ ควรจำกัดช่วงเวลา
- [ ] ข้อความ LINE ที่ใส่ในหน้า Notion ถูกตัดที่ 1,900 ตัวอักษรโดยไม่บอก
- [ ] เปลี่ยนคิวซีเป็นโค้ดตรวจ (ตัด AI ตัวที่ 2 ออก)

## ถ้าเจอ error

| ข้อความ | สาเหตุ / ทางแก้ |
|---|---|
| `400` ... `API key not valid` | key ผิด/ก๊อปไม่ครบ — แก้ใน credential |
| `403` ... `PERMISSION_DENIED` | key ถูกจำกัดสิทธิ์/ยังไม่เปิด Generative Language API ในโปรเจกต์ |
| `400` ... `thinking` | รุ่นที่เลือกไม่รับค่า `thinkingBudget` นั้น (ดูหมายเหตุเรื่องรุ่นด้านบน) |
| `429` | เกินโควต้า — ดูหน้า billing/quota ของ Google AI Studio |
| `Gemini ตอบไม่จบ (ชน maxOutputTokens)` | เพิ่ม `maxOutputTokens` ในขั้นที่ 1 หรือลด `thinkingBudget` |
| `Gemini หยุดกลางทางเพราะ SAFETY` | ตัวกรองของ Google ตีเนื้อหาประชุม — ส่ง transcript ช่วงนั้นมาให้ดู |

## วางทับทั้ง workflow (ใช้ไฟล์ n8n_mint_workflow_gemini.json)

1. ทำ "ก่อนเริ่ม" ข้อ 1 (Download สำรองของเดิม) และขั้นที่ 0 (สร้าง credential ชื่อ **`Gemini (เลขาประชุม)`** ให้ตรงตัว)
2. เปิดไฟล์ JSON → Ctrl+A → Ctrl+C
3. เปิด workflow เดิมใน n8n → คลิกพื้นที่ว่างบนผืนผ้าใบ → **Ctrl+A → Delete** (ลบโหนดเดิมทั้งหมด)
4. คลิกพื้นที่ว่าง → **Ctrl+V**
5. เปิดโหนด `มินท์ สรุปประชุม` และ `คิวซี ตรวจ 7 ข้อ` → ช่อง credential เลือก `Gemini (เลขาประชุม)` (ถ้ายังไม่ได้เลือกให้)
6. **เช็คเส้นเชื่อม 3 จุดที่ต่อจากการเดา** (ข้อความที่วางมาให้ผมถูกตัดตรงส่วนเส้นเชื่อม — ผมต่อตามที่โค้ดในแต่ละโหนดบอก):
   - `รับต่อจาก WF0 (ทันทีที่ลงทะเบียน)` → `อ่านทะเบียนประชุม`
   - `เตรียมรอบแก้ (ครั้งเดียว)` → `ประกอบ Prompt มินท์`
   - `ประกอบข้อความ` → แยก 2 ทาง: `LINE ห้องตรวจ` → `สร้างหน้า Notion` → `ชีต: สรุปแล้ว=ใช่` และ `กระจาย Action เป็นแถว` → `บันทึก Action Items`

   ถ้าของเดิมต่อไม่เหมือนนี้ ลากเส้นใหม่ให้ตรงของเดิม (ดูจากไฟล์สำรองข้อ 1)
7. **Save** → ทดสอบตามหัวข้อ "หลังเปลี่ยนแล้ว"

> วางทับใน workflow ตัวเดิม (ไม่สร้าง workflow ใหม่) เพราะ WF0 เรียก workflow นี้ด้วย id —
> ถ้าสร้างใหม่ WF0 จะยังเรียกตัวเก่าอยู่

## ที่มา (เช็คก่อนตั้งงบ / ก่อนอ้างเรื่องข้อมูล — หน้าเหล่านี้เปลี่ยนได้)

- ราคา: [Gemini Developer API pricing](https://ai.google.dev/gemini-api/docs/pricing)
- การใช้ข้อมูลแบบฟรี vs จ่ายเงิน: [Gemini API Additional Terms of Service](https://ai.google.dev/gemini-api/terms)
- การเก็บ log 55 วัน: [Abuse monitoring](https://ai.google.dev/gemini-api/docs/usage-policies)
- การแชร์ข้อมูลให้ Google: [Data logging and sharing](https://ai.google.dev/gemini-api/docs/logs-policy)
