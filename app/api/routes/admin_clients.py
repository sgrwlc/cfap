# -*- coding: utf-8 -*-
"""
Admin API Routes for Client (Call Center) and PJSIP Management.
"""
from flask import Blueprint, request, jsonify, current_app, abort
from marshmallow import ValidationError
from flask_login import current_user # Needed to get creator_user_id

from app.services.client_service import ClientService
from app.utils.decorators import admin_required # Use admin decorator (or staff_required if applicable)
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
        # Note: PJSIP IDs validation (matching identifier) might need custom logic
        # or rely on service layer validation for atomicity.
        data = create_client_schema.load(json_data)
    except ValidationError as err:
        current_app.logger.warning(f"Admin create client validation error: {err.messages}")
        return jsonify(err.messages), 400

    # Extract client and PJSIP data parts
    client_data = {k: v for k, v in data.items() if k != 'pjsip'}
    pjsip_data = data.get('pjsip', {}) # Should always be present due to schema requirement

    # --- Add validation: Ensure nested PJSIP IDs match client_identifier ---
    client_identifier = client_data.get('clientIdentifier')
    if pjsip_data.get('endpoint', {}).get('id') != client_identifier:
         return jsonify({"pjsip.endpoint.id": ["Endpoint ID must match clientIdentifier."]}), 400
    if pjsip_data.get('aor', {}).get('id') != client_identifier:
         return jsonify({"pjsip.aor.id": ["AOR ID must match clientIdentifier."]}), 400
    if pjsip_data.get('auth') and pjsip_data['auth'].get('id') is None:
         return jsonify({"pjsip.auth.id": ["Auth ID is required if auth section is provided."]}), 400
    # --- End validation ---

    try:
        creator_id = current_user.id
        new_client = ClientService.create_client_with_pjsip(
            creator_user_id=creator_id,
            client_data=client_data,
            pjsip_data=pjsip_data
        )
        # Serialize response (includes nested PJSIP data)
        return jsonify(client_schema.dump(new_client)), 201 # Created
    except ValueError as e:
        current_app.logger.error(f"Admin create client error: {e}")
        status_code = 409 if 'already exists' in str(e) or 'conflict' in str(e).lower() else 400
        abort(status_code, description=str(e))
    except Exception as e:
        current_app.logger.exception(f"Unexpected error creating client: {e}")
        abort(500, description="Could not create client.")


@admin_clients_bp.route('', methods=['GET'])
@admin_required # Or staff_required
def admin_get_clients():
    """Admin: Get list of clients (paginated)."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status', None, type=str) # Filter by 'active' or 'inactive'

    try:
        paginated_clients = ClientService.get_all_clients(page=page, per_page=per_page, status=status)
        result = client_list_schema.dump({
            'items': paginated_clients.items,
            'page': paginated_clients.page,
            'perPage': paginated_clients.per_page,
            'total': paginated_clients.total,
            'pages': paginated_clients.pages
        })
        return jsonify(result), 200
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

    # Serialize response (includes nested PJSIP data automatically)
    return jsonify(client_schema.dump(client)), 200


@admin_clients_bp.route('/<int:client_id>', methods=['PUT'])
@admin_required # Or staff_required
def admin_update_client(client_id):
    """Admin: Update client details and/or PJSIP config."""
    json_data = request.get_json()
    if not json_data:
        abort(400, description="No input data provided.")

    try:
        # Validate input data (allows partial updates)
        data_to_update = update_client_schema.load(json_data)
    except ValidationError as err:
        current_app.logger.warning(f"Admin update client validation error for ID {client_id}: {err.messages}")
        return jsonify(err.messages), 400

    if not data_to_update:
         abort(400, description="No valid fields provided for update.")

    # Separate client and PJSIP parts
    client_data = {k: v for k, v in data_to_update.items() if k != 'pjsip'}
    pjsip_data = data_to_update.get('pjsip', {}) # Use {} if pjsip key not sent

    try:
        updated_client = ClientService.update_client_with_pjsip(
            client_id=client_id,
            client_data=client_data,
            pjsip_data=pjsip_data
        )
        return jsonify(client_schema.dump(updated_client)), 200
    except ValueError as e:
        current_app.logger.error(f"Admin update client error for ID {client_id}: {e}")
        status_code = 404 if 'not found' in str(e) else 400
        abort(status_code, description=str(e))
    except Exception as e:
        current_app.logger.exception(f"Unexpected error updating client {client_id}: {e}")
        abort(500, description="Could not update client.")


@admin_clients_bp.route('/<int:client_id>', methods=['DELETE'])
@admin_required # Or staff_required
def admin_delete_client(client_id):
    """Admin: Delete a client and its PJSIP config."""
    try:
        success = ClientService.delete_client(client_id)
        if success:
            return '', 204 # No Content
        else:
             # Should not happen if service raises ValueError
             abort(500, description="Client deletion failed for an unknown reason.")
    except ValueError as e: # Catches not found, linked to active campaign, or DB errors
        current_app.logger.error(f"Admin delete client error for ID {client_id}: {e}")
        status_code = 404 if 'not found' in str(e) else (409 if 'linked to active campaigns' in str(e) else 500)
        abort(status_code, description=str(e))
    except Exception as e:
        current_app.logger.exception(f"Unexpected error deleting client {client_id}: {e}")
        abort(500, description="Could not delete client.")