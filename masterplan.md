Master Plan: CapConduit Call Platform (v3.0 - Redesigned)
1. Executive Summary

CapConduit is a specialized, multi-tenant, web-based software platform designed to bridge Call Sellers (lead generators) with Call Centers (Clients). It allows Sellers to create marketing campaigns associated with specific DIDs (phone numbers) and intelligently route incoming calls to pre-registered, verified Call Center Clients based on defined rules, concurrency limits, and volume caps. Routing is managed via a central MIKO-PBX (Asterisk) system utilizing Asterisk Realtime Architecture (ARA) for dynamic endpoint configuration sourced from the platform's database. The platform operates on a usage model potentially involving manual pre-payment balances managed by a Platform Administrator (though billing logic is not yet implemented).

2. Problem Definition: The Call Seller's Challenge

Call Sellers face challenges managing call delivery to their clients (Call Centers) who often have strict limits on:

Concurrency: How many simultaneous calls they can handle.
Volume: Total number of calls they will accept per campaign or overall (budget-based).
Routing Complexity: Directing calls from different sources (campaigns/DIDs) to the correct client endpoint with failover or distribution logic.
Manual management is error-prone, leads to dropped calls, exceeds client caps (causing lost revenue/disputes), and reduces operational efficiency.

3. Solution: The CapConduit Platform (Redesigned)

CapConduit provides Call Sellers and Platform Administrators/Staff with tools to automate and manage call routing and capping:

Central Client Registry: Admins/Staff manage a central database of Call Center Clients, including their technical connection details (SIP endpoints via ARA).
Simplified Campaign Linking: Sellers create Campaigns, associate their DIDs, and link them directly to one or more approved Clients.
Granular Cap Control: Concurrency and total volume caps are defined per specific Campaign-to-Client link, allowing fine-grained control.
ARA Integration: Asterisk reads SIP endpoint configurations directly from the platform's database in real-time, simplifying endpoint management.
Intelligent Routing: The system (primarily Asterisk dialplan using data provided) enforces caps and routing rules (Priority, Round-Robin, Weighted, Timeout Fallback) before dialing a Client.
Value Proposition:

For Sellers: Automated cap enforcement, optimized delivery, reduced waste, streamlined campaign setup, reporting (via Call Logs).
For Admins/Staff: Centralized client management, simplified endpoint configuration via ARA, platform oversight.
4. Target Audience

Primary Users (Call Sellers - Role: user): Businesses generating inbound calls and selling them. Interact via API/future web portal to manage Campaigns, DIDs, and Campaign-Client links.
Secondary Users (Platform Admins/Staff - Role: admin/staff): Operators of the CapConduit platform. Manage Users, Clients (including PJSIP/ARA configuration), DIDs (inventory/assignment), and overall system health via API/future admin portal.
Tertiary Users (Call Centers - Role: client entity): The end recipients of calls. Pre-registered by Admins/Staff. Do not interact directly with the platform UI.
System Interaction: Asterisk (MIKO-PBX) interacts via ARA database lookups and potentially internal APIs for logging.
5. Core Features & Functionality (Based on Implemented Schema/Services/APIs)

User Management (Admin/Staff): CRUD operations for user accounts (Admin, Staff, Seller). Role and status management. Password changes.
Client & PJSIP (ARA) Management (Admin/Staff): CRUD operations for logical Clients. Atomic CRUD operations for associated PJSIP ARA configurations (pjsip_endpoints, pjsip_aors, pjsip_auths) linked to Clients. Status management. Prevent deletion if linked to active campaigns.
DID Management (Seller): CRUD operations for own DIDs. Status management.
Campaign Management (Seller): CRUD operations for own Campaigns. Define routing_strategy and dial_timeout_seconds. Status management.
Campaign-DID Linking (Seller): Associate/disassociate owned DIDs with owned Campaigns (Many-to-Many).
Campaign-Client Linking & Settings (Seller):
List available active Clients (managed by Admin/Staff).
Link owned Campaigns to available Clients (Many-to-Many).
Define per-link settings: max_concurrency, total_calls_allowed (optional), forwarding_priority, weight, status.
Update and remove these links/settings.
Real-time Data for Asterisk (Internal API / Services):
Logic exists (CallRoutingService) to look up DID -> User -> Campaign -> Active/Eligible CampaignClientSettings (ordered by strategy) including PJSIP URIs, concurrency/total caps. This data will be used by Asterisk.
Call Detail Record (CDR) Logging (Internal API / Services):
Logic exists (CallLoggingService) to receive call attempt details from Asterisk.
Inserts detailed records into call_logs.
Atomically increments current_total_calls on the relevant CampaignClientSettings record for successfully answered calls.
Call Log Viewing (Seller): Retrieve and filter own call logs (paginated).
6. Business Model (Conceptual)

Primary Mechanism: Usage-based tracking (call attempts logged).
Charging: Not implemented. Conceptually could be per-call, per-minute based on billsec_seconds, potentially using Admin-managed balances.
Payment: Not implemented. Assumed manual pre-payment if balance system were added.
Suspension: Not implemented. Logic could be added to CallRoutingService to reject calls based on user balance.
7. Technical Architecture Summary

Cloud Provider: Google Cloud Platform (GCP).
Server: Single Compute Engine VM (Debian).
Telephony Engine: Asterisk 20 (Handles signaling, uses ARA for endpoints, executes dialplan logic).
Database: PostgreSQL (Stores all config, user data, logs; provides ARA tables).
Backend: Python 3 / Flask / SQLAlchemy (Provides APIs, business logic via Service Layer).
Web Server/Proxy: Nginx.
WSGI Server: Gunicorn.
Key Protocols: SIP/IAX2 (Implicitly via Asterisk PJSIP), HTTP/S (for APIs).
ARA: Asterisk Realtime Architecture via res_config_pgsql (or similar) reading pjsip_* tables is a core design principle.
8. Operational Plan & Requirements

Onboarding: Admin/Staff create Seller (user) accounts via API.
Client Setup: Admin/Staff create Client records and corresponding PJSIP ARA configurations via API.
DID Procurement: Assumed manual procurement by Admin/Staff; DIDs added/assigned to Sellers via API/future UI.
Support/Billing: Manual processes outside the current platform scope.
Monitoring/Maintenance: Admin responsibility.
9. Current Status & Next Steps

Status: Infrastructure deployed, core software installed. Database schema (v3.0 ARA-focused) implemented and populated. Backend API (Flask) including Auth, Admin (User, Client/PJSIP), Seller (DID, Campaign, Links), and Internal (Logging) endpoints are implemented and functionally tested via Pytest integration tests. Service layer logic is complete.
Next Step: Phase 11 (Revised) - Asterisk + ARA Integration. Configure Asterisk (sorcery.conf, res_pjsip.conf, extconfig.conf) to connect to the PostgreSQL database and use the pjsip_* tables via ARA. Develop Asterisk dialplan (extensions.conf) to query necessary routing data (potentially via a simplified internal API or direct DB lookup), check caps using fetched data and GROUP_COUNT, perform Dial(), and trigger the logging API via AGI.