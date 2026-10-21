# Oxlet Auto in-house CRM ("Connect" + Sales Dashboard): current state as of 12 Oct 2026 (12 ต.ค.69)

> **Source convention.** Every source is a file in the repo. Paths are relative to `C:\Users\watta\SaleforceOxletauto\`. `CLAUDE.md Lnnn` means the line number in CLAUDE.md, which is the ~4,760-line developer log and the main spec. Thai dates use the Buddhist year: "69" = 2026, so "ต.ค.69" = Oct 2026. Items marked **(inference)** are my reading and are not stated in the sources.
>
> **Doc-drift warning.** README.md and the opening "ภาพรวม" section of CLAUDE.md are stale. They describe "Vercel, no local DB, Sheets only" ([README.md L1-5, L64](README.md); [CLAUDE.md L5-11](CLAUDE.md)). The real deployment is a Hostinger VPS (`srv1793506.hstgr.cloud`) running Postgres, gunicorn (5 workers) and nginx ([CLAUDE.md L560-568, L1487-1488, L3135](CLAUDE.md)). The report writer should rely on the dated sections of CLAUDE.md and on the code.

---

## Q1. Which channels feed the CRM, and how are messages captured?

### Takeaway
LINE OA 1:1 chat is the primary live channel. It enters through webhooks forwarded by n8n. Facebook Messenger (2 pages) shares the same queue, but it arrives by API polling every 2 minutes, because the real-time webhook is blocked until Meta finishes App Review and business verification. TikTok has no chat API access. TikTok leads, and leads from phone or other sources, come in as text "draft slips" that admins post in a LINE group. LINE *groups* are also used as the operational backbone (lead dispatch, reports, purchasing). Google Sheets is still the source of truth for leads and sales.

### Cited Findings
- **Two LINE OA accounts with split roles.** "OxletAuto" (key `crm`, @zpb0787e) only *receives*: customer chats, chat/profile storage and the webhook. "OxletautoGiveLead" (key `push`, @693tyhah) *sends* everything: group posts and 1:1 DMs to staff. The owner decided this on 20 Sep 2026 — [CLAUDE.md L2753-2770, L2852-2862](CLAUDE.md)
- The two OAs sit under **different LINE Providers**. LINE user IDs are issued per provider, so the same person gets different IDs on each bot and the system cannot merge them. The owner decided "do not rebuild" because @693tyhah receives no customer 1:1 chats — [CLAUDE.md L2788-2797, L2907-2922](CLAUDE.md)
- Any number of extra LINE OA accounts can be added through env vars (`LINE_OA_<KEY>_TOKEN/_SECRET/_NAME`) without code changes — [CLAUDE.md L2896-2906](CLAUDE.md)
- **Single ingress rule.** The owner's instruction is that LINE data comes "from n8n only". n8n forwards the raw LINE webhook body to `/api/line/group_ingest` (auth: `CRON_SECRET`). A direct `/api/line/webhook` also exists. Any new account must come through the same n8n path — [CLAUDE.md L2923-2925; L4090-4140 (checkout ingest)](CLAUDE.md)
- Every LINE message, group or 1:1, is stored in `GroupChat` (`chat_type` = group/user/room, with `direction` in/out). Customer 1:1 chat retention is **60 days**. Group chat retention is **90 days** — [CLAUDE.md L4140-4160](CLAUDE.md); [checkout/models.py L229](checkout/models.py)
- Outbound replies sent from Connect are stored as `direction=out` with `sent_by`, so both sides of the conversation are kept (the stated intent is to later train an in-house chatbot) — [CLAUDE.md L1320-1349](CLAUDE.md); [checkout/chat.py](checkout/chat.py)
- **Facebook Messenger is in the same queue as LINE** (owner chose "รวมคิวเดียวกับ LINE", 4 Oct). `ChatOwner` has `profile` (LINE) *or* `fb_profile` (FB) — [CLAUDE.md L1843-1893](CLAUDE.md); [checkout/models.py L840-848](checkout/models.py)
- FB capture paths:
  - **(a)** Messenger webhook `/api/meta/webhook` (HMAC `X-Hub-Signature-256`; returns 503 if no app secret). Receiving real customers needs **Advanced Access for `pages_messaging` = App Review + Business Verification**, which is **not yet granted**.
  - **(b)** Fallback polling `fb_sync.sync_live()` every `fb_poll_min` = **2 min** (configurable 2–60). Measured Meta usage was 1% of quota.
  - **(c)** Nightly full sync.
  - Sources: [CLAUDE.md L1850-1872](CLAUDE.md); [checkout/connect.py L71-76](checkout/connect.py); [deploy/meta_business_verification.md L1-5](deploy/meta_business_verification.md); [deploy/meta_webhook.md](deploy/meta_webhook.md)
- FB page replies typed in the Facebook/Business Suite app *do* come back (echo) and stop the SLA clock. Page auto-replies sent within 15 s are not counted as replies (`FB_AUTO_SEC`) — [CLAUDE.md L1873-1882](CLAUDE.md)
- FB data at 29 Sep: ≥8,200 threads and ≥115,000 messages on Facebook. Per-page PSIDs (the same person on 2 pages = 2 rows) — [checkout/fb_sync.py L11](checkout/fb_sync.py); [CLAUDE.md L3097-3103](CLAUDE.md)
- **TikTok has no DM or comment access.** The connected app is Login Kit (profile stats and video views for 10+ channels). The owner chose to apply for TikTok API for Business / Business Messaging API. That requires a DSPR security review (2–4 weeks; needs written security policies, a privacy notice, MFA, pentest reports and so on). None of these exist yet — [deploy/tiktok_business_api.md L1-45](deploy/tiktok_business_api.md); [CLAUDE.md L1892-1893, L3131-3184](CLAUDE.md)
- **Instagram:** the FB pages are not linked to an IG Professional account, so there is no IG data — [CLAUDE.md L3012-3018](CLAUDE.md)
- **TikTok, phone and other leads enter by hand.** Admins post a "draft lead slip" (lead prefix + month but no running number, no @seller) in the LINE group **"ADMIN เก็บ Lead"**. The system parses it (`leadpark.parse_draft`). Over 30 days of real messages: 2,317 slips, 0 unreadable — [checkout/leadpark.py L1-31](checkout/leadpark.py); [CLAUDE.md L1756-1790](CLAUDE.md)
- **Google Sheets remains the system of record** for leads ("leads" sheet, one tab per month, ~26 columns), sales/bookings, live sessions, employees and config. There are 7+ sheets — [CLAUDE.md L529-559](CLAUDE.md)
- **LINE groups as workflow channels.** Examples: "ห้องจ่ายเบอร์ บ้านเก่า" (lead dispatch), "ห้องจ่ายเบอร์ REJECT", "ADMIN เก็บ Lead", "เคสHOT (พี่หมี/พี่ต๊าด)" and "เคสVERY HOT" (car buy-in leads), "Sale Coaching Room", and check-in groups. On 28 Sep: 16 groups, 17,034 messages, now registered as `LineGroup` with a `kind` taxonomy of 12 types — [CLAUDE.md L2633-2689](CLAUDE.md)
- **Media:** customer images and files on LINE and FB are downloaded to a private disk folder outside `/media/` and served only via an ACL-checked endpoint. LINE expires files after an unknown number of days — [CLAUDE.md L2130-2168](CLAUDE.md); [checkout/chatmedia.py](checkout/chatmedia.py)
- Scale of stored chat: 28 Sep — LINE 17,029 + FB 45,494 = 62,523 messages. 29 Sep — 75,744 (LINE 19,224 + FB 56,520) — [CLAUDE.md L1218, L2575](CLAUDE.md)

### Inferences
- **(inference)** "Omnichannel" here really means LINE + FB inbox, plus manual intake via LINE groups. The system has no email, SMS, web-form or call-center (telephony) integration; I found no code for them.
- **(inference)** LINE groups act as the "task bus" between admins and sellers. Many CRM actions (dispatch, reports, purchasing tickets) are parsed out of chat text, not entered in structured forms.

### Gaps
- I found no website lead form or showroom-site → CRM lead capture. The showroom sync is one-way, stock → website ([CLAUDE.md L4650-4664](CLAUDE.md)).
- No documentation of the LINE OA monthly message-quota plan, or of actual monthly push volume.

---

## Q2. What is the lead lifecycle (capture → parking → dispatch → stages → follow-up)?

### Takeaway
A multi-step pipeline grown on top of LINE groups:
1. A chat arrives and joins the queue, with a 5-minute reply clock.
2. Contact details and profile are extracted automatically.
3. An admin moves the lead into the **parking room (ห้องพัก Lead)**.
4. An admin **dispatches** it (จ่ายเบอร์). The system issues a lead code, posts a slip into the LINE dispatch group and @mentions the seller.
5. A 15-minute "call clock" waits for the seller's text report in the group.
6. The lead moves through CRM stages, appointments and call logs.
7. Booking and finance status comes from the sales Google Sheet.

Rejected leads get a "second stick" (ไม้ 2) re-dispatch.

### Cited Findings
- **Capture.** An inbound 1:1 message calls `note_customer_message` / `note_fb_batch`. This creates or updates a `ChatOwner` (1 row per customer) and opens an "awaiting" round (`awaiting_since`, `due_at`) — [checkout/connect.py L1-23](checkout/connect.py); [CLAUDE.md L1366-1367](CLAUDE.md)
- **Automatic enrichment on every message:**
  - `capture_contact` extracts phone numbers (7 formats). It takes a LINE ID only when labelled, or when sent as the next message after we asked for it.
  - LINE add-friend links and **LINE QR images** (decoded locally with zxing-cpp) count as a LINE ID.
  - `capture_profile` runs the keyword extractor.
  - `apply_deal_kind` classifies buy-vs-sell.
  - Sources: [CLAUDE.md L1700-1712, L2169-2196, L2266-2310](CLAUDE.md)
- **Queue:** unowned rows sit in "รอรับ" (waiting for pickup). On-duty team sellers see a preview (≤10 customer messages, no contact data) and can claim — [CLAUDE.md L1384-1389](CLAUDE.md)
- **Parking room (ห้องพัก Lead), the central dispatch hub for all channels.** Sources:
  - (a) Drafts from the "ADMIN เก็บ Lead" group (enter automatically).
  - (b) Chats an admin ticked as "รับ lead จากแชทนี้แล้ว" (since 11 Oct, `room_chat_auto=False` by default; earlier, any chat with a phone or LINE ID entered automatically).
  - (c) A highlighted orange group, "ให้เบอร์แล้ว · รอรับ lead": chats with a phone or LINE ID within 3 days that are waiting for an admin click.
  - (d) A separate "รับซื้อรถ" (buy-in) tab.
  - Sources: [CLAUDE.md L1700-1755, L2220-2265](CLAUDE.md); [checkout/connect.py L89-92](checkout/connect.py)
- **Dispatch (จ่ายเบอร์).** The admin clicks a seller name.
  - The system issues lead code `<prefix><month>-<running>`, e.g. `NLD10-8409`. Prefixes: NLD = Moderate, WLD = Hot, HLD = Very Hot, BLD, TLD = TikTok, TALD = TikTokAds. A = admin's own lead, R = reject case.
  - The running number is shared across prefixes and derived from the max of the last 20 slips. It is protected by a Postgres advisory lock (`code_lock`).
  - The slip is posted into "ห้องจ่ายเบอร์ บ้านเก่า" (or REJECT for R codes) with a real LINE @mention of the seller (`slip_post` on since 6 Oct). The admin is asked to confirm before each post.
  - Sources: [CLAUDE.md L1614-1700](CLAUDE.md); [checkout/models.py L987-993](checkout/models.py)
- **Duplicate check:** the `LeadPhone` "phonebook" is built from the leads sheet every 6 h, plus slips and system dispatches. The dispatch box warns "this number was lead X of @Y" and offers "give to previous owner" — [CLAUDE.md L1903-1936](CLAUDE.md); [checkout/models.py L1063-1087](checkout/models.py)
- **Round-robin queue (คิวจ่ายวน)** in `leadflow_config`:
  - Teams A, B, C. `cap_day` = 12 slips per person per day. Skips day-off people, test accounts and (optionally) people who have not checked in.
  - Ordered by fewest slips today. "Today" counts the time the slip reached the group (fixed 11 Oct after a bug pushed sellers out of the queue).
  - Sources: [checkout/leadflow.py L52-69](checkout/leadflow.py); [CLAUDE.md L1947-1958](CLAUDE.md)
- **Run Auto** lives only in the parking room, not in the chat page.
  - It produces a *plan* first (`crm.room_plan`), with no writes. Rules: existing chat owner keeps the lead → previous owner via phonebook (if they left, skip and let the admin choose) → otherwise round-robin. Max 30 per round.
  - The admin unticks items, then the browser calls the normal dispatch endpoints one by one.
  - Sources: [checkout/crm.py L625-716](checkout/crm.py); [CLAUDE.md L2032-2045](CLAUDE.md)
- `auto_assign` (dispatch parked drafts automatically after N min) and `auto_pull` (re-dispatch overdue or "pass" slips) both exist but are **off by default**. Chat leads (LINE/FB) are never auto-dispatched — [checkout/leadflow.py L52-69](checkout/leadflow.py); [CLAUDE.md L1959-1962](CLAUDE.md)
- **Call clock (นาฬิกาโทร).**
  - `LeadTask`, one row per slip, from system dispatch *or* slips admins posted by hand.
  - The seller must report within `call_min` = **15 min** of business hours.
  - The clock stops when the seller posts "running number + result" in the group (e.g. "9075 รอตอบครับ"; messages containing @ are ignored as admin nagging), or replies via Connect.
  - "The system cannot know whether the seller actually called."
  - Sources: [checkout/leadflow.py L1-31](checkout/leadflow.py); [checkout/models.py L1090-1137](checkout/models.py)
- **Seller report parsing** (no AI) produces customer status, occupation, income, tenure, payment history and appointment date/time.
  - Reports with real data can trigger a confirmation card in the seller's DM. "ถูกต้อง" writes to the leads sheet, only for rows owned by that seller.
  - LINE button cards for รับเคส / ขอผ่าน / โทร can be appended to the slip push (HMAC-signed postbacks; reply token = free).
  - **All of these sending features are off by default.**
  - Volume: ~1,189 report messages per week.
  - Sources: [CLAUDE.md L1914-1946](CLAUDE.md); [checkout/models.py L1140-1175](checkout/models.py)
- **"Second stick" (ไม้ 2):** re-dispatch to the REJECT room as `R` + original code + `/1` (prod: 1,075 of 1,077 forwards; /2 never seen) — [CLAUDE.md L1916-1919, L1963-1964](CLAUDE.md)
- **CRM stages** (added 11 Oct, `crm.STAGES`): new → waiting → contacted → viewing → finance → won / lost, plus "pool" (returned to the shared pool).
  - Blank means system-computed: no owner = new; owner but no reply = waiting; replied = contacted.
  - Stages advance automatically, forward only: a "talked" call log moves the lead to contacted, a viewing appointment moves it to viewing.
  - "Lost" requires one of 8 reasons (down payment insufficient, credit/bureau fail, price too high, no matching car, bought elsewhere, ghosted, not ready, other).
  - Stage is separate from sheet column Z "customer status" (the customer's attitude).
  - Sources: [checkout/crm.py L1-17, L36-142](checkout/crm.py); [CLAUDE.md L2014-2024](CLAUDE.md)
- **Appointments** (`ChatFollowup`: follow-up or car viewing) and **call logs** (`ChatCall`: talked / no answer / off / wrong number / call back / other, plus up to 6 proof screenshots, 10 MB each, on VPS disk) — [checkout/models.py L1177-1234](checkout/models.py); [checkout/crm.py L301-370](checkout/crm.py)
- **Booking, finance and won** status is not tracked in Connect. `crm.booking_of(code)` looks up the lead code in the precomputed sales-sheet dashboard cache (statuses จอง / รอเซ็นต์ / รอผล / รอปล่อย / ปล่อย / รีเจ็ก) — [checkout/crm.py L423-470](checkout/crm.py); [CLAUDE.md L258-265](CLAUDE.md)
- **Leads dispatched directly in the sheet** (outside the system) are auto-cleared from the parking room via `sheet_match` (phonebook hit within 14 days). Prod evidence 11 Oct: 35 of 72 waiting leads with phones already had sheet codes — [CLAUDE.md L2197-2219](CLAUDE.md)
- **Legacy sheet-based follow-up layer, still in production:**
  - Sheet column Z "สถานะลูกค้า" with 16–24 dropdown values and priorities.
  - "ตามด่วน" (follow-up urgency) ranking uses: not called (+120), hot × idle days, status priority, idle; plus per-status cadence and a "no answer > 5 times → rest" rule.
  - Plain-text LINE DMs to each seller at 09:00 and 13:00, scheduled from sheet "ตั้งเวลาส่ง", over a 14-day rolling window.
  - Sources: [CLAUDE.md L266-292, L324-333](CLAUDE.md)
- **Retention:** chats, Connect rows and lead data cascade-delete when the customer is silent for 60 days (PDPA) — [checkout/models.py L836-837, L941](checkout/models.py); [CLAUDE.md L2098](CLAUDE.md)

### Inferences
- **(inference)** There are two parallel pipelines that are not unified: (1) Connect stages in Postgres and (2) the sheet-based lead row (column Z, update count, call proof), which feeds dashboards and scorecards. Connect lead data is not written back to the sheet (see Q8), so a lead can have different states in each place.
- **(inference)** The dispatch model is "push to a named seller with an SLA clock" (round-robin plus duplicate ownership), similar to lead-routing modules in Salesforce or HubSpot. But it is driven by LINE group posts, not in-app task assignment.

### Gaps
- No documented definition of when a Connect "won" stage should sync with the sales-sheet "ปล่อย" (released) status. They appear independent.
- No measured conversion funnel from chat to won is reported. The team dashboard has a funnel view, but no numbers are quoted in the docs.

---

## Q3. What are the routing and ownership rules (shifts, claim, SLA, hours, escalation, pull-back, transfer)?

### Takeaway
Ownership is first-claim-wins, with a DB-level lock, alternating-day team shifts (A/B), sticky ownership, and a 5-minute business-hours reply SLA. Most automated escalations and pull-backs are built but switched off. The reason: the team still answers in the LINE OA Manager app, which LINE does not mirror back, so SLA signals are unreliable.

### Cited Findings
- **Shift rotation:** alternating days computed from `anchor_date` (2026-10-01) + `anchor_team` (A). Teams list `["A","B"]`; more teams rotate automatically. Per-day overrides are possible. The day cuts at midnight Bangkok time, weekends included — [checkout/connect.py L41-48](checkout/connect.py); [CLAUDE.md L1368-1370](CLAUDE.md)
- **Claim lock:** `UPDATE … WHERE owner IS NULL`. Only one of two simultaneous clickers wins. Sellers can claim only on their team's duty day and only customers currently waiting. Admins can claim or assign any day — [checkout/connect.py L12-13](checkout/connect.py); [CLAUDE.md L1370-1371](CLAUDE.md)
- **Sticky ownership:** the customer stays with the same seller whatever team is on duty, except when an admin transfers them or the seller is deactivated (`Employee.active=False`; the customer returns to the queue on their next message) — [CLAUDE.md L1372-1373](CLAUDE.md)
- **SLA:** `sla_min` = 5. The clock stops only on an actual reply ("claiming does not stop it"). Rapid messages from the customer keep the same deadline. Applies to every message, including from owned customers. "No reply needed" button closes the round (thanks / stickers) — [checkout/connect.py L49-53](checkout/connect.py); [CLAUDE.md L1374-1375](CLAUDE.md)
- **Business hours:** 08:30–20:00 by default (open = close means 24 h). Messages after hours start the clock at opening — [checkout/connect.py L51-53](checkout/connect.py); [CLAUDE.md L1376-1377](CLAUDE.md)
- **Escalation:**
  - Overdue rows show red in Connect.
  - The cron flags `escalated_at` once per round.
  - LINE alert to the admin group (`alert_on`) and LINE notify-sellers-on-new-message (`notify_sellers`) are both **off by default**: quota cost of ~9 sellers × every new customer, and the owner said "don't send anything out yet".
  - The admin "overdue" tab was **removed on 7 Oct** because 102 already-answered chats showed as overdue.
  - Sources: [CLAUDE.md L1378-1385](CLAUDE.md); [checkout/connect.py L54-59](checkout/connect.py)
- **Pull-back:** `pull_min` (0 = off by default) returns claimed-but-unanswered chats to the queue. It is explicitly warned not to be enabled while staff reply in LINE OA Manager — [checkout/connect.py L83-86](checkout/connect.py); [checkout/crm.py L998-1014](checkout/crm.py)
- **Transfer and release:** admins transfer or return to the queue. Sellers can "คืนกองกลาง" (return to pool) with a reason, logged in `ChatOwnerLog` — [checkout/crm.py L719-722](checkout/crm.py); [checkout/models.py L890-925](checkout/models.py)
- **Visibility:**
  - Admins see all chats.
  - Owners see full history.
  - Queue preview shows only the customer's messages since the round started (≤10). Phone, needs and status are not sent from the server until claimed.
  - Others get 403. Checks are server-side.
  - Sellers without an employee-registry record are blocked.
  - Sources: [CLAUDE.md L1384-1389, L1404](CLAUDE.md)
- **Facebook customers assigned to sellers are "data only".** Sellers can view and fill lead data but **cannot reply** or close rounds (403 `FB_DATA_ONLY`). Admins can reply under the `fb_reply` mode (default `test` = only designated test threads). This changed from the 4 Oct plan — [CLAUDE.md L1683-1684](CLAUDE.md); [checkout/connect.py L63-66](checkout/connect.py)
- **Who is in rotation** (measured): Team A = 3 sellers; Team B = 5–6. **Team C (3 people) and telesales are not in the rotation**, so they cannot claim new customers themselves; admins must transfer — [CLAUDE.md L2104-2108](CLAUDE.md)
- **Unread state** is team-shared ("like LINE OA"), not per user. Reading in LINE OA Manager does not count — [CLAUDE.md L1436-1449](CLAUDE.md)
- **Test mode:** simulated sellers and customers (`TEST-` IDs that never hit LINE), plus a real "test account" (`Wattanakit`). Switching to impersonate a real seller is blocked — [CLAUDE.md L1406-1428](CLAUDE.md)

### Inferences
- **(inference)** The rules mirror a classic "round-robin + claim + SLA" contact-center design. The key weakness is not the logic but data completeness: replies outside the system make SLA, unread and pull-back metrics untrustworthy.

### Gaps
- No skills- or language-based routing, no workload-weighted routing beyond the daily cap, and no VIP/priority queue were found.
- No SLA for internal follow-up beyond the 15-minute call clock and appointment reminders.

---

## Q4. What data is captured per customer (data model)?

### Takeaway
Each customer has a `ChatOwner` row (ownership plus SLA state) linked to a LINE or FB profile, a `ChatLead` row that mirrors the 26-column Google Sheet lead row plus CRM fields, and child tables for appointments, calls and history. A deterministic, non-AI keyword engine fills occupation, income, tenure, payment history, customer type, status, car interest and buy-vs-sell, with provenance recorded per field.

### Cited Findings
- **`LineProfile`**: user_id, display name, status message, language, nickname (if employee), `is_employee`, message count, first/last seen, `channel(s)`. Profile pictures are *not* stored here (PDPA minimisation) — [checkout/models.py L309](checkout/models.py); [CLAUDE.md L4160-4175](CLAUDE.md)
- **`FbProfile` / `FbChat`**: a parallel FB schema with identical column names where the meaning matches. Unique per (page, PSID) — [CLAUDE.md L3085-3119](CLAUDE.md); [checkout/models.py L627-731](checkout/models.py)
- **`ChatOwner`** (1 per customer): owner (Employee), team, claimed_at, first_reply_at, awaiting_since, due_at, escalated_at, last in/out/at, last preview/direction, `read_at` (team-shared unread), LINE picture URL (stored here deliberately so employee pictures are never stored; refreshed every 7 days) — [checkout/models.py L823-888](checkout/models.py)
- **`ChatOwnerLog`**: events claim / assign / release / escalate / reply / dismiss / stage / appt / call / summary, with `wait_sec` and `on_time`. This is the source of per-seller response-time statistics — [checkout/models.py L890-925](checkout/models.py)
- **`ChatLead`** (1 per customer): mirrors the leads sheet.
  - Lead fields: code, type, ADS, account, channel, branch, live team, admin, focus, car text, car model (formula), call proof, fill note, admin profile.
  - Profile: name, LINE ID, phone, occupation, income, job tenure, payment history, customer type, customer status (column Z).
  - Slip fields: live, more, tags.
  - CRM: stage, stage_at/by, lost_reason, summary, summary_at/by.
  - Dispatch: assigned_at/by, code_demo, post_info.
  - `auto` JSON = which fields the system filled and from where (แชท / ใบจ่ายลีด / ระบบ / ชีตลีด). Human-edited fields are marked `คน` and are never overwritten.
  - Derived fields (first contact, contact time, update count, last update) are computed, not stored.
  - Sources: [checkout/models.py L928-1005](checkout/models.py)
- **`ExtLead`** (parked external leads: TikTok/FB/other), **`LeadPhone`** (phonebook), **`LeadTask`** (call clock), **`LeadReport`** (seller text reports, parsed fields, appointment), **`ChatFollowup`**, **`ChatCall`** — [checkout/models.py L1008-1234](checkout/models.py)
- **`CustomerNeed`**: 1 row per *need* (model, year, budget min/max, monthly installment, down payment, status new / lead / booked / won / rj, evidence). `reject_kind` + `waiting=True` turn "rejected because of price or no stock" into a standing order to match against incoming stock. Sources: chat (Gemini extraction) or the dispatch-group slip (regex). Stock matching (`need_match.py`) looks at ready-to-sell cars within +5% of budget and requires a model match, not just brand — [CLAUDE.md L2347-2414](CLAUDE.md)
- **Keyword engine `lead_keywords.py`** ("no AI, deterministic, auditable which word matched").
  - Extracts occupation, customer type, monthly income (must be preceded by an income word; installments, down payments and budgets are excluded), job tenure, payment/credit history, and customer status (latest message wins).
  - Handles Thai without spaces (word-boundary guards), negation, relatives' and past occupations.
  - Accuracy against ~1,150 real October sheet notes: income 96%, tenure 96%, occupation 85%, customer type 83%. Customer status matched the sheet only 15%, a different concept (call outcome vs. what the customer said).
  - Sources: [checkout/lead_keywords.py L1-22](checkout/lead_keywords.py); [CLAUDE.md L1574-1613](CLAUDE.md)
- **Car interest:** `car_in`/`brand_in` map Thai and English model names to the sheet's "CAR/สูตร" dropdown. Ambiguous models (City 4 vs 5 doors, Civic FC/FE/FK) are left as "ไม่ระบุรุ่นรถ" (model not specified) rather than guessed. Data basis: for "city", admins chose 5-door 37% and 4-door 20% — [CLAUDE.md L1546-1573, L1608-1613](CLAUDE.md)
- **Dropdown sync:** the lead form uses the *same* dropdown options as the live Google Sheet month tab (data validation, read hourly into KV). Branch and channel defaults come from real distributions (LINE leads written `LINE@` in 740 of 741 cases) — [CLAUDE.md L1531-1545](CLAUDE.md)
- **Buy-lead vs sell-lead:**
  - `deal_kind` (rule-based) separates customers *selling* a car to the dealer (purchasing team, "OC-/SC-" tickets in the "เคสHOT" groups) from buyers.
  - Trade-ins remain sell leads with a "มีรถเทิร์น" (has trade-in) tag.
  - Measured: 19 of 21 buy leads detected; 3 of 178 sell leads misclassified.
  - Staff phrases ("ฝ่ายจัดซื้อ", "หน้า 4 และ 18") classify instantly on FB.
  - Sources: [CLAUDE.md L2266-2310](CLAUDE.md)
- **Highlights and provenance UI** (12 Oct): extracted words are highlighted in chat bubbles by category. Each auto-filled field shows "จากแชท 14:02" and links to the source message. A "readiness" box (e.g. 3 of 5 fields ready to dispatch). **Pending suggestions** when a customer later states a new value (occupation, income, tenure, new phone, specific model), with use / keep / dismiss options — [CLAUDE.md L2311-2346](CLAUDE.md)
- **Heat score** (`heat_of`, 0–100; hot ≥60, warm ≥35, cold).
  - Inputs: lead type (Very Hot 40 … RJ 6), column-Z status (dead words → cold), stage (viewing +20, finance +25), recency (≤1 day +20 … >14 days −25), has contact +8, awaiting +5.
  - Returns reasons. No extra input fields.
  - Sources: [checkout/crm.py L144-220](checkout/crm.py)
- **Legacy "Lead Score"** (sheet leads, `compute_lead_score`): freshness, type, channel (Walk-in +15, TikTok +10, FB +5), engagement. Tiers hot ≥55 / warm ≥35 / cold. Distribution ~3% / 30% / 67% — [CLAUDE.md L406-412](CLAUDE.md)

### Inferences
- **(inference)** The data model is dealership-specific (car model formula, down payment and installment, credit bureau, trade-in, finance stage). This is a strength compared with a generic CRM, but it lives half in Postgres and half in Sheets.
- **(inference)** There is no unified "Contact" or "Account" entity across channels. A customer on LINE, FB and phone appears as separate rows linked only by phone or code matching.

### Gaps
- No consent or opt-in fields per customer (marketing consent, PDPA lawful basis) were found in the model.
- No customer lifetime record beyond 60 days of silence, so there is no repeat-buyer history in Connect.

---

## Q5. How is seller performance managed (scorecard, follow-up, reports, coaching)?

### Takeaway
Performance management is extensive but mostly sheet- and LINE-driven: a 100-point scorecard, a follow-up "urgency brain" pushed to sellers twice daily, LINE "nag" statistics, daily report images posted to LINE groups, response-time stats from Connect, a team dashboard, attendance check-ins and an archived senior↔junior coaching log.

### Cited Findings
- **Scorecard, 100 points:**
  - Released/closed 30 (target 15).
  - Bookings 10 (target 30).
  - Conversion 20 (5% release ÷ normal leads, RJ excluded).
  - Status velocity 10 (booking → sign ≤3 days, sign → result ≤3, result → release ≤1; Bayesian shrink k=1).
  - Follow-up diligence 20 (Σ min(updates, 4) / (4 × cases to follow)).
  - Bans 10 (10 − bans).
  - The leaderboard is visible to sellers.
  - Sources: [CLAUDE.md L293-310](CLAUDE.md)
- **Follow-up urgency ("ตามด่วน"):** combines not-yet-called, hot × idle, status priority and idle time, with per-status cadence (e.g. สนใจมาก 1 day, รอเงิน 3) and a "no answer > 5 → rest" rule. Plus a "stuck deals" list (booking/sign stuck >3 days, result >5, release >3). Sent as plain-text LINE DMs at 09:00 and 13:00, top N per seller, plus a team summary to admins — [CLAUDE.md L324-333](CLAUDE.md)
- **Nag statistics:** `FollowupLog` counts per seller per day how many rounds they were "nagged" for calls, status or deals; `SellerWeekly` holds weekly output. Lesson learned: a single nag metric saturates near 100% for everyone, so it was split three ways — [CLAUDE.md L334-344](CLAUDE.md)
- **Daily LINE report images:** a Playwright headless capture of dashboard tables (booking / approval / release per seller; per-team summary), sent to LINE groups with @All. Multiple groups per card, configurable time and date range. Repeated history of "silent failures" (2–3 days, 10 days, 3 days), now monitored on the system-health page — [CLAUDE.md L345-405, L1025-1043, L1094-1140](CLAUDE.md)
- **Connect team dashboard (แดชบอร์ดทีม):** slips today, % reported, % chats answered on time, released this month, chat → release funnel, per-seller table with the last 6 days, plus response-time stats from `ChatOwnerLog` — [CLAUDE.md L1984-1993 (table)](CLAUDE.md)
- **Insights:**
  - `crm.insights`: stage counts by channel, win rate, lost reasons, by ADS (ad), hot/warm/cold.
  - A downloadable "unwanted list" CSV (lost + dead statuses, with phone) for excluding people from ad audiences. Admin only, logged.
  - Sources: [checkout/crm.py L911-989](checkout/crm.py)
- **Coaching room:** the LINE group "Sale Coaching Room". 4 senior sellers (อุ้ม, เฟิร์ส, โอ๊ต, นวล). Messages archived permanently to `CoachLog` (Postgres) and the sheet tab "บันทึกโค้ช" (append-only, 1,695 rows Apr–Sep). The previous AI coaching chatbot was shut down by the owner, so currently "facts only, no AI". Limits: 91% of data is from Apr–May, 78% of senior comments come from one person, 70% of rows have no team — [CLAUDE.md L2415-2632](CLAUDE.md)
- **Attendance check-in:** photos in a LINE group are OCR'd by n8n into `CheckIn` in Postgres. Lateness uses each person's own start time. An escalation round at 10:00 tags absentees and managers. A table image is sent to LINE — [CLAUDE.md L743-987](CLAUDE.md)
- **AI seller coaching** (Gemini, on demand): strengths, weaknesses and a weekly plan per seller from filtered stats — [CLAUDE.md L515-521](CLAUDE.md)

### Inferences
- **(inference)** The performance system measures activity mainly from sheet data (update counts, call proof) and from LINE-group text. True activity capture (calls, replies) is incomplete because calls are made on personal phones and replies happen in LINE OA Manager.

### Gaps
- No commission/incentive calculation, quota management beyond targets, or gamification beyond the leaderboard.
- No QA scoring of chat replies (e.g. reply-quality review) despite storing both sides of conversations.

---

## Q6. Where is AI used, and what is explicitly non-AI?

### Takeaway
AI (Google Gemini over REST) is used narrowly and always with a human in the loop: chat summary drafts, document OCR for finance/loan forms, seller coaching and forecast narratives, need extraction from chat, and translation of Burmese/Khmer notes in car tracking. All lead routing, scoring and field extraction is deliberately rule-based for determinism and auditability. No customer-facing bot replies.

### Cited Findings
- **AI chat summary** (`crm.ai_draft`): Gemini drafts a summary, suggested stage and follow-up date. It is **never saved automatically**; the seller edits and clicks save. **Phone numbers and LINE IDs are masked before sending.** Cached 30 min. Hidden if there is no `GEMINI_API_KEY` — [checkout/crm.py L792-886](checkout/crm.py)
- **OCR** of finance/loan documents (Gemini vision; 27 and 59 fields; JSON schema mode; temperature 0; blank if not found) → draft form → LINE Flex to a *test* recipient only ("ช่วงทดสอบ", test phase) — [CLAUDE.md L522-528](CLAUDE.md)
- **Insights** (Gemini `gemini-2.5-flash`): seller coaching analysis and sales-forecast narrative, cached 30 min — [CLAUDE.md L515-521](CLAUDE.md)
- **Need extraction** from chat (`need_extract.py`, Gemini) via a manual command. A fingerprint avoids re-calling when there is no new message. Low-confidence results are flagged for human review. The cron job is not set up — [CLAUDE.md L2378-2414](CLAUDE.md)
- **Translation** of Burmese/Khmer worker notes to Thai in car tracking (Gemini flash, async, best-effort) — [CLAUDE.md L3799](CLAUDE.md)
- **Explicitly non-AI:**
  - `lead_keywords` ("ไม่ใช้ AI — ผลเหมือนเดิมทุกครั้ง ตรวจย้อนได้" — no AI, same result every time, auditable).
  - `deal_kind` buy/sell classifier.
  - Seller report parsing ("ระบบอ่านคำ (ไม่ใช้ AI)" — the system reads words, no AI).
  - Slip parsing (regex; 100% field capture on 600 real slips).
  - Heat and lead score, round-robin, duplicate checks.
  - QR decoding (zxing-cpp locally, so customer images are not sent to a third party).
  - Sources: [checkout/lead_keywords.py L5](checkout/lead_keywords.py); [checkout/models.py L1143](checkout/models.py); [CLAUDE.md L2275, L2378-2381, L2179-2181](CLAUDE.md)
- **AI vision on customer images** (car photos, registration books, ID-card screenshots) is explicitly *not* done: it would send customer images to Google. Pending an owner decision — [CLAUDE.md L2182-2183](CLAUDE.md)
- The **in-house chatbot** is an aspiration only. The stated reason for storing outbound replies is "so we can build our own chatbot later". The earlier coaching chatbot was turned off — [CLAUDE.md L1320-1327, L2413, L2416](CLAUDE.md)

### Inferences
- **(inference)** Compared with global CRMs that ship generative AI features (auto-reply, intent detection, lead-scoring ML), Oxlet's AI is assistive and opt-in. That is a conservative posture driven by PDPA concerns and the owner's "don't send anything to customers yet" instruction.

### Gaps
- No ML-based lead scoring or predictive conversion model; all scores are hand-tuned weights.
- No AI auto-reply or chatbot for customers; no sentiment or intent model beyond keyword rules.

---

## Q7. What channels do sellers and admins use (web, mobile, LINE), and what admin/reporting tools exist?

### Takeaway
Users work in a Django web app (the "Connect" lead control center and a seller page with a left sidebar), a demo Expo Go mobile app, and LINE (groups and DMs for notifications). Admin tooling includes a lead database view with duplicate detection, a booking pipeline view, a rules/settings page, a read-only SQL console and data export.

### Cited Findings
- **Connect** (`/connect/`, redesigned 11 Oct as "ศูนย์ควบคุมลีด", the lead control center). Admin pages:
  - Chat inbox.
  - Parking room (one-click seller buttons, live wait time, seller load).
  - Lead database (raw 26-column sheet rows, duplicate detection by code / phone / LINE ID; 931 duplicate codes and 1,217 duplicate phone/LINE rows measured).
  - Pipeline (booking → sign → result → release, overdue flags).
  - Team dashboard.
  - Rules (live switches).
  - Sellers get a single inbox page.
  - Sources: [CLAUDE.md L1966-2012](CLAUDE.md)
- **Seller page** (`/me/`): today's work (slips with countdown, not-yet-called, appointments, stuck deals, due follow-ups), new cars, my customers, chat (embedded Connect), my stats, duplicate-phone check, car status, loan application — [CLAUDE.md L2004-2008](CLAUDE.md)
- **Inbox filters:** awaiting reply, follow-up today, customer not replying (>24 h), silent 3+ / 7+ days, hot, new-car match, stage, heat, lost reason, car model, budget, date range. Badges show stage, heat, appointment, silence and car-match. Bell alerts for the queue, overdue / almost due, appointments, silent customers and car matches — [checkout/crm.py L527-623, L733-789](checkout/crm.py); [CLAUDE.md L2050-2060](CLAUDE.md)
- **Mobile app** (Expo SDK 57, **Expo Go demo only**, real server).
  - Tabs by role: seller = Chat / Today / Cars / Me; admin adds Overview and Parking room; workers and purchasing have their own tabs.
  - Login via the web (LINE Login or password) + PKCE, Bearer token valid 30 days. No new API.
  - **No push notifications** (needs a custom build and a $99/yr Apple Developer account). No sending images to customers.
  - It was built "to evaluate before deciding whether to pay for a real app".
  - Sources: [mobile/README.md L1-69](mobile/README.md); [CLAUDE.md L4682-4747](CLAUDE.md)
- **Notifications to staff are via LINE:** follow-up DMs, slip @mentions, report cards and check-in tables. Many are toggled off by default — [CLAUDE.md L2753-2980](CLAUDE.md); [checkout/leadflow.py L21-30](checkout/leadflow.py)
- **Admin data tools:** read-only SQL console (`/dashboard/sql/`, Postgres READ ONLY transaction, staff LINE IDs scrubbed), CSV/ZIP export, an Excel data dictionary (52 tables, 582 columns), event log (`dash_event_log`, 90 days), system-health page that flags failed sends — [CLAUDE.md L619-676, L988-1043, L1231-1249, L1271-1303](CLAUDE.md)
- **External API v1** (read-only employees and groups, API key): no rate limit or call log — [CLAUDE.md L167-178](CLAUDE.md)

### Inferences
- **(inference)** The mobile story is not yet production-grade: Expo Go plus the same Wi-Fi as the developer's PC, and no push. Field sellers therefore still rely on LINE for real-time alerts.

### Gaps
- No native store app, offline mode or click-to-call telephony integration with call logging.

---

## Q8. What are the known limitations, gaps and pending work?

### Takeaway
The biggest structural issues are:
1. Replies sent outside Connect (LINE OA Manager) are invisible, which corrupts SLA, unread and pull-back logic.
2. Dependence on Google Sheets as the system of record, with no write-back from Connect.
3. Missing channel APIs (FB webhook pending Meta review, no TikTok or IG chat).
4. No cross-channel identity.
5. Several "built but switched off" automations.
6. A 60-day data retention limit.
7. A history of silent failures.

### Cited Findings
- **LINE OA Manager blind spot:** LINE does not send events for replies made in the OA Manager app. Consequences:
  - The 5-minute clock never stops, so chats show overdue (102 chats measured; on 4 Oct the team "replied" but Connect showed no replies since 23:21 the night before).
  - Unread state is wrong.
  - Pull-back cannot be enabled.
  - The listed fix is to **remove sellers' LINE OA Manager access** (a pre-launch requirement still open).
  - Sources: [CLAUDE.md L1314-1319, L1380-1383, L1897-1903, L2083-2091](CLAUDE.md)
- **Reply lock switch:** `chat.reply_on()` / `reply_customer` is off by default, with server-side enforcement ("อย่าเพิ่งส่งข้อความอะไรหาลูกค้า" — don't send customers anything yet). The prod status note of 3 Oct 22:00 says `store_customer_chat` and `reply_customer` were **turned on** ("ตอบลูกค้าจริงได้แล้ว" — can now reply to real customers) — [CLAUDE.md L1336-1340, L2102-2103](CLAUDE.md)
- **Push quota:** every reply from Connect is a LINE *push*, which counts against the OA monthly message quota. Moving all replies into the system will raise usage a lot. "ต้องเช็คแพ็กเกจ" (need to check the plan) — [CLAUDE.md L2095](CLAUDE.md)
- **Replies use the receiving OA (OxletAuto)**, an exception to the "send only from OxletautoGiveLead" policy, because a push to a 1:1 chat only reaches people who added that OA as a friend — [CLAUDE.md L2096-2097](CLAUDE.md)
- **Not yet built:**
  - Sellers cannot send images back to customers ("งานถัดไปที่สำคัญที่สุด" — the most important next task).
  - No canned or template replies (only field-gap quick-reply suggestions since 12 Oct).
  - No push in the mobile app.
  - TikTok and IG chat.
  - Separate A/B/C grading.
  - Stages not written to the sheet.
  - Sources: [CLAUDE.md L2092-2100, L2074-2075, L2167, L2324-2329](CLAUDE.md)
- **No write-back to Google Sheets:** Connect lead data and lead codes are kept in Postgres only. Auto-writing to the leads sheet is "ต้องถามเจ้าของก่อน" (ask the owner first) because it would affect all dashboard numbers and risk duplicating rows admins type by hand. Admins must still add the sheet row by hand. **Lead numbers can collide** with codes admins issue directly in the sheet — [CLAUDE.md L1525-1527, L1685-1688](CLAUDE.md)
- **Duplicate entry risk in purchasing:** the team types each buy-in case into the monthly tab by hand. If the bot also writes, cases duplicate, so the bot writes a TestBot tab until the owner decides — [CLAUDE.md L4567-4570](CLAUDE.md)
- **Facebook webhook** needs Meta App Review plus Business Verification (owner action pending). Until then FB arrives by polling (≤2 min delay; risk of showing as overdue) — [CLAUDE.md L1866-1872](CLAUDE.md); [deploy/meta_business_verification.md](deploy/meta_business_verification.md)
- **TikTok Business Messaging** requires a DSPR security review and policy documents the company does not have (privacy notice, security policy, MFA, pentest). The current token encryption is AES-128 (Fernet) versus the AES-256 TikTok expects — [deploy/tiktok_business_api.md L30-38](deploy/tiktok_business_api.md)
- **No cross-channel identity:**
  - LINE IDs differ per provider (two bots = two people).
  - FB PSIDs are per page.
  - "55% of FB threads contain a LINE ID in the text" but are not linked.
  - Sources: [CLAUDE.md L2788-2797, L3115](CLAUDE.md)
- **PDPA retention trade-off:** customer chats, Connect rows and lead data are deleted after 60 days of silence. Keeping seller chat history longer "needs a PDPA decision first" — [CLAUDE.md L2098-2099](CLAUDE.md)
- **Google Sheets dependency and fragility:**
  - Header-based column mapping is needed because layouts change monthly.
  - Documented silent bugs: a whole month lost to one header cell; 481 cases lost when 5 columns were inserted; a fixed read range capped purchasing leads at 398 per month (28% lost); fetch failures cached silently.
  - Dates are lost via FORMATTED_VALUE.
  - Sources: [CLAUDE.md L2690-2752, L4366-4386](CLAUDE.md)
- **Recurring "silent failure" mode:** daily reports stopped 2–3 days (Aug), scheduled cards failed 10 days (17–26 Sep), follow-up DMs to the whole team failed 3 days (25–27 Sep) because of wrong-provider IDs. Found by the owner, not by alerts. Now covered by the system-health monitor — [CLAUDE.md L1025-1043, L2863-2895](CLAUDE.md)
- **Need matching** (`CustomerNeed`) is still run by hand; no cron and no seller alert when a matching car arrives — [CLAUDE.md L2410-2414](CLAUDE.md)
- **Pending pre-launch checklist:** migrations, enabling customer chat, enabling replies, removing OA Manager access, setting the first shift — [CLAUDE.md L2083-2091](CLAUDE.md)
- **Prod data hygiene:**
  - On 9 Oct, 141 Connect rows existed and 86 had been waiting >2 days (mostly answered in OA Manager).
  - Pending-pickup candidates: 144, of which 73 within 3 days (66 were Facebook customers who gave a LINE ID).
  - Sources: [CLAUDE.md L1443-1445, L2262](CLAUDE.md)
- **Open DB exposure (owner decision):** on 4 Oct the owner chose to open Postgres port 5432 online for external read-only access to all tables, including personal data. Only password and token columns are hidden; access is rate-limited — [CLAUDE.md L1250-1270](CLAUDE.md)

### Inferences
- **(inference)** Many capabilities are "dark-launched" (built, tested, off by default) because the owner is cautious about outbound messaging and quota. The operational CRM is therefore less automated than the code suggests.
- **(inference)** Running two sources of truth (Sheets + Postgres) is the main architectural debt, and the most likely reason to consider a packaged CRM.

### Gaps
- No documented go-live date or adoption metrics (e.g. % of chats actually answered in Connect versus OA Manager after 4 Oct).
- No cost figures for the in-house build (developer time). The mobile prototype doc mentions ~4,400 THB first-year infra cost for 50–60 users ([CLAUDE.md L4742](CLAUDE.md)), with no wider TCO.

---

## Q9. What are the scale facts and architecture?

### Takeaway
A small-to-mid dealership operation: about 18 sellers in Connect (13–21 in sales config and sheet dropdowns), around 50 employees, tens of thousands of leads per year in Sheets, about 60–75k chat messages stored, on a single VPS with Django, Postgres and n8n.

### Cited Findings
- About 18 sellers in Connect scope — [CLAUDE.md L1353](CLAUDE.md). Sheet "E เซลล์" dropdown has 21 values — [CLAUDE.md L1700](CLAUDE.md). Employees: 48–51 — [CLAUDE.md L176, L1235](CLAUDE.md)
- Leads sheet: 22,275 rows (Aug), 14,790 after removing RJ/RB and duplicates — [CLAUDE.md L484](CLAUDE.md). Junk (returned / reassigned / cancelled) is ~50% of leads in a month — [CLAUDE.md L281](CLAUDE.md). Running lead code ~8,400 by Oct (e.g. `NLD10-8409`) — [CLAUDE.md L1630](CLAUDE.md)
- Purchasing (buy-in) leads Jan–Sep: 4,825; cars bought in: 466; stock ready to sell ~90 of 209–236 — [CLAUDE.md L4395, L4379](CLAUDE.md)
- DB (28 Sep): 48 tables, 108,129 rows, 192 MB; 20 tables hold personal data. Excel dictionary (3 Oct): 52 tables, 582 columns — [CLAUDE.md L1215-1219, L1233-1236](CLAUDE.md)
- Connect at prod-like scale: 2,314 customers, 33k messages; normal list request ~0.09 s — [CLAUDE.md L1486-1503](CLAUDE.md)
- Seller reports in the dispatch room: ~1,189 per week — [checkout/leadflow.py L13-14](checkout/leadflow.py)
- **Stack:**
  - Django 4.2 on a Hostinger VPS (gunicorn, nginx, Postgres local).
  - n8n calls `/api/cron/tick` every minute.
  - Google Sheets API (service account), Google Drive (media), Playwright (report images), Gemini (AI), LINE Messaging API ×2, Meta Graph API, TikTok Login Kit, YouTube Data API.
  - Expo app.
  - Sources: [CLAUDE.md L13-24, L560-568, L4682-4747](CLAUDE.md)
- **Test coverage** (indicative of in-house rigor): test_connect 710, test_leadflow 158, test_crm 145, test_chat_media 131, test_lead_keywords 115 assertions — [CLAUDE.md L2307, L2014, L2076, L2165, L2342](CLAUDE.md)
- **Development pace:** the last 40 commits (Oct 2026) are almost all Connect/CRM features: chat highlights, buy vs sell leads, parking room, mobile app, chat inbox, lead database, dispatch automation — [git log --oneline -40](.git)

### Inferences
- **(inference)** The volume (hundreds of chats per day across ~18 sellers) is within the range global SaaS CRMs (Salesforce, HubSpot, Zoho) or LINE-native Thai CRMs (e.g. Zwiz.ai, SleekFlow, respond.io) handle easily. The in-house system's differentiation is its dealership-specific dispatch, Sheet integration and LINE-group workflows, not scale.
- **(inference)** The in-house build carries key-person and maintenance risk: one owner/developer working with an AI coding assistant, documentation in a single 4,700-line dev log, and README drift.

### Gaps
- No precise daily or monthly inbound chat volume per channel is documented.
- No measured SLA performance (median response time) from production is quoted in the docs.
