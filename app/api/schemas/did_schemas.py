# -*- coding: utf-8 -*-
"""
Schemas for DID API requests and responses (Seller perspective).
"""
from marshmallow import Schema, fields, validate, EXCLUDE

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

class DidSchema(Schema):
    id = fields.Int(dump_only=True)
    number = fields.Str(required=True)
    status = fields.Str(required=True, validate=validate.OneOf(['active', 'inactive']))
    description = fields.Str(allow_none=True)
    created_at = fields.DateTime(dump_only=True, data_key="createdAt")
    updated_at = fields.DateTime(dump_only=True, data_key="updatedAt")

class DidListSchema(Schema):
    items = fields.List(fields.Nested(DidSchema()), required=True)
    page = fields.Int(required=True)
    perPage = fields.Int(required=True, attribute="per_page")
    total = fields.Int(required=True)
    pages = fields.Int(required=True)