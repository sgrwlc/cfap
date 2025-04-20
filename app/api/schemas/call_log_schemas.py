# -*- coding: utf-8 -*-
"""
Schemas for Call Logging API requests and responses.
"""
from marshmallow import Schema, fields, validate, EXCLUDE

# Schema for the request body sent by Asterisk to log a call
class LogCallRequestSchema(Schema):
    # Allow unknown fields to be ignored during loading
    class Meta:
        unknown = EXCLUDE

    # Required fields from Asterisk
    incoming_did_number = fields.Str(required=True, data_key="incomingDidNumber")
    timestamp_start = fields.DateTime(required=True, data_key="timestampStart") # Expect ISO 8601 format
    call_status = fields.Str(required=True, data_key="callStatus") # e.g., ANSWERED, NOANSWER, BUSY, FAILED, REJECTED_*
    asterisk_uniqueid = fields.Str(required=True, data_key="asteriskUniqueid")

    # Fields provided by the routing lookup or initial channel state
    user_id = fields.Int(required=False, allow_none=True, data_key="userId") # May not always be present if rejection happened early
    campaign_id = fields.Int(required=False, allow_none=True, data_key="campaignId")
    did_id = fields.Int(required=False, allow_none=True, data_key="didId") # ID of the DID record

    # Fields related to the specific client routing attempt
    client_id = fields.Int(required=False, allow_none=True, data_key="clientId") # Client actually attempted/connected
    campaign_client_setting_id = fields.Int(required=False, allow_none=True, data_key="campaignClientSettingId") # Setting used

    # Optional fields from Asterisk CDR / Channel Variables
    caller_id_num = fields.Str(required=False, allow_none=True, data_key="callerIdNum")
    caller_id_name = fields.Str(required=False, allow_none=True, data_key="callerIdName")
    timestamp_answered = fields.DateTime(required=False, allow_none=True, data_key="timestampAnswered")
    timestamp_end = fields.DateTime(required=False, allow_none=True, data_key="timestampEnd")
    duration_seconds = fields.Int(required=False, allow_none=True, data_key="durationSeconds")
    billsec_seconds = fields.Int(required=False, allow_none=True, data_key="billsecSeconds")
    hangup_cause_code = fields.Int(required=False, allow_none=True, data_key="hangupCauseCode")
    hangup_cause_text = fields.Str(required=False, allow_none=True, data_key="hangupCauseText")
    asterisk_linkedid = fields.Str(required=False, allow_none=True, data_key="asteriskLinkedid")


# Schema for the response body after logging a call
class LogCallResponseSchema(Schema):
    status = fields.Str(required=True, validate=validate.OneOf(['success', 'error']))
    message = fields.Str(required=True)
    cdr_id = fields.Int(required=False, data_key="cdrId") # Include only on success


# --- Schemas for Seller Viewing Call Logs ---

# Basic info about related entities shown in log list
class CallLogClientInfoSchema(Schema):
    id = fields.Int()
    name = fields.Str()
    client_identifier = fields.Str(data_key="clientIdentifier")

class CallLogCampaignInfoSchema(Schema):
    id = fields.Int()
    name = fields.Str()

class CallLogDidInfoSchema(Schema):
    id = fields.Int()
    number = fields.Str()

# Schema for displaying a single Call Log entry to a Seller
class CallLogSchema(Schema):
    id = fields.Int(dump_only=True) # Use Int, BigInt handled by DB driver usually
    # user_id = fields.Int(dump_only=True) # Owner knows who they are
    campaign = fields.Nested(CallLogCampaignInfoSchema(), allow_none=True)
    did = fields.Nested(CallLogDidInfoSchema(), allow_none=True)
    client = fields.Nested(CallLogClientInfoSchema(), allow_none=True) # Client attempted/connected
    # campaign_client_setting_id = fields.Int(allow_none=True, data_key="settingId") # Maybe not needed for seller view

    incoming_did_number = fields.Str(data_key="incomingDidNumber")
    caller_id_num = fields.Str(allow_none=True, data_key="callerIdNum")
    caller_id_name = fields.Str(allow_none=True, data_key="callerIdName")

    timestamp_start = fields.DateTime(data_key="timestampStart")
    timestamp_answered = fields.DateTime(allow_none=True, data_key="timestampAnswered")
    timestamp_end = fields.DateTime(allow_none=True, data_key="timestampEnd")

    duration_seconds = fields.Int(allow_none=True, data_key="durationSeconds")
    billsec_seconds = fields.Int(allow_none=True, data_key="billsecSeconds")

    call_status = fields.Str(data_key="callStatus")
    hangup_cause_code = fields.Int(allow_none=True, data_key="hangupCauseCode")
    hangup_cause_text = fields.Str(allow_none=True, data_key="hangupCauseText")

    asterisk_uniqueid = fields.Str(data_key="asteriskUniqueid")
    asterisk_linkedid = fields.Str(allow_none=True, data_key="asteriskLinkedid")

    created_at = fields.DateTime(dump_only=True, data_key="createdAt")

# Schema for Call Log list pagination response
class CallLogListSchema(Schema):
    items = fields.List(fields.Nested(CallLogSchema()), required=True)
    page = fields.Int(required=True)
    per_page = fields.Int(required=True, data_key="perPage")
    total = fields.Int(required=True)
    pages = fields.Int(required=True)