# app/api/schemas/did_schemas.py
# -*- coding: utf-8 -*-
"""
Schemas for DID API requests and responses (Seller perspective).
"""
import re
from marshmallow import Schema, fields, validate, EXCLUDE

# Schema for creating a DID (Input)
class CreateDidSchema(Schema):
    number = fields.Str(
        required=True,
        validate=validate.Regexp(
            r'^\+[1-9]\d{1,14}$', # E.164-like format
            error="Invalid phone number format. Must start with '+' and contain digits (e.g., +15551234567)."
        )
    )
    description = fields.Str(allow_none=True)
    status = fields.Str(load_default='active', validate=validate.OneOf(['active', 'inactive']))

# Schema for updating a DID (Input - Partial)
class UpdateDidSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    description = fields.Str(allow_none=True) # Allow setting description to null/empty
    status = fields.Str(validate=validate.OneOf(['active', 'inactive']))

# Schema for DID output (Response)
class DidSchema(Schema):
    id = fields.Int(dump_only=True)
    number = fields.Str(required=True, dump_only=True) # Number is immutable after creation
    status = fields.Str(required=True, validate=validate.OneOf(['active', 'inactive']))
    description = fields.Str(allow_none=True)
    created_at = fields.DateTime(dump_only=True, data_key="createdAt")
    updated_at = fields.DateTime(dump_only=True, data_key="updatedAt")

# Schema for DID list pagination response
class DidListSchema(Schema):
    items = fields.List(fields.Nested(DidSchema()), required=True)
    page = fields.Int(required=True)
    perPage = fields.Int(required=True, attribute="per_page") # Map attribute
    total = fields.Int(required=True)
    pages = fields.Int(required=True)