# -*- coding: utf-8 -*-
"""Defines fixtures for pytest tests."""

import pytest
import os
import subprocess # Import subprocess module
import sys

# Ensure correct app path is recognized if running pytest from root
# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app # Import the app factory
from app.extensions import db as _db # Import the db instance from extensions
# Import models to ensure tables are known to metadata when create_all is called
# and potentially for use in other fixtures
from app.database.models import *


# ---- Application Fixtures ----

@pytest.fixture(scope='session')
def app():
    """
    Session-wide test Flask application.
    Uses 'testing' configuration.
    """
    # Force TESTING config regardless of environment variables for safety
    _app = create_app(config_name='testing')

    # Establish an application context before running tests
    # This makes app and g available to fixtures and tests
    with _app.app_context():
        yield _app


@pytest.fixture(scope='function') # Function scope for clean client state per test
def client(app):
    """
    A test client for the Flask application.
    Provides methods like client.get(), client.post(), etc.
    """
    return app.test_client()


# ---- Database Fixtures ----
# This setup uses a session-scoped DB (tables created/dropped once)
# and loads sample data once per session.
# Test functions use a function-scoped transaction fixture ('session') for isolation.

@pytest.fixture(scope='session')
def db(app):
    """
    Session-wide test database instance.
    Creates tables and loads sample data once per session, drops tables afterwards.
    """
    with app.app_context():
        print("\n--- Setting up session-scoped test DB ---")
        # Drop existing tables (if any from previous failed runs) and create fresh
        _db.drop_all()
        _db.create_all()
        print("--- Test DB tables created ---")

        # --- Load Sample Data After Table Creation ---
        # Construct path relative to conftest.py (assuming conftest.py is in tests/)
        # Adjust if your sample data is elsewhere
        sample_data_path = os.path.join(os.path.dirname(__file__), '..', 'sample_data.sql')
        # Get DB URI from Flask app config (should be TestingConfig's URI)
        db_uri = app.config.get('SQLALCHEMY_DATABASE_URI')

        if not db_uri:
             print("ERROR: SQLALCHEMY_DATABASE_URI not found in app config for sample data loading.")
             pytest.fail("SQLALCHEMY_DATABASE_URI not configured for testing.")

        if os.path.exists(sample_data_path):
            print(f"--- Loading sample data from: {sample_data_path} ---")
            try:
                # Use subprocess to run psql command
                # This assumes 'psql' is in the system's PATH
                # It relies on psql being able to parse the full db_uri directly
                env = os.environ.copy()
                # Avoid exposing password in logs if possible - psql should handle URI securely
                # If password contains special characters requiring separate args: parse uri carefully

                result = subprocess.run(
                    ['psql', db_uri, '-v', 'ON_ERROR_STOP=1', '-f', sample_data_path], # Added -v ON_ERROR_STOP=1
                    capture_output=True, text=True, check=True, env=env, timeout=30 # Added timeout
                )
                print("--- Sample data loaded successfully. psql Output: ---")
                # Only print stdout/stderr if they contain something relevant
                if result.stdout and 'ERROR' not in result.stdout:
                    print(result.stdout)
                if result.stderr:
                     print(f"--- psql stderr (potentially ignorable notices): --- \n{result.stderr}")

            except FileNotFoundError:
                print("ERROR: 'psql' command not found. Make sure PostgreSQL client tools are installed and in your PATH.")
                pytest.fail("'psql' command not found.")
            except subprocess.TimeoutExpired:
                 print("ERROR: psql command timed out loading sample data.")
                 pytest.fail("psql command timed out.")
            except subprocess.CalledProcessError as e:
                print("ERROR: Failed to load sample data using psql.")
                print(f"Command: {' '.join(e.cmd)}") # Log the command safely
                print(f"Return Code: {e.returncode}")
                print(f"stdout:\n{e.stdout}")
                print(f"stderr:\n{e.stderr}")
                pytest.fail("Failed to load sample data via psql. Check errors above.")
            except Exception as e:
                print(f"ERROR: An unexpected error occurred during sample data loading: {e}")
                pytest.fail(f"Unexpected error loading sample data: {e}")
        else:
             print(f"WARNING: Sample data file not found at {sample_data_path}. Skipping data load.")
        # --- End Sample Data Loading ---

        yield _db # Provide the db instance to tests that need it directly

        # Teardown: drop all tables after the test session finishes
        print("\n--- Tearing down session-scoped test DB ---")
        _db.drop_all()
        print("--- Test DB tables dropped ---")


@pytest.fixture(scope='function')
def session(app, db):
    """
    Function-scoped database session with automatic rollback via explicit
    connection and transaction management. Test isolation provider.
    """
    with app.app_context():
        # Get connection from engine
        connection = db.engine.connect()
        # Begin a transaction
        transaction = connection.begin()

        # Use a session bound to this connection
        # db.session is a proxy, configure it to use our connection
        db.session.configure(bind=connection)
        # Start the session scope (optional but good practice)
        # db.session.begin_nested() # Maybe not needed if route commits directly

        # Optional: Reduce print noise
        # print("\n--- DB function session transaction started ---")

        yield db.session # Provide the transaction-bound session

        # Teardown: Rollback the transaction and clean up
        db.session.remove() # Ensure session registry is cleared
        transaction.rollback() # Rollback the main transaction
        connection.close() # Close the connection

        # Optional: Reduce print noise
        # print("\n--- DB function session transaction rolled back ---")

# ---- Authentication Fixtures (Example - Assuming UserService doesn't commit) ----

@pytest.fixture(scope='function')
def logged_in_client(client, app, db, session):
    """
    Provides a test client logged in as a 'user'.
    Creates the user if they don't exist within the test session transaction.
    """
    # Import service locally within fixture to avoid top-level circular dependencies
    from app.services.user_service import UserService
    # UserModel is already imported at the top

    test_user_username = "pytest_seller"
    test_user_email = "pytest@seller.test"
    test_user_pass = "PytestPass123!"

    # Check if user exists in current transaction context
    user = session.query(UserModel).filter_by(username=test_user_username).one_or_none()

    if not user:
         user = UserService.create_user( # This adds to session, doesn't commit
             username=test_user_username,
             email=test_user_email,
             password=test_user_pass,
             role='user',
             status='active'
         )
         # Flush to get ID if needed, but login uses username
         # session.flush()
         print(f"\n--- Created test user '{test_user_username}' (will rollback) for login fixture ---")
    # else:
    #      print(f"\n--- Found existing test user '{test_user_username}' in transaction ---")


    # Use the test client's context manager for login
    with client:
        res = client.post('/api/auth/login', json={
            'username': test_user_username,
            'password': test_user_pass
        })
        # Robust check: ensure login actually succeeded
        if res.status_code != 200:
             print(f"ERROR: Login failed within logged_in_client fixture!")
             print(f"Response status: {res.status_code}")
             print(f"Response data: {res.data}")
             pytest.fail("Login failed within logged_in_client fixture.")

        # print(f"\n--- Logged in client fixture as '{test_user_username}' ---") # Optional noise reduction
        yield client # Provide the client, now with session cookie

    # print(f"\n--- Logged out client fixture ---") # Optional noise reduction


@pytest.fixture(scope='function')
def logged_in_admin_client(client, app, db, session):
    """Provides a test client logged in as an admin."""
    from app.services.user_service import UserService
    # UserModel is already imported at the top

    test_admin_username = "pytest_admin"
    test_admin_email = "pytest@admin.test"
    test_admin_pass = "PytestAdminPass123!"

    admin = session.query(UserModel).filter_by(username=test_admin_username).one_or_none()

    if not admin:
        admin = UserService.create_user(
            username=test_admin_username,
            email=test_admin_email,
            password=test_admin_pass,
            role='admin',
            status='active'
        )
        # session.flush()
        print(f"\n--- Created test admin '{test_admin_username}' (will rollback) for login fixture ---")
    # else:
    #      print(f"\n--- Found existing test admin '{test_admin_username}' in transaction ---")

    with client:
        res = client.post('/api/auth/login', json={
            'username': test_admin_username,
            'password': test_admin_pass
        })
        if res.status_code != 200:
             print(f"ERROR: Login failed within logged_in_admin_client fixture!")
             print(f"Response status: {res.status_code}")
             print(f"Response data: {res.data}")
             pytest.fail("Login failed within logged_in_admin_client fixture.")

        # print(f"\n--- Logged in client fixture as '{test_admin_username}' ---") # Optional noise reduction
        yield client
    # print(f"\n--- Logged out client fixture ---") # Optional noise reduction

# Import sqlalchemy event listener for session fixture enhancement
import sqlalchemy