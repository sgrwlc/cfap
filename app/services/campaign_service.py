# -*- coding: utf-8 -*-
"""
Campaign Service
Handles business logic related to Campaigns, their linked DIDs,
and the settings for linked Clients (CampaignClientSettings).
Service methods that modify data add/delete/update objects in the
session but DO NOT COMMIT. The caller (e.g., route handler) is
responsible for committing the transaction.
"""
from sqlalchemy import select, delete, func, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, Session # Import Session for type hinting if needed

# Import Pagination type hint
from flask_sqlalchemy.pagination import Pagination
# Import models
from app.database.models.campaign import CampaignModel, CampaignDidModel, CampaignClientSettingsModel
from app.database.models.did import DidModel
from app.database.models.client import ClientModel
# Import db instance
from app.extensions import db
# Import current_app for logging if needed (though better to pass logger or use standard logging)
# from flask import current_app

# Example custom exceptions (define these in utils/exceptions.py)
# class NotFoundError(Exception): pass
# class ConflictError(Exception): pass
# class AuthorizationError(Exception): pass
# class ServiceError(Exception): pass

class CampaignService:

    # --- Campaign CRUD ---

    @staticmethod
    def create_campaign(user_id: int, name: str, routing_strategy: str, dial_timeout_seconds: int,
                        status: str = 'active', description: str | None = None) -> CampaignModel:
        """
        Creates a new campaign and adds it to the session (DOES NOT COMMIT).

        Args:
            user_id (int): The ID of the user (Call Seller) owning the campaign.
            name (str): The name of the campaign (must be unique per user).
            routing_strategy (str): 'priority', 'round_robin', or 'weighted'.
            dial_timeout_seconds (int): Time before trying the next client.
            status (str): Initial status ('active', 'inactive', 'paused').
            description (str, optional): Description of the campaign.

        Returns:
            CampaignModel: The newly created campaign instance (uncommitted).

        Raises:
            ValueError: If name conflicts, invalid strategy/status/timeout, or DB flush error.
        """
        # Validation
        if not name:
            raise ValueError("Campaign name cannot be empty.")
        if routing_strategy not in ['priority', 'round_robin', 'weighted']:
            raise ValueError("Invalid routing strategy.")
        if status not in ['active', 'inactive', 'paused']:
            raise ValueError("Invalid status.")
        if dial_timeout_seconds <= 0:
             raise ValueError("Dial timeout must be a positive integer.")

        # Check uniqueness using session query
        session = db.session
        existing = session.query(CampaignModel.id).filter_by(user_id=user_id, name=name).first()
        if existing:
            raise ValueError(f"Campaign name '{name}' already exists for this user.")
            # raise ConflictError(...)

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
            session.flush() # Flush to get ID and check constraints early
            return new_campaign
        except IntegrityError as e: # Catch potential FK violation on flush
            session.rollback()
            raise ValueError(f"Database integrity error creating campaign '{name}': {e.orig}")
        except Exception as e: # Catch other flush errors
            session.rollback()
            raise ValueError(f"Failed to add campaign to session due to an unexpected error: {e}")


    @staticmethod
    def get_campaign_by_id(campaign_id: int, user_id: int | None = None) -> CampaignModel | None:
        """
        Fetches a campaign by its ID, optionally checking ownership. Uses session.get.

        Args:
            campaign_id (int): The campaign ID.
            user_id (int, optional): If provided, ensures the campaign belongs to this user.

        Returns:
            CampaignModel or None: The campaign or None if not found/not owned.
        """
        campaign = db.session.get(CampaignModel, campaign_id)
        if campaign and (user_id is None or campaign.user_id == user_id):
             # Optional: Eager load common relationships if needed often
             # You might pass load options from the caller or define common loading here
             # e.g., using db.session.get(CampaignModel, campaign_id, options=[...])
             return campaign
        return None

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
        query = db.session.query(CampaignModel).filter_by(user_id=user_id).order_by(CampaignModel.name)
        if status and status in ['active', 'inactive', 'paused']:
            query = query.filter(CampaignModel.status == status)

        # Use select=True for paginate with SQLAlchemy >= 2.0 session queries
        campaigns = query.paginate(page=page, per_page=per_page, error_out=False, count=True)
        return campaigns


    @staticmethod
    def update_campaign(campaign_id: int, user_id: int, **kwargs) -> CampaignModel:
        """
        Updates a campaign's details in the session (DOES NOT COMMIT).
        Only the owner can update.

        Args:
            campaign_id (int): ID of the campaign to update.
            user_id (int): ID of the user attempting the update (must be owner).
            **kwargs: Fields to update (name, routing_strategy, dial_timeout_seconds, status, description).

        Returns:
            CampaignModel: The updated campaign instance (uncommitted).

        Raises:
            ValueError: If campaign not found, user not owner, invalid data, name conflict, or DB flush error.
        """
        session = db.session
        campaign = session.get(CampaignModel, campaign_id)

        if not campaign:
            raise ValueError(f"Campaign with ID {campaign_id} not found.")
        if campaign.user_id != user_id:
            raise ValueError("User is not authorized to update this campaign.")

        allowed_updates = ['name', 'routing_strategy', 'dial_timeout_seconds', 'status', 'description']
        updated = False
        try:
            for key, value in kwargs.items():
                if key in allowed_updates:
                    # Validation
                    if key == 'name' and value != campaign.name:
                         if not value: raise ValueError("Campaign name cannot be empty.")
                         existing = session.query(CampaignModel.id).filter(
                             CampaignModel.user_id == user_id,
                             CampaignModel.id != campaign_id,
                             CampaignModel.name == value
                         ).first()
                         if existing:
                             raise ValueError(f"Campaign name '{value}' already exists for this user.")
                    if key == 'routing_strategy' and value not in ['priority', 'round_robin', 'weighted']:
                         raise ValueError("Invalid routing strategy.")
                    if key == 'status' and value not in ['active', 'inactive', 'paused']:
                         raise ValueError("Invalid status.")
                    if key == 'dial_timeout_seconds' and (not isinstance(value, int) or value <= 0):
                         raise ValueError("Dial timeout must be a positive integer.")

                    setattr(campaign, key, value)
                    updated = True

            if updated:
                session.flush() # Flush to check constraints early
            return campaign
        except IntegrityError as e: # Catch potential unique constraint violation on flush
             session.rollback()
             if 'uq_user_campaign_name' in str(e.orig):
                 raise ValueError(f"Campaign name '{kwargs.get('name')}' already exists for this user.")
             else:
                 raise ValueError(f"Database integrity error updating campaign: {e.orig}")
        except Exception as e: # Catch other flush errors
            session.rollback()
            raise ValueError(f"Failed to flush campaign update due to an unexpected error: {e}")


    @staticmethod
    def delete_campaign(campaign_id: int, user_id: int) -> bool:
        """
        Marks a campaign for deletion in the session (DOES NOT COMMIT).
        Only the owner can delete. Cascades handled by DB/ORM relationships.

        Args:
            campaign_id (int): ID of the campaign to delete.
            user_id (int): ID of the user attempting deletion (must be owner).

        Returns:
            bool: True if marked for deletion successfully.

        Raises:
            ValueError: If campaign not found or user not owner.
        """
        session = db.session
        campaign = session.get(CampaignModel, campaign_id)

        if not campaign:
            raise ValueError(f"Campaign with ID {campaign_id} not found.")
        if campaign.user_id != user_id:
            raise ValueError("User is not authorized to delete this campaign.")

        try:
            session.delete(campaign)
            session.flush() # Flush to ensure delete is processed within transaction context if needed
            return True
        except Exception as e: # Catch potential errors during delete/flush
            session.rollback()
            raise ValueError(f"Failed to mark campaign for deletion due to an unexpected error: {e}")


    # --- Campaign DID Link Management ---

    @staticmethod
    def set_campaign_dids(campaign_id: int, user_id: int, did_ids: list[int]) -> bool:
        """
        Sets the DIDs associated with a campaign in the session (DOES NOT COMMIT).
        Ensures the user owns both the campaign and the specified DIDs.

        Args:
            campaign_id (int): The ID of the campaign.
            user_id (int): The ID of the user (owner).
            did_ids (list[int]): A list of DID IDs to associate with the campaign.

        Returns:
            bool: True on success (changes staged in session).

        Raises:
            ValueError: If campaign/DID not found, ownership mismatch, or DB flush error.
        """
        session = db.session
        campaign = session.get(CampaignModel, campaign_id)
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found.")
        if campaign.user_id != user_id:
             raise ValueError(f"User {user_id} not authorized for campaign {campaign_id}.")

        try:
            # Verify user owns all provided DIDs within the current session/transaction
            unique_did_ids = set(did_ids) # Process unique IDs
            if unique_did_ids: # Only check if list is not empty
                 owned_dids_count = session.query(func.count(DidModel.id)).filter(
                     DidModel.user_id == user_id,
                     DidModel.id.in_(unique_did_ids)
                 ).scalar()
                 if owned_dids_count != len(unique_did_ids):
                      raise ValueError("One or more specified DIDs are not owned by the user or do not exist.")

            # Efficiently replace links: Delete existing, then add new ones
            # 1. Delete existing links for this campaign
            session.execute(delete(CampaignDidModel).where(CampaignDidModel.campaign_id == campaign_id))

            # 2. Add new links
            if unique_did_ids:
                new_links = [{'campaign_id': campaign_id, 'did_id': did_id} for did_id in unique_did_ids]
                if new_links:
                    # Use add_all with ORM objects or stick to bulk_insert if preferred
                    # Creating objects might trigger ORM events if needed later
                    instances = [CampaignDidModel(**link) for link in new_links]
                    session.add_all(instances)
                    # Or: session.bulk_insert_mappings(CampaignDidModel, new_links)
            session.flush() # Flush to check constraints early
            return True

        except Exception as e:
            session.rollback()
            raise ValueError(f"Failed to stage DID settings for campaign {campaign_id}: {e}")


    # --- Campaign Client Settings Management ---

    @staticmethod
    def add_client_to_campaign(campaign_id: int, user_id: int, client_id: int, settings: dict) -> CampaignClientSettingsModel:
        """
        Links a Client to a Campaign with specific settings, adding to session (DOES NOT COMMIT).

        Args:
            campaign_id (int): The campaign ID.
            user_id (int): The user ID (must own the campaign).
            client_id (int): The client ID to link.
            settings (dict): Dictionary containing settings like:
                             { max_concurrency, total_calls_allowed (optional),
                               forwarding_priority, weight, status (optional, default 'active') }

        Returns:
            CampaignClientSettingsModel: The newly created settings record (uncommitted).

        Raises:
            ValueError: If campaign/client not found, ownership mismatch, client already linked, invalid settings, or DB error.
        """
        session = db.session
        campaign = session.get(CampaignModel, campaign_id)
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found.")
        if campaign.user_id != user_id:
             raise ValueError(f"User {user_id} not authorized for campaign {campaign_id}.")

        # Verify client exists
        client = session.get(ClientModel, client_id) # Use session.get
        if not client:
            raise ValueError(f"Client with ID {client_id} not found.")

        # Check if already linked
        existing_link = session.query(CampaignClientSettingsModel.id).filter_by(
            campaign_id=campaign_id,
            client_id=client_id
        ).first()
        if existing_link:
            raise ValueError(f"Client {client_id} is already linked to campaign {campaign_id}.")

        # Validate required settings keys exist (values validated by model/flush)
        required_keys = ['max_concurrency', 'forwarding_priority', 'weight']
        if not all(key in settings for key in required_keys):
            raise ValueError(f"Missing required settings: {', '.join(required_keys)}")

        try:
            new_setting = CampaignClientSettingsModel(
                campaign_id=campaign_id,
                client_id=client_id,
                max_concurrency=settings['max_concurrency'],
                total_calls_allowed=settings.get('total_calls_allowed'), # Can be None
                forwarding_priority=settings['forwarding_priority'],
                weight=settings['weight'],
                status=settings.get('status', 'active')
            )
            session.add(new_setting)
            session.flush() # Flush to validate model constraints and get ID
            return new_setting
        except IntegrityError as e: # Catch FK or other integrity errors on flush
            session.rollback()
            raise ValueError(f"Database integrity error linking client to campaign: {e.orig}")
        except Exception as e: # Catch other flush errors
            session.rollback()
            raise ValueError(f"Failed to add client link to session for campaign {campaign_id}: {e}")


    @staticmethod
    def update_campaign_client_setting(setting_id: int, user_id: int, updates: dict) -> CampaignClientSettingsModel:
        """
        Updates the settings for a specific Campaign-Client link in session (DOES NOT COMMIT).

        Args:
            setting_id (int): The ID of the CampaignClientSettings record.
            user_id (int): The user ID (must own the parent campaign).
            updates (dict): Dictionary of settings to update.

        Returns:
            CampaignClientSettingsModel: The updated settings record (uncommitted).

        Raises:
            ValueError: If setting not found, ownership mismatch, invalid data, or DB flush error.
        """
        session = db.session
        # Fetch setting and eagerly load campaign for ownership check using session.get
        setting = session.get(
            CampaignClientSettingsModel,
            setting_id,
            options=[joinedload(CampaignClientSettingsModel.campaign)]
        )

        if not setting:
            raise ValueError(f"Campaign client setting with ID {setting_id} not found.")
        if setting.campaign.user_id != user_id:
            raise ValueError("User is not authorized to update this campaign client setting.")

        allowed_updates = ['max_concurrency', 'total_calls_allowed', 'current_total_calls',
                           'forwarding_priority', 'weight', 'status']
        updated = False
        try:
            for key, value in updates.items():
                 if key in allowed_updates:
                     # Basic type/value validation (more complex in schema or here)
                     if key == 'status' and value not in ['active', 'inactive']:
                         raise ValueError("Invalid status.")
                     if key == 'current_total_calls' and (value is not None and (not isinstance(value, int) or value < 0)):
                          raise ValueError("Current total calls must be a non-negative integer or null.")
                     # Model's @validates handles positive weight/concurrency checks

                     setattr(setting, key, value)
                     updated = True

            if updated:
                session.flush() # Flush to check constraints
            return setting
        except Exception as e:
            session.rollback()
            raise ValueError(f"Failed to flush updated campaign client setting {setting_id}: {e}")


    @staticmethod
    def remove_client_from_campaign(setting_id: int, user_id: int) -> bool:
        """
        Marks a Campaign-Client link for deletion in the session (DOES NOT COMMIT).

        Args:
            setting_id (int): The ID of the CampaignClientSettings record to delete.
            user_id (int): The user ID (must own the parent campaign).

        Returns:
            bool: True if marked for deletion successfully.

        Raises:
            ValueError: If setting not found or ownership mismatch.
        """
        session = db.session
        # Fetch setting and verify ownership via the campaign
        setting = session.get(
            CampaignClientSettingsModel,
            setting_id,
            options=[joinedload(CampaignClientSettingsModel.campaign)]
        )

        if not setting:
            raise ValueError(f"Campaign client setting with ID {setting_id} not found.")
        if setting.campaign.user_id != user_id:
            raise ValueError("User is not authorized to remove this campaign client setting.")

        try:
            session.delete(setting)
            session.flush() # Flush to ensure delete is processed within transaction
            return True
        except Exception as e:
            session.rollback()
            raise ValueError(f"Failed to mark client link {setting_id} for deletion: {e}")


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
        """
        # Check campaign ownership first
        campaign = db.session.get(CampaignModel, campaign_id)
        if not campaign:
             raise ValueError(f"Campaign {campaign_id} not found.")
        if campaign.user_id != user_id:
             raise ValueError(f"User {user_id} not authorized for campaign {campaign_id}.")

        # Query settings, eager loading client info
        return db.session.query(CampaignClientSettingsModel)\
            .filter_by(campaign_id=campaign_id)\
            .options(joinedload(CampaignClientSettingsModel.client))\
            .order_by(CampaignClientSettingsModel.forwarding_priority)\
            .all()