# -*- coding: utf-8 -*-
"""
Integration tests for the Admin Client Management endpoints (/api/admin/clients).
"""
import json
import pytest

from app.database.models import ClientModel, PjsipEndpointModel, PjsipAorModel, PjsipAuthModel
from app.services.client_service import ClientService # May need for setup, but prefer API calls

# Fixtures: client, session, db, logged_in_admin_client, logged_in_client

# --- Test GET /api/admin/clients ---

def test_admin_get_clients_success(logged_in_admin_client, session):
    """
    GIVEN admin client logged in and clients exist in DB
    WHEN GET /api/admin/clients is requested
    THEN check status 200 and valid paginated client list is returned.
    """
    # Arrange: Sample data should already have clients. We can create one more for certainty.
    # Use the API to create if possible, otherwise use service directly for setup.
    client_payload = {
        "clientIdentifier": "test_list_client", "name": "Test List Client",
        "pjsip": {
            "endpoint": {"id": "test_list_client", "context": "from-cap", "allow": "ulaw"},
            "aor": {"id": "test_list_client", "contact": "sip:list@test.com"}
        }
    }
    create_resp = logged_in_admin_client.post('/api/admin/clients', json=client_payload)
    assert create_resp.status_code == 201 # Ensure creation worked

    # Act
    response = logged_in_admin_client.get('/api/admin/clients?page=1&per_page=5')

    # Assert
    assert response.status_code == 200
    data = json.loads(response.data)
    assert 'items' in data
    assert data.get('page') == 1
    assert data.get('perPage') == 5 # Check camelCase output key (ensure schema fixed)
    assert 'total' in data and data['total'] >= 1 # Should have at least the one we created + sample data
    assert 'pages' in data
    assert isinstance(data['items'], list)
    # Check if the created client is present
    assert any(item['clientIdentifier'] == 'test_list_client' for item in data['items'])
    # Check for nested PJSIP data (basic check)
    test_client_item = next((item for item in data['items'] if item['clientIdentifier'] == 'test_list_client'), None)
    assert test_client_item is not None
    assert 'pjsipEndpoint' in test_client_item
    assert 'pjsipAor' in test_client_item
    assert test_client_item['pjsipEndpoint']['id'] == 'test_list_client'
    assert test_client_item['pjsipAor']['contact'] == 'sip:list@test.com'


def test_admin_get_clients_forbidden_for_seller(logged_in_client):
    """
    GIVEN seller client logged in
    WHEN GET /api/admin/clients is requested
    THEN check status 403 Forbidden.
    """
    response = logged_in_client.get('/api/admin/clients')
    assert response.status_code == 403

def test_admin_get_clients_unauthorized(client):
    """
    GIVEN no user logged in
    WHEN GET /api/admin/clients is requested
    THEN check status 401 Unauthorized.
    """
    response = client.get('/api/admin/clients')
    assert response.status_code == 401


# --- Test POST /api/admin/clients ---

@pytest.mark.parametrize("auth_present", [True, False]) # Test with and without auth section
def test_admin_create_client_success(logged_in_admin_client, session, auth_present):
    """
    GIVEN admin client logged in
    WHEN POST /api/admin/clients with valid data (with/without auth)
    THEN check status 201 Created and client/PJSIP details are correct.
    """
    identifier = f"created_client_{'auth' if auth_present else 'noauth'}"
    client_payload = {
        "clientIdentifier": identifier,
        "name": f"Created Client {'With' if auth_present else 'No'} Auth",
        "department": "Testing",
        "status": "active",
        "notes": "Test creation",
        "pjsip": {
            "endpoint": {
                "id": identifier, "transport": "transport-udp", "aors": identifier,
                "context": "from-capconduit", "allow": "ulaw,g729",
                "outbound_auth": "auth_to_created" if auth_present else None # Reference auth only if present
            },
            "aor": {
                "id": identifier, "contact": f"sip:{identifier}@test.local",
                "qualify_frequency": 33
            }
            # Auth section added below based on parameter
        }
    }
    if auth_present:
        client_payload["pjsip"]["auth"] = {
            "id": "auth_to_created", "username": "testuser", "password": "TestPassword!", "realm": "testrealm"
        }

    # Act
    response = logged_in_admin_client.post('/api/admin/clients', json=client_payload)

    # Assert Response
    assert response.status_code == 201
    data = json.loads(response.data)
    assert data['clientIdentifier'] == identifier
    assert data['name'] == client_payload['name']
    assert 'id' in data
    client_id = data['id']

    # Assert PJSIP details in response
    assert 'pjsipEndpoint' in data and data['pjsipEndpoint']['id'] == identifier
    assert data['pjsipEndpoint']['allow'] == "ulaw,g729"
    assert data['pjsipEndpoint']['outbound_auth'] == ("auth_to_created" if auth_present else None)
    assert 'pjsipAor' in data and data['pjsipAor']['id'] == identifier
    assert data['pjsipAor']['contact'] == f"sip:{identifier}@test.local"
    assert data['pjsipAor']['qualify_frequency'] == 33
    if auth_present:
        assert 'pjsipAuth' in data and data['pjsipAuth'] is not None
        assert data['pjsipAuth']['id'] == "auth_to_created"
        assert data['pjsipAuth']['username'] == "testuser"
        assert data['pjsipAuth'].get('password') is None # Password should not be dumped
        assert data['pjsipAuth']['realm'] == "testrealm"
    else:
        assert data.get('pjsipAuth') is None

    # Assert Database State
    client_db = session.get(ClientModel, client_id)
    assert client_db is not None
    assert client_db.client_identifier == identifier
    assert client_db.pjsip_endpoint is not None
    assert client_db.pjsip_endpoint.id == identifier
    assert client_db.pjsip_endpoint.allow == "ulaw,g729"
    assert client_db.pjsip_aor is not None
    assert client_db.pjsip_aor.id == identifier
    assert client_db.pjsip_aor.contact == f"sip:{identifier}@test.local"
    if auth_present:
        assert client_db.pjsip_auth is not None
        assert client_db.pjsip_auth.id == "auth_to_created"
        assert client_db.pjsip_auth.username == "testuser"
        assert client_db.pjsip_auth.password == "TestPassword!" # Password IS stored in DB
    else:
        assert client_db.pjsip_auth is None


def test_admin_create_client_duplicate_identifier(logged_in_admin_client, session):
    """
    GIVEN admin client logged in and a client identifier exists
    WHEN POST /api/admin/clients with the same identifier
    THEN check status 409 Conflict.
    """
    # Arrange: Create initial client via API for setup
    identifier = "duplicate_client_id"
    payload1 = {
        "clientIdentifier": identifier, "name": "Original Client",
        "pjsip": {
            "endpoint": {"id": identifier, "context": "ctx", "allow": "ulaw"},
            "aor": {"id": identifier, "contact": "sip:dup@test"}
        }
    }
    res1 = logged_in_admin_client.post('/api/admin/clients', json=payload1)
    assert res1.status_code == 201

    # Try creating again with same identifier
    payload2 = {
        "clientIdentifier": identifier, # Duplicate
        "name": "Duplicate Client",
        "pjsip": {
            "endpoint": {"id": identifier, "context": "ctx2", "allow": "ulaw"},
            "aor": {"id": identifier, "contact": "sip:dup2@test"}
        }
    }

    # Act
    response = logged_in_admin_client.post('/api/admin/clients', json=payload2)

    # Assert
    assert response.status_code == 409
    data = json.loads(response.data)
    assert f"Client identifier '{identifier}' already exists" in data.get('message', '')


def test_admin_create_client_pjsip_id_mismatch(logged_in_admin_client):
    """
    GIVEN admin client logged in
    WHEN POST /api/admin/clients with mismatched clientIdentifier and pjsip IDs
    THEN check status 400 Bad Request.
    """
    client_payload = {
        "clientIdentifier": "main_identifier",
        "name": "Mismatch Test",
        "pjsip": {
            "endpoint": {"id": "wrong_endpoint_id", "context": "ctx", "allow": "ulaw"}, # Mismatch
            "aor": {"id": "main_identifier", "contact": "sip:mismatch@test"}
        }
    }
    response = logged_in_admin_client.post('/api/admin/clients', json=client_payload)
    assert response.status_code == 400
    data = json.loads(response.data)
    # Check nested structure
    assert 'pjsip.endpoint.id' in data.get('errors', {})
    assert "Endpoint ID must match client_identifier" in data['errors'].get('pjsip.endpoint.id', [])[0]

def test_admin_create_client_missing_pjsip_section(logged_in_admin_client):
    """
    GIVEN admin client logged in
    WHEN POST /api/admin/clients without the 'pjsip' section
    THEN check status 400 Bad Request.
    """
    client_payload = {
        "clientIdentifier": "no_pjsip_client",
        "name": "No PJSIP Info",
    }
    response = logged_in_admin_client.post('/api/admin/clients', json=client_payload)
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'pjsip' in data.get('errors', {}) # Check 'errors' dict


def test_admin_create_client_missing_pjsip_aor_contact(logged_in_admin_client):
    """
    GIVEN admin client logged in
    WHEN POST /api/admin/clients with pjsip.aor missing 'contact'
    THEN check status 400 Bad Request.
    """
    identifier = "missing_contact"
    client_payload = {
        "clientIdentifier": identifier,
        "name": "Missing Contact",
        "pjsip": {
            "endpoint": {"id": identifier, "context": "ctx", "allow": "ulaw", "aors": identifier},
            "aor": {"id": identifier} # Missing contact
        }
    }
    response = logged_in_admin_client.post('/api/admin/clients', json=client_payload)
    assert response.status_code == 400
    data = json.loads(response.data)
    # Check nested error structure
    assert 'pjsip' in data.get('errors', {})
    assert 'aor' in data['errors'].get('pjsip', {})
    assert 'contact' in data['errors']['pjsip'].get('aor', {})

# --- Test GET /api/admin/clients/{client_id} ---

def test_admin_get_client_by_id_success(logged_in_admin_client, session):
    """
    GIVEN admin client logged in and a target client exists
    WHEN GET /api/admin/clients/{client_id} is requested
    THEN check status 200 OK and correct client details (incl. PJSIP) are returned.
    """
    # Arrange: Create a client using the API to get a valid ID and structure
    identifier = "get_client_test"
    payload = {
        "clientIdentifier": identifier, "name": "Get Me Client", "status": "active",
        "pjsip": {
            "endpoint": {"id": identifier, "context": "getctx", "allow": "g722"},
            "aor": {"id": identifier, "contact": "sip:getme@test.local"}
        }
    }
    create_resp = logged_in_admin_client.post('/api/admin/clients', json=payload)
    assert create_resp.status_code == 201
    created_data = json.loads(create_resp.data)
    target_id = created_data['id']

    # Act
    response = logged_in_admin_client.get(f'/api/admin/clients/{target_id}')

    # Assert
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['id'] == target_id
    assert data['clientIdentifier'] == identifier
    assert data['name'] == "Get Me Client"
    assert data['pjsipEndpoint']['allow'] == "g722"
    assert data['pjsipAor']['contact'] == "sip:getme@test.local"
    assert data.get('pjsipAuth') is None


def test_admin_get_client_by_id_not_found(logged_in_admin_client):
    """
    GIVEN admin client logged in
    WHEN GET /api/admin/clients/{client_id} for a non-existent ID
    THEN check status 404 Not Found.
    """
    response = logged_in_admin_client.get('/api/admin/clients/99999')
    assert response.status_code == 404
    data = json.loads(response.data)
    assert "Client with ID 99999 not found" in data.get('message', '')


# --- Test PUT /api/admin/clients/{client_id} ---

def test_admin_update_client_success_partial(logged_in_admin_client, session):
    """
    GIVEN admin client logged in and a target client exists
    WHEN PUT /api/admin/clients/{client_id} with partial valid update data
    THEN check status 200 OK and details are updated in DB and response.
    """
    # Arrange: Create a client
    identifier = "update_client_test"
    payload = {
        "clientIdentifier": identifier, "name": "Update Me Client", "status": "active",
        "department": "OrigDept",
        "pjsip": {
            "endpoint": {"id": identifier, "context": "updctx", "allow": "ulaw"},
            "aor": {"id": identifier, "contact": "sip:update@test.local", "qualify_frequency": 60}
        }
    }
    create_resp = logged_in_admin_client.post('/api/admin/clients', json=payload)
    assert create_resp.status_code == 201
    target_id = json.loads(create_resp.data)['id']

    # Data for partial update
    update_data_json = {
        "name": "Update Me Client (UPDATED)",
        "status": "inactive",
        "pjsip": {
            "aor": { # Only update AOR contact
                "contact": "sip:updated_contact@test.local"
            }
        }
    }

    # Act
    response = logged_in_admin_client.put(f'/api/admin/clients/{target_id}', json=update_data_json)

    # Assert Response
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['id'] == target_id
    assert data['clientIdentifier'] == identifier
    assert data['name'] == "Update Me Client (UPDATED)" # Updated
    assert data['status'] == "inactive" # Updated
    assert data['department'] == "OrigDept" # Unchanged
    assert data['pjsipEndpoint']['allow'] == "ulaw" # Unchanged endpoint field
    assert data['pjsipAor']['contact'] == "sip:updated_contact@test.local" # Updated AOR field
    assert data['pjsipAor']['qualify_frequency'] == 60 # Unchanged AOR field

    # Assert Database State
    client_db = session.get(ClientModel, target_id)
    session.refresh(client_db) # Refresh to get latest state after commit
    assert client_db is not None
    assert client_db.name == "Update Me Client (UPDATED)"
    assert client_db.status == "inactive"
    assert client_db.pjsip_aor.contact == "sip:updated_contact@test.local"
    assert client_db.pjsip_endpoint.allow == "ulaw" # Check unchanged PJSIP parts too


def test_admin_update_client_add_auth(logged_in_admin_client, session):
    """
    GIVEN admin client logged in and a client exists without auth
    WHEN PUT /api/admin/clients/{client_id} adds auth data and updates endpoint
    THEN check status 200 OK and auth details are added.
    """
    # Arrange: Create client without auth
    identifier = "add_auth_client"
    payload = {
        "clientIdentifier": identifier, "name": "Add Auth Client",
        "pjsip": {
            "endpoint": {"id": identifier, "context": "addauth", "allow": "ulaw", "aors": identifier},
            "aor": {"id": identifier, "contact": "sip:addauth@test"}
        }
    }
    create_resp = logged_in_admin_client.post('/api/admin/clients', json=payload)
    assert create_resp.status_code == 201
    target_id = json.loads(create_resp.data)['id']

    # Update data to add auth
    update_data_json = {
        "pjsip": {
            "auth": {
                "id": "auth_for_add_auth", # Must match endpoint's outbound_auth
                "username": "authuser",
                "password": "AuthPassword!",
                "realm": "authrealm"
            },
            "endpoint": {
                "outbound_auth": "auth_for_add_auth" # Point endpoint to the new auth
            }
        }
    }

    # Act
    response = logged_in_admin_client.put(f'/api/admin/clients/{target_id}', json=update_data_json)

    # Assert Response
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['pjsipEndpoint']['outbound_auth'] == "auth_for_add_auth"
    assert data['pjsipAuth'] is not None
    assert data['pjsipAuth']['id'] == "auth_for_add_auth"
    assert data['pjsipAuth']['username'] == "authuser"
    assert data['pjsipAuth'].get('password') is None # Excluded

    # Assert Database State
    client_db = session.get(ClientModel, target_id)
    session.refresh(client_db)
    assert client_db.pjsip_endpoint.outbound_auth == "auth_for_add_auth"
    assert client_db.pjsip_auth is not None
    assert client_db.pjsip_auth.id == "auth_for_add_auth"
    assert client_db.pjsip_auth.password == "AuthPassword!"


def test_admin_update_client_remove_auth(logged_in_admin_client, session):
    """
    GIVEN admin client logged in and a client exists with auth
    WHEN PUT /api/admin/clients/{client_id} sets auth to null and updates endpoint
    THEN check status 200 OK and auth details are removed.
    """
    # Arrange: Create client with auth
    identifier = "remove_auth_client"
    payload = {
        "clientIdentifier": identifier, "name": "Remove Auth Client",
        "pjsip": {
            "endpoint": {"id": identifier, "context": "rmauth", "aors": identifier, "outbound_auth": "auth_to_remove"},
            "aor": {"id": identifier, "contact": "sip:rmauth@test"},
            "auth": {"id": "auth_to_remove", "username": "rmuser", "password": "RmPass!"}
        }
    }
    create_resp = logged_in_admin_client.post('/api/admin/clients', json=payload)
    assert create_resp.status_code == 201
    target_id = json.loads(create_resp.data)['id']

    # Update data to remove auth
    update_data_json = {
        "pjsip": {
            "auth": None, # Signal removal
            "endpoint": {
                "outbound_auth": None # Clear reference from endpoint
            }
        }
    }

    # Act
    response = logged_in_admin_client.put(f'/api/admin/clients/{target_id}', json=update_data_json)

    # Assert Response
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['pjsipEndpoint']['outbound_auth'] is None
    assert data.get('pjsipAuth') is None

    # Assert Database State
    client_db = session.get(ClientModel, target_id)
    session.refresh(client_db)
    assert client_db.pjsip_endpoint.outbound_auth is None
    assert client_db.pjsip_auth is None
    # Check the auth record is actually gone
    auth_record = session.get(PjsipAuthModel, "auth_to_remove")
    assert auth_record is None


def test_admin_update_client_fail_change_identifier(logged_in_admin_client, session):
    """
    GIVEN admin client logged in and a client exists
    WHEN PUT /api/admin/clients/{client_id} attempts to change clientIdentifier
    THEN check status 400 Bad Request.
    """
    # Arrange: Create a client
    identifier = "no_change_id"
    payload = { "clientIdentifier": identifier, "name": "No Change ID", "pjsip": {"endpoint": {"id": identifier, "context": "ctx"}, "aor": {"id": identifier, "contact": "sip:nochange"}} }
    create_resp = logged_in_admin_client.post('/api/admin/clients', json=payload)
    assert create_resp.status_code == 201
    target_id = json.loads(create_resp.data)['id']

    # Attempt update with different identifier
    update_data_json = {"clientIdentifier": "try_change_id"}

    # Act
    response = logged_in_admin_client.put(f'/api/admin/clients/{target_id}', json=update_data_json)

    # Assert
    assert response.status_code == 400
    # This validation happens in the service layer before schema loading for update
    data = json.loads(response.data)
    assert "No valid fields provided for update" in data.get('message', '')


def test_admin_update_client_not_found(logged_in_admin_client):
    """
    GIVEN admin client logged in
    WHEN PUT /api/admin/clients/{client_id} for a non-existent ID
    THEN check status 404 Not Found.
    """
    response = logged_in_admin_client.put('/api/admin/clients/99999', json={"name": "Not Found Update"})
    assert response.status_code == 404


# --- Test DELETE /api/admin/clients/{client_id} ---

def test_admin_delete_client_success(logged_in_admin_client, session):
    """
    GIVEN admin client logged in and a target client exists (not linked to campaigns)
    WHEN DELETE /api/admin/clients/{client_id} is requested
    THEN check status 204 No Content and client/PJSIP records are removed from DB.
    """
    # Arrange: Create a client
    identifier = "delete_client_test"
    payload = {
        "clientIdentifier": identifier, "name": "Delete Me Client",
        "pjsip": {
            "endpoint": {"id": identifier, "context": "delctx", "outbound_auth": "auth_del", "aors": identifier},
            "aor": {"id": identifier, "contact": "sip:delete@me"},
            "auth": {"id": "auth_del", "username": "deluser", "password": "DelPass"}
        }
    }
    create_resp = logged_in_admin_client.post('/api/admin/clients', json=payload)
    assert create_resp.status_code == 201
    target_id = json.loads(create_resp.data)['id']

    # Verify records exist before delete
    client_before = session.get(ClientModel, target_id)
    assert client_before is not None
    assert session.get(PjsipEndpointModel, identifier) is not None
    assert session.get(PjsipAorModel, identifier) is not None
    assert session.get(PjsipAuthModel, "auth_del") is not None

    # Act
    response = logged_in_admin_client.delete(f'/api/admin/clients/{target_id}')

    # Assert Response
    assert response.status_code == 204

    # Assert Database State (check all related records are gone due to cascade)
    assert session.get(ClientModel, target_id) is None
    assert session.get(PjsipEndpointModel, identifier) is None
    assert session.get(PjsipAorModel, identifier) is None
    assert session.get(PjsipAuthModel, "auth_del") is None


def test_admin_delete_client_fail_linked_to_campaign(logged_in_admin_client, session): # Need seller client too
    """
    GIVEN admin client logged in and a client is linked to a seller's campaign
    WHEN DELETE /api/admin/clients/{client_id} is requested
    THEN check status 409 Conflict.
    """
    # Arrange:
    # 1. Get client 'client_alpha_sales' ID (ID=1 from sample data)
    client_id = 1
    # 2. Sample data links client 1 to campaign 1 (active)

    # Act: Admin attempts to delete client 1
    response = logged_in_admin_client.delete(f'/api/admin/clients/{client_id}')

    # Assert
    assert response.status_code == 409 # Status code is correct now
    data = json.loads(response.data)
    # Check for the core reason in the message, allowing for variations like added IDs
    assert f"Cannot delete client {client_id}" in data.get('message', '') # Check start
    assert "linked to active campaigns" in data.get('message', '')    # Check key phrase

def test_admin_delete_client_not_found(logged_in_admin_client):
    """
    GIVEN admin client logged in
    WHEN DELETE /api/admin/clients/{client_id} for a non-existent ID
    THEN check status 404 Not Found.
    """
    response = logged_in_admin_client.delete('/api/admin/clients/99999')
    assert response.status_code == 404