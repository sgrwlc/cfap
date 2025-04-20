-- CapConduit Redesigned Database Schema (v3.0 - ARA Focused)
-- PostgreSQL database setup script
-- Assumes Asterisk Realtime Architecture (ARA) for PJSIP configuration

-- Ensure UTC timezone is used for all timestamp operations internally
SET TIME ZONE 'UTC';

-- Drop existing tables in reverse order of dependency to handle Foreign Keys
-- Using CASCADE simplifies dropping tables with dependencies.
DROP TABLE IF EXISTS call_logs CASCADE;
DROP TABLE IF EXISTS campaign_client_settings CASCADE;
DROP TABLE IF EXISTS campaign_dids CASCADE;
DROP TABLE IF EXISTS campaigns CASCADE;
DROP TABLE IF EXISTS dids CASCADE;
DROP TABLE IF EXISTS pjsip_auths CASCADE;       -- ARA PJSIP Auth table
DROP TABLE IF EXISTS pjsip_aors CASCADE;        -- ARA PJSIP AOR table
DROP TABLE IF EXISTS pjsip_endpoints CASCADE;   -- ARA PJSIP Endpoint table
DROP TABLE IF EXISTS clients CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- Drop the trigger function if it exists
DROP FUNCTION IF EXISTS update_updated_at_column();

-- Trigger function to automatically update 'updated_at' column on modifications
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
   -- Set updated_at to the current UTC time
   NEW.updated_at = timezone('utc', now());
   RETURN NEW;
END;
$$ language 'plpgsql';


-- Users Table: Stores platform administrators, staff, and call sellers
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(80) UNIQUE NOT NULL,
    email VARCHAR(120) UNIQUE NOT NULL,
    password_hash VARCHAR(128) NOT NULL, -- Store only Bcrypt hashed passwords
    role VARCHAR(10) NOT NULL CHECK (role IN ('admin', 'staff', 'user')), -- 'user' represents Call Seller
    status VARCHAR(15) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'pending_approval', 'suspended')),
    full_name VARCHAR(100),
    company_name VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT timezone('utc', now()),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT timezone('utc', now())
);
-- Indexes for users
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_users_status ON users(status);
-- Trigger for users updated_at
CREATE TRIGGER trigger_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
COMMENT ON TABLE users IS 'Stores platform administrators, staff, and call sellers (role=user).';
COMMENT ON COLUMN users.role IS 'admin: full access, staff: operational oversight, user: call seller.';


-- Clients Table: Logical representation of Call Centers receiving calls
CREATE TABLE clients (
    id SERIAL PRIMARY KEY,
    client_identifier VARCHAR(50) UNIQUE NOT NULL, -- A unique handle for the client (e.g., 'client_alpha_sales') used for linking and potentially PJSIP ID
    name VARCHAR(100) NOT NULL,
    department VARCHAR(100), -- e.g., 'Sales', 'Support', 'Intake'
    status VARCHAR(10) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    notes TEXT, -- Internal notes about the client
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL, -- Which admin/staff added this client
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT timezone('utc', now()),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT timezone('utc', now())
);
-- Indexes for clients
CREATE INDEX idx_clients_name ON clients(name);
CREATE INDEX idx_clients_status ON clients(status);
-- Trigger for clients updated_at
CREATE TRIGGER trigger_clients_updated_at BEFORE UPDATE ON clients FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
COMMENT ON TABLE clients IS 'Logical representation of Call Centers (companies/departments receiving calls). Linked to technical SIP details via pjsip_* tables.';
COMMENT ON COLUMN clients.client_identifier IS 'Unique text identifier used across system and potentially as PJSIP endpoint ID.';


-- PJSIP Endpoints Table (ARA Compatible)
-- Stores PJSIP endpoint configuration. Column names should match Asterisk ARA requirements.
CREATE TABLE pjsip_endpoints (
    id VARCHAR(40) PRIMARY KEY, -- Matches clients.client_identifier - the unique name Asterisk uses
    client_id INTEGER UNIQUE REFERENCES clients(id) ON DELETE CASCADE, -- Link back to the logical client
    transport VARCHAR(40), -- Name of PJSIP transport to use (e.g., 'transport-udp')
    aors VARCHAR(200), -- Comma-separated list of AOR IDs (typically just 'id')
    auth VARCHAR(40), -- Auth ID if authentication is needed TO the client
    context VARCHAR(80) NOT NULL, -- Dialplan context for incoming calls FROM this endpoint (if applicable, likely outbound-only)
    disallow VARCHAR(200) DEFAULT 'all',
    allow VARCHAR(200) DEFAULT 'ulaw,alaw,gsm', -- Codecs to allow for calls TO this client
    direct_media VARCHAR(10) DEFAULT 'no',
    -- Outbound specific settings (sending calls TO the client)
    outbound_auth VARCHAR(40), -- Auth ID to use when WE authenticate to THEM
    from_user VARCHAR(80), -- Optional: Username part of From header
    from_domain VARCHAR(80), -- Optional: Domain part of From header
    callerid VARCHAR(80), -- Default Caller ID Name <number>
    -- Add other necessary PJSIP endpoint options here based on Asterisk version and needs
    -- Avoid storing sensitive info like passwords directly if possible (use auth table)
    -- Timestamps might not be needed if Asterisk just reads, but useful for tracking changes
    config_updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now())
);
COMMENT ON TABLE pjsip_endpoints IS 'ARA table for PJSIP endpoint configuration. `id` must match clients.client_identifier and Asterisk config.';
COMMENT ON COLUMN pjsip_endpoints.id IS 'PJSIP Endpoint ID, must match clients.client_identifier.';
COMMENT ON COLUMN pjsip_endpoints.aors IS 'Comma-delimited list of AOR IDs associated with this endpoint (usually same as endpoint id).';
COMMENT ON COLUMN pjsip_endpoints.outbound_auth IS 'Auth section ID to use for authenticating *to* this client endpoint, if required.';


-- PJSIP AORs Table (ARA Compatible)
-- Address of Record - Defines where to send calls for an endpoint.
CREATE TABLE pjsip_aors (
    id VARCHAR(40) PRIMARY KEY, -- Matches endpoint ID
    client_id INTEGER UNIQUE REFERENCES clients(id) ON DELETE CASCADE, -- Link back to the logical client
    contact VARCHAR(255) NOT NULL, -- Crucial: The SIP URI(s) of the client (e.g., 'sip:1.2.3.4:5060', 'sip:user@domain.com'). Comma-separate for multiple contacts if needed.
    max_contacts INTEGER DEFAULT 1, -- Typically 1 for sending calls to a static PBX
    qualify_frequency INTEGER DEFAULT 60, -- How often to send OPTIONS requests (0 to disable)
    -- Add other necessary PJSIP AOR options here
    config_updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now())
);
COMMENT ON TABLE pjsip_aors IS 'ARA table for PJSIP Address of Record (AOR) configuration. Defines client contact URI(s).';
COMMENT ON COLUMN pjsip_aors.id IS 'PJSIP AOR ID, must match the endpoint ID.';
COMMENT ON COLUMN pjsip_aors.contact IS 'SIP URI(s) where Asterisk should send calls for this client.';


-- PJSIP Auths Table (ARA Compatible)
-- Authentication details. Used for authenticating TO the client (outbound) or FROM the client (inbound).
CREATE TABLE pjsip_auths (
    id VARCHAR(40) PRIMARY KEY, -- Matches endpoint ID / auth name referenced in pjsip_endpoints.auth or outbound_auth
    client_id INTEGER UNIQUE REFERENCES clients(id) ON DELETE CASCADE, -- Link back to the logical client
    auth_type VARCHAR(20) DEFAULT 'userpass', -- e.g., 'userpass', 'md5'
    username VARCHAR(80), -- Username required BY the client or provided TO the client
    password VARCHAR(128), -- Password required BY the client or provided TO the client
    realm VARCHAR(80), -- SIP realm, often needed for authentication
    -- Add other necessary PJSIP auth options here
    config_updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now())
);
COMMENT ON TABLE pjsip_auths IS 'ARA table for PJSIP Authentication configuration. Used if *we* need to authenticate *to* the client or vice-versa.';
COMMENT ON COLUMN pjsip_auths.id IS 'PJSIP Auth section ID, referenced by endpoints.';


-- DIDs Table: Phone numbers owned by Call Sellers
CREATE TABLE dids (
    id SERIAL PRIMARY KEY,
    number VARCHAR(50) UNIQUE NOT NULL, -- E.164 format recommended (+1xxxxxxxxxx)
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, -- The Call Seller who owns this DID
    status VARCHAR(10) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    description VARCHAR(255), -- User-friendly description
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT timezone('utc', now()),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT timezone('utc', now())
);
-- Indexes for dids
CREATE INDEX idx_dids_number ON dids(number);
CREATE INDEX idx_dids_user_id ON dids(user_id);
-- Trigger for dids updated_at
CREATE TRIGGER trigger_dids_updated_at BEFORE UPDATE ON dids FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
COMMENT ON TABLE dids IS 'Phone numbers (DIDs) owned by Call Sellers (users).';


-- Campaigns Table: Call Seller campaigns defining routing logic
CREATE TABLE campaigns (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, -- Campaign owner (Call Seller)
    name VARCHAR(100) NOT NULL,
    status VARCHAR(10) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'paused')),
    routing_strategy VARCHAR(20) NOT NULL DEFAULT 'priority' CHECK (routing_strategy IN ('priority', 'round_robin', 'weighted')),
    dial_timeout_seconds INTEGER NOT NULL DEFAULT 30 CHECK (dial_timeout_seconds > 0), -- Time to wait for answer before trying next client
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT timezone('utc', now()),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT timezone('utc', now()),
    UNIQUE (user_id, name) -- Campaign name must be unique per user
);
-- Indexes for campaigns
CREATE INDEX idx_campaigns_user_id ON campaigns(user_id);
CREATE INDEX idx_campaigns_status ON campaigns(status);
-- Trigger for campaigns updated_at
CREATE TRIGGER trigger_campaigns_updated_at BEFORE UPDATE ON campaigns FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
COMMENT ON TABLE campaigns IS 'Call Seller campaigns linking DIDs to Clients with specific rules and caps.';
COMMENT ON COLUMN campaigns.routing_strategy IS 'How to select the next client if multiple are configured.';
COMMENT ON COLUMN campaigns.dial_timeout_seconds IS 'Max time (seconds) to attempt dialing a client before trying the next one based on strategy.';


-- Campaign DIDs Table: Junction table linking DIDs to Campaigns (Many-to-Many)
CREATE TABLE campaign_dids (
    campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    did_id INTEGER NOT NULL REFERENCES dids(id) ON DELETE CASCADE,
    PRIMARY KEY (campaign_id, did_id) -- Ensures unique pairings
);
-- Indexes for campaign_dids (Primary Key usually creates these)
CREATE INDEX idx_campaign_dids_did_id ON campaign_dids(did_id); -- Useful for finding campaigns for a DID
COMMENT ON TABLE campaign_dids IS 'Links DIDs to the Campaigns they feed calls into.';


-- Campaign Client Settings Table: Defines rules/caps for specific Campaign-Client pairings
CREATE TABLE campaign_client_settings (
    id SERIAL PRIMARY KEY, -- Useful for direct referencing/updates
    campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    status VARCHAR(10) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')), -- Status of this specific link
    max_concurrency INTEGER NOT NULL CHECK (max_concurrency >= 1), -- Max simultaneous calls FOR THIS CLIENT FROM THIS CAMPAIGN
    total_calls_allowed INTEGER, -- Total calls allowed FOR THIS CLIENT FROM THIS CAMPAIGN (NULL = unlimited)
    current_total_calls INTEGER NOT NULL DEFAULT 0, -- Counter towards total_calls_allowed
    forwarding_priority INTEGER NOT NULL DEFAULT 0, -- Lower number = higher priority (for 'priority' strategy)
    weight INTEGER NOT NULL DEFAULT 100 CHECK (weight > 0), -- Weight for 'weighted' strategy
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT timezone('utc', now()),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT timezone('utc', now()),
    UNIQUE (campaign_id, client_id) -- A campaign can only link to a specific client once
);
-- Indexes for campaign_client_settings
CREATE INDEX idx_ccs_campaign_id_status ON campaign_client_settings(campaign_id, status); -- Find active clients for a campaign
CREATE INDEX idx_ccs_client_id ON campaign_client_settings(client_id);
CREATE INDEX idx_ccs_priority ON campaign_client_settings(forwarding_priority);
-- Trigger for campaign_client_settings updated_at
CREATE TRIGGER trigger_ccs_updated_at BEFORE UPDATE ON campaign_client_settings FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
COMMENT ON TABLE campaign_client_settings IS 'CRITICAL TABLE: Defines settings (caps, priority, weight) for each specific Campaign-to-Client link.';
COMMENT ON COLUMN campaign_client_settings.max_concurrency IS 'Concurrency cap specific to this campaign-client link.';
COMMENT ON COLUMN campaign_client_settings.total_calls_allowed IS 'Total calls cap specific to this campaign-client link (NULL=unlimited).';
COMMENT ON COLUMN campaign_client_settings.current_total_calls IS 'Counter tracking calls towards total_calls_allowed.';
COMMENT ON COLUMN campaign_client_settings.forwarding_priority IS 'Order for Priority routing (lower number = higher priority).';
COMMENT ON COLUMN campaign_client_settings.weight IS 'Weight for Weighted Round Robin routing.';


-- Call Logs Table: Records details of every call attempt processed by the system
CREATE TABLE call_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL, -- The Call Seller associated with the call
    campaign_id INTEGER REFERENCES campaigns(id) ON DELETE SET NULL, -- The campaign that sourced the call
    did_id INTEGER REFERENCES dids(id) ON DELETE SET NULL, -- The DID that received the call
    client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL, -- The specific Client the call was SENT TO (if attempt was made)
    campaign_client_setting_id INTEGER REFERENCES campaign_client_settings(id) ON DELETE SET NULL, -- Link to the specific rule set applied

    incoming_did_number VARCHAR(50) NOT NULL, -- Store the number called for historical record
    caller_id_num VARCHAR(50), -- Caller's phone number
    caller_id_name VARCHAR(100), -- Caller's name (if available)

    timestamp_start TIMESTAMP WITH TIME ZONE NOT NULL, -- When Asterisk received the call
    timestamp_answered TIMESTAMP WITH TIME ZONE, -- When the call was answered by the Client (or Asterisk media)
    timestamp_end TIMESTAMP WITH TIME ZONE, -- When the call ended

    duration_seconds INTEGER, -- Total time from start to end (may include ringing)
    billsec_seconds INTEGER, -- Time the call was actually answered (bridged)

    -- Detailed status reflecting the final outcome / rejection reason
    call_status VARCHAR(50) NOT NULL, -- e.g., ANSWERED, NOANSWER, BUSY, FAILED, REJECTED_CC, REJECTED_TOTAL, REJECTED_NO_CLIENTS, TIMEOUT_FALLBACK
    hangup_cause_code INTEGER, -- Asterisk hangup cause code (e.g., 16, 17, 19)
    hangup_cause_text VARCHAR(50), -- Corresponding text (e.g., 'Normal Clearing', 'User busy')

    asterisk_uniqueid VARCHAR(50) UNIQUE, -- Asterisk's channel unique ID
    asterisk_linkedid VARCHAR(50), -- Asterisk's call group ID

    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT timezone('utc', now()) -- Log entry time
);
-- Indexes for call_logs
CREATE INDEX idx_call_logs_user_id ON call_logs(user_id);
CREATE INDEX idx_call_logs_campaign_id ON call_logs(campaign_id);
CREATE INDEX idx_call_logs_client_id ON call_logs(client_id);
CREATE INDEX idx_call_logs_did_id ON call_logs(did_id);
CREATE INDEX idx_call_logs_incoming_did_number ON call_logs(incoming_did_number);
CREATE INDEX idx_call_logs_timestamp_start ON call_logs(timestamp_start);
CREATE INDEX idx_call_logs_call_status ON call_logs(call_status);
CREATE INDEX idx_call_logs_asterisk_uniqueid ON call_logs(asterisk_uniqueid);
COMMENT ON TABLE call_logs IS 'Detailed records of call attempts, including routing decisions and outcomes.';
COMMENT ON COLUMN call_logs.call_status IS 'Final outcome (e.g., ANSWERED, NOANSWER, BUSY, FAILED, REJECTED_CC, REJECTED_TOTAL, TIMEOUT_FALLBACK).';
COMMENT ON COLUMN call_logs.client_id IS 'The Client the call was ultimately routed/attempted to.';


-- Grant permissions to the application user (replace 'call_platform_user' if different)
-- Ensure this user exists in PostgreSQL first.
GRANT USAGE ON SCHEMA public TO call_platform_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO call_platform_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO call_platform_user;

-- Set default privileges for future tables/sequences (useful for migrations)
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO call_platform_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO call_platform_user;


-- Final verification message
SELECT 'CapConduit Redesigned Schema v3.0 (ARA Focused) created successfully!' AS status;