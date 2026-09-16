"""ดู/ตั้งค่า "ดักเก็บข้อมูลจากกลุ่ม LINE" จากบรรทัดคำสั่ง (ไม่ต้องเปิดเว็บ)

    python manage.py checkout_config                          # ดูค่าปัจจุบัน
    python manage.py checkout_config --store-chat on          # เปิดเก็บแชทกลุ่ม
    python manage.py checkout_config --customer-chat on       # เปิดเก็บแชทลูกค้า (1:1)
    python manage.py checkout_config --listen on --group Cxxx # ตั้งกลุ่มที่ดักเก็บเคส
    python manage.py checkout_config --send off               # ปิดการโพสต์กลับเข้ากลุ่ม

★ ก.ย.69 — ทำขึ้นเพราะเวลาตั้งค่าผ่านหน้าเว็บแล้วยังไม่เข้า **แยกไม่ออก**ว่า
  ลืมกดบันทึก / เบราว์เซอร์ค้างหน้าเก่า / หรือค่าไม่ถูกเก็บจริง
  คำสั่งนี้อ่าน-เขียน KVStore ตัวเดียวกับหน้าเว็บ → เห็นค่าจริงที่เซิร์ฟเวอร์ถืออยู่
"""
from django.core.management.base import BaseCommand

KEY = "checkout_line_config"
_FLAGS = [("store_chat", "store_chat", "เก็บแชทกลุ่ม"),
          ("customer_chat", "store_customer_chat", "เก็บแชทลูกค้า (1:1)"),
          ("listen", "listen", "ดักเก็บเคสเบิก-คืน"),
          ("send", "send", "ให้บอทโพสต์กลับเข้ากลุ่ม"),
          # ★ เปิดโดยปริยาย — ปิดเมื่อมีกลุ่มที่ลูกค้าปนอยู่ (จะได้ไม่ดูดเข้าทะเบียนพนักงาน)
          ("auto_employee", "auto_employee", "คนใหม่ในกลุ่ม = เพิ่มเข้าทะเบียนพนักงานให้เอง")]


def _kv_get():
    from dashboard.services import cache_store
    return (cache_store.get_kv(KEY) or {}).get("data") or {}


class Command(BaseCommand):
    help = "ดู/ตั้งค่าการดักเก็บข้อมูลจากกลุ่ม LINE"

    def add_arguments(self, p):
        p.add_argument("--group", help="LINE group id ที่จะดักเก็บเคสเบิก-คืน")
        for arg, _key, help_ in _FLAGS:
            p.add_argument("--" + arg.replace("_", "-"), choices=["on", "off"], help=help_)

    def handle(self, *a, **o):
        from dashboard.services import cache_store
        cfg = _kv_get()
        changed = []

        if o.get("group") is not None:
            cfg["group_id"] = (o["group"] or "").strip()
            changed.append("กลุ่มที่ดักเก็บ = %s" % (cfg["group_id"] or "(ล้างค่า)"))
        for arg, key, label in _FLAGS:
            val = o.get(arg)
            if val:
                cfg[key] = (val == "on")
                changed.append("%s = %s" % (label, "เปิด" if cfg[key] else "ปิด"))

        if changed:
            cache_store.set_kv(KEY, cfg)
            cfg = _kv_get()          # อ่านกลับจาก DB จริง — ยืนยันว่าเขียนติด
            self.stdout.write("บันทึกแล้ว:")
            for c in changed:
                self.stdout.write("   - " + c)
            self.stdout.write("")

        self.stdout.write("ค่าที่เซิร์ฟเวอร์ถืออยู่ตอนนี้")
        self.stdout.write("-" * 46)
        self.stdout.write("  กลุ่มที่ดักเก็บเคส : %s" % (cfg.get("group_id") or "(ยังไม่ได้ตั้ง)"))
        for _arg, key, label in _FLAGS:
            self.stdout.write("  %-20s: %s" % (label, "เปิด" if cfg.get(key) else "ปิด"))

        try:
            from checkout.models import GroupChat
            n = GroupChat.objects.count()
            self.stdout.write("")
            self.stdout.write("  แชทที่เก็บแล้ว     : %d ข้อความ" % n)
            if not (cfg.get("store_chat") or cfg.get("store_customer_chat")):
                self.stdout.write("  ⚠️ ยังไม่ได้เปิดเก็บแชทเลย → จะไม่มีอะไรเข้ามา")
            last = (cache_store.get_kv("chat_store_last") or {}).get("data") or {}
            if last.get("at"):
                self.stdout.write("  ลองเก็บล่าสุด      : %s — เก็บได้ %s · ข้าม %s (จาก %s event)"
                                  % (last.get("at"), last.get("saved"), last.get("skipped"),
                                     last.get("events")))
                if last.get("error"):
                    self.stdout.write("  ⚠️ error: %s" % last["error"])
            elif n == 0:
                self.stdout.write("  (ยังไม่เคยมีข้อความวิ่งเข้ามาให้เก็บเลย — ลองให้คนพิมพ์ในกลุ่ม 1 ครั้ง)")
        except Exception as e:
            self.stdout.write("")
            self.stdout.write("  ⚠️ อ่านตารางแชทไม่ได้ (%s) — ยัง migrate ไม่ครบหรือเปล่า?" % e)
