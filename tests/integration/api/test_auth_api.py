# -*- coding: utf-8 -*-
"""
Integration tests for the /api/auth endpoints.
"""
import json
import pytest # Import pytest if using markers etc.

from app.database.models.user import UserModel
from app.services.user_service import UserService # To potentially create users if needed

# Fixtures like 'client', 'session', 'db', 'logged_in_client', 'logged_in_admin_client'
# are automatically used when included as test function arguments.

# --- Test /api/auth/login ---

def test_login_success(client, session):
    """
    GIVEN a user created in the test database
    WHEN a POST request is made to /api/auth/login with correct credentials
    THEN check the response is 200 OK and contains user details and a success message.
    """
    # Arrange: Create a test user using the service (relies on session fixture)
    username = "logintestuser"
    password = "Password123!"
    email = "login@test.com"
    UserService.create_user(username=username, email=email, password=password, role='user', status='active')
    # No explicit commit needed here as the session fixture handles rollback

    # Act: Make login request
    response = client.post('/api/auth/login', json={
        'username': username,
        'password': password
    })

    # Assert
    assert response.status_code == 200
    response_data = json.loads(response.data)
    assert response_data['message'] == "Login successful."
    assert 'user' in response_data
    assert response_data['user']['username'] == username
    assert response_data['user']['email'] == email
    assert response_data['user']['role'] == 'user'
    assert response.headers.get('Set-Cookie') is not None # Check if session cookie is set

def test_login_fail_wrong_password(client, session):
    """
    GIVEN a user created in the test database
    WHEN a POST request is made to /api/auth/login with incorrect password
    THEN check the response is 401 Unauthorized.
    """
    # Arrange: Create user
    username = "wrongpassuser"
    password = "Password123!"
    UserService.create_user(username=username, email="wrongpass@test.com", password=password, role='user', status='active')

    # Act: Make login request with wrong password
    response = client.post('/api/auth/login', json={
        'username': username,
        'password': "WrongPassword!"
    })

    # Assert
    assert response.status_code == 401
    response_data = json.loads(response.data)
    assert "Invalid username or password" in response_data['message']

def test_login_fail_inactive_user(client, session):
    """
    GIVEN an inactive user created in the test database
    WHEN a POST request is made to /api/auth/login with correct credentials
    THEN check the response is 401 Unauthorized.
    """
    # Arrange: Create inactive user
    username = "inactiveuser"
    password = "Password123!"
    UserService.create_user(username=username, email="inactive@test.com", password=password, role='user', status='inactive')

    # Act: Make login request
    response = client.post('/api/auth/login', json={
        'username': username,
        'password': password
    })

    # Assert
    assert response.status_code == 401
    response_data = json.loads(response.data)
    assert "Invalid username or password, or inactive account" in response_data['message']


def test_login_fail_missing_username(client):
    """
    WHEN a POST request is made to /api/auth/login without a username
    THEN check the response is 400 Bad Request.
    """
    response = client.post('/api/auth/login', json={
        'password': "Password123!"
    })
    assert response.status_code == 400
    response_data = json.loads(response.data)
    assert "Username and password are required" in response_data['message']


def test_login_fail_missing_password(client):
    """
    WHEN a POST request is made to /api/auth/login without a password
    THEN check the response is 400 Bad Request.
    """
    response = client.post('/api/auth/login', json={
        'username': "someuser"
    })
    assert response.status_code == 400
    response_data = json.loads(response.data)
    assert "Username and password are required" in response_data['message']


# --- Test /api/auth/status ---

def test_status_when_logged_in(logged_in_client):
    """
    GIVEN a logged-in client (using the fixture)
    WHEN a GET request is made to /api/auth/status
    THEN check the response is 200 OK and contains logged-in user details.
    """
    # Act: logged_in_client fixture handles login
    client = logged_in_client # Get the client provided by the fixture
    response = client.get('/api/auth/status')

    # Assert
    assert response.status_code == 200
    response_data = json.loads(response.data)
    assert response_data['logged_in'] is True
    assert 'user' in response_data
    assert response_data['user']['username'] == "pytest_seller" # Matches user created in fixture
    assert response_data['user']['role'] == 'user'

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
    assert "Authentication required" in response_data['message']


# --- Test /api/auth/logout ---

def test_logout_success(logged_in_client):
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
    assert "Authentication required" in status_data['message']


def test_logout_when_not_logged_in(client):
    """
    WHEN a POST request is made to /api/auth/logout without being logged in
    THEN check the response is 401 Unauthorized.
    """
    # Act: Make logout request
    response = client.post('/api/auth/logout')

    # Assert
    assert response.status_code == 401 # @login_required decorator prevents access
    response_data = json.loads(response.data)
    assert "Authentication required" in response_data['message']