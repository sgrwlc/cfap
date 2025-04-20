# tests/conftest.py
import pytest
from app import create_app
from app.extensions import db as _db # Use alias to avoid name clash
from app.config import TestingConfig

@pytest.fixture(scope='session')
def app():
    """Session-wide test Flask application."""
    _app = create_app(config_name='testing') # Use TestingConfig

    # Establish an application context before running tests
    with _app.app_context():
        yield _app

# Fixture for the Flask test client (useful for API tests later)
# @pytest.fixture(scope='function')
# def client(app):
#     return app.test_client()

@pytest.fixture(scope='session')
def db(app):
    """Session-wide test database."""
    _db.app = app # Associate db with the app context
    _db.create_all() # Create tables based on models

    yield _db # Provide the db object to tests

    _db.session.remove() # Clean up session
    _db.drop_all() # Drop tables after tests finish

@pytest.fixture(scope='function')
def session(db):
    """Creates a new database session for a test."""
    connection = db.engine.connect()
    transaction = connection.begin()
    # Use the connection for the session
    options = dict(bind=connection, binds={})
    sess = db.create_scoped_session(options=options)

    # establish  savepoints - use nested transactions to ensure isolation
    # sess.begin_nested() # Removed - simpler approach below

    # @event.listens_for(sess(), 'after_transaction_end')
    # def restart_savepoint(sess, transaction):
    #    if transaction.nested and not transaction._parent.nested:
    #       sess.expire_all()
    #       sess.begin_nested()

    db.session = sess # Assign the scoped session to db.session

    yield sess # Provide the session to the test function

    # Clean up
    sess.remove()
    # Rollback the overall transaction to undo changes made in the test
    transaction.rollback()
    connection.close()