# app/api/routes/seller_campaigns.py
# -*- coding: utf-8 -*-
"""
Seller API Routes for Campaign and Campaign-Client Settings Management.
Handles transaction commit/rollback and catches custom service exceptions.
Relies on Service layer for all DB interactions and validation.
"""
from flask import Blueprint, request, jsonify, current_app, abort
from flask_login import current_user
from marshmallow import ValidationError
from werkzeug.exceptions import HTTPException

# Import db for transaction control
from app.extensions import db
# Import Models (Only needed if creating simple helper lists like available_clients directly)
from app.database.models.client import ClientModel
# Import Services and custom exceptions
from app.services.campaign_service import CampaignService
from app.services.client_service import ClientService # Keep for listing available clients helper
from app.utils.exceptions import (
    ResourceNotFound, ConflictError, ServiceError,
    ValidationError as CustomValidationError, AuthorizationError
)
# Import Utilities and Decorators
from app.utils.decorators import seller_required
# Import Schemas
from app.api.schemas.campaign_schemas import (
    CampaignSchema, CreateCampaignSchema, UpdateCampaignSchema, CampaignListSchema,
    SetCampaignDidsSchema, CampaignClientSettingSchema, CampaignClientSettingInputSchema
)
from app.api.schemas.client_schemas import ClientSchema # For available clients list


# Create Blueprint
seller_campaigns_bp = Blueprint('seller_campaigns_api', __name__)

# --- Instantiate Schemas ---
# Output Schemas (for serialization)
campaign_schema = CampaignSchema()
campaign_list_schema = CampaignListSchema()
campaign_client_setting_schema = CampaignClientSettingSchema()

# Input Schemas (for deserialization/validation)
create_campaign_schema = CreateCampaignSchema()
update_campaign_schema = UpdateCampaignSchema()
set_dids_schema = SetCampaignDidsSchema()
campaign_client_setting_input_schema = CampaignClientSettingInputSchema()

# Schema for basic client info list (used in helper endpoint)
simple_client_schema = ClientSchema(
    many=True,
    only=("id", "client_identifier", "name", "department") # Only include essential fields
)
# --- End Schema Instantiation ---


# --- Campaign CRUD ---

@seller_campaigns_bp.route('', methods=['POST'])
@seller_required
def seller_create_campaign():
    """Seller: Create a new campaign."""
    json_data = request.get_json()
    if not json_data:
        abort(400, description="No input data provided.")

    try:
        # Validate and deserialize input
        data = create_campaign_schema.load(json_data)
    except ValidationError as err: # Marshmallow validation error
        current_app.logger.warning(f"Seller create campaign validation error for user {current_user.id}: {err.messages}")
        return jsonify({"errors": err.messages}), 400

    try:
        # Call service - adds campaign to session, raises custom exceptions
        new_campaign = CampaignService.create_campaign(
            user_id=current_user.id,
            **data
        )

        # --- Commit Transaction ---
        db.session.commit()
        current_app.logger.info(f"Seller {current_user.id} created campaign {new_campaign.id} ('{new_campaign.name}')")
        # Serialize the created object using the detailed output schema
        return jsonify(campaign_schema.dump(new_campaign)), 201 # Created

    except (ConflictError, CustomValidationError) as e: # Catch specific service errors
        db.session.rollback()
        current_app.logger.warning(f"Seller create campaign failed for user {current_user.id}: {e}")
        status_code = 409 if isinstance(e, ConflictError) else 400
        abort(status_code, description=str(e))
    except ServiceError as e: # Catch broader service/DB errors
        db.session.rollback()
        current_app.logger.error(f"Seller create campaign service error for user {current_user.id}: {e}", exc_info=True)
        abort(500, description=str(e))
    except Exception as e: # Catch unexpected errors
        db.session.rollback()
        current_app.logger.exception(f"Unexpected error creating campaign for user {current_user.id}: {e}")
        abort(500, description="Could not create campaign due to an internal server error.")


@seller_campaigns_bp.route('', methods=['GET'])
@seller_required
def seller_get_campaigns():
    """Seller: Get list of own campaigns (paginated)."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status', None, type=str)

    # Basic validation for status param
    if status is not None and status not in ['active', 'inactive', 'paused']:
         abort(400, description="Invalid status filter. Allowed: active, inactive, paused.")

    try:
        # Service call is read-only
        paginated_campaigns = CampaignService.get_campaigns_for_user(
            user_id=current_user.id,
            page=page,
            per_page=per_page,
            status=status
        )
        # Prepare data structure matching the CampaignListSchema
        result_data = {
            'items': paginated_campaigns.items,
            'page': paginated_campaigns.page,
            'per_page': paginated_campaigns.per_page, # Source attribute name
            'total': paginated_campaigns.total,
            'pages': paginated_campaigns.pages
        }
        # Schema maps 'per_page' attribute to 'perPage'
        return jsonify(campaign_list_schema.dump(result_data)), 200
    except Exception as e: # Catch unexpected errors during fetch/serialization
        current_app.logger.exception(f"Unexpected error fetching campaigns for user {current_user.id}: {e}")
        abort(500, description="Could not fetch campaigns.")


@seller_campaigns_bp.route('/<int:campaign_id>', methods=['GET'])
@seller_required
def seller_get_campaign(campaign_id):
    """Seller: Get details of a specific owned campaign."""
    try:
        # Service handles ownership check and can load related data
        # Pass load_links=True to get DIDs and Client Settings
        campaign = CampaignService.get_campaign_by_id(
            campaign_id=campaign_id,
            user_id=current_user.id,
            load_links=True # Request eager loading
        )

        if not campaign:
            # Service returns None if not found or not owned
            abort(404, description=f"Campaign with ID {campaign_id} not found or not owned by user.")

        # CampaignSchema handles serialization, including nested data
        return jsonify(campaign_schema.dump(campaign)), 200
    except (ResourceNotFound, AuthorizationError) as e:
         # These shouldn't be raised if the initial check handles None, but catch defensively
         db.session.rollback() # Good practice on error
         log_func = current_app.logger.warning if isinstance(e, AuthorizationError) else current_app.logger.info
         log_func(f"Get campaign {campaign_id} failed for user {current_user.id}: {e}")
         status_code = 403 if isinstance(e, AuthorizationError) else 404
         abort(status_code, description=str(e))
    except Exception as e: # Catch only *other* unexpected errors
        # DO NOT catch HTTPException here, let abort(404) propagate
        if isinstance(e, HTTPException):
             raise e
        db.session.rollback()
        current_app.logger.exception(f"Unexpected error fetching campaign {campaign_id} for user {current_user.id}: {e}")
        abort(500, description="Could not fetch campaign details.")


@seller_campaigns_bp.route('/<int:campaign_id>', methods=['PUT'])
@seller_required
def seller_update_campaign(campaign_id):
    """Seller: Update an owned campaign."""
    json_data = request.get_json()
    if not json_data:
        abort(400, description="No input data provided.")

    try:
        # Validate using the update schema (allows partial data)
        data_to_update = update_campaign_schema.load(json_data)
    except ValidationError as err: # Marshmallow validation error
         current_app.logger.warning(f"Seller update campaign validation error for ID {campaign_id}, user {current_user.id}: {err.messages}")
         return jsonify({"errors": err.messages}), 400

    if not data_to_update:
         abort(400, description="No valid fields provided for update.")

    try:
        # Call service - updates object in session, raises custom exceptions
        updated_campaign = CampaignService.update_campaign(
            campaign_id=campaign_id,
            user_id=current_user.id,
            **data_to_update
        )

        # --- Commit Transaction ---
        db.session.commit()
        current_app.logger.info(f"Seller {current_user.id} updated campaign {campaign_id}")

        # Fetch again after commit to ensure latest state including potential nested changes
        # (though service returns the updated object, fetching ensures consistency)
        campaign_for_response = CampaignService.get_campaign_by_id(
            updated_campaign.id,
            current_user.id,
            load_links=True # Load links for the response
        )
        if not campaign_for_response: # Defensive check
             current_app.logger.error(f"Failed to re-fetch updated campaign {updated_campaign.id} after commit.")
             abort(500, description="Updated campaign data could not be retrieved.")

        return jsonify(campaign_schema.dump(campaign_for_response)), 200

    except ResourceNotFound as e:
        db.session.rollback()
        current_app.logger.warning(f"Seller update campaign failed: {e}")
        abort(404, description=str(e))
    except AuthorizationError as e:
        db.session.rollback()
        current_app.logger.warning(f"Seller update campaign authorization failed for campaign {campaign_id}, user {current_user.id}: {e}")
        abort(403, description=str(e))
    except (ConflictError, CustomValidationError) as e:
        db.session.rollback()
        current_app.logger.warning(f"Seller update campaign failed for campaign {campaign_id}, user {current_user.id}: {e}")
        status_code = 409 if isinstance(e, ConflictError) else 400
        abort(status_code, description=str(e))
    except ServiceError as e:
        db.session.rollback()
        current_app.logger.error(f"Seller update campaign service error for campaign {campaign_id}, user {current_user.id}: {e}", exc_info=True)
        abort(500, description=str(e))
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception(f"Unexpected error updating campaign {campaign_id} for user {current_user.id}: {e}")
        abort(500, description="Could not update campaign due to an internal error.")


@seller_campaigns_bp.route('/<int:campaign_id>', methods=['DELETE'])
@seller_required
def seller_delete_campaign(campaign_id):
    """Seller: Delete an owned campaign."""
    try:
        # Call service - marks campaign for deletion, raises custom exceptions
        CampaignService.delete_campaign(campaign_id=campaign_id, user_id=current_user.id)

        # --- Commit Transaction ---
        db.session.commit()
        current_app.logger.info(f"Seller {current_user.id} deleted campaign {campaign_id}")
        return '', 204 # No Content signifies successful deletion

    except ResourceNotFound as e:
        db.session.rollback()
        current_app.logger.warning(f"Seller delete campaign failed: {e}")
        abort(404, description=str(e))
    except AuthorizationError as e:
        db.session.rollback()
        current_app.logger.warning(f"Seller delete campaign authorization failed for campaign {campaign_id}, user {current_user.id}: {e}")
        abort(403, description=str(e))
    except ServiceError as e:
        db.session.rollback()
        current_app.logger.error(f"Seller delete campaign service error for campaign {campaign_id}, user {current_user.id}: {e}", exc_info=True)
        abort(500, description=str(e))
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception(f"Unexpected error deleting campaign {campaign_id} for user {current_user.id}: {e}")
        abort(500, description="Could not delete campaign due to an internal error.")


# --- Campaign DID Links ---

@seller_campaigns_bp.route('/<int:campaign_id>/dids', methods=['PUT'])
@seller_required
def seller_set_campaign_dids(campaign_id):
    """Seller: Set the DIDs associated with an owned campaign."""
    json_data = request.get_json()
    if not json_data:
        abort(400, description="No input data provided.")

    try:
        # Validate input using the specific schema
        data = set_dids_schema.load(json_data)
    except ValidationError as err: # Marshmallow validation error
        current_app.logger.warning(f"Seller set campaign DIDs validation error for campaign {campaign_id}, user {current_user.id}: {err.messages}")
        return jsonify({"errors": err.messages}), 400

    try:
        # Service handles ownership checks (campaign and DIDs) and updates in session
        CampaignService.set_campaign_dids(
            campaign_id=campaign_id,
            user_id=current_user.id,
            did_ids=data['did_ids'] # Use the key defined in the schema ('didIds')
        )

        # --- Commit Transaction ---
        db.session.commit()
        current_app.logger.info(f"Seller {current_user.id} updated DIDs for campaign {campaign_id}")
        return jsonify({"message": "Campaign DIDs updated successfully."}), 200

    except ResourceNotFound as e: # Campaign not found
        db.session.rollback()
        current_app.logger.warning(f"Seller set DIDs failed: {e}")
        abort(404, description=str(e))
    except AuthorizationError as e: # Campaign or DID ownership error
        db.session.rollback()
        current_app.logger.warning(f"Seller set DIDs authorization failed for campaign {campaign_id}, user {current_user.id}: {e}")
        # Distinguish between campaign ownership (404) and DID ownership (403) based on message if needed
        if "not authorized for campaign" in str(e).lower():
            abort(404, description=f"Campaign {campaign_id} not found or not owned by user.")
        else: # Assume DID ownership error
            abort(403, description=str(e))
    except ServiceError as e: # Catch broader service/DB errors
        db.session.rollback()
        current_app.logger.error(f"Seller set DIDs service error for campaign {campaign_id}, user {current_user.id}: {e}", exc_info=True)
        abort(500, description=str(e))
    except Exception as e: # Catch unexpected errors
        db.session.rollback()
        current_app.logger.exception(f"Unexpected error setting DIDs for campaign {campaign_id}, user {current_user.id}: {e}")
        abort(500, description="Could not update campaign DIDs due to an internal error.")


# --- Campaign Client Links / Settings ---

@seller_campaigns_bp.route('/<int:campaign_id>/clients', methods=['POST'])
@seller_required
def seller_add_campaign_client(campaign_id):
    """Seller: Link a client to an owned campaign with settings."""
    json_data = request.get_json()
    if not json_data:
        abort(400, description="No input data provided.")

    try:
        # Validate using the input schema for settings
        setting_data = campaign_client_setting_input_schema.load(json_data)
    except ValidationError as err: # Marshmallow validation error
        current_app.logger.warning(f"Seller add campaign client validation error for campaign {campaign_id}, user {current_user.id}: {err.messages}")
        return jsonify({"errors": err.messages}), 400

    try:
        # Service handles campaign ownership check, client existence check, and creation in session
        new_setting = CampaignService.add_client_to_campaign(
            campaign_id=campaign_id,
            user_id=current_user.id,
            client_id=setting_data['client_id'], # Use key from schema
            settings=setting_data # Pass the full validated dict
        )

        # --- Commit Transaction ---
        db.session.commit()
        current_app.logger.info(f"Seller {current_user.id} linked client {setting_data['client_id']} to campaign {campaign_id} (Setting ID: {new_setting.id})")
        # Return the created setting details using its specific schema
        return jsonify(campaign_client_setting_schema.dump(new_setting)), 201 # Created

    except ResourceNotFound as e: # Campaign or Client not found
        db.session.rollback()
        current_app.logger.warning(f"Seller add client link failed: {e}")
        abort(404, description=str(e))
    except AuthorizationError as e: # Campaign ownership error
        db.session.rollback()
        current_app.logger.warning(f"Seller add client link authorization failed for campaign {campaign_id}, user {current_user.id}: {e}")
        abort(403, description=str(e)) # Or 404 if treating as campaign not found for user
    except ConflictError as e: # Client already linked
        db.session.rollback()
        current_app.logger.warning(f"Seller add client link conflict for campaign {campaign_id}, user {current_user.id}: {e}")
        abort(409, description=str(e))
    except (CustomValidationError, ServiceError) as e: # Catch validation or DB errors
         db.session.rollback()
         current_app.logger.error(f"Seller add client link service error for campaign {campaign_id}, user {current_user.id}: {e}", exc_info=True)
         status_code = 400 if isinstance(e, CustomValidationError) else 500
         abort(status_code, description=str(e))
    except Exception as e: # Catch unexpected errors
        db.session.rollback()
        current_app.logger.exception(f"Unexpected error linking client for campaign {campaign_id}, user {current_user.id}: {e}")
        abort(500, description="Could not link client to campaign due to an internal error.")


@seller_campaigns_bp.route('/<int:campaign_id>/clients/<int:setting_id>', methods=['PUT'])
@seller_required
def seller_update_campaign_client_setting(campaign_id, setting_id):
    """Seller: Update settings for a specific campaign-client link."""
    json_data = request.get_json()
    if not json_data:
        abort(400, description="No input data provided.")

    try:
        # Load data allowing partial input for PUT requests
        # Schema implicitly makes fields optional with partial=True
        updates = CampaignClientSettingInputSchema(partial=True).load(json_data)
    except ValidationError as err: # Marshmallow validation error
        current_app.logger.warning(f"Seller update campaign client setting validation error for setting {setting_id}, user {current_user.id}: {err.messages}")
        return jsonify({"errors": err.messages}), 400

    # Business rule: client_id cannot be changed via this endpoint
    if 'client_id' in updates: # Check against the actual attribute name if schema maps it differently
        abort(400, description="Cannot change client_id via this endpoint. Remove and re-add the link.")
    if not updates:
         abort(400, description="No valid fields provided for update.")

    # REMOVED direct query pre-check - rely on service layer for validation/auth

    try:
        # Call the service - handles checks and updates object in session
        # Service raises ResourceNotFound or AuthorizationError if checks fail
        updated_setting = CampaignService.update_campaign_client_setting(
            setting_id=setting_id,
            user_id=current_user.id,
            campaign_id=campaign_id, # <<< Pass campaign_id from URL
            updates=updates
        )
        # Check if setting belongs to the correct campaign (extra safety check, service should ensure)
        # if updated_setting.campaign_id != campaign_id:
        #     db.session.rollback() # Rollback inconsistent state
        #     current_app.logger.error(f"Consistency Error: Setting {setting_id} updated but belongs to campaign {updated_setting.campaign_id}, not {campaign_id}.")
        #     abort(500, description="Internal data consistency error.")

        # --- Commit Transaction ---
        db.session.commit()
        current_app.logger.info(f"Seller {current_user.id} updated campaign client setting {setting_id}")
        return jsonify(campaign_client_setting_schema.dump(updated_setting)), 200

    except ResourceNotFound as e:
        db.session.rollback()
        current_app.logger.warning(f"Seller update setting failed: {e}")
        abort(404, description=str(e)) # Setting not found
    except AuthorizationError as e:
        db.session.rollback()
        current_app.logger.warning(f"Seller update setting authorization failed for setting {setting_id}, user {current_user.id}: {e}")
        abort(403, description=str(e)) # User doesn't own parent campaign
    except (CustomValidationError, ServiceError) as e: # Catch validation or DB errors
         db.session.rollback()
         current_app.logger.error(f"Seller update setting service error for setting {setting_id}, user {current_user.id}: {e}", exc_info=True)
         status_code = 400 if isinstance(e, CustomValidationError) else 500
         abort(status_code, description=str(e))
    except Exception as e: # Catch unexpected errors
        db.session.rollback()
        current_app.logger.exception(f"Unexpected error updating setting {setting_id} for user {current_user.id}: {e}")
        abort(500, description="Could not update campaign client setting.")


@seller_campaigns_bp.route('/<int:campaign_id>/clients/<int:setting_id>', methods=['DELETE'])
@seller_required
def seller_remove_campaign_client(campaign_id, setting_id):
    """Seller: Unlink a client from an owned campaign."""
    # REMOVED direct query pre-check - rely on service layer

    try:
        # Call service - handles ownership checks and marks for deletion
        # Service raises ResourceNotFound or AuthorizationError if checks fail
        success = CampaignService.remove_client_from_campaign(
            setting_id=setting_id,
            user_id=current_user.id,
            campaign_id=campaign_id
        )
        # Optional: Add check if setting's campaign_id matches route's campaign_id?
        # Usually handled by service implicitly via ownership check.

        # --- Commit Transaction ---
        if success: # Should always be true if no exception raised
            db.session.commit()
            current_app.logger.info(f"Seller {current_user.id} removed campaign client setting {setting_id}")
            return '', 204 # No Content
        else:
            # This path should ideally not be reached if service raises exceptions
            db.session.rollback()
            current_app.logger.error(f"Service remove_client_from_campaign returned False unexpectedly for setting {setting_id}")
            abort(500, description="Client link removal failed for an unknown reason.")

    except ResourceNotFound as e:
        db.session.rollback()
        current_app.logger.warning(f"Seller remove setting failed: {e}")
        abort(404, description=str(e)) # Setting not found
    except AuthorizationError as e:
        db.session.rollback()
        current_app.logger.warning(f"Seller remove setting authorization failed for setting {setting_id}, user {current_user.id}: {e}")
        abort(403, description=str(e)) # User doesn't own parent campaign
    except ServiceError as e: # Catch DB errors during flush
         db.session.rollback()
         current_app.logger.error(f"Seller remove setting service error for setting {setting_id}, user {current_user.id}: {e}", exc_info=True)
         abort(500, description=str(e))
    except Exception as e: # Catch unexpected errors
        db.session.rollback()
        current_app.logger.exception(f"Unexpected error removing setting {setting_id} for user {current_user.id}: {e}")
        abort(500, description="Could not remove client link.")


# --- Helper Endpoint: List available clients for linking ---
@seller_campaigns_bp.route('/available_clients', methods=['GET'])
@seller_required
def seller_get_available_clients():
    """Seller: Get a list of active clients they can link campaigns to."""
    try:
        # Use ClientService for consistency (even if it's just a simple query)
        # Assuming default pagination is acceptable or ClientService adjusts
        paginated_clients = ClientService.get_all_clients(page=1, per_page=500, status='active') # Fetch many active clients

        # Use the specific simple schema for this list
        return jsonify(simple_client_schema.dump(paginated_clients.items)), 200
    except Exception as e: # Catch unexpected errors
        current_app.logger.exception(f"Unexpected error fetching available clients for user {current_user.id}: {e}")
        abort(500, description="Could not fetch available clients.")