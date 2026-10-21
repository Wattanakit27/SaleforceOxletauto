# CRM built on LINE (LINE Official Account / Messaging API): Thailand, Japan, Taiwan, as of Oct 2026

Research date: 2026-10-12. Scope: what LINE OA natively offers for CRM, what the Messaging API allows and forbids for third-party CRMs, LINE-based CRM vendors in TH/JP/TW, Thai automotive use, and PDPA. The comparison target is a Thai used-car dealer's in-house CRM that ingests LINE OA chats via webhook.

---

## 1. LINE OA native CRM features (2025–2026) and LINE OA pricing (TH, plus JP/TW for reference)

### Takeaway
On its own, LINE OA is a light CRM: chat with tags and notes, segmented broadcast, rich menu, coupons, a membership card, and the MyCustomer loyalty add-on. Thailand sells the deeper chat features as a paid "OA Chat Package" (555 THB/month ex-VAT). It adds 5-year chat history, chat export, up to 300 tags and 1,000 notes per chat, and an AI chatbot beta. Thai plans are Free (300 broadcast messages), Basic (1,280 THB, 15,000) and Pro (1,780 THB, 35,000), all ex-VAT. Chat replies, auto-replies and greetings don't count toward the quota.

### Cited Findings
**Thailand plans and prices**
- Thai monthly plans: **Free** 300 broadcast messages/month with no extra messages; **Basic** 1,280 THB/month for 15,000 messages, extras 0.10 THB each; **Pro** 1,780 THB/month for 35,000 messages, extras 0.06 THB each. Prices exclude 7% VAT. Chat messages, auto-reply and greeting messages are not counted. — [Z.com (LINE TH agency) package explainer](https://website.z.com/th/en/lineoa-article-package/); [LINE for Business TH – features/pricing pages](https://lineforbusiness.com/th/service/line-oa-features). Note: one LINE Help Center page reportedly lists Pro extras as "0.6 THB", which is likely a typo for 0.06. Unverified.
- LINE TH announcement of 18 Jun 2024, effective 1 Aug 2024: Pro cut from 1,869 to 1,780 THB/month and now **includes MyCustomer | CRM** (valued at 369 THB/month). Free quota cut from 500 to 300 messages/month. Pro extras raised from 0.04 to 0.06 THB from the billing cycle starting 10 Sep 2024. Mid-month upgrades deduct free messages already sent above 300 from the new quota. — [LINE for Business TH news 20240619_1](https://lineforbusiness.com/th/news/20240619_1)
- Earlier change effective 1 Aug 2023: Basic went from 1,200 to 1,280 THB and Basic extras from 0.08 to 0.10 THB. Upgrading Basic to Pro mid-month costs the 220 THB difference. — [Prachachat](https://www.prachachat.net/hilight-prachachat/news-1330156). Older articles such as Brand Inside still quote 1,200/1,500 THB, which is outdated. — [Brand Inside](https://brandinside.asia/what-is-line-oa/)

**OA Chat Package (Thailand)**
- Price is **555 THB/month ex-VAT**, charged in full on the 1st of the month even if bought mid-month. Purchase is through manager.line.biz or the mobile webstore. — [LINE for Business TH – OA Chat Package](https://lineforbusiness.com/th/service/line-oa-features/oa-chat-package)
- Free vs package, per the same page:

| Feature | Free | Package |
|---|---|---|
| Chat history retention | 6 months | 5 years |
| Chat history download | No | Yes |
| Tags created | 5 | 300 |
| Tags per chat | 1 | 30 |
| Notes | 1 per chat | 1,000 per chat |
| Custom filter | No | "coming soon" |
| AI Chatbot auto-reply (Beta; Q&A built from PDF, JPEG or PNG) | No | Yes |

  - History created before 1 Jan 2024 can't be viewed or downloaded, even with the package.
  - After cancelling, existing tags and notes stay but no new ones can be created.
  - MyShop add-ons are bundled: direct transfer, customer profile, reminders, scheduled messages.
  - [LINE for Business TH – OA Chat Package](https://lineforbusiness.com/th/service/line-oa-features/oa-chat-package)
- An agency lists an annual option of 3,999 THB/year (about 333 THB/month ex-VAT) for the chat package. — [Z.com LINE OA page](https://website.z.com/th/en/lineoa/)
- The page doesn't mention assignees, multiple-admin routing or auto-assignment. — [LINE for Business TH – OA Chat Package](https://lineforbusiness.com/th/service/line-oa-features/oa-chat-package)

**MyCustomer | CRM and OA Plus**
- MyCustomer | CRM is LINE TH's add-on for memberships, loyalty points and customer segmentation. It costs 369 THB/month ex-VAT standalone, signup is at oaplus.line.biz, and it is part of the "OA Plus" tools alongside MyShop and MyRestaurant. — [Z.com LINE OA page](https://website.z.com/th/en/lineoa/); [LINE TH news 20240619_1](https://lineforbusiness.com/th/news/20240619_1) (included in Pro since Aug 2024)

**LINE Thailand's 2026 business lineup (Marketing Oops, 11 Aug 2026, quoting LINE TH VP Commerce)**
- 56M LINE users in TH, more than 12B LINE OA conversations in 2025, and about 800M new OA friend-adds in H1 2026.
- Verified OAs now show blue and green badges.
- OA Chat Package keeps chat history for 5 years.
- MyShop is a chat-commerce engine with AI automation for taking orders in chat.
- "MyTeam" is slated for early 2027.
- LINE MINI Apps tripled to more than 1,000 after developer access opened in March 2026.
- No prices were given and figures are LINE's own.
- [Relevant Audience summary, 12 Aug 2026](https://www.relevantaudience.com/digital-marketing-en/line-thailand-business-solutions-2026/)

**Platform features exposed to developers (2025)**
- 13 Feb 2025: the Messaging API gained an endpoint for the user IDs of users who joined an OA **membership**, plus a membership webhook event (join, renew, leave). — [LINE Developers news (LINE OA tag)](https://developers.line.biz/en/news/tags/line-official-account); [Use membership features](https://developers.line.biz/ja/docs/messaging-api/use-membership-features/)
- 6 Aug 2025: **coupons** can be created, discontinued and listed via the Messaging API and sent as messages. Drafts are only possible in OA Manager. — [LINE Developers – Send coupons](https://developers.line.biz/en/docs/messaging-api/send-coupons-to-users/)
- 25 Jun 2025 (Japan): new OAs must be connected to Business Manager. LINE Bot MCP Server was published on GitHub. — [LINE Developers news](https://developers.line.biz/en/news/tags/line-official-account)

**Japan reference: chat features and plans**
- Japan sells the chat-history extension as the **"チャットProオプション" (Chat Pro option)** at 3,000 JPY/month ex-tax, available from 4 Mar 2025.
  - It keeps text, images, video and files for up to 5 years, covering history from 1 Jan 2024 onward, and raises tag and note limits.
  - In group or multi-person chats, images and video are kept only 2 weeks and files 1 week, with or without the option.
  - [LY Biz – Chat Pro option](https://www.lycbiz.com/jp/service/line-official-account/chat-pro-option); [LY Biz news 2025-03-05](https://www.lycbiz.com/jp/news/line-official-account/20250305)
- JP plans (ex-tax):

| Plan | Monthly fee | Free messages | Extra messages |
|---|---|---|---|
| Communication | 0 JPY | 200 | Not possible |
| Light | 5,000 JPY | 5,000 | Not possible |
| Standard | 15,000 JPY | 30,000 | 3 JPY each; from **1 Oct 2026**, 3 JPY up to 200k extra and 2.5 JPY beyond |

  - Notice dated 16 Feb 2026. Premium ID rises from 100 to 400 JPY/month from 1 Dec 2026.
  - [Aurant Technologies, updated 30 Sep 2026, citing lycbiz.com](https://aurant-technologies.com/blog/line-official-pricing-plan-2026/)

**Taiwan reference: plans**
- TW plans (ex-tax):

| Plan | Monthly fee | Free messages | Extra messages |
|---|---|---|---|
| 輕用量 (Light) | NT$0 | 200 | Not possible |
| 中用量 (Medium) | NT$800, rising to **NT$1,000 from 1 Nov 2026** | 3,000 | Not possible |
| 高用量 (High) | NT$1,200, rising to **NT$1,400** | 6,000 | NT$0.2 each for 1–50,000, then NT$0.15 |

  - [ACTGSYS, 30 Sep 2026, citing LINE Biz-Solutions notice](https://actgsys.com/zh/blog/line-bot-development-cost-guide-2026); 2023 baseline in [Omnichat TW blog](https://blog.omnichat.ai/tw/line-2-0-official-account-pricing/)

### Inferences
- Thailand's native "CRM" is now mostly OA Manager chat plus the paid OA Chat Package, MyCustomer and MyShop. None of these appears to offer lead pipelines, sales-rep ownership, SLA timers or vehicle/stock linkage. The dealer's in-house CRM is differentiated on exactly those.
- At 555 THB/month, buying the OA Chat Package is cheap insurance for 5-year chat retention and export inside LINE, even if the in-house CRM is the system of record. It also makes OA Manager a better backup and audit view of conversations.
- On cost, the Thai Pro plan's 35,000 messages (1,780 THB) is the main lever if the CRM sends many push messages. See section 3 on push vs reply.

### Gaps
- No official Thai doc confirms whether Thailand's OA Manager has a native chat "assignee" (ผู้รับผิดชอบ) feature. A Japanese vendor blog surfaced in search says Japan's OA Manager added a 担当者 (assignee) feature in June 2023, but I couldn't verify the source page.
- Verified-badge (blue) fee: a Thai marketing article surfaced in search claims 888 THB one-time, and another says badge display became more prominent from April 2026. Neither was confirmed with an official LINE TH page.
- No official TH page found listing the exact AI Chatbot (Beta) limits or eligible industries.

---

## 2. Critical technical question: do staff replies sent from LINE OA Manager (app or web) reach the Messaging API webhook? How do third-party CRMs cope, and do any official APIs help?

### Takeaway
No. LINE has no "echo" or outbound-message webhook for messages typed by staff in LINE OA Manager. Webhooks carry only user-originated events (message, follow, unfollow, postback, unsend and similar). Major vendors document this explicitly: respond.io says echo messages from LINE don't appear, and Omnichat says replies made in the LINE OA backend don't enter its inbox. The standard industry answer is to make the vendor's own inbox the only place agents reply. Japanese tools like L Step even recommend turning OA Manager Chat OFF. Partner-only Module channels with chat control (Acquire/Release) exist, but they are Japan/LINE-Marketplace, corporate-application-only, and still don't expose OA Manager-typed messages. The newer public helpers are Mark-as-read (needs Chat ON) and the loading animation; neither solves outbound visibility.

### Cited Findings
**What the webhook carries**
- Webhook event types for 1:1 chats are message, unsend, follow, unfollow, postback and video-viewing-complete. The platform POSTs an event "each time a user adds the account as a friend or sends it a message". No event type exists for messages sent by the OA or its staff. — [LINE Developers – Receive messages (webhook)](https://developers.line.biz/en/docs/messaging-api/receiving-messages/)

**What vendors document**
- respond.io (help page last modified 17 Aug 2026):
  - "Echo messages from the LINE channel do not appear on the respond.io platform due to a limitation of LINE Channel itself."
  - "If you have the Chat and Webhooks toggles turned on at the same time, messages sent from the Line Developers Console will not be reflected on the respond.io platform."
  - User profile info may not be shared.
  - [respond.io – LINE channel help](https://respond.io/help/channels/line)
- Omnichat (Taiwan/HK, LINE tech partner): "在 LINE OA 後台回覆給客人的訊息不會進入到 Omnichat 的後台", meaning replies made to customers in the LINE OA backend do not enter Omnichat. — [Omnichat docs – LINE integration troubleshooting](https://docs.omnichat.ai/features/tong-xun-qu-dao/integrations/line-2.0/line-zheng-he-yi-nan-pai-cha)
- L Step (Japan): per its setup guidance surfaced in search, the recommended OA response settings are Chat OFF, greeting OFF, Webhook ON, auto-response OFF. Agents then reply from L Step's own 1:1 chat, so every message passes through its system. — [linestep.jp setup articles](https://linestep.jp/2021/06/04/first_setup/) (search snippet; exact page not individually verified)
- Older behaviour: switching OA response mode to "Chat" used to disable the webhook automatically, so integrations told users to stay in "Bot" mode. — [Zendesk help – LINE integration stops receiving messages](https://support.zendesk.com/hc/en-us/articles/4408826465690-LINE-integration-stops-receiving-messages)

**Chat and webhook can coexist (since about 2022)**
- Chat and webhook can now run together via OA Manager response settings, where previously it was "webhook or chat". OA Manager then displays *all* exchanges, including bot/API-sent ones ("OAMには全部のやり取りも含め表示されています"). — [Classmethod DevelopersIO, 10 Dec 2022](https://dev.classmethod.jp/articles/line-chat-webhook)

**Only one webhook endpoint per channel**
- Each OA's Messaging API channel has a single webhook URL. Connecting the same OA to a second tool redirects incoming messages away from the first. — [Conduit docs – Connect LINE](https://docs.conduit.ai/setting-up-conduit/connect-line)
- Normally only one Messaging API channel can be opened per OA, and an OA can't be un-linked from its Messaging API channel. — [LINE Developers – Module overview](https://developers.line.biz/en/docs/partner-docs/module/); [LINE Developers FAQ](https://developers.line.biz/en/faq/)

**Module channels and chat control (partner-only)**
- A module channel attaches to an OA and can call the Messaging API. One module channel can be linked to many OAs.
- Events for "content sent to the LINE Official Account's chat room" go to the module. If the OA also has a Messaging API channel with webhooks enabled, that channel receives a copy with `mode: "standby"` and no replyToken.
- LINE's own example flow mixes an operator replying in OA Manager chat with a module bot triggered from the rich menu.
- Restrictions:
  - Available "only to corporate customers who have made the prescribed applications".
  - "currently… only available for release as a paid extension on the LINE Marketplace (only available in Japanese)".
  - Only one module per OA on Marketplace.
- [LINE Developers – Module overview](https://developers.line.biz/en/docs/partner-docs/module/)
- Chat control ("initiative"):
  - Managed per user, chat room or group. Only one **Active** channel per OA, by default the primary Messaging API channel; all others are **Standby** and should not send.
  - Uses the Acquire Control and Release Control APIs.
  - Marketplace "Default Active" modules take control automatically on attach.
  - [LINE Developers – Chat control](https://developers.line.biz/en/docs/partner-docs/module-technical-chat-control/)
- Standby events carry no replyToken. Module events fire on switch to active or standby. — [LINE Developers – Using the Messaging API from a module channel](https://developers.line.biz/en/docs/partner-docs/module-technical-using-messaging-api/)

**"Switcher API"**
- No current LINE Developers page documents a "Switcher API". The name appears in NAVER Cloud's CLOVA Chatbot guide as an agent-handoff API, enabled only for corporations that have contracted with LINE for Switcher API. — [NAVER Cloud CLOVA Chatbot guide](https://guide.ncloud-docs.com/docs/en/chatbot-chatbot-6-1)
- LINE's partner notices for 2025–2026 mention neither Switcher API nor module changes. — [LINE Developers – Notice for corporate customers](https://developers.line.biz/en/docs/partner-docs/notice/)

**Mark messages as read (public)**
- Endpoint: `POST https://api.line.me/v2/bot/chat/markAsRead` with `markAsReadToken`, which arrives in each webhook message event.
- It marks the target message and all earlier messages as read. Tokens have no expiry.
- Chat must be ON. With Chat OFF, user messages are auto-marked as read.
- [LINE Developers – Mark messages as read](https://developers.line.biz/en/docs/messaging-api/mark-as-read/)
- Old partner API: the notice of 18 May 2026 says new applications for the old "Mark as read API" stop at end of Oct 2026, and LY may deprecate it. Users should migrate to the public endpoint, which "can be used in conjunction with the chat feature". The old API couldn't be used together with chat. — [LINE Developers – Notice for corporate customers](https://developers.line.biz/en/docs/partner-docs/notice/)

**Loading animation (public)**
- Endpoint: `POST /v2/bot/chat/loading/start` with `loadingSeconds` from 5 to 60. Works in 1:1 chats only.
- Shown only while the user is viewing the chat. Disappears on timeout or when the OA sends a message.
- [LINE Developers – Loading animation](https://developers.line.biz/en/docs/messaging-api/use-loading-indicator/)
- Rate limit is 100 requests per second. — [Messaging API reference](https://developers.line.biz/en/reference/messaging-api/)

**Read receipts**
- You can't use the Messaging API to verify that a message *you* sent was read. — [LINE Developers FAQ](https://developers.line.biz/en/faq/)

### Inferences
- The dealer's observation is expected platform behaviour, not a bug. There is no official API, public or partner, that delivers OA Manager-typed staff messages to a third-party webhook. Module channels receive user→OA content events, not operator outbound messages, and aren't available to Thai SMEs anyway.
- The architecture used by every vendor found is: **all outbound replies go through the CRM**, using the Reply API when within the reply-token window, otherwise Push. OA Manager remains a read-only mirror, because API-sent messages appear in OA Manager chat per Classmethod.
- Recommended operating rule for the in-house CRM, drawn from vendor practice:
  - Keep Chat ON so OA Manager still shows the full thread as a backup and Mark-as-read works.
  - Forbid replying from the OA Manager app by policy.
  - Optionally detect "gaps" (customer message followed by no CRM reply) for SLA alerts.
- Turning Chat ON plus calling markAsRead only when a salesperson actually opens the thread in the CRM gives customers truthful "Read" receipts. With Chat OFF, every message is instantly shown as read, which hides slow follow-up.
- A practical fallback for staff who insist on using the LINE app is to have them reply in the CRM. Alternatively, staff can paste or log a manual summary in the CRM. There is no technical capture path.

### Gaps
- I found no single LINE official sentence that literally says "messages sent from OA Manager are not delivered to webhooks". The conclusion rests on the webhook event list plus explicit vendor documentation (respond.io, Omnichat).
- The general-availability date of the public Mark-as-read endpoint wasn't confirmed: the Codezine article returned 403. The docs page has no date. Search snippets suggest late 2025.
- I couldn't confirm whether a module channel receives events for operator-sent OA Manager messages. The docs only say "content sent to the LINE Official Account's chat room".

---

## 3. Messaging API limits relevant to a CRM

### Takeaway
Replies made with a reply token are free but must be used within about 1 minute. Every push, multicast, broadcast or narrowcast counts against the monthly quota per recipient. Profile lookup works for friends and for non-friends who messaged, but not for users who blocked the OA. The follower-ID list needs a verified or premium account. Media must be downloaded promptly because LINE auto-deletes it after an unspecified period. Webhook redelivery is opt-in and doesn't guarantee delivery.

### Cited Findings
**Reply vs push and quota counting**
- "Reply tokens must be used within one minute after receiving the webhook. Use beyond one minute isn't guaranteed to work." Expired or used tokens return "Invalid reply token". — [Messaging API reference](https://developers.line.biz/en/reference/messaging-api/)
- Reply messages don't count toward the message count. Chats, auto-responses and greetings in OA Manager are free too. Push, multicast, broadcast and narrowcast count. — [LINE Developers FAQ](https://developers.line.biz/en/faq/)
- Messages are counted per recipient. One push containing several message objects to one user counts as one message. Messages to users who don't receive them, such as blocked users, aren't counted. Scheduled sends temporarily *reserve* quota, which can trigger 429 "monthly limit" errors. — [LINE Developers FAQ](https://developers.line.biz/en/faq/)

**Rate limits and idempotency**
- Rate limits: broadcast and narrowcast 60 requests per hour; multicast 200 requests per second; other endpoints 2,000 requests per second; loading animation 100 requests per second. — [Messaging API reference](https://developers.line.biz/en/reference/messaging-api/)
- Retry keys for idempotent pushes are kept for 24 hours. — [Messaging API reference](https://developers.line.biz/en/reference/messaging-api/)

**Profiles, user IDs and consent**
- Get profile works for users who added the OA as a friend and for users who haven't but have sent the OA a message. "You can't get the profile information of a user who has blocked your LINE Official Account." — [Messaging API reference](https://developers.line.biz/en/reference/messaging-api/)
- The follower-IDs list is **verified or premium accounts only**; others get a 403. It excludes deleted accounts, users who blocked, and users who didn't consent to profile access. — [Messaging API reference](https://developers.line.biz/en/reference/messaging-api/); [Getting user IDs](https://developers.line.biz/en/docs/messaging-api/getting-user-ids/)
- User IDs are per provider: the same provider gives the same ID across its channels. Format is `U[0-9a-f]{32}`. — [Getting user IDs](https://developers.line.biz/en/docs/messaging-api/getting-user-ids/)
- If a user hasn't consented to profile access (for example, users who never used LINE on iOS or Android), webhooks contain no user ID and no membership events fire. — [User consent](https://developers.line.biz/en/docs/messaging-api/user-consent/); [Getting user IDs](https://developers.line.biz/en/docs/messaging-api/getting-user-ids/)

**Content retrieval**
- Images, video, audio and files are fetched via `GET https://api-data.line.me/v2/bot/message/{messageId}/content`, with previews at `/content/preview`.
- "Content that users send is automatically deleted after a certain period of time". The period is unspecified.
- "There is no API available to get the text again after receiving the webhook."
- [Receive messages](https://developers.line.biz/en/docs/messaging-api/receiving-messages/); [Messaging API reference](https://developers.line.biz/en/reference/messaging-api/)
- For comparison, OA Manager keeps chat history 6 months on free TH accounts and 5 years with the OA Chat Package. — [OA Chat Package](https://lineforbusiness.com/th/service/line-oa-features/oa-chat-package)

**Webhook redelivery**
- Off by default and enabled in the Console.
- Redeliveries are identical except `deliveryContext.isRedelivery=true`. Duplicates are possible, so dedupe on `webhookEventId`. Order may change, so use `timestamp`.
- Retry count and interval aren't disclosed, and redelivery "doesn't guarantee" delivery.
- [Receive messages](https://developers.line.biz/en/docs/messaging-api/receiving-messages/)
- LINE emails error notifications and shows a "Webhook errors" tab. The notification email format changed on 30 Jun 2025. — [LINE Developers – Error notification](https://developers.line.biz/en/docs/partner-docs/error-notification/); [Notice](https://developers.line.biz/en/docs/partner-docs/notice/)

**Multiple OAs**
- One Messaging API channel per OA. Module channels (partner-only) can attach to many OAs. — [Module overview](https://developers.line.biz/en/docs/partner-docs/module/)
- A CRM handling several OAs, such as multiple branches, needs one channel and token set per OA. User IDs differ across providers. — [Getting user IDs](https://developers.line.biz/en/docs/messaging-api/getting-user-ids/)

### Inferences
- **Quota impact for a dealer CRM:**
  - Any salesperson reply sent more than about 60 seconds after the customer's message must be a push, so it consumes quota.
  - A busy dealer chatting with hundreds of leads daily can burn through Basic (15,000) or Pro (35,000) quickly.
  - Mitigations:
    - Auto-acknowledge with the reply token immediately, which is free.
    - Bundle up to five bubbles into one push, which counts as one message per recipient.
    - Monitor quota with the "number of messages sent this month" endpoint.
- Download media (car photos, ID cards, payslips, slips) to your own storage immediately on webhook, since LINE deletes it after an undisclosed period. Store text from the webhook payload, because it can't be re-fetched.
- Call Get profile on follow and message events to cache display name and picture. Expect failures for blocked users and missing user IDs for non-consenting users.
- Enable redelivery and build idempotency on `webhookEventId`.

### Gaps
- Exact content-retention period for message media is not documented.
- The per-message overage cost when pushes exceed the Thai plan quota is covered in section 1. Whether Thai quota resets at the calendar month or billing cycle wasn't confirmed.

---

## 4. LINE-based CRM / chat-commerce vendors: features, target market, pricing

### Takeaway
- **Thailand:** a crowded field of LINE-OA-connected inboxes, bots and loyalty CRMs. Examples are ZWIZ.AI, ChocoCRM, Page365, ZORT, OHO, KaoJai, Zaapi, Botnoi, klink, Buzzebees, Ourgreenfish (HubSpot) and Cresclab. Prices run from a few hundred to about 6,000 THB/month, plus LINE OA fees.
- **Japan:** the mature "LINE marketing tool" segment is led by L Step (Lステップ) with Liny as its enterprise tier, L Message (エルメ), Mico Engage AI (ex-MicoCloud) and KANAMETO.
- **Taiwan:** led by Crescendo Lab (MAAC/CAAC), Omnichat and Super 8.
- All of these sit on the same Messaging API constraints, so agents reply inside the vendor tool.

### Cited Findings
**Thailand**
- **ZWIZ.AI**
  - Features: AI chatbot, Thai bank and TrueMoney slip verification, comment/DM-to-chat automation, live selling with cart, LINE rich menus. Described as a LINE tech partner.
  - Pricing: free plan; SME plans in the hundreds of THB/month; Booking bundle 28,500 THB/year; Loyalty bundle 30,000 THB/year. [HDmall Jib OS comparison, 19 Aug 2026](https://hdmall.co.th/jib-os/blog/7-line-oa-chat-systems-for-clinics/). The official site advertises paid plans from 500 THB/month and a rich-menu builder. — [zwiz.ai](https://www.zwiz.ai/en)
- **Other Thai LINE-OA-capable inboxes and bots**, all from the same HDmall comparison (19 Aug 2026), vendor-sourced prices: [HDmall comparison](https://hdmall.co.th/jib-os/blog/7-line-oa-chat-systems-for-clinics/)

| Vendor | Pitch | Price (THB) |
|---|---|---|
| OHO Chat | Omnichannel inbox, anti-delete of chats, case management, AI drafts | Pro from about 1,000/month annual |
| KaoJai.ai | RAG AI, booking, CheckSlip | Starter 590/month |
| Zaapi | Marketplace orders and stock plus chat | From 1,875/month annual |
| SleekFlow | Automation, AI routing | Pro AI about 3,300/month incl. 500 MAC and 3 users |
| klink.cloud | Voice and chat contact centre | 6.9 per resolved chat; Growth about 3,071 |
| Botnoi | No-code Thai NLP bot | About 0.12 per message |
| Jib OS (HDmall's own) | Clinic CRM | 6,000/month |

- **ChocoCRM (Choco CRM)**
  - Voted #1 "CRM for B2C" in Thailand's MarTech Report for 2023–2025 (13% of votes).
  - New "Marketplace CRM" links Shopee, Lazada, TikTok Shop and **LINE MyShop** orders to a brand membership and points system. — [Marketeer Online](https://marketeeronline.co/archives/458380)
  - A vendor brochure shows Marketing Automation packages of 3,000–4,500 THB depending on 3–18-month terms. It's unclear whether that's per month or total. — [ChocoCRM brochure (Microsoft-hosted PDF)](https://query.prod.cms.rt.microsoft.com/cms/api/am/binary/RW1bBso)
- **Primo**: loyalty and engagement platform (loyalty management, campaigns, touchpoints) for FMCG, retail, finance and healthcare. Its LINE OA integration specifics weren't found. — [CB Insights comparison](https://www.cbinsights.com/compare/choco-card-enterprise-vs-primo)
- **Page365** (by PEAK): social-commerce inbox combining Facebook, Instagram and LINE OA, with auto-reply, shortcuts, free broadcast and per-admin attribution. Free app with in-app purchases. — [App Store – Page365](https://apps.apple.com/us/app/-/id894477175). PEAK moves Page365 API usage to credit packages from 1 Aug 2026 (overage from 0.50 THB/item). — [PEAK help](https://intercom.help/peak/en/articles/15644874-การเปลี-ยนแปลงของลูกค-า-page365-มาสู-ระบบ-credit-package)
- **ZORT**: Thai online-store/OMS that connects LINE OA chat by entering the Messaging API Channel ID and Secret. — [ZORT docs](https://zortout.com/en/docs/how-to-connect-the-line-oa)
- **Pancake / Botcake**: Botcake (Pancake's bot) syncs LINE customer data into Pancake CRM. Pricing not found. — [Botcake – LINE integration](https://botcake.io/integrations/line)
- **Botsphere**: claims LINE Partner status; rich-menu Basic 190 THB/month; Enterprise extra channels 6,990 THB per 2 channels per month. — [botsphere.chat](https://botsphere.chat/)
- **Buzzebees**: LINE OA member-card and loyalty CRM. — [Buzzebees guide, 6 Nov 2024](https://crm.buzzebees.com/en-th/blog/2024/11/06/get-to-know-crm-line-oa/)
- **Ourgreenfish**: LINE OA to HubSpot integration with a dedicated pitch for Thai EV dealerships (see section 5). — [Ourgreenfish](https://ourgreenfish.com/en/ev-market-solutions-line-crm-for-thai-dealers-ourgreenfish)

**Crescendo Lab (TW/TH/JP)**
- Became one of four **LINE Thailand Expert Developer Partners** in June 2025, and claims to be the only SaaS vendor in Asia with both TH Expert and TW Gold status.
- Launched "AiMon" AI agents with a "dual-track" AI strategy. — [Cresclab newsroom](https://www.cresclab.com/en/newsroom/crescendo-lab-gains-line-expert-status-launches-ai-dual-track-strategy)
- **MAAC** is LINE marketing automation and CRM with segmentation and AI content. **CAAC** is a 1:1 chat platform for LINE, IG, FB, WhatsApp and SMS, with AI answers and call recording plus summaries.
- Claims 8.49B messages a year and more than 800 clients (IKEA, H&M, Rakuten), from a single source. — [Biz-Journal (JP)](https://biz-journal.jp/company/post_393725.html)
- Pricing is on request. — [imitsu – MAAC](https://saas.imitsu.jp/cate-line-marketing-tool/service/5087/price)

**Japan**
- **L Step (Lステップ)** official plans, tax-included; LINE OA fee is separate. — [linestep.jp plan page](https://linestep.jp/lp/01/plan.html)

| Plan | Monthly fee | Messages | Notes |
|---|---|---|---|
| Free | 0 JPY | ~200 | 10 tags, 1 scenario |
| Start | 5,000 JPY | ~5,000 | |
| Standard | 21,780 JPY | ~30,000 | Segment rich menus, URL click tracking |
| Pro | 32,780 JPY | ~50,000 | 10 staff, conversion/funnel analytics, ad integration |

  - Every plan includes 1:1 chat, tags, customer-info fields, scoring and reservations.
  - **Webhook forwarding option** costs 5,500 JPY/month per account. **API integration** (Pro) costs 11,000 JPY/month, or 5,500 JPY if Webhook is already taken. Extra staff cost 1,100 JPY/month each.
  - 30-day free trial. Terms revised 1 Jul 2026.
- **Liny** is now integrated as L Step's top enterprise plan (100k+ messages, 11+ operators, heavy integration). Price on request. — [linestep.jp plan page](https://linestep.jp/lp/01/plan.html); [imitsu – Liny](https://saas.imitsu.jp/cate-line-marketing-tool/service/2678/price)
- **L Message (エルメ)**
  - Free plan: 1,000 messages/month, 180-day chat history, 50,000 friends.
  - Standard: 10,780 JPY tax-included. Pro: 33,000 JPY tax-included. Paid plans have unlimited sends and history.
  - Another source lists Pro at 29,700 JPY ex-tax, which conflicts.
  - [imitsu – L Message pricing](https://saas.imitsu.jp/cate-line-marketing-tool/service/3324/price)
- **Mico Engage AI (formerly MicoCloud)**: segment delivery and 1:1 CRM-oriented. Price on request. — [imitsu – Mico Engage AI](https://saas.imitsu.jp/cate-line-marketing-tool/service/1791/price)
- **KANAMETO** (transcosmos online communications): paid plan from 70,000 JPY initial fee, monthly on request. Free plan for corporations and municipalities. — [imitsu – KANAMETO](https://saas.imitsu.jp/cate-line-marketing-tool/service/4164/price)

**Taiwan**
- **Omnichat**: LINE silver technology partner with a Social CDP across LINE, web store, FB and IG. Pricing isn't public. Its docs confirm OA-backend replies don't sync. — [Omnichat blog](https://blog.omnichat.ai/line-pricing-sep2023/); [Omnichat docs](https://docs.omnichat.ai/features/tong-xun-qu-dao/integrations/line-2.0/line-zheng-he-yi-nan-pai-cha)
- **Super 8 (雲發互動科技)**
  - LINE OA, FB and IG marketing-automation and customer-service SaaS, usage-based subscription.
  - Integrates with Vital CRM via open API. Case: 舊振南 got 66% of LINE friends to bind membership in 3 months.
  - Info dates from 2020–22. — [CNA press release](https://www.cna.com.tw/postwrite/chi/309520); [INSIDE](https://www.inside.com.tw/article/18962-super-8-martech)

**LINE's own CRM tools**
- **MyCustomer | CRM** (369 THB/month, or included with Pro) and **MyShop**. — [Z.com](https://website.z.com/th/en/lineoa/); [LINE TH news](https://lineforbusiness.com/th/news/20240619_1)

### Inferences
- Thai vendors are mostly e-commerce, clinic or loyalty oriented: slip checks, orders, points. None found is purpose-built for vehicle sales: stock-matching, test-drive, finance pre-approval, trade-in. Ourgreenfish's HubSpot plus LINE dealer pitch is the closest, and it's a services and integration play, not a product with public pricing.
- Japanese tools (L Step, Liny, L Message) show the mature pattern for a LINE CRM:
  - Tags and custom fields per friend
  - Scenario (step) messages
  - Segment rich menus
  - Scoring
  - Staff 1:1 chat inside the tool
  - Webhook forwarding to other systems as a paid add-on
- These are useful feature benchmarks for an in-house dealer CRM.
- Budget reality for a Thai SME: tool fee (0.5k–6k THB/month) **plus** LINE OA plan (0–1,780 THB) **plus** push-message overage. All third-party inboxes cause agent replies to use push, consuming quota, once past the reply-token window.

### Gaps
- Could not verify that "Rocket", "Bentoweb", "Kinlong" or "Hotlink/Omnichat Thai" exist as active LINE CRM products in Thailand. Searches returned no relevant results; treat as unverified.
- No public current pricing found for Primo, Pancake, Page365's chat tiers, Cresclab MAAC/CAAC, Omnichat, Super 8, Liny, Mico Engage AI or KANAMETO's monthly fee.
- HDmall's comparison is written by a competing vendor (Jib OS), so its competitor prices should be rechecked on vendor sites.

---

## 5. How Thai businesses, especially automotive, use LINE OA for sales

### Takeaway
Thai car brands use LINE OA as a primary customer channel:
- **Toyota:** test-drive registration routed to dealer showrooms, service booking, segmentation, LINE Ads and Business Manager data.
- **Isuzu:** LINE Ads plus OA-follower lookalikes and segmented broadcasts, with a vendor-reported 17x leads and -94% CPL.

No public case study of a Thai *used-car* dealer's LINE CRM was found. Vendor pitches for Thai EV dealers describe the same pain points as Oxlet: slow replies at volume, lost data when reps leave, no hot-lead ranking.

### Cited Findings
- **Toyota Motor Thailand** (Thairath, 19 Dec 2024)
  - LINE OA is a main communication channel offering **test-drive registration and after-sales service booking**. Test-drive requests connect directly to dealer showrooms in the system, and customers choose the showroom.
  - Toyota says conversations and usage behaviour let it segment followers finely.
  - Uses LINE Ads for awareness and Business Manager for LINE-ecosystem data.
  - Built a website for customers to verify a salesperson's name, against impersonation on online channels.
  - Has more than 450 service centres and sold more than 200k units; Toyota Alive-X loyalty runs with The 1.
  - [Thairath](https://www.thairath.co.th/money/business_marketing/trends/2831815)
- **Tri Petch Isuzu Sales**: LINE Ads retargeting and conversion tracking, Lookalike audiences built from OA followers, segmented broadcasts via LINE Business Connect CRM. Reported **leads up 17x and cost-per-lead down 94% in 3 months**, vendor-published and unaudited. — [LINE for Business TH – ISUZU case](https://lineforbusiness.com/th-en/case-study/success-ISUZU)
- **Toyota Road Safety**: LINE OA with a LIFF game ("Drive Well") plus LINE Ads to grow followers. Participants averaged more than 40 activities per person. — [LINE for Business TH – Toyota case](https://lineforbusiness.com/th-en/case-study/toyota)
- **Thai EV dealers** (vendor pitch, no named clients or measured results)
  - Pain points:
    - High chat volume makes reps slow to reply.
    - New and existing customers can't be told apart.
    - "Data is lost if a sales rep leaves."
    - No hot-lead ranking.
    - After-sales can't see chat history.
  - Proposed fixes: LINE OA to HubSpot logging, pipeline stages (browsing, test drive booked, ready to buy), territory/keyword/menu-based routing, 1-day test-drive reminders, model-specific promos, maintenance alerts.
  - [Ourgreenfish – LINE CRM for Thai EV dealerships](https://ourgreenfish.com/en/ev-market-solutions-line-crm-for-thai-dealers-ourgreenfish)
- **LINE Thailand scale**: 56M users and more than 12B OA conversations in 2025, per LINE's own figures. — [Relevant Audience, Aug 2026](https://www.relevantaudience.com/digital-marketing-en/line-thailand-business-solutions-2026/)
- **LY Corp feature on LINE Thailand for Business (4 Nov 2025)**: headline claims "sales +50%" and "200,000 phone calls reduced" in cases from bank DX to brand experience. Details weren't fetched. — [LY Corp story](https://www.lycorp.co.jp/ja/story/20251104/lineth_forbusiness.html)

### Inferences
- The OEM pattern (Toyota) is LINE OA as front door, LIFF/forms for test-drive and service booking, and routing to the selected dealer. A used-car dealer can mirror this:
  - Rich menu entries for "ดูรถในสต็อก / นัดดูรถ / ประเมินไฟแนนซ์ / เทิร์นรถ" (browse stock, book a viewing, finance pre-check, trade-in).
  - LIFF forms that write directly to the CRM, which the CRM controls, unlike OA Manager chat.
- Toyota's "verify salesperson" page shows impersonation is a real risk in LINE-based car sales. A verified OA badge plus a single official OA, rather than salespeople's personal LINE, supports trust and keeps data in the company.
- Ourgreenfish's EV-dealer pain list matches the in-house CRM's goals (SLA, ownership, history retention). The in-house system is aligned with what vendors sell to dealers.

### Gaps
- No Thai used-car dealer (e.g., Toyota Sure, Carsome, Krungthai Car Rent's used-car arm) LINE CRM case study found.
- No public metrics on LINE OA response time vs conversion for Thai auto dealers.

---

## 6. PDPA considerations for storing LINE chats and profiles (Thailand)

### Takeaway
LINE chats, user IDs, display names and photos, plus documents sent in chat (ID cards, payslips, bank statements for finance), are personal data under Thailand's PDPA. Some content, such as religion and health, may be sensitive data under Section 26. The PDPC has moved to real fines: a first THB 7M fine in Aug 2024, then eight fines in five cases announced 1 Aug 2025, mostly over leaks exploited by call-centre scammers. Platform-level LINE "consent to profile access" is not PDPA consent. The dealer needs its own lawful basis, notice, retention schedule and security.

### Cited Findings
**Enforcement**
- First PDPC administrative fine (Aug 2024): **THB 7M** for PDPA non-compliance leading to unauthorized disclosure of personal data to a call-centre scam gang. — [Tilleke & Gibbins – landmark fine](https://www.tilleke.com/insights/landmark-fine-imposed-under-thailands-personal-data-protection-act/)
- 1 Aug 2025: PDPC announced **eight new fines in five cases**:
  - IT retailer THB 7M, after customer data was misused by call-centre fraudsters; company size and revenue were considered.
  - Cosmetics company THB 2.5M.
  - Toy company THB 500k and its data processor THB 3M, after an online reservation breach of about 200k records.
  - Private hospital more than THB 1.2M.
  - Government agency and its developer about THB 150k each.
  - [Tilleke & Gibbins](https://www.tilleke.com/insights/more-than-a-warning-eight-serious-fines-imposed-in-thai-data-protection-cases); [Gala Law](https://blog.galalaw.com/post/102lr0u/thailands-pdpc-signals-tougher-enforcement-with-multi-million-baht-fines)
  - Totals conflict: Tilleke cites about THB 21.5M cumulative; Gala says the round was THB 14.5M and the cumulative total exceeds THB 21M.

**PDPA principles**
- Sensitive data under PDPA s.26 includes race, religion, political opinion, criminal record, sexual orientation and health data, and may be collected only in legally specified cases. — [Thai PBS](https://www.thaipbs.or.th/sciandtech/tech/3698)
- Data minimisation, using only what's necessary for a lawful purpose, is stressed in the PDPC's public handbook. — [PDPA for People (PDPC handbook, Mahidol-hosted)](https://il.mahidol.ac.th/upload/pdpa/PDPA_for_People-2565.pdf)

**LINE-side consent and retention**
- LINE's own "consent to profile information" is a LINE-account-level setting. Without it, webhooks contain no user ID and follower and membership lists exclude the user. — [LINE Developers – User consent](https://developers.line.biz/en/docs/messaging-api/user-consent/)
- LINE OA Manager retains chats 6 months free, or 5 years with the TH OA Chat Package. Third-party retention is the operator's responsibility. — [OA Chat Package](https://lineforbusiness.com/th/service/line-oa-features/oa-chat-package)
- The LINE Official Account API Terms of Use were revised for some countries on 26 Nov 2024. Text not reviewed. — [LINE Developers news](https://developers.line.biz/en/news/tags/line-official-account)
- A Thai healthcare provider integrated LINE CRM with HubSpot "while maintaining PDPA compliance", a vendor claim. — [Relevant Audience](https://www.relevantaudience.com/social-media-marketing/why-modern-crm-lives-in-chat-thailand/)

### Inferences
These are from background PDPA knowledge and should be verified with counsel or pdpc.or.th.
- **Lawful basis:** answering a buyer's enquiry and preparing a sale or finance application can generally rely on contract or pre-contract steps. Marketing broadcasts and re-targeting typically need consent or a carefully assessed legitimate interest. Separate the two in the CRM, for example a `marketing_consent` flag with timestamp and source.
- **Privacy notice at first contact:** use the greeting message and a rich-menu link to the dealer's privacy notice, covering purposes, retention period and data-subject rights.
- **Sensitive data in chats:** ID-card photos, health or disability mentions and similar content can arrive unsolicited. Mask or limit storage, restrict access by role, and define deletion periods for documents once finance is approved or rejected.
- **Processors:** any third-party CRM, AI or LLM, or cloud storage processing chats is a data processor and needs a DPA-style contract. The 2025 toy-company case fined the processor (THB 3M) as well as the controller.
- **Security and breach readiness:** leaks used by call-centre scammers are the PDPC's primary enforcement pattern. Customer phone numbers, names and car-purchase data in a dealer CRM are exactly that risk class. Implement:
  - Access logging
  - Least privilege for sales staff
  - No exporting of lead lists to personal LINE or Excel
  - A breach-notification process (PDPA s.37(4), 72-hour PDPC notification, from background knowledge and not re-verified here)
- Keeping salespeople off personal LINE accounts and on the official OA plus CRM is both a data-control measure and a PDPA measure, since the company remains controller and can honour deletion and access requests.

### Gaps
- No PDPC guidance found specifically on chat-app (LINE) data retention or on ID-card copy masking.
- No 2026 PDPC enforcement decisions found in this search. The newest found was Aug 2025.
- Did not review the Thai LINE Official Account API Terms of Use text for operator data-handling obligations.
