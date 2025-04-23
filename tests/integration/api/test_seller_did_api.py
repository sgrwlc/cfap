# tests/integration/api/test_seller_did_api.py
# -*- coding: utf-8 -*-
"""
Integration tests for the Seller DID Management endpoints (/api/seller/dids),
aligned with refactored services and routes.
"""
import json
import pytest
import logging

from app.database.models import DidModel, UserModel
from app.services.did_service import DidService # For setup within session fixture
from app.services.user_service import UserService # For creating other users

log = logging.getLogger(__name__)

# Fixtures: client, session, db, logged_in_client (seller), logged_in_admin_client

# Helper function to get the ID of the logged-in test seller
def get_seller_id(session):
    user = session.query(UserModel).filter_by(username="pytest_seller").one()
    return user.id

# Helper to create DID via service for setup (relies on session fixture rollback)
def create_did_via_service(session, user_id, number, **kwargs):
    did = DidService.add_did(user_id=user_id, number=number, **kwargs)
    session.flush() # Ensure ID is available
    log.debug(f"Setup: Created DID '{number}' (ID: {did.id}) for user {user_id} via service.")
    return did

# --- Test GET /api/seller/dids ---

def test_seller_get_own_dids_list(logged_in_client, session):
    """
    GIVEN seller client logged in and seller owns DIDs
    WHEN GET /api/seller/dids requested
    THEN check status 200 and only own DIDs are returned.
    """
    log.debug("Running test_seller_get_own_dids_list")
    # Arrange: Create DIDs via service within session transaction
    seller_id = get_seller_id(session)
    did1 = create_did_via_service(session, seller_id, "+15551001001", description="Seller List DID 1")
    did2 = create_did_via_service(session, seller_id, "+15551001002", description="Seller List DID 2", status="inactive")
    # Create DID for another user (should not appear)
    other_user = UserService.create_user("otherseller_list", "other_list@s.com", "Pass123")
    session.flush()
    create_did_via_service(session, other_user.id, "+15554004004", description="Other Seller List DID")

    # Act: Call API
    response = logged_in_client.get('/api/seller/dids?page=1&per_page=10')

    # Assert
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data.get('total') == 2 # Only the 2 for pytest_seller
    assert len(data['items']) == 2
    numbers_returned = {item['number'] for item in data['items']}
    assert did1.number in numbers_returned
    assert did2.number in numbers_returned
    assert "+15554004004" not in numbers_returned
    log.debug("Finished test_seller_get_own_dids_list")


def test_seller_get_own_dids_list_filtered(logged_in_client, session):
    """
    GIVEN seller client logged in and seller owns active/inactive DIDs
    WHEN GET /api/seller/dids?status=inactive requested
    THEN check status 200 and only own inactive DIDs are returned.
    """
    log.debug("Running test_seller_get_own_dids_list_filtered")
    # Arrange
    seller_id = get_seller_id(session)
    create_did_via_service(session, seller_id, "+15552002001", status="active")
    did_inactive = create_did_via_service(session, seller_id, "+15552002002", status="inactive")

    # Act
    response = logged_in_client.get('/api/seller/dids?status=inactive')

    # Assert
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data.get('total') == 1
    assert len(data['items']) == 1
    assert data['items'][0]['id'] == did_inactive.id
    assert data['items'][0]['status'] == 'inactive'
    log.debug("Finished test_seller_get_own_dids_list_filtered")


def test_seller_get_dids_unauthorized(client):
    """
    GIVEN no user logged in
    WHEN GET /api/seller/dids requested
    THEN check status 401 Unauthorized.
    """
    response = client.get('/api/seller/dids')
    assert response.status_code == 401


# --- Test POST /api/seller/dids ---

def test_seller_add_did_success(logged_in_client, session):
    """
    GIVEN seller client logged in
    WHEN POST /api/seller/dids with valid data
    THEN check status 201 Created and DID added to DB for that seller.
    """
    log.debug("Running test_seller_add_did_success")
    seller_id = get_seller_id(session)
    did_payload = {
        "number": "+17778889999",
        "description": "My New Campaign DID",
        "status": "active"
    }

    # Act: Call API (handles commit)
    response = logged_in_client.post('/api/seller/dids', json=did_payload)

    # Assert Response
    assert response.status_code == 201
    data = json.loads(response.data)
    assert data['number'] == did_payload['number']
    assert data['description'] == did_payload['description']
    assert 'id' in data
    did_id = data['id']

    # Assert Database State
    did_db = session.get(DidModel, did_id) # Use session.get after API commit
    assert did_db is not None
    assert did_db.user_id == seller_id
    assert did_db.number == did_payload['number']
    log.debug("Finished test_seller_add_did_success")


def test_seller_add_did_duplicate_fail(logged_in_client, session):
    """
    GIVEN seller client logged in and a DID number exists
    WHEN POST /api/seller/dids with the same number
    THEN check status 409 Conflict.
    """
    # Arrange: Create initial DID via service
    seller_id = get_seller_id(session)
    existing_number = "+17778881111"
    create_did_via_service(session, seller_id, existing_number)

    did_payload = { "number": existing_number, "description": "Duplicate" }

    # Act: Call API
    response = logged_in_client.post('/api/seller/dids', json=did_payload)

    # Assert: Route catches ConflictError
    assert response.status_code == 409
    data = json.loads(response.data)
    assert f"DID number '{existing_number}' already exists" in data.get('message', '')


def test_seller_add_did_missing_number(logged_in_client):
    """
    GIVEN seller client logged in
    WHEN POST /api/seller/dids without 'number' field
    THEN check status 400 Bad Request (schema validation).
    """
    did_payload = { "description": "Missing number" }
    response = logged_in_client.post('/api/seller/dids', json=did_payload)
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'errors' in data and 'number' in data['errors']


def test_seller_add_did_invalid_format(logged_in_client):
    """
    GIVEN seller client logged in
    WHEN POST /api/seller/dids with invalid phone number format
    THEN check status 400 Bad Request (schema validation).
    """
    did_payload = {"number": "invalid-phone", "description": "Invalid Format"}
    response = logged_in_client.post('/api/seller/dids', json=did_payload)
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'errors' in data and 'number' in data['errors']
    assert "invalid phone number format" in data['errors']['number'][0].lower()


# --- Test GET /api/seller/dids/{did_id} ---

def test_seller_get_own_did_success(logged_in_client, session):
    """
    GIVEN seller client logged in and owns a specific DID
    WHEN GET /api/seller/dids/{did_id} requested
    THEN check status 200 OK and correct DID details returned.
    """
    # Arrange
    seller_id = get_seller_id(session)
    did = create_did_via_service(session, seller_id, "+15559990000", description="Get Me")
    target_id = did.id

    # Act
    response = logged_in_client.get(f'/api/seller/dids/{target_id}')

    # Assert
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['id'] == target_id
    assert data['number'] == "+15559990000"


def test_seller_get_other_did_fail(logged_in_client, session):
    """
    GIVEN seller client logged in
    WHEN GET /api/seller/dids/{did_id} for DID owned by another user
    THEN check status 404 Not Found.
    """
    # Arrange: Create DID owned by another user
    other_user = UserService.create_user("otherseller2", "other2@s.com", "Pass123")
    session.flush()
    other_did = create_did_via_service(session, other_user.id, "+15559991111")
    target_id = other_did.id

    # Act
    response = logged_in_client.get(f'/api/seller/dids/{target_id}')

    # Assert: Service check within route leads to 404
    assert response.status_code == 404
    data = json.loads(response.data)
    assert f"DID with ID {target_id} not found or not owned by user" in data.get('message', '')


def test_seller_get_nonexistent_did_fail(logged_in_client):
    """
    GIVEN seller client logged in
    WHEN GET /api/seller/dids/{did_id} for non-existent ID
    THEN check status 404 Not Found.
    """
    response = logged_in_client.get('/api/seller/dids/999999')
    assert response.status_code == 404


# --- Test PUT /api/seller/dids/{did_id} ---

def test_seller_update_own_did_success(logged_in_client, session):
    """
    GIVEN seller client logged in and owns a specific DID
    WHEN PUT /api/seller/dids/{did_id} with valid data
    THEN check status 200 OK and details are updated.
    """
    # Arrange
    seller_id = get_seller_id(session)
    did = create_did_via_service(session, seller_id, "+15558880000", description="Update Me", status="active")
    target_id = did.id
    update_payload = {"description": "UPDATED Desc", "status": "inactive"}

    # Act: Call API (handles commit)
    response = logged_in_client.put(f'/api/seller/dids/{target_id}', json=update_payload)

    # Assert Response
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['description'] == "UPDATED Desc"
    assert data['status'] == "inactive"

    # Assert Database
    did_db = session.get(DidModel, target_id) # Re-fetch
    assert did_db.description == "UPDATED Desc"
    assert did_db.status == "inactive"


def test_seller_update_other_did_fail(logged_in_client, session):
    """
    GIVEN seller client logged in
    WHEN PUT /api/seller/dids/{did_id} for DID owned by another user
    THEN check status 403 Forbidden (or 404 if service checks that first).
    """
    # Arrange
    other_user = UserService.create_user("otherseller3", "other3@s.com", "Pass123")
    session.flush()
    other_did = create_did_via_service(session, other_user.id, "+15558881111")
    target_id = other_did.id
    update_payload = {"description": "Updated Description"}

    # Act
    response = logged_in_client.put(f'/api/seller/dids/{target_id}', json=update_payload)

    # Assert: Route catches ResourceNotFound or AuthorizationError
    assert response.status_code in [403, 404]


def test_seller_update_did_invalid_status_fail(logged_in_client, session):
    """
    GIVEN seller client logged in and owns a specific DID
    WHEN PUT /api/seller/dids/{did_id} with invalid status
    THEN check status 400 Bad Request (schema validation).
    """
    # Arrange
    seller_id = get_seller_id(session)
    did = create_did_via_service(session, seller_id, "+15558882222", status="active")
    target_id = did.id
    update_payload = {"status": "invalid_status"}

    # Act
    response = logged_in_client.put(f'/api/seller/dids/{target_id}', json=update_payload)

    # Assert
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'errors' in data and 'status' in data['errors']


# --- Test DELETE /api/seller/dids/{did_id} ---

def test_seller_delete_own_did_success(logged_in_client, session):
    """
    GIVEN seller client logged in and owns a specific DID
    WHEN DELETE /api/seller/dids/{did_id} requested
    THEN check status 204 No Content and DID is removed.
    """
    # Arrange
    seller_id = get_seller_id(session)
    did = create_did_via_service(session, seller_id, "+15557770000", description="Delete Me")
    target_id = did.id
    assert session.get(DidModel, target_id) is not None # Verify setup

    # Act: Call API (handles commit)
    response = logged_in_client.delete(f'/api/seller/dids/{target_id}')

    # Assert Response
    assert response.status_code == 204

    # Assert Database
    assert session.get(DidModel, target_id) is None


def test_seller_delete_other_did_fail(logged_in_client, session):
    """
    GIVEN seller client logged in
    WHEN DELETE /api/seller/dids/{did_id} for DID owned by another user
    THEN check status 403 Forbidden or 404 Not Found.
    """
    # Arrange
    other_user = UserService.create_user("otherseller4", "other4@s.com", "Pass123")
    session.flush()
    other_did = create_did_via_service(session, other_user.id, "+15557771111")
    target_id = other_did.id

    # Act
    response = logged_in_client.delete(f'/api/seller/dids/{target_id}')

    # Assert: Route catches ResourceNotFound or AuthorizationError
    assert response.status_code in [403, 404]


def test_seller_delete_nonexistent_did_fail(logged_in_client):
    """
    GIVEN seller client logged in
    WHEN DELETE /api/seller/dids/{did_id} for non-existent ID
    THEN check status 404 Not Found.
    """
    response = logged_in_client.delete('/api/seller/dids/999999')
    assert response.status_code == 404
