# app/api/routes/admin_clients.py
# -*- coding: utf-8 -*-
"""
Admin API Routes for Client (Call Center) and PJSIP Management.
Handles transaction commit/rollback and catches custom service exceptions.
"""
from flask import Blueprint, request, jsonify, current_app, abort
from marshmallow import ValidationError
from flask_login import current_user # Needed to get creator_user_id

# Import db for controlling transaction commit/rollback in routes
from app.extensions import db
# Import Service and custom exceptions
from app.services.client_service import ClientService
from app.utils.exceptions import (
    ResourceNotFound, ConflictError, ServiceError, ValidationError as CustomValidationError
)
# Import Decorators
from app.utils.decorators import admin_required
# Import Schemas
from app.api.schemas.client_schemas import (
    ClientSchema, CreateClientSchema, UpdateClientSchema, ClientListSchema
)

# Create Blueprint
admin_clients_bp = Blueprint('admin_clients_api', __name__)

# Instantiate schemas
client_schema = ClientSchema()
create_client_schema = CreateClientSchema()
update_client_schema = UpdateClientSchema()
client_list_schema = ClientListSchema()

@admin_clients_bp.route('', methods=['POST'])
@admin_required
def admin_create_client():
    """Admin: Create a new client with PJSIP config."""
    json_data = request.get_json()
    if not json_data:
        abort(400, description="No input data provided.")

    try:
        # Validate and deserialize input using schema
        data = create_client_schema.load(json_data)
    except ValidationError as err: # Marshmallow validation error
        current_app.logger.warning(f"Admin create client validation error: {err.messages}")
        return jsonify({"errors": err.messages}), 400

    # Additional Validation (moved from original route for consistency, though could be in service)
    # This logic checks if nested PJSIP IDs match the main identifier *before* calling the service.
    # client_identifier = data.get('client_identifier')
    # pjsip_data = data.get('pjsip', {})
    # endpoint_id = pjsip_data.get('endpoint', {}).get('id')
    # aor_id = pjsip_data.get('aor', {}).get('id')
    # auth_config = pjsip_data.get('auth')
    # auth_id = auth_config.get('id') if isinstance(auth_config, dict) else None

    # validation_errors = {}
    # if not client_identifier: # Should be caught by schema, but defensive check
    #      validation_errors["clientIdentifier"] = ["This field is required."]
    # if endpoint_id != client_identifier:
    #     validation_errors["pjsip.endpoint.id"] = [f"Endpoint ID must match client_identifier ('{client_identifier}')."]
    # if aor_id != client_identifier:
    #     validation_errors["pjsip.aor.id"] = [f"AOR ID must match client_identifier ('{client_identifier}')."]
    # if auth_config and not auth_id: # ID is required if auth section is present
    #     validation_errors["pjsip.auth.id"] = ["Auth ID is required if auth section is provided."]

    # if validation_errors:
    #     current_app.logger.warning(f"Admin create client pre-service validation failed: {validation_errors}")
    #     return jsonify({"errors": validation_errors}), 400
    # --- End additional validation ---

    # Extract client and PJSIP data parts after validation for service call
    # Service expects specific dict structures now
    client_service_data = {k: v for k, v in data.items() if k not in ['pjsip']}
    pjsip_service_data = data.get('pjsip', {}) # Pass the nested dict

    try:
        creator_id = current_user.id
        # Call service - adds objects to session, may flush, raises custom exceptions
        # Service now handles internal checks including ID matching consistency
        new_client = ClientService.create_client_with_pjsip(
            creator_user_id=creator_id,
            client_data=client_service_data,
            pjsip_data=pjsip_service_data
        )

        # --- Commit transaction here in the route handler ---
        db.session.commit()
        current_app.logger.info(f"Admin {creator_id} successfully created client {new_client.id} ('{new_client.client_identifier}')")
        return jsonify(client_schema.dump(new_client)), 201 # Created

    except (ConflictError, CustomValidationError) as e: # Catch specific service errors
        db.session.rollback()
        current_app.logger.warning(f"Admin create client failed: {e}")
        status_code = 409 if isinstance(e, ConflictError) else 400
        abort(status_code, description=str(e))
    except ServiceError as e: # Catch broader service/DB errors
        db.session.rollback()
        current_app.logger.error(f"Admin create client service error: {e}", exc_info=True)
        abort(500, description=str(e))
    except Exception as e: # Catch unexpected errors
        db.session.rollback()
        current_app.logger.exception(f"Unexpected error creating client: {e}")
        abort(500, description="Could not create client due to an internal server error.")


@admin_clients_bp.route('', methods=['GET'])
@admin_required
def admin_get_clients():
    """Admin: Get list of clients (paginated)."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status', None, type=str)

    # Basic validation for status parameter
    if status is not None and status not in ['active', 'inactive']:
        abort(400, description="Invalid status filter. Allowed values: active, inactive.")

    try:
        # Service call is read-only
        paginated_clients = ClientService.get_all_clients(page=page, per_page=per_page, status=status)
        # Prepare data structure matching the List schema
        result_data = {
            'items': paginated_clients.items,
            'page': paginated_clients.page,
            'per_page': paginated_clients.per_page, # Source attribute name
            'total': paginated_clients.total,
            'pages': paginated_clients.pages
        }
        return jsonify(client_list_schema.dump(result_data)), 200
    except Exception as e: # Catch unexpected errors during fetch/serialization
        current_app.logger.exception(f"Unexpected error fetching clients: {e}")
        abort(500, description="Could not fetch clients.")


@admin_clients_bp.route('/<int:client_id>', methods=['GET'])
@admin_required
def admin_get_client(client_id):
    """Admin: Get details for a specific client, including PJSIP config."""
    client = ClientService.get_client_by_id(client_id) # Service eager loads PJSIP
    if not client:
        abort(404, description=f"Client with ID {client_id} not found.")

    # Schema handles serialization, including nested PJSIP data
    return jsonify(client_schema.dump(client)), 200


@admin_clients_bp.route('/<int:client_id>', methods=['PUT'])
@admin_required
def admin_update_client(client_id):
    """Admin: Update client details and/or PJSIP config."""
    json_data = request.get_json()
    if not json_data:
        abort(400, description="No input data provided.")

    try:
        # Validate input data (allows partial updates via schema)
        data_to_update = update_client_schema.load(json_data)
    except ValidationError as err: # Marshmallow validation error
        current_app.logger.warning(f"Admin update client validation error for ID {client_id}: {err.messages}")
        return jsonify({"errors": err.messages}), 400

    if not data_to_update:
         abort(400, description="No valid fields provided for update.")

    # Separate client and PJSIP parts using schema field names
    client_service_data = {k: v for k, v in data_to_update.items() if k != 'pjsip'}
    pjsip_service_data = data_to_update.get('pjsip', {}) # Use empty dict if key missing

    try:
        # Call service - updates objects in session, raises custom exceptions
        updated_client = ClientService.update_client_with_pjsip(
            client_id=client_id,
            client_data=client_service_data,
            pjsip_data=pjsip_service_data
        )

        # --- Commit transaction here in the route handler ---
        db.session.commit()
        current_app.logger.info(f"Admin {current_user.id} successfully updated client {client_id}")
        # Return the updated client data after successful commit
        return jsonify(client_schema.dump(updated_client)), 200

    except ResourceNotFound as e:
        db.session.rollback()
        current_app.logger.warning(f"Admin update client failed: {e}")
        abort(404, description=str(e))
    except (ConflictError, CustomValidationError) as e: # Catch specific service validation/conflict errors
        db.session.rollback()
        current_app.logger.warning(f"Admin update client failed for ID {client_id}: {e}")
        status_code = 409 if isinstance(e, ConflictError) else 400
        abort(status_code, description=str(e))
    except ServiceError as e: # Catch broader service/DB errors during flush
        db.session.rollback()
        current_app.logger.error(f"Admin update client service error for ID {client_id}: {e}", exc_info=True)
        abort(500, description=str(e))
    except Exception as e: # Catch unexpected errors
        db.session.rollback()
        current_app.logger.exception(f"Unexpected error updating client {client_id}: {e}")
        abort(500, description="Could not update client due to an internal error.")


@admin_clients_bp.route('/<int:client_id>', methods=['DELETE'])
@admin_required
def admin_delete_client(client_id):
    """Admin: Delete a client and its PJSIP config."""
    try:
        # Call the service - marks for deletion in session, raises custom exceptions
        ClientService.delete_client(client_id)

        # --- Commit Transaction ---
        db.session.commit()
        current_app.logger.info(f"Admin {current_user.id} successfully deleted client {client_id}")
        return '', 204 # No Content

    except ResourceNotFound as e:
        db.session.rollback()
        current_app.logger.warning(f"Admin delete client failed: {e}")
        abort(404, description=str(e))
    except ConflictError as e: # Catch specific conflict (e.g., linked to active campaign)
        db.session.rollback()
        current_app.logger.warning(f"Admin delete client conflict for ID {client_id}: {e}")
        abort(409, description=str(e)) # 409 Conflict
    except ServiceError as e: # Catch broader service/DB errors during flush/delete check
        db.session.rollback()
        current_app.logger.error(f"Admin delete client service error for ID {client_id}: {e}", exc_info=True)
        abort(500, description=str(e))
    except Exception as e: # Catch unexpected errors
        db.session.rollback()
        current_app.logger.exception(f"Unexpected error deleting client {client_id}: {e}")
        abort(500, description="Could not delete client due to an internal server error.")