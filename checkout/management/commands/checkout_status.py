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


def _ago(iso):
    """'2 ชม.ที่แล้ว' จาก ISO string — คืน (ข้อความ, ชั่วโมงที่ผ่านไป) · อ่านไม่ได้ = (ค่าเดิม, None)"""
    from datetime import datetime
    if not iso:
        return "-", None
    try:
        dt = datetime.fromisoformat(str(iso))
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt)
        h = (timezone.now() - dt).total_seconds() / 3600
        if h < 1:
            return "%d นาทีที่แล้ว" % max(1, int(h * 60)), h
        if h < 48:
            return "%.0f ชม.ที่แล้ว" % h, h
        return "%d วันที่แล้ว" % int(h / 24), h
    except Exception:
        return str(iso), None


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
        cfg0 = _kv("checkout_line_config") or {}      # อ่านก่อน เพราะข้อ 3 ต้องรู้ว่าตั้งกลุ่มไหนไว้
        add("=" * 60)
        add("สถานะการดักเก็บข้อมูลจากกลุ่ม LINE   (ตอนนี้ %s)" % now.strftime("%d/%m %H:%M"))
        add("=" * 60)

        # --- 1-2) webhook เข้ามาถึงไหม ---
        beat = _kv("line_webhook_last") or {}
        if not beat.get("at"):
            add("1) webhook เข้ามาไหม : ยังไม่มี **นับตั้งแต่รีสตาร์ทรอบล่าสุด**")
            add("   (ตัวจับนี้เพิ่งมี ก.ย.69 — ไม่ได้ย้อนหลัง · ดูข้อ 3 ว่าเคยถึงไหม)")
        else:
            txt, _h = _ago(beat.get("at"))
            add("1) webhook เข้ามาไหม : ✅ %s ครั้ง · ล่าสุด %s (ทาง %s)"
                % (beat.get("hits", 0), txt, beat.get("path", "-")))
        if beat.get("sigFail"):
            add("2) ลายเซ็น          : ⚠️ ไม่ผ่าน %s ครั้ง (ล่าสุด %s)"
                % (beat["sigFail"], beat.get("lastSigFailAt", "-")))
            add("   → LINE_CHANNEL_SECRET ใน env ไม่ตรงกับ channel ที่ตั้ง webhook ไว้")
        elif beat.get("at"):
            add("2) ลายเซ็น          : ✅ ผ่าน")

        # --- 2.5) อ่าน event ไม่ได้เลย → โชว์ "หน้าตา body ที่ส่งมา" ---
        #   ★ ตัวชี้ขาดว่า n8n forward "body ดิบ" มาจริงไหม · ไม่มีตัวนี้ได้แค่ตัวเลข events=0
        dbg = _kv("line_ingest_last") or {}
        if dbg.get("at") and not beat.get("events"):
            txt, _h = _ago(dbg.get("at"))
            add("")
            add("2.5) body ล่าสุดที่อ่าน event ไม่ได้ (%s · ทาง %s · %s bytes)"
                % (txt, dbg.get("path", "-"), dbg.get("bytes", 0)))
            add("     ชนิดที่ parse ได้ : %s" % dbg.get("parsedType", "-"))
            add("     คีย์ชั้นบนสุด    : %s" % (dbg.get("topKeys") or "(ไม่มี)"))
            add("     ตัวอย่าง         : %s" % (dbg.get("preview") or "")[:300])
            keys = set(dbg.get("topKeys") or [])
            if keys and not (keys & {"events", "destination"}):
                add("     → ไม่ใช่ body ดิบของ LINE (ต้องมีคีย์ 'events') = โหนดใน n8n ส่งผลของโหนดอื่นมาแทน")

        # --- 3) บอทรู้จักกลุ่มไหนบ้าง ---
        groups = _kv("line_groups") or {}
        add("")
        add("3) กลุ่มที่บอทได้ยิน : %d กลุ่ม  (เวลา = ได้ยินข้อความจากกลุ่มนั้นล่าสุด)" % len(groups))
        rows = sorted(groups.items(), key=lambda kv: (kv[1] or {}).get("lastSeen") or "", reverse=True)
        newest_h = None
        for gid, v in rows[:10]:
            txt, h = _ago((v or {}).get("lastSeen"))
            if newest_h is None or (h is not None and h < newest_h):
                newest_h = h
            mark = " ←ตั้งไว้" if gid == (cfg0 or {}).get("group_id") else ""
            add("     %-26s %-16s %s%s"
                % (((v or {}).get("name") or "(ยังไม่รู้ชื่อ)")[:26], txt, gid[:12] + "…", mark))

        # --- 4) ตั้งค่าแล้วหรือยัง ---
        cfg = cfg0
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
        # ★ ใช้ "ได้ยินกลุ่มล่าสุดเมื่อไหร่" เป็นหลักฐานหลัก — ย้อนหลังได้จริง
        #   (heartbeat ข้อ 1 เพิ่งมี ก.ย.69 นับตั้งแต่รีสตาร์ทเท่านั้น จะสรุปจากมันอย่างเดียวไม่ได้)
        if not groups:
            add("สรุป: บอทไม่เคยได้ยินกลุ่มไหนเลย → webhook ยังมาไม่ถึงเซิร์ฟเวอร์นี้")
            add("      เช็คว่า Webhook URL ชี้มาที่นี่ หรือถ้าชี้ไป n8n ให้ n8n forward มาที่")
            add("      POST /api/line/group_ingest (header X-Cron-Secret)")
        elif beat.get("sigFail") and not seen:
            add("สรุป: webhook เข้ามาแต่ลายเซ็นไม่ผ่าน → แก้ LINE_CHANNEL_SECRET ให้ตรง channel")
        elif not gid:
            add("สรุป: บอทได้ยินกลุ่มแล้ว แต่ยังไม่ได้เลือกว่าจะเก็บกลุ่มไหน")
        elif not cfg.get("listen"):
            add("สรุป: เลือกกลุ่มแล้วแต่ยังไม่ติ๊ก 'เก็บข้อมูลจากกลุ่มนี้'")
        elif seen:
            add("สรุป: ทำงานอยู่ — อ่านไป %d ข้อความ เก็บเป็นเคสได้ %d เคส" % (len(seen), qs.count()))
        elif newest_h is not None and newest_h <= 24:
            add("สรุป: ⚠️ บอท **ได้ยินกลุ่มเมื่อไม่กี่ชั่วโมงก่อน** แต่ยังไม่ได้อ่านข้อความสักข้อความ")
            # ★ อย่าเดา — ข้อ 2.5 บอกหน้าตา body จริงแล้ว ให้ชี้สาเหตุตามหลักฐาน
            _keys = set(dbg.get("topKeys") or [])
            if dbg.get("at") and int(dbg.get("bytes") or 0) <= 4 and not _keys:
                add("      = โหนดใน n8n ส่ง body **ว่างเปล่า** ({}) มา ไม่ใช่ข้อมูลของ LINE")
                add("      → โหนดนั้นรับ input มาจากโหนดที่ไม่มีข้อมูล (เช่นต่อท้าย HTTP node อื่น)")
                add("        แก้: ตั้ง body เป็น  {{ JSON.stringify($('Webhook').first().json.body) }}")
                add("        (อ้างชื่อโหนด Webhook ตรงๆ → วางไว้ตรงไหนในสายก็ทำงาน)")
            elif _keys and not (_keys & {"events", "destination"}):
                add("      = ตัว forward ส่งมาแต่ %s ไม่ได้ส่ง 'ตัวข้อความ' มาด้วย" % sorted(_keys)[:4])
                add("      → ใน n8n: HTTP Request node ต้องส่ง body ดิบทั้งก้อนที่ LINE ส่งมา")
            else:
                add("      → ใน n8n: HTTP Request node ต้องส่ง body ดิบทั้งก้อนที่ LINE ส่งมา")
                add("        แล้วดู response ว่าได้ textEvents >= 1 ไหม (ถ้าได้ 0 = ยังไม่ครบ)")
        else:
            when = ("ล่าสุด %s" % _ago(rows[0][1].get("lastSeen"))[0]) if rows else "-"
            add("สรุป: บอทเคยได้ยินกลุ่ม (%s) แต่ช่วงนี้เงียบ + ยังไม่มีข้อความถูกอ่าน" % when)
            add("      ลองให้คนพิมพ์อะไรก็ได้ในกลุ่มที่ตั้งไว้ 1 ครั้ง แล้วรันคำสั่งนี้ใหม่")
        report = "\n".join(L)

        if o["out"]:
            with open(o["out"], "w", encoding="utf-8") as f:
                f.write(report)
            self.stdout.write("wrote report -> %s" % o["out"])
        else:
            self.stdout.write(report)
