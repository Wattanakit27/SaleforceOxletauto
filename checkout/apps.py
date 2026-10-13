from django.apps import AppConfig


class CheckoutConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "checkout"
    verbose_name = "ระบบเบิก-คืนรถส่วนกลาง"

    def ready(self):
        # ★ 14 ต.ค.69 ตัวเฝ้าระบบลงชีตจ่ายเบอร์ (leadsheet.start_watchdog) — เฉพาะเว็บจริงใต้ gunicorn
        #   (ไม่เริ่มตอน manage.py / runserver / เทสต์) · ปิดได้ด้วย env LEADSHEET_WATCHDOG=0
        import os
        import sys
        if "gunicorn" in (sys.argv[0] if sys.argv else "") \
                and os.environ.get("LEADSHEET_WATCHDOG", "1") != "0":
            try:
                from . import leadsheet
                leadsheet.start_watchdog()
            except Exception:
                pass
