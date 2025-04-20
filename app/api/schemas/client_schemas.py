# -*- coding: utf-8 -*-
"""
Schemas for Client and PJSIP API requests and responses.
"""
from marshmallow import Schema, fields, validate, EXCLUDE

# --- PJSIP Sub-Schemas ---
# Note: These often mirror model fields closely

class PjsipEndpointSchema(Schema):
    class Meta:
        unknown = EXCLUDE # Allow partial updates

    # ID is required for creation/update but defined by client_identifier
    id = fields.Str(required=True) # Dump only? ID set based on client_identifier
    transport = fields.Str(allow_none=True)
    aors = fields.Str(allow_none=True) # Usually same as ID
    auth = fields.Str(allow_none=True) # Auth section ID for incoming
    context = fields.Str(required=True) # Context for incoming calls from endpoint
    disallow = fields.Str(load_default='all')
    allow = fields.Str(load_default='ulaw,alaw,gsm')
    direct_media = fields.Str(load_default='no')
    outbound_auth = fields.Str(allow_none=True) # Auth section ID for outgoing
    from_user = fields.Str(allow_none=True)
    from_domain = fields.Str(allow_none=True)
    callerid = fields.Str(allow_none=True)

class PjsipAorSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Str(required=True) # Usually same as ID
    contact = fields.Str(required=True) # SIP URI
    max_contacts = fields.Int(load_default=1)
    qualify_frequency = fields.Int(load_default=60)

class PjsipAuthSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Str(required=True) # Auth section name
    auth_type = fields.Str(load_default='userpass')
    username = fields.Str(allow_none=True)
    password = fields.Str(allow_none=True, load_only=True) # Load only for security
    realm = fields.Str(allow_none=True)

# --- Client Schemas ---

# Base Client Schema (for output)
class ClientSchema(Schema):
    id = fields.Int(dump_only=True)
    client_identifier = fields.Str(required=True, data_key="clientIdentifier")
    name = fields.Str(required=True)
    department = fields.Str(allow_none=True)
    status = fields.Str(required=True, validate=validate.OneOf(['active', 'inactive']))
    notes = fields.Str(allow_none=True)
    created_by = fields.Int(dump_only=True, data_key="createdBy") # User ID of creator
    created_at = fields.DateTime(dump_only=True, data_key="createdAt")
    updated_at = fields.DateTime(dump_only=True, data_key="updatedAt")

    # Nested PJSIP info for GET requests
    pjsip_endpoint = fields.Nested(PjsipEndpointSchema, dump_only=True, data_key="pjsipEndpoint")
    pjsip_aor = fields.Nested(PjsipAorSchema, dump_only=True, data_key="pjsipAor")
    pjsip_auth = fields.Nested(PjsipAuthSchema, dump_only=True, data_key="pjsipAuth", allow_none=True)


# Schema for Creating a Client (Admin)
class CreateClientSchema(Schema):
    # Client fields
    client_identifier = fields.Str(required=True, data_key="clientIdentifier")
    name = fields.Str(required=True)
    department = fields.Str(allow_none=True)
    status = fields.Str(load_default='active', validate=validate.OneOf(['active', 'inactive']))
    notes = fields.Str(allow_none=True)

    # PJSIP fields nested under 'pjsip' key
    pjsip = fields.Nested(
        lambda: PjsipWrapperSchema(context={'client_identifier_field': 'clientIdentifier'}), # Pass context
        required=True
    )

# Helper schema to structure PJSIP data during creation/update
class PjsipWrapperSchema(Schema):
    endpoint = fields.Nested(PjsipEndpointSchema, required=True)
    aor = fields.Nested(PjsipAorSchema, required=True)
    auth = fields.Nested(PjsipAuthSchema, required=False, allow_none=True) # Auth is optional

    # Ensure nested IDs match the top-level client identifier during load
    # This might require custom validation logic or careful structuring in the route handler
    # Alternatively, the service layer handles setting the correct IDs.


# Schema for Updating a Client (Admin)
class UpdateClientSchema(Schema):
    class Meta:
        unknown = EXCLUDE # Allow partial updates

    # Client fields (identifier cannot be changed)
    name = fields.Str()
    department = fields.Str(allow_none=True)
    status = fields.Str(validate=validate.OneOf(['active', 'inactive']))
    notes = fields.Str(allow_none=True)

    # PJSIP fields nested under 'pjsip' key
    # All parts are optional during update
    pjsip = fields.Nested(
        lambda: UpdatePjsipWrapperSchema(),
        required=False
    )

# Helper schema for updating PJSIP data (all nested parts are optional)
class UpdatePjsipWrapperSchema(Schema):
     endpoint = fields.Nested(PjsipEndpointSchema, required=False)
     aor = fields.Nested(PjsipAorSchema, required=False)
     auth = fields.Nested(PjsipAuthSchema, required=False, allow_none=True) # allow_none=True allows sending 'null' to delete auth


# Schema for client list pagination response
class ClientListSchema(Schema):
    items = fields.List(fields.Nested(ClientSchema()), required=True)
    page = fields.Int(required=True)
    per_page = fields.Int(required=True, data_key="perPage")
    total = fields.Int(required=True)
    pages = fields.Int(required=True)