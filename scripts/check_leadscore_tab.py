"""เช็คชื่อ tab ใน spreadsheet '1HOhrPSI...' (employees + ตั้งค่าเซลล์ + leadscore ใหม่)"""
import os, sys, requests, django
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
django.setup()

from dashboard.services.google_sheets import _get_credentials
from google.auth.transport.requests import Request as AuthRequest

SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
SID = "1HOhrPSIFTxfOpc4UWvKb-LfMuXGYW2vYkR5vbGzPd_A"

creds = _get_credentials()
creds.refresh(AuthRequest())
headers = {"Authorization": f"Bearer {creds.token}"}

# ดึง metadata ทั้งหมด
r = requests.get(
    f"{SHEETS_API}/{SID}?fields=sheets.properties(sheetId,title,index)",
    headers=headers, timeout=15,
)
data = r.json()
sheets = data.get("sheets", [])
print(f"\n=== Tabs ใน spreadsheet {SID} ===\n")
print(f"{'index':>6} {'sheetId':>12} {'title'}")
print("-" * 60)
for s in sheets:
    p = s["properties"]
    title = p.get("title", "?")
    sid = p.get("sheetId", "?")
    idx = p.get("index", "?")
    marker = "  ← gid ที่ user สร้าง (336741110)" if str(sid) == "336741110" else ""
    print(f"{idx:>6} {sid:>12} {title}{marker}")
