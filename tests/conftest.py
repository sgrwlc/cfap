# tests/conftest.py
# -*- coding: utf-8 -*-
"""Defines fixtures for pytest tests."""

import pytest
import os
import subprocess
import sys
import logging # Use logging instead of print
import sqlalchemy # Keep event import

# Ensure correct app path is recognized if running pytest from root
# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app # Import the app factory
from app.extensions import db as _db # Import the db instance from extensions
# Import models to ensure tables are known to metadata when create_all is called
# and for direct use in fixtures if necessary (e.g., querying fixture users)
from app.database.models import *
# Import services for setting up test data (e.g., creating users for login fixtures)
from app.services.user_service import UserService

# Configure basic logging for test setup/teardown messages
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


# ---- Application Fixtures ----

@pytest.fixture(scope='session')
def app():
    """
    Session-wide test Flask application instance.
    Uses 'testing' configuration.
    """
    log.info("Creating session-scoped test Flask app instance...")
    _app = create_app(config_name='testing')

    # Establish an application context for the duration of the session setup
    with _app.app_context():
        yield _app
    log.info("Test Flask app instance session teardown.")


@pytest.fixture(scope='function')
def client(app):
    """
    Function-scoped Flask test client.
    Provides methods like client.get(), client.post(), etc.
    """
    # log.debug("Creating function-scoped test client.") # Too noisy maybe
    return app.test_client()


# ---- Database Fixtures ----

@pytest.fixture(scope='session')
def db(app):
    """
    Session-wide test database instance.
    Creates tables once per session, loads sample data, drops tables afterwards.
    Requires the 'app' fixture.
    """
    with app.app_context():
        log.info("Setting up session-scoped test database...")
        # Drop existing tables (if any from previous failed runs) and create fresh
        _db.drop_all()
        _db.create_all()
        log.info("Test DB tables created.")

        # --- Load Sample Data ---
        sample_data_path = os.path.join(os.path.dirname(__file__), '..', 'sample_data.sql')
        db_uri = app.config.get('SQLALCHEMY_DATABASE_URI')

        if not db_uri:
             log.error("SQLALCHEMY_DATABASE_URI not found in app config for sample data loading.")
             pytest.fail("SQLALCHEMY_DATABASE_URI not configured for testing.")

        if os.path.exists(sample_data_path):
            log.info(f"Loading sample data from: {sample_data_path}...")
            try:
                # Use subprocess to run psql command
                # Assumes 'psql' is in the system's PATH
                env = os.environ.copy()
                result = subprocess.run(
                    ['psql', db_uri, '-v', 'ON_ERROR_STOP=1', '-q', '-f', sample_data_path], # Added -q for quiet
                    capture_output=True, text=True, check=True, env=env, timeout=30
                )
                log.info("Sample data loaded successfully via psql.")
                # Log stderr only if it contains errors/warnings (psql notices often go to stderr)
                if result.stderr and ('ERROR' in result.stderr or 'WARNING' in result.stderr):
                     log.warning(f"psql stderr during sample data load:\n{result.stderr}")

            except FileNotFoundError:
                log.error("'psql' command not found. Make sure PostgreSQL client tools are installed and in your PATH.")
                pytest.fail("'psql' command not found.")
            except subprocess.TimeoutExpired:
                 log.error("psql command timed out loading sample data.")
                 pytest.fail("psql command timed out.")
            except subprocess.CalledProcessError as e:
                log.error("Failed to load sample data using psql.")
                log.error(f"Command: {' '.join(e.cmd)}")
                log.error(f"Return Code: {e.returncode}")
                log.error(f"stdout:\n{e.stdout}")
                log.error(f"stderr:\n{e.stderr}")
                pytest.fail("Failed to load sample data via psql. Check errors above.")
            except Exception as e:
                log.error(f"An unexpected error occurred during sample data loading: {e}", exc_info=True)
                pytest.fail(f"Unexpected error loading sample data: {e}")
        else:
             log.warning(f"Sample data file not found at {sample_data_path}. Skipping data load.")
        # --- End Sample Data Loading ---

        yield _db # Provide the db instance

        # Teardown: drop all tables after the test session finishes
        log.info("Tearing down session-scoped test database...")
        _db.drop_all()
        log.info("Test DB tables dropped.")


@pytest.fixture(scope='function')
def session(app, db):
    """
    Function-scoped database session with automatic rollback. Provides test isolation.
    Uses SQLAlchemy's event system for nested transaction behavior.
    """
    with app.app_context():
        connection = _db.engine.connect()
        transaction = connection.begin()
        # Bind the Flask-SQLAlchemy session proxy to the connection
        options = dict(bind=connection, binds={})
        sess = _db.create_scoped_session(options=options)
        # Establish SAVEPOINT for test isolation
        sess.begin_nested()

        # Event listener to rollback nested transaction (SAVEPOINT) automatically after test
        @sqlalchemy.event.listens_for(sess(), 'after_transaction_end')
        def restart_savepoint(session, transaction):
            if transaction.nested and not transaction._parent.nested:
                session.expire_all()
                session.begin_nested()

        # Yield the session configured for the test
        # log.debug("DB function session (nested tx) started.") # Too noisy
        yield sess

        # Teardown: Remove session, rollback main transaction, close connection
        sess.remove()
        transaction.rollback()
        connection.close()
        # log.debug("DB function session (nested tx) rolled back.") # Too noisy


# ---- Authentication Fixtures ----

@pytest.fixture(scope='function')
def logged_in_client(client, app, session): # Depends on function-scoped session
    """
    Provides a test client logged in as a standard 'user' (seller).
    Creates the test user within the function-scoped transaction if not present.
    """
    test_user_username = "pytest_seller"
    test_user_email = "pytest@seller.test"
    test_user_pass = "PytestPass123!"

    # Check if user exists in current transaction context
    user = session.query(UserModel).filter_by(username=test_user_username).one_or_none()

    if not user:
         # Use service - it adds to session but does not commit
         user = UserService.create_user(
             username=test_user_username,
             email=test_user_email,
             password=test_user_pass,
             role='user',
             status='active'
         )
         # Flush within the fixture's transaction to ensure user exists for login attempt
         try:
             session.flush()
             log.info(f"Created test user '{test_user_username}' (will rollback) for login fixture.")
         except Exception as e:
             log.error(f"Failed to flush test user '{test_user_username}' in fixture: {e}", exc_info=True)
             session.rollback() # Rollback immediately on fixture setup failure
             pytest.fail(f"Fixture setup failed: Could not flush user {test_user_username}")

    # Use the test client's context manager for login
    with client:
        res = client.post('/api/auth/login', json={
            'username': test_user_username,
            'password': test_user_pass
        })
        if res.status_code != 200:
             log.error(f"Login failed within logged_in_client fixture! Status: {res.status_code}, Data: {res.data}")
             pytest.fail("Login failed within logged_in_client fixture.")

        # log.debug(f"Logged in client fixture as '{test_user_username}'.")
        yield client # Provide the client, now with session cookie

    # log.debug(f"Logged out client fixture (end of context).")


@pytest.fixture(scope='function')
def logged_in_admin_client(client, app, session): # Depends on function-scoped session
    """
    Provides a test client logged in as an 'admin'.
    Creates the test admin user within the function-scoped transaction if not present.
    """
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
        try:
            session.flush()
            log.info(f"Created test admin '{test_admin_username}' (will rollback) for login fixture.")
        except Exception as e:
            log.error(f"Failed to flush test admin '{test_admin_username}' in fixture: {e}", exc_info=True)
            session.rollback()
            pytest.fail(f"Fixture setup failed: Could not flush admin {test_admin_username}")

    with client:
        res = client.post('/api/auth/login', json={
            'username': test_admin_username,
            'password': test_admin_pass
        })
        if res.status_code != 200:
             log.error(f"Login failed within logged_in_admin_client fixture! Status: {res.status_code}, Data: {res.data}")
             pytest.fail("Login failed within logged_in_admin_client fixture.")

        # log.debug(f"Logged in client fixture as '{test_admin_username}'.")
        yield client
    # log.debug(f"Logged out admin client fixture (end of context).")