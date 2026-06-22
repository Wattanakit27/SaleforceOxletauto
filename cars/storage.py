"""
Supabase Storage backend — เก็บรูปรถ/สแกน/เล่มทะเบียนของแอป cars/ (tracking)
ผ่าน REST (requests) ไม่มี SDK · Vercel serverless เขียนไฟล์ถาวรไม่ได้ → ต้องเก็บนอก

เปิดใช้อัตโนมัติเมื่อ settings มีครบ: SUPABASE_URL + SUPABASE_SECRET_KEY + SUPABASE_STORAGE_BUCKET
(ดู oxlet/settings.py · ถ้าไม่ครบ จะ fallback FileSystemStorage = local dev เท่านั้น)
"""
import mimetypes
import posixpath
import uuid
from urllib.parse import quote

import requests
from django.conf import settings
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible


@deconstructible
class SupabaseStorage(Storage):
    def __init__(self, bucket=None):
        self.base = (getattr(settings, "SUPABASE_URL", "") or "").rstrip("/")
        self.key = getattr(settings, "SUPABASE_SECRET_KEY", "") or ""
        self.bucket = bucket or getattr(settings, "SUPABASE_STORAGE_BUCKET", "") or ""

    # ---- helpers ----
    def _headers(self, extra=None):
        h = {"Authorization": f"Bearer {self.key}", "apikey": self.key}
        if extra:
            h.update(extra)
        return h

    def _object_url(self, name):
        return f"{self.base}/storage/v1/object/{self.bucket}/{quote(name)}"

    # ---- Django Storage API ----
    def _save(self, name, content):
        content.seek(0)
        data = content.read()
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        r = requests.post(
            self._object_url(name),
            data=data,
            headers=self._headers({"Content-Type": ctype, "x-upsert": "true"}),
            timeout=30,
        )
        if r.status_code not in (200, 201):
            raise IOError(f"Supabase upload failed {r.status_code}: {r.text[:200]}")
        return name

    def exists(self, name):
        # คืน False เสมอ → ใช้ชื่อจาก get_available_name (unique อยู่แล้ว) ไม่วนลูปเช็ก
        return False

    def get_available_name(self, name, max_length=None):
        # กันชื่อชน: แทรก uuid สั้น ๆ หน้าไฟล์
        folder = posixpath.dirname(name)
        base = posixpath.basename(name)
        newbase = f"{uuid.uuid4().hex[:8]}-{base}"
        return posixpath.join(folder, newbase) if folder else newbase

    def url(self, name):
        # bucket ต้องตั้งเป็น public read
        return f"{self.base}/storage/v1/object/public/{self.bucket}/{quote(name)}"

    def delete(self, name):
        try:
            requests.delete(self._object_url(name), headers=self._headers(), timeout=15)
        except Exception:
            pass

    def size(self, name):
        return 0
