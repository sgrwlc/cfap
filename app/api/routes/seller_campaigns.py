# -*- coding: utf-8 -*-
"""
Seller API Routes for Campaign and Campaign-Client Settings Management.
"""
from flask import Blueprint, request, jsonify, current_app, abort
from flask_login import current_user
from marshmallow import ValidationError
from sqlalchemy.orm import joinedload # Needed for getting details

# --- Required Model Imports ---
from app.database.models.campaign import CampaignModel, CampaignDidModel, CampaignClientSettingsModel
from app.database.models.client import ClientModel # For listing available clients
# --- End Required Model Imports ---

from app.services.campaign_service import CampaignService
from app.services.client_service import ClientService # Needed to list available clients
from app.utils.decorators import seller_required
from app.api.schemas.campaign_schemas import (
    CampaignSchema, CreateCampaignSchema, UpdateCampaignSchema, CampaignListSchema,
    SetCampaignDidsSchema, CampaignClientSettingSchema, CampaignClientSettingInputSchema
)
from app.api.schemas.client_schemas import ClientSchema # For listing available clients
# Create Blueprint
seller_campaigns_bp = Blueprint('seller_campaigns_api', __name__)

# Instantiate schemas
campaign_schema = CampaignSchema()
campaign_list_schema = CampaignListSchema()
create_campaign_schema = CreateCampaignSchema()
update_campaign_schema = UpdateCampaignSchema()
set_dids_schema = SetCampaignDidsSchema()
campaign_client_setting_schema = CampaignClientSettingSchema()
campaign_client_setting_input_schema = CampaignClientSettingInputSchema()
# Schema for basic client info list
simple_client_schema = ClientSchema(many=True, only=("id", "clientIdentifier", "name", "department"))


# --- Campaign CRUD ---

@seller_campaigns_bp.route('', methods=['POST'])
@seller_required
def seller_create_campaign():
    """Seller: Create a new campaign."""
    json_data = request.get_json()
    if not json_data:
        abort(400, description="No input data provided.")

    try:
        data = create_campaign_schema.load(json_data)
    except ValidationError as err:
        current_app.logger.warning(f"Seller create campaign validation error for user {current_user.id}: {err.messages}")
        return jsonify(err.messages), 400

    try:
        new_campaign = CampaignService.create_campaign(
            user_id=current_user.id,
            **data
        )
        # Use the detailed schema for the response
        return jsonify(campaign_schema.dump(new_campaign)), 201
    except ValueError as e:
        current_app.logger.error(f"Seller create campaign error for user {current_user.id}: {e}")
        status_code = 409 if 'already exists' in str(e) else 400
        abort(status_code, description=str(e))
    except Exception as e:
        current_app.logger.exception(f"Unexpected error creating campaign for user {current_user.id}: {e}")
        abort(500, description="Could not create campaign.")


@seller_campaigns_bp.route('', methods=['GET'])
@seller_required
def seller_get_campaigns():
    """Seller: Get list of own campaigns (paginated)."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status', None, type=str)

    try:
        paginated_campaigns = CampaignService.get_campaigns_for_user(
            user_id=current_user.id,
            page=page,
            per_page=per_page,
            status=status
        )
        # Use the list schema (less detail per item)
        result = campaign_list_schema.dump({
            'items': paginated_campaigns.items,
            'page': paginated_campaigns.page,
            'perPage': paginated_campaigns.per_page,
            'total': paginated_campaigns.total,
            'pages': paginated_campaigns.pages
        })
        return jsonify(result), 200
    except Exception as e:
        current_app.logger.exception(f"Unexpected error fetching campaigns for user {current_user.id}: {e}")
        abort(500, description="Could not fetch campaigns.")


@seller_campaigns_bp.route('/<int:campaign_id>', methods=['GET'])
@seller_required
def seller_get_campaign(campaign_id):
    """Seller: Get details of a specific owned campaign."""
    # Eager load details needed by the CampaignSchema
    campaign = CampaignModel.query.options(
        joinedload(CampaignModel.did_associations).joinedload(CampaignDidModel.did),
        joinedload(CampaignModel.client_settings).joinedload(CampaignClientSettingsModel.client)
    ).filter(
        CampaignModel.id == campaign_id,
        CampaignModel.user_id == current_user.id
    ).one_or_none()

    if not campaign:
        abort(404, description=f"Campaign with ID {campaign_id} not found or not owned by user.")

    # Manually populate 'dids' if using association_proxy isn't desired/set up
    # This example assumes the relationships load the data correctly for Marshmallow
    return jsonify(campaign_schema.dump(campaign)), 200


@seller_campaigns_bp.route('/<int:campaign_id>', methods=['PUT'])
@seller_required
def seller_update_campaign(campaign_id):
    """Seller: Update an owned campaign."""
    json_data = request.get_json()
    if not json_data:
        abort(400, description="No input data provided.")

    try:
        data_to_update = update_campaign_schema.load(json_data)
    except ValidationError as err:
         current_app.logger.warning(f"Seller update campaign validation error for ID {campaign_id}, user {current_user.id}: {err.messages}")
         return jsonify(err.messages), 400

    if not data_to_update:
         abort(400, description="No valid fields provided for update.")

    try:
        updated_campaign = CampaignService.update_campaign(
            campaign_id=campaign_id,
            user_id=current_user.id,
            **data_to_update
        )
        # Return full details after update
        campaign = CampaignService.get_campaign_by_id(updated_campaign.id, current_user.id)
        return jsonify(campaign_schema.dump(campaign)), 200
    except ValueError as e:
        current_app.logger.error(f"Seller update campaign error for ID {campaign_id}, user {current_user.id}: {e}")
        status_code = 404 if 'not found' in str(e) else (403 if 'authorized' in str(e) else (409 if 'already exists' in str(e) else 400))
        abort(status_code, description=str(e))
    except Exception as e:
        current_app.logger.exception(f"Unexpected error updating campaign {campaign_id} for user {current_user.id}: {e}")
        abort(500, description="Could not update campaign.")


@seller_campaigns_bp.route('/<int:campaign_id>', methods=['DELETE'])
@seller_required
def seller_delete_campaign(campaign_id):
    """Seller: Delete an owned campaign."""
    try:
        success = CampaignService.delete_campaign(campaign_id=campaign_id, user_id=current_user.id)
        if success:
            return '', 204 # No Content
        else:
            abort(500, description="Campaign deletion failed for an unknown reason.")
    except ValueError as e:
        current_app.logger.error(f"Seller delete campaign error for ID {campaign_id}, user {current_user.id}: {e}")
        status_code = 404 if 'not found' in str(e) else (403 if 'authorized' in str(e) else 500)
        abort(status_code, description=str(e))
    except Exception as e:
        current_app.logger.exception(f"Unexpected error deleting campaign {campaign_id} for user {current_user.id}: {e}")
        abort(500, description="Could not delete campaign.")


# --- Campaign DID Links ---

@seller_campaigns_bp.route('/<int:campaign_id>/dids', methods=['PUT'])
@seller_required
def seller_set_campaign_dids(campaign_id):
    """Seller: Set the DIDs associated with an owned campaign."""
    json_data = request.get_json()
    if not json_data:
        abort(400, description="No input data provided.")

    try:
        # Validate that 'did_ids' key exists and is a list of integers
        data = set_dids_schema.load(json_data)
    except ValidationError as err:
        current_app.logger.warning(f"Seller set campaign DIDs validation error for campaign {campaign_id}, user {current_user.id}: {err.messages}")
        return jsonify(err.messages), 400

    try:
        success = CampaignService.set_campaign_dids(
            campaign_id=campaign_id,
            user_id=current_user.id,
            did_ids=data['did_ids'] # Use validated list
        )
        if success:
            return jsonify({"message": "Campaign DIDs updated successfully."}), 200
        else:
             abort(500, description="Failed to update campaign DIDs for an unknown reason.")
    except ValueError as e:
        current_app.logger.error(f"Seller set campaign DIDs error for campaign {campaign_id}, user {current_user.id}: {e}")
        status_code = 404 if 'not found' in str(e) else (403 if 'authorized' in str(e) or 'owned' in str(e) else 400)
        abort(status_code, description=str(e))
    except Exception as e:
        current_app.logger.exception(f"Unexpected error setting DIDs for campaign {campaign_id}, user {current_user.id}: {e}")
        abort(500, description="Could not update campaign DIDs.")


# --- Campaign Client Links / Settings ---

@seller_campaigns_bp.route('/<int:campaign_id>/clients', methods=['POST'])
@seller_required
def seller_add_campaign_client(campaign_id):
    """Seller: Link a client to an owned campaign with settings."""
    json_data = request.get_json()
    if not json_data:
        abort(400, description="No input data provided.")

    try:
        # Use the input schema for validation
        setting_data = campaign_client_setting_input_schema.load(json_data)
    except ValidationError as err:
        current_app.logger.warning(f"Seller add campaign client validation error for campaign {campaign_id}, user {current_user.id}: {err.messages}")
        return jsonify(err.messages), 400

    try:
        new_setting = CampaignService.add_client_to_campaign(
            campaign_id=campaign_id,
            user_id=current_user.id,
            client_id=setting_data['client_id'],
            settings=setting_data # Pass the validated dict to service
        )
        # Return the created setting details
        return jsonify(campaign_client_setting_schema.dump(new_setting)), 201
    except ValueError as e:
        current_app.logger.error(f"Seller add campaign client error for campaign {campaign_id}, user {current_user.id}: {e}")
        status_code = 404 if 'not found' in str(e) else (403 if 'authorized' in str(e) else (409 if 'already linked' in str(e) else 400))
        abort(status_code, description=str(e))
    except Exception as e:
        current_app.logger.exception(f"Unexpected error linking client for campaign {campaign_id}, user {current_user.id}: {e}")
        abort(500, description="Could not link client to campaign.")


@seller_campaigns_bp.route('/<int:campaign_id>/clients/<int:setting_id>', methods=['PUT'])
@seller_required
def seller_update_campaign_client_setting(campaign_id, setting_id):
    """Seller: Update settings for a specific campaign-client link."""
    # Verify campaign_id matches the setting's campaign? Optional, service checks ownership anyway.
    json_data = request.get_json()
    if not json_data:
        abort(400, description="No input data provided.")

    try:
        # Use input schema, allows partial updates
        updates = campaign_client_setting_input_schema.load(json_data)
    except ValidationError as err:
        current_app.logger.warning(f"Seller update campaign client setting validation error for setting {setting_id}, user {current_user.id}: {err.messages}")
        return jsonify(err.messages), 400

    # Cannot change client_id via PUT on the setting ID
    if 'client_id' in updates:
        abort(400, description="Cannot change client_id via this endpoint. Remove and re-add the link.")
    if not updates:
         abort(400, description="No valid fields provided for update.")

    try:
        updated_setting = CampaignService.update_campaign_client_setting(
            setting_id=setting_id,
            user_id=current_user.id,
            updates=updates
        )
        # Optional: Add check if updated_setting.campaign_id matches path campaign_id
        if updated_setting.campaign_id != campaign_id:
             current_app.logger.error(f"Mismatch: Setting {setting_id} belongs to campaign {updated_setting.campaign_id}, not path campaign {campaign_id}.")
             abort(404, description="Setting not found for the specified campaign.") # Treat as not found in this context

        return jsonify(campaign_client_setting_schema.dump(updated_setting)), 200
    except ValueError as e:
        current_app.logger.error(f"Seller update campaign client setting error for setting {setting_id}, user {current_user.id}: {e}")
        status_code = 404 if 'not found' in str(e) else (403 if 'authorized' in str(e) else 400)
        abort(status_code, description=str(e))
    except Exception as e:
        current_app.logger.exception(f"Unexpected error updating setting {setting_id} for user {current_user.id}: {e}")
        abort(500, description="Could not update campaign client setting.")


@seller_campaigns_bp.route('/<int:campaign_id>/clients/<int:setting_id>', methods=['DELETE'])
@seller_required
def seller_remove_campaign_client(campaign_id, setting_id):
    """Seller: Unlink a client from an owned campaign."""
    # Optional: Verify the setting actually belongs to the campaign_id in the path first
    setting = CampaignClientSettingsModel.query.filter_by(id=setting_id, campaign_id=campaign_id).first()
    if not setting:
         abort(404, description="Setting not found for the specified campaign.")

    try:
        success = CampaignService.remove_client_from_campaign(
            setting_id=setting_id,
            user_id=current_user.id # Service verifies ownership via campaign
        )
        if success:
            return '', 204 # No Content
        else:
            abort(500, description="Client link removal failed for an unknown reason.")
    except ValueError as e:
        current_app.logger.error(f"Seller remove campaign client error for setting {setting_id}, user {current_user.id}: {e}")
        status_code = 404 if 'not found' in str(e) else (403 if 'authorized' in str(e) else 500)
        abort(status_code, description=str(e))
    except Exception as e:
        current_app.logger.exception(f"Unexpected error removing setting {setting_id} for user {current_user.id}: {e}")
        abort(500, description="Could not remove client link.")


# Helper Endpoint: List available clients for linking
@seller_campaigns_bp.route('/available_clients', methods=['GET'])
@seller_required
def seller_get_available_clients():
    """Seller: Get a list of active clients they can link campaigns to."""
    # In this model, sellers can link to *any* active client managed by admins
    try:
        # Get non-paginated list of active clients for simplicity, could paginate later
        active_clients = ClientModel.query.filter_by(status='active').order_by(ClientModel.name).all()
        return jsonify(simple_client_schema.dump(active_clients)), 200
    except Exception as e:
        current_app.logger.exception(f"Unexpected error fetching available clients for user {current_user.id}: {e}")
        abort(500, description="Could not fetch available clients.")