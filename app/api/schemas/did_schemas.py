# -*- coding: utf-8 -*-
"""
Schemas for DID API requests and responses (Seller perspective).
"""
from marshmallow import Schema, fields, validate, EXCLUDE

# Schema for DID output
class DidSchema(Schema):
    id = fields.Int(dump_only=True)
    number = fields.Str(required=True)
    # user_id = fields.Int(dump_only=True) # Usually not needed in response to the owner
    status = fields.Str(required=True, validate=validate.OneOf(['active', 'inactive']))
    description = fields.Str(allow_none=True)
    created_at = fields.DateTime(dump_only=True, data_key="createdAt")
    updated_at = fields.DateTime(dump_only=True, data_key="updatedAt")
    # Add campaign info if needed? Requires modification to service/query
    # campaigns = fields.List(fields.Nested("BasicCampaignSchema")) # Example

# Schema for creating a DID
class CreateDidSchema(Schema):
    number = fields.Str(required=True)
    description = fields.Str(allow_none=True)
    status = fields.Str(load_default='active', validate=validate.OneOf(['active', 'inactive']))

# Schema for updating a DID
class UpdateDidSchema(Schema):
    class Meta:
        unknown = EXCLUDE # Allow partial updates
    description = fields.Str(allow_none=True)
    status = fields.Str(validate=validate.OneOf(['active', 'inactive']))

# Schema for DID list pagination response
class DidListSchema(Schema):
    items = fields.List(fields.Nested(DidSchema()), required=True)
    page = fields.Int(required=True)
    per_page = fields.Int(required=True, data_key="perPage")
    total = fields.Int(required=True)
    pages = fields.Int(required=True)