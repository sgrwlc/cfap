# app/services/user_service.py
# -*- coding: utf-8 -*-
"""
User Service
Handles business logic related to user management (CRUD operations, etc.).
Service methods modify the session but DO NOT COMMIT.
"""
from sqlalchemy.exc import IntegrityError
from flask import current_app # Added for logging
from flask_sqlalchemy.pagination import Pagination # Import for type hint

from app.database.models.user import UserModel
from app.extensions import db
# Import custom exceptions
from app.utils.exceptions import (
    ResourceNotFound,
    ConflictError,
    ServiceError,
    ValidationError,
    AuthorizationError
)

class UserService:

    @staticmethod
    def create_user(username: str, email: str, password: str, role: str = 'user',
                    status: str = 'active', full_name: str | None = None,
                    company_name: str | None = None) -> UserModel:
        """
        Adds a new user instance to the session (DOES NOT COMMIT).

        Args:
            username (str): User's username.
            email (str): User's email.
            password (str): User's plaintext password.
            role (str): User role ('admin', 'staff', 'user'). Schema validates value.
            status (str): Initial user status. Schema validates value.
            full_name (str, optional): User's full name.
            company_name (str, optional): User's company name.

        Returns:
            UserModel: The newly created user instance, added to the session.

        Raises:
            ConflictError: If username or email already exists.
            ValidationError: If username, email, or password is empty.
            ServiceError: If a database or unexpected error occurs during flush.
        """
        # Basic validation (non-redundant checks like emptiness if schema doesn't enforce minLength)
        if not username: raise ValidationError("Username cannot be empty.")
        if not email: raise ValidationError("Email cannot be empty.")
        if not password: raise ValidationError("Password cannot be empty.") # Added password check
        # Schema should handle role/status value checks

        # Check uniqueness within the current transaction context
        if db.session.query(UserModel.id).filter_by(username=username).first():
            raise ConflictError(f"Username '{username}' already exists.")
        if db.session.query(UserModel.id).filter_by(email=email).first():
            raise ConflictError(f"Email '{email}' already exists.")

        new_user = UserModel(
            username=username,
            email=email,
            password=password, # The __init__ method handles hashing
            role=role,
            status=status,
            full_name=full_name,
            company_name=company_name
        )
        try:
            db.session.add(new_user)
            db.session.flush() # Flush to catch potential DB constraints early and get ID
            current_app.logger.info(f"User '{username}' added to session with ID {new_user.id}.")
            return new_user
        except IntegrityError as e:
            db.session.rollback() # Rollback on integrity error during flush
            current_app.logger.error(f"Database integrity error creating user '{username}': {e}", exc_info=True)
            # Could try to determine if it was a constraint violation missed by initial checks
            raise ConflictError(f"Database integrity error creating user: {e.orig}")
        except Exception as e:
            db.session.rollback() # Rollback on any other error during add/flush
            current_app.logger.error(f"Unexpected error adding user '{username}' to session: {e}", exc_info=True)
            raise ServiceError(f"Failed to add user to session: {e}")


    @staticmethod
    def get_user_by_id(user_id: int) -> UserModel | None:
        """Fetches a user by their ID using the current session."""
        return db.session.get(UserModel, user_id) # Returns None if not found


    @staticmethod
    def get_user_by_username(username: str) -> UserModel | None:
        """Fetches a user by their username using the current session."""
        return db.session.query(UserModel).filter_by(username=username).one_or_none()


    @staticmethod
    def get_all_users(page: int = 1, per_page: int = 20) -> Pagination:
        """Fetches a paginated list of all users using the current session."""
        query = db.session.query(UserModel).order_by(UserModel.username)
        pagination = query.paginate(page=page, per_page=per_page, error_out=False, count=True)
        return pagination


    @staticmethod
    def update_user(user_id: int, **kwargs) -> UserModel:
        """
        Updates a user's details in the session (DOES NOT COMMIT).
        Password should be handled separately via change_password.

        Args:
            user_id (int): The ID of the user to update.
            **kwargs: Fields to update (e.g., email, role, status, full_name, company_name).

        Returns:
            UserModel: The updated user instance present in the session.

        Raises:
            ResourceNotFound: If the user with user_id is not found.
            ConflictError: If the updated email conflicts with another user.
            ValidationError: If email is empty or role/status invalid (if not schema checked).
            ServiceError: If a database or unexpected error occurs during flush.
        """
        user = db.session.get(UserModel, user_id)
        if not user:
            raise ResourceNotFound(f"User with ID {user_id} not found.")

        allowed_updates = ['email', 'role', 'status', 'full_name', 'company_name']
        updated = False
        try:
            for key, value in kwargs.items():
                if key in allowed_updates:
                    # Validation: Schema should handle role/status values. Check email uniqueness.
                    if key == 'email' and value != user.email:
                         if not value: raise ValidationError("Email cannot be empty.")
                         existing = db.session.query(UserModel.id).filter(
                             UserModel.id != user_id, UserModel.email == value
                         ).first()
                         if existing:
                             raise ConflictError(f"Email '{value}' is already in use.")
                    # Rely on schema for role/status enum validation

                    setattr(user, key, value)
                    updated = True

            if updated:
                db.session.flush() # Flush to check constraints early
                current_app.logger.info(f"User ID {user_id} updated in session.")
            else:
                current_app.logger.info(f"No valid fields provided to update user ID {user_id}.")

            return user # Return instance from session

        # --- Catch specific exceptions that can occur during the process ---
        except ConflictError as e: # Catch the specific ConflictError raised earlier
            # Don't rollback here, let the route handler do it
            current_app.logger.warning(f"Conflict error during user update flush for ID {user_id}: {e}")
            raise e # Re-raise the original ConflictError
        except IntegrityError as e: # Catch DB constraint errors during flush
            db.session.rollback() # Rollback mandatory on IntegrityError
            current_app.logger.error(f"Database integrity error updating user {user_id}: {e}", exc_info=True)
            # Determine if it was the unique email constraint again
            if 'unique constraint "ix_users_email"' in str(e.orig).lower():
                raise ConflictError(f"Email conflict during database update: {e.orig}")
            else:
                raise ServiceError(f"Database integrity error updating user: {e.orig}")
        except Exception as e: # Catch other unexpected errors during flush/logic
            db.session.rollback()
            current_app.logger.error(f"Unexpected error updating user {user_id} in session: {e}", exc_info=True)
            # Avoid re-raising known types as ServiceError if already caught
            if isinstance(e, (ResourceNotFound, AuthorizationError, ValidationError)):
                raise e
            raise ServiceError(f"Failed to update user in session: {e}")


    @staticmethod
    def change_password(user_id: int, new_password: str) -> bool:
        """
        Changes a user's password hash in the session (DOES NOT COMMIT).

        Args:
            user_id (int): The ID of the user whose password to change.
            new_password (str): The new plaintext password. Schema validates length.

        Returns:
            bool: True if the password was set on the user object in the session.

        Raises:
            ResourceNotFound: If the user with user_id is not found.
            ValidationError: If the new password is empty (should be caught by schema).
            ServiceError: If an unexpected error occurs.
        """
        user = db.session.get(UserModel, user_id)
        if not user:
            raise ResourceNotFound(f"User with ID {user_id} not found.")

        # Basic check, though schema should enforce min length
        if not new_password:
            raise ValidationError("New password cannot be empty.")

        try:
            user.set_password(new_password)
            db.session.flush() # Flush to ensure change is reflected within transaction context
            current_app.logger.info(f"Password hash updated in session for user ID {user_id}.")
            return True
        except Exception as e:
            db.session.rollback() # Rollback on error during set/flush
            current_app.logger.error(f"Unexpected error changing password for user {user_id}: {e}", exc_info=True)
            raise ServiceError(f"Failed to stage password change: {e}")


    @staticmethod
    def delete_user(user_id: int) -> bool:
        """
        Marks a user for deletion in the session (DOES NOT COMMIT).
        Associated data (DIDs, Campaigns) should be handled by DB cascade.

        Args:
            user_id (int): The ID of the user to delete.

        Returns:
            bool: True if the user was marked for deletion in the session.

        Raises:
            ResourceNotFound: If the user with user_id is not found.
            AuthorizationError: If trying to delete the last admin (example check).
            ServiceError: If an unexpected error occurs during delete/flush.
        """
        user = db.session.get(UserModel, user_id)
        if not user:
            raise ResourceNotFound(f"User with ID {user_id} not found.")

        # Example business logic check: prevent deleting the last admin
        if user.role == 'admin':
             # Use SQLAlchemy core function for count
             from sqlalchemy import func as sql_func
             admin_count = db.session.query(sql_func.count(UserModel.id)).filter_by(role='admin').scalar()
             if admin_count is not None and admin_count <= 1:
                 raise AuthorizationError("Cannot delete the last administrator account.")

        try:
            db.session.delete(user)
            db.session.flush() # Flush to potentially catch FK issues early if cascade isn't perfect
            current_app.logger.info(f"User ID {user_id} marked for deletion in session.")
            return True
        except IntegrityError as e: # Catch specific constraint violations on delete/flush if cascade fails
            db.session.rollback()
            current_app.logger.error(f"Database integrity error deleting user {user_id}: {e}", exc_info=True)
            raise ServiceError(f"Failed to stage user deletion due to DB constraints: {e.orig}")
        except Exception as e:
            db.session.rollback() # Rollback on error during delete/flush
            current_app.logger.error(f"Unexpected error deleting user {user_id}: {e}", exc_info=True)
            raise ServiceError(f"Failed to stage user deletion: {e}")