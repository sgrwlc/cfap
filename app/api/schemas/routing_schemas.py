# app/api/schemas/routing_schemas.py
# -*- coding: utf-8 -*-
"""
Schemas for Internal Call Routing API responses.
Defines the structure returned by the /route_info endpoint.
"""
from marshmallow import Schema, fields, validate

# Schema for individual target information returned by the routing service
class RoutingTargetSchema(Schema):
    # Mark individual fields as dump_only as this schema represents API output
    ccs_id = fields.Int(required=True, data_key="campaignClientSettingId", dump_only=True)
    client_id = fields.Int(required=True, dump_only=True)
    client_identifier = fields.Str(required=True, dump_only=True)
    client_name = fields.Str(dump_only=True)
    sip_uri = fields.Str(required=True, dump_only=True)
    max_concurrency = fields.Int(required=True, dump_only=True)
    weight = fields.Int(required=True, dump_only=True)
    priority = fields.Int(required=True, dump_only=True)
    outbound_auth = fields.Str(allow_none=True, dump_only=True)
    callerid_override = fields.Str(allow_none=True, dump_only=True)
    context = fields.Str(allow_none=True, dump_only=True)
    transport = fields.Str(allow_none=True, dump_only=True)


# Schema for the main routing information structure (nested in the response)
class RoutingInfoSchema(Schema):
    # Mark individual fields as dump_only
    user_id = fields.Int(required=True, dump_only=True)
    campaign_id = fields.Int(required=True, dump_only=True)
    did_id = fields.Int(required=True, dump_only=True)
    routing_strategy = fields.Str(required=True, dump_only=True, validate=validate.OneOf(['priority', 'round_robin', 'weighted']))
    dial_timeout_seconds = fields.Int(required=True, dump_only=True)
    targets = fields.List(fields.Nested(RoutingTargetSchema()), required=True, dump_only=True) # List is dump_only


# Schema for the overall response of the /route_info endpoint
class RouteInfoResponseSchema(Schema):
    # Mark individual fields as dump_only
    status = fields.Str(required=True, dump_only=True, validate=validate.OneOf(['proceed', 'reject']))
    routing_info = fields.Nested(RoutingInfoSchema(), required=False, allow_none=True, data_key="routingInfo", dump_only=True)
    reject_reason = fields.Str(required=False, allow_none=True, data_key="rejectReason", dump_only=True)