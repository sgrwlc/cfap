Okay, here is a Master Plan document detailing the CapConduit platform concept based only on the features, functionality, and model we have designed and discussed so far. This focuses specifically on the system we are building, including its business logic and operational context.

Master Plan: CapConduit Call Platform

1. Executive Summary

CapConduit is a specialized, multi-tenant, web-based software platform designed explicitly for Call Sellers – businesses that generate inbound phone call leads and sell them to their clients on a performance basis. The platform solves the critical operational challenge of managing call delivery volume and concurrency against client-stipulated limits. By acting as an intelligent call routing "conduit," CapConduit automatically enforces pre-defined caps (simultaneous calls, total calls per period) in real-time before forwarding calls via VoIP (SIP/IAX2), preventing call wastage, maintaining client satisfaction, and enabling efficient operations for the Call Seller. The platform operates on a usage-based, manual pre-payment model managed by a Platform Administrator.

2. Problem Definition: The Call Seller's Challenge

Businesses generating inbound leads (e.g., via online advertising, SEO, partner networks) for clients like insurance agencies, home service providers, legal firms, etc., often operate on a Pay-Per-Call or Pay-Per-Qualified-Call model. Their clients agree to buy leads but typically have strict limitations based on:

Agent Capacity (Concurrency): Clients can only handle a specific number of simultaneous inbound calls (e.g., 15 agents available means a concurrency cap of 15). Sending more calls at once overwhelms agents, leads to abandoned calls, and frustrates the client.
Budget/Volume Caps: Clients allocate specific budgets translating to a maximum number of calls they will purchase within a given timeframe (e.g., 50 calls/hour, 500 calls/day, 1000 calls total per pre-payment). Exceeding these caps results in unbillable calls and potential disputes.
Managing these caps manually across multiple advertising campaigns and numerous clients is complex, time-consuming, and highly prone to error. Failure to adhere to caps damages client relationships and leads to lost revenue for the Call Seller.

3. Solution: The CapConduit Platform

CapConduit provides Call Sellers with a dedicated platform to automate the enforcement of these critical call caps. It acts as a central routing point that intelligently validates each incoming call against defined rules before connecting it to the end client.

Value Proposition for Call Sellers:

Automated Cap Enforcement: Eliminates manual tracking and errors related to concurrency and volume limits.
Optimized Call Delivery: Ensures calls are only sent when the client is ready and within agreed limits, maximizing the value of each generated lead.
Improved Client Satisfaction: Prevents agent overload and call abandonment, leading to stronger client relationships.
Reduced Waste: Avoids sending unbillable calls that exceed client caps.
Operational Efficiency: Centralizes campaign, client (Target), and routing rule management.
Data & Reporting: Provides clear Call Detail Records (CDRs) for monitoring performance and facilitating accurate billing of their own clients.
4. Target Audience

Primary Users (Call Sellers): Businesses or individuals generating inbound phone call leads and selling them to other businesses. They interact with the web portal (forwarding.realpropbx.com) to manage their operations. This is a multi-tenant system, meaning multiple Call Sellers can use the platform independently, each managing their own campaigns, targets, and rules.
Secondary Users (Platform Administrators): The entity operating the CapConduit platform (i.e., "us"). Responsible for overall platform management, user account creation, manual balance adjustments, DID procurement and assignment, setting global parameters (like billing rate), and system monitoring/maintenance .
Non-Users (End Clients): The Call Seller's clients who ultimately receive the calls. They do not interact with CapConduit directly; calls are forwarded to their existing phone systems (PBX, contact center).
5. Core Features & Functionality

User & Account Management (Admin):
Create, view, update, and delete Call Seller user accounts.
Manually adjust Call Seller account balances (pre-paid credit).
DID (Phone Number) Management:
Admin: Procure DIDs externally (manual process), add them to the platform inventory, view all DIDs, assign DIDs to users based on requests or directly.
Call Seller: Request new DIDs via the platform, view their assigned DIDs, see which campaigns DIDs are linked to.
Campaign Management (Call Seller):
Create and manage campaigns (e.g., "Google Ads - NY Insurance", "Facebook - CA Home Services").
Assign one or more owned DIDs to each campaign.
Define Volume Caps per campaign: Max calls per hour, per day, and/or total overall.
Monitor campaign status (active/inactive).
Target Management (Call Seller):
Define "Targets" representing their end clients.
Specify client details (Name, etc.).
Configure the technical destination: VoIP protocol (SIP or IAX2) and the specific URI (e.g., sip:sales@client-pbx.com:5060).
Define Concurrency Cap: Maximum simultaneous calls allowed to this specific Target endpoint.
Define Total Calls Allowed: A counter representing the maximum number of calls this Target can receive based on budget/pre-payment (decremented with each successful, billable call).
Monitor Target status (active/inactive).
Forwarding Rule Management (Call Seller):
Create and manage rules that define call flow.
Link one or more source Campaigns to a rule.
Link one or more destination Targets to a rule.
Define Routing Strategy (how to choose between multiple targets in a rule):
Primary: Send all calls to the first active/eligible target.
Priority: Send calls to the target with the lowest priority number first; failover to higher numbers if the primary is unavailable/capped.
RoundRobin: Distribute calls sequentially across eligible targets (future: potentially add weighting).
Set Minimum Billable Duration (seconds): Calls must last at least this long to be counted against caps and incur charges.
Real-time Call Processing (Automated Backend/Asterisk):
Incoming call arrives at a DID on the platform.
Identify DID owner (User) and linked active Campaign.
Check User Balance: If insufficient, Reject Call (Rejected-Balance).
Check Campaign Volume Caps (Hourly/Daily/Total): If any cap is reached, Reject Call (Rejected-VolCap). Reset hourly/daily counters as needed.
Identify active Forwarding Rule linked to the Campaign.
Identify potential Target(s) linked to the Rule, ordered by strategy.
For each potential Target:
Check Target Total Calls Allowed: If cap reached, skip to next target.
Check Target Concurrency Cap: Use Asterisk's real-time tracking (GROUP_COUNT) against the Target's defined limit. If limit reached, skip to next target.
If a Target passes all checks: Forward the call via direct SIP/IAX2 to the Target's URI. Stop checking other targets (unless strategy dictates otherwise).
If all potential Targets are capped or unavailable: Reject Call (Rejected-TargetCap, Rejected-ConcurrencyCap, Failed-NoRoute).
Call Detail Record (CDR) Logging:
Log every call attempt with comprehensive details: timestamps (start, answer, end), duration, billable duration, caller ID, incoming DID, linked User/Campaign/Target IDs, final status (Connected, Rejected Reason, Failed, Busy, NoAnswer), Asterisk call IDs.
Accounting & Counter Decrementing:
On call completion, if the call connected and met the min_billable_duration:
Calculate cost: billable_duration * billing_rate_per_minute / 60.
Decrement the Call Seller's users.balance by the calculated cost.
Decrement the targets.total_calls_allowed counter by 1 (if applicable).
Increment relevant campaigns.current_*_calls counters.
Reporting (Call Seller):
View assigned DIDs, active Campaigns, Targets, and Rules.
View current account balance.
View detailed CDR list with filtering options (date, campaign, target).
Export CDRs (e.g., to CSV) for analysis and client billing.
Notifications (Basic):
View simple in-platform notifications (e.g., "DID Assigned", "Low Balance Warning").
Mark notifications as read.
System Settings (Admin):
View and update global platform settings (e.g., billing_rate_per_minute).
6. Business Model

Primary Revenue Stream: Usage-based charges to the Call Seller.
Charging Mechanism: A per-minute rate (billing_rate_per_minute set by Admin) is applied to the billable_duration of successfully connected calls.
Payment Model: Manual Pre-payment. Call Sellers pre-pay funds to the Platform Administrator outside the system. The Admin then manually updates the Call Seller's balance within the CapConduit platform using the /admin/balance API endpoint.
Service Suspension: Calls are automatically rejected (Rejected-Balance) if a Call Seller's balance is less than or equal to zero (or another defined threshold).
Not Included in Current Model: Subscription fees, per-user fees, per-DID fees (though Admin tracks DID costs), tiered pricing, automated invoicing, integrated payment gateways.
7. Technical Architecture Summary

Cloud Provider: Google Cloud Platform (GCP).
Server: Single Compute Engine VM (call-platform-vm-debian).
OS: Debian 12 (Bookworm).
Telephony Engine: Asterisk 20 (handles call signaling, routing execution, concurrency check via GROUP_COUNT).
Database: PostgreSQL (stores all configuration, user data, logs).
Backend: Python 3 / Flask (provides web interface, APIs, business logic).
Web Server/Proxy: Nginx (handles HTTP requests, proxies to backend, SSL termination planned).
WSGI Server: Gunicorn (runs the Flask application).
Protocols: SIP/IAX2 (for forwarding calls to Targets), HTTP/S (for web portal/API).
8. Operational Plan & Requirements

Onboarding: Call Seller accounts are created manually by the Platform Administrator via the Admin API or interface.
DID Procurement/Management: Platform Administrator manually procures phone numbers from third-party providers (e.g., Twilio, Bandwidth), adds them to the CapConduit inventory via the Admin API, and assigns them to users.
Billing & Payments: Administrator invoices Call Sellers externally. Upon receiving payment, the Administrator manually updates the user's balance in CapConduit.
Support: Provided directly by the Platform Administrator to Call Sellers (e.g., via email, phone).
Monitoring & Maintenance: Administrator responsibility includes monitoring server health (CPU, RAM, disk), application logs (Flask, Asterisk), database performance/backups, and applying system/software updates.
Security: Managed via GCP firewall rules, OS-level firewall (UFW), Fail2Ban, planned HTTPS encryption (Let's Encrypt), secure coding practices (authentication, authorization checks, parameterized queries).
Legal: Standard Terms of Service and Privacy Policy required for Call Sellers using the platform.
9. Current Status & Next Steps

Status: Infrastructure deployed, core software installed, database schema implemented, sample data loaded. Backend API (Flask) for user, admin, and internal functions is fully implemented and tested locally/remotely.
Next Step: Phase 11 - Asterisk Integration. Develop AGI scripts and Asterisk dialplan logic to connect the telephony engine with the backend Internal APIs (/internal_api/route_info, /internal_api/log_cdr) to enable real-time call processing and logging based on the implemented rules and caps.
This Master Plan provides a detailed blueprint of the CapConduit platform as currently designed and implemented up to the end of the backend API phase. It clarifies the target user, the problem solved, the specific features, the business model, and operational context.
