# -*- coding: utf-8 -*-
"""
Schemas for User API requests and responses.
"""
from marshmallow import Schema, fields, validate, EXCLUDE

# Base User Schema (for output, excluding sensitive info)
class UserSchema(Schema):
    id = fields.Int(dump_only=True)
    username = fields.Str(required=True)
    email = fields.Email(required=True)
    role = fields.Str(required=True, validate=validate.OneOf(['admin', 'staff', 'user']))
    status = fields.Str(required=True, validate=validate.OneOf(['active', 'inactive', 'pending_approval', 'suspended']))
    full_name = fields.Str(allow_none=True, data_key="fullName")
    company_name = fields.Str(allow_none=True, data_key="companyName")
    created_at = fields.DateTime(dump_only=True, data_key="createdAt")
    updated_at = fields.DateTime(dump_only=True, data_key="updatedAt")

# Schema for creating a new user (Admin) - requires password
class CreateUserSchema(UserSchema):
    # Password is required for creation, but never dumped
    password = fields.Str(required=True, load_only=True, validate=validate.Length(min=8))

    class Meta:
        # Exclude fields inherited from UserSchema that shouldn't be set on creation directly
        exclude = ('id', 'created_at', 'updated_at')

# Schema for updating a user (Admin) - password not included here
class UpdateUserSchema(Schema):
    # Allow partial updates, ignore unknown fields
    class Meta:
        unknown = EXCLUDE

    # Fields admin can update
    email = fields.Email()
    role = fields.Str(validate=validate.OneOf(['admin', 'staff', 'user']))
    status = fields.Str(validate=validate.OneOf(['active', 'inactive', 'pending_approval', 'suspended']))
    full_name = fields.Str(allow_none=True, data_key="fullName")
    company_name = fields.Str(allow_none=True, data_key="companyName")

# Schema for Admin changing a user's password
class ChangePasswordSchema(Schema):
    password = fields.Str(required=True, load_only=True, validate=validate.Length(min=8))

# Schema for user list pagination response
class UserListSchema(Schema):
    items = fields.List(fields.Nested(UserSchema()), required=True)
    page = fields.Int(required=True)
    # Rename field to match data_key, remove data_key if needed
    # Option A: Rename field, keep data_key (should also work)
    # perPage = fields.Int(required=True, attribute="per_page", data_key="perPage")
    # Option B: Rename field, remove data_key (cleaner if output key matches field name)
    perPage = fields.Int(required=True, attribute="per_page") # Map field 'perPage' to object attribute 'per_page'
    total = fields.Int(required=True)
    pages = fields.Int(required=True)