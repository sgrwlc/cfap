# -*- coding: utf-8 -*-
"""
Schemas for Campaign API requests and responses (Seller perspective).
"""
from marshmallow import Schema, fields, validate, EXCLUDE
from .did_schemas import DidSchema # Re-use DID schema for listing associated DIDs
from .client_schemas import ClientSchema # Re-use Client schema

# Schema for Campaign Client Settings output (nested within Campaign)
class CampaignClientSettingSchema(Schema):
    id = fields.Int(dump_only=True)
    # campaign_id = fields.Int(dump_only=True) # Often redundant when nested
    # Exclude client PJSIP details unless specifically needed by seller view
    client = fields.Nested(lambda: ClientSchema(exclude=("pjsip_endpoint", "pjsip_aor", "pjsip_auth")), dump_only=True)
    client_id = fields.Int(required=True, load_only=True) # Required for creation/update input
    status = fields.Str(required=True, validate=validate.OneOf(['active', 'inactive']))
    max_concurrency = fields.Int(required=True, validate=validate.Range(min=1), data_key="maxConcurrency")
    total_calls_allowed = fields.Int(allow_none=True, data_key="totalCallsAllowed", validate=validate.Range(min=0))
    current_total_calls = fields.Int(dump_only=True, data_key="currentTotalCalls") # Read-only for seller
    forwarding_priority = fields.Int(required=True, data_key="forwardingPriority", validate=validate.Range(min=0))
    weight = fields.Int(required=True, validate=validate.Range(min=1))
    created_at = fields.DateTime(dump_only=True, data_key="createdAt")
    updated_at = fields.DateTime(dump_only=True, data_key="updatedAt")


# Base Campaign Schema (for output)
class CampaignSchema(Schema):
    id = fields.Int(dump_only=True)
    # user_id = fields.Int(dump_only=True) # Usually not needed in response to the owner
    name = fields.Str(required=True)
    status = fields.Str(required=True, validate=validate.OneOf(['active', 'inactive', 'paused']))
    routing_strategy = fields.Str(required=True, validate=validate.OneOf(['priority', 'round_robin', 'weighted']), data_key="routingStrategy")
    dial_timeout_seconds = fields.Int(required=True, data_key="dialTimeoutSeconds", validate=validate.Range(min=1))
    description = fields.Str(allow_none=True)
    created_at = fields.DateTime(dump_only=True, data_key="createdAt")
    updated_at = fields.DateTime(dump_only=True, data_key="updatedAt")

    # Nested data for GET requests
    # DIDs associated with this campaign
    dids = fields.List(fields.Nested(lambda: DidSchema(only=("id", "number", "description", "status"))), dump_only=True)
    # Client settings/links for this campaign
    client_settings = fields.List(fields.Nested(CampaignClientSettingSchema()), dump_only=True, data_key="clientSettings")


# Schema for Creating a Campaign
class CreateCampaignSchema(Schema):
    name = fields.Str(required=True)
    routing_strategy = fields.Str(required=True, validate=validate.OneOf(['priority', 'round_robin', 'weighted']), data_key="routingStrategy")
    dial_timeout_seconds = fields.Int(required=True, data_key="dialTimeoutSeconds", validate=validate.Range(min=1))
    status = fields.Str(load_default='active', validate=validate.OneOf(['active', 'inactive', 'paused']))
    description = fields.Str(allow_none=True)

# Schema for Updating a Campaign
class UpdateCampaignSchema(Schema):
    class Meta:
        unknown = EXCLUDE # Allow partial updates
    name = fields.Str()
    routing_strategy = fields.Str(validate=validate.OneOf(['priority', 'round_robin', 'weighted']), data_key="routingStrategy")
    dial_timeout_seconds = fields.Int(data_key="dialTimeoutSeconds", validate=validate.Range(min=1))
    status = fields.Str(validate=validate.OneOf(['active', 'inactive', 'paused']))
    description = fields.Str(allow_none=True)

# Schema for setting DIDs associated with a campaign
class SetCampaignDidsSchema(Schema):
    did_ids = fields.List(fields.Int(), required=True, data_key="didIds")

# Schema for adding/updating a client link to a campaign
# cfap/app/api/schemas/campaign_schemas.py
class CampaignClientSettingInputSchema(Schema):
    # Allow partial updates for PUT, required fields for POST validated in route
    class Meta:
        unknown = EXCLUDE
    # These fields are implicitly required by Marshmallow unless specified otherwise
    client_id = fields.Int(required=True, data_key="clientId") # Required!
    status = fields.Str(load_default='active', validate=validate.OneOf(['active', 'inactive']))
    max_concurrency = fields.Int(required=True, validate=validate.Range(min=1), data_key="maxConcurrency") # Required!
    total_calls_allowed = fields.Int(allow_none=True, data_key="totalCallsAllowed", validate=validate.Range(min=0))
    forwarding_priority = fields.Int(required=True, data_key="forwardingPriority", validate=validate.Range(min=0)) # Required!
    weight = fields.Int(required=True, validate=validate.Range(min=1)) # Required!

# Schema for campaign list pagination response
class CampaignListSchema(Schema):
    items = fields.List(fields.Nested(CampaignSchema(exclude=("client_settings", "dids"))), required=True)
    page = fields.Int(required=True)
    # Rename field, map attribute
    perPage = fields.Int(required=True, attribute="per_page") # <-- APPLY FIX HERE
    total = fields.Int(required=True)
    pages = fields.Int(required=True)