"""ตรวจว่า "ดักเก็บข้อมูลจากกลุ่ม LINE" ทำงานถึงไหนแล้ว — ใช้ระหว่างช่วงเฝ้าดู

    python manage.py checkout_status            # ภาพรวม + เคสที่บอทเก็บได้ 2 วันล่าสุด
    python manage.py checkout_status --days 7   # ย้อนหลัง 7 วัน
    python manage.py checkout_status --out r.txt

ตอบคำถาม "ทำไมข้อมูลไม่เข้า" ได้ในหน้าเดียว โดยไล่จากต้นทางไปปลายทาง:
  1. LINE ยิง webhook มาถึงเซิร์ฟเวอร์ไหม  (KVStore `line_webhook_last`)
  2. ลายเซ็นผ่านไหม                        (นับ sigFail)
  3. บอทรู้จักกลุ่มไหนบ้าง                  (KVStore `line_groups`)
  4. ตั้งกลุ่ม + ติ๊ก "เก็บข้อมูล" แล้วหรือยัง (KVStore `checkout_line_config`)
  5. ข้อความจากกลุ่มนั้นถูกอ่านกี่ข้อความ    (KVStore `checkout_seen_msgs`)
  6. กลายเป็นเคสกี่เคส                      (CarMovement source=line)
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from checkout import constants as C
from checkout.models import CarMovement


def _kv(key):
    try:
        from dashboard.services import cache_store
        return (cache_store.get_kv(key) or {}).get("data")
    except Exception:
        return None


class Command(BaseCommand):
    help = "ตรวจสถานะการดักเก็บข้อมูลจากกลุ่ม LINE (ใช้ช่วงเฝ้าดู)"

    def add_arguments(self, p):
        p.add_argument("--days", type=int, default=2, help="ดูเคสย้อนหลังกี่วัน (default 2)")
        p.add_argument("--out", help="เขียนรายงานลงไฟล์ (UTF-8)")

    def handle(self, *a, **o):
        L = []
        add = L.append
        now = timezone.localtime()
        add("=" * 60)
        add("สถานะการดักเก็บข้อมูลจากกลุ่ม LINE   (ตอนนี้ %s)" % now.strftime("%d/%m %H:%M"))
        add("=" * 60)

        # --- 1-2) webhook เข้ามาถึงไหม ---
        beat = _kv("line_webhook_last") or {}
        if not beat.get("at"):
            add("1) webhook จาก LINE : ❌ ยังไม่เคยมีเข้ามาเลย")
            add("   → ไปตั้ง Webhook URL ใน LINE Developers Console + เปิด Use webhook")
            add("     แล้วเพิ่มบอทเข้ากลุ่ม + พิมพ์อะไรก็ได้ในกลุ่ม 1 ครั้ง")
        else:
            add("1) webhook จาก LINE : ✅ เข้ามาแล้ว %s ครั้ง · ล่าสุด %s (ทาง %s)"
                % (beat.get("hits", 0), beat.get("at", "-"), beat.get("path", "-")))
        if beat.get("sigFail"):
            add("2) ลายเซ็น          : ⚠️ ไม่ผ่าน %s ครั้ง (ล่าสุด %s)"
                % (beat["sigFail"], beat.get("lastSigFailAt", "-")))
            add("   → LINE_CHANNEL_SECRET ใน env ไม่ตรงกับ channel ที่ตั้ง webhook ไว้")
        elif beat.get("at"):
            add("2) ลายเซ็น          : ✅ ผ่าน")

        # --- 3) บอทรู้จักกลุ่มไหนบ้าง ---
        groups = _kv("line_groups") or {}
        add("")
        add("3) กลุ่มที่บอทได้ยิน : %d กลุ่ม" % len(groups))
        for gid, v in list(groups.items())[:10]:
            add("     %s  %s" % ((v or {}).get("name") or "(ยังไม่รู้ชื่อ)", gid[:14] + "…"))

        # --- 4) ตั้งค่าแล้วหรือยัง ---
        cfg = _kv("checkout_line_config") or {}
        gid = (cfg.get("group_id") or "").strip()
        add("")
        add("4) ตั้งค่า")
        add("     กลุ่มที่ดักเก็บ : %s" % (gid or "❌ ยังไม่ได้เลือก"))
        if gid:
            add("     ชื่อกลุ่มนั้น   : %s" % ((groups.get(gid) or {}).get("name") or "(บอทยังไม่รู้ชื่อ)"))
            if gid not in groups:
                add("     ⚠️ กลุ่มนี้ไม่อยู่ในรายการที่บอทได้ยิน — อาจวาง id ผิด หรือบอทยังไม่ได้อยู่ในกลุ่ม")
        add("     เก็บข้อมูล     : %s" % ("✅ เปิด" if cfg.get("listen") else "❌ ปิด (จะไม่เก็บอะไรเลย)"))
        add("     ส่งเข้ากลุ่ม    : %s" % ("⚠️ เปิด" if cfg.get("send") else "ปิด (ถูกต้องสำหรับช่วงเฝ้าดู)"))

        # --- 5) อ่านข้อความไปกี่ข้อความ ---
        seen = _kv("checkout_seen_msgs") or []
        add("")
        add("5) ข้อความจากกลุ่มที่อ่านแล้ว : %d ข้อความ %s"
            % (len(seen), "(เก็บย้อนหลังสูงสุด 300)" if len(seen) >= 300 else ""))
        if beat.get("at") and gid and cfg.get("listen") and not seen:
            add("   ⚠️ webhook เข้าแต่ไม่มีข้อความถูกอ่านเลย → มักเป็นเพราะ **กลุ่มที่ตั้งไว้ไม่ตรงกับกลุ่มที่คนพิมพ์**")

        # --- 6) กลายเป็นเคสกี่เคส ---
        qs = CarMovement.objects.filter(source=CarMovement.SRC_LINE)
        since = now - timezone.timedelta(days=o["days"])
        recent = list(qs.filter(checked_out_at__gte=since).order_by("checked_out_at"))
        add("")
        add("6) เคสที่บอทเก็บได้ : ทั้งหมด %d เคส · ใน %d วันล่าสุด %d เคส"
            % (qs.count(), o["days"], len(recent)))
        if recent:
            add("")
            add("%-12s %-10s %-7s %-22s %s" % ("เวลาเบิก", "ผู้เบิก", "ทะเบียน", "งาน", "คืนแล้ว"))
            add("-" * 60)
            for m in recent:
                add("%-12s %-10s %-7s %-22s %s" % (
                    timezone.localtime(m.checked_out_at).strftime("%d/%m %H:%M") if m.checked_out_at else "-",
                    (m.borrower_name or "-")[:10],
                    m.plate_text or "-",
                    (m.purpose or "(เดาไม่ได้)")[:22],
                    timezone.localtime(m.returned_at).strftime("%H:%M") if m.returned_at else "ยังไม่คืน"))
            unknown = sum(1 for m in recent if m.borrower_name in ("", "ไม่ทราบชื่อ"))
            if unknown:
                add("")
                add("⚠️ เทียบชื่อเล่นไม่ได้ %d เคส — คนนั้นยังไม่มี LINE user id ในชีตพนักงาน" % unknown)
            noplate = sum(1 for m in recent if not m.plate_text)
            if noplate:
                add("⚠️ ไม่รู้ว่าคันไหน %d เคส — คนพิมพ์ไม่บอกทะเบียน (ส่งรูปแทน)" % noplate)
        elif cfg.get("listen") and gid:
            add("   (ยังไม่มีเคส — ถ้ามีคนพิมพ์เบิก/คืนในกลุ่มแล้วยังไม่ขึ้น ให้ดูข้อ 5)")

        # --- สรุปสั้น ---
        add("")
        add("-" * 60)
        if not beat.get("at"):
            add("สรุป: LINE ยังไม่ได้ยิง webhook มาเลย — ติดที่การตั้งค่าใน LINE Console")
        elif beat.get("sigFail") and not seen:
            add("สรุป: webhook เข้ามาแต่ลายเซ็นไม่ผ่าน → แก้ LINE_CHANNEL_SECRET")
        elif not gid:
            add("สรุป: บอทได้ยินกลุ่มแล้ว แต่ยังไม่ได้เลือกว่าจะเก็บกลุ่มไหน")
        elif not cfg.get("listen"):
            add("สรุป: เลือกกลุ่มแล้วแต่ยังไม่ติ๊ก 'เก็บข้อมูลจากกลุ่มนี้'")
        elif not seen:
            add("สรุป: ตั้งครบแล้วแต่ยังไม่มีข้อความเข้า — เช็คว่ากลุ่มที่ตั้งตรงกับกลุ่มที่ใช้งานจริง")
        else:
            add("สรุป: ทำงานอยู่ — อ่านไป %d ข้อความ เก็บเป็นเคสได้ %d เคส" % (len(seen), qs.count()))
        report = "\n".join(L)

        if o["out"]:
            with open(o["out"], "w", encoding="utf-8") as f:
                f.write(report)
            self.stdout.write("wrote report -> %s" % o["out"])
        else:
            self.stdout.write(report)
