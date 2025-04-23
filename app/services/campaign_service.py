# app/services/campaign_service.py
# -*- coding: utf-8 -*-
"""
Campaign Service
Handles business logic related to Campaigns, their linked DIDs,
and the settings for linked Clients (CampaignClientSettings).
Service methods modify the session but DO NOT COMMIT.
"""
from sqlalchemy import select, delete, func, and_
from sqlalchemy.exc import IntegrityError
# Corrected import: Added selectinload
from sqlalchemy.orm import joinedload, Session, contains_eager, selectinload
from flask import current_app # Added for logging
from flask_sqlalchemy.pagination import Pagination

# Import models
from app.database.models.campaign import CampaignModel, CampaignDidModel, CampaignClientSettingsModel
from app.database.models.did import DidModel
from app.database.models.client import ClientModel
from app.database.models.user import UserModel # Needed for checks
# Import db instance
from app.extensions import db
# Import custom exceptions
from app.utils.exceptions import ResourceNotFound, ConflictError, ServiceError, ValidationError, AuthorizationError


class CampaignService:

    # --- Campaign CRUD ---

    @staticmethod
    def create_campaign(user_id: int, name: str, routing_strategy: str, dial_timeout_seconds: int,
                        status: str = 'active', description: str | None = None) -> CampaignModel:
        """
        Adds a new campaign instance to the session (DOES NOT COMMIT).

        Args:
            user_id (int): The ID of the user (Call Seller) owning the campaign.
            name (str): The name of the campaign (must be unique per user).
            routing_strategy (str): 'priority', 'round_robin', or 'weighted'. Schema validates value.
            dial_timeout_seconds (int): Time before trying the next client. Schema validates range.
            status (str): Initial status ('active', 'inactive', 'paused'). Schema validates value.
            description (str, optional): Description of the campaign.

        Returns:
            CampaignModel: The newly created campaign instance, added to the session.

        Raises:
            ValidationError: For invalid input if not caught by schema.
            ConflictError: If campaign name conflicts for the user.
            ServiceError: For database integrity errors or unexpected errors during flush.
        """
        # Basic validation
        if not name: raise ValidationError("Campaign name cannot be empty.")
        # Schema should handle strategy, status, timeout checks

        # Check uniqueness within the current transaction context
        if db.session.query(CampaignModel.id).filter_by(user_id=user_id, name=name).first():
            raise ConflictError(f"Campaign name '{name}' already exists for this user.")

        new_campaign = CampaignModel(
            user_id=user_id,
            name=name,
            routing_strategy=routing_strategy,
            dial_timeout_seconds=dial_timeout_seconds,
            status=status,
            description=description
        )
        try:
            db.session.add(new_campaign)
            db.session.flush() # Flush to catch constraints and get ID
            current_app.logger.info(f"Campaign '{name}' added to session for user ID {user_id}.")
            return new_campaign
        except IntegrityError as e:
            db.session.rollback()
            current_app.logger.error(f"Database integrity error creating campaign '{name}': {e}", exc_info=True)
            if 'uq_user_campaign_name' in str(e.orig).lower(): # Check specific constraint name if known
                 raise ConflictError(f"Campaign name '{name}' already exists for this user (constraint violation).")
            elif 'violates foreign key constraint "campaigns_user_id_fkey"' in str(e.orig).lower():
                 raise ServiceError(f"Cannot create campaign: User with ID {user_id} does not exist.")
            else:
                 raise ServiceError(f"Database integrity error creating campaign: {e.orig}")
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Unexpected error adding campaign '{name}' to session: {e}", exc_info=True)
            raise ServiceError(f"Failed to add campaign to session: {e}")


    @staticmethod
    def get_campaign_by_id(campaign_id: int, user_id: int | None = None, load_links: bool = False) -> CampaignModel | None:
        """
        Fetches a campaign by its ID, optionally checking ownership and loading links.

        Args:
            campaign_id (int): The campaign ID.
            user_id (int, optional): If provided, ensures the campaign belongs to this user.
            load_links (bool): If True, eagerly loads DIDs and Client Settings.

        Returns:
            CampaignModel or None: The campaign or None if not found/not owned.
        """
        query = db.session.query(CampaignModel)
        # if load_links:
        #     query = query.options(
        #         # Use selectinload on the association table -> joinedload the target
        #         # selectinload(CampaignModel.did_associations).joinedload(CampaignDidModel.did, innerjoin=True), # Load DID via association
        #         selectinload(CampaignModel.client_settings).joinedload(CampaignClientSettingsModel.client, innerjoin=True) # Load Setting->Client
        #     )
        # Use session.get for primary key lookup
        # campaign = query.get(campaign_id) # Causes LegacyAPIWarning and eager loading issue with dynamic?
        # Fetch using filter and options instead when eager loading complex relationships
        query = query.filter(CampaignModel.id == campaign_id)
        campaign = query.one_or_none()

        if campaign and (user_id is None or campaign.user_id == user_id):
            return campaign
        return None


    @staticmethod
    def get_campaigns_for_user(user_id: int, page: int = 1, per_page: int = 20,
                               status: str | None = None) -> Pagination:
        """Fetches a paginated list of campaigns owned by a user."""
        query = db.session.query(CampaignModel).filter_by(user_id=user_id).order_by(CampaignModel.name)
        if status and status in ['active', 'inactive', 'paused']:
            query = query.filter(CampaignModel.status == status)

        pagination = query.paginate(page=page, per_page=per_page, error_out=False, count=True)
        return pagination


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
            CampaignModel: The updated campaign instance present in the session.

        Raises:
            ResourceNotFound: If campaign not found.
            AuthorizationError: If user is not the owner.
            ValidationError: If data is invalid (timeout <= 0, invalid enum values if not schema checked).
            ConflictError: If updated name conflicts with another campaign for the user.
            ServiceError: For unexpected errors during flush.
        """
        session = db.session
        campaign = session.get(CampaignModel, campaign_id)

        if not campaign:
            raise ResourceNotFound(f"Campaign with ID {campaign_id} not found.")
        if campaign.user_id != user_id:
            current_app.logger.warning(f"User {user_id} attempted to update campaign {campaign_id} owned by user {campaign.user_id}.")
            raise AuthorizationError("User is not authorized to update this campaign.")

        allowed_updates = ['name', 'routing_strategy', 'dial_timeout_seconds', 'status', 'description']
        updated = False
        try:
            for key, value in kwargs.items():
                if key in allowed_updates:
                    if key == 'name' and value != campaign.name:
                         if not value: raise ValidationError("Campaign name cannot be empty.")
                         existing = session.query(CampaignModel.id).filter(
                             CampaignModel.user_id == user_id,
                             CampaignModel.id != campaign_id,
                             CampaignModel.name == value
                         ).first()
                         if existing:
                             raise ConflictError(f"Campaign name '{value}' already exists for this user.")
                    if key == 'dial_timeout_seconds':
                         if not isinstance(value, int) or value <= 0:
                              raise ValidationError("Dial timeout must be a positive integer.")

                    setattr(campaign, key, value)
                    updated = True

            if updated:
                session.flush()
                current_app.logger.info(f"Campaign ID {campaign_id} updated in session.")
            else:
                current_app.logger.info(f"No valid fields provided to update Campaign ID {campaign_id}.")

            return campaign
        except ConflictError as e:
            # Don't rollback here, let route handle it based on this specific error
            current_app.logger.warning(f"Conflict error during campaign update flush for ID {campaign_id}: {e}")
            raise e # Re-raise
        except IntegrityError as e:
            session.rollback() # Rollback mandatory
            current_app.logger.error(f"Database integrity error updating campaign {campaign_id}: {e}", exc_info=True)
            if 'uq_user_campaign_name' in str(e.orig):
                raise ConflictError(f"Campaign name '{kwargs.get('name')}' already exists for this user (constraint violation).")
            else:
                raise ServiceError(f"Database integrity error updating campaign: {e.orig}")
        # --- Catch other KNOWN custom exceptions if applicable ---
        except ValidationError as e:
            # Don't rollback here, let route handle it
            raise e
        # --- Catch truly unexpected exceptions LAST ---
        except Exception as e:
            session.rollback()
            current_app.logger.error(f"Unexpected error updating campaign {campaign_id} in session: {e}", exc_info=True)
            # Avoid re-raising known custom errors as generic ServiceError
            if isinstance(e, (ResourceNotFound, AuthorizationError)):
                raise e
            raise ServiceError(f"Failed to update campaign in session: {e}")


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
            ResourceNotFound: If campaign not found.
            AuthorizationError: If user is not the owner.
            ServiceError: For unexpected errors during delete/flush.
        """
        session = db.session
        campaign = session.get(CampaignModel, campaign_id)

        if not campaign:
            raise ResourceNotFound(f"Campaign with ID {campaign_id} not found.")
        if campaign.user_id != user_id:
            current_app.logger.warning(f"User {user_id} attempted to delete campaign {campaign_id} owned by user {campaign.user_id}.")
            raise AuthorizationError("User is not authorized to delete this campaign.")

        try:
            session.delete(campaign)
            session.flush()
            current_app.logger.info(f"Campaign ID {campaign_id} marked for deletion in session.")
            return True
        except IntegrityError as e:
             session.rollback()
             current_app.logger.error(f"Database integrity error deleting campaign {campaign_id}: {e}", exc_info=True)
             raise ServiceError(f"Failed to stage campaign deletion due to DB integrity issues: {e.orig}")
        except Exception as e:
            session.rollback()
            current_app.logger.error(f"Unexpected error deleting campaign {campaign_id}: {e}", exc_info=True)
            raise ServiceError(f"Failed to stage campaign deletion: {e}")


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
            ResourceNotFound: If campaign not found.
            AuthorizationError: If user doesn't own campaign or one of the DIDs.
            ServiceError: For unexpected errors during update/flush.
        """
        session = db.session
        campaign = session.get(CampaignModel, campaign_id)
        if not campaign:
            raise ResourceNotFound(f"Campaign {campaign_id} not found.")
        if campaign.user_id != user_id:
             current_app.logger.warning(f"User {user_id} attempted to set DIDs for campaign {campaign_id} owned by user {campaign.user_id}.")
             raise AuthorizationError(f"User not authorized for campaign {campaign_id}.")

        try:
            unique_did_ids = set(did_ids)
            if unique_did_ids:
                 owned_dids_query = session.query(DidModel.id).filter(
                     DidModel.user_id == user_id,
                     DidModel.id.in_(unique_did_ids)
                 )
                 owned_dids_count = owned_dids_query.count()

                 if owned_dids_count != len(unique_did_ids):
                      owned_set = {row.id for row in owned_dids_query.all()}
                      missing_or_not_owned = unique_did_ids - owned_set
                      raise AuthorizationError(f"One or more specified DIDs are not owned by the user or do not exist: {list(missing_or_not_owned)}.")

            session.execute(delete(CampaignDidModel).where(CampaignDidModel.campaign_id == campaign_id))

            if unique_did_ids:
                instances = [CampaignDidModel(campaign_id=campaign_id, did_id=did_id) for did_id in unique_did_ids]
                if instances:
                    session.add_all(instances)

            session.flush()
            current_app.logger.info(f"DID links updated in session for campaign ID {campaign_id}.")
            return True

        except IntegrityError as e:
            session.rollback()
            current_app.logger.error(f"Database integrity error setting DIDs for campaign {campaign_id}: {e}", exc_info=True)
            raise ServiceError(f"Database error setting DIDs for campaign: {e.orig}")
        except Exception as e:
            session.rollback()
            current_app.logger.error(f"Unexpected error setting DIDs for campaign {campaign_id}: {e}", exc_info=True)
            if isinstance(e, AuthorizationError): raise e
            raise ServiceError(f"Failed to stage DID settings for campaign {campaign_id}: {e}")


    # --- Campaign Client Settings Management ---

    @staticmethod
    def add_client_to_campaign(campaign_id: int, user_id: int, client_id: int,
                               settings: dict) -> CampaignClientSettingsModel:
        """
        Links a Client to a Campaign with specific settings, adding to session (DOES NOT COMMIT).

        Args:
            campaign_id (int): The campaign ID.
            user_id (int): The user ID (must own the campaign).
            client_id (int): The client ID to link.
            settings (dict): Settings (max_concurrency, forwarding_priority, weight, etc.). Schema validates contents.

        Returns:
            CampaignClientSettingsModel: The newly created settings record (uncommitted).

        Raises:
            ResourceNotFound: If campaign or client not found.
            AuthorizationError: If user doesn't own campaign.
            ConflictError: If client already linked to this campaign.
            ValidationError: For invalid settings values if not caught by schema.
            ServiceError: For database integrity errors or unexpected errors during flush.
        """
        session = db.session
        campaign = session.get(CampaignModel, campaign_id)
        if not campaign:
            raise ResourceNotFound(f"Campaign {campaign_id} not found.")
        if campaign.user_id != user_id:
             current_app.logger.warning(f"User {user_id} attempted to link client to campaign {campaign_id} owned by user {campaign.user_id}.")
             raise AuthorizationError(f"User not authorized for campaign {campaign_id}.")

        if not session.query(ClientModel.id).filter_by(id=client_id).first():
            raise ResourceNotFound(f"Client with ID {client_id} not found.")

        existing_link = session.query(CampaignClientSettingsModel.id).filter_by(
            campaign_id=campaign_id,
            client_id=client_id
        ).first()
        if existing_link:
            raise ConflictError(f"Client {client_id} is already linked to campaign {campaign_id}.")

        required_keys = ['max_concurrency', 'forwarding_priority', 'weight']
        if not all(key in settings for key in required_keys):
            raise ValidationError(f"Missing required settings: {', '.join(required_keys)}")

        try:
            new_setting = CampaignClientSettingsModel(
                campaign_id=campaign_id,
                client_id=client_id,
                max_concurrency=settings['max_concurrency'],
                total_calls_allowed=settings.get('total_calls_allowed'),
                forwarding_priority=settings['forwarding_priority'],
                weight=settings['weight'],
                status=settings.get('status', 'active')
            )
            session.add(new_setting)
            session.flush()
            current_app.logger.info(f"Client {client_id} linked to campaign {campaign_id} in session with setting ID {new_setting.id}.")
            return new_setting
        except IntegrityError as e:
            session.rollback()
            current_app.logger.error(f"DB integrity error linking client {client_id} to campaign {campaign_id}: {e}", exc_info=True)
            raise ServiceError(f"Database integrity error linking client to campaign: {e.orig}")
        except Exception as e:
            session.rollback()
            current_app.logger.error(f"Unexpected error linking client {client_id} to campaign {campaign_id}: {e}", exc_info=True)
            raise ServiceError(f"Failed to add client link to session: {e}")


    @staticmethod
    def update_campaign_client_setting(setting_id: int, user_id: int, campaign_id: int, updates: dict) -> CampaignClientSettingsModel:
        """
        Updates the settings for a specific Campaign-Client link in session (DOES NOT COMMIT).

        Args:
            setting_id (int): The ID of the CampaignClientSettings record.
            user_id (int): The user ID (must own the parent campaign).
            updates (dict): Dictionary of settings to update. Schema validates contents.

        Returns:
            CampaignClientSettingsModel: The updated settings record (uncommitted).

        Raises:
            ResourceNotFound: If setting not found.
            AuthorizationError: If user doesn't own the parent campaign.
            ValidationError: For invalid setting values if not caught by schema.
            ServiceError: For unexpected errors during flush.
        """
        session = db.session
        setting = db.session.get(
            CampaignClientSettingsModel,
            setting_id,
            options=[joinedload(CampaignClientSettingsModel.campaign)] # Eager load campaign for check
        )

        if not setting:
            raise ResourceNotFound(f"Campaign client setting with ID {setting_id} not found.")
        # --- ADDED CHECK ---
        if setting.campaign_id != campaign_id:
            # Log the mismatch clearly
            current_app.logger.warning(f"Attempt to update setting {setting_id} (belongs to campaign {setting.campaign_id}) via wrong campaign URL ({campaign_id}).")
            # Raise ResourceNotFound as the setting wasn't found for *this specific campaign* context
            raise ResourceNotFound(f"Campaign client setting with ID {setting_id} not found for campaign {campaign_id}.")
        # --- END ADDED CHECK ---
        if setting.campaign.user_id != user_id:
            current_app.logger.warning(f"User {user_id} attempted to update setting {setting_id} for campaign owned by user {setting.campaign.user_id}.")
            raise AuthorizationError("User is not authorized to update this campaign client setting.")

        allowed_updates = ['max_concurrency', 'total_calls_allowed', 'current_total_calls',
                           'forwarding_priority', 'weight', 'status']
        updated = False
        try:
            for key, value in updates.items():
                 if key in allowed_updates:
                     setattr(setting, key, value)
                     updated = True

            if updated:
                session.flush()
                current_app.logger.info(f"Campaign client setting ID {setting_id} updated in session.")
            else:
                current_app.logger.info(f"No valid fields provided to update setting ID {setting_id}.")

            return setting
        except IntegrityError as e:
             session.rollback()
             current_app.logger.error(f"DB integrity error updating setting {setting_id}: {e}", exc_info=True)
             raise ServiceError(f"Database integrity error updating setting: {e.orig}")
        except Exception as e:
            session.rollback()
            current_app.logger.error(f"Unexpected error updating setting {setting_id}: {e}", exc_info=True)
            raise ServiceError(f"Failed to update campaign client setting {setting_id}: {e}")


    @staticmethod
    def remove_client_from_campaign(setting_id: int, user_id: int, campaign_id: int) -> bool:
        """
        Marks a Campaign-Client link for deletion in the session (DOES NOT COMMIT).

        Args:
            setting_id (int): The ID of the CampaignClientSettings record to delete.
            user_id (int): The user ID (must own the parent campaign).

        Returns:
            bool: True if marked for deletion successfully.

        Raises:
            ResourceNotFound: If setting not found.
            AuthorizationError: If user doesn't own the parent campaign.
            ServiceError: For unexpected errors during delete/flush.
        """
        session = db.session
        setting = db.session.get(
            CampaignClientSettingsModel,
            setting_id,
            options=[joinedload(CampaignClientSettingsModel.campaign)] # Eager load campaign for check
        )

        if not setting:
            raise ResourceNotFound(f"Campaign client setting with ID {setting_id} not found.")
        # --- ADDED CHECK ---
        if setting.campaign_id != campaign_id:
             current_app.logger.warning(f"Attempt to remove setting {setting_id} (belongs to campaign {setting.campaign_id}) via wrong campaign URL ({campaign_id}).")
             raise ResourceNotFound(f"Campaign client setting with ID {setting_id} not found for campaign {campaign_id}.")
        # --- END ADDED CHECK ---
        if setting.campaign.user_id != user_id:
            current_app.logger.warning(f"User {user_id} attempted to remove setting {setting_id} for campaign owned by user {setting.campaign.user_id}.")
            raise AuthorizationError("User is not authorized to remove this campaign client setting.")

        try:
            session.delete(setting)
            session.flush()
            current_app.logger.info(f"Campaign client setting ID {setting_id} marked for deletion.")
            return True
        except IntegrityError as e:
             session.rollback()
             current_app.logger.error(f"DB integrity error removing setting {setting_id}: {e}", exc_info=True)
             raise ServiceError(f"Failed to stage client link deletion due to DB constraints: {e.orig}")
        except Exception as e:
            session.rollback()
            current_app.logger.error(f"Unexpected error removing setting {setting_id}: {e}", exc_info=True)
            raise ServiceError(f"Failed to mark client link {setting_id} for deletion: {e}")


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
            ResourceNotFound: If campaign not found.
            AuthorizationError: If user is not the campaign owner.
        """
        campaign = db.session.get(CampaignModel, campaign_id)
        if not campaign:
             raise ResourceNotFound(f"Campaign {campaign_id} not found.")
        if campaign.user_id != user_id:
             current_app.logger.warning(f"User {user_id} attempted to get settings for campaign {campaign_id} owned by user {campaign.user_id}.")
             raise AuthorizationError(f"User not authorized for campaign {campaign_id}.")

        return db.session.query(CampaignClientSettingsModel)\
            .filter_by(campaign_id=campaign_id)\
            .options(joinedload(CampaignClientSettingsModel.client))\
            .order_by(CampaignClientSettingsModel.forwarding_priority)\
            .all()