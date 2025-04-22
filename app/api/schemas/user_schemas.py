# app/api/schemas/user_schemas.py
# -*- coding: utf-8 -*-
"""
Schemas for User API requests and responses.
"""
from marshmallow import Schema, fields, validate, EXCLUDE

# Base User Schema (for output, excluding sensitive info like password hash)
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

# Schema for creating a new user (Admin Input)
class CreateUserSchema(Schema):
    username = fields.Str(required=True, validate=validate.Length(min=3, error="Username must be at least 3 characters long."))
    email = fields.Email(required=True)
    password = fields.Str(required=True, load_only=True, validate=validate.Length(min=8, error="Password must be at least 8 characters long."))
    role = fields.Str(required=True, validate=validate.OneOf(['admin', 'staff', 'user']))
    status = fields.Str(load_default='active', validate=validate.OneOf(['active', 'inactive', 'pending_approval', 'suspended']))
    full_name = fields.Str(allow_none=True, data_key="fullName")
    company_name = fields.Str(allow_none=True, data_key="companyName")


# Schema for updating a user (Admin Input - Partial)
class UpdateUserSchema(Schema):
    class Meta:
        unknown = EXCLUDE # Allow partial updates

    # Fields admin can update (all optional on input)
    email = fields.Email()
    role = fields.Str(validate=validate.OneOf(['admin', 'staff', 'user']))
    status = fields.Str(validate=validate.OneOf(['active', 'inactive', 'pending_approval', 'suspended']))
    full_name = fields.Str(allow_none=True, data_key="fullName")
    company_name = fields.Str(allow_none=True, data_key="companyName")

# Schema for Admin changing a user's password (Input)
class ChangePasswordSchema(Schema):
    password = fields.Str(
        required=True,
        load_only=True, # Never dump the password
        validate=validate.Length(min=8, error="Password must be at least 8 characters long.")
    )

# Schema for user list pagination response
class UserListSchema(Schema):
    items = fields.List(fields.Nested(UserSchema()), required=True)
    page = fields.Int(required=True)
    perPage = fields.Int(required=True, attribute="per_page") # Map DB attribute 'per_page' to JSON field 'perPage'
    total = fields.Int(required=True)
    pages = fields.Int(required=True)