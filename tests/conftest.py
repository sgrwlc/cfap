# tests/conftest.py
# -*- coding: utf-8 -*-
"""
Pytest fixtures for integration tests.

Sets up the Flask application in testing mode, initializes a test database,
provides fixtures for making API requests, managing database sessions per test,
and setting up authenticated clients.
"""

import pytest
import os
import subprocess
import sys
import logging # Use logging instead of print

# --- Add this block ---
# Add the project root directory (cfap/) to the Python path
# This allows imports like 'from app import ...' to work correctly
project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)
    log = logging.getLogger(__name__) # Define log after path adjustment if needed
    log.debug(f"Added project directory to sys.path: {project_dir}")
# --- End block ---

from app import create_app # Import the app factory
from app.extensions import db as _db # Import the db instance from extensions
# Import all models to ensure they are registered with SQLAlchemy metadata
from app.database import models # Use the models package import


# Configure logging for fixtures
log = logging.getLogger(__name__)


# ---- Application Fixtures ----

@pytest.fixture(scope='session')
def app():
    """
    Session-wide test Flask application instance configured for 'testing'.
    Establishes an application context for the session.
    """
    log.info("Setting up session-scoped Flask app for testing...")
    # Force TESTING config regardless of environment variables for safety
    _app = create_app(config_name='testing')

    # Push an application context for the duration of the session setup/teardown
    ctx = _app.app_context()
    ctx.push()
    log.info("Flask app context pushed for session.")

    yield _app # Provide the app instance to other fixtures

    # Teardown the application context
    ctx.pop()
    log.info("Flask app context popped for session.")


@pytest.fixture(scope='function')
def client(app):
    """
    Function-scoped test client for the Flask application.
    Provides methods like client.get(), client.post(), etc.
    """
    # log.debug("Creating function-scoped test client.") # Reduce log noise
    return app.test_client()


# ---- Database Fixtures ----

@pytest.fixture(scope='session')
def db(app):
    """
    Session-wide test database management.
    Creates all tables before the session starts, loads sample data once,
    and drops all tables after the session ends.
    """
    log.info("Setting up session-scoped test database...")
    with app.app_context(): # Ensure context for DB operations
        # --- Setup ---
        log.debug("Dropping existing test database tables (if any)...")
        _db.drop_all() # Clean slate
        log.debug("Creating new test database tables...")
        _db.create_all()
        log.info("Test database tables created.")

        # --- Load Sample Data ---
        sample_data_path = os.path.join(os.path.dirname(__file__), '..', 'sample_data.sql')
        db_uri = app.config.get('SQLALCHEMY_DATABASE_URI')

        if not db_uri:
             log.critical("SQLALCHEMY_DATABASE_URI not found in app config for testing.")
             pytest.fail("SQLALCHEMY_DATABASE_URI not configured for testing.")

        if os.path.exists(sample_data_path):
            log.info(f"Loading sample data from: {sample_data_path}...")
            try:
                # Use psql command via subprocess (ensure psql is in PATH)
                env = os.environ.copy()
                # Execute psql; capture output; check for errors; set timeout
                result = subprocess.run(
                    ['psql', db_uri, '-v', 'ON_ERROR_STOP=1', '-q', '-f', sample_data_path], # Added -q for quiet
                    capture_output=True, text=True, check=True, env=env, timeout=45 # Increased timeout slightly
                )
                log.info("Sample data loaded successfully via psql.")
                # Log stdout/stderr only if there's potential relevant info (e.g., errors despite check=True)
                if result.stdout and 'ERROR' in result.stdout.upper(): log.warning(f"psql stdout: {result.stdout}")
                if result.stderr: log.warning(f"psql stderr: {result.stderr}")

            except FileNotFoundError:
                log.critical("Command 'psql' not found. Ensure PostgreSQL client tools are installed and in PATH.")
                pytest.fail("'psql' command not found.")
            except subprocess.TimeoutExpired:
                 log.critical(f"psql command timed out after 45 seconds loading sample data from {sample_data_path}.")
                 pytest.fail("psql command timed out loading sample data.")
            except subprocess.CalledProcessError as e:
                log.critical(f"Failed to load sample data using psql (Return Code: {e.returncode}). File: {sample_data_path}")
                log.error(f"psql stdout:\n{e.stdout}")
                log.error(f"psql stderr:\n{e.stderr}")
                pytest.fail(f"Failed to load sample data via psql. Check logs. RC: {e.returncode}")
            except Exception as e:
                log.critical(f"An unexpected error occurred during sample data loading: {e}", exc_info=True)
                pytest.fail(f"Unexpected error loading sample data: {e}")
        else:
             log.warning(f"Sample data file not found at {sample_data_path}. Skipping data load.")
        # --- End Sample Data Loading ---

        yield _db # Provide the db extension instance

        # --- Teardown ---
        log.info("Tearing down session-scoped test database...")
        _db.session.remove() # Ensure session is clean before drop
        _db.drop_all()
        log.info("Test database tables dropped.")


@pytest.fixture(scope='function')
def session(app, db):
    """
    Function-scoped database session with automatic rollback.

    Creates a transactional scope around each test function. All database
    operations performed within the test that use this session fixture will be
    rolled back automatically at the end of the test, ensuring test isolation.
    DO NOT explicitly commit within tests using this fixture for setup.
    API calls made via the test client *will* commit as part of app logic testing.
    """
    with app.app_context(): # Ensure context for DB operations
        # Establish connection and begin transaction
        connection = db.engine.connect()
        transaction = connection.begin()
        # Bind the SQLAlchemy session to this transaction
        db.session.configure(bind=connection)
        # Optional: Begin a nested transaction if savepoints are desired (usually not needed)
        # nested_transaction = connection.begin_nested()
        # db.session.begin_nested()

        # log.debug("DB function session transaction started.") # Reduce log noise

        yield db.session # Provide the transaction-bound session to the test

        # --- Teardown ---
        db.session.remove() # Clean up the session object
        transaction.rollback() # Rollback the transaction <<< Key for isolation
        connection.close() # Close the connection
        # log.debug("DB function session transaction rolled back.") # Reduce log noise


# ---- Authentication Fixtures ----
# These fixtures provide logged-in test clients. They create the necessary
# user within the test's transaction if it doesn't exist.

@pytest.fixture(scope='function')
def logged_in_client(client, app, session): # Depends on 'session' fixture for DB ops
    """
    Provides a test client logged in as a standard 'user' (Seller).
    Creates the test user ('pytest_seller') within the test's transaction if needed.
    """
    from app.services.user_service import UserService # Local import
    from app.database.models import UserModel # Local import if needed

    test_user_username = "pytest_seller"
    test_user_email = "pytest@seller.test"
    test_user_pass = "PytestPass123!"

    # Check if user exists within the current transaction
    user = session.query(UserModel).filter_by(username=test_user_username).one_or_none()

    if not user:
         log.debug(f"Creating user '{test_user_username}' for logged_in_client fixture.")
         # Use service (which now only adds to session)
         user = UserService.create_user(
             username=test_user_username,
             email=test_user_email,
             password=test_user_pass,
             role='user',
             status='active'
         )
         # No commit here - session fixture handles rollback
         session.flush() # Flush to get ID if absolutely necessary before login
         log.info(f"Created test user '{test_user_username}' (ID: {user.id}) within test transaction.")
    # else:
    #     log.debug(f"Using existing user '{test_user_username}' from test transaction.")

    # Perform login using the test client
    with client: # Use client context manager for session handling
        res = client.post('/api/auth/login', json={
            'username': test_user_username,
            'password': test_user_pass
        })
        if res.status_code != 200:
             log.error(f"Login failed within logged_in_client fixture! Status: {res.status_code}, Data: {res.data.decode()}")
             pytest.fail("Login failed within logged_in_client fixture.")

        # log.debug(f"Client logged in as '{test_user_username}'.") # Reduce noise
        yield client # Provide the authenticated client


@pytest.fixture(scope='function')
def logged_in_admin_client(client, app, session): # Depends on 'session' fixture
    """
    Provides a test client logged in as an 'admin'.
    Creates the test admin user ('pytest_admin') within the test's transaction if needed.
    """
    from app.services.user_service import UserService # Local import
    from app.database.models import UserModel

    test_admin_username = "pytest_admin"
    test_admin_email = "pytest@admin.test"
    test_admin_pass = "PytestAdminPass123!"

    admin = session.query(UserModel).filter_by(username=test_admin_username).one_or_none()

    if not admin:
        log.debug(f"Creating admin user '{test_admin_username}' for logged_in_admin_client fixture.")
        admin = UserService.create_user(
            username=test_admin_username,
            email=test_admin_email,
            password=test_admin_pass,
            role='admin',
            status='active'
        )
        session.flush()
        log.info(f"Created test admin '{test_admin_username}' (ID: {admin.id}) within test transaction.")
    # else:
    #     log.debug(f"Using existing admin user '{test_admin_username}' from test transaction.")


    with client:
        res = client.post('/api/auth/login', json={
            'username': test_admin_username,
            'password': test_admin_pass
        })
        if res.status_code != 200:
            log.error(f"Login failed within logged_in_admin_client fixture! Status: {res.status_code}, Data: {res.data.decode()}")
            pytest.fail("Login failed within logged_in_admin_client fixture.")

        # log.debug(f"Client logged in as '{test_admin_username}'.") # Reduce noise
        yield client