AI Handoff & Briefing Document: CapConduit Call Platform (v3.0)
Objective: Fully assume the role of the primary AI developer for the CapConduit project (CFAP codebase). Internalize the project's current state, architecture, goals, and codebase (v3.0 redesign) to seamlessly continue development into the Asterisk+ARA Integration phase.

1. Prerequisite Document Analysis:

Thoroughly read and assimilate:

Master Plan: CapConduit Call Platform (v3.0 - Redesigned): Understands business logic, user roles, core features (Seller->Client linking, granular caps), ARA focus.
Progress Report: CapConduit Platform Deployment (v3.0 Update): Details completed phases, current tested state of APIs and services.
AI Handoff & Briefing Document (This Document): Synthesizes state, outlines next steps.
Project Files (cfap/ directory): Includes app/ (Flask code), tests/ (Pytest integration tests), configuration files (.env, config.py), DB files (schema_v3.sql, sample_data_v3.sql).
2. Core Knowledge Internalization:

Project Goal: Route calls from Sellers' DIDs/Campaigns to specific, pre-registered Call Center Clients via a central Asterisk PBX, enforcing caps defined per Campaign-Client link.
Key Entities: Users (Admin, Staff, Seller), Clients (Call Centers), DIDs, Campaigns, CampaignClientSettings (CRITICAL: holds link-specific caps/rules), CallLogs, pjsip_* tables (for ARA).
Architecture: Nginx -> Gunicorn -> Flask (Python/SQLAlchemy) -> PostgreSQL. Asterisk interacts via ARA (reading pjsip_* tables) and Internal API (primarily POST /api/internal/log_call).
Critical Logic:
Admins/Staff manage Clients and their PJSIP configs (written to ARA tables).
Sellers manage Campaigns, DIDs, and link them to Clients via CampaignClientSettings, defining caps/priority/weight per link.
Asterisk (Dialplan) reads ARA PJSIP data, queries DB/API for Campaign/Settings data, checks caps (GROUP_COUNT + total call check), performs Dial based on strategy/timeout.
Asterisk (AGI) calls POST /api/internal/log_call on hangup, passing call details and the ID of the specific CampaignClientSetting used.
Backend API (log_call endpoint) logs CDR and increments current_total_calls on the specific CampaignClientSettings record.
3. Current State Confirmation (CRITICAL):

Confirm understanding that:

Infrastructure, DB Schema (v3.0 ARA), Sample Data, Flask App Structure, Service Layer logic are complete.
All currently implemented API endpoints (Auth, Admin User Mgmt, Admin Client/PJSIP Mgmt, Seller DID Mgmt, Seller Campaign/Link Mgmt, Seller Log View, Internal Log Call) are functionally complete and PASSING their corresponding Pytest integration tests.
The project is poised to begin Phase 11 (Revised): Asterisk + ARA Integration. Do NOT revisit or modify work on the Flask backend/services/tested APIs unless strictly necessary for Asterisk integration issues.
4. Immediate Task Identification (Phase 11 Revised: Asterisk + ARA Integration):

Focus solely on making the Asterisk instance use the database via ARA and interact with the logging API.

A. Configure Asterisk for ARA:
modules.conf: Ensure res_config_pgsql.so (or MySQL equivalent if used) and res_pjsip_config_wizard.so (optional) are loaded.
extconfig.conf: Define connection details for pgsql (or mysql) to call_platform_db. Create mappings for pjsip.conf => pgsql,call_platform_db,pjsip_endpoints, pjsip.conf => pgsql,call_platform_db,pjsip_aors, pjsip.conf => pgsql,call_platform_db,pjsip_auths.
res_pjsip.conf: Define necessary transports (e.g., transport-udp). Ensure endpoint/aor/auth loading points to the realtime backend (e.g., endpoint=config,pjsip.conf,criteria=type=endpoint).
sorcery.conf: Configure if using configuration wizards, otherwise ensure basic PJSIP objects point to config backend type.
Verification: Use Asterisk CLI: module load res_config_pgsql.so, realtime load pjsip, pjsip show endpoints, pjsip show aors should show clients defined in the database.
B. Develop Asterisk Dialplan (extensions.conf):
Define entry context (e.g., [from-pstn], [from-trunk]).
Answer()
Lookup Campaign: Use ODBC_Function (via func_odbc.conf pointing to extconfig.conf connection) or simple AGI script to query DB: SELECT c.id, c.routing_strategy, c.dial_timeout_seconds FROM campaigns c JOIN campaign_dids cd ON c.id = cd.campaign_id JOIN dids d ON cd.did_id = d.id WHERE d.number = '${CHANNEL(dnid)}' AND c.status = 'active' LIMIT 1; Set results to channel variables (e.g., CAMPAIGN_ID, ROUTING_STRATEGY, DIAL_TIMEOUT). Handle no campaign found.
Fetch Eligible Client Settings: Use ODBC_Function/AGI to query DB: SELECT cs.id, cs.client_id, cs.max_concurrency, cs.total_calls_allowed, cs.current_total_calls, cs.forwarding_priority, cs.weight, cl.client_identifier FROM campaign_client_settings cs JOIN clients cl ON cs.client_id = cl.id WHERE cs.campaign_id = ${CAMPAIGN_ID} AND cs.status = 'active' AND cl.status = 'active' ORDER BY cs.forwarding_priority ASC; Store results perhaps delimited in a channel variable or use complex AGI. Handle no settings found.
Loop/Select Target:
Iterate through fetched settings based on ROUTING_STRATEGY (Priority order is default, RR/Weighted needs dialplan logic).
Check Total Cap: GotoIf($[${SETTING_CURRENT_TOTAL} >= ${SETTING_TOTAL_ALLOWED}]?next_target) (Handle NULL allowed).
Check Concurrency: Define dynamic group GROUP(ccs-${SETTING_ID}) or GROUP(camp${CAMPAIGN_ID}-client${CLIENT_ID}). Use GotoIf($[${GROUP_COUNT(${GROUP_NAME})} >= ${SETTING_MAX_CC}]?next_target).
Set Call Group: Set(GROUP()=${GROUP_NAME}).
Store Attempted Setting ID: Set(EFFECTIVE_CCS_ID=${SETTING_ID}).
Dial: Dial(PJSIP/${CLIENT_IDENTIFIER},${DIAL_TIMEOUT},ghH) (g: continue on answer, h: run h ext on caller hangup, H: run h ext on callee hangup).
Handle DIALSTATUS: Check ANSWER, BUSY, NOANSWER, CONGESTION, CHANUNAVAIL. If ANSWER, break loop/goto done. If BUSY/NOANSWER/etc., and strategy allows fallback, continue loop (goto(next_target)). Handle timeout (${HASH(SYSTEMSTATUS)} or DIALSTATUS).
Hangup() if no target reached.
Define h extension: Run cdr_logger.agi.
C. Develop AGI Script (cdr_logger.agi):
Location: /var/lib/asterisk/agi-bin/.
Language: Python 3 (/opt/call_platform/venv/bin/python).
Functionality:
Import necessary libraries (requests, sys, os, json, datetime). Read AGI variables (agi.get_variable).
Gather required variables: UNIQUEID, LINKEDID, CHANNEL(dnid), CALLERID(num), CALLERID(name), start/answer/end times (CDR(start), etc.), DIALSTATUS, HANGUPCAUSE, EFFECTIVE_CCS_ID (set in dialplan), User/Campaign/DID IDs (potentially passed from dialplan or re-queried based on DNID if needed).
Construct JSON payload matching LogCallRequestSchema.
Read INTERNAL_API_TOKEN from environment or config file accessible to Asterisk user.
Make POST request to http://127.0.0.1:5000/api/internal/log_call with JSON payload and X-Internal-API-Token header.
Log success/failure of API call.
5. Execution Mindset & Approach:

Strict adherence to Phase 11 Revised plan.
Incremental Testing: Configure ARA first, test with CLI. Develop dialplan context by context, test lookups. Develop AGI, test standalone then in h extension. Use agi set debug on.
Consistency: Match Python style.
Security: Ensure AGI script runs as asterisk user if needed, protect API token. Set file permissions (chmod +x).
Error Handling: Robust checks in dialplan (GotoIf, Hangup) and AGI (try...except).
Logging: Use Asterisk Verbose/NoOp and Python logging within AGI.
6. Key Context Variables:

Internal Log API: http://127.0.0.1:5000/api/internal/log_call
DB Connection for ARA: Defined in extconfig.conf (using details from .env).
AGI Directory: /var/lib/asterisk/agi-bin/
Asterisk Config Dir: /etc/asterisk/
7. Interaction Protocol:

Proceed with configuring Asterisk ARA (extconfig.conf, res_config_pgsql, res_pjsip, sorcery). Present config files for review.
Develop dialplan logic. Present extensions.conf changes.
Develop cdr_logger.agi script. Present script.
Report issues encountered during Asterisk configuration or testing.
8. Confirmation:

Before generating Asterisk configs, confirm: "I have processed the updated Master Plan, Progress Report, and Handoff Document. I confirm the backend API and database (v3.0) are complete and tested via Pytest. My immediate focus is Phase 11 (Revised): Configuring Asterisk for ARA using PostgreSQL and developing the corresponding dialplan and logging AGI script."