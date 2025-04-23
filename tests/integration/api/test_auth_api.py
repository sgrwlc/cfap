# tests/integration/api/test_auth_api.py
# -*- coding: utf-8 -*-
"""
Integration tests for the /api/auth endpoints, aligned with refactored services.
"""
import json
import pytest
import logging

# Import User model for type checking if needed, and Service for setup
from app.database.models.user import UserModel
from app.services.user_service import UserService

log = logging.getLogger(__name__)

# Fixtures 'client', 'session', 'db', 'logged_in_client', 'logged_in_admin_client' used.

# --- Test /api/auth/login ---

def test_login_success(client, session):
    """
    GIVEN a user created in the test database via service (no commit)
    WHEN a POST request is made to /api/auth/login with correct credentials
    THEN check the response is 200 OK and contains expected user details
         and the session cookie is set on the client.
    """
    log.debug("Running test_login_success")
    # Arrange: Create a test user using the service within the transaction
    username = "logintestuser_phase5"
    password = "Password123!"
    email = "login_p5@test.com"
    user = UserService.create_user(username=username, email=email, password=password, role='user', status='active')
    session.flush()

    # Act: Make login request
    response = client.post('/api/auth/login', json={
        'username': username,
        'password': password
    })

    # Assert Response Status and Body
    assert response.status_code == 200, f"Login failed: {response.data.decode()}"
    response_data = json.loads(response.data)
    assert response_data['message'] == "Login successful."
    assert 'user' in response_data
    assert response_data['user']['username'] == username
    assert response_data['user']['email'] == email
    assert response_data['user']['role'] == 'user'
    assert response_data['user']['status'] == 'active'

    # Assert Cookies using response headers (checking presence, not full validation)
    cookies_set = response.headers.getlist('Set-Cookie')
    log.debug(f"Set-Cookie headers received: {cookies_set}")

    session_cookie_found = any(cookie.strip().startswith('session=') for cookie in cookies_set)
    # Check for remember token set by login_user(remember=True)
    remember_cookie_found = any(cookie.strip().startswith('remember_token=') for cookie in cookies_set)

    # Assert that both the session cookie and remember token were set
    assert session_cookie_found, "Session cookie was not found in Set-Cookie headers."
    # Since we used remember=True, also check for the remember token
    assert remember_cookie_found, "Remember token cookie was not found in Set-Cookie headers."
    log.debug("Finished test_login_success")

    # Assert that at least the session cookie was set
    assert session_cookie_found, "Session cookie was not set on the client after login."
    # Since we used remember=True, also check for the remember token
    assert remember_cookie_found, "Remember token cookie was not set on the client after login with remember=True."
    log.debug("Finished test_login_success")


# --- Other tests remain the same ---

def test_login_fail_wrong_password(client, session):
    """
    GIVEN a user created in the test database
    WHEN a POST request is made to /api/auth/login with incorrect password
    THEN check the response is 401 Unauthorized with appropriate message.
    """
    # Arrange: Create user
    username = "wrongpassuser_p5"
    password = "Password123!"
    UserService.create_user(username=username, email="wrongpass_p5@test.com", password=password, role='user', status='active')
    session.flush()

    # Act: Make login request with wrong password
    response = client.post('/api/auth/login', json={
        'username': username,
        'password': "WrongPassword!"
    })

    # Assert
    assert response.status_code == 401
    response_data = json.loads(response.data)
    assert "Invalid username or password" in response_data.get('message', '')

def test_login_fail_inactive_user(client, session):
    """
    GIVEN an inactive user created in the test database
    WHEN a POST request is made to /api/auth/login with correct credentials
    THEN check the response is 401 Unauthorized with appropriate message.
    """
    # Arrange: Create inactive user
    username = "inactiveuser_p5"
    password = "Password123!"
    UserService.create_user(username=username, email="inactive_p5@test.com", password=password, role='user', status='inactive')
    session.flush()

    # Act: Make login request
    response = client.post('/api/auth/login', json={
        'username': username,
        'password': password
    })

    # Assert
    assert response.status_code == 401
    response_data = json.loads(response.data)
    assert "User account is inactive" in response_data.get('message', '')

def test_login_fail_user_not_found(client, session):
    """
    GIVEN no user exists with the provided username
    WHEN a POST request is made to /api/auth/login
    THEN check the response is 401 Unauthorized.
    """
    # Act: Attempt login with non-existent username
    response = client.post('/api/auth/login', json={
        'username': "nonexistentuser_p5",
        'password': "Password123!"
    })

    # Assert
    assert response.status_code == 401
    response_data = json.loads(response.data)
    assert "Invalid username or password" in response_data.get('message', '')

def test_login_fail_missing_username(client):
    """
    WHEN a POST request is made to /api/auth/login without a username
    THEN check the response is 400 Bad Request (schema validation).
    """
    response = client.post('/api/auth/login', json={
        'password': "Password123!"
    })
    assert response.status_code == 400
    response_data = json.loads(response.data)
    assert 'errors' in response_data
    assert 'username' in response_data['errors']

def test_login_fail_missing_password(client):
    """
    WHEN a POST request is made to /api/auth/login without a password
    THEN check the response is 400 Bad Request (schema validation).
    """
    response = client.post('/api/auth/login', json={
        'username': "someuser_p5"
    })
    assert response.status_code == 400
    response_data = json.loads(response.data)
    assert 'errors' in response_data
    assert 'password' in response_data['errors']


# --- Test /api/auth/status ---

def test_status_when_logged_in(logged_in_client): # Uses fixture
    """
    GIVEN a logged-in client (using the fixture 'logged_in_client')
    WHEN a GET request is made to /api/auth/status
    THEN check the response is 200 OK and contains correct logged-in user details.
    """
    # Act: logged_in_client fixture handles login
    client = logged_in_client # Get the client provided by the fixture
    response = client.get('/api/auth/status')

    # Assert
    assert response.status_code == 200
    response_data = json.loads(response.data)
    assert response_data.get('logged_in') is True
    assert 'user' in response_data
    assert response_data['user']['username'] == "pytest_seller" # Matches user created in fixture
    assert response_data['user']['role'] == 'user'
    assert response_data['user']['status'] == 'active'

def test_status_when_not_logged_in(client):
    """
    GIVEN a client that is not logged in
    WHEN a GET request is made to /api/auth/status
    THEN check the response is 401 Unauthorized.
    """
    # Act: Use the basic, non-logged-in client
    response = client.get('/api/auth/status')

    # Assert
    assert response.status_code == 401
    response_data = json.loads(response.data)
    assert "Authentication required" in response_data.get('message', '')


# --- Test /api/auth/logout ---

def test_logout_success(logged_in_client): # Uses fixture
    """
    GIVEN a logged-in client (using the fixture)
    WHEN a POST request is made to /api/auth/logout
    THEN check the response is 200 OK and subsequent status check returns 401.
    """
    client = logged_in_client

    # Act: Logout request
    logout_response = client.post('/api/auth/logout')

    # Assert Logout
    assert logout_response.status_code == 200
    logout_data = json.loads(logout_response.data)
    assert logout_data['message'] == "Logout successful."

    # Act: Check status *after* logout using the same client instance
    status_response = client.get('/api/auth/status')

    # Assert Status after Logout
    assert status_response.status_code == 401
    status_data = json.loads(status_response.data)
    assert "Authentication required" in status_data.get('message', '')


def test_logout_when_not_logged_in(client):
    """
    WHEN a POST request is made to /api/auth/logout without being logged in
    THEN check the response is 401 Unauthorized.
    """
    # Act: Make logout request using non-authenticated client
    response = client.post('/api/auth/logout')

    # Assert
    assert response.status_code == 401 # @login_required decorator triggers unauthorized handler
    response_data = json.loads(response.data)
    assert "Authentication required" in response_data.get('message', '')