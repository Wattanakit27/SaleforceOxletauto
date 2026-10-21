# Global CRM Landscape: How CRM Works and Which Platforms Exist (state as of Oct 2026)

Research date: 2026-10-12. All prices are USD per user per month unless stated otherwise. Vendor pricing pages read in October 2026 are marked "official". Most other price figures come from third-party review and pricing blogs, and they often disagree with each other. Conflicts are flagged inline.

---

## Q1. What are the standard CRM building blocks, data model and workflows?

### Takeaway
Every mainstream CRM uses the same core objects and flow. **Lead** (unqualified person or inquiry) is converted into **Contact** (person) + **Account** (company or household) + optional **Opportunity/Deal**. The deal then moves through **pipeline stages**, with **activities/tasks** logged against it. Around that core sit lead **scoring → routing/assignment (rules, queues, round-robin) → response SLA with escalation**, then reporting and forecasting. Customer data platforms (CDPs), omnichannel inboxes and marketing automation are add-on layers. Speed-to-lead research (5-minute and 1-hour windows) is the main justification for routing and SLA rules.

### Cited Findings
**Data model: lead → contact/account/opportunity**
- In Salesforce, once a salesperson judges a lead ready to proceed, the lead is "converted" into an Account (the company the lead works for, or a household), a Contact, and optionally an Opportunity. After conversion the lead is locked and visible only to users with special permissions. — [Trailblazer Community](https://trailhead.salesforce.com/trailblazer-community/feed/0D54S00000A8KppSAF); [SalesforceTutorial guide summarizing Trailhead](https://www.salesforcetutorial.com/?p=6813)
- The conversion screen has Account, Contact and Opportunity sections. Each can create a new record or match an existing one, for example a new lead from a company that is already a customer attaches to that existing Account. Creating the Opportunity is optional ("Do not create a new opportunity upon conversion"). The "Converted Status" values are defined by the admin. — [Trailhead: Track Prospects with Salesforce Leads](https://trailhead.salesforce.com/de/content/learn/modules/prospect-tracking-with-salesforce-leads-quick-look/track-prospects-with-salesforce-leads); [SalesforceTutorial](https://www.salesforcetutorial.com/?p=6813)
- Data from the lead only fills blank account fields and does not overwrite existing account data. Later leads from the same company become new opportunities under the same account. — [SalesforceTutorial](https://www.salesforcetutorial.com/?p=6813) (Trailhead-adjacent sources, some community posts dated 2010–2021)

**Lead routing / assignment rules / round-robin**
- Salesforce standard **assignment rules** run once, when the lead is created, and are deterministic: the lead goes to the rep the rule matches. They cannot check rep availability, so a lead assigned to a rep on leave sits until that rep returns. For first-available or round-robin models the usual alternative is **queues**, from which any available rep can claim the lead. — [Revenue.io](https://www.revenue.io/blog/how-to-manage-inbound-leads-inside-salesforce-without-losing-speed-to-lead)
- The same source recommends **scoring/tiering leads before routing**, so the routing step knows which response SLA to apply. — [Revenue.io](https://www.revenue.io/blog/how-to-manage-inbound-leads-inside-salesforce-without-losing-speed-to-lead)
- **Round-robin** hands leads out equally among available reps in rotating order. Its benefits are fairness and preventing cherry-picking. Basic round-robin works best for homogeneous teams of about 3–15 reps and breaks down at scale or when lead quality varies a lot by source. **Weighted, availability-aware and capacity-based** variants fix most of those failure modes. — [LeanData](https://leandata.com/blog/round-robins-role-in-effective-lead-management); [Rework](https://resources.rework.com/vi/libraries/lead-management/lead-routing)
- A typical routing pipeline runs: lead capture → data enrichment → rule-based routing → assignment → fallback/escalation. Track **time from lead creation to first touch** and keep an **audit trail** of why each lead went to a given rep. — [Kilo lead-router cookbook](https://kilo.ai/kiloclaw/bytes/lead-router); [Reform real-time lead assignment guide](https://www.reform.app/blog/ultimate-real-time-lead-assignment-guide)
- Best practice is to auto-escalate to a manager when an SLA is missed, and to report weekly on lead volume per rep, average response time, SLA compliance rate and misrouted leads. — [Nimble](https://www.nimble.com/blog/best-practices-for-lead-assignment-in-crm/)

**Speed-to-lead evidence (why SLAs exist)**
- MIT/InsideSales.com work from 2007, covering 15,000+ leads, is the most-cited figure: a rep who calls within **5 minutes is 21× more likely to qualify** the lead than one who calls at 30 minutes. — summarized by [Nimble](https://www.nimble.com/blog/best-practices-for-lead-assignment-in-crm/) / [LeanData](https://leandata.com/blog/round-robins-role-in-effective-lead-management)
- A Harvard Business Review study of 2,241 US companies found that firms responding **within 1 hour were ~7× more likely to qualify** the lead than firms that waited longer, and that **23% of companies never responded at all**. — summarized in the same lead-routing sources above. (The original is HBR's "The Short Life of Online Sales Leads", 2011. I did not fetch the original.)
- Vendor-sourced claims such as "+391% conversion if you respond within 1 minute" (attributed to Velocify) should be treated as directional only. — [Nimble](https://www.nimble.com/blog/best-practices-for-lead-assignment-in-crm/)

**CRM vs CDP (customer data platform)**
- A CRM mainly holds first-party data on *known* customers and prospects to support sales and service. A CDP holds both *anonymous and known* data from many sources, unifies it into a single "Customer 360" profile, and pushes it to downstream tools for activation. A CDP often ingests the CRM as one of its sources. — [RudderStack](https://rudderstack.com/blog/customer-data-platform-vs-crm); [Twilio](https://www.twilio.com/en-us/blog/cdp-vs-crm-whats-the-difference)
- Positioning differs by vendor. Salesforce Data Cloud is a separately licensed CDP; a HubSpot blog claims it needs 3–6 months of implementation and costs from ~$108,000/yr for 50 users. HubSpot says its data unification and segmentation are native (Data Hub). This is vendor marketing from a competitor. — [HubSpot blog (ES)](https://blog.hubspot.es/marketing/salesforce-data-cloud-vs-hubspot-data-hub)

**Omnichannel inbox, AI assist and forecasting as standard modules (from vendor feature lists)**
- Freshworks' Freddy AI Agent handles customer conversations across email, chat, WhatsApp and social channels. Freddy Copilot drafts replies, summarizes tickets and analyzes sentiment. — [eesel.ai guide to Freddy AI (2026)](https://eesel.ai/blog/freddy-ai)
- Dynamics 365 Sales Enterprise includes opportunity summaries, email and meeting assistance and natural-language insights. Premium adds "Sales Insights", AI-powered recommended actions (next-best-action) and AI data enrichment. — [Microsoft official pricing](https://www.microsoft.com/en-us/dynamics-365/products/sales/pricing)
- Pipedrive's AI Sales Assistant predicts which deals are likely to close, highlights risky opportunities and suggests next actions (deal-level forecasting and risk). — [Pipedrive AI KB](https://support.pipedrive.com/en/article/pipedrive-ai); [review summarized via search](https://modernoutreach.beehiiv.com/p/pipedrive-review)

### Inferences
- The universal workflow behind every product below is: **capture (web form / chat / ads / walk-in) → dedupe & enrich → score → route (rules, territory, round-robin, queue) → first-contact SLA timer → qualify → convert to deal → move through stages (e.g., New → Contacted → Qualified → Proposal/Test-drive → Negotiation → Won/Lost) → log every call, message and task → report and forecast (pipeline value × stage probability).** Stage names are configurable in every CRM; the stage list in this bullet is an illustrative common pattern, not quoted from one vendor.
- "Lead" vs "Opportunity/Deal" is the most important concept to explain to a Thai owner. A lead is an unverified inquiry. A deal is a qualified buying intent with a value and stage. Mixing the two inflates the pipeline.
- Round-robin alone is not enough. Mature setups combine it with availability checks (leave and shifts), weighting (senior vs junior reps), and SLA escalation to a manager.

### Gaps
- I did not fetch a neutral, vendor-agnostic reference model of CRM objects. The data model above is Salesforce-centric, though HubSpot (Contacts/Companies/Deals/Tickets) and Zoho (Leads/Contacts/Accounts/Deals) follow the same pattern. I did not verify their object names in this session.
- I did not verify the original MIT/InsideSales and HBR studies directly; only secondary summaries were read.
- No standard benchmark was found for pipeline stage conversion rates or typical lead-scoring models (point-based vs predictive).

---

## Q2. Who are the market leaders, what is their market share, and what does each cost per user per month?

### Takeaway
Salesforce dominates revenue share (IDC: **20.0% of 2025 CRM revenue**, #1 for the 13th year). Oracle (~4.1%) and Microsoft (~4.0%) are distant #2/#3. HubSpot leads by customer count (~299k paying customers) rather than revenue. Gartner's 2025 SFA Magic Quadrant Leaders are Salesforce, Microsoft and Oracle. Prices range from free (HubSpot, Zoho for 3 users, Bitrix24) to ~$9–25 for SME tools (Freshsales, Zoho, Pipedrive, monday, Kommo) and $100–550 for enterprise suites. Many vendors restructured pricing in 2025–2026 around AI credits.

### Cited Findings
**Market share and analyst rankings**
- IDC Worldwide Semiannual Software Tracker (April 2026): Salesforce held **20.0%** of the 2025 CRM market, #1 for the 13th consecutive year. Salesforce was also #1 in Sales (14th year), Customer Service (13th year) and Marketing (7th year). — [Salesforce newsroom, 4 Jun 2026](https://www.salesforce.com/news/stories/idc-crm-market-share-ranking-2026/) (vendor citing IDC)
- In the same IDC data, **Oracle is #2 at 4.1%** and **Microsoft #3 at 4.0%**, down from 5.2%. Salesforce slipped from 20.7% (2024) to 20.0% (2025), which one analysis attributes to the market growing faster than Salesforce. — [CX Foundation](https://cxfoundation.com/news/salesforce-extends-crm-market-lead); [CRMSwitch](https://crmswitch.com/crm-industry/crm-market-share/)
- IDC's first "Agent Build and Deploy" market share (H2 2025) put Salesforce at **#2 with 17.5%**. — [Salesforce newsroom](https://www.salesforce.com/news/stories/idc-crm-market-share-ranking-2026/) (the #1 vendor is not named in that article)
- HubSpot's revenue share estimates diverge: ~3.0% (derived from IDC) vs 5–6% (other estimates). IDC does not publish exact figures below the top three. HubSpot reported **299,458 paying customers as of 31 Mar 2026 (+16% YoY)**, so it leads by customer count, not revenue. — [Resonate HQ](https://www.resonatehq.com/blog/hubspot-market-share); [CommandLinux stats](https://commandlinux.com/statistics/crm-market-share-salesforce-hubspot-zoho/)
- The overall CRM category size is ~US$128 bn (a "Gartner estimate" quoted by a stats aggregator, not verified against Gartner). — [Digital Applied CRM statistics 2026](https://www.digitalapplied.com/blog/crm-statistics-2026-market-adoption-roi-data-reference)
- Gartner Magic Quadrant for Sales Force Automation Platforms, 21 Jul 2025: 13 vendors evaluated, and the **Leaders were Salesforce, Microsoft and Oracle**, unchanged from 2024. — [CX Today](https://www.cxtoday.com/crm/gartner-magic-quadrant-for-sales-force-automation-platforms-sfa-2025-the-rundown/). Oracle says this is its 9th consecutive year as a Leader. — [Oracle](https://www.oracle.com/cx/sales/sales-force-automation/gartner-mq/). Zoho was reportedly placed as a Visionary in the same MQ (aggregator claim, not verified).

**Pricing by vendor (per user/month unless noted)**

| Vendor / product | Tiers & list price | Notes / source |
|---|---|---|
| **Salesforce Sales Cloud** (renamed **Agentforce Sales** at Dreamforce 2025) | Free Suite $0; **Starter Suite $25** (monthly or annual); **Pro Suite $100**; **Core $195**; **Advanced $395**; **Max $550** (annual billing for Pro and above) | Official page, Oct 2026: Max includes Agentforce for Sales, "Agentforce Coworker" and 2.75M Flex Credits/org/yr. **Agentforce for Sales add-on from $125/user/mo.** — [Salesforce pricing](https://www.salesforce.com/sales/pricing/); rename — [SalesforceBen](https://salesforceben.com/salesforce-rebrands-sales-cloud-to-agentforce-sales-at-dreamforce-25) |
| Salesforce (legacy editions, for context) | Enterprise $165–175; Unlimited $330–350 | A **September 2026 restructure** reportedly folded Enterprise into Core ($195), Unlimited into Advanced, and Agentforce 1 into Max. — [Valintry360](https://valintry360.com/blogs/salesforce-agentforce-pricing/); [G2](https://www.g2.com/products/agentforce-sales-formerly-salesforce-sales-cloud/pricing); [SaaSworthy](https://www.saasworthy.com/blog/salesforce-pricing) (sources conflict on exact legacy prices) |
| Salesforce Agentforce consumption | Flex Credits $500 per 100,000; legacy $2 per conversation; Agentforce User License $5/user/mo (needs Flex Credits) | — [Supered](https://www.supered.io/blog/agentforce-pricing/); [Oliv.ai](https://www.oliv.ai/blog/salesforce-agentforce-pricing-breakdown) (one analysis puts realistic all-in cost at "$125–$650 per user") |
| **Microsoft Dynamics 365 Sales** | **Professional $65; Enterprise $105; Premium $150** (all paid yearly); Relationship Sales = contact sales, 10-seat minimum, includes LinkedIn Sales Navigator | Official, Oct 2026. Premium includes **1,000 Copilot Credits/user/mo** (tenant-pooled, no rollover). Pay-as-you-go credits need an Azure subscription; pre-purchase saves up to 20%. — [Microsoft pricing](https://www.microsoft.com/en-us/dynamics-365/products/sales/pricing) |
| Microsoft 365 Copilot (incl. "Sales agent") | $30/user/mo | Separate from the Dynamics agents. — [AI CX News](https://www.aicxonews.com/posts/what-microsoft-copilot-includes-for-sales-teams-2026/) |
| **HubSpot Sales Hub** | Free CRM; **Starter ~$15–20/seat**; **Professional ~$90–100/seat + $1,500 one-time onboarding**; **Enterprise ~$150/seat + $3,500 onboarding** | Third-party figures; sources conflict and the official page could not be parsed. Included HubSpot Credits/mo: **Starter 500, Pro 3,000, Enterprise 5,000**; overage $0.01/credit; no rollover. — [Supered](https://www.supered.io/blog/hubspot-breeze-ai/); [Vantagepoint](https://vantagepoint.io/blog/hs/hubspot-breeze-prospecting-agent-credits-pricing-guide); [Sliq](https://getsliq.com/blog/hubspot-breeze-prospecting-agent-pricing) |
| **Zoho CRM** | **Free (3 users)**; **Standard $14** annual / $20 monthly; **Professional $23/$35**; **Enterprise $40/$50**; **Ultimate $52/$65**. Bigin (simple CRM) from $7; Zoho One suite $37/employee | Zia AI needs Enterprise or higher; Agent Studio (custom agents) needs Ultimate (sources partly conflict). — [SpotSaaS](https://www.spotsaas.com/blog/zoho-crm-pricing); [Layer3Labs](https://www.layer3labs.io/guides/zoho-crm-pricing); [CodeStringers](https://www.codestringers.com/articles/zoho-crm-pricing) |
| **Pipedrive** | **$14–$79/seat** annual ($24–$99 monthly) across 4 plans (Lite → top tier) | Automations and sequences start at the Growth tier. Add-ons (campaigns, lead gen) add cost. — [Axis Consulting](https://axisconsulting.io/pipedrive-pricing-plans/); [SaaS CRM Review](https://saascrmreview.com/pipedrive-vs-freshsales/) |
| **Freshworks Freshsales** | **Growth $9**; **Pro $39**; **Enterprise $59** (annual) | Entry price disputed ($7 / $9 / $15 monthly). Built-in phone on paid plans. — [SaaS CRM Review](https://saascrmreview.com/pipedrive-vs-freshsales/); [CRM pricing comparison](https://saasmaste.com/best/crm-pricing-comparison/) |
| **monday CRM** | Basic **$12/seat**; Pro **$28/seat** | **3-seat minimum** on all plans. Basic has no automations, email sync or integrations, so one reviewer calls Pro the functional starting tier. — [Conduyt](https://conduyt.com/resources/crm-pricing-comparison-2026/); [Sonary](https://sonary.com/content/pipedrive-vs-monday-crm/) |
| **Bitrix24** | **Flat price per team pack, not per seat.** Free plan; Basic (5 users) $49–69/mo; Standard (50 users) $99–144/mo; Professional (100 users) $199–289/mo; Enterprise $499–579/mo | Sources disagree considerably, so verify on bitrix24.com. — [Capterra](https://www.capterra.com/p/113540/Bitrix24/); [Findstack](https://findstack.com/compare/bitrix24-vs-kommo-formerly-amocrm); [ITQlick](https://www.itqlick.com/bitrix24/pricing) |
| **Kommo (ex-amoCRM)** | Official 2026 guide: **Base $25, Advanced $35, Pro $45**, Enterprise custom | No permanent free plan; 14-day trial. Older third-party listings show $15/$25/$45 (likely annual or older prices). — [Kommo pricing guide 2026](https://www.kommo.com/blog/kommo-pricing/); [Capterra](https://www.capterra.com/p/120048/Kommo/) |
| **Oracle (Fusion Sales/CX)**, **SAP (Sales Cloud/CX)** | No reliable public per-user price found | Both are enterprise-focused. Oracle is a Gartner SFA Leader. Mordor lists Oracle and SAP among Thailand's "industry leaders". |

**Positioning summary (from sources above)**
- Salesforce: broadest enterprise platform and most expensive. AI is now bundled into the top editions plus consumption credits. — [Salesforce pricing](https://www.salesforce.com/sales/pricing/)
- Microsoft: tight integration with Microsoft 365, Teams and LinkedIn; agents are paid via Copilot Credits. — [Microsoft pricing](https://www.microsoft.com/en-us/dynamics-365/products/sales/pricing)
- HubSpot: freemium entry and a combined marketing + sales + service platform; leads by customer count. — [Resonate HQ](https://www.resonatehq.com/blog/hubspot-market-share)
- Zoho: lowest-cost full suite, with an in-house LLM (see Q3). — [SpotSaaS](https://www.spotsaas.com/blog/zoho-crm-pricing)
- Pipedrive: pipeline-first and simple for sales teams. Freshsales: cheapest per-seat with a built-in phone. monday CRM: a work-management tool with CRM on top, so its pipeline features can be lighter. — [SaaS CRM Review](https://saascrmreview.com/pipedrive-vs-freshsales/); [Sonary](https://sonary.com/content/pipedrive-vs-monday-crm/)
- Bitrix24: flat-rate all-in-one (CRM + tasks + chat) with a free tier, cheapest for teams that grow in headcount. Kommo: per-seat, messenger-centric. — [Findstack](https://findstack.com/compare/bitrix24-vs-kommo-formerly-amocrm)

### Inferences
- Illustrative monthly list cost for **10 sales users** (my arithmetic from the prices above, annual billing, excluding add-ons and taxes): Freshsales Growth ≈ $90; Bitrix24 Standard (flat) ≈ $99–144; Zoho Professional ≈ $230; Kommo Advanced ≈ $350; Pipedrive ≈ $140–790; HubSpot Sales Pro ≈ $900–1,000 + $1,500 one-off; Salesforce Pro Suite ≈ $1,000 (Core ≈ $1,950); Dynamics Sales Enterprise ≈ $1,050. The spread is more than 10×.
- The market is split in two. Enterprise suites (Salesforce, Microsoft, Oracle, SAP) hold most of the revenue. SME-focused vendors (HubSpot, Zoho, Pipedrive, Freshworks, monday, Bitrix24, Kommo) hold most of the customer count.
- 2025–2026 pricing is moving from pure per-seat to **seat + AI credits / outcome-based** pricing (Salesforce Flex Credits, Microsoft Copilot Credits, HubSpot Credits, Zoho AI credits). Budget forecasting is now harder.

### Gaps
- The full IDC table (ranks below #3) and Gartner's own MQ report were not accessible. HubSpot, Zoho and SAP shares are unverified estimates.
- HubSpot's official Sales Hub price page could not be parsed, so HubSpot seat prices come from third-party sources.
- No reliable public list prices were found for Oracle Fusion Sales or SAP Sales Cloud.
- Bitrix24 prices conflict significantly across sources, and regional (Thai baht) pricing was not checked for any vendor.

---

## Q3. What AI/agent features shipped in 2025–2026, and what do they actually do?

### Takeaway
2025–2026 was the shift from "AI copilot" (summaries, email drafts) to **autonomous agents**: AI SDRs that engage and qualify inbound leads 24/7 and book meetings, qualification and research agents, deal-coaching agents, and customer-service agents that resolve conversations. All major vendors now charge for them via credits or outcomes. Vendor performance claims are largely unverified.

### Cited Findings
**Salesforce Agentforce**
- **Agentforce SDR agent** (lead nurturing): engages inbound leads 24/7 across web chat, email and SMS; qualifies them against ICP criteria; answers product questions; books meetings on rep calendars; and hands off to a human with full conversation context. — [Jitendra Zaa analysis](https://www.jitendrazaa.com/blog/salesforce/salesforce-agentforce-out-of-box-agents-complete-analysis/); [Trailhead: Agentforce SDR](https://trailhead.salesforce.com/ko/content/learn/modules/agentforce-sdr-setup-and-customization/get-to-know-agentforce-sdr)
- **Agentforce Sales Coach**: role-plays with sellers and gives personalized feedback based on the company's selling methodology and qualification checklists. It also analyzes deals, suggests next-best actions and flags risk. Both agents were announced at Dreamforce 2024 and reported GA in October 2024. — [No Jitter](https://www.nojitter.com/virtual-agents/no-jitter-midroll-salesforce-launches-ai-agents-for-sales); [Geekflare](https://geekflare.com/news/salesforce-new-ai-agents-are-quietly-taking-over-sales-teams)
- **Dreamforce 2025 (Oct 2025): Agentforce 360** platform, with a conversational agent builder, "hybrid reasoning" for control and accuracy, and voice. Sales Cloud was rebranded **Agentforce Sales**, covering prospecting → qualification → meeting-setting. New prospecting and enrichment capabilities were planned GA for February 2026, backed by the Bluebirds acquisition and ZoomInfo/6sense partnerships. — [SalesforceBen](https://salesforceben.com/salesforce-rebrands-sales-cloud-to-agentforce-sales-at-dreamforce-25); [CXM World](https://cxm.world/digital-experience/dreamforce-2025-delivers-agentforce-360-and-new-slack/); [Futurum](https://futurumgroup.com/insights/dreamforce-announcements-focus-on-ai-agentforce-and-cloud-enhancements/)
- The 2026 official pricing page lists "Agentforce Coworker" plus Agentforce for Sales in the Max edition, and AI available as an add-on from the Core edition up. — [Salesforce pricing](https://www.salesforce.com/sales/pricing/)
- In Thailand, IEAT and Bumrungrad International Hospital adopted Agentforce in April 2026. — [Mordor Intelligence](https://www.mordorintelligence.com/industry-reports/thailand-crm-market)

**HubSpot Breeze (as of an article dated 2 Oct 2026)**
- **Breeze Assistant**: a chat helper inside HubSpot, included with every Core Seat. It draws on shared context such as brand voice, products, ICPs and personas. — [Supered](https://www.supered.io/blog/hubspot-breeze-ai/)
- **Agent Hub** (arrived summer 2026) manages the agents. Credit costs per action:
  - **Prospecting Agent**: researches and recommends outreach per lead, 100 credits (= **$1 per qualified lead**).
  - **Customer Agent**: resolves a text conversation, 50 credits per resolution.
  - **Data Agent**: answers a prompt about a record, 10 credits.
  - **Nurture Agent**: personalized email, 10 credits (beta).
  - **Content Agent**: 1,000 credits per piece (beta).
  - **Knowledge Base Agent**: 200 credits per article (beta).
  - **Revenue Agent**: collections outreach per invoice, 500 credits (beta).
  - **Deal progression**: reads call transcripts and emails, then proposes deal-property and next-step updates (Sales/Service Hub Pro or Enterprise).
  - **Custom agents / agentic workflows**: Pro or Enterprise.
  — [Supered](https://www.supered.io/blog/hubspot-breeze-ai/)
- HubSpot switched the Prospecting and Customer agents to **outcome-based ("pay when done") pricing on 14 April 2026**. Before, it charged per enrolled contact. — [Resolve247](https://resolve247.ai/blog/hubspot-breeze-pricing-change/); [Vantagepoint](https://vantagepoint.io/blog/hs/hubspot-breeze-prospecting-agent-credits-pricing-guide)
- Agents that were free during the Breeze Studio beta now consume credits (MarTech roundup, 21 Aug 2026, as cited by Supered). — [Supered](https://www.supered.io/blog/hubspot-breeze-ai/)
- One reviewer estimates a realistic cost for 10 reps on Sales Hub Pro at ~$1,000 base plus $300–900/mo in credits. — [Sliq](https://getsliq.com/blog/hubspot-breeze-prospecting-agent-pricing)

**Microsoft Dynamics 365 Sales / Copilot**
- Agents listed on the official pricing page: **Sales Qualification Agent, Sales Opportunity Agent, Sales Research Agent, and Sales Close Agent (preview)**. Copilot in Dynamics 365 provides opportunity summaries, email and meeting assistance, and natural-language insights. Premium adds AI recommended actions and data enrichment. — [Microsoft pricing](https://www.microsoft.com/en-us/dynamics-365/products/sales/pricing)
- An April 2026 source says the Sales Qualification, Sales Opportunity and Data Enrichment agents are generally available. — [Apprising](https://www.apprising.co.nz/post/microsoft-sales-ai-agents-overview); [Cynoteck](https://www.cynoteck.com/blog-post/sales-qualification-agent-dynamics-365-sales)
- Licensing requirements for the Qualification Agent are reported inconsistently across sources (D365 Sales license + Copilot Credits; some say a Copilot Studio license plus Exchange server-side sync). — [Logan Consulting](https://www.loganconsulting.com/blog/microsoft-dynamics-365-sales-ai-agents/); [Cynoteck](https://www.cynoteck.com/blog-post/sales-qualification-agent-dynamics-365-sales)

**Zoho Zia**
- On **17 Jul 2025 (Zoholics India)** Zoho launched:
  - its own **Zia LLM** in three sizes, plus English/Hindi speech-recognition models;
  - **25+ prebuilt Zia Agents** sold through an Agent Marketplace;
  - the no-code, prompt-based **Zia Agent Studio**, with access to 700+ actions across Zoho apps;
  - an **MCP server** for third-party agents, with A2A protocol support planned.
- Agents can run autonomously, from a button, from rules, or inside conversations. They act as a "digital employee" that respects user permissions, and admins can audit their behavior. GA was expected around end-2025.
— [Zoho press release](https://prezohoweb.zoho.com/news/zoho-launches-zia-llm-and-deepens-ai-portfolio-with-prebuilt-agents-custom-agent-builder-mcp-and-marketplace.html); [Business Wire](https://www.businesswire.com/news/home/20250717118204/en/)
- Building agents in Agent Studio is free. Model usage is billed via prepaid credits at **1,000 credits per $1**, and bring-your-own-key setups add no Zoho-side fee. — [Layer3Labs Zia guide](https://www.layer3labs.io/guides/zoho-zia-explained)

**Pipedrive and Freshworks**
- Pipedrive announced its "agentic AI CRM" on **4 Feb 2025**: voice- and text-enabled agents that draft emails, summarize past interactions and highlight important communications, with salespeople staying in control. It was in beta for limited customers, and 2026 reviews say rollout is still gradual. — [Business Wire](https://www.businesswire.com/news/home/20250204946106/en/Pipedrive-Unveils-Next-Generation-AI-CRM-With-Agentic-Experience/); [SiliconANGLE](https://siliconangle.com/2025/02/04/pipedrive-introduces-agentic-ai-teammates-sales-process/)
- Freshworks Freddy AI has three parts: **AI Agent** (autonomous conversations), **Copilot** (assists humans) and **Insights**. Freshworks claims up to 80% of queries are resolved without humans; this is a vendor claim. A G2 AI evaluation shows a 3.7 rating from only 7 reviews, and reviewers report it struggles with complex queries. — [eesel.ai](https://eesel.ai/blog/freddy-ai); [G2 AI evaluation](https://ai.g2.com/evaluations/categories/customer-experience/freshworks-freddy)

### Inferences
- In practice the agent features cluster into five jobs:
  1. **Inbound lead response and qualification** (AI SDR: Agentforce SDR, HubSpot Prospecting/Customer agents, D365 Sales Qualification Agent, Zia agents).
  2. **Summaries and data entry** (call and email summaries, auto-updating deal fields: HubSpot deal progression, Copilot).
  3. **Next-best-action and deal-risk scoring** (Sales Coach, D365 Premium, Pipedrive AI).
  4. **Data enrichment and research** (D365 Research/Enrichment, Agentforce prospecting).
  5. **Customer-service resolution** (Freddy AI Agent, HubSpot Customer Agent).
- These agents only work as well as the underlying CRM data (clean lead and contact records, logged activities, defined stages). A business without the Q1 basics gets little value from them.
- Outcome-based pricing ($1 per qualified lead, per resolved conversation) is new in 2026 and lowers the risk of trying agents. Costs scale with volume, however.

### Gaps
- I did not verify Dreamforce 2026 (Sept/Oct 2026) announcements beyond what appears on the October 2026 pricing page ("Agentforce Coworker", Max edition).
- No independent, peer-reviewed measurements of AI SDR agent effectiveness were found. Vendor conversion-lift figures are marketing claims.
- Thai-language quality of these agents (Agentforce, Breeze, Zia, Copilot) was not researched.

---

## Q4. Build vs buy: what do companies that build their own CRM gain or lose, and when is a custom CRM justified?

### Takeaway
Most sources favor **buying** for small teams with standard sales processes. **Building** pays off only with large user counts, truly unique workflows, special compliance or integration needs, or when you have a sustained in-house dev capacity. The decisive cost is ongoing maintenance (often 15–40% of build cost per year), not the initial build. Note that almost all TCO figures come from vendors who sell one side or the other.

### Cited Findings
- A SaaS-CRM vendor's model for a 25-person company: building costs ~**$5.31M over 5 years vs ~$154,950** for a mature SaaS platform (34× gap). This is a vendor analysis. — [Salesboom](https://www.salesboom.com/cloud-crm-guide/buy-vs-build-crm-total-cost-analysis.html)
- A custom-dev author's model reaches the opposite conclusion: bespoke CRM/ERP becomes cheaper than SaaS by year 2, at **~£108,500 vs ~£257,000 over 5 years**, assuming SaaS at £75/user/mo. — [DEV Community (Mecanik)](https://dev.to/mecanik-dev/bespoke-crm-erp-development-build-vs-buy-guide-2026-341m)
- Figures from one vendor page:
  - **custom MVP takes 6–18 months and costs $150k–$500k+**;
  - adding email, automation and mobile extends it to 12–24 months;
  - integrations add 3–6 months, and projects "ship 2x later than planned";
  - **maintenance runs 20–40% of build cost per year** (a $300k build means $60k–$120k/yr);
  - **5-year TCO is $400k–$1M+**, versus $25k–$250k+ for enterprise SaaS.
  — [Juicy Goosey CRM](https://www.juicygooseycrm.com/build-vs-buy-crm/) (vendor of a $49/mo CRM, so biased toward buying)
- The same page says buying fits "most businesses under 50 people" with a standard lead → qualify → propose → close workflow. Building makes sense for "500+ users with unique workflows", compliance needs no commercial CRM supports, when the CRM is itself the product, or when an internal team can maintain it without pulling from core work. It lists hidden build costs: security, falling behind vendor features, and a "bus factor of 1" when developers leave. Bought CRMs typically cover "80–90%" of needs. — [Juicy Goosey CRM](https://www.juicygooseycrm.com/build-vs-buy-crm/)
- Other guides give lower thresholds:
  - custom builds can become cost-effective within 2–3 years for **~20+ users with specific workflows**;
  - for under ~15 users with a standard process, a ~$40k build never pays back against a low subscription;
  - another estimate puts maintenance at **15–25%** of build cost per year.
  — [Leads360](https://leads360llc.com/crm-software-development-build-vs-buy/); [QBS Global](https://qbsglobal.blog/cost-to-build-a-custom-crm-2026); [Pipeline CRM](https://pipelinecrm.com/blog/custom-crm-vs-off-the-shelf-crm/) (attribution of individual thresholds among these three guides is approximate; they came from a combined search summary)
- **Gains from building**:
  - exact fit to your process;
  - control of architecture and roadmap;
  - full data ownership;
  - no per-seat fees as headcount grows;
  - direct integration with internal systems without marketplace fees.
- **Losses from building**:
  - months of build time;
  - maintenance, security and upgrades fall on you;
  - developers are diverted from the core business;
  - quality depends on the team;
  - each new integration becomes a new project.
  — [Pipeline CRM](https://pipelinecrm.com/blog/custom-crm-vs-off-the-shelf-crm/); [Vantagepoint](https://vantagepoint.io/blog/sf/insights/hidden-cost-crm-customization-build-vs-buy)
- **Downsides of buying**: per-seat cost scales linearly with headcount, vendors raise prices at renewal, the tool can be rigid for unusual processes, and data sits with a third party. — [Pipeline CRM](https://pipelinecrm.com/blog/custom-crm-vs-off-the-shelf-crm/)

### Inferences
- A middle path is common: **buy a CRM core and customize or integrate it** (custom fields, automations, APIs, low-code). Alternatively, build a **thin custom layer** (dashboards, local-channel integrations, special SLA rules) on top of cheap data infrastructure. This captures the fit benefits without carrying a full CRM's maintenance burden.
- AI tooling in 2025–2026 lowers the cost of building small custom systems, but it does not remove the ongoing maintenance, security and "bus factor" risks the sources highlight.
- A custom CRM is most defensible when the critical workflow is not supported well by global CRMs, for example local messaging channels, industry-specific stock or inventory matching, or local payment and finance processes. It is weakest when the custom system re-implements commodity features (contacts, pipelines, email) that a $10–25/user tool already provides.

### Gaps
- No independent (non-vendor) academic or analyst study of CRM build-vs-buy TCO was found. All quantified figures come from interested parties.
- No Thailand-specific developer cost data was gathered; the figures above are in US/UK cost terms.

---

## Q5. Which platforms are commonly used by SMEs in Southeast Asia and Thailand?

### Takeaway
No neutral market-share survey of Thai SME CRM usage exists in what I could find. Mordor Intelligence (2026) describes the market as three tiers:
- global enterprise suites (Salesforce, Microsoft, Oracle, SAP) in large companies;
- freemium mid-tier foreign tools (HubSpot, Zoho, Freshworks) for cost-sensitive firms;
- local Thai vendors (Zanroo, Choco CRM, Buzzebees) winning SMEs with Thai UX and LINE OA connectors.

The Thai CRM market is small (~US$198M in 2026) but growing ~12%/yr, with SMEs driving incremental growth.

### Cited Findings
- **Thailand CRM market**: US$176.55M (2025) → **US$197.6M (2026)** → US$346.52M (2031), **11.90% CAGR** 2026–2031. — [Mordor Intelligence](https://www.mordorintelligence.com/industry-reports/thailand-crm-market)
- **Large enterprises** held **62.55% (US$110.42M)** of the 2025 market. **SMEs grow at a 12.68% CAGR** and are expected to supply most incremental revenue through 2031. **Cloud** deployment was 62.20% of 2025 revenue; hybrid is the fastest-growing at a 13.05% CAGR. — [Mordor Intelligence](https://www.mordorintelligence.com/industry-reports/thailand-crm-market)
- **Vendors named by Mordor**:
  - **Leaders**: Salesforce, Microsoft, Oracle, SAP and IBM. Global suites win enterprise accounts on breadth and compliance certifications. Oracle has a Thai data-center partnership that helps with data residency.
  - **Local**: Zanroo, Choco CRM and Buzzebees win SME deals with Thai-language UX, LINE OA plug-ins and rapid-deployment templates.
  - **Mid-tier foreign**: HubSpot, Zoho and Freshworks target cost-sensitive buyers with freemium tiers.
  - **Implementation partners**: Yokogawa Votiva Solutions (Thailand) and Hitachi Solutions deliver Microsoft Dynamics 365 projects.
  — [Mordor Intelligence](https://www.mordorintelligence.com/industry-reports/thailand-crm-market)
- **Recent Thai signals**:
  - IEAT and Bumrungrad International Hospital adopted Salesforce Agentforce (April 2026).
  - Microsoft committed more than US$1B (2026–2028) to cloud and AI data-center infrastructure in Thailand.
  - Drivers: Thailand 4.0, 1%-interest soft loans for SME cloud CRM adoption, depa MSME cloud/AI incentives.
  - Constraints: compliance under PDPA.
  — [Mordor Intelligence](https://www.mordorintelligence.com/industry-reports/thailand-crm-market)
- Another market report calls Thai SMEs the "largest untapped CRM opportunity", historically held back by software cost and limited digital skills. This is easing as local vendors bundle low-friction offerings. — [Next Move Strategy Consulting](https://www.nextmsc.com/report/thailand-customer-relationship-management-crm-market-ic4043)
- A Bangkok web-studio guide calls **HubSpot the most popular CRM for Bangkok SMEs** because its free tier is functional, with Pipedrive as the alternative for sales-focused teams. This is a single opinion source. — [Nopa Studio](https://nopastudio.com/en/blog/crm-bangkok-businesses-manage-customers)
- A 2026 listing ranks **Shopline and Zaapi** highest for Thai retailers because of native social-commerce and LINE sync. — [Software-Listing](https://software-listing.com/best/thailand-crm)
- Pepper Cloud (Singapore) markets itself as a CRM "engineered for Thai SMEs" with WhatsApp and LINE integration. This is vendor self-promotion. — [Pepper Cloud](https://peppercloud.com/country/best-crm-software-in-thailand/)
- Listing sites such as SoftwareSuggest are paid by vendors for traffic and leads, so their "best CRM in Thailand" rankings are not neutral. — [SoftwareSuggest](https://www.softwaresuggest.com/crm-software/thailand)

### Inferences
- For a Thai SME the realistic shortlist splits three ways:
  - **(a) global SME tools** (HubSpot free/Starter, Zoho, Freshsales, Pipedrive, Bitrix24, Kommo): cheap, mature, but LINE support usually comes via third-party connectors;
  - **(b) Thai/regional tools** (Zanroo, Choco CRM, Buzzebees, Zaapi, Pepper Cloud): Thai UX and native LINE OA, but smaller ecosystems;
  - **(c) enterprise suites** (Salesforce, Dynamics): justified mainly for larger organizations or regulated industries.
- Because LINE OA is Thailand's dominant customer channel (per Mordor), "how well does it connect to LINE?" is often the deciding factor for Thai SMEs. That topic is covered by another researcher.

### Gaps
- No neutral survey of Thai SME CRM adoption or vendor share exists in what I found (e.g., from OSMEP, depa or an independent research firm). Vendor rankings are promotional.
- Customer counts in Thailand for HubSpot, Zoho, Bitrix24 and others were not found.
- Thai-baht pricing and local reseller/partner pricing were not researched.
