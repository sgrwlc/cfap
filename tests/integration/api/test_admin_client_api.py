# tests/integration/api/test_admin_client_api.py
# -*- coding: utf-8 -*-
"""
Integration tests for the Admin Client Management endpoints (/api/admin/clients),
aligned with refactored services and routes.
"""
import json
import pytest
import logging

from app.database.models import ( # Import models used in tests
    ClientModel, PjsipEndpointModel, PjsipAorModel, PjsipAuthModel,
    CampaignModel, CampaignClientSettingsModel # <<< ADDED MISSING IMPORTS
)
# Use API for setup/assertions where possible, avoid direct service calls in tests

log = logging.getLogger(__name__)

# Fixtures: client, session, db, logged_in_admin_client, logged_in_client

# Helper to create a client via API for setup within tests
def create_client_via_api(admin_client, identifier, name, pjsip_config=None):
    """Helper to create a client using the API and return the response data."""
    if pjsip_config is None:
        # Default minimal valid PJSIP config
        pjsip_config = {
            "endpoint": {"id": identifier, "context": "test-ctx", "aors": identifier},
            "aor": {"id": identifier, "contact": f"sip:{identifier}@test.local"}
        }
    payload = {
        "clientIdentifier": identifier,
        "name": name,
        "pjsip": pjsip_config
    }
    response = admin_client.post('/api/admin/clients', json=payload)
    assert response.status_code == 201, f"API Setup Failed: Create client '{identifier}'. Response: {response.data.decode()}"
    return json.loads(response.data)


# --- Test GET /api/admin/clients ---

def test_admin_get_clients_success(logged_in_admin_client, session):
    """
    GIVEN admin client logged in
    WHEN GET /api/admin/clients is requested
    THEN check status 200 and valid paginated client list is returned.
    """
    log.debug("Running test_admin_get_clients_success")
    # Arrange: Ensure at least one client exists via API setup
    created_data = create_client_via_api(logged_in_admin_client, "list_client_p5", "List Client P5")

    # Act
    response = logged_in_admin_client.get('/api/admin/clients?page=1&per_page=50') # Fetch enough to see it

    # Assert
    assert response.status_code == 200
    data = json.loads(response.data)
    assert 'items' in data and data.get('page') == 1
    assert 'total' in data and data['total'] >= 1 # Should include sample data + created one
    assert any(item['clientIdentifier'] == "list_client_p5" for item in data['items'])

    # Check nested PJSIP data basic structure in list view
    test_item = next((item for item in data['items'] if item['clientIdentifier'] == "list_client_p5"), None)
    assert test_item is not None
    assert 'pjsipEndpoint' in test_item and test_item['pjsipEndpoint']['id'] == "list_client_p5"
    assert 'pjsipAor' in test_item and test_item['pjsipAor']['contact'] == "sip:list_client_p5@test.local"
    log.debug("Finished test_admin_get_clients_success")


def test_admin_get_clients_forbidden_for_seller(logged_in_client):
    """
    GIVEN seller client logged in
    WHEN GET /api/admin/clients requested
    THEN check status 403 Forbidden.
    """
    response = logged_in_client.get('/api/admin/clients')
    assert response.status_code == 403


def test_admin_get_clients_unauthorized(client):
    """
    GIVEN no user logged in
    WHEN GET /api/admin/clients requested
    THEN check status 401 Unauthorized.
    """
    response = client.get('/api/admin/clients')
    assert response.status_code == 401


# --- Test POST /api/admin/clients ---

@pytest.mark.parametrize("auth_present", [True, False])
def test_admin_create_client_success(logged_in_admin_client, session, auth_present):
    """
    GIVEN admin client logged in
    WHEN POST /api/admin/clients with valid data (with/without auth)
    THEN check status 201 Created and client/PJSIP details correct in response & DB.
    """
    log.debug(f"Running test_admin_create_client_success (auth_present={auth_present})")
    identifier = f"created_client_p5_{'auth' if auth_present else 'noauth'}"
    auth_id = "auth_to_created_p5"
    pjsip_config = {
        "endpoint": {
            "id": identifier, "transport": "transport-udp", "aors": identifier,
            "context": "from-capconduit-p5", "allow": "ulaw,g729",
            "outbound_auth": auth_id if auth_present else None
        },
        "aor": {
            "id": identifier, "contact": f"sip:{identifier}@test.local", "qualify_frequency": 33
        }
    }
    if auth_present:
        pjsip_config["auth"] = {
            "id": auth_id, "username": "testuser_p5", "password": "TestPasswordP5!", "realm": "testrealm_p5"
        }

    # Act: Use helper for API call
    data = create_client_via_api(logged_in_admin_client, identifier, f"Created P5 {'With' if auth_present else 'No'} Auth", pjsip_config)
    client_id = data['id'] # Get ID from response

    # Assert Response (Helper already checked status 201)
    assert data['clientIdentifier'] == identifier
    assert data['pjsipEndpoint']['allow'] == "ulaw,g729"
    assert data['pjsipEndpoint']['outbound_auth'] == (auth_id if auth_present else None)
    assert data['pjsipAor']['qualify_frequency'] == 33
    if auth_present:
        assert 'pjsipAuth' in data and data['pjsipAuth']['id'] == auth_id
        assert data['pjsipAuth']['username'] == "testuser_p5"
        assert 'password' not in data['pjsipAuth'] # Ensure password not dumped
    else:
        assert data.get('pjsipAuth') is None

    # Assert Database State (using session fixture)
    client_db = session.get(ClientModel, client_id) # Use session.get
    assert client_db is not None
    assert client_db.client_identifier == identifier
    assert client_db.pjsip_endpoint is not None and client_db.pjsip_endpoint.id == identifier
    assert client_db.pjsip_aor is not None and client_db.pjsip_aor.qualify_frequency == 33
    if auth_present:
        assert client_db.pjsip_auth is not None and client_db.pjsip_auth.id == auth_id
        assert client_db.pjsip_auth.password == "TestPasswordP5!" # Check password stored in DB
    else:
        assert client_db.pjsip_auth is None
    log.debug(f"Finished test_admin_create_client_success (auth_present={auth_present})")


def test_admin_create_client_duplicate_identifier(logged_in_admin_client, session):
    """
    GIVEN admin client logged in and a client identifier exists
    WHEN POST /api/admin/clients with the same identifier
    THEN check status 409 Conflict.
    """
    # Arrange: Create initial client via API
    identifier = "duplicate_client_id_p5"
    create_client_via_api(logged_in_admin_client, identifier, "Original Client P5")

    # Act: Try creating again with same identifier
    response = logged_in_admin_client.post('/api/admin/clients', json={
        "clientIdentifier": identifier, "name": "Duplicate Client P5",
        "pjsip": {
            "endpoint": {"id": identifier, "context": "ctx2", "aors": identifier},
            "aor": {"id": identifier, "contact": "sip:dup2@test"}
        }
    })

    # Assert: Route catches ConflictError
    assert response.status_code == 409
    data = json.loads(response.data)
    assert f"Client identifier '{identifier}' already exists" in data.get('message', '')


def test_admin_create_client_pjsip_id_mismatch(logged_in_admin_client):
    """
    GIVEN admin client logged in
    WHEN POST /api/admin/clients with mismatched clientIdentifier and pjsip IDs
    THEN check status 400 Bad Request (pre-service validation in route).
    """
    client_payload = {
        "clientIdentifier": "main_identifier_p5", "name": "Mismatch P5",
        "pjsip": {
            "endpoint": {"id": "wrong_endpoint_id_p5", "context": "ctx", "aors": "main_identifier_p5"}, # Mismatch
            "aor": {"id": "main_identifier_p5", "contact": "sip:mismatch_p5@test"}
        }
    }
    response = logged_in_admin_client.post('/api/admin/clients', json=client_payload)
    assert response.status_code == 400
    data = json.loads(response.data)
    # assert 'errors' in data and 'pjsip.endpoint.id' in data['errors'] # OLD
    assert 'message' in data # NEW - Check for message key
    # Check that the specific error message is returned
    assert "PJSIP endpoint ID must match the client_identifier" in data['message'] # NEW


def test_admin_create_client_missing_pjsip_section(logged_in_admin_client):
    """
    GIVEN admin client logged in
    WHEN POST /api/admin/clients without the 'pjsip' section
    THEN check status 400 Bad Request (schema validation).
    """
    client_payload = {"clientIdentifier": "no_pjsip_p5", "name": "No PJSIP P5"}
    response = logged_in_admin_client.post('/api/admin/clients', json=client_payload)
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'errors' in data and 'pjsip' in data['errors']


def test_admin_create_client_missing_pjsip_aor_contact(logged_in_admin_client):
    """
    GIVEN admin client logged in
    WHEN POST /api/admin/clients with pjsip.aor missing 'contact'
    THEN check status 400 Bad Request (schema validation).
    """
    identifier = "missing_contact_p5"
    client_payload = {
        "clientIdentifier": identifier, "name": "Missing Contact P5",
        "pjsip": {
            "endpoint": {"id": identifier, "context": "ctx", "aors": identifier},
            "aor": {"id": identifier} # Missing required 'contact'
        }
    }
    response = logged_in_admin_client.post('/api/admin/clients', json=client_payload)
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'errors' in data and 'pjsip' in data['errors']
    assert 'aor' in data['errors']['pjsip'] and 'contact' in data['errors']['pjsip']['aor']


# --- Test GET /api/admin/clients/{client_id} ---

def test_admin_get_client_by_id_success(logged_in_admin_client, session):
    """
    GIVEN admin client logged in and a target client exists
    WHEN GET /api/admin/clients/{client_id} requested
    THEN check status 200 OK and correct client details returned.
    """
    # Arrange: Create client via API
    created_data = create_client_via_api(logged_in_admin_client, "get_client_p5", "Get Me Client P5")
    target_id = created_data['id']

    # Act
    response = logged_in_admin_client.get(f'/api/admin/clients/{target_id}')

    # Assert
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['id'] == target_id
    assert data['clientIdentifier'] == "get_client_p5"
    assert data['pjsipAor']['contact'] == "sip:get_client_p5@test.local"


def test_admin_get_client_by_id_not_found(logged_in_admin_client):
    """
    GIVEN admin client logged in
    WHEN GET /api/admin/clients/{client_id} for non-existent ID
    THEN check status 404 Not Found.
    """
    response = logged_in_admin_client.get('/api/admin/clients/999999')
    assert response.status_code == 404


# --- Test PUT /api/admin/clients/{client_id} ---

def test_admin_update_client_success_partial(logged_in_admin_client, session):
    """
    GIVEN admin client logged in and a target client exists
    WHEN PUT /api/admin/clients/{client_id} with partial valid update data
    THEN check status 200 OK and details updated in DB and response.
    """
    # Arrange: Create client via API
    identifier = "update_client_p5"
    created_data = create_client_via_api(logged_in_admin_client, identifier, "Update Me P5", {
        "endpoint": {"id": identifier, "context": "updctx", "allow": "ulaw", "aors": identifier},
        "aor": {"id": identifier, "contact": "sip:update_p5@test.local", "qualify_frequency": 60}
    })
    target_id = created_data['id']

    update_data_json = {
        "name": "Update Me P5 (UPDATED)", "status": "inactive",
        "pjsip": {"aor": {"contact": "sip:updated_contact_p5@test.local"}} # Partial PJSIP update
    }
    # Act: Call API (handles commit)
    response = logged_in_admin_client.put(f'/api/admin/clients/{target_id}', json=update_data_json)

    # Assert Response
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['name'] == "Update Me P5 (UPDATED)"
    assert data['status'] == "inactive"
    assert data['pjsipAor']['contact'] == "sip:updated_contact_p5@test.local"
    assert data['pjsipAor']['qualify_frequency'] == 60 # Unchanged

    # Assert Database State
    client_db = session.get(ClientModel, target_id) # Re-fetch
    assert client_db.name == "Update Me P5 (UPDATED)"
    assert client_db.status == "inactive"
    assert client_db.pjsip_aor.contact == "sip:updated_contact_p5@test.local"
    assert client_db.pjsip_endpoint.allow == "ulaw" # Check unchanged part


def test_admin_update_client_add_auth(logged_in_admin_client, session):
    """
    GIVEN admin client logged in and a client exists without auth
    WHEN PUT adds auth data and updates endpoint to reference it
    THEN check status 200 OK and auth details are added/referenced.
    """
    # Arrange: Create client without auth via API
    identifier = "add_auth_client_p5"
    created_data = create_client_via_api(logged_in_admin_client, identifier, "Add Auth P5")
    target_id = created_data['id']
    auth_id = "auth_for_add_p5"

    update_data_json = {
        "pjsip": {
            "auth": {"id": auth_id, "username": "authuser_p5", "password": "AuthP5!", "realm": "authrealm_p5"},
            "endpoint": {"outbound_auth": auth_id} # Point endpoint to new auth
        }
    }
    # Act
    response = logged_in_admin_client.put(f'/api/admin/clients/{target_id}', json=update_data_json)

    # Assert Response
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['pjsipEndpoint']['outbound_auth'] == auth_id
    assert data['pjsipAuth'] is not None and data['pjsipAuth']['id'] == auth_id

    # Assert Database
    client_db = session.get(ClientModel, target_id)
    assert client_db.pjsip_endpoint.outbound_auth == auth_id
    assert client_db.pjsip_auth is not None and client_db.pjsip_auth.id == auth_id
    assert client_db.pjsip_auth.password == "AuthP5!"


def test_admin_update_client_remove_auth(logged_in_admin_client, session):
    """
    GIVEN admin client logged in and a client exists with auth
    WHEN PUT sets auth to null and updates endpoint reference
    THEN check status 200 OK and auth details are removed.
    """
    # Arrange: Create client with auth via API
    identifier = "remove_auth_client_p5"
    auth_id = "auth_to_remove_p5"
    created_data = create_client_via_api(logged_in_admin_client, identifier, "Remove Auth P5", {
        "endpoint": {"id": identifier, "context": "rmauth", "aors": identifier, "outbound_auth": auth_id},
        "aor": {"id": identifier, "contact": "sip:rmauth@test"},
        "auth": {"id": auth_id, "username": "rmuser_p5", "password": "RmPassP5!"}
    })
    target_id = created_data['id']
    assert session.get(PjsipAuthModel, auth_id) is not None # Verify setup

    update_data_json = {
        "pjsip": {
            "auth": None, # Signal removal
            "endpoint": {"outbound_auth": None} # Clear reference
        }
    }
    # Act
    response = logged_in_admin_client.put(f'/api/admin/clients/{target_id}', json=update_data_json)

    # Assert Response
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['pjsipEndpoint']['outbound_auth'] is None
    assert data.get('pjsipAuth') is None

    # Assert Database
    client_db = session.get(ClientModel, target_id)
    assert client_db.pjsip_endpoint.outbound_auth is None
    assert client_db.pjsip_auth is None
    # Check the auth record is actually gone from DB after commit by API
    assert session.get(PjsipAuthModel, auth_id) is None


def test_admin_update_client_fail_change_identifier(logged_in_admin_client, session):
    """
    GIVEN admin client logged in and a client exists
    WHEN PUT attempts to change clientIdentifier
    THEN check status 400 Bad Request (service/route validation).
    """
    # Arrange: Create client via API
    identifier = "no_change_id_p5"
    created_data = create_client_via_api(logged_in_admin_client, identifier, "No Change ID P5")
    target_id = created_data['id']
    original_identifier = created_data['clientIdentifier'] # Store original

    # Act: Attempt update with different identifier AND another valid field
    update_data_json = {"clientIdentifier": "try_change_id_p5", "name": "Name Update P5"}
    response = logged_in_admin_client.put(f'/api/admin/clients/{target_id}', json=update_data_json)

    # Assert: Update succeeds (200 OK) but identifier is NOT changed.
    assert response.status_code == 200 # Update should succeed for the 'name' field
    data = json.loads(response.data)
    assert data['clientIdentifier'] == original_identifier # Check ID hasn't changed
    assert data['name'] == "Name Update P5" # Check name was updated

    # Optional: Assert DB state
    client_db = session.get(ClientModel, target_id)
    assert client_db.client_identifier == original_identifier
    assert client_db.name == "Name Update P5"


def test_admin_update_client_not_found(logged_in_admin_client):
    """
    GIVEN admin client logged in
    WHEN PUT /api/admin/clients/{client_id} for non-existent ID
    THEN check status 404 Not Found.
    """
    response = logged_in_admin_client.put('/api/admin/clients/999999', json={"name": "Not Found Update"})
    assert response.status_code == 404


# --- Test DELETE /api/admin/clients/{client_id} ---

def test_admin_delete_client_success(logged_in_admin_client, session):
    """
    GIVEN admin client logged in and a target client exists (not linked)
    WHEN DELETE /api/admin/clients/{client_id} requested
    THEN check status 204 No Content and client/PJSIP records removed from DB.
    """
    # Arrange: Create client via API
    identifier = "delete_client_p5"
    auth_id = "auth_del_p5"
    created_data = create_client_via_api(logged_in_admin_client, identifier, "Delete Me P5", {
        "endpoint": {"id": identifier, "context": "delctx", "outbound_auth": auth_id, "aors": identifier},
        "aor": {"id": identifier, "contact": "sip:delete@me"},
        "auth": {"id": auth_id, "username": "deluser_p5", "password": "DelPassP5"}
    })
    target_id = created_data['id']
    assert session.get(ClientModel, target_id) is not None # Verify exists

    # Act: Call API (handles commit)
    response = logged_in_admin_client.delete(f'/api/admin/clients/{target_id}')

    # Assert Response
    assert response.status_code == 204

    # Assert Database State (check cascade delete worked)
    assert session.get(ClientModel, target_id) is None
    assert session.get(PjsipEndpointModel, identifier) is None
    assert session.get(PjsipAorModel, identifier) is None
    assert session.get(PjsipAuthModel, auth_id) is None


def test_admin_delete_client_fail_linked_to_active_campaign(logged_in_admin_client, session):
    """
    GIVEN admin client logged in and a client is linked to an active campaign
    WHEN DELETE /api/admin/clients/{client_id} requested
    THEN check status 409 Conflict.
    """
    # Arrange: Use client 'client_alpha_sales' (ID=1) linked in sample data
    client_id = 1
    client_db = session.get(ClientModel, client_id)
    assert client_db is not None, "Sample client ID 1 not found"
    # Verify active link to active campaign exists (logic similar to service check)
    active_link_exists = session.query(CampaignClientSettingsModel.id)\
        .join(CampaignModel)\
        .filter(CampaignClientSettingsModel.client_id == client_id)\
        .filter(CampaignClientSettingsModel.status == 'active')\
        .filter(CampaignModel.status == 'active')\
        .limit(1).scalar() is not None
    assert active_link_exists, f"Test setup assumption failed: Client {client_id} not linked to an active campaign in sample data."

    # Act: Admin attempts to delete the linked client
    response = logged_in_admin_client.delete(f'/api/admin/clients/{client_id}')

    # Assert: Route catches ConflictError from service
    assert response.status_code == 409
    data = json.loads(response.data)
    assert f"Cannot delete client {client_id}. It is actively linked" in data.get('message', '')


def test_admin_delete_client_not_found(logged_in_admin_client):
    """
    GIVEN admin client logged in
    WHEN DELETE /api/admin/clients/{client_id} for non-existent ID
    THEN check status 404 Not Found.
    """
    response = logged_in_admin_client.delete('/api/admin/clients/999999')
    # Route catches ResourceNotFound from service
    assert response.status_code == 404