# Omnichannel Conversational CRM / Unified-Inbox Platforms in Thailand & SEA (LINE + Facebook + IG/WhatsApp/TikTok), as of Oct 2026

Research date: 2026-10-12. Prices are as published or reported on the date each source was fetched (Oct 2026) unless noted. Currencies are kept as published. THB conversions are marked "≈" and are my approximations, not vendor figures. They use about 32 THB/USD, which matches the ratio implied by hdmall's THB quote for Zaapi ($59 → 1,875 THB ≈ 31.8). HKD is converted at the 7.8 peg.

---

## 1. Which platforms are prominent in Thailand/SEA, and which natively support LINE OA, Facebook Messenger and TikTok DM?

### Takeaway
Three groups compete in Thailand:
- **Regional SEA/HK/TW players:** respond.io (MY), SleekFlow (HK), Crescendo Lab MAAC/CAAC (TW, with a Bangkok office) and Omnichat (HK).
- **Thai-local, SME/e-commerce tools:** Zwiz.ai, Zaapi, Page365, Chatcone, OHO Chat, KaoJai, klink.cloud and Botnoi.
- **Global helpdesks:** Zendesk, Freshchat/Freshdesk Omni, Chatwoot and Bitrix24.

LINE OA + Messenger support is confirmed for respond.io, SleekFlow, Cresclab, Omnichat, Zwiz, Zaapi, Page365, Chatcone, Zendesk, Freshchat and Chatwoot. Wati, Gorgias, Trengo and Kommo showed no confirmed native LINE support. TikTok DM support is still uneven and region-restricted.

### Cited Findings

**Channel support matrix (confirmed sources)**
- **respond.io:** LINE is a connectable channel with its own help docs. [respond.io LINE help](https://respond.io/help/line/line-overview)
  - The pricing page does not mention LINE; it shows channels only as icons with "+ more" and names WhatsApp, TikTok, Instagram and Facebook. [respond.io pricing](https://respond.io/pricing)
  - The TikTok channel launched in 2025 as an Open Beta. TikTok Business Messaging is unavailable to orgs registered in the US. EEA/Swiss/UK business accounts cannot manage DMs via the API. [respond.io changelog](https://roadmap.respond.io/changelog/tiktok-channel-is-here-connect-with-your-audience-like-never-before)
  - The TikTok Messaging Ads help article says only "Instant Messaging Ads" (which send users to WhatsApp/Messenger) were supported, not Direct Messaging Ads. [respond.io TikTok ads help](https://respond.io/help/integrations/tiktok-messaging-ads-integration)
  - The TikTok solution was announced 10 Jan 2025. [GlobeNewswire](https://www.globenewswire.com/fr/news-release/2025/01/10/3007414/0/en/Respond-io-Unveils-AI-Powered-Solution-for-TikTok-Messaging-Ads-Aiming-to-Bridge-4-1-Trillion-SME-Financing-Gap.html)
- **SleekFlow:** The pricing page lists WhatsApp, LINE, Messenger, Instagram, TikTok, Viber, WeChat, Telegram, SMS, Outlook, Gmail and voice calls. It says "All messaging, email and calls channels — included on every plan", but the number of channels is capped per plan. [SleekFlow HK pricing](https://sleekflow.io/en-hk/pricing)
  - **Conflict:** hdmall's 2026 Thai roundup says SleekFlow has no TikTok. [hdmall](https://hdmall.co.th/jib-os/blog/7-line-oa-chat-systems-for-clinics/index.md)
- **Crescendo Lab (Cresclab):**
  - The homepage names WhatsApp, LINE, Instagram, Messenger, web chat and SMS. [cresclab.com](https://cresclab.com)
  - A CAAC tutorial says LINE OA and FB page conversations can be managed together in CAAC. [Tango tutorial: CAAC Omnichannel – Facebook Messenger](https://app.tango.us/app/workflow/4ffd2f65-a90c-4d53-b056-ba4ffe6147ee)
  - It has offices in Taipei, Tokyo and Bangkok, and is an official LINE Thailand tech partner. [Cresclab company](https://cresclab.com/en/company); [Cresclab blog](https://blog.cresclab.com/th/crescendo-lab-is-now-a-line-thailand-tech-partner)
- **Omnichat:** Supports WhatsApp, Messenger, Instagram, LINE, TikTok, WeChat and web chat. This comes from a competitor (imBee), not from Omnichat. [imBee](https://id.imbee.io/omnichat-alternatives)
  - Thailand was named among Omnichat's first SEA expansion markets in its 2022 press release. [Omnichat PR](https://blog.omnichat.ai/pre-a-round-funding-press-release/amp/)
- **Zwiz.ai (Thai):** Automated chat and comment handling on Facebook, Instagram, LINE, TikTok and WhatsApp, with one inbox for all channels and desktop + mobile apps. [zwiz.ai/en](https://www.zwiz.ai/en)
- **Zaapi (Thai-focused):** Unified inbox for LINE OA, Facebook, Instagram, TikTok, WhatsApp, Shopee and Lazada, with "unlimited channels" on all paid plans. [Zaapi pricing](https://www.zaapi.com/pricing)
- **Page365 (Thai):** Combines Facebook, LINE OA and IG chats and includes order/stock management. TikTok is not mentioned. [App Store listing](https://apps.apple.com/us/app/-/id894477175)
- **Chatcone (by MakeWebEasy, Thai):** The free plan connects 2 channels (LINE, Facebook Messenger, web chat). [MakeWebEasy Chatcone](https://www.makewebeasy.com/en/chatcone)
- **Other Thai tools in a 2026 roundup.** hdmall says to verify prices with each vendor. [hdmall](https://hdmall.co.th/jib-os/blog/7-line-oa-chat-systems-for-clinics/index.md)
  - **OHO Chat:** LINE, FB, IG, TikTok Shop.
  - **KaoJai.ai:** LINE OA, FB.
  - **klink.cloud:** voice, LINE OA, web chat, FB; no TikTok.
  - **Botnoi:** LINE OA, FB, website; no TikTok.
  - **Jib OS** (clinic vertical): LINE OA, FB, IG, WhatsApp, email, web chat.
- **Zendesk:** The Agent Workspace natively supports WhatsApp, LINE, WeChat, Facebook Messenger and Twitter DM. Extra channels through Sunshine Conversations need Suite Professional or above. [Zendesk help](https://support.zendesk.com/hc/en-us/articles/4408836484378-Adding-Sunshine-Conversations-channels-to-the-Zendesk-Agent-Workspace)
- **Freshchat:** Native LINE channel (Admin > Channels > Line Messenger > Add Account). [Freshworks LINE integration article](https://crmsupport.freshworks.com/support/solutions/articles/50000004428-line-integration)
- **Chatwoot (open source):** The README lists website live chat, email, Facebook, Instagram, Twitter, WhatsApp, Telegram, Line and SMS. TikTok is not listed. [GitHub chatwoot/chatwoot](https://github.com/chatwoot/chatwoot)
- **Bitrix24 Open Channels:** Connects Facebook messages and comments, Instagram Business/Direct, Viber, Telegram and others. [Bitrix24 helpdesk](https://helpdesk.bitrix24.com/section/67933/); [Bitrix24 blog](https://www.bitrix24.com/about/blogs/contact-center/bitrix24-open-channels-now-work-with-instagram.php)
- **Wati:** WhatsApp, Instagram, Facebook Messenger, RCS, SMS, TikTok and web chat. No LINE was found. The multi-channel Team Inbox is Pro/Business only, though Aug 2026 notes extend multiple channels to Growth. [Wati support](https://support.wati.io/en/articles/11463002-how-to-use-the-multi-channel-team-inbox-in-wati); [Wati updates Aug 2026](https://feedback.wati.io/whats-cooking-at-wati---aug-2026-3iagKI)
- **Gorgias:** No native LINE integration found; its messaging integrations surfaced were SMS (Textline). [Gorgias Textline app](https://www.gorgias.com/apps/textline)
- **Pancake (pages.fm, now pancake.biz):** The pricing page shows WhatsApp API and marks Messenger and TikTok "in development". LINE is not mentioned, and subscription prices showed as placeholders ("0 đ"). [pancake.biz pricing](http://pancake.biz/pricing)

### Inferences
- For a Thai dealer, the realistic off-the-shelf shortlist that covers LINE OA + Messenger + IG with team routing is: respond.io, SleekFlow, Cresclab CAAC, Zaapi, Omnichat, Zendesk/Freshchat (heavier helpdesk style), and Chatwoot (self-host).
  - Zwiz, Page365, Pancake and Chatcone are oriented toward e-commerce order and slip handling more than lead routing.
- Pancake's page probably reflects a particular regional/WhatsApp variant. Pancake is widely used by Thai online sellers for FB/IG, but its LINE and TikTok support could not be confirmed from primary sources.
- TikTok DM via official API is the weakest channel everywhere. Expect "beta", region restrictions, or TikTok Shop-only chat rather than full TikTok DM parity.

### Gaps
- No confirmed native LINE support for Trengo, Kommo (amoCRM) or Bitrix24. Searches returned nothing on Kommo or amoCRM LINE pages. Bitrix24 docs surfaced only FB/IG/Viber/Telegram.
- Pancake LINE/TikTok status and Thai prices (pages fetched showed placeholders).
- Market-share data for these tools in Thailand: no reliable source found.

---

## 2. Per-platform features: routing, SLA, pipeline, AI, broadcast, API, reporting, compliance and pricing

### Takeaway
- **respond.io** has the most transparent pricing. It bills by Monthly Active Contacts (MAC) plus a plan fee with bundled seats ($79–$279/mo yearly; 5–10 users included). Its workflow-based assignment includes round-robin, least-open-contacts, online-only, a max-open cap, and a queue with a timeout of up to 7 days.
- **SleekFlow** is similar: MAC-based, 3–5 seats included, from HK$1,199/mo (≈US$154, ≈4,900 THB). Its strongest analytics publish first response, assignment-to-first-response and resolution metrics, but only on Premium.
- **Zaapi** is cheapest among the Thai-focused team tools ($59–$134/mo yearly, 3 seats), but chat assignment needs Pro and above.
- **Cresclab and Omnichat** are quote-only and annual-only.
- **Helpdesks** (Freshdesk Omni $29–$119/agent; Chatwoot cloud $19–$99/agent) charge per agent and have the most mature SLA and reporting.

### Cited Findings

#### respond.io (Malaysia HQ; strong in SEA)
- **Pricing (USD, fetched Oct 2026):** [respond.io pricing](https://respond.io/pricing)

  | Plan | Yearly billing | Monthly billing | Users included | Extra user |
  |---|---|---|---|---|
  | Starter | $79/mo ($948/yr) | $99 | 5 | $12/mo |
  | Growth | $159/mo ($1,908/yr) | $199 | 10 | $20/mo |
  | Advanced | $279/mo ($3,348/yr) | $349 | 10 | $24/mo |
  | Enterprise | custom | custom | unlimited | n/a |

  - Extra-user prices were matched to plans by order on the page and should be verified.
  - MAC tiers start at 1,000. Overage is $12 per 100 MACs (Growth) and $15 per 100 MACs (Advanced).
  - One third-party review lists Advanced at $199/mo rather than $279 (conflict). [eesel.ai](https://www.eesel.ai/blog/respond-io-pricing)
- **AI:** AI credits are 5,000 (Starter), 10,000 (Growth), 20,000 (Advanced) and 40,000 (Enterprise). Overage is $15 per 1,000 credits, capped at 200%. AI Agents are not on Starter (AI Prompt and AI Assist only) and are included on Growth and above under fair use. [respond.io pricing](https://respond.io/pricing)
- **Feature gating:** [respond.io pricing](https://respond.io/pricing)
  - Starter: team and custom inboxes, mobile app, basic reports, 2FA.
  - Growth adds: Broadcasts, Workflows, AI Agents, Advanced Reports, Zapier/Make, Developer API.
  - Advanced adds: masking of phone/email, multiple workspaces, HTTP requests in workflows, incoming/outgoing webhooks, SSO, custom channels.
  - HubSpot and Salesforce are listed under integrations, but the page does not say which plans include them.
- **Routing:** The "Assign To" workflow step offers four options: a specific user or AI Agent, a user in a specific Team, a user in the Workspace, or Unassign. [respond.io Assign To](https://respond.io/help/workflows/step-assign-to)
  - Logic options are "Assign to users round-robin" and "Assign to the user with least open Contacts".
  - Advanced settings are "Only assign to online users" and "Only assign to users with fewer than XX open contacts".
  - If nobody qualifies, the contact is queued. A timeout branch can be set up to 7 days (default 7 days) and can trigger fallback steps.
  - respond.io pairs these into two templates: "Round Robin + Online Only" (low-cost strategy) and "Least Open Contacts" (high-quality strategy). [respond.io assignment strategy](https://respond.io/help/automate-conversations/assignment-strategy-automatic-contact-distribution-load-balancing)
- **Reporting:** The roadmap lists advanced reports covering Conversation, Contacts, Users, Messages and Logs, including "Response Time: Total Average". [respond.io roadmap](https://roadmap.respond.io/feature-request/p/advance-analytics-reports-20)
  - A respond.io blog says the user report measures assigned conversations, messages sent and replied, and average resolution times. [respond.io blog (IT)](https://respond.io/it/blog/whatsapp-business-metrics)
- **LINE-specific limits:** [respond.io LINE help](https://respond.io/help/line/line-overview)
  - Images over 1 MB are converted to links. Audio and video up to 200 MB.
  - Receiving stickers works; sending stickers is "not supported for now". Flex messages and contact cards are not displayed.
  - Message status is "Sent" only (no delivered or read).
  - No LINE calls.
  - Broadcasts cannot use imported contacts, and are capped by both the LINE OA plan and the respond.io plan.
- **Compliance:** ISO 27001:2022 announced Sept 2023 [respond.io blog](https://respond.io/blog/iso-certification). Claims to be "fully GDPR compliant". [respond.io security (DE)](https://respond.io/de/security)

#### SleekFlow (Hong Kong HQ; regional pricing varies)
- **Pricing (HK page, HKD):** [SleekFlow HK pricing](https://sleekflow.io/en-hk/pricing)
  - **Pro:** HK$1,199/mo, or HK$14,388/yr. That is ≈US$154/mo, ≈4,900 THB.
  - **Premium:** HK$2,499/mo, or HK$29,988/yr. That is ≈US$320/mo, ≈10,200 THB.
  - **Enterprise:** custom.
  - Seats: 3 / 5 / custom. MACs start at 500 / 1,000.
  - Channels: 3 / 10 / unlimited. Active flows: 50 / 100 / 200.
  - Extra seat and MAC add-on prices are not published.
- **Pricing (other sources):**
  - US figures from one analysis (monthly / yearly): Pro $149 / $119; Pro AI $199 / $149; Premium $349 / $299; Premium AI $399 / $349. [eesel.ai](https://www.eesel.ai/blog/sleekflow-pricing)
  - hdmall quotes Pro AI at about 3,300 THB/mo with 500 MAC and 3 accounts. [hdmall](https://hdmall.co.th/jib-os/blog/7-line-oa-chat-systems-for-clinics/index.md)
  - Prices conflict across regions and sources.
- **Gating:** [SleekFlow HK pricing](https://sleekflow.io/en-hk/pricing)
  - Pro: omnichannel inbox, broadcast, Flow Builder, basic analytics, API access, Shopify, Google Sheets, Zapier, Make, FB Lead Ads.
  - Premium adds: role-based access control (RBAC), HTTP/webhook automations, HubSpot, Zoho, Meta Conversions API, TikTok Instant Forms, advanced analytics, multiple workspaces.
  - Enterprise adds: Salesforce, PII masking, conversation export, a dedicated CSM, enterprise SLAs.
  - AI: "AI Agents" (Pro), "AI agents with integrations" (Premium), "AI forward-deployed services" (Enterprise).
- **Routing:** Round-robin for new leads is built in Advanced Flow Builder. The trigger is "Incoming message received" (filterable by channel, working days and keywords). The flow assigns to a team, then the team's queue picks the agent ("Team – By queue"). Article updated Dec 2025 and Jul 2026. [SleekFlow help](https://help.sleekflow.io/en_US/round-robin-assignment-for-new-leads-in-advanced-flow-builder)
- **Reporting (Performance Analytics):** Premium and Enterprise only. [SleekFlow help](https://help.sleekflow.io/en_US/performance-analytics)
  - Response metrics: Average response time, Average first response time, Average first human response time, Average assignment-to-first-response time, Average assignment-to-first-human-response time.
  - Resolution metrics: Resolution rate, Average resolution time, Average assignment-to-resolution time, Average number of reassignments before resolution.
  - Working-hours toggle; date range up to 180 days; CSV export.
- **Compliance:** The Trust Center lists ISO/IEC 42001:2023, SOC 2 Type II, ISO/IEC 27001:2022, and GDPR compliance. [SleekFlow trust center](https://sleekflow.io/trust-center.md)
- **Automotive positioning:** "Chat-based CRM for car dealers, auto part retailers, and car rental companies", including chatbot test-drive booking (date, time, model) and day-before reminders. [SleekFlow automotive](https://sleekflow.io/solutions/automotive)

#### Crescendo Lab — MAAC (marketing automation) + CAAC (conversation/customer service)
- **Pricing:** No public prices. The plans are Growth, Scale, Professional and Enterprise (custom), with MAAC and CAAC bundled in each. [Cresclab TH pricing](https://www.cresclab.com/th/pricing)
  - Billing is based on Monthly Active Contacts (unique contacts with an interaction in the last 30 days), smoothed quarterly.
  - Credits are deducted per feature use, and usage limits can be set.
  - Professional adds e-commerce/catalog connection and an online revenue attribution report.
- **Routing:** [Cresclab commerce page](https://cresclab.com/en/channels/commerce)
  - Keyword-based routing to agents by branch, function or other criteria.
  - Per-agent QR codes: each agent has unique QR codes, and customers who add the LINE OA through one are "automatically assign[ed] to the agent owner".
  - Off-hours and department handoff rules.
- **AI:**
  - CAAC added a ChatGPT integration ("CAAC AI") for drafting replies in 2023. [Technode](https://technode.global/?p=38154)
  - The 2025–26 positioning talks about "specialized agents" for roles such as lead qualification. The source snippet is truncated. [cresclab.com](https://cresclab.com)

#### Omnichat (Hong Kong)
- Every tier shows "Quote"; no public price as of Aug 2026. Plans are annual only. Basic and Pro include 3 users, with paid extra seats; cost varies by "effective contacts and users". All of this comes from competitor imBee and is unverified with Omnichat. [imBee](https://id.imbee.io/omnichat-alternatives)

#### Zaapi (Thai-market focused; prices exclude 7% VAT)
- **Pricing (USD):** [Zaapi pricing](https://www.zaapi.com/pricing)

  | Plan | Monthly | Yearly (per month) | Seats included | Extra seat (monthly / yearly) |
  |---|---|---|---|---|
  | Basic | $79 | $59 | 3 | $35 / $26 |
  | Pro | $129 | $97 | 3 | $49 / $37 |
  | Advanced | $179 | $134 | 3 | $65 / $49 |

  - Yearly billing is a 25% discount. Prices exclude 7% VAT.
  - hdmall gives Basic as "from 1,875 THB/mo (annual)". [hdmall](https://hdmall.co.th/jib-os/blog/7-line-oa-chat-systems-for-clinics/index.md)
- **Features:** [Zaapi pricing](https://www.zaapi.com/pricing)
  - Assigning conversations to agents: Pro and Advanced only. Round-robin is not mentioned.
  - AI agent on all paid plans; AI tokens cost $40 per 1,000 messages.
  - LINE broadcast on all plans; WhatsApp broadcast on Pro and above.
  - Full analytics (conversation, agent, sales performance, label usage) and raw export on Pro and above.
  - HubSpot and Shopify from Pro.
  - Advanced only: OpenAPI + MCP, webhook/HTTP actions, auto-translate, full message history export.

#### Zwiz.ai (Thai)
- Price "Start at 500 Baht/Month". [zwiz.ai/en](https://www.zwiz.ai/en)
- hdmall lists a free plan, SME plans from hundreds of THB/mo, a booking bundle at 28,500 THB/yr and a loyalty bundle at 30,000 THB/yr. [hdmall](https://hdmall.co.th/jib-os/blog/7-line-oa-chat-systems-for-clinics/index.md)
- **Features:** [zwiz.ai/en](https://www.zwiz.ai/en)
  - Labels and statuses, customer notes, invoices from chat.
  - Bank slip verification (Thai banks and TrueMoney, fake-slip detection).
  - AI chat summarization, cross-platform customer matching, real-time translation, AI follow-ups until a sale or stop condition.
  - Reports exportable to Excel.
  - Per-staff chat assignment is not described.
  - Won Thailand MarTech Awards 2025 and 2026 (vendor claim).

#### Other Thai tools (hdmall 2026 roundup; prices "as stated", verify with vendor)
- OHO Chat Pro about 1,000 THB/mo (annual), with AI reply drafts and case management. [hdmall](https://hdmall.co.th/jib-os/blog/7-line-oa-chat-systems-for-clinics/index.md)
- KaoJai.ai Starter 590 THB/mo, with RAG answers from documents.
- klink.cloud Growth about 3,071 THB/mo, or pay-as-you-go at 6.9 THB per closed chat. AI agent "Kai".
- Botnoi about 0.12 THB per message.
- Jib OS 6,000 THB/mo (clinic vertical).
- **Chatcone:** the free plan is 3 users for 90 days. "Assigning chats to relevant staff" and "Receive/respond to chats from others" are not included in the free plan. Paid prices were not found. [MakeWebEasy Chatcone](https://www.makewebeasy.com/en/chatcone)

#### Global helpdesks
- **Freshdesk Omni / Freshchat:**
  - Freshdesk Omni costs about $29 (Growth), $69–79 (Pro) and $109–119 (Enterprise) per agent per month; sources conflict. [Ringly](https://www.ringly.io/blog/freshdesk-pricing); [Featurebase](https://www.featurebase.app/blog/freshdesk-pricing)
  - Freddy AI Copilot is $29 per agent per month (Pro and Enterprise). Freddy AI Agent is $100 per 1,000 sessions. [Chatarmin](https://chatarmin.com/en/blog/freshworks-pricing); [eesel](https://eesel.ai/blog/freshdesk-ai-omnichannel)
  - Freshchat standalone costs about $18–19 (Growth) and $47–49 (Pro) per agent per month. [Dupple](https://dupple.com/reviews/freshchat)
- **Chatwoot Cloud:** [Chatwoot pricing](https://www.chatwoot.com/pricing)

  | Plan | Price per agent/mo | Conversations | Captain AI credits | Notable additions |
  |---|---|---|---|---|
  | Hacker | $0 (≤2 agents) | 500/mo | none | live chat only |
  | Startups | $19 | unlimited (fair use) | 300 | all channels |
  | Business | $39 | unlimited (fair use) | 500 | Teams, automation rules, voice |
  | Enterprise | $99 | unlimited (fair use) | 800 | SSO, audit logs |

  - Extra AI credits cost $20 per 1,000.
  - SLA policies (first-response and resolution targets) are on Business and Enterprise. [Chatwoot solutions](https://www.chatwoot.com/solutions/teams/support)
- **Zendesk:** LINE is native in the Agent Workspace. Messages become tickets with business rules and Explore reporting. [Zendesk help](https://support.zendesk.com/hc/en-us/articles/4408836484378-Adding-Sunshine-Conversations-channels-to-the-Zendesk-Agent-Workspace)
- **Trengo:** Seat packages, not per-user pricing. Boost is €299/mo (annual; 10 users, 6,000 conversations/yr). Pro is €499/mo (20 users, 18,000 conversations/yr). AI costs €0.25–0.30 per AI conversation. [Chatarmin](https://chatarmin.com/en/blog/trengo-pricing)
- **Bitrix24:** Basic from $69/mo for 5 users (Capterra). WhatsApp via marketplace apps costs extra, e.g. Gupshup connector at $14/mo. [Capterra](https://www.capterra.com/p/113540/Bitrix24/reviews/2385562/); [Bitrix24 app](https://www.bitrix24.com/apps/app/cultiv.app8/)

### Inferences
- **Illustrative 10-salesperson team** (my calculations; channel/MAC overage excluded):
  - respond.io Growth yearly: $159/mo, 10 users included, ≈5,100 THB.
  - Zaapi Pro yearly: $97 + 7 × $37 = $356/mo, ≈11,400 THB + VAT.
  - SleekFlow Premium: HK$2,499 for 5 seats plus 5 add-on seats at an unpublished price, so more than ≈10,200 THB.
  - Chatwoot Cloud Business: 10 × $39 = $390/mo, ≈12,500 THB.
  - Freshdesk Omni Growth: 10 × $29 = $290/mo, ≈9,300 THB, before AI add-ons.
  - Chatwoot self-hosted Community: $0 license + server cost.
- **MAC billing:** respond.io, SleekFlow and Cresclab bill by Monthly Active Contacts. A used-car dealer with many low-intent ad leads would see costs scale with lead volume, not headcount.
- **Routing coverage:** The routing primitives a dealer needs (round-robin, online-only, capacity cap, queue + timeout fallback, per-salesperson QR ownership) all exist off-the-shelf:
  - respond.io (workflow Assign To);
  - SleekFlow (Flow Builder + team queue);
  - Cresclab CAAC (keyword routing + per-agent QR code ownership, which fits dealers giving each salesperson a personal LINE QR).
- **Gaps across vendors:**
  - "Auto-reassign if not answered in X minutes" is not documented as a one-click setting anywhere. In respond.io it would have to be built from workflow timeouts.
  - Shift-based routing beyond business hours and online status was not documented.
  - Pipeline stages and lifecycle exist in respond.io as "Lifecycle" (not verified in this round). Deal pipelines are typically delegated to HubSpot or Salesforce integrations, which are gated to higher tiers.
- **SleekFlow's metric set is a useful benchmark for an in-house build.** It splits first response from first human response, measures assignment-to-first-response, and counts reassignments before resolution.

### Gaps
- respond.io official definitions of its report metrics (docs not retrieved).
- SleekFlow Thai THB price list (TH pricing URL returned 404).
- Cresclab and Omnichat actual prices.
- Zendesk Suite 2026 prices (not fetched).
- Explicit SLA-breach timers for respond.io, SleekFlow and Zaapi.
- Mobile app parity details and data-export formats beyond those noted.
- Thai PDPA statements from any vendor: none surfaced. Only ISO, SOC 2 and GDPR claims were found for SleekFlow and respond.io.

---

## 3. Do these platforms capture staff replies made in native apps (LINE OA Manager / Meta Business Suite), or require replying in-platform?

### Takeaway
- **LINE: in practice every API-based inbox requires replying in-platform.** Vendor setup guides tell you to turn OA Manager chat mode off or set it to "Bot", and turn off auto-reply and greeting messages. Channel Talk warns that re-enabling chat mode disconnects the integration. LINE webhooks fire on user-sent events, so replies typed in OA Manager are not visible to the inbox. That last point is my inference; no vendor documents an OA Manager echo sync.
- **Facebook/IG: capture is technically possible** through Meta's `message_echoes` webhook, which flags Page Inbox-originated messages via `app_id`, but it is vendor-dependent. Some tools sync echoes and some explicitly don't.

### Cited Findings
- Channel Talk's required settings are "Chat: Off, Webhooks: On, Auto-response messages: Off". It also says: [Channel Talk LINE doc](https://docs.channel.io/help/en/articles/Line-1af80f96)
  - "LINE Official Account Manager's chat mode will be deactivated after integration"
  - "the integration will be disconnected if you activate the chat mode"
  - "It is difficult to retrieve previous chat data"
  - Agent-specific profiles are not applied.
- Freshchat recommends setting LINE response mode to Bot, disabling the greeting message and auto response, and enabling webhooks. [Freshworks LINE integration](https://crmsupport.freshworks.com/support/solutions/articles/50000004428-line-integration)
- Chatwoot says to turn off LINE auto-reply so Chatwoot can handle responses. [Chatwoot LINE setup](https://developers.chatwoot.com/contributing-guide/line-channel-setup)
- Zendesk and Qiscus say chat mode disables the webhook and that the response mode must be Bot. [Zendesk support](https://support.zendesk.com/hc/en-us/articles/4408826465690-LINE-integration-stops-receiving-messages); [Qiscus](https://support.qiscus.com/hc/en-us/articles/7250817806745-Failed-Integrating-LINE-to-Omnichannel)
- respond.io's LINE docs do not address OA Manager echo or native-app replies. [respond.io LINE help](https://respond.io/help/line/line-overview)
- Meta's `message_echoes` webhook fires when the Page sends a message (`is_echo`), and `app_id` returns the Page inbox app ID when sent from the Facebook Page inbox. [Meta docs](https://developers.facebook.com/documentation/business-messaging/messenger-platform/webhooks/webhook-events/message-echoes.md)
- Vendors differ on echo sync:
  - Enchant: "not synchronizing outbound messages sent directly from Meta interfaces". [Enchant](https://help.enchant.com/article/163/managing-facebook-messenger-conversations-in-enchant)
  - Amio documents that echo can record messages sent "directly from Facebook Page administration". [Amio](https://docs.amio.io/reference/facebook-messeger-webhooks-message-echo)
  - Front says replies sync instantly with Messenger. [Front](https://front.com/integrations/facebook)

### Inferences
- The "staff reply in native app" problem is structural on LINE, not a weakness of any one vendor. Off-the-shelf platforms solve it by policy: mandate in-platform replies, enforced by disabling OA Manager chat. They do not solve it technically.
  - Caveat: newer OA Manager versions may allow chat and webhook simultaneously. This conflicts with the Zendesk/Qiscus/Channel Talk guidance, and the LINE-API researcher should confirm.
  - Even if both are on, OA Manager replies still would not reach the webhook.
- On Facebook, an in-house inbox can capture Business Suite replies by subscribing to `message_echoes` and attributing them by `app_id`. Before buying, ask each vendor whether it ingests echoes; this was not confirmed for respond.io, SleekFlow or Zaapi.

### Gaps
- No documentation found from respond.io, SleekFlow, Zaapi, Cresclab or Zwiz on whether they ingest Messenger or IG echoes, or on any LINE OA Manager reply sync.
- Whether LINE's current OA Manager allows chat mode and webhook concurrently in Thailand: there are conflicting claims, deferred to the LINE-API researcher.

---

## 4. Open-source / self-hosted options (Chatwoot etc.): LINE support, and viability as a base for a custom build

### Takeaway
Chatwoot is the clear open-source candidate:
- MIT-licensed core, 37.7k GitHub stars.
- Native LINE inbox via the Messaging API webhook (`/webhooks/line/<channel-id>`), plus Facebook, IG, WhatsApp, Telegram, email, SMS and web chat.
- Auto-assignment by availability; conversation, agent, inbox, label, team and CSAT reports.
- Captain AI.

The pro-grade features (SLA, agent capacity, audit logs, white-label) sit in the proprietary Enterprise edition, licensed per agent. TikTok is not supported.

### Cited Findings
- **Core:** Channels are website live chat, email, Facebook, Instagram, Twitter, WhatsApp, Telegram, Line and SMS. MIT License; 37.7k stars. Auto-assignment by agent availability. Conversation, agent, inbox, label, team and CSAT reports, downloadable. Captain AI agent. [GitHub](https://github.com/chatwoot/chatwoot)
- **LINE setup:** Settings → Inboxes → Add Inbox → Line; enter the Channel ID, Secret and Token. Set the webhook to `https://<host>/webhooks/line/<channel-id>` and turn off LINE auto-reply. The doc does not list supported LINE message types (Flex, LIFF, etc.). [Chatwoot LINE setup](https://developers.chatwoot.com/contributing-guide/line-channel-setup)
- **Enterprise Edition:** A proprietary build from the same repo. It includes white-labeling, SLA Management, Audit Logs and Agent Capacity Management. [Chatwoot EE docs](https://developers.chatwoot.com/self-hosted/enterprise-edition)
  - Agent capacity "enhances Auto Assignment", using round-robin with per-agent limits set in Inbox Settings. [Chatwoot agent capacity](https://www.chatwoot.com/hc/user-guide/articles/1741998212-agent-capacity)
  - Self-hosted licensing is per agent per month, starting at $19, bought through Stripe from Super Admin. There is no instance license. [Chatwoot EE docs](https://developers.chatwoot.com/self-hosted/enterprise-edition)
  - A third-party guide lists self-hosted Enterprise at $99 per agent per month (annual) and Community at $0 with no Captain AI, voice or SSO. This is secondhand. [eesel](https://www.eesel.ai/blog/chatwoot-pricing)

### Inferences
- Chatwoot could serve as a base, or as a reference architecture, for the dealer's in-house inbox. It is a Rails + Postgres + Redis stack with a public API and webhooks, already has LINE, FB and IG inboxes, round-robin assignment and reports.
- The dealer would still need to build:
  - Thai-specific lead fields and the used-car pipeline;
  - timed auto-reassign/SLA escalation (Enterprise-only, or custom code);
  - LINE Flex/rich-menu handling;
  - TikTok;
  - echo capture for Business Suite replies.
- The MIT core allows forking, but SLA and capacity features live in the proprietary `enterprise` folder. Reimplementing them avoids the license fee but adds maintenance.

### Gaps
- No other open-source LINE-capable inbox was researched in depth this round; Tiledesk and Papercups were only mentioned in passing in search results.
- Chatwoot's handling of LINE stickers, images and Flex, and of Messenger echoes, is undocumented.
- Chatwoot's latest release version and date were not retrieved.

---

## 5. Case studies: Thai/SEA businesses (ideally automotive or high-ticket) with measured results

### Takeaway
No verified Thai automotive case study with measured results was found. The closest are:
- respond.io × Srikandi, an Indonesian Mitsubishi dealer with 47 branches;
- SleekFlow × BateriHub, a Malaysian auto-battery retailer with 130+ branches;
- Ourgreenfish, which pitches LINE OA + HubSpot for Thai EV dealers without numbers.

All results are vendor-reported.

### Cited Findings
- **respond.io × Srikandi** (Mitsubishi dealer, Indonesia, 47 branches; WhatsApp, not LINE). [respond.io case study](https://respond.io/customers/how-srikandi-streamlined-communication-for-47-branches-and-accelerated-revenue-growth)
  - Problem: agents used personal numbers.
  - Solution: workflows route leads to the preferred branch and agent.
  - Reported results: +23% revenue, +125% conversations, 88% of conversations auto-routed to the right branch and agent, and 20,100 broadcasts in 5 months.
- **SleekFlow × BateriHub** (Malaysia, 130+ branches, auto batteries). [SleekFlow customer story](https://sleekflow.io/de-de/customer-stories/baterihub)
  - Reported results: 17x faster response, under 1% spam leads, +22% conversions in 3 months.
  - The original pain point was lead attribution from ads.
- **Ourgreenfish** (Thai agency): LINE OA → HubSpot CRM for Thai EV dealers. [Ourgreenfish](https://ourgreenfish.com/en/ev-market-solutions-line-crm-for-thai-dealers-ourgreenfish)
  - Features: territory-based routing to sales reps, keyword or menu routing to service, a pipeline stage per lead (browsing → test drive → ready to buy), and 1-day test-drive reminders.
  - No named clients and no numbers. It says success is measured by an "increase in test drive appointments and shorter sales closing times".
- **Crescendo Lab** serves 500+ brands including automotive, but no automotive brand is named. [CakeResume profile](https://www.cakeresume.com/pages/crescendo-lab?locale=ko)

### Inferences
- The Srikandi pattern (multi-branch dealer moving staff off personal phones, plus auto-routing by branch) is the closest analogue to a Thai used-car dealer. Its main measurable wins were routing coverage and conversation volume, not AI.
- The dealer's in-house system can benchmark against these headline metrics:
  - percentage of chats auto-assigned;
  - first response time;
  - conversion from lead to test drive or visit.

### Gaps
- No verified Thai automotive or high-ticket case study from respond.io, SleekFlow, Cresclab, Zaapi or Zwiz.
- A search snippet claims Muang Thai Life Insurance uses Crescendo Lab on a LINE OA with over 40M followers, with "AI Smart Sending" open rates up to 75%. The underlying Thai article (likely posttoday.com/ai-today/726615 or brandbuffet.in.th) was not opened, so this is unverified.
- No independent (non-vendor) measurement of any of these results.
