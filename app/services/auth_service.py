# app/services/auth_service.py
# -*- coding: utf-8 -*-
"""
Auth Service
Handles user authentication logic.
"""
from flask import current_app # Added for logging

from app.database.models.user import UserModel
from app.extensions import bcrypt # Bcrypt is used by user.check_password
# Import custom exception
from app.utils.exceptions import AuthenticationError


class AuthService:
    @staticmethod
    def authenticate_user(username, password):
        """
        Authenticates a user based on username and password.

        Args:
            username (str): The user's username.
            password (str): The user's password.

        Returns:
            UserModel: The authenticated and active UserModel instance.

        Raises:
            AuthenticationError: If authentication fails due to invalid credentials,
                                 non-existent user, or inactive account status.
        """
        user = UserModel.query.filter_by(username=username).one_or_none()

        if not user:
            current_app.logger.warning(f"Authentication attempt failed: User '{username}' not found.")
            raise AuthenticationError("Invalid username or password.") # Use generic message for security

        if not user.check_password(password):
            current_app.logger.warning(f"Authentication attempt failed: Invalid password for user '{username}'.")
            raise AuthenticationError("Invalid username or password.") # Use generic message for security

        # Check user status *after* validating password
        if not user.is_active: # Uses the property from UserModel
            current_app.logger.warning(f"Authentication attempt failed: User '{username}' is inactive (status: {user.status}).")
            # Provide a slightly more specific message internally if needed, but API response might still be generic
            raise AuthenticationError("User account is inactive.")

        # If all checks pass
        current_app.logger.info(f"User '{username}' authenticated successfully.")
        return user

    # Add other auth-related methods here if needed (e.g., token generation/validation)