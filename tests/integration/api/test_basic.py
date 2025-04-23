# tests/integration/api/test_basic.py
# -*- coding: utf-8 -*-
"""
Basic integration tests for fundamental endpoints like health checks.
"""
import json # Import the json module to parse the response body
import pytest # Import pytest for testing framework

# Fixture 'client' is automatically injected by pytest from conftest.py

def test_health_check(client):
    """
    GIVEN a Flask application configured for testing
    WHEN the '/health' page is requested (GET)
    THEN check that the response is valid (200 OK) and indicates success.
    """
    # Act: Use the test client fixture to make a GET request
    response = client.get('/health')

    # Assert Status Code
    assert response.status_code == 200, f"Expected status code 200 but got {response.status_code}"

    # Assert Response Body Content
    try:
        response_data = json.loads(response.data)
        assert 'status' in response_data, "Response JSON missing 'status' key"
        assert response_data['status'] == 'ok', f"Expected status 'ok' but got '{response_data.get('status')}'"
        assert 'message' in response_data, "Response JSON missing 'message' key" # Check for message field added in __init__
    except json.JSONDecodeError:
        pytest.fail(f"Failed to decode JSON response: {response.data}")
    except AssertionError as e:
        pytest.fail(f"Assertion Failed: {e}. Response data: {response.data.decode()}")