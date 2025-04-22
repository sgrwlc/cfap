# app/api/schemas/campaign_schemas.py
# -*- coding: utf-8 -*-
"""
Schemas for Campaign API requests and responses (Seller perspective).
"""
from marshmallow import Schema, fields, validate, EXCLUDE
from .did_schemas import DidSchema # Re-use DID schema for listing associated DIDs
from .client_schemas import ClientSchema # Re-use Client schema

# --- Nested Schemas ---

# Minimal DID info for embedding in Campaign response
class _CampaignDidInfoSchema(Schema):
    id = fields.Int(dump_only=True)
    number = fields.Str(dump_only=True)
    description = fields.Str(allow_none=True, dump_only=True)
    status = fields.Str(dump_only=True) # Include status for info

# Minimal Client info for embedding CampaignClientSetting response
class _CampaignClientInfoSchema(Schema):
     id = fields.Int(dump_only=True)
     client_identifier = fields.Str(data_key="clientIdentifier", dump_only=True)
     name = fields.Str(dump_only=True)
     department = fields.Str(allow_none=True, dump_only=True)

# Schema for Campaign Client Settings output (nested within Campaign)
class CampaignClientSettingSchema(Schema):
    id = fields.Int(dump_only=True)
    # Use the minimal client schema, explicitly mark as dump_only
    client = fields.Nested(_CampaignClientInfoSchema, dump_only=True, required=True)
    client_id = fields.Int(required=True, load_only=True) # Required for input link creation/update

    status = fields.Str(required=True, validate=validate.OneOf(['active', 'inactive']))
    max_concurrency = fields.Int(required=True, validate=validate.Range(min=1), data_key="maxConcurrency")
    total_calls_allowed = fields.Int(allow_none=True, data_key="totalCallsAllowed", validate=validate.Range(min=0))
    current_total_calls = fields.Int(dump_only=True, data_key="currentTotalCalls") # Read-only for seller
    forwarding_priority = fields.Int(required=True, data_key="forwardingPriority", validate=validate.Range(min=0))
    weight = fields.Int(required=True, validate=validate.Range(min=1))

    created_at = fields.DateTime(dump_only=True, data_key="createdAt")
    updated_at = fields.DateTime(dump_only=True, data_key="updatedAt")

# --- Main Campaign Schemas ---

# Base Campaign Schema (for output)
class CampaignSchema(Schema):
    id = fields.Int(dump_only=True)
    name = fields.Str(required=True)
    status = fields.Str(required=True, validate=validate.OneOf(['active', 'inactive', 'paused']))
    routing_strategy = fields.Str(required=True, data_key="routingStrategy", validate=validate.OneOf(['priority', 'round_robin', 'weighted']))
    dial_timeout_seconds = fields.Int(required=True, data_key="dialTimeoutSeconds", validate=validate.Range(min=1))
    description = fields.Str(allow_none=True)
    created_at = fields.DateTime(dump_only=True, data_key="createdAt")
    updated_at = fields.DateTime(dump_only=True, data_key="updatedAt")

    # Nested data for detailed GET requests
    dids = fields.List(
        fields.Nested(_CampaignDidInfoSchema),
        dump_only=True,
        dump_default=[] # Ensure empty list output if none linked
    )
    client_settings = fields.List(
        fields.Nested(CampaignClientSettingSchema()),
        dump_only=True,
        data_key="clientSettings",
        dump_default=[] # Ensure empty list output if none linked
    )

# Schema for Creating a Campaign (Input)
class CreateCampaignSchema(Schema):
    name = fields.Str(required=True, validate=validate.Length(min=1))
    routing_strategy = fields.Str(required=True, data_key="routingStrategy", validate=validate.OneOf(['priority', 'round_robin', 'weighted']))
    dial_timeout_seconds = fields.Int(required=True, data_key="dialTimeoutSeconds", validate=validate.Range(min=1))
    status = fields.Str(load_default='active', validate=validate.OneOf(['active', 'inactive', 'paused']))
    description = fields.Str(allow_none=True)

# Schema for Updating a Campaign (Input - Partial)
class UpdateCampaignSchema(Schema):
    class Meta:
        unknown = EXCLUDE # Allow partial updates

    name = fields.Str(validate=validate.Length(min=1))
    routing_strategy = fields.Str(data_key="routingStrategy", validate=validate.OneOf(['priority', 'round_robin', 'weighted']))
    dial_timeout_seconds = fields.Int(data_key="dialTimeoutSeconds", validate=validate.Range(min=1))
    status = fields.Str(validate=validate.OneOf(['active', 'inactive', 'paused']))
    description = fields.Str(allow_none=True)

# Schema for setting DIDs associated with a campaign (Input)
class SetCampaignDidsSchema(Schema):
    did_ids = fields.List(fields.Int(), required=True, data_key="didIds")

# Schema for adding/updating a client link to a campaign (Input)
class CampaignClientSettingInputSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    # These fields are required for POST, optional for PUT
    client_id = fields.Int(required=True, data_key="clientId")
    status = fields.Str(load_default='active', validate=validate.OneOf(['active', 'inactive'])) # Default for POST
    max_concurrency = fields.Int(required=True, data_key="maxConcurrency", validate=validate.Range(min=1)) # Required for POST
    forwarding_priority = fields.Int(required=True, data_key="forwardingPriority", validate=validate.Range(min=0)) # Required for POST
    weight = fields.Int(required=True, validate=validate.Range(min=1)) # Required for POST
    total_calls_allowed = fields.Int(allow_none=True, data_key="totalCallsAllowed", validate=validate.Range(min=0))


# Schema for campaign list pagination response
class CampaignListSchema(Schema):
    items = fields.List(fields.Nested(CampaignSchema(exclude=("client_settings", "dids"))), required=True)
    page = fields.Int(required=True)
    perPage = fields.Int(required=True, attribute="per_page")
    total = fields.Int(required=True)
    pages = fields.Int(required=True)