# tests/integration/services/test_user_service.py
import pytest
from app.services.user_service import UserService
from app.database.models.user import UserModel

def test_create_user_success(session): # Use the session fixture
    """Test creating a user successfully."""
    username = "testuser"
    email = "test@example.com"
    password = "password123"
    user = UserService.create_user(username, email, password, role='user')

    # Assert returned object is correct
    assert user is not None
    assert user.username == username
    assert user.email == email
    assert user.role == 'user'
    assert user.id is not None # Ensure it got an ID

    # Assert persistence (query directly)
    user_from_db = UserModel.query.get(user.id)
    assert user_from_db is not None
    assert user_from_db.username == username

def test_create_user_duplicate_username(session):
    """Test creating a user with a duplicate username raises ValueError."""
    UserService.create_user("existing", "e1@example.com", "pass") # Create first user

    with pytest.raises(ValueError, match="Username 'existing' already exists."):
        UserService.create_user("existing", "e2@example.com", "pass")

def test_create_user_duplicate_email(session):
    """Test creating a user with a duplicate email raises ValueError."""
    UserService.create_user("user1", "existing@example.com", "pass")

    with pytest.raises(ValueError, match="Email 'existing@example.com' already exists."):
        UserService.create_user("user2", "existing@example.com", "pass")

def test_get_user_by_id_found(session):
    """Test fetching an existing user by ID."""
    user = UserService.create_user("fetchme", "fetch@example.com", "pass")
    fetched_user = UserService.get_user_by_id(user.id)
    assert fetched_user is not None
    assert fetched_user.id == user.id
    assert fetched_user.username == "fetchme"

def test_get_user_by_id_not_found(session):
    """Test fetching a non-existent user by ID returns None."""
    fetched_user = UserService.get_user_by_id(99999) # Assuming this ID doesn't exist
    assert fetched_user is None

# --- Add more tests for ---
# - get_user_by_username (found/not found)
# - get_all_users (check pagination object structure, maybe item count if predictable)
# - update_user (successful update, update non-existent, update with email conflict)
# - change_password (check hash changes)
# - delete_user (successful delete, delete non-existent)
# - Test edge cases for role/status validation in create/update