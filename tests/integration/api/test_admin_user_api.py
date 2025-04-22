# tests/integration/api/test_admin_user_api.py
# -*- coding: utf-8 -*-
"""
Integration tests for the Admin User Management endpoints (/api/admin/users).
"""
import json
import pytest
import logging # Use logging

from app.database.models import UserModel
from app.services.user_service import UserService

log = logging.getLogger(__name__)

# Fixtures: client, session, db, logged_in_admin_client, logged_in_client

# --- Test GET /api/admin/users ---

def test_admin_get_users_success(logged_in_admin_client, session):
    """ GIVEN admin logged in; WHEN user created via API & GET /api/admin/users; THEN 200 """
    # log.debug("test_admin_get_users_success - START")
    username_to_create = "temp_seller_for_get_api"
    user_payload = {"username": username_to_create, "email": "temp_get_api@seller.xyz", "password": "TempPassGetAPI123", "role": "user", "status": "active"}
    create_response = logged_in_admin_client.post('/api/admin/users', json=user_payload)
    assert create_response.status_code == 201, f"Failed to create setup user via API: {create_response.data.decode()}"
    # log.debug(f"Setup user '{username_to_create}' created via API.")

    # Act
    response = logged_in_admin_client.get('/api/admin/users?page=1&per_page=10')
    # log.debug(f"List API Response Status: {response.status_code}")
    data = response.get_json()
    # log.debug(f"List API Response Data:\n{json.dumps(data, indent=2)}")

    # Assert
    assert response.status_code == 200
    assert 'items' in data and isinstance(data['items'], list)
    assert data.get('perPage') == 10

    # Check for the user created VIA API in this test
    temp_seller_found = any(item['username'] == username_to_create for item in data['items'])
    assert temp_seller_found, f"Expected {username_to_create} user (created via API) not found in response"
    # log.debug("test_admin_get_users_success - END")

def test_admin_get_users_forbidden_for_seller(logged_in_client):
    """ GIVEN seller logged in; WHEN GET /api/admin/users; THEN 403 """
    response = logged_in_client.get('/api/admin/users')
    assert response.status_code == 403

def test_admin_get_users_unauthorized(client):
    """ GIVEN no user logged in; WHEN GET /api/admin/users; THEN 401 """
    response = client.get('/api/admin/users')
    assert response.status_code == 401


# --- Test POST /api/admin/users ---

def test_admin_create_user_success(logged_in_admin_client, session):
    """ GIVEN admin logged in; WHEN POST with valid data; THEN 201 """
    new_user_data_json = {
        "username": "admin_created_user_api", "email": "created_api@admin.test", "password": "CreateMePassAPI123!",
        "role": "user", "status": "pending_approval", "fullName": "Admin Created API", "companyName": "Admin API Inc."
    }

    # Act
    response = logged_in_admin_client.post('/api/admin/users', json=new_user_data_json)

    # Assert Response
    assert response.status_code == 201
    data = response.get_json()
    assert data['username'] == new_user_data_json['username']
    assert data['email'] == new_user_data_json['email']
    assert data['role'] == new_user_data_json['role']
    assert data['status'] == new_user_data_json['status']
    assert data['fullName'] == new_user_data_json['fullName']
    assert data['companyName'] == new_user_data_json['companyName']
    assert 'id' in data
    user_id = data['id']

    # Assert Database State
    user_in_db = session.get(UserModel, user_id)
    assert user_in_db is not None
    assert user_in_db.username == new_user_data_json['username']
    assert user_in_db.email == new_user_data_json['email']
    assert user_in_db.role == new_user_data_json['role']
    assert user_in_db.status == new_user_data_json['status']
    assert user_in_db.full_name == new_user_data_json['fullName']
    assert user_in_db.company_name == new_user_data_json['companyName']
    assert user_in_db.check_password(new_user_data_json['password'])


def test_admin_create_user_duplicate_username(logged_in_admin_client, session):
    """ GIVEN username exists; WHEN POST with same username; THEN 409 """
    # Arrange: Create user via API first
    existing_username = "duplicate_user_api"
    payload1 = {"username": existing_username, "email": "original_api@duplicate.test", "password": "Pass123API", "role": "user", "status": "active"}
    res1 = logged_in_admin_client.post('/api/admin/users', json=payload1)
    assert res1.status_code == 201

    # Attempt to create again
    payload2 = {"username": existing_username, "email": "new_api@duplicate.test", "password": "CreateMePassAPI123!", "role": "user", "status": "active"}
    response = logged_in_admin_client.post('/api/admin/users', json=payload2)

    # Assert
    assert response.status_code == 409
    assert f"Username '{existing_username}' already exists" in response.get_json().get('message', '')


def test_admin_create_user_duplicate_email(logged_in_admin_client, session):
    """ GIVEN email exists; WHEN POST with same email; THEN 409 """
    existing_email = "original_api@duplicate.test"
    payload1 = {"username": "original_user_email_api", "email": existing_email, "password": "Pass123API", "role": "user", "status": "active"}
    res1 = logged_in_admin_client.post('/api/admin/users', json=payload1)
    assert res1.status_code == 201

    payload2 = {"username": "new_user_dup_email_api", "email": existing_email, "password": "CreateMePassAPI123!", "role": "user", "status": "active"}
    response = logged_in_admin_client.post('/api/admin/users', json=payload2)

    assert response.status_code == 409
    assert f"Email '{existing_email}' already exists" in response.get_json().get('message', '')


def test_admin_create_user_missing_fields(logged_in_admin_client):
    """ GIVEN missing required fields (e.g., password); WHEN POST; THEN 400 """
    new_user_data_json = {"username": "missing_pass_user_api", "email": "missing_api@pass.test", "role": "user", "status": "active"}
    response = logged_in_admin_client.post('/api/admin/users', json=new_user_data_json)
    assert response.status_code == 400
    assert 'password' in response.get_json().get('errors', {})


def test_admin_create_user_invalid_role(logged_in_admin_client):
    """ GIVEN invalid role; WHEN POST; THEN 400 """
    new_user_data_json = {"username": "invalid_role_user_api", "email": "invalid_api@role.test", "password": "Password123API!", "role": "invalid_role", "status": "active"}
    response = logged_in_admin_client.post('/api/admin/users', json=new_user_data_json)
    assert response.status_code == 400
    assert 'role' in response.get_json().get('errors', {})


# --- Test GET /api/admin/users/{user_id} ---

def test_admin_get_user_by_id_success(logged_in_admin_client, session):
    """ GIVEN target user exists; WHEN GET /api/admin/users/{user_id}; THEN 200 """
    # Arrange: Create user via API
    payload = {"username": "get_me_api", "email": "get_api@me.test", "password": "PassGetAPI123", "role": "user", "status": "active"}
    res = logged_in_admin_client.post('/api/admin/users', json=payload)
    assert res.status_code == 201
    target_id = res.get_json()['id']

    # Act
    response = logged_in_admin_client.get(f'/api/admin/users/{target_id}')
    assert response.status_code == 200
    data = response.get_json()
    assert data['id'] == target_id
    assert data['username'] == "get_me_api"


def test_admin_get_user_by_id_not_found(logged_in_admin_client):
    """ GIVEN non-existent ID; WHEN GET /api/admin/users/{user_id}; THEN 404 """
    response = logged_in_admin_client.get('/api/admin/users/99999')
    assert response.status_code == 404


# --- Test PUT /api/admin/users/{user_id} ---

def test_admin_update_user_success(logged_in_admin_client, session):
    """ GIVEN target user exists; WHEN PUT with valid update data; THEN 200 """
    # Arrange: Create user via API
    payload = {"username": "update_me_api", "email": "update_api@me.test", "password": "PassUpdateAPI123", "role": "user", "status": "active", "fullName": "Original Name API"}
    res = logged_in_admin_client.post('/api/admin/users', json=payload)
    assert res.status_code == 201
    target_id = res.get_json()['id']

    update_data_json = {"email": "updated_api@me.test", "role": "staff", "status": "inactive", "fullName": "Updated Name API"}

    # Act
    response = logged_in_admin_client.put(f'/api/admin/users/{target_id}', json=update_data_json)

    # Assert Response
    assert response.status_code == 200
    data = response.get_json()
    assert data['id'] == target_id
    assert data['email'] == update_data_json['email']
    assert data['role'] == update_data_json['role']
    assert data['status'] == update_data_json['status']
    assert data['fullName'] == update_data_json['fullName']

    # Assert Database State
    target_user = session.get(UserModel, target_id)
    assert target_user is not None
    assert target_user.email == update_data_json['email']
    assert target_user.role == update_data_json['role']
    assert target_user.status == update_data_json['status']
    assert target_user.full_name == update_data_json['fullName']


def test_admin_update_user_duplicate_email_fail(logged_in_admin_client, session):
    """ GIVEN user A and user B exist; WHEN PUT user A email to user B email; THEN 409 """
    # Arrange: Create users via API
    payload_a = {"username": "update_user_a_api", "email": "a_api@update.test", "password": "PassAAPI", "role": "user", "status": "active"}
    payload_b = {"username": "update_user_b_api", "email": "b_api@update.test", "password": "PassBAPI", "role": "user", "status": "active"}
    res_a = logged_in_admin_client.post('/api/admin/users', json=payload_a)
    res_b = logged_in_admin_client.post('/api/admin/users', json=payload_b)
    assert res_a.status_code == 201 and res_b.status_code == 201
    user_a_id = res_a.get_json()['id']
    user_b_email = res_b.get_json()['email']

    # Act: Attempt to update user A's email to user B's
    update_data_json = {"email": user_b_email}
    response = logged_in_admin_client.put(f'/api/admin/users/{user_a_id}', json=update_data_json)

    # Assert
    assert response.status_code == 409
    assert f"Email '{user_b_email}' is already in use" in response.get_json().get('message', '')


def test_admin_update_user_not_found(logged_in_admin_client):
    """ GIVEN non-existent ID; WHEN PUT /api/admin/users/{user_id}; THEN 404 """
    response = logged_in_admin_client.put('/api/admin/users/99999', json={"status": "active"})
    assert response.status_code == 404


# --- Test PUT /api/admin/users/{user_id}/password ---

def test_admin_change_user_password_success(logged_in_admin_client, session):
    """ GIVEN target user exists; WHEN PUT password with valid new password; THEN 200 """
    # Arrange: Create user via API
    payload = {"username": "pass_change_me_api", "email": "pass_api@change.test", "password": "OldPassAPI123", "role": "user", "status": "active"}
    res = logged_in_admin_client.post('/api/admin/users', json=payload)
    assert res.status_code == 201
    target_id = res.get_json()['id']

    new_password = "NewSecurePasswordAPI789!"
    password_data = {"password": new_password}

    # Act
    response = logged_in_admin_client.put(f'/api/admin/users/{target_id}/password', json=password_data)

    # Assert Response
    assert response.status_code == 200
    assert response.get_json()['message'] == "Password updated successfully."

    # Assert Database State
    target_user = session.get(UserModel, target_id)
    assert target_user.check_password(new_password)
    assert not target_user.check_password("OldPassAPI123")


def test_admin_change_user_password_short_fail(logged_in_admin_client, session):
    """ GIVEN short password; WHEN PUT password; THEN 400 """
    # Arrange: Create user via API
    payload = {"username": "pass_short_api", "email": "short_api@pass.change", "password": "OldPassAPI123", "role": "user", "status": "active"}
    res = logged_in_admin_client.post('/api/admin/users', json=payload)
    assert res.status_code == 201
    target_id = res.get_json()['id']

    password_data = {"password": "short"}
    response = logged_in_admin_client.put(f'/api/admin/users/{target_id}/password', json=password_data)

    assert response.status_code == 400
    assert 'password' in response.get_json().get('errors', {})


def test_admin_change_user_password_not_found(logged_in_admin_client):
    """ GIVEN non-existent ID; WHEN PUT password; THEN 404 """
    response = logged_in_admin_client.put('/api/admin/users/99999/password', json={"password": "ValidPassAPI123!"})
    assert response.status_code == 404


# --- Test DELETE /api/admin/users/{user_id} ---

def test_admin_delete_user_success(logged_in_admin_client, session):
    """ GIVEN target user exists; WHEN DELETE /api/admin/users/{user_id}; THEN 204 """
    # Arrange: Create user via API
    payload = {"username": "delete_me_api", "email": "delete_api@me.test", "password": "PassDeleteAPI123", "role": "user", "status": "active"}
    res = logged_in_admin_client.post('/api/admin/users', json=payload)
    assert res.status_code == 201
    target_id = res.get_json()['id']
    assert session.get(UserModel, target_id) is not None # Verify exists before API call

    # Act
    response = logged_in_admin_client.delete(f'/api/admin/users/{target_id}')

    # Assert Response
    assert response.status_code == 204

    # Assert Database State (Check object is gone after API commit)
    assert session.get(UserModel, target_id) is None


def test_admin_delete_user_self_fail(logged_in_admin_client, session):
    """ GIVEN admin logged in; WHEN DELETE self; THEN 403 """
    # Arrange: Get ID of the currently logged-in admin fixture user
    admin_user = session.query(UserModel).filter_by(username="pytest_admin").first()
    assert admin_user is not None, "Admin fixture user not found"
    admin_id = admin_user.id

    # Act
    response = logged_in_admin_client.delete(f'/api/admin/users/{admin_id}')

    # Assert
    assert response.status_code == 403
    assert "Admin cannot delete their own account" in response.get_json().get('message', '')


def test_admin_delete_user_not_found(logged_in_admin_client):
    """ GIVEN non-existent ID; WHEN DELETE /api/admin/users/{user_id}; THEN 404 """
    response = logged_in_admin_client.delete('/api/admin/users/99999')
    assert response.status_code == 404