# tests/integration/api/test_basic.py
# -*- coding: utf-8 -*-
"""
Basic integration tests for fundamental endpoints like health checks.
"""
import json

# Note: Fixture 'client' is automatically discovered and injected by pytest.

def test_health_check(client):
    """
    GIVEN a Flask application configured for testing
    WHEN the '/health' page is requested (GET)
    THEN check that the response is valid (200 OK) and indicates success.
    """
    # Act: Use the test client fixture to make a GET request
    response = client.get('/health')

    # Assertions
    assert response.status_code == 200 # Check the HTTP status code

    # Parse the JSON response body
    response_data = response.get_json() # Use Flask's get_json() helper

    # Check the content of the response
    assert response_data is not None
    assert response_data.get('status') == 'ok'
    assert "Application is running" in response_data.get('message', '')