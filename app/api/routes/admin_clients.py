# -*- coding: utf-8 -*-
"""
Admin API Routes for Client (Call Center) and PJSIP Management.
"""
from flask import Blueprint, request, jsonify, current_app, abort
from marshmallow import ValidationError
from flask_login import current_user # Needed to get creator_user_id

# Import db for controlling transaction commit/rollback in routes
from app.extensions import db
# Import Service
from app.services.client_service import ClientService
# Import Decorators
from app.utils.decorators import admin_required # Use admin decorator (or staff_required if applicable)
# Import Schemas
from app.api.schemas.client_schemas import (
    ClientSchema, CreateClientSchema, UpdateClientSchema, ClientListSchema
)

# Create Blueprint
admin_clients_bp = Blueprint('admin_clients_api', __name__)

# Instantiate schemas
client_schema = ClientSchema()
clients_schema = ClientSchema(many=True) # For lists without pagination meta
create_client_schema = CreateClientSchema()
update_client_schema = UpdateClientSchema()
client_list_schema = ClientListSchema()

@admin_clients_bp.route('', methods=['POST'])
@admin_required # Or staff_required
def admin_create_client():
    """Admin: Create a new client with PJSIP config."""
    json_data = request.get_json()
    if not json_data:
        abort(400, description="No input data provided.")

    try:
        # Validate and deserialize input
        data = create_client_schema.load(json_data)
    except ValidationError as err:
        current_app.logger.warning(f"Admin create client validation error: {err.messages}")
        return jsonify({"errors": err.messages}), 400 # Return validation errors

    # Extract client and PJSIP data parts after validation
    client_data = {k: v for k, v in data.items() if k != 'pjsip'}
    pjsip_data = data.get('pjsip', {})

    # --- Validation for PJSIP IDs matching client identifier ---
    client_identifier_value = client_data.get('client_identifier')
    if not client_identifier_value:
        # Corrected: Removed extra parenthesis before comma
        return jsonify({"errors": {"client_identifier": ["This field is required."]}}), 400

    endpoint_id = pjsip_data.get('endpoint', {}).get('id')
    aor_id = pjsip_data.get('aor', {}).get('id')
    auth_config = pjsip_data.get('auth')
    auth_id = auth_config.get('id') if isinstance(auth_config, dict) else None

    errors = {} # Initialize errors dict
    if endpoint_id != client_identifier_value:
        errors["pjsip.endpoint.id"] = [f"Endpoint ID must match client_identifier ('{client_identifier_value}')."]
    if aor_id != client_identifier_value:
        errors["pjsip.aor.id"] = [f"AOR ID must match client_identifier ('{client_identifier_value}')."]
    if auth_config and not auth_id:
        errors["pjsip.auth.id"] = ["Auth ID is required if auth section is provided."]

    if errors: # Check if any validation errors were found
        return jsonify({"errors": errors}), 400
    # --- End validation ---

    try:
        creator_id = current_user.id
        # Call service - adds objects to session
        new_client = ClientService.create_client_with_pjsip(
            creator_user_id=creator_id,
            client_data=client_data,
            pjsip_data=pjsip_data
        )

        # --- Commit transaction here in the route handler ---
        try:
            db.session.commit()
            current_app.logger.info(f"Admin {creator_id} successfully created client {new_client.id} ('{new_client.client_identifier}')")
            return jsonify(client_schema.dump(new_client)), 201 # Created
        except Exception as commit_err:
            db.session.rollback()
            current_app.logger.exception(f"Database commit error creating client: {commit_err}")
            abort(500, description="Database error during client creation.")
        # --- End Commit Logic ---

    except ValueError as e: # Catch specific errors raised by the service
        db.session.rollback()
        current_app.logger.error(f"Admin create client service error: {e}")
        status_code = 409 if 'already exists' in str(e) or 'conflict' in str(e).lower() else 400
        abort(status_code, description=str(e))
    except Exception as e: # Catch unexpected errors during service call
        db.session.rollback()
        current_app.logger.exception(f"Unexpected error creating client: {e}")
        abort(500, description="Could not create client due to an internal error.")


@admin_clients_bp.route('', methods=['GET'])
@admin_required # Or staff_required
def admin_get_clients():
    """Admin: Get list of clients (paginated)."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status', None, type=str)

    try:
        paginated_clients = ClientService.get_all_clients(page=page, per_page=per_page, status=status)
        # Prepare data structure matching the List schema, using attribute names
        result_data = {
            'items': paginated_clients.items,
            'page': paginated_clients.page,
            'per_page': paginated_clients.per_page, # Source attribute name
            'total': paginated_clients.total,
            'pages': paginated_clients.pages
        }
        # Schema maps 'per_page' attribute to 'perPage' output key
        return jsonify(client_list_schema.dump(result_data)), 200
    except Exception as e:
        current_app.logger.exception(f"Unexpected error fetching clients: {e}")
        abort(500, description="Could not fetch clients.")


@admin_clients_bp.route('/<int:client_id>', methods=['GET'])
@admin_required # Or staff_required
def admin_get_client(client_id):
    """Admin: Get details for a specific client, including PJSIP config."""
    client = ClientService.get_client_by_id(client_id)
    if not client:
        abort(404, description=f"Client with ID {client_id} not found.")

    # Schema handles serialization, including nested PJSIP data
    return jsonify(client_schema.dump(client)), 200


@admin_clients_bp.route('/<int:client_id>', methods=['PUT'])
@admin_required # Or staff_required
def admin_update_client(client_id):
    """Admin: Update client details and/or PJSIP config."""
    json_data = request.get_json()
    if not json_data:
        abort(400, description="No input data provided.")

    try:
        # Validate input data (allows partial updates via schema)
        data_to_update = update_client_schema.load(json_data)
    except ValidationError as err:
        current_app.logger.warning(f"Admin update client validation error for ID {client_id}: {err.messages}")
        return jsonify({"errors": err.messages}), 400

    if not data_to_update:
         abort(400, description="No valid fields provided for update.")

    # Separate client and PJSIP parts using schema field names
    client_data = {k: v for k, v in data_to_update.items() if k != 'pjsip'}
    pjsip_data = data_to_update.get('pjsip', {})

    try:
        # Call service - this updates objects in session but SHOULD NOT COMMIT
        updated_client = ClientService.update_client_with_pjsip(
            client_id=client_id,
            client_data=client_data,
            pjsip_data=pjsip_data
        )

        # --- Commit transaction here in the route handler ---
        try:
            db.session.commit()
            current_app.logger.info(f"Admin {current_user.id} successfully updated client {client_id}")
            # Return the updated client data after successful commit
            return jsonify(client_schema.dump(updated_client)), 200
        except Exception as commit_err:
            db.session.rollback()
            current_app.logger.exception(f"Database commit error updating client {client_id}: {commit_err}")
            abort(500, description="Database error during client update.")
        # --- End Commit Logic ---

    except ValueError as e: # Catch specific service errors (not found, validation)
        db.session.rollback()
        current_app.logger.error(f"Admin update client service error for ID {client_id}: {e}")
        status_code = 404 if 'not found' in str(e).lower() else 400
        abort(status_code, description=str(e))
    except Exception as e: # Catch unexpected errors during service call
        db.session.rollback()
        current_app.logger.exception(f"Unexpected error updating client {client_id}: {e}")
        abort(500, description="Could not update client due to an internal error.")


@admin_clients_bp.route('/<int:client_id>', methods=['DELETE'])
@admin_required # Or staff_required
def admin_delete_client(client_id):
    """Admin: Delete a client and its PJSIP config."""
    try:
        # Call the service. It handles checks, deletion, and commit/rollback internally for DELETE.
        # It returns True or raises ValueError.
        ClientService.delete_client(client_id)
        # If service call completes without exception, deletion was successful
        return '', 204 # No Content

    except ValueError as e: # Catch specific ValueErrors raised by the service
        error_message = str(e)
        # Log as warning because these are expected application/data logic errors
        current_app.logger.warning(f"Admin delete client error for ID {client_id}: {error_message}")
        # Determine status code based on error message content
        if 'not found' in error_message.lower():
            status_code = 404
        elif 'linked to active campaigns' in error_message.lower():
            status_code = 409 # Conflict
        elif 'database error' in error_message.lower(): # Catch commit errors from service
             status_code = 500
        else:
            # Treat other ValueErrors as potential bad requests if not categorized
            status_code = 400
        abort(status_code, description=error_message)

    except Exception as e: # Catch truly unexpected errors (not ValueErrors)
        current_app.logger.exception(f"Unexpected error during client deletion process for ID {client_id}: {e}")
        # Ensure rollback for safety in case service failed before rollback
        try:
            db.session.rollback()
            current_app.logger.info(f"Rolled back session after unexpected error during client delete for ID {client_id}")
        except Exception as rb_err:
            current_app.logger.error(f"Error during rollback after exception in delete client route for ID {client_id}: {rb_err}")
        abort(500, description="Could not delete client due to an internal server error.")