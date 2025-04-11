-- Clear existing data (Optional - use if you only want this exact data)
-- DELETE FROM balance_adjustments;
-- DELETE FROM notifications;
-- DELETE FROM did_requests;
-- DELETE FROM rule_targets;
-- DELETE FROM rule_campaigns;
-- DELETE FROM forwarding_rules;
-- DELETE FROM campaign_dids;
-- DELETE FROM dids;
-- DELETE FROM targets;
-- DELETE FROM campaigns;
-- DELETE FROM users WHERE role != 'admin'; -- Keep admin if exists
-- DELETE FROM users WHERE role = 'admin' AND username != 'admin_user'; -- Keep specific admin

-- Reset sequences (Optional - if you want IDs to start from 1)
-- SELECT setval(pg_get_serial_sequence('users', 'id'), coalesce(max(id), 0)+1 , false) FROM users;
-- SELECT setval(pg_get_serial_sequence('dids', 'id'), coalesce(max(id), 0)+1 , false) FROM dids;
-- SELECT setval(pg_get_serial_sequence('campaigns', 'id'), coalesce(max(id), 0)+1 , false) FROM campaigns;
-- SELECT setval(pg_get_serial_sequence('targets', 'id'), coalesce(max(id), 0)+1 , false) FROM targets;
-- SELECT setval(pg_get_serial_sequence('forwarding_rules', 'id'), coalesce(max(id), 0)+1 , false) FROM forwarding_rules;
-- SELECT setval(pg_get_serial_sequence('balance_adjustments', 'id'), coalesce(max(id), 0)+1 , false) FROM balance_adjustments;
-- SELECT setval(pg_get_serial_sequence('notifications', 'id'), coalesce(max(id), 0)+1 , false) FROM notifications;
-- SELECT setval(pg_get_serial_sequence('did_requests', 'id'), coalesce(max(id), 0)+1 , false) FROM did_requests;
-- SELECT setval(pg_get_serial_sequence('call_detail_records', 'id'), coalesce(max(id), 0)+1 , false) FROM call_detail_records;


BEGIN; -- Start Transaction

-- === Users ===
-- Ensure passwords below are hashed using your app's Bcrypt logic if running directly
-- For this SQL script, we'll insert placeholder hashes. Replace if needed.
-- Hash for "Password123!" (Example - generate this with bcrypt in Python)
-- python -c "import bcrypt; print(bcrypt.hashpw(b'Password123!', bcrypt.gensalt()).decode('utf-8'))"
-- Example hash: $2b$12$EXAMPLEHASHFORADMINUSERXXXXXXXXXXXXXXXXXXXXXX.
-- Example hash: $2b$12$EXAMPLEHASHFORUSERALICEXXXXXXXXXXXXXXXXXXXXX.
-- Example hash: $2b$12$EXAMPLEHASHFORUSERBOBXXXXXXXXXXXXXXXXXXXXXX.

INSERT INTO users (username, email, password_hash, role, balance, status, contact_name, company_name) VALUES
('admin_user', 'admin@capconduit.test', '$2b$12$EXAMPLEHASHFORADMINUSERXXXXXXXXXXXXXXXXXXXXXX.', 'admin', 0.0000, 'active', 'Platform Admin', 'CapConduit HQ'),
('alice_seller', 'alice@seller.test', '$2b$12$EXAMPLEHASHFORUSERALICEXXXXXXXXXXXXXXXXXXXXX.', 'user', 100.0000, 'active', 'Alice Smith', 'Alice Leads Co'),
('bob_broker', 'bob@broker.test', '$2b$12$EXAMPLEHASHFORUSERBOBXXXXXXXXXXXXXXXXXXXXXX.', 'user', 75.5000, 'active', 'Bob Jones', 'Bob Call Brokerage')
ON CONFLICT (username) DO NOTHING; -- Avoid errors if admin_user already exists


-- === DIDs ===
-- Get User IDs (adjust if IDs are different after inserts/resets)
DO $$ DECLARE admin_id INT; alice_id INT; bob_id INT;
BEGIN
   SELECT id INTO admin_id FROM users WHERE username = 'admin_user';
   SELECT id INTO alice_id FROM users WHERE username = 'alice_seller';
   SELECT id INTO bob_id FROM users WHERE username = 'bob_broker';

   INSERT INTO dids (number, country_code, number_type, assignment_status, assigned_user_id, provider_source, monthly_cost) VALUES
   ('+18005551001', 'US', 'TFN', 'assigned', alice_id, 'Twilio', 2.00),        -- Alice's TFN
   ('+12125551002', 'US', 'Local', 'assigned', alice_id, 'Bandwidth', 1.00),   -- Alice's NY Local
   ('+13105551003', 'US', 'Local', 'assigned', bob_id, 'Twilio', 1.00),        -- Bob's CA Local
   ('+442075551004', 'GB', 'Local', 'unassigned', NULL, 'Test Provider', 1.20), -- Unassigned UK
   ('+18885551005', 'US', 'TFN', 'unassigned', NULL, 'Bandwidth', 2.00);       -- Unassigned TFN

-- === Campaigns ===
   INSERT INTO campaigns (user_id, name, description, status, cap_daily, cap_hourly) VALUES
   (alice_id, 'Alice Google Ads Leads', 'Insurance leads from Google', 'active', 200, 25),
   (alice_id, 'Alice Facebook Leads', 'Home service leads from FB', 'active', 100, NULL),
   (bob_id, 'Bob SEO Calls', 'Organic SEO traffic calls', 'active', 50, 10),
   (bob_id, 'Bob Partner Calls', 'Calls from partner network', 'inactive', NULL, NULL); -- Inactive campaign

-- === Link DIDs to Campaigns ===
   -- Link +18005551001 to Alice Google Ads Leads (assuming DID ID 1, Campaign ID 1)
   INSERT INTO campaign_dids (campaign_id, did_id) VALUES
   ((SELECT id FROM campaigns WHERE user_id = alice_id AND name = 'Alice Google Ads Leads'), (SELECT id FROM dids WHERE number = '+18005551001')),
   ((SELECT id FROM campaigns WHERE user_id = alice_id AND name = 'Alice Facebook Leads'), (SELECT id FROM dids WHERE number = '+12125551002'));
   -- Link +13105551003 to Bob SEO Calls (assuming DID ID 3, Campaign ID 3)
   INSERT INTO campaign_dids (campaign_id, did_id) VALUES
   ((SELECT id FROM campaigns WHERE user_id = bob_id AND name = 'Bob SEO Calls'), (SELECT id FROM dids WHERE number = '+13105551003'));

-- === Targets ===
   INSERT INTO targets (user_id, name, client_name, destination_type, destination_uri, concurrency_limit, total_calls_allowed, status) VALUES
   (alice_id, 'Alice Client X', 'Client X Insurance', 'SIP', 'sip:sales@clientx.com:5060', 10, 5000, 'active'),
   (alice_id, 'Alice Client Y', 'Client Y Home Svcs', 'SIP', 'sip:intake@clienty.org:5066', 5, NULL, 'active'),
   (bob_id, 'Bob Client Z', 'Client Z Corp', 'SIP', 'sip:1001@bob-client-z.pbx.local', 20, 10000, 'active'),
   (bob_id, 'Bob Client W (Overflow)', 'Client W Backup', 'IAX2', 'iax2:guest@clientw.com/iax-context', 2, NULL, 'active');

-- === Forwarding Rules ===
   INSERT INTO forwarding_rules (user_id, name, routing_strategy, min_billable_duration, status) VALUES
   (alice_id, 'Alice Google Ads to Client X', 'Primary', 30, 'active'),
   (alice_id, 'Alice FB to Client Y', 'Primary', 60, 'active'),
   (bob_id, 'Bob SEO to Client Z (Primary)', 'Priority', 15, 'active');

-- === Link Rules to Campaigns ===
   INSERT INTO rule_campaigns (rule_id, campaign_id) VALUES
   ((SELECT id FROM forwarding_rules WHERE user_id = alice_id AND name = 'Alice Google Ads to Client X'), (SELECT id FROM campaigns WHERE user_id = alice_id AND name = 'Alice Google Ads Leads')),
   ((SELECT id FROM forwarding_rules WHERE user_id = alice_id AND name = 'Alice FB to Client Y'), (SELECT id FROM campaigns WHERE user_id = alice_id AND name = 'Alice Facebook Leads')),
   ((SELECT id FROM forwarding_rules WHERE user_id = bob_id AND name = 'Bob SEO to Client Z (Primary)'), (SELECT id FROM campaigns WHERE user_id = bob_id AND name = 'Bob SEO Calls'));

-- === Link Rules to Targets ===
   INSERT INTO rule_targets (rule_id, target_id, priority, weight) VALUES
   -- Alice Google Ads -> Client X
   ((SELECT id FROM forwarding_rules WHERE user_id = alice_id AND name = 'Alice Google Ads to Client X'), (SELECT id FROM targets WHERE user_id = alice_id AND name = 'Alice Client X'), 0, 100),
   -- Alice FB -> Client Y
   ((SELECT id FROM forwarding_rules WHERE user_id = alice_id AND name = 'Alice FB to Client Y'), (SELECT id FROM targets WHERE user_id = alice_id AND name = 'Alice Client Y'), 0, 100),
   -- Bob SEO -> Client Z (Priority 0), Client W (Priority 1)
   ((SELECT id FROM forwarding_rules WHERE user_id = bob_id AND name = 'Bob SEO to Client Z (Primary)'), (SELECT id FROM targets WHERE user_id = bob_id AND name = 'Bob Client Z'), 0, 100),
   ((SELECT id FROM forwarding_rules WHERE user_id = bob_id AND name = 'Bob SEO to Client Z (Primary)'), (SELECT id FROM targets WHERE user_id = bob_id AND name = 'Bob Client W (Overflow)'), 1, 100);

END $$; -- End DO block

-- === System Settings ===
-- Ensure billing rate exists (will update if already present)
INSERT INTO system_settings (setting_key, setting_value, description)
VALUES ('billing_rate_per_minute', '0.0600', 'Global cost per minute charged to user balance (USD)')
ON CONFLICT (setting_key) DO UPDATE SET
    setting_value = EXCLUDED.setting_value,
    description = EXCLUDED.description,
    updated_at = CURRENT_TIMESTAMP;


COMMIT; -- Commit Transaction

VACUUM ANALYZE; -- Update statistics for the query planner

SELECT 'Sample data loaded successfully!' AS status;