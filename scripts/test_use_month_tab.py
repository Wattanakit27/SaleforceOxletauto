"""ทดสอบใช้ tab "พฤษภาคม 69" โดยตรง — น่าจะตรงกับเลข 2,582"""
import os, sys, django, urllib.parse, requests
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "oxlet.settings")
django.setup()

from dashboard.services.google_sheets import (
    SHEET_CONFIG, _get_credentials, _dedupe_leads_by_code, cell, LEADS_COL as L,
)
from google.auth.transport.requests import Request as AuthRequest
from dashboard.services.fetch_dashboard import parse_date, bangkok_now
from dashboard.services.constants import normalize_seller

SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
now = bangkok_now()

creds = _get_credentials(); creds.refresh(AuthRequest())
headers = {"Authorization": f"Bearer {creds.token}"}
sid = SHEET_CONFIG["leads"]["spreadsheet_id"]

encoded = urllib.parse.quote(f"'พฤษภาคม 69'")
tab_rows = requests.get(
    f"{SHEETS_API}/{sid}/values/{encoded}?valueRenderOption=FORMATTED_VALUE",
    headers=headers, timeout=30,
).json().get("values", [])[1:]
print(f"\ntab 'พฤษภาคม 69' raw rows = {len(tab_rows)}")

# Filter by date = May
filtered = [r for r in tab_rows if (d := parse_date(cell(r, L.received_date))) and d.year == 2026 and d.month == 5]
print(f"filter date=พ.ค.        = {len(filtered)}")

# Dedup
deduped = _dedupe_leads_by_code(filtered)
print(f"หลัง dedup             = {len(deduped)}  ← user คาด ~2582")

# Per-seller
print(f"\nPer-seller:")
c = Counter()
for r in deduped:
    s = normalize_seller(cell(r, L.sales_rep)) or "(ว่าง)"
    c[s] += 1
for s, n in c.most_common():
    print(f"  {s:<14} {n}")
print(f"  รวม          = {sum(c.values())}")
