# tests/integration/api/test_auth_api.py
# -*- coding: utf-8 -*-
"""
Integration tests for the /api/auth endpoints.
"""
import json
import pytest
import logging # Use logging

from app.database.models.user import UserModel
# Import UserService ONLY if needed for specific status setup not possible via API
from app.services.user_service import UserService

log = logging.getLogger(__name__)

# Fixtures: client, session, db, logged_in_client, logged_in_admin_client

# Helper to create user via Admin API (assuming admin is logged in)
def create_user_via_api(admin_client, username, email, password, role='user', status='active'):
    payload = {"username": username, "email": email, "password": password, "role": role, "status": status}
    response = admin_client.post('/api/admin/users', json=payload)
    assert response.status_code == 201, f"Failed to create user '{username}' via API for test setup: {response.data.decode()}"
    return response.get_json()

# --- Test /api/auth/login ---

def test_login_success(client, logged_in_admin_client): # Use admin client for setup
    """ GIVEN user created via API; WHEN POST /login with correct credentials; THEN 200 """
    # Arrange: Create user using the admin API
    username = "logintestuser_api"
    password = "PasswordAPI123!"
    email = "login_api@test.com"
    create_user_via_api(logged_in_admin_client, username, email, password, role='user', status='active')

    # Act: Make login request with non-admin client
    response = client.post('/api/auth/login', json={'username': username, 'password': password})

    # Assert
    assert response.status_code == 200
    response_data = response.get_json()
    assert response_data['message'] == "Login successful."
    assert 'user' in response_data and response_data['user']['username'] == username
    assert response.headers.get('Set-Cookie') is not None


def test_login_fail_wrong_password(client, logged_in_admin_client):
    """ GIVEN user created via API; WHEN POST /login with wrong password; THEN 401 """
    # Arrange
    username = "wrongpassuser_api"
    password = "PasswordAPI123!"
    create_user_via_api(logged_in_admin_client, username, "wrongpass_api@test.com", password)

    # Act
    response = client.post('/api/auth/login', json={'username': username, 'password': "WrongPasswordAPI!"})

    # Assert
    assert response.status_code == 401
    assert "Invalid username or password" in response.get_json().get('message', '')


def test_login_fail_inactive_user(client, logged_in_admin_client):
    """ GIVEN inactive user created via API; WHEN POST /login; THEN 401 """
    # Arrange
    username = "inactiveuser_api"
    password = "PasswordAPI123!"
    create_user_via_api(logged_in_admin_client, username, "inactive_api@test.com", password, status='inactive')

    # Act
    response = client.post('/api/auth/login', json={'username': username, 'password': password})

    # Assert
    assert response.status_code == 401
    # The service now raises specific errors, check message accordingly
    assert "User account is inactive" in response.get_json().get('message', '') or \
           "Invalid username or password" in response.get_json().get('message', '') # Depending on exact AuthService flow


def test_login_fail_missing_username(client):
    """ WHEN POST /login without username; THEN 400 """
    response = client.post('/api/auth/login', json={'password': "PasswordAPI123!"})
    assert response.status_code == 400
    assert "Username and password are required" in response.get_json().get('message', '')


def test_login_fail_missing_password(client):
    """ WHEN POST /login without password; THEN 400 """
    response = client.post('/api/auth/login', json={'username': "someuser_api"})
    assert response.status_code == 400
    assert "Username and password are required" in response.get_json().get('message', '')


# --- Test /api/auth/status ---

def test_status_when_logged_in(logged_in_client): # Uses 'pytest_seller' fixture
    """ GIVEN logged-in client; WHEN GET /status; THEN 200 """
    client = logged_in_client # Get the client provided by the fixture
    response = client.get('/api/auth/status')

    # Assert
    assert response.status_code == 200
    response_data = response.get_json()
    assert response_data['logged_in'] is True
    assert 'user' in response_data
    assert response_data['user']['username'] == "pytest_seller" # Matches user created in fixture
    assert response_data['user']['role'] == 'user'


def test_status_when_not_logged_in(client):
    """ GIVEN client not logged in; WHEN GET /status; THEN 401 """
    response = client.get('/api/auth/status')
    assert response.status_code == 401
    assert "Authentication required" in response.get_json().get('message', '')


# --- Test /api/auth/logout ---

def test_logout_success(logged_in_client):
    """ GIVEN logged-in client; WHEN POST /logout; THEN 200 and subsequent status is 401 """
    client = logged_in_client

    # Act: Logout request
    logout_response = client.post('/api/auth/logout')

    # Assert Logout
    assert logout_response.status_code == 200
    assert logout_response.get_json()['message'] == "Logout successful."

    # Act: Check status *after* logout
    status_response = client.get('/api/auth/status')

    # Assert Status after Logout
    assert status_response.status_code == 401
    assert "Authentication required" in status_response.get_json().get('message', '')


def test_logout_when_not_logged_in(client):
    """ WHEN POST /logout without being logged in; THEN 401 """
    response = client.post('/api/auth/logout')
    assert response.status_code == 401
    assert "Authentication required" in response.get_json().get('message', '')