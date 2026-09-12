"""ลงทะเบียนกลุ่ม LINE เข้าระบบด้วยมือ (ไม่ต้องรอ webhook) — ★ ก.ย.69

    python manage.py line_group_add --file groups.json
    python manage.py line_group_add --id C75fa… --name "ห้องจ่ายเบอร์ บ้านเก่า"
    cat groups.json | python manage.py line_group_add
    python manage.py line_group_add --file g.json --dry-run   # ดูเฉยๆ ไม่เขียน

ทำไมต้องมี: ปกติกลุ่มจะเข้าระบบเองตอน **webhook** ส่งข้อความจากกลุ่มนั้นมา
แต่ตอนนี้ inbound มาทาง n8n ทางเดียว และโหนดที่ส่ง "ชื่อกลุ่ม" ยังไม่ได้ทำ
→ กลุ่มที่บอทตัวใหม่เข้าไปอยู่จะยังไม่โผล่ในระบบเลย · คำสั่งนี้ให้เอา group id
มาใส่ตรงๆ ได้ก่อน แล้วค่อยปล่อยให้ webhook อัปเดตทับทีหลัง

รับ JSON รูปแบบที่ LINE/n8n คืนมาได้เลย (list หรือ object เดี่ยว · หลายก้อนติดกันก็ได้):
    [{"groupId": "C…", "groupName": "…", "pictureUrl": "…"}]
คีย์ที่รับ: groupId/group_id/id · groupName/group_name/name

⚠️ **ไม่เก็บรูปกลุ่ม (`pictureUrl`)** — ระบบไม่ได้ใช้ และไม่จำเป็นต้องสะสมไว้
"""
import json
import sys

from django.core.management.base import BaseCommand


def _pairs_from(obj):
    """แกะ [(gid, name)] จาก JSON หลายรูปแบบ — list / object เดี่ยว / ซ้อนใน body"""
    out = []

    def one(d):
        if not isinstance(d, dict):
            return
        gid = (d.get("groupId") or d.get("group_id") or d.get("id") or "").strip()
        name = (d.get("groupName") or d.get("group_name") or d.get("name") or "").strip()
        if gid:
            out.append((gid, name))

    if isinstance(obj, dict):
        inner = obj.get("body") or obj.get("json")
        if isinstance(inner, (dict, list)):
            return _pairs_from(inner)
        one(obj)
    elif isinstance(obj, list):
        for x in obj:
            out.extend(_pairs_from(x))
    return out


def _parse_many(raw):
    """อ่าน JSON ที่อาจมีหลายก้อนวางต่อกัน (แบบที่ก๊อปจาก n8n ทีละ node)"""
    raw = (raw or "").strip()
    if not raw:
        return []
    try:
        return _pairs_from(json.loads(raw))
    except Exception:
        pass
    out, dec, idx = [], json.JSONDecoder(), 0
    while idx < len(raw):
        while idx < len(raw) and raw[idx] in " \t\r\n,":
            idx += 1
        if idx >= len(raw):
            break
        try:
            obj, idx = dec.raw_decode(raw, idx)
        except Exception:
            break
        out.extend(_pairs_from(obj))
    return out


class Command(BaseCommand):
    help = "ลงทะเบียนกลุ่ม LINE เข้าระบบด้วยมือ (จาก JSON หรือ --id/--name)"

    def add_arguments(self, p):
        p.add_argument("--file", help="ไฟล์ JSON (UTF-8) — แนะนำ เพราะชื่อกลุ่มเป็นภาษาไทย")
        p.add_argument("--id", help="group id ตัวเดียว")
        p.add_argument("--name", default="", help="ชื่อกลุ่ม (คู่กับ --id)")
        p.add_argument("--dry-run", action="store_true", help="ดูว่าจะเพิ่มอะไร ไม่เขียนจริง")
        p.add_argument("--out", help="เขียนผลลงไฟล์ (กัน console ไทยเพี้ยน)")

    def handle(self, *a, **o):
        L = []
        add = L.append

        pairs = []
        if o.get("id"):
            pairs.append((o["id"].strip(), (o.get("name") or "").strip()))
        raw = ""
        if o.get("file"):
            with open(o["file"], encoding="utf-8") as f:
                raw = f.read()
        elif not pairs and not sys.stdin.isatty():
            raw = sys.stdin.read()
        pairs.extend(_parse_many(raw))

        # ตัดซ้ำ · เก็บตัวที่มีชื่อไว้
        uniq = {}
        for gid, name in pairs:
            if gid not in uniq or (name and not uniq[gid]):
                uniq[gid] = name
        pairs = list(uniq.items())

        if not pairs:
            add("❌ ไม่เจอ group id ในข้อมูลที่ส่งมา")
            add('   ใช้:  --file groups.json   หรือ   --id C… --name "ชื่อกลุ่ม"')
            self._emit(L, o)
            return

        add("จะลงทะเบียน %d กลุ่ม:" % len(pairs))
        for gid, name in pairs:
            add("   %-36s %s" % (gid, name or "(ไม่ได้ระบุชื่อ — จะลองดึงจาก LINE)"))

        if o.get("dry_run"):
            add("")
            add("(--dry-run · ยังไม่เขียนลงระบบ)")
            self._emit(L, o)
            return

        from dashboard.views import _store_line_groups
        added = _store_line_groups(pairs, source="manual")
        add("")
        add("✅ บันทึกแล้ว %d กลุ่ม" % len(added))

        # ตรวจว่าบัญชีไหนอยู่ในกลุ่มนี้จริง — ยืนยันว่าสั่ง push เข้าได้
        try:
            import requests
            from dashboard.services import line_channels as ch
            add("")
            add("ตรวจว่าบัญชีไหนอยู่ในกลุ่มนี้จริง (ดึงชื่อกลุ่มได้ = อยู่ในกลุ่ม)")
            add("-" * 62)
            from dashboard.services import cache_store
            store = (cache_store.get_kv("line_groups") or {}).get("data") or {}
            changed = False
            for gid, _n in pairs:
                who, roles = [], []
                for role in (ch.CRM, ch.PUSH):
                    tok = ch.token_of(role)
                    if not tok:
                        continue
                    try:
                        r = requests.get("https://api.line.me/v2/bot/group/%s/summary" % gid,
                                         headers={"Authorization": "Bearer %s" % tok}, timeout=8)
                        if r.status_code == 200:
                            roles.append(role)
                            who.append(ch.bot_info(tok).get("displayName") or role)
                    except Exception:
                        pass
                # ★ จดผลตรวจลงระบบเลย — ไม่งั้นรู้แค่ตอนรันคำสั่ง พอปิดจอก็หายไป
                #   (ลงทะเบียนด้วยมือไม่มี `destination` ให้ดู จึงต้องยืนยันด้วยการถาม LINE)
                if roles and store.get(gid) is not None:
                    if sorted(store[gid].get("channels") or []) != sorted(roles):
                        store[gid]["channels"] = roles
                        changed = True
                add("  %-24s %s" % (gid[:20] + "…", " + ".join(dict.fromkeys(who))
                                    or "❌ ไม่มีบัญชีไหนอยู่ในกลุ่ม (เช็ค id / เชิญบอทเข้ากลุ่มก่อน)"))
            if changed:
                cache_store.set_kv("line_groups", store)
                add("")
                add("   (จดไว้แล้วว่ากลุ่มไหนมีบัญชีไหนอยู่ — ใช้ตอนเลือกกลุ่มปลายทาง)")
        except Exception as e:
            add("  ⚠️ ตรวจไม่ได้: %s" % e)

        self._emit(L, o)

    def _emit(self, L, o):
        report = "\n".join(L)
        if o.get("out"):
            with open(o["out"], "w", encoding="utf-8") as f:
                f.write(report)
            self.stdout.write("wrote -> %s" % o["out"])
        else:
            self.stdout.write(report)
