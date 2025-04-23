# app/api/schemas/client_schemas.py
# -*- coding: utf-8 -*-
"""
Schemas for Client and PJSIP API requests and responses.
"""
from marshmallow import Schema, fields, validate, EXCLUDE, ValidationError

# --- PJSIP Sub-Schemas ---

class PjsipEndpointSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Str(required=True) # ID matches client_identifier, dump only
    transport = fields.Str(allow_none=True)
    aors = fields.Str(required=True) # Required field
    auth = fields.Str(allow_none=True)
    context = fields.Str(required=True) # Required field
    disallow = fields.Str(load_default='all')
    allow = fields.Str(load_default='ulaw,alaw,gsm')
    direct_media = fields.Str(load_default='no', validate=validate.OneOf(['yes', 'no', 'nonat', 'update']))
    outbound_auth = fields.Str(allow_none=True)
    from_user = fields.Str(allow_none=True)
    from_domain = fields.Str(allow_none=True)
    callerid = fields.Str(allow_none=True)

class PjsipAorSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Str(required=True) # ID matches client_identifier, dump only
    contact = fields.Str(required=True) # Required field
    max_contacts = fields.Int(load_default=1, validate=validate.Range(min=1))
    qualify_frequency = fields.Int(load_default=60, validate=validate.Range(min=0))

class PjsipAuthSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Str(required=True) # Required field
    auth_type = fields.Str(load_default='userpass', validate=validate.OneOf(['userpass', 'md5', 'google_oauth']))
    username = fields.Str(allow_none=True)
    password = fields.Str(allow_none=True, load_only=True) # Load only for security
    realm = fields.Str(allow_none=True)

    # Example validation: If auth_type is userpass, username and password should be provided on input.
    # This is often better handled in the service layer logic before creating the model,
    # but can be added here for stricter schema validation if needed.
    # @validates_schema
    # def validate_userpass_fields(self, data, **kwargs):
    #     if data.get('auth_type') == 'userpass' and not kwargs.get('partial'): # Only apply on full load (POST)
    #         errors = {}
    #         if not data.get('username'):
    #             errors['username'] = ['Username is required for auth_type userpass.']
    #         if not data.get('password'):
    #             errors['password'] = ['Password is required for auth_type userpass.']
    #         if errors:
    #             raise ValidationError(errors)

# --- Client Schemas ---

# Base Client Schema (for output)
class ClientSchema(Schema):
    id = fields.Int(dump_only=True)
    client_identifier = fields.Str(required=True, data_key="clientIdentifier")
    name = fields.Str(required=True)
    department = fields.Str(allow_none=True)
    status = fields.Str(required=True, validate=validate.OneOf(['active', 'inactive']))
    notes = fields.Str(allow_none=True)
    # Use dump_only=True explicitly for clarity on nested fields
    pjsip_endpoint = fields.Nested(PjsipEndpointSchema, dump_only=True, data_key="pjsipEndpoint")
    pjsip_aor = fields.Nested(PjsipAorSchema, dump_only=True, data_key="pjsipAor")
    pjsip_auth = fields.Nested(PjsipAuthSchema, dump_only=True, data_key="pjsipAuth", allow_none=True)

    created_by = fields.Int(dump_only=True, data_key="createdBy")
    created_at = fields.DateTime(dump_only=True, data_key="createdAt")
    updated_at = fields.DateTime(dump_only=True, data_key="updatedAt")


# --- Schemas for Input/Requests ---

# Helper schema to structure PJSIP data during creation input
class PjsipInputWrapperSchema(Schema):
    endpoint = fields.Nested(PjsipEndpointSchema, required=True)
    aor = fields.Nested(PjsipAorSchema, required=True)
    auth = fields.Nested(PjsipAuthSchema, required=False, allow_none=True) # Auth is optional

# Schema for Creating a Client (Admin Input)
class CreateClientSchema(Schema):
    client_identifier = fields.Str(required=True, data_key="clientIdentifier")
    name = fields.Str(required=True, validate=validate.Length(min=1))
    department = fields.Str(allow_none=True)
    status = fields.Str(load_default='active', validate=validate.OneOf(['active', 'inactive']))
    notes = fields.Str(allow_none=True)
    pjsip = fields.Nested(PjsipInputWrapperSchema, required=True)


# Helper schema for updating PJSIP data (nested parts are optional)
class UpdatePjsipInputWrapperSchema(Schema):
    # Allow providing partial data for endpoint/aor/auth when updating
    # Requires the nested schema itself to handle partial loading, or set partial=True here
    endpoint = fields.Nested(lambda: PjsipEndpointSchema(partial=True), required=False)
    aor = fields.Nested(lambda: PjsipAorSchema(partial=True), required=False)
    auth = fields.Nested(lambda: PjsipAuthSchema(partial=True), required=False, allow_none=True) # Allow null to remove


# Schema for Updating a Client (Admin Input - Partial)
class UpdateClientSchema(Schema):
    class Meta:
        unknown = EXCLUDE # Allow partial updates
    # Client fields (identifier cannot be changed - enforced by service/route)
    name = fields.Str(validate=validate.Length(min=1))
    department = fields.Str(allow_none=True)
    status = fields.Str(validate=validate.OneOf(['active', 'inactive']))
    notes = fields.Str(allow_none=True)

    # PJSIP fields nested under 'pjsip' key
    pjsip = fields.Nested(UpdatePjsipInputWrapperSchema, required=False)


# Schema for client list pagination response
class ClientListSchema(Schema):
    items = fields.List(fields.Nested(ClientSchema()), required=True)
    page = fields.Int(required=True)
    perPage = fields.Int(required=True, attribute="per_page")
    total = fields.Int(required=True)
    pages = fields.Int(required=True)