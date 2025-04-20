# -*- coding: utf-8 -*-
"""Flask extensions instances."""

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_bcrypt import Bcrypt
from flask_login import LoginManager

# Database ORM
db = SQLAlchemy()

# Database Migrations
migrate = Migrate()

# Password Hashing
bcrypt = Bcrypt()

# User Session Management
login_manager = LoginManager()

# Configure Flask-Login settings
login_manager.login_view = 'api.auth_login' # Adjust if your auth blueprint/route changes
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info' # For flashing messages if used with web UI

# Define the user loader function - This will be implemented properly later
# when the UserModel is defined. For now, it references the function name.
# It tells Flask-Login how to load a user object given the ID stored in the session.
@login_manager.user_loader
def load_user(user_id):
    """Load user by ID."""
    # Import needs to be lazy to avoid circular imports
    from .database.models.user import UserModel
    # Query the database for the user by primary key
    # Use .one_or_none() for robustness, though .get() is common too
    return UserModel.query.get(int(user_id))