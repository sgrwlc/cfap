# -*- coding: utf-8 -*-
"""
Schemas for Internal Call Routing API requests and responses.
"""
from marshmallow import Schema, fields, validate

# Schema for individual target information returned by the routing service
class RoutingTargetSchema(Schema):
    ccs_id = fields.Int(required=True, data_key="campaignClientSettingId", dump_only=True) # CampaignClientSetting ID
    client_id = fields.Int(required=True, dump_only=True)
    client_identifier = fields.Str(required=True, dump_only=True) # PJSIP Endpoint ID / GROUP name
    client_name = fields.Str(dump_only=True) # Informational
    sip_uri = fields.Str(required=True, dump_only=True) # Asterisk Destination URI(s)
    max_concurrency = fields.Int(required=True, dump_only=True) # Concurrency for this link
    weight = fields.Int(required=True, dump_only=True) # Weight for weighted routing
    priority = fields.Int(required=True, dump_only=True) # Priority level
    outbound_auth = fields.Str(allow_none=True, dump_only=True) # Optional PJSIP auth section ID
    callerid_override = fields.Str(allow_none=True, dump_only=True) # Optional CallerID override
    context = fields.Str(allow_none=True, dump_only=True) # Optional PJSIP context
    transport = fields.Str(allow_none=True, dump_only=True) # Optional PJSIP transport


# Schema for the main routing information structure
class RoutingInfoSchema(Schema):
    user_id = fields.Int(required=True, dump_only=True)
    campaign_id = fields.Int(required=True, dump_only=True)
    routing_strategy = fields.Str(required=True, dump_only=True, validate=validate.OneOf(['priority', 'round_robin', 'weighted']))
    dial_timeout_seconds = fields.Int(required=True, dump_only=True)
    targets = fields.List(fields.Nested(RoutingTargetSchema()), required=True, dump_only=True) # List of potential targets


# Schema for the overall response of the /route_info endpoint
class RouteInfoResponseSchema(Schema):
    status = fields.Str(required=True, validate=validate.OneOf(['proceed', 'reject']))
    # Only include routing_info if status is 'proceed'
    routing_info = fields.Nested(RoutingInfoSchema(), required=False, data_key="routingInfo")
    # Only include reject_reason if status is 'reject'
    reject_reason = fields.Str(required=False, data_key="rejectReason")