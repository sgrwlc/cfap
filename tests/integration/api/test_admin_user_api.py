# tests/integration/api/test_admin_user_api.py
# -*- coding: utf-8 -*-
"""
Integration tests for the Admin User Management endpoints (/api/admin/users),
aligned with refactored services and routes.
"""
import json
import pytest
import logging # Use logging

from app.database.models import UserModel # Import model for checks
from app.services.user_service import UserService # Import service for setup if needed


log = logging.getLogger(__name__) # Use logger

# Fixtures 'client', 'session', 'db', 'logged_in_admin_client', 'logged_in_client' used.

# --- Test GET /api/admin/users ---

def test_admin_get_users_success(logged_in_admin_client, session):
    """
    GIVEN admin client logged in
    WHEN GET /api/admin/users is requested
    THEN check status 200 and a paginated list including expected users is returned.
    """
    log.debug("Running test_admin_get_users_success")
    # Arrange: Use API to create a user to ensure it appears in the list
    username_to_create = "list_test_user_p5"
    user_payload = {
        "username": username_to_create, "email": "list_p5@test.com",
        "password": "ListUserPass1!", "role": "user", "status": "active"
    }
    create_resp = logged_in_admin_client.post('/api/admin/users', json=user_payload)
    assert create_resp.status_code == 201, f"Setup failed: Could not create user via API. Response: {create_resp.data.decode()}"
    created_user_id = json.loads(create_resp.data)['id']
    log.debug(f"Setup user '{username_to_create}' (ID: {created_user_id}) created via API.")

    # Act: Get the list
    # Fetch more items per page to increase chance of seeing created/fixture users
    response = logged_in_admin_client.get('/api/admin/users?page=1&per_page=50')

    # Assert
    assert response.status_code == 200
    data = json.loads(response.data)
    assert 'items' in data and isinstance(data['items'], list)
    assert data.get('page') == 1
    assert 'total' in data and data['total'] >= 1 # At least the one we created should be there

    # Check if the user created via API is present
    api_created_found = any(item['username'] == username_to_create for item in data['items'])
    assert api_created_found, f"User '{username_to_create}' created via API not found in list response."

    # Check if the admin user from the fixture is present (should be)
    admin_fixture_found = any(item['username'] == 'pytest_admin' for item in data['items'])
    assert admin_fixture_found, "Admin user 'pytest_admin' from fixture not found in list response."
    log.debug("Finished test_admin_get_users_success")


def test_admin_get_users_forbidden_for_seller(logged_in_client):
    """
    GIVEN seller client logged in
    WHEN GET /api/admin/users is requested
    THEN check status 403 Forbidden.
    """
    response = logged_in_client.get('/api/admin/users')
    assert response.status_code == 403
    data = json.loads(response.data)
    assert "Required role(s) ['admin'] not met" in data.get('message', '')


def test_admin_get_users_unauthorized(client):
    """
    GIVEN no user logged in
    WHEN GET /api/admin/users is requested
    THEN check status 401 Unauthorized.
    """
    response = client.get('/api/admin/users')
    assert response.status_code == 401


# --- Test POST /api/admin/users ---

def test_admin_create_user_success(logged_in_admin_client, session):
    """
    GIVEN admin client logged in
    WHEN POST /api/admin/users with valid data
    THEN check status 201 Created, response details correct, and user exists in DB.
    """
    log.debug("Running test_admin_create_user_success")
    new_user_data_json = {
        "username": "admin_created_p5", "email": "created_p5@admin.test",
        "password": "CreateMePass123!", "role": "user", "status": "pending_approval",
        "fullName": "Admin Created P5", "companyName": "Admin P5 Inc."
    }

    # Act: Call API to create user (route handles commit)
    response = logged_in_admin_client.post('/api/admin/users', json=new_user_data_json)

    # Assert Response
    assert response.status_code == 201
    data = json.loads(response.data)
    assert data['username'] == new_user_data_json['username']
    assert data['email'] == new_user_data_json['email']
    assert data['role'] == new_user_data_json['role']
    assert data['status'] == new_user_data_json['status']
    assert data['fullName'] == new_user_data_json['fullName']
    assert data['companyName'] == new_user_data_json['companyName']
    assert 'id' in data
    user_id = data['id']

    # Assert Database State (use session fixture to query after API commit)
    user_in_db = session.get(UserModel, user_id)
    assert user_in_db is not None
    assert user_in_db.username == new_user_data_json['username']
    assert user_in_db.role == new_user_data_json['role']
    assert user_in_db.status == new_user_data_json['status']
    assert user_in_db.full_name == new_user_data_json['fullName']
    assert user_in_db.check_password(new_user_data_json['password'])
    log.debug("Finished test_admin_create_user_success")


def test_admin_create_user_duplicate_username(logged_in_admin_client, session):
    """
    GIVEN admin client logged in and a user exists
    WHEN POST /api/admin/users with the same username
    THEN check status 409 Conflict.
    """
    # Arrange: Create initial user directly via service (no commit needed for setup)
    existing_username = "duplicate_user_p5"
    UserService.create_user(existing_username, "original_p5@duplicate.test", "Pass123", role="user", status="active")
    session.flush() # Ensure user exists in transaction for subsequent check

    new_user_data_json = {
        "username": existing_username, # Duplicate
        "email": "new_p5@duplicate.test", "password": "CreateMePass123!",
        "role": "user", "status": "active"
    }

    # Act: Call API
    response = logged_in_admin_client.post('/api/admin/users', json=new_user_data_json)

    # Assert: Route should catch ConflictError from service and abort(409)
    assert response.status_code == 409
    data = json.loads(response.data)
    assert f"Username '{existing_username}' already exists" in data.get('message', '')


def test_admin_create_user_duplicate_email(logged_in_admin_client, session):
    """
    GIVEN admin client logged in and a user exists
    WHEN POST /api/admin/users with the same email
    THEN check status 409 Conflict.
    """
    # Arrange
    existing_email = "original_p5@duplicate.test"
    UserService.create_user("original_user_email_p5", existing_email, "Pass123", role="user", status="active")
    session.flush()

    new_user_data_json = {
        "username": "new_user_dup_email_p5", "email": existing_email, # Duplicate
        "password": "CreateMePass123!", "role": "user", "status": "active"
    }
    # Act
    response = logged_in_admin_client.post('/api/admin/users', json=new_user_data_json)

    # Assert
    assert response.status_code == 409
    data = json.loads(response.data)
    assert f"Email '{existing_email}' already exists" in data.get('message', '')


def test_admin_create_user_missing_fields(logged_in_admin_client):
    """
    GIVEN admin client logged in
    WHEN POST /api/admin/users with missing required fields (e.g., password)
    THEN check status 400 Bad Request (schema validation).
    """
    new_user_data_json = {"username": "missing_pass_p5", "email": "missing_p5@pass.test"}
    response = logged_in_admin_client.post('/api/admin/users', json=new_user_data_json)
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'errors' in data and 'password' in data['errors']


def test_admin_create_user_invalid_role(logged_in_admin_client):
    """
    GIVEN admin client logged in
    WHEN POST /api/admin/users with an invalid role
    THEN check status 400 Bad Request (schema validation).
    """
    new_user_data_json = {
        "username": "invalid_role_p5", "email": "invalid_p5@role.test",
        "password": "Password123!", "role": "invalid_role" # Invalid
    }
    response = logged_in_admin_client.post('/api/admin/users', json=new_user_data_json)
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'errors' in data and 'role' in data['errors']


# --- Test GET /api/admin/users/{user_id} ---

def test_admin_get_user_by_id_success(logged_in_admin_client, session):
    """
    GIVEN admin client logged in and a target user exists
    WHEN GET /api/admin/users/{user_id} is requested
    THEN check status 200 OK and correct user details are returned.
    """
    # Arrange: Create user via service
    target_user = UserService.create_user("get_me_p5", "get_p5@me.test", "Pass123", role="user", status="active")
    session.flush() # Ensure ID is assigned
    target_id = target_user.id

    # Act
    response = logged_in_admin_client.get(f'/api/admin/users/{target_id}')

    # Assert
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['id'] == target_id
    assert data['username'] == "get_me_p5"


def test_admin_get_user_by_id_not_found(logged_in_admin_client):
    """
    GIVEN admin client logged in
    WHEN GET /api/admin/users/{user_id} for non-existent ID
    THEN check status 404 Not Found.
    """
    response = logged_in_admin_client.get('/api/admin/users/999999') # Use a clearly non-existent ID
    assert response.status_code == 404


# --- Test PUT /api/admin/users/{user_id} ---

def test_admin_update_user_success(logged_in_admin_client, session):
    """
    GIVEN admin client logged in and a target user exists
    WHEN PUT /api/admin/users/{user_id} with valid update data
    THEN check status 200 OK and user details are updated in DB and response.
    """
    # Arrange: Create user via service
    target_user = UserService.create_user("update_me_p5", "update_p5@me.test", "Pass123", role="user", status="active", full_name="Original P5")
    session.flush()
    target_id = target_user.id

    update_data_json = {
        "email": "updated_p5@me.test", "role": "staff", "status": "inactive", "fullName": "Updated P5"
    }
    # Act: Call API (handles commit)
    response = logged_in_admin_client.put(f'/api/admin/users/{target_id}', json=update_data_json)

    # Assert Response
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['email'] == update_data_json['email']
    assert data['role'] == update_data_json['role']
    assert data['status'] == update_data_json['status']
    assert data['fullName'] == update_data_json['fullName']

    # Assert Database State (query after API commit)
    user_in_db = session.get(UserModel, target_id) # Re-fetch from DB
    assert user_in_db is not None
    assert user_in_db.email == update_data_json['email']
    assert user_in_db.role == update_data_json['role']
    assert user_in_db.status == update_data_json['status']
    assert user_in_db.full_name == update_data_json['fullName']


def test_admin_update_user_duplicate_email_fail(logged_in_admin_client, session):
    """
    GIVEN admin client logged in, user A and user B exist
    WHEN PUT /api/admin/users/{user_A_id} attempts to set email to user B's email
    THEN check status 409 Conflict.
    """
    # Arrange
    user_a = UserService.create_user("update_user_a_p5", "a_p5@update.test", "PassA", role="user", status="active")
    user_b = UserService.create_user("update_user_b_p5", "b_p5@update.test", "PassB", role="user", status="active")
    session.flush()
    update_data_json = {"email": user_b.email} # Attempt to use user B's email

    # Act: Call API for user A
    response = logged_in_admin_client.put(f'/api/admin/users/{user_a.id}', json=update_data_json)

    # Assert: Route catches ConflictError from service
    assert response.status_code == 409
    data = json.loads(response.data)
    assert f"Email '{user_b.email}' is already in use" in data.get('message', '')


def test_admin_update_user_not_found(logged_in_admin_client):
    """
    GIVEN admin client logged in
    WHEN PUT /api/admin/users/{user_id} for non-existent ID
    THEN check status 404 Not Found.
    """
    response = logged_in_admin_client.put('/api/admin/users/999999', json={"status": "active"})
    assert response.status_code == 404


# --- Test PUT /api/admin/users/{user_id}/password ---

def test_admin_change_user_password_success(logged_in_admin_client, session):
    """
    GIVEN admin client logged in and a target user exists
    WHEN PUT /api/admin/users/{user_id}/password with a new valid password
    THEN check status 200 OK and the password is changed in DB.
    """
    # Arrange
    target_user = UserService.create_user("pass_change_p5", "pass_p5@change.test", "OldPass123", role="user", status="active")
    session.flush()
    target_id = target_user.id
    new_password = "NewSecurePasswordP5!"
    password_data = {"password": new_password}

    # Act: Call API (handles commit)
    response = logged_in_admin_client.put(f'/api/admin/users/{target_id}/password', json=password_data)

    # Assert Response
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['message'] == "Password updated successfully."

    # Assert Database State
    user_in_db = session.get(UserModel, target_id) # Re-fetch
    assert user_in_db.check_password(new_password)
    assert not user_in_db.check_password("OldPass123")


def test_admin_change_user_password_short_fail(logged_in_admin_client, session):
    """
    GIVEN admin client logged in and a target user exists
    WHEN PUT /api/admin/users/{user_id}/password with a short password
    THEN check status 400 Bad Request (schema validation).
    """
    # Arrange
    target_user = UserService.create_user("pass_short_p5", "short_p5@pass.change", "OldPass123", role="user", status="active")
    session.flush()
    target_id = target_user.id
    password_data = {"password": "short"}

    # Act
    response = logged_in_admin_client.put(f'/api/admin/users/{target_id}/password', json=password_data)

    # Assert: Schema validation fails
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'errors' in data and 'password' in data['errors']
    assert "password must be at least 8 characters long." in data['errors']['password'][0].lower()


def test_admin_change_user_password_not_found(logged_in_admin_client):
    """
    GIVEN admin client logged in
    WHEN PUT /api/admin/users/{user_id}/password for non-existent ID
    THEN check status 404 Not Found.
    """
    response = logged_in_admin_client.put('/api/admin/users/999999/password', json={"password": "ValidPassP5!"})
    assert response.status_code == 404


# --- Test DELETE /api/admin/users/{user_id} ---

def test_admin_delete_user_success(logged_in_admin_client, session):
    """
    GIVEN admin client logged in and a target user exists
    WHEN DELETE /api/admin/users/{user_id} is requested
    THEN check status 204 No Content and user is removed from DB.
    """
    # Arrange
    target_user = UserService.create_user("delete_me_p5", "delete_p5@me.test", "Pass123", role="user", status="active")
    session.flush()
    target_id = target_user.id
    assert session.get(UserModel, target_id) is not None # Verify exists before API call

    # Act: Call API (handles commit)
    response = logged_in_admin_client.delete(f'/api/admin/users/{target_id}')

    # Assert Response
    assert response.status_code == 204

    # Assert Database State (Check object is gone after API commit)
    assert session.get(UserModel, target_id) is None


def test_admin_delete_user_self_fail(logged_in_admin_client, session):
    """
    GIVEN admin client logged in
    WHEN DELETE /api/admin/users/{user_id} is requested for self
    THEN check status 403 Forbidden.
    """
    # Arrange: Get the logged-in admin's ID
    admin_user = session.query(UserModel).filter_by(username="pytest_admin").one()
    admin_id = admin_user.id

    # Act
    response = logged_in_admin_client.delete(f'/api/admin/users/{admin_id}')

    # Assert
    assert response.status_code == 403
    data = json.loads(response.data)
    assert "Admin cannot delete their own account" in data.get('message', '')


def test_admin_delete_user_not_found(logged_in_admin_client):
    """
    GIVEN admin client logged in
    WHEN DELETE /api/admin/users/{user_id} for non-existent ID
    THEN check status 404 Not Found.
    """
    response = logged_in_admin_client.delete('/api/admin/users/999999')
    # Route catches ResourceNotFound from service and aborts
    assert response.status_code == 404