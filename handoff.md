# AI Handoff & Briefing Document: CapConduit Call Platform (v3.0 - Post-Refactor)

**Objective:** Fully assume the role of the primary AI developer for the CapConduit project (CFAP codebase). Internalize the project's **current refactored and verified state** to seamlessly proceed with the **Asterisk + ARA Integration phase**.

**1. Prerequisite Document Analysis:**

Thoroughly read and assimilate:

*   **Master Plan: CapConduit Call Platform (v3.0 - Refactored & Verified):** Understands business logic, user roles, core features, ARA focus, and *current verified status*.
*   **Progress Report: CapConduit Platform Deployment (v3.0 - Post-Refactor):** Details completed phases, confirms completion of backend refactoring and testing.
*   **AI Handoff & Briefing Document (This Document):** Synthesizes the current state, outlines the *immediate* next steps (Asterisk).
*   **Project Files (`cfap/` directory):** Includes the refactored `app/`, `tests/`, configuration files, DB files, and this documentation.

**2. Core Knowledge Internalization:**

*   **Project Goal:** Route calls from Sellers' DIDs/Campaigns to specific Call Center Clients via Asterisk, enforcing Campaign-Client link caps, using ARA for PJSIP config.
*   **Key Entities:** Users (Admin, Staff, Seller), Clients, DIDs, Campaigns, `CampaignClientSettings` (CRITICAL), CallLogs, `pjsip_*` tables (ARA).
*   **Architecture:** Nginx -> Gunicorn -> Flask (Python/SQLAlchemy) -> PostgreSQL. Asterisk interacts via ARA (reading `pjsip_*` tables) and Internal API (`POST /api/internal/log_call`).
*   **Critical Logic:**
    *   Admins manage Clients & PJSIP ARA data via API.
    *   Sellers manage Campaigns, DIDs, link them to Clients via `CampaignClientSettings` (defining caps/priority/weight) via API.
    *   *Backend API layer is now standardized (transactions, errors) and fully tested.*
    *   **Asterisk (Next Step):** Will read ARA PJSIP data, query DB/API for routing info, check caps (using `GROUP_COUNT` + total call data), perform `Dial()`, and call logging AGI.
    *   **Backend API (`/log_call`):** Logs CDR and increments `current_total_calls`. Verified via integration tests.

**3. Current State Confirmation (CRITICAL):**

Confirm understanding that:

*   Infrastructure, DB Schema (v3.0 ARA), Sample Data are complete.
*   The Flask Backend (`app/`) **has been fully refactored**:
    *   Service layer logic is complete.
    *   Transaction management is standardized in API routes.
    *   Error handling uses custom exceptions.
    *   Direct DB queries removed from routes.
*   All backend API endpoints (Auth, Admin, Seller, Internal Log Call) are functionally complete and **PASSING** their corresponding Pytest integration tests.
*   The project is **ready to begin Phase: Asterisk + ARA Integration.** Do *NOT* revisit or modify the Flask backend/services/tested APIs unless a problem is discovered *during* Asterisk integration testing that points definitively to a backend issue.

**4. Immediate Task Identification (Asterisk + ARA Integration):**

Focus *solely* on configuring Asterisk and implementing the necessary dialplan and AGI logic.

*   **A. Configure Asterisk for ARA:**
    *   `modules.conf`: Ensure `res_config_pgsql.so`, `res_pjsip.so` loaded.
    *   `extconfig.conf`: Define PostgreSQL connection; map `pjsip.conf` types to `pgsql,call_platform_db,pjsip_endpoints/aors/auths`.
    *   `res_pjsip.conf`: Define transports; point endpoint/aor/auth lookups to realtime (`config,pjsip.conf,...`).
    *   `sorcery.conf`: Configure if needed, or ensure basic PJSIP objects use config backend.
    *   *Verification:* Use Asterisk CLI (`realtime load`, `pjsip show endpoints`, etc.) to confirm clients from DB appear.

*   **B. Develop Asterisk Dialplan (`extensions.conf`):**
    *   Define entry context (e.g., `[from-pstn]`).
    *   `Answer()`
    *   Lookup Campaign/User/DID info (via `func_odbc` or simple AGI querying DB based on `${CHANNEL(dnid)}`). Store results (Campaign ID, Strategy, Timeout, User ID, DID ID) in channel variables. Handle lookup failures.
    *   Fetch Eligible Client Settings (via `func_odbc` or AGI querying DB based on Campaign ID, filtering by active status for Setting & Client). Store ordered results (including PJSIP identifier, caps, priority, weight). Handle no settings found.
    *   Loop/Select Target:
        *   Iterate through settings based on Strategy variable.
        *   Check Total Cap: `GotoIf($[${SETTING_CURRENT_TOTAL} >= ${SETTING_TOTAL_ALLOWED}]?next_target)` (handle NULL allowed).
        *   Check Concurrency: Define `GROUP(ccs-${SETTING_ID})`. Use `GotoIf($[${GROUP_COUNT(${GROUP_NAME})} >= ${SETTING_MAX_CC}]?next_target)`.
        *   Set Call Group: `Set(GROUP()=${GROUP_NAME})`.
        *   Store Attempted Setting ID: `Set(EFFECTIVE_CCS_ID=${SETTING_ID})`. Also store User/Campaign/DID IDs.
        *   `Dial(PJSIP/${CLIENT_IDENTIFIER},${DIAL_TIMEOUT},ghH)` (gH options for hangup handling).
        *   Handle `DIALSTATUS`: If ANSWER, `Goto(done)`. If BUSY/NOANSWER/etc., `Goto(next_target)` if strategy allows. Handle channel unavailable/congestion.
    *   `Hangup()` if no target reached/answered.
    *   Define `h` extension: `AGI(cdr_logger.agi)`.

*   **C. Develop AGI Script (`cdr_logger.agi`):**
    *   Location: `/var/lib/asterisk/agi-bin/cdr_logger.agi`. Permissions: `chmod +x`. Shebang: `#!/opt/call_platform/venv/bin/python` (or correct venv path).
    *   Language: Python 3.
    *   Functionality:
        *   Import `requests`, `sys`, `os`, `json`, `datetime`, AGI library (e.g., `python-agi`).
        *   Read AGI variables: `agi.get_variable('UNIQUEID')`, `agi.get_variable('LINKEDID')`, `agi.get_variable('EFFECTIVE_CCS_ID')`, CDR times, CallerID, DNID, DIALSTATUS, HANGUPCAUSE, User/Campaign/DID IDs (passed from dialplan).
        *   Construct JSON payload matching `LogCallRequestSchema`. Handle potential `None` values for IDs if call rejected early. Map AGI vars to schema keys (e.g., `agi.get_variable('CDR(start)')` -> `timestampStart`). Convert timestamps to ISO 8601 UTC format.
        *   Read `INTERNAL_API_TOKEN` from env var or config file accessible to Asterisk user.
        *   Make `POST` request to `http://127.0.0.1:5000/api/internal/log_call` with JSON payload and `X-Internal-API-Token` header.
        *   Log success/failure of API call using AGI `verbose()` or standard Python logging directed appropriately. Handle request exceptions gracefully.

**5. Execution Mindset & Approach:**

*   **Strict adherence to Asterisk Integration plan.** Avoid backend changes unless integration reveals a clear backend bug.
*   **Incremental Testing:** Configure ARA -> Test CLI. Develop Dialplan context -> Test lookups. Develop AGI -> Test standalone -> Test in `h` ext. Use `agi set debug on`, `core set verbose 5`.
*   **Consistency:** Follow existing Python style. Match Asterisk config conventions.
*   **Security:** Protect API token. Set AGI script permissions. Run as appropriate user.
*   **Error Handling:** Robust checks in dialplan (`GotoIf`, `Hangup`) and AGI (`try...except`).

**6. Key Context Variables:**

*   Internal Log API: `http://127.0.0.1:5000/api/internal/log_call`
*   DB Connection for ARA: Defined in `extconfig.conf` (using details from `.env`).
*   AGI Directory: `/var/lib/asterisk/agi-bin/`
*   Asterisk Config Dir: `/etc/asterisk/`

**7. Interaction Protocol:**

1.  Proceed with configuring Asterisk ARA (`extconfig.conf`, `res_config_pgsql`, `res_pjsip`, `sorcery.conf`). Present config files for review.
2.  Develop dialplan logic (`extensions.conf`). Present changes.
3.  Develop `cdr_logger.agi` script. Present script.
4.  Report issues encountered during Asterisk configuration or testing *clearly distinguishing between potential Asterisk config issues and suspected backend API issues*.

**8. Confirmation:**

Before generating Asterisk configs, confirm: *"I have processed the updated Master Plan, Progress Report, and Handoff Document. I confirm the backend API and database (v3.0) have been refactored, tested via Pytest (all tests passing), and are considered complete. My sole focus now is the Asterisk + ARA Integration phase: Configuring Asterisk for ARA using PostgreSQL and developing the corresponding dialplan and logging AGI script."*