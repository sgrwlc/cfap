AI Replica Instruction Set: CapConduit Project Handoff

Objective: Your objective is to fully assume the role of the primary AI developer for the CapConduit project, effective immediately. You must internalize the project's current state, architecture, goals, and codebase to seamlessly continue development from the exact point documented below. There should be no deviation from the established plan or need to revisit completed phases.

1. Prerequisite Document Analysis:

You must first thoroughly read and fully assimilate the information contained in the following documents provided alongside this instruction set:

Master Plan: CapConduit Call Platform: Understand the core business logic, value proposition, target users, features (especially call capping mechanisms), business model (manual balance), and overall technical architecture.
Progress Report: CapConduit Platform Deployment: Understand the sequence of deployment steps completed, the configuration of the remote VM environment, and the verification status of each phase.
AI Handoff & Briefing Document: CapConduit Call Platform: Synthesizes the current state, technical stack, environment details, and explicitly identifies the next steps.
Project Files (app.py, schema.sql, sample_data.sql, requirements.txt, .env description, service/nginx configs): These represent the current implementation state.
2. Core Knowledge Internalization:

Project Goal: Recognize that CapConduit's primary function is automated, real-time enforcement of call concurrency and volume caps for Call Sellers routing calls via direct VoIP (SIP/IAX2).
Key Entities: Understand the roles and interactions of Users (Admin/Seller), DIDs, Campaigns (with Volume Caps), Targets (with Concurrency/Total Caps), Forwarding Rules (linking Campaigns to Targets with strategy), CDRs, Balance Adjustments, Notifications, DID Requests, and System Settings.
Architecture: Internalize the Nginx -> Gunicorn -> Flask (Python) -> PostgreSQL backend architecture, and its intended interaction with Asterisk via internal APIs.
Critical APIs: Pay special attention to the functionality of the internal APIs:
GET /internal_api/route_info: Performs DID lookup, cascading checks (Balance, Campaign Caps, Target Caps), and returns routing data or rejection reasons.
POST /internal_api/log_cdr: Logs call attempts and performs transactional updates to balance and counters based on call outcome and billability.
Business Model: Understand the manual pre-payment balance system managed by the Admin and the per-minute billing logic triggered by the log_cdr endpoint.
3. Current State Confirmation (CRITICAL):

You must confirm your understanding that:

Development Phases 1 through 10 are 100% complete and tested on the target Google Cloud VM (call-platform-vm-debian, IP 34.59.92.30).
The backend Flask application (app.py) is fully functional, containing working code for all user-facing APIs, admin APIs, and the critical internal APIs (/internal_api/route_info, /internal_api/log_cdr). There are no known bugs in the backend code.
The PostgreSQL database (call_platform_db) is running, structured according to schema.sql, and populated with the sample data from sample_data.sql.
All supporting services (Nginx, Gunicorn, PostgreSQL, Asterisk) are running correctly on the VM.
The project is exactly poised to begin Phase 11: Asterisk Integration. Do NOT attempt to revisit or modify work from Phases 1-10 unless explicitly instructed due to a newly discovered critical issue related only to Phase 11 implementation.
4. Immediate Task Identification (Phase 11):

Your sole focus is now Phase 11: Asterisk Integration. This involves making the running Asterisk instance interact with the functional backend API. Your tasks are:

Develop AGI Script (routing_lookup.agi):
Location: /var/lib/asterisk/agi-bin/ on the VM.
Language: Python 3 (using the same venv: /opt/call_platform/venv/bin/python).
Functionality: Read agi_dnid, call GET http://127.0.0.1:5000/internal_api/route_info (URL-encode + in DID), parse JSON, set appropriate channel variables (ROUTING_STATUS, REJECT_REASON, target details, limits, rates) for the dialplan.
Develop AGI Script (cdr_logger.agi):
Location: /var/lib/asterisk/agi-bin/.
Language: Python 3 (using the same venv).
Functionality: Read relevant Asterisk channel variables on hangup (h extension), calculate billable_duration, construct JSON payload, call POST http://127.0.0.1:5000/internal_api/log_cdr.
Develop Asterisk Dialplan (extensions.conf):
Location: /etc/asterisk/extensions.conf (or included files).
Functionality: Define inbound context, execute routing_lookup.agi, check ROUTING_STATUS, handle rejections, if proceeding loop through targets, check concurrency (GROUP_COUNT vs. variable), execute Dial() with h option, handle DIALSTATUS, define h extension to run cdr_logger.agi.
5. Execution Mindset & Approach:

Follow the Plan: Adhere strictly to the steps outlined for Phase 11.
Incremental Development & Testing: Develop the AGI scripts first. Test them individually using Asterisk CLI commands (agi set debug on, channel originate Local/... exec AGI ...) before integrating fully into the dialplan. Test the dialplan logic step-by-step.
Consistency: Maintain coding style and patterns established in app.py when writing the Python AGI scripts. Utilize existing helper functions if applicable by structuring the AGI scripts appropriately or adding shared utility modules.
Security: Remember the internal APIs are currently only protected by basic IP checks (if uncommented). Assume calls to them originate from 127.0.0.1 (Asterisk on the same server). Ensure AGI scripts have correct execute permissions (chmod +x) and are owned by the asterisk user/group if necessary for execution by Asterisk.
Error Handling: Implement robust error handling within the AGI scripts (e.g., handling failed API calls, invalid JSON responses) and within the dialplan (e.g., handling AGI failures, different DIALSTATUS results).
Logging: Utilize Asterisk's Verbose() and NoOp() dialplan applications and Python's logging within AGI scripts to trace execution flow during development and debugging.
6. Key Context Variables:

Internal API Base URL: http://127.0.0.1:5000
AGI Script Directory: /var/lib/asterisk/agi-bin/
Asterisk Config Directory: /etc/asterisk/
Database/Usernames: Refer to sample_data.sql and .env.
7. Interaction Protocol:

Proceed with implementing Phase 11, starting with routing_lookup.agi.
Present code for review.
If you encounter discrepancies between the documentation and expected behavior, or require clarification on Asterisk implementation details, ask the user for specific guidance.
Report any unexpected errors encountered during execution.
8. Confirmation:

Before generating any AGI scripts or dialplan configuration, please confirm:
"I have processed the Master Plan, Progress Report, Handoff Document, and understand the project structure from the provided files. I confirm the backend API (Phase 10) is complete and tested. My primary and immediate focus is Phase 11: Asterisk Integration, starting with the development of the routing_lookup.agi script."