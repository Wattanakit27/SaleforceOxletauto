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
        name = name.replace("\\", "/")  # กัน path Windows (\) — Supabase key ต้องเป็น /
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
        # กันชื่อชน: แทรก uuid สั้น ๆ หน้าไฟล์ · normalize \ → / (Windows)
        name = name.replace("\\", "/")
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


@deconstructible
class GoogleDriveStorage(Storage):
    """เก็บไฟล์ลง Google Drive (ผ่าน cars/gdrive.py) — "name" ที่เก็บใน DB = Drive file id
    ใช้กับ ImageField/FileField ของ Car (photo, doc_registration). ส่วน media หลายไฟล์
    (ScanLog.media) อัปผ่าน api_upload โดยตรง ไม่ผ่าน backend นี้.
    เปิดใช้เมื่อตั้ง GDRIVE_* ครบ (ดู oxlet/settings.py) · file id ไม่มี "/" → แยกจาก path เก่าได้"""

    def _save(self, name, content):
        from . import gdrive
        base = name.replace("\\", "/").rsplit("/", 1)[-1]  # ใช้แค่ชื่อไฟล์ (folder จาก upload_to ทิ้ง)
        size = getattr(content, "size", None)
        ctype = getattr(getattr(content, "file", None), "content_type", "") \
            or getattr(content, "content_type", "")
        return gdrive.upload(content, base, content_type=ctype, size=size,
                             parent_id=getattr(settings, "GDRIVE_ROOT_FOLDER_ID", ""))

    def exists(self, name):
        return False  # name = Drive id (unique อยู่แล้ว) ไม่ต้องเช็ก

    def get_available_name(self, name, max_length=None):
        return name

    def url(self, name):
        from . import gdrive
        if not name:
            return ""
        if "/" in name:  # path — ดิสก์ VPS (/media/) หรือ Supabase legacy (ถ้ายังตั้ง bucket)
            # ★ ต้องเช็ค Supabase ก่อน (เหมือน _media_urls) — ไม่งั้นรูป target=disk (cars/CBxxxx/..)
            #   จะชี้ไป Supabase URL ที่ลบโปรเจกต์ไปแล้ว = รูปหน้าปกพัง
            if getattr(settings, "SUPABASE_STORAGE_BUCKET", "") and getattr(settings, "SUPABASE_URL", ""):
                base = settings.SUPABASE_URL.rstrip("/")
                bucket = settings.SUPABASE_STORAGE_BUCKET
                return f"{base}/storage/v1/object/public/{bucket}/{quote(name)}"
            return getattr(settings, "MEDIA_URL", "/media/").rstrip("/") + "/" + name.lstrip("/")
        return gdrive.photo_url(name)  # Drive file id → thumbnail (ใช้กับรูปรถ)

    def delete(self, name):
        if name and "/" not in name:
            from . import gdrive
            gdrive.delete(name)

    def size(self, name):
        return 0
