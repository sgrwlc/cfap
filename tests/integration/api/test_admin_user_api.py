# -*- coding: utf-8 -*-
"""
Integration tests for the Admin User Management endpoints (/api/admin/users).
"""
import json
import pytest

from app.database.models import UserModel # Import model for checks
from app.services.user_service import UserService # Import service for test setup


# Fixtures like 'client', 'session', 'db', 'logged_in_admin_client', 'logged_in_client'
# are automatically used when included as test function arguments.

# --- Test GET /api/admin/users ---

def test_admin_get_users_success(logged_in_admin_client, session):
    """
    GIVEN admin client logged in and some users in DB
    WHEN GET /api/admin/users is requested
    THEN check status 200 and valid paginated user list is returned.
    """
    # Arrange: The logged_in_admin_client fixture creates at least one admin user.
    # Add another user to test pagination/listing. Use Python attribute names.
    UserService.create_user(
        username="temp_seller",
        email="temp@seller.xyz",
        password="TempPass123",
        role="user",
        status="active"
    )

    # Act
    response = logged_in_admin_client.get('/api/admin/users?page=1&per_page=5')

    # Assert
    assert response.status_code == 200
    data = json.loads(response.data)
    assert 'items' in data
    assert data.get('page') == 1
    assert data.get('perPage') == 5 # Check camelCase output key
    assert 'total' in data
    assert 'pages' in data
    assert isinstance(data['items'], list)
    assert len(data['items']) >= 2 # Check if at least the admin and the temp user are present
    assert any(item['username'] == 'pytest_admin' for item in data['items'])
    assert any(item['username'] == 'temp_seller' for item in data['items'])

def test_admin_get_users_forbidden_for_seller(logged_in_client):
    """
    GIVEN seller client logged in
    WHEN GET /api/admin/users is requested
    THEN check status 403 Forbidden.
    """
    response = logged_in_client.get('/api/admin/users')
    assert response.status_code == 403
    data = json.loads(response.data)
    assert "Forbidden" in data.get('message', '') or "role(s) ['admin'] not met" in data.get('message', '')

def test_admin_get_users_unauthorized(client):
    """
    GIVEN no user logged in
    WHEN GET /api/admin/users is requested
    THEN check status 401 Unauthorized.
    """
    response = client.get('/api/admin/users')
    assert response.status_code == 401
    data = json.loads(response.data)
    assert "Authentication required" in data.get('message', '')


# --- Test POST /api/admin/users ---

def test_admin_create_user_success(logged_in_admin_client, session):
    """
    GIVEN admin client logged in
    WHEN POST /api/admin/users with valid data
    THEN check status 201 Created and user details are returned correctly.
    """
    # Arrange: Use camelCase keys matching schema's data_key for input JSON
    new_user_data_json = {
        "username": "admin_created_user",
        "email": "created@admin.test",
        "password": "CreateMePass123!",
        "role": "user",
        "status": "pending_approval", # Assumes DB migration for length applied
        "fullName": "Admin Created",
        "companyName": "Admin Inc."
    }

    # Act
    response = logged_in_admin_client.post('/api/admin/users', json=new_user_data_json)

    # Assert Status & Response Body (Output uses camelCase from data_key)
    assert response.status_code == 201
    data = json.loads(response.data)
    assert data['username'] == new_user_data_json['username']
    assert data['email'] == new_user_data_json['email']
    assert data['role'] == new_user_data_json['role']
    assert data['status'] == new_user_data_json['status']
    assert data['fullName'] == new_user_data_json['fullName']
    assert data['companyName'] == new_user_data_json['companyName']
    assert 'id' in data
    assert 'createdAt' in data
    assert 'updatedAt' in data
    user_id = data['id']

    # Assert Database State (DB uses snake_case attributes)
    user_in_db = session.get(UserModel, user_id)
    assert user_in_db is not None
    assert user_in_db.username == new_user_data_json['username']
    assert user_in_db.email == new_user_data_json['email']
    assert user_in_db.role == new_user_data_json['role']
    assert user_in_db.status == new_user_data_json['status']
    assert user_in_db.full_name == new_user_data_json['fullName'] # Check correct attribute
    assert user_in_db.company_name == new_user_data_json['companyName'] # Check correct attribute
    assert user_in_db.check_password(new_user_data_json['password'])


def test_admin_create_user_duplicate_username(logged_in_admin_client, session):
    """
    GIVEN admin client logged in and a user exists
    WHEN POST /api/admin/users with the same username
    THEN check status 409 Conflict.
    """
    # Arrange: Create an initial user
    existing_username = "duplicate_user"
    UserService.create_user(existing_username, "original@duplicate.test", "Pass123", role="user", status="active") # Add status

    new_user_data_json = {
        "username": existing_username, # Duplicate
        "email": "new@duplicate.test",
        "password": "CreateMePass123!",
        "role": "user",
        "status": "active" # Add status to input
    }

    # Act
    response = logged_in_admin_client.post('/api/admin/users', json=new_user_data_json)

    # Assert
    assert response.status_code == 409
    data = json.loads(response.data)
    assert f"Username '{existing_username}' already exists" in data.get('message', '')


def test_admin_create_user_duplicate_email(logged_in_admin_client, session):
    """
    GIVEN admin client logged in and a user exists
    WHEN POST /api/admin/users with the same email
    THEN check status 409 Conflict.
    """
    # Arrange: Create an initial user
    existing_email = "original@duplicate.test"
    UserService.create_user("original_user_email", existing_email, "Pass123", role="user", status="active") # Add status

    new_user_data_json = {
        "username": "new_user_dup_email",
        "email": existing_email, # Duplicate
        "password": "CreateMePass123!",
        "role": "user",
        "status": "active" # Add status to input
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
    THEN check status 400 Bad Request.
    """
    new_user_data_json = {
        "username": "missing_pass_user",
        "email": "missing@pass.test",
        "role": "user",
        "status": "active"
    }
    response = logged_in_admin_client.post('/api/admin/users', json=new_user_data_json)
    # Assert
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'password' in data # Check key exists directly in response dict
    assert data['password'] == ['Missing data for required field.'] # Check message

def test_admin_create_user_invalid_role(logged_in_admin_client):
    """
    GIVEN admin client logged in
    WHEN POST /api/admin/users with an invalid role
    THEN check status 400 Bad Request.
    """
    new_user_data_json = {
        "username": "invalid_role_user",
        "email": "invalid@role.test",
        "password": "Password123!",
        "role": "invalid_role", # Invalid
        "status": "active"
    }
    response = logged_in_admin_client.post('/api/admin/users', json=new_user_data_json)
    # Assert
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'role' in data # Check key exists directly in response dict
    assert data['role'] == ['Must be one of: admin, staff, user.'] # Check message

# --- Test GET /api/admin/users/{user_id} ---

def test_admin_get_user_by_id_success(logged_in_admin_client, session):
    """
    GIVEN admin client logged in and a target user exists
    WHEN GET /api/admin/users/{user_id} is requested
    THEN check status 200 OK and correct user details are returned.
    """
    target_user = UserService.create_user("get_me", "get@me.test", "Pass123", role="user", status="active")
    target_id = target_user.id
    response = logged_in_admin_client.get(f'/api/admin/users/{target_id}')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['id'] == target_id
    assert data['username'] == "get_me"
    assert data['email'] == "get@me.test"
    assert data['role'] == "user"
    assert data['status'] == "active"

def test_admin_get_user_by_id_not_found(logged_in_admin_client):
    """
    GIVEN admin client logged in
    WHEN GET /api/admin/users/{user_id} is requested for a non-existent ID
    THEN check status 404 Not Found.
    """
    response = logged_in_admin_client.get('/api/admin/users/99999')
    assert response.status_code == 404
    data = json.loads(response.data)
    assert "User with ID 99999 not found" in data.get('message', '')


# --- Test PUT /api/admin/users/{user_id} ---

def test_admin_update_user_success(logged_in_admin_client, session):
    """
    GIVEN admin client logged in and a target user exists
    WHEN PUT /api/admin/users/{user_id} with valid update data
    THEN check status 200 OK and user details are updated in DB and response.
    """
    # Arrange: Create a target user using snake_case for service call arguments
    target_user = UserService.create_user(
        "update_me",
        "update@me.test",
        "Pass123",
        role="user",
        status="active",
        full_name="Original Name" # Use snake_case for keyword arg
    )
    target_id = target_user.id
    # Input JSON uses camelCase keys matching schema's data_key
    update_data_json = {
        "email": "updated@me.test",
        "role": "staff",
        "status": "inactive",
        "fullName": "Updated Name"
    }

    # Act
    response = logged_in_admin_client.put(f'/api/admin/users/{target_id}', json=update_data_json)

    # Assert Response (Output uses camelCase from data_key)
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['id'] == target_id
    assert data['username'] == "update_me"
    assert data['email'] == update_data_json['email']
    assert data['role'] == update_data_json['role']
    assert data['status'] == update_data_json['status']
    assert data['fullName'] == update_data_json['fullName']

    # Assert Database State (DB uses snake_case attributes)
    # Force refresh from DB within the same session if needed
    session.refresh(target_user) # Or query again: target_user = session.get(UserModel, target_id)
    assert target_user.email == update_data_json['email']
    assert target_user.role == update_data_json['role']
    assert target_user.status == update_data_json['status']
    assert target_user.full_name == update_data_json['fullName'] # Compare DB snake_case attribute to input value

def test_admin_update_user_duplicate_email_fail(logged_in_admin_client, session):
    """
    GIVEN admin client logged in, user A and user B exist
    WHEN PUT /api/admin/users/{user_A_id} attempts to set email to user B's email
    THEN check status 409 Conflict.
    """
    user_a = UserService.create_user("update_user_a", "a@update.test", "PassA", role="user", status="active")
    user_b = UserService.create_user("update_user_b", "b@update.test", "PassB", role="user", status="active")
    update_data_json = {"email": user_b.email}
    response = logged_in_admin_client.put(f'/api/admin/users/{user_a.id}', json=update_data_json)
    assert response.status_code == 409
    data = json.loads(response.data)
    assert f"Email '{user_b.email}' is already in use" in data.get('message', '')

def test_admin_update_user_not_found(logged_in_admin_client):
    """
    GIVEN admin client logged in
    WHEN PUT /api/admin/users/{user_id} for a non-existent ID
    THEN check status 404 Not Found.
    """
    response = logged_in_admin_client.put('/api/admin/users/99999', json={"status": "active"})
    assert response.status_code == 404
    data = json.loads(response.data)
    assert "User with ID 99999 not found" in data.get('message', '')


# --- Test PUT /api/admin/users/{user_id}/password ---

def test_admin_change_user_password_success(logged_in_admin_client, session):
    """
    GIVEN admin client logged in and a target user exists
    WHEN PUT /api/admin/users/{user_id}/password with a new valid password
    THEN check status 200 OK and the password is changed in DB.
    """
    target_user = UserService.create_user("pass_change_me", "pass@change.test", "OldPass123", role="user", status="active")
    target_id = target_user.id
    new_password = "NewSecurePassword789!"
    password_data = {"password": new_password}
    response = logged_in_admin_client.put(f'/api/admin/users/{target_id}/password', json=password_data)
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['message'] == "Password updated successfully."
    # Refresh user object from session/db to get updated hash
    session.refresh(target_user)
    assert target_user.check_password(new_password)
    assert not target_user.check_password("OldPass123")

def test_admin_change_user_password_short_fail(logged_in_admin_client, session):
    """
    GIVEN admin client logged in and a target user exists
    WHEN PUT /api/admin/users/{user_id}/password with a short password
    THEN check status 400 Bad Request.
    """
    target_user = UserService.create_user("pass_short", "short@pass.change", "OldPass123", role="user", status="active")
    target_id = target_user.id
    password_data = {"password": "short"}
    response = logged_in_admin_client.put(f'/api/admin/users/{target_id}/password', json=password_data)
    # Assert
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'password' in data # Check key exists directly in response dict
    assert data['password'] == ['Shorter than minimum length 8.'] # Check message

def test_admin_change_user_password_not_found(logged_in_admin_client):
    """
    GIVEN admin client logged in
    WHEN PUT /api/admin/users/{user_id}/password for a non-existent ID
    THEN check status 404 Not Found.
    """
    response = logged_in_admin_client.put('/api/admin/users/99999/password', json={"password": "ValidPass123!"})
    assert response.status_code == 404


# --- Test DELETE /api/admin/users/{user_id} ---

def test_admin_delete_user_success(logged_in_admin_client, session):
    """
    GIVEN admin client logged in and a target user exists
    WHEN DELETE /api/admin/users/{user_id} is requested
    THEN check status 204 No Content and user is removed from DB.
    """
    target_user = UserService.create_user("delete_me", "delete@me.test", "Pass123", role="user", status="active")
    target_id = target_user.id
    user_before = session.get(UserModel, target_id)
    assert user_before is not None
    response = logged_in_admin_client.delete(f'/api/admin/users/{target_id}')
    assert response.status_code == 204
    user_after = session.get(UserModel, target_id)
    assert user_after is None

def test_admin_delete_user_self_fail(logged_in_admin_client, session):
    """
    GIVEN admin client logged in
    WHEN DELETE /api/admin/users/{user_id} is requested for self
    THEN check status 403 Forbidden.
    """
    admin_user = UserModel.query.filter_by(username="pytest_admin").first()
    assert admin_user is not None
    admin_id = admin_user.id
    response = logged_in_admin_client.delete(f'/api/admin/users/{admin_id}')
    assert response.status_code == 403
    data = json.loads(response.data)
    assert "Admin cannot delete their own account" in data.get('message', '')

def test_admin_delete_user_not_found(logged_in_admin_client):
    """
    GIVEN admin client logged in
    WHEN DELETE /api/admin/users/{user_id} for a non-existent ID
    THEN check status 404 Not Found.
    """
    response = logged_in_admin_client.delete('/api/admin/users/99999')
    assert response.status_code == 404