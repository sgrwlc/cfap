# -*- coding: utf-8 -*-
"""
Basic integration tests for fundamental endpoints like health checks.
"""
import json # Import the json module to parse the response body

# Note: Fixtures like 'client' are automatically discovered and injected
# by pytest based on their names from conftest.py

def test_health_check(client):
    """
    GIVEN a Flask application configured for testing
    WHEN the '/health' page is requested (GET)
    THEN check that the response is valid and indicates success
    """
    # Use the test client fixture to make a GET request
    response = client.get('/health')

    # Assertions
    assert response.status_code == 200 # Check the HTTP status code

    # Parse the JSON response body
    response_data = json.loads(response.data)

    # Check the content of the response
    assert 'status' in response_data
    assert response_data['status'] == 'ok'