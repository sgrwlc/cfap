# -*- coding: utf-8 -*-
"""
Seller API Routes for DID Management.
"""
from flask import Blueprint, request, jsonify, current_app, abort
from flask_login import current_user
from marshmallow import ValidationError

from app.services.did_service import DidService
from app.utils.decorators import seller_required # Use the seller decorator
from app.api.schemas.did_schemas import (
    DidSchema, CreateDidSchema, UpdateDidSchema, DidListSchema
)

# Create Blueprint
seller_dids_bp = Blueprint('seller_dids_api', __name__)

# Instantiate schemas
did_schema = DidSchema()
dids_schema = DidSchema(many=True)
create_did_schema = CreateDidSchema()
update_did_schema = UpdateDidSchema()
did_list_schema = DidListSchema()

@seller_dids_bp.route('', methods=['POST'])
@seller_required
def seller_add_did():
    """Seller: Add a new DID."""
    json_data = request.get_json()
    if not json_data:
        abort(400, description="No input data provided.")

    try:
        data = create_did_schema.load(json_data)
    except ValidationError as err:
        current_app.logger.warning(f"Seller add DID validation error for user {current_user.id}: {err.messages}")
        return jsonify(err.messages), 400

    try:
        new_did = DidService.add_did(
            user_id=current_user.id,
            **data
        )
        return jsonify(did_schema.dump(new_did)), 201 # Created
    except ValueError as e:
        current_app.logger.error(f"Seller add DID error for user {current_user.id}: {e}")
        status_code = 409 if 'already exists' in str(e) else 400
        abort(status_code, description=str(e))
    except Exception as e:
        current_app.logger.exception(f"Unexpected error adding DID for user {current_user.id}: {e}")
        abort(500, description="Could not add DID.")


@seller_dids_bp.route('', methods=['GET'])
@seller_required
def seller_get_dids():
    """Seller: Get list of own DIDs (paginated)."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status', None, type=str) # Filter by 'active' or 'inactive'

    try:
        paginated_dids = DidService.get_dids_for_user(
            user_id=current_user.id,
            page=page,
            per_page=per_page,
            status=status
        )
        result = did_list_schema.dump({
            'items': paginated_dids.items,
            'page': paginated_dids.page,
            'perPage': paginated_dids.per_page,
            'total': paginated_dids.total,
            'pages': paginated_dids.pages
        })
        return jsonify(result), 200
    except Exception as e:
        current_app.logger.exception(f"Unexpected error fetching DIDs for user {current_user.id}: {e}")
        abort(500, description="Could not fetch DIDs.")


@seller_dids_bp.route('/<int:did_id>', methods=['GET'])
@seller_required
def seller_get_did(did_id):
    """Seller: Get details of a specific owned DID."""
    did = DidService.get_did_by_id(did_id=did_id, user_id=current_user.id) # Ensure ownership
    if not did:
        abort(404, description=f"DID with ID {did_id} not found or not owned by user.")

    return jsonify(did_schema.dump(did)), 200


@seller_dids_bp.route('/<int:did_id>', methods=['PUT'])
@seller_required
def seller_update_did(did_id):
    """Seller: Update an owned DID (description, status)."""
    json_data = request.get_json()
    if not json_data:
        abort(400, description="No input data provided.")

    try:
        data_to_update = update_did_schema.load(json_data)
    except ValidationError as err:
        current_app.logger.warning(f"Seller update DID validation error for ID {did_id}, user {current_user.id}: {err.messages}")
        return jsonify(err.messages), 400

    if not data_to_update:
        abort(400, description="No valid fields provided for update.")

    try:
        updated_did = DidService.update_did(
            did_id=did_id,
            user_id=current_user.id, # Pass owner ID for verification
            **data_to_update
        )
        return jsonify(did_schema.dump(updated_did)), 200
    except ValueError as e:
        current_app.logger.error(f"Seller update DID error for ID {did_id}, user {current_user.id}: {e}")
        status_code = 404 if 'not found' in str(e) else (403 if 'authorized' in str(e) else 400)
        abort(status_code, description=str(e))
    except Exception as e:
        current_app.logger.exception(f"Unexpected error updating DID {did_id} for user {current_user.id}: {e}")
        abort(500, description="Could not update DID.")


@seller_dids_bp.route('/<int:did_id>', methods=['DELETE'])
@seller_required
def seller_delete_did(did_id):
    """Seller: Delete an owned DID."""
    try:
        success = DidService.delete_did(did_id=did_id, user_id=current_user.id) # Pass owner ID
        if success:
            return '', 204 # No Content
        else:
             abort(500, description="DID deletion failed for an unknown reason.")
    except ValueError as e:
        current_app.logger.error(f"Seller delete DID error for ID {did_id}, user {current_user.id}: {e}")
        status_code = 404 if 'not found' in str(e) else (403 if 'authorized' in str(e) else 500)
        abort(status_code, description=str(e))
    except Exception as e:
        current_app.logger.exception(f"Unexpected error deleting DID {did_id} for user {current_user.id}: {e}")
        abort(500, description="Could not delete DID.")