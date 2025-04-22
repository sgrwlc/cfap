# -*- coding: utf-8 -*-
"""
Integration tests for the Seller DID Management endpoints (/api/seller/dids).
"""
import json
import pytest

from app.database.models import DidModel, UserModel
from app.services.did_service import DidService # For test setup if needed
from app.services.user_service import UserService # For creating other users

# Fixtures: client, session, db, logged_in_client (logs in as 'pytest_seller'), logged_in_admin_client

# Helper function to get the ID of the logged-in test seller
def get_seller_id(session):
    user = session.query(UserModel).filter_by(username="pytest_seller").one_or_none()
    # If user doesn't exist yet (first test run using the fixture perhaps)
    if user is None:
         pytest.fail("FATAL: pytest_seller user not found. Check logged_in_client fixture setup.")
    return user.id

# Helper function to get the ID of the logged-in test admin
def get_admin_id(session):
    user = session.query(UserModel).filter_by(username="pytest_admin").one_or_none()
    if user is None:
         pytest.fail("FATAL: pytest_admin user not found. Check logged_in_admin_client fixture setup.")
    return user.id

# --- Test GET /api/seller/dids ---

def test_seller_get_own_dids_list(logged_in_client, session):
    """
    GIVEN seller client logged in and seller owns some DIDs
    WHEN GET /api/seller/dids is requested
    THEN check status 200 and only own DIDs are returned.
    """
    # Arrange: Ensure the logged-in seller ('pytest_seller') owns at least two DIDs
    seller_id = get_seller_id(session)
    did1_num = "+15551001001"
    did2_num = "+15551001002"
    # Add to session, DO NOT COMMIT
    did1 = DidService.add_did(user_id=seller_id, number=did1_num, description="Seller List DID 1")
    did2 = DidService.add_did(user_id=seller_id, number=did2_num, description="Seller List DID 2", status="inactive")
    other_user = UserService.create_user("otherseller_list", "other_list@s.com", "Pass123")
    DidService.add_did(user_id=other_user.id, number="+15554004004", description="Other Seller List DID")
    # Flush to get IDs if needed
    session.flush()
    print(f"DEBUG list: Created DID1 ID {did1.id}, DID2 ID {did2.id}")

    # Act
    response = logged_in_client.get('/api/seller/dids?page=1&per_page=5')

    # Assert
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data.get('total') == 2 # Should see the 2 DIDs added in this test's session
    assert len(data['items']) == 2
    numbers_returned = {item['number'] for item in data['items']}
    assert did1.number in numbers_returned
    assert did2.number in numbers_returned
    assert "+15554004004" not in numbers_returned


def test_seller_get_own_dids_list_filtered(logged_in_client, session):
    """
    GIVEN seller client logged in and seller owns active/inactive DIDs
    WHEN GET /api/seller/dids?status=inactive is requested
    THEN check status 200 and only own inactive DIDs are returned.
    """
    # Arrange: Ensure active and inactive DIDs exist for the seller in THIS test's scope
    seller_id = get_seller_id(session)
    # Use DIFFERENT unique numbers for this test's setup
    did_active_num = "+15552002001"
    did_inactive_num = "+15552002002"
    # Add to session, DO NOT COMMIT
    DidService.add_did(user_id=seller_id, number=did_active_num, description="Seller Filter Test DID Active", status="active")
    did_inactive = DidService.add_did(user_id=seller_id, number=did_inactive_num, description="Seller Filter Test DID Inactive", status="inactive")
    # Flush to ensure objects have IDs
    session.flush()
    print(f"DEBUG filter: Created inactive DID ID {did_inactive.id}")

    # Act
    response = logged_in_client.get('/api/seller/dids?status=inactive')

    # Assert
    assert response.status_code == 200
    data = json.loads(response.data)
    # Verify the DID we created is in the results
    assert data.get('total') >= 1

    # Find our DID in the results
    our_did = next((item for item in data['items'] if item['id'] == did_inactive.id), None)
    assert our_did is not None
    assert our_did['number'] == did_inactive.number
    assert our_did['status'] == 'inactive'


def test_seller_get_dids_unauthorized(client):
    """
    GIVEN no user logged in
    WHEN GET /api/seller/dids is requested
    THEN check status 401 Unauthorized.
    """
    response = client.get('/api/seller/dids')
    assert response.status_code == 401

def test_seller_get_dids_pagination(logged_in_client, session):
    """
    GIVEN seller client logged in and owns multiple DIDs
    WHEN GET /api/seller/dids?page=2&per_page=2 is requested
    THEN check correct page of results is returned.
    """
    seller_id = get_seller_id(session)
    
    # Create 5 DIDs to ensure we have enough for pagination
    for i in range(5):
        DidService.add_did(
            user_id=seller_id, 
            number=f"+1555666{i+1000}", 
            description=f"Pagination Test DID {i+1}"
        )
    session.flush()
    
    # Request page 2 with 2 items per page
    response = logged_in_client.get('/api/seller/dids?page=2&per_page=2')
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data.get('page') == 2
    assert data.get('perPage') == 2
    assert len(data['items']) == 2

def test_seller_get_dids_invalid_filter(logged_in_client):
    """
    GIVEN seller client logged in
    WHEN GET /api/seller/dids?status=nonexistent_status is requested
    THEN check API handles invalid filter gracefully.
    """
    response = logged_in_client.get('/api/seller/dids?status=nonexistent_status')
    
    # Either return empty results (200) or bad request (400)
    assert response.status_code in [200, 400]
    if response.status_code == 200:
        data = json.loads(response.data)
        assert data.get('total', 0) == 0

# --- Test POST /api/seller/dids ---

def test_seller_add_did_success(logged_in_client, session):
    """
    GIVEN seller client logged in
    WHEN POST /api/seller/dids with valid data
    THEN check status 201 Created and DID is added to DB for that seller.
    """
    # Arrange
    seller_id = get_seller_id(session)
    did_payload = {
        "number": "+17778889999",
        "description": "My New Campaign DID",
        "status": "active"
    }

    # Act
    response = logged_in_client.post('/api/seller/dids', json=did_payload)

    # Assert Response
    assert response.status_code == 201
    data = json.loads(response.data)
    assert data['number'] == did_payload['number']
    assert data['description'] == did_payload['description']
    assert data['status'] == did_payload['status']
    assert 'id' in data
    did_id = data['id']

    # Assert Database State (use session.get for pk lookup)
    did_db = session.get(DidModel, did_id)
    assert did_db is not None
    assert did_db.user_id == seller_id # Check ownership
    assert did_db.number == did_payload['number']
    assert did_db.description == did_payload['description']

def test_seller_add_did_duplicate_fail(logged_in_client, session):
    """
    GIVEN seller client logged in and a DID number exists
    WHEN POST /api/seller/dids with the same number
    THEN check status 409 Conflict.
    """
    # Arrange: Create initial DID without commit
    seller_id = get_seller_id(session)
    existing_number = "+17778881111"
    DidService.add_did(user_id=seller_id, number=existing_number)
    session.flush() # Flush is okay

    did_payload = { "number": existing_number, "description": "Duplicate" }

    # Act
    response = logged_in_client.post('/api/seller/dids', json=did_payload)

    # Assert
    assert response.status_code == 409
    data = json.loads(response.data)
    assert f"DID number '{existing_number}' already exists" in data.get('message', '')

def test_seller_add_did_missing_number(logged_in_client):
    """
    GIVEN seller client logged in
    WHEN POST /api/seller/dids without 'number' field
    THEN check status 400 Bad Request.
    """
    did_payload = { "description": "Missing number" }
    response = logged_in_client.post('/api/seller/dids', json=did_payload)
    assert response.status_code == 400
    data = json.loads(response.data)
    # Check key exists directly in response data
    assert 'number' in data
    assert data['number'] == ['Missing data for required field.']

def test_seller_add_did_invalid_format(logged_in_client):
    """
    GIVEN seller client logged in
    WHEN POST /api/seller/dids with invalid phone number format
    THEN check status 400 Bad Request.
    """
    did_payload = {
        "number": "invalid-phone",
        "description": "Invalid Format"
    }
    
    response = logged_in_client.post('/api/seller/dids', json=did_payload)
    
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'number' in data
    assert any('format' in error.lower() for error in data.get('number', []))

# --- Test GET /api/seller/dids/{did_id} ---

def test_seller_get_own_did_success(logged_in_client, session):
    """
    GIVEN seller client logged in and owns a specific DID
    WHEN GET /api/seller/dids/{did_id} is requested for that DID
    THEN check status 200 OK and correct DID details are returned.
    """
    # Arrange
    seller_id = get_seller_id(session)
    did = DidService.add_did(user_id=seller_id, number="+15559990000", description="Get Me")
    session.flush() # Flush to get ID
    target_id = did.id

    # Act
    response = logged_in_client.get(f'/api/seller/dids/{target_id}')

    # Assert
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['id'] == target_id
    assert data['number'] == "+15559990000"
    assert data['description'] == "Get Me"

def test_seller_get_other_did_fail(logged_in_client, session):
    """
    GIVEN seller client logged in
    WHEN GET /api/seller/dids/{did_id} is requested for a DID owned by another user
    THEN check status 404 Not Found.
    """
    # Arrange: Create DID owned by another user
    other_user = UserService.create_user("otherseller2", "other2@s.com", "Pass123")
    other_did = DidService.add_did(user_id=other_user.id, number="+15559991111")
    session.flush() # Flush to get ID
    target_id = other_did.id

    # Act
    response = logged_in_client.get(f'/api/seller/dids/{target_id}')

    # Assert
    assert response.status_code == 404
    data = json.loads(response.data)
    # Check specific message if service layer includes ownership check in get_did_by_id call from route
    assert f"DID with ID {target_id} not found or not owned by user" in data.get('message', '')

def test_seller_get_nonexistent_did_fail(logged_in_client):
    """
    GIVEN seller client logged in
    WHEN GET /api/seller/dids/{did_id} for a non-existent ID
    THEN check status 404 Not Found.
    """
    response = logged_in_client.get('/api/seller/dids/99999')
    assert response.status_code == 404


# --- Test PUT /api/seller/dids/{did_id} ---

def test_seller_update_own_did_success(logged_in_client, session):
    """
    GIVEN seller client logged in and owns a specific DID
    WHEN PUT /api/seller/dids/{did_id} with valid data for that DID
    THEN check status 200 OK and details are updated.
    """
    # Arrange
    seller_id = get_seller_id(session)
    did = DidService.add_did(user_id=seller_id, number="+15558880000", description="Update Me", status="active")
    session.flush() # Flush to get ID
    target_id = did.id
    update_payload = {"description": "UPDATED Desc", "status": "inactive"}

    # Act
    response = logged_in_client.put(f'/api/seller/dids/{target_id}', json=update_payload)

    # Assert Response
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['id'] == target_id
    assert data['description'] == "UPDATED Desc"
    assert data['status'] == "inactive"

    # Assert Database (Refresh object after API call which commits)
    session.refresh(did)
    assert did.description == "UPDATED Desc"
    assert did.status == "inactive"

def test_seller_update_other_did_fail(logged_in_client, session):
    """
    GIVEN seller client logged in
    WHEN PUT /api/seller/dids/{did_id} for a DID owned by another user
    THEN check status 403 Forbidden or 404 Not Found.
    """
    # Arrange
    other_user = UserService.create_user("otherseller3", "other3@s.com", "Pass123")
    other_did = DidService.add_did(user_id=other_user.id, number="+15558881111")
    session.flush() # Flush to get ID
    target_id = other_did.id
    update_payload = {"description": "Updated Description"} # Define the missing variable
    response = logged_in_client.put(f'/api/seller/dids/{target_id}', json=update_payload)

    # Assert (Service check should result in 403/404 depending on implementation)
    # Based on current DidService.update_did, it will likely be 404 first then 403 if ID exists but owned by other.
    assert response.status_code in [403, 404]

def test_seller_update_did_empty_description(logged_in_client, session):
    """
    GIVEN seller client logged in and owns a specific DID
    WHEN PUT /api/seller/dids/{did_id} with empty description
    THEN check status 400 Bad Request.
    """
    seller_id = get_seller_id(session)
    did = DidService.add_did(user_id=seller_id, number="+15558883333", description="")
    session.flush()
    target_id = did.id
    
    update_payload = {"description": ""}
    response = logged_in_client.put(f'/api/seller/dids/{target_id}', json=update_payload)
    
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'description' in data

# --- Test DELETE /api/seller/dids/{did_id} ---

def test_seller_delete_own_did_success(logged_in_client, session):
    """
    GIVEN seller client logged in and owns a specific DID
    WHEN DELETE /api/seller/dids/{did_id} for that DID
    THEN check status 204 No Content and DID is removed.
    """
    # Arrange
    seller_id = get_seller_id(session)
    did = DidService.add_did(user_id=seller_id, number="+15557770000", description="Delete Me")
    session.flush() # Flush to get ID
    target_id = did.id
    assert session.get(DidModel, target_id) is not None # Verify exists before API call

    # Act
    response = logged_in_client.delete(f'/api/seller/dids/{target_id}')

    # Assert Response
    assert response.status_code == 204

    # Assert Database (Check object is gone after API commit)
    assert session.get(DidModel, target_id) is None


def test_seller_delete_other_did_fail(logged_in_client, session):
    """
    GIVEN seller client logged in
    WHEN DELETE /api/seller/dids/{did_id} for a DID owned by another user
    THEN check status 403 Forbidden or 404 Not Found.
    """
    # Arrange
    other_user = UserService.create_user("otherseller4", "other4@s.com", "Pass123")
    other_did = DidService.add_did(user_id=other_user.id, number="+15557771111")
    session.flush() # Flush to get ID
    target_id = other_did.id
    response = logged_in_client.delete(f'/api/seller/dids/{target_id}')

    # Assert (Service check should result in 403/404 depending on implementation)
    assert response.status_code in [403, 404]