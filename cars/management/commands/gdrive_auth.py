"""
ขอ Google Drive refresh token (ครั้งเดียว) สำหรับเก็บรูป/วิดีโอรถ

วิธีใช้ (รันบน "เครื่องที่มีเบราว์เซอร์" เช่น โน้ตบุ๊กตัวเอง — ไม่ใช่บน VPS):
  1) Google Cloud Console → APIs & Services → เปิดใช้ "Google Drive API"
  2) OAuth consent screen: User type = External · เพิ่ม scope .../auth/drive.file
     · Publishing status = "In production" (กัน refresh token หมดอายุใน 7 วันของโหมด Testing)
     · เพิ่มบัญชี oxletauto@gmail.com เป็น user (ถ้ายัง Testing)
  3) Credentials → Create OAuth client ID → Application type = "Desktop app" → ได้ Client ID + Secret
  4) รันคำสั่งนี้:
       python manage.py gdrive_auth --client-id <ID> --client-secret <SECRET>
     (หรือ set GDRIVE_CLIENT_ID/GDRIVE_CLIENT_SECRET ใน .env แล้วรันเปล่า ๆ)
  5) เบราว์เซอร์เปิดหน้า Google → ล็อกอินด้วย oxletauto@gmail.com → อนุญาต
  6) คำสั่งจะพิมพ์ GDRIVE_REFRESH_TOKEN → เอาไปใส่ใน .env บน VPS
"""
import http.server
import json
import socket
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

SCOPE = "https://www.googleapis.com/auth/drive.file"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"


class _Catcher(http.server.BaseHTTPRequestHandler):
    code = None

    def do_GET(self):
        q = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(q)
        _Catcher.code = (params.get("code") or [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        msg = "สำเร็จ! กลับไปที่หน้าต่างคำสั่งได้เลย ปิดแท็บนี้ได้" if _Catcher.code else "ไม่พบ code"
        self.wfile.write(f"<h2>{msg}</h2>".encode("utf-8"))

    def log_message(self, *a):
        pass  # เงียบ


class Command(BaseCommand):
    help = "ขอ Google Drive refresh token (OAuth loopback) — รันบนเครื่องที่มีเบราว์เซอร์"

    def add_arguments(self, parser):
        parser.add_argument("--client-id", default=getattr(settings, "GDRIVE_CLIENT_ID", ""))
        parser.add_argument("--client-secret", default=getattr(settings, "GDRIVE_CLIENT_SECRET", ""))
        parser.add_argument("--port", type=int, default=8765)

    def handle(self, *args, **opts):
        try:  # กัน UnicodeEncodeError ตอนพิมพ์ ✓/ไทย บน console cp874 (Windows ไทย)
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass
        cid, secret, port = opts["client_id"], opts["client_secret"], opts["port"]
        if not (cid and secret):
            raise CommandError("ต้องมี --client-id และ --client-secret (หรือ GDRIVE_CLIENT_ID/SECRET ใน .env)")

        redirect_uri = f"http://127.0.0.1:{port}"
        auth = AUTH_URL + "?" + urllib.parse.urlencode({
            "client_id": cid,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPE,
            "access_type": "offline",
            "prompt": "consent",
        })

        try:
            httpd = http.server.HTTPServer(("127.0.0.1", port), _Catcher)
        except socket.error as e:
            raise CommandError(f"เปิดพอร์ต {port} ไม่ได้ ({e}) — ลอง --port อื่น")

        self.stdout.write(self.style.NOTICE("เปิดเบราว์เซอร์เพื่ออนุญาต... ถ้าไม่เด้ง เปิดลิงก์นี้เอง:\n" + auth + "\n"))
        threading.Thread(target=lambda: webbrowser.open(auth), daemon=True).start()
        httpd.handle_request()  # รอ redirect กลับมา 1 ครั้ง
        httpd.server_close()

        code = _Catcher.code
        if not code:
            raise CommandError("ไม่ได้รับ authorization code")

        data = urllib.parse.urlencode({
            "code": code, "client_id": cid, "client_secret": secret,
            "redirect_uri": redirect_uri, "grant_type": "authorization_code",
        }).encode()
        try:
            with urllib.request.urlopen(urllib.request.Request(TOKEN_URL, data=data)) as r:
                tok = json.loads(r.read().decode())
        except Exception as e:
            raise CommandError(f"แลก token ไม่สำเร็จ: {e}")

        refresh = tok.get("refresh_token")
        if not refresh:
            raise CommandError("ไม่ได้ refresh_token (ลองถอดสิทธิ์แอปที่ myaccount.google.com/permissions "
                               "แล้วรันใหม่ · ต้องมี access_type=offline + prompt=consent)")

        self.stdout.write(self.style.SUCCESS("\n✓ สำเร็จ! ใส่ค่านี้ใน .env บน VPS:\n"))
        self.stdout.write(f"GDRIVE_CLIENT_ID={cid}")
        self.stdout.write(f"GDRIVE_CLIENT_SECRET={secret}")
        self.stdout.write(f"GDRIVE_REFRESH_TOKEN={refresh}")
        self.stdout.write(self.style.NOTICE("\nจากนั้นรัน `python manage.py gdrive_setup` เพื่อสร้างโฟลเดอร์หลัก (ออปชั่น)"))
