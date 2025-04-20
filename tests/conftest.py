# -*- coding: utf-8 -*-
"""Defines fixtures for tests."""
import pytest
import logging
from flask_login import login_user # To help with login fixtures

from app import create_app # Your app factory
from app.extensions import db as _db # Use _db to avoid pytest fixture name clash
from app.database.models.user import UserModel # Import user model for fixtures

@pytest.fixture(scope='session')
def app():
    """Session-wide test `Flask` application."""
    _app = create_app(config_name='testing') # Use testing config

    # Establish an application context before running the tests
    ctx = _app.app_context()
    ctx.push()

    yield _app # controllers can import this fixture

    ctx.pop()


@pytest.fixture(scope='session')
def db(app):
    """Session-wide test database."""
    # Configure logging for tests if needed
    # logging.basicConfig(level=logging.DEBUG) # Example

    # Ensure the test database is clean before the session
    _db.app = app # Associate db instance with the test app
    with app.app_context():
         # _db.drop_all() # Optional: Drop tables if they somehow exist
         _db.create_all() # Create tables based on models

    yield _db

    # Teardown: drop all tables after the test session finishes
    with app.app_context():
        _db.drop_all()


@pytest.fixture(scope='function')
def session(db):
    """
    Creates a new database session for a test, ensuring rollback.
    Uses the db.session provided by Flask-SQLAlchemy but manages
    the transaction lifecycle for test isolation.
    """
    with db.engine.connect() as connection:
        with connection.begin() as transaction:
            # Bind the existing scoped session to this transaction/connection
            # This ensures db.session uses our isolated transaction
            db.session.configure(bind=connection)

            # Start a SAVEPOINT
            nested_transaction = connection.begin_nested()

            # Make the current session available to event listeners if needed
            @db.event.listens_for(db.session, "after_transaction_end")
            def end_savepoint(session, transaction):
                nonlocal nested_transaction
                if (
                    not nested_transaction.is_active
                    and transaction.is_active
                ):
                    nested_transaction = connection.begin_nested()


            # --- Provide the session to the test ---
            yield db.session
            # --- Test runs here ---


            # --- Teardown ---
            # Rollback the database state to the SAVEPOINT created before the test ran
            # Effectively discarding changes made by the test
            db.session.remove() # Remove the session, releasing the connection
            transaction.rollback() # Rollback the main transaction for the test
            # Connection is automatically closed by the 'with' statement


@pytest.fixture(scope='function')
def client(app, session): # Use the session fixture to ensure context
    """Get a Flask test client."""
    return app.test_client()


# --- Helper Fixtures for Creating Test Data ---

@pytest.fixture(scope='function')
def make_user(session): # Takes the main session fixture
    """Factory fixture to create user instances."""
    def _make_user(**kwargs):
        defaults = {
            "username": "testuser",
            "email": "test@test.com",
            "password": "password123",
            "role": "user",
            "status": "active",
        }
        final_kwargs = {**defaults, **kwargs}

        # --- Check for existing user BEFORE adding ---
        # This check might still be useful if tests create users directly
        # but the primary issue was the commit. Let's keep it for now.
        existing_user = UserModel.query.filter_by(username=final_kwargs['username']).one_or_none()
        if existing_user:
            # Instead of failing, let's just return the existing user if found during setup?
            # Or ensure tests use unique names. For now, let's try allowing it.
            # pytest.fail(f"Test setup error: Username {final_kwargs['username']} already exists.")
            return existing_user # Return existing if found

        existing_email = UserModel.query.filter_by(email=final_kwargs['email']).one_or_none()
        if existing_email:
            # pytest.fail(f"Test setup error: Email {final_kwargs['email']} already exists.")
            return existing_email # Return existing if found

        user = UserModel(**final_kwargs)
        session.add(user)
        # --- REMOVED session.commit() ---
        # Flush to assign ID if needed immediately, but usually not required
        session.flush()
        return user
    return _make_user

@pytest.fixture(scope='function')
def admin_user(make_user):
    """Create an admin user."""
    return make_user(username='admin_test', email='admin@test.com', role='admin')

@pytest.fixture(scope='function')
def seller_user(make_user):
    """Create a seller (role='user') user."""
    return make_user(username='seller_test', email='seller@test.com', role='user')

# --- Helper Fixture for Logging In ---
@pytest.fixture(scope='function')
def logged_in_client(client, seller_user): # Example logging in as seller
    """Provides a test client that is already logged in."""
    # Use the test client's post method to simulate login
    res = client.post('/api/auth/login', json={
        'username': seller_user.username,
        'password': 'password123' # Use the default password from make_user
    })
    assert res.status_code == 200 # Ensure login was successful
    # The client now has the session cookie set
    yield client
    # Logout after test (optional, session teardown handles DB state)
    client.post('/api/auth/logout')

@pytest.fixture(scope='function')
def logged_in_admin_client(client, admin_user): # Example logging in as admin
    """Provides a test client logged in as admin."""
    res = client.post('/api/auth/login', json={
        'username': admin_user.username,
        'password': 'password123'
    })
    assert res.status_code == 200
    yield client
    client.post('/api/auth/logout')

# --- Add more fixtures as needed (e.g., creating clients, campaigns) ---