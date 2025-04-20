# -*- coding: utf-8 -*-
"""
DID Service
Handles business logic related to DID (Phone Number) management,
primarily for Call Sellers.
"""
from sqlalchemy.exc import IntegrityError
from flask_sqlalchemy.pagination import Pagination
from app.database.models.did import DidModel
from app.extensions import db
# from app.utils.exceptions import NotFoundError, ValidationError, AuthorizationError # Example custom exceptions

class DidService:

    @staticmethod
    def add_did(user_id: int, number: str, description: str | None = None, status: str = 'active') -> DidModel:
        """
        Adds a new DID owned by a specific user (Call Seller).

        Args:
            user_id (int): The ID of the user (Call Seller) owning this DID.
            number (str): The phone number in E.164 or other standard format.
            description (str, optional): A user-friendly description.
            status (str): Initial status ('active' or 'inactive').

        Returns:
            DidModel: The newly created DID instance.

        Raises:
            ValueError: If number already exists, status is invalid, or DB error occurs.
            # Consider custom exceptions
        """
        # Basic validation
        if not number:
            raise ValueError("DID number cannot be empty.")
        if status not in ['active', 'inactive']:
            raise ValueError("Invalid status specified.")

        # Check uniqueness
        if DidModel.query.filter_by(number=number).first():
            raise ValueError(f"DID number '{number}' already exists in the system.")
            # raise ConflictError(f"DID number '{number}' already exists.")

        session = db.session
        try:
            new_did = DidModel(
                user_id=user_id,
                number=number,
                description=description,
                status=status
            )
            session.add(new_did)
            session.commit()
            return new_did
        except IntegrityError as e:
             session.rollback()
             # Log error e
             # Could be FK violation if user_id doesn't exist, or unique constraint again
             raise ValueError(f"Database integrity error adding DID '{number}'.")
        except Exception as e:
            session.rollback()
            # Log error e
            raise ValueError(f"Failed to add DID due to an unexpected error: {e}")
            # raise ServiceError(f"Failed to add DID: {e}")


    @staticmethod
    def get_did_by_id(did_id: int, user_id: int | None = None) -> DidModel | None:
        """
        Fetches a DID by its primary key ID.

        Args:
            did_id (int): The ID of the DID.
            user_id (int, optional): If provided, also ensures the DID belongs to this user.

        Returns:
            DidModel or None: The DID model or None if not found (or not owned by user_id if specified).
        """
        query = DidModel.query.filter_by(id=did_id)
        if user_id is not None:
            query = query.filter_by(user_id=user_id)
        return query.one_or_none()

    @staticmethod
    def get_did_by_number(number: str, user_id: int | None = None) -> DidModel | None:
        """
        Fetches a DID by its number string.

        Args:
            number (str): The DID number string.
            user_id (int, optional): If provided, also ensures the DID belongs to this user.

        Returns:
            DidModel or None: The DID model or None if not found (or not owned by user_id if specified).
        """
        query = DidModel.query.filter_by(number=number)
        if user_id is not None:
            query = query.filter_by(user_id=user_id)
        return query.one_or_none()

    @staticmethod
    def get_dids_for_user(user_id: int, page: int = 1, per_page: int = 20, status: str | None = None) -> Pagination:
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
        query = DidModel.query.filter_by(user_id=user_id).order_by(DidModel.number)
        if status and status in ['active', 'inactive']:
            query = query.filter(DidModel.status == status)

        dids = query.paginate(page=page, per_page=per_page, error_out=False)
        return dids


    @staticmethod
    def update_did(did_id: int, user_id: int, **kwargs) -> DidModel:
        """
        Updates a DID's details (description, status). Only the owner can update.
        Number cannot be changed via this method.

        Args:
            did_id (int): The ID of the DID to update.
            user_id (int): The ID of the user attempting the update (must be the owner).
            **kwargs: Fields to update (e.g., description, status).

        Returns:
            DidModel: The updated DID instance.

        Raises:
            ValueError: If DID not found, user is not owner, invalid status, or update fails.
            # Consider NotFoundError, AuthorizationError, ServiceError
        """
        did = DidService.get_did_by_id(did_id)

        if not did:
            raise ValueError(f"DID with ID {did_id} not found.")
            # raise NotFoundError(...)
        if did.user_id != user_id:
             raise ValueError("User is not authorized to update this DID.")
             # raise AuthorizationError(...)

        allowed_updates = ['description', 'status']
        updated = False
        for key, value in kwargs.items():
            if key in allowed_updates:
                if key == 'status' and value not in ['active', 'inactive']:
                    raise ValueError("Invalid status specified.")
                setattr(did, key, value)
                updated = True

        if updated:
            session = db.session
            try:
                session.commit()
                return did
            except Exception as e:
                session.rollback()
                # Log error e
                raise ValueError(f"Failed to update DID due to an unexpected error: {e}")
                # raise ServiceError(...)
        else:
             # No valid fields provided for update
             return did # Return unchanged object


    @staticmethod
    def delete_did(did_id: int, user_id: int) -> bool:
        """
        Deletes a DID. Only the owner can delete.
        Associated campaign links (CampaignDidModel) will be cascade deleted.

        Args:
            did_id (int): The ID of the DID to delete.
            user_id (int): The ID of the user attempting the deletion (must be the owner).

        Returns:
            bool: True if deletion was successful.

        Raises:
            ValueError: If DID not found, user is not owner, or deletion fails.
            # Consider NotFoundError, AuthorizationError, ServiceError
        """
        did = DidService.get_did_by_id(did_id)

        if not did:
            raise ValueError(f"DID with ID {did_id} not found.")
            # raise NotFoundError(...)
        if did.user_id != user_id:
             raise ValueError("User is not authorized to delete this DID.")
             # raise AuthorizationError(...)

        # Add checks? Prevent deletion if part of an 'active' campaign?
        # This might be overly restrictive, as cascade delete on CampaignDidModel handles the links.
        # Let's allow deletion for now.

        session = db.session
        try:
            # Deleting the DID will cascade delete CampaignDidModel records
            session.delete(did)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            # Log error e
            raise ValueError(f"Failed to delete DID due to an unexpected error: {e}")
            # raise ServiceError(...)