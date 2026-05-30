"""One-off: inspect 'รายงานแบน' tab structure (read-only)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
django.setup()

import urllib.parse
import requests
from google.auth.transport.requests import Request as AuthRequest
from dashboard.services.google_sheets import _get_credentials, SHEETS_API

SID = "18Djos3lUJnoZ00gYEBuCCExwm1YknfIQrP-TIuUgjWU"
TAB = "รายงานแบน"

creds = _get_credentials()
creds.refresh(AuthRequest())
enc = urllib.parse.quote(f"'{TAB}'")
url = f"{SHEETS_API}/{SID}/values/{enc}?valueRenderOption=FORMATTED_VALUE"
r = requests.get(url, headers={"Authorization": f"Bearer {creds.token}"}, timeout=30)
print("STATUS", r.status_code)
if r.status_code != 200:
    print(r.text[:500])
    raise SystemExit(1)

rows = r.json().get("values", [])
print("TOTAL ROWS:", len(rows))
print("=" * 60)
for i, row in enumerate(rows[:15]):
    print(f"[{i}] ({len(row)} cols)", row)
