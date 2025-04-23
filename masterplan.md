# Master Plan: CapConduit Call Platform (v3.0 - Refactored & Verified)

## 1. Executive Summary

CapConduit is a specialized, multi-tenant, web-based software platform designed to bridge Call Sellers (lead generators) with Call Centers (Clients). It allows Sellers to create marketing campaigns associated with specific DIDs (phone numbers) and intelligently route incoming calls to pre-registered, verified Call Center Clients based on defined rules, concurrency limits, and volume caps. Routing is managed via a central MIKO-PBX (Asterisk) system utilizing Asterisk Realtime Architecture (ARA) for dynamic endpoint configuration sourced from the platform's database. The platform operates on a usage model potentially involving manual pre-payment balances managed by a Platform Administrator (though billing logic is not yet implemented).

## 2. Problem Definition: The Call Seller's Challenge

Call Sellers face challenges managing call delivery to their clients (Call Centers) who often have strict limits on:

*   **Concurrency:** How many simultaneous calls they can handle.
*   **Volume:** Total number of calls they will accept per campaign or overall (budget-based).
*   **Routing Complexity:** Directing calls from different sources (campaigns/DIDs) to the correct client endpoint with failover or distribution logic.

Manual management is error-prone, leads to dropped calls, exceeds client caps (causing lost revenue/disputes), and reduces operational efficiency.

## 3. Solution: The CapConduit Platform (Refactored)

CapConduit provides Call Sellers and Platform Administrators/Staff with tools to automate and manage call routing and capping:

*   **Central Client Registry:** Admins/Staff manage a central database of Call Center Clients, including their technical connection details (SIP endpoints via ARA).
*   **Simplified Campaign Linking:** Sellers create Campaigns, associate their DIDs, and link them directly to one or more approved Clients.
*   **Granular Cap Control:** Concurrency and total volume caps are defined per specific Campaign-to-Client link, allowing fine-grained control.
*   **ARA Integration:** Asterisk reads SIP endpoint configurations directly from the platform's database in real-time, simplifying endpoint management.
*   **Intelligent Routing:** The system (primarily Asterisk dialplan using data provided) enforces caps and routing rules (Priority, Round-Robin, Weighted, Timeout Fallback) before dialing a Client.
*   **Standardized Backend:** Refactored API layer adheres to consistent transaction management, error handling using custom exceptions, and clear separation of concerns.

**Value Proposition:**

*   For Sellers: Automated cap enforcement, optimized delivery, reduced waste, streamlined campaign setup, reporting (via Call Logs).
*   For Admins/Staff: Centralized client management, simplified endpoint configuration via ARA, platform oversight, maintainable codebase.

## 4. Target Audience

*   **Primary Users (Call Sellers - Role: `user`):** Businesses generating inbound calls and selling them. Interact via API/future web portal.
*   **Secondary Users (Platform Admins/Staff - Role: `admin`/`staff`):** Operators of the CapConduit platform. Manage Users, Clients (including PJSIP/ARA), DIDs, and system health via API/future admin portal.
*   **Tertiary Users (Call Centers - Role: `client` entity):** End recipients of calls. Pre-registered by Admins/Staff. Do not interact directly with the platform UI.
*   **System Interaction:** Asterisk (MIKO-PBX) interacts via ARA database lookups and the internal logging API.

## 5. Core Features & Functionality (Verified)

*   **User Management (Admin/Staff):** CRUD operations, role/status management, password changes.
*   **Client & PJSIP (ARA) Management (Admin/Staff):** Atomic CRUD for Clients & associated PJSIP ARA configurations. Status management. Deletion prevention for actively linked clients.
*   **DID Management (Seller):** CRUD for owned DIDs. Status management.
*   **Campaign Management (Seller):** CRUD for owned Campaigns. Define routing strategy, timeout. Status management.
*   **Campaign-DID Linking (Seller):** Associate/disassociate owned DIDs with owned Campaigns.
*   **Campaign-Client Linking & Settings (Seller):** Link Campaigns to Clients; Define per-link `max_concurrency`, `total_calls_allowed`, `forwarding_priority`, `weight`, `status`. Update/remove links.
*   **Real-time Data Retrieval Logic (Internal):** `CallRoutingService` provides logic to fetch necessary data for Asterisk routing decisions (DID -> User -> Campaign -> Eligible Client Settings).
*   **Call Detail Record (CDR) Logging (Internal):** `/api/internal/log_call` endpoint receives call details, logs CDR, increments `current_total_calls` on `CampaignClientSettings` for answered calls. Secured via token.
*   **Call Log Viewing (Seller):** Retrieve and filter own call logs via API.
*   **Standardized Error Handling:** Services raise specific custom exceptions; routes catch these and return appropriate HTTP status codes/messages.
*   **Standardized Transaction Management:** Database commits/rollbacks are consistently handled at the route level per request.

## 6. Business Model (Conceptual)

*   **Primary Mechanism:** Usage-based tracking (call attempts logged).
*   **Charging:** Not implemented.
*   **Payment:** Not implemented.
*   **Suspension:** Not implemented.

## 7. Technical Architecture Summary

*   **Cloud Provider:** Google Cloud Platform (GCP).
*   **Server:** Single Compute Engine VM (Debian).
*   **Telephony Engine:** Asterisk 20 (Handles signaling, uses ARA, executes dialplan).
*   **Database:** PostgreSQL (Stores all config, user data, logs; provides ARA tables).
*   **Backend:** Python 3.11 / Flask / SQLAlchemy (Provides APIs, business logic).
*   **Web Server/Proxy:** Nginx.
*   **WSGI Server:** Gunicorn.
*   **Key Protocols:** SIP/IAX2 (Implicitly via Asterisk PJSIP), HTTP/S (for APIs).
*   **ARA:** Asterisk Realtime Architecture via `res_config_pgsql` reading `pjsip_*` tables.

## 8. Operational Plan & Requirements

*   Onboarding, Client Setup, DID Procurement, Support/Billing remain largely manual API/Admin driven processes outside the current platform UI scope.
*   Monitoring/Maintenance: Admin responsibility.

## 9. Current Status & Next Steps

*   **Current Status:** Infrastructure deployed, core software installed. PostgreSQL database schema (v3.0 ARA-focused) implemented via Flask-Migrate and populated with sample data. The **backend API application has been fully refactored and verified**:
    *   All API endpoints (Auth, Admin, Seller, Internal) are implemented.
    *   Business logic resides in the Service layer.
    *   Transaction management is standardized at the route level.
    *   Error handling uses custom exceptions mapped to appropriate HTTP responses.
    *   Code quality improved, debug remnants removed.
    *   **All integration tests are passing**, confirming backend functionality.
*   **Next Step:** **Phase: Asterisk + ARA Integration.** Configure Asterisk (`sorcery.conf`, `res_pjsip.conf`, `extconfig.conf`) to connect to the PostgreSQL database and utilize the `pjsip_*` tables via ARA. Develop the Asterisk dialplan (`extensions.conf`) to query necessary routing data, check caps, perform `Dial()`, and trigger the `/api/internal/log_call` endpoint via an AGI script (`cdr_logger.agi`).