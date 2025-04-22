# -*- coding: utf-8 -*-
"""
Seller API Routes for Campaign and Campaign-Client Settings Management.
"""
from flask import Blueprint, request, jsonify, current_app, abort
from flask_login import current_user
from marshmallow import ValidationError
from sqlalchemy.orm import joinedload # Keep for specific scenarios if needed, but often schema handles it

# --- Required Model Imports ---
# Import all models used directly in this file for queries or type checking
from app.database.models.campaign import CampaignModel, CampaignDidModel, CampaignClientSettingsModel
from app.database.models.client import ClientModel # For listing available clients
# --- End Required Model Imports ---

# Import Services
from app.services.campaign_service import CampaignService
from app.services.client_service import ClientService # Needed to list available clients

# Import Utilities and Decorators
from app.utils.decorators import seller_required

# Import Schemas
from app.api.schemas.campaign_schemas import (
    CampaignSchema, CreateCampaignSchema, UpdateCampaignSchema, CampaignListSchema,
    SetCampaignDidsSchema, CampaignClientSettingSchema, CampaignClientSettingInputSchema
)
# Import ClientSchema for listing available clients
# Note: Ensure ClientSchema definition excludes sensitive PJSIP details if not needed here
from app.api.schemas.client_schemas import ClientSchema


# Create Blueprint
seller_campaigns_bp = Blueprint('seller_campaigns_api', __name__)

# Instantiate schemas
# Output Schemas (for serialization)
campaign_schema = CampaignSchema() # For single detailed campaign view
campaign_list_schema = CampaignListSchema() # For paginated list view
campaign_client_setting_schema = CampaignClientSettingSchema() # For single setting view

# Input Schemas (for deserialization/validation)
create_campaign_schema = CreateCampaignSchema()
update_campaign_schema = UpdateCampaignSchema()
set_dids_schema = SetCampaignDidsSchema()
campaign_client_setting_input_schema = CampaignClientSettingInputSchema()

# Schema for basic client info list (used in helper endpoint)
# Define explicitly which fields are needed to avoid loading/exposing too much
simple_client_schema = ClientSchema(
    many=True,
    only=("id", "client_identifier", "name", "department") # Only include essential fields
)


# --- Campaign CRUD ---

@seller_campaigns_bp.route('', methods=['POST'])
@seller_required
def seller_create_campaign():
    """Seller: Create a new campaign."""
    json_data = request.get_json()
    if not json_data:
        abort(400, description="No input data provided.")

    try:
        # Validate and deserialize input using the specific creation schema
        data = create_campaign_schema.load(json_data)
    except ValidationError as err:
        current_app.logger.warning(f"Seller create campaign validation error for user {current_user.id}: {err.messages}")
        return jsonify({"errors": err.messages}), 400 # Return validation errors

    try:
        # Call the service with validated data
        new_campaign = CampaignService.create_campaign(
            user_id=current_user.id,
            **data
        )
        # Serialize the created object using the detailed output schema
        return jsonify(campaign_schema.dump(new_campaign)), 201 # Created
    except ValueError as e: # Catch specific service errors (like duplicates)
        current_app.logger.error(f"Seller create campaign service error for user {current_user.id}: {e}")
        status_code = 409 if 'already exists' in str(e) else 400
        abort(status_code, description=str(e))
    except Exception as e: # Catch unexpected errors
        current_app.logger.exception(f"Unexpected error creating campaign for user {current_user.id}: {e}")
        abort(500, description="Could not create campaign due to an internal error.")


@seller_campaigns_bp.route('', methods=['GET'])
@seller_required
def seller_get_campaigns():
    """Seller: Get list of own campaigns (paginated)."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status', None, type=str)

    try:
        # Call service to get paginated campaign data
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
            # Use the attribute name 'per_page' here, the schema maps it to 'perPage'
            'per_page': paginated_campaigns.per_page,
            'total': paginated_campaigns.total,
            'pages': paginated_campaigns.pages
        }
        # Serialize the paginated response using the list schema
        return jsonify(campaign_list_schema.dump(result_data)), 200
    except Exception as e: # Catch unexpected errors during fetch/serialization
        current_app.logger.exception(f"Unexpected error fetching campaigns for user {current_user.id}: {e}")
        abort(500, description="Could not fetch campaigns due to an internal error.")


@seller_campaigns_bp.route('/<int:campaign_id>', methods=['GET'])
@seller_required
def seller_get_campaign(campaign_id):
    """Seller: Get details of a specific owned campaign."""
    # Fetch the campaign, checking ownership via the service layer is cleaner
    campaign = CampaignService.get_campaign_by_id(campaign_id=campaign_id, user_id=current_user.id)

    if not campaign:
        abort(404, description=f"Campaign with ID {campaign_id} not found or not owned by user.")

    # Let the detailed CampaignSchema handle serialization, including nested DIDs and Client Settings
    # Marshmallow will trigger lazy-loading of relationships if not already loaded.
    return jsonify(campaign_schema.dump(campaign)), 200


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
    except ValidationError as err:
         current_app.logger.warning(f"Seller update campaign validation error for ID {campaign_id}, user {current_user.id}: {err.messages}")
         return jsonify({"errors": err.messages}), 400

    if not data_to_update: # Check if any valid fields were actually provided
         abort(400, description="No valid fields provided for update.")

    try:
        # Call service to perform the update
        updated_campaign = CampaignService.update_campaign(
            campaign_id=campaign_id,
            user_id=current_user.id,
            **data_to_update
        )
        # Fetch again or rely on service return to serialize the current state
        # Re-fetching ensures nested data is up-to-date if service doesn't return it all
        campaign_for_response = CampaignService.get_campaign_by_id(updated_campaign.id, current_user.id)
        if not campaign_for_response: # Defensive check
            abort(404, description="Updated campaign data could not be retrieved.")

        return jsonify(campaign_schema.dump(campaign_for_response)), 200 # Return full details
    except ValueError as e: # Catch specific service errors
        current_app.logger.error(f"Seller update campaign service error for ID {campaign_id}, user {current_user.id}: {e}")
        status_code = 404 if 'not found' in str(e) else (403 if 'authorized' in str(e) else (409 if 'already exists' in str(e) else 400))
        abort(status_code, description=str(e))
    except Exception as e: # Catch unexpected errors
        current_app.logger.exception(f"Unexpected error updating campaign {campaign_id} for user {current_user.id}: {e}")
        abort(500, description="Could not update campaign due to an internal error.")


@seller_campaigns_bp.route('/<int:campaign_id>', methods=['DELETE'])
@seller_required
def seller_delete_campaign(campaign_id):
    """Seller: Delete an owned campaign."""
    try:
        # Service handles ownership check and deletion (including cascades)
        success = CampaignService.delete_campaign(campaign_id=campaign_id, user_id=current_user.id)
        if success:
            return '', 204 # No Content signifies successful deletion
        else:
            # This case implies the service layer failed without raising an expected ValueError
            abort(500, description="Campaign deletion failed for an unknown reason.")
    except ValueError as e: # Catch specific service errors (not found, not authorized)
        current_app.logger.error(f"Seller delete campaign service error for ID {campaign_id}, user {current_user.id}: {e}")
        status_code = 404 if 'not found' in str(e) else (403 if 'authorized' in str(e) else 500)
        abort(status_code, description=str(e))
    except Exception as e: # Catch unexpected errors
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
    except ValidationError as err:
        current_app.logger.warning(f"Seller set campaign DIDs validation error for campaign {campaign_id}, user {current_user.id}: {err.messages}")
        return jsonify({"errors": err.messages}), 400

    try:
        # Service handles ownership checks (campaign and DIDs) and updates
        success = CampaignService.set_campaign_dids(
            campaign_id=campaign_id,
            user_id=current_user.id,
            did_ids=data['did_ids'] # Use the key defined in the schema ('didIds')
        )
        if success:
            return jsonify({"message": "Campaign DIDs updated successfully."}), 200
        else:
             abort(500, description="Failed to update campaign DIDs for an unknown reason.")
    
    except ValueError as e:
        error_message = str(e)
        current_app.logger.error(f"Seller set campaign DIDs service error for campaign {campaign_id}, user {current_user.id}: {error_message}")
        # --- Refined Status Code Mapping ---
        # Treat both "not found" and "not authorized" for the *campaign* as 404 for the user
        if 'not found or not owned by user' in error_message.lower() or \
           'not authorized for campaign' in error_message.lower(): # <-- ADDED CHECK
            status_code = 404 # Treat as Not Found for this user
        elif 'not owned by the user' in error_message.lower(): # Specific DID ownership error
            status_code = 403 # Forbidden to use that DID
        else:
            status_code = 400 # Other validation errors
        # --- End Refined Mapping ---
        abort(status_code, description=error_message)

    except Exception as e: # Catch unexpected errors
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
        # Ensure all required fields for creation are present (schema validates this)
    except ValidationError as err:
        current_app.logger.warning(f"Seller add campaign client validation error for campaign {campaign_id}, user {current_user.id}: {err.messages}")
        return jsonify({"errors": err.messages}), 400

    try:
        # Service handles campaign ownership check, client existence check, and creation
        new_setting = CampaignService.add_client_to_campaign(
            campaign_id=campaign_id,
            user_id=current_user.id,
            client_id=setting_data['client_id'], # Use key from schema
            settings=setting_data # Pass the full validated dict
        )
        # Return the created setting details using its specific schema
        return jsonify(campaign_client_setting_schema.dump(new_setting)), 201 # Created
    except ValueError as e: # Catch service errors (not found, already linked, etc.)
        current_app.logger.error(f"Seller add campaign client service error for campaign {campaign_id}, user {current_user.id}: {e}")
        status_code = 404 if 'not found' in str(e) else (403 if 'authorized' in str(e) else (409 if 'already linked' in str(e) else 400))
        abort(status_code, description=str(e))
    except Exception as e: # Catch unexpected errors
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
        # Load data allowing partial input for PUT requests using partial=True
        updates = CampaignClientSettingInputSchema(partial=True).load(json_data)
    except ValidationError as err:
        current_app.logger.warning(f"Seller update campaign client setting validation error for setting {setting_id}, user {current_user.id}: {err.messages}")
        return jsonify({"errors": err.messages}), 400

    # Business rule: client_id cannot be changed via this endpoint
    if 'clientId' in updates: # Check against the schema key
        abort(400, description="Cannot change client_id via this endpoint. Remove and re-add the link.")
    if not updates: # Ensure some valid update data was provided
         abort(400, description="No valid fields provided for update.")

    # Perform pre-check: Does the setting exist and belong to the specified campaign and user?
    # This prevents calling the service unnecessarily for invalid URL combinations.
    setting = CampaignClientSettingsModel.query.options(
        joinedload(CampaignClientSettingsModel.campaign) # Load campaign to check owner
    ).filter(
        CampaignClientSettingsModel.id == setting_id,
        CampaignClientSettingsModel.campaign_id == campaign_id # Check campaign match
    ).first() # Use first() instead of get() to filter by campaign_id too

    if not setting:
        abort(404, description=f"Setting {setting_id} not found for campaign {campaign_id}.")

    if setting.campaign.user_id != current_user.id:
        # This check might be redundant if the initial query used current_user.id,
        # but it's a good safeguard.
        current_app.logger.warning(f"User {current_user.id} attempted to update setting {setting_id} not owned by them.")
        abort(403, description="User is not authorized to update this campaign client setting.")

    try:
        # Call the service to perform the update
        updated_setting = CampaignService.update_campaign_client_setting(
            setting_id=setting_id,
            user_id=current_user.id, # Service should re-verify ownership
            updates=updates # Pass the validated partial data
        )
        return jsonify(campaign_client_setting_schema.dump(updated_setting)), 200
    except ValueError as e: # Catch specific errors from the service
        current_app.logger.error(f"Seller update campaign client setting service error for setting {setting_id}, user {current_user.id}: {e}")
        # Service might raise 404/403 if internal checks fail
        status_code = 404 if 'not found' in str(e) else (403 if 'authorized' in str(e) else 400)
        abort(status_code, description=str(e))
    except Exception as e: # Catch unexpected errors
        current_app.logger.exception(f"Unexpected error updating setting {setting_id} for user {current_user.id}: {e}")
        abort(500, description="Could not update campaign client setting due to an internal error.")


@seller_campaigns_bp.route('/<int:campaign_id>/clients/<int:setting_id>', methods=['DELETE'])
@seller_required
def seller_remove_campaign_client(campaign_id, setting_id):
    """Seller: Unlink a client from an owned campaign."""
    # Perform pre-check: Does the setting exist and belong to the specified campaign and user?
    setting = CampaignClientSettingsModel.query.join(CampaignModel).filter(
        CampaignClientSettingsModel.id == setting_id,
        CampaignClientSettingsModel.campaign_id == campaign_id,
        CampaignModel.user_id == current_user.id # Check ownership directly
    ).first()

    if not setting:
         abort(404, description=f"Setting {setting_id} not found for campaign {campaign_id} or not owned by user.")

    try:
        # Service handles deletion after initial check passes
        success = CampaignService.remove_client_from_campaign(
            setting_id=setting_id,
            user_id=current_user.id # Service re-verifies ownership
        )
        if success:
            return '', 204 # No Content
        else:
            abort(500, description="Client link removal failed for an unknown reason.")
    except ValueError as e: # Catch service errors (e.g., if somehow not found despite pre-check)
        current_app.logger.error(f"Seller remove campaign client service error for setting {setting_id}, user {current_user.id}: {e}")
        status_code = 404 if 'not found' in str(e) else (403 if 'authorized' in str(e) else 500)
        abort(status_code, description=str(e))
    except Exception as e: # Catch unexpected errors
        current_app.logger.exception(f"Unexpected error removing setting {setting_id} for user {current_user.id}: {e}")
        abort(500, description="Could not remove client link due to an internal error.")


# Helper Endpoint: List available clients for linking
@seller_campaigns_bp.route('/available_clients', methods=['GET'])
@seller_required
def seller_get_available_clients():
    """Seller: Get a list of active clients they can link campaigns to."""
    try:
        # Service layer could be used here too for consistency, but simple query is fine
        active_clients = ClientModel.query.filter_by(status='active').order_by(ClientModel.name).all()
        # Use the specific simple schema for this list
        return jsonify(simple_client_schema.dump(active_clients)), 200
    except Exception as e: # Catch unexpected errors
        current_app.logger.exception(f"Unexpected error fetching available clients for user {current_user.id}: {e}")
        abort(500, description="Could not fetch available clients due to an internal error.")