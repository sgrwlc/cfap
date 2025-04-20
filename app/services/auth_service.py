# -*- coding: utf-8 -*-
"""
Auth Service
Handles user authentication logic (login, potentially logout, token handling if needed).
"""

from app.database.models.user import UserModel
from app.extensions import bcrypt

class AuthService:
    @staticmethod
    def authenticate_user(username, password):
        """
        Authenticates a user based on username and password.

        Args:
            username (str): The user's username.
            password (str): The user's password.

        Returns:
            UserModel or None: The authenticated UserModel instance or None if authentication fails.
        """
        user = UserModel.query.filter_by(username=username).one_or_none()
        if user and user.check_password(password):
            # Additionally check if the user is active or allowed to log in
            if user.status == 'active':
                 return user
            # Optionally handle other statuses (e.g., log a warning for inactive/suspended)
        return None

    # Add other auth-related methods here if needed (e.g., token generation/validation for APIs)