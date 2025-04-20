# -*- coding: utf-8 -*-
"""
Campaign Service
Handles business logic related to Campaigns, their linked DIDs,
and the settings for linked Clients (CampaignClientSettings).
"""
# --- MODIFICATION: Import select, delete, func, and_ ---
from sqlalchemy import select, delete, func, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
# --- MODIFICATION: Import Pagination ---
from flask_sqlalchemy.pagination import Pagination

from app.database.models.campaign import CampaignModel, CampaignDidModel, CampaignClientSettingsModel
from app.database.models.did import DidModel
from app.database.models.client import ClientModel # Needed for checking client existence
from app.extensions import db
# from app.utils.exceptions import NotFoundError, ValidationError, AuthorizationError, ConflictError # Example custom exceptions
class CampaignService:

    # --- Campaign CRUD ---

    @staticmethod
    def create_campaign(user_id: int, name: str, routing_strategy: str, dial_timeout_seconds: int,
                        status: str = 'active', description: str | None = None) -> CampaignModel:
        """
        Creates a new campaign for a user.

        Args:
            user_id (int): The ID of the user (Call Seller) owning the campaign.
            name (str): The name of the campaign (must be unique per user).
            routing_strategy (str): 'priority', 'round_robin', or 'weighted'.
            dial_timeout_seconds (int): Time before trying the next client.
            status (str): Initial status ('active', 'inactive', 'paused').
            description (str, optional): Description of the campaign.

        Returns:
            CampaignModel: The newly created campaign instance.

        Raises:
            ValueError: If name conflicts, invalid strategy/status/timeout, or DB error.
            # Consider ConflictError, ValidationError, ServiceError
        """
        # Validation
        if not name:
            raise ValueError("Campaign name cannot be empty.")
        if routing_strategy not in ['priority', 'round_robin', 'weighted']:
            raise ValueError("Invalid routing strategy.")
        if status not in ['active', 'inactive', 'paused']:
            raise ValueError("Invalid status.")
        if dial_timeout_seconds <= 0:
             raise ValueError("Dial timeout must be positive.")

        # Check uniqueness for the user
        if CampaignModel.query.filter_by(user_id=user_id, name=name).first():
            raise ValueError(f"Campaign name '{name}' already exists for this user.")
            # raise ConflictError(...)

        session = db.session
        try:
            new_campaign = CampaignModel(
                user_id=user_id,
                name=name,
                routing_strategy=routing_strategy,
                dial_timeout_seconds=dial_timeout_seconds,
                status=status,
                description=description
            )
            session.add(new_campaign)
            session.commit()
            return new_campaign
        except IntegrityError as e:
            session.rollback()
            # Log error e (could be FK violation if user_id is invalid)
            raise ValueError(f"Database integrity error creating campaign '{name}'.")
        except Exception as e:
            session.rollback()
            # Log error e
            raise ValueError(f"Failed to create campaign due to an unexpected error: {e}")
            # raise ServiceError(...)


    @staticmethod
    def get_campaign_by_id(campaign_id: int, user_id: int | None = None) -> CampaignModel | None:
        """
        Fetches a campaign by its ID, optionally checking ownership.

        Args:
            campaign_id (int): The campaign ID.
            user_id (int, optional): If provided, ensures the campaign belongs to this user.

        Returns:
            CampaignModel or None: The campaign or None if not found/not owned.
        """
        query = CampaignModel.query.filter_by(id=campaign_id)
        if user_id is not None:
            query = query.filter_by(user_id=user_id)
        # Eager load related data frequently needed together?
        # query = query.options(joinedload(CampaignModel.client_settings), joinedload(CampaignModel.did_associations))
        return query.one_or_none()

    @staticmethod
    def get_campaigns_for_user(user_id: int, page: int = 1, per_page: int = 20, status: str | None = None) -> Pagination:
        """
        Fetches a paginated list of campaigns owned by a user.

        Args:
            user_id (int): The user's ID.
            page (int): Page number.
            per_page (int): Items per page.
            status (str, optional): Filter by status ('active', 'inactive', 'paused').

        Returns:
            Pagination: Flask-SQLAlchemy Pagination object.
        """
        query = CampaignModel.query.filter_by(user_id=user_id).order_by(CampaignModel.name)
        if status and status in ['active', 'inactive', 'paused']:
            query = query.filter(CampaignModel.status == status)

        campaigns = query.paginate(page=page, per_page=per_page, error_out=False)
        return campaigns


    @staticmethod
    def update_campaign(campaign_id: int, user_id: int, **kwargs) -> CampaignModel:
        """
        Updates a campaign's details. Only the owner can update.

        Args:
            campaign_id (int): ID of the campaign to update.
            user_id (int): ID of the user attempting the update (must be owner).
            **kwargs: Fields to update (name, routing_strategy, dial_timeout_seconds, status, description).

        Returns:
            CampaignModel: The updated campaign instance.

        Raises:
            ValueError: If campaign not found, user not owner, invalid data, name conflict, or update fails.
            # Consider NotFoundError, AuthorizationError, ConflictError, ValidationError, ServiceError
        """
        campaign = CampaignService.get_campaign_by_id(campaign_id)

        if not campaign:
            raise ValueError(f"Campaign with ID {campaign_id} not found.")
            # raise NotFoundError(...)
        if campaign.user_id != user_id:
            raise ValueError("User is not authorized to update this campaign.")
            # raise AuthorizationError(...)

        allowed_updates = ['name', 'routing_strategy', 'dial_timeout_seconds', 'status', 'description']
        updated = False
        session = db.session
        try:
            for key, value in kwargs.items():
                if key in allowed_updates:
                    # Add validation for specific fields
                    if key == 'name' and value != campaign.name:
                         if not value: raise ValueError("Campaign name cannot be empty.")
                         if CampaignModel.query.filter(CampaignModel.user_id == user_id,
                                                       CampaignModel.id != campaign_id,
                                                       CampaignModel.name == value).first():
                             raise ValueError(f"Campaign name '{value}' already exists for this user.")
                             # raise ConflictError(...)
                    if key == 'routing_strategy' and value not in ['priority', 'round_robin', 'weighted']:
                         raise ValueError("Invalid routing strategy.")
                    if key == 'status' and value not in ['active', 'inactive', 'paused']:
                         raise ValueError("Invalid status.")
                    if key == 'dial_timeout_seconds' and (not isinstance(value, int) or value <= 0):
                         raise ValueError("Dial timeout must be a positive integer.")

                    setattr(campaign, key, value)
                    updated = True

            if updated:
                session.commit()
            return campaign
        except IntegrityError as e: # Catch potential unique constraint violation on name commit
             session.rollback()
             if 'uq_user_campaign_name' in str(e.orig):
                 raise ValueError(f"Campaign name '{kwargs.get('name')}' already exists for this user.")
             else:
                 raise ValueError("Database integrity error updating campaign.")
        except Exception as e:
            session.rollback()
            # Log error e
            raise ValueError(f"Failed to update campaign due to an unexpected error: {e}")
            # raise ServiceError(...)


    @staticmethod
    def delete_campaign(campaign_id: int, user_id: int) -> bool:
        """
        Deletes a campaign. Only the owner can delete.
        Associated CampaignDidModel and CampaignClientSettingsModel records are cascade deleted.

        Args:
            campaign_id (int): ID of the campaign to delete.
            user_id (int): ID of the user attempting deletion (must be owner).

        Returns:
            bool: True if deletion was successful.

        Raises:
            ValueError: If campaign not found, user not owner, or deletion fails.
            # Consider NotFoundError, AuthorizationError, ServiceError
        """
        campaign = CampaignService.get_campaign_by_id(campaign_id)

        if not campaign:
            raise ValueError(f"Campaign with ID {campaign_id} not found.")
            # raise NotFoundError(...)
        if campaign.user_id != user_id:
            raise ValueError("User is not authorized to delete this campaign.")
            # raise AuthorizationError(...)

        session = db.session
        try:
            # Deleting the campaign will cascade delete associations due to model definitions
            session.delete(campaign)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            # Log error e
            raise ValueError(f"Failed to delete campaign due to an unexpected error: {e}")
            # raise ServiceError(...)


    # --- Campaign DID Link Management ---

    @staticmethod
    def set_campaign_dids(campaign_id: int, user_id: int, did_ids: list[int]) -> bool:
        """
        Sets the DIDs associated with a campaign, replacing any existing ones.
        Ensures the user owns both the campaign and the specified DIDs.

        Args:
            campaign_id (int): The ID of the campaign.
            user_id (int): The ID of the user (owner).
            did_ids (list[int]): A list of DID IDs to associate with the campaign.

        Returns:
            bool: True on success.

        Raises:
            ValueError: If campaign/DID not found, ownership mismatch, or DB error.
            # Consider NotFoundError, AuthorizationError, ServiceError
        """
        campaign = CampaignService.get_campaign_by_id(campaign_id, user_id)
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found or not owned by user {user_id}.")
            # raise NotFoundError or AuthorizationError

        session = db.session
        try:
            # Verify user owns all provided DIDs
            if did_ids: # Only check if list is not empty
                 owned_dids_count = db.session.query(func.count(DidModel.id)).filter(
                     DidModel.user_id == user_id,
                     DidModel.id.in_(did_ids)
                 ).scalar()
                 if owned_dids_count != len(set(did_ids)): # Use set to handle potential duplicates in input list
                      raise ValueError("One or more specified DIDs are not owned by the user.")
                      # raise AuthorizationError(...)

            # Efficiently replace links: Delete existing, then add new ones
            # 1. Delete existing links for this campaign
            session.execute(delete(CampaignDidModel).where(CampaignDidModel.campaign_id == campaign_id))

            # 2. Add new links
            if did_ids:
                new_links = [{'campaign_id': campaign_id, 'did_id': did_id} for did_id in set(did_ids)]
                if new_links:
                    session.bulk_insert_mappings(CampaignDidModel, new_links)

            session.commit()
            return True

        except Exception as e:
            session.rollback()
            # Log error e
            raise ValueError(f"Failed to set DIDs for campaign {campaign_id}: {e}")
            # raise ServiceError(...)


    # --- Campaign Client Settings Management ---

    @staticmethod
    def add_client_to_campaign(campaign_id: int, user_id: int, client_id: int, settings: dict) -> CampaignClientSettingsModel:
        """
        Links a Client to a Campaign with specific settings.

        Args:
            campaign_id (int): The campaign ID.
            user_id (int): The user ID (must own the campaign).
            client_id (int): The client ID to link.
            settings (dict): Dictionary containing settings like:
                             { max_concurrency, total_calls_allowed (optional),
                               forwarding_priority, weight, status (optional, default 'active') }

        Returns:
            CampaignClientSettingsModel: The newly created settings record.

        Raises:
            ValueError: If campaign/client not found, ownership mismatch, client already linked, invalid settings, or DB error.
            # Consider NotFoundError, AuthorizationError, ConflictError, ValidationError, ServiceError
        """
        campaign = CampaignService.get_campaign_by_id(campaign_id, user_id)
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found or not owned by user {user_id}.")

        # Verify client exists (doesn't need to be owned by the user)
        client = ClientModel.query.get(client_id)
        if not client:
            raise ValueError(f"Client with ID {client_id} not found.")
            # raise NotFoundError(...)

        # Check if already linked
        existing_link = CampaignClientSettingsModel.query.filter_by(
            campaign_id=campaign_id,
            client_id=client_id
        ).first()
        if existing_link:
            raise ValueError(f"Client {client_id} is already linked to campaign {campaign_id}.")
            # raise ConflictError(...)

        # Validate required settings
        required_settings = ['max_concurrency', 'forwarding_priority', 'weight']
        if not all(key in settings for key in required_settings):
            raise ValueError(f"Missing required settings: {', '.join(required_settings)}")

        session = db.session
        try:
            new_setting = CampaignClientSettingsModel(
                campaign_id=campaign_id,
                client_id=client_id,
                max_concurrency=settings['max_concurrency'],
                total_calls_allowed=settings.get('total_calls_allowed'), # Optional
                forwarding_priority=settings['forwarding_priority'],
                weight=settings['weight'],
                status=settings.get('status', 'active')
            )
            # Validation logic (e.g., positive weight/concurrency) is handled by @validates in the model

            session.add(new_setting)
            session.commit()
            return new_setting
        except IntegrityError as e: # Could be FK violation if IDs invalid somehow
            session.rollback()
            raise ValueError("Database integrity error linking client to campaign.")
        except Exception as e:
            session.rollback()
            # Log error e
            raise ValueError(f"Failed to link client {client_id} to campaign {campaign_id}: {e}")
            # raise ServiceError(...)


    @staticmethod
    def update_campaign_client_setting(setting_id: int, user_id: int, updates: dict) -> CampaignClientSettingsModel:
        """
        Updates the settings for a specific Campaign-Client link.

        Args:
            setting_id (int): The ID of the CampaignClientSettings record.
            user_id (int): The user ID (must own the parent campaign).
            updates (dict): Dictionary of settings to update (max_concurrency,
                            total_calls_allowed, current_total_calls, forwarding_priority,
                            weight, status).

        Returns:
            CampaignClientSettingsModel: The updated settings record.

        Raises:
            ValueError: If setting not found, ownership mismatch, invalid data, or update fails.
            # Consider NotFoundError, AuthorizationError, ValidationError, ServiceError
        """
        setting = CampaignClientSettingsModel.query.options(
            joinedload(CampaignClientSettingsModel.campaign) # Eager load campaign for ownership check
        ).get(setting_id)

        if not setting:
            raise ValueError(f"Campaign client setting with ID {setting_id} not found.")
            # raise NotFoundError(...)
        if setting.campaign.user_id != user_id:
            raise ValueError("User is not authorized to update this campaign client setting.")
            # raise AuthorizationError(...)

        allowed_updates = ['max_concurrency', 'total_calls_allowed', 'current_total_calls',
                           'forwarding_priority', 'weight', 'status']
        updated = False
        session = db.session
        try:
            for key, value in updates.items():
                 if key in allowed_updates:
                     # Add specific validation if needed (models handle basic type/constraints)
                     if key == 'status' and value not in ['active', 'inactive']:
                         raise ValueError("Invalid status.")
                     if key == 'current_total_calls' and (not isinstance(value, int) or value < 0):
                          raise ValueError("Current total calls must be a non-negative integer.")

                     setattr(setting, key, value)
                     updated = True

            if updated:
                session.commit()
            return setting
        except Exception as e:
            session.rollback()
            # Log error e
            raise ValueError(f"Failed to update campaign client setting {setting_id}: {e}")
            # raise ServiceError(...)


    @staticmethod
    def remove_client_from_campaign(setting_id: int, user_id: int) -> bool:
        """
        Removes a Client link (and its settings) from a Campaign.

        Args:
            setting_id (int): The ID of the CampaignClientSettings record to delete.
            user_id (int): The user ID (must own the parent campaign).

        Returns:
            bool: True if deletion was successful.

        Raises:
            ValueError: If setting not found, ownership mismatch, or deletion fails.
            # Consider NotFoundError, AuthorizationError, ServiceError
        """
        # Fetch setting and verify ownership via the campaign
        setting = db.session.get(CampaignClientSettingsModel, setting_id, options=[joinedload(CampaignClientSettingsModel.campaign)])

        if not setting:
            raise ValueError(f"Campaign client setting with ID {setting_id} not found.")
            # raise NotFoundError(...)
        if setting.campaign.user_id != user_id:
            raise ValueError("User is not authorized to remove this campaign client setting.")
            # raise AuthorizationError(...)

        session = db.session
        try:
            session.delete(setting)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            # Log error e
            raise ValueError(f"Failed to remove client link {setting_id}: {e}")
            # raise ServiceError(...)


    @staticmethod
    def get_campaign_client_settings(campaign_id: int, user_id: int) -> list[CampaignClientSettingsModel]:
        """
        Gets all client settings/links for a specific campaign owned by the user.

        Args:
            campaign_id (int): The campaign ID.
            user_id (int): The user ID (must own the campaign).

        Returns:
            list[CampaignClientSettingsModel]: List of settings objects, ordered by priority.

        Raises:
            ValueError: If campaign not found or not owned by user.
            # Consider NotFoundError, AuthorizationError
        """
        campaign = CampaignService.get_campaign_by_id(campaign_id, user_id)
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found or not owned by user {user_id}.")

        return CampaignClientSettingsModel.query.filter_by(campaign_id=campaign_id)\
            .options(joinedload(CampaignClientSettingsModel.client))\
            .order_by(CampaignClientSettingsModel.forwarding_priority)\
            .all()