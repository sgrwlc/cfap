# app/extensions.py
# -*- coding: utf-8 -*-
"""
Flask extensions instances and configuration.
Central place to initialize extensions to avoid circular imports.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
import os

# Database ORM: Provides SQLAlchemy integration
db = SQLAlchemy()

# Database Migrations: Handles schema migrations using Alembic
# Explicitly pass the migrations directory relative to the app's root path
# Assuming app root is the parent directory of this file's directory ('app')
# app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # This gets cfap/
# migrations_dir = os.path.join(app_root, 'migrations')
# OR simpler relative path if extensions.py is always in app/
migrations_dir = os.path.join(os.path.dirname(__file__), '..', 'migrations')

migrate = Migrate(directory=migrations_dir)

# Password Hashing: Provides bcrypt hashing capabilities
bcrypt = Bcrypt()

# User Session Management: Handles user login sessions via Flask-Login
login_manager = LoginManager()

# --- Flask-Login Configuration ---

# The name of the view function (endpoint) for the login page.
# If using blueprints, it's typically '<blueprint_name>.<view_function_name>'.
# This matches the `auth_bp = Blueprint('auth_api', __name__)` and `def login()` in auth routes.
login_manager.login_view = 'auth_api.login'

# The message flashed to the user when they try to access a @login_required view without being logged in.
# Requires session flashing to be configured if used in a web UI context.
login_manager.login_message = u"Please log in to access this page."
login_manager.login_message_category = "info" # Bootstrap alert category for flashed messages

# The user loader function tells Flask-Login how to find a specific user object
# given the ID stored in their session cookie.
@login_manager.user_loader
def load_user(user_id):
    """Load user by ID for Flask-Login session management."""
    # Lazy import of UserModel to avoid circular imports during initialization
    from .database.models.user import UserModel
    try:
        # Convert user_id from string (session stores it as string) to int
        user_id_int = int(user_id)
        # Use db.session.get for efficient primary key lookup
        return db.session.get(UserModel, user_id_int)
    except (ValueError, TypeError):
        # Handle cases where user_id is not a valid integer
        return None