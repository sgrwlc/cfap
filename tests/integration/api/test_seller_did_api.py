# tests/integration/api/test_seller_did_api.py
# -*- coding: utf-8 -*-
"""
Integration tests for the Seller DID Management endpoints (/api/seller/dids).
Tests rely on API calls for setup/modification and transactional fixture for rollback.
"""
import json
import pytest
import logging

from app.database.models import DidModel, UserModel
# Import UserService ONLY for creating other users if needed
from app.services.user_service import UserService
# Avoid importing DidService into tests, use API instead

log = logging.getLogger(__name__)

# Fixtures: client, session, db, logged_in_client (seller), logged_in_admin_client

# Helper to get seller ID
def get_seller_id(session):
    user = session.query(UserModel).filter_by(username="pytest_seller").one_or_none()
    assert user is not None, "Test setup failed: pytest_seller not found."
    return user.id

# Helper to create DID via API (using seller client)
def create_did_via_api(seller_client, number, description=None, status="active"):
    payload = {"number": number, "description": description, "status": status}
    response = seller_client.post('/api/seller/dids', json=payload)
    assert response.status_code == 201, f"Failed to create DID '{number}' via API: {response.data.decode()}"
    return response.get_json()

# --- Test GET /api/seller/dids ---

def test_seller_get_own_dids_list(logged_in_client, session):
    """ GIVEN seller owns DIDs; WHEN GET /dids; THEN 200 """
    # Arrange: Ensure DIDs exist via API calls
    did1_data = create_did_via_api(logged_in_client, "+15551001001", "Seller List API DID 1")
    did2_data = create_did_via_api(logged_in_client, "+15551001002", "Seller List API DID 2", status="inactive")
    # Create DID for another user (use service within transaction, will rollback)
    other_user = UserService.create_user("otherseller_list_api", "other_list_api@s.com", "Pass123")
    session.flush() # Need user ID
    # Can't use API easily for other user, so service call is okay here if necessary for setup
    # but avoid if test focus is purely on logged_in_client's view
    # DidService.add_did(user_id=other_user.id, number="+15554004004", description="Other Seller List DID")
    # session.flush()

    # Act
    response = logged_in_client.get('/api/seller/dids?page=1&per_page=5')

    # Assert
    assert response.status_code == 200
    data = response.get_json()
    # Total should reflect DIDs created via API in this test + any pre-existing from sample data for this user
    # Let's check >= 2
    assert data.get('total') >= 2
    assert len(data['items']) >= 2
    numbers_returned = {item['number'] for item in data['items']}
    assert did1_data['number'] in numbers_returned
    assert did2_data['number'] in numbers_returned
    assert "+15554004004" not in numbers_returned # Ensure other user's DID not present


def test_seller_get_own_dids_list_filtered(logged_in_client, session):
    """ GIVEN seller owns active/inactive DIDs; WHEN GET /dids?status=inactive; THEN 200 """
    # Arrange: Create DIDs via API
    create_did_via_api(logged_in_client, "+15552002001", "Seller Filter API Active", status="active")
    did_inactive_data = create_did_via_api(logged_in_client, "+15552002002", "Seller Filter API Inactive", status="inactive")

    # Act
    response = logged_in_client.get('/api/seller/dids?status=inactive')

    # Assert
    assert response.status_code == 200
    data = response.get_json()
    assert data.get('total') >= 1
    # Find our inactive DID in the results
    our_did = next((item for item in data['items'] if item['id'] == did_inactive_data['id']), None)
    assert our_did is not None
    assert our_did['number'] == did_inactive_data['number']
    assert our_did['status'] == 'inactive'


def test_seller_get_dids_unauthorized(client):
    """ GIVEN no user logged in; WHEN GET /dids; THEN 401 """
    response = client.get('/api/seller/dids')
    assert response.status_code == 401


# --- Test POST /api/seller/dids ---

def test_seller_add_did_success(logged_in_client, session):
    """ GIVEN seller logged in; WHEN POST /dids with valid data; THEN 201 """
    seller_id = get_seller_id(session)
    did_payload = {"number": "+17778889999", "description": "My New DID API", "status": "active"}

    # Act
    response = logged_in_client.post('/api/seller/dids', json=did_payload)

    # Assert Response
    assert response.status_code == 201
    data = response.get_json()
    assert data['number'] == did_payload['number']
    assert 'id' in data
    did_id = data['id']

    # Assert Database State
    did_db = session.get(DidModel, did_id)
    assert did_db is not None and did_db.user_id == seller_id


def test_seller_add_did_duplicate_fail(logged_in_client, session):
    """ GIVEN DID number exists; WHEN POST /dids with same number; THEN 409 """
    # Arrange: Create initial DID via API
    existing_number = "+17778881111"
    create_did_via_api(logged_in_client, existing_number)

    # Act: Attempt duplicate
    did_payload = { "number": existing_number, "description": "Duplicate API" }
    response = logged_in_client.post('/api/seller/dids', json=did_payload)

    # Assert
    assert response.status_code == 409
    assert f"DID number '{existing_number}' already exists" in response.get_json().get('message', '')


def test_seller_add_did_missing_number(logged_in_client):
    """ GIVEN missing number; WHEN POST /dids; THEN 400 """
    did_payload = { "description": "Missing number API" }
    response = logged_in_client.post('/api/seller/dids', json=did_payload)
    assert response.status_code == 400
    assert 'number' in response.get_json().get('errors', {})


def test_seller_add_did_invalid_format(logged_in_client):
    """ GIVEN invalid phone number format; WHEN POST /dids; THEN 400 """
    did_payload = {"number": "invalid-phone-api", "description": "Invalid Format API"}
    response = logged_in_client.post('/api/seller/dids', json=did_payload)
    assert response.status_code == 400
    errors = response.get_json().get('errors', {})
    assert 'number' in errors and any('format' in e.lower() for e in errors['number'])


# --- Test GET /api/seller/dids/{did_id} ---

def test_seller_get_own_did_success(logged_in_client, session):
    """ GIVEN seller owns DID; WHEN GET /dids/{id}; THEN 200 """
    # Arrange
    did_data = create_did_via_api(logged_in_client, "+15559990000", "Get Me API")
    target_id = did_data['id']

    # Act
    response = logged_in_client.get(f'/api/seller/dids/{target_id}')

    # Assert
    assert response.status_code == 200
    data = response.get_json()
    assert data['id'] == target_id
    assert data['number'] == "+15559990000"


def test_seller_get_other_did_fail(logged_in_client, session):
    """ GIVEN DID owned by another; WHEN GET /dids/{id}; THEN 404 """
    # Arrange: Create DID owned by another user (use service, will rollback)
    other_user = UserService.create_user("otherseller2_api", "other2_api@s.com", "Pass123")
    session.flush()
    # Need DidService temporarily if API creation isn't easy for other user
    from app.services.did_service import DidService
    other_did = DidService.add_did(user_id=other_user.id, number="+15559991111")
    session.flush() # Need ID
    target_id = other_did.id

    # Act
    response = logged_in_client.get(f'/api/seller/dids/{target_id}')

    # Assert
    assert response.status_code == 404
    assert f"DID with ID {target_id} not found or not owned by user" in response.get_json().get('message', '')


def test_seller_get_nonexistent_did_fail(logged_in_client):
    """ GIVEN non-existent ID; WHEN GET /dids/{id}; THEN 404 """
    response = logged_in_client.get('/api/seller/dids/99999')
    assert response.status_code == 404


# --- Test PUT /api/seller/dids/{did_id} ---

def test_seller_update_own_did_success(logged_in_client, session):
    """ GIVEN seller owns DID; WHEN PUT /dids/{id} with valid data; THEN 200 """
    # Arrange
    did_data = create_did_via_api(logged_in_client, "+15558880000", "Update Me API", status="active")
    target_id = did_data['id']
    update_payload = {"description": "UPDATED Desc API", "status": "inactive"}

    # Act
    response = logged_in_client.put(f'/api/seller/dids/{target_id}', json=update_payload)

    # Assert Response
    assert response.status_code == 200
    data = response.get_json()
    assert data['id'] == target_id
    assert data['description'] == "UPDATED Desc API"
    assert data['status'] == "inactive"

    # Assert Database
    did_db = session.get(DidModel, target_id)
    assert did_db is not None and did_db.description == "UPDATED Desc API" and did_db.status == "inactive"


def test_seller_update_other_did_fail(logged_in_client, session):
    """ GIVEN DID owned by another; WHEN PUT /dids/{id}; THEN 404/403 """
    # Arrange: Create DID owned by another user
    other_user = UserService.create_user("otherseller3_api", "other3_api@s.com", "Pass123")
    session.flush()
    from app.services.did_service import DidService
    other_did = DidService.add_did(user_id=other_user.id, number="+15558881111")
    session.flush()
    target_id = other_did.id
    update_payload = {"description": "Updated Desc API"}

    # Act
    response = logged_in_client.put(f'/api/seller/dids/{target_id}', json=update_payload)

    # Assert
    assert response.status_code in [403, 404] # Service raises ResourceNotFound -> maps to 404


# --- Test DELETE /api/seller/dids/{did_id} ---

def test_seller_delete_own_did_success(logged_in_client, session):
    """ GIVEN seller owns DID; WHEN DELETE /dids/{id}; THEN 204 """
    # Arrange
    did_data = create_did_via_api(logged_in_client, "+15557770000", "Delete Me API")
    target_id = did_data['id']
    assert session.get(DidModel, target_id) is not None # Verify exists

    # Act
    response = logged_in_client.delete(f'/api/seller/dids/{target_id}')

    # Assert Response
    assert response.status_code == 204

    # Assert Database
    assert session.get(DidModel, target_id) is None


def test_seller_delete_other_did_fail(logged_in_client, session):
    """ GIVEN DID owned by another; WHEN DELETE /dids/{id}; THEN 404/403 """
    # Arrange: Create DID owned by another user
    other_user = UserService.create_user("otherseller4_api", "other4_api@s.com", "Pass123")
    session.flush()
    from app.services.did_service import DidService
    other_did = DidService.add_did(user_id=other_user.id, number="+15557771111")
    session.flush()
    target_id = other_did.id

    # Act
    response = logged_in_client.delete(f'/api/seller/dids/{target_id}')

    # Assert
    assert response.status_code in [403, 404] # Service raises ResourceNotFound -> maps to 404