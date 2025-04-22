# tests/integration/api/test_seller_campaign_api.py
# -*- coding: utf-8 -*-
"""
Integration tests for Seller Campaign Management endpoints (/api/seller/campaigns).
Tests now rely on API calls for setup/modification where possible,
and the transactional 'session' fixture for rollback, removing explicit commits within tests.
"""
import json
import pytest
import logging

# Import Models for DB checks and setup helpers
from app.database.models import CampaignModel, UserModel, DidModel, ClientModel, CampaignDidModel, CampaignClientSettingsModel
# Import Services ONLY if absolutely necessary for complex setup not feasible via API
from app.services.campaign_service import CampaignService
from app.services.user_service import UserService
from app.services.did_service import DidService
# from app.services.client_service import ClientService # Use API to manage clients

log = logging.getLogger(__name__)

# Fixtures: client, session, db, logged_in_client (seller), logged_in_admin_client

# Helper to get seller ID (defined previously in conftest or here)
def get_seller_id(session):
    user = session.query(UserModel).filter_by(username="pytest_seller").one_or_none()
    assert user is not None, "Test setup failed: pytest_seller not found."
    return user.id

# Helper to create campaign via API (using seller client)
def create_campaign_via_api(seller_client, name, strategy="priority", timeout=30, status="active", description=None):
    payload = {"name": name, "routingStrategy": strategy, "dialTimeoutSeconds": timeout, "status": status}
    if description: payload["description"] = description
    response = seller_client.post('/api/seller/campaigns', json=payload)
    assert response.status_code == 201, f"Failed to create campaign '{name}' via API: {response.data.decode()}"
    return response.get_json()

# Helper to create DID via API (using seller client)
def create_did_via_api(seller_client, number, description=None, status="active"):
    payload = {"number": number, "description": description, "status": status}
    response = seller_client.post('/api/seller/dids', json=payload)
    assert response.status_code == 201, f"Failed to create DID '{number}' via API: {response.data.decode()}"
    return response.get_json()

# --- Test GET /api/seller/campaigns ---

def test_seller_get_own_campaigns_list(logged_in_client, session):
    """ GIVEN seller owns campaigns; WHEN GET /campaigns; THEN 200 """
    # Arrange: Create campaigns via API
    camp1_data = create_campaign_via_api(logged_in_client, "My First Camp API", "priority", 30)
    camp2_data = create_campaign_via_api(logged_in_client, "My Second Camp API", "round_robin", 25, status='inactive')
    # Create campaign for another user (use service within transaction, will rollback)
    other_user = UserService.create_user("otherseller_camp_api", "other_camp_api@s.com", "Pass123")
    session.flush() # Need user ID
    CampaignService.create_campaign(other_user.id, "Other Seller Camp API", "priority", 30)
    session.flush() # Ensure other campaign exists in transaction for testing visibility

    # Act
    response = logged_in_client.get('/api/seller/campaigns?page=1&per_page=5')

    # Assert
    assert response.status_code == 200
    data = response.get_json()
    assert data.get('total') == 2 # Only the 2 created for logged_in_client
    assert len(data['items']) == 2
    names_returned = {item['name'] for item in data['items']}
    assert camp1_data['name'] in names_returned
    assert camp2_data['name'] in names_returned
    assert "Other Seller Camp API" not in names_returned


def test_seller_get_campaigns_unauthorized(client):
    """ GIVEN no user logged in; WHEN GET /campaigns; THEN 401 """
    response = client.get('/api/seller/campaigns')
    assert response.status_code == 401


# --- Test POST /api/seller/campaigns ---

def test_seller_create_campaign_success(logged_in_client, session):
    """ GIVEN seller logged in; WHEN POST /campaigns with valid data; THEN 201 """
    seller_id = get_seller_id(session)
    campaign_payload = {"name": "Seller Created API", "routingStrategy": "weighted", "dialTimeoutSeconds": 28, "description": "API test"}

    # Act
    response = logged_in_client.post('/api/seller/campaigns', json=campaign_payload)

    # Assert Response
    assert response.status_code == 201
    data = response.get_json()
    assert data['name'] == campaign_payload['name']
    assert data['routingStrategy'] == campaign_payload['routingStrategy']
    assert 'id' in data
    campaign_id = data['id']

    # Assert Database State
    campaign_db = session.get(CampaignModel, campaign_id)
    assert campaign_db is not None and campaign_db.user_id == seller_id


def test_seller_create_campaign_duplicate_name_fail(logged_in_client, session):
    """ GIVEN campaign name exists for seller; WHEN POST with same name; THEN 409 """
    existing_name = "Duplicate Campaign API Test"
    create_campaign_via_api(logged_in_client, existing_name) # Create first one

    # Attempt duplicate
    campaign_payload = {"name": existing_name, "routingStrategy": "round_robin", "dialTimeoutSeconds": 20}
    response = logged_in_client.post('/api/seller/campaigns', json=campaign_payload)

    assert response.status_code == 409
    assert f"Campaign name '{existing_name}' already exists" in response.get_json().get('message', '')


def test_seller_create_campaign_missing_name(logged_in_client):
    """ GIVEN missing name; WHEN POST /campaigns; THEN 400 """
    payload = {"routingStrategy": "priority", "dialTimeoutSeconds": 25}
    response = logged_in_client.post('/api/seller/campaigns', json=payload)
    assert response.status_code == 400
    assert 'name' in response.get_json().get('errors', {})


def test_seller_create_campaign_invalid_strategy(logged_in_client):
    """ GIVEN invalid routingStrategy; WHEN POST /campaigns; THEN 400 """
    payload = {"name": "Invalid Strategy API", "routingStrategy": "fastest", "dialTimeoutSeconds": 25}
    response = logged_in_client.post('/api/seller/campaigns', json=payload)
    assert response.status_code == 400
    assert 'routingStrategy' in response.get_json().get('errors', {})


# --- Test GET /api/seller/campaigns/{campaign_id} ---

def test_seller_get_own_campaign_success(logged_in_client, session):
    """ GIVEN seller owns campaign with links; WHEN GET /campaigns/{id}; THEN 200 """
    # Arrange: Create campaign, DID, Link client via API
    campaign_data = create_campaign_via_api(logged_in_client, "Get My Detailed Camp API")
    did_data = create_did_via_api(logged_in_client, "+15553334444", "DID for Detail Test")
    campaign_id = campaign_data['id']
    did_id = did_data['id']
    client_id = 1 # Use client from sample data

    # Link DID
    link_did_resp = logged_in_client.put(f'/api/seller/campaigns/{campaign_id}/dids', json={"didIds": [did_id]})
    assert link_did_resp.status_code == 200

    # Link Client
    setting_payload = {"clientId": client_id, "maxConcurrency": 5, "forwardingPriority": 0, "weight": 100}
    link_client_resp = logged_in_client.post(f'/api/seller/campaigns/{campaign_id}/clients', json=setting_payload)
    assert link_client_resp.status_code == 201
    setting_id = link_client_resp.get_json()['id']

    # Act
    response = logged_in_client.get(f'/api/seller/campaigns/{campaign_id}')

    # Assert
    assert response.status_code == 200
    data = response.get_json()
    assert data['id'] == campaign_id
    assert data['name'] == "Get My Detailed Camp API"
    assert isinstance(data.get('dids'), list) and len(data['dids']) == 1
    assert data['dids'][0]['id'] == did_id
    assert isinstance(data.get('clientSettings'), list) and len(data['clientSettings']) == 1
    assert data['clientSettings'][0]['id'] == setting_id
    assert data['clientSettings'][0]['client']['id'] == client_id


def test_seller_get_other_campaign_fail(logged_in_client, session):
    """ GIVEN campaign owned by another user; WHEN GET /campaigns/{id}; THEN 404 """
    # Arrange: Create campaign for another user (service call, will rollback)
    other_user = UserService.create_user("otherseller_camp_get_api", "other_get_api@s.com", "Pass123")
    session.flush()
    other_campaign = CampaignService.create_campaign(other_user.id, "Other Seller Get API", "priority", 30)
    session.flush() # Need ID
    target_id = other_campaign.id

    # Act
    response = logged_in_client.get(f'/api/seller/campaigns/{target_id}')

    # Assert
    assert response.status_code == 404
    assert f"Campaign with ID {target_id} not found or not owned by user" in response.get_json().get('message', '')


def test_seller_get_nonexistent_campaign_fail(logged_in_client):
    """ GIVEN non-existent ID; WHEN GET /campaigns/{id}; THEN 404 """
    response = logged_in_client.get('/api/seller/campaigns/99999')
    assert response.status_code == 404


# --- Test PUT /api/seller/campaigns/{campaign_id} ---

def test_seller_update_own_campaign_success(logged_in_client, session):
    """ GIVEN seller owns campaign; WHEN PUT /campaigns/{id} with valid data; THEN 200 """
    # Arrange
    campaign_data = create_campaign_via_api(logged_in_client, "Update Campaign API Test", status="active")
    target_id = campaign_data['id']
    update_payload = {"name": "Update API (Updated)", "routingStrategy": "round_robin", "status": "paused", "dialTimeoutSeconds": 45}

    # Act
    response = logged_in_client.put(f'/api/seller/campaigns/{target_id}', json=update_payload)

    # Assert Response
    assert response.status_code == 200
    data = response.get_json()
    assert data['id'] == target_id
    assert data['name'] == update_payload['name']
    assert data['status'] == update_payload['status']

    # Assert Database
    updated_campaign_db = session.get(CampaignModel, target_id)
    assert updated_campaign_db.name == update_payload['name']
    assert updated_campaign_db.status == update_payload['status']


def test_seller_update_other_campaign_fail(logged_in_client, session):
    """ GIVEN campaign owned by another; WHEN PUT /campaigns/{id}; THEN 404/403 """
    # Arrange: Create campaign for another user
    other_user = UserService.create_user("otherseller_camp_upd_api", "other_upd_api@s.com", "Pass123")
    session.flush()
    other_campaign = CampaignService.create_campaign(other_user.id, "Other Seller Upd API", "priority", 30)
    session.flush()
    target_id = other_campaign.id
    update_payload = {"name": "Attempted Update API"}

    # Act
    response = logged_in_client.put(f'/api/seller/campaigns/{target_id}', json=update_payload)

    # Assert (Service raises ResourceNotFound or AuthorizationError, maps to 404/403)
    assert response.status_code in [403, 404]


def test_seller_update_campaign_duplicate_name_fail(logged_in_client, session):
    """ GIVEN seller owns two campaigns; WHEN PUT renames one to match other; THEN 409 """
    # Arrange
    campaign1_data = create_campaign_via_api(logged_in_client, "Unique Name API 1")
    campaign2_data = create_campaign_via_api(logged_in_client, "Unique Name API 2")
    update_payload = {"name": campaign1_data['name']} # Try renaming campaign2 to campaign1's name

    # Act
    response = logged_in_client.put(f'/api/seller/campaigns/{campaign2_data["id"]}', json=update_payload)

    # Assert
    assert response.status_code == 409
    assert f"Campaign name '{campaign1_data['name']}' already exists" in response.get_json().get('message', '')


# --- Test DELETE /api/seller/campaigns/{campaign_id} ---

def test_seller_delete_own_campaign_success(logged_in_client, session):
    """ GIVEN seller owns campaign; WHEN DELETE /campaigns/{id}; THEN 204 """
    # Arrange
    campaign_data = create_campaign_via_api(logged_in_client, "Delete Campaign API Test")
    target_id = campaign_data['id']
    assert session.get(CampaignModel, target_id) is not None # Verify exists before API call

    # Act
    response = logged_in_client.delete(f'/api/seller/campaigns/{target_id}')

    # Assert Response
    assert response.status_code == 204

    # Assert Database
    assert session.get(CampaignModel, target_id) is None


def test_seller_delete_other_campaign_fail(logged_in_client, session):
    """ GIVEN campaign owned by another; WHEN DELETE /campaigns/{id}; THEN 404/403 """
    # Arrange
    other_user = UserService.create_user("otherseller_camp_del_api", "other_del_api@s.com", "Pass123")
    session.flush()
    other_campaign = CampaignService.create_campaign(other_user.id, "Other Seller Del API", "priority", 30)
    session.flush()
    target_id = other_campaign.id

    # Act
    response = logged_in_client.delete(f'/api/seller/campaigns/{target_id}')

    # Assert
    assert response.status_code in [403, 404]


# --- Test PUT /api/seller/campaigns/{campaign_id}/dids ---

def test_seller_set_campaign_dids_success(logged_in_client, session):
    """ GIVEN seller owns campaign and DIDs; WHEN PUT /campaigns/{id}/dids; THEN 200 """
    # Arrange
    campaign_data = create_campaign_via_api(logged_in_client, "Set DIDs Camp API")
    did1_data = create_did_via_api(logged_in_client, "+15550101010")
    did2_data = create_did_via_api(logged_in_client, "+15550101011")
    did3_data = create_did_via_api(logged_in_client, "+15550101012")
    campaign_id = campaign_data['id']
    # Add initial link to remove later
    link_resp = logged_in_client.put(f'/api/seller/campaigns/{campaign_id}/dids', json={"didIds": [did1_data['id']]})
    assert link_resp.status_code == 200

    # Act: Replace link to did1 with links to did2 and did3
    payload = {"didIds": [did2_data['id'], did3_data['id']]}
    response = logged_in_client.put(f'/api/seller/campaigns/{campaign_id}/dids', json=payload)

    # Assert Response
    assert response.status_code == 200

    # Assert Database state
    links = session.query(CampaignDidModel).filter_by(campaign_id=campaign_id).all()
    linked_did_ids = {link.did_id for link in links}
    assert len(links) == 2
    assert did1_data['id'] not in linked_did_ids
    assert did2_data['id'] in linked_did_ids
    assert did3_data['id'] in linked_did_ids


def test_seller_set_campaign_dids_clear_success(logged_in_client, session):
    """ GIVEN campaign has linked DIDs; WHEN PUT /campaigns/{id}/dids with empty list; THEN 200 """
    # Arrange
    campaign_data = create_campaign_via_api(logged_in_client, "Clear DIDs Camp API")
    did1_data = create_did_via_api(logged_in_client, "+15550202020")
    campaign_id = campaign_data['id']
    link_resp = logged_in_client.put(f'/api/seller/campaigns/{campaign_id}/dids', json={"didIds": [did1_data['id']]})
    assert link_resp.status_code == 200
    assert session.query(CampaignDidModel).filter_by(campaign_id=campaign_id).count() == 1 # Verify initial state

    # Act: Send empty list
    payload = {"didIds": []}
    response = logged_in_client.put(f'/api/seller/campaigns/{campaign_id}/dids', json=payload)

    # Assert Response
    assert response.status_code == 200

    # Assert Database state
    assert session.query(CampaignDidModel).filter_by(campaign_id=campaign_id).count() == 0


def test_seller_set_campaign_dids_fail_did_not_owned(logged_in_client, session):
    """ GIVEN DID owned by another; WHEN PUT /campaigns/{id}/dids with that DID; THEN 403 """
     # Arrange
    campaign_data = create_campaign_via_api(logged_in_client, "Not Owned DID Camp API")
    campaign_id = campaign_data['id']
    # Create DID owned by another user (use service, will rollback)
    other_user = UserService.create_user("otherseller_didlink_api", "other_link_api@s.com", "Pass123")
    session.flush()
    other_did = DidService.add_did(user_id=other_user.id, number="+15550303030")
    session.flush()
    other_did_id = other_did.id

    # Act: Try to link other user's DID
    payload = {"didIds": [other_did_id]}
    response = logged_in_client.put(f'/api/seller/campaigns/{campaign_id}/dids', json=payload)

    # Assert
    assert response.status_code == 403 # Service should raise AuthorizationError -> 403
    assert "not owned by the user" in response.get_json().get('message', '')


def test_seller_set_campaign_dids_fail_campaign_not_owned(logged_in_client, session):
    """ GIVEN campaign owned by another; WHEN PUT /campaigns/{id}/dids; THEN 404 """
    # Arrange
    my_did_data = create_did_via_api(logged_in_client, "+15550404040") # DID owned by logged-in user
    my_did_id = my_did_data['id']
    # Campaign owned by other user (use service, will rollback)
    other_user = UserService.create_user("otherseller_didlink2_api", "other_link2_api@s.com", "Pass123")
    session.flush()
    other_campaign = CampaignService.create_campaign(other_user.id, "Other User Set DID Camp API", "priority", 30)
    session.flush()
    other_campaign_id = other_campaign.id

    payload = {"didIds": [my_did_id]}

    # Act
    response = logged_in_client.put(f'/api/seller/campaigns/{other_campaign_id}/dids', json=payload)

    # Assert
    assert response.status_code == 404 # Service raises AuthorizationError -> route maps to 404 if campaign not owned
    assert f"User not authorized for campaign {other_campaign_id}" in response.get_json().get('message', '')


# --- Test GET /api/seller/campaigns/available_clients ---

def test_seller_get_available_clients(logged_in_client, logged_in_admin_client, session):
    """ GIVEN active/inactive clients exist; WHEN GET /available_clients; THEN 200 """
    # Arrange: Ensure an inactive client exists (created via admin API)
    payload = {"clientIdentifier": "inactive_test_api", "name": "Inactive API Test", "status": "inactive", "pjsip": {"endpoint": {"id": "inactive_test_api", "context": "ctx", "aors":"inactive_test_api"}, "aor": {"id": "inactive_test_api", "contact": "sip:inactive_api"}}}
    res = logged_in_admin_client.post('/api/admin/clients', json=payload)
    assert res.status_code == 201

    # Act: Use the seller client
    response = logged_in_client.get('/api/seller/campaigns/available_clients')

    # Assert
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)
    assert len(data) >= 3 # At least alpha, beta, gamma from sample
    identifiers = {item['clientIdentifier'] for item in data}
    assert 'client_alpha_sales' in identifiers
    assert 'client_beta_support' in identifiers
    assert 'client_gamma_intake' in identifiers
    assert 'inactive_test_api' not in identifiers # Should only list active
    assert 'id' in data[0] and 'name' in data[0] and 'clientIdentifier' in data[0]
    assert 'status' not in data[0] and 'pjsipEndpoint' not in data[0] # Check excluded fields


# --- Test POST /api/seller/campaigns/{campaign_id}/clients ---

def test_seller_add_client_link_success(logged_in_client, session):
    """ GIVEN seller owns campaign, client exists; WHEN POST /clients with valid settings; THEN 201 """
    # Arrange
    campaign_data = create_campaign_via_api(logged_in_client, "Link Client Camp API")
    campaign_id = campaign_data['id']
    client_id = 2 # Use Client Beta (ID 2 from sample data)
    settings_payload = {"clientId": client_id, "maxConcurrency": 7, "totalCallsAllowed": 500, "forwardingPriority": 1, "weight": 150, "status": "active"}

    # Act
    response = logged_in_client.post(f'/api/seller/campaigns/{campaign_id}/clients', json=settings_payload)

    # Assert Response
    assert response.status_code == 201
    data = response.get_json()
    assert data['client']['id'] == client_id
    assert data['maxConcurrency'] == settings_payload['maxConcurrency']
    assert 'id' in data
    setting_id = data['id']

    # Assert Database
    setting_db = session.get(CampaignClientSettingsModel, setting_id)
    assert setting_db is not None and setting_db.campaign_id == campaign_id and setting_db.client_id == client_id


def test_seller_add_client_link_duplicate_fail(logged_in_client, session):
    """ GIVEN client already linked; WHEN POST /clients for same client; THEN 409 """
    # Arrange
    campaign_data = create_campaign_via_api(logged_in_client, "Duplicate Link Camp API")
    campaign_id = campaign_data['id']
    client_id = 1 # Alpha
    # Link it first
    settings1 = {"clientId": client_id, "maxConcurrency": 5, "forwardingPriority": 0, "weight": 100}
    res1 = logged_in_client.post(f'/api/seller/campaigns/{campaign_id}/clients', json=settings1)
    assert res1.status_code == 201

    # Attempt duplicate link
    settings2 = {"clientId": client_id, "maxConcurrency": 1, "forwardingPriority": 1, "weight": 1}
    response = logged_in_client.post(f'/api/seller/campaigns/{campaign_id}/clients', json=settings2)

    # Assert
    assert response.status_code == 409
    assert f"Client {client_id} is already linked" in response.get_json().get('message', '')


def test_seller_add_client_link_missing_settings(logged_in_client, session):
    """ GIVEN missing required settings; WHEN POST /clients; THEN 400 """
    # Arrange
    campaign_data = create_campaign_via_api(logged_in_client, "Missing Settings Camp API")
    campaign_id = campaign_data['id']
    client_id = 1 # Alpha
    settings_payload = {"clientId": client_id} # Missing maxConcurrency, etc.

    # Act
    response = logged_in_client.post(f'/api/seller/campaigns/{campaign_id}/clients', json=settings_payload)

    # Assert
    assert response.status_code == 400
    errors = response.get_json().get('errors', {})
    assert 'maxConcurrency' in errors and 'forwardingPriority' in errors and 'weight' in errors


# --- Test PUT /api/seller/campaigns/{campaign_id}/clients/{setting_id} ---

def test_seller_update_client_setting_success(logged_in_client, session):
    """ GIVEN seller owns campaign and setting; WHEN PUT setting with valid updates; THEN 200 """
    # Arrange
    campaign_data = create_campaign_via_api(logged_in_client, "Update Setting Camp API")
    campaign_id = campaign_data['id']
    client_id = 1 # Alpha
    settings1 = {"clientId": client_id, "maxConcurrency": 5, "forwardingPriority": 0, "weight": 100, "status": "active"}
    res1 = logged_in_client.post(f'/api/seller/campaigns/{campaign_id}/clients', json=settings1)
    assert res1.status_code == 201
    setting_id = res1.get_json()['id']

    update_payload = {"maxConcurrency": 8, "status": "inactive", "forwardingPriority": 10} # Partial

    # Act
    response = logged_in_client.put(f'/api/seller/campaigns/{campaign_id}/clients/{setting_id}', json=update_payload)

    # Assert Response
    assert response.status_code == 200
    data = response.get_json()
    assert data['id'] == setting_id
    assert data['maxConcurrency'] == 8
    assert data['status'] == "inactive"

    # Assert Database
    setting_db = session.get(CampaignClientSettingsModel, setting_id)
    assert setting_db.max_concurrency == 8 and setting_db.status == "inactive"


def test_seller_update_client_setting_fail_not_found(logged_in_client, session):
    """ GIVEN non-existent setting ID; WHEN PUT setting; THEN 404 """
    # Arrange
    campaign_data = create_campaign_via_api(logged_in_client, "Update Missing Setting API")
    campaign_id = campaign_data['id']
    update_payload = {"status": "inactive"}

    # Act
    response = logged_in_client.put(f'/api/seller/campaigns/{campaign_id}/clients/99999', json=update_payload)

    # Assert
    assert response.status_code == 404


def test_seller_update_client_setting_fail_wrong_campaign(logged_in_client, session):
    """ GIVEN setting exists for camp A; WHEN PUT via camp B URL; THEN 404 """
    # Arrange
    camp_a_data = create_campaign_via_api(logged_in_client, "Update Wrong Camp A API")
    camp_b_data = create_campaign_via_api(logged_in_client, "Update Wrong Camp B API")
    client_id = 1
    settings1 = {"clientId": client_id, "maxConcurrency": 5, "forwardingPriority": 0, "weight": 100}
    res1 = logged_in_client.post(f'/api/seller/campaigns/{camp_a_data["id"]}/clients', json=settings1)
    assert res1.status_code == 201
    setting_a_id = res1.get_json()['id']
    camp_b_id = camp_b_data['id']
    update_payload = {"status": "inactive"}

    # Act: Try to update Setting A via Campaign B's endpoint
    response = logged_in_client.put(f'/api/seller/campaigns/{camp_b_id}/clients/{setting_a_id}', json=update_payload)

    # Assert
    assert response.status_code == 404 # Service raises ResourceNotFound


# --- Test DELETE /api/seller/campaigns/{campaign_id}/clients/{setting_id} ---

def test_seller_remove_client_link_success(logged_in_client, session):
    """ GIVEN seller owns campaign and setting; WHEN DELETE setting; THEN 204 """
    # Arrange
    campaign_data = create_campaign_via_api(logged_in_client, "Remove Link Camp API")
    campaign_id = campaign_data['id']
    client_id = 1
    settings1 = {"clientId": client_id, "maxConcurrency": 5, "forwardingPriority": 0, "weight": 100}
    res1 = logged_in_client.post(f'/api/seller/campaigns/{campaign_id}/clients', json=settings1)
    assert res1.status_code == 201
    setting_id = res1.get_json()['id']
    assert session.get(CampaignClientSettingsModel, setting_id) is not None # Verify exists

    # Act
    response = logged_in_client.delete(f'/api/seller/campaigns/{campaign_id}/clients/{setting_id}')

    # Assert Response
    assert response.status_code == 204

    # Assert Database
    assert session.get(CampaignClientSettingsModel, setting_id) is None


def test_seller_remove_client_link_fail_not_found(logged_in_client, session):
    """ GIVEN non-existent setting ID; WHEN DELETE setting; THEN 404 """
    # Arrange
    campaign_data = create_campaign_via_api(logged_in_client, "Remove Missing Setting API")
    campaign_id = campaign_data['id']

    # Act
    response = logged_in_client.delete(f'/api/seller/campaigns/{campaign_id}/clients/99999')

    # Assert
    assert response.status_code == 404


def test_seller_remove_client_link_fail_wrong_campaign(logged_in_client, session):
    """ GIVEN setting exists for camp A; WHEN DELETE via camp B URL; THEN 404 """
    # Arrange
    camp_a_data = create_campaign_via_api(logged_in_client, "Remove Wrong Camp A API")
    camp_b_data = create_campaign_via_api(logged_in_client, "Remove Wrong Camp B API")
    client_id = 1
    settings1 = {"clientId": client_id, "maxConcurrency": 5, "forwardingPriority": 0, "weight": 100}
    res1 = logged_in_client.post(f'/api/seller/campaigns/{camp_a_data["id"]}/clients', json=settings1)
    assert res1.status_code == 201
    setting_a_id = res1.get_json()['id']
    camp_b_id = camp_b_data['id']

    # Act: Try to delete Setting A via Campaign B's endpoint
    response = logged_in_client.delete(f'/api/seller/campaigns/{camp_b_id}/clients/{setting_a_id}')

    # Assert
    assert response.status_code == 404 # Service raises ResourceNotFound