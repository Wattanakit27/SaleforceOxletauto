"""
Google Drive client — เก็บรูป/วิดีโอรถของแอป cars/ (tracking) ลง Drive ของบัญชี Gmail
ผ่าน REST (requests) ไม่มี SDK (ตาม convention โปรเจกต์)

ทำไม OAuth refresh token (ไม่ใช่ service account):
  service account อัปไฟล์ลง Google Drive ส่วนตัวไม่ได้ (quota = 0 ต้องมี Shared Drive/Workspace)
  → ใช้ OAuth ของบัญชี oxletauto@gmail.com ตรง ๆ (ไฟล์เป็นของบัญชีนี้ ใช้พื้นที่ Google One ที่ซื้อไว้)
  scope = drive.file (เห็น/แก้เฉพาะไฟล์ที่แอปสร้างเอง — ปลอดภัย ไม่แตะไฟล์อื่นในไดรฟ์)

เปิดใช้เมื่อ settings มีครบ: GDRIVE_CLIENT_ID + GDRIVE_CLIENT_SECRET + GDRIVE_REFRESH_TOKEN
(ขอ refresh token ครั้งเดียวด้วย `python manage.py gdrive_auth` — รันบนเครื่องที่มีเบราว์เซอร์)

ไฟล์ทุกตัวถูกตั้ง permission "anyone with link: reader" → ฝัง <img> / เปิดดูได้
  • รูป  → https://drive.google.com/thumbnail?id=<id>&sz=w1920  (ฝังใน <img> ได้)
  • วิดีโอ → https://drive.google.com/file/d/<id>/view            (เปิดตัวเล่นของ Drive)
"""
import threading
import time
from urllib.parse import quote

import requests
from django.conf import settings

FOLDER_MIME = "application/vnd.google-apps.folder"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_FILES = "https://www.googleapis.com/drive/v3/files"
_UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"

_token = {"value": "", "exp": 0.0}
_lock = threading.Lock()


def is_configured():
    return bool(
        getattr(settings, "GDRIVE_CLIENT_ID", "")
        and getattr(settings, "GDRIVE_CLIENT_SECRET", "")
        and getattr(settings, "GDRIVE_REFRESH_TOKEN", "")
    )


def _access_token():
    """access_token (cache จนกว่าจะใกล้หมดอายุ) — แลกจาก refresh_token"""
    now = time.time()
    if _token["value"] and now < _token["exp"] - 60:
        return _token["value"]
    with _lock:
        if _token["value"] and time.time() < _token["exp"] - 60:
            return _token["value"]
        r = requests.post(_TOKEN_URL, data={
            "client_id": settings.GDRIVE_CLIENT_ID,
            "client_secret": settings.GDRIVE_CLIENT_SECRET,
            "refresh_token": settings.GDRIVE_REFRESH_TOKEN,
            "grant_type": "refresh_token",
        }, timeout=20)
        if r.status_code != 200:
            raise IOError(f"gdrive token fail {r.status_code}: {r.text[:200]}")
        j = r.json()
        _token["value"] = j["access_token"]
        _token["exp"] = time.time() + int(j.get("expires_in", 3600))
        return _token["value"]


def _auth(extra=None):
    h = {"Authorization": f"Bearer {_access_token()}"}
    if extra:
        h.update(extra)
    return h


# ──────────────────────────── โฟลเดอร์ ────────────────────────────
def ensure_folder(name, parent_id="", existing_id=""):
    """คืน folder id ของรถคันนั้น — มี existing_id แล้ว = rename ให้ตรงชื่อปัจจุบัน (กรณีแก้ทะเบียน)
    ไม่มี = สร้างใหม่ใต้ parent_id (root ของไดรฟ์ถ้าไม่ระบุ). existing_id หาย (404) = สร้างใหม่."""
    if existing_id:
        r = requests.patch(f"{_FILES}/{existing_id}?fields=id",
                           headers=_auth({"Content-Type": "application/json"}),
                           json={"name": name}, timeout=20)
        if r.status_code == 200:
            return existing_id
        if r.status_code != 404:
            raise IOError(f"gdrive rename fail {r.status_code}: {r.text[:200]}")
        # 404 → โฟลเดอร์ถูกลบ สร้างใหม่
    meta = {"name": name, "mimeType": FOLDER_MIME}
    if parent_id:
        meta["parents"] = [parent_id]
    r = requests.post(f"{_FILES}?fields=id",
                      headers=_auth({"Content-Type": "application/json"}),
                      json=meta, timeout=20)
    if r.status_code not in (200, 201):
        raise IOError(f"gdrive folder fail {r.status_code}: {r.text[:200]}")
    return r.json()["id"]


# ──────────────────────────── อัปโหลดไฟล์ ────────────────────────────
def upload(fileobj, filename, content_type="", size=None, parent_id="", public=True):
    """อัปไฟล์ (resumable streaming — ไม่โหลดทั้งก้อนเข้า RAM) → คืน file id
    fileobj = file-like (Django UploadedFile หรือมี .read/.seek) · ตั้ง public link ให้เลย"""
    ctype = content_type or "application/octet-stream"
    if size is None:
        size = getattr(fileobj, "size", None)
    try:
        fileobj.seek(0)
    except Exception:
        pass

    meta = {"name": filename or "file"}
    if parent_id:
        meta["parents"] = [parent_id]
    # 1) เปิด resumable session
    init = requests.post(
        f"{_UPLOAD}?uploadType=resumable&fields=id",
        headers=_auth({
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": ctype,
            **({"X-Upload-Content-Length": str(size)} if size is not None else {}),
        }),
        json=meta, timeout=20,
    )
    if init.status_code not in (200, 201):
        raise IOError(f"gdrive init fail {init.status_code}: {init.text[:200]}")
    session_url = init.headers.get("Location")
    if not session_url:
        raise IOError("gdrive: ไม่มี session URL")

    # 2) PUT เนื้อไฟล์ (stream ตรงจาก fileobj)
    put_headers = {"Content-Type": ctype}
    if size is not None:
        put_headers["Content-Length"] = str(size)
    r = requests.put(session_url, data=fileobj, headers=put_headers, timeout=600)
    if r.status_code not in (200, 201):
        raise IOError(f"gdrive upload fail {r.status_code}: {r.text[:200]}")
    file_id = (r.json() or {}).get("id")
    if not file_id:
        raise IOError("gdrive: upload ไม่คืน id")

    if public:
        make_public(file_id)
    return file_id


def make_public(file_id):
    """ตั้งสิทธิ์ anyone with link = reader (ให้ฝัง <img>/เปิดดูได้)"""
    try:
        requests.post(f"{_FILES}/{quote(file_id)}/permissions?fields=id",
                      headers=_auth({"Content-Type": "application/json"}),
                      json={"role": "reader", "type": "anyone"}, timeout=20)
    except Exception:
        pass


def move_to_folder(file_id, folder_id):
    """ย้ายไฟล์เข้าโฟลเดอร์ (เอาออกจาก parent เดิมทั้งหมด) — best-effort"""
    if not (file_id and folder_id):
        return
    try:
        cur = requests.get(f"{_FILES}/{quote(file_id)}?fields=parents",
                           headers=_auth(), timeout=20)
        old = ",".join((cur.json() or {}).get("parents", [])) if cur.status_code == 200 else ""
        url = f"{_FILES}/{quote(file_id)}?addParents={folder_id}&fields=id"
        if old:
            url += f"&removeParents={old}"
        requests.patch(url, headers=_auth(), timeout=20)
    except Exception:
        pass


def delete(file_id):
    if not file_id:
        return
    try:
        requests.delete(f"{_FILES}/{quote(file_id)}", headers=_auth(), timeout=15)
    except Exception:
        pass


# ──────────────────────────── URL สำหรับแสดงผล ────────────────────────────
def photo_url(file_id, size="w1920"):
    return f"https://drive.google.com/thumbnail?id={file_id}&sz={size}"


def video_view_url(file_id):
    return f"https://drive.google.com/file/d/{file_id}/view"


def video_preview_url(file_id):
    return f"https://drive.google.com/file/d/{file_id}/preview"
