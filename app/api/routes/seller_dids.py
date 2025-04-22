# app/api/routes/seller_dids.py
# -*- coding: utf-8 -*-
"""
Seller API Routes for DID Management.
Handles transaction commit/rollback and catches custom service exceptions.
"""
import logging # Keep logging import
from flask import Blueprint, request, jsonify, current_app, abort
from flask_login import current_user
from marshmallow import ValidationError

# Import db for transaction control
from app.extensions import db
# Import Service and custom exceptions
from app.services.did_service import DidService
from app.utils.exceptions import ResourceNotFound, ConflictError, ServiceError, ValidationError as CustomValidationError, AuthorizationError
# Import Decorators
from app.utils.decorators import seller_required
# Import Schemas
from app.api.schemas.did_schemas import (
    DidSchema, CreateDidSchema, UpdateDidSchema, DidListSchema
)

# Create Blueprint
seller_dids_bp = Blueprint('seller_dids_api', __name__)

# Instantiate schemas
did_schema = DidSchema()
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
        # Validate input using schema
        data = create_did_schema.load(json_data)
    except ValidationError as err: # Marshmallow validation error
        current_app.logger.warning(f"Seller add DID validation error for user {current_user.id}: {err.messages}")
        # Return validation errors in structured format
        return jsonify({"errors": err.messages}), 400

    try:
        # Call service - adds DID to session, raises custom exceptions
        new_did = DidService.add_did(
            user_id=current_user.id,
            **data
        )

        # --- Commit Transaction ---
        db.session.commit()
        current_app.logger.info(f"Seller {current_user.id} successfully added DID {new_did.id} ('{new_did.number}')")
        return jsonify(did_schema.dump(new_did)), 201 # Created

    except (ConflictError, CustomValidationError) as e: # Catch specific service errors
        db.session.rollback()
        current_app.logger.warning(f"Seller add DID failed for user {current_user.id}: {e}")
        status_code = 409 if isinstance(e, ConflictError) else 400
        abort(status_code, description=str(e))
    except ServiceError as e: # Catch broader service/DB errors
        db.session.rollback()
        current_app.logger.error(f"Seller add DID service error for user {current_user.id}: {e}", exc_info=True)
        abort(500, description=str(e))
    except Exception as e: # Catch unexpected errors
        db.session.rollback()
        current_app.logger.exception(f"Unexpected error adding DID for user {current_user.id}: {e}")
        abort(500, description="Could not add DID due to an internal error.")


@seller_dids_bp.route('', methods=['GET'])
@seller_required
def seller_get_dids():
    """Seller: Get list of own DIDs (paginated and filterable)."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status', None, type=str)

    # Validate status filter (basic check)
    allowed_statuses = ['active', 'inactive']
    if status is not None and status not in allowed_statuses:
        abort(400, description=f"Invalid status filter. Allowed values: {', '.join(allowed_statuses)}")

    try:
        # Service call is read-only
        paginated_dids = DidService.get_dids_for_user(
            user_id=current_user.id,
            page=page,
            per_page=per_page,
            status=status
        )
        # Prepare data structure for List schema
        result_data = {
            'items': paginated_dids.items,
            'page': paginated_dids.page,
            'per_page': paginated_dids.per_page, # Source attribute name
            'total': paginated_dids.total,
            'pages': paginated_dids.pages
        }
        # Schema maps 'per_page' to 'perPage' output key
        return jsonify(did_list_schema.dump(result_data)), 200
    except Exception as e: # Catch unexpected errors during fetch/serialization
        current_app.logger.exception(f"Unexpected error fetching DIDs for user {current_user.id}: {e}")
        abort(500, description="Could not fetch DIDs.")


@seller_dids_bp.route('/<int:did_id>', methods=['GET'])
@seller_required
def seller_get_did(did_id):
    """Seller: Get details of a specific owned DID."""
    # Service handles ownership check
    did = DidService.get_did_by_id(did_id=did_id, user_id=current_user.id)
    if not did:
        # Service didn't find it or user doesn't own it
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
        # Validate input using schema (allows partial updates)
        data_to_update = update_did_schema.load(json_data)
    except ValidationError as err: # Marshmallow validation error
        current_app.logger.warning(f"Seller update DID validation error for ID {did_id}, user {current_user.id}: {err.messages}")
        return jsonify({"errors": err.messages}), 400

    if not data_to_update:
        abort(400, description="No valid fields provided for update.")

    try:
        # Call service - updates object in session, raises custom exceptions
        updated_did = DidService.update_did(
            did_id=did_id,
            user_id=current_user.id, # Pass owner ID for verification
            **data_to_update
        )

        # --- Commit Transaction ---
        db.session.commit()
        current_app.logger.info(f"Seller {current_user.id} successfully updated DID {did_id}")
        return jsonify(did_schema.dump(updated_did)), 200

    except ResourceNotFound as e:
        db.session.rollback()
        current_app.logger.warning(f"Seller update DID failed: {e}")
        abort(404, description=str(e))
    except AuthorizationError as e:
        db.session.rollback()
        current_app.logger.warning(f"Seller update DID authorization failed for user {current_user.id}, DID {did_id}: {e}")
        abort(403, description=str(e)) # Return 403 Forbidden
    except (CustomValidationError, ServiceError) as e: # Catch validation or DB errors from service
         db.session.rollback()
         current_app.logger.error(f"Seller update DID service error for ID {did_id}, user {current_user.id}: {e}", exc_info=True)
         status_code = 400 if isinstance(e, CustomValidationError) else 500
         abort(status_code, description=str(e))
    except Exception as e: # Catch unexpected errors
        db.session.rollback()
        current_app.logger.exception(f"Unexpected error updating DID {did_id} for user {current_user.id}: {e}")
        abort(500, description="Could not update DID due to an internal error.")


@seller_dids_bp.route('/<int:did_id>', methods=['DELETE'])
@seller_required
def seller_delete_did(did_id):
    """Seller: Delete an owned DID."""
    try:
        # Call service - marks DID for deletion in session, raises custom exceptions
        DidService.delete_did(did_id=did_id, user_id=current_user.id) # Pass owner ID

        # --- Commit Transaction ---
        db.session.commit()
        current_app.logger.info(f"Seller {current_user.id} successfully deleted DID {did_id}")
        return '', 204 # No Content

    except ResourceNotFound as e:
        db.session.rollback()
        current_app.logger.warning(f"Seller delete DID failed: {e}")
        abort(404, description=str(e))
    except AuthorizationError as e:
        db.session.rollback()
        current_app.logger.warning(f"Seller delete DID authorization failed for user {current_user.id}, DID {did_id}: {e}")
        abort(403, description=str(e)) # Return 403 Forbidden
    except (ConflictError, ServiceError) as e: # Catch conflict (e.g., if check added) or DB errors
         db.session.rollback()
         current_app.logger.error(f"Seller delete DID service error for ID {did_id}, user {current_user.id}: {e}", exc_info=True)
         status_code = 409 if isinstance(e, ConflictError) else 500
         abort(status_code, description=str(e))
    except Exception as e: # Catch unexpected errors
        db.session.rollback()
        current_app.logger.exception(f"Unexpected error deleting DID {did_id} for user {current_user.id}: {e}")
        abort(500, description="Could not delete DID due to an internal error.")