# app/api/schemas/call_log_schemas.py
# -*- coding: utf-8 -*-
"""
Schemas for Call Logging API requests and responses.
"""
from marshmallow import Schema, fields, validate, EXCLUDE

# --- Internal Logging Schemas ---

# Schema for the request body sent by Asterisk to log a call (/api/internal/log_call)
class LogCallRequestSchema(Schema):
    # Allow unknown fields from Asterisk AGI/CDR to be ignored during loading
    class Meta:
        unknown = EXCLUDE
        # datetimeformat = '%Y-%m-%dT%H:%M:%S.%f%z' # Optional: Explicit datetime format

    # Required fields expected from Asterisk AGI script context
    incoming_did_number = fields.Str(required=True, data_key="incomingDidNumber")
    timestamp_start = fields.DateTime(required=True, data_key="timestampStart") # Expect ISO 8601 format UTC
    call_status = fields.Str(required=True, data_key="callStatus", validate=validate.Length(max=50))
    asterisk_uniqueid = fields.Str(required=True, data_key="asteriskUniqueid", validate=validate.Length(max=50))

    # Fields provided by the routing lookup or initial channel state (potentially nullable)
    user_id = fields.Int(required=False, allow_none=True, data_key="userId")
    campaign_id = fields.Int(required=False, allow_none=True, data_key="campaignId")
    did_id = fields.Int(required=False, allow_none=True, data_key="didId")

    # Fields related to the specific client routing attempt (potentially nullable)
    client_id = fields.Int(required=False, allow_none=True, data_key="clientId")
    campaign_client_setting_id = fields.Int(required=False, allow_none=True, data_key="campaignClientSettingId")

    # Optional fields from Asterisk CDR / Channel Variables
    caller_id_num = fields.Str(required=False, allow_none=True, data_key="callerIdNum", validate=validate.Length(max=50))
    caller_id_name = fields.Str(required=False, allow_none=True, data_key="callerIdName", validate=validate.Length(max=100))
    timestamp_answered = fields.DateTime(required=False, allow_none=True, data_key="timestampAnswered") # Expect ISO 8601 format UTC
    timestamp_end = fields.DateTime(required=False, allow_none=True, data_key="timestampEnd") # Expect ISO 8601 format UTC
    duration_seconds = fields.Int(required=False, allow_none=True, data_key="durationSeconds", validate=validate.Range(min=0))
    billsec_seconds = fields.Int(required=False, allow_none=True, data_key="billsecSeconds", validate=validate.Range(min=0))
    hangup_cause_code = fields.Int(required=False, allow_none=True, data_key="hangupCauseCode")
    hangup_cause_text = fields.Str(required=False, allow_none=True, data_key="hangupCauseText", validate=validate.Length(max=50))
    asterisk_linkedid = fields.Str(required=False, allow_none=True, data_key="asteriskLinkedid", validate=validate.Length(max=50))


# Schema for the response body after logging a call (/api/internal/log_call)
class LogCallResponseSchema(Schema):
    status = fields.Str(required=True, validate=validate.OneOf(['success', 'error']))
    message = fields.Str(required=True)
    cdr_id = fields.Int(required=False, allow_none=True, data_key="cdrId") # Include only on success


# --- Schemas for Seller Viewing Call Logs (/api/seller/logs) ---

# Basic info about related entities shown in log list (Internal helper schemas)
class _CallLogClientInfoSchema(Schema):
    id = fields.Int(dump_only=True)
    name = fields.Str(dump_only=True)
    client_identifier = fields.Str(data_key="clientIdentifier", dump_only=True)

class _CallLogCampaignInfoSchema(Schema):
    id = fields.Int(dump_only=True)
    name = fields.Str(dump_only=True)

class _CallLogDidInfoSchema(Schema):
    id = fields.Int(dump_only=True)
    number = fields.Str(dump_only=True)

# Schema for displaying a single Call Log entry to a Seller (API Response)
class CallLogSchema(Schema):
    id = fields.Int(dump_only=True)

    # Use the internal schemas for nested objects
    campaign = fields.Nested(_CallLogCampaignInfoSchema, allow_none=True, dump_only=True)
    did = fields.Nested(_CallLogDidInfoSchema, allow_none=True, dump_only=True)
    client = fields.Nested(_CallLogClientInfoSchema, allow_none=True, dump_only=True)

    # Key Call Details
    incoming_did_number = fields.Str(data_key="incomingDidNumber", dump_only=True)
    caller_id_num = fields.Str(allow_none=True, data_key="callerIdNum", dump_only=True)
    caller_id_name = fields.Str(allow_none=True, data_key="callerIdName", dump_only=True)

    # Timestamps
    timestamp_start = fields.DateTime(data_key="timestampStart", dump_only=True) # Output in ISO 8601 UTC
    timestamp_answered = fields.DateTime(allow_none=True, data_key="timestampAnswered", dump_only=True)
    timestamp_end = fields.DateTime(allow_none=True, data_key="timestampEnd", dump_only=True)

    # Durations
    duration_seconds = fields.Int(allow_none=True, data_key="durationSeconds", dump_only=True)
    billsec_seconds = fields.Int(allow_none=True, data_key="billsecSeconds", dump_only=True)

    # Status & Hangup
    call_status = fields.Str(data_key="callStatus", dump_only=True)
    hangup_cause_code = fields.Int(allow_none=True, data_key="hangupCauseCode", dump_only=True)
    hangup_cause_text = fields.Str(allow_none=True, data_key="hangupCauseText", dump_only=True)

    # Asterisk IDs
    asterisk_uniqueid = fields.Str(data_key="asteriskUniqueid", dump_only=True)
    asterisk_linkedid = fields.Str(allow_none=True, data_key="asteriskLinkedid", dump_only=True)

    # Record Timestamps
    created_at = fields.DateTime(dump_only=True, data_key="createdAt")


# Schema for Call Log list pagination response (/api/seller/logs)
class CallLogListSchema(Schema):
    items = fields.List(fields.Nested(CallLogSchema()), required=True)
    page = fields.Int(required=True)
    perPage = fields.Int(required=True, attribute="per_page") # Map attribute 'per_page' to field 'perPage'
    total = fields.Int(required=True)
    pages = fields.Int(required=True)