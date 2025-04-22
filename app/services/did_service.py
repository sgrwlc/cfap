# app/services/did_service.py
# -*- coding: utf-8 -*-
"""
DID Service
Handles business logic related to DID (Phone Number) management.
Service methods modify the session but DO NOT COMMIT.
"""
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func as sql_func # Added for potential future checks
from flask_sqlalchemy.pagination import Pagination
from flask import current_app # Added for logging

from app.database.models.did import DidModel
from app.database.models.user import UserModel
# Import Campaign models needed for the optional check example
from app.database.models.campaign import CampaignModel, CampaignDidModel
from app.extensions import db
# Import custom exceptions
from app.utils.exceptions import ResourceNotFound, ConflictError, ServiceError, ValidationError, AuthorizationError


class DidService:

    @staticmethod
    def add_did(user_id: int, number: str, description: str | None = None,
                status: str = 'active') -> DidModel:
        """
        Adds a new DID owned by a specific user to the session (DOES NOT COMMIT).

        Args:
            user_id (int): The ID of the user (Call Seller) owning this DID.
            number (str): The phone number in E.164 or other standard format. Schema validates format.
            description (str, optional): A user-friendly description.
            status (str): Initial status ('active' or 'inactive'). Schema validates value.

        Returns:
            DidModel: The newly created DID instance, added to the session.

        Raises:
            ConflictError: If the DID number already exists.
            ValidationError: For invalid input if not caught by schema (e.g., empty number).
            ServiceError: For database integrity errors (like invalid user_id) or unexpected errors during flush.
        """
        # Basic validation (non-redundant)
        if not number:
            raise ValidationError("DID number cannot be empty.")
        # Schema should validate status enum and number format

        # Check uniqueness within the current transaction context
        if db.session.query(DidModel.id).filter_by(number=number).first():
            raise ConflictError(f"DID number '{number}' already exists in the system.")

        new_did = DidModel(
            user_id=user_id,
            number=number,
            description=description,
            status=status
        )
        try:
            db.session.add(new_did)
            db.session.flush() # Flush to catch constraints (like invalid user_id FK) early
            current_app.logger.info(f"DID '{number}' added to session for user ID {user_id}.")
            return new_did
        except IntegrityError as e:
            db.session.rollback()
            current_app.logger.error(f"Database integrity error adding DID '{number}': {e}", exc_info=True)
            if 'violates foreign key constraint "dids_user_id_fkey"' in str(e.orig).lower():
                 raise ServiceError(f"Cannot add DID: User with ID {user_id} does not exist.")
            elif 'unique constraint "ix_dids_number"' in str(e.orig).lower():
                 raise ConflictError(f"DID number '{number}' already exists (constraint violation).")
            else:
                 raise ServiceError(f"Database integrity error adding DID: {e.orig}")
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Unexpected error adding DID '{number}' to session: {e}", exc_info=True)
            raise ServiceError(f"Failed to add DID to session: {e}")


    @staticmethod
    def get_did_by_id(did_id: int, user_id: int | None = None) -> DidModel | None:
        """
        Fetches a DID by its primary key ID, optionally checking ownership.

        Args:
            did_id (int): The ID of the DID.
            user_id (int, optional): If provided, also ensures the DID belongs to this user.

        Returns:
            DidModel or None: The DID model or None if not found (or not owned).
        """
        query = db.session.query(DidModel).filter_by(id=did_id)
        if user_id is not None:
            query = query.filter_by(user_id=user_id)
        return query.one_or_none()


    @staticmethod
    def get_did_by_number(number: str, user_id: int | None = None) -> DidModel | None:
        """
        Fetches a DID by its number string, optionally checking ownership.

        Args:
            number (str): The DID number string.
            user_id (int, optional): If provided, also ensures the DID belongs to this user.

        Returns:
            DidModel or None: The DID model or None if not found (or not owned).
        """
        query = db.session.query(DidModel).filter_by(number=number)
        if user_id is not None:
            query = query.filter_by(user_id=user_id)
        return query.one_or_none()


    @staticmethod
    def get_dids_for_user(user_id: int, page: int = 1, per_page: int = 20,
                          status: str | None = None) -> Pagination:
        """
        Fetches a paginated list of DIDs owned by a specific user.

        Args:
            user_id (int): The ID of the user whose DIDs to fetch.
            page (int): Page number.
            per_page (int): Items per page.
            status (str, optional): Filter by status ('active' or 'inactive').

        Returns:
            Pagination: Flask-SQLAlchemy Pagination object.
        """
        query = db.session.query(DidModel).filter_by(user_id=user_id).order_by(DidModel.number)
        if status and status in ['active', 'inactive']:
            query = query.filter(DidModel.status == status)
        # Schema/Route should validate status value before calling service

        pagination = query.paginate(page=page, per_page=per_page, error_out=False, count=True)
        return pagination


    @staticmethod
    def update_did(did_id: int, user_id: int, **kwargs) -> DidModel:
        """
        Updates a DID's details (description, status) in the session (DOES NOT COMMIT).
        Only the owner can update. Number cannot be changed via this method.

        Args:
            did_id (int): The ID of the DID to update.
            user_id (int): The ID of the user attempting the update (must be the owner).
            **kwargs: Fields to update (e.g., description, status).

        Returns:
            DidModel: The updated DID instance present in the session.

        Raises:
            ResourceNotFound: If DID not found or not owned by user.
            ValidationError: If status is invalid (if not handled by schema).
            ServiceError: For unexpected errors during flush.
        """
        # Use the get method which already incorporates the ownership check if user_id is provided
        did = DidService.get_did_by_id(did_id=did_id, user_id=user_id)

        if not did:
            raise ResourceNotFound(f"DID with ID {did_id} not found or not owned by user {user_id}.")

        allowed_updates = ['description', 'status']
        updated = False
        try:
            for key, value in kwargs.items():
                if key in allowed_updates:
                    # Schema should validate status enum value
                    setattr(did, key, value)
                    updated = True

            if updated:
                db.session.flush() # Flush to catch potential DB constraints early
                current_app.logger.info(f"DID ID {did_id} updated in session by user {user_id}.")
            else:
                 current_app.logger.info(f"No valid fields provided to update DID ID {did_id}.")

            return did # Return the instance from the session

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Unexpected error updating DID {did_id} in session: {e}", exc_info=True)
            raise ServiceError(f"Failed to update DID in session: {e}")


    @staticmethod
    def delete_did(did_id: int, user_id: int) -> bool:
        """
        Marks a DID for deletion in the session (DOES NOT COMMIT).
        Only the owner can delete. Associated campaign links (CampaignDidModel)
        will be cascade deleted by the database relationship setting.

        Args:
            did_id (int): The ID of the DID to delete.
            user_id (int): The ID of the user attempting the deletion (must be the owner).

        Returns:
            bool: True if the DID was marked for deletion in the session.

        Raises:
            ResourceNotFound: If DID not found or not owned by user.
            ConflictError: If business logic prevents deletion (e.g., linked to active campaign).
            ServiceError: For unexpected errors during delete/flush.
        """
        # Use the get method which handles ownership check
        did = DidService.get_did_by_id(did_id=did_id, user_id=user_id)

        if not did:
            raise ResourceNotFound(f"DID with ID {did_id} not found or not owned by user {user_id}.")

        # --- Optional Business logic check: Prevent deletion if DID is actively used? ---
        # Example: Check if linked to any *active* campaign owned by this user.
        # Ensure this block is correctly commented if not active
        # try:
        #     is_linked_to_active_campaign = db.session.query(CampaignDidModel.campaign_id)\
        #         .join(CampaignModel, CampaignDidModel.campaign_id == CampaignModel.id)\
        #         .filter(CampaignDidModel.did_id == did_id)\
        #         .filter(CampaignModel.user_id == user_id) # Ensure campaign is also owned by user
        #         .filter(CampaignModel.status == 'active')\
        #         .limit(1).scalar() is not None # Check if any such link exists
        #
        #     if is_linked_to_active_campaign:
        #          raise ConflictError(f"Cannot delete DID {did_id} as it is currently linked to one or more active campaigns.")
        # except Exception as e:
        #      # Handle potential errors during the check itself
        #      current_app.logger.error(f"Error checking active campaign links for DID {did_id}: {e}", exc_info=True)
        #      raise ServiceError("Could not verify campaign links before deleting DID.")
        # --- End Optional Check ---


        try:
            # Deleting the DID will cascade delete CampaignDidModel records via relationship cascade
            db.session.delete(did)
            db.session.flush() # Flush to potentially catch FK issues early
            current_app.logger.info(f"DID ID {did_id} marked for deletion in session by user {user_id}.")
            return True
        except IntegrityError as e: # Catch integrity errors on flush (less likely with cascade)
            db.session.rollback()
            current_app.logger.error(f"Database integrity error deleting DID {did_id}: {e}", exc_info=True)
            raise ServiceError(f"Failed to stage DID deletion due to DB integrity issues: {e.orig}")
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Unexpected error deleting DID {did_id}: {e}", exc_info=True)
            raise ServiceError(f"Failed to stage DID deletion: {e}")