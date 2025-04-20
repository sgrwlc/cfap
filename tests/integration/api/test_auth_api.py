# -*- coding: utf-8 -*-
"""
Tests for the Authentication API endpoints (/api/auth).
"""
import pytest
from flask import url_for

class TestAuthApi:

    def test_login_success(self, client, seller_user):
        """Test successful login."""
        res = client.post(url_for('auth_api.login'), json={
            'username': seller_user.username,
            'password': 'password123'
        })
        assert res.status_code == 200
        assert 'access_token' not in res.json # Assuming no JWT for now
        assert res.json['message'] == 'Login successful.'
        assert res.json['user']['username'] == seller_user.username
        assert res.json['user']['role'] == 'user'
        # Check cookie is set? Harder to test directly, rely on subsequent requests

    def test_login_failure_wrong_password(self, client, seller_user):
        """Test login with incorrect password."""
        res = client.post(url_for('auth_api.login'), json={
            'username': seller_user.username,
            'password': 'wrongpassword'
        })
        assert res.status_code == 401 # Unauthorized
        assert res.json['message'] == 'Invalid username or password, or inactive account.'

    def test_login_failure_wrong_username(self, client):
        """Test login with non-existent username."""
        res = client.post(url_for('auth_api.login'), json={
            'username': 'nosuchuser',
            'password': 'password123'
        })
        assert res.status_code == 401
        assert res.json['message'] == 'Invalid username or password, or inactive account.'

    def test_login_missing_fields(self, client):
        """Test login with missing username or password."""
        res_no_user = client.post(url_for('auth_api.login'), json={'password': 'password123'})
        assert res_no_user.status_code == 400
        assert 'Username and password are required' in res_no_user.json['message']

        res_no_pass = client.post(url_for('auth_api.login'), json={'username': 'test'})
        assert res_no_pass.status_code == 400
        assert 'Username and password are required' in res_no_pass.json['message']

    def test_logout_success(self, logged_in_client, seller_user):
        """Test successful logout."""
        # First check status while logged in
        res_status = logged_in_client.get(url_for('auth_api.status'))
        assert res_status.status_code == 200
        assert res_status.json['logged_in'] is True
        assert res_status.json['user']['username'] == seller_user.username

        # Perform logout
        res_logout = logged_in_client.post(url_for('auth_api.logout'))
        assert res_logout.status_code == 200
        assert res_logout.json['message'] == 'Logout successful.'

        # Check status again - should be unauthorized
        res_status_after = logged_in_client.get(url_for('auth_api.status'))
        assert res_status_after.status_code == 401 # Unauthorized now
        assert 'Authentication required' in res_status_after.json['message']

    def test_logout_not_logged_in(self, client):
        """Test logout attempt when not logged in."""
        res = client.post(url_for('auth_api.logout'))
        assert res.status_code == 401 # Unauthorized

    def test_status_logged_in(self, logged_in_client, seller_user):
        """Test /status endpoint when logged in."""
        res = logged_in_client.get(url_for('auth_api.status'))
        assert res.status_code == 200
        assert res.json['logged_in'] is True
        assert res.json['user']['username'] == seller_user.username
        assert res.json['user']['role'] == 'user'

    def test_status_not_logged_in(self, client):
        """Test /status endpoint when not logged in."""
        res = client.get(url_for('auth_api.status'))
        assert res.status_code == 401 # Unauthorized