"""ทะเบียนกลุ่ม LINE — ย้าย/อัปเดตจาก JSON ก้อนเดียว (`dash_kv['line_groups']`) มาเป็นตารางจริง

    python manage.py line_groups_sync                       # ดูสถานะ (ไม่เขียนอะไร)
    python manage.py line_groups_sync --apply               # สร้าง/อัปเดตแถวในตาราง
    python manage.py line_groups_sync --set Cxxx=coaching   # ตั้งประเภทเอง (ระบบจะไม่เดาทับอีก)
    python manage.py line_groups_sync --kinds               # ดูรายชื่อประเภทที่มีให้เลือก
    python manage.py line_groups_sync --out ไฟล์.txt         # เขียนผลลงไฟล์ (console ไทยเพี้ยน)

★ เจ้าของสั่ง 28 ก.ย.69: *"จริงๆ ควรแยกชัดกลุ่มแต่ละกลุ่มนะ"*
★ **ไม่ลบอะไรทิ้ง** — KVStore `line_groups` ยังเขียนอยู่เหมือนเดิม (ของเดิมหลายตัวอ่านคีย์นั้น)
★ ประเภทที่ "ระบบเดาให้จากชื่อกลุ่ม" ติดป้าย `kind_auto=True` ไว้ → คนมาตั้งเองเมื่อไหร่
  ระบบจะไม่เดาทับอีก (บทเรียนเดิม: ค่าที่เดาให้ ถ้าไม่ติดป้ายจะกลายเป็นของจริงโดยไม่มีใครแก้)
"""
import io

from django.core.management.base import BaseCommand

# คำใบ้ → ประเภท · **เรียงจากเฉพาะเจาะจงไปกว้าง** (ตัวแรกที่ตรงชนะ)
HINTS = [
    ("coaching", ["coaching", "โค้ช", "โคช"]),
    ("checkin", ["เช็คชื่อ", "เช็กชื่อ", "ลงเวลา"]),
    ("lead", ["จ่ายเบอร์", "จ่ายลีด", "แจกเบอร์"]),
    ("tradein", ["เคสhot", "ซื้อ-ขาย", "ซื้อขาย", "เทิร์น"]),
    ("purchase", ["จัดซื้อ", "รับรถเข้า", "รถเข้าใหม่"]),
    ("finance", ["ไฟแนนซ์", "ไฟแนน"]),
    ("booking", ["จองรถ", "ห้องจอง"]),
    ("transfer", ["รับ-ส่ง", "รับส่ง", "ระหว่างสาขา"]),
    ("hr", ["รับสมัคร", "สมัครงาน", "บุคคล"]),
    ("content", ["content", "branding", "marketing", "คอนเทนต์", "การตลาด"]),
    ("admin", ["ทีมadmin", "แอดมิน", "admin"]),
]


def guess_kind(name):
    n = (name or "").lower().replace(" ", "")
    for kind, words in HINTS:
        for wd in words:
            if wd.replace(" ", "") in n:
                return kind
    return "other"


class Command(BaseCommand):
    help = "ทะเบียนกลุ่ม LINE: ย้ายจาก KVStore มาเป็นตาราง + จัดประเภทกลุ่ม"

    def add_arguments(self, p):
        p.add_argument("--apply", action="store_true", help="เขียนลงตารางจริง")
        p.add_argument("--set", action="append", default=[],
                       help="ตั้งประเภทเอง: --set <group_id|ชื่อบางส่วน>=<ประเภท>")
        p.add_argument("--kinds", action="store_true", help="ดูรายชื่อประเภททั้งหมด")
        p.add_argument("--out", help="เขียนผลลงไฟล์ (UTF-8)")

    def handle(self, *a, **o):
        from django.db.models import Count, Max
        from django.utils import timezone

        from dashboard.services import cache_store

        from ...models import GroupChat, LineGroup
        out = []

        def say(s=""):
            out.append(s)

        if o["kinds"]:
            say("ประเภทกลุ่มที่มีให้เลือก:")
            for k, label in LineGroup.KIND_CHOICES:
                say("   %-10s %s" % (k, label))
            return self._w(out, o)

        # ── 1. รวบรวมกลุ่มจาก 2 แหล่ง: ทะเบียน KV + กลุ่มที่เคยมีข้อความจริง ──
        kv = (cache_store.get_kv("line_groups") or {}).get("data") or {}
        found = {}
        for gid, v in (kv.items() if isinstance(kv, dict) else []):
            v = v if isinstance(v, dict) else {}
            found[gid] = {"name": v.get("name") or "", "channels": v.get("channels") or [],
                          "source": v.get("source") or "webhook"}
        chat = (GroupChat.objects.filter(chat_type=GroupChat.GROUP).exclude(group_id="")
                .values("group_id").annotate(n=Count("id"), last=Max("sent_at"),
                                             nm=Max("group_name")))
        counts = {}
        for r in chat:
            counts[r["group_id"]] = (r["n"], r["last"])
            cur = found.setdefault(r["group_id"], {"name": "", "channels": [], "source": "chat"})
            if not cur["name"]:
                cur["name"] = r["nm"] or ""

        say("กลุ่มที่เจอทั้งหมด %d  (ในทะเบียน KV %d · มีข้อความจริง %d)"
            % (len(found), len(kv or {}), len(counts)))
        say("")

        # ── 2. ตั้งประเภทเองตามที่สั่ง ──
        manual = {}
        valid = {k for k, _ in LineGroup.KIND_CHOICES}
        for item in o["set"]:
            if "=" not in item:
                say("⚠️ ข้าม --set %s (ต้องเป็น <กลุ่ม>=<ประเภท>)" % item)
                continue
            key, kind = item.rsplit("=", 1)
            kind = kind.strip()
            if kind not in valid:
                say("⚠️ ไม่รู้จักประเภท '%s' — ดูรายการด้วย --kinds" % kind)
                continue
            hit = [g for g in found if g == key.strip()
                   or key.strip().lower() in (found[g]["name"] or "").lower()]
            if len(hit) != 1:
                say("⚠️ '%s' ตรงกับ %d กลุ่ม — ระบุ group id ให้ชัด" % (key, len(hit)))
                continue
            manual[hit[0]] = kind

        # ── 3. เขียน / แสดงผล ──
        rows, new, upd = [], 0, 0
        for gid, v in sorted(found.items(), key=lambda x: -(counts.get(x[0], (0,))[0])):
            n, last = counts.get(gid, (0, None))
            obj = LineGroup.objects.filter(group_id=gid).first() if o["apply"] else None
            if o["apply"]:
                if obj is None:
                    obj = LineGroup(group_id=gid, source=v["source"])
                    new += 1
                else:
                    upd += 1
                if v["name"]:
                    obj.name = v["name"]
                obj.channels = v["channels"]
                if gid in manual:                      # คนตั้งเอง → เลิกเดาทับตลอดไป
                    obj.kind, obj.kind_auto = manual[gid], False
                elif obj.kind_auto:                    # ยังเป็นค่าที่ระบบเดา → เดาใหม่ได้
                    obj.kind = guess_kind(obj.name)
                if last:
                    obj.last_seen = last
                elif not obj.pk:
                    obj.last_seen = timezone.now()
                obj.save()
                kind, auto = obj.kind, obj.kind_auto
            else:
                kind = manual.get(gid) or guess_kind(v["name"])
                auto = gid not in manual
            rows.append((n, v["name"] or "(ไม่ทราบชื่อ)", kind, auto, gid))

        say("%-7s %-38s %-10s %s" % ("ข้อความ", "ชื่อกลุ่ม", "ประเภท", "id"))
        say("-" * 96)
        for n, name, kind, auto, gid in rows:
            say("%7s %-38s %-10s %s%s"
                % ("{:,}".format(n) if n else "-", name[:38], kind,
                   gid[:12] + "…", "  ← ระบบเดาให้" if auto else ""))
        say("")
        if o["apply"]:
            say("เขียนแล้ว: เพิ่มใหม่ %d · อัปเดต %d" % (new, upd))
            say("ตั้งประเภทเอง:  manage.py line_groups_sync --set <group id>=<ประเภท> --apply")
        else:
            say("** ยังไม่ได้เขียนอะไร ** ใส่ --apply เพื่อบันทึกลงตาราง `checkout_linegroup`")
        n_auto = sum(1 for r in rows if r[3])
        if n_auto:
            say("⚠️ %d กลุ่มยังเป็นประเภทที่ระบบเดาให้ — ตรวจแล้วตั้งเองด้วย --set" % n_auto)
        return self._w(out, o)

    def _w(self, lines, o):
        text = "\n".join(lines)
        if o.get("out"):
            with io.open(o["out"], "w", encoding="utf-8") as f:
                f.write(text + "\n")
            self.stdout.write("wrote %s (%d lines)" % (o["out"], len(lines)))
            return
        for ln in lines:
            try:
                self.stdout.write(ln)
            except UnicodeEncodeError:
                self.stdout.write(ln.encode("ascii", "replace").decode())
