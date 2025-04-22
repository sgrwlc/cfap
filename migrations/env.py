# migrations/env.py
import os
import sys
from logging.config import fileConfig

from flask import current_app
from alembic import context
from sqlalchemy import pool # Keep pool import if needed by engine_from_config

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- Flask-Migrate Integration ---
# Add project root to sys.path - IMPORTANT
# Assumes migrations folder is one level down from project root (cfap/)
project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_dir not in sys.path:
     sys.path.insert(0, project_dir)

# Import db instance from extensions - This is crucial
try:
    from app.extensions import db
    # Import models AFTER potentially setting up sys.path
    from app.database import models # noqa Ensures models are registered with metadata
except ImportError as e:
    print(f"Error importing app components in migrations/env.py: {e}")
    print("Check Flask app structure and sys.path.")
    sys.exit(1)

# Use the metadata from the Flask-SQLAlchemy db instance
target_metadata = db.metadata

# --- Alembic Configuration ---

def get_engine_url():
    """Retrieve database URL from Flask config."""
    try:
        return current_app.config['SQLALCHEMY_DATABASE_URI']
    except NameError: # Handle running alembic command outside app context
        # Fallback to alembic.ini if needed, though flask db commands provide context
        return config.get_main_option("sqlalchemy.url")

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_engine_url()
    if not url:
        raise ValueError("Database URL not found. Set SQLALCHEMY_DATABASE_URI in config.")

    context.configure(
        url=url.replace('%', '%%'), # Ensure correct escaping for URL
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    # Flask-Migrate sets up the engine connection from the app context
    # Use the engine directly from the imported `db` instance
    connectable = db.engine

    with connectable.connect() as connection:
        # Pass the Flask app's extensions['migrate'].configure_args if needed
        # conf_args = current_app.extensions['migrate'].configure_args or {}
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            # Use render_as_batch from Flask-Migrate context arguments if available
            render_as_batch=context.get_x_argument(as_dictionary=True).get('batch', False)
            # **conf_args # Pass other Flask-Migrate specific args
        )

        with context.begin_transaction():
            context.run_migrations()

# Determine mode and run migrations
if context.is_offline_mode():
    run_migrations_offline()
else:
    # Ensure app context is available (Flask-Migrate CLI commands usually provide this)
    if current_app:
        run_migrations_online()
    else:
        print("Error: Cannot run online migrations without Flask application context.")
        print("Use 'flask db upgrade' or ensure the Flask app is configured.")
        sys.exit(1)