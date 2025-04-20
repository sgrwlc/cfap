-- CapConduit Redesigned Sample Data (v3.0 - ARA Focused) - CORRECTED v3
-- For database: call_platform_db
-- Assumes schema v3.0 is already applied.

BEGIN; -- Start Transaction

-- === Users ===
-- Passwords below are example bcrypt hashes for "Password123!"
-- Generate real hashes using your application's bcrypt library.
INSERT INTO users (username, email, password_hash, role, status, full_name, company_name) VALUES
('platform_admin', 'admin@capconduit.local', '$2a$12$yP4MEm9XPNvdDUR0bWUXrOKfm/RXWCVDmNH6Piol9VqI1RdG3sJJG', 'admin', 'active', 'Admin User', 'CapConduit HQ'),
('ops_staff', 'staff@capconduit.local', '$2a$12$yP4MEm9XPNvdDUR0bWUXrOKfm/RXWCVDmNH6Piol9VqI1RdG3sJJG', 'staff', 'active', 'Operations Staff', 'CapConduit HQ'),
('seller_alice', 'alice@seller.xyz', '$2a$12$yP4MEm9XPNvdDUR0bWUXrOKfm/RXWCVDmNH6Piol9VqI1RdG3sJJG', 'user', 'active', 'Alice Wonderland', 'Alice Leads Ltd.'),
('seller_bob', 'bob@broker.xyz', '$2a$12$yP4MEm9XPNvdDUR0bWUXrOKfm/RXWCVDmNH6Piol9VqI1RdG3sJJG', 'user', 'active', 'Bob The Broker', 'Bob Call Services')
ON CONFLICT (username) DO NOTHING;

-- === Clients (Call Centers) ===
-- The `client_identifier` is crucial as it will likely be the PJSIP endpoint ID.
INSERT INTO clients (client_identifier, name, department, status, notes, created_by) VALUES
('client_alpha_sales', 'Alpha Corp', 'Sales Department', 'active', 'Primary client for tech leads.', (SELECT id FROM users WHERE username = 'platform_admin')),
('client_beta_support', 'Beta Industries', 'Customer Support', 'active', 'Handles overflow support calls.', (SELECT id FROM users WHERE username = 'platform_admin')),
('client_gamma_intake', 'Gamma Services', 'New Client Intake', 'active', 'Requires authentication. High volume.', (SELECT id FROM users WHERE username = 'ops_staff')),
('client_delta_partners', 'Delta Partners Inc', 'Partner Relations', 'inactive', 'Currently inactive campaign.', (SELECT id FROM users WHERE username = 'ops_staff'))
ON CONFLICT (client_identifier) DO NOTHING;

-- Start PL/pgSQL block to handle variable assignment
DO $$
DECLARE
    admin_user_id INT;
    staff_user_id INT;
    alice_user_id INT;
    bob_user_id INT;
    client_alpha_id INT;
    client_beta_id INT;
    client_gamma_id INT;
    client_delta_id INT;
    did_alice_1_id INT;
    did_alice_2_id INT;
    did_bob_1_id INT;
    did_alice_uk_id INT;
    campaign_alice_prio_id INT;
    campaign_alice_rr_id INT;
    campaign_bob_prio_id INT;
    ccs_alice_prio_alpha_id INT;
    ccs_alice_prio_beta_id INT;
    ccs_alice_rr_beta_id INT;
    ccs_alice_rr_gamma_id INT;
    ccs_bob_prio_gamma_id INT;
    ccs_bob_prio_alpha_id INT;
    ccs_bob_prio_delta_id INT;
BEGIN
    -- Get User IDs
    SELECT id INTO admin_user_id FROM users WHERE username = 'platform_admin';
    SELECT id INTO staff_user_id FROM users WHERE username = 'ops_staff';
    SELECT id INTO alice_user_id FROM users WHERE username = 'seller_alice';
    SELECT id INTO bob_user_id FROM users WHERE username = 'seller_bob';

    -- Get Client IDs
    SELECT id INTO client_alpha_id FROM clients WHERE client_identifier = 'client_alpha_sales';
    SELECT id INTO client_beta_id FROM clients WHERE client_identifier = 'client_beta_support';
    SELECT id INTO client_gamma_id FROM clients WHERE client_identifier = 'client_gamma_intake';
    SELECT id INTO client_delta_id FROM clients WHERE client_identifier = 'client_delta_partners';

    -- === PJSIP Configuration (Matching Clients) ===

    -- PJSIP Endpoints (id must match client_identifier)
    INSERT INTO pjsip_endpoints (id, client_id, transport, aors, context, allow, outbound_auth, callerid, from_user, from_domain) VALUES
    ('client_alpha_sales', client_alpha_id, 'transport-udp', 'client_alpha_sales', 'from-capconduit', 'ulaw,alaw', NULL, 'Alice Leads <+18005551111>', 'alice_out', 'capconduit.local'),
    ('client_beta_support', client_beta_id, 'transport-udp', 'client_beta_support', 'from-capconduit', 'ulaw,alaw,gsm', NULL, 'CapConduit <+18885552222>', NULL, NULL),
    ('client_gamma_intake', client_gamma_id, 'transport-udp', 'client_gamma_intake', 'from-capconduit', 'ulaw', 'auth_to_gamma', 'Bob Broker <+19005553333>', 'bob_calls', 'capconduit.local'),
    ('client_delta_partners', client_delta_id, 'transport-udp', 'client_delta_partners', 'from-capconduit', 'ulaw', NULL, 'System <+17775554444>', NULL, NULL)
    ON CONFLICT (id) DO NOTHING; -- Added semicolon

    -- PJSIP AORs (Address of Record - Where to send calls)
    INSERT INTO pjsip_aors (id, client_id, contact, max_contacts, qualify_frequency) VALUES
    ('client_alpha_sales', client_alpha_id, 'sip:10.10.10.1:5060', 1, 60),
    ('client_beta_support', client_beta_id, 'sip:sip.betasupport.com;transport=udp', 1, 60),
    ('client_gamma_intake', client_gamma_id, 'sip:intake@gamma.internal:5064', 1, 30),
    ('client_delta_partners', client_delta_id, 'sip:192.168.50.100', 1, 0)
    ON CONFLICT (id) DO NOTHING; -- Added semicolon

    -- PJSIP Auths (Only needed if WE need to authenticate TO the client)
    INSERT INTO pjsip_auths (id, client_id, auth_type, username, password, realm) VALUES
    ('auth_to_gamma', client_gamma_id, 'userpass', 'capconduit_user', 'GammaSecretPassw0rd', 'gamma.internal')
    ON CONFLICT (id) DO NOTHING; -- Added semicolon


    -- === DIDs ===
    INSERT INTO dids (number, user_id, status, description) VALUES
    ('+18005550101', alice_user_id, 'active', 'Alice Campaign A TFN'),
    ('+12125550102', alice_user_id, 'active', 'Alice Campaign B Local NY'),
    ('+13105550103', bob_user_id, 'active', 'Bob Campaign C Local CA'),
    ('+442075550104', alice_user_id, 'inactive', 'Alice UK Number (Inactive)'); -- Added semicolon (end of statement)

    -- Select IDs reliably after the insert
    SELECT id INTO did_alice_1_id FROM dids WHERE number = '+18005550101';
    SELECT id INTO did_alice_2_id FROM dids WHERE number = '+12125550102';
    SELECT id INTO did_bob_1_id FROM dids WHERE number = '+13105550103';
    SELECT id INTO did_alice_uk_id FROM dids WHERE number = '+442075550104';

    -- === Campaigns ===
    INSERT INTO campaigns (user_id, name, status, routing_strategy, dial_timeout_seconds, description) VALUES
    (alice_user_id, 'Alice Priority Tech Leads', 'active', 'priority', 25, 'Sends tech support leads, Client Alpha first.'),
    (alice_user_id, 'Alice RoundRobin Support', 'active', 'round_robin', 35, 'Distributes support calls between Beta and Gamma.'),
    (bob_user_id, 'Bob Weighted Sales Calls', 'active', 'weighted', 20, 'Sends sales calls mainly to Gamma, fallback Alpha.'); -- Added semicolon (end of statement)

    -- Select IDs reliably after the insert
    SELECT id INTO campaign_alice_prio_id FROM campaigns WHERE user_id = alice_user_id AND name = 'Alice Priority Tech Leads';
    SELECT id INTO campaign_alice_rr_id FROM campaigns WHERE user_id = alice_user_id AND name = 'Alice RoundRobin Support';
    SELECT id INTO campaign_bob_prio_id FROM campaigns WHERE user_id = bob_user_id AND name = 'Bob Weighted Sales Calls';


    -- === Campaign DIDs (Link DIDs to Campaigns) ===
    INSERT INTO campaign_dids (campaign_id, did_id) VALUES
    (campaign_alice_prio_id, did_alice_1_id),
    (campaign_alice_rr_id, did_alice_2_id),
    (campaign_bob_prio_id, did_bob_1_id); -- Added semicolon (end of statement)


    -- === Campaign Client Settings (The Core Logic) ===
    INSERT INTO campaign_client_settings (campaign_id, client_id, status, max_concurrency, total_calls_allowed, current_total_calls, forwarding_priority, weight) VALUES
    (campaign_alice_prio_id, client_alpha_id, 'active', 10, 5000, 0, 0, 100),
    (campaign_alice_prio_id, client_beta_id, 'active', 5, NULL, 0, 1, 100),
    (campaign_alice_rr_id, client_beta_id, 'active', 8, 1000, 0, 0, 100),
    (campaign_alice_rr_id, client_gamma_id, 'active', 15, 2000, 0, 1, 100),
    (campaign_bob_prio_id, client_gamma_id, 'active', 20, 10000, 0, 0, 70),
    (campaign_bob_prio_id, client_alpha_id, 'active', 5, 2000, 0, 1, 30),
    (campaign_bob_prio_id, client_delta_id, 'inactive', 2, 100, 0, 2, 100);

    -- Select IDs reliably after the insert
    SELECT id INTO ccs_alice_prio_alpha_id FROM campaign_client_settings WHERE campaign_id = campaign_alice_prio_id AND client_id = client_alpha_id;
    SELECT id INTO ccs_alice_prio_beta_id FROM campaign_client_settings WHERE campaign_id = campaign_alice_prio_id AND client_id = client_beta_id;
    SELECT id INTO ccs_alice_rr_beta_id FROM campaign_client_settings WHERE campaign_id = campaign_alice_rr_id AND client_id = client_beta_id;
    SELECT id INTO ccs_alice_rr_gamma_id FROM campaign_client_settings WHERE campaign_id = campaign_alice_rr_id AND client_id = client_gamma_id;
    SELECT id INTO ccs_bob_prio_gamma_id FROM campaign_client_settings WHERE campaign_id = campaign_bob_prio_id AND client_id = client_gamma_id;
    SELECT id INTO ccs_bob_prio_alpha_id FROM campaign_client_settings WHERE campaign_id = campaign_bob_prio_id AND client_id = client_alpha_id;
    SELECT id INTO ccs_bob_prio_delta_id FROM campaign_client_settings WHERE campaign_id = campaign_bob_prio_id AND client_id = client_delta_id;

    -- === Call Logs (Example Scenarios) ===
    INSERT INTO call_logs (user_id, campaign_id, did_id, client_id, campaign_client_setting_id, incoming_did_number, caller_id_num, timestamp_start, timestamp_answered, timestamp_end, duration_seconds, billsec_seconds, call_status, hangup_cause_code, hangup_cause_text, asterisk_uniqueid, asterisk_linkedid) VALUES
    (alice_user_id, campaign_alice_prio_id, did_alice_1_id, client_alpha_id, ccs_alice_prio_alpha_id, '+18005550101', '+15551234567', NOW() - INTERVAL '2 hour', NOW() - INTERVAL '1 hour 59 minutes 50 seconds', NOW() - INTERVAL '1 hour 58 minutes', 110, 100, 'ANSWERED', 16, 'Normal Clearing', 'uniqueid-call-001', 'linkedid-call-001'),
    (alice_user_id, campaign_alice_prio_id, did_alice_1_id, client_beta_id, ccs_alice_prio_beta_id, '+18005550101', '+15557654321', NOW() - INTERVAL '1 hour', NOW() - INTERVAL '59 minutes 45 seconds', NOW() - INTERVAL '59 minutes', 45, 30, 'ANSWERED', 16, 'Normal Clearing', 'uniqueid-call-002', 'linkedid-call-002'),
    (alice_user_id, campaign_alice_rr_id, did_alice_2_id, client_beta_id, ccs_alice_rr_beta_id, '+12125550102', '+15551112222', NOW() - INTERVAL '30 minutes', NOW() - INTERVAL '29 minutes 55 seconds', NOW() - INTERVAL '28 minutes', 115, 110, 'ANSWERED', 16, 'Normal Clearing', 'uniqueid-call-003', 'linkedid-call-003'),
    (alice_user_id, campaign_alice_rr_id, did_alice_2_id, client_gamma_id, ccs_alice_rr_gamma_id, '+12125550102', '+15553334444', NOW() - INTERVAL '20 minutes', NULL, NOW() - INTERVAL '19 minutes', 60, 0, 'NOANSWER', 19, 'No Answer from user', 'uniqueid-call-004', 'linkedid-call-004'),
    (bob_user_id, campaign_bob_prio_id, did_bob_1_id, client_gamma_id, ccs_bob_prio_gamma_id, '+13105550103', '+15559998888', NOW() - INTERVAL '10 minutes', NOW() - INTERVAL '9 minutes 50 seconds', NOW() - INTERVAL '8 minutes', 110, 100, 'ANSWERED', 16, 'Normal Clearing', 'uniqueid-call-005', 'linkedid-call-005'),
    (bob_user_id, campaign_bob_prio_id, did_bob_1_id, NULL, NULL, '+13105550103', '+15557776666', NOW() - INTERVAL '5 minutes', NULL, NOW() - INTERVAL '5 minutes', 0, 0, 'REJECTED_TOTAL', 0, 'Rejected - Total Calls Cap', 'uniqueid-call-006', 'linkedid-call-006'); -- Added semicolon (end of statement)

    -- Update counters based on sample calls (Manual simulation for sample data)
    UPDATE campaign_client_settings SET current_total_calls = current_total_calls + 1 WHERE id = ccs_alice_prio_alpha_id;
    UPDATE campaign_client_settings SET current_total_calls = current_total_calls + 1 WHERE id = ccs_alice_prio_beta_id;
    UPDATE campaign_client_settings SET current_total_calls = current_total_calls + 1 WHERE id = ccs_alice_rr_beta_id;
    UPDATE campaign_client_settings SET current_total_calls = current_total_calls + 1 WHERE id = ccs_bob_prio_gamma_id;
    UPDATE campaign_client_settings SET current_total_calls = total_calls_allowed WHERE id = ccs_bob_prio_gamma_id AND total_calls_allowed IS NOT NULL;

END $$; -- End DO block


COMMIT; -- Commit Transaction

VACUUM ANALYZE; -- Update statistics for the query planner

SELECT 'CapConduit Sample Data v3.0 (ARA Focused) loaded successfully!' AS status;