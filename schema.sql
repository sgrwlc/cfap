-- CapConduit Platform Database Schema
-- Version: 2.0 (Includes fixes and auto updated_at trigger)
-- PostgreSQL database setup script

-- Make script idempotent by dropping existing tables in reverse order of dependency
-- Using CASCADE simplifies dropping even with foreign keys
DROP TABLE IF EXISTS balance_adjustments CASCADE;
DROP TABLE IF EXISTS call_detail_records CASCADE;
DROP TABLE IF EXISTS notifications CASCADE;
DROP TABLE IF EXISTS did_requests CASCADE;
DROP TABLE IF EXISTS rule_targets CASCADE;
DROP TABLE IF EXISTS rule_campaigns CASCADE;
DROP TABLE IF EXISTS campaign_dids CASCADE;
DROP TABLE IF EXISTS system_settings CASCADE;
DROP TABLE IF EXISTS forwarding_rules CASCADE;
DROP TABLE IF EXISTS targets CASCADE;
DROP TABLE IF EXISTS campaigns CASCADE;
DROP TABLE IF EXISTS dids CASCADE;
DROP TABLE IF EXISTS users CASCADE;


-- Trigger function to automatically update 'updated_at' column
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
   NEW.updated_at = timezone('utc', now()); -- Ensure UTC timezone
   RETURN NEW;
END;
$$ language 'plpgsql';


-- Users table: Stores platform administrators and call seller users
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(80) UNIQUE NOT NULL,
    email VARCHAR(120) UNIQUE NOT NULL,
    password_hash VARCHAR(128) NOT NULL, -- Store hashed passwords only!
    role VARCHAR(10) NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')), -- 'admin' or 'user'
    balance NUMERIC(10, 4) NOT NULL DEFAULT 0.0000, -- Example: Up to 999,999.9999
    status VARCHAR(10) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'suspended')),
    contact_name VARCHAR(100),
    company_name VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now()),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now())
);
-- Indexes for users table
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_users_status ON users(status);
-- Trigger for users updated_at
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- DIDs table: Stores all phone numbers managed by the platform
CREATE TABLE dids (
    id SERIAL PRIMARY KEY,
    number VARCHAR(50) UNIQUE NOT NULL, -- E.164 format recommended (+1xxxxxxxxxx)
    country_code VARCHAR(5), -- e.g., US, CA, GB
    number_type VARCHAR(20) CHECK (number_type IN ('TFN', 'Local', 'Mobile', 'Other')), -- Toll-Free, Local, etc.
    assigned_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL, -- Who owns/is assigned this DID
    assignment_status VARCHAR(20) NOT NULL DEFAULT 'unassigned' CHECK (assignment_status IN ('unassigned', 'assigned', 'pending_request')),
    provider_source VARCHAR(50), -- Optional: Where the Admin got it (e.g., 'Twilio', 'Bandwidth')
    monthly_cost NUMERIC(8, 2), -- Optional: For Admin tracking
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now()),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now())
);
-- Indexes for dids table
CREATE INDEX idx_dids_number ON dids(number);
CREATE INDEX idx_dids_assigned_user_id ON dids(assigned_user_id);
CREATE INDEX idx_dids_assignment_status ON dids(assignment_status);
-- Trigger for dids updated_at
CREATE TRIGGER update_dids_updated_at BEFORE UPDATE ON dids FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- Campaigns table: User-defined campaigns
CREATE TABLE campaigns (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, -- Ensures campaigns are deleted if user is deleted
    name VARCHAR(100) NOT NULL,
    description TEXT,
    ad_platform VARCHAR(100),
    country VARCHAR(50),
    status VARCHAR(10) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    cap_hourly INTEGER, -- Max calls per hour (NULL means no limit)
    cap_daily INTEGER, -- Max calls per day (NULL means no limit)
    cap_total INTEGER, -- Max calls overall (NULL means no limit)
    current_hourly_calls INTEGER NOT NULL DEFAULT 0,
    current_daily_calls INTEGER NOT NULL DEFAULT 0,
    current_total_calls INTEGER NOT NULL DEFAULT 0,
    last_hourly_reset TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now()),
    last_daily_reset TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now()),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now()),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now()),
    UNIQUE (user_id, name) -- Campaign name must be unique per user
);
-- Indexes for campaigns table
CREATE INDEX idx_campaigns_user_id ON campaigns(user_id);
CREATE INDEX idx_campaigns_status ON campaigns(status);
-- Trigger for campaigns updated_at
CREATE TRIGGER update_campaigns_updated_at BEFORE UPDATE ON campaigns FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- Campaign_DIDs table: Junction table linking campaigns to DIDs (Many-to-Many)
CREATE TABLE campaign_dids (
    campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    did_id INTEGER NOT NULL REFERENCES dids(id) ON DELETE CASCADE,
    PRIMARY KEY (campaign_id, did_id) -- Ensures unique pairings
);
-- Indexes for campaign_dids table (Primary Key usually creates these, but explicit doesn't hurt)
CREATE INDEX idx_campaign_dids_campaign_id ON campaign_dids(campaign_id);
CREATE INDEX idx_campaign_dids_did_id ON campaign_dids(did_id);


-- Targets table: Client endpoints
CREATE TABLE targets (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    client_name VARCHAR(100),
    description TEXT,
    destination_type VARCHAR(10) NOT NULL CHECK (destination_type IN ('SIP', 'IAX2')),
    destination_uri VARCHAR(255) NOT NULL, -- e.g., sip:user@host:port or iax2:user@host/context
    total_calls_allowed INTEGER, -- Max calls this target can EVER receive (decremented, NULL means no limit)
    current_total_calls_delivered INTEGER NOT NULL DEFAULT 0, -- Counter for the above
    concurrency_limit INTEGER NOT NULL DEFAULT 1 CHECK (concurrency_limit >= 1), -- Global max simultaneous calls for this target
    status VARCHAR(10) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now()),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now()),
    UNIQUE (user_id, name) -- Target name must be unique per user
);
-- Indexes for targets table
CREATE INDEX idx_targets_user_id ON targets(user_id);
CREATE INDEX idx_targets_status ON targets(status);
-- Trigger for targets updated_at
CREATE TRIGGER update_targets_updated_at BEFORE UPDATE ON targets FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- Forwarding rules table: Defines routing logic
CREATE TABLE forwarding_rules (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    routing_strategy VARCHAR(20) NOT NULL DEFAULT 'Primary' CHECK (routing_strategy IN ('Primary', 'RoundRobin', 'Priority')),
    min_delay_between_calls INTEGER DEFAULT 0 CHECK (min_delay_between_calls >= 0), -- Seconds pause after call to same target via this rule
    min_billable_duration INTEGER DEFAULT 0 CHECK (min_billable_duration >= 0), -- Seconds threshold for billing/counting
    status VARCHAR(10) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now()),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now()),
    UNIQUE (user_id, name) -- Rule name must be unique per user
);
-- Indexes for forwarding_rules table
CREATE INDEX idx_forwarding_rules_user_id ON forwarding_rules(user_id);
CREATE INDEX idx_forwarding_rules_status ON forwarding_rules(status);
-- Trigger for forwarding_rules updated_at
CREATE TRIGGER update_forwarding_rules_updated_at BEFORE UPDATE ON forwarding_rules FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- Rule campaigns table: Links rules to source campaigns (Many-to-Many)
CREATE TABLE rule_campaigns (
    rule_id INTEGER NOT NULL REFERENCES forwarding_rules(id) ON DELETE CASCADE,
    campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    PRIMARY KEY (rule_id, campaign_id)
);
-- Indexes for rule_campaigns table
CREATE INDEX idx_rule_campaigns_rule_id ON rule_campaigns(rule_id);
CREATE INDEX idx_rule_campaigns_campaign_id ON rule_campaigns(campaign_id);


-- Rule targets table: Links rules to destination targets (Many-to-Many)
CREATE TABLE rule_targets (
    rule_id INTEGER NOT NULL REFERENCES forwarding_rules(id) ON DELETE CASCADE,
    target_id INTEGER NOT NULL REFERENCES targets(id) ON DELETE CASCADE,
    priority INTEGER DEFAULT 0, -- Used for Priority routing strategy
    weight INTEGER DEFAULT 100 CHECK (weight > 0), -- Used for Weighted Round Robin (optional)
    PRIMARY KEY (rule_id, target_id)
);
-- Indexes for rule_targets table
CREATE INDEX idx_rule_targets_rule_id ON rule_targets(rule_id);
CREATE INDEX idx_rule_targets_target_id ON rule_targets(target_id);


-- Call detail records table: Logs call attempts
CREATE TABLE call_detail_records (
    id BIGSERIAL PRIMARY KEY, -- Use BIGSERIAL for potentially large tables
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL, -- Keep CDR even if user deleted
    timestamp_start TIMESTAMP WITH TIME ZONE NOT NULL,
    timestamp_answer TIMESTAMP WITH TIME ZONE, -- NULL if not answered
    timestamp_end TIMESTAMP WITH TIME ZONE,
    duration INTEGER CHECK (duration >= 0 OR duration IS NULL), -- Total call duration in seconds (pickup to hangup)
    billable_duration INTEGER CHECK (billable_duration >= 0 OR billable_duration IS NULL), -- Duration meeting minimum threshold (in seconds)
    caller_id_num VARCHAR(50),
    caller_id_name VARCHAR(100),
    incoming_did VARCHAR(50) NOT NULL,
    campaign_id INTEGER REFERENCES campaigns(id) ON DELETE SET NULL,
    target_id INTEGER REFERENCES targets(id) ON DELETE SET NULL,
    final_status VARCHAR(30) NOT NULL, -- e.g., Connected, Rejected-VolumeCap, Rejected-ConcurrencyCap, Rejected-TargetCap, Rejected-Balance, Failed-NoRoute, TargetBusy, TargetNoAnswer, etc.
    asterisk_status_code VARCHAR(30), -- e.g., ANSWERED, BUSY, NOANSWER, FAILED
    recording_path VARCHAR(512), -- Full path to recording file
    calculated_cost NUMERIC(10, 5), -- Cost calculated based on rate and billable duration
    asterisk_uniqueid VARCHAR(50) UNIQUE, -- Asterisk's unique ID for the call leg
    asterisk_linkedid VARCHAR(50), -- Asterisk's ID linking multiple call legs
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now())
);
-- Indexes for call_detail_records table
CREATE INDEX idx_cdr_user_id ON call_detail_records(user_id);
CREATE INDEX idx_cdr_timestamp_start ON call_detail_records(timestamp_start);
CREATE INDEX idx_cdr_incoming_did ON call_detail_records(incoming_did);
CREATE INDEX idx_cdr_campaign_id ON call_detail_records(campaign_id);
CREATE INDEX idx_cdr_target_id ON call_detail_records(target_id);
CREATE INDEX idx_cdr_asterisk_uniqueid ON call_detail_records(asterisk_uniqueid);
CREATE INDEX idx_cdr_asterisk_linkedid ON call_detail_records(asterisk_linkedid);
CREATE INDEX idx_cdr_final_status ON call_detail_records(final_status);


-- Balance adjustments table: Logs manual admin changes
CREATE TABLE balance_adjustments (
    id SERIAL PRIMARY KEY,
    admin_user_id INTEGER NOT NULL REFERENCES users(id), -- User performing the action
    target_user_id INTEGER NOT NULL REFERENCES users(id), -- User whose balance is changed
    amount NUMERIC(10, 4) NOT NULL, -- Positive for addition, negative for subtraction
    reason TEXT,
    adjustment_timestamp TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now())
);
-- Indexes for balance_adjustments table
CREATE INDEX idx_balance_adjustments_target_user_id ON balance_adjustments(target_user_id);
CREATE INDEX idx_balance_adjustments_admin_user_id ON balance_adjustments(admin_user_id);
CREATE INDEX idx_balance_adjustments_timestamp ON balance_adjustments(adjustment_timestamp);


-- Notifications table: Stores user notifications
CREATE TABLE notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    message TEXT NOT NULL,
    notification_type VARCHAR(10) NOT NULL DEFAULT 'info' CHECK (notification_type IN ('info', 'warning', 'error', 'success')),
    related_entity_type VARCHAR(20), -- e.g., 'campaign', 'target', 'did' (optional)
    related_entity_id INTEGER, -- (optional)
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now()),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now()) -- Added missing column
);
-- Indexes for notifications table
CREATE INDEX idx_notifications_user_id ON notifications(user_id);
CREATE INDEX idx_notifications_is_read ON notifications(is_read);
CREATE INDEX idx_notifications_created_at ON notifications(created_at);
-- Trigger for notifications updated_at
CREATE TRIGGER update_notifications_updated_at BEFORE UPDATE ON notifications FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- DID requests table: Tracks user requests for numbers
CREATE TABLE did_requests (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    request_details TEXT, -- e.g., "Need USA TFN for marketing campaign"
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'assigned', 'rejected')),
    admin_notes TEXT, -- Notes from admin during processing
    assigned_did_id INTEGER REFERENCES dids(id) ON DELETE SET NULL, -- Link to the DID if assigned
    requested_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now()),
    processed_at TIMESTAMP WITH TIME ZONE -- Set when admin processes it
);
-- Indexes for did_requests table
CREATE INDEX idx_did_requests_user_id ON did_requests(user_id);
CREATE INDEX idx_did_requests_status ON did_requests(status);


-- System settings table: Stores global settings (like the billing rate)
CREATE TABLE system_settings (
    setting_key VARCHAR(50) PRIMARY KEY,
    setting_value TEXT,
    description TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now())
);
-- Trigger for system_settings updated_at
CREATE TRIGGER update_system_settings_updated_at BEFORE UPDATE ON system_settings FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Insert default rate
INSERT INTO system_settings (setting_key, setting_value, description)
VALUES ('billing_rate_per_minute', '0.0600', 'Global cost per minute charged to user balance (USD)');


-- Grant permissions to the application user (replace 'call_platform_user' if needed)
-- Note: Run these commands after the user/database exist
GRANT USAGE ON SCHEMA public TO call_platform_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO call_platform_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO call_platform_user;
-- Set default privileges for future tables/sequences created by migrations or superuser
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO call_platform_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO call_platform_user;


-- Add a verification message to indicate successful completion
SELECT 'CapConduit database schema v2.0 successfully created!' AS status;