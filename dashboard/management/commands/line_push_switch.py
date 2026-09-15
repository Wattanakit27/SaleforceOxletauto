"""ย้าย "ปลายทางกลุ่ม" ทุกจุดที่ตั้งไว้ ให้เป็น group id ที่บอทตัวส่ง (OxletautoGiveLead) ส่งได้ — ★ ก.ย.69

    python manage.py line_push_switch                 # ดูเฉยๆ (ค่าเริ่มต้น ไม่เขียนอะไร)
    python manage.py line_push_switch --apply         # เขียนจริง
    python manage.py line_push_switch --out ผล.txt    # console ไทยเพี้ยน → เขียนไฟล์

ทำไมต้องมี: โค้ดส่งเข้ากลุ่มด้วยบัญชีตัวส่งอยู่แล้ว (`token_for`) แต่ **group id ออกต่อ provider**
กลุ่มเดียวกันมี id คนละตัวในสายตาบอทแต่ละตัว → ปลายทางที่ตั้งไว้สมัยบอทเดิมใช้กับบอทใหม่ไม่ได้
(15/09 การ์ดตั้งเวลาทุกใบส่งไม่ออก: LINE 400 "Failed to send messages")

ทำอะไร (ต่อทุก group id ที่ตั้งไว้):
  1. บอทตัวส่งอยู่ในกลุ่มนี้แล้ว → ไม่แตะ
  2. ไม่อยู่ → หาชื่อกลุ่ม (ถาม LINE ด้วยบัญชีอื่น / ทะเบียน `line_groups`)
     → หา id ฝั่งบอทตัวส่งที่ชื่อตรงกันในทะเบียน → **ถาม LINE ยืนยันอีกรอบ** ว่าบอทตัวส่งอยู่จริงและชื่อตรง
  3. หาไม่เจอ / ชื่อซ้ำหลายกลุ่ม = **ไม่แตะ** แล้วบอกว่าต้องทำอะไรก่อน (ไม่เดา)

จุดที่ตรวจ: การ์ดส่งไลน์ทุกใบ (`cardline_*`) · รายงานรายวัน (`report_line_config`) ·
กลุ่มเบิก-คืนรถ (`checkout_line_config`) · และรายงานค่า `LINE_GROUP_ID` ใน .env (แก้เองเท่านั้น)
**ไม่แตะแชท 1:1 (test id ที่ขึ้นต้น U)** — ส่งหาคนยังใช้บัญชีเดิมตาม `dm_token()`
"""
from django.core.management.base import BaseCommand


def _norm(name):
    return " ".join((name or "").split()).lower()


class Command(BaseCommand):
    help = "ย้ายปลายทางกลุ่มทุกจุดให้เป็น id ที่บอทตัวส่ง (OxletautoGiveLead) ส่งได้"

    def add_arguments(self, p):
        p.add_argument("--apply", action="store_true", help="เขียนจริง (ไม่ใส่ = ดูเฉยๆ)")
        p.add_argument("--out", help="เขียนผลลงไฟล์ UTF-8")

    def handle(self, *a, **o):
        import requests
        from django.conf import settings
        from dashboard.models import KVStore
        from dashboard.services import cache_store
        from dashboard.services import line_channels as ch

        L = []
        add = L.append
        apply = o["apply"]
        push_tok = ch.push_token()
        me = ch.bot_info(push_tok) if push_tok else {"error": "ไม่มี token"}
        add("บอทตัวส่ง: %s (%s)" % (me.get("displayName") or "-", me.get("basicId") or me.get("error") or "-"))
        if not ch.has_push_channel():
            add("⛔ ยังไม่ได้ตั้ง LINE_PUSH_CHANNEL_ACCESS_TOKEN แยก — ไม่มีอะไรให้ย้าย")
            return self._emit(L, o)
        add("โหมด: %s" % ("เขียนจริง" if apply else "ดูเฉยๆ (ใส่ --apply เพื่อเขียน)"))
        add("")

        reg = (cache_store.get_kv("line_groups") or {}).get("data") or {}
        other_tokens = [t for t in ch.group_tokens() if t != push_tok]

        def old_name(gid):
            for t in other_tokens:
                try:
                    r = requests.get("https://api.line.me/v2/bot/group/%s/summary" % gid,
                                     headers={"Authorization": "Bearer %s" % t}, timeout=8)
                    if r.status_code == 200:
                        return (r.json() or {}).get("groupName", "")
                except Exception:
                    pass
            name = (reg.get(gid) or {}).get("name", "")
            if name:
                return name
            # ★ ทะเบียนเคยทำกลุ่มหาย + บอทเดิมอาจออกจากกลุ่มแล้ว (ถาม LINE ไม่ได้)
            #   → ชื่อกลุ่มที่จดไว้ในคลังแชทเป็นแหล่งสุดท้าย (เจอจริงบนเซิร์ฟเวอร์ 16/09)
            try:
                from checkout.models import GroupChat
                return (GroupChat.objects.filter(group_id=gid).exclude(group_name="")
                        .order_by("-sent_at").values_list("group_name", flat=True).first()) or ""
            except Exception:
                return ""

        cache = {}

        def resolve(gid):
            """คืน (สถานะ, id ใหม่, ชื่อ, หมายเหตุ) · สถานะ = ok | switch | missing | unknown"""
            if gid in cache:
                return cache[gid]
            chk = ch.push_group_check(gid)
            if chk["ok"] is True:
                res = ("ok", gid, chk["name"], "")
            elif chk["ok"] is None:
                res = ("unknown", "", "", chk["error"])
            else:
                name = old_name(gid)
                cands = [g for g, v in reg.items()
                         if g != gid and name and _norm((v or {}).get("name")) == _norm(name)
                         and ch.PUSH in ((v or {}).get("channels") or [])]
                hits = []
                for c in cands:
                    cc = ch.push_group_check(c)
                    if cc["ok"] is True and _norm(cc["name"]) == _norm(name):
                        hits.append(c)
                if len(hits) == 1:
                    res = ("switch", hits[0], name, "")
                elif len(hits) > 1:
                    res = ("missing", "", name, "มีหลายกลุ่มชื่อ \"%s\" — เลือกเองในหน้าตั้งค่า" % name)
                else:
                    res = ("missing", "", name,
                           "บอทตัวส่งยังไม่อยู่ในกลุ่ม \"%s\" (หรือยังไม่มีข้อความจากกลุ่มนั้นเข้ามา) — เชิญบอทก่อน"
                           % (name or gid))
            cache[gid] = res
            return res

        todo = []     # (ป้าย, คีย์ใน KV)
        for row in (KVStore.objects.filter(key__startswith="cardline_")
                    .exclude(key__startswith="cardline_last_").exclude(key="cardline_lock")
                    .only("key").order_by("key")):
            todo.append(("การ์ด " + row.key[len("cardline_"):], row.key))
        todo.append(("รายงานรายวัน", "report_line_config"))
        todo.append(("กลุ่มเบิก-คืนรถ (ดักเก็บ+โพสต์สรุป)", "checkout_line_config"))

        n_ok = n_sw = n_miss = n_unk = 0
        need_invite = {}
        for label, key in todo:
            data = (cache_store.get_kv(key) or {}).get("data") or {}
            gid = str(data.get("group_id") or "").strip()
            on = data.get("enabled", data.get("listen"))
            tag = "" if on is None else (" [เปิดอยู่]" if on else " [ปิดอยู่]")
            if not gid:
                add("· %s%s — ไม่ได้ตั้งกลุ่ม ข้าม" % (label, tag))
                continue
            st, new, name, note = resolve(gid)
            if st == "ok":
                n_ok += 1
                add("✅ %s%s — ใช้ได้แล้ว: %s" % (label, tag, name or gid))
            elif st == "switch":
                n_sw += 1
                add("🔁 %s%s — \"%s\"  %s… → %s…" % (label, tag, name, gid[:10], new[:10]))
                if apply:
                    data["group_id"] = new
                    cache_store.set_kv(key, data)
            elif st == "missing":
                n_miss += 1
                need_invite[name or gid] = need_invite.get(name or gid, 0) + 1
                add("⚠️ %s%s — %s" % (label, tag, note))
            else:
                n_unk += 1
                add("❔ %s%s — ถาม LINE ไม่ได้: %s (ไม่แตะ)" % (label, tag, note))

        add("")
        add("สรุป: ใช้ได้แล้ว %d · %s %d · ต้องจัดการเอง %d · ตรวจไม่ได้ %d"
            % (n_ok, "ย้ายแล้ว" if apply else "จะย้าย", n_sw, n_miss, n_unk))
        for name, n in need_invite.items():
            add("   → เชิญ %s เข้ากลุ่ม \"%s\" (%d จุดรออยู่) ให้มีคนพิมพ์ในกลุ่ม 1 ครั้ง แล้วรันคำสั่งนี้ซ้ำ"
                % (me.get("basicId") or "บอทตัวส่ง", name, n))

        # ── ช่อง .env ของระบบติดตามรถ (อ่านอย่างเดียว — .env ต้องแก้เอง) ──
        cars_gid = (getattr(settings, "LINE_GROUP_ID", "") or "").strip()
        cars_tok = (getattr(settings, "LINE_CHANNEL_TOKEN", "") or "").strip()
        add("")
        if cars_gid and cars_tok:
            which = ("ตัวส่ง" if cars_tok == push_tok
                     else "ตัวรับ (บอทเดิม)" if cars_tok == ch.crm_token() else "บัญชีอื่น")
            add("ℹ️ แจ้งเตือนเปลี่ยนสเตปรถ (.env LINE_GROUP_ID) เปิดอยู่ · token = %s" % which)
            if cars_tok != push_tok:
                add("   → ถ้าจะย้าย: แก้ .env ให้ LINE_CHANNEL_TOKEN = token ตัวส่ง และ LINE_GROUP_ID = id ฝั่งตัวส่ง แล้ว restart")
        else:
            add("ℹ️ แจ้งเตือนเปลี่ยนสเตปรถ (.env LINE_GROUP_ID) ไม่ได้ตั้ง — ไม่มีอะไรต้องย้าย")
        add("ℹ️ แชท 1:1 (ตามด่วนรายเซลล์) ไม่ได้ย้าย — ยังส่งจากบัญชีเดิมจนกว่าจะตั้ง LINE_DM_CHANNEL=push")
        self._emit(L, o)

    def _emit(self, L, o):
        report = "\n".join(L)
        if o.get("out"):
            with open(o["out"], "w", encoding="utf-8") as f:
                f.write(report)
            self.stdout.write("wrote -> %s" % o["out"])
        else:
            self.stdout.write(report)
