"""
ดึงข้อมูลระบบติดตามรถ (cars/) + ผู้ใช้ + รูป จาก Supabase เข้า DB/ดิสก์ของ VPS โดยตรง
— รันบน VPS (เว็บเทอร์มินัล Hostinger ก็ได้) · Supabase ต้องยังออนไลน์ · ไม่ต้องอัปไฟล์จากเครื่อง

  python manage.py import_from_supabase --url https://xxx.supabase.co --key <service_role_key>

ตัวเลือก: --skip-photos (เฉพาะข้อมูล) · --skip-data (เฉพาะรูป) · --bucket car-photos
idempotent — รันซ้ำได้ (loaddata update ตาม pk · รูป overwrite). ใช้คู่กับ deploy ขั้น 8.1
"""
import json
import os
import tempfile

import requests
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

TABLES = ["cars_branch", "auth_group", "auth_user", "auth_user_groups",
          "cars_car", "cars_scanlog", "cars_loginevent"]


class Command(BaseCommand):
    help = "ดึงข้อมูลรถ/ผู้ใช้/รูป จาก Supabase เข้า VPS โดยตรง (รันบน VPS)"

    def add_arguments(self, parser):
        parser.add_argument("--url", required=True, help="SUPABASE_URL เช่น https://xxx.supabase.co")
        parser.add_argument("--key", required=True, help="Supabase service_role key")
        parser.add_argument("--bucket", default="car-photos", help="ชื่อ storage bucket รูป")
        parser.add_argument("--skip-photos", action="store_true", help="ไม่โหลดรูป (เฉพาะข้อมูล)")
        parser.add_argument("--skip-data", action="store_true", help="ไม่โหลดข้อมูล (เฉพาะรูป)")

    def handle(self, *args, **o):
        url = o["url"].rstrip("/")
        headers = {"apikey": o["key"], "Authorization": "Bearer " + o["key"]}

        def fetch(table):
            rows, off = [], 0
            while True:
                r = requests.get(f"{url}/rest/v1/{table}?select=*&limit=1000&offset={off}",
                                 headers=headers, timeout=60)
                if r.status_code not in (200, 206):
                    raise CommandError(f"{table}: {r.status_code} {r.text[:200]}")
                batch = r.json()
                rows += batch
                if len(batch) < 1000:
                    return rows
                off += 1000

        data = {}

        # ── ข้อมูล DB → fixtures → loaddata ──
        if not o["skip_data"]:
            self.stdout.write("ดึงข้อมูลจาก Supabase...")
            for t in TABLES:
                data[t] = fetch(t)
                self.stdout.write(f"  {t}: {len(data[t])}")

            ug = {}
            for r in data["auth_user_groups"]:
                ug.setdefault(r["user_id"], []).append(r["group_id"])

            fix = []
            for r in data["cars_branch"]:
                fix.append({"model": "cars.branch", "pk": r.pop("id"), "fields": r})
            for r in data["auth_group"]:
                fix.append({"model": "auth.group", "pk": r.pop("id"),
                            "fields": {"name": r.get("name"), "permissions": []}})
            for r in data["auth_user"]:
                pk = r.pop("id"); r["groups"] = ug.get(pk, []); r["user_permissions"] = []
                fix.append({"model": "auth.user", "pk": pk, "fields": r})
            for r in data["cars_car"]:
                fix.append({"model": "cars.car", "pk": r.pop("code"), "fields": r})
            for r in data["cars_scanlog"]:
                pk = r.pop("id"); r["car"] = r.pop("car_id")
                fix.append({"model": "cars.scanlog", "pk": pk, "fields": r})
            for r in data["cars_loginevent"]:
                fix.append({"model": "cars.loginevent", "pk": r.pop("id"), "fields": r})

            tf = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
            json.dump(fix, tf, ensure_ascii=False, default=str)
            tf.close()
            try:
                call_command("loaddata", tf.name, verbosity=0)
            finally:
                os.unlink(tf.name)
            self.stdout.write(self.style.SUCCESS(f"โหลดข้อมูล {len(fix)} รายการเข้า DB แล้ว"))

        # ── รูปจาก Storage → MEDIA_ROOT ──
        if not o["skip_photos"]:
            if o["skip_data"]:
                data["cars_car"] = fetch("cars_car")
                data["cars_scanlog"] = fetch("cars_scanlog")
            paths = set()
            for r in data["cars_car"]:
                for f in (r.get("photo"), r.get("doc_registration")):
                    if f:
                        paths.add(f)
            for r in data["cars_scanlog"]:
                if r.get("photo"):
                    paths.add(r["photo"])
                for m in (r.get("media") or []):
                    p = m.get("path") if isinstance(m, dict) else m
                    if p and "/" in str(p):
                        paths.add(p)

            root = str(settings.MEDIA_ROOT)
            self.stdout.write(f"ดาวน์โหลดรูป {len(paths)} ไฟล์ -> {root}")
            ok = fail = 0
            for p in paths:
                try:
                    r = requests.get(f"{url}/storage/v1/object/{o['bucket']}/{p}", headers=headers, timeout=120)
                    if r.status_code == 200:
                        dest = os.path.join(root, *p.split("/"))
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        with open(dest, "wb") as fp:
                            fp.write(r.content)
                        ok += 1
                    else:
                        fail += 1
                except Exception:
                    fail += 1
            self.stdout.write(self.style.SUCCESS(f"รูปสำเร็จ {ok}/{len(paths)} (พลาด {fail})"))
