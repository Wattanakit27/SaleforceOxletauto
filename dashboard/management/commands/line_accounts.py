"""ดูว่าตอนนี้มีบัญชี LINE กี่ตัว ตัวไหนทำหน้าที่อะไร — ★ ก.ย.69

    python manage.py line_accounts              # ถาม LINE ว่า token เป็นของบัญชีไหน
    python manage.py line_accounts --offline    # ดูแค่ว่าตั้ง env ครบไหม (ไม่ยิงเน็ต)
    python manage.py line_accounts --groups     # เช็คด้วยว่าบัญชีไหนอยู่ในกลุ่มไหนบ้าง
    python manage.py line_accounts --out r.txt  # เขียนไฟล์ (กัน console ไทยเพี้ยน cp874)

ทำไมต้องมี: พอมี 2 บัญชี **วาง token สลับช่องแล้วระบบยังทำงานได้ครึ่งๆ** —
push ออกจากบัญชีผิดตัว (ลูกค้าเห็นชื่อบอทผิด) หรือดึงโปรไฟล์ไม่ได้แต่ไม่มี error ชัดๆ
คำสั่งนี้ถาม LINE ตรงๆ ว่า "token นี้คือบัญชีชื่ออะไร" → เห็นทันทีว่าวางถูกช่องไหม
โดยไม่ต้องส่งข้อความจริงเข้ากลุ่มเพื่อลอง
"""
from django.core.management.base import BaseCommand

from dashboard.services import line_channels as ch


class Command(BaseCommand):
    help = "ดูบัญชี LINE ที่ระบบใช้อยู่ (ตัวรับ/CRM + ตัวส่ง) และยืนยันว่า token เป็นของใคร"

    def add_arguments(self, p):
        p.add_argument("--offline", action="store_true", help="ไม่ยิง LINE — ดูแค่ env")
        p.add_argument("--groups", action="store_true", help="เช็คว่าบัญชีไหนอยู่ในกลุ่มไหน")
        p.add_argument("--out", help="เขียนผลลงไฟล์ (UTF-8)")

    def handle(self, *a, **o):
        L = []
        add = L.append
        live = not o.get("offline")

        add("=" * 66)
        add("บัญชี LINE ที่ระบบใช้อยู่")
        add("=" * 66)

        rows = ch.describe(live=live)
        for r in rows:
            add("")
            add("[%s]  %s%s" % (r["key"].upper(), r["roleName"],
                                  "" if r.get("legacy") else "   (เพิ่มเองใน .env)"))
            if not r["configured"]:
                add("   ❌ ยังไม่ได้ตั้ง token")
            elif r["shared"]:
                add("   ⚠️ ยังใช้บัญชีเดียวกับตัวรับ (ยังไม่ได้เอาบัญชีใหม่มาลง)")
                add("      ตั้ง LINE_PUSH_CHANNEL_ACCESS_TOKEN ใน .env เพื่อแยก")
            else:
                add("   ✅ ตั้งแล้ว (token ลงท้าย %s)" % r["tokenTail"])
            if r.get("error"):
                add("   ⚠️ ถาม LINE ไม่ได้: %s" % r["error"])
            elif r.get("displayName"):
                add("   ชื่อบัญชี : %s" % r["displayName"])
                add("   LINE id  : %s" % r.get("basicId", "-"))
                add("   โหมดแชท  : %s" % r.get("chatMode", "-"))
                # userId ของตัวบอท = ค่า `destination` ที่ LINE ใส่มาใน webhook
                # → ระบบใช้ค่านี้แยกว่าข้อความชุดไหนมาจากบัญชีไหน
                add("   destination (ใช้แยกว่า event มาจากบัญชีไหน) : %s" % r.get("userId", "-"))
            add("   ลายเซ็น webhook (%s) : %s"
                % (r["secretEnv"], "ตั้งแล้ว" if r["hasSecret"] else "❌ ยังไม่ได้ตั้ง"))
            if r.get("dmFrom"):
                add("")
                add("   ข้อความ 1:1 หา 'คน' (ตามด่วน/Flex เซลล์) ส่งจาก : %s"
                    % ("บัญชีตัวส่ง" if r["dmFrom"] == "push" else "บัญชีตัวรับ (ค่าเริ่มต้น)"))
                if r["dmFrom"] != "push":
                    add("   → ย้ายไปตัวส่งได้เมื่อทุกคนเพิ่มบัญชีใหม่เป็นเพื่อนแล้ว: LINE_DM_CHANNEL=push")

        # ── สรุปว่าตอนนี้กี่บัญชี ──
        add("")
        add("-" * 66)
        real = [r for r in rows if r["configured"] and not r["shared"]]
        n = len(real)
        if n >= 2:
            add("สรุป: ใช้อยู่ %d บัญชี" % n)
        elif n == 1:
            add("สรุป: มีบัญชีเดียว ทำทั้งรับและส่ง (ยังไม่ได้เอาบัญชีใหม่มาลง)")
        else:
            add("สรุป: ยังไม่ได้ตั้ง LINE token เลย")
        add("   เพิ่มบัญชีที่ 3 เป็นต้นไป: ใส่ LINE_OA_<คีย์>_TOKEN / _SECRET / _NAME ใน .env แล้ว restart")

        # ── ★ ตั้ง secret ไม่ครบ = อันตรายกว่าไม่ตั้งเลย ──
        has, miss = [r for r in real if r["hasSecret"]], [r for r in real if not r["hasSecret"]]
        add("")
        if not has:
            add("⚠️ ยังไม่ได้ตั้ง channel secret สักตัว → **ไม่มีการตรวจลายเซ็น webhook**")
            add("   = ใครก็ยิง /api/line/webhook มาได้ · ควรตั้ง LINE_CHANNEL_SECRET")
        elif miss:
            add("⛔ ตั้ง secret ไว้ %d บัญชี แต่ขาด %d บัญชี — **อันตรายกว่าไม่ตั้งเลย**" % (len(has), len(miss)))
            add("   ระบบเริ่มตรวจลายเซ็นทันทีที่มี secret สักตัว → event ของบัญชีที่ยังไม่ตั้ง")
            add("   จะโดนปฏิเสธ 403 ทั้งหมด (ถ้ายิง webhook ตรง ไม่ผ่าน n8n)")
            for r in miss:
                add("     ขาด: %s  (%s)" % (r["secretEnv"], r.get("displayName") or r["roleName"]))

        # ── ★ provider: ตัวชี้ขาดว่าลูกค้าคนเดียวจะถูกนับซ้ำไหม ──
        if n >= 2:
            add("")
            add("ℹ️ LINE ออก userId **ต่อ provider** ไม่ใช่ต่อ OA")
            add("   OA ที่ลูกค้าทักเข้ามาหลายตัว ถ้าอยู่คนละ provider = ลูกค้าคนเดียวกลายเป็นหลายคน")
            add("   เช็คที่ developers.line.biz/console (ดูว่าแต่ละ channel อยู่ใต้ provider ไหน)")
            add("   · ย้าย channel ข้าม provider ไม่ได้ → เลือกให้ถูกตั้งแต่ตอนสร้าง")

        # ── บัญชีไหนอยู่ในกลุ่มไหน ──
        if o.get("groups"):
            add("")
            add("=" * 66)
            add("บัญชีไหนอยู่ในกลุ่มไหน  (ดึงชื่อกลุ่มได้ = อยู่ในกลุ่มนั้น)")
            add("=" * 66)
            try:
                import requests
                from dashboard.services import cache_store
                groups = (cache_store.get_kv("line_groups") or {}).get("data") or {}
                if not groups:
                    add("  (บอทยังไม่รู้จักกลุ่มไหนเลย)")
                labels = {}
                for r in rows:
                    if r["configured"]:
                        labels[r["role"]] = r.get("displayName") or r["role"]
                for gid, v in sorted(groups.items(),
                                     key=lambda kv: (kv[1] or {}).get("lastSeen") or "", reverse=True):
                    who = []
                    for role, token in ((ch.CRM, ch.crm_token()), (ch.PUSH, ch.push_token())):
                        if not token:
                            continue
                        try:
                            resp = requests.get(
                                "https://api.line.me/v2/bot/group/%s/summary" % gid,
                                headers={"Authorization": "Bearer %s" % token}, timeout=8)
                            if resp.status_code == 200:
                                who.append(labels.get(role, role))
                        except Exception:
                            pass
                    add("  %-28s %s" % (((v or {}).get("name") or "(ไม่รู้ชื่อ)")[:28],
                                        " + ".join(dict.fromkeys(who)) or "❌ ไม่มีบัญชีไหนอยู่ในกลุ่ม"))
                add("")
                add("⚠️ กลุ่มที่จะให้ 'โพสต์สรุป/รายงาน' ต้องมี **บัญชีตัวส่ง** อยู่ในกลุ่มนั้น")
                add("   ส่วนกลุ่มที่จะ 'เก็บแชท' ต้องมีบัญชีที่ตั้ง webhook ไว้อยู่ในกลุ่ม")
            except Exception as e:
                add("  ⚠️ เช็คไม่ได้: %s" % e)

        report = "\n".join(L)
        if o.get("out"):
            with open(o["out"], "w", encoding="utf-8") as f:
                f.write(report)
            self.stdout.write("wrote -> %s" % o["out"])
        else:
            self.stdout.write(report)
