# tests/integration/api/test_admin_client_api.py
# -*- coding: utf-8 -*-
"""
Integration tests for the Admin Client Management endpoints (/api/admin/clients).
"""
import json
import pytest
import logging # Use logging if needed for debugging tests

from app.database.models import ClientModel, PjsipEndpointModel, PjsipAorModel, PjsipAuthModel
# from app.services.client_service import ClientService # Avoid using service directly in tests if possible

log = logging.getLogger(__name__)

# Fixtures: client, session, db, logged_in_admin_client, logged_in_client

# --- Test GET /api/admin/clients ---

def test_admin_get_clients_success(logged_in_admin_client, session):
    """
    GIVEN admin client logged in and clients exist in DB (from sample data + potential test additions)
    WHEN GET /api/admin/clients is requested
    THEN check status 200 and valid paginated client list is returned.
    """
    # Arrange: Create one more client via API to ensure it appears
    client_payload = {
        "clientIdentifier": "test_list_client_api", "name": "Test List Client API",
        "pjsip": {
            "endpoint": {"id": "test_list_client_api", "context": "from-cap", "allow": "ulaw"},
            "aor": {"id": "test_list_client_api", "contact": "sip:list_api@test.com"}
        }
    }
    create_resp = logged_in_admin_client.post('/api/admin/clients', json=client_payload)
    assert create_resp.status_code == 201, f"Setup failed: {create_resp.data.decode()}"

    # Act
    response = logged_in_admin_client.get('/api/admin/clients?page=1&per_page=5')

    # Assert
    assert response.status_code == 200
    data = json.loads(response.data)
    assert 'items' in data and isinstance(data['items'], list)
    assert data.get('page') == 1
    assert data.get('perPage') == 5
    assert 'total' in data and data['total'] >= 4 # 3 from sample + 1 created here
    assert 'pages' in data
    # Check if the created client is present
    assert any(item['clientIdentifier'] == 'test_list_client_api' for item in data['items'])
    test_client_item = next((item for item in data['items'] if item['clientIdentifier'] == 'test_list_client_api'), None)
    assert test_client_item is not None
    assert 'pjsipEndpoint' in test_client_item and test_client_item['pjsipEndpoint']['id'] == 'test_list_client_api'
    assert 'pjsipAor' in test_client_item and test_client_item['pjsipAor']['contact'] == 'sip:list_api@test.com'


def test_admin_get_clients_forbidden_for_seller(logged_in_client):
    """ GIVEN seller client logged in; WHEN GET /api/admin/clients; THEN 403 """
    response = logged_in_client.get('/api/admin/clients')
    assert response.status_code == 403

def test_admin_get_clients_unauthorized(client):
    """ GIVEN no user logged in; WHEN GET /api/admin/clients; THEN 401 """
    response = client.get('/api/admin/clients')
    assert response.status_code == 401


# --- Test POST /api/admin/clients ---

@pytest.mark.parametrize("auth_present", [True, False])
def test_admin_create_client_success(logged_in_admin_client, session, auth_present):
    """ GIVEN admin logged in; WHEN POST /api/admin/clients with valid data; THEN 201 """
    identifier = f"created_client_{'auth' if auth_present else 'noauth'}_api"
    client_payload = {
        "clientIdentifier": identifier,
        "name": f"Created Client {'With' if auth_present else 'No'} Auth API",
        "pjsip": {
            "endpoint": {"id": identifier, "context": "from-cap", "allow": "ulaw,g729", "aors": identifier, "outbound_auth": "auth_created_api" if auth_present else None},
            "aor": {"id": identifier, "contact": f"sip:{identifier}@test.local", "qualify_frequency": 33}
        }
    }
    if auth_present:
        client_payload["pjsip"]["auth"] = {"id": "auth_created_api", "username": "testuser_api", "password": "TestPasswordAPI!", "realm": "testrealm_api"}

    # Act
    response = logged_in_admin_client.post('/api/admin/clients', json=client_payload)

    # Assert Response
    assert response.status_code == 201
    data = json.loads(response.data)
    assert data['clientIdentifier'] == identifier
    assert 'id' in data
    client_id = data['id']
    assert data['pjsipEndpoint']['id'] == identifier
    assert data['pjsipEndpoint']['allow'] == "ulaw,g729"
    assert data['pjsipEndpoint']['outbound_auth'] == ("auth_created_api" if auth_present else None)
    assert data['pjsipAor']['id'] == identifier
    assert data['pjsipAor']['contact'] == f"sip:{identifier}@test.local"
    if auth_present:
        assert data['pjsipAuth']['id'] == "auth_created_api"
        assert data['pjsipAuth']['username'] == "testuser_api"
        assert 'password' not in data['pjsipAuth'] # Ensure password not dumped
    else:
        assert data.get('pjsipAuth') is None

    # Assert Database State (check AFTER API call commit)
    client_db = session.get(ClientModel, client_id)
    assert client_db is not None
    assert client_db.client_identifier == identifier
    assert client_db.pjsip_endpoint is not None and client_db.pjsip_endpoint.id == identifier
    assert client_db.pjsip_aor is not None and client_db.pjsip_aor.id == identifier
    if auth_present:
        assert client_db.pjsip_auth is not None and client_db.pjsip_auth.id == "auth_created_api"
        assert client_db.pjsip_auth.password == "TestPasswordAPI!" # Password stored in DB
    else:
        assert client_db.pjsip_auth is None


def test_admin_create_client_duplicate_identifier(logged_in_admin_client, session):
    """ GIVEN identifier exists; WHEN POST with same identifier; THEN 409 """
    identifier = "duplicate_client_id_api"
    payload1 = {
        "clientIdentifier": identifier, "name": "Original Client API",
        "pjsip": {"endpoint": {"id": identifier, "context": "ctx", "allow": "ulaw", "aors": identifier}, "aor": {"id": identifier, "contact": "sip:dup_api@test"}}
    }
    res1 = logged_in_admin_client.post('/api/admin/clients', json=payload1)
    assert res1.status_code == 201

    payload2 = { "clientIdentifier": identifier, "name": "Duplicate Client API", "pjsip": payload1["pjsip"] } # Re-use PJSIP section

    # Act
    response = logged_in_admin_client.post('/api/admin/clients', json=payload2)

    # Assert
    assert response.status_code == 409
    assert f"Client identifier '{identifier}' already exists" in response.get_json().get('message', '')


def test_admin_create_client_pjsip_id_mismatch(logged_in_admin_client):
    """ GIVEN mismatched clientIdentifier and pjsip IDs; WHEN POST; THEN 400 """
    client_payload = {
        "clientIdentifier": "main_identifier_api", "name": "Mismatch Test API",
        "pjsip": {
            "endpoint": {"id": "wrong_endpoint_id_api", "context": "ctx", "allow": "ulaw", "aors": "main_identifier_api"}, # Mismatch
            "aor": {"id": "main_identifier_api", "contact": "sip:mismatch_api@test"}
        }
    }
    response = logged_in_admin_client.post('/api/admin/clients', json=client_payload)
    assert response.status_code == 400
    errors = response.get_json().get('errors', {})
    assert 'pjsip.endpoint.id' in errors
    assert "must match client_identifier" in errors['pjsip.endpoint.id'][0]


def test_admin_create_client_missing_pjsip_section(logged_in_admin_client):
    """ GIVEN 'pjsip' section missing; WHEN POST; THEN 400 """
    client_payload = { "clientIdentifier": "no_pjsip_client_api", "name": "No PJSIP Info API" }
    response = logged_in_admin_client.post('/api/admin/clients', json=client_payload)
    assert response.status_code == 400
    assert 'pjsip' in response.get_json().get('errors', {})


def test_admin_create_client_missing_pjsip_aor_contact(logged_in_admin_client):
    """ GIVEN pjsip.aor missing 'contact'; WHEN POST; THEN 400 """
    identifier = "missing_contact_api"
    client_payload = {
        "clientIdentifier": identifier, "name": "Missing Contact API",
        "pjsip": {"endpoint": {"id": identifier, "context": "ctx", "allow": "ulaw", "aors": identifier}, "aor": {"id": identifier}} # Missing contact
    }
    response = logged_in_admin_client.post('/api/admin/clients', json=client_payload)
    assert response.status_code == 400
    errors = response.get_json().get('errors', {})
    assert 'pjsip' in errors and 'aor' in errors['pjsip'] and 'contact' in errors['pjsip']['aor']


# --- Test GET /api/admin/clients/{client_id} ---

def test_admin_get_client_by_id_success(logged_in_admin_client, session):
    """ GIVEN target client exists; WHEN GET /api/admin/clients/{client_id}; THEN 200 """
    identifier = "get_client_test_api"
    payload = {
        "clientIdentifier": identifier, "name": "Get Me Client API",
        "pjsip": {"endpoint": {"id": identifier, "context": "getctx", "allow": "g722", "aors": identifier}, "aor": {"id": identifier, "contact": "sip:getme_api@test.local"}}
    }
    create_resp = logged_in_admin_client.post('/api/admin/clients', json=payload)
    assert create_resp.status_code == 201
    target_id = create_resp.get_json()['id']

    # Act
    response = logged_in_admin_client.get(f'/api/admin/clients/{target_id}')

    # Assert
    assert response.status_code == 200
    data = response.get_json()
    assert data['id'] == target_id
    assert data['clientIdentifier'] == identifier
    assert data['pjsipEndpoint']['allow'] == "g722"
    assert data['pjsipAor']['contact'] == "sip:getme_api@test.local"


def test_admin_get_client_by_id_not_found(logged_in_admin_client):
    """ GIVEN non-existent ID; WHEN GET /api/admin/clients/{client_id}; THEN 404 """
    response = logged_in_admin_client.get('/api/admin/clients/99999')
    assert response.status_code == 404
    assert "Client with ID 99999 not found" in response.get_json().get('message', '')


# --- Test PUT /api/admin/clients/{client_id} ---

def test_admin_update_client_success_partial(logged_in_admin_client, session):
    """ GIVEN client exists; WHEN PUT with partial valid data; THEN 200 """
    identifier = "update_client_test_api"
    payload = {
        "clientIdentifier": identifier, "name": "Update Me API", "status": "active", "department": "OrigDept API",
        "pjsip": {"endpoint": {"id": identifier, "context": "updctx", "allow": "ulaw", "aors": identifier}, "aor": {"id": identifier, "contact": "sip:update_api@test.local", "qualify_frequency": 60}}
    }
    create_resp = logged_in_admin_client.post('/api/admin/clients', json=payload)
    assert create_resp.status_code == 201
    target_id = create_resp.get_json()['id']

    update_data_json = {"name": "Update Me API (UPDATED)", "status": "inactive", "pjsip": {"aor": {"contact": "sip:updated_contact_api@test.local"}}}

    # Act
    response = logged_in_admin_client.put(f'/api/admin/clients/{target_id}', json=update_data_json)

    # Assert Response
    assert response.status_code == 200
    data = response.get_json()
    assert data['name'] == "Update Me API (UPDATED)"
    assert data['status'] == "inactive"
    assert data['department'] == "OrigDept API" # Unchanged
    assert data['pjsipAor']['contact'] == "sip:updated_contact_api@test.local" # Updated
    assert data['pjsipAor']['qualify_frequency'] == 60 # Unchanged

    # Assert Database State
    client_db = session.get(ClientModel, target_id)
    assert client_db is not None and client_db.name == "Update Me API (UPDATED)" and client_db.status == "inactive"
    assert client_db.pjsip_aor.contact == "sip:updated_contact_api@test.local"


def test_admin_update_client_add_auth(logged_in_admin_client, session):
    """ GIVEN client exists without auth; WHEN PUT adds auth data; THEN 200 """
    identifier = "add_auth_client_api"
    payload = {"clientIdentifier": identifier, "name": "Add Auth API", "pjsip": {"endpoint": {"id": identifier, "context": "addauth", "aors": identifier}, "aor": {"id": identifier, "contact": "sip:addauth_api@test"}}}
    create_resp = logged_in_admin_client.post('/api/admin/clients', json=payload)
    assert create_resp.status_code == 201
    target_id = create_resp.get_json()['id']

    update_data_json = {"pjsip": {"auth": {"id": "auth_add_api", "username": "authuser_api", "password": "AuthPassAPI!"}, "endpoint": {"outbound_auth": "auth_add_api"}}}

    # Act
    response = logged_in_admin_client.put(f'/api/admin/clients/{target_id}', json=update_data_json)

    # Assert Response
    assert response.status_code == 200
    data = response.get_json()
    assert data['pjsipEndpoint']['outbound_auth'] == "auth_add_api"
    assert data['pjsipAuth']['id'] == "auth_add_api"

    # Assert Database State
    client_db = session.get(ClientModel, target_id)
    assert client_db.pjsip_endpoint.outbound_auth == "auth_add_api"
    assert client_db.pjsip_auth is not None and client_db.pjsip_auth.id == "auth_add_api"


def test_admin_update_client_remove_auth(logged_in_admin_client, session):
    """ GIVEN client exists with auth; WHEN PUT sets auth to null; THEN 200 """
    identifier = "remove_auth_client_api"
    payload = {"clientIdentifier": identifier, "name": "Remove Auth API", "pjsip": {"endpoint": {"id": identifier, "context": "rmauth", "aors": identifier, "outbound_auth": "auth_rm_api"}, "aor": {"id": identifier, "contact": "sip:rmauth_api@test"}, "auth": {"id": "auth_rm_api", "username": "rmuser_api", "password": "RmPassAPI!"}}}
    create_resp = logged_in_admin_client.post('/api/admin/clients', json=payload)
    assert create_resp.status_code == 201
    target_id = create_resp.get_json()['id']

    update_data_json = {"pjsip": {"auth": None, "endpoint": {"outbound_auth": None}}}

    # Act
    response = logged_in_admin_client.put(f'/api/admin/clients/{target_id}', json=update_data_json)

    # Assert Response
    assert response.status_code == 200
    data = response.get_json()
    assert data['pjsipEndpoint']['outbound_auth'] is None
    assert data.get('pjsipAuth') is None

    # Assert Database State
    client_db = session.get(ClientModel, target_id)
    assert client_db.pjsip_endpoint.outbound_auth is None
    assert client_db.pjsip_auth is None
    assert session.get(PjsipAuthModel, "auth_rm_api") is None # Check record deleted


def test_admin_update_client_fail_change_identifier(logged_in_admin_client, session):
    """ GIVEN client exists; WHEN PUT attempts to change clientIdentifier; THEN 400 """
    identifier = "no_change_id_api"
    payload = { "clientIdentifier": identifier, "name": "No Change ID API", "pjsip": {"endpoint": {"id": identifier, "context": "ctx", "aors":identifier}, "aor": {"id": identifier, "contact": "sip:nochange_api"}} }
    create_resp = logged_in_admin_client.post('/api/admin/clients', json=payload)
    assert create_resp.status_code == 201
    target_id = create_resp.get_json()['id']

    update_data_json = {"clientIdentifier": "try_change_id_api"}

    # Act
    response = logged_in_admin_client.put(f'/api/admin/clients/{target_id}', json=update_data_json)

    # Assert
    assert response.status_code == 400
    # This validation happens in the service layer now
    assert "Client identifier cannot be changed" in response.get_json().get('message', '')


def test_admin_update_client_not_found(logged_in_admin_client):
    """ GIVEN non-existent ID; WHEN PUT /api/admin/clients/{client_id}; THEN 404 """
    response = logged_in_admin_client.put('/api/admin/clients/99999', json={"name": "Not Found Update"})
    assert response.status_code == 404


# --- Test DELETE /api/admin/clients/{client_id} ---

def test_admin_delete_client_success(logged_in_admin_client, session):
    """ GIVEN unlinked client exists; WHEN DELETE /api/admin/clients/{client_id}; THEN 204 """
    identifier = "delete_client_test_api"
    payload = {"clientIdentifier": identifier, "name": "Delete Me API", "pjsip": {"endpoint": {"id": identifier, "context": "delctx", "aors":identifier}, "aor": {"id": identifier, "contact": "sip:delete_api@me"}, "auth": {"id": "auth_del_api", "username": "deluser_api"}}}
    create_resp = logged_in_admin_client.post('/api/admin/clients', json=payload)
    assert create_resp.status_code == 201
    target_id = create_resp.get_json()['id']

    # Verify records exist before delete
    assert session.get(ClientModel, target_id) is not None
    assert session.get(PjsipEndpointModel, identifier) is not None
    assert session.get(PjsipAorModel, identifier) is not None
    assert session.get(PjsipAuthModel, "auth_del_api") is not None

    # Act
    response = logged_in_admin_client.delete(f'/api/admin/clients/{target_id}')

    # Assert Response
    assert response.status_code == 204

    # Assert Database State (check all related records are gone due to cascade)
    assert session.get(ClientModel, target_id) is None
    assert session.get(PjsipEndpointModel, identifier) is None
    assert session.get(PjsipAorModel, identifier) is None
    assert session.get(PjsipAuthModel, "auth_del_api") is None


def test_admin_delete_client_fail_linked_to_active_campaign(logged_in_admin_client, session):
    """ GIVEN client linked to active campaign; WHEN DELETE client; THEN 409 """
    # Arrange: Use sample data where client 1 ('client_alpha_sales') is linked to active campaign 1
    client_id = 1 # Assumes Client ID 1 exists from sample_data.sql
    client = session.get(ClientModel, client_id)
    assert client is not None, "Sample client ID 1 not found"

    # Act: Admin attempts to delete client 1
    response = logged_in_admin_client.delete(f'/api/admin/clients/{client_id}')

    # Assert
    assert response.status_code == 409
    assert "actively linked to one or more active campaigns" in response.get_json().get('message', '')


def test_admin_delete_client_not_found(logged_in_admin_client):
    """ GIVEN non-existent ID; WHEN DELETE /api/admin/clients/{client_id}; THEN 404 """
    response = logged_in_admin_client.delete('/api/admin/clients/99999')
    assert response.status_code == 404