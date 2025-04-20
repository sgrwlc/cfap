# -*- coding: utf-8 -*-
"""
User Service
Handles business logic related to user management (CRUD operations, etc.).
"""
from app.database.models.user import UserModel
from app.extensions import db
# from app.utils.exceptions import NotFoundError, ValidationError # Example custom exceptions

class UserService:

    @staticmethod
    def create_user(username, email, password, role='user', status='active', full_name=None, company_name=None):
        """
        Creates a new user.

        Args:
            username (str): User's username.
            email (str): User's email.
            password (str): User's plaintext password.
            role (str): User role ('admin', 'staff', 'user').
            status (str): Initial user status.
            full_name (str, optional): User's full name.
            company_name (str, optional): User's company name.

        Returns:
            UserModel: The newly created user instance.

        Raises:
            ValueError: If username or email already exists or role/status invalid (could use custom exceptions).
        """
        # Basic validation (more can be added)
        if UserModel.query.filter_by(username=username).first():
            raise ValueError(f"Username '{username}' already exists.")
        if UserModel.query.filter_by(email=email).first():
            raise ValueError(f"Email '{email}' already exists.")
        if role not in ['admin', 'staff', 'user']:
             raise ValueError("Invalid role specified.")
        if status not in ['active', 'inactive', 'pending_approval', 'suspended']:
             raise ValueError("Invalid status specified.")

        new_user = UserModel(
            username=username,
            email=email,
            password=password, # The __init__ method handles hashing
            role=role,
            status=status,
            full_name=full_name,
            company_name=company_name
        )
        db.session.add(new_user)
        # Commit should ideally happen at the end of the request cycle (in the route handler)
        # But for simplicity in the service for now:
        try:
             db.session.commit()
             return new_user
        except Exception as e:
             db.session.rollback()
             # Log the exception e
             raise ValueError("Failed to create user due to database error.") # Or re-raise

    @staticmethod
    def get_user_by_id(user_id):
        """Fetches a user by their ID."""
        return UserModel.query.get(user_id) # Returns None if not found

    @staticmethod
    def get_user_by_username(username):
        """Fetches a user by their username."""
        return UserModel.query.filter_by(username=username).one_or_none()

    @staticmethod
    def get_all_users(page=1, per_page=20):
        """Fetches a paginated list of all users."""
        # Example pagination
        return UserModel.query.paginate(page=page, per_page=per_page, error_out=False)

    @staticmethod
    def update_user(user_id, **kwargs):
        """
        Updates a user's details. Password should be handled separately.

        Args:
            user_id (int): The ID of the user to update.
            **kwargs: Fields to update (e.g., email, role, status, full_name, company_name).

        Returns:
            UserModel: The updated user instance.

        Raises:
            ValueError: If user not found or update fails.
        """
        user = UserService.get_user_by_id(user_id)
        if not user:
            raise ValueError(f"User with ID {user_id} not found.")

        allowed_updates = ['email', 'role', 'status', 'full_name', 'company_name']
        updated = False
        for key, value in kwargs.items():
            if key in allowed_updates:
                # Add validation for email uniqueness, role/status values if needed
                if key == 'email' and value != user.email:
                    if UserModel.query.filter(UserModel.id != user_id, UserModel.email == value).first():
                         raise ValueError(f"Email '{value}' is already in use.")
                if key == 'role' and value not in ['admin', 'staff', 'user']:
                     raise ValueError("Invalid role specified.")
                if key == 'status' and value not in ['active', 'inactive', 'pending_approval', 'suspended']:
                     raise ValueError("Invalid status specified.")

                setattr(user, key, value)
                updated = True

        if updated:
            try:
                db.session.commit()
                return user
            except Exception as e:
                db.session.rollback()
                # Log the exception e
                raise ValueError("Failed to update user due to database error.")
        else:
            # No valid fields were provided for update
             return user # Or raise an error/return None?


    @staticmethod
    def change_password(user_id, new_password):
        """Changes a user's password."""
        user = UserService.get_user_by_id(user_id)
        if not user:
            raise ValueError(f"User with ID {user_id} not found.")

        user.set_password(new_password)
        try:
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            # Log exception
            raise ValueError("Failed to change password due to database error.")


    @staticmethod
    def delete_user(user_id):
        """
        Deletes a user. Handle cascade deletes appropriately.

        Args:
            user_id (int): The ID of the user to delete.

        Returns:
            bool: True if deletion was successful.

        Raises:
            ValueError: If user not found or deletion fails.
        """
        user = UserService.get_user_by_id(user_id)
        if not user:
            raise ValueError(f"User with ID {user_id} not found.")

        # Consider adding checks here, e.g., prevent deleting the last admin user?

        try:
            db.session.delete(user)
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            # Log exception e
            raise ValueError("Failed to delete user due to database error.")