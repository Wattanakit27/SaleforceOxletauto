# งานสำหรับ Claude in Chrome: หา workflow ใน n8n ที่เกี่ยวกับระบบ "มินท์" (เลขาสรุปประชุม)

## เป้าหมาย

ผู้ใช้ (คนที่สั่งงานคุณ) กำลังแก้ workflow **"มินท์ สรุปประชุม"** ใน n8n และต้องการรู้ว่า
**มี workflow ตัวอื่นที่ทำงานร่วมกับมันบ้าง** เช่น ตัวที่รับประชุมจาก Fireflies แล้วลงทะเบียน (WF0) ·
ตัวที่ส่งสรุปเข้ากลุ่มทีมหลังตรวจแล้ว · ตัวรับ error · ตัวที่เรียกต่อกันเป็นทอดๆ

วิธีทำ: **export workflow ทั้งหมดเป็นไฟล์ชั่วคราวในเซิร์ฟเวอร์ → ใช้สคริปต์ค้นคำที่เป็นเอกลักษณ์ของระบบนี้
→ รายงานผู้ใช้ → ดาวน์โหลด JSON ของตัวที่เกี่ยวข้อง → ลบไฟล์ชั่วคราวทิ้ง**

งานนี้ **อ่านอย่างเดียว** ไม่แก้ ไม่เปิด/ปิด ไม่สั่งรัน workflow ใดๆ ทั้งสิ้น

## ข้อมูลเซิร์ฟเวอร์

| | |
|---|---|
| เว็บควบคุม | https://hpanel.hostinger.com (ผู้ใช้ login ไว้แล้ว) |
| VPS ที่รัน n8n | ชื่อขึ้นต้น **`srv1102218`** |
| หน้าเว็บ n8n | https://n8n.srv1102218.hstgr.cloud (ถ้าเปิดไม่ได้ ดูลิงก์ในหน้าภาพรวม VPS ของ hPanel หรือถามผู้ใช้) |
| ⚠️ เครื่องที่ **ห้ามแตะ** | `srv1793506` = เว็บบริษัท ไม่เกี่ยวกับงานนี้ |

## กติกา (สำคัญ อ่านก่อนเริ่ม)

1. **รันเฉพาะคำสั่งที่เขียนไว้ในไฟล์นี้ ทีละขั้น ตามลำดับ** ห้ามคิดคำสั่งใหม่เอง ห้ามแก้ไฟล์ด้วย nano/vim
2. **ห้ามทำอะไรที่ทำให้ workflow ทำงานหรือเปลี่ยน**
   - ในหน้าเว็บ n8n: **ห้ามกด Execute / Test / Activate / Save / ลากโหนด**
     (กด Execute ครั้งเดียว = เรียก AI เสียเงินจริง + ส่งข้อความเข้ากลุ่ม LINE จริง)
   - ใน terminal: ห้าม `n8n execute` · `n8n import:*` · `n8n update:*` ·
     ห้าม `docker restart/stop/rm` · ห้าม `docker compose` ทุกคำสั่ง
3. **ห้ามดูความลับ** — ห้าม `n8n export:credentials` · `docker inspect` · `env` · `printenv` ·
   ห้าม `cat` ไฟล์ `.env` และ **ห้าม `cat` ไฟล์ JSON ที่ export ออกมา** (บาง workflow อาจมี token ฝังอยู่ในโหนด)
   ให้ใช้สคริปต์ในขั้นที่ 3 อ่านแทน ซึ่งพิมพ์แค่ ชื่อ · id · ตัวเริ่มทำงาน · ใครเรียกใคร
4. **ผลไม่ตรงกับ "ผลที่ถูก" หรือมี error → หยุด** ก๊อปข้อความในหน้าจอส่งผู้ใช้ แล้วรอคำสั่ง ห้ามลองแก้เอง
   (ยกเว้นทางสำรองที่เขียนไว้ในขั้นนั้นๆ)
5. ถ้ามีหน้าต่างถามรหัสผ่าน หรือถามยืนยันอะไรที่ไม่ได้เขียนไว้ในไฟล์นี้ → หยุดแล้วถามผู้ใช้
6. **ขั้นที่ 6 (ลบไฟล์ชั่วคราว) ต้องทำเสมอ** แม้ขั้นกลางจะล้ม

## ขั้นตอน

### ขั้นที่ 0 — เปิด terminal ของเครื่อง n8n

1. ไปที่ https://hpanel.hostinger.com
2. เมนู **VPS** → เลือกเครื่องที่ชื่อขึ้นต้น **`srv1102218`** (ถ้าไม่เจอ หรือเห็นแค่ `srv1793506` → หยุดถามผู้ใช้)
3. กดปุ่ม **Browser terminal** (หรือ **Terminal**) ที่หน้าภาพรวมของ VPS
4. รอจนเห็นบรรทัดพร้อมพิมพ์ลักษณะ `root@srv1102218:~#`
   ถ้าไม่ใช่ `root` ให้ใส่ `sudo` หน้าคำสั่ง `docker` ทุกคำสั่ง · ถ้าระบบถามรหัสผ่าน → หยุดถามผู้ใช้

> คลิกในกรอบ terminal ก่อนพิมพ์ทุกครั้ง · กด Enter หลังพิมพ์แต่ละคำสั่ง ·
> **คำสั่งทุกบรรทัดในไฟล์นี้เป็นอักษรอังกฤษล้วน** พิมพ์ตามตัวอักษรได้เลย ·
> **ห้ามใช้ปุ่ม Tab** (ย่อหน้าในสคริปต์เป็นช่องว่างเท่านั้น)

### ขั้นที่ 1 — หา container ของ n8n

```bash
docker ps --format '{{.Names}}  |  {{.Image}}  |  {{.Status}}'
```

**ผลที่ถูก:** มีอย่างน้อย 1 บรรทัดที่ช่องกลาง (image) มีคำว่า `n8n` เช่น `n8nio/n8n` หรือ `docker.n8n.io/n8nio/n8n`

- `docker: command not found` หรือไม่มีบรรทัดไหนมีคำว่า `n8n` → หยุด รายงานผู้ใช้ว่า "n8n ไม่ได้รันใน docker"

แล้วเก็บชื่อ container ไว้ในตัวแปร `C`:

```bash
C=$(docker ps --format '{{.Names}} {{.Image}}' | awk '$2 ~ /n8n/ && $0 !~ /runner|worker/ {print $1; exit}'); echo "container = $C"
```

**ผลที่ถูก:** `container = <ชื่อ>` (ไม่ว่าง)

- ขึ้น `container = ` เฉยๆ → หยุด ก๊อปผลของคำสั่งก่อนหน้าส่งผู้ใช้
- ⚠️ ตัวแปร `C` **หายไปถ้า terminal หลุดหรือถูกรีเฟรช** → ถ้าเกิดขึ้น ให้รันบรรทัด `C=...` นี้ใหม่ก่อนทำขั้นต่อไป

### ขั้นที่ 2 — export workflow ทั้งหมดเป็นไฟล์ชั่วคราว

```bash
docker exec -u node "$C" sh -c 'rm -rf /tmp/wfx && mkdir -p /tmp/wfx && n8n export:workflow --all --separate --output=/tmp/wfx/' && rm -rf /tmp/wfx && docker cp "$C":/tmp/wfx /tmp/wfx && ls /tmp/wfx | wc -l
```

ใช้เวลาไม่กี่วินาที ถึงประมาณ 1 นาที

**ผลที่ถูก:** บรรทัดสุดท้ายเป็นตัวเลข = จำนวน workflow (มากกว่า 0)
ข้อความเตือนพวก `Permissions 0644 for n8n settings file` หรือ `deprecat...` ขึ้นได้ ไม่ต้องสนใจ

- ขึ้น `unable to find user node` → รันคำสั่งเดิมอีกครั้ง **โดยลบ `-u node ` ออก** (ทางสำรองข้อเดียวที่อนุญาต)
- ขึ้น `n8n: not found` / error อื่น / ตัวเลขเป็น `0` → หยุด รายงานผู้ใช้ แล้วไปขั้นที่ 6

### ขั้นที่ 3 — สร้างสคริปต์ค้นหา

เช็คก่อนว่ามี Python:

```bash
python3 --version
```

- ได้ `Python 3.x` → ทำขั้นนี้ต่อ
- ได้ `command not found` → **ข้ามไปขั้นที่ 3ข**

พิมพ์ **ทั้งก้อน** ตั้งแต่บรรทัด `cat` ไปจนถึงบรรทัด `PY` บรรทัดสุดท้าย
ระหว่างพิมพ์จะเห็น `>` นำหน้าทุกบรรทัด เป็นเรื่องปกติ

```bash
cat > /tmp/wfscan.py <<'PY'
import glob, json, os, sys
D = sys.argv[1] if len(sys.argv) > 1 else "/tmp/wfx"
STRONG = {
    "sheet-meeting": "1l8EqFMeuvqimmndrQ7jqGaKb6gyt0MIDOBh7HQgOKtA",
    "notion-db": "3d5eeea9-8d22-8102-84af-f920e6532520",
    "notion-db2": "3d5eeea98d22810284aff920e6532520",
    "line-review-room": "Cd05e936cea3e3e42e85ed9e80da85bf4",
    "cred-line-mint": "Qg0BsZe0MY3TbzZH",
    "fireflies": "fireflies",
    "transcript.md": "transcript.md",
    "mint-raw": "mint-raw",
    "th:mint": "\u0e21\u0e34\u0e19\u0e17\u0e4c",
    "th:meeting-register": "\u0e17\u0e30\u0e40\u0e1a\u0e35\u0e22\u0e19\u0e1b\u0e23\u0e30\u0e0a\u0e38\u0e21",
    "th:sent-to-team": "\u0e2a\u0e48\u0e07\u0e17\u0e35\u0e21\u0e41\u0e25\u0e49\u0e27",
    "th:meeting-secretary": "\u0e40\u0e25\u0e02\u0e32\u0e1b\u0e23\u0e30\u0e0a\u0e38\u0e21",
    "th:qc": "\u0e04\u0e34\u0e27\u0e0b\u0e35",
    "th:wait-confirm": "\u0e23\u0e2d\u0e22\u0e37\u0e19\u0e22\u0e31\u0e19",
    "th:meeting-summary": "\u0e2a\u0e23\u0e38\u0e1b\u0e1b\u0e23\u0e30\u0e0a\u0e38\u0e21",
}
WEAK = {
    "anthropic-api": "api.anthropic.com",
    "cred-anthropic": "xzQMuXfzuLZUkg5S",
    "cred-notion": "zF9TEhv2Z5tCSqvq",
    "action-items": "Action Items",
}
TRIG = ("Trigger", "formTrigger")

def rl(v):
    if isinstance(v, dict):
        v = v.get("value")
    return str(v or "")

wfs = {}
for f in sorted(glob.glob(os.path.join(D, "*.json"))):
    try:
        data = json.load(open(f, encoding="utf-8"))
    except Exception as e:
        print("READ-FAIL", os.path.basename(f), e)
        continue
    for w in (data if isinstance(data, list) else [data]):
        txt = json.dumps(w, ensure_ascii=False)
        low = txt.lower()
        strong = [k for k, v in STRONG.items() if v.lower() in low]
        weak = [k for k, v in WEAK.items() if v.lower() in low]
        trig, calls = [], []
        for n in w.get("nodes") or []:
            t = n.get("type", "")
            p = n.get("parameters") or {}
            if t.endswith("executeWorkflow"):
                calls.append(rl(p.get("workflowId")))
            if t.endswith("executeWorkflowTrigger"):
                trig.append("called-by-other-wf")
            elif t.endswith("webhook"):
                trig.append("webhook " + str(p.get("httpMethod", "GET")) + " /" + str(p.get("path", "")))
            elif t.endswith("scheduleTrigger") or t.endswith(".cron"):
                cr = [i.get("expression") or i.get("field") for i in ((p.get("rule") or {}).get("interval") or [])]
                trig.append("schedule " + ", ".join(str(c) for c in cr))
            elif any(x in t for x in TRIG):
                trig.append(t.split(".")[-1])
        err = rl((w.get("settings") or {}).get("errorWorkflow"))
        wfs[str(w.get("id"))] = dict(name=w.get("name"), active=w.get("active"), arch=w.get("isArchived"),
            upd=str(w.get("updatedAt", ""))[:16], strong=strong, weak=weak,
            trig=trig, calls=[c for c in calls if c], err=err, nodes=len(w.get("nodes") or []))

core = {i for i, w in wfs.items() if w["strong"]}
link = {}
for i in core:
    for c in wfs[i]["calls"] + ([wfs[i]["err"]] if wfs[i]["err"] else []):
        if c in wfs and c not in core:
            link[c] = "called-by " + i
for i, w in wfs.items():
    if i in core or i in link:
        continue
    for c in core:
        if c in w["calls"] or c == w["err"]:
            link[i] = "calls " + c

print("== total workflows:", len(wfs), "| related:", len(core), "| linked:", len(link), "==")
for group, ids in (("RELATED", sorted(core, key=lambda i: -len(wfs[i]["strong"]))), ("LINKED", sorted(link))):
    for i in ids:
        w = wfs[i]
        print("")
        state = "ARCHIVED" if w["arch"] else ("ON " if w["active"] else "off")
        print("[%s] %s %s | %s UTC | nodes=%d | %s" % (group, i, state, w["upd"], w["nodes"], w["name"]))
        print("   trigger :", "; ".join(w["trig"]) or "-")
        print("   calls   :", ", ".join("%s (%s)" % (c, wfs[c]["name"] if c in wfs else "?") for c in w["calls"]) or "-")
        print("   errorWF :", w["err"] or "-")
        if group == "RELATED":
            print("   matched :", ", ".join(w["strong"]), ("| weak: " + ", ".join(w["weak"])) if w["weak"] else "")
        else:
            print("   link    :", link[i])
print("")
print("== weak-only (anthropic/notion but no meeting keys):",
      ", ".join("%s (%s)" % (i, w["name"]) for i, w in wfs.items() if w["weak"] and not w["strong"]) or "-")
PY
```

แล้วตรวจว่าสคริปต์ไม่พัง:

```bash
python3 -m py_compile /tmp/wfscan.py && echo SCRIPT-OK
```

**ผลที่ถูก:** `SCRIPT-OK`

- ขึ้น `SyntaxError` หรือไม่ขึ้น `SCRIPT-OK` → รัน `rm -f /tmp/wfscan.py` แล้วพิมพ์ก้อนสคริปต์ใหม่ **1 ครั้ง**
  ถ้ายังพังอีก → ข้ามไปขั้นที่ 3ข

### ขั้นที่ 3ข — ทางสำรอง (เฉพาะเมื่อไม่มี Python หรือสคริปต์พัง 2 ครั้ง)

```bash
grep -l -i -E '1l8EqFMeuvqimmndrQ7jqGaKb6gyt0MIDOBh7HQgOKtA|3d5eeea9-8d22-8102-84af-f920e6532520|Cd05e936cea3e3e42e85ed9e80da85bf4|Qg0BsZe0MY3TbzZH|fireflies|transcript.md|mint-raw' /tmp/wfx/*.json
```

ผลเป็นรายชื่อไฟล์ เช่น `/tmp/wfx/AbC123xyz.json` → **ชื่อไฟล์ (ไม่รวม `.json`) คือ id ของ workflow**
จดทุก id ไว้ แล้วข้ามไปขั้นที่ 5 (ไปดูชื่อและดาวน์โหลดในหน้าเว็บ n8n)

### ขั้นที่ 4 — รันสคริปต์

```bash
python3 /tmp/wfscan.py /tmp/wfx > /tmp/wfscan.txt; wc -l /tmp/wfscan.txt; clear; sed -n '1,45p' /tmp/wfscan.txt
```

ถ้าบรรทัดแรกบอกว่ามีมากกว่า 45 บรรทัด ให้อ่านส่วนที่เหลือทีละหน้า:

```bash
clear; sed -n '46,90p' /tmp/wfscan.txt
```

```bash
clear; sed -n '91,140p' /tmp/wfscan.txt
```

**อ่านผลยังไง:**

| ส่วน | ความหมาย |
|---|---|
| บรรทัดแรก `== total workflows: N \| related: M \| linked: K ==` | มีทั้งหมด N ตัว · เกี่ยวข้องโดยตรง M ตัว · เชื่อมกับตัวที่เกี่ยวข้อง K ตัว |
| `[RELATED]` | มีคำเฉพาะของระบบมินท์อยู่ข้างใน (ดูบรรทัด `matched`) |
| `[LINKED]` | ไม่มีคำเฉพาะ แต่ **เรียก / ถูกเรียก / เป็นตัวรับ error** ของตัวที่เกี่ยวข้อง |
| `ON` / `off` / `ARCHIVED` | เปิดใช้งาน / ปิดอยู่ / ถูกเก็บเข้าคลัง |
| เวลา `... UTC` | เวลาที่แก้ล่าสุด เป็นเวลา UTC (เวลาไทย = บวก 7 ชั่วโมง) |
| `trigger` | ตัวเริ่มทำงาน: `schedule <cron>` ตั้งเวลา · `webhook POST /<path>` มีคนยิงเข้ามา · `called-by-other-wf` ถูก workflow อื่นเรียก |
| `calls` | workflow นี้เรียก workflow ไหนต่อ (id และชื่อ) |
| `errorWF` | ถ้าพังจะส่งไปให้ workflow ไหนจัดการ |
| `matched` | คำที่เจอ (ดูความหมายในตารางท้ายไฟล์) |
| บรรทัดสุดท้าย `weak-only` | ใช้ Anthropic/Notion แต่ไม่มีคำของระบบประชุม — **อาจไม่เกี่ยว** รายงานไว้เฉยๆ |

ก๊อปผลทุกบรรทัดเก็บไว้ใส่รายงาน

### ขั้นที่ 5 — ดาวน์โหลด JSON ของ workflow ที่เกี่ยวข้องจากหน้าเว็บ n8n

ทำกับ **ทุก id ในกลุ่ม `[RELATED]` และ `[LINKED]`** (หรือทุก id ที่ได้จากขั้นที่ 3ข)

1. เปิดแท็บใหม่ ไปที่ `https://n8n.srv1102218.hstgr.cloud/workflow/<id>` (แทน `<id>` ด้วย id จริง)
   - ถ้าเจอหน้า login → หยุดถามผู้ใช้ (ห้ามเดารหัสผ่าน)
2. กดปุ่ม **`⋯`** (สามจุด) มุมขวาบนของหน้า workflow → เลือก **Download**
3. ไฟล์จะลงโฟลเดอร์ Downloads ของเครื่องผู้ใช้ จดชื่อไฟล์ไว้
4. ไป workflow ถัดไปโดยแก้ URL ตรงๆ — **ถ้ามีหน้าต่างถามเรื่องบันทึกการแก้ไข ให้เลือกไม่บันทึก (Leave without saving)**

ห้ามกดปุ่มอื่นในหน้านี้ (ดูกติกาข้อ 2)

### ขั้นที่ 6 — ลบไฟล์ชั่วคราว (ทำเสมอ)

กลับไปที่แท็บ terminal

```bash
rm -rf /tmp/wfx /tmp/wfscan.py /tmp/wfscan.txt; docker exec -u node "$C" rm -rf /tmp/wfx; ls /tmp/wfx /tmp/wfscan.py 2>&1
```

**ผลที่ถูก:** มี `No such file or directory` 2 บรรทัด

- ถ้าขึ้น error เกี่ยวกับ `docker exec` เพราะ `C` หาย → รันบรรทัด `C=...` ในขั้นที่ 1 ใหม่ แล้วรันคำสั่งลบนี้อีกครั้ง
- ถ้าขั้นที่ 2 เคยต้องลบ `-u node` ออก ให้ลบออกจากคำสั่งนี้ด้วย

## รายงานผู้ใช้ (ใช้รูปแบบนี้ · แปลคำอังกฤษในผลเป็นไทย แต่ **ชื่อ workflow ให้คงตามเดิม**)

```
ผลค้นหา workflow ที่เกี่ยวกับระบบมินท์ (n8n เครื่อง srv1102218)
- container n8n: <ชื่อ> · workflow ทั้งหมด <N> ตัว

เกี่ยวข้องโดยตรง:
1. <ชื่อ> (id <id>) · เปิด/ปิด · แก้ล่าสุด <เวลาไทย>
   เริ่มทำงานจาก: <ตั้งเวลา ... / webhook ... / ถูกเรียกจาก workflow อื่น>
   เรียกต่อ: <ชื่อ (id)> · ส่ง error ไป: <ชื่อ (id) หรือ ไม่มี>
   เจอคำ: <...>
2. ...

เชื่อมกัน (ไม่มีคำของระบบ แต่เรียกหรือถูกเรียก):
1. <ชื่อ> (id <id>) · <เรียก/ถูกเรียกโดย ...>

ใช้ Anthropic/Notion แต่น่าจะไม่เกี่ยว: <รายชื่อ หรือ ไม่มี>

ไฟล์ที่ดาวน์โหลด: <ชื่อไฟล์> × <จำนวน> (อยู่ในโฟลเดอร์ Downloads)
ลบไฟล์ชั่วคราวแล้ว: ใช่ / ไม่ (เหตุผล)
ปัญหาที่เจอระหว่างทาง: <ไม่มี / ข้อความ error>
```

## คำค้นที่สคริปต์ใช้ (อ้างอิง)

| ชื่อในผล | หาอะไร | ความหมาย |
|---|---|---|
| `sheet-meeting` | `1l8EqFMeuvqimmndrQ7jqGaKb6gyt0MIDOBh7HQgOKtA` | ไฟล์ Google Sheets ทะเบียนประชุม / Action Items / พนักงาน |
| `notion-db` / `notion-db2` | `3d5eeea9-8d22-8102-84af-f920e6532520` | ฐานข้อมูลบันทึกประชุมใน Notion |
| `line-review-room` | `Cd05e936cea3e3e42e85ed9e80da85bf4` | กลุ่ม LINE ห้องตรวจ (James + ฮอน/เนย์) |
| `cred-line-mint` | `Qg0BsZe0MY3TbzZH` | credential "LINE (เลขาประชุม)" ใน n8n |
| `fireflies` · `transcript.md` · `mint-raw` | ข้อความตามชื่อ | ระบบถอดเสียง · ไฟล์ transcript · ไฟล์เซฟผลของมินท์ |
| `th:mint` · `th:meeting-register` · `th:sent-to-team` · `th:meeting-secretary` · `th:qc` · `th:wait-confirm` · `th:meeting-summary` | มินท์ · ทะเบียนประชุม · ส่งทีมแล้ว · เลขาประชุม · คิวซี · รอยืนยัน · สรุปประชุม | คำภาษาไทยในชื่อโหนด/คอลัมน์ (ในสคริปต์เขียนเป็นรหัส `\uXXXX` เพื่อไม่ต้องพิมพ์ภาษาไทยลง terminal) |
| weak: `anthropic-api` · `cred-anthropic` · `cred-notion` · `action-items` | `api.anthropic.com` · `xzQMuXfzuLZUkg5S` · `zF9TEhv2Z5tCSqvq` · `Action Items` | ใช้ร่วมกับงานอื่นได้ จึงนับเป็นคำอ่อน ไม่ทำให้ขึ้น RELATED |
